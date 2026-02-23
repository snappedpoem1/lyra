# Lyra Oracle CLI Launcher for PowerShell
# Usage: .\lyra.ps1 <command> [options]
# Examples:
#   .\lyra.ps1 status
#   .\lyra.ps1 score --all
#   .\lyra.ps1 pipeline --library "A:\music\Active Music"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    & $venvPython -m oracle.cli @args
} else {
    python -m oracle.cli @args
}
