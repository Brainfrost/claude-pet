#!/bin/bash
# claude-pet entfernen (macOS): beendet das Pet, entfernt Autostart und Erweiterung, auf Wunsch die Daten.
cd "$(dirname "$0")" || exit 1
LABEL="com.claude-pet"
printf "\033[35mclaude-pet – Deinstallation\033[0m\n"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
pkill -f "$(pwd)/run.pyw" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "  ✓ Pet beendet, Autostart entfernt"
if [ -x .venv/bin/python ]; then
    .venv/bin/python -m claude_pet.vsix --remove >/dev/null 2>&1 && echo "  ✓ Erweiterung aus VS Code/Cursor entfernt"
fi
DATA="$HOME/Library/Application Support/claude-pet"
if [ -d "$DATA" ]; then
    echo
    echo "  In $DATA liegen dein Pet, sein Tagebuch, die Schatzkiste und die Einstellungen."
    read -r -p "  Auch diese Daten löschen? Dein Pet ist dann weg. [j/n] " a
    case "$a" in
        [jJyY]*) rm -rf "$DATA"; echo "  ✓ Daten gelöscht" ;;
        *) echo "  Daten bleiben – bei einer neuen Installation ist dein Pet wieder da." ;;
    esac
fi
echo
echo "Fertig. Den Ordner $(pwd) kannst du jetzt löschen."
echo "Die Freigabe „Bedienungshilfen“ für Python kannst du in den Systemeinstellungen entfernen."
read -r -p "Enter zum Schließen …" _
