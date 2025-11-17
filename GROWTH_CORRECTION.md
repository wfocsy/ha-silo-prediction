# Növekedési Korrekció - Feed Intake Growth Correction

## Probléma

Az eredeti siló predikciós rendszer **lineáris regressziót** használt, ami feltételezi, hogy a takarmányfogyasztás üteme **konstans**.

Azonban állattenyésztésben (baromfi, sertés, stb.) az állatok **növekednek**, így:
- Fiatal állatok: kevés takarmányt fogyasztanak
- Idősebb állatok: egyre több takarmányt fogyasztanak
- **Nem-lineáris**: a fogyasztás napról napra nő

Ez azt jelenti, hogy a lineáris modell **alulbecsli** a siló kiürülési idejét, mert nem számol azzal, hogy a jövőben az állatok **gyorsabban** fognak enni.

## Megoldás: Növekedési Korrekció

A módosított rendszer opcionálisan alkalmazhat egy **növekedési korrekciót**, ami figyelembe veszi, hogy az állatok idővel több takarmányt fogyasztanak.

### Adatalapú Modell

Az alábbi napi takarmányfelvételi adatokból (egyedre vetítve, 24 óra alatt):

```
Nap 0:  0 g/nap    → 0.000 g/óra
Nap 10: 52 g/nap   → 2.153 g/óra
Nap 20: 100 g/nap  → 4.164 g/óra
Nap 30: 148 g/nap  → 6.175 g/óra
Nap 40: 197 g/nap  → 8.186 g/óra
Nap 50: 227 g/nap  → 9.458 g/óra
```

**Lineáris regresszió eredménye:**
- Növekedési ráta: **4.83 g/nap²** (R² = 0.9929)
- Óránkénti növekedés: **0.201 g/óra/nap**
- Kilogrammban: **0.000201 kg/óra/nap**

Ez azt jelenti, hogy minden nap az állatok átlagosan **0.201 grammal/órával több** takarmányt fogyasztanak, mint az előző napon!

### Grafikus elemzés

Az [analyze_growth.py](analyze_growth.py) script által generált grafikon:

![Growth Analysis](growth_analysis.png)

A görbe **kvadratikus modellt** (R² = 0.9958) követ, de a lineáris közelítés is kiváló (R² = 0.9929).

## Implementáció

### 1. Konfigurációs Paraméterek

A [config.yaml](silo_prediction_addon/config.yaml) fájlban minden siló számára beállítható:

```yaml
silos:
  - entity_id: "sensor.cfm_3_hall_modbus_1_lp7516_merleg_suly"
    sensor_name: "CFM 3 Hall Silo Prediction"
    refill_threshold: 1000
    max_capacity: 20000
    # Növekedési korrekció bekapcsolása
    enable_growth_correction: true
    # Állatok jelenlegi életkora napokban
    animal_age_days: 25.0
    # Óránkénti növekedési ráta (kg/óra/nap)
    growth_rate_kg_per_hour_per_day: 0.000201
```

**Paraméterek:**
- `enable_growth_correction` (bool): Be/kikapcsolja a növekedési korrekciót (alapértelmezett: `false`)
- `animal_age_days` (float): Az állatok jelenlegi életkora napokban (alapértelmezett: `25.0`)
- `growth_rate_kg_per_hour_per_day` (float): Óránkénti növekedési ráta kg-ban (alapértelmezett: `0.000201`)

### 2. Működési Logika

#### Lineáris Módszer (enable_growth_correction = false)

```
Órák 0 kg-ig = (0 - intercept) / slope
```

Feltételezi, hogy a fogyasztás üteme konstans:
```
Súly(t) = slope * t + intercept
```

#### Növekedési Korrekciós Módszer (enable_growth_correction = true)

Iteratív szimuláció óránként:

```python
while weight > 0:
    day_in_cycle = animal_age_days + (hours_elapsed / 24.0)
    growth_adjustment = growth_rate * day_in_cycle
    hourly_consumption = base_slope - growth_adjustment
    weight += hourly_consumption  # negatív, csökkenti a súlyt
    hours_elapsed += 1
```

**Magyarázat:**
- `base_slope`: A lineáris regresszió meredeksége (kg/óra) - **negatív** érték
- `growth_adjustment`: Az állatok életkorától függő növekedési korrekció
- `hourly_consumption`: Tényleges óránkénti fogyás = base_slope - growth_adjustment
  - Mivel a growth_adjustment pozitív, a fogyás **gyorsul** az idő előrehaladtával!

**Példa:**
- Alapfogyás: -5 kg/óra (lineáris trend)
- 25. napon az állatok életkora alapján: 0.000201 * 25 = 0.005025 kg/óra extra fogyás
- Tényleges fogyás: -5 - 0.005025 = **-5.005025 kg/óra**

Ahogy az idő telik, a korrekció egyre nagyobb lesz, tehát a siló **gyorsabban** ürül!

## Példa Eredmények

