"""Ein einfaches Lesefenster im Stil des Adoptionsfensters – für Tagebuch und Schatzkiste."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

STYLE = """
    QWidget { background: #14121f; color: #ece9f7; font-family: 'Segoe UI'; font-size: 14px; }
    QLabel#title { font-size: 20px; font-weight: 600; }
    QLabel#sub { color: #8f86c9; font-size: 12px; }
    QTextBrowser { background: #1b1830; border: 1px solid #2e2a4a; border-radius: 10px; padding: 10px; }
    QPushButton { background: #2b2745; border: 1px solid #4a4470; border-radius: 8px; padding: 7px 14px; }
    QPushButton:hover { background: #363057; }
    QPushButton:disabled { color: #6c6790; }
    QScrollBar:vertical { background: transparent; width: 10px; margin: 4px 2px; }
    QScrollBar::handle:vertical { background: #3a3556; border-radius: 3px; min-height: 30px; }
    QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: none; }
"""
DOC_CSS = """
    p.wh { color: #f2c66d; font-weight: 600; margin: 0 0 4px 0; }
    h3 { color: #b9adff; font-size: 14px; margin: 14px 0 2px 0; }
    p { margin: 2px 0 4px 0; line-height: 140%; }
    p.sym { color: #8f86c9; font-size: 12px; }
    td { padding: 3px 10px 3px 0; }
    .rar { font-size: 11px; color: #8f86c9; }
"""


class BookWindow(QWidget):
    """Titel, Untertitel, HTML-Inhalt und optional ein Knopf unten."""

    def __init__(self, title, subtitle, html, button=None, on_button=None, size=(560, 640)):
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle(title)
        self.setStyleSheet(STYLE)
        self.resize(*size)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        t = QLabel(title)
        t.setObjectName("title")
        lay.addWidget(t)
        self.sub = QLabel(subtitle)
        self.sub.setObjectName("sub")
        self.sub.setWordWrap(True)
        lay.addWidget(self.sub)
        self.view = QTextBrowser()
        self.view.document().setDefaultStyleSheet(DOC_CSS)
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.button = None
        if button:
            self.button = QPushButton(button)
            self.button.clicked.connect(on_button)
            row.addWidget(self.button)
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        row.addWidget(close)
        lay.addLayout(row)
        self.set_html(html)

    def set_html(self, html):
        bar = self.view.verticalScrollBar()
        pos = bar.value()
        self.view.setHtml(html)
        bar.setValue(pos)

    def show_front(self):
        self.show()
        self.raise_()
        self.activateWindow()
