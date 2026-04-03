#!/bin/bash
# ============================================================
#  build_dmg.sh — LRC Generator macOS Distributor
#  Erstellt eine vollständige, standalone LRC Generator.dmg
#  die man direkt weiterschicken kann. Kein Python oder
#  Terminal beim Empfänger nötig.
#
#  Voraussetzungen (nur für den BUILD-Rechner):
#    brew install python-tk
#    pip3 install stable-ts mutagen customtkinter --break-system-packages
#
#  Aufruf: bash build_dmg.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="LRC Generator"
MAIN_SCRIPT="lrc_generator_app.py"
SPEC_FILE="lrc_generator.spec"
DIST_DIR="$SCRIPT_DIR/dist"
BUILD_DIR="$SCRIPT_DIR/build"
DMG_STAGING="$SCRIPT_DIR/_dmg_staging"
DMG_OUTPUT="$SCRIPT_DIR/LRC-Generator-macOS.dmg"
VOLUME_NAME="LRC Generator"

# ── Farben ────────────────────────────────────────────────────
GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
info() { echo -e "${BLUE}→${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
fail() { echo -e "${RED}✗ FEHLER:${NC} $1"; exit 1; }

echo ""
echo -e "${BLUE}🎵 LRC Generator — macOS App Build${NC}"
echo "======================================"
echo ""

cd "$SCRIPT_DIR"

# ── 1. Voraussetzungen prüfen ──────────────────────────────────
info "Prüfe Python..."
PYTHON=$(command -v python3 || fail "python3 nicht gefunden. Bitte: brew install python-tk")

# Homebrew-Python bevorzugen (ARM64-nativ)
if [[ -x "/opt/homebrew/bin/python3" ]]; then
    PYTHON="/opt/homebrew/bin/python3"
    ok "Homebrew Python gefunden: $PYTHON"
elif [[ -x "/usr/local/bin/python3" ]]; then
    PYTHON="/usr/local/bin/python3"
    ok "Homebrew Python (Intel) gefunden: $PYTHON"
else
    warn "Kein Homebrew-Python gefunden — nutze: $PYTHON"
fi

PY_VERSION=$("$PYTHON" --version 2>&1)
ok "Python: $PY_VERSION"

# ── 2. Abhängigkeiten sicherstellen ───────────────────────────
info "Installiere/prüfe Abhängigkeiten..."
"$PYTHON" -m pip install \
    stable-ts \
    mutagen \
    customtkinter \
    pyinstaller \
    --break-system-packages \
    --quiet \
    --upgrade
ok "Alle Abhängigkeiten OK"

# ── 3. Alte Builds aufräumen ──────────────────────────────────
info "Räume alte Build-Artefakte auf..."
rm -rf "$BUILD_DIR" "$DIST_DIR" "$DMG_STAGING"
[[ -f "$DMG_OUTPUT" ]] && rm -f "$DMG_OUTPUT"
ok "Aufgeräumt"

# ── 4. PyInstaller ausführen ──────────────────────────────────
info "Starte PyInstaller (das dauert 2–5 Minuten)..."
echo ""
"$PYTHON" -m PyInstaller "$SPEC_FILE" \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR" \
    --noconfirm
echo ""

APP_PATH="$DIST_DIR/$APP_NAME.app"
[[ -d "$APP_PATH" ]] || fail "PyInstaller hat keine .app erstellt. Prüfe den Output oben."
ok "App erstellt: $APP_PATH"

# ── 5. App-Größe anzeigen ──────────────────────────────────────
APP_SIZE=$(du -sh "$APP_PATH" | cut -f1)
info "App-Größe: $APP_SIZE"

# ── 6. DMG erstellen ──────────────────────────────────────────
info "Erstelle DMG..."

# Staging-Ordner
mkdir -p "$DMG_STAGING"
cp -r "$APP_PATH" "$DMG_STAGING/"
# Symlink auf /Applications für Drag-to-install
ln -s /Applications "$DMG_STAGING/Applications"

# Temporäre R/W DMG erstellen
TEMP_DMG="$SCRIPT_DIR/_temp.dmg"
hdiutil create \
    -volname "$VOLUME_NAME" \
    -srcfolder "$DMG_STAGING" \
    -ov \
    -format UDRW \
    "$TEMP_DMG" \
    > /dev/null

# Komprimierte finale DMG
hdiutil convert "$TEMP_DMG" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -o "$DMG_OUTPUT" \
    > /dev/null

# Aufräumen
rm -f "$TEMP_DMG"
rm -rf "$DMG_STAGING"
ok "DMG erstellt!"

# ── 7. Ergebnis ───────────────────────────────────────────────
DMG_SIZE=$(du -sh "$DMG_OUTPUT" | cut -f1)
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅  BUILD ERFOLGREICH!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  Datei:  $(basename "$DMG_OUTPUT")"
echo "  Größe:  $DMG_SIZE"
echo "  Pfad:   $DMG_OUTPUT"
echo ""
echo "  Weitergabe:"
echo "  → DMG-Datei per AirDrop, iCloud, WeTransfer etc. verschicken"
echo "  → Empfänger öffnet die DMG und zieht die App in Programme"
echo "  → Beim ersten Start: Rechtsklick → Öffnen (Gatekeeper-Bypass)"
echo ""
