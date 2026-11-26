"""Die Fenster: das Pet selbst, seine Sprechblase, der Effekt am Tab-Reiter und die Debug-Ansicht.

Alle sind rahmenlos, durchsichtig und immer im Vordergrund. Bis auf das Pet lassen alle Klicks durch.
"""
import math
import time

from PyQt6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen,
                         QTransform)
from PyQt6.QtWidgets import QWidget

from . import creatures, effects, osapi
from .pet import GROUND, NO_BODY
from .world import OUTSIDE_ROWS, ROW_FLOOR, ROW_VISION, ROW_WINDOW

SHADOW_ROWS = 1         # Rasterpixel unter den Füßen, in die der Schatten reicht

_OVERLAY_FLAGS = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                  | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                  | Qt.WindowType.WindowDoesNotAcceptFocus)


class _Overlay(QWidget):
    """Basis für Fenster, durch die Klicks hindurchgehen."""

    def __init__(self):
        super().__init__(None, _OVERLAY_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def showEvent(self, e):
        super().showEvent(e)
        osapi.prepare_overlay(int(self.winId()), click_through=True)


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
        osapi.prepare_overlay(int(self.winId()))

    def geometry_for(self, pet):
        """Fenster = Bild der Figur plus ein Streifen unter den Füßen für den Schatten."""
        w, h, fx, fy = self.ctl.renderer.size(pet.creature, pet.px)
        return int(pet.x - fx), int(pet.y - fy), w, h + SHADOW_ROWS * pet.px

    # --------------------------------------------------------------- Zeichnen
    def paintEvent(self, e):
        ctl = self.ctl
        pet = ctl.pet
        s = pet.px
        img = ctl.renderer.render(pet.creature, variant=ctl.prof["personality"], t=pet.anim_t,
                                  px=s, stage=pet.stage, accessories=ctl.accessories(),
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
        b = pet.body()
        if (pet.state in GROUND and pet.support is not None) or pet.windup > 0:
            # weicher Schatten unter den Füßen (verschwindet im Sprung)
            w, h = img.width(), img.height()
            sw, sh = pet.W * 0.72 * b["sx"], max(2.0, s * 1.5)
            p.setBrush(QColor(0, 0, 0, 55))
            p.drawEllipse(QRectF(w / 2 - sw / 2 + b["dx"] * s, h - sh / 2, sw, sh))
            p.setBrush(Qt.BrushStyle.NoBrush)
        if b != NO_BODY:
            # Geste/Landung/Flug: um die Fußmitte (gehalten: um den Kopf) strecken und neigen
            w, h = img.width(), img.height()
            ax, ay = w / 2, (creatures.MARGIN_TOP * s if b["pivot"] == "kopf" else h)
            p.translate(ax + b["dx"] * s, ay + b["dy"] * s)
            p.rotate(b["rot"])
            p.scale(b["sx"], b["sy"])
            p.translate(-ax, -ay)
        p.drawImage(0, 0, img)
        p.resetTransform()
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
            elif kind == "gähn":
                effects.draw_text(p, cx + 3 * s, top + 3 * s - rise * 0.5, "gähn", 4 * s, "#cfe8ff", alpha)
            elif kind == "hatschi":
                effects.draw_text(p, cx + 4 * s * pet.facing + k * 3 * s * pet.facing, top + 4 * s - rise * 0.4,
                                  "hatschi!", 4 * s, "#ffffff", alpha)
            elif kind == "schale":
                # Eierschale fliegt in Splittern auseinander und fällt
                foot = top + (pet.creature["h"] + 1) * s
                for i, ang in enumerate((-2.6, -2.1, -1.4, -0.9, -0.4, -2.9)):
                    dist = (6 + (i % 3) * 2.5) * s * k
                    px_ = cx + math.cos(ang) * dist
                    py_ = foot - 3 * s + math.sin(ang) * dist * 0.8 + k * k * 9 * s
                    size = max(2, int(s * (1.6 if i % 2 else 1.2)))
                    for col, off in (("#8b7b5a", 0), ("#f4ecd8", max(1, size // 3))):
                        c = QColor(col)
                        c.setAlpha(alpha)
                        p.fillRect(int(px_) + off, int(py_) + off, size - off, size - off, c)
            elif kind == "funkeln":
                # kleines Pluszeichen-Funkeln, das kurz aufblitzt
                ang = fx["dx"]
                r = (5 + 2 * math.sin(ang * 3)) * s
                px_, py_ = cx + math.cos(ang) * r, top + 9 * s + math.sin(ang) * r * 0.7
                arm = max(1, int(s * (1.6 - abs(k - 0.4) * 2)))
                c = QColor("#fff4b0")
                c.setAlpha(alpha)
                q = max(1, s // 2)
                p.fillRect(int(px_ - arm), int(py_ - q / 2), 2 * arm, q, c)
                p.fillRect(int(px_ - q / 2), int(py_ - arm), q, 2 * arm, c)
            elif kind == "staub":
                # kleine Wölkchen an den Füßen, die zur Seite wegpuffen und vergehen
                foot = top + (pet.creature["h"] + 1) * s
                c = QColor("#d9d4c7")
                c.setAlpha(int(alpha * 0.8))
                sides = (-1, 1) if not fx["dx"] else (1 if fx["dx"] > 0 else -1,)
                for side in sides:
                    for i in range(3):
                        size = max(1, int(s * (1.4 - i * 0.35) * (1 - 0.5 * k)))
                        px_ = cx + side * (pet.W * 0.25 + (i * 1.6 + k * 4) * s)
                        py_ = foot - s - i * 0.6 * s - k * 2 * s
                        p.fillRect(int(px_ - size / 2), int(py_ - size), size, size, c)
            elif kind == "krümel":
                c = QColor("#c8a26b")
                c.setAlpha(alpha)
                for i in range(3):
                    p.fillRect(int(cx + fx["dx"] + (i - 1) * s * 1.5), int(top + 15 * s + k * 5 * s + i * s),
                               max(1, s // 2 + 1), max(1, s // 2 + 1), c)
            elif kind == "konfetti":
                colors = ("#ff4d6d", "#ffd166", "#4dd0ff", "#7CFC00", "#c77dff", "#ffffff")
                for i, col in enumerate(colors):
                    a_ = fx["dx"] + i * 1.05
                    c = QColor(col)
                    c.setAlpha(alpha)
                    px_ = cx + math.cos(a_) * k * 9 * s
                    py_ = top + 4 * s - math.sin(a_) * k * 7 * s + k * k * 10 * s
                    p.fillRect(int(px_), int(py_), max(2, s), max(2, s), c)
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
        # Streicheln erkennt der Controller über die Mausposition (_track_stroke)

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


# ===================================================================== Ball
class BallWindow(QWidget):
    """Der Ball: zum Greifen und Werfen (wie das Pet), sonst gehen Klicks am Rand durch."""

    def __init__(self, ctl):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.ctl = ctl
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._samples = []

    def showEvent(self, e):
        super().showEvent(e)
        osapi.prepare_overlay(int(self.winId()))

    def place(self, ball):
        d = ball.r * 2 + 4
        self.setGeometry(int(ball.x - d / 2), int(ball.y - d / 2), d, d)
        self.update()

    def paintEvent(self, e):
        ball = self.ctl.ball
        if ball is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = ball.r
        c = self.width() / 2
        p.setPen(QPen(QColor("#2b2140"), 2))
        p.setBrush(QColor("#ff4d6d"))
        p.drawEllipse(int(c - r), int(c - r), 2 * r, 2 * r)
        p.setPen(QPen(QColor("#ffffff"), max(2, r // 3)))
        a = ball.angle
        p.drawLine(int(c + math.cos(a) * r * 0.85), int(c + math.sin(a) * r * 0.85),
                   int(c - math.cos(a) * r * 0.85), int(c - math.sin(a) * r * 0.85))
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.ctl.ball is not None:
            self.ctl.grab_ball()
            g = e.globalPosition()
            self._samples = [(time.perf_counter(), g.x(), g.y())]

    def mouseMoveEvent(self, e):
        ball = self.ctl.ball
        if ball is None or ball.carried_by != "user":
            return
        g = e.globalPosition()
        ball.x, ball.y = g.x(), g.y()
        now = time.perf_counter()
        self._samples = [s for s in self._samples if now - s[0] < 0.1] + [(now, g.x(), g.y())]
        self.place(ball)

    def mouseReleaseEvent(self, e):
        ball = self.ctl.ball
        if ball is None or ball.carried_by != "user":
            return
        vx = vy = 0.0
        if len(self._samples) >= 2:
            (t0, x0, y0), (t1, x1, y1) = self._samples[0], self._samples[-1]
            if t1 - t0 > 0.005:
                vx, vy = (x1 - x0) / (t1 - t0), (y1 - y0) / (t1 - t0)
        ball.throw(vx, vy)


# ===================================================================== Biss im Text
class BiteFx(_Overlay):
    """Ein angeknabbertes Wort: die vordere Hälfte verschwindet unter einem Biss, ein paar Krümel."""
    LIFE = 7.0

    def __init__(self):
        super().__init__()
        self.bites = []         # (start, rect, Farbe)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def bite(self, rect, color):
        self.bites.append((time.perf_counter(), rect, color))
        self._fit()
        if not self.isVisible():
            self.show()
        self.timer.start(50)
        self.update()

    def _tick(self):
        now = time.perf_counter()
        n = len(self.bites)
        self.bites = [b for b in self.bites if now - b[0] < self.LIFE]
        if not self.bites:
            self.timer.stop()
            self.hide()
            return
        if len(self.bites) != n:
            self._fit()
        self.update()

    def _fit(self):
        """Fenster nur so groß wie die Bissspuren (+ Rand für Krümel) – nie bildschirmfüllend."""
        pad = 16
        l = min(r[0] for _, r, _ in self.bites) - pad
        t = min(r[1] for _, r, _ in self.bites) - pad
        rr = max(r[0] + r[2] for _, r, _ in self.bites) + pad
        b = max(r[1] + r[3] for _, r, _ in self.bites) + pad
        self.setGeometry(int(l), int(t), int(rr - l), int(b - t))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ox, oy = self.geometry().x(), self.geometry().y()
        now = time.perf_counter()
        for t0, (x, y, w, h), col in self.bites:
            k = (now - t0) / self.LIFE
            alpha = 255 if k < 0.85 else int(255 * (1 - k) / 0.15)
            c = QColor(col)
            c.setAlpha(alpha)
            path = QPainterPath()
            bw = w * 0.55                       # vordere Hälfte "abgebissen"
            path.moveTo(x - ox, y - oy)
            path.lineTo(x - ox + bw, y - oy)
            for i in range(3):                  # Bissspuren: drei Halbkreise am Rand
                cy_ = y - oy + h * (i + 0.5) / 3
                path.arcTo(x - ox + bw - h / 6, cy_ - h / 6, h / 3, h / 3, 90, 180)
            path.lineTo(x - ox, y - oy + h)
            path.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawPath(path)
            crumb = QColor("#c8a26b")
            crumb.setAlpha(alpha)
            for i in range(4):
                p.fillRect(int(x - ox + bw + 4 + i * 5), int(y - oy + h + 2 + (i % 2) * 3), 3, 3, crumb)
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


class ThoughtBubble(Bubble):
    """Gedankenwolke: was das Hirn gerade vorhat (kursiv, mit Gedanken-Kringeln statt Zipfel)."""
    TAIL = 14

    def __init__(self):
        super().__init__()
        self.font_.setItalic(True)
        self.font_.setPixelSize(13)

    def say(self, text):
        super().say(text)
        self.until = time.perf_counter() + 4.5 + 0.05 * len(text)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        top = self.TAIL if self.tail_up else 0
        body = QRect(1, top + 1, w - 2, h - self.TAIL - 2)
        p.setPen(QPen(QColor("#cfc8e6"), 1.5))
        p.setBrush(QColor(44, 38, 70, 225))
        p.drawRoundedRect(body, 14, 14)
        tx = self.tail_x
        dots = ((tx, 4.0, 4), (tx - 4, 10.0, 2.6)) if not self.tail_up else ((tx, top - 4.0, 4), (tx - 4, top - 10.0, 2.6))
        for x, dy, r in dots:
            y = body.bottom() + dy if not self.tail_up else dy
            p.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
        p.setPen(QColor("#e9e4ff"))
        p.setFont(self.font_)
        p.drawText(self.text_rect.translated(0, top), Qt.TextFlag.TextWordWrap, self.text)
        p.end()


# ===================================================================== Bug-Jagd
class HuntOverlay(QWidget):
    """Spielfeld über dem Pane: Käfer sind anklickbar, der Rest lässt Klicks durch (Alpha 0)."""

    def __init__(self, ctl):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.ctl = ctl
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def showEvent(self, e):
        super().showEvent(e)
        osapi.prepare_overlay(int(self.winId()))

    def sync(self, rect):
        l, t, r, b = rect
        if self.geometry() != QRect(int(l), int(t), int(r - l), int(b - t)):
            self.setGeometry(int(l), int(t), int(r - l), int(b - t))
        self.update()

    def mousePressEvent(self, e):
        g = e.globalPosition()
        self.ctl.hunt_click(g.x(), g.y())

    def paintEvent(self, e):
        hunt = self.ctl.hunt
        if hunt is None:
            return
        from .dreams import ICONS
        rows, colors = ICONS["kaefer"]
        s = max(2, self.ctl.pet.px - 1)
        ox, oy = self.geometry().x(), self.geometry().y()
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        for b in hunt.bugs:
            cx, by = b.x - ox, b.y - oy
            if b.alive:
                # unsichtbarer Klick-Hof (Alpha 1), damit man die kleinen Käfer gut trifft
                p.setBrush(QColor(0, 0, 0, 1))
                r = 7 * s
                p.drawEllipse(QRectF(cx - r, by - 3.5 * s - r, 2 * r, 2 * r))
                leg = int(b.t * 12) % 2
                for y, row in enumerate(rows):
                    for x, ch in enumerate(row):
                        if ch in colors:
                            xx = x if b.vx >= 0 else 6 - x
                            dy = (leg if y in (0, 1) else 0)
                            p.fillRect(QRectF(cx - 3.5 * s + xx * s, by - 7 * s + (y + dy) * s, s, s),
                                       QColor(colors[ch]))
            else:
                k = 1 - b.splat / 0.6
                c = QColor("#7CFC00" if b.by == "du" else "#ffd166")
                c.setAlpha(int(255 * (1 - k)))
                for i in range(6):
                    a = i * 1.047
                    d = (2 + k * 8) * s
                    p.fillRect(QRectF(cx + math.cos(a) * d, by - 3 * s + math.sin(a) * d * 0.7, s, s), c)
        # Anzeige oben rechts: Zeit und Punkte
        name = self.ctl.prof["name"]
        text = f"🐞 {int(hunt.left + 0.99)} s   Du {hunt.score['du']} : {hunt.score['pet']} {name}"
        f = QFont("Segoe UI")
        f.setPixelSize(max(14, 5 * s))
        f.setBold(True)
        fm = QFontMetrics(f)
        w, h = fm.horizontalAdvance(text) + 24, fm.height() + 12
        x = self.width() - w - 16
        p.setBrush(QColor(20, 18, 31, 225))
        p.drawRoundedRect(QRectF(x, 8, w, h), 8, 8)
        p.setFont(f)
        p.setPen(QColor("#ece9f7"))
        p.drawText(QRectF(x, 8, w, h), Qt.AlignmentFlag.AlignCenter, text)
        p.end()


# ===================================================================== Träume
class DreamCloud(_Overlay):
    """Gedankenwolke über dem schlafenden Pet."""

    UNITS = (17, 15)               # Breite/Höhe in Pet-Pixeln

    def __init__(self, dreamer):
        super().__init__()
        self.dreamer = dreamer

    def follow(self, pet):
        s = max(2, pet.px)
        w, h = self.UNITS[0] * s, self.UNITS[1] * s
        bob = math.sin((self.dreamer.current or ("", 0))[1] * 2.2) * s * 0.6
        x = int(pet.x + pet.W * 0.15)
        y = int(pet.y - pet.H - h + 2 * s + bob)
        if self.geometry() != QRect(x, y, w, h):
            self.setGeometry(x, y, w, h)
        self.update()

    def paintEvent(self, e):
        d = self.dreamer
        if d.current is None:
            return
        from .dreams import CLOUD, ICONS, OUTLINE
        s = max(2, self.width() // self.UNITS[0])
        a = d.alpha()
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        out, fill = QColor(OUTLINE), QColor(CLOUD)
        out.setAlpha(a)
        fill.setAlpha(a)
        # Wolke aus Kreisen (erst Rand, dann Füllung), unten links zwei kleine Bläschen zum Kopf
        blobs = [(4, 3, 3.2), (8.5, 2.6, 3.6), (13, 3.4, 3.0), (5, 7.2, 3.3), (10, 7.6, 3.5), (13.6, 6.6, 2.6)]
        bubbles = [(2.2, 12.2, 1.2), (0.9, 14.0, 0.7)]
        for color, grow in ((out, 0.6), (fill, 0.0)):
            p.setBrush(color)
            for cx, cy, r in blobs + bubbles:
                rr = (r + grow) * s
                p.drawEllipse(QRectF(cx * s - rr, cy * s - rr, 2 * rr, 2 * rr))
        rows, colors = ICONS[d.current[0]]
        ox, oy = 5.0 * s, 1.8 * s
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch in colors:
                    c = QColor(colors[ch])
                    c.setAlpha(a)
                    p.fillRect(QRectF(ox + x * s, oy + y * s, s, s), c)
        p.end()


# ===================================================================== Jahreszeiten
class SeasonOverlay(_Overlay):
    """Zeichnet Schnee/Laub/Blüten über dem Terminal (Klicks gehen durch)."""

    def __init__(self, weather):
        super().__init__()
        self.weather = weather

    def sync(self, rect):
        l, t, r, b = rect
        if self.geometry() != QRect(l, t, r - l, b - t):
            self.setGeometry(l, t, r - l, b - t)
        self.update()

    def paintEvent(self, e):
        w = self.weather
        ox, oy = self.geometry().x(), self.geometry().y()
        p = QPainter(self)
        leaf = w.kind in ("herbst", "fruehling")
        for part in list(w.flying) + list(w.resting):
            s = part["size"]
            x, y = int(part["x"] - ox), int(part["y"] - oy - s)
            c = QColor(part["color"])
            if leaf:
                p.fillRect(x, y + 1, s, max(1, s - 2), c)     # Blatt: etwas breiter als hoch
                p.fillRect(x + 1, y, max(1, s - 2), 1, c)
            else:
                p.fillRect(x, y, s, s, c)
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
        scan = QColor("#4dff88")
        scan.setAlpha(110)
        for runs in ctl.debug_scan.values():
            for y, a, b in runs:
                p.fillRect(QRect(int(a - ox), int(y - oy), max(1, int(b - a)), 2), scan)
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
                     f"Ziel: {b.goal[0] if b.goal else '–'}  ·  Laune {pet.mood:.0f}  ·  Energie {pet.energy:.0f}"]
            x, y = int(pet.x - ox + pet.W / 2 + 8), int(pet.y - oy - pet.H)
            p.fillRect(x - 4, y - 14, 300, 18 * len(lines) + 6, QColor(0, 0, 0, 150))
            p.setPen(QColor("#ffffff"))
            for i, t in enumerate(lines):
                p.drawText(x, y + i * 18, t)
        p.end()
