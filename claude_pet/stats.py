"""Zählt lokal, wie viel du mit Claude Code arbeitest – aus den Transcripts unter ~/.claude/projects.

Liest nur neu angehängte Zeilen (Byte-Offsets pro Datei) und nur Einträge seit der Geburt des Pets.
Nichts davon verlässt den Rechner.
"""
import glob
import json
import logging
import os
import time
from datetime import datetime, timedelta

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
                if d["tools"] or d["prompts"] or d["sessions"] or d["minutes"]:
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
            s.setdefault("minutes", [])
            return s
        except (OSError, ValueError):
            return {"offsets": {}, "sessions": [], "minutes": []}

    def _save(self, state):
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        state["sessions"] = state["sessions"][-500:]
        # schon gezählte aktive Minuten: nur die letzten zwei Tage aufheben
        keep = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        state["minutes"] = sorted(m for m in state.get("minutes", []) if m >= keep)
        tmp = STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, STATE)

    def _scan(self, state):
        d = {"cats": {}, "tools": 0, "prompts": 0, "sessions": 0, "minutes": {}}
        offsets = state["offsets"]
        known_sessions = set(state["sessions"])
        self._seen_min = set(state.setdefault("minutes", []))
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
            sub = os.sep + "subagents" + os.sep in path
            for raw in chunk[:end].split(b"\n"):
                self._line(raw, d, known_sessions, state, sub)
        state["minutes"] = sorted(self._seen_min)
        return d

    def _line(self, raw, d, known_sessions, state, sub=False):
        if b'tool_use' not in raw and b'"user"' not in raw:
            return
        try:
            e = json.loads(raw)
        except ValueError:
            return
        ts = e.get("timestamp")
        if ts:
            try:
                t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                t = None
            if t is not None:
                if t.timestamp() < self.born:
                    return
                # aktive Minute (Ortszeit), jede nur einmal – auch wenn Subagents parallel laufen
                key = t.astimezone().strftime("%Y-%m-%dT%H:%M")
                if key not in self._seen_min:
                    self._seen_min.add(key)
                    day = key[:10]
                    d["minutes"][day] = d["minutes"].get(day, 0) + 1
        if sub:
            return          # Subagents: nur die aktive Zeit zählt, nicht ihre vielen Tool-Aufrufe
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
