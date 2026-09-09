#!/usr/bin/env python3
"""
Laser! Laser Laser! — realtime laser visuals synth for the Helios DAC.

Usage:
  python3 laserx3.py --preview              # screen only, no laser
  python3 laserx3.py --laser                # laser only
  python3 laserx3.py --laser --preview      # both
  python3 laserx3.py --list-midi            # show MIDI input ports
  python3 laserx3.py --laser --midi "MPK"   # match port by substring

Keyboard (preview window):
  1-9 select shape   ←/→ ratio A   ↑/↓ ratio B   [ ] size
  m/M morph          s/S spin      h hue step    a/A audio amount
  d/D copies +/-     c mono        f/g flip X/Y
  SPACE blank/unblank              ESC/q quit (blanks laser)
  . disarm laser     > (shift-.) arm laser

Default MIDI CC map (channel-agnostic):
  CC1→ratio A  CC2→ratio B  CC3→morph  CC4→spin  CC5→size
  CC6→hue  CC7→hue cycle  CC8→audio amount  CC9→brightness
  CC10→pos X  CC11→pos Y  CC12→sweep depth  CC13→sweep speed
  CC14→copies  CC15→spread  CC16→falloff  CC17→orbit
  CC18→mono  CC19→flip X  CC20→flip Y  CC21→dotify
  Notes bound to patterns (MIDI learn in the web UI) load those patterns.
  Notes from C1 (36) upward select shapes.
"""

__version__ = "1.8.2"

import argparse
import sys
import threading
import time

# Installed before anything else is imported, deliberately: a missing bundled
# module or a broken native dependency is one of the things the log exists to
# diagnose, and a handler installed after the failing import never runs.
# (promptwaver's PACKAGING.md §4.)
import crashlog
crashlog.install(version=__version__)
crashlog.step("interpreter up, importing dependencies")

import numpy as np

from ilda import IldaLibrary
from geometry import GeometryCorrection, test_pattern
from laser_output import NullOutput, SafeOutput, install_panic_handlers

from mask import MaskFilter
from masks import MaskBank
from settings import SettingsStore
from vectorise import VectorSource
from patterns import PatternBank
from shapes import ShapeEngine, SHAPE_NAMES

crashlog.step("dependencies imported")

# ---------------------------------------------------------------- MIDI map
CC_MAP = {
    1: ("ratio_a", 1.0, 12.0),
    2: ("ratio_b", 1.0, 12.0),
    3: ("morph", 0.0, 1.0),
    4: ("spin", 0.0, 1.0),
    5: ("size", 0.0, 1.0),
    6: ("hue", 0.0, 1.0),
    7: ("hue_cycle", 0.0, 1.0),
    8: ("audio_amt", 0.0, 1.0),
    9: ("brightness", 0.0, 1.0),
    10: ("pos_x", 0.0, 1.0),
    11: ("pos_y", 0.0, 1.0),
    12: ("sweep", 0.0, 1.0),
    13: ("sweep_speed", 0.0, 1.0),
    14: ("dup_count", 1.0, 6.0),
    15: ("dup_spread", 0.0, 1.0),
    16: ("dup_scale", 0.0, 1.0),
    17: ("dup_spin", 0.0, 1.0),
    18: ("mono", 0.0, 1.0),
    19: ("flip_x", 0.0, 1.0),
    20: ("flip_y", 0.0, 1.0),
    21: ("dotify", 0.0, 1.0),
    22: ("ilda_rate", 0.0, 1.0),
    23: ("vec_bright", 0.0, 1.0),
    24: ("vec_contrast", 0.0, 1.0),
    25: ("vec_thresh", 0.0, 1.0),
    26: ("vec_detail", 0.0, 1.0),
    27: ("dup_mirror_x", 0.0, 1.0),
    28: ("dup_mirror_y", 0.0, 1.0),
    29: ("ilda_mode", 0.0, 2.0),
    30: ("scope_mode", 0.0, 4.0),
    31: ("audio_off", 0.0, 1.0),
    32: ("lfo_target", 0.0, 9.0),
    33: ("lfo_wave", 0.0, 4.0),
    34: ("lfo_rate", 0.0, 1.0),
    35: ("lfo_depth", 0.0, 1.0),
    36: ("lfo_dropoff", 0.0, 1.0),
    37: ("sweep_x", 0.0, 1.0),
    38: ("sweep_y", 0.0, 1.0),
    39: ("sweep_x_speed", 0.0, 1.0),
    40: ("sweep_y_speed", 0.0, 1.0),
    41: ("wave_type", 0.0, 4.0),
    42: ("aud_bass_dest", 0.0, 10.0),
    43: ("aud_mid_dest", 0.0, 10.0),
    44: ("aud_high_dest", 0.0, 10.0),
    45: ("size_y", 0.02, 1.0),
    46: ("size_link", 0.0, 1.0),
    47: ("rotate", 0.0, 1.0),
}

# value ranges for every MIDI-mappable parameter (used by custom mapping)
PARAM_RANGES = {key: (lo, hi) for key, lo, hi in CC_MAP.values()}


# momentary "action" params: mappable like any other, but instead of
# setting a value, a rising edge (value >= 64) fires a callback. The web
# UI and MIDI both address these by name so LEARN works identically.
ACTION_KEYS = ("act_pause", "act_stop_spin", "act_blank", "act_disarm")


