# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller Spec — LRC Generator (macOS)
#
# Dieses Spec-Datei bündelt die App inklusive aller Abhängigkeiten
# zu einer standalone .app ohne externe Python-Installation.
#
# Bekannte große Pakete im Bundle:
#   - PyTorch (via stable-ts/whisper): ~400–700 MB
#   - Whisper-Modell: wird beim ersten Start heruntergeladen (~140 MB)
#   - CustomTkinter + Tkinter-Framework
#   - mutagen (Audiometadaten)
#
# Aufruf: python3 -m PyInstaller lrc_generator.spec

from PyInstaller.utils.hooks import collect_data_files, collect_all
import sys

APP_NAME = "LRC Generator"
MAIN_SCRIPT = "lrc_generator_app.py"

# ── Daten-Assets sammeln ─────────────────────────────────────────
datas = []

# CustomTkinter: Themes, Icons, Assets (zwingend erforderlich)
datas += collect_data_files("customtkinter")

# stable_whisper: interne Daten falls vorhanden
try:
    datas += collect_data_files("stable_whisper")
except Exception:
    pass

# whisper: tokenizer, mel_filters.npz, assets (mehrsprachige Unterstützung)
try:
    datas += collect_data_files("whisper")
except Exception:
    pass

# tiktoken: für Whisper-Tokenisierung
try:
    datas += collect_data_files("tiktoken")
    datas += collect_data_files("tiktoken_ext")
except Exception:
    pass

# ── Hidden Imports ────────────────────────────────────────────────
# Dynamische Importe die PyInstaller nicht automatisch erkennt
hiddenimports = [
    # mutagen: wird dynamisch für das jeweilige Audioformat geladen
    "mutagen",
    "mutagen.mp3",
    "mutagen.mp4",
    "mutagen.flac",
    "mutagen.oggvorbis",
    "mutagen.oggopus",
    "mutagen.wave",
    "mutagen.aiff",
    "mutagen.id3",
    "mutagen._vorbis",
    "mutagen._tags",
    "mutagen.id3._tags",
    "mutagen.id3._frames",
    "mutagen.id3._specs",
    # torch: Backends
    "torch",
    "torch.nn",
    "torch.nn.functional",
    # tqdm: Fortschrittsbalken für Whisper-Download
    "tqdm",
    "tqdm.auto",
    # numba (optionale torch-Abhängigkeit)
    "numba",
    # tiktoken (Whisper-Tokenizer)
    "tiktoken",
    "tiktoken.core",
    "tiktoken_ext.openai_public",
    # audio backends
    "soundfile",
    "scipy",
    "scipy.signal",
    "scipy.io",
    "scipy.io.wavfile",
    # stable_whisper internals
    "stable_whisper",
    "stable_whisper.audio",
    "stable_whisper.result",
    "stable_whisper.text_output",
    # packaging (wird von vielen Libs benutzt)
    "packaging",
    "packaging.version",
    # tkinter (macOS Tk-Framework)
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "_tkinter",
]

# ── Excludes: Unnötige Pakete rausschmeißen ───────────────────────
excludes = [
    # Test-Frameworks
    "pytest",
    "unittest",
    # Jupyter / IPython
    "IPython",
    "jupyter",
    "notebook",
    # Matplotlib (nicht benötigt)
    "matplotlib",
    # OpenCV (nicht benötigt)
    "cv2",
    # Qt-Varianten (wir nutzen Tkinter)
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    # Sphinx / Docs
    "sphinx",
    "docutils",
]

# ── Analyse ───────────────────────────────────────────────────────
a = Analysis(
    [MAIN_SCRIPT],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)

# ── PYZ-Archiv ───────────────────────────────────────────────────
pyz = PYZ(a.pure)

# ── EXE (macOS: innerhalb der .app) ──────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # Kein Konsolenfenster
    disable_windowed_traceback=False,
    argv_emulation=True,    # macOS: File-Drop auf Dock-Icon
    target_arch=None,       # Auto-detect (arm64 oder x86_64)
    codesign_identity=None,
    entitlements_file=None,
)

# ── COLLECT: Alle Dateien zusammenführen ─────────────────────────
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

# ── BUNDLE: macOS .app erstellen ─────────────────────────────────
app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=None,              # Optional: 'icon.icns' hier eintragen
    bundle_identifier="de.timstuerenburg.lrcgenerator",
    version="1.1.0",
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": "1.1.0",
        "CFBundleVersion": "1.1.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,  # Dark Mode erlaubt
        # Mikrofon/Audio nicht benötigt, aber Datei-Zugriff:
        "NSAppleEventsUsageDescription": "Für den Ordnerzugriff benötigt",
        # Damit macOS keine Sandbox-Probleme macht:
        "LSMinimumSystemVersion": "12.0",
        "LSUIElement": False,
    },
)
