"""Gesten: kurze Körper-Animationen (strecken, schütteln, Kopf schief …) für alle Figuren."""
import math
import random

from PyQt6.QtGui import QColor

from claude_pet import creatures
from claude_pet.creatures import MARGIN_TOP, MARGIN_X
from claude_pet.pet import GESTURES, NO_BODY, Pet
from claude_pet.windows import PetWindow
from claude_pet.world import Platform


def _standing(pers="neugierig", cid="katze"):
    pet = Pet(creatures.get(cid), "jung", pers)
    pet.placed, pet.x, pet.y = True, 300.0, 400.0
    pet.support = Platform(0, 1000, 400, 0, 3)
    pet.pane = 0
    pet.state, pet.timer = "idle", 30.0
    pet.grace = 0
    return pet


def _run(pet, seconds, dt=1 / 60):
    for _ in range(int(seconds / dt)):
        pet.anim_t += dt
        pet._tick_gesture(dt)


def test_jede_geste_laeuft_durch_und_endet():
    for kind, (dur, allowed) in GESTURES.items():
        pet = _standing()
        pet.state = "happy" if allowed and "idle" not in allowed else "idle"
        assert pet.start_gesture(kind), kind
        bodies = []
        for _ in range(int(dur * 60) + 2):
            bodies.append(pet.body())
            _run(pet, 1 / 60)
        assert pet.gesture is None, f"{kind} endet nach {dur} s"
        assert any(b != NO_BODY for b in bodies), f"{kind} bewegt sichtbar etwas"
        assert pet.body() == NO_BODY


def test_gesten_bleiben_im_bild():
    """Gestreckt, geneigt und verschoben passt jede Figur noch in ihr Fenster (Ränder MARGIN_*)."""
    for c in creatures.data()["creatures"]:
        for kind, (dur, allowed) in GESTURES.items():
            pet = _standing(cid=c["id"])
            pet.state = "happy" if allowed and "idle" not in allowed else "idle"
            pet.start_gesture(kind)
            hop = 2 if pet.state == "happy" else 0            # Freuden-Hüpfer hebt um 2 Rasterpixel
            while pet.gesture is not None:
                b = pet.body()
                a = math.radians(b["rot"])
                w2, h = c["w"] / 2 * b["sx"], (c["h"] + hop) * b["sy"]
                # Ecken des Inhalts relativ zur Fußmitte (y nach oben)
                for x, y in ((-w2, 0), (w2, 0), (-w2, h), (w2, h)):
                    rx = x * math.cos(a) + y * math.sin(a) + b["dx"]
                    ry = -x * math.sin(a) + y * math.cos(a)
                    assert abs(rx) <= c["w"] / 2 + MARGIN_X, (c["id"], kind, rx)
                    assert ry <= c["h"] + MARGIN_TOP - 1, (c["id"], kind, ry)
                _run(pet, 1 / 30)


def test_geste_bricht_ab_wenn_pet_hochgehoben_wird():
    pet = _standing()
    pet.start_gesture("strecken")
    pet.grab()
    _run(pet, 1 / 60)
    assert pet.gesture is None
    b = pet.body()
    assert b["pivot"] == "kopf", "gehalten baumelt es an der Hand"


def test_geste_nur_in_passendem_zustand():
    pet = _standing()
    pet.state = "sleep"
    assert not pet.start_gesture("strecken")
    assert not pet.start_gesture("gibtsnicht")
    assert pet.start_gesture("zittern"), "zittern geht immer"


def test_umschauen_schaut_hin_und_her_und_endet_umgedreht():
    pet = _standing()
    before = pet.facing
    pet.perform("umschauen")
    seen = set()
    for _ in range(100):
        _run(pet, 1 / 60)
        seen.add(pet.facing)
    assert seen == {1, -1}
    assert pet.gesture is None and pet.facing == -before


def test_aufwachen_mit_strecken():
    random.seed(1)
    pet = _standing("faul")
    pet.state, pet.timer = "sleep", 0.01
    pet._ground(0.05, None)
    assert pet.state == "idle"
    assert pet.gesture and pet.gesture["kind"] == "strecken"


def test_harte_landung_schuettelt():
    pet = _standing()
    pet.state, pet.vy = "fall", 2600 * pet.S
    pet._land(Platform(0, 1000, 400, 0, 3))
    assert pet.state == "sit" and pet.gesture["kind"] == "schuetteln"


