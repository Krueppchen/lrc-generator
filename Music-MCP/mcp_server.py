#!/usr/bin/env python3
"""
Music-MCP Server
════════════════
MCP-Server für Claude Cowork — orchestriert den kompletten
Suno-Song-Workflow: Scannen → LRC generieren → Metadaten setzen
→ In Bibliothek verschieben → CSV aktualisieren.

Claude übernimmt die intelligenten Entscheidungen (Genres interpretieren,
Metadaten bestimmen). Dieser Server stellt die Werkzeuge bereit.

Starten: python3 mcp_server.py
Config:  mcp_config.json (im gleichen Ordner)
"""

import json
import csv
import re
import os
import shutil
import logging
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

# ── Logging ───────────────────────────────────────────────────────
LOG_PATH = Path.home() / "Library" / "Logs" / "MusicMCP.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_PATH), level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)

# ── Config laden ──────────────────────────────────────────────────
_HERE = Path(__file__).parent
_CFG_PATH = _HERE / "mcp_config.json"

def _load_config() -> dict:
    try:
        raw = json.loads(_CFG_PATH.read_text(encoding="utf-8"))
        # Pfade expandieren (~)
        for key in ["suno_downloads", "library_csv", "library_root"]:
            if key in raw:
                raw[key] = str(Path(raw[key]).expanduser())
        return raw
    except Exception as e:
        logging.error(f"Config-Fehler: {e}")
        return {}

CFG = _load_config()
SUNO_DIR    = Path(CFG.get("suno_downloads", "~/Downloads/Suno Downloads")).expanduser()
LIBRARY_CSV = Path(CFG.get("library_csv", "~/Downloads/Music/songs_assignment.csv")).expanduser()
LIBRARY_ROOT = Path(CFG.get("library_root", "~/Music/Musikbibliothek")).expanduser()
WHISPER_MODEL = CFG.get("whisper_model", "medium")
LANGUAGE      = CFG.get("language", "de")
MAX_GENRES    = int(CFG.get("max_genres", 4))

AUDIO_FORMATS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif"}

# ── MCP Server ────────────────────────────────────────────────────
mcp = FastMCP(
    "Music Library Manager",
    instructions="""
Du verwaltest die Musik-Bibliothek von Tim.

Workflow für neue Suno-Songs:
1. scan_folder(subfolder) — zeigt was neu ist
2. read_song_json(song, subfolder) — JSON lesen, Genres/Metadaten SELBST interpretieren
3. generate_lrc(audio_path, lyrics_path) — LRC via Whisper erzeugen
4. embed_metadata(audio_path, ...) — alles in die Datei schreiben
5. move_to_library(audio_path, artist, album, track_nr, title) — in Bibliothek verschieben
6. update_library_csv(...) — Datenbank aktualisieren

Pfade aus der Config:
- Suno Downloads: """ + str(SUNO_DIR) + """
- Library CSV:    """ + str(LIBRARY_CSV) + """
- Library Root:   """ + str(LIBRARY_ROOT) + """
"""
)


# ════════════════════════════════════════════════════════════════
# TOOL 1: Ordner scannen
# ════════════════════════════════════════════════════════════════
@mcp.tool()
def scan_folder(subfolder: str = "") -> dict:
    """
    Scannt einen Unterordner in Suno Downloads nach Songs.
    Gibt für jeden Song zurück: Audio-Pfad, Lyrics vorhanden?,
    JSON vorhanden?, Cover vorhanden?, LRC bereits vorhanden?

    Args:
        subfolder: Unterordner in Suno Downloads (z.B. "Jungs", "Nice Touchy").
                   Leer lassen für den Root-Ordner.
    """
    target = SUNO_DIR / subfolder if subfolder else SUNO_DIR
    if not target.exists():
        return {"error": f"Ordner nicht gefunden: {target}"}

    songs = []
    for audio in sorted(target.rglob("*")):
        if audio.suffix.lower() not in AUDIO_FORMATS:
            continue

        stem_clean = re.sub(r"_mastered.*$", "", audio.stem, flags=re.IGNORECASE)
        parent = audio.parent

        def _exists_any(s, exts):
            return any((parent / (s + e)).exists() for e in exts)

        has_lyrics = _exists_any(audio.stem, [".txt", ".md"]) or \
                     _exists_any(stem_clean, [".txt", ".md"])
        has_json   = _exists_any(audio.stem, [".json"]) or \
                     _exists_any(stem_clean, [".json"])
        has_cover  = _exists_any(audio.stem, [".jpg", ".jpeg", ".png"]) or \
                     _exists_any(stem_clean, [".jpg", ".jpeg", ".png"])
        has_lrc    = audio.with_suffix(".lrc").exists()

        songs.append({
            "name":        audio.stem,
            "audio_path":  str(audio),
            "format":      audio.suffix.lower().lstrip("."),
            "has_lyrics":  has_lyrics,
            "has_json":    has_json,
            "has_cover":   has_cover,
            "lrc_exists":  has_lrc,
            "ready":       has_lyrics and not has_lrc,
        })

    ready = sum(1 for s in songs if s["ready"])
    logging.info(f"scan_folder('{subfolder}'): {len(songs)} Songs, {ready} bereit")
    return {
        "folder":     str(target),
        "total":      len(songs),
        "ready":      ready,
        "songs":      songs,
    }


