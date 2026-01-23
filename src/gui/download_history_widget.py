"""
下載歷史 Widget
顯示下載記錄與重複下載追蹤
使用樹狀結構，相同 TID 的記錄合併為父子關係
"""
import webbrowser
from typing import Optional, List, Dict
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QHeaderView, QDialog, QListWidget, QListWidgetItem,
    QGroupBox, QFrame, QLineEdit, QComboBox, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QFont, QAction, QCursor


class DownloadTimesDialog(QDialog):
    """顯示下載時間記錄的浮動視窗"""

    def __init__(self, tid: str, title: str, times: List[Dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"下載歷史 - {title}")
        self.setMinimumSize(350, 250)

        layout = QVBoxLayout(self)

        # 標題
        lbl_title = QLabel(f"TID: {tid}")
        lbl_title.setFont(QFont("", 10, QFont.Weight.Bold))
        layout.addWidget(lbl_title)

        lbl_count = QLabel(f"共下載 {len(times)} 次")
        layout.addWidget(lbl_count)

        # 分隔線
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)

        # 時間列表
        self.list_times = QListWidget()
        for i, record in enumerate(times, 1):
            download_time = record.get('download_time', '')
            filename = record.get('filename', '')

            # 格式化時間
            try:
                dt = datetime.fromisoformat(download_time)
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                time_str = download_time

            item_text = f"第 {i} 次: {time_str}"
            if filename:
                item_text += f"\n    檔案: {filename}"

            item = QListWidgetItem(item_text)
            self.list_times.addItem(item)

        layout.addWidget(self.list_times)

        # 關閉按鈕
        btn_close = QPushButton("關閉")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


