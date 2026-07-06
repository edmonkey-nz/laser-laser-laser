"""
ilda.py — ILDA Image Data Transfer Format (.ild) parser + file library.

Supports all point format codes:
  0: 3D, indexed colour       1: 2D, indexed colour
  2: colour palette (applies to subsequent frames in the file)
  4: 3D, true colour (BGR)    5: 2D, true colour (BGR)

Frames are returned engine-ready:
  {"x": float32 [-1..1], "y": float32 [-1..1],
   "rgb": float32 (N,3) 0..1, "lit": bool (N,)}

Z is parsed and discarded (we project to 2D). The ILDA status byte's
blanking bit (0x40) drives the lit mask. Files without an embedded
palette use an approximation of the ILDA standard 64-colour palette
(rainbow ramp + grey ramp); embedded format-2 palettes are used exactly.
"""

import os
import re
import struct

import numpy as np

HEADER = struct.Struct(">4s3xB8s8sHHHBx")   # 32 bytes
POINT_FMT = {
    0: struct.Struct(">hhhBB"),      # x y z status colour_index
    1: struct.Struct(">hhBB"),       # x y   status colour_index
    2: struct.Struct(">BBB"),        # r g b (palette entry)
    4: struct.Struct(">hhhBBBB"),    # x y z status B G R
    5: struct.Struct(">hhBBBB"),     # x y   status B G R
}
BLANK_BIT = 0x40


def _default_palette():
    """Approximation of the ILDA standard palette: 0..55 rainbow sweep,
    56..63 grey-to-white ramp. Format-2 palettes override this exactly."""
    pal = np.zeros((64, 3), dtype=np.float32)
    for i in range(56):
        h = i / 56.0
        k = h * 6.0
        seg, f = int(k) % 6, k - int(k)
        r, g, b = [(1, f, 0), (1 - f, 1, 0), (0, 1, f),
                   (0, 1 - f, 1), (f, 0, 1), (1, 0, 1 - f)][seg]
        pal[i] = (r, g, b)
    for i in range(8):
        v = 0.3 + 0.7 * i / 7.0
        pal[56 + i] = (v, v, v)
    pal[63] = (1, 1, 1)
    return pal


def parse_ild(data):
    """Parse .ild bytes → list of frame dicts. Raises ValueError on
    malformed input. Zero-record end headers and unknown formats are
    handled; truncated files fail loudly rather than half-parsing."""
    if len(data) < 32:
        raise ValueError("file too short to contain an ILDA header")
    frames = []
    palette = _default_palette()
    off = 0
    while off + 32 <= len(data):
        magic, fmt, _name, _co, nrec, _fno, _ftot, _proj = \
            HEADER.unpack_from(data, off)
        off += 32
        if magic != b"ILDA":
            raise ValueError(f"bad section magic at offset {off - 32}")
        if nrec == 0:            # end-of-file marker
            break
        if fmt not in POINT_FMT:
            raise ValueError(f"unsupported ILDA format code {fmt}")
        ps = POINT_FMT[fmt]
        need = nrec * ps.size
        if off + need > len(data):
            raise ValueError("truncated file: fewer point records than "
                             "the header promises")
        if fmt == 2:             # palette section
            pal = np.frombuffer(data, dtype=np.uint8,
                                count=nrec * 3, offset=off)
            palette = (pal.reshape(-1, 3).astype(np.float32) / 255.0)
            off += need
            continue

        raw = data[off:off + need]
        off += need
        xs = np.empty(nrec, np.float32)
        ys = np.empty(nrec, np.float32)
        rgb = np.empty((nrec, 3), np.float32)
        lit = np.empty(nrec, bool)
        for i in range(nrec):
            rec = ps.unpack_from(raw, i * ps.size)
            if fmt == 0:
                x, y, _z, status, ci = rec
                col = palette[ci % len(palette)]
            elif fmt == 1:
                x, y, status, ci = rec
                col = palette[ci % len(palette)]
            elif fmt == 4:
                x, y, _z, status, cb, cg, cr = rec
                col = (cr / 255.0, cg / 255.0, cb / 255.0)
            else:  # 5
                x, y, status, cb, cg, cr = rec
                col = (cr / 255.0, cg / 255.0, cb / 255.0)
            xs[i] = x / 32767.0
            ys[i] = y / 32767.0
            rgb[i] = col
            lit[i] = not (status & BLANK_BIT)
        frames.append({"x": np.clip(xs, -1, 1), "y": np.clip(ys, -1, 1),
                       "rgb": rgb, "lit": lit})
    if not frames:
        raise ValueError("no drawable frames found")
    return frames


def dwell_warnings(frames, run=48):
    """Static-beam safety check: returns a list of warnings for frames
    containing long runs of lit points at the same coordinate (which
    would park the beam). Purely advisory."""
    warns = []
    for fi, fr in enumerate(frames):
        if len(fr["x"]) < run:
            continue
        same = (np.diff(fr["x"]) == 0) & (np.diff(fr["y"]) == 0) \
            & fr["lit"][1:]
        # longest run of consecutive True
        best = cur = 0
        for v in same:
            cur = cur + 1 if v else 0
            best = max(best, cur)
        if best >= run:
            warns.append(f"frame {fi}: {best + 1} consecutive lit points "
                         "at one coordinate (beam dwell)")
    return warns


class IldaLibrary:
    """Manages the ilda/ folder: scan, cached parse, validated upload."""

    SAFE = re.compile(r"[^A-Za-z0-9._ -]")

    def __init__(self, folder):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self._cache = {}

    def names(self):
        try:
            return sorted(f for f in os.listdir(self.folder)
                          if f.lower().endswith(".ild"))
        except OSError:
            return []

    def frames(self, name):
        """Parsed frames for a library file, or None if missing/corrupt."""
        if name in self._cache:
            return self._cache[name]
        path = os.path.join(self.folder, os.path.basename(name))
        try:
            with open(path, "rb") as f:
                frames = parse_ild(f.read())
        except (OSError, ValueError) as e:
            print(f"[ilda] cannot load '{name}': {e}")
            return None
        for w in dwell_warnings(frames):
            print(f"[ilda] warning in '{name}': {w}")
        self._cache[name] = frames
        return frames

    def add(self, filename, data):
        """Validate and store uploaded bytes. Returns (safe_name, n_frames).
        Raises ValueError on anything unusable."""
        base = os.path.basename(filename or "")
        base = self.SAFE.sub("_", base)[:64].strip() or "upload.ild"
        if not base.lower().endswith(".ild"):
            raise ValueError("only .ild files are accepted")
        if len(data) > 20 * 1024 * 1024:
            raise ValueError("file too large (20 MB limit)")
        frames = parse_ild(data)          # validate before touching disk
        path = os.path.join(self.folder, base)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        self._cache[base] = frames
        for w in dwell_warnings(frames):
            print(f"[ilda] warning in '{base}': {w}")
        print(f"[ilda] added '{base}' ({len(frames)} frame(s))")
        return base, len(frames)
