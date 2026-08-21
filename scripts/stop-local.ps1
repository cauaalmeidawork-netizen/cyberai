$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$StateDir = Join-Path $Root ".data/local-dev"
$ComposeFile = Join-Path $Root "infra/compose/docker-compose.yml"
$PidFiles = @(
    @{ Name = "FastAPI"; Path = (Join-Path $StateDir "api.pid") },
    @{ Name = "Next.js"; Path = (Join-Path $StateDir "web.pid") }
)

function Write-Step([string] $Message) {
    Write-Host "[cyberai-local] $Message"
}

foreach ($entry in $PidFiles) {
    if (-not (Test-Path $entry.Path)) {
        continue
    }
    $rawPid = Get-Content $entry.Path -ErrorAction SilentlyContinue
    if (-not $rawPid) {
        Remove-Item -LiteralPath $entry.Path -Force
        continue
    }
    $pidValue = [int] $rawPid
    $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if ($process) {
        Write-Step "Stopping $($entry.Name) PID $pidValue."
        Stop-Process -Id $pidValue -Force
    }
    Remove-Item -LiteralPath $entry.Path -Force
}

if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Step "Stopping CyberAI PostgreSQL and Redis containers."
    docker compose -f $ComposeFile stop postgres redis | Out-Null
}

Write-Step "Local stack stopped."
