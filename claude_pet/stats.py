"""Zählt lokal, wie viel du mit Claude Code arbeitest – aus den Transcripts unter ~/.claude/projects.

Liest nur neu angehängte Zeilen (Byte-Offsets pro Datei) und nur Einträge seit der Geburt des Pets.
Nichts davon verlässt den Rechner.
"""
import glob
import json
import logging
import os
import time
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)

PROJECTS = os.path.join(os.path.expanduser("~"), ".claude", "projects")
STATE = os.path.join(os.environ.get("LOCALAPPDATA", "."), "claude-pet", "stats_state.json")
SCAN_EVERY = 45  # Sekunden

CATEGORY = {
    "Bash": "bash", "PowerShell": "bash",
    "WebSearch": "web", "WebFetch": "web",
    "Grep": "search", "Glob": "search",
    "Read": "read",
    "Edit": "edit", "Write": "edit", "NotebookEdit": "edit",
    "Agent": "agent", "Task": "agent",
}


def category(tool):
    if tool in CATEGORY:
        return CATEGORY[tool]
    if tool.startswith("mcp__claude-in-chrome__") or "browser" in tool.lower():
        return "web"
    return "other"


class StatsWatcher(QThread):
    delta = pyqtSignal(object)   # {"cats": {...}, "tools": n, "prompts": n, "sessions": n}

    def __init__(self, born_iso):
        super().__init__()
        self._stop = False
        try:
            self.born = datetime.fromisoformat(born_iso).timestamp()
        except (TypeError, ValueError):
            self.born = time.time()

    def stop(self):
        self._stop = True

    def reset(self, born_iso):
        """Neues Pet: Offsets bleiben (alte Arbeit zählt nicht), nur der Startzeitpunkt ändert sich."""
        try:
            self.born = datetime.fromisoformat(born_iso).timestamp()
        except (TypeError, ValueError):
            self.born = time.time()

    def run(self):
        state = self._load()
        while not self._stop:
            try:
                d = self._scan(state)
                if d["tools"] or d["prompts"] or d["sessions"]:
                    self.delta.emit(d)
                self._save(state)
            except Exception:
                log.exception("Stats-Scan fehlgeschlagen")
            for _ in range(SCAN_EVERY * 10):
                if self._stop:
                    return
                self.msleep(100)

    # ------------------------------------------------------------ intern
    def _load(self):
        try:
            with open(STATE, encoding="utf-8") as f:
                s = json.load(f)
            s.setdefault("offsets", {})
            s.setdefault("sessions", [])
            return s
        except (OSError, ValueError):
            return {"offsets": {}, "sessions": []}

    def _save(self, state):
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        state["sessions"] = state["sessions"][-500:]
        tmp = STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, STATE)

    def _scan(self, state):
        d = {"cats": {}, "tools": 0, "prompts": 0, "sessions": 0}
        offsets = state["offsets"]
        known_sessions = set(state["sessions"])
        files = glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")) + \
            glob.glob(os.path.join(PROJECTS, "*", "*", "subagents", "*.jsonl"))
        for path in files:
            try:
                st = os.stat(path)
            except OSError:
                continue
            if st.st_mtime < self.born:
                offsets.setdefault(path, st.st_size)
                continue
            off = offsets.get(path, 0)
            if off > st.st_size:
                off = 0
            if off == st.st_size:
                continue
            with open(path, "rb") as f:
                f.seek(off)
                chunk = f.read()
            end = chunk.rfind(b"\n")
            if end < 0:
                continue
            offsets[path] = off + end + 1
            for raw in chunk[:end].split(b"\n"):
                self._line(raw, d, known_sessions, state)
        return d

    def _line(self, raw, d, known_sessions, state):
        if b'"tool_use"' not in raw and b'"type":"user"' not in raw:
            return
        try:
            e = json.loads(raw)
        except ValueError:
            return
        ts = e.get("timestamp")
        if ts:
            try:
                if datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() < self.born:
                    return
            except ValueError:
                pass
        sid = e.get("sessionId")
        if sid and sid not in known_sessions:
            known_sessions.add(sid)
            state["sessions"].append(sid)
            d["sessions"] += 1
        msg = e.get("message") or {}
        content = msg.get("content")
        if e.get("type") == "assistant" and isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    cat = category(str(c.get("name", "")))
                    d["cats"][cat] = d["cats"].get(cat, 0) + 1
                    d["tools"] += 1
        elif e.get("type") == "user" and not e.get("isMeta"):
            if isinstance(content, str) and content.strip() and not content.startswith("<"):
                d["prompts"] += 1
            elif isinstance(content, list) and any(
                    isinstance(c, dict) and c.get("type") == "text" for c in content) and not any(
                    isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
                d["prompts"] += 1
