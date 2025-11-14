# Silo Prediction Telepítési Útmutató

## Áttekintés

A Silo Prediction rendszer két részből áll:
1. **Add-on** (Docker konténer) - Háttérben fut, adatokat gyűjt, előrejelzést számol, REST API-t szolgáltat
2. **RESTful Sensor** - Home Assistant szenzor ami az Add-on API-ját használja

## 1. Add-on Telepítése

### 1.1 Add-on Hozzáadása Home Assistant-hoz

1. Másold a `silo_prediction_addon` mappát a Home Assistant add-on könyvtárába:
   ```
   /addons/silo_prediction_addon/
   ```

2. Vagy add hozzá a repository-t HAOS-ben:
   - Settings → Add-ons → Add-on Store → ⋮ (jobb felső sarokban) → Repositories
   - Add meg: `https://github.com/wfocsy/ha-silo-prediction`

### 1.2 Add-on Konfigurálása

1. Telepítsd az Add-on-t a Store-ból
2. A Configuration fülön ellenőrizd/módosítsd:

```yaml
log_level: info
homeassistant_token: ""  # Nem szükséges - az Add-on közvetlenül az adatbázishoz csatlakozik
database:
  host: core-mariadb
  port: 3306
  username: homeassistant
  password: Pozsi1981
  database: homeassistant
silos:
  - name: CFM 3 Hall Silo
    entity_id: sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly
    prediction_entity: sensor.cfm_3_hall_silo_empty_prediction
    max_capacity: 20000
    refill_threshold: 10000
    refill_time_window: 45
    area: cfm_3_hall
  - name: CFM 1 Hall Silo (Bosche)
    entity_id: sensor.cfm_1_hall_silo_scale_bosche_silo_merleg_suly
    prediction_entity: sensor.cfm_1_hall_silo_empty_prediction
    max_capacity: 20000
    refill_threshold: 10000
    refill_time_window: 45
    area: cfm_1_hall
prediction:
  history_days: 10
  min_data_points: 24
  update_interval: 3600
  refill_detection_threshold: 8000
```

3. Indítsd el az Add-on-t
4. Engedélyezd a "Start on boot" opciót
5. Engedélyezd a "Watchdog" opciót

### 1.3 Ellenőrzés

Nézd meg az Add-on logokat:
- Settings → Add-ons → Silo Prediction Add-on → Log

Keresed ezeket:
```
INFO:__main__:Retrieved 692 valid data points from statistics for sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly
INFO:__main__:Prediction calculated: empty at 2025-11-16 15:00:07, current: 2174.28kg, rate: 3360.77kg/day
INFO:__main__:Updated entity sensor.cfm_3_hall_silo_empty_prediction successfully in database
```

## 2. RESTful Sensor Konfigurálása

Az Add-on **nem hoz létre automatikusan** Home Assistant entitásokat. Helyette egy **REST API**-t szolgáltat, amit RESTful Sensor-okkal lehet lekérdezni.

### 2.1 Configuration.yaml Szerkesztése

Nyisd meg a `configuration.yaml` fájlt (File Editor Add-on-nal vagy SSH-val):

```yaml
# configuration.yaml
sensor: !include restful_sensor_config.yaml
```

### 2.2 RESTful Sensor Fájl Létrehozása

Hozz létre egy `restful_sensor_config.yaml` fájlt ugyanabban a könyvtárban:

