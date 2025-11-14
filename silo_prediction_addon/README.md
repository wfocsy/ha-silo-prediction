# Silo Prediction Add-on

Home Assistant add-on több siló kiürülési előrejelzéséhez lineáris regresszió alapján.

## Működés

Az add-on minden konfigurált silohoz:
1. Lekéri a szenzor történeti adatait a Home Assistant API-ból
2. Óránkénti mintavételezést végez az adatokon
3. Automatikusan detektálja és eltávolítja a feltöltéseket
4. Lineáris regresszióval előrejelzi, mikor lesz 0 kg a siloban
5. Két új szenzort hoz létre:
   - Dátum szenzor: mikor lesz 0 kg (YYYY-MM-DD HH:MM)
   - Idő szenzor: hátralévő idő (X nap Y óra formátumban)

## Multi-Silo Konfiguráció

A config felületen tetszőleges számú silót adhatsz hozzá:

```yaml
silos:
  - entity_id: "sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly"
    sensor_name: "CFM 3 Hall Silo Empty Prediction"
    refill_threshold: 1000
    max_capacity: 20000
  - entity_id: "sensor.cfm_1_hall_silo_scale_bosche_silo_merleg_suly"
    sensor_name: "CFM 1 Hall Silo Empty Prediction"
    refill_threshold: 1000
    max_capacity: 20000
prediction_days: 10        # Hány nap adat alapján
update_interval: 3600      # Frissítési intervallum másodpercben
```

### Siló paraméterek

- `entity_id`: A siló súly szenzor entity ID
- `sensor_name`: Az előrejelzési szenzor neve
- `refill_threshold`: Feltöltés detektálás küszöb (kg)
- `max_capacity`: Maximális kapacitás (kg)

### Globális paraméterek

- `prediction_days`: Hány nap történeti adatot használjon (1-30)
- `update_interval`: Frissítési intervallum másodpercben (300-7200)

## Architektúra

- ✅ Multi-silo támogatás dinamikus konfigurációval
- ✅ Minimális függőségek: requests, numpy, scipy
- ✅ Közvetlen Home Assistant API használat
- ✅ Home Assistant base image bashio támogatással
- ✅ Refill detektálás (3000kg küszöb óránkénti átlagolás után)
- ✅ 0 kg előrejelzés (nem threshold alapú)

## Telepítés

1. Másold az addon mappát a Home Assistant `/addons/` könyvtárába
2. Supervisor > Add-on Store > Local add-ons > Silo Prediction
3. Konfiguráld a silókat a config felületen
4. Start & Auto-start engedélyezése

## Létrehozott Szenzorok

Minden silohoz 2 szenzor:
- `sensor.{sensor_name}` - Dátum (pl. "2025-11-21 14:30")
- `sensor.{sensor_name}_time_remaining` - Idő (pl. "5 nap 14 óra")

## Logok

Logok helye: `/app/logs/silo_prediction.log`

Vagy az add-on Log nézetében a Home Assistantban.
