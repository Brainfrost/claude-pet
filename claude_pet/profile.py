"""Dauerhafter Steckbrief des Pets: welche Figur, welcher Charakter, welche Wachstumsstufe."""
import json
import os
import random
from datetime import datetime

from . import creatures

DIR = os.path.join(os.environ.get("LOCALAPPDATA", "."), "claude-pet")
PATH = os.path.join(DIR, "profile.json")

# Lieblingscharakter je Figur: wird mit FAVORITE_CHANCE gewählt, sonst einer der anderen.
FAVORITES = {
    "katze": "neugierig",
    "schleim": "verspielt",
    "krake": "aengstlich",
    "bit": "faul",
    "spatz": "aengstlich",
    "pilz": "faul",
    "axolotl": "verspielt",
    "klammer": "verspielt",
}
FAVORITE_CHANCE = 0.5


def roll_personality(cid):
    all_p = creatures.personalities()
    fav = FAVORITES.get(cid)
    if fav in all_p and random.random() < FAVORITE_CHANCE:
        return fav
    return random.choice([p for p in all_p if p != fav] or all_p)


def load():
    """Lädt den Steckbrief. Beim allerersten Start wird Figur und Charakter ausgewürfelt."""
    try:
        with open(PATH, encoding="utf-8") as f:
            prof = json.load(f)
        if prof.get("creature") in creatures.creature_ids():
            return prof
    except (OSError, ValueError):
        pass
    c = creatures.get(random.choice(creatures.creature_ids()))
    prof = {
        "creature": c["id"],
        "name": c["name"],
        "personality": roll_personality(c["id"]),
        "stage": "baby",
        "accessories": [],
        "born": datetime.now().isoformat(timespec="seconds"),
    }
    save(prof)
    return prof


def save(prof):
    os.makedirs(DIR, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(prof, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)


def reroll():
    try:
        os.remove(PATH)
    except OSError:
        pass
    return load()
