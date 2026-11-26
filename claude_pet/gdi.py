"""Bildschirmaufnahme per GDI (nur Windows) für die Bildanalyse in vision.py."""
import ctypes
import ctypes.wintypes as wt

import numpy as np

# --------------------------------------------------------------------- Bildschirmaufnahme per GDI
# (thread-sicher – anders als QScreen.grabWindow, das nur im GUI-Thread laufen darf)
_user32, _gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
_HANDLE = ctypes.c_void_p
_user32.GetDC.restype = _HANDLE
_user32.GetDC.argtypes = [_HANDLE]
_user32.ReleaseDC.argtypes = [_HANDLE, _HANDLE]
_user32.MonitorFromPoint.restype = _HANDLE
_user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
_gdi32.CreateCompatibleDC.restype = _HANDLE
_gdi32.CreateCompatibleDC.argtypes = [_HANDLE]
_gdi32.CreateCompatibleBitmap.restype = _HANDLE
_gdi32.CreateCompatibleBitmap.argtypes = [_HANDLE, ctypes.c_int, ctypes.c_int]
_gdi32.SelectObject.restype = _HANDLE
_gdi32.SelectObject.argtypes = [_HANDLE, _HANDLE]
_gdi32.BitBlt.argtypes = [_HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                          _HANDLE, ctypes.c_int, ctypes.c_int, wt.DWORD]
_gdi32.GetDIBits.argtypes = [_HANDLE, _HANDLE, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
_gdi32.DeleteObject.argtypes = [_HANDLE]
_gdi32.DeleteDC.argtypes = [_HANDLE]
SRCCOPY = 0x00CC0020


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


def monitor_rect_at(x, y):
    mon = _user32.MonitorFromPoint(wt.POINT(int(x), int(y)), 2)    # MONITOR_DEFAULTTONEAREST
    info = _MONITORINFO(ctypes.sizeof(_MONITORINFO))
    if not mon or not _user32.GetMonitorInfoW(mon, ctypes.byref(info)):
        return None
    m = info.rcMonitor
    return m.left, m.top, m.right, m.bottom


def grab(x, y, w, h):
    """Bildschirmausschnitt (physische Pixel, auf einen Monitor beschnitten) als Graustufen-Array
    (int16) samt linker oberer Ecke, oder None."""
    mon = monitor_rect_at(x + w / 2, y + h / 2)
    if mon is None:
        return None
    x0, y0 = int(max(x, mon[0])), int(max(y, mon[1]))
    x1, y1 = int(min(x + w, mon[2])), int(min(y + h, mon[3]))
    w, h = x1 - x0, y1 - y0
    if w < 4 or h < 4:
        return None
    screen = _user32.GetDC(None)
    mem = _gdi32.CreateCompatibleDC(screen)
    bmp = _gdi32.CreateCompatibleBitmap(screen, w, h)
    old = _gdi32.SelectObject(mem, bmp)
    try:
        _gdi32.BitBlt(mem, 0, 0, w, h, screen, x0, y0, SRCCOPY)
        bi = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = (ctypes.c_ubyte * (w * h * 4))()
        _gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    finally:
        _gdi32.SelectObject(mem, old)
        _gdi32.DeleteObject(bmp)
        _gdi32.DeleteDC(mem)
        _user32.ReleaseDC(None, screen)
    px = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 4).astype(np.int16)
    gray = (px[:, :, 2] * 77 + px[:, :, 1] * 150 + px[:, :, 0] * 29) >> 8
    return gray, x0, y0
