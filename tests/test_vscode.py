"""VS Code/Cursor als Terminal-Quelle: Emulator, Kanal-Protokoll, Zuordnung, Geometrie, Quellenwahl."""
import json
import zipfile

from claude_pet import terminal, vscode, vsix
from claude_pet.emulator import TermEmulator
from claude_pet.streams import StreamHub


# ------------------------------------------------------------------ Emulator
def test_emulator_text_und_unbekannte_sequenzen():
    e = TermEmulator(40, 5)
    # Kitty-Tastatur / modifyOtherKeys: pyte kennt sie nicht und schrieb früher ein 'u' auf den Bildschirm
    e.feed("\x1b[?2004h\x1b[<u\x1b[>5u\x1b[>4;2m❯ hallo")
    assert e.lines()[0].rstrip() == "❯ hallo"
    assert len(e.lines()[0]) == 40


def test_emulator_zerteilte_sequenz():
    e = TermEmulator(20, 3)
    e.feed("ab\x1b[3")          # Sequenz endet mitten im Stück
    e.feed("1mrot\x1b[0m")
    assert e.lines()[0].rstrip() == "abrot"


def test_emulator_titel():
    e = TermEmulator(20, 3)
    e.feed("\x1b]0;✳ README lesen\x07x")
    assert e.title == "✳ README lesen"


def test_emulator_verschieben_und_groesse():
    e = TermEmulator(10, 6)
    e.feed("eins\r\nzwei")
    assert e.cursor_row == 1
    e.shift(3)                                        # Inhalt begann eigentlich weiter unten
    assert [l.rstrip() for l in e.lines()][:5] == ["", "", "", "eins", "zwei"]
    assert e.cursor_row == 4
    e.shift(-2)
    assert e.lines()[1].rstrip() == "eins" and e.cursor_row == 2
    e.resize(8, 3)                                    # kleiner: oben fällt weg, Cursor bleibt im Bild
    assert e.rows == 3 and e.cols == 8 and 0 <= e.cursor_row < 3


# ------------------------------------------------------------------ Kanal-Protokoll
def _hub_mit_sitzung(cid=1, workspace="projekt"):
    hub = StreamHub()
    hub.handle(cid, {"type": "hello", "app": "Visual Studio Code", "workspace": workspace})
    hub.handle(cid, {"type": "start", "term": "t1", "cmd": "claude", "dims": {"columns": 100, "rows": 20},
                     "title": "✳ Claude Code"})
    hub.handle(cid, {"type": "data", "term": "t1", "d": "\x1b]0;✳ Aufgabe\x07Hallo Welt"})
    return hub


def test_kanal_protokoll():
    hub = _hub_mit_sitzung()
    (s,) = hub.sessions.values()
    assert s.workspace == "projekt" and s.start_dims == (100, 20) and s.running
    assert s.best_title == "✳ Aufgabe"                 # Titel aus dem Strom geht vor
    assert s.emu.lines()[0].startswith("Hallo Welt")
    hub.handle(1, {"type": "active", "term": "t1"})
    assert s.active
    hub.handle(1, {"type": "end", "term": "t1"})
    assert not s.running
    hub.handle(1, {"type": "closed", "term": "t1"})
    assert not hub.sessions
    hub.handle(1, {"type": "data"})                    # kaputte Nachricht: ignoriert
    hub.drop_client(1)
    assert not hub.clients


# ------------------------------------------------------------------ Titel/Zuordnung
def test_titel_aus_eingabefeld():
    name = "Terminal 1, ✳ Inhalt der README Run the command: Toggle Screen Reader Accessibility Mode"
    assert vscode.textarea_title(name) == "✳ Inhalt der README"
    assert vscode.textarea_title(name, known=["✳ Inhalt der README"]) == "✳ Inhalt der README"
    assert vscode.textarea_title("Terminal 3, ◐ arbeitet") == "◐ arbeitet"


def test_fenster_und_arbeitsbereich():
    assert vscode.is_editor_title("main.py - projekt - Visual Studio Code")
    assert vscode.is_editor_title("projekt - Cursor")
    assert not vscode.is_editor_title("Visual Studio Code Tipps - Google Chrome")
    assert vscode.workspace_in_title("projekt", "main.py - projekt - Visual Studio Code")
    assert not vscode.workspace_in_title("proj", "main.py - projekt - Visual Studio Code")


