"""Fenster und Effekte zeichnen (offscreen) – darf nicht abstürzen."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter

from claude_pet import creatures
from claude_pet.ball import Ball
from claude_pet.brain import Brain
from claude_pet.pet import Pet
from claude_pet.windows import BallWindow, BiteFx, Bubble, DebugOverlay, PetWindow, TabFx
from claude_pet.world import World
from conftest import make_snapshot


class Ctl:
    pass


def test_all_effect_kinds_draw(qapp):
    pet = Pet(creatures.get("spatz"), "jung", "verspielt")
    for kind in ("heart", "z", "♪", "gähn", "krümel", "konfetti", "!", "*", "…", "?", "staub", "hatschi", "schale", "funkeln"):
        pet._effect(kind, life=1.0, dx=0.5)
    for e in pet.effects:
        e["age"] = 0.4
    img = QImage(200, 200, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    PetWindow._draw_effects(p, pet, 100, 50, 3)
    p.end()


def test_overlays_render(qapp):
    c = Ctl()
    c.world = World()
    c.world.update(make_snapshot(["hallo"]))
    c.pet = Pet(creatures.get("katze"), "jung", "faul")
    c.pet.placed, c.pet.x, c.pet.y = True, 100, 300
    c.brain = Brain(c.pet, "faul")
    c.debug_scan = {0: [(500, 10, 300)]}
    c.ball = Ball(50, 50, line_h=20)
    bw = BallWindow(c)
    bw.place(c.ball)
    assert not bw.grab().isNull()
    bite = BiteFx()
    bite.bite((10, 10, 40, 20), "#101010")
    assert not bite.grab().isNull()
    d = DebugOverlay(c)
    d.sync()
    assert not d.grab().isNull()
    b = Bubble()
    b.say("Hallo 😀")
    b.follow(c.pet, True)
    t = TabFx()
    t.play("puff", 100, 0, None)
    assert not b.grab().isNull() and not t.grab().isNull()
