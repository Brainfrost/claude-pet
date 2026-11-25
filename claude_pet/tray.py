"""Tray-Symbol und -Menü: Steckbrief, Aktionen, Einstellungen, Entwicklung, Accessoires."""
from PyQt6.QtGui import QAction, QIcon, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

import os
from datetime import date

from . import creatures, growth


def _today():
    return date.today().isoformat()

SIZES = (("klein", "Klein"), ("normal", "Normal"), ("gross", "Groß"))
TALK = (("aus", "Aus (nur auf Wunsch)"), ("wenig", "Wenig"), ("normal", "Normal"), ("viel", "Viel"))
BREAK_MIN = ((60, "1 Stunde"), (90, "1,5 Stunden"), (120, "2 Stunden"), (150, "2,5 Stunden"))
SWITCHES = (("bubbles", "Sprechblasen anzeigen"),
            ("break_reminder", "Pausen-Erinnerung"),
            ("messenger", "Bote: holt mich, wenn eine Session fertig ist"),
            ("quiet_calls", "Ruhemodus bei Calls (Mikrofon aktiv)"),
            ("quiet_fullscreen", "Ruhemodus bei Vollbild/Präsentation"),
            ("autostart", "Mit Windows starten"))


class Tray:
    def __init__(self, ctl):
        self.ctl = ctl
        self.icon = QSystemTrayIcon()
        m = self.menu = QMenu()
        self.a_info = QAction("", m)
        self.a_info.setEnabled(False)
        m.addAction(self.a_info)
        m.addSeparator()
        self._action(m, "Was denkst du gerade?", lambda: ctl.speech.ask_now(ctl.world, ctl.pet.pane or 0))
        self._action(m, "Ausflug machen!", lambda: setattr(ctl.pet, "want_adventure", True))
        self._action(m, "Ball werfen", ctl.throw_ball)
        self.a_noball = self._action(m, "Ball wegräumen", ctl.remove_ball)
        self._action(m, "Pet zu mir holen", ctl.summon)
        a_dbg = QAction("Entwickler-Ansicht", m, checkable=True)
        a_dbg.toggled.connect(ctl.toggle_debug)
        m.addAction(a_dbg)
        m.addSeparator()
        self.a_dnd = QAction("Bitte nicht stören", m, checkable=True)
        self.a_dnd.toggled.connect(lambda on: ctl.set_setting("dnd", on))
        m.addAction(self.a_dnd)
        self.m_set = m.addMenu("Einstellungen")
        self.m_dev = m.addMenu("Entwicklung")
        self.m_acc = m.addMenu("Accessoires")
        m.aboutToShow.connect(self._refresh)
        m.addSeparator()
        if os.environ.get("CLAUDE_PET_DEV") == "1":
            self._action(m, "Entwicklung: Pet archivieren und neu adoptieren", ctl.dev_reset)
        self._action(m, "Beenden", ctl.quit)
        self.icon.setContextMenu(m)
        self.update_identity()
        self.icon.show()

    @staticmethod
    def _action(menu, text, slot):
        a = QAction(text, menu)
        a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def hide(self):
        self.icon.hide()

    # ------------------------------------------------------------ Anzeige
    def update_identity(self):
        ctl = self.ctl
        prof, c = ctl.prof, ctl.pet.creature
        img = ctl.renderer.render(c, variant=prof["personality"], state="idle", t=0, walk_i=0,
                                  blinking=False, facing=1, px=2, stage="erwachsen")
        icon_img = img.copy(creatures.MARGIN_X * 2, creatures.MARGIN_TOP * 2, c["w"] * 2, c["h"] * 2)
        self.icon.setIcon(QIcon(QPixmap.fromImage(icon_img)))
        label = creatures.data()["variants"].get(prof["personality"], {}).get("label", "")
        text = f"{prof['name']} – {label} ({prof.get('stage', 'baby')})"
        persona = prof.get("persona")
        self.icon.setToolTip(text + ("\n\n" + persona if persona else ""))
        if ctl.quiet_reason:
            text += f"  ·  Ruhemodus: {ctl.quiet_reason}"
        self.a_info.setText(text)

    def _refresh(self):
        self.a_noball.setEnabled(self.ctl.ball is not None)
        self._fill_settings()
        self._fill_development()

    def _fill_settings(self):
        s, ctl = self.ctl.settings, self.ctl
        self.a_dnd.blockSignals(True)
        self.a_dnd.setChecked(bool(s.get("dnd")))
        self.a_dnd.blockSignals(False)
        self.m_set.clear()
        for title, key, opts in (("Größe", "size", SIZES), ("Redefreude", "talk", TALK)):
            sub = self.m_set.addMenu(title)
            for val, label in opts:
                a = sub.addAction(label)
                a.setCheckable(True)
                a.setChecked(s.get(key) == val)
                a.triggered.connect(lambda _=False, key=key, val=val: ctl.set_setting(key, val))
        sub = self.m_set.addMenu("Pause erinnern nach")
        for val, label in BREAK_MIN:
            a = sub.addAction(label)
            a.setCheckable(True)
            a.setChecked(s.get("break_minutes") == val)
            a.triggered.connect(lambda _=False, val=val: ctl.set_setting("break_minutes", val))
        self.m_set.addSeparator()
        for key, label in SWITCHES:
            a = self.m_set.addAction(label)
            a.setCheckable(True)
            a.setChecked(bool(s.get(key)))
            a.toggled.connect(lambda on, key=key: ctl.set_setting(key, on))

    def _fill_development(self):
        pr = self.ctl.prof
        st = pr.get("stats", {})
        nxt, need = growth.next_stage(pr["xp"])
        active = growth.hours(pr["xp"])
        tricks = [growth.TRICKS[t].split(" – ")[0] for t in pr.get("tricks", [])]
        lines = [
            f"Stufe: {pr.get('stage')}  ·  aktive Zeit {active}"
            + (f" / {growth.hours(need)} bis {nxt}" if nxt else ""),
            f"Bindung {pr['bond']:.0f}/100  ·  Stimmung {pr['mood']:.0f}/100  ·  Energie {self.ctl.pet.energy:.0f}/100",
            f"Seit Geburt: {st.get('tools', 0)} Tool-Aufrufe, {st.get('prompts', 0)} Eingaben, "
            f"{st.get('sessions', 0)} Sessions",
            "Tricks: " + (", ".join(tricks) if tricks else "noch keine"),
            f"Gefressen: {pr['eaten'].get('today', 0) if pr['eaten'].get('date') == _today() else 0} heute, "
            f"{pr['eaten'].get('total', 0)} insgesamt  ·  Ball gebracht: {pr.get('fetched', 0)}×",
        ]
        self.m_dev.clear()
        for t in lines:
            self.m_dev.addAction(t).setEnabled(False)
        self.m_acc.clear()
        for acc, (_keys, _need, desc) in growth.ACCESSORIES.items():
            label = desc.split(" – ")[0]
            have, need_n = growth.accessory_progress(pr, acc)
            if acc in pr.get("accessories", []):
                a = self.m_acc.addAction(label)
                a.setCheckable(True)
                a.setChecked(acc not in pr.get("accessories_off", []))
                a.toggled.connect(lambda on, acc=acc: self.ctl.toggle_accessory(acc, on))
            else:
                self.m_acc.addAction(f"{label} – gesperrt ({have}/{need_n})").setEnabled(False)
