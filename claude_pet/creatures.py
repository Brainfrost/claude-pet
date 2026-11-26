"""Rendert die Figuren aus design/pet-data.json nach den dort beschriebenen Regeln.

Gezeichnet wird in doppelter Auflösung („fein“): Das Raster wird per Scale2x/EPX hochgerechnet (rundere
Kanten), Augen bekommen eigene 4×4-Vorlagen (Glanzpunkt, Blickrichtung, Blinzeln in Stufen), und
Körperteile (Schwanz, Arme, Tentakel, Saum …, siehe PARTS) bewegen sich um halbe Rasterpixel.
"""
import colorsys
import json
import math
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QTransform

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "design", "pet-data.json")

STAGE_PX = {"baby": 2, "jung": 3, "erwachsen": 4}
# Wintermütze (an der Helm-Position), nur wenn kein Bauhelm getragen wird
MUETZE = {"map": ["...WW...", "..rrrr..", ".rrrrrr.", "rrrrrrrr", "WWWWWWWW"],
          "colors": {"r": "#d62839", "W": "#ffffff"}}
MARGIN_X = 6     # Rasterpixel links/rechts im Bild (Lupe, Herzchen)
MARGIN_TOP = 8   # Rasterpixel über dem Kopf (Hand, Helm, Effekte)
PAD = 4          # Feinpixel Rand ums feine Raster (links, rechts, oben): Platz für bewegte Teile

# Augen in Feinpixeln (4×4 statt 2×2): . = Lid (Hautfarbe), e = Auge, w = Glanzpunkt, - = Lidstrich
EYES = {
    "normal": [".ee.", "eeee", "eeee", ".ee."],
    "glint":  [".ee.", "ewee", "eeee", ".ee."],
    "half":   ["....", "----", "eeee", ".ee."],
    "small":  ["....", ".ee.", ".ee.", "...."],
    "closed": ["....", "....", "----", "...."],
    "happy":  ["....", ".--.", "-..-", "...."],
    "wide":   [".ee.", "eeee", "ewee", "eeee", ".ee."],   # erschrocken: höher (ragt 1 Feinpixel nach oben)
    "dizzy":  ["-..-", ".--.", ".--.", "-..-"],     # schwindelig: X-Augen
    "sparkle": [".ee.", "ewee", "eeew", ".ee."],    # funkelnd (Ball!): zwei Glanzpunkte
}
_EYE_KEYS = {".": "lid", "e": "e", "w": "w", "-": "shut"}
LOOK_MODES = {"normal", "glint", "small", "half", "wide", "sparkle"}
RIM = (255, 255, 255, 64)   # heller Umriss: hebt dunkle Figuren vom dunklen Terminal ab

# Mund je Figur: box = vorhandener Mund (Rasterpixel, Steh-Frame); hidden = im Ruhezustand unsichtbar
# (Katze); beak = Zeile, ab der der Unterschnabel beim Öffnen nach unten klappt; tongue = Zunge zeigen.
MOUTHS = {
    "katze": {"box": (15, 8, 15, 8), "hidden": True},
    "schleim": {"box": (7, 10, 8, 10)},
    "krake": {"box": (7, 9, 8, 9)},
    "bit": {"box": (7, 8, 8, 8), "tongue": False},
    "spatz": {"box": (7, 7, 8, 8), "beak": 8},
    "pilz": {"box": (7, 10, 8, 10)},
    "axolotl": {"box": (9, 7, 10, 7)},
    "klammer": {"box": (8, 8, 9, 8), "tongue": False},
    "tasse": {"box": (6, 8, 7, 8)},
    "ente": {"box": (17, 6, 19, 7), "beak": 7},
    "toast": {"box": (7, 9, 8, 9)},
    "kaktus": {"box": (7, 9, 8, 9)},
    "geist": {"box": (7, 7, 8, 8)},
    "saugi": {"box": (9, 7, 10, 7), "tongue": False},
}
# Mundformen in Feinpixeln, ab Oberkante des Mundes mittig: . = Haut, e = dunkel, T = Zunge.
# Je nach Mundgröße: schmal (2 breit), normal (4×2), hoch (4×4, Geist).
MOUTH_SHAPES = {
    "narrow": {"shut": [], "open": ["ee", "ee"], "wide": ["ee", "ee", "ee"], "o": ["ee", "ee"]},
    "normal": {"shut": ["e..e", ".ee."], "open": ["eeee", "eTTe", ".ee."],
               "wide": [".ee.", "eeee", "eeee", "eTTe", ".ee."], "o": [".ee.", "eeee", ".ee."]},
    "tall":   {"shut": ["....", "....", "e..e", ".ee."], "open": [".ee.", "eeee", "eeee", "eTTe", ".ee."],
               "wide": [".ee.", "eeee", "eeee", "eeee", "eTTe", ".ee."], "o": ["....", ".ee.", "eeee", ".ee."]},
}
TONGUE = "#ff7a9a"

