#!/bin/bash
# ============================================================
#  build_dmg.sh — LRC Generator macOS Distributor
#  Erstellt eine vollständige, standalone LRC Generator.dmg
#  die man direkt weiterschicken kann. Kein Python oder
#  Terminal beim Empfänger nötig.
#
#  Voraussetzungen (nur für den BUILD-Rechner):
#    brew install python-tk@3.11   ← wichtig: python-tk, nicht python@3.11!
#
#  Aufruf: bash build_dmg.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="LRC Generator"
SPEC_FILE="lrc_generator.spec"
DIST_DIR="$SCRIPT_DIR/dist"
BUILD_DIR="$SCRIPT_DIR/build"
VENV_DIR="$SCRIPT_DIR/.build_venv"
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

# ── 1. python-tk@3.11 sicherstellen ───────────────────────────
# python-tk@3.11 bringt Tcl/Tk korrekt für PyInstaller mit.
# Ohne das crasht die App beim Start (stiller Tod nach "App gestartet").
info "Prüfe python-tk@3.11..."

if [[ -x "/opt/homebrew/bin/python3.11" ]]; then
    BASE_PYTHON="/opt/homebrew/bin/python3.11"
elif [[ -x "/usr/local/bin/python3.11" ]]; then
    BASE_PYTHON="/usr/local/bin/python3.11"
else
    info "python-tk@3.11 nicht gefunden — installiere jetzt..."
    brew install python-tk@3.11 || fail "brew install python-tk@3.11 fehlgeschlagen"
    BASE_PYTHON="/opt/homebrew/bin/python3.11"
fi

ok "Python: $($BASE_PYTHON --version)"

# ── 2. Saubere virtuelle Umgebung erstellen ────────────────────
# Ein venv isoliert den Build von system-/homebrew-Paketen.
# Verhindert Versions- und Architektur-Konflikte.
info "Erstelle saubere Build-Umgebung (venv)..."
rm -rf "$VENV_DIR"
"$BASE_PYTHON" -m venv "$VENV_DIR"
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
ok "venv erstellt: $VENV_DIR"

# ── 3. Abhängigkeiten im venv installieren ─────────────────────
info "Installiere Abhängigkeiten im venv (kann einige Minuten dauern)..."
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet \
    stable-ts \
    mutagen \
    customtkinter \
    pyinstaller
ok "Alle Abhängigkeiten installiert"

# ── 4. Alte Builds aufräumen ──────────────────────────────────
info "Räume alte Build-Artefakte auf..."
rm -rf "$BUILD_DIR" "$DIST_DIR" "$DMG_STAGING"
[[ -f "$DMG_OUTPUT" ]] && rm -f "$DMG_OUTPUT"
ok "Aufgeräumt"

# ── 5. PyInstaller ausführen ──────────────────────────────────
info "Starte PyInstaller (das dauert 3–8 Minuten beim ersten Mal)..."
echo ""
"$PYTHON" -m PyInstaller "$SPEC_FILE" \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR" \
    --noconfirm
echo ""

APP_PATH="$DIST_DIR/$APP_NAME.app"
[[ -d "$APP_PATH" ]] || fail "PyInstaller hat keine .app erstellt. Prüfe den Output oben."
ok "App erstellt: $APP_PATH"
info "App-Größe: $(du -sh "$APP_PATH" | cut -f1)"

# ── 6. DMG erstellen ──────────────────────────────────────────
info "Erstelle DMG..."

mkdir -p "$DMG_STAGING"
cp -r "$APP_PATH" "$DMG_STAGING/"
ln -s /Applications "$DMG_STAGING/Applications"

TEMP_DMG="$SCRIPT_DIR/_temp.dmg"
hdiutil create \
    -volname "$VOLUME_NAME" \
    -srcfolder "$DMG_STAGING" \
    -ov -format UDRW \
    "$TEMP_DMG" > /dev/null

hdiutil convert "$TEMP_DMG" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -o "$DMG_OUTPUT" > /dev/null

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
echo "  → DMG per AirDrop, iCloud, WeTransfer etc. verschicken"
echo "  → Empfänger öffnet die DMG und zieht die App in Programme"
echo "  → Beim ersten Start: Rechtsklick → Öffnen (Gatekeeper-Bypass)"
echo ""
