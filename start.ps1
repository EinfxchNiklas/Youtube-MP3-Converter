# Lokaler Start-Script für YT MP3 Converter
# Ausführen: .\start.ps1

$ErrorActionPreference = "Stop"

# ffmpeg in PATH aufnehmen (nach winget-Installation nötig bis Shell neu gestartet)
$env:PATH = [System.Environment]::GetEnvironmentVariable('PATH','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('PATH','User')

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# Prüfen ob .env existiert
if (-not (Test-Path "$root\.env")) {
    Write-Host "HINWEIS: Keine .env gefunden. Kopiere .env.example ..."
    Copy-Item "$root\.env.example" "$root\.env"
}

# Venv aktivieren falls vorhanden
$activate = "$root\.venv\Scripts\Activate.ps1"
if (Test-Path $activate) {
    & $activate
} else {
    Write-Host "Virtuelle Umgebung nicht gefunden. Erstelle sie..."
    python -m venv .venv
    & $activate
    pip install -r requirements.txt
}

Write-Host ""
Write-Host "Server startet auf http://127.0.0.1:8000"
Write-Host "Zugangsdaten aus .env (Standard: admin / changeme)"
Write-Host "Mit STRG+C beenden."
Write-Host ""

uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
