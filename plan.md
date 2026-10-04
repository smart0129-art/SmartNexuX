# 企業級多模態 AI 知識平台

## 專案狀態

- 目前階段：Phase 4.2 — 本機帳號密碼登入、SSE 聊天、文件上傳、歷史紀錄與使用者隔離。
- 已完成進度：Phase 0、Phase 1.1–1.3、Phase 2.1–2.2、Phase 3、Phase 4.1、Phase 4.2 實作及自動／整合驗證。
- 手動驗證：Phase 0 至 Phase 4.1 均已由使用者確認通過；本機帳號密碼註冊／登入流程待手動驗證。
- Python 虛擬環境偏好：未來開始 Python 建置前，先詢問是否使用專案 `.venv`；未確認前不建立或安裝本機虛擬環境套件。
- 本機建置環境：使用既有 `.venv`（Python 3.11.6）；程式需同時相容 Python 3.11 與 3.12。
- Embedding 模型：`nomic-embed-text`；Milvus 向量維度為 768。

## 系統架構

```text
瀏覽器（Next.js App Router + Tailwind + Zustand；Phase 4.1 Dashboard）
  └── FastAPI（backend/app/main.py；連接埠 8000）
        ├── Ollama（主機服務；Docker 容器透過 host.docker.internal:11434 存取）
        └── Milvus Standalone（連接埠 19530）
              ├── etcd 中繼資料
              └── MinIO 物件儲存
```

- 後端：Python 3.12、FastAPI、Pydantic v2、非同步請求處理。
- 文件匯入：MarkItDown 與 OCR plugin；PDF 逐頁處理，使用 Qwen2.5-VL 擷取圖片／掃描頁內容，依標題、段落及圖片邊界動態切片。
- 檢索：Milvus Collection 使用 768 維向量、HNSW/COSINE 索引及 BM25 全文索引；支援語意與關鍵字混合搜尋。
- Agent：使用 Ollama `qwen2.5vl:3b` 依 JSON Schema 產生受控 ReAct 決策，只呼叫註冊式 Python Skills；每次呼叫與結果記入回應。
- 聊天路由：`ChatModelRouter` 支援本機 Ollama 與可設定的 OpenAI Chat Completions 相容端點；SSE 提供 token、使用量及錯誤事件。
- 身份與對話：本機 email／密碼註冊登入，密碼以 PBKDF2-HMAC-SHA256 雜湊保存；SQLite 命名 Volume 保存帳號索引與對話紀錄，對話及新上傳文件依使用者隔離。Milvus 文件 JSON metadata 同步保存 owner UUID，混合檢索套用 owner filter。
- 前端：Next.js App Router、Tailwind CSS、Zustand；三艙式暗色儀表板，Phase 4.2 串接本機帳號註冊登入、模型目錄、SSE 聊天、文件上傳、歷史紀錄及 Agent 執行資訊。
- 前端語系：使用者介面採繁體中文（`zh-Hant`），保留品牌名稱、模型／Skill ID 與必要技術術語。
- 視覺方向：暗色極簡風格（`#090D16` 至 `#0F172A`）與玻璃擬態。

## API 規範

| 方法 | 路徑 | 用途 | 狀態 |
|---|---|---|---|
| GET | `/health` | 後端存活狀態 | Phase 0 已實作 |
| POST | `/api/auth/register`、`/api/auth/login` | 建立本機帳號或登入，成功後設定 session cookie | Phase 4.2 已實作 |
| GET | `/api/auth/me`、`POST /api/auth/logout` | 查詢目前使用者或清除 session；需有效 session（登出除外） | Phase 4.2 已實作 |
| GET/POST | `/api/conversations`、`GET/DELETE /api/conversations/{id}` | 使用者專屬對話清單、建立、載入及刪除；需登入 | Phase 4.2 已實作 |
| GET/POST | `/api/documents` | 使用者專屬文件清單；multipart 上傳、解析、Embedding 寫入 Milvus | Phase 4.2 已實作 |
| POST | `/api/search` | 登入後以 owner filter 執行語意＋BM25 混合搜尋 | Phase 4.2 已實作 |
| POST | `/api/agent/run` | 以受控 ReAct 執行已註冊 Skill；支援歷史與使用者文件脈絡 | Phase 4.2 已實作 |
| GET | `/api/models`、`/api/skills` | 列出已設定模型與註冊 Skills；需登入 | Phase 4.2 已實作 |
| POST | `/api/chat/stream` | 依選定供應商／模型以 SSE 串流聊天；持久化對話、Token usage 與附件 ID；需登入 | Phase 4.2 已實作 |

各階段實作時，再記錄 API 載荷、驗證與錯誤回應格式。Phase 0 健康檢查回應為 `{"status":"ok"}`。

### Phase 1.3 API 合約

- `POST /api/documents`：Phase 4.2 起需有效 session；`multipart/form-data` 欄位 `file`。單檔上限預設 100 MiB（`MAX_UPLOAD_BYTES` 可調）。成功回傳 HTTP 201 與 `{"document_id":"<uuid>","source_name":"<檔名>","chunks_indexed":1,"uploaded_at":"<ISO-8601>"}`。副檔名不支援回傳 415、超限回傳 413、無法解析回傳 422、Embedding／Milvus 無法使用回傳 503。
- `POST /api/search`：需登入；JSON 欄位 `query`（必填）、`top_k`（預設 5，範圍 1–50）、`document_id`（選填 UUID 篩選）。搜尋固定套用目前使用者 UUID owner filter；回傳 `results`，每筆包含 chunk ID、文件 ID、chunk 索引、文字、RRF 分數及來源中繼資料。
- Nomic Embedding 使用 `search_document:` 與 `search_query:` 前綴；向量維度必須符合 Milvus Collection 設定。無效 Embedding 回應會回報錯誤，不會靜默略過資料。

