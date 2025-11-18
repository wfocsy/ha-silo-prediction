# SILO PREDICTION ADDON - PREDIKCIÓS LOGIKA ELEMZÉSE

## 📊 ÁTTEKINTÉS

Az addon **két fő predikciós módszert** használ:
1. **ELSŐDLEGES:** Technológiai adat alapú predikció (0. nap detektálással)
2. **FALLBACK:** Lineáris regressziós predikció (ha 0. nap nem detektálható)

---

## 🔄 FŐ FELDOLGOZÁSI FOLYAMAT (`process()` függvény)

### 1. Adatgyűjtés és mintavételezés
```
45 napos adatok lekérése (History API)
    ↓
6 ÓRÁS MINTAVÉTELEZÉS (7:00, 13:00, 19:00, 1:00) - napi 4 adatpont
    ↓
sample_daily_data() függvény
```

**KRITIKUS PONT:** Csak 6 órás mintavételezés van, **NINCS 5 perces** feltöltés detektáláshoz!

### 2. Aktív feltöltés ellenőrzés (NYERS adatokból!)
```python
# Sor 1305-1340: Aktív feltöltés detektálás
if len(raw_data) >= 5:
    recent_raw = raw_data[-5:]  # Utolsó ~5-10 perc

    # Keresés: >30 kg emelkedés az utolsó 5 percben?
    if max_weight_increase > 30:
        # → FELTÖLTÉS ALATT
        # Szenzor frissítése "Feltöltés alatt" státusszal
        return
```

**Logika:**
- ✅ Használ **nyers adatokat** (nem 6 órás mintavételezést)
- ✅ Utolsó 5 perc vizsgálata
- ✅ 30 kg-os küszöb
- ❌ **NEM használ 5 perces mintavételezést**
- ❌ **NEM detektálja a feltöltés befejezését** (10 perc csend logika NINCS)

### 3. Ciklus kezdet (0. nap) detektálás

```
detect_cycle_start() függvény
    ↓
ELSŐDLEGES módszer: Csend periódus keresése
    5+ napos periódus: súly < 1000 kg, fogyasztás < 50 kg/nap
    Csend után: 3000kg+ ugrás → ELSŐ FELTÖLTÉS
    ↓
FALLBACK módszer (ha nincs csend):
    Nagy feltöltés keresése: 5000kg+ ugrás (sor 428)
    ↓
0. nap keresése:
    Első 100kg+ napi fogyasztás feltöltés után
```

**Fontosak:**
- ✅ 5000kg fallback küszöb (javítva 10000kg-ról)
- ✅ 45 napos purge_keep_days beállítás
- ⚠️ Jelenleg még nincs elég adat (csak 10 nap)

---

## 🎯 PREDIKCIÓS MÓDSZEREK

### A) ELSŐDLEGES: Technológiai adat alapú predikció

**Előfeltétel:** 0. nap sikeresen detektálva

**Lépések:**

1. **Folyamatos görbe készítése** (`create_continuous_curve()`)
   ```python
   # Sor 453-507
   # Feltöltések "kiszűrése" - mintha folyamatos lenne a fogyás
   normalized_weight = weight - cumulative_refill_offset
   ```

2. **Madár darabszám kalkuláció** (`calculate_daily_bird_count()`)
   ```python
   # Sor 509-576
   # Napi fogyasztás / Technológiai adat (g/madár/nap) = Madárszám
   daily_consumption_kg = prev_weight - curr_weight
   bird_count = actual_consumption_g / expected_per_bird_g
   ```

   **Logika:**
   - Csak **7:00-as adatpontokat** használ (napi 1 összehasonlítás)
   - Mai 7:00 - Tegnapi 7:00 = **Tegnapi fogyasztás**
   - Tegnapi tech adatot használ

3. **Korrekciós szorzó számítása** (`calculate_correction_factor()`)
   ```python
   # Sor 578-650
   # Valós fogyás / Várható tech fogyás = Korrekciós szorzó
   correction_factor = total_actual / total_expected
   ```

   **Példák:**
   - 1.00 = pontos egyezés
   - 1.05 = 5%-kal TÖBB fogy
   - 0.95 = 5%-kal KEVESEBB fogy

4. **Előrejelzés iteratív szimulációval** (`calculate_prediction_with_tech_data()`)
   ```python
   # Sor 652-745
   # ÓRÁNKÉNTI iteráció (nem napi!)
   while weight > 0:
       expected_per_bird_g = tech_data[day]
       total_daily_kg = (expected_per_bird_g * avg_bird_count) / 1000
       corrected_daily_kg = total_daily_kg * correction_factor
       hourly_kg = corrected_daily_kg / 24.0
       weight -= hourly_kg
       hours_elapsed += 1
   ```

   **Előnyök:**
   - ✅ Figyelembe veszi a madarak növekedését (tech adat változik naponta)
   - ✅ Korrekciós szorzóval finomít
   - ✅ **VALÓS jelenlegi súlyt használ** (nem normalizáltat!)

5. **Dátum formázás** (`_format_prediction_with_window()`)
   ```python
   # Sor 1022-1086
   # 2 órás időablak + relatív dátum
   if days_diff == 0:
       date_str = "Ma"
   elif days_diff == 1:
       date_str = "Holnap"
   elif days_diff == 2:
       date_str = "Holnapután"

   # Kimenet: "Ma 18-20 óra között (~19:04)"
   ```

   **✅ Már van emberi olvasható formátum!**

### B) FALLBACK: Lineáris regressziós predikció

**Előfeltétel:** 0. nap NEM detektálható

**Lépések:**

