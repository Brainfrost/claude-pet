"""Pet + Gehirn ohne Fenster auf künstlichen Terminal-Snapshots simulieren."""
import random

import pytest

from claude_pet import creatures
from claude_pet.brain import Brain
from claude_pet.pet import Pet
from claude_pet.world import World
from conftest import make_snapshot

TEXT_A = ["● Ich schaue mir das an", "", "  def foo(x):", "      return x * 2", "",
          "● Fertig, alle Tests laufen", "  12 passed in 0.3s"] * 3
TEXT_B = ["ganz anderer Inhalt in Tab B"] * 12
VBOUNDS = (-2000, -100, 4000, 1200)


def floor(_x):
    return 1100


def run(pet, brain, world, seconds, snap_fn, cursor=(500, 300)):
    for f in range(int(seconds * 60)):
        if f % 4 == 0:
            world.update(snap_fn(f))
            brain.on_world(world)
            pet.on_world(world)
        brain.tick(1 / 60, world, cursor)
        pet.step(1 / 60, world, floor, VBOUNDS, cursor)
        assert VBOUNDS[0] <= pet.x <= VBOUNDS[2] and VBOUNDS[1] <= pet.y <= 1200, (pet.state, pet.x, pet.y)


@pytest.mark.parametrize("pers", ["faul", "neugierig", "verspielt", "aengstlich"])
@pytest.mark.parametrize("cid", ["katze", "klammer"])
def test_lives_without_crashing(pers, cid):
    random.seed(hash((pers, cid)) & 0xFFFF)
    world, pet = World(), Pet(creatures.get(cid), "jung", pers)
    pet.tricks = {"doppelsprung", "purzelbaum", "weitsprung"}
    brain = Brain(pet, pers)

    def snaps(f):
        active = (f // 600) % 3                       # alle 10 s Tab wechseln
        lines = TEXT_A[(f // 120) % 5:] if active == 0 else TEXT_B
        return make_snapshot(lines, active=active)

    run(pet, brain, world, 45, snaps)


def test_tab_switch_hides_and_restores_in_place():
    random.seed(3)
    world, pet = World(), Pet(creatures.get("bit"), "jung", "faul")
    brain = Brain(pet, "faul")
    a, b = make_snapshot(TEXT_A, active=0), make_snapshot(TEXT_B, active=1)
    run(pet, brain, world, 6, lambda f: a)
    for _ in range(600):                              # warten, bis es sicher steht
        if pet.grounded and pet.support.row >= 0 and not pet.busy:
            break
        run(pet, brain, world, 1 / 15, lambda f: a)
    assert pet.grounded and pet.support.row >= 0
    text, x = pet.support.text, pet.x

    world.update(b)
    brain.on_world(world)
    pet.on_world(world)
    assert pet.state == "hidden", "verschwindet sofort mit seinem Tab"

    world.update(a)
    brain.on_world(world)
    pet.on_world(world)
    assert pet.state != "hidden" and pet.support is not None
    assert pet.support.text == text and pet.x == x, "sitzt wieder genau dort"


def test_curious_pet_follows_to_new_tab():
    random.seed(5)
    world, pet = World(), Pet(creatures.get("katze"), "jung", "neugierig")
    brain = Brain(pet, "neugierig")
    run(pet, brain, world, 5, lambda f: make_snapshot(TEXT_A, active=0))
    world.update(make_snapshot(TEXT_B, active=1))
    brain.on_world(world)
    pet.on_world(world)
    assert pet.state != "hidden"
