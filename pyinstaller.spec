# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Laser! Laser Laser! — builds a --onedir bundle (a
folder, not a single exe) so patterns.json / settings.json / ilda/ stay
real, writable files you can hand-edit, exactly like running from source.
See docs/INSTALL.md for the full story.

Note: since PyInstaller 6 those files live in the bundle's `_internal/`
subfolder rather than beside the executable (COLLECT's contents_directory
default changed). The app finds them either way — every module resolves
data relative to its own __file__ — but a user hand-editing patterns.json
has to look in `_internal/`.

Used both by .github/workflows/build.yml (one job per OS) and for a
local build:  pyinstaller pyinstaller.spec

Expects the platform Helios shared library staged in helios_lib/ before
running (see build.yml for exactly what goes there per OS). On Linux the
repo's own libHeliosDacAPI.so is used directly — no staging needed.
"""
import os
import shutil
import sys

datas = [
    ("static", "static"),
    ("about.md", "."),
    ("patterns.json", "."),
    ("ilda/spinning_star.ild", "ilda"),
]
if sys.platform == "win32":
    datas += [("helios_lib/HeliosLaserDAC.dll", "."),
              ("helios_lib/libusb-1.0.dll", ".")]
elif sys.platform == "darwin":
    datas += [("helios_lib/libHeliosDacAPI.dylib", "."),
              ("helios_lib/libusb-1.0.0.dylib", ".")]
else:
    datas += [("libHeliosDacAPI.so", ".")]

a = Analysis(
    ["laserx3.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    # mido picks its backend with a dynamic importlib.import_module() call,
    # which PyInstaller's static analysis can't trace on its own.
    hiddenimports=["mido.backends.rtmidi"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="laser-laser-laser",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="laser-laser-laser",
)

# README.txt goes at the TOP level of every zip, beside the executable, so
# it is the first thing a user sees: one per OS, from docs/release/.
_readme = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
shutil.copy(f"docs/release/README-{_readme}.txt",
            os.path.join(DISTPATH, "laser-laser-laser", "README.txt"))

# The Linux udev rule and its installer have to sit at the TOP level of the
# unzipped folder, not in _internal/ where `datas` would put them — a user
# is told to run `./install-udev.sh` from the folder they just unzipped (the
# app's own error message names that path), and the script expects the rule
# beside it. shutil.copy keeps the script's executable bit. Done here rather
# than as a CI step so a local `pyinstaller pyinstaller.spec` produces the
# same folder.
if sys.platform not in ("win32", "darwin"):
    for f in ("scripts/heliosdac.rules", "scripts/install-udev.sh"):
        shutil.copy(f, os.path.join(DISTPATH, "laser-laser-laser"))