# Liegepose zum Schlafen je Figur: rows = eigenes Raster (sonst Sitz-Frame), mouth = Mund darin
# (None = keiner, z.B. Schnabel eingezogen), lean = so weit lehnt es sich im Schlaf zurück (Grad).
_E = "." * 20
SLEEP = {
    "katze": {"rows": [_E] * 8 + [
        ".............o...o..",
        "............opo.opo.",
        "...........oBBBBBBBo",
        "...ooooooooBBeeBeeBo",
        "..oBBBBBBBBBBeeBeeBo",
        ".oBBBLLLLLLBkBBpBBko",
        ".oDDDDDDDBBBBBBBBBo.",
        "..oooooooooooooooo.."], "mouth": (15, 14, 15, 14)},
    "schleim": {"rows": [_E[:16]] * 7 + [
        "......oooo......",
        "...ooBBBBBBoo...",
        "..oBBBBBBBBLLo..",
        ".oBBeeBBBBeeBLo.",
        ".oBBeeBBBBeeBBo.",
        "oBBkBBBDDBBBkBBo",
        ".oooooooooooooo."], "mouth": (7, 12, 8, 12)},
    "krake": {"rows": [_E[:16]] * 8 + [
        ".....oooooo.....",
        "...ooBBBBBBoo...",
        "..oBBBBBBBLLBo..",
        ".oBBeeBBBBeeBBo.",
        ".oBBeeBBBBeeBBo.",
        ".oBkBBBDDBBBkBo.",
        "oBBBBBBBBBBBBBBo",
        ".oBoBoBooBoBoBo."], "mouth": (7, 13, 8, 13)},
    "bit": {"rows": [_E[:16]] * 8 + [
        "..oooooooooooo..",
        ".oBBBBBBBBBBBBo.",
        ".oBSSeeSSSeeSBo.",
        ".oBSSeeSSSeeSBo.",
        ".oBSSSSMMSSSSBo.",
        ".oBBBBBBBBBBBBo.",
        "..oooooooooooo..",
        "....oooooooo...."], "mouth": (7, 12, 8, 12)},
    "spatz": {"rows": [_E[:16]] * 8 + [
        "......oooo......",
        "....ooBBBBoo....",
        "...oBBBBBBBBo...",
        "..oBBeeBBeeBBo..",
        ".oDBBeeBBeeBBDo.",
        ".oDDBBBppBBBDDo.",
        ".oDDBLLLLLLBDDo.",
        "..oooooooooooo.."], "mouth": None},
    "pilz": {"rows": [_E[:16]] * 6 + [
        ".....oooooo.....",
        "...ooBBLLBBoo...",
        "..oBBBBBBBBLLo..",
        ".oBLLBBBBBBBLBo.",
        "oDDDDDDDDDDDDDDo",
        "...oSeeSSeeSo...",
        "...oSeeSSeeSo...",
        "...okSSooSSko...",
        "...oSSSSSSSSo...",
        "....oooooooo...."], "mouth": (7, 13, 8, 13)},
    "axolotl": {"rows": [_E] * 8 + [
        "..pp.oooooooooo.pp..",
        ".pp.oBBBBBBBBBBo.pp.",
        "pp.oBBeeBBBBeeBBo.pp",
        "...oBBeeBBBBeeBBo...",
        "...oBkBBBooBBBkBo...",
        "..oBBBBLLLLLLBBBBoBo",
        "..oooooooooooooooo.."], "mouth": (9, 12, 10, 12)},
    "klammer": {"rows": [_E[:18]] * 8 + [
        "...ooo......ooo...",
        "..oBBo......oBBo..",
        ".oBo..ee..ee..oBo.",
        "oBo...ee..ee...oBo",
        ".oBo..k.MM.k..oBo.",
        "..oBBo......oBBo..",
        "...ooo......ooo...",
        "....oo......oo...."], "mouth": (8, 12, 9, 12)},
    "tasse": {"rows": [_E[:18]] * 5 + [
        ".oooooooooooo.....",
        ".oDDDDDDDDDDo.....",
        ".oBBBBBBBBBBoooo..",
        ".oBBeeBBeeBBo..o..",
        ".oBBeeBBeeBBo..o..",
        ".oBkBBooBBkBo..o..",
        ".oBBBBBBBBBBoooo..",
        ".oLBBBBBBBBBo.....",
        ".oLBBBBBBBBBo.....",
        "..oBBBBBBBBo......",
        "...oooooooo......."], "mouth": (6, 10, 7, 10), "lean": 8},
    "ente": {"rows": [_E] * 8 + [
        "..........oooo......",
        ".oo......oBBBBo.....",
        ".oBooooooBeeBeeBo...",
        ".oBBBBBBBBeeBeeBoppo",
        ".oBBDDDDDBkBBBkBoppo",
        "..oBBBBBBBBBBBBBo...",
        "...ooooooooooooo...."], "mouth": None},
    "toast": {"rows": [_E[:16]] * 5 + [
        "...oooooooooo...",
        "..oDDDDDDDDDDo..",
        ".oDLLLLLLBBBLDo.",
        ".oDDLLLLLLLLDDo.",
        "..oDLLLLLLLLDo..",
        "..oDLeeLLeeLDo..",
        "..oDLeeLLeeLDo..",
        "..oDkLLooLLkDo..",
        "..oDLLLLLLLLDo..",
        "..oDDDDDDDDDDo..",
        "...oooooooooo..."], "mouth": (7, 12, 8, 12), "lean": 10},
    "kaktus": {"mouth": (7, 10, 8, 10), "lean": 6},
    "geist": {"rows": [_E[:16]] * 8 + [
        ".....oooooo.....",
        "...ooBBBBBBoo...",
        "..oBBBBBBBBBBo..",
        ".oBBeeBBBBeeBBo.",
        "oBBBeeBBBBeeBBBo",
        "oBkBBBBooBBBBkBo",
        "oBBoBBBooBBBoBBo",
        ".oo.ooo..ooo.oo."], "mouth": (7, 13, 8, 14)},
    "saugi": {"mouth": (9, 8, 10, 8)},
}
# Licht je Tageszeit: (Farbe, Anteil) – abends warm, nachts kühles Mondlicht
TINTS = {"abend": ("#ffb070", 0.10), "nacht": ("#8fa8ff", 0.10)}

