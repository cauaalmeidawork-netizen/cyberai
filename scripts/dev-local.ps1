param(
    [switch] $SkipMigrations
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ApiDir = Join-Path $Root "services/api"
$WebDir = Join-Path $Root "apps/web"
$ComposeFile = Join-Path $Root "infra/compose/docker-compose.yml"
$StateDir = Join-Path $Root ".data/local-dev"
$ApiLog = Join-Path $StateDir "api.log"
$WebLog = Join-Path $StateDir "web.log"
$ApiPidFile = Join-Path $StateDir "api.pid"
$WebPidFile = Join-Path $StateDir "web.pid"
$ProcessHelper = Join-Path $PSScriptRoot "local-process.ps1"
. $ProcessHelper

function Write-Step([string] $Message) {
    Write-CyberAILocalStep $Message
}

function Assert-Command([string] $Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Wait-HttpOk([string] $Url, [int] $TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                return
            }
        } catch {
            Start-Sleep -Milliseconds 750
        }
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for $Url."
}

function New-LocalSecret {
    $bytes = [byte[]]::new(32)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    return -join ($bytes | ForEach-Object { $_.ToString("x2") })
}

function Ensure-ApiEnv {
    $envPath = Join-Path $ApiDir ".env"
    if (Test-Path $envPath) {
        return
    }
    $sessionSecret = New-LocalSecret
    $csrfSecret = New-LocalSecret
    @"
CYBERAI_ENVIRONMENT=local
CYBERAI_DEBUG=true
CYBERAI_LOGGING__LEVEL=DEBUG
CYBERAI_LOGGING__FORMAT=console
CYBERAI_DATABASE__URL=postgresql+asyncpg://cyberai:cyberai_dev_password@localhost:5432/cyberai
CYBERAI_REDIS__URL=redis://localhost:6379/0
CYBERAI_APP__CORS_ORIGINS=["http://localhost:3000"]
CYBERAI_APP__TRUSTED_HOSTS=["localhost","127.0.0.1","testserver"]
CYBERAI_APP__EXPOSE_DOCS=true
CYBERAI_AUTH__JWT_SECRET=cyberai_dev_jwt_secret_do_not_use_in_prod
CYBERAI_AUTH__LEGACY_BEARER_ENABLED=true
CYBERAI_AUTH__OIDC_ENABLED=false
CYBERAI_AUTH__OIDC_AUTO_PROVISION_ENABLED=false
CYBERAI_AUTH__SESSION_SECURE_COOKIE=false
CYBERAI_AUTH__SESSION_SAMESITE=lax
CYBERAI_AUTH__SESSION_SECRET=$sessionSecret
CYBERAI_AUTH__CSRF_SECRET=$csrfSecret
CYBERAI_OPENAI_COMPATIBLE__ENABLED=true
CYBERAI_OPENAI_COMPATIBLE__API_KEY=ollama
CYBERAI_OPENAI_COMPATIBLE__BASE_URL=http://localhost:11434/v1
CYBERAI_OPENAI_COMPATIBLE__MODEL=qwen2.5:3b
CYBERAI_OPENAI_COMPATIBLE__MODEL_KEY=openai-compatible-chat
CYBERAI_OPENAI_COMPATIBLE__DISPLAY_NAME=Qwen 2.5 3B Local
CYBERAI_MODELS__DEFAULT_MODEL=openai-compatible-chat
CYBERAI_MODELS__FALLBACK_MODELS=[]
CYBERAI_BILLING__ENABLED=true
CYBERAI_BILLING__PROVIDER=none
CYBERAI_BILLING__RATE_LIMIT_FAIL_OPEN=true
CYBERAI_POLICY__ENABLED=true
CYBERAI_POLICY__PROFILE=default
"@ | Set-Content -NoNewline -Encoding utf8 $envPath
    Write-Step "Created services/api/.env with local Ollama settings."
}

function Ensure-WebEnv {
    $envPath = Join-Path $WebDir ".env.local"
    if (Test-Path $envPath) {
        return
    }
    @"
API_PROXY_TARGET=http://localhost:8001
NEXT_PUBLIC_API_BASE_URL=
"@ | Set-Content -NoNewline -Encoding utf8 $envPath
    Write-Step "Created apps/web/.env.local for same-origin proxying."
}

