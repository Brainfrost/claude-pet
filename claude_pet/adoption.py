"""Adoption: bis zu 5× würfeln, zwischen den Vorschlägen wählen, benennen – danach gehört das Pet dir.

Figur, Charakter und Name werden bei der Adoption festgelegt und später nie mehr geändert.
"""
import random

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
                             QWidget)

from . import creatures, personas, profile
from .speech import Speech

MAX_ROLLS = 5
CHAR_SHORT = {
    "faul": "Faul – schläft gern und lange, zieht sich in ruhige Sessions zurück.",
    "neugierig": "Neugierig – folgt dir überall hin und kommentiert, was im Terminal passiert.",
    "verspielt": "Verspielt – flitzt herum, jagt jeden Ball und hängt sich an deine Maus.",
    "aengstlich": "Ängstlich – erschrickt bei Fehlern, ist aber sehr anhänglich und lieb.",
}


class AdoptionPool:
    """Die gewürfelten Vorschläge (ohne Qt, damit testbar)."""

    def __init__(self, rnd=None, max_rolls=MAX_ROLLS):
        self.rnd = rnd or random.Random()
        self.max_rolls = max_rolls
        self.rolls = []          # [(figur, charakter)]
        self.index = -1

    @property
    def left(self):
        return self.max_rolls - len(self.rolls)

    def roll(self):
        if self.left <= 0:
            return None
        ids = creatures.creature_ids()
        seen = {c for c, _ in self.rolls}
        cid = self.rnd.choice([c for c in ids if c not in seen] or ids)    # möglichst Neues zeigen
        self.rolls.append((cid, profile.roll_personality(cid, self.rnd)))
        self.index = len(self.rolls) - 1
        return self.rolls[-1]

    def select(self, i):
        if 0 <= i < len(self.rolls):
            self.index = i

    @property
    def current(self):
        return self.rolls[self.index] if self.rolls else None


def short_description(cid):
    text = personas.CREATURE.get(cid, "").split(". ")[0].replace("Du bist ", "").rstrip(".")
    return (text[:1].upper() + text[1:] + ".") if text else ""