# ════════════════════════════════════════════════════════════════
# TOOL 2: Song-JSON lesen (Claude interpretiert selbst)
# ════════════════════════════════════════════════════════════════
@mcp.tool()
def read_song_json(song_name: str, subfolder: str = "") -> dict:
    """
    Liest die Suno-JSON-Datei eines Songs und gibt den Inhalt zurück.
    Claude interpretiert daraus Genres, Stimmung, BPM etc. selbst.

    Args:
        song_name: Name des Songs (ohne Dateiendung, ohne _mastered)
        subfolder: Unterordner in Suno Downloads (z.B. "Jungs")
    """
    base = SUNO_DIR / subfolder if subfolder else SUNO_DIR
    stem_clean = re.sub(r"_mastered.*$", "", song_name, flags=re.IGNORECASE)

    for stem in [song_name, stem_clean]:
        for candidate in [base / f"{stem}.json"]:
            if candidate.exists():
                try:
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                    logging.info(f"read_song_json: {candidate.name}")
                    return {
                        "file":     str(candidate),
                        "content":  data,
                        "hint":     (
                            "Interpretiere 'metadata.tags' und "
                            "'metadata.artist_reference_warning.artist_to_tag_mapping' "
                            f"um max. {MAX_GENRES} passende Genres zu bestimmen. "
                            "Nutze 'display_name' als Artist, 'project_name' als Album, "
                            "'title' als Songtitel."
                        ),
                    }
                except Exception as e:
                    return {"error": f"JSON-Lesefehler: {e}"}

    return {"error": f"Keine JSON-Datei gefunden für '{song_name}' in {base}"}


