#!/usr/bin/env python3
"""
Ciklus detektálás tesztelése CSV adatokkal (mintha History API lenne)
"""
import csv
from datetime import datetime
import numpy as np

def load_csv_as_history():
    """CSV betöltése History API formátumban"""
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
    print(f"📅 Időszak: {data[0][0].strftime('%Y-%m-%d')} - {data[-1][0].strftime('%Y-%m-%d')}")
    return data

def resample_6hourly(data):
    """6 órás mintavételezés"""
    if len(data) == 0:
        return []

    timestamps = np.array([t for t, w in data])
    weights = np.array([w for t, w in data])

    start_time = timestamps[0]
    end_time = timestamps[-1]

    from datetime import timedelta
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

    print(f"📈 {len(sample_data)} mintavételezett adatpont (6 óránként)")
    return sample_data

def detect_cycle_start(data):
    """
    Ciklus kezdet detektálása (az addon logikája)
    """
    print("\n" + "=" * 80)
    print("🎯 CIKLUS KEZDET DETEKTÁLÁSA")
    print("=" * 80)

    if len(data) < 7:
        print("❌ Nincs elég adat (minimum 7 nap)")
        return None

    first_refill_index = -1

    # 1. ELSŐDLEGES: Csend periódus + első feltöltés keresése
    print("\n1️⃣ ELSŐDLEGES MÓDSZER: Csend periódus keresése")
    print("-" * 80)

    for i in range(5, len(data)):
        # Előző 5 nap vizsgálata (csend periódus?)
        silence_period = True
        silence_weights = []

        for j in range(i - 5, i):
            weight = data[j][1]
            silence_weights.append(weight)

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
                avg_silence = np.mean(silence_weights)
                print(f"✅ Csend periódus detektálva:")
                print(f"   Időszak: {data[i-5][0].strftime('%Y-%m-%d')} - {data[i-1][0].strftime('%Y-%m-%d')}")
                print(f"   Átlag súly: {avg_silence:.0f} kg (< 1000 kg)")
                print(f"\n✅ ELSŐ FELTÖLTÉS (csend után):")
                print(f"   Dátum: {data[i][0].strftime('%Y-%m-%d %H:%M')}")
                print(f"   Feltöltés: +{weight_change:.0f} kg ({data[i-1][1]:.0f} -> {data[i][1]:.0f} kg)")
                break

    # 2. FALLBACK: Nagy feltöltés (5000kg+)
    if first_refill_index < 0:
        print("⚠️ Csend periódus nem található")
        print("\n2️⃣ FALLBACK MÓDSZER: Nagy feltöltés keresése (5000kg+)")
        print("-" * 80)

        for i in range(1, len(data)):
            weight_change = data[i][1] - data[i-1][1]

            if weight_change > 5000:
                first_refill_index = i
                print(f"✅ NAGY FELTÖLTÉS detektálva:")
                print(f"   Dátum: {data[i][0].strftime('%Y-%m-%d %H:%M')}")
                print(f"   Feltöltés: +{weight_change:.0f} kg ({data[i-1][1]:.0f} -> {data[i][1]:.0f} kg)")
                break

    if first_refill_index < 0:
        print("❌ Nem található ciklus kezdő feltöltés")
        return None

    # 3. 0. nap keresése: Első 100kg+ fogyasztás feltöltés után
    print("\n3️⃣ 0. NAP KERESÉSE (100kg+ napi fogyasztás)")
    print("-" * 80)

    for i in range(first_refill_index + 1, min(first_refill_index + 50, len(data))):
        prev_day_weight = data[i - 1][1]
        current_weight = data[i][1]
        daily_consumption = prev_day_weight - current_weight

        if daily_consumption > 100:
            cycle_start = data[i][0]
            print(f"✅ 0. NAP DETEKTÁLVA:")
            print(f"   Dátum: {cycle_start.strftime('%Y-%m-%d %H:%M')}")
            print(f"   Napi fogyasztás: {daily_consumption:.0f} kg")
            print(f"   Súly: {prev_day_weight:.0f} -> {current_weight:.0f} kg")
            return cycle_start, first_refill_index, i

    print("⚠️ 0. nap nem található (nincs 100kg+ fogyasztás)")
    return None

