"""Das kleine Hirn: Haiku plant alle paar Minuten, was das Pet als Nächstes vorhat.

Ablauf: Das Hirn schreibt ein Lagebild (Uhrzeit, Energie, Stimmung, was du tust, Sessions, was zuletzt
passiert ist, was das Pet gemacht hat, ein maskierter Bildschirm-Auszug, sein Gedächtnis) und Haiku
antwortet mit einem Gedanken und einem Plan aus 1–3 Schritten. Das Pet führt die Schritte mit seinen
vorhandenen Bewegungen aus (brain.py fragt `drive`). Physik und Reflexe (Maus, Werfen, Fallen,
Erschöpfung) bleiben lokal – Haiku braucht Sekunden pro Antwort. Ohne Plan würfelt das Pet wie bisher.

Häufigkeit (Einstellung „brain“): normal ≈ alle 3–5 Min. bei Aktivität + wichtige Momente (höchstens
15/h), sparsam ≈ alle 8–15 Min. (höchstens 6/h), aus = nie. Bist du weg (keine Eingabe), plant es nicht.
"""
import json
import logging
import random
import re
import time
from collections import deque
from dataclasses import dataclass

from . import daily, personas, profile
from .speech import context_from, mask

log = logging.getLogger(__name__)

LEVELS = {
    "aus": None,
    "sparsam": {"min_gap": 480, "max_gap": 900, "per_hour": 6},
    "normal": {"min_gap": 180, "max_gap": 300, "per_hour": 15},
}
URGENT_GAP = 75          # s: wichtige Momente dürfen so bald nach dem letzten Plan neu planen
AWAY_AFTER = 240         # s ohne Eingabe: Mensch ist weg -> nur noch bei wichtigen Momenten planen
FIRST_PLAN = 40          # s nach dem Start
SHOW_THOUGHT = 0.35      # so oft erscheint der Gedanke als Wolke (bei wichtigen Momenten öfter)
MEMORY_KEEP = 10
WAIT_READY = 12.0        # s: so lange wartet ein Schritt, bis das Pet bereit ist (landet, ausredet …)
URGENT_KINDS = {"done", "error", "attention"}

VERBS = {
    "zuschauen": "zur neuesten Ausgabe im Terminal springen, dort sitzen und zuschauen",
    "hinlaufen": "zu einem Wort im Terminal laufen und dort bleiben (ziel = ein Wort, das wörtlich im "
                 "Bildschirm-Auszug steht)",
    "fressen": "ein Futterwort anknabbern (bug, TODO, FIXME, error, Fehler …; ziel = das Wort)",
    "sitzen": "sich hinsetzen und ausruhen",
    "schlafen": "ein Nickerchen machen",
    "erkunden": "frei auf den Textzeilen herumlaufen und -springen",
    "verstecken": "sich in einem anderen, ruhigen Tab verkriechen",
    "zur_maus": "zum Mauszeiger deines Menschen laufen und bei ihm sein",
    "ausflug": "auf ein anderes Fenster springen und es erkunden",
    "tanzen": "ein kurzes Freudentänzchen",
    "huepfen": "einmal hochhüpfen",
    "umschauen": "sich verwundert umschauen",
}
INSTANT = {"tanzen", "huepfen", "umschauen", "ausflug", "verstecken"}
DURATION = {"zuschauen": (20, 240), "hinlaufen": (10, 120), "fressen": (5, 30), "sitzen": (15, 240),
            "schlafen": (30, 300), "erkunden": (20, 180), "zur_maus": (10, 60)}
REASONS = {
    "start": "Du bist gerade aufgewacht und schaust, was los ist.",
    "takt": "Ein paar Minuten sind vergangen – was machst du als Nächstes?",
    "plan_fertig": "Dein letzter Plan ist erledigt.",
    "done": "Claude ist gerade mit einer Aufgabe fertig geworden.",
    "error": "Gerade ist ein Fehler im Terminal aufgetaucht.",
    "attention": "Claude wartet gerade auf eine Antwort oder Freigabe deines Menschen.",
    "pause_ende": "Dein Mensch ist gerade aus einer Pause zurück.",
}


@dataclass
class Step:
    verb: str
    ziel: str = ""
    dauer: float = 30.0
    left: float = 30.0
    started: bool = False
    phase: int = 0
    waited: float = 0.0