class DownloadHistoryWidget(QWidget):
    """下載歷史 Widget - 使用樹狀結構顯示"""

    # 訊號
    refresh_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 標題與刷新按鈕
        header_layout = QHBoxLayout()

        lbl_title = QLabel("下載記錄")
        lbl_title.setFont(QFont("", 12, QFont.Weight.Bold))
        header_layout.addWidget(lbl_title)

        header_layout.addStretch()

        # 搜尋
        header_layout.addWidget(QLabel("搜尋:"))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("輸入標題...")
        self.txt_search.setMaximumWidth(200)
        self.txt_search.textChanged.connect(self._apply_filter)
        header_layout.addWidget(self.txt_search)

        # 篩選
        header_layout.addWidget(QLabel("篩選:"))
        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["全部", "僅重複下載", "僅分割檔"])
        self.combo_filter.currentTextChanged.connect(self._apply_filter)
        header_layout.addWidget(self.combo_filter)

        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self._refresh)
        header_layout.addWidget(btn_refresh)

        layout.addLayout(header_layout)

        # 統計資訊
        stats_group = QGroupBox("統計")
        stats_layout = QHBoxLayout(stats_group)

        self.lbl_total = QLabel("總計: 0")
        self.lbl_repeated = QLabel("重複下載: 0")
        self.lbl_split = QLabel("分割檔: 0")
        stats_layout.addWidget(self.lbl_total)
        stats_layout.addWidget(self.lbl_repeated)
        stats_layout.addWidget(self.lbl_split)
        stats_layout.addStretch()

        layout.addWidget(stats_group)

        # 樹狀結構
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([
            "標題", "TID", "下載次數", "分割檔數", "最後下載", "狀態"
        ])

        # 設定欄位寬度
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)

        # 右鍵選單
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)

        # 雙擊展開/收合或查看詳情
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        layout.addWidget(self.tree)

        # 操作按鈕列
        btn_layout = QHBoxLayout()

        btn_expand_all = QPushButton("全部展開")
        btn_expand_all.clicked.connect(self.tree.expandAll)
        btn_layout.addWidget(btn_expand_all)

        btn_collapse_all = QPushButton("全部收合")
        btn_collapse_all.clicked.connect(self.tree.collapseAll)
        btn_layout.addWidget(btn_collapse_all)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    def _refresh(self):
        """刷新資料"""
        self.refresh_requested.emit()

    def load_data(self, records: List[Dict]):
        """
        載入資料
        records: 每筆記錄應包含 tid, title, download_count, last_download, status, files
                 files 是該 TID 下的所有檔案列表
        """
        self.tree.clear()

        total = 0
        repeated = 0
        split_count = 0

        # 按 TID 分組
        tid_groups: Dict[str, List[Dict]] = {}
        for record in records:
            tid = str(record.get('tid', ''))
            if tid not in tid_groups:
                tid_groups[tid] = []
            tid_groups[tid].append(record)

        for tid, group_records in tid_groups.items():
            total += 1

            # 主記錄（第一筆或合併資訊）
            main_record = group_records[0]
            title = main_record.get('title', '') or f"TID: {tid}"
            download_count = main_record.get('download_count', len(group_records))
            last_download = main_record.get('last_download', '')
            status = main_record.get('status', '')

            # 計算分割檔數量
            files = main_record.get('files', [])
            split_files_count = len(files) if files else len(group_records)
            if split_files_count > 1:
                split_count += 1

            # 建立主項目
            item = QTreeWidgetItem()
            item.setText(0, title)
            item.setText(1, tid)

            # 下載次數
            count_text = f"[{download_count}]"
            item.setText(2, count_text)
            if download_count >= 3:
                item.setForeground(2, QBrush(QColor(200, 0, 0)))
                item.setFont(2, QFont("", -1, QFont.Weight.Bold))
                repeated += 1
            elif download_count >= 2:
                item.setForeground(2, QBrush(QColor(200, 100, 0)))
                repeated += 1

            # 分割檔數量
            if split_files_count > 1:
                item.setText(3, f"{split_files_count} 個分割檔")
                item.setForeground(3, QBrush(QColor(0, 100, 180)))
            else:
                item.setText(3, "-")

            # 最後下載時間
            try:
                dt = datetime.fromisoformat(last_download)
                time_str = dt.strftime("%Y-%m-%d %H:%M")
            except:
                time_str = last_download
            item.setText(4, time_str)

            # 狀態
            item.setText(5, status)

            # 儲存完整記錄資料
            item.setData(0, Qt.ItemDataRole.UserRole, main_record)

            # 加入子項目（分割檔詳細資訊）
            if files and len(files) > 1:
                for file_record in files:
                    child = QTreeWidgetItem()
                    filename = file_record.get('filename', '')
                    child.setText(0, f"  └─ {filename}")
                    child.setText(1, "")

                    # 單檔下載次數
                    file_count = file_record.get('download_count', 1)
                    child.setText(2, f"[{file_count}]")

                    child.setText(3, "")

                    # 下載時間
                    file_time = file_record.get('download_time', '')
                    try:
                        dt = datetime.fromisoformat(file_time)
                        child.setText(4, dt.strftime("%Y-%m-%d %H:%M"))
                    except:
                        child.setText(4, file_time)

                    child.setText(5, file_record.get('status', ''))
                    child.setData(0, Qt.ItemDataRole.UserRole, file_record)

                    item.addChild(child)

            self.tree.addTopLevelItem(item)

            # 有多個子項目時預設收合
            if item.childCount() > 0:
                item.setExpanded(False)

        # 更新統計
        self.lbl_total.setText(f"總計: {total}")
        self.lbl_repeated.setText(f"重複下載: {repeated}")
        self.lbl_split.setText(f"分割檔: {split_count}")

    def _apply_filter(self):
        """套用篩選"""
        search_text = self.txt_search.text().lower()
        filter_type = self.combo_filter.currentText()

        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            title = item.text(0).lower()
            tid = item.text(1)
            count_text = item.text(2)
            split_text = item.text(3)

            # 搜尋匹配
            search_match = not search_text or search_text in title or search_text in tid

            # 篩選匹配
            filter_match = True
            if filter_type == "僅重複下載":
                try:
                    count = int(count_text.strip('[]'))
                    filter_match = count >= 2
                except:
                    filter_match = False
            elif filter_type == "僅分割檔":
                filter_match = split_text != "-"

            item.setHidden(not (search_match and filter_match))

    def _show_context_menu(self, position):
        """顯示右鍵選單"""
        item = self.tree.itemAt(position)
        if not item:
            return

        record = item.data(0, Qt.ItemDataRole.UserRole)
        if not record:
            return

        menu = QMenu(self)

        # 開啟帖子連結
        post_url = record.get('post_url', '')
        if post_url:
            action_open = QAction("開啟帖子連結", self)
            action_open.triggered.connect(lambda: webbrowser.open(post_url))
            menu.addAction(action_open)

        # 查看下載歷史
        tid = record.get('tid', item.text(1))
        if tid:
            action_history = QAction("查看下載時間記錄", self)
            action_history.triggered.connect(lambda: self._show_download_times(tid, item.text(0)))
            menu.addAction(action_history)

        if menu.actions():
            menu.exec(QCursor.pos())

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """雙擊項目"""
        # 如果是父項目且有子項目，切換展開狀態
        if item.childCount() > 0:
            item.setExpanded(not item.isExpanded())
        else:
            # 查看下載時間記錄
            record = item.data(0, Qt.ItemDataRole.UserRole)
            if record:
                tid = record.get('tid', '')
                title = item.text(0)
                if tid:
                    self._show_download_times(tid, title)

    def _show_download_times(self, tid: str, title: str):
        """顯示下載時間記錄"""
        try:
            from ..database.db_manager import DatabaseManager
            db = DatabaseManager()
            times = db.get_download_times(tid)

            if times:
                dialog = DownloadTimesDialog(tid, title, times, self)
                dialog.exec()
        except Exception as e:
            print(f"載入下載時間失敗: {e}")


