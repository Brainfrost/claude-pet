"""Wachstum, Haiku-Antworten, Maskierung und Mustererkennung."""
from claude_pet import growth
from claude_pet.reactions import ATTENTION, CODE_LINE, ERROR, SUCCESS
from claude_pet.speech import _parse, is_content, mask


# ------------------------------------------------------------ Wachstum
def prof():
    return growth.ensure_defaults({"personality": "aengstlich", "stage": "baby"})


def test_stage_and_accessories():
    p = prof()
    ms = growth.apply_stats(p, {"tools": 450, "prompts": 0, "sessions": 0, "cats": {"bash": 160}})
    assert ("stage", "jung") in ms and ("accessory", "helm") in ms and ("trick", "doppelsprung") in ms
    assert p["stage"] == "jung" and growth.worn(p) == ["helm"]
    ms = growth.apply_stats(p, {"tools": 0, "prompts": 0, "sessions": 300, "cats": {}})
    assert ("stage", "erwachsen") in ms and "weitsprung" in p["tricks"]


def test_bond_and_mood_are_clamped_and_personality_specific():
    p = prof()
    for _ in range(100):
        growth.interact(p, "thrown")                 # ängstlich mag das gar nicht
    assert p["bond"] == 0 and p["mood"] == 0
    for _ in range(100):
        growth.interact(p, "stroke")
    assert p["bond"] == 100 and p["mood"] == 100 and "purzelbaum" in p["tricks"]


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
