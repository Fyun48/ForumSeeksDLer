# Nord 深色主題設計

## 概述

為 ForumSeeksDLer GUI 設計完整的 Nord 深色主題，改善可讀性與視覺一致性。

- **配色方案**：Nord
- **主題類型**：深色 (Dark)
- **覆蓋範圍**：完整應用程式
- **切換功能**：不需要

## 色彩定義

### Nord Polar Night (背景色系)
| 變數 | 色碼 | 用途 |
|------|------|------|
| NORD0 | `#2E3440` | 最深 - 主背景 |
| NORD1 | `#3B4252` | 次深 - 卡片/面板背景 |
| NORD2 | `#434C5E` | 中間 - 懸停狀態 |
| NORD3 | `#4C566A` | 淺深 - 邊框/分隔線 |

### Nord Snow Storm (文字色系)
| 變數 | 色碼 | 用途 |
|------|------|------|
| NORD4 | `#D8DEE9` | 次要文字 |
| NORD5 | `#E5E9F0` | 一般文字 |
| NORD6 | `#ECEFF4` | 主要文字（最亮） |

### Nord Frost (強調色系)
| 變數 | 色碼 | 用途 |
|------|------|------|
| NORD7 | `#8FBCBB` | 青綠 - 連結/可點擊 |
| NORD8 | `#88C0D0` | 冰藍 - 主要強調 |
| NORD9 | `#81A1C1` | 灰藍 - 次要強調 |
| NORD10 | `#5E81AC` | 深藍 - 選中狀態 |

### Nord Aurora (語意色系)
| 變數 | 色碼 | 用途 |
|------|------|------|
| NORD11 | `#BF616A` | 紅 - 錯誤/危險 |
| NORD12 | `#D08770` | 橙 - 警告 |
| NORD13 | `#EBCB8B` | 黃 - 提醒 |
| NORD14 | `#A3BE8C` | 綠 - 成功 |
| NORD15 | `#B48EAD` | 紫 - 特殊標記 |

## 元件樣式

### 主視窗
- 背景：`NORD0`
- 預設文字：`NORD5`

### 按鈕
| 類型 | 背景 | 文字 | 用途 |
|------|------|------|------|
| Primary | `NORD10` | `NORD6` | 主要操作 |
| Danger | `NORD11` | `NORD6` | 危險操作（清空、刪除） |
| Subtle | `NORD2` | `NORD5` | 一般操作 |

- Hover 狀態：背景變亮一階
- 圓角：4px
- 內距：6px 16px

### 輸入元件
- 背景：`NORD1`（比主背景稍亮）
- 邊框：`NORD3`
- Focus 邊框：`NORD8`（冰藍）
- 選取高亮：`NORD10`

### 表格
- 背景：`NORD0`
- 交替行：`NORD1`
- 格線：`NORD2`
- 表頭背景：`NORD1`
- 表頭底線：`NORD3`（2px）
- 選中行：`NORD10`
- 懸停行：`NORD2`

### 表格語意顏色
| 狀態 | 顏色 | 用途 |
|------|------|------|
| 成功 | `NORD14` | 已完成、已下載 |
| 警告 | `NORD13` | 待處理 |
| 錯誤 | `NORD11` | 失敗 |
| 資訊 | `NORD8` | 連結、關鍵字 |
| 次要 | `NORD4` | 淡化文字 |

### 分頁標籤
- 未選中背景：`NORD1`
- 選中背景：`NORD0`
- 選中指示：`NORD8` 底線（2px）

### 捲軸
- 軌道背景：`NORD0`
- 滑塊：`NORD3`
- 滑塊懸停：`NORD9`
- 圓角設計

### 其他元件
- Tooltip：`NORD1` 背景 + `NORD3` 邊框
- Checkbox：勾選時 `NORD10` 背景
- GroupBox：`NORD3` 邊框 + `NORD6` 標題

## 實作方式

### 檔案結構
```
src/gui/styles.py  # 重寫此檔案
```

### 套用方式
```python
# 在 dlp01_gui.py 或 main.py 中
from src.gui.styles import apply_nord_theme

app = QApplication(sys.argv)
apply_nord_theme(app)  # 一行套用
```

### 需修改的檔案
1. `src/gui/styles.py` - 完整重寫，加入 Nord 主題
2. `src/gui/web_download_widget.py` - 移除硬編碼顏色，改用 styles 常數
3. `src/gui/main_window.py` - 移除硬編碼顏色，改用 styles 常數
4. `dlp01_gui.py` - 呼叫 `apply_nord_theme()`

## 設計原則

1. **對比度**：文字與背景至少 4.5:1 對比度（WCAG AA）
2. **層次感**：用 NORD0-3 建立背景層次
3. **一致性**：所有元件使用相同色彩系統
4. **狀態回饋**：hover/focus/selected 狀態明確
