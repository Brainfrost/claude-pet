"""Erkennt, was in den Sessions passiert, und lässt das Pet (und seine Sprechblase) reagieren.

Quellen:
  - Tab-Titel: Wechsel zwischen 'working' (Spinner) und 'idle' (✳) -> start / done
  - neu erscheinender Text im sichtbaren Pane -> error / success / attention
"""
import logging
import re
import time
from collections import deque

from .brain import FOOD, tab_key
from .speech import content_rows, digest, is_content

log = logging.getLogger(__name__)

# Zeilen aus Code-Listings/Diffs ("  73 +   except Exception:") nicht als Meldung werten
CODE_LINE = re.compile(r"^\s*\d+\s*[+\-]?\s")
ERROR = re.compile(
    r"(^\s*(⎿\s*)?(error|fatal|fehler)\b"
    r"|\b\w*(error|exception):\s"
    r"|traceback \(most recent call last\)"
    r"|\bfailed\b|\bFAILED\b|fehlgeschlagen"
    r"|exit code [1-9]"
    r"|[✗✘❌])", re.I)
SUCCESS = re.compile(
    r"([✓✔✅]|\b\d+ passed\b|\ball tests pass|\bsuccessfully\b|\berfolgreich\b|\bbuild succeeded\b)", re.I)
ATTENTION = re.compile(
    r"(do you want to|möchtest du|❯\s*1\.\s*yes|enter to select|esc to cancel|\(y/n\))", re.I)

# git: der Befehl (wie Claude Code ihn anzeigt) oder die Ausgabe von commit/push
_CMD = r"(?:(?:Bash|PowerShell)\([^\n]*|^\s*[$>]\s*)\bgit\b[^\n]*"
GIT_COMMIT = re.compile(_CMD + r"\bcommit\b|\[[\w./-]+(?: \(root-commit\))? [0-9a-f]{7,}\] ")
GIT_PUSH = re.compile(_CMD + r"\bpush\b|\b[0-9a-f]{7,}\.\.[0-9a-f]{7,}\s+\S+\s+->\s+\S+|\* \[new branch\]")

COOLDOWN = {"error": 25, "success": 25, "attention": 40, "done": 15, "start": 20, "commit": 30, "push": 30}

NL = chr(10)
CONTENT_CHARS = 350    # so viel neuer Text, bevor das Pet den Inhalt kommentiert
BUFFER_LINES = 60


class Reactions:
    def __init__(self, ctl):
        self.ctl = ctl
        self.seen = set()
        self.seen_order = deque()
        self.tab_states = {}
        self.working_since = {}         # Tab -> seit wann Claude dort arbeitet
        self.last = {}
        self.primed = False
        self.buffer = deque(maxlen=BUFFER_LINES)   # neu erschienener Inhalt seit dem letzten Kommentar

    def _remember(self, line):
        if line in self.seen:
            return
        self.seen.add(line)
        self.seen_order.append(line)
        while len(self.seen_order) > 800:
            self.seen.discard(self.seen_order.popleft())

    def on_world(self, world):
        if not world.ok:
            return
        pet, brain = self.ctl.pet, self.ctl.brain
        snap = world.snap
        events = []

        # --- Session-Zustand aus den Tab-Titeln
        home_key = brain.home[0] if brain.home else None
        states = {}
        for t in snap.tabs:
            k = tab_key(t)
            states[k] = t.state
            prev = self.tab_states.get(k)
            relevant = k == home_key or t.selected
            if t.state == "working" and prev != "working":
                self.working_since[k] = time.time()
            if prev == "working" and t.state == "idle":
                # Bote: lange Arbeit fertig, und du schaust gerade nicht hin
                worked = time.time() - self.working_since.pop(k, time.time())
                if worked >= 20 and (not t.selected or not self.ctl.terminal_focused()):
                    self.ctl.messenger(k)
            if prev and prev != t.state and relevant:
                if prev == "working" and t.state == "idle":
                    events.append(("done", ""))
                elif prev == "idle" and t.state == "working":
                    events.append(("start", ""))
        self.tab_states = states

        # --- neuer Text im Pane, in dem das Pet ist
        pi = pet.pane if pet.pane is not None else 0
        if pi < len(snap.panes):
            rows = [t.rstrip() for _, t in snap.panes[pi].lines]
            shift = world.shifts[pi] if pi < len(world.shifts) else None
            new = [r for r in rows if r.strip() and r not in self.seen]
            for r in rows:
                self._remember(r)
            if shift is None:
                self.buffer.clear()                 # Tab gewechselt / Bildschirm neu
            if self.primed and shift is not None:
                visible = set(content_rows(rows))     # ohne Eingabefeld (was du gerade tippst)
                for line in new:
                    typed = line not in visible
                    if not typed:
                        if is_content(line):
                            self.buffer.append(line.rstrip())
                            brain.news = True
                        if FOOD.search(line):
                            brain.food_urge = True    # neues Futter: bald hingehen
                        if GIT_PUSH.search(line):
                            events.append(("push", line.strip()))
                        elif GIT_COMMIT.search(line):
                            events.append(("commit", line.strip()))
                    if CODE_LINE.match(line):
                        continue
                    s = line.strip()
                    if ATTENTION.search(s):
                        events.append(("attention", s))
                    elif ERROR.search(s):
                        events.append(("error", s))
                    elif SUCCESS.search(s):
                        events.append(("success", s))
        self.primed = True

        visible = pet.state != "hidden" and pet.pane is not None
        if not visible:
            return
        speech = self.ctl.speech
        done_kinds = set()
        for kind, detail in events:
            if kind in done_kinds:
                continue
            now = time.time()
            if now - self.last.get(kind, 0) < COOLDOWN.get(kind, 20):
                continue
            self.last[kind] = now
            done_kinds.add(kind)
            log.info("Ereignis %s: %s", kind, detail[:80])
            if kind in ("commit", "push"):
                pet.celebrate()
                self.ctl.interact("success")
                if not speech.on_event(kind, world, pi, detail):
                    speech.canned(kind, force=True)
                continue
            pet.react(kind)
            self.ctl.interact(kind)
            new_text = NL.join(self.buffer) if kind == "done" else ""
            if speech.on_event(kind, world, pi, detail, new_text=new_text) and new_text:
                self.buffer.clear()
        # --- laufend mitlesen: genug neuer Inhalt beisammen -> kommentieren
        chars = len(digest(self.buffer)) if len(self.buffer) >= 3 else 0
        if chars >= CONTENT_CHARS and speech.can_comment():
            text = NL.join(self.buffer)
            self.buffer.clear()
            if speech.on_event("content", world, pi, new_text=text):
                log.info("Inhalt kommentieren (%d Zeichen)", chars)
