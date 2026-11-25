"""Entwicklung des Pets: Wachstum, Accessoires, Tricks, Bindung und Stimmung.

Maßstab fürs Wachstum sind **aktive Minuten** mit Claude Code (jede Minute mit Aktivität zählt einmal,
höchstens 8 Stunden pro Tag) – robust gegen Automatisierungs-Tage mit tausenden Tool-Aufrufen und fair
zwischen Leuten mit unterschiedlichem Arbeitsstil. Kalibriert an echten Daten: ~4 aktive Stunden pro
Arbeitstag -> jung nach ~1 Woche, erwachsen nach ~6 Wochen.
"""
import time
from datetime import date

DAY_CAP_MIN = 8 * 60
STAGES = [("baby", 0), ("jung", 20 * 60), ("erwachsen", 120 * 60)]      # aktive Minuten

# Accessoire -> (Kategorien, Schwelle, Beschreibung). Richtwerte pro Arbeitstag: ~300 Bash,
# ~65 Web, ~55 Lesen/Suchen -> jeweils ein bis drei Wochen.
ACCESSORIES = {
    "helm": (("bash",), 3000, "Bauhelm – du arbeitest viel auf der Kommandozeile"),
    "brille": (("web",), 600, "Brille – du recherchierst viel im Web"),
    "lupe": (("search", "read"), 800, "Lupe – du liest und durchsuchst viel Code"),
}

TRICKS = {
    "doppelsprung": "Doppelsprung – springt höher und legt mitten in der Luft nach",
    "purzelbaum": "Purzelbaum – überschlägt sich manchmal beim Springen",
    "weitsprung": "Weitsprung – geht doppelt so oft auf Ausflüge zu anderen Fenstern",
}

BOND_TRICK = 40              # ab dieser Bindung: Purzelbaum
BOND_DAY_CAP = 8.0           # so viel Bindung kann man pro Tag durch Interaktionen gewinnen
BOND_PER_ACTIVE_HOUR = 0.5   # gemeinsame Arbeitszeit stärkt die Bindung ein wenig


def ensure_defaults(prof):
    prof.setdefault("stats", {})
    st = prof["stats"]
    st.setdefault("cats", {})
    for k in ("tools", "prompts", "sessions", "active_min"):
        st.setdefault(k, 0)
    st.setdefault("days", {})                    # Datum -> aktive Minuten (für die Tagesgrenze)
    prof.setdefault("xp", 0)
    prof.setdefault("stage", "baby")
    prof.setdefault("bond", 10.0)
    prof.setdefault("bond_today", {"date": "", "gained": 0.0})
    prof.setdefault("mood", 60.0)
    prof.setdefault("tricks", [])
    prof.setdefault("accessories", [])          # freigeschaltet
    prof.setdefault("accessories_off", [])      # vom Nutzer ausgeblendet
    prof.setdefault("last_seen", time.time())
    prof.setdefault("eaten", {"date": "", "today": 0, "total": 0})
    prof.setdefault("fetched", 0)
    prof.setdefault("last_greet", "")
    return prof


def worn(prof):
    return [a for a in prof.get("accessories", []) if a not in prof.get("accessories_off", [])]


def stage_for(xp):
    st = STAGES[0][0]
    for name, need in STAGES:
        if xp >= need:
            st = name
    return st


def next_stage(xp):
    for name, need in STAGES:
        if xp < need:
            return name, need
    return None, None


def hours(minutes):
    return f"{minutes / 60:.1f}".replace(".", ",").replace(",0", "") + " h"


def apply_stats(prof, d):
    """Neue Arbeit verbuchen. d: {"cats", "tools", "prompts", "sessions", "minutes": {datum: n}}.
    Gibt Meilensteine zurück: [(art, schlüssel)]."""
    s = prof["stats"]
    for k in ("tools", "prompts", "sessions"):
        s[k] = s.get(k, 0) + d.get(k, 0)
    for cat, n in d.get("cats", {}).items():
        s["cats"][cat] = s["cats"].get(cat, 0) + n
    gained = 0
    for day, n in d.get("minutes", {}).items():
        before = s["days"].get(day, 0)
        after = min(DAY_CAP_MIN, before + n)
        s["days"][day] = after
        gained += after - before
    if len(s["days"]) > 40:                      # nur die letzten Wochen aufheben
        for day in sorted(s["days"])[:-40]:
            del s["days"][day]
    s["active_min"] = s.get("active_min", 0) + gained
    prof["xp"] = s["active_min"]
    prof["bond"] = min(100.0, prof.get("bond", 10.0) + gained / 60.0 * BOND_PER_ACTIVE_HOUR)
    return check(prof)


