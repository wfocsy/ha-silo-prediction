# Silo Prediction Add-on

Egyszerűsített Home Assistant add-on siló kiürülési előrejelzéshez lineáris regresszió alapján.

## Működés

Az add-on:
1. Lekéri a megadott szenzor történeti adatait a Home Assistant API-ból
2. Óránkénti mintavételezést végez az adatokon
3. Automatikusan detektálja és eltávolítja a feltöltéseket
4. Lineáris regresszióval előrejelzi, mikor éri el a súly a megadott küszöböt
5. Létrehoz egy új szenzort a Home Assistantban az előrejelzéssel

## Konfiguráció

```yaml
entity_id: sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly  # A siló súly szenzor
sensor_name: CFM 3 Hall Silo Empty Prediction              # Az új szenzor neve
refill_threshold: 1000                                      # Küszöbérték kg-ban
max_capacity: 20000                                         # Max kapacitás kg-ban
prediction_days: 10                                         # Hány nap adat alapján
update_interval: 3600                                       # Frissítési intervallum másodpercben
```

## Egyszerűsített architektúra

A korábbi komplex verzióval szemben:
- ✅ Nincs Flask web szerver
- ✅ Nincs MySQL adatbázis függőség
- ✅ Nincs multi-silo támogatás (egyszerűség kedvéért)
- ✅ Minimális függőségek: requests, numpy, scipy
- ✅ Közvetlen Home Assistant API használat
- ✅ Python 3.11-slim Docker image (könnyebb)

## Telepítés

1. Másold az addon mappát a Home Assistant `/addons/` könyvtárába
2. Supervisor > Add-on Store > Local add-ons > Silo Prediction
3. Konfiguráld az opciókat
4. Start & Auto-start engedélyezése

## Logok

Logok helye: `/app/logs/silo_prediction.log`

Vagy az add-on Log nézetében a Home Assistantban.
