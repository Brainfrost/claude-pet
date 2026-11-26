"""Mac-Zweig mit nachgebautem macOS (Quartz/AppKit/ApplicationServices) – läuft auch unter Windows.

Der Accessibility-Baum entspricht dem, was Electron/Chromium für ein VS-Code-Terminal liefert:
Fenster → Gruppe → AXWebArea → .xterm → .xterm-screen → .xterm-helpers → .xterm-helper-textarea
"""
import importlib
import os
import sys
import types
from types import SimpleNamespace as NS

import pytest

OWN = os.getpid()
ERR = -25212          # kAXErrorNoValue


class El:
    """Nachgebautes AX-Element."""
    def __init__(self, role="AXGroup", classes=(), rect=None, children=(), **attrs):
        self.attrs = {"AXRole": role, "AXDOMClassList": list(classes), **attrs}
        if rect:
            l, t, r, b = rect
            self.attrs["AXPosition"] = NS(kind="pt", x=l, y=t)
            self.attrs["AXSize"] = NS(kind="sz", width=r - l, height=b - t)
        self.attrs["AXChildren"] = list(children)
        for c in children:
            c.attrs["AXParent"] = self


def _tree(search_supported=True):
    ta = El("AXTextArea", ["xterm-helper-textarea"], (310, 210, 320, 232),
            AXDescription="Terminal 1, ✳ Aufgabe Run the command: Toggle Screen Reader")
    helpers = El(classes=["xterm-helpers"], children=[ta])
    screen = El(classes=["xterm-screen"], rect=(300, 100, 1200, 540), children=[helpers])
    term = El(classes=["terminal", "xterm"], children=[screen])
    web = El("AXWebArea", children=[term])
    win = El("AXWindow", rect=(0, 0, 1200, 800), children=[El(children=[web])],
             AXTitle="main.py - projekt - Visual Studio Code")
    app = El("AXApplication", AXWindows=[win])
    return NS(app=app, win=win, web=web, screen=screen, ta=ta, search=search_supported)


