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
    pet.grace = 0                                   # ohne Schonzeit nach dem Start
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
    for _ in range(120):
        pet.on_world(w)
        pet.step(1 / 60, w, floor, VB, (0, 0))
    while not pet.grounded:
        pet.step(1 / 60, w, floor, VB, (0, 0))
    pet.energy = 5
    pet.state, pet.timer = "idle", 0
    pet._decide(w)
    assert pet.state == "sleep" and pet.timer > 60, "erschöpft -> Nickerchen"
    # müde: will deutlich seltener springen als frisch (400 Entscheidungen je Zustand)
    middle = next(q for q in w.platforms if q.row == 4)

    def jump_rate(energy):
        random.seed(11)
        n = 0
        for _ in range(400):
            pet.x, pet.y, pet.support, pet.pane = (middle.x0 + middle.x1) / 2, middle.y, middle, 0
            pet.state, pet.energy, pet.want_adventure = "idle", energy, False
            pet._decide(w)
            n += pet.state == "jump"
        return n / 400
    assert jump_rate(30) < jump_rate(95) * 0.5


def test_pet_coming_out_of_a_tab_jumps_into_the_text_and_does_not_stick_to_the_top():
    """Regression: aus dem Tab gekommen, blieb es oben auf der ersten Zeile stehen."""
    A = [("● " if i % 3 == 0 else "  ") + "Text in Tab A " * 4 for i in range(26)]
    B = [("● " if i % 3 == 0 else "  ") + "Inhalt von Tab B " * 4 for i in range(26)]
    top_share = []
    for seed in range(4):
        random.seed(seed)
        w = World()
        pet = Pet(creatures.get("geist"), "jung", "verspielt")
        brain = Brain(pet, "verspielt")
        active = [0]
        on_top, samples = 0, 0
        for f in range(60 * 75):
            if f % 4 == 0:
                w.update(make_snapshot(A if active[0] == 0 else B, active=active[0], n_tabs=2, rows=30))
                brain.on_world(w)
                pet.on_world(w)
            if f == 60 * 5:
                assert brain.hide_somewhere(w)
            if f == 60 * 15:
                active[0] = 1                            # du folgst ihm in Tab B
            brain.tick(1 / 60, w, (5000, 5000))
            pet.step(1 / 60, w, floor, VB, (5000, 5000))
            if f >= 60 * 18 and pet.grounded:
                samples += 1
                on_top += pet.support.row <= 1
        top_share.append(on_top / max(1, samples))
    assert sum(top_share) / len(top_share) < 0.35, top_share


def test_messenger_pet_flies_to_cursor_and_clings():
    w = World()
    w.update(make_snapshot(["x" * 70] * 8, rows=20))
    pet = Pet(creatures.get("geist"), "jung", "verspielt")
    pet.placed, pet.state = True, "hidden"                 # sogar aus einem versteckten Tab heraus
    pet.x, pet.y = 100, 100
    assert pet.come_to_user()
    cursor = (2600, 500)                                   # auf einem anderen Bildschirm
    for _ in range(60 * 4):
        pet.step(1 / 60, w, floor, VB, cursor)
        if pet.state == "cling":
            break
    assert pet.state == "cling" and abs(pet.x - cursor[0]) < 1


def test_neustart_macht_nicht_muede():
    """Regression: Nach jedem Start fällt das Pet ins Fenster und springt heim – das kostete bis zu
    14 Energie. Viele Neustarts (Updates, Tests) machten es dauerhaft müde."""
    w = _world()
    pet = Pet(creatures.get("schleim"), "jung", "verspielt")
    pet.energy = 50.0
    for _ in range(5):
        pet._hop(-300)
        pet.leap_to(pet.x + 400, pet.y)
    assert pet.energy == 50.0, "Einzug gratis"
    for _ in range(int(16 * 60)):                    # Schonzeit vorbei
        pet.on_world(w)
        pet.step(1 / 60, w, floor, VB, (0, 0))
    before = pet.energy
    pet._hop(-300)
    assert pet.energy < before, "danach kostet Toben wieder"
