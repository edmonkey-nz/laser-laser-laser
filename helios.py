"""
helios.py — thin ctypes wrapper around libHeliosDacAPI.so (Grix/helios_dac SDK).

Classic WriteFrame() interface: 12-bit X/Y (0..4095), 8-bit R/G/B/I.
Expects libHeliosDacAPI.so next to this file (or HeliosLaserDAC.dll on Windows).
"""

import ctypes
import os
import platform
import time

HELIOS_FLAGS_DEFAULT = 0
HELIOS_FLAG_START_IMMEDIATELY = 1 << 0
HELIOS_FLAG_SINGLE_MODE = 1 << 1
HELIOS_FLAG_DONT_BLOCK = 1 << 2

XY_MAX = 0xFFF  # 12-bit


class HeliosPoint(ctypes.Structure):
    _fields_ = [('x', ctypes.c_uint16),
                ('y', ctypes.c_uint16),
                ('r', ctypes.c_uint8),
                ('g', ctypes.c_uint8),
                ('b', ctypes.c_uint8),
                ('i', ctypes.c_uint8)]


def _lib_path():
    here = os.path.dirname(os.path.abspath(__file__))
    system = platform.system()
    if system == "Windows":
        return os.path.join(here, "HeliosLaserDAC.dll")
    if system == "Darwin":
        return os.path.join(here, "libHeliosDacAPI.dylib")
    return os.path.join(here, "libHeliosDacAPI.so")


class HeliosDAC:
    """Manages one Helios DAC (device 0 by default)."""

    def __init__(self, dac_num=0):
        self.lib = ctypes.cdll.LoadLibrary(_lib_path())
        self.dac_num = dac_num
        self.num_devices = self.lib.OpenDevices()
        if self.num_devices <= dac_num:
            self.lib.CloseDevices()
            raise RuntimeError(
                f"Helios DAC #{dac_num} not found "
                f"({self.num_devices} device(s) detected). "
                "On Linux, check udev rules or run with sudo.")

    def write_frame(self, points_np, pps, timeout=0.5):
        """
        points_np: numpy uint16/uint8 structured data as (N,6) int array
                   columns: x, y (0..4095), r, g, b, i (0..255)
        Blocks (polling GetStatus) until the DAC buffer is free, then sends.
        Returns False on timeout or write error.
        """
        n = len(points_np)
        frame = (HeliosPoint * n)()
        # Bulk fill via ctypes.memmove from a packed numpy view
        import numpy as np
        packed = np.zeros(n, dtype=[('x', '<u2'), ('y', '<u2'),
                                    ('r', 'u1'), ('g', 'u1'),
                                    ('b', 'u1'), ('i', 'u1')])
        packed['x'] = points_np[:, 0]
        packed['y'] = points_np[:, 1]
        packed['r'] = points_np[:, 2]
        packed['g'] = points_np[:, 3]
        packed['b'] = points_np[:, 4]
        packed['i'] = points_np[:, 5]
        ctypes.memmove(frame, packed.tobytes(), ctypes.sizeof(frame))

        deadline = time.monotonic() + timeout
        while self.lib.GetStatus(self.dac_num) != 1:
            if time.monotonic() > deadline:
                return False
            time.sleep(0.0005)
        return self.lib.WriteFrame(self.dac_num, int(pps),
                                   HELIOS_FLAGS_DEFAULT, frame, n) == 1

    def stop(self):
        """Blank, stop and centre output."""
        try:
            self.lib.Stop(self.dac_num)
        except Exception:
            pass

    def close(self):
        self.stop()
        self.lib.CloseDevices()
