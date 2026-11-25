"""Steuerung: verbindet Terminal, Welt, Pet, Gehirn, Sprache und Fenster und treibt die Spielschleife."""
import logging
import random
import time

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

from . import creatures, growth, profile, quiet, settings, vision, winapi
from .brain import Brain
from .pet import AIR, TRANSITION, Pet
from .reactions import Reactions
from .speech import Speech
from .stats import StatsWatcher
from .terminal import TerminalWatcher
from .tray import Tray
from .windows import Bubble, DebugOverlay, PetWindow, TabFx
from .world import World

log = logging.getLogger(__name__)

MILESTONE_TEXT = {
    ("stage", "jung"): "Ich bin gewachsen! Schau, wie groß ich schon bin!",
    ("stage", "erwachsen"): "Ich bin jetzt ausgewachsen! Danke, dass du dich um mich kümmerst.",
    ("accessory", "helm"): "Ein Bauhelm! So viel Kommandozeile – ich bin jetzt Baustellen-Profi.",
    ("accessory", "brille"): "Ich hab eine Brille! Vom vielen Recherchieren, schätze ich.",
    ("accessory", "lupe"): "Eine Lupe! Jetzt finde ich jeden Bug.",
    ("trick", "doppelsprung"): "Neuer Trick: Doppelsprung! Ich komme jetzt viel höher.",
    ("trick", "purzelbaum"): "Neuer Trick: Purzelbaum! Weil du so lieb zu mir bist.",
    ("trick", "weitsprung"): "Neuer Trick: Weitsprung! Jetzt gehe ich öfter auf Ausflüge.",
}


