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

Default MIDI CC map (channel-agnostic):
  CC1→ratio A  CC2→ratio B  CC3→morph  CC4→spin  CC5→size
  CC6→hue  CC7→hue cycle  CC8→audio amount  CC9→brightness
  CC10→pos X  CC11→pos Y  CC12→sweep depth  CC13→sweep speed
  CC14→copies  CC15→spread  CC16→falloff  CC17→orbit
  CC18→mono  CC19→flip X  CC20→flip Y  CC21→dotify
  Notes bound to patterns (MIDI learn in the web UI) load those patterns.
  Notes from C1 (36) upward select shapes.
"""

__version__ = "1.0.0"

import argparse
import sys
import threading
import time

import numpy as np

from ilda import IldaLibrary
from geometry import GeometryCorrection, test_pattern
from settings import SettingsStore
from vectorise import VectorSource
from patterns import PatternBank
from shapes import ShapeEngine, SHAPE_NAMES

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
}

# value ranges for every MIDI-mappable parameter (used by custom mapping)
PARAM_RANGES = {key: (lo, hi) for key, lo, hi in CC_MAP.values()}


# momentary "action" params: mappable like any other, but instead of
# setting a value, a rising edge (value >= 64) fires a callback. The web
# UI and MIDI both address these by name so LEARN works identically.
ACTION_KEYS = ("act_pause", "act_stop_spin", "act_blank")


def _register_actions(engine):
    def toggle_pause():
        engine.paused = not engine.paused

    def stop_spin():
        engine.set_param("spin", 0.5)
        engine.rot = 0.0

    def toggle_blank():
        engine.blanked = not engine.blanked

    return {"act_pause": toggle_pause,
            "act_stop_spin": stop_spin,
            "act_blank": toggle_blank}


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
        self._actions = _register_actions(engine)
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
    """pygame window mirroring the laser output, with keyboard control."""

    def __init__(self, engine, size=700):
        import pygame
        self.pygame = pygame
        pygame.init()
        self.size = size
        self.screen = pygame.display.set_mode((size, size))
        pygame.display.set_caption("Laser! Laser Laser!")
        self.engine = engine
        self.font = pygame.font.SysFont("monospace", 13)

    def draw(self, frame):
        pg = self.pygame
        self.screen.fill((6, 6, 10))
        pts = frame.astype(float)
        xs = pts[:, 0] / 0xFFF * self.size
        ys = (1.0 - pts[:, 1] / 0xFFF) * self.size
        if not self.engine.blanked:
            for i in range(len(pts) - 1):
                col = (int(pts[i, 2]), int(pts[i, 3]), int(pts[i, 4]))
                pg.draw.line(self.screen, col, (xs[i], ys[i]),
                             (xs[i + 1], ys[i + 1]), 2)
        p = self.engine.p
        hud = (f"{SHAPE_NAMES[int(p['shape'])]}  a={p['ratio_a']:.1f} "
               f"b={p['ratio_b']:.1f} morph={p['morph']:.2f} "
               f"spin={p['spin']:.2f} size={p['size']:.2f} "
               f"audio={p['audio_amt']:.2f}"
               + ("  [BLANKED]" if self.engine.blanked else ""))
        self.screen.blit(self.font.render(hud, True, (180, 180, 180)), (8, 8))
        pg.display.flip()

    def handle_events(self):
        """Returns False when the app should quit."""
        pg, p = self.pygame, self.engine.p
        for ev in pg.event.get():
            if ev.type == pg.QUIT:
                return False
            if ev.type == pg.KEYDOWN:
                k, mod = ev.key, ev.mod
                shift = mod & pg.KMOD_SHIFT
                if k in (pg.K_ESCAPE, pg.K_q):
                    return False
                if pg.K_1 <= k <= pg.K_9:
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
        return True

    def close(self):
        self.pygame.quit()


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
    ap.add_argument("--laser", action="store_true", help="output to Helios DAC")
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
    ap.add_argument("--web", action="store_true",
                    help="serve browser control surface")
    ap.add_argument("--web-port", type=int, default=8080)
    ap.add_argument("--list-midi", action="store_true")
    args = ap.parse_args()

    if args.list_midi:
        import mido
        print("\n".join(mido.get_input_names()) or "(none)")
        return

    if not args.laser and not args.preview and not args.web:
        args.preview = True  # sensible default: don't fire a laser by surprise

    import os as _os
    engine = ShapeEngine(n_points=args.points)
    _here = _os.path.dirname(_os.path.abspath(__file__))
    bank = PatternBank(_os.path.join(_here, "patterns.json"))
    ilda_lib = IldaLibrary(_os.path.join(_here, "ilda"))
    vec = VectorSource(engine)
    geom = GeometryCorrection()
    settings = SettingsStore(_os.path.join(_here, "settings.json"))
    # saved settings win over CLI defaults; CLI seeds first run
    engine.pps = int(settings.get("pps", args.pps))
    engine.n_points = int(settings.get("points", args.points))
    engine.hw_flip_x = bool(settings.get("hw_flip_x", args.hw_flip_x))
    engine.hw_flip_y = bool(settings.get("hw_flip_y", args.hw_flip_y))
    engine.xfade_time = float(settings.get("xfade_time", 2.0))
    geom.set_corners(settings.get("corners", [0.0] * 8))
    geom.set_pincushion(float(settings.get("pincushion", 0.0)))
    midi = MidiInput(engine, args.midi, bank=bank, ilda_lib=ilda_lib,
                     settings=settings)
    engine.on_load = midi._caught.clear   # re-arm soft takeover on any load
    audio = None if args.no_audio else AudioAnalyzer()

    web = None
    if args.web:
        from webui import WebUI
        web = WebUI(engine, port=args.web_port, bank=bank,
                    ilda_lib=ilda_lib, vec=vec, settings=settings,
                    midi=midi, geom=geom)

    dac = None
    if args.laser:
        from helios import HeliosDAC
        dac = HeliosDAC(0)
        print(f"[laser] Helios DAC ready ({dac.num_devices} device(s))")
        if web:
            web.status["laser"] = True

    preview = Preview(engine) if args.preview else None

    print(f"[run] {engine.n_points} pts @ {engine.pps} pps ≈ "
          f"{engine.pps / engine.n_points:.0f} fps — Ctrl-C to quit")

    last = time.monotonic()
    fps_ema = 0.0
    try:
        while True:
            now = time.monotonic()
            dt, last = now - last, now

            vec.tick()
            a = audio.get() if (audio and audio.data) else None
            frame = engine.frame(dt, a)
            if engine.blanked:
                frame[:, 2:6] = 0
            fps_ema = 0.9 * fps_ema + 0.1 * (1.0 / max(dt, 1e-6))

            if preview:
                if not preview.handle_events():
                    break
                preview.draw(frame)

            if web:
                web.publish(frame, a, fps_ema)

            if dac:
                # write_frame blocks on GetStatus, which paces us to the DAC
                out_frame = hw_orient(frame, engine.hw_flip_x,
                                      engine.hw_flip_y)
                out_frame = geom.apply(out_frame)
                if not dac.write_frame(out_frame, engine.pps):
                    print("[laser] frame dropped (DAC busy)")
            else:
                frame_dt = engine.n_points / max(engine.pps, 1000)
                spare = frame_dt - (time.monotonic() - now)
                if spare > 0:
                    time.sleep(spare)
    except KeyboardInterrupt:
        pass
    finally:
        vec.stop_camera()
        if dac:
            dac.close()
            print("[laser] blanked and closed")
        if audio:
            audio.close()
        if midi:
            midi.close()
        if preview:
            preview.close()


if __name__ == "__main__":
    main()
