# Contributing

Thanks for your interest! This is a personal hobby project, shared in the
hope it's useful to other laser/synth tinkerers.

## Ground rules

- **Laser safety comes first.** Any change that affects what gets sent to
  the DAC (point generation, blanking, geometry, brightness) should keep
  the "closed curves + blanked travel moves + blank on exit" safety
  properties intact. Test in `--preview` before `--laser`.
- Keep the **no-build-step** philosophy: vanilla Python + a single
  self-contained `static/index.html` (no bundlers, no npm, no CDN).
- Every code change should bump the version in `lasersynth.py`
  (`__version__`) and add a `CHANGELOG.md` entry.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python lasersynth.py --web        # screen only, no laser
```

The architecture, in brief:
- `shapes.py` — the render engine (all parameters, shapes, LFO, routing)
- `lasersynth.py` — app entry, render loop, MIDI, DAC output
- `webui.py` + `static/index.html` — the browser control surface
- `patterns.py` / `settings.py` / `ilda.py` / `vectorise.py` /
  `geometry.py` — feature modules, each fairly self-contained

Issues and pull requests welcome.
