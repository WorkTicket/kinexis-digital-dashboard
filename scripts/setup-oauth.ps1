# Kinexis one-time sign-in setup (run once before building/distributing)
# Creates kinexis/backend/oauth.json and updates .env

$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot ".." "backend"
$oauthPath = Join-Path $backend "oauth.json"
$envPath = Join-Path $backend ".env"
$examplePath = Join-Path $backend "oauth.json.example"

Write-Host ""
Write-Host "=== Kinexis Sign-In Setup ===" -ForegroundColor Cyan
Write-Host "This is a one-time step for whoever builds Kinexis."
Write-Host "End users will only click Sign in — they never see this."
Write-Host ""

if (Test-Path $oauthPath) {
    $existing = Get-Content $oauthPath -Raw | ConvertFrom-Json
    if ($existing.google.client_id -and $existing.cloudflare.client_id) {
        $ans = Read-Host "oauth.json already exists. Overwrite? (y/N)"
        if ($ans -ne "y" -and $ans -ne "Y") { exit 0 }
    }
}

Write-Host "Step 1 — Google" -ForegroundColor Yellow
Write-Host "  1. Open https://console.cloud.google.com/apis/credentials"
Write-Host "  2. Create OAuth client (Desktop app or Web)"
Write-Host "  3. Add redirect URI: http://127.0.0.1:8000/auth/google/callback"
Write-Host "  4. Enable: Search Console API, Google Analytics Data API, Google Analytics Admin API"
Start-Process "https://console.cloud.google.com/apis/credentials"
$googleId = Read-Host "Paste Google Client ID"
$googleSecret = Read-Host "Paste Google Client Secret"

Write-Host ""
Write-Host "Step 2 — Cloudflare" -ForegroundColor Yellow
Write-Host "  1. Cloudflare Dashboard -> Manage Account -> OAuth clients -> Create"
Write-Host "  2. Public desktop app, PKCE, grant types: authorization_code + refresh_token"
Write-Host "  3. Redirect URI: http://127.0.0.1:8000/auth/cloudflare/callback"
Write-Host "  4. Scopes: account.read, zone.read"
Start-Process "https://dash.cloudflare.com/?to=/:account/manage-account/oauth-clients"
$cfId = Read-Host "Paste Cloudflare Client ID"
$cfSecret = Read-Host "Paste Cloudflare Client Secret (optional for PKCE, press Enter to skip)"

$oauth = @{
    google = @{
        client_id = $googleId.Trim()
        client_secret = $googleSecret.Trim()
    }
    cloudflare = @{
        client_id = $cfId.Trim()
    }
}
if ($cfSecret.Trim()) {
    $oauth.cloudflare.client_secret = $cfSecret.Trim()
}

$oauth | ConvertTo-Json -Depth 3 | Set-Content $oauthPath -Encoding UTF8
Write-Host "Wrote $oauthPath" -ForegroundColor Green

# Sync into .env for dev runs
if (Test-Path $envPath) {
    $lines = Get-Content $envPath
    $map = @{
        "GOOGLE_CLIENT_ID" = $googleId.Trim()
        "GOOGLE_CLIENT_SECRET" = $googleSecret.Trim()
        "CLOUDFLARE_CLIENT_ID" = $cfId.Trim()
        "CLOUDFLARE_CLIENT_SECRET" = $cfSecret.Trim()
    }
    $seen = @{}
    $out = foreach ($line in $lines) {
        if ($line -match '^([A-Z_]+)=') {
            $key = $Matches[1]
            if ($map.ContainsKey($key)) {
                $seen[$key] = $true
                "$key=$($map[$key])"
            } else { $line }
        } else { $line }
    }
    foreach ($key in $map.Keys) {
        if (-not $seen[$key]) { $out += "$key=$($map[$key])" }
    }
    $out | Set-Content $envPath -Encoding UTF8
    Write-Host "Updated $envPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "Done. Rebuild Kinexis so oauth.json is bundled:" -ForegroundColor Cyan
Write-Host "  cd kinexis/frontend && npm run build"
Write-Host "  cd kinexis/backend && pyinstaller kinexis-backend.spec"
Write-Host "  cd kinexis/electron && npm run build"
