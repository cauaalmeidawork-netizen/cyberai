$ErrorActionPreference = "Stop"

$CookieJar = Join-Path $env:TEMP "nomercy-local-cookies.txt"
if (Test-Path $CookieJar) {
    Remove-Item -LiteralPath $CookieJar -Force
}

function Assert-True([bool] $Condition, [string] $Message) {
    if (-not $Condition) {
        throw $Message
    }
}

function New-JsonPayloadFile([string] $Json) {
    $path = Join-Path $env:TEMP "nomercy-payload-$([guid]::NewGuid()).json"
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($path, $Json, $encoding)
    return $path
}

# ── Pre-flight checks ────────────────────────────────────────────────────────

$health = Invoke-RestMethod -Uri "http://localhost:8001/healthz" -TimeoutSec 5
Assert-True ($health.status -eq "ok") "API healthz failed."

$ollamaModels = Invoke-RestMethod -Uri "http://127.0.0.1:11434/v1/models" -TimeoutSec 5
$hasDolphin = @($ollamaModels.data | Where-Object { $_.id -eq "dolphin3:8b" }).Count -gt 0
Assert-True $hasDolphin "dolphin3:8b not found in Ollama models."

# ── Auth ──────────────────────────────────────────────────────────────────────

curl.exe -sS -L -c $CookieJar -b $CookieJar `
    "http://localhost:3000/api/v1/auth/dev-login?return_to=%2F" | Out-Null

$me = (curl.exe -sS -b $CookieJar "http://localhost:3000/api/v1/auth/me") | ConvertFrom-Json
Assert-True ([bool] $me.user_id) "Local auth/me failed."
Assert-True ($me.role -eq "owner") "Local auth role was not owner."

$models = Invoke-RestMethod -Uri "http://localhost:3000/api/v1/models" -TimeoutSec 10
Assert-True ($models.default_model -eq "openai-compatible-chat") "Unexpected default model."
$dolphin = @(
    $models.data | Where-Object {
        $_.key -eq "openai-compatible-chat" -and $_.display_name -eq "Dolphin 3 8B"
    }
)
Assert-True ($dolphin.Count -gt 0) "Dolphin local model display not found."

$csrfLine = Get-Content $CookieJar | Where-Object { $_ -match "cyberai_csrf" } | Select-Object -Last 1
$csrf = ($csrfLine -split "`t")[-1]
Assert-True ([bool] $csrf) "CSRF cookie not found."

# ── Create isolated test project ──────────────────────────────────────────────

$smokeProjectName = "__smoke_test__"
$smokeProjectId = $null
$smokeConversationId = $null

