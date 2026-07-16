# Convert merged HF weights → GGUF → Ollama model `kinexis-marketing-ft`
#
# Prerequisites:
#   - train.py finished (output/kinexis-marketing-merged exists)
#   - llama.cpp convert script OR `pip install gguf` + huggingface convert
#   - Ollama running
#
# Usage:
#   powershell -File kinexis/backend/finetune/export_ollama.ps1
#   powershell -File kinexis/backend/finetune/export_ollama.ps1 -Quant Q4_K_M

param(
  [string]$Quant = "Q4_K_M",
  [string]$ModelName = "kinexis-marketing-ft"
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$merged = Join-Path $here "output\kinexis-marketing-merged"
$ggufDir = Join-Path $here "output\gguf"
$modelfile = Join-Path $here "Modelfile.ft"

if (-not (Test-Path $merged)) {
  Write-Host "Missing merged weights at $merged"
  Write-Host "Run: python train.py   (or python train.py --merge-only)"
  exit 1
}

New-Item -ItemType Directory -Force -Path $ggufDir | Out-Null

# Prefer llama.cpp convert if cloned beside finetune; else try python -m
$convertPy = Join-Path $here "llama.cpp\convert_hf_to_gguf.py"
if (-not (Test-Path $convertPy)) {
  $convertPy = Join-Path $here "tools\convert_hf_to_gguf.py"
}

$outGgufF16 = Join-Path $ggufDir "kinexis-marketing-f16.gguf"
$outGgufQ = Join-Path $ggufDir "kinexis-marketing-$Quant.gguf"

$venvPython = Join-Path $here ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { $venvPython = "python" }

if (Test-Path $convertPy) {
  Write-Host "Converting HF → GGUF (F16)..."
  & $venvPython $convertPy $merged --outfile $outGgufF16 --outtype f16
} else {
  Write-Host @"
llama.cpp convert script not found.

Clone once:
  cd `"$here`"
  git clone --depth 1 https://github.com/ggerganov/llama.cpp.git
  .\.venv\Scripts\pip.exe install -r llama.cpp\requirements\requirements-convert_hf_to_gguf.txt

Then re-run this script.
"@
  exit 1
}

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$quantize = Join-Path $here "llama.cpp\build\bin\Release\llama-quantize.exe"
if (-not (Test-Path $quantize)) {
  $quantize = Join-Path $here "llama.cpp\llama-quantize.exe"
}

if (Test-Path $quantize) {
  Write-Host "Quantizing to $Quant..."
  & $quantize $outGgufF16 $outGgufQ $Quant
  $fromFile = $outGgufQ
} else {
  Write-Host "llama-quantize not built — using F16 GGUF (larger). Build llama.cpp to quantize."
  $fromFile = $outGgufF16
}

# Write Modelfile pointing at the GGUF
$mf = @"
FROM $fromFile

PARAMETER temperature 0.35
PARAMETER num_ctx 16384
PARAMETER repeat_penalty 1.1
PARAMETER num_predict 6144

SYSTEM `"You are Kinexis Marketing AI — fine-tuned for digital marketing success metrics. Every recommendation must name the metric, lever, asset (URL/query), and how to measure. Prefer concrete JSON when asked. Ground answers in client data.`"
"@
Set-Content -Path $modelfile -Value $mf -Encoding UTF8

Write-Host "Creating Ollama model '$ModelName'..."
ollama create $ModelName -f $modelfile
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Set in backend .env:"
Write-Host "  OLLAMA_MODEL=$ModelName"
Write-Host "Then restart the Kinexis backend."
