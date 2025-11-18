#!/usr/bin/env python3
"""
Komplex validációs és predikciós teszt
1. Korábbi előrejelzések pontosságának ellenőrzése
2. Mai (nov 18) feltöltés detektálása
3. Jelenlegi kiürülés előrejelzése
4. Madárszám becslés technológiai adatokkal
"""
import csv
from datetime import datetime, timedelta
import numpy as np
from scipy import stats

# Technológiai takarmány fogyasztási adatok (g/nap/madár)
TECH_FEED_DATA = {
    0: 0, 1: 0, 2: 16, 3: 20, 4: 24, 5: 27, 6: 31, 7: 35, 8: 39, 9: 44,
    10: 48, 11: 52, 12: 57, 13: 62, 14: 67, 15: 72, 16: 77, 17: 83, 18: 88, 19: 94,
    20: 100, 21: 105, 22: 111, 23: 117, 24: 122, 25: 128, 26: 134, 27: 139, 28: 145, 29: 150,
    30: 156, 31: 161, 32: 166, 33: 171, 34: 176, 35: 180, 36: 185, 37: 189, 38: 193, 39: 197,
    40: 201, 41: 204, 42: 207, 43: 211, 44: 213, 45: 216, 46: 219, 47: 221, 48: 223, 49: 225,
    50: 227
}

def load_csv():
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

def detect_refills(data, threshold=1000):
    """Feltöltések detektálása"""
    refills = []
    for i in range(1, len(data)):
        increase = data[i][1] - data[i-1][1]
        if increase > threshold:
            refills.append({
                'time': data[i][0],
                'before': data[i-1][1],
                'after': data[i][1],
                'amount': increase,
                'index': i
            })
    return refills

def make_prediction_at_time(data, start_idx, prediction_date):
    """Előrejelzés készítése egy adott időpontban (validációhoz)"""
    # Adatok a start_idx-től kezdve
    cycle_data = []
    base_adjustment = 0

    for i in range(start_idx, len(data)):
        t, w = data[i]

        # Feltöltés detektálás és kiszűrés
        if i > start_idx:
            increase = w - data[i-1][1]
            if increase > 1000:
                base_adjustment -= increase

        adjusted_weight = w + base_adjustment
        cycle_data.append((t, adjusted_weight))

        # Ha elértük a prediction_date-et, itt állunk meg
        if t >= prediction_date:
            break

    if len(cycle_data) < 5:
        return None

    # Lineáris regresszió
    times = np.array([(t - cycle_data[0][0]).total_seconds() / 3600 for t, w in cycle_data])
    weights = np.array([w for t, w in cycle_data])

    slope, intercept, r_value, _, _ = stats.linregress(times, weights)

    if slope >= 0:  # Nem csökkenő trend
        return None

    # 0 kg előrejelzés
    hours_to_zero = -intercept / slope
    zero_date = cycle_data[0][0] + timedelta(hours=hours_to_zero)

    return {
        'prediction_date': prediction_date,
        'predicted_zero': zero_date,
        'slope': slope,
        'r2': r_value**2,
        'data_points': len(cycle_data),
        'start_weight': weights[0]
    }

def validate_predictions(data, cycle_start_idx, refills):
    """Validálás: előrejelzések pontossága"""
    print("=" * 80)
    print("📊 ELŐREJELZÉSEK VALIDÁCIÓJA")
    print("=" * 80)
    print()

    # Tegyük fel, hogy minden feltöltésnél új előrejelzést készítünk
    validation_points = [
        cycle_start_idx,  # Ciklus kezdet
    ]

    # Feltöltések utáni időpontok
    for refill in refills:
        if refill['index'] > cycle_start_idx:
            validation_points.append(refill['index'] + 1)

    predictions = []

    print("🔮 Előrejelzések különböző időpontokban:")
    print("-" * 80)

    for i, vp_idx in enumerate(validation_points[:10]):  # Max 10 validációs pont
        if vp_idx >= len(data):
            continue

        prediction_time = data[vp_idx][0]
        pred = make_prediction_at_time(data, vp_idx, prediction_time)

        if pred:
            days_from_start = (prediction_time - data[cycle_start_idx][0]).days
            print(f"\n#{i+1}. Előrejelzés: {prediction_time.strftime('%Y-%m-%d %H:%M')} (Nap {days_from_start})")
            print(f"   Előrejelzett 0 kg: {pred['predicted_zero'].strftime('%Y-%m-%d %H:%M')}")
            print(f"   Fogyási sebesség: {pred['slope']:.2f} kg/óra")
            print(f"   R²: {pred['r2']:.3f}")
            print(f"   Adatpontok: {pred['data_points']}")
            predictions.append(pred)

    # Pontosság elemzése (ha van tényleges kiürülés)
    print("\n" + "=" * 80)
    print("✅ Összesítés:")
    print("-" * 80)
    print(f"Összes előrejelzés: {len(predictions)}")
    if predictions:
        avg_r2 = np.mean([p['r2'] for p in predictions])
        print(f"Átlagos R²: {avg_r2:.3f}")

        # Előrejelzések szórása
        pred_dates = [p['predicted_zero'] for p in predictions]
        if len(pred_dates) > 1:
            pred_timestamps = [(d - pred_dates[0]).total_seconds() for d in pred_dates]
            std_days = np.std(pred_timestamps) / 86400
            print(f"Előrejelzések szórása: {std_days:.1f} nap")

