"""
masks.py — named polygon masks ("venue masks"), persisted to masks.json
next to the scripts. Same shape as patterns.py: plain JSON, hand-editable,
atomic writes (temp file + rename) so a crash mid-save can't corrupt it.

File format: { "back wall": {"polys": [[[x,y], ...], ...], "invert": false} }
"""

import json
import os
import threading

from mask import clean_polys


class MaskBank:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self.masks = {}
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, dict) and "polys" in v:
                        self.masks[k] = {"polys": clean_polys(v["polys"]),
                                         "invert": bool(v.get("invert"))}
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[masks] could not read {path}: {e} — starting empty")

    def names(self):
        return sorted(self.masks)

    def save(self, name, polys, invert=False):
        name = str(name).strip()[:32]
        clean = clean_polys(polys)
        if not name or not clean:
            return False
        with self._lock:
            self.masks[name] = {"polys": clean, "invert": bool(invert)}
            self._write()
        print(f"[masks] saved mask '{name}' ({len(clean)} shape(s))")
        return True

    def entry(self, name):
        return self.masks.get(name)

    def delete(self, name):
        with self._lock:
            if name not in self.masks:
                return False
            del self.masks[name]
            self._write()
        print(f"[masks] deleted mask '{name}'")
        return True

    def _write(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.masks, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)
