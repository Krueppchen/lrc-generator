# 🎵 LRC Generator — Anleitung

Erstellt `.lrc` Timestamp-Dateien für alle Songs mit vorhandener `.txt` Lyrics-Datei.

---

## Schnellstart (2 Schritte)

### Schritt 1: App installieren
Terminal öffnen und eingeben:
```bash
bash ~/Downloads/LRC\ Generator/create_app.sh
```

Das Script erstellt `~/Applications/LRC Generator.app` und fragt, ob es
fehlende Abhängigkeiten installieren soll.

### Schritt 2: App starten
Doppelklick auf `~/Applications/LRC Generator.app`

Beim ersten Start werden automatisch installiert (falls nötig):
- `customtkinter` — das UI-Framework (~5 MB)
- `stable-ts` — das Whisper-Alignment-Tool (~200 MB)

---

## Was macht das Script?

**Methode: Forced Alignment**
Das bekannte Lyrics-Text wird präzise auf das Audio ausgerichtet — viel
genauer als reine Sprach-Transkription, weil der Text schon bekannt ist.

**Verarbeitete Songs:**
- Findet alle `.wav` Dateien mit zugehöriger `.txt` Lyrics-Datei
- `SongName_mastered.wav` → nutzt `SongName.txt` automatisch
- Entfernt `[Intro]`, `[Chorus]`, `[Strophe]`-Marker aus den Lyrics
- Schreibt `.lrc` Datei direkt neben die `.wav` Datei
- Überspringt Songs wo bereits eine `.lrc` existiert

---

## Modell-Empfehlungen

| Modell | Größe | Geschwindigkeit | Genauigkeit |
|--------|-------|-----------------|-------------|
| tiny   | 75 MB | sehr schnell    | ausreichend |
| base   | 145 MB| schnell         | gut         |
| small  | 460 MB| mittel          | sehr gut    |
| **medium** | **1.4 GB** | **mittel** | **excellent** ← Standard |
| large  | 2.9 GB| langsam         | maximal     |

Für Deutsche Lyrics empfehle ich **medium** oder **large**.

---

## Manuell starten (ohne .app)

```bash
# Abhängigkeiten installieren (einmalig)
pip install stable-ts customtkinter

# App starten
python3 ~/Downloads/LRC\ Generator/lrc_generator_app.py
```

---

## Ausgabe-Format

Erstellt Standard `.lrc` Dateien, kompatibel mit:
- Apple Music / iTunes
- VLC, MusicBee, foobar2000
- Karaoke-Apps
- Lyric-Display in Media Playern

Beispiel-Output:
```
[ar:Tim Stuer]
[al:Nice Touchy]
[ti:Kohle an]

[00:00.00]Gartentor auf, Kohle glüht — der Grill ist schon auf Hitze
[00:04.98]Drei Salate, Marinaden — Jens macht das mit Witz und Spitze
...
```
