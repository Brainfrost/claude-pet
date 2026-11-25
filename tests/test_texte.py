"""Texte: Eingabefeld ausblenden, Platzhalter, persönliche Sprüche, Wort unter der Maus."""
import json
import random

from claude_pet import creatures
from claude_pet.brain import Brain
from claude_pet.pet import Pet
from claude_pet.speech import content_rows, fill, parse_lines
from claude_pet.world import World
from conftest import CELL_W, LINE_H, make_snapshot

SEP = "─" * 60


def test_input_box_is_never_read():
    rows = ["● Claude hat geantwortet", "  mit mehreren Zeilen", "", SEP,
            "❯ das wir uns die tex", "  zweite Zeile der Eingabe", SEP,
            "  ⏵⏵ auto mode on (shift+tab to cycle)"]
    assert content_rows(rows) == rows[:3]
    assert content_rows(["nur Text", "ohne Eingabefeld"]) == ["nur Text", "ohne Eingabefeld"]


def test_fill_only_touches_known_placeholders():
    assert fill("Mampf, {word}! ({today} heute) { }", word="Bug", today=3) == "Mampf, Bug! (3 heute) { }"


def test_parse_lines_validates_kinds_and_placeholders():
    from claude_pet.personas import LINE_KINDS
    data = {k: [f"Spruch {k} 1", f"Spruch {k} 2"] for k in LINE_KINDS}
    data["eat"] = ["Lecker {word}! ({today})", "ohne Platzhalter"]
    data["break"] = ["Schon {hours}!", "x" * 200]
    out = parse_lines("Hier: " + json.dumps(data, ensure_ascii=False))
    assert out["eat"] == ["Lecker {word}! ({today})"], "Sprüche ohne {word} fliegen raus"
    assert out["break"] == ["Schon {hours}!"], "zu lange fliegen raus"
    assert parse_lines("kein json") is None
    assert parse_lines(json.dumps({"poke": ["a"]})) is None, "fast alles fehlt"


def test_word_under_cursor():
    w = World()
    w.update(make_snapshot(["", "  hier ist ein Bug drin"]))
    y = 40 + 1 * LINE_H + LINE_H / 2
    word, cx, plat = w.word_at(2 * CELL_W + 15 * CELL_W + 3, y)
    assert word == "Bug" and plat.row == 1 and abs(cx - (15 + 1.5) * CELL_W) < 1e-6
    assert w.word_at(5, y) is None, "Leerraum"


def test_hovering_food_sends_pet_to_eat_it():
    random.seed(1)
    w = World()
    snap = make_snapshot(["x" * 60] * 4 + ["  hier ist ein Bug drin"] + ["x" * 60] * 4, rows=20)
    pet = Pet(creatures.get("geist"), "jung", "verspielt")
    brain = Brain(pet, "verspielt")
    for _ in range(180):
        w.update(snap)
        pet.on_world(w)
        pet.step(1 / 60, w, lambda x: 1100, (-2000, -100, 4000, 1200), (0, 0))
    word, x, plat = w.word_at(2 * CELL_W + 15 * CELL_W + 3, 40 + 4 * LINE_H + LINE_H / 2)
    assert brain.hovered(word, x, plat, w)
    assert brain.goal and brain.goal[0] == "eat" and brain.goal[-1] == "Bug"


def test_pet_is_sated_after_eating_and_mouse_has_priority():
    random.seed(2)
    w = World()
    snap = make_snapshot(["x" * 60] * 4 + ["  hier ist ein Bug drin, noch ein Bug"] + ["x" * 60] * 4, rows=20)
    pet = Pet(creatures.get("geist"), "jung", "verspielt")
    brain = Brain(pet, "verspielt")
    eaten = []
    brain.on_ate = lambda word, p, s: eaten.append(word)
    far = (5000, 5000)
    for f in range(60 * 30):
        if f % 4 == 0:
            w.update(snap)
            brain.on_world(w)
            pet.on_world(w)
        if f == 120:
            brain.eat_t = 0
        brain.food_urge = True                       # ständig neues Futter im Text
        brain.tick(1 / 60, w, far)
        pet.step(1 / 60, w, lambda x: 1100, (-2000, -100, 4000, 1200), far)
    assert len(eaten) == 1, f"satt nach dem ersten Wort, nicht {len(eaten)}"
    # satt: auf Futter zeigen löst kein neues Fressen aus
    word, x, plat = w.word_at(2 * CELL_W + 15 * CELL_W + 3, 40 + 4 * LINE_H + LINE_H / 2)
    assert brain.hovered(word, x, plat, w) and not brain.goal
    # Weg zum Futter wird für die Maus abgebrochen
    brain.sated_t = 0
    brain.set_goal(("eat", plat.text, plat.row, 15, "Bug"))
    pet.busy = True
    word2, x2, plat2 = w.word_at(2 * CELL_W + 3, 40 + 4 * LINE_H + LINE_H / 2)
    assert brain.hovered(word2, x2, plat2, w), "Maus hat Vorrang vor dem Weg zum Futter"
