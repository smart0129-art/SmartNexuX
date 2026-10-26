# NexuX

**NexuX** 是一套可在 Windows 本機執行的多模態 AI 知識工作區。使用者可以和 AI 對話、上傳文件並依文件內容搜尋，也可以透過 Agent 執行專案中明確註冊的 Python Skills。

系統以 Docker Compose 啟動前端、API 與向量資料庫；本機推論使用 Ollama，無須另外安裝 Python 或 Node.js。Windows 安裝與一鍵啟動步驟請見 [`Install.md`](./Install.md)。

## 功能特色

- **AI 串流聊天**：逐步顯示回覆，支援 Ollama 與 OpenAI Chat Completions 相容服務。
- **私人與共用知識庫**：上傳時可選擇僅自己可用，或分享給此 NexuX 上的所有帳號。
- **多模態解析**：支援常見文字、Office 文件、PDF 與圖片格式；可使用視覺模型處理圖片或掃描內容。
- **Agent 與 Skills**：Agent 以受控流程呼叫已註冊的 Python Skills，不執行任意使用者程式碼。
- **本機帳號**：提供 email／密碼註冊、登入與登出；密碼以 PBKDF2-HMAC-SHA256 雜湊保存。
- **資料隔離**：對話與私人文件依登入使用者隔離；明確標記為共用的文件可供所有登入帳號搜尋。
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
3. 雙擊專案根目錄的 `Start-NexuX.bat`，選擇「公司離線模式」或「線上建置模式」。
4. 離線模式使用已載入的 Docker images 與 Ollama 模型，不會建置、拉取或下載；線上模式會建置 images 並下載缺少的 Ollama 模型。
5. 完成後瀏覽器會開啟 `http://localhost:3000`；在登入頁選擇註冊，建立本機帳號後即可使用。

也可在命令列執行 `Start-NexuX.bat --offline` 或 `Start-NexuX.bat --online` 直接指定模式。兩種模式都使用 Docker Compose + 主機 Ollama，不需要在 Windows 安裝 Python、Node.js 或 npm。離線聊天會使用本機 Ollama；線上模式依 `.env` 的 `CHAT_DEFAULT_PROVIDER` 設定使用 Ollama 或 OpenAI 相容服務。一鍵啟動不會自動安裝 Windows 軟體、WSL 或顯示卡驅動。

### 預設 Admin 帳號與管理功能

系統預設會建立一個最高權限管理員帳號，方便首次部署時直接登入與驗證權限控制：

- Email: `admin@nexux.local`
- Password: `ChangeMeNow123!`

首次登入後請立即變更預設密碼，避免在公開 LAN / 內網環境留下高權限帳號。

本機網路公開入口會優先使用本機實際 IPv4 位址（若未取得則回退到 `http://localhost:3000`）。登入後若目前帳號角色為 `Admin`，可在右上角或 Dashboard 導覽中進入 `/admin` 管理頁面。管理頁面提供：

- 目前所有帳號的清單
- 每個使用者的角色與最後在線時間
- 是否在線上（依最近活動時間判定）
- 一鍵重設指定使用者的密碼；系統會產生臨時密碼，並要求使用者下次登入時先更新密碼
- 忘記密碼的 Token 申請與重設 API

管理員重設密碼後，請透過安全管道將畫面顯示的臨時密碼交給使用者。使用者以臨時密碼登入後，必須先設定新密碼才能繼續使用工作區。

忘記密碼可透過 `POST /api/auth/forgot-password` 申請重設 Token，再以 `POST /api/auth/reset-password` 提交 Token 與新密碼。這兩個 API 目前不會寄送電子郵件；申請成功時 Token 會直接包含在 API 回應中，效期為一小時且只能使用一次。登入／註冊畫面尚未提供自助重設密碼表單。

### 預設模型

| 模型 | 用途 |
|---|---|
| `qwen2.5vl:3b` | 預設聊天、Agent 與視覺文件解析 |
| `nomic-embed-text` | 文件向量化與檢索 |

線上建置模式會在模型尚未下載時呼叫 `ollama pull`；公司離線模式只檢查模型，不會下載。

### 最近更新與目前路由狀態

