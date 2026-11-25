"""Die Fenster: das Pet selbst, seine Sprechblase, der Effekt am Tab-Reiter und die Debug-Ansicht.

Alle sind rahmenlos, durchsichtig und immer im Vordergrund. Bis auf das Pet lassen alle Klicks durch.
"""
import math
import time

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen,
                         QTransform)
from PyQt6.QtWidgets import QWidget

from . import creatures, effects, growth, winapi
from .world import OUTSIDE_ROWS, ROW_FLOOR, ROW_VISION, ROW_WINDOW

_OVERLAY_FLAGS = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                  | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                  | Qt.WindowType.WindowDoesNotAcceptFocus)
_CLICK_THROUGH = (winapi.WS_EX_TRANSPARENT | winapi.WS_EX_LAYERED | winapi.WS_EX_NOACTIVATE
                  | winapi.WS_EX_TOOLWINDOW)


class _Overlay(QWidget):
    """Basis für Fenster, durch die Klicks hindurchgehen."""

    def __init__(self):
        super().__init__(None, _OVERLAY_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def showEvent(self, e):
        super().showEvent(e)
        winapi.add_exstyle(int(self.winId()), _CLICK_THROUGH)


# ===================================================================== Pet
class PetWindow(QWidget):
    def __init__(self, ctl):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.ctl = ctl
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self._press = None
        self._samples = []
        self._stroke_dir = 0
        self._stroke_flips = []
        self._last_mx = None

    def showEvent(self, e):
        super().showEvent(e)
        winapi.add_exstyle(int(self.winId()), winapi.WS_EX_NOACTIVATE | winapi.WS_EX_TOOLWINDOW)

    def geometry_for(self, pet):
        w, h, fx, fy = self.ctl.renderer.size(pet.creature, pet.px)
        return int(pet.x - fx), int(pet.y - fy), w, h

    # --------------------------------------------------------------- Zeichnen
    def paintEvent(self, e):
        ctl = self.ctl
        pet = ctl.pet
        s = pet.px
        img = ctl.renderer.render(pet.creature, variant=ctl.prof["personality"], t=pet.anim_t,
                                  px=s, stage=pet.stage, accessories=growth.worn(ctl.prof),
                                  **pet.pose())
        if 0 < pet.spin < 1:
            # Purzelbaum: um die Körpermitte drehen
            w, h = img.width(), img.height()
            cy = h - pet.H / 2
            tr = QTransform().translate(w / 2, cy).rotate(pet.spin * 360 * pet.facing).translate(-w / 2, -cy)
            rot = img.transformed(tr, Qt.TransformationMode.FastTransformation)
            img = rot.copy(int((rot.width() - w) / 2), int((rot.height() - h) / 2), w, h)
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        if pet.clip_y is not None:
            # klettert in den / aus dem Reiter: oberhalb der Reiter-Unterkante unsichtbar
            top = int(pet.clip_y - self.geometry().y())
            p.setClipRect(0, max(0, top), img.width(), img.height())
        if pet.squash > 0.05:
            # Landung: kurz breit gedrückt, Füße bleiben am Boden
            k = pet.squash * 0.18
            w, h = img.width(), img.height()
            nw, nh = int(w * (1 + k)), int(h * (1 - k))
            p.drawImage(QRect((w - nw) // 2, h - nh, nw, nh), img)
        else:
            p.drawImage(0, 0, img)
        self._draw_effects(p, pet, img.width() / 2, (creatures.MARGIN_TOP - 1) * s, s)
        p.end()

    @staticmethod
    def _draw_effects(p, pet, cx, top, s):
        for fx in pet.effects:
            a = fx["age"]
            if a < 0:
                continue
            k = a / fx["life"]
            alpha = int(255 * (1 - k) ** 0.7)
            rise = k * 6 * s
            kind = fx["kind"]
            if kind == "heart":
                effects.draw_heart(p, cx - 2.5 * s + fx["dx"] * 0.5, top - rise, max(1, s - 1), alpha)
            elif kind == "z":
                effects.draw_text(p, cx + 4 * s + k * 2 * s, top + 2 * s - rise, "z", 5 * s, "#cfe8ff", alpha)
            elif kind == "♪":
                effects.draw_text(p, cx + fx["dx"] * 0.5, top + 2 * s - rise, "♪", 6 * s, "#b8f2ff", alpha)
            else:
                effects.draw_text(p, cx - s, top + 2 * s - rise * 0.3, kind, 7 * s, "#ffd166", alpha)

    # --------------------------------------------------------------- Maus
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            g = e.globalPosition()
            self._press = (g.x(), g.y())
            self._samples = [(time.perf_counter(), g.x(), g.y())]

    def mouseMoveEvent(self, e):
        g = e.globalPosition()
        pet = self.ctl.pet
        if self._press:
            if pet.state != "held" and abs(g.x() - self._press[0]) + abs(g.y() - self._press[1]) > 5:
                pet.grab()
            if pet.state == "held":
                # am Nacken halten: Mauspunkt sitzt knapp unterm Kopf
                pet.x, pet.y = g.x(), g.y() + pet.H * 0.75
                now = time.perf_counter()
                self._samples.append((now, g.x(), g.y()))
                self._samples = [sm for sm in self._samples if now - sm[0] < 0.1]
                self.ctl.place()
            return
        # Streicheln: hin und her über das Pet fahren
        if self._last_mx is not None:
            d = 1 if g.x() > self._last_mx + 1 else -1 if g.x() < self._last_mx - 1 else 0
            if d and d != self._stroke_dir:
                if self._stroke_dir:
                    now = time.perf_counter()
                    self._stroke_flips = [t for t in self._stroke_flips if now - t < 1.5] + [now]
                    if len(self._stroke_flips) >= 4:
                        self._stroke_flips = []
                        self.ctl.on_stroke()
                self._stroke_dir = d
        self._last_mx = g.x()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self._press:
            return
        self._press = None
        if self.ctl.pet.state != "held":
            self.ctl.on_poke()
            return
        vx = vy = 0.0
        if len(self._samples) >= 2:
            (t0, x0, y0), (t1, x1, y1) = self._samples[0], self._samples[-1]
            if t1 - t0 > 0.005:
                vx, vy = (x1 - x0) / (t1 - t0), (y1 - y0) / (t1 - t0)
        g = e.globalPosition()
        self.ctl.on_release(g.x(), g.y(), vx, vy)

    def leaveEvent(self, e):
        self._last_mx = None
        self._stroke_dir = 0


# ===================================================================== Reiter-Effekt
class TabFx(_Overlay):
    """Kleiner Effekt am Tab-Reiter: Wackeln beim Hineinklettern, Staubwölkchen beim Verschwinden."""
    LIFE = 0.5

    def __init__(self):
        super().__init__()
        self.fx = []            # (art, start, x, y) in Fensterkoordinaten
        self.box = (0, 0, 0, 0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def play(self, kind, x, y, tab_rect):
        l, t, r, b = tab_rect if tab_rect is not None else (x - 80, y - 40, x + 80, y)
        pad = 14
        self.setGeometry(int(l - pad), int(t - pad), int(r - l + 2 * pad), int(b - t + 3 * pad))
        self.box = (pad, pad, r - l, b - t)
        self.fx.append((kind, time.perf_counter(), x - l + pad, y - t + pad))
        if not self.isVisible():
            self.show()
        self.timer.start(16)

    def _tick(self):
        now = time.perf_counter()
        self.fx = [f for f in self.fx if now - f[1] < self.LIFE]
        if not self.fx:
            self.timer.stop()
            self.hide()
            return
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.perf_counter()
        bx, by, bw, bh = self.box
        for kind, t0, x, y in self.fx:
            k = (now - t0) / self.LIFE
            a = int(200 * (1 - k))
            if kind == "wiggle":
                dx = math.sin(k * 40) * 3 * (1 - k)
                p.setPen(QPen(QColor(255, 255, 255, a), 2))
                p.setBrush(QColor(255, 255, 255, int(a * 0.18)))
                p.drawRoundedRect(int(bx + dx), int(by), int(bw), int(bh), 6, 6)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(220, 220, 230, int(a * 0.8)))
                for i, ang in enumerate((-2.4, -1.9, -1.2, -0.6, 0.0, 0.6)):
                    r = 3 + k * 9
                    d = 6 + k * 18
                    cx = x + math.cos(ang + 1.57) * d * (1 if i % 2 else -1)
                    cy = y + 4 + abs(math.sin(ang)) * d * 0.5
                    p.drawEllipse(int(cx - r), int(cy - r), int(2 * r), int(2 * r))
        p.end()


# ===================================================================== Sprechblase
class Bubble(_Overlay):
    """Sprechblase über dem Pet."""
    MAX_W = 260
    PAD = 9
    TAIL = 9

    def __init__(self):
        super().__init__()
        self.font_ = QFont("Segoe UI")
        self.font_.setPixelSize(14)
        self.text = ""
        self.until = 0.0
        self.tail_x = 0
        self.tail_up = False
        self.text_rect = QRect()

    def say(self, text):
        self.text = text
        self.until = time.perf_counter() + 3.5 + 0.06 * len(text)
        r = QFontMetrics(self.font_).boundingRect(QRect(0, 0, self.MAX_W, 1000), Qt.TextFlag.TextWordWrap, text)
        self.text_rect = QRect(self.PAD, self.PAD, r.width() + 2, r.height())
        self.resize(r.width() + 2 * self.PAD + 2, r.height() + 2 * self.PAD + self.TAIL)

    def follow(self, pet, pet_visible):
        expired = time.perf_counter() > self.until
        if not self.text or expired or not pet_visible:
            if self.isVisible():
                self.hide()
            if expired:
                self.text = ""
            return
        w, h = self.width(), self.height()
        x = int(pet.x - w / 2)
        y = int(pet.y - pet.H - 2 - h)
        scr = QGuiApplication.screenAt(QPoint(int(pet.x), int(pet.y - pet.H / 2)))
        if scr:
            g = scr.geometry()
            x = max(g.x() + 2, min(x, g.x() + g.width() - w - 2))
            if y < g.y():
                y = int(pet.y + 4)          # kein Platz oben: unter das Pet
        self.tail_x = int(min(max(pet.x - x, 14), w - 14))
        self.tail_up = y > pet.y - pet.H
        self.move(x, y)
        if not self.isVisible():
            self.show()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        top = self.TAIL if self.tail_up else 0
        body = QRect(1, top + 1, w - 2, h - self.TAIL - 2)
        path = QPainterPath()
        path.addRoundedRect(body.x(), body.y(), body.width(), body.height(), 8, 8)
        tail = QPainterPath()
        tx = self.tail_x
        if self.tail_up:
            tail.moveTo(tx - 7, top + 2)
            tail.lineTo(tx, 1)
            tail.lineTo(tx + 7, top + 2)
        else:
            tail.moveTo(tx - 7, body.bottom() - 1)
            tail.lineTo(tx, h - 1)
            tail.lineTo(tx + 7, body.bottom() - 1)
        p.setPen(QPen(QColor("#e8e4f0"), 2))
        p.setBrush(QColor(27, 21, 48, 238))
        p.drawPath(path.united(tail))
        p.setPen(QColor("#ffffff"))
        p.setFont(self.font_)
        p.drawText(self.text_rect.translated(0, top), Qt.TextFlag.TextWordWrap, self.text)
        p.end()


# ===================================================================== Debug
class DebugOverlay(_Overlay):
    """Entwickler-Ansicht über allen Bildschirmen: erkannte Ebenen, Tabs und was das Pet vorhat.

    Farben: Terminal-Text blau, Pane-Boden rot, Fensterkanten gelb, Bildanalyse grün.
    """
    COLORS = {ROW_FLOOR: "#ff4d6d", ROW_WINDOW: "#ffd166", ROW_VISION: "#4dff88"}

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl

    def sync(self):
        g = QGuiApplication.primaryScreen().virtualGeometry()
        if self.geometry() != g:
            self.setGeometry(g)
        self.update()

    def paintEvent(self, e):
        ctl = self.ctl
        w, pet = ctl.world, ctl.pet
        ox, oy = self.geometry().x(), self.geometry().y()
        p = QPainter(self)
        for q in w.platforms:
            c = QColor(self.COLORS.get(q.row, "#4dd0ff"))
            c.setAlpha(190)
            p.fillRect(QRect(int(q.x0 - ox), int(q.y - oy), max(1, int(q.x1 - q.x0)), 2), c)
        if w.ok:
            for tab in w.snap.tabs:
                p.setPen(QColor("#7CFC00" if tab.selected else "#ffd166"))
                tl, tt, tr, tb = tab.rect
                p.drawRect(int(tl - ox), int(tt - oy), int(tr - tl), int(tb - tt))
                p.drawText(int(tl - ox) + 4, int(tb - oy) + 14, tab.state)
        if pet.placed and pet.state != "hidden":
            b = ctl.brain
            sp = pet.support
            where = ("draußen" if sp is not None and sp.row in OUTSIDE_ROWS else
                     f"Zeile {sp.row}" if sp is not None else "in der Luft")
            lines = [f"{pet.state}  ·  {where}",
                     f"Ziel: {b.goal[0] if b.goal else '–'}  ·  Laune {pet.mood:.0f}  ·  Bindung {pet.bond:.0f}"]
            x, y = int(pet.x - ox + pet.W / 2 + 8), int(pet.y - oy - pet.H)
            p.fillRect(x - 4, y - 14, 300, 18 * len(lines) + 6, QColor(0, 0, 0, 150))
            p.setPen(QColor("#ffffff"))
            for i, t in enumerate(lines):
                p.drawText(x, y + i * 18, t)
        p.end()
