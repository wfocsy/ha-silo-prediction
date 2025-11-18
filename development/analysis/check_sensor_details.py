#!/usr/bin/env python3
"""
Részletes entitás vizsgálat - pontosan mi érhető el
"""
import requests
import os
from datetime import datetime, timedelta

HA_URL = "http://supervisor/core"
TOKEN = os.getenv("SUPERVISOR_TOKEN")
ENTITY_ID = "sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly"

print("🔍 Szenzor részletes vizsgálat")
print("=" * 80)
print(f"Entitás: {ENTITY_ID}")
print()

# 1. Jelenlegi állapot
print("1️⃣ JELENLEGI ÁLLAPOT")
print("-" * 80)
url = f"{HA_URL}/api/states/{ENTITY_ID}"
headers = {"Authorization": f"Bearer {TOKEN}"}

try:
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    state = response.json()

    print(f"State: {state.get('state')}")
    print(f"Last changed: {state.get('last_changed')}")
    print(f"Last updated: {state.get('last_updated')}")

    if 'attributes' in state:
        attrs = state['attributes']
        print(f"\nAttribútumok:")
        for key, value in attrs.items():
            print(f"  - {key}: {value}")
except Exception as e:
    print(f"❌ Hiba: {e}")

# 2. History - különböző időablakok
print("\n2️⃣ HISTORY API - Különböző időablakok")
print("-" * 80)

test_periods = [7, 14, 30, 60, 90]

for days in test_periods:
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    url = f"{HA_URL}/api/history/period/{start_time.isoformat()}"
    params = {
        "filter_entity_id": ENTITY_ID,
        "end_time": end_time.isoformat(),
        "minimal_response": "true"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data and data[0]:
            count = len(data[0])
            first_time = datetime.fromisoformat(data[0][0]["last_changed"].replace("Z", "+00:00"))
            last_time = datetime.fromisoformat(data[0][-1]["last_changed"].replace("Z", "+00:00"))
            actual_days = (last_time - first_time).days

            print(f"  {days:3d} nap lekérés: {count:6d} rekord, valós időtartam: {actual_days:3d} nap ({first_time.strftime('%Y-%m-%d')} - {last_time.strftime('%Y-%m-%d')})")
        else:
            print(f"  {days:3d} nap lekérés: ❌ Nincs adat")
    except Exception as e:
        print(f"  {days:3d} nap lekérés: ❌ Hiba: {e}")

# 3. Recorder konfiguráció ellenőrzés
print("\n3️⃣ RECORDER KONFIGURÁCIÓ")
print("-" * 80)

try:
    # Config ellenőrzés
    with open("/config/configuration.yaml", "r") as f:
        config = f.read()

    if "purge_keep_days:" in config:
        for line in config.split("\n"):
            if "purge_keep_days:" in line:
                print(f"  {line.strip()}")

    print("\n  Ez azt jelenti, hogy a recorder valóban csak 10 napot őriz meg.")
    print("  DE: Ha 60 napot kérsz le, és 10+ napnyi adat jön vissza,")
    print("      akkor a történeti adat még a purge előtt van.")

except Exception as e:
    print(f"❌ Hiba: {e}")

print("\n" + "=" * 80)
print("📝 MAGYARÁZAT")
print("=" * 80)
print("""
Ha 60 vagy 90 napos lekérésnél is csak 10 napnyi adatot kapsz vissza,
akkor a purge_keep_days=10 működik és valóban törli a régi adatokat.

A purge általában naponta egyszer fut (éjjel), és törli a 10 napnál
régebbi rekordokat. Ezért mindig csak ~10 nap lesz elérhető.

Az augusztusi adatok amit látsz:
- Lehet, hogy más entitás
- Vagy egy CSV export/mentett adat
- Vagy a Developer Tools → History grafikonja cache-t használ
""")

print("=" * 80)