def test_zuordnung():
    hub = _hub_mit_sitzung()
    s = next(iter(hub.sessions.values()))
    title = "projekt - Visual Studio Code"
    # über den Titel
    assert vscode.match_sessions([{"ta_name": "Terminal 1, ✳ Aufgabe Run…"}], [s], title, True) == [s]
    # anderer Titel, eine Fläche, Terminal ist aktiv -> trotzdem zugeordnet
    s.active = True
    assert vscode.match_sessions([{"ta_name": "Terminal 2, pwsh"}], [s], title, True) == [s]
    # zwei Flächen ohne passenden Titel: lieber nichts als das Falsche
    assert vscode.match_sessions([{"ta_name": "a"}, {"ta_name": "b"}], [s], title, True) == [None, None]
    # anderes Fenster (anderer Arbeitsbereich) bei mehreren Fenstern: nicht zuordnen
    assert vscode.match_sessions([{"ta_name": "Terminal 1, ✳ Aufgabe"}], [s], "x - Cursor", False) == [None]


def test_eingabefeld_zur_flaeche():
    screens = [(0, 0, 500, 300), (0, 320, 500, 600)]
    tas = [((10, 400, 20, 420), "unten"), ((10, 100, 20, 120), "oben")]
    assert [n for _, n in vscode.pair_textareas(screens, tas)] == ["oben", "unten"]


# ------------------------------------------------------------------ Geometrie/Ausrichtung
def test_pane_kalibriert_und_ausgerichtet():
    hub = _hub_mit_sitzung()
    s = next(iter(hub.sessions.values()))
    rect = (300, 100, 300 + 100 * 9, 100 + 20 * 22)      # 100x20 Zellen à 9x22 px
    s.emu.last_feed = 0.0                               # Strom ruhig
    # Cursor des echten Terminals steht in Zeile 5 (der Prompt war nicht oben)
    ta = (310, 100 + 5 * 22, 320, 100 + 6 * 22)
    pane = vscode.build_pane(rect, s, ta, now=10.0)
    assert s.cell == (9.0, 22.0)
    assert pane.line_h == 22.0 and pane.cell_w == 9.0 and len(pane.lines) == 20
    assert pane.lines[5][1].startswith("Hallo Welt")    # um 5 Zeilen nach unten ausgerichtet
    assert pane.lines[5][0] == 100 + 5 * 22
    # unverändertes Eingabefeld: keine weitere Verschiebung, auch wenn der Emulator-Cursor wandert
    s.emu.feed("\r\nneue Zeile", now=0.0)
    vscode.build_pane(rect, s, ta, now=10.0)
    assert s.emu.lines()[6].startswith("neue Zeile")
    # Panel kleiner gezogen: Emulator folgt der Fläche
    small = (300, 100, 300 + 50 * 9, 100 + 10 * 22)
    pane = vscode.build_pane(small, s, None, now=10.0)
    assert (s.emu.cols, s.emu.rows) == (50, 10) and len(pane.lines) == 10


def test_pane_ohne_sitzung_ist_leer():
    pane = vscode.build_pane((0, 0, 900, 440), None, (5, 5, 15, 27), now=1.0)
    assert pane.lines == [] and pane.line_h == 22


# ------------------------------------------------------------------ Quellenwahl
class _FakeVS:
    def __init__(self, wins):
        self.wins = wins

    def windows(self):
        return self.wins

    def has_terminal(self, h):
        return True


def test_quellenwahl_folgt_dem_aktiven_fenster(qapp, monkeypatch):
    w = terminal.TerminalWatcher(StreamHub())
    w.vscode = _FakeVS([200])
    clock = {"t": 100.0, "fg": 0}
    monkeypatch.setattr(terminal.time, "time", lambda: clock["t"])
    monkeypatch.setattr(terminal.osapi, "foreground_window", lambda: clock["fg"])
    assert w._choose_host([100])[0] == ("wt", None)          # nichts aktiv: Windows Terminal
    clock["fg"] = 200                                       # VS Code wird aktiv …
    assert w._choose_host([100])[0] == ("wt", None)          # … aber noch nicht lange genug
    clock["t"] += terminal.SWITCH_DELAY + 0.1
    assert w._choose_host([100])[0] == ("vscode", 200)
    assert w._choose_host([])[0] == ("vscode", 200)          # WT zu: bleibt in VS Code
    w.vscode = _FakeVS([])                                  # VS Code zu, WT da: zurück
    assert w._choose_host([100])[0] == ("wt", None)


# ------------------------------------------------------------------ Paket
def test_vsix_paket(tmp_path):
    out = vsix.build(tmp_path)
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        assert {"extension.vsixmanifest", "[Content_Types].xml",
                "extension/package.json", "extension/extension.js"} <= names
        pkg = json.loads(z.read("extension/package.json"))
        assert pkg["activationEvents"] == ["*"]
        assert f'Id="{pkg["name"]}"' in z.read("extension.vsixmanifest").decode()
    assert vsix.extension_id() == "claude-pet.claude-pet-terminal"


