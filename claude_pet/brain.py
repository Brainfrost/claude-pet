"""Das 'Gehirn': entscheidet nach Charakter, in welcher Session (Tab) das Pet lebt und was es vorhat.

Ziele (self.goal):
  ("enter", ref)  – in den Reiter des Tabs ref klettern (ducken, hochspringen, hineinziehen)
  ("drop",)       – gerade aus einem Reiter herausgeklettert: runter auf den Text des aktiven Tabs
"""
import logging
import random
from collections import deque

from .pet import AIR, TRANSITION

log = logging.getLogger(__name__)

DECIDE_EVERY = {
    "faul": (60, 150),
    "neugierig": (25, 60),
    "verspielt": (20, 50),
    "aengstlich": (40, 100),
}


def tab_key(tab):
    """Tab-Titel ohne das Status-Zeichen, das Claude Code voranstellt."""
    name = tab.name
    if name and not name[0].isalnum():
        name = name[1:]
    return name.strip()


class Brain:
    def __init__(self, pet, personality):
        self.pet = pet
        self.pers = personality
        self.home = None            # (key, index) des Tabs, in dem das Pet wohnt
        self.goal = None
        self.prev_active = None
        self.decide_t = random.uniform(*DECIDE_EVERY.get(personality, (30, 60))) * 0.5
        self.cursor_hist = deque(maxlen=20)
        self.cursor_still_t = 0.0
        self.cling_t = 0.0

    # ------------------------------------------------------------ Tabs finden
    def _ref(self, world, i):
        return (tab_key(world.snap.tabs[i]), i)

    def _find(self, world, ref):
        if ref is None or not world.ok:
            return None
        tabs = world.snap.tabs
        for i, t in enumerate(tabs):
            if tab_key(t) == ref[0]:
                return i
        return ref[1] if ref[1] < len(tabs) else None

    def _active(self, world):
        return next((i for i, t in enumerate(world.snap.tabs) if t.selected), None)

    def _tab_cx(self, world, i):
        l, _, r, _ = world.snap.tabs[i].rect
        return (l + r) / 2

    def _idle_tabs(self, world, exclude_active=True):
        return [i for i, t in enumerate(world.snap.tabs)
                if t.state != "working" and not (exclude_active and t.selected)]

    # ------------------------------------------------------------ Ereignisse
    def on_world(self, world):
        if not world.ok or not world.snap.tabs:
            return
        a = self._active(world)
        if a is None:
            return
        ref = self._ref(world, a)
        if self.home is None:
            self.home = ref
        prev = self.prev_active
        self.prev_active = ref
        if prev is not None and self._find(world, prev) != a:
            self._active_changed(world, prev, ref)
        # Tab des versteckten Pets wurde geschlossen: im aktiven Tab auftauchen
        if self.pet.state == "hidden" and self._find(world, self.home) is None:
            self.home = ref
            self._emerge(world, a)

    def _active_changed(self, world, prev, new):
        pet = self.pet
        log.info("aktiver Tab: %s -> %s (Pet: %s, home=%s)", prev[0][:30], new[0][:30], pet.state, self.home and self.home[0][:30])
        if pet.state == "hidden":
            hi = self._find(world, self.home)
            if hi is not None and hi == self._find(world, new):
                if not pet.restore_in(world):            # du öffnest seinen Tab: es sitzt noch da
                    self._emerge(world, hi)              # ... oder klettert aus dem Reiter
            elif self.pers == "neugierig" and hi is not None:
                self._emerge(world, hi)                  # kommt raus und läuft dir nach
            return
        if pet.state in ("held", "cling") or pet.pane is None:
            self.home = new
            return
        if self.pers == "neugierig" or (self.pers == "verspielt" and random.random() < 0.5):
            self.home = new                              # bleibt bei dir
            self.goal = None
            pet.busy = False
        else:
            # gehört zum Inhalt seines Tabs: verschwindet sofort mit ihm (und sitzt beim
            # Zurückwechseln wieder genau dort)
            self.goal = None
            pet.hide_with_tab()

    def dropped_on_tab(self, world, i):
        """Nutzer hat das Pet auf einem Tab-Reiter losgelassen."""
        pet = self.pet
        tab = world.snap.tabs[i]
        sy = world.tab_strip_y()
        if tab.selected or sy is None:
            return False
        pet.begin_enter(self._tab_cx(world, i), sy)
        self.home, self.goal = self._ref(world, i), None
        return True

    def hide_somewhere(self, world):
        """Von Haiku gewünscht: sich in einem anderen (am liebsten ruhigen) Tab verstecken."""
        if self.goal or self.pet.state in ("hidden", "held", "cling") or not world.ok:
            return False
        tabs = world.snap.tabs
        cands = self._idle_tabs(world) or [i for i, t in enumerate(tabs) if not t.selected]
        if not cands:
            return False
        self.goal = ("enter", self._ref(world, random.choice(cands)))
        self.decide_t = random.uniform(20, 60)   # nicht ewig verschwunden bleiben
        return True

    # ------------------------------------------------------------ Takt
    def tick(self, dt, world, cursor):
        if not world.ok or not world.snap.tabs:
            return
        self._track_cursor(dt, cursor)
        pet = self.pet
        if pet.state == "cling":
            self.cling_t -= dt
            if self.cling_t <= 0:
                pet.uncling()
            return
        if self.goal:
            self._pursue(world)
            return
        self.decide_t -= dt
        if self.decide_t <= 0:
            self.decide_t = random.uniform(*DECIDE_EVERY.get(self.pers, (30, 60)))
            self._decide(world)
        self._personality_tick(dt, world, cursor)

    def _pursue(self, world):
        pet = self.pet
        kind = self.goal[0]
        if pet.state in ("held", "hidden"):
            self.goal, pet.busy = None, False
            return
        if pet.state in TRANSITION or pet.state == "cling":
            return
        if kind == "drop":
            # gerade unter einem Reiter hervorgekommen: runter auf den Text des aktiven Tabs
            a = self._active(world)
            if a is not None:
                self.home = self._ref(world, a)
            self.goal, pet.busy = None, False
            pet.drop_down(world)
            return
        # kind == "enter": hochspringen, am Scheitelpunkt in den Reiter schlüpfen
        i = self._find(world, self.goal[1])
        sy = world.tab_strip_y()
        if i is None or sy is None or world.snap.tabs[i].selected:
            self.goal, pet.busy = None, False
            return
        if pet.state in AIR:
            return
        if pet.grounded:
            self.home, self.goal = self._ref(world, i), None
            pet.begin_enter(self._tab_cx(world, i), sy)

    def _emerge(self, world, i):
        sy = world.tab_strip_y()
        if sy is None:
            return
        self.pet.restore = None
        self.pet.emerge_at(self._tab_cx(world, i), sy)
        self.pet.busy = True
        self.goal = ("drop",)

    # ------------------------------------------------------------ Charakter
    def _decide(self, world):
        pet = self.pet
        tabs = world.snap.tabs
        hi = self._find(world, self.home)
        home_working = hi is not None and tabs[hi].state == "working"
        hidden = pet.state == "hidden"
        visible = not hidden and pet.pane is not None and pet.grounded
        p = self.pers
        if p == "faul":
            if (home_working or random.random() < 0.4) and visible:
                idle = self._idle_tabs(world)
                if idle:
                    self.goal = ("enter", self._ref(world, random.choice(idle)))
            elif hidden and home_working:
                idle = self._idle_tabs(world)
                if idle:
                    self.home = self._ref(world, random.choice(idle))   # zieht leise um
        elif p == "neugierig":
            if hidden and hi is not None:
                self._emerge(world, hi)
            elif visible:
                self._look_at_newest(world)
        elif p == "verspielt":
            if hidden and hi is not None:
                self._emerge(world, hi)
            elif visible:
                r = random.random()
                others = [i for i, t in enumerate(tabs) if not t.selected]
                if r < 0.35 and others:
                    self.goal = ("enter", self._ref(world, random.choice(others)))
                    self.decide_t = random.uniform(8, 25)      # kommt bald wieder raus
                elif r < 0.7:
                    pet.walk_to(pet.x + random.choice((-1, 1)) * random.uniform(3, 8) * pet.W, run=2.2)
        if p in ("faul", "aengstlich") and hidden and not home_working and random.random() < 0.3:
            if hi is not None:
                self._emerge(world, hi)            # mal vorsichtig rausschauen
            return
        if p == "aengstlich":
            if visible and home_working:
                idle = self._idle_tabs(world)
                if idle:
                    pet._effect("!", life=0.8)
                    self.goal = ("enter", self._ref(world, random.choice(idle)))
            elif hidden and home_working:
                idle = self._idle_tabs(world)
                if idle:
                    self.home = self._ref(world, random.choice(idle))

    def _look_at_newest(self, world):
        """Neugierig: zur neuesten Ausgabe (unterste Textzeilen) springen."""
        pet = self.pet
        cands = [q for q in world.platforms if q.row >= 0 and q.pane == (pet.pane or 0)
                 and q.x1 - q.x0 > pet.W * 0.6]
        if not cands:
            return
        bottom = max(q.row for q in cands)
        near = [q for q in cands if q.row >= bottom - 3]
        q = random.choice(near)
        tx = min(max(pet.x, q.x0 + pet.px), q.x1 - pet.px)
        pet.leap_to(tx, q.y) if abs(q.y - pet.y) > 6 * pet.line_h else pet.jump_to(tx, q.y)

    def _track_cursor(self, dt, cursor):
        import time
        now = time.perf_counter()
        if self.cursor_hist and abs(cursor[0] - self.cursor_hist[-1][1]) + abs(cursor[1] - self.cursor_hist[-1][2]) < 2:
            self.cursor_still_t += dt
        else:
            self.cursor_still_t = 0.0
        self.cursor_hist.append((now, cursor[0], cursor[1]))

    def _cursor_speed(self):
        if len(self.cursor_hist) < 2:
            return 0.0
        (t0, x0, y0), (t1, x1, y1) = self.cursor_hist[0], self.cursor_hist[-1]
        return ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 / max(1e-3, t1 - t0)

    def _personality_tick(self, dt, world, cursor):
        pet = self.pet
        if pet.state not in ("idle", "walk", "sit", "happy") or not pet.grounded or pet.pane is None:
            return
        cx, cy = cursor
        dx = cx - pet.x
        dist = (dx ** 2 + (cy - (pet.y - pet.H / 2)) ** 2) ** 0.5
        in_pane = world.pane_at(cx, cy) == pet.pane
        p = self.pers
        # an den Mauszeiger hängen
        cling_rate = {"verspielt": 0.35, "neugierig": 0.15, "faul": 0.01, "aengstlich": 0.0}.get(p, 0)
        cling_rate *= 0.4 + pet.bond / 60.0
        if dist < 3 * pet.W and self.cursor_still_t > 1.0 and random.random() < dt * cling_rate:
            self.cling_t = random.uniform(3, 8)
            pet.cling(0.0, pet.H + 6)
            return
        if p == "neugierig" and in_pane and pet.state == "idle" and abs(dx) > 3 * pet.W \
                and random.random() < dt * 0.6:
            sp = pet.support
            pet.walk_to(min(max(cx, sp.x0), sp.x1) if sp.row >= 0 else cx)
        elif p == "aengstlich" and dist < 3 * pet.W and self._cursor_speed() > 1200:
            if pet.run < 2:
                pet._effect("!", life=0.6)
            pet.walk_to(pet.x - (1 if dx > 0 else -1) * random.uniform(3, 6) * pet.W, run=2.6)
