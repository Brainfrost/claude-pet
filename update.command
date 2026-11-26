#!/bin/bash
# claude-pet aktualisieren (macOS): neue Version holen (git pull), Pakete nachziehen, neu starten.
cd "$(dirname "$0")" || exit 1
printf "\033[35mclaude-pet – Update\033[0m\n"
if [ -d .git ]; then
    git pull --ff-only || { echo "  ✗ git pull fehlgeschlagen (lokale Änderungen?)"; read -r -p "Enter …" _; exit 1; }
else
    echo "  ! Kein git-Ordner – neue Version bitte als ZIP herunterladen und darüber entpacken."
fi
exec bash ./install.command
