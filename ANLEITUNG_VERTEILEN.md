# LRC Generator — Verteilbare App erstellen

## Was du am Ende hast

Eine Datei: **`LRC-Generator-macOS.dmg`** (~500–900 MB)

Die kannst du per AirDrop, iCloud Drive, WeTransfer oder USB-Stick weiterschicken. Wer sie bekommt, braucht kein Python, kein Terminal, nichts installieren.

---

## Einmalige Vorbereitung (auf deinem Mac, nur du)

```bash
# 1. Homebrew Python mit Tkinter (falls noch nicht vorhanden)
brew install python-tk

# 2. Abhängigkeiten installieren
pip3 install stable-ts mutagen customtkinter --break-system-packages

# 3. In den App-Ordner wechseln
cd ~/Downloads/LRC\ Generator
```

---

## App bauen

```bash
bash build_dmg.sh
```

Das dauert beim ersten Mal **3–8 Minuten** (PyTorch-Download, Kompilierung).

Danach liegt im selben Ordner:
```
LRC-Generator-macOS.dmg   ← Das ist die Datei zum Weiterschicken
```

---

## Was der Empfänger tut

1. **DMG öffnen** → Doppelklick auf die .dmg-Datei
2. **App installieren** → „LRC Generator" in den Ordner „Programme" ziehen
3. **Erster Start** → Rechtsklick auf die App → „Öffnen" wählen
   *(einmalig nötig, weil die App nicht aus dem App Store kommt)*
4. **Whisper-Modell** → Beim allerersten LRC-Generieren lädt die App das
   Whisper-Modell herunter (~140 MB) — das passiert automatisch im Hintergrund.

---

## Fehlerbehebung

### "Build-Ordner/Dist-Ordner schon vorhanden"
Das Script räumt automatisch auf. Kein Problem.

### PyInstaller-Fehler wegen ARM64/x86_64
```bash
# Sicherstellen dass Homebrew-Python verwendet wird:
/opt/homebrew/bin/python3 -m pip install pyinstaller --break-system-packages
/opt/homebrew/bin/python3 -m PyInstaller lrc_generator.spec
```

### App startet beim Empfänger nicht
- macOS-Version prüfen: mindestens macOS 12 (Monterey) benötigt
- Gatekeeper-Dialog: Rechtsklick → Öffnen (nicht Doppelklick beim ersten Start)
- Fehlerlog: `~/Library/Logs/LRCGenerator.log`

### App ist sehr groß (>900 MB)
Normal — PyTorch (für Whisper) ist groß. Zum Vergleich: Slack ist ~400 MB.

---

## Hinweis zu Code-Signierung

Die App ist **nicht code-signiert**. Das bedeutet:
- Empfänger müssen beim ersten Start Rechtsklick → Öffnen wählen
- In Firmenumgebungen mit strikter Gatekeeper-Policy kann das problematisch sein
- Für breitere Verteilung: Apple Developer Account (~99 €/Jahr) für Signierung und Notarisierung

---

*Erstellt mit PyInstaller · Whisper-Modell von OpenAI · stable-ts für Forced Alignment*
