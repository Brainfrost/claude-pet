"""Terminal-Emulator für mitgeschnittene Terminal-Ausgabe (VS Code/Cursor über die Begleit-Erweiterung).

Spielt den Rohdatenstrom (mit Escape-Sequenzen) in einem pyte-Bildschirm nach und liefert die
sichtbaren Zeilen – so wie Windows Terminal sie per UI Automation liefert.
"""
import re
import time

import pyte

# Sequenzen, die pyte nicht kennt und sonst als Text ausgibt (Kitty-Tastatur `CSI < u`, `CSI > 5 u`,
# modifyOtherKeys `CSI > 4 ; 2 m`, Rückfragen `CSI = …`)
_UNSUPPORTED = re.compile(r"\x1b\[[<>=][0-9;:]*[ -/]*[@-~]")
# unvollständige Escape-Sequenz am Ende eines Stücks (wird mit dem nächsten Stück zusammengesetzt)
_PARTIAL_TAIL = re.compile(r"\x1b(\[[0-9;:<>=?]*[ -/]*|\][^\x07\x1b]*|\x1b?)?$")
_MAX_TAIL = 4096


class TermEmulator:
    def __init__(self, cols=120, rows=30):
        self.screen = pyte.Screen(max(2, cols), max(2, rows))
        self.stream = pyte.Stream(self.screen)
        self._tail = ""
        self.last_feed = 0.0
        self.chars = 0

    # ------------------------------------------------------------ Daten
    def feed(self, data, now=None):
        data = self._tail + data
        m = _PARTIAL_TAIL.search(data)
        if m and m.start() < len(data) and len(data) - m.start() <= _MAX_TAIL:
            self._tail, data = data[m.start():], data[:m.start()]
        else:
            self._tail = ""
        if data:
            self.stream.feed(_UNSUPPORTED.sub("", data))
            self.chars += len(data)
        self.last_feed = time.time() if now is None else now

    # ------------------------------------------------------------ Größe/Lage
    @property
    def cols(self):
        return self.screen.columns

    @property
    def rows(self):
        return self.screen.lines

    def resize(self, cols, rows):
        cols, rows = max(2, int(cols)), max(2, int(rows))
        if (cols, rows) == (self.cols, self.rows):
            return
        self.screen.resize(rows, cols)
        c = self.screen.cursor
        c.y = min(max(c.y, 0), rows - 1)
        c.x = min(max(c.x, 0), cols - 1)

    @property
    def cursor_row(self):
        return self.screen.cursor.y

    def shift(self, n):
        """Inhalt um n Zeilen nach unten (n > 0) bzw. oben (n < 0) verschieben – der Emulator kennt die
        Zeile nicht, in der die Ausgabe begann; ausgerichtet wird am echten Cursor."""
        if not n:
            return
        s = self.screen
        c = s.cursor
        y, x = c.y, c.x
        s.cursor_position(1, 1)                  # 1-basiert: oberste Zeile
        if n > 0:
            s.insert_lines(n)
        else:
            s.delete_lines(-n)
        c.y = min(max(y + n, 0), s.lines - 1)
        c.x = x

    # ------------------------------------------------------------ Ergebnis
    def lines(self):
        """Sichtbare Zeilen, auf volle Breite mit Leerzeichen aufgefüllt."""
        return list(self.screen.display)

    @property
    def title(self):
        return (self.screen.title or "").strip()