def analyze_nov18_refill(data):
    """November 18-i feltöltés elemzése"""
    print("\n" + "=" * 80)
    print("🔍 NOVEMBER 18-I FELTÖLTÉS ELEMZÉSE")
    print("=" * 80)
    print()

    # November 18-i adatok
    nov18_data = [(t, w) for t, w in data if t.date() == datetime(2025, 11, 18).date()]

    if not nov18_data:
        print("❌ Nincs november 18-i adat")
        return None

    print(f"📊 November 18-i adatok: {len(nov18_data)} rekord")
    print(f"   Időszak: {nov18_data[0][0].strftime('%H:%M')} - {nov18_data[-1][0].strftime('%H:%M')}")
    print(f"   Min súly: {min(w for t, w in nov18_data):.0f} kg")
    print(f"   Max súly: {max(w for t, w in nov18_data):.0f} kg")

    # Óránkénti összefoglaló
    hourly = {}
    for t, w in nov18_data:
        hour = t.hour
        if hour not in hourly:
            hourly[hour] = []
        hourly[hour].append(w)

    print("\n📈 Óránkénti átlagok:")
    print("-" * 80)

    refill_detected = False
    refill_time = None

    for hour in sorted(hourly.keys()):
        avg = np.mean(hourly[hour])
        min_w = np.min(hourly[hour])
        max_w = np.max(hourly[hour])

        # Feltöltés detektálás
        marker = ""
        if hour > 0 and hour in hourly and (hour-1) in hourly:
            prev_max = np.max(hourly[hour-1])
            curr_min = np.min(hourly[hour])
            increase = curr_min - prev_max

            if increase > 3000:
                marker = f"  ⬆️ FELTÖLTÉS! (+{increase:.0f} kg)"
                refill_detected = True
                refill_time = hour

        print(f"  {hour:02d}:00  átlag={avg:7.0f} kg, min={min_w:7.0f} kg, max={max_w:7.0f} kg{marker}")

    if refill_detected:
        print(f"\n✅ Feltöltés detektálva: ~{refill_time:02d}:00 óra körül")
    else:
        print(f"\n⚠️ Jelentős feltöltés nem detektálva a mintavételezett adatokban")
        print(f"   (Lehetséges, hogy a 6 órás mintavételezés miatt átlagolódott)")

    return refill_time

def predict_current_emptying(data):
    """Jelenlegi kiürülés előrejelzése"""
    print("\n" + "=" * 80)
    print("🎯 JELENLEGI KIÜRÜLÉS ELŐREJELZÉSE")
    print("=" * 80)
    print()

    # Utolsó 48 óra adatai (jelenlegi trend)
    now = data[-1][0]
    cutoff = now - timedelta(hours=48)
    recent_data = [(t, w) for t, w in data if t >= cutoff]

    # Mintavételezés
    sampled = resample_6hourly(recent_data)

    # Feltöltések kiszűrése
    continuous = []
    base_adj = 0

    for i, (t, w) in enumerate(sampled):
        if i > 0:
            increase = w - sampled[i-1][1]
            if increase > 1000:
                base_adj -= increase
                print(f"   🔄 Feltöltés kiszűrve: {t.strftime('%Y-%m-%d %H:%M')}, +{increase:.0f} kg")

        continuous.append((t, w + base_adj))

    if len(continuous) < 3:
        print("❌ Nincs elég adat az előrejelzéshez")
        return None

    # Regresszió
    times = np.array([(t - continuous[0][0]).total_seconds() / 3600 for t, w in continuous])
    weights = np.array([w for t, w in continuous])

    slope, intercept, r_value, _, _ = stats.linregress(times, weights)

    print(f"\n📊 Fogyási trend (utolsó 48 óra):")
    print(f"   Adatpontok: {len(continuous)}")
    print(f"   Fogyási sebesség: {slope:.2f} kg/óra ({slope*24:.0f} kg/nap)")
    print(f"   R²: {r_value**2:.3f}")
    print(f"   Jelenlegi súly: {continuous[-1][1]:.0f} kg")

    if slope >= 0:
        print("\n⚠️ Nem csökkenő trend (lehet feltöltés volt)")
        return None

    # 0 kg előrejelzés
    hours_to_zero = -intercept / slope
    zero_date = continuous[0][0] + timedelta(hours=hours_to_zero)
    days_remaining = hours_to_zero / 24

    print(f"\n🎯 ELŐREJELZÉS:")
    print(f"   0 kg várható: {zero_date.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Hátralévő idő: {days_remaining:.1f} nap")

    return {
        'zero_date': zero_date,
        'days_remaining': days_remaining,
        'slope': slope,
        'r2': r_value**2,
        'current_weight': continuous[-1][1]
    }

