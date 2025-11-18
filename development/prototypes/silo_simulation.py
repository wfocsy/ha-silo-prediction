#!/usr/bin/env python3
"""
Silo Prediction Simulation - CFM 3 Hall csend periódus detektálás debug
"""
import requests
import numpy as np
from datetime import datetime, timedelta
import json

# Konfiguráció
ENTITY_ID = "sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly"
REFILL_THRESHOLD = 1000
MAX_CAPACITY = 20000
PREDICTION_DAYS = 60  # Növelve 60 napra, hogy lássuk a szeptember végi csend periódust

# Home Assistant API
HA_URL = "http://supervisor/core"
TOKEN_FILE = "/data/options.json"

def get_token():
    """Read supervisor token"""
    import os

    # Try environment variables first
    token = os.getenv("SUPERVISOR_TOKEN") or os.getenv("HASSIO_TOKEN") or os.getenv("HASS_TOKEN")
    if token:
        return token

    # Try reading from file
    try:
        with open("/run/s6/container_environment/SUPERVISOR_TOKEN", "r") as f:
            return f.read().strip()
    except:
        pass

    return None

def fetch_history(entity_id, days=45):
    """Fetch history from Home Assistant"""
    token = get_token()
    if not token:
        print("❌ Nincs token!")
        return None

    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    url = f"{HA_URL}/api/history/period/{start_time.isoformat()}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    params = {
        "filter_entity_id": entity_id,
        "end_time": end_time.isoformat()
    }

    print(f"📊 Adatok lekérése: {start_time.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%Y-%m-%d %H:%M')}")

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if not data or not data[0]:
            print("❌ Nincs adat!")
            return None

        print(f"✅ API válasz: {len(data[0])} rekord")
        return data[0]
    except Exception as e:
        print(f"❌ API hiba: {e}")
        return None

def parse_history(history_data):
    """Parse history data to numpy arrays"""
    timestamps = []
    weights = []
    skipped = 0

    for entry in history_data:
        try:
            state = entry.get("state")
            if state in ["unknown", "unavailable", None]:
                skipped += 1
                continue

            weight = float(state)
            timestamp = datetime.fromisoformat(entry["last_changed"].replace("Z", "+00:00"))

            timestamps.append(timestamp)
            weights.append(weight)
        except:
            skipped += 1
            continue

    if skipped > 0:
        print(f"⚠️ Kihagyott invalid rekord: {skipped}")

    return np.array(timestamps), np.array(weights)

