"""Bug-Jagd: Käfer krabbeln auf Zeilen, Klicks treffen, das Pet jagt mit."""
import random

from claude_pet import bughunt, creatures
from claude_pet.brain import Brain
from claude_pet.pet import Pet
from claude_pet.world import World
from conftest import make_snapshot

VB = (-2000, -100, 4000, 1200)


def floor(_x):
    return 1100


def _world():
    w = World()
    w.update(make_snapshot([("  " if i % 2 else "") + "Text " * 14 for i in range(22)], rows=24))
    return w


def test_bugs_crawl_on_lines_and_clicks_squash_them():
    w = _world()
    h = bughunt.BugHunt(0, random.Random(1))
    ys = {p.y for p in w.term_platforms if p.row >= 0}
    for _ in range(60 * 5):
        h.step(1 / 60, w)
        for b in h.alive:
            assert b.hop or b.y in ys, "Käfer sitzt auf einer Textzeile"
    assert 3 <= len(h.alive) <= bughunt.MAX_BUGS
    b = next(b for b in h.alive if not b.hop)
    assert h.hit(b.x + 3, b.y - 6, radius=20) is b and h.score["du"] == 1 and not b.alive
    assert h.hit(-500, -500, radius=20) is None


def test_scrolled_away_bug_counts_for_nobody():
    text = [f"Zeile {i} " + "x" * 60 for i in range(200)]
    w = World()
    w.update(make_snapshot(text[0:20], rows=22))
    h = bughunt.BugHunt(0, random.Random(2))
    for _ in range(120):
        h.step(1 / 60, w)
    rows = {id(b): b.row for b in h.alive if not b.hop}
    w.update(make_snapshot(text[2:22], rows=22))
    h.on_world(w)
    for b in h.alive:
        if id(b) in rows:
            assert b.row == rows[id(b)] - 2


def test_pet_hunts_and_catches_bugs_and_game_ends():
    random.seed(3)
    w = _world()
    pet = Pet(creatures.get("schleim"), "jung", "verspielt")
    brain = Brain(pet, "verspielt")
    h = bughunt.BugHunt(0, random.Random(3))
    brain.on_catch = h.catch
    for f in range(int(60 * (bughunt.GAME_LEN + 1))):
        if f % 4 == 0:
            pet.on_world(w)
        h.step(1 / 60, w)
        g = brain.goal
        if (not g or g[0] != "hunt") and pet.grounded and pet.state not in ("eat",):
            t = h.nearest(pet.x, pet.y)
            if t is not None:
                brain.goal, pet.busy = None, False
                brain.set_goal(("hunt", t))
        brain.tick(1 / 60, w, (5000, 5000))
        pet.step(1 / 60, w, floor, VB, (5000, 5000))
    assert h.finished
    assert h.score["pet"] >= 3, h.score
    assert h.result() == "won"