def _register_actions(engine, holder):
    """holder carries a late-bound .out (the SafeOutput), which does not
    exist yet when MIDI is set up."""

    def toggle_pause():
        engine.paused = not engine.paused

    def stop_spin():
        engine.set_param("spin", 0.5)
        engine.rot = 0.0

    def toggle_blank():
        engine.blanked = not engine.blanked

    def disarm():
        # One-way on purpose: a MIDI accident should never arm a laser.
        if holder.out:
            holder.out.disarm()
            print("[laser] disarmed (MIDI)")

    return {"act_pause": toggle_pause,
            "act_stop_spin": stop_spin,
            "act_blank": toggle_blank,
            "act_disarm": disarm}


def custom_key_for_cc(custom, cc):
    """Which param/action is custom-bound to this CC, if any."""
    for k, v in custom.items():
        if int(v) == cc:
            return k
    return None


def build_cc_map(custom):
    """Effective CC -> (param, lo, hi) map: defaults overlaid with the
    user's custom bindings. A custom binding both moves its param off the
    default CC and steals the target CC from whatever default used it."""
    customized = set(custom)
    stolen = {int(cc) for cc in custom.values()}
    eff = {}
    for cc, (key, lo, hi) in CC_MAP.items():
        if key in customized or cc in stolen:
            continue
        eff[cc] = (key, lo, hi)
    for key, cc in custom.items():
        lo, hi = PARAM_RANGES.get(key, (0.0, 1.0))
        eff[int(cc)] = (key, lo, hi)
    return eff
NOTE_SHAPE_BASE = 36  # C1 selects shape 0, C#1 shape 1, ...


class MidiInput:
    def __init__(self, engine, port_hint=None, bank=None, ilda_lib=None,
                 settings=None):
        self.engine = engine
        self.bank = bank
        self.ilda_lib = ilda_lib
        self.settings = settings
        self.port = None
        self.port_name = "none"
        self.last_msg = 0.0        # monotonic time of last incoming message
        self.msg_count = 0
        self._caught = {}          # catch-mode: has the knob caught the value?
        self._catch_last = {}      # catch-mode: last raw value seen per param
        self.out = None            # SafeOutput, attached once it exists
        self._actions = _register_actions(engine, self)
        self._act_last = {}        # action CCs: last value, for edge detection
        names = self.list_ports()
        saved = settings.get("midi_port") if settings else None
        name = self._pick(names, port_hint, saved)
        if name:
            self.open_port(name)
        elif names:
            print(f"[midi] no controller auto-selected "
                  f"(available: {names}) — pick one in Settings")
        else:
            print("[midi] no MIDI input ports found")

    @staticmethod
    def list_ports():
        try:
            import mido
            return mido.get_input_names()
        except ImportError:
            print("[midi] mido not installed — MIDI disabled")
            return []
        except Exception as e:
            print(f"[midi] backend unavailable ({e}) — MIDI disabled")
            return []

    @staticmethod
    def _pick(names, hint, saved):
        """Choose a port: CLI hint > saved setting > first real device.
        'Midi Through' (the ALSA loopback that is always port 0) is never
        auto-picked — it swallows everything silently."""
        if not names:
            return None
        if hint:
            for n in names:
                if hint.lower() in n.lower():
                    return n
            print(f"[midi] no port matching '{hint}', have: {names}")
            return None
        if saved:
            if saved in names:
                return saved
            # ALSA client:port suffixes change across reboots — match base
            import re
            base = re.sub(r"\s+\d+:\d+$", "", saved).lower()
            for n in names:
                if re.sub(r"\s+\d+:\d+$", "", n).lower() == base:
                    return n
            print(f"[midi] saved port '{saved}' not present")
        real = [n for n in names if "midi through" not in n.lower()]
        return real[0] if real else None

    def open_port(self, name):
        """(Re)connect to a port at runtime. Empty name disconnects."""
        try:
            import mido
        except ImportError:
            return False
        if self.port:
            try:
                self.port.close()
            except Exception:
                pass
        self.port = None
        self.port_name = "none"
        if not name:
            print("[midi] disconnected")
            return True
        try:
            self.port = mido.open_input(name, callback=self._on_msg)
        except Exception as e:
            print(f"[midi] could not open '{name}': {e}")
            return False
        self.port_name = name
        print(f"[midi] listening on: {name}")
        return True

    def active(self, window=0.6):
        return (time.monotonic() - self.last_msg) < window

    def _apply_cc(self, key, value, lo, hi, mode):
        """Turn a raw CC value into a parameter change per encoder mode."""
        eng = self.engine
        span = hi - lo
        if mode == "relative":
            # auto-detect: 1..63 = +delta, 65..127 = -delta (two common
            # "signed" encodings share this shape); 0 and 64 are no-ops.
            if value == 0 or value == 64:
                return
            delta = value if value < 64 else value - 128
            step = span / 127.0
            cur = eng.p.get(key, lo)
            eng.set_param(key, float(np.clip(cur + delta * step, lo, hi)))
            return
        target = lo + (value / 127.0) * span
        if mode == "catch":
            cur = eng.p.get(key, lo)
            last = self._catch_last.get(key)
            self._catch_last[key] = value
            if self._caught.get(key):
                eng.set_param(key, target)
            else:
                # catch when the current value lies between the previous and
                # current knob positions (i.e. the knob swept across it), or
                # when we land essentially on it.
                last_t = (lo + last / 127.0 * span) if last is not None \
                    else target
                if min(last_t, target) - 1e-9 <= cur <= max(last_t, target) \
                        + 1e-9:
                    self._caught[key] = True
                    eng.set_param(key, target)
                # else: ignore — waiting for the knob to reach the value
            return
        eng.set_param(key, target)   # absolute

    def _on_msg(self, msg):
        self.last_msg = time.monotonic()
        self.msg_count += 1
        eng = self.engine
        if msg.type == "control_change":
            # knob learn takes priority (mirrors the pattern-note approach)
            if self.settings and self.settings.learn_param:
                self.settings.bind_cc(self.settings.learn_param, msg.control)
                self.settings.learn_param = None
                return
            custom = self.settings.custom_cc if self.settings else {}
            key = custom_key_for_cc(custom, msg.control)
            if key in ACTION_KEYS:
                # actions: fire on a rising edge, ignore the falling edge
                prev = self._act_last.get(key, 0)
                self._act_last[key] = msg.value
                if msg.value >= 64 and prev < 64 and self._actions:
                    fn = self._actions.get(key)
                    if fn:
                        fn()
                return
            ent = build_cc_map(custom).get(msg.control)
            if ent:
                pkey, lo, hi = ent
                mode = (self.settings.cc_mode.get(pkey, "absolute")
                        if self.settings else "absolute")
                self._apply_cc(pkey, msg.value, lo, hi, mode)
        elif msg.type == "note_on" and msg.velocity > 0:
            # 1) MIDI-learn capture takes priority
            if self.bank and self.bank.learn_target:
                self.bank.bind(self.bank.learn_target, msg.note)
                self.bank.learn_target = None
                return
            # 2) then pattern bindings
            if self.bank:
                name = self.bank.name_for_note(msg.note)
                if name:
                    if self.bank.apply_entry(name, eng, self.ilda_lib):
                        self._caught.clear()   # re-arm soft takeover
                        print(f"[midi] pattern → {name}")
                    return
            # 3) then shape select
            idx = msg.note - NOTE_SHAPE_BASE
            if 0 <= idx < len(SHAPE_NAMES):
                eng.set_param("shape", idx)
                print(f"[midi] shape → {SHAPE_NAMES[idx]}")

    def close(self):
        if self.port:
            self.port.close()