def analyze_cycle_data(data, cycle_start_info):
    """Ciklus adatok elemzése"""
    if cycle_start_info is None:
        return

    cycle_start, refill_idx, day0_idx = cycle_start_info

    print("\n" + "=" * 80)
    print("📊 CIKLUS ADATOK ELEMZÉSE")
    print("=" * 80)

    # Adatok day0 után
    cycle_data = data[day0_idx:]

    # Folyamatos görbe készítése (feltöltések nélkül)
    continuous_data = []
    base_adjustment = 0

    for i, (t, w) in enumerate(cycle_data):
        if i > 0:
            weight_change = w - cycle_data[i-1][1]
            # Ha feltöltés (>1000 kg növekedés), adjusztáljuk
            if weight_change > 1000:
                base_adjustment -= weight_change
                print(f"   Feltöltés detektálva: {t.strftime('%Y-%m-%d %H:%M')}, +{weight_change:.0f} kg")

        adjusted_weight = w + base_adjustment
        continuous_data.append((t, adjusted_weight))

    print(f"\n📉 Fogyási trend elemzése:")
    print(f"   Adatpontok: {len(continuous_data)}")
    print(f"   Kezdő súly: {continuous_data[0][1]:.0f} kg")
    print(f"   Jelenlegi súly: {continuous_data[-1][1]:.0f} kg")
    print(f"   Időtartam: {(continuous_data[-1][0] - continuous_data[0][0]).days} nap")

    # Lineáris regresszió
    from scipy import stats

    times = np.array([(t - continuous_data[0][0]).total_seconds() / 3600 for t, w in continuous_data])
    weights = np.array([w for t, w in continuous_data])

    slope, intercept, r_value, p_value, std_err = stats.linregress(times, weights)

    print(f"\n📈 Lineáris regresszió:")
    print(f"   Meredekség: {slope:.2f} kg/óra")
    print(f"   R²: {r_value**2:.3f}")
    print(f"   Kezdő súly (illesztett): {intercept:.0f} kg")

    # 0 kg előrejelzés
    if slope < 0:
        from datetime import timedelta
        hours_to_zero = -intercept / slope
        days_to_zero = hours_to_zero / 24
        zero_date = continuous_data[0][0] + timedelta(hours=hours_to_zero)

        print(f"\n🎯 ELŐREJELZÉS:")
        print(f"   0 kg várható: {zero_date.strftime('%Y-%m-%d %H:%M')}")
        print(f"   Hátralévő idő: {days_to_zero:.1f} nap")

def main():
    print("🧪 CIKLUS DETEKTÁLÁS TESZT - CSV ADATOKKAL")
    print("=" * 80)
    print()

    # CSV betöltése
    data = load_csv_as_history()

    # Csak október 13 - november 15 közötti adatok (a teljes első ciklus)
    from datetime import datetime
    oct13 = datetime(2025, 10, 13, tzinfo=data[0][0].tzinfo)
    nov15 = datetime(2025, 11, 15, tzinfo=data[0][0].tzinfo)

    filtered_data = [(t, w) for t, w in data if oct13 <= t <= nov15]
    print(f"\n📅 Szűrt időszak: {filtered_data[0][0].strftime('%Y-%m-%d')} - {filtered_data[-1][0].strftime('%Y-%m-%d')}")
    print(f"📊 Rekordok: {len(filtered_data)}")

    # 6 órás mintavételezés
    sampled_data = resample_6hourly(filtered_data)

    # Ciklus detektálás
    result = detect_cycle_start(sampled_data)

    # Elemzés
    if result:
        from datetime import timedelta
        analyze_cycle_data(sampled_data, result)

    print("\n" + "=" * 80)
    print("✅ TESZT BEFEJEZVE")
    print("=" * 80)

if __name__ == "__main__":
    main()
