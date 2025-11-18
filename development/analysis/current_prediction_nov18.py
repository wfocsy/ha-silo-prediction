#!/usr/bin/env python3
"""
November 18-i feltöltés utáni predikció
"""
import csv
import numpy as np
from datetime import datetime, timedelta
from scipy import stats

def load_csv_data():
    """CSV betöltése"""
    data = []
    with open("/data/Blokkhistory3_4.csv", "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                state = row['state']
                if state in ['unavailable', 'unknown', '']:
                    continue
                weight = float(state)
                timestamp = datetime.fromisoformat(row['last_changed'].replace('Z', '+00:00'))
                data.append((timestamp, weight))
            except:
                continue
    return data

def resample_6hourly(data):
    """6 órás mintavételezés"""
    if len(data) == 0:
        return []

    timestamps = np.array([t for t, w in data])
    weights = np.array([w for t, w in data])

    start_time = timestamps[0]
    end_time = timestamps[-1]

    current = start_time.replace(hour=(start_time.hour // 6) * 6, minute=0, second=0, microsecond=0)
    sample_data = []

    while current <= end_time:
        window_start = current - timedelta(hours=3)
        window_end = current + timedelta(hours=3)

        mask = (timestamps >= window_start) & (timestamps <= window_end)
        if np.any(mask):
            avg_weight = np.mean(weights[mask])
            sample_data.append((current, avg_weight))

        current += timedelta(hours=6)

    return sample_data

def format_prediction_time(prediction_datetime):
    """Emberi olvasható dátum formátum"""
    from datetime import datetime
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

    # 2 órás intervallum
    hour_start = (pred_hour // 2) * 2
    hour_end = hour_start + 2

    formatted = f"{date_str} {hour_start:02d}-{hour_end:02d} óra között (~{pred_hour:02d}:{pred_minute:02d})"

    return formatted

def main():
    print("🎯 NOVEMBER 18-I FELTÖLTÉS UTÁNI PREDIKCIÓ")
    print("=" * 80)

    # CSV betöltése
    data = load_csv_data()
    print(f"✅ {len(data)} rekord betöltve")
    print(f"📅 Időszak: {data[0][0].strftime('%Y-%m-%d')} - {data[-1][0].strftime('%Y-%m-%d')}")

    # 6 órás mintavételezés
    sampled = resample_6hourly(data)
    print(f"📈 {len(sampled)} mintavételezett adatpont (6 óránként)")

    # November 18 utáni adatok keresése
    nov18_12 = datetime(2025, 11, 18, 12, 0, tzinfo=sampled[0][0].tzinfo)

    # Legutolsó nagy feltöltés keresése
    last_refill_idx = -1
    for i in range(len(sampled) - 1, 0, -1):
        weight_change = sampled[i][1] - sampled[i-1][1]
        if weight_change > 3000:  # Nagy feltöltés
            last_refill_idx = i
            break

    if last_refill_idx < 0:
        print("❌ Nem található feltöltés")
        return

    refill_time = sampled[last_refill_idx][0]
    refill_weight = sampled[last_refill_idx][1]

    print(f"\n🔄 LEGUTOLSÓ FELTÖLTÉS:")
    print(f"   Időpont: {refill_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Súly: {refill_weight:.0f} kg")

    # Feltöltés utáni adatok
    after_refill = sampled[last_refill_idx:]

    print(f"\n📊 Feltöltés utáni adatpontok: {len(after_refill)}")

    if len(after_refill) < 3:
        print("⚠️ Még nincs elég adat predikciós görbéhez (minimum 3 adatpont kell)")
        print("\nUtolsó mérések:")
        for t, w in after_refill:
            print(f"   {t.strftime('%Y-%m-%d %H:%M')}: {w:.0f} kg")
        return

    # Folyamatos görbe készítése (további feltöltések kiszűrésével)
    continuous_data = []
    base_adjustment = 0

    for i, (t, w) in enumerate(after_refill):
        if i > 0:
            weight_change = w - after_refill[i-1][1]
            if weight_change > 1000:
                base_adjustment -= weight_change
                print(f"   ⚠️ Feltöltés detektálva: {t.strftime('%Y-%m-%d %H:%M')}, +{weight_change:.0f} kg")

        adjusted_weight = w + base_adjustment
        continuous_data.append((t, adjusted_weight))

    print(f"\n📉 Folyamatos fogyási görbe: {len(continuous_data)} adatpont")

    # Utolsó pár mérés
    print("\nUtolsó mérések:")
    for t, w in continuous_data[-5:]:
        print(f"   {t.strftime('%Y-%m-%d %H:%M')}: {w:.0f} kg")

    # Lineáris regresszió
    times = np.array([(t - continuous_data[0][0]).total_seconds() / 3600 for t, w in continuous_data])
    weights = np.array([w for t, w in continuous_data])

    slope, intercept, r_value, p_value, std_err = stats.linregress(times, weights)

    print(f"\n📈 LINEÁRIS REGRESSZIÓ:")
    print(f"   Meredekség: {slope:.2f} kg/óra ({slope*24:.0f} kg/nap)")
    print(f"   R²: {r_value**2:.3f}")
    print(f"   Kezdő súly (illesztett): {intercept:.0f} kg")

    # Jelenlegi súly
    current_weight = continuous_data[-1][1]
    current_time = continuous_data[-1][0]

    print(f"\n🎯 JELENLEGI ÁLLAPOT:")
    print(f"   Időpont: {current_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Súly: {current_weight:.0f} kg")

    # Előrejelzés
    if slope < 0:
        hours_to_zero = -intercept / slope
        days_to_zero = hours_to_zero / 24
        zero_date = continuous_data[0][0] + timedelta(hours=hours_to_zero)

        hours_remaining = hours_to_zero - times[-1]
        days_remaining = hours_remaining / 24

        formatted_prediction = format_prediction_time(zero_date)

        print(f"\n🎯 ELŐREJELZETT KIÜRÜLÉS:")
        print(f"   {formatted_prediction}")
        print(f"   (Pontos: {zero_date.strftime('%Y-%m-%d %H:%M')})")
        print(f"   Hátralévő idő: {days_remaining:.1f} nap ({hours_remaining:.1f} óra)")

        # Napi fogyasztás technológiai adatokkal
        print(f"\n🐔 MADÁRSZÁM BECSLÉS:")

        # Feltöltéstől eltelt napok
        days_since_refill = (current_time - refill_time).total_seconds() / 86400

        # Becsült nevelési nap (feltételezzük ugyanaz a ciklus folytatódik)
        # Október 20 = 0. nap
        oct20 = datetime(2025, 10, 20, 6, 0, tzinfo=refill_time.tzinfo)
        days_since_cycle_start = (current_time - oct20).total_seconds() / 86400

        bird_age_day = int(days_since_cycle_start)

        # Technológiai takarmány fogyasztás (g/madár/nap)
        # Egyszerűsített: 5 g/nap/madár * nap szám
        tech_consumption_per_bird = 5 * bird_age_day  # g/madár/nap

        if tech_consumption_per_bird > 0:
            daily_consumption_kg = abs(slope * 24)
            estimated_birds = (daily_consumption_kg * 1000) / tech_consumption_per_bird

            print(f"   Nevelési nap: {bird_age_day} (ciklus kezdet: {oct20.strftime('%Y-%m-%d')})")
            print(f"   Technológiai fogyasztás: {tech_consumption_per_bird:.0f} g/madár/nap")
            print(f"   Tényleges fogyasztás: {daily_consumption_kg:.0f} kg/nap")
            print(f"   🐔 Becsült madárszám: {estimated_birds:,.0f} db")

    else:
        print("\n⚠️ Nincs fogyás (növekvő vagy stagnáló súly)")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
