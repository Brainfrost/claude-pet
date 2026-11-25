"""Das Pet: Physik und Bewegungsverhalten (ohne Qt). Koordinaten: x = Mitte, y = Fußsohle, physische Pixel.

Das Pet entscheidet selbst, wie es sich im Kleinen bewegt (laufen, springen, sitzen). Größere Ziele
(in einen Tab gehen, dem Nutzer folgen) setzt brain.Brain über die öffentlichen Befehle.
"""
import math
import random

from .creatures import STAGE_PX
from .world import OUTSIDE_ROWS, ROW_FLOOR, ROW_SCREEN, ROW_VISION, ROW_WINDOW, Platform

GROUND = {"idle", "walk", "sit", "sleep", "happy", "eat", "talk"}
AIR = {"fall", "jump"}
# Abläufe beim Hinein-/Herausklettern in einen Tab-Reiter (zeitgesteuert, keine Physik)
TRANSITION = {"crouch", "hang", "climb_in", "climb_out"}

# Energie: (Verbrauch-Faktor, Erholungs-Faktor) je Charakter. Laufen/Springen kosten, Sitzen und
# Schlafen laden auf. Verspielte haben Ausdauer, Faule sind schnell erschöpft.
ENERGY = {"faul": (1.6, 1.2), "neugierig": (1.0, 1.0), "verspielt": (1.0, 0.9), "aengstlich": (1.1, 1.0)}
REGEN = {"sit": 0.3, "sleep": 0.8, "hidden": 0.5, "eat": 0.1}
AWAKE_DRAIN = 0.04      # wach sein macht langsam müde (pro Sekunde, außer beim Sitzen/Schlafen)
TIRED, EXHAUSTED = 40.0, 12.0
CROUCH_T, HANG_T, CLIMB_T = 0.22, 0.35, 0.40

# Wie sich die Charaktere bewegen
TRAITS = {
    "faul":       {"speed": 0.6, "walk": 0.30, "jump": 0.08, "sit": 0.45, "sleep": 0.85, "idle": (3.0, 8.0),
                   "sleep_len": (40, 120)},
    "neugierig":  {"speed": 1.1, "walk": 0.50, "jump": 0.20, "sit": 0.15, "sleep": 0.20, "idle": (1.2, 3.5),
                   "sleep_len": (15, 40)},
    "verspielt":  {"speed": 1.6, "walk": 0.45, "jump": 0.25, "sit": 0.12, "sleep": 0.15, "idle": (1.0, 2.8),
                   "sleep_len": (10, 25)},
    "aengstlich": {"speed": 1.0, "walk": 0.40, "jump": 0.12, "sit": 0.30, "sleep": 0.35, "idle": (1.5, 4.0),
                   "sleep_len": (20, 60)},
}


