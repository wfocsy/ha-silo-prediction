#!/usr/bin/env python3
"""
Predikciós pontosság validáció CSV adatokkal
Cél: Megvizsgálni, hogy a korai előrejelzések mennyire pontosak voltak
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

def detect_refills(data):
    """Feltöltések detektálása"""
    print("\n" + "=" * 80)
    print("🔍 FELTÖLTÉSEK DETEKTÁLÁSA")
    print("=" * 80)

    refills = []

    for i in range(1, len(data)):
        weight_change = data[i][1] - data[i-1][1]

        # Feltöltés: >1000 kg növekedés
        if weight_change > 1000:
            refills.append({
                'index': i,
                'timestamp': data[i][0],
                'weight_before': data[i-1][1],
                'weight_after': data[i][1],
                'amount': weight_change
            })

    print(f"\n✅ {len(refills)} feltöltés detektálva:\n")
    for i, refill in enumerate(refills, 1):
        print(f"  #{i}. {refill['timestamp'].strftime('%Y-%m-%d %H:%M')}: "
              f"+{refill['amount']:.0f} kg "
              f"({refill['weight_before']:.0f} → {refill['weight_after']:.0f} kg)")

    return refills

def create_continuous_curve(data, start_idx):
    """
    Folyamatos fogyási görbe létrehozása (feltöltések kiszűrésével)
    start_idx után kezdődik
    """
    cycle_data = data[start_idx:]
    continuous_data = []
    base_adjustment = 0

    for i, (t, w) in enumerate(cycle_data):
        if i > 0:
            weight_change = w - cycle_data[i-1][1]
            # Ha feltöltés (>1000 kg növekedés), adjusztáljuk
            if weight_change > 1000:
                base_adjustment -= weight_change

        adjusted_weight = w + base_adjustment
        continuous_data.append((t, adjusted_weight))

    return continuous_data

def make_prediction(continuous_data, prediction_idx):
    """
    Előrejelzés készítése egy adott indexnél
    continuous_data: folyamatos fogyási görbe
    prediction_idx: melyik indexnél készítsük az előrejelzést
    """
    if prediction_idx >= len(continuous_data):
        return None

    # Csak a prediction_idx-ig használjuk az adatokat
    pred_data = continuous_data[:prediction_idx + 1]

    if len(pred_data) < 5:  # Minimum 5 adatpont kell
        return None

    # Lineáris regresszió
    times = np.array([(t - pred_data[0][0]).total_seconds() / 3600 for t, w in pred_data])
    weights = np.array([w for t, w in pred_data])

    slope, intercept, r_value, p_value, std_err = stats.linregress(times, weights)

    # 0 kg előrejelzés
    if slope >= 0:  # Nincs fogyás
        return None

    hours_to_zero = -intercept / slope
    zero_date = pred_data[0][0] + timedelta(hours=hours_to_zero)

    return {
        'prediction_time': pred_data[-1][0],
        'predicted_empty': zero_date,
        'slope': slope,
        'r_squared': r_value**2,
        'data_points': len(pred_data),
        'current_weight': pred_data[-1][1],
        'days_from_start': (pred_data[-1][0] - pred_data[0][0]).days
    }

def validate_cycle(data, cycle_start_idx, next_refill):
    """
    Egy ciklus validálása
    cycle_start_idx: ciklus kezdete (0. nap)
    next_refill: következő feltöltés (vagy None ha nincs)
    """
    # Folyamatos görbe létrehozása
    continuous = create_continuous_curve(data, cycle_start_idx)

    if len(continuous) < 10:
        return None

    # Előrejelzések különböző időpontokban (3, 7, 14, 21, 28 nap)
    predictions = []

    for days_offset in [3, 7, 14, 21, 28]:
        # Keressük meg a days_offset naphoz tartozó indexet
        target_date = continuous[0][0] + timedelta(days=days_offset)

        # Legközelebbi index keresése
        best_idx = None
        min_diff = timedelta(days=999)

        for i, (t, w) in enumerate(continuous):
            diff = abs(t - target_date)
            if diff < min_diff:
                min_diff = diff
                best_idx = i

        if best_idx is not None and min_diff < timedelta(hours=12):  # Max 12 óra eltérés
            pred = make_prediction(continuous, best_idx)
            if pred:
                predictions.append(pred)

    return {
        'cycle_start': continuous[0][0],
        'cycle_end': continuous[-1][0],
        'predictions': predictions,
        'next_refill': next_refill,
        'continuous_data': continuous
    }

def analyze_prediction_accuracy(cycle_info):
    """Előrejelzés pontosságának elemzése"""
    if not cycle_info or not cycle_info['predictions']:
        return

    cycle_start = cycle_info['cycle_start']
    next_refill = cycle_info['next_refill']
    predictions = cycle_info['predictions']

    print("\n" + "=" * 80)
    print(f"📊 CIKLUS VALIDÁCIÓ: {cycle_start.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)

    # Tényleges kimenetel
    if next_refill:
        actual_event = next_refill['timestamp']
        actual_weight = next_refill['weight_before']
        event_type = "FELTÖLTÉS"
        print(f"\n🎯 TÉNYLEGES KIMENETEL:")
        print(f"   {event_type}: {actual_event.strftime('%Y-%m-%d %H:%M')}")
        print(f"   Súly feltöltés előtt: {actual_weight:.0f} kg")
    else:
        print(f"\n⚠️ Nincs következő feltöltés (ciklus még tart)")
        actual_event = None

    # Előrejelzések elemzése
    print(f"\n📈 ELŐREJELZÉSEK ({len(predictions)} db):")
    print("-" * 80)

    for i, pred in enumerate(predictions, 1):
        days_from_start = pred['days_from_start']
        pred_time = pred['prediction_time']
        pred_empty = pred['predicted_empty']

        print(f"\n  #{i}. NAP {days_from_start} ({pred_time.strftime('%Y-%m-%d %H:%M')}):")
        print(f"     Adatpontok: {pred['data_points']}")
        print(f"     Jelenlegi súly: {pred['current_weight']:.0f} kg")
        print(f"     Fogyási sebesség: {pred['slope']:.2f} kg/óra ({pred['slope']*24:.0f} kg/nap)")
        print(f"     R²: {pred['r_squared']:.3f}")
        print(f"     Előrejelzett kiürülés: {pred_empty.strftime('%Y-%m-%d %H:%M')}")

        if actual_event:
            # Hiba számítása
            error = (pred_empty - actual_event).total_seconds() / 3600  # órában
            error_days = error / 24

            # Előrejelzés időpontjától a tényleges eseményig hány nap van
            lead_time = (actual_event - pred_time).total_seconds() / 3600 / 24

            if abs(error) < 24:
                emoji = "🎯"
                accuracy = "KIVÁLÓ"
            elif abs(error) < 72:
                emoji = "✅"
                accuracy = "JÓ"
            elif abs(error) < 168:
                emoji = "⚠️"
                accuracy = "ELFOGADHATÓ"
            else:
                emoji = "❌"
                accuracy = "GYENGE"

            print(f"     {emoji} Pontosság: {accuracy}")
            print(f"        Eltérés: {error:+.1f} óra ({error_days:+.1f} nap)")
            print(f"        Előrejelzési idő: {lead_time:.1f} nap előre")

            # Ha túl korán vagy túl későn jelezte előre
            if error > 0:
                print(f"        → Előrejelzés KÉSŐBB jósolt kiürülést ({abs(error):.1f} órával)")
            else:
                print(f"        → Előrejelzés KORÁBBAN jósolt kiürülést ({abs(error):.1f} órával)")

def main():
    print("🧪 PREDIKCIÓS PONTOSSÁG VALIDÁCIÓ")
    print("=" * 80)
    print("Cél: Korai előrejelzések pontosságának vizsgálata")
    print()

    # CSV betöltése
    data = load_csv_data()

    # 6 órás mintavételezés
    sampled_data = resample_6hourly(data)

    # Feltöltések detektálása
    refills = detect_refills(sampled_data)

    if len(refills) < 2:
        print("\n❌ Nincs elég feltöltés a validációhoz (minimum 2 kell)")
        return

    # Ciklusok validálása
    print("\n" + "=" * 80)
    print("🔄 CIKLUSOK VALIDÁLÁSA")
    print("=" * 80)

    for i in range(len(refills) - 1):
        cycle_start_refill = refills[i]
        next_refill = refills[i + 1]

        # Keressük meg a 0. napot (első 100kg+ fogyasztás a feltöltés után)
        day0_idx = None
        for j in range(cycle_start_refill['index'] + 1, len(sampled_data)):
            if j >= next_refill['index']:
                break

            consumption = sampled_data[j-1][1] - sampled_data[j][1]
            if consumption > 100:
                day0_idx = j
                break

        if day0_idx is None:
            print(f"\n⚠️ Ciklus #{i+1}: Nincs 0. nap (nincs 100kg+ fogyasztás)")
            continue

        # Ciklus validálása
        cycle_info = validate_cycle(sampled_data, day0_idx, next_refill)

        if cycle_info:
            analyze_prediction_accuracy(cycle_info)

    # Utolsó ciklus (ha van)
    if len(refills) > 0:
        last_refill = refills[-1]

        # 0. nap keresése
        day0_idx = None
        for j in range(last_refill['index'] + 1, len(sampled_data)):
            consumption = sampled_data[j-1][1] - sampled_data[j][1]
            if consumption > 100:
                day0_idx = j
                break

        if day0_idx:
            print(f"\n📌 UTOLSÓ CIKLUS (még tart):")
            cycle_info = validate_cycle(sampled_data, day0_idx, None)
            if cycle_info:
                analyze_prediction_accuracy(cycle_info)

    print("\n" + "=" * 80)
    print("✅ VALIDÁCIÓ BEFEJEZVE")
    print("=" * 80)

if __name__ == "__main__":
    main()
