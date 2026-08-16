# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A laser visuals synth for the Helios DAC and the LaserCube (network): a
Python render loop generating point frames, driven from a browser control
surface, a MIDI controller, and a pygame preview window simultaneously.

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python laserx3.py                  # preview + browser UI, NO laser — dev mode
python laserx3.py --web            # browser UI only, no pygame window
python laserx3.py --laser          # real DAC output (alias for --output helios)
python laserx3.py --output lasercube          # LaserCube over the network
python laserx3.py --output lasercube --lasercube-dry-run   # pack, send nothing
python laserx3.py --list-midi      # enumerate MIDI ports
python laserx3.py --list-lasercubes           # discover LaserCubes
python laserx3.py --version

python scripts/lasercube_sim.py    # fake LaserCube: test the whole path,
                                   # zero photons. --stall-after / --drop /
                                   # --refuse-enable / --temperature / etc.
```

**Output starts disarmed with a 5% brightness ceiling**, on every backend.
Nothing is emitted until ARM. Arming can fail (the LaserCube refuses while
over-temperature), so `arm()` returns a bool — do not assume it succeeded.
The output device is switchable at runtime from Settings, and switching
always disarms.

The browser UI is always on (`--no-web` opts out); port 8080, `--web-port`
to move it. Never tell a user to pass `--web` to get the UI — passing it
explicitly only suppresses the pygame preview-window fallback. Without
`--laser`/`--preview`/`--web`, preview is forced on so nothing fires a laser
by surprise.

**There is no test suite, linter, or build step** — and the no-build-step
philosophy is deliberate (see CONTRIBUTING.md): vanilla Python plus a single
self-contained `static/index.html`, no bundler, no npm, no CDN. Verify
changes by running the app and driving it over the WebSocket, not by running
tests.

Standalone executables are built in CI only (`pyinstaller.spec` +
`.github/workflows/build.yml`), triggered by pushing a `v*.*.*` tag.

## Repo conventions

- **Every code change bumps `__version__` in `laserx3.py` and adds a
  `CHANGELOG.md` entry.** (CONTRIBUTING.md ground rule.)
- Laser safety governs anything touching the DAC stream: preserve the
  "closed curves + blanked travel moves + blank on exit" properties. Test in
  `--preview` before `--laser`. **`docs/SAFETY.md` §6 is the rulebook for
  changing anything on this path** — read it before touching output code.
- **`laser_output.py`, `helios.py` and `lasercube_output.py` are copied
  verbatim into laser-arcade and promptwaver.** Keep them importable
  standalone — numpy + stdlib only, nothing from this project, Python 3.9
  compatible (laser-arcade's floor). A bug in `laser_output.py` is a safety
  bug in three repos. The safety requirements it implements are
  `docs/lasercubeoutput.md` §4.
- `settings.json` and `masks.json` are gitignored runtime state;
  `patterns.json` is tracked and ships with starter patterns.
- **The flat root layout is deliberate — do not "tidy" the Python modules
  into a package.** Several resolve their data with
  `os.path.dirname(__file__)` (`about.md`, `patterns.json`, `static/`, and
  the Helios shared library `helios.py` loads by path), and the PyInstaller
  bundle flattens to the same layout, so moving them breaks both source and
  frozen runs in ways CI only catches per-OS. Docs live in `docs/`, helper
  scripts in `scripts/`.

## Architecture

### The frame is the spine

`ShapeEngine.frame(dt, audio)` (`shapes.py:540`) returns an `(N,6)` int32
array — columns `x,y` in 0..4095 (12-bit DAC space) and `r,g,b,i` in 0..255.
Every consumer takes that same array. The main loop (`laserx3.py`, ~line 570
onward) is where the pipeline order lives, and **the distinction that matters
most is which stage a transform belongs to**:

```
frame = engine.frame(dt, a)
if engine.blanked: frame[:, 2:6] = 0
frame = mask.apply(frame)          # ← shared: hits preview, web AND DAC
    ├── preview.draw(frame)                    (pygame window)
    ├── web.publish(frame, ...)                (browser scope)
    └── out.write(geom.apply(hw_orient(frame, ...)), pps)
                                    # ← DAC-ONLY, never shared
