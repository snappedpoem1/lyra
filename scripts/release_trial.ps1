<#
.SYNOPSIS
    Lyra Release Trial Runner — tests, builds, packages, receipts.

.DESCRIPTION
    Runs the full release-confidence pipeline:
      1. Preflight checks (toolchain, git, paths)
      2. Backend tests (pytest)
      3. Renderer dependency install (npm ci)
      4. Renderer tests (vitest)
      5. Renderer + TypeScript build (tsc + vite)
      6. Docs QA (check_docs_state.ps1)
      7. Tauri installer build (backend sidecar + tauri build)
      8. Artifact discovery and summary

    Produces timestamped logs, a text summary, a JSON summary,
    and a QA checklist in artifacts/release_trial_<timestamp>/.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\release_trial.ps1
    powershell -ExecutionPolicy Bypass -File .\scripts\release_trial.ps1 -CopyInstallerToRunFolder
    powershell -ExecutionPolicy Bypass -File .\scripts\release_trial.ps1 -SkipInstaller
#>
[CmdletBinding()]
param(
    [string]$RepoRoot,
    [switch]$SkipBackendTests,
    [switch]$SkipFrontendTests,
    [switch]$SkipBuild,
    [switch]$SkipInstaller,
    [switch]$SkipDocsQA,
    [switch]$AllowDirtyGit,
    [switch]$CopyInstallerToRunFolder,
    [switch]$OpenArtifactFolder
)

$ErrorActionPreference = "Stop"

# ─── Resolve repo root ───────────────────────────────────────
if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
else {
    $RepoRoot = (Resolve-Path $RepoRoot).Path
}

Set-Location $RepoRoot

# ─── Utility / style helpers ─────────────────────────────────

$script:OverallStart = Get-Date
$script:StepIndex    = 0
$script:StepTotal    = 0

function Get-NowStamp {
    return (Get-Date -Format "HH:mm:ss")
}

function Get-ElapsedString {
    param([datetime]$StartTime)
    $elapsed = (Get-Date) - $StartTime
    return "{0:00}:{1:00}:{2:00}" -f [int]$elapsed.TotalHours, $elapsed.Minutes, $elapsed.Seconds
}