- 聊天預設 provider 為本機 `ollama`，預設模型為 `qwen2.5vl:3b`；線上建置模式可選擇設定 OpenAI 相容服務。
- 新增了「新對話列表」的刪除紀錄功能：在左側對話清單中可直接刪除既有對話紀錄，並在刪除後即時更新 UI 狀態與可選清單。
- 文件向量化使用 Ollama 的 `nomic-embed-text`；聊天模型與向量模型可各自設定。

## 上傳文件並建立向量索引

### 從 Dashboard 上傳

1. 登入 NexuX，使用右側「工作區 → 知識與執行資訊」面板。
2. 確認面板選取「知識庫」分頁（不是「Agent 執行記錄」）。
3. 點擊「新增至知識庫」，選擇一個或多個要匯入的檔案。多個檔案會逐一建立索引；進度區會顯示已完成數、總數及目前處理的檔名。每個檔案上限為 **100 MB**。
4. 如需讓這台 NexuX 的其他帳號也能檢索文件，勾選上傳按鈕下方的「分享給這台 NexuX 的所有帳號」。預設不勾選，文件只供目前帳號使用。完成後，文件會列在「知識庫」並標示「私人」或「共用」。

也可以在聊天輸入框點擊「新增附件」；附件會先建立索引，再用於該次對話，並預設加入私人知識庫。需要共用時，請從知識庫面板上傳並勾選共用選項。

支援的副檔名：`.bmp`、`.csv`、`.docx`、`.gif`、`.htm`、`.html`、`.jpeg`、`.jpg`、`.md`、`.pdf`、`.png`、`.pptx`、`.tif`、`.tiff`、`.txt`、`.webp`、`.xls`、`.xlsx`。`.doc` 等未列出的格式目前不支援。

### 上傳後如何解析及寫入向量

上傳後由後端自動完成，不需要手動執行 MarkItDown 或 Milvus 指令：

1. **檔案解析**：MarkItDown 將文件轉為文字／Markdown；PDF 會逐頁處理並保留頁碼與來源中繼資料。
2. **視覺內容辨識**：遇到圖片或掃描頁等視覺內容時，解析器會使用 Ollama 的 `qwen2.5vl:3b` 視覺模型協助擷取內容。一般文字檔案不需要 Qwen 做 OCR。
3. **大型文件切片**：依標題、段落等語意區塊切分；預設每片最多 **4,000 字元**，超長內容會保留 **300 字元重疊**，避免切片交界遺失上下文。PDF 切片也會帶有頁碼。
4. **向量化**：使用 Ollama 的 `nomic-embed-text` 為每個片段建立 **768 維向量**。
5. **寫入索引**：片段、向量及來源／頁碼中繼資料寫入 Milvus，建立向量與 BM25 全文混合搜尋索引。每筆資料包含擁有者 ID，搜尋只會查到目前帳號的文件。
6. **保存來源圖片**：PDF 含圖片或圖表的頁面會保存縮圖；DOCX、PPTX 與 XLSX 會保存能對應到索引內容的內嵌圖片。聊天回答最多附上 3 張與檢索片段相符的圖片，並標示來源與頁碼／投影片／工作表。原始上傳檔案不會永久保存；圖片衍生檔與文件索引一同保存在 Docker 資料 Volume。

聊天時，系統會自動從目前使用者已索引的文件檢索相關片段，提供給模型作為回答脈絡；如果相關片段有可對應的文件圖片，回答下方也會顯示圖片及其來源位置。圖片僅能由擁有該文件的登入使用者讀取。也可以在 Swagger UI 的 `POST /api/search` 直接測試知識搜尋。

圖片關聯只會在文件上傳索引時建立；既有索引沒有保存圖片，若要在回答中附圖，請重新上傳相關文件。

### 手動搜尋知識庫

登入後，點擊左側導覽列的「搜尋知識」，輸入文件中的關鍵字或問題並按 Enter／「搜尋」。也可以使用 `Ctrl+K`（macOS 為 `⌘K`）快速開啟搜尋面板。結果會顯示相關文字片段、來源文件及 PDF 頁碼；點選「用這份文件繼續提問」可將問題帶回聊天。搜尋只會檢索目前帳號已建立索引的文件。

### 動態 SOP 規則記憶層

