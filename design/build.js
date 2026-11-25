// Baut pet-data.json aus kompakten Definitionen, prüft alle Raster und
// setzt das JSON in template.html ein -> claude-pet-entwuerfe.html
const fs = require('fs'), path = require('path');
const dir = __dirname;
const B = w => '.'.repeat(w);

// ---------- 1  Tilde (Pixelkatze) 20x16 ----------
const CAT_TOP = [
  "....................",
  ".............o...o..",
  "..o.........opo.opo.",
  ".o.........oBBBBBBBo",
  ".o.........oBBBBBBBo",
  ".o.........oBeeBeeBo",
  "..o........oBeeBeeBo",
  "..o........okBBpBBko",
  "...ooooooooBBBBBBBBo",
  "..oBBBBBBBBBBoooooo.",
  "..oBBBLLLLLLBBo.....",
  "..oBBBLLLLLLBBo.....",
  "...oBBBBBBBBBo......",
];
const CL = "....ooDD..ooDD......";
const cat = {
  id: 'katze', num: 1, name: 'Tilde', art: 'Pixelkatze', w: 20, h: 16,
  palette: { o: '#2a1f2d', B: '#e59a4f', L: '#f8dcb0', D: '#a8622b', e: '#2a1f2d', p: '#f08aa0', k: 'B', lid: 'B', shut: 'o', w: '#ffffff' },
  frames: {
    stand: [...CAT_TOP, CL, CL, CL],
    walk: [
      [...CAT_TOP, CL, CL, "...ooDD..ooDD......."],
      [...CAT_TOP, CL, CL, CL],
      [...CAT_TOP, CL, CL, ".....ooDD..ooDD....."],
      [...CAT_TOP, CL, CL, CL],
    ],
    sit: [B(20), B(20), ...CAT_TOP, "...oooo...oooo......"],
    held: [
      [...CAT_TOP, CL, "....o.D...o.D.......", "....o.D...o.D......."],
      [...CAT_TOP, CL, "....o.D...o.D.......", ".....o.D...o.D......"],
    ],
  },
  walkHop: [0, 0, 0, 0],
  breathRow: { stand: 10, sit: 12 },
  anchors: { hand: { x: 10, y: 8 }, helm: { x: 11, y: 0 }, lupe: { x: 16, y: 8 }, sweat: { x: 19, y: 1 } },
  glassColor: '#1d1f27', crt: false,
};

// ---------- 2  Glibber (Schleimwesen) 16x14 ----------
const SL = [
  "................",
  "................",
  "......oooo......",
  "....ooBBBBoo....",
  "...oBBBBBBLLo...",
  "..oBBBBBBBBLLo..",
  "..oBBBBBBBBBBo..",
  ".oBBeeBBBBeeBBo.",
  ".oBBeeBBBBeeBBo.",
  ".oBkBBBBBBBBkBo.",
  ".oBBBBBDDBBBBBo.",
  ".oDBBBBBBBBBBDo.",
  "..oDDDDDDDDDDo..",
  "...oooooooooo...",
];
const SL_SQUASH = [B(16), ...SL.slice(0, 5), ...SL.slice(6, 12), ".oDDDDDDDDDDDDo.", "..oooooooooooo.."];
const SL_SIT = [B(16), ...SL_SQUASH.slice(0, 6), ...SL_SQUASH.slice(7)];
const slime = {
  id: 'schleim', num: 2, name: 'Glibber', art: 'Schleimwesen', w: 16, h: 14,
  palette: { o: '#5a2233', B: '#f2849e', L: '#ffd6df', D: '#c95a74', e: '#3a1420', k: 'B', lid: 'B', shut: 'e', w: '#ffffff' },
  frames: {
    stand: SL,
    walk: [SL_SQUASH, SL],
    sit: SL_SIT,
    held: [
      [...SL.slice(1), "....DD....DD...."],
      [...SL.slice(1), ".....DD..DD....."],
    ],
  },
  walkHop: [0, -2],
  breathRow: { stand: 6, sit: 11 },
  anchors: { hand: { x: 8, y: 2 }, helm: { x: 4, y: 0 }, lupe: { x: 12, y: 6 }, sweat: { x: 13, y: 2 } },
  glassColor: '#3a1420', crt: false,
};

