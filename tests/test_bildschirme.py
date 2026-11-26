"""Mehrere Bildschirme: keine Lücken im Rechteck um alle Monitore, Streicheln über die Mausposition."""
from types import SimpleNamespace as NS

from claude_pet import creatures
from claude_pet.ball import Ball
from claude_pet.controller import Controller
from claude_pet.pet import Pet
from claude_pet.world import World, keep_on_screens, screen_span

# Antons Anordnung: links ein hochkant gestellter Monitor, Mitte (Hauptbildschirm), rechts
SCREENS = [(-1080, -395, 0, 1525), (0, 0, 1920, 1080), (1920, 0, 3840, 1080)]
VB = (-1080, -395, 3840, 1525)                    # das Rechteck um alle – mit Lücken über/unter Mitte und rechts


def floor(x):
    return 1872 - 395 if x < 0 else (1020 if x < 1920 else 1032)


def test_hilfsfunktionen():
    assert keep_on_screens(SCREENS, 500, 600, 10, 40)[2:] == (False, False)     # auf dem Bildschirm: nichts tun
    x, y, side, cap = keep_on_screens(SCREENS, 500, -200, 10, 40)               # Lücke über der Mitte
    assert (x, y) == (500, 40) and cap
    x, y, side, cap = keep_on_screens(SCREENS, 3900, 500, 10, 40)               # rechts daneben
    assert x == 3830 and side
    assert screen_span(SCREENS, 3000, 1030) == (1920, 3840)
    assert screen_span(SCREENS, -500, 1400) == (-1080, 0)


def _pet(x, y):
    w = World()
    pet = Pet(creatures.get("geist"), "jung", "verspielt")
    pet.grace, pet.screens = 0, SCREENS
    pet.placed, pet.x, pet.y = True, x, y
    return w, pet


def test_hochwerfen_ueber_der_mitte_bleibt_sichtbar():
    w, pet = _pet(900, 900)
    pet.drop(0, -4000)                                # kräftig nach oben werfen
    top = pet.y
    for _ in range(60 * 4):
        pet.step(1 / 60, w, floor, VB, (0, 0))
        top = min(top, pet.y - pet.H)
    assert top >= 0, f"flog in die Lücke über dem Hauptbildschirm (bis y={top:.0f})"
    assert pet.grounded and abs(pet.y - 1020) < 1


def test_auf_dem_boden_rechts_nicht_ins_nichts_laufen():
    w, pet = _pet(3700, 900)
    for _ in range(60 * 3):                           # auf den Boden des rechten Bildschirms fallen
        pet.step(1 / 60, w, floor, VB, (0, 0))
    assert pet.grounded and pet.support.x1 == 3840, "Boden nur so breit wie der Bildschirm"
    pet.walk_to(5000)
    for _ in range(60 * 20):
        pet.step(1 / 60, w, floor, VB, (0, 0))
        assert pet.x <= 3840, "rechts aus dem Bildschirm gelaufen"


def test_ball_bleibt_sichtbar():
    w = World()
    ball = Ball(2500, 800, 300, -5000)
    ball.screens = SCREENS
    for _ in range(60 * 5):
        ball.step(1 / 60, w, floor, VB)
        assert ball.y - ball.r >= -1 and ball.x <= 3840


def test_streicheln_auch_ueber_den_rand_hinaus():
    pet = NS(x=500.0, y=600.0, W=40.0, H=40.0, placed=True, state="idle")
    strokes = []
    fake = NS(pet=pet, win=NS(isVisible=lambda: True), on_stroke=lambda: strokes.append(1))
    t = 0.0
    for x in (470, 535, 470, 535, 470, 535):          # hin und her, jeweils bis knapp über den Rand
        Controller._track_stroke(fake, (x, 590), t)
        t += 0.2
    assert strokes == [1]
    Controller._track_stroke(fake, (900, 590), t)     # weit weg: zählt nicht weiter
    assert fake._stroke_last is None
