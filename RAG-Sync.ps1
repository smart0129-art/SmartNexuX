param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Export", "Import")]
    [string]$Action
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http
Add-Type -AssemblyName System.IO.Compression.FileSystem

$baseUrl = Read-Host "NexuX API URL [http://localhost:8000]"
if ([string]::IsNullOrWhiteSpace($baseUrl)) {
    $baseUrl = "http://localhost:8000"
}
$baseUrl = $baseUrl.Trim().TrimEnd("/")
$apiUri = $null
if (-not [Uri]::TryCreate($baseUrl, [UriKind]::Absolute, [ref]$apiUri) -or
    $apiUri.Scheme -notin @("http", "https")) {
    throw "API URL must be an absolute HTTP or HTTPS URL."
}

$email = Read-Host "NexuX account email"
$securePassword = Read-Host "NexuX account password" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
$password = $null
$client = $null
$inputStream = $null
$outputStream = $null
$response = $null
$healthResponse = $null
$documentsResponse = $null
$loginResponse = $null
$loginContent = $null
$multipart = $null
$fileContent = $null
$updateContent = $null

function Get-RagArchiveSummary {
    param([Parameter(Mandatory = $true)][string]$Path)

    $archive = [IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $manifestEntry = $archive.GetEntry("manifest.json")
        if ($null -eq $manifestEntry -or $manifestEntry.Length -gt 10MB) {
            throw "Archive is missing a valid manifest.json."
        }
        $manifestStream = $manifestEntry.Open()
        $reader = New-Object IO.StreamReader($manifestStream, [Text.Encoding]::UTF8)
        try {
            $manifest = $reader.ReadToEnd() | ConvertFrom-Json
        }
        finally {
            $reader.Dispose()
        }
        if ($manifest.format_version -ne 1 -or $null -eq $manifest.documents) {
            throw "Unsupported or invalid RAG archive format."
        }

        $documents = @($manifest.documents)
        $sourceIds = New-Object "System.Collections.Generic.HashSet[string]"
        $chunkCount = 0
        foreach ($document in $documents) {
            $sourceId = [string]$document.source_document_id
            $chunksPath = "chunks/$sourceId.jsonl"
            $chunksEntry = $archive.GetEntry($chunksPath)
            if ([string]::IsNullOrWhiteSpace($sourceId) -or
                -not $sourceIds.Add($sourceId) -or
                $document.chunks_path -ne $chunksPath -or
                $document.chunks_indexed -le 0 -or
                $null -eq $chunksEntry) {
                throw "Archive contains invalid or missing chunks for document '$sourceId'."
            }
            $chunkStream = $chunksEntry.Open()
            $chunkReader = New-Object IO.StreamReader($chunkStream, [Text.Encoding]::UTF8)
            $documentChunkCount = 0
            try {
                while ($null -ne ($line = $chunkReader.ReadLine())) {
                    if ([string]::IsNullOrWhiteSpace($line)) {
                        throw "Archive contains an empty chunk for document '$sourceId'."
                    }
                    try {
                        $null = $line | ConvertFrom-Json -ErrorAction Stop
                    }
                    catch {
                        throw "Archive contains invalid JSON chunks for document '$sourceId'."
                    }
                    $documentChunkCount++
                }
            }
            finally {
                $chunkReader.Dispose()
            }
            if ($documentChunkCount -ne [int]$document.chunks_indexed) {
                throw "Archive chunk count does not match the manifest for document '$sourceId'."
            }
            foreach ($imageId in @($document.image_ids)) {
                $imagePath = "images/$sourceId/$imageId.jpg"
                if ($null -eq $archive.GetEntry($imagePath)) {
                    throw "Archive is missing image '$imagePath'."
                }
            }
            $chunkCount += $documentChunkCount
        }

        return [PSCustomObject]@{
            DocumentCount = $documents.Count
            ChunkCount    = $chunkCount
            Length        = (Get-Item -LiteralPath $Path).Length
        }
    }
    finally {
        $archive.Dispose()
    }
}