function Start-LoggedProcess(
    [string] $Name,
    [string] $WorkingDirectory,
    [string] $Command,
    [string] $LogPath,
    [string] $PidPath
) {
    $errorLogPath = $LogPath -replace "\.log$", ".err.log"
    Clear-StalePidFile -Path $PidPath -Name $Name -Root $Root -ExcludeProcessIds (Get-CurrentProcessLineageIds)
    if (Test-Path $LogPath) {
        Remove-Item -LiteralPath $LogPath -Force
    }
    if (Test-Path $errorLogPath) {
        Remove-Item -LiteralPath $errorLogPath -Force
    }
    $workingDirectoryLiteral = ConvertTo-PowerShellSingleQuotedString $WorkingDirectory
    $wrappedCommand = "Set-Location -LiteralPath $workingDirectoryLiteral; $Command"
    $process = Start-Process `
        -FilePath "powershell" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $wrappedCommand) `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $LogPath `
        -RedirectStandardError $errorLogPath `
        -PassThru `
        -WindowStyle Hidden
    Set-Content -NoNewline -Encoding ascii -Path $PidPath -Value ([string] $process.Id)
    Write-Step "$Name started with PID $($process.Id). Logs: $LogPath and $errorLogPath"
}

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

$currentLineage = Get-CurrentProcessLineageIds
Write-Step "Cleaning up stale CyberAI local processes."
Clear-StalePidFile -Path $ApiPidFile -Name "FastAPI" -Root $Root -ExcludeProcessIds $currentLineage
Clear-StalePidFile -Path $WebPidFile -Name "Next.js" -Root $Root -ExcludeProcessIds $currentLineage
Stop-CyberAIListenersOnPort -Port 8001 -Name "FastAPI" -Root $Root -ExcludeProcessIds $currentLineage -FailOnExternal
Stop-CyberAIListenersOnPort -Port 3000 -Name "Next.js" -Root $Root -ExcludeProcessIds $currentLineage -FailOnExternal
Stop-CyberAIOrphanProcesses -Root $Root -ExcludeProcessIds $currentLineage
Assert-PortAvailable -Port 8001 -Name "CyberAI API" -Root $Root -ExcludeProcessIds $currentLineage
Assert-PortAvailable -Port 3000 -Name "CyberAI web" -Root $Root -ExcludeProcessIds $currentLineage

Write-Step "Validating local dependencies."
Assert-Command "docker"
Assert-Command "uv"
Assert-Command "npm"
docker info | Out-Null

try {
    $models = Invoke-RestMethod -Uri "http://127.0.0.1:11434/v1/models" -Method Get -TimeoutSec 5
} catch {
    throw "Ollama is not reachable at http://127.0.0.1:11434. Start Ollama before running this script."
}
if (-not (@($models.data) | Where-Object { $_.id -eq "qwen2.5:3b" })) {
    throw "Ollama is reachable, but model qwen2.5:3b is not installed. Run: ollama pull qwen2.5:3b"
}

Ensure-ApiEnv
Ensure-WebEnv

Write-Step "Starting PostgreSQL and Redis containers."
docker compose -f $ComposeFile up -d postgres redis | Out-Null

Write-Step "Waiting for PostgreSQL and Redis health."
docker compose -f $ComposeFile ps postgres redis

if (-not $SkipMigrations) {
    Write-Step "Running Alembic migrations."
    Push-Location $ApiDir
    try {
        uv run alembic upgrade head
    } finally {
        Pop-Location
    }
}

Write-Step "Starting FastAPI on http://localhost:8001."
Start-LoggedProcess `
    -Name "FastAPI" `
    -WorkingDirectory $ApiDir `
    -Command "uv run uvicorn cyberai.main:create_app --factory --host 127.0.0.1 --port 8001 --reload" `
    -LogPath $ApiLog `
    -PidPath $ApiPidFile

Write-Step "Waiting for API liveness."
Wait-HttpOk "http://127.0.0.1:8001/healthz" 45

Write-Step "Starting Next.js on http://localhost:3000."
Start-LoggedProcess `
    -Name "Next.js" `
    -WorkingDirectory $WebDir `
    -Command "`$env:API_PROXY_TARGET='http://localhost:8001'; `$env:NEXT_PUBLIC_API_BASE_URL=''; npm run dev -- --hostname 127.0.0.1 --port 3000" `
    -LogPath $WebLog `
    -PidPath $WebPidFile

Write-Step "Waiting for web server."
Wait-HttpOk "http://127.0.0.1:3000" 60

Write-Step "Local stack is ready."
Write-Host "Open: http://localhost:3000"
Write-Host "API:  http://localhost:8001"
Write-Host "Logs:"
Write-Host "  Get-Content -Wait $ApiLog"
Write-Host "  Get-Content -Wait $($ApiLog -replace '\.log$', '.err.log')"
Write-Host "  Get-Content -Wait $WebLog"
Write-Host "  Get-Content -Wait $($WebLog -replace '\.log$', '.err.log')"
