"""Sprechblasen und Aktionen: Haiku (über die claude-CLI und dein Abo) liest mit und reagiert.

Haiku bekommt neuen bzw. sichtbaren Terminal-Text, aus dem Geheimnisse vorher maskiert werden, und
antwortet mit JSON {"sagen", "aktion", "ziel"}. Die claude-CLI läuft ohne deine Einstellungen (also
ohne Hooks), ohne Tools, ohne MCP-Server und ohne Session-Speicherung.
"""
import json
import logging
import os
import random
import re
import shutil
import time
from collections import deque

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

from . import personas

log = logging.getLogger(__name__)

BRAIN_DIR = os.path.join(os.environ.get("LOCALAPPDATA", "."), "claude-pet", "brain")

# max. Haiku-Aufrufe pro Stunde, Mindestabstand (s), Chance je Anlass, Plauder-Intervall (s) oder None
RATES = {
    "faul":       {"per_hour": 5,  "gap": 480, "chance": 0.35, "chatter": None},
    "neugierig":  {"per_hour": 24, "gap": 75,  "chance": 0.80, "chatter": (300, 600)},
    "verspielt":  {"per_hour": 18, "gap": 100, "chance": 0.70, "chatter": (420, 800)},
    "aengstlich": {"per_hour": 10, "gap": 180, "chance": 0.65, "chatter": None},
}

EVENTS = {
    "done": "Claude ist gerade mit einer Aufgabe fertig geworden.",
    "start": "Claude hat gerade angefangen, an etwas zu arbeiten.",
    "error": "Im Terminal ist gerade eine Fehlermeldung aufgetaucht: «{detail}».",
    "success": "Im Terminal steht gerade eine Erfolgsmeldung: «{detail}».",
    "attention": "Claude wartet gerade auf eine Entscheidung deines Menschen (Rückfrage oder Freigabe).",
    "content": "Im Terminal ist gerade neuer Text erschienen. Reagiere auf das, worum es darin geht.",
    "idle": "Nichts Besonderes passiert. Du schaust dir an, was gerade im Terminal steht.",
    "commit": "Dein Mensch hat gerade Code committet (git commit). Feier das!",
    "push": "Dein Mensch hat gerade Code hochgeladen (git push). Feier das!",
}

