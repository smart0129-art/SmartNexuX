# NexuX Windows 安裝與啟動指南

本專案使用 Docker Compose 啟動前端、API、Milvus 及其相依服務。Windows 上不需要另外安裝 Python、Node.js、CUDA Toolkit 或手動建立資料庫；聊天及文件處理使用主機上的 Ollama。

## 系統需求

- Windows 10/11 64 位元，已啟用 CPU 虛擬化；建議至少 16 GB RAM 和 20 GB 可用磁碟空間。
- Docker Desktop（使用 WSL 2 backend）。
- Ollama for Windows。
- 線上建置模式需要網路下載 Docker 映像及 Ollama 模型；公司離線模式需事先準備好 images 與 Ollama 模型。
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

將專案原始碼複製到本機，至少保留 `docker-compose.yml`、`.env.example`、`backend`、`frontend`、`Start-NexuX.bat`、`Stop-NexuX.bat`、`Setup-Environment.ps1`、`RAG-Sync.bat`、`RAG-Sync.ps1`；不要只複製 BAT 檔。打包／複製時排除 `.venv`、`frontend\node_modules`、`frontend\.next`、`__pycache__` 和舊電腦的 `.env`，這些是可重建或含本機 session 金鑰的資料。專案已忽略前端 Docker 建置中的 `node_modules`／`.next`，以便乾淨建置。

Compose 資料 Volume（帳號、對話、文件及向量索引）保存在執行 Docker 的電腦，不會包含在原始碼資料夾或專案 ZIP 中。以下流程會在新電腦建立新的工作區；如需搬移舊帳號與資料，須另外備份及還原 Docker Volume。

啟動 Docker Desktop 後，雙擊專案根目錄的 **`Start-NexuX.bat`**，選擇使用模式；預設選項為公司離線模式。也可直接執行：

```powershell
.\Start-NexuX.bat --offline
.\Start-NexuX.bat --online
```

- **公司離線模式**：只使用本機 Docker images 和 Ollama 模型，不建置、不拉取 Docker images，也不下載 Ollama 模型；聊天自動使用本機 Ollama。
- **線上建置模式**：建置 Docker images，並在 Ollama 缺少必要模型時下載。聊天 provider 依 `.env` 的 `CHAT_DEFAULT_PROVIDER` 設定；預設為 Ollama。

兩種模式的啟動檔都會自動：

1. 檢查 Docker Desktop；若未執行，嘗試啟動它並等待 Docker Engine 就緒。
2. 確認 Ollama 已安裝且服務可連線；若服務尚未執行，嘗試在背景啟動 Ollama。
3. 檢查 `qwen2.5vl:3b` 與 `nomic-embed-text` 模型；只在線上建置模式下載缺少的模型。
4. 首次建立本機 `.env` 並產生隨機 session 金鑰；後續啟動保留既有設定與自訂值。
5. 依選擇建置或直接使用本機 images 啟動 Compose 服務，等待 API 與前端皆可連線。
6. 開啟 Dashboard；預設網址為 `http://localhost:3000`。

首次線上建置需下載容器映像及前後端相依套件，時間會較久。首次離線部署前，請依下方「準備離線電腦」先匯入 Docker images 和 Ollama 模型。瀏覽器首次開啟時，選「註冊」建立本機帳號。API 文件位於 `http://localhost:8000/docs`。

### 準備離線電腦

在可連網的電腦上，先建置應用程式映像並下載 Compose 使用的服務映像，再將五個 images 打包：

```powershell
docker compose build api frontend
docker compose pull etcd milvus
docker image inspect minio/minio:RELEASE.2024-12-18T13-15-44Z
docker save -o NexuX-offline-images.tar `
  nexux-api:latest `
  nexux-frontend:latest `
  quay.io/coreos/etcd:v3.5.18 `
  minio/minio:RELEASE.2024-12-18T13-15-44Z `
  milvusdb/milvus:v2.5.10
