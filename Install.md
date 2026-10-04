# NexuX Windows 安裝與啟動指南

本專案使用 Docker Compose 啟動前端、API、Milvus 及其相依服務。Windows 上不需要另外安裝 Python、Node.js、CUDA Toolkit 或手動建立資料庫；聊天及文件處理使用主機上的 Ollama。

## 系統需求

- Windows 10/11 64 位元，已啟用 CPU 虛擬化；建議至少 16 GB RAM 和 20 GB 可用磁碟空間。
- Docker Desktop（使用 WSL 2 backend）。
- Ollama for Windows。
- 網路連線：Docker 首次建置會下載容器映像，Ollama 模型亦需下載數 GB。
- NVIDIA GPU 不是必要條件；沒有可用 GPU 時 Ollama 可使用 CPU，但回覆較慢。

## 1. 安裝 Windows／虛擬化元件

1. 在工作管理員 →「效能 → CPU」確認「虛擬化」為「已啟用」。如未啟用，需在 BIOS/UEFI 開啟 Intel VT-x 或 AMD SVM/AMD-V。
2. 以系統管理員身分開啟 PowerShell，安裝或更新 WSL 2：

   ```powershell
   wsl --install
   wsl --update
   wsl --set-default-version 2
   ```

   如果 Windows 要求重新啟動，先重新開機再繼續。`wsl --install` 可能同時安裝 Ubuntu；本專案不要求在 Ubuntu 內安裝應用程式。

## 2. 安裝 Docker Desktop

1. 從 [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) 下載並安裝 Docker Desktop。
2. 安裝時選擇 **Use WSL 2 instead of Hyper-V**（若安裝程式提供此選項）。
3. 啟動 Docker Desktop，接受首次啟動提示，並等待 Docker Desktop 顯示 Engine running。
4. 開啟新的 PowerShell 視窗，確認命令可用：

   ```powershell
   docker --version
   docker compose version
   docker info
   ```

Docker Desktop 需要 WSL 2 與硬體虛擬化。一般不需要另外安裝 Docker Engine、Linux、Python、Node.js 或 npm。

## 3. 安裝 Ollama 與模型