class AudioAnalyzer:
    """Grabs the default input device; publishes rms/bass/mid/high + waveform."""

    def __init__(self, samplerate=44100, blocksize=1024):
        self.data = None
        self._lock = threading.Lock()
        try:
            import sounddevice as sd
        except ImportError:
            print("[audio] sounddevice not installed — audio disabled")
            self.stream = None
            return
        self.samplerate = samplerate
        try:
            self.stream = sd.InputStream(
                channels=1, samplerate=samplerate, blocksize=blocksize,
                callback=self._cb)
            self.stream.start()
            print("[audio] capturing from default input device")
        except Exception as e:
            print(f"[audio] could not open input: {e} — audio disabled")
            self.stream = None

    def _cb(self, indata, frames, t, status):
        mono = indata[:, 0].astype(np.float32)
        spec = np.abs(np.fft.rfft(mono * np.hanning(len(mono))))
        freqs = np.fft.rfftfreq(len(mono), 1.0 / self.samplerate)

        def band(lo, hi):
            m = (freqs >= lo) & (freqs < hi)
            return float(np.mean(spec[m])) if np.any(m) else 0.0

        d = {
            "rms": float(np.sqrt(np.mean(mono ** 2))),
            "bass": band(20, 200), "mid": band(200, 2000),
            "high": band(2000, 8000), "wave": mono.copy(),
        }
        # crude adaptive normalisation
        with self._lock:
            prev = self.data
            for k in ("bass", "mid", "high"):
                peak_key = "_pk_" + k
                pk = prev[peak_key] if prev else 1e-6
                pk = max(d[k], pk * 0.995, 1e-6)
                d[peak_key] = pk
                d[k] = min(1.0, d[k] / pk)
            self.data = d

    def get(self):
        with self._lock:
            return self.data

    def close(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()


class Preview:
    """The desktop window: a launcher, not a control surface.

    Double-clicked from a file manager, the old window showed the beam and
    nothing else — no URL, no sign that the browser UI existed, no way to
    quit but the task manager. That is what this fixes, and that is all it
    does: the address to open, a button to open it, a button to stop, and
    enough status to show it is alive.

    Everything else — arming, blanking, parameters — stays in the browser.
    A second place to arm a laser is a second place for the two to disagree
    about whether it is armed.

    Built in pygame rather than the tkinter that promptwaver's PACKAGING.md
    recommends, because its two premises do not hold here. pygame is already
    bundled for this window, where tkinter would add tcl/tk plus a
    `python3-tk` step in Linux CI that silently degrades to console-only if
    forgotten. And the doc's central rule — Tk must own the main thread —
    inverts this app: the render loop owns the main thread on purpose,
    because the Helios paces it by blocking in GetStatus and blank-on-exit
    hangs off that.

    The beam is still a keystroke away on `v`, full-window, which is what
    this window used to be.
    """

    BASE_W, BASE_H = 560, 300
    SCALE = 2.0
    BG = (10, 12, 17)
    PANEL = (17, 21, 29)
    EDGE = (28, 34, 48)
    INK = (200, 210, 224)
    DIM = (92, 103, 120)
    ACCENT = (216, 230, 242)
    DANGER = (255, 74, 61)
    OK = (60, 200, 120)

    def __init__(self, engine, size=700, out=None, web=None, version="",
                 scale=None):
        import pygame
        self.pygame = pygame
        pygame.init()
        self.engine = engine
        self.out = out          # SafeOutput, for the ARM/DISARM keys
        self.web = web          # WebUI, for the URL and the client count
        self.version = version
        self.size = size        # beam size when showing the beam full-window
        self.beam_full = False  # `v` toggles
        # Back off the scale if the display cannot take it — at 2x this
        # window is 1440x1120, which is taller than a 1080p screen.
        self.scale = self.SCALE if scale is None else float(scale)
        if scale is None:
            try:
                info = pygame.display.Info()
                if info.current_w > 0 and info.current_h > 0:
                    fit = min((info.current_w - 40) / self.BASE_W,
                              (info.current_h - 90) / self.BASE_H)
                    self.scale = max(1.0, min(self.SCALE, fit))
            except Exception:
                pass
        # An explicit --gui-scale is honoured as given: the fit calculation
        # is a courtesy for the default, not a cap on what you asked for.
        self.W = int(self.BASE_W * self.scale)
        self.H = int(self.BASE_H * self.scale)
        self.screen = pygame.display.set_mode((self.W, self.H))
        pygame.display.set_caption("Laser! Laser Laser!")
        f = lambda pt: pygame.font.SysFont("monospace",
                                           max(9, int(pt * self.scale)))
        fb = lambda pt: pygame.font.SysFont("monospace",
                                            max(9, int(pt * self.scale)), bold=True)
        self.font = f(13)
        self.small = f(11)
        self.big = fb(20)
        self.mid = fb(15)
        self.bind_error = getattr(web, "bind_error", None)
        port = getattr(web, "port", None)
        self.url = (f"http://localhost:{port}"
                    if port and not self.bind_error else None)
        try:
            import socket
            self.lan_url = (f"http://{socket.gethostname()}:{port}"
                            if port else None)
        except Exception:
            self.lan_url = None
        self.buttons = []       # filled by draw(), hit-tested by handle_events

    # ---- helpers ----

    def u(self, v):
        """Logical layout unit -> device pixels."""
        return int(v * self.scale)

    def _text(self, surf, txt, x, y, font=None, col=None):
        surf.blit((font or self.font).render(txt, True, col or self.INK), (x, y))

    def _beam(self, surf, frame, rect):
        """Draw the frame into rect. The whole point of the thumbnail is that
        a still picture would not prove anything, so it is the real frame."""
        pg = self.pygame
        x0, y0, w, h = rect
        pg.draw.rect(surf, (0, 0, 0), rect)
        pg.draw.rect(surf, self.EDGE, rect, 1)
        if self.engine.blanked:
            self._text(surf, "BLANKED", x0 + w // 2 - 28, y0 + h // 2 - 7,
                       self.small, self.DANGER)
            return
        pts = frame.astype(float)
        xs = x0 + pts[:, 0] / 0xFFF * w
        ys = y0 + (1.0 - pts[:, 1] / 0xFFF) * h
        width = max(1, self.u(2 if w > self.u(400) else 1))
        for i in range(len(pts) - 1):
            col = (int(pts[i, 2]), int(pts[i, 3]), int(pts[i, 4]))
            if col == (0, 0, 0):
                continue                      # blanked travel move
            pg.draw.line(surf, col, (xs[i], ys[i]), (xs[i + 1], ys[i + 1]),
                         width)

    def _button(self, surf, label, rect, key, danger=False, active=False):
        pg = self.pygame
        r = pg.Rect(rect)
        bg = self.DANGER if danger else (self.ACCENT if active else self.PANEL)
        fg = (10, 12, 17) if (danger or active) else self.INK
        pg.draw.rect(surf, bg, r, border_radius=self.u(4))
        pg.draw.rect(surf, self.EDGE, r, max(1, self.u(1)),
                     border_radius=self.u(4))
        t = self.small.render(label, True, fg)
        surf.blit(t, (r.centerx - t.get_width() // 2,
                      r.centery - t.get_height() // 2))
        self.buttons.append((r, key))

    # ---- drawing ----

    def draw(self, frame, fps=0.0):
        pg, u = self.pygame, self.u
        self.buttons = []
        s = self.screen
        s.fill(self.BG)

        if self.beam_full:
            self._beam(s, frame, (0, 0, self.W, self.H))
            self._text(s, "v: back to the panel   ESC/q: quit", u(10),
                       self.H - u(18), self.small, self.DIM)
            pg.display.flip()
            return

        self._text(s, "LASER! LASER LASER!", u(16), u(14), self.big, self.ACCENT)
        if self.version:
            self._text(s, f"v{self.version}", u(268), u(20), self.small, self.DIM)

        # --- the URL, which is the whole reason this window exists ---
        if self.url:
            self._text(s, "CONTROL SURFACE — open this in a browser:",
                       u(16), u(54), self.small, self.DIM)
            self._text(s, self.url, u(16), u(72), self.mid, self.ACCENT)
            if self.lan_url and self.lan_url != self.url:
                self._text(s, f"or {self.lan_url}  (same network)", u(16),
                           u(94), self.small, self.DIM)
        elif self.bind_error:
            self._text(s, "CONTROL SURFACE UNAVAILABLE", u(16), u(54),
                       self.small, self.DANGER)
            self._text(s, self.bind_error[:64], u(16), u(72), self.font,
                       self.DANGER)
        else:
            self._text(s, "browser UI disabled (--no-web)", u(16), u(72),
                       self.mid, self.DIM)

        # --- buttons: open the thing, or stop the thing ---
        # Arming, blanking and the rest deliberately live in the browser.
        # This window is a launcher, not a second control surface.
        y, gap = u(124), u(10)
        specs = ([("OPEN BROWSER", "open")] if self.url else []) + \
                [("QUIT", "quit")]
        bw = (self.W - u(32) - (len(specs) - 1) * gap) // len(specs)
        for i, (label, key) in enumerate(specs):
            self._button(s, label, (u(16) + i * (bw + gap), y, bw, u(32)), key)

        # --- a little status, so it is visibly alive ---
        pg.draw.line(s, self.EDGE, (u(16), u(176)), (self.W - u(16), u(176)))
        out_name = self.out.name if self.out else "none"
        armed = bool(self.out and self.out.armed)
        clients = len(getattr(self.web, "_clients", ()) or ())
        rows = [
            ("output", f"{out_name}   —   "
                       + ("LASER ARMED" if armed else "disarmed")),
            # getattr: pps is assigned by main() after construction, and a
            # status panel must never be able to take down the render loop
            ("running", f"{fps:.0f} fps   {self.engine.n_points} pts @ "
                        f"{getattr(self.engine, 'pps', 0)} pps"),
            ("browsers", f"{clients} connected"),
        ]
        yy = u(188)
        for k, v in rows:
            self._text(s, k, u(16), yy, self.small, self.DIM)
            self._text(s, str(v), u(110), yy - u(1), self.font,
                       self.DANGER if (k == "output" and armed) else self.INK)
            yy += u(22)

        self._text(s, "Closing this window stops the laser and blanks it.",
                   u(16), self.H - u(22), self.small, self.DIM)
        pg.display.flip()

    # ---- input ----

    def _do(self, key):
        """A panel button. Returns False to quit."""
        if key == "quit":
            return False
        if key == "open" and self.url:
            import webbrowser
            webbrowser.open(self.url)
        return True

    def handle_events(self):
        """Returns False when the app should quit."""
        pg, p = self.pygame, self.engine.p
        for ev in pg.event.get():
            if ev.type == pg.QUIT:
                return False
            if ev.type == pg.MOUSEBUTTONDOWN and ev.button == 1:
                for rect, key in self.buttons:
                    if rect.collidepoint(ev.pos):
                        if not self._do(key):
                            return False
                        break
            if ev.type == pg.KEYDOWN:
                k, mod = ev.key, ev.mod
                shift = mod & pg.KMOD_SHIFT
                if k in (pg.K_ESCAPE, pg.K_q):
                    return False
                if k == pg.K_v:
                    self.beam_full = not self.beam_full
                elif pg.K_1 <= k <= pg.K_9:
                    p["shape"] = k - pg.K_1
                elif k == pg.K_RIGHT:
                    p["ratio_a"] = min(12, p["ratio_a"] + 1)
                elif k == pg.K_LEFT:
                    p["ratio_a"] = max(1, p["ratio_a"] - 1)
                elif k == pg.K_UP:
                    p["ratio_b"] = min(12, p["ratio_b"] + 1)
                elif k == pg.K_DOWN:
                    p["ratio_b"] = max(1, p["ratio_b"] - 1)
                elif k == pg.K_RIGHTBRACKET:
                    p["size"] = min(1, p["size"] + 0.05)
                elif k == pg.K_LEFTBRACKET:
                    p["size"] = max(0.05, p["size"] - 0.05)
                elif k == pg.K_m:
                    p["morph"] = (p["morph"] + (-0.05 if shift else 0.05)) % 1
                elif k == pg.K_s:
                    p["spin"] = np.clip(p["spin"] + (-0.05 if shift else 0.05), 0, 1)
                elif k == pg.K_h:
                    p["hue"] = (p["hue"] + 0.08) % 1
                elif k == pg.K_a:
                    p["audio_amt"] = np.clip(
                        p["audio_amt"] + (-0.1 if shift else 0.1), 0, 1)
                elif k == pg.K_d:
                    p["dup_count"] = np.clip(
                        p["dup_count"] + (-1 if shift else 1), 1, 6)
                elif k == pg.K_c:
                    p["mono"] = 0.0 if p["mono"] > 0.5 else 1.0
                elif k == pg.K_f:
                    p["flip_x"] = 0.0 if p["flip_x"] > 0.5 else 1.0
                elif k == pg.K_g:
                    p["flip_y"] = 0.0 if p["flip_y"] > 0.5 else 1.0
                elif k == pg.K_SPACE:
                    self.engine.blanked = not self.engine.blanked
                # Panic-off you can hit without the browser focused. Bare `.`
                # disarms; shift-. arms, so arming is never a one-key slip.
                elif k == pg.K_PERIOD and self.out:
                    self.out.set_armed(bool(shift))
                    print("[laser] ARMED" if self.out.armed
                          else "[laser] disarmed")
        return True

    def close(self):
        self.pygame.quit()


MONO_LASER_COLOURS = ("r", "g", "b")     # column offset 0/1/2 into rgb


def mono_laser(frame, colour, ttl=True, thresh=0.5):
    """Collapse colour onto the single diode a monochrome projector has.

    Not the same thing as the MONO button, which picks one *hue* out of the
    palette and is a creative choice. This describes the hardware: a
    red-only (or green-, or blue-only) projector, where every other channel
    is a wire to nothing.

    The naive version — zero the two channels the device lacks — is wrong,
    and wrong in a way that looks like a bug. Content is hue-ramped along
    the path, so a red-only device would draw only the arcs that happen to
    be red and drop out through the cyan half of every rainbow. Instead
    take each point's *level* as the strongest channel it had and put it on
    the diode that exists, so the figure is drawn whole, continuously,
    whatever hue it was authored in.

    max() rather than a luma weighting on purpose: luma would render blues
    at 11% and the beam would visibly dim through those arcs, which is the
    same drop-out problem in a subtler form.

    `ttl` is the common case for these projectors: the diode is switched,
    not dimmed — full power or dark, with nothing in between. Feeding it a
    graded level is then a fiction, because every non-zero value comes out
    at 100%. So in TTL mode the level is thresholded to a clean on/off,
    and the threshold is taken *relative to the brightest point in the
    frame* rather than as an absolute. Absolute would mean the brightness
    fader silently blanked the whole figure once it fell under the line;
    relative keeps the structure the content actually has — a comet still
    reads as a comet — and matches the hardware, where brightness is not a
    thing you have.

    Applied to the *shared* frame, not the DAC copy — unlike hw_orient and
    geom. Those stay DAC-only so the preview remains a true alignment
    reference; the brightness ceiling stays DAC-only so it is conspicuous.
    Neither argument applies here: on a one-colour projector a rainbow
    preview is simply a lie about what the wall will show, so preview,
    browser scope and monitor all agree with the beam. Same reasoning as
    the mask.
    """
    try:
        idx = MONO_LASER_COLOURS.index(colour)
    except ValueError:
        return frame
    out = frame.copy()
    rgb = out[:, 2:5]
    level = rgb.max(axis=1)          # 0 stays 0, so blanking survives
    if ttl:
        peak = int(level.max())
        if peak <= 0:
            level = np.zeros_like(level)
        else:
            # `level > 0` is load-bearing: at thresh 0 the >= test alone
            # would light every blanked point in the frame, bridges included
            cut = max(1, int(round(float(thresh) * peak)))
            level = np.where((level > 0) & (level >= cut), 255, 0)
        # the intensity column is switched too, or a device that reads it
        # would see a graded value the diode cannot produce
        out[:, 5] = np.where(level > 0, 255, 0).astype(out.dtype)
    rgb[:] = 0
    rgb[:, idx] = level
    return out


def hw_orient(frame, flip_x, flip_y):
    """Projector output orientation. Applied only to the DAC stream so the
    wall matches the preview; separate from the artistic FLIP X/Y buttons.
    Also corrects apparent spin direction (a mirror reverses rotation)."""
    if not flip_x and not flip_y:
        return frame
    out = frame.copy()
    if flip_x:
        out[:, 0] = 0xFFF - out[:, 0]
    if flip_y:
        out[:, 1] = 0xFFF - out[:, 1]
    return out


def main():
    ap = argparse.ArgumentParser(description="Laser! Laser Laser! — Helios laser visuals synth")
    ap.add_argument("--version", action="version",
                    version=f"Laser! Laser Laser! {__version__}")
    ap.add_argument("--gui-scale", type=float, default=None,
                    help="size of the desktop window (default: 2x, backed "
                         "off if the display is too small for it)")
    ap.add_argument("--laser", action="store_true", help="output to Helios DAC")
    ap.add_argument("--output", choices=("none", "helios", "lasercube"),
                    default=None,
                    help="output backend (default none; --laser is an alias "
                         "for --output helios)")
    ap.add_argument("--lasercube-ip", default=None,
                    help="LaserCube address (default: discover by broadcast)")
    ap.add_argument("--lasercube-dry-run", action="store_true",
                    help="pack and rate-control but send nothing — validates "
                         "the whole path with zero photons")
    ap.add_argument("--lasercube-point-order", choices=("xyrgb", "rgbxy"),
                    default="xyrgb",
                    help="wire field order (default xyrgb; see "
                         "lasercube_output.py's module docstring)")
    ap.add_argument("--list-lasercubes", action="store_true",
                    help="discover LaserCubes on the network and exit")
    ap.add_argument("--max-brightness", type=float, default=None,
                    help="hard ceiling on output brightness, 0..1 "
                         "(default 0.05). A creative limiter, NOT a safety "
                         "interlock — see docs/lasercubeoutput.md §4.4")
    ap.add_argument("--preview", action="store_true", help="pygame preview window")
    ap.add_argument("--points", type=int, default=800, help="points per frame")
    ap.add_argument("--pps", type=int, default=30000, help="DAC points per second")
    ap.add_argument("--midi", default=None, help="MIDI port name substring")
    ap.add_argument("--no-audio", action="store_true", help="disable audio input")
    ap.add_argument("--hw-flip-x", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="mirror X on the DAC output so the projected image "
                         "matches the preview (default on; --no-hw-flip-x "
                         "if your projector is oriented the other way)")
    ap.add_argument("--hw-flip-y", action=argparse.BooleanOptionalAction,
                    default=False, help="mirror Y on the DAC output")
    ap.add_argument("--web", action=argparse.BooleanOptionalAction,
                    default=None,
                    help="serve browser control surface (on by default; "
                         "--no-web to disable)")
    ap.add_argument("--web-port", type=int, default=8080)
    ap.add_argument("--list-midi", action="store_true")
    args = ap.parse_args()

    if args.list_midi:
        import mido
        print("\n".join(mido.get_input_names()) or "(none)")
        return

    if args.list_lasercubes:
        from lasercube_output import discover
        found = discover()
        for ip, info in found:
            print(f"{ip}  fw {info.get('fw','?')}  "
                  f"{info.get('connection','?')}  "
                  f"battery {info.get('battery_pct','?')}%  "
                  f"{info.get('temperature_c','?')}°C  "
                  f"max {info.get('max_dac_rate','?')} pps")
        print(f"({len(found)} found)" if found else "(none found)")
        return

    if args.output is None:
        args.output = "helios" if args.laser else "none"
    args.laser = args.output != "none"

    if not args.laser and not args.preview and not args.web:
        args.preview = True  # sensible default: don't fire a laser by surprise
    if args.web is None:
        args.web = True  # on by default (including prebuilt executables); --no-web opts out

    import os as _os
    engine = ShapeEngine(n_points=args.points)
    _here = _os.path.dirname(_os.path.abspath(__file__))
    crashlog.step(f"loading data from {_here}")
    bank = PatternBank(_os.path.join(_here, "patterns.json"))
    ilda_lib = IldaLibrary(_os.path.join(_here, "ilda"))
    vec = VectorSource(engine)
    geom = GeometryCorrection()
    mask = MaskFilter()
    mask_bank = MaskBank(_os.path.join(_here, "masks.json"))
    settings = SettingsStore(_os.path.join(_here, "settings.json"))
    # saved settings win over CLI defaults; CLI seeds first run
    engine.pps = int(settings.get("pps", args.pps))
    engine.n_points = int(settings.get("points", args.points))
    engine.hw_flip_x = bool(settings.get("hw_flip_x", args.hw_flip_x))
    engine.hw_flip_y = bool(settings.get("hw_flip_y", args.hw_flip_y))
    engine.mono_laser = bool(settings.get("mono_laser", False))
    engine.mono_laser_colour = str(settings.get("mono_laser_colour", "r"))
    engine.mono_laser_ttl = bool(settings.get("mono_laser_ttl", True))
    engine.mono_laser_thresh = float(settings.get("mono_laser_thresh", 0.5))
    engine.xfade_time = float(settings.get("xfade_time", 2.0))
    geom.set_corners(settings.get("corners", [0.0] * 8))
    geom.set_pincushion(float(settings.get("pincushion", 0.0)))
    mask.restore(settings.get("mask", {}))
    midi = MidiInput(engine, args.midi, bank=bank, ilda_lib=ilda_lib,
                     settings=settings)
    engine.on_load = midi._caught.clear   # re-arm soft takeover on any load
    audio = None if args.no_audio else AudioAnalyzer()

    web = None
    crashlog.step("settings and banks loaded")
    if args.web:
        from webui import WebUI
        web = WebUI(engine, port=args.web_port, bank=bank,
                    ilda_lib=ilda_lib, vec=vec, settings=settings,
                    midi=midi, geom=geom, mask=mask, mask_bank=mask_bank)

    # ---- output backend + safety layer ----
    # Literal if/elif with direct imports so PyInstaller can trace them;
    # importlib here would silently drop a backend from the bundle. Both
    # backends are imported lazily so a missing Helios library never stops
    # the LaserCube path working, or vice versa.
    def make_backend(kind):
        if kind == "helios":
            from helios import HeliosOutput
            b = HeliosOutput(0)
            print(f"[laser] Helios DAC ready ({b.num_devices} device(s))")
            return b
        if kind == "lasercube":
            from lasercube_output import LaserCubeOutput
            return LaserCubeOutput(ip=args.lasercube_ip,
                                   pps=engine.pps,
                                   point_order=args.lasercube_point_order,
                                   dry_run=args.lasercube_dry_run)
        return NullOutput()

    # A saved output choice applies when the CLI didn't name one, exactly like
    # pps/points above.
    explicit = args.output != "none"
    kind = args.output if explicit else str(settings.get("output", "none"))
    try:
        backend = make_backend(kind)
    except Exception as e:
        # An explicit --output/--laser is a statement about which projector is
        # plugged in. Failing that silently and running with no output would
        # let someone believe the laser is live when nothing is connected, so
        # it is fatal. A *remembered* choice is only a preference, and falls
        # back — you should be able to start the app after unplugging.
        if explicit:
            print(f"[laser] could not open {kind}: {e}")
            return 1
        print(f"[laser] could not open saved output {kind}: {e} "
              "— starting with no output")
        backend, kind = NullOutput(), "none"
    args.laser = kind != "none"

    cap = (args.max_brightness if args.max_brightness is not None
           else float(settings.get("max_brightness", 0.05)))
    out = SafeOutput(backend, max_brightness=cap)
    dac = backend if args.laser else None    # for the existing `if dac:` HUD
    midi.out = out
    if web:
        web.status["laser"] = args.laser
        web.out = out
        web.make_backend = make_backend

    # Wait for the bind before building the window, so it can show what
    # actually happened rather than an optimistic URL (PACKAGING.md §1).
    if web is not None:
        crashlog.step(f"starting web server on port {args.web_port}")
        web.ready.wait(5.0)
        crashlog.step("web server: "
                      + (web.bind_error or f"listening on {web.port}"))
    crashlog.step("opening window" if args.preview
                  else "no window (--web only)")
    preview = (Preview(engine, out=out, web=web, version=__version__,
                       scale=args.gui_scale)
               if args.preview else None)

    print(f"[run] {engine.n_points} pts @ {engine.pps} pps ≈ "
          f"{engine.pps / engine.n_points:.0f} fps — Ctrl-C to quit")
    if args.laser:
        print(f"[laser] DISARMED — ceiling {out.max_brightness:.0%}. "
              "Nothing is emitted until you ARM.")

    # Installed last, so nothing set up above displaces the handlers. Without
    # the SIGTERM handler a `kill` skips the finally below entirely and the
    # DAC keeps replaying its last frame.
    install_panic_handlers(out)

    crashlog.step(f"entering render loop — output={out.name}, "
                  f"{engine.n_points} pts @ {engine.pps} pps")
    last = time.monotonic()
    fps_ema = 0.0
    armed_was = None          # arm transitions are logged, see below
    try:
        while True:
            now = time.monotonic()
            dt, last = now - last, now

            # per-pattern PPS/points overrides win over system settings when
            # a loaded pattern set them; otherwise fall back to the engine's
            # configured values.
            eff_points = int(engine.pattern_points or engine.n_points)
            eff_pps = int(engine.pattern_pps or engine.pps)
            if engine.n_points != eff_points:
                engine.n_points = eff_points   # engine.frame() reads this

            vec.tick()
            a = audio.get() if (audio and audio.data) else None
            frame = engine.frame(dt, a)
            if engine.blanked:
                frame[:, 2:6] = 0
            # masking happens before the preview/web/DAC split so all three
            # agree — unlike hw_orient/geom, which are DAC-only
            frame = mask.apply(frame)
            # same reasoning as the mask: a one-colour projector should look
            # like one on the monitor too, so this is shared, not DAC-only
            if engine.mono_laser:
                frame = mono_laser(frame, engine.mono_laser_colour,
                                   engine.mono_laser_ttl,
                                   engine.mono_laser_thresh)
            fps_ema = 0.9 * fps_ema + 0.1 * (1.0 / max(dt, 1e-6))

            # Arm transitions go in the log. Polled rather than hooked so
            # every route is covered — browser, MIDI, panel button, keyboard
            # — and so laser_output.py, which is copied verbatim into the
            # sibling projects, needs no knowledge of this module.
            if out.armed != armed_was:
                armed_was = out.armed
                crashlog.step(f"output {'ARMED' if out.armed else 'disarmed'}"
                              f" — ceiling {out.max_brightness:.0%},"
                              f" device {out.name}")

            if preview:
                if not preview.handle_events():
                    break
                preview.draw(frame, fps_ema)

            if web:
                web.publish(frame, a, fps_ema)

            # hw_orient and geom are DAC-only, so the preview stays a true,
            # uncorrected reference. SafeOutput's arm gate and brightness
            # ceiling are applied inside out.write(), downstream of both.
            out_frame = hw_orient(frame, engine.hw_flip_x, engine.hw_flip_y)
            out_frame = geom.apply(out_frame)
            if not out.write(out_frame, eff_pps) and dac:
                print("[laser] frame dropped (DAC busy)")

            if not out.paces_loop:
                # Helios paces us by blocking on GetStatus; everything else
                # has to keep its own time.
                frame_dt = eff_points / max(eff_pps, 1000)
                spare = frame_dt - (time.monotonic() - now)
                if spare > 0:
                    time.sleep(spare)
    except KeyboardInterrupt:
        pass
    finally:
        crashlog.step("shutting down — blanking output")
        vec.stop_camera()
        out.close()
        if dac:
            print("[laser] blanked and closed")
        if audio:
            audio.close()
        if midi:
            midi.close()
        if preview:
            preview.close()
        # `finally` also runs while an exception is on its way to the hook,
        # so ask what is in flight rather than assuming this was a clean
        # shutdown — a log claiming "clean exit" above a traceback is worse
        # than no log
        _exc = sys.exc_info()[0]
        crashlog.finish("clean exit" if _exc is None
                        else f"shutting down after {_exc.__name__}")


if __name__ == "__main__":
    sys.exit(main() or 0)
