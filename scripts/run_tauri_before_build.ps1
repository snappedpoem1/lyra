param(
    [string]$RepoRoot
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
else {
    $RepoRoot = (Resolve-Path $RepoRoot).Path
}

$rendererRoot = Join-Path $RepoRoot "desktop\renderer-app"
$distRoot = Join-Path $rendererRoot "dist"
$skipFrontendBuild = $env:LYRA_SKIP_FRONTEND_BUILD -and $env:LYRA_SKIP_FRONTEND_BUILD.Trim().ToLower() -in @("1", "true", "yes", "on")

if ($skipFrontendBuild) {
    if (-not (Test-Path $distRoot)) {
        throw "LYRA_SKIP_FRONTEND_BUILD is set, but renderer dist was not found at '$distRoot'. Run npm run build first or unset the flag."
    }

    Write-Host "[tauri-before-build] reusing existing renderer dist at $distRoot"
    exit 0
}

Write-Host "[tauri-before-build] building renderer"
Push-Location $rendererRoot
try {
    & npm run build
    if ($LASTEXITCODE -ne 0) {
        throw "Renderer build failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

# Stage backend sidecar and runtime tools for bundling
Write-Host "[tauri-before-build] staging backend sidecar for bundling"

$sidecarSource = Join-Path $RepoRoot ".lyra-build\bin\lyra_backend.exe"
$tauriSrcRoot = Join-Path $rendererRoot "src-tauri"
$bundleBinDir = Join-Path $tauriSrcRoot "bin"

# Ensure destination exists
if (-not (Test-Path $bundleBinDir)) {
    New-Item -ItemType Directory -Path $bundleBinDir -Force | Out-Null
}

# Copy sidecar
if (Test-Path $sidecarSource) {
    $dest = Join-Path $bundleBinDir "lyra_backend.exe"
    Write-Host "[tauri-before-build] copying sidecar: $(Split-Path $sidecarSource -Leaf) -> $dest"
    Copy-Item -Path $sidecarSource -Destination $dest -Force
}
else {
    Write-Warning "Backend sidecar not found at $sidecarSource - installer may fail to launch backend"
}

# Copy runtime tools
$toolsSource = Join-Path $RepoRoot ".lyra-build\bin"
if (Test-Path $toolsSource) {
    $toolFiles = Get-ChildItem -Path $toolsSource -File -Filter "*.exe" | Where-Object { $_.Name -ne "lyra_backend.exe" }
    if ($toolFiles.Count -gt 0) {
        Write-Host "[tauri-before-build] copying $($toolFiles.Count) runtime tool(s)"
        foreach ($tool in $toolFiles) {
            $dest = Join-Path $bundleBinDir $tool.Name
            Copy-Item -Path $tool.FullName -Destination $dest -Force
        }
    }
}

Write-Host "[tauri-before-build] pre-build staging complete"