function Write-Cass {
    param(
        [string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::Gray
    )
    Write-Host "[$(Get-NowStamp)] $Message" -ForegroundColor $Color
}

function Write-Banner {
    param([string]$Message)
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor DarkCyan
    Write-Host "  $Message" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor DarkCyan
}

function Write-Phase {
    param([string]$Message)
    Write-Host ""
    Write-Host "--- $Message ---" -ForegroundColor Magenta
}

function Write-Ok {
    param([string]$Message)
    Write-Cass "  $Message" Green
}

function Write-WarnMsg {
    param([string]$Message)
    Write-Cass "  $Message" Yellow
}

function Write-Fail {
    param([string]$Message)
    Write-Cass "  $Message" Red
}

function New-DirIfMissing {
    param([string]$PathToCreate)
    if (-not (Test-Path $PathToCreate)) {
        New-Item -ItemType Directory -Path $PathToCreate -Force | Out-Null
    }
}

function Test-CommandExists {
    param([string]$CommandName)
    return $null -ne (Get-Command $CommandName -ErrorAction SilentlyContinue)
}

function Update-OverallProgress {
    param(
        [string]$Activity,
        [string]$Status
    )
    $percent = 0
    if ($script:StepTotal -gt 0) {
        $percent = [math]::Min(100, [math]::Floor(($script:StepIndex / $script:StepTotal) * 100))
    }
    Write-Progress -Id 1 -Activity $Activity -Status $Status -PercentComplete $percent
}

function Start-Step {
    param([string]$StepName)
    $script:StepIndex++
    $stepLabel = "[$($script:StepIndex)/$($script:StepTotal)] $StepName"
    $overallElapsed = Get-ElapsedString -StartTime $script:OverallStart

    Write-Host ""
    Write-Host "[$(Get-NowStamp)] >>> $stepLabel" -ForegroundColor Cyan
    Write-Cass "Overall elapsed: $overallElapsed" DarkGray

    Update-OverallProgress -Activity "Lyra Release Trial" -Status $stepLabel

    return Get-Date
}

function Finish-Step {
    param(
        [string]$StepName,
        [datetime]$StepStart,
        [bool]$Success
    )
    $elapsed = Get-ElapsedString -StartTime $StepStart
    if ($Success) {
        Write-Ok "$StepName finished in $elapsed"
    }
    else {
        Write-Fail "$StepName failed after $elapsed"
    }
}

function Invoke-LoggedCommand {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Command,
        [Parameter(Mandatory)][string]$WorkingDirectory,
        [Parameter(Mandatory)][string]$LogFile,
        [string]$CassIntro = ""
    )

    $stepStart = Start-Step -StepName $Name

    if ($CassIntro) {
        Write-Cass $CassIntro Cyan
    }
    Write-Cass "  Working dir: $WorkingDirectory" DarkGray
    Write-Cass "  Command:     $Command" DarkGray
    Write-Cass "  Log file:    $LogFile" DarkGray

    $start = Get-Date
    $exitCode = 0

    Push-Location $WorkingDirectory
    try {
        Write-Progress -Id 2 -ParentId 1 -Activity $Name -Status "Running..." -PercentComplete 15

        $output = & cmd.exe /c "$Command 2>&1"
        $exitCode = $LASTEXITCODE

        Write-Progress -Id 2 -ParentId 1 -Activity $Name -Status "Writing log..." -PercentComplete 90
    }
    finally {
        Pop-Location
    }

    $output | Out-File -FilePath $LogFile -Encoding utf8

    $duration = (Get-Date) - $start
    $seconds  = [Math]::Round($duration.TotalSeconds, 2)

    if ($seconds -gt 30) {
        Write-WarnMsg "That one took a minute ($seconds s). Still on track."
    }

    Write-Progress -Id 2 -ParentId 1 -Activity $Name -Status "Complete" -PercentComplete 100
    Start-Sleep -Milliseconds 200
    Write-Progress -Id 2 -ParentId 1 -Activity $Name -Completed

    $result = [PSCustomObject]@{
        Name         = $Name
        Command      = $Command
        WorkingDir   = $WorkingDirectory
        LogFile      = $LogFile
        ExitCode     = $exitCode
        DurationSecs = $seconds
    }

    Finish-Step -StepName $Name -StepStart $stepStart -Success ($exitCode -eq 0)

    return $result
}

