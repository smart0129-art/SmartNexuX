@echo off
setlocal
cd /d "%~dp0"

echo NexuX startup
echo.

where docker >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker Desktop is not installed or docker.exe is not on PATH.
    echo Install Docker Desktop by following Install.md, then try again.
    pause
    exit /b 1
)

docker compose version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker Compose is unavailable. Update Docker Desktop and try again.
    pause
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
        echo Starting Docker Desktop...
        start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
    ) else (
        echo Docker Desktop is not running. Start it, wait until the Engine is ready, then retry.
        pause
        exit /b 1
    )

    set "DOCKER_READY="
    for /L %%i in (1,1,60) do (
        docker info >nul 2>&1
        if not errorlevel 1 set "DOCKER_READY=1"
        if defined DOCKER_READY goto :docker_ready
        timeout /t 5 /nobreak >nul
    )
    echo ERROR: Docker Engine did not start within five minutes.
    pause
    exit /b 1
)

:docker_ready
where ollama >nul 2>&1
if errorlevel 1 (
    echo ERROR: Ollama is not installed or ollama.exe is not on PATH.
    echo Install Ollama by following Install.md, then try again.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { $null=Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://localhost:11434/api/tags'; exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo Starting the Ollama server...
    start "NexuX Ollama" /min cmd.exe /c ollama serve
    set "OLLAMA_READY="
    for /L %%i in (1,1,30) do (
        powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { $null=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://localhost:11434/api/tags'; exit 0 } catch { exit 1 }" >nul 2>&1
        if not errorlevel 1 set "OLLAMA_READY=1"
        if defined OLLAMA_READY goto :ollama_ready
        timeout /t 2 /nobreak >nul
    )
    echo ERROR: Ollama did not start. Check the Ollama installation and try again.
    pause
    exit /b 1
)

:ollama_ready
echo Checking required Ollama models...
ollama list | findstr /c:"qwen2.5vl:3b" >nul
if errorlevel 1 (
    echo Downloading qwen2.5vl:3b. This model is several GB and may take a while...
    ollama pull qwen2.5vl:3b
    if errorlevel 1 (
        echo ERROR: Could not download qwen2.5vl:3b. Check your network and Ollama, then retry.
        pause
        exit /b 1
    )
)

ollama list | findstr /c:"nomic-embed-text" >nul
if errorlevel 1 (
    echo Downloading nomic-embed-text...
    ollama pull nomic-embed-text
    if errorlevel 1 (
        echo ERROR: Could not download nomic-embed-text. Check your network and Ollama, then retry.
        pause
        exit /b 1
    )
)

if not exist ".env" (
    if not exist ".env.example" (
        echo ERROR: .env.example is missing. Run this script from the NexuX project folder.
        pause
        exit /b 1
    )
    copy /y ".env.example" ".env" >nul
    if errorlevel 1 (
        echo ERROR: Could not create .env.
        pause
        exit /b 1
    )
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup-Environment.ps1"
if errorlevel 1 (
    echo ERROR: Could not prepare the local environment file.
    pause
    exit /b 1
)

docker compose config --quiet
if errorlevel 1 (
    echo ERROR: Docker Compose configuration is invalid.
    pause
    exit /b 1
)

echo Building and starting NexuX services. The first run may take several minutes...
docker compose up --build -d
if errorlevel 1 (
    echo ERROR: NexuX services failed to start. Check: docker compose logs --tail 100
    pause
    exit /b 1
)

echo Waiting for the API health check...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddMinutes(5); do { try { $response=Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://localhost:8000/health'; if ($response.StatusCode -eq 200) { exit 0 } } catch { }; Start-Sleep -Seconds 5 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
    echo ERROR: API did not become healthy. Check: docker compose ps
    echo Logs: docker compose logs --tail 100 api milvus
    pause
    exit /b 1
)

echo Waiting for the frontend...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddMinutes(2); do { try { $response=Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://localhost:3000'; if ($response.StatusCode -eq 200) { exit 0 } } catch { }; Start-Sleep -Seconds 3 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
    echo ERROR: Frontend did not become ready. Check: docker compose ps
    echo Logs: docker compose logs --tail 100 frontend
    pause
    exit /b 1
)

echo NexuX is ready at http://localhost:3000
start "" "http://localhost:3000"
exit /b 0
