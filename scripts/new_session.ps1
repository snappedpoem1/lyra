<#
.SYNOPSIS
    Create a new Lyra Oracle work session log and update the session index.

.DESCRIPTION
    - Creates docs/sessions/YYYY-MM-DD-<slug>.md from docs/sessions/_template.md
    - Appends a stub row to docs/SESSION_INDEX.md
    - Prints the suggested session ID and commit message prefix

.PARAMETER Slug
    Short hyphenated identifier for the session (e.g. "fix-search-api").

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
$ErrorActionPreference = 'Stop'

# Resolve repo root relative to this script
$RepoRoot = Split-Path -Parent $PSScriptRoot

# ── Date and session ID ──────────────────────────────────────────────────────

$Today     = Get-Date -Format 'yyyy-MM-dd'
$DayStamp  = Get-Date -Format 'yyyyMMdd'

$SessionDir = Join-Path $RepoRoot 'docs\sessions'
$IndexFile  = Join-Path $RepoRoot 'docs\SESSION_INDEX.md'
$Template   = Join-Path $SessionDir '_template.md'

# Count existing sessions for today to build the NN counter
$Existing = @(Get-ChildItem -Path $SessionDir -Filter "${Today}-*.md" -ErrorAction SilentlyContinue |
              Where-Object { $_.Name -ne '_template.md' })
$Counter  = ($Existing.Count + 1).ToString('D2')
$SessionId = "S-${DayStamp}-${Counter}"

# ── Session file ─────────────────────────────────────────────────────────────

$SessionFile = Join-Path $SessionDir "${Today}-${Slug}.md"

if (Test-Path $SessionFile) {
    Write-Warning "Session file already exists: $SessionFile"
    Write-Warning "Skipping file creation. Continuing with index update."
} else {
    if (-not (Test-Path $Template)) {
        Write-Error "Template not found: $Template"
        exit 1
    }

    $Content = Get-Content -Raw $Template
    $Content = $Content -replace '\[SESSION_ID\]', $SessionId
    $Content = $Content -replace 'YYYY-MM-DD', $Today
    $Content = $Content -replace 'One sentence describing what this session set out to do\.', $Goal
    Set-Content -Path $SessionFile -Value $Content -Encoding UTF8
    Write-Host "Created session log: $SessionFile" -ForegroundColor Green
}

# ── Session index ─────────────────────────────────────────────────────────────

if (-not (Test-Path $IndexFile)) {
    Write-Error "Session index not found: $IndexFile"
    exit 1
}

$IndexContent = Get-Content -Raw $IndexFile

# Build the new row
$NewRow = "| $SessionId | $Today | $Goal | — | — | In progress | — |"

# Append after the last table row (find the last | line)
$Lines   = $IndexContent -split "`n"
$LastRow = ($Lines | Select-String '^\|' | Select-Object -Last 1).LineNumber - 1

if ($null -ne $LastRow) {
    $Before = $Lines[0..$LastRow] -join "`n"
    $After  = if ($LastRow + 1 -lt $Lines.Count) { $Lines[($LastRow + 1)..($Lines.Count - 1)] -join "`n" } else { '' }
    $Updated = $Before + "`n" + $NewRow + "`n" + $After
    Set-Content -Path $IndexFile -Value $Updated.TrimEnd() -Encoding UTF8
    Write-Host "Updated session index: $IndexFile" -ForegroundColor Green
} else {
    Add-Content -Path $IndexFile -Value "`n$NewRow" -Encoding UTF8
    Write-Host "Appended to session index: $IndexFile" -ForegroundColor Green
}

# ── Summary ───────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  Session ID   : $SessionId" -ForegroundColor Cyan
Write-Host "  Session file : docs/sessions/${Today}-${Slug}.md" -ForegroundColor Cyan
Write-Host "  Commit prefix: [$SessionId]" -ForegroundColor Cyan
Write-Host "  Example      : git commit -m '[$SessionId] feat: $Goal'" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""
