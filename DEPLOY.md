# Automatikus Telepítés Home Assistant OS-re

## Előkészületek (egyszer kell megcsinálni)

### 1. SSH Hozzáférés Beállítása

A Home Assistant-ban:
1. Settings → Add-ons → Add-on Store
2. Telepítsd az **"Advanced SSH & Web Terminal"** add-on-t
3. Configuration fül:
   ```yaml
   password: ""  # Hagyd üresen, kulcsot használunk
   authorized_keys:
     - "ssh-rsa AAAAB3Nza..."  # A publikus SSH kulcsod
   port: 22
   ```
4. Indítsd el az add-on-t

### 2. SSH Kulcs Generálása (ha még nincs)

Mac/Linux terminálon:
```bash
# SSH kulcs generálása (ha még nincs)
ssh-keygen -t rsa -b 4096 -C "homeassistant-deploy"

# Publikus kulcs megjelenítése
cat ~/.ssh/id_rsa.pub
```

Másold be ezt a kulcsot a Home Assistant SSH add-on konfigurációjába!

### 3. Szkript Konfigurálása

Nyisd meg a `deploy_to_haos.sh` fájlt és állítsd be:

```bash
HAOS_HOST="homeassistant.local"  # Vagy IP cím (pl. 192.168.1.100)
HAOS_PORT="22"                   # SSH port (általában 22 vagy 22222)
HAOS_USER="root"                 # Felhasználónév
```

---

## Használat

### Automatikus Telepítés (EGYSZERŰ!)

```bash
cd /Users/FeherZsolt/Library/CloudStorage/GoogleDrive-wfocsy@gmail.com/Egyéb\ számítógépek/Saját\ Mac\ mini/Arduino/CFMServer/SiloPrediction/ha-silo-prediction

./deploy_to_haos.sh
```

### Mit csinál a szkript?

1. ✅ SSH kapcsolat ellenőrzése
2. ✅ `/addons/local/silo_prediction_addon/` mappa létrehozása
3. ✅ Régi fájlok törlése
4. ✅ Új fájlok feltöltése
5. ✅ Verzió ellenőrzése

### Utána (kézi lépés)

1. Nyisd meg: Settings → Add-ons → Silo Prediction
2. Kattints: **Restart**
3. Nézd meg a **Log** fület

---

## Gyakori Hibák

### "Connection refused"

**Probléma:** SSH add-on nem fut vagy rossz port.

**Megoldás:**
1. Ellenőrizd, hogy az SSH add-on fut-e
2. Ellenőrizd a port számot (22 vagy 22222)

### "Permission denied"

**Probléma:** SSH kulcs nincs beállítva.

**Megoldás:**
1. Generálj SSH kulcsot: `ssh-keygen`
2. Add hozzá a publikus kulcsot az SSH add-on-hoz
3. Indítsd újra az SSH add-on-t

### "No such file or directory"

**Probléma:** Rossz forrásmappa útvonal.

**Megoldás:**
Futtasd a szkriptet a repository mappájából:
```bash
cd /Users/FeherZsolt/.../ha-silo-prediction
./deploy_to_haos.sh
```

---

## Manuális Telepítés (ha a szkript nem működik)

```bash
# 1. SSH kapcsolódás
ssh root@homeassistant.local

# 2. Mappa létrehozása
mkdir -p /addons/local/silo_prediction_addon

# 3. Kilépés
exit

# 4. Fájlok másolása
scp -r silo_prediction_addon/* root@homeassistant.local:/addons/local/silo_prediction_addon/

# 5. Home Assistant UI → Settings → Add-ons → Silo Prediction → Restart
```

---

## Gyors Frissítés Workflow

```bash
# 1. Módosítsd a kódot
vim silo_prediction_addon/silo_prediction.py

# 2. Növeld a verziót
vim silo_prediction_addon/config.yaml
# version: "6.5.0" → "6.5.1"

# 3. Commit GitHub-ra (opcionális)
git add .
git commit -m "v6.5.1: változások"
git push

# 4. AUTOMATIKUS TELEPÍTÉS
./deploy_to_haos.sh

# 5. Home Assistant UI → Restart add-on
```

**Kész!** 🎉
