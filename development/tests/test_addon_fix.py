#!/usr/bin/env python3
"""
Addon javítás tesztelése - 5000kg fallback küszöb
Szimuláljuk az addon detect_cycle_start() függvényét a valós adatokkal
"""
import sys
sys.path.insert(0, '/addons/silo_prediction')

import numpy as np
from datetime import datetime, timedelta
import requests
import os

# Token
TOKEN = os.getenv("SUPERVISOR_TOKEN")
HA_URL = "http://supervisor/core"
ENTITY_ID = "sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly"

def fetch_and_resample():
    """Adatok lekérése és 6 órás mintavételezés"""
    print("=" * 80)
    print("📊 ADATOK LEKÉRÉSE ÉS MINTAVÉTELEZÉS")
    print("=" * 80)

    end_time = datetime.now()
    start_time = end_time - timedelta(days=45)

    url = f"{HA_URL}/api/history/period/{start_time.isoformat()}"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    params = {
        "filter_entity_id": ENTITY_ID,
        "end_time": end_time.isoformat()
    }

    print(f"Lekérdezés: {start_time.strftime('%Y-%m-%d')} - {end_time.strftime('%Y-%m-%d')}")

    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()[0]

    # Parse
    timestamps = []
    weights = []
    for entry in data:
        try:
            state = entry.get("state")
            if state in ["unknown", "unavailable", None]:
                continue
            weight = float(state)
            timestamp = datetime.fromisoformat(entry["last_changed"].replace("Z", "+00:00"))
            timestamps.append(timestamp)
            weights.append(weight)
        except:
            continue

    timestamps = np.array(timestamps)
    weights = np.array(weights)

    print(f"✅ {len(timestamps)} nyers adatpont betöltve")
    print(f"📅 Időszak: {timestamps[0].strftime('%Y-%m-%d')} - {timestamps[-1].strftime('%Y-%m-%d')}")

    # 6 órás mintavételezés
    start_time = timestamps[0]
    end_time = timestamps[-1]

    current = start_time.replace(hour=(start_time.hour // 6) * 6, minute=0, second=0, microsecond=0)
    sample_times = []
    sample_weights = []

    while current <= end_time:
        window_start = current - timedelta(hours=3)
        window_end = current + timedelta(hours=3)

        mask = (timestamps >= window_start) & (timestamps <= window_end)
        if np.any(mask):
            avg_weight = np.mean(weights[mask])
            sample_times.append(current)
            sample_weights.append(avg_weight)

        current += timedelta(hours=6)

    print(f"📈 {len(sample_times)} mintavételezett adatpont (6 óránként)")

    # Konvertálás lista formára
    data_list = list(zip(sample_times, sample_weights))
    return data_list

def test_cycle_detection_old(data):
    """RÉGI módszer tesztelése (10000kg küszöb)"""
    print("\n" + "=" * 80)
    print("🔍 RÉGI MÓDSZER (10000kg küszöb)")
    print("=" * 80)

    first_refill_index = -1

    # 1. Csend periódus keresés
    for i in range(5, len(data)):
        silence_period = True
        for j in range(i - 5, i):
            weight = data[j][1]
            if weight > 1000:
                silence_period = False
                break
            if j > 0:
                daily_change = abs(data[j][1] - data[j-1][1])
                if daily_change > 50:
                    silence_period = False
                    break

        if silence_period and i < len(data):
            weight_change = data[i][1] - data[i-1][1]
            if weight_change > 3000:
                first_refill_index = i
                print(f"✅ Csend periódus találat: {data[i][0].strftime('%Y-%m-%d %H:%M')}, +{weight_change:.0f} kg")
                break

    # 2. Fallback: nagy feltöltés (10000kg+)
    if first_refill_index < 0:
        print("🔍 Csend periódus nem található, fallback: 10000kg+ feltöltés keresése...")

        for i in range(1, len(data)):
            weight_change = data[i][1] - data[i-1][1]
            if weight_change > 10000:
                first_refill_index = i
                print(f"✅ Nagy feltöltés találat: {data[i][0].strftime('%Y-%m-%d %H:%M')}, +{weight_change:.0f} kg")
                break

    if first_refill_index < 0:
        print("❌ NINCS TALÁLAT - Nem található ciklus kezdő feltöltés")
        return None

    # 3. 0. nap keresése (100kg+ fogyasztás)
    for i in range(first_refill_index + 1, len(data)):
        prev_day_weight = data[i - 1][1]
        current_weight = data[i][1]
        daily_consumption = prev_day_weight - current_weight

        if daily_consumption > 100:
            cycle_start = data[i][0]
            print(f"🐣 0. NAP: {cycle_start.strftime('%Y-%m-%d %H:%M')}, fogyasztás: {daily_consumption:.0f} kg")
            return cycle_start

    print("⚠️ 0. nap nem található")
    return None

def test_cycle_detection_new(data):
    """ÚJ módszer tesztelése (5000kg küszöb)"""
    print("\n" + "=" * 80)
    print("🔍 ÚJ MÓDSZER (5000kg küszöb - JAVÍTOTT)")
    print("=" * 80)

    first_refill_index = -1

    # 1. Csend periódus keresés
    for i in range(5, len(data)):
        silence_period = True
        for j in range(i - 5, i):
            weight = data[j][1]
            if weight > 1000:
                silence_period = False
                break
            if j > 0:
                daily_change = abs(data[j][1] - data[j-1][1])
                if daily_change > 50:
                    silence_period = False
                    break

        if silence_period and i < len(data):
            weight_change = data[i][1] - data[i-1][1]
            if weight_change > 3000:
                first_refill_index = i
                print(f"✅ Csend periódus találat: {data[i][0].strftime('%Y-%m-%d %H:%M')}, +{weight_change:.0f} kg")
                break

    # 2. Fallback: nagy feltöltés (5000kg+) - JAVÍTOTT!
    if first_refill_index < 0:
        print("🔍 Csend periódus nem található, fallback: 5000kg+ feltöltés keresése...")

        for i in range(1, len(data)):
            weight_change = data[i][1] - data[i-1][1]
            if weight_change > 5000:
                first_refill_index = i
                print(f"✅ Nagy feltöltés találat: {data[i][0].strftime('%Y-%m-%d %H:%M')}, +{weight_change:.0f} kg")
                break

    if first_refill_index < 0:
        print("❌ NINCS TALÁLAT - Nem található ciklus kezdő feltöltés")
        return None

    # 3. 0. nap keresése (100kg+ fogyasztás)
    for i in range(first_refill_index + 1, len(data)):
        prev_day_weight = data[i - 1][1]
        current_weight = data[i][1]
        daily_consumption = prev_day_weight - current_weight

        if daily_consumption > 100:
            cycle_start = data[i][0]
            print(f"🐣 0. NAP: {cycle_start.strftime('%Y-%m-%d %H:%M')}, fogyasztás: {daily_consumption:.0f} kg")
            return cycle_start

    print("⚠️ 0. nap nem található")
    return None

def main():
    print("🧪 ADDON JAVÍTÁS TESZT")
    print("=" * 80)
    print("Cél: Tesztelni az 5000kg-os fallback küszöb javítást")
    print()

    # Adatok lekérése
    data = fetch_and_resample()

    # Régi módszer tesztelése
    old_result = test_cycle_detection_old(data)

    # Új módszer tesztelése
    new_result = test_cycle_detection_new(data)

    # Összehasonlítás
    print("\n" + "=" * 80)
    print("📊 EREDMÉNYEK ÖSSZEHASONLÍTÁSA")
    print("=" * 80)

    print("\nRÉGI módszer (10000kg küszöb):")
    if old_result:
        print(f"  ✅ Sikeres - 0. nap: {old_result.strftime('%Y-%m-%d %H:%M')}")
    else:
        print(f"  ❌ Sikertelen - Nem találta a 0. napot")

    print("\nÚJ módszer (5000kg küszöb):")
    if new_result:
        print(f"  ✅ Sikeres - 0. nap: {new_result.strftime('%Y-%m-%d %H:%M')}")
    else:
        print(f"  ❌ Sikertelen - Nem találta a 0. napot")

    print("\n" + "=" * 80)
    print("🎯 KÖVETKEZTETÉS")
    print("=" * 80)

    if not old_result and new_result:
        print("✅ A JAVÍTÁS MŰKÖDIK!")
        print("   Az új 5000kg küszöb megtalálta a ciklus kezdetet,")
        print("   míg a régi 10000kg küszöb NEM találta meg.")
    elif old_result and new_result:
        print("ℹ️  Mindkét módszer működik")
    elif not old_result and not new_result:
        print("❌ Egyik módszer sem működik - További vizsgálat szükséges")
    else:
        print("⚠️ Váratlan eredmény")

    print("=" * 80)

if __name__ == "__main__":
    main()