# ════════════════════════════════════════════════════════════════
# TOOL 3: LRC generieren (Whisper Forced Alignment)
# ════════════════════════════════════════════════════════════════
@mcp.tool()
def generate_lrc(
    audio_path: str,
    lyrics_path: str,
    model: str = "",
    language: str = "",
) -> dict:
    """
    Erzeugt eine .lrc-Datei via Whisper Forced Alignment (stable-ts).
    Die LRC-Datei wird neben der Audio-Datei gespeichert.

    Args:
        audio_path:  Absoluter Pfad zur Audio-Datei
        lyrics_path: Absoluter Pfad zur Lyrics-Datei (.txt oder .md)
        model:       Whisper-Modell (tiny/base/small/medium/large). Leer = Config-Default
        language:    Sprache (de/en/auto). Leer = Config-Default
    """
    audio  = Path(audio_path)
    lyrics = Path(lyrics_path)
    model  = model or WHISPER_MODEL
    lang   = language or LANGUAGE

    if not audio.exists():
        return {"error": f"Audio nicht gefunden: {audio}"}
    if not lyrics.exists():
        return {"error": f"Lyrics nicht gefunden: {lyrics}"}

    # Lyrics parsen (Section-Marker und Suno-Metadaten entfernen)
    raw = lyrics.read_text(encoding="utf-8")
    lyric_lines = []
    in_prompt = "Prompt:" in raw or "prompt:" in raw.lower()
    active = not in_prompt
    STOP = re.compile(
        r"^(Genre|Style|Tags|BPM|Tempo|Mood|This\s+(song|track)|The\s+(song|track))",
        re.IGNORECASE
    )
    for line in raw.splitlines():
        line = line.strip()
        if re.match(r"^Prompt\s*:", line, re.IGNORECASE): active = True; continue
        if re.match(r"^(Title|ID)\s*:", line, re.IGNORECASE): continue
        if not active: continue
        if STOP.match(line): break
        if re.match(r"^\[.+\]$", line): continue
        if line: lyric_lines.append(line)

    clean_lyrics = "\n".join(lyric_lines)
    if not clean_lyrics.strip():
        return {"error": "Keine verwertbaren Lyrics gefunden"}

    try:
        import stable_whisper
        language_arg = lang if lang != "auto" else None
        model_obj = stable_whisper.load_model(model)
        result    = model_obj.align(str(audio), clean_lyrics, language=language_arg)

        lrc_path = audio.with_suffix(".lrc")

        if hasattr(result, "to_lrc"):
            result.to_lrc(str(lrc_path))
        else:
            lines = [f"[ti:{audio.stem}]", ""]
            for seg in getattr(result, "segments", []):
                start = getattr(seg, "start", None)
                text  = getattr(seg, "text", "").strip()
                if start is not None and text:
                    m = int(start // 60); s = start % 60
                    lines.append(f"[{m:02d}:{s:05.2f}]{text}")
            lrc_path.write_text("\n".join(lines), encoding="utf-8")

        logging.info(f"generate_lrc OK: {lrc_path}")
        return {
            "success":  True,
            "lrc_path": str(lrc_path),
            "model":    model,
            "language": lang,
            "lines":    lrc_path.read_text(encoding="utf-8").count("\n"),
        }

    except Exception as e:
        logging.error(f"generate_lrc Fehler: {e}")
        return {"error": str(e)}


# ════════════════════════════════════════════════════════════════
# TOOL 4: Metadaten einbetten
# ════════════════════════════════════════════════════════════════
@mcp.tool()
def embed_metadata(
    audio_path: str,
    title:      str = "",
    artist:     str = "",
    album:      str = "",
    track_nr:   str = "",
    genres:     list[str] = [],
    lrc_path:   str = "",
    cover_path: str = "",
) -> dict:
    """
    Schreibt alle Metadaten in die Audio-Datei:
    - Synced Lyrics (SYLT/SYNCEDLYRICS) aus der LRC-Datei
    - CoverArt (APIC/PICTURE/covr) aus Bilddatei
    - Genres (TCON/GENRE/©gen)
    - Artist, Album, Track-Nr., Titel

    Args:
        audio_path: Absoluter Pfad zur Audio-Datei
        title:      Songtitel
        artist:     Künstlername
        album:      Album-/Projektname
        track_nr:   Track-Nummer (als String, z.B. "3")
        genres:     Liste von Genres (max. 4), z.B. ["German Rap", "Hip Hop"]
        lrc_path:   Pfad zur .lrc-Datei (leer = gleicher Name wie Audio)
        cover_path: Pfad zur Cover-Bilddatei (leer = automatisch suchen)
    """
    audio = Path(audio_path)
    if not audio.exists():
        return {"error": f"Audio nicht gefunden: {audio}"}

    suffix = audio.suffix.lower()
    written = []

    # LRC-Pfad auflösen
    lrc = Path(lrc_path) if lrc_path else audio.with_suffix(".lrc")

    # Cover suchen
    cover = Path(cover_path) if cover_path else None
    if not cover:
        stem = re.sub(r"_mastered.*$", "", audio.stem, flags=re.IGNORECASE)
        for s in [audio.stem, stem]:
            for ext in [".jpg", ".jpeg", ".png"]:
                c = audio.parent / (s + ext)
                if c.exists(): cover = c; break
            if cover: break

    cover_data = cover.read_bytes() if (cover and cover.exists()) else None
    cover_mime = "image/png" if (cover and cover.suffix.lower() == ".png") else "image/jpeg"
    genre_str  = ", ".join(genres[:MAX_GENRES]) if genres else None

    try:
        # ── ID3: WAV / MP3 / AIFF ────────────────────────────────
        if suffix in (".mp3", ".wav", ".aif", ".aiff"):
            from mutagen.id3 import (APIC, TCON, TPE1, TALB, TRCK, TIT2,
                                      SYLT, USLT, Encoding)
            if suffix == ".mp3":
                from mutagen.mp3 import MP3 as Mf
            elif suffix == ".wav":
                from mutagen.wave import WAVE as Mf
            else:
                from mutagen.aiff import AIFF as Mf

            audio_tag = Mf(str(audio))
            if audio_tag.tags is None: audio_tag.add_tags()
            t = audio_tag.tags

            # Synced Lyrics
            if lrc.exists():
                entries = _parse_lrc(lrc)
                if entries:
                    t.delall("SYLT")
                    t.add(SYLT(encoding=Encoding.UTF8, lang="deu",
                               format=2, type=1,
                               text=[(tx, ts) for tx, ts in entries]))
                    t.delall("USLT")
                    t.add(USLT(encoding=Encoding.UTF8, lang="deu", desc="",
                               text="\n".join(tx for tx, _ in entries)))
                    written.append("SYLT+USLT")

            if cover_data:
                t.delall("APIC")
                t.add(APIC(encoding=Encoding.UTF8, mime=cover_mime,
                           type=3, desc="Cover", data=cover_data))
                written.append("APIC")
            if genre_str:
                t.delall("TCON"); t.add(TCON(encoding=Encoding.UTF8, text=[genre_str]))
                written.append("TCON")
            if artist:
                t.delall("TPE1"); t.add(TPE1(encoding=Encoding.UTF8, text=[artist]))
                written.append("TPE1")
            if album:
                t.delall("TALB"); t.add(TALB(encoding=Encoding.UTF8, text=[album]))
                written.append("TALB")
            if track_nr:
                t.delall("TRCK"); t.add(TRCK(encoding=Encoding.UTF8, text=[str(track_nr)]))
                written.append("TRCK")
            if title:
                t.delall("TIT2"); t.add(TIT2(encoding=Encoding.UTF8, text=[title]))
                written.append("TIT2")
            audio_tag.save()

        # ── FLAC ─────────────────────────────────────────────────
        elif suffix == ".flac":
            from mutagen.flac import FLAC, Picture
            audio_tag = FLAC(str(audio))
            if lrc.exists():
                lrc_txt = lrc.read_text(encoding="utf-8")
                audio_tag["SYNCEDLYRICS"] = [lrc_txt]
                audio_tag["LYRICS"] = ["\n".join(l.split("]",1)[-1]
                                        for l in lrc_txt.splitlines() if "]" in l)]
                written.append("SYNCEDLYRICS")
            if cover_data:
                pic = Picture(); pic.type = 3; pic.mime = cover_mime
                pic.desc = "Cover"; pic.data = cover_data
                audio_tag.clear_pictures(); audio_tag.add_picture(pic)
                written.append("PICTURE")
            if genre_str:  audio_tag["GENRE"]       = [genre_str]; written.append("GENRE")
            if artist:     audio_tag["ARTIST"]      = [artist];    written.append("ARTIST")
            if album:      audio_tag["ALBUM"]       = [album];     written.append("ALBUM")
            if track_nr:   audio_tag["TRACKNUMBER"] = [str(track_nr)]; written.append("TRACKNUMBER")
            if title:      audio_tag["TITLE"]       = [title];     written.append("TITLE")
            audio_tag.save()

        # ── OGG / Opus ────────────────────────────────────────────
        elif suffix in (".ogg", ".opus"):
            from mutagen.oggvorbis import OggVorbis
            from mutagen.oggopus  import OggOpus
            Mf = OggVorbis if suffix == ".ogg" else OggOpus
            audio_tag = Mf(str(audio))
            if lrc.exists():
                audio_tag["SYNCEDLYRICS"] = [lrc.read_text(encoding="utf-8")]
                written.append("SYNCEDLYRICS")
            if genre_str:  audio_tag["GENRE"]       = [genre_str]; written.append("GENRE")
            if artist:     audio_tag["ARTIST"]      = [artist];    written.append("ARTIST")
            if album:      audio_tag["ALBUM"]       = [album];     written.append("ALBUM")
            if track_nr:   audio_tag["TRACKNUMBER"] = [str(track_nr)]; written.append("TRACKNUMBER")
            if title:      audio_tag["TITLE"]       = [title];     written.append("TITLE")
            audio_tag.save()

        # ── M4A / AAC ─────────────────────────────────────────────
        elif suffix in (".m4a", ".aac", ".mp4"):
            from mutagen.mp4 import MP4, MP4Cover
            audio_tag = MP4(str(audio))
            if lrc.exists():
                audio_tag.tags["©lyr"] = [lrc.read_text(encoding="utf-8")]
                written.append("©lyr")
            if cover_data:
                fmt = MP4Cover.FORMAT_PNG if cover_mime == "image/png" else MP4Cover.FORMAT_JPEG
                audio_tag.tags["covr"] = [MP4Cover(cover_data, imageformat=fmt)]
                written.append("covr")
            if genre_str:  audio_tag.tags["©gen"] = [genre_str]; written.append("©gen")
            if artist:     audio_tag.tags["©ART"] = [artist];    written.append("©ART")
            if album:      audio_tag.tags["©alb"] = [album];     written.append("©alb")
            if track_nr:
                nr = int(track_nr) if str(track_nr).isdigit() else 0
                audio_tag.tags["trkn"] = [(nr, 0)]; written.append("trkn")
            if title:      audio_tag.tags["©nam"] = [title];     written.append("©nam")
            audio_tag.save()

        else:
            return {"error": f"Format nicht unterstützt: {suffix}"}

        logging.info(f"embed_metadata OK: {audio.name} → {written}")
        return {
            "success":     True,
            "audio":       str(audio),
            "tags_written": written,
            "cover_used":  str(cover) if cover_data else None,
            "lrc_used":    str(lrc) if lrc.exists() else None,
        }

    except Exception as e:
        logging.error(f"embed_metadata Fehler {audio}: {e}")
        return {"error": str(e)}


def _parse_lrc(lrc_path: Path):
    entries = []
    pattern = re.compile(r"^\[(\d+):(\d+\.\d+)\](.*)")
    for line in lrc_path.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line.strip())
        if m:
            ms = int((int(m.group(1)) * 60 + float(m.group(2))) * 1000)
            text = m.group(3).strip()
            if text: entries.append((text, ms))
    return entries


