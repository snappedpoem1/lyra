param()

$ErrorActionPreference = "Stop"

function Write-Check {
    param([string]$Message)
    Write-Host "[docs-check] $Message"
}

function Add-Issue {
    param(
        [ref]$Issues,
        [string]$Message
    )
    $Issues.Value += $Message
}

$issues = @()
$repoRoot = (Get-Location).Path

Write-Check "collecting tracked markdown files"
$mdFiles = git ls-files "*.md"
if (-not $mdFiles -or $mdFiles.Count -eq 0) {
    Add-Issue -Issues ([ref]$issues) -Message "no tracked markdown files were found"
}

Write-Check "checking broken relative links"
foreach ($file in $mdFiles) {
    $full = Join-Path $repoRoot $file
    if (-not (Test-Path $full)) {
        continue
    }
    $content = Get-Content -Path $full -Raw -Encoding utf8
    $matches = [regex]::Matches($content, '\[[^\]]+\]\(([^)]+)\)')
    foreach ($match in $matches) {
        $target = $match.Groups[1].Value.Trim()
        if ($target -match '^(https?:|mailto:|#)') {
            continue
        }
        $targetPath = $target.Split('#')[0].Split('?')[0]
        if ([string]::IsNullOrWhiteSpace($targetPath)) {
            continue
        }
        if ($targetPath -match '^[A-Za-z]:\\') {
            if (-not (Test-Path $targetPath)) {
                Add-Issue -Issues ([ref]$issues) -Message "broken absolute link in $file -> $target"
            }
            continue
        }
        $resolved = Join-Path (Split-Path -Parent $full) $targetPath
        if (-not (Test-Path $resolved)) {
            Add-Issue -Issues ([ref]$issues) -Message "broken relative link in $file -> $target"
        }
    }
}

Write-Check "checking mojibake markers"
$mojibakePattern = 'â|Ã|�'
foreach ($file in $mdFiles) {
    $full = Join-Path $repoRoot $file
    if (-not (Test-Path $full)) {
        continue
    }
    $content = Get-Content -Path $full -Raw -Encoding utf8
    if ($content -match $mojibakePattern) {
        Add-Issue -Issues ([ref]$issues) -Message "possible mojibake marker found in $file"
    }
}

Write-Check "checking canonical doc consistency"
$canonicalFiles = @(
    "README.md",
    "AGENTS.md",
    "docs/PROJECT_STATE.md",
    "docs/WORKLIST.md",
    "docs/MISSING_FEATURES_REGISTRY.md",
    "docs/ROADMAP_ENGINE_TO_ENTITY.md",
    "docs/MASTER_PLAN_EXPANDED.md"
)

foreach ($file in $canonicalFiles) {
    if (-not (Test-Path (Join-Path $repoRoot $file))) {
        Add-Issue -Issues ([ref]$issues) -Message "missing canonical file: $file"
    }
}

if (Test-Path "docs/MASTER_PLAN_EXPANDED.md") {
    $masterPlan = Get-Content -Path "docs/MASTER_PLAN_EXPANDED.md" -Raw -Encoding utf8
    if ($masterPlan -notmatch "ROADMAP_ENGINE_TO_ENTITY\.md") {
        Add-Issue -Issues ([ref]$issues) -Message "docs/MASTER_PLAN_EXPANDED.md must point to docs/ROADMAP_ENGINE_TO_ENTITY.md"
    }
}

if (Test-Path "docs/ROADMAP_ENGINE_TO_ENTITY.md") {
    $roadmap = Get-Content -Path "docs/ROADMAP_ENGINE_TO_ENTITY.md" -Raw -Encoding utf8
    if ($roadmap -notmatch "Tauri") {
        Add-Issue -Issues ([ref]$issues) -Message "docs/ROADMAP_ENGINE_TO_ENTITY.md must mention Tauri"
    }
    if ($roadmap -notmatch "Rust") {
        Add-Issue -Issues ([ref]$issues) -Message "docs/ROADMAP_ENGINE_TO_ENTITY.md must mention Rust runtime ownership"
    }
    if ($roadmap -notmatch "SvelteKit") {
        Add-Issue -Issues ([ref]$issues) -Message "docs/ROADMAP_ENGINE_TO_ENTITY.md must mention SvelteKit"
    }
}

$activeDocs = @(
    "README.md",
    "docs/PROJECT_STATE.md",
    "docs/WORKLIST.md",
    "docs/MISSING_FEATURES_REGISTRY.md"
)
$legacyPattern = 'foobar2000|BeefWeb'
foreach ($file in $activeDocs) {
    if (-not (Test-Path $file)) {
        continue
    }
    $content = Get-Content -Path $file -Raw -Encoding utf8
    if ($content -match $legacyPattern) {
        Add-Issue -Issues ([ref]$issues) -Message "legacy playback gate language found in active doc: $file"
    }
}

if ($issues.Count -gt 0) {
    Write-Host ""
    Write-Host "[docs-check] FAILED"
    $issues | ForEach-Object { Write-Host " - $_" }
    exit 1
}

Write-Check "OK - docs state checks passed"
