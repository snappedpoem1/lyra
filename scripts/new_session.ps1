<#
.SYNOPSIS
    Create a new Lyra Oracle work session log and update the session index.

.DESCRIPTION
    - Creates docs/sessions/YYYY-MM-DD-<slug>.md from docs/sessions/_template.md
    - Appends a stub row to docs/SESSION_INDEX.md
    - Prints the suggested session ID and commit message prefix

.PARAMETER Slug
    Short hyphenated identifier for the session (for example, "fix-search-api").

.PARAMETER Goal
    One-sentence description of the session goal.

.EXAMPLE
    .\scripts\new_session.ps1 -Slug "fix-search-api" -Goal "Fix the hybrid search ranking bug"
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Slug,

    [Parameter(Mandatory = $true)]
    [string]$Goal
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Resolve repo root relative to this script.
$RepoRoot = Split-Path -Parent $PSScriptRoot

# Date and session ID.
$Today = Get-Date -Format "yyyy-MM-dd"
$DayStamp = Get-Date -Format "yyyyMMdd"

$SessionDir = Join-Path $RepoRoot "docs\sessions"
$IndexFile = Join-Path $RepoRoot "docs\SESSION_INDEX.md"
$Template = Join-Path $SessionDir "_template.md"

$Existing = @(
    Get-ChildItem -Path $SessionDir -Filter "${Today}-*.md" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne "_template.md" }
)
$Counter = ($Existing.Count + 1).ToString("D2")
$SessionId = "S-${DayStamp}-${Counter}"

# Session file.
$SessionFile = Join-Path $SessionDir "${Today}-${Slug}.md"

if (Test-Path $SessionFile) {
    Write-Warning "Session file already exists: $SessionFile"
    Write-Warning "Skipping file creation. Continuing with index update."
}
else {
    if (-not (Test-Path $Template)) {
        Write-Error "Template not found: $Template"
        exit 1
    }

    $Content = Get-Content -Path $Template -Raw
    $Content = $Content -replace "\[SESSION_ID\]", $SessionId
    $Content = $Content -replace "YYYY-MM-DD", $Today
    $Content = $Content -replace "One sentence describing what this session set out to do\.", $Goal
    Set-Content -Path $SessionFile -Value $Content -Encoding UTF8
    Write-Host "Created session log: $SessionFile" -ForegroundColor Green
}

# Session index.
if (-not (Test-Path $IndexFile)) {
    Write-Error "Session index not found: $IndexFile"
    exit 1
}

$Lines = @(Get-Content -Path $IndexFile)
$NewRow = "| $SessionId | $Today | $Goal | - | - | In progress | - |"

$LastTableLine = $null
for ($i = 0; $i -lt $Lines.Count; $i++) {
    if ($Lines[$i] -match "^\|") {
        $LastTableLine = $i
    }
}

if ($null -eq $LastTableLine) {
    Add-Content -Path $IndexFile -Value $NewRow -Encoding UTF8
    Write-Host "Appended to session index: $IndexFile" -ForegroundColor Green
}
else {
    $InsertAt = $LastTableLine + 1
    $Before = if ($InsertAt -gt 0) { @($Lines[0..($InsertAt - 1)]) } else { @() }
    $After = if ($InsertAt -lt $Lines.Count) { @($Lines[$InsertAt..($Lines.Count - 1)]) } else { @() }
    $UpdatedLines = @($Before + $NewRow + $After)
    Set-Content -Path $IndexFile -Value $UpdatedLines -Encoding UTF8
    Write-Host "Updated session index: $IndexFile" -ForegroundColor Green
}

# Summary.
$Rule = "------------------------------------------------------------"

Write-Host ""
Write-Host $Rule -ForegroundColor Cyan
Write-Host "  Session ID   : $SessionId" -ForegroundColor Cyan
Write-Host "  Session file : docs/sessions/${Today}-${Slug}.md" -ForegroundColor Cyan
Write-Host "  Commit prefix: [$SessionId]" -ForegroundColor Cyan
Write-Host "  Example      : git commit -m '[$SessionId] feat: $Goal'" -ForegroundColor Cyan
Write-Host $Rule -ForegroundColor Cyan
Write-Host ""
