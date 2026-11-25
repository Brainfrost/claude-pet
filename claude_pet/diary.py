"""Tagebuch: Das Pet zählt mit, was am Tag passiert. Abends (oder für vergessene Tage am nächsten Morgen)
schreibt Haiku daraus einen kurzen Eintrag in der Stimme des Pets, am Wochenende einen Wochenrückblick.

Gespeichert wird in %LOCALAPPDATA%\\claude-pet\\tagebuch.json, getrennt vom Steckbrief.
"""
import json
import logging
import os
from datetime import date, datetime, timedelta

from . import profile

log = logging.getLogger(__name__)

PATH = os.path.join(profile.DIR, "tagebuch.json")
KEEP_DAYS = 120
EVENING = (18, 0)              # ab dann schreibt das Pet den Eintrag für heute
MIN_ACTIVE = 20                # so viele aktive Minuten braucht ein Tag, damit er einen Eintrag bekommt
WEEK_DAY = (4, (16, 0))        # Freitag ab 16 Uhr: Wochenrückblick für die laufende Woche
WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")

# Zähler: Schlüssel -> (Beschriftung für Haiku, kurzes Symbol für die Anzeige)
COUNTERS = {
    "minutes": ("Minuten gemeinsam mit Claude gearbeitet", "⏱"),
    "done": ("Mal ist Claude mit einer Aufgabe fertig geworden", "✔"),
    "errors": ("Fehlermeldungen im Terminal", "⚠"),
    "commits": ("Commits", "◆"),
    "pushes": ("Pushes", "▲"),
    "eaten": ("Wörter gefressen", "🍪"),
    "balls": ("Mal Ball gespielt", "●"),
    "strokes": ("Mal gestreichelt worden", "♥"),
    "pokes": ("Mal angestupst worden", "☝"),
    "naps": ("Nickerchen gemacht", "z"),
    "messenger": ("Mal als Bote den Menschen geholt", "✉"),
    "bugs": ("Käfer bei der Bug-Jagd erwischt", "🐞"),
}


def day_label(day):
    d = date.fromisoformat(day)
    return f"{WEEKDAYS[d.weekday()]}, {d.day}.{d.month}.{d.year}"


def week_key(d):
    """Montag der Woche als ISO-Datum."""
    return (d - timedelta(days=d.weekday())).isoformat()


def week_label(key):
    mo = date.fromisoformat(key)
    so = mo + timedelta(days=6)
    return f"Woche vom {mo.day}.{mo.month}. bis {so.day}.{so.month}.{so.year}"


