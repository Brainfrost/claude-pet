#!/bin/bash
# claude-pet installieren (macOS): im Finder doppelklicken oder im Terminal `bash install.command`.
# Richtet eine eigene Python-Umgebung (.venv) ein, installiert die Erweiterung für VS Code/Cursor,
# legt den Autostart an (LaunchAgent) und startet das Pet. Admin-Rechte braucht es nicht.
set -u -o pipefail
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
LABEL="com.claude-pet"

step() { printf "\n\033[36m» %s\033[0m\n" "$1"; }
ok()   { printf "  \033[32m✓ %s\033[0m\n" "$1"; }
warn() { printf "  \033[33m! %s\033[0m\n" "$1"; }
fail() { printf "  \033[31m✗ %s\033[0m\n" "$1"; }
finish() { echo; read -r -p "Enter zum Schließen …" _; exit "$1"; }

printf "\033[35mclaude-pet – Installation (macOS)\033[0m\nOrdner: %s\n" "$ROOT"

# ------------------------------------------------------------------ 1. macOS
step "macOS"
VER="$(sw_vers -productVersion)"
MAJOR="${VER%%.*}"
ARCH="$(uname -m)"
if [ "$ARCH" = "x86_64" ] && [ "$MAJOR" -lt 14 ]; then
    fail "macOS $VER auf Intel: Qt (die Fenster-Bibliothek) braucht hier macOS 14 oder neuer."
    finish 1
fi
ok "macOS $VER ($ARCH)"

# ------------------------------------------------------------------ 2. Claude Code
step "Claude Code (claude)"
if command -v claude >/dev/null 2>&1; then
    ok "gefunden – die Sprechblasen nutzen Haiku über dein Claude-Abo"
else
    warn "claude ist nicht im PATH. Das Pet läuft trotzdem, sagt dann aber nur vorgefertigte Sprüche."
fi

# ------------------------------------------------------------------ 3. Python
step "Python 3.11 oder neuer"
PY=""
for c in python3.13 python3.12 python3.11 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
        PY="$(command -v "$c")"
        break
    fi
done
if [ -z "$PY" ]; then
    fail "kein passendes Python gefunden (das von macOS mitgelieferte ist zu alt)."
    echo "    Installieren mit Homebrew:  brew install python@3.12"
    echo "    oder von https://www.python.org/downloads/macos/ – danach install.command nochmal starten."
    finish 1
fi
ok "$("$PY" --version) ($PY)"

# ------------------------------------------------------------------ 4. Umgebung + Pakete
step "Python-Umgebung (.venv) und Pakete"
if [ ! -x .venv/bin/python ]; then
    "$PY" -m venv .venv || { fail "venv konnte nicht angelegt werden"; finish 1; }
    ok ".venv angelegt"
else
    ok ".venv vorhanden"
fi
VPY="$ROOT/.venv/bin/python"
"$VPY" -m pip install --disable-pip-version-check -q -r requirements.txt || { fail "Pakete konnten nicht installiert werden (Internet/Proxy?)"; finish 1; }
"$VPY" -c "import PyQt6.QtWidgets, numpy, pyte, Quartz, AppKit, ApplicationServices" || { fail "Pakete installiert, lassen sich aber nicht laden"; finish 1; }
ok "PyQt6, numpy, pyte, pyobjc bereit"

# ------------------------------------------------------------------ 5. VS Code / Cursor
step "Erweiterung für VS Code / Cursor"
if "$VPY" -m claude_pet.vsix | sed 's/^/  /'; then
    ok "installiert – läuft claude dort schon, einmal neu starten (/exit, dann claude)"
else
    warn "Erweiterung nicht (überall) installiert – ohne sie sieht das Pet in VS Code/Cursor keinen Text."
fi

# ------------------------------------------------------------------ 6. Autostart + Start
step "Autostart und Start"
pkill -f "$ROOT/run.pyw" 2>/dev/null
PLIST="$("$VPY" -m claude_pet.settings --agent)" || { fail "LaunchAgent konnte nicht angelegt werden"; finish 1; }
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null
launchctl kickstart -k "gui/$(id -u)/$LABEL" || { fail "Start über launchd fehlgeschlagen"; finish 1; }
ok "gestartet (Autostart: $PLIST)"

# ------------------------------------------------------------------ 7. Freigabe
step "Freigabe „Bedienungshilfen“"
echo "  Damit das Pet das Terminal in VS Code/Cursor findet, braucht es einmalig die Freigabe"
echo "  „Bedienungshilfen“. macOS zeigt dazu gleich einen Dialog – oder:"
echo "  Systemeinstellungen → Datenschutz & Sicherheit → Bedienungshilfen → „Python“ einschalten."
echo "  Danach das Pet neu starten: start.command (oder Menüleiste → Beenden, dann start.command)."
echo "  Bildschirmaufnahme braucht das Pet NICHT."
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null

echo
printf "\033[32mFertig!\033[0m\n"
echo "- Beim ersten Start öffnet sich das Adoptionsfenster: Figur aussuchen, Namen geben, adoptieren."
echo "- Das Pet sitzt oben in der Menüleiste (deine Figur). Klick darauf → Menü."
echo "- Klappt etwas nicht: diagnose.command doppelklicken und die Ausgabe weiterschicken."
finish 0
