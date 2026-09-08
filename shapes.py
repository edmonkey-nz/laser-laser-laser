"""
shapes.py — vector shape oscillators for the laser synth.

Every generator returns (x, y) in [-1, 1] for a closed curve sampled at
n points, given a continuously-advancing phase. Closed curves need no
blanking, which keeps the Helios pipeline simple and the beam bright.
"""

import numpy as np

TWO_PI = 2.0 * np.pi

SHAPE_NAMES = ["lissajous", "rose", "hypotrochoid", "wave", "harmonograph",
               "polygon", "scope", "ilda", "vector", "text", "custom",
               "superformula", "maurer", "knot"]
# NOTE: append only. The index is p["shape"], is persisted in patterns.json
# and is bound to MIDI notes from NOTE_SHAPE_BASE — inserting mid-list
# silently rewrites the shape of every saved pattern.

MAX_CUSTOM_POINTS = 64


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


def custom_polygon(n, phase, points):
    """User-clicked polygon: straight edges connecting the given points in
    click order, closed back to the first point. points is a list of
    (x, y) pairs in [-1, 1]. Resampled to n points at equal arc length,
    same as the regular `polygon` shape, so beam brightness stays even."""
    if not points or len(points) < 2:
        t = np.linspace(0, TWO_PI, n, endpoint=False)
        return 0.15 * np.cos(t), 0.15 * np.sin(t)
    pts = np.asarray(points, dtype=float)
    pts = np.vstack([pts, pts[:1]])          # close the loop
    vx, vy = pts[:, 0], pts[:, 1]
    seg = np.hypot(np.diff(vx), np.diff(vy))
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    if cum[-1] < 1e-9:
        return np.full(n, vx[0]), np.full(n, vy[0])
    s = np.linspace(0, cum[-1], n, endpoint=False)
    x = np.interp(s, cum, vx)
    y = np.interp(s, cum, vy)
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


def _resample_closed(x, y, n):
    """Resample a closed polyline to n points at equal arc length.

    Even spacing is two things at once here: even beam brightness, and no
    bunching of samples. Bunched samples on a laser are a slow-moving or
    stationary beam, which docs/SAFETY.md §6 treats as a burn risk rather
    than a visual artifact. Same idiom as `polygon`.
    """
    px = np.concatenate([x, x[:1]])
    py = np.concatenate([y, y[:1]])
    seg = np.hypot(np.diff(px), np.diff(py))
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    if cum[-1] < 1e-9:
        # degenerate: the figure collapsed to a point. Never return that —
        # it is exactly the parked beam the arc-length spacing exists to
        # avoid. Fall back to a small circle, as custom_polygon does.
        t = np.linspace(0, TWO_PI, n, endpoint=False)
        return 0.15 * np.cos(t), 0.15 * np.sin(t)
    s = np.linspace(0, cum[-1], n, endpoint=False)
    return np.interp(s, cum, px), np.interp(s, cum, py)


def superformula(n, phase, p):
    """
    Gielis superformula — one equation that morphs continuously through
    circles, polygons, stars, flowers and blobs:

        r(t) = (|cos(m·t/4)|^n2 + |sin(m·t/4)|^n3) ^ (-1/n1)

    ratio_a = m, the symmetry, rounded to an integer so the curve closes.
    ratio_b = n1, morph = n2/n3 together. Sweeping morph from the LFO or
    an audio band walks the whole family, which is the point of it.

    The exponents are held inside the well-behaved region: outside it r
    spikes hard, and after normalising a spike the rest of the curve
    collapses toward the origin — points bunch, the beam slows. The
    arc-length resample is the second line of defence against that.
    """
    t = np.linspace(0, TWO_PI, n, endpoint=False)
    m = max(1, round(p["ratio_a"]))
    n1 = 0.3 + (np.clip(p["ratio_b"], 1.0, 12.0) - 1.0) / 11.0 * 3.7
    n23 = 0.3 + np.clip(p["morph"], 0.0, 1.0) * 3.7
    a = np.abs(np.cos(m * t / 4.0)) ** n23
    b = np.abs(np.sin(m * t / 4.0)) ** n23
    base = np.maximum(a + b, 1e-6)
    r = base ** (-1.0 / n1)
    r = np.clip(r, 0.0, 1e3)
    mx = max(np.max(r), 1e-6)
    return _resample_closed(r * np.cos(t) / mx, r * np.sin(t) / mx, n)


