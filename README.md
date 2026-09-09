# Laser! Laser Laser!

![version](https://img.shields.io/badge/version-1.8.2-blueviolet)
![license](https://img.shields.io/badge/license-MIT-green)
![platform](https://img.shields.io/badge/platform-Ubuntu%20%7C%20Windows%20%7C%20macOS-informational)
![ai-code](https://img.shields.io/badge/AI%20coded-YES-orange)

Realtime vector visuals synthesizer for the Helios Laser DAC and the
LaserCube over the network. 
- Lissajous figures, rose curves, hypotrochoids, waveforms, harmonographs,polygons/stars
- Text input
- Draw polygons directly and save as patterns
- Advanced 'duplicator' functionailty 
- Live audio scope (with various forms)
- Random pattern generator
- Play ILDA files
- Vectorise raster images + live webcam video > laser paths
- Custom PPS settings per pattern
- Masking - draw polygons onscreen to mask out/in
- Keystone ability
- Monitor output if you don't have a laser
- Two output backends — Helios DAC (USB) and LaserCube (network) —
  switchable live, with per-device diagnostics
- Output safety layer: ARM gate, brightness ceiling, watchdog, blank on exit

Browser-based UI, MIDI mappable, oscillators, routable audio reactivity, a pattern bank, crossfades, free-from plyand projection geometry correction.


Created using Claude.AI, but with a human in the loop requesting, orchestrating features, bugs and UX.

![Snapshot of web interface](docs/laserlaserlaser.png)

## ⚠️ Laser safety first

TLDR; Don't be an idiot.

Point generation bugs can park the beam. This synth only draws closed
curves (no static points). Output starts **disarmed** and emits nothing
until you arm it, sits under a brightness ceiling that defaults to **5%**,
blanks on every exit path (including `kill`), and runs a watchdog that
blanks if the render loop ever stalls. Test everything in `--preview`
first.

None of that is a safety device. The ceiling is a creative limiter; the
[Mask](docs/MANUAL.md#mask) is a projection-mapping tool. The key switch,
aperture shutter, interlock loop, Remote Stop, rated eyewear and a
controlled beam path are the actual safety layer, and they are mandatory
regardless of what this software does.

**[Read SAFETY.md](docs/SAFETY.md)** — what the software does, what it
explicitly does not, the operating procedure, and the hardware bring-up
checklist.

## Quick start

Don't want to set up Python? Grab a zip from the
[Releases page](https://github.com/edmonkey-nz/laser-laser-laser/releases)
— Ubuntu, Windows and macOS (Apple Silicon), no install step. See
[INSTALL.md](docs/INSTALL.md) for the details and per-platform notes.

From source:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python3 laserx3.py                    # preview window + browser UI, no laser
python3 laserx3.py --laser            # output to the Helios DAC
python3 laserx3.py --output lasercube # output to a LaserCube over the network
```

Then open <http://localhost:8080/>. The browser UI is the main control
surface — a phone or tablet on the same LAN works too.

Output starts **disarmed** with a 5% brightness ceiling — nothing is
emitted until you press ARM. You can also pick the output device in
Settings and switch it live.

Driving the Helios needs its shared library and (on Linux) a udev rule —
[INSTALL.md](docs/INSTALL.md) covers both. The LaserCube path is pure
Python over the network, so it needs neither.

## Documentation

- **[INSTALL.md](docs/INSTALL.md)** — prebuilt binaries, Ubuntu / Windows /
  macOS setup, building the Helios library, command-line options, and
  testing the LaserCube without hardware
- **[SAFETY.md](docs/SAFETY.md)** — what the software does about laser
  safety and what it explicitly does not, the operating procedure, the
  hardware bring-up checklist, and the known gaps. **Read this one.**
- **[MANUAL.md](docs/MANUAL.md)** — every control explained: shapes,
  modulation, colour, geometry, the mask, ILDA / vectoriser / text,
  the pattern bank, MIDI mapping and settings
- **[CHANGELOG.md](CHANGELOG.md)** — what changed, per release
- **[PORTING.md](docs/PORTING.md)** — adopting the output safety layer in
  another project (laser-arcade, promptwaver)
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — ground rules if you want to
  hack on it

## Version

Current release: **1.8.2** (see `CHANGELOG.md`). Run `python laserx3.py
--version` to check the installed version.

## License

This project is released under the **MIT License** — see `LICENSE`. In
short: use it freely, including commercially, keep the copyright notice.
