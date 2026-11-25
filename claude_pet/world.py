"""Macht aus einem Terminal-Snapshot eine Jump'n'Run-Welt: Textzeilen werden Plattformen."""
import re
from dataclasses import dataclass

GAP_CELLS = 3          # ab so vielen Leerzeichen am Stück entsteht ein Loch
SURFACE = 0.18         # Plattform-Oberkante relativ zur Zeilenhöhe (Oberkante der Schrift)

ROW_FLOOR = -1         # Unterkante eines Panes
ROW_SCREEN = -2        # Bildschirmboden außerhalb des Terminals
ROW_WINDOW = -4        # Oberkante eines anderen Fensters (pane = -1, text = hwnd)
ROW_VISION = -5        # per Bildanalyse erkannte Kante in irgendeinem Fenster (pane = -1)
OUTSIDE_ROWS = (ROW_SCREEN, ROW_WINDOW, ROW_VISION)


@dataclass(frozen=True)
class Platform:
    x0: float
    x1: float
    y: float
    pane: int
    row: int           # Zeilenindex im sichtbaren Bereich, -1 = Boden des Panes
    text: str = ""

    def covers(self, x, tol=0.0):
        return self.x0 - tol <= x <= self.x1 + tol


_SEG = re.compile(r"[^\s](?:[^\s]|\s{1,%d}(?=[^\s]))*" % (GAP_CELLS - 1))
_seg_cache = {}


def segments(text, gap=GAP_CELLS):
    """(start, end) Spaltenbereiche mit Text; Lücken < gap Leerzeichen werden überbrückt."""
    if gap == GAP_CELLS:
        hit = _seg_cache.get(text)
        if hit is None:
            if len(_seg_cache) > 5000:
                _seg_cache.clear()
            hit = _seg_cache[text] = [(m.start(), m.end()) for m in _SEG.finditer(text)]
        return hit
    return _segments_slow(text, gap)


def _segments_slow(text, gap):
    out, start, spaces = [], None, 0
    for i, ch in enumerate(text):
        if ch.isspace():
            spaces += 1
            if start is not None and spaces >= gap:
                out.append((start, i - spaces + 1))
                start = None
        else:
            if start is None:
                start = i
            spaces = 0
    if start is not None:
        out.append((start, len(text.rstrip())))
    return out


