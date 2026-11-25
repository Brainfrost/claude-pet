"""Erkennt 'Ebenen' in beliebigen Fenstern per Bildanalyse: waagrechte Kanten (Textzeilen, Rahmen,
Buttons, Bildränder) werden zu Plattformen.

Es wird nur ein Ausschnitt rund ums Pet aufgenommen. Die Bilder bleiben im Speicher, werden nie
gespeichert und nie verschickt.
"""
import ctypes
import ctypes.wintypes as wt
import logging
import threading

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)

EDGE = 26          # Helligkeitssprung zwischen zwei Pixelzeilen, ab dem eine Kante zählt
MIN_LEN = 36       # Mindestlänge einer Plattform in Pixeln
GAP_X = 5          # Lücken bis zu so vielen Pixeln werden überbrückt (Buchstaben einer Zeile)
MERGE_Y = 4        # Kanten, die so nah übereinander liegen, gelten als eine
MAX_PLATFORMS = 160
TEXTURE = 0.45     # Bänder mit mehr Kantenanteil sind Fotos/Rauschen -> ignorieren

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


def detect(gray, exclude=()):
    """Waagrechte Kanten -> [(y, x0, x1)] in Bildkoordinaten. exclude: Rechtecke (l, t, r, b),
    die ignoriert werden (das Pet selbst, seine Sprechblase)."""
    h, w = gray.shape
    d = np.abs(gray[1:, :] - gray[:-1, :]) > EDGE          # Kante zwischen Zeile y und y+1
    for l, t, r, b in exclude:
        d[max(0, t - 2):max(0, b + 2), max(0, l - 2):max(0, r + 2)] = False
    # Buchstaben einer Zeile zusammenziehen: waagrecht dilatieren, senkrecht 1 Pixel
    m = d.copy()
    for k in range(1, GAP_X + 1):
        m[:, k:] |= d[:, :-k]
    m[1:, :] |= m[:-1, :]
    # Textur (Fotos, Verläufe mit Rauschen): Anteil der Kantenpixel in der ganzen Zeile ...
    band = d.mean(axis=1)
    # ... und Präfixsummen, um ihn für jede einzelne Kante in konstanter Zeit zu prüfen
    row_cs = np.zeros((h - 1, w + 1), dtype=np.int32)       # Kanten je Zeile, aufsummiert
    np.cumsum(d, axis=1, out=row_cs[:, 1:])
    box_cs = np.zeros((h, w + 1), dtype=np.int32)
    np.cumsum(row_cs, axis=0, out=box_cs[1:, :])
    # Alle zusammenhängenden Kanten-Stücke aller Zeilen auf einmal (vektorisiert – die Schleife
    # über 900 Bildzeilen in Python hat sonst die Animation im anderen Thread ausgebremst)
    padded = np.zeros((h - 1, w + 2), dtype=np.int8)
    padded[:, 1:-1] = m
    edges = np.diff(padded, axis=1)
    ys, starts = np.nonzero(edges == 1)
    _, ends = np.nonzero(edges == -1)                     # gleiche Reihenfolge: je Zeile abwechselnd
    keep = ((ends - starts) >= MIN_LEN) & (band[ys] <= TEXTURE)
    ys, starts, ends = ys[keep], starts[keep], ends[keep]
    # zusätzlich lokal: Fotos, die nur einen Teil der Zeile einnehmen
    y0, y1 = np.maximum(0, ys - 3), np.minimum(h - 1, ys + 4)
    box = box_cs[y1, ends] - box_cs[y0, ends] - box_cs[y1, starts] + box_cs[y0, starts]
    keep = box / ((y1 - y0) * (ends - starts)) <= TEXTURE
    ys, starts, ends = ys[keep], starts[keep], ends[keep]
    tops = _snap_up(row_cs, ys, starts, ends) + 1
    out = [(int(y), int(s), int(e - GAP_X)) for y, s, e in zip(tops, starts, ends)]
    return _merge(out)


