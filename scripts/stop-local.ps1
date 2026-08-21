$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$StateDir = Join-Path $Root ".data/local-dev"
$ComposeFile = Join-Path $Root "infra/compose/docker-compose.yml"
$ProcessHelper = Join-Path $PSScriptRoot "local-process.ps1"
. $ProcessHelper
$PidFiles = @(
    @{ Name = "FastAPI"; Path = (Join-Path $StateDir "api.pid") },
    @{ Name = "Next.js"; Path = (Join-Path $StateDir "web.pid") }
)

function Write-Step([string] $Message) {
    Write-CyberAILocalStep $Message
}

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$currentLineage = Get-CurrentProcessLineageIds

foreach ($entry in $PidFiles) {
    Clear-StalePidFile -Path $entry.Path -Name $entry.Name -Root $Root -ExcludeProcessIds $currentLineage
}

Stop-CyberAIListenersOnPort -Port 8001 -Name "FastAPI" -Root $Root -ExcludeProcessIds $currentLineage -FailOnExternal
Stop-CyberAIListenersOnPort -Port 3000 -Name "Next.js" -Root $Root -ExcludeProcessIds $currentLineage -FailOnExternal
Stop-CyberAIOrphanProcesses -Root $Root -ExcludeProcessIds $currentLineage
Wait-PortFree -Port 8001 -TimeoutSeconds 15
Wait-PortFree -Port 3000 -TimeoutSeconds 15

if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Step "Stopping CyberAI PostgreSQL and Redis containers."
    docker compose -f $ComposeFile stop postgres redis | Out-Null
}

Assert-PortNotListening -Port 8001
Assert-PortNotListening -Port 3000
Write-Step "Local stack stopped."
