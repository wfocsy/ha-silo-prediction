#!/usr/bin/env python3
"""
ÚJ EXPONENCIÁLIS PREDIKCIÓS MÓDSZER - PROTOTÍPUS
Tesztelés CSV adatokkal
"""
import csv
import numpy as np
from datetime import datetime, timedelta
from scipy import stats

# Technológiai takarmány adatok (g/madár/nap)
TECH_FEED_DATA = {
    0: 0, 1: 0, 2: 16, 3: 20, 4: 24, 5: 27, 6: 31, 7: 35, 8: 39, 9: 44,
    10: 48, 11: 52, 12: 57, 13: 62, 14: 67, 15: 72, 16: 77, 17: 83, 18: 88, 19: 94,
    20: 100, 21: 105, 22: 111, 23: 117, 24: 122, 25: 128, 26: 134, 27: 139, 28: 145, 29: 150,
    30: 156, 31: 161, 32: 166, 33: 171, 34: 176, 35: 180, 36: 185, 37: 189, 38: 193, 39: 197,
    40: 201, 41: 204, 42: 207, 43: 211, 44: 213, 45: 216, 46: 219, 47: 221, 48: 223, 49: 225,
    50: 227
}

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
    print(f"📅 Időszak: {data[0][0].strftime('%Y-%m-%d')} - {data[-1][0].strftime('%Y-%m-%d')}")
    return data

def resample_6hourly(data):
    """6 órás mintavételezés (predikciós görbe számításhoz)"""
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

    print(f"📈 {len(sample_data)} mintavételezett adatpont (6 óránként)")
    return sample_data

def create_normalized_curve(data_6h):
    """
    NORMALIZÁLT GÖRBE KÉSZÍTÉSE - Feltöltések kivonásával

    Ez a görbe mutatja a folyamatos fogyást, mintha nem lennének feltöltések.
    A súly lehet NEGATÍV is, ez rendben van!
    """
    print("\n" + "=" * 80)
    print("📉 NORMALIZÁLT GÖRBE KÉSZÍTÉSE (feltöltések kivonásával)")
    print("=" * 80)

    normalized = []
    cumulative_refill = 0  # Összes feltöltés amit kivontunk

    for i, (timestamp, weight) in enumerate(data_6h):
        # Feltöltés detektálás
        if i > 0:
            prev_weight = data_6h[i-1][1]
            weight_change = weight - prev_weight

            # Ha feltöltés (+3000 kg), kivonjuk
            if weight_change > 3000:
                cumulative_refill += weight_change
                print(f"   🔄 Feltöltés detektálva: {timestamp.strftime('%Y-%m-%d %H:%M')}, "
                      f"+{weight_change:.0f} kg → kumulatív: {cumulative_refill:.0f} kg")

        # Normalizált súly = valós súly - összes feltöltés
        normalized_weight = weight - cumulative_refill
        normalized.append((timestamp, normalized_weight))

    print(f"\n✅ Normalizált görbe: {len(normalized)} adatpont")
    print(f"   Kezdő súly: {normalized[0][1]:.0f} kg")
    print(f"   Végső súly: {normalized[-1][1]:.0f} kg (lehet negatív!)")
    print(f"   Összes kivont feltöltés: {cumulative_refill:.0f} kg")

    return normalized

