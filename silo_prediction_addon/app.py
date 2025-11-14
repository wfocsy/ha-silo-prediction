from flask import Flask, jsonify, request
import json
import os
import requests
import logging
import pymysql
import numpy as np
from datetime import datetime, timedelta
from scipy import stats
import threading
import time
from dateutil import tz

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SiloPredictionService:
    def __init__(self, config):
        self.config = config
        self.db_config = config.get('database', {})
        self.silos = config.get('silos', [])
        self.prediction_config = config.get('prediction', {})
        self.predictions = {}
        self.last_update = {}
        
    def get_db_connection(self):
        """Create database connection"""
        try:
            connection = pymysql.connect(
                host=self.db_config.get('host', 'core-mariadb'),
                port=self.db_config.get('port', 3306),
                user=self.db_config.get('username', 'homeassistant'),
                password=self.db_config.get('password', ''),
                database=self.db_config.get('database', 'homeassistant'),
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            return connection
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return None
    
    def get_historical_data(self, entity_id, days=10):
        """Get historical data for entity from Home Assistant database"""
        connection = self.get_db_connection()
        if not connection:
            logger.error("No database connection!")
            return []

        try:
            with connection.cursor() as cursor:
                # DEBUG 1: Létezik egyáltalán az entity_id a states táblában?
                debug_query = "SELECT COUNT(*) as total FROM states WHERE entity_id = %s"
                cursor.execute(debug_query, (entity_id,))
                total_count = cursor.fetchone()
                logger.info(f"Total rows in states for '{entity_id}': {total_count}")

                # DEBUG 2: Ha 0, keressük meg hasonló nevű entitásokat
                if total_count['total'] == 0:
                    logger.warning(f"Entity '{entity_id}' not found in states table!")
                    similar_query = "SELECT DISTINCT entity_id FROM states WHERE entity_id LIKE %s LIMIT 10"
                    cursor.execute(similar_query, (f"%{entity_id.split('.')[-1][:20]}%",))
                    similar = cursor.fetchall()
                    logger.info(f"Similar entities found: {similar}")

                    # DEBUG 3: Nézzük a statistics táblát is
                    stats_query = "SELECT COUNT(*) as total FROM statistics_meta WHERE statistic_id = %s"
                    cursor.execute(stats_query, (entity_id,))
                    stats_count = cursor.fetchone()
                    logger.info(f"Found in statistics_meta: {stats_count}")

                    # Ha megtaláltuk a statistics_meta-ban, használjuk azt!
                    if stats_count['total'] > 0:
                        logger.info(f"Using statistics table instead of states for {entity_id}")

                        # DEBUG: Nézzük meg az összes statistics sort
                        total_stats_query = """
                        SELECT COUNT(*) as total
                        FROM statistics s
                        JOIN statistics_meta sm ON s.metadata_id = sm.id
                        WHERE sm.statistic_id = %s
                        """
                        cursor.execute(total_stats_query, (entity_id,))
                        total_stats = cursor.fetchone()
                        logger.info(f"Total statistics rows for {entity_id}: {total_stats}")

                        # DEBUG: Legfrissebb és legrégebbi dátum - try different column names
                        # Próbáljuk created, start, start_ts
                        date_range_query = """
                        SELECT MIN(s.created) as oldest_created, MAX(s.created) as newest_created,
                               MIN(s.start_ts) as oldest_ts, MAX(s.start_ts) as newest_ts
                        FROM statistics s
                        JOIN statistics_meta sm ON s.metadata_id = sm.id
                        WHERE sm.statistic_id = %s
                        """
                        cursor.execute(date_range_query, (entity_id,))
                        date_range = cursor.fetchone()
                        logger.info(f"Statistics date range: {date_range}")

                        # DEBUG: Show first row structure
                        sample_query = """
                        SELECT *
                        FROM statistics s
                        JOIN statistics_meta sm ON s.metadata_id = sm.id
                        WHERE sm.statistic_id = %s
                        LIMIT 1
                        """
                        cursor.execute(sample_query, (entity_id,))
                        sample = cursor.fetchone()
                        logger.info(f"Sample statistics row columns: {list(sample.keys()) if sample else 'None'}")

                        # Statistics query - használjuk a start_ts Unix timestampet!
                        stats_data_query = """
                        SELECT
                            FROM_UNIXTIME(s.start_ts) as start_datetime,
                            s.start_ts,
                            s.mean as state
                        FROM statistics s
                        JOIN statistics_meta sm ON s.metadata_id = sm.id
                        WHERE sm.statistic_id = %s
                            AND s.start_ts >= UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 30 DAY))
                        ORDER BY s.start_ts ASC
                        """
                        cursor.execute(stats_data_query, (entity_id,))
                        results = cursor.fetchall()

                        logger.info(f"Statistics query returned {len(results)} rows for {entity_id}")

                        # Convert to list of tuples (datetime, weight)
                        data = []
                        for row in results:
                            try:
                                weight = float(row['state'])
                                if weight > 0:
                                    dt = row['start_datetime']
                                    if isinstance(dt, str):
                                        dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                                    data.append((dt, weight))
                            except (ValueError, TypeError):
                                continue

                        logger.info(f"Retrieved {len(data)} valid data points from statistics for {entity_id}")
                        return data

                    return []

                # Egyszerűsített query - csak az alapokat kérjük le
                query = """
                SELECT
                    state,
                    last_changed
                FROM states
                WHERE entity_id = %s
                    AND last_changed >= DATE_SUB(NOW(), INTERVAL %s DAY)
                ORDER BY last_changed ASC
                """
                cursor.execute(query, (entity_id, days))
                results = cursor.fetchall()

                logger.info(f"Raw query returned {len(results)} rows for {entity_id}")

                # Convert to list of tuples (datetime, weight) with filtering in Python
                data = []
                for row in results:
                    try:
                        # Try to convert state to float
                        weight = float(row['state'])
                        if weight > 0:  # Only positive weights
                            dt = row['last_changed']
                            if isinstance(dt, str):
                                dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                            data.append((dt, weight))
                    except (ValueError, TypeError) as e:
                        # Skip non-numeric states
                        continue

                logger.info(f"Retrieved {len(data)} valid data points for {entity_id}")
                return data
                
        except Exception as e:
            logger.error(f"Error getting historical data: {e}")
            return []
        finally:
            connection.close()
    
    def detect_refill(self, data, threshold=8000):
        """Detect refill events in the data"""
        if len(data) < 2:
            return []
        
        refills = []
        for i in range(1, len(data)):
            prev_weight = data[i-1][1]
            curr_weight = data[i][1]
            weight_increase = curr_weight - prev_weight
            
            if weight_increase >= threshold:
                refills.append({
                    'timestamp': data[i][0],
                    'increase': weight_increase,
                    'before': prev_weight,
                    'after': curr_weight
                })
                logger.info(f"Refill detected at {data[i][0]}: {weight_increase}kg increase")
        
        return refills
    
    def get_data_after_last_refill(self, data, refills):
        """Get data points after the last refill"""
        if not refills:
            return data
        
        last_refill_time = refills[-1]['timestamp']
        filtered_data = [(dt, weight) for dt, weight in data if dt > last_refill_time]
        
        logger.info(f"Using {len(filtered_data)} data points after last refill at {last_refill_time}")
        return filtered_data
    
    def calculate_prediction(self, data):
        """Calculate when silo will be empty using derivative-based approach"""
        if len(data) < self.prediction_config.get('min_data_points', 24):
            return None
        
        try:
            # Convert to numpy arrays
            timestamps = [dt.timestamp() for dt, weight in data]
            weights = [weight for dt, weight in data]
            
            # Convert timestamps to hours from start
            start_time = timestamps[0]
            hours = [(ts - start_time) / 3600 for ts in timestamps]
            
            # Calculate consumption rate using polynomial fit (2nd degree)
            # This captures the non-linear nature of consumption
            coefficients = np.polyfit(hours, weights, 2)
            poly_func = np.poly1d(coefficients)
            
            # Find when weight reaches 0
            # Solve: ax² + bx + c = 0
            a, b, c = coefficients
            
            if abs(a) < 1e-10:  # Nearly linear case
                if abs(b) < 1e-10:  # Constant weight
                    return None
                empty_hours = -c / b
            else:
                # Quadratic formula
                discriminant = b**2 - 4*a*c
                if discriminant < 0:
                    return None
                
                # Take the positive root that's in the future
                root1 = (-b + np.sqrt(discriminant)) / (2*a)
                root2 = (-b - np.sqrt(discriminant)) / (2*a)
                
                # Choose the root that's greater than current time
                current_hours = hours[-1]
                empty_hours = None
                
                for root in [root1, root2]:
                    if root > current_hours:
                        if empty_hours is None or root < empty_hours:
                            empty_hours = root
                
                if empty_hours is None:
                    return None
            
            # Convert back to datetime
            empty_timestamp = start_time + empty_hours * 3600
            empty_datetime = datetime.fromtimestamp(empty_timestamp)
            
            # Get current weight (last data point)
            current_weight = weights[-1]
            current_time = data[-1][0]
            
            # Calculate consumption rate (kg/day) at current point
            if len(data) >= 2:
                recent_hours = hours[-10:] if len(hours) >= 10 else hours
                recent_weights = weights[-10:] if len(weights) >= 10 else weights
                
                if len(recent_hours) >= 2:
                    rate_per_hour = (recent_weights[0] - recent_weights[-1]) / (recent_hours[-1] - recent_hours[0])
                    rate_per_day = rate_per_hour * 24
                else:
                    rate_per_day = 0
            else:
                rate_per_day = 0
            
            # Calculate R² to assess prediction quality
            predicted_weights = [poly_func(h) for h in hours]
            ss_res = sum((weights[i] - predicted_weights[i])**2 for i in range(len(weights)))
            ss_tot = sum((w - np.mean(weights))**2 for w in weights)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            
            prediction = {
                'empty_datetime': empty_datetime,
                'current_weight': current_weight,
                'current_time': current_time,
                'consumption_rate_kg_day': abs(rate_per_day),
                'prediction_accuracy': r_squared,
                'data_points_used': len(data),
                'method': 'polynomial_2nd_degree'
            }
            
            logger.info(f"Prediction calculated: empty at {empty_datetime}, current: {current_weight}kg, rate: {rate_per_day:.2f}kg/day")
            return prediction
            
        except Exception as e:
            logger.error(f"Error calculating prediction: {e}")
            return None
    
    def update_home_assistant_entity(self, silo_config, prediction):
        """Update Home Assistant entity with prediction - DIRECTLY via database"""
        try:
            connection = self.get_db_connection()
            if not connection:
                logger.error("No database connection for entity update!")
                return False
            
            if not prediction:
                state = "unknown"
                attributes = {
                    "friendly_name": f"{silo_config['name']} Empty Prediction",
                    "device_class": "timestamp",
                    "status": "insufficient_data",
                    "last_update": datetime.now().isoformat()
                }
            else:
                # Convert to Home Assistant timezone
                local_tz = tz.gettz()  # Gets system timezone
                empty_time_local = prediction['empty_datetime'].replace(tzinfo=tz.tzutc()).astimezone(local_tz)
                
                state = empty_time_local.isoformat()
                attributes = {
                    "friendly_name": f"{silo_config['name']} Empty Prediction",
                    "device_class": "timestamp",
                    "current_weight": prediction['current_weight'],
                    "consumption_rate_kg_day": round(prediction['consumption_rate_kg_day'], 2),
                    "prediction_accuracy": round(prediction['prediction_accuracy'], 3),
                    "data_points_used": prediction['data_points_used'],
                    "method": prediction['method'],
                    "last_update": datetime.now().isoformat(),
                    "status": "predicted"
                }
            
            # Update entity state DIRECTLY in database
            entity_id = silo_config['prediction_entity']

            # DEBUG: Log what we're trying to insert
            logger.info(f"DEBUG - entity_id: '{entity_id}' (length: {len(entity_id)})")
            logger.info(f"DEBUG - state: '{state}' (length: {len(state)})")

            try:
                with connection.cursor() as cursor:
                    # Convert attributes to JSON
                    import json
                    attributes_json = json.dumps(attributes)

                    # DEBUG: Check states_meta table
                    meta_query = "DESCRIBE states_meta"
                    cursor.execute(meta_query)
                    meta_schema = cursor.fetchall()
                    logger.info(f"DEBUG - states_meta table schema: {meta_schema}")

                    # Check if our entity exists in states_meta
                    check_meta_query = "SELECT * FROM states_meta WHERE entity_id = %s"
                    cursor.execute(check_meta_query, (entity_id,))
                    existing_meta = cursor.fetchone()
                    logger.info(f"DEBUG - Existing metadata for {entity_id}: {existing_meta}")

                    # Első: Ellenőrizzük hogy létezik-e már az entitás
                    check_query = "SELECT entity_id FROM states WHERE entity_id = %s ORDER BY last_updated DESC LIMIT 1"
                    cursor.execute(check_query, (entity_id,))
                    exists = cursor.fetchone()

                    if exists:
                        # UPDATE existing entity
                        update_query = """
                        UPDATE states
                        SET state = %s,
                            attributes = %s,
                            last_changed = NOW(),
                            last_updated = NOW()
                        WHERE entity_id = %s
                        AND last_updated = (SELECT MAX(last_updated) FROM (SELECT * FROM states) AS s WHERE entity_id = %s)
                        """
                        logger.info(f"DEBUG - Executing UPDATE for {entity_id}")
                        cursor.execute(update_query, (state, attributes_json, entity_id, entity_id))
                    else:
                        # INSERT new entity
                        insert_query = """
                        INSERT INTO states (entity_id, state, attributes, last_changed, last_updated)
                        VALUES (%s, %s, %s, NOW(), NOW())
                        """
                        logger.info(f"DEBUG - Executing INSERT for {entity_id}")
                        logger.info(f"DEBUG - INSERT params: entity_id='{entity_id}', state='{state}', attributes_len={len(attributes_json)}")
                        cursor.execute(insert_query, (entity_id, state, attributes_json))

                    connection.commit()
                    logger.info(f"Updated entity {entity_id} successfully in database (state: {state[:50]})")
                    return True

            finally:
                connection.close()

        except Exception as e:
            logger.error(f"Error updating Home Assistant entity: {e}", exc_info=True)
            return False
    
    def process_silo(self, silo_config):
        """Process a single silo for prediction"""
        try:
            entity_id = silo_config['entity_id']
            logger.info(f"Processing silo: {silo_config['name']}")
            
            # Get historical data
            days = self.prediction_config.get('history_days', 10)
            data = self.get_historical_data(entity_id, days)
            
            if not data:
                logger.warning(f"No data found for {entity_id}")
                self.update_home_assistant_entity(silo_config, None)
                return
            
            # Detect refills
            threshold = self.prediction_config.get('refill_detection_threshold', 8000)
            refills = self.detect_refill(data, threshold)
            
            # Use data after last refill
            filtered_data = self.get_data_after_last_refill(data, refills)
            
            if not filtered_data:
                logger.warning(f"No data after refill for {entity_id}")
                self.update_home_assistant_entity(silo_config, None)
                return
            
            # Calculate prediction
            prediction = self.calculate_prediction(filtered_data)
            
            # Store prediction
            self.predictions[entity_id] = prediction
            self.last_update[entity_id] = datetime.now()
            
            # Update Home Assistant entity
            self.update_home_assistant_entity(silo_config, prediction)
            
        except Exception as e:
            logger.error(f"Error processing silo {silo_config['name']}: {e}")
    
    def update_all_predictions(self):
        """Update predictions for all configured silos"""
        logger.info("Starting prediction update for all silos")
        for silo_config in self.silos:
            self.process_silo(silo_config)
        logger.info("Completed prediction update for all silos")
    
    def start_background_updates(self):
        """Start background thread for periodic updates"""
        def update_loop():
            while True:
                try:
                    self.update_all_predictions()
                    interval = self.prediction_config.get('update_interval', 3600)
                    time.sleep(interval)
                except Exception as e:
                    logger.error(f"Error in update loop: {e}")
                    time.sleep(60)  # Wait 1 minute before retrying
        
        update_thread = threading.Thread(target=update_loop, daemon=True)
        update_thread.start()
        logger.info("Background update thread started")

# Load configuration
def load_config():
    """Load configuration from Home Assistant Add-on options"""
    config_path = '/data/options.json'
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return {}

config = load_config()
prediction_service = SiloPredictionService(config)

@app.route('/')
def index():
    """Main page"""
    return jsonify({
        "name": "Silo Prediction Add-on",
        "version": "1.0.0",
        "status": "running",
        "silos_configured": len(prediction_service.silos),
        "last_updates": {k: v.isoformat() for k, v in prediction_service.last_update.items()}
    })

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"})

@app.route('/api/predictions')
def get_predictions():
    """Get current predictions for all silos"""
    result = {}
    for entity_id, prediction in prediction_service.predictions.items():
        if prediction:
            result[entity_id] = {
                "empty_datetime": prediction['empty_datetime'].isoformat(),
                "current_weight": prediction['current_weight'],
                "consumption_rate_kg_day": prediction['consumption_rate_kg_day'],
                "prediction_accuracy": prediction['prediction_accuracy'],
                "data_points_used": prediction['data_points_used'],
                "method": prediction['method']
            }
        else:
            result[entity_id] = None
    
    return jsonify(result)

@app.route('/api/update', methods=['POST'])
def trigger_update():
    """Manually trigger prediction update"""
    try:
        prediction_service.update_all_predictions()
        return jsonify({"status": "success", "message": "Predictions updated"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/silo/<entity_id>')
def get_silo_info(entity_id):
    """Get detailed info for specific silo"""
    # Find silo config
    silo_config = None
    for silo in prediction_service.silos:
        if silo['entity_id'] == entity_id:
            silo_config = silo
            break
    
    if not silo_config:
        return jsonify({"error": "Silo not found"}), 404
    
    # Get current prediction
    prediction = prediction_service.predictions.get(entity_id)
    last_update = prediction_service.last_update.get(entity_id)
    
    # Get recent historical data for display
    data = prediction_service.get_historical_data(entity_id, 2)  # Last 2 days
    
    result = {
        "silo_config": silo_config,
        "prediction": prediction,
        "last_update": last_update.isoformat() if last_update else None,
        "recent_data_points": len(data),
        "current_weight": data[-1][1] if data else None,
        "current_time": data[-1][0].isoformat() if data else None
    }
    
    return jsonify(result)

if __name__ == '__main__':
    logger.info("Starting Silo Prediction Add-on...")
    
    # Start background updates
    prediction_service.start_background_updates()
    
    # Run initial update
    prediction_service.update_all_predictions()
    
    # Start Flask app
    app.run(host='0.0.0.0', port=5001, debug=False)
