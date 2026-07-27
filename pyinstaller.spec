# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Laser! Laser Laser! — builds a --onedir bundle (a
folder, not a single exe) so patterns.json / settings.json / ilda/ stay
real, writable files next to the app, exactly like running from source.
See the README's "Building executables" section for the full story.

Used both by .github/workflows/build.yml (one job per OS) and for a
local build:  pyinstaller pyinstaller.spec

Expects the platform Helios shared library staged in helios_lib/ before
running (see build.yml for exactly what goes there per OS). On Linux the
repo's own libHeliosDacAPI.so is used directly — no staging needed.
"""
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
