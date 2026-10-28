# Laser safety

What this software does about safety, what it deliberately does not, and how
to work with it. Read §1 and §2 before anything else.

Applies to version 1.6.0 onward. Last reviewed against 1.12.0 (2026-10-27).

---

## 1. The one thing that matters

**Software is not a safety device.** Every control described in this document
is implemented in Python, running in the same process as the render loop it is
supposed to protect you from. When the software is the failure — a crash, a
driver bug, a wedged USB call, a stuck buffer — none of it can help you.
That is not a limitation to be engineered away; it is the nature of the thing.

The actual safety layer is physical, and it is mandatory regardless of what
this code does:

- **Key switch** — output physically disabled when the key is out.
- **Aperture shutter** — blocks the beam at the head.
- **Interlock loop** — kills output when the room is opened.
- **Remote Stop** — in your hand, not across the room, whenever the key is in.
- **Eyewear** rated for *every* wavelength the projector emits, worn by
  everyone present, not just you. For the **LaserCube Ultra 7.5W** that is
  **455 nm blue (4 W), 525 nm green (2 W), 638 nm red (1.5 W)**. Check the
  figures against your own unit's plate — do not trust a number in a document.
- **Controlled beam path** — into a dump or a matte dark surface. Never toward
  eyes, windows, reflective surfaces, or skyward.

A 7.5 W Class 4 laser can cause instant permanent eye injury *including from
diffuse reflections*, plus skin burns and ignition. Treat the beam as
dangerous at all times, not just when it's pointed somewhere obvious.

---

## 2. Daily operating procedure

1. Beam path set up and clear. Dump or matte surface at the end of it.
2. Eyewear on — everyone in the room.
3. Remote Stop in hand.
4. Key in, shutter closed.
5. Start the synth. It comes up **disarmed**. Check the **MAX** badge in the
   header reads **5%** — the ceiling persists between runs, so it may not.
6. Open the shutter, then **ARM**. Confirm the beam lands where you expect,
   at the power you expect.
7. Raise the ceiling only once you're satisfied with the aim.

