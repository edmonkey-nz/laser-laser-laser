# Changelog

All notable changes to this project are documented here. This project
adheres to [Semantic Versioning](https://semver.org/).

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