@pytest.fixture
def mac(monkeypatch):
    """Lädt macapi/macax mit nachgebauten pyobjc-Modulen."""
    state = NS(tree=_tree(), windows=[])

    def copy(el, attr, _):
        v = el.attrs.get(attr) if isinstance(el, El) else None
        return (0, v) if v is not None else (ERR, None)

    def param(el, attr, pred, _):
        if not state.tree.search or attr != "AXUIElementsForSearchPredicate":
            return (-25205, None)                        # nicht unterstützt
        out, stack = [], [el]
        while stack:
            e = stack.pop()
            if e.attrs["AXRole"] in ("AXTextArea", "AXTextField"):
                out.append(e)
            stack.extend(e.attrs["AXChildren"])
        return (0, out)

    quartz = types.ModuleType("Quartz")
    for k in ("kCGWindowLayer", "kCGWindowBounds", "kCGWindowNumber", "kCGWindowOwnerPID",
              "kCGWindowOwnerName", "kCGWindowName", "kCGWindowAlpha"):
        setattr(quartz, k, k)
    quartz.kCGWindowListOptionOnScreenOnly, quartz.kCGWindowListExcludeDesktopElements = 1, 16
    quartz.kCGNullWindowID = 0
    quartz.CGWindowListCopyWindowInfo = lambda opts, wid: state.windows
    quartz.CGEventCreate = lambda _: None
    quartz.CGEventGetLocation = lambda _: NS(x=5.0, y=6.0)
    quartz.kCGEventSourceStateCombinedSessionState, quartz.kCGAnyInputEventType = 0, 0xFFFFFFFF
    quartz.CGEventSourceSecondsSinceLastEventType = lambda a, b: 12.5
    appkit = types.ModuleType("AppKit")
    appkit.NSWorkspace = NS(sharedWorkspace=lambda: NS(frontmostApplication=lambda: NS(processIdentifier=lambda: 500)))
    appkit.NSApplication = NS(sharedApplication=lambda: NS(setActivationPolicy_=lambda p: None))
    aps = types.ModuleType("ApplicationServices")
    aps.AXIsProcessTrustedWithOptions = lambda opts: True
    aps.AXUIElementCopyAttributeValue = copy
    aps.AXUIElementCopyParameterizedAttributeValue = param
    aps.AXUIElementCreateApplication = lambda pid: state.tree.app
    aps.AXUIElementSetAttributeValue = lambda el, attr, v: 0
    aps.AXValueGetValue = lambda v, kind, _: (True, v)
    aps.kAXTrustedCheckOptionPrompt, aps.kAXValueCGPointType, aps.kAXValueCGSizeType = "prompt", 1, 2
    for name, mod in (("Quartz", quartz), ("AppKit", appkit), ("ApplicationServices", aps)):
        monkeypatch.setitem(sys.modules, name, mod)
    for m in ("claude_pet.macapi", "claude_pet.macax"):
        sys.modules.pop(m, None)
    macapi = importlib.import_module("claude_pet.macapi")
    macax = importlib.import_module("claude_pet.macax")
    state.windows = [
        {"kCGWindowNumber": 9, "kCGWindowOwnerPID": 1, "kCGWindowOwnerName": "Window Server",
         "kCGWindowLayer": 25, "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 1920, "Height": 25}},
        {"kCGWindowNumber": 77, "kCGWindowOwnerPID": 500, "kCGWindowOwnerName": "Code", "kCGWindowLayer": 0,
         "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 1200, "Height": 800}, "kCGWindowName": ""},
        {"kCGWindowNumber": 88, "kCGWindowOwnerPID": OWN, "kCGWindowOwnerName": "Python", "kCGWindowLayer": 0,
         "kCGWindowBounds": {"X": 10, "Y": 10, "Width": 300, "Height": 300}},
        {"kCGWindowNumber": 99, "kCGWindowOwnerPID": 600, "kCGWindowOwnerName": "Safari", "kCGWindowLayer": 0,
         "kCGWindowBounds": {"X": 1300, "Y": 100, "Width": 600, "Height": 500}},
    ]
    yield NS(api=macapi, ax=macax, state=state)
    for m in ("claude_pet.macapi", "claude_pet.macax"):
        sys.modules.pop(m, None)


def _fresh(mac):
    mac.api._cache = (0.0, [])


def test_fensterliste(mac):
    api = mac.api
    _fresh(mac)
    assert api.enum_windows() == [77, 88, 99]                 # Ebene 0, vorderstes zuerst
    assert api.foreground_window() == 77
    assert [w[0] for w in api.window_rects(term_hwnd=77)] == [77, 99]    # ohne eigene Fenster
    assert api.window_rects(term_hwnd=77)[0][2] is True
    assert api.top_window_at(1400, 200) == 99 and api.top_window_at(1250, 50) is None
    assert api.window_title(77) == "main.py - projekt - Visual Studio Code"   # über die Bedienungshilfen
    assert api.class_name(77) == "Code" and api.is_shown(77) and not api.is_shown(5)
    assert api.cursor_pos() == (5, 6) and api.idle_seconds() == 12.5


@pytest.mark.parametrize("search", [True, False])
def test_terminal_finden(mac, search):
    """Mit Chromium-Suche und – falls die fehlt – per Baumsuche."""
    mac.state.tree = _tree(search_supported=search)
    _fresh(mac)
    sc = mac.ax.AXScanner()
    assert sc.windows() == [77]
    screens, tas, tab = sc.read(77)
    assert screens == [(300, 100, 1200, 540)]
    assert tas == [((310, 210, 320, 232), "Terminal 1, ✳ Aufgabe Run the command: Toggle Screen Reader")]
    assert sc.has_terminal(77)


def test_ende_zu_ende_mac(mac, monkeypatch):
    """Erweiterung schickt Ausgabe, AX liefert Fläche + Cursor -> Pane mit Text an der richtigen Stelle."""
    from claude_pet import vscode
    from claude_pet.streams import StreamHub
    _fresh(mac)
    monkeypatch.setattr(vscode, "osapi", mac.api)
    hub = StreamHub()
    hub.handle(1, {"type": "hello", "app": "Visual Studio Code", "workspace": "projekt"})
    hub.handle(1, {"type": "start", "term": "t1", "cmd": "claude", "dims": {"columns": 100, "rows": 20}})
    hub.handle(1, {"type": "data", "term": "t1", "d": "\x1b]0;✳ Aufgabe\x07Hallo vom Mac"})
    next(iter(hub.sessions.values())).emu.last_feed = 0.0
    src = vscode.VSCodeSource(mac.ax.AXScanner(), hub)
    snap = src.poll(77, single_window=True)
    assert snap.ok and snap.host == "vscode" and snap.win_rect == (0, 0, 1200, 800)
    (pane,) = snap.panes
    assert (pane.cell_w, pane.line_h) == (9.0, 22.0)
    assert pane.lines[5][1].startswith("Hallo vom Mac")       # Cursor in Zeile 5 (210 = 100 + 5 * 22)
    assert snap.tabs[0].name == "✳ Aufgabe" and snap.tabs[0].state == "idle"


def test_launch_agent(monkeypatch):
    from claude_pet import settings
    monkeypatch.setenv("PATH", "/usr/bin:/bin")              # so sieht der PATH auf dem Mac aus
    a = settings.launch_agent(run_at_load=False)
    assert a["Label"] == "com.claude-pet" and a["RunAtLoad"] is False
    assert a["ProgramArguments"][-1].endswith("run.pyw")
    path = a["EnvironmentVariables"]["PATH"].split(":")
    assert path[:2] == ["/usr/bin", "/bin"] and "/opt/homebrew/bin" in path    # + übliche claude-Orte
