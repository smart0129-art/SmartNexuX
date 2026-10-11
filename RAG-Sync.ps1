param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Export", "Import")]
    [string]$Action
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http

$baseUrl = Read-Host "NexuX API URL [http://localhost:8000]"
if ([string]::IsNullOrWhiteSpace($baseUrl)) {
    $baseUrl = "http://localhost:8000"
}
$baseUrl = $baseUrl.TrimEnd("/")

$email = Read-Host "NexuX account email"
$securePassword = Read-Host "NexuX account password" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
$password = $null
$client = $null
$inputStream = $null
$outputStream = $null
$multipart = $null
$fileContent = $null

try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.CookieContainer = New-Object System.Net.CookieContainer
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromHours(2)

    $loginJson = @{
        email = $email
        password = $password
    } | ConvertTo-Json -Compress
    $loginContent = New-Object System.Net.Http.StringContent(
        $loginJson,
        [Text.Encoding]::UTF8,
        "application/json"
    )
    $loginResponse = $client.PostAsync(
        "$baseUrl/api/auth/login",
        $loginContent
    ).GetAwaiter().GetResult()
    if (-not $loginResponse.IsSuccessStatusCode) {
        $detail = $loginResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        throw "Sign-in failed ($([int]$loginResponse.StatusCode)): $detail"
    }

    if ($Action -eq "Export") {
        $directory = Join-Path $PSScriptRoot "RAG-Exports"
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        $destination = Join-Path $directory (
            "NexuX-RAG-{0}.zip" -f (Get-Date -Format "yyyyMMdd-HHmmssfff")
        )
        $response = $client.GetAsync(
            "$baseUrl/api/documents/export",
            [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead
        ).GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            $detail = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            throw "Export failed ($([int]$response.StatusCode)): $detail"
        }
        $inputStream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $outputStream = [IO.File]::Create($destination)
        $inputStream.CopyTo($outputStream)
        $outputStream.Dispose()
        $outputStream = $null
        Write-Host "RAG archive created: $destination"
    }
    else {
        $sourcePath = Read-Host "Path to the RAG ZIP file"
        $sourcePath = [Environment]::ExpandEnvironmentVariables(
            $sourcePath.Trim('"')
        )
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw "Archive file not found: $sourcePath"
        }

        $multipart = New-Object System.Net.Http.MultipartFormDataContent
        $inputStream = [IO.File]::OpenRead($sourcePath)
        $fileContent = New-Object System.Net.Http.StreamContent($inputStream)
        $fileContent.Headers.ContentType = [Net.Http.Headers.MediaTypeHeaderValue]::Parse(
            "application/zip"
        )
        $multipart.Add(
            $fileContent,
            "file",
            [IO.Path]::GetFileName($sourcePath)
        )
        $response = $client.PostAsync(
            "$baseUrl/api/documents/import",
            $multipart
        ).GetAwaiter().GetResult()
        $responseBody = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            throw "Import failed ($([int]$response.StatusCode)): $responseBody"
        }
        $result = $responseBody | ConvertFrom-Json
        Write-Host (
            "Import complete. Added: {0}; already present: {1}." -f
            $result.imported,
            $result.skipped
        )
    }
}
catch {
    Write-Error $_
    exit 1
}
finally {
    if ($outputStream) { $outputStream.Dispose() }
    if ($inputStream) { $inputStream.Dispose() }
    if ($fileContent) { $fileContent.Dispose() }
    if ($multipart) { $multipart.Dispose() }
    if ($client) { $client.Dispose() }
    if ($passwordPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }
    $password = $null
}