def test_zappeln_im_leerlauf_je_nach_charakter():
    for pers in ("faul", "neugierig", "verspielt", "aengstlich"):
        random.seed(7)
        pet = _standing(pers)
        kinds = set()
        for _ in range(60 * 120):
            pet.timer = 30.0
            pet._maybe_fidget(1 / 60, "idle")
            if pet.gesture:
                kinds.add(pet.gesture["kind"])
            _run(pet, 1 / 60)
        assert kinds, f"{pers} zappelt in zwei Minuten mindestens einmal"


def test_flug_streckt_und_rennen_lehnt():
    pet = _standing()
    pet.state, pet.vy, pet.vx = "jump", -900 * pet.S, 400 * pet.S
    b = pet.body()
    assert b["sy"] > 1 and b["rot"] > 0
    pet.state, pet.run, pet.facing, pet.vx, pet.vy = "walk", 1.8, -1, 0, 0
    assert pet.body()["rot"] < 0


def test_haiku_und_sprueche_kennen_die_gesten():
    from claude_pet import mind, personas
    for v in ("strecken", "schuetteln"):
        assert v in mind.VERBS and v in mind.INSTANT and v in personas.ACTIONS
    pet = _standing()
    pet.perform("strecken")
    assert pet.gesture["kind"] == "strecken"
    pet.gesture = None
    pet.perform("schuetteln")
    assert pet.gesture["kind"] == "schuetteln"
    pet.perform("tanzen")
    assert pet.state == "happy" and pet.gesture["kind"] == "tanzen"


class _Ctl:
    def __init__(self, pet):
        self.pet = pet
        self.renderer = creatures.Renderer()
        self.prof = {"personality": pet.personality}

    def accessories(self):
        return ()


def test_pet_fenster_zeichnet_gesten(qapp):
    pet = _standing()
    win = PetWindow(_Ctl(pet))
    win.setGeometry(*win.geometry_for(pet))
    plain = win.grab().toImage()
    pet.start_gesture("kopfschief")
    _run(pet, 0.8)
    tilted = win.grab().toImage()
    assert plain.size() == tilted.size() and plain != tilted
    # Füße bleiben unten in der Mitte stehen: unterste Zeile in der Mitte nicht leer
    h = tilted.height()
    row = [QColor(tilted.pixel(x, h - 1)).alpha() for x in range(tilted.width())]
    assert any(row)


# ------------------------------------------------------------ feinere Grafik, Augen, Körperteile
def _img(c, **kw):
    args = dict(variant="neugierig", state="idle", t=0.0, walk_i=0, blinking=False, facing=1, px=4,
                stage="erwachsen")
    args.update(kw)
    img = creatures.Renderer().render(c, **args)
    return bytes(img.constBits().asarray(img.sizeInBytes()))     # Inhalt, vergleichbar


def test_epx_verdoppelt_und_rundet_ecken():
    fine = creatures.epx(["..o..", ".ooo.", "ooooo"])
    assert len(fine) == 6 and len(fine[0]) == 10
    assert fine[0][4] == "." or fine[0][5] == "o", "Spitze bleibt erhalten"
    assert fine[2][2] == ".", "Treppenstufe wird abgerundet"


def test_augen_schauen_in_alle_richtungen_und_blinzeln_in_stufen():
    c = creatures.get("geist")
    seen = {_img(c, look=lk) for lk in ((0, 0), (1, 0), (-1, 0), (0, -1), (0, 1))}
    assert len(seen) == 5, "jede Blickrichtung sieht anders aus"
    opened, half, shut = _img(c), _img(c, lid=True), _img(c, blinking=True)
    assert len({opened, half, shut}) == 3


def test_koerperteile_bewegen_sich_bei_allen_figuren_mit_teilen():
    for c in creatures.data()["creatures"]:
        if not creatures.PARTS.get(c["id"]):
            continue
        frames = {_img(c, t=t / 10) for t in range(0, 70)}
        assert len(frames) > 2, f"{c['id']}: Teile bewegen sich"


