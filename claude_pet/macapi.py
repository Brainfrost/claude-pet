"""macOS-Gegenstück zu winapi.py (pyobjc).

Freigaben: Für Fensterlisten und -positionen braucht macOS keine Freigabe (Fenstertitel anderer
Programme gibt es ohne „Bildschirmaufnahme“ nicht – dafür nehmen wir Programmname bzw. Bedienungshilfen).
Für VS Code/Cursor (Terminal-Fläche, Titel) braucht das Pet einmalig „Bedienungshilfen“.
Bildschirmaufnahme wird bewusst NICHT benutzt (macOS fragt dafür monatlich neu nach).

Koordinaten: globale Punkte, Ursprung links oben am Hauptbildschirm – wie Qt auf dem Mac.
"""
import logging
import os
import time
from dataclasses import dataclass

import Quartz
from AppKit import NSApplication, NSWorkspace
from ApplicationServices import (AXIsProcessTrustedWithOptions, AXUIElementCopyAttributeValue,
                                 AXUIElementCreateApplication, AXUIElementSetAttributeValue,
                                 AXValueGetValue, kAXTrustedCheckOptionPrompt, kAXValueCGPointType,
                                 kAXValueCGSizeType)

from .paths import data_dir

log = logging.getLogger(__name__)

OWN_PID = os.getpid()
_OPTS = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
_SKIP_OWNERS = {"Window Server", "Dock", "Control Center", "Kontrollzentrum", "Notification Center",
                "Mitteilungszentrale", "SystemUIServer", "Spotlight", "Wallpaper", "WindowManager",
                "Screenshot", "TextInputMenuAgent"}


@dataclass
class _Win:
    id: int
    pid: int
    owner: str
    name: str
    rect: tuple
    alpha: float


_cache = (0.0, [])


def _windows(max_age=0.15):
    """Sichtbare normale Fenster (Ebene 0), vorderstes zuerst."""
    global _cache
    now = time.monotonic()
    if now - _cache[0] < max_age:
        return _cache[1]
    out = []
    for w in Quartz.CGWindowListCopyWindowInfo(_OPTS, Quartz.kCGNullWindowID) or ():
        if int(w.get(Quartz.kCGWindowLayer, 0)) != 0:
            continue
        b = w.get(Quartz.kCGWindowBounds) or {}
        x, y = float(b.get("X", 0)), float(b.get("Y", 0))
        rect = (int(x), int(y), int(x + float(b.get("Width", 0))), int(y + float(b.get("Height", 0))))
        out.append(_Win(int(w[Quartz.kCGWindowNumber]), int(w.get(Quartz.kCGWindowOwnerPID, 0)),
                        str(w.get(Quartz.kCGWindowOwnerName) or ""), str(w.get(Quartz.kCGWindowName) or ""),
                        rect, float(w.get(Quartz.kCGWindowAlpha, 1.0))))
    _cache = (now, out)
    return out


def _win(wid):
    return next((w for w in _windows() if w.id == wid), None)


# ===================================================================== wie winapi
def set_dpi_awareness():
    """Auf dem Mac nicht nötig (Punkte statt Pixel)."""


_lock_fd = None