function Find-FileSafe {
    param(
        [string]$BasePath,
        [string[]]$Patterns
    )
    foreach ($pattern in $Patterns) {
        $found = Get-ChildItem -Path $BasePath -Recurse -File -Filter $pattern -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    return $null
}

# ─── Run folder setup ────────────────────────────────────────

$Timestamp     = Get-Date -Format "yyyyMMdd_HHmmss"
$ArtifactsRoot = Join-Path $RepoRoot "artifacts"
$RunRoot       = Join-Path $ArtifactsRoot "release_trial_$Timestamp"
$LogsRoot      = Join-Path $RunRoot   "logs"
$SummaryFile   = Join-Path $RunRoot   "release_summary.txt"
$JsonSummary   = Join-Path $RunRoot   "release_summary.json"
$ChecklistFile = Join-Path $RunRoot   "trial_checklist.txt"

New-DirIfMissing $ArtifactsRoot
New-DirIfMissing $RunRoot
New-DirIfMissing $LogsRoot

Write-Banner "Lyra Release Trial Runner"
Write-Cass "Cap, we're doing the grown-up thing: tests, build, installer, receipts." Cyan
Write-Cass "  Repo root:  $RepoRoot" DarkGray
Write-Cass "  Run folder: $RunRoot" DarkGray

# ─── Git snapshot ────────────────────────────────────────────

$GitBranch = ""
$GitHash   = ""
$GitDirty  = $false
if (Test-CommandExists "git") {
    try {
        $GitBranch = (& git rev-parse --abbrev-ref HEAD 2>$null).Trim()
        $GitHash   = (& git rev-parse --short HEAD 2>$null).Trim()
        $statusOut = (& git status --porcelain 2>$null)
        $GitDirty  = [bool]$statusOut
    }
    catch { }
}

# ─── Preflight ────────────────────────────────────────────────

$RendererAppPath   = Join-Path $RepoRoot "desktop\renderer-app"
$TauriConfigPath   = Join-Path $RendererAppPath "src-tauri\tauri.conf.json"
$VenvPython        = Join-Path $RepoRoot ".venv\Scripts\python.exe"

# Calculate step count
$script:StepTotal = 2   # preflight + artifact summary (always)
if (-not $SkipBackendTests)  { $script:StepTotal++ }
if (-not $SkipFrontendTests) { $script:StepTotal += 2 }   # npm ci + vitest
if (-not $SkipBuild)         { $script:StepTotal++ }
if (-not $SkipDocsQA)        { $script:StepTotal++ }
if (-not $SkipInstaller)     { $script:StepTotal++ }

$PreflightIssues = [System.Collections.Generic.List[string]]::new()

$preflightStart = Start-Step -StepName "Preflight checks"
Write-Cass "Checking the toolbox before we start swinging." Cyan

if (-not (Test-Path $VenvPython)) {
    $PreflightIssues.Add(".venv\Scripts\python.exe not found - need a Python venv in the repo root")
}
if (-not (Test-CommandExists "git"))   { $PreflightIssues.Add("git not found in PATH") }
if (-not (Test-CommandExists "npm"))   { $PreflightIssues.Add("npm not found in PATH") }
if (-not (Test-CommandExists "cargo")) { $PreflightIssues.Add("cargo not found in PATH (needed for Tauri build)") }
if (-not (Test-CommandExists "npx"))   { $PreflightIssues.Add("npx not found in PATH") }

if (-not (Test-Path $RendererAppPath))   { $PreflightIssues.Add("desktop\renderer-app not found") }
if (-not (Test-Path $TauriConfigPath))   { $PreflightIssues.Add("desktop\renderer-app\src-tauri\tauri.conf.json not found") }

if (-not $AllowDirtyGit -and $GitDirty) {
    $PreflightIssues.Add("Git working tree is dirty. Commit first or re-run with -AllowDirtyGit.")
}

if ($PreflightIssues.Count -gt 0) {
    Finish-Step -StepName "Preflight checks" -StepStart $preflightStart -Success $false
    Write-Fail "Preflight failed. Here's the damage:"
    $PreflightIssues | ForEach-Object { Write-Host "   - $_" -ForegroundColor Red }
    $PreflightIssues | Out-File -FilePath $SummaryFile -Encoding utf8
    throw "Preflight checks failed. Fix these before proceeding."
}

Write-Ok "All tools present. No cursed surprises."
Write-Cass "  Git: $GitBranch @ $GitHash$(if ($GitDirty) { ' (dirty)' })" DarkGray
Finish-Step -StepName "Preflight checks" -StepStart $preflightStart -Success $true

# ─── Execution ────────────────────────────────────────────────

$Results = [System.Collections.Generic.List[object]]::new()
$CriticalFailure = $false

function Add-Result {
    param([object]$R)
    $Results.Add($R) | Out-Null
}

function Run-Step {
    param(
        [string]$Name,
        [string]$Command,
        [string]$WorkDir,
        [string]$CassMsg,
        [bool]$Critical = $true
    )
    $safeName = ($Name -replace '[^a-zA-Z0-9_\- ]', '') -replace '\s+', '_'
    $logFile  = Join-Path $LogsRoot "$safeName.log"

    $r = Invoke-LoggedCommand `
        -Name $Name `
        -Command $Command `
        -WorkingDirectory $WorkDir `
        -LogFile $logFile `
        -CassIntro $CassMsg

    Add-Result $r

    if ($r.ExitCode -ne 0) {
        if ($Critical) {
            $script:CriticalFailure = $true
            Write-Fail "$Name failed (exit $($r.ExitCode)). Logs: $logFile"
            throw "$Name failed. See log: $logFile"
        }
        else {
            Write-WarnMsg "$Name returned exit $($r.ExitCode) - non-critical, continuing."
        }
    }
    else {
        Write-Ok "$Name cleared."
    }
}

try {
    # ── Backend tests ──
    if (-not $SkipBackendTests) {
        Write-Phase "Backend lane"
        Run-Step `
            -Name "Backend tests (pytest)" `
            -Command "`"$VenvPython`" -m pytest -q" `
            -WorkDir $RepoRoot `
            -CassMsg "Backend tests are up first. Let's see if the bones hold."
    }
    else {
        Write-WarnMsg "Skipping backend tests (you told me to)."
    }

    # ── Frontend install ──
    if (-not $SkipFrontendTests) {
        Write-Phase "Renderer lane"

        Run-Step `
            -Name "Renderer npm install" `
            -Command "npm ci --prefer-offline" `
            -WorkDir $RendererAppPath `
            -CassMsg "Making sure renderer dependencies are clean."

        Run-Step `
            -Name "Renderer tests (vitest)" `
            -Command "npx vitest run --passWithNoTests" `
            -WorkDir $RendererAppPath `
            -CassMsg "Now we shake down the renderer side."
    }
    else {
        Write-WarnMsg "Skipping frontend tests."
    }

    # ── Build (tsc + vite) ──
    if (-not $SkipBuild) {
        Write-Phase "Build lane"
        Run-Step `
            -Name "Renderer build (tsc + vite)" `
            -Command "npm run build" `
            -WorkDir $RendererAppPath `
            -CassMsg "Time to make the pretty parts stand up in public."
    }
    else {
        Write-WarnMsg "Skipping build."
    }

    # ── Docs QA ──
    if (-not $SkipDocsQA) {
        Write-Phase "Docs QA lane"
        $docsScript = Join-Path $RepoRoot "scripts\check_docs_state.ps1"
        Run-Step `
            -Name "Docs QA check" `
            -Command "powershell -NoProfile -ExecutionPolicy Bypass -File `"$docsScript`"" `
            -WorkDir $RepoRoot `
            -CassMsg "Checking docs for broken links and mojibake." `
            -Critical $false
    }
    else {
        Write-WarnMsg "Skipping docs QA."
    }

    # ── Installer ──
    if (-not $SkipInstaller) {
        Write-Phase "Installer lane"
        Write-Cass "Alright, now we box it up and make it presentable. This will take a while." Yellow
        Run-Step `
            -Name "Tauri installer build" `
            -Command "npm run tauri:build" `
            -WorkDir $RendererAppPath `
            -CassMsg "Building the full package: backend sidecar + Tauri bundle."
    }
    else {
        Write-WarnMsg "Skipping installer build."
    }
}
catch {
    Write-Fail $_.Exception.Message
}

