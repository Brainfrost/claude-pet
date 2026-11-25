"""Qt-Seite: Pet-Fenster, Maus, Debug-Overlay, Tray und die 60-fps-Schleife."""
import logging
import time

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import (QTransform, QAction, QColor, QFont, QFontMetrics, QGuiApplication, QIcon, QPainter,
                         QPainterPath, QPen, QPixmap)
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from . import creatures, growth, profile, quiet, settings, sprites, vision, winapi
from .brain import Brain
from .pet import AIR, GROUND, TRANSITION, Pet
from .reactions import Reactions
from .speech import Speech
from .stats import StatsWatcher
from .terminal import TerminalWatcher
from .world import World

log = logging.getLogger(__name__)



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
        self._grab_off = (0, 0)
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
        pose = pet.pose()
        img = ctl.renderer.render(pet.creature, variant=ctl.prof["personality"], t=pet.anim_t,
                                  px=s, stage=pet.stage, accessories=growth.worn(ctl.prof),
                                  **pose)
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
        top = (creatures.MARGIN_TOP - 1) * s
        cx = img.width() / 2
        for fx in pet.effects:
            a = fx["age"]
            if a < 0:
                continue
            k = a / fx["life"]
            alpha = int(255 * (1 - k) ** 0.7)
            rise = k * 6 * s
            if fx["kind"] == "heart":
                sprites.draw_heart(p, cx - 2.5 * s + fx["dx"] * 0.5, top - rise, max(1, s - 1), alpha)
            elif fx["kind"] == "z":
                sprites.draw_text(p, cx + 4 * s + k * 2 * s, top + 2 * s - rise, "z", 5 * s, "#cfe8ff", alpha)
            elif fx["kind"] == "♪":
                sprites.draw_text(p, cx + fx["dx"] * 0.5, top + 2 * s - rise, "♪", 6 * s, "#b8f2ff", alpha)
            elif fx["kind"] in ("!", "*", "…", "?"):
                sprites.draw_text(p, cx - s, top + 2 * s - rise * 0.3, fx["kind"], 7 * s, "#ffd166", alpha)
        p.end()

    # --------------------------------------------------------------- Maus
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            g = e.globalPosition()
            self._press = (g.x(), g.y(), time.perf_counter())
            self._samples = [(time.perf_counter(), g.x(), g.y())]
            pet = self.ctl.pet
            self._grab_off = (pet.x - g.x(), pet.y - g.y())

    def mouseMoveEvent(self, e):
        g = e.globalPosition()
        pet = self.ctl.pet
        if self._press:
            if pet.state != "held":
                if abs(g.x() - self._press[0]) + abs(g.y() - self._press[1]) > 5:
                    pet.grab()
            if pet.state == "held":
                # am Nacken halten: Mauspunkt sitzt knapp unterm Kopf
                pet.x = g.x()
                pet.y = g.y() + pet.H * 0.75
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
                        pet.stroke()
                        self.ctl.speech.canned("stroke")
                        self.ctl.interact("stroke")
                self._stroke_dir = d
        self._last_mx = g.x()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self._press:
            return
        pet = self.ctl.pet
        if pet.state == "held":
            vx = vy = 0.0
            if len(self._samples) >= 2:
                (t0, x0, y0), (t1, x1, y1) = self._samples[0], self._samples[-1]
                if t1 - t0 > 0.005:
                    vx, vy = (x1 - x0) / (t1 - t0), (y1 - y0) / (t1 - t0)
            g = e.globalPosition()
            ti = self.ctl.world.tab_at(g.x(), g.y())
            if ti is None or not self.ctl.brain.dropped_on_tab(self.ctl.world, ti):
                pet.drop(vx, vy)
                if (vx * vx + vy * vy) ** 0.5 > 1500:
                    self.ctl.speech.canned("thrown")
                    self.ctl.interact("thrown")
        else:
            self.ctl.interact("poke_sleep" if pet.state == "sleep" else "poke")
            pet.poke()
            self.ctl.speech.canned("poke")
        self._press = None

    def leaveEvent(self, e):
        self._last_mx = None
        self._stroke_dir = 0


