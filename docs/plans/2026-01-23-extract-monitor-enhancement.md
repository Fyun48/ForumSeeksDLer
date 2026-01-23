# 解壓縮監控增強設計文件

**日期**: 2026-01-23
**狀態**: 已確認，準備實作

---

## 1. 功能總覽

| 功能 | 說明 |
|------|------|
| **巢狀解壓** | 自動處理壓縮檔內的壓縮檔，可設定最大層數（預設 3 層） |
| **重複檔案處理** | 依檔案大小判斷：相同大小跳過，不同大小則重新命名 |
| **排除副檔名** | 預設排除 `.txt`, `.nfo`, `.url`, `.htm`, `.html`, `.lnk`，可自訂增刪 |
| **永久刪除** | 解壓成功後直接永久刪除原始壓縮檔，不經資源回收桶 |
| **智慧資料夾結構** | 根據壓縮檔內容決定是否建立外層資料夾 |

### 智慧資料夾結構邏輯

- 壓縮檔根目錄是單一資料夾 → 直接解壓，不加外層
- 壓縮檔根目錄是散落檔案 → 排除過濾副檔名後：
  - 只剩 1 個檔案 → 不建外層資料夾
  - 2 個以上檔案 → 建立以壓縮檔名命名的資料夾

---

## 2. 設定檔結構

在 `config.yaml` 中新增：

```yaml
extract:
  # 巢狀解壓設定
  nested:
    enabled: true
    max_depth: 3

  # 重複檔案處理
  duplicate:
    mode: "smart"  # smart = 依大小判斷

  # 排除副檔名
  exclude_extensions:
    - ".txt"
    - ".nfo"
    - ".url"
    - ".htm"
    - ".html"
    - ".lnk"

  # 刪除設定
  delete:
    enabled: true
    permanent: true

  # 智慧資料夾結構
  smart_folder:
    enabled: true
    min_files_for_folder: 2
```

---

## 3. 資料庫欄位擴充

在 `downloads` 表新增欄位：

| 欄位名稱 | 類型 | 說明 |
|---------|------|------|
| `extract_dest_path` | TEXT | 解壓目的地路徑 |
| `files_extracted` | INTEGER | 實際解壓的檔案數量（過濾後） |
| `files_skipped` | INTEGER | 因重複而跳過的檔案數量 |
| `files_filtered` | INTEGER | 因副檔名過濾而排除的檔案數量 |
| `archive_size` | INTEGER | 原始壓縮檔大小 (bytes) |
| `extracted_size` | INTEGER | 解壓後總檔案大小 (bytes) |
| `nested_level` | INTEGER | 巢狀層級（0=原始，1=第一層巢狀...） |
| `parent_download_id` | INTEGER | 巢狀壓縮檔的父層 download_id |

---

## 4. 處理流程

```
監控目錄發現壓縮檔
        │
        ▼
   嘗試解壓 (使用密碼清單)
        │
        ▼
   解壓成功？ ──否──→ 標記失敗，等待下次重試
        │
       是
        ▼
   過濾階段：移除排除副檔名的檔案
        │
        ▼
   智慧資料夾判斷
        │
        ▼
   重複檔案處理：比對大小，決定跳過或重新命名
        │
        ▼
   搬移檔案到目的地
        │
        ▼
   巢狀解壓檢查：目的地有壓縮檔且層數 < 最大層數？→ 遞迴處理
        │
        ▼
   永久刪除原始壓縮檔
        │
        ▼
   記錄到資料庫
```

---

## 5. 核心類別設計

### ExtractMonitor 類別

