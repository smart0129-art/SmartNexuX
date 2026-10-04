# NexuX

**NexuX** 是一套可在 Windows 本機執行的多模態 AI 知識工作區。使用者可以和 AI 對話、上傳文件並依文件內容搜尋，也可以透過 Agent 執行專案中明確註冊的 Python Skills。

系統以 Docker Compose 啟動前端、API 與向量資料庫；本機推論使用 Ollama，無須另外安裝 Python 或 Node.js。Windows 安裝與一鍵啟動步驟請見 [`Install.md`](./Install.md)。

## 功能特色

- **AI 串流聊天**：逐步顯示回覆，支援 Ollama 與 OpenAI Chat Completions 相容服務。
- **個人知識庫**：上傳文件、解析內容、建立向量索引，並在聊天與搜尋中檢索相關資料。
- **多模態解析**：支援常見文字、Office 文件、PDF 與圖片格式；可使用視覺模型處理圖片或掃描內容。
- **Agent 與 Skills**：Agent 以受控流程呼叫已註冊的 Python Skills，不執行任意使用者程式碼。
- **本機帳號**：提供 email／密碼註冊、登入與登出；密碼以 PBKDF2-HMAC-SHA256 雜湊保存。
- **資料隔離**：對話、文件與搜尋依登入使用者隔離。
- **繁體中文介面**：採響應式 Dashboard，並提供聊天歷史與 Agent 執行資訊。

## 架構

```text
瀏覽器
  └── Next.js 前端（localhost:3000）
        └── FastAPI 後端（localhost:8000）
              ├── Ollama（主機 localhost:11434）
              ├── SQLite（帳號、對話與文件索引資料）
              └── Milvus（向量與全文檢索）
                    ├── etcd（中繼資料）
                    └── MinIO（物件儲存）
```

前端與 API 的連接埠會映射到主機；Milvus、MinIO 和 etcd 僅供 Docker Compose 內部服務通訊。

## 快速開始

### 需求

