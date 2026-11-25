"""Rendert die Figuren aus design/pet-data.json nach den dort beschriebenen Regeln."""
import colorsys
import json
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QTransform

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "design", "pet-data.json")

STAGE_PX = {"baby": 2, "jung": 3, "erwachsen": 4}
MARGIN_X = 6     # Rasterpixel links/rechts im Bild (Lupe, Herzchen)
MARGIN_TOP = 8   # Rasterpixel über dem Kopf (Hand, Helm, Effekte)

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
    """Liefert (rows, frame_name) für Zustand und Zeit."""
    if state == "walk":
        fs = _frames(c, "walk")
        return list(fs[walk_i % len(fs)]), "walk"
    if state in ("held", "fall", "jump"):
        fs = _frames(c, "held")
        return list(fs[int(t / 0.24) % len(fs)]), "held"
    if state in ("sit", "sleep"):
        rows, name = list(_frames(c, "sit")[0]), "sit"
    else:
        rows, name = list(_frames(c, "stand")[0]), "stand"
    period = 1.3 if state == "sleep" else 0.16 if state == "talk" else 0.85   # reden: schnelles Wippen
    br = c.get("breathRow", {}).get(name)
    if br is not None and int(t / period) % 2 == 1:
        rows.pop(br)
        rows.insert(0, "." * c["w"])
    return rows, name


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


def eye_mode(variant, state, blinking):
    d = data()
    if state == "sleep":
        return "closed"
    if state == "happy":
        return "happy"
    if state in ("held", "fall"):
        return "small" if variant == "aengstlich" else "glint"
    if blinking and state in ("idle", "sit", "walk"):
        return "closed"
    return d["variants"].get(variant, {}).get("eyes", "normal")


# ----------------------------------------------------------------- Zeichnen
class Renderer:
    def __init__(self):
        self._cache = {}

    def size(self, c, px):
        """(Bildbreite, Bildhöhe, Fuß-x, Fuß-y) in Bildpixeln."""
        w = (c["w"] + 2 * MARGIN_X) * px
        h = (c["h"] + MARGIN_TOP) * px
        return w, h, w / 2, h

    def render(self, c, *, variant, state, t, walk_i, blinking, facing, px, stage, accessories=()):
        rows, frame = pose_rows(c, state, t, walk_i)
        mode = eye_mode(variant, state, blinking)
        hop = 0
        if state == "walk":
            hops = c.get("walkHop") or [0]
            hop = hops[walk_i % len(hops)]
        elif state == "happy":
            hop = -2 if int(t / 0.26) % 2 else 0
        cursor_on = int(t / 0.5) % 2 == 0
        sweat = variant == "aengstlich" and state != "sleep"
        sweat_dy = int(t / 0.4) % 2 if sweat else 0
        key = (c["id"], variant, tuple(rows), mode, hop, cursor_on, sweat_dy if sweat else None,
               state == "held", facing, px, stage, tuple(accessories), state == "happy")
        img = self._cache.get(key)
        if img is None:
            if len(self._cache) > 600:
                self._cache.clear()
            img = self._draw(c, rows, variant, mode, hop, cursor_on, sweat, sweat_dy, state,
                             facing, px, stage, accessories)
            self._cache[key] = img
        return img

    def _draw(self, c, rows, variant, mode, hop, cursor_on, sweat, sweat_dy, state, facing, px,
              stage, accessories):
        d = data()
        pal = palette(c, variant, happy=(state == "happy"))
        W, H, _, _ = self.size(c, px)
        img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setPen(Qt.PenStyle.NoPen)
        ox, oy = MARGIN_X, MARGIN_TOP + hop

        def put(x, y, color):
            p.fillRect(int((ox + x) * px), int((oy + y) * px), px, px, QColor(color))

        # Augen ersetzen
        grid = [list(r) for r in rows]
        blocks = _eye_blocks(rows)
        em = d["eyeModes"].get(mode, d["eyeModes"]["normal"])
        for bx, by in blocks:
            for i, (dx, dy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
                grid[by + dy][bx + dx] = em[i]
        for y, row in enumerate(grid):
            for x, ch in enumerate(row):
                if ch == ".":
                    continue
                if ch == "C" and not cursor_on:
                    ch = "S"
                col = pal.get(ch)
                if col is None or len(col) < 2:
                    continue
                put(x, y, col)
        # CRT-Scanlines
        if c.get("crt"):
            sl = QColor(0, 0, 0, 72)
            hh = max(1, px // 4)
            for y, row in enumerate(grid):
                for x, ch in enumerate(row):
                    if ch != ".":
                        p.fillRect(int((ox + x) * px), int((oy + y) * px + px - hh), px, hh, sl)
        # Babystufe: Eierschale über die unteren Zeilen
        if stage == "baby":
            self._eggshell(p, grid, ox, oy, px, d["overlays"]["eggshell"])
        # Accessoires
        anchors = c.get("anchors", {})
        if "brille" in accessories:
            gc = QColor(c.get("glassColor", "#1d1f27"))
            for bx, by in blocks:
                for i in range(4):
                    for (xx, yy) in ((bx - 1 + i, by - 1), (bx - 1 + i, by + 2), (bx - 1, by - 1 + i), (bx + 2, by - 1 + i)):
                        put(xx, yy, gc.name())
            if len(blocks) >= 2:
                (x1, y1), (x2, _) = sorted(blocks)[:2]
                for xx in range(x1 + 3, x2 - 1):
                    put(xx, y1 - 1, gc.name())
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

    @staticmethod
    def _eggshell(p, grid, ox, oy, px, egg):
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
