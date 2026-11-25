"""Jahreszeiten: Schnee, Laub, Blüten oder Pusteblumen-Samen fallen auf die Textzeilen und bleiben liegen.

Liegende Teilchen hängen an ihrer Zeile: scrollt der Text, wandern sie mit; verschwindet die Zeile, fallen
sie weiter. Läuft das Pet hindurch, wirbelt es sie auf.
"""
import math
import random
from datetime import date

from .world import ROW_FLOOR

SEASONS = {
    # Art: (Teilchen pro Sekunde, Größe, Farben, Fallgeschwindigkeit, Schaukeln, Liegedauer s)
    "winter": (7.0, (2, 4), ("#ffffff", "#eef6ff", "#dfeeff"), 45, 18, (120, 240)),
    "herbst": (1.6, (4, 6), ("#d9822b", "#b5541c", "#e8b23a", "#8c3b1c"), 60, 40, (60, 140)),
    "fruehling": (1.4, (3, 4), ("#ffb7c9", "#ffd3df", "#ffffff"), 40, 35, (50, 110)),
    "sommer": (0.5, (2, 3), ("#fffbe6", "#fff3b0"), 22, 50, (30, 60)),
}
MAX_FLYING = 40
MAX_RESTING = 260


def season(today=None):
    m = (today or date.today()).month
    return ("winter" if m in (12, 1, 2) else "fruehling" if m in (3, 4, 5)
            else "sommer" if m in (6, 7, 8) else "herbst")


class Weather:
    def __init__(self, kind=None, rnd=None):
        self.kind = kind or season()
        self.rnd = rnd or random.Random()
        self.flying = []       # dicts: x, y, vx, vy, size, color, phase
        self.resting = []      # dicts: pane, row, x, size, color, until
        self._spawn_acc = 0.0
        self.t = 0.0

    @property
    def active(self):
        return bool(self.flying or self.resting)

    def clear(self):
        self.flying, self.resting = [], []

    def on_world(self, world):
        """Liegende Teilchen mit ihrer Zeile mitscrollen lassen."""
        if not world.ok:
            self.clear()
            return
        keep = []
        for p in self.resting:
            d = world.shifts[p["pane"]] if p["pane"] < len(world.shifts) else None
            if d is None:
                continue                              # Tab gewechselt: weg damit
            row = p["row"] - d
            plat = world.platform_in_row(p["pane"], row, p["x"], 0) if row >= 0 else None
            if plat is None:
                # Zeile weg: weiterfallen (sofern noch im Bild)
                if row >= 0 and len(self.flying) < MAX_FLYING:
                    self.flying.append(self._flyer(p["x"], p["y"], p["size"], p["color"]))
                continue
            p["row"], p["y"] = row, plat.y
            keep.append(p)
        self.resting = keep

    def step(self, dt, world, pet=None):
        if not world.ok or not world.snap.panes:
            return
        self.t += dt
        rate, sizes, colors, fall, sway, _ = SEASONS[self.kind]
        # neue Teilchen oben über dem Pane
        self._spawn_acc += dt * rate
        rect = world.snap.panes[0].rect
        while self._spawn_acc >= 1 and len(self.flying) < MAX_FLYING:
            self._spawn_acc -= 1
            x = self.rnd.uniform(rect[0], rect[2])
            self.flying.append(self._flyer(x, rect[1] - 5, self.rnd.randint(*sizes), self.rnd.choice(colors)))
        self._spawn_acc = min(self._spawn_acc, 1.0)
        # fallen, schaukeln, landen
        still = []
        for f in self.flying:
            f["phase"] += dt
            f["vy"] = min(f["vy"] + 60 * dt, fall)
            nx = f["x"] + f["vx"] * dt + math.sin(f["phase"] * 2.0) * sway * dt
            ny = f["y"] + f["vy"] * dt
            plat = _landing(world, nx, f["y"], ny)
            if plat is not None and len(self.resting) < MAX_RESTING:
                lo, hi = SEASONS[self.kind][5]
                self.resting.append({"pane": plat.pane, "row": plat.row, "x": nx, "y": plat.y,
                                     "size": f["size"], "color": f["color"],
                                     "until": self.t + self.rnd.uniform(lo, hi)})
                continue
            if ny > rect[3] + 20:
                continue
            f["x"], f["y"] = nx, ny
            still.append(f)
        self.flying = still
        # liegende Teilchen schmelzen/verwelken; das Pet wirbelt sie beim Laufen auf
        kicked = []
        rest = []
        for p in self.resting:
            if p["until"] < self.t:
                continue
            if (pet is not None and pet.state == "walk" and abs(p["x"] - pet.x) < pet.W * 0.4
                    and abs(p["y"] - pet.y) < 4):
                kicked.append(p)
                continue
            rest.append(p)
        self.resting = rest
        for p in kicked[:6]:
            f = self._flyer(p["x"], p["y"] - 3, p["size"], p["color"])
            f["vy"] = -self.rnd.uniform(60, 140)
            f["vx"] = self.rnd.uniform(-60, 60)
            self.flying.append(f)

    def _flyer(self, x, y, size, color):
        return {"x": x, "y": y, "vx": self.rnd.uniform(-8, 8), "vy": self.rnd.uniform(10, 30),
                "size": size, "color": color, "phase": self.rnd.uniform(0, 6.28)}


def _landing(world, x, y_old, y_new):
    """Wie World.landing, aber nur für Textzeilen (keine Pane-Böden/Fenster) – günstiger."""
    best = None
    for p in world.term_platforms:
        if p.row == ROW_FLOOR or p.row < 0:
            continue
        if y_old <= p.y + 0.5 and y_new >= p.y and p.x0 <= x <= p.x1:
            if best is None or p.y < best.y:
                best = p
    return best