class Pet:
    def __init__(self, creature, stage="baby", personality="neugierig"):
        self.creature = creature
        self.stage = stage
        self.personality = personality
        self.traits = TRAITS.get(personality, TRAITS["neugierig"])
        self.x = self.y = 0.0
        self.vx = self.vy = 0.0
        self.state = "fall"
        self.facing = 1
        self.support = None
        self.pane = None            # in welchem Terminal-Pane das Pet zuletzt stand
        self.thrown = False
        self.timer = 1.0
        self.target_x = None
        self.edge_done = False
        self.squash = 0.0
        self.anim_t = 0.0
        self.walk_phase = 0.0
        self.next_blink = 3.0
        self.blink_t = 0.0
        self.effects = []
        self.placed = False
        self.busy = False           # Brain steuert gerade: keine eigenen Entscheidungen
        self.run = 1.0              # Tempo-Faktor fürs aktuelle Laufen (Flucht = schneller)
        self.size_factor = 1.0      # Einstellung „Größe“
        self.clip_y = None          # beim Klettern: alles oberhalb dieser Höhe ist im Reiter verschwunden
        self.tab_target = None      # (x, Unterkante) des Reiters, in den es gerade will
        self.restore = None         # wo es saß, als sein Tab weggeschaltet wurde
        self.fx_requests = []       # ("wiggle", x, y) / ("puff", x, y) für das Tab-Overlay
        self.cling_off = (0.0, 0.0)
        self.mood = 60.0
        self.bond = 10.0
        self.tricks = set()
        self.spin = 0.0             # Purzelbaum: Fortschritt der Drehung (0..1), 0 = aus
        self.spin_rate = 2.2        # Umdrehungen pro Sekunde, passend zur Flugzeit
        self.ignore_y = None        # beim Sprung nach unten: durch die eigene Ebene hindurchfallen
        self.pass_until_y = None    # beim Sprung in den Text: alle Ebenen oberhalb davon ignorieren
        self.double_hop = False     # Doppelsprung: zweiter Hüpfer steht noch aus
        self.want_adventure = False # möchte zu einem anderen Fenster springen (Controller sucht Ziel)
        self.vision_grace = 0       # Bildanalyse hat die Kante kurz verloren: so oft noch tolerieren
        self.daypart = "tag"        # morgen | tag | abend | nacht (setzt der Controller)
        self.carrying = False       # trägt gerade den Ball im Maul
        self.energy = 100.0         # 0..100 – sinkt durch Toben, steigt durch Sitzen/Schlafen
        self.set_scale(24)

    # ------------------------------------------------------------ Maßstab
    def set_scale(self, line_h):
        self.line_h = line_h
        base = STAGE_PX.get(self.stage, 3) * max(1, int(round(line_h / 19)))
        self.px = max(1, int(round(base * self.size_factor)))
        self.W = self.creature["w"] * self.px
        self.H = self.creature["h"] * self.px
        S = line_h / 24.0
        self.S = S
        self.G = 2000 * S
        self.WALK = 48 * S * self.traits["speed"]
        self.tol = 3 * self.px

    @property
    def visible_state(self):
        return self.state != "hidden"

    @property
    def grounded(self):
        return self.state in GROUND and self.support is not None

    # ------------------------------------------------------------ Welt-Updates
    def on_world(self, world):
        """Nach jedem neuen Terminal-Snapshot: Plattform unter den Füßen nachführen (Scrollen)."""
        if not world.ok:
            # Terminal minimiert/weg: wer drin stand, fällt raus und erkundet die anderen Fenster
            sp = self.support
            if self.pane is not None and self.state in GROUND and sp is not None and sp.pane >= 0:
                self.pane = None
                self._start_fall(0.0, -150 * self.S)
            return
        if world.panes_line_h():
            self.set_scale(world.panes_line_h())
        if not self.placed:
            self._spawn(world)
            return
        if self.state in AIR:
            self._catch_scrolling_line(world)
            return
        if self.state not in GROUND or self.support is None or self.support.pane < 0:
            return
        sp = self.support
        new = None
        d = None
        if sp.row == ROW_FLOOR:
            new = next((p for p in world.platforms if p.pane == sp.pane and p.row == sp.row), None)
        else:
            d = world.shifts[sp.pane] if sp.pane < len(world.shifts) else None
            if d is not None:
                new = world.platform_in_row(sp.pane, sp.row - d, self.x, self.tol)
            else:
                cand = [p for p in world.platforms if abs(p.y - sp.y) < 2 and p.covers(self.x, self.tol)]
                new = cand[0] if cand else None
        if new is None and d is not None and sp.row - d < 0:
            # seine Zeile ist oben aus dem Bild gescrollt: auf die nächste Zeile darunter umsteigen,
            # statt frei zu fallen (beim schnellen Scrollen rauschte es sonst bis ganz nach unten)
            below = [p for p in world.platforms if p.pane == sp.pane and p.row >= 0
                     and p.covers(self.x, self.tol) and p.y >= self.y - 2]
            if below:
                new = min(below, key=lambda p: p.y)
                self.squash = max(self.squash, 0.35)
        if new is None:
            self._start_fall(vx=0.0, vy=0.0)
        else:
            self.support, self.y = new, new.y

    def _catch_scrolling_line(self, world):
        """Im Fall: Zieht durchs Scrollen eine Zeile an den Füßen vorbei nach oben, landet es darauf
        (die normale Landeprüfung sieht nur Füße, die eine Zeile durchqueren)."""
        if self.pane is None or self.pane >= len(world.shifts) or self.vy < -50 * self.S:
            return
        d = world.shifts[self.pane]
        if not d or d <= 0:
            return
        shift = d * self.line_h
        passed = [p for p in world.platforms if p.pane == self.pane and p.row >= 0
                  and p.covers(self.x, self.tol) and p.y <= self.y + 1 < p.y + shift]
        if passed:
            self.vy = min(self.vy, 300 * self.S)
            self._land(max(passed, key=lambda p: p.y))

    def on_windows(self, world, old_rects):
        """Fensterkanten neu berechnet: auf einem Fenster stehend mitwandern oder runterfallen."""
        sp = self.support
        if self.state not in GROUND or sp is None or sp.row != ROW_WINDOW:
            return
        h = int(sp.text)
        old, new = old_rects.get(h), world.win_rects.get(h)
        if old and new and old != new:
            self.x += new[0] - old[0]
        q = next((q for q in world.win_platforms
                  if q.text == sp.text and q.covers(self.x, self.tol)), None)
        if q is None:
            self._start_fall(0.0, 0.0)
        else:
            self.support, self.y = q, q.y

    def on_vision(self, world):
        """Bildanalyse neu: auf einer erkannten Kante stehend die Höhe nachführen oder fallen."""
        sp = self.support
        if self.state not in GROUND or sp is None or sp.row != ROW_VISION:
            return
        cands = [q for q in world.vis_platforms if abs(q.y - sp.y) <= 6 and q.covers(self.x, self.tol)]
        if cands:
            q = min(cands, key=lambda q: abs(q.y - sp.y))
            self.support, self.y, self.vision_grace = q, q.y, 2
        elif self.vision_grace > 0:
            self.vision_grace -= 1              # kurz nicht erkannt (Flackern): noch stehen bleiben
        else:
            self._start_fall(0.0, 0.0)

    def translate(self, dx, dy):
        """Terminal-Fenster wurde verschoben: mitwandern, wenn wir drin sind."""
        if self.pane is not None and self.state not in ("held", "cling"):
            self.x += dx
            self.y += dy

    # ------------------------------------------------------------ Nutzer-Interaktion
    def grab(self):
        self.pass_until_y = None
        self.state = "held"
        self.support = None
        self.busy = False
        self.clip_y = self.tab_target = None
        self.effects = [e for e in self.effects if e["kind"] != "z"]

    def drop(self, vx, vy):
        cap = 3200 * self.S
        self.vx = max(-cap, min(cap, vx))
        self.vy = max(-cap, min(cap, vy))
        self.state = "fall"
        self.thrown = True
        self.pane = None

    def poke(self):
        if self.state in ("held", "hidden") or self.state in TRANSITION:
            return
        if self.state == "cling":
            self.uncling()
            return
        if self.state == "sleep":
            self._effect("!" if self.personality != "faul" else "…", life=0.9)
            self._hop(-520 if self.personality != "faul" else -200)
        elif self.personality == "aengstlich":
            self._effect("!", life=0.8)
            self._hop(-600)
            self.vx = random.choice((-1, 1)) * 260 * self.S
        else:
            self._effect("heart", life=1.2)
            self._hop(-320)

    def stroke(self):
        if self.state not in GROUND:
            return
        was_sleeping = self.state == "sleep"
        self.state = "happy"
        self.timer = 2.0
        for i in range(1 if was_sleeping else 3):
            self._effect("heart", life=1.4, dx=random.uniform(-0.4, 0.4) * self.W, delay=i * 0.25)

    def react(self, kind):
        """Reaktion auf ein Session-Ereignis (done/start/error/success/attention), je nach Charakter."""
        if self.state in ("held", "hidden", "cling") or self.state in TRANSITION:
            return
        p = self.personality
        g = self.grounded and not self.busy
        if kind in ("done", "success"):
            if p == "faul":
                self._effect("…" if self.state == "sleep" else "heart", life=1.2)
                return
            self._effect("heart", life=1.3)
            self._effect("heart", life=1.3, dx=0.3 * self.W, delay=0.2)
            if g:
                if p == "verspielt" or (p == "neugierig" and kind == "done"):
                    self._hop(-480)
                else:
                    self.state, self.timer = "happy", 2.0
        elif kind == "error":
            if p == "aengstlich":
                self._effect("!", life=1.0)
                if g:
                    self._hop(-560)
                    self.vx = random.choice((-1, 1)) * 220 * self.S
            elif p == "faul":
                self._effect("…", life=1.2)
            else:
                self._effect("!", life=0.8)
                if g and p == "verspielt":
                    self._hop(-300)
        elif kind == "attention":
            if p == "faul":
                self._effect("…", life=1.0)
            else:
                self._effect("!", life=1.0)
                if g:
                    self._hop(-400)
        elif kind == "start":
            if p in ("neugierig", "verspielt"):
                self._effect("!", life=0.6)
            elif p == "faul" and g and self.state not in ("sit", "sleep"):
                self.state, self.timer = "sit", random.uniform(4, 10)

    def perform(self, action):
        """Eine von Haiku gewählte Aktion ausführen (verstecken/hinlaufen macht das Brain)."""
        if self.state in ("held", "hidden", "cling") or self.state in TRANSITION:
            return
        g = self.grounded and not self.busy
        if action == "huepfen" and g:
            self._hop(-420)
        elif action == "freuen":
            self.react("success")
        elif action == "tanzen":
            for i in range(3):
                self._effect("♪", life=1.2, dx=random.uniform(-0.5, 0.5) * self.W, delay=i * 0.35)
            if g:
                self.state, self.timer = "happy", 2.6
        elif action == "erschrecken":
            self._effect("!", life=0.9)
            if g:
                self._hop(-520)
                self.vx = random.choice((-1, 1)) * 200 * self.S
        elif action == "hinsetzen" and g:
            self.state, self.timer = "sit", random.uniform(6, 14)
        elif action == "einschlafen" and g:
            self.state, self.timer = "sleep", random.uniform(*self.traits["sleep_len"])
        elif action == "umschauen":
            self._effect("?", life=1.0)
            if g:
                self.facing = -self.facing
                self.state, self.timer = "idle", 1.5

    @property
    def tired(self):
        return self.energy < TIRED

    def _spend(self, amount):
        cost = ENERGY.get(self.personality, (1.0, 1.0))[0]
        if self.daypart == "abend":
            cost *= 1.2
        elif self.daypart == "nacht":
            cost *= 1.5
        self.energy = max(0.0, self.energy - amount * cost)

    def _recover(self, dt, state):
        if state not in REGEN and state != "held":
            self._spend(dt * AWAKE_DRAIN)
        rate = REGEN.get(state, 0.0) * ENERGY.get(self.personality, (1.0, 1.0))[1]
        if self.daypart in ("abend", "nacht"):
            rate *= 0.8
        if rate:
            self.energy = min(100.0, self.energy + rate * dt)

    def start_talking(self):
        """Etwas sagen: stehen bleiben, bis die Sprechblase weg ist (Rede-Animation)."""
        if self.grounded and self.state not in ("sleep", "eat", "talk"):
            self.state, self.run = "talk", 1.0
            self.target_x = self.x
            return True
        return False

    def stop_talking(self):
        if self.state == "talk":
            self.state, self.timer = "idle", random.uniform(0.6, 1.5)

    def eat(self):
        """Ein Wort anknabbern (der Controller zeigt den Biss im Text)."""
        if not self.grounded:
            return False
        self.state, self.timer, self.busy = "eat", 1.6, False
        return True

    def celebrate(self):
        """Git-Moment: Tänzchen mit Konfetti."""
        for i in range(3):
            self._effect("konfetti", life=1.4, dx=random.uniform(0, 6.28), delay=i * 0.2)
        self.perform("tanzen")

    def go_to_word(self, word, world):
        """Zu einem Wort im sichtbaren Text laufen bzw. springen. True, wenn gefunden."""
        if not word or not self.grounded or self.busy or self.pane is None:
            return False
        w = word.lower().strip(" .,:;!?\"'«»„“")
        if len(w) < 2:
            return False
        best = None
        for q in world.platforms:
            if q.pane != self.pane or q.row < 0:
                continue
            i = q.text.lower().find(w)
            if i < 0:
                continue
            frac = (i + len(w) / 2) / max(1, len(q.text))
            tx = q.x0 + (q.x1 - q.x0) * frac
            d = abs(q.y - self.y) * 2 + abs(tx - self.x)
            if best is None or d < best[0]:
                best = (d, q, tx)
        if best is None:
            return False
        _, q, tx = best
        tx = min(max(tx, q.x0 + self.px), q.x1 - self.px)
        if q is self.support or abs(q.y - self.y) < 2:
            self.walk_to(tx, run=1.4)
        elif abs(q.y - self.y) > 6 * self.line_h:
            self.leap_to(tx, q.y)
        else:
            self._ballistic_to(tx, q.y, apex=0.7 * self.line_h)
        return True

    # ------------------------------------------------------------ Befehle vom Brain
    def walk_to(self, x, run=1.0):
        if not self.grounded:
            return False
        self.target_x, self.run = x, run
        self.state, self.edge_done = "walk", False
        return True

    def jump_to(self, tx, ty, apex=None):
        if not self.grounded and self.state not in AIR:
            return False
        self._ballistic_to(tx, ty, apex=apex if apex is not None else 0.8 * self.line_h)
        return True

    def begin_enter(self, tab_x, tab_bottom):
        """In einen Tab-Reiter klettern: ducken -> hochspringen -> am Reiter hängen -> hineinziehen."""
        self.tab_target = (tab_x, tab_bottom)
        self.busy = True
        if self.grounded:
            self.state, self.timer = "crouch", CROUCH_T
            self.squash = 0.6
        else:
            self._hang_at(tab_x, tab_bottom)

    def _hang_at(self, tab_x, tab_bottom):
        self.x, self.y = tab_x, tab_bottom + self.H * 0.98
        self.vx = self.vy = 0.0
        self.support = None
        self.state, self.timer = "hang", HANG_T
        self.fx_requests.append(("wiggle", tab_x, tab_bottom))

    def emerge_at(self, x, tab_bottom):
        """Aus einem Tab-Reiter herausklettern (Kopf voran nach unten) und dann fallen."""
        self.placed = True
        self.x, self.y = x, tab_bottom
        self.support, self.pane = None, 0
        self.vx = self.vy = 0.0
        self.tab_target = (x, tab_bottom)
        self.clip_y = tab_bottom
        self.state, self.timer = "climb_out", CLIMB_T
        self.fx_requests.append(("wiggle", x, tab_bottom))

    def hide_with_tab(self):
        """Sein Tab wurde weggeschaltet: sofort mit dem Tab-Inhalt verschwinden, Platz merken."""
        sp = self.support
        if self.state in GROUND and sp is not None and sp.pane >= 0:
            st = self.state if self.state in ("sit", "sleep") else "idle"
            self.restore = (sp.pane, sp.row, sp.text, self.x, self.y, st, self.timer)
        else:
            self.restore = None
        self.state, self.busy = "hidden", False
        self.clip_y = self.tab_target = None
        self.effects = []

    def restore_in(self, world):
        """Tab wieder offen: genau dort weitermachen, wo es saß. False, wenn der Platz weg ist."""
        r, self.restore = self.restore, None
        if not r:
            return False
        pane, row, text, x, y, st, timer = r
        cands = [q for q in world.platforms
                 if q.pane == pane and q.row >= 0 and q.text == text and q.covers(x, self.tol)]
        if not cands:
            cands = [q for q in world.platforms
                     if q.pane == pane and q.row >= 0 and abs(q.y - y) < 3 and q.covers(x, self.tol)]
        if not cands:
            return False
        q = min(cands, key=lambda q: abs(q.y - y))
        self.x, self.y, self.support, self.pane = x, q.y, q, pane
        self.state, self.timer = st, max(1.0, timer)
        self.placed = True
        return True

    def cling(self, off_x, off_y):
        self.state, self.support, self.busy = "cling", None, True
        self.cling_off = (off_x, off_y)
        self._effect("heart", life=1.0)

    def uncling(self):
        if self.state == "cling":
            self.busy = False
            self._start_fall(0, 0)

    def drop_down(self, world):
        """Aus dem Tab-Reiter hinein in den Text springen – mitten hinein (mittlerer bis unterer
        Bereich), nicht auf die oberste Zeile, wo es sonst hängen blieb."""
        p = self.support
        pane = p.pane if p is not None and p.pane >= 0 else (self.pane or 0)
        r = world.pane_rect(pane)
        cands = [q for q in world.platforms
                 if q.pane == pane and q.row >= 0 and q.x1 - q.x0 > self.W
                 and abs((q.x0 + q.x1) / 2 - self.x) < 14 * self.W]
        if r:
            h = r[3] - r[1]
            middle = [q for q in cands if r[1] + 0.3 * h <= q.y <= r[1] + 0.85 * h]
            cands = middle or cands
        if cands:
            q = random.choice(cands)
            tx = min(max(self.x, q.x0 + self.W / 2), q.x1 - self.W / 2)
            if abs(q.y - self.y) > 12 * self.line_h:
                self.leap_to(tx, q.y)
            else:
                self._ballistic_to(tx, q.y, apex=0.4 * self.line_h)
            self.pass_until_y = q.y - 2               # nicht schon oben auf einer Zeile hängenbleiben
        else:
            self._start_fall(self.facing * self.WALK, -100 * self.S)

    # ------------------------------------------------------------ Simulation
    def step(self, dt, world, screen_floor, vbounds, cursor):
        self.anim_t += dt
        self.squash = max(0.0, self.squash - dt * 4)
        self._tick_effects(dt)
        self._tick_blink(dt)
        st = self.state
        self._recover(dt, st)
        if self.spin > 0 and st not in AIR:
            self.spin += dt * 5
            if self.spin >= 1:
                self.spin = 0.0
        if st in ("held", "hidden") or not self.placed:
            return
        if st == "cling":
            self.x = cursor[0] + self.cling_off[0]
            self.y = cursor[1] + self.cling_off[1]
            return
        if st in TRANSITION:
            self._transition(dt)
            return
        if st in AIR:
            self._air(dt, world, screen_floor, vbounds)
        else:
            self._ground(dt, world)

    def _transition(self, dt):
        self.timer -= dt
        st = self.state
        if st == "hang" and self.tab_target is None:
            if self.timer <= 0:
                self._start_fall(0.0, 0.0)                # nach dem Herausklettern loslassen
            return
        tx, ty = self.tab_target or (self.x, self.y)
        if st == "crouch":
            self.squash = 0.6
            if self.timer <= 0:
                self.squash = 0.0
                # Sprung so, dass der Kopf am Scheitelpunkt die Reiter-Unterkante berührt
                self._ballistic_to(tx, ty + self.H * 0.98, apex=0.05 * self.line_h)
                self.double_hop = False
                self.spin = 0.0
        elif st == "hang":
            # kurz am Reiter baumeln
            if self.tab_target is None:
                return                                    # Herausklettern: unten loslassen (s.u.)
            self.x = tx + math.sin(self.anim_t * 18) * self.px * 0.6
            if self.timer <= 0:
                self.x = tx
                self.clip_y = ty
                self.state, self.timer = "climb_in", CLIMB_T
        elif st == "climb_in":
            k = 1 - max(0.0, self.timer / CLIMB_T)
            k = k * k * (3 - 2 * k)                       # weich ein-/ausblenden
            self.y = ty + self.H * 0.98 * (1 - k)
            if self.timer <= 0:
                self.fx_requests.append(("puff", tx, ty))
                self.clip_y = self.tab_target = None
                self.restore = None
                self.state, self.busy = "hidden", False
        elif st == "climb_out":
            k = 1 - max(0.0, self.timer / CLIMB_T)
            k = k * k * (3 - 2 * k)
            self.y = ty + self.H * 0.98 * k
            if self.timer <= 0:
                self.clip_y = None
                self.state, self.timer = "hang", HANG_T * 0.6
                self.tab_target = None

    def _air(self, dt, world, screen_floor, vbounds):
        if self.tab_target and self.state == "jump" and self.vy >= -40 * self.S:
            self._hang_at(*self.tab_target)               # Scheitelpunkt: am Reiter festhalten
            return
        if self.double_hop and self.vy > 0:
            self.double_hop = False                 # Doppelsprung: in der Luft nachlegen
            self.vy = -380 * self.S
            self._effect("*", life=0.5)
        if self.spin > 0:
            self.spin += dt * self.spin_rate
            if self.spin >= 1:
                self.spin = 0.0
        self.vy = min(self.vy + self.G * dt, 3500 * self.S)
        nx = self.x + self.vx * dt
        ny = self.y + self.vy * dt
        if not self.thrown and self.pane is not None:
            r = world.pane_rect(self.pane)
            if r:
                lo, hi = r[0] + self.W / 2, r[2] - self.W / 2
                if nx < lo or nx > hi:
                    nx = min(max(nx, lo), hi)
                    self.vx = -self.vx * 0.3
        l, t, r_, b = vbounds
        if nx < l + self.W / 2 or nx > r_ - self.W / 2:
            nx = min(max(nx, l + self.W / 2), r_ - self.W / 2)
            self.vx = -self.vx * 0.5
        if ny - self.H < t:
            ny = t + self.H
            self.vy = abs(self.vy) * 0.2
        if self.vy > 0:
            if self.ignore_y is not None and self.y > self.ignore_y + 3:
                self.ignore_y = None
            p = world.landing(nx, self.y, ny, self.tol, skip_y=self.ignore_y)
            if p is not None and self.pass_until_y is not None and p.y < self.pass_until_y:
                p = None                              # noch nicht am Ziel: weiterfallen
            floor = screen_floor(nx)
            if p is None and ny >= floor:
                p = Platform(nx - 10 ** 6, nx + 10 ** 6, floor, -1, ROW_SCREEN)
            if p is not None:
                self.x = nx
                self._land(p)
                return
        self.x, self.y = nx, ny

    def _land(self, p):
        impact = self.vy
        self.double_hop = False
        self.ignore_y = None
        self.pass_until_y = None
        self.y = p.y
        self.vx = self.vy = 0.0
        self.support = p
        self.pane = p.pane if p.pane >= 0 else None
        self.thrown = False
        self.edge_done = False
        self.squash = min(1.0, impact / (1400 * self.S))
        if impact > 2200 * self.S:
            self._effect("*", life=1.6)
            self.state, self.timer = "sit", random.uniform(1.5, 3)
        else:
            self.state, self.timer = "idle", random.uniform(*self.traits["idle"]) * 0.5

    def _ground(self, dt, world):
        p = self.support
        if p is None:
            self._start_fall(0, 0)
            return
        st = self.state
        if st == "talk":
            return                                    # steht still und redet
        if st == "eat":
            self.timer -= dt
            if random.random() < dt * 6:
                self._effect("krümel", life=0.7, dx=self.facing * self.W * 0.35)
            if self.timer <= 0:
                self.state, self.timer = "happy", 1.2
                self._effect("heart", life=1.2)
            return
        if st in ("idle", "sit", "sleep", "happy"):
            self.timer -= dt
            if st == "sleep" and random.random() < dt * 0.9:
                self._effect("z", life=2.2, dx=self.W * 0.3)
            if self.timer > 0 or self.busy:
                return
            if st == "sit":
                night = self.daypart == "nacht"
                if random.random() < (0.95 if night else self.traits["sleep"]):
                    self.state, self.timer = "sleep", random.uniform(*self.traits["sleep_len"]) * (2.5 if night else 1)
                else:
                    self.state, self.timer = "idle", random.uniform(*self.traits["idle"])
                return
            if st in ("sleep", "happy"):
                self.state, self.timer = "idle", random.uniform(*self.traits["idle"])
                return
            self._decide(world)
        elif st == "walk":
            d = 1 if self.target_x > self.x else -1
            self.facing = d
            self._spend(dt * 0.25 * self.run * (1.4 if self.carrying else 1.0))
            step = self.WALK * self.run * (0.75 if self.tired else 1.0) * dt
            self.walk_phase += step
            if abs(self.target_x - self.x) <= step:
                self.x = self.target_x
                self.run = 1.0
                self.state, self.timer = "idle", random.uniform(*self.traits["idle"])
                return
            self.x += d * step
            if p.covers(self.x, 0):
                self.edge_done = False
            elif not p.covers(self.x, self.tol):
                if not self.edge_done:
                    self._at_edge(world, d)
                elif not p.covers(self.x, self.tol * 2):
                    self._start_fall(vx=d * self.WALK, vy=0.0)

    def _decide(self, world):
        p = self.support
        tr = self.traits
        if p.row in OUTSIDE_ROWS:                      # draußen: erkunden oder heimspringen
            home = {"neugierig": 0.45, "aengstlich": 0.6, "verspielt": 0.15, "faul": 0.12}
            if world.ok and random.random() < home.get(self.personality, 0.3):
                if self._jump_home(world):
                    return
            self._explore(world)
            return
        if self.energy < EXHAUSTED:
            self._effect("gähn", life=1.8)
            self.state = "sleep"                          # Nickerchen, bis es wieder fit ist
            self.timer = (85.0 - self.energy) / (REGEN["sleep"] * ENERGY[self.personality][1])
            return
        if (self.daypart == "abend" or self.tired) and random.random() < 0.15:
            self._effect("gähn", life=1.8)
        if self.daypart == "nacht" and random.random() < 0.7:
            self.state, self.timer = "sit", random.uniform(2, 5)     # nachts: hinsetzen, einschlafen
            return
        r = random.random()
        w_walk, w_jump, w_sit = tr["walk"], tr["jump"], tr["sit"]
        if self.mood < 35:                            # schlechte Laune: eher rumsitzen
            w_walk, w_jump, w_sit = w_walk * 0.7, w_jump * 0.5, w_sit + 0.25
        elif self.mood > 75:
            w_jump *= 1.5
        if self.tired:                                # müde: kaum springen, öfter hinsetzen
            w_walk, w_jump, w_sit = w_walk * 0.5, w_jump * 0.15, w_sit + 0.4
        chance = {"verspielt": 0.07, "neugierig": 0.05, "aengstlich": 0.012, "faul": 0.01}.get(
            self.personality, 0.03) * (2 if "weitsprung" in self.tricks else 1)
        if self.energy > 50 and random.random() < chance:
            self.want_adventure = True          # Controller sucht per Bildanalyse ein Ziel
            self.timer = 1.0
            return
        if r < w_walk:
            lo, hi = p.x0 + self.px, p.x1 - self.px
            if p.row == ROW_FLOOR:
                lo, hi = max(p.x0, self.x - 8 * self.W), min(p.x1, self.x + 8 * self.W)
            if random.random() < 0.25:
                lo, hi = lo - 2 * self.W, hi + 2 * self.W
            self.walk_to(random.uniform(lo, hi) if hi > lo else (lo + hi) / 2)
        elif r < w_walk + w_jump:
            # je weiter oben, desto eher nach unten; findet eine Richtung kein Ziel, die andere
            rect = world.pane_rect(p.pane) if p.pane >= 0 else None
            frac = (p.y - rect[1]) / max(1, rect[3] - rect[1]) if rect else 0.5
            up = random.random() < min(0.65, max(0.1, frac))
            if not self._jump_to_other(world, up=up) and not self._jump_to_other(world, up=not up):
                self.timer = random.uniform(*tr["idle"])
        elif r < w_walk + w_jump + w_sit:
            self.state, self.timer = "sit", random.uniform(5, 14)
        else:
            self.timer = random.uniform(*tr["idle"])

    def _explore(self, world):
        """Auf Fensterkanten/Bildschirmboden: herumlaufen, zu anderen Fenstern springen, rasten."""
        p = self.support
        r = random.random()
        if r < 0.35:
            lo = max(p.x0, self.x - 6 * self.W) + self.px
            hi = min(p.x1, self.x + 6 * self.W) - self.px
            self.walk_to(random.uniform(lo, hi) if hi > lo else self.x)
        elif r < 0.65:
            if not self._jump_window(world):
                self.timer = random.uniform(*self.traits["idle"])
        elif r < 0.8:
            self.state, self.timer = "sit", random.uniform(4, 10)
        else:
            self.timer = random.uniform(*self.traits["idle"])

    def _jump_window(self, world, far=False):
        reach = 5.5 if "doppelsprung" in self.tricks else 3.5
        span = (20 if far or "weitsprung" in self.tricks else 7) * self.W
        cands = []
        for q in world.platforms:
            if q.row not in (ROW_WINDOW, ROW_VISION) or q is self.support or q.x1 - q.x0 < self.W * 0.8:
                continue
            dy = self.y - q.y
            tx = min(max(self.x, q.x0 + self.W / 2), q.x1 - self.W / 2)
            if abs(tx - self.x) > span or dy > reach * self.H:
                continue
            cands.append((q, tx))
        if not cands:
            return False
        q, tx = random.choice(cands)
        if abs(tx - self.x) > 8 * self.W:
            self.leap_to(tx, q.y)
        else:
            self._ballistic_to(tx, q.y, apex=0.8 * self.H)
        return True

    def adventure_to(self, x0, x1, y):
        """Ausflug: zu einer Kante in einem anderen Fenster springen (Ziel sucht der Controller)."""
        self.want_adventure = False
        if not self.grounded or self.busy:
            return False
        lo, hi = x0 + self.W / 2, x1 - self.W / 2
        self.leap_to(random.uniform(lo, hi) if hi > lo else (x0 + x1) / 2, y)
        self.pane = None
        self._effect("!", life=0.7)
        return True

    def _at_edge(self, world, d):
        if self.edge_done:
            return
        self.edge_done = True
        if self.busy:
            return
        if self.support.pane < 0:                     # draußen: rüberspringen oder runterfallen
            if random.random() < 0.5 and self._jump_window(world):
                return
            if random.random() < 0.4:
                p = self.support
                self.target_x = random.uniform(p.x0 + self.px, max(p.x0 + self.px, p.x1 - self.px))
                return
            self._start_fall(vx=d * self.WALK * 1.3, vy=-90 * self.S)
            return
        r = random.random()
        careful = 0.6 if self.personality in ("aengstlich", "faul") else 0.35
        if r < careful:
            p = self.support
            self.target_x = random.uniform(p.x0 + self.px, max(p.x0 + self.px, p.x1 - self.px))
        elif r < 0.8:
            self._start_fall(vx=d * self.WALK * 1.3, vy=-90 * self.S)
        else:
            if not self._jump_to_other(world, up=None, direction=d):
                self._start_fall(vx=d * self.WALK * 1.3, vy=-90 * self.S)

    # ------------------------------------------------------------ Sprünge
    def _jump_to_other(self, world, up, direction=0):
        p = self.support
        h = self.line_h
        cands = []
        for q in world.platforms:
            if q is p or q.pane != p.pane or q.row < 0 or q.x1 - q.x0 < self.px * 3:
                continue
            dy = p.y - q.y
            reach = 5.5 if "doppelsprung" in self.tricks else 3.3
            if up is True and not (0.5 * h < dy <= reach * h):
                continue
            if up is False and not (-6 * h <= dy < -0.5 * h):
                continue
            if up is None and not (-4 * h <= dy <= 2.3 * h):
                continue
            tx = min(max(self.x, q.x0 + self.px), q.x1 - self.px)
            dist = abs(tx - self.x)
            if dist > 5 * self.W or dist < (self.W * 0.5 if up is None else 0):
                continue
            if direction and (tx - self.x) * direction <= 0:
                continue
            cands.append((q, tx))
        if not cands:
            return False
        q, tx = random.choice(cands)
        self._ballistic_to(tx + random.uniform(-1, 1) * self.px, q.y, apex=0.7 * h)
        return True

    def _jump_home(self, world):
        plats = [q for q in world.platforms if q.pane >= 0 and q.row >= 0 and q.x1 - q.x0 > self.W]
        if not plats:
            plats = [q for q in world.platforms if q.pane >= 0]
        if not plats:
            return False
        q = random.choice(plats)
        tx = random.uniform(q.x0 + self.px, q.x1 - self.px) if q.x1 - q.x0 > 2 * self.px else q.x0
        self.leap_to(tx, q.y)
        self._effect("!", life=0.6)
        return True

    def _pass_own_floor(self, ty):
        """Ziel liegt tiefer: die Ebene unter den Füßen darf beim Herunterfallen nicht bremsen."""
        sp = self.support
        self.ignore_y = sp.y if sp is not None and ty > sp.y + 2 else None

    def leap_to(self, tx, ty):
        """Weiter Sprung über beliebige Distanz (z.B. zurück ins Terminal)."""
        self._pass_own_floor(ty)
        self._spend(4.0)
        dist = math.hypot(tx - self.x, ty - self.y)
        T = min(1.6, max(0.6, dist / (1400 * self.S)))
        if ty < self.y:
            T = max(T, math.sqrt(2 * (self.y - ty) / self.G) * 1.2)
        self.vx = (tx - self.x) / T
        self.vy = (ty - self.y - 0.5 * self.G * T * T) / T
        self.facing = 1 if self.vx >= 0 else -1
        self.state, self.support, self.thrown = "jump", None, True

    def _ballistic_to(self, tx, ty, apex):
        self._pass_own_floor(ty)
        self._spend(1.5)
        top = min(self.y, ty) - apex
        vy0 = -math.sqrt(2 * self.G * max(1.0, self.y - top))
        t_up = -vy0 / self.G
        t_down = math.sqrt(2 * max(1.0, ty - top) / self.G)
        T = t_up + t_down
        self.vx = (tx - self.x) / T
        self.vy = vy0
        self.facing = 1 if self.vx >= 0 else -1
        self.state, self.support = "jump", None
        if "purzelbaum" in self.tricks and random.random() < 0.25:
            self._start_spin(T)

    def _hop(self, vy):
        self.vy = vy * self.S
        self.vx = 0.0
        self.state, self.support = "jump", None
        self._spend(1.5)
        self._maybe_trick()

    def _start_spin(self, airtime):
        """Purzelbaum nur bei genug Flugzeit, und so schnell, dass er bis zur Landung rum ist."""
        if airtime >= 0.3:
            self.spin, self.spin_rate = 0.001, 1.0 / (airtime * 0.9)

    def _maybe_trick(self):
        if "purzelbaum" in self.tricks and random.random() < 0.35:
            self._start_spin(2 * abs(self.vy) / self.G)
        if "doppelsprung" in self.tricks and random.random() < 0.3:
            self.double_hop = True

    def _start_fall(self, vx, vy):
        self.vx, self.vy = vx, vy
        self.state, self.support = "fall", None

    def _spawn(self, world):
        plats = [q for q in world.platforms if q.row >= 0 and q.x1 - q.x0 > self.W]
        if not plats:
            plats = world.platforms
        if not plats:
            return
        q = random.choice(plats)
        r = world.pane_rect(q.pane)
        self.x = (q.x0 + q.x1) / 2
        self.y = r[1] + self.H if r else q.y - 3 * self.H
        self.pane = q.pane
        self._start_fall(0, 0)
        self.placed = True

    # ------------------------------------------------------------ Effekte & Darstellung
    def _effect(self, kind, life, dx=0.0, delay=0.0):
        self.effects.append({"kind": kind, "age": -delay, "life": life, "dx": dx})

    def _tick_effects(self, dt):
        for e in self.effects:
            e["age"] += dt
        self.effects = [e for e in self.effects if e["age"] < e["life"]]

    def _tick_blink(self, dt):
        self.next_blink -= dt
        if self.next_blink <= 0:
            self.blink_t = 0.13
            self.next_blink = random.uniform(2.8, 4.6)
        self.blink_t = max(0.0, self.blink_t - dt)

    def pose(self):
        """Was der Renderer zeichnen soll."""
        st = self.state
        if st == "jump":
            st = "fall" if self.vy > 0 else "jump"
        elif st == "cling":
            st = "fall"
        elif st == "crouch":
            st = "sit"
        elif st == "eat":
            st = "sit" if int(self.anim_t / 0.15) % 2 else "idle"      # mampfen
        elif st in TRANSITION:
            st = "fall"
        return {"state": st, "walk_i": int(self.anim_t / (0.15 / max(0.5, self.run))),
                "blinking": self.blink_t > 0, "facing": self.facing}
