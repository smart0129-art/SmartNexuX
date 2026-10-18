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

$existingLines = [System.IO.File]::ReadAllLines($environmentPath)
$values = @{}
foreach ($line in $existingLines) {
    if ($line -match "^([^#=]+)=(.*)$") {
        $key = $Matches[1]
        $value = $Matches[2]
        $values[$key] = $value
    }
}

function Get-PreferredLocalHost {
    $fixedHost = "10.54.15.175"
    $preferredHost = $fixedHost

    $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -and
            $_.IPAddress -eq $fixedHost
        } |
        Select-Object -First 1 -ExpandProperty IPAddress

    if (-not [string]::IsNullOrWhiteSpace($ip)) {
        return $ip
    }

    $defaultRoute = Get-NetRoute -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
        Where-Object { $_.NextHop -ne "0.0.0.0" } |
        Sort-Object RouteMetric |
        Select-Object -First 1

    if ($null -ne $defaultRoute) {
        $defaultRouteIp = Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $defaultRoute.InterfaceIndex -ErrorAction SilentlyContinue |
            Where-Object {
                $_.IPAddress -and
                $_.IPAddress -ne "127.0.0.1" -and
                $_.IPAddress -notmatch "^169\.254\."
            } |
            Select-Object -First 1 -ExpandProperty IPAddress

        if (-not [string]::IsNullOrWhiteSpace($defaultRouteIp)) {
            return $defaultRouteIp
        }
    }

    $primaryIp = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -and
            $_.IPAddress -ne "127.0.0.1" -and
            $_.IPAddress -notmatch "^169\.254\."
        } |
        Select-Object -First 1 -ExpandProperty IPAddress

    if (-not [string]::IsNullOrWhiteSpace($primaryIp)) {
        return $primaryIp
    }

    $adapters = @(Get-CimInstance Win32_NetworkAdapterConfiguration -Filter "IPEnabled = 'True'" -ErrorAction SilentlyContinue)
    foreach ($adapter in $adapters) {
        foreach ($address in @($adapter.IPAddress)) {
            if (-not [string]::IsNullOrWhiteSpace($address) -and $address -ne "127.0.0.1" -and $address -notmatch "^169\.254\.") {
                return $address
            }
        }
    }

    return "localhost"
}

$preferredHost = Get-PreferredLocalHost
$expectedAdminEmail = "admin@nexux.local"
$expectedAdminPassword = "ChangeMeNow123!"
$expectedApiBase = "http://${preferredHost}:8000"
$originList = @(
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000"
)
if ($preferredHost -ne "localhost") {
    $originList = @("http://${preferredHost}:3000", "http://${preferredHost}:8000") + $originList
}
$originList = @($originList | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object { $_.Trim() } | Select-Object -Unique)
$expectedOrigins = ($originList -join ",")

$secret = $values["SESSION_SECRET"]
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

$sanitized = @(
    "SESSION_SECRET=$secret",
    "ADMIN_EMAIL=$expectedAdminEmail",
    "ADMIN_PASSWORD=$expectedAdminPassword",
    "NEXT_PUBLIC_API_BASE_URL=$expectedApiBase",
    "FRONTEND_ORIGINS=$expectedOrigins",
    "COOKIE_SECURE=false"
)

$before = [System.IO.File]::ReadAllText($environmentPath)
$finalText = ($sanitized -join [Environment]::NewLine) + [Environment]::NewLine
if ($before -ne $finalText) {
    [System.IO.File]::WriteAllText($environmentPath, $finalText, (New-Object System.Text.UTF8Encoding($false)))
    Write-Output "Local environment prepared"
}
else {
    Write-Output "Using existing local environment settings"
}