def resample_6hourly(timestamps, weights):
    """Resample to 6-hourly intervals (4 samples per day)"""
    if len(timestamps) == 0:
        return np.array([]), np.array([])

    start_time = timestamps[0]
    end_time = timestamps[-1]

    # Generate 6-hourly grid (00:00, 06:00, 12:00, 18:00)
    current = start_time.replace(hour=(start_time.hour // 6) * 6, minute=0, second=0, microsecond=0)
    sample_times = []
    sample_weights = []

    while current <= end_time:
        # Find data within ±3 hours
        window_start = current - timedelta(hours=3)
        window_end = current + timedelta(hours=3)

        mask = (timestamps >= window_start) & (timestamps <= window_end)
        if np.any(mask):
            avg_weight = np.mean(weights[mask])
            sample_times.append(current)
            sample_weights.append(avg_weight)

        current += timedelta(hours=6)

    return np.array(sample_times), np.array(sample_weights)

def analyze_silence_periods(timestamps, weights, min_silence_hours=12):
    """Analyze silence periods in the data"""
    print("\n" + "="*80)
    print("🔍 CSEND PERIÓDUSOK ELEMZÉSE")
    print("="*80)

    if len(timestamps) < 2:
        print("❌ Nincs elég adat!")
        return

    # Calculate time gaps
    time_diffs = np.diff(timestamps)
    time_diffs_hours = np.array([td.total_seconds() / 3600 for td in time_diffs])

    # Find silence periods (gaps > min_silence_hours)
    silence_mask = time_diffs_hours >= min_silence_hours
    silence_indices = np.where(silence_mask)[0]

    print(f"\n📊 Statisztika:")
    print(f"   - Összes adatpont: {len(timestamps)}")
    print(f"   - Átlagos időköz: {np.mean(time_diffs_hours):.2f} óra")
    print(f"   - Max időköz: {np.max(time_diffs_hours):.2f} óra")
    print(f"   - Min időköz: {np.min(time_diffs_hours):.4f} óra")
    print(f"   - {min_silence_hours}+ órás csend periódusok száma: {len(silence_indices)}")

    if len(silence_indices) > 0:
        print(f"\n🔇 Talált csend periódusok (>{min_silence_hours} óra):")
        for idx in silence_indices[:10]:  # Show first 10
            silence_hours = time_diffs_hours[idx]
            silence_start = timestamps[idx]
            silence_end = timestamps[idx + 1]
            weight_before = weights[idx]
            weight_after = weights[idx + 1]
            weight_change = weight_after - weight_before

            print(f"   {silence_start.strftime('%Y-%m-%d %H:%M')} -> {silence_end.strftime('%Y-%m-%d %H:%M')}")
            print(f"      Időtartam: {silence_hours:.1f} óra")
            print(f"      Súly előtte: {weight_before:.0f} kg")
            print(f"      Súly utána: {weight_after:.0f} kg")
            print(f"      Változás: {weight_change:+.0f} kg")
            print()
    else:
        print(f"\n❌ Nincs {min_silence_hours}+ órás csend periódus!")
        print(f"   Ez azt jelenti, hogy folyamatos adatgyűjtés van.")

def analyze_refills(timestamps, weights, refill_threshold=1000):
    """Analyze refill events"""
    print("\n" + "="*80)
    print("🔄 FELTÖLTÉSEK ELEMZÉSE")
    print("="*80)

    if len(timestamps) < 2:
        print("❌ Nincs elég adat!")
        return

    # Calculate weight changes
    weight_diffs = np.diff(weights)

    # Find refills (weight increase > threshold)
    refill_mask = weight_diffs >= refill_threshold
    refill_indices = np.where(refill_mask)[0]

    print(f"\n📊 Statisztika:")
    print(f"   - Feltöltési küszöb: {refill_threshold} kg")
    print(f"   - Talált feltöltések száma: {len(refill_indices)}")
    print(f"   - Max súlynövekedés: {np.max(weight_diffs):.0f} kg")
    print(f"   - Max súlycsökkenés: {np.min(weight_diffs):.0f} kg")

    if len(refill_indices) > 0:
        print(f"\n⬆️ Talált feltöltések (>{refill_threshold} kg):")
        for idx in refill_indices[:20]:  # Show first 20
            refill_time = timestamps[idx + 1]
            weight_before = weights[idx]
            weight_after = weights[idx + 1]
            weight_change = weight_after - weight_before

            print(f"   {refill_time.strftime('%Y-%m-%d %H:%M')}: {weight_before:.0f} -> {weight_after:.0f} kg (+{weight_change:.0f} kg)")
    else:
        print(f"\n❌ Nincs {refill_threshold}+ kg-os feltöltés!")
        print(f"   Próbálj alacsonyabb küszöböt használni.")

def find_cycle_start(timestamps, weights, refill_threshold=1000, silence_hours=12):
    """Try to find cycle start using the addon's logic"""
    print("\n" + "="*80)
    print("🎯 CIKLUS KEZDET KERESÉSE (Addon logika)")
    print("="*80)

    weight_diffs = np.diff(weights)
    time_diffs = np.array([td.total_seconds() / 3600 for td in np.diff(timestamps)])

    # Method 1: Silence period + refill
    print("\n1️⃣ Módszer: Csend periódus utáni feltöltés")
    silence_mask = time_diffs >= silence_hours
    refill_mask = weight_diffs >= refill_threshold

    cycle_candidates = []
    for i in range(len(weight_diffs)):
        if silence_mask[i] and refill_mask[i]:
            cycle_candidates.append(i + 1)
            print(f"   ✅ Találat: {timestamps[i + 1].strftime('%Y-%m-%d %H:%M')}")
            print(f"      Csend: {time_diffs[i]:.1f} óra")
            print(f"      Feltöltés: {weight_diffs[i]:.0f} kg")

    if not cycle_candidates:
        print(f"   ❌ Nincs találat (csend ÉS feltöltés együtt)")

    # Method 2: Large refill only
    print(f"\n2️⃣ Módszer: Nagy feltöltés (>{refill_threshold*5} kg)")
    large_refill_threshold = refill_threshold * 5
    large_refills = np.where(weight_diffs >= large_refill_threshold)[0]

    if len(large_refills) > 0:
        for idx in large_refills[:10]:
            print(f"   ✅ Találat: {timestamps[idx + 1].strftime('%Y-%m-%d %H:%M')}")
            print(f"      Feltöltés: {weight_diffs[idx]:.0f} kg ({weights[idx]:.0f} -> {weights[idx+1]:.0f} kg)")
    else:
        print(f"   ❌ Nincs {large_refill_threshold}+ kg-os feltöltés")

    # Method 3: Weight distribution analysis
    print(f"\n3️⃣ Módszer: Súlyeloszlás elemzés")
    print(f"   - Min súly: {np.min(weights):.0f} kg")
    print(f"   - Max súly: {np.max(weights):.0f} kg")
    print(f"   - Átlag súly: {np.mean(weights):.0f} kg")
    print(f"   - Medián súly: {np.median(weights):.0f} kg")

    # Find weights near max capacity
    near_max = weights >= MAX_CAPACITY * 0.8
    if np.any(near_max):
        near_max_times = timestamps[near_max]
        print(f"   -Max kapacitás 80%-a feletti időpontok: {len(near_max_times)} db")
        if len(near_max_times) > 0:
            print(f"     Legutóbbi: {near_max_times[-1].strftime('%Y-%m-%d %H:%M')}")

def main():
    print("🚀 CFM 3 Hall Silo - Csend Periódus Debug Szimuláció")
    print("="*80)

    # Fetch data
    history = fetch_history(ENTITY_ID, PREDICTION_DAYS)
    if not history:
        return

    # Parse data
    timestamps, weights = parse_history(history)
    print(f"✅ {len(timestamps)} adatpont betöltve")

    if len(timestamps) == 0:
        print("❌ Nincs feldolgozható adat!")
        return

    print(f"📅 Időtartam: {timestamps[0].strftime('%Y-%m-%d %H:%M')} - {timestamps[-1].strftime('%Y-%m-%d %H:%M')}")

    # Resample to 6-hourly
    sample_times, sample_weights = resample_6hourly(timestamps, weights)
    print(f"📈 {len(sample_times)} adatpont mintavételezve (6 óránként)")

    if len(sample_times) == 0:
        print("❌ Nincs mintavételezett adat!")
        return

    # Analyze original data
    print("\n" + "="*80)
    print("📊 EREDETI ADATOK ELEMZÉSE (minden adatpont)")
    print("="*80)
    analyze_silence_periods(timestamps, weights, min_silence_hours=12)
    analyze_refills(timestamps, weights, REFILL_THRESHOLD)

    # Analyze resampled data
    print("\n" + "="*80)
    print("📊 MINTAVÉTELEZETT ADATOK ELEMZÉSE (6 óránként)")
    print("="*80)
    analyze_silence_periods(sample_times, sample_weights, min_silence_hours=12)
    analyze_refills(sample_times, sample_weights, REFILL_THRESHOLD)
    find_cycle_start(sample_times, sample_weights, REFILL_THRESHOLD, silence_hours=12)

    print("\n" + "="*80)
    print("✅ Szimuláció befejezve")
    print("="*80)

if __name__ == "__main__":
    main()