動態 SOP 規則讓使用者可明確記錄設備或製程的修正指引，讓後續相關聊天與 Agent 提問自動帶入提示。規則儲存在 NexuX 使用的 SQLite 資料庫中；啟動時會自動建立 `rule_memories` 資料表，不需另外執行資料庫遷移。每筆資料包含規則 ID、擁有者 ID、設備關鍵字、製程關鍵字、規則內容、建立時間及更新時間。每筆規則至少要有一個設備或製程關鍵字，關鍵字最多各 20 個且每個最多 80 字元，規則內容最多 4,000 字元。

#### 新增規則

先在 `http://localhost:8000/docs` 登入／註冊 NexuX 帳號，再以同一個登入 session 呼叫 API。以下是新增規則的 JSON：

```json
{
  "equipment_keywords": ["CNC-900"],
  "process_keywords": ["換線"],
  "content": "執行換線前先停機、完成鎖定掛牌並確認零能量。"
}
```

呼叫 `POST /api/rules` 建立規則，成功回應為 HTTP 201，內容包含新產生的 `rule_id`、`owner_id`、關鍵字、規則內容及建立／更新時間。也可在 Windows PowerShell 以 `curl.exe` 登入並用 cookie jar 保留 session，再新增規則：

```powershell
$cookieFile = Join-Path $env:TEMP "nexux-cookies.txt"
curl.exe -c $cookieFile -b $cookieFile `
  -H "Content-Type: application/json" `
  -d '{"email":"your-account@example.com","password":"your-password"}' `
  http://localhost:8000/api/auth/login

curl.exe -c $cookieFile -b $cookieFile `
  -H "Content-Type: application/json" `
  -d '{"equipment_keywords":["CNC-900"],"process_keywords":["換線"],"content":"執行換線前先停機、完成鎖定掛牌並確認零能量。"}' `
  http://localhost:8000/api/rules
```

請以實際帳號取代範例登入資料，並妥善保管 cookie jar 檔案；其中包含登入 session，不要提交或分享。

#### 列出、更新與刪除

- `GET /api/rules`：列出目前登入者建立的規則，依最近更新時間排序。
- `PUT /api/rules/{rule_id}`：更新指定規則。使用建立規則時相同的 JSON 欄位；這是完整取代更新，請在 request 中提供最新的設備關鍵字、製程關鍵字與規則內容。
- `DELETE /api/rules/{rule_id}`：刪除指定規則，成功回應為 HTTP 204。

例如，使用新增 API 回應中的 ID 更新規則：

```powershell
$ruleId = "填入 POST /api/rules 回傳的 rule_id"
$cookieFile = Join-Path $env:TEMP "nexux-cookies.txt"
curl.exe -c $cookieFile -b $cookieFile `
  -X PUT -H "Content-Type: application/json" `
  -d '{"equipment_keywords":["CNC-900"],"process_keywords":["換線","維修"],"content":"作業前停機並執行鎖定掛牌；確認零能量後才可開始。"}' `
  "http://localhost:8000/api/rules/$ruleId"
