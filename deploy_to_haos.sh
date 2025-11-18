#!/bin/bash
# ====================================================================
# Automatikus feltöltés Home Assistant OS-re SSH-n keresztül
# ====================================================================

set -e  # Kilépés hiba esetén

# KONFIGURÁCIÓ - Állítsd be a saját adataidat!
# ====================================================================
HAOS_HOST="homeassistant.local"  # Vagy IP cím, pl. "192.168.1.100"
HAOS_PORT="22222"                # SSH port (általában 22 vagy 22222)
HAOS_USER="root"                 # Felhasználónév

# Helyi forrásmappa
SOURCE_DIR="$(cd "$(dirname "$0")/silo_prediction_addon" && pwd)"

# Távoli célmappa a HAOS-en
REMOTE_DIR="/addons/local/silo_prediction_addon"

# ====================================================================
# NE MÓDOSÍTSD AZ ALÁBBIAKAT (hacsak nem tudod, mit csinálsz)
# ====================================================================

echo "======================================================================"
echo "🚀 Silo Prediction Add-on Telepítő - Home Assistant OS"
echo "======================================================================"
echo ""
echo "Forrás:  $SOURCE_DIR"
echo "Cél:     $HAOS_USER@$HAOS_HOST:$REMOTE_DIR"
echo "Port:    $HAOS_PORT"
echo ""

# Ellenőrzés: létezik-e a forrásmappa?
if [ ! -d "$SOURCE_DIR" ]; then
    echo "❌ HIBA: Forrásmappa nem található: $SOURCE_DIR"
    exit 1
fi

# Ellenőrzés: létezik-e a config.yaml?
if [ ! -f "$SOURCE_DIR/config.yaml" ]; then
    echo "❌ HIBA: config.yaml nem található: $SOURCE_DIR/config.yaml"
    exit 1
fi

# Verzió kiírása
VERSION=$(grep -E "^version:" "$SOURCE_DIR/config.yaml" | sed 's/version: *"\(.*\)"/\1/')
echo "📦 Verzió: $VERSION"
echo ""

# 1. SSH kapcsolat tesztelése
echo "🔍 1. SSH kapcsolat ellenőrzése..."
if ! ssh -p "$HAOS_PORT" -o ConnectTimeout=5 "$HAOS_USER@$HAOS_HOST" "echo '✅ Kapcsolat OK'" 2>/dev/null; then
    echo "❌ HIBA: Nem lehet csatlakozni a Home Assistant OS-hez!"
    echo ""
    echo "Ellenőrizd:"
    echo "  - HAOS_HOST: $HAOS_HOST"
    echo "  - HAOS_PORT: $HAOS_PORT"
    echo "  - HAOS_USER: $HAOS_USER"
    echo "  - SSH add-on engedélyezve van?"
    exit 1
fi
echo ""

# 2. Célmappa létrehozása (ha nem létezik)
echo "📁 2. Célmappa létrehozása a HAOS-en..."
ssh -p "$HAOS_PORT" "$HAOS_USER@$HAOS_HOST" "mkdir -p $REMOTE_DIR"
echo "   ✅ $REMOTE_DIR létrehozva"
echo ""

# 3. Régi fájlok törlése
echo "🗑️  3. Régi fájlok törlése..."
ssh -p "$HAOS_PORT" "$HAOS_USER@$HAOS_HOST" "rm -rf $REMOTE_DIR/*"
echo "   ✅ Régi fájlok törölve"
echo ""

# 4. Új fájlok feltöltése
echo "📤 4. Új fájlok feltöltése..."
scp -P "$HAOS_PORT" -r "$SOURCE_DIR"/* "$HAOS_USER@$HAOS_HOST:$REMOTE_DIR/"
echo "   ✅ Fájlok feltöltve"
echo ""

# 5. Verzió ellenőrzése távoli gépen
echo "✅ 5. Verzió ellenőrzése..."
REMOTE_VERSION=$(ssh -p "$HAOS_PORT" "$HAOS_USER@$HAOS_HOST" "grep -E '^version:' $REMOTE_DIR/config.yaml | sed 's/version: *\"\(.*\)\"/\1/'")
echo "   📦 Távoli verzió: $REMOTE_VERSION"

if [ "$VERSION" = "$REMOTE_VERSION" ]; then
    echo "   ✅ Verzió egyezik!"
else
    echo "   ⚠️  FIGYELEM: Verzió eltérés!"
    echo "      Helyi:  $VERSION"
    echo "      Távoli: $REMOTE_VERSION"
fi
echo ""

# 6. Kész!
echo "======================================================================"
echo "✅ TELEPÍTÉS SIKERES!"
echo "======================================================================"
echo ""
echo "Következő lépések:"
echo "  1. Nyisd meg a Home Assistant UI-t"
echo "  2. Settings → Add-ons → Silo Prediction"
echo "  3. Kattints a 'Restart' gombra"
echo "  4. Ellenőrizd a logokat (Log fül)"
echo ""
echo "Várható log üzenet:"
echo "  version: \"$VERSION\""
echo ""
echo "======================================================================"
