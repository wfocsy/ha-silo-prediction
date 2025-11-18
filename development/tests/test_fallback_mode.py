#!/usr/bin/env python3
"""
FALLBACK MÓDSZER TESZT - Nincs 0. nap (mint az élő rendszerben most)

Szimuláljuk, hogy csak November 8-tól vannak adataink (10 nap),
így NEM találjuk meg a 0. napot (csend periódus nincs).
"""
import csv
import numpy as np
from datetime import datetime, timedelta
from scipy import stats

def load_csv_data():
    """CSV betöltése"""
    print("=" * 80)
    print("📂 CSV BETÖLTÉSE")
    print("=" * 80)

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

    print(f"✅ {len(data)} rekord betöltve")
    print(f"📅 Teljes időszak: {data[0][0].strftime('%Y-%m-%d')} - {data[-1][0].strftime('%Y-%m-%d')}")
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

def create_normalized_curve(data_6h):
    """Normalizált görbe készítése (feltöltések kivonásával)"""
    print("\n" + "=" * 80)
    print("📉 NORMALIZÁLT GÖRBE KÉSZÍTÉSE")
    print("=" * 80)

    normalized = []
    cumulative_refill = 0

    for i, (timestamp, weight) in enumerate(data_6h):
        if i > 0:
            prev_weight = data_6h[i-1][1]
            weight_change = weight - prev_weight

            if weight_change > 3000:
                cumulative_refill += weight_change
                print(f"   🔄 Feltöltés: {timestamp.strftime('%Y-%m-%d %H:%M')}, +{weight_change:.0f} kg")

        normalized_weight = weight - cumulative_refill
        normalized.append((timestamp, normalized_weight))

    print(f"\n✅ Normalizált görbe: {len(normalized)} adatpont")
    print(f"   Kezdő: {normalized[0][1]:.0f} kg")
    print(f"   Végső: {normalized[-1][1]:.0f} kg")
    print(f"   Kivont feltöltés: {cumulative_refill:.0f} kg")

    return normalized

def calculate_exp_constant(normalized_curve):
    """Exponenciális állandó számítása"""
    print("\n" + "=" * 80)
    print("🧮 EXPONENCIÁLIS ÁLLANDÓ SZÁMÍTÁSA")
    print("=" * 80)

    if len(normalized_curve) < 8:
        print("❌ Nincs elég adat")
        return 1.0, 0.0, 0.0

    # Napi fogyási ráták
    daily_rates = []

    for i in range(4, len(normalized_curve)):  # 4 adatpont = 24 óra
        prev_weight = normalized_curve[i-4][1]
        curr_weight = normalized_curve[i][1]

        daily_consumption = prev_weight - curr_weight

        if daily_consumption > 10:  # Min 10 kg/nap
            daily_rates.append(daily_consumption)

    if len(daily_rates) < 2:
        print("❌ Nincs elég fogyási adat")
        return 1.0, 0.0, 0.0

    print(f"📊 Napi fogyási ráták ({len(daily_rates)} mérés):")
    print(f"   Min: {min(daily_rates):.0f} kg/nap")
    print(f"   Max: {max(daily_rates):.0f} kg/nap")
    print(f"   Átlag: {np.mean(daily_rates):.0f} kg/nap")

    # Lineáris regresszió a rátákra
    days = np.arange(len(daily_rates))
    rates = np.array(daily_rates)

    slope, intercept, r_value, p_value, std_err = stats.linregress(days, rates)

    print(f"\n📈 Trend:")
    print(f"   Kezdő ráta: {intercept:.0f} kg/nap")
    print(f"   Gyorsulás: {slope:.2f} kg/nap²")
    print(f"   R²: {r_value**2:.3f}")

    # Exponenciális faktor
    avg_rate = np.mean(daily_rates)
    exp_constant = slope / avg_rate if avg_rate > 0 else 0.0

    print(f"\n🎯 EXP ÁLLANDÓ: {exp_constant:.6f}")

    return exp_constant, intercept, slope

