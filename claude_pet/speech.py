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

from . import motifs, personas
from .paths import data_dir

log = logging.getLogger(__name__)

BRAIN_DIR = data_dir("brain")

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
    "hover": "Dein Mensch zeigt gerade mit der Maus auf das Wort «{detail}». Reagiere darauf.",
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
    "lunch": {
        "faul": ["Mittag. Endlich ein guter Grund, nichts zu tun.", "Essen … und danach ein Nickerchen."],
        "neugierig": ["Mittagszeit! Was gibt's heute bei dir?", "Hunger! Und du? Schon was gegessen?"],
        "verspielt": ["Mampf-Alarm! Ab in die Mittagspause!", "Mittag! Wer zuerst beim Essen ist!"],
        "aengstlich": ["Ä-ähm, es ist Mittag … du solltest was essen, ja?", "Mittagspause? Bitte vergiss nicht zu essen."],
    },
    "evening": {
        "faul": ["Feierabend. Ich hab heute wirklich alles gegeben.", "Schon fünf. Ich bin müde für zwei."],
        "neugierig": ["Feierabend in Sicht! Was nimmst du dir für morgen vor?", "Schon so spät? Was war heute das Beste?"],
        "verspielt": ["Feierabend! Rennen wir zur Tür?", "Fünf Uhr! Zeit für Unfug!"],
        "aengstlich": ["Es ist schon spät … mach nicht zu lang, ja?", "Feierabend? Ich pass so lange auf alles auf."],
    },
    "weekend": {
        "faul": ["Wochenende naht. Zwei Tage Schlaf am Stück.", "Freitag. Mein Lieblingstag zum Nichtstun."],
        "neugierig": ["Fast Wochenende! Was hast du vor?", "Freitag! Was war diese Woche dein Highlight?"],
        "verspielt": ["WOCHENENDE IN SICHT! Freitagstänzchen!", "Freitag! Ich tanz schon mal vor."],
        "aengstlich": ["Bald Wochenende … ich werd dich vermissen.", "Freitag! Bitte erhol dich gut, ja?"],
    },
    "messenger": {
        "faul": ["„{tab}“ ist fertig. Ich bin extra aufgestanden.", "Psst … „{tab}“ wartet auf dich."],
        "neugierig": ["„{tab}“ ist fertig – was ist rausgekommen? Schau mal!", "Komm mit! „{tab}“ ist fertig!"],
        "verspielt": ["Hier bin ich! „{tab}“ ist fertig – ab ins Terminal!", "Tadaa, „{tab}“ ist durch!"],
        "aengstlich": ["Ä-ähm, „{tab}“ ist fertig … ich wollte nur Bescheid sagen.", "„{tab}“ ist fertig – nicht böse sein, dass ich störe!"],
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
    "treasure": {
        "faul": ["Oh. Ein {rarity}er Schatz: {word}. Das war die Mühe wert.", "{word}! Selten. Fast so selten wie ich wach."],
        "neugierig": ["Wow, ein {rarity}es {word}! Ab in die Schatzkiste!", "{word}?! So eins hatte ich noch nie!"],
        "verspielt": ["JACKPOT! Ein {rarity}es {word}!", "{word}! {word}! Neuer Schatz! Juhuu!"],
        "aengstlich": ["E-ein {rarity}es {word}… ich hab's tatsächlich erwischt!", "{word}… ganz neu für mich. Ich heb's gut auf."],
    },
    "hunt_start": {
        "faul": ["Käferjagd? Na gut. Aber nur 30 Sekunden.", "Ich jag mit. Langsam."],
        "neugierig": ["Käfer! Überall Käfer! Los geht's!", "Wer fängt mehr? Ich will's wissen!"],
        "verspielt": ["JAGD! Die gehören alle mir!", "Auf die Plätze, fertig, KÄFER!"],
        "aengstlich": ["K-Käfer?! Okay … ich bin mutig. Glaub ich.", "Ich versuch's … die krabbeln so!"],
    },
    "hunt_won": {
        "faul": ["{pet} zu {du}. Hätte nicht gedacht, dass ich so schnell bin.", "Gewonnen. Jetzt brauch ich ein Nickerchen."],
        "neugierig": ["{pet} zu {du} für mich! Revanche?", "Ha, {pet} Käfer! Ich kenn jetzt ihre Tricks."],
        "verspielt": ["SIEG! {pet} zu {du}! Nochmal, nochmal!", "{pet} zu {du}! Ich bin der Käferkönig!"],
        "aengstlich": ["Ich hab gewonnen?! {pet} zu {du}! Wow!", "{pet} zu {du} … ich war echt mutig, oder?"],
    },
    "hunt_lost": {
        "faul": ["{du} zu {pet}. Ich hab dich gewinnen lassen.", "Du warst schneller. War mir zu anstrengend."],
        "neugierig": ["{du} zu {pet} – wie klickst du so schnell?!", "Respekt! {du} Käfer. Nächstes Mal krieg ich dich."],
        "verspielt": ["Nööö! {du} zu {pet}! REVANCHE!", "{du} zu {pet}… du Käferschreck!"],
        "aengstlich": ["{du} zu {pet} … du bist richtig gut darin.", "Danke, dass du die meisten erwischt hast."],
    },
    "hunt_draw": {
        "faul": ["{du} zu {pet}. Unentschieden. Perfekt, keiner muss sich anstrengen.", "Gleichstand. Passt."],
        "neugierig": ["Unentschieden, {du} zu {pet}! Wer gewinnt das Stechen?", "{du} zu {pet} – exakt gleich!"],
        "verspielt": ["{du} zu {pet}! Gleichstand! Nochmal!", "Unentschieden?! Das schreit nach Revanche!"],
        "aengstlich": ["{du} zu {pet} – wir sind ein gutes Team!", "Gleichstand … das ist doch schön, oder?"],
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
    "tired": {
        "faul": ["Gähn… ich such mir ein ruhiges Plätzchen.", "So. Genug für heute. Bis später."],
        "neugierig": ["Ich bin so müde… ich ruh mich kurz aus.", "Augen fallen zu… nur ein kleines Nickerchen!"],
        "verspielt": ["Akku leer! Ich verkriech mich kurz und tank auf.", "Puh, ausgetobt. Kurzes Nickerchen!"],
        "aengstlich": ["Ich bin müde… ich such mir eine stille Ecke.", "Darf ich mich kurz ausruhen? Ganz leise."],
    },
    "rested": {
        "faul": ["Mh. Ausgeschlafen. Fast.", "Bin wieder da. Langsam."],
        "neugierig": ["Ausgeschlafen! Was hab ich verpasst?", "Wieder fit! Zeig mal, was du gemacht hast."],
        "verspielt": ["Akku voll! Wer spielt mit mir?", "Ausgeschlafen und bereit für Quatsch!"],
        "aengstlich": ["Ich bin wieder da… war alles ruhig?", "Ausgeruht. Ich bleib jetzt in deiner Nähe."],
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


_PROMPT = re.compile(r"^\s*❯")
_SEPARATOR = re.compile(r"^[\s─━═]{10,}$")


def content_rows(rows):
    """Zeilen ohne das Eingabefeld von Claude Code: alles ab der Trennlinie über der Eingabezeile (❯)
    wird abgeschnitten – das Pet liest nie mit, was du gerade tippst."""
    for i in range(len(rows) - 1, max(-1, len(rows) - 16), -1):
        if _PROMPT.match(rows[i]):
            cut = i
            for j in range(i - 1, max(-1, i - 4), -1):
                if _SEPARATOR.match(rows[j]):
                    cut = j
                    break
            return rows[:cut]
    return rows


def fill(line, **values):
    """Platzhalter {word}/{today}/{hours} ersetzen, ohne über andere Klammern zu stolpern."""
    for k, v in values.items():
        line = line.replace("{" + k + "}", str(v))
    return line


_TOOL = re.compile(r"^● ([A-Za-z_][\w.\-]*)\(")
_PROSE = re.compile(r"^● (.+)")
_USER = re.compile(r"^❯ (\S.*)")
_RESULT = re.compile(r"^\s+⎿\s*(.*)")
_STATUS = re.compile(r"^[✻✽✶✢✳·*]\s*\S+(…| for )|^\s*(Allowed by|Running…|Tip:|… \+\d+ lines)")
_CODEISH = re.compile(r"^\s*\d+\s*[+\-]?\s|[{};]\s*$|^\s*(def |class |import |from |return |if |for |const |let )")


def digest(lines, max_chars=900):
    """Terminal-Text für Haiku aufbereiten: was Claude geschrieben hat (ohne Code/Diffs), welche
    Werkzeuge es benutzt hat, wichtige Ergebnisse und deine letzte Nachricht – statt eines wirren
    Rohtext-Ausschnitts, aus dem Haiku sich irgendein Fragment greift."""
    prose, tools, results, user = [], [], [], []
    mode = None
    for raw in lines:
        line = raw.rstrip()
        if not line.strip() or _STATUS.search(line) or _CHROME.search(line):
            continue
        m = _TOOL.match(line)
        if m:
            tools.append(m.group(1))
            mode = "tool"
            continue
        m = _USER.match(line)
        if m:
            user = [m.group(1).strip()]
            mode = "user"
            continue
        m = _PROSE.match(line)
        if m:
            prose.append(m.group(1).strip())
            mode = "prose"
            continue
        m = _RESULT.match(line)
        if m:
            text = m.group(1).strip()
            if text and not _STATUS.search(text):
                results.append(text)
            mode = "result"
            continue
        if line.startswith("  ") and not _CODEISH.search(line):
            if mode == "prose":
                prose.append(line.strip())
            elif mode == "user":
                user.append(line.strip())
    parts = []
    if user:
        parts.append("Dein Mensch hat geschrieben: " + " ".join(user)[:240])
    if prose:
        parts.append("Claude hat geschrieben: " + " ".join(prose)[-(max_chars - 300):])
    if tools:
        counts = {}
        for t in tools:
            counts[t] = counts.get(t, 0) + 1
        parts.append("Claude hat benutzt: " + ", ".join(f"{t} ×{n}" if n > 1 else t for t, n in counts.items()))
    if results:
        parts.append("Ergebnisse: " + " | ".join(r[:90] for r in results[-3:]))
    return mask("\n".join(parts))[:max_chars]


def is_content(line):
    s = line.strip()
    return len(s) >= 3 and not _CHROME.search(line)


def context_from(world, pane=0, max_chars=700):
    """Was gerade im Terminal zu sehen ist – aufbereitet, ohne Eingabefeld."""
    if not world.ok or not world.snap.panes:
        return ""
    pane = min(pane or 0, len(world.snap.panes) - 1)
    return digest(content_rows([t.rstrip() for _, t in world.snap.panes[pane].lines]), max_chars)


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


_REQUIRED = {"eat": ("{word}",), "break": ("{hours}",)}


def parse_lines(out):
    """Haiku-Antwort für den Spruch-Satz prüfen: nur bekannte Anlässe, kurze Texte, nötige Platzhalter."""
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    result = {}
    for kind in personas.LINE_KINDS:
        items = data.get(kind)
        if not isinstance(items, list):
            continue
        need = _REQUIRED.get(kind, ())
        good = [s.strip() for s in items if isinstance(s, str) and 0 < len(s.strip()) <= 90
                and all(n in s for n in need)]
        if good:
            result[kind] = good[:4]
    return result if len(result) >= len(personas.LINE_KINDS) - 2 else None


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
        self.recent = deque(maxlen=8)          # zuletzt gesagt – damit es sich nicht wiederholt
        self.motif_hist = deque(maxlen=motifs.LIVE_WINDOW)   # für den Motiv-Wächter (Sprüche + Gedanken)
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
        own = (self.prof.get("lines") or {}).get(kind)          # persönlicher Spruch-Satz des Pets
        lines = own or CANNED.get(kind, {}).get(self.prof["personality"])
        if not lines:
            return
        if not force and (now - self.last_canned < 25 or random.random() > 0.4):
            return
        self.last_canned = now
        fresh = [l for l in lines if fill(l, **values) not in self.recent] or lines
        text = fill(random.choice(fresh), **values)
        self.recent.append(text)
        self.said.emit(text)

    def on_event(self, kind, world, pane=0, detail="", new_text="", force=False):
        """Bei einem Anlass vielleicht reagieren (Haiku). True, wenn angefragt."""
        if self.muted or self.factor <= 0:
            return False
        if not force and random.random() > min(1.0, self.rates["chance"] * self.factor):
            return False
        if not self._budget_ok():
            return False
        return self._ask(kind, context_from(world, pane), mask(detail)[:160],
                         digest(new_text.splitlines()) if new_text else "")

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

    def invent_lines(self, prof, callback):
        """Haiku schreibt einmalig den persönlichen Spruch-Satz des Pets; callback(dict) bei Erfolg."""
        if not self.exe:
            return False
        system, user = personas.lines_prompt(prof)
        self._run(user, system=system, on_out=lambda out: self._lines_done(out, callback), count=False)
        return True

    @staticmethod
    def _lines_done(out, callback):
        lines = parse_lines(out)
        if lines:
            callback(lines)
        else:
            log.warning("Spruch-Satz nicht verwertbar: %s", out[:200])

    def rewrite_lines(self, prof, items, avoid, callback, on_fail=None):
        """Motiv-Wächter: einzelne Sprüche des festen Satzes neu schreiben lassen.
        callback({(anlass, index): neuer_spruch}) mit nur den brauchbaren Ergebnissen."""
        if not self.exe or not items:
            return False
        system, user = personas.rewrite_prompt(prof, items, avoid)

        def done(out):
            m = re.search(r"\{.*\}", out or "", re.S)
            try:
                data = json.loads(m.group(0)) if m else {}
            except ValueError:
                data = {}
            new = {}
            for n, (k, i, old) in enumerate(items, 1):
                text = motifs.accept_rewrite(old, str(data.get(str(n), "")), avoid)
                if text:
                    new[(k, i)] = text
            callback(new)

        self._run(user, system=system, on_out=done, count=False, on_fail=on_fail)
        return True

    def note_said(self, text):
        """Für den Motiv-Wächter merken, was das Pet gesagt/gedacht hat."""
        if text:
            self.motif_hist.append(text)

    def avoid_hint(self, topic=""):
        """Zuletzt zu oft benutzte Motive – ohne die, um die es gerade wirklich geht (z.B. „Hook“ bei
        einem weiteren Hook-Fehler)."""
        on_topic = motifs.stems(topic)
        return [w for w in motifs.avoid_hint(self.motif_hist) if w.lower()[:5] not in on_topic]

    def invent_persona(self, prof, callback):
        """Haiku erfindet eine Persönlichkeit und ruft callback(text) auf. False ohne claude-CLI."""
        if not self.exe:
            return False
        self._run(personas.persona_prompt(prof), system="Du bist kreativ und schreibst knapp.",
                  on_out=lambda out: callback(out.strip()[:600]), count=False)
        return True

    def write(self, system, user, callback, on_fail=None):
        """Längerer Text (Tagebuch, Rückblick) – zählt nicht ins Sprech-Budget. False ohne claude-CLI."""
        if not self.exe:
            return False
        self._run(user, system=system, on_out=callback, count=False, on_fail=on_fail)
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
            parts.append(f"Was gerade neu passiert ist:\n{new_text}")
        if ctx and ctx != new_text:
            parts.append(f"Was sonst im Terminal steht (nur zur Orientierung):\n{ctx}")
        avoid = self.avoid_hint(f"{detail}\n{new_text}")
        if avoid:
            parts.append("Diese Wörter und Bilder hattest du zuletzt zu oft – lass sie diesmal ganz weg: "
                         + ", ".join(avoid))
        if self.recent:
            parts.append("Deine letzten Sprüche (nichts davon wiederholen):\n"
                         + "\n".join(f"- {r}" for r in self.recent))
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
            say = say.strip('"„“»«')
            self.recent.append(say)
            self.note_said(say)
            self.said.emit(say)
        if act != "nichts":
            self.acted.emit(act, target)

    def _run(self, user, system, on_out, count, on_fail=None):
        args = ["-p", "--model", "haiku", "--setting-sources", "", "--no-session-persistence",
                "--strict-mcp-config", "--tools", "", "--disable-slash-commands",
                "--system-prompt", system]
        proc = QProcess(self)
        proc.setProcessEnvironment(_clean_env())
        proc.setWorkingDirectory(BRAIN_DIR)
        proc.finished.connect(lambda code, status, pr=proc: self._done(pr, code, on_out, count, on_fail))
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

    def _done(self, proc, code, on_out, count, on_fail=None):
        if count:
            self.busy = False
        out = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace").strip()
        err = bytes(proc.readAllStandardError()).decode("utf-8", "replace").strip()
        proc.deleteLater()
        if code != 0 or not out:
            log.warning("Haiku ohne Antwort (code %s): %s", code, err[:200])
            if on_fail:
                on_fail()
            return
        try:
            on_out(out)
        except Exception:
            log.exception("Haiku-Antwort nicht verarbeitbar")
