
from flask import Flask, jsonify
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline
import mysql.connector
from datetime import datetime, timedelta

app = Flask(__name__)

# --- KONFIGURÁCIÓ ---
MONITORED_ENTITY_ID = "sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly"
DB_HOST = "localhost"
DB_USER = "homeassistant"
DB_PASSWORD = "Pozsi1981"
DB_NAME = "homeassistant"

@app.route('/predict', methods=['GET'])
def predict():
    try:
        # 1. MariaDB Adatbázis Kapcsolódás és Adatgyűjtés
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        cursor = conn.cursor()
        start_date = (datetime.utcnow() - timedelta(days=30)).isoformat(timespec='seconds') + 'Z'
        query = f"""
        SELECT state, last_changed
        FROM states
        WHERE entity_id = '{MONITORED_ENTITY_ID}'
        AND last_changed >= '{start_date}'
        ORDER BY last_changed ASC;
        """
        cursor.execute(query)
        data = cursor.fetchall()
        if not data:
            return jsonify({"error": "No data for prediction", "status": "nodata"})
        df = pd.DataFrame(data, columns=['state', 'last_changed'])
        df['last_changed'] = pd.to_datetime(df['last_changed'])
        df['state'] = pd.to_numeric(df['state'], errors='coerce')
        df.dropna(subset=['state', 'last_changed'], inplace=True)
        df = df[df['state'] >= 0]
        if df.empty:
            return jsonify({"error": "DataFrame empty after cleaning", "status": "nodata"})
        df = df.set_index('last_changed')
        df_resampled = df['state'].resample('H').mean()
        df_resampled.dropna(inplace=True)
        if df_resampled.empty or len(df_resampled) < 2:
            return jsonify({"error": "Not enough data points for prediction", "status": "nodata"})
        # 2. Polinom regresszió
        df_reg = pd.DataFrame({'timestamp': df_resampled.index, 'weight': df_resampled.values})
        min_timestamp = df_reg['timestamp'].min()
        df_reg['timestamp_numeric'] = (df_reg['timestamp'] - min_timestamp).dt.total_seconds()
        X = df_reg[['timestamp_numeric']]
        y = df_reg['weight']
        if len(X) < 2:
            return jsonify({"error": "Not enough data points for regression", "status": "nodata"})
        degree = 2
        poly_model = make_pipeline(PolynomialFeatures(degree), LinearRegression())
        poly_model.fit(X, y)
        if y.iloc[-1] <= 0:
            return jsonify({"predicted_0kg": datetime.now().isoformat(), "status": "empty"})
        last_timestamp_numeric = X['timestamp_numeric'].max()
        future_timestamps_numeric = np.linspace(
            last_timestamp_numeric, last_timestamp_numeric + (60 * 24 * 3600), 500
        ).reshape(-1, 1)
        predicted_future_weights = poly_model.predict(future_timestamps_numeric)
        predicted_0kg_numeric_time = None
        for i, weight in enumerate(predicted_future_weights):
            if weight <= 0:
                predicted_0kg_numeric_time = future_timestamps_numeric[i][0]
                break
        if predicted_0kg_numeric_time is not None:
            predicted_date_utc = min_timestamp + pd.to_timedelta(predicted_0kg_numeric_time, unit='s')
            if predicted_date_utc < datetime.utcnow():
                return jsonify({"error": "Predicted 0kg date is in the past", "status": "unstable"})
            return jsonify({"predicted_0kg": predicted_date_utc.isoformat(), "status": "ok"})
        return jsonify({"error": "No 0kg prediction found", "status": "unstable"})
    except Exception as e:
        return jsonify({"error": str(e), "status": "error"})
    finally:
        try:
            if conn and conn.is_connected():
                conn.close()
        except:
            pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
