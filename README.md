# Home Assistant Silo Prediction

Ez a repó egy Home Assistant Add-on-t és egy custom komponenst tartalmaz, amely előrejelzi, mikor fog kiürülni a siló (pl. takarmány mérleg alapján).

## Tartalom
- `custom_components/silo_prediction/` – HACS custom component (NEM ajánlott Home Assistant OS alatt)
- `silo_prediction_addon/` – Home Assistant Add-on (Docker konténer, REST API-val, minden szükséges csomaggal)
- `repository.json` – Add-on Store kompatibilitás

## Telepítés Home Assistant Add-on Store-ból
1. Nyisd meg a Home Assistantot.
2. Navigálj: Beállítások → Kiegészítők → Kiegészítő tárolók → "Tároló hozzáadása"
3. Add meg ezt a repó URL-t:
   ```
   https://github.com/wfocsy/ha-silo-prediction
   ```
4. Telepítsd a `silo_prediction_addon`-t a listából.
5. Indítsd el az Add-on-t, állítsd be a szükséges adatbázis elérési adatokat a config.json-ban.

## REST API használata
Az Add-on egy Flask alapú REST API-t indít, amely a predikciós eredményt adja vissza.

- Példa endpoint: `http://<homeassistant-ip>:5000/predict`
- Integráld Home Assistant RESTful szenzorral.

## Fejlesztői információk
- A custom component csak akkor működik, ha a szükséges Python csomagok telepíthetők (nem Home Assistant OS!).
- Az Add-on minden szükséges csomagot tartalmaz Dockerben.

## Licenc
MIT
# ha-silo-prediction
HASiloScalePredection
Hello CFM