1. 從 [Ollama for Windows](https://ollama.com/download/windows) 下載並安裝。
2. 開啟新的 PowerShell 視窗，確認命令可用並下載專案預設模型：

   ```powershell
   ollama --version
   ollama pull qwen2.5vl:3b
   ollama pull nomic-embed-text
   ollama list
   ```

   - `qwen2.5vl:3b`：聊天、Agent 及圖片／文件視覺解析。
   - `nomic-embed-text`：文件向量化與檢索。

保持 Ollama 在背景執行。通常 Windows 版安裝程式會啟動 Ollama；若 API 無法連線，先確認 `http://localhost:11434` 可連線，並從系統匣或 PowerShell 啟動 Ollama。Docker 中的 API 透過 `host.docker.internal:11434` 連接主機。

### 顯示卡驅動（選用）

- NVIDIA GPU：到 [NVIDIA Driver Downloads](https://www.nvidia.com/Download/index.aspx) 安裝適用於顯示卡的最新正式版 Windows 驅動，重新啟動後再執行 `ollama list`。本機 Ollama GPU 推論一般不需要另裝 CUDA Toolkit。
- AMD／Intel GPU：請安裝電腦或 GPU 製造商提供的 Windows 顯示卡驅動。GPU 推論支援依 Ollama 版本、顯示卡及驅動而異；即使 GPU 不支援，本系統仍可改用 CPU 執行。
- 安裝或更新驅動前，請確認硬體型號並使用官方來源。驅動程式安裝通常需要系統管理員權限及重新啟動。

## 4. 取得專案並啟動

將專案原始碼複製到本機，至少保留 `docker-compose.yml`、`.env.example`、`backend`、`frontend`、`Start-NexuX.bat`、`Setup-Environment.ps1`；不要只複製 BAT 檔。打包／複製時排除 `.venv`、`frontend\node_modules`、`frontend\.next`、`__pycache__` 和舊電腦的 `.env`，這些是可重建或含本機 session 金鑰的資料。專案已忽略前端 Docker 建置中的 `node_modules`／`.next`，以便乾淨建置。

Compose 資料 Volume（帳號、對話、文件及向量索引）保存在執行 Docker 的電腦，不會包含在原始碼資料夾或專案 ZIP 中。以下流程會在新電腦建立新的工作區；如需搬移舊帳號與資料，須另外備份及還原 Docker Volume。

啟動 Docker Desktop 後，雙擊專案根目錄的 **`Start-NexuX.bat`**。

BAT 會自動：

1. 檢查 Docker Desktop；若未執行，嘗試啟動它並等待 Docker Engine 就緒。
2. 確認 Ollama 已安裝且服務可連線；若服務尚未執行，嘗試在背景啟動 Ollama。
3. 檢查 `qwen2.5vl:3b` 與 `nomic-embed-text` 模型，缺少時自動下載。
4. 首次建立本機 `.env`，產生隨機 session 金鑰（不會覆寫既有金鑰）。
5. 建置並啟動 Compose 服務，等待 API 與前端皆可連線。
6. 開啟 `http://localhost:3000`。

第一次執行需下載容器映像並建置前後端，時間會較久。瀏覽器首次開啟時，選「註冊」建立本機帳號。API 文件位於 `http://localhost:8000/docs`。

> 一鍵啟動不會自動安裝 Docker Desktop、WSL、Ollama 或顯示卡驅動；請先依照前述步驟完成安裝。缺少 Ollama 模型時，BAT 會自動下載；首次下載聊天模型需較長時間與數 GB 網路流量。

## 日常使用

- 啟動：雙擊 `Start-NexuX.bat`，或在專案資料夾執行 `docker compose up -d`。
- 網頁：`http://localhost:3000`
- API 健康狀態：`http://localhost:8000/health`
- 查看服務：`docker compose ps`
- 查看 API 記錄：`docker compose logs --tail 100 api`
- 停止：在專案資料夾執行 `docker compose down`。

停止服務不要加 `-v`；具名 Volume 保存的帳號、對話、文件索引及 Milvus 資料會保留。也請保留 `.env`：其中的 `SESSION_SECRET` 用來簽署登入 session，遺失或更換會使既有 session 失效。

## 常見問題

### `Docker 未安裝` 或找不到 `docker`

安裝 Docker Desktop，完成後關閉並重新開啟 BAT／終端機。確認 `docker compose version` 有正常輸出。

### Docker Engine 尚未啟動

開啟 Docker Desktop，等待顯示 Engine running 後重新執行 `Start-NexuX.bat`。如 WSL 有問題，可在管理員 PowerShell 執行 `wsl --update`，重新開機後再試。

### 聊天無法連線到 Ollama

確認 Windows 上 Ollama 正在執行，`ollama list` 可列出兩個模型。接著查看 `docker compose logs --tail 100 api`。如果 Ollama 綁定在僅限容器無法存取的位址，請參閱 [plan.md 的 Ollama 連線說明](./plan.md)；不要將 Ollama 服務暴露到不可信任網路。

### 連接埠已被使用

本機的 `3000`（前端）或 `8000`（API）若已被其他程式占用，Compose 服務可能無法啟動。Milvus、MinIO 和其健康檢查使用的連接埠都只在 Docker 內部網路開放，不占用 Windows 主機埠。關閉占用 `3000` 或 `8000` 的程式後再執行 BAT。

### 服務啟動失敗

在專案目錄執行 `docker compose ps` 和 `docker compose logs --tail 100` 查看錯誤；確認網路連線、可用磁碟空間和 Docker Desktop 記憶體資源，再重新啟動。

## 安全提醒

本指南設定用於本機開發。不要把 `.env` 分享或提交，也不要在不可信網路公開 Compose 服務。MinIO 範例帳密及 HTTP Cookie 設定不是正式部署設定；對外部署前須另外設定 HTTPS、安全憑證與存取控制。