# Bewegte Körperteile je Figur. Koordinaten in Rasterpixeln des Steh-Frames (andere Frames werden
# automatisch ausgerichtet). box = (x0, y0, x1, y1) inklusive; axis = Richtung der Auslenkung;
# grow = wo das Teil am Körper hängt („up“: unten fest, Spitze oben; „down“, „left“, „right“ analog;
# None = alles gleich weit); amp = Auslenkung in Feinpixeln an der Spitze; period in s; k = Wellen-
# versatz je Feinpixel quer zur Achse; every = (alle s, Dauer s) für gelegentliche Zuckungen.
# kind „float“ = ganze Figur schwebt auf und ab, „glow“ = Farbe key pulsiert zwischen colors.
PARTS = {
    "katze": [
        {"box": (0, 1, 2, 8), "axis": "x", "grow": "up", "amp": 2, "period": 1.8, "arm": True},  # Schwanz
        {"box": (12, 1, 19, 2), "axis": "y", "grow": "up", "amp": -1, "period": 0.3,
         "every": (5.5, 0.3)},                                                                # Ohren zucken
    ],
    "schleim": [
        {"box": (1, 2, 14, 13), "axis": "x", "grow": "up", "amp": 1, "period": 1.6, "k": 0.35},  # Glibber
    ],
    "krake": [
        {"box": (1, 12, 14, 15), "axis": "x", "grow": "down", "amp": 2, "period": 1.4, "k": 0.6, "arm": True},  # Tentakel
    ],
    "bit": [],
    "spatz": [
        {"box": (1, 8, 3, 11), "axis": "x", "grow": "down", "amp": -1, "period": 0.18, "every": (4.5, 0.55),
         "arm": True},
        {"box": (12, 8, 14, 11), "axis": "x", "grow": "down", "amp": 1, "period": 0.18, "every": (4.5, 0.55),
         "arm": True},
        {"box": (7, 0, 9, 1), "axis": "x", "grow": "up", "amp": 1, "period": 2.2},           # Federschopf
    ],
    "pilz": [
        {"box": (0, 1, 15, 6), "axis": "x", "grow": "up", "amp": 1, "period": 2.6},          # Hut wiegt
    ],
    "axolotl": [
        {"box": (0, 1, 3, 7), "axis": "y", "grow": "left", "amp": 1, "period": 1.2, "k": 0.5, "arm": True},  # Kiemen
        {"box": (16, 1, 19, 7), "axis": "y", "grow": "right", "amp": 1, "period": 1.2, "k": 0.5,
         "phase": 1.6, "arm": True},
        {"box": (16, 9, 18, 11), "axis": "y", "grow": "right", "amp": -1, "period": 1.6},     # Schwanz
    ],
    "klammer": [
        {"box": (0, 1, 5, 11), "axis": "x", "grow": None, "amp": -1, "period": 2.0},          # atmen
        {"box": (12, 1, 17, 11), "axis": "x", "grow": None, "amp": 1, "period": 2.0},
    ],
    "tasse": [
        {"box": (3, 0, 10, 2), "axis": "x", "grow": "up", "amp": 1, "period": 1.0, "k": 1.2},  # Dampf
    ],
    "ente": [
        {"box": (1, 8, 2, 9), "axis": "y", "grow": "left", "amp": -1, "period": 0.3,
         "every": (3.5, 0.9)},                                                                # Bürzel wackelt
    ],
    "toast": [
        {"kind": "glow", "key": "B", "colors": ("#ffe066", "#fff4b8"), "period": 2.4},        # Butter glänzt
    ],
    "kaktus": [
        {"box": (0, 4, 4, 8), "axis": "y", "grow": "left", "amp": -1, "period": 1.8, "arm": True},  # Arme
        {"box": (11, 4, 15, 8), "axis": "y", "grow": "right", "amp": -1, "period": 1.8, "phase": math.pi,
         "arm": True},
        {"box": (6, 0, 9, 1), "axis": "x", "grow": "up", "amp": 1, "period": 2.5},           # Blüte
    ],
    "geist": [
        {"kind": "float", "amp": 1, "period": 2.4},                                           # schwebt
        {"box": (1, 12, 14, 14), "axis": "y", "grow": "down", "amp": 1, "period": 1.2, "k": 0.8},  # Saum
        {"box": (0, 8, 1, 9), "axis": "y", "grow": "left", "amp": -1, "period": 1.6, "arm": True},  # Ärmchen
        {"box": (14, 8, 15, 9), "axis": "y", "grow": "right", "amp": -1, "period": 1.6, "phase": 1.2,
         "arm": True},
    ],
    "saugi": [
        {"kind": "glow", "key": "p", "colors": ("#ff4d4d", "#6a1c1c"), "period": 1.4},        # Lämpchen
    ],
}
# so schnell bewegen sich die Teile je Zustand (reden/freuen = aufgeregt, schlafen = träge)
PART_SPEED = {"talk": 1.8, "happy": 1.8, "walk": 1.3, "held": 1.6, "fall": 1.4, "jump": 1.4, "tuck": 1.4,
              "sleep": 0.4}

