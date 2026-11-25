@echo off
rem Startet claude-pet ohne Konsolenfenster. Beenden: Tray-Symbol -> Beenden.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m claude_pet
