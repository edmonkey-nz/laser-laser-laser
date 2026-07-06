"""
patterns.py — named parameter snapshots ("patterns"), persisted to a
plain JSON file next to the scripts. Hand-editable, easy to back up,
no dependencies. Writes are atomic (temp file + rename) so a crash
mid-save can't corrupt the bank.
"""

import json
import os
import threading


class PatternBank:
    """
    File format (v2): { "name": {"params": {...}, "midi_note": 38|null} }
    v1 files (flat param dicts) are migrated transparently on load.
    """

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self.patterns = {}
        self.learn_target = None   # pattern name awaiting a MIDI note
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, dict) and "params" in v:
                        self.patterns[k] = v
                    elif isinstance(v, dict):     # v1 migration
                        self.patterns[k] = {"params": v, "midi_note": None}
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[bank] could not read {path}: {e} — starting empty")

    def names(self):
        return sorted(self.patterns)

    def save(self, name, params, ilda_file=None):
        name = str(name).strip()[:32]
        if not name:
            return False
        with self._lock:
            note = self.patterns.get(name, {}).get("midi_note")
            self.patterns[name] = {
                "params": {k: float(v) for k, v in params.items()},
                "midi_note": note,
                "ilda_file": ilda_file or None,
            }
            self._write()
        print(f"[bank] saved pattern '{name}'")
        return True

    def load(self, name):
        entry = self.patterns.get(name)
        return entry["params"] if entry else None

    def entry(self, name):
        return self.patterns.get(name)

    def delete(self, name):
        with self._lock:
            if name not in self.patterns:
                return False
            del self.patterns[name]
            self._write()
        if self.learn_target == name:
            self.learn_target = None
        print(f"[bank] deleted pattern '{name}'")
        return True

    # ---- MIDI note bindings ----
    def bind(self, name, note):
        """Bind a note to a pattern (steals it from any other pattern).
        note=None clears the binding."""
        with self._lock:
            if name not in self.patterns:
                return False
            if note is not None:
                for other in self.patterns.values():
                    if other.get("midi_note") == note:
                        other["midi_note"] = None
            self.patterns[name]["midi_note"] = note
            self._write()
        print(f"[bank] '{name}' midi note -> {note}")
        return True

    def name_for_note(self, note):
        for n, e in self.patterns.items():
            if e.get("midi_note") == note:
                return n
        return None

    def apply_entry(self, name, engine, ilda_lib=None):
        """Load a pattern into the engine: params (snap or xfade), plus the
        ILDA file it was saved with, if any. Shared by web UI and MIDI."""
        entry = self.patterns.get(name)
        if not entry:
            return False
        f = entry.get("ilda_file")
        if f and ilda_lib:
            frames = ilda_lib.frames(f)
            if frames:
                engine.set_ilda(frames, f)
            else:
                print(f"[bank] pattern '{name}': ILDA file '{f}' unavailable")
        engine.apply_params(entry["params"])
        return True

    def bindings(self):
        return {n: e["midi_note"] for n, e in self.patterns.items()
                if e.get("midi_note") is not None}

    def _write(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.patterns, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)
