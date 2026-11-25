"""Tagesablauf: Tageszeit und wie lange du schon am Stück arbeitest (für die Pausen-Erinnerung)."""
import ctypes
import ctypes.wintypes as wt
import time
from datetime import datetime


# Einmal am Tag: (Schlüssel, Wochentage (0=Mo) oder None, von, bis) – Uhrzeiten als (h, min)
MOMENTS = [
    ("lunch", None, (11, 45), (13, 0)),
    ("evening", (0, 1, 2, 3, 4), (17, 0), (18, 30)),
    ("weekend", (4,), (14, 0), (17, 0)),
]


def due_moments(now, done):
    """Welche Tagesmomente jetzt fällig sind (und heute noch nicht dran waren)."""
    t = (now.hour, now.minute)
    out = []
    for key, days, start, end in MOMENTS:
        if key in done or (days is not None and now.weekday() not in days):
            continue
        if start <= t < end:
            out.append(key)
    return out


def daypart(now=None):
    h = (now or datetime.now()).hour
    if 5 <= h < 10:
        return "morgen"
    if 10 <= h < 18:
        return "tag"
    if 18 <= h < 22:
        return "abend"
    return "nacht"


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


def idle_seconds():
    """Sekunden seit der letzten Maus-/Tastatureingabe (systemweit)."""
    info = _LASTINPUTINFO(ctypes.sizeof(_LASTINPUTINFO), 0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return max(0.0, (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0)


class WorkTracker:
    """Misst die Arbeit am Stück. Eine Pause = mindestens `break_after` Sekunden ohne Eingabe."""

    def __init__(self, idle_fn=idle_seconds, clock=time.time, break_after=5 * 60):
        self.idle_fn, self.clock, self.break_after = idle_fn, clock, break_after
        self.streak_start = None
        self.last_reminder = None
        self.returned_after = None       # Länge der Pause, nach der du gerade zurück bist (einmalig)
        self._break_began = None

    def update(self):
        """Gibt die Minuten zurück, die du gerade am Stück arbeitest (0 während einer Pause)."""
        now, idle = self.clock(), self.idle_fn()
        if idle >= self.break_after:
            if self.streak_start is not None:
                self._break_began = now - idle
            self.streak_start = None
            self.last_reminder = None
            return 0.0
        if self.streak_start is None:
            began = self._break_began
            if began is not None:
                self.returned_after = (now - idle) - began
                self._break_began = None
            self.streak_start = now - idle
        return (now - self.streak_start) / 60.0

    def reminder_due(self, limit_min, repeat_min=30):
        minutes = self.update()
        if minutes < limit_min:
            return False
        now = self.clock()
        if self.last_reminder is not None and now - self.last_reminder < repeat_min * 60:
            return False
        self.last_reminder = now
        return True

    def take_return(self):
        """Pause gerade beendet? -> Länge der Pause in Minuten (nur einmal), sonst None."""
        r, self.returned_after = self.returned_after, None
        return r / 60.0 if r else None