# ─── Artifact discovery ──────────────────────────────────────

$artifactStart = Start-Step -StepName "Artifact discovery and summary"
Write-Phase "Artifact hunt"
Write-Cass "Installer hunt underway. Let's see what the shop turned out." Cyan

$InstallerPath    = $null
$InstallerMsiPath = $null
$BuildOutputPath  = $null

$BundleRoot = Join-Path $RendererAppPath "src-tauri\target\release\bundle"

if (Test-Path $BundleRoot) {
    # NSIS installer (.exe)
    $nsisDir = Join-Path $BundleRoot "nsis"
    if (Test-Path $nsisDir) {
        $InstallerPath = Find-FileSafe -BasePath $nsisDir -Patterns @("*.exe")
    }

    # WiX MSI
    $msiDir = Join-Path $BundleRoot "msi"
    if (Test-Path $msiDir) {
        $InstallerMsiPath = Find-FileSafe -BasePath $msiDir -Patterns @("*.msi")
    }
}

$RendererDist = Join-Path $RendererAppPath "dist"
if (Test-Path $RendererDist) {
    $BuildOutputPath = $RendererDist
}

# Copy installer into run folder if requested
$CopiedInstallerPath = $null
if ($CopyInstallerToRunFolder -and $InstallerPath -and (Test-Path $InstallerPath)) {
    $installerName = Split-Path $InstallerPath -Leaf
    $CopiedInstallerPath = Join-Path $RunRoot $installerName
    Copy-Item -Path $InstallerPath -Destination $CopiedInstallerPath -Force
    Write-Ok "Copied installer into run folder: $CopiedInstallerPath"
}

