param()

$ErrorActionPreference = "Stop"

function Write-Step {
  param([string]$Message)
  Write-Host "[codex-helpers] $Message"
}

function Reset-McpServer {
  param([string]$Name)

  codex mcp remove $Name *> $null
  $global:LASTEXITCODE = 0
}

$playwrightOutputDir = "C:\Users\Admin\.codex\playwright-mcp"
New-Item -ItemType Directory -Force -Path $playwrightOutputDir | Out-Null

Write-Step "registering sqlite MCP helper"
Reset-McpServer -Name "sqlite"
codex mcp add sqlite -- npx -y mcp-sqlite-server

Write-Step "registering playwright MCP helper"
Reset-McpServer -Name "playwright"
codex mcp add playwright -- npx -y @playwright/mcp@latest --browser msedge --headless --isolated --output-dir $playwrightOutputDir

Write-Step "current MCP servers"
codex mcp list
