# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A laser visuals synth for the Helios DAC and the LaserCube (network): a
Python render loop generating point frames, driven from a browser control
surface, a MIDI controller, and a small pygame desktop window (a launcher
with status and keyboard shortcuts; `v` shows the beam full-window).

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

- **Every code change bumps the version and adds a `CHANGELOG.md` entry.**
  (CONTRIBUTING.md ground rule.) The version is written out in **five**
  places and nothing derives it from anything else, so bump all of them:
  1. `laserx3.py` — `__version__` (the source of truth; `--version` reads it)
  2. `about.md` — line 2, `v1.8.0`; the About panel serves this file verbatim
  3. `README.md` — the shields.io **version badge** near the top
  4. `README.md` — "Current release: **1.8.0**" under *## Version*
  5. `CHANGELOG.md` — the new `## [1.8.0] — YYYY-MM-DD` heading

  Historical mentions ("built in 1.6.0", "fixed in 1.5.0", SAFETY.md's
  "applies to version 1.6.0 onward") are statements about the past and must
  **not** be bumped.

  This list is written out because it keeps drifting: `about.md` sat at
  v1.3.0 through four releases, and the two README references sat at 1.6.0
  through two. Nothing warns you — grep for the old number before tagging.
- Laser safety governs anything touching the DAC stream: preserve the
  "closed curves + blanked travel moves + blank on exit" properties. Test in
  `--preview` before `--laser`. **`docs/SAFETY.md` §6 is the rulebook for
  changing anything on this path** — read it before touching output code.
- **`laser_output.py`, `helios.py` and `lasercube_output.py` are written to
  be dropped into other projects unchanged** (`docs/PORTING.md`). Keep them
  importable standalone — numpy + stdlib only, nothing from this project,
  Python 3.9 compatible. The safety requirements they implement are
  `docs/lasercubeoutput.md` §4.
- **This repo is standalone.** Don't name or cite other projects in code,
  comments or docs; past CHANGELOG entries are history and stay as written.
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

`ShapeEngine.frame(dt, audio)` (`shapes.py`) returns an `(N,6)` int32
array — columns `x,y` in 0..4095 (12-bit DAC space) and `r,g,b,i` in 0..255.
Every consumer takes that same array. The render loop (the `while True:` in
`laserx3.py`'s `main()`) is where the pipeline order lives, and **the
distinction that matters most is which stage a transform belongs to**:

```
frame = engine.frame(dt, a)
if engine.blanked: frame[:, 2:6] = 0
frame = mask.apply(frame)          # ← shared: hits preview, web AND DAC
frame = mono_laser(frame, ...)     # ← shared (only if a mono projector is set)
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
`geometry.py`'s module docstring says so explicitly. The mask and
`mono_laser` are the opposite case: they mutate the shared frame precisely so
laser and monitor agree. When adding an output transform, decide which of
these two it is; that decision is the whole design.

Normalised space is `[-1,1]` everywhere in the UI and stored data; the
12-bit conversion is `v/2047.5 - 1` (see `geometry.py`, `mask.py`).

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
blocks the render thread, here or in the repos that copy it — a network
hiccup must cost a dropped frame, not a stalled loop. Its module
docstring carries the protocol, with a source cited per constant; the
protocol is reverse-engineered, so treat it as unverified until hardware says
otherwise. `scripts/lasercube_sim.py` is a fake device for testing it.

### Frame sources

The engine draws either a generated shape (`SHAPE_NAMES`, `shapes.py`) or
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
(`laserx3.py`).

### Browser control surface

`webui.py` runs aiohttp in a background thread with its own asyncio loop; the
render loop stays on the main thread and hands frames over under a lock.

- **Server → client**: packed binary frames at 30 Hz (format documented in
  `webui.py`'s module docstring) plus a JSON `state` message at 5 Hz carrying
  the full UI state.
- **Client → server**: JSON messages dispatched by a single `if/elif` chain in
  `WebUI._apply()`. Adding a feature means: a handler branch there, a key in
  the `state` broadcast, and UI in `static/index.html`.

`static/index.html` is one ~2500-line file — inline CSS and vanilla JS, no
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

Frames go out in *repeat* mode (the DAC replays the last frame until the next
arrives). `single_shot=True` (1.12.0) plays each frame once instead; it exists
for hosts that need a dead process to go dark without the watchdog; this
app leaves it off. See `docs/SAFETY.md` §3.

### Threads and the GIL — hypotheses, NOT yet measured here

Another app with the same thread shape measured its way through a
thread-contention problem in 2026-09 (same laptop, same Python). Its
conclusions are recorded here as leads; **none of the points below has been
measured in this repo** — treat them as hypotheses to test, not facts.

**The shape.** Five threads share one GIL: the render loop (main thread), the
LaserCube sender (`lasercube_output.py`, wakes every 2ms), the `AudioAnalyzer`
input callback (`laserx3.py`), the aiohttp thread (`webui.py`) and the
vectoriser camera thread (`vectorise.py`). No `sys.setswitchinterval` call
exists, so CPython hands the GIL over at its 5ms default.

- **The sender is the thread at risk.** It is paced and latency-sensitive —
  the role an audio producer thread played in that app. There, a render
  thread saturating the GIL starved the producer (36% of blocks missed at the 5ms
  default with render at 2x its budget) and `sys.setswitchinterval(0.0005)`
  took it to 0.0% for ~3% of frame rate. Here the symptom would be the
  LaserCube ring buffer draining → beam pauses, most likely when fluid sim or
  the vectoriser is heavy. **Test before changing:** load the render loop
  heavily against `scripts/lasercube_sim.py` and watch `rx_buffer_free`. If it
  doesn't underrun, don't add the call.
- **Don't reach for thread priority.** `SCHED_FIFO` was tested on the
  starving thread: noise (36.1% → 33.3%). A thread with OS priority still waits
  on the GIL, and priority needs per-OS permissions a released binary can't
  assume.
- **Keep `ctypes.cdll` in `helios.py`.** `CDLL` releases the GIL for the
  duration of each foreign call, so the render thread blocking on `GetStatus`
  lets everything else run. `PyDLL` would hold it through every blocking wait.
- **`AudioAnalyzer._cb` does FFT and band maths inside the PortAudio callback.**
  That app moved all work out of its (output) callback for this reason. Lower stakes here — it's an input stream, so a late callback means jittery
  audio reactivity, not an audible dropout.

**Measuring, in general.** Per-point Python/numpy loops are dispatch-bound, not
arithmetic-bound: in that app, 300 tiny numpy ops took 1.44ms while one op
over 21x the data took 0.067ms. Batching beats faster hardware. Measure with the
app's real thread shape — two Python threads produced *less* total work than
one. Extra cores, RAM and GPU did nothing for that app's frame rate.

**Before trusting any timing on the dev laptop,** check the CPU isn't capped:
compare `scaling_max_freq` with `cpuinfo_max_freq` under
`/sys/devices/system/cpu/cpu*/cpufreq/`. On 2026-09-16, 11 of 12 cores were
found pinned at 2.1GHz of 4.06GHz, halving everything; the fix does not survive
a reboot. Read the real clock from `/proc/cpuinfo` MHz — `scaling_cur_freq` is
only a hint on amd-pstate. Numbers recorded before that date (e.g. the sender
comment's "~320 frames/s against a 31 fps render loop") may have been taken at
half clock.
