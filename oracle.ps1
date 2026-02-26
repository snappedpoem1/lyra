param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    Write-Error "Missing venv interpreter: $py"
    exit 1
}

& $py -m oracle.cli @Args
exit $LASTEXITCODE
