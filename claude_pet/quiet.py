"""Ruhemodus-Erkennung: Call (ein Programm benutzt das Mikrofon) oder Vollbild/Präsentation.

Mikrofon: Windows führt unter CapabilityAccessManager\\ConsentStore\\microphone pro App
LastUsedTimeStart/-Stop. Solange eine App das Mikrofon benutzt, ist LastUsedTimeStop = 0.
Mac: Vollbild über die Fensterliste; eine Mikrofon-Erkennung gibt es dort (noch) nicht.
"""
import ctypes
import sys

from . import osapi

if sys.platform == "win32":
    import ctypes.wintypes as wt
    import winreg

MIC = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"

# SHQueryUserNotificationState: 3 = D3D-Vollbild (Spiele/Videos), 4 = Präsentationsmodus.
# (2 = "irgendein Vollbild-Fenster" wird NICHT benutzt: das meldet Windows auch für unsere eigenen
#  durchsichtigen Overlays über allen Bildschirmen – stattdessen prüfen wir das aktive Fenster selbst.)
_BUSY_STATES = {3, 4}
_SHELL = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
          "Finder", "Dock", "Window Server"}          # Mac: Programmnamen statt Fensterklassen


def _foreground():
    """(pid, Klasse, Fensterrechteck, Monitorrechteck) des aktiven Fensters, oder None."""
    h = osapi.foreground_window()
    if not h:
        return None
    if sys.platform != "win32":
        scr = osapi.screen_of_window(h)
        if scr is None:
            return None
        return osapi.window_pid(h), osapi.class_name(h), scr[0], scr[1]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]

    mon = ctypes.windll.user32.MonitorFromWindow(wt.HWND(h), 2)      # MONITOR_DEFAULTTONEAREST
    info = _MONITORINFO(ctypes.sizeof(_MONITORINFO))
    if not ctypes.windll.user32.GetMonitorInfoW(mon, ctypes.byref(info)):
        return None
    m = info.rcMonitor
    return osapi.window_pid(h), osapi.class_name(h), osapi.window_rect(h), (m.left, m.top, m.right, m.bottom)


def foreground_fullscreen(fg=None):
    """Bedeckt das aktive Fenster (eines anderen Programms) den ganzen Monitor inkl. Taskleiste?"""
    fg = fg if fg is not None else _foreground()
    if not fg:
        return False
    pid, cls, (l, t, r, b), (ml, mt, mr, mb) = fg
    if pid == osapi.OWN_PID or cls in _SHELL:
        return False
    return l <= ml and t <= mt and r >= mr and b >= mb


def _apps_using(root_path):
    out = []
    if sys.platform != "win32":
        return out
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
    if sys.platform != "win32":
        return foreground_fullscreen()
    state = ctypes.c_int(0)
    try:
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
            return False
    except (AttributeError, OSError):
        return False
    return state.value in _BUSY_STATES or foreground_fullscreen()


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