def calculate_exp_constant(normalized_curve):
    """
    EXPONENCIÁLIS ÁLLANDÓ SZÁMÍTÁSA - Csak történelmi adatokból!

    Méri, hogy mennyire gyorsul a fogyás az idő múlásával.

    Módszer:
    - Napi fogyási sebességek számítása
    - Exponenciális vagy lineáris illesztés a sebességekre
    - Visszaadja a gyorsulási faktort
    """
    print("\n" + "=" * 80)
    print("🧮 EXPONENCIÁLIS ÁLLANDÓ SZÁMÍTÁSA")
    print("=" * 80)

    if len(normalized_curve) < 8:  # Minimum 2 nap x 4 adatpont
        print("❌ Nincs elég adat (min 8 adatpont kell)")
        return 1.0

    # Napi fogyási ráták számítása (24 órás ablakokból = 4 adatpont)
    daily_rates = []
    daily_timestamps = []

    # 6 óránként 4 adatpont = 24 óra
    for i in range(4, len(normalized_curve)):
        # 24 órás ablak
        prev_time, prev_weight = normalized_curve[i-4]
        curr_time, curr_weight = normalized_curve[i]

        # Napi fogyás (24 óra)
        daily_consumption = prev_weight - curr_weight

        # Pozitív fogyás (abszolút érték, mert a normalizált görbe lehet negatív!)
        if daily_consumption < 0:
            daily_consumption = abs(daily_consumption)

        if daily_consumption > 10:  # Min 10 kg/nap
            daily_rates.append(daily_consumption)
            daily_timestamps.append(curr_time)

    if len(daily_rates) < 2:
        print("❌ Nincs elég napi fogyási adat")
        return 1.0

    print(f"\n📊 Napi fogyási ráták ({len(daily_rates)} nap):")
    print(f"   Min: {min(daily_rates):.0f} kg/nap")
    print(f"   Max: {max(daily_rates):.0f} kg/nap")
    print(f"   Átlag: {np.mean(daily_rates):.0f} kg/nap")

    # Exponenciális illesztés
    days = np.arange(len(daily_rates))
    rates = np.array(daily_rates)

    # Lineáris regresszió a fogyási rátákra (mennyi a gyorsulás?)
    slope, intercept, r_value, p_value, std_err = stats.linregress(days, rates)

    print(f"\n📈 Fogyási ráta trend:")
    print(f"   Kezdő ráta: {intercept:.0f} kg/nap")
    print(f"   Gyorsulás: {slope:.2f} kg/nap²")
    print(f"   R²: {r_value**2:.3f}")

    # Exponenciális faktor: mennyivel nő a fogyás naponta
    # exp_factor = 1 + (gyorsulás / átlag_ráta)
    avg_rate = np.mean(daily_rates)
    exp_constant = slope / avg_rate if avg_rate > 0 else 0.0

    print(f"\n🎯 EXPONENCIÁLIS ÁLLANDÓ: {exp_constant:.6f}")
    print(f"   (Relatív gyorsulás naponta)")

    return exp_constant, intercept, slope

def detect_cycle_start(data_6h):
    """0. nap detektálása (mint az addonban)"""
    print("\n" + "=" * 80)
    print("🔍 0. NAP DETEKTÁLÁSA")
    print("=" * 80)

    if len(data_6h) < 7:
        print("❌ Nincs elég adat")
        return None, None

    first_refill_index = -1

    # 1. ELSŐDLEGES: Csend periódus keresése
    for i in range(5, len(data_6h)):
        silence_period = True
        for j in range(i - 5, i):
            weight = data_6h[j][1]
            if weight > 1000:
                silence_period = False
                break
            if j > 0:
                daily_change = abs(data_6h[j][1] - data_6h[j-1][1])
                if daily_change > 50:
                    silence_period = False
                    break

        if silence_period and i < len(data_6h):
            weight_change = data_6h[i][1] - data_6h[i-1][1]
            if weight_change > 3000:
                first_refill_index = i
                print(f"✅ Csend periódus + első feltöltés: {data_6h[i][0].strftime('%Y-%m-%d')}")
                break

    # 2. FALLBACK: Nagy feltöltés (5000kg+)
    if first_refill_index < 0:
        print("⚠️ Csend periódus nem található, fallback...")
        for i in range(1, len(data_6h)):
            weight_change = data_6h[i][1] - data_6h[i-1][1]
            if weight_change > 5000:
                first_refill_index = i
                print(f"✅ Nagy feltöltés: {data_6h[i][0].strftime('%Y-%m-%d')}, +{weight_change:.0f} kg")
                break

    if first_refill_index < 0:
        print("❌ Nem található ciklus kezdet")
        return None, None

    # 3. 0. nap keresése (100kg+ fogyasztás)
    for i in range(first_refill_index + 1, len(data_6h)):
        prev_weight = data_6h[i - 1][1]
        curr_weight = data_6h[i][1]
        daily_consumption = prev_weight - curr_weight

        if daily_consumption > 100:
            cycle_start = data_6h[i][0]
            print(f"🐣 0. NAP: {cycle_start.strftime('%Y-%m-%d')}, fogyasztás: {daily_consumption:.0f} kg")
            return cycle_start, first_refill_index

    print("⚠️ 0. nap nem található")
    return None, first_refill_index

