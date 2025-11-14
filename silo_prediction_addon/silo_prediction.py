#!/usr/bin/env python3
"""
Silo Prediction Home Assistant Add-on - Multi-Silo Support
Intelligens siló kiürülési előrejelzés lineáris regresszióval
"""

import os
import json
import time
import logging
import requests
import numpy as np
import pytz
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional
from scipy import stats

# Logging beállítása időbélyeggel
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('/app/logs/silo_prediction.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Timezone beállítása - Home Assistant timezone-ja
try:
    LOCAL_TZ = pytz.timezone('Europe/Budapest')
    logger.info(f"✅ Timezone beállítva: Europe/Budapest")
except Exception as e:
    LOCAL_TZ = pytz.UTC
    logger.warning(f"⚠️ Europe/Budapest timezone nem elérhető ({e}), UTC-t használunk")


class SiloPredictor:
    """Egy silo előrejelzési logikája"""

    def __init__(self, ha_url: str, ha_token: str, entity_id: str, sensor_name: str,
                 refill_threshold: int, max_capacity: int, prediction_days: int):
        self.ha_url = ha_url
        self.ha_token = ha_token
        self.entity_id = entity_id
        self.sensor_name = sensor_name
        self.refill_threshold = refill_threshold
        self.max_capacity = max_capacity
        self.prediction_days = prediction_days

        self.headers = {
            'Authorization': f'Bearer {self.ha_token}',
            'Content-Type': 'application/json'
        }

        logger.info(f"📦 Silo inicializálva: {self.sensor_name} ({self.entity_id})")

    def get_historical_data(self) -> List[Tuple[datetime, float]]:
        """Történeti adatok lekérése a Home Assistant API-ból"""
        # Lokális időben számolunk
        end_time = datetime.now(LOCAL_TZ)
        start_time = end_time - timedelta(days=self.prediction_days)

        logger.info(f"📊 [{self.sensor_name}] Adatok lekérése: {start_time.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%Y-%m-%d %H:%M')}")

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
                logger.warning(f"❌ [{self.sensor_name}] Nincs adat a válaszban")
                return []

            # Adatok feldolgozása - UTC-ből lokális időre konvertálás
            processed_data = []
            for entry in data[0]:
                try:
                    # HA UTC-ben küldi, konvertáljuk lokálisra
                    timestamp_utc = datetime.fromisoformat(entry['last_changed'].replace('Z', '+00:00'))
                    # Konvertálás lokális időzónára
                    timestamp = timestamp_utc.astimezone(LOCAL_TZ)

                    state = entry.get('state', '0')
                    if state in ['unknown', 'unavailable', 'null', None]:
                        continue

                    weight = float(state)
                    if 0 <= weight <= 50000:
                        processed_data.append((timestamp, weight))

                except (ValueError, KeyError, TypeError):
                    continue

            processed_data.sort(key=lambda x: x[0])

            logger.info(f"✅ [{self.sensor_name}] {len(processed_data)} adatpont betöltve")
            return processed_data

        except requests.RequestException as e:
            logger.error(f"❌ [{self.sensor_name}] API hiba: {e}")
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

        if hour_values and current_hour:
            avg_weight = np.mean(hour_values)
            hourly_data.append((current_hour, avg_weight))

        logger.info(f"📈 [{self.sensor_name}] {len(hourly_data)} óránkénti adatpont mintavételezve")
        return hourly_data

    def detect_refills(self, data: List[Tuple[datetime, float]]) -> List[Tuple[datetime, float]]:
        """Feltöltések detektálása és csak az utolsó feltöltés UTÁNI adatok megtartása"""
        if len(data) < 2:
            return data

        last_refill_index = -1

        for i in range(1, len(data)):
            prev_weight = data[i-1][1]
            curr_weight = data[i][1]
            weight_change = curr_weight - prev_weight

            if weight_change > 3000:
                logger.info(f"🔄 [{self.sensor_name}] Feltöltés detektálva: {data[i-1][0]} -> {data[i][0]}, "
                           f"Súlyváltozás: +{weight_change:.0f}kg")
                last_refill_index = i

        if last_refill_index >= 0:
            cleaned_data = data[last_refill_index:]
            logger.info(f"✅ [{self.sensor_name}] Utolsó feltöltés után: {len(cleaned_data)} adatpont ({data[last_refill_index][0]})")
        else:
            cleaned_data = data
            logger.info(f"✅ [{self.sensor_name}] Nem volt feltöltés, {len(cleaned_data)} adatpont használva")

        return cleaned_data

    def calculate_prediction(self, data: List[Tuple[datetime, float]]) -> Optional[Dict]:
        """Előrejelzés készítése lineáris regresszióval"""
        if len(data) < 24:
            logger.warning(f"❌ [{self.sensor_name}] Nincs elég adat az előrejelzéshez (minimum 24 óra kell, {len(data)} van)")
            return None

        timestamps = [t for t, w in data]
        weights = [w for t, w in data]

        start_time = timestamps[0]
        hours = [(t - start_time).total_seconds() / 3600 for t in timestamps]

        slope, intercept, r_value, p_value, std_err = stats.linregress(hours, weights)
        r_squared = r_value ** 2

        logger.info(f"📉 [{self.sensor_name}] Regresszió: meredekség={slope:.2f} kg/óra, R²={r_squared:.4f}")

        current_hours = hours[-1]
        current_weight = weights[-1]

        if abs(slope) < 0.01:
            logger.warning(f"⚠️ [{self.sensor_name}] Közel nulla meredekség, nincs trend")
            return {
                'prediction_date': None,
                'days_until_empty': None,
                'slope': slope,
                'r_squared': r_squared,
                'current_weight': current_weight,
                'status': 'no_trend'
            }

        if slope >= -0.1:
            logger.info(f"⚠️ [{self.sensor_name}] A siló nem ürül (pozitív vagy nulla trend)")
            return {
                'prediction_date': None,
                'days_until_empty': None,
                'slope': slope,
                'r_squared': r_squared,
                'current_weight': current_weight,
                'threshold': 0,
                'status': 'filling' if slope > 0 else 'stable'
            }

        hours_to_zero = -intercept / slope
        hours_from_now = hours_to_zero - current_hours

        if hours_from_now < 0:
            logger.warning(f"⚠️ [{self.sensor_name}] A számítás szerint már kiürült volna (hibás adat)")
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
            logger.info(f"⚠️ [{self.sensor_name}] Túl távoli előrejelzés: {days_until:.0f} nap")
            return {
                'prediction_date': None,
                'days_until_empty': None,
                'slope': slope,
                'r_squared': r_squared,
                'current_weight': current_weight,
                'threshold': 0,
                'status': 'too_far'
            }

        # Előrejelzés lokális időben
        prediction_datetime = datetime.now(LOCAL_TZ) + timedelta(hours=hours_from_now)

        formatted_date = prediction_datetime.strftime('%Y-%m-%d %H:%M')

        logger.info(f"📅 [{self.sensor_name}] 0 kg előrejelzés: {formatted_date}")
        logger.info(f"⏱️ [{self.sensor_name}] Hátralévő idő: {days_until:.1f} nap")

        return {
            'prediction_date': formatted_date,
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
            logger.warning(f"❌ [{self.sensor_name}] Nincs előrejelzési adat a szenzor frissítéshez")
            return

        self._update_date_sensor(prediction_data)
        self._update_time_remaining_sensor(prediction_data)
        self._update_last_updated_sensor()

    def _update_date_sensor(self, prediction_data: Dict):
        """Dátum szenzor frissítése (mikor lesz 0 kg)"""
        sensor_entity_id = f"sensor.{self.sensor_name.lower().replace(' ', '_')}"

        prediction_date = prediction_data.get('prediction_date')
        status = prediction_data.get('status', 'unknown')

        state = prediction_date if prediction_date else status

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

        self._post_sensor(sensor_entity_id, state, attributes)

    def _update_time_remaining_sensor(self, prediction_data: Dict):
        """Hátralévő idő szenzor frissítése (X nap Y óra formátum)"""
        time_sensor_entity_id = f"sensor.{self.sensor_name.lower().replace(' ', '_')}_time_remaining"

        days_until = prediction_data.get('days_until_empty')
        status = prediction_data.get('status', 'unknown')

        if days_until is not None and days_until >= 0:
            days = int(days_until)
            hours = int((days_until - days) * 24)

            if days > 0:
                state = f"{days} nap {hours} óra"
            else:
                state = f"{hours} óra"
        else:
            state = status

        attributes = {
            'days': int(days_until) if days_until is not None else None,
            'hours': int((days_until - int(days_until)) * 24) if days_until is not None else None,
            'total_hours': round(days_until * 24, 1) if days_until is not None else None,
            'status': status,
            'friendly_name': f"{self.sensor_name} - Hátralévő Idő",
            'icon': 'mdi:timer-sand'
        }

        self._post_sensor(time_sensor_entity_id, state, attributes)

    def _update_last_updated_sensor(self):
        """Utolsó frissítés időpontja szenzor"""
        last_updated_entity_id = f"sensor.{self.sensor_name.lower().replace(' ', '_')}_last_updated"

        # Aktuális idő lokális időzónában
        now = datetime.now(LOCAL_TZ)

        # Formázott időbélyeg
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')

        attributes = {
            'timestamp': timestamp,
            'friendly_name': f"{self.sensor_name} - Utolsó Frissítés",
            'icon': 'mdi:clock-check-outline'
        }

        self._post_sensor(last_updated_entity_id, timestamp, attributes)

    def _post_sensor(self, entity_id: str, state: str, attributes: Dict):
        """Közös metódus szenzor adatok POST-olásához"""
        url = f"{self.ha_url}/api/states/{entity_id}"
        payload = {
            'state': state,
            'attributes': attributes
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"✅ [{self.sensor_name}] Szenzor frissítve: {entity_id} = {state}")
        except requests.RequestException as e:
            logger.error(f"❌ [{self.sensor_name}] Szenzor frissítési hiba ({entity_id}): {e}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                logger.error(f"Válasz: {e.response.text}")

    def process(self):
        """Teljes feldolgozási folyamat egy silohoz"""
        try:
            raw_data = self.get_historical_data()

            if not raw_data:
                logger.warning(f"⚠️ [{self.sensor_name}] Nincs adat")
                return

            hourly_data = self.sample_hourly_data(raw_data)
            cleaned_data = self.detect_refills(hourly_data)
            prediction = self.calculate_prediction(cleaned_data)

            if prediction:
                self.update_sensor(prediction)

        except Exception as e:
            logger.error(f"❌ [{self.sensor_name}] Hiba a feldolgozás során: {e}", exc_info=True)


class MultiSiloManager:
    """Multi-silo manager - kezeli az összes silót"""

    def __init__(self):
        self.ha_url = os.getenv('HA_URL', 'http://supervisor/core')
        self.ha_token = os.getenv('HA_TOKEN', os.getenv('SUPERVISOR_TOKEN'))
        self.prediction_days = int(os.getenv('PREDICTION_DAYS', '10'))
        self.update_interval = int(os.getenv('UPDATE_INTERVAL', '3600'))

        logger.info("🚀 Multi-Silo Prediction Add-on indítva")
        logger.info(f"Home Assistant URL: {self.ha_url}")

        if not self.ha_token:
            logger.error("❌ SUPERVISOR_TOKEN vagy HA_TOKEN nincs beállítva!")
        else:
            logger.info(f"✅ Token hossza: {len(self.ha_token)} karakter")

        # Siló konfiguráció betöltése
        self.silos = self._load_silo_config()
        logger.info(f"📦 {len(self.silos)} silo konfigurálva")

    def _load_silo_config(self) -> List[SiloPredictor]:
        """Siló konfiguráció betöltése JSON-ból"""
        silos_json = os.getenv('SILOS_CONFIG', '[]')

        try:
            silos_config = json.loads(silos_json)
        except json.JSONDecodeError as e:
            logger.error(f"❌ Hibás JSON konfiguráció: {e}")
            return []

        silos = []
        for silo_cfg in silos_config:
            try:
                silo = SiloPredictor(
                    ha_url=self.ha_url,
                    ha_token=self.ha_token,
                    entity_id=silo_cfg['entity_id'],
                    sensor_name=silo_cfg['sensor_name'],
                    refill_threshold=silo_cfg.get('refill_threshold', 1000),
                    max_capacity=silo_cfg.get('max_capacity', 20000),
                    prediction_days=self.prediction_days
                )
                silos.append(silo)
            except KeyError as e:
                logger.error(f"❌ Hiányzó mező a silo konfigurációban: {e}")

        return silos

    def run(self):
        """Fő futási ciklus - periodikusan feldolgozza az összes silót"""
        logger.info("🔄 Multi-Silo Prediction szolgáltatás indítva")

        while True:
            try:
                logger.info("=" * 60)
                logger.info(f"🔄 Új feldolgozási ciklus kezdődik ({len(self.silos)} silo)")

                for silo in self.silos:
                    silo.process()

                logger.info(f"✅ Feldolgozási ciklus befejezve")
                logger.info(f"⏰ Következő frissítés {self.update_interval} másodperc múlva...")
                time.sleep(self.update_interval)

            except Exception as e:
                logger.error(f"❌ Hiba a futás során: {e}", exc_info=True)
                time.sleep(60)


if __name__ == '__main__':
    manager = MultiSiloManager()
    manager.run()