def estimate_bird_count(prediction, cycle_start_date):
    """Madárszám becslés technológiai adatok alapján"""
    print("\n" + "=" * 80)
    print("🐔 MADÁRSZÁM BECSLÉS (Technológiai adatok alapján)")
    print("=" * 80)
    print()

    if not prediction:
        print("❌ Nincs előrejelzés, madárszám nem becsülhető")
        return None

    # Nevelési nap kiszámítása
    now = datetime.now(cycle_start_date.tzinfo)
    cycle_days = (now - cycle_start_date).days

    print(f"📅 Nevelési nap: {cycle_days} (ciklus kezdet: {cycle_start_date.strftime('%Y-%m-%d')})")

    if cycle_days > 50 or cycle_days < 0:
        print(f"⚠️ Nevelési nap kívül esik a tartományon (0-50 nap)")
        return None

    # Technológiai napi fogyasztás (g/madár/nap)
    tech_consumption = TECH_FEED_DATA.get(cycle_days, 0)

    # Valós fogyasztás (kg/óra -> kg/nap)
    actual_consumption_kg_day = abs(prediction['slope']) * 24
    actual_consumption_g_day = actual_consumption_kg_day * 1000

    # Madárszám becslés
    if tech_consumption > 0:
        estimated_birds = actual_consumption_g_day / tech_consumption

        print(f"\n📊 Számítás:")
        print(f"   Technológiai fogyasztás: {tech_consumption} g/madár/nap ({cycle_days}. napon)")
        print(f"   Tényleges fogyasztás: {actual_consumption_kg_day:.0f} kg/nap = {actual_consumption_g_day:.0f} g/nap")
        print(f"\n🐔 BECSÜLT MADÁRSZÁM: {estimated_birds:.0f} db")

        # Tipikus baromfitelep méretekkel való összehasonlítás
        print(f"\n📌 Referencia:")
        if estimated_birds < 5000:
            print(f"   Kis telepméret")
        elif estimated_birds < 20000:
            print(f"   Közepes telepméret")
        else:
            print(f"   Nagy telepméret")

        return int(estimated_birds)
    else:
        print(f"⚠️ Nincs technológiai adat a {cycle_days}. napra")
        return None

def main():
    print("🧪 KOMPLEX VALIDÁCIÓS ÉS PREDIKCIÓS TESZT")
    print("=" * 80)
    print()

    # CSV betöltése
    print("📂 CSV betöltése...")
    data = load_csv()
    print(f"✅ {len(data)} rekord")
    print(f"📅 Időszak: {data[0][0].strftime('%Y-%m-%d')} - {data[-1][0].strftime('%Y-%m-%d')}")

    # Mintavételezés
    sampled = resample_6hourly(data)
    print(f"📈 {len(sampled)} mintavételezett adatpont")

    # Ciklus kezdet (ismert: 2025-10-20 06:00)
    cycle_start = datetime(2025, 10, 20, 6, 0, tzinfo=data[0][0].tzinfo)
    cycle_start_idx = None

    for i, (t, w) in enumerate(sampled):
        if t >= cycle_start:
            cycle_start_idx = i
            break

    print(f"🎯 Ciklus kezdet: {cycle_start.strftime('%Y-%m-%d %H:%M')} (index: {cycle_start_idx})")

    # Feltöltések detektálása
    refills = detect_refills(sampled)
    print(f"🔄 Feltöltések száma: {len(refills)}")

    # 1. Validáció
    validate_predictions(sampled, cycle_start_idx, refills)

    # 2. November 18-i feltöltés
    analyze_nov18_refill(data)

    # 3. Jelenlegi előrejelzés
    prediction = predict_current_emptying(sampled)

    # 4. Madárszám becslés
    if prediction:
        estimate_bird_count(prediction, cycle_start)

    print("\n" + "=" * 80)
    print("✅ TESZT BEFEJEZVE")
    print("=" * 80)

if __name__ == "__main__":
    main()
