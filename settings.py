"""
settings.py — persistent synth settings, stored in settings.json next to
the scripts (atomic writes, hand-editable):

  {
    "cc_map": {"size": 10, ...},        # custom param -> MIDI CC bindings
    "cc_mode": {"size": "catch", ...},  # per-param encoder mode
    "pps": 30000, "points": 800,        # runtime engine settings
    "hw_flip_x": true, "hw_flip_y": false,
    "xfade_time": 2.0
  }

Encoder modes:
  absolute  0..127 maps straight to the value range (default)
  relative  encoder sends deltas (auto-detects two-s-complement and
            64-centred encodings); nudges from the current value
  catch     absolute knob, but ignored until it crosses the current
            value ("soft takeover"), so pattern loads never cause jumps

Values saved here win over CLI defaults on the next launch — the
Settings page is the persistent config; CLI flags seed first run.
"""

import json
import os
import threading


class SettingsStore:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self.data = {}
        self.learn_param = None      # param awaiting a MIDI CC (knob learn)
        try:
            with open(path) as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.data = d
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[settings] could not read {path}: {e} — using defaults")
        self.data.setdefault("cc_map", {})
        self.data.setdefault("cc_mode", {})

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        with self._lock:
            self.data[key] = value
            self._write()

    # ---- custom MIDI CC bindings (param -> cc) ----
    @property
    def custom_cc(self):
        return self.data.get("cc_map", {})

    def bind_cc(self, param, cc):
        """Bind a CC to a param, stealing it from any other param."""
        with self._lock:
            m = self.data.setdefault("cc_map", {})
            for k in [k for k, v in m.items() if v == cc]:
                del m[k]
            m[param] = int(cc)
            self._write()
        print(f"[settings] CC {cc} -> {param}")

    def unmap(self, param):
        with self._lock:
            m = self.data.setdefault("cc_map", {})
            mode = self.data.setdefault("cc_mode", {})
            changed = False
            if param in m:
                del m[param]; changed = True
            if param in mode:
                del mode[param]; changed = True
            if changed:
                self._write()
                print(f"[settings] {param} back to default mapping")

    @property
    def cc_mode(self):
        return self.data.get("cc_mode", {})

    def set_mode(self, param, mode):
        if mode not in ("absolute", "relative", "catch"):
            return
        with self._lock:
            modes = self.data.setdefault("cc_mode", {})
            if mode == "absolute":
                modes.pop(param, None)
            else:
                modes[param] = mode
            self._write()
        print(f"[settings] {param} encoder mode -> {mode}")

    def _write(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)
