#!/usr/bin/env python3
"""
LRC Generator — Mac App
Erstellt .lrc Timestamp-Dateien für Suno-Songs via Forced Alignment
und schreibt Synced Lyrics optional in Audio-Metadaten (SYLT/SYNCEDLYRICS).
"""

import os
import re
import sys
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
    ok = messagebox.askyesno("Abhängigkeit fehlt",
        "'customtkinter' ist nicht installiert.\nJetzt automatisch installieren?")
    r.destroy()
    if ok:
        if not _install("customtkinter"):
            import tkinter as tk; from tkinter import messagebox
            r2 = tk.Tk(); r2.withdraw()
            messagebox.showerror("Fehler", "pip fehlgeschlagen.\n"
                                 "Bitte manuell: pip install customtkinter")
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
        return "keine LRC-Einträge"

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
        return f"Format nicht unterstützt: {suffix}"


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
        self.title("🎵 LRC Generator")
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
        ctk.CTkLabel(hdr, text="Lyrics-Timestamps via Whisper Forced Alignment",
                     font=ctk.CTkFont(size=13), text_color="gray").pack(
            side="left", padx=(12, 0), pady=(6, 0))

        # ── Einstellungen ────────────────────────────────────────
        cfg = ctk.CTkFrame(self)
        cfg.grid(row=1, column=0, padx=20, pady=12, sticky="ew")
        cfg.grid_columnconfigure(1, weight=1)

        # Ordner-Zeile
        ctk.CTkLabel(cfg, text="Musik-Ordner:", anchor="w",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=(16, 8), pady=(14, 6), sticky="w")
        frow = ctk.CTkFrame(cfg, fg_color="transparent")
        frow.grid(row=0, column=1, columnspan=2, padx=(0, 16), pady=(14, 6), sticky="ew")
        frow.grid_columnconfigure(0, weight=1)
        self.folder_var = tk.StringVar()
        ctk.CTkEntry(frow, textvariable=self.folder_var,
                     placeholder_text="Ordner wählen…").grid(
            row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(frow, text="Durchsuchen", width=110,
                      command=self._browse).grid(row=0, column=1)

        # Optionen-Zeile 1: Modell, Sprache, Überschreiben, Neu scannen
        opts1 = ctk.CTkFrame(cfg, fg_color="transparent")
        opts1.grid(row=1, column=0, columnspan=3, padx=16, pady=(0, 6), sticky="ew")

        ctk.CTkLabel(opts1, text="Modell:", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.model_var = tk.StringVar(value="medium")
        ctk.CTkOptionMenu(opts1, values=["tiny", "base", "small", "medium", "large"],
                          variable=self.model_var, width=120).pack(side="left", padx=(6, 20))

        ctk.CTkLabel(opts1, text="Sprache:", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.lang_var = tk.StringVar(value="de")
        ctk.CTkOptionMenu(opts1, values=["de", "en", "auto"],
                          variable=self.lang_var, width=80).pack(side="left", padx=(6, 20))

        self.overwrite_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(opts1, text="Bestehende .lrc überschreiben",
                        variable=self.overwrite_var,
                        command=self._scan_songs).pack(side="left", padx=4)

        ctk.CTkButton(opts1, text="🔍 Neu scannen", width=120,
                      fg_color="gray30", hover_color="gray40",
                      command=self._scan_songs).pack(side="right")

        # Optionen-Zeile 2: Metadaten
        opts2 = ctk.CTkFrame(cfg, fg_color="transparent")
        opts2.grid(row=2, column=0, columnspan=3, padx=16, pady=(0, 14), sticky="ew")

        self.meta_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts2,
            text="Synced Lyrics auch in Audio-Metadaten schreiben  "
                 "(WAV/MP3→SYLT · FLAC/OGG→SYNCEDLYRICS · M4A→©lyr)",
            variable=self.meta_var,
            font=ctk.CTkFont(size=12)
        ).pack(side="left")

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

        ctk.CTkButton(lhdr, text="Keine", width=60, height=26,
                      fg_color="gray30", hover_color="gray40",
                      font=ctk.CTkFont(size=12),
                      command=self._select_none).pack(side="right", padx=(4, 0))
        ctk.CTkButton(lhdr, text="Alle", width=60, height=26,
                      fg_color="gray30", hover_color="gray40",
                      font=ctk.CTkFont(size=12),
                      command=self._select_all).pack(side="right", padx=(4, 0))
        ctk.CTkLabel(lhdr, text="Auswahl:", font=ctk.CTkFont(size=12),
                     text_color="gray").pack(side="right", padx=(12, 4))

        self.scroll_frame = ctk.CTkScrollableFrame(lf, label_text="")
        self.scroll_frame.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.scroll_frame.grid_columnconfigure(1, weight=1)

        # ── Fortschritt ──────────────────────────────────────────
        pf = ctk.CTkFrame(self, fg_color="transparent")
        pf.grid(row=3, column=0, padx=20, pady=(8, 0), sticky="ew")
        pf.grid_columnconfigure(0, weight=1)
        self.progress_label = ctk.CTkLabel(pf, text="Bereit.", anchor="w",
                                            font=ctk.CTkFont(size=12), text_color="gray")
        self.progress_label.grid(row=0, column=0, sticky="w")
        self.progress_bar = ctk.CTkProgressBar(pf)
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.progress_bar.set(0)

        # ── Log ──────────────────────────────────────────────────
        logf = ctk.CTkFrame(self)
        logf.grid(row=4, column=0, padx=20, pady=(10, 0), sticky="ew")
        logf.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(logf, text="Log:", anchor="w",
                     font=ctk.CTkFont(size=11), text_color="gray").grid(
            row=0, column=0, padx=12, pady=(8, 2), sticky="w")
        self.log_box = ctk.CTkTextbox(logf, font=ctk.CTkFont(family="Menlo", size=11),
                                       height=100, state="disabled", wrap="word")
        self.log_box.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")

        # ── Buttons ──────────────────────────────────────────────
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.grid(row=5, column=0, padx=20, pady=(8, 20), sticky="ew")
        self.start_btn = ctk.CTkButton(bf, text="▶  Starten", width=200, height=44,
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
            title="Musik-Ordner wählen",
            initialdir=self.folder_var.get() or str(Path.home() / "Downloads"))
        if folder:
            self.folder_var.set(folder)
            self._scan_songs()

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
                                text=f"── {len(to_skip)} bereits vorhanden ──",
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
        self.songs_label.configure(text=f"Songs: {len(to_proc)} zu verarbeiten")
        self.skip_label.configure(
            text=f"+ {len(to_skip)} vorhanden" if to_skip else "")
        self.progress_bar.set(0)
        self.progress_label.configure(text="Bereit.")
        self._update_sel_count()

    def _update_sel_count(self):
        n = sum(1 for r in self._rows if r["var"].get())
        self.sel_count_label.configure(
            text=f"{n} Song{'s' if n != 1 else ''} ausgewählt")

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
            self.start_btn.configure(text="Wird gestoppt…", state="disabled",
                                     fg_color="gray40")
        else:
            self._start_processing()

    def _start_processing(self):
        selected = [(r["song"], r["status"]) for r in self._rows if r["var"].get()]
        if not selected:
            messagebox.showinfo("Keine Auswahl",
                                "Bitte mindestens einen Song auswählen.")
            return

        write_meta = self.meta_var.get()

        # Mutagen prüfen wenn Metadaten gewünscht
        if write_meta and not _has("mutagen"):
            answer = messagebox.askyesno(
                "mutagen fehlt",
                "Für Metadaten-Schreiben wird 'mutagen' benötigt.\n\n"
                "Jetzt installieren? (einmalig, ~1 MB)")
            if answer:
                if not _install("mutagen"):
                    messagebox.showerror("Fehler",
                        "pip install mutagen fehlgeschlagen.\n"
                        "Bitte manuell: pip install mutagen")
                    return
            else:
                write_meta = False  # Ohne Metadaten weitermachen

        self._running = True
        self._stop_flag = False
        self.start_btn.configure(text="⏹  Stoppen", fg_color="#c0392b",
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
            args=(selected, self.model_var.get(), self.lang_var.get(), write_meta),
            daemon=True)
        thread.start()

    # ─────────────────────────────────────────────────────────────
    # Verarbeitung (Background-Thread)
    # ─────────────────────────────────────────────────────────────
    def _process_songs(self, selected: List, model_name: str,
                       lang: str, write_meta: bool):
        try:
            self._log(f"⚙️  Lade Whisper-Modell '{model_name}'…")
            self._log("   (Erster Download kann einige Minuten dauern)")

            try:
                import stable_whisper
            except ImportError as _ie:
                self._log(f"❌ Import-Fehler: {_ie}")
                self._log(f"   Python: {sys.executable}")
                import sys as _sys; self._log(f"   sys.path: {_sys.path}")
                self._log(f"   Ausführen: {sys.executable} -m pip install stable-ts")
                self._set_prog("Fehler: stable-ts fehlt", None)
                self.after(0, lambda: messagebox.showerror("stable-ts fehlt",
                    f"Bitte im Terminal:\n\n  {sys.executable} -m pip install stable-ts"))
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

            self._log("✅ Modell geladen.\n")

            total = len(selected)
            success = failed = 0

            for i, (song, status_lbl) in enumerate(selected):
                if self._stop_flag:
                    self._log("\n⏹  Gestoppt."); break

                audio, txt, lrc, name = (
                    song["audio"], song["txt"], song["lrc"], song["name"])

                self._set_icon(status_lbl, ICON_RUNNING)
                self._set_prog(f"[{i+1}/{total}]  {name}", None)
                self._log(f"🎵 {name}  [{song['fmt'].lstrip('.')}]")

                lyrics = parse_lyrics(txt)
                if not lyrics.strip():
                    self._log("   ⚠ Keine Lyrics — übersprungen")
                    self._set_icon(status_lbl, ICON_SKIP)
                    continue

                try:
                    # ── LRC generieren ──
                    result = model.align(str(audio), lyrics, language=language)
                    write_lrc(result, lrc, song_name=name)
                    self._log(f"   ✅ LRC: {lrc.name}")

                    # ── Metadaten schreiben ──
                    if write_meta:
                        try:
                            tag_info = write_metadata(audio, lrc, lang=lang_tag)
                            self._log(f"   🏷  Metadaten: {tag_info}")
                        except Exception as me:
                            self._log(f"   ⚠ Metadaten-Fehler: {me}")
                            logging.warning(f"Metadaten {name}: {me}")

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
            self._log(f"🎉 Fertig! {success} LRC-Dateien erstellt"
                      + (f", {failed} Fehler" if failed else ""))
            self._set_prog(f"Fertig! {success}/{total} erstellt.", 1.0)

        except Exception as e:
            logging.exception(e)
            self._log(f"❌ Kritischer Fehler: {e}")
        finally:
            self._finish()

    def _finish(self):
        self._running = False
        self._stop_flag = False
        def restore():
            self.start_btn.configure(text="▶  Starten", state="normal",
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
    try:
        app = LRCGeneratorApp()
        app.mainloop()
    except Exception as e:
        logging.exception(e); raise
