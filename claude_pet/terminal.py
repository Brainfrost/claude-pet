"""Liest das Terminal, in dem das Pet lebt: Tabs und den sichtbaren Text samt Pixel-Position.

Quellen: Windows Terminal (UI Automation, hier) sowie VS Code/Cursor (vscode.py: Geometrie per UIA,
Text über die Begleit-Erweiterung). Es gilt das zuletzt aktive Terminal-Fenster.
Läuft in einem eigenen Thread (COM-Apartment) und liefert ~10x pro Sekunde einen Snapshot.
"""
import logging
import time
from dataclasses import dataclass, field

from PyQt6.QtCore import QThread, pyqtSignal

from . import osapi

log = logging.getLogger(__name__)

REFIND_EVERY = 0.5  # Sekunden: Tabs/TermControls neu suchen
SWITCH_DELAY = 0.8  # Sekunden im Vordergrund, bevor das Pet in ein anderes Terminal-Programm umzieht


@dataclass
class Tab:
    name: str
    rect: tuple  # (l, t, r, b); None bei Sessions anderer Programme (Snapshot.others)
    selected: bool
    host: str = ""   # nur bei Snapshot.others: "wt" oder "vscode"

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
    host: str = "wt"           # "wt" = Windows Terminal, "vscode" = VS Code/Cursor
    others: list = field(default_factory=list)   # Sessions anderer Terminal-Programme (nur Name/Zustand)

    @property
    def active_tab(self):
        return next((t for t in self.tabs if t.selected), None)


class TerminalWatcher(QThread):
    snapshot = pyqtSignal(object)

    def __init__(self, hub=None):
        super().__init__()
        self._stop = False
        self.poll_hz = 10          # vom Controller angepasst (versteckt/draußen: seltener)
        self._wt_cache = None
        self.hub = hub             # streams.StreamHub: Text aus VS Code/Cursor
        self.vscode = None
        self._host = None          # ("wt", None) oder ("vscode", hwnd)
        self._pending = (None, 0.0)
        self._poll_ms = []         # Dauer der letzten Abfragen (für die Debug-Zeile)
        self._bg_wt = (0.0, [])    # (Zeit, Tabs) des Windows Terminals, wenn das Pet woanders wohnt

    def stop(self):
        self._stop = True

    def timing(self):
        """'Ø 12 / max 40 ms (vscode)' – Dauer der letzten Terminal-Abfragen."""
        ms = list(self._poll_ms)
        if not ms:
            return "-"
        host = self._host[0] if self._host else "-"
        return f"Ø {sum(ms) / len(ms):.0f} / max {max(ms):.0f} ms ({host})"

    def run(self):
        try:
            self._run()
        except Exception:
            log.exception("TerminalWatcher abgestürzt")

    def _run(self):
        import sys
        self._cache_hwnd = None
        self._cache_t = 0.0
        self._terms = []
        self._tabs = []
        self._tab_elems = []
        self._last_sel = None
        if sys.platform == "win32":
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
            if self.hub is not None:
                from .vscode import UIAScanner, VSCodeSource
                self.vscode = VSCodeSource(UIAScanner(self.uia, U), self.hub)
        elif self.hub is not None:
            from .macax import AXScanner
            from .vscode import VSCodeSource
            self.vscode = VSCodeSource(AXScanner(), self.hub)
        while not self._stop:
            t0 = time.perf_counter()
            try:
                snap = self.poll()
            except Exception as e:  # WT kann mitten im Lesen Tabs schließen o.ä.
                log.debug("poll failed: %r", e)
                self._cache_hwnd = None
                if self.vscode is not None:
                    self.vscode.clear()
                snap = Snapshot(ok=False, t=time.time())
            self.snapshot.emit(snap)
            dt = time.perf_counter() - t0
            self._poll_ms = (self._poll_ms + [dt * 1000])[-40:]
            self.msleep(max(5, int((1.0 / max(1, self.poll_hz) - dt) * 1000)))

    # ---------------------------------------------------------------- polling
    def _terminal_windows(self):
        now = time.time()
        cached = self._wt_cache
        if cached and now - cached[0] < 1.0 and all(osapi.is_shown(h) for h in cached[1]):
            return cached[1]
        wins = osapi.find_terminal_windows()
        self._wt_cache = (now, wins)
        return wins

    def _choose_host(self, wt_wins):
        """Welches Terminal-Programm gilt? Das zuletzt aktive; Wechsel erst nach SWITCH_DELAY."""
        vsc = self.vscode.windows() if self.vscode else []
        now = time.time()
        fg = osapi.foreground_window()
        want = None
        if fg in wt_wins:
            want = ("wt", None)
        elif fg in vsc and self.vscode.has_terminal(fg):
            want = ("vscode", fg)
        cur = self._host
        if cur and cur[0] == "wt" and not wt_wins:
            cur = None
        if cur and cur[0] == "vscode" and (cur[1] not in vsc or not self.vscode.has_terminal(cur[1])):
            cur = None
        if want and want != cur:
            if cur is None:
                cur = want
            elif self._pending[0] != want:
                self._pending = (want, now)
            elif now - self._pending[1] >= SWITCH_DELAY:
                log.info("Pet zieht um: %s -> %s", cur[0], want[0])
                cur, self._pending = want, (None, 0.0)
        else:
            self._pending = (None, 0.0)
        if cur is None:
            if wt_wins:
                cur = ("wt", None)
            else:
                cur = next((("vscode", h) for h in vsc if self.vscode.has_terminal(h)), None)
        self._host = cur
        return cur, len(vsc)

    def poll(self):
        wins = self._terminal_windows()
        host, n_vsc = self._choose_host(wins)
        if host is None:
            snap = Snapshot(ok=False, t=time.time())
        elif host[0] == "vscode":
            snap = self.vscode.poll(host[1], single_window=n_vsc == 1)
        else:
            snap = self._poll_wt(wins)
        snap.others = self._other_sessions(host, wins)
        return snap

    def _other_sessions(self, host, wins):
        """Sessions, die das Pet gerade nicht sieht – damit der Bote auch dort Bescheid sagt.
        VS Code/Cursor: Titel aus dem Strom (Claude Code setzt ✳/Spinner); Windows Terminal: Tab-Titel."""
        out = []
        if self.hub is not None:
            shown = self.vscode.last_matched if (host and host[0] == "vscode") else set()
            with self.hub.lock:
                for s in self.hub.snapshot_sessions():
                    if s.key not in shown and s.best_title:
                        out.append(Tab(s.best_title, None, False, "vscode"))
        if host and host[0] == "vscode" and wins:
            now = time.time()
            if now - self._bg_wt[0] > 1.0:
                tabs = []
                try:
                    if wins[0] != self._cache_hwnd or now - self._cache_t > REFIND_EVERY:
                        self._refind(wins[0], now)
                    tabs = [Tab(t.name, None, False, "wt") for t in (self._read_tabs() or [])]
                except Exception:
                    self._cache_hwnd = None
                self._bg_wt = (now, tabs)
            out += self._bg_wt[1]
        return out

    def _poll_wt(self, wins):
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
        return Snapshot(ok=bool(panes), hwnd=hwnd, win_rect=osapi.window_rect(hwnd),
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