class TabFx(QWidget):
    """Kleiner Effekt am Tab-Reiter: Wackeln beim Hineinklettern, Staubwölkchen beim Verschwinden."""
    LIFE = 0.5

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.fx = []            # (art, start, x, y) in Fensterkoordinaten
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def showEvent(self, e):
        super().showEvent(e)
        winapi.add_exstyle(int(self.winId()), winapi.WS_EX_TRANSPARENT | winapi.WS_EX_LAYERED
                           | winapi.WS_EX_NOACTIVATE | winapi.WS_EX_TOOLWINDOW)

    def play(self, kind, x, y, tab_rect):
        if tab_rect is None:
            l, t, r, b = x - 80, y - 40, x + 80, y
        else:
            l, t, r, b = tab_rect
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
        import math
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
                for i, ang in enumerate((-2.4, -1.9, -1.2, -0.6, 0.0, 0.6)):
                    r = 3 + k * 9
                    d = 6 + k * 18
                    cx = x + math.cos(ang + 1.57) * d * (1 if i % 2 else -1)
                    cy = y + 4 + abs(math.sin(ang)) * d * 0.5
                    p.setBrush(QColor(220, 220, 230, int(a * 0.8)))
                    p.drawEllipse(int(cx - r), int(cy - r), int(2 * r), int(2 * r))
        p.end()


class Bubble(QWidget):
    """Sprechblase über dem Pet. Klicks gehen durch."""
    MAX_W = 260
    PAD = 9
    TAIL = 9

    def __init__(self, ctl):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.ctl = ctl
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.font_ = QFont("Segoe UI")
        self.font_.setPixelSize(14)
        self.text = ""
        self.until = 0.0
        self.tail_x = 0

    def showEvent(self, e):
        super().showEvent(e)
        winapi.add_exstyle(int(self.winId()), winapi.WS_EX_TRANSPARENT | winapi.WS_EX_LAYERED
                           | winapi.WS_EX_NOACTIVATE | winapi.WS_EX_TOOLWINDOW)

    def say(self, text):
        self.text = text
        self.until = time.perf_counter() + 3.5 + 0.06 * len(text)
        fm = QFontMetrics(self.font_)
        r = fm.boundingRect(QRect(0, 0, self.MAX_W, 1000), Qt.TextFlag.TextWordWrap, text)
        self.text_rect = QRect(self.PAD, self.PAD, r.width() + 2, r.height())
        self.resize(r.width() + 2 * self.PAD + 2, r.height() + 2 * self.PAD + self.TAIL)

    def follow(self, pet, pet_visible):
        if not self.text or time.perf_counter() > self.until or not pet_visible:
            if self.isVisible():
                self.hide()
            if time.perf_counter() > self.until:
                self.text = ""
            return
        w, h = self.width(), self.height()
        head = pet.y - pet.H - 2
        x = int(pet.x - w / 2)
        y = int(head - h)
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
        up = getattr(self, "tail_up", False)
        top = self.TAIL if up else 0
        body = QRect(1, top + 1, w - 2, h - self.TAIL - 2)
        path = QPainterPath()
        path.addRoundedRect(body.x(), body.y(), body.width(), body.height(), 8, 8)
        tail = QPainterPath()
        tx = self.tail_x
        if up:
            tail.moveTo(tx - 7, top + 2)
            tail.lineTo(tx, 1)
            tail.lineTo(tx + 7, top + 2)
        else:
            tail.moveTo(tx - 7, body.bottom() - 1)
            tail.lineTo(tx, h - 1)
            tail.lineTo(tx + 7, body.bottom() - 1)
        path = path.united(tail)
        p.setPen(QPen(QColor("#e8e4f0"), 2))
        p.setBrush(QColor(27, 21, 48, 238))
        p.drawPath(path)
        p.setPen(QColor("#ffffff"))
        p.setFont(self.font_)
        p.drawText(self.text_rect.translated(0, top), Qt.TextFlag.TextWordWrap, self.text)
        p.end()


