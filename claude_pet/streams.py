"""Empfängt die Terminal-Ausgabe von der Begleit-Erweiterung in VS Code/Cursor.

Die Erweiterung (Ordner vscode-extension/) verbindet sich mit einem lokalen Kanal – Named Pipe unter
Windows, Unix-Socket auf dem Mac – und schickt zeilenweise JSON:

    {"type": "hello", "app": "Visual Studio Code", "workspace": "projekt", "version": 1}
    {"type": "start", "term": "t1", "cmd": "claude", "dims": {"columns": 177, "rows": 39}, "title": "…"}
    {"type": "data",  "term": "t1", "d": "<Rohdaten mit Escape-Sequenzen>"}
    {"type": "end",   "term": "t1"}
    {"type": "active", "term": "t1"}          # aktives Terminal des Fensters (oder null)
    {"type": "closed", "term": "t1"}          # Terminal geschlossen

Nichts davon wird gespeichert.

Sicherheit: Der Kanalname wird bei jedem Start zufällig gewählt und nur im privaten Datenordner
abgelegt (Datei `channel`, dort liest ihn die Erweiterung). Ein anderer Benutzer desselben Rechners kann
ihn daher weder erraten noch vorher selbst belegen und so die Ausgabe abgreifen. Auf dem Mac liegt der
Socket selbst im privaten Datenordner. Zusätzlich lässt Qt nur den eigenen Benutzer zu.
"""
import getpass
import json
import logging
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field

from .emulator import TermEmulator
from .paths import data_dir

log = logging.getLogger(__name__)

MAX_LINE = 4 * 1024 * 1024        # Schutz gegen kaputte Gegenstellen
MAX_SESSIONS = 64                 # Terminals je Verbindung (Schutz gegen Speicherfresser)
_SAFE = re.compile(r"[^A-Za-z0-9_.-]")
_CHANNEL = None


def channel_name():
    """Name des Kanals dieses Pet-Laufs (zufällig; Windows: Pipe-Name, Mac: Socket-Pfad)."""
    global _CHANNEL
    if _CHANNEL is None:
        token = secrets.token_hex(8)
        if os.name == "nt":
            user = _SAFE.sub("_", getpass.getuser() or "user")
            _CHANNEL = f"claude-pet-{user}-{token}"          # -> \\.\pipe\claude-pet-<user>-<zufall>
        else:
            _CHANNEL = data_dir(f"ch-{token}.sock")           # privater Datenordner
    return _CHANNEL


def channel_file():
    """Hier steht der volle Kanalname für die Erweiterung."""
    return data_dir("channel")


def published_channel():
    """Den von einem laufenden Pet veröffentlichten Kanal lesen (Diagnose), oder None."""
    try:
        with open(channel_file(), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


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
            if sum(1 for k in self.sessions if k[0] == cid) >= MAX_SESSIONS:
                raise ValueError("zu viele Terminals auf einer Verbindung")
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
        self._published = srv.fullServerName()
        try:                                          # für die Erweiterung veröffentlichen (privater Ordner)
            os.makedirs(data_dir(), exist_ok=True)
            tmp = channel_file() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(self._published)
            if os.name != "nt":
                os.chmod(tmp, 0o600)
            os.replace(tmp, channel_file())
        except OSError:
            log.exception("Kanal konnte nicht veröffentlicht werden")
        log.info("Kanal für VS Code/Cursor geöffnet")
        return True

    def stop(self):
        if self._server is not None:
            self._server.close()
            self._server = None
            if published_channel() == getattr(self, "_published", None):
                try:
                    os.remove(channel_file())
                except OSError:
                    pass

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
            if not isinstance(msg, dict):
                continue
            try:
                self.handle(cid, msg)
            except Exception as e:                    # eine kaputte Nachricht darf das Pet nicht beenden
                log.warning("VS-Code-Erweiterung: Nachricht verworfen (%s)", e)

    def _on_gone(self, cid):
        entry = self._sockets.pop(cid, None)
        if entry:
            entry[0].deleteLater()
        self.drop_client(cid)
        log.info("VS-Code-Erweiterung getrennt")
