# LRC Generator — Projektverlauf & Chat-Zusammenfassung

Erstellt: April 2026

---

## Was wurde gebaut?

Eine macOS Desktop-App (`LRC Generator.app`), die automatisch **timestamped `.lrc` Lyrics-Dateien** für Suno AI Songs generiert — per AI-basiertem Forced Alignment (Whisper). Die App schreibt die Synced Lyrics auch direkt in die Audio-Metadaten.

---

## Dateien im Ordner

| Datei | Zweck |
|-------|-------|
| `lrc_generator_app.py` | Haupt-App (Python + CustomTkinter UI) |
| `create_app.sh` | Erstellt die doppelklickbare `.app` in `~/Applications/` |
| `diagnose.sh` | Diagnose-Script bei Problemen |
| `requirements.txt` | Python-Dependencies (`pip install -r requirements.txt`) |
| `README.md` | GitHub-Dokumentation (English) |
| `LICENSE` | MIT License |
| `.gitignore` | Ignoriert Audio-Dateien, Logs, `.app` Bundle |
| `ANLEITUNG.md` | Deutsche Kurzanleitung |

---

## Features der App

- Forced Alignment via **stable-ts** (Whisper `base` Modell, ~140 MB, wird einmalig gecacht)
- Generiert `.lrc` Dateien im Standard-Format (`[mm:ss.cc]Text`)
- Schreibt Synced Lyrics in Audio-Metadaten:
  - **SYLT ID3-Tag** für MP3, WAV, AIFF
  - **SYNCEDLYRICS Vorbis Comment** für FLAC, OGG, Opus
- Unterstützt alle gängigen Audio-Formate: `.wav .mp3 .flac .m4a .aac .ogg .opus .aiff`
- Intelligentes Datei-Matching (3 Stufen: exakt → Suffix-Strip → Slug-Normalisierung)
- Song-Auswahl UI mit Checkboxen und farbigen Format-Badges
- Live-Download-Fortschritt für das Whisper-Modell
- Automatische Dependency-Installation beim ersten Start

---

## Gelöste Probleme (Chronologie)

### 1. App startet nicht (Icon bounced, kein Fenster)
**Ursache:** Der Python-Pfad im `.app` Bundle hatte keinen Homebrew-PATH
**Fix:** `create_app.sh` sucht jetzt den absoluten Python-Pfad und bäckt ihn fest ins Launcher-Script

### 2. SSL-Zertifikat-Fehler beim Whisper-Download
**Ursache:** Python.org-Python fehlen macOS-Zertifikate
**Fix:** `/Applications/Python 3.x/Install Certificates.command` ausführen

### 3. "stable-ts nicht installiert" obwohl installiert
**Ursache:** ARM64 vs x86_64 Architektur-Mismatch (Rosetta Terminal vs native .app)
**Fix:** Homebrew-Python (`/opt/homebrew/bin/python3`) verwenden — ist nativ ARM64

### 4. externally-managed-environment Fehler
**Ursache:** Homebrew blockiert pip standardmäßig
**Fix:** `pip install ... --break-system-packages`

### 5. `'WhisperResult' has no attribute 'to_lrc'`
**Ursache:** API-Unterschied in stable-ts 2.19.1
**Fix:** `write_lrc()` Funktion mit `hasattr()` Check + manuellem Segment-Fallback

### 6. Suno-Metadaten landen in der LRC-Datei
**Ursache:** Der `.txt`-Parser stoppte nicht bei Style-Beschreibungen
**Fix:** `STOP_PATTERNS` Regex + `Prompt:` Block-Erkennung im Parser

### 7. Nur 6 von 10 Deutsch-Rap Songs werden angezeigt
**Ursache 1:** Umlaut-Mismatch (`für` in Dateiname vs `fuer` in Lyrics-Datei)
**Ursache 2:** Klammer-Varianten wie `(1)` im Dateinamen
**Fix:** `_normalize_name()` ergänzt um Umlaut-Mapping (`ä→ae`, `ö→oe`, `ü→ue`, `ß→ss`) und Klammer-Strip

---

## Technische Details

```
Whisper-Modell:    base (multilingual, ~140 MB)
Modell-Cache:      ~/.cache/whisper/  (bleibt erhalten, wird nicht gelöscht)
App-Log:           ~/Library/Logs/LRCGenerator.log
GUI-Framework:     CustomTkinter (Dark Mode)
Alignment:         stable-ts (Forced Alignment)
Metadaten:         mutagen
```

---

## GitHub veröffentlichen

```bash
cd ~/Downloads/LRC\ Generator

# Git initialisieren
git init
git add .
git commit -m "Initial release: LRC Generator v1.1"

# Auf GitHub: neues Repo anlegen unter github.com/new
git remote add origin https://github.com/DEIN_USERNAME/lrc-generator.git
git push -u origin main
```

---

## Nächste mögliche Schritte

- [ ] Drag & Drop Ordner-Auswahl
- [ ] Whisper Modell-Auswahl (tiny / base / small / medium)
- [ ] LRC-Vorschau vor dem Speichern
- [ ] Batch-Export als ZIP
- [ ] Windows-Support (CustomTkinter läuft plattformübergreifend)
