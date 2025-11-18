#!/usr/bin/env python3
"""
TECH ADAT KORRELÁCIÓ ELEMZÉSE

Összehasonlítjuk a tech adatok alapján várható fogyást
a valós mért fogyással.

Cél: Megállapítani, mennyire pontosak a tech adatok.
"""
import csv
import numpy as np
from datetime import datetime, timedelta

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
    """Normalizált görbe (feltöltések nélkül)"""
    normalized = []
    cumulative_refill = 0

    for i, (timestamp, weight) in enumerate(data_6h):
        if i > 0:
            weight_change = weight - data_6h[i-1][1]
            if weight_change > 3000:
                cumulative_refill += weight_change

        normalized_weight = weight - cumulative_refill
        normalized.append((timestamp, normalized_weight))

    return normalized

def analyze_tech_correlation(normalized_curve, cycle_start, bird_count):
    """
    Tech adat vs valós fogyás korreláció elemzése
    """
    print("\n" + "=" * 80)
    print("🔬 TECH ADAT KORRELÁCIÓ ELEMZÉSE")
    print("=" * 80)
    print(f"\n📊 Paraméterek:")
    print(f"   Ciklus kezdet: {cycle_start.strftime('%Y-%m-%d')}")
    print(f"   Madárszám: {bird_count:,}")

    # Ciklus utáni adatok
    cycle_data = [(t, w) for t, w in normalized_curve if t >= cycle_start]

    if len(cycle_data) < 8:
        print("❌ Nincs elég adat")
        return

    # Napi összehasonlítás
    results = []

    for i in range(4, len(cycle_data)):  # 4 adatpont = 24 óra
        # 24 órás ablak
        prev_time, prev_weight = cycle_data[i-4]
        curr_time, curr_weight = cycle_data[i]

        # Valós napi fogyás
        actual_daily_kg = prev_weight - curr_weight

        if actual_daily_kg < 10:  # Minimum fogyás
            continue

        # Nevelési nap
        day = (curr_time - cycle_start).days

        # Tech adat alapján várható fogyás
        tech_per_bird_g = TECH_FEED_DATA.get(day, 150)
        tech_daily_kg = (tech_per_bird_g * bird_count) / 1000

        # Eltérés
        difference_kg = actual_daily_kg - tech_daily_kg
        difference_percent = (difference_kg / tech_daily_kg) * 100 if tech_daily_kg > 0 else 0

        results.append({
            'day': day,
            'date': curr_time,
            'actual_kg': actual_daily_kg,
            'tech_kg': tech_daily_kg,
            'diff_kg': difference_kg,
            'diff_percent': difference_percent
        })

    if not results:
        print("❌ Nincs összehasonlítható adat")
        return

    # Statisztikák
    actual_values = [r['actual_kg'] for r in results]
    tech_values = [r['tech_kg'] for r in results]
    diff_values = [r['diff_kg'] for r in results]
    diff_percent_values = [r['diff_percent'] for r in results]

    print(f"\n📈 ÖSSZESÍTETT STATISZTIKÁK ({len(results)} nap):")
    print("-" * 80)
    print(f"\n  VALÓS FOGYÁS:")
    print(f"    Átlag: {np.mean(actual_values):.0f} kg/nap")
    print(f"    Min:   {np.min(actual_values):.0f} kg/nap ({results[np.argmin(actual_values)]['day']}. nap)")
    print(f"    Max:   {np.max(actual_values):.0f} kg/nap ({results[np.argmax(actual_values)]['day']}. nap)")

    print(f"\n  TECH ALAPÚ VÁRHATÓ FOGYÁS:")
    print(f"    Átlag: {np.mean(tech_values):.0f} kg/nap")
    print(f"    Min:   {np.min(tech_values):.0f} kg/nap")
    print(f"    Max:   {np.max(tech_values):.0f} kg/nap")

    print(f"\n  ELTÉRÉS (Valós - Tech):")
    print(f"    Átlag: {np.mean(diff_values):+.0f} kg/nap ({np.mean(diff_percent_values):+.1f}%)")
    print(f"    Min:   {np.min(diff_values):+.0f} kg/nap ({np.min(diff_percent_values):+.1f}%)")
    print(f"    Max:   {np.max(diff_values):+.0f} kg/nap ({np.max(diff_percent_values):+.1f}%)")

    # Korreláció
    from scipy import stats as sp_stats
    correlation, p_value = sp_stats.pearsonr(actual_values, tech_values)

    print(f"\n  📊 KORRELÁCIÓ:")
    print(f"    Pearson r: {correlation:.3f}")
    print(f"    p-érték: {p_value:.6f}")

    if correlation > 0.9:
        print(f"    ✅ NAGYON ERŐ KORRELÁCIÓ!")
    elif correlation > 0.7:
        print(f"    ✅ ERŐ KORRELÁCIÓ!")
    elif correlation > 0.5:
        print(f"    ⚠️ KÖZEPES KORRELÁCIÓ")
    else:
        print(f"    ❌ GYENGE KORRELÁCIÓ")

    # Részletes lista (első 10 nap + utolsó 10 nap)
    print(f"\n📋 RÉSZLETES ÖSSZEHASONLÍTÁS:")
    print("-" * 80)
    print(f"{'Nap':<5} {'Dátum':<12} {'Valós':<10} {'Tech':<10} {'Eltérés':<15}")
    print("-" * 80)

    # Első 10
    for r in results[:10]:
        print(f"{r['day']:>3}. {r['date'].strftime('%m-%d'):<12} "
              f"{r['actual_kg']:>7.0f} kg  {r['tech_kg']:>7.0f} kg  "
              f"{r['diff_kg']:+7.0f} kg ({r['diff_percent']:+5.1f}%)")

    if len(results) > 20:
        print("  ...")

        # Utolsó 10
        for r in results[-10:]:
            print(f"{r['day']:>3}. {r['date'].strftime('%m-%d'):<12} "
                  f"{r['actual_kg']:>7.0f} kg  {r['tech_kg']:>7.0f} kg  "
                  f"{r['diff_kg']:+7.0f} kg ({r['diff_percent']:+5.1f}%)")

    # Következtetés
    print(f"\n💡 KÖVETKEZTETÉS:")
    print("-" * 80)

    avg_diff = np.mean(diff_values)
    avg_diff_pct = np.mean(diff_percent_values)

    if abs(avg_diff_pct) < 5:
        print(f"✅ A tech adatok KIVÁLÓAN illeszkednek a valós fogyáshoz!")
        print(f"   Átlagos eltérés: {avg_diff_pct:+.1f}% (< 5%)")
    elif abs(avg_diff_pct) < 10:
        print(f"✅ A tech adatok JÓL illeszkednek a valós fogyáshoz!")
        print(f"   Átlagos eltérés: {avg_diff_pct:+.1f}% (< 10%)")
    elif abs(avg_diff_pct) < 20:
        print(f"⚠️ A tech adatok ELFOGADHATÓAN illeszkednek a valós fogyáshoz.")
        print(f"   Átlagos eltérés: {avg_diff_pct:+.1f}% (< 20%)")
    else:
        print(f"❌ A tech adatok NEM illeszkednek jól a valós fogyáshoz!")
        print(f"   Átlagos eltérés: {avg_diff_pct:+.1f}% (> 20%)")

    if avg_diff > 0:
        print(f"\n   → A madarak TÖBBET esznek, mint a tech adat!")
        print(f"   → Korrekciós faktor: {1 + (avg_diff / np.mean(tech_values)):.3f}x")
    else:
        print(f"\n   → A madarak KEVESEBBET esznek, mint a tech adat!")
        print(f"   → Korrekciós faktor: {1 + (avg_diff / np.mean(tech_values)):.3f}x")

    return results

def main():
    print("🔬 TECH ADAT KORRELÁCIÓ ELEMZÉSE")
    print("=" * 80)
    print()

    # Adatok betöltése
    data = load_csv_data()
    data_6h = resample_6hourly(data)

    print(f"✅ {len(data)} rekord betöltve")
    print(f"📈 {len(data_6h)} mintavételezett adatpont (6 óránként)")

    # Normalizált görbe
    normalized = create_normalized_curve(data_6h)

    # 0. nap és madárszám (hard-coded a korábbi eredmények alapján)
    cycle_start = datetime(2025, 10, 20, 6, 0, tzinfo=data_6h[0][0].tzinfo)
    bird_count = 19524  # Korábbi számítás eredménye

    # Korreláció elemzése
    analyze_tech_correlation(normalized, cycle_start, bird_count)

    print("\n" + "=" * 80)
    print("✅ ELEMZÉS BEFEJEZVE")
    print("=" * 80)

if __name__ == "__main__":
    main()
