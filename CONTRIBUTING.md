# Contributing

Thanks for your interest! This is a personal hobby project, shared in the
hope it's useful to other laser/synth tinkerers.

## Ground rules

- **Laser safety comes first.** Any change that affects what gets sent to
  the DAC (point generation, blanking, geometry, brightness) should keep
  the "closed curves + blanked travel moves + blank on exit" safety
  properties intact. Test in `--preview` before `--laser`.
  **[docs/SAFETY.md](docs/SAFETY.md) §6 is the rulebook** — read it before
  touching anything on the output path. In particular: the arm gate and
  the brightness ceiling are the last transform before the device, so a
  new output transform goes *before* them, never after.
- **`laser_output.py` and `helios.py` are copied verbatim into two sibling
  projects** (laser-arcade, promptwaver). Keep them importable standalone —
  numpy and stdlib only, nothing from this project, Python 3.9 compatible.
  A bug in `laser_output.py` is a safety bug in three repositories.
- **No hardware? You can still test the LaserCube path.**
  `scripts/lasercube_sim.py` is a fake device that answers on the real
  ports and can be told to stall, drop packets, refuse to enable output or
  report over-temperature.
- Keep the **no-build-step** philosophy: vanilla Python + a single
  self-contained `static/index.html` (no bundlers, no npm, no CDN).
- Every code change should bump the version in `laserx3.py`
  (`__version__`) and add a `CHANGELOG.md` entry.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python laserx3.py              # screen only, no laser (browser UI always on)
```

The architecture, in brief:
- `shapes.py` — the render engine (all parameters, shapes, LFO, routing)
- `laserx3.py` — app entry, render loop, MIDI, output wiring
- `laser_output.py` — the output safety layer: `LaserOutput` protocol,
  `NullOutput`, and the `SafeOutput` wrapper that every backend sits under
  (arm gate, brightness ceiling, watchdog, blank-on-exit)
- `helios.py` — Helios DAC backend (USB, ctypes)
- `lasercube_output.py` — LaserCube backend (network, pure Python UDP)
- `webui.py` + `static/index.html` — the browser control surface
- `patterns.py` / `settings.py` / `ilda.py` / `vectorise.py` /
  `geometry.py` — feature modules, each fairly self-contained

Backends are deliberately ringfenced: a backend imports nothing from this
project, and adding one means a class implementing the protocol plus a
branch in `make_backend()`. Neither backend can bypass `SafeOutput`.

Issues and pull requests welcome.