class Controller:
    def __init__(self, app):
        self.app = app
        self.world = World()
        self.settings = settings.load()
        self.quiet_reason = None
        self.prof = growth.ensure_defaults(profile.load())
        growth.absence(self.prof)
        self.renderer = creatures.Renderer()
        self._new_pet()

        self.win = PetWindow(self)
        self.bubble = Bubble()
        self.tabfx = TabFx()
        self.debug = DebugOverlay(self)
        self.debug_on = False
        self.debug_scan = {}            # Bildschirm-Index -> Kanten der Ganz-Bildschirm-Analyse
        self._scan_i = 0
        self._scan_t = 0.0

        self.speech = Speech(self.prof)
        self.speech.said.connect(self._say)
        self.speech.acted.connect(self.on_action)
        self.speech.persona_ready.connect(self.on_persona)
        if not self.prof.get("persona"):
            self.speech.generate_persona(self.prof)
        self.reactions = Reactions(self)
        self._apply_settings()
        self._ensure_autostart()

        self._prev_state = None
        self._last_win_rect = None
        self._visible_ok = True
        now = time.perf_counter()
        self._last = self._last_save = now
        self._vis_check = self._win_check = self._vision_check = self._quiet_check = 0.0
        self._debug_t = self._log_t = 0.0
        self._interval = 16

        self.watcher = TerminalWatcher()
        self.watcher.snapshot.connect(self.on_snapshot)
        self.watcher.start()
        self.stats = StatsWatcher(self.prof.get("born"))
        self.stats.delta.connect(self.on_stats)
        self.stats.start()

        self.timer = QTimer()
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(self._interval)
        self.tray = Tray(self)

    # ================================================================ Pet & Profil
    def _new_pet(self):
        self.pet = Pet(creatures.get(self.prof["creature"]), self.prof.get("stage", "baby"),
                       self.prof["personality"])
        self.brain = Brain(self.pet, self.prof["personality"])
        self._sync_progress()
        log.info("Pet: %s (%s), Charakter %s, Stufe %s, XP %d, Bindung %.0f", self.prof["name"],
                 self.prof["creature"], self.prof["personality"], self.pet.stage, self.prof["xp"],
                 self.prof["bond"])

    def _sync_progress(self):
        pet, pr = self.pet, self.prof
        pet.mood, pet.bond = pr["mood"], pr["bond"]
        pet.tricks = set(pr.get("tricks", []))
        if pet.stage != pr.get("stage", "baby"):
            pet.stage = pr["stage"]
            pet.set_scale(pet.line_h)

    def reroll(self):
        """Steckbrief löschen und ein neues Pet auswürfeln."""
        self.prof = growth.ensure_defaults(profile.reroll())
        self.stats.reset(self.prof.get("born"))
        self._new_pet()
        self._apply_settings()
        self.brain.on_world(self.world)
        self.pet.on_world(self.world)
        self.speech.set_profile(self.prof)
        self.speech.generate_persona(self.prof)
        self.tray.update_identity()

    def on_persona(self, text):
        if not text:
            return
        self.prof["persona"] = text
        profile.save(self.prof)
        log.info("Persönlichkeit für %s: %s", self.prof["name"], " ".join(text.split()))
        self.tray.update_identity()

    def on_stats(self, d):
        log.info("Arbeit verbucht: %s", d)
        self.on_milestones(growth.apply_stats(self.prof, d))
        profile.save(self.prof)

    def interact(self, kind):
        self.on_milestones(growth.interact(self.prof, kind))

    def on_milestones(self, ms):
        if not ms:
            return
        self._sync_progress()
        for kind, key in ms:
            log.info("Meilenstein: %s %s", kind, key)
            text = MILESTONE_TEXT.get((kind, key))
            if text:
                self._say(text)
        self.pet.react("success")
        profile.save(self.prof)
        self.tray.update_identity()

    def toggle_accessory(self, acc, on):
        off = self.prof.setdefault("accessories_off", [])
        if on and acc in off:
            off.remove(acc)
        elif not on and acc not in off:
            off.append(acc)
        profile.save(self.prof)

    # ================================================================ Maus (aus dem Pet-Fenster)
    def on_stroke(self):
        self.pet.stroke()
        self.speech.canned("stroke")
        self.interact("stroke")

    def on_poke(self):
        self.interact("poke_sleep" if self.pet.state == "sleep" else "poke")
        self.pet.poke()
        self.speech.canned("poke")

    def on_release(self, x, y, vx, vy):
        ti = self.world.tab_at(x, y)
        if ti is not None and self.brain.dropped_on_tab(self.world, ti):
            return
        self.pet.drop(vx, vy)
        if (vx * vx + vy * vy) ** 0.5 > 1500:
            self.speech.canned("thrown")
            self.interact("thrown")

    def on_action(self, action, target):
        """Von Haiku gewählte Aktion umsetzen."""
        if action == "verstecken":
            self.brain.hide_somewhere(self.world)
        elif action == "hinlaufen":
            if not self.pet.go_to_word(target, self.world):
                self.pet.perform("umschauen")
        else:
            self.pet.perform(action)

    def summon(self):
        x, y = winapi.cursor_pos()
        self.pet.placed = True
        self.pet.x, self.pet.y = x, y + self.pet.H * 0.75
        self.pet.drop(0, 0)

    # ================================================================ Einstellungen
    def set_setting(self, key, val):
        self.settings[key] = val
        settings.save(self.settings)
        if key == "autostart":
            try:
                settings.set_autostart(bool(val))
            except OSError:
                log.exception("Autostart ändern fehlgeschlagen")
        if key in ("dnd", "quiet_calls", "quiet_fullscreen"):
            self._quiet_check = 0.0
        self._apply_settings()
        log.info("Einstellung %s = %s", key, val)

    def _apply_settings(self):
        f = settings.SIZE_FACTOR.get(self.settings.get("size"), 1.0)
        if self.pet.size_factor != f:
            self.pet.size_factor = f
            self.pet.set_scale(self.pet.line_h)
        self.speech.factor = settings.TALK_FACTOR.get(self.settings.get("talk"), 1.0)

    def _ensure_autostart(self):
        try:
            if self.settings.get("autostart") and not settings.autostart_enabled():
                settings.set_autostart(True)
                log.info("Autostart eingerichtet: %s", settings.autostart_command())
        except OSError:
            log.exception("Autostart konnte nicht eingerichtet werden")

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
            self.tray.update_identity()

    def toggle_debug(self, on):
        self.debug_on = on
        logging.getLogger().setLevel(logging.DEBUG if on else logging.INFO)
        if on:
            self._scan_i = 0
            self.debug.sync()
            self.debug.show()
        else:
            self.debug.hide()
            self.debug_scan.clear()

    def _debug_scan_next(self):
        """Entwickler-Ansicht: reihum einen ganzen Bildschirm analysieren (nur zur Anzeige)."""
        screens = QGuiApplication.screens()
        if not screens:
            return
        i = self._scan_i % len(screens)
        self._scan_i += 1
        g = screens[i].geometry()
        term = self.world.snap.win_rect if self.world.ok else None
        runs = vision.platforms_in_rect(g.x(), g.y(), g.width(), g.height())
        if term:
            runs = [r for r in runs
                    if not (term[0] <= (r[1] + r[2]) / 2 < term[2] and term[1] <= r[0] < term[3])]
        self.debug_scan[i] = runs

    def quit(self):
        self.prof["last_seen"] = time.time()
        profile.save(self.prof)
        self.stats.stop()
        self.watcher.stop()
        self.watcher.wait(1500)
        self.tray.hide()
        self.app.quit()

    # ================================================================ Terminal-Daten
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
        # erst das Gehirn (merkt sich den Platz, bevor der Text eines anderen Tabs gilt), dann das Pet
        self.brain.on_world(self.world)
        self.pet.on_world(self.world)
        self.reactions.on_world(self.world)

    def screen_floor(self, x):
        g = self._screen_near(x, self.pet.y - 1).availableGeometry()
        return g.y() + g.height()

    def screen_top_at(self, x, y):
        return self._screen_near(x, y + 5).geometry().y()

    @staticmethod
    def _screen_near(x, y):
        scr = QGuiApplication.screenAt(QPoint(int(x), int(y)))
        return scr or min(QGuiApplication.screens(), key=lambda s: abs(s.geometry().center().x() - x))

    @staticmethod
    def vbounds():
        g = QGuiApplication.primaryScreen().virtualGeometry()
        return g.x(), g.y(), g.x() + g.width(), g.y() + g.height()

    # ================================================================ Spielschleife
    def tick(self):
        now = time.perf_counter()
        dt = min(0.05, now - self._last)
        self._last = now
        pet = self.pet
        cursor = winapi.cursor_pos()
        if now - self._quiet_check > 2.0:
            self._quiet_check = now
            self._update_quiet()
        if self.quiet_reason:
            self.win.hide()
            self.bubble.hide()
            self._adapt_rate(pet)
            return
        if pet.state in ("idle", "sit", "happy") and abs(cursor[0] - pet.x) > pet.W * 1.5:
            pet.facing = 1 if cursor[0] > pet.x else -1          # schaut zu dir
        self._update_surroundings(now)
        growth.drift(self.prof, dt)
        pet.mood, pet.bond = self.prof["mood"], self.prof["bond"]
        if now - self._last_save > 30:
            self._last_save = now
            self.prof["last_seen"] = time.time()
            profile.save(self.prof)

        self.brain.tick(dt, self.world, cursor)
        pet.step(dt, self.world, self.screen_floor, self.vbounds(), cursor)
        self._play_tab_effects()
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
        if self.debug_on:
            if now - self._scan_t > 0.7:
                self._scan_t = now
                self._debug_scan_next()
            if now - self._debug_t > 0.1:
                self._debug_t = now
                self.debug.sync()
        if now - self._log_t > 2:
            self._log_t = now
            sp = pet.support
            log.debug("pet state=%s pos=(%.0f,%.0f) visible=%s world=%s support=%s goal=%s home=%s",
                      pet.state, pet.x, pet.y, self.win.isVisible(), self.world.ok,
                      sp and (sp.pane, sp.row, sp.text[:20]), self.brain.goal and self.brain.goal[0],
                      self.brain.home and self.brain.home[0][:25])

    def _update_surroundings(self, now):
        """Fensterkanten, Bildanalyse, Ausflüge und Abfragerate des Terminals."""
        pet = self.pet
        outside = pet.pane is None and pet.placed and pet.state != "hidden"
        if now - self._win_check > (0.4 if outside else 1.0):
            self._win_check = now
            old = dict(self.world.win_rects)
            self.world.set_windows(winapi.window_rects(), pet.H + 6, self.screen_top_at)
            pet.on_windows(self.world, old)
        if outside and now - self._vision_check > 0.33:
            self._vision_check = now
            self.world.set_vision(vision.platforms_around(pet.x, pet.y, 1100, 900, self._exclusions()))
            pet.on_vision(self.world)
        if pet.want_adventure:
            self._adventure()
        self.watcher.poll_hz = 8 if (pet.pane is not None and pet.state != "hidden") else 4

    def _play_tab_effects(self):
        pet = self.pet
        for kind, fx, fy in pet.fx_requests:
            ti = self.world.tab_at(fx, fy - 4)
            rect = self.world.snap.tabs[ti].rect if ti is not None else None
            self.tabfx.play(kind, fx, fy, rect)
        pet.fx_requests.clear()

    def _adapt_rate(self, pet):
        """Bildrate nach Zustand: flüssig in Bewegung, sparsam im Ruhezustand."""
        st = pet.state
        if self.quiet_reason:
            iv = 250
        elif (st in AIR or st in TRANSITION or st in ("held", "cling", "walk") or pet.effects
              or pet.squash > 0 or self.bubble.isVisible() or self.debug_on):
            iv = 16
        elif st in ("idle", "happy"):
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
        for w in (self.win, self.bubble, self.debug):
            if w.isVisible() and w is not self.debug:
                g = w.geometry()
                out.append((g.x(), g.y(), g.x() + g.width(), g.y() + g.height()))
        return out

    def _adventure(self):
        """Ziel für einen Ausflug: ein Ausschnitt auf einem anderen Bildschirm bzw. neben dem
        Terminal, darin per Bildanalyse eine Kante."""
        pet = self.pet
        pet.want_adventure = False
        term = self.world.snap.win_rect if self.world.ok else None

        def in_term(x, y):
            return term and term[0] <= x < term[2] and term[1] <= y < term[3]

        spots = []
        for scr in QGuiApplication.screens():
            g = scr.availableGeometry()
            cx = g.x() + random.uniform(0.2, 0.8) * g.width()
            cy = g.y() + random.uniform(0.3, 0.8) * g.height()
            if not in_term(cx, cy):
                spots.append((cx, cy))
        random.shuffle(spots)
        for cx, cy in spots[:2]:
            runs = [r for r in vision.platforms_around(cx, cy, 900, 700, self._exclusions())
                    if r[2] - r[1] >= pet.W * 1.2 and not in_term((r[1] + r[2]) / 2, r[0])]
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
        in_terminal = (self.world.ok and pet.pane is not None and pet.state not in ("held", "cling")
                       and pet.state not in AIR)
        if show and in_terminal:
            # im Terminal: nur zeigen, wenn das Terminal an dieser Stelle nicht verdeckt ist
            if now - self._vis_check > 0.25:
                self._vis_check = now
                top = winapi.top_window_at(int(pet.x), int(pet.y - pet.H / 2))
                self._visible_ok = top == self.world.snap.hwnd
            show = self._visible_ok
        if show != self.win.isVisible():
            self.win.setVisible(show)


def run():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app._ctl = Controller(app)
    return app.exec()