def predict_with_exp_only(current_real_weight, normalized_curve, base_rate, acceleration):
    """
    FALLBACK PREDIKCIÓ - Csak exponenciális állandó (NINCS 0. nap)

    Gyorsuló lineáris extrapoláció
    """
    print("\n" + "=" * 80)
    print("⚠️ PREDIKCIÓ - CSAK EXP ÁLLANDÓ (NINCS 0. NAP)")
    print("=" * 80)

    print(f"📊 Bemenet:")
    print(f"   Jelenlegi súly: {current_real_weight:.0f} kg")
    print(f"   Alap fogyási ráta: {base_rate:.2f} kg/nap")
    print(f"   Gyorsulás: {acceleration:.2f} kg/nap²")

    # Iteratív szimuláció gyorsuló lineáris trenddel
    weight = current_real_weight
    current_rate = base_rate
    hours = 0
    day = 0

    print(f"\n🔄 Szimuláció indítása...")

    while weight > 0 and hours < 60 * 24:  # Max 60 nap
        # Napi fogyasztás (folyamatosan nő)
        daily_kg = current_rate
        hourly_kg = daily_kg / 24

        weight -= hourly_kg
        hours += 1

        # Naponta növeljük a rátát
        if hours % 24 == 0:
            day += 1
            current_rate += acceleration

            # Debug minden 3. nap
            if day % 3 == 0:
                print(f"   {day}. nap: súly={weight:.0f} kg, ráta={daily_kg:.0f} kg/nap")

    now = datetime.now(normalized_curve[0][0].tzinfo)
    prediction_datetime = now + timedelta(hours=hours)
    days_until = hours / 24

    print(f"\n✅ EREDMÉNY:")
    print(f"   Kiürülés: {prediction_datetime.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Hátralévő idő: {days_until:.1f} nap ({hours:.0f} óra)")

    return prediction_datetime, days_until

def main():
    print("🧪 FALLBACK MÓDSZER TESZT - NINCS 0. NAP")
    print("=" * 80)
    print("Szimulálva: Csak november 8-tól van adat (10 nap)")
    print()

    # 1. Teljes CSV betöltése
    all_data = load_csv_data()

    # 2. SZIMULÁCIÓ: Csak November 8-tól (mint az élő rendszer most!)
    nov8 = datetime(2025, 11, 8, tzinfo=all_data[0][0].tzinfo)
    filtered_data = [(t, w) for t, w in all_data if t >= nov8]

    print(f"\n⚠️ SZŰRÉS: Csak nov 8-tól")
    print(f"   Adatok: {len(filtered_data)} rekord")
    print(f"   Időszak: {filtered_data[0][0].strftime('%Y-%m-%d')} - {filtered_data[-1][0].strftime('%Y-%m-%d')}")

    # 3. 6 órás mintavételezés
    data_6h = resample_6hourly(filtered_data)
    print(f"   6 órás: {len(data_6h)} adatpont")

    # 4. Normalizált görbe
    normalized = create_normalized_curve(data_6h)

    # 5. Exponenciális állandó
    exp_constant, base_rate, acceleration = calculate_exp_constant(normalized)

    # 6. 0. nap detektálás próba
    print("\n" + "=" * 80)
    print("🔍 0. NAP DETEKTÁLÁS PRÓBA")
    print("=" * 80)

    # Csend periódus keresése
    found_silence = False
    if len(data_6h) >= 7:
        for i in range(5, len(data_6h)):
            silence = True
            for j in range(i - 5, i):
                if data_6h[j][1] > 1000:
                    silence = False
                    break
            if silence:
                found_silence = True
                print(f"✅ Csend periódus: {data_6h[i-5][0].strftime('%Y-%m-%d')} - {data_6h[i-1][0].strftime('%Y-%m-%d')}")
                break

    if not found_silence:
        print("❌ NINCS csend periódus (csak 10 nap adat!)")
        print("   → FALLBACK módszer használata")

    # 7. Jelenlegi valós súly
    current_real_weight = data_6h[-1][1]

    # 8. FALLBACK PREDIKCIÓ (nincs 0. nap)
    predict_with_exp_only(
        current_real_weight=current_real_weight,
        normalized_curve=normalized,
        base_rate=base_rate,
        acceleration=acceleration
    )

    # 9. Összehasonlítás a jelenlegi trenddel
    print("\n" + "=" * 80)
    print("📊 ÖSSZEHASONLÍTÁS A JELENLEGI TRENDDEL")
    print("=" * 80)
    print()
    print("Jelenlegi trend (3h mérés):     Nov 21, 14:17 (2.7 nap)")
    print("Exponenciális prototípus:       Nov 20, 15:31 (1.8 nap)")
    print("FALLBACK módszer (fenti):       Lásd fent")

    print("\n" + "=" * 80)
    print("✅ TESZT BEFEJEZVE")
    print("=" * 80)

if __name__ == "__main__":
    main()
