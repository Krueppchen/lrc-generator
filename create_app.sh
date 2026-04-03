#!/bin/bash
# ══════════════════════════════════════════════════════════════════
# LRC Generator — Mac App Bundle erstellen
# Einmalig ausführen:
#   bash ~/Downloads/LRC\ Generator/create_app.sh
# ══════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="LRC Generator"
APP_DIR="$HOME/Applications/$APP_NAME.app"
PYTHON_SCRIPT="$SCRIPT_DIR/lrc_generator_app.py"

echo "🎵  LRC Generator — App Bundle erstellen"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Python suchen (inkl. Homebrew & pyenv) ─────────────────────
find_python() {
    # Homebrew zuerst (hat Tkinter-Support)
    local candidates=(
        "/opt/homebrew/bin/python3"       # Apple Silicon Homebrew
        "/usr/local/bin/python3"           # Intel Homebrew
        "$HOME/.pyenv/shims/python3"       # pyenv
        "$HOME/miniconda3/bin/python3"     # conda
        "$HOME/anaconda3/bin/python3"      # anaconda
        "$(which python3 2>/dev/null)"     # Shell PATH
        "/usr/bin/python3"                 # System (letzter Ausweg)
    )
    for py in "${candidates[@]}"; do
        if [ -f "$py" ] && "$py" -c "import tkinter" 2>/dev/null; then
            echo "$py"
            return 0
        fi
    done
    return 1
}

PYTHON=$(find_python)
if [ -z "$PYTHON" ]; then
    echo "❌ Kein Python 3 mit Tkinter-Unterstützung gefunden!"
    echo ""
    echo "   Option A (empfohlen): Homebrew-Python installieren:"
    echo "     brew install python-tk"
    echo ""
    echo "   Option B: Python.org:"
    echo "     https://www.python.org/downloads/"
    exit 1
fi

echo "✅ Python: $PYTHON ($("$PYTHON" --version))"

# Tkinter-Test
"$PYTHON" -c "import tkinter" 2>/dev/null && echo "✅ Tkinter: OK" || {
    echo "⚠️  Tkinter fehlt für $PYTHON"
    echo "   Bitte ausführen: brew install python-tk"
    exit 1
}

# ── App-Bundle Struktur ─────────────────────────────────────────
echo ""
echo "📦 Erstelle App-Bundle: $APP_DIR"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Python-Script kopieren
cp "$PYTHON_SCRIPT" "$APP_DIR/Contents/Resources/lrc_generator_app.py"

# ── Launcher-Script ─────────────────────────────────────────────
# Schreibe den Launcher mit explizitem Python-Pfad (kein PATH-Problem)
LAUNCHER="$APP_DIR/Contents/MacOS/$APP_NAME"

cat > "$LAUNCHER" << EOF
#!/bin/bash
# LRC Generator Launcher — Python: $PYTHON

PYTHON="$PYTHON"
SCRIPT="\$(dirname "\$0")/../Resources/lrc_generator_app.py"
LOG="\$HOME/Library/Logs/LRCGenerator.log"

# Homebrew zum PATH hinzufügen (für pip etc.)
export PATH="/opt/homebrew/bin:/usr/local/bin:\$PATH"

# Python und Tkinter prüfen
if [ ! -f "\$PYTHON" ]; then
    osascript -e 'display alert "Python nicht gefunden" message "'"$PYTHON"' existiert nicht mehr.\n\nBitte create_app.sh erneut ausführen."'
    exit 1
fi

if ! "\$PYTHON" -c "import tkinter" 2>/dev/null; then
    osascript -e 'display alert "Tkinter fehlt" message "Tkinter ist nicht verfügbar.\n\nBitte im Terminal ausführen:\n  brew install python-tk"'
    exit 1
fi

# customtkinter installieren falls nötig
if ! "\$PYTHON" -c "import customtkinter" 2>/dev/null; then
    ANSWER=\$(osascript -e 'button returned of (display dialog "'\''customtkinter'\'' ist nicht installiert.\n\nJetzt automatisch installieren?" buttons {"Abbrechen", "Installieren"} default button "Installieren" with icon note)')
    if [ "\$ANSWER" = "Installieren" ]; then
        "\$PYTHON" -m pip install customtkinter --quiet >> "\$LOG" 2>&1
    else
        exit 0
    fi
fi

# App starten
exec "\$PYTHON" "\$SCRIPT"
EOF

chmod +x "$LAUNCHER"

# ── Info.plist ──────────────────────────────────────────────────
cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>LRC Generator</string>
    <key>CFBundleDisplayName</key>
    <string>LRC Generator</string>
    <key>CFBundleIdentifier</key>
    <string>com.github.lrc-generator</string>
    <key>CFBundleVersion</key>
    <string>1.1</string>
    <key>CFBundleExecutable</key>
    <string>LRC Generator</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
PLIST

# ── Gatekeeper-Quarantäne entfernen ────────────────────────────
xattr -cr "$APP_DIR" 2>/dev/null && echo "✅ Gatekeeper: Quarantäne entfernt"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ App erstellt: $APP_DIR"
echo ""
echo "Starten mit:"
echo "   open '$APP_DIR'"
echo ""

read -p "App jetzt starten? [j/N] " OPEN_NOW
if [[ "$OPEN_NOW" =~ ^[jJyY]$ ]]; then
    open "$APP_DIR"
fi
