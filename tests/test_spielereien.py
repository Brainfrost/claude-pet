"""Ball, Wörter fressen, Tagesablauf, Pausen, Git-Momente."""
import random
from datetime import datetime

from claude_pet import creatures, daily, growth
from claude_pet.ball import Ball
from claude_pet.brain import FOOD, Brain
from claude_pet.pet import Pet
from claude_pet.reactions import GIT_COMMIT, GIT_PUSH
from claude_pet.speech import CANNED
from claude_pet.world import World
from conftest import make_snapshot

VB = (-2000, -100, 4000, 1200)


def floor(_x):
    return 1100


def step_all(pet, brain, world, snap, seconds, cursor=(300, 100), ball=None):
    for f in range(int(seconds * 60)):
        if f % 4 == 0:
            world.update(snap)
            brain.on_world(world)
            pet.on_world(world)
        brain.tick(1 / 60, world, cursor)
        pet.step(1 / 60, world, floor, VB, cursor)
        if ball is not None:
            if ball.carried_by == "pet":
                ball.x, ball.y = pet.x + pet.facing * pet.W * 0.35, pet.y - pet.H * 0.45
            ball.step(1 / 60, world, floor, VB)


# ------------------------------------------------------------ Ball-Physik
def test_ball_bounces_and_comes_to_rest_on_text():
    world = World()
    world.update(make_snapshot(["x" * 60] * 3, rows=10))
    ball = Ball(200, 0, 0, 0, line_h=20)
    for _ in range(600):
        ball.step(1 / 60, world, floor, VB)
    assert ball.resting and ball.support is not None and ball.support.row >= 0
    assert abs(ball.bottom - ball.support.y) < 1e-6


def test_ball_rolls_off_edge_and_falls():
    world = World()
    world.update(make_snapshot(["abc", "", "", "x" * 80], rows=10))
    ball = Ball(10, 0, 0, 0, line_h=20)
    for _ in range(120):
        ball.step(1 / 60, world, floor, VB)
    assert ball.resting and ball.support.row == 0
    ball.vx = 500
    for _ in range(240):
        ball.step(1 / 60, world, floor, VB)
    assert ball.resting and ball.support.row == 3, "über die Kante gerollt, eine Ebene tiefer gelandet"


# ------------------------------------------------------------ Apportieren
def test_playful_pet_fetches_ball_to_cursor():
    random.seed(11)
    world = World()
    snap = make_snapshot(["Zeile " + "x" * 70] * 8, rows=20)
    pet = Pet(creatures.get("schleim"), "jung", "verspielt")
    brain = Brain(pet, "verspielt")
    fetched = []
    brain.on_fetched = lambda: fetched.append(1)
    step_all(pet, brain, world, snap, 4)
    ball = Ball(900, 50, 0, 0, line_h=20)
    brain.ball = ball
    step_all(pet, brain, world, snap, 25, cursor=(150, 60), ball=ball)
    assert fetched, (pet.state, pet.x, ball.x, brain.goal)
    assert abs(ball.x - 150) < 200, "Ball liegt beim Mauszeiger"


# ------------------------------------------------------------ Wörter fressen
def test_pet_walks_to_bug_and_eats_it():
    random.seed(4)
    world = World()
    snap = make_snapshot(["x" * 70] * 5 + ["● Hier ist noch ein Bug versteckt " + "." * 30] * 2 + ["x" * 70] * 6,
                         rows=20)
    pet = Pet(creatures.get("katze"), "jung", "neugierig")
    brain = Brain(pet, "neugierig")
    eaten = []
    brain.on_ate = lambda word, p, start: eaten.append((word, start))
    far = (5000, 5000)                       # Mauszeiger weit weg (sonst hängt es sich evtl. dran)
    step_all(pet, brain, world, snap, 4, cursor=far)
    brain.eat_t = 0
    step_all(pet, brain, world, snap, 20, cursor=far)
    assert eaten and eaten[0][0].lower() == "bug", (pet.state, brain.goal)


def test_food_words_and_counter():
    assert FOOD.search("Ein TODO hier") and FOOD.search("3 Fehler") and FOOD.search("FIXME:")
    assert not FOOD.search("debugger") and not FOOD.search("fehlerfrei")
    p = growth.ensure_defaults({"personality": "faul"})
    assert growth.count_eaten(p, "2026-11-25") == 1
    assert growth.count_eaten(p, "2026-11-25") == 2
    assert growth.count_eaten(p, "2026-11-26") == 1 and p["eaten"]["total"] == 3


