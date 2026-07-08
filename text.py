"""
text.py - single-stroke vector font for laser text rendering.

A compact Hershey-style stroke font (no fills - ideal for lasers): each
glyph is a set of polyline strokes on a 0..14 grid (baseline y=4, cap
top y=14, x-height y=10, descenders to y=0). Three styles are derived
from one base font for efficiency:

  plain    - the base single stroke
  script   - italic slant (shear transform)
  bold     - double-stroked outline (parallel offset copy per stroke)

Macron vowels for te reo Maori are composed from the base vowel plus a
macron bar, so they render in every style.

render_text(s, style) returns an engine source frame dict
{"x","y","rgb","lit"} in [-1,1], with blanked travel moves between
glyphs and strokes so the beam is off between letters.
"""

import numpy as np

# base glyphs: char -> (advance_width, [ [ [x,y], ... ], ... ])
_FONT = {
    " ": (8, []),
    "!": (5, [[[3, 14], [3, 7]], [[3, 4], [3, 5]]]),
    "&": (12, [[[10, 4], [4, 14], [2, 12], [4, 10], [8, 6], [6, 4], [3, 6], [6, 9], [10, 7]]]),
    "'": (4, [[[3, 14], [3, 11]]]),
    "(": (6, [[[6, 14], [3, 11], [3, 7], [6, 4]]]),
    ")": (6, [[[2, 14], [5, 11], [5, 7], [2, 4]]]),
    ",": (5, [[[3, 4], [2, 2]]]),
    "-": (8, [[[2, 9], [7, 9]]]),
    ".": (5, [[[2, 4], [2, 5]]]),
    "/": (8, [[[2, 4], [8, 14]]]),
    "0": (11, [[[4, 4], [2, 6], [2, 12], [4, 14], [8, 14], [10, 12], [10, 6], [8, 4], [4, 4]], [[4, 5], [8, 13]]]),
    "1": (8, [[[3, 12], [6, 14], [6, 4]], [[3, 4], [9, 4]]]),
    "2": (11, [[[2, 12], [4, 14], [8, 14], [10, 12], [10, 10], [2, 4], [10, 4]]]),
    "3": (11, [[[2, 12], [4, 14], [8, 14], [10, 12], [8, 9], [10, 6], [8, 4], [4, 4], [2, 6]], [[6, 9], [8, 9]]]),
    "4": (11, [[[8, 4], [8, 14], [2, 7], [11, 7]]]),
    "5": (11, [[[10, 14], [3, 14], [2, 9], [8, 9], [10, 7], [8, 4], [4, 4], [2, 6]]]),
    "6": (11, [[[9, 13], [6, 14], [3, 12], [2, 8], [2, 6], [4, 4], [8, 4], [10, 6], [8, 9], [4, 9], [2, 7]]]),
    "7": (10, [[[2, 14], [10, 14], [5, 4]]]),
    "8": (11, [[[4, 9], [2, 11], [4, 14], [8, 14], [10, 11], [8, 9], [4, 9], [2, 7], [4, 4], [8, 4], [10, 7], [8, 9]]]),
    "9": (11, [[[9, 7], [6, 4], [3, 6], [2, 10], [4, 13], [8, 14], [10, 11], [9, 7], [6, 9], [3, 8]]]),
    ":": (5, [[[3, 10], [3, 11]], [[3, 6], [3, 7]]]),
    "?": (9, [[[2, 12], [4, 14], [6, 14], [8, 12], [6, 9], [5, 9], [5, 7]], [[5, 4], [5, 5]]]),
    "A": (12, [[[1, 4], [6, 14], [11, 4]], [[3, 8], [9, 8]]]),
    "B": (11, [[[2, 4], [2, 14], [8, 14], [10, 12], [8, 9], [2, 9]], [[2, 9], [8, 9], [10, 6], [8, 4], [2, 4]]]),
    "C": (11, [[[10, 12], [8, 14], [4, 14], [2, 12], [2, 6], [4, 4], [8, 4], [10, 6]]]),
    "D": (11, [[[2, 4], [2, 14], [7, 14], [10, 11], [10, 7], [7, 4], [2, 4]]]),
    "E": (10, [[[10, 14], [2, 14], [2, 4], [10, 4]], [[2, 9], [7, 9]]]),
    "F": (10, [[[10, 14], [2, 14], [2, 4]], [[2, 9], [7, 9]]]),
    "G": (12, [[[10, 12], [8, 14], [4, 14], [2, 12], [2, 6], [4, 4], [8, 4], [10, 6], [10, 9], [7, 9]]]),
    "H": (11, [[[2, 4], [2, 14]], [[10, 4], [10, 14]], [[2, 9], [10, 9]]]),
    "I": (6, [[[3, 4], [9, 4]], [[6, 4], [6, 14]], [[3, 14], [9, 14]]]),
    "J": (9, [[[3, 6], [5, 4], [7, 4], [9, 6], [9, 14]], [[5, 14], [11, 14]]]),
    "K": (11, [[[2, 4], [2, 14]], [[10, 14], [2, 9], [10, 4]]]),
    "L": (9, [[[2, 14], [2, 4], [10, 4]]]),
    "M": (13, [[[2, 4], [2, 14], [7, 8], [12, 14], [12, 4]]]),
    "N": (12, [[[2, 4], [2, 14], [10, 4], [10, 14]]]),
    "O": (12, [[[4, 4], [2, 6], [2, 12], [4, 14], [8, 14], [10, 12], [10, 6], [8, 4], [4, 4]]]),
    "P": (10, [[[2, 4], [2, 14], [8, 14], [10, 12], [8, 9], [2, 9]]]),
    "Q": (12, [[[4, 4], [2, 6], [2, 12], [4, 14], [8, 14], [10, 12], [10, 6], [8, 4], [4, 4]], [[7, 7], [11, 3]]]),
    "R": (11, [[[2, 4], [2, 14], [8, 14], [10, 12], [8, 9], [2, 9]], [[6, 9], [10, 4]]]),
    "S": (11, [[[10, 12], [8, 14], [4, 14], [2, 12], [4, 9], [8, 9], [10, 6], [8, 4], [4, 4], [2, 6]]]),
    "T": (10, [[[1, 14], [11, 14]], [[6, 14], [6, 4]]]),
    "U": (11, [[[2, 14], [2, 7], [4, 4], [8, 4], [10, 7], [10, 14]]]),
    "V": (12, [[[1, 14], [6, 4], [11, 14]]]),
    "W": (14, [[[1, 14], [4, 4], [7, 10], [10, 4], [13, 14]]]),
    "X": (11, [[[2, 4], [10, 14]], [[10, 4], [2, 14]]]),
    "Y": (11, [[[1, 14], [6, 9], [11, 14]], [[6, 9], [6, 4]]]),
    "Z": (11, [[[2, 14], [10, 14], [2, 4], [10, 4]]]),
    "a": (10, [[[8, 4], [8, 10]], [[8, 8], [6, 10], [4, 10], [2, 8], [2, 6], [4, 4], [6, 4], [8, 6]]]),
    "b": (10, [[[2, 14], [2, 4]], [[2, 6], [4, 4], [7, 4], [9, 6], [9, 8], [7, 10], [4, 10], [2, 8]]]),
    "c": (9, [[[8, 9], [6, 10], [4, 10], [2, 8], [2, 6], [4, 4], [6, 4], [8, 5]]]),
    "d": (10, [[[8, 14], [8, 4]], [[8, 6], [6, 4], [3, 4], [1, 6], [1, 8], [3, 10], [6, 10], [8, 8]]]),
    "e": (9, [[[2, 7], [8, 7], [8, 9], [6, 10], [3, 10], [1, 8], [2, 5], [4, 4], [7, 4]]]),
    "f": (7, [[[6, 14], [4, 14], [3, 12], [3, 4]], [[1, 9], [6, 9]]]),
    "g": (10, [[[8, 10], [8, 2], [6, 0], [3, 0], [1, 2]], [[8, 8], [6, 10], [3, 10], [1, 8], [1, 6], [3, 4], [6, 4], [8, 6]]]),
    "h": (10, [[[2, 14], [2, 4]], [[2, 8], [4, 10], [7, 10], [9, 8], [9, 4]]]),
    "i": (4, [[[2, 10], [2, 4]], [[2, 12], [2, 13]]]),
    "j": (5, [[[3, 10], [3, 1], [1, 0]], [[3, 12], [3, 13]]]),
    "k": (9, [[[2, 14], [2, 4]], [[8, 10], [2, 7], [8, 4]]]),
    "l": (4, [[[2, 14], [2, 4]]]),
    "m": (13, [[[2, 10], [2, 4]], [[2, 8], [3, 10], [5, 10], [6, 8], [6, 4]], [[6, 8], [8, 10], [10, 10], [11, 8], [11, 4]]]),
    "n": (10, [[[2, 10], [2, 4]], [[2, 8], [4, 10], [7, 10], [9, 8], [9, 4]]]),
    "o": (10, [[[4, 4], [2, 6], [2, 8], [4, 10], [6, 10], [8, 8], [8, 6], [6, 4], [4, 4]]]),
    "p": (10, [[[2, 10], [2, 0]], [[2, 8], [4, 10], [7, 10], [9, 8], [9, 6], [7, 4], [4, 4], [2, 6]]]),
    "q": (10, [[[8, 10], [8, 0]], [[8, 8], [6, 10], [3, 10], [1, 8], [1, 6], [3, 4], [6, 4], [8, 6]]]),
    "r": (7, [[[2, 10], [2, 4]], [[2, 8], [4, 10], [6, 10]]]),
    "s": (9, [[[8, 9], [6, 10], [3, 10], [2, 8], [4, 7], [6, 7], [8, 6], [6, 4], [3, 4], [1, 5]]]),
    "t": (6, [[[3, 14], [3, 6], [4, 4], [6, 4]], [[1, 10], [6, 10]]]),
    "u": (10, [[[2, 10], [2, 6], [4, 4], [7, 4], [9, 6]], [[9, 10], [9, 4]]]),
    "v": (9, [[[1, 10], [5, 4], [9, 10]]]),
    "w": (12, [[[1, 10], [3, 4], [6, 8], [9, 4], [11, 10]]]),
    "x": (9, [[[2, 10], [8, 4]], [[8, 10], [2, 4]]]),
    "y": (9, [[[1, 10], [5, 4]], [[9, 10], [5, 4], [2, 0]]]),
    "z": (9, [[[2, 10], [8, 10], [2, 4], [8, 4]]]),
}

