"""Betriebssystem-Schicht: unter Windows winapi.py, auf dem Mac macapi.py – gleiche Funktionen.

Fenster-IDs sind unter Windows HWNDs, auf dem Mac CGWindowIDs. Koordinaten: Windows physische Pixel,
Mac Punkte (beides passt zu Qt im jeweiligen Modus).

    set_dpi_awareness()                    single_instance() -> bool
    cursor_pos() -> (x, y)                 foreground_window() -> id
    enum_windows() -> [id] (oberstes zuerst)
    is_shown(id)  window_rect(id)  window_title(id)  window_pid(id)  class_name(id)
    find_terminal_windows() -> [id]        (Windows Terminal; Mac: [])
    window_rects(term_id) -> [(id, rect, ist_terminal)]   top_window_at(x, y) -> id
    prepare_overlay(win_id, click_through) – Overlay-Fenster: nicht aktivierbar, nicht in Aufnahmen
    idle_seconds()                         hide_dock_icon()
    OWN_PID
"""
import sys

if sys.platform == "win32":
    from . import winapi as _impl
elif sys.platform == "darwin":
    from . import macapi as _impl
else:  # pragma: no cover
    raise ImportError("claude-pet läuft unter Windows und macOS")


def __getattr__(name):
    return getattr(_impl, name)