def calculate_bird_count(normalized_curve, cycle_start):
    """Madárszám becslés (mint az addonban)"""
    print("\n" + "=" * 80)
    print("🐔 MADÁRSZÁM BECSLÉS")
    print("=" * 80)

    bird_counts = []

    # Minden adatpont (nem csak 7:00-as) a ciklus után
    cycle_data = [(t, w) for t, w in normalized_curve if t >= cycle_start]

    if len(cycle_data) < 8:  # Min 2 nap x 4 adatpont
        print("❌ Nincs elég adat")
        return None

    # 6 óránkénti fogyások vizsgálata
    for i in range(4, len(cycle_data)):  # Napi 4 adatpont -> 24 óra
        # Előző 24 óra (4 adatpont) összesített fogyása
        day_start_idx = i - 4
        prev_weight = cycle_data[day_start_idx][1]
        curr_weight = cycle_data[i][1]

        daily_consumption_kg = prev_weight - curr_weight

        if daily_consumption_kg < 10:  # Min 10 kg/nap
            continue

        # Nevelési nap
        days_since_start = (cycle_data[i][0] - cycle_start).days

        # Tech adat
        tech_per_bird = TECH_FEED_DATA.get(days_since_start, 150)

        if tech_per_bird <= 0:
            continue

        # Madárszám
        bird_count = int((daily_consumption_kg * 1000) / tech_per_bird)

        if bird_count > 0 and bird_count < 100000:  # Ésszerű tartomány
            bird_counts.append(bird_count)

            # Debug első 5
            if len(bird_counts) <= 5:
                print(f"   {days_since_start}. nap: {daily_consumption_kg:.0f} kg fogyás, "
                      f"{tech_per_bird} g/madár → {bird_count} madár")

    if not bird_counts:
        print("❌ Nincs madárszám adat")
        return None

    avg_birds = int(np.mean(bird_counts))
    print(f"\n✅ Madárszám: {min(bird_counts)}-{max(bird_counts)} (átlag: {avg_birds})")

    return avg_birds

def predict_with_tech_data(current_real_weight, cycle_start, bird_count, exp_constant, base_rate, acceleration):
    """
    MÓDSZER 1: Tech adat + Exp állandó (VAN 0. nap)
    """
    print("\n" + "=" * 80)
    print("🎯 PREDIKCIÓ - TECH ADAT + EXP ÁLLANDÓ")
    print("=" * 80)

    now = datetime.now(cycle_start.tzinfo)
    current_day = (now - cycle_start).days

    print(f"📊 Bemenet:")
    print(f"   Jelenlegi súly: {current_real_weight:.0f} kg")
    print(f"   Nevelési nap: {current_day}")
    print(f"   Madárszám: {bird_count}")
    print(f"   Exp állandó: {exp_constant:.6f}")
    print(f"   Alap ráta: {base_rate:.2f} kg/nap")
    print(f"   Gyorsulás: {acceleration:.2f} kg/nap²")

    # Iteratív szimuláció
    weight = current_real_weight
    day = current_day
    hours = 0
    max_days = 60

    print(f"\n🔄 Szimuláció indítása...")

    while weight > 0 and day < current_day + max_days:
        # Tech napi fogyasztás
        tech_per_bird = TECH_FEED_DATA.get(day, 227)  # Max 227 g/nap
        tech_daily_kg = (tech_per_bird * bird_count) / 1000

        # Exponenciális korrekció alkalmazása
        # Aktuális ráta = alap ráta + gyorsulás * napok száma
        days_elapsed = day - current_day
        current_rate = base_rate + (acceleration * days_elapsed)

        # Korrekciós faktor
        exp_factor = current_rate / base_rate if base_rate > 0 else 1.0

        # Tényleges napi fogyasztás
        actual_daily_kg = tech_daily_kg * exp_factor

        # Óránkénti fogyasztás
        hourly_kg = actual_daily_kg / 24

        # Súly csökkentése
        weight -= hourly_kg
        hours += 1

        # Nap váltás
        if hours % 24 == 0:
            day += 1

            # Debug minden 7. nap
            if day % 7 == 0:
                print(f"   {day}. nap: súly={weight:.0f} kg, "
                      f"tech={tech_daily_kg:.0f} kg/nap, "
                      f"actual={actual_daily_kg:.0f} kg/nap "
                      f"(×{exp_factor:.2f})")

    prediction_datetime = now + timedelta(hours=hours)
    days_until = hours / 24

    print(f"\n✅ EREDMÉNY:")
    print(f"   Kiürülés: {prediction_datetime.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Hátralévő idő: {days_until:.1f} nap")

    return prediction_datetime, days_until