# ===================================================================== reine Logik (getestet)
def parse_plan(out):
    """Haiku-Antwort -> (gedanke, [Step], merken). Unbekanntes wird verworfen, Dauern begrenzt."""
    m = re.search(r"\{.*\}", out or "", re.S)
    if not m:
        return "", [], ""
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return "", [], ""
    if not isinstance(d, dict):
        return "", [], ""
    thought = str(d.get("gedanke") or "").strip().strip('"„“')[:140]
    steps = []
    for item in d.get("plan") or []:
        if not isinstance(item, dict):
            continue
        verb = str(item.get("tun") or "").strip().lower()
        if verb not in VERBS:
            continue
        ziel = str(item.get("ziel") or "").strip()[:40]
        lo, hi = DURATION.get(verb, (2, 5))
        try:
            dauer = float(item.get("dauer") or lo)
        except (TypeError, ValueError):
            dauer = lo
        dauer = min(max(dauer, lo), hi) if verb not in INSTANT else 4.0
        steps.append(Step(verb, ziel, dauer, dauer))
        if len(steps) == 3:
            break
    memo = str(d.get("merken") or "").strip()[:160]
    return thought, steps, memo


def remember(prof, note, today):
    """Notiz ins Gedächtnis (bleibt im Steckbrief); keine Dubletten, nur die letzten MEMORY_KEEP."""
    note = (note or "").strip()
    if not note:
        return False
    mem = prof.setdefault("memory", [])
    if any(m.get("text") == note for m in mem):
        return False
    mem.append({"t": today, "text": note})
    del mem[:-MEMORY_KEEP]
    return True


def due(level, now, last_plan, started_at, has_plan, idle, urgent, history):
    """Ist ein neuer Plan fällig? -> Anlass oder None."""
    cfg = LEVELS.get(level)
    if cfg is None:
        return None
    while history and now - history[0] > 3600:
        history.popleft()
    if len(history) >= cfg["per_hour"]:
        return None
    since = now - last_plan if last_plan else now - started_at
    if urgent:
        return urgent if since >= URGENT_GAP else None
    if idle > AWAY_AFTER:
        return None                                   # du bist weg: nichts verbrauchen
    if not last_plan:
        return "start" if since >= FIRST_PLAN else None
    if not has_plan and since >= cfg["min_gap"]:
        return "plan_fertig"
    if since >= cfg["max_gap"]:
        return "takt"
    return None


def system_prompt(prof):
    verbs = "\n".join(f"- {k}: {v}" for k, v in VERBS.items())
    return (
        personas.identity(prof)
        + "\nDu planst jetzt, was du in den nächsten Minuten machst – wie ein echtes kleines Tier mit "
        "eigenem Kopf. Richte dich nach deinem Charakter, deiner Energie und Stimmung, der Tageszeit, "
        "dem, was dein Mensch gerade tut, und dem, was im Terminal passiert.\n"
        "Regeln:\n"
        "- Müde (Energie unter 40) oder spät: eher sitzen, schlafen, zuschauen. Fit und gute Laune: eher "
        "erkunden, fressen, tanzen, Ausflüge.\n"
        "- Arbeitet Claude gerade, ist Zuschauen spannend. Ist etwas fertig oder schiefgegangen, reagiere "
        "darauf (zuschauen, hinlaufen, freuen, erschrecken passt zu deinem Charakter).\n"
        "- Mach nicht immer dasselbe wie zuletzt.\n"
        "- Deinen Menschen nennst du nie beim Namen, immer nur „mein Mensch“ – auch wenn ein Name im "
        "Terminal steht.\n"
        "- \"gedanke\": ein kurzer innerer Gedanke auf Deutsch (höchstens 10 Wörter, Ich-Form, deine "
        "Stimme). Keine Dateinamen, Pfade, Namen, Nummern oder Zugangsdaten.\n"
        "- \"plan\": 1 bis 3 Schritte. \"tun\" aus dieser Liste, \"dauer\" in Sekunden, \"ziel\" nur bei "
        "hinlaufen/fressen (ein Wort, das wörtlich im Bildschirm-Auszug steht), sonst \"\".\n"
        f"{verbs}\n"
        "- \"merken\": nur wenn dir etwas Bleibendes über deinen Menschen oder euren Tag auffällt, das "
        "du dir merken willst (höchstens 12 Wörter, keine Namen, Pfade, Nummern, Zugangsdaten), sonst \"\".\n"
        'Antworte NUR mit JSON: {"gedanke": "...", "plan": [{"tun": "...", "ziel": "", "dauer": 60}], '
        '"merken": ""}'
    )


