#!/usr/bin/env python3
"""
Élő predikció a jelenlegi adatokkal (History API)
"""
import requests
import numpy as np
from datetime import datetime, timedelta
from scipy import stats
import os

TOKEN = os.getenv("SUPERVISOR_TOKEN")
HA_URL = "http://supervisor/core"
ENTITY_ID = "sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly"

def fetch_data():
    """Adatok lekérése History API-ból"""
    end_time = datetime.now()
    start_time = end_time - timedelta(days=10)  # Utolsó 10 nap

    url = f"{HA_URL}/api/history/period/{start_time.isoformat()}"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    params = {
        "filter_entity_id": ENTITY_ID,
        "end_time": end_time.isoformat()
    }

    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()[0]

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

def format_prediction_time(prediction_datetime):
    """Emberi olvasható dátum formátum"""
    now = datetime.now(prediction_datetime.tzinfo)

    days_diff = (prediction_datetime.date() - now.date()).days

    if days_diff == 0:
        date_str = "Ma"
    elif days_diff == 1:
        date_str = "Holnap"
    elif days_diff == -1:
        date_str = "Tegnap"
    else:
        date_str = prediction_datetime.strftime('%Y-%m-%d')

    pred_hour = prediction_datetime.hour
    pred_minute = prediction_datetime.minute

    hour_start = (pred_hour // 2) * 2
    hour_end = hour_start + 2

    formatted = f"{date_str} {hour_start:02d}-{hour_end:02d} óra között (~{pred_hour:02d}:{pred_minute:02d})"

    return formatted

def main():
    print("🎯 ÉLŐ PREDIKCIÓ - JELENLEGI ÁLLAPOT")
    print("=" * 80)

    # Adatok lekérése
    timestamps, weights = fetch_data()
    print(f"✅ {len(timestamps)} nyers adatpont betöltve")
    print(f"📅 Időszak: {timestamps[0].strftime('%Y-%m-%d %H:%M')} - {timestamps[-1].strftime('%Y-%m-%d %H:%M')}")

    # 6 órás mintavételezés
    sample_times, sample_weights = resample_6hourly(timestamps, weights)
    print(f"📈 {len(sample_times)} mintavételezett adatpont (6 óránként)")

    # Legutolsó nagy feltöltés keresése
    last_refill_idx = -1
    for i in range(len(sample_times) - 1, 0, -1):
        weight_change = sample_weights[i] - sample_weights[i-1]
        if weight_change > 3000:
            last_refill_idx = i
            break

    if last_refill_idx < 0:
        print("❌ Nem található feltöltés az elmúlt 10 napban")
        return

    refill_time = sample_times[last_refill_idx]
    refill_weight = sample_weights[last_refill_idx]

    print(f"\n🔄 LEGUTOLSÓ FELTÖLTÉS:")
    print(f"   Időpont: {refill_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Súly: {refill_weight:.0f} kg")

    # Feltöltés utáni adatok
    after_refill_times = sample_times[last_refill_idx:]
    after_refill_weights = sample_weights[last_refill_idx:]

    print(f"\n📊 Feltöltés utáni adatpontok: {len(after_refill_times)}")

    if len(after_refill_times) < 3:
        print("⚠️ Még nincs elég adat predikciós görbéhez (minimum 3 adatpont kell)")
        print("\nUtolsó mérések:")
        for t, w in zip(after_refill_times, after_refill_weights):
            print(f"   {t.strftime('%Y-%m-%d %H:%M')}: {w:.0f} kg")

        # Nyers adatok utolsó 10 mérése
        print("\nUtolsó 10 NYERS mérés:")
        for t, w in zip(timestamps[-10:], weights[-10:]):
            print(f"   {t.strftime('%Y-%m-%d %H:%M:%S')}: {w:.0f} kg")

        return

    # Folyamatos görbe (további feltöltések kiszűrésével)
    continuous_times = []
    continuous_weights = []
    base_adjustment = 0

    for i in range(len(after_refill_times)):
        t = after_refill_times[i]
        w = after_refill_weights[i]

        if i > 0:
            weight_change = w - after_refill_weights[i-1]
            if weight_change > 1000:
                base_adjustment -= weight_change
                print(f"   ⚠️ További feltöltés detektálva: {t.strftime('%Y-%m-%d %H:%M')}, +{weight_change:.0f} kg")

        adjusted_weight = w + base_adjustment
        continuous_times.append(t)
        continuous_weights.append(adjusted_weight)

    print(f"\n📉 Folyamatos fogyási görbe: {len(continuous_times)} adatpont")
    print("\nUtolsó 5 mérés (adjusztált):")
    for t, w in zip(continuous_times[-5:], continuous_weights[-5:]):
        print(f"   {t.strftime('%Y-%m-%d %H:%M')}: {w:.0f} kg")

    # Lineáris regresszió
    times_hours = np.array([(t - continuous_times[0]).total_seconds() / 3600 for t in continuous_times])
    weights_array = np.array(continuous_weights)

    slope, intercept, r_value, p_value, std_err = stats.linregress(times_hours, weights_array)

    print(f"\n📈 LINEÁRIS REGRESSZIÓ:")
    print(f"   Meredekség: {slope:.2f} kg/óra ({slope*24:.0f} kg/nap)")
    print(f"   R²: {r_value**2:.3f}")
    print(f"   Kezdő súly (illesztett): {intercept:.0f} kg")

    # Jelenlegi állapot
    current_weight = continuous_weights[-1]
    current_time = continuous_times[-1]

    print(f"\n🎯 JELENLEGI ÁLLAPOT:")
    print(f"   Időpont: {current_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Súly: {current_weight:.0f} kg")

    # Előrejelzés
    if slope < 0:
        hours_to_zero = -intercept / slope
        days_to_zero = hours_to_zero / 24
        zero_date = continuous_times[0] + timedelta(hours=hours_to_zero)

        hours_remaining = hours_to_zero - times_hours[-1]
        days_remaining = hours_remaining / 24

        formatted_prediction = format_prediction_time(zero_date)

        print(f"\n🎯 ELŐREJELZETT KIÜRÜLÉS:")
        print(f"   {formatted_prediction}")
        print(f"   (Pontos: {zero_date.strftime('%Y-%m-%d %H:%M')})")
        print(f"   Hátralévő idő: {days_remaining:.1f} nap ({hours_remaining:.1f} óra)")

        # Madárszám becslés
        daily_consumption_kg = abs(slope * 24)

        # Feltöltéstől eltelt napok
        days_since_refill = (current_time - refill_time).total_seconds() / 86400

        # Becsült nevelési nap (október 20 = 0. nap)
        oct20 = datetime(2025, 10, 20, 6, 0, tzinfo=refill_time.tzinfo)
        days_since_cycle_start = (current_time - oct20).total_seconds() / 86400
        bird_age_day = int(days_since_cycle_start)

        # Technológiai takarmány (g/madár/nap)
        tech_consumption_per_bird = 5 * bird_age_day

        if tech_consumption_per_bird > 0:
            estimated_birds = (daily_consumption_kg * 1000) / tech_consumption_per_bird

            print(f"\n🐔 MADÁRSZÁM BECSLÉS:")
            print(f"   Nevelési nap: {bird_age_day} (ciklus kezdet: {oct20.strftime('%Y-%m-%d')})")
            print(f"   Technológiai fogyasztás: {tech_consumption_per_bird:.0f} g/madár/nap")
            print(f"   Tényleges fogyasztás: {daily_consumption_kg:.0f} kg/nap")
            print(f"   🐔 Becsült madárszám: {estimated_birds:,.0f} db")

    else:
        print("\n⚠️ Nincs fogyás (növekvő vagy stagnáló súly)")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
