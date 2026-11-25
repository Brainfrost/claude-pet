"""Erkennt 'Ebenen' in beliebigen Fenstern per Bildanalyse: waagrechte Kanten (Textzeilen, Rahmen,
Buttons, Bildränder) werden zu Plattformen.

Es wird nur ein Ausschnitt rund ums Pet aufgenommen. Die Bilder bleiben im Speicher, werden nie
gespeichert und nie verschickt.
"""
import numpy as np
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QGuiApplication, QImage

EDGE = 26          # Helligkeitssprung zwischen zwei Pixelzeilen, ab dem eine Kante zählt
MIN_LEN = 36       # Mindestlänge einer Plattform in Pixeln
GAP_X = 5          # Lücken bis zu so vielen Pixeln werden überbrückt (Buchstaben einer Zeile)
MERGE_Y = 4        # Kanten, die so nah übereinander liegen, gelten als eine
MAX_PLATFORMS = 160
TEXTURE = 0.45     # Bänder mit mehr Kantenanteil sind Fotos/Rauschen -> ignorieren


def grab(x, y, w, h):
    """Bildschirmausschnitt (physische Pixel) als Graustufen-Array, oder None."""
    scr = QGuiApplication.screenAt(QPoint(int(x + w / 2), int(y + h / 2)))
    if scr is None:
        return None
    g = scr.geometry()
    x0, y0 = max(x, g.x()), max(y, g.y())
    x1, y1 = min(x + w, g.x() + g.width()), min(y + h, g.y() + g.height())
    if x1 - x0 < 40 or y1 - y0 < 40:
        return None
    pm = scr.grabWindow(0, x0 - g.x(), y0 - g.y(), x1 - x0, y1 - y0)
    img = pm.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape(img.height(), img.bytesPerLine())[:, :img.width()]
    return arr.astype(np.int16), x0, y0


def detect(gray, exclude=()):
    """Waagrechte Kanten -> [(y, x0, x1)] in Bildkoordinaten. exclude: Rechtecke (l, t, r, b),
    die ignoriert werden (das Pet selbst, seine Sprechblase)."""
    h, w = gray.shape
    d = np.abs(gray[1:, :] - gray[:-1, :]) > EDGE          # Kante zwischen Zeile y und y+1
    for l, t, r, b in exclude:
        d[max(0, t - 2):max(0, b + 2), max(0, l - 2):max(0, r + 2)] = False
    # Buchstaben einer Zeile zusammenziehen: waagrecht dilatieren, senkrecht 1 Pixel
    m = d.copy()
    for k in range(1, GAP_X + 1):
        m[:, k:] |= d[:, :-k]
    m[1:, :] |= m[:-1, :]
    # Textur (Fotos, Verläufe mit Rauschen): Anteil der Kantenpixel in der ganzen Zeile ...
    band = d.mean(axis=1)
    # ... und Präfixsummen, um ihn für jede einzelne Kante in konstanter Zeit zu prüfen
    box_cs = np.zeros((h, w + 1), dtype=np.int32)
    np.cumsum(np.cumsum(d, axis=1), axis=0, out=box_cs[1:, 1:])
    out = []
    for y in range(h - 1):
        if band[y] > TEXTURE:
            continue
        row = m[y]
        if not row.any():
            continue
        diff = np.diff(np.concatenate(([0], row.view(np.int8), [0])))
        starts = np.flatnonzero(diff == 1)
        ends = np.flatnonzero(diff == -1)
        for s, e in zip(starts, ends):
            if e - s < MIN_LEN:
                continue
            # zusätzlich lokal: Fotos, die nur einen Teil der Zeile einnehmen
            y0, y1 = max(0, y - 3), min(h - 1, y + 4)
            if (box_cs[y1, e] - box_cs[y0, e] - box_cs[y1, s] + box_cs[y0, s]) / ((y1 - y0) * (e - s)) > TEXTURE:
                continue
            out.append((_snap_up(d, y, int(s), int(e)) + 1, int(s), int(e - GAP_X)))
    return _merge(out)


def _snap_up(d, y, a, b, max_up=14, density=0.03):
    """Bei Text liegt die längste Kante oft mitten in den Buchstaben: so weit nach oben gehen,
    wie in derselben Spaltenbreite noch 'Tinte' (Kanten) ist – bis zur Oberkante der Schrift."""
    yy = y
    while yy - 1 >= 0 and y - yy < max_up and d[yy - 1, a:b].mean() > density:
        yy -= 1
    return yy


def _merge(runs):
    """Kanten, die fast auf gleicher Höhe liegen und sich überlappen, zusammenfassen (obere gewinnt)."""
    runs.sort()
    merged = []
    for y, a, b in runs:
        for i, (my, ma, mb) in enumerate(merged):
            if y - my <= MERGE_Y and a < mb and b > ma:
                merged[i] = (my, min(a, ma), max(b, mb))
                break
        else:
            merged.append((y, a, b))
    merged.sort(key=lambda r: r[2] - r[1], reverse=True)
    return merged[:MAX_PLATFORMS]


def platforms_around(cx, cy, w, h, exclude_global=()):
    """Plattformen [(y, x0, x1)] in globalen Koordinaten für den Ausschnitt um (cx, cy)."""
    return platforms_in_rect(int(cx - w / 2), int(cy - h * 0.6), int(w), int(h), exclude_global)


def platforms_in_rect(x, y, w, h, exclude_global=()):
    """Plattformen [(y, x0, x1)] in globalen Koordinaten für ein Bildschirm-Rechteck."""
    res = grab(int(x), int(y), int(w), int(h))
    if res is None:
        return []
    gray, ox, oy = res
    excl = [(l - ox, t - oy, r - ox, b - oy) for l, t, r, b in exclude_global]
    return [(y + oy, a + ox, b + ox) for y, a, b in detect(gray, excl)]
