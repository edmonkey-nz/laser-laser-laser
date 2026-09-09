"""
crashlog.py — the only diagnostic you get back from the field.

A packaged build that dies has no console to print to, and on this app the
most likely deaths leave no Python traceback at all: the Helios driver is
reached through ctypes, MIDI through rtmidi, the window through SDL. A
segfault in any of those unwinds nothing. So the breadcrumb trail matters
more than the traceback — the last line written is the evidence of how far
it got.

Written beside the executable when frozen, or next to the scripts from a
checkout. Every line opens, writes, flushes and closes the file, so a
process that is killed outright still leaves the trail on disk.

Kept to the standard library on purpose: this is installed *above* the
project's own imports, because a missing bundled module or a broken native
dependency is one of the things it exists to diagnose, and a handler
installed after the failing import never runs.
"""

import os
import sys
import time
import traceback

LOG_NAME = "error.txt"
PREV_NAME = "error.prev.txt"

_path = None
_start = None


def log_dir():
    """Where the log goes.

    Frozen: beside the executable, so it is where the user can find it and
    not inside a bundle directory. Falls back to the home directory when the
    install location is read-only (Program Files, /Applications).
    """
    if getattr(sys, "frozen", False):
        beside = os.path.dirname(os.path.abspath(sys.executable))
        if os.access(beside, os.W_OK):
            return beside
        home = os.path.join(os.path.expanduser("~"), ".laserlaserlaser")
        try:
            os.makedirs(home, exist_ok=True)
        except OSError:
            return os.path.abspath(".")
        return home
    return os.path.dirname(os.path.abspath(__file__))


def path():
    return _path


def _write(line):
    if not _path:
        return
    try:
        with open(_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    except OSError:
        pass          # a log that cannot be written must never stop the app


def step(msg):
    """A startup/lifecycle breadcrumb. Cheap enough to call freely, but not
    per frame — the point is the sequence, not a trace."""
    dt = (time.monotonic() - _start) if _start else 0.0
    _write(f"[{dt:7.2f}s] {msg}")


def install(version="", argv=None):
    """Start a fresh log and take over the exception hooks.

    Call this before importing anything else of the project's own.
    """
    global _path, _start
    _start = time.monotonic()
    d = log_dir()
    _path = os.path.join(d, LOG_NAME)
    # keep one previous run: a crash followed by a restart would otherwise
    # overwrite the only evidence of the crash
    try:
        if os.path.exists(_path):
            os.replace(_path, os.path.join(d, PREV_NAME))
    except OSError:
        pass
    meipass = getattr(sys, "_MEIPASS", None)
    header = [
        "=" * 68,
        f"Laser! Laser Laser! {version}".rstrip(),
        time.strftime("%Y-%m-%d %H:%M:%S"),
        f"python   {sys.version.split()[0]}  ({sys.executable})",
        f"platform {sys.platform}",
        f"frozen   {bool(getattr(sys, 'frozen', False))}"
        + (f"   _MEIPASS {meipass}" if meipass else ""),
        f"cwd      {os.getcwd()}",
        f"argv     {' '.join(argv or sys.argv)}",
        "=" * 68,
    ]
    for line in header:
        _write(line)

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            _write("\n[exit] KeyboardInterrupt")
            sys.__excepthook__(exc_type, exc, tb)
            return
        _write("\n--- UNHANDLED EXCEPTION ---")
        _write("".join(traceback.format_exception(exc_type, exc, tb)).rstrip())
        sys.__excepthook__(exc_type, exc, tb)
        print(f"\n[crash] details written to {_path}", file=sys.stderr)
        _hold_console()

    sys.excepthook = hook

    # Daemon threads die silently by default, and this app runs the web
    # server, the LaserCube sender and audio capture on them. A dead worker
    # with a live main loop is exactly the confusing case worth catching.
    try:
        import threading

        def thook(args):
            _write(f"\n--- UNHANDLED EXCEPTION in thread "
                   f"{getattr(args.thread, 'name', '?')} ---")
            _write("".join(traceback.format_exception(
                args.exc_type, args.exc_value, args.exc_traceback)).rstrip())
            print(f"[crash] thread {getattr(args.thread, 'name', '?')} died — "
                  f"see {_path}", file=sys.stderr)

        threading.excepthook = thook
    except Exception:
        pass
    return _path


def _hold_console():
    """Keep a double-clicked window open long enough to read the error.

    Guarded on isatty so a piped or service run does not hang forever.
    """
    if not getattr(sys, "frozen", False):
        return
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            input("\nPress Enter to close...")
    except Exception:
        pass


def finish(msg="clean exit"):
    """Mark a normal shutdown, so a log that simply stops is distinguishable
    from one that was closed properly."""
    step(msg)