// ---------- 3  Tinte (Mini-Krake) 16x16 ----------
const OC_TOP = [
  "................",
  ".....oooooo.....",
  "...ooBBBBBBoo...",
  "..oBBBBBBBLLBo..",
  "..oBBBBBBBBLBo..",
  ".oBBBBBBBBBBBBo.",
  ".oBBeeBBBBeeBBo.",
  ".oBBeeBBBBeeBBo.",
  ".oBkBBBBBBBBkBo.",
  ".oBBBBBDDBBBBBo.",
  "..oBBBBBBBBBBo..",
  ".oBBBBBBBBBBBBo.",
];
const T = ".oBo.oBooBo.oBo.";
const octo = {
  id: 'krake', num: 3, name: 'Tinte', art: 'Mini-Krake', w: 16, h: 16,
  palette: { o: '#191c3f', B: '#5b6ee1', L: '#aab6ff', D: '#3d49ad', e: '#0d0f2b', k: 'B', lid: 'B', shut: 'e', w: '#ffffff' },
  frames: {
    stand: [...OC_TOP, T, T, T, "..o...o..o...o.."],
    walk: [
      [...OC_TOP, T, T, "oBo..oBooBo..oBo", ".o....o..o....o."],
      [...OC_TOP, T, T, T, "..o...o..o...o.."],
      [...OC_TOP, T, T, "..oBooBooBooBo..", "...o..o..o..o..."],
      [...OC_TOP, T, T, T, "..o...o..o...o.."],
    ],
    sit: [B(16), B(16), ...OC_TOP, "oBBo.oBooBo.oBBo", ".oo..oo..oo..oo."],
    held: [
      [...OC_TOP, T, T, T, "..o...o..o...o.."],
      [...OC_TOP, T, T, T, ".o....o..o....o."],
    ],
  },
  walkHop: [0, -1, 0, -1],
  breathRow: { stand: 5, sit: 7 },
  anchors: { hand: { x: 8, y: 1 }, helm: { x: 4, y: -1 }, lupe: { x: 13, y: 7 }, sweat: { x: 13, y: 1 } },
  glassColor: '#eef0ff', crt: false,
};

// ---------- 4  Bit (Terminalwesen) 16x16 ----------
const BT_TOP = [
  "................",
  "..oooooooooooo..",
  ".oBBBBBBBBBBBBo.",
  ".oBSSSSSSSSSSBo.",
  ".oBSSSSSSSSSSBo.",
  ".oBSSeeSSSeeSBo.",
  ".oBSSeeSSSeeSBo.",
  ".oBSSkSSSSSkSBo.",
  ".oBSSSSMMSSCSBo.",
  ".oBSSSSSSSSSSBo.",
  ".oBBBBBBBBBBBBo.",
  "..oooooooooooo..",
  "......oBBo......",
  "....oooooooo....",
];
const BL = "....oo....oo....";
const bit = {
  id: 'bit', num: 4, name: 'Bit', art: 'Terminalwesen', w: 16, h: 16,
  palette: { o: '#0a1a10', B: '#2e4a36', S: '#07130c', e: '#5dff8f', M: 'e', C: 'e', k: 'S', lid: 'S', shut: 'e', w: '#e6ffee' },
  noTweak: true,
  variantPalette: {
    faul: { e: '#ffb000', w: '#fff1c9', B: '#4a3f24' },
    neugierig: {},
    verspielt: { e: '#55e6ff', w: '#e6fbff', B: '#24454c' },
    aengstlich: { e: '#c9ffd9', B: '#46584c' },
  },
  frames: {
    stand: [...BT_TOP, BL, BL],
    walk: [
      [...BT_TOP, BL, "...oo......oo..."],
      [...BT_TOP, BL, BL],
      [...BT_TOP, BL, ".....oo..oo....."],
      [...BT_TOP, BL, BL],
    ],
    sit: [B(16), B(16), ...BT_TOP],
    held: [
      [...BT_TOP, "....o......o....", "....o......o...."],
      [...BT_TOP, "....o......o....", ".....o....o....."],
    ],
  },
  walkHop: [0, 0, 0, 0],
  breathRow: { stand: 4, sit: 6 },
  anchors: { hand: { x: 8, y: 1 }, helm: { x: 4, y: -2 }, lupe: { x: 13, y: 7 }, sweat: { x: 14, y: 0 } },
  glassColor: '#d9ffe5', crt: true,
};

