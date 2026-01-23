"""
解壓記錄顯示 GUI 元件
採用主列表 + 詳細面板設計
"""
import os
import subprocess
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
    QSplitter, QFrame, QComboBox, QLineEdit, QHeaderView,
    QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class ExtractHistoryWidget(QWidget):
    """解壓記錄顯示元件"""

    # 重新整理訊號
    refresh_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_record = None
        self._init_ui()

    def _init_ui(self):
        """初始化介面"""
        layout = QVBoxLayout(self)

        # 搜尋/篩選列
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("搜尋:"))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("輸入檔案名稱...")
        self.txt_search.textChanged.connect(self._on_search_changed)
        self.txt_search.setMaximumWidth(200)
        filter_layout.addWidget(self.txt_search)

        filter_layout.addWidget(QLabel("狀態:"))
        self.combo_status = QComboBox()
        self.combo_status.addItems(["全部", "成功", "失敗"])
        self.combo_status.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.combo_status)

        filter_layout.addStretch()

        btn_refresh = QPushButton("重新整理")
        btn_refresh.clicked.connect(self._on_refresh_clicked)
        filter_layout.addWidget(btn_refresh)

        layout.addLayout(filter_layout)

        # 分割視窗：上方列表，下方詳細
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 主列表
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)

        self.tree_records = QTreeWidget()
        self.tree_records.setHeaderLabels(["檔案名稱", "狀態", "檔案數", "解壓時間", "大小"])
        self.tree_records.setColumnWidth(0, 300)
        self.tree_records.setColumnWidth(1, 60)
        self.tree_records.setColumnWidth(2, 60)
        self.tree_records.setColumnWidth(3, 140)
        self.tree_records.setColumnWidth(4, 80)
        self.tree_records.setAlternatingRowColors(True)
        self.tree_records.setRootIsDecorated(True)  # 顯示樹狀展開按鈕
        self.tree_records.itemSelectionChanged.connect(self._on_selection_changed)

        # 設定欄位調整模式
        header = self.tree_records.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)

        list_layout.addWidget(self.tree_records)
        splitter.addWidget(list_widget)

        # 詳細面板
        self.detail_panel = self._create_detail_panel()
        splitter.addWidget(self.detail_panel)

        # 設定分割比例
        splitter.setSizes([300, 200])

        layout.addWidget(splitter)

    def _create_detail_panel(self) -> QWidget:
        """建立詳細資訊面板"""
        panel = QGroupBox("詳細資訊")
        layout = QVBoxLayout(panel)

        # 檔案名稱
        self.lbl_filename = QLabel("請選擇一筆記錄")
        self.lbl_filename.setFont(QFont("", 11, QFont.Weight.Bold))
        layout.addWidget(self.lbl_filename)

        # 來源帖子
        source_layout = QHBoxLayout()
        self.lbl_source_title = QLabel("")
        source_layout.addWidget(self.lbl_source_title)
        source_layout.addStretch()
        self.btn_open_post = QPushButton("開啟帖子連結")
        self.btn_open_post.setEnabled(False)
        self.btn_open_post.clicked.connect(self._open_post_url)
        source_layout.addWidget(self.btn_open_post)
        layout.addLayout(source_layout)

        # 分隔線
        layout.addWidget(self._create_separator())

        # 解壓資訊
        info_group = QWidget()
        info_layout = QGridLayout(info_group)
        info_layout.setContentsMargins(0, 0, 0, 0)

        info_layout.addWidget(QLabel("狀態:"), 0, 0)
        self.lbl_status = QLabel("-")
        info_layout.addWidget(self.lbl_status, 0, 1)

        info_layout.addWidget(QLabel("解壓時間:"), 0, 2)
        self.lbl_extract_time = QLabel("-")
        info_layout.addWidget(self.lbl_extract_time, 0, 3)

        info_layout.addWidget(QLabel("目的地:"), 1, 0)
        self.lbl_dest_path = QLabel("-")
        self.lbl_dest_path.setWordWrap(True)
        info_layout.addWidget(self.lbl_dest_path, 1, 1, 1, 3)

        info_layout.addWidget(QLabel("巢狀層級:"), 2, 0)
        self.lbl_nested_level = QLabel("-")
        info_layout.addWidget(self.lbl_nested_level, 2, 1)

        layout.addWidget(info_group)

        # 分隔線
        layout.addWidget(self._create_separator())

        # 檔案統計
        stats_group = QWidget()
        stats_layout = QGridLayout(stats_group)
        stats_layout.setContentsMargins(0, 0, 0, 0)

        stats_layout.addWidget(QLabel("解壓檔案:"), 0, 0)
        self.lbl_files_extracted = QLabel("-")
        stats_layout.addWidget(self.lbl_files_extracted, 0, 1)

        stats_layout.addWidget(QLabel("跳過 (重複):"), 0, 2)
        self.lbl_files_skipped = QLabel("-")
        stats_layout.addWidget(self.lbl_files_skipped, 0, 3)

        stats_layout.addWidget(QLabel("過濾排除:"), 0, 4)
        self.lbl_files_filtered = QLabel("-")
        stats_layout.addWidget(self.lbl_files_filtered, 0, 5)

        layout.addWidget(stats_group)

        # 分隔線
        layout.addWidget(self._create_separator())

        # 大小資訊
        size_group = QWidget()
        size_layout = QGridLayout(size_group)
        size_layout.setContentsMargins(0, 0, 0, 0)

        size_layout.addWidget(QLabel("壓縮檔:"), 0, 0)
        self.lbl_archive_size = QLabel("-")
        size_layout.addWidget(self.lbl_archive_size, 0, 1)

        size_layout.addWidget(QLabel("解壓後:"), 0, 2)
        self.lbl_extracted_size = QLabel("-")
        size_layout.addWidget(self.lbl_extracted_size, 0, 3)

        size_layout.addWidget(QLabel("壓縮率:"), 0, 4)
        self.lbl_compression_ratio = QLabel("-")
        size_layout.addWidget(self.lbl_compression_ratio, 0, 5)

        layout.addWidget(size_group)

        # 錯誤訊息 (失敗時顯示)
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: red;")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setVisible(False)
        layout.addWidget(self.lbl_error)

        # 操作按鈕
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_open_folder = QPushButton("開啟目的地資料夾")
        self.btn_open_folder.setEnabled(False)
        self.btn_open_folder.clicked.connect(self._open_dest_folder)
        btn_layout.addWidget(self.btn_open_folder)

        layout.addLayout(btn_layout)

        return panel

    def _create_separator(self) -> QFrame:
        """建立分隔線"""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _format_size(self, size: int) -> str:
        """格式化檔案大小"""
        if size is None:
            return "-"
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / 1024 / 1024:.1f} MB"
        else:
            return f"{size / 1024 / 1024 / 1024:.2f} GB"

    def _format_time(self, time_str: str) -> str:
        """格式化時間"""
        if not time_str:
            return "-"
        return time_str[:19].replace('T', ' ')

    def load_records(self, records: list, nested_records: dict = None):
        """
        載入記錄

        Args:
            records: 主記錄列表
            nested_records: 巢狀記錄字典 {parent_id: [child_records]}
        """
        self.tree_records.clear()
        nested_records = nested_records or {}

        for record in records:
            item = self._create_tree_item(record)
            self.tree_records.addTopLevelItem(item)

            # 加入巢狀子記錄
            parent_id = record.get('id')
            if parent_id in nested_records:
                for child_record in nested_records[parent_id]:
                    child_item = self._create_tree_item(child_record, is_nested=True)
                    item.addChild(child_item)

            # 展開有子項目的節點
            if item.childCount() > 0:
                item.setExpanded(True)

    def _create_tree_item(self, record: dict, is_nested: bool = False) -> QTreeWidgetItem:
        """建立樹狀項目"""
        item = QTreeWidgetItem()

        # 檔案名稱
        filename = record.get('archive_filename') or record.get('jd_package_name') or '-'
        if is_nested:
            filename = f"  └─ {filename}"
        item.setText(0, filename)

        # 狀態
        success = record.get('extract_success')
        if success is True:
            item.setText(1, "成功")
            item.setForeground(1, Qt.GlobalColor.darkGreen)
        elif success is False:
            item.setText(1, "失敗")
            item.setForeground(1, Qt.GlobalColor.red)
        else:
            item.setText(1, "-")

        # 檔案數
        files_extracted = record.get('files_extracted')
        item.setText(2, str(files_extracted) if files_extracted else "-")

        # 解壓時間
        item.setText(3, self._format_time(record.get('extracted_at')))

        # 大小
        item.setText(4, self._format_size(record.get('archive_size')))

        # 儲存完整記錄資料
        item.setData(0, Qt.ItemDataRole.UserRole, record)

        return item

    def _on_selection_changed(self):
        """選取變更事件"""
        items = self.tree_records.selectedItems()
        if not items:
            self._clear_detail()
            return

        record = items[0].data(0, Qt.ItemDataRole.UserRole)
        if record:
            self._show_detail(record)

    def _clear_detail(self):
        """清空詳細面板"""
        self._current_record = None
        self.lbl_filename.setText("請選擇一筆記錄")
        self.lbl_source_title.setText("")
        self.btn_open_post.setEnabled(False)
        self.lbl_status.setText("-")
        self.lbl_extract_time.setText("-")
        self.lbl_dest_path.setText("-")
        self.lbl_nested_level.setText("-")
        self.lbl_files_extracted.setText("-")
        self.lbl_files_skipped.setText("-")
        self.lbl_files_filtered.setText("-")
        self.lbl_archive_size.setText("-")
        self.lbl_extracted_size.setText("-")
        self.lbl_compression_ratio.setText("-")
        self.lbl_error.setVisible(False)
        self.btn_open_folder.setEnabled(False)

    def _show_detail(self, record: dict):
        """顯示詳細資訊"""
        self._current_record = record

        # 檔案名稱
        filename = record.get('archive_filename') or record.get('jd_package_name') or '-'
        self.lbl_filename.setText(f"檔案：{filename}")

        # 來源帖子
        title = record.get('title', '')
        if title:
            self.lbl_source_title.setText(f"來源帖子：{title[:50]}{'...' if len(title) > 50 else ''}")
            self.btn_open_post.setEnabled(bool(record.get('post_url')))
        else:
            self.lbl_source_title.setText("")
            self.btn_open_post.setEnabled(False)

        # 狀態
        success = record.get('extract_success')
        if success is True:
            self.lbl_status.setText("成功")
            self.lbl_status.setStyleSheet("color: green; font-weight: bold;")
        elif success is False:
            self.lbl_status.setText("失敗")
            self.lbl_status.setStyleSheet("color: red; font-weight: bold;")
        else:
            self.lbl_status.setText("-")
            self.lbl_status.setStyleSheet("")

        # 解壓時間
        self.lbl_extract_time.setText(self._format_time(record.get('extracted_at')))

        # 目的地
        dest_path = record.get('extract_dest_path', '-')
        self.lbl_dest_path.setText(dest_path or '-')
        self.btn_open_folder.setEnabled(bool(dest_path))

        # 巢狀層級
        nested_level = record.get('nested_level', 0)
        level_text = f"{nested_level}" if nested_level else "0 (原始)"
        self.lbl_nested_level.setText(level_text)

        # 檔案統計
        self.lbl_files_extracted.setText(str(record.get('files_extracted') or 0))
        self.lbl_files_skipped.setText(str(record.get('files_skipped') or 0))
        self.lbl_files_filtered.setText(str(record.get('files_filtered') or 0))

        # 大小資訊
        archive_size = record.get('archive_size') or 0
        extracted_size = record.get('extracted_size') or 0
        self.lbl_archive_size.setText(self._format_size(archive_size))
        self.lbl_extracted_size.setText(self._format_size(extracted_size))

        # 壓縮率
        if archive_size and extracted_size:
            ratio = (archive_size / extracted_size) * 100
            self.lbl_compression_ratio.setText(f"{ratio:.1f}%")
        else:
            self.lbl_compression_ratio.setText("-")

        # 錯誤訊息
        error_msg = record.get('error_message')
        if error_msg:
            self.lbl_error.setText(f"錯誤：{error_msg}")
            self.lbl_error.setVisible(True)
        else:
            self.lbl_error.setVisible(False)

    def _open_post_url(self):
        """開啟帖子連結"""
        if self._current_record:
            url = self._current_record.get('post_url')
            if url:
                import webbrowser
                webbrowser.open(url)

    def _open_dest_folder(self):
        """開啟目的地資料夾"""
        if self._current_record:
            path = self._current_record.get('extract_dest_path')
            if path and os.path.exists(path):
                # Windows 使用 explorer
                subprocess.run(['explorer', path])
            else:
                QMessageBox.warning(self, "錯誤", f"資料夾不存在：{path}")

    def _on_search_changed(self, text: str):
        """搜尋文字變更"""
        self._apply_filter()

    def _on_filter_changed(self, text: str):
        """篩選條件變更"""
        self._apply_filter()

    def _apply_filter(self):
        """套用篩選"""
        search_text = self.txt_search.text().lower()
        status_filter = self.combo_status.currentText()

        for i in range(self.tree_records.topLevelItemCount()):
            item = self.tree_records.topLevelItem(i)
            self._filter_item(item, search_text, status_filter)

    def _filter_item(self, item: QTreeWidgetItem, search_text: str, status_filter: str):
        """篩選項目"""
        filename = item.text(0).lower()
        status = item.text(1)

        # 搜尋條件
        match_search = not search_text or search_text in filename

        # 狀態條件
        match_status = (
            status_filter == "全部" or
            (status_filter == "成功" and status == "成功") or
            (status_filter == "失敗" and status == "失敗")
        )

        visible = match_search and match_status
        item.setHidden(not visible)

        # 遞迴處理子項目
        for j in range(item.childCount()):
            child = item.child(j)
            self._filter_item(child, search_text, status_filter)

    def _on_refresh_clicked(self):
        """重新整理按鈕點擊"""
        self.refresh_requested.emit()