class DebugOverlay(QWidget):
    """Zeigt die erkannten Plattformen als Linien über dem Terminal. Klicks gehen durch."""

    def __init__(self, ctl):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput)
        self.ctl = ctl
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def showEvent(self, e):
        super().showEvent(e)
        winapi.add_exstyle(int(self.winId()), winapi.WS_EX_TRANSPARENT | winapi.WS_EX_LAYERED
                           | winapi.WS_EX_NOACTIVATE)

    def sync(self):
        w = self.ctl.world
        if not w.ok:
            self.hide()
            return
        l, t, r, b = w.snap.win_rect
        self.setGeometry(l, t, r - l, b - t)
        self.update()

    def paintEvent(self, e):
        w = self.ctl.world
        if not w.ok:
            return
        l, t, _, _ = w.snap.win_rect
        p = QPainter(self)
        for q in w.platforms:
            c = QColor("#ff4d6d" if q.row == -1 else "#4dd0ff")
            c.setAlpha(170)
            p.fillRect(QRect(int(q.x0 - l), int(q.y - t), max(1, int(q.x1 - q.x0)), 2), c)
        for tab in w.snap.tabs:
            c = QColor("#7CFC00" if tab.selected else "#ffd166")
            p.setPen(c)
            tl, tt, tr, tb = tab.rect
            p.drawRect(int(tl - l), int(tt - t), int(tr - tl), int(tb - tt))
            p.drawText(int(tl - l) + 4, int(tb - t) + 14, tab.state)
        p.end()


