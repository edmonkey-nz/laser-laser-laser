"""
vectorise.py — turn images and live webcam video into laser vector frames.

Pipeline: frame -> grayscale -> brightness/contrast -> blur -> Canny
edges -> contours -> simplify -> arc-length resample -> paths ordered
greedy-nearest to minimise beam travel, joined by blanked bridges.
Contour points are coloured by sampling the source image, so camera
mode traces subjects in their own colours.

Output is an engine-ready frame dict {"x","y","rgb","lit"} written to
engine.vector_frame — the same shape the ILDA player consumes.

Filter parameters live in engine.p (so faders/CCs/patterns drive them):
  vec_bright    0..1 (0.5 neutral)
  vec_contrast  0..1 (0.5 neutral)
  vec_thresh    0..1 edge sensitivity (higher = fewer edges)
  vec_detail    0..1 (lower = more blur, more simplification, fewer paths)

OpenCV (opencv-python-headless) is an optional dependency: everything
degrades to a clear status message if it isn't installed.
"""

import glob
import os
import threading
import time

import numpy as np

try:
    import cv2
    HAVE_CV2 = True
except ImportError:
    cv2 = None
    HAVE_CV2 = False

PROC_W = 320            # processing width (small = fast + less detail)
BRIDGE = 6              # blanked points between paths
MAX_PATHS = 48
TARGET_POINTS = 900     # engine resamples to its budget anyway


def cameras():
    """Enumerate V4L2 capture devices with human names (Linux)."""
    cams = []
    for dev in sorted(glob.glob("/dev/video*"),
                      key=lambda d: int(d.replace("/dev/video", ""))):
        idx = int(dev.replace("/dev/video", ""))
        name_file = f"/sys/class/video4linux/video{idx}/name"
        try:
            name = open(name_file).read().strip()
        except OSError:
            name = dev
        cams.append({"id": idx, "name": f"{name} ({dev})"})
    return cams