_data = None


def data():
    global _data
    if _data is None:
        with open(DATA_PATH, encoding="utf-8") as f:
            _data = json.load(f)
    return _data


def creature_ids():
    return [c["id"] for c in data()["creatures"]]


def get(cid):
    return next((c for c in data()["creatures"] if c["id"] == cid), data()["creatures"][0])


def personalities():
    return list(data()["variants"])


# ----------------------------------------------------------------- Palette
def _tweak(hex_color, tw):
    c = QColor(hex_color)
    r, g, b = c.redF(), c.greenF(), c.blueF()
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    h = (h + tw.get("h", 0) / 360.0) % 1.0
    s = min(1.0, max(0.0, s + tw.get("s", 0)))
    l = min(1.0, max(0.0, l + tw.get("l", 0)))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return QColor.fromRgbF(r, g, b).name()


def palette(c, variant, happy=False):
    d = data()
    pal = dict(c["palette"])
    v = d["variants"].get(variant, {})
    if not c.get("noTweak"):
        for k in ("B", "L", "D"):
            if k in pal and len(pal[k]) > 1:
                pal[k] = _tweak(pal[k], v.get("tweak", {}))
    pal.update(c.get("variantPalette", {}).get(variant, {}))
    if variant == "verspielt" or happy:
        pal["k"] = d["overlays"]["cheekPink"]
    for _ in range(4):  # Verweise (ein Zeichen) auflösen, auch verkettet
        for k, val in list(pal.items()):
            if isinstance(val, str) and len(val) == 1 and val in pal:
                pal[k] = pal[val]
    return pal


# ----------------------------------------------------------------- Frames
def _frames(c, name):
    fr = c["frames"][name]
    return [fr] if fr and isinstance(fr[0], str) else fr


def pose_rows(c, state, t, walk_i):
    """Liefert (rows, frame_name) für Zustand und Zeit. Atmen passiert fein: siehe breath_row."""
    if state == "walk":
        fs = _frames(c, "walk")
        return list(fs[walk_i % len(fs)]), "walk"
    if state in ("held", "fall", "jump"):
        fs = _frames(c, "held")
        return list(fs[int(t / 0.24) % len(fs)]), "held"
    if state == "sleep":
        rows = SLEEP.get(c["id"], {}).get("rows")
        return list(rows or _frames(c, "sit")[0]), "sleep"
    if state in ("sit", "tuck"):                          # tuck = Beine angezogen am Sprung-Scheitel
        return list(_frames(c, "sit")[0]), "sit"
    return list(_frames(c, "stand")[0]), "stand"


def breath_row(c, name, state, t):
    """Rasterzeile, an der der Oberkörper beim Ausatmen ein Feinpixel zusammensackt (sonst None)."""
    period = 1.3 if state == "sleep" else 0.16 if state == "talk" else 0.85   # reden: schnelles Wippen
    br = c.get("breathRow", {}).get(name)
    if br is not None and int(t / period) % 2 == 1:
        return br
    return None


def _eye_blocks(rows):
    seen, blocks = set(), []
    for y in range(len(rows) - 1):
        for x in range(len(rows[y]) - 1):
            if (x, y) in seen:
                continue
            if rows[y][x] == "e" and rows[y][x + 1] == "e" and rows[y + 1][x] == "e" and rows[y + 1][x + 1] == "e":
                blocks.append((x, y))
                seen.update({(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)})
    return blocks


def eye_mode(variant, state, blinking, lid=False, expr=None):
    """Augenform. expr = Gesichtsausdruck vom Pet (wide, dizzy, half, closed, happy) – geht vor."""
    d = data()
    if state == "sleep":
        return "closed"
    if expr in ("dizzy", "closed", "happy"):
        return expr
    if expr == "sparkle" and state not in ("held", "fall"):
        return "closed" if blinking else "sparkle"
    if state == "happy":
        return "happy"
    if expr == "wide":
        return "closed" if blinking else "wide"
    if state in ("held", "fall", "jump", "tuck"):
        return "small" if variant == "aengstlich" else "glint"
    if state in ("idle", "sit", "walk", "talk"):
        if blinking:
            return "closed"
        if lid:
            return "half"                               # Blinzeln: halb zu, ganz zu, halb zu
    base = d["variants"].get(variant, {}).get("eyes", "normal")
    if expr == "half" and base in ("normal", "glint"):
        return "half"                                   # müde: Lider hängen
    return base


