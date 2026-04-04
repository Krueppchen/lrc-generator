#!/usr/bin/env python3
"""
LRC Generator — Mac App
Erstellt .lrc Timestamp-Dateien für Suno-Songs via Forced Alignment
und schreibt Synced Lyrics optional in Audio-Metadaten (SYLT/SYNCEDLYRICS).
"""

import os
import re
import sys
import json
import csv
import threading
import subprocess
import queue
from pathlib import Path
from typing import Optional, List, Dict


# ── Logging ───────────────────────────────────────────────────────
import logging
LOG_FILE = Path.home() / "Library" / "Logs" / "LRCGenerator.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_FILE), level=logging.DEBUG,
    format="%(asctime)s %(levelname)s: %(message)s"
)
logging.info(f"App gestartet. Python: {sys.executable} {sys.version}")


# ── Unterstützte Audio-Formate ────────────────────────────────────
AUDIO_FORMATS = [".wav", ".mp3", ".flac", ".m4a", ".aac",
                 ".ogg", ".opus", ".aiff", ".aif"]


# ── Mastering Presets ─────────────────────────────────────────────
MASTERING_PRESETS: Dict[str, Dict] = {
    "Suno-Standard": {
        # EQ-Bänder: (frequenz_hz, breite_oktaven, gain_dB)
        "eq": [
            (300,   2.0, -0.5),
            (1000,  2.0,  0.2),
            (3500,  2.0,  2.2),
            (8000,  2.0,  2.0),
            (14000, 2.0,  3.0),
        ],
        "compressor": {
            "threshold": -18,   # dB
            "ratio": 1.8,
            "attack": 80,       # ms
            "release": 200,     # ms
        },
        "stereo_width": 1.18,   # extrastereo-Faktor (1.0 = unverändert)
        "loudness_lufs": -12.2,
        "true_peak": -1,
        "dither_bits": 24,      # TPDF Dither, 0 = deaktiviert
    }
}


def _find_ffmpeg() -> Optional[str]:
    """Sucht FFmpeg im App-Bundle, neben dem Skript, Homebrew und PATH."""
    # 1. Eingebettetes ffmpeg (PyInstaller-Bundle, neben der .app)
    bundle = Path(sys.executable).parent / "ffmpeg"
    if bundle.exists():
        return str(bundle)
    # 2. Neben dem Skript (Entwicklermodus)
    script_dir = Path(__file__).parent
    local = script_dir / "ffmpeg"
    if local.exists():
        return str(local)
    # 3. Bekannte Installationspfade (Homebrew M1/Intel, System)
    for candidate in [
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg",
    ]:
        if Path(candidate).exists():
            return candidate
    # 4. PATH-Suche via which
    try:
        r = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None


def _mastering_filter_chain(preset: Dict) -> str:
    """Erzeugt die FFmpeg -af Filterkette aus einem Mastering-Preset-Dict."""
    filters = []

    # EQ-Bänder
    for freq, width_oct, gain in preset.get("eq", []):
        if gain != 0:
            filters.append(
                f"equalizer=f={freq}:width_type=o:width={width_oct}:g={gain}"
            )

    # Dynamikkompressor
    comp      = preset.get("compressor", {})
    threshold = comp.get("threshold", -18)
    ratio     = comp.get("ratio", 1.8)
    attack    = comp.get("attack", 80)
    release   = comp.get("release", 200)
    filters.append(
        f"acompressor=threshold={threshold}dB:ratio={ratio}"
        f":attack={attack}:release={release}"
    )

    # Stereo-Breite (extrastereo: m = Faktor - 1.0)
    sw = preset.get("stereo_width", 1.0)
    if abs(sw - 1.0) > 0.01:
        m = round(sw - 1.0, 4)
        filters.append(f"extrastereo=m={m}")

    # Lautheits-Normalisierung (EBU R128)
    lufs = preset.get("loudness_lufs", -14)
    tp   = preset.get("true_peak", -1)
    filters.append(f"loudnorm=I={lufs}:TP={tp}:LRA=11")

    # Note: dithering only needed when reducing bit depth (e.g. 24→16).
    # Since we output pcm_s24le, no dither filter is applied.

    return ",".join(filters)


