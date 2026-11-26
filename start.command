#!/bin/bash
# claude-pet starten (macOS) – über launchd, damit die Freigabe „Bedienungshilfen“ immer greift.
cd "$(dirname "$0")" || exit 1
LABEL="com.claude-pet"
PLIST="$(.venv/bin/python -m claude_pet.settings --agent)" || { echo "Erst install.command ausführen."; exit 1; }
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null
launchctl kickstart -k "gui/$(id -u)/$LABEL" && echo "claude-pet gestartet."
