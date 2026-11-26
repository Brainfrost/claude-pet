"""Das Hirn: Haiku-Pläne lesen, Takt/Budget, Gedächtnis, Lagebild und Ausführen der Schritte."""
import random
from collections import deque
from types import SimpleNamespace as NS

from claude_pet import creatures, mind
from claude_pet.brain import Brain
from claude_pet.pet import Pet
from claude_pet.world import World
from conftest import make_snapshot

VB = (-2000, -100, 4000, 1200)


# ------------------------------------------------------------------ Plan lesen
def test_plan_lesen_robust():
    out = ('Klar!\n```json\n{"gedanke": "„Da tut sich was, ich schau mal!“", "plan": ['
           '{"tun": "zuschauen", "dauer": 9999}, {"tun": "fliegen", "dauer": 10}, '
           '{"tun": "fressen", "ziel": "TODO", "dauer": "abc"}, {"tun": "tanzen", "dauer": 300}, '
           '{"tun": "schlafen", "dauer": 60}], "merken": "Er testet gern spät."}\n```')
    thought, steps, memo = mind.parse_plan(out)
    assert thought == "Da tut sich was, ich schau mal!"
    assert [s.verb for s in steps] == ["zuschauen", "fressen", "tanzen"]      # Unbekanntes raus, max. 3
    assert steps[0].dauer == 240                                             # begrenzt
    assert steps[1].ziel == "TODO" and steps[1].dauer == 5                   # unlesbare Dauer -> Minimum
    assert steps[2].dauer == 4.0                                             # Sofort-Aktion
    assert memo == "Er testet gern spät."
    assert mind.parse_plan("kein json") == ("", [], "")
    assert mind.parse_plan('{"plan": "kaputt"}')[1] == []


# ------------------------------------------------------------------ Takt und Budget
def test_takt_und_budget():
    h = deque()
    t0 = 1000.0
    assert mind.due("normal", t0 + 10, 0, t0, False, 5, None, h) is None          # gleich nach Start: warten
    assert mind.due("normal", t0 + 41, 0, t0, False, 5, None, h) == "start"
    assert mind.due("normal", t0 + 100, t0 + 41, t0, True, 5, None, h) is None    # Plan läuft
    assert mind.due("normal", t0 + 41 + 181, t0 + 41, t0, False, 5, None, h) == "plan_fertig"
    assert mind.due("normal", t0 + 41 + 301, t0 + 41, t0, True, 5, None, h) == "takt"
    assert mind.due("normal", t0 + 41 + 301, t0 + 41, t0, True, 600, None, h) is None   # du bist weg
    assert mind.due("normal", t0 + 41 + 60, t0 + 41, t0, True, 600, "done", h) is None  # zu früh
    assert mind.due("normal", t0 + 41 + 80, t0 + 41, t0, True, 600, "done", h) == "done"
    assert mind.due("aus", t0 + 9999, 0, t0, False, 0, "done", h) is None
    full = deque([t0 + 100.0] * 15)
    assert mind.due("normal", t0 + 2000, t0 + 100, t0, False, 0, "error", full) is None  # Stundengrenze
    assert mind.due("sparsam", t0 + 41 + 300, t0 + 41, t0, False, 5, None, h) is None    # sparsam: seltener


def test_gedaechtnis():
    prof = {}
    for i in range(14):
        mind.remember(prof, f"Notiz {i}", "2026-11-26")
    assert not mind.remember(prof, "Notiz 13", "2026-11-27")                 # keine Dublette
    assert len(prof["memory"]) == mind.MEMORY_KEEP and prof["memory"][-1]["text"] == "Notiz 13"


# ------------------------------------------------------------------ Lagebild
def _setup(lines=None, personality="neugierig"):
    random.seed(3)
    w = World()
    snap = make_snapshot(lines or ["x" * 60, "  fix the TODO later  ", "y" * 60] * 4, rows=20,
                         tab_names=["Refactoring"], n_tabs=1, working=(0,))
    w.update(snap)
    pet = Pet(creatures.get("schleim"), "jung", personality)
    brain = Brain(pet, personality)
    for _ in range(200):                                             # landen lassen
        pet.on_world(w)
        pet.step(1 / 60, w, lambda x: 1100, VB, (0, 0))
    ctl = NS(pet=pet, brain=brain, world=w, prof={"name": "Günther", "memory": [{"t": "x", "text": "Er mag Tests."}]},
             quiet_reason=None, speech=NS(exe=None), work=NS(streak_start=None),
             terminal_focused=lambda: True)
    m = mind.Mind(ctl)
    brain.mind = m
    return ctl, m, w


def test_lagebild(monkeypatch):
    monkeypatch.setattr(mind.daily, "idle_seconds", lambda: 3.0)
    ctl, m, _ = _setup(["⏺ Ich schaue mir die fehlschlagenden Tests an.", "  ⎿  3 passed, 1 failed", "x" * 40])
    m.note_events([("error", "Error: token=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ungültig")])
    text = m.situation("error")
    assert "Fehler" in text and "Energie" in text and "„Refactoring“ arbeitet" in text
    assert "Er mag Tests." in text and "Bildschirm-Auszug" in text
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" not in text           # maskiert
    assert m.urgent == "error"


# ------------------------------------------------------------------ Ausführen
def _run(ctl, m, w, seconds):
    pet, brain = ctl.pet, ctl.brain
    for _ in range(int(seconds * 60)):
        brain.tick(1 / 60, w, (0, 0))
        pet.on_world(w)
        pet.step(1 / 60, w, lambda x: 1100, VB, (0, 0))


def test_schritte_werden_ausgefuehrt():
    ctl, m, w = _setup()
    pet, brain = ctl.pet, ctl.brain
    eaten = []
    brain.on_ate = lambda word, plat, start: eaten.append(word)
    m.plan = deque([mind.Step("sitzen", "", 20, 20), mind.Step("fressen", "TODO", 20, 20)])
    decide_before = brain.decide_t
    _run(ctl, m, w, 2)
    assert m.step.verb == "sitzen" and pet.state == "sit"
    assert brain.decide_t == decide_before, "während eines Plans würfelt das Brain nicht"
    _run(ctl, m, w, 15)
    assert eaten == [] and pet.state == "sit"               # sitzt die 20 s ab, frisst nicht nebenbei
    # danach: das gewünschte Futterwort anknabbern
    _run(ctl, m, w, 12)
    assert list(m.did)[:2] == ["sitzen", "fressen"] and eaten == ["TODO"]


def test_unmoeglicher_schritt_wird_uebersprungen():
    ctl, m, w = _setup()
    m.plan = deque([mind.Step("hinlaufen", "gibtsnicht", 30, 30), mind.Step("tanzen", "", 4, 4)])
    _run(ctl, m, w, 1)
    assert "hinlaufen (ging nicht)" in m.did
    assert m.step is None or m.step.verb == "tanzen"
