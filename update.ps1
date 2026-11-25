# claude-pet aktualisieren: neue Version holen (git pull), Pakete nachziehen, Pet neu starten.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

Write-Host "claude-pet – Update" -ForegroundColor Magenta
if (Test-Path (Join-Path $PSScriptRoot '.git')) {
    git pull --ff-only
    if ($LASTEXITCODE -ne 0) { Write-Host "  ✗ git pull fehlgeschlagen (lokale Änderungen?)" -ForegroundColor Red; exit 1 }
} else {
    Write-Host "  ! Kein git-Ordner – neue Version bitte als ZIP herunterladen und darüber entpacken." -ForegroundColor Yellow
}
& (Join-Path $PSScriptRoot 'install.ps1')
