"""
webui.py — browser control surface for lasersynth.

Runs an aiohttp server in a background thread:
  GET /    → static/index.html (single file, vanilla JS, works offline)
  GET /ws  → WebSocket

Server → client:
  binary frames (30 Hz):  uint16 n, uint8 bass, uint8 mid, uint8 high,
                          uint8 blanked, then n × (uint16 x, uint16 y,
                          uint8 r, uint8 g, uint8 b), little-endian
  JSON "state" (5 Hz):    {"type":"state","p":{...},"shapes":[...],
                           "fps":.., "midi":"..", "laser":bool}

Client → server (JSON):
  {"type":"set","key":"size","value":0.8}
  {"type":"shape","index":2}
  {"type":"blank","value":true}
  {"type":"pattern_save","name":"triad"}     (snapshots current params)
  {"type":"pattern_load","name":"triad"}
  {"type":"pattern_delete","name":"triad"}
  {"type":"xfade","value":true}              (pattern loads glide vs snap)
  {"type":"pattern_learn","name":"triad"}    (next MIDI note binds; resend to cancel)
  {"type":"pattern_unbind","name":"triad"}
  {"type":"ilda_select","name":"star.ild"}   (loads file, switches to ilda shape)
  {"type":"geom_corners","corners":[8 floats]} {"type":"geom_pincushion","value":0.3}
  {"type":"geom_test","value":true} {"type":"geom_reset"}
POST /upload_ilda (raw body + X-Filename header) adds a file to the library.
POST /upload_image (raw body) loads an image into the vectoriser.
  {"type":"vec_source","mode":"camera","device":0} | {"mode":"image"} | {"mode":"off"}
"""

import asyncio
import json
import os
import struct
import threading
import time

from shapes import SHAPE_NAMES
import vectorise
from geometry import GeometryCorrection, test_pattern
from settings import SettingsStore
from ilda import IldaLibrary
from patterns import PatternBank

HERE = os.path.dirname(os.path.abspath(__file__))