```python
class ExtractMonitor:
    def __init__(self, config: dict, db: DatabaseManager)

    # 主要流程
    def process_archive(self, archive_path, nested_level=0, parent_id=None) -> ExtractResult

    # 分析階段
    def analyze_archive(self, archive_path) -> ArchiveInfo
    def should_create_folder(self, archive_info) -> tuple[bool, str]

    # 過濾階段
    def filter_entries(self, entries) -> FilterResult

    # 解壓階段
    def extract_archive(self, archive_path, dest_path, exclude_patterns) -> bool

    # 重複檔案處理
    def handle_duplicates(self, dest_path, extracted_files) -> DuplicateResult
    def get_unique_filename(self, file_path) -> Path

    # 巢狀處理
    def find_nested_archives(self, dest_path) -> List[Path]

    # 清理階段
    def delete_archive(self, archive_path) -> bool

    # 資料庫記錄
    def record_extraction(self, result) -> int
```

### 資料類別

```python
@dataclass
class ArchiveInfo:
    path: Path
    size: int
    root_is_single_folder: bool
    root_folder_name: str
    all_entries: List[str]
    file_count: int

@dataclass
class FilterResult:
    kept: List[str]
    excluded: List[str]

@dataclass
class DuplicateResult:
    processed: List[Path]
    skipped: List[Path]
    renamed: List[tuple]

@dataclass
class ExtractResult:
    success: bool
    archive_path: Path
    dest_path: Path
    archive_size: int
    extracted_size: int
    files_extracted: int
    files_skipped: int
    files_filtered: int
    nested_level: int
    parent_id: int
    error_message: str = None
```

---

## 6. GUI 設計

### 設定介面

在設定視窗新增「解壓縮設定」分頁，包含：
- 巢狀解壓開關與最大層數
- 重複檔案處理模式
- 刪除選項（永久/資源回收桶）
- 智慧資料夾開關與最小檔案數
- 排除副檔名清單管理

### 記錄顯示介面

採用「主列表 + 詳細面板」設計：
- 主列表顯示：檔案名稱、狀態、檔案數、時間、大小
- 巢狀壓縮檔以樹狀縮排顯示
- 選取項目後顯示詳細資訊面板

### 訊號定義

```python
class ExtractSignals(QObject):
    started = pyqtSignal(str, int)      # 開始處理
    progress = pyqtSignal(str, int)     # 進度更新
    file_extracted = pyqtSignal(str)    # 單檔完成
    finished = pyqtSignal(object)       # 解壓完成
    error = pyqtSignal(str, str)        # 發生錯誤
    nested_found = pyqtSignal(str, int) # 發現巢狀壓縮檔
    file_skipped = pyqtSignal(str, str) # 檔案被跳過
    stats_updated = pyqtSignal(dict)    # 統計更新
```

---

## 7. 錯誤處理

| 錯誤情境 | 處理方式 |
|---------|---------|
| 密碼錯誤 | 標記待重試，保留壓縮檔 |
| 壓縮檔損壞 | 標記失敗，保留供手動處理 |
| 磁碟空間不足 | 中止解壓，清理暫存，通知使用者 |
| 目的地路徑過長 | 自動縮短資料夾名稱 |
| 檔案被佔用 | 等待重試（最多 3 次） |
| 巢狀層數超限 | 停止遞迴，記錄已完成部分 |

---

## 8. 需要修改的檔案

```
src/
├── downloader/
│   └── extract_monitor.py    # 主要修改
├── database/
│   └── db_manager.py         # 新增欄位與方法
├── gui/
│   ├── main_window.py        # 整合訊號、狀態列
│   ├── settings_dialog.py    # 新增設定分頁
│   └── extract_history.py    # 新增：記錄顯示元件
└── models/
    └── extract_models.py     # 新增：資料類別

config/
└── config.yaml               # 新增 extract 區塊
```

---

## 9. 預設值

| 設定項 | 預設值 |
|-------|-------|
| 巢狀最大層數 | 3 |
| 建立資料夾最小檔案數 | 2 |
| 永久刪除 | 是 |
| 排除副檔名 | `.txt`, `.nfo`, `.url`, `.htm`, `.html`, `.lnk` |