def test_teile_liegen_im_raster_und_passen_zu_allen_frames():
    for c in creatures.data()["creatures"]:
        for part in creatures.PARTS.get(c["id"], ()):
            if "box" not in part:
                continue
            x0, y0, x1, y1 = part["box"]
            assert 0 <= x0 <= x1 < c["w"] and 0 <= y0 <= y1 < c["h"], (c["id"], part)
        for name in ("sit", "held", "walk"):
            for rows in creatures._frames(c, name):
                assert abs(creatures.frame_dy(c, rows)) <= 3, (c["id"], name)


def test_sitzen_ist_tiefer_ausgerichtet():
    c = creatures.get("katze")
    assert creatures.frame_dy(c, creatures._frames(c, "sit")[0]) == 2
    assert creatures.frame_dy(c, creatures._frames(c, "stand")[0]) == 0


def test_blick_folgt_der_maus():
    pet = _standing()
    pet.facing = 1
    pet.step(1 / 60, None, lambda x: 1000, (0, 0, 2000, 2000), (pet.x + 200, pet.y - 300))
    assert pet.look == (1, -1), "Maus rechts oben"
    pet.look_hold = 0
    pet._tick_look(1 / 60, (pet.x - 200, pet.y))
    assert pet.look[0] == -1, "Maus hinter dem Pet: schaut zurück"
    pet.state, pet.vy, pet.look_hold = "fall", 500, 0
    pet._tick_look(1 / 60, None)
    assert pet.look == (0, 1), "fällt: schaut nach unten"


def test_lidschlag_halb_zu_halb():
    from claude_pet.pet import BLINK_T
    pet = _standing()
    seen = []
    pet.blink_t, pet.next_blink = BLINK_T, 99
    while pet.blink_t > 0:
        pose = pet.pose()
        seen.append("zu" if pose["blinking"] else "halb" if pose["lid"] else "offen")
        pet._tick_blink(1 / 120)
    dedup = [s for i, s in enumerate(seen) if i == 0 or s != seen[i - 1]]
    assert dedup == ["halb", "zu", "halb"]


def test_zeichnen_bleibt_schnell():
    import time
    c = creatures.get("katze")
    r = creatures.Renderer()
    t0 = time.perf_counter()
    for i in range(60):
        r.render(c, variant="verspielt", state="idle", t=i * 0.37, walk_i=0, blinking=False, facing=1,
                 px=4, stage="erwachsen", look=((i % 3) - 1, 0), accessories=("brille", "helm"))
    per = (time.perf_counter() - t0) / 60
    assert per < 0.02, f"{per * 1000:.1f} ms pro Bild"


# ------------------------------------------------------------ Mund, Ausdrücke, Winken, Niesen, Staub
def test_jede_figur_kann_den_mund_bewegen():
    for c in creatures.data()["creatures"]:
        rest = _img(c, mouth="rest")
        for m in ("open", "wide", "o"):
            assert _img(c, mouth=m) != rest, (c["id"], m)


def test_neue_augen_ausdruecke():
    c = creatures.get("katze")
    base = _img(c)
    for expr in ("wide", "dizzy", "half", "closed"):
        assert _img(c, expr=expr) != base, expr
    assert _img(c, expr="half", variant="aengstlich") == _img(c, variant="aengstlich"), \
        "kleine ängstliche Augen bleiben klein, auch wenn es müde ist"


def test_winken_bewegt_die_arme():
    c = creatures.get("kaktus")
    still = {_img(c, t=t / 20) for t in range(10)}
    waving = {_img(c, t=t / 20, wave=True) for t in range(10)}
    assert len(waving) > len(still)


def test_reden_bewegt_den_mund_unregelmaessig():
    pet = _standing()
    pet.state = "talk"
    mouths = []
    for _ in range(80):
        pet.anim_t += 1 / 60
        mouths.append(pet.face()[1])
    assert {"open", "shut", "rest"} <= set(mouths)


def test_gaehnen_erschrecken_schwindelig_muede():
    pet = _standing()
    pet._effect("gähn", life=1.8)
    assert pet.face()[:2] == ("closed", "wide")
    _run_look(pet, 1.5)
    pet._effect("!", life=1.0)
    assert pet.face()[:2] == ("wide", "o")
    _run_look(pet, 1.0)
    pet.state, pet.vy = "fall", 2600 * pet.S
    pet._land(Platform(0, 1000, 400, 0, 3))
    assert pet.face()[0] == "dizzy"
    assert any(e["kind"] == "staub" for e in pet.effects), "harte Landung wirbelt Staub auf"
    _run_look(pet, 2.0)
    pet.state, pet.energy, pet.gesture = "idle", 20, None
    assert pet.face()[0] == "half", "müde: Lider hängen"