# ════════════════════════════════════════════════════════════════
# TOOL 5: In Bibliothek verschieben
# ════════════════════════════════════════════════════════════════
@mcp.tool()
def move_to_library(
    audio_path: str,
    artist:     str,
    album:      str,
    track_nr:   str,
    title:      str,
    also_move:  list[str] = [],
) -> dict:
    """
    Verschiebt die Audio-Datei (und optional Begleitdateien) in die
    Musikbibliothek-Ordnerstruktur: library_root/Artist/Album/

    Die Datei wird umbenannt zu: "track_nr - title.extension"

    Args:
        audio_path: Absoluter Pfad zur Audio-Datei
        artist:     Künstlername (wird Ordnername)
        album:      Album-Name (wird Ordnername)
        track_nr:   Track-Nummer (z.B. "1")
        title:      Songtitel (wird Dateiname)
        also_move:  Liste weiterer Dateipfade die mitgenommen werden
                    (z.B. [".lrc", ".jpg"] — automatisch gleicher Stamm)
    """
    audio = Path(audio_path)
    if not audio.exists():
        return {"error": f"Datei nicht gefunden: {audio}"}

    # Zielordner erstellen
    safe_artist = re.sub(r'[<>:"/\\|?*]', "", artist).strip()
    safe_album  = re.sub(r'[<>:"/\\|?*]', "", album).strip()
    target_dir  = LIBRARY_ROOT / safe_artist / safe_album
    target_dir.mkdir(parents=True, exist_ok=True)

    # Dateiname: "01 - Titel.wav"
    nr_str    = str(track_nr).zfill(2)
    safe_title = re.sub(r'[<>:"/\\|?*]', "", title).strip()
    new_name   = f"{nr_str} - {safe_title}{audio.suffix}"
    target     = target_dir / new_name

    moved = []
    try:
        shutil.move(str(audio), str(target))
        moved.append({"from": str(audio), "to": str(target)})

        # Begleitdateien: LRC, Cover, JSON, TXT — alle mit gleichem Stem
        stem_clean = re.sub(r"_mastered.*$", "", audio.stem, flags=re.IGNORECASE)
        companion_exts = [".lrc", ".jpg", ".jpeg", ".png", ".json", ".txt", ".md"]
        companion_new_stem = f"{nr_str} - {safe_title}"

        for ext in companion_exts:
            for s in [audio.stem, stem_clean]:
                src = audio.parent / (s + ext)
                if src.exists():
                    dst = target_dir / (companion_new_stem + ext)
                    shutil.move(str(src), str(dst))
                    moved.append({"from": str(src), "to": str(dst)})
                    break  # Nur eine pro Endung

        logging.info(f"move_to_library OK: {audio.name} → {target}")
        return {
            "success":    True,
            "target_dir": str(target_dir),
            "audio_dest": str(target),
            "moved":      moved,
        }

    except Exception as e:
        logging.error(f"move_to_library Fehler: {e}")
        return {"error": str(e)}


