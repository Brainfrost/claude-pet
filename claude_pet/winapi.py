"""Dünne ctypes-Schicht über die Win32-Funktionen, die das Pet braucht.

Alle Koordinaten sind physische Pixel: der Prozess ist per-monitor-DPI-aware
(siehe set_dpi_awareness) und Qt läuft ohne eigene Skalierung.
"""
import ctypes
import ctypes.wintypes as wt
import os

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WT_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsIconic.argtypes = [wt.HWND]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetForegroundWindow.restype = wt.HWND
dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]

OWN_PID = os.getpid()


def set_dpi_awareness():
    """Per-Monitor-V2, damit UIA, Win32 und Qt dieselben physischen Pixel sprechen."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass


def single_instance(name="Local\\claude-pet-single-instance"):
    """True, wenn wir die einzige laufende Instanz sind. Handle bleibt bis Prozessende offen."""
    kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def add_exstyle(hwnd, flags):
    cur = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, cur | flags)


def cursor_pos():
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_title(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def window_pid(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def is_cloaked(hwnd):
    val = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(val), ctypes.sizeof(val))
    return val.value != 0


def window_rect(hwnd):
    """Sichtbare Fenstergrenzen (ohne unsichtbaren Resize-Rand) als (l, t, r, b)."""
    r = wt.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                    ctypes.byref(r), ctypes.sizeof(r)) != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def enum_windows():
    """Alle Top-Level-Fenster, oberstes zuerst (Z-Reihenfolge)."""
    out = []

    def cb(hwnd, _):
        out.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def is_shown(hwnd):
    return bool(user32.IsWindowVisible(hwnd)) and not user32.IsIconic(hwnd) and not is_cloaked(hwnd)


def find_terminal_windows():
    """Sichtbare Windows-Terminal-Fenster, oberstes zuerst."""
    return [h for h in enum_windows() if class_name(h) == WT_CLASS and is_shown(h)]


def any_terminal_window():
    """Irgendein WT-Fenster, auch minimiert (für 'Terminal ist weg' vs. 'nur verdeckt')."""
    return [h for h in enum_windows() if class_name(h) == WT_CLASS and user32.IsWindowVisible(h)]


def _is_overlay_like(hwnd):
    ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    if ex & WS_EX_TRANSPARENT:
        return True
    if not window_title(hwnd) and ex & (WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE):
        return True
    return False


_SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                 "Windows.UI.Core.CoreWindow", "NotifyIconOverflowWindow"}


def window_rects():
    """Sichtbare 'echte' Top-Level-Fenster als [(hwnd, (l, t, r, b), ist_terminal)], oberstes zuerst."""
    out = []
    for h in enum_windows():
        if not is_shown(h) or window_pid(h) == OWN_PID or _is_overlay_like(h):
            continue
        cls = class_name(h)
        if cls in _SKIP_CLASSES:
            continue
        l, t, r, b = window_rect(h)
        if r - l < 160 or b - t < 80:
            continue
        out.append((h, (l, t, r, b), cls == WT_CLASS))
    return out


def top_window_at(x, y):
    """Das oberste 'echte' Fenster an (x, y), ohne unsere eigenen und Overlay-artige."""
    for h in enum_windows():
        if not is_shown(h) or window_pid(h) == OWN_PID or _is_overlay_like(h):
            continue
        l, t, r, b = window_rect(h)
        if r - l <= 0 or b - t <= 0:
            continue
        if l <= x < r and t <= y < b:
            return h
    return None
