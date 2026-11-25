"""Liest Windows Terminal per UI Automation: Tabs und den sichtbaren Text samt Pixel-Position.

Läuft in einem eigenen Thread (COM-Apartment) und liefert ~15x pro Sekunde einen Snapshot.
"""
import logging
import time
from dataclasses import dataclass, field

from PyQt6.QtCore import QThread, pyqtSignal

from . import winapi

log = logging.getLogger(__name__)

REFIND_EVERY = 0.5  # Sekunden: Tabs/TermControls neu suchen


@dataclass
class Tab:
    name: str
    rect: tuple  # (l, t, r, b)
    selected: bool

    @property
    def state(self):
        """'idle' (✳), 'working' (Spinner) oder 'unknown' – aus dem Titel, den Claude Code setzt."""
        ch = self.name[:1]
        if ch == "✳":
            return "idle"
        if ch in "◐◓◑◒⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏·✢✶✻✽":
            return "working"
        return "unknown"


@dataclass
class Pane:
    rect: tuple            # (l, t, r, b) des Terminal-Inhalts
    line_h: float
    cell_w: float
    lines: list            # [(y_top, text)] – Text auf volle Breite mit Leerzeichen aufgefüllt
    x0: float              # linke Kante der Textspalte 0


@dataclass
class Snapshot:
    ok: bool
    hwnd: int = 0
    win_rect: tuple = None
    panes: list = field(default_factory=list)
    tabs: list = field(default_factory=list)
    t: float = 0.0

    @property
    def active_tab(self):
        return next((t for t in self.tabs if t.selected), None)


class TerminalWatcher(QThread):
    snapshot = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._stop = False
        self.poll_hz = 10          # vom Controller angepasst (versteckt/draußen: seltener)
        self._wt_cache = None

    def stop(self):
        self._stop = True

    def run(self):
        try:
            self._run()
        except Exception:
            log.exception("TerminalWatcher abgestürzt")

    def _run(self):
        import sys
        sys.coinit_flags = 0  # comtypes initialisiert COM beim Import: MTA für diesen Thread
        import comtypes
        import comtypes.client
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as U
        self.U = U
        self.uia = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)
        self.c_term = self.uia.CreatePropertyCondition(U.UIA_ClassNamePropertyId, "TermControl")
        self.c_tab = self.uia.CreatePropertyCondition(U.UIA_ControlTypePropertyId,
                                                      U.UIA_TabItemControlTypeId)
        self._cache_hwnd = None
        self._cache_t = 0.0
        self._terms = []
        self._tabs = []
        self._tab_elems = []
        self._last_sel = None
        while not self._stop:
            t0 = time.perf_counter()
            try:
                snap = self.poll()
            except Exception as e:  # WT kann mitten im Lesen Tabs schließen o.ä.
                log.debug("poll failed: %r", e)
                self._cache_hwnd = None
                snap = Snapshot(ok=False, t=time.time())
            self.snapshot.emit(snap)
            dt = time.perf_counter() - t0
            self.msleep(max(5, int((1.0 / max(1, self.poll_hz) - dt) * 1000)))

    # ---------------------------------------------------------------- polling
    def _terminal_windows(self):
        now = time.time()
        cached = self._wt_cache
        if cached and now - cached[0] < 1.0 and all(winapi.is_shown(h) for h in cached[1]):
            return cached[1]
        wins = winapi.find_terminal_windows()
        self._wt_cache = (now, wins)
        return wins

    def poll(self):
        wins = self._terminal_windows()
        if not wins:
            return Snapshot(ok=False, t=time.time())
        hwnd = wins[0]
        now = time.time()
        if hwnd != self._cache_hwnd or now - self._cache_t > REFIND_EVERY:
            self._refind(hwnd, now)
        # Tabs bei JEDER Abfrage lesen: Text und aktiver Tab müssen zusammenpassen, sonst sieht
        # das Pet nach einem Tab-Wechsel kurz den neuen Text, hält aber den alten Tab für aktiv.
        tabs = self._read_tabs()
        sel = next((i for i, t in enumerate(tabs or []) if t.selected), None)
        if tabs is not None and sel != self._last_sel and self._cache_t != now:
            self._refind(hwnd, now)              # Tab gewechselt: Textfeld des neuen Tabs holen
        self._last_sel = sel
        panes = self._read_panes()
        if not panes or tabs is None:
            # direkt nach einem Tab-Wechsel zeigt das gemerkte Textfeld noch auf den alten Tab
            self._refind(hwnd, now)
            tabs = self._read_tabs()
            panes = self._read_panes()
        return Snapshot(ok=bool(panes), hwnd=hwnd, win_rect=winapi.window_rect(hwnd),
                        panes=panes, tabs=tabs or [], t=now)

    def _refind(self, hwnd, now):
        U = self.U
        win = self.uia.ElementFromHandle(hwnd)
        terms = win.FindAll(U.TreeScope_Descendants, self.c_term)
        self._terms = [terms.GetElement(i) for i in range(terms.Length)]
        tabs = win.FindAll(U.TreeScope_Descendants, self.c_tab)
        self._tab_elems = []
        for i in range(tabs.Length):
            e = tabs.GetElement(i)
            try:
                pat = e.GetCurrentPattern(U.UIA_SelectionItemPatternId) \
                    .QueryInterface(U.IUIAutomationSelectionItemPattern)
            except Exception:
                pat = None
            self._tab_elems.append((e, pat))
        self._cache_hwnd, self._cache_t = hwnd, now

    def _read_tabs(self):
        out = []
        try:
            for e, pat in self._tab_elems:
                sel = bool(pat.CurrentIsSelected) if pat is not None else False
                r = e.CurrentBoundingRectangle
                out.append(Tab(e.CurrentName, (r.left, r.top, r.right, r.bottom), sel))
        except Exception:
            return None          # Tab geschlossen/verschoben: neu suchen
        return out

    def _read_panes(self):
        panes = []
        for term in self._terms:
            try:
                p = self._read_pane(term)
            except Exception:
                p = None
            if p:
                panes.append(p)
        return panes

    def _read_pane(self, term):
        U = self.U
        r = term.CurrentBoundingRectangle
        rect = (r.left, r.top, r.right, r.bottom)
        if rect[2] - rect[0] <= 0 or rect[3] - rect[1] <= 0:
            return None  # Element eines nicht sichtbaren Tabs
        tp = term.GetCurrentPattern(U.UIA_TextPatternId).QueryInterface(U.IUIAutomationTextPattern)
        ranges = tp.GetVisibleRanges()
        lines, line_h, cell_w, x0 = [], 0.0, 0.0, rect[0]
        for i in range(ranges.Length):
            rng = ranges.GetElement(i)
            text = rng.GetText(-1)
            rects = rng.GetBoundingRectangles() or ()
            rows = text.split("\r\n") if "\r\n" in text else text.split("\n")
            for k, row in enumerate(rows):
                if 4 * k + 3 >= len(rects):
                    break
                x, y, w, h = rects[4 * k: 4 * k + 4]
                if not line_h and h > 0:
                    line_h = h
                if not cell_w and row and w > 0:
                    cell_w = w / len(row)
                    x0 = x
                lines.append((y, row))
        if not lines or not line_h or not cell_w:
            return None
        return Pane(rect=rect, line_h=line_h, cell_w=cell_w, lines=lines, x0=x0)
