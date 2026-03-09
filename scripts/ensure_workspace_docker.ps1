param(
    [switch]$IncludeQobuz,
    [int]$DockerWaitSeconds = 90,
    [int]$ServiceWaitSeconds = 30
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $ProjectRoot "archive\legacy-ops\docker-compose.yml"

function Test-DockerDaemon {
    try {
        $null = & docker info 2>$null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

function Get-DockerDesktopPath {
    $candidates = @(
        (Join-Path ${env:ProgramFiles} "Docker\Docker\Docker Desktop.exe"),
        (Join-Path ${env:LOCALAPPDATA} "Docker Desktop\Docker Desktop.exe"),
        (Join-Path ${env:ProgramW6432} "Docker\Docker\Docker Desktop.exe")
    ) | Where-Object { $_ -and (Test-Path $_) }

    if ($candidates.Count -gt 0) {
        return $candidates[0]
    }

    return $null
}

function Start-DockerDesktop {
    $exe = Get-DockerDesktopPath
    if (-not $exe) {
        throw "Docker Desktop.exe was not found on this machine."
    }

    Write-Host "[lyra] Starting Docker Desktop..." -ForegroundColor Cyan
    Start-Process -FilePath $exe | Out-Null

    $deadline = (Get-Date).AddSeconds($DockerWaitSeconds)
    do {
        Start-Sleep -Seconds 2
        if (Test-DockerDaemon) {
            Write-Host "[lyra] Docker daemon is ready." -ForegroundColor Green
            return
        }
    } while ((Get-Date) -lt $deadline)

    throw "Docker daemon did not become ready within $DockerWaitSeconds seconds."
}

function Test-HttpReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec 4 -UseBasicParsing
        return ($response.StatusCode -eq 200 -or $response.StatusCode -eq 401 -or $response.StatusCode -eq 403)
    }
    catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
            if ($statusCode -eq 401 -or $statusCode -eq 403) {
                return $true
            }
        }
        return $false
    }
}

function Wait-ForTargetHealth {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Services
    )

    $deadline = (Get-Date).AddSeconds($ServiceWaitSeconds)
    do {
        $allHealthy = $true
        foreach ($service in $Services) {
            if (-not (Test-HttpReady -Url $healthChecks[$service])) {
                $allHealthy = $false
                break
            }
        }

        if ($allHealthy) {
            return $true
        }

        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    return $false
}

function Get-ContainerState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ContainerName
    )

    try {
        $value = & docker inspect --format "{{.State.Status}}" $ContainerName 2>$null
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        return ($value | Out-String).Trim()
    }
    catch {
        return $null
    }
}

function Start-ExistingContainer {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ContainerName
    )

    try {
        & docker start $ContainerName | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

if (-not (Test-Path $ComposeFile)) {
    throw "Compose file not found: $ComposeFile"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "docker CLI was not found in PATH."
}

if (-not (Test-DockerDaemon)) {
    Start-DockerDesktop
}
else {
    Write-Host "[lyra] Docker daemon already running." -ForegroundColor Green
}

$services = @("prowlarr", "rdtclient", "slskd")
if ($IncludeQobuz -or $env:LYRA_BOOTSTRAP_QOBUZ -match "^(1|true|yes|on)$") {
    $services += "qobuz"
}

$healthChecks = @{
    "prowlarr"  = "http://localhost:9696/health"
    "rdtclient" = "http://localhost:6500"
    "slskd"     = "http://localhost:5030/api/v0/application"
    "qobuz"     = "http://localhost:7700/health"
}

$containerNames = @{
    "prowlarr"  = "lyra_prowlarr"
    "rdtclient" = "lyra_rdtclient"
    "slskd"     = "lyra_slskd"
    "qobuz"     = "lyra_qobuz"
}

$targetsHealthy = $true
foreach ($service in $services) {
    if (-not (Test-HttpReady -Url $healthChecks[$service])) {
        $targetsHealthy = $false
        break
    }
}

if ($targetsHealthy) {
    Write-Host "[lyra] Target Docker services already healthy: $($services -join ', ')." -ForegroundColor Green
    exit 0
}

$startedExisting = @()
foreach ($service in $services) {
    if (Test-HttpReady -Url $healthChecks[$service]) {
        continue
    }

    $containerName = $containerNames[$service]
    $state = Get-ContainerState -ContainerName $containerName
    if ($state -and $state -ne "running") {
        if (Start-ExistingContainer -ContainerName $containerName) {
            $startedExisting += $containerName
        }
    }
}

if ($startedExisting.Count -gt 0) {
    Write-Host "[lyra] Started existing containers: $($startedExisting -join ', ')." -ForegroundColor Green
    if (Wait-ForTargetHealth -Services $services) {
        Write-Host "[lyra] Target Docker services are healthy after starting existing containers." -ForegroundColor Green
        exit 0
    }
}

if (Wait-ForTargetHealth -Services $services) {
    Write-Host "[lyra] Target Docker services became healthy without a compose restart." -ForegroundColor Green
    exit 0
}

Write-Host "[lyra] Ensuring Docker services: $($services -join ', ')" -ForegroundColor Cyan
& docker compose -f $ComposeFile up -d @services
if ($LASTEXITCODE -ne 0) {
    if (Wait-ForTargetHealth -Services $services) {
        Write-Host "[lyra] Compose returned a non-zero exit code, but target services are healthy." -ForegroundColor Yellow
        exit 0
    }

    throw "docker compose up failed."
}

Write-Host "[lyra] Docker services requested successfully." -ForegroundColor Green
