"""
版區搜尋元件
搜尋指定版區內的帖子並批次下載
"""
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QLineEdit, QGroupBox, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QProgressBar, QCheckBox, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QColor, QBrush

from ..database.db_manager import DatabaseManager
from ..utils.logger import logger


class SearchWorker(QThread):
    """搜尋工作執行緒"""
    progress_signal = pyqtSignal(str)
    result_signal = pyqtSignal(list)  # 搜尋結果
    error_signal = pyqtSignal(str)

    def __init__(self, config_path: str, keyword: str, fids: List[str]):
        super().__init__()
        self.config_path = config_path
        self.keyword = keyword
        self.fids = fids

    def run(self):
        try:
            from ..crawler.forum_client import ForumClient
            from ..crawler.forum_searcher import ForumSearcher

            self.progress_signal.emit("正在連線...")
            client = ForumClient(self.config_path)

            if not client.check_login():
                self.error_signal.emit("未登入，請先設定 Cookie")
                return

            self.progress_signal.emit(f"正在搜尋 {len(self.fids)} 個版區...")
            searcher = ForumSearcher(client)
            results = searcher.search(self.keyword, self.fids, max_pages=3)

            self.result_signal.emit(results)

        except Exception as e:
            self.error_signal.emit(str(e))


class SectionSearchWidget(QWidget):
    """版區搜尋元件"""

    # 訊號
    download_requested = pyqtSignal(list)  # 請求下載選中的帖子
    import_from_manager_requested = pyqtSignal()  # 請求從版區管理匯入

    def __init__(self, config: dict, config_path: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.config_path = config_path
        self.db = DatabaseManager()
        self.search_worker = None
        self.current_session_id = None
        self._section_manager = None  # 用於取得版區管理的選擇

        self._init_ui()
        self._load_sections()

    def set_section_manager(self, manager):
        """設定版區管理元件參考"""
        self._section_manager = manager

    def _init_ui(self):
        """初始化介面"""
        layout = QVBoxLayout(self)

        # 使用分割器
        splitter = QSplitter(Qt.Orientation.Vertical)

        # === 上半部：選擇版區和搜尋 ===
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        # 步驟一：選擇版區
        section_group = QGroupBox("步驟一：選擇版區")
        section_layout = QVBoxLayout(section_group)

        # 版區搜尋
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("篩選版區:"))
        self.txt_section_filter = QLineEdit()
        self.txt_section_filter.setPlaceholderText("輸入版區名稱關鍵字...")
        self.txt_section_filter.textChanged.connect(self._filter_sections)
        filter_layout.addWidget(self.txt_section_filter)

        btn_select_all = QPushButton("全選")
        btn_select_all.clicked.connect(self._select_all_sections)
        filter_layout.addWidget(btn_select_all)

        btn_clear_all = QPushButton("清除")
        btn_clear_all.clicked.connect(self._clear_all_sections)
        filter_layout.addWidget(btn_clear_all)

        filter_layout.addStretch()

        self.btn_import_from_manager = QPushButton("從版區管理匯入")
        self.btn_import_from_manager.setToolTip("匯入「版區管理」中已勾選的版區")
        self.btn_import_from_manager.clicked.connect(self._import_from_manager)
        filter_layout.addWidget(self.btn_import_from_manager)

        section_layout.addLayout(filter_layout)

        # 版區樹狀結構
        self.section_tree = QTreeWidget()
        self.section_tree.setHeaderLabels(["選擇", "版區名稱", "FID"])
        self.section_tree.setColumnCount(3)
        self.section_tree.setMaximumHeight(200)

        header = self.section_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        section_layout.addWidget(self.section_tree)

        top_layout.addWidget(section_group)

        # 步驟二：搜尋帖子
        search_group = QGroupBox("步驟二：搜尋帖子")
        search_layout = QHBoxLayout(search_group)

        search_layout.addWidget(QLabel("關鍵字:"))
        self.txt_keyword = QLineEdit()
        self.txt_keyword.setPlaceholderText("輸入搜尋關鍵字...")
        self.txt_keyword.returnPressed.connect(self._do_search)
        search_layout.addWidget(self.txt_keyword)

        self.btn_search = QPushButton("搜尋帖子")
        self.btn_search.clicked.connect(self._do_search)
        search_layout.addWidget(self.btn_search)

        top_layout.addWidget(search_group)

        splitter.addWidget(top_widget)

        # === 下半部：搜尋結果 ===
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        # 結果標題和按鈕
        result_header = QHBoxLayout()

        self.lbl_result_count = QLabel("搜尋結果 (共 0 筆，已選 0 筆)")
        self.lbl_result_count.setFont(QFont("", 10, QFont.Weight.Bold))
        result_header.addWidget(self.lbl_result_count)

        result_header.addStretch()

        btn_select_all_results = QPushButton("全選")
        btn_select_all_results.clicked.connect(self._select_all_results)
        result_header.addWidget(btn_select_all_results)

        self.btn_download = QPushButton("執行下載")
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self._do_download)
        result_header.addWidget(self.btn_download)

        bottom_layout.addLayout(result_header)

        # 進度條
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        bottom_layout.addWidget(self.progress_bar)

        # 狀態標籤
        self.lbl_status = QLabel("")
        self.lbl_status.setVisible(False)
        bottom_layout.addWidget(self.lbl_status)

        # 結果表格
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(6)
        self.result_table.setHorizontalHeaderLabels([
            "選擇", "標題", "版區", "作者", "日期", "TID"
        ])

        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self.result_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.result_table.setAlternatingRowColors(True)
        self.result_table.itemChanged.connect(self._on_result_item_changed)

        bottom_layout.addWidget(self.result_table)

        splitter.addWidget(bottom_widget)

        # 設定分割比例
        splitter.setSizes([300, 400])

        layout.addWidget(splitter)

    def _load_sections(self):
        """載入版區到樹狀結構"""
        self.section_tree.clear()

        # 取得版區樹狀結構
        sections_tree = self.db.get_forum_sections_tree()

        if not sections_tree:
            # 沒有版區資料，顯示提示
            item = QTreeWidgetItem(self.section_tree)
            item.setText(1, "(尚未同步版區，請先到「版區設定」同步)")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            return

        # 遞迴建立樹狀結構
        for section in sections_tree:
            self._add_section_to_tree(section, None)

        self.section_tree.expandAll()

    def _add_section_to_tree(self, section: Dict, parent_item: QTreeWidgetItem):
        """遞迴新增版區到樹狀結構"""
        fid = section['fid']
        name = section['name']

        # 建立項目
        if parent_item:
            item = QTreeWidgetItem(parent_item)
        else:
            item = QTreeWidgetItem(self.section_tree)

        # 勾選框
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Unchecked)

        # 版區名稱
        item.setText(1, name)

        # FID
        item.setText(2, fid)

        # 儲存 fid 到 item data
        item.setData(0, Qt.ItemDataRole.UserRole, fid)

        # 遞迴處理子版區
        for child in section.get('children', []):
            self._add_section_to_tree(child, item)

    def _filter_sections(self):
        """篩選版區"""
        filter_text = self.txt_section_filter.text().lower()

        def filter_item(item: QTreeWidgetItem) -> bool:
            """遞迴篩選項目"""
            child_visible = False
            for i in range(item.childCount()):
                if filter_item(item.child(i)):
                    child_visible = True

            name = item.text(1).lower()
            visible = filter_text in name or child_visible
            item.setHidden(not visible)

            return visible

        for i in range(self.section_tree.topLevelItemCount()):
            filter_item(self.section_tree.topLevelItem(i))

    def _select_all_sections(self):
        """全選可見的版區"""
        def select_visible(item: QTreeWidgetItem):
            if not item.isHidden():
                fid = item.data(0, Qt.ItemDataRole.UserRole)
                # 只選擇實際版區，不選分類
                if fid and not fid.startswith('gid_') and not fid.startswith('cat_'):
                    item.setCheckState(0, Qt.CheckState.Checked)
            for i in range(item.childCount()):
                select_visible(item.child(i))

        for i in range(self.section_tree.topLevelItemCount()):
            select_visible(self.section_tree.topLevelItem(i))

    def _clear_all_sections(self):
        """清除所有選擇"""
        def clear_item(item: QTreeWidgetItem):
            item.setCheckState(0, Qt.CheckState.Unchecked)
            for i in range(item.childCount()):
                clear_item(item.child(i))

        for i in range(self.section_tree.topLevelItemCount()):
            clear_item(self.section_tree.topLevelItem(i))

    def _import_from_manager(self):
        """從版區管理匯入已勾選的版區"""
        if not self._section_manager:
            QMessageBox.warning(self, "提示", "無法連接到版區管理")
            return

        # 取得版區管理中已勾選的版區
        enabled_sections = self._section_manager.get_enabled_sections_from_tree()

        if not enabled_sections:
            QMessageBox.warning(self, "提示", "版區管理中沒有勾選任何版區")
            return

        # 建立 fid 集合方便查詢
        enabled_fids = {s['fid'] for s in enabled_sections}

        # 清除現有選擇
        self._clear_all_sections()

        # 勾選匹配的版區
        count = 0

        def check_matching(item: QTreeWidgetItem):
            nonlocal count
            fid = item.data(0, Qt.ItemDataRole.UserRole)
            if fid and str(fid) in enabled_fids:
                item.setCheckState(0, Qt.CheckState.Checked)
                count += 1
            for i in range(item.childCount()):
                check_matching(item.child(i))

        for i in range(self.section_tree.topLevelItemCount()):
            check_matching(self.section_tree.topLevelItem(i))

        QMessageBox.information(self, "完成", f"已匯入 {count} 個版區")

    def _get_selected_fids(self) -> List[str]:
        """取得選中的版區 FID"""
        fids = []

        def collect_fids(item: QTreeWidgetItem):
            if item.checkState(0) == Qt.CheckState.Checked:
                fid = item.data(0, Qt.ItemDataRole.UserRole)
                if fid:
                    fids.append(fid)
            for i in range(item.childCount()):
                collect_fids(item.child(i))

        for i in range(self.section_tree.topLevelItemCount()):
            collect_fids(self.section_tree.topLevelItem(i))

        return fids

    def _do_search(self):
        """執行搜尋"""
        keyword = self.txt_keyword.text().strip()
        if not keyword:
            QMessageBox.warning(self, "提示", "請輸入搜尋關鍵字")
            return

        fids = self._get_selected_fids()
        if not fids:
            QMessageBox.warning(self, "提示", "請選擇至少一個版區")
            return

        if self.search_worker and self.search_worker.isRunning():
            QMessageBox.warning(self, "提示", "正在搜尋中，請稍候...")
            return

        # 清空結果
        self.result_table.setRowCount(0)

        # 顯示進度
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不確定進度
        self.lbl_status.setVisible(True)
        self.lbl_status.setText("準備搜尋...")
        self.btn_search.setEnabled(False)

        # 建立搜尋 session
        self.current_session_id = self.db.create_search_session()

        # 啟動搜尋
        self.search_worker = SearchWorker(str(self.config_path), keyword, fids)
        self.search_worker.progress_signal.connect(self._on_search_progress)
        self.search_worker.result_signal.connect(self._on_search_result)
        self.search_worker.error_signal.connect(self._on_search_error)
        self.search_worker.start()

    def _on_search_progress(self, message: str):
        """搜尋進度更新"""
        self.lbl_status.setText(message)

    def _on_search_result(self, results: List[Dict]):
        """搜尋結果"""
        self.progress_bar.setVisible(False)
        self.lbl_status.setVisible(False)
        self.btn_search.setEnabled(True)

        if not results:
            QMessageBox.information(self, "搜尋結果", "沒有找到符合條件的帖子")
            return

        # 儲存到資料庫
        self.db.save_search_results_batch(self.current_session_id, results)

        # 顯示結果
        self._display_results(results)

    def _on_search_error(self, error: str):
        """搜尋錯誤"""
        self.progress_bar.setVisible(False)
        self.lbl_status.setVisible(False)
        self.btn_search.setEnabled(True)
        QMessageBox.warning(self, "搜尋失敗", f"錯誤: {error}")

    def _display_results(self, results: List[Dict]):
        """顯示搜尋結果"""
        self.result_table.blockSignals(True)
        self.result_table.setRowCount(len(results))

        for row, result in enumerate(results):
            # 勾選框
            chk_item = QTableWidgetItem()
            chk_item.setFlags(chk_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            chk_item.setCheckState(Qt.CheckState.Unchecked)
            chk_item.setData(Qt.ItemDataRole.UserRole, result)
            self.result_table.setItem(row, 0, chk_item)

            # 標題
            self.result_table.setItem(row, 1, QTableWidgetItem(result.get('title', '')))

            # 版區
            self.result_table.setItem(row, 2, QTableWidgetItem(result.get('forum_name', '')))

            # 作者
            self.result_table.setItem(row, 3, QTableWidgetItem(result.get('author', '')))

            # 日期
            self.result_table.setItem(row, 4, QTableWidgetItem(result.get('post_date', '')))

            # TID
            self.result_table.setItem(row, 5, QTableWidgetItem(result.get('tid', '')))

        self.result_table.blockSignals(False)
        self._update_result_count()

    def _on_result_item_changed(self, item: QTableWidgetItem):
        """結果項目變更"""
        if item.column() == 0:
            self._update_result_count()

    def _update_result_count(self):
        """更新結果計數"""
        total = self.result_table.rowCount()
        selected = 0

        for row in range(total):
            item = self.result_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected += 1

        self.lbl_result_count.setText(f"搜尋結果 (共 {total} 筆，已選 {selected} 筆)")
        self.btn_download.setEnabled(selected > 0)

    def _select_all_results(self):
        """全選結果"""
        self.result_table.blockSignals(True)
        for row in range(self.result_table.rowCount()):
            item = self.result_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)
        self.result_table.blockSignals(False)
        self._update_result_count()

    def _do_download(self):
        """執行下載"""
        selected_posts = []

        for row in range(self.result_table.rowCount()):
            item = self.result_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                post_data = item.data(Qt.ItemDataRole.UserRole)
                if post_data:
                    selected_posts.append(post_data)

        if not selected_posts:
            QMessageBox.warning(self, "提示", "請選擇要下載的帖子")
            return

        # 確認
        reply = QMessageBox.question(
            self, "確認下載",
            f"確定要下載 {len(selected_posts)} 個帖子嗎？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.download_requested.emit(selected_posts)
