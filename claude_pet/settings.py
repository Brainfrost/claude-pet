"""Einstellungen (gelten fürs Gerät, nicht fürs einzelne Pet) und Autostart über HKCU\\...\\Run."""
import json
import os
import sys
import winreg

DIR = os.path.join(os.environ.get("LOCALAPPDATA", "."), "claude-pet")
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


def set_autostart(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, RUN_NAME)[0] == autostart_command()
    except OSError:
        return False
