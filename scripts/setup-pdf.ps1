# Install Playwright Chromium for Kinexis PDF report export
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $root "backend"

Write-Host "=== Kinexis PDF Setup ===" -ForegroundColor Cyan

Push-Location $backend
try {
    if (Test-Path ".venv\Scripts\python.exe") {
        $python = ".venv\Scripts\python.exe"
    } else {
        $python = "python"
    }

    Write-Host "`n[1/2] Installing backend requirements (includes playwright)..." -ForegroundColor Yellow
    & $python -m pip install -r requirements.txt

    Write-Host "`n[2/2] Installing Chromium for Playwright..." -ForegroundColor Yellow
    & $python -m playwright install chromium

    Write-Host "`nDone. Report tab Download PDF should work." -ForegroundColor Green
    Write-Host "If PDF still returns 503, use Open HTML → Print → Save as PDF."
} finally {
    Pop-Location
}
