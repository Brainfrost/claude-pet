"""Das 'Gehirn': entscheidet nach Charakter, in welcher Session (Tab) das Pet lebt und was es vorhat.

Ziele (self.goal):
  ("enter", ref)  – in den Reiter des Tabs ref klettern (ducken, hochspringen, hineinziehen)
  ("drop",)       – gerade aus einem Reiter herausgeklettert: runter auf den Text des aktiven Tabs
"""
import logging
import random
import re
from collections import deque

from .pet import AIR, TRANSITION

log = logging.getLogger(__name__)

# Wörter, die das Pet gern frisst
FOOD = re.compile(r"\b(bugs?|todos?|fixme|errors?|fehler)\b", re.I)
BALL_INTEREST = {"verspielt": 1.0, "neugierig": 0.8, "aengstlich": 0.4, "faul": 0.15}
EAT_EVERY = {"verspielt": (20, 50), "neugierig": (25, 60), "aengstlich": (60, 150), "faul": (90, 240)}
# Nach dem Fressen satt (Sekunden): in der Zeit wird nichts gefressen, auch nicht auf Maus-Hinweis
SATED = {"verspielt": (360, 600), "neugierig": (480, 720), "aengstlich": (720, 1200), "faul": (900, 1800)}
GOAL_TIMEOUT = 25.0
MAX_GOAL_JUMPS = 4      # so viele Sprünge ohne Erfolg, dann gibt es auf

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
        self.ball = None               # setzt der Controller, solange ein Ball im Spiel ist
        self.cursor = (0, 0)
        self.goal_t = 0.0
        self._ball_check = 0.0
        self.eat_t = random.uniform(*EAT_EVERY.get(personality, (40, 90))) * 0.5
        self.food_urge = False         # neues Futter im Text gesehen -> bald essen gehen
        self.news = False              # neuer Text erschienen (für die Neugier)
        self.sated_t = 0.0             # so lange (s) ist es noch satt
        self.on_ate = None             # Callback(word, platform, start) – Biss anzeigen, zählen
        self.on_fetched = None         # Callback() – Ball zurückgebracht

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

    SCARY = re.compile(r"^(error|errors|fehler|exception|failed|fatal|crash|warning|traceback)$", re.I)

    def hovered(self, word, x, plat, world):
        """Der Mauszeiger ruht auf einem Wort im Terminal: je nach Charakter hinschauen, hinlaufen,
        draufspringen, nervös werden – oder es fressen gehen."""
        pet = self.pet
        if self.goal and self.goal[0] == "eat":
            self.goal, pet.busy = None, False          # du zeigst auf etwas: das ist wichtiger
        if (self.goal or pet.busy or pet.state in ("hidden", "held", "cling", "sleep", "eat", "talk")
                or not pet.grounded or pet.pane is None or plat.pane != pet.pane):
            return False
        pet.facing = 1 if x > pet.x else -1
        if FOOD.fullmatch(word):
            start = plat.text.find(word)
            if start >= 0 and self.hungry:
                self.set_goal(("eat", plat.text, plat.row, start, word))
                return True
            pet._effect("…", life=1.0)                  # satt: nur hinschauen
            return True
        p = self.pers
        if pet.tired:
            if random.random() < 0.3:
                pet._effect("gähn", life=1.5)             # müde: nur hinschauen
            return True
        if p == "neugierig":
            pet._effect("?", life=0.9)
            self.set_goal(None)
            if abs(plat.y - pet.y) < 2:
                pet.walk_to(x, run=1.3)
            else:
                pet.go_to_word(word, world)
        elif p == "verspielt":
            pet._effect("!", life=0.6)
            pet._ballistic_to(x, plat.y, apex=1.2 * pet.line_h)      # draufspringen
        elif p == "aengstlich":
            if self.SCARY.match(word):
                pet._effect("!", life=0.9)
                pet.walk_to(pet.x - pet.facing * 4 * pet.W, run=2.4)
        elif p == "faul" and random.random() < 0.3:
            pet._effect("…", life=1.0)
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
        self.cursor = cursor
        self._track_cursor(dt, cursor)
        pet = self.pet
        if pet.state == "talk":
            return                                    # erst ausreden
        if pet.state == "cling":
            self.cling_t -= dt
            if self.cling_t <= 0:
                pet.uncling()
            return
        if self.goal:
            self.goal_t += dt
            if self.goal_t > GOAL_TIMEOUT:            # aufgeben, nicht ewig hinterherjagen
                self.goal, pet.busy = None, False
                return
            if self.goal[0] in ("ball", "eat"):
                self._pursue_play(world)
            elif world.ok and world.snap.tabs:
                self._pursue(world)
            return
        if self._maybe_ball(dt):
            return
        if not world.ok or not world.snap.tabs:
            return
        if self._maybe_eat(dt, world):
            return
        self.decide_t -= dt
        if self.decide_t <= 0:
            self.decide_t = random.uniform(*DECIDE_EVERY.get(self.pers, (30, 60)))
            self._decide(world)
        self._personality_tick(dt, world, cursor)

    def set_goal(self, goal):
        self.goal, self.goal_t, self.goal_jumps, self._goal_best = goal, 0.0, 0, None

    # ------------------------------------------------------------ Ball & Futter
    def _maybe_ball(self, dt):
        pet, ball = self.pet, self.ball
        if ball is None or not ball.free or not pet.placed or not pet.grounded or pet.busy:
            return False
        self._ball_check -= dt
        if self._ball_check > 0:
            return False
        self._ball_check = 1.0
        interest = BALL_INTEREST.get(self.pers, 0.5) * (0.0 if pet.energy < 25 else (pet.energy / 100) ** 0.5)
        if random.random() < interest:
            self.set_goal(("ball",))
            return True
        pet.facing = 1 if ball.x > pet.x else -1           # schaut wenigstens hin
        return False

    @property
    def hungry(self):
        return self.sated_t <= 0

    def _maybe_eat(self, dt, world):
        pet = self.pet
        if self.sated_t > 0:
            self.sated_t -= dt
            self.food_urge = False
            return False
        if pet.state == "hidden" or pet.pane is None or not pet.grounded or pet.busy:
            return False
        self.eat_t -= dt * (4 if self.food_urge else 1)
        if self.eat_t > 0:
            return False
        self.eat_t = random.uniform(*EAT_EVERY.get(self.pers, (40, 90)))
        self.food_urge = False
        food = self._find_food(world)
        if food:
            self.set_goal(("eat",) + food)
            return True
        return False

    def _find_food(self, world):
        pet = self.pet
        best = None
        for p in world.term_platforms:
            if p.pane != pet.pane or p.row < 0:
                continue
            r = world.pane_rect(p.pane)
            if r and p.y - pet.H * 1.3 < r[1]:
                continue                        # zu nah am oberen Rand: kein Platz zum Hinspringen
            m = FOOD.search(p.text)
            if not m:
                continue
            d = abs(p.y - pet.y) * 2 + abs(p.x0 - pet.x)
            if best is None or d < best[0]:
                best = (d, (p.text, p.row, m.start(), m.group(0)))
        return best[1] if best else None

    def _food_spot(self, world, text, row, start, word):
        """Die Zeile mit dem Futter wiederfinden (sie kann inzwischen gescrollt sein)."""
        cands = [p for p in world.term_platforms if p.text == text and p.row >= 0]
        if not cands:
            return None
        p = min(cands, key=lambda q: abs(q.row - row))
        cell = world.snap.panes[p.pane].cell_w if world.ok and p.pane < len(world.snap.panes) else 9
        return p, p.x0 + (start + len(word) / 2) * cell

    def _pursue_play(self, world):
        pet = self.pet
        if pet.state in ("held", "hidden"):
            self.goal, pet.busy = None, False
            if self.ball is not None and self.ball.carried_by == "pet":
                self.ball.carried_by, pet.carrying = None, False
            return
        if pet.state in AIR or pet.state in TRANSITION or pet.state in ("cling", "eat") or not pet.grounded:
            return
        if getattr(self, "goal_jumps", 0) > MAX_GOAL_JUMPS:
            # kommt nicht hin (zu weit oben, Text scrollt weg …): aufgeben statt endlos zu hüpfen
            log.info("Ziel %s aufgegeben nach %d Sprüngen", self.goal[0], self.goal_jumps)
            if self.goal[0] == "eat":
                self.eat_t = random.uniform(*EAT_EVERY.get(self.pers, (40, 90)))
            self.goal, pet.busy = None, False
            return
        pet.busy = True
        if self.goal[0] == "eat":
            spot = self._food_spot(world, *self.goal[1:])
            if spot is None:
                self.goal, pet.busy = None, False
                return
            p, tx = spot
            if abs(pet.y - p.y) < 2 and abs(pet.x - tx) < pet.W * 0.3:
                _, _text, _row, start, word = self.goal
                pet.facing = 1 if tx >= pet.x else -1
                self.goal = None
                pet.eat()
                self.sated_t = random.uniform(*SATED.get(self.pers, (480, 900)))
                if self.on_ate:
                    self.on_ate(word, p, start)
                return
            self._move_to(world, tx, p.y)
            return
        # Ball
        ball = self.ball
        if ball is None or ball.carried_by == "user":
            self.goal, pet.busy = None, False
            pet.carrying = False
            return
        if pet.carrying:
            tx, ty = self._return_spot(world)
            if abs(pet.y - ty) < 3 and abs(pet.x - tx) < pet.W * 0.8:
                ball.carried_by, pet.carrying = None, False
                ball.x = pet.x + pet.facing * pet.W * 0.6
                ball.y = pet.y - pet.H * 0.5
                ball.throw(pet.facing * 120 * pet.S, -260 * pet.S)
                self.goal, pet.busy = None, False
                pet.react("success")
                if self.on_fetched:
                    self.on_fetched()
                return
            self._move_to(world, tx, ty)
            return
        if not ball.resting:
            pet.facing = 1 if ball.x > pet.x else -1
            return
        if abs(pet.y - ball.bottom) < 4 and abs(pet.x - ball.x) < pet.W * 0.55:
            ball.carried_by, pet.carrying = "pet", True
            self.goal_jumps, self._goal_best = 0, None      # neue Etappe: zurückbringen
            pet._effect("!", life=0.5)
            return
        self._move_to(world, ball.x, ball.bottom)

    def _return_spot(self, world):
        """Wohin der Ball gebracht wird: auf die Ebene direkt unter deinem Mauszeiger."""
        cx, cy = self.cursor
        pet = self.pet
        below = [p for p in world.platforms if p.covers(cx, pet.W * 0.5) and p.y >= cy]
        if not below:
            return pet.x, pet.y
        p = min(below, key=lambda q: q.y)
        return min(max(cx, p.x0 + pet.W * 0.3), p.x1 - pet.W * 0.3), p.y

    def _move_to(self, world, tx, ty):
        pet = self.pet
        # nur Sprünge zählen, nach denen es dem Ziel nicht näher gekommen ist
        dist = abs(pet.x - tx) + 3 * abs(pet.y - ty)
        best = getattr(self, "_goal_best", None)
        if best is not None and dist < best - pet.W * 0.5:
            self.goal_jumps = 0
        self._goal_best = dist if best is None else min(best, dist)
        if abs(pet.y - ty) < 3:
            if pet.state != "walk" or abs(pet.target_x - tx) > pet.W * 0.5:
                pet.walk_to(tx, run=1.8)
        else:
            self.goal_jumps = getattr(self, "goal_jumps", 0) + 1
            if abs(tx - pet.x) > 10 * pet.W or pet.y - ty > 6 * pet.line_h:
                pet.leap_to(tx, ty)
            else:
                pet._ballistic_to(tx, ty, apex=0.7 * pet.line_h)

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
                if self.news and not pet.tired:
                    self.news = False
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
        if abs(q.y - pet.y) > 12 * pet.line_h:
            pet.leap_to(tx, q.y)                       # nur bei sehr weiten Wegen ein großer Satz
        else:
            pet.jump_to(tx, q.y)

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
