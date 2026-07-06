# Laser! Laser Laser!

![version](https://img.shields.io/badge/version-1.0.0-blueviolet)
![license](https://img.shields.io/badge/license-MIT-green)
![platform](https://img.shields.io/badge/platform-Ubuntu%20%7C%20Windows-informational)

Realtime vector visuals synthesizer for the Helios Laser DAC. Draw
lissajous figures, rose curves, hypotrochoids, waveforms, harmonographs,
polygons/stars (line → polygon → circle) and a live audio scope — or play
ILDA files and vectorise images and webcam video into laser art. Drive it
all from a browser control surface, MIDI, or the keyboard, with an
oscillator, routable audio reactivity, a pattern bank, crossfades, and
projection geometry correction.

Runs on Ubuntu (Windows works too, see below). No build step; vanilla
Python + numpy, with a thin ctypes wrapper over the official Helios SDK.

## ⚠️ Laser safety first

Point generation bugs can park the beam. This synth only draws closed
curves (no static points), blanks on exit, and defaults to preview-only —
but *you* are the safety system. Never run at full power into an
unscanned or unknown state, keep beam paths above head height or
terminated, and test everything in `--preview` first.

## Files

- `lasersynth.py` — main app (render loop, MIDI, audio, preview)
- `webui.py` + `static/index.html` — browser control surface
- `patterns.py` + `patterns.json` — pattern bank storage (a few starter
  patterns included)
- `ilda.py` + `ilda/` — ILDA (.ild) import: parser and file library
  (an animated sample is included)
- `vectorise.py` — image/webcam vectoriser (needs opencv-python-headless)
- `settings.py` + `settings.json` — persistent settings and custom MIDI
  CC map (created on first change)
- `geometry.py` — projection geometry correction (corner-pin + pincushion)
  and the alignment test pattern
- `about.md` — free-text About page shown in the ABOUT modal (edit freely)
- `icon.png` — the app icon (also embedded as the favicon)
- `shapes.py` — shape oscillator engine
- `helios.py` — ctypes wrapper for the Helios SDK
- `libHeliosDacAPI.so` — Helios SDK shared library, built for x86-64
  Linux (Ubuntu 24.04, libusb-1.0). Rebuild instructions below.
- `heliosdac.rules` — udev rule for non-root USB access

## Ubuntu setup

```bash
sudo apt install libusb-1.0-0 python3-pip
pip install numpy mido python-rtmidi sounddevice pygame aiohttp
pip install opencv-python-headless   # optional: image/webcam vectoriser

# USB permissions (once):
sudo cp heliosdac.rules /etc/udev/rules.d/011_heliosdac.rules
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
cp libHeliosDacAPI.so /path/to/lasersynth/
```

(Bonus: this build includes the SDK's IDN network-DAC support, so the
same wrapper will drive an OpenIDN adapter later if you ever want one.)

## Windows

Drop `HeliosLaserDAC.dll` and `libusb-1.0.dll` from the SDK repo
(`sdk/cpp/shared_library` and `sdk/cpp/libusb_bin`) next to the scripts.
`helios.py` picks the DLL automatically on Windows.

## Running

```bash
python3 lasersynth.py --preview             # screen only — start here
python3 lasersynth.py --web                 # browser UI at localhost:8080
python3 lasersynth.py --laser --web         # laser + browser control
python3 lasersynth.py --laser --preview     # laser + pygame mirror
python3 lasersynth.py --list-midi           # find your controller
python3 lasersynth.py --laser --midi "MPK"  # match MIDI port by substring
```

Modes combine freely (`--laser --web --preview` all at once is fine).

Options: `--points N` (default 800) and `--pps N` (default 30000).
Frame rate ≈ pps/points, so 800 pts @ 30 kpps ≈ 37 fps. Fewer points =
faster/smoother motion but coarser curves; the Helios tops out at 65 kpps
if your scanners can take it.

## Control

**Browser UI** (`--web`, default port 8080, `--web-port` to change):
laid out as visualiser + pattern bank on the left and two columns of
controls on the right — everything on screen at once at 1080p, no
scrolling. Collapses to one control column on narrow windows and stacks
fully on mobile.
single self-contained page, vanilla JS, no internet needed. Live beam
view with phosphor glow, shape buttons, faders for every parameter,
bass/mid/high meters, and a big BLANK button. It binds to all
interfaces, so a phone or tablet on the same LAN works as a wireless
control surface — `http://<machine-ip>:8080`. MIDI, keyboard and
browser stay in sync (state echoes to the page at 5 Hz); frames stream
as compact binary over a WebSocket at 30 Hz. No auth — it's for your
LAN, not the internet.

**MIDI port selection**: on launch the synth auto-connects to the
first *real* controller — ALSA's ever-present "Midi Through" loopback
is never auto-picked (it silently swallows everything; if MIDI ever
seems dead, that's the first suspect). Pick a different port in
Settings → MIDI input: the dropdown lists every input port live, the
choice persists in `settings.json`, and stale ALSA client numbers from
reboots/replugs are matched by device name. The green activity dot
(header status line and Settings) lights on *any* incoming message —
mapped or not — and the modal shows a running message count, so
"controller working but nothing mapped" and "no data arriving at all"
look different. `--midi <substring>` on the CLI still overrides
everything for one-off sessions.

**MIDI** (any channel):

| CC | Parameter | | Note | Shape |
|----|-----------|-|------|-------|
| 1 | ratio A (1–12) | | 36 (C1) | lissajous |
| 2 | ratio B (1–12) | | 37 | rose |
| 3 | morph | | 38 | hypotrochoid |
| 4 | spin | | 39* | wave (then harmonograph…) |
| 5 | size | | 39 | harmonograph |
| 6 | hue | | 40 | polygon |
| 7 | hue cycle speed | | | |
| 8 | audio amount | | | |
| 9 | master brightness | | | |
| 10 | X position | | | |
| 11 | Y position | | | |
| 12 | sweep depth | | | |
| 13 | sweep speed | | | |
| 14 | copies (1–6) | | | |
| 15 | duplicator spread | | | |
| 16 | duplicator falloff | | | |
| 17 | duplicator orbit | | | |
| 18 | mono (≥64 on) | | | |
| 19 | flip X (≥64 on) | | | |
| 20 | flip Y (≥64 on) | | | |
| 21 | dotify | | | |
| 22 | ILDA playback rate | | | |
| 23 | vectoriser brightness | | | |
| 24 | vectoriser contrast | | | |
| 25 | vectoriser threshold | | | |
| 26 | vectoriser detail | | | |
| 27 | dup mirror X (≥64 on) | | | |
| 28 | dup mirror Y (≥64 on) | | | |
| 29 | ILDA mode (0–2) | | | |
| 30 | scope mode (0–4) | | | |
| 31 | audio stop (≥64 on) | | | |
| 32 | LFO target (0–9) | | | |
| 33 | LFO wave (0–4) | | | |
| 34 | LFO rate | | | |
| 35 | LFO depth | | | |
| 36 | LFO dropoff | | | |
| 37 | sweep X depth | | | |
| 38 | sweep Y depth | | | |
| 39 | sweep X speed | | | |
| 40 | sweep Y speed | | | |
| 41 | wave type (0–4) | | | |
| 42 | audio bass dest (0–10) | | | |
| 43 | audio mid dest (0–10) | | | |
| 44 | audio high dest (0–10) | | | |
| 45 | size Y | | | |
| 46 | size link (≥64 on) | | | |

Remap by editing `CC_MAP` at the top of `lasersynth.py`.

**Keyboard** (preview window): `1–6` shapes, `←/→` ratio A, `↑/↓` ratio B,
`[`/`]` size, `m` morph, `s` spin, `h` hue, `a` audio amount, `d`/`D`
copies up/down, `c` mono, `f`/`g` flip X/Y, `SPACE` blank, `ESC`/`q`
quit (blanks the laser).

**Polygon shape**: ratio A sets the side count — 1 draws a single line
(morph tilts it from horizontal toward vertical), 2 a line through the
centre, then 3 triangle, 4 square, 6 hexagon, up to 12. Morph rounds the corners, all the way to a perfect
circle at 1.0. Ratio B is a star skip: 2 on a 5-sided polygon draws a
pentagram, 7-sided with skip 3 a heptagram, and so on. Points are spaced
by arc length, so edges scan at even brightness.

**Duplicator**: copies (1–6) repeats the figure around a ring.
MIRROR X / MIRROR Y reflect every second copy, turning duplicates into
kaleidoscope-style reflections — 2 copies + mirror X gives the figure
and its mirror image facing each other. Spread
sets the ring radius, falloff shrinks each successive copy (echo-style;
full right = all equal), orbit rotates the whole ring (bipolar — centre
is stopped). Copies are joined by blanked travel moves, so the beam is
off between them — no bridge lines. The total point budget is shared
across copies, so more copies = fewer points each; with 6 copies of a
detailed shape, consider raising `--points`. The rainbow gradient spans
all copies (each gets a different slice); mono makes them uniform.

**Dotify** (Colour panel): breaks the beam into dots instead of a
continuous line — 0 is solid, full is 1-in-8 points lit, giving sharp
dots at the cost of overall brightness (fewer lit points = dimmer
figure; nudge brightness up to compensate). Dots sit at fixed positions
along the curve, so they rotate and morph with the shape. Combines with
the duplicator.

**Mono**: the MONO toggle (Colour panel) switches from the rainbow
gradient to a single colour set by the hue fader — hue cycle still
animates it, so a slow cycle gives a slowly colour-shifting single beam.
Handy for single-colour lasers and for cleaner projection looks.

**Projection geometry** (Settings → Projection geometry): corrects
keystone and lens distortion on the **laser output only** — the preview
is deliberately left uncorrected so it stays a true reference. Click
SHOW TEST PATTERN to project an alignment grid (white border + grid,
cyan centre cross, red corner ticks), then drag the four corners of the
editor to match your physical surface — this is a full perspective
(homography) warp, so it handles keystone, tilt and trapezoid, not just
scaling. The pincushion / barrel slider adds a radial term on top for
lens-style bulge (positive = pincushion, negative = barrel). RESET
GEOMETRY clears everything. All of it persists in `settings.json` and
applies after the orientation flips, i.e. in projector space.

**Projector orientation**: the DAC output mirrors X by default so the
projected image matches the preview (this also makes spin direction
agree between wall and screen — a mirror reverses apparent rotation).
If your projector is mounted the other way, launch with
`--no-hw-flip-x`; `--hw-flip-y` is there too. This is a hardware
correction on the DAC stream only — the FLIP X/Y buttons below remain
artistic controls that flip preview and laser together.

**Flip X / Flip Y** (Position panel): mirrors the entire output,
position and sweep included — for projector orientation, rear
projection, or bounce mirrors.

**Position & sweep**: X/Y position faders offset the whole figure
(0.5 = centred; parts pushed past the edge clamp at the scan limits).
Sweep auto-wanders the centre on two incommensurate sine waves — a slow
Lissajous drift that never quite repeats — with depth and speed faders.
Manual position and sweep add together.

**Vectoriser** (Vectoriser panel, column 1): traces the edges of images
or live webcam video and scans them as laser paths, coloured by
sampling the source — point a camera at someone and the beam draws
their outline in their own colours. Two sources: drop/upload an image
(IMAGE button or drag a png/jpg/webp/bmp/gif onto the page), or pick a
camera from the dropdown — it lists every V4L2 device (built-in and USB
webcams) by name; capture runs in its own thread at ~15 fps so the scan
never stutters. Pipeline: brightness/contrast → blur → Canny edge
detection → contour simplification → paths ordered to minimise beam
travel, joined by blanked bridges. The four filter faders shape it
live: **brightness**/**contrast** precondition the image, **threshold**
sets edge sensitivity (higher = fewer edges), **detail** trades
fidelity for scanability (lower = more blur, more simplification,
fewer paths — start low for camera mode). Spin, size, position, mono,
dotify and the duplicator all compose on top. Filter settings are
patterns-compatible (CC 23–26); the image/camera source itself isn't
stored in patterns. Requires `opencv-python-headless`; without it the
panel just reports the missing dependency. Realtime note: complex
scenes vectorise into many paths, and every blanked hop between paths
costs scan time — if the projected image flickers, lower detail, raise
threshold, or raise `--pps`.

**ILDA import** (ILDA panel, column 1): plays standard `.ild` laser
files — all point formats (2D/3D, indexed and true colour, embedded
palettes; files without a palette get an approximation of the ILDA
standard 64-colour palette). Pick a file from the dropdown (this
switches the shape to `ilda`), drop a `.ild` anywhere onto the page, or
use UPLOAD — files land in the `ilda/` folder next to the scripts, so
you can also just copy them there. The **playback** slider runs
animations from freeze (0) up to 24 fps, and LOOP / PING-PONG / SINGLE
set the traversal: loop wraps, ping-pong bounces end to end, single
plays once and holds the last frame (re-select the file to replay); frames are resampled to the
point budget for stable scan timing. File colours are used as authored;
MONO overrides them, and brightness, dotify, spin, size, position,
sweep, flips and even the duplicator all apply on top. Saved patterns
remember which ILDA file they used and restore it on load (including
MIDI-triggered loads). Safety note: unlike the synth shapes, ILDA files
can contain beam dwells — the importer scans for long runs of lit
points at one coordinate and prints a warning; treat warned files with
care at full power.

**Pattern bank** (left column, beside the visualiser): dial in
a look, type a name,
hit SAVE (or press Enter). Click a pattern to load it — this also puts
its name in the field, so the edit workflow is load → tweak → SAVE to
overwrite. The × on each pattern deletes it (with confirmation).

*Transitions*: the INSTANT/XFADE buttons set how pattern loads behave.
XFADE glides every parameter to the target over ~2 s with eased motion —
hue takes the short way around the colour wheel; discrete settings
(shape, mono, flips) switch at the midpoint. Grabbing a fader or CC
mid-fade takes that parameter out of the transition, so you always win.
Applies to browser clicks and MIDI-triggered patterns alike.

*MIDI learn*: the ♪ button on each pattern arms learn — hit a key on
your controller and that note now loads the pattern (from anywhere, web
UI open or not). The button shows the bound note (e.g. D2); click to
re-learn, shift-click to clear. Pattern bindings take priority over the
built-in shape-select notes; binding a note steals it from any pattern
that had it. Bindings are stored with the pattern in `patterns.json`.
Patterns capture every parameter and live in `patterns.json` next to
the scripts: plain JSON, atomic writes, safe to hand-edit or keep in
git. Delete the file to reset to nothing; a few starter patterns ship
with the project.

**Pause / Stop spin** (Geometry panel): PAUSE freezes every
time-driven motion — spin, sweep, orbit, hue cycling, ILDA playback and
in-flight crossfades — while faders stay live, so you can pose a frame
and adjust it. STOP SPIN zeroes the spin rate and resets the figure to
its upright orientation.

**Settings** (button in the header): a modal with runtime engine
settings — points per frame, scan rate (pps), crossfade time, and the
projector-orientation flips, all adjustable live without restarting —
plus the custom **MIDI mapping** table. Every parameter is listed with
its current CC; hit LEARN and move a knob on your controller to bind it
(same workflow as pattern notes). Custom bindings are highlighted,
steal the CC from whatever had it, suppress that parameter's default
CC, and × returns a row to its default.

Each fader row also has an **encoder mode** for how its CC is
interpreted — important for rotary encoders:
- *abs* (default): value 0–127 maps straight to the range. Fine for
  real faders; with endless encoders it makes the value jump when you
  load a pattern and then touch the knob.
- *rel*: the encoder sends deltas, not positions — each turn nudges the
  value from wherever it currently sits, so pattern loads never fight
  the knob. Auto-detects the two common signed encodings (1/127 and
  65/63 style). Use this if your controller can be set to relative /
  "endless" output.
- *catch* (soft takeover): for absolute encoders that can't do
  relative. After a pattern sets a value, the knob is ignored until you
  turn it *past* that value, then it catches and tracks smoothly — no
  jump. Re-arms automatically on every pattern load. Everything here persists in
`settings.json` — saved settings win over CLI defaults on the next
launch, so the Settings page is the durable config and CLI flags seed
the first run.

**Oscillator (LFO)** (top of column 3): a low-frequency oscillator that
automatically sweeps one parameter over time, for hands-free movement.
Pick a **target** (morph, size, hue, ratio A/B, spin, position, dup
spread or dotify) and a **wave** (sine, triangle, square, saw, or
random sample-and-hold), then set **rate**, **depth** and **dropoff**.
The oscillator moves the target around its current fader value rather
than overwriting it, so the fader still sets the centre point and the
LFO swings around it — set depth to 0 to switch it off. Dropoff decays
the swing across each cycle, so the movement "settles" toward the base
value instead of oscillating evenly. Everything is a normal parameter,
so it's mappable (CC 32–36) and captured in patterns — you can save a
look that breathes on its own.

**Scope modes** (Audio panel, `scope` shape only): the scope shape now
has five visualisations, selectable by button or CC 30 — *waveform*
(classic oscilloscope trace), *vu meter* (level bar that grows with
loudness), *spectrum* (bass/mid/high skyline from the FFT), *radial*
(waveform wrapped around a circle), and *xy* (Lissajous plot of the
waveform against a delayed copy of itself). Each falls back to a calm
idle shape when no audio is present.

**Audio stop** (Audio panel): the AUDIO STOP button is a master kill
switch for everything audio-driven — it freezes the bass/mid/high
modulation of size, morph and brightness *and* drops the scope shapes
to their idle state, in one click. Mappable to a MIDI button (CC 31)
and stored in patterns, so you can bake "no audio" into a look.

**Mappable buttons**: the momentary actions **pause**, **stop spin**
and **blank** can be MIDI-mapped like any parameter — in Settings →
MIDI mapping they appear as ▶ rows; LEARN one and press a button or pad
on your controller. They fire on the press (rising edge) and ignore the
release, so a momentary pad toggles cleanly. The on-screen toggles
(mono, flips, mirrors, audio stop, scope mode) are all mappable too.

**Audio routing** (Audio panel): each frequency band — bass, mid,
high — has a dropdown selecting which parameter it drives. Defaults are
bass→size, mid→morph, high→brightness (the old fixed behaviour), but
you can point any band at size, morph, brightness, hue, spin, dup
spread, dotify, X/Y position or ratio A, or set it to *off*. Multiple
bands can target the same parameter (they add). The modulation is
additive around the current fader value, so your faders still set the
baseline. Routings are saved in patterns and MIDI-mappable (CC 42–44).

**Wave shape**: the `wave` shape draws a classic oscillator waveform
across the field — sine, triangle, saw, square or pulse, chosen in the
Wave shape panel (column 3). Ratio A sets the number of cycles and
morph controls amplitude (or duty cycle, for pulse).

**Size X / Y**: size is split into independent X and Y scales in the
Geometry panel, with a 🔗 LINK SIZE toggle. When linked (the default),
the two faders move together and stay equal; unlink to stretch a shape
into an ellipse, a wide line, or any non-square aspect. The link state
and both axes are saved in patterns and MIDI-mappable (CC 45–46); the
audio/LFO "size" destination drives the X axis (and Y too when linked).

**Split sweep**: X and Y auto-sweep are now independent — separate
depth and speed for each axis (Position panel), so you can set up
Lissajous-style drift with different rates per axis, or sweep only
horizontally.

**Random pattern**: the 🎲 RANDOM PATTERN button under the bank invents
a complete pattern from all synth options except ILDA and vector (which
need external files) — random shape, ratios, colours, duplicator,
oscillator and audio routing, kept within musical ranges. It loads
immediately (respecting the transition mode); save it if you like it.

**About page**: the ABOUT button (top bar) shows the contents of
`about.md` rendered as Markdown, light grey on black — edit that file
to keep your own notes, cheat-sheets or credits with the synth.

**Audio capture**: captures the default input device (mic or a
loopback/monitor source — in `pavucontrol` set the recording source to
"Monitor of <output>" to react to whatever's playing). Bass pumps the
size, mids wobble the morph, highs push brightness; `scope` mode draws
the raw waveform. Levels are adaptively normalised so it works without
gain fiddling.

## How it talks to the DAC

Classic Helios pipeline: `OpenDevices()` → poll `GetStatus()` until 1 →
`WriteFrame(dac, pps, flags, points, n)` with 12-bit X/Y + 8-bit RGBI
points. The DAC is double-buffered, so `write_frame()` blocking on
`GetStatus` naturally paces the render loop to the point clock — no
timers needed when the laser is running.

## Version

Current release: **1.0.0** (see `CHANGELOG.md`). Run `python lasersynth.py
--version` to check the installed version.

## License

This project is released under the **MIT License** — see `LICENSE`. In
short: use it freely, including commercially, keep the copyright notice.

It depends on permissively-licensed libraries (numpy BSD, mido/rtmidi/
sounddevice MIT, aiohttp/OpenCV Apache-2.0, pygame LGPL) and bundles the
MIT-licensed Helios DAC host driver. Full details, including the LGPL
note for pygame if you make a bundled binary, are in
`THIRD_PARTY_LICENSES.md`.

**Laser safety is your responsibility.** This software drives real laser
hardware; operate it safely and within your local regulations. See the
safety notice in `LICENSE` and the warning at the top of this file.