def _run_look(pet, seconds):
    for _ in range(int(seconds * 60)):
        pet._tick_look(1 / 60, None)
        _run(pet, 1 / 60)


def test_maus_kommt_zurueck_pet_winkt():
    pet = _standing()
    far = (pet.x + 5000, pet.y)
    for _ in range(60):
        pet._tick_look(1.0, far)
    pet._tick_look(1 / 60, (pet.x + 30, pet.y - 20))
    assert pet.gesture and pet.gesture["kind"] == "winken"
    assert pet.face()[2], "winkt mit den Armen"
    pet.gesture = None
    pet._tick_look(1 / 60, (pet.x + 30, pet.y - 20))
    assert pet.gesture is None, "nicht bei jedem Vorbeikommen"


def test_niesen_mit_hatschi():
    pet = _standing()
    pet.start_gesture("niesen")
    _run(pet, 1.5)
    assert any(e["kind"] == "hatschi" for e in pet.effects)


def test_rennen_staubt():
    pet = _standing()
    pet.walk_to(pet.x + 500, run=1.8)
    for _ in range(60):
        pet._ground(1 / 60, None)
    assert sum(e["kind"] == "staub" for e in pet.effects) >= 2


# ------------------------------------------------------------ Sprung, Klettern, Schatten, Tageslicht
def _world_pet(cid="katze"):
    from claude_pet.world import World
    from conftest import make_snapshot
    w = World()
    w.update(make_snapshot(["x" * 70] * 12, rows=20))
    pet = Pet(creatures.get(cid), "jung", "verspielt")
    pet.busy = True
    for _ in range(600):
        pet.on_world(w)
        pet.step(1 / 60, w, lambda x: 1100, (-2000, -100, 4000, 1200), None)
        if pet.grounded and pet.land_t > 1:
            break
    return pet, w


def _tick(pet, w, n=1):
    for _ in range(n):
        pet.on_world(w)
        pet.step(1 / 60, w, lambda x: 1100, (-2000, -100, 4000, 1200), None)


def test_sprung_holt_aus_rollt_sich_ein_und_federt_die_landung():
    pet, w = _world_pet()
    x0, y0, row = pet.x, pet.y, pet.support.row
    target = next(q for q in w.platforms if q.row == row - 3)
    pet._ballistic_to(pet.x + 40, target.y, apex=1.2 * pet.line_h)
    assert pet.state == "jump" and pet.windup > 0
    assert pet.pose()["state"] == "windup" and pet.body()["sy"] <= 1
    _tick(pet, w, 4)
    assert (pet.x, pet.y) == (x0, y0), "beim Ausholen steht es noch"
    assert pet.body()["sy"] < 0.9, "in den Knien"
    poses, dust = [], False
    for _ in range(200):
        _tick(pet, w)
        poses.append(pet.pose()["state"])
        dust = dust or any(e["kind"] == "staub" for e in pet.effects)
        if pet.grounded:
            break
    assert pet.support.row == row - 3, "Sprung kommt trotz Ausholen an"
    assert "tuck" in poses and poses.index("tuck") > 0, "am Scheitel Beine angezogen"
    assert dust, "kräftiger Absprung wirbelt Staub auf"
    sys_ = []
    for _ in range(int(0.4 * 60)):
        sys_.append(pet.body()["sy"])
        _tick(pet, w)
    assert min(sys_) < 1 and max(sys_) > 1, "stauchen und nachfedern"


def test_huepfer_vom_boden_holt_kurz_aus_aber_nicht_in_der_luft():
    pet, w = _world_pet("geist")
    pet._hop(-400)
    assert pet.windup > 0
    pet.windup = 0
    _tick(pet, w, 5)
    pet._hop(-400)                                     # in der Luft: sofort
    assert pet.windup == 0


def test_gepackt_beim_ausholen_bricht_den_sprung_ab():
    pet, w = _world_pet()
    pet._hop(-400)
    pet.grab()
    _tick(pet, w)
    assert pet.windup == 0


