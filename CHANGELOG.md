# Changelog

All notable changes to this project are documented here. This project
adheres to [Semantic Versioning](https://semver.org/).

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

[1.2.0]: https://github.com/USERNAME/laser-laser-laser/releases/tag/v1.2.0

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

[1.1.1]: https://github.com/USERNAME/laser-laser-laser/releases/tag/v1.1.1

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

[1.1.0]: https://github.com/USERNAME/laser-laser-laser/releases/tag/v1.1.0

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

[1.0.0]: https://github.com/USERNAME/laser-laser-laser/releases/tag/v1.0.0