### Phase 2.2 Agent API 合約

- `POST /api/agent/run`：需登入；JSON 欄位 `prompt`（必填、去除首尾空白後不得為空，最長 8192 字元）、可選 `conversation_id` 及最多 10 個 `attachment_ids`。Agent 使用該使用者的最近對話及 owner-scoped 文件檢索脈絡，並將使用者／助理回合、附件及 Tool calls 持久化。Agent 呼叫 Ollama `/api/chat`，以 Pydantic JSON Schema 約束 `call_skill`／`final_answer` 決策；僅能執行 Registry 中的 Skill。
- `AGENT_MODEL` 預設 `qwen2.5vl:3b`；`AGENT_MAX_TOOL_CALLS` 預設 5，允許 0–20 次 Skill 呼叫。Ollama 連線及伺服器錯誤會重試最多 3 次。
- 成功回傳 `{"answer":"...","tool_calls":[{"skill_name":"...","arguments":{},"result":{},"error":null}]}`。無效輸入回傳 422、Ollama 不可用回傳 503、模型回應不符合決策協定或超出工具呼叫上限回傳 502。
- 未註冊 Skill 與參數驗證失敗會成為錯誤 observation，提供模型修正；Skill handler 執行失敗及不可 JSON 序列化的回傳值會明確失敗，不會偽裝成成功。

### Phase 3 聊天 API／模型路由合約

- `GET /api/models` 回傳預設 provider/model 及依環境設定的模型目錄；外部模型的 `configured` 只表示已提供 API key，不代表已連線測試。
- Phase 4.2 起 `GET /api/models` 與 `POST /api/chat/stream` 需有效 session。聊天 JSON 接受 `prompt`（必填，去除首尾空白後不得為空，最長 8192 字元）、`provider`（`ollama` 或 `openai_compatible`，省略時使用預設值）、可選 `model`、`conversation_id` 及最多 10 個已擁有的 `attachment_ids`。模型必須列在相應 provider 的允許清單中。
- SSE 事件格式：`meta` 提供供應商／模型／對話 ID；每個 `token` 傳送 `{"token":"..."}`；`done` 傳送完整答案、`conversation_id`、`message_id` 及 `prompt_tokens`、`completion_tokens`、`total_tokens` 和使用量來源；串流開始後的 provider 錯誤以 `error` 事件回報。Provider 未提供 usage 時，以 UTF-8 位元組長度估算並標示 `source: "estimate"`。如提供對話 ID，使用者訊息先持久化，助理訊息於成功結束後連同 usage 保存。
- `CHAT_DEFAULT_PROVIDER` 預設 `ollama`；`OLLAMA_CHAT_MODELS` 預設 `qwen2.5vl:3b`。OpenAI 相容端點設定為 `OPENAI_BASE_URL`（預設 OpenAI API）、`OPENAI_API_KEY`（外部呼叫必填）與 `OPENAI_CHAT_MODELS`（預設 `gpt-4o-mini`）。
- 無效輸入或未設定模型回傳 422；選擇外部 provider 但沒有 API key 回傳 503。API key 只透過環境變數傳入，不應寫入程式碼或提交至版本控制。

### Phase 4.2 身份、對話與工作區 API 合約

- `POST /api/auth/register` 接受 email、至少 8 字元的密碼及選填顯示名稱；`POST /api/auth/login` 接受 email 與密碼。email 會去除首尾空白並轉為小寫；重複註冊回 HTTP 409，登入資訊錯誤回 HTTP 401。密碼使用 PBKDF2-HMAC-SHA256 雜湊後儲存，不會以明文保存。
- `SESSION_SECRET` 用於簽署 HttpOnly、SameSite=Lax、預設 8 小時 session cookie；若留白，API 啟動時建立暫時隨機密鑰並記錄警告，重啟後登入失效。正式／持續使用須在本機 `.env` 設定強隨機密鑰；絕不可貼入對話或提交。HTTPS 部署設 `COOKIE_SECURE=true`。
- `FRONTEND_ORIGINS` 為逗號分隔的明確允許 Origin 清單。變更 API 請求會拒絕不信任的 `Origin`。
- `/api/auth/me`、`/api/models`、`/api/skills`、`/api/agent/run`、`/api/chat/stream`、`/api/conversations`、`/api/documents`、`/api/search` 都需要登入；未登入回 HTTP 401。對話或文件不屬於目前使用者時回 HTTP 404，避免洩漏其他使用者資料是否存在。
- `POST /api/conversations` 接受 `{"title":"New conversation"}`（標題可省略）；回傳 `id/title/created_at/updated_at`。`GET /api/conversations` 僅列出目前使用者資料；`GET /api/conversations/{id}` 回傳訊息及 usage/tool calls/attachment IDs；`DELETE` 只刪除本人對話。
- SQLite 預設路徑 `/data/nexux.sqlite3`，Compose 以 `nexux-data` 命名 Volume 持久化 users（含雜湊後密碼）、conversations、messages 及 documents 索引；現有 users 資料表會在啟動時遷移新增密碼欄位。Milvus 新文件 chunk 的 JSON `metadata.owner_id` 儲存同一使用者 UUID；對話引用／搜尋以該 UUID 限制範圍。過往沒有 owner metadata 的 Milvus 文件不會自動分享或顯示，需由使用者重新上傳才能納入隔離後的工作區。
- 文件附件先由前端上傳並索引，回傳 document ID 再附加到聊天／Agent 請求；最多 10 個，且 API 驗證每個 ID 的擁有者。聊天和 Agent 均會以使用者文件做 hybrid search，將有限長度的命中結果與最近對話組合為模型脈絡。

## Skills 清單

已實作的 Skill 註冊系統與初始範例：

