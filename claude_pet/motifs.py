"""Motiv-Wächter: erkennt, wenn ein Pet sich wiederholt (gleiches Wort, gleiches Bild, gleicher Satzanfang).

Haiku nimmt Charakter-Vorgaben gern sehr wörtlich und hält sich an einmal gefundene Bilder – ein
verspieltes Pet sah früher überall „Wettlauf“, ein Gespenst wackelt ständig mit dem Saum. Darum:
- live: vor jedem Spruch/Plan die zuletzt zu oft benutzten Motive mitgeben („lass sie weg“)
- fester Spruch-Satz: einmal prüfen und die betroffenen Sprüche gezielt neu schreiben lassen
"""
import re
from collections import Counter, defaultdict

# häufige Wörter, die kein Motiv sind
STOP = set("""
aber alle alles also auch auf aus bei beim bin bis bist dann das dass dein deine deinem deinen deiner dem den
der des die dies diese diesem diesen dieser dir doch dort du durch ein eine einem einen einer eines einfach
erst etwas euch für gar ganz gerade gleich gern gibt habe haben hast hat hier hin ich ihr im immer in ins ist
jetzt kann kein keine mach mache machen mal man mehr mein meine meinem meinen meiner mich mir mit muss nach
nicht nichts noch nun nur oder schon sehr sein seine sich sie sind so soll toll über um und uns unter viel vom
von vor war was weil wenn wer wie wieder wir wird wo zu zum zur zwei
""".split())
_WORD = re.compile(r"[A-Za-zÄÖÜäöüß]+")
_PLACEHOLDER = re.compile(r"\{[a-z_]+\}")

LIVE_WINDOW = 12        # so viele letzte Sprüche werden betrachtet
LIVE_MIN = 3            # Motiv in so vielen davon -> „zu oft“
SET_MIN = 4             # fester Satz: Motiv in so vielen Sprüchen -> neu schreiben
SET_OPENER_MIN = 3      # fester Satz: so viele gleiche Satzanfänge -> neu schreiben
# alte Stimme der verspielten Pets („siehst überall einen Wettlauf“): diese Sprüche gelten als betroffen
LEGACY = {"verspielt": re.compile(r"wett|schneller|renn|flitz", re.I)}


def _words(text):
    return [w.lower() for w in _WORD.findall(_PLACEHOLDER.sub(" ", text or ""))]


def stems(text):
    """Motiv-Stämme eines Satzes: inhaltliche Wörter, auf 5 Buchstaben gekürzt (wackle/wackelt …)."""
    return {w[:5] for w in _words(text) if len(w) >= 4 and w not in STOP}


def opener(text):
    """Erstes inhaltliches Wort (Satzanfang); „Ich“ & Co. zählen nicht – Ich-Form ist gewollt."""
    for w in _words(text)[:2]:
        if w not in STOP:
            return w
    return ""


def _surface(lines, stem):
    """Wie das Motiv tatsächlich geschrieben wurde (häufigste Form)."""
    c = Counter(w for l in lines for w in _WORD.findall(l) if w.lower()[:5] == stem and len(w) >= 4)
    return c.most_common(1)[0][0] if c else stem


def overused(lines, min_lines):
    """Motive, die in mindestens min_lines der Sätze vorkommen -> [Wort], häufigste zuerst."""
    count = Counter(s for l in lines for s in stems(l))
    hot = [s for s, n in count.most_common() if n >= min_lines]
    return [_surface(lines, s) for s in hot]


def avoid_hint(recent):
    """Für den nächsten Live-Spruch: zuletzt zu oft benutzte Motive und Satzanfänge (höchstens 6)."""
    recent = [r for r in list(recent)[-LIVE_WINDOW:] if r]
    words = overused(recent, LIVE_MIN)
    starts = [w for w, n in Counter(opener(r) for r in recent).items() if w and n >= LIVE_MIN]
    out = []
    for w in words + [s.capitalize() for s in starts]:
        if w.lower() not in (o.lower() for o in out):
            out.append(w)
    return out[:6]


SET_KEEP = 2            # so viele Sprüche dürfen ein gehäuftes Motiv behalten (es gehört ja zum Pet)


def offenders(line_set, personality=""):
    """Fester Spruch-Satz {anlass: [sprüche]} -> ([(anlass, index, spruch)], [zu vermeidende Wörter]).

    Gehäuft ist ein Motiv, das in ≥ SET_MIN verschiedenen Anlässen vorkommt (Wörter, die zum Anlass
    gehören – „zurück“ beim Ball und nach der Pause –, zählen so nicht), bzw. ein Satzanfang in
    ≥ SET_OPENER_MIN Sprüchen. Die ersten SET_KEEP Sprüche mit einem Motiv behalten es, die übrigen
    werden neu geschrieben. Bei verspielten Pets zusätzlich alle mit den Renn-Wörtern der alten Stimme."""
    flat = [(k, i, t) for k, v in (line_set or {}).items() for i, t in enumerate(v or []) if isinstance(t, str)]
    texts = [t for _, _, t in flat]
    kinds = defaultdict(set)
    for k, _, t in flat:
        for s in stems(t):
            kinds[s].add(k)
    hot = {s for s, ks in kinds.items() if len(ks) >= SET_MIN}
    starts = Counter(opener(t) for t in texts)
    hot_starts = {w for w, n in starts.items() if w and n >= SET_OPENER_MIN}
    legacy = LEGACY.get(personality)
    kept = Counter()
    picked, avoid = [], Counter()
    for k, i, t in flat:
        motifs_here = stems(t) & hot
        start_here = {opener(t)} & hot_starts
        is_legacy = bool(legacy and legacy.search(t))
        if not (motifs_here or start_here or is_legacy):
            continue
        if not is_legacy and not start_here and all(kept[s] < SET_KEEP for s in motifs_here):
            kept.update(motifs_here)                    # darf das Motiv behalten
            continue
        picked.append((k, i, t))
        avoid.update(_surface(texts, s) for s in motifs_here)
        avoid.update(_surface(texts, s[:5]) for s in start_here)
    words = [w for w, _ in avoid.most_common()]
    if legacy and any(legacy.search(t) for _, _, t in picked):
        words += [w for w in ("Wetten", "schneller", "Wettlauf", "Rennen") if w.lower() not in map(str.lower, words)]
    return picked, words[:10]


def accept_rewrite(old, new, avoid):
    """Taugt der neu geschriebene Spruch? Gleiche Platzhalter, kurz, keine der gemiedenen Wörter."""
    new = (new or "").strip().strip('"„“')
    if not new or len(new) > 90 or new == old:
        return None
    if sorted(_PLACEHOLDER.findall(old)) != sorted(_PLACEHOLDER.findall(new)):
        return None
    bad = {w.lower()[:5] for w in avoid}
    if stems(new) & bad or opener(new)[:5] in bad:
        return None
    return new
