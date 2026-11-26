"""Wo das Pet seine Daten ablegt: Windows %LOCALAPPDATA%\\claude-pet, macOS ~/Library/Application Support/claude-pet."""
import os
import sys


def data_dir(*parts):
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "claude-pet", *parts)
