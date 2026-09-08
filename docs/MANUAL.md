# Manual

Everything the synth can do, panel by panel. For installation see
[INSTALL.md](INSTALL.md).

## Control

You drive the synth from three places at once — a browser control
surface, a MIDI controller, and the preview-window keyboard — and they
all stay in sync. The rest of this section is grouped by what you're
doing: the interfaces first, then shapes, modulation, colour, position
and geometry, the mask, the external sources (ILDA / vectoriser / text),
the pattern bank, and finally settings.

### Interfaces

**Browser UI** (`--web`, default port 8080, `--web-port` to change): a
single self-contained page — vanilla JS, no build step, no internet
needed. Laid out as visualiser + pattern bank on the left and three
columns of controls on the right, everything on screen at once at 1080p.
It collapses to fewer columns on narrow windows and stacks fully on
mobile. Live beam view with phosphor glow, shape buttons, a fader for
every parameter, bass/mid/high meters, and the ARM / brightness-ceiling /
BLANK controls in the top bar. The server binds to all interfaces, so a
phone or tablet on the same LAN works as a wireless control surface —
`http://<machine-ip>:8080`.
State echoes to the page at 5 Hz and frames stream as compact binary over
a WebSocket at 30 Hz. No auth — it's for your LAN, not the internet.

The startup message prints `http://laserx3:8080/`. That friendly name
resolves if you set the machine's hostname to `laserx3` (`hostnamectl
set-hostname laserx3`) or add it to `/etc/hosts`; otherwise just use
`http://localhost:8080/` on the same machine, or the machine's IP from
elsewhere on the LAN.

**Output monitor** (MONITOR button, top right): opens the beam view in its
own window — black background, no panels, scaled to fill and letterboxed
to the square scan field. Drag it to a second screen or projector and
double-click for fullscreen; the cursor hides itself when idle. It reads
the same frame stream as the control surface, so it shows exactly what the
laser is doing, mask included — handy as a stand-in display when there's
no laser to hand, or as an audience-facing view while you work the
controls on the main screen. It reconnects on its own if the synth
restarts, and clicking MONITOR again focuses the existing window rather
than opening another. The address is `/monitor`, so you can also just open
`http://localhost:8080/monitor` directly (or from another machine on the
LAN). The mask outline is deliberately not drawn here — it's an editing
aid, and this is meant to be a clean feed.