def predict_with_exp_only(current_real_weight, normalized_curve, exp_constant, base_rate, acceleration):
    """
    MÓDSZER 2: Csak Exp állandó (NINCS 0. nap) - Fallback
    """
    print("\n" + "=" * 80)
    print("⚠️ PREDIKCIÓ - CSAK EXP ÁLLANDÓ (FALLBACK)")
    print("=" * 80)

    print(f"📊 Bemenet:")
    print(f"   Jelenlegi súly: {current_real_weight:.0f} kg")
    print(f"   Exp állandó: {exp_constant:.6f}")
    print(f"   Alap ráta: {base_rate:.2f} kg/nap")
    print(f"   Gyorsulás: {acceleration:.2f} kg/nap²")

    # Egyszerű lineáris extrapoláció gyorsulással
    weight = current_real_weight
    current_rate = base_rate
    hours = 0

    print(f"\n🔄 Szimuláció (gyorsuló lineáris)...")

    while weight > 0 and hours < 60 * 24:  # Max 60 nap
        # Napi ráta növekszik
        daily_kg = current_rate
        hourly_kg = daily_kg / 24

        weight -= hourly_kg
        hours += 1

        # Ráta növelése naponta
        if hours % 24 == 0:
            current_rate += acceleration

    now = datetime.now(normalized_curve[0][0].tzinfo)
    prediction_datetime = now + timedelta(hours=hours)
    days_until = hours / 24

    print(f"\n✅ EREDMÉNY:")
    print(f"   Kiürülés: {prediction_datetime.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Hátralévő idő: {days_until:.1f} nap")

    return prediction_datetime, days_until

def main():
    print("🧪 EXPONENCIÁLIS PREDIKCIÓS MÓDSZER - TESZT")
    print("=" * 80)
    print()

    # 1. CSV betöltése
    data = load_csv_data()

    # 2. 6 órás mintavételezés
    data_6h = resample_6hourly(data)

    # 3. Normalizált görbe (feltöltések kivonásával)
    normalized = create_normalized_curve(data_6h)

    # 4. Exponenciális állandó számítása
    exp_constant, base_rate, acceleration = calculate_exp_constant(normalized)

    # 5. 0. nap detektálása
    cycle_start, refill_idx = detect_cycle_start(data_6h)

    # 6. Jelenlegi valós súly
    current_real_weight = data_6h[-1][1]

    # 7. PREDIKCIÓ
    if cycle_start is not None:
        # ✅ VAN 0. NAP → Tech adat + Exp
        bird_count = calculate_bird_count(normalized, cycle_start)

        if bird_count:
            predict_with_tech_data(
                current_real_weight=current_real_weight,
                cycle_start=cycle_start,
                bird_count=bird_count,
                exp_constant=exp_constant,
                base_rate=base_rate,
                acceleration=acceleration
            )
        else:
            print("\n⚠️ Nincs madárszám → Fallback módszer")
            predict_with_exp_only(
                current_real_weight=current_real_weight,
                normalized_curve=normalized,
                exp_constant=exp_constant,
                base_rate=base_rate,
                acceleration=acceleration
            )
    else:
        # ❌ NINCS 0. NAP → Csak Exp
        predict_with_exp_only(
            current_real_weight=current_real_weight,
            normalized_curve=normalized,
            exp_constant=exp_constant,
            base_rate=base_rate,
            acceleration=acceleration
        )

    print("\n" + "=" * 80)
    print("✅ TESZT BEFEJEZVE")
    print("=" * 80)

if __name__ == "__main__":
    main()
