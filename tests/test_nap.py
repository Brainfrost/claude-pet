"""Nickerchen: müde -> Bescheid sagen, ruhigen Schlafplatz suchen, schlafen, ausgeschlafen zurück."""
import random

from claude_pet import brain as B, creatures
from claude_pet.brain import Brain
from claude_pet.pet import Pet
from claude_pet.world import World
from conftest import make_snapshot

VB = (-2000, -100, 4000, 1200)


def floor(_x):
    return 1100


def _setup(snap, energy=20.0):
    random.seed(7)
    w = World()
    w.update(snap)
    pet = Pet(creatures.get("geist"), "jung", "verspielt")
    pet.grace = 0
    br = Brain(pet, "verspielt")
    said = []
    br.on_nap = said.append
    for _ in range(240):                                  # landen lassen (noch fit)
        pet.on_world(w)
        pet.step(1 / 60, w, floor, VB, (0, 0))
    pet.energy = energy
    return w, pet, br, said


def _run(w, pet, br, seconds, cursor=(0, 0)):
    for _ in range(int(seconds * 60)):
        br.tick(1 / 60, w, cursor)
        pet.on_world(w)
        pet.step(1 / 60, w, floor, VB, cursor)


def test_muede_verkriecht_sich_im_freien_tab_und_kommt_ausgeschlafen_zurueck():
    lines = ["x" * 70] * 12
    snap = make_snapshot(lines, rows=20, n_tabs=3, active=0, working=(1,))   # Tab 1 arbeitet, Tab 2 ist frei
    w, pet, br, said = _setup(snap)
    _run(w, pet, br, 0.5)
    assert said == ["tired"] and br.nap and br.nap["mode"] == "tab"
    _run(w, pet, br, 6)
    assert pet.state == "hidden" and pet.napping and br.nap["phase"] == "sleep"
    assert br._find(w, br.home) == 2, "im freien Tab – nie in einem, in dem Claude arbeitet"
    e = pet.energy
    _run(w, pet, br, 10)
    assert pet.energy > e + 5, "versteckt schlafen lädt auf"
    _run(w, pet, br, 120)
    assert said == ["tired", "rested"] and br.nap is None and not pet.napping
    assert pet.state != "hidden" and br._find(w, br.home) == 0, "zurück in deinem Tab"


def test_ohne_freien_tab_ruhige_stelle_weit_weg_von_der_maus():
    lines = ["x" * 70] * 14
    snap = make_snapshot(lines, rows=20, n_tabs=1, active=0)                  # wie VS Code: kein anderer Tab
    w, pet, br, said = _setup(snap)
    cursor = (1100, 1000)                                                     # Maus rechts unten
    pet.x = 900                                                               # steht erst nahe der Maus
    _run(w, pet, br, 0.5, cursor)
    assert br.nap and br.nap["mode"] == "spot"
    _run(w, pet, br, 22, cursor)
    assert pet.state == "sleep" and pet.napping
    newest = max(q.y for q in w.term_platforms if q.row >= 0)
    assert pet.y < newest - 3 * 20, "nicht bei der neuesten Ausgabe"
    assert ((pet.x - cursor[0]) ** 2 + (pet.y - cursor[1]) ** 2) ** 0.5 > 500, "weit weg von der Maus"
    _run(w, pet, br, 150, cursor)
    assert said == ["tired", "rested"] and pet.state != "sleep"


def test_geweckt_laesst_es_sich_eine_weile_in_ruhe():
    snap = make_snapshot(["x" * 70] * 14, rows=20, n_tabs=1, active=0)
    w, pet, br, said = _setup(snap)
    _run(w, pet, br, 25)
    assert pet.state == "sleep"
    pet.poke()                                                                # anstupsen weckt
    _run(w, pet, br, 1)
    assert br.nap is None and said == ["tired"]
    _run(w, pet, br, B.NAP_RETRY - 10)
    assert said == ["tired"], "nicht sofort wieder hinlegen"
