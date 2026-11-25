"""Kleine Effekte über dem Pet: Herzchen und Zeichen (z, !, ?, ♪ …)."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter

HEART = [".r.r.", "rrrrr", ".rrr.", "..r.."]
HEART_COLOR = "#ff4d6d"
OUTLINE = "#1b1530"


def draw_heart(p: QPainter, ox, oy, s, alpha=255):
    c = QColor(HEART_COLOR)
    c.setAlpha(alpha)
    for y, row in enumerate(HEART):
        for x, ch in enumerate(row):
            if ch != ".":
                p.fillRect(int(ox + x * s), int(oy + y * s), s, s, c)


def draw_text(p: QPainter, x, y, text, size_px, color="#ffffff", alpha=255):
    """Text mit dunklem Rand, damit er auf jedem Hintergrund lesbar ist."""
    f = QFont("Consolas")
    f.setPixelSize(max(8, int(size_px)))
    f.setBold(True)
    p.setFont(f)
    shadow = QColor(OUTLINE)
    shadow.setAlpha(alpha)
    p.setPen(shadow)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        p.drawText(int(x + dx), int(y + dy), text)
    c = QColor(color)
    c.setAlpha(alpha)
    p.setPen(c)
    p.drawText(int(x), int(y), text)
    p.setPen(Qt.PenStyle.NoPen)
