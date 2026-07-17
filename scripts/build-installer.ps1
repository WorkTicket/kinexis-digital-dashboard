# Build Kinexis Windows installer (frontend + backend + electron)
[CmdletBinding()]
param(
    [switch]$Publish = $false
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

Write-Host "=== Kinexis Installer Build ===" -ForegroundColor Cyan
if ($Publish) {
    Write-Host "Mode: BUILD + PUBLISH to GitHub Releases" -ForegroundColor Magenta
    if (-not $env:GH_TOKEN) {
        Write-Error "GH_TOKEN environment variable not set. Set a GitHub personal access token with repo scope."
    }
} else {
    Write-Host "Mode: BUILD only (add -Publish to push to GitHub)" -ForegroundColor DarkGray
}

if (-not (Test-Path "$root\backend\.env")) {
    Write-Error "Missing backend/.env — copy .env.template and set FERNET_KEY first."
}
if (-not (Test-Path "$root\backend\oauth.json")) {
    Write-Error "Missing backend/oauth.json — run setup-oauth.ps1 first."
}

Write-Host "`n[1/4] Generating icons..." -ForegroundColor Yellow
if (Test-Path "$root\backend\.venv\Scripts\python.exe") {
    & "$root\backend\.venv\Scripts\python.exe" "$root\scripts\generate_icons.py"
} else {
    python "$root\scripts\generate_icons.py"
}

Write-Host "`n[2/4] Building frontend..." -ForegroundColor Yellow
Push-Location "$root\frontend"
npm run build
Pop-Location

Write-Host "`n[3/4] Building backend (PyInstaller)..." -ForegroundColor Yellow
Push-Location "$root\backend"
if (Test-Path ".venv\Scripts\python.exe") {
    & .\.venv\Scripts\python.exe -m PyInstaller kinexis-backend.spec --noconfirm
} else {
    python -m PyInstaller kinexis-backend.spec --noconfirm
}
if ($LASTEXITCODE -ne 0) {
    Pop-Location
    Write-Error "PyInstaller backend build failed."
}
Pop-Location

Write-Host "`n[4/4] Building Windows installer (Electron)..." -ForegroundColor Yellow

# Stale Setup.exe is easy to reinstall by mistake — wipe prior installer outputs first.
# Also stop any running app so win-unpacked / NSIS packaging is not file-locked.
cmd /c "taskkill /F /IM Kinexis.exe /T >nul 2>&1"
cmd /c "taskkill /F /IM kinexis-backend.exe /T >nul 2>&1"
Start-Sleep -Seconds 1

$distDir = "$root\electron\dist"
if (Test-Path $distDir) {
    Get-ChildItem $distDir -Filter "Kinexis-Setup*.exe*" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem $distDir -Filter "Kinexis Setup*.exe*" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    if (Test-Path "$distDir\win-unpacked") {
        Remove-Item "$distDir\win-unpacked" -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Push-Location "$root\electron"
if ($Publish) {
    npm run publish
} else {
    npm run build
}
Pop-Location

$installer = Get-ChildItem "$root\electron\dist" -Filter "Kinexis-Setup*.exe" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notmatch "unpacked|blockmap" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if ($installer) {
    Write-Host "`nDone! Installer (canonical name - use THIS file):" -ForegroundColor Green
    Write-Host $installer.FullName
    Write-Host ("Built: {0}  Size: {1:N0} bytes" -f $installer.LastWriteTime, $installer.Length)
    if ($Publish) {
        Write-Host "Published to GitHub Releases - users will auto-update to this version" -ForegroundColor Green
    }
} else {
    Write-Host "`nBuild finished but no Kinexis-Setup*.exe found. Check electron\dist" -ForegroundColor Red
    exit 1
}
