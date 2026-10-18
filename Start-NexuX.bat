@echo off
setlocal
cd /d "%~dp0"

echo NexuX startup

where docker >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker Desktop is not installed or docker.exe is not on PATH.
    pause
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo Starting Docker Desktop...
    start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
    echo Please wait until Docker Desktop is ready, then press any key.
    pause
)

where ollama >nul 2>&1
if errorlevel 1 (
    echo ERROR: Ollama is not installed or ollama.exe is not on PATH.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://localhost:11434/api/tags' | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo Starting Ollama...
    start "" cmd /c "ollama serve"
)

if not exist ".env" copy ".env.example" ".env"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup-Environment.ps1"
if errorlevel 1 (
    echo ERROR: Could not prepare the local environment.
    pause
    exit /b 1
)

set "NEXT_PUBLIC_API_BASE_URL="
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /c:"NEXT_PUBLIC_API_BASE_URL=" "%~dp0.env"`) do set "NEXT_PUBLIC_API_BASE_URL=%%B"
if not defined NEXT_PUBLIC_API_BASE_URL (
    echo ERROR: NEXT_PUBLIC_API_BASE_URL is missing from .env.
    pause
    exit /b 1
)
set "NEXUX_FRONTEND_URL=%NEXT_PUBLIC_API_BASE_URL:8000=3000%"

docker compose up --build -d --remove-orphans
if errorlevel 1 (
    echo ERROR: Docker services failed to start.
    pause
    exit /b 1
)

echo Waiting for the API and frontend to become ready...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$urls = @('http://127.0.0.1:8000/health', 'http://127.0.0.1:3000'); $deadline = (Get-Date).AddMinutes(5); foreach ($url in $urls) { do { try { $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 $url; if ($response.StatusCode -eq 200) { Write-Host ('Ready: ' + $url); break } } catch { }; if ((Get-Date) -ge $deadline) { Write-Error ('Timed out waiting for ' + $url); exit 1 }; Start-Sleep -Seconds 3 } while ($true) }"
if errorlevel 1 (
    echo ERROR: NexuX did not become ready. Recent service logs:
    docker compose logs --tail 50 api frontend
    pause
    exit /b 1
)

echo Opening %NEXUX_FRONTEND_URL%
start "" "%NEXUX_FRONTEND_URL%"