**On a switched (TTL) projector, steps 5 and 7 mean nothing** — the ceiling
cannot dim it, so the first armed frame is full power. See
[§3](#it-does-nothing-on-a-switched-ttl-projector).

To stop, in decreasing order of urgency: **Remote Stop** → **key out** →
**shutter** → **DISARM** (header button, `.` in the desktop window, or a
mapped MIDI pad). The first three are real; DISARM is software.

---

## 3. What the software does

### ARM gate

Output starts **disarmed** on every launch and emits nothing until you arm it.
This is never remembered between runs, however the last session ended — there
is no auto-arm flag, deliberately.

Arming asks for confirmation in the browser. Disarming never does, and takes
effect on the very next frame with no crossfade: a fade on the way down is a
fade you are still emitting through.

Three ways to disarm: the header **ARM/DISARM** button, `.` in the desktop
window (`shift-.` arms), or a MIDI pad bound to the **DISARM laser** action.
The MIDI action is one-way on purpose — a stray CC should never be able to arm
a laser. Arming lives only in the browser and on `shift-.`; the desktop
window has no arm button, so there are not two places to disagree about
whether the beam is live.

**BLANK is not DISARM.** The header **BLANK** button, `space` in the desktop
window and the MIDI **blank** action zero the colour of the scene, upstream of
everything. The output stays
armed, and un-blanking brings the beam straight back with no confirmation.
Use it as a creative cut, not as a stop.

> **"Disarmed" does not mean the DAC goes quiet.** It means it is actively
> streaming darkness. A Helios repeats its last frame until a new one arrives,
> so a DAC that simply stopped being fed would sit there replaying whatever was
> on screen when you disarmed. Silence would be the *less* safe state.

### Brightness ceiling

A hard cap applied at the very last step before the DAC — after the scene, the
mask, the geometry warp, and every other transform. Nothing upstream can
exceed it: not a pattern load, not audio modulation, not a MIDI knob, not the
`brightness` fader.

Defaults to **5%**. It lives in **Settings → Brightness ceiling**, not in the
header, so it cannot be nudged mid-show; the header shows it read-only as
**MAX n%**, and the number turns amber above 5%. Raising it asks for
confirmation (and says so if you are armed). **SET 5% (BRING-UP)** snaps it
back. The value persists in `settings.json`, so if you raise it, it stays
raised next launch — the ARM gate, not the ceiling, is the per-session
guarantee.

`--max-brightness 0..1` on the command line overrides the saved value for that
run only; it is not written back. It cannot bypass the ceiling, only set it —
but a launcher script that passes `--max-brightness 1` makes every session
start at full power, so check how the app was started.

On the LaserCube this ceiling matters more than it looks. The network protocol
has **no power-limit command** — per-point RGB is the only brightness control
the device exposes — so this is the only limiter in the system. There is no
firmware cap sitting downstream of a host-side bug.

It is separate from the `brightness` fader in Colour & beam, which remains a
purely creative control operating underneath the ceiling.

At 5% on an 8-bit colour channel you have about 13 levels. Plenty for aiming,
coarse for content.

#### It does nothing on a switched (TTL) projector

The ceiling scales amplitude. A projector whose diode is **switched rather
than dimmed** — full power or dark, which is most single-colour units — has
no amplitude to scale. Every non-zero value it receives comes out at 100%, so
a 5% ceiling produces a full-power beam while the header reads 5%.

This is the one case where the procedure in §2 is actively misleading: step 5
has you trust a number that the hardware ignores. On such a projector the
ceiling is not a limiter at all. Use the key switch, the shutter, eyewear and
distance, and treat every armed frame as full power — because it is.

**Settings → Monochrome projector → on/off only (TTL)** is where this is
declared, and the panel says the same thing next to the checkbox. Ticking it
does not make the projector safer; it makes the *image* correct, by cutting
graded levels to a clean on/off instead of sending values the diode cannot
render. The safety consequence is a property of the hardware and is there
whether or not the box is ticked.

### Watchdog

A daemon thread blanks the output if the render loop stops feeding it — a GC
pause, a deadlock, a logic bug, a stalled network write.

The stall threshold adapts to the frame time: `max(250 ms, 3 × points/pps)`.
A fixed threshold would be wrong, because at 4000 points and 5000 pps a single
frame legitimately takes 800 ms. It also doesn't start guarding until the first
frame is written, since startup routinely takes longer than the threshold.

**The watchdog blanks; it does not disarm.** If the render loop recovers, the
next frame goes out through the arm gate as normal — an armed output comes
back on by itself, with `render loop recovered` in the console and nothing
asked of you. A stall is something to investigate before carrying on, not a
stop. (A signal — Ctrl-C or `kill` — is different: it disarms as well as
blanking, and the process is on its way out anyway.)

If the watchdog cannot take the device lock, it treats that as evidence the
render thread is alive inside a write, not as a stall. If the driver is
genuinely wedged inside a C call, no software can blank that device — that is
what the key switch is for.

On the LaserCube, the sender thread keeps re-sending the current frame while
the render loop is stalled (that is what keeps the device buffer from
draining). So during a stall the image is *repeated and still scanning* until
the watchdog replaces it with darkness, not frozen on a point.

### Blank on every exit path

`SIGINT` (Ctrl-C), `SIGTERM` (`kill`), unhandled exceptions in the render
loop, closing the desktop window (or its QUIT button), and an `atexit`
backstop all blank before releasing the device. All five paths are verified.

**SIGTERM was the real gap before 1.5.0.** Without a handler the default action
terminates the process outright, so teardown never ran and the DAC sat
replaying its last frame indefinitely.

On the Helios, blanking writes a dark frame in *repeat* mode rather than merely
calling `Stop()`, so the DAC keeps emitting darkness even if the process dies
immediately afterwards. On the LaserCube, blanking first replaces the streamed
frame with darkness (so the beam goes dark even if the next command is lost),
then turns the device's output off.

### Device gate (LaserCube only)

The LaserCube has a hardware output gate (`CMD_SET_OUTPUT`), so ARM and DISARM
drive the device itself, not just our frame stream. A disarmed LaserCube stops
emitting even if this process is killed mid-frame.

Three consequences worth knowing:

- **Arming can fail.** If the device refuses — it reports over-temperature,
  say — the app stays **disarmed** and says so. It will not show ARMED over a
  device that is dark.
- **Enable is verified, not assumed.** UDP has no acknowledgement, so a
  successful send proves only that the datagram left this machine. `enable()`
  reads the state back from the device and believes the device.
- **Switching output device always disarms.** Arming is a statement about one
  specific projector; it is never carried across a device change.

### Helios frame mode

By default the Helios plays each frame in *repeat* mode: it replays the last
frame until the next arrives. That keeps the beam scanning if the host
hiccups, but it also means a host that dies without blanking leaves the image
painted (which is what the exit paths above exist to prevent).

Since 1.12.0 `helios.py` can instead send **single-shot** frames
(`HeliosOutput(single_shot=True)`): the DAC plays each frame once and stops,
so a process that stops feeding it goes dark after the current frame. The DAC
parks on the final point of a single-shot frame, so that point is forced dark
in this mode. **This app does not enable it**: it is for hosts that need a
dead process to go dark without relying on the watchdog.
TEST DEVICE reports which mode is in use.

### Device diagnostics

**Settings → Laser output → TEST DEVICE** queries the attached device and
reports what it says about itself. It emits nothing, so it is safe to press at
any time, armed or not.

For a LaserCube that means firmware, serial, model, connection type,
temperature and thermal warnings, **interlock state**, output state, power
source, scan rate and its maximum, buffer occupancy, the device's own packet
error count, and our frame sent/dropped/error counters. For a Helios it means
device count, link status and frame mode — the Helios reports no temperature,
interlock or power state at all, and the panel says so rather than showing
blanks. Every backend also reports the arm state, ceiling, watchdog state and
current stall threshold.

Reading a device's interlock state is not the same as having an interlock. The
hardware loop is the interlock; this is a readout of it.

### Field log

Every arm and disarm is written to `error.txt` (beside the executable, or the
checkout) with the ceiling and the device at that moment, whichever route
caused it — browser, MIDI, keyboard. Each line is flushed on its own, so the
trail survives a `kill -9` or a native crash. After an incident, this is how
you answer "was it armed, and at what ceiling". The previous run is kept as
`error.prev.txt`.

### Point generation

A parked beam is a burn and fire risk, not just a visual artifact, so the
engine is built to avoid one:

- **Generated shapes are single closed curves** — no static points, no
  multi-stroke geometry. Where a figure cannot be drawn in one stroke (a 3D
  wireframe's edges), edges are retraced rather than adding a blanked jump.
- **Duplicator copies, text, and vectoriser paths** are joined by blanked
  travel moves.
- **Samples are spaced by arc length**, so they do not bunch where a curve
  turns.
- **The 3D stage cannot collapse a figure to a point.** Flat shapes never
  reach perfect edge-on (`MIN_FLAT_COS`), and no figure may shrink below a
  fraction of its incoming size (`MIN_3D_EXTENT`). Without these, a 1:1
  lissajous tilted edge-on put an entire 800-point frame on one DAC
  coordinate. 3D solids are built off-axis for the same reason: face-on, a
  box's uprights project to four points.
- **The fluid shape is a vortex flow**, which has no sinks, so samples cannot
  converge into a pile.

**ILDA files are not covered.** They are drawn as the file describes them. On
load the app checks for runs of lit points on one coordinate and prints a
warning to the console, but **plays the file anyway** — see §4.

---

## 4. What the software does *not* protect against

Be specific about this, because vague reassurance is worse than none:

| Control | Does not help against |
|---|---|
| ARM gate | Anything after you've armed it. It is a deliberate-action gate, not a monitor. |
| BLANK | Anything. It is a creative cut; the output stays armed. |
| Brightness ceiling | A crash, a driver bug, a stuck buffer, or a protocol error. It is a **creative limiter**. It also cannot stop a beam that is parked — 5% of a 7.5 W beam, stationary, still burns — and it does **nothing at all** on a switched (TTL) projector, which has no amplitude to scale. |
| Watchdog | A driver wedged inside a C call, or anything that kills the process without running Python (`SIGKILL`, power loss, a kernel panic). And it does not disarm: when the loop recovers, an armed output resumes on its own. |
| Blank-on-exit | `kill -9`. Nothing in userspace survives that. |
| ILDA dwell check | A parked beam in an ILDA file. It is a console warning; the file still plays. |
| [Mask](MANUAL.md#mask) | Anything. It is a **projection-mapping tool** — the galvos still travel through masked areas with the beam dark. Not an interlock, not a zone limiter. |
| Geometry correction | Anything. It is applied to the DAC copy only, for aiming. |

---

## 5. Bringing up new hardware

Do these **in order**. Do not skip ahead. This applies to a new projector, a
new DAC, a new output backend, or a rig you haven't used in a while.

1. **Dry run, no hardware.** Confirm the app runs, the watchdog fires on a
   simulated stall, and the exit paths blank.
2. **Hardware connected, output disabled.** Confirm the device is detected and
   responding (TEST DEVICE). Confirm nothing is emitting.
3. **First light — minimum power, beam dump, eyewear, Remote Stop in hand.**
   Ceiling at 5%. Confirm a blanked frame is *genuinely dark* — this is the
   check an analog ILDA path can fail, because DAC offset versus the
   projector's mute threshold produces a ghost beam. On a switched (TTL)
   projector there is no minimum power: this step is at full power.
4. **Stall test.** Deliberately stall the sender and observe what the hardware
   does. Three possibilities:
   - blanks automatically — ideal;
   - repeats the last buffered points — acceptable, still scanning;
   - **holds the final point — hazardous.** A stationary beam is a burn and
     fire risk. If this is the answer, the watchdog is load-bearing
     safety-critical code and must be treated as such.

   The **Helios repeats** (case 2) in its default repeat mode, because
   `WriteFrame()` without `HELIOS_FLAG_SINGLE_MODE` replays its frame until the
   next one arrives. In single-shot mode (not used by this app) it stops after
   the frame and holds a point that the driver forces dark. The LaserCube's
   behaviour is **not yet known** — see
   [lasercubeoutput.md §4.3](lasercubeoutput.md). Until it is answered on
   hardware, assume the hazardous case.
5. **Disconnection test.** Pull the cable mid-stream. Does the device blank?
6. **Only then** raise power incrementally.

For the LaserCube specifically, steps 1–2 can be done properly without the
projector:

```bash
python scripts/lasercube_sim.py            # a fake device, no photons
python laserx3.py --output lasercube --lasercube-ip 127.0.0.1
```

The simulator can be told to misbehave — `--stall-after`, `--drop`,
`--refuse-enable`, `--tiny-buffer`, `--temperature 45`, `--interlock-open`,
`--packet-errors`, `--mains` — so the watchdog, the backpressure path, the
arm-refusal path and reconnect can all be driven to completion before the
hardware arrives. Use `--list-lasercubes` to check discovery against the real
unit, and `--lasercube-dry-run` to pack and rate-control against real hardware
while transmitting nothing.

---

## 6. If you are changing the code

Anything touching the DAC stream — point generation, blanking, geometry,
brightness — must preserve these properties:

- **Closed curves, blanked travel moves, blank on exit.** Non-negotiable.
  No trading the closed-curve property for a blanked jump to make a shape
  easier to draw.
- **No parked beam.** Nothing may pile lit samples onto one coordinate:
  check any new shape or transform at its degenerate settings (edge-on,
  zero size, ratio 1:1, one side) for dwell, not just at the defaults.
- **Test in `--preview` before `--laser`.** In preview the full `SafeOutput`
  layer runs — arm gate, ceiling, watchdog — over a null backend, so bugs in
  it surface without hardware. The device backends themselves do not run;
  for the LaserCube path, use `scripts/lasercube_sim.py`.
- **The ceiling and the arm gate are the last transform before the device.**
  If you add an output transform, it goes *before* them, never after. Anything
  downstream of the ceiling can bypass it, which defeats the entire point.
- **Decide whether a transform is shared or DAC-only, and say why.** The
  mask and the monochrome-projector collapse are *shared*: they change what
  the beam actually shows, so the preview must agree. `hw_orient`, geometry
  correction and the ceiling are *DAC-only*: the monitor keeps showing what
  the content actually is. Dimming the preview would make the ceiling
  invisible rather than obvious.

`laser_output.py`, `helios.py` and `lasercube_output.py` are **written to be
dropped into other projects unchanged** ([PORTING.md](PORTING.md)). Keep them
importable standalone — numpy and stdlib only, nothing project-specific,
Python 3.9 compatible. A bug in `laser_output.py` is a safety bug everywhere
it has been copied.

The full requirements these implement are
[lasercubeoutput.md §4](lasercubeoutput.md).

---

## 7. Known gaps

Honest list, kept current:

- **None of this has been run against real hardware.** The Helios path was
  developed with no DAC attached; the LaserCube path was developed against a
  simulator. Verify per §5 before trusting either.
- **The LaserCube wire format is reverse-engineered.** Three independent
  sources agree on the point layout, but agreement is not the same as
  verification. The first frame on real hardware is the test. If it comes out
  as garbage, try `--lasercube-point-order rgbxy` — the field order is the
  most likely thing to be wrong, and it is a flag, not a code change.
- **LaserCube underrun behaviour is unknown** (§5 step 4). Until it is
  answered on hardware, assume the hazardous case.
- **The LaserCube has no power-limit command**, so the software ceiling is the
  only brightness limiter. A firmware cap would have been strictly better.
- **Y axis orientation is unconfirmed** for the LaserCube. If the image is
  upside down, use HW FLIP Y in Settings — it is live, no restart.
- **A frame larger than the device ring buffer will drop continuously.** Real
  buffers are ~6000 points and typical frames are 800, so this needs a
  deliberately odd configuration to hit, but the failure mode is a nearly
  static image rather than an error.
- **The ceiling persists.** Raise it once and it stays raised across restarts.
  If you share a rig, check the **MAX** badge in the header at the start of
  every session — and check whether the app was launched with
  `--max-brightness`.
- **Watchdog recovery re-lights an armed output** without asking (§3). A
  stall that clears itself mid-show puts the beam back exactly where the
  content says, at the current ceiling.
- **ILDA files can park the beam.** The dwell check is advisory and goes to
  the console, which a packaged build may not show.
- **No auth on the browser control surface.** The server listens on all
  interfaces (`0.0.0.0`), so anyone on your LAN can arm the laser. It is built
  for a trusted local network, not the internet — and the ARM button is
  reachable by every device on it.
