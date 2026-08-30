$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ModulePath = Join-Path $PSScriptRoot "local-process.ps1"
$EnvModulePath = Join-Path $PSScriptRoot "local-env.ps1"
. $ModulePath
. $EnvModulePath

function Assert-True([bool] $Condition, [string] $Message) {
    if (-not $Condition) {
        throw $Message
    }
}

function New-FakeProcessInfo(
    [int] $ProcessId,
    [int] $ParentProcessId,
    [string] $Name,
    [string] $CommandLine
) {
    [pscustomobject]@{
        ProcessId = $ProcessId
        ParentProcessId = $ParentProcessId
        Name = $Name
        CommandLine = $CommandLine
        ExecutablePath = $null
    }
}

$cyberAiWeb = New-FakeProcessInfo `
    -ProcessId 1001 `
    -ParentProcessId 1000 `
    -Name "node.exe" `
    -CommandLine "`"C:\Program Files\nodejs\node.exe`" `"$Root\apps\web\node_modules\next\dist\server\lib\start-server.js`""
Assert-True (Test-CyberAIProcess -ProcessInfo $cyberAiWeb -Root $Root) `
    "Expected a Next.js process under the repository root to be classified as CyberAI."

$externalNode = New-FakeProcessInfo `
    -ProcessId 1002 `
    -ParentProcessId 1000 `
    -Name "node.exe" `
    -CommandLine "`"C:\Program Files\nodejs\node.exe`" C:\OtherProject\server.js"
Assert-True (-not (Test-CyberAIProcess -ProcessInfo $externalNode -Root $Root)) `
    "Expected an external Node process to be rejected."

$legacyApiWrapper = New-FakeProcessInfo `
    -ProcessId 1003 `
    -ParentProcessId 1000 `
    -Name "powershell.exe" `
    -CommandLine "powershell -NoProfile -Command uv run uvicorn cyberai.main:create_app --factory --host 127.0.0.1 --port 8001 --reload"
Assert-True (Test-CyberAIProcess -ProcessInfo $legacyApiWrapper -Root $Root) `
    "Expected a legacy CyberAI FastAPI wrapper to be classified as CyberAI."

$legacyWebWrapper = New-FakeProcessInfo `
    -ProcessId 1004 `
    -ParentProcessId 1000 `
    -Name "powershell.exe" `
    -CommandLine "powershell -NoProfile -Command `$env:API_PROXY_TARGET='http://localhost:8001'; npm run dev -- --hostname 127.0.0.1 --port 3000"
Assert-True (Test-CyberAIProcess -ProcessInfo $legacyWebWrapper -Root $Root) `
    "Expected a legacy CyberAI Next.js wrapper to be classified as CyberAI."

$currentIds = Get-CurrentProcessLineageIds
Assert-True ($currentIds -contains $PID) "Expected current PID to be excluded from cleanup candidates."

$externalMessage = Format-ExternalProcessMessage -Port 3000 -ProcessInfo $externalNode
Assert-True ($externalMessage -match "Port 3000 is owned by an external process") `
    "Expected external process message to identify the port owner."
Assert-True ($externalMessage -match "Refusing to terminate it") `
    "Expected external process message to refuse termination."

$envTestDirectory = Join-Path `
    ([System.IO.Path]::GetTempPath()) `
    ("nomercy-local-env-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $envTestDirectory | Out-Null
try {
    $envTestPath = Join-Path $envTestDirectory ".env"
    @(
        "CYBERAI_OPENAI_COMPATIBLE__MODEL=legacy-local:3b"
        "CYBERAI_OPENAI_COMPATIBLE__DISPLAY_NAME=Legacy Local Model"
        "CYBERAI_MODELS__DEFAULT_MODEL=mock-analyst-1"
        "CUSTOM_VALUE=preserved"
    ) | Set-Content -Encoding utf8 $envTestPath

    Set-LocalApiRuntimeValues -Path $envTestPath
    $migratedEnv = Get-Content -Raw $envTestPath
    Assert-True ($migratedEnv -match '(?m)^CYBERAI_OPENAI_COMPATIBLE__MODEL=dolphin3:8b\r?$') `
        "Expected an existing API .env to migrate to dolphin3:8b."
    Assert-True ($migratedEnv -match '(?m)^CYBERAI_OPENAI_COMPATIBLE__DISPLAY_NAME=Dolphin 3 8B\r?$') `
        "Expected the migrated API .env to display Dolphin 3 8B."
    Assert-True ($migratedEnv -match '(?m)^CYBERAI_INFERENCE__FIRST_TOKEN_TIMEOUT_SECONDS=120\r?$') `
        "Expected the migrated API .env to allow enough time for the local 8B model."
    Assert-True ($migratedEnv -match '(?m)^CYBERAI_APP__REQUEST_TIMEOUT_SECONDS=120\r?$') `
        "Expected the migrated API .env to keep the global HTTP timeout bounded."
    Assert-True ($migratedEnv -match '(?m)^CYBERAI_MODELS__DEFAULT_MODEL=openai-compatible-chat\r?$') `
        "Expected the migrated API .env to select the local provider by default."
    Assert-True ($migratedEnv -match '(?m)^CUSTOM_VALUE=preserved\r?$') `
        "Expected API .env migration to preserve unrelated values."
} finally {
    $resolvedEnvTestDirectory = (Resolve-Path -LiteralPath $envTestDirectory).Path
    $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    Assert-True ($resolvedEnvTestDirectory.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) `
        "Refusing to remove a test directory outside the system temp directory."
    Remove-Item -LiteralPath $resolvedEnvTestDirectory -Recurse -Force
}

Write-Host "[nomercy-local-test] local process helper tests passed."
