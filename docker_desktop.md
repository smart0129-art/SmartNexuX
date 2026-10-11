# Docker Desktop 跨電腦搬移與備份指南

Docker Desktop **無法直接將整個應用程式主體打包安裝到新電腦**。標準的做法是：
1. **在新電腦重新安裝 Docker Desktop 應用程式**。
2. **將舊電腦中的容器（Containers）、影像檔（Images）或資料（Volumes）匯出後，再搬移至新電腦匯入**。

以下提供三種常見的搬移與備份方法，請根據需求選擇最合適的方式。

---

## 方案一：備份特定容器與資料（最推薦、最穩定）

適用於只需要轉移特定幾組運作中的系統或服務。

### 1. 備份指定的容器 (Container)
將運行中的容器打包成新的 Image：
```bash
docker commit <容器名稱或ID> my-saved-container:v1
```

將該 Image 打包匯出成 `.tar` 歸檔檔案：
```bash
docker save -o my-saved-container.tar my-saved-container:v1
```

在新電腦載入該 Image：
```bash
docker load -i my-saved-container.tar
```

### 2. 備份資料卷 (Volume)
若系統資料（如資料庫）存在 Volume 中，可透過臨時容器將 Volume 打包：

* **Windows (CMD):**
  ```cmd
  docker run --rm -v <資料卷名稱>:/volume -v %cd%:/backup busybox tar cvf /backup/volume_data.tar /volume
  ```
* **Mac / Linux / PowerShell:**
  ```bash
  docker run --rm -v <資料卷名稱>:/volume -v $(pwd):/backup busybox tar cvf /backup/volume_data.tar /volume
  ```

---

## 方案二：一次打包所有 Docker 影像 (Images)

適用於舊電腦中有多個 Image，想一次性完整轉移到新電腦的情況。

### 1. 在舊電腦匯出所有 Image
```bash
docker save -o all_my_images.tar $(docker images -q)
```

### 2. 在新電腦匯入所有 Image
將 `all_my_images.tar` 複製到新電腦後執行：
```bash
docker load -i all_my_images.tar
```

---

## 方案三：Windows WSL2 全機環境完整搬移（僅限 Windows）

如果你在 Windows 上使用 Docker Desktop (WSL2 後端)，所有容器、影像與資料都儲存在 `docker-desktop-data` 虛擬磁碟中，可以直接匯出整個 WSL2 環境。

### 1. 在舊電腦匯出 Docker WSL2 資料
1. 完全關閉 Docker Desktop（從系統托盤退出）。
2. 開啟 CMD 或 PowerShell 執行：
   ```cmd
   wsl --export docker-desktop-data C:\docker-backup.tar
   ```

### 2. 在新電腦匯入 Docker WSL2 資料
1. 在新電腦安裝好 Docker Desktop 並先關閉它。
2. 開啟 CMD 或 PowerShell 執行：
   ```cmd
   wsl --unregister docker-desktop-data
   wsl --import docker-desktop-data %LOCALAPPDATA%\Docker\wsl\data C:\docker-backup.tar --version 2
   ```
3. 重新啟動 Docker Desktop，舊電腦的所有容器與影像將完整恢復。

---

## 💡 最佳實務建議 (Best Practices)

1. **優先使用 Dockerfile / Docker Compose**：
   如果環境是透過程式碼建置的，最乾淨的做法是將 `Dockerfile` 或 `docker-compose.yml` 複製到新電腦，執行 `docker compose up -d` 重新建立。
2. **獨立處理持久化資料**：
   僅針對資料庫或設定檔等持久化資料（Volumes）進行打包備份，能有效避免不同電腦間的系統環境衝突。