"""Dauerhafter Steckbrief des Pets: welche Figur, welcher Charakter, welcher Name, welche Entwicklung.

Ein Pet entsteht nur durch Adoption (siehe adoption.py) und bleibt danach für immer dasselbe.
"""
import json
import os
import random
from datetime import datetime

from . import creatures

DIR = os.path.join(os.environ.get("LOCALAPPDATA", "."), "claude-pet")
PATH = os.path.join(DIR, "profile.json")
ARCHIVE = os.path.join(DIR, "archiv")

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


def roll_personality(cid, rnd=random):
    all_p = creatures.personalities()
    fav = FAVORITES.get(cid)
    if fav in all_p and rnd.random() < FAVORITE_CHANCE:
        return fav
    return rnd.choice([p for p in all_p if p != fav] or all_p)


def load():
    """Der Steckbrief des adoptierten Pets – oder None, wenn noch keines adoptiert wurde."""
    try:
        with open(PATH, encoding="utf-8") as f:
            prof = json.load(f)
    except (OSError, ValueError):
        return None
    return prof if prof.get("creature") in creatures.creature_ids() else None


def adopt(creature_id, personality, name):
    """Neues Pet anlegen (einmalig, bei der Adoption)."""
    prof = {
        "creature": creature_id,
        "name": name.strip() or creatures.get(creature_id)["name"],
        "personality": personality,
        "stage": "baby",
        "accessories": [],
        "born": datetime.now().isoformat(timespec="seconds"),
        "adopted": True,
    }
    save(prof)
    return prof


def save(prof):
    os.makedirs(DIR, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(prof, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)


def archive(reason="verabschiedet"):
    """Das aktuelle Pet ins Archiv legen (nicht löschen). Danach ist eine neue Adoption möglich."""
    prof = load()
    if prof is None:
        return None
    os.makedirs(ARCHIVE, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = os.path.join(ARCHIVE, f"{stamp}-{prof.get('name', 'pet')}.json")
    prof["archived"] = {"at": datetime.now().isoformat(timespec="seconds"), "reason": reason}
    with open(target, "w", encoding="utf-8") as f:
        json.dump(prof, f, ensure_ascii=False, indent=2)
    os.remove(PATH)
    return target
