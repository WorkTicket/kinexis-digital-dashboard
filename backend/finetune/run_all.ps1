# End-to-end: dataset → QLoRA train → merge → (optional) Ollama export
#   powershell -File kinexis/backend/finetune/run_all.ps1
#   powershell -File kinexis/backend/finetune/run_all.ps1 -SkipExport
#   powershell -File kinexis/backend/finetune/run_all.ps1 -SetupOnly

param(
  [switch]$SetupOnly,
  [switch]$SkipExport,
  [switch]$SkipSetup,
  [int]$NPerPattern = 10
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$venvPy = Join-Path $here ".venv\Scripts\python.exe"

if (-not $SkipSetup) {
  if (-not (Test-Path $venvPy)) {
    Write-Host "=== setup_venv ==="
    & powershell -File (Join-Path $here "setup_venv.ps1")
  } else {
    Write-Host "Venv exists — skipping setup (pass without -SkipSetup after deleting .venv to reinstall)"
  }
}

if ($SetupOnly) { exit 0 }

if (-not (Test-Path $venvPy)) {
  Write-Host "Missing $venvPy — run setup_venv.ps1 first"
  exit 1
}

Write-Host "=== generate_dataset (n=$NPerPattern per pattern) ==="
& $venvPy (Join-Path $here "generate_dataset.py") --n-per-pattern $NPerPattern

Write-Host "=== train.py (QLoRA + merge) ==="
Write-Host "This can take several hours on a 12GB GPU..."
$env:HF_HUB_DISABLE_SYMLINKS = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
& $venvPy (Join-Path $here "train.py") --force

if (-not $SkipExport) {
  Write-Host "=== export_ollama ==="
  & powershell -File (Join-Path $here "export_ollama.ps1")
}

Write-Host "All done."
