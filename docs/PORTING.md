# Porting the output layer to another project

How to adopt `laser_output.py`, `helios.py` and `lasercube_output.py` in
another Python project that drives a laser.

Read [SAFETY.md](SAFETY.md) first if you haven't. This document is about
mechanics; that one is about what the code is for.

---

## 1. Why bother

Every project that drives a laser needs the same safety half: a real
`blank()`, an arm gate, a brightness ceiling, a watchdog, and blanking on
every exit path including `SIGTERM`. It is easy to end up with some of these
and not others, and the missing ones are only discovered when something goes
wrong. This is the layer where duplication costs real safety, so it is
written once.

What is *not* shared, deliberately: path planning. Planners differ
legitimately between projects — nearest-neighbour ordering, arc-length
resampling, letterboxing — and they should stay that way. Don't let the
shared layer grow into a planner.

---

## 2. What you copy

Three flat files, no package, no install step:

| File | Needed when |
|---|---|
| `laser_output.py` | Always. The protocol, `NullOutput`, `SafeOutput`. |
| `helios.py` | You drive a Helios. |
| `lasercube_output.py` | You drive a LaserCube over the network. |

Each carries a `# CANONICAL: laser-laser-laser/<name>` header. **This repo is
upstream.** Fix bugs here and re-copy; don't fork. A bug in
`laser_output.py` is a safety bug in every project that has it.

An installable package was considered and rejected: hosts that freeze with
PyInstaller, or have no build step at all, are better served by three flat
files than by a path dependency.

### Constraints these files hold to

Keep them true or the copy stops being a copy:

- **numpy + stdlib only.** Nothing from any host project.
- **Python 3.9 compatible.** `from __future__ import annotations` at the
  top; no `X | None` at runtime, no `match`.
- **Library path is injectable.** `HeliosDAC(lib_path=...)`, because hosts
  stage the `.so` differently — bundled as PyInstaller `datas` here, but a
  host may leave it unbundled and search for it, or take it from an
  environment variable.

---

## 3. The contract

```python
class LaserOutput(Protocol):
    name: str
    paces_loop: bool          # True if write() blocks until the device is ready
    last_points: int
    def write(self, frame, pps) -> bool: ...
    def blank(self) -> bool: ...
    def close(self) -> None: ...
    # optional:
    def enable(self) -> bool: ...    # hardware output gate, if the device has one
    def disable(self) -> bool: ...
    def diagnostics(self) -> list: ...  # [(label, value, severity), ...]
```

**Frame format: numpy `(N,6)` int32 — `x, y` 0..4095, `r, g, b, i` 0..255.**

Not normalised floats: it is the Helios point layout, which most laser
pipelines already produce or consume. If your
pipeline *is* float-native, convert at your edge with
`laser_output.from_normalised(xy, rgb, i)`.

`paces_loop` is the one that bites. Helios `write_frame` blocks on `GetStatus`,
so the DAC's point clock times your render loop and you need no sleep. UDP and
Null do not block, so **your loop must keep its own time**:

```python
if not out.paces_loop:
    spare = points / pps - (time.monotonic() - frame_start)
    if spare > 0:
        time.sleep(spare)
```

---

## 4. Wiring it in

```python
from laser_output import NullOutput, SafeOutput, install_panic_handlers

def make_backend(kind):
    if kind == "helios":
        from helios import HeliosOutput
        return HeliosOutput(0, lib_path=my_lib_path)
    if kind == "lasercube":
        from lasercube_output import LaserCubeOutput
        return LaserCubeOutput(ip=None)      # None = discover by broadcast
    return NullOutput()

out = SafeOutput(make_backend(kind), max_brightness=0.05)
install_panic_handlers(out)                  # as late as possible before the loop

try:
    while running:
        frame = ...                          # your (N,6) int32 frame
        out.write(frame, pps)
        if not out.paces_loop:
            ...                              # sleep to hit your frame time
finally:
    out.close()                              # blanks first
```

Use a literal `if/elif` with direct imports, not `importlib` — PyInstaller
cannot trace `importlib` and will silently drop the backend from the bundle.

`SafeOutput` owns the arm gate, the brightness ceiling, the watchdog, the
device lock and blank-on-exit. Nothing downstream of it can bypass those, which
is the point — so **do not** apply your own transforms after `out.write()`.

### The one hard rule

Your geometry correction, orientation flips and any other output transform go
**before** `out.write()`. The ceiling and arm gate are the last thing before
the device. Anything you put after them can exceed the ceiling, which defeats
the entire mechanism.

---

## 5. Adapting an existing pipeline

**Point lists.** A pure-Python pipeline producing `(x, y, r, g, b)` tuples in
DAC units needs a one-function adapter:

```python
import numpy as np

def to_frame(points):
    """List of (x, y, r, g, b) in DAC units -> (N,6) int32."""
    a = np.asarray(points, dtype=np.int32)        # (N,5): x,y,r,g,b
    frame = np.empty((len(a), 6), dtype=np.int32)
    frame[:, :5] = a
    frame[:, 5] = a[:, 2:5].max(axis=1)           # i = max(r,g,b)
    return frame
```

- **Keep your existing `i` convention** (`max(r,g,b)`, or 255 lit / 0 blank).
  Changing it changes brightness on the rig for no reason anyone will
  remember.
- **Keep your planner untouched.** Resampling, letterboxing, keystone and the
  rest stay where they are, upstream of `out.write()`.
- **An existing `laser_on` gate becomes `SafeOutput.arm()`/`disarm()`.** Keep
  disarming unfaded and same-tick.
- **A creative `brightness` control stays.** The ceiling is separate and sits
  below it.
- **Don't double-buffer.** If your old output already runs a writer thread
  with latest-wins buffering, either keep it and set `paces_loop = False`, or
  drop it and let the blocking Helios path pace the loop — not both.
- **Pass `lib_path` explicitly** if your build does not bundle the Helios
  library next to `helios.py`.

**A realtime audio callback in the same process** is the case to be careful
of. A per-point Python packing loop holding the GIL, or a naked
`while: pass` spin on `GetStatus`, will starve it into audible dropouts. The
shared code sleeps rather than spins and packs with numpy in one shot — don't
undo either. Prefer the LaserCube backend if you have the choice: its
`write()` never touches a socket.

**Out of scope:** anything that writes `.ild` files rather than driving a
DAC, and anything that must run on Python 2.7. File-codec code is a separate
question, and a 2.7 constraint would poison these files.

---

## 6. Verifying the port

Before you trust it. None of this needs a laser:

1. App starts, comes up **disarmed**, ceiling 5%.
2. Disarmed produces zero-colour frames — not an absence of frames.
3. Ceiling holds with your brightness control at maximum.
4. Every exit path blanks: Ctrl-C, `kill -TERM`, an exception in the loop,
   `atexit` alone.
5. Watchdog fires on an injected `sleep(2)` and releases on recovery.
6. Frame rate unregressed versus before the port.
7. For LaserCube: `scripts/lasercube_sim.py` with `--stall-after`, `--drop`,
   `--refuse-enable`, `--tiny-buffer`, `--temperature 45`.

Then, and only then, [SAFETY.md](SAFETY.md) §5 on real hardware.

---

## 7. Keeping copies in sync

There is no tooling for this and deliberately no build step. The discipline is
manual:

```bash
sha256sum laser_output.py helios.py lasercube_output.py \
          /path/to/your/project/{laser_output,helios,lasercube_output}.py
```

If you find yourself wanting to change one of these files *for one project*,
that is the signal the change belongs behind a constructor argument instead —
`lib_path`, `max_brightness` and `single_shot` are all there for exactly that
reason.
