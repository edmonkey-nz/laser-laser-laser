"""
shapes.py — vector shape oscillators for the laser synth.

Every generator returns (x, y) in [-1, 1] for a closed curve sampled at
n points, given a continuously-advancing phase. Closed curves need no
blanking, which keeps the Helios pipeline simple and the beam bright.
"""

import numpy as np

TWO_PI = 2.0 * np.pi

SHAPE_NAMES = ["lissajous", "rose", "hypotrochoid", "wave", "harmonograph",
               "polygon", "scope", "ilda", "vector", "text"]


def polygon(n, phase, p):
    """
    Regular/star polygon with equal arc-length point spacing (even beam
    brightness along edges). ratio_a = sides: 1 draws a single horizontal
    line, 2 a line through the centre, 3..12 a polygon; ratio_b = star skip
    (1 = regular, 2 = pentagram-style), morph = corner rounding → circle.
    """
    from math import gcd
    a_sides = int(round(p["ratio_a"]))
    if a_sides <= 1:
        # single line: a horizontal stroke, morph tilts it toward vertical
        ang = p.get("morph", 0.0) * (np.pi / 2)
        t = np.linspace(-1.0, 1.0, n)
        return t * np.cos(ang), t * np.sin(ang)
    if a_sides == 2:
        # two "sides": a line through the origin (spin then rotates it)
        t = np.concatenate([np.linspace(-1, 1, n // 2),
                            np.linspace(1, -1, n - n // 2)])
        return t, np.zeros_like(t)
    sides = int(np.clip(a_sides, 3, 12))
    skip = int(np.clip(round(p["ratio_b"]), 1, max(1, sides // 2)))
    if gcd(sides, skip) != 1:
        skip = 1
    ang = np.arange(sides + 1) * (TWO_PI * skip / sides) + np.pi / 2
    vx, vy = np.cos(ang), np.sin(ang)
    seg = np.hypot(np.diff(vx), np.diff(vy))
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    s = np.linspace(0, cum[-1], n, endpoint=False)
    x = np.interp(s, cum, vx)
    y = np.interp(s, cum, vy)
    # rounding: blend each point outward to the unit circle at its angle
    r = np.clip(p["morph"], 0, 1)
    if r > 0:
        theta = np.arctan2(y, x)
        x = (1 - r) * x + r * np.cos(theta)
        y = (1 - r) * y + r * np.sin(theta)
    return x, y


def lissajous(n, phase, p):
    """x = sin(a·t + φ), y = sin(b·t). The classic."""
    t = np.linspace(0, TWO_PI, n, endpoint=False)
    a = max(1, round(p["ratio_a"]))
    b = max(1, round(p["ratio_b"]))
    x = np.sin(a * t + p["morph"] * np.pi + phase * 0.0)
    y = np.sin(b * t + phase * 0.0)
    return x, y


def rose(n, phase, p):
    """r = cos(k·t) rose curve; morph skews petal shape."""
    t = np.linspace(0, TWO_PI, n, endpoint=False)
    k = max(1, round(p["ratio_a"]))
    r = np.cos(k * t + p["morph"] * np.pi)
    return r * np.cos(t), r * np.sin(t)


def hypotrochoid(n, phase, p):
    """Spirograph. ratio_a/ratio_b set gear ratio, morph sets pen offset."""
    R = 1.0
    r = max(1, round(p["ratio_b"])) / 10.0 + 0.05
    d = 0.2 + p["morph"] * 0.8
    loops = max(1, round(p["ratio_a"]))
    t = np.linspace(0, TWO_PI * loops, n, endpoint=False)
    q = (R - r) / r
    x = (R - r) * np.cos(t) + d * np.cos(q * t)
    y = (R - r) * np.sin(t) - d * np.sin(q * t)
    m = max(np.max(np.abs(x)), np.max(np.abs(y)), 1e-6)
    return x / m, y / m


def harmonograph(n, phase, p):
    """Two-term undamped harmonograph — Lissajous with sidebands."""
    t = np.linspace(0, TWO_PI, n, endpoint=False)
    a = max(1, round(p["ratio_a"]))
    b = max(1, round(p["ratio_b"]))
    m = p["morph"]
    x = 0.7 * np.sin(a * t) + 0.3 * np.sin((a + b) * t + m * np.pi)
    y = 0.7 * np.sin(b * t + np.pi / 2) + 0.3 * np.sin((b + a) * t + m * np.pi * 0.5)
    return x, y


SCOPE_MODES = ["waveform", "vu meter", "spectrum", "radial", "xy"]

# parameters the oscillator (LFO) can modulate, and their display order
LFO_TARGETS = ["morph", "size", "hue", "ratio_a", "ratio_b", "spin",
               "pos_x", "pos_y", "dup_spread", "dotify"]
LFO_WAVES = ["sine", "triangle", "square", "saw", "random"]

# audio band routing: each band (bass/mid/high) can drive one destination.
# "size+", "morph+" etc. are additive modulations of that parameter.
AUDIO_DESTS = ["off", "size", "morph", "brightness", "hue", "spin",
               "dup_spread", "dotify", "pos_x", "pos_y", "ratio_a"]

# waveform sub-shapes for the "wave" shape (item 6)
WAVE_TYPES = ["sine", "triangle", "saw", "square", "pulse"]

# value bounds for LFO-modulated params (for scaling the swing)
PARAM_BOUNDS = {
    "morph": (0.0, 1.0), "size": (0.02, 1.0), "hue": (0.0, 1.0),
    "ratio_a": (1.0, 12.0), "ratio_b": (1.0, 12.0), "spin": (0.0, 1.0),
    "rotate": (0.0, 1.0),
    "pos_x": (0.0, 1.0), "pos_y": (0.0, 1.0), "dup_spread": (0.0, 1.0),
    "dotify": (0.0, 1.0), "brightness": (0.0, 1.0),
    "size_y": (0.02, 1.0),
}


def wave(n, phase, p):
    """Waveform shape: draws a classic oscillator waveform across the field.
    wave_type selects sine/triangle/saw/square/pulse; ratio_a sets the
    number of cycles, morph adds vertical amplitude / duty variation."""
    wt = int(round(p.get("wave_type", 0))) % len(WAVE_TYPES)
    cycles = max(1, round(p["ratio_a"]))
    x = np.linspace(-1, 1, n, endpoint=False)
    t = np.linspace(0, 1, n, endpoint=False) * cycles
    frac = t - np.floor(t)
    amp = 0.4 + 0.5 * p["morph"]
    if wt == 0:                                  # sine
        y = np.sin(t * TWO_PI)
    elif wt == 1:                                # triangle
        y = 2.0 * np.abs(2.0 * frac - 1.0) - 1.0
    elif wt == 2:                                # saw
        y = 2.0 * frac - 1.0
    elif wt == 3:                                # square
        y = np.where(frac < 0.5, 1.0, -1.0)
    else:                                        # pulse (morph = duty)
        duty = 0.1 + 0.8 * p["morph"]
        y = np.where(frac < duty, 1.0, -1.0)
        amp = 0.9
    return x, y * amp


def scope(n, phase, p, audio=None):
    """Audio-driven visualiser with several modes (scope_mode param):
      0 waveform  — classic left-to-right oscilloscope trace
      1 vu meter  — horizontal level bar that grows with loudness
      2 spectrum  — bass..treble bar-graph skyline from the FFT bands
      3 radial    — waveform wrapped around a circle (radial scope)
      4 xy        — Lissajous-style XY plot of the waveform vs itself
    audio: the full audio dict (wave + bands) or None.
    """
    mode = int(round(p.get("scope_mode", 0))) % len(SCOPE_MODES)
    wave = audio.get("wave") if audio else None
    gain = 1.0 + 4.0 * p["morph"]

    def resampled(m):
        idx = np.linspace(0, len(wave) - 1, m).astype(int)
        return np.clip(wave[idx] * gain, -1, 1)

    if mode == 1:  # VU meter — level bar centred, length tracks RMS
        rms = audio["rms"] if audio else 0.0
        level = np.clip(rms * gain * 3.0, 0.02, 1.0)
        half = n // 2
        top = np.linspace(-level, level, half)
        x = np.concatenate([top, top[::-1]])
        y = np.concatenate([np.full(half, 0.12), np.full(n - half, -0.12)])
        return x[:n], y[:n]

    if mode == 2:  # spectrum — skyline of the frequency bands
        bands = [audio["bass"], audio["mid"], audio["high"]] if audio \
            else [0.3, 0.5, 0.2]
        nb = len(bands)
        xs, ys = [], []
        for i, v in enumerate(bands):
            x0 = -0.9 + 1.8 * i / nb
            x1 = -0.9 + 1.8 * (i + 1) / nb - 0.05
            h = -0.8 + 1.6 * np.clip(v * gain, 0, 1)
            xs += [x0, x0, x1, x1]
            ys += [-0.8, h, h, -0.8]
        seg_x = np.array(xs)
        seg_y = np.array(ys)
        idx = np.linspace(0, len(seg_x) - 1, n)
        return np.interp(idx, np.arange(len(seg_x)), seg_x), \
            np.interp(idx, np.arange(len(seg_y)), seg_y)

    if mode == 3:  # radial — waveform wrapped around a circle
        t = np.linspace(0, TWO_PI, n, endpoint=False)
        if wave is not None and len(wave) > 1:
            r = 0.5 + 0.4 * resampled(n)
        else:
            r = 0.5 + 0.1 * np.sin(t * max(1, round(p["ratio_a"])))
        return r * np.cos(t), r * np.sin(t)

    if mode == 4:  # xy — waveform vs a phase-shifted copy of itself
        if wave is not None and len(wave) > 1:
            w = resampled(n)
            shift = max(1, n // 7)
            return w, np.roll(w, shift)
        t = np.linspace(0, TWO_PI, n, endpoint=False)
        return np.sin(2 * t), np.sin(3 * t)

    # mode 0: waveform
    x = np.linspace(-1, 1, n, endpoint=False)
    if wave is not None and len(wave) > 1:
        y = resampled(n)
    else:
        y = np.sin(np.linspace(0, TWO_PI * max(1, round(p["ratio_a"])), n))
    return x, y



class ShapeEngine:
    """
    Holds parameter state, advances phase continuously between frames,
    applies rotation / size / audio modulation, and colours the curve.

    Parameters (all 0..1 unless noted, mapped from MIDI CCs):
      shape       int index into SHAPE_NAMES
      ratio_a     1..12 (float, rounded per shape)
      ratio_b     1..12
      morph       phase/pen offset inside the shape
      spin        rotation speed (bipolar around 0.5)
      size        master scale
      hue         base hue 0..1
      hue_cycle   hue rotation speed
      audio_amt   how hard audio modulates the visuals
      brightness  master intensity
      pos_x/pos_y beam centre offset (0.5 = centred)
      sweep       auto-sweep depth (Lissajous-style wander of the centre)
      sweep_speed auto-sweep rate
    """

    def __init__(self, n_points=800):
        self.n_points = n_points
        self.phase = 0.0        # shape-internal drift
        self.rot = 0.0          # rotation angle
        self.hue_phase = 0.0
        self.blanked = False    # master blank — zeroes all colour output
        self.p = {
            "shape": 0,
            "ratio_a": 3.0, "ratio_b": 2.0,
            "morph": 0.25, "spin": 0.55,
            "rotate": 0.0,      # static rotation offset (0..1 = 0..360°)
            "size": 0.8, "hue": 0.0, "hue_cycle": 0.15,
            "size_y": 0.8,      # independent Y scale; "size" is the X scale
            "size_link": 1.0,   # >0.5: X and Y locked to the same value
            "audio_amt": 0.5, "brightness": 1.0,
            "pos_x": 0.5, "pos_y": 0.5,
            "sweep_x": 0.0, "sweep_y": 0.0,       # per-axis sweep depth
            "sweep_x_speed": 0.3, "sweep_y_speed": 0.3,
            "wave_type": 0.0,   # waveform for the "wave" shape
            "aud_bass_dest": 1.0,  # bass -> size by default (index into AUDIO_DESTS)
            "aud_mid_dest": 2.0,   # mid -> morph
            "aud_high_dest": 3.0,  # high -> brightness
            "scope_mode": 0.0,  # scope visual: waveform/vu/spectrum/radial/xy
            "audio_off": 0.0,   # >0.5 = master audio kill (mods + scope idle)
            "lfo_target": 0.0,  # which param the oscillator modulates (index)
            "lfo_wave": 0.0,    # 0 sine 1 triangle 2 square 3 saw 4 random S&H
            "lfo_rate": 0.3,    # oscillation speed
            "lfo_depth": 0.0,   # modulation amount (0 = off)
            "lfo_dropoff": 0.0,  # >0 = oscillation decays over each cycle
            "dup_count": 1.0,   # 1..6 beam copies
            "dup_spread": 0.5,  # ring radius the copies sit on
            "dup_scale": 1.0,   # per-copy size falloff (1 = all equal)
            "dup_spin": 0.5,    # ring orbit speed (bipolar around 0.5)
            "dup_mirror_x": 0.0,  # >0.5: alternate copies mirrored in X
            "dup_mirror_y": 0.0,  # >0.5: alternate copies mirrored in Y
            "ilda_rate": 0.5,   # ILDA playback speed (0 = freeze, 1 = 24 fps)
            "ilda_mode": 0.0,   # 0 = loop, 1 = ping-pong, 2 = single
            "vec_bright": 0.5,  # vectoriser: image brightness (0.5 neutral)
            "vec_contrast": 0.5,  # vectoriser: contrast (0.5 neutral)
            "vec_thresh": 0.4,  # vectoriser: edge threshold (high = fewer)
            "vec_detail": 0.5,  # vectoriser: detail (low = simpler paths)
            "dotify": 0.0,      # break the beam into dots (0 = solid line)
            "mono": 0.0,        # >0.5 = single-colour output from hue fader
            "flip_x": 0.0,      # >0.5 = mirror horizontally
            "flip_y": 0.0,      # >0.5 = mirror vertically
        }
        self.ring_phase = 0.0
        self.lfo_phase = 0.0      # oscillator (LFO) phase accumulator
        self.sweep_x_phase = 0.0
        self.sweep_y_phase = 0.0
        self.xfade = False        # pattern loads crossfade instead of snap
        self.xfade_time = 2.0
        self._trans = None        # active transition state
        self.ilda_frames = None   # parsed ILDA frames (list of dicts)
        self.ilda_name = ""
        self.ilda_pos = 0.0       # playback position (fractional frames)
        self.vector_frame = None  # live frame from the image/webcam vectoriser
        self.text_str = ""        # current text-shape string
        self.text_style = 0       # 0 plain, 1 script, 2 bold
        self.text_frame = None    # cached rendered text frame
        # per-pattern PPS/points overrides (None = use system settings)
        self.pattern_pps = None
        self.pattern_points = None
        self.paused = False       # freezes all time-driven motion
        self.on_load = None       # optional callback when a pattern loads
        self.test_frame = None    # when set, overrides all shapes (alignment)

    DISCRETE = {"shape", "mono", "flip_x", "flip_y",
                "dup_mirror_x", "dup_mirror_y", "ilda_mode",
                "scope_mode", "audio_off", "lfo_target", "lfo_wave",
                "wave_type", "aud_bass_dest", "aud_mid_dest", "aud_high_dest",
                "size_link"}

    @staticmethod
    def random_params():
        """Generate a random but musically-sensible parameter set drawn
        from all synth options EXCEPT ILDA and vector (which need external
        files). Returns a params dict suitable for a pattern."""
        import random as _r
        # shapes minus ilda/vector/scope (scope needs audio to be interesting)
        pickable = [s for s in SHAPE_NAMES
                    if s not in ("ilda", "vector", "scope")]
        shape_idx = SHAPE_NAMES.index(_r.choice(pickable))
        p = {
            "shape": float(shape_idx),
            "ratio_a": float(_r.randint(1, 8)),
            "ratio_b": float(_r.randint(1, 8)),
            "morph": round(_r.uniform(0, 1), 3),
            "spin": round(_r.uniform(0.35, 0.65), 3),
            "size": round(_r.uniform(0.5, 0.95), 3),
            "hue": round(_r.random(), 3),
            "hue_cycle": round(_r.choice([0, 0, 0.1, 0.25, 0.5]), 3),
            "wave_type": float(_r.randint(0, len(WAVE_TYPES) - 1)),
            # position roughly centred
            "pos_x": round(_r.uniform(0.4, 0.6), 3),
            "pos_y": round(_r.uniform(0.4, 0.6), 3),
            # sweep: sometimes on
            "sweep_x": round(_r.choice([0, 0, _r.uniform(0.1, 0.5)]), 3),
            "sweep_y": round(_r.choice([0, 0, _r.uniform(0.1, 0.5)]), 3),
            "sweep_x_speed": round(_r.uniform(0.1, 0.6), 3),
            "sweep_y_speed": round(_r.uniform(0.1, 0.6), 3),
            # duplicator: often single, sometimes 2-4
            "dup_count": float(_r.choice([1, 1, 1, 2, 3, 4])),
            "dup_spread": round(_r.uniform(0.2, 0.8), 3),
            "dup_scale": round(_r.uniform(0.4, 1.0), 3),
            "dup_spin": round(_r.uniform(0.4, 0.6), 3),
            "dup_mirror_x": float(_r.random() < 0.3),
            "dup_mirror_y": float(_r.random() < 0.3),
            # colour / dots
            "mono": float(_r.random() < 0.3),
            "dotify": round(_r.choice([0, 0, 0, _r.uniform(0.3, 0.8)]), 3),
            "brightness": round(_r.uniform(0.7, 1.0), 3),
            # oscillator: 50% chance active
            "lfo_target": float(_r.randint(0, len(LFO_TARGETS) - 1)),
            "lfo_wave": float(_r.randint(0, len(LFO_WAVES) - 1)),
            "lfo_rate": round(_r.uniform(0.1, 0.6), 3),
            "lfo_depth": round(_r.choice([0, 0, _r.uniform(0.2, 0.6)]), 3),
            "lfo_dropoff": round(_r.uniform(0, 0.5), 3),
            # audio routing: random destinations
            "aud_bass_dest": float(_r.randint(0, len(AUDIO_DESTS) - 1)),
            "aud_mid_dest": float(_r.randint(0, len(AUDIO_DESTS) - 1)),
            "aud_high_dest": float(_r.randint(0, len(AUDIO_DESTS) - 1)),
            "audio_amt": round(_r.uniform(0.3, 0.7), 3),
        }
        return p


    def set_param(self, key, value):
        """External param change (fader/CC). Cancels any in-flight
        transition for that key so the user always wins."""
        # switching to a source shape (text/ILDA/vector) defaults spin to
        # stopped (0.5) — these are usually meant to sit still, not spin.
        if key == "shape":
            name = SHAPE_NAMES[int(value) % len(SHAPE_NAMES)]
            prev = SHAPE_NAMES[int(self.p.get("shape", 0)) % len(SHAPE_NAMES)]
            if name in ("text", "ilda", "vector") and name != prev:
                self.p["spin"] = 0.5
        self.p[key] = value
        if self._trans:
            self._trans["from"].pop(key, None)
            self._trans["to"].pop(key, None)

    def apply_params(self, params):
        """Load a full parameter set — snap, or glide if xfade is on."""
        clean = {k: float(v) for k, v in params.items() if k in self.p}
        if self.on_load:
            self.on_load()
        if self.xfade:
            self._trans = {"t": 0.0, "dur": max(0.05, self.xfade_time),
                           "from": {k: float(self.p[k]) for k in clean},
                           "to": clean}
        else:
            self._trans = None
            self.p.update(clean)

    def _advance_transition(self, dt):
        tr = self._trans
        if not tr:
            return
        tr["t"] += dt
        u = min(1.0, tr["t"] / tr["dur"])
        e = u * u * (3.0 - 2.0 * u)          # smoothstep
        for k, tv in tr["to"].items():
            fv = tr["from"].get(k, tv)
            if k in self.DISCRETE:
                self.p[k] = tv if u >= 0.5 else fv
            elif k == "hue":                  # circular: short way round
                d = ((tv - fv + 0.5) % 1.0) - 0.5
                self.p[k] = (fv + d * e) % 1.0
            else:
                self.p[k] = fv + (tv - fv) * e
        if u >= 1.0:
            self._trans = None

    def _apply_lfo(self, dt):
        """Advance the oscillator and return an effective param dict with
        the target parameter modulated around its current (fader) value.
        Returns self.p unchanged when depth is zero."""
        p = self.p
        depth = p.get("lfo_depth", 0.0)
        if depth <= 1e-4:
            return p
        self.lfo_phase = (self.lfo_phase + p["lfo_rate"] * 2.0 * dt) % 1.0
        ph = self.lfo_phase
        wave = int(round(p.get("lfo_wave", 0))) % len(LFO_WAVES)
        if wave == 0:                                   # sine
            s = np.sin(ph * TWO_PI)
        elif wave == 1:                                 # triangle
            s = 4.0 * abs(ph - 0.5) - 1.0
        elif wave == 2:                                 # square
            s = 1.0 if ph < 0.5 else -1.0
        elif wave == 3:                                 # saw
            s = 2.0 * ph - 1.0
        else:                                           # random sample & hold
            if ph < getattr(self, "_lfo_last_ph", 1.0):
                self._lfo_sh = np.random.uniform(-1.0, 1.0)
            self._lfo_last_ph = ph
            s = getattr(self, "_lfo_sh", 0.0)
        # dropoff: decay the swing across each cycle so it "settles"
        drop = p.get("lfo_dropoff", 0.0)
        if drop > 1e-4:
            s *= (1.0 - drop * ph)

        tgt = LFO_TARGETS[int(round(p.get("lfo_target", 0))) % len(LFO_TARGETS)]
        lo, hi = PARAM_BOUNDS.get(tgt, (0.0, 1.0))
        eff = dict(p)
        base = p[tgt]
        eff[tgt] = float(np.clip(base + s * depth * (hi - lo) * 0.5, lo, hi))
        return eff

    def set_text(self, string, style):
        """Render text to the cached text frame (called on change only)."""
        from text import render_text, STYLES
        # keep up to 4 lines, each capped at 32 chars
        lines = (string or "").split("\n")[:4]
        self.text_str = "\n".join(ln[:32] for ln in lines)
        self.text_style = int(style) % len(STYLES)
        self.text_frame = render_text(self.text_str,
                                      STYLES[self.text_style],
                                      self.n_points)

    def set_ilda(self, frames, name):
        """Install a parsed ILDA file as the playback source."""
        self.ilda_pos = 0.0
        self.ilda_frames = frames
        self.ilda_name = name

    @staticmethod
    def _placeholder(n):
        t = np.linspace(0, TWO_PI, n, endpoint=False)
        return np.cos(t), np.sin(t), None, None

    @staticmethod
    def _resample_src(fr, n):
        """Resample a source frame dict {"x","y","rgb","lit"} to n points."""
        N = len(fr["x"])
        if N < 2:
            return ShapeEngine._placeholder(n)
        idx = np.linspace(0, N - 1, n)
        x = np.interp(idx, np.arange(N), fr["x"])
        y = np.interp(idx, np.arange(N), fr["y"])
        ni = np.clip(np.round(idx).astype(int), 0, N - 1)
        return x, y, fr["rgb"][ni], fr["lit"][ni]

    def _ilda_points(self, n, dt, rate):
        """Current ILDA frame resampled to n points. ilda_mode selects
        loop (0), ping-pong (1), or single/hold-last (2) playback."""
        frames = self.ilda_frames
        if not frames:
            return self._placeholder(n)
        L = len(frames)
        adv = rate * 24.0 * dt
        mode = int(round(self.p["ilda_mode"]))
        if mode == 1 and L > 1:                    # ping-pong
            self.ilda_pos = (self.ilda_pos + adv) % (2 * L)
            pp = self.ilda_pos
            idx = int(pp) if pp < L else int(2 * L - pp - 1e-9)
        elif mode == 2:                            # single: hold last frame
            self.ilda_pos = min(self.ilda_pos + adv, L - 1e-6)
            idx = int(self.ilda_pos)
        else:                                      # loop
            self.ilda_pos = (self.ilda_pos + adv) % L
            idx = int(self.ilda_pos)
        return self._resample_src(frames[min(idx, L - 1)], n)

    def frame(self, dt, audio=None):
        """
        audio: dict with keys rms, bass, mid, high (0..1-ish) and wave
               (float32 array, -1..1), or None.
        Returns (N,6) int array: x,y 0..4095, r,g,b,i 0..255.
        """
        if self.paused:
            dt = 0.0
        self._advance_transition(dt)
        p = self._apply_lfo(dt)
        n_total = self.n_points

        # --- duplicator point budget --------------------------------------
        # Total points stay ~n_points so the pps/fps maths holds. Copies are
        # joined by short blanked "bridge" runs so the galvos can travel
        # between them with the beam off.
        count = int(np.clip(round(p["dup_count"]), 1, 6))
        if count > 1:
            bridge = max(4, n_total // 120)
            n = max(16, (n_total - count * bridge) // count)
        else:
            bridge = 0
            n = n_total

        # --- audio modulation -------------------------------------------
        # audio_off is the master kill switch: when set, the visuals see no
        # audio at all (mods frozen AND scope falls back to its idle shapes).
        if p.get("audio_off", 0.0) > 0.5:
            audio = None
        amt = p["audio_amt"]
        bass = mid = high = 0.0
        wave_data = None
        if audio:
            bass, mid, high = audio["bass"], audio["mid"], audio["high"]
            wave_data = audio.get("wave")

        # --- routable audio modulation ------------------------------------
        # Each band drives a chosen destination parameter additively. We
        # accumulate per-parameter modulation, then apply it to a working
        # copy so the base (fader) values are never overwritten.
        p_mod = dict(p)
        audio_mod = {}   # param -> additive amount (already ×amt)
        if audio:
            for band_val, dest_key in (
                    (bass, "aud_bass_dest"),
                    (mid, "aud_mid_dest"),
                    (high, "aud_high_dest")):
                di = int(round(p.get(dest_key, 0))) % len(AUDIO_DESTS)
                dest = AUDIO_DESTS[di]
                if dest == "off":
                    continue
                lo, hi = PARAM_BOUNDS.get(dest, (0.0, 1.0))
                audio_mod[dest] = audio_mod.get(dest, 0.0) + \
                    amt * band_val * (hi - lo) * 0.6
        for k, add in audio_mod.items():
            lo, hi = PARAM_BOUNDS.get(k, (0.0, 1.0))
            p_mod[k] = float(np.clip(p[k] + add, lo, hi))
        # size is read separately below (needs the modulated value)
        size = np.clip(p_mod.get("size", p["size"]), 0.02, 1.0)
        # when linked, Y tracks X (the size fader); else Y is independent
        if p.get("size_link", 1.0) > 0.5:
            size_y = size
        else:
            size_y = np.clip(p_mod.get("size_y", p["size_y"]), 0.02, 1.0)

        # --- generate curve ----------------------------------------------
        name = SHAPE_NAMES[int(p["shape"]) % len(SHAPE_NAMES)]
        src_rgb = src_lit = None
        if self.test_frame is not None:
            x, y, src_rgb, src_lit = self._resample_src(self.test_frame, n)
        elif name == "ilda":
            x, y, src_rgb, src_lit = self._ilda_points(n, dt, p["ilda_rate"])
        elif name == "vector":
            fr = self.vector_frame
            if fr is None:
                x, y, src_rgb, src_lit = self._placeholder(n)
            else:
                x, y, src_rgb, src_lit = self._resample_src(fr, n)
        elif name == "text":
            fr = self.text_frame
            if fr is None:
                x, y, src_rgb, src_lit = self._placeholder(n)
            else:
                x, y, src_rgb, src_lit = self._resample_src(fr, n)
        elif name == "scope":
            x, y = scope(n, self.phase, p_mod, audio)
        else:
            fn = {"lissajous": lissajous, "rose": rose,
                  "hypotrochoid": hypotrochoid, "wave": wave,
                  "harmonograph": harmonograph,
                  "polygon": polygon}[name]
            x, y = fn(n, self.phase, p_mod)

        # --- rotate + scale ----------------------------------------------
        spin = (p_mod["spin"] - 0.5) * 4.0        # -2..2 rad/s (audio-routable)
        self.rot = (self.rot + spin * dt) % TWO_PI
        # static rotate offset (0..1 -> 0..2pi), added to the spinning angle
        angle = self.rot + p_mod.get("rotate", 0.0) * TWO_PI
        c, s = np.cos(angle), np.sin(angle)
        xr = (x * c - y * s) * size
        yr = (x * s + y * c) * size_y

        # --- duplicate: copies on an orbiting ring, with size falloff -----
        if count > 1:
            self.ring_phase = (self.ring_phase
                               + (p["dup_spin"] - 0.5) * 3.0 * dt) % TWO_PI
            radius = p_mod["dup_spread"] * 0.8
            falloff = 0.4 + 0.6 * p["dup_scale"]   # per-copy scale multiplier
            segs_x, segs_y, lit, rgb_segs = [], [], [], []
            copy_lit = src_lit if src_lit is not None                 else np.ones(len(xr), bool)
            mx = p["dup_mirror_x"] > 0.5
            my = p["dup_mirror_y"] > 0.5
            copies = []
            for k in range(count):
                a = self.ring_phase + TWO_PI * k / count
                sc = falloff ** k
                kx = -xr if (mx and k % 2) else xr
                ky = -yr if (my and k % 2) else yr
                copies.append((kx * sc + radius * np.cos(a),
                               ky * sc + radius * np.sin(a)))
            for k in range(count):
                cx, cy = copies[k]
                nx, ny = copies[(k + 1) % count]
                # lit copy, then a blanked travel move to the next copy
                bx = np.linspace(cx[-1], nx[0], bridge, endpoint=False)
                by = np.linspace(cy[-1], ny[0], bridge, endpoint=False)
                segs_x += [cx, bx]
                segs_y += [cy, by]
                lit += [copy_lit, np.zeros(bridge, bool)]
                if src_rgb is not None:
                    rgb_segs += [src_rgb, np.zeros((bridge, 3), np.float32)]
            xr = np.concatenate(segs_x)
            yr = np.concatenate(segs_y)
            lit = np.concatenate(lit)
            if src_rgb is not None:
                src_rgb = np.concatenate(rgb_segs)
        else:
            lit = src_lit if src_lit is not None else np.ones(len(xr), bool)
        total = len(xr)

        # --- dotify: chop the beam into dots --------------------------------
        if p_mod["dotify"] > 0.001:
            period = 8
            on = max(1, int(round((1.0 - p_mod["dotify"]) * period)))
            lit = lit & ((np.arange(total) % period) < on)

        # --- position + auto sweep (independent X and Y) ------------------
        self.sweep_x_phase += p["sweep_x_speed"] * 2.5 * dt
        self.sweep_y_phase += p["sweep_y_speed"] * 2.5 * dt
        ox = (p_mod["pos_x"] - 0.5) * 1.8 + p["sweep_x"] * 0.9 * np.sin(
            self.sweep_x_phase)
        oy = (p_mod["pos_y"] - 0.5) * 1.8 + p["sweep_y"] * 0.9 * np.sin(
            self.sweep_y_phase)
        xr += ox
        yr += oy

        self.phase += dt
        self.hue_phase = (self.hue_phase + p["hue_cycle"] * dt * 0.5) % 1.0

        # --- colour -------------------------------------------------------
        bright = np.clip(p_mod["brightness"], 0, 1)
        if src_rgb is not None and p["mono"] <= 0.5:
            # ILDA file colours, scaled by brightness/audio
            r = src_rgb[:, 0] * bright
            g = src_rgb[:, 1] * bright
            b = src_rgb[:, 2] * bright
        else:
            if p["mono"] > 0.5:
                # single-colour output: hue fader (hue cycle animates it)
                hue = np.full(total, (p_mod["hue"] + self.hue_phase) % 1.0)
            else:
                hue = (p_mod["hue"] + self.hue_phase
                       + np.linspace(0, 1, total, endpoint=False)) % 1.0
            r, g, b = _hsv_to_rgb(hue, 1.0, bright)
        r, g, b = r * lit, g * lit, b * lit    # bridges/blanking stay dark

        # --- pack to Helios ranges (axis flips applied here so they -------
        # --- mirror everything, position and sweep included) --------------
        out = np.empty((total, 6), dtype=np.int32)
        xi = np.clip((xr * 0.5 + 0.5) * 0xFFF, 0, 0xFFF).astype(np.int32)
        yi = np.clip((yr * 0.5 + 0.5) * 0xFFF, 0, 0xFFF).astype(np.int32)
        out[:, 0] = (0xFFF - xi) if p["flip_x"] > 0.5 else xi
        out[:, 1] = (0xFFF - yi) if p["flip_y"] > 0.5 else yi
        out[:, 2] = (r * 255).astype(np.int32)
        out[:, 3] = (g * 255).astype(np.int32)
        out[:, 4] = (b * 255).astype(np.int32)
        out[:, 5] = (lit * int(np.clip(p["brightness"], 0, 1) * 255)
                     ).astype(np.int32)
        return out


def _hsv_to_rgb(h, s, v):
    """Vectorised HSV→RGB, h array 0..1, s/v scalars or arrays."""
    i = np.floor(h * 6.0).astype(int) % 6
    f = h * 6.0 - np.floor(h * 6.0)
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    v = np.broadcast_to(v, h.shape).astype(float)
    p = np.broadcast_to(p, h.shape).astype(float)
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return r, g, b