# ----------------------------------------------------------------- fein (doppelte Auflösung)
_epx_cache = {}
_dy_cache = {}


def epx(rows):
    """Scale2x/EPX: jedes Rasterpixel wird zu 2×2 Feinpixeln, Ecken an Kanten werden abgerundet."""
    key = tuple(rows)
    out = _epx_cache.get(key)
    if out is not None:
        return out
    h, w = len(rows), len(rows[0])

    def at(x, y):
        return rows[y][x] if 0 <= x < w and 0 <= y < h else "."
    out = [[None] * (2 * w) for _ in range(2 * h)]
    for y in range(h):
        for x in range(w):
            P = rows[y][x]
            A, B, C, D = at(x, y - 1), at(x + 1, y), at(x - 1, y), at(x, y + 1)
            p1 = A if C == A and C != D and A != B else P
            p2 = B if A == B and A != C and B != D else P
            p3 = C if D == C and D != B and C != A else P
            p4 = D if B == D and B != A and D != C else P
            out[2 * y][2 * x], out[2 * y][2 * x + 1] = p1, p2
            out[2 * y + 1][2 * x], out[2 * y + 1][2 * x + 1] = p3, p4
    if len(_epx_cache) > 400:
        _epx_cache.clear()
    out = tuple(tuple(r) for r in out)
    _epx_cache[key] = out
    return out


def frame_dy(c, rows):
    """Um wie viele Rasterzeilen dieser Frame gegenüber dem Steh-Frame verschoben ist (Sitzen: tiefer)."""
    key = (c["id"], tuple(rows))
    dy = _dy_cache.get(key)
    if dy is None:
        stand = _frames(c, "stand")[0]
        best = -1
        for cand in (0, 1, -1, 2, -2, 3, -3, 4, -4):
            score = sum(1 for y, row in enumerate(rows) if 0 <= y - cand < len(stand)
                        for a, b in zip(row, stand[y - cand]) if a != "." and a == b)
            if score > best:
                best, dy = score, cand
        _dy_cache[key] = dy
    return dy


def parts_of(c, wave=False):
    """Die bewegten Teile; beim Winken schwingen die Arme doppelt so weit und schnell durchgehend."""
    out = []
    for part in PARTS.get(c["id"], ()):
        if wave and part.get("arm"):
            part = {k: v for k, v in part.items() if k != "every"}
            part["amp"], part["period"] = part["amp"] * 2, 0.32
        out.append(part)
    return out


def part_phases(c, state, t, wave=False):
    """Je bewegtem Teil eine Phasenstufe (None = ruht gerade). Gestuft, damit der Bild-Cache trifft."""
    speed = PART_SPEED.get(state, 1.0)
    out = []
    for i, part in enumerate(parts_of(c, wave)):
        if "every" in part:
            every, dur = part["every"]
            local = (t + every * ((i * 0.37 + len(c["id"]) * 0.11) % 1)) % every
            out.append(int(local * 24) if local < dur else None)
        else:
            out.append(int((t * speed / part["period"] + part.get("phase", 0) / math.tau) * 16) % 16)
    return tuple(out)


def _angle(part, q):
    if "every" in part:
        return math.tau * (q / 24) / part["period"]
    return math.tau * q / 16


def _round(v):
    return math.floor(v + 0.5)


def _bend(fine, part, q, dy):
    """Teil um bis zu amp Feinpixel auslenken. Rückwärts abgetastet (jedes Ziel holt sich sein Quell-
    pixel), dadurch entstehen keine Löcher; Stellen außerhalb des Teils behalten ihr altes Pixel."""
    H, W = len(fine), len(fine[0])
    x0, y0, x1, y1 = part["box"]
    X0, X1 = PAD + 2 * x0, PAD + 2 * x1 + 1
    Y0, Y1 = PAD + 2 * (y0 + dy), PAD + 2 * (y1 + dy) + 1
    amp, axis, grow, k = part["amp"], part["axis"], part.get("grow"), part.get("k", 0.0)
    ang = _angle(part, q)
    mar = abs(amp) + 1
    orig = [list(r) for r in fine]

    def weight(fx, fy):
        if grow == "up":
            w = (Y1 + 1 - (fy + 0.5)) / (Y1 + 1 - Y0)
        elif grow == "down":
            w = (fy + 0.5 - Y0) / (Y1 + 1 - Y0)
        elif grow == "left":
            w = (X1 + 1 - (fx + 0.5)) / (X1 + 1 - X0)
        elif grow == "right":
            w = (fx + 0.5 - X0) / (X1 + 1 - X0)
        else:
            return 1.0
        return min(1.0, max(0.0, w))

    xs = range(max(0, X0 - mar), min(W, X1 + mar + 1)) if axis == "x" else range(max(0, X0), min(W, X1 + 1))
    ys = range(max(0, Y0 - mar), min(H, Y1 + mar + 1)) if axis == "y" else range(max(0, Y0), min(H, Y1 + 1))
    for fy in ys:
        for fx in xs:
            along = fy if axis == "x" else fx
            d = _round(amp * weight(fx, fy) * math.sin(ang + k * along))
            sx, sy = (fx - d, fy) if axis == "x" else (fx, fy - d)
            src_in = X0 <= sx <= X1 and Y0 <= sy <= Y1 and 0 <= sx < W and 0 <= sy < H
            v = orig[sy][sx] if src_in else "."
            if X0 <= fx <= X1 and Y0 <= fy <= Y1:
                fine[fy][fx] = v
            elif src_in and v != ".":
                fine[fy][fx] = v


