# Changelog

All notable changes to this project are documented here. This project
adheres to [Semantic Versioning](https://semver.org/).

## [1.7.0] — 2026-09-08

Three new closed-curve shapes and three effects that apply to every shape.
The effects are the larger half: a new stage in `frame()` reaches all
fourteen shapes plus ILDA, text and the vectoriser, where a new generator
only adds one more entry to the list.

All of it stays inside the one geometry rule the engine is built on —
single closed curves, no new blanked multi-stroke geometry.

### Added
- **`superformula`** — the Gielis superformula: one equation that morphs
  continuously through circles, polygons, stars, flowers and blobs. Ratio A
  is the symmetry, ratio B and morph the lobe shape. Built to be modulated:
  the oscillator or an audio band on morph walks the whole family.
- **`maurer`** — a Maurer rose. Walks a rose curve in fixed degree steps and
  joins the positions with chords, which interfere into a dense moiré
  lattice. Ratio B selects the lattice *and* its density, ordered from 20
  chords up to the classic 360. Density is the part that matters on real
  hardware: at 800 points a 360-chord rose gets 2.2 points per chord, about
  88 us for the galvos to cross the field, which they cannot do — so the
  dense end is deliberately at the top of the dial rather than spread across
  it. Each step is also chosen large enough that the chords cross into a
  lattice instead of hugging the rose outline, and the walk runs for exactly
  360/gcd(d, 360) chords, which is one closure, so no part of the point
  budget is spent retracing.
- **`knot`** — a (p,q) torus knot, and the first genuinely 3D shape. It
  returns a third `z` column, which the new tilt/tumble stage projects.
  Generators may now return `(x, y)` or `(x, y, z)`; the six existing ones
  are untouched and sit at z = 0.
- **Ripple warp** — displaces the curve along its own normal, indexed by
  point number rather than polar angle so it works on open curves,
  off-centre curves and source frames alike. An integer cycle count is what
  keeps a closed curve closed.
- **3D tilt / tumble / perspective** — rotates any shape in 3D with a
  perspective divide, before the duplicator so each copy reads as its own
  object. The beam has no shading, so parallax is the only depth cue a
  laser has.
- **Comet chase** — a brightness envelope travelling along the path.
  Intensity only: the geometry and the point rate are untouched, so the
  galvos keep moving at full speed. The same trade as dotify.
- `warp_amt`, `chase_amt`, `persp` are routable audio destinations;
  `warp_amt`, `tilt_y` and `chase_amt` are oscillator targets. Both lists
  are appended to, so existing patterns keep their routing.
- The RANDOM button reaches the new shapes and effects.
- **Per-panel on/off switches** on Effects, Duplicator, Audio and Oscillator,
  in the top right of each heading. Switching a panel off bypasses that stage
  in the render loop while leaving its faders untouched, so a panel can be
  dropped and brought back without rebuilding the setup; a bypassed panel
  dims its controls. The switches drive engine parameters (`fx_on`, `dup_on`,
  `lfo_on`), so MIDI and the preview keyboard stay in step. Audio's switch
  drives the existing `audio_off` rather than adding a second kill switch
  that could disagree with the first.
- **RESET ALL**, above the Oscillator panel — every parameter back to its
  default, over a new `{"type":"params_reset"}` message. It snaps rather than
  crossfading and cancels any transition in flight, since a reset that eased
  in over two seconds would defeat the point of pressing it, and it resets
  the running phases so spin and tumble return to their starting angles.
  Installed sources (text, ILDA, the custom polygon) are left alone — they
  are content, not settings. The button asks twice: the first press arms it,
  the second does it, and it disarms itself after a few seconds.

### Safety
- **The 3D stage cannot collapse a figure to a point.** Rotating a flat
  shape toward edge-on shrinks it without limit, and a flat shape that is
  itself a line — lissajous at 1:1, polygon with 1 or 2 sides — goes all the
  way to a single coordinate. Measured during development: an entire
  800-point frame on one DAC coordinate, which is a parked beam and exactly
  what `docs/SAFETY.md` §6 rules out. Two guards now prevent it: flat shapes
  never reach perfect edge-on (`MIN_FLAT_COS`), and the stage may not shrink
  any figure below a fraction of the extent it was handed
  (`MIN_3D_EXTENT`). The edge-on guard folds through `|cos|` rather than
  clamping the signed cosine: clamping held the width pinned at the floor
  across a range of angles and then flipped the figure to its mirror, which
  read as a stall followed by a jump of 584 DAC units in a single degree of
  tumble. Folded, the largest step is 32 units against a median of 25, so
  the rotation is smooth throughout. With both in place the worst dwell across every shape,
  swept over the full tilt/perspective/ripple space, is 14 lit points
  against the advisory threshold of 48 that `ilda.dwell_warnings` uses.
- The perspective divide biases z so its denominator is never below 1, so
  the projection can only shrink the figure, never drive coordinates off
  the field. Clipped coordinates pile onto the field edge, which is the
  same parked-beam hazard by another route.
- New generators follow the existing defences: arc-length resampling for
  even spacing (`polygon`'s idiom), normalising by max abs
  (`hypotrochoid`'s), and a `gcd` guard on the knot (`polygon`'s). All four
  were verified closed — the closing segment is exactly one sample step.

### Changed
- **Spin is off by default** (`spin` 0.5 rather than 0.55). A figure that
  starts drifting the moment the app opens is a nuisance when you are trying
  to set one up. This is the only change to how existing shapes render:
  restoring the old value reproduces the previous output byte for byte, and
  saved patterns are unaffected either way because they store `spin`
  explicitly.
- `ShapeEngine.default_params()` is now the single source of the factory
  defaults, so `__init__` and the master reset cannot drift apart.
- **`falloff` (the duplicator's per-copy size falloff) is now an oscillator
  target and an audio destination.** Both lists are appended to, so every
  saved pattern's existing routing still points where it did.
  Wiring it up also needed the duplicator to read `p_mod["dup_scale"]`
  rather than `p["dup_scale"]`: audio modulation is accumulated into
  `p_mod` alone, so the raw read would have left falloff selectable in the
  menu but inert in the beam. (The oscillator path would have worked either
  way, which is exactly how a half-working routing goes unnoticed.)
- **Lighter UI chrome.** The fader knob is a 4px marker rather than a 10px
  slab (it was the loudest thing in a panel full of values), picking up the
  accent colour on hover instead of wearing it permanently. The audio level
  bars fill in `--ink-dim` rather than full `--ink`, so three bouncing bars
  are no longer the brightest thing on the page.
- **Panels tied to one shape dim when another shape is selected** — Wave
  shape, Custom Shape, ILDA, Vectoriser, and the scope-mode buttons inside
  Audio. Dimmed, deliberately *not* disabled: picking an ILDA file, drawing
  a custom polygon or starting the vectoriser is what switches the engine to
  that shape in the first place, so locking them until their shape is
  current would make those shapes unreachable. It is a legibility cue, not
  a gate.
- RESET ALL moved from above the Oscillator panel to under Geometry.
- **Four parameter columns instead of three, and a smaller beam preview.**
  The preview is 359px rather than 479 (a quarter down), and the controls
  grid is four columns from 1460px of viewport width up, dropping to three,
  two and one below that. The panels were also redistributed: the old third
  column carried six panels while the first carried three, so the page ran
  well past the fold. They are now grouped as figure / placement /
  colour-and-modulation / shape-specific-and-sources, which measures as a
  tallest column of 771px against 868 before. Measured in a headless
  browser at 1920, 1680, 1500 and 1460: four columns, preview holding
  359px, and no scrolling in either direction.
  The stage column's floor is set to the preview width, so the beam view
  keeps its size instead of being squeezed further as the fourth column
  is fitted in.
- **The pattern, mask and ILDA lists now sort case-insensitively.** They
  were already sorted, but `sorted()` is ASCII order, which puts every
  capitalised name ahead of every lowercase one — "VU-1" landed above
  "dotted orbit" and the bank did not read as alphabetical. All three
  `names()` methods now sort on `str.lower`.

### Removed
- The `flow` shape. It was not interesting enough to keep — a wobbling
  circle whose motion read as noise rather than as structure. Removed from
  the end of `SHAPE_NAMES`, so no other shape's index moves and no saved
  pattern is disturbed.

### Fixed
- **A recalled pattern now reproduces the look it was saved with.** Every
  one of the 58 parameters was already stored and restored exactly — that
  part was never broken. What leaked was the engine's *animation* state,
  which is not part of a pattern: the spin angle, the hue rotation, the
  duplicator's orbit, the two sweep oscillators, the 3D tumble, the shape
  phase behind the ripple and the comet, and the oscillator's phase. All
  nine kept whatever value the session had reached, so a pattern saved with
  spin stopped and a deliberate `rotate` offset came back **76 degrees out
  of true** — the parameters matched, the picture did not. `rotate` was
  simply where it showed most, because a stationary figure's orientation is
  obvious.

  `ShapeEngine.reset_phases()` rewinds all nine, and a snapping pattern load
  (or a randomise) now calls it. A crossfade deliberately does not: gliding
  from wherever things are is the whole point of it, and snapping the phases
  mid-glide is exactly the jump it exists to avoid. `reset_params()` shares
  the same method rather than repeating the list.
- **Content pushed outside the projection field no longer parks the beam.**
  Off-field geometry was clamped onto the field boundary by the `np.clip` at
  pack time, and a clamped run of *lit* points is a stationary beam — the
  same hazard as a dwell, reached by a different route. Worst measured case:
  a full-size lissajous at 1:1 rotated 45°, where the diagonal becomes
  2·sqrt(2) long and 402 of its 800 points pin to the edge, giving a run of
  201 lit points on one DAC coordinate. Ordinary shapes nudged into a corner
  with pos X / pos Y produced runs of 41–120 the same way, so this was
  general, not specific to one shape.

  Points outside the field are now blanked rather than smeared along the
  edge. The galvos travel the same path; the beam is simply off for the part
  that is outside — which is also the correct visual behaviour, since
  content off the edge of the field should not be drawn. With this in place
  the worst dwell anywhere, swept across every shape over ratios, morph,
  rotation, position, tilt, perspective and ripple, is 17 lit points against
  the advisory threshold of 48 in `ilda.dwell_warnings`.

  This predates the new shapes and effects — it reproduces on the 1.6.0 code
  — but the 3D stage made it easier to reach, so it is fixed here. No saved
  pattern changes: all seven starter patterns and all eleven original shapes
  still render byte-identically, because none of them render off-field.

### Notes
- The effects default to off and `tilt_x`/`tilt_y` default to 0.5 (neutral),
  so the whole stage is a byte-for-byte no-op at its defaults and existing
  patterns render exactly as before.
- Patterns saved before 1.7.0 carry none of the new keys, so loading one
  leaves the effects at their *current* values rather than resetting them —
  the same behaviour `rotate` and `size_y` already had.

## [1.6.0] — 2026-08-17

LaserCube network output, and a runtime output selector. The LaserCube path is
deliberately ringfenced: `lasercube_output.py` is a standalone module that
imports nothing from this project, and the Helios path is untouched except for
gaining diagnostics. Both backends sit under the same `SafeOutput` wrapper, so
the arm gate, brightness ceiling, watchdog and blank-on-exit apply identically
and neither backend can bypass them.

### Added
- **LaserCube / LaserCube Ultra output over the network** (`--output
  lasercube`). UDP, pure Python, no C toolchain. `write()` never touches a
  socket — it hands the frame to a sender thread through a lock-guarded slot,
  so the render thread can never be blocked by the network. The sender paces
  to the DAC rate and keeps the device buffer topped up rather than sending
  one burst per frame, and drops frames rather than blocking under
  backpressure.
- **Output device selector in Settings** — switch between none, Helios (USB)
  and LaserCube (network) live, without restarting. The choice persists.
  **Switching always disarms**: arming is a statement about one specific
  projector and is never carried across a device change. If the new device
  fails to open, output falls back to none rather than leaving a dead backend
  in place.
- **TEST DEVICE diagnostics** (Settings → Laser output). Queries the attached
  device and reports what it says about itself — for a LaserCube: firmware,
  serial, model, connection type, temperature and thermal warnings, interlock
  state, output state, power source, scan rate and maximum, buffer occupancy,
  the device's own packet-error count, and our frame sent/dropped/error
  counters. For a Helios: device count and link status, and an explicit note
  that it reports no telemetry. Emits nothing, so it is safe to press at any
  time.
- **`scripts/lasercube_sim.py`** — a fake LaserCube that answers on the real
  ports, so discovery, framing, throttling, the watchdog, arm-refusal and
  reconnect can all be exercised with zero photons. It can be told to
  misbehave: `--stall-after`, `--drop`, `--refuse-enable`, `--tiny-buffer`,
  `--temperature`, `--interlock-open`, `--packet-errors`. It builds its
  responses independently of the client's parser, so a shared offset error
  cannot pass unnoticed.
- `--list-lasercubes` discovers units on the network and prints their status.
  `--lasercube-dry-run` packs and rate-controls while transmitting nothing.
  `--lasercube-ip` skips discovery; `--lasercube-point-order` swaps the wire
  field order without a code change, if the hardware disagrees with the spec.
- **Thermal and interlock awareness**: the device's own temperature, thermal
  warnings and interlock state are read and surfaced, and `enable()` refuses
  while the device reports over-temperature.

- **`docs/PORTING.md`** — how to adopt the output safety layer in the sibling
  projects, with the per-project adaptations each needs, and the constraints
  that keep the shared files copyable.
- **`.claude/skills/verify-output/`** — the verification procedure for changes
  to the output path, including the simulator workflow and the invariants to
  re-check.

### Changed
- **The brightness ceiling moved from the header to Settings**, behind a
  confirmation when raising it above 5%. It was too easy to nudge mid-show
  from the header. The header now shows it read-only, in amber when above 5%.
- **Arming can now fail.** If the backend has a hardware output gate and the
  device refuses, the app stays disarmed and says so, rather than displaying
  ARMED over a device that is dark. `enable()` on the LaserCube reads the
  state back from the device instead of trusting an unacknowledged UDP send.

### Fixed
- `docs/lasercubeoutput.md` gave the LaserCube's wavelengths as 445/520/638
  nm. The Ultra is **455 nm blue, 525 nm green, 638 nm red** — an eyewear
  rating is not a place for an approximate number.
- The same document claimed native 12-bit colour as an advantage of the
  network path. The wire carries 12-bit fields but the hardware does 16.7
  million colours — 8 bits per channel, the same as the Helios. There is no
  colour-depth win.
- Every remaining `[VERIFY]` item in the protocol spec is resolved and cited
  except stream-underrun behaviour, which only hardware can answer.

## [1.5.0] — 2026-08-16

Output safety hardening. This release implements the mandatory requirements
in `docs/lasercubeoutput.md` §4 for the Helios path, in a shared module
(`laser_output.py`) written to be copied into the sibling laser projects
rather than reimplemented in each. None of these are safety devices — the key
switch, aperture shutter, interlock loop and Remote Stop remain the only
actual safety layer.

### Added
- **ARM gate**: the laser output starts **disarmed** and emits nothing until
  you arm it — from the header ARM button, or `shift-.` in the preview
  window. Disarming is instant, with no crossfade, and available from the
  same button, `.` in the preview, or a new `act_disarm` MIDI action you can
  LEARN onto any pad. Arm state is deliberately never persisted: every start
  is disarmed, however the last session ended. Note that "disarmed" means
  *actively streaming darkness*, not silence — a DAC that simply stops being
  fed repeats its last frame forever.
- **Brightness ceiling**: a hard cap on output, applied at the final packing
  stage after every scene, mask and geometry transform, so nothing upstream —
  pattern load, audio modulation, MIDI — can exceed it. **Defaults to 5%**;
  set it with the header MAX slider, the one-click 5% button, or
  `--max-brightness`, and it persists in `settings.json`. This is a creative
  limiter, not a safety interlock: it cannot help against a crash or a driver
  bug. It is separate from the existing `brightness` parameter, which stays
  exactly as it was.
- **Watchdog**: a daemon thread blanks the output if the render loop stops
  feeding it — a GC pause, a deadlock, a logic bug. The stall threshold
  adapts to the frame time (`max(250 ms, 3 × points/pps)`) so slow, legitimate
  frames at low PPS don't false-trip it.
- **Blank on every exit path**: SIGINT, SIGTERM and `atexit` handlers, plus a
  context manager. **SIGTERM was the real gap** — without a handler, `kill`
  terminated the process outright, the teardown never ran, and the DAC sat
  replaying its last frame.
- `--output {none,helios}` selects the backend; `--laser` remains an alias for
  `--output helios`.
- `laser_output.py`, a project-independent module (stdlib + numpy only,
  Python 3.9 compatible) holding the `LaserOutput` protocol, `NullOutput`,
  the `SafeOutput` wrapper and the panic handlers.

- **`docs/SAFETY.md`**: what the software does about safety, what it
  explicitly does not, the daily operating procedure, the hardware bring-up
  checklist, the rules for changing anything on the DAC path, and an honest
  list of known gaps.

### Fixed
- `HeliosDAC` gained a real `blank()` primitive — a dark frame written in
  *repeat* mode, so the DAC keeps emitting darkness even if the process dies
  immediately afterwards. `close()` now blanks, settles and then releases.
- `HeliosDAC.stop()` no longer swallows every exception silently. A blank that
  failed is now reported loudly, which is the whole point of the call.

## [1.4.0] — 2026-08-14

### Added
- **Output monitor window**: a MONITOR button in the header opens the beam
  view in its own window — no panels, no chrome, just the output on black,
  scaled to fill and letterboxed to the square scan field. Drag it to a
  second screen or projector and double-click for fullscreen. It reads the
  same 30 Hz frame stream as the control surface (so it shows exactly what
  the laser is doing, mask included) and reconnects on its own if the synth
  restarts. Served at `/monitor`; useful as a stand-in display when you
  don't have a laser to hand.
- **Mask**: draw polygons over the live beam and everything outside them
  is blanked — on the laser **and** the monitor, unlike projection
  geometry, which is laser-only. Click points straight onto the scope;
  select/drag, delete and undo as you go, with the shape updating the
  output live. A mask holds up to 8 polygons (64 points each) and inside
  means inside any of them; INVERT flips it to block-inside, so you can
  cut windows out of a full field. Masks save to a named library
  (`masks.json`) and reload with a click, independent of the pattern bank
  — the mask is about the room, not the visual. The live mask persists in
  `settings.json` across restarts. Applied before the geometry warp, so it
  is defined in the same space the monitor shows. Blanking only: the beam
  still travels masked areas dark, so it is a projection-mapping tool, not
  a safety interlock.

### Changed
- **Text and Mask panels collapse**: both start collapsed as slim headers,
  since they're occasional-use — click a header to open. Hitting the
  **text** shape button opens the Text panel and focuses the box, so
  picking the shape and typing is still one move.
- **Docs split**: the README is now a short landing page; per-platform
  setup and the command-line reference moved to `docs/INSTALL.md`, and the
  full control reference to `docs/MANUAL.md`. Added `CLAUDE.md` for
  AI-assisted work on the codebase.
- **Tidier root**: documentation, the interface snapshot and the app icon
  moved to `docs/`; `heliosdac.rules` and `build_helios_lib.sh` to
  `scripts/` (the udev-rule install command in `docs/INSTALL.md` changed to
  match). The Python modules and their data files stay flat in the root on
  purpose — several resolve paths relative to their own file, and the
  PyInstaller bundle flattens to the same layout.

[1.4.0]: https://github.com/edmonkey-nz/laser-laser-laser/releases/tag/v1.4.0

## [1.3.1] — 2026-07-27

### Fixed
- **Browser UI now on by default**: the prebuilt executables (and the
  bare `python laserx3.py` invocation) launched with `--web` off, so
  double-clicking the Windows/macOS/Linux binary just showed the pygame
  preview stuck on whatever pattern loaded, with no way to switch
  patterns or otherwise control the synth. The browser control surface
  is now on by default; `--no-web` opts back out. Explicit invocations
  of `--web`, `--laser` and `--preview` keep their previous meanings.

[1.3.1]: https://github.com/edmonkey-nz/laser-laser-laser/releases/tag/v1.3.1

## [1.3.0] — 2026-07-27

### Added
- **Custom shape**: a point-and-click polygon editor. Add, select/drag,
  and delete points in a modal editor; edges connect the points in click
  order and close back to the first. Saved and restored per pattern
  (capped at 64 points).
- **Prebuilt executables**: a GitHub Actions workflow
  (`.github/workflows/build.yml`) builds standalone Ubuntu/Windows/macOS
  binaries with PyInstaller and publishes them to GitHub Releases on
  every version tag.

[1.3.0]: https://github.com/edmonkey-nz/laser-laser-laser/releases/tag/v1.3.0

## [1.2.0] — 2026-07-08

### Added
- **Multi-line text**: the text block is now a 4-line input; lines are
  centred and the block auto-scales to fit the field.
- **Rotate**: a static rotation offset in the Geometry panel (separate
  from the continuous spin). Switching to a source shape (text / ILDA /
  vector) now defaults spin to stopped.
- **Colour swatches**: the hue fader is replaced by a strip of clickable
  16×16 colour blocks. Hue remains a normal 0–1 parameter, so it's still
  MIDI-mappable and saved in patterns.
- Snapshot image added to the README.

### Fixed
- Lowercase `a` in the text font rendered as a malformed open loop; it's
  now a proper bowl-and-stem glyph.

### Changed
- Removed the instructional text and CLEAR button from the per-pattern
  PPS / points block (leave a field blank to use the system value).

[1.2.0]: https://github.com/edmonkey-nz/laser-laser-laser/releases/tag/v1.2.0

## [1.1.1] — 2026-07-08

### Added
- **macOS support**: `helios.py` now loads `libHeliosDacAPI.dylib` on
  macOS, and the webcam vectoriser falls back to index-based camera
  selection (no V4L2) on macOS/Windows. Added a macOS build/setup section
  to the README.

### Changed
- Restructured the README's Control section into logical groups
  (Interfaces, Shapes, Modulation, Colour & beam, Position & geometry,
  Sources, Pattern bank, Live actions, Settings) so related controls sit
  together. Removed the fixed MIDI CC table — mappings are configured
  entirely in Settings → MIDI mapping via LEARN.

[1.1.1]: https://github.com/edmonkey-nz/laser-laser-laser/releases/tag/v1.1.1

## [1.1.0] — 2026-07-08

### Added
- **Text shape**: type a string to project it as laser text, in three
  single-stroke vector fonts (plain, script, bold+outline) built for
  efficiency. Includes macron vowels (ā ē ī ō ū) for te reo Māori, with
  a quick macron button in the text block (under the visualiser).
- **Per-pattern PPS / points override** (column 3): optionally pin a
  scan rate and point count to an individual pattern; blank fields fall
  back to the system settings. Saved and restored with the pattern,
  excluded from the random generator, and not MIDI-mapped.

[1.1.0]: https://github.com/edmonkey-nz/laser-laser-laser/releases/tag/v1.1.0

## [1.0.0] — 2026-07-06

First public release. A complete realtime laser visuals synthesizer for
the Helios DAC, controllable from a browser, MIDI, and the keyboard.

### Shapes & sources
- Vector shapes: lissajous, rose, hypotrochoid, wave (sine/triangle/saw/
  square/pulse), harmonograph, polygon (line → polygon → star → circle),
  and an audio scope (waveform / VU / spectrum / radial / XY).
- ILDA (`.ild`) import with all point formats, animation playback
  (loop / ping-pong / single), drag-and-drop upload and a file library.
- Image + webcam vectoriser (OpenCV) with brightness/contrast/threshold/
  detail filters, tracing subjects in their own colours.

### Control & modulation
- Browser control surface (vanilla JS, no build step) with a live beam
  view; works on the LAN as a phone/tablet controller.
- MIDI CC and note mapping with a learn workflow, custom mappings, and
  three encoder modes (absolute / relative / soft-takeover "catch").
- Mappable action buttons (pause, stop-spin, blank) and toggles.
- Oscillator (LFO) that sweeps any parameter (5 wave shapes, rate,
  depth, dropoff).
- Routable audio reactivity: each frequency band drives a chosen target.
- Duplicator with orbit, falloff and mirror; independent X/Y size with a
  link toggle; independent X/Y auto-sweep; crossfade transitions.

### Output & workflow
- Pattern bank with save/load/delete, per-pattern MIDI notes, crossfade
  vs instant transitions, and a random pattern generator.
- Projection geometry correction (corner-pin keystone + pincushion) and
  an alignment test pattern, applied to the laser output only.
- Persistent settings, projector orientation flips, and an editable
  About page.

[1.0.0]: https://github.com/edmonkey-nz/laser-laser-laser/releases/tag/v1.0.0