def _snap_up(row_cs, ys, a, b, max_up=14, density=0.03):
    """Bei Text liegt die längste Kante oft mitten in den Buchstaben: so weit nach oben gehen,
    wie in derselben Spaltenbreite noch 'Tinte' (Kanten) ist – bis zur Oberkante der Schrift.
    Für alle Kanten gleichzeitig (höchstens max_up Schritte statt tausender Einzelrechnungen)."""
    yy = ys.copy()
    active = np.ones(len(ys), dtype=bool)
    width = (b - a).astype(np.float64)
    for _ in range(max_up):
        rows = yy - 1
        ok = active & (rows >= 0)
        r = np.where(ok, rows, 0)
        dens = (row_cs[r, b] - row_cs[r, a]) / width
        step = ok & (dens > density)
        yy[step] -= 1
        active = step
        if not active.any():
            break
    return yy


def _merge(runs):
    """Kanten, die fast auf gleicher Höhe liegen und sich überlappen, zusammenfassen (obere gewinnt)."""
    runs.sort()
    merged = []
    for y, a, b in runs:
        for i, (my, ma, mb) in enumerate(merged):
            if y - my <= MERGE_Y and a < mb and b > ma:
                merged[i] = (my, min(a, ma), max(b, mb))
                break
        else:
            merged.append((y, a, b))
    merged.sort(key=lambda r: r[2] - r[1], reverse=True)
    return merged[:MAX_PLATFORMS]


def platforms_around(cx, cy, w, h, exclude_global=()):
    """Plattformen [(y, x0, x1)] in globalen Koordinaten für den Ausschnitt um (cx, cy)."""
    return platforms_in_rect(int(cx - w / 2), int(cy - h * 0.6), int(w), int(h), exclude_global)


def platforms_in_rect(x, y, w, h, exclude_global=()):
    """Plattformen [(y, x0, x1)] in globalen Koordinaten für ein Bildschirm-Rechteck."""
    res = grab(int(x), int(y), int(w), int(h))
    if res is None:
        return []
    gray, ox, oy = res
    excl = [(l - ox, t - oy, r - ox, b - oy) for l, t, r, b in exclude_global]
    return [(y + oy, a + ox, b + ox) for y, a, b in detect(gray, excl)]


# --------------------------------------------------------------------- Hintergrund-Thread
class VisionWorker(QThread):
    """Führt Bildanalysen im Hintergrund aus, damit die Animation nie darauf warten muss.

    request(tag, rects, exclude, info): pro tag zählt nur der neueste Auftrag. Von mehreren
    Rechtecken wird das erste mit Ergebnis gemeldet: done(tag, info, rect, runs)."""
    done = pyqtSignal(str, object, object, object)
    PRIORITY = ("trip", "near", "scan")

    def __init__(self):
        super().__init__()
        self._jobs = {}
        self._running = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False

    def request(self, tag, rects, exclude=(), info=None):
        with self._lock:
            self._jobs[tag] = (list(rects), list(exclude), info)
        self._wake.set()

    def busy(self, tag):
        with self._lock:
            return tag in self._jobs or self._running == tag

    def stop(self):
        self._stop = True
        self._wake.set()

    def run(self):
        while not self._stop:
            self._wake.wait(0.5)
            self._wake.clear()
            while not self._stop:
                with self._lock:
                    tag = next((t for t in self.PRIORITY if t in self._jobs), None)
                    if tag is None:
                        break
                    rects, exclude, info = self._jobs.pop(tag)
                    self._running = tag
                try:
                    found = None
                    for rect in rects:
                        runs = platforms_in_rect(*rect, exclude)
                        found = (rect, runs)
                        if runs:
                            break
                    if found is not None:
                        self.done.emit(tag, info, found[0], found[1])
                except Exception:
                    log.exception("Bildanalyse fehlgeschlagen")
                finally:
                    with self._lock:
                        self._running = None