def _stamp_eyes(fine, blocks, mode, look):
    tpl = [[_EYE_KEYS[ch] for ch in row] for row in EYES.get(mode, EYES["normal"])]
    lx, ly = look if mode in LOOK_MODES else (0, 0)
    if mode == "wide":
        ly = 0                                          # große Augen füllen den Block schon ganz
    if mode == "half":
        ly = 0
    n = len(tpl)                                        # 4 Zeilen, höhere Vorlagen ragen nach oben
    for bx, by in blocks:
        X, Y = PAD + 2 * bx, PAD + 2 * by - (n - 4)
        out = [["lid" if ch in ("e", "w") else ch for ch in row] for row in tpl]
        for y in range(n):
            for x in range(4):
                if tpl[y][x] in ("e", "w") and 0 <= x + lx < 4 and 0 <= y + ly < n:
                    out[y + ly][x + lx] = tpl[y][x]
        for y in range(n):
            for x in range(4):
                fine[Y + y][X + x] = out[y][x]


def _stamp_mouth(fine, spec, mode, dy):
    """Mund nach Form zeichnen (rest = wie im Raster). Schnäbel klappen den Unterschnabel herunter."""
    if spec is None or mode in (None, "rest"):
        return
    H, W = len(fine), len(fine[0])
    x0, y0, x1, y1 = spec["box"]
    X0, X1 = PAD + 2 * x0, PAD + 2 * x1 + 1
    Y0, Y1 = PAD + 2 * (y0 + dy), PAD + 2 * (y1 + dy) + 1
    if "beak" in spec:
        if mode == "shut":
            return
        n = 2 if mode == "wide" else 1
        split = PAD + 2 * (spec["beak"] + dy)
        lower = [list(fine[fy]) for fy in range(split, Y1 + 1)]
        for fy in range(split, split + n):                # Spalt zwischen den Schnabelhälften
            for fx in range(X0, X1 + 1):
                if lower[0][fx] != "." and fy < H:
                    fine[fy][fx] = "e"
        for i, row in enumerate(lower):                   # Unterschnabel n Feinpixel tiefer
            fy = split + n + i
            for fx in range(X0, X1 + 1):
                if row[fx] != "." and fy < H:
                    fine[fy][fx] = row[fx]
        return
    wf, hf = X1 - X0 + 1, Y1 - Y0 + 1
    size = "narrow" if wf <= 2 else "tall" if hf >= 4 else "normal"
    shape = MOUTH_SHAPES[size].get(mode)
    if shape is None:
        return
    above = fine[Y0 - 1][(X0 + X1) // 2] if Y0 > 0 else "."
    skin = above if above not in (".", "e", "o") else "lid"
    if not spec.get("hidden"):
        for fy in range(Y0, Y1 + 1):                      # alten Mund wegnehmen
            for fx in range(X0, X1 + 1):
                fine[fy][fx] = skin
    tongue = spec.get("tongue", True)
    for i, row in enumerate(shape):
        fy = Y0 + i
        xs = (X0 + X1 + 1) // 2 - len(row) // 2
        for j, ch in enumerate(row):
            fx = xs + j
            if not (0 <= fy < H and 0 <= fx < W):
                continue
            if ch == "e":
                fine[fy][fx] = "e"
            elif ch == "T":
                fine[fy][fx] = "tongue" if tongue else "e"
            elif not spec.get("hidden") and fy <= Y1:
                fine[fy][fx] = skin


def _mix(a, b, k):
    ca, cb = QColor(a), QColor(b)
    return QColor.fromRgbF(ca.redF() + (cb.redF() - ca.redF()) * k, ca.greenF() + (cb.greenF() - ca.greenF()) * k,
                           ca.blueF() + (cb.blueF() - ca.blueF()) * k).name()


# ----------------------------------------------------------------- Zeichnen
class Renderer:
    def __init__(self):
        self._cache = {}
        self._colors = {}

    def size(self, c, px):
        """(Bildbreite, Bildhöhe, Fuß-x, Fuß-y) in Bildpixeln."""
        w = (c["w"] + 2 * MARGIN_X) * px
        h = (c["h"] + MARGIN_TOP) * px
        return w, h, w / 2, h

    def render(self, c, *, variant, state, t, walk_i, blinking, facing, px, stage, accessories=(),
               look=(0, 0), lid=False, expr=None, mouth="rest", wave=False, tint=None, crack=0,
               rim=True):
        """look = Blickrichtung, lid = halb geschlossen (Blinzeln), expr = Ausdruck (siehe eye_mode),
        mouth = rest|shut|open|wide|o, wave = Arme winken, tint = Tageszeit-Licht (siehe TINTS),
        crack = Risse in der Eierschale (0–3, Schlüpfen), rim = heller Umriss."""
        rows, frame = pose_rows(c, state, t, walk_i)
        breath = (breath_row(c, frame, state, t)
                  if frame in ("stand", "sit") and state not in ("tuck", "windup") else None)
        mode = eye_mode(variant, state, blinking, lid, expr)
        hop = bob = 0
        if state == "walk":
            hops = c.get("walkHop") or [0]
            hop = hops[walk_i % len(hops)]
            if not any(hops):
                bob = walk_i % 2                          # ohne eigenes Hüpfen: bei jedem Schritt wippen
        elif state == "happy":
            hop = -2 if int(t / 0.26) % 2 else 0
        cursor_on = int(t / 0.5) % 2 == 0
        sweat = variant == "aengstlich" and state != "sleep"
        sweat_dy = int(t / 0.4) % 2 if sweat else 0
        phases = part_phases(c, state, t, wave)
        look = tuple(look)
        key = (c["id"], variant, tuple(rows), mode, hop, cursor_on, sweat_dy if sweat else None,
               state == "held", facing, px, stage, tuple(accessories), state == "happy", breath, phases, look,
               mouth, wave, bob, tint, crack, rim)
        img = self._cache.get(key)
        if img is None:
            if len(self._cache) > 600:
                self._cache.clear()
            img = self._draw(c, rows, variant, mode, hop, cursor_on, sweat, sweat_dy, state,
                             facing, px, stage, accessories, breath, phases, look, mouth, wave, bob, tint,
                             crack, rim)
            self._cache[key] = img
        return img

    def _color(self, hex_color):
        col = self._colors.get(hex_color)
        if col is None:
            col = self._colors[hex_color] = QColor(hex_color)
        return col

    def _draw(self, c, rows, variant, mode, hop, cursor_on, sweat, sweat_dy, state, facing, px,
              stage, accessories, breath=None, phases=(), look=(0, 0), mouth="rest", wave=False, bob=0,
              tint=None, crack=0, rim=False):
        d = data()
        pal = palette(c, variant, happy=(state == "happy"))
        pal["tongue"] = TONGUE
        W, H, _, _ = self.size(c, px)
        img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setPen(Qt.PenStyle.NoPen)

        # feines Raster: hochgerechnet, mit Rand für bewegte Teile
        blocks = _eye_blocks(rows)
        fw = 2 * c["w"] + 2 * PAD
        fine = [["."] * fw for _ in range(PAD)]
        fine += [["."] * PAD + list(r) + ["."] * PAD for r in epx(rows)]
        _stamp_eyes(fine, blocks, mode, look)
        lying = state == "sleep"
        if lying:                                         # Liegepose: Mund steht im eigenen Raster
            sp = SLEEP.get(c["id"], {})
            box = sp.get("mouth")
            spec, dy = (dict(MOUTHS.get(c["id"], {}), box=box) if box else None), 0
            spec = spec and {k: v for k, v in spec.items() if k != "beak"}
        else:
            spec, dy = MOUTHS.get(c["id"]), frame_dy(c, rows)
        _stamp_mouth(fine, spec, mouth, dy)
        float_dy = bob
        for part, q in zip(parts_of(c, wave), phases):
            if q is None:
                continue
            kind = part.get("kind", "bend")
            if lying and kind == "bend":
                continue                                  # im Schlaf liegen Arme, Schwanz & Co. still
            if kind == "float":
                float_dy += _round(part["amp"] * math.sin(_angle(part, q)))
            elif kind == "glow":
                a, b = part["colors"]
                pal[part["key"]] = _mix(a, b, 0.5 + 0.5 * math.sin(_angle(part, q)))
            else:
                _bend(fine, part, q, dy)
        if tint in TINTS:
            col, k = TINTS[tint]
            pal = {key: (_mix(v, col, k) if isinstance(v, str) and len(v) > 1 else v) for key, v in pal.items()}
        if breath is not None:
            del fine[PAD + 2 * breath + 1]                # ausatmen: Oberkörper sackt ein Feinpixel
            fine.insert(0, ["."] * fw)

        def ph(f):
            return (f * px) // 2

        fx0 = 2 * MARGIN_X - PAD
        fy0 = 2 * (MARGIN_TOP + hop) - PAD + float_dy
        crt = c.get("crt")
        sl, slh = QColor(0, 0, 0, 72), max(1, px // 4)
        if rim:
            self._rim(p, fine, pal, fx0, fy0, ph)
        for y, row in enumerate(fine):
            Y = fy0 + y
            y0, y1 = ph(Y), ph(Y + 1)
            if y1 <= y0:
                continue
            for x, ch in enumerate(row):
                if ch == ".":
                    continue
                if ch == "C" and not cursor_on:
                    ch = "S"
                col = pal.get(ch)
                if col is None or len(col) < 2:
                    continue
                x0, x1 = ph(fx0 + x), ph(fx0 + x + 1)
                p.fillRect(x0, y0, x1 - x0, y1 - y0, self._color(col))
                if crt and Y % 2 == 1:                    # CRT-Scanline unten in jedem Rasterpixel
                    p.fillRect(x0, y1 - slh, x1 - x0, slh, sl)

        # Zubehör in Rasterpixeln (schwebt mit)
        ox, oy = MARGIN_X, MARGIN_TOP + hop + float_dy / 2

        def put(x, y, color):
            p.fillRect(int((ox + x) * px), int((oy + y) * px), px, px, self._color(color))

        if stage == "baby":                               # Eierschale bleibt am Boden, auch wenn es schwebt
            self._eggshell(p, rows, ox, MARGIN_TOP + hop, px, d["overlays"]["eggshell"], crack)
        anchors = c.get("anchors", {})
        if "brille" in accessories:
            gc = c.get("glassColor", "#1d1f27")
            for bx, by in blocks:
                for i in range(4):
                    for (xx, yy) in ((bx - 1 + i, by - 1), (bx - 1 + i, by + 2), (bx - 1, by - 1 + i), (bx + 2, by - 1 + i)):
                        put(xx, yy, gc)
            if len(blocks) >= 2:
                (x1, y1), (x2, _) = sorted(blocks)[:2]
                for xx in range(x1 + 3, x2 - 1):
                    put(xx, y1 - 1, gc)
        if "muetze" in accessories and "helm" not in accessories and "helm" in anchors:
            self._overlay(p, MUETZE, anchors["helm"]["x"], anchors["helm"]["y"], ox, oy, px)
        if "helm" in accessories and "helm" in anchors:
            self._overlay(p, d["overlays"]["helm"], anchors["helm"]["x"], anchors["helm"]["y"], ox, oy, px)
        if "lupe" in accessories and "lupe" in anchors:
            self._overlay(p, d["overlays"]["lupe"], anchors["lupe"]["x"], anchors["lupe"]["y"], ox, oy, px)
        if sweat and "sweat" in anchors:
            self._overlay(p, d["overlays"]["sweat"], anchors["sweat"]["x"], anchors["sweat"]["y"] + sweat_dy, ox, oy, px)
        if state == "held" and "hand" in anchors:
            a = anchors["hand"]
            self._overlay(p, d["overlays"]["hand"], a["x"] - 3, a["y"] - 5, ox, oy - hop, px)
        p.end()
        if facing < 0:
            img = img.transformed(QTransform().scale(-1, 1))
        return img

    @staticmethod
    def _overlay(p, ov, ax, ay, ox, oy, px):
        for y, row in enumerate(ov["map"]):
            for x, ch in enumerate(row):
                if ch != "." and ch in ov["colors"]:
                    p.fillRect(int((ox + ax + x) * px), int((oy + ay + y) * px), px, px, QColor(ov["colors"][ch]))

    def _rim(self, p, fine, pal, fx0, fy0, ph):
        """Heller Umriss: jedes leere Feinpixel neben der Figur bekommt einen Hauch Weiß."""
        H, W = len(fine), len(fine[0])
        vis = [[ch != "." and len(pal.get("S" if ch == "C" else ch) or "") > 1 for ch in row] for row in fine]
        col = QColor(*RIM)
        for y in range(H):
            for x in range(W):
                if vis[y][x]:
                    continue
                if ((y > 0 and vis[y - 1][x]) or (y + 1 < H and vis[y + 1][x])
                        or (x > 0 and vis[y][x - 1]) or (x + 1 < W and vis[y][x + 1])):
                    x0, x1, y0, y1 = ph(fx0 + x), ph(fx0 + x + 1), ph(fy0 + y), ph(fy0 + y + 1)
                    p.fillRect(x0, y0, x1 - x0, y1 - y0, col)

    @staticmethod
    def _eggshell(p, grid, ox, oy, px, egg, crack=0):
        h = len(grid)
        xs = [x for row in grid[-6:] for x, ch in enumerate(row) if ch != "."]
        if not xs:
            return
        x0, x1 = min(xs) - 1, max(xs) + 1
        top = h - 5
        shell, outline = QColor(egg["shell"]), QColor(egg["outline"])
        for x in range(x0, x1 + 1):
            edge = top + (0 if x % 2 == 0 else 1)
            for y in range(edge, h):
                is_border = y == edge or x in (x0, x1) or y == h - 1
                p.fillRect(int((ox + x) * px), int((oy + y) * px), px, px, outline if is_border else shell)
        # Schlüpfen: Risse im Zickzack, erst in der Mitte, dann links und rechts
        mid = (x0 + x1) // 2
        cracks = [(mid, 0), (x0 + 2, 1), (x1 - 2, 1)][:max(0, min(3, crack))]
        for cx, dy0 in cracks:
            for i in range(3):
                xx, yy = cx + (i % 2), top + 1 + dy0 + i
                if yy < h - 1:
                    p.fillRect(int((ox + xx) * px), int((oy + yy) * px), px, px, outline)
