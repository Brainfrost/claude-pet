"""Platzhalter-Figur (Pixel-Blob-Katze), bis das endgültige Design feststeht.

Pixel-Maps: '.' = transparent, sonst Schlüssel in PALETTE. Die Augen werden je nach
Blickrichtung/Stimmung prozedural gesetzt.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter

PALETTE = {
    "O": "#2b2140",  # Umriss
    "a": "#f4a261",  # Fell
    "b": "#ffe0b8",  # Bauch
    "i": "#ff8fab",  # Ohr innen
    "c": "#f08a6c",  # Bäckchen
    "m": "#2b2140",  # Mund
    "W": "#ffffff",  # Augenweiß
    "p": "#1b1530",  # Pupille
    "r": "#ff4d6d",  # Herz
}

BODY = [
    "...OO......OO...",
    "..OiaO....OaiO..",
    "..OaaaOOOOaaaO..",
    ".OaaaaaaaaaaaaO.",
    ".OaaaaaaaaaaaaO.",
    "OaaaWWaaaaWWaaaO",
    "OaaaWWaaaaWWaaaO",
    "OaccaaaaaaaaccaO",
    "OaaaaaammaaaaaaO",
    "OaaabbbbbbbbaaaO",
    ".OaabbbbbbbbaaO.",
    ".OaaabbbbbbaaaO.",
    "..OOaaaaaaaaOO..",
    "...OOOOOOOOOO...",
]
FEET = {
    "stand": "...OO......OO...",
    "walk1": "..OO.......OO...",
    "walk2": "....OO......OO..",
    "dangle": "...O.O....O.O...",
    "sit": "..OOOO....OOOO..",
}
GRID_W = 16
GRID_H = len(BODY) + 1          # + Fußzeile
EYES = ((4, 5), (10, 5))        # linke obere Ecke je Auge (2x2)

HEART = [".r.r.", "rrrrr", ".rrr.", "..r.."]


def _eye_pixels(mode, look_x, look_y):
    """Liefert {(x, y): farbschlüssel} für beide Augen."""
    px = {}
    for ex, ey in EYES:
        if mode == "closed":
            px.update({(ex, ey): "a", (ex + 1, ey): "a", (ex, ey + 1): "O", (ex + 1, ey + 1): "O"})
        elif mode == "happy":
            px.update({(ex, ey): "a", (ex + 1, ey): "a", (ex, ey + 1): "a", (ex + 1, ey + 1): "a"})
            if ex < 8:
                px.update({(ex, ey + 1): "O", (ex + 1, ey): "O"})
            else:
                px.update({(ex, ey): "O", (ex + 1, ey + 1): "O"})
        else:
            for dx in (0, 1):
                for dy in (0, 1):
                    px[(ex + dx, ey + dy)] = "W"
            col = ex + (1 if look_x > 0 else 0)
            if mode == "wide":
                px[(col, ey)] = "p"
            else:
                rows = (ey,) if look_y < 0 else (ey + 1,) if look_y > 0 else (ey, ey + 1)
                for ry in rows:
                    px[(col, ry)] = "p"
    return px


def draw_pet(p: QPainter, ox, oy, s, *, feet="stand", eyes="open", look=(0, 0), bob=0,
             squash=0.0):
    """Zeichnet die Figur mit linker oberer Ecke (ox, oy) und Pixelgröße s.
    bob: Körper um n Pixel nach unten (Atmen/Sitzen). squash: 0..1 Landungs-Stauchung."""
    eye_px = _eye_pixels(eyes, *look)
    body_off = bob
    # Stauchung: obere Reihen rücken nach unten, Figur wirkt breiter gedrückt
    sq_rows = int(round(squash * 3))
    for y, row in enumerate(BODY):
        for x, ch in enumerate(row):
            key = eye_px.get((x, y), ch)
            if key == ".":
                continue
            yy = y + body_off
            if sq_rows and y < sq_rows:
                yy = y + body_off + (sq_rows - y) // 2 + 1
            p.fillRect(int(ox + x * s), int(oy + yy * s), s, s, QColor(PALETTE[key]))
    frow = FEET[feet]
    for x, ch in enumerate(frow):
        if ch != ".":
            p.fillRect(int(ox + x * s), int(oy + (GRID_H - 1) * s), s, s, QColor(PALETTE[ch]))


def draw_heart(p: QPainter, ox, oy, s, alpha=255):
    for y, row in enumerate(HEART):
        for x, ch in enumerate(row):
            if ch != ".":
                c = QColor(PALETTE[ch])
                c.setAlpha(alpha)
                p.fillRect(int(ox + x * s), int(oy + y * s), s, s, c)


def draw_text(p: QPainter, x, y, text, size_px, color="#ffffff", alpha=255):
    f = QFont("Consolas")
    f.setPixelSize(max(8, int(size_px)))
    f.setBold(True)
    p.setFont(f)
    c = QColor(color)
    c.setAlpha(alpha)
    # dunkler Rand für Lesbarkeit auf jedem Hintergrund
    shadow = QColor("#1b1530")
    shadow.setAlpha(alpha)
    p.setPen(shadow)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        p.drawText(int(x + dx), int(y + dy), text)
    p.setPen(c)
    p.drawText(int(x), int(y), text)
    p.setPen(Qt.PenStyle.NoPen)