class VectorSource:
    """Owns the current vectoriser mode (off / image / camera), the
    camera capture thread, and pushes processed frames to the engine."""

    def __init__(self, engine):
        self.engine = engine
        self.mode = "off"
        self.device = None
        self.status = "off" if HAVE_CV2 else \
            "opencv not installed - pip install opencv-python-headless"
        self._image = None            # BGR source for image mode
        self._last_sig = None         # params signature for reprocessing
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    # ------------------------------------------------ mode control
    def set_image(self, bgr):
        if not HAVE_CV2:
            return False
        self.stop_camera()
        with self._lock:
            self._image = bgr
            self.mode = "image"
            self._last_sig = None     # force reprocess
        return True

    def set_mode(self, mode, device=None):
        if mode == "camera":
            if not HAVE_CV2:
                self.status = ("opencv not installed - "
                               "pip install opencv-python-headless")
                return
            self.stop_camera()
            self.mode = "camera"
            self.device = int(device or 0)
            self._stop.clear()
            self._thread = threading.Thread(target=self._camera_loop,
                                            daemon=True)
            self._thread.start()
        elif mode == "image":
            self.stop_camera()
            self.mode = "image" if self._image is not None else "off"
            self._last_sig = None
        else:
            self.stop_camera()
            self.mode = "off"
            self.status = "off"
            self.engine.vector_frame = None

    def stop_camera(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    # ------------------------------------------------ per-frame hook
    def tick(self):
        """Called from the render loop. In image mode, reprocess when a
        filter fader moved; camera mode has its own thread."""
        if self.mode != "image" or self._image is None:
            return
        sig = self._params_sig()
        if sig == self._last_sig:
            return
        self._last_sig = sig
        frame, npaths = self._process(self._image)
        self.engine.vector_frame = frame
        self.status = f"image: {npaths} path(s)" if frame else \
            "image: no edges found - lower threshold or raise contrast"

    def _params_sig(self):
        p = self.engine.p
        return tuple(round(p[k], 3) for k in
                     ("vec_bright", "vec_contrast", "vec_thresh",
                      "vec_detail"))

    # ------------------------------------------------ camera thread
    def _camera_loop(self):
        cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not cap.isOpened():
            self.status = f"camera /dev/video{self.device}: cannot open"
            print(f"[vec] {self.status}")
            return
        self.status = f"camera /dev/video{self.device}: live"
        print(f"[vec] {self.status}")
        t_frame = 1.0 / 15
        while not self._stop.is_set():
            t0 = time.monotonic()
            ok, bgr = cap.read()
            if not ok:
                self.status = f"camera /dev/video{self.device}: read failed"
                break
            frame, npaths = self._process(bgr)
            if self.mode == "camera":       # may have switched meanwhile
                self.engine.vector_frame = frame
                self.status = (f"camera /dev/video{self.device}: "
                               f"{npaths} path(s)")
            spare = t_frame - (time.monotonic() - t0)
            if spare > 0:
                self._stop.wait(spare)
        cap.release()

    # ------------------------------------------------ the pipeline
    def _process(self, bgr):
        p = self.engine.p
        detail = float(np.clip(p["vec_detail"], 0, 1))

        h0, w0 = bgr.shape[:2]
        scale = PROC_W / max(w0, 1)
        small = cv2.resize(bgr, (PROC_W, max(1, int(h0 * scale))),
                           interpolation=cv2.INTER_AREA)
        h, w = small.shape[:2]

        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
        contrast = 0.5 + float(p["vec_contrast"]) * 1.5     # 0.5 .. 2.0
        bright = (float(p["vec_bright"]) - 0.5) * 200.0     # -100 .. +100
        gray = np.clip(gray * contrast + bright, 0, 255).astype(np.uint8)

        k = 1 + 2 * int((1.0 - detail) * 3)                 # 1,3,5,7
        if k > 1:
            gray = cv2.GaussianBlur(gray, (k, k), 0)

        lo = 30 + float(p["vec_thresh"]) * 180              # 30 .. 210
        edges = cv2.Canny(gray, lo, min(255, lo * 2.5))

        cnts, _ = cv2.findContours(edges, cv2.RETR_LIST,
                                   cv2.CHAIN_APPROX_NONE)
        eps = 0.5 + (1.0 - detail) * 2.5                    # px
        min_len = 10 + (1.0 - detail) * 50                  # arc px
        paths = []
        for c in cnts:
            if cv2.arcLength(c, False) < min_len:
                continue
            a = cv2.approxPolyDP(c, eps, False).reshape(-1, 2)
            if len(a) >= 2:
                paths.append(a.astype(np.float32))
        if not paths:
            return None, 0

        # longest first, cap count, then greedy nearest-neighbour order
        paths.sort(key=lambda a: -cv2.arcLength(a.reshape(-1, 1, 2), False))
        paths = paths[:MAX_PATHS]
        ordered = [paths.pop(0)]
        while paths:
            end = ordered[-1][-1]
            j = min(range(len(paths)),
                    key=lambda i: float(np.sum((paths[i][0] - end) ** 2)))
            ordered.append(paths.pop(j))

        # arc-length resample each path; budget shared by length
        lens = [float(np.hypot(*np.diff(a, axis=0).T).sum()) or 1.0
                for a in ordered]
        total_len = sum(lens)
        budget = TARGET_POINTS - BRIDGE * len(ordered)
        xs, ys, rgbs, lits = [], [], [], []
        half = max(w, h) / 2.0
        for a, plen in zip(ordered, lens):
            n = max(3, int(budget * plen / total_len))
            seg = np.hypot(*np.diff(a, axis=0).T)
            cum = np.concatenate([[0.0], np.cumsum(seg)])
            s = np.linspace(0, cum[-1], n)
            px = np.interp(s, cum, a[:, 0])
            py = np.interp(s, cum, a[:, 1])
            # colour: sample the source image along the path
            ix = np.clip(px.astype(int), 0, w - 1)
            iy = np.clip(py.astype(int), 0, h - 1)
            col = small[iy, ix].astype(np.float32)[:, ::-1] / 255.0  # BGR->RGB
            # avoid near-black beams on dark subjects: floor the value
            vmax = col.max(axis=1, keepdims=True)
            col = np.where(vmax > 0.25, col, col + (0.25 - vmax))
            xs.append((px - w / 2.0) / half)
            ys.append(-(py - h / 2.0) / half)
            rgbs.append(col)
            lits.append(np.ones(n, bool))
            # blanked bridge toward the next path (or wrap to first)
            xs.append(np.full(BRIDGE, xs[-1][-1], np.float32))
            ys.append(np.full(BRIDGE, ys[-1][-1], np.float32))
            rgbs.append(np.zeros((BRIDGE, 3), np.float32))
            lits.append(np.zeros(BRIDGE, bool))
        # make bridges actually travel to the next path start
        x = np.concatenate(xs)
        y = np.concatenate(ys)
        rgb = np.concatenate(rgbs)
        lit = np.concatenate(lits)
        dark = np.where(~lit)[0]
        runs = np.split(dark, np.where(np.diff(dark) != 1)[0] + 1)
        for run in runs:
            if len(run) == 0:
                continue
            j = (run[-1] + 1) % len(x)
            x[run] = np.linspace(x[run[0] - 1], x[j], len(run),
                                 endpoint=False)
            y[run] = np.linspace(y[run[0] - 1], y[j], len(run),
                                 endpoint=False)
        frame = {"x": np.clip(x, -1, 1), "y": np.clip(y, -1, 1),
                 "rgb": rgb, "lit": lit}
        return frame, len(ordered)
