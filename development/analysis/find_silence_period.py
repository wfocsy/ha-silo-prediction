#!/usr/bin/env python3
"""
Csend periódus keresése a jelenlegi adatokban
"""
import requests
import numpy as np
from datetime import datetime, timedelta
import os

TOKEN = os.getenv("SUPERVISOR_TOKEN")
HA_URL = "http://supervisor/core"
ENTITY_ID = "sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly"

def fetch_data():
    """Adatok lekérése"""
    end_time = datetime.now()
    start_time = end_time - timedelta(days=10)  # Csak 10 nap van

    url = f"{HA_URL}/api/history/period/{start_time.isoformat()}"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    params = {
        "filter_entity_id": ENTITY_ID,
        "end_time": end_time.isoformat()
    }

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

    return np.array(timestamps), np.array(weights)

def resample_6hourly(timestamps, weights):
    """6 órás mintavételezés"""
    if len(timestamps) == 0:
        return [], []

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

    return sample_times, sample_weights

def analyze_silence_periods(timestamps, weights):
    """Csend periódusok elemzése"""
    print("=" * 80)
    print("🔍 CSEND PERIÓDUS KERESÉSE")
    print("=" * 80)
    print()

    # Napi összegzés
    print("📊 NAPI SÚLY STATISZTIKA:")
    print("-" * 80)

    daily_data = {}
    for t, w in zip(timestamps, weights):
        day = t.date()
        if day not in daily_data:
            daily_data[day] = []
        daily_data[day].append(w)

    for day in sorted(daily_data.keys()):
        weights_day = daily_data[day]
        avg = np.mean(weights_day)
        min_w = np.min(weights_day)
        max_w = np.max(weights_day)

        # Csend jelölő
        silence_marker = ""
        if max_w < 1000:
            silence_marker = "  ⚠️ CSEND? (max < 1000 kg)"
        elif max_w < 500:
            silence_marker = "  🔇 ERŐS CSEND (max < 500 kg)"
        elif max_w < 100:
            silence_marker = "  🔕 TELJES CSEND (max < 100 kg)"

        print(f"  {day}: átlag={avg:7.0f} kg, min={min_w:7.0f} kg, max={max_w:7.0f} kg{silence_marker}")

    # Órás csend periódusok
    print("\n📉 ALACSONY SÚLY IDŐSZAKOK (< 1000 kg):")
    print("-" * 80)

    low_weight_periods = []
    current_period = None

    for t, w in zip(timestamps, weights):
        if w < 1000:
            if current_period is None:
                current_period = {"start": t, "end": t, "min": w, "max": w, "weights": [w]}
            else:
                current_period["end"] = t
                current_period["min"] = min(current_period["min"], w)
                current_period["max"] = max(current_period["max"], w)
                current_period["weights"].append(w)
        else:
            if current_period is not None:
                if len(current_period["weights"]) > 10:  # Legalább 10 mérés
                    low_weight_periods.append(current_period)
                current_period = None

    # Utolsó periódus lezárása
    if current_period is not None and len(current_period["weights"]) > 10:
        low_weight_periods.append(current_period)

    if low_weight_periods:
        for i, period in enumerate(low_weight_periods):
            duration = period["end"] - period["start"]
            avg = np.mean(period["weights"])
            print(f"\n  Periódus #{i+1}:")
            print(f"    Kezdet: {period['start'].strftime('%Y-%m-%d %H:%M')}")
            print(f"    Vége:   {period['end'].strftime('%Y-%m-%d %H:%M')}")
            print(f"    Időtartam: {duration.total_seconds() / 3600:.1f} óra ({duration.days} nap)")
            print(f"    Átlag súly: {avg:.0f} kg")
            print(f"    Min: {period['min']:.0f} kg, Max: {period['max']:.0f} kg")
            print(f"    Mérések: {len(period['weights'])} db")
    else:
        print("  ❌ Nincs jelentős alacsony súly periódus")

    # Csend kritériumok ellenőrzése
    print("\n🎯 CSEND KRITÉRIUMOK ELEMZÉSE:")
    print("-" * 80)

    print("\n  1️⃣ Van-e 5+ napos periódus ahol súly < 1000 kg?")
    five_day_silence = False
    for period in low_weight_periods:
        duration_days = (period["end"] - period["start"]).days
        if duration_days >= 5:
            print(f"     ✅ IGEN - {period['start'].strftime('%Y-%m-%d')} ({duration_days} nap)")
            five_day_silence = True
            break
    if not five_day_silence:
        print(f"     ❌ NEM")

    print("\n  2️⃣ Van-e 12+ órás időszak ahol súly < 100 kg?")
    very_low_periods = []
    for t, w in zip(timestamps, weights):
        if w < 100:
            very_low_periods.append((t, w))

    if very_low_periods:
        # Csoportosítás folytonos periódusokba
        groups = []
        current_group = [very_low_periods[0]]
        for i in range(1, len(very_low_periods)):
            if (very_low_periods[i][0] - current_group[-1][0]).total_seconds() < 7200:  # 2 óra
                current_group.append(very_low_periods[i])
            else:
                if len(current_group) > 1:
                    groups.append(current_group)
                current_group = [very_low_periods[i]]
        if len(current_group) > 1:
            groups.append(current_group)

        if groups:
            for group in groups:
                duration = (group[-1][0] - group[0][0]).total_seconds() / 3600
                if duration >= 12:
                    print(f"     ✅ IGEN - {group[0][0].strftime('%Y-%m-%d %H:%M')} ({duration:.1f} óra)")
                    break
        else:
            print(f"     ❌ NEM (van < 100 kg, de nem 12+ óráig)")
    else:
        print(f"     ❌ NEM")

    print("\n  3️⃣ Van-e folyamatos növekedés 5000+ kg-mal egy periódusból?")
    for i in range(1, len(timestamps)):
        increase = weights[i] - weights[i-1]
        if increase > 5000:
            print(f"     ✅ IGEN - {timestamps[i].strftime('%Y-%m-%d %H:%M')}: +{increase:.0f} kg ({weights[i-1]:.0f} -> {weights[i]:.0f} kg)")
            # Előző nap ellenőrzése
            prev_day = timestamps[i-1].date()
            if prev_day in daily_data:
                prev_max = np.max(daily_data[prev_day])
                if prev_max < 1000:
                    print(f"        ⭐ Előző nap max súly: {prev_max:.0f} kg < 1000 kg → CSEND UTÁNI FELTÖLTÉS!")
            break
    else:
        print(f"     ❌ NEM")

