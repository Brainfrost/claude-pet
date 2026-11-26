#!/bin/bash
# claude-pet Diagnose (macOS): zeigt, was das Pet sieht. Ausgabe bitte weiterschicken.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then echo "Erst install.command ausführen."; read -r -p "Enter …" _; exit 1; fi
.venv/bin/python -m claude_pet.diagnose 2>&1 | tee "$HOME/Desktop/claude-pet-diagnose.txt"
echo
echo "(Auch gespeichert unter ~/Desktop/claude-pet-diagnose.txt)"
read -r -p "Enter zum Schließen …" _
