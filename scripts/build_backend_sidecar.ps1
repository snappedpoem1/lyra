param(
    [switch]$SkipLaunchCheck,
    [int]$LaunchCheckTimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[backend-sidecar] $Message"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$entrypoint = Join-Path $repoRoot "lyra_api.py"
$distDir = Join-Path $repoRoot ".lyra-build\bin"
$tmpRoot = Join-Path $repoRoot ".tmp\pyinstaller"
$runStamp = Get-Date -Format "yyyyMMddHHmmssfff"
$buildDistDir = Join-Path $tmpRoot "dist\$runStamp"
$workDir = Join-Path $tmpRoot "build\$runStamp"
$specDir = Join-Path $tmpRoot "spec\$runStamp"

function Copy-StagedExecutable {
    param(
        [string]$SourcePath,
        [string]$DestinationPath
    )

    try {
        Copy-Item -Path $SourcePath -Destination $DestinationPath -Force
        return $true
    } catch {
        if (Test-Path $DestinationPath) {
            Write-Warning "staged sidecar output is locked; keeping existing artifact at '$DestinationPath'"
            return $false
        }
        throw
    }
}

if (-not (Test-Path $pythonExe)) {
    throw "python executable not found at '$pythonExe'. Create and install .venv first."
}
if (-not (Test-Path $entrypoint)) {
    throw "backend entrypoint not found at '$entrypoint'."
}

New-Item -ItemType Directory -Path $distDir -Force | Out-Null
New-Item -ItemType Directory -Path $buildDistDir -Force | Out-Null
New-Item -ItemType Directory -Path $workDir -Force | Out-Null
New-Item -ItemType Directory -Path $specDir -Force | Out-Null

Write-Step "checking PyInstaller availability"
& $pythonExe -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed in .venv. Run: .venv\Scripts\python.exe -m pip install pyinstaller"
}

Write-Step "building lyra_backend.exe"
$env:LYRA_SKIP_VENV_REEXEC = "1"
$excludeModules = @(
    "nltk"
)
& $pythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name lyra_backend `
    --distpath $buildDistDir `
    --workpath $workDir `
    --specpath $specDir `
    --exclude-module $excludeModules[0] `
    --collect-submodules oracle.api.blueprints `
    $entrypoint
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

$builtExe = Join-Path $buildDistDir "lyra_backend.exe"
if (-not (Test-Path $builtExe)) {
    throw "expected output not found: $builtExe"
}

$outputExe = Join-Path $distDir "lyra_backend.exe"
[void](Copy-StagedExecutable -SourcePath $builtExe -DestinationPath $outputExe)

Write-Step "built sidecar: $outputExe"

if (-not $SkipLaunchCheck) {
    $baseUrl = "http://127.0.0.1:5000"
    $healthRunning = $false
    try {
        $health = Invoke-RestMethod -Method Get -Uri "$baseUrl/api/health" -TimeoutSec 1
        if ($health.status -eq "ok") {
            $healthRunning = $true
        }
    } catch {
        $healthRunning = $false
    }

    if ($healthRunning) {
        Write-Step "launch check skipped: backend already running at $baseUrl"
    } else {
        Write-Step "verifying sidecar launch health"
        $env:LYRA_PROJECT_ROOT = $repoRoot
        $env:LYRA_SKIP_VENV_REEXEC = "1"
        $env:LYRA_BOOTSTRAP = "0"
        $proc = Start-Process -FilePath $outputExe -WorkingDirectory $repoRoot -PassThru
        try {
            $ready = $false
            $maxAttempts = [Math]::Max(1, [int]($LaunchCheckTimeoutSeconds * 2))
            for ($i = 0; $i -lt $maxAttempts; $i++) {
                Start-Sleep -Milliseconds 500
                if ($proc.HasExited) {
                    throw "sidecar exited during launch check (exit code: $($proc.ExitCode))"
                }
                try {
                    $health = Invoke-RestMethod -Method Get -Uri "$baseUrl/api/health" -TimeoutSec 1
                    if ($health.status -eq "ok") {
                        $ready = $true
                        break
                    }
                } catch {
                    continue
                }
            }
            if (-not $ready) {
                throw "sidecar launch check timeout after ${LaunchCheckTimeoutSeconds}s"
            }
        } finally {
            if ($proc -and -not $proc.HasExited) {
                Stop-Process -Id $proc.Id -Force
            }
        }
        Write-Step "sidecar launch check passed"
    }
}
