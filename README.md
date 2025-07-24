## Telepítés és használat Home Assistant OS alatt

1. **Add-on repó hozzáadása**
   - Home Assistantban menj a **Beállítások → Kiegészítők → Kiegészítő tárolók** menüpontra.
   - Kattints a jobb alsó sarokban a **Tároló hozzáadása** gombra.
   - Add meg ezt a repó URL-t:
     ```
     https://github.com/wfocsy/ha-silo-prediction
     ```
   - Mentsd el, majd a listában megjelenik a `silo_prediction_addon`.

2. **Add-on telepítése**
   - Válaszd ki a `silo_prediction_addon`-t a listából.
   - Kattints a **Telepítés** gombra.

3. **Konfiguráció**
   - Szükség esetén szerkeszd a `config.json`-t (pl. adatbázis elérés, entity_id).
   - Alapértelmezés szerint a Home Assistant saját MariaDB-jét használja (host: `core-mariadb`).

4. **Add-on indítása**
   - Kattints az **Indítás** gombra.
   - Az Add-on elindít egy REST API-t a 5000-es porton.

5. **RESTful szenzor beállítása Home Assistantban**
   - Hozz létre egy RESTful szenzort a configuration.yaml-ban vagy a GUI-ban, pl.:
     ```yaml
     sensor:
       - platform: rest
         name: Silo 0kg becsült idő
         resource: "http://localhost:5000/predict"
         value_template: "{{ value_json.predicted_0kg }}"
         json_attributes:
           - status
           - error
     ```
   - Indítsd újra a Home Assistantot vagy töltsd újra a szenzorokat.

6. **Eredmény**
   - A szenzor állapota a becsült 0kg időpont lesz, extra attribútumokkal (pl. status, error).

**Megjegyzés:**
- A custom_components/HACS verziót Home Assistant OS alatt nem lehet használni, csak az Add-on működik!
## Predikciós (business) logika működése

A predikciós logika célja, hogy előrejelezze, mikor fog a siló tömege elérni a 0 kg-ot, azaz mikor fogy ki a takarmány. Az algoritmus lépései:

1. **Adatgyűjtés**: Az Add-on (vagy a custom component) lekérdezi a Home Assistant recorder adatbázisából (MariaDB) a kiválasztott mérleg szenzor (`entity_id`) elmúlt 30 napos állapotváltozásait (timestamp + súlyérték párok).

2. **Adattisztítás és előfeldolgozás**:
   - Csak a pozitív, valós számként értelmezhető súlyértékek maradnak.
   - Az adatok óránkénti átlagolással újramintavételezve lesznek, hogy kisimítsák a zajt és csökkentsék a kiugró értékek hatását.
   - Ha nincs elég adat, vagy az adatok nem alkalmasak predikcióra, a rendszer hibát jelez.

3. **Polinomiális regresszió**:
   - A tisztított idősor adatokra egy 2. fokú polinomiális regressziós modellt illesztünk (scikit-learn, numpy).
   - Az időtengelyen minden adatpontot átalakítunk: az első adatponttól eltelt másodpercek száma lesz a független változó.
   - A modell célja, hogy a súlycsökkenés trendjét megbecsülje, és extrapolálja a jövőbe.

4. **Előrejelzés**:
   - A modell segítségével előrejelzünk a jövőbe (akár 60 napra), és megkeressük azt az időpontot, amikor a becsült súly először eléri vagy átlépi a 0 kg-ot.
   - Ha a siló már üres (utolsó súly <= 0), az aktuális időpontot adja vissza.
   - Ha a predikció nem stabil vagy nem található 0 kg-os pont, hibát jelez.

5. **Időzóna kezelés**:
   - Az előrejelzett időpontot UTC-ből a Home Assistant helyi időzónájára konvertálja.

6. **Eredmény**:
   - A REST API vagy a szenzor állapota a becsült 0 kg időpont (helyi időzónában), illetve extra attribútumként az utolsó futás ideje és a predikció nyers (UTC) értéke is elérhető.

**Fontos:**
- A predikció pontossága függ a szenzor adatok minőségétől, a fogyás trendjének stabilitásától és a múltbeli adatok mennyiségétől.
- A logika minden szükséges adatfeldolgozást, tisztítást és hibakezelést automatikusan elvégez.
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
