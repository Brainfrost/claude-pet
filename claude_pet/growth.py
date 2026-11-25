"""Entwicklung des Pets: Erfahrung, Wachstum, Accessoires, Tricks, Bindung und Stimmung."""
import time

STAGES = [("baby", 0), ("jung", 400), ("erwachsen", 2500)]

# Accessoire -> (Kategorie, Schwelle, Beschreibung)
ACCESSORIES = {
    "helm": ("bash", 150, "Bauhelm – du arbeitest viel auf der Kommandozeile"),
    "brille": ("web", 25, "Brille – du recherchierst viel im Web"),
    "lupe": ("search", 60, "Lupe – du suchst und debuggst viel"),
}

TRICKS = {
    "doppelsprung": "Doppelsprung – springt höher und legt mitten in der Luft nach",
    "purzelbaum": "Purzelbaum – überschlägt sich manchmal beim Springen",
    "weitsprung": "Weitsprung – geht doppelt so oft auf Ausflüge zu anderen Fenstern",
}

BOND_TRICK = 40      # ab dieser Bindung: Purzelbaum


def ensure_defaults(prof):
    prof.setdefault("stats", {"cats": {}, "tools": 0, "prompts": 0, "sessions": 0})
    prof.setdefault("xp", 0)
    prof.setdefault("bond", 10.0)
    prof.setdefault("mood", 60.0)
    prof.setdefault("tricks", [])
    prof.setdefault("accessories", [])          # freigeschaltet
    prof.setdefault("accessories_off", [])      # vom Nutzer ausgeblendet
    prof.setdefault("last_seen", time.time())
    prof.setdefault("eaten", {"date": "", "today": 0, "total": 0})
    prof.setdefault("fetched", 0)
    prof.setdefault("last_greet", "")
    return prof


def count_eaten(prof, today):
    e = prof["eaten"]
    if e.get("date") != today:
        e["date"], e["today"] = today, 0
    e["today"] += 1
    e["total"] = e.get("total", 0) + 1
    return e["today"]


def worn(prof):
    return [a for a in prof.get("accessories", []) if a not in prof.get("accessories_off", [])]


def xp_of(stats):
    return stats.get("tools", 0) + 3 * stats.get("prompts", 0) + 10 * stats.get("sessions", 0)


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


def apply_stats(prof, d):
    """Neue Arbeit verbuchen. Gibt eine Liste von Meilensteinen zurück: (art, schlüssel)."""
    s = prof["stats"]
    for k in ("tools", "prompts", "sessions"):
        s[k] = s.get(k, 0) + d.get(k, 0)
    for cat, n in d.get("cats", {}).items():
        s["cats"][cat] = s["cats"].get(cat, 0) + n
    prof["xp"] = xp_of(s)
    return check(prof)


def check(prof):
    out = []
    st = stage_for(prof["xp"])
    order = [n for n, _ in STAGES]
    if order.index(st) > order.index(prof.get("stage", "baby")):
        prof["stage"] = st
        out.append(("stage", st))
    for acc, (cat, need, _) in ACCESSORIES.items():
        if acc not in prof["accessories"] and prof["stats"]["cats"].get(cat, 0) >= need:
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


# Auswirkungen von Interaktionen auf (Bindung, Stimmung), je Charakter
INTERACTION = {
    "stroke": {"*": (2.0, 6.0)},
    "poke": {"*": (0.5, 2.0), "faul": (0.3, -2.0)},
    "poke_sleep": {"*": (0.0, -3.0), "faul": (-0.5, -6.0)},
    "thrown": {"*": (-0.5, -3.0), "verspielt": (1.0, 6.0), "aengstlich": (-2.0, -10.0)},
    "cling": {"*": (1.0, 3.0)},
    "done": {"*": (0.0, 3.0)},
    "success": {"*": (0.0, 3.0)},
    "error": {"*": (0.0, -3.0), "aengstlich": (0.0, -7.0), "faul": (0.0, -1.0)},
}


def interact(prof, kind):
    tab = INTERACTION.get(kind)
    if not tab:
        return []
    db, dm = tab.get(prof.get("personality"), tab["*"])
    prof["bond"] = max(0.0, min(100.0, prof["bond"] + db))
    prof["mood"] = max(0.0, min(100.0, prof["mood"] + dm))
    return check(prof)


def drift(prof, dt):
    """Stimmung pendelt sich langsam bei 60 ein; Zeit zusammen stärkt die Bindung ein wenig."""
    m = prof["mood"]
    prof["mood"] = m + (60.0 - m) * min(1.0, dt / 600.0)
    prof["bond"] = min(100.0, prof["bond"] + dt / 3600.0 * 0.5)


def absence(prof):
    """Beim Start: lange Abwesenheit kostet etwas Bindung (max. 15)."""
    days = max(0.0, (time.time() - prof.get("last_seen", time.time())) / 86400.0)
    if days > 1:
        prof["bond"] = max(0.0, prof["bond"] - min(15.0, 2.0 * days))


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
