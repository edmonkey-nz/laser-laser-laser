"""
geometry.py — projection geometry correction, applied ONLY to the DAC
output stream (never the preview). Two stages, in order:

  1. corner-pin (homography): map the unit square's four corners to
     user-set positions. Handles keystone, tilt, trapezoid, rotation.
  2. pincushion / barrel: radial term for lens-style bulge, applied
     after the corner-pin around the warped centre.

Corner values are normalised offsets in [-0.5, 0.5] added to each
nominal corner, stored in settings.json as:
  corners = [tlx,tly, trx,try, brx,bry, blx,bly]   (8 floats, default 0)
  pincushion = 0.0   (>0 pincushion, <0 barrel)

The homography is recomputed only when the parameters change (cached),
so per-frame cost is one matrix multiply + optional radial warp.
"""

import numpy as np

# nominal corners of the normalised field, in [-1, 1] laser space:
# top-left, top-right, bottom-right, bottom-left
_SRC = np.array([[-1, 1], [1, 1], [1, -1], [-1, -1]], dtype=np.float64)


def _solve_homography(dst):
    """3x3 homography mapping _SRC -> dst (both 4x2). Standard DLT."""
    A = []
    b = []
    for (sx, sy), (dx, dy) in zip(_SRC, dst):
        A.append([sx, sy, 1, 0, 0, 0, -sx * dx, -sy * dx])
        b.append(dx)
        A.append([0, 0, 0, sx, sy, 1, -sx * dy, -sy * dy])
        b.append(dy)
    h = np.linalg.solve(np.array(A), np.array(b))
    return np.array([[h[0], h[1], h[2]],
                     [h[3], h[4], h[5]],
                     [h[6], h[7], 1.0]])


class GeometryCorrection:
    """Holds correction params and applies them to a Helios frame
    (N,6 int array). Preview code never calls this."""

    def __init__(self):
        self.corners = [0.0] * 8
        self.pincushion = 0.0
        self.enabled = False
        self._sig = None
        self._H = np.eye(3)

    def set_corners(self, corners):
        self.corners = [float(np.clip(c, -0.5, 0.5)) for c in corners[:8]]
        self._refresh_enabled()

    def set_pincushion(self, v):
        self.pincushion = float(np.clip(v, -1.0, 1.0))
        self._refresh_enabled()

    def reset(self):
        self.corners = [0.0] * 8
        self.pincushion = 0.0
        self.enabled = False

    def _refresh_enabled(self):
        self.enabled = (any(abs(c) > 1e-6 for c in self.corners)
                        or abs(self.pincushion) > 1e-6)

    def _ensure(self):
        sig = (tuple(self.corners),)
        if sig != self._sig:
            self._sig = sig
            off = np.array(self.corners, dtype=np.float64).reshape(4, 2)
            # each corner offset spans the full field (×2 because field is
            # 2 units wide); this makes a 0.5 offset reach the centre.
            dst = _SRC + off * 2.0
            try:
                self._H = _solve_homography(dst)
            except np.linalg.LinAlgError:
                self._H = np.eye(3)

    def apply(self, frame):
        """Return a geometry-corrected copy of frame, or frame unchanged
        when correction is disabled."""
        if not self.enabled:
            return frame
        self._ensure()
        out = frame.copy()
        # 12-bit -> [-1,1]
        x = out[:, 0].astype(np.float64) / 2047.5 - 1.0
        y = out[:, 1].astype(np.float64) / 2047.5 - 1.0

        # 1) homography
        denom = self._H[2, 0] * x + self._H[2, 1] * y + self._H[2, 2]
        denom = np.where(np.abs(denom) < 1e-9, 1e-9, denom)
        xw = (self._H[0, 0] * x + self._H[0, 1] * y + self._H[0, 2]) / denom
        yw = (self._H[1, 0] * x + self._H[1, 1] * y + self._H[1, 2]) / denom

        # 2) pincushion / barrel around centre
        if abs(self.pincushion) > 1e-6:
            r2 = xw * xw + yw * yw
            k = self.pincushion * 0.5
            f = 1.0 + k * r2
            xw = xw * f
            yw = yw * f

        out[:, 0] = np.clip((xw + 1.0) * 2047.5, 0, 0xFFF).astype(np.int32)
        out[:, 1] = np.clip((yw + 1.0) * 2047.5, 0, 0xFFF).astype(np.int32)
        return out


# ---------------------------------------------------------------- test frame
def test_pattern(points=900, grid=4):
    """Build an alignment test frame as an engine source dict
    {"x","y","rgb","lit"}: outer border, inner grid, centre cross, and
    bright corner ticks. All in [-1,1]. Colours: white grid, cyan centre,
    red corners — so orientation and distortion are both obvious."""
    segs = []          # each: (x0,y0,x1,y1,(r,g,b))
    W = (1.0, 1.0, 1.0)
    C = (0.0, 1.0, 1.0)
    R = (1.0, 0.2, 0.2)
    e = 0.98

    # border
    segs += [(-e, -e, e, -e, W), (e, -e, e, e, W),
             (e, e, -e, e, W), (-e, e, -e, -e, W)]
    # inner grid
    for i in range(1, grid):
        t = -e + 2 * e * i / grid
        segs.append((t, -e, t, e, W))
        segs.append((-e, t, e, t, W))
    # centre cross
    segs += [(-0.12, 0, 0.12, 0, C), (0, -0.12, 0, 0.12, C)]
    # corner ticks (short bright L shapes just inside each corner)
    for cx, cy in [(-e, -e), (e, -e), (e, e), (-e, e)]:
        sx = -0.18 if cx > 0 else 0.18
        sy = -0.18 if cy > 0 else 0.18
        segs.append((cx, cy, cx + sx, cy, R))
        segs.append((cx, cy, cx, cy + sy, R))

    # distribute points across segments by length, blanked hops between
    lens = [np.hypot(s[2] - s[0], s[3] - s[1]) for s in segs]
    total = sum(lens) or 1.0
    bridge = 3
    budget = points - bridge * len(segs)
    xs, ys, rgb, lit = [], [], [], []
    for (x0, y0, x1, y1, col), L in zip(segs, lens):
        n = max(2, int(budget * L / total))
        xs.append(np.linspace(x0, x1, n))
        ys.append(np.linspace(y0, y1, n))
        rgb.append(np.tile(col, (n, 1)))
        lit.append(np.ones(n, bool))
        # blanked hop to next segment start
        xs.append(np.full(bridge, x1))
        ys.append(np.full(bridge, y1))
        rgb.append(np.zeros((bridge, 3)))
        lit.append(np.zeros(bridge, bool))
    x = np.concatenate(xs)
    y = np.concatenate(ys)
    r = np.concatenate(rgb).astype(np.float32)
    li = np.concatenate(lit)
    # fill blanked hop coordinates so the beam travels to the next start
    dark = np.where(~li)[0]
    for run in np.split(dark, np.where(np.diff(dark) != 1)[0] + 1):
        if len(run) == 0:
            continue
        j = (run[-1] + 1) % len(x)
        x[run] = np.linspace(x[run[0] - 1], x[j], len(run), endpoint=False)
        y[run] = np.linspace(y[run[0] - 1], y[j], len(run), endpoint=False)
    return {"x": x.astype(np.float32), "y": y.astype(np.float32),
            "rgb": r, "lit": li}
