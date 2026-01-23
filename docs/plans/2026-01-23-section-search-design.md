# 版區搜尋與管理功能設計

## 概述

新增兩個主要功能：
1. **版區搜尋下載** - 在指定版區中搜尋關鍵字，勾選帖子批次下載
2. **版區自動更新與管理** - 自動爬取論壇版面結構，支援啟用/停用、個性化分類

## 資料結構

### 資料庫表格 `forum_sections`

```sql
CREATE TABLE forum_sections (
    id INTEGER PRIMARY KEY,
    fid TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    parent_fid TEXT,
    level INTEGER DEFAULT 0,
    post_count INTEGER,
    last_updated DATETIME,
    FOREIGN KEY (parent_fid) REFERENCES forum_sections(fid)
);
```

### 資料庫表格 `search_results`

```sql
CREATE TABLE search_results (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    tid TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT,
    post_date TEXT,
    fid TEXT,
    forum_name TEXT,
    post_url TEXT,
    selected BOOLEAN DEFAULT FALSE,
    processed BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 設定檔結構 (config.yaml)

```yaml
forum:
  section_settings:
    '77':
      enabled: true
      category: '我的最愛'
  categories:
    - '我的最愛'
    - '常用'
    - '其他'
```

## 新增檔案

- `src/crawler/forum_structure_scraper.py` - 版區結構爬取
- `src/crawler/forum_searcher.py` - 帖子搜尋器
- `src/gui/section_search_widget.py` - 版區搜尋分頁
- `src/gui/section_manager_widget.py` - 版區管理分頁
- `src/gui/search_download_worker.py` - 搜尋下載執行緒

## 修改檔案

- `src/database/db_manager.py` - 新增表格及方法
- `src/gui/main_window.py` - 新增分頁
- `config/config.yaml` - 新增設定結構

## 設計決策

1. **論壇結構**：支援三層或更深的巢狀結構
2. **搜尋方式**：混合模式（優先論壇搜尋 API，失敗則本地篩選）
3. **下載流程**：獨立於主爬蟲，搜尋結果單獨表格，勾選後批次執行
4. **儲存方式**：版區結構存資料庫（共用），啟用/分類設定存設定檔
5. **個性化分類**：純粹視覺分組，不影響爬取行為