- `@skill` 裝飾器、唯一名稱註冊、描述及 Pydantic v2 參數模型驗證。
- `SkillRegistry` 提供 Skill 清單、Function Calling 工具 JSON Schema，以及同步／非同步 handler 呼叫；同步 handler 透過 `asyncio.to_thread` 執行。
- 內建 `text_stats` 純運算範例，並由 `GET /api/skills` 公開已註冊技能與參數 Schema。
- Agent 使用受 JSON Schema 約束的 ReAct 動作格式（非 Ollama 原生 `tools`）；每輪只允許 `call_skill` 或 `final_answer`，並以設定值限制 Skill 呼叫次數。
- 目前只執行程式明確註冊的 Skills，不執行使用者任意提供的 Python 程式碼；外部模型路由與 SSE 已於 Phase 3 實作，Phase 4.2 起相關工作區 API 需登入。

## 本機服務與指令

Windows 安裝、前置需求及一鍵啟動請參閱 [Install.md](./Install.md)；完成 Docker Desktop 與 Ollama 安裝後，可雙擊專案根目錄的 `Start-NexuX.bat`。

### Windows 上的 Ollama

在主機環境執行 Ollama（不包含在本 Compose 服務中）：

```powershell
ollama serve
ollama pull qwen2.5vl:3b
ollama pull nomic-embed-text
ollama list
```

`nomic-embed-text` 將於 Phase 1.3 用於文件 Embedding。模型就緒後，可測試 Ollama 本機 API：

```powershell
curl.exe -sS http://localhost:11434/api/generate -H "Content-Type: application/json" -d '{"model":"qwen2.5vl:3b","prompt":"Reply with OK only.","stream":false}'
```

API 容器設定透過 `http://host.docker.internal:11434` 連線至主機上的 Ollama。若 Ollama 僅接受 loopback 連線，導致 Docker Desktop 無法存取，請在啟動 Ollama 前設定主機綁定：

```powershell
$env:OLLAMA_HOST = "0.0.0.0:11434"
ollama serve
```

Ollama 執行期間請保持該 PowerShell 視窗開啟。綁定所有網路介面可能讓其他裝置存取 API，請只在可信任網路使用並以 Windows 防火牆限制存取；不要將 Ollama 連接埠暴露給不可信任的網路。

### Docker Compose

在專案根目錄啟動 API 與 Milvus 相依服務：

```powershell
docker compose up --build -d
docker compose ps
docker compose logs --tail 100 api milvus etcd minio
```

停止服務但保留本機資料 Volume：

```powershell
docker compose down
```

Compose 僅將前端 `3000` 與 API `8000` 映射到主機；Milvus `19530`、健康檢查 `9091` 和 MinIO `9000`／`9001` 僅在 Compose 內部網路提供，避免不必要的主機埠占用與對外暴露。Compose 中的 MinIO 帳密僅供本機開發使用；部署至共用或正式環境前必須更換。執行 `docker compose down` 後，具名 Volume 仍會保留 Milvus、etcd 與 MinIO 資料。

## 分階段實作

| 階段 | 範圍 | 狀態 |
|---|---|---|
| 0 | 初版專案紀錄、Compose 服務、Ollama 指引、FastAPI 骨架 | 已實作；手動驗證通過 |
| 1.1 | Milvus 存取模組與 Collection 初始化腳本 | 已實作；手動驗證通過 |
| 1.2 | MarkItDown／Qwen 解析與大型文件切片 | 已實作；手動驗證通過 |
| 1.3 | Embedding 寫入與向量／混合檢索 API | 已實作；手動驗證通過 |
| 2.1 | Python Skill 註冊與測試 Skill | 已實作；使用者手動驗證通過 |
| 2.2 | ReAct／Function Calling Agent 執行流程 | 已實作；使用者手動驗證通過 |
| 3 | SSE 聊天 API 與 Ollama／OpenAI 相容外部模型動態路由 | 已實作；使用者手動驗證通過 |
| 4.1 | Next.js 太空艙 Dashboard 與 Glassmorphism 主題 | 已實作；使用者手動驗證通過 |
| 4.2 | 本機帳號使用者隔離、SQLite 對話歷史、SSE 聊天、附件上傳與前端整合 | 已實作及自動驗證；待使用者手動驗證 |

## 測試矩陣