// ---------- 5  Pieps (Spatz) 16x16 ----------
const PI_TOP = [
  "................",
  "........o.......",
  ".....oooooo.....",
  "....oBBBBBBo....",
  "...oBBBBBBBBo...",
  "...oBeeBBeeBo...",
  "...oBeeBBeeBo...",
  "..oBkBBppBBkBo..",
  "..oDBBBpBBBBDo..",
  ".oDDBLLLLLLBDDo.",
  ".oDDBLLLLLLBDDo.",
  "..oDBLLLLLLBDo..",
  "...oBBLLLLBBo...",
  "....oooooooo....",
];
const PL = "......p..p......", PF = ".....pp.pp......";
const PI_WING_UP = { 8: ".oDDBBBpBBBBDDo.", 9: "oDDDBLLLLLLBDDDo" };
const PI_WING_DN = { 10: "oDDDBLLLLLLBDDDo", 11: ".oDDBLLLLLLBDDo." };
const withRows = (rows, repl) => rows.map((r, i) => repl[i] !== undefined ? repl[i] : r);
const sparrow = {
  id: 'spatz', num: 5, name: 'Pieps', art: 'Spatz', w: 16, h: 16,
  palette: { o: '#3b2a1e', B: '#a9744a', L: '#f1e2c8', D: '#6e4529', e: '#22160e', p: '#f0a030', k: 'B', lid: 'B', shut: 'e', w: '#ffffff' },
  frames: {
    stand: [...PI_TOP, PL, PF],
    walk: [
      [...PI_TOP, PL, "....pp....pp...."],
      [...PI_TOP, "......pppp......", B(16)],
    ],
    sit: [B(16), B(16), ...PI_TOP],
    held: [
      [...withRows(PI_TOP, PI_WING_UP), PL, PL],
      [...withRows(PI_TOP, PI_WING_DN), PL, PL],
    ],
  },
  walkHop: [0, -3],
  breathRow: { stand: 10, sit: 12 },
  anchors: { hand: { x: 8, y: 2 }, helm: { x: 4, y: 0 }, lupe: { x: 12, y: 8 }, sweat: { x: 12, y: 2 } },
  glassColor: '#22160e', crt: false,
};

// ---------- 6  Hütchen (Pilzwesen) 16x16 ----------
const MU_TOP = [
  "................",
  ".....oooooo.....",
  "...ooBBLLBBoo...",
  "..oBBBBBBBBLLo..",
  ".oBLLBBBBBBBLBo.",
  ".oBLLBBBLLBBBBo.",
  "oDDDDDDDDDDDDDDo",
  "...oSSSSSSSSo...",
  "...oSeeSSeeSo...",
  "...oSeeSSeeSo...",
  "...okSSooSSko...",
  "...oSSSSSSSSo...",
  "...oSSSSSSSSo...",
  "....oooooooo....",
];
const MF = ".....oo..oo.....";
const mushroom = {
  id: 'pilz', num: 6, name: 'Hütchen', art: 'Pilzwesen', w: 16, h: 16,
  palette: { o: '#3a1414', B: '#d9453b', L: '#fff4e6', D: '#cfa68c', S: '#f3e3c6', e: '#2a1a12', k: 'S', lid: 'S', shut: 'e', w: '#ffffff' },
  frames: {
    stand: [...MU_TOP, MF, MF],
    walk: [
      [...MU_TOP, MF, "....oo....oo...."],
      [...MU_TOP, MF, MF],
      [...MU_TOP, MF, "......oooo......"],
      [...MU_TOP, MF, MF],
    ],
    sit: [B(16), B(16), ...MU_TOP],
    held: [
      [...MU_TOP, ".....o....o.....", ".....o....o....."],
      [...MU_TOP, ".....o....o.....", "......o..o......"],
    ],
  },
  walkHop: [0, -1, 0, -1],
  breathRow: { stand: 11, sit: 13 },
  anchors: { hand: { x: 8, y: 1 }, helm: { x: 4, y: -2 }, lupe: { x: 12, y: 9 }, sweat: { x: 13, y: 7 } },
  glassColor: '#2a1a12', crt: false,
};

