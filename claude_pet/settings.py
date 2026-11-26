"""Einstellungen (gelten fürs Gerät, nicht fürs einzelne Pet) und Autostart:
Windows über HKCU\\...\\Run, Mac über einen LaunchAgent (~/Library/LaunchAgents/com.claude-pet.plist)."""
import json
import os
import plistlib
import sys

from .paths import data_dir

if sys.platform == "win32":
    import winreg

DIR = data_dir()
PATH = os.path.join(DIR, "settings.json")
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS = {
    "size": "normal",            # klein | normal | gross
    "talk": "normal",            # aus | wenig | normal | viel
    "bubbles": True,
    "autostart": True,
    "quiet_calls": True,         # Ruhemodus, solange ein Programm das Mikrofon benutzt
    "quiet_fullscreen": True,    # Ruhemodus bei Vollbild/Präsentation
    "dnd": False,                # "Bitte nicht stören" (manuell)
    "break_reminder": True,      # Pausen-Erinnerung
    "break_minutes": 120,        # nach so vielen Minuten Arbeit am Stück
    "messenger": True,           # Bote: holt dich, wenn eine Session fertig ist und du woanders bist
    "seasons": True,             # Jahreszeiten: Schnee/Laub/Blüten auf den Textzeilen, Wintermütze
    "brain": "normal",           # Hirn: Haiku plant das Verhalten (aus | sparsam | normal)
}
SIZE_FACTOR = {"klein": 0.67, "normal": 1.0, "gross": 1.5}
TALK_FACTOR = {"aus": 0.0, "wenig": 0.5, "normal": 1.0, "viel": 1.6}

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "claude-pet"


def load():
    s = dict(DEFAULTS)
    try:
        with open(PATH, encoding="utf-8") as f:
            s.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return s


def save(s):
    os.makedirs(DIR, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    os.replace(tmp, PATH)


def autostart_command():
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pyw}" "{os.path.join(PROJECT, "run.pyw")}"'


# ------------------------------------------------------------------ Mac: LaunchAgent
AGENT_LABEL = "com.claude-pet"
AGENT_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{AGENT_LABEL}.plist")
_EXTRA_PATH = ("/opt/homebrew/bin", "/usr/local/bin", os.path.expanduser("~/.local/bin"),
               os.path.expanduser("~/.npm-global/bin"), "/usr/bin", "/bin", "/usr/sbin", "/sbin")


def launch_agent(run_at_load=True):
    """Inhalt des LaunchAgents. Gestartet wird das Pet immer über launchd (auch vom Installer), damit
    macOS die Freigabe „Bedienungshilfen“ stets demselben Programm (Python) zuordnet."""
    path = [p for p in os.environ.get("PATH", "").split(":") if p]
    path += [p for p in _EXTRA_PATH if p not in path]          # für `claude` (Haiku-Sprüche)
    return {
        "Label": AGENT_LABEL,
        "ProgramArguments": [sys.executable, os.path.join(PROJECT, "run.pyw")],
        "WorkingDirectory": PROJECT,
        "RunAtLoad": bool(run_at_load),
        "ProcessType": "Interactive",
        "EnvironmentVariables": {"PATH": ":".join(path)},
        "StandardErrorPath": data_dir("launchd.log"),
    }


def _write_agent(run_at_load):
    os.makedirs(os.path.dirname(AGENT_PATH), exist_ok=True)
    os.makedirs(data_dir(), exist_ok=True)
    with open(AGENT_PATH, "wb") as f:
        plistlib.dump(launch_agent(run_at_load), f)


def _read_agent():
    try:
        with open(AGENT_PATH, "rb") as f:
            return plistlib.load(f)
    except (OSError, plistlib.InvalidFileException):
        return None


# ------------------------------------------------------------------ gemeinsam
def set_autostart(on):
    if sys.platform == "darwin":
        _write_agent(on)            # die Datei bleibt (fürs Starten über launchd), nur RunAtLoad wechselt
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass


def autostart_enabled():
    if sys.platform == "darwin":
        a = _read_agent()
        return bool(a and a.get("RunAtLoad")
                    and a.get("ProgramArguments") == launch_agent()["ProgramArguments"])
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, RUN_NAME)[0] == autostart_command()
    except OSError:
        return False


if __name__ == "__main__":
    # Installer (Mac): `python -m claude_pet.settings --agent` schreibt den LaunchAgent
    if "--agent" in sys.argv:
        set_autostart(load().get("autostart", True))
        print(AGENT_PATH)
