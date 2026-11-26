"""VS Code und Cursor als Terminal-Quelle.

- Wo die Terminals liegen und wie ihre Sitzung heißt (✳ = Claude fertig), liest UI Automation aus dem
  Accessibility-Baum von Electron: `xterm-screen` = Textfläche, `xterm-helper-textarea` = unsichtbares
  Eingabefeld am Cursor, dessen Name den Terminal-Titel enthält.
- Den Text liefert die Begleit-Erweiterung (streams.py): xterm.js zeichnet auf ein Canvas, UIA sieht
  dort keinen Text.
"""
import logging
import re
import time

from . import osapi
from .terminal import Pane, Snapshot, Tab

log = logging.getLogger(__name__)

ELECTRON_CLASS = "Chrome_WidgetWin_1"
APPS = ("Visual Studio Code", "Visual Studio Code - Insiders", "Cursor")
REFIND_EVERY = 0.6
QUIET_BEFORE_ALIGN = 0.35        # s ohne neue Daten, bevor am Cursor ausgerichtet wird


# ===================================================================== reine Logik (getestet)
def is_editor_title(title):
    return any(title == a or title.endswith(" - " + a) for a in APPS)


def workspace_in_title(workspace, title):
    """Gehört ein Fenster (Titel 'datei - ordner - Visual Studio Code') zu diesem Arbeitsbereich?"""
    if not workspace:
        return False
    parts = [p.strip() for p in title.split(" - ")]
    return workspace in parts


_TA_PREFIX = re.compile(r"^[^,]{0,40}?\d+,\s*")
_TA_SUFFIXES = (" Run the command", " Führen Sie den Befehl", " Use ", " Ejecute el comando")


def textarea_title(name, known=()):
    """Terminal-Titel aus dem Namen des Eingabefelds ('Terminal 1, ✳ Titel Run the command: …')."""
    for t in sorted((k for k in known if k), key=len, reverse=True):
        if t in name:
            return t
    rest = _TA_PREFIX.sub("", name, count=1)
    for s in _TA_SUFFIXES:
        i = rest.find(s)
        if i > 0:
            rest = rest[:i]
    return rest.strip()


def match_sessions(screens, sessions, win_title, single_window):
    """Ordnet jeder sichtbaren Textfläche eine Sitzung zu (oder None).

    screens: [{"ta_name": str}], sessions: [Session]. Vorrang: Titel des Terminals steht im Namen des
    Eingabefelds; sonst – bei genau einer Fläche – das aktive Terminal des Fensters."""
    cands = [s for s in sessions if workspace_in_title(s.workspace, win_title)]
    if not cands and single_window:
        cands = list(sessions)
    out, used = [], set()
    for sc in screens:
        name = sc.get("ta_name") or ""
        best = None
        for s in cands:
            t = s.best_title
            if t and t in name and id(s) not in used and (best is None or len(t) > len(best.best_title)):
                best = s
        out.append(best)
        if best is not None:
            used.add(id(best))
    if len(screens) == 1 and out[0] is None:
        free = [s for s in cands if id(s) not in used]
        active = [s for s in free if s.active]
        pick = active or (free if len(free) == 1 else [])
        if pick:
            out[0] = max(pick, key=lambda s: s.started)
    return out


def calibrate(sess, rect):
    """Zellgröße aus der Fläche und der Terminalgröße beim Start von claude."""
    if sess.cell is not None or not sess.start_dims:
        return
    cols, rows = sess.start_dims
    w, h = rect[2] - rect[0], rect[3] - rect[1]
    cw, ch = w / cols, h / rows
    if 3 <= cw <= 60 and 6 <= ch <= 90:
        sess.cell = (cw, ch)


