# Changelog

All notable changes to this project are documented here. This project
adheres to [Semantic Versioning](https://semver.org/).

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
