import random

from claude_pet.world import (ROW_FLOOR, ROW_VISION, ROW_WINDOW, World, _segments_slow, scroll_shift,
                              segments)
from conftest import CELL_W, LINE_H, make_snapshot


def test_segments_regex_equals_reference():
    rnd = random.Random(7)
    samples = ["", "   ", "abc", "a  b   c", "  foo bar  baz    qux   ", "tab\there  x", "⎿ \xa0Wrote 40 lines"]
    samples += ["".join(rnd.choice("ab  \t") for _ in range(60)) for _ in range(2000)]
    for t in samples:
        assert segments(t) == _segments_slow(t, 3), repr(t)


def test_segments_gaps():
    # Lücken unter 3 Leerzeichen werden überbrückt, ab 3 entsteht ein Loch
    assert segments("ab cd  ef   gh") == [(0, 9), (12, 14)]


def test_scroll_shift():
    old = [f"Zeile Nummer {i}" for i in range(20)]
    assert scroll_shift(old, old) == 0
    assert scroll_shift(old, old[3:] + ["neu a", "neu b", "neu c"]) == 3
    assert scroll_shift(old, [f"ganz anderer Text {i}" for i in range(20)]) is None


def test_update_builds_platforms_and_floor():
    w = World()
    w.update(make_snapshot(["hallo welt", "", "    eingerueckt   und weiter"]))
    rows = {p.row for p in w.platforms}
    assert {0, 2, ROW_FLOOR} <= rows and 1 not in rows
    first = next(p for p in w.platforms if p.row == 0)
    assert first.x0 == 0 and first.x1 == 10 * CELL_W
    assert abs(first.y - (40 + 0.18 * LINE_H)) < 1e-6
    indented = sorted(p.x0 for p in w.platforms if p.row == 2)
    assert indented == [4 * CELL_W, 18 * CELL_W]


def test_unchanged_snapshot_keeps_platforms():
    w = World()
    s = make_snapshot(["a b c"])
    w.update(s)
    before = list(w.platforms)
    w.update(make_snapshot(["a b c"]))
    assert w.platforms == before and w.shifts == [0]


def test_window_top_edges_with_occlusion():
    w = World()
    rects = [
        (1, (300, 100, 700, 400), False),      # oben, verdeckt einen Teil der Kante darunter
        (2, (100, 200, 900, 600), False),
        (3, (0, 0, 2000, 1000), False),        # maximiert: kein Platz über der Kante
        (4, (50, 300, 500, 500), True),        # das Terminal selbst
    ]
    w.set_windows(rects, headroom=50, screen_top_at=lambda x, y: 0)
    spans = sorted((p.x0, p.x1) for p in w.platforms if p.row == ROW_WINDOW and p.text == "2")
    assert spans == [(100, 300), (700, 900)]
    assert not [p for p in w.platforms if p.text in ("3", "4")]
    assert [p for p in w.platforms if p.text == "1"]


def test_vision_ignores_visible_terminal():
    w = World()
    w.update(make_snapshot(["x"]))
    w.set_vision([(100, 10, 200), (5000, 10, 200)])       # erste Kante liegt im Terminal
    vis = [p for p in w.platforms if p.row == ROW_VISION]
    assert [p.y for p in vis] == [5000]