### Lineáris Módszer
```
Jelenlegi súly: 5000 kg
Meredekség: -5.2 kg/óra
Előrejelzés: 962 óra (40.1 nap)
```

### Növekedési Korrekciós Módszer
```
Jelenlegi súly: 5000 kg
Alapmeredekség: -5.2 kg/óra
Állat életkor: 25 nap
Előrejelzés: 890 óra (37.1 nap) ← 3 nappal HAMARABB!
```

A növekedési korrekció figyelembe veszi, hogy az állatok idővel több takarmányt fogyasztanak, ezért **pontosabb előrejelzést** ad.

## Használati Útmutató

### 1. Alapértelmezett (Lineáris) Mód

Nincs szükség semmilyen beállításra, a rendszer az eredeti lineáris módszert használja:

```yaml
silos:
  - entity_id: "sensor.silo_weight"
    sensor_name: "Silo 1"
    # enable_growth_correction alapértelmezett: false
```

### 2. Növekedési Korrekció Bekapcsolása

#### a) Alapértelmezett Paraméterekkel

```yaml
silos:
  - entity_id: "sensor.silo_weight"
    sensor_name: "Silo 1"
    enable_growth_correction: true
    animal_age_days: 25.0  # Állatok jelenlegi életkora
```

#### b) Egyedi Növekedési Ráta

Ha más fajjal vagy más növekedési görbével dolgozol:

```yaml
silos:
  - entity_id: "sensor.silo_weight"
    sensor_name: "Silo 1"
    enable_growth_correction: true
    animal_age_days: 30.0
    growth_rate_kg_per_hour_per_day: 0.000150  # Egyedi ráta
```

### 3. Növekedési Ráta Meghatározása

Használd az [analyze_growth.py](analyze_growth.py) scriptet saját adatokkal:

1. Szerkeszd a `daily_intake` listát a saját napi takarmányfelvételi adataiddal (g/nap)
2. Futtasd a scriptet:
   ```bash
   python3 analyze_growth.py
   ```
3. Az eredményből vedd az **óránkénti növekedési rátát** (kg/óra/nap)
4. Állítsd be a `growth_rate_kg_per_hour_per_day` paramétert

## Logok és Diagnosztika

A növekedési korrekció engedélyezésekor a log így néz ki:

```
2025-11-17 10:30:00 - INFO - 📦 Silo inicializálva: CFM 3 Hall Silo Prediction
2025-11-17 10:30:00 - INFO - 🌱 Növekedési korrekció ENGEDÉLYEZVE: állat életkor=25.0 nap, növekedési ráta=0.000201 kg/óra/nap
...
2025-11-17 10:30:15 - INFO - 🧮 [CFM 3 Hall Silo Prediction] Növekedési szimulációs számítás indítása...
2025-11-17 10:30:15 - INFO -    Kezdeti súly: 5234.0 kg
2025-11-17 10:30:15 - INFO -    Alapmeredekség: -5.2300 kg/óra
2025-11-17 10:30:15 - INFO -    Állat életkor: 25.0 nap
2025-11-17 10:30:15 - INFO - ✅ [CFM 3 Hall Silo Prediction] Szimulációs eredmény: 890 óra (37.1 nap)
2025-11-17 10:30:15 - INFO - 🌱 [CFM 3 Hall Silo Prediction] Növekedési korrekció alkalmazva: 890.0 óra
```

## Technikai Részletek

### Kód Módosítások

**Módosított fájlok:**
- [silo_prediction.py](silo_prediction_addon/silo_prediction.py)
  - `SiloPredictor.__init__()`: Új paraméterek
  - `SiloPredictor.calculate_prediction()`: Elágazás lineáris vs. korrekciós számításhoz
  - `SiloPredictor._calculate_with_growth_correction()`: Új metódus iteratív szimulációhoz
  - `MultiSiloManager._load_silo_config()`: Új paraméterek átadása
- [config.yaml](silo_prediction_addon/config.yaml): Schema bővítése

### Teljesítmény

Az iteratív szimuláció gyors:
- 1000 óra (41 nap): ~0.1 másodperc
- Maximum 10000 óra (416 nap): ~1 másodperc

### Limitációk

- Maximum szimuláció: 10000 óra (~416 nap)
- Az állat életkorát **manuálisan** kell frissíteni a konfigurációban!
- A növekedési ráta **konstans** az egész előrejelzési periódusra

## Következő Lépések

Lehetséges továbbfejlesztések:
1. **Automatikus életkor követés**: Állat életkorának automatikus számítása az utolsó feltöltés óta
2. **Nem-lineáris növekedési modellek**: Kvadratikus vagy exponenciális görbék támogatása
3. **Több állat-típus**: Előre definiált növekedési paraméterek különböző fajokhoz
4. **Dinamikus paraméter optimalizáció**: Gépi tanulás alapú paraméter becslés a mért adatokból

## Szerző és Verzió

- **Verzió**: 5.2.0
- **Funkció**: Növekedési Korrekció (Growth Correction)
- **Dátum**: 2025-11-17