def test_klettern_pendelt_und_zieht_sich_hoch():
    pet, w = _world_pet("kaktus")
    pet.begin_enter(pet.x, pet.y - 4 * pet.line_h)
    seen = {}
    for _ in range(240):
        _tick(pet, w)
        if pet.state in ("hang", "climb_in"):
            b = pet.body()
            seen.setdefault(pet.state, []).append((b["rot"], b["sy"], b["pivot"]))
            assert pet.look[1] == -1, "schaut nach oben, wo es hinwill"
        if pet.state == "hidden":
            break
    assert pet.state == "hidden"
    for st in ("hang", "climb_in"):
        rots = [r for r, _, _ in seen[st]]
        assert max(rots) - min(rots) > 3, f"{st}: pendelt/zieht im Rhythmus"
        assert all(pv == "kopf" for _, _, pv in seen[st])


def test_schatten_unter_den_fuessen_nur_am_boden(qapp):
    pet = _standing()
    win = PetWindow(_Ctl(pet))
    x, y, w_, h = win.geometry_for(pet)
    assert h == creatures.Renderer().size(pet.creature, pet.px)[1] + pet.px
    win.setGeometry(x, y, w_, h)
    img = win.grab().toImage()
    assert img.pixelColor(w_ // 2, h - pet.px).alpha() > 0, "Schatten unter den Füßen"
    pet.state, pet.support = "fall", None
    img = win.grab().toImage()
    assert img.pixelColor(w_ // 2, h - pet.px).alpha() == 0, "im Flug kein Schatten am Boden"


def test_tageszeit_licht():
    c = creatures.get("geist")
    assert len({_img(c), _img(c, tint="abend"), _img(c, tint="nacht")}) == 3
    pet = _standing()
    pet.daypart = "nacht"
    assert pet.pose()["tint"] == "nacht"
    pet.daypart = "tag"
    assert pet.pose()["tint"] is None


# ------------------------------------------------------------ Liegen, Schlüpfen, Anpirschen, Umriss
def test_liegeposen_passen_ins_raster_und_haben_augen():
    for c in creatures.data()["creatures"]:
        sp = creatures.SLEEP.get(c["id"])
        assert sp is not None, f"{c['id']}: keine Liegepose"
        rows, _ = creatures.pose_rows(c, "sleep", 0, 0)
        assert len(rows) == c["h"] and all(len(r) == c["w"] for r in rows), c["id"]
        assert len(creatures._eye_blocks(rows)) >= 2, f"{c['id']}: Augen in der Liegepose"
        box = sp.get("mouth")
        if box:
            x0, y0, x1, y1 = box
            assert 0 <= x0 <= x1 < c["w"] and 0 <= y0 <= y1 < c["h"], c["id"]
        if "rows" in sp:
            assert _img(c, state="sleep") != _img(c, state="sit"), f"{c['id']}: liegt anders als es sitzt"


def test_einschlafen_erst_sitzen_dann_hinlegen():
    pet = _standing()
    pet.state, pet.timer = "sleep", 60
    w = None
    for _ in range(3):
        pet.step(1 / 60, w, lambda x: 1000, (0, 0, 2000, 2000), None)
    assert pet.pose()["state"] == "sit"
    for _ in range(30):
        pet.step(1 / 60, w, lambda x: 1000, (0, 0, 2000, 2000), None)
    assert pet.pose()["state"] == "sleep"


def test_schluepfen_wackelt_reisst_bricht_auf():
    pet = Pet(creatures.get("geist"), "baby", "verspielt")
    pet.placed, pet.x, pet.y = True, 300.0, 400.0
    pet.support, pet.pane, pet.state, pet.grace = Platform(0, 1000, 400, 0, 3), 0, "idle", 0
    baby_px = pet.px
    assert pet.start_hatch("jung")
    cracks, rots = [], []
    for _ in range(int(3.2 * 60)):
        cracks.append(pet.pose()["crack"])
        rots.append(pet.body()["rot"])
        pet.step(1 / 60, None, lambda x: 1000, (0, 0, 2000, 2000), None)
        assert pet.x == 300.0, "schlüpft an Ort und Stelle"
    assert cracks[0] == 0 and max(cracks) == 3 and cracks[-1] == 0
    assert max(map(abs, rots)) > 4, "Ei wackelt"
    assert pet.stage == "jung" and pet.hatch is None
    assert pet.px > baby_px, "nach dem Schlüpfen größer"


def test_schluepfen_bringt_splitter_und_funkeln():
    pet = Pet(creatures.get("katze"), "baby", "neugierig")
    pet.placed, pet.support, pet.pane, pet.state, pet.grace = True, Platform(0, 1000, 400, 0, 3), 0, "idle", 0
    pet.x, pet.y = 300.0, 400.0
    pet.start_hatch("jung")
    kinds = set()
    for _ in range(int(2.0 * 60)):
        pet.step(1 / 60, None, lambda x: 1000, (0, 0, 2000, 2000), None)
        kinds |= {e["kind"] for e in pet.effects}
    assert {"schale", "funkeln"} <= kinds


def test_schluepfen_ohne_auftritt_wenn_es_nicht_passt():
    pet = Pet(creatures.get("katze"), "baby", "neugierig")
    pet.state = "fall"
    assert not pet.start_hatch("jung")
    assert pet.stage == "jung" and pet.hatch is None


def test_gepackt_beim_schluepfen_schluepft_sofort():
    pet = Pet(creatures.get("katze"), "baby", "neugierig")
    pet.placed, pet.support, pet.pane, pet.state, pet.grace = True, Platform(0, 1000, 400, 0, 3), 0, "idle", 0
    pet.start_hatch("jung")
    pet.step(1 / 60, None, lambda x: 1000, (0, 0, 2000, 2000), None)
    pet.grab()
    pet.step(1 / 60, None, lambda x: 1000, (0, 0, 2000, 2000), None)
    assert pet.stage == "jung" and pet.hatch is None


def test_pirscht_sich_an_den_ball_an_und_springt():
    import random as _r
    from claude_pet.ball import Ball
    from claude_pet.brain import Brain
    from claude_pet.world import World
    from conftest import make_snapshot
    _r.seed(3)
    w = World()
    snap = make_snapshot(["x" * 100] * 6, rows=20)
    w.update(snap)
    pet = Pet(creatures.get("katze"), "jung", "verspielt")
    brain = Brain(pet, "verspielt")
    VB, fl = (-2000, -100, 4000, 1200), (lambda x: 1100)
    for f in range(240):
        if f % 4 == 0:
            w.update(snap)
            pet.on_world(w)
        pet.busy = True
        pet.step(1 / 60, w, fl, VB, None)
    bx = pet.x + 4 * pet.W if pet.x + 4 * pet.W < 950 else pet.x - 4 * pet.W
    ball = Ball(bx, pet.y - 10, line_h=20)
    for _ in range(240):
        ball.step(1 / 60, w, fl, VB)
    assert ball.support.row == pet.support.row
    brain.ball = ball
    brain.set_goal(("ball",))
    pet.busy = True
    phases, crouched, sparkle = [], False, False
    for f in range(60 * 8):
        if f % 4 == 0:
            w.update(snap)
            brain.on_world(w)
            pet.on_world(w)
        brain.tick(1 / 60, w, (5000, 5000))
        pet.step(1 / 60, w, fl, VB, (5000, 5000))
        ball.step(1 / 60, w, fl, VB)
        if not phases or phases[-1] != brain._stalk:
            phases.append(brain._stalk)
        crouched = crouched or (pet.state == "walk" and pet.body()["sy"] < 0.9)
        sparkle = sparkle or pet.face()[0] == "sparkle"
        if pet.carrying:
            break
    assert phases[:3] == ["schleichen", "wackeln", "fertig"], phases
    assert crouched and sparkle and pet.carrying


def test_fauler_pirscht_nicht():
    from claude_pet.brain import Brain
    pet = _standing("faul")
    brain = Brain(pet, "faul")

    class B:
        x, bottom, resting = pet.x + 300, pet.y, True
    assert not brain._stalk_ball(B())


def test_heller_umriss_um_die_figur():
    c = creatures.get("bit")
    r = creatures.Renderer()
    kw = dict(variant="neugierig", state="idle", t=0, walk_i=0, blinking=False, facing=1, px=4, stage="erwachsen")
    with_rim, without = r.render(c, **kw), r.render(c, rim=False, **kw)
    # links neben dem Monitor: mit Umriss halbdurchsichtig hell, ohne leer
    y = (creatures.MARGIN_TOP + 6) * 4 + 2
    x = next(x for x in range(without.width()) if without.pixelColor(x, y).alpha() > 0) - 1
    assert without.pixelColor(x, y).alpha() == 0
    assert 0 < with_rim.pixelColor(x, y).alpha() < 255