def main():
    print("🔍 CSEND PERIÓDUS KERESÉSE A JELENLEGI ADATOKBAN")
    print("=" * 80)
    print()

    # Adatok lekérése
    timestamps, weights = fetch_data()
    print(f"✅ {len(timestamps)} nyers adatpont betöltve")
    print(f"📅 Időszak: {timestamps[0].strftime('%Y-%m-%d')} - {timestamps[-1].strftime('%Y-%m-%d')}")
    print()

    # Elemzés
    analyze_silence_periods(timestamps, weights)

    # 6 órás mintavételezés elemzése
    print("\n" + "=" * 80)
    print("📈 6 ÓRÁS MINTAVÉTELEZÉS ELEMZÉSE")
    print("=" * 80)
    print()

    sample_times, sample_weights = resample_6hourly(timestamps, weights)
    print(f"✅ {len(sample_times)} mintavételezett adatpont")

    if len(sample_times) > 0:
        print(f"📅 Időszak: {sample_times[0].strftime('%Y-%m-%d')} - {sample_times[-1].strftime('%Y-%m-%d')}")

        print("\n📊 Mintavételezett adatok áttekintése:")
        for t, w in zip(sample_times[-20:], sample_weights[-20:]):  # Utolsó 20
            print(f"  {t.strftime('%Y-%m-%d %H:%M')}: {w:7.0f} kg")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
