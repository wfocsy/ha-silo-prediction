#!/usr/bin/env python3
"""
Javított validációs és predikciós teszt
1. Előrejelzés számítások javítása (validáció)
2. 5 perces mintavételezés feltöltés detektáláshoz
3. Emberi olvasható dátum formátum (Ma 18-20 óra között)
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

def resample_5min(data, start_time, end_time):
    """5 perces mintavételezés feltöltés detektáláshoz"""
    timestamps = np.array([t for t, w in data])
    weights = np.array([w for t, w in data])

    current = start_time
    sample_data = []

    while current <= end_time:
        window_start = current - timedelta(minutes=2.5)
        window_end = current + timedelta(minutes=2.5)

        mask = (timestamps >= window_start) & (timestamps <= window_end)
        if np.any(mask):
            avg_weight = np.mean(weights[mask])
            sample_data.append((current, avg_weight))

        current += timedelta(minutes=5)

    return sample_data

def detect_refill_completion(data_5min):
    """
    Feltöltés befejezésének detektálása
    - 5 perces mintavételezett adatokon
    - Ha 10 percen keresztül nincs emelkedés (2 minta) → feltöltés vége
    """
    refill_end_times = []
    in_refill = False
    last_increase_idx = -1

    for i in range(1, len(data_5min)):
        increase = data_5min[i][1] - data_5min[i-1][1]

        if increase > 100:  # Jelentős emelkedés (feltöltés folyamatban)
            in_refill = True
            last_increase_idx = i

        # Ha feltöltésben vagyunk és 10 perc (2 minta) óta nincs emelkedés
        if in_refill and i - last_increase_idx >= 2:
            refill_end = data_5min[i][0]
            refill_end_times.append({
                'end_time': refill_end,
                'end_weight': data_5min[i][1],
                'index': i
            })
            in_refill = False

    return refill_end_times

def format_prediction_time(prediction_datetime):
    """
    Emberi olvasható formátumra konvertálás
    Pl: "Ma 18-20 óra között (~19:04)"
    """
    now = datetime.now(prediction_datetime.tzinfo)

    # Dátum különbség
    days_diff = (prediction_datetime.date() - now.date()).days

    # Óra és 2 órás ablak
    pred_hour = prediction_datetime.hour
    pred_minute = prediction_datetime.minute

    # 2 órás ablak
    hour_start = max(0, pred_hour - 1)
    hour_end = min(23, pred_hour + 1)

    # Dátum szöveg
    if days_diff == 0:
        date_str = "Ma"
    elif days_diff == 1:
        date_str = "Holnap"
    else:
        date_str = prediction_datetime.strftime('%Y-%m-%d')

    # Formázott szöveg
    formatted = f"{date_str} {hour_start:02d}-{hour_end:02d} óra között (~{pred_hour:02d}:{pred_minute:02d})"

    return formatted

def resample_6hourly(data):
    """6 órás mintavételezés (előrejelzéshez)"""
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

def make_prediction_from_data(cycle_data, refill_detections):
    """
    Előrejelzés készítése adott ciklus adatokból
    - Feltöltések kiszűrése
    - Lineáris regresszió
    """
    if len(cycle_data) < 5:
        return None

    # Folyamatos görbe (feltöltések nélkül)
    continuous = []
    base_adj = 0

    for i, (t, w) in enumerate(cycle_data):
        if i > 0:
            increase = w - cycle_data[i-1][1]
            if increase > 1000:  # Feltöltés detektálás
                base_adj -= increase

        continuous.append((t, w + base_adj))

    # Lineáris regresszió
    times = np.array([(t - continuous[0][0]).total_seconds() / 3600 for t, w in continuous])
    weights = np.array([w for t, w in continuous])

    slope, intercept, r_value, _, _ = stats.linregress(times, weights)

    if slope >= 0:  # Nem csökkenő trend
        return None

    # 0 kg előrejelzés
    hours_to_zero = -intercept / slope
    zero_date = continuous[0][0] + timedelta(hours=hours_to_zero)

    return {
        'zero_date': zero_date,
        'slope': slope,
        'r2': r_value**2,
        'data_points': len(continuous),
        'current_weight': weights[-1]
    }

def validate_predictions_fixed(data_6h, cycle_start_idx):
    """
    Javított validáció: különböző időpontokban készült előrejelzések
    """
    print("=" * 80)
    print("📊 ELŐREJELZÉSEK VALIDÁCIÓJA (JAVÍTOTT)")
    print("=" * 80)
    print()

    # Validációs időpontok: ciklus kezdet után minden 3 napban
    validation_points = []
    for days_offset in [3, 7, 14, 21, 28]:
        vp_time = data_6h[cycle_start_idx][0] + timedelta(days=days_offset)

        # Megkeressük a legközelebbi adatpontot
        for i, (t, w) in enumerate(data_6h):
            if t >= vp_time:
                validation_points.append(i)
                break

    print(f"🔮 Előrejelzések {len(validation_points)} különböző időpontban:")
    print("-" * 80)

    predictions = []

    for vp_idx in validation_points:
        if vp_idx >= len(data_6h) or vp_idx <= cycle_start_idx:
            continue

        # Adatok a ciklus kezdetétől a validációs pontig
        cycle_data = data_6h[cycle_start_idx:vp_idx+1]

        pred = make_prediction_from_data(cycle_data, [])

        if pred:
            pred_time = data_6h[vp_idx][0]
            days_from_start = (pred_time - data_6h[cycle_start_idx][0]).days

            formatted_pred = format_prediction_time(pred['zero_date'])

            print(f"\n📅 Előrejelzés {pred_time.strftime('%Y-%m-%d')} (Nap {days_from_start}):")
            print(f"   Adatpontok: {pred['data_points']}")
            print(f"   Fogyási sebesség: {pred['slope']:.2f} kg/óra ({pred['slope']*24:.0f} kg/nap)")
            print(f"   R²: {pred['r2']:.3f}")
            print(f"   Előrejelzett kiürülés: {formatted_pred}")
            print(f"      (Pontos: {pred['zero_date'].strftime('%Y-%m-%d %H:%M')})")

            predictions.append(pred)

    # Összesítés
    print("\n" + "=" * 80)
    print("✅ Validációs összesítés:")
    print("-" * 80)
    print(f"Sikeres előrejelzések: {len(predictions)}")

    if predictions:
        avg_r2 = np.mean([p['r2'] for p in predictions])
        print(f"Átlagos R²: {avg_r2:.3f}")

        # Előrejelzések konvergenciája
        pred_dates = [p['zero_date'] for p in predictions]
        if len(pred_dates) > 1:
            # Első és utolsó előrejelzés közötti különbség
            first_pred = pred_dates[0]
            last_pred = pred_dates[-1]
            diff_hours = abs((last_pred - first_pred).total_seconds() / 3600)

            print(f"Első vs utolsó előrejelzés eltérése: {diff_hours:.1f} óra ({diff_hours/24:.1f} nap)")

    return predictions

def analyze_nov18_refill_5min(data):
    """November 18-i feltöltés 5 perces mintavételezéssel"""
    print("\n" + "=" * 80)
    print("🔍 NOVEMBER 18-I FELTÖLTÉS (5 perces mintavételezés)")
    print("=" * 80)
    print()

    # November 18-i adatok
    nov18_start = datetime(2025, 11, 18, 0, 0, tzinfo=data[0][0].tzinfo)
    nov18_end = datetime(2025, 11, 18, 23, 59, tzinfo=data[0][0].tzinfo)

    nov18_data = [(t, w) for t, w in data if nov18_start <= t <= nov18_end]

    if not nov18_data:
        print("❌ Nincs november 18-i adat")
        return None

    # 5 perces mintavételezés
    data_5min = resample_5min(nov18_data, nov18_start, nov18_end)

    print(f"📊 5 perces mintavételezés: {len(data_5min)} adatpont")

    # Feltöltés befejezés detektálása
    refill_ends = detect_refill_completion(data_5min)

    print(f"\n🔄 Feltöltés befejezések: {len(refill_ends)} db")

    for i, re in enumerate(refill_ends):
        print(f"\n#{i+1}. Feltöltés vége:")
        print(f"   Időpont: {re['end_time'].strftime('%Y-%m-%d %H:%M')}")
        print(f"   Végső súly: {re['end_weight']:.0f} kg")

    # Grafikus megjelenítés (óránkénti)
    print(f"\n📈 Súly változás óránként:")
    print("-" * 80)

    hourly = {}
    for t, w in data_5min:
        hour = t.hour
        if hour not in hourly:
            hourly[hour] = []
        hourly[hour].append(w)

    for hour in sorted(hourly.keys()):
        avg = np.mean(hourly[hour])
        min_w = np.min(hourly[hour])
        max_w = np.max(hourly[hour])

        # Emelkedés jelzés
        marker = ""
        if hour > 0 and (hour-1) in hourly:
            prev_avg = np.mean(hourly[hour-1])
            increase = avg - prev_avg
            if increase > 1000:
                marker = f"  ⬆️ +{increase:.0f} kg/óra"

        print(f"  {hour:02d}:00  átlag={avg:6.0f} kg, tartomány=[{min_w:6.0f} - {max_w:6.0f}]{marker}")

    return refill_ends

def predict_current_with_format(data):
    """Jelenlegi kiürülés előrejelzése emberi formátummal"""
    print("\n" + "=" * 80)
    print("🎯 JELENLEGI KIÜRÜLÉS ELŐREJELZÉSE")
    print("=" * 80)
    print()

    # Utolsó 48 óra
    now = data[-1][0]
    cutoff = now - timedelta(hours=48)
    recent_data = [(t, w) for t, w in data if t >= cutoff]

    # 6 órás mintavételezés
    sampled = resample_6hourly(recent_data)

    pred = make_prediction_from_data(sampled, [])

    if not pred:
        print("❌ Nem sikerült előrejelzést készíteni")
        return None

    # Formázott kimenet
    formatted_time = format_prediction_time(pred['zero_date'])

    print(f"📊 Fogyási trend (utolsó 48 óra):")
    print(f"   Adatpontok: {pred['data_points']}")
    print(f"   Fogyási sebesség: {pred['slope']:.2f} kg/óra ({pred['slope']*24:.0f} kg/nap)")
    print(f"   R²: {pred['r2']:.3f}")
    print(f"   Jelenlegi súly: {pred['current_weight']:.0f} kg")

    print(f"\n🎯 ELŐREJELZETT KIÜRÜLÉS:")
    print(f"   {formatted_time}")
    print(f"   (Pontos: {pred['zero_date'].strftime('%Y-%m-%d %H:%M')})")

    # Hátralévő idő
    now = datetime.now(pred['zero_date'].tzinfo)
    remaining = pred['zero_date'] - now
    remaining_hours = remaining.total_seconds() / 3600

    if remaining_hours < 24:
        print(f"   Hátralévő idő: {remaining_hours:.1f} óra")
    else:
        print(f"   Hátralévő idő: {remaining_hours/24:.1f} nap")

    return pred

def estimate_bird_count(prediction, cycle_start_date):
    """Madárszám becslés"""
    print("\n" + "=" * 80)
    print("🐔 MADÁRSZÁM BECSLÉS")
    print("=" * 80)
    print()

    if not prediction:
        return None

    now = datetime.now(cycle_start_date.tzinfo)
    cycle_days = (now - cycle_start_date).days

    print(f"📅 Nevelési nap: {cycle_days} (ciklus kezdet: {cycle_start_date.strftime('%Y-%m-%d')})")

    if cycle_days > 50 or cycle_days < 0:
        print(f"⚠️ Nevelési nap kívül esik a tartományon (0-50)")
        return None

    tech_consumption = TECH_FEED_DATA.get(cycle_days, 0)
    actual_consumption_kg_day = abs(prediction['slope']) * 24
    actual_consumption_g_day = actual_consumption_kg_day * 1000

    if tech_consumption > 0:
        estimated_birds = actual_consumption_g_day / tech_consumption

        print(f"\n📊 Számítás:")
        print(f"   Technológiai fogyasztás: {tech_consumption} g/madár/nap ({cycle_days}. nap)")
        print(f"   Tényleges fogyasztás: {actual_consumption_kg_day:.0f} kg/nap")
        print(f"\n🐔 BECSÜLT MADÁRSZÁM: {estimated_birds:,.0f} db")

        return int(estimated_birds)

    return None

def main():
    print("🧪 JAVÍTOTT VALIDÁCIÓS ÉS PREDIKCIÓS TESZT")
    print("=" * 80)
    print()

    # CSV betöltés
    data = load_csv()
    print(f"✅ {len(data)} rekord betöltve")
    print(f"📅 {data[0][0].strftime('%Y-%m-%d')} - {data[-1][0].strftime('%Y-%m-%d')}")

    # 6 órás mintavételezés
    sampled_6h = resample_6hourly(data)
    print(f"📈 {len(sampled_6h)} mintavételezett adatpont (6 óránként)")

    # Ciklus kezdet
    cycle_start = datetime(2025, 10, 20, 6, 0, tzinfo=data[0][0].tzinfo)
    cycle_start_idx = None
    for i, (t, w) in enumerate(sampled_6h):
        if t >= cycle_start:
            cycle_start_idx = i
            break

    print(f"🎯 Ciklus kezdet: {cycle_start.strftime('%Y-%m-%d %H:%M')} (index: {cycle_start_idx})")

    # 1. Javított validáció
    validate_predictions_fixed(sampled_6h, cycle_start_idx)

    # 2. November 18-i feltöltés (5 perces)
    analyze_nov18_refill_5min(data)

    # 3. Jelenlegi előrejelzés (formázott)
    prediction = predict_current_with_format(sampled_6h)

    # 4. Madárszám becslés
    if prediction:
        estimate_bird_count(prediction, cycle_start)

    print("\n" + "=" * 80)
    print("✅ TESZT BEFEJEZVE")
    print("=" * 80)

if __name__ == "__main__":
    main()
