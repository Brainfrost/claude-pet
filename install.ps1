# claude-pet installieren: prüft die Voraussetzungen, richtet die Python-Umgebung ein und startet das Pet.
# Aufruf: install.cmd doppelklicken (oder: powershell -ExecutionPolicy Bypass -File install.ps1)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Write-Step($text) { Write-Host ""; Write-Host "» $text" -ForegroundColor Cyan }
function Write-Ok($text) { Write-Host "  ✓ $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "  ! $text" -ForegroundColor Yellow }
function Write-Fail($text) { Write-Host "  ✗ $text" -ForegroundColor Red }

function Test-Python($exe, $extra) {
    # Gibt die Version zurück (z. B. "3.12"), wenn $exe ein brauchbares Python >= 3.11 ist, sonst $null
    $a = @()
    if ($extra) { $a += $extra }
    # ohne Anführungszeichen im Python-Code: PowerShell 5.1 reicht sie an native Programme kaputt weiter
    $a += '-c', 'import sys; print(sys.version_info[0], sys.version_info[1], sep=chr(46))'
    try {
        $v = & $exe @a 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $v) { return $null }
        if ([version]"$v" -ge [version]'3.11') { return "$v" }
    } catch { }
    return $null
}

function Find-Python {
    foreach ($c in @(@('py', '-3.12'), @('py', '-3.13'), @('py', '-3.11'), @('python', $null))) {
        if (Get-Command $c[0] -ErrorAction SilentlyContinue) {
            $v = Test-Python $c[0] $c[1]
            if ($v) { return @{ exe = $c[0]; extra = $c[1]; version = $v } }
        }
    }
    foreach ($dir in @('Python312', 'Python313', 'Python311')) {
        $p = Join-Path $env:LOCALAPPDATA "Programs\Python\$dir\python.exe"
        if (Test-Path $p) {
            $v = Test-Python $p $null
            if ($v) { return @{ exe = $p; extra = $null; version = $v } }
        }
    }
    return $null
}

Write-Host "claude-pet – Installation" -ForegroundColor Magenta
Write-Host "Ordner: $PSScriptRoot"

# ------------------------------------------------------------------ 1. Windows
Write-Step "Windows"
$build = [Environment]::OSVersion.Version.Build
if ($build -lt 19041) { Write-Warn "Windows-Build $build ist alt – getestet ist Windows 11." } else { Write-Ok "Windows-Build $build" }

# ------------------------------------------------------------------ 2. Windows Terminal
Write-Step "Windows Terminal (oder VS Code / Cursor)"
$wt = (Get-Command wt.exe -ErrorAction SilentlyContinue) -or (Get-AppxPackage -Name 'Microsoft.WindowsTerminal*' -ErrorAction SilentlyContinue)
if ($wt) {
    Write-Ok "gefunden"
} else {
    Write-Warn "nicht gefunden. Das Pet lebt auf dem Text von Claude Code im Windows Terminal oder in VS Code/Cursor."
    Write-Warn "Installieren: winget install Microsoft.WindowsTerminal  (oder über den Microsoft Store)"
}

# ------------------------------------------------------------------ 3. Claude Code
Write-Step "Claude Code (claude)"
if (Get-Command claude -ErrorAction SilentlyContinue) {
    Write-Ok "gefunden – die Sprechblasen nutzen Haiku über dein Claude-Abo"
} else {
    Write-Warn "claude ist nicht im PATH. Das Pet läuft trotzdem, sagt dann aber nur vorgefertigte Sprüche"
    Write-Warn "und kann sich bei der Adoption keine eigene Persönlichkeit ausdenken."
}

# ------------------------------------------------------------------ 4. Python
Write-Step "Python 3.11 oder neuer"
$py = Find-Python
if (-not $py) {
    Write-Warn "kein passendes Python gefunden."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        $answer = Read-Host "  Python 3.12 jetzt mit winget installieren (nur für deinen Benutzer)? [j/n]"
        if ($answer -match '^[jJyY]') {
            winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
            $py = Find-Python
        }
    }
    if (-not $py) {
        Write-Fail "Bitte Python 3.12 installieren (python.org oder: winget install Python.Python.3.12) und install.cmd nochmal starten."
        exit 1
    }
}
Write-Ok "Python $($py.version) ($($py.exe) $($py.extra))"

# ------------------------------------------------------------------ 5. Umgebung + Pakete
Write-Step "Python-Umgebung (.venv) und Pakete"
$venvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    $a = @()
    if ($py.extra) { $a += $py.extra }
    & $py.exe @a -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Fail "venv konnte nicht angelegt werden"; exit 1 }
    Write-Ok ".venv angelegt"
} else {
    Write-Ok ".venv vorhanden"
}
& $venvPy -m pip install --disable-pip-version-check -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Fail "Pakete konnten nicht installiert werden (Internet/Proxy?)"; exit 1 }
& $venvPy -c "import PyQt6.QtWidgets, comtypes, numpy, pyte"
if ($LASTEXITCODE -ne 0) { Write-Fail "Pakete installiert, lassen sich aber nicht laden"; exit 1 }
Write-Ok "PyQt6, comtypes, numpy, pyte bereit"

# ------------------------------------------------------------------ 5b. VS Code / Cursor
Write-Step "Erweiterung für VS Code / Cursor"
if ((Get-Command code -ErrorAction SilentlyContinue) -or (Get-Command cursor -ErrorAction SilentlyContinue)) {
    & $venvPy -m claude_pet.vsix | ForEach-Object { Write-Host "  $_" }
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "installiert – das Pet lebt jetzt auch im Terminal von VS Code/Cursor"
        Write-Warn "Läuft claude dort schon, einmal neu starten (/exit, dann claude)."
    } else {
        Write-Warn "Erweiterung nicht (überall) installiert – das Pet läuft trotzdem im Windows Terminal."
    }
} else {
    Write-Ok "kein VS Code/Cursor gefunden – übersprungen"
}

# ------------------------------------------------------------------ 6. Starten
Write-Step "Pet starten"
Get-CimInstance Win32_Process -Filter "Name like 'python%.exe'" |
    Where-Object { $_.CommandLine -like '*claude_pet*' -or $_.CommandLine -like "*$PSScriptRoot*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Process -FilePath (Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe') -ArgumentList ('"' + (Join-Path $PSScriptRoot 'run.pyw') + '"') -WorkingDirectory $PSScriptRoot
Write-Ok "gestartet"

Write-Host ""
Write-Host "Fertig!" -ForegroundColor Green
Write-Host "- Beim ersten Start öffnet sich das Adoptionsfenster: Figur aussuchen, Namen geben, adoptieren."
Write-Host "- Das Pet startet ab jetzt automatisch mit Windows (abschaltbar im Tray-Menü → Einstellungen)."
Write-Host "- Tray-Symbol: rechts unten neben der Uhr (evtl. unter ^). Rechtsklick → Menü."
Write-Host "- Anleitung: ANLEITUNG.md"
