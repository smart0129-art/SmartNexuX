param(
    [switch]$Offline,
    [switch]$Online
)

$ErrorActionPreference = 'Stop'
if ($Offline -and $Online) {
    Write-Error "Choose either -Offline or -Online, not both."
    exit 1
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$batPath = (Resolve-Path (Join-Path $scriptDir 'Start-NexuX.bat')).Path
$argumentList = @('/D', '/K', ('"' + $batPath + '"'))
$modeArgument = ""
if ($Offline) {
    $argumentList += '--offline'
    $modeArgument = '--offline'
}
elseif ($Online) {
    $argumentList += '--online'
    $modeArgument = '--online'
}

# Use Start-Process to open a new cmd window and keep it open (/K) so logs/errors stay visible when launched via Windows Explorer or PowerShell.
try {
    $process = Start-Process -FilePath 'cmd.exe' -ArgumentList $argumentList -WorkingDirectory $scriptDir -WindowStyle Normal -Wait -PassThru
    exit $process.ExitCode
} catch {
    # Fallback: run directly (useful if already in a cmd session)
    $quoted = '"' + $batPath + '"'
    if ($modeArgument) {
        & cmd.exe /D /K $quoted $modeArgument
    }
    else {
        & cmd.exe /D /K $quoted
    }
    exit $LASTEXITCODE
}
