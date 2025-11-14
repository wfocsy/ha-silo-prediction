#!/usr/bin/env python3
"""
Silo Prediction Home Assistant Add-on
Intelligens siló kiürülési előrejelzés lineáris regresszióval
"""

import os
import time
import logging
import requests
import numpy as np
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional
from scipy import stats

# Logging beállítása
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/silo_prediction.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SiloPredictionAddon:
    def __init__(self):
        self.ha_url = os.getenv('HA_URL', 'http://supervisor/core')
        self.ha_token = os.getenv('HA_TOKEN', os.getenv('SUPERVISOR_TOKEN'))
        self.entity_id = os.getenv('ENTITY_ID', 'sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly')
        self.sensor_name = os.getenv('SENSOR_NAME', 'Silo Prediction')
        self.refill_threshold = int(os.getenv('REFILL_THRESHOLD', '1000'))
        self.max_capacity = int(os.getenv('MAX_CAPACITY', '20000'))
        self.prediction_days = int(os.getenv('PREDICTION_DAYS', '10'))
        self.update_interval = int(os.getenv('UPDATE_INTERVAL', '3600'))

        self.headers = {
            'Authorization': f'Bearer {self.ha_token}',
            'Content-Type': 'application/json'
        }

        logger.info("🚀 Silo Prediction Add-on indítva")
        logger.info(f"Home Assistant URL: {self.ha_url}")
        logger.info(f"Entity ID: {self.entity_id}")

        # Debug: Check if token is available
        if not self.ha_token:
            logger.error("❌ SUPERVISOR_TOKEN vagy HA_TOKEN nincs beállítva!")
        else:
            logger.info(f"✅ Token hossza: {len(self.ha_token)} karakter")

    def get_historical_data(self, days: int = 10) -> List[Tuple[datetime, float]]:
        """Történeti adatok lekérése a Home Assistant API-ból"""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        logger.info(f"📊 Adatok lekérése: {start_time} - {end_time}")

        url = f"{self.ha_url}/api/history/period/{start_time.isoformat()}"
        params = {
            'filter_entity_id': self.entity_id,
            'end_time': end_time.isoformat()
        }

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            if not data or not data[0]:
                logger.warning("❌ Nincs adat a válaszban")
                return []

            # Adatok feldolgozása
            processed_data = []
            for entry in data[0]:
                try:
                    timestamp = datetime.fromisoformat(entry['last_changed'].replace('Z', '+00:00'))
                    timestamp = timestamp.replace(tzinfo=None)  # Eltávolítjuk a timezone info-t

                    state = entry.get('state', '0')
                    if state in ['unknown', 'unavailable', 'null', None]:
                        continue

                    weight = float(state)
                    if 0 <= weight <= 50000:  # Érvényes tartomány
                        processed_data.append((timestamp, weight))

                except (ValueError, KeyError, TypeError) as e:
                    continue

            # Időrend szerint rendezés
            processed_data.sort(key=lambda x: x[0])

            logger.info(f"✅ {len(processed_data)} adatpont betöltve")
            return processed_data

        except requests.RequestException as e:
            logger.error(f"❌ API hiba: {e}")
            return []

    def sample_hourly_data(self, data: List[Tuple[datetime, float]]) -> List[Tuple[datetime, float]]:
        """Óránkénti mintavételezés az adatokból"""
        if not data:
            return []

        hourly_data = []
        current_hour = None
        hour_values = []

        for timestamp, weight in data:
            hour = timestamp.replace(minute=0, second=0, microsecond=0)

            if current_hour is None:
                current_hour = hour

            if hour == current_hour:
                hour_values.append(weight)
            else:
                if hour_values:
                    avg_weight = np.mean(hour_values)
                    hourly_data.append((current_hour, avg_weight))
                current_hour = hour
                hour_values = [weight]

        # Utolsó óra
        if hour_values and current_hour:
            avg_weight = np.mean(hour_values)
            hourly_data.append((current_hour, avg_weight))

        logger.info(f"📈 {len(hourly_data)} óránkénti adatpont mintavételezve")
        return hourly_data

    def detect_refills(self, data: List[Tuple[datetime, float]]) -> List[Tuple[datetime, float]]:
        """
        Feltöltések detektálása és csak az utolsó feltöltés UTÁNI adatok megtartása.
        Ez azért fontos, mert csak az utolsó feltöltés után tudjuk pontosan előrejelezni az ürülést.
        """
        if len(data) < 2:
            return data

        last_refill_index = -1

        # Keressük meg az utolsó feltöltés indexét
        for i in range(1, len(data)):
            prev_weight = data[i-1][1]
            curr_weight = data[i][1]
            weight_change = curr_weight - prev_weight

            # Ha a súly 3000kg-nál többel nőtt, az feltöltés
            # (Óránkénti átlagolás után is detektálható legyen)
            if weight_change > 3000:
                logger.info(f"🔄 Feltöltés detektálva: {data[i-1][0]} -> {data[i][0]}, "
                           f"Súlyváltozás: +{weight_change:.0f}kg")
                last_refill_index = i

        # Ha volt feltöltés, csak az utolsó feltöltés utáni adatokat tartjuk meg
        if last_refill_index >= 0:
            cleaned_data = data[last_refill_index:]
            logger.info(f"✅ Utolsó feltöltés után: {len(cleaned_data)} adatpont ({data[last_refill_index][0]})")
        else:
            cleaned_data = data
            logger.info(f"✅ Nem volt feltöltés, {len(cleaned_data)} adatpont használva")

        return cleaned_data

    def calculate_prediction(self, data: List[Tuple[datetime, float]]) -> Optional[Dict]:
        """Előrejelzés készítése lineáris regresszióval"""
        if len(data) < 24:
            logger.warning(f"❌ Nincs elég adat az előrejelzéshez (minimum 24 óra kell, {len(data)} van)")
            return None

        # Időpontok és súlyok szétválasztása
        timestamps = [t for t, w in data]
        weights = [w for t, w in data]

        # Unix timestamp-ekké konvertálás (órák)
        start_time = timestamps[0]
        hours = [(t - start_time).total_seconds() / 3600 for t in timestamps]

        # Lineáris regresszió
        slope, intercept, r_value, p_value, std_err = stats.linregress(hours, weights)

        r_squared = r_value ** 2

        logger.info(f"📉 Regresszió: meredekség={slope:.2f} kg/óra, R²={r_squared:.4f}")

        current_hours = hours[-1]
        current_weight = weights[-1]

        # Számítsuk ki, mikor lesz 0 kg (mindig, függetlenül a trenddől)
        # y = slope * x + intercept
        # 0 = slope * x + intercept
        # x = -intercept / slope

        if abs(slope) < 0.01:
            # Ha a meredekség közel nulla, nincs értelmes előrejelzés
            logger.warning("⚠️ Közel nulla meredekség, nincs trend")
            return {
                'prediction_date': None,
                'days_until_empty': None,
                'slope': slope,
                'r_squared': r_squared,
                'current_weight': current_weight,
                'status': 'no_trend'
            }

        # Ellenőrizzük a trend irányát
        if slope >= -0.1:
            # A siló nem ürül (töltődik vagy stabil)
            logger.info("⚠️ A siló nem ürül (pozitív vagy nulla trend)")
            return {
                'prediction_date': None,
                'days_until_empty': None,
                'slope': slope,
                'r_squared': r_squared,
                'current_weight': current_weight,
                'threshold': 0,
                'status': 'filling' if slope > 0 else 'stable'
            }

        # Negatív slope - a siló ürül
        # Hány óra múlva lesz 0 kg?
        hours_to_zero = -intercept / slope
        hours_from_now = hours_to_zero - current_hours

        # Ellenőrizzük, hogy értelmes-e az előrejelzés
        if hours_from_now < 0:
            logger.warning("⚠️ A számítás szerint már kiürült volna (hibás adat)")
            return {
                'prediction_date': None,
                'days_until_empty': None,
                'slope': slope,
                'r_squared': r_squared,
                'current_weight': current_weight,
                'threshold': 0,
                'status': 'error'
            }

        days_until = hours_from_now / 24

        if days_until > 365:
            logger.info(f"⚠️ Túl távoli előrejelzés: {days_until:.0f} nap")
            return {
                'prediction_date': None,
                'days_until_empty': None,
                'slope': slope,
                'r_squared': r_squared,
                'current_weight': current_weight,
                'threshold': 0,
                'status': 'too_far'
            }

        # Érvényes ürülési előrejelzés
        prediction_datetime = datetime.now() + timedelta(hours=hours_from_now)

        # Formázott dátum: YYYY-MM-DD HH:MM (másodperc nélkül)
        formatted_date = prediction_datetime.strftime('%Y-%m-%d %H:%M')

        logger.info(f"📅 0 kg előrejelzés: {formatted_date}")
        logger.info(f"⏱️ Hátralévő idő: {days_until:.1f} nap")

        return {
            'prediction_date': formatted_date,  # Formázott string, nem ISO
            'days_until_empty': round(days_until, 2),
            'slope': round(slope, 2),
            'r_squared': round(r_squared, 4),
            'current_weight': round(current_weight, 0),
            'threshold': 0,
            'status': 'emptying'
        }

    def update_sensor(self, prediction_data: Dict):
        """Home Assistant szenzor frissítése"""
        if not prediction_data:
            logger.warning("❌ Nincs előrejelzési adat a szenzor frissítéshez")
            return

        sensor_entity_id = f"sensor.{self.sensor_name.lower().replace(' ', '_')}"

        # A state értéke: ha van prediction_date, akkor azt használjuk (timestamp formátumban)
        # Különben a status értékét
        prediction_date = prediction_data.get('prediction_date')
        status = prediction_data.get('status', 'unknown')

        if prediction_date:
            # ISO formátumú dátumot használunk state-ként
            state = prediction_date
        else:
            # Ha nincs dátum, a status-t használjuk
            state = status

        attributes = {
            'prediction_date': prediction_date,
            'days_until_empty': prediction_data.get('days_until_empty'),
            'slope_kg_per_hour': prediction_data.get('slope'),
            'r_squared': prediction_data.get('r_squared'),
            'current_weight_kg': prediction_data.get('current_weight'),
            'threshold_kg': prediction_data.get('threshold'),
            'status': status,
            'friendly_name': self.sensor_name,
            'icon': 'mdi:silo'
        }

        url = f"{self.ha_url}/api/states/{sensor_entity_id}"
        payload = {
            'state': state,
            'attributes': attributes
        }

        try:
            logger.debug(f"Szenzor frissítés URL: {url}")
            logger.debug(f"Payload: {payload}")
            response = requests.post(url, headers=self.headers, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"✅ Szenzor frissítve: {sensor_entity_id} = {state} nap")
        except requests.RequestException as e:
            logger.error(f"❌ Szenzor frissítési hiba: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Válasz: {e.response.text}")

    def run(self):
        """Fő futási ciklus"""
        logger.info("🔄 Prediction szolgáltatás indítva")

        while True:
            try:
                # 1. Adatok lekérése
                raw_data = self.get_historical_data(days=self.prediction_days)

                if not raw_data:
                    logger.warning("⚠️ Nincs adat, várakozás...")
                    time.sleep(self.update_interval)
                    continue

                # 2. Óránkénti mintavételezés
                hourly_data = self.sample_hourly_data(raw_data)

                # 3. Feltöltések eltávolítása
                cleaned_data = self.detect_refills(hourly_data)

                # 4. Előrejelzés
                prediction = self.calculate_prediction(cleaned_data)

                # 5. Szenzor frissítése
                if prediction:
                    self.update_sensor(prediction)

                logger.info(f"⏰ Következő frissítés {self.update_interval} másodperc múlva...")
                time.sleep(self.update_interval)

            except Exception as e:
                logger.error(f"❌ Hiba a futás során: {e}", exc_info=True)
                time.sleep(60)  # Hiba esetén 1 perc várakozás

if __name__ == '__main__':
    addon = SiloPredictionAddon()
    addon.run()