# ------------------------------------------------------------ Tagesablauf & Pausen
def test_daypart():
    assert daily.daypart(datetime(2026, 1, 1, 7)) == "morgen"
    assert daily.daypart(datetime(2026, 1, 1, 14)) == "tag"
    assert daily.daypart(datetime(2026, 1, 1, 20)) == "abend"
    assert daily.daypart(datetime(2026, 1, 1, 2)) == "nacht"


def test_work_tracker_reminds_after_streak_and_resets_after_break():
    t = [0.0]
    idle = [0.0]
    w = daily.WorkTracker(idle_fn=lambda: idle[0], clock=lambda: t[0], break_after=300)
    w.update()
    t[0] = 119 * 60
    assert not w.reminder_due(120)
    t[0] = 121 * 60
    assert w.reminder_due(120)
    t[0] = 125 * 60
    assert not w.reminder_due(120, repeat_min=30), "nicht gleich nochmal"
    idle[0] = 15 * 60                                  # Pause
    t[0] = 140 * 60
    assert w.update() == 0
    idle[0] = 0
    t[0] = 141 * 60
    assert w.update() < 1 and w.take_return() >= 10, "zurück nach Pause"


def test_night_makes_pet_sleep():
    random.seed(2)
    world = World()
    snap = make_snapshot(["x" * 70] * 6, rows=20)
    pet = Pet(creatures.get("bit"), "jung", "verspielt")
    pet.daypart = "nacht"
    brain = Brain(pet, "verspielt")
    states = {}
    for f in range(60 * 60):
        if f % 4 == 0:
            world.update(snap)
            brain.on_world(world)
            pet.on_world(world)
        brain.tick(1 / 60, world, (0, 0))
        pet.step(1 / 60, world, floor, VB, (0, 0))
        states[pet.state] = states.get(pet.state, 0) + 1
    assert states.get("sleep", 0) > 0.4 * 3600, states


# ------------------------------------------------------------ Git & Sprüche
def test_git_patterns():
    assert GIT_COMMIT.search('● Bash(cd "/x" && git commit -q -m "a")')
    assert GIT_COMMIT.search("  ⎿  [main 4c167d6] Aufräumen")
    assert GIT_PUSH.search("   4c167d6..88426f8  main -> main")
    assert GIT_PUSH.search("$ git push origin main")
    assert not GIT_COMMIT.search("Bei `git commit` tanzt das Pet.")
    assert not GIT_PUSH.search("● Bash(git log --oneline)")


def test_all_canned_lines_format():
    values = {"word": "Bug", "today": 3, "hours": "2 Stunden", "tab": "Checkout prüfen"}
    for kind, by_pers in CANNED.items():
        for pers, lines in by_pers.items():
            for line in lines:
                assert line.format(**values), (kind, pers)


# ------------------------------------------------------------ Regression: Dauerspringen am oberen Rand
def test_food_at_top_edge_is_ignored_and_unreachable_goals_are_abandoned():
    random.seed(9)
    world = World()
    snap = make_snapshot(["ganz oben steht ein Fehler"] + ["x" * 70] * 8, rows=20, top=40)
    pet = Pet(creatures.get("spatz"), "jung", "aengstlich")
    brain = Brain(pet, "aengstlich")
    ceiling = (-2000, 0, 4000, 1200)               # Bildschirmrand knapp über dem Terminal
    for f in range(60 * 4):
        if f % 4 == 0:
            world.update(snap)
            brain.on_world(world)
            pet.on_world(world)
        brain.tick(1 / 60, world, (0, 0))
        pet.step(1 / 60, world, floor, ceiling, (0, 0))
    assert brain._find_food(world) is None, "Futter am oberen Rand wird ignoriert"
    # Ziel trotzdem erzwingen: es darf nicht endlos hüpfen
    brain.set_goal(("eat", "ganz oben steht ein Fehler", 0, 20, "Fehler"))
    jumps, prev = 0, None
    for f in range(60 * 20):
        if f % 4 == 0:
            world.update(snap)
            brain.on_world(world)
            pet.on_world(world)
        brain.tick(1 / 60, world, (0, 0))
        pet.step(1 / 60, world, floor, ceiling, (0, 0))
        if pet.state == "jump" and prev != "jump":
            jumps += 1
        prev = pet.state
        if brain.goal is None:
            break
    assert brain.goal is None and jumps <= 6, jumps


