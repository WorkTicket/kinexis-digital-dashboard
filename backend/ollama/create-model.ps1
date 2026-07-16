# Create / refresh the Kinexis marketing-tuned Ollama model.
# Requires: Ollama running, base model already pulled (default qwen3:14b).
#
# Usage (PowerShell or bash, from repo):
#   powershell -File kinexis/backend/ollama/create-model.ps1
#   # or:
#   ollama create kinexis-marketing -f kinexis/backend/ollama/Modelfile

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

Write-Host "Creating Ollama model 'kinexis-marketing' from Modelfile..."
ollama create kinexis-marketing -f Modelfile
if ($LASTEXITCODE -ne 0) {
  Write-Host "Failed. Is Ollama running and is the FROM model pulled? Try: ollama pull qwen3:14b"
  exit $LASTEXITCODE
}
Write-Host ""
Write-Host "Done. Set in backend .env:"
Write-Host "  OLLAMA_MODEL=kinexis-marketing"
Write-Host "Then restart the Kinexis backend."