class _Preview(QWidget):
    """Animierte Vorschau einer Figur."""

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
        p.fillRect(self.rect(), QColor("#1e1b2e" if not self.selected else "#2e2850"))
        if self.clickable:
            p.setPen(QColor("#8f86c9" if self.selected else "#3a3556"))
            p.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 8, 8)
        if self.pick is None:
            p.setPen(QColor("#5c5680"))
            f = QFont("Segoe UI")
            f.setPixelSize(max(14, self.height() // 3))
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "?")
            p.end()
            return
        cid, pers = self.pick
        c = creatures.get(cid)
        cycle = int(self.t / 2.5) % 3 if not self.clickable else 0
        state = ("idle", "walk", "happy")[cycle]
        img = self.renderer.render(c, variant=pers, state=state, t=self.t, walk_i=int(self.t / 0.15),
                                   blinking=(self.t % 3.7) < 0.13, facing=1, px=self.px, stage="erwachsen")
        x = (self.width() - img.width()) // 2
        y = (self.height() - img.height()) // 2
        p.drawImage(x, y, img)
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
            QPushButton:disabled { color: #6b6690; border-color: #2b2745; }
            QPushButton#adopt { background: #6d5ce8; border-color: #8b7cf0; font-weight: 600; }
            QPushButton#adopt:hover { background: #7d6df0; }
        """)
        self.pool = AdoptionPool(rnd)
        self.renderer = creatures.Renderer()
        self._name_edited = False
        self.personas = {}                     # Index des Wurfs -> von Haiku erfundene Persönlichkeit
        self.speech = Speech({"name": "", "personality": "neugierig"})

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)
        head = QLabel("Ein neues Pet adoptieren")
        head.setObjectName("title")
        hint = QLabel(f"Du kannst bis zu {MAX_ROLLS}× würfeln und dann eines der Vorschläge wählen. "
                      "Figur, Charakter und Name bleiben danach für immer.")
        hint.setObjectName("sub")
        hint.setWordWrap(True)
        root.addWidget(head)
        root.addWidget(hint)

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
        for w in (self.art, self.desc, self.char):
            root.addWidget(w)
        h2 = QLabel("PERSÖNLICHKEIT")
        h2.setObjectName("head2")
        self.persona = QLabel()
        self.persona.setObjectName("persona")
        self.persona.setWordWrap(True)
        for w in (h2, self.persona):
            root.addWidget(w)

        thumbs = QHBoxLayout()
        self.thumbs = []
        for i in range(MAX_ROLLS):
            t = _Preview(self.renderer, px=2, clickable=True)
            t.setFixedSize(86, 70)
            t.on_click = lambda i=i: self._select(i)
            thumbs.addWidget(t)
            self.thumbs.append(t)
        root.addLayout(thumbs)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self.name = QLineEdit()
        self.name.setMaxLength(24)
        self.name.textEdited.connect(lambda _: setattr(self, "_name_edited", True))
        name_row.addWidget(self.name, 1)
        root.addLayout(name_row)

        buttons = QHBoxLayout()
        self.roll_btn = QPushButton()
        self.roll_btn.clicked.connect(self._roll)
        self.adopt_btn = QPushButton("Adoptieren")
        self.adopt_btn.setObjectName("adopt")
        self.adopt_btn.clicked.connect(self._adopt)
        buttons.addWidget(self.roll_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.adopt_btn)
        root.addLayout(buttons)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(60)
        self._roll()
        self.resize(580, 760)

    # ------------------------------------------------------------ Ablauf
    def _roll(self):
        if self.pool.roll() is not None:
            i = self.pool.index
            cid, pers = self.pool.current
            started = self.speech.invent_persona({"creature": cid, "personality": pers},
                                                 lambda text, i=i: self._persona_ready(i, text))
            if not started:
                self.personas[i] = ""
            self._show_current(new_name=True)

    def _persona_ready(self, i, text):
        self.personas[i] = text
        if i == self.pool.index:
            self._show_persona()

    def _show_persona(self):
        text = self.personas.get(self.pool.index)
        if text is None:
            self.persona.setText("Einen Moment, die Persönlichkeit entsteht gerade …")
        elif text:
            self.persona.setText(text)
        else:
            self.persona.setText("(Ohne claude-CLI: die Persönlichkeit entsteht nach der Adoption.)")

    def _select(self, i):
        if i < len(self.pool.rolls):
            self.pool.select(i)
            self._show_current(new_name=not self._name_edited)

    def _show_current(self, new_name):
        cid, pers = self.pool.current
        c = creatures.get(cid)
        self.preview.set_pick((cid, pers))
        self.art.setText(f"{c['name']} · {c['art']}")
        self.desc.setText(short_description(cid))
        self.char.setText(CHAR_SHORT.get(pers, pers))
        self._show_persona()
        if new_name:
            self.name.setText(c["name"])
            self._name_edited = False
        for i, t in enumerate(self.thumbs):
            t.set_pick(self.pool.rolls[i] if i < len(self.pool.rolls) else None)
            t.selected = i == self.pool.index
            t.update()
        left = self.pool.left
        self.roll_btn.setText(f"🎲  Neu würfeln (noch {left})" if left else "Keine Würfe mehr – wähle eines")
        self.roll_btn.setEnabled(left > 0)

    def _animate(self):
        self.preview.t += 0.06
        self.preview.update()

    def _adopt(self):
        cid, pers = self.pool.current
        name = self.name.text().strip() or creatures.get(cid)["name"]
        label = creatures.data()["variants"].get(pers, {}).get("label", pers)
        ok = QMessageBox.question(
            self, "Adoptieren?",
            f"{name} ({creatures.get(cid)['art']}, {label}) adoptieren?\n\n"
            "Das ist dann dein Pet – Figur, Charakter und Name bleiben für immer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if ok == QMessageBox.StandardButton.Yes:
            self.timer.stop()
            self.adopted.emit(cid, pers, name, self.personas.get(self.pool.index) or "")
            self.close()
