# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A laser visuals synth for the Helios DAC: a Python render loop generating
point frames, driven from a browser control surface, a MIDI controller, and
a pygame preview window simultaneously.

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python laserx3.py                  # preview + browser UI, NO laser — dev mode
python laserx3.py --web            # browser UI only, no pygame window
python laserx3.py --laser          # real DAC output
python laserx3.py --list-midi      # enumerate MIDI ports
python laserx3.py --version
```

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
  `--preview` before `--laser`.
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
    └── out = geom.apply(hw_orient(frame, ...)) # ← DAC-ONLY, never shared
        dac.write_frame(out, pps)
```

`hw_orient()` and `GeometryCorrection.apply()` are deliberately applied only
to the DAC copy so the preview stays a true, uncorrected reference —
`geometry.py`'s module docstring says so explicitly. The mask is the opposite
case: it mutates the shared frame precisely so laser and monitor agree. When
adding an output transform, decide which of these two it is; that decision is
the whole design.

Normalised space is `[-1,1]` everywhere in the UI and stored data; the
12-bit conversion is `v/2047.5 - 1` (see `geometry.py:90`, `mask.py`).

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