- Windows 10／11 64 位元，並已啟用硬體虛擬化。
- [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) 與 WSL 2。
- [Ollama for Windows](https://ollama.com/download/windows)。
- 建議至少 16 GB 記憶體及 20 GB 可用磁碟空間。無 GPU 也可執行，但推論速度可能較慢。

### 啟動

1. 依 [`Install.md`](./Install.md) 安裝 WSL 2、Docker Desktop 和 Ollama。
2. 將完整專案原始碼放到本機，啟動 Docker Desktop。
3. 雙擊專案根目錄的 `Start-NexuX.bat`。
4. 第一次啟動會建置容器，並在需要時下載 Ollama 模型；完成後瀏覽器會開啟 `http://localhost:3000`。
5. 在登入頁選擇註冊，建立本機帳號後即可使用。

一鍵啟動會檢查並嘗試啟動 Docker Desktop 和 Ollama、下載缺少的預設模型、建立本機 `.env`，並在前後端就緒後開啟首頁。它不會自動安裝 Windows 軟體、WSL 或顯示卡驅動。

### 預設模型

| 模型 | 用途 |
|---|---|
| `qwen2.5vl:3b` | 預設聊天、Agent 與視覺文件解析 |
| `nomic-embed-text` | 文件向量化與檢索 |

一鍵啟動會在模型尚未下載時呼叫 `ollama pull`。請預留下載時間與磁碟空間。

## 上傳文件並建立向量索引

### 從 Dashboard 上傳

1. 登入 NexuX，使用右側「工作區 → 知識與執行資訊」面板。
2. 確認面板選取「知識庫」分頁（不是「Agent 執行記錄」）。
3. 點擊「新增至知識庫」，選擇要匯入的檔案。每個檔案上限為 **100 MB**。
4. 等待按鈕上的「正在建立文件索引…」完成。成功後，文件會列在「你的文件 → 知識庫」下方，並顯示已建立的「索引片段」數。

也可以在聊天輸入框點擊「新增附件」；附件會先建立索引，再用於該次對話，並加入個人知識庫。

支援的副檔名：`.bmp`、`.csv`、`.docx`、`.gif`、`.htm`、`.html`、`.jpeg`、`.jpg`、`.md`、`.pdf`、`.png`、`.pptx`、`.tif`、`.tiff`、`.txt`、`.webp`、`.xls`、`.xlsx`。`.doc` 等未列出的格式目前不支援。

### 上傳後如何解析及寫入向量

上傳後由後端自動完成，不需要手動執行 MarkItDown 或 Milvus 指令：

1. **檔案解析**：MarkItDown 將文件轉為文字／Markdown；PDF 會逐頁處理並保留頁碼與來源中繼資料。
2. **視覺內容辨識**：遇到圖片或掃描頁等視覺內容時，解析器會使用 Ollama 的 `qwen2.5vl:3b` 視覺模型協助擷取內容。一般文字檔案不需要 Qwen 做 OCR。
3. **大型文件切片**：依標題、段落等語意區塊切分；預設每片最多 **4,000 字元**，超長內容會保留 **300 字元重疊**，避免切片交界遺失上下文。PDF 切片也會帶有頁碼。
4. **向量化**：使用 Ollama 的 `nomic-embed-text` 為每個片段建立 **768 維向量**。
5. **寫入索引**：片段、向量及來源／頁碼中繼資料寫入 Milvus，建立向量與 BM25 全文混合搜尋索引。每筆資料包含擁有者 ID，搜尋只會查到目前帳號的文件。
6. **保存文件清單**：SQLite 記錄檔名、片段數與上傳時間；原始上傳檔案不會以原檔形式永久保存在 NexuX 的文件清單中。

聊天時，系統會自動從目前使用者已索引的文件檢索相關片段，提供給模型作為回答脈絡。也可以在 Swagger UI 的 `POST /api/search` 直接測試知識搜尋。

### 手動搜尋知識庫

登入後，點擊左側導覽列的「搜尋知識」，輸入文件中的關鍵字或問題並按 Enter／「搜尋」。也可以使用 `Ctrl+K`（macOS 為 `⌘K`）快速開啟搜尋面板。結果會顯示相關文字片段、來源文件及 PDF 頁碼；點選「用這份文件繼續提問」可將問題帶回聊天。搜尋只會檢索目前帳號已建立索引的文件。

若上傳失敗，先確認 Ollama 正在執行，且 `ollama list` 有 `qwen2.5vl:3b` 和 `nomic-embed-text`；再查看 `docker compose logs --tail 100 api`。不支援格式回 HTTP 415，檔案超過 100 MB 回 HTTP 413，解析失敗回 HTTP 422，Ollama 或 Milvus 無法使用回 HTTP 503。

PPTX／PDF 中個別圖片的 OCR 若遇到 `invalid image input` 或 `token repeat limit reached`，解析器會記錄警告並使用 MarkItDown 的原生解析結果繼續索引；圖片中的文字或內容可能不會出現在搜尋結果中。若需要圖片內容也能被搜尋，請確認 Ollama 正常且視覺模型可用後重新上傳；API 日誌會記錄 OCR 失敗原因。

## 常用網址與指令

| 項目 | 網址／指令 |
|---|---|
| 使用者介面 | <http://localhost:3000> |
| API 文件（Swagger UI） | <http://localhost:8000/docs> |
| API 健康檢查 | <http://localhost:8000/health> |
| 啟動／更新服務 | `docker compose up --build -d` |
| 查看服務狀態 | `docker compose ps` |
| 查看 API 記錄 | `docker compose logs --tail 100 api` |
| 停止服務並保留資料 | `docker compose down` |

停止服務時不要加 `-v`，否則會刪除 Docker Volume 內的帳號、對話與檢索資料。

## API 概覽

完整請求／回應格式可在啟動系統後透過 Swagger UI 查看。

| 方法 | 路徑 | 說明 |
|---|---|---|
| `POST` | `/api/auth/register` | 建立帳號並登入 |
| `POST` | `/api/auth/login` | 登入 |
| `GET` | `/api/auth/me` | 取得目前登入使用者 |
| `POST` | `/api/auth/logout` | 登出 |
| `GET`, `POST` | `/api/conversations` | 列出或建立對話 |
| `GET`, `DELETE` | `/api/conversations/{id}` | 載入或刪除自己的對話 |
| `GET`, `POST` | `/api/documents` | 列出文件或上傳文件 |
| `POST` | `/api/search` | 搜尋自己的知識庫 |
| `POST` | `/api/chat/stream` | 以 SSE 串流聊天 |
| `POST` | `/api/agent/run` | 執行 Agent |
| `GET` | `/api/models`, `/api/skills` | 列出模型與已註冊 Skills |

除註冊、登入與登出外，工作區 API 需要有效的登入 session。

## 設定

一鍵啟動會從 [`.env.example`](./.env.example) 建立本機 `.env`，並產生隨機的 `SESSION_SECRET`。預設設定可在 Windows 本機使用 Ollama，不需要 OIDC 設定。

若要調整設定，請編輯本機 `.env`，例如：

- `CHAT_DEFAULT_PROVIDER`：預設聊天服務，預設為 `ollama`。
- `OLLAMA_CHAT_MODELS`：允許使用的 Ollama 聊天模型。
- `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_CHAT_MODELS`：選用的 OpenAI 相容服務設定。
- `SESSION_SECRET`：簽署登入 session 的秘密金鑰；請保留在本機，不要分享或提交。
- `COOKIE_SECURE`：本機 HTTP 開發為 `false`；使用 HTTPS 部署時必須設為 `true`。

設定外部模型時，API key 僅透過本機環境變數傳入。不要把 `.env`、API key 或 session secret 提交到版本控制。

## 資料與安全

- SQLite、Milvus、MinIO 和 etcd 資料使用 Docker Compose named volumes 保存；重新啟動或執行 `docker compose down` 不會移除資料。
- 專案原始碼資料夾不包含 Docker Volume。移轉到另一台電腦時，預設會建立新的工作區；要搬移既有帳號與內容，需另外備份及還原 Docker Volume。
- `.env` 含有 session 簽署金鑰，遺失或變更後，既有登入 session 將失效。
- 專案預設為本機開發環境；MinIO 範例帳密、HTTP Cookie 與服務設定不可直接作為對外正式部署設定。
- 本機帳號功能目前沒有 email 驗證、密碼重設或登入節流；請勿將未加強的開發部署公開到不可信任網路。

## 開發與測試

執行後端測試需先有 Python 環境並安裝 `backend/requirements.txt`，例如：

```powershell
Push-Location backend
python -m unittest discover -s tests -v
Pop-Location
```

前端 lint 與 build 可透過 Docker 執行，不需要在 Windows 安裝 Node.js：

```powershell
docker compose run --rm --no-deps frontend npm run lint
docker compose run --rm --no-deps frontend npm run build
```

## 疑難排解

- **Docker Desktop 未啟動**：開啟 Docker Desktop，等待 Engine 顯示為執行中，再重新執行 `Start-NexuX.bat`。
- **聊天無法連線到 Ollama**：確認 Ollama 正在執行，且 `ollama list` 可列出上述模型；查看 `docker compose logs --tail 100 api`。
- **連接埠衝突**：主機只映射前端 `3000` 與 API `8000`。若被占用，停止占用該埠的程式後再啟動。
- **容器未正常啟動**：執行 `docker compose ps` 及 `docker compose logs --tail 100` 檢查服務記錄。

更多 Windows 安裝、Ollama 連線與啟動說明請見 [`Install.md`](./Install.md)；專案設計及 API 細節請見 [`plan.md`](./plan.md)。
