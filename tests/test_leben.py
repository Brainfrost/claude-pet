"""Leben: Scrollen oben, Müdigkeit und Energie."""
import random

from claude_pet import creatures
from claude_pet.brain import Brain
from claude_pet.pet import Pet
from claude_pet.world import ROW_FLOOR, World
from conftest import make_snapshot

VB = (-2000, -100, 4000, 1200)


def floor(_x):
    return 1100


def test_pet_at_top_stays_on_text_when_lines_scroll_out_fast():
    """Regression: oben stehend und Zeile scrollt weg -> landete ganz unten am Pane-Boden."""
    random.seed(1)
    text = [f"Zeile {i} " + "x" * 60 for i in range(3000)]
    w = World()
    pet = Pet(creatures.get("geist"), "jung", "faul")
    w.update(make_snapshot(text[0:28], rows=30))
    pet.placed, pet.pane = True, 0
    top = next(p for p in w.platforms if p.row == 1)
    pet.x, pet.y, pet.support, pet.state, pet.timer = 300, top.y, top, "sit", 100
    off = 0
    for f in range(60 * 6):
        if f % 4 == 0:
            off += 5                                     # Claude schreibt schnell: 5 Zeilen pro Abfrage
            w.update(make_snapshot(text[off:off + 28], rows=30))
            pet.on_world(w)
        pet.step(1 / 60, w, floor, VB, (5000, 5000))
        assert not (pet.support is not None and pet.support.row == ROW_FLOOR), "rauschte bis zum Boden"
    assert pet.support is not None and pet.support.row <= 3, pet.support


def test_falling_pet_lands_on_lines_scrolling_past():
    text = [f"Zeile {i} " + "x" * 60 for i in range(3000)]
    w = World()
    pet = Pet(creatures.get("katze"), "jung", "neugierig")
    w.update(make_snapshot(text[0:28], rows=30))
    pet.placed, pet.pane = True, 0
    pet.x, pet.y = 300, 200
    pet._start_fall(0.0, 0.0)
    off = 0
    for f in range(60 * 3):
        if f % 4 == 0:
            off += 6
            w.update(make_snapshot(text[off:off + 28], rows=30))
            pet.on_world(w)
        pet.step(1 / 60, w, floor, VB, (5000, 5000))
        if pet.grounded:
            break
    assert pet.grounded and pet.support.row >= 0, "auf einer Textzeile gelandet, nicht am Boden"


def _world(lines=8):
    w = World()
    w.update(make_snapshot(["x" * 70] * lines, rows=20))
    return w


def test_jumping_costs_energy_and_rest_restores_it():
    w = _world()
    pet = Pet(creatures.get("schleim"), "jung", "verspielt")
    for _ in range(120):
        pet.on_world(w)
        pet.step(1 / 60, w, floor, VB, (0, 0))
    before = pet.energy
    for _ in range(10):
        pet._hop(-300)
    assert pet.energy < before - 10
    while not pet.grounded:                          # erst landen lassen
        pet.step(1 / 60, w, floor, VB, (0, 0))
    low = pet.energy
    pet.state, pet.timer = "sleep", 999
    for _ in range(60 * 30):
        pet.step(1 / 60, w, floor, VB, (0, 0))
    assert pet.energy > low + 15, "Schlafen lädt auf"


def test_exhausted_pet_takes_a_nap_and_tired_pet_barely_jumps():
    random.seed(4)
    w = _world()
    pet = Pet(creatures.get("schleim"), "jung", "verspielt")
    brain = Brain(pet, "verspielt")
    for _ in range(120):
        pet.on_world(w)
        pet.step(1 / 60, w, floor, VB, (0, 0))
    while not pet.grounded:
        pet.step(1 / 60, w, floor, VB, (0, 0))
    pet.energy = 5
    pet.state, pet.timer = "idle", 0
    pet._decide(w)
    assert pet.state == "sleep" and pet.timer > 60, "erschöpft -> Nickerchen"
    # müde: deutlich weniger Sprünge als frisch
    def jumps(energy):
        random.seed(9)
        pet.energy, pet.state, pet.timer = energy, "idle", 0
        n, prev = 0, None
        for f in range(60 * 120):
            pet.energy = energy                      # Energie für den Vergleich festhalten
            if f % 4 == 0:
                w.update(make_snapshot(["x" * 70] * 8, rows=20))
                brain.on_world(w)
                pet.on_world(w)
            brain.tick(1 / 60, w, (5000, 5000))
            pet.step(1 / 60, w, floor, VB, (5000, 5000))
            if pet.state == "jump" and prev != "jump":
                n += 1
            prev = pet.state
        return n
    assert jumps(30) < jumps(95) * 0.5
