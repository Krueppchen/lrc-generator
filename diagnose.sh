#!/bin/bash
# LRC Generator — Diagnose
echo "=== Python-Umgebung ==="
echo "which python3: $(which python3 2>/dev/null || echo 'NICHT GEFUNDEN')"
echo "python3 version: $(python3 --version 2>&1)"
echo ""

echo "=== Homebrew Python? ==="
for p in /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  [ -f "$p" ] && echo "  gefunden: $p ($($p --version 2>&1))" || echo "  nicht da: $p"
done
echo ""

echo "=== Pakete ==="
python3 -c "import tkinter; print('  tkinter: OK')" 2>/dev/null || echo "  tkinter: FEHLT ← Hauptproblem!"
python3 -c "import customtkinter; print('  customtkinter: OK', customtkinter.__version__)" 2>/dev/null || echo "  customtkinter: FEHLT"
python3 -c "import stable_whisper; print('  stable-ts: OK')" 2>/dev/null || echo "  stable-ts: FEHLT (normal, wird beim Start installiert)"
echo ""

echo "=== Log-Datei ==="
LOG="$HOME/Library/Logs/LRCGenerator.log"
if [ -f "$LOG" ]; then
  echo "  $LOG:"
  tail -20 "$LOG"
else
  echo "  Keine Log-Datei (App hat noch nicht gestartet)"
fi

echo ""
echo "=== Direkter App-Start (zeigt Fehler) ==="
python3 "$HOME/Downloads/LRC Generator/lrc_generator_app.py" 2>&1