```

#### 規則如何套用到回答

在 `POST /api/chat/stream` 的 `prompt`，以及 `POST /api/agent/run` 的 `prompt` 中，系統會以不區分大小寫的子字串比對問題與目前使用者的設備／製程關鍵字；任一關鍵字符合即命中，最多注入五筆規則。符合時，規則會在 RAG 文件及對話歷史之前加入 `[強制防禦／最新SOP修正指引]` 區塊，提示模型優先遵循規則；沒有符合的規則時，正常組裝其他上下文，不會加入此區塊。

規則以擁有者隔離，其他使用者無法列出、更新或刪除該規則。規則需透過 API 明確手動新增或更新，系統不會由聊天內容自動推斷／寫入規則。這個 prompt 區塊是給模型的高優先權指引，並非硬性的安全控制，也不應取代經核准的正式安全 SOP。

更新程式後，需重新建置並啟動 API 容器，規則功能才會在執行中的服務啟用；一般線上環境可執行 `docker compose up -d --build api`。離線環境請先在可建置的環境產生新版 `nexux-api:latest` image，並依「準備離線電腦」更新及搬移 image bundle，再使用離線啟動模式。已有的規則會留在 SQLite 資料 Volume 中，不會因重建 API image 而移除。

### 在沒有網路的電腦間搬移 RAG

在 Dashboard 右側「工作區資訊 → 知識庫」下方點選「備份 RAG」，即可下載目前登入帳號可存取的已索引資料 ZIP；在目的端相同位置點選「匯入 ZIP」並選取備份檔，即可匯入。勾選「更新先前匯入的對應文件」會更新已同步文件；不勾選時則略過重複項目。

若要在離線電腦間搬移，先在來源端點選「備份 RAG」，使用 USB 等離線方式將 ZIP 搬到目的電腦，再於公司端點選「匯入 ZIP」。兩台 NexuX 不必彼此互通；目的端須先啟動 NexuX。此 Dashboard 功能會使用目前登入帳號，若在遠端公司主機操作，也不必另行輸入 API URL。命令列 `RAG-Sync.bat` 仍可供自動化或疑難排解時使用。

匯入預設會合併至目前登入帳號的知識庫：新增文件、更新先前同步的對應文件，並略過目的端既有但非此同步來源的文件。系統先依來源文件 ID 配對；來源重新上傳而產生新 ID 時，只有當封存與目的端各自都只有一份同名的已同步文件，才會以檔名配對更新（忽略大小寫）。僅以檔名配對時，同名多份會新增，不會猜測替換對象；來源 ID 完全相同仍可精確更新。`RAG-Sync.bat` 匯入時可選擇是否更新；選「N」則採用只新增、略過重複文件的模式。匯入不會覆蓋其他文件。這會搬移已索引的文字片段、向量、文件資訊及檢索圖片，不包含原始上傳檔、帳號或聊天紀錄；來源上傳的原始檔案並未永久保存。兩台電腦應使用相同的 embedding 模型與向量維度。ZIP 含文件內容，請妥善保管並只傳給授權使用者。

匯出的共用文件匯入後會維持共用；私人文件維持私人。若公司端其他登入帳號也需要使用，請確保來源文件是共用狀態，並在目的端以有權管理該知識資料的帳號匯入。共用範圍是「同一台 NexuX 上所有已登入帳號」，不會讓未登入者或其他 NexuX 主機直接存取。若來源端或目的端更新過程式，請先使用新版 `Start-NexuX.bat` 重新建置／啟動，再執行同步；封存會在匯出後驗證 ZIP 格式、文件數及索引片段數，匯入前也會再次檢查封存結構。

若上傳失敗，先確認 Ollama 正在執行，且 `ollama list` 有 `qwen2.5vl:3b` 和 `nomic-embed-text`；再查看 `docker compose logs --tail 100 api`。不支援格式回 HTTP 415，檔案超過 100 MB 回 HTTP 413，解析失敗回 HTTP 422，Ollama 或 Milvus 無法使用回 HTTP 503。

PPTX／PDF 中個別圖片的 OCR 若遇到 `invalid image input` 或 `token repeat limit reached`，解析器會記錄警告並使用 MarkItDown 的原生解析結果繼續索引；圖片中的文字或內容可能不會出現在搜尋結果中。若需要圖片內容也能被搜尋，請確認 Ollama 正常且視覺模型可用後重新上傳；API 日誌會記錄 OCR 失敗原因。

## 常用網址與指令

| 項目 | 網址／指令 |
|---|---|
| 使用者介面 | <http://localhost:3000> |
| API 文件（Swagger UI） | <http://localhost:8000/docs> |
| API 健康檢查 | <http://localhost:8000/health> |
| 啟動／更新服務 | 雙擊 `Start-NexuX.bat` 選擇線上或離線模式 |
| 查看服務狀態 | `docker compose ps` |
| 查看 API 記錄 | `docker compose logs --tail 100 api` |
| 停止 NexuX 並保留資料 | 雙擊 `Stop-NexuX.bat`，或執行 `docker compose down` |

`Stop-NexuX.bat` 也會關閉由 `Start-NexuX.bat` 啟動的 Ollama；其他 Ollama 服務不會受影響。預設不會退出 Docker Desktop；如要一併退出，請執行 `Stop-NexuX.bat --quit-docker`。停止服務時不要在 `docker compose down` 後加 `-v`，否則會刪除 Docker Volume 內的帳號、對話與檢索資料。

## API 概覽

完整請求／回應格式可在啟動系統後透過 Swagger UI 查看。

| 方法 | 路徑 | 說明 |
|---|---|---|
| `POST` | `/api/auth/register` | 建立帳號並登入 |
| `POST` | `/api/auth/login` | 登入 |
| `POST` | `/api/auth/change-password` | 驗證目前密碼後更新密碼 |
| `POST` | `/api/auth/forgot-password` | 申請密碼重設 Token（目前由 API 回傳，不寄送電子郵件） |
| `POST` | `/api/auth/reset-password` | 使用有效的重設 Token 設定新密碼 |
| `GET` | `/api/auth/me` | 取得目前登入使用者 |
| `POST` | `/api/auth/logout` | 登出 |
| `GET` | `/api/admin/users` | 列出帳號、角色、在線狀態及最後在線時間（Admin 限定） |
| `POST` | `/api/admin/users/{user_id}/reset-password` | 重設指定帳號密碼並要求下次登入時更新（Admin 限定） |
| `GET`, `POST` | `/api/conversations` | 列出或建立對話 |
| `GET`, `DELETE` | `/api/conversations/{id}` | 載入或刪除自己的對話 |
| `GET`, `POST` | `/api/documents` | 列出目前帳號可存取的文件（自己的私人文件及共用文件），或上傳文件；上傳可帶 `is_shared=true` |
| `GET` | `/api/documents/export` | 匯出目前登入者的 RAG 封存 |
| `POST` | `/api/documents/import` | 合併 RAG 封存；可用 `update_existing=true` 更新同來源匯入的文件 |
| `GET` | `/api/documents/{id}/images/{image_id}` | 讀取自己文件中的索引圖片 |
| `GET`, `POST` | `/api/rules` | 列出自己的規則或新增 SOP 規則 |
| `PUT`, `DELETE` | `/api/rules/{rule_id}` | 更新或刪除自己的 SOP 規則 |
| `POST` | `/api/search` | 搜尋自己的私人文件及共用知識庫 |
| `POST` | `/api/chat/stream` | 以 SSE 串流聊天 |
| `POST` | `/api/agent/run` | 執行 Agent |
| `GET` | `/api/models`, `/api/skills` | 列出模型與已註冊 Skills |

除註冊、登入、登出及忘記／重設密碼 API 外，工作區 API 需要有效的登入 session。管理 API 另需 Admin 角色。

## 設定

一鍵啟動會從 [`.env.example`](./.env.example) 建立本機 `.env`，並產生隨機的 `SESSION_SECRET`。預設設定可在 Windows 本機使用 Ollama，不需要 OIDC 設定。

若要調整設定，請編輯本機 `.env`，例如：

- `CHAT_DEFAULT_PROVIDER`：預設聊天服務，預設為本機 `ollama`；線上建置模式可設為 `openai_compatible`。
- `OLLAMA_CHAT_MODELS`：允許使用的 Ollama 聊天模型。
- `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_CHAT_MODELS`：選用的 OpenAI 相容服務設定；模型名稱需改成服務實際支援的名稱。
- `SESSION_SECRET`：簽署登入 session 的秘密金鑰；請保留在本機，不要分享或提交。
- `COOKIE_SECURE`：本機 HTTP 開發為 `false`；使用 HTTPS 部署時必須設為 `true`。

設定外部模型時，API key 僅透過本機環境變數傳入。不要把 `.env`、API key 或 session secret 提交到版本控制。

## 資料與安全

- SQLite、Milvus、MinIO 和 etcd 資料使用 Docker Compose named volumes 保存；重新啟動或執行 `docker compose down` 不會移除資料。私人文件只供上傳者使用；勾選共用的文件可供所有登入帳號檢索。
- 專案原始碼資料夾不包含 Docker Volume。移轉到另一台電腦時，預設會建立新的工作區；要搬移既有帳號與內容，需另外備份及還原 Docker Volume。
- `.env` 含有 session 簽署金鑰，遺失或變更後，既有登入 session 將失效。
- 專案預設為本機開發環境；MinIO 範例帳密、HTTP Cookie 與服務設定不可直接作為對外正式部署設定。
- 本機帳號目前沒有 email 驗證、密碼重設郵件寄送或登入節流。忘記密碼 API 會將 Token 直接回傳給呼叫端，不應當作已驗證的電子郵件重設流程；請勿將未加強的開發部署公開到不可信任網路。

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
