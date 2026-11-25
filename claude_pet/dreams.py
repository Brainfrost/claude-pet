"""Träume: Schläft das Pet, steigt ab und zu eine Gedankenwolke auf – mit einem kleinen Pixelbild von dem,
was es heute erlebt hat (Ball, gefressene Käfer, Commits …) oder was zu ihm passt."""
import random

# 7×7-Pixelbilder. Farben: k = dunkler Rand, sonst je Bild eigene Palette.
ICONS = {
    "ball": (["..rrr..", ".rwrrr.", "rwrrrrr", "rrrrrrr", "rrrrrrr", ".rrrrr.", "..rrr.."],
             {"r": "#ff5d5d", "w": "#ffffff"}),
    "kaefer": (["k.....k", ".k...k.", "..kkk..", ".krkrk.", "krrkrrk", ".krkrk.", "..kkk.."],
               {"k": "#1b1530", "r": "#e0413a"}),
    "keks": (["..ccc..", ".cdccc.", "cccccdc", "ccdcccc", "cccccdc", ".cdccc.", "..ccc.."],
             {"c": "#d9a45b", "d": "#6b3f1d"}),
    "herz": ([".rr.rr.", "rrrrrrr", "rrrrrrr", ".rrrrr.", "..rrr..", "...r...", "......."],
             {"r": "#ff4d6d"}),
    "stern": (["...y...", "...y...", "yyyyyyy", ".yyyyy.", "..yyy..", ".yy.yy.", "y.....y"],
              {"y": "#f2b705"}),
    "mond": (["..yyy..", ".yy....", "yy.....", "yy.....", "yy.....", ".yy....", "..yyy.."],
             {"y": "#f2b705"}),
    "fisch": ([".......", "..bbb.b", ".bbbbbb", "bkbbbb.", ".bbbbbb", "..bbb.b", "......."],
              {"b": "#4dabf7", "k": "#1b1530"}),
    "terminal": (["kkkkkkk", "kgkkkkk", "kkgkkkk", "kgkkkkk", "kkkkggk", "kkkkkkk", "......."],
                 {"k": "#1b1530", "g": "#3ddc84"}),
    "kaffee": ([".k.k...", "..k.k..", "bbbbb..", "bcccbbb", "bcccb.b", "bcccbbb", ".bbb..."],
               {"b": "#7a4a2a", "c": "#3b2416", "k": "#9a94b8"}),
    "wurm": ([".......", ".......", "..pp...", ".p..p.p", "p....pp", ".......", "......."],
             {"p": "#e86f9a"}),
    "brot": ([".......", "..bbbb.", ".bcbcbb", "bbbbbbb", "bbbbbbb", ".bbbbb.", "......."],
             {"b": "#c47a2c", "c": "#f3d29b"}),
}
LABEL = {"ball": "Ball", "kaefer": "Käfer", "keks": "Kekse", "herz": "Streicheleinheiten", "stern": "Commits",
         "mond": "den Mond", "fisch": "Fisch", "terminal": "das Terminal", "kaffee": "Kaffee", "wurm": "Würmer",
         "brot": "Brot"}

# Was die Figur besonders gern träumt
CREATURE_DREAM = {"katze": "fisch", "krake": "fisch", "ente": "brot", "spatz": "wurm", "tasse": "kaffee",
                  "toast": "brot", "bit": "terminal", "saugi": "keks", "axolotl": "fisch"}
CHARACTER_DREAM = {"verspielt": "ball", "faul": "mond", "neugierig": "terminal", "aengstlich": "herz"}

CLOUD = "#f4f1ff"
OUTLINE = "#1b1530"
LIFE = 4.5                     # so lange schwebt eine Wolke (s)
FIRST_AFTER = 5.0              # erster Traum frühestens nach so vielen Sekunden Schlaf
GAP = (14.0, 26.0)             # Abstand zwischen zwei Träumen


def pick(creature, personality, day, rnd=random):
    """Traumbild auswählen – gewichtet nach dem, was heute passiert ist."""
    w = {"mond": 1.0, "terminal": 1.0, "herz": 1.0 + min(4, day.get("strokes", 0)),
         "ball": 0.5 + min(6, 2 * day.get("balls", 0)),
         "kaefer": 0.5 + min(5, day.get("eaten", 0)),
         "keks": 0.3 + (1.5 if day.get("eaten") else 0),
         "stern": 0.2 + min(6, 2 * day.get("commits", 0))}
    fav = CREATURE_DREAM.get(creature)
    if fav:
        w[fav] = w.get(fav, 0) + 3.0
    w[CHARACTER_DREAM.get(personality, "mond")] += 2.0
    keys = list(w)
    return rnd.choices(keys, weights=[w[k] for k in keys])[0]


class Dreamer:
    """Entscheidet, wann geträumt wird. step() gibt ein neues Traumbild zurück, wenn es soweit ist."""

    def __init__(self, rnd=None):
        self.rnd = rnd or random.Random()
        self.asleep_for = 0.0
        self.next_at = FIRST_AFTER
        self.current = None        # (Bild, Alter)

    def step(self, dt, sleeping, creature, personality, day):
        if not sleeping:
            self.asleep_for, self.next_at, self.current = 0.0, FIRST_AFTER, None
            return None
        self.asleep_for += dt
        if self.current is not None:
            icon, age = self.current
            age += dt
            self.current = (icon, age) if age < LIFE else None
            return None
        if self.asleep_for >= self.next_at:
            icon = pick(creature, personality, day, self.rnd)
            self.current = (icon, 0.0)
            self.next_at = self.asleep_for + LIFE + self.rnd.uniform(*GAP)
            return icon
        return None

    def alpha(self):
        if self.current is None:
            return 0
        _, age = self.current
        k = min(1.0, age / 0.5, (LIFE - age) / 0.7)
        return max(0, int(255 * k))
