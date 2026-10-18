$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$batPath = (Resolve-Path (Join-Path $scriptDir 'Stop-NexuX.bat')).Path

# Use Start-Process to open a new cmd window and keep it open (/K) so logs/errors stay visible when launched via Windows Explorer or PowerShell.
$quoted = '"' + $batPath + '"'
try {
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/D','/K',$quoted -WorkingDirectory $scriptDir -WindowStyle Normal -Wait
    exit $LASTEXITCODE
} catch {
    # Fallback: run directly (useful if already in a cmd session)
    & cmd.exe /D /K $quoted
    exit $LASTEXITCODE
}