def master_audio(audio_path: Path,
                 preset_name: str = "Suno-Standard",
                 log_fn=None) -> Optional[Path]:
    """
    Mastert eine Audio-Datei mit dem gewählten Preset via FFmpeg.
    Gibt den Pfad zur _mastered.wav zurück, oder None bei Fehler.
    Die Quelldatei bleibt unverändert.
    """
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        if log_fn:
            log_fn("❌ FFmpeg not found. Please install: brew install ffmpeg")
        return None

    preset = MASTERING_PRESETS.get(preset_name)
    if not preset:
        if log_fn:
            log_fn(f"❌ Unknown preset: {preset_name}")
        return None

    # Ausgabe: gleicher Ordner, Stem ohne _mastered + _mastered.wav
    stem     = re.sub(r"_mastered.*$", "", audio_path.stem, flags=re.IGNORECASE)
    out_path = audio_path.parent / f"{stem}_mastered.wav"

    cmd = [
        ffmpeg, "-y",
        "-i", str(audio_path),
        "-af", _mastering_filter_chain(preset),
        "-ar", "44100",
        "-c:a", "pcm_s24le",
        str(out_path),
    ]

    if log_fn:
        log_fn(f"   🎚 Mastering with '{preset_name}'…")
    logging.info(f"master_audio: {audio_path.name} → {out_path.name}")
    logging.debug(f"FFmpeg cmd: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            err = (result.stderr or "")[-400:]
            if log_fn:
                log_fn(f"   ❌ FFmpeg error: {err}")
            logging.error(f"FFmpeg error ({audio_path.name}): {result.stderr}")
            return None
        if log_fn:
            log_fn(f"   ✅ Mastered: {out_path.name}")
        logging.info(f"master_audio OK: {out_path}")
        return out_path
    except subprocess.TimeoutExpired:
        if log_fn:
            log_fn("   ❌ Mastering timeout (>5 min)")
        return None
    except Exception as e:
        if log_fn:
            log_fn(f"   ❌ Mastering error: {e}")
        logging.error(f"master_audio Exception: {e}")
        return None


# ── Auto-install helper ───────────────────────────────────────────
def _has(pkg):
    try: __import__(pkg); return True
    except ImportError: return False

def _install(pkg, import_name=None):
    """Installiert ein Paket via pip. Gibt True bei Erfolg zurück."""
    res = subprocess.run(
        [sys.executable, "-m", "pip", "install", pkg, "-q"],
        capture_output=True, text=True)
    logging.info(f"pip install {pkg}: code={res.returncode} {res.stderr[:200]}")
    return res.returncode == 0


# ── Bootstrap: customtkinter ──────────────────────────────────────
if not _has("customtkinter"):
    import tkinter as tk
    from tkinter import messagebox
    r = tk.Tk(); r.withdraw()
    ok = messagebox.askyesno("Missing dependency",
        "'customtkinter' is not installed.\nInstall automatically now?")
    r.destroy()
    if ok:
        if not _install("customtkinter"):
            import tkinter as tk; from tkinter import messagebox
            r2 = tk.Tk(); r2.withdraw()
            messagebox.showerror("Error", "pip failed.\n"
                                 "Please install manually: pip install customtkinter")
            r2.destroy(); sys.exit(1)
    else:
        sys.exit(0)

try:
    import customtkinter as ctk
    import tkinter as tk
    from tkinter import filedialog, messagebox
    logging.info(f"customtkinter {ctk.__version__} geladen")
except Exception as e:
    logging.error(f"Import-Fehler: {e}"); raise


# ── Design ────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ICON_PENDING = "○"
ICON_RUNNING = "⏳"
ICON_DONE    = "✅"
ICON_ERROR   = "❌"
ICON_SKIP    = "⏭"


# ── tqdm/stderr Capture für Whisper-Download-Progress ────────────
class _StderrCapture:
    """
    Leitet sys.stderr um und extrahiert tqdm-Fortschrittszeilen.
    tqdm schreibt den Fortschrittsbalken mit \\r auf stderr.
    Wir parsen das und leiten es in die UI weiter.
    """
    def __init__(self, log_fn, status_fn):
        self._log    = log_fn     # für normale Text-Zeilen
        self._status = status_fn  # für Progress-Label Updates
        self._buf    = ""

    def write(self, s: str):
        self._buf += s
        # tqdm nutzt \r um die Zeile zu überschreiben, \n für neue Zeilen
        while True:
            for sep in ("\r", "\n"):
                idx = self._buf.find(sep)
                if idx < 0:
                    continue
                line = self._buf[:idx].strip()
                self._buf = self._buf[idx + 1:]
                if not line:
                    break
                # tqdm-Fortschrittszeile (enthält % oder Einheiten)
                if any(x in line for x in ("%", "MiB", "GiB", "kB", "MB", "GB")):
                    self._status(f"⬇️  {line}")
                else:
                    self._log(line)
                break
            else:
                break  # kein Separator mehr im Buffer

    def flush(self):   pass
    def isatty(self):  return True   # tqdm zeigt Balken nur bei TTY


# ── Slug-Normalisierung für Dateinamen-Matching ───────────────────
def _normalize_name(s: str) -> str:
    """
    Normalisiert einen Dateinamen für fuzzy Matching.

    Behandelt:
    - Führende Tracknummern:  '07 - Kohle an'  → 'kohlean'
    - Klammer-Varianten:      'Song (1)'        → 'song'  (ignoriert)
    - Umlaute (beide Formen): 'für' = 'fuer', 'fällt' = 'faellt'
    - Sonderzeichen:          Kommas, Punkte, etc. werden entfernt
    """
    s = s.lower()
    s = re.sub(r"^\d+\s*[-–—.]\s*", "", s)    # führende Tracknummer
    s = re.sub(r"\s*\(\d+\)\s*", "", s)        # Klammer-Varianten: (1), (2)…
    # Umlaute vereinheitlichen: ä→ae, ö→oe, ü→ue, ß→ss
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]", "", s)            # nur Buchstaben/Zahlen behalten
    return s


# ── Lyrics-Parser ─────────────────────────────────────────────────
def parse_lyrics(lyrics_path: Path) -> str:
    """
    Extrahiert gesungene Zeilen aus .txt oder .md Dateien.

    .txt (Suno-Export):  Entfernt [Section]-Marker und Metadaten-Kopf.
    .md  (Song-Dokument): Extrahiert bevorzugt '## Streaming Lyrics',
                          Fallback auf 'Lyrics Box' im Suno-Block.
    """
    with open(lyrics_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # ── .md: strukturiertes Song-Dokument ──
    if lyrics_path.suffix.lower() == ".md":
        # 1. Bevorzugt: ## Streaming Lyrics (sauberer Text, keine Marker)
        m = re.search(
            r"##\s+Streaming Lyrics\s*\n```[^\n]*\n(.*?)```",
            raw, re.DOTALL | re.IGNORECASE)
        if m:
            text = m.group(1).strip()
            # Trotzdem noch Section-Marker rausfiltern falls vorhanden
            lines = [l.strip() for l in text.splitlines()
                     if l.strip() and not re.match(r"^\[.+\]$", l.strip())]
            return "\n".join(lines)

        # 2. Fallback: Lyrics Box (enthält Section-Marker, aber besser als nichts)
        m = re.search(
            r"###\s+Lyrics Box.*?```[^\n]*\n(.*?)```",
            raw, re.DOTALL | re.IGNORECASE)
        if m:
            text = m.group(1).strip()
            lines = [l.strip() for l in text.splitlines()
                     if l.strip() and not re.match(r"^\[.+\]$", l.strip())]
            return "\n".join(lines)

        # 3. Letzter Fallback: gesamter Inhalt, Markdown-Syntax entfernen
        text = re.sub(r"^#{1,6}\s+.*$", "", raw, flags=re.MULTILINE)  # Überschriften
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)          # Code-Blöcke
        text = re.sub(r"\|.*?\|", "", text)                             # Tabellen
        text = re.sub(r"[-*_]{2,}", "", text)                           # Trennlinien
        lines = [l.strip() for l in text.splitlines()
                 if l.strip() and not re.match(r"^\[.+\]$", l.strip())]
        return "\n".join(lines)

    # ── .txt (Suno-Export-Format) ──
    # Stopp-Muster: Suno-Metadata die nach den Lyrics auftauchen können
    STOP_PATTERNS = re.compile(
        r"^(Genre|Style|Tags|BPM|Tempo|Mood|Instrumentation|"
        r"This\s+(song|track|piece)|"          # "This song/track kicks off..."
        r"The\s+(song|track|verse|chorus))",   # "The track features..."
        re.IGNORECASE
    )
    result = []
    in_prompt = False  # Erst ab Prompt:-Zeile sammeln wenn vorhanden
    has_prompt = "Prompt:" in raw or "prompt:" in raw.lower()

    for line in raw.splitlines():
        line = line.strip()

        # Prompt:-Marker: ab hier sind die echten Lyrics
        if re.match(r"^Prompt\s*:", line, re.IGNORECASE):
            in_prompt = True
            continue

        # Metadaten-Kopf überspringen
        if re.match(r"^(Title|ID)\s*:", line, re.IGNORECASE): continue

        # Wenn Datei keinen Prompt:-Block hat, alles verarbeiten
        if has_prompt and not in_prompt: continue

        # Stopp bei Suno-Stil-Beschreibungen
        if STOP_PATTERNS.match(line): break

        # Section-Marker überspringen
        if re.match(r"^\[.+\]$", line): continue

        if not line: continue
        result.append(line)
    return "\n".join(result)