| 驗證項目 | 指令／步驟 | 預期結果 | 狀態 |
|---|---|---|---|
| Compose 設定檢查 | `docker compose config` | Compose 設定可正常解析 | 通過（使用者回報） |
| Docker 服務健康狀態 | `docker compose up --build -d`，接著執行 `docker compose ps` | API 與 Milvus 顯示 healthy；etcd 與 MinIO 正在執行 | 通過（使用者回報） |
| FastAPI 健康端點 | `curl.exe -i http://localhost:8000/health` | HTTP 200 且回傳 `{"status":"ok"}` | 通過（使用者回報） |
| Ollama 模型／API | 執行 `ollama list`，再執行上方 `/api/generate` 指令 | 清單中有 `qwen2.5vl:3b`，且生成 API 回傳內容 | 通過（使用者回報） |
| Swagger UI | 開啟 `http://localhost:8000/docs`，展開 `GET /health`，按 **Try it out** → **Execute** | HTTP 200 且回傳 `{"status":"ok"}` | 通過（使用者回報） |
| Milvus Collection 初始化 | `docker compose exec api python -m app.scripts.init_milvus`（連續執行兩次） | 第一次建立或確認 Collection；後續回報已存在；維度為 768 | 通過（助理整合測試及使用者手動確認） |
| 後端單元測試 | 從專案根目錄執行 `Push-Location backend; ..\.venv\Scripts\python.exe -m unittest discover -s tests -v; Pop-Location` | 37 項測試通過 | 通過（助理執行） |
| API Docker 映像建置 | `docker compose build api` | Python 3.12 映像安裝文件解析與 OCR 相依套件成功 | 通過（助理執行） |
| PDF／圖片解析整合測試 | Docker API 容器解析含文字與圖片的 PDF，並解析獨立 PNG | PDF 文字、頁碼中繼資料及 Qwen OCR／圖片描述均成功 | 通過（助理執行及使用者手動確認） |
| 文件解析與語意切片 | `Push-Location backend; ..\.venv\Scripts\python.exe -m app.scripts.parse_document <文件路徑>; Pop-Location` | 輸出文件內容及附有來源／頁碼中繼資料的 chunks；視覺內容由 Qwen 描述 | 通過（助理執行及使用者手動確認） |
| 文件上傳與向量檢索 API | 以 `curl.exe` 上傳 PDF／圖片，再使用回傳 `document_id` 呼叫 `/api/search` | 回傳 chunks 計數；搜尋結果包含內容、分數及來源中繼資料 | 通過（助理整合測試及使用者手動確認） |
| Skill CLI 範例 | `Push-Location backend; ..\.venv\Scripts\python.exe -m app.scripts.test_skill; Pop-Location` | `text_stats` 成功輸出字元、詞數與行數 JSON | 通過（助理執行） |
| Skills 清單 API | `curl.exe --fail --silent --show-error http://localhost:8000/api/skills`，或在 Swagger UI 執行 `GET /api/skills` | 回傳已註冊 Skill 名稱、描述與 Pydantic 參數 JSON Schema | 通過（助理整合測試及使用者手動確認） |
| Skill Registry 單元測試 | 執行後端單元測試命令 | 驗證同步／非同步呼叫、JSON Schema、重複／無效名稱、無效參數及未知 Skill | 通過（助理執行及使用者手動確認） |
| Agent ReAct／Skill 呼叫流程 | `POST /api/agent/run` 傳入要求使用 `text_stats` 的 prompt | 模型產生合法 ReAct 決策、執行 Skill，回傳答案及呼叫 arguments/result | 通過（助理整合測試及使用者手動確認） |
| Agent 決策協定與停止條件 | 執行後端單元測試命令 | 無效決策明確失敗；超出 Skill 呼叫上限即停止 | 通過（助理執行） |
| SSE 與 Token 使用量 | `curl.exe -N -X POST http://localhost:8000/api/chat/stream`，使用 Ollama 預設模型 | 收到 `meta`、增量 `token` 及含 Token 使用量的 `done` 事件 | 通過（助理測試及使用者手動確認） |
| 模型目錄與路由驗證 | `GET /api/models`；用 `provider`／`model` 呼叫聊天端點 | 回傳已設定模型；未允許的模型收到 422，未設定外部 API key 收到 503 | 通過（助理測試及使用者手動確認） |
| 前端 ESLint | `docker compose exec frontend npm run lint` | ESLint 無錯誤 | 通過（助理執行） |
| 前端 production build | `docker compose run --rm --no-deps frontend npm run build` | Next.js 靜態首頁建置成功且 TypeScript 檢查通過 | 通過（助理執行） |
| 前端 production dependencies audit | `docker compose run --rm --no-deps frontend npm audit --omit=dev` | Production dependencies 無已知漏洞 | 通過（助理執行；0 vulnerabilities；dev-only audit 另有 5 項 high，未執行會降級 Next ESLint 設定的 force 修復） |
| Dashboard Docker／HTTP | `docker compose up --build -d frontend`、`docker compose ps frontend`、`curl.exe -I http://localhost:3000` | 前端容器執行中，首頁 HTTP 200 | 通過（助理執行及瀏覽器確認） |
| Dashboard 桌面互動 | 瀏覽器以桌面尺寸開啟 `http://localhost:3000`，切換 Knowledge／Agent log | 三欄版面顯示、文件高度內捲動、全頁高度等於 viewport，面板可切換 | 通過（助理瀏覽器驗證）；待使用者手動確認 |
| Dashboard 行動版導覽 | 瀏覽器調整至 390×844，使用導覽按鈕並點擊側欄外區域 | 側欄初始收合、按鈕可開啟、點擊遮罩可關閉，右側面板隱藏 | 通過（助理瀏覽器驗證）；待使用者手動確認 |
| Phase 4.1 使用者手動驗證 | 使用者確認桌面三欄、Knowledge／Agent log、行動版側欄及預覽資料標示 | Phase 4.1 UI 檢查項目完成 | 通過（使用者確認） |
| Phase 4.2 後端單元測試 | `Push-Location backend; ..\.venv\Scripts\python.exe -m unittest discover -s tests -v; Pop-Location` | 驗證本機帳號註冊／登入／登出、密碼雜湊、登入保護及跨使用者資料隔離 | 通過（助理執行） |
| Phase 4.2 Milvus owner filter 整合 | 建立隨機命名的暫存 Collection；兩位 owner 寫入同向量後分別 hybrid search，結束時 drop 該 Collection | JSON `metadata["owner_id"]` filter 各自只回傳本 owner 的一筆結果；暫存 Collection 已清理 | 通過（Milvus 2.5.10 實測） |
| Phase 4.2 前端檢查 | `docker compose exec -T frontend npm run lint`、`npm run build`、`npm audit --omit=dev` | ESLint／TypeScript／Next.js production build 通過；production audit 0 vulnerabilities | 通過（助理執行） |
| Phase 4.2 Compose／Docker smoke test | `docker compose config --quiet`、`docker compose build api frontend`、`docker compose up -d api frontend`、`docker compose ps api frontend` | 設定與映像建置成功；API healthy，前端執行中 | 通過（助理執行） |
| Phase 4.2 公開／保護端點 | `POST /api/auth/register`、`POST /api/auth/login`、`GET /api/auth/me`、`POST /api/auth/logout`、未登入 `GET /api/conversations` | 註冊／登入建立 session、登出清除 session、未登入 conversations 回 401 | 通過（助理執行） |
| Phase 4.2 本機帳號登入畫面 | 瀏覽器開啟 `http://localhost:3000` | 顯示註冊／登入表單；成功登入後載入工作區，未登入不顯示資料 | 待使用者手動驗證 |
| 繁體中文介面 | `docker compose exec -T frontend npm run lint`、`npm run build`；瀏覽器開啟 `http://localhost:3000` | ESLint/build 通過；頁面語系為 `zh-Hant`，登入畫面、導覽與主要工作區文案使用繁體中文 | 通過（助理執行與瀏覽器驗證；使用者確認符合期待） |
| Phase 4.2 本機帳號註冊／登入／登出 | 瀏覽器建立帳號、登出後以相同 email／密碼登入，再登出 | 建立 HttpOnly session；登出後回到登入表單 | 自動測試通過；待使用者手動驗證 |
| Phase 4.2 歷史／聊天／附件／Agent | 登入後建立多個對話、傳送 SSE prompt、上傳文件、切換 Agent 並觸發 `text_stats`，重新載入並切換歷史 | Token 即時顯示；訊息、usage、附件、Skill logs 持久化；歷史與文件脈絡可載入 | 待使用者手動驗證 |
| Phase 4.2 使用者隔離端到端 | 以兩個不同 email 註冊，第二位嘗試打開第一位對話 ID、文件清單及搜尋第一位內容 | 跨使用者對話／文件不可見；對話 ID 回 404；文件搜尋不回傳其他 owner 資料 | 待使用者手動驗證 |

