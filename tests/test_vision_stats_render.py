"""Bildanalyse auf künstlichen Bildern, Transcript-Zählung auf Testdateien, Rendern aller Figuren."""
import json
from datetime import datetime, timedelta, timezone

import numpy as np

from claude_pet import creatures, stats, vision


# ------------------------------------------------------------ Bildanalyse
def test_detects_line_and_text_top_but_not_noise():
    img = np.full((300, 600), 230, dtype=np.int16)
    img[50, 20:400] = 30                                   # Trennlinie
    rng = np.random.default_rng(1)
    for x in range(100, 400, 9):                           # "Textzeile": Buchstaben 7 px breit
        img[120:132, x:x + 7] = 40
        img[120, x + 1:x + 6] = 230                        # runde Oberkanten
    img[200:260, 300:560] = rng.integers(0, 255, (60, 260))   # Foto/Rauschen
    runs = vision.detect(img)
    ys = sorted(y for y, a, b in runs)
    assert any(abs(y - 50) <= 1 for y in ys), ys
    assert any(118 <= y <= 122 for y in ys), ys           # an der Oberkante der Schrift
    # Ober- und Unterkante des Fotos sind echte Kanten (die untere darf beim Hochziehen etwas
    # hineinrutschen), aber im Inneren des Fotos darf keine Ebene entstehen
    assert not any(206 <= y <= 240 for y, a, b in runs if a >= 300), "Rauschen ignorieren"


def test_exclusion_area_is_ignored():
    img = np.full((200, 400), 230, dtype=np.int16)
    img[100, 10:390] = 20
    assert vision.detect(img)
    assert not vision.detect(img, exclude=[(0, 90, 400, 110)])


# ------------------------------------------------------------ Transcript-Zählung
def test_stats_counts_only_new_work_since_birth(tmp_path, monkeypatch):
    proj = tmp_path / "projects" / "proj"
    proj.mkdir(parents=True)
    monkeypatch.setattr(stats, "PROJECTS", str(tmp_path / "projects"))
    born = datetime.now(timezone.utc) - timedelta(hours=1)
    old, new = (born - timedelta(hours=2)).isoformat(), (born + timedelta(minutes=5)).isoformat()

    def entry(ts, typ, content, sid="s1"):
        return json.dumps({"type": typ, "timestamp": ts, "sessionId": sid, "message": {"content": content}})

    lines = [
        entry(old, "assistant", [{"type": "tool_use", "name": "Bash"}]),          # vor der Geburt
        entry(new, "user", "Bitte baue X"),
        entry(new, "assistant", [{"type": "tool_use", "name": "Bash"}, {"type": "tool_use", "name": "Grep"}]),
        entry(new, "user", [{"type": "tool_result", "content": "ok"}]),            # kein Prompt
        entry(new, "assistant", [{"type": "tool_use", "name": "WebSearch"}], sid="s2"),
    ]
    f = proj / "a.jsonl"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    w = stats.StatsWatcher(born.isoformat())
    state = {"offsets": {}, "sessions": []}
    d = w._scan(state)
    assert d["tools"] == 3 and d["prompts"] == 1 and d["sessions"] == 2
    assert d["cats"] == {"bash": 1, "search": 1, "web": 1}
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(entry(new, "assistant", [{"type": "tool_use", "name": "Edit"}]) + "\n")
    d2 = w._scan(state)
    assert d2["tools"] == 1 and d2["cats"] == {"edit": 1}, "nur neu angehängte Zeilen"


# ------------------------------------------------------------ Rendern
def test_all_creatures_render_in_all_states(qapp):
    r = creatures.Renderer()
    for c in creatures.data()["creatures"]:
        for state in ("idle", "walk", "sit", "sleep", "happy", "held", "fall", "jump"):
            for stage in ("baby", "jung", "erwachsen"):
                img = r.render(c, variant="aengstlich", state=state, t=0.9, walk_i=1, blinking=False,
                               facing=-1, px=3, stage=stage, accessories=("helm", "brille", "lupe"))
                assert img.width() > 0
                assert any(img.pixelColor(x, y).alpha() > 0
                           for x in range(0, img.width(), 3) for y in range(0, img.height(), 3)), \
                    (c["id"], state, stage)


def test_stats_counts_active_minutes_once_and_subagents_only_as_time(tmp_path, monkeypatch):
    proj = tmp_path / "projects" / "p"
    (proj / "sess" / "subagents").mkdir(parents=True)
    monkeypatch.setattr(stats, "PROJECTS", str(tmp_path / "projects"))
    born = datetime.now(timezone.utc) - timedelta(hours=1)
    t1 = (born + timedelta(minutes=10)).replace(second=5)
    t2 = t1 + timedelta(seconds=30)                  # gleiche Minute
    t3 = t1 + timedelta(minutes=2)

    def entry(ts, sid="s1"):
        return json.dumps({"type": "assistant", "timestamp": ts.isoformat(), "sessionId": sid,
                           "message": {"content": [{"type": "tool_use", "name": "Bash"}]}})
    (proj / "a.jsonl").write_text(entry(t1) + "\n" + entry(t2) + "\n", encoding="utf-8")
    sub = "\n".join(entry(t1 + timedelta(seconds=i)) for i in range(20)) + "\n" + entry(t3) + "\n"
    (proj / "sess" / "subagents" / "x.jsonl").write_text(sub, encoding="utf-8")
    w = stats.StatsWatcher(born.isoformat())
    d = w._scan({"offsets": {}, "sessions": [], "minutes": []})
    assert sum(d["minutes"].values()) == 2, "zwei verschiedene aktive Minuten"
    assert d["tools"] == 2 and d["cats"] == {"bash": 2}, "Subagents zählen nicht als eigene Arbeit"
