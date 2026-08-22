$ErrorActionPreference = "Stop"

<#
.SYNOPSIS
    Remove test-pollution data created by previous smoke-local.ps1 runs.

.DESCRIPTION
    This script authenticates via dev-login, lists all conversations across
    all projects, and deletes ONLY those that are unmistakably smoke-test
    artifacts. It logs every action.

    Safe-to-delete indicators:
    - Conversation title is "__smoke_test__"
    - Project name is "__smoke_test__"
    - Conversation whose messages contain "CYBERAI_LOCAL_OK" or "NOMERCY_LOCAL_OK"
      and title is "New conversation"

    Real user conversations are NEVER deleted.
#>

$CookieJar = Join-Path $env:TEMP "nomercy-cleanup-cookies.txt"
if (Test-Path $CookieJar) { Remove-Item -LiteralPath $CookieJar -Force }

function New-JsonPayloadFile([string] $Json) {
    $path = Join-Path $env:TEMP "nomercy-payload-$([guid]::NewGuid()).json"
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($path, $Json, $encoding)
    return $path
}

# ── Auth ──────────────────────────────────────────────────────────────────────

Write-Host "[cleanup] Authenticating..."
curl.exe -sS -L -c $CookieJar -b $CookieJar `
    "http://localhost:3000/api/v1/auth/dev-login?return_to=%2F" | Out-Null

$me = (curl.exe -sS -b $CookieJar "http://localhost:3000/api/v1/auth/me") | ConvertFrom-Json
if (-not $me.user_id) {
    throw "Authentication failed."
}

$csrfLine = Get-Content $CookieJar | Where-Object { $_ -match "cyberai_csrf" } | Select-Object -Last 1
$csrf = ($csrfLine -split "`t")[-1]

Write-Host "[cleanup] Authenticated as user $($me.user_id), role=$($me.role)"

# ── Enumerate projects ────────────────────────────────────────────────────────

$projects = @(
    (curl.exe -sS -b $CookieJar "http://localhost:3000/api/v1/projects") | ConvertFrom-Json
)
Write-Host "[cleanup] Found $($projects.Count) project(s)"

$deletedConversations = 0
$deletedProjects = 0
$preservedConversations = 0

foreach ($project in $projects) {
    Write-Host "[cleanup] Inspecting project '$($project.name)' ($($project.id))"

    # Delete entire __smoke_test__ projects
    if ($project.name -eq "__smoke_test__") {
        Write-Host "[cleanup]   -> Project is a smoke test artifact. Deleting..."
        curl.exe -sS -b $CookieJar `
            -H "X-CSRF-Token: $csrf" `
            -X DELETE `
            "http://localhost:3000/api/v1/projects/$($project.id)" | Out-Null
        $deletedProjects++
        continue
    }

    $conversations = @(
        (curl.exe -sS -b $CookieJar `
            "http://localhost:3000/api/v1/projects/$($project.id)/conversations") | ConvertFrom-Json
    )

    foreach ($conversation in $conversations) {
        $isTestArtifact = $false
        $reason = ""

        # Check title
        if ($conversation.title -eq "__smoke_test__") {
            $isTestArtifact = $true
            $reason = "title is __smoke_test__"
        }

        # Check if "New conversation" with test content
        if (-not $isTestArtifact -and $conversation.title -eq "New conversation") {
            try {
                $messagesResp = (curl.exe -sS -b $CookieJar `
                    "http://localhost:3000/api/v1/projects/$($project.id)/conversations/$($conversation.id)/messages?limit=10&offset=0") | ConvertFrom-Json
                $msgs = @($messagesResp.messages)
                $hasTestMarker = $false
                foreach ($msg in $msgs) {
                    if ($msg.content -match "CYBERAI_LOCAL_OK|NOMERCY_LOCAL_OK|MockModelProvider") {
                        $hasTestMarker = $true
                        break
                    }
                }
                if ($hasTestMarker) {
                    $isTestArtifact = $true
                    $reason = "title 'New conversation' with test marker in messages"
                }
            } catch {
                Write-Warning "[cleanup]   Could not fetch messages for conversation $($conversation.id): $_"
            }
        }

        if ($isTestArtifact) {
            Write-Host "[cleanup]   -> Deleting conversation '$($conversation.title)' ($($conversation.id)): $reason"
            curl.exe -sS -b $CookieJar `
                -H "X-CSRF-Token: $csrf" `
                -X DELETE `
                "http://localhost:3000/api/v1/projects/$($project.id)/conversations/$($conversation.id)" | Out-Null
            $deletedConversations++
        } else {
            Write-Host "[cleanup]   -> Preserving conversation '$($conversation.title)' ($($conversation.id))"
            $preservedConversations++
        }
    }
}

# ── Also clean via direct SQL for orphaned records ────────────────────────────
# Only delete messages matching known test markers in conversations titled
# "New conversation" or "__smoke_test__"

try {
    Write-Host "[cleanup] Cleaning orphaned test records via SQL..."
    $sqlCleanup = @"
DELETE FROM chat_idempotency_keys
WHERE user_message_id IN (
    SELECT m.id FROM messages m
    JOIN conversations c ON m.conversation_id = c.id
    WHERE c.title IN ('New conversation', '__smoke_test__')
    AND (
        m.content LIKE '%CYBERAI_LOCAL_OK%'
        OR m.content LIKE '%NOMERCY_LOCAL_OK%'
        OR m.content LIKE '%MockModelProvider%'
        OR m.content LIKE '%mock-analyst%'
    )
) OR assistant_message_id IN (
    SELECT m.id FROM messages m
    JOIN conversations c ON m.conversation_id = c.id
    WHERE c.title IN ('New conversation', '__smoke_test__')
    AND (
        m.content LIKE '%CYBERAI_LOCAL_OK%'
        OR m.content LIKE '%NOMERCY_LOCAL_OK%'
        OR m.content LIKE '%MockModelProvider%'
        OR m.content LIKE '%mock-analyst%'
    )
);

DELETE FROM messages
WHERE id IN (
    SELECT m.id FROM messages m
    JOIN conversations c ON m.conversation_id = c.id
    WHERE c.title IN ('New conversation', '__smoke_test__')
    AND (
        m.content LIKE '%CYBERAI_LOCAL_OK%'
        OR m.content LIKE '%NOMERCY_LOCAL_OK%'
        OR m.content LIKE '%MockModelProvider%'
        OR m.content LIKE '%mock-analyst%'
    )
);
"@
    $result = docker exec cyberai-postgres psql -U cyberai -d cyberai -c $sqlCleanup
    Write-Host "[cleanup] SQL cleanup result: $result"
} catch {
    Write-Warning "[cleanup] SQL cleanup skipped or failed: $_"
}

# ── Summary ───────────────────────────────────────────────────────────────────

if (Test-Path $CookieJar) { Remove-Item -LiteralPath $CookieJar -Force -ErrorAction SilentlyContinue }

Write-Host ""
Write-Host "[cleanup] Done."
Write-Host "[cleanup]   Deleted conversations: $deletedConversations"
Write-Host "[cleanup]   Deleted projects:      $deletedProjects"
Write-Host "[cleanup]   Preserved:             $preservedConversations"
