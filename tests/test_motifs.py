"""Motiv-Wächter: Wiederholungen in Sprüchen erkennen und gezielt ersetzen."""
from collections import deque
from types import SimpleNamespace as NS

from claude_pet import motifs
from claude_pet.speech import Speech

# so sah Günthers Satz aus (verspielt, alte Stimme „siehst überall einen Wettlauf“)
GUENTHER = {
    "stroke": ["Hihi, mein Saum wackelt schon vor Freude.", "Mehr davon, bitte!"],
    "thrown": ["Wheeee, ich fliege! Wetten, ich lande zuerst?", "Ich segle durchs Terminal!"],
    "cling": ["Ich hänge am Cursor!", "Wetten, du schaffst es nicht, mich abzuschütteln?"],
    "fetch": ["Ball zurück! Diesmal bin ich schneller, versprochen!", "Gefunden! Ich wedle stolz mit meinem Saum."],
    "morning": ["Morgen! Mein Saum ist noch verschlafen.", "Guten Morgen! Wetten, ich bin vor dir wach?"],
    "break": ["Pause seit {hours}? Wetten, der Cursor wartet schon auf dich?"],
    "welcome": ["Du bist zurück! Ich habe nicht gezittert, ehrlich."],
    "commit": ["Gespeichert! Ich klatsche lautlos mit meinem Saum."],
    "push": ["Hochgeladen! Mein Saum fliegt gleich davon."],
}


def test_fester_satz_betroffene_sprueche():
    items, avoid = motifs.offenders(GUENTHER, "verspielt")
    texts = [t for _, _, t in items]
    assert all("Wetten" in t or "schneller" in t or "Saum" in t for t in texts)
    assert sum("Wetten" in t or "schneller" in t for t in texts) == 5       # alle Renn-Sprüche
    saum_kept = sum("Saum" in t for v in GUENTHER.values() for t in v) - sum("Saum" in t for t in texts)
    assert saum_kept == motifs.SET_KEEP                                       # der Saum bleibt in zweien
    assert "Wetten" in avoid and "Saum" in avoid
    assert not any("zurück" in w.lower() for w in avoid)                      # gehört zum Anlass, kein Tick
    assert not any(w.lower() == "ich" for w in avoid)                         # Ich-Form ist gewollt


def test_unauffaelliger_satz_bleibt():
    calm = {"poke": ["Hey!"], "stroke": ["Schön."], "thrown": ["Uiii!"], "fetch": ["Da ist er."]}
    assert motifs.offenders(calm, "neugierig") == ([], [])


def test_neuer_spruch_wird_geprueft():
    avoid = ["Wetten", "Saum", "schneller"]
    old = "Pause seit {hours}? Wetten, der Cursor wartet schon auf dich?"
    assert motifs.accept_rewrite(old, "Seit {hours} am Stück? Zeit für eine Kekspause!", avoid)
    assert motifs.accept_rewrite(old, "Zeit für eine Kekspause!", avoid) is None           # Platzhalter fehlt
    assert motifs.accept_rewrite(old, "Wetten, {hours} sind genug?", avoid) is None        # gemiedenes Wort
    assert motifs.accept_rewrite(old, "Mein Saum sagt: {hours} reichen!", avoid) is None
    assert motifs.accept_rewrite(old, "x" * 95 + "{hours}", avoid) is None                 # zu lang


def test_live_hinweis():
    recent = ["Mein Saum zittert!", "Ich wackle mit dem Saum.", "Grün! Mein Saum tanzt.",
              "Huch, ein Fehler.", "Huch, schon wieder.", "Huch! Ein Hook ist gestolpert.",
              "Ein Hook hakt.", "Noch ein Hook?"]
    hint = motifs.avoid_hint(recent)
    assert "Saum" in hint and "Huch" in hint and "Hook" in hint
    # Worum es gerade geht, darf vorkommen (ein weiterer Hook-Fehler)
    fake = NS(motif_hist=deque(recent))
    on_topic = Speech.avoid_hint(fake, "PostToolUse:Edit hook failed")
    assert "Hook" not in on_topic and "Saum" in on_topic
