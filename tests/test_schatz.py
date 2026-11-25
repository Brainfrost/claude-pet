"""Schatzkiste: Seltenheiten, Sammlung, Futter-Auswahl."""
import random
from datetime import date

from claude_pet import creatures, treasure
from claude_pet.brain import FOOD, Brain
from claude_pet.pet import Pet
from claude_pet.speech import CANNED, fill
from claude_pet.world import World
from conftest import make_snapshot


def test_food_regex_knows_all_treasures_and_forms():
    for w in ("bug", "Bugs", "TODO", "fehler", "warnings", "Segfault", "heisenbug", "Teapot"):
        assert FOOD.fullmatch(w), w
    for w in ("debug", "nullpointer", "hackathon", "terror"):
        assert not FOOD.fullmatch(w), w
    assert treasure.rarity("Warnings") == 1 and treasure.rarity("PANIC") == 2 and treasure.rarity("teapot") == 3
    assert treasure.rarity("todos") == 0


def test_collection_counts_and_reports_new_finds():
    prof = {}
    assert treasure.add(prof, "Bugs", date(2026, 11, 25)) == ("bug", 0, True)
    assert treasure.add(prof, "bug") == ("bug", 0, False)
    assert treasure.add(prof, "Deadlock") == ("deadlock", 2, True)
    assert prof["treasure"]["bug"]["n"] == 2 and prof["treasure"]["bug"]["first"] == "2026-11-25"
    assert treasure.progress(prof) == (2, len(treasure.RARITY))
    html = treasure.html(prof)
    assert "DEADLOCK" in html and "???" in html and "legendär" in html


def test_pet_prefers_the_rare_word():
    random.seed(2)
    w = World()
    lines = ["x" * 60] * 6 + ["  hier steht ein TODO im Code"] + ["x" * 60] * 4 + ["  plötzlich: DEADLOCK erkannt"]
    w.update(make_snapshot(lines + ["x" * 60] * 6, rows=24))
    pet = Pet(creatures.get("katze"), "jung", "neugierig")
    pet.placed, pet.pane = True, 0
    todo = next(p for p in w.platforms if "TODO" in p.text)
    pet.x, pet.y, pet.support = todo.x0 + 150, todo.y, todo
    food = Brain(pet, "neugierig")._find_food(w)
    assert food and food[3] == "DEADLOCK"


def test_treasure_lines_fill_grammatically():
    for pers, lines in CANNED["treasure"].items():
        for line in lines:
            for tier in ("selten", "episch", "legendär"):
                out = fill(line, word="PANIC", rarity=tier)
                assert "{" not in out
    assert fill(CANNED["treasure"]["neugierig"][0], word="PANIC", rarity="episch").startswith("Wow, ein episches PANIC")
