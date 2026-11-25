"""Schatzkiste: Jedes gefressene Wort wandert in die Sammlung. Manche Wörter tauchen im Terminal selten auf –
die sind entsprechend wertvoll. Noch nicht gefundene Schätze stehen als „???“ in der Kiste."""
import re
from datetime import date

from .diary import esc

# Stufe -> (Anzeigename, Farbe, Wörter)
TIERS = [
    ("gewöhnlich", "#c9c3e6", ("bug", "todo", "error", "fehler", "fixme")),
    ("selten", "#4dabf7", ("warning", "deprecated", "undefined", "timeout", "hack", "workaround", "typo")),
    ("episch", "#c77dff", ("segfault", "deadlock", "panic", "overflow", "leak", "flaky", "regression")),
    ("legendär", "#f2b705", ("heisenbug", "teapot", "spaghetti", "gremlin")),
]
COLS = 3
RARITY = {w: i for i, (_, _, words) in enumerate(TIERS) for w in words}
# Plural-/Wortformen, die auf denselben Schatz zählen
_FORMS = {"bugs": "bug", "todos": "todo", "errors": "error", "warnings": "warning", "timeouts": "timeout",
          "hacks": "hack", "workarounds": "workaround", "typos": "typo", "leaks": "leak",
          "regressions": "regression", "gremlins": "gremlin", "heisenbugs": "heisenbug", "panics": "panic",
          "deadlocks": "deadlock", "overflows": "overflow", "segfaults": "segfault", "teapots": "teapot"}
FOOD = re.compile(r"\b(" + "|".join(sorted(set(RARITY) | set(_FORMS), key=len, reverse=True)) + r")\b", re.I)


def key(word):
    w = word.lower()
    return _FORMS.get(w, w)


def rarity(word):
    return RARITY.get(key(word), 0)


def add(prof, word, today=None):
    """Wort in die Sammlung legen. Gibt (schlüssel, stufe, neu) zurück."""
    box = prof.setdefault("treasure", {})
    k = key(word)
    entry = box.get(k)
    new = entry is None
    if new:
        entry = box[k] = {"n": 0, "first": (today or date.today()).isoformat()}
    entry["n"] += 1
    return k, RARITY.get(k, 0), new


def progress(prof):
    box = prof.get("treasure", {})
    return sum(1 for w in RARITY if w in box), len(RARITY)


def html(prof):
    box = prof.get("treasure", {})
    found, total = progress(prof)
    out = [f"<p class='sym'>{found} von {total} Schätzen gefunden · insgesamt "
           f"{sum(e['n'] for e in box.values())} Wörter gefressen</p>"]
    for stars, (name, color, words) in reversed(list(enumerate(TIERS, 1))):
        out.append(f"<h3 style='color:{color}'>{'★' * stars} {name}</h3>"
                   "<table width='100%' cellspacing='6' cellpadding='8'>")
        for i in range(0, len(words), COLS):
            out.append("<tr>")
            for w in words[i:i + COLS]:
                e = box.get(w)
                if e:
                    d = date.fromisoformat(e["first"])
                    out.append(f"<td width='33%' bgcolor='#262046'><b style='color:{color}'>{esc(w.upper())}</b>"
                               f"<br><span class='rar'>× {e['n']} · seit {d.day}.{d.month}.</span></td>")
                else:
                    out.append("<td width='33%' bgcolor='#1f1b38' style='color:#5a5480'>???<br>"
                               "<span class='rar'>&nbsp;</span></td>")
            out.append("<td></td>" * (COLS - len(words[i:i + COLS])) + "</tr>")
        out.append("</table>")
    return "\n".join(out)