```yaml
# restful_sensor_config.yaml
# CFM 3 Hall Silo Empty Prediction
- platform: rest
  name: "CFM 3 Hall Silo Empty Prediction"
  unique_id: cfm_3_hall_silo_empty_prediction
  resource: "http://localhost:5001/api/silo/CFM%203%20Hall%20Silo/prediction"
  scan_interval: 3600
  device_class: timestamp
  value_template: "{{ value_json.prediction.empty_datetime if value_json.prediction else 'unknown' }}"
  json_attributes_path: "$.prediction"
  json_attributes:
    - current_weight
    - consumption_rate_kg_day
    - prediction_accuracy
    - data_points_used
    - method
    - days_remaining

# CFM 1 Hall Silo (Bosche) Empty Prediction
- platform: rest
  name: "CFM 1 Hall Silo Empty Prediction"
  unique_id: cfm_1_hall_silo_empty_prediction
  resource: "http://localhost:5001/api/silo/CFM%201%20Hall%20Silo%20(Bosche)/prediction"
  scan_interval: 3600
  device_class: timestamp
  value_template: "{{ value_json.prediction.empty_datetime if value_json.prediction else 'unknown' }}"
  json_attributes_path: "$.prediction"
  json_attributes:
    - current_weight
    - consumption_rate_kg_day
    - prediction_accuracy
    - data_points_used
    - method
    - days_remaining
```

### 2.3 Home Assistant Újraindítás

1. Developer Tools → YAML → Check Configuration
2. Ha OK, akkor: Restart

### 2.4 Ellenőrzés

Néhány perc után a szenzorokat itt láthatod:
- Developer Tools → States → keress rá: `sensor.cfm_3_hall_silo_empty_prediction`

## 3. Hibaelhárítás

### "Entity not found"

- Ellenőrizd hogy az Add-on fut-e
- Nézd meg az Add-on logokat hogy vannak-e hibák
- Teszteld az API-t manuálisan:
  ```bash
  curl http://localhost:5001/api/silo/CFM%203%20Hall%20Silo/prediction
  ```

### "Connection refused"

- Az Add-on nem fut
- Vagy a port nem 5001 (nézd meg a config.yaml-ban a `ports` beállítást)

### "Invalid JSON"

- Az Add-on még nem számolt ki előrejelzést
- Várj pár percet amíg összegyűjt elég adatot

### "Insufficient data"

- Még nincs elég történeti adat (minimum 24 óra)
- Ellenőrizd hogy a mérleg szenzorok (`sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly`) léteznek és adatokat küldenek

## 4. Dashboard Kártya Példa

```yaml
type: entities
title: Siló Állapotok
entities:
  - entity: sensor.cfm_3_hall_silo_empty_prediction
    name: CFM 3 Hall - Kifogyás
    secondary_info: last-updated
  - type: attribute
    entity: sensor.cfm_3_hall_silo_empty_prediction
    attribute: current_weight
    name: Jelenlegi súly
    suffix: " kg"
  - type: attribute
    entity: sensor.cfm_3_hall_silo_empty_prediction
    attribute: consumption_rate_kg_day
    name: Napi fogyás
    suffix: " kg/nap"
  - type: attribute
    entity: sensor.cfm_3_hall_silo_empty_prediction
    attribute: days_remaining
    name: Hátralévő napok
    suffix: " nap"
  - entity: sensor.cfm_1_hall_silo_empty_prediction
    name: CFM 1 Hall (Bosche) - Kifogyás
    secondary_info: last-updated
  - type: attribute
    entity: sensor.cfm_1_hall_silo_empty_prediction
    attribute: current_weight
    name: Jelenlegi súly
    suffix: " kg"
  - type: attribute
    entity: sensor.cfm_1_hall_silo_empty_prediction
    attribute: consumption_rate_kg_day
    name: Napi fogyás
    suffix: " kg/nap"
  - type: attribute
    entity: sensor.cfm_1_hall_silo_empty_prediction
    attribute: days_remaining
    name: Hátralévő napok
    suffix: " nap"
```

## 5. Verziófrissítés

Amikor új verziót telepítesz:
1. Állítsd le az Add-on-t
2. Frissítsd a fájlokat
3. Növeld a verzió számot a `config.yaml`-ban
4. Indítsd újra az Add-on-t
5. **NEM** kell újraindítani a Home Assistant-ot (csak ha változott a `configuration.yaml`)

## Támogatás

Issues: https://github.com/wfocsy/ha-silo-prediction/issues