class RepeatedDownloadsWidget(QWidget):
    """重複下載警示 Widget - 只顯示下載次數 >= 2 的"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 標題
        lbl_title = QLabel("重複下載警示")
        lbl_title.setFont(QFont("", 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #c00;")
        layout.addWidget(lbl_title)

        # 樹狀結構
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["標題", "TID", "下載次數", "分割檔數"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.setMaximumHeight(200)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        layout.addWidget(self.tree)

    def load_data(self, records: List[Dict]):
        """載入資料 (只顯示 count >= 2)"""
        self.tree.clear()

        for record in records:
            count = record.get('download_count', 1)
            if count < 2:
                continue

            tid = str(record.get('tid', ''))
            title = record.get('title', '') or f"TID: {tid}"
            files = record.get('files', [])
            split_count = len(files) if files else 1

            item = QTreeWidgetItem()
            item.setText(0, title)
            item.setText(1, tid)

            # 下載次數
            count_item_text = str(count)
            item.setText(2, count_item_text)
            if count >= 3:
                item.setForeground(2, QBrush(QColor(200, 0, 0)))
                item.setFont(2, QFont("", -1, QFont.Weight.Bold))
            else:
                item.setForeground(2, QBrush(QColor(200, 100, 0)))

            # 分割檔數
            if split_count > 1:
                item.setText(3, f"{split_count} 個")
            else:
                item.setText(3, "-")

            item.setData(0, Qt.ItemDataRole.UserRole, record)
            self.tree.addTopLevelItem(item)

        # 如果沒有資料，隱藏自己
        self.setVisible(self.tree.topLevelItemCount() > 0)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """雙擊項目 - 查看下載時間記錄"""
        record = item.data(0, Qt.ItemDataRole.UserRole)
        if record:
            tid = record.get('tid', '')
            title = item.text(0)
            if tid:
                try:
                    from ..database.db_manager import DatabaseManager
                    db = DatabaseManager()
                    times = db.get_download_times(tid)

                    if times:
                        dialog = DownloadTimesDialog(tid, title, times, self)
                        dialog.exec()
                except Exception as e:
                    print(f"載入下載時間失敗: {e}")