def align(sess, rect, ta_rect, now):
    """Emulator am echten Cursor ausrichten: Der Strom beginnt mitten auf dem Bildschirm (dort, wo der
    Prompt stand) – der Emulator kennt diese Zeile nicht. Das Eingabefeld von xterm sitzt am Cursor.

    Ausgerichtet wird nur bei ruhigem Strom und nur, wenn eine neue Ausgabe begann oder sich das
    Eingabefeld bewegt hat (sonst könnte ein veraltetes Feld den Emulator verschieben)."""
    if ta_rect is None or sess.cell is None or now - sess.emu.last_feed < QUIET_BEFORE_ALIGN:
        return False
    ch = sess.cell[1]
    ta_row = int(round((ta_rect[1] - rect[1]) / ch))
    if not 0 <= ta_row < sess.emu.rows:
        return False
    moved = sess.misalign.get("ta_row") != ta_row
    sess.misalign["ta_row"] = ta_row
    if not (sess.align_pending or moved):
        return False
    diff = ta_row - sess.emu.cursor_row
    sess.align_pending = False
    if diff:
        sess.emu.shift(diff)
        log.debug("VS-Code-Emulator um %+d Zeilen ausgerichtet", diff)
        return True
    return False


def build_pane(rect, sess, ta_rect, now):
    """Pane für eine Textfläche: mit Text, wenn eine kalibrierte Sitzung dazugehört, sonst leer."""
    l, t, r, b = rect
    if sess is not None:
        calibrate(sess, rect)
    if sess is None or sess.cell is None:
        lh = (ta_rect[3] - ta_rect[1]) if ta_rect and ta_rect[3] > ta_rect[1] else 20
        return Pane(rect=rect, line_h=float(lh), cell_w=lh * 0.45, lines=[], x0=l)
    cw, ch = sess.cell
    cols, rows = max(2, int((r - l) / cw + 0.25)), max(2, int((b - t) / ch + 0.25))
    sess.emu.resize(cols, rows)
    align(sess, rect, ta_rect, now)
    lines = [(t + i * ch, text) for i, text in enumerate(sess.emu.lines())]
    return Pane(rect=rect, line_h=ch, cell_w=cw, lines=lines, x0=l)


def pair_textareas(screens, textareas):
    """Eingabefeld zur Textfläche: es liegt innerhalb (am Cursor); sonst das nächstgelegene."""
    out = []
    for (l, t, r, b) in screens:
        inside = [ta for ta in textareas if l - 2 <= ta[0][0] <= r and t - 2 <= ta[0][1] <= b]
        if not inside and textareas:
            inside = [min(textareas, key=lambda ta: abs(ta[0][0] - l) + abs(ta[0][1] - t))]
        out.append(inside[0] if inside else (None, ""))
    return out


# ===================================================================== Scanner (UIA / AX)
class Scanner:
    """Findet in einem Editor-Fenster die Terminal-Flächen, Eingabefelder und den Terminal-Reiter.
    Windows: UIAScanner (UI Automation), Mac: macax.AXScanner (Bedienungshilfen)."""
    REFIND_EVERY = REFIND_EVERY

    def __init__(self):
        self._cache = {}          # hwnd -> (t, screens, textareas, tab)
        self._win_cache = (0.0, [])

    # -- von Unterklassen
    def _list_windows(self):
        raise NotImplementedError

    def _refind_elements(self, hwnd):
        """-> (Flächen-Elemente, Eingabefeld-Elemente, Reiter-Element oder None)"""
        raise NotImplementedError

    def _rect(self, e):
        raise NotImplementedError

    def _name(self, e):
        raise NotImplementedError

    # -- gemeinsam
    def windows(self):
        now = time.time()
        t, wins = self._win_cache
        if now - t < 1.0 and all(osapi.is_shown(h) for h in wins):
            return wins
        wins = self._list_windows()
        self._win_cache = (now, wins)
        return wins

    def clear(self):
        self._cache.clear()

    def _entry(self, hwnd, force=False):
        now = time.time()
        entry = self._cache.get(hwnd)
        if force or entry is None or now - entry[0] > self.REFIND_EVERY:
            entry = (now, *self._refind_elements(hwnd))
            self._cache[hwnd] = entry
        return entry

    @staticmethod
    def _visible(rect):
        return rect is not None and rect[2] - rect[0] > 40 and rect[3] - rect[1] > 20

    def has_terminal(self, hwnd):
        """Hat das Fenster ein sichtbares Terminal? (für die Wahl der Quelle)"""
        try:
            return any(self._visible(self._rect(e)) for e in self._entry(hwnd)[1])
        except Exception:
            return False

    def read(self, hwnd):
        """-> (Flächen [rect], Eingabefelder [(rect, name)], Reiter-Rechteck oder None)"""
        for force in (False, True):
            _, screen_els, ta_els, tab_el = self._entry(hwnd, force)
            try:
                screens = [r for r in (self._rect(e) for e in screen_els) if self._visible(r)]
                tas = [(r, self._name(e)) for e in ta_els if (r := self._rect(e)) is not None]
                tab_rect = self._rect(tab_el) if tab_el is not None else None
                return screens, tas, tab_rect
            except Exception:
                continue                    # Elemente veraltet (Terminal geschlossen o.ä.): neu suchen
        return [], [], None