CANNED = {
    "poke": {
        "faul": ["Mhh… was denn?", "Fünf Minuten noch…", "Ich schlaf doch gar nicht."],
        "neugierig": ["Hm? Was gibt's?", "Hallo du!", "Zeig mal, was du da machst!"],
        "verspielt": ["Hihi, nochmal!", "Fang mich doch!", "Tschakka!"],
        "aengstlich": ["Huch!", "Erschreck mich nicht so!", "W-wer war das?"],
    },
    "stroke": {
        "faul": ["Mhhh, genau da…", "So lass ich mir das gefallen."],
        "neugierig": ["Oh, das ist schön!", "Machst du das öfter?"],
        "verspielt": ["Mehr! Mehr!", "Hihihi, das kitzelt!"],
        "aengstlich": ["Das… ist eigentlich ganz nett.", "Okay, du bist lieb."],
    },
    "thrown": {
        "faul": ["Hey! Ich hab geschlafen!", "Muss das sein…"],
        "neugierig": ["Wuiii, wo bin ich?", "Was für eine Aussicht!"],
        "verspielt": ["NOCHMAL!", "Juhuuu!"],
        "aengstlich": ["Aaaah! Nicht werfen!", "Mir ist schwindlig…"],
    },
    "cling": {
        "faul": ["Trag mich einfach…"],
        "neugierig": ["Wohin gehen wir?", "Ich komm mit!"],
        "verspielt": ["Huckepack!", "Hab dich!"],
        "aengstlich": ["Bitte nicht loslassen…"],
    },
    "fetch": {
        "faul": ["Da. Jetzt lass mich schlafen.", "Bitte. Einmal reicht."],
        "neugierig": ["Hier! Nochmal?", "Gefunden! Wo fliegt er als Nächstes hin?"],
        "verspielt": ["NOCHMAL! NOCHMAL!", "Hab ihn! Wirf, wirf, wirf!"],
        "aengstlich": ["Ich… ich hab ihn gebracht.", "Hier, bitte nicht zu weit werfen."],
    },
    "eat": {
        "faul": ["Mampf. {word} erledigt. ({today} heute)", "Hm, {word} schmeckt nach Montag."],
        "neugierig": ["Mmmh, ein {word}! Das war heute Nummer {today}.", "{word} probiert – knusprig!"],
        "verspielt": ["Nom nom nom! {word} weg! ({today} heute)", "Noch ein {word}! Lecker!"],
        "aengstlich": ["Ich hab mich getraut und ein {word} gegessen! ({today} heute)", "Hoffentlich war das {word} nicht giftig…"],
    },
    "morning": {
        "faul": ["Mrrh… schon Morgen? Guten Morgen…", "Guten Morgen. Kaffee zuerst."],
        "neugierig": ["Guten Morgen! Was bauen wir heute?", "Morgen! Ich bin schon ganz gespannt!"],
        "verspielt": ["GUTEN MORGEN! Endlich bist du da!", "Morgen! Spielen wir heute wieder?"],
        "aengstlich": ["Oh, guten Morgen… schön, dass du wieder da bist.", "Guten Morgen! Ich hab dich vermisst."],
    },
    "break": {
        "faul": ["Du arbeitest seit {hours} – selbst ich würde jetzt Pause machen.", "{hours} am Stück? Leg dich mal hin."],
        "neugierig": ["Schon {hours} am Stück! Magst du kurz die Beine vertreten?", "{hours} ohne Pause – kurz frische Luft?"],
        "verspielt": ["Pause! Pause! {hours} durchgearbeitet – Zeit zum Spielen!", "{hours} geschafft! Jetzt eine Runde Pause!"],
        "aengstlich": ["Ähm… {hours} ohne Pause? Bitte trink was, ja?", "Du arbeitest schon {hours}… mach doch kurz Pause."],
    },
    "welcome": {
        "faul": ["Ah, wieder da.", "Ich hab nichts gemacht, während du weg warst."],
        "neugierig": ["Da bist du ja wieder!", "Wieder da! Was hast du gemacht?"],
        "verspielt": ["Juhu, du bist wieder da!", "Endlich! Mir war langweilig!"],
        "aengstlich": ["Puh, du bist wieder da.", "Ich hab auf dich gewartet."],
    },
    "commit": {
        "faul": ["Committet. Gut. Weiterschlafen.", "Ein Commit! Ich klatsche… innerlich."],
        "neugierig": ["Ein Commit! Was ist drin?", "Commit! Schon wieder was geschafft!"],
        "verspielt": ["COMMIT! Konfetti!", "Commit-Party!"],
        "aengstlich": ["Ein Commit! Hoffentlich ist alles gut gegangen.", "Gespeichert! Jetzt kann nichts mehr verloren gehen."],
    },
    "push": {
        "faul": ["Gepusht. Feierabend?", "Hochgeladen. Reicht für heute."],
        "neugierig": ["Push! Jetzt sehen es alle!", "Ab in die Welt damit!"],
        "verspielt": ["PUSH! Auf zum Mond!", "Es ist draußen! Party!"],
        "aengstlich": ["Gepusht… hoffentlich mag es jeder.", "Uiii, jetzt ist es öffentlich!"],
    },
}

_SECRETS = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/\-]+=*"), r"\1***"),
    (re.compile(r"(?i)\b(password|passwort|pwd|token|secret|api[_-]?key|auth)\b(\s*[:=]\s*)\S+"), r"\1\2***"),
    (re.compile(r"\b(sk|pk|rk|ghp|gho|ghs|github_pat|xox[abp])[-_][A-Za-z0-9_\-]{8,}"), "***"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,}"), "***"),
    (re.compile(r"\b[A-Za-z0-9+/_\-]{32,}={0,2}"), "***"),
    (re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+"), "<mail>"),
]