# Maurer-rose degree steps, ordered sparse -> dense, selected by ratio_b.
#
# Two things have to be true of a good step. It must be *large*, or the
# chords are short, hug the rose outline and no lattice forms. And it must
# share a factor with 360, because the walk closes after 360/gcd(d, 360)
# chords — that quotient is the chord count, and the chord count is what
# decides whether a projector can actually draw the figure.
#
# At 800 points a 360-chord rose gets 2.2 points per chord: roughly 88 us
# for the galvos to cross the field, which they cannot do, so the lattice
# comes out blurred and dim rather than crisp. Every step here is large
# enough to make a lattice, and ratio_b walks the chord count from 20
# (40 points each, clean on anything) up to the classic dense 360.
MAURER_STEPS = [54, 75, 84, 99, 88, 66, 85, 76, 51, 38, 71, 97]


def maurer(n, phase, p):
    """
    Maurer rose: walk the k-petal rose r = sin(k*theta) in fixed d-degree
    steps and join consecutive positions with straight chords. The chords
    interfere into a dense moire lattice — a great deal of structure out
    of two integers.

    The walk closes after 360/gcd(d, 360) chords: at that point k*d is a
    multiple of 360 and it lands back on its first vertex. Walking further
    only retraces, so the chord count is exactly that quotient and the
    whole point budget goes on chords that are actually distinct.

    ratio_a = petals. ratio_b = which lattice, ordered sparse to dense:
    low values draw 20-45 chords and scan cleanly on any projector, high
    values draw the classic 360-chord rose and want the point count raised
    to match (Settings, or the per-pattern override).
    """
    from math import gcd
    k = max(1, round(p["ratio_a"]))
    di = int(np.clip(round(p["ratio_b"]), 1, 12)) - 1
    d = MAURER_STEPS[di % len(MAURER_STEPS)]
    chords = 360 // gcd(d, 360)
    theta = np.arange(chords) * d * np.pi / 180.0
    r = np.sin(k * theta)
    return _resample_closed(r * np.cos(theta), r * np.sin(theta), n)


def knot(n, phase, p):
    """
    (p,q) torus knot — a genuinely 3D closed curve. Returns a third array
    z, which the tilt/tumble stage projects. That is the whole point: the
    beam has no shading, so parallax from a curve rotating in space is
    the only depth cue a laser has, and it is a convincing one. A flat
    projection tumbled instead reads as a spinning picture of a knot.

    ratio_a = p (turns around the torus axis), ratio_b = q (turns through
    the hole), morph = tube radius. p and q are forced coprime — a
    non-coprime pair traces the same loop gcd(p,q) times over one period,
    which spends the point budget on a retrace. It stays closed either
    way, so this is about points, not safety.
    """
    from math import gcd
    pp = int(np.clip(round(p["ratio_a"]), 2, 12))
    qq = int(np.clip(round(p["ratio_b"]), 1, 12))
    if gcd(pp, qq) != 1:
        qq = 1
    t = np.linspace(0, TWO_PI, n, endpoint=False)
    tube = 0.25 + 0.45 * np.clip(p["morph"], 0.0, 1.0)
    r = 1.0 + tube * np.cos(qq * t)
    m = 1.0 + tube
    return (r * np.cos(pp * t) / m,
            r * np.sin(pp * t) / m,
            tube * np.sin(qq * t) / m)


SCOPE_MODES = ["waveform", "vu meter", "spectrum", "radial", "xy"]

# parameters the oscillator (LFO) can modulate, and their display order.
# Append only — the index is stored in patterns.json, and the display names
# are mirrored by hand in static/index.html (they are not sent over the wire).
LFO_TARGETS = ["morph", "size", "hue", "ratio_a", "ratio_b", "spin",
               "pos_x", "pos_y", "dup_spread", "dotify",
               "warp_amt", "tilt_y", "chase_amt", "dup_scale"]
LFO_WAVES = ["sine", "triangle", "square", "saw", "random"]