# ─── QA Checklist ─────────────────────────────────────────────

$installerDisplay = if ($CopiedInstallerPath) { $CopiedInstallerPath } elseif ($InstallerPath) { $InstallerPath } else { "NOT FOUND" }

$checklistLines = @(
    "Lyra Real-Use Trial Checklist"
    "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    "Branch: $GitBranch at $GitHash"
    ""
    "Installer: $installerDisplay"
    ""
    "Pre-launch:"
    "  [ ] Installer file exists and is non-zero size"
    "  [ ] No antivirus quarantine on the installer"
    ""
    "Install + first launch:"
    "  [ ] Installer launches successfully"
    "  [ ] App installs without packaging errors"
    "  [ ] App opens to the expected main surface"
    ""
    "Library + playback:"
    "  [ ] Library loads (tracks visible)"
    "  [ ] Playback starts from a library track"
    "  [ ] Queue builds and plays through correctly"
    "  [ ] Pause / seek / skip / repeat behave"
    ""
    "Surfaces:"
    "  [ ] Home surface looks coherent"
    "  [ ] Oracle recommendation surfaces render"
    "  [ ] Explanation chips and why-this-track content render"
    "  [ ] Feedback actions (more/less like this) work visibly"
    "  [ ] Playlist creation and browsing work"
    "  [ ] Settings surface renders"
    ""
    "Stability:"
    "  [ ] No obvious crash during 10+ minutes of use"
    "  [ ] No broken icons or obvious placeholder UI"
    "  [ ] No console errors visible in dev tools (if applicable)"
    ""
    "Notes:"
    "  - ________________________________________"
    "  - ________________________________________"
    "  - ________________________________________"
)
$checklistLines | Out-File -FilePath $ChecklistFile -Encoding utf8

# ─── Summary ──────────────────────────────────────────────────

$FailedCount = ($Results | Where-Object { $_.ExitCode -ne 0 }).Count
$AllPassed = ($Results.Count -gt 0) -and ($FailedCount -eq 0)
$NoneRan = ($Results.Count -eq 0)
$OverallStatus = if ($NoneRan) { "SKIP" } elseif ($AllPassed) { "PASS" } else { "FAIL" }
$OverallElapsed = Get-ElapsedString -StartTime $script:OverallStart

$SummaryLines = @()
$SummaryLines += "Lyra Release Trial Summary"
$SummaryLines += "========================="
$SummaryLines += ""
$SummaryLines += "Timestamp:       $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$SummaryLines += "Branch:          $GitBranch"
$SummaryLines += "Commit:          $GitHash$(if ($GitDirty) { ' (dirty)' })"
$SummaryLines += "Repo root:       $RepoRoot"
$SummaryLines += "Run folder:      $RunRoot"
$SummaryLines += "Overall elapsed: $OverallElapsed"
$SummaryLines += "Overall status:  $OverallStatus"
$SummaryLines += ""
$SummaryLines += "Steps:"
$SummaryLines += "------"
foreach ($r in $Results) {
    $mark = if ($r.ExitCode -eq 0) { "PASS" } else { "FAIL" }
    $SummaryLines += "  [$mark] $($r.Name)  ($($r.DurationSecs)s)"
    $SummaryLines += "         command:  $($r.Command)"
    $SummaryLines += "         log:      $($r.LogFile)"
}
$SummaryLines += ""
$SummaryLines += "Artifacts:"
$SummaryLines += "----------"
$SummaryLines += "  Renderer dist:     $(if ($BuildOutputPath) { $BuildOutputPath } else { 'NOT FOUND' })"
$SummaryLines += "  NSIS installer:    $(if ($InstallerPath) { $InstallerPath } else { 'NOT FOUND' })"
$SummaryLines += "  MSI installer:     $(if ($InstallerMsiPath) { $InstallerMsiPath } else { 'NOT FOUND' })"
$SummaryLines += "  Copied installer:  $(if ($CopiedInstallerPath) { $CopiedInstallerPath } else { 'NOT COPIED' })"
$SummaryLines += "  QA checklist:      $ChecklistFile"
$SummaryLines += ""
$SummaryLines += "Cass notes:"
$SummaryLines += "-----------"
if ($NoneRan) {
    $SummaryLines += "  All steps were skipped. Nothing to report."
}
elseif ($AllPassed -and $InstallerPath) {
    $SummaryLines += "  Good news, Cap. The package is standing up straight and ready for real-use trials."
}
elseif ($AllPassed -and -not $InstallerPath) {
    $SummaryLines += "  Tests and build cleared, but I didn't find the installer."
    $SummaryLines += "  Check the Tauri build log before calling it done."
}
else {
    $failedSteps = ($Results | Where-Object { $_.ExitCode -ne 0 } | ForEach-Object { $_.Name }) -join ", "
    $SummaryLines += "  Something slipped on the stairs: $failedSteps"
    $SummaryLines += "  Check the failing logs before you run real-world trials."
}