# ------------------------------------------------------------------ Bote über Programmgrenzen
class _Ctl:
    """Schlanker Controller-Ersatz für Reactions."""
    def __init__(self, focused=True):
        from types import SimpleNamespace
        self.pet = SimpleNamespace(pane=None, state="hidden")
        self.brain = SimpleNamespace(home=None, news=False, food_urge=False)
        self.diary = SimpleNamespace(count=lambda key: None)
        self.focused = focused
        self.messages = []

    def terminal_focused(self):
        return self.focused

    def messenger(self, tab, host=None):
        self.messages.append(tab)


def _world_with(snap):
    from claude_pet.world import World
    w = World()
    w.update(snap)
    return w


def test_bote_fuer_session_in_anderem_programm(monkeypatch):
    """Pet wohnt im Windows Terminal (das du gerade benutzt); in VS Code arbeitet Claude 30 s und wird
    fertig -> der Bote kommt, obwohl VS Code gerade nicht sichtbar ist."""
    from claude_pet import reactions
    from claude_pet.terminal import Tab
    from conftest import make_snapshot
    clock = {"t": 1000.0}
    monkeypatch.setattr(reactions.time, "time", lambda: clock["t"])
    ctl = _Ctl(focused=True)
    r = reactions.Reactions(ctl)
    for title, dt in (("⠋ Refactoring", 0), ("⠙ Refactoring", 30), ("✳ Refactoring", 1)):
        clock["t"] += dt
        snap = make_snapshot(["hallo"])
        snap.others = [Tab(title, None, False, "vscode")]
        r.on_world(_world_with(snap))
    assert ctl.messages == ["Refactoring"]


def test_kein_bote_bei_kurzer_arbeit_und_umzug_zaehlt_weiter(monkeypatch):
    from claude_pet import reactions
    from claude_pet.terminal import Tab
    from conftest import make_snapshot
    clock = {"t": 1000.0}
    monkeypatch.setattr(reactions.time, "time", lambda: clock["t"])
    ctl = _Ctl(focused=False)
    r = reactions.Reactions(ctl)
    # kurz gearbeitet: kein Bote
    for title, dt in (("⠋ Kurz", 0), ("✳ Kurz", 5)):
        clock["t"] += dt
        snap = make_snapshot(["x"])
        snap.others = [Tab(title, None, False, "vscode")]
        r.on_world(_world_with(snap))
    assert ctl.messages == []
    # Session sichtbar (Pet wohnt in VS Code), du wechselst weg -> Pet zieht um, Session läuft im
    # Hintergrund weiter: die Arbeitszeit zählt über den Umzug hinweg
    s1 = make_snapshot(["x"], tab_names=["Lang"], n_tabs=1, working=(0,))
    s1.host = "vscode"
    r.on_world(_world_with(s1))
    clock["t"] += 25
    s2 = make_snapshot(["x"])
    s2.others = [Tab("✳ Lang", None, False, "vscode")]
    r.on_world(_world_with(s2))
    assert ctl.messages == ["Lang"]


def test_bote_holt_gesperrte_meldungen_nach(monkeypatch):
    """Zwei Sessions werden kurz nacheinander fertig: die zweite geht nicht verloren (früher: 30-s-Sperre
    hat sie verworfen), sondern kommt nach Ablauf der Sperre – mehrere in einem Gang."""
    from types import SimpleNamespace
    from claude_pet import controller as C
    clock = {"t": 1000.0}
    monkeypatch.setattr(C.time, "time", lambda: clock["t"])
    flights = []
    ctl = SimpleNamespace(settings={"messenger": True}, quiet_reason=None, _messenger_queue={},
                          _messenger_t=0.0, _messenger_text=None, focused=False,
                          world=SimpleNamespace(ok=True, snap=SimpleNamespace(host="wt")),
                          pet=SimpleNamespace(come_to_user=lambda: flights.append(clock["t"]) or True),
                          diary=SimpleNamespace(count=lambda k: None))
    ctl.terminal_focused = lambda: ctl.focused
    ctl._deliver_messenger = lambda: C.Controller._deliver_messenger(ctl)
    send = lambda tab, host: C.Controller.messenger(ctl, tab, host)  # noqa: E731

    send("Unser Gespräch", "wt")
    assert flights == [1000.0] and ctl._messenger_text == "Unser Gespräch"
    clock["t"] += 26
    send("Barrierefreiheit", "vscode")                 # gesperrt: wird zurückgestellt
    send("Tests", "vscode")
    assert len(flights) == 1 and set(ctl._messenger_queue) == {"Barrierefreiheit", "Tests"}
    clock["t"] += 5                                    # Sperre vorbei: beide in einem Gang
    assert ctl._deliver_messenger()
    assert len(flights) == 2 and ctl._messenger_text == "Barrierefreiheit“ und „Tests"
    # Du bist inzwischen selbst in dem Programm, dessen Session fertig ist: kein Botengang nötig
    clock["t"] += 31
    ctl.focused, ctl.world.snap.host = True, "vscode"
    send("Schon gesehen", "vscode")
    assert len(flights) == 2 and not ctl._messenger_queue


