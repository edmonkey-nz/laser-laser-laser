"""
mask.py — polygon blanking mask, applied to the shared frame so it hits
the preview window, the browser scope and the DAC alike (unlike
geometry.py, which is deliberately DAC-only).

A mask is a list of polygons in normalised [-1,1] laser space. A point is
"inside" the mask if it falls inside ANY of them; the invert flag flips
that, turning a keep-region into a block-region. Points outside the mask
have their colour and intensity zeroed — the galvos still traverse the
masked area, just dark, so this is a blanking mask and NOT a safety
interlock.

Stored in settings.json (live mask) and masks.json (named library) as:
  polys  = [[[x,y], ...], ...]   each polygon >= 3 points, coords -1..1
  invert = false
"""

import numpy as np

MAX_MASK_POLYS = 8
MAX_MASK_POINTS = 64      # per polygon; matches shapes.MAX_CUSTOM_POINTS


def clean_polys(polys):
    """Validate/clamp a raw polygon list from the wire or a JSON file.
    Drops anything with fewer than 3 points, caps sizes."""
    clean = []
    for poly in list(polys or [])[:MAX_MASK_POLYS]:
        pts = []
        for pt in list(poly or [])[:MAX_MASK_POINTS]:
            try:
                x, y = pt
                pts.append([float(np.clip(float(x), -1.0, 1.0)),
                            float(np.clip(float(y), -1.0, 1.0))])
            except (TypeError, ValueError):
                continue
        if len(pts) >= 3:
            clean.append(pts)
    return clean


class MaskFilter:
    """Holds the mask and applies it to a Helios frame (N,6 int array)."""

    def __init__(self):
        self.polys = []          # [[[x,y], ...], ...] in [-1,1]
        self.invert = False
        self.enabled = False     # the ON/OFF toggle
        self.name = None         # name of the loaded saved mask, or None
        self._arrays = []        # cached (V,2) float arrays

    # ---- state ----
    def set_polys(self, polys, invert=None):
        self.polys = clean_polys(polys)
        if invert is not None:
            self.invert = bool(invert)
        self._arrays = [np.asarray(p, dtype=np.float64) for p in self.polys]

    def clear(self):
        self.polys = []
        self._arrays = []
        self.name = None

    def state(self):
        """Serialisable snapshot, as stored under settings.json's "mask"."""
        return {"on": self.enabled, "invert": self.invert,
                "name": self.name, "polys": self.polys}

    def restore(self, d):
        if not isinstance(d, dict):
            return
        self.set_polys(d.get("polys", []), d.get("invert", False))
        self.enabled = bool(d.get("on", False))
        self.name = d.get("name") or None

    # ---- geometry ----
    def _contains(self, px, py):
        """Crossing-number point-in-polygon, vectorised over all N points.
        The vertex loop is Python (<=64 iterations); the per-point work is
        numpy, so this stays cheap at 3000 points / 30 fps."""
        inside = np.zeros(len(px), dtype=bool)
        for poly in self._arrays:
            x0, y0 = poly[:, 0], poly[:, 1]
            x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
            acc = np.zeros(len(px), dtype=bool)
            for j in range(len(x0)):
                dy = y1[j] - y0[j]
                if dy == 0.0:            # horizontal edge casts no crossing
                    continue
                straddles = (y0[j] > py) != (y1[j] > py)
                xint = (x1[j] - x0[j]) * (py - y0[j]) / dy + x0[j]
                acc ^= straddles & (px < xint)
            inside |= acc
        return inside

    def apply(self, frame):
        """Return a masked copy of frame, or frame unchanged when the mask
        is off or empty."""
        if not self.enabled or not self._arrays:
            return frame
        # 12-bit -> [-1,1], same convention as geometry.py
        x = frame[:, 0].astype(np.float64) / 2047.5 - 1.0
        y = frame[:, 1].astype(np.float64) / 2047.5 - 1.0
        ins = self._contains(x, y)
        if self.invert:
            ins = ~ins
        # A point and BOTH its neighbours must be inside. The browser and
        # pygame renderers colour a segment from its start point while the
        # DAC colours it at the destination, so this kills the boundary-
        # crossing segment under either convention and nothing lit escapes
        # the polygon. The wrap-around roll is correct: the frame is a
        # closed loop the DAC repeats.
        keep = ins & np.roll(ins, 1) & np.roll(ins, -1)
        out = frame.copy()
        out[~keep, 2:6] = 0
        return out