// ---------- 7  Kiemchen (Axolotl) 20x15 ----------
const AX_TOP = [
  "....................",
  "..p..............p..",
  ".pp..oooooooooo..pp.",
  "..pp.oBBBBBBBBo.pp..",
  "pp..oBBBBBBBBBBo..pp",
  ".ppoBBeeBBBBeeBBopp.",
  "...oBBeeBBBBeeBBo...",
  "..ppoBkBBooBBkBo.pp.",
  "....oBBBBBBBBBBo....",
  ".....oBBLLLLBBo.oo..",
  "....oBBLLLLLLBBoBBo.",
  "....oBBBBBBBBBBoo...",
  ".....oooooooooo.....",
];
const AL1 = "......BB....BB......", AL2 = "......oo....oo......";
const axolotl = {
  id: 'axolotl', num: 7, name: 'Kiemchen', art: 'Axolotl', w: 20, h: 15,
  palette: { o: '#5a2a3a', B: '#f7b6c8', L: '#fde3ea', D: '#e8578a', p: '#e8578a', e: '#2a1420', k: 'B', lid: 'B', shut: 'e', w: '#ffffff' },
  frames: {
    stand: [...AX_TOP, AL1, AL2],
    walk: [
      [...AX_TOP, ".....BB......BB.....", ".....oo......oo....."],
      [...AX_TOP, AL1, AL2],
      [...AX_TOP, ".......BB..BB.......", ".......oo..oo......."],
      [...AX_TOP, AL1, AL2],
    ],
    sit: [B(20), B(20), ...AX_TOP],
    held: [
      [...AX_TOP, ".......B....B.......", ".......B....B......."],
      [...AX_TOP, ".......B....B.......", "......B......B......"],
    ],
  },
  walkHop: [0, 0, 0, 0],
  breathRow: { stand: 8, sit: 10 },
  anchors: { hand: { x: 10, y: 2 }, helm: { x: 6, y: -1 }, lupe: { x: 16, y: 8 }, sweat: { x: 15, y: 1 } },
  glassColor: '#5a2a3a', crt: false,
};

// ---------- 8  Klammerich (lebendiges Klammer-Paar) 18x16 ----------
const KL_TOP = [
  "..................",
  "...ooo......ooo...",
  "..oBBo......oBBo..",
  "..oBo........oBo..",
  "..oBo........oBo..",
  ".oBo..ee..ee..oBo.",
  "oBo...ee..ee...oBo",
  ".oBo..k....k..oBo.",
  "..oBo...MM...oBo..",
  "..oBo........oBo..",
  "..oBBo......oBBo..",
  "...ooo......ooo...",
];
const KLeg = "....o........o....";
const braces = {
  id: 'klammer', num: 8, name: 'Klammerich', art: 'Klammer-Paar { }', w: 18, h: 16,
  palette: { o: '#2a1036', B: '#d77bff', e: '#c45cf0', M: 'e', k: '', lid: '', shut: 'e', w: '#ffffff' },
  frames: {
    stand: [...KL_TOP, KLeg, KLeg, KLeg, "...oo........oo..."],
    walk: [
      [...KL_TOP, KLeg, KLeg, "...o..........o...", "..oo..........oo.."],
      [...KL_TOP, KLeg, KLeg, KLeg, "...oo........oo..."],
      [...KL_TOP, KLeg, KLeg, ".....o......o.....", ".....oo.....oo...."],
      [...KL_TOP, KLeg, KLeg, KLeg, "...oo........oo..."],
    ],
    sit: [B(18), B(18), ...KL_TOP, KLeg, "...oo........oo..."],
    held: [
      [...KL_TOP, KLeg, KLeg, KLeg, KLeg],
      [...KL_TOP, KLeg, KLeg, KLeg, ".....o......o....."],
    ],
  },
  walkHop: [0, -1, 0, -1],
  breathRow: { stand: 3, sit: 5 },
  anchors: { hand: { x: 4, y: 2 }, helm: { x: 5, y: 0 }, lupe: { x: 14, y: 7 }, sweat: { x: 12, y: 2 } },
  glassColor: '#9a5cd6', crt: false,
};

