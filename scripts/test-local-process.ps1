$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ModulePath = Join-Path $PSScriptRoot "local-process.ps1"
. $ModulePath

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

Write-Host "[cyberai-local-test] local process helper tests passed."
