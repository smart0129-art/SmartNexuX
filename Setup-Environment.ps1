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

$lines = [System.IO.File]::ReadAllLines($environmentPath)
$secretIndex = -1
for ($index = 0; $index -lt $lines.Length; $index++) {
    if ($lines[$index] -match "^SESSION_SECRET=") {
        $secretIndex = $index
        break
    }
}

if ($secretIndex -lt 0 -or [string]::IsNullOrWhiteSpace(($lines[$secretIndex] -replace "^SESSION_SECRET=", ""))) {
    $bytes = New-Object byte[] 48
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $random.GetBytes($bytes)
    }
    finally {
        $random.Dispose()
    }

    $secret = [Convert]::ToBase64String($bytes)
    if ($secretIndex -lt 0) {
        $lines += "SESSION_SECRET=$secret"
    }
    else {
        $lines[$secretIndex] = "SESSION_SECRET=$secret"
    }
    [System.IO.File]::WriteAllLines(
        $environmentPath,
        $lines,
        (New-Object System.Text.UTF8Encoding($false))
    )
    Write-Output "Created .env and generated a local session secret."
}
else {
    Write-Output "Using existing .env and session secret."
}