### Phase 0 手動驗證步驟

1. 確認 Docker Desktop 正在執行。依照上方指令啟動 Ollama 並下載 `qwen2.5vl:3b`。
2. 在專案根目錄執行 `docker compose config`。
3. 執行 `docker compose up --build -d`，接著執行 `docker compose ps`；若服務未達健康狀態，查看服務紀錄。
4. 執行 `curl.exe -i http://localhost:8000/health`，或前往 `http://localhost:8000/docs` 使用 Swagger UI 測試 `GET /health`。
5. 執行 Ollama API 測試。若主機端測試失敗，先確認 Ollama 已啟動且模型已下載。主機到容器的 Ollama 連線是另一項檢查；Phase 0 的 `/health` 不會呼叫 Ollama。

手動測試後，依實際結果更新此處狀態。不得只因檔案已產生就將測試標記為通過。

### Phase 1.1 手動驗證步驟

1. 確認 Docker Compose 中的 Milvus 服務已健康啟動。
2. 在專案根目錄執行 `docker compose up --build -d api`，讓 API 映像安裝新增的 `pymilvus` 依賴。
3. 執行 `docker compose exec api python -m app.scripts.init_milvus`；預期輸出指出 `knowledge_chunks` 已建立（或已存在）且向量維度為 768。
4. 再執行一次初始化命令，確認可重複執行而不會建立重複 Collection。
5. 執行 `docker compose exec api python -c "from pymilvus import MilvusClient; c=MilvusClient(uri='http://milvus:19530'); print(c.list_indexes('knowledge_chunks')); c.close()"`；預期索引清單包含 `embedding` 與 `sparse_embedding`。
6. 執行 `curl.exe -i http://localhost:8000/health`；預期為 HTTP 200 與 `{"status":"ok"}`。
7. 若需檢視服務紀錄，執行 `docker compose logs --tail 100 api milvus`。

### Phase 1.2 手動驗證步驟

1. 確認 Ollama 正在執行，且 `ollama list` 中有 `qwen2.5vl:3b`。
2. 從專案根目錄執行 `Push-Location backend; ..\.venv\Scripts\python.exe -m app.scripts.parse_document "C:\path\to\sample.pdf"; Pop-Location`，將路徑換成一份含可擷取文字的 PDF。
3. 以同一指令測試一張有文字或圖表的 PNG/JPG，檢查 chunk 文字、頁碼／來源中繼資料及視覺描述。
4. 測試超過 `CHUNK_MAX_CHARS` 的文件；各 chunk 應不超過設定上限，單一超長段落切分時保留 overlap。
5. 確認無法連線至 Ollama 或視覺模型請求失敗時，命令列會顯示錯誤，而非回報成功。

### Phase 1.3 手動驗證步驟

1. 確認 Docker Desktop、Milvus、Ollama 及 `nomic-embed-text` Embedding 模型正在執行／可用。
2. 執行 `curl.exe -i -X POST http://localhost:8000/api/documents -F "file=@C:\path\to\sample.pdf"`；預期回傳 `document_id`、安全化來源名稱與已索引 chunk 數。
3. 在 `http://localhost:8000/docs` 展開 `POST /api/search`，按 **Try it out**；輸入文件中的主題、`top_k: 5` 及上一步回傳的 `document_id`，再按 **Execute**。
4. 或在 PowerShell 將 `<document-id>` 換成實際 UUID，使用檔案傳遞 JSON，避免 PowerShell 對 curl 引號的解析差異：

   ```powershell
   $body = '{"query":"文件中的一個關鍵主題","top_k":5,"document_id":"<document-id>"}'
   $bodyPath = Join-Path $env:TEMP "nexux-search.json"
   Set-Content -Path $bodyPath -Value $body -NoNewline -Encoding ascii
   curl.exe -i -X POST http://localhost:8000/api/search -H "Content-Type: application/json" --data-binary "@$bodyPath"
   Remove-Item -LiteralPath $bodyPath
   ```

5. 確認搜尋結果包含相關文字、分數及來源／頁碼中繼資料；不提供 `document_id` 時應可搜尋整個 Collection。
6. 測試不支援的副檔名及超過 100 MiB 的檔案，預期分別收到明確的 415 與 413 錯誤。

### Phase 2.1 手動驗證步驟

