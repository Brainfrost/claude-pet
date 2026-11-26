# claude-pet entfernen: beendet das Pet, entfernt den Autostart und auf Wunsch die Daten (Pet, Tagebuch …).
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

Write-Host "claude-pet – Deinstallation" -ForegroundColor Magenta

Get-CimInstance Win32_Process -Filter "Name like 'python%.exe'" |
    Where-Object { $_.CommandLine -like '*claude_pet*' -or $_.CommandLine -like "*$PSScriptRoot*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Write-Host "  ✓ Pet beendet" -ForegroundColor Green

$venvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if ((Test-Path $venvPy) -and ((Get-Command code -ErrorAction SilentlyContinue) -or (Get-Command cursor -ErrorAction SilentlyContinue))) {
    & $venvPy -m claude_pet.vsix --remove | Out-Null
    Write-Host "  ✓ Erweiterung aus VS Code/Cursor entfernt" -ForegroundColor Green
}

$run = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
if (Get-ItemProperty -Path $run -Name 'claude-pet' -ErrorAction SilentlyContinue) {
    Remove-ItemProperty -Path $run -Name 'claude-pet'
}
Write-Host "  ✓ Autostart entfernt" -ForegroundColor Green

$data = Join-Path $env:LOCALAPPDATA 'claude-pet'
if (Test-Path $data) {
    Write-Host ""
    Write-Host "  In $data liegen dein Pet, sein Tagebuch, die Schatzkiste und die Einstellungen." -ForegroundColor Yellow
    $answer = Read-Host "  Auch diese Daten löschen? Dein Pet ist dann weg. [j/n]"
    if ($answer -match '^[jJyY]') {
        Remove-Item -Recurse -Force $data
        Write-Host "  ✓ Daten gelöscht" -ForegroundColor Green
    } else {
        Write-Host "  Daten bleiben – bei einer neuen Installation ist dein Pet wieder da."
    }
}
Write-Host ""
Write-Host "Fertig. Den Ordner $PSScriptRoot kannst du jetzt löschen."