class Diary:
    def __init__(self, path=PATH):
        self.path = path
        self.data = {"days": {}, "entries": {}, "weeks": {}}
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            for k in self.data:
                self.data[k].update(loaded.get(k, {}))
        except (OSError, ValueError):
            pass
        self.dirty = False
        self.failed = set()            # in dieser Sitzung gescheiterte Einträge (nicht dauernd neu fragen)

    # ------------------------------------------------------------ zählen
    def _day(self, day=None):
        return self.data["days"].setdefault(day or date.today().isoformat(), {})

    def count(self, key, n=1, day=None):
        d = self._day(day)
        d[key] = d.get(key, 0) + n
        self.dirty = True

    def set_minutes(self, day, minutes):
        d = self._day(day)
        if d.get("minutes") != minutes:
            d["minutes"] = minutes
            self.dirty = True

    def add_word(self, word, day=None):
        words = self._day(day).setdefault("words", [])
        if word not in words and len(words) < 8:
            words.append(word)
            self.dirty = True

    def save(self):
        if not self.dirty:
            return
        cutoff = (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
        for k in ("days", "entries"):
            for day in [d for d in self.data[k] if d < cutoff]:
                del self.data[k][day]
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
            self.dirty = False
        except OSError:
            log.exception("Tagebuch nicht gespeichert")

    # ------------------------------------------------------------ was fehlt noch?
    def worth_writing(self, day):
        d = self.data["days"].get(day, {})
        return d.get("minutes", 0) >= MIN_ACTIVE or sum(v for k, v in d.items()
                                                        if k not in ("minutes", "words")) >= 8

    def due_entry(self, now=None):
        """Tag, für den jetzt ein Eintrag fällig ist (ältester zuerst) – oder None."""
        now = now or datetime.now()
        today = now.date().isoformat()
        week_ago = (now.date() - timedelta(days=7)).isoformat()
        for day in sorted(self.data["days"]):
            if day < week_ago or day in self.data["entries"] or day in self.failed:
                continue
            if day == today and (now.hour, now.minute) < EVENING:
                continue
            if day > today or not self.worth_writing(day):
                continue
            return day
        return None

    def due_week(self, now=None):
        """Woche, für die ein Rückblick fällig ist: die letzte (wenn noch keiner da ist) oder ab Freitag
        16 Uhr die laufende. Nur, wenn es mindestens zwei Einträge gibt."""
        now = now or datetime.now()
        this = week_key(now.date())
        last = week_key(now.date() - timedelta(days=7))
        candidates = [last]
        if (now.weekday(), (now.hour, now.minute)) >= (WEEK_DAY[0], WEEK_DAY[1]):
            candidates.append(this)
        for key in candidates:
            if key in self.data["weeks"] or ("w" + key) in self.failed:
                continue
            if len(self.week_entries(key)) >= 2:
                return key
        return None

    def week_entries(self, key):
        mo = date.fromisoformat(key)
        days = [(mo + timedelta(days=i)).isoformat() for i in range(7)]
        return [(d, self.data["entries"][d]) for d in days if d in self.data["entries"]]

    def week_totals(self, key):
        mo = date.fromisoformat(key)
        tot = {}
        for i in range(7):
            for k, v in self.data["days"].get((mo + timedelta(days=i)).isoformat(), {}).items():
                if k != "words":
                    tot[k] = tot.get(k, 0) + v
        return tot

    # ------------------------------------------------------------ Texte
    def facts(self, day):
        """Was an dem Tag los war, als Stichpunkte für Haiku (nur Zahlen > 0)."""
        d = self.data["days"].get(day, {})
        out = []
        for k, (label, _) in COUNTERS.items():
            v = d.get(k, 0)
            if not v:
                continue
            if k == "minutes":
                out.append(f"- {hours_text(v)} gemeinsam mit Claude gearbeitet")
            else:
                out.append(f"- {v} {label}")
        if d.get("words"):
            out.append("- gefressene Wörter waren u.a.: " + ", ".join(d["words"][:6]))
        return "\n".join(out)

    def summary(self, counts):
        """Kurze Symbolzeile für die Anzeige, z.B. '⏱ 3,5 h · ✔ 12 · 🍪 4'."""
        parts = []
        for k, (_, sym) in COUNTERS.items():
            v = counts.get(k, 0)
            if v:
                parts.append(f"{sym} {hours_text(v, short=True)}" if k == "minutes" else f"{sym} {v}")
        return " · ".join(parts)

    def set_entry(self, day, text):
        self.data["entries"][day] = text
        self.dirty = True
        self.save()

    def set_week(self, key, text):
        self.data["weeks"][key] = text
        self.dirty = True
        self.save()

    def html(self, name):
        """Das ganze Tagebuch als HTML für das Fenster (neueste zuerst)."""
        e, w = self.data["entries"], self.data["weeks"]
        if not e and not w:
            return (f"<p style='color:#8f86c9'>Noch leer. {esc(name)} schreibt abends ab "
                    f"{EVENING[0]} Uhr, wenn ihr zusammen gearbeitet habt.</p>")
        # Rückblick direkt über dem letzten Tag seiner Woche
        items = [(d, "day") for d in e] + [((self.week_entries(k) or [(k, "")])[-1][0] + "~", k) for k in w]
        out = []
        for sort_key, kind in sorted(items, reverse=True):
            if kind == "day":
                day = sort_key
                sym = self.summary(self.data["days"].get(day, {}))
                out.append(f"<h3>{day_label(day)}</h3><p>{esc(e[day])}</p>"
                           f"<p class='sym'>{esc(sym)}</p>")
            else:
                sym = self.summary(self.week_totals(kind))
                out.append("<table width='100%' cellpadding='10' bgcolor='#262046'><tr><td>"
                           f"<p class='wh'>★ Wochenrückblick · {week_label(kind)}</p>"
                           f"<p>{esc(w[kind])}</p><p class='sym'>{esc(sym)}</p></td></tr></table>")
        return "\n".join(out)


def hours_text(minutes, short=False):
    if minutes < 60:
        return f"{minutes} min" if short else f"{minutes} Minuten"
    h = f"{minutes / 60:.1f}".replace(".", ",").replace(",0", "")
    return f"{h} h" if short else f"{h} Stunden"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\n", "<br>"))


def clean(text, limit=900):
    """Haiku-Antwort aufräumen: Markdown, Anführungszeichen und Überschriften weg."""
    lines = [ln.strip().lstrip("#").strip() for ln in text.strip().splitlines()]
    lines = [ln for ln in lines if ln and not (len(ln) < 50 and ln.endswith(":") or
                                               ln.lower().startswith(("tagebucheintrag", "wochenrückblick"))
                                               and len(ln) < 50)]
    t = "\n".join(lines).replace("**", "").replace("__", "").strip().strip('"„“').strip()
    return t[:limit]
