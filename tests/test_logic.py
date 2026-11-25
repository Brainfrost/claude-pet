"""Wachstum, Haiku-Antworten, Maskierung und Mustererkennung."""
from claude_pet import growth
from claude_pet.reactions import ATTENTION, CODE_LINE, ERROR, SUCCESS
from claude_pet.speech import _parse, is_content, mask


# ------------------------------------------------------------ Wachstum
def prof():
    return growth.ensure_defaults({"personality": "aengstlich", "stage": "baby"})


def test_growth_by_active_minutes_with_daily_cap():
    p = prof()
    # ein Automatisierungs-Tag mit 14 Stunden Aktivität zählt höchstens 8 Stunden
    assert growth.apply_stats(p, {"minutes": {"2026-11-24": 14 * 60}}) == []
    assert p["xp"] == 8 * 60 and p["stage"] == "baby"
    ms = growth.apply_stats(p, {"minutes": {"2026-11-25": 6 * 60, "2026-11-26": 6 * 60}})
    assert p["xp"] == 20 * 60 and ("stage", "jung") in ms and ("trick", "doppelsprung") in ms
    ms = []
    for i in range(14):
        ms += growth.apply_stats(p, {"minutes": {f"2026-12-{i + 1:02d}": 8 * 60}})
    assert p["stage"] == "erwachsen" and ("trick", "weitsprung") in ms


def test_accessories_need_weeks_of_work():
    p = prof()
    assert growth.apply_stats(p, {"cats": {"bash": 300, "web": 65, "read": 40, "search": 15}}) == []
    ms = growth.apply_stats(p, {"cats": {"bash": 2700, "read": 600, "search": 200}})
    assert ("accessory", "helm") in ms and ("accessory", "lupe") in ms and "brille" not in p["accessories"]
    assert growth.accessory_progress(p, "brille") == (65, 600)


def test_bond_grows_slowly_with_daily_cap_and_mood_is_clamped():
    p = prof()
    for _ in range(200):
        growth.interact(p, "stroke", today="2026-11-25")
    assert abs(p["bond"] - (10 + growth.BOND_DAY_CAP)) < 1e-9 and p["mood"] == 100
    growth.interact(p, "stroke", today="2026-11-26")
    assert p["bond"] > 10 + growth.BOND_DAY_CAP, "neuer Tag, neue Bindung"
    for _ in range(100):
        growth.interact(p, "thrown")                 # ängstlich mag das gar nicht – senkt ohne Grenze
    assert p["bond"] == 0 and p["mood"] == 0


def test_hidden_accessory_is_not_worn():
    p = prof()
    p["accessories"], p["accessories_off"] = ["helm", "lupe"], ["helm"]
    assert growth.worn(p) == ["lupe"]


# ------------------------------------------------------------ Haiku-Antworten
def test_parse_json_and_fallbacks():
    assert _parse('Klar! {"sagen": "Blubb!", "aktion": "hinlaufen", "ziel": "Migration"}') == \
        ("Blubb!", "hinlaufen", "Migration")
    assert _parse('{"sagen": "x", "aktion": "fliegen"}') == ("x", "nichts", "")   # unbekannte Aktion
    assert _parse("nur ein Satz") == ("nur ein Satz", "nichts", "")
    assert _parse("") == ("", "nichts", "")


def test_mask_secrets():
    s = mask("Authorization=Bearer abcDEF123456789 token: geheim sk-ant-api03-AAAAbbbbCCCC "
             "mail max.muster@firma.at key AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    for secret in ("abcDEF123456789", "geheim", "sk-ant-api03", "max.muster@firma.at", "A" * 36):
        assert secret not in s


def test_is_content_skips_claude_code_chrome():
    assert is_content("● Ich baue jetzt die Migration")
    for chrome in ("────────────", "  ⏵⏵ auto mode on (shift+tab to cycle)", "❯ ", "x"):
        assert not is_content(chrome)


# ------------------------------------------------------------ Muster im Terminal-Text
def kind(line):
    if CODE_LINE.match(line):
        return "code"
    for name, rx in (("attention", ATTENTION), ("error", ERROR), ("success", SUCCESS)):
        if rx.search(line):
            return name
    return None


def test_patterns():
    assert kind("  ⎿  Error: file not found") == "error"
    assert kind("Traceback (most recent call last):") == "error"
    assert kind("ValueError: bad thing") == "error"
    assert kind("Exit code 1") == "error"
    assert kind("  73 +     except Exception:") == "code"
    assert kind("===== 12 passed in 0.3s =====") == "success"
    assert kind("● Die Tests sind erfolgreich durchgelaufen") == "success"
    assert kind(" Do you want to proceed?") == "attention"
    assert kind(" ❯ 1. Yes") == "attention"
    assert kind("● Der Fehler liegt im Thread") is None
    assert kind("log.exception('x')") is None


# ------------------------------------------------------------ Vollbild-Erkennung (Ruhemodus)
def test_fullscreen_detection_ignores_maximized_and_own_windows():
    import os
    from claude_pet import quiet
    mon = (0, 0, 1920, 1080)
    assert quiet.foreground_fullscreen((123, "Chrome_WidgetWin_1", (0, 0, 1920, 1080), mon))      # F11/Video
    assert not quiet.foreground_fullscreen((123, "Chrome_WidgetWin_1", (0, 0, 1920, 1040), mon))  # maximiert
    assert not quiet.foreground_fullscreen((os.getpid(), "Qt", (0, 0, 1920, 1080), mon))         # eigenes Overlay
    assert not quiet.foreground_fullscreen((123, "Progman", (0, 0, 1920, 1080), mon))             # Desktop


# ------------------------------------------------------------ Adoption und Steckbrief
def test_adoption_pool_limits_rolls_and_varies():
    import random
    from claude_pet.adoption import AdoptionPool
    pool = AdoptionPool(random.Random(1))
    picks = [pool.roll() for _ in range(5)]
    assert all(picks) and pool.roll() is None and pool.left == 0
    assert len({c for c, _ in picks}) == 5, "fünf verschiedene Figuren"
    pool.select(1)
    assert pool.current == picks[1]


def test_profile_adopt_and_archive(tmp_path, monkeypatch):
    from claude_pet import profile
    monkeypatch.setattr(profile, "DIR", str(tmp_path))
    monkeypatch.setattr(profile, "PATH", str(tmp_path / "profile.json"))
    monkeypatch.setattr(profile, "ARCHIVE", str(tmp_path / "archiv"))
    assert profile.load() is None, "ohne Adoption gibt es kein Pet (kein automatisches Würfeln mehr)"
    p = profile.adopt("spatz", "neugierig", "  Krümel ")
    assert p["name"] == "Krümel" and profile.load()["creature"] == "spatz"
    target = profile.archive()
    assert profile.load() is None and (tmp_path / "archiv").exists() and target.endswith("Krümel.json")