def single_instance(name="instance.lock"):
    import fcntl
    global _lock_fd
    os.makedirs(data_dir(), exist_ok=True)
    fd = os.open(data_dir(name), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return False
    _lock_fd = fd
    return True


def cursor_pos():
    p = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    return int(p.x), int(p.y)


def foreground_window():
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return 0
    pid = int(app.processIdentifier())
    return next((w.id for w in _windows() if w.pid == pid), 0)


def enum_windows():
    return [w.id for w in _windows()]


def is_shown(wid):
    return _win(wid) is not None          # OnScreenOnly: nicht minimiert, auf dem aktuellen Space


def window_rect(wid):
    w = _win(wid)
    return w.rect if w else (0, 0, 0, 0)


def window_pid(wid):
    w = _win(wid)
    return w.pid if w else 0


def class_name(wid):
    """Kein Klassenname auf dem Mac – der Programmname erfüllt denselben Zweck."""
    w = _win(wid)
    return w.owner if w else ""


def window_title(wid):
    """Fenstertitel: ohne Bildschirmaufnahme-Freigabe liefert macOS ihn nicht – dann über die
    Bedienungshilfen (AXTitle des passenden Fensters)."""
    w = _win(wid)
    if w is None:
        return ""
    if w.name:
        return w.name
    ax = ax_window_for(wid)
    return str(ax_get(ax, "AXTitle") or "") if ax is not None else ""


def find_terminal_windows():
    return []                             # Windows Terminal gibt es auf dem Mac nicht


def _usable(w):
    return w.pid != OWN_PID and w.owner not in _SKIP_OWNERS and w.alpha > 0.05


def window_rects(term_hwnd=None):
    out = []
    for w in _windows():
        if not _usable(w):
            continue
        l, t, r, b = w.rect
        if r - l < 160 or b - t < 80:
            continue
        out.append((w.id, w.rect, w.id == term_hwnd))
    return out


def top_window_at(x, y):
    for w in _windows():
        if not _usable(w):
            continue
        l, t, r, b = w.rect
        if l <= x < r and t <= y < b:
            return w.id
    return None


_NS_SHARING_NONE = 0
_BEHAVIOR = (1 << 0) | (1 << 4) | (1 << 6) | (1 << 8)   # alle Spaces, fest, nicht im Cmd-`, über Vollbild


def prepare_overlay(win_id, click_through=False):
    """Fenster des Pets auf allen Spaces und über Vollbild-Apps, nicht in Aufnahmen, ggf. klick-durchlässig."""
    try:
        import objc
        view = objc.objc_object(c_void_p=int(win_id))
        win = view.window()
        if win is None:
            return
        win.setSharingType_(_NS_SHARING_NONE)
        win.setCollectionBehavior_(_BEHAVIOR)
        win.setHidesOnDeactivate_(False)
        if click_through:
            win.setIgnoresMouseEvents_(True)
    except Exception:
        log.debug("Overlay-Einstellungen nicht gesetzt", exc_info=True)


def idle_seconds():
    try:
        return float(Quartz.CGEventSourceSecondsSinceLastEventType(
            Quartz.kCGEventSourceStateCombinedSessionState, Quartz.kCGAnyInputEventType))
    except Exception:
        return 0.0


def hide_dock_icon():
    """Kein Dock-Symbol und kein Menü – das Pet lebt im Menüleisten-Symbol."""
    try:
        NSApplication.sharedApplication().setActivationPolicy_(1)    # Accessory
    except Exception:
        log.debug("Dock-Symbol nicht versteckt", exc_info=True)


def accessibility_trusted(prompt=False):
    """Hat das Pet die Freigabe „Bedienungshilfen“? prompt=True öffnet den Systemdialog."""
    try:
        return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: bool(prompt)}))
    except Exception:
        return False


def screen_of_window(wid):
    """Für die Vollbild-Erkennung: (Fensterrechteck, Rechteck des Bildschirms darunter) oder None."""
    w = _win(wid)
    if w is None:
        return None
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QGuiApplication
    l, t, r, b = w.rect
    scr = QGuiApplication.screenAt(QPoint((l + r) // 2, (t + b) // 2))
    if scr is None:
        return None
    g = scr.geometry()
    return w.rect, (g.x(), g.y(), g.x() + g.width(), g.y() + g.height())


# ===================================================================== Bedienungshilfen (AX)
_enabled_pids = set()


def ax_get(el, attr):
    try:
        err, val = AXUIElementCopyAttributeValue(el, attr, None)
    except Exception:
        return None
    return val if err == 0 else None


def ax_app(pid):
    """AX-Element eines Programms; bei Electron (VS Code, Cursor) einmal den Barrierefreiheits-Baum
    einschalten – sonst sieht man darin nichts."""
    app = AXUIElementCreateApplication(pid)
    if pid not in _enabled_pids:
        try:
            AXUIElementSetAttributeValue(app, "AXManualAccessibility", True)
        except Exception:
            pass
        _enabled_pids.add(pid)
    return app


def ax_rect(el):
    pos, size = ax_get(el, "AXPosition"), ax_get(el, "AXSize")
    if pos is None or size is None:
        return None
    try:
        _, p = AXValueGetValue(pos, kAXValueCGPointType, None)
        _, s = AXValueGetValue(size, kAXValueCGSizeType, None)
    except Exception:
        return None
    return (int(round(p.x)), int(round(p.y)), int(round(p.x + s.width)), int(round(p.y + s.height)))


def ax_classes(el):
    v = ax_get(el, "AXDOMClassList")
    try:
        return [str(c) for c in v] if v is not None else []
    except TypeError:
        return []


def ax_children(el):
    v = ax_get(el, "AXChildren")
    return list(v) if v is not None else []


def ax_window_for(wid):
    """Das AX-Fenster zur CGWindowID (gleiche Lage/Größe)."""
    w = _win(wid)
    if w is None:
        return None
    best, best_d = None, None
    for ax in ax_get(ax_app(w.pid), "AXWindows") or ():
        r = ax_rect(ax)
        if r is None:
            continue
        d = sum(abs(a - b) for a, b in zip(r, w.rect))
        if best_d is None or d < best_d:
            best, best_d = ax, d
    return best if best_d is not None and best_d < 40 else None