try {
    $projectBody = @{ name = $smokeProjectName; description = "Smoke test workspace - auto-created, safe to delete" } | ConvertTo-Json -Compress
    $projectBodyFile = New-JsonPayloadFile $projectBody
    $project = (
        curl.exe -sS -b $CookieJar -c $CookieJar `
            -H "X-CSRF-Token: $csrf" `
            -H "Content-Type: application/json" `
            -X POST --data-binary "@$projectBodyFile" `
            "http://localhost:3000/api/v1/projects"
    ) | ConvertFrom-Json
    Remove-Item -LiteralPath $projectBodyFile -Force
    $smokeProjectId = $project.id
    Assert-True ([bool] $smokeProjectId) "Failed to create smoke test project."

    # ── Create isolated test conversation ──────────────────────────────────────

    $conversationBody = @{ title = "__smoke_test__" } | ConvertTo-Json -Compress
    $conversationBodyFile = New-JsonPayloadFile $conversationBody
    $conversation = (
        curl.exe -sS -b $CookieJar -c $CookieJar `
            -H "X-CSRF-Token: $csrf" `
            -H "Content-Type: application/json" `
            -X POST --data-binary "@$conversationBodyFile" `
            "http://localhost:3000/api/v1/projects/$smokeProjectId/conversations"
    ) | ConvertFrom-Json
    Remove-Item -LiteralPath $conversationBodyFile -Force
    $smokeConversationId = $conversation.id
    Assert-True ([bool] $smokeConversationId) "Failed to create smoke test conversation."

    # ── Send test message ──────────────────────────────────────────────────────

    $payload = @{
        messages = @(@{
            role = "user"
            content = "Comece com o marcador exato NMAP_SV_OK. Depois explique em uma frase o que faz nmap -sV."
        })
        model = "openai-compatible-chat"
        max_tokens = 96
        temperature = 0.0
        rag_enabled = $false
    } | ConvertTo-Json -Depth 10 -Compress
    $payloadFile = New-JsonPayloadFile $payload

    $stream = curl.exe -sS -N -b $CookieJar -c $CookieJar `
        -H "X-CSRF-Token: $csrf" `
        -H "Idempotency-Key: $([guid]::NewGuid().ToString())" `
        -H "Accept: text/event-stream" `
        -H "Content-Type: application/json" `
        -X POST --data-binary "@$payloadFile" `
        "http://localhost:3000/api/v1/projects/$smokeProjectId/conversations/$smokeConversationId/messages"
    Remove-Item -LiteralPath $payloadFile -Force

    $streamText = $stream -join "`n"
    function Get-StreamTextDelta([string] $SseText) {
        $builder = [System.Text.StringBuilder]::new()
        foreach ($line in ($SseText -split "`n")) {
            if (-not $line.StartsWith("data: ")) {
                continue
            }
            $data = $line.Substring(6).Trim()
            if ($data -eq "[DONE]" -or -not $data.StartsWith("{")) {
                continue
            }
            $event = $data | ConvertFrom-Json
            if ($event.event -eq "delta") {
                [void] $builder.Append([string] $event.text)
            }
        }
        return $builder.ToString()
    }

    $responseText = Get-StreamTextDelta $streamText
    if (-not ($responseText -match "NMAP_SV_OK")) {
        Write-Host "[smoke] Unexpected model response: $responseText"
    }
    Assert-True ($responseText -match "NMAP_SV_OK") "Expected legitimate cybersecurity response marker not found."
    Assert-True (($responseText -match "(?i)-sV") -and ($responseText -match "(?i)servi|vers.o")) `
        "Expected a substantive explanation of nmap -sV."
    Assert-True (-not ($streamText -match "(?i)policy_denied|blocked by security policy|bloquead[oa] pela pol.tica")) `
        "Legitimate cybersecurity prompt was blocked by policy."
    Assert-True (-not ($responseText -match "(?i)n.o posso ajudar|cannot assist|can't assist|i can't help|recuso")) `
        "Local model returned a generic refusal for a legitimate cybersecurity prompt."
    Assert-True (-not ($streamText -match "MockModelProvider|mock-analyst")) "Stream indicates mock provider/model."

    # ── Verify usage record ────────────────────────────────────────────────────

    $usage = docker exec cyberai-postgres psql -U cyberai -d cyberai -tA -c `
        "SELECT provider || '|' || model_key || '|' || provider_model FROM usage_records ORDER BY occurred_at DESC LIMIT 1;"
    $usage = $usage.Trim()
    Assert-True ($usage -eq "openai-compatible|openai-compatible-chat|dolphin3:8b") `
        "Unexpected latest usage provider/model: $usage"

    [pscustomobject]@{
        api_health = $health.status
        model = $models.default_model
        display = $dolphin[0].display_name
        auth_role = $me.role
        project = $project.name
        conversation = $conversation.title
        provider_usage = $usage
        response_marker = "NMAP_SV_OK"
    } | ConvertTo-Json -Compress

} finally {
    # ── Mandatory cleanup ──────────────────────────────────────────────────────
    # Delete the smoke test conversation and project, regardless of test outcome.

    if ($smokeConversationId -and $smokeProjectId) {
        try {
            curl.exe -sS -b $CookieJar `
                -H "X-CSRF-Token: $csrf" `
                -X DELETE `
                "http://localhost:3000/api/v1/projects/$smokeProjectId/conversations/$smokeConversationId" | Out-Null
            Write-Host "[smoke] Cleaned up test conversation $smokeConversationId"
        } catch {
            Write-Warning "[smoke] Failed to delete test conversation: $_"
        }
    }

    if ($smokeProjectId) {
        try {
            curl.exe -sS -b $CookieJar `
                -H "X-CSRF-Token: $csrf" `
                -X DELETE `
                "http://localhost:3000/api/v1/projects/$smokeProjectId" | Out-Null
            Write-Host "[smoke] Cleaned up test project $smokeProjectId"
        } catch {
            Write-Warning "[smoke] Failed to delete test project: $_"
        }
    }

    if (Test-Path $CookieJar) {
        Remove-Item -LiteralPath $CookieJar -Force -ErrorAction SilentlyContinue
    }
}
