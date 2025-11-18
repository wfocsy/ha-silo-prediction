#!/usr/bin/env python3
"""
Jelenlegi fogyási trend ellenőrzése (utolsó 2-3 óra)
"""
import requests
import numpy as np
from datetime import datetime, timedelta
import os

TOKEN = os.getenv("SUPERVISOR_TOKEN")
HA_URL = "http://supervisor/core"
ENTITY_ID = "sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly"

def fetch_recent_data(hours=3):
    """Utolsó N óra adatai"""
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)

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

print("🔍 JELENLEGI FOGYÁSI TREND ELEMZÉSE")
print("=" * 80)

# Utolsó 3 óra
timestamps, weights = fetch_recent_data(hours=3)

print(f"✅ {len(timestamps)} adatpont (utolsó 3 óra)")
print(f"📅 {timestamps[0].strftime('%H:%M:%S')} - {timestamps[-1].strftime('%H:%M:%S')}")
print()

# Első és utolsó
first_time = timestamps[0]
last_time = timestamps[-1]
first_weight = weights[0]
last_weight = weights[-1]

total_time_hours = (last_time - first_time).total_seconds() / 3600
total_consumption = first_weight - last_weight

print(f"📊 ÖSSZESÍTETT:")
print(f"   Kezdő: {first_time.strftime('%H:%M:%S')} → {first_weight:.0f} kg")
print(f"   Utolsó: {last_time.strftime('%H:%M:%S')} → {last_weight:.0f} kg")
print(f"   Időtartam: {total_time_hours:.2f} óra")
print(f"   Fogyás: {total_consumption:.0f} kg")
print(f"   Sebesség: {total_consumption / total_time_hours:.0f} kg/óra = {(total_consumption / total_time_hours) * 24:.0f} kg/nap")
print()

# Óránkénti átlagok
print("📈 ÓRÁNKÉNTI ÁTLAGOK:")

hourly_avg = {}
for t, w in zip(timestamps, weights):
    hour_key = t.replace(minute=0, second=0, microsecond=0)
    if hour_key not in hourly_avg:
        hourly_avg[hour_key] = []
    hourly_avg[hour_key].append(w)

for hour in sorted(hourly_avg.keys()):
    avg = np.mean(hourly_avg[hour])
    min_w = np.min(hourly_avg[hour])
    max_w = np.max(hourly_avg[hour])
    count = len(hourly_avg[hour])

    print(f"   {hour.strftime('%H:00')}: átlag={avg:.0f} kg, min={min_w:.0f}, max={max_w:.0f} ({count} mérés)")

# Óránkénti fogyások
print()
print("📉 ÓRÁNKÉNTI FOGYÁSOK:")
sorted_hours = sorted(hourly_avg.keys())
for i in range(1, len(sorted_hours)):
    prev_hour = sorted_hours[i-1]
    curr_hour = sorted_hours[i]

    prev_avg = np.mean(hourly_avg[prev_hour])
    curr_avg = np.mean(hourly_avg[curr_hour])

    hourly_consumption = prev_avg - curr_avg

    print(f"   {prev_hour.strftime('%H:00')} → {curr_hour.strftime('%H:00')}: {hourly_consumption:.0f} kg/óra")

# Jelenlegi súly
current_weight = weights[-1]
print()
print(f"🎯 JELENLEGI SÚLY: {current_weight:.0f} kg")
print(f"   Időpont: {timestamps[-1].strftime('%Y-%m-%d %H:%M:%S')}")

# Becslés
if total_consumption > 0 and total_time_hours > 0:
    hourly_rate = total_consumption / total_time_hours
    hours_to_empty = current_weight / hourly_rate
    days_to_empty = hours_to_empty / 24

    empty_time = datetime.now() + timedelta(hours=hours_to_empty)

    print()
    print(f"🔮 BECSLÉS (jelenlegi sebességgel):")
    print(f"   Sebesség: {hourly_rate:.0f} kg/óra")
    print(f"   Kiürülés: {empty_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Hátralévő idő: {days_to_empty:.1f} nap")

print()
print("=" * 80)
