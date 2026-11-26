"""Diagnose: Was sieht das Pet auf diesem Rechner? Ausgabe zum Weiterschicken.

    Windows:  .venv\\Scripts\\python -m claude_pet.diagnose
    Mac:      .venv/bin/python -m claude_pet.diagnose      (oder diagnose.command doppelklicken)

Liest nur – ändert nichts. Gibt keine Terminal-Inhalte aus, nur Fenster, Lagen und Titel.
"""
import importlib
import os
import platform
import sys
import time

OK, WARN, FAIL = "✓", "!", "✗"
_APP = None


def line(mark, text):
    print(f"  {mark} {text}")


def section(title):
    print(f"\n== {title}")


def check_packages():
    section("Python und Pakete")
    line(OK, f"Python {platform.python_version()} ({sys.executable})")
    mods = ["PyQt6.QtWidgets", "PyQt6.QtNetwork", "numpy", "pyte"]
    mods += ["comtypes"] if sys.platform == "win32" else ["Quartz", "AppKit", "ApplicationServices"]
    ok = True
    for m in mods:
        try:
            importlib.import_module(m)
            line(OK, m)
        except Exception as e:
            ok = False
            line(FAIL, f"{m}: {e}")
    return ok


def check_permissions():
    if sys.platform != "darwin":
        return True
    section("Freigaben (macOS)")
    from . import osapi
    trusted = osapi.accessibility_trusted()
    if trusted:
        line(OK, "Bedienungshilfen: erteilt")
    else:
        line(FAIL, "Bedienungshilfen: FEHLT – Systemeinstellungen → Datenschutz & Sicherheit → Bedienungshilfen → "
                   "„Python“ einschalten (ggf. mit + hinzufügen), dann Pet neu starten")
    return trusted


def check_pet():
    section("Pet")
    from .paths import data_dir
    from .streams import channel_name
    line(OK, f"Datenordner: {data_dir()}")
    log = data_dir("pet.log")
    if os.path.exists(log):
        age = time.time() - os.path.getmtime(log)
        line(OK if age < 120 else WARN, f"Log zuletzt geschrieben vor {age:.0f} s: {log}")
        try:
            with open(log, encoding="utf-8", errors="replace") as f:
                tail = f.readlines()[-400:]
            for marker in ("Kanal für VS Code", "VS-Code-Erweiterung verbunden", "VS Code/Cursor (Fenster",
                           "Bedienungshilfen", "Pet zieht um", "abgestürzt", "Traceback"):
                hits = [t.strip() for t in tail if marker in t]
                if hits:
                    line(FAIL if marker in ("abgestürzt", "Traceback") else OK, "Log: " + hits[-1][:160])
        except OSError:
            pass
    else:
        line(WARN, "noch kein Log – lief das Pet schon einmal?")
    from PyQt6.QtNetwork import QLocalSocket
    sock = QLocalSocket()
    sock.connectToServer(channel_name())
    if sock.waitForConnected(800):
        line(OK, f"Pet läuft, Kanal für VS Code/Cursor offen ({channel_name()})")
        sock.disconnectFromServer()
    else:
        line(FAIL, f"Kanal nicht erreichbar ({channel_name()}) – läuft das Pet?")


def check_extension():
    section("Erweiterung „claude-pet: Terminal“")
    from . import vsix
    eds = vsix.editors()
    if not eds:
        line(WARN, "kein VS Code / Cursor gefunden")
    ext = vsix.extension_id()
    for name, cli in eds.items():
        ok, out = vsix._run(cli, "--list-extensions", "--show-versions")
        hit = [x for x in out.splitlines() if x.lower().startswith(ext.lower())]
        line(OK if hit else FAIL, f"{name}: " + (hit[0] if hit else "nicht installiert – `python -m claude_pet.vsix`"))


def check_terminals():
    section("Terminals in VS Code / Cursor (was das Pet sieht)")
    from . import osapi
    if sys.platform == "win32":
        sys.coinit_flags = 0
        import comtypes.client
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as U
        from .vscode import UIAScanner
        uia = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)
        scanner = UIAScanner(uia, U)
    else:
        import logging
        logging.basicConfig(level=logging.INFO, format="    (log) %(message)s")
        from .macax import AXScanner
        scanner = AXScanner()
    wins = scanner.windows()
    if not wins:
        line(WARN, "kein sichtbares VS-Code-/Cursor-Fenster (nicht minimiert, auf diesem Schreibtisch)")
        return
    fg = osapi.foreground_window()
    for h in wins:
        title = osapi.window_title(h)
        line(OK, f"Fenster {h}{' (vorne)' if h == fg else ''}: {title or '(Titel unbekannt)'}  {osapi.window_rect(h)}")
        t0 = time.perf_counter()
        screens, tas, tab = scanner.read(h)
        if not screens and sys.platform == "darwin":
            time.sleep(1.0)                  # Electron baut den Baum nach dem Einschalten erst auf
            scanner.clear()
            screens, tas, tab = scanner.read(h)
        ms = (time.perf_counter() - t0) * 1000
        if screens:
            line(OK, f"  {len(screens)} Terminal-Fläche(n) ({ms:.0f} ms): {screens}")
        else:
            line(FAIL, f"  keine Terminal-Fläche gefunden ({ms:.0f} ms) – Terminal-Panel offen?")
        for r, name in tas:
            line(OK, f"  Eingabefeld {r}: {name[:90]!r}")
        if tab:
            line(OK, f"  Terminal-Reiter: {tab}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    print(f"claude-pet Diagnose – {platform.system()} {platform.release()} ({platform.machine()})")
    global _APP
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication([])     # für Bildschirm-Infos und QLocalSocket
    steps = [check_packages, check_permissions, check_pet, check_extension, check_terminals]
    for step in steps:
        try:
            step()
        except Exception as e:
            line(FAIL, f"{step.__name__}: {type(e).__name__}: {e}")
    print("\nFertig. Diese Ausgabe kannst du so weiterschicken (sie enthält keine Terminal-Inhalte).")


if __name__ == "__main__":
    main()
