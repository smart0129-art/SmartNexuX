@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo NexuX RAG 資料同步
echo.
echo 匯出與匯入前，請先確認目標 NexuX 已啟動。
echo 匯入公司主機時，請準備該主機的 API URL 與公司端帳號。
echo.
echo 1. 匯出知識庫到 ZIP 檔
echo 2. 匯入 ZIP，新增文件並更新已同步的對應文件
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
echo.
echo 匯出只會備份此帳號可存取的已索引文件。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0RAG-Sync.ps1" -Action Export
if errorlevel 1 (
    echo 知識庫匯出失敗，請依上方錯誤訊息檢查 API、帳號與文件索引。
    pause
    exit /b 1
)
echo.
echo 請使用 USB 等離線方式將 ZIP 檔複製到公司電腦。
pause
exit /b 0

:import
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0RAG-Sync.ps1" -Action Import
if errorlevel 1 (
    echo 知識庫匯入失敗，請依上方錯誤訊息檢查 API、帳號、封存與 embedding 設定。
    pause
    exit /b 1
)
pause
exit /b 0