# ===================================================================== Hirn
class Mind:
    def __init__(self, ctl):
        self.ctl = ctl
        self.level = "normal"
        self.plan = deque()
        self.step = None
        self.last_plan = 0.0
        self.started_at = time.time()
        self.history = deque()
        self.urgent = None
        self.pending = False
        self.events = deque(maxlen=8)       # (Zeit, Art, Detail)
        self.did = deque(maxlen=6)          # was das Pet zuletzt gemacht hat
        self.thought = ""

    # ------------------------------------------------------------ Eingänge
    def set_level(self, level):
        self.level = level if level in LEVELS else "normal"
        if LEVELS.get(self.level) is None:
            self.plan.clear()
            self.step = None

    def note_events(self, events):
        now = time.time()
        for kind, detail in events:
            self.events.append((now, kind, mask(detail or "")[:80]))
            if kind in URGENT_KINDS:
                self.urgent = kind

    def note(self, kind):
        """Wichtiger Moment von außen (z.B. pause_ende)."""
        self.events.append((time.time(), kind, ""))
        self.urgent = kind

    # ------------------------------------------------------------ Takt (Controller, ~1×/s)
    def tick(self, now=None):
        now = time.time() if now is None else now
        ctl = self.ctl
        if self.pending or ctl.quiet_reason or not ctl.speech.exe or not ctl.pet.placed:
            return
        has_plan = self.step is not None or bool(self.plan)
        reason = due(self.level, now, self.last_plan, self.started_at, has_plan,
                     daily.idle_seconds(), self.urgent, self.history)
        if reason is None:
            return
        self.urgent = None
        self._ask(reason, now)

    def _ask(self, reason, now):
        user = self.situation(reason)
        self.pending = True
        self.last_plan = now
        self.history.append(now)
        log.info("Hirn: plane (%s), %d diese Stunde", reason, len(self.history))
        ok = self.ctl.speech.write(system_prompt(self.ctl.prof), user,
                                   lambda out, r=reason: self._on_plan(out, r),
                                   on_fail=self._on_fail)
        if not ok:
            self.pending = False

    def _on_fail(self, *_):
        self.pending = False

    def _on_plan(self, out, reason):
        self.pending = False
        thought, steps, memo = parse_plan(out)
        if not steps:
            log.info("Hirn: kein verwertbarer Plan (%s)", (out or "")[:120])
            return
        self.plan = deque(steps)
        self.step = None
        self.thought = thought
        log.info("Hirn: %s | %s", thought, ", ".join(f"{s.verb}{'→' + s.ziel if s.ziel else ''} {s.dauer:.0f}s"
                                                     for s in steps))
        if memo and remember(self.ctl.prof, memo, time.strftime("%Y-%m-%d")):
            log.info("Hirn merkt sich: %s", memo)
            profile.save(self.ctl.prof)
        urgent = reason in URGENT_KINDS or reason == "pause_ende"
        if thought and random.random() < (0.6 if urgent else SHOW_THOUGHT):
            self.ctl.show_thought(thought)

    # ------------------------------------------------------------ Lagebild
    def situation(self, reason):
        ctl, pet, world = self.ctl, self.ctl.pet, self.ctl.world
        now = time.time()
        lines = [f"Anlass: {REASONS.get(reason, reason)}",
                 f"Uhrzeit: {time.strftime('%H:%M')} ({daily.daypart()}).",
                 f"Du: Energie {pet.energy:.0f}/100, Stimmung {pet.mood:.0f}/100, Bindung {pet.bond:.0f}/100, "
                 f"gerade: {_where(pet)}."]
        idle = daily.idle_seconds()
        streak = ctl.work.streak_start
        if idle > AWAY_AFTER:
            lines.append(f"Dein Mensch: seit {idle / 60:.0f} Min. nicht am Rechner.")
        else:
            work = f", arbeitet seit {(now - streak) / 60:.0f} Min. am Stück" if streak else ""
            where = "schaut gerade auf dein Terminal" if ctl.terminal_focused() else "ist in einem anderen Fenster"
            lines.append(f"Dein Mensch: aktiv{work}, {where}.")
        if world.ok:
            sess = [f"„{_short(t.name)}“ {_state(t.state)}" for t in world.snap.tabs]
            sess += [f"„{_short(t.name)}“ {_state(t.state)} (anderes Programm)" for t in world.snap.others]
            if sess:
                lines.append("Sessions: " + "; ".join(sess[:6]) + ".")
        ev = [f"{_ago(now - t)}: {EVENT_LABEL.get(k, k)}{(' – ' + d) if d else ''}"
              for t, k, d in self.events if now - t < 1800]
        if ev:
            lines.append("Zuletzt passiert:\n" + "\n".join(f"- {e}" for e in ev[-6:]))
        if self.did:
            lines.append("Was du zuletzt gemacht hast: " + ", ".join(self.did) + ".")
        mem = [m["text"] for m in self.ctl.prof.get("memory", [])][-6:]
        if mem:
            lines.append("Dein Gedächtnis:\n" + "\n".join(f"- {m}" for m in mem))
        screen = context_from(world, pet.pane or 0, max_chars=600) if world.ok else ""
        if screen:
            lines.append(f"Bildschirm-Auszug (nur zur Orientierung):\n{screen}")
        return "\n".join(lines) + "\n\nDein Plan als JSON:"

    # ------------------------------------------------------------ Ausführen (Brain, jeden Frame)
    def drive(self, dt, world):
        """Führt den aktuellen Schritt aus. True = das Hirn hat gerade die Kontrolle (das Brain würfelt
        dann keine eigenen Ziele)."""
        if self.step is None:
            if not self.plan:
                return False
            self.step = self.plan.popleft()
        st, pet = self.step, self.ctl.pet
        if not st.started:
            if not _ready(pet):
                st.waited += dt
                if st.waited > WAIT_READY:
                    self._finish("übersprungen")
                return False
            st.started = True
            if not self._start(st, world):
                self._finish("ging nicht")
                return False
            return True
        st.left -= dt
        if st.left <= 0:
            self._finish()
            return False
        return self._continue(st, world)

    def _finish(self, how=""):
        st = self.step
        if st is not None:
            self.did.append(st.verb + (f" ({how})" if how else ""))
            if pet_sits(self.ctl.pet) and st.verb in ("sitzen", "zuschauen", "hinlaufen", "zur_maus"):
                self.ctl.pet.timer = min(self.ctl.pet.timer, 1.0)    # Sitzen nicht ewig nachziehen
        self.step = None

    def _start(self, st, world):
        pet, brain = self.ctl.pet, self.ctl.brain
        v = st.verb
        if v in ("tanzen", "huepfen", "umschauen"):
            pet.perform(v)
            return True
        if v == "sitzen":
            pet.state, pet.timer = "sit", st.dauer
            return True
        if v == "schlafen":
            pet.perform("einschlafen")
            if pet.state == "sleep":
                pet.timer = st.dauer
            return pet.state == "sleep"
        if v == "zuschauen":
            if pet.pane is None:
                return False
            brain._look_at_newest(world)
            return True
        if v == "hinlaufen":
            return pet.go_to_word(st.ziel, world)
        if v == "fressen":
            if not brain.hungry:
                return False
            food = brain._find_food(world, prefer=st.ziel)
            if not food:
                return False
            brain.set_goal(("eat",) + food)
            return True
        if v == "verstecken":
            return brain.hide_somewhere(world)
        if v == "ausflug":
            if pet.energy < 40:
                return False
            pet.want_adventure = True
            return True
        if v == "zur_maus":
            cx = brain.cursor[0] if getattr(brain, "cursor", None) else pet.x
            sp = pet.support
            if sp is None:
                return False
            pet.walk_to(min(max(cx, sp.x0 + pet.px), sp.x1 - pet.px), run=1.3)
            return True
        if v == "erkunden":
            return True
        return False

    def _continue(self, st, world):
        """Während eines Schritts: nach dem Hinlaufen/-springen hinsetzen; Ziel-Schritte enden mit dem Ziel."""
        pet, brain = self.ctl.pet, self.ctl.brain
        v = st.verb
        if v == "erkunden":
            return False                              # freie Bewegung: das Brain darf würfeln
        if v == "fressen":
            if brain.goal is None:
                self._finish()
            return True
        if v in ("zuschauen", "hinlaufen", "zur_maus") and st.phase == 0 and pet.grounded \
                and pet.state == "idle" and not pet.busy:
            st.phase = 1
            pet.state, pet.timer = "sit", st.left    # angekommen: dableiben
        return True


EVENT_LABEL = {"done": "Claude ist fertig geworden", "start": "Claude hat angefangen zu arbeiten",
               "error": "Fehler", "success": "Erfolg", "attention": "Claude wartet auf eine Antwort",
               "commit": "Commit", "push": "Push", "pause_ende": "dein Mensch ist aus der Pause zurück"}


def _ready(pet):
    return (pet.placed and pet.grounded and not pet.busy
            and pet.state in ("idle", "walk", "sit", "happy"))


def pet_sits(pet):
    return pet.state == "sit"


def _where(pet):
    if pet.state == "hidden":
        return "in einem Tab versteckt"
    if pet.state == "sleep":
        return "am Schlafen"
    if pet.pane is None:
        return "draußen auf einem anderen Fenster"
    return {"sit": "sitzt im Terminal", "walk": "läuft im Terminal herum"}.get(pet.state, "im Terminal")


def _state(s):
    return {"working": "arbeitet", "idle": "wartet/fertig"}.get(s, "?")


def _short(name):
    name = name.lstrip("✳◐◓◑◒⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏·✢✶✻✽ ").strip()
    return mask(name)[:40]


def _ago(sec):
    return "gerade eben" if sec < 90 else f"vor {sec / 60:.0f} Min."

