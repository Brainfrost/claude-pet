"""Adoption: aus allen Figuren frei wählen, benennen – danach gehört das Pet dir.

Jede Figur bekommt beim Öffnen des Fensters einen zufälligen Charakter (der Lieblingscharakter der Figur
mit 50 % Chance) und – sobald man sie anschaut – eine von Haiku erfundene einmalige Persönlichkeit. So hat
jeder eine einfache Auswahl, und die Pets sind trotzdem nie ganz gleich. Figur, Charakter, Persönlichkeit
und Name werden bei der Adoption festgelegt und später nie mehr geändert.
"""
import random

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                             QVBoxLayout, QWidget)

from . import creatures, personas, profile
from .speech import Speech

GRID_COLS = 7
CHAR_SHORT = {
    "faul": "Faul – schläft gern und lange, zieht sich in ruhige Sessions zurück.",
    "neugierig": "Neugierig – folgt dir überall hin und kommentiert, was im Terminal passiert.",
    "verspielt": "Verspielt – flitzt herum, jagt jeden Ball und hängt sich an deine Maus.",
    "aengstlich": "Ängstlich – erschrickt bei Fehlern, ist aber sehr anhänglich und lieb.",
}


class AdoptionOffer:
    """Alle Figuren mit je einem zufälligen Charakter (ohne Qt, damit testbar)."""

    def __init__(self, rnd=None):
        self.rnd = rnd or random.Random()
        self.picks = [(cid, profile.roll_personality(cid, self.rnd)) for cid in creatures.creature_ids()]
        self.index = self.rnd.randrange(len(self.picks))

    def select(self, i):
        if 0 <= i < len(self.picks):
            self.index = i

    @property
    def current(self):
        return self.picks[self.index]


def short_description(cid):
    text = personas.CREATURE.get(cid, "").split(". ")[0].replace("Du bist ", "").rstrip(".")
    return (text[:1].upper() + text[1:] + ".") if text else ""


