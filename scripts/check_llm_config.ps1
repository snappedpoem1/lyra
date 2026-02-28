$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

Write-Host "Lyra LLM configuration check"
Write-Host "Repo: $repoRoot"

& $python -m oracle.llm_config
exit $LASTEXITCODE
