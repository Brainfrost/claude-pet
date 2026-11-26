"""macOS: Terminals in VS Code/Cursor über die Bedienungshilfen (Accessibility) finden.

Electron gibt seinen Barrierefreiheits-Baum erst heraus, wenn man ihn einschaltet (AXManualAccessibility,
macht macapi.ax_app). Chromium hängt an jedes Element die CSS-Klassen (AXDOMClassList) – daran
erkennen wir `xterm-screen` (Textfläche) und `xterm-helper-textarea` (Eingabefeld am Cursor, sein
Name enthält den Terminal-Titel).

Suche: zuerst über AXUIElementsForSearchPredicate (Chromium sucht selbst nach Textfeldern, schnell),
sonst durch den Baum (begrenzt). Was gefunden wurde, wird 2 s gemerkt; pro Abfrage werden nur
Positionen und Namen gelesen.
"""
import logging
from collections import deque

from ApplicationServices import AXUIElementCopyParameterizedAttributeValue

from . import macapi as M
from .vscode import Scanner

log = logging.getLogger(__name__)

EDITOR_OWNERS = {"Code", "Visual Studio Code", "Code - Insiders", "Visual Studio Code - Insiders", "Cursor"}
MAX_WEB_SEARCH = 600          # Knoten bis zur Web-Fläche
MAX_WALK = 5000               # Knoten bei der Baumsuche (Notweg)


def _name(el):
    for attr in ("AXDescription", "AXTitle", "AXHelp"):
        v = M.ax_get(el, attr)
        if v:
            return str(v)
    return ""


class AXScanner(Scanner):
    REFIND_EVERY = 2.0

    def __init__(self):
        super().__init__()
        self._web = {}            # hwnd -> AXWebArea
        self._reported = {}       # hwnd -> zuletzt geloggtes Ergebnis

    def _list_windows(self):
        return [w.id for w in M._windows() if w.owner in EDITOR_OWNERS and w.rect[2] - w.rect[0] > 200]

    def _rect(self, e):
        return M.ax_rect(e)

    def _name(self, e):
        return _name(e)

    # ------------------------------------------------------------ Suche
    def _web_area(self, hwnd, win):
        web = self._web.get(hwnd)
        if web is not None and M.ax_get(web, "AXRole") == "AXWebArea":
            return web
        queue, n = deque([(win, 0)]), 0
        while queue and n < MAX_WEB_SEARCH:
            el, depth = queue.popleft()
            n += 1
            if M.ax_get(el, "AXRole") == "AXWebArea":
                self._web[hwnd] = el
                return el
            if depth < 20:
                queue.extend((c, depth + 1) for c in M.ax_children(el))
        return None

    @staticmethod
    def _search_textareas(web):
        """Alle Textfelder per Chromium-Suche; None, wenn die Suche nicht unterstützt wird."""
        pred = {"AXSearchKey": "AXTextFieldSearchKey", "AXResultsLimit": 200,
                "AXDirection": "AXDirectionNext", "AXVisibleOnly": False}
        try:
            err, res = AXUIElementCopyParameterizedAttributeValue(web, "AXUIElementsForSearchPredicate", pred, None)
        except Exception:
            return None
        if err != 0 or res is None:
            return None
        return [e for e in res if "xterm-helper-textarea" in M.ax_classes(e)]

    @staticmethod
    def _screen_for(textarea):
        """Von einem Eingabefeld zur Textfläche: die Fläche ist ein Vorfahr (xterm-screen) bzw. ein
        Kind des Terminal-Elements (.xterm)."""
        el = textarea
        for _ in range(8):
            el = M.ax_get(el, "AXParent")
            if el is None:
                return None
            cls = M.ax_classes(el)
            if "xterm-screen" in cls:
                return el
            if "xterm" in cls:
                for c in M.ax_children(el):
                    if "xterm-screen" in M.ax_classes(c):
                        return c
                return None
        return None

    @staticmethod
    def _walk(web):
        screens, tas, tab = [], [], None
        queue, n = deque([web]), 0
        while queue and n < MAX_WALK:
            el = queue.popleft()
            n += 1
            cls = M.ax_classes(el)
            if "xterm-screen" in cls:
                screens.append(el)
            elif "xterm-helper-textarea" in cls:
                tas.append(el)
                continue
            elif "single-terminal-tab" in cls:
                tab = el
            queue.extend(M.ax_children(el))
        return screens, tas, tab, n

    def _refind_elements(self, hwnd):
        win = M.ax_window_for(hwnd)
        if win is None:
            self._report(hwnd, "kein AX-Fenster (Freigabe „Bedienungshilfen“ fehlt?)")
            return [], [], None
        web = self._web_area(hwnd, win)
        if web is None:
            self._report(hwnd, "keine Web-Fläche im Fenster gefunden")
            return [], [], None
        tas = self._search_textareas(web)
        if tas is not None:
            screens = [s for s in (self._screen_for(t) for t in tas) if s is not None]
            self._report(hwnd, f"Suche: {len(screens)} Terminal(s), {len(tas)} Eingabefeld(er)")
            return screens, tas, None
        screens, tas, tab, n = self._walk(web)
        self._report(hwnd, f"Baumsuche ({n} Knoten): {len(screens)} Terminal(s), {len(tas)} Eingabefeld(er)")
        return screens, tas, tab

    def _report(self, hwnd, text):
        if self._reported.get(hwnd) != text:
            self._reported[hwnd] = text
            log.info("VS Code/Cursor (Fenster %s): %s", hwnd, text)