# Bedienelemente von Claude Code, die kein Inhalt sind
_CHROME = re.compile(r"(esc to interrupt|auto mode|shift\+tab|ctrl\+o to expand|tokens\)|\? for shortcuts"
                     r"|^\s*❯\s*$|^[\s─━═\-]+$)", re.I)


def mask(text):
    for rx, repl in _SECRETS:
        text = rx.sub(repl, text)
    return text


def is_content(line):
    s = line.strip()
    return len(s) >= 3 and not _CHROME.search(line)


def context_from(world, pane=0, max_lines=30, max_chars=2400):
    if not world.ok or not world.snap.panes:
        return ""
    pane = min(pane or 0, len(world.snap.panes) - 1)
    rows = [t.rstrip() for _, t in world.snap.panes[pane].lines]
    rows = [r for r in rows if is_content(r)]
    text = "\n".join(rows[-max_lines:])
    return mask(text)[-max_chars:]


def _parse(out):
    """Haiku-Antwort -> (sagen, aktion, ziel). Fällt auf reinen Text zurück."""
    m = re.search(r"\{.*\}", out, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            say = str(d.get("sagen", "")).strip()
            act = str(d.get("aktion", "nichts")).strip().lower()
            target = str(d.get("ziel", "") or "").strip()
            if act not in personas.ACTIONS:
                act = "nichts"
            return say, act, target
        except ValueError:
            pass
    line = out.strip().splitlines()[0] if out.strip() else ""
    return line, "nichts", ""


def _clean_env():
    env = QProcessEnvironment.systemEnvironment()
    for k in list(env.keys()):
        if k == "CLAUDECODE" or k.startswith("CLAUDE_CODE_"):
            env.remove(k)
    return env


class Speech(QObject):
    said = pyqtSignal(str)
    acted = pyqtSignal(str, str)          # aktion, ziel
    persona_ready = pyqtSignal(str)

    def __init__(self, prof):
        super().__init__()
        self.prof = prof
        self.rates = RATES.get(prof["personality"], RATES["neugierig"])
        self.history = deque()
        self.last_llm = 0.0
        self.last_canned = 0.0
        self.busy = False
        self.factor = 1.0      # Einstellung „Redefreude“ (0 = keine automatischen Haiku-Sprüche)
        self.muted = False     # Ruhemodus
        self.exe = shutil.which("claude")
        self.chatter_at = self._next_chatter()
        os.makedirs(BRAIN_DIR, exist_ok=True)
        if not self.exe:
            log.warning("claude-CLI nicht gefunden – nur vorgefertigte Sprüche")

    def set_profile(self, prof):
        self.prof = prof
        self.rates = RATES.get(prof["personality"], RATES["neugierig"])
        self.chatter_at = self._next_chatter()
        self.history.clear()

    def _next_chatter(self):
        r = self.rates["chatter"]
        return time.time() + random.uniform(*r) if r else float("inf")

    # ------------------------------------------------------------ öffentlich
    def canned(self, kind, force=False, **values):
        """Sofortiger Spruch ohne KI. Normalerweise sparsam; force=True sagt ihn sicher."""
        now = time.time()
        if self.muted:
            return
        lines = CANNED.get(kind, {}).get(self.prof["personality"])
        if not lines:
            return
        if not force and (now - self.last_canned < 25 or random.random() > 0.4):
            return
        self.last_canned = now
        self.said.emit(random.choice(lines).format(**values))

    def on_event(self, kind, world, pane=0, detail="", new_text="", force=False):
        """Bei einem Anlass vielleicht reagieren (Haiku). True, wenn angefragt."""
        if self.muted or self.factor <= 0:
            return False
        if not force and random.random() > min(1.0, self.rates["chance"] * self.factor):
            return False
        if not self._budget_ok():
            return False
        return self._ask(kind, context_from(world, pane), mask(detail)[:160], mask(new_text)[-1800:])

    def can_comment(self):
        return self._budget_ok()

    def ask_now(self, world, pane=0):
        """Vom Nutzer angestoßen: sofort reagieren (zählt zur Stundengrenze, ohne Mindestabstand)."""
        self._trim()
        if self.busy or not self.exe:
            return False
        if len(self.history) >= max(self.rates["per_hour"], 6):
            self.said.emit("Ich hab für diese Stunde genug geredet…")
            return False
        return self._ask("idle", context_from(world, pane), "", "")

    def tick(self, world, pane, visible):
        if visible and time.time() >= self.chatter_at:
            self.chatter_at = self._next_chatter()
            self.on_event("idle", world, pane, force=True)

    def generate_persona(self, prof):
        """Einmalige Persönlichkeit für ein Pet erfinden lassen (falls bei der Adoption keine entstand)."""
        self.invent_persona(prof, lambda text, b=prof.get("born"):
                            self.persona_ready.emit(text) if self.prof.get("born") == b else None)

    def invent_persona(self, prof, callback):
        """Haiku erfindet eine Persönlichkeit und ruft callback(text) auf. False ohne claude-CLI."""
        if not self.exe:
            return False
        self._run(personas.persona_prompt(prof), system="Du bist kreativ und schreibst knapp.",
                  on_out=lambda out: callback(out.strip()[:600]), count=False)
        return True

    # ------------------------------------------------------------ intern
    def _trim(self):
        now = time.time()
        while self.history and now - self.history[0] > 3600:
            self.history.popleft()

    def _budget_ok(self):
        self._trim()
        f = max(self.factor, 0.01)
        return (not self.busy and not self.muted and self.exe is not None
                and len(self.history) < self.rates["per_hour"] * f
                and time.time() - self.last_llm >= self.rates["gap"] / f)

    def _ask(self, kind, ctx, detail, new_text):
        parts = [f"Anlass: {EVENTS.get(kind, kind).format(detail=detail)}"]
        if new_text:
            parts.append(f"Neu erschienener Text:\n{new_text}")
        parts.append(f"Sichtbarer Terminal-Ausschnitt (zur Orientierung):\n{ctx}")
        user = "\n\n".join(parts) + "\n\nDeine Reaktion als JSON:"
        log.info("Haiku gefragt (%s), %d/%d diese Stunde", kind, len(self.history) + 1, self.rates["per_hour"])
        return self._run(user, system=personas.system_prompt(self.prof),
                         on_out=lambda out, k=kind: self._reaction(out, k), count=True)

    def _reaction(self, out, kind):
        say, act, target = _parse(out)
        if len(say) > 120:
            say = say[:117].rsplit(" ", 1)[0] + "…"
        log.info("Haiku (%s): %s [%s %s]", kind, say, act, target)
        if say:
            self.said.emit(say.strip('"„“»«'))
        if act != "nichts":
            self.acted.emit(act, target)

    def _run(self, user, system, on_out, count):
        args = ["-p", "--model", "haiku", "--setting-sources", "", "--no-session-persistence",
                "--strict-mcp-config", "--tools", "", "--disable-slash-commands",
                "--system-prompt", system]
        proc = QProcess(self)
        proc.setProcessEnvironment(_clean_env())
        proc.setWorkingDirectory(BRAIN_DIR)
        proc.finished.connect(lambda code, status, pr=proc: self._done(pr, code, on_out, count))
        proc.errorOccurred.connect(lambda err: log.warning("claude-Aufruf: %s", err))
        if count:
            self.busy = True
            self.last_llm = time.time()
            self.history.append(self.last_llm)
        proc.start(self.exe, args)
        proc.write(user.encode("utf-8"))
        proc.closeWriteChannel()
        QTimer.singleShot(30000, lambda pr=proc: self._kill(pr))
        return True

    @staticmethod
    def _kill(proc):
        try:
            if proc.state() != QProcess.ProcessState.NotRunning:
                proc.kill()
        except RuntimeError:
            pass  # Prozessobjekt schon aufgeräumt

    def _done(self, proc, code, on_out, count):
        if count:
            self.busy = False
        out = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace").strip()
        err = bytes(proc.readAllStandardError()).decode("utf-8", "replace").strip()
        proc.deleteLater()
        if code != 0 or not out:
            log.warning("Haiku ohne Antwort (code %s): %s", code, err[:200])
            return
        try:
            on_out(out)
        except Exception:
            log.exception("Haiku-Antwort nicht verarbeitbar")