const overlays = {
  cheekPink: '#ff7fa6',
  heart: { map: ["rr.rr", "rrrrr", ".rrr.", "..r.."], colors: { r: '#ff5c8a' } },
  zzz: { map: ["zzzz", "..z.", ".z..", "zzzz"], colors: { z: '#8a93e6' } },
  sweat: { map: [".b", "bb", "bb"], colors: { b: '#7cc7ff' } },
  hand: { map: ["..oo..", ".oWWo.", ".oWWo.", ".oWWo.", "oWWWWo", ".oooo."], colors: { o: '#3a2a22', W: '#ffe0c2' } },
  helm: { map: ["..oooo..", ".oyYyyo.", "oyyyyyyo", "oooooooo"], colors: { o: '#4a3a10', y: '#f5c518', Y: '#fff1a8' } },
  lupe: { map: [".ooo...", "ogGgo..", "ogggo..", ".oooh..", "....hh.", ".....hh", "......h"], colors: { o: '#2b2b33', g: '#bfe6ff', G: '#ffffff', h: '#8a5a2b' } },
  eggshell: { shell: '#f4ecd8', outline: '#8b7b5a' },
};

const variants = {
  faul:       { label: 'Faul',       eyes: 'half',   tweak: { h: 0,  s: -0.18, l: -0.06 } },
  neugierig:  { label: 'Neugierig',  eyes: 'glint',  tweak: { h: 0,  s: 0,     l: 0 } },
  verspielt:  { label: 'Verspielt',  eyes: 'normal', tweak: { h: 10, s: 0.12,  l: 0.03 } },
  aengstlich: { label: 'Ängstlich',  eyes: 'small',  tweak: { h: -6, s: -0.25, l: 0.10 } },
};

// Augenmodi: Reihenfolge der 2x2-Augenpixel = oben links, oben rechts, unten links, unten rechts
const eyeModes = {
  normal: ['e', 'e', 'e', 'e'],
  glint:  ['w', 'e', 'e', 'e'],
  half:   ['lid', 'lid', 'e', 'e'],
  small:  ['lid', 'lid', 'e', 'lid'],
  closed: ['lid', 'lid', 'shut', 'shut'],
  happy:  ['shut', 'shut', 'lid', 'lid'],
};