**MIDI**: every parameter, and the pause / stop-spin / blank / disarm
actions, can be mapped to a MIDI CC or note — there's no fixed mapping
to memorise. Open **Settings → MIDI mapping**, hit LEARN on any row, and
move a knob or press a pad to bind it; bindings persist in
`settings.json`. Rotary encoders get a per-row mode (absolute / relative
/ soft-takeover) — see [Settings](#settings). Pattern recall is mapped
the same way from the pattern bank (the ♪ button). On launch the synth
auto-connects to the first real controller (never the ALSA "Midi
Through" loopback); pick a specific port in Settings → MIDI input, or
pass `--midi <substring>` for a one-off session. The activity dot in the
header and Settings lights on any incoming message and the modal shows a
running count, so "working but unmapped" and "no data at all" look
different.

**Keyboard** (preview window): `1–9` shapes, `←/→` ratio A, `↑/↓` ratio
B, `[`/`]` size, `m` morph, `s` spin, `h` hue, `a` audio amount, `d`/`D`
copies up/down, `c` mono, `f`/`g` flip X/Y, `SPACE` blank, `.` disarm
the laser (`shift-.` arms it), `ESC`/`q` quit (blanks the laser on the
way out).

### Shapes

Ten generated shapes plus four external sources (ILDA, vectoriser,
text, and a hand-drawn custom polygon — covered under *Sources* below).
The maths shapes — lissajous,
rose, hypotrochoid, wave, harmonograph, polygon, scope, superformula,
maurer and knot — share the
ratio A / ratio B / morph controls, which each shape interprets in its
own way.

**Polygon**: ratio A sets the side count — 1 draws a single line (morph
tilts it from horizontal toward vertical), 2 a line through the centre,
then 3 triangle, 4 square, 6 hexagon, up to 12. Morph rounds the
corners, all the way to a perfect circle at 1.0. Ratio B is a star skip:
2 on a 5-sided polygon draws a pentagram, 7-sided with skip 3 a
heptagram, and so on. Points are spaced by arc length, so edges scan at
even brightness.

**Wave**: draws a classic oscillator waveform across the field — sine,
triangle, saw, square or pulse, chosen in the Wave shape panel (column
3). Ratio A sets the number of cycles; morph controls amplitude (or duty
cycle, for pulse).

**Scope** (Audio panel, `scope` shape only): an audio visualiser with
five modes, selectable by button — *waveform* (classic oscilloscope
trace), *vu meter* (level bar that grows with loudness), *spectrum*
(bass/mid/high skyline from the FFT), *radial* (waveform wrapped around a
circle), and *xy* (Lissajous plot of the waveform against a delayed copy
of itself). Each falls back to a calm idle shape when no audio is
present.

**Superformula**: one equation that morphs continuously through circles,
polygons, stars, flowers and blobs. Ratio A is the symmetry (how many
lobes), ratio B and morph shape the lobes between fat and spiky. It
rewards being modulated rather than set: put the oscillator or an audio
band on morph and it walks the whole family.

**Maurer**: walks a rose curve in fixed degree steps and joins the
positions with straight chords, which interfere into a dense moiré
lattice. Ratio A sets the petal count. Ratio B picks the lattice and, with
it, the density — it runs from 20 chords at 1 up to 360 at 11 and 12.
That matters on real hardware: at the default 800 points a 20-chord
lattice gets 40 points per chord and draws crisply on anything, while the
360-chord version gets barely two, which is less time than the galvos need
to cross the field, so it comes out soft and dim. If you want the dense
ones sharp, raise the point count (Settings, or the per-pattern override)
and accept the lower frame rate.

### Effects

Three effects in the Effects panel (column 2). All are off at their
defaults, and all apply to *every* shape and source, ILDA and text
included.

**Ripple**: pushes the curve in and out along its own edge. *ripples*
sets how many waves travel around it, *ripple spd* how fast they move.
Small amounts breathe; large amounts turn a circle into a flower.

**Tilt / tumble / perspective**: rotates the figure in 3D. *tilt x* and
*tilt y* aim it (0.5 is straight on), *tumble* rotates it continuously,
*perspective* controls how strongly the far side shrinks. Flat shapes
read as a card turning; the *knot* shape reads as a solid object.

**Comet**: a bright head that travels along the path, leaving the rest
dim — the beam keeps scanning the whole figure, so what you get is a
chase rather than a shortened stroke. *comet* sets how much of the
figure falls away behind the head, *comet spd* the travel speed
(0.5 is stationary, below it runs backwards).

Each of the Effects, Duplicator, Audio and Oscillator panels has a small
**on/off switch** in the top right of its heading. Switching a panel off
bypasses that whole stage while leaving its faders exactly where you left
them, so you can drop the duplicator or the oscillator out of the picture
and bring it back without rebuilding the setup. A bypassed panel dims its
controls so it is obvious at a glance that they are not reaching the beam.
The switch drives the same parameter the render loop reads, so MIDI and
the preview keyboard stay in step with it. (Audio's switch is the AUDIO
STOP control under a different name — one kill switch, two places to
reach it.)

**RESET ALL**, above the Oscillator panel, puts every parameter back to
its default. It asks twice: the first press arms it, the second does it,
and it disarms itself after a few seconds. Installed sources — text, an
ILDA file, the custom polygon — are left alone; the reset is for settings,
not for content you loaded.

### Modulation

Three ways to move parameters without touching them: the oscillator
(automatic), audio reactivity (sound-driven), and sweep (positional,
under *Position & geometry*).

**Oscillator (LFO)** (top of column 3): a low-frequency oscillator that
sweeps one parameter over time, for hands-free movement. Pick a
**target** (morph, size, hue, ratio A/B, spin, position, dup spread,
dotify, ripple, tilt y, comet or falloff) and a **wave** (sine, triangle, square, saw, or random
sample-and-hold), then set **rate**, **depth** and **dropoff**. The LFO
moves the target *around its current fader value* rather than
overwriting it, so the fader still sets the centre and the oscillator
swings around it — depth 0 switches it off. Dropoff decays the swing
across each cycle, so the movement settles toward the base value instead
of oscillating evenly. It's a normal parameter, so it's mappable and
saved in patterns — you can store a look that breathes on its own.

**Audio reactivity**: capture comes from the default input device (mic,
or a loopback/monitor source — in `pavucontrol` set the recording source
to "Monitor of …" to react to whatever's playing). Levels are adaptively
normalised, so it works without gain fiddling. Each frequency band —
bass, mid, high — has a **destination dropdown** in the Audio panel
selecting which parameter it drives. Defaults are bass→size, mid→morph,
high→brightness, but you can point any band at size, morph, brightness,
hue, spin, dup spread, dotify, X/Y position, ratio A, ripple, comet,
perspective or falloff, or *off*. Note the modulation only pushes a value
*up* from where its fader sits, so a destination whose fader is already at
maximum has nowhere to go — falloff in particular defaults to 1.0, so pull
it down before routing a band at it.
Multiple bands can target the same parameter (they add). Modulation is
additive around the current fader value, so your faders still set the
baseline, and routings are saved in patterns. **AUDIO STOP** (Audio
panel) is a master kill switch: one click freezes all band modulation
*and* drops the scope shapes to idle. The **audio amount** fader scales
the overall depth.

### Colour & beam

**Hue** (Colour panel): a strip of colour swatches sets the base hue —
click one to jump straight to that colour. Hue is still a normal 0–1
parameter under the hood, so it remains MIDI-mappable (a CC sweeps
continuously through the wheel) and is captured in patterns; the
swatches are just a faster way to pick by eye than a fader.

**Rainbow / mono**: by default a rainbow gradient spans the whole figure
(and all duplicator copies, each a different slice). The MONO toggle
(Colour panel) switches to a single colour set by the hue swatches; the
hue cycle fader still animates it, so a slow cycle gives a gently
colour-shifting single beam. Good for single-colour lasers and cleaner
looks.

**Dotify** (Colour panel): breaks the beam into dots instead of a
continuous line — 0 is solid, full is 1-in-8 points lit. Sharp dots at
the cost of brightness (fewer lit points = dimmer; nudge brightness up to
compensate). Dots sit at fixed positions along the curve, so they rotate
and morph with the shape, and combine with the duplicator.

**Duplicator**: copies (1–6) repeat the figure around a ring. MIRROR X /
MIRROR Y reflect every second copy for kaleidoscope-style symmetry — 2
copies + mirror X gives the figure and its mirror facing each other.
Spread sets the ring radius, falloff shrinks each successive copy
(echo-style; full right = all equal), orbit rotates the whole ring
(bipolar — centre is stopped). Copies are joined by blanked travel moves,
so there are no bridge lines. The point budget is shared across copies,
so more copies = fewer points each; with 6 copies of a detailed shape,
raise `--points`.

### Position & geometry

**Rotate** (Geometry panel): a static rotation offset (0–360°) added on
top of the continuous spin, for setting a figure at a fixed angle.
Switching to a source shape (text, ILDA or vector) defaults *spin* to
stopped, since those are usually meant to sit still — use rotate to
angle them.

**Size X / Y** (Geometry panel): independent X and Y scale with a 🔗 LINK
SIZE toggle. Linked (the default), the two faders move together and stay
equal; unlink to stretch a shape into an ellipse, a wide line, or any
aspect ratio. Both axes and the link state are saved in patterns; the
audio/LFO "size" destination drives the X axis (and Y too when linked).

**Position & sweep** (Position panel): X/Y position faders offset the
whole figure (0.5 = centred; parts pushed past the edge clamp at the scan
limits). Sweep auto-wanders the centre — and X and Y are **independent**,
each with its own depth and speed fader, so you can set a slow
Lissajous-style drift with different rates per axis, or sweep only one
axis. Manual position and sweep add together.

**Flip X / Flip Y** (Position panel): mirror the entire output, position
and sweep included — for projector orientation, rear projection, or
bounce mirrors. These are artistic flips that affect preview and laser
together (distinct from the hardware orientation flip below).

**Projection geometry** (Settings → Projection geometry): corrects
keystone and lens distortion on the **laser output only** — the preview
is deliberately left uncorrected so it stays a true reference. Click SHOW
TEST PATTERN to project an alignment grid (white border + grid, cyan
centre cross, red corner ticks), then drag the four corners of the editor
to match your surface — a full perspective (homography) warp, so it
handles keystone, tilt and trapezoid, not just scaling. The pincushion /
barrel slider adds a radial term for lens-style bulge (positive =
pincushion, negative = barrel). RESET GEOMETRY clears it. All of it
persists in `settings.json` and applies after the orientation flips, in
projector space.

**Projector orientation**: the DAC output mirrors X by default so the
projected image matches the preview (this also makes spin direction agree
between wall and screen). If your projector is mounted the other way,
launch with `--no-hw-flip-x`; `--hw-flip-y` is there too. This is a
hardware correction on the DAC stream only.

### Mask

**Mask** (panel under Text, collapsed by default — click the header to
open): draw polygons over the live beam and the
output is blanked outside them — on the laser and the monitor **both**,
unlike projection geometry, which is laser-only. Use it to keep light off
a window or a doorway, to fit the show to an irregular surface, or to cut
the audience side out of a wall wash.

Hit **DRAW…**, then click on the scope to lay down points; the shape
closes back to the first point and updates the laser live as you go.
**SELECT** drags a point, **DELETE** removes one, **UNDO** drops the last.
**NEW SHAPE** starts another polygon — a mask can hold up to 8 shapes (64
points each), and anything inside *any* of them counts as inside.
**INVERT** flips the whole thing, turning keep-inside into block-inside so
you can knock two windows out of an otherwise full field. **DONE** leaves
edit mode; the outline stays on the scope as a dim dashed guide whenever
the mask is on.

Name a mask and hit SAVE to keep it — saved masks appear as chips below
and reload with a click, so a venue's mask survives between sessions
(`masks.json`). Masks are independent of the pattern bank: the mask is
about the room, not the visual, so it stays put as you switch patterns.
The live mask (shapes, invert, on/off) persists in `settings.json` and
comes back on restart.

Two things worth knowing. The mask is applied to the shared frame before
the projection-geometry warp, so it's defined in the same space the
monitor shows — align the geometry first, then draw the mask, and the
boundary lands on the wall where the preview said it would. Turning on
the alignment test pattern (Settings → Projection geometry → SHOW TEST
PATTERN) while drawing is the practical way to line a mask up to a real
surface.

> **This is a blanking mask, not a safety interlock.** The galvos still
> traverse masked areas with the beam off; a scanner fault or a lost frame
> is not covered by it. It is a projection-mapping tool. Keep using proper
> mounting, aiming and power discipline for anything safety-critical.

### Sources: ILDA, vectoriser, text, custom shape

These three feed the render pipeline instead of a generated shape — and
every effect above (spin, size, position, colour, dotify, duplicator,
sweep, flips) still composes on top.

**ILDA import** (ILDA panel, column 3): plays standard `.ild` laser files
— all point formats (2D/3D, indexed and true colour, embedded palettes;
files without a palette get an approximation of the ILDA 64-colour
palette). Pick a file from the dropdown (this switches the shape to
`ilda`), drop a `.ild` onto the page, or use UPLOAD — files land in the
`ilda/` folder, so you can also just copy them there. The **playback**
slider runs animations from freeze (0) to 24 fps; LOOP / PING-PONG /
SINGLE set the traversal. File colours are used as authored (MONO
overrides them). Saved patterns remember which ILDA file they used and
restore it on load, including MIDI-triggered loads. Safety note: unlike
the synth shapes, ILDA files can contain beam dwells — the importer scans
for long runs of lit points at one coordinate and prints a warning; treat
warned files with care at full power.

**Vectoriser** (Vectoriser panel, column 3): traces the edges of images
or live webcam video and scans them as laser paths, coloured by sampling
the source — point a camera at someone and the beam draws their outline
in their own colours. Two sources: drop/upload an image, or pick a camera
from the dropdown. Pipeline: brightness/contrast → blur → Canny edge
detection → contour simplification → paths ordered to minimise beam
travel. The four filter faders shape it live: **brightness**/**contrast**
precondition the image, **threshold** sets edge sensitivity, **detail**
trades fidelity for scanability (start low for camera mode). Filter
settings are saved in patterns; the image/camera source itself isn't.
Requires `opencv-python-headless`; without it the panel just reports the
missing dependency. If the projected image flickers, lower detail, raise
threshold, or raise `--pps`.

**Text** (block under the visualiser): type a string and it's projected
as laser text in one of three single-stroke vector fonts — plain, script
(italic), or bold (outline). The fonts are Hershey-style single strokes
(no fills), so they scan efficiently. Macron vowels for te reo Māori are
supported (ā ē ī ō ū); the **ā** button adds a macron to the last vowel
typed. Selecting text switches the shape to `text`.

The panel is collapsed by default — click the header to open it, or just
hit the **text** shape button, which opens the panel and puts the cursor
in the box for you.

**Custom shape** (Custom Shape panel, column 3): click EDIT POINTS… to
open a point editor and draw your own polygon — straight edges connect
the points in the order you click them, closing back to the first one.
ADD mode places a new point on each click; SELECT lets you click-and-drag
an existing point to reposition it; DELETE removes a clicked point.
UNDO LAST and CLEAR ALL round out editing. USE SHAPE applies the points
and switches to the `custom` shape (CLOSE discards the edit instead).
Points are capped at 64 and saved/restored with the pattern.

### Pattern bank

**Saving & loading** (left column, beside the visualiser): dial in a
look, type a name, hit SAVE (or press Enter). Click a pattern to load it
— this also puts its name in the field, so the edit workflow is load →
tweak → SAVE to overwrite. The × on each pattern deletes it (with
confirmation). Patterns capture every parameter and live in
`patterns.json` next to the scripts: plain JSON, atomic writes, safe to
hand-edit or keep in git. A few starter patterns ship with the project.

**Random pattern**: the 🎲 RANDOM PATTERN button invents a complete
pattern from all synth options except ILDA and vector (which need
external files) — random shape, ratios, colours, duplicator, oscillator
and audio routing, kept within musical ranges. It loads immediately
(respecting the transition mode); save it if you like it.

**Transitions**: the INSTANT / XFADE buttons set how pattern loads
behave. XFADE glides every parameter to the target over ~2 s with eased
motion — hue takes the short way around the wheel; discrete settings
(shape, mono, flips) switch at the midpoint. Grabbing a fader or CC
mid-fade takes that parameter out of the transition, so you always win.
Applies to browser clicks and MIDI-triggered patterns alike.

**MIDI learn**: the ♪ button on each pattern arms learn — hit a key on
your controller and that note now loads the pattern from anywhere. The
button shows the bound note (e.g. D2); click to re-learn, shift-click to
clear. Pattern bindings take priority over the built-in shape-select
notes and are stored with the pattern in `patterns.json`.

**Per-pattern PPS / points** (bottom of column 3): optional per-pattern
overrides for scan rate and point count. Leave them blank to use the
system settings; enter a value to pin it to the next pattern you save.
Stored with the pattern and restored on load, cleared automatically by
patterns that don't set them, excluded from the random generator, and
intentionally not MIDI-mapped (they're setup values, not performance
controls). Useful when one pattern needs a slower scan for a complex
figure while the rest run fast.

### Live actions

**Pause / Stop spin** (Geometry panel): PAUSE freezes every time-driven
motion — spin, sweep, orbit, hue cycling, ILDA playback and in-flight
crossfades — while faders stay live, so you can pose a frame and adjust
it. STOP SPIN zeroes the spin rate and resets the figure upright. Both,
plus **BLANK**, are mappable to MIDI buttons (they fire on the press and
ignore the release, so a momentary pad toggles cleanly).

### Output safety: ARM and the brightness ceiling

Two controls sit together in the header, and they are the only things
standing between the render loop and a live beam.

**ARM / DISARM** is the output gate. The app always starts **disarmed**,
and nothing is emitted until you arm it — this is never remembered
between runs, however the last session ended. Arming asks for
confirmation; disarming never does, and takes effect on the very next
frame with no crossfade. You can also disarm with `.` in the preview
window (`shift-.` arms) or from a MIDI pad via the **DISARM laser**
action in the mapping table. The MIDI action is deliberately one-way: a
stray CC should never be able to arm a laser.

Note that "disarmed" does not mean the DAC goes quiet — it means it is
actively streaming darkness. A Helios that simply stops being fed repeats
its last frame forever, so silence would be the *less* safe state.

**MAX** is a hard ceiling on output brightness, applied at the very last
step before the DAC — after the scene, the mask, the geometry warp and
every other transform. Nothing upstream can exceed it: not a pattern
load, not audio modulation, not a MIDI knob. It defaults to **5%** and
persists in `settings.json`. It is separate from the `brightness` fader
in Colour & beam, which stays a purely creative control.

The header shows the ceiling but does **not** let you change it — it
turns amber above 5%, so a raised ceiling is visible at a glance without
being one stray click away from moving. Changing it lives in **Settings →
Brightness ceiling**, and raising it above 5% asks for confirmation.
**SET 5% (BRING-UP)** snaps it back.

On the LaserCube this is the only brightness limiter that exists — the
network protocol has no power-limit command, so there is no firmware cap
sitting downstream of a host-side bug.

At 5% on an 8-bit colour channel you have about 13 levels to play with —
plenty for aiming, coarse for content.

> **The ceiling is a creative limiter, not a safety interlock.** Neither
> it nor the ARM gate can help you against a crash, a driver bug or a
> stuck buffer. The key switch, aperture shutter, interlock loop, Remote
> Stop, proper eyewear and a controlled beam path are the actual safety
> layer, and they are mandatory regardless of what this software does.
> **[SAFETY.md](SAFETY.md)** covers all of this properly, including the
> operating procedure and the hardware bring-up checklist.

Behind these, and needing no attention from you: the output blanks on
every exit path — Ctrl-C, `kill`, an unhandled exception, or closing the
window — and a watchdog thread blanks the beam if the render loop ever
stops feeding it.

### Choosing an output device

**Settings → Laser output** picks where the beam goes: **none**, **Helios
DAC (USB)**, or **LaserCube (network)**. You can switch live, without
restarting, and the choice is remembered.

**Switching always disarms.** Arming is a statement about one particular
projector, so it is never carried across a device change — re-arm
deliberately, every time. If the new device can't be opened, output falls
back to none rather than leaving a dead device selected.

A remembered choice that fails to open at startup falls back to none with
a message. An explicit `--output` or `--laser` on the command line does
not: if you named a device, failing to open it is fatal, because starting
silently with no output would let you believe a laser is live when
nothing is connected.

**TEST DEVICE** queries the attached device and shows what it reports
about itself. It emits nothing, so it is safe to press at any time. A
LaserCube reports firmware, serial, model, connection type, temperature
and thermal warnings, interlock state, output state, power source, scan
rate and its maximum, buffer occupancy and its own packet-error count,
alongside our frame sent/dropped/error counters. A Helios reports device
count and link status — it has no temperature, interlock or power
telemetry to give, and the panel says so rather than showing blanks.

The LaserCube runs over Ethernet or WiFi; use **Ethernet**. Buffer levels
are unstable over WiFi and the app warns if it finds itself on it.
`--list-lasercubes` prints every unit it can find on the network.

### Settings

**Settings** (button in the header): a modal with runtime engine settings
— points per frame, scan rate (pps), crossfade time, and the
projector-orientation flips, all adjustable live without restarting —
plus projection geometry and the custom **MIDI mapping** table. Every
parameter is listed with its current binding; hit LEARN and move a
control to bind it. Custom bindings are highlighted, steal the CC from
whatever had it, and × returns a row to its default.

Each fader row also has an **encoder mode** for how its CC is
interpreted — important for rotary encoders:
- *abs* (default): value 0–127 maps straight to the range. Fine for real
  faders; with endless encoders the value jumps when you load a pattern
  and then touch the knob.
- *rel*: the encoder sends deltas, not positions — each turn nudges from
  wherever the value sits, so pattern loads never fight the knob.
  Auto-detects the two common signed encodings. Use this if your
  controller can send relative / "endless" output.
- *catch* (soft takeover): for absolute encoders that can't do relative.
  After a pattern sets a value, the knob is ignored until you turn it
  *past* that value, then it catches and tracks smoothly — no jump.
  Re-arms on every pattern load.

Everything here persists in `settings.json` — saved settings win over CLI
defaults on the next launch, so the Settings page is the durable config
and CLI flags seed the first run.

**About** (button in the header): shows the contents of `about.md`
rendered as Markdown, light grey on black — edit that file to keep your
own notes, cheat-sheets or credits with the synth.

## How it talks to the DAC

Classic Helios pipeline: `OpenDevices()` → poll `GetStatus()` until 1 →
`WriteFrame(dac, pps, flags, points, n)` with 12-bit X/Y + 8-bit RGBI
points. The DAC is double-buffered, so `write_frame()` blocking on
`GetStatus` naturally paces the render loop to the point clock — no
timers needed when the laser is running.

Everything bound for the DAC passes through `SafeOutput` in
`laser_output.py`, which owns the ARM gate, the brightness ceiling, the
watchdog and blanking on exit. `WriteFrame()` without
`HELIOS_FLAG_SINGLE_MODE` *repeats* its frame until the next one arrives,
which is why blanking writes a dark frame rather than merely calling
`Stop()` — a stopped-but-unblanked DAC sits there replaying whatever was
last sent.

`laser_output.py` and `helios.py` are written to be copied verbatim into
the sibling laser projects, so they depend on nothing but numpy and the
standard library.

## Project layout

The Python modules and their data files all sit in the repo root, flat and
next to each other. That's deliberate, not untidy: several of them find
their data with `os.path.dirname(__file__)` (`about.md`, `patterns.json`,
`static/`, and the Helios shared library that `helios.py` loads), and the
PyInstaller bundle flattens to the same layout. Docs and helper scripts
live in `docs/` and `scripts/`.

- `laserx3.py` — main app (render loop, MIDI, audio, preview)
- `laser_output.py` — output safety layer (ARM gate, brightness ceiling,
  watchdog, blank-on-exit); shared verbatim with the sibling projects
- `helios.py` — Helios DAC backend (USB, ctypes over libHeliosDacAPI)
- `lasercube_output.py` — LaserCube backend (network, pure Python UDP);
  `scripts/lasercube_sim.py` is a fake device for testing without hardware
- `webui.py` + `static/index.html` — browser control surface
- `static/monitor.html` — chrome-free output monitor page (`/monitor`)
- `patterns.py` + `patterns.json` — pattern bank storage (a few starter
  patterns included)
- `ilda.py` + `ilda/` — ILDA (.ild) import: parser and file library
  (an animated sample is included)
- `vectorise.py` — image/webcam vectoriser (needs opencv-python-headless)
- `text.py` — single-stroke vector font for the text shape
- `settings.py` + `settings.json` — persistent settings and custom MIDI
  CC map (created on first change)
- `geometry.py` — projection geometry correction (corner-pin + pincushion)
  and the alignment test pattern
- `mask.py` — polygon blanking mask applied to laser and monitor alike
- `masks.py` + `masks.json` — saved mask library (created on first save;
  venue-specific, so it's gitignored)
- `about.md` — free-text About page shown in the ABOUT modal (edit freely)
- `shapes.py` — shape oscillator engine
- `helios.py` — ctypes wrapper for the Helios SDK
- `libHeliosDacAPI.so` — Helios SDK shared library, built for x86-64
  Linux (Ubuntu 24.04, libusb-1.0). Must sit beside `helios.py`, which
  loads it by path. Rebuild instructions in
  [INSTALL.md](INSTALL.md#rebuilding-libheliosdacapiso-if-the-prebuilt-one-doesnt-load).
- `pyinstaller.spec` + `.github/workflows/build.yml` — builds standalone
  executables for Ubuntu, Windows and macOS (see
  [INSTALL.md](INSTALL.md#prebuilt-executables))
- `docs/` — this manual, `INSTALL.md`, third-party licences, and the
  interface snapshot / app icon
- `scripts/` — `heliosdac.rules` (udev rule for non-root USB access) and
  `build_helios_lib.sh`
