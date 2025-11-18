#!/usr/bin/env python3
"""
CSV elemzés: 0. nap detektálása az október 13-18-i csend periódus után
"""
import csv
from datetime import datetime
import numpy as np

print("🔍 CSV Elemzés - 0. Nap Detektálása")
print("=" * 80)

# CSV beolvasás
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

print(f"✅ Betöltve: {len(data)} rekord")
print(f"📅 Időszak: {data[0][0].strftime('%Y-%m-%d')} - {data[-1][0].strftime('%Y-%m-%d')}")

# Október 13 - november 8 közötti adatok (órás átlagok)
# November 8 után nyers adatok
print("\n" + "=" * 80)
print("📊 Október 13 - Október 31 elemzése (csend periódus + feltöltés)")
print("=" * 80)

# Szűrjük ki az október 13-31 közötti adatokat
oct_data = [(t, w) for t, w in data if t.month == 10 and t.day >= 13]
print(f"\nOktóber 13-31: {len(oct_data)} adatpont")

if len(oct_data) > 0:
    # Napi összefoglaló
    daily_summary = {}
    for timestamp, weight in oct_data:
        day = timestamp.date()
        if day not in daily_summary:
            daily_summary[day] = []
        daily_summary[day].append(weight)

    print("\n📅 Napi átlagok és min/max:")
    print("-" * 80)
    for day in sorted(daily_summary.keys()):
        weights = daily_summary[day]
        avg = np.mean(weights)
        min_w = np.min(weights)
        max_w = np.max(weights)
        print(f"  {day}: átlag={avg:7.1f} kg, min={min_w:7.1f} kg, max={max_w:7.1f} kg, pontok={len(weights)}")

# Csend periódus detektálás
print("\n" + "=" * 80)
print("🔍 CSEND PERIÓDUS KERESÉSE")
print("=" * 80)

# Keresünk ~5 napot, ahol a súly < 1000 kg és nincs nagy változás
silence_periods = []
for i in range(len(data) - 1):
    timestamp, weight = data[i]

    # Ha a súly < 100 kg, ellenőrizzük az előző 3-5 napot
    if weight < 100:
        # Előző 5 nap adatai
        prev_5_days = [data[j] for j in range(max(0, i-120), i)]  # ~120 óra = 5 nap

        if len(prev_5_days) > 24:  # Legalább 1 nap adat
            prev_weights = [w for _, w in prev_5_days]
            avg_prev = np.mean(prev_weights)

            if avg_prev < 1000:  # Alacsony súly periódus
                silence_periods.append((timestamp, weight, avg_prev))

if silence_periods:
    print(f"\n✅ Talált csend időpontok (súly < 100 kg):")
    for ts, w, avg in silence_periods[:10]:
        print(f"  {ts.strftime('%Y-%m-%d %H:%M')}: {w:.1f} kg (előző 5 nap átlag: {avg:.1f} kg)")
else:
    print("\n❌ Nincs csend periódus ahol súly < 100 kg")

# FELTÖLTÉS KERESÉSE csend után
print("\n" + "=" * 80)
print("🔄 ELSŐ FELTÖLTÉS KERESÉSE (csend után)")
print("=" * 80)

for i in range(1, len(data)):
    prev_time, prev_weight = data[i-1]
    curr_time, curr_weight = data[i]

    weight_increase = curr_weight - prev_weight

    # Nagy feltöltés (>1000 kg ugrás)
    if weight_increase > 1000:
        # Ellenőrizzük, hogy előtte alacsony volt-e a súly
        if prev_weight < 1000:
            print(f"\n✅ ELSŐ FELTÖLTÉS (csend után):")
            print(f"  Dátum: {curr_time.strftime('%Y-%m-%d %H:%M')}")
            print(f"  Súly előtte: {prev_weight:.1f} kg")
            print(f"  Súly utána: {curr_weight:.1f} kg")
            print(f"  Növekedés: +{weight_increase:.1f} kg")

            # Keressük a 0. napot: első 100kg+ fogyasztás a feltöltés után
            print(f"\n  🐣 0. NAP KERESÉSE (100kg+ fogyasztás):")
            for j in range(i+1, min(i+200, len(data))):  # Következő ~8 nap
                t1, w1 = data[j-1]
                t2, w2 = data[j]
                consumption = w1 - w2

                if consumption > 100:
                    print(f"     ✅ 0. NAP: {t2.strftime('%Y-%m-%d %H:%M')}")
                    print(f"        Fogyasztás: {consumption:.1f} kg/óra")
                    print(f"        Súly: {w1:.1f} -> {w2:.1f} kg")
                    break

            break  # Csak az első feltöltést nézzük

print("\n" + "=" * 80)
