$ErrorActionPreference = "Stop"

$environmentPath = Join-Path $PSScriptRoot ".env"
$examplePath = Join-Path $PSScriptRoot ".env.example"

if (-not (Test-Path $environmentPath)) {
    if (-not (Test-Path $examplePath)) {
        Write-Error ".env.example is missing."
        exit 1
    }
    Copy-Item $examplePath $environmentPath
}

$lines = New-Object "System.Collections.Generic.List[string]"
$lines.AddRange([System.IO.File]::ReadAllLines($environmentPath))

function Set-EnvironmentDefault {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowEmptyString()][string]$DefaultValue
    )

    $pattern = "^\s*$([regex]::Escape($Name))\s*=\s*(.*)$"
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match $pattern) {
            if ([string]::IsNullOrWhiteSpace($Matches[1]) -and $DefaultValue -ne "") {
                $lines[$index] = "$Name=$DefaultValue"
                return $true
            }
            return $false
        }
    }

    $lines.Add("$Name=$DefaultValue")
    return $true
}

$secretLine = $lines | Where-Object { $_ -match "^\s*SESSION_SECRET\s*=" } | Select-Object -First 1
$secret = ""
if ($secretLine -match "^\s*SESSION_SECRET\s*=\s*(.*)$") {
    $secret = $Matches[1].Trim()
}
if ([string]::IsNullOrWhiteSpace($secret)) {
    $bytes = New-Object byte[] 48
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $random.GetBytes($bytes)
    }
    finally {
        $random.Dispose()
    }
    $secret = [Convert]::ToBase64String($bytes)
}

$changed = Set-EnvironmentDefault -Name "SESSION_SECRET" -DefaultValue $secret
$defaults = [ordered]@{
    ADMIN_EMAIL = "admin@nexux.local"
    ADMIN_PASSWORD = "ChangeMeNow123!"
    NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000"
    FRONTEND_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
    COOKIE_SECURE = "false"
    CHAT_DEFAULT_PROVIDER = "ollama"
    OLLAMA_CHAT_MODELS = "qwen2.5vl:3b"
    OPENAI_BASE_URL = "https://api.openai.com/v1"
    OPENAI_API_KEY = ""
    OPENAI_CHAT_MODELS = "gemini-3.5-flash-lite"
}
foreach ($entry in $defaults.GetEnumerator()) {
    if (Set-EnvironmentDefault -Name $entry.Key -DefaultValue $entry.Value) {
        $changed = $true
    }
}

if ($changed) {
    $finalText = ($lines -join [Environment]::NewLine) + [Environment]::NewLine
    [System.IO.File]::WriteAllText($environmentPath, $finalText, (New-Object System.Text.UTF8Encoding($false)))
    Write-Output "Local environment defaults prepared; existing values were preserved"
}
else {
    Write-Output "Using existing local environment settings"
}