1. 從專案根目錄執行 `Push-Location backend; ..\.venv\Scripts\python.exe -m app.scripts.test_skill; Pop-Location`；預期輸出 `text_stats` 的 JSON 統計結果。
2. 確認 Docker API 已重建並啟動；執行 `docker compose up --build -d api`，再用 `curl.exe --fail --silent --show-error http://localhost:8000/api/skills` 檢查回應。
3. 或開啟 `http://localhost:8000/docs`，執行 `GET /api/skills`；確認列出 `text_stats`、描述及參數 JSON Schema。
4. 執行後端單元測試：`Push-Location backend; ..\.venv\Scripts\python.exe -m unittest discover -s tests -v; Pop-Location`；應有 23 項通過，並涵蓋重複／無效名稱、未知 Skill 及不符合 Pydantic Schema 的參數。
5. 回報 CLI、API 與測試結果；Phase 2.1 確認通過後才開始 Phase 2.2 Agent 派送流程。

### Phase 2.2 手動驗證步驟

1. 確認 Ollama 正在執行且 `ollama list` 中有 `qwen2.5vl:3b`，再於專案根目錄執行 `docker compose up --build -d api`。
2. 開啟 `http://localhost:8000/docs`，展開 `POST /api/agent/run`，按 **Try it out**，輸入以下 JSON 後按 **Execute**：

   ```json
   {
     "prompt": "You must call the text_stats skill on exactly this text: alpha beta gamma. Then explain the returned character, word, and line counts."
   }
   ```

3. 預期回應包含答案及一筆 `tool_calls`，其 `skill_name` 為 `text_stats`、`arguments.text` 為 `alpha beta gamma`、`result` 為 `{"characters":16,"words":3,"lines":1}`。
4. 或在 PowerShell 使用暫存 JSON 檔避免命令列引號問題：

   ```powershell
   $bodyPath = Join-Path $env:TEMP "nexux-agent-request.json"
   Set-Content -Path $bodyPath -Value '{"prompt":"You must call the text_stats skill on exactly this text: alpha beta gamma. Then explain the returned character, word, and line counts."}' -NoNewline -Encoding ascii
   try {
       curl.exe -i -X POST http://localhost:8000/api/agent/run -H "Content-Type: application/json" --data-binary "@$bodyPath"
   } finally {
       Remove-Item -LiteralPath $bodyPath
   }
   ```

5. 執行後端單元測試命令，預期 29 項通過；確認 Agent 輸入驗證、模型決策 Schema、Skill observation 與呼叫上限測試皆通過。
6. 回報 Swagger／curl 與測試結果；Phase 2.2 確認通過後才進入 Phase 3。

### Phase 3 手動驗證步驟

1. 確認 Ollama 執行且 `ollama list` 有 `qwen2.5vl:3b`，再執行 `docker compose up --build -d api`。
2. 執行 `curl.exe http://localhost:8000/api/models`；確認預設 provider/model 為 `ollama`／`qwen2.5vl:3b`，且未提供外部 API key 時 OpenAI 相容模型顯示 `configured: false`。
3. 以 `http://localhost:8000/docs` 查看 `POST /api/chat/stream` 合約；實際觀察 SSE 請使用 PowerShell 暫存 JSON 檔及 `curl.exe -N`：

   ```powershell
   $bodyPath = Join-Path $env:TEMP "nexux-chat-stream.json"
   Set-Content -Path $bodyPath -Value '{"prompt":"Reply in one short sentence: streaming works."}' -NoNewline -Encoding ascii
   try {
       curl.exe -N -X POST http://localhost:8000/api/chat/stream -H "Content-Type: application/json" --data-binary "@$bodyPath"
   } finally {
       Remove-Item -LiteralPath $bodyPath
   }
   ```

4. 確認依序收到 `meta`、多筆即時 `token` 與 `done`；`done.usage` 應有 prompt/completion/total Token 數及 `source`。
5. 將 request 的 `provider` 設為 `ollama`、`model` 設為 `/api/models` 所列模型，確認路由成功；若使用未設定模型，應回 HTTP 422。
6. 若要測外部路由，在本機 `.env` 或啟動 Docker Compose 的 PowerShell session 設定 `OPENAI_API_KEY`，必要時設定 `OPENAI_BASE_URL`、`OPENAI_CHAT_MODELS`，重新建立 API 容器後以 `provider: "openai_compatible"` 和已設定 model 測試。不要把金鑰貼入對話或提交至版本控制；未設定金鑰時選外部 provider 預期回 HTTP 503。
7. 執行後端單元測試命令，預期 37 項通過；回報結果後才進入 Phase 4。

### Phase 4.1 手動驗證步驟

1. 確認 Docker Desktop 正在執行，於專案根目錄啟動前端：`docker compose up --build -d frontend`；以 `docker compose ps frontend` 確認容器執行中。
2. 執行 `curl.exe -I http://localhost:3000`，預期首頁回 HTTP 200；再於瀏覽器開啟 `http://localhost:3000`。
3. 桌面尺寸確認左側導覽、中間工作區及右側 Workspace 面板皆能顯示；文件／集合清單可在面板內捲動，切換 **Knowledge** 與 **Agent log** 時右側內容應改變。
4. 將瀏覽器縮至行動尺寸（例如 390×844），確認左側導覽預設收合；按主區域導覽按鈕開啟，再點擊側欄外的遮罩區關閉。此尺寸下右側面板預期隱藏，主要工作區可正常垂直瀏覽。
5. 確認 UI 有標示 **INTERFACE PREVIEW**、**SAMPLE LIBRARY** 與 **SAMPLE COLLECTIONS**；對話、附件上傳及歷史資料尚未串接 API，這些功能留待 Phase 4.2。
6. 回報以上項目是否通過；收到使用者確認前不開始 Phase 4.2。

### Phase 4.2 手動驗證步驟（目前 checkpoint）

#### A. 設定並驗證本機帳號

