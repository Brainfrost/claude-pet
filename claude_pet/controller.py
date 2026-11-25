"""Steuerung: verbindet Terminal, Welt, Pet, Gehirn, Sprache und Fenster und treibt die Spielschleife."""
import logging
import random
import time

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

from datetime import date, datetime

from . import creatures, daily, growth, profile, quiet, settings, vision, winapi
from .adoption import AdoptionDialog
from .ball import Ball
from .brain import Brain
from .pet import AIR, TRANSITION, Pet
from .reactions import Reactions
from .speech import Speech
from .stats import StatsWatcher
from .terminal import TerminalWatcher
from .tray import Tray
from .windows import BallWindow, BiteFx, Bubble, DebugOverlay, PetWindow, TabFx
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
    def __init__(self, app, prof, fresh=False):
        self.app = app
        self.world = World()
        self.settings = settings.load()
        self.quiet_reason = None
        self.prof = growth.ensure_defaults(prof)
        growth.absence(self.prof)
        self.renderer = creatures.Renderer()
        self._new_pet()

        self.win = PetWindow(self)
        self.bubble = Bubble()
        self.tabfx = TabFx()
        self.bitefx = BiteFx()
        self.ball = None
        self.ball_win = BallWindow(self)
        self.work = daily.WorkTracker()
        self._day_t = self._work_t = 0.0
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
        self._debug_t = self._log_t = self._hover_t = 0.0
        self._hover_word = None
        self._pending_action = None
        self._interval = 16

        self.watcher = TerminalWatcher()
        self.watcher.snapshot.connect(self.on_snapshot)
        self.watcher.start()
        self.stats = StatsWatcher(self.prof.get("born"))
        self.stats.delta.connect(self.on_stats)
        self.stats.start()
        self.vision = vision.VisionWorker()        # Bildanalyse im Hintergrund (Animation ruckelt nie)
        self.vision.done.connect(self.on_vision)
        self.vision.start()

        self.timer = QTimer()
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(self._interval)
        self.tray = Tray(self)
        if not self.prof.get("lines"):
            self.speech.invent_lines(self.prof, self.on_lines)
        if fresh:
            QTimer.singleShot(2500, lambda: self._say(f"Hallo! Ich bin {self.prof['name']}. Schön, dass du mich adoptiert hast!"))

    # ================================================================ Pet & Profil
    def _new_pet(self):
        self.pet = Pet(creatures.get(self.prof["creature"]), self.prof.get("stage", "baby"),
                       self.prof["personality"])
        self.brain = Brain(self.pet, self.prof["personality"])
        self.brain.on_ate = self.on_ate
        self.brain.on_fetched = self.on_fetched
        self.brain.ball = getattr(self, "ball", None)
        self.pet.daypart = daily.daypart()
        # Energie: zuletzt gespeicherter Stand, plus Erholung für die Zeit, in der das Pet aus war
        away_h = max(0.0, (time.time() - self.prof.get("last_seen", time.time())) / 3600.0)
        self.pet.energy = min(100.0, self.prof.get("energy", 100.0) + away_h * 60.0)
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

    def dev_reset(self):
        """Nur für die Entwicklung (CLAUDE_PET_DEV=1): Pet archivieren und neu adoptieren."""
        path = profile.archive("Entwicklung: zurückgesetzt")
        log.info("Pet archiviert: %s", path)
        self.quit()

    def on_lines(self, lines):
        """Persönlicher Spruch-Satz von Haiku – einmalig, danach gratis und offline."""
        self.prof["lines"] = lines
        profile.save(self.prof)
        log.info("Persönliche Sprüche für %s: %d Anlässe", self.prof["name"], len(lines))

    def _hover(self, now, cursor):
        """Mauszeiger ruht auf einem Wort im Terminal -> das Pet reagiert (selten auch mit Haiku)."""
        if now - self._hover_t < 0.25:
            return
        self._hover_t = now
        if self.brain.cursor_still_t < 1.0:
            if self.brain.cursor_still_t < 0.2:
                self._hover_word = None
            return
        hit = self.world.word_at(*cursor)
        if hit is None or hit[0] == self._hover_word:
            return
        word, x, plat = hit
        self._hover_word = word
        if self.brain.hovered(word, x, plat, self.world):
            log.info("Maus auf Wort: %s", word)
            if random.random() < 0.12:
                self.speech.on_event("hover", self.world, plat.pane, detail=word)

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

    # ================================================================ Spielen
    def throw_ball(self):
        """Ball ab Mauszeiger in die Welt werfen."""
        x, y = winapi.cursor_pos()
        self.ball = Ball(x, y - 30, random.uniform(-700, 700), random.uniform(-900, -400), self.pet.line_h)
        self.brain.ball = self.ball
        self.ball_win.place(self.ball)
        self.ball_win.show()
        log.info("Ball geworfen")

    def remove_ball(self):
        self.ball = None
        self.brain.ball = None
        self.pet.carrying = False
        if self.brain.goal and self.brain.goal[0] == "ball":
            self.brain.goal, self.pet.busy = None, False
        self.ball_win.hide()

    def grab_ball(self):
        if self.ball is None:
            return
        if self.ball.carried_by == "pet":
            self.pet.carrying = False
        self.ball.carried_by = "user"

    def terminal_focused(self):
        """Ist das Windows Terminal gerade das aktive Fenster?"""
        return bool(self.world.ok and winapi.user32.GetForegroundWindow() == self.world.snap.hwnd)

    def messenger(self, tab):
        """Bote: eine Session ist fertig und du schaust woanders hin -> das Pet holt dich."""
        now = time.time()
        if (not self.settings.get("messenger", True) or self.quiet_reason
                or now - getattr(self, "_messenger_t", 0) < 30):
            return
        if self.pet.come_to_user():
            self._messenger_t = now
            self._messenger_text = tab[:40]
            log.info("Bote: %s ist fertig", tab)

    def on_fetched(self):
        self.prof["fetched"] = self.prof.get("fetched", 0) + 1
        self.speech.canned("fetch", force=random.random() < 0.5)
        self.interact("stroke")

    def on_ate(self, word, platform, start):
        """Pet hat ein Wort angeknabbert: Biss anzeigen, zählen, kommentieren."""
        n = growth.count_eaten(self.prof, date.today().isoformat())
        profile.save(self.prof)
        if self.world.ok and platform.pane < len(self.world.snap.panes):
            pane = self.world.snap.panes[platform.pane]
            x = platform.x0 + start * pane.cell_w
            y = platform.y - 0.18 * pane.line_h
            rect = (x, y, len(word) * pane.cell_w, pane.line_h)
            self.bitefx.bite(rect, self._background_at(x - 3, y + pane.line_h / 2))
        self.speech.canned("eat", force=True, word=word, today=n)
        log.info("Wort gefressen: %s (%d heute)", word, n)

    @staticmethod
    def _background_at(x, y):
        """Hintergrundfarbe direkt neben dem Wort (damit der Biss wie ein Loch im Text aussieht)."""
        res = vision.grab(int(x) - 2, int(y) - 2, 4, 4)
        if res is None:
            return "#0c0c0c"
        v = int(res[0].mean())
        return f"#{v:02x}{v:02x}{v:02x}"

    def _tick_daily(self, now):
        """Tageszeit, Morgengruß, Pausen-Erinnerung (zwei- bzw. einmal pro Minute)."""
        if now - self._day_t > 60:
            self._day_t = now
            self.pet.daypart = part = daily.daypart()
            today = date.today().isoformat()
            if part == "morgen" and self.prof.get("last_greet") != today and daily.idle_seconds() < 60:
                self.prof["last_greet"] = today
                profile.save(self.prof)
                self.pet.react("done")
                self.speech.canned("morning", force=True)
            # Mittag, Feierabend, Freitagnachmittag – je einmal am Tag, wenn du gerade da bist
            moments = self.prof.setdefault("moments", {"date": "", "done": []})
            if moments.get("date") != today:
                moments["date"], moments["done"] = today, []
            if daily.idle_seconds() < 60 and self.pet.state not in ("hidden", "sleep"):
                for key in daily.due_moments(datetime.now(), moments["done"])[:1]:
                    moments["done"].append(key)
                    profile.save(self.prof)
                    self.pet.perform({"lunch": "freuen", "evening": "hinsetzen", "weekend": "tanzen"}[key])
                    if key == "evening":
                        self.pet._effect("gähn", life=1.8)
                    self.speech.canned(key, force=True)
                    log.info("Tagesmoment: %s", key)
        if now - self._work_t > 30:
            self._work_t = now
            s = self.settings
            if s.get("break_reminder") and self.work.reminder_due(s.get("break_minutes", 120)):
                mins = self.work.update()
                hours = f"{mins / 60:.1f}".replace(".", ",").replace(",0", "") + " Stunden"
                if self.pet.state == "hidden" and self.brain.home is not None and self.world.ok:
                    i = self.brain._find(self.world, self.brain.home)
                    if i is not None:
                        self.brain._emerge(self.world, i)
                self.pet.perform("huepfen")
                self.speech.canned("break", force=True, hours=hours)
                log.info("Pausen-Erinnerung nach %.0f Minuten", mins)
            back = self.work.take_return()
            if back is not None and back >= 10 and random.random() < 0.7:
                self.speech.canned("welcome", force=True)

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
        """Von Haiku gewählte Aktion – erst nach dem Satz (das Pet redet gerade)."""
        self._pending_action = (action, target)

    def _do_action(self, action, target):
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
        if not self.vision.busy("scan"):
            self.vision.request("scan", [(g.x(), g.y(), g.width(), g.height())], info=i)

    def quit(self):
        self.prof["last_seen"] = time.time()
        self.prof["energy"] = round(self.pet.energy, 1)
        profile.save(self.prof)
        self.stats.stop()
        self.vision.stop()
        self.vision.wait(1500)
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
            self.ball_win.hide()
            self._adapt_rate(pet)
            return
        if pet.state in ("idle", "sit", "happy", "talk") and abs(cursor[0] - pet.x) > pet.W * 1.5:
            pet.facing = 1 if cursor[0] > pet.x else -1          # schaut zu dir
        self._update_surroundings(now)
        growth.drift(self.prof, dt)
        pet.mood, pet.bond = self.prof["mood"], self.prof["bond"]
        if now - self._last_save > 30:
            self._last_save = now
            self.prof["last_seen"] = time.time()
            self.prof["energy"] = round(pet.energy, 1)
            profile.save(self.prof)

        self._tick_daily(now)
        if self.world.ok:
            self._hover(now, cursor)
        self.brain.tick(dt, self.world, cursor)
        pet.step(dt, self.world, self.screen_floor, self.vbounds(), cursor)
        self._tick_ball(dt)
        self._play_tab_effects()
        self._update_visibility(now)
        self.place()
        if pet.state != self._prev_state:
            if pet.state == "cling" and getattr(self, "_messenger_text", None):
                self.speech.canned("messenger", force=True, tab=self._messenger_text)
                self._messenger_text = None
                self.brain.cling_t = 7.0
                self.pet._effect("!", life=1.2)
            elif pet.state == "cling":
                self.speech.canned("cling")
                self.interact("cling")
            self._prev_state = pet.state
        visible = self.win.isVisible() and pet.state != "hidden"
        self.speech.tick(self.world, pet.pane or 0, visible and pet.grounded)
        self.bubble.follow(pet, visible)
        self._talk(pet)
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
        if outside and now - self._vision_check > 0.33 and not self.vision.busy("near"):
            self._vision_check = now
            self.vision.request("near", [(pet.x - 550, pet.y - 540, 1100, 900)], self._exclusions())
        if pet.want_adventure:
            self._adventure()
        self.watcher.poll_hz = 8 if (pet.pane is not None and pet.state != "hidden") else 4

    def _tick_ball(self, dt):
        ball = self.ball
        if ball is None:
            return
        if ball.carried_by == "pet":
            pet = self.pet
            ball.x = pet.x + pet.facing * pet.W * 0.35
            ball.y = pet.y - pet.H * 0.45
        ball.step(dt, self.world, self.screen_floor, self.vbounds())
        if ball.idle_t > 180:                       # drei Minuten unbeachtet: aufräumen
            self.remove_ball()
            return
        visible = not (ball.carried_by == "pet" and not self.win.isVisible())
        if visible != self.ball_win.isVisible():
            self.ball_win.setVisible(visible)
        if ball.carried_by != "user":
            self.ball_win.place(ball)

    def _talk(self, pet):
        """Während die Sprechblase zu sehen ist, bleibt das Pet stehen und redet; danach macht es,
        was Haiku als Aktion vorgeschlagen hat."""
        speaking = bool(self.bubble.text) and self.bubble.isVisible()
        if speaking:
            if pet.state != "talk":
                pet.start_talking()           # in der Luft: klappt nach der Landung
        elif pet.state == "talk":
            pet.stop_talking()
        if not speaking and self._pending_action and pet.state != "talk":
            action, target = self._pending_action
            self._pending_action = None
            self._do_action(action, target)

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
        elif (st in AIR or st in TRANSITION or st in ("held", "cling", "walk", "fly") or pet.effects
              or pet.squash > 0 or self.bubble.isVisible() or self.debug_on
              or (self.ball is not None and not (self.ball.resting and self.ball.vx == 0))):
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
        rects = [(cx - 450, cy - 420, 900, 700) for cx, cy in spots[:2]]
        if rects:
            self.vision.request("trip", rects, self._exclusions())

    def on_vision(self, tag, info, rect, runs):
        """Ergebnis einer Bildanalyse aus dem Hintergrund-Thread."""
        term = self.world.snap.win_rect if self.world.ok else None

        def in_term(x, y):
            return term and term[0] <= x < term[2] and term[1] <= y < term[3]

        runs = [r for r in runs if not in_term((r[1] + r[2]) / 2, r[0])]
        pet = self.pet
        if tag == "near":
            if pet.pane is None:                    # inzwischen wieder im Terminal: verwerfen
                self.world.set_vision(runs)
                pet.on_vision(self.world)
        elif tag == "scan":
            if self.debug_on:
                self.debug_scan[info] = runs
        elif tag == "trip":
            runs = [r for r in runs if r[2] - r[1] >= pet.W * 1.2]
            if runs:
                self.world.set_vision(runs)         # Ziel muss beim Landen bekannt sein
                y, a, b = random.choice(runs)
                if pet.adventure_to(a, b, y):
                    log.info("Ausflug nach (%d, %d)", (a + b) // 2, y)

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
    prof = profile.load()
    if prof is not None:
        app.setQuitOnLastWindowClosed(False)
        app._ctl = Controller(app, prof)
        return app.exec()
    # noch kein Pet: erst adoptieren (Fenster zu ohne Adoption -> beenden)
    dlg = AdoptionDialog()

    def adopted(cid, pers, name, persona):
        app.setQuitOnLastWindowClosed(False)
        new = profile.adopt(cid, pers, name, persona or None)
        log.info("Adoptiert: %s (%s, %s)", name, cid, pers)
        app._ctl = Controller(app, new, fresh=True)

    dlg.adopted.connect(adopted)
    dlg.show()
    app._dlg = dlg
    return app.exec()