class WebUI:
    def __init__(self, engine, port=8080, host="0.0.0.0", downsample=2,
                 bank=None, ilda_lib=None, vec=None, settings=None,
                 midi=None, geom=None):
        self.engine = engine
        self.port = port
        self.host = host
        self.downsample = max(1, downsample)
        self.status = {"fps": 0.0, "laser": False}
        self.bank = bank or PatternBank(os.path.join(HERE, "patterns.json"))
        self.ilda = ilda_lib or IldaLibrary(os.path.join(HERE, "ilda"))
        self.vec = vec or vectorise.VectorSource(engine)
        self.settings = settings or SettingsStore(
            os.path.join(HERE, "settings.json"))
        self.midi = midi
        self.geom = geom or GeometryCorrection()
        self._midi_ports = []
        self._midi_ports_t = 0.0
        self._latest = None          # packed frame bytes
        self._lock = threading.Lock()
        self._loop = None
        self._clients = set()        # touched only from server thread
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    # ------------------------------------------------ main-thread side
    def publish(self, frame, audio, fps):
        """Called from the render loop. Packs and stores the latest frame."""
        self.status["fps"] = fps
        ds = frame[::self.downsample]
        n = len(ds)
        bands = [0, 0, 0]
        if audio:
            bands = [int(min(1.0, audio[k]) * 255)
                     for k in ("bass", "mid", "high")]
        buf = bytearray(struct.pack("<H4B", n, *bands,
                                    1 if self.engine.blanked else 0))
        pts = struct.pack(f"<{'HHBBB' * n}",
                          *(int(v) for row in ds for v in
                            (row[0], row[1], row[2], row[3], row[4])))
        buf += pts
        with self._lock:
            self._latest = bytes(buf)

    # ------------------------------------------------ server thread side
    def _run(self):
        from aiohttp import web

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def index(request):
            return web.FileResponse(os.path.join(HERE, "static", "index.html"))

        async def about(request):
            path = os.path.join(HERE, "about.md")
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                text = "# About\n\n(Create about.md next to the scripts.)"
            return web.json_response({"text": text})

        async def ws_handler(request):
            ws = web.WebSocketResponse(heartbeat=20)
            await ws.prepare(request)
            self._clients.add(ws)
            try:
                async for msg in ws:
                    if msg.type == web.WSMsgType.TEXT:
                        self._apply(json.loads(msg.data))
            finally:
                self._clients.discard(ws)
            return ws

        async def broadcaster(app):
            frame_dt, state_dt, since_state = 1 / 30, 0.2, 0.0
            while True:
                await asyncio.sleep(frame_dt)
                with self._lock:
                    latest = self._latest
                dead = []
                if latest and self._clients:
                    for ws in self._clients:
                        try:
                            await ws.send_bytes(latest)
                        except Exception:
                            dead.append(ws)
                since_state += frame_dt
                if since_state >= state_dt and self._clients:
                    since_state = 0.0
                    # port scan is not free — refresh at most every 2 s
                    if time.time() - self._midi_ports_t > 2.0:
                        self._midi_ports_t = time.time()
                        if self.midi:
                            self._midi_ports = self.midi.list_ports()
                    msg = json.dumps({
                        "type": "state",
                        "p": {k: v for k, v in self.engine.p.items()},
                        "shapes": SHAPE_NAMES,
                        "blanked": self.engine.blanked,
                        "patterns": self.bank.names(),
                        "bindings": self.bank.bindings(),
                        "learn": self.bank.learn_target,
                        "xfade": self.engine.xfade,
                        "paused": self.engine.paused,
                        "midi": {
                            "port": self.midi.port_name if self.midi
                                    else "none",
                            "ports": self._midi_ports,
                            "active": self.midi.active() if self.midi
                                      else False,
                            "count": self.midi.msg_count if self.midi
                                     else 0,
                        },
                        "cc_map": {k: c for c, (k, _l, _h) in
                                   __import__("lasersynth").build_cc_map(
                                       self.settings.custom_cc).items()},
                        "cc_custom": dict(self.settings.custom_cc),
                        "cc_mode": dict(self.settings.cc_mode),
                        "midi_learn_param": self.settings.learn_param,
                        "geom": {
                            "corners": list(self.geom.corners),
                            "pincushion": self.geom.pincushion,
                            "test": self.engine.test_frame is not None,
                        },
                        "settings": {
                            "points": self.engine.n_points,
                            "pps": getattr(self.engine, "pps", 30000),
                            "hw_flip_x": getattr(self.engine, "hw_flip_x", True),
                            "hw_flip_y": getattr(self.engine, "hw_flip_y", False),
                            "xfade_time": self.engine.xfade_time,
                        },
                        "ilda_files": self.ilda.names(),
                        "ilda_file": self.engine.ilda_name,
                        "vec": {"mode": self.vec.mode,
                                "device": self.vec.device,
                                "status": self.vec.status,
                                "cameras": vectorise.cameras(),
                                "have_image": self.vec._image is not None},
                        **self.status,
                    })
                    for ws in self._clients:
                        try:
                            await ws.send_str(msg)
                        except Exception:
                            dead.append(ws)
                for ws in dead:
                    self._clients.discard(ws)

        async def start_bg(app):
            app["bg"] = asyncio.ensure_future(broadcaster(app))

        async def upload_ilda(request):
            name = request.headers.get("X-Filename", "upload.ild")
            try:
                data = await request.read()
                safe, nframes = self.ilda.add(name, data)
            except ValueError as e:
                return web.json_response({"ok": False, "error": str(e)},
                                         status=400)
            except Exception as e:
                return web.json_response({"ok": False, "error": repr(e)},
                                         status=500)
            return web.json_response({"ok": True, "name": safe,
                                      "frames": nframes})

        async def upload_image(request):
            import numpy as _np
            if not vectorise.HAVE_CV2:
                return web.json_response(
                    {"ok": False, "error": "opencv not installed on the "
                     "synth machine - pip install opencv-python-headless"},
                    status=400)
            try:
                data = await request.read()
                import cv2 as _cv2
                img = _cv2.imdecode(_np.frombuffer(data, _np.uint8),
                                    _cv2.IMREAD_COLOR)
                if img is None:
                    raise ValueError("not a decodable image")
                self.vec.set_image(img)
                from shapes import SHAPE_NAMES as _SN
                self.engine.set_param("shape", _SN.index("vector"))
            except ValueError as e:
                return web.json_response({"ok": False, "error": str(e)},
                                         status=400)
            except Exception as e:
                return web.json_response({"ok": False, "error": repr(e)},
                                         status=500)
            return web.json_response({"ok": True})

        app = web.Application(client_max_size=25 * 1024 * 1024)
        app.router.add_post("/upload_image", upload_image)
        app.router.add_get("/", index)
        app.router.add_get("/about", about)
        app.router.add_get("/ws", ws_handler)
        app.router.add_post("/upload_ilda", upload_ilda)
        app.on_startup.append(start_bg)

        runner = web.AppRunner(app, access_log=None)
        self._loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, self.host, self.port)
        self._loop.run_until_complete(site.start())
        print(f"[web] control surface at http://localhost:{self.port} "
              f"(reachable on your LAN too)")
        self._loop.run_forever()

    def _apply(self, msg):
        p = self.engine.p
        t = msg.get("type")
        if t == "set" and msg.get("key") in p:
            key, val = msg["key"], float(msg["value"])
            if key == "shape":
                return
            self.engine.set_param(key, val)
        elif t == "shape":
            idx = int(msg.get("index", 0))
            if 0 <= idx < len(SHAPE_NAMES):
                p["shape"] = idx
        elif t == "blank":
            self.engine.blanked = bool(msg.get("value"))
        elif t == "pattern_save":
            self.bank.save(msg.get("name", ""), dict(p),
                           ilda_file=self.engine.ilda_name or None)
        elif t == "pattern_load":
            self.bank.apply_entry(msg.get("name", ""), self.engine,
                                  self.ilda)
        elif t == "pattern_delete":
            self.bank.delete(msg.get("name", ""))
        elif t == "pattern_random":
            from shapes import ShapeEngine as _SE
            rp = _SE.random_params()
            self.engine.apply_params(rp)
            if self.engine.on_load:
                pass  # apply_params already fires on_load
        elif t == "xfade":
            self.engine.xfade = bool(msg.get("value"))
        elif t == "pattern_learn":
            name = msg.get("name", "")
            self.bank.learn_target = None if self.bank.learn_target == name                 else (name if name in self.bank.patterns else None)
        elif t == "pattern_unbind":
            self.bank.bind(msg.get("name", ""), None)
        elif t == "pause":
            self.engine.paused = bool(msg.get("value"))
        elif t == "stop_spin":
            self.engine.set_param("spin", 0.5)
            self.engine.rot = 0.0
        elif t == "midi_port":
            if self.midi:
                name = msg.get("name", "")
                if self.midi.open_port(name):
                    self.settings.set("midi_port", name)
        elif t == "midi_learn_cc":
            param = msg.get("param", "")
            import lasersynth as _ls
            valid = param in p or param in _ls.ACTION_KEYS
            self.settings.learn_param = None \
                if self.settings.learn_param == param \
                else (param if valid else None)
        elif t == "midi_unmap":
            self.settings.unmap(msg.get("param", ""))
        elif t == "midi_mode":
            self.settings.set_mode(msg.get("param", ""),
                                   msg.get("mode", "absolute"))
        elif t == "geom_corners":
            c = msg.get("corners", [0.0] * 8)
            if isinstance(c, list) and len(c) == 8:
                self.geom.set_corners(c)
                self.settings.set("corners", list(self.geom.corners))
        elif t == "geom_pincushion":
            self.geom.set_pincushion(float(msg.get("value", 0.0)))
            self.settings.set("pincushion", self.geom.pincushion)
        elif t == "geom_reset":
            self.geom.reset()
            self.settings.set("corners", [0.0] * 8)
            self.settings.set("pincushion", 0.0)
        elif t == "geom_test":
            self.engine.test_frame = test_pattern(self.engine.n_points)                 if msg.get("value") else None
        elif t == "setting":
            key, val = msg.get("key"), msg.get("value")
            if key == "points":
                self.engine.n_points = int(max(100, min(3000, val)))
                self.settings.set("points", self.engine.n_points)
            elif key == "pps":
                self.engine.pps = int(max(5000, min(65535, val)))
                self.settings.set("pps", self.engine.pps)
            elif key == "xfade_time":
                self.engine.xfade_time = float(max(0.1, min(10.0, val)))
                self.settings.set("xfade_time", self.engine.xfade_time)
            elif key in ("hw_flip_x", "hw_flip_y"):
                setattr(self.engine, key, bool(val))
                self.settings.set(key, bool(val))
        elif t == "vec_source":
            mode = msg.get("mode", "off")
            self.vec.set_mode(mode, msg.get("device"))
            if mode in ("camera", "image"):
                from shapes import SHAPE_NAMES as _SN
                self.engine.set_param("shape", _SN.index("vector"))
        elif t == "ilda_select":
            name = msg.get("name", "")
            frames = self.ilda.frames(name) if name else None
            if frames:
                self.engine.set_ilda(frames, name)
                from shapes import SHAPE_NAMES as _SN
                self.engine.set_param("shape", _SN.index("ilda"))
