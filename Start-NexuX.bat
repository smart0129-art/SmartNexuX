@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "NEXUX_MODE="
if /I "%~1"=="--offline" set "NEXUX_MODE=offline"
if /I "%~1"=="--online" set "NEXUX_MODE=online"
if not "%~1"=="" if not defined NEXUX_MODE (
    echo ERROR: Unknown option "%~1". Use --offline or --online.
    pause
    exit /b 1
)

if defined NEXUX_MODE goto :mode_selected
echo NexuX startup
echo.
echo 1. Company offline mode - use local Docker images and Ollama; never download
echo 2. Online setup mode - build images and download missing Ollama models
echo.
set /p "NEXUX_CHOICE=Select mode [1]: "
if not defined NEXUX_CHOICE set "NEXUX_CHOICE=1"
if "%NEXUX_CHOICE%"=="1" set "NEXUX_MODE=offline"
if "%NEXUX_CHOICE%"=="2" set "NEXUX_MODE=online"
if not defined NEXUX_MODE (
    echo ERROR: Invalid selection. Choose 1 or 2.
    pause
    exit /b 1
)

:mode_selected

echo NexuX startup - %NEXUX_MODE% mode
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
    set "DOCKER_DESKTOP=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
    if not exist "%DOCKER_DESKTOP%" (
        echo Docker Engine is not running. Start Docker Desktop and retry.
        pause
        exit /b 1
    )
    echo Starting Docker Desktop...
    start "" "%DOCKER_DESKTOP%"
    for /L %%i in (1,1,60) do (
        docker info >nul 2>&1
        if not errorlevel 1 goto :docker_ready
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

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { $null=Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://localhost:11434/api/tags'; exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo Starting Ollama...
    start "NexuX Ollama" /min cmd.exe /c ollama serve
    set "OLLAMA_READY="
    for /L %%i in (1,1,30) do (
        powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { $null=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://localhost:11434/api/tags'; exit 0 } catch { exit 1 }" >nul 2>&1
        if not errorlevel 1 set "OLLAMA_READY=1"
        if defined OLLAMA_READY goto :ollama_ready
        timeout /t 2 /nobreak >nul
    )
    echo ERROR: Ollama did not start. Check the Ollama installation and retry.
    pause
    exit /b 1
)

:ollama_ready
ollama list >nul 2>&1
if errorlevel 1 (
    echo ERROR: Could not list Ollama models. Check the Ollama service and retry.
    pause
    exit /b 1
)

echo Checking required Ollama models...
ollama list | findstr /B /C:"qwen2.5vl:3b" >nul
if errorlevel 1 (
    if /I "%NEXUX_MODE%"=="offline" (
        echo ERROR: Required model qwen2.5vl:3b is missing. Offline mode will not download it.
        echo Load the model into Ollama on a connected computer and transfer its model data first.
        pause
        exit /b 1
    )
    echo Downloading qwen2.5vl:3b. This model is several GB and may take a while...
    ollama pull qwen2.5vl:3b
    if errorlevel 1 (
        echo ERROR: Could not download qwen2.5vl:3b. Check your network and Ollama, then retry.
        pause
        exit /b 1
    )
)

ollama list | findstr /B /C:"nomic-embed-text" >nul
if errorlevel 1 (
    if /I "%NEXUX_MODE%"=="offline" (
        echo ERROR: Required model nomic-embed-text is missing. Offline mode will not download it.
        echo Load the model into Ollama on a connected computer and transfer its model data first.
        pause
        exit /b 1
    )
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
        echo ERROR: .env.example is missing. Run this script inside the NexuX project folder.
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

if /I "%NEXUX_MODE%"=="offline" (
    set "CHAT_DEFAULT_PROVIDER=ollama"
    call :mark_missing_image nexux-api:latest
    call :mark_missing_image nexux-frontend:latest
    call :mark_missing_image quay.io/coreos/etcd:v3.5.18
    call :mark_missing_image minio/minio:RELEASE.2024-12-18T13-15-44Z
    call :mark_missing_image milvusdb/milvus:v2.5.10
    if defined NEED_OFFLINE_IMAGES if exist "NexuX-offline-images.tar" (
        echo Loading NexuX-offline-images.tar...
        docker load -i "NexuX-offline-images.tar"
        if errorlevel 1 (
            echo ERROR: Could not load NexuX-offline-images.tar.
            pause
            exit /b 1
        )
    )

    call :check_image nexux-api:latest
    if errorlevel 1 goto :missing_offline_image
    call :check_image nexux-frontend:latest
    if errorlevel 1 goto :missing_offline_image
    call :check_image quay.io/coreos/etcd:v3.5.18
    if errorlevel 1 goto :missing_offline_image
    call :check_image minio/minio:RELEASE.2024-12-18T13-15-44Z
    if errorlevel 1 goto :missing_offline_image
    call :check_image milvusdb/milvus:v2.5.10
    if errorlevel 1 goto :missing_offline_image
)

docker compose config --quiet
if errorlevel 1 (
    echo ERROR: Docker Compose configuration is invalid.
    pause
    exit /b 1
)

if /I "%NEXUX_MODE%"=="offline" (
    echo Starting NexuX from local images without building or pulling...
    docker compose up -d --no-build --pull never --remove-orphans
) else (
    echo Building and starting NexuX. The first run requires network access...
    docker compose up --build -d --remove-orphans
)
if errorlevel 1 (
    echo ERROR: NexuX Docker services failed to start. Check: docker compose logs --tail 100
    pause
    exit /b 1
)

set "NEXT_PUBLIC_API_BASE_URL="
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /c:"NEXT_PUBLIC_API_BASE_URL=" "%~dp0.env"`) do set "NEXT_PUBLIC_API_BASE_URL=%%B"
if not defined NEXT_PUBLIC_API_BASE_URL set "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000"
set "NEXUX_FRONTEND_URL=%NEXT_PUBLIC_API_BASE_URL:8000=3000%"
if "%NEXUX_FRONTEND_URL%"=="%NEXT_PUBLIC_API_BASE_URL%" set "NEXUX_FRONTEND_URL=http://localhost:3000"

echo Waiting for the API and frontend to become ready...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$urls = @('http://127.0.0.1:8000/health', 'http://127.0.0.1:3000'); foreach ($url in $urls) { $deadline = (Get-Date).AddMinutes(5); do { try { $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 $url; if ($response.StatusCode -eq 200) { Write-Host ('Ready: ' + $url); break } } catch { }; if ((Get-Date) -ge $deadline) { Write-Error ('Timed out waiting for ' + $url); exit 1 }; Start-Sleep -Seconds 3 } while ($true) }"
if errorlevel 1 (
    echo ERROR: NexuX did not become ready. Recent service logs:
    docker compose logs --tail 50 api frontend
    pause
    exit /b 1
)

echo NexuX is ready at %NEXUX_FRONTEND_URL%
start "" "%NEXUX_FRONTEND_URL%"
exit /b 0

:check_image
docker image inspect "%~1" >nul 2>&1
if errorlevel 1 (
    echo Missing offline image: %~1
    exit /b 1
)
exit /b 0

:mark_missing_image
docker image inspect "%~1" >nul 2>&1
if errorlevel 1 set "NEED_OFFLINE_IMAGES=1"
exit /b 0

:missing_offline_image
echo ERROR: Offline Docker images are missing.
echo Place NexuX-offline-images.tar in the project folder, then run this script again.
echo See Install.md for the image bundle contents and transfer instructions.
pause
exit /b 1
