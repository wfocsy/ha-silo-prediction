#!/usr/bin/env python3
"""
Ellenőrizzük a különbséget a history és statistics API között
"""
import requests
import json
from datetime import datetime, timedelta
import os

HA_URL = "http://supervisor/core"
TOKEN = os.getenv("SUPERVISOR_TOKEN")
ENTITY_ID = "sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly"

def test_history_api():
    """History API teszt (recorder adatbázis)"""
    print("=" * 80)
    print("📊 HISTORY API (recorder - purge_keep_days=10 vonatkozik rá)")
    print("=" * 80)

    end_time = datetime.now()
    start_time = end_time - timedelta(days=60)

    url = f"{HA_URL}/api/history/period/{start_time.isoformat()}"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    params = {
        "filter_entity_id": ENTITY_ID,
        "end_time": end_time.isoformat()
    }

    print(f"Lekérdezés: {start_time.strftime('%Y-%m-%d')} - {end_time.strftime('%Y-%m-%d')}")

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data and data[0]:
            print(f"✅ Találatok: {len(data[0])} rekord")

            # Első és utolsó rekord
            first = data[0][0]
            last = data[0][-1]

            first_time = datetime.fromisoformat(first["last_changed"].replace("Z", "+00:00"))
            last_time = datetime.fromisoformat(last["last_changed"].replace("Z", "+00:00"))

            print(f"📅 Első adat: {first_time.strftime('%Y-%m-%d %H:%M')}")
            print(f"📅 Utolsó adat: {last_time.strftime('%Y-%m-%d %H:%M')}")
            print(f"⏱️ Időtartam: {(last_time - first_time).days} nap")

            return first_time, last_time
        else:
            print("❌ Nincs adat!")
            return None, None
    except Exception as e:
        print(f"❌ Hiba: {e}")
        return None, None

def test_statistics_api():
    """Statistics API teszt (long-term statistics)"""
    print("\n" + "=" * 80)
    print("📊 STATISTICS API (long-term statistics - NEM törli a purge)")
    print("=" * 80)

    end_time = datetime.now()
    start_time = end_time - timedelta(days=60)

    url = f"{HA_URL}/api/history/statistics_during_period"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

    payload = {
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "statistic_ids": [ENTITY_ID],
        "period": "hour"
    }

    print(f"Lekérdezés: {start_time.strftime('%Y-%m-%d')} - {end_time.strftime('%Y-%m-%d')}")

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data and ENTITY_ID in data and data[ENTITY_ID]:
            stats = data[ENTITY_ID]
            print(f"✅ Találatok: {len(stats)} statisztikai rekord")

            # Első és utolsó
            first_time = datetime.fromisoformat(stats[0]["start"].replace("Z", "+00:00"))
            last_time = datetime.fromisoformat(stats[-1]["start"].replace("Z", "+00:00"))

            print(f"📅 Első adat: {first_time.strftime('%Y-%m-%d %H:%M')}")
            print(f"📅 Utolsó adat: {last_time.strftime('%Y-%m-%d %H:%M')}")
            print(f"⏱️ Időtartam: {(last_time - first_time).days} nap")

            return first_time, last_time
        else:
            print("❌ Nincs statisztikai adat vagy az entitás nincs rögzítve!")
            return None, None
    except Exception as e:
        print(f"❌ Hiba: {e}")
        return None, None

def main():
    print("🔍 Home Assistant Adattárolás Teszt")
    print()

    hist_first, hist_last = test_history_api()
    stat_first, stat_last = test_statistics_api()

    print("\n" + "=" * 80)
    print("📝 KÖVETKEZTETÉS")
    print("=" * 80)

    if hist_first and stat_first:
        hist_days = (hist_last - hist_first).days
        stat_days = (stat_last - stat_first).days

        print(f"\nHistory API (recorder):  {hist_days} nap adatot tart")
        print(f"Statistics API:          {stat_days} nap adatot tart")

        if stat_days > hist_days:
            print(f"\n✅ A Statistics API TÖBB adatot tart ({stat_days - hist_days} nappal)!")
            print("   → Az addon módosítható, hogy statistics API-t használjon")
        else:
            print("\n⚠️ Mindkét API ugyanannyi vagy kevesebb adatot tart")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
