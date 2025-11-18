#!/usr/bin/env python3
"""
Silo Prediction Home Assistant Add-on - Multi-Silo Support
Intelligens siló kiürülési előrejelzés technológiai fogyasztási adatok alapján
"""

import os
import json
import time
import logging
import requests
import numpy as np
import pytz
import csv
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


class TechnologicalFeedData:
    """
    Technológiai takarmány fogyasztási adatok kezelése
    CSV fájlból betöltés és interpoláció
    """

    def __init__(self, csv_path: str = '/app/tech_feed_data.csv'):
        self.csv_path = csv_path
        self.feed_data = {}  # {day: grams_per_day}
        self._load_csv()

    def _load_csv(self):
        """CSV fájl betöltése"""
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)  # Fejléc átugrása

                for row in reader:
                    if len(row) >= 2:
                        # " 10. nap" -> 10
                        day_str = row[0].strip().replace('.', '').replace('nap', '').strip()
                        # " 48 g" -> 48
                        intake_str = row[1].strip().replace('g', '').strip()

                        try:
                            day = int(day_str)
                            intake_g = int(intake_str)
                            self.feed_data[day] = intake_g
                        except ValueError:
                            continue

            logger.info(f"✅ Technológiai adatok betöltve: {len(self.feed_data)} nap ({min(self.feed_data.keys())}-{max(self.feed_data.keys())} nap)")

        except FileNotFoundError:
            logger.error(f"❌ Technológiai CSV nem található: {self.csv_path}")
            # Fallback: beégetett adatok
            self._load_fallback_data()
        except Exception as e:
            logger.error(f"❌ Hiba a CSV betöltése során: {e}")
            self._load_fallback_data()

    def _load_fallback_data(self):
        """Beégetett fallback adatok, ha a CSV nem elérhető"""
        logger.warning("⚠️ Fallback: beégetett technológiai adatok használata")
        self.feed_data = {
            0: 0, 1: 0, 2: 16, 3: 20, 4: 24, 5: 27, 6: 31, 7: 35, 8: 39, 9: 44,
            10: 48, 11: 52, 12: 57, 13: 62, 14: 67, 15: 72, 16: 77, 17: 83, 18: 88, 19: 94,
            20: 100, 21: 105, 22: 111, 23: 117, 24: 122, 25: 128, 26: 134, 27: 139, 28: 145, 29: 150,
            30: 156, 31: 161, 32: 166, 33: 171, 34: 176, 35: 180, 36: 185, 37: 189, 38: 193, 39: 197,
            40: 201, 41: 204, 42: 207, 43: 211, 44: 213, 45: 216, 46: 219, 47: 221, 48: 223, 49: 225,
            50: 227
        }

    def get_daily_intake_per_bird(self, day: int) -> float:
        """
        Egy madár várható napi takarmány felvétele

        Args:
            day: Nevelési nap (0-tól számítva)

        Returns:
            Takarmány felvétel grammban/nap (1 madár)
        """
        if day < 0:
            return 0.0

        # Ha túlléptük a táblázat végét, plató érték
        if day > max(self.feed_data.keys()):
            return float(self.feed_data[max(self.feed_data.keys())])

        # Pontos érték
        if day in self.feed_data:
            return float(self.feed_data[day])

        # Lineáris interpoláció két ismert pont között
        lower_day = max([d for d in self.feed_data.keys() if d < day], default=0)
        upper_day = min([d for d in self.feed_data.keys() if d > day], default=max(self.feed_data.keys()))

        if lower_day == upper_day:
            return float(self.feed_data[lower_day])

        # Lineáris interpoláció
        lower_intake = self.feed_data[lower_day]
        upper_intake = self.feed_data[upper_day]

        fraction = (day - lower_day) / (upper_day - lower_day)
        interpolated = lower_intake + fraction * (upper_intake - lower_intake)

        return interpolated


