param(
    [string]$InstallerPath = "",
    [string]$InstallDir = "",
    [switch]$BuildFirst,
    [switch]$Silent
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[lyra-installer] $Message"
}

function Resolve-DesktopRoot {
    if ($PSScriptRoot -and (Test-Path $PSScriptRoot)) {
        return $PSScriptRoot
    }

    if ($PSCommandPath) {
        return (Split-Path -Parent $PSCommandPath)
    }

    return (Get-Location).Path
}

function Get-NewestInstaller {
    param([string]$DesktopRoot)

    $distDir = Join-Path $DesktopRoot "dist"
    if (-not (Test-Path $distDir)) {
        throw "Desktop dist folder not found at '$distDir'. Build the desktop app first or pass -InstallerPath."
    }

    $patterns = @("Lyra Setup *.exe", "Lyra Oracle Setup *.exe")
    $installer = $null
    foreach ($pattern in $patterns) {
        $installer = Get-ChildItem -Path $distDir -Filter $pattern |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
        if ($installer) {
            break
        }
    }

    if (-not $installer) {
        throw "No Lyra installer EXE found in '$distDir'."
    }

    return $installer.FullName
}

function Resolve-InstallDir {
    param(
        [string]$RequestedDir,
        [string]$DesktopRoot
    )

    if ($RequestedDir) {
        return $RequestedDir
    }

    $localAppData = [Environment]::GetFolderPath("LocalApplicationData")
    $defaultDir = Join-Path $localAppData "Programs\Lyra"
    return $defaultDir
}

function Run-Build {
    param([string]$DesktopRoot)

    Write-Step "building installer first"
    Push-Location $DesktopRoot
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) {
            throw "npm run build failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

$desktopRoot = Resolve-DesktopRoot

if ($BuildFirst) {
    Run-Build -DesktopRoot $desktopRoot
}

if (-not $InstallerPath) {
    $InstallerPath = Get-NewestInstaller -DesktopRoot $desktopRoot
}

if (-not (Test-Path $InstallerPath)) {
    throw "Installer not found: $InstallerPath"
}

$resolvedInstallDir = Resolve-InstallDir -RequestedDir $InstallDir -DesktopRoot $desktopRoot
$resolvedInstallDir = [System.IO.Path]::GetFullPath($resolvedInstallDir)

Write-Step "installer: $InstallerPath"
Write-Step "target dir: $resolvedInstallDir"

$installerArgs = @()
if ($Silent) {
    $installerArgs += "/S"
}
$installerArgs += "/D=$resolvedInstallDir"

Write-Step "launching installer"
$process = Start-Process -FilePath $InstallerPath -ArgumentList $installerArgs -Wait -PassThru

if ($process.ExitCode -ne 0) {
    throw "Installer exited with code $($process.ExitCode)"
}

$exeCandidates = @(
    (Join-Path $resolvedInstallDir "Lyra.exe"),
    (Join-Path $resolvedInstallDir "Lyra\Lyra.exe"),
    (Join-Path $resolvedInstallDir "Lyra Oracle.exe"),
    (Join-Path $resolvedInstallDir "Lyra Oracle\Lyra Oracle.exe")
)

$installedExe = $exeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($installedExe) {
    Write-Step "installed executable: $installedExe"
}
else {
    Write-Step "install completed; executable path not auto-detected"
}

Write-Step "done"
Write-Step "next steps:"
Write-Step "  1. powershell -ExecutionPolicy Bypass -File ..\\scripts\\check_llm_config.ps1"
Write-Step "  2. powershell -ExecutionPolicy Bypass -File ..\\scripts\\smoke_desktop.ps1 -AllowLlmFailure"
Write-Step "  3. launch Lyra and confirm Library, Queue, and playback are live"
