# 🎵 LRC Generator

> Automatically generate timestamped `.lrc` lyric files for your [Suno AI](https://suno.com) songs — no manual editing, no Terminal required.

[![Build & Release](https://github.com/Krueppchen/lrc-generator/actions/workflows/build-release.yml/badge.svg)](https://github.com/Krueppchen/lrc-generator/actions/workflows/build-release.yml)
[![macOS](https://img.shields.io/badge/macOS-12%2B-blue?logo=apple)](https://github.com/Krueppchen/lrc-generator/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ⬇️ Download

**Just want to use the app? Download the latest release:**

👉 **[Download LRC-Generator-macOS.dmg](https://github.com/Krueppchen/lrc-generator/releases/latest)**

Open the DMG, drag the app to Applications, done. No Python, no Terminal needed.

> **First launch:** Right-click the app → "Open" (required once because the app is not from the App Store)
>
> **First run:** The app downloads the Whisper AI model (~140 MB) automatically in the background.

---

## ✨ What It Does

Drop your Suno audio and lyrics files in the same folder. The app uses OpenAI Whisper to precisely align each lyric line to the audio — not by transcribing, but by *forcing* the known lyrics onto the audio timeline. The result is a perfect `.lrc` file ready for Apple Music, karaoke apps, or any media player.

**Features:**

- Automatic forced alignment via [stable-ts](https://github.com/jianfch/stable-ts) (Whisper-based)
- Generates standard `.lrc` files — compatible with Apple Music, VLC, MusicBee, foobar2000, karaoke apps
- Writes synced lyrics into audio metadata (SYLT for MP3/WAV/AIFF · SYNCEDLYRICS for FLAC/OGG/Opus)
- Supports all common formats: `.wav` `.mp3` `.flac` `.m4a` `.aac` `.ogg` `.opus` `.aiff`
- Handles both Suno export formats: plain `.txt` and structured `.md` song documents
- Smart filename matching — handles track numbers, umlauts (ä→ae), `_mastered` suffixes, bracket variants
- Song selection UI with checkboxes and colored format badges
- Live progress for Whisper model download and per-song processing

---

## 📁 How It Works

Place your audio and lyrics files **in the same folder**:

```
My Songs/
├── 01 - Kohle an_mastered.wav    ← audio
├── 01 - Kohle an.txt             ← lyrics (matched automatically)
├── 02 - Hamburg.flac
├── 02 - Hamburg.md
└── ...
```

The app matches files using a three-stage strategy: exact name → strip suffixes like `_mastered` → fuzzy slug match (handles umlauts, track numbers, punctuation). Then click **LRC generieren** and you're done.

**Supported lyrics formats:**

Plain `.txt` (Suno direct export):
```
Prompt: ...
[Verse 1]
Line one
Line two

[Chorus]
...
```

Structured `.md` (song document with `## Streaming Lyrics` section):
```markdown
# Song Title

## Streaming Lyrics
\`\`\`
[Verse 1]
Line one
\`\`\`
```

The app strips all Suno metadata (style tags, genre, BPM descriptions) and only aligns the actual lyric lines.

---

## 🖥 Usage

1. Launch `LRC Generator.app`
2. Click **"Ordner wählen"** and select the folder with your songs
3. The app shows all songs with a matching lyrics file — check/uncheck as needed
4. Click **"LRC generieren"**
5. `.lrc` files appear next to each audio file; metadata is updated automatically

---

## ⚙️ Technical Details

| Component | Detail |
|-----------|--------|
| AI Model | Whisper `base` (multilingual, ~140 MB, cached at `~/.cache/whisper/`) |
| Alignment | stable-ts forced alignment (not transcription) |
| LRC format | `[mm:ss.cc]text` per segment |
| MP3/WAV/AIFF metadata | SYLT ID3 tag via mutagen |
| FLAC/OGG/Opus metadata | SYNCEDLYRICS Vorbis comment via mutagen |
| GUI framework | CustomTkinter (dark mode) |
| Distribution | Standalone `.app` via PyInstaller — no Python required |

---

## 🐛 Troubleshooting

**App doesn't open (icon bounces, no window)**

Check the log:
```bash
cat ~/Library/Logs/LRCGenerator.log
```
Or run the diagnostic script (developer mode only):
```bash
bash diagnose.sh
```

**Songs not showing up in the list**

The song needs a matching lyrics file (`.txt` or `.md`) in the same folder. The fuzzy matcher handles umlauts, `_mastered` suffixes, and track numbers — check that the base name roughly matches.

**SSL error on first Whisper download**

This only happens with Python.org installations (not relevant for the standalone app):
```bash
open /Applications/Python*/Install\ Certificates.command
```

---

## 🛠 Build From Source

If you want to run or build the app yourself:

```bash
# 1. Install Python with Tkinter support
brew install python-tk

# 2. Clone and install dependencies
git clone https://github.com/Krueppchen/lrc-generator.git
cd lrc-generator
pip3 install -r requirements.txt --break-system-packages

# 3a. Run directly
python3 lrc_generator_app.py

# 3b. Or build a standalone .app + .dmg
bash build_dmg.sh
```

The `build_dmg.sh` script installs PyInstaller, builds the `.app` bundle, and wraps it in a distributable `.dmg`. Takes 3–8 minutes on first run.

---

## 🚀 Releasing a New Version

Releases are built automatically via GitHub Actions. To publish a new version:

```bash
git tag v1.2.0
git push origin v1.2.0
```

GitHub Actions will build the macOS `.app`, package it as a `.dmg`, and attach it to a new GitHub Release automatically.

---

## 🤝 Contributing

Pull requests welcome! Ideas for future improvements:

- [ ] Drag & drop folder support
- [ ] Whisper model selector (tiny / base / small / medium)
- [ ] LRC preview before saving
- [ ] Batch export to ZIP
- [ ] Windows support

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built with [stable-ts](https://github.com/jianfch/stable-ts) · [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) · [mutagen](https://mutagen.readthedocs.io/) · [OpenAI Whisper](https://github.com/openai/whisper)*