# ── WhisperResult → LRC schreiben ────────────────────────────────
def write_lrc(result, lrc_path: Path, song_name: str = ""):
    """
    Schreibt LRC-Datei aus einem stable-ts WhisperResult.
    Versucht zuerst result.to_lrc() — fällt bei fehlendem Attribut
    auf manuelle Generierung aus result.segments zurück.
    """
    # ── Weg 1: natives to_lrc() ──
    if hasattr(result, "to_lrc"):
        result.to_lrc(str(lrc_path))
        return

    # ── Weg 2: manuell aus Segmenten ──
    lines = []
    if song_name:
        lines.append(f"[ti:{song_name}]")
        lines.append("")

    segments = getattr(result, "segments", [])
    for seg in segments:
        start = getattr(seg, "start", None)
        text  = getattr(seg, "text", "").strip()
        if start is None or not text:
            continue
        mins = int(start // 60)
        secs = start % 60
        lines.append(f"[{mins:02d}:{secs:05.2f}]{text}")

    lrc_path.write_text("\n".join(lines), encoding="utf-8")


# ── LRC → SYLT-Daten ─────────────────────────────────────────────
def parse_lrc(lrc_path: Path) -> List[tuple]:
    """
    Gibt [(text, timestamp_ms), ...] zurück — das Format das SYLT braucht.
    LRC-Format: [mm:ss.cc]text   (cc = Hundertstel-Sekunden)
    """
    entries = []
    pattern = re.compile(r"^\[(\d+):(\d+\.\d+)\](.*)")
    with open(lrc_path, "r", encoding="utf-8") as f:
        for line in f:
            m = pattern.match(line.strip())
            if m:
                mins = int(m.group(1))
                secs = float(m.group(2))
                text = m.group(3).strip()
                if text:
                    ms = int((mins * 60 + secs) * 1000)
                    entries.append((text, ms))
    return entries


# ── Metadaten schreiben ───────────────────────────────────────────
def write_metadata(audio_path: Path, lrc_path: Path, lang: str = "deu") -> str:
    """
    Schreibt Synced Lyrics in die Audio-Metadaten.
    Gibt eine Beschreibung des Ergebnisses zurück.
    """
    import mutagen  # noqa – wird weiter oben geprüft

    entries = parse_lrc(lrc_path)
    if not entries:
        return "no LRC entries"

    full_text = "\n".join(t for t, _ in entries)
    with open(lrc_path, "r", encoding="utf-8") as f:
        lrc_content = f.read()

    suffix = audio_path.suffix.lower()

    # ── ID3-basierte Formate: WAV, MP3, AIFF ──
    if suffix in (".wav", ".mp3", ".aif", ".aiff"):
        from mutagen.id3 import SYLT, USLT, TIT2, Encoding

        if suffix == ".mp3":
            from mutagen.mp3 import MP3 as MutagenFile
        elif suffix == ".wav":
            from mutagen.wave import WAVE as MutagenFile
        else:
            from mutagen.aiff import AIFF as MutagenFile

        audio = MutagenFile(str(audio_path))
        if audio.tags is None:
            audio.add_tags()

        # Synchronized lyrics (SYLT)
        audio.tags.delall("SYLT")
        audio.tags.add(SYLT(
            encoding=Encoding.UTF8,
            lang=lang,
            format=2,   # 2 = Millisekunden
            type=1,     # 1 = Lyrics
            text=[(text, ts) for text, ts in entries]
        ))

        # Unsynchronized lyrics (USLT) — Fallback für ältere Player
        audio.tags.delall("USLT")
        audio.tags.add(USLT(
            encoding=Encoding.UTF8,
            lang=lang,
            desc="",
            text=full_text
        ))
        audio.save()
        return f"SYLT + USLT (ID3)"

    # ── FLAC / OGG / Opus: Vorbis Comments ──
    elif suffix == ".flac":
        from mutagen.flac import FLAC
        audio = FLAC(str(audio_path))
        audio["SYNCEDLYRICS"] = [lrc_content]   # LRC-Inhalt direkt
        audio["LYRICS"] = [full_text]
        audio.save()
        return "SYNCEDLYRICS + LYRICS (Vorbis)"

    elif suffix in (".ogg", ".opus"):
        if suffix == ".ogg":
            from mutagen.oggvorbis import OggVorbis as MutagenFile
        else:
            from mutagen.oggopus import OggOpus as MutagenFile
        audio = MutagenFile(str(audio_path))
        audio["SYNCEDLYRICS"] = [lrc_content]
        audio["LYRICS"] = [full_text]
        audio.save()
        return "SYNCEDLYRICS + LYRICS (Vorbis)"

    # ── M4A / AAC / MP4: iTunes Atoms ──
    elif suffix in (".m4a", ".aac", ".mp4"):
        from mutagen.mp4 import MP4
        audio = MP4(str(audio_path))
        # ©lyr = unsynced lyrics (kein Standard für synced in M4A)
        audio.tags["©lyr"] = [full_text]
        # Roher LRC-Text als custom tag
        audio.tags["----:com.apple.iTunes:SYNCEDLYRICS"] = [
            lrc_content.encode("utf-8")]
        audio.save()
        return "©lyr + SYNCEDLYRICS (M4A)"

    else:
        return f"Format not supported: {suffix}"


# ── Musik-Library aus CSV laden ──────────────────────────────────
def load_music_library(csv_path: Path) -> Dict[str, Dict]:
    """
    Lädt songs_assignment.csv → {normalisierter_stem: row}
    Spalten: artist, album, track_nr, titel, datei, ordner, genre, ...
    """
    library = {}
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                datei = row.get("datei", "").strip()
                if datei:
                    key = _normalize_name(Path(datei).stem)
                    library[key] = row
        logging.info(f"Library geladen: {len(library)} Einträge aus {csv_path.name}")
    except Exception as e:
        logging.warning(f"Library-Ladefehler ({csv_path}): {e}")
    return library


def find_library_entry(audio_path: Path, library: Dict) -> Optional[Dict]:
    """Sucht einen Library-Eintrag zum Audio-Stem (mit Fuzzy-Matching)."""
    for stem in [audio_path.stem, re.sub(r"_mastered.*$", "", audio_path.stem, flags=re.IGNORECASE)]:
        entry = library.get(_normalize_name(stem))
        if entry:
            return entry
    return None


# ── Begleitdateien finden ─────────────────────────────────────────
def find_cover_art(audio_path: Path) -> Optional[Path]:
    """Findet Bild (.jpg/.jpeg/.png) mit gleichem Stammnamen wie die Audio-Datei."""
    stems = [audio_path.stem, re.sub(r"_mastered.*$", "", audio_path.stem, flags=re.IGNORECASE)]
    for s in stems:
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            c = audio_path.parent / (s + ext)
            if c.exists():
                return c
    return None


def find_json_file(audio_path: Path) -> Optional[Path]:
    """Findet eine gleichnamige .json Suno-Exportdatei."""
    stems = [audio_path.stem, re.sub(r"_mastered.*$", "", audio_path.stem, flags=re.IGNORECASE)]
    for s in stems:
        c = audio_path.parent / (s + ".json")
        if c.exists():
            return c
    return None


# ── Genres aus Suno-JSON extrahieren ─────────────────────────────
def extract_genres_from_json(json_path: Path, max_genres: int = 4) -> List[str]:
    """
    Extrahiert max. N Genres aus einer Suno-JSON-Datei.
    Nutzt zuerst artist_reference_warning.artist_to_tag_mapping,
    dann parsed metadata.tags nach bekannten Schlüsselwörtern.
    """
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    genres: List[str] = []

    # 1. artist_reference_warning — schon sauber klassifiziert
    mapping = (data.get("metadata", {})
                   .get("artist_reference_warning", {})
                   .get("artist_to_tag_mapping", {}))
    for tags in mapping.values():
        for tag in tags:
            g = tag.strip().title()
            if g and g not in genres:
                genres.append(g)
    if len(genres) >= max_genres:
        return genres[:max_genres]

    # 2. metadata.tags parsen
    GENRE_KEYWORDS = [
        "hip hop", "rap", "r&b", "pop", "rock", "jazz", "classical",
        "electronic", "techno", "house", "trap", "soul", "folk", "country",
        "metal", "punk", "reggae", "blues", "dance", "deutschpop", "schlager",
        "indie", "alternative", "ambient", "german hip hop", "deutschrap",
        "electro", "funk", "gospel", "latin", "children", "anthem", "ballad",
        "comedy", "novelty", "festival", "club",
    ]
    tags_str = data.get("metadata", {}).get("tags", "").lower()
    for kw in GENRE_KEYWORDS:
        if kw in tags_str:
            g = kw.title()
            if g not in genres:
                genres.append(g)
        if len(genres) >= max_genres:
            break

    return genres[:max_genres]


# ── Erweiterte Metadaten schreiben ───────────────────────────────
def write_extended_metadata(
    audio_path: Path,
    cover_path: Optional[Path] = None,
    genres: Optional[List[str]] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    track_nr: Optional[str] = None,
    title: Optional[str] = None,
) -> List[str]:
    """
    Schreibt CoverArt (APIC/PICTURE/covr), Genres (TCON/GENRE/©gen),
    Artist, Album und Track-Nr. in die Audio-Metadaten.
    Gibt Liste der geschriebenen Tags zurück.
    """
    written: List[str] = []
    suffix = audio_path.suffix.lower()

    cover_data: Optional[bytes] = None
    cover_mime = "image/jpeg"
    if cover_path and cover_path.exists():
        cover_data = cover_path.read_bytes()
        cover_mime = "image/png" if cover_path.suffix.lower() == ".png" else "image/jpeg"

    genre_str = ", ".join(genres) if genres else None

    if suffix in (".mp3", ".wav", ".aif", ".aiff"):
        from mutagen.id3 import APIC, TCON, TPE1, TALB, TRCK, TIT2, Encoding
        try:
            from mutagen.id3 import PictureType
            cover_type = PictureType.COVER_FRONT
        except ImportError:
            cover_type = 3

        if suffix == ".mp3":
            from mutagen.mp3 import MP3 as Mf
        elif suffix == ".wav":
            from mutagen.wave import WAVE as Mf
        else:
            from mutagen.aiff import AIFF as Mf

        audio = Mf(str(audio_path))
        if audio.tags is None:
            audio.add_tags()

        if cover_data:
            audio.tags.delall("APIC")
            audio.tags.add(APIC(
                encoding=Encoding.UTF8, mime=cover_mime,
                type=cover_type, desc="Cover", data=cover_data))
            written.append("APIC")
        if genre_str:
            audio.tags.delall("TCON")
            audio.tags.add(TCON(encoding=Encoding.UTF8, text=[genre_str]))
            written.append("TCON")
        if artist:
            audio.tags.delall("TPE1")
            audio.tags.add(TPE1(encoding=Encoding.UTF8, text=[artist]))
            written.append("TPE1")
        if album:
            audio.tags.delall("TALB")
            audio.tags.add(TALB(encoding=Encoding.UTF8, text=[album]))
            written.append("TALB")
        if track_nr:
            audio.tags.delall("TRCK")
            audio.tags.add(TRCK(encoding=Encoding.UTF8, text=[str(track_nr)]))
            written.append("TRCK")
        if title:
            audio.tags.delall("TIT2")
            audio.tags.add(TIT2(encoding=Encoding.UTF8, text=[title]))
            written.append("TIT2")
        audio.save()

    elif suffix == ".flac":
        from mutagen.flac import FLAC, Picture
        audio = FLAC(str(audio_path))
        if cover_data:
            pic = Picture()
            pic.type = 3; pic.mime = cover_mime
            pic.desc = "Cover"; pic.data = cover_data
            audio.clear_pictures(); audio.add_picture(pic)
            written.append("PICTURE")
        if genre_str:  audio["GENRE"] = [genre_str]; written.append("GENRE")
        if artist:     audio["ARTIST"] = [artist]; written.append("ARTIST")
        if album:      audio["ALBUM"] = [album]; written.append("ALBUM")
        if track_nr:   audio["TRACKNUMBER"] = [str(track_nr)]; written.append("TRACKNUMBER")
        if title:      audio["TITLE"] = [title]; written.append("TITLE")
        audio.save()

    elif suffix in (".ogg", ".opus"):
        if suffix == ".ogg":
            from mutagen.oggvorbis import OggVorbis as Mf
        else:
            from mutagen.oggopus import OggOpus as Mf
        audio = Mf(str(audio_path))
        if genre_str:  audio["GENRE"] = [genre_str]; written.append("GENRE")
        if artist:     audio["ARTIST"] = [artist]; written.append("ARTIST")
        if album:      audio["ALBUM"] = [album]; written.append("ALBUM")
        if track_nr:   audio["TRACKNUMBER"] = [str(track_nr)]; written.append("TRACKNUMBER")
        if title:      audio["TITLE"] = [title]; written.append("TITLE")
        audio.save()

    elif suffix in (".m4a", ".aac", ".mp4"):
        from mutagen.mp4 import MP4, MP4Cover
        audio = MP4(str(audio_path))
        if cover_data:
            fmt = MP4Cover.FORMAT_PNG if cover_mime == "image/png" else MP4Cover.FORMAT_JPEG
            audio.tags["covr"] = [MP4Cover(cover_data, imageformat=fmt)]
            written.append("covr")
        if genre_str:  audio.tags["©gen"] = [genre_str]; written.append("©gen")
        if artist:     audio.tags["©ART"] = [artist]; written.append("©ART")
        if album:      audio.tags["©alb"] = [album]; written.append("©alb")
        if track_nr:
            audio.tags["trkn"] = [(int(track_nr) if str(track_nr).isdigit() else 0, 0)]
            written.append("trkn")
        if title:      audio.tags["©nam"] = [title]; written.append("©nam")
        audio.save()

    return written


# ── Song-Finder ───────────────────────────────────────────────────
LYRICS_EXTENSIONS = [".txt", ".md"]

def find_lyrics_for_audio(audio_path: Path) -> Optional[Path]:
    """
    Findet die Lyrics-Datei (.txt oder .md) zu einer Audio-Datei.

    Suchstrategie (in Reihenfolge):
    1. Exakter Name:        'Song.wav'          → 'Song.txt' / 'Song.md'
    2. Ohne _mastered:      'Song_mastered.wav' → 'Song.txt' / 'Song.md'
    3. Slug-Matching:       '07 - Kohle an.wav' → '07-kohle-an.md'
                            (normalisierter Vergleich)
    """
    stem, parent = audio_path.stem, audio_path.parent

    # Kandidaten-Stems: original + ohne _mastered-Suffix
    stems_to_try = [stem]
    cleaned = re.sub(r"_mastered.*$", "", stem)
    if cleaned != stem:
        stems_to_try.append(cleaned)

    # 1 + 2: Exakter Name-Match (beide Erweiterungen)
    for s in stems_to_try:
        for ext in LYRICS_EXTENSIONS:
            candidate = parent / (s + ext)
            if candidate.exists():
                return candidate

    # 3: Slug-Matching — alle Lyrics-Dateien im Ordner normalisiert vergleichen
    target_norm = _normalize_name(stems_to_try[-1])  # Basis ohne _mastered
    if not target_norm:
        return None

    for candidate in sorted(parent.iterdir()):
        if candidate.suffix.lower() not in LYRICS_EXTENSIONS:
            continue
        if _normalize_name(candidate.stem) == target_norm:
            return candidate

    return None


def scan_songs(base_dir: Path) -> List[Dict]:
    """Sucht alle Audio-Dateien mit zugehöriger .txt Lyrics-Datei."""
    seen_lrc: set = set()  # Vermeidet Duplikate (gleiche LRC-Zieldatei)
    songs = []

    # Alle Audio-Formate, sortiert so dass Originale vor _mastered kommen
    all_audio = []
    for fmt in AUDIO_FORMATS:
        all_audio.extend(base_dir.rglob(f"*{fmt}"))
    all_audio.sort(key=lambda p: (str(p.parent), p.name))

    for audio in all_audio:
        txt = find_lyrics_for_audio(audio)
        if txt is None: continue
        lrc = audio.with_suffix(".lrc")
        # Gleiche LRC-Datei nicht doppelt anzeigen
        if str(lrc) in seen_lrc: continue
        seen_lrc.add(str(lrc))
        songs.append({
            "audio":     audio,
            "txt":       txt,
            "lrc":       lrc,
            "name":      audio.stem,
            "fmt":       audio.suffix.lower(),
            "lrc_exists": lrc.exists(),
        })

    logging.info(f"Scan '{base_dir}': {len(songs)} Songs")
    return songs


# ── App ───────────────────────────────────────────────────────────
class LRCGeneratorApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("🎵 LRC Generator")  # app title
        self.geometry("820x750")
        self.resizable(True, True)
        self.minsize(700, 580)

        self._songs:    List[Dict] = []
        self._rows:     List[Dict] = []
        self._running   = False
        self._stop_flag = False
        self._log_q:    queue.Queue = queue.Queue()
        self._prog_q:   queue.Queue = queue.Queue()

        self._build_ui()
        self._poll_queues()

        default = Path.home() / "Downloads"
        if default.exists():
            self.folder_var.set(str(default))
            self._scan_songs()

    # ─────────────────────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Header ──────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, padx=20, pady=(20, 0), sticky="ew")
        ctk.CTkLabel(hdr, text="🎵  LRC Generator",
                     font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")
        ctk.CTkLabel(hdr, text="Lyrics timestamps via Whisper Forced Alignment",
                     font=ctk.CTkFont(size=13), text_color="gray").pack(
            side="left", padx=(12, 0), pady=(6, 0))

        # ── Einstellungen ────────────────────────────────────────
        cfg = ctk.CTkFrame(self)
        cfg.grid(row=1, column=0, padx=20, pady=12, sticky="ew")
        cfg.grid_columnconfigure(1, weight=1)

        # Ordner-Zeile
        ctk.CTkLabel(cfg, text="Music Folder:", anchor="w",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=(16, 8), pady=(14, 6), sticky="w")
        frow = ctk.CTkFrame(cfg, fg_color="transparent")
        frow.grid(row=0, column=1, columnspan=2, padx=(0, 16), pady=(14, 6), sticky="ew")
        frow.grid_columnconfigure(0, weight=1)
        self.folder_var = tk.StringVar()
        ctk.CTkEntry(frow, textvariable=self.folder_var,
                     placeholder_text="Choose folder…").grid(
            row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(frow, text="Browse", width=110,
                      command=self._browse).grid(row=0, column=1)

        # Library row: songs_assignment.csv
        ctk.CTkLabel(cfg, text="Music Library:", anchor="w",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, padx=(16, 8), pady=(0, 6), sticky="w")
        lrow = ctk.CTkFrame(cfg, fg_color="transparent")
        lrow.grid(row=1, column=1, columnspan=2, padx=(0, 16), pady=(0, 6), sticky="ew")
        lrow.grid_columnconfigure(0, weight=1)
        self.library_var = tk.StringVar()
        default_lib = Path.home() / "Downloads" / "Music" / "songs_assignment.csv"
        if default_lib.exists():
            self.library_var.set(str(default_lib))
        ctk.CTkEntry(lrow, textvariable=self.library_var,
                     placeholder_text="songs_assignment.csv (optional)…").grid(
            row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(lrow, text="Browse", width=110,
                      command=self._browse_library).grid(row=0, column=1)

        # Options row 1: Model, Language, Overwrite, Rescan
        opts1 = ctk.CTkFrame(cfg, fg_color="transparent")
        opts1.grid(row=2, column=0, columnspan=3, padx=16, pady=(0, 6), sticky="ew")

        ctk.CTkLabel(opts1, text="Model:", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.model_var = tk.StringVar(value="medium")
        ctk.CTkOptionMenu(opts1, values=["tiny", "base", "small", "medium", "large"],
                          variable=self.model_var, width=120).pack(side="left", padx=(6, 20))

        ctk.CTkLabel(opts1, text="Language:", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.lang_var = tk.StringVar(value="en")
        ctk.CTkOptionMenu(opts1, values=["en", "de", "auto"],
                          variable=self.lang_var, width=80).pack(side="left", padx=(6, 20))

        self.overwrite_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(opts1, text="Overwrite existing .lrc",
                        variable=self.overwrite_var,
                        command=self._scan_songs).pack(side="left", padx=4)

        ctk.CTkButton(opts1, text="🔍 Rescan", width=120,
                      fg_color="gray30", hover_color="gray40",
                      command=self._scan_songs).pack(side="right")

        # Options row 2: Synced Lyrics metadata
        opts2 = ctk.CTkFrame(cfg, fg_color="transparent")
        opts2.grid(row=3, column=0, columnspan=3, padx=16, pady=(0, 4), sticky="ew")

        self.meta_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts2,
            text="Synced Lyrics in audio metadata  (WAV/MP3→SYLT · FLAC/OGG→SYNCEDLYRICS · M4A→©lyr)",
            variable=self.meta_var,
            font=ctk.CTkFont(size=12)
        ).pack(side="left")

        # Options row 3: Extended metadata
        opts3 = ctk.CTkFrame(cfg, fg_color="transparent")
        opts3.grid(row=4, column=0, columnspan=3, padx=16, pady=(0, 4), sticky="ew")

        self.cover_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(opts3, text="🖼  Embed cover art",
                        variable=self.cover_var,
                        font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 16))

        self.genres_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(opts3, text="🎵  Genres from JSON",
                        variable=self.genres_var,
                        font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 16))

        self.library_meta_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(opts3, text="📚  Artist / Album / Track from Library",
                        variable=self.library_meta_var,
                        font=ctk.CTkFont(size=12)).pack(side="left")

        # Options row 4: Mastering
        opts4 = ctk.CTkFrame(cfg, fg_color="transparent")
        opts4.grid(row=5, column=0, columnspan=3, padx=16, pady=(0, 14), sticky="ew")

        self.master_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(opts4, text="🎚  Master audio (before LRC generation)",
                        variable=self.master_var,
                        font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 16))

        ctk.CTkLabel(opts4, text="Preset:", font=ctk.CTkFont(size=12)).pack(side="left")
        self.master_preset_var = tk.StringVar(value=list(MASTERING_PRESETS.keys())[0])
        ctk.CTkOptionMenu(opts4,
                          values=list(MASTERING_PRESETS.keys()),
                          variable=self.master_preset_var,
                          width=220,
                          font=ctk.CTkFont(size=12)).pack(side="left", padx=(6, 0))

        # ── Song-Liste ───────────────────────────────────────────
        lf = ctk.CTkFrame(self)
        lf.grid(row=2, column=0, padx=20, pady=0, sticky="nsew")
        lf.grid_columnconfigure(0, weight=1)
        lf.grid_rowconfigure(1, weight=1)

        lhdr = ctk.CTkFrame(lf, fg_color="transparent")
        lhdr.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")

        self.songs_label = ctk.CTkLabel(lhdr, text="Songs: –",
                                         font=ctk.CTkFont(weight="bold"))
        self.songs_label.pack(side="left")
        self.skip_label = ctk.CTkLabel(lhdr, text="", text_color="gray",
                                        font=ctk.CTkFont(size=12))
        self.skip_label.pack(side="left", padx=(10, 0))

        ctk.CTkButton(lhdr, text="None", width=60, height=26,
                      fg_color="gray30", hover_color="gray40",
                      font=ctk.CTkFont(size=12),
                      command=self._select_none).pack(side="right", padx=(4, 0))
        ctk.CTkButton(lhdr, text="All", width=60, height=26,
                      fg_color="gray30", hover_color="gray40",
                      font=ctk.CTkFont(size=12),
                      command=self._select_all).pack(side="right", padx=(4, 0))
        ctk.CTkLabel(lhdr, text="Select:", font=ctk.CTkFont(size=12),
                     text_color="gray").pack(side="right", padx=(12, 4))

        self.scroll_frame = ctk.CTkScrollableFrame(lf, label_text="")
        self.scroll_frame.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.scroll_frame.grid_columnconfigure(1, weight=1)

        # ── Fortschritt ──────────────────────────────────────────
        pf = ctk.CTkFrame(self, fg_color="transparent")
        pf.grid(row=3, column=0, padx=20, pady=(8, 0), sticky="ew")
        pf.grid_columnconfigure(0, weight=1)
        self.progress_label = ctk.CTkLabel(pf, text="Ready.", anchor="w",
                                            font=ctk.CTkFont(size=12), text_color="gray")
        self.progress_label.grid(row=0, column=0, sticky="w")
        self.progress_bar = ctk.CTkProgressBar(pf)
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.progress_bar.set(0)

        # ── Log ──────────────────────────────────────────────────
        logf = ctk.CTkFrame(self)
        logf.grid(row=4, column=0, padx=20, pady=(10, 0), sticky="ew")
        logf.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(logf, text="Log:", anchor="w",  # label
                     font=ctk.CTkFont(size=11), text_color="gray").grid(
            row=0, column=0, padx=12, pady=(8, 2), sticky="w")
        self.log_box = ctk.CTkTextbox(logf, font=ctk.CTkFont(family="Menlo", size=11),
                                       height=100, state="disabled", wrap="word")
        self.log_box.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")

        # ── Buttons ──────────────────────────────────────────────
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.grid(row=5, column=0, padx=20, pady=(8, 20), sticky="ew")
        self.start_btn = ctk.CTkButton(bf, text="▶  Start", width=200, height=44,
                                        font=ctk.CTkFont(size=15, weight="bold"),
                                        command=self._start_or_stop)
        self.start_btn.pack(side="right")
        self.sel_count_label = ctk.CTkLabel(bf, text="", anchor="w",
                                             font=ctk.CTkFont(size=12), text_color="gray")
        self.sel_count_label.pack(side="left")

    # ─────────────────────────────────────────────────────────────
    # Ordner & Scan
    # ─────────────────────────────────────────────────────────────
    def _browse(self):
        folder = filedialog.askdirectory(
            title="Choose music folder",
            initialdir=self.folder_var.get() or str(Path.home() / "Downloads"))
        if folder:
            self.folder_var.set(folder)
            self._scan_songs()

    def _browse_library(self):
        f = filedialog.askopenfilename(
            title="Choose music library (songs_assignment.csv)",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=str(Path.home() / "Downloads" / "Music"))
        if f:
            self.library_var.set(f)

    def _scan_songs(self, *_):
        path_str = self.folder_var.get()
        if not path_str: return
        path = Path(path_str)
        if not path.exists():
            self._rebuild_list([], []); return
        all_songs = scan_songs(path)
        self._songs = all_songs
        overwrite = self.overwrite_var.get()
        to_proc = [s for s in all_songs if overwrite or not s["lrc_exists"]]
        to_skip = [s for s in all_songs if not overwrite and s["lrc_exists"]]
        self._rebuild_list(to_proc, to_skip)

    # ─────────────────────────────────────────────────────────────
    # Checkbox-Liste aufbauen
    # ─────────────────────────────────────────────────────────────
    # Format-Badge Farben
    FMT_COLOR = {
        ".wav":  ("#2e7d32", "#4caf50"),   # grün
        ".mp3":  ("#1565c0", "#42a5f5"),   # blau
        ".flac": ("#6a1b9a", "#ab47bc"),   # lila
        ".m4a":  ("#e65100", "#ff7043"),   # orange
        ".aac":  ("#bf360c", "#ff8a65"),   # dunkelorange
        ".ogg":  ("#00695c", "#26a69a"),   # teal
        ".opus": ("#004d40", "#4db6ac"),   # dunkelteal
        ".aiff": ("#37474f", "#78909c"),   # grau
        ".aif":  ("#37474f", "#78909c"),   # grau
    }

    def _fmt_badge(self, parent, suffix: str):
        color = self.FMT_COLOR.get(suffix, ("gray30", "gray60"))
        lbl = ctk.CTkLabel(parent, text=suffix.lstrip(".").upper(),
                           font=ctk.CTkFont(size=10, weight="bold"),
                           width=42, height=20, corner_radius=4,
                           fg_color=color, text_color="white")
        return lbl

    def _rebuild_list(self, to_proc: List[Dict], to_skip: List[Dict]):
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self._rows = []

        base = Path(self.folder_var.get()) if self.folder_var.get() else None

        def rel(p):
            try:    return str(p.relative_to(base)) if base else p.stem
            except: return p.stem

        for i, song in enumerate(to_proc):
            var = tk.BooleanVar(value=True)

            row = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            row.grid(row=i, column=0, columnspan=3, sticky="ew", pady=1)
            row.grid_columnconfigure(1, weight=1)

            cb = ctk.CTkCheckBox(
                row, text=rel(song["audio"]),
                variable=var,
                font=ctk.CTkFont(family="Menlo", size=12),
                command=self._update_sel_count)
            cb.grid(row=0, column=0, sticky="w", padx=(4, 6))

            badge = self._fmt_badge(row, song["fmt"])
            badge.grid(row=0, column=1, sticky="w", padx=(0, 6))

            status = ctk.CTkLabel(row, text=ICON_PENDING,
                                   font=ctk.CTkFont(size=13), width=26, anchor="e")
            status.grid(row=0, column=2, sticky="e", padx=(0, 8))

            self._rows.append({"var": var, "cb": cb, "status": status, "song": song})

        # Bereits vorhandene (ausgegraut)
        offset = len(to_proc)
        if to_skip:
            sep = ctk.CTkLabel(self.scroll_frame,
                                text=f"── {len(to_skip)} already exist ──",
                                font=ctk.CTkFont(size=11), text_color="gray")
            sep.grid(row=offset, column=0, columnspan=3,
                     pady=(8, 2), padx=8, sticky="w")
            for j, song in enumerate(to_skip):
                row = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
                row.grid(row=offset + 1 + j, column=0,
                         columnspan=3, sticky="ew", pady=1)
                row.grid_columnconfigure(1, weight=1)

                lbl = ctk.CTkLabel(row,
                    text=f"{ICON_SKIP}  {rel(song['audio'])}",
                    font=ctk.CTkFont(family="Menlo", size=12),
                    text_color="gray", anchor="w")
                lbl.grid(row=0, column=0, sticky="w", padx=(28, 6))
                self._fmt_badge(row, song["fmt"]).grid(
                    row=0, column=1, sticky="w")

        self.scroll_frame.grid_columnconfigure(0, weight=1)
        self.songs_label.configure(text=f"Songs: {len(to_proc)} to process")
        self.skip_label.configure(
            text=f"+ {len(to_skip)} existing" if to_skip else "")
        self.progress_bar.set(0)
        self.progress_label.configure(text="Ready.")
        self._update_sel_count()

    def _update_sel_count(self):
        n = sum(1 for r in self._rows if r["var"].get())
        self.sel_count_label.configure(
            text=f"{n} song{'s' if n != 1 else ''} selected")

    def _select_all(self):
        for r in self._rows: r["var"].set(True)
        self._update_sel_count()

    def _select_none(self):
        for r in self._rows: r["var"].set(False)
        self._update_sel_count()

    # ─────────────────────────────────────────────────────────────
    # Start / Stop
    # ─────────────────────────────────────────────────────────────
    def _start_or_stop(self):
        if self._running:
            self._stop_flag = True
            self.start_btn.configure(text="Stopping…", state="disabled",
                                     fg_color="gray40")
        else:
            self._start_processing()

    def _start_processing(self):
        selected = [(r["song"], r["status"]) for r in self._rows if r["var"].get()]
        if not selected:
            messagebox.showinfo("No selection",
                                "Please select at least one song.")
            return

        write_meta = self.meta_var.get()

        # Check for mutagen if metadata is requested
        if write_meta and not _has("mutagen"):
            answer = messagebox.askyesno(
                "mutagen missing",
                "Writing metadata requires 'mutagen'.\n\n"
                "Install now? (one-time, ~1 MB)")
            if answer:
                if not _install("mutagen"):
                    messagebox.showerror("Error",
                        "pip install mutagen failed.\n"
                        "Please install manually: pip install mutagen")
                    return
            else:
                write_meta = False  # Continue without metadata

        self._running = True
        self._stop_flag = False
        self.start_btn.configure(text="⏹  Stop", fg_color="#c0392b",
                                  hover_color="#922b21")
        for r in self._rows:
            r["cb"].configure(state="disabled")
        for _, sl in selected:
            sl.configure(text=ICON_PENDING)

        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

        thread = threading.Thread(
            target=self._process_songs,
            args=(selected, self.model_var.get(), self.lang_var.get(), write_meta,
                  self.cover_var.get(), self.genres_var.get(),
                  self.library_meta_var.get(), self.library_var.get(),
                  self.master_var.get(), self.master_preset_var.get()),
            daemon=True)
        thread.start()

    # ─────────────────────────────────────────────────────────────
    # Verarbeitung (Background-Thread)
    # ─────────────────────────────────────────────────────────────
    def _process_songs(self, selected: List, model_name: str,
                       lang: str, write_meta: bool,
                       embed_cover: bool = True, use_genres: bool = True,
                       use_library: bool = True, library_path: str = "",
                       do_master: bool = False,
                       master_preset: str = "Suno-Standard"):
        try:
            self._log(f"⚙️  Loading Whisper model '{model_name}'…")
            self._log("   (First download may take several minutes)")

            try:
                import stable_whisper
            except ImportError as _ie:
                self._log(f"❌ Import error: {_ie}")
                self._log(f"   Python: {sys.executable}")
                import sys as _sys; self._log(f"   sys.path: {_sys.path}")
                self._log(f"   Run: {sys.executable} -m pip install stable-ts")
                self._set_prog("Error: stable-ts missing", None)
                self.after(0, lambda: messagebox.showerror("stable-ts missing",
                    f"Please run in terminal:\n\n  {sys.executable} -m pip install stable-ts"))
                self._finish(); return

            language = lang if lang and lang != "auto" else None
            lang_tag  = "deu" if lang == "de" else ("eng" if lang == "en" else "und")
            # stderr umleiten → tqdm-Fortschritt in die UI
            import sys as _sys
            _old_stderr = _sys.stderr
            _sys.stderr = _StderrCapture(
                log_fn    = lambda s: self._log(f"   {s}"),
                status_fn = lambda s: self._set_prog(s, None)
            )
            try:
                model = stable_whisper.load_model(model_name)
            finally:
                _sys.stderr = _old_stderr

            self._log("✅ Model loaded.\n")

            # ── Load library once ──
            library: Dict = {}
            if use_library and library_path:
                lib_p = Path(library_path)
                if lib_p.exists():
                    library = load_music_library(lib_p)
                    self._log(f"📚 Library: {len(library)} entries loaded\n")
                else:
                    self._log(f"⚠  Library not found: {lib_p.name}\n")

            total = len(selected)
            success = failed = 0

            for i, (song, status_lbl) in enumerate(selected):
                if self._stop_flag:
                    self._log("\n⏹  Stopped."); break

                audio, txt, lrc, name = (
                    song["audio"], song["txt"], song["lrc"], song["name"])

                self._set_icon(status_lbl, ICON_RUNNING)
                self._set_prog(f"[{i+1}/{total}]  {name}", None)
                self._log(f"🎵 {name}  [{song['fmt'].lstrip('.')}]")

                # ── Begleitdateien suchen ──
                cover_path = find_cover_art(audio) if embed_cover else None
                json_path  = find_json_file(audio) if use_genres else None
                lib_entry  = find_library_entry(audio, library) if use_library else None

                lyrics = parse_lyrics(txt)
                if not lyrics.strip():
                    self._log("   ⚠ No lyrics found — skipped")
                    self._set_icon(status_lbl, ICON_SKIP)
                    continue

                # ── Mastering (optional, vor LRC) ──
                audio_for_lrc = audio   # Standardmäßig Originaldatei
                if do_master:
                    mastered = master_audio(audio, master_preset, log_fn=self._log)
                    if mastered:
                        audio_for_lrc = mastered  # Gemasterte Datei für LRC verwenden
                    else:
                        self._log("   ⚠ Mastering failed — continuing with original")

                try:
                    # ── LRC generieren ──
                    result = model.align(str(audio_for_lrc), lyrics, language=language)
                    # LRC neben die gemasterte Datei schreiben (falls gemastert)
                    lrc_target = audio_for_lrc.with_suffix(".lrc")
                    write_lrc(result, lrc_target, song_name=name)
                    self._log(f"   ✅ LRC: {lrc_target.name}")

                    # ── Synced Lyrics in metadata ──
                    if write_meta:
                        try:
                            tag_info = write_metadata(audio_for_lrc, lrc_target, lang=lang_tag)
                            self._log(f"   🏷  Lyrics tags: {tag_info}")
                        except Exception as me:
                            self._log(f"   ⚠ Lyrics metadata error: {me}")
                            logging.warning(f"Metadaten {name}: {me}")

                    # ── Erweiterte Metadaten: Cover, Genres, Artist, Album ──
                    do_extended = embed_cover or use_genres or use_library
                    if do_extended:
                        try:
                            genres = extract_genres_from_json(json_path) if json_path else []
                            artist   = lib_entry.get("artist", "").strip() if lib_entry else None
                            album    = lib_entry.get("album", "").strip()  if lib_entry else None
                            track_nr = lib_entry.get("track_nr", "").strip() if lib_entry else None
                            title    = lib_entry.get("titel", "").strip()  if lib_entry else None
                            # Library-Genres überschreiben JSON falls vorhanden
                            if lib_entry and lib_entry.get("genre", "").strip():
                                raw = lib_entry["genre"].strip()
                                genres = [g.strip() for g in raw.split(",")][:4]

                            ext_tags = write_extended_metadata(
                                audio_for_lrc,
                                cover_path=cover_path if embed_cover else None,
                                genres=genres if (use_genres and genres) else None,
                                artist=artist   if use_library else None,
                                album=album     if use_library else None,
                                track_nr=track_nr if use_library else None,
                                title=title     if use_library else None,
                            )
                            if ext_tags:
                                cover_note = f"🖼 {cover_path.name}" if cover_path else ""
                                genre_note = f"🎵 {', '.join(genres)}" if genres else ""
                                self._log(f"   ✨ Ext. tags: {' · '.join(filter(None, [cover_note, genre_note]))}")
                                self._log(f"      {', '.join(ext_tags)}")
                        except Exception as xe:
                            self._log(f"   ⚠ Extended metadata error: {xe}")
                            logging.warning(f"ExtMetadaten {name}: {xe}")

                    self._set_icon(status_lbl, ICON_DONE)
                    success += 1
                    logging.info(f"OK: {lrc}")

                except Exception as e:
                    self._log(f"   ❌ {e}")
                    self._set_icon(status_lbl, ICON_ERROR)
                    logging.error(f"Fehler {name}: {e}")
                    failed += 1

                self._set_prog(f"[{i+1}/{total}]  {name}", (i + 1) / total)

            self._log(f"\n{'─'*50}")
            self._log(f"🎉 Done! {success} LRC file{'s' if success != 1 else ''} created"
                      + (f", {failed} error{'s' if failed != 1 else ''}" if failed else ""))
            self._set_prog(f"Done! {success}/{total} created.", 1.0)

        except Exception as e:
            logging.exception(e)
            self._log(f"❌ Critical error: {e}")
        finally:
            self._finish()

    def _finish(self):
        self._running = False
        self._stop_flag = False
        def restore():
            self.start_btn.configure(text="▶  Start", state="normal",
                                     fg_color=["#3a7ebf", "#1f538d"],
                                     hover_color=["#325882", "#14375e"])
            for r in self._rows:
                r["cb"].configure(state="normal")
        self.after(0, restore)

    # ─────────────────────────────────────────────────────────────
    # Thread-sichere Helfer
    # ─────────────────────────────────────────────────────────────
    def _log(self, msg: str):
        self._log_q.put(("log", msg + "\n"))

    def _set_prog(self, label: str, value: Optional[float]):
        self._prog_q.put((label, value))

    def _set_icon(self, widget, icon: str):
        self._log_q.put(("icon", widget, icon))

    def _poll_queues(self):
        try:
            while True:
                item = self._log_q.get_nowait()
                if item[0] == "icon":
                    _, widget, icon = item
                    widget.configure(text=icon)
                else:
                    _, text = item
                    self.log_box.configure(state="normal")
                    self.log_box.insert("end", text)
                    self.log_box.see("end")
                    self.log_box.configure(state="disabled")
        except queue.Empty:
            pass

        try:
            while True:
                label, value = self._prog_q.get_nowait()
                if label: self.progress_label.configure(text=label)
                if value is not None: self.progress_bar.set(value)
        except queue.Empty:
            pass

        self.after(100, self._poll_queues)


# ── Entry Point ───────────────────────────────────────────────────
if __name__ == "__main__":
    # freeze_support() prevents PyInstaller from spawning a second
    # process on macOS when multiprocessing is used by torch/whisper
    import multiprocessing
    multiprocessing.freeze_support()

    try:
        app = LRCGeneratorApp()
        app.mainloop()
    except Exception as e:
        logging.exception(e); raise
