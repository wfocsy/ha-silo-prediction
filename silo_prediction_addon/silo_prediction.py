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
                 refill_threshold: int, max_capacity: int, prediction_days: int,
                 enable_growth_correction: bool = False, animal_age_days: float = 25.0,
                 growth_rate_kg_per_hour_per_day: float = 0.000201):
        self.ha_url = ha_url
        self.ha_token = ha_token
        self.entity_id = entity_id
        self.sensor_name = sensor_name
        self.refill_threshold = refill_threshold
        self.max_capacity = max_capacity
        self.prediction_days = prediction_days

        # Növekedési korrekció paraméterek
        self.enable_growth_correction = enable_growth_correction
        self.animal_age_days = animal_age_days
        self.growth_rate_kg_per_hour_per_day = growth_rate_kg_per_hour_per_day

        # Előző ciklus slope tárolása (betöltés HA szenzorból)
        self.previous_slope = None
        self.previous_r_squared = None

        self.headers = {
            'Authorization': f'Bearer {self.ha_token}',
            'Content-Type': 'application/json'
        }

        logger.info(f"📦 Silo inicializálva: {self.sensor_name} ({self.entity_id})")
        if self.enable_growth_correction:
            logger.info(f"🌱 Növekedési korrekció ENGEDÉLYEZVE: állat életkor={self.animal_age_days} nap, "
                       f"növekedési ráta={self.growth_rate_kg_per_hour_per_day:.6f} kg/óra/nap")

        # Betöltjük az előző ciklus slope-ját (ha van)
        self._load_previous_slope()

    def _load_previous_slope(self):
        """Előző ciklus slope betöltése a HA szenzor attribútumaiból"""
        sensor_entity_id = f"sensor.{self.sensor_name.lower().replace(' ', '_')}"
        url = f"{self.ha_url}/api/states/{sensor_entity_id}"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                attributes = data.get('attributes', {})

                self.previous_slope = attributes.get('previous_slope_kg_per_hour')
                self.previous_r_squared = attributes.get('previous_r_squared')

                if self.previous_slope is not None:
                    logger.info(f"📥 [{self.sensor_name}] Előző ciklus slope betöltve: "
                               f"{self.previous_slope:.4f} kg/óra (R²={self.previous_r_squared:.4f})")
                else:
                    logger.info(f"ℹ️ [{self.sensor_name}] Nincs előző ciklus slope adat")
            else:
                logger.debug(f"ℹ️ [{self.sensor_name}] Szenzor még nem létezik, nincs előző slope")
        except Exception as e:
            logger.debug(f"ℹ️ [{self.sensor_name}] Előző slope betöltése nem sikerült: {e}")

    def _save_current_slope(self, slope: float, r_squared: float):
        """Jelenlegi slope mentése a következő ciklushoz"""
        self.previous_slope = slope
        self.previous_r_squared = r_squared
        logger.info(f"💾 [{self.sensor_name}] Slope mentve a következő ciklushoz: "
                   f"{slope:.4f} kg/óra (R²={r_squared:.4f})")

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
        """Előrejelzés készítése lineáris regresszióval (opcionális növekedési korrekcióval)"""

        # Ha kevés adat van, de van előző slope, használjuk azt
        use_previous_slope = False
        if len(data) < 24:
            if self.previous_slope is not None and len(data) >= 2:
                logger.info(f"⚠️ [{self.sensor_name}] Kevés adat ({len(data)} óra < 24 óra), "
                           f"előző ciklus slope-ját használom: {self.previous_slope:.4f} kg/óra")
                use_previous_slope = True
            else:
                logger.warning(f"❌ [{self.sensor_name}] Nincs elég adat az előrejelzéshez "
                             f"(minimum 24 óra vagy előző slope kell, {len(data)} van)")
                return None

        timestamps = [t for t, w in data]
        weights = [w for t, w in data]

        start_time = timestamps[0]
        hours = [(t - start_time).total_seconds() / 3600 for t in timestamps]

        # Slope meghatározása
        if use_previous_slope:
            # Használjuk az előző ciklus slope-ját
            slope = self.previous_slope
            r_squared = self.previous_r_squared if self.previous_r_squared else 0.95

            # Intercept becslése a jelenlegi adatokból
            # intercept = weight - slope * hours
            intercept = weights[-1] - slope * hours[-1]

            logger.info(f"📉 [{self.sensor_name}] Előző ciklus slope használata: meredekség={slope:.2f} kg/óra, R²={r_squared:.4f}")
        else:
            # Normál regresszió
            slope, intercept, r_value, p_value, std_err = stats.linregress(hours, weights)
            r_squared = r_value ** 2

            # Mentjük el a slope-ot a következő ciklushoz
            if r_squared > 0.7:  # Csak jó minőségű slope-ot mentünk
                self._save_current_slope(slope, r_squared)

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

        # Növekedési korrekció alkalmazása
        if self.enable_growth_correction:
            hours_from_now = self._calculate_with_growth_correction(
                current_weight, slope, current_hours, self.animal_age_days
            )
            logger.info(f"🌱 [{self.sensor_name}] Növekedési korrekció alkalmazva: {hours_from_now:.1f} óra")
        else:
            # Eredeti lineáris számítás
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

        # Formázott dátum időablakkal (±1 óra)
        formatted_date = self._format_prediction_with_window(prediction_datetime)

        logger.info(f"📅 [{self.sensor_name}] 0 kg előrejelzés: {formatted_date}")
        logger.info(f"⏱️ [{self.sensor_name}] Hátralévő idő: {days_until:.1f} nap")

        return {
            'prediction_date': formatted_date,
            'days_until_empty': round(days_until, 2),
            'slope': round(slope, 2),
            'r_squared': round(r_squared, 4),
            'current_weight': round(current_weight, 0),
            'threshold': 0,
            'status': 'emptying',
            'growth_correction_enabled': self.enable_growth_correction
        }

    def _format_prediction_with_window(self, prediction_datetime: datetime) -> str:
        """
        Formázza az előrejelzést időablakkal (±1 óra, kerekítve)

        Formátum:
        - Ma 16-18 óra között (~17:45)
        - Holnap 10-12 óra között (~11:30)
        - 2025-12-15 16-18 óra között (~17:20)

        Logika: prediction_datetime ± 1 óra, kerekítve egész órákra

        Args:
            prediction_datetime: Előrejelzett időpont

        Returns:
            Formázott string időablakkal és pontos idővel zárójelben
        """
        now = datetime.now(LOCAL_TZ)

        # ±1 óra ablak számítása
        window_start_dt = prediction_datetime - timedelta(hours=1)
        window_end_dt = prediction_datetime + timedelta(hours=1)

        # Kerekítés egész órákra
        # Ha perc < 30, lefelé kerekítünk, különben felfelé
        if window_start_dt.minute < 30:
            hour_start = window_start_dt.hour
        else:
            hour_start = (window_start_dt.hour + 1) % 24

        if window_end_dt.minute < 30:
            hour_end = window_end_dt.hour
        else:
            hour_end = (window_end_dt.hour + 1) % 24

        # Dátum különbség napokban
        days_diff = (prediction_datetime.date() - now.date()).days

        # Relatív dátum formázás
        if days_diff == 0:
            date_str = "Ma"
        elif days_diff == 1:
            date_str = "Holnap"
        elif days_diff == 2:
            date_str = "Holnapután"
        else:
            date_str = prediction_datetime.strftime('%Y-%m-%d')

        # Pontos idő zárójelben
        exact_time = prediction_datetime.strftime('%H:%M')

        # Időablak formázás
        if hour_end > hour_start or (hour_end == 0 and hour_start == 22):  # Éjféli átlépés: 22-00
            time_window = f"{hour_start:02d}-{hour_end:02d} óra között (~{exact_time})"
        else:
            # Normál éjféli átlépés
            time_window = f"{hour_start:02d}-{hour_end:02d} óra között (~{exact_time}, éjféli átlépés)"

        return f"{date_str} {time_window}"

    def _calculate_with_growth_correction(self, current_weight: float, base_slope: float,
                                          current_hours: float, animal_age_days: float) -> float:
        """
        Növekedési korrekciós számítás - iteratív megoldás

        A növekvő takarmányfogyasztás miatt a siló gyorsabban ürül, mint amit a lineáris regresszió mutat.

        Args:
            current_weight: Jelenlegi súly (kg)
            base_slope: Lineáris regresszió meredeksége (kg/óra) - NEGATÍV!
            current_hours: Eltelt órák száma a mérési kezdet óta
            animal_age_days: Állatok jelenlegi életkora napokban

        Returns:
            Hátralévő órák száma a 0 kg eléréséig
        """
        # Iteratív számítás - óránkénti szimulációval
        weight = current_weight
        hours_elapsed = 0
        max_iterations = 10000  # Maximum ~416 nap

        # Jelenlegi nap
        current_day = animal_age_days

        logger.info(f"🧮 [{self.sensor_name}] Növekedési szimulációs számítás indítása...")
        logger.info(f"   Kezdeti súly: {current_weight:.1f} kg")
        logger.info(f"   Alapmeredekség: {base_slope:.4f} kg/óra")
        logger.info(f"   Állat életkor: {animal_age_days:.1f} nap")

        while weight > 0 and hours_elapsed < max_iterations:
            # Aktuális nap (az állatokéhoz képest)
            day_in_cycle = current_day + (hours_elapsed / 24.0)

            # Óránkénti fogyás = alap fogyás + növekedési korrekció
            # Növekedési korrekció: napi kb. 0.201 g/óra/nap = 0.000201 kg/óra/nap
            growth_adjustment = self.growth_rate_kg_per_hour_per_day * day_in_cycle

            # Teljes óránkénti fogyás (negatív, ezért a growth_adjustment CSÖKKENTI)
            hourly_consumption = base_slope - growth_adjustment

            # Súly csökkentése
            weight += hourly_consumption  # hourly_consumption negatív, tehát csökkenti a súlyt

            hours_elapsed += 1

            # Debug log minden 100 óránként
            if hours_elapsed % 100 == 0:
                logger.debug(f"   {hours_elapsed}h: súly={weight:.1f} kg, "
                           f"napi_pozíció={day_in_cycle:.1f}, korrekció={growth_adjustment:.6f} kg/óra")

        if hours_elapsed >= max_iterations:
            logger.warning(f"⚠️ [{self.sensor_name}] Szimulációs limit elérve ({max_iterations} óra)")
            return max_iterations

        logger.info(f"✅ [{self.sensor_name}] Szimulációs eredmény: {hours_elapsed} óra ({hours_elapsed/24:.1f} nap)")

        return hours_elapsed

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
            'icon': 'mdi:silo',
            # Előző ciklus slope mentése a következő ciklushoz
            'previous_slope_kg_per_hour': self.previous_slope,
            'previous_r_squared': self.previous_r_squared,
            'growth_correction_enabled': prediction_data.get('growth_correction_enabled', False)
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
                    prediction_days=self.prediction_days,
                    # Növekedési korrekció paraméterek
                    enable_growth_correction=silo_cfg.get('enable_growth_correction', False),
                    animal_age_days=silo_cfg.get('animal_age_days', 25.0),
                    growth_rate_kg_per_hour_per_day=silo_cfg.get('growth_rate_kg_per_hour_per_day', 0.000201)
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
