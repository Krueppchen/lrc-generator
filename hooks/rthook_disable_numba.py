# Runtime Hook: Numba JIT deaktivieren
# Numba versucht im PyInstaller-Bundle llvmlite zu laden und crasht dabei.
# NUMBA_DISABLE_JIT=1 schaltet JIT ab — stable-ts/whisper läuft trotzdem normal.
import os
os.environ["NUMBA_DISABLE_JIT"] = "1"
os.environ["NUMBA_CACHE_DIR"] = os.path.join(os.path.expanduser("~"), ".cache", "numba")