class SiloPredictor:
    """Egy silo előrejelzési logikája technológiai adatok alapján"""

    def __init__(self, ha_url: str, ha_token: str, entity_id: str, sensor_name: str,
                 refill_threshold: int, max_capacity: int, prediction_days: int = 45,
                 tech_csv_path: str = '/app/tech_feed_data.csv'):
        self.ha_url = ha_url
        self.ha_token = ha_token
        self.entity_id = entity_id
        self.sensor_name = sensor_name
        self.refill_threshold = refill_threshold
        self.max_capacity = max_capacity
        self.prediction_days = prediction_days  # 45 nap ajánlott

        # Technológiai fogyasztási adatok betöltése
        self.tech_data = TechnologicalFeedData(csv_path=tech_csv_path)

        # Ciklus adatok (betöltés HA szenzorból)
        self.cycle_start_date = None  # 0. nap dátuma
        self.bird_count = None  # Madár darabszám

        self.headers = {
            'Authorization': f'Bearer {self.ha_token}',
            'Content-Type': 'application/json'
        }

        logger.info(f"📦 Silo inicializálva: {self.sensor_name} ({self.entity_id})")
        logger.info(f"📊 Előrejelzési időablak: {self.prediction_days} nap")

        # Betöltjük a ciklus adatokat (ha vannak)
        self._load_cycle_data()

    def _load_cycle_data(self):
        """Ciklus adatok betöltése a HA szenzor attribútumaiból"""
        sensor_entity_id = f"sensor.{self.sensor_name.lower().replace(' ', '_')}"
        url = f"{self.ha_url}/api/states/{sensor_entity_id}"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                attributes = data.get('attributes', {})

                # Ciklus kezdete (0. nap)
                cycle_start_str = attributes.get('cycle_start_date')
                if cycle_start_str:
                    self.cycle_start_date = datetime.fromisoformat(cycle_start_str).replace(tzinfo=LOCAL_TZ)
                    logger.info(f"📥 [{self.sensor_name}] Ciklus kezdete betöltve: {self.cycle_start_date.strftime('%Y-%m-%d')}")

                # Madár darabszám
                self.bird_count = attributes.get('bird_count')
                if self.bird_count:
                    logger.info(f"📥 [{self.sensor_name}] Madár darabszám betöltve: {self.bird_count}")

            else:
                logger.debug(f"ℹ️ [{self.sensor_name}] Szenzor még nem létezik, nincs ciklus adat")
        except Exception as e:
            logger.debug(f"ℹ️ [{self.sensor_name}] Ciklus adatok betöltése nem sikerült: {e}")

    def _save_cycle_data(self, cycle_start_date: datetime, bird_count: int):
        """Ciklus adatok mentése (0. nap, madár darabszám)"""
        self.cycle_start_date = cycle_start_date
        self.bird_count = bird_count
        logger.info(f"💾 [{self.sensor_name}] Ciklus adatok mentve: "
                   f"kezdet={cycle_start_date.strftime('%Y-%m-%d')}, madarak={bird_count}")

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

    def sample_daily_data(self, data: List[Tuple[datetime, float]]) -> List[Tuple[datetime, float]]:
        """
        6 ÓRÁNKÉNTI mintavételezés (napi 4 adatpont) - 7:00-kor nap váltás

        Minden 6 órás periódusból (7:00, 13:00, 19:00, 1:00) egy átlagos súlyértéket készít.

        INDOKLÁS:
        A nevelési ciklus végén a fogyási ráta exponenciálisan növekszik:
        - 1-2. feltöltés: 7-9 nap
        - 2-3. feltöltés: 5 nap
        - 3-4. feltöltés: 4 nap
        - 4+. feltöltés: 2-3 nap

        Napi 1 adatpont későbbi fázisban pontatlan lenne!

        Args:
            data: Nyers adatok

        Returns:
            List of (timestamp, átlag_súly) - 6 óránként
        """
        if not data:
            return []

        # 6 órás időszakokra csoportosítás
        # Periódusok: 7:00-12:59, 13:00-18:59, 19:00-0:59, 1:00-6:59
        period_buckets = {}

        for timestamp, weight in data:
            # Nap kulcs (7:00-os nap váltással)
            if timestamp.hour < 7:
                day_key = timestamp.date() - timedelta(days=1)
            else:
                day_key = timestamp.date()

            # Periódus meghatározása (0-3: 7:00, 13:00, 19:00, 1:00)
            if 7 <= timestamp.hour < 13:
                period = 0  # 7:00-12:59
            elif 13 <= timestamp.hour < 19:
                period = 1  # 13:00-18:59
            elif 19 <= timestamp.hour < 24:
                period = 2  # 19:00-23:59
            else:  # 0 <= timestamp.hour < 7
                period = 3  # 0:00-6:59 (előző nap folytatása)

            period_key = (day_key, period)

            if period_key not in period_buckets:
                period_buckets[period_key] = []

            period_buckets[period_key].append(weight)

        # Periódus átlagok számítása
        sampled_data = []
        for (day_key, period) in sorted(period_buckets.keys()):
            weights = period_buckets[(day_key, period)]
            avg_weight = np.mean(weights)

            # Timestamp: a periódus kezdete
            if period == 0:
                period_timestamp = datetime.combine(day_key, datetime.min.time()).replace(hour=7, tzinfo=LOCAL_TZ)
            elif period == 1:
                period_timestamp = datetime.combine(day_key, datetime.min.time()).replace(hour=13, tzinfo=LOCAL_TZ)
            elif period == 2:
                period_timestamp = datetime.combine(day_key, datetime.min.time()).replace(hour=19, tzinfo=LOCAL_TZ)
            else:  # period == 3
                # 1:00 (következő nap 1:00-ja, de még az előző naphoz tartozik)
                period_timestamp = datetime.combine(day_key + timedelta(days=1), datetime.min.time()).replace(hour=1, tzinfo=LOCAL_TZ)

            sampled_data.append((period_timestamp, avg_weight))

        if sampled_data:
            logger.info(f"📈 [{self.sensor_name}] {len(sampled_data)} adatpont mintavételezve (6 óránként, napi 4 minta) "
                       f"({sampled_data[0][0].strftime('%Y-%m-%d %H:%M')} - {sampled_data[-1][0].strftime('%Y-%m-%d %H:%M')})")

        return sampled_data

    def detect_refills(self, data: List[Tuple[datetime, float]]) -> Tuple[List[Tuple[datetime, float]], Optional[datetime]]:
        """
        Feltöltések detektálása és csak az utolsó feltöltés UTÁNI adatok megtartása

        Returns:
            Tuple: (cleaned_data, last_refill_timestamp)
                   last_refill_timestamp: None ha nem volt feltöltés, különben az utolsó feltöltés időpontja
        """
        if len(data) < 2:
            return data, None

        last_refill_index = -1
        last_refill_timestamp = None

        for i in range(1, len(data)):
            prev_weight = data[i-1][1]
            curr_weight = data[i][1]
            weight_change = curr_weight - prev_weight

            if weight_change > 3000:
                logger.info(f"🔄 [{self.sensor_name}] Feltöltés detektálva: {data[i-1][0]} -> {data[i][0]}, "
                           f"Súlyváltozás: +{weight_change:.0f}kg")
                last_refill_index = i
                last_refill_timestamp = data[i][0]

        if last_refill_index >= 0:
            cleaned_data = data[last_refill_index:]
            logger.info(f"✅ [{self.sensor_name}] Utolsó feltöltés után: {len(cleaned_data)} adatpont ({data[last_refill_index][0]})")
        else:
            cleaned_data = data
            logger.info(f"✅ [{self.sensor_name}] Nem volt feltöltés, {len(cleaned_data)} adatpont használva")

        return cleaned_data, last_refill_timestamp

    def detect_cycle_start(self, data: List[Tuple[datetime, float]]) -> Optional[datetime]:
        """
        0. nap detektálása: INTELLIGENS első feltöltés detektálás + 100kg+ súlycsökkenés napja

        Logika (KÉTLÉPCSŐS):
        1. ELSŐDLEGES: Keresünk ~5 napos "csend" periódust (előző ciklus vége):
           - Siló súlya < 1000 kg
           - Nincs jelentős fogyasztás (< 50 kg/nap)
           - Ezt követő 3000kg+ ugrás = ELSŐ FELTÖLTÉS (új ciklus kezdete)
        2. FALLBACK: Ha nincs csend periódus, keresünk nagy (10000kg+) feltöltést
           - Ez valószínűleg ciklus kezdő feltöltés
        3. Utána keressük az első 100kg+ csökkenést egy nap alatt
        4. Ez lesz a 0. nap (állomány érkezése)

        Args:
            data: Mintavételezett adatok (6 óránként)

        Returns:
            0. nap dátuma vagy None
        """
        if len(data) < 7:  # Minimum 7 nap adat kell
            return None

        # 1. ELSŐDLEGES: Csend periódus + első feltöltés keresése
        first_refill_index = -1

        for i in range(5, len(data)):  # Legalább 5 nap múltbeli adat kell
            # Előző 5 nap vizsgálata (csend periódus?)
            silence_period = True
            for j in range(i - 5, i):
                weight = data[j][1]

                # Súly túl magas (> 1000 kg) → nem csend periódus
                if weight > 1000:
                    silence_period = False
                    break

                # Van fogyasztás (> 50 kg/nap)
                if j > 0:
                    daily_change = abs(data[j][1] - data[j-1][1])
                    if daily_change > 50:
                        silence_period = False
                        break

            # Ha csend periódus, és most jön egy 3000kg+ ugrás → ELSŐ FELTÖLTÉS
            if silence_period and i < len(data):
                weight_change = data[i][1] - data[i-1][1]

                if weight_change > 3000:
                    first_refill_index = i
                    logger.info(f"📍 [{self.sensor_name}] Csend periódus detektálva: "
                               f"{data[i-5][0].strftime('%Y-%m-%d')} - {data[i-1][0].strftime('%Y-%m-%d')} "
                               f"(súly < 1000 kg, nincs fogyasztás)")
                    logger.info(f"📍 [{self.sensor_name}] ELSŐ FELTÖLTÉS (csend után): {data[i][0].strftime('%Y-%m-%d')}, "
                               f"+{weight_change:.0f} kg → súly: {data[i][1]:.0f} kg")
                    break

        # 2. FALLBACK: Ha nincs csend periódus, keresünk nagy (5000kg+) feltöltést
        if first_refill_index < 0:
            logger.info(f"🔍 [{self.sensor_name}] Csend periódus nem található, alternatív módszer: nagy feltöltés keresése...")

            for i in range(1, len(data)):
                weight_change = data[i][1] - data[i-1][1]

                # Nagy feltöltés (5000kg+) = valószínűleg ciklus kezdő feltöltés
                # Csökkentve 10000-ről 5000-re, mert a purge_keep_days=10 miatt nincs elég adat a csend periódus detektáláshoz
                if weight_change > 5000:
                    first_refill_index = i
                    logger.info(f"📍 [{self.sensor_name}] NAGY FELTÖLTÉS detektálva (ciklus kezdet): {data[i][0].strftime('%Y-%m-%d')}, "
                               f"+{weight_change:.0f} kg → súly: {data[i][1]:.0f} kg")
                    break

        if first_refill_index < 0:
            logger.warning(f"⚠️ [{self.sensor_name}] Nem található ciklus kezdő feltöltés (sem csend után, sem nagy feltöltés)")
            return None

        # 3. Első feltöltés után keresés 100kg+ napi csökkenésre
        for i in range(first_refill_index + 1, len(data)):
            prev_day_weight = data[i - 1][1]
            current_weight = data[i][1]
            daily_consumption = prev_day_weight - current_weight

            if daily_consumption > 100:  # 100kg+ fogyasztás egy nap alatt
                cycle_start = data[i][0]
                logger.info(f"🐣 [{self.sensor_name}] 0. NAP DETEKTÁLVA: {cycle_start.strftime('%Y-%m-%d')}, "
                           f"napi fogyasztás: {daily_consumption:.0f} kg")
                return cycle_start

        logger.warning(f"⚠️ [{self.sensor_name}] 0. nap nem található (nincs 100kg+ napi fogyasztás feltöltés után)")
        return None

    def create_continuous_curve(self, data: List[Tuple[datetime, float]],
                                cycle_start: datetime) -> List[Tuple[datetime, float, int, float]]:
        """
        Folyamatos fogyási görbe készítése feltöltések kiszűrésével

        A feltöltések értékét "kivonjuk", mintha folyamatos lenne a görbe.
        Minden adatponthoz hozzárendeljük a nevelési napot (0-tól) és pontos időt (napokban).

        Args:
            data: Mintavételezett adatok (6 óránként)
            cycle_start: 0. nap időpontja

        Returns:
            List of (timestamp, normalized_weight, day_in_cycle, exact_day_float)
        """
        if not data or not cycle_start:
            return []

        continuous_data = []
        cumulative_refill_offset = 0  # Összes feltöltés súlya (amit le kell vonni)

        for i, (timestamp, weight) in enumerate(data):
            # Feltöltés detektálás
            if i > 0:
                prev_weight = data[i-1][1]
                weight_change = weight - prev_weight

                if weight_change > 3000:  # Feltöltés
                    refill_amount = weight_change
                    cumulative_refill_offset += refill_amount
                    logger.info(f"🔄 [{self.sensor_name}] Feltöltés normalizálás: {timestamp.strftime('%Y-%m-%d %H:%M')}, "
                               f"+{refill_amount:.0f} kg (kumulatív offset: {cumulative_refill_offset:.0f} kg)")

            # Normalizált súly: mintha nem lettek volna feltöltések
            normalized_weight = weight - cumulative_refill_offset

            # Nevelési nap számítása (0-tól) - NAP VÁLTÁS 7:00-KOR!
            # Ha 7:00 előtt vagyunk, az előző naphoz tartozik
            adjusted_timestamp = timestamp
            if timestamp.hour < 7:
                # 0:00-6:59 → előző nap része
                adjusted_timestamp = timestamp - timedelta(hours=timestamp.hour + 17)  # Visszamegyünk az előző nap 7:00-jához

            days_since_start = (adjusted_timestamp - cycle_start).total_seconds() / 86400
            day_in_cycle = int(days_since_start)
            exact_day = days_since_start  # Pontos nap tört értékkel (pl. 5.25 = 5. nap délután)

            # Csak a cycle_start utáni adatokat tartjuk meg
            if days_since_start >= 0:
                continuous_data.append((timestamp, normalized_weight, day_in_cycle, exact_day))

        logger.info(f"✅ [{self.sensor_name}] Folyamatos görbe: {len(continuous_data)} adatpont (6 óránként), "
                   f"{continuous_data[0][2]}-{continuous_data[-1][2]} nap között")

        return continuous_data

    def calculate_daily_bird_count(self, continuous_data: List[Tuple[datetime, float, int, float]]) -> Dict[int, int]:
        """
        Madár darabszám kalkuláció naponta - 6 ÓRÁNKÉNTI MINTÁK ALAPJÁN

        FONTOS LOGIKA:
        - NAPI összesített fogyasztást számolunk (4x6óra = 24óra)
        - Csak a 7:00-as adatpontokat használjuk összehasonlításra
        - Mai 7:00 súly - Tegnapi 7:00 súly = TEGNAPI fogyasztás
        - Tegnapi tech adatot használjuk (mert az a nap fogyott)

        Args:
            continuous_data: [(timestamp, normalized_weight, day_in_cycle, exact_day), ...]
                             6 óránkénti adatok

        Returns:
            {day: bird_count}
        """
        if not continuous_data or len(continuous_data) < 8:  # Minimum 2 nap x 4 adatpont kell
            return {}

        bird_counts = {}

        # Csak 7:00-as adatpontokat szűrjük ki
        daily_7am_data = [(ts, w, day, exact) for ts, w, day, exact in continuous_data if ts.hour == 7]

        if len(daily_7am_data) < 2:
            logger.warning(f"⚠️ [{self.sensor_name}] Nincs elég 7:00-as adatpont a madár számhoz ({len(daily_7am_data)})")
            return {}

        # Minden napra: előző 7:00 - jelenlegi 7:00 = ELŐZŐ NAP fogyasztása
        for i in range(1, len(daily_7am_data)):
            prev_timestamp, prev_weight, prev_day, _ = daily_7am_data[i-1]
            curr_timestamp, curr_weight, curr_day, _ = daily_7am_data[i]

            # Napi fogyasztás (ez az ELŐZŐ NAP fogyasztása!)
            daily_consumption_kg = prev_weight - curr_weight

            if daily_consumption_kg < 0:  # Negatív fogyasztás (hibás adat vagy feltöltés maradt)
                logger.debug(f"⚠️ [{self.sensor_name}] {prev_day}. nap: negatív fogyasztás ({daily_consumption_kg:.1f} kg), kihagyva")
                continue

            if daily_consumption_kg < 10:  # Túl kicsi fogyasztás (< 10 kg/nap)
                logger.debug(f"⚠️ [{self.sensor_name}] {prev_day}. nap: túl kicsi fogyasztás ({daily_consumption_kg:.1f} kg), kihagyva")
                continue

            # FONTOS: ELŐZŐ NAP tech adatát használjuk (mert az a nap fogyott!)
            expected_per_bird_g = self.tech_data.get_daily_intake_per_bird(prev_day)

            if expected_per_bird_g <= 0:
                logger.debug(f"⚠️ [{self.sensor_name}] {prev_day}. nap: nincs tech adat (0 g/madár)")
                continue

            # Madár darabszám kalkuláció
            actual_consumption_g = daily_consumption_kg * 1000
            bird_count = int(actual_consumption_g / expected_per_bird_g)

            # ELŐZŐ NAPHOZ rendeljük!
            bird_counts[prev_day] = bird_count

            logger.debug(f"📊 [{self.sensor_name}] {prev_day}. nap: {daily_consumption_kg:.1f} kg fogyasztás, "
                        f"{expected_per_bird_g:.1f} g/madár → {bird_count} madár")

        if bird_counts:
            avg_birds = int(np.mean(list(bird_counts.values())))
            logger.info(f"🐔 [{self.sensor_name}] Madár darabszám: {min(bird_counts.values())}-{max(bird_counts.values())} "
                       f"(átlag: {avg_birds})")

        return bird_counts

    def calculate_correction_factor(self, continuous_data: List[Tuple[datetime, float, int, float]],
                                    bird_counts: Dict[int, int]) -> float:
        """
        Korrekciós szorzó számítása: valós fogyás vs. technológiai fogyás aránya

        Ez megmutatja, hogy a valóságban hány %-kal fogy több/kevesebb takarmány,
        mint amit a technológiai adatok alapján várnánk.

        Args:
            continuous_data: Normalizált adatok (6 óránként)
            bird_counts: Napi madár darabszámok

        Returns:
            correction_factor:
                - 1.00 = pontos egyezés (100%)
                - 1.05 = 5%-kal TÖBB fogy a valóságban
                - 0.95 = 5%-kal KEVESEBB fogy a valóságban
        """
        if not continuous_data or not bird_counts or len(continuous_data) < 2:
            return 1.0  # Alapértelmezett: nincs korrekció

        total_actual_consumption = 0.0
        total_expected_consumption = 0.0

        # Csak 7:00-as adatpontokat használunk napi összehasonlításhoz
        daily_7am_data = [(ts, w, day, exact) for ts, w, day, exact in continuous_data if ts.hour == 7]

        # Végigmegyünk minden napon, ahol van bird_count
        for i in range(1, len(daily_7am_data)):
            prev_timestamp, prev_weight, prev_day, _ = daily_7am_data[i-1]
            curr_timestamp, curr_weight, curr_day, _ = daily_7am_data[i]

            # Csak azokat a napokat nézzük, ahol van madár szám
            if prev_day not in bird_counts:
                continue

            # Valós fogyasztás (mért)
            actual_consumption_kg = prev_weight - curr_weight

            if actual_consumption_kg < 0:  # Hibás adat
                continue

            # Várható fogyasztás (tech adat)
            bird_count = bird_counts[prev_day]
            expected_per_bird_g = self.tech_data.get_daily_intake_per_bird(prev_day)

            if expected_per_bird_g <= 0:
                continue

            expected_consumption_kg = (expected_per_bird_g * bird_count) / 1000.0

            # Hozzáadjuk az összegekhez
            total_actual_consumption += actual_consumption_kg
            total_expected_consumption += expected_consumption_kg

        # Korrekciós szorzó számítása
        if total_expected_consumption > 0:
            correction_factor = total_actual_consumption / total_expected_consumption
        else:
            correction_factor = 1.0  # Alapértelmezett

        logger.info(f"📐 [{self.sensor_name}] Korrekciós szorzó: {correction_factor:.3f} "
                   f"(valós: {total_actual_consumption:.0f} kg, várható: {total_expected_consumption:.0f} kg)")

        return correction_factor

    def calculate_prediction_with_tech_data(self, continuous_data: List[Tuple[datetime, float, int, float]],
                                           bird_counts: Dict[int, int],
                                           current_real_weight: float) -> Optional[Dict]:
        """
        Előrejelzés készítése technológiai adatok alapján

        FONTOS: A normalizált görbe csak a madár darabszám és korrekciós szorzó számításához
        használatos! Az előrejelzés a JELENLEGI VALÓS SÚLYBÓL indul!

        Args:
            continuous_data: Normalizált adatok (timestamp, weight, day, exact_day) - CSAK analízishez! (6 óránként)
            bird_counts: Napi madár darabszámok
            current_real_weight: VALÓS jelenlegi súly (nem normalizált!)

        Returns:
            Prediction dictionary vagy None
        """
        if not continuous_data or not bird_counts:
            logger.warning(f"❌ [{self.sensor_name}] Nincs elég adat az előrejelzéshez")
            return None

        # Aktuális állapot (VALÓS súllyal!)
        current_timestamp, _, current_day, _ = continuous_data[-1]

        if current_real_weight <= 0:
            logger.info(f"⚠️ [{self.sensor_name}] A siló már üres (0 kg)")
            return {
                'prediction_date': None,
                'days_until_empty': 0,
                'current_weight': 0,
                'bird_count': bird_counts.get(current_day, 0),
                'day_in_cycle': current_day,
                'status': 'empty'
            }

        # Átlagos madár darabszám (utolsó 7 nap vagy összes)
        recent_days = [d for d in bird_counts.keys() if d >= current_day - 7]
        if recent_days:
            avg_bird_count = int(np.mean([bird_counts[d] for d in recent_days]))
        else:
            avg_bird_count = int(np.mean(list(bird_counts.values())))

        logger.info(f"🐔 [{self.sensor_name}] Átlagos madár darabszám (előrejelzéshez): {avg_bird_count}")

        # Korrekciós szorzó számítása (valós vs. tech fogyás)
        correction_factor = self.calculate_correction_factor(continuous_data, bird_counts)

        # Iteratív szimuláció: VALÓS jelenlegi súlyból indulunk!
        weight = current_real_weight
        day = current_day
        hours_elapsed = 0
        max_days = 100  # Maximum 100 nap előrejelzés

        logger.info(f"🎯 [{self.sensor_name}] Előrejelzés indítása: "
                   f"valós súly={weight:.0f} kg, {day}. nap")

        while weight > 0 and day < current_day + max_days:
            # Várható napi fogyasztás (1 madár, tech adat)
            expected_per_bird_g = self.tech_data.get_daily_intake_per_bird(day)

            # Teljes állomány napi fogyasztása (tech szerint)
            total_daily_kg = (expected_per_bird_g * avg_bird_count) / 1000.0

            # KORREKCIÓ: valós vs. tech arány alapján
            corrected_daily_kg = total_daily_kg * correction_factor

            # Óránkénti fogyasztás (korrigált)
            hourly_kg = corrected_daily_kg / 24.0

            # Súly csökkentése (1 óra)
            weight -= hourly_kg
            hours_elapsed += 1

            # Nap váltás minden 24 órában
            if hours_elapsed % 24 == 0:
                day += 1

            # Debug log minden 7 napban
            if hours_elapsed % (24 * 7) == 0:
                logger.debug(f"   {hours_elapsed}h ({day}. nap): súly={weight:.0f} kg, "
                           f"tech={total_daily_kg:.1f} kg/nap, korrigált={corrected_daily_kg:.1f} kg/nap")

        prediction_datetime = datetime.now(LOCAL_TZ) + timedelta(hours=hours_elapsed)
        days_until = hours_elapsed / 24.0

        # Formázott dátum időablakkal
        formatted_date, window_midpoint_hours = self._format_prediction_with_window(prediction_datetime)
        days_until_midpoint = window_midpoint_hours / 24.0

        logger.info(f"📅 [{self.sensor_name}] 0 kg előrejelzés: {formatted_date}")
        logger.info(f"⏱️ [{self.sensor_name}] Hátralévő idő: {days_until_midpoint:.1f} nap")

        return {
            'prediction_date': formatted_date,
            'days_until_empty': round(days_until_midpoint, 2),
            'current_weight': round(current_real_weight, 0),
            'bird_count': avg_bird_count,
            'day_in_cycle': current_day,
            'correction_factor': round(correction_factor, 3),
            'status': 'emptying',
            'tech_data_used': True
        }

    def resample_5min(self, start_time: datetime, end_time: datetime) -> List[Tuple[datetime, float]]:
        """
        5 perces mintavételezés CSAK feltöltés detektáláshoz

        NEM használjuk predikciós görbéhez!

        Args:
            start_time: Kezdő időpont
            end_time: Vég időpont

        Returns:
            [(timestamp, weight), ...] 5 percenként
        """
        url = f"{self.ha_url}/api/history/period/{start_time.isoformat()}"
        params = {
            'filter_entity_id': self.entity_id,
            'end_time': end_time.isoformat()
        }

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            history = response.json()
        except Exception as e:
            logger.error(f"❌ [{self.sensor_name}] 5min resample API hiba: {e}")
            return []

        if not history or len(history) == 0:
            return []

        # Összes adat
        all_data = []
        for record in history[0]:
            try:
                state = record.get('state')
                if state in ['unavailable', 'unknown', 'None', None, '']:
                    continue

                weight = float(state)
                last_changed = record.get('last_changed')
                timestamp = datetime.fromisoformat(last_changed.replace('Z', '+00:00'))
                all_data.append((timestamp, weight))
            except (ValueError, TypeError, AttributeError):
                continue

        if not all_data:
            return []

        # 5 perces mintavételezés
        all_data.sort(key=lambda x: x[0])
        timestamps = np.array([t for t, _ in all_data])
        weights = np.array([w for _, w in all_data])

        resampled = []
        current = start_time.replace(second=0, microsecond=0)
        current = current.replace(minute=(current.minute // 5) * 5)  # 5 perces kerekítés

        while current <= end_time:
            window_start = current - timedelta(minutes=2.5)
            window_end = current + timedelta(minutes=2.5)

            mask = (timestamps >= window_start) & (timestamps <= window_end)
            if np.any(mask):
                avg_weight = np.mean(weights[mask])
                resampled.append((current, avg_weight))

            current += timedelta(minutes=5)

        return resampled

    def detect_refill_completion(self, data_5min: List[Tuple[datetime, float]]) -> Tuple[bool, Optional[datetime]]:
        """
        Feltöltés befejezés detektálás

        Ha 10 percig (2x5 perc) nincs 100kg+ emelkedés → vége

        Args:
            data_5min: 5 perces mintavételezett adatok

        Returns:
            (refill_in_progress, refill_end_time)
        """
        if len(data_5min) < 3:
            return False, None

        # Utolsó 30 perc adatai (6x5 perc)
        recent = data_5min[-6:]

        # Keressük az utolsó jelentős emelkedést (100kg+)
        last_increase_idx = -1
        for i in range(1, len(recent)):
            weight_change = recent[i][1] - recent[i-1][1]
            if weight_change > 100:  # 100kg+ emelkedés
                last_increase_idx = i

        # Ha nincs emelkedés az utolsó 30 percben → nincs feltöltés
        if last_increase_idx == -1:
            return False, None

        # Ha az utolsó emelkedés 10+ perce volt → feltöltés vége
        time_since_last = len(recent) - 1 - last_increase_idx
        if time_since_last >= 2:  # 2x5 perc = 10 perc
            refill_end_time = recent[last_increase_idx][0]
            return False, refill_end_time

        # Feltöltés folyamatban
        return True, None

    def check_active_refill(self) -> Tuple[bool, Optional[datetime], Optional[float]]:
        """
        Ellenőrzi, hogy most folyik-e aktív feltöltés (5 perces mintavételezéssel)

        Returns:
            (is_refilling, refill_end_time, current_weight)
        """
        now = datetime.now(LOCAL_TZ)
        start_time = now - timedelta(minutes=30)  # Utolsó 30 perc

        # 5 perces mintavételezés
        data_5min = self.resample_5min(start_time, now)

        if not data_5min:
            return False, None, None

        current_weight = data_5min[-1][1]

        # Feltöltés detektálás
        is_refilling, refill_end = self.detect_refill_completion(data_5min)

        if is_refilling:
            logger.info(f"🔄 [{self.sensor_name}] AKTÍV FELTÖLTÉS FOLYAMATBAN")
            return True, None, current_weight

        if refill_end:
            logger.info(f"✅ [{self.sensor_name}] Feltöltés befejezve: {refill_end.strftime('%Y-%m-%d %H:%M')}")
            return False, refill_end, current_weight

        return False, None, current_weight

    def calculate_exp_constant(self, normalized_curve: List[Tuple[datetime, float]]) -> Tuple[float, float, float]:
        """
        Exponenciális állandó számítása normalizált görbéből

        24 órás ablakokból (4x6h adatpont) napi fogyási rátákat számol,
        majd lineáris regresszióval meghatározza a gyorsulást.

        Args:
            normalized_curve: [(timestamp, normalized_weight), ...] 6 óránként

        Returns:
            (exp_constant, base_rate, acceleration)
        """
        if len(normalized_curve) < 8:  # Min 2 nap x 4 adatpont
            logger.warning(f"❌ [{self.sensor_name}] Exp állandó: kevés adat ({len(normalized_curve)} pont)")
            return 0.0, 0.0, 0.0

        # Napi fogyási ráták számítása 24 órás ablakokból
        daily_rates = []
        days = []

        for i in range(4, len(normalized_curve)):  # 4 pont = 24 óra
            prev_time, prev_weight = normalized_curve[i-4]
            curr_time, curr_weight = normalized_curve[i]

            # Napi fogyás (lehet negatív a normalizált görbében!)
            daily_consumption = prev_weight - curr_weight
            if daily_consumption < 0:
                daily_consumption = abs(daily_consumption)

            # Csak értelmes fogyásokat vegyük figyelembe
            if daily_consumption > 10:  # Min 10 kg/nap
                daily_rates.append(daily_consumption)
                days.append(i / 4.0)  # Nap index (4 adatpont = 1 nap)

        if len(daily_rates) < 3:
            logger.warning(f"⚠️ [{self.sensor_name}] Exp állandó: kevés napi adat ({len(daily_rates)})")
            return 0.0, 0.0, 0.0

        # Lineáris regresszió: fogyási ráta változása az időben
        rates_array = np.array(daily_rates)
        days_array = np.array(days)

        slope, intercept, r_value, _, _ = stats.linregress(days_array, rates_array)

        # Exponenciális állandó = gyorsulás / átlag ráta
        avg_rate = np.mean(rates_array)
        exp_constant = slope / avg_rate if avg_rate > 0 else 0.0

        logger.info(f"📈 [{self.sensor_name}] Exp állandó: {exp_constant:.6f}, "
                   f"alap ráta: {avg_rate:.1f} kg/nap, gyorsulás: {slope:.2f} kg/nap²")

        return exp_constant, avg_rate, slope

    def predict_with_tech_and_exp(self, current_real_weight: float, cycle_start: datetime,
                                   bird_count: int, base_rate: float, acceleration: float) -> Tuple[datetime, float]:
        """
        ELSŐDLEGES: Tech adat + Exponenciális predikció (VAN 0. nap)

        Iteratív szimuláció:
        - Tech napi fogyasztás (madárszám × tech g/nap)
        - Exponenciális korrekció (gyorsulás figyelembevételével)
        - Valós jelenlegi súlyból indul

        Args:
            current_real_weight: Jelenlegi valós súly (kg)
            cycle_start: 0. nap időpontja
            bird_count: Madárszám
            base_rate: Alap fogyási ráta (kg/nap)
            acceleration: Gyorsulás (kg/nap²)

        Returns:
            (prediction_datetime, days_until)
        """
        weight = current_real_weight
        current_time = datetime.now(LOCAL_TZ)

        # Jelenlegi nevelési nap
        current_day = (current_time - cycle_start).days

        hours = 0
        day = current_day
        max_days = 60  # Max 60 nap előre

        logger.info(f"🎯 [{self.sensor_name}] Tech+Exp predikció: súly={weight:.0f} kg, "
                   f"nap={day}, madár={bird_count:,}")

        while weight > 0 and day < current_day + max_days:
            # Tech adat: g/madár/nap
            tech_per_bird_g = self.tech_data.get_daily_intake_per_bird(day)
            tech_daily_kg = (tech_per_bird_g * bird_count) / 1000.0

            # Exponenciális korrekció
            days_elapsed = day - current_day
            current_rate = base_rate + (acceleration * days_elapsed)
            exp_factor = current_rate / base_rate if base_rate > 0 else 1.0

            # Korrigált napi fogyás
            actual_daily_kg = tech_daily_kg * exp_factor

            # Óránkénti fogyás
            hourly_kg = actual_daily_kg / 24.0
            weight -= hourly_kg
            hours += 1

            if hours % 24 == 0:
                day += 1

        prediction_time = current_time + timedelta(hours=hours)
        days_until = hours / 24.0

        logger.info(f"📅 [{self.sensor_name}] Tech+Exp: {prediction_time.strftime('%b %d, %H:%M')} "
                   f"({days_until:.1f} nap)")

        return prediction_time, days_until

    def predict_with_exp_only(self, current_real_weight: float, normalized_curve: List[Tuple[datetime, float]],
                               base_rate: float, acceleration: float) -> Tuple[datetime, float]:
        """
        FALLBACK: Csak exponenciális predikció (NINCS 0. nap)

        Gyorsuló lineáris extrapoláció a történelmi adatokból.

        Args:
            current_real_weight: Jelenlegi valós súly (kg)
            normalized_curve: Normalizált görbe
            base_rate: Alap fogyási ráta (kg/nap)
            acceleration: Gyorsulás (kg/nap²)

        Returns:
            (prediction_datetime, days_until)
        """
        weight = current_real_weight
        current_time = datetime.now(LOCAL_TZ)

        hours = 0
        current_rate = base_rate
        max_days = 60

        logger.info(f"🎯 [{self.sensor_name}] Exp-only predikció: súly={weight:.0f} kg, "
                   f"ráta={base_rate:.1f} kg/nap, gyorsulás={acceleration:.2f}")

        while weight > 0 and hours < (max_days * 24):
            # Napi fogyás (gyorsuló)
            daily_kg = current_rate
            hourly_kg = daily_kg / 24.0

            weight -= hourly_kg
            hours += 1

            # Naponta növeljük a rátát a gyorsulással
            if hours % 24 == 0:
                current_rate += acceleration

        prediction_time = current_time + timedelta(hours=hours)
        days_until = hours / 24.0

        logger.info(f"📅 [{self.sensor_name}] Exp-only: {prediction_time.strftime('%b %d, %H:%M')} "
                   f"({days_until:.1f} nap)")

        return prediction_time, days_until

    def calculate_prediction_exponential_fallback(self, data: List[Tuple[datetime, float]]) -> Optional[Dict]:
        """
        FALLBACK MÓDSZER: Exponenciális regressziós előrejelzés

        Akkor használatos, ha a 0. nap nem detektálható (nincs csend periódus + feltöltés).
        Csak az UTOLSÓ FELTÖLTÉS UTÁNI adatokra épít lineáris regressziót.

        Args:
            data: Napi mintavételezett adatok (timestamp, weight)

        Returns:
            Prediction dictionary vagy None
        """
        if not data or len(data) < 3:
            logger.warning(f"❌ [{self.sensor_name}] Exponenciális fallback: kevés adat ({len(data)} nap)")
            return None

        # 1. Utolsó feltöltés keresése
        last_refill_index = -1
        for i in range(1, len(data)):
            weight_change = data[i][1] - data[i-1][1]
            if weight_change > 3000:  # Feltöltés
                last_refill_index = i

        # 2. Csak utolsó feltöltés utáni adatok
        if last_refill_index > 0:
            cleaned_data = data[last_refill_index:]
            logger.info(f"📊 [{self.sensor_name}] Exponenciális módszer: utolsó feltöltés utáni {len(cleaned_data)} adatpont")

            # Ha kevés adat van feltöltés után, használjunk MINDEN adatot
            if len(cleaned_data) < 3:
                logger.warning(f"⚠️ [{self.sensor_name}] Kevés adat felt öltés után ({len(cleaned_data)}), MINDEN adat használata...")
                cleaned_data = data
        else:
            cleaned_data = data
            logger.info(f"📊 [{self.sensor_name}] Exponenciális módszer: {len(cleaned_data)} adatpont (nincs feltöltés)")

        if len(cleaned_data) < 3:
            logger.warning(f"❌ [{self.sensor_name}] Exponenciális fallback: kevés adat összesen ({len(cleaned_data)})")
            return None

        # 3. Lineáris regresszió (súly ~ idő)
        timestamps = np.array([(t - cleaned_data[0][0]).total_seconds() / 3600 for t, _ in cleaned_data])
        weights = np.array([w for _, w in cleaned_data])

        # Lineáris illesztés
        slope, intercept, r_value, p_value, std_err = stats.linregress(timestamps, weights)
        r_squared = r_value ** 2

        logger.info(f"📉 [{self.sensor_name}] Lineáris regresszió: "
                   f"meredekség={slope:.2f} kg/óra, R²={r_squared:.3f}")

        # 4. Előrejelzés: mikor lesz 0 kg?
        current_weight = weights[-1]
        current_timestamp = cleaned_data[-1][0]

        if slope >= 0:
            logger.warning(f"⚠️ [{self.sensor_name}] Exponenciális fallback: nem csökkenő trend (slope={slope:.2f})")
            return None

        # 0 kg időpont számítása: 0 = slope * t + intercept → t = -intercept / slope
        current_hours = timestamps[-1]
        hours_until_empty = -current_weight / slope  # Hány óra múlva lesz 0 kg

        if hours_until_empty < 0:
            logger.warning(f"⚠️ [{self.sensor_name}] Exponenciális fallback: negatív előrejelzés")
            return None

        prediction_datetime = datetime.now(LOCAL_TZ) + timedelta(hours=hours_until_empty)
        days_until = hours_until_empty / 24.0

        # Formázott dátum
        formatted_date, window_midpoint_hours = self._format_prediction_with_window(prediction_datetime)
        days_until_midpoint = window_midpoint_hours / 24.0

        logger.info(f"📅 [{self.sensor_name}] Exponenciális fallback 0 kg: {formatted_date}")
        logger.info(f"⏱️ [{self.sensor_name}] Hátralévő idő: {days_until_midpoint:.1f} nap")

        return {
            'prediction_date': formatted_date,
            'days_until_empty': round(days_until_midpoint, 2),
            'current_weight': round(current_weight, 0),
            'bird_count': None,  # Nem tudjuk
            'day_in_cycle': None,  # Nem tudjuk
            'correction_factor': None,
            'status': 'emptying',
            'tech_data_used': False,
            'method': 'exponential_fallback',
            'r_squared': round(r_squared, 3)
        }

    def calculate_prediction(self, data: List[Tuple[datetime, float]],
                             last_refill_time: Optional[datetime] = None) -> Optional[Dict]:
        """
        Előrejelzés készítése lineáris regresszióval (opcionális növekedési korrekcióval)

        ⚠️ EZ A RÉGI MÓDSZER - MOSTANTÓL NEM HASZNÁLT!

        Args:
            data: Súly adatok (timestamp, weight) párok
            last_refill_time: Utolsó feltöltés időpontja (None ha nem volt)

        Returns:
            Prediction dictionary vagy None
        """

        # Ellenőrizzük, hogy éppen most van-e feltöltés (utolsó 15 percben)
        if last_refill_time:
            time_since_refill = (datetime.now(LOCAL_TZ) - last_refill_time).total_seconds() / 3600
            if time_since_refill < 0.25:  # 15 perc = 0.25 óra
                minutes_since = int(time_since_refill * 60)
                logger.info(f"🔄 [{self.sensor_name}] Feltöltés folyamatban ({minutes_since} perce)")
                return {
                    'prediction_date': None,
                    'days_until_empty': None,
                    'slope': None,
                    'r_squared': None,
                    'current_weight': data[-1][1] if data else None,
                    'threshold': 0,
                    'status': 'refilling',
                    'refill_message': f'Feltöltés alatt ({minutes_since} perce)'
                }

        # AZONNALI előrejelzés 15 perc után (ha van előző slope)
        # 3 órás mintavételezésnél: minimum 8 adatpont (24 óra) kell az új regresszióhoz
        use_previous_slope = False
        if len(data) < 8:  # 8 * 3 óra = 24 óra
            if self.previous_slope is not None:
                logger.info(f"⚡ [{self.sensor_name}] Feltöltés utáni azonnali előrejelzés! "
                           f"({len(data)} adatpont, előző slope: {self.previous_slope:.4f} kg/óra)")
                use_previous_slope = True
            else:
                logger.warning(f"⏳ [{self.sensor_name}] Adatra vár "
                             f"(minimum 8 adatpont vagy előző slope kell, {len(data)} van)")
                return {
                    'prediction_date': None,
                    'days_until_empty': None,
                    'slope': None,
                    'r_squared': None,
                    'current_weight': data[-1][1] if data else None,
                    'threshold': 0,
                    'status': 'waiting_for_data',
                    'message': 'Adatra vár'
                }

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
        formatted_date, window_midpoint_hours = self._format_prediction_with_window(prediction_datetime)

        # Hátralévő idő az időablak KÖZEPÉIG (nem a pontos időig!)
        days_until_midpoint = window_midpoint_hours / 24

        logger.info(f"📅 [{self.sensor_name}] 0 kg előrejelzés: {formatted_date}")
        logger.info(f"⏱️ [{self.sensor_name}] Hátralévő idő (ablak közepéig): {days_until_midpoint:.1f} nap")

        return {
            'prediction_date': formatted_date,
            'days_until_empty': round(days_until_midpoint, 2),
            'slope': round(slope, 2),
            'r_squared': round(r_squared, 4),
            'current_weight': round(current_weight, 0),
            'threshold': 0,
            'status': 'emptying',
            'growth_correction_enabled': self.enable_growth_correction
        }

    def _format_prediction_with_window(self, prediction_datetime: datetime) -> Tuple[str, float]:
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
            Tuple: (formatted_string, hours_until_midpoint)
                   hours_until_midpoint: Órák száma az időablak közepéig
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

        # Időablak középpontja (órában)
        midpoint_hour = (hour_start + hour_end) / 2
        if hour_end < hour_start:  # Éjféli átlépés
            midpoint_hour = (hour_start + hour_end + 24) / 2
            if midpoint_hour >= 24:
                midpoint_hour -= 24

        # Időablak középpontjának datetime objektuma
        midpoint_date = prediction_datetime.date()
        if hour_end < hour_start and midpoint_hour < 12:  # Éjféli átlépés, középpont már másnapra esik
            midpoint_date = (prediction_datetime + timedelta(days=1)).date()

        window_midpoint = datetime.combine(midpoint_date, datetime.min.time()).replace(
            hour=int(midpoint_hour),
            minute=int((midpoint_hour - int(midpoint_hour)) * 60),
            tzinfo=LOCAL_TZ
        )

        # Órák száma a középpontig
        hours_until_midpoint = (window_midpoint - now).total_seconds() / 3600

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

        return f"{date_str} {time_window}", hours_until_midpoint

    def _calculate_with_growth_correction(self, current_weight: float, base_slope: float,
                                          current_hours: float, animal_age_days: float,
                                          step_hours: int = 3) -> float:
        """
        Növekedési korrekciós számítás - iteratív megoldás

        A növekvő takarmányfogyasztás miatt a siló gyorsabban ürül, mint amit a lineáris regresszió mutat.

        Args:
            current_weight: Jelenlegi súly (kg)
            base_slope: Lineáris regresszió meredeksége (kg/óra) - NEGATÍV!
            current_hours: Eltelt órák száma a mérési kezdet óta
            animal_age_days: Állatok jelenlegi életkora napokban
            step_hours: Szimulációs lépésköz órákban (alapértelmezett: 3)

        Returns:
            Hátralévő órák száma a 0 kg eléréséig
        """
        # Iteratív számítás - 3 órás lépésekkel
        weight = current_weight
        hours_elapsed = 0
        max_iterations = 10000 // step_hours  # Maximum ~416 nap (3 órás lépésekkel)

        # Jelenlegi nap
        current_day = animal_age_days

        logger.info(f"🧮 [{self.sensor_name}] Növekedési szimulációs számítás indítása...")
        logger.info(f"   Kezdeti súly: {current_weight:.1f} kg")
        logger.info(f"   Alapmeredekség: {base_slope:.4f} kg/óra")
        logger.info(f"   Állat életkor: {animal_age_days:.1f} nap")
        logger.info(f"   Szimulációs lépésköz: {step_hours} óra")

        iteration = 0
        while weight > 0 and iteration < max_iterations:
            # Aktuális nap (az állatokéhoz képest)
            day_in_cycle = current_day + (hours_elapsed / 24.0)

            # Növekedési korrekció az aktuális napra
            growth_adjustment = self.growth_rate_kg_per_hour_per_day * day_in_cycle

            # Teljes óránkénti fogyás (negatív, ezért a growth_adjustment CSÖKKENTI)
            hourly_consumption = base_slope - growth_adjustment

            # Súly csökkentése (step_hours órányira)
            weight += hourly_consumption * step_hours

            hours_elapsed += step_hours
            iteration += 1

            # Debug log minden 100 iterációnként (~300 óra)
            if iteration % 100 == 0:
                logger.debug(f"   {hours_elapsed}h: súly={weight:.1f} kg, "
                           f"napi_pozíció={day_in_cycle:.1f}, korrekció={growth_adjustment:.6f} kg/óra")

        if iteration >= max_iterations:
            logger.warning(f"⚠️ [{self.sensor_name}] Szimulációs limit elérve ({max_iterations} iteráció)")
            return hours_elapsed

        logger.info(f"✅ [{self.sensor_name}] Szimulációs eredmény: {hours_elapsed} óra ({hours_elapsed/24:.1f} nap)")

        return hours_elapsed

    def update_sensor(self, prediction_data: Dict):
        """Home Assistant szenzor frissítése"""
        if not prediction_data:
            logger.warning(f"❌ [{self.sensor_name}] Nincs előrejelzési adat a szenzor frissítéshez")
            return

        self._update_date_sensor(prediction_data)
        self._update_time_remaining_sensor(prediction_data)
        self._update_bird_count_sensor(prediction_data)
        self._update_last_updated_sensor()

    def _update_date_sensor(self, prediction_data: Dict):
        """Dátum szenzor frissítése (mikor lesz 0 kg)"""
        sensor_entity_id = f"sensor.{self.sensor_name.lower().replace(' ', '_')}"

        prediction_date = prediction_data.get('prediction_date')
        status = prediction_data.get('status', 'unknown')

        # Speciális üzenetek
        if status == 'refilling':
            state = "Feltöltés alatt"
        elif status == 'waiting_for_data':
            state = "Adatra vár"
        else:
            state = prediction_date if prediction_date else status

        attributes = {
            'prediction_date': prediction_date,
            'days_until_empty': prediction_data.get('days_until_empty'),
            'current_weight_kg': prediction_data.get('current_weight'),
            'bird_count': prediction_data.get('bird_count'),
            'day_in_cycle': prediction_data.get('day_in_cycle'),
            'correction_factor': prediction_data.get('correction_factor'),
            'status': status,
            'friendly_name': self.sensor_name,
            'icon': 'mdi:silo',
            # Ciklus adatok mentése
            'cycle_start_date': self.cycle_start_date.isoformat() if self.cycle_start_date else None,
            'tech_data_used': prediction_data.get('tech_data_used', False)
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

    def _update_bird_count_sensor(self, prediction_data: Dict):
        """Madár darabszám szenzor frissítése"""
        bird_count_entity_id = f"sensor.{self.sensor_name.lower().replace(' ', '_')}_bird_count"

        bird_count = prediction_data.get('bird_count')
        day_in_cycle = prediction_data.get('day_in_cycle', 0)

        if bird_count is not None:
            state = str(bird_count)
        else:
            state = "unknown"

        attributes = {
            'bird_count': bird_count,
            'day_in_cycle': day_in_cycle,
            'unit_of_measurement': 'madár',
            'friendly_name': f"{self.sensor_name} - Madár Darabszám",
            'icon': 'mdi:bird'
        }

        self._post_sensor(bird_count_entity_id, state, attributes)

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
        """
        Teljes feldolgozási folyamat egy silohoz

        ÚJ LOGIKA:
        1. 45 napos adatok lekérése
        2. 6 ÓRÁNKÉNTI mintavételezés (7:00, 13:00, 19:00, 1:00) - napi 4 adatpont
        3. AKTÍV FELTÖLTÉS ELLENŐRZÉS (utolsó 3 adatpont vizsgálata)
        4. 0. nap (ciklus kezdet) detektálás próbálkozás
        5a. HA SIKERÜLT 0. nap detektálás:
            - Folyamatos görbe (normalizált, 6óránként) → madár darabszám + korrekciós szorzó
            - Előrejelzés technológiai adatok + VALÓS jelenlegi súly
        5b. HA NEM SIKERÜLT 0. nap detektálás:
            - FALLBACK: Exponenciális regresszió utolsó feltöltés utáni adatokra
        6. Szenzor frissítése
        """
        try:
            logger.info(f"🔄 [{self.sensor_name}] Feldolgozás indítása...")

            # 1. Adatok lekérése (45 nap)
            raw_data = self.get_historical_data()

            if not raw_data:
                logger.warning(f"⚠️ [{self.sensor_name}] Nincs adat")
                return

            # 2. AKTÍV FELTÖLTÉS ELLENŐRZÉS (5 perces mintavételezéssel)
            is_refilling, refill_end, current_weight = self.check_active_refill()

            if is_refilling:
                # Feltöltés alatt szenzor frissítése
                refilling_data = {
                    'prediction_date': 'Feltöltés alatt',
                    'days_until_empty': None,
                    'current_weight': current_weight,
                    'bird_count': self.bird_count,
                    'day_in_cycle': None,
                    'status': 'refilling'
                }
                self.update_sensor(refilling_data)
                logger.info(f"✅ [{self.sensor_name}] Feltöltés alatt szenzor frissítve")
                return

            # 3. 6 órás mintavételezés (predikciós görbéhez)
            daily_data = self.sample_daily_data(raw_data)

            if not daily_data:
                logger.warning(f"⚠️ [{self.sensor_name}] Nincs napi mintavételezett adat")
                return

            # Jelenlegi VALÓS súly (utolsó mért érték)
            current_real_weight = daily_data[-1][1]

            # 4. Normalizált görbe készítése (csak timestamp, weight párokat használunk)
            normalized_simple = [(t, w) for t, w, _, _ in daily_data] if daily_data and len(daily_data[0]) == 4 else daily_data

            # 5. Exponenciális állandó számítása
            exp_constant, base_rate, acceleration = self.calculate_exp_constant(normalized_simple)

            if base_rate == 0:
                logger.warning(f"⚠️ [{self.sensor_name}] Nem sikerült exp állandót számítani")
                return

            # 6. 0. nap detektálás (ha még nincs)
            cycle_start_detected = False
            if not self.cycle_start_date:
                cycle_start = self.detect_cycle_start(daily_data)
                if cycle_start:
                    self._save_cycle_data(cycle_start, None)  # bird_count később kerül meghatározásra
                    cycle_start_detected = True
                else:
                    logger.warning(f"⚠️ [{self.sensor_name}] 0. nap nem detektálható → Fallback módszer")
            else:
                cycle_start_detected = True

            # 7. PREDIKCIÓ
            if cycle_start_detected and self.cycle_start_date:
                logger.info(f"✅ [{self.sensor_name}] TECH + EXP MÓDSZER használata")

                # Folyamatos görbe készítése (madár számításhoz)
                continuous_data = self.create_continuous_curve(daily_data, self.cycle_start_date)

                if not continuous_data:
                    logger.warning(f"⚠️ [{self.sensor_name}] Nincs folyamatos görbe adat")
                    return

                # Madár darabszám kalkuláció
                bird_counts = self.calculate_daily_bird_count(continuous_data)

                if not bird_counts:
                    logger.warning(f"⚠️ [{self.sensor_name}] Madár darabszám nem számolható, fallback...")
                    # Fallback-re váltunk
                    prediction_time, days_until = self.predict_with_exp_only(
                        current_real_weight, normalized_simple, base_rate, acceleration
                    )

                    # Formázott dátum
                    formatted_date, window_midpoint_hours = self._format_prediction_with_window(prediction_time)
                    days_until_midpoint = window_midpoint_hours / 24.0

                    # Nevelési nap (ha van cycle_start_date)
                    current_day = (datetime.now(LOCAL_TZ) - self.cycle_start_date).days if self.cycle_start_date else None

                    prediction = {
                        'prediction_date': formatted_date,
                        'days_until_empty': round(days_until_midpoint, 2),
                        'current_weight': round(current_real_weight, 0),
                        'bird_count': None,
                        'day_in_cycle': current_day,
                        'status': 'emptying',
                        'tech_data_used': False
                    }
                else:
                    # Átlag madárszám
                    avg_bird_count = int(np.mean(list(bird_counts.values())))

                    # Tech + Exp predikció
                    prediction_time, days_until = self.predict_with_tech_and_exp(
                        current_real_weight, self.cycle_start_date,
                        avg_bird_count, base_rate, acceleration
                    )

                    # Formázott dátum
                    formatted_date, window_midpoint_hours = self._format_prediction_with_window(prediction_time)
                    days_until_midpoint = window_midpoint_hours / 24.0

                    # Nevelési nap
                    current_day = (datetime.now(LOCAL_TZ) - self.cycle_start_date).days

                    prediction = {
                        'prediction_date': formatted_date,
                        'days_until_empty': round(days_until_midpoint, 2),
                        'current_weight': round(current_real_weight, 0),
                        'bird_count': avg_bird_count,
                        'day_in_cycle': current_day,
                        'status': 'emptying',
                        'tech_data_used': True
                    }

            # 7b. EXPONENCIÁLIS FALLBACK MÓDSZER (ha nincs 0. nap)
            else:
                logger.info(f"⚠️ [{self.sensor_name}] EXP-ONLY FALLBACK MÓDSZER használata")

                # Csak Exp predikció
                prediction_time, days_until = self.predict_with_exp_only(
                    current_real_weight, normalized_simple, base_rate, acceleration
                )

                # Formázott dátum
                formatted_date, window_midpoint_hours = self._format_prediction_with_window(prediction_time)
                days_until_midpoint = window_midpoint_hours / 24.0

                prediction = {
                    'prediction_date': formatted_date,
                    'days_until_empty': round(days_until_midpoint, 2),
                    'current_weight': round(current_real_weight, 0),
                    'bird_count': None,
                    'day_in_cycle': None,
                    'status': 'emptying',
                    'tech_data_used': False
                }

            # 5. Szenzor frissítése
            if prediction:
                # Mentjük a bird_count-ot a ciklus adatok közé
                if not self.bird_count and prediction.get('bird_count'):
                    self.bird_count = prediction['bird_count']

                self.update_sensor(prediction)
                logger.info(f"✅ [{self.sensor_name}] Feldolgozás sikeres")
            else:
                logger.warning(f"⚠️ [{self.sensor_name}] Előrejelzés sikertelen")

        except Exception as e:
            logger.error(f"❌ [{self.sensor_name}] Hiba a feldolgozás során: {e}", exc_info=True)


class MultiSiloManager:
    """Multi-silo manager - kezeli az összes silót"""

    def __init__(self):
        self.ha_url = os.getenv('HA_URL', 'http://supervisor/core')
        self.ha_token = os.getenv('HA_TOKEN', os.getenv('SUPERVISOR_TOKEN'))
        self.prediction_days = int(os.getenv('PREDICTION_DAYS', '45'))  # 45 nap az új alapértelmezett
        self.update_interval = int(os.getenv('UPDATE_INTERVAL', '86400'))  # 24 óra (86400s)

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
                    tech_csv_path='/app/tech_feed_data.csv'
                )
                silos.append(silo)
            except KeyError as e:
                logger.error(f"❌ Hiányzó mező a silo konfigurációban: {e}")

        return silos

    def _check_recent_refill(self, silo: 'SiloPredictor') -> bool:
        """
        Ellenőrzi, hogy volt-e friss feltöltés az elmúlt 20 percben

        Args:
            silo: SiloPredictor példány

        Returns:
            True ha volt friss feltöltés (< 20 perc)
        """
        try:
            # Utolsó 1 óra adat lekérése
            end_time = datetime.now(LOCAL_TZ)
            start_time = end_time - timedelta(hours=1)

            url = f"{self.ha_url}/api/history/period/{start_time.isoformat()}"
            params = {
                'filter_entity_id': silo.entity_id,
                'end_time': end_time.isoformat()
            }

            response = requests.get(url, headers=silo.headers, params=params, timeout=10)
            if response.status_code != 200:
                return False

            data = response.json()
            if not data or not data[0]:
                return False

            # Utolsó 2 adatpont vizsgálata
            recent_data = data[0][-2:] if len(data[0]) >= 2 else data[0]

            for i in range(1, len(recent_data)):
                try:
                    prev_weight = float(recent_data[i-1].get('state', 0))
                    curr_weight = float(recent_data[i].get('state', 0))
                    weight_change = curr_weight - prev_weight

                    timestamp_str = recent_data[i].get('last_changed', '')
                    timestamp_utc = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    timestamp = timestamp_utc.astimezone(LOCAL_TZ)

                    minutes_ago = (datetime.now(LOCAL_TZ) - timestamp).total_seconds() / 60

                    # Feltöltés detektálás: +3000 kg az elmúlt 20 percben
                    if weight_change > 3000 and minutes_ago < 20:
                        logger.info(f"🔄 [{silo.sensor_name}] Friss feltöltés detektálva: "
                                   f"{minutes_ago:.0f} perce, +{weight_change:.0f} kg")
                        return True

                except (ValueError, KeyError, TypeError):
                    continue

            return False

        except Exception as e:
            logger.debug(f"❌ [{silo.sensor_name}] Feltöltés ellenőrzési hiba: {e}")
            return False

    def run(self):
        """
        Fő futási ciklus - periodikusan feldolgozza az összes silót

        FRISSÍTÉSI LOGIKA:
        - Normál: 24 óránként
        - Feltöltés után: 20 perc várakozás, majd AZONNALI frissítés
        """
        # Várakozás Home Assistant core felállására (502 Bad Gateway elkerülése)
        logger.info("⏳ Várakozás 30 másodpercet a Home Assistant core indulására...")
        time.sleep(30)

        logger.info("🔄 Multi-Silo Prediction szolgáltatás indítva")
        logger.info(f"📊 Normál frissítési intervallum: {self.update_interval / 3600:.0f} óra")
        logger.info(f"⚡ Feltöltés utáni frissítés: 20 perc várakozás után")

        while True:
            try:
                logger.info("=" * 60)
                logger.info(f"🔄 Új feldolgozási ciklus kezdődik ({len(self.silos)} silo)")

                refill_detected = False

                for silo in self.silos:
                    silo.process()

                    # Ellenőrizzük, hogy volt-e friss feltöltés
                    if self._check_recent_refill(silo):
                        refill_detected = True

                logger.info(f"✅ Feldolgozási ciklus befejezve")

                # Feltöltés utáni logika
                if refill_detected:
                    logger.info(f"⚡ Feltöltés detektálva! Várakozás 20 perc, majd újra futtatás...")
                    time.sleep(20 * 60)  # 20 perc = 1200 másodperc

                    logger.info("🔄 Feltöltés utáni újra futtatás...")
                    for silo in self.silos:
                        silo.process()

                    logger.info(f"✅ Feltöltés utáni frissítés befejezve")

                # Normál várakozás
                logger.info(f"⏰ Következő frissítés {self.update_interval / 3600:.0f} óra múlva...")
                time.sleep(self.update_interval)

            except Exception as e:
                logger.error(f"❌ Hiba a futás során: {e}", exc_info=True)
                time.sleep(60)


if __name__ == '__main__':
    manager = MultiSiloManager()
    manager.run()