1. 在專案根目錄建立本機環境檔：`Copy-Item .env.example .env`。本機測試不需要 OIDC／IdP 設定。
2. 產生 session 簽署密鑰並只保存在本機 `.env`（不要貼到對話、截圖或提交）：
   ```powershell
   $bytes = New-Object byte[] 48
   $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
   $rng.GetBytes($bytes)
   [Convert]::ToBase64String($bytes)
   $rng.Dispose()
   ```
   將輸出填入 `SESSION_SECRET`。本機 HTTP 開發使用 `COOKIE_SECURE=false`；HTTPS 部署必須改成 `COOKIE_SECURE=true`。
3. 執行 `docker compose config --quiet`，再執行 `docker compose up --build -d api frontend` 和 `docker compose ps api frontend`；預期 API healthy、前端執行中。
4. 瀏覽器開啟 `http://localhost:3000`，選擇註冊並建立帳號；預期成功後載入 Dashboard。
5. 按 **Sign out**，用相同 email／密碼登入，再次確認登出會返回帳號登入表單。

#### B. 驗證未登入保護與 Swagger

1. 在未登入的私密視窗或登出後執行 `curl.exe -i http://localhost:8000/api/conversations`；預期 HTTP 401 與 `Authentication is required`。
2. 登入後，在同一瀏覽器開啟 `http://localhost:8000/docs`。用 **Try it out** 測試 `GET /api/auth/me`、`GET /api/models`、`GET /api/skills`；預期回傳目前帳號、已設定模型及 `text_stats` Skill。
3. 登入後用 Swagger 建立對話（`POST /api/conversations`，body 可為 `{}`），記下回傳的 conversation ID；也可在 Dashboard 按 **New session** 建立。

#### C. 驗證歷史、SSE 聊天、文件與 Agent

1. 在 Dashboard 選擇已設定模型，送出「請用一句話說明串流回覆正常。」；確認文字逐步出現，完成後有 Token usage。
2. 重新載入瀏覽器、再選取該 session；確認使用者／助理訊息和 usage 仍存在。建立另一個 session 後切回舊 session，確認內容互不混用。
3. 在 Knowledge 面板上傳一份含明確事實的 `.txt`、PDF 或圖片；確認文件清單顯示檔名。於聊天提問該文件中的事實，確認回答可參照文件內容。
4. 切換 **Agent** 模式並送出「請使用 text_stats 技能統計以下文字的字元、單字與行數：NexuX agent skill verification.」；確認 Agent log 顯示 tool call/result，答案出現在對話中。
5. 重新載入頁面並選回 Agent 對話；確認 Agent 回合及 tool log 可從持久化歷史還原。

#### D. 驗證使用者隔離及登出

1. 使用第一個帳號建立一個對話並上傳一份可辨識文件；在 `http://localhost:8000/docs` 的 `POST /api/conversations`／`POST /api/documents` response 記下 ID（Swagger 與 Dashboard 共用 localhost session）。
2. Dashboard 執行 **Sign out**，註冊並登入不同 email 的第二個帳號；預期對話清單及文件清單不會顯示第一個帳號的資料。
3. 以第二個帳號在 Swagger 對 `GET /api/conversations/{第一位的ID}` 按 **Try it out**；預期 HTTP 404。呼叫 `POST /api/search` 搜尋第一位文件的唯一字串，預期不含第一位文件內容。
4. 確認第二位使用者只能看到／載入自己的 session，再按 **Sign out**；預期返回登入畫面。
5. 以上完成後請回覆 Phase 4.2 手動檢查結果。未收到確認前不開始下一階段；如有失敗，請附上端點、HTTP 狀態及已遮蔽敏感值的錯誤訊息（不要提供 cookie、client secret 或 session secret）。

## 更新紀錄

