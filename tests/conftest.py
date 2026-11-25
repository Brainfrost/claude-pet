import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from claude_pet.terminal import Pane, Snapshot, Tab  # noqa: E402

LINE_H = 20
CELL_W = 10
COLS = 120


def make_snapshot(lines, active=0, n_tabs=3, left=0, top=40, rows=30, tab_names=None, working=()):
    """Künstlicher Terminal-Snapshot: Text ab Zeile 0, aufgefüllt auf volle Breite."""
    rows_text = [(l + " " * COLS)[:COLS] for l in lines] + [" " * COLS] * max(0, rows - len(lines))
    pane_rect = (left, top, left + COLS * CELL_W, top + rows * LINE_H)
    pane = Pane(rect=pane_rect, line_h=LINE_H, cell_w=CELL_W, x0=left,
                lines=[(top + i * LINE_H, t) for i, t in enumerate(rows_text)])
    names = tab_names or [f"Session {i}" for i in range(n_tabs)]
    tabs = [Tab(("◐ " if i in working else "✳ ") + names[i],
                (left + i * 200, top - 36, left + (i + 1) * 200, top - 4), i == active)
            for i in range(len(names))]
    return Snapshot(ok=True, hwnd=1, win_rect=(left, top - 40, pane_rect[2], pane_rect[3]),
                    panes=[pane], tabs=tabs, t=0.0)


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtGui import QGuiApplication
    return QGuiApplication.instance() or QGuiApplication([])