# audio band routing: each band (bass/mid/high) can drive one destination.
# "size+", "morph+" etc. are additive modulations of that parameter.
# Append only, same reasons as LFO_TARGETS.
AUDIO_DESTS = ["off", "size", "morph", "brightness", "hue", "spin",
               "dup_spread", "dotify", "pos_x", "pos_y", "ratio_a",
               "warp_amt", "chase_amt", "persp", "dup_scale"]

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
    "warp_amt": (0.0, 1.0), "warp_freq": (1.0, 12.0),
    "tilt_x": (0.0, 1.0), "tilt_y": (0.0, 1.0), "persp": (0.0, 1.0),
    "chase_amt": (0.0, 1.0), "dup_scale": (0.0, 1.0),
}

# Ripple warp: maximum displacement along the curve normal, in normalised
# units. Capped well below the point where a fold would push neighbouring
# samples onto each other — folded samples are a beam that stops moving.
WARP_MAX = 0.35

# Perspective: floor on the projection denominator. Without it a point
# crossing the eye plane sends the divide to infinity, the coordinates
# clip flat against the edge of the field, and a whole run of samples
# lands on one DAC coordinate — a parked beam.
PERSP_MIN_W = 0.3

# 3D: the smallest fraction of its incoming extent the tilt/tumble stage is
# allowed to shrink a figure to. A flat shape (z = 0) seen exactly edge-on
# collapses to a line, and a shape that is itself a line — lissajous at 1:1,
# polygon with 1 or 2 sides, a flat wave — collapses all the way to a point.
# Measured without this guard: an entire 800-point frame on one DAC
# coordinate. That is a parked beam, which docs/SAFETY.md §6 rules out
# outright, so the stage is not allowed to reach it.
MIN_3D_EXTENT = 0.2

# 3D: how thin a *flat* shape is allowed to get as it turns toward edge-on.
# At exactly edge-on a flat figure becomes a perfect line, and on a line the
# samples pile up wherever the parametrisation turns around — lissajous
# measured 52 lit points on one coordinate that way. A shape that supplies a
# real z (like `knot`) has genuine thickness and is left alone: clamping it
# would break an honest rotation.
MIN_FLAT_COS = 0.15