- 2026-10-03：建立初版系統架構、API／Skills 路線圖、本機服務指令、Phase 0 測試矩陣、Docker Compose 基礎設定及 FastAPI 健康端點。
- 2026-10-03：將紀錄改為繁體中文，記錄未來 Python 建置前先詢問是否使用專案 `.venv`。
- 2026-10-03：使用者回報 Phase 0 所有手動驗證項目通過，已更新 Testing Matrix。
- 2026-10-03：使用者選定 `nomic-embed-text`（768 維）及既有 Python 3.11.6 `.venv`；開始 Phase 1.1。
- 2026-10-03：完成 Milvus Store 與冪等 Collection 初始化；建立 HNSW/COSINE 及 BM25 索引。4 項單元測試及 Docker/Milvus 重複初始化整合測試通過。
- 2026-10-03：使用者手動確認 Phase 1.1 驗證通過；開始 Phase 1.2 文件解析與切片。
- 2026-10-03：Phase 1.2 採用 MarkItDown OCR plugin 與 Ollama OpenAI 相容介面處理視覺內容；PDF 逐頁轉換，並依標題、段落及圖片 OCR 邊界動態切片。
- 2026-10-03：完成文件解析 CLI 與 chunker；7 項單元測試、Python 3.11 `.venv` 解析、Python 3.12 Docker 建置，以及容器內 PDF OCR／獨立圖片視覺解析整合測試通過。
- 2026-10-03：使用者手動確認 Phase 1.2 驗證通過；開始 Phase 1.3 Embedding 寫入與檢索 API。
- 2026-10-03：使用者選定文件上傳預設上限 100 MiB；上限將由環境變數調整。
- 2026-10-03：完成文件上傳／Embedding 寫入、Milvus HNSW＋BM25 混合檢索 API；Nomic Embedding 及即時搜尋容器整合測試通過，等待使用者手動驗證。
- 2026-10-03：使用者手動確認 Phase 1.3 驗證通過；開始 Phase 2.1 Skill 註冊系統。
- 2026-10-03：使用者確認 Phase 2.1 沿用現有 Python 3.11.6 `.venv`。
- Phase 2.1：完成 Pydantic 驗證 Skill Registry、同步／非同步呼叫、Function Calling Schema、`text_stats` CLI 範例與 `GET /api/skills`；23 項後端單元測試、CLI、API Docker 重建及端點測試通過。
- 使用者確認 Phase 2.1 手動驗證通過，並同意開始 Phase 2.2；確認沿用既有 `.venv`。
- Phase 2.2：依本機 Ollama 能力選擇受 JSON Schema 約束的自訂 ReAct 決策格式，以 `qwen2.5vl:3b` 派送已註冊 Skills；新增 `POST /api/agent/run`、可設定的模型／呼叫上限與執行紀錄。
- Phase 2.2：29 項後端單元測試、Compose 設定、Python 3.12 API Docker 建置及真實 Ollama＋Docker `text_stats` 端對端呼叫通過。
- 使用者確認 Phase 2.2 手動驗證通過，並同意開始 Phase 3；確認沿用既有 `.venv`，選擇 OpenAI 相容外部 API 路由。
- Phase 3：新增 `ChatModelRouter`、`GET /api/models`、`POST /api/chat/stream` SSE（meta/token/done/error）及 provider usage／估算 Token 計數；外部 API credentials 僅透過環境變數設定。
- Phase 3：37 項後端單元測試、Compose 設定、Python 3.12 API Docker 建置、Ollama SSE 即時 Token／usage 端對端測試及模型目錄／錯誤路由測試通過。
- 使用者確認 Phase 3 手動驗證通過，並同意開始 Phase 4；沿用 `.venv` 偏好不適用於本階段前端工作。
- Phase 4.1：盤點確認目前工作區尚無 Next.js／前端檔案；開始建立 App Router 與 Dashboard 介面。
- Phase 4.1：以 Docker Node 22 建立 Next.js 16 App Router、Tailwind CSS、Zustand 三欄式 Dashboard；新增前端 Dockerfile、Compose service 及執行說明。對話、上傳與歷史資料 API 整合保留至 Phase 4.2。
- Phase 4.1：調整桌面 viewport 版面及面板內捲動，加入可響應視窗尺寸變更的行動版導覽收合；預覽文件／集合資料明確標示為 sample。前端 ESLint、production build、production dependency audit（0 vulnerabilities）、Docker HTTP 200 及瀏覽器桌面／行動互動檢查通過。
- Phase 4.1 當時：UI 初版採英文，文件語言標記為 `en`。Dev dependency audit 仍回報 5 個 high severity 傳遞相依；未執行可能降級 Next ESLint 設定的 force 修復。使用者其後已完成手動驗證。
- 使用者完成 Phase 4.1 桌面／行動版手動檢查並確認通過，同意開始 Phase 4.2。
- Phase 4.2 設計選擇：對話由後端保存於 SQLite 命名 Volume；登入採通用 OIDC，啟用每位使用者的對話與知識文件隔離。Client secret 透過本機環境變數設定，不在對話中傳送；目前沒有指定 IdP，實作以 OIDC discovery 設定為準。
- Phase 4.2：完成 Authlib OIDC discovery／登入 callback、HttpOnly session、SQLite users/conversations/messages/documents、owner-scoped API、Milvus JSON owner filter、聊天／Agent 歷史與 RAG 脈絡、SSE 持久化及前端工作區串接；新增未登入／跨使用者隔離及 OIDC 設定測試。
- Phase 4.2：50 項後端測試通過（含文件上傳回應 `uploaded_at` 及 Milvus owner metadata 驗證）；Milvus 2.5.10 暫存 Collection 實測兩位 owner 的 hybrid search filter 各自僅回傳本人的資料，測後已刪除 Collection。前端 ESLint、TypeScript／production build、production npm audit（0 vulnerabilities）通過；API／前端映像建置、Compose 啟動、API healthy、health/auth config/unauthenticated 401 與首頁 HTTP 200 通過。
- Phase 4.2：瀏覽器確認未設定 OIDC 時顯示設定提示。由於尚未提供 IdP issuer／client 設定，真實 SSO 登入、登入後 UI 工作流程及雙帳號手動隔離仍待使用者依 Verification Checkpoint 執行；舊有無 owner metadata 文件需重新上傳。
- Phase 4.2 手動 checkpoint：使用者回報登入時 `OIDC is not configured`；Testing Matrix 維持阻塞，待使用者僅於本機 `.env` 填入 IdP 設定後重啟 API 再驗證。
- 2026-10-03：依使用者要求將 Dashboard、登入頁、導覽、對話、文件庫、Agent 記錄與輔助文字本地化為繁體中文，並設定文件語系 `zh-Hant`。
- 繁體中文介面驗證：前端 ESLint、Next.js production build／TypeScript 檢查通過；重新啟動前端容器後，瀏覽器確認頁面標題、登入頁文案及 OIDC 未設定提示皆以繁體中文呈現。
- 使用者確認繁體中文介面呈現符合期待。
- 2026-10-04：依使用者要求以本機 email／密碼註冊登入取代目前使用的 OIDC 登入流程；保留 HttpOnly session、登出及使用者資料隔離，不再需要設定 IdP。密碼以 PBKDF2-HMAC-SHA256 雜湊，舊 users 資料表會自動新增 password_hash 欄位。
- 本機帳號註冊／登入／登出、錯誤憑證、重複 email、來源 Origin 限制及舊資料表遷移均加入測試；後端完整測試 52 項通過。前端 ESLint 與 Next.js production build／TypeScript 檢查通過（Docker Compose）。
- 過往 OIDC 實作紀錄保留作為歷史；目前有效 API 與前端登入入口已改成本機帳號流程。既有 OIDC 身份不會自動綁定本機帳號，以免未驗證 email 導致帳號接管；同 email 註冊會建立獨立使用者。此簡易帳號功能不含電子郵件驗證、密碼重設或登入節流。