```

`out` is a `SafeOutput` (`laser_output.py`) wrapping the backend. Inside
`write()` it applies the arm gate and the brightness ceiling — the last
transform before the device, so nothing upstream can bypass them. Those are
DAC-only for the same reason `geom` is: the monitor must keep showing what the
*content* is, or the ceiling becomes invisible instead of obvious.

`hw_orient()` and `GeometryCorrection.apply()` are deliberately applied only
to the DAC copy so the preview stays a true, uncorrected reference —
`geometry.py`'s module docstring says so explicitly. The mask is the opposite
case: it mutates the shared frame precisely so laser and monitor agree. When
adding an output transform, decide which of these two it is; that decision is
the whole design.

Normalised space is `[-1,1]` everywhere in the UI and stored data; the
12-bit conversion is `v/2047.5 - 1` (see `geometry.py:90`, `mask.py`).

### Output backends

Backends implement the `LaserOutput` protocol (`laser_output.py`) and are
built by `make_backend(kind)` in `laserx3.py` — a literal `if/elif` with
direct imports, because PyInstaller cannot trace `importlib`. Adding one
means a class plus a branch; nothing else in the loop changes.

Two properties carry the design:

- `paces_loop` — True when `write()` blocks until the device is ready, so the
  device's own point clock times the render loop. Helios True (it blocks on
  `GetStatus`), LaserCube and Null False (the loop must sleep itself).
- optional `enable()`/`disable()` — a *hardware* output gate, mirrored from
  the arm state by `SafeOutput._gate_device`. The LaserCube has one
  (`CMD_SET_OUTPUT`); the Helios does not, and its safe state is streaming
  darkness instead. `enable()` may legitimately refuse, and `arm()` honours
  that refusal rather than reporting ARMED over a dark device.

`lasercube_output.py` is UDP and non-blocking: `write()` swaps the frame into
a lock-guarded slot (the `WebUI.publish` pattern) and a daemon sender thread
streams it, paced to the DAC rate with `rx_buffer_free` as a brake. It never
blocks the render thread — promptwaver shares a process with a realtime audio
callback, and a blocked render thread there is an audible xrun. Its module
docstring carries the protocol, with a source cited per constant; the
protocol is reverse-engineered, so treat it as unverified until hardware says
otherwise. `scripts/lasercube_sim.py` is a fake device for testing it.

### Frame sources

The engine draws either a generated shape (`SHAPE_NAMES`, `shapes.py:13`) or
an installed source, resolved inside `frame()`: `test_frame` (alignment grid,
overrides everything), ILDA frames, rendered text, the custom polygon, or the
vectoriser. All of them then get the same effects composed on top (spin, size,
position, colour, dotify, duplicator, sweep, flips).

### Parameters and control surfaces

`engine.p` is a flat dict of floats — the single source of truth. Everything
funnels into it: `set_param()` for one value, `apply_params()` for a whole set
(which snaps or crossfades depending on `engine.xfade`). Browser, MIDI and
preview keyboard are three peers writing the same dict, which is why they stay
in sync for free. MIDI actions that aren't parameters live in `ACTION_KEYS`
(`laserx3.py:104`).

### Browser control surface

`webui.py` runs aiohttp in a background thread with its own asyncio loop; the
render loop stays on the main thread and hands frames over under a lock.

- **Server → client**: packed binary frames at 30 Hz (format documented in
  `webui.py`'s module docstring) plus a JSON `state` message at 5 Hz carrying
  the full UI state.
- **Client → server**: JSON messages dispatched by a single `if/elif` chain in
  `WebUI._apply()`. Adding a feature means: a handler branch there, a key in
  the `state` broadcast, and UI in `static/index.html`.

`static/index.html` is one ~1900-line file — inline CSS and vanilla JS, no
framework. The scope canvas (`onFrame`) draws with `globalCompositeOperation
= "lighter"` and a phosphor-decay fill, so **anything overlaid on it must
reset the composite mode to `source-over`** (see `drawMaskOverlay`). Note the
scope canvas is CSS-scaled: pointer coordinates need scaling by
`canvas.width / rect.width`, unlike the fixed-size modal editors.

`static/monitor.html` (served at `/monitor`) is a second, standalone page:
a chrome-free beam view for a second screen. It deliberately duplicates the
small render loop rather than sharing code — it consumes only the binary
frame stream (the header's blanked byte means it needs no JSON state) and
reconnects on its own.

### Persistence

Every store follows the same shape — plain hand-editable JSON next to the
scripts, a `threading.Lock`, and atomic writes (temp file + `os.replace`), with
read failures degrading to empty rather than crashing. `patterns.py`
(`PatternBank`), `masks.py` (`MaskBank`) and `settings.py` (`SettingsStore`)
are all variations on it; copy the pattern for anything new.

Patterns store a param snapshot plus optional extras (text, ILDA file, custom
points, per-pattern pps/points) and are re-applied through
`PatternBank.apply_entry()`. Masks are deliberately *independent* of patterns
— a mask describes the room, not the visual.

### Hardware

`helios.py` is a ctypes wrapper over `libHeliosDacAPI.so`. `write_frame()`
blocks on `GetStatus`, so when the laser is running the DAC's point clock
paces the render loop — no timer needed. Without a DAC the loop sleeps to hit
the target frame time instead.