def test_somersault_always_completes():
    pet = Pet(creatures.get("spatz"), "jung", "verspielt")
    pet.tricks = {"purzelbaum"}
    world = World()
    world.update(make_snapshot(["x" * 70] * 6, rows=20))
    for _ in range(200):
        pet.on_world(world)
        pet.step(1 / 60, world, floor, VB, (0, 0))
    for _ in range(40):
        pet._hop(-450)
        pet._start_spin(2 * abs(pet.vy) / pet.G)
        assert pet.spin > 0
        for _ in range(300):
            pet.step(1 / 60, world, floor, VB, (0, 0))
            if pet.spin == 0 and pet.grounded:
                break
        assert pet.spin == 0, "Rolle ist ganz zu Ende gedreht"


def test_can_jump_down_to_a_lower_line_below_itself():
    """Regression: früher landete es beim Sprung nach unten immer wieder auf der eigenen Zeile."""
    world = World()
    world.update(make_snapshot(["x" * 70] * 8, rows=20))
    pet = Pet(creatures.get("katze"), "jung", "neugierig")
    for _ in range(120):
        pet.on_world(world)
        pet.step(1 / 60, world, floor, VB, (0, 0))
    start_row = pet.support.row
    target = next(p for p in world.platforms if p.row == start_row + 3)
    pet._ballistic_to(pet.x, target.y, apex=0.7 * pet.line_h)
    for _ in range(180):
        pet.step(1 / 60, world, floor, VB, (0, 0))
        if pet.grounded:
            break
    assert pet.support.row > start_row, "ist tiefer gekommen"


def test_daily_moments():
    from claude_pet.daily import due_moments
    fri = datetime(2026, 11, 27, 12, 0)                    # Freitag
    assert due_moments(fri, []) == ["lunch"]
    assert due_moments(fri, ["lunch"]) == []
    assert due_moments(datetime(2026, 11, 27, 15, 0), []) == ["weekend"]
    assert due_moments(datetime(2026, 11, 26, 15, 0), []) == [], "Donnerstag: kein Wochenende"
    assert due_moments(datetime(2026, 11, 26, 17, 30), []) == ["evening"]
    assert due_moments(datetime(2026, 11, 28, 17, 30), []) == [], "Samstag: kein Feierabend"


# ------------------------------------------------------------ Jahreszeiten
def test_seasons_and_weather_lands_on_text_and_scrolls_with_it():
    from datetime import date
    from claude_pet import seasons
    assert seasons.season(date(2026, 12, 3)) == "winter" and seasons.season(date(2026, 11, 25)) == "herbst"
    assert seasons.season(date(2026, 4, 1)) == "fruehling" and seasons.season(date(2026, 7, 1)) == "sommer"
    text = [f"Zeile {i} " + "x" * 60 for i in range(200)]
    w = World()
    w.update(make_snapshot(text[0:20], rows=22))
    wx = seasons.Weather("winter", random.Random(1))
    for _ in range(60 * 20):
        wx.step(1 / 60, w)
    assert wx.resting, "Schnee bleibt auf den Zeilen liegen"
    assert all(p["row"] >= 0 for p in wx.resting)
    assert len(wx.flying) <= seasons.MAX_FLYING
    before = {id(p): p["row"] for p in wx.resting}
    w.update(make_snapshot(text[3:23], rows=22))              # 3 Zeilen gescrollt
    wx.on_world(w)
    moved = [p for p in wx.resting if id(p) in before]
    assert moved and all(p["row"] == before[id(p)] - 3 for p in moved), "wandert mit der Zeile"


def test_winter_hat_renders(qapp):
    r = creatures.Renderer()
    c = creatures.get("katze")
    plain = r.render(c, variant="faul", state="idle", t=0, walk_i=0, blinking=False, facing=1, px=3, stage="jung")
    hat = r.render(c, variant="faul", state="idle", t=0, walk_i=0, blinking=False, facing=1, px=3, stage="jung",
                   accessories=("muetze",))
    assert plain != hat