def _flat_foreshorten(c):
    """Foreshortening factor for a flat shape, kept off zero.

    Note this returns |cos| rescaled, never a negative value. Clamping the
    signed cosine instead — max(|c|, floor) with the sign kept — is what an
    earlier version did, and it read badly: the width sat pinned at the
    floor for the whole range where |cos| < floor (a visible stall), then
    the sign flipped and the figure jumped to its mirror image. Folding
    through |cos| removes both. The shape thins to the floor at exactly
    edge-on and immediately opens out again, continuously and at a constant
    angular rate, which is what a card turning in space actually looks
    like. It no longer mirrors as it passes through, and for a flat figure
    that is the better trade.
    """
    return MIN_FLAT_COS + (1.0 - MIN_FLAT_COS) * abs(c)


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

    @staticmethod
    def default_params():
        """The factory defaults, in one place so __init__ and the
        master reset cannot drift apart."""
        return {
            "shape": 0,
            "ratio_a": 3.0, "ratio_b": 2.0,
            "morph": 0.25, "spin": 0.5,   # 0.5 = stopped (bipolar)
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
            # ripple warp — displaces points along the curve normal
            "warp_amt": 0.0,    # 0 = off
            "warp_freq": 3.0,   # ripples around the curve (1..12, integer)
            "warp_speed": 0.5,  # travel speed, bipolar around 0.5
            # 3D tilt / tumble — depth by parallax
            # 0.5 is neutral (0 degrees) — the stage must be a no-op at
            # its defaults, or every existing pattern would come back tilted
            "tilt_x": 0.5,      # static tilt about X (0..1 = -180..180)
            "tilt_y": 0.5,      # static tilt about Y
            "tumble": 0.5,      # continuous Y-axis tumble, bipolar
            "persp": 0.0,       # perspective strength (0 = flat/orthographic)
            # comet chase — a brightness envelope travelling along the path
            "chase_amt": 0.0,   # 0 = off, 1 = only the comet is lit
            "chase_speed": 0.6,  # bipolar around 0.5
            # per-panel bypasses (1 = enabled). These mute a whole stage
            # while leaving its faders where the user left them, so the
            # panel can be switched back on without losing the setup.
            # Audio has no equivalent key on purpose — audio_off already
            # is one, and two competing kill switches would be worse.
            "fx_on": 1.0,       # Effects: ripple, 3D tilt/tumble, comet
            "dup_on": 1.0,      # Duplicator
            "lfo_on": 1.0,      # Oscillator
            "mono": 0.0,        # >0.5 = single-colour output from hue fader
            "flip_x": 0.0,      # >0.5 = mirror horizontally
            "flip_y": 0.0,      # >0.5 = mirror vertically
        }

    def __init__(self, n_points=800):
        self.n_points = n_points
        self.phase = 0.0        # shape-internal drift
        self.rot = 0.0          # rotation angle
        self.hue_phase = 0.0
        self.blanked = False    # master blank — zeroes all colour output
        self.p = self.default_params()
        self.ring_phase = 0.0
        self.tumble_phase = 0.0   # 3D tumble angle accumulator
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
        self.custom_points = []   # user-clicked polygon points [[x,y], ...]
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
                "size_link", "fx_on", "dup_on", "lfo_on"}

    @staticmethod
    def random_params():
        """Generate a random but musically-sensible parameter set drawn
        from all synth options EXCEPT ILDA and vector (which need external
        files). Returns a params dict suitable for a pattern."""
        import random as _r
        # shapes minus ilda/vector/scope (scope needs audio to be interesting)
        pickable = [s for s in SHAPE_NAMES
                    if s not in ("ilda", "vector", "scope", "custom")]
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
            # ripple warp: usually off, sometimes a gentle swell
            "warp_amt": round(_r.choice([0, 0, 0, _r.uniform(0.2, 0.7)]), 3),
            "warp_freq": float(_r.randint(2, 9)),
            "warp_speed": round(_r.uniform(0.3, 0.7), 3),
            # 3D: occasionally tilt into depth and tumble
            "tilt_x": round(_r.choice([0.5, 0.5, _r.uniform(0.2, 0.8)]), 3),
            "tilt_y": round(_r.choice([0.5, 0.5, _r.uniform(0.2, 0.8)]), 3),
            "tumble": round(_r.choice([0.5, 0.5, _r.uniform(0.4, 0.6)]), 3),
            "persp": round(_r.choice([0, 0, _r.uniform(0.3, 0.9)]), 3),
            # comet chase: occasional
            "chase_amt": round(_r.choice([0, 0, 0, _r.uniform(0.4, 0.9)]), 3),
            "chase_speed": round(_r.uniform(0.55, 0.8), 3),
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


    def reset_phases(self):
        """Rewind every running animation accumulator to its start.

        These are the engine's *motion* state, not parameters: the spin
        angle, the hue rotation, the duplicator's orbit, the sweep
        oscillators, the 3D tumble, the shape phase that drives the ripple
        and the comet, and the oscillator's own phase. None of them are
        stored in a pattern, so without this a recalled pattern renders at
        whatever attitude the session happened to have reached — a figure
        saved with spin stopped and a deliberate `rotate` offset came back
        tens of degrees out, because `rot` had kept the angle it spun to
        earlier. Rewinding them is what makes a pattern reproduce the look
        it was saved with.
        """
        self.rot = 0.0
        self.phase = 0.0
        self.hue_phase = 0.0
        self.ring_phase = 0.0
        self.tumble_phase = 0.0
        self.lfo_phase = 0.0
        self.sweep_x_phase = 0.0
        self.sweep_y_phase = 0.0

    def reset_params(self):
        """Master reset: every parameter back to its factory default.

        Snaps rather than crossfading, and cancels any transition in
        flight — a reset that eased in over two seconds would be worse
        than useless when the point of pressing it is to get back to
        something known. The running phases are reset too, so spin and
        tumble return to their starting angles instead of leaving the
        figure at whatever attitude it had reached.

        Installed sources (text, ILDA, the custom polygon, the vectoriser
        frame) are left alone. They are content, not settings, and
        reloading a file the user picked is not what this button is for.
        """
        self._trans = None
        self.p = self.default_params()
        self.reset_phases()

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
            # Snapping to a pattern means "give me this look". The stored
            # parameters alone do not do that: the animation phases below
            # are session state, and a figure with spin stopped would come
            # back rotated by however far it had spun earlier. Rewind them.
            # A crossfade deliberately does not — its whole job is to glide
            # from where things are, and snapping the phases mid-glide is
            # the jump it exists to avoid.
            self.reset_phases()

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
        if depth <= 1e-4 or p.get("lfo_on", 1.0) <= 0.5:
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

    def set_custom_points(self, points):
        """Install a user-clicked point list (list of [x, y] pairs, each
        -1..1). Capped so a runaway click session can't bloat the pattern
        file or the per-frame resample cost."""
        clean = []
        for pt in points[:MAX_CUSTOM_POINTS]:
            x, y = pt
            clean.append([float(np.clip(x, -1.0, 1.0)),
                          float(np.clip(y, -1.0, 1.0))])
        self.custom_points = clean

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
        if p.get("dup_on", 1.0) <= 0.5:
            count = 1
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
        zc = None               # depth column, if the generator supplies one
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
        elif name == "custom":
            x, y = custom_polygon(n, self.phase, self.custom_points)
        else:
            fn = {"lissajous": lissajous, "rose": rose,
                  "hypotrochoid": hypotrochoid, "wave": wave,
                  "harmonograph": harmonograph,
                  "polygon": polygon, "superformula": superformula,
                  "maurer": maurer, "knot": knot}[name]
            # a generator may return a third array z (see `knot`); flat
            # shapes return two and sit at z = 0.
            res = fn(n, self.phase, p_mod)
            if len(res) == 3:
                x, y, zc = res
            else:
                x, y = res
                zc = None

        # --- effects bypass -----------------------------------------------
        # One flag for the whole Effects panel. The faders keep their values
        # so the panel can be switched back on without losing the setup.
        fx_on = p.get("fx_on", 1.0) > 0.5

        # --- ripple warp: displace along the curve normal ------------------
        # Indexed by point number rather than polar angle, so it works on
        # open curves ("wave"), off-centre curves and source frames alike.
        # An integer cycle count is what keeps a closed curve closed.
        warp = np.clip(p_mod.get("warp_amt", 0.0), 0.0, 1.0)
        if fx_on and warp > 1e-4:
            k = max(1, round(p_mod.get("warp_freq", 3.0)))
            u = np.arange(len(x)) / max(1, len(x))
            d = (warp * WARP_MAX) * np.sin(
                TWO_PI * k * u
                + self.phase * (p.get("warp_speed", 0.5) - 0.5) * 6.0)
            # unit normal from the local tangent
            tx, ty = np.gradient(x), np.gradient(y)
            mag = np.maximum(np.hypot(tx, ty), 1e-9)
            x = x + d * (-ty / mag)
            y = y + d * (tx / mag)

        # --- rotate + scale ----------------------------------------------
        spin = (p_mod["spin"] - 0.5) * 4.0        # -2..2 rad/s (audio-routable)
        self.rot = (self.rot + spin * dt) % TWO_PI
        # static rotate offset (0..1 -> 0..2pi), added to the spinning angle
        angle = self.rot + p_mod.get("rotate", 0.0) * TWO_PI
        c, s = np.cos(angle), np.sin(angle)
        xr = (x * c - y * s) * size
        yr = (x * s + y * c) * size_y

        # --- 3D tilt + tumble ---------------------------------------------
        # Placed before the duplicator so each copy reads as its own solid
        # object. The beam has no shading, so parallax is the only depth
        # cue a laser has — and it is a strong one.
        self.tumble_phase = (self.tumble_phase
                             + (p["tumble"] - 0.5) * 2.0 * dt) % TWO_PI
        ax = (p_mod["tilt_x"] - 0.5) * TWO_PI if fx_on else 0.0
        ay = ((p_mod["tilt_y"] - 0.5) * TWO_PI + self.tumble_phase) \
            if fx_on else 0.0
        persp = np.clip(p_mod["persp"], 0.0, 1.0) if fx_on else 0.0
        if zc is None:
            zr = np.zeros(len(xr))
        else:
            zr = zc * size
        if abs(ax) > 1e-4 or abs(ay) > 1e-4 or persp > 1e-4:
            flat_x, flat_y = xr, yr        # kept for the collapse guard
            flat = zc is None
            cx_, sx_ = np.cos(ax), np.sin(ax)
            cy_, sy_ = np.cos(ay), np.sin(ay)
            if flat:
                cx_, cy_ = _flat_foreshorten(cx_), _flat_foreshorten(cy_)
            yr, zr = yr * cx_ - zr * sx_, yr * sx_ + zr * cx_
            xr, zr = xr * cy_ + zr * sy_, -xr * sy_ + zr * cy_
            if persp > 1e-4:
                # Bias z so the nearest point sits at the eye distance. The
                # denominator is then >= 1 everywhere, so the projection can
                # only ever shrink the figure — it can never expand it past
                # the edge of the field. That matters: coordinates driven
                # outside the field get clipped at pack time, and a clipped
                # run of samples piles onto one DAC coordinate, which is a
                # parked beam. PERSP_MIN_W is the belt-and-braces floor.
                w = 1.0 / np.maximum(1.0 + persp * (zr - zr.min()),
                                     PERSP_MIN_W)
                xr, yr = xr * w, yr * w
            # Collapse guard. Rotating a flat figure toward edge-on shrinks
            # it without limit, and a flat figure that is *itself* a line
            # (lissajous at 1:1, polygon with 1-2 sides) goes all the way to
            # a point — the whole frame on one coordinate, a parked beam.
            # Never let this stage shrink a figure past MIN_3D_EXTENT of
            # what it was given; below that, ease back toward the flat form,
            # which by definition still has the extent it came in with.
            pre = max(np.ptp(flat_x), np.ptp(flat_y))
            post = max(np.ptp(xr), np.ptp(yr))
            floor = MIN_3D_EXTENT * pre
            if pre > 1e-9 and post < floor:
                u3 = post / floor          # 0 = fully collapsed
                xr = u3 * xr + (1.0 - u3) * flat_x
                yr = u3 * yr + (1.0 - u3) * flat_y

        # --- duplicate: copies on an orbiting ring, with size falloff -----
        if count > 1:
            self.ring_phase = (self.ring_phase
                               + (p["dup_spin"] - 0.5) * 3.0 * dt) % TWO_PI
            radius = p_mod["dup_spread"] * 0.8
            # p_mod, not p: audio modulation is accumulated into p_mod
            # only, so reading the raw dict here would make falloff
            # routable in the menu but inert in the beam
            falloff = 0.4 + 0.6 * p_mod["dup_scale"]  # per-copy scale
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

        # --- off-field blanking -------------------------------------------
        # Anything outside the projection field gets clamped onto the
        # boundary by the np.clip at pack time, and a clamped run is a
        # stationary *lit* beam — the same parked-beam hazard as a dwell,
        # reached by a different route. Measured before this guard: 201 lit
        # points on one coordinate for a full-size lissajous at 1:1 rotated
        # 45 degrees (the diagonal becomes 2*sqrt(2) long and half of it
        # pins to the edge), and 41-120 for ordinary shapes pushed into a
        # corner with pos_x/pos_y.
        #
        # Blank what leaves the field instead of smearing it along the edge.
        # The galvos still travel the same path, the beam is simply off for
        # the part that is outside — which is also what should happen
        # visually: content off the edge of the field is not drawn.
        onfield = (np.abs(xr) <= 1.0 + 1e-9) & (np.abs(yr) <= 1.0 + 1e-9)
        lit = lit & onfield

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

        # --- comet chase: a brightness envelope travelling along the path --
        # Intensity only. The geometry and the point rate are untouched, so
        # the galvos keep moving at exactly the same speed — structurally
        # the same trade as dotify, which dims without ever parking the
        # beam. Turning it up narrows the comet and darkens the tail.
        chase = np.clip(p_mod["chase_amt"], 0.0, 1.0) if fx_on else 0.0
        env = None
        if chase > 1e-4:
            u = np.linspace(0, 1, total, endpoint=False)
            head = (self.phase * (p["chase_speed"] - 0.5) * 2.0) % 1.0
            dist = np.abs(((u - head + 0.5) % 1.0) - 0.5)   # wrapped distance
            width = 0.02 + 0.30 * (1.0 - 0.9 * chase)
            env = (1.0 - chase) + chase * np.exp(-(dist / width) ** 2)
            r, g, b = r * env, g * env, b * env

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
        out[:, 5] = (lit * (env if env is not None else 1.0)
                     * int(np.clip(p["brightness"], 0, 1) * 255)
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