$SummaryLines | Out-File -FilePath $SummaryFile -Encoding utf8

# JSON summary
$jsonObj = [PSCustomObject]@{
    timestamp           = (Get-Date).ToString("s")
    branch              = $GitBranch
    commit              = $GitHash
    dirty               = $GitDirty
    repoRoot            = $RepoRoot
    runRoot             = $RunRoot
    overallElapsed      = $OverallElapsed
    overallStatus       = $OverallStatus
    steps               = @($Results | ForEach-Object {
        [PSCustomObject]@{
            name         = $_.Name
            command      = $_.Command
            workingDir   = $_.WorkingDir
            logFile      = $_.LogFile
            exitCode     = $_.ExitCode
            durationSecs = $_.DurationSecs
        }
    })
    rendererBuildPath   = $BuildOutputPath
    nsisInstallerPath   = $InstallerPath
    msiInstallerPath    = $InstallerMsiPath
    copiedInstallerPath = $CopiedInstallerPath
    checklistPath       = $ChecklistFile
}
$jsonObj | ConvertTo-Json -Depth 6 | Out-File -FilePath $JsonSummary -Encoding utf8

# Report artifact locations
if ($InstallerPath) {
    Write-Ok "NSIS installer: $InstallerPath"
}
if ($InstallerMsiPath) {
    Write-Ok "MSI installer:  $InstallerMsiPath"
}
if (-not $InstallerPath -and -not $InstallerMsiPath) {
    Write-WarnMsg "No dice on the package yet. Check the Tauri build log."
}

Write-Ok "Summary:   $SummaryFile"
Write-Ok "JSON:      $JsonSummary"
Write-Ok "Checklist: $ChecklistFile"
Write-Ok "Logs:      $LogsRoot"

Finish-Step -StepName "Artifact discovery and summary" -StepStart $artifactStart -Success $true

# ─── Final banner ─────────────────────────────────────────────

Write-Banner "Release Trial Complete"
Write-Cass "Overall elapsed: $OverallElapsed" Cyan
Write-Cass "Branch: $GitBranch @ $GitHash$(if ($GitDirty) { ' (dirty)' })" DarkGray

if ($NoneRan) {
    Write-WarnMsg "All steps were skipped. Nothing to verify."
}
elseif ($AllPassed) {
    Write-Ok "Good news, Cap. The run cleared."
    if ($InstallerPath) {
        Write-Cass "  You've got a package ready for real-use trials." Green
    }
}
else {
    Write-Fail "The run did not fully clear. Logs: $LogsRoot"
}

Write-Progress -Id 1 -Activity "Lyra Release Trial" -Completed

# Open artifact folder if requested
if ($OpenArtifactFolder) {
    Start-Process explorer.exe -ArgumentList $RunRoot
}

if (-not $AllPassed -and -not $NoneRan) {
    exit 1
}
