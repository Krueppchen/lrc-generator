# Runtime Hook: ffmpeg aus dem Bundle-Verzeichnis auffindbar machen
#
# stable-ts ruft ffmpeg als subprocess auf. Im PyInstaller-Bundle
# ist ffmpeg neben der App-Binary — wir setzen PATH entsprechend.

import os
import sys

if getattr(sys, "frozen", False):
    # Wir laufen im PyInstaller-Bundle
    bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    os.environ["PATH"] = bundle_dir + os.pathsep + os.environ.get("PATH", "")
