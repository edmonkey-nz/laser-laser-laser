# Installing

Setup for each platform, plus the command-line reference. Once you're
running, see [MANUAL.md](MANUAL.md) for what all the controls do.

## Prebuilt executables

Don't want to set up Python? Grab a zip from the
[Releases page](https://github.com/edmonkey-nz/laser-laser-laser/releases) —
one each for Ubuntu, Windows and macOS (Apple Silicon), built automatically
by GitHub Actions (`.github/workflows/build.yml`) whenever a version tag is
pushed. Unzip and run the `laser-laser-laser` executable inside — the
folder contains everything needed (Python runtime, the Helios library,
starter patterns), no install step.

A few things to know:
- **Unsigned binaries**: none of these are code-signed, so Windows
  SmartScreen and macOS Gatekeeper will both flag them on first run.
  Windows: "More info" → "Run anyway". macOS: right-click the executable
  → "Open" (or `xattr -d com.apple.quarantine laser-laser-laser` in
  Terminal) — plain double-clicking a Gatekeeper-blocked file just fails
  silently otherwise.
- **Linux needs `libusb-1.0-0` installed** (`sudo apt install
  libusb-1.0-0` if it isn't already — most desktops have it). The Ubuntu
  udev rule (`heliosdac.rules`) is included in the zip; see *Ubuntu
  setup* below for how to install it.
- **macOS build is Apple Silicon (arm64) only.** Older Intel Macs aren't
  covered by the current workflow.
- These are the same source files as this repo at that tag — nothing
  extra is bundled beyond the Python runtime and dependencies (including
  the optional OpenCV vectoriser, so that panel works out of the box).

Maintainers: cutting a release is just `git tag vX.Y.Z && git push origin
vX.Y.Z` — the workflow builds all three platforms and attaches them to a
new GitHub Release automatically. `workflow_dispatch` (the "Run workflow"
button in the Actions tab) builds without publishing, handy for testing
the pipeline itself.

## Ubuntu setup

Recent Ubuntu (23.04+) protects the system Python (PEP 668), so `pip
install` into it fails with an `externally-managed-environment` error.
Create a virtual environment in the project folder first, then install
into that:

```bash
sudo apt install libusb-1.0-0 python3-venv python3-full

cd laser-laser-laser          # the project folder
python3 -m venv .venv
source .venv/bin/activate      # activate it (prompt shows (.venv))

pip install numpy mido python-rtmidi sounddevice pygame aiohttp
pip install opencv-python-headless   # optional: image/webcam vectoriser
```

If a source build of `python-rtmidi` or `sounddevice` complains about
missing headers, also install the build tools:

```bash
sudo apt install build-essential python3-dev libasound2-dev libportaudio2
```

Once the venv exists you don't have to activate it every time —
`.venv/bin/python laserx3.py --web` runs it directly, which is handy for
a launcher script.

```bash
# USB permissions (once):
sudo cp scripts/heliosdac.rules /etc/udev/rules.d/011_heliosdac.rules
sudo udevadm control --reload
sudo usermod -aG plugdev $USER   # then log out/in
```

Replug the DAC after installing the rule.

### Rebuilding libHeliosDacAPI.so (if the prebuilt one doesn't load)

```bash
sudo apt install libusb-1.0-0-dev g++
git clone https://github.com/Grix/helios_dac.git
cd helios_dac/sdk/cpp/shared_library
g++ -O2 -fPIC -shared -std=c++14 -o libHeliosDacAPI.so \
    HeliosDacAPI.cpp ../HeliosDac.cpp \
    ../idn/idn.cpp ../idn/idnServerList.cpp ../idn/plt-posix.cpp \
    $(pkg-config --cflags --libs libusb-1.0) -I.. -lpthread
cp libHeliosDacAPI.so /path/to/laserx3/
```

(Bonus: this build includes the SDK's IDN network-DAC support, so the
same wrapper will drive an OpenIDN adapter later if you ever want one.)

## Windows

Drop `HeliosLaserDAC.dll` and `libusb-1.0.dll` from the SDK repo
(`sdk/cpp/shared_library` and `sdk/cpp/libusb_bin`) next to the scripts.
`helios.py` picks the DLL automatically on Windows.

## macOS

Yes, it runs on macOS. The whole app is portable Python; the only
platform-specific pieces (the DAC library name and webcam access) are
handled automatically. You need a macOS build of the Helios library:

```bash
brew install libusb python@3.12
git clone https://github.com/Grix/helios_dac.git
cd helios_dac/sdk/cpp/shared_library
clang++ -O2 -fPIC -dynamiclib -std=c++14 -o libHeliosDacAPI.dylib \
    HeliosDacAPI.cpp ../HeliosDac.cpp \
    ../idn/idn.cpp ../idn/idnServerList.cpp ../idn/plt-posix.cpp \
    $(pkg-config --cflags --libs libusb-1.0) -I.. 
cp libHeliosDacAPI.dylib /path/to/laserx3/
```

`helios.py` looks for `libHeliosDacAPI.dylib` on macOS automatically. No
udev rules are needed (that's a Linux thing); the DAC just works over USB.
For the webcam vectoriser, the camera dropdown lists indices `camera 0…5`
(macOS has no stable device-name list), and the first launch prompts for
camera permission. Everything else — browser UI, MIDI, ILDA, audio — is
identical to Linux.

## Running

```bash
python3 laserx3.py                       # pygame preview + browser UI (both on by default)
python3 laserx3.py --laser               # Helios DAC + browser UI
python3 laserx3.py --laser --preview     # laser + pygame mirror + browser UI
python3 laserx3.py --list-midi           # find your controller
python3 laserx3.py --laser --midi "MPK"  # match MIDI port by substring
```

**Output starts disarmed.** Whatever you launch with, nothing is emitted
until you press ARM in the header, and the brightness ceiling starts at
5%. See [SAFETY.md](SAFETY.md).

**You never need to pass `--web`.** The browser control surface is always
on — including in the prebuilt executables — so
`http://localhost:8080/` works after any launch. `--no-web` turns it off
if you really want to; `--web-port N` moves it.

A bare launch also opens the pygame preview window, so double-clicking an
executable gets you a visible window as well as browser control. Passing
`--laser` or `--preview` explicitly takes over that choice, and modes
combine freely (`--laser --preview` is fine).

Options: `--points N` (default 800) and `--pps N` (default 30000).
Frame rate ≈ pps/points, so 800 pts @ 30 kpps ≈ 37 fps. Fewer points =
faster/smoother motion but coarser curves; the Helios tops out at 65 kpps
if your scanners can take it.

### Choosing an output device

```bash
python3 laserx3.py --output none         # no laser (default)
python3 laserx3.py --output helios       # Helios DAC over USB; --laser is an alias
python3 laserx3.py --output lasercube    # LaserCube over the network
```

You can also switch device live in **Settings → Laser output**, without
restarting, and the choice is remembered. A remembered choice that fails
to open falls back to no output with a message; an explicit `--output` on
the command line that fails is fatal, because starting silently with no
output would let you believe a laser is connected when it isn't.

`--max-brightness F` sets the hard output ceiling (0..1, default 0.05).
It persists, so you normally set it once in Settings rather than per run.

### LaserCube over the network

Use the **Ethernet** adapter, not WiFi — buffer levels are unstable over
WiFi and the app warns if it finds itself on it.

```bash
python3 laserx3.py --list-lasercubes      # discover units and print status
python3 laserx3.py --output lasercube --lasercube-ip 192.168.1.50
python3 laserx3.py --output lasercube --lasercube-dry-run
```

`--lasercube-ip` skips broadcast discovery. `--lasercube-dry-run` does all
the packing and rate control but transmits nothing, so you can validate
throughput and the watchdog with zero photons.
`--lasercube-point-order rgbxy` swaps the wire field order — only needed
if the hardware disagrees with the protocol spec, which is the first
thing to try if the first frame comes out as garbage.

No extra dependencies: the LaserCube path is pure Python (`socket` +
`struct`), so there's no shared library to build or install for it.

**Testing without hardware.** `scripts/lasercube_sim.py` is a fake
LaserCube that answers on the real ports:

```bash
python3 scripts/lasercube_sim.py                  # behave
python3 scripts/lasercube_sim.py --stall-after 5  # go silent, to trip the watchdog
python3 scripts/lasercube_sim.py --temperature 45 # report over-temperature
python3 scripts/lasercube_sim.py --refuse-enable  # decline to enable output
```

then in another terminal:

```bash
python3 laserx3.py --output lasercube --lasercube-ip 127.0.0.1
```

