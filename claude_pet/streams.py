"""Empfängt die Terminal-Ausgabe von der Begleit-Erweiterung in VS Code/Cursor.

Die Erweiterung (Ordner vscode-extension/) verbindet sich mit einem lokalen Kanal – Named Pipe unter
Windows, Unix-Socket auf dem Mac – und schickt zeilenweise JSON:

    {"type": "hello", "app": "Visual Studio Code", "workspace": "projekt", "version": 1}
    {"type": "start", "term": "t1", "cmd": "claude", "dims": {"columns": 177, "rows": 39}, "title": "…"}
    {"type": "data",  "term": "t1", "d": "<Rohdaten mit Escape-Sequenzen>"}
    {"type": "end",   "term": "t1"}
    {"type": "active", "term": "t1"}          # aktives Terminal des Fensters (oder null)
    {"type": "closed", "term": "t1"}          # Terminal geschlossen

Nichts davon wird gespeichert; der Kanal ist nur für den eigenen Benutzer erreichbar.
"""
import getpass
import json
import logging
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field

from .emulator import TermEmulator

log = logging.getLogger(__name__)

MAX_LINE = 4 * 1024 * 1024        # Schutz gegen kaputte Gegenstellen
_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def channel_name():
    """Name des Kanals; die Erweiterung bildet ihn genauso (pro Benutzer)."""
    user = _SAFE.sub("_", getpass.getuser() or "user")
    name = f"claude-pet-{user}"
    if os.name == "nt":
        return name                                   # -> \\.\pipe\claude-pet-<user>
    return os.path.join(tempfile.gettempdir(), name)  # $TMPDIR/claude-pet-<user>


@dataclass
class Session:
    """Ein Terminal in VS Code/Cursor, in dem Claude Code lief oder läuft."""
    key: tuple                        # (Verbindung, Terminal-ID der Erweiterung)
    app: str = ""
    workspace: str = ""
    emu: TermEmulator = None
    start_dims: tuple = None          # (cols, rows) beim Start von claude – zum Kalibrieren der Zellgröße
    cell: tuple = None                # (Zellbreite, Zeilenhöhe) in Pixeln, vom Watcher gesetzt
    running: bool = False
    active: bool = False
    title: str = ""                   # letzter Titel laut Erweiterung (falls der Strom ihn nicht enthält)
    started: float = 0.0
    align_pending: bool = True        # neue Ausgabe: Startzeile unbekannt -> am Cursor ausrichten
    misalign: dict = field(default_factory=dict)

    @property
    def best_title(self):
        return (self.emu.title if self.emu else "") or self.title


class StreamHub:
    """Hält die Emulatoren. Nachrichten kommen im GUI-Thread an (QLocalServer), gelesen wird im
    Watcher-Thread – deshalb ein Lock um alles."""

    def __init__(self):
        self.lock = threading.Lock()
        self.sessions = {}            # key -> Session
        self.clients = {}             # Verbindungs-ID -> {"app":…, "workspace":…}
        self._server = None
        self._sockets = {}

    # ------------------------------------------------------------ Protokoll (ohne Qt testbar)
    def handle(self, cid, msg):
        typ = msg.get("type")
        with self.lock:
            if typ == "hello":
                self.clients[cid] = {"app": str(msg.get("app", "")), "workspace": str(msg.get("workspace", ""))}
                log.info("VS-Code-Erweiterung verbunden: %s (%s)", msg.get("app"), msg.get("workspace"))
                return
            term = msg.get("term")
            if term is None and typ != "active":
                return
            key = (cid, str(term))
            if typ == "start":
                s = self._session(cid, key)
                d = msg.get("dims") or {}
                cols, rows = int(d.get("columns") or 0), int(d.get("rows") or 0)
                if cols > 1 and rows > 1:
                    s.start_dims = (cols, rows)
                    s.emu.resize(cols, rows)
                    s.cell = None                 # neu kalibrieren
                s.running, s.started, s.align_pending = True, time.time(), True
                if msg.get("title"):
                    s.title = str(msg["title"])
            elif typ == "data":
                s = self._session(cid, key)
                s.emu.feed(str(msg.get("d", "")))
            elif typ == "end":
                s = self.sessions.get(key)
                if s:
                    s.running = False
            elif typ == "closed":
                self.sessions.pop(key, None)
            elif typ == "active":
                for k, s in self.sessions.items():
                    if k[0] == cid:
                        s.active = term is not None and k == key

    def _session(self, cid, key):
        s = self.sessions.get(key)
        if s is None:
            c = self.clients.get(cid, {})
            s = Session(key=key, app=c.get("app", ""), workspace=c.get("workspace", ""), emu=TermEmulator())
            self.sessions[key] = s
        return s

    def drop_client(self, cid):
        with self.lock:
            self.clients.pop(cid, None)
            for k in [k for k in self.sessions if k[0] == cid]:
                del self.sessions[k]

    def snapshot_sessions(self):
        """Liste der Sitzungen (nur unter self.lock benutzen!)."""
        return list(self.sessions.values())

    # ------------------------------------------------------------ Qt-Kanal
    def start(self):
        from PyQt6.QtNetwork import QLocalServer
        name = channel_name()
        srv = QLocalServer()
        srv.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        QLocalServer.removeServer(name)               # Überbleibsel eines abgestürzten Laufs
        if not srv.listen(name):
            log.warning("Kanal für die VS-Code-Erweiterung nicht verfügbar: %s", srv.errorString())
            return False
        srv.newConnection.connect(self._on_connection)
        self._server = srv
        log.info("Kanal für VS Code/Cursor: %s", srv.fullServerName())
        return True

    def stop(self):
        if self._server is not None:
            self._server.close()
            self._server = None

    def _on_connection(self):
        while self._server is not None and self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            cid = id(sock)
            self._sockets[cid] = [sock, b""]
            sock.readyRead.connect(lambda c=cid: self._on_read(c))
            sock.disconnected.connect(lambda c=cid: self._on_gone(c))

    def _on_read(self, cid):
        entry = self._sockets.get(cid)
        if entry is None:
            return
        sock, buf = entry
        buf += bytes(sock.readAll())
        *lines, buf = buf.split(b"\n")
        if len(buf) > MAX_LINE:
            log.warning("VS-Code-Erweiterung: zu lange Nachricht, Verbindung getrennt")
            sock.abort()
            return
        entry[1] = buf
        for line in lines:
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict):
                self.handle(cid, msg)

    def _on_gone(self, cid):
        entry = self._sockets.pop(cid, None)
        if entry:
            entry[0].deleteLater()
        self.drop_client(cid)
        log.info("VS-Code-Erweiterung getrennt")
