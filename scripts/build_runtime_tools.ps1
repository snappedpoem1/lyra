param(
  [switch]$SkipSmokeCheck
)

$ErrorActionPreference = "Stop"

function Write-Step {
  param([string]$Message)
  Write-Host "[runtime-tools] $Message"
}

function Invoke-PyInstallerTool {
  param(
    [string]$PythonExe,
    [string]$Name,
    [string]$Entrypoint,
    [string]$DistPath,
    [string]$WorkPath,
    [string]$SpecPath,
    [string[]]$CollectAllPackages,
    [string[]]$CopyMetadataPackages
  )

  $args = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--log-level", "WARN",
    "--name", $Name,
    "--distpath", $DistPath,
    "--workpath", $WorkPath,
    "--specpath", $SpecPath
  )

  foreach ($package in $CollectAllPackages) {
    $args += @("--collect-all", $package)
  }
  foreach ($package in $CopyMetadataPackages) {
    $args += @("--copy-metadata", $package)
  }

  $args += $Entrypoint
  & $PythonExe @args
  if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed for $Name (exit code $LASTEXITCODE)"
  }
}

function Copy-ToolToTargets {
  param(
    [string]$SourcePath,
    [string[]]$Targets
  )

  foreach ($target in $Targets) {
    $targetDir = Split-Path -Parent $target
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    Copy-Item -Path $SourcePath -Destination $target -Force
  }
}

function Test-ToolExecutable {
  param(
    [string]$ExecutablePath,
    [string[]]$Arguments
  )

  & $ExecutablePath @Arguments *> $null
  if ($LASTEXITCODE -ne 0) {
    throw "runtime tool smoke check failed: $ExecutablePath $($Arguments -join ' ')"
  }
}

function Copy-OptionalHostBinary {
  param(
    [string]$CommandName,
    [string[]]$Targets
  )

  $found = (Get-Command $CommandName -ErrorAction SilentlyContinue).Source
  if (-not $found) {
    Write-Step "optional host tool not found: $CommandName"
    return
  }

  Write-Step "staging optional host tool: $CommandName"
  Copy-ToolToTargets -SourcePath $found -Targets $Targets
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$tmpRoot = Join-Path $repoRoot ".tmp\pyinstaller-runtime"
$runtimeRoot = Join-Path $repoRoot "runtime"
$runtimeBin = Join-Path $runtimeRoot "bin"
$tauriRuntimeBin = Join-Path $repoRoot "desktop\renderer-app\src-tauri\bin\runtime\bin"
$workRoot = Join-Path $tmpRoot "build"
$specRoot = Join-Path $tmpRoot "spec"
$entrypointRoot = Join-Path $repoRoot "scripts\runtime_tool_entrypoints"

if (-not (Test-Path $pythonExe)) {
  throw "python executable not found at '$pythonExe'"
}

New-Item -ItemType Directory -Force -Path $runtimeBin | Out-Null
New-Item -ItemType Directory -Force -Path $tauriRuntimeBin | Out-Null
New-Item -ItemType Directory -Force -Path $workRoot | Out-Null
New-Item -ItemType Directory -Force -Path $specRoot | Out-Null

Write-Step "checking PyInstaller availability"
& $pythonExe -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller is not installed in .venv. Run: .venv\\Scripts\\python.exe -m pip install pyinstaller"
}

Write-Step "building bundled spotdl runtime"
Invoke-PyInstallerTool `
  -PythonExe $pythonExe `
  -Name "spotdl" `
  -Entrypoint (Join-Path $entrypointRoot "spotdl_runtime.py") `
  -DistPath $runtimeBin `
  -WorkPath (Join-Path $workRoot "spotdl") `
  -SpecPath (Join-Path $specRoot "spotdl") `
  -CollectAllPackages @("spotdl", "yt_dlp", "pykakasi") `
  -CopyMetadataPackages @("spotdl", "yt_dlp", "pykakasi")

Write-Step "building bundled streamrip runtime"
Invoke-PyInstallerTool `
  -PythonExe $pythonExe `
  -Name "rip" `
  -Entrypoint (Join-Path $entrypointRoot "streamrip_runtime.py") `
  -DistPath $runtimeBin `
  -WorkPath (Join-Path $workRoot "streamrip") `
  -SpecPath (Join-Path $specRoot "streamrip") `
  -CollectAllPackages @("streamrip") `
  -CopyMetadataPackages @("streamrip")

$spotdlExe = Join-Path $runtimeBin "spotdl.exe"
$streamripExe = Join-Path $runtimeBin "rip.exe"

if (-not (Test-Path $spotdlExe)) {
  throw "expected bundled spotdl executable not found: $spotdlExe"
}
if (-not (Test-Path $streamripExe)) {
  throw "expected bundled streamrip executable not found: $streamripExe"
}

Copy-ToolToTargets -SourcePath $spotdlExe -Targets @(
  (Join-Path $tauriRuntimeBin "spotdl.exe")
)
Copy-ToolToTargets -SourcePath $streamripExe -Targets @(
  (Join-Path $tauriRuntimeBin "rip.exe")
)

Copy-OptionalHostBinary -CommandName "ffmpeg" -Targets @(
  (Join-Path $runtimeBin "ffmpeg.exe"),
  (Join-Path $tauriRuntimeBin "ffmpeg.exe")
)
Copy-OptionalHostBinary -CommandName "ffprobe" -Targets @(
  (Join-Path $runtimeBin "ffprobe.exe"),
  (Join-Path $tauriRuntimeBin "ffprobe.exe")
)

if (-not $SkipSmokeCheck) {
  Write-Step "running executable smoke checks"
  Test-ToolExecutable -ExecutablePath $spotdlExe -Arguments @("--help")
  Test-ToolExecutable -ExecutablePath $streamripExe -Arguments @("--help")
}

Write-Step "bundled runtime tools staged to:"
Write-Step "  $runtimeBin"
Write-Step "  $tauriRuntimeBin"