def check(prof):
    out = []
    st = stage_for(prof["xp"])
    order = [n for n, _ in STAGES]
    if order.index(st) > order.index(prof.get("stage", "baby")):
        prof["stage"] = st
        out.append(("stage", st))
    cats = prof["stats"]["cats"]
    for acc, (keys, need, _) in ACCESSORIES.items():
        if acc not in prof["accessories"] and sum(cats.get(k, 0) for k in keys) >= need:
            prof["accessories"].append(acc)
            out.append(("accessory", acc))
    tricks = prof["tricks"]
    if "doppelsprung" not in tricks and order.index(prof["stage"]) >= 1:
        tricks.append("doppelsprung")
        out.append(("trick", "doppelsprung"))
    if "weitsprung" not in tricks and prof["stage"] == "erwachsen":
        tricks.append("weitsprung")
        out.append(("trick", "weitsprung"))
    if "purzelbaum" not in tricks and prof["bond"] >= BOND_TRICK:
        tricks.append("purzelbaum")
        out.append(("trick", "purzelbaum"))
    return out


def accessory_progress(prof, acc):
    keys, need, _ = ACCESSORIES[acc]
    return sum(prof["stats"]["cats"].get(k, 0) for k in keys), need


# Auswirkungen von Interaktionen auf (Bindung, Stimmung), je Charakter. Bindung wächst langsam
# (Tagesgrenze), Stimmung reagiert sofort.
INTERACTION = {
    "stroke": {"*": (0.6, 6.0)},
    "poke": {"*": (0.15, 2.0), "faul": (0.1, -2.0)},
    "poke_sleep": {"*": (0.0, -3.0), "faul": (-0.3, -6.0)},
    "thrown": {"*": (-0.4, -3.0), "verspielt": (0.3, 6.0), "aengstlich": (-1.5, -10.0)},
    "cling": {"*": (0.4, 3.0)},
    "done": {"*": (0.0, 3.0)},
    "success": {"*": (0.0, 3.0)},
    "error": {"*": (0.0, -3.0), "aengstlich": (0.0, -7.0), "faul": (0.0, -1.0)},
}


def interact(prof, kind, today=None):
    tab = INTERACTION.get(kind)
    if not tab:
        return []
    db, dm = tab.get(prof.get("personality"), tab["*"])
    if db > 0:
        bt = prof.setdefault("bond_today", {"date": "", "gained": 0.0})
        today = today or date.today().isoformat()
        if bt.get("date") != today:
            bt["date"], bt["gained"] = today, 0.0
        db = max(0.0, min(db, BOND_DAY_CAP - bt["gained"]))
        bt["gained"] += db
    prof["bond"] = max(0.0, min(100.0, prof["bond"] + db))
    prof["mood"] = max(0.0, min(100.0, prof["mood"] + dm))
    return check(prof)


def drift(prof, dt):
    """Die Stimmung pendelt sich langsam bei 60 ein."""
    m = prof["mood"]
    prof["mood"] = m + (60.0 - m) * min(1.0, dt / 600.0)


def absence(prof):
    """Beim Start: lange Abwesenheit kostet etwas Bindung (max. 15)."""
    days = max(0.0, (time.time() - prof.get("last_seen", time.time())) / 86400.0)
    if days > 1:
        prof["bond"] = max(0.0, prof["bond"] - min(15.0, 2.0 * days))


def count_eaten(prof, today):
    e = prof["eaten"]
    if e.get("date") != today:
        e["date"], e["today"] = today, 0
    e["today"] += 1
    e["total"] = e.get("total", 0) + 1
    return e["today"]


def describe(prof):
    """Kurztext für Haiku: wie es dem Pet geht und wie gut ihr euch kennt."""
    b, m = prof.get("bond", 10), prof.get("mood", 60)
    bond = ("ihr kennt euch noch kaum" if b < 20 else "ihr werdet langsam Freunde" if b < 50
            else "ihr seid gute Freunde" if b < 80 else "ihr seid allerbeste Freunde")
    mood = ("du bist gerade schlecht gelaunt" if m < 30 else "deine Laune ist eher mäßig" if m < 50
            else "du bist gut gelaunt" if m < 80 else "du bist bestens gelaunt")
    stage = {"baby": "Du bist noch ein Baby (gerade geschlüpft).", "jung": "Du bist ein junges Pet.",
             "erwachsen": "Du bist ausgewachsen."}.get(prof.get("stage", "baby"), "")
    return f"{stage} Zu deinem Menschen: {bond}; {mood}."
