"""Ruhemodus-Erkennung: Call (ein Programm benutzt das Mikrofon) oder Vollbild/Präsentation.

Mikrofon: Windows führt unter CapabilityAccessManager\\ConsentStore\\microphone pro App
LastUsedTimeStart/-Stop. Solange eine App das Mikrofon benutzt, ist LastUsedTimeStop = 0.
"""
import ctypes
import winreg

MIC = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"

# SHQueryUserNotificationState: 2 = Vollbild-App, 3 = D3D-Vollbild (Spiele/Videos), 4 = Präsentationsmodus
_BUSY_STATES = {2, 3, 4}


def _apps_using(root_path):
    out = []
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, root_path)
    except OSError:
        return out
    with root:
        i = 0
        while True:
            try:
                name = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            if name == "NonPackaged":
                out += _apps_using(root_path + "\\NonPackaged")
                continue
            try:
                with winreg.OpenKey(root, name) as k:
                    start = winreg.QueryValueEx(k, "LastUsedTimeStart")[0]
                    stop = winreg.QueryValueEx(k, "LastUsedTimeStop")[0]
                    if start and stop == 0:
                        out.append(name.split("#")[-1])
            except OSError:
                continue
    return out


def mic_users():
    """Apps, die gerade das Mikrofon benutzen (z.B. Teams, Zoom, Chrome bei Meet)."""
    return _apps_using(MIC)


def fullscreen_busy():
    state = ctypes.c_int(0)
    try:
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
            return False
    except (AttributeError, OSError):
        return False
    return state.value in _BUSY_STATES


def reason(settings):
    """Grund für den Ruhemodus als kurzer Text, oder None."""
    if settings.get("dnd"):
        return "Bitte nicht stören"
    if settings.get("quiet_calls"):
        users = mic_users()
        if users:
            return "Call (Mikrofon: " + ", ".join(sorted(set(u.rsplit(".", 1)[0][-24:] for u in users))) + ")"
    if settings.get("quiet_fullscreen") and fullscreen_busy():
        return "Vollbild/Präsentation"
    return None
