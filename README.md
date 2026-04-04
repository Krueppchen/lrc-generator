# 🎵 LRC Generator + Music Library MCP

> Automatically generate timestamped `.lrc` lyric files and manage your Suno AI music library — fully automated via Claude Cowork, or standalone without any setup.

[![Build & Release](https://github.com/Krueppchen/lrc-generator/actions/workflows/build-release.yml/badge.svg)](https://github.com/Krueppchen/lrc-generator/actions/workflows/build-release.yml)
[![macOS](https://img.shields.io/badge/macOS-12%2B-blue?logo=apple)](https://github.com/Krueppchen/lrc-generator/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Two Ways to Use This

| | Standalone App | Claude Cowork + MCP |
|---|---|---|
| **Who it's for** | Anyone, no setup needed | Power users with Claude Desktop |
| **What it does** | LRC generation + metadata in a GUI | Full pipeline: scan → LRC → metadata → library → CSV |
| **Requires Python** | ❌ No | ✅ Yes (one-time setup) |
| **Genre detection** | Manual | AI-powered (Claude reads Suno JSON) |
| **Library management** | ❌ | ✅ Auto-organizes + updates CSV database |

---

## ⬇️ Download the Standalone App

**No Python, no Terminal — just open and use:**

👉 **[Download LRC-Generator-macOS.dmg](https://github.com/Krueppchen/lrc-generator/releases/latest)**

Open the DMG, drag to Applications, done.

> **First launch:** Right-click → "Open" (required once — app is not from the App Store)
>
> **First run:** Whisper AI model downloads automatically (~140–500 MB depending on model)

---

## 🤖 Automated Workflow with Claude Cowork + MCP

This is the full power-user setup. Claude becomes your music librarian — it reads the Suno JSON metadata, decides on genres intelligently, generates LRC files via Whisper, embeds everything into the audio files, moves them into your library folder structure, and updates your CSV database. All from a single chat message.

### How the Pipeline Works

```
Suno.com
   │
   ▼  [SunoMaster Plugin — bulk export]
~/Downloads/Suno Downloads/AlbumName/
   ├── Song Title.wav (mastered)
   ├── Song Title.json  ← Suno metadata, tags, BPM, mood
   ├── Song Title.jpeg  ← cover art
   └── Song Title.txt   ← lyrics
   │
   ▼  [Claude Cowork — "Process my new songs in Chill/"]
   │
   ├─ scan_folder()        → what's new?
   ├─ read_song_json()     → Claude interprets genres from Suno tags
   ├─ generate_lrc()       → Whisper forced alignment → .lrc
   ├─ embed_metadata()     → LRC + cover + genres + title into audio
   ├─ move_to_library()    → ~/Music/Musikbibliothek/Artist/Album/01 - Title.wav
   └─ update_library_csv() → songs_assignment.csv updated
```

### Step 1 — Export from Suno with SunoMaster

[SunoMaster](https://sunomaster.app) is a browser plugin that lets you bulk-download your Suno songs. Install it, open your Suno library, select songs, and export. Each song downloads with four files:

```
Song Title_mastered.wav   ← high-quality audio
Song Title.json           ← full Suno metadata (tags, BPM, mood, model)
Song Title.jpeg           ← cover image
Song Title.txt            ← lyrics text
```

Put them all in a subfolder under `~/Downloads/Suno Downloads/`, e.g.:

```
~/Downloads/Suno Downloads/
└── Chill/
    ├── Morning Drift_mastered.wav
    ├── Morning Drift.json
    ├── Morning Drift.jpeg
    └── Morning Drift.txt
```

### Step 2 — Set Up the MCP Server (one-time)

**Prerequisites:**
- [Claude Desktop](https://claude.ai/download) installed
- Python 3.11+ with Homebrew (`brew install python-tk@3.11`)

**Install dependencies:**

```bash
pip3 install mcp fastmcp mutagen stable-whisper --break-system-packages
```

**Clone the MCP server files:**

```bash
mkdir -p ~/Documents/Music-MCP
# Copy mcp_server.py and mcp_config.json from this repo's Music-MCP/ folder
```

**Configure paths** in `~/Documents/Music-MCP/mcp_config.json`:

```json
{
  "suno_downloads": "~/Downloads/Suno Downloads",
  "library_csv":    "~/Downloads/Music/songs_assignment.csv",
  "library_root":   "~/Music/Musikbibliothek",
  "whisper_model":  "medium",
  "language":       "en",
  "max_genres":     4
}
```

**Register with Claude Desktop:**

```bash
code ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

Add this (replace the `python3` path with your actual path from `which python3`):

```json
{
  "mcpServers": {
    "music-library": {
      "command": "/opt/homebrew/bin/python3",
      "args": ["/Users/YOUR_USERNAME/Documents/Music-MCP/mcp_server.py"]
    }
  }
}
```

Restart Claude Desktop. The `music-library` MCP tools are now available.

### Step 3 — Tell Claude to Process Your Songs

Open Claude Cowork and just ask:

> *"I have new songs in my Suno Downloads/Chill folder. Process them all and add them to the library. Suggest a good artist and album name based on the style."*

Claude will scan the folder, read the Suno JSON for each song, intelligently determine genres from the style tags, run Whisper for each song, embed everything, move the files, and update the CSV — all automatically.

**Example prompts:**

```
"What's the status of my music library?"

"Process all new songs in Suno Downloads/Rock —
 add them to Suno // Rock / Rock & Alternative"

"I have 5 new chill songs in Downloads/Ambient.
 Suggest a good album name and process them."
```

---

## 🖥 Standalone App Usage

For users who want to generate LRC files and embed metadata without Claude — just the GUI app.

**Supported formats:** `.wav` `.mp3` `.flac` `.m4a` `.aac` `.ogg` `.opus` `.aiff`

1. Launch `LRC Generator.app`
2. Click **"Ordner wählen"** — select the folder with your songs
3. Optionally select a **music library CSV** for automatic metadata lookup
4. Check the options you want:
   - ✅ **LRC generieren** — create timestamped lyric files
   - ✅ **Cover einbetten** — embed cover art from matching `.jpg`/`.jpeg` files
   - ✅ **Genres aus JSON** — read genres from Suno `.json` files
   - ✅ **Bibliotheks-Metadaten** — pull artist/album/track from your CSV
5. Select a **Whisper model** (base = fast, medium = accurate, large = slow but best)
6. Select **language** (de / en / auto)
7. Click **"LRC generieren"**

**File matching:** The app auto-matches audio to lyrics using a three-stage strategy: exact filename → strip `_mastered` suffix → fuzzy slug match (handles umlauts, track numbers, punctuation).

**Output:** `.lrc` files appear next to each audio file; all selected metadata is written directly into the audio file.

---

## 📁 File Structure

The app and MCP server expect (and produce) this layout:

```
~/Downloads/Suno Downloads/        ← staging area (SunoMaster exports here)
└── AlbumName/
    ├── Song Title_mastered.wav
    ├── Song Title.json
    ├── Song Title.jpeg
    └── Song Title.txt

~/Music/Musikbibliothek/           ← final library (configurable)
└── Artist Name/
    └── Album Name/
        ├── 01 - Song Title.wav
        ├── 01 - Song Title.lrc
        ├── 01 - Song Title.jpeg
        ├── 01 - Song Title.json
        └── 01 - Song Title.txt

~/Downloads/Music/
└── songs_assignment.csv           ← library database (configurable)
```

---

## 🔧 MCP Server Tools Reference

The `music-library` MCP server exposes 7 tools to Claude:

| Tool | What it does |
|------|-------------|
| `scan_folder(subfolder)` | Lists all songs in a Suno Downloads subfolder with status flags (has lyrics, has JSON, has cover, LRC done) |
| `read_song_json(song, subfolder)` | Returns the full Suno JSON for a song — Claude interprets genre tags, BPM, mood, etc. |
| `generate_lrc(audio, lyrics, model, language)` | Runs Whisper forced alignment to generate a precise `.lrc` file |
| `embed_metadata(audio, title, artist, album, track_nr, genres, lrc, cover)` | Writes all tags into the audio file — synced lyrics, cover art, genres, track info |
| `move_to_library(audio, artist, album, track_nr, title)` | Moves audio + all companion files into `library_root/Artist/Album/NN - Title.ext` |
| `update_library_csv(...)` | Adds or updates the song in the CSV database |
| `get_library_status()` | Returns total count, artists, albums, and any pending songs |

**Supported audio formats for metadata:** WAV · MP3 · FLAC · OGG · Opus · M4A · AAC · AIFF

**Synced lyrics tag format by format:**
- WAV / MP3 / AIFF → ID3 `SYLT` (millisecond precision) + `USLT` (unsynchronized fallback)
- FLAC → Vorbis `SYNCEDLYRICS`
- OGG / Opus → Vorbis `SYNCEDLYRICS`
- M4A / AAC → iTunes `©lyr`

---

## ⚙️ Technical Details

| Component | Detail |
|-----------|--------|
| AI Alignment | stable-ts Whisper forced alignment (not transcription) |
| LRC format | `[mm:ss.cc]text` per segment |
| Whisper models | tiny (~75MB) / base (~140MB) / small (~460MB) / medium (~1.5GB) / large (~3GB) |
| GUI framework | CustomTkinter (dark mode, macOS native feel) |
| Metadata library | mutagen — handles all formats natively |
| Distribution | Standalone `.app` via PyInstaller — no Python required for app users |
| MCP framework | FastMCP (Python) via stdio transport |

---

## 🛠 Build the App From Source

```bash
# 1. Install Python with Tkinter support
brew install python-tk@3.11

# 2. Clone and install dependencies
git clone https://github.com/Krueppchen/lrc-generator.git
cd lrc-generator
pip3 install -r requirements.txt --break-system-packages

# 3a. Run directly
python3 lrc_generator_app.py

# 3b. Build standalone .app + .dmg
bash build_dmg.sh
```

The build script creates an isolated virtualenv, runs PyInstaller, bundles ffmpeg, and packages everything into a distributable `.dmg`. Takes 5–10 minutes on first run.

---

## 🚀 Releasing a New Version

Releases are built automatically via GitHub Actions on tag push:

```bash
git tag v1.2.0
git push origin v1.2.0
```

GitHub Actions builds the macOS `.app`, wraps it in a `.dmg`, and attaches it to a new GitHub Release automatically.

---

## 🐛 Troubleshooting

**App doesn't open (bounces, no window)**
```bash
cat ~/Library/Logs/LRCGenerator.log
```

**MCP server not showing in Claude**
```bash
# Test if it starts cleanly:
/opt/homebrew/bin/python3 ~/Documents/Music-MCP/mcp_server.py
# Should run silently. Any error = missing dependency.

# Check MCP log:
cat ~/Library/Logs/MusicMCP.log
```

**`npx` or `python3` not found in Claude Desktop**
Claude Desktop starts without the shell PATH. Always use full paths in `claude_desktop_config.json`:
```bash
which python3   # → e.g. /opt/homebrew/bin/python3
which npx       # → e.g. /Users/you/.nvm/versions/node/v22.18.0/bin/npx
```

**Songs not showing up in the app**
The song needs a matching lyrics file (`.txt` or `.md`) in the same folder. The fuzzy matcher handles umlauts, `_mastered` suffixes, and track numbers automatically.

**LRC generation times out in Claude**
Whisper takes 30–120 seconds per song. The MCP tool may hit a 60s timeout — the process continues in the background. Re-scan the folder to confirm the `.lrc` was created, then continue with `embed_metadata`.

---

## 🤝 Contributing

Pull requests welcome!

- [x] Whisper model selector (tiny / base / small / medium / large)
- [x] Language selector (de / en / auto)
- [x] Cover art embedding from matching image files
- [x] Genre extraction from Suno JSON
- [x] Music library CSV integration
- [x] Claude Cowork MCP server
- [ ] Drag & drop folder support in GUI
- [ ] LRC preview before saving
- [ ] Batch export to ZIP
- [ ] Windows support

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built with [stable-ts](https://github.com/jianfch/stable-ts) · [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) · [mutagen](https://mutagen.readthedocs.io/) · [OpenAI Whisper](https://github.com/openai/whisper) · [FastMCP](https://github.com/jlowin/fastmcp)*
