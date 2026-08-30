function Set-LocalEnvValue([string] $Path, [string] $Name, [string] $Value) {
    $line = "$Name=$Value"
    if (-not (Test-Path $Path)) {
        Set-Content -NoNewline -Encoding utf8 $Path $line
        return
    }
    $lines = @(Get-Content $Path -ErrorAction SilentlyContinue)
    $updated = $false
    $nextLines = $lines | ForEach-Object {
        if ($_ -match "^$([regex]::Escape($Name))=") {
            $updated = $true
            $line
        } else {
            $_
        }
    }
    if (-not $updated) {
        $nextLines += $line
    }
    Set-Content -Encoding utf8 $Path $nextLines
}

function Set-LocalApiRuntimeValues([string] $Path) {
    Set-LocalEnvValue $Path "CYBERAI_APP__REQUEST_TIMEOUT_SECONDS" "120"
    Set-LocalEnvValue $Path "CYBERAI_REDIS__URL" "redis://127.0.0.1:6379/0"
    Set-LocalEnvValue $Path "CYBERAI_REDIS__SOCKET_TIMEOUT_SECONDS" "0.25"
    Set-LocalEnvValue $Path "CYBERAI_REDIS__SOCKET_CONNECT_TIMEOUT_SECONDS" "0.25"
    Set-LocalEnvValue $Path "CYBERAI_INFERENCE__REQUEST_TIMEOUT_SECONDS" "300"
    Set-LocalEnvValue $Path "CYBERAI_INFERENCE__FIRST_TOKEN_TIMEOUT_SECONDS" "120"
    Set-LocalEnvValue $Path "CYBERAI_OPENAI_COMPATIBLE__ENABLED" "true"
    Set-LocalEnvValue $Path "CYBERAI_OPENAI_COMPATIBLE__API_KEY" "ollama"
    Set-LocalEnvValue $Path "CYBERAI_OPENAI_COMPATIBLE__BASE_URL" "http://localhost:11434/v1"
    Set-LocalEnvValue $Path "CYBERAI_OPENAI_COMPATIBLE__MODEL" "dolphin3:8b"
    Set-LocalEnvValue $Path "CYBERAI_OPENAI_COMPATIBLE__MODEL_KEY" "openai-compatible-chat"
    Set-LocalEnvValue $Path "CYBERAI_OPENAI_COMPATIBLE__DISPLAY_NAME" "Dolphin 3 8B"
    Set-LocalEnvValue $Path "CYBERAI_OPENAI_COMPATIBLE__KEEP_ALIVE" "30m"
    Set-LocalEnvValue $Path "CYBERAI_OPENAI_COMPATIBLE__REQUEST_TIMEOUT_SECONDS" "300"
    Set-LocalEnvValue $Path "CYBERAI_MODELS__DEFAULT_MODEL" "openai-compatible-chat"
    Set-LocalEnvValue $Path "CYBERAI_MODELS__FALLBACK_MODELS" "[]"
}
