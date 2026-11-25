"""Mini-Spiel Bug-Jagd: 30 Sekunden lang krabbeln Käfer über die Textzeilen. Du klickst sie weg,
das Pet jagt mit. Wer mehr erwischt, gewinnt – der Rekord wird gespeichert."""
import math
import random

GAME_LEN = 30.0
MAX_BUGS = 6
SPAWN_EVERY = (0.5, 1.3)
HOP_TIME = 0.45
SPLAT_TIME = 0.6


class Bug:
    __slots__ = ("x", "y", "pane", "row", "vx", "alive", "t", "hop", "splat", "by")

    def __init__(self, x, y, pane, row, vx):
        self.x, self.y, self.pane, self.row, self.vx = x, y, pane, row, vx
        self.alive = True
        self.t = 0.0
        self.hop = None        # (x0, y0, x1, y1, pane, row, Zeit) während eines Sprungs auf eine andere Zeile
        self.splat = 0.0       # >0: gerade erwischt (Spritzer-Animation)
        self.by = None         # "du" / "pet"

    @property
    def target(self):
        """Wohin das Pet laufen soll (springt der Käfer gerade, dann zum Landepunkt)."""
        if self.hop:
            return self.hop[2], self.hop[3]
        return self.x, self.y


class BugHunt:
    def __init__(self, pane=0, rnd=None):
        self.rnd = rnd or random.Random()
        self.pane = pane
        self.left = GAME_LEN
        self.bugs = []
        self.score = {"du": 0, "pet": 0}
        self._spawn_t = 0.2

    @property
    def finished(self):
        return self.left <= 0

    @property
    def alive(self):
        return [b for b in self.bugs if b.alive]

    # ------------------------------------------------------------ Welt
    def _lines(self, world):
        cell = world.snap.panes[self.pane].cell_w if world.ok and self.pane < len(world.snap.panes) else 9
        return [p for p in world.term_platforms
                if p.pane == self.pane and p.row >= 0 and p.x1 - p.x0 >= 5 * cell]

    def on_world(self, world):
        """Text gescrollt: Käfer wandern mit ihrer Zeile; ist die Zeile weg, krabbelt der Käfer davon."""
        if not world.ok or self.pane >= len(world.shifts):
            return
        d = world.shifts[self.pane]
        for b in self.bugs:
            if not b.alive or b.hop:
                continue
            row = b.row - (d or 0)
            p = world.platform_in_row(self.pane, row, b.x, 4) if d is not None and row >= 0 else None
            if p is None:
                b.alive = False                           # weggescrollt – zählt für niemanden
                continue
            b.row, b.y = row, p.y

    def step(self, dt, world):
        self.left = max(0.0, self.left - dt)
        lines = self._lines(world) if world.ok else []
        # neue Käfer
        self._spawn_t -= dt
        if self._spawn_t <= 0 and lines and not self.finished and len(self.alive) < MAX_BUGS:
            self._spawn_t = self.rnd.uniform(*SPAWN_EVERY)
            p = self.rnd.choice(lines)
            speed = world.line_h * self.rnd.uniform(2.2, 4.2)
            self.bugs.append(Bug(self.rnd.uniform(p.x0, p.x1), p.y, p.pane, p.row,
                                 speed * self.rnd.choice((-1, 1))))
        for b in self.bugs:
            b.t += dt
            if not b.alive:
                b.splat = max(0.0, b.splat - dt)
                continue
            if b.hop:
                x0, y0, x1, y1, pane, row, ht = b.hop
                ht += dt
                k = min(1.0, ht / HOP_TIME)
                b.x = x0 + (x1 - x0) * k
                b.y = y0 + (y1 - y0) * k - math.sin(k * math.pi) * world.line_h * 1.2
                b.hop = None if k >= 1 else (x0, y0, x1, y1, pane, row, ht)
                if k >= 1:
                    b.x, b.y, b.pane, b.row = x1, y1, pane, row
                continue
            p = world.platform_in_row(b.pane, b.row, b.x, 6) if world.ok else None
            if p is None:
                b.alive = False
                continue
            b.y = p.y
            b.x += b.vx * dt
            if self.rnd.random() < dt * 0.35:
                b.vx = -b.vx                                  # Käfer sind unberechenbar
            if b.x < p.x0 or b.x > p.x1:
                b.x = min(max(b.x, p.x0), p.x1)
                near = [q for q in lines if q.row != b.row and abs(q.row - b.row) <= 4]
                if near and self.rnd.random() < 0.35:
                    q = self.rnd.choice(near)
                    b.hop = (b.x, b.y, self.rnd.uniform(q.x0, q.x1), q.y, q.pane, q.row, 0.0)
                else:
                    b.vx = -b.vx
        self.bugs = [b for b in self.bugs if b.alive or b.splat > 0]

    # ------------------------------------------------------------ fangen
    def _squash(self, b, who):
        b.alive, b.splat, b.by = False, SPLAT_TIME, who
        self.score[who] += 1

    def hit(self, x, y, radius):
        """Klick des Menschen: nächster Käfer im Umkreis wird zerquetscht."""
        if self.finished:
            return None
        best = None
        for b in self.alive:
            d = math.hypot(b.x - x, (b.y - radius * 0.5) - y)
            if d <= radius and (best is None or d < best[0]):
                best = (d, b)
        if best:
            self._squash(best[1], "du")
            return best[1]
        return None

    def catch(self, b):
        """Das Pet hat den Käfer erwischt."""
        if b.alive and not self.finished:
            self._squash(b, "pet")
            return True
        return False

    def nearest(self, x, y):
        cands = [b for b in self.alive]
        if not cands:
            return None
        return min(cands, key=lambda b: abs(b.target[0] - x) + 3 * abs(b.target[1] - y))

    def result(self):
        du, pet = self.score["du"], self.score["pet"]
        return "draw" if du == pet else "won" if pet > du else "lost"