```

確認 `docker image inspect` 成功後再執行 `docker save`。若 MinIO image 不在本機且 registry 無法提供該 tag，請先從可信任來源取得並載入完全相同的 image；不要改用其他 tag。

以 USB 等離線方式將 `NexuX-offline-images.tar` 與專案檔案複製到公司電腦，並在專案目錄載入 images：

```powershell
docker load -i .\NexuX-offline-images.tar
```

在該電腦安裝 Ollama，並確保 Ollama 的模型資料包含 `qwen2.5vl:3b` 與 `nomic-embed-text`。可在已下載模型的電腦安裝相同版本 Ollama，使用該機 Ollama 模型資料目錄進行離線搬移；切勿只複製其中部分 blob。模型就緒後執行 `.\Start-NexuX.bat --offline`。若 images bundle 放在專案根目錄，啟動檔會在需要時自動載入；缺少 image 或模型時會停止並指出缺少項目，不會嘗試連網。

離線啟動只需 Docker Desktop、Ollama、專案檔案、所需 images 和模型；Windows 主機不需安裝 Node.js、npm 或 Python。帳號、對話及知識庫資料存在 Docker volumes，不會包含在 images bundle 中。

登入後，在 Dashboard 右側「知識庫」分頁點選「新增至知識庫」即可上傳文件。上傳預設為私人；勾選「分享給這台 NexuX 的所有帳號」後，其他登入帳號也可搜尋及使用該文件。MarkItDown 解析、Qwen 視覺辨識、語意切片與 Ollama Embedding／Milvus 向量索引都由 API 自動處理；詳細格式與操作說明請見 [README 的文件索引流程](./README.md#上傳文件並建立向量索引)。

> 一鍵啟動不會自動安裝 Docker Desktop、WSL、Ollama 或顯示卡驅動；請先依照前述步驟完成安裝。只有線上建置模式會下載缺少的 Ollama 模型。

## 日常使用

- 啟動並選擇模式：雙擊 `Start-NexuX.bat`；直接指定離線模式：`.\Start-NexuX.bat --offline`；線上建置：`.\Start-NexuX.bat --online`。
- 網頁：`http://localhost:3000`
- API 健康狀態：`http://localhost:8000/health`
- 查看服務：`docker compose ps`
- 查看 API 記錄：`docker compose logs --tail 100 api`
- 停止：雙擊 `Stop-NexuX.bat`，或在專案資料夾執行 `docker compose down`。
- 同時退出 Docker Desktop：執行 `Stop-NexuX.bat --quit-docker`。

`Stop-NexuX.bat` 會一併關閉由啟動檔啟動的 Ollama；如果 Ollama 原本已在背景執行，會保留它。停止服務不要加 `-v`；具名 Volume 保存的帳號、對話、文件索引及 Milvus 資料會保留。也請保留 `.env`：其中的 `SESSION_SECRET` 用來簽署登入 session，遺失或更換會使既有 session 失效。

## 兩台離線電腦間同步 RAG

兩台電腦需各自完成安裝、啟動 NexuX，並使用相同的 embedding 模型與向量維度。來源與目的電腦不需要彼此連網：

1. 在來源電腦執行 `Start-NexuX.bat` 更新並啟動 NexuX，確認文件已完成索引後，在 Dashboard 右側「工作區資訊 → 知識庫」點選「備份 RAG」。
2. 將瀏覽器下載的 ZIP 用 USB 搬到目的電腦。
3. 在公司目的電腦執行 `Start-NexuX.bat` 更新並啟動 NexuX，在 Dashboard 相同位置點選「匯入 ZIP」並選取備份。頁面會使用目前登入的公司端帳號；來源和目的電腦不必互通。命令列 `RAG-Sync.bat` 仍可供自動化或疑難排解時使用。