class World:
    def __init__(self):
        self.snap = None
        self.term_platforms = []
        self.win_platforms = []
        self.vis_platforms = []
        self.platforms = []
        self.win_rects = {}        # hwnd -> (l, t, r, b)
        self.line_h = 24.0
        self._prev_rows = []       # pro Pane: Liste der Zeilentexte
        self.shifts = []           # pro Pane: um wie viele Zeilen der Inhalt seit dem letzten Snapshot nach oben gewandert ist (None = unbekannt)

    @property
    def ok(self):
        return bool(self.snap and self.snap.ok)

    def update(self, snap):
        self.snap = snap
        if not snap.ok:
            self.term_platforms, self.shifts = [], []
            self._combine()
            return
        key = tuple((p.rect, p.x0, p.cell_w, tuple(p.lines)) for p in snap.panes)
        if key == getattr(self, "_last_key", None):
            self.shifts = [0] * len(snap.panes)       # nichts verändert: Plattformen bleiben
            return
        self._last_key = key
        plats, rows_all, shifts = [], [], []
        for pi, pane in enumerate(snap.panes):
            self.line_h = pane.line_h
            rows = [t for _, t in pane.lines]
            prev = self._prev_rows[pi] if pi < len(self._prev_rows) else None
            shifts.append(scroll_shift(prev, rows) if prev is not None else 0)
            rows_all.append(rows)
            for ri, (y, text) in enumerate(pane.lines):
                if y + pane.line_h > pane.rect[3] + 1 or y < pane.rect[1] - 1:
                    continue  # angeschnittene Zeilen am Rand ignorieren
                for a, b in segments(text):
                    plats.append(Platform(pane.x0 + a * pane.cell_w, pane.x0 + b * pane.cell_w,
                                          y + SURFACE * pane.line_h, pi, ri, text[a:b]))
            l, t, r, b = pane.rect
            plats.append(Platform(l, r, b - 2, pi, ROW_FLOOR, ""))
        self._prev_rows = rows_all
        self.term_platforms = plats
        self.shifts = shifts
        self._combine()

    def _combine(self):
        self.platforms = self.term_platforms + self.win_platforms + self.vis_platforms

    def set_vision(self, runs):
        """Per Bildanalyse erkannte Kanten [(y, x0, x1)] übernehmen; im sichtbaren Terminal gilt
        dessen genaue Textwelt, dort werden sie verworfen."""
        term = self.snap.win_rect if self.ok else None
        plats = []
        for y, a, b in runs:
            if term and term[0] <= (a + b) / 2 < term[2] and term[1] <= y < term[3]:
                continue
            plats.append(Platform(float(a), float(b), float(y), -1, ROW_VISION, "v"))
        self.vis_platforms = plats
        self._combine()

    def set_windows(self, rects, headroom, screen_top_at):
        """Oberkanten anderer Fenster als Plattformen; Stellen, die ein höheres Fenster verdeckt,
        fallen weg. rects: [(hwnd, (l,t,r,b), ist_terminal)] oberstes zuerst."""
        plats, self.win_rects = [], {}
        for i, (h, (l, t, r, b), is_term) in enumerate(rects):
            self.win_rects[h] = (l, t, r, b)
            if is_term:
                continue                      # das Terminal hat seine eigene Welt
            if t - headroom < screen_top_at((l + r) / 2, t):
                continue                      # kein Platz über dem Fenster (maximiert o.ä.)
            spans = [(l, r)]
            for _, (l2, t2, r2, b2), _ in rects[:i]:
                if t2 <= t - 2 < b2 or t2 <= t + 2 < b2:
                    spans = _subtract(spans, l2, r2)
                if not spans:
                    break
            for a, c in spans:
                if c - a >= 40:
                    plats.append(Platform(a, c, t, -1, ROW_WINDOW, str(h)))
        self.win_platforms = plats
        self._combine()

    # ------------------------------------------------------------- Abfragen
    def panes_line_h(self):
        return self.snap.panes[0].line_h if self.ok and self.snap.panes else None

    def pane_rect(self, pane=0):
        if not self.ok or pane >= len(self.snap.panes):
            return None
        return self.snap.panes[pane].rect

    def pane_at(self, x, y):
        if not self.ok:
            return None
        for i, p in enumerate(self.snap.panes):
            l, t, r, b = p.rect
            if l <= x < r and t <= y <= b:
                return i
        return None

    def tab_strip_y(self):
        """Unterkante der Tab-Leiste (dort schlüpft das Pet in die Reiter)."""
        if not self.ok or not self.snap.tabs:
            return None
        return max(t.rect[3] for t in self.snap.tabs)

    def tab_at(self, x, y):
        if not self.ok:
            return None
        for i, t in enumerate(self.snap.tabs):
            l, tp, r, b = t.rect
            if l <= x < r and tp <= y < b:
                return i
        return None

    def platform_in_row(self, pane, row, x, tol):
        for p in self.platforms:
            if p.pane == pane and p.row == row and p.covers(x, tol):
                return p
        return None

    def landing(self, x, y_old, y_new, tol):
        """Höchste Plattform, durch deren Oberkante die Füße gerade von oben gefallen sind."""
        best = None
        for p in self.platforms:
            if y_old <= p.y + 0.5 and y_new >= p.y and p.covers(x, tol):
                if best is None or p.y < best.y:
                    best = p
        return best


def _subtract(spans, l, r):
    out = []
    for a, c in spans:
        if r <= a or l >= c:
            out.append((a, c))
            continue
        if a < l:
            out.append((a, l))
        if r < c:
            out.append((r, c))
    return out


def scroll_shift(old, new, max_shift=None):
    """Um wie viele Zeilen ist der Inhalt nach oben gewandert? None, wenn kein Bezug mehr besteht
    (Tab gewechselt, Bildschirm gelöscht)."""
    if old == new:
        return 0
    n = len(new)
    max_shift = max_shift or max(len(old), n)
    keyed = [(i, s) for i, s in enumerate(old) if len(s.strip()) >= 4]
    if not keyed:
        return None
    best_d, best_score = None, 0
    for d in range(-max_shift, max_shift + 1):
        score = 0
        for i, s in keyed:
            j = i - d
            if 0 <= j < n and new[j] == s:
                score += 1
        if score > best_score:
            best_d, best_score = d, score
    if best_score < max(2, len(keyed) // 4):
        return None
    return best_d
