@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo NexuX RAG 資料同步
echo.
echo 1. 匯出知識庫到 ZIP 檔
echo 2. 匯入並合併 ZIP 檔內的知識庫
echo 0. 離開
echo.
set /p "ACTION=請選擇功能："

if "%ACTION%"=="1" goto export
if "%ACTION%"=="2" goto import
if "%ACTION%"=="0" exit /b 0
echo 選項無效。
pause
exit /b 1

:export
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0RAG-Sync.ps1" -Action Export
if errorlevel 1 (
    echo 知識庫匯出失敗。
    pause
    exit /b 1
)
echo.
echo 請使用 USB 等離線方式將 ZIP 檔複製到另一台電腦。
pause
exit /b 0

:import
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0RAG-Sync.ps1" -Action Import
if errorlevel 1 (
    echo 知識庫匯入失敗。
    pause
    exit /b 1
)
pause
exit /b 0