class Controller:
    def __init__(self, app):
        self.app = app
        self.world = World()
        self.prof = growth.ensure_defaults(profile.load())
        growth.absence(self.prof)
        self.renderer = creatures.Renderer()
        self.pet = Pet(creatures.get(self.prof["creature"]), self.prof.get("stage", "baby"),
                       self.prof["personality"])
        self.brain = Brain(self.pet, self.prof["personality"])
        self._sync_progress()
        log.info("Pet: %s (%s), Charakter %s, Stufe %s, XP %d, Bindung %.0f", self.prof["name"],
                 self.prof["creature"], self.prof["personality"], self.pet.stage, self.prof["xp"],
                 self.prof["bond"])
        self.win = PetWindow(self)
        self.bubble = Bubble(self)
        self.speech = Speech(self.prof)
        self.speech.said.connect(self._say)
        self.speech.acted.connect(self.on_action)
        self.speech.persona_ready.connect(self.on_persona)
        if not self.prof.get("persona"):
            self.speech.generate_persona(self.prof)
        self.reactions = Reactions(self)
        self._prev_state = None
        self.settings = settings.load()
        self.quiet_reason = None
        self._quiet_check = 0.0
        self.tabfx = TabFx()
        self._apply_settings()
        try:
            if self.settings.get("autostart") and not settings.autostart_enabled():
                settings.set_autostart(True)
                log.info("Autostart eingerichtet: %s", settings.autostart_command())
        except OSError:
            log.exception("Autostart konnte nicht eingerichtet werden")
        self.debug = DebugOverlay(self)
        self.debug_on = False
        self._last_win_rect = None
        self._visible_ok = True
        self._vis_check = 0.0
        self._last = time.perf_counter()

        self.watcher = TerminalWatcher()
        self.watcher.snapshot.connect(self.on_snapshot)
        self.watcher.start()
        self.stats = StatsWatcher(self.prof.get("born"))
        self.stats.delta.connect(self.on_stats)
        self.stats.start()
        self._win_check = 0.0
        self._vision_check = 0.0
        self._interval = 16
        self._last_save = time.perf_counter()

        self.timer = QTimer()
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        self._make_tray()

    # --------------------------------------------------------------- Tray
    def _make_tray(self):
        self.tray = QSystemTrayIcon()
        self._update_tray_identity()
        m = QMenu()
        self.a_info = QAction("", m)
        self.a_info.setEnabled(False)
        m.addAction(self.a_info)
        self._update_tray_identity()
        m.addSeparator()
        a_new = QAction("Neues Pet auswürfeln", m)
        a_new.triggered.connect(self.reroll)
        m.addAction(a_new)
        a_talk = QAction("Was denkst du gerade?", m)
        a_talk.triggered.connect(lambda: self.speech.ask_now(self.world, self.pet.pane or 0))
        m.addAction(a_talk)
        a_trip = QAction("Ausflug machen!", m)
        a_trip.triggered.connect(lambda: setattr(self.pet, "want_adventure", True))
        m.addAction(a_trip)
        a_come = QAction("Pet zu mir holen", m)
        a_come.triggered.connect(self.summon)
        a_dbg = QAction("Debug: Plattformen anzeigen", m, checkable=True)
        a_dbg.toggled.connect(self.toggle_debug)
        a_quit = QAction("Beenden", m)
        a_quit.triggered.connect(self.quit)
        for a in (a_come, a_dbg):
            m.addAction(a)
        m.addSeparator()
        self.a_dnd = QAction("Bitte nicht stören", m, checkable=True)
        self.a_dnd.toggled.connect(lambda on: self._set("dnd", on))
        m.addAction(self.a_dnd)
        self.m_set = m.addMenu("Einstellungen")
        self.m_dev = m.addMenu("Entwicklung")
        self.m_acc = m.addMenu("Accessoires")
        m.aboutToShow.connect(self._fill_dev_menus)
        m.aboutToShow.connect(self._fill_settings_menu)
        m.addSeparator()
        m.addAction(a_quit)
        self.tray.setContextMenu(m)
        self._menu = m
        self.tray.show()

    def _update_tray_identity(self):
        c = self.pet.creature
        img = self.renderer.render(c, variant=self.prof["personality"], state="idle", t=0, walk_i=0,
                                   blinking=False, facing=1, px=2, stage="erwachsen")
        icon_img = img.copy(creatures.MARGIN_X * 2, creatures.MARGIN_TOP * 2, c["w"] * 2, c["h"] * 2)
        self.tray.setIcon(QIcon(QPixmap.fromImage(icon_img)))
        label = creatures.data()["variants"].get(self.prof["personality"], {}).get("label", "")
        text = f"{self.prof['name']} – {label} ({self.prof.get('stage', 'baby')})"
        persona = self.prof.get("persona")
        self.tray.setToolTip(text + ("\n\n" + persona if persona else ""))
        if getattr(self, "quiet_reason", None):
            text += f"  ·  Ruhemodus: {self.quiet_reason}"
        if hasattr(self, "a_info"):
            self.a_info.setText(text)

    def _fill_dev_menus(self):
        pr = self.prof
        st = pr.get("stats", {})
        nxt, need = growth.next_stage(pr["xp"])
        lines = [
            f"Stufe: {pr.get('stage')}  ·  XP {pr['xp']}" + (f" / {need} bis {nxt}" if nxt else ""),
            f"Bindung {pr['bond']:.0f}/100  ·  Stimmung {pr['mood']:.0f}/100",
            f"Seit Geburt: {st.get('tools', 0)} Tool-Aufrufe, {st.get('prompts', 0)} Eingaben, "
            f"{st.get('sessions', 0)} Sessions",
        ]
        tricks = [growth.TRICKS[t].split(" – ")[0] for t in pr.get("tricks", [])]
        lines.append("Tricks: " + (", ".join(tricks) if tricks else "noch keine"))
        self.m_dev.clear()
        for t in lines:
            a = self.m_dev.addAction(t)
            a.setEnabled(False)
        self.m_acc.clear()
        cats = st.get("cats", {})
        for acc, (cat, need_n, desc) in growth.ACCESSORIES.items():
            have = acc in pr.get("accessories", [])
            label = desc.split(" – ")[0]
            if have:
                a = self.m_acc.addAction(label)
                a.setCheckable(True)
                a.setChecked(acc not in pr.get("accessories_off", []))
                a.toggled.connect(lambda on, acc=acc: self._toggle_acc(acc, on))
            else:
                a = self.m_acc.addAction(f"{label} – gesperrt ({cats.get(cat, 0)}/{need_n})")
                a.setEnabled(False)

    def _fill_settings_menu(self):
        s = self.settings
        self.m_set.clear()
        self.a_dnd.blockSignals(True)
        self.a_dnd.setChecked(bool(s.get("dnd")))
        self.a_dnd.blockSignals(False)
        for title, key, opts in (("Größe", "size", (("klein", "Klein"), ("normal", "Normal"), ("gross", "Groß"))),
                                 ("Redefreude", "talk", (("aus", "Aus (nur auf Wunsch)"), ("wenig", "Wenig"),
                                                         ("normal", "Normal"), ("viel", "Viel")))):
            sub = self.m_set.addMenu(title)
            for val, label in opts:
                a = sub.addAction(label)
                a.setCheckable(True)
                a.setChecked(s.get(key) == val)
                a.triggered.connect(lambda _=False, key=key, val=val: self._set(key, val))
        self.m_set.addSeparator()
        for key, label in (("bubbles", "Sprechblasen anzeigen"), ("quiet_calls", "Ruhemodus bei Calls (Mikrofon aktiv)"),
                           ("quiet_fullscreen", "Ruhemodus bei Vollbild/Präsentation"),
                           ("autostart", "Mit Windows starten")):
            a = self.m_set.addAction(label)
            a.setCheckable(True)
            a.setChecked(bool(s.get(key)))
            a.toggled.connect(lambda on, key=key: self._set(key, on))

    def _set(self, key, val):
        self.settings[key] = val
        settings.save(self.settings)
        if key == "autostart":
            try:
                settings.set_autostart(bool(val))
            except OSError:
                log.exception("Autostart ändern fehlgeschlagen")
        self._apply_settings()
        if key in ("dnd", "quiet_calls", "quiet_fullscreen"):
            self._quiet_check = 0.0
        log.info("Einstellung %s = %s", key, val)

    def _apply_settings(self):
        s = self.settings
        pet = self.pet
        f = settings.SIZE_FACTOR.get(s.get("size"), 1.0)
        if pet.size_factor != f:
            pet.size_factor = f
            pet.set_scale(pet.line_h)
        self.speech.factor = settings.TALK_FACTOR.get(s.get("talk"), 1.0)

    def _say(self, text):
        if self.settings.get("bubbles", True) and not self.quiet_reason:
            self.bubble.say(text)

    def _update_quiet(self):
        try:
            r = quiet.reason(self.settings)
        except OSError:
            r = None
        if r != self.quiet_reason:
            log.info("Ruhemodus: %s", r or "aus")
            self.quiet_reason = r
            self.speech.muted = bool(r)
            self._update_tray_identity()

    def _toggle_acc(self, acc, on):
        off = self.prof.setdefault("accessories_off", [])
        if on and acc in off:
            off.remove(acc)
        elif not on and acc not in off:
            off.append(acc)
        profile.save(self.prof)

    def _sync_progress(self):
        pet, pr = self.pet, self.prof
        pet.mood, pet.bond = pr["mood"], pr["bond"]
        pet.tricks = set(pr.get("tricks", []))
        if pet.stage != pr.get("stage", "baby"):
            pet.stage = pr["stage"]
            pet.set_scale(pet.line_h)

    def interact(self, kind):
        self.on_milestones(growth.interact(self.prof, kind))

    def on_stats(self, d):
        log.info("Arbeit verbucht: %s", d)
        self.on_milestones(growth.apply_stats(self.prof, d))
        profile.save(self.prof)

    MILESTONE_TEXT = {
        ("stage", "jung"): "Ich bin gewachsen! Schau, wie groß ich schon bin!",
        ("stage", "erwachsen"): "Ich bin jetzt ausgewachsen! Danke, dass du dich um mich kümmerst.",
        ("accessory", "helm"): "Ein Bauhelm! So viel Kommandozeile – ich bin jetzt Baustellen-Profi.",
        ("accessory", "brille"): "Ich hab eine Brille! Vom vielen Recherchieren, schätze ich.",
        ("accessory", "lupe"): "Eine Lupe! Jetzt finde ich jeden Bug.",
        ("trick", "doppelsprung"): "Neuer Trick: Doppelsprung! Ich komme jetzt viel höher.",
        ("trick", "purzelbaum"): "Neuer Trick: Purzelbaum! Weil du so lieb zu mir bist.",
        ("trick", "weitsprung"): "Neuer Trick: Weitsprung! Jetzt kann ich andere Fenster besuchen.",
    }

    def on_milestones(self, ms):
        if not ms:
            return
        self._sync_progress()
        for kind, key in ms:
            log.info("Meilenstein: %s %s", kind, key)
            text = self.MILESTONE_TEXT.get((kind, key))
            if text:
                self.bubble.say(text)
        self.pet.react("success")
        profile.save(self.prof)
        self._update_tray_identity()

    def reroll(self):
        """Steckbrief löschen und ein neues Pet auswürfeln (zum Ausprobieren)."""
        self.prof = growth.ensure_defaults(profile.reroll())
        self.stats.reset(self.prof.get("born"))
        self.pet = Pet(creatures.get(self.prof["creature"]), self.prof.get("stage", "baby"),
                       self.prof["personality"])
        self.brain = Brain(self.pet, self.prof["personality"])
        self._sync_progress()
        self._apply_settings()
        self.pet.on_world(self.world)
        self.brain.on_world(self.world)
        self.speech.set_profile(self.prof)
        self.speech.generate_persona(self.prof)
        self._update_tray_identity()
        log.info("neu ausgewürfelt: %s (%s)", self.prof["name"], self.prof["personality"])

    def on_action(self, action, target):
        """Von Haiku gewählte Aktion umsetzen."""
        if action == "verstecken":
            self.brain.hide_somewhere(self.world)
        elif action == "hinlaufen":
            if not self.pet.go_to_word(target, self.world):
                self.pet.perform("umschauen")
        else:
            self.pet.perform(action)

    def on_persona(self, text):
        if not text:
            return
        self.prof["persona"] = text
        profile.save(self.prof)
        log.info("Persönlichkeit für %s: %s", self.prof["name"], " ".join(text.split()))
        self._update_tray_identity()

    def summon(self):
        x, y = winapi.cursor_pos()
        self.pet.placed = True
        self.pet.x, self.pet.y = x, y + self.pet.H * 0.75
        self.pet.drop(0, 0)

    def toggle_debug(self, on):
        self.debug_on = on
        if on:
            self.debug.sync()
            self.debug.show()
        else:
            self.debug.hide()

    def quit(self):
        self.prof["last_seen"] = time.time()
        profile.save(self.prof)
        self.stats.stop()
        self.watcher.stop()
        self.watcher.wait(1500)
        self.tray.hide()
        self.app.quit()

    # --------------------------------------------------------------- Daten
    def on_snapshot(self, snap):
        if snap.ok and self._last_win_rect and snap.win_rect != self._last_win_rect:
            (l0, t0, r0, b0), (l1, t1, r1, b1) = self._last_win_rect, snap.win_rect
            if (r0 - l0, b0 - t0) == (r1 - l1, b1 - t1):
                self.pet.translate(l1 - l0, t1 - t0)
        if snap.ok:
            self._last_win_rect = snap.win_rect
        self.world.update(snap)
        if self.quiet_reason:
            return
        self.brain.on_world(self.world)
        self.pet.on_world(self.world)
        self.reactions.on_world(self.world)
        if self.debug_on:
            self.debug.sync()

    def screen_floor(self, x):
        scr = QGuiApplication.screenAt(QPoint(int(x), int(self.pet.y - 1)))
        if scr is None:
            scr = min(QGuiApplication.screens(),
                      key=lambda s: abs(s.geometry().center().x() - x))
        g = scr.availableGeometry()
        return g.y() + g.height()

    def screen_top_at(self, x, y):
        scr = QGuiApplication.screenAt(QPoint(int(x), int(y) + 5))
        if scr is None:
            scr = min(QGuiApplication.screens(),
                      key=lambda s: abs(s.geometry().center().x() - x))
        return scr.geometry().y()

    def vbounds(self):
        g = QGuiApplication.primaryScreen().virtualGeometry()
        return g.x(), g.y(), g.x() + g.width(), g.y() + g.height()

    # --------------------------------------------------------------- Schleife
    def tick(self):
        now = time.perf_counter()
        dt = min(0.05, now - self._last)
        self._last = now
        pet = self.pet
        cx, cy = winapi.cursor_pos()
        if now - self._quiet_check > 2.0:
            self._quiet_check = now
            self._update_quiet()
        if self.quiet_reason:
            if self.win.isVisible():
                self.win.hide()
            if self.bubble.isVisible():
                self.bubble.hide()
            self._adapt_rate(pet)
            return
        if pet.state in ("idle", "sit", "happy") and abs(cx - pet.x) > pet.W * 1.5:
            pet.facing = 1 if cx > pet.x else -1   # schaut zu dir
        outside = pet.pane is None and pet.placed and pet.state != "hidden"
        if now - self._win_check > (0.4 if outside else 1.0):
            self._win_check = now
            old = dict(self.world.win_rects)
            self.world.set_windows(winapi.window_rects(), pet.H + 6, self.screen_top_at)
            pet.on_windows(self.world, old)
        if outside and now - self._vision_check > 0.33:
            self._vision_check = now
            self._update_vision()
        if pet.want_adventure:
            self._adventure()
        self.watcher.poll_hz = 8 if (pet.pane is not None and pet.state != "hidden") else 4
        growth.drift(self.prof, dt)
        pet.mood, pet.bond = self.prof["mood"], self.prof["bond"]
        if now - self._last_save > 30:
            self._last_save = now
            self.prof["last_seen"] = time.time()
            profile.save(self.prof)
        self.brain.tick(dt, self.world, (cx, cy))
        pet.step(dt, self.world, self.screen_floor, self.vbounds(), (cx, cy))
        if pet.fx_requests:
            for kind, fx, fy in pet.fx_requests:
                ti = self.world.tab_at(fx, fy - 4)
                rect = self.world.snap.tabs[ti].rect if ti is not None else None
                self.tabfx.play(kind, fx, fy, rect)
            pet.fx_requests.clear()
        self._update_visibility(now)
        self.place()
        if pet.state != self._prev_state:
            if pet.state == "cling":
                self.speech.canned("cling")
                self.interact("cling")
            self._prev_state = pet.state
        visible = self.win.isVisible() and pet.state != "hidden"
        self.speech.tick(self.world, pet.pane or 0, visible and pet.grounded)
        self.bubble.follow(pet, visible)
        self._adapt_rate(pet)
        if now - getattr(self, "_last_log", 0) > 2:
            self._last_log = now
            sp = pet.support
            b = self.brain
            log.info("pet state=%s pos=(%.0f,%.0f) visible=%s world=%s support=%s goal=%s home=%s",
                     pet.state, pet.x, pet.y, self.win.isVisible(), self.world.ok,
                     sp and (sp.pane, sp.row, sp.text[:20]), b.goal and b.goal[0],
                     b.home and b.home[0][:25])

    def _adapt_rate(self, pet):
        """Bildrate nach Zustand: flüssig in Bewegung, sparsam im Ruhezustand."""
        st = pet.state
        if self.quiet_reason:
            iv = 250
        elif st in AIR or st in TRANSITION or st in ("held", "cling", "walk") or pet.effects \
                or pet.squash > 0 or self.bubble.isVisible():
            iv = 16
        elif st in ("idle", "happy", "crouch"):
            iv = 33
        elif st == "sit":
            iv = 66
        elif st == "hidden":
            iv = 200
        else:
            iv = 100
        if iv != self._interval:
            self._interval = iv
            self.timer.setInterval(iv)

    def _exclusions(self):
        out = []
        for w in (self.win, self.bubble):
            if w.isVisible():
                g = w.geometry()
                out.append((g.x(), g.y(), g.x() + g.width(), g.y() + g.height()))
        return out

    def _update_vision(self):
        pet = self.pet
        runs = vision.platforms_around(pet.x, pet.y, 1100, 900, self._exclusions())
        self.world.set_vision(runs)
        pet.on_vision(self.world)

    def _adventure(self):
        """Ziel für einen Ausflug suchen: ein Ausschnitt auf einem anderen Bildschirm bzw. neben
        dem Terminal, darin per Bildanalyse eine Kante."""
        import random
        pet = self.pet
        pet.want_adventure = False
        term = self.world.snap.win_rect if self.world.ok else None
        cands = []
        for scr in QGuiApplication.screens():
            g = scr.availableGeometry()
            cx = g.x() + random.uniform(0.2, 0.8) * g.width()
            cy = g.y() + random.uniform(0.3, 0.8) * g.height()
            if term and term[0] <= cx < term[2] and term[1] <= cy < term[3]:
                continue
            cands.append((cx, cy))
        random.shuffle(cands)
        for cx, cy in cands[:2]:
            runs = vision.platforms_around(cx, cy, 900, 700, self._exclusions())
            runs = [r for r in runs if r[2] - r[1] >= pet.W * 1.2]
            if term:
                runs = [r for r in runs if not (term[0] <= (r[1] + r[2]) / 2 < term[2] and term[1] <= r[0] < term[3])]
            if runs:
                self.world.set_vision(runs)         # Ziel muss beim Landen bekannt sein
                y, a, b = random.choice(runs)
                if pet.adventure_to(a, b, y):
                    log.info("Ausflug nach (%d, %d)", (a + b) // 2, y)
                return

    def place(self):
        x, y, w, h = self.win.geometry_for(self.pet)
        if self.win.geometry() != QRect(x, y, w, h):
            self.win.setGeometry(x, y, w, h)
        self.win.update()

    def _update_visibility(self, now):
        pet = self.pet
        show = pet.placed and pet.state != "hidden"
        if pet.state == "cling":
            pass
        elif not self.world.ok:
            pass                                    # Terminal weg: Pet erkundet die anderen Fenster
        elif pet.pane is not None and pet.state not in ("held", "hidden") and pet.state not in AIR:
            if now - self._vis_check > 0.25:
                self._vis_check = now
                top = winapi.top_window_at(int(pet.x), int(pet.y - pet.H / 2))
                self._visible_ok = top == self.world.snap.hwnd
            show = show and self._visible_ok
        if show and not self.win.isVisible():
            self.win.show()
        elif not show and self.win.isVisible():
            self.win.hide()


def run():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    ctl = Controller(app)
    app._ctl = ctl
    return app.exec()