匯入時預設會新增文件、更新先前同步的對應文件，並略過目的端既有但非此同步來源的文件；先依來源文件 ID 配對，若來源重新上傳造成 ID 改變，只有封存和目的端各自都只有一份同名的已同步文件時，才會忽略大小寫以檔名配對更新。僅以檔名配對時，同名多份會新增、不猜測替換；來源 ID 完全相同仍可精確更新。程式會詢問是否更新，回答 `N` 可改為只新增並略過重複文件。匯入不會取代其他文件。封存包含已索引的文字、向量、文件資訊及檢索圖片，不包含原始上傳檔、帳號或對話。由於原始上傳檔不會永久保存，搬移後仍可搜尋及使用索引內容，但不能從封存還原原始文件檔。匯出的共用／私人狀態會保留；請將 ZIP 視為敏感資料妥善保管。

更新 NexuX 程式後，請在來源及目的環境各自先執行 `Start-NexuX.bat` 完成服務更新，再使用 Dashboard 備份／匯入或 `RAG-Sync.bat`。封存會驗證 ZIP、文件數及索引片段數；匯入前會檢查封存結構。來源與目的端必須使用相同的 embedding 模型及向量維度，否則目的端 API 會拒絕不相容的向量。

## 常見問題

### `Docker 未安裝` 或找不到 `docker`

安裝 Docker Desktop，完成後關閉並重新開啟 BAT／終端機。確認 `docker compose version` 有正常輸出。

### Docker Engine 尚未啟動

開啟 Docker Desktop，等待顯示 Engine running 後重新執行 `Start-NexuX.bat`。如 WSL 有問題，可在管理員 PowerShell 執行 `wsl --update`，重新開機後再試。

### minio安裝至另一台電腦
先下載並打包映像檔：
docker pull minio/minio:RELEASE.2024-12-18T13-15-44Z
docker save -o .\minio-RELEASE.2024-12-18T13-15-44Z.tar minio/minio:RELEASE.2024-12-18T13-15-44Z

把產生的 .tar 檔用 USB 或其他方式搬到另一台電腦。在那台電腦安裝好 Docker Desktop 後，於 PowerShell 載入映像檔：
docker load -i .\minio-RELEASE.2024-12-18T13-15-44Z.tar

接著把專案的 docker-compose.yml 也複製過去，在該檔案所在目錄啟動 MinIO：
docker compose up -d minio

映像檔與 MinIO 儲存資料是分開的：這些步驟只搬移 MinIO 程式，不會搬移原電腦 minio-data volume 裡的物件資料。若另一台電腦要離線啟動整個專案，也要先把 Compose 中其他服務所需的 Docker 映像檔一併打包搬過去；只載入 MinIO 映像檔不會包含它們。

請在目標電腦確認 Compose 檔實際使用的映像設定：
Select-String -Path .\docker-compose.yml -Pattern 'image:.*minio'

如果顯示 image: minio/minio:latest，請編輯 docker-compose.yml 的 minio 服務，把那一行改成：
image: minio/minio:RELEASE.2024-12-18T13-15-44Z
### 聊天無法連線到 Ollama

確認 Windows 上 Ollama 正在執行，`ollama list` 可列出兩個模型。接著查看 `docker compose logs --tail 100 api`。如果 Ollama 綁定在僅限容器無法存取的位址，請參閱 [plan.md 的 Ollama 連線說明](./plan.md)；不要將 Ollama 服務暴露到不可信任網路。

### 連接埠已被使用

本機的 `3000`（前端）或 `8000`（API）若已被其他程式占用，Compose 服務可能無法啟動。Milvus、MinIO 和其健康檢查使用的連接埠都只在 Docker 內部網路開放，不占用 Windows 主機埠。關閉占用 `3000` 或 `8000` 的程式後再執行 BAT。

### 服務啟動失敗

在專案目錄執行 `docker compose ps` 和 `docker compose logs --tail 100` 查看錯誤；確認網路連線、可用磁碟空間和 Docker Desktop 記憶體資源，再重新啟動。

## 安全提醒

本指南設定用於本機開發。不要把 `.env` 分享或提交，也不要在不可信網路公開 Compose 服務。MinIO 範例帳密及 HTTP Cookie 設定不是正式部署設定；對外部署前須另外設定 HTTPS、安全憑證與存取控制。