class _Preview(QWidget):
    """Animierte Vorschau einer Figur (groß) bzw. Kachel im Raster (klein, anklickbar)."""

    def __init__(self, renderer, px, parent=None, clickable=False):
        super().__init__(parent)
        self.renderer, self.px = renderer, px
        self.pick = None
        self.t = 0.0
        self.selected = False
        self.clickable = clickable
        self.on_click = None
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_pick(self, pick):
        self.pick = pick
        self.update()

    def mousePressEvent(self, e):
        if self.clickable and self.on_click:
            self.on_click()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#2e2850" if self.selected else "#1e1b2e"))
        if self.clickable:
            p.setPen(QColor("#8f86c9" if self.selected else "#3a3556"))
            p.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 8, 8)
        if self.pick is not None:
            cid, pers = self.pick
            c = creatures.get(cid)
            moving = not self.clickable or self.selected
            state = ("idle", "walk", "happy")[int(self.t / 2.5) % 3] if not self.clickable else (
                "happy" if self.selected else "idle")
            img = self.renderer.render(c, variant=pers, state=state, t=self.t if moving else 0.0,
                                       walk_i=int(self.t / 0.15), blinking=(self.t % 3.7) < 0.13,
                                       facing=1, px=self.px, stage="erwachsen")
            p.drawImage((self.width() - img.width()) // 2, (self.height() - img.height()) // 2, img)
        p.end()


class AdoptionDialog(QWidget):
    adopted = pyqtSignal(str, str, str, str)  # figur, charakter, name, persönlichkeit ("" = später)

    def __init__(self, rnd=None):
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle("Adoption – claude-pet")
        self.setStyleSheet("""
            QWidget { background: #14121f; color: #ece9f7; font-family: 'Segoe UI'; font-size: 14px; }
            QLabel#title { font-size: 22px; font-weight: 600; }
            QLabel#sub { color: #a9a3c9; }
            QLabel#char { color: #d8d2f5; }
            QLabel#head2 { color: #8f86c9; font-size: 12px; font-weight: 600; letter-spacing: 1px; }
            QLabel#persona { color: #ece9f7; font-size: 13px; font-style: italic; background: #221d3d;
                             border-radius: 6px; padding: 8px 10px; }
            QLineEdit { background: #221f35; border: 1px solid #3a3556; border-radius: 6px; padding: 6px 8px;
                        font-size: 15px; }
            QPushButton { background: #2b2745; border: 1px solid #4a4470; border-radius: 8px; padding: 8px 14px; }
            QPushButton:hover { background: #363057; }
            QPushButton#adopt { background: #6d5ce8; border-color: #8b7cf0; font-weight: 600; }
            QPushButton#adopt:hover { background: #7d6df0; }
        """)
        self.offer = AdoptionOffer(rnd)
        self.renderer = creatures.Renderer()
        self._name_edited = False
        self.personas = {}                     # Figur -> von Haiku erfundene Persönlichkeit ("" = keine)
        self.speech = Speech({"name": "", "personality": "neugierig"})

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)
        head = QLabel("Ein Pet adoptieren")
        head.setObjectName("title")
        hint = QLabel("Wähle dein Pet aus. Jedes hat heute einen zufälligen Charakter und eine eigene "
                      "Persönlichkeit. Figur, Charakter und Name bleiben nach der Adoption für immer.")
        hint.setObjectName("sub")
        hint.setWordWrap(True)
        root.addWidget(head)
        root.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(6)
        self.tiles = []
        for i, pick in enumerate(self.offer.picks):
            t = _Preview(self.renderer, px=2, clickable=True)
            t.setFixedSize(84, 64)
            t.set_pick(pick)
            t.on_click = lambda i=i: self._select(i)
            grid.addWidget(t, i // GRID_COLS, i % GRID_COLS)
            self.tiles.append(t)
        root.addLayout(grid)

        self.preview = _Preview(self.renderer, px=5)
        self.preview.setMinimumSize(420, 150)
        root.addWidget(self.preview)
        self.art = QLabel()
        self.art.setObjectName("title")
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desc = QLabel()
        self.desc.setObjectName("sub")
        self.desc.setWordWrap(True)
        self.desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.char = QLabel()
        self.char.setObjectName("char")
        self.char.setWordWrap(True)
        self.char.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h2 = QLabel("PERSÖNLICHKEIT")
        h2.setObjectName("head2")
        self.persona = QLabel()
        self.persona.setObjectName("persona")
        self.persona.setWordWrap(True)
        self.persona.setMinimumHeight(70)
        for w in (self.art, self.desc, self.char, h2, self.persona):
            root.addWidget(w)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self.name = QLineEdit()
        self.name.setMaxLength(24)
        self.name.textEdited.connect(lambda _: setattr(self, "_name_edited", True))
        name_row.addWidget(self.name, 1)
        self.adopt_btn = QPushButton("Adoptieren")
        self.adopt_btn.setObjectName("adopt")
        self.adopt_btn.clicked.connect(self._adopt)
        name_row.addWidget(self.adopt_btn)
        root.addLayout(name_row)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(60)
        self._select(self.offer.index)
        self.resize(680, 800)

    # ------------------------------------------------------------ Ablauf
    def _select(self, i):
        self.offer.select(i)
        cid, pers = self.offer.current
        c = creatures.get(cid)
        self.preview.set_pick((cid, pers))
        self.art.setText(f"{c['name']} · {c['art']}")
        self.desc.setText(short_description(cid))
        self.char.setText(CHAR_SHORT.get(pers, pers))
        if not self._name_edited:
            self.name.setText(c["name"])
        for j, t in enumerate(self.tiles):
            t.selected = j == self.offer.index
            t.update()
        if cid not in self.personas:
            self.personas[cid] = None          # wird gerade erfunden
            started = self.speech.invent_persona({"creature": cid, "personality": pers},
                                                 lambda text, cid=cid: self._persona_ready(cid, text))
            if not started:
                self.personas[cid] = ""
        self._show_persona()

    def _persona_ready(self, cid, text):
        self.personas[cid] = text
        if self.offer.current[0] == cid:
            self._show_persona()

    def _show_persona(self):
        text = self.personas.get(self.offer.current[0])
        if text is None:
            self.persona.setText("Einen Moment, die Persönlichkeit entsteht gerade …")
        elif text:
            self.persona.setText(text)
        else:
            self.persona.setText("(Die Persönlichkeit entsteht nach der Adoption.)")

    def _animate(self):
        self.preview.t += 0.06
        self.preview.update()
        t = self.tiles[self.offer.index]
        t.t += 0.06
        t.update()

    def _adopt(self):
        cid, pers = self.offer.current
        name = self.name.text().strip() or creatures.get(cid)["name"]
        label = creatures.data()["variants"].get(pers, {}).get("label", pers)
        ok = QMessageBox.question(
            self, "Adoptieren?",
            f"{name} ({creatures.get(cid)['art']}, {label}) adoptieren?\n\n"
            "Das ist dann dein Pet – Figur, Charakter und Name bleiben für immer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if ok == QMessageBox.StandardButton.Yes:
            self.timer.stop()
            self.adopted.emit(cid, pers, name, self.personas.get(cid) or "")
            self.close()