STYLES = ["plain", "script", "bold"]

_MACRONS = {
    "\u0100": "A", "\u0101": "a", "\u0112": "E", "\u0113": "e",
    "\u012a": "I", "\u012b": "i", "\u014c": "O", "\u014d": "o",
    "\u016a": "U", "\u016b": "u",
}


def _glyph(ch):
    if ch in _FONT:
        return _FONT[ch]
    if ch in _MACRONS:
        base = _MACRONS[ch]
        w, strokes = _FONT.get(base, _FONT["?"])
        strokes = [list(s) for s in strokes]
        y = 15.5 if base.isupper() else 12.0
        strokes = strokes + [[[2, y], [w - 2, y]]]
        return w, strokes
    up = ch.upper()
    if up in _FONT:
        return _FONT[up]
    return _FONT["?"]


def _style_strokes(strokes, style):
    if style == "script":
        k = 0.18
        return [[(x + k * (y - 4), y) for (x, y) in s] for s in strokes]
    if style == "bold":
        out = []
        for s in strokes:
            out.append([(x, y) for (x, y) in s])
            out.append([(x + 0.5, y + 0.5) for (x, y) in s])
        return out
    return [[(x, y) for (x, y) in s] for s in strokes]


def render_text(text, style="plain", points=900):
    if style not in STYLES:
        style = "plain"
    # split into up to 4 lines, each capped at 32 chars
    raw_lines = (text or "").split("\n")[:4]
    lines = [ln[:32] for ln in raw_lines]

    # lay out each line's strokes in font units, tracking each line's width
    line_strokes = []   # list of (list_of_strokes, width) per line
    for ln in lines:
        cursor = 0.0
        strokes_here = []
        for ch in ln:
            w, strokes = _glyph(ch)
            styled = _style_strokes(strokes, style)
            placed = [[(x + cursor, y) for (x, y) in s] for s in styled]
            strokes_here.extend(s for s in placed if len(s) >= 2)
            cursor += w + 2
        line_strokes.append((strokes_here, max(cursor - 2, 0.0)))

    if not any(s for s, _ in line_strokes):
        return {"x": np.zeros(points, np.float32),
                "y": np.zeros(points, np.float32),
                "rgb": np.zeros((points, 3), np.float32),
                "lit": np.zeros(points, bool)}

    n_lines = len(line_strokes)
    line_h = 18.0                       # baseline-to-baseline in font units
    max_w = max((w for _, w in line_strokes), default=1.0) or 1.0
    total_h = line_h * n_lines
    # fit the block into [-0.9,0.9] on both axes, preserving aspect
    scale = min(1.8 / max_w, 1.8 / total_h)

    # stack lines top-to-bottom: line i centred at its own y offset
    placed_strokes = []
    for i, (strokes_here, w) in enumerate(line_strokes):
        # centre this line horizontally, and offset vertically by line index
        line_cx = w / 2.0
        # y centre of the whole block is 9; lines run downward from the top
        y_off = (n_lines - 1) / 2.0 * line_h - i * line_h
        for s in strokes_here:
            placed_strokes.append([(x - line_cx, (y - 9.0) + y_off)
                                   for (x, y) in s])

    xs, ys, lit = [], [], []
    bridge = 3
    for s in placed_strokes:
        arr = np.array(s, dtype=np.float32)
        sx = arr[:, 0] * scale
        sy = arr[:, 1] * scale
        seg = np.hypot(np.diff(sx), np.diff(sy))
        clen = np.concatenate([[0.0], np.cumsum(seg)])
        npts = max(2, int(clen[-1] / (2.0 * scale)) + 2)
        t = np.linspace(0, clen[-1], npts)
        xs.append(np.interp(t, clen, sx))
        ys.append(np.interp(t, clen, sy))
        lit.append(np.ones(npts, bool))
        xs.append(np.zeros(bridge, np.float32))
        ys.append(np.zeros(bridge, np.float32))
        lit.append(np.zeros(bridge, bool))

    x = np.concatenate(xs); y = np.concatenate(ys); li = np.concatenate(lit)
    dark = np.where(~li)[0]
    for run in np.split(dark, np.where(np.diff(dark) != 1)[0] + 1):
        if len(run) == 0:
            continue
        j = (run[-1] + 1) % len(x)
        x[run] = np.linspace(x[run[0] - 1], x[j], len(run), endpoint=False)
        y[run] = np.linspace(y[run[0] - 1], y[j], len(run), endpoint=False)

    n = len(x)
    if n != points:
        idx = np.linspace(0, n - 1, points)
        xi = np.arange(n)
        x = np.interp(idx, xi, x).astype(np.float32)
        y = np.interp(idx, xi, y).astype(np.float32)
        li = li[np.clip(np.round(idx).astype(int), 0, n - 1)]

    return {"x": np.clip(x, -1, 1).astype(np.float32),
            "y": np.clip(y, -1, 1).astype(np.float32),
            "rgb": np.ones((points, 3), np.float32), "lit": li}
