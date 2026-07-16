# Create a Python 3.12 venv and install fine-tune deps.
# Run from anywhere:
#   powershell -File kinexis/backend/finetune/setup_venv.ps1

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$venv = Join-Path $here ".venv"
Write-Host "Creating venv at $venv (Python 3.12)..."
py -3.12 -m venv $venv
& "$venv\Scripts\python.exe" -m pip install --upgrade pip

Write-Host "Installing PyTorch (CUDA 12.8 nightly — required for RTX 50-series / sm_120)..."
& "$venv\Scripts\pip.exe" uninstall -y torch torchvision torchaudio 2>$null
& "$venv\Scripts\pip.exe" install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128 --no-cache-dir

Write-Host "Installing fine-tune requirements..."
& "$venv\Scripts\pip.exe" install -r (Join-Path $here "requirements.txt")

Write-Host ""
Write-Host "Done. Activate with:"
Write-Host "  $venv\Scripts\Activate.ps1"
Write-Host "Then:"
Write-Host "  `$env:HF_HUB_DISABLE_SYMLINKS='1'"
Write-Host "  python generate_dataset.py"
Write-Host "  python train.py"
Write-Host "  .\export_ollama.ps1"
