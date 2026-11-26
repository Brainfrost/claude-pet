// claude-pet: Terminal – gibt die Terminal-Ausgabe von Claude Code an das claude-pet weiter.
//
// Warum: VS Code/Cursor zeichnen das Terminal auf ein Canvas; von außen ist der Text nicht lesbar.
// Die Erweiterung liest die Ausgabe von `claude`-Aufrufen über die Shell-Integration mit und schickt
// sie über einen lokalen Kanal (Named Pipe unter Windows, Unix-Socket auf dem Mac) an das Pet.
// Nichts wird gespeichert oder ins Netz geschickt. Läuft das Pet nicht, passiert nichts.
'use strict';
const vscode = require('vscode');
const net = require('net');
const os = require('os');
const path = require('path');

const fs = require('fs');

const RING_CHARS = 256 * 1024;      // so viel Ausgabe je Terminal wird für ein (später) startendes Pet gehalten
const RETRY_MS = 3000;
const CLAUDE = /(^|[\s"'\/\\&;|])claude(-code)?(\.exe|\.cmd|\.ps1)?(?=$|[\s"';|&])/i;
const TITLE = /\x1b\][02];([^\x07\x1b]*)(?:\x07|\x1b\\)/g;

// Datenordner des Pets (nur für den eigenen Benutzer lesbar)
function dataDir() {
  if (process.platform === 'win32') {
    return path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'), 'claude-pet');
  }
  if (process.platform === 'darwin') return path.join(os.homedir(), 'Library', 'Application Support', 'claude-pet');
  return path.join(process.env.XDG_DATA_HOME || path.join(os.homedir(), '.local', 'share'), 'claude-pet');
}

// Das Pet würfelt bei jedem Start einen Kanalnamen und legt ihn im Datenordner ab. Nur einem Kanal
// vertrauen, der dort steht und die erwartete Form hat – sonst nichts senden.
function channel() {
  let ch;
  try { ch = fs.readFileSync(path.join(dataDir(), 'channel'), 'utf8').trim(); } catch (e) { return null; }
  if (process.platform === 'win32') {
    return /^\\\\\.\\pipe\\claude-pet-[A-Za-z0-9_.-]+-[0-9a-f]{16}$/.test(ch) ? ch : null;
  }
  const dir = dataDir() + path.sep;
  return ch.startsWith(dir) && /^ch-[0-9a-f]{16}\.sock$/.test(ch.slice(dir.length)) ? ch : null;
}

let sock = null;
let alive = false;
let disposed = false;
let nextId = 1;
const terms = new Map();             // vscode.Terminal -> Zustand

function stateOf(term) {
  let t = terms.get(term);
  if (!t) {
    t = { id: 't' + nextId++, ring: [], size: 0, title: '', cmd: '', dims: null, exec: null, running: false };
    terms.set(term, t);
  }
  return t;
}

function send(msg) {
  if (alive && sock) {
    try { sock.write(JSON.stringify(msg) + '\n'); } catch (e) { /* Kanal weg: close-Handler verbindet neu */ }
  }
}

function hello() {
  send({ type: 'hello', version: 1, app: vscode.env.appName, workspace: vscode.workspace.name || '' });
}

function replay() {
  // Pet kam nach claude: bisherige Ausgabe (gekürzt) nachliefern, damit es den Bildschirm kennt
  for (const t of terms.values()) {
    if (!t.cmd) continue;
    send({ type: 'start', term: t.id, cmd: t.cmd, dims: t.dims, title: t.title, replay: true });
    if (t.ring.length) send({ type: 'data', term: t.id, d: t.ring.join('') });
    if (!t.running) send({ type: 'end', term: t.id });
  }
  const act = vscode.window.activeTerminal;
  send({ type: 'active', term: act && terms.has(act) ? terms.get(act).id : null });
}

function connect() {
  if (disposed || sock) return;
  const ch = channel();
  if (!ch) { setTimeout(connect, RETRY_MS); return; }      // Pet läuft (noch) nicht
  const s = net.connect(ch);
  sock = s;
  s.on('connect', () => { alive = true; hello(); replay(); });
  s.on('error', () => { /* Pet läuft nicht – später nochmal */ });
  s.on('close', () => {
    if (sock === s) { sock = null; alive = false; }
    if (!disposed) setTimeout(connect, RETRY_MS);
  });
}

function remember(t, d) {
  t.ring.push(d);
  t.size += d.length;
  while (t.size > RING_CHARS && t.ring.length > 1) t.size -= t.ring.shift().length;
  let m;
  TITLE.lastIndex = 0;
  while ((m = TITLE.exec(d)) !== null) t.title = m[1];
}

async function guardScreenReaderMode(context) {
  // Das Pet liest Lage und Titel des Terminals über die Bedienungshilfen des Systems. Steht VS Code auf
  // "auto", hält es das für einen Screenreader und schaltet in den Screenreader-Modus. Einmal fragen.
  const KEY = 'claudePet.askedScreenReader';
  const cfg = vscode.workspace.getConfiguration('editor');
  if (cfg.get('accessibilitySupport') !== 'auto' || context.globalState.get(KEY)) return;
  await context.globalState.update(KEY, true);
  const yes = 'Auf „off“ stellen';
  const pick = await vscode.window.showInformationMessage(
    'claude-pet liest das Terminal über die Bedienungshilfen. Damit VS Code dadurch nicht in den ' +
    'Screenreader-Modus schaltet, empfiehlt sich „editor.accessibilitySupport: off“ (falls du keinen ' +
    'Screenreader benutzt).', yes, 'Nein danke');
  if (pick === yes) await cfg.update('accessibilitySupport', 'off', vscode.ConfigurationTarget.Global);
}

function activate(context) {
  const subs = context.subscriptions;
  guardScreenReaderMode(context).catch(() => {});

  subs.push(vscode.window.onDidStartTerminalShellExecution(async (e) => {
    const cmd = (e.execution.commandLine && e.execution.commandLine.value) || '';
    if (!CLAUDE.test(cmd)) return;
    const t = stateOf(e.terminal);
    Object.assign(t, { ring: [], size: 0, cmd, dims: e.terminal.dimensions || null, exec: e.execution, running: true });
    send({ type: 'start', term: t.id, cmd, dims: t.dims, title: t.title });
    if (vscode.window.activeTerminal === e.terminal) send({ type: 'active', term: t.id });
    try {
      for await (const d of e.execution.read()) {
        remember(t, d);
        send({ type: 'data', term: t.id, d });
      }
    } catch (err) { /* Strom abgebrochen */ }
  }));

  subs.push(vscode.window.onDidEndTerminalShellExecution((e) => {
    const t = terms.get(e.terminal);
    if (t && t.exec === e.execution) {
      t.running = false;
      send({ type: 'end', term: t.id });
    }
  }));

  subs.push(vscode.window.onDidCloseTerminal((term) => {
    const t = terms.get(term);
    if (t) {
      send({ type: 'closed', term: t.id });
      terms.delete(term);
    }
  }));

  subs.push(vscode.window.onDidChangeActiveTerminal((term) => {
    send({ type: 'active', term: term && terms.has(term) ? terms.get(term).id : null });
  }));

  subs.push({ dispose: () => { disposed = true; if (sock) sock.destroy(); } });
  connect();
}

function deactivate() {
  disposed = true;
  if (sock) sock.destroy();
}

module.exports = { activate, deactivate };
