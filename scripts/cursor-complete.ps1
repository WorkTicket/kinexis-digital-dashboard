param(
    [Parameter(Mandatory=$true)]
    [int]$TaskId,
    [int]$Port = 8000,
    [string]$TokenFile = ".cursor\api_token"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..\..")
$tokenPath = Join-Path $projectRoot $TokenFile

if (-not (Test-Path $tokenPath)) {
    $candidates = @(
        (Join-Path $env:APPDATA "kinexis-desktop\.cursor\api_token"),
        (Join-Path $env:APPDATA "kinexis-desktop\api_token")
    )
    foreach ($cand in $candidates) {
        if (Test-Path $cand) {
            $tokenPath = $cand
            break
        }
    }
}

if (-not (Test-Path $tokenPath)) {
    Write-Error "API token file not found at $tokenPath. Ensure the Kinexis Electron app is running."
    exit 1
}

$apiToken = (Get-Content $tokenPath -Raw).Trim()
if (-not $apiToken) {
    Write-Error "API token is empty"
    exit 1
}

$body = @{ status = "done" } | ConvertTo-Json
$uri = "http://127.0.0.1:$Port/tasks/$TaskId"

try {
    $response = Invoke-RestMethod -Uri $uri -Method Put -Body $body `
        -ContentType "application/json" `
        -Headers @{ "X-Kinexis-Token" = $apiToken } `
        -TimeoutSec 10

    Write-Output "Task $TaskId marked as done."
    Write-Output "Impact outcome: $($response.impact_outcome ?? 'pending recheck')"
    exit 0
} catch {
    Write-Error "Failed to mark task $TaskId as done: $_"
    exit 1
}