class UIAScanner(Scanner):
    """Windows: VS Code/Cursor per UI Automation."""

    def __init__(self, uia, U):
        super().__init__()
        self.uia, self.U = uia, U
        self.c_screen = uia.CreatePropertyCondition(U.UIA_ClassNamePropertyId, "xterm-screen")
        self.c_ta = uia.CreatePropertyCondition(U.UIA_ClassNamePropertyId, "xterm-helper-textarea")
        self.c_tab = uia.CreatePropertyCondition(U.UIA_ClassNamePropertyId, "action-label single-terminal-tab")

    def _list_windows(self):
        return [h for h in osapi.enum_windows()
                if osapi.class_name(h) == ELECTRON_CLASS and osapi.is_shown(h)
                and is_editor_title(osapi.window_title(h))]

    def _refind_elements(self, hwnd):
        U = self.U
        win = self.uia.ElementFromHandle(hwnd)
        screens = win.FindAll(U.TreeScope_Descendants, self.c_screen)
        tas = win.FindAll(U.TreeScope_Descendants, self.c_ta)
        tab = win.FindFirst(U.TreeScope_Descendants, self.c_tab)
        return ([screens.GetElement(i) for i in range(screens.Length)],
                [tas.GetElement(i) for i in range(tas.Length)], tab)

    def _rect(self, e):
        r = e.CurrentBoundingRectangle
        return (r.left, r.top, r.right, r.bottom)

    def _name(self, e):
        return e.CurrentName or ""


# ===================================================================== Quelle
class VSCodeSource:
    """VS Code/Cursor als Terminal-Quelle; läuft im Watcher-Thread."""

    def __init__(self, scanner, hub):
        self.scanner, self.hub = scanner, hub
        self.last_matched = set()  # Sitzungen, die gerade sichtbar sind (Schlüssel)
        self._titles = {}          # hwnd -> (Zeit, Fenstertitel) – auf dem Mac ist der Titel teuer

    def windows(self):
        return self.scanner.windows()

    def has_terminal(self, hwnd):
        return self.scanner.has_terminal(hwnd)

    def clear(self):
        self.scanner.clear()

    def _title(self, hwnd, now):
        t, title = self._titles.get(hwnd, (0.0, ""))
        if now - t > 2.0:
            title = osapi.window_title(hwnd)
            self._titles[hwnd] = (now, title)
        return title

    def poll(self, hwnd, single_window=True):
        now = time.time()
        screens, tas, tab_rect = self.scanner.read(hwnd)
        screens.sort(key=lambda r: (r[1], r[0]))
        paired = pair_textareas(screens, tas)
        title = self._title(hwnd, now)
        panes, tabs = [], []
        with self.hub.lock:
            sessions = self.hub.snapshot_sessions()
            infos = [{"ta_name": name} for _, name in paired]
            matched = match_sessions(infos, sessions, title, single_window)
            self.last_matched = {m.key for m in matched if m is not None}
            for rect, (ta_rect, ta_name), sess in zip(screens, paired, matched):
                panes.append(build_pane(rect, sess, ta_rect, now))
                known = [sess.best_title] if sess else []
                name = textarea_title(ta_name, known) or (sess.best_title if sess else "") or "Terminal"
                tr = tab_rect if tab_rect and tab_rect[2] > tab_rect[0] else (rect[0], rect[1] - 34, rect[0] + 220, rect[1] - 6)
                tabs.append(Tab(name, tr, True))
        return Snapshot(ok=bool(panes), hwnd=hwnd, win_rect=osapi.window_rect(hwnd),
                        panes=panes, tabs=tabs, t=now, host="vscode")