1. **Utolsó feltöltés keresése**
   ```python
   # Sor 764-783
   for i in range(1, len(data)):
       if weight_change > 3000:
           last_refill_index = i
   ```

2. **Lineáris regresszió** (scipy.stats.linregress)
   ```python
   # Sor 788-797
   slope, intercept, r_value, ... = stats.linregress(timestamps, weights)
   ```

3. **0 kg előrejelzés**
   ```python
   # Sor 807-823
   hours_until_empty = -current_weight / slope
   prediction_datetime = now + timedelta(hours=hours_until_empty)
   ```

**Hátrányok:**
- ❌ Nem veszi figyelembe a madarak növekedését
- ❌ Nincs madárszám becslés
- ✅ De egyszerű és gyors

---

## ⚡ FELTÖLTÉS UTÁNI FRISSÍTÉS

```python
# Sor 1556-1565: run() függvényben
if refill_detected:
    logger.info("⚡ Feltöltés detektálva! Várakozás 20 perc...")
    time.sleep(20 * 60)  # 20 perc várakozás

    # Újra futtatás
    for silo in self.silos:
        silo.process()
```

**Logika:**
- Feltöltés detektálva → 20 perc várakozás
- Újra futtatás (új adatok lekérése)
- ❌ **NEM figyeli a feltöltés befejezését** (nincs 10 perces logika)

---

## 📅 FRISSÍTÉSI GYAKORISÁG

```python
# Sor 1537-1569: run() függvényben
# Normál: 24 óránként
time.sleep(self.update_interval)  # 86400 sec = 24 óra

# Feltöltés után: 20 perc várakozás + azonnali frissítés
```

**Problémák:**
- ⚠️ 24 órás frissítési intervallum **túl ritka** a november 18-i helyzethez
- ⚠️ Feltöltés után 20 perc múlva csak **1 adatponttal több** lesz (6 órás mintavételezés!)

---

## 🔍 KRITIKUS KÜLÖNBSÉGEK A TERVEZETT ÉS JELENLEGI LOGIKA KÖZÖTT

| Funkció | Tervezett (improved_validation.py) | Jelenlegi (addon) |
|---------|-----------------------------------|-------------------|
| **Feltöltés detektálás mintavételezés** | ✅ 5 perces mintavételezés | ❌ 6 órás mintavételezés |
| **Feltöltés befejezés detektálás** | ✅ 10 perc csend logika | ❌ Nincs |
| **Feltöltés utáni predikció** | ✅ Azonnali (feltöltés vége után) | ⚠️ 20 perc várakozás |
| **Emberi olvasható dátum** | ✅ "Ma 18-20 óra között" | ✅ **Már van!** (sor 1067-1081) |
| **Frissítési gyakoriság** | ✅ Naponta + feltöltés után azonnal | ⚠️ 24 óránként + 20 perc feltöltés után |

---

## 🎯 NOVEMBER 18-I HELYZET ELEMZÉSE

**Probléma:**
1. Feltöltés: November 18, 12:00-13:00 (CSV szerint ~10000 kg)
2. Addon 20 perc várakozás után újra futott: ~13:20
3. **Új 6 órás adatpont csak 18:00-kor lesz!** (következő: 19:00)
4. Így csak **1 adatponttal** tud dolgozni (18:00), ami kevés predikciós görbéhez

**Megoldás:**
- ✅ Használni kell a **nyers adatokat** is (live_prediction_now.py script mutatja)
- ✅ 5 perces mintavételezés bevezetése feltöltés detektáláshoz
- ✅ Feltöltés befejezés detektálás (10 perc csend)

---

## 📝 ÖSSZEFOGLALÁS

### ✅ Amit JÓL csinál az addon:
1. **Technológiai adat alapú predikció** - pontos és figyelembe veszi a madarak növekedését
2. **Madárszám becslés** - működik
3. **Korrekciós szorzó** - finomít a valós adatokkal
4. **Emberi olvasható dátum** - már van "Ma 18-20 óra között" formátum
5. **Fallback módszer** - ha nincs 0. nap, akkor is van predikció

### ❌ Amit JAVÍTANI kell:
1. **5 perces mintavételezés** feltöltés detektáláshoz
2. **10 perces feltöltés befejezés** detektálás
3. **Feltöltés utáni azonnali predikció** (ne várjon 20 percet, hanem figyelje a befejezést)
4. ~~Emberi olvasható dátum~~ (már van!)

### ⚠️ Jelenlegi probléma (Nov 18):
- Feltöltés 12:00-13:00
- Addon 13:20-kor futott (20 perc várakozás után)
- **Csak 1 új 6 órás adatpont** (18:00) → kevés predikciós görbéhez
- Következő adatpont: 00:00 (holnap éjfél)
- **Csak holnap reggel** (3+ adatpont után) lesz használható predikció

---

## 🚀 JAVASLAT

**Integráljuk az improved_validation.py logikáját az addonba:**

1. **Feltöltés detektálás javítása:**
   - Használjunk 5 perces mintavételezést csak feltöltés detektáláshoz
   - Ne módosítsuk a predikciós 6 órás mintavételezést!

2. **Feltöltés befejezés detektálás:**
   - 10 perc (2x5 perc minta) csend → feltöltés vége
   - Ekkor azonnal készítsen predikciót (ne várjon 20 percet!)

3. **Predikciós finomítás:**
   - Használja a jelenlegi tech adatos módszert
   - Csak a dátum formázás finomítása (ami már jó!)

4. **Tesztelés:**
   - Validáció CSV adatokkal
   - Élő tesztelés a következő feltöltésnél