def test_kanal_zufaellig_und_robust(monkeypatch):
    """Kanalname nicht erratbar; kaputte oder zu viele Nachrichten beenden das Pet nicht."""
    from claude_pet import streams
    monkeypatch.setattr(streams, "_CHANNEL", None)
    a = streams.channel_name()
    monkeypatch.setattr(streams, "_CHANNEL", None)
    assert streams.channel_name() != a                     # jeder Start würfelt neu
    hub = StreamHub()
    hub.handle(1, {"type": "hello", "app": "x", "workspace": "y"})
    import pytest
    with pytest.raises(ValueError):                        # wird in _on_read abgefangen und geloggt
        hub.handle(1, {"type": "start", "term": "t", "dims": {"columns": "viele", "rows": 3}})
    for i in range(streams.MAX_SESSIONS - len(hub.sessions)):
        hub.handle(1, {"type": "data", "term": f"t{i}", "d": "x"})
    with pytest.raises(ValueError):
        hub.handle(1, {"type": "data", "term": "einer-zu-viel", "d": "x"})
    assert len(hub.sessions) == streams.MAX_SESSIONS


def test_codezeilen_im_editor_bleiben_ebenen():
    """Regression: Mit VS Code als Terminal-Programm wurde das ganze Fenster als Terminal behandelt –
    die Codezeilen im Editor (Bildanalyse-Kanten) waren keine Ebenen mehr."""
    from claude_pet.world import ROW_VISION, World
    from conftest import make_snapshot
    snap = make_snapshot(["claude"], top=600, rows=10)          # Terminal-Fläche unten im Fenster
    snap.win_rect = (0, 0, 1400, 900)                           # ganzes Editor-Fenster
    snap.host = "vscode"
    w = World()
    w.update(snap)
    editor, terminal = (200, 100, 600), (700, 100, 600)         # (y, x0, x1)
    w.set_vision([editor, terminal])
    assert [p.y for p in w.platforms if p.row == ROW_VISION] == [200]
    assert not w.in_terminal(300, 200) and w.in_terminal(300, 700)
    snap.host = "wt"                                            # Windows Terminal: ganzes Fenster ist Terminal
    w.set_vision([editor, terminal])
    assert not [p for p in w.platforms if p.row == ROW_VISION]


def test_terminal_ohne_groesse_nach_reload():
    """Regression: Nach „Reload Window“ meldet VS Code für zurückgeholte Terminals keine Größe (0x0) –
    der Text wurde verworfen. Jetzt: gemerkte Zellgröße (gleicher Editor, gleiche Zeilenhöhe), und
    sobald die Größe nachgemeldet wird, genau kalibrieren."""
    rect = (300, 100, 300 + 100 * 9, 100 + 20 * 22)
    ta = (310, 100 + 5 * 22, 320, 100 + 6 * 22)                       # Eingabefeld: 22 px hoch
    # 1) früher einmal genau gemessen (frisches Terminal mit Größe)
    hub = _hub_mit_sitzung()
    vscode.build_pane(rect, next(iter(hub.sessions.values())), ta, now=10.0)
    # 2) neues Pet, zurückgeholtes Terminal ohne Größe
    hub2 = StreamHub()
    hub2.handle(1, {"type": "hello", "app": "Visual Studio Code", "workspace": "projekt"})
    hub2.handle(1, {"type": "start", "term": "t1", "cmd": "claude", "dims": None, "replay": True})
    hub2.handle(1, {"type": "data", "term": "t1", "d": "Hallo trotz Reload"})
    s = next(iter(hub2.sessions.values()))
    s.emu.last_feed = 0.0
    pane = vscode.build_pane(rect, s, ta, now=10.0)
    assert s.cell == (9.0, 22.0) and s.cell_guessed and len(pane.lines) == 20
    assert any("Hallo trotz Reload" in t for _, t in pane.lines)
    # anderer Monitor/Zoom (Eingabefeld 30 px): gemerkte Größe passt nicht -> lieber leer als falsch
    s.cell = None
    assert vscode.build_pane(rect, s, (310, 110, 320, 140), now=10.0).lines == []
    # 3) die Erweiterung meldet die Größe nach -> genau kalibrieren
    hub2.handle(1, {"type": "dims", "term": "t1", "dims": {"columns": 100, "rows": 20}})
    assert s.start_dims == (100, 20) and s.cell is None
    vscode.build_pane(rect, s, ta, now=10.0)
    assert s.cell == (9.0, 22.0) and not s.cell_guessed