try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.CookieContainer = New-Object System.Net.CookieContainer
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromHours(2)

    try {
        $healthResponse = $client.GetAsync(
            "$baseUrl/health"
        ).GetAwaiter().GetResult()
        if (-not $healthResponse.IsSuccessStatusCode) {
            throw "API health check failed ($([int]$healthResponse.StatusCode))."
        }
        $healthResponse.Dispose()
        $healthResponse = $null
    }
    catch {
        throw "Cannot reach NexuX API at '$baseUrl'. Start NexuX or check the API URL. $($_.Exception.Message)"
    }

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
    $loginResponse.Dispose()
    $loginContent.Dispose()
    $loginResponse = $null
    $loginContent = $null

    if ($Action -eq "Export") {
        $documentsResponse = $client.GetAsync(
            "$baseUrl/api/documents"
        ).GetAwaiter().GetResult()
        if (-not $documentsResponse.IsSuccessStatusCode) {
            $detail = $documentsResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            throw "Could not list the signed-in account's documents ($([int]$documentsResponse.StatusCode)): $detail"
        }
        $documentList = $documentsResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult() |
            ConvertFrom-Json
        $expectedDocumentCount = @($documentList).Count
        $documentsResponse.Dispose()
        $documentsResponse = $null
        if ($expectedDocumentCount -eq 0) {
            throw "No accessible documents were found. Sign in with the account that owns or can access the RAG data."
        }

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
        $inputStream.Dispose()
        $inputStream = $null
        $response.Dispose()
        $response = $null

        $summary = Get-RagArchiveSummary -Path $destination
        if ($summary.DocumentCount -ne $expectedDocumentCount) {
            throw "Export verification failed: API listed $expectedDocumentCount documents, but the archive contains $($summary.DocumentCount)."
        }
        Write-Host (
            "Verified RAG archive: {0} document(s), {1} chunk(s), {2:N2} MB." -f
            $summary.DocumentCount,
            $summary.ChunkCount,
            ($summary.Length / 1MB)
        )
        Write-Host "RAG archive created: $destination"
    }
    else {
        $sourcePath = Read-Host "Path to the RAG ZIP file"
        $sourcePath = [Environment]::ExpandEnvironmentVariables(
            $sourcePath.Trim().Trim('"')
        )
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw "Archive file not found: $sourcePath"
        }
        $summary = Get-RagArchiveSummary -Path $sourcePath
        Write-Host (
            "Archive verified: {0} document(s), {1} chunk(s), {2:N2} MB." -f
            $summary.DocumentCount,
            $summary.ChunkCount,
            ($summary.Length / 1MB)
        )
        $updateAnswer = Read-Host "Update matching imported documents by source ID or unique file name? [Y/n]"
        if ([string]::IsNullOrWhiteSpace($updateAnswer) -or $updateAnswer -match "^y(es)?$") {
            $updateExisting = $true
        }
        elseif ($updateAnswer -match "^n(o)?$") {
            $updateExisting = $false
        }
        else {
            throw "Please answer Y or N."
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
        $updateContent = New-Object System.Net.Http.StringContent(
            $updateExisting.ToString().ToLowerInvariant(),
            [Text.Encoding]::UTF8
        )
        $multipart.Add($updateContent, "update_existing")
        $response = $client.PostAsync(
            "$baseUrl/api/documents/import",
            $multipart
        ).GetAwaiter().GetResult()
        $responseBody = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            throw "Import failed ($([int]$response.StatusCode)): $responseBody"
        }
        $result = $responseBody | ConvertFrom-Json
        foreach ($countName in @("imported", "updated", "skipped")) {
            $count = $result.$countName
            if (($count -isnot [int] -and $count -isnot [long]) -or $count -lt 0) {
                throw "Import returned an invalid '$countName' count: $responseBody"
            }
        }
        $response.Dispose()
        $response = $null
        Write-Host (
            "Import complete. Added: {0}; updated: {1}; skipped: {2}." -f
            $result.imported,
            $result.updated,
            $result.skipped
        )
    }
}
catch {
    if ($outputStream) {
        $outputStream.Dispose()
        $outputStream = $null
    }
    if ($inputStream) {
        $inputStream.Dispose()
        $inputStream = $null
    }
    if ($response) {
        $response.Dispose()
        $response = $null
    }
    if ($healthResponse) { $healthResponse.Dispose() }
    if ($documentsResponse) { $documentsResponse.Dispose() }
    if ($Action -eq "Export" -and $destination -and (Test-Path -LiteralPath $destination)) {
        Remove-Item -LiteralPath $destination -Force
    }
    Write-Error $_
    exit 1
}
finally {
    if ($outputStream) { $outputStream.Dispose() }
    if ($inputStream) { $inputStream.Dispose() }
    if ($response) { $response.Dispose() }
    if ($healthResponse) { $healthResponse.Dispose() }
    if ($documentsResponse) { $documentsResponse.Dispose() }
    if ($loginResponse) { $loginResponse.Dispose() }
    if ($loginContent) { $loginContent.Dispose() }
    if ($fileContent) { $fileContent.Dispose() }
    if ($updateContent) { $updateContent.Dispose() }
    if ($multipart) { $multipart.Dispose() }
    if ($client) { $client.Dispose() }
    if ($securePassword) { $securePassword.Dispose() }
    if ($passwordPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }
    $password = $null
}
