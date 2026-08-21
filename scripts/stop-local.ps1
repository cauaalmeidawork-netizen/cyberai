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

function Stop-ProcessTree([int] $ProcessId, [string] $Name) {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        return
    }

    Write-Step "Stopping $Name process tree rooted at PID $ProcessId."
    $taskkill = Get-Command taskkill.exe -ErrorAction SilentlyContinue
    if ($taskkill) {
        & $taskkill.Source /PID $ProcessId /T /F | Out-Null
        if ($LASTEXITCODE -ne 0 -and (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {
            throw "Failed to stop $Name process tree rooted at PID $ProcessId."
        }
        return
    }

    Stop-Process -Id $ProcessId -Force
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
    Stop-ProcessTree -ProcessId $pidValue -Name $entry.Name
    Remove-Item -LiteralPath $entry.Path -Force
}

if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Step "Stopping CyberAI PostgreSQL and Redis containers."
    docker compose -f $ComposeFile stop postgres redis | Out-Null
}

Write-Step "Local stack stopped."