const rules = {
  grid: "Jede Zeile ist ein String, jedes Zeichen ein Pixel. '.' = transparent, sonst Schlüssel in palette. Figuren schauen nach rechts; nach links = horizontal spiegeln. Fußpunkt = Mitte der untersten Rasterzeile.",
  paletteRefs: "Ein Paletteneintrag mit genau einem Zeichen ist ein Verweis auf einen anderen Schlüssel (z.B. k:'B'). Nach Charakter-Anpassung auflösen. Ein leerer Eintrag ('') bedeutet transparent (Klammerich: Augenlid und Bäckchen unsichtbar).",
  variantTweak: "Außer bei noTweak: B, L, D in HSL verschieben (h in Grad, s/l additiv, auf 0..1 begrenzt). Danach variantPalette[variant] darüberlegen. Verspielt (und Zustand happy): k = overlays.cheekPink.",
  eyes: "Augen = jeder 2x2-Block aus 'e'. Modus pro Block über eyeModes ersetzen. Modus: Charakter (variants[v].eyes); Zustand überschreibt: sleep=closed, happy=happy, held/fall=glint (ängstlich: small), Blinzeln im Ruhezustand alle ~3,7 s für 130 ms = closed.",
  breathing: "In idle/sit/sleep/happy jede zweite Phase (850 ms, Schlaf 1300 ms): Zeile breathRow[stand|sit] löschen und oben eine leere Zeile einfügen.",
  walk: "walk-Frames alle 150 ms weiter; walkHop[i] = vertikaler Versatz in Rasterpixeln (negativ = hoch).",
  cursor: "Zeichen 'C' (nur Bit) blinkt: 500 ms an, 500 ms als 'S'.",
  crt: "crt=true: unter jedes Pixel einen Streifen rgba(0,0,0,.28) mit Höhe max(1, s/4) legen (Scanline).",
  happy: "Zustand happy: abwechselnd 260 ms um 2 Rasterpixel hochhüpfen, Herzchen über dem Kopf aufsteigen lassen.",
  held: "Zustand held: held-Frames alle 240 ms wechseln; overlays.hand mit Unterkante-Mitte auf anchors.hand zeichnen (oben links = hand.x-3, hand.y-5). Freier Fall nutzt dieselben Frames ohne Hand.",
  glasses: "Brille: um jeden Augenblock einen 4x4-Ring (ohne Ecken-Logik, alle Randpixel) in glassColor, dazu eine Brücke in der oberen Augenzeile zwischen beiden Ringen.",
  helm: "Bauhelm: overlays.helm mit oben links auf anchors.helm.",
  lupe: "Lupe: overlays.lupe mit oben links auf anchors.lupe.",
  sweat: "Ängstlich (außer im Schlaf): overlays.sweat bei anchors.sweat, wippt 1 px.",
  growth: "Baby = Pixelgröße 2 + Eierschale über den unteren 4-5 Zeilen (Zickzack-Kante, overlays.eggshell), Jung = 3, Erwachsen = 4 (bei gleicher Darstellung).",
};

const data = { version: 1, creatures: [cat, slime, octo, bit, sparrow, mushroom, axolotl, braces], overlays, variants, eyeModes, rules };

// ---------- Prüfung ----------
let errors = 0;
for (const c of data.creatures) {
  const keys = new Set(Object.keys(c.palette));
  const check = (rows, label) => {
    if (rows.length !== c.h) { console.error(`${c.id} ${label}: ${rows.length} Zeilen statt ${c.h}`); errors++; }
    rows.forEach((r, i) => {
      if (r.length !== c.w) { console.error(`${c.id} ${label} Zeile ${i}: Länge ${r.length} statt ${c.w}: "${r}"`); errors++; }
      for (const ch of r) if (ch !== '.' && !keys.has(ch)) { console.error(`${c.id} ${label} Zeile ${i}: unbekanntes Zeichen '${ch}'`); errors++; }
    });
  };
  check(c.frames.stand, 'stand');
  c.frames.walk.forEach((f, i) => check(f, 'walk' + i));
  check(c.frames.sit, 'sit');
  c.frames.held.forEach((f, i) => check(f, 'held' + i));
  if (c.walkHop.length !== c.frames.walk.length) { console.error(`${c.id}: walkHop passt nicht`); errors++; }
  // Augenblöcke zählen
  const eyes = (rows) => { let n = 0; for (let y = 0; y < rows.length - 1; y++) for (let x = 0; x < rows[y].length - 1; x++) if (rows[y][x] === 'e' && rows[y][x + 1] === 'e' && rows[y + 1][x] === 'e' && rows[y + 1][x + 1] === 'e') n++; return n; };
  for (const [lbl, rows] of [['stand', c.frames.stand], ['sit', c.frames.sit]]) {
    const n = eyes(rows); if (n !== 2) { console.error(`${c.id} ${lbl}: ${n} Augenblöcke statt 2`); errors++; }
  }
}
if (errors) { console.error(errors + ' Fehler'); process.exit(1); }

const json = JSON.stringify(data);
fs.writeFileSync(path.join(dir, 'pet-data.json'), JSON.stringify(data, null, 1));
const tpl = fs.readFileSync(path.join(dir, 'template.html'), 'utf8');
if (!tpl.includes('__PET_DATA__')) { console.error('Platzhalter fehlt'); process.exit(1); }
fs.writeFileSync(path.join(dir, 'claude-pet-entwuerfe.html'), tpl.replace('__PET_DATA__', json.replace(/</g, '\\u003c')));
console.log('ok', json.length, 'Bytes Daten');
