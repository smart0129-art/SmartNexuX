@echo off
setlocal
cd /d "%~dp0"

set "QUIT_DOCKER=0"
if /I "%~1"=="--quit-docker" set "QUIT_DOCKER=1"
set "STOP_ERROR=0"

echo NexuX shutdown
echo.

where docker >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not installed or docker.exe is not on PATH.
    set "STOP_ERROR=1"
    goto :stop_ollama
)

docker compose version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker Compose is unavailable.
    set "STOP_ERROR=1"
    goto :stop_ollama
)

docker info >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker Engine is not running. NexuX containers could not be stopped.
    set "STOP_ERROR=1"
    goto :stop_ollama
)

echo Stopping NexuX Docker Compose services...
docker compose down
if errorlevel 1 (
    echo ERROR: Could not stop NexuX Docker Compose services.
    set "STOP_ERROR=1"
) else (
    echo NexuX Docker Compose services stopped. Persistent data was preserved.
)

:stop_ollama
echo.
echo Stopping Ollama if it was started by NexuX...
tasklist /FI "WINDOWTITLE eq NexuX Ollama" /V /FO CSV | findstr /I /C:"NexuX Ollama" >nul
if errorlevel 1 (
    echo No NexuX-launched Ollama window found; other Ollama servers were left running.
) else (
    taskkill /FI "WINDOWTITLE eq NexuX Ollama" /T /F >nul
    if errorlevel 1 (
        echo ERROR: Could not stop the NexuX-launched Ollama server.
        set "STOP_ERROR=1"
    ) else (
        echo NexuX-launched Ollama server stopped.
    )
)

if "%QUIT_DOCKER%"=="1" (
    echo.
    if exist "%ProgramFiles%\Docker\Docker\DockerCli.exe" (
        echo Shutting down Docker Desktop...
        "%ProgramFiles%\Docker\Docker\DockerCli.exe" -Shutdown
        if errorlevel 1 (
            echo ERROR: Could not shut down Docker Desktop.
            set "STOP_ERROR=1"
        )
    ) else (
        echo ERROR: DockerCli.exe was not found; close Docker Desktop from its system tray menu.
        set "STOP_ERROR=1"
    )
)

echo.
if "%STOP_ERROR%"=="1" (
    echo NexuX shutdown finished with errors. Review the messages above.
    exit /b 1
)

echo NexuX shutdown complete.
exit /b 0