# ════════════════════════════════════════════════════════════════
# TOOL 6: Library-CSV aktualisieren
# ════════════════════════════════════════════════════════════════
@mcp.tool()
def update_library_csv(
    artist:   str,
    album:    str,
    track_nr: str,
    titel:    str,
    datei:    str,
    ordner:   str,
    genre:    str,
    cover:    str = "✅",
    lyrics:   str = "✅ SYLT",
    status:   str = "fertig",
    notiz:    str = "",
) -> dict:
    """
    Fügt einen neuen Eintrag zur songs_assignment.csv hinzu
    oder aktualisiert einen bestehenden (Matching per Dateiname).

    Args:
        artist:   Künstlername
        album:    Album-Name
        track_nr: Track-Nummer
        titel:    Songtitel
        datei:    Dateiname (z.B. "01 - HAMBURGER DOM.wav")
        ordner:   Relativer Pfad in der Bibliothek (z.B. "Musikbibliothek/Tim Stuer/Jungs/")
        genre:    Komma-getrennte Genres (z.B. "German Rap, Hip Hop, Trap")
        cover:    Cover-Status (Standard: ✅)
        lyrics:   Lyrics-Status (Standard: ✅ SYLT)
        status:   Verarbeitungs-Status (Standard: fertig)
        notiz:    Optionale Notiz
    """
    FIELDNAMES = ["artist", "album", "track_nr", "titel", "datei",
                  "ordner", "genre", "cover", "lyrics", "tags_gesetzt", "status", "notiz"]

    new_row = {
        "artist":      artist,
        "album":       album,
        "track_nr":    track_nr,
        "titel":       titel,
        "datei":       datei,
        "ordner":      ordner,
        "genre":       genre,
        "cover":       cover,
        "lyrics":      lyrics,
        "tags_gesetzt": "✅",
        "status":      status,
        "notiz":       notiz,
    }

    try:
        rows = []
        updated = False

        if LIBRARY_CSV.exists():
            with open(LIBRARY_CSV, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("datei", "").strip() == datei.strip():
                        rows.append(new_row)
                        updated = True
                    else:
                        rows.append(row)

        if not updated:
            rows.append(new_row)

        LIBRARY_CSV.parent.mkdir(parents=True, exist_ok=True)
        with open(LIBRARY_CSV, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        logging.info(f"update_library_csv: {'aktualisiert' if updated else 'hinzugefügt'}: {datei}")
        return {
            "success": True,
            "action":  "updated" if updated else "added",
            "entry":   new_row,
            "csv":     str(LIBRARY_CSV),
        }

    except Exception as e:
        logging.error(f"update_library_csv Fehler: {e}")
        return {"error": str(e)}


# ════════════════════════════════════════════════════════════════
# TOOL 7: Library-Status abfragen
# ════════════════════════════════════════════════════════════════
@mcp.tool()
def get_library_status() -> dict:
    """
    Gibt einen Überblick über die aktuelle Musikbibliothek:
    Anzahl Songs, Künstler, Alben und Songs die noch ausstehen.
    """
    if not LIBRARY_CSV.exists():
        return {"error": f"Library-CSV nicht gefunden: {LIBRARY_CSV}"}

    try:
        rows = []
        with open(LIBRARY_CSV, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))

        artists = sorted(set(r.get("artist", "") for r in rows if r.get("artist")))
        albums  = sorted(set(f"{r.get('artist')} – {r.get('album')}"
                             for r in rows if r.get("artist") and r.get("album")))
        pending = [r for r in rows if r.get("status", "").strip() != "fertig"]

        return {
            "total_songs": len(rows),
            "artists":     artists,
            "albums":      albums,
            "pending":     [{"titel": r.get("titel"), "artist": r.get("artist"),
                             "status": r.get("status")} for r in pending],
            "csv_path":    str(LIBRARY_CSV),
        }

    except Exception as e:
        logging.error(f"get_library_status Fehler: {e}")
        return {"error": str(e)}


# ── Entry Point ───────────────────────────────────────────────────
if __name__ == "__main__":
    logging.info("Music-MCP Server gestartet")
    mcp.run(transport="stdio")
