"""
版區搜尋管理元件
整合版區管理和搜尋功能
"""
import webbrowser
from typing import Dict, List, Optional
from datetime import datetime
import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QLineEdit, QGroupBox, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QProgressDialog, QComboBox, QCheckBox, QApplication, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QColor, QBrush, QAction, QCursor

from ..database.db_manager import DatabaseManager
from ..utils.logger import logger


class SyncWorker(QThread):
    """同步版區結構的工作執行緒"""
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int)
    error_signal = pyqtSignal(str)

    def __init__(self, config_path: str):
        super().__init__()
        self.config_path = config_path

    def run(self):
        try:
            from ..crawler.forum_client import ForumClient
            from ..crawler.forum_structure_scraper import ForumStructureScraper

            self.progress_signal.emit("正在連線到論壇...")
            client = ForumClient(self.config_path)

            if not client.check_login():
                self.error_signal.emit("未登入，請先設定 Cookie")
                return

            self.progress_signal.emit("正在爬取版區結構...")
            scraper = ForumStructureScraper(client)
            count = scraper.scrape_and_save()

            self.finished_signal.emit(count)

        except Exception as e:
            self.error_signal.emit(str(e))


class SearchWorker(QThread):
    """搜尋工作執行緒"""
    progress_signal = pyqtSignal(str)
    result_signal = pyqtSignal(list)
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


class SectionSearchManagerWidget(QWidget):
    """版區搜尋管理元件"""

    # 訊號
    settings_changed = pyqtSignal()
    download_requested = pyqtSignal(list)
    export_to_group_requested = pyqtSignal(list)

    # 搜尋歷史最大筆數
    MAX_SEARCH_HISTORY = 90

    def __init__(self, config: dict, config_path: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.config_path = config_path
        self.db = DatabaseManager()
        self.sync_worker = None
        self.search_worker = None

        # 搜尋歷史：儲存已搜尋過的帖子 TID
        self.search_history: List[str] = []
        self._load_search_history()

        self._init_ui()
        self._load_sections()
        self._update_selected_count()

    def _get_history_file_path(self) -> Path:
        """取得搜尋歷史檔案路徑"""
        config_dir = Path(self.config_path).parent
        return config_dir / 'search_history.json'

    def _load_search_history(self):
        """載入搜尋歷史"""
        try:
            history_file = self._get_history_file_path()
            if history_file.exists():
                with open(history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.search_history = data.get('tids', [])[-self.MAX_SEARCH_HISTORY:]
        except Exception as e:
            logger.warning(f"載入搜尋歷史失敗: {e}")
            self.search_history = []

    def _save_search_history(self):
        """儲存搜尋歷史"""
        try:
            history_file = self._get_history_file_path()
            # 只保留最新的 90 筆
            self.search_history = self.search_history[-self.MAX_SEARCH_HISTORY:]
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump({'tids': self.search_history}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"儲存搜尋歷史失敗: {e}")

    def _init_ui(self):
        """初始化介面"""
        layout = QVBoxLayout(self)

        # 使用分割器分隔版區樹和搜尋結果
        splitter = QSplitter(Qt.Orientation.Vertical)

        # === 上半部：版區管理 ===
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        # 工具列
        toolbar = QHBoxLayout()

        self.btn_sync = QPushButton("同步版區結構")
        self.btn_sync.clicked.connect(self._sync_sections)
        toolbar.addWidget(self.btn_sync)

        toolbar.addWidget(QLabel("篩選:"))
        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("輸入版區名稱...")
        self.txt_filter.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.txt_filter)

        toolbar.addWidget(QLabel("分類:"))
        self.combo_category = QComboBox()
        self.combo_category.addItem("全部")
        self.combo_category.currentTextChanged.connect(self._apply_filter)
        toolbar.addWidget(self.combo_category)

        toolbar.addStretch()

        self.lbl_last_sync = QLabel("最後同步: 從未")
        toolbar.addWidget(self.lbl_last_sync)

        top_layout.addLayout(toolbar)

        # 版區樹狀結構
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["選擇", "版區名稱", "FID", "分類"])
        self.tree.setColumnCount(4)

        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.tree.itemChanged.connect(self._on_item_changed)

        # 右鍵選單 - 用於管理單一版區的分類
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_section_context_menu)

        top_layout.addWidget(self.tree)

        # 快速操作列 - 選擇控制
        select_layout = QHBoxLayout()

        btn_select_all = QPushButton("全選")
        btn_select_all.clicked.connect(self._select_all)
        select_layout.addWidget(btn_select_all)

        btn_clear_all = QPushButton("取消全選")
        btn_clear_all.clicked.connect(self._clear_all)
        select_layout.addWidget(btn_clear_all)

        select_layout.addStretch()

        # 分類設定區 - 先勾選版區，再點擊分類按鈕
        select_layout.addWidget(QLabel("將勾選的版區設為:"))

        btn_set_favorite = QPushButton("★ 我的最愛")
        btn_set_favorite.setStyleSheet("QPushButton { color: #d4a000; font-weight: bold; }")
        btn_set_favorite.clicked.connect(lambda: self._set_selected_category("我的最愛"))
        select_layout.addWidget(btn_set_favorite)

        btn_set_common = QPushButton("◆ 常用")
        btn_set_common.setStyleSheet("QPushButton { color: #0066cc; font-weight: bold; }")
        btn_set_common.clicked.connect(lambda: self._set_selected_category("常用"))
        select_layout.addWidget(btn_set_common)

        btn_set_other = QPushButton("○ 其它")
        btn_set_other.clicked.connect(lambda: self._set_selected_category("其它"))
        select_layout.addWidget(btn_set_other)

        btn_clear_category = QPushButton("✕ 清除分類")
        btn_clear_category.setStyleSheet("QPushButton { color: #999; }")
        btn_clear_category.clicked.connect(lambda: self._set_selected_category(""))
        select_layout.addWidget(btn_clear_category)

        top_layout.addLayout(select_layout)

        # 操作列 - 匯出功能
        action_layout = QHBoxLayout()

        self.lbl_selected_count = QLabel("已勾選: 0 個版區")
        action_layout.addWidget(self.lbl_selected_count)

        action_layout.addStretch()

        btn_export = QPushButton("匯出勾選的版區到「版區群組」")
        btn_export.clicked.connect(self._export_to_group)
        action_layout.addWidget(btn_export)

        top_layout.addLayout(action_layout)

        splitter.addWidget(top_widget)

        # === 下半部：搜尋功能 ===
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        # 搜尋列
        search_layout = QHBoxLayout()

        search_layout.addWidget(QLabel("搜尋關鍵字:"))
        self.txt_keyword = QLineEdit()
        self.txt_keyword.setPlaceholderText("輸入關鍵字 (空格=AND, |=OR, \"...\"=精確詞組)")
        self.txt_keyword.setToolTip(
            "搜尋語法：\n"
            "• 空格分隔 = AND（都要符合）: ROSE JAV\n"
            "• | 分隔 = OR（任一符合）: ROSE|玫瑰\n"
            "• 雙引號 = 精確詞組: \"ROSE Vol\"\n"
            "• 混合使用: \"ROSE Vol\"|玫瑰"
        )
        self.txt_keyword.returnPressed.connect(self._do_search)
        search_layout.addWidget(self.txt_keyword)

        self.btn_search = QPushButton("搜尋帖子")
        self.btn_search.clicked.connect(self._do_search)
        search_layout.addWidget(self.btn_search)

        bottom_layout.addLayout(search_layout)

        # 搜尋範圍顯示
        self.lbl_search_scope = QLabel("搜尋範圍: (請勾選版區)")
        self.lbl_search_scope.setStyleSheet("color: #666; font-size: 11px;")
        self.lbl_search_scope.setWordWrap(True)
        self.lbl_search_scope.setMaximumHeight(40)
        bottom_layout.addWidget(self.lbl_search_scope)

        # 搜尋結果標題
        result_header = QHBoxLayout()

        self.lbl_result = QLabel("搜尋結果 (共 0 筆，已選 0 筆)")
        self.lbl_result.setFont(QFont("", 10, QFont.Weight.Bold))
        result_header.addWidget(self.lbl_result)

        result_header.addStretch()

        btn_select_all_results = QPushButton("全選結果")
        btn_select_all_results.clicked.connect(self._select_all_results)
        result_header.addWidget(btn_select_all_results)

        btn_clear_results = QPushButton("清除選擇")
        btn_clear_results.clicked.connect(self._clear_result_selection)
        result_header.addWidget(btn_clear_results)

        self.btn_open_link = QPushButton("開啟連結")
        self.btn_open_link.clicked.connect(self._open_checked_posts)
        self.btn_open_link.setEnabled(False)
        result_header.addWidget(self.btn_open_link)

        self.btn_download = QPushButton("下載選中")
        self.btn_download.clicked.connect(self._request_download)
        self.btn_download.setEnabled(False)
        result_header.addWidget(self.btn_download)

        bottom_layout.addLayout(result_header)

        # 搜尋結果表格 - 移除作者欄，加入版區與開版日期，支援排序
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(4)
        self.result_table.setHorizontalHeaderLabels(["選擇", "標題", "版區", "開版日期"])

        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        # 啟用排序
        self.result_table.setSortingEnabled(True)

        # 設定右鍵選單
        self.result_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.result_table.customContextMenuRequested.connect(self._show_context_menu)

        self.result_table.itemChanged.connect(self._on_result_selection_changed)
        self.result_table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.result_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        bottom_layout.addWidget(self.result_table)

        splitter.addWidget(bottom_widget)

        # 設定分割比例
        splitter.setSizes([400, 300])

        layout.addWidget(splitter)

    def _load_sections(self):
        """載入版區到樹狀結構"""
        self.tree.blockSignals(True)
        self.tree.clear()

        # 取得版區樹狀結構
        sections_tree = self.db.get_forum_sections_tree()

        # 取得設定中的版區設定
        section_settings = self.config.get('forum', {}).get('section_settings', {})

        # 遞迴建立樹狀結構
        for section in sections_tree:
            self._add_section_to_tree(section, None, section_settings)

        self.tree.expandAll()
        self.tree.blockSignals(False)

        # 更新分類下拉選單
        self._load_categories()

        # 更新最後同步時間
        last_updated = self.db.get_sections_last_updated()
        if last_updated:
            try:
                dt = datetime.fromisoformat(last_updated)
                self.lbl_last_sync.setText(f"最後同步: {dt.strftime('%Y-%m-%d %H:%M')}")
            except:
                self.lbl_last_sync.setText(f"最後同步: {last_updated[:16]}")
        else:
            self.lbl_last_sync.setText("最後同步: 從未")

    def _add_section_to_tree(self, section: Dict, parent_item: QTreeWidgetItem,
                             section_settings: Dict):
        """遞迴新增版區到樹狀結構"""
        fid = section['fid']
        name = section['name']
        settings = section_settings.get(fid, {})

        # 建立項目
        if parent_item:
            item = QTreeWidgetItem(parent_item)
        else:
            item = QTreeWidgetItem(self.tree)

        # 勾選框
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        enabled = settings.get('enabled', False)
        item.setCheckState(0, Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)

        # 版區名稱
        item.setText(1, name)

        # FID
        item.setText(2, fid)

        # 分類
        category = settings.get('category', '')
        item.setText(3, category)

        # 儲存 fid
        item.setData(0, Qt.ItemDataRole.UserRole, fid)

        # 遞迴處理子版區
        for child in section.get('children', []):
            self._add_section_to_tree(child, item, section_settings)

    def _load_categories(self):
        """載入分類列表"""
        categories = self.config.get('forum', {}).get('categories', ['我的最愛', '常用', '其它'])

        self.combo_category.blockSignals(True)
        self.combo_category.clear()
        self.combo_category.addItem("全部")
        for cat in categories:
            self.combo_category.addItem(cat)
        self.combo_category.blockSignals(False)

    def _apply_filter(self):
        """套用篩選"""
        filter_text = self.txt_filter.text().lower()
        category_filter = self.combo_category.currentText()

        def filter_item(item: QTreeWidgetItem) -> bool:
            child_visible = False
            for i in range(item.childCount()):
                if filter_item(item.child(i)):
                    child_visible = True

            name = item.text(1).lower()
            category = item.text(3)

            name_match = not filter_text or filter_text in name
            category_match = category_filter == "全部" or category == category_filter

            visible = (name_match and category_match) or child_visible
            item.setHidden(not visible)

            return visible

        for i in range(self.tree.topLevelItemCount()):
            filter_item(self.tree.topLevelItem(i))

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        """項目變更事件 - 級聯勾選"""
        if column == 0:
            self.tree.blockSignals(True)
            self._cascade_check_state(item)
            self.tree.blockSignals(False)
            self._update_selected_count()

    def _cascade_check_state(self, item: QTreeWidgetItem):
        """級聯設定子項目的勾選狀態"""
        check_state = item.checkState(0)
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, check_state)
            self._cascade_check_state(child)

    def _select_all(self):
        """全選可見項目"""
        def select_visible(item: QTreeWidgetItem):
            if not item.isHidden():
                item.setCheckState(0, Qt.CheckState.Checked)
            for i in range(item.childCount()):
                select_visible(item.child(i))

        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            select_visible(self.tree.topLevelItem(i))
        self.tree.blockSignals(False)
        self._update_selected_count()

    def _clear_all(self):
        """清除所有選擇"""
        def clear_item(item: QTreeWidgetItem):
            item.setCheckState(0, Qt.CheckState.Unchecked)
            for i in range(item.childCount()):
                clear_item(item.child(i))

        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            clear_item(self.tree.topLevelItem(i))
        self.tree.blockSignals(False)
        self._update_selected_count()

    def _update_selected_count(self):
        """更新已勾選數量顯示"""
        sections = self._get_selected_sections()
        self.lbl_selected_count.setText(f"已勾選: {len(sections)} 個版區")

    def _set_selected_category(self, category: str):
        """將已勾選的項目設定為指定分類並自動儲存（批量操作）"""
        count = 0

        def set_category(item: QTreeWidgetItem):
            nonlocal count
            if item.checkState(0) == Qt.CheckState.Checked:
                fid = item.data(0, Qt.ItemDataRole.UserRole)
                if fid and not str(fid).startswith('gid_') and not str(fid).startswith('cat_'):
                    item.setText(3, category)
                    count += 1
            for i in range(item.childCount()):
                set_category(item.child(i))

        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            set_category(self.tree.topLevelItem(i))
        self.tree.blockSignals(False)

        if count > 0:
            self._save_settings_silent()
            if category:
                QMessageBox.information(self, "完成", f"已將 {count} 個版區設為「{category}」並儲存")
            else:
                QMessageBox.information(self, "完成", f"已清除 {count} 個版區的分類並儲存")
        else:
            QMessageBox.warning(self, "提示", "請先勾選要設定分類的版區")

    def _show_section_context_menu(self, position):
        """顯示版區右鍵選單 - 管理單一版區的分類"""
        item = self.tree.itemAt(position)
        if not item:
            return

        fid = item.data(0, Qt.ItemDataRole.UserRole)
        if not fid or str(fid).startswith('gid_') or str(fid).startswith('cat_'):
            return  # 跳過分類項目

        current_category = item.text(3)
        section_name = item.text(1)

        menu = QMenu(self)
        menu.setTitle(f"版區: {section_name}")

        # 定義分類列表
        categories = [
            ("我的最愛", "★", "#d4a000"),
            ("常用", "◆", "#0066cc"),
            ("其它", "○", "#666666")
        ]

        for cat_name, icon, color in categories:
            if current_category == cat_name:
                # 已在此分類 - 顯示移出選項
                action = QAction(f"從「{cat_name}」移出", self)
                action.triggered.connect(lambda checked, i=item: self._set_item_category(i, ""))
            else:
                # 不在此分類 - 顯示加入選項
                action = QAction(f"{icon} 加入「{cat_name}」", self)
                action.triggered.connect(lambda checked, i=item, c=cat_name: self._set_item_category(i, c))
            menu.addAction(action)

        menu.addSeparator()

        # 清除分類
        if current_category:
            action_clear = QAction("✕ 清除分類", self)
            action_clear.triggered.connect(lambda: self._set_item_category(item, ""))
            menu.addAction(action_clear)

        # 顯示目前分類
        menu.addSeparator()
        if current_category:
            info_action = QAction(f"目前分類: {current_category}", self)
            info_action.setEnabled(False)
            menu.addAction(info_action)
        else:
            info_action = QAction("目前無分類", self)
            info_action.setEnabled(False)
            menu.addAction(info_action)

        menu.exec(QCursor.pos())

    def _set_item_category(self, item: QTreeWidgetItem, category: str):
        """設定單一版區的分類"""
        old_category = item.text(3)
        section_name = item.text(1)

        item.setText(3, category)
        self._save_settings_silent()

        if category:
            self.statusBar_message(f"已將「{section_name}」加入「{category}」")
        elif old_category:
            self.statusBar_message(f"已將「{section_name}」從「{old_category}」移出")

    def statusBar_message(self, msg: str):
        """顯示狀態列訊息（透過父視窗）"""
        parent = self.parent()
        while parent:
            if hasattr(parent, 'statusBar'):
                parent.statusBar().showMessage(msg, 3000)
                return
            parent = parent.parent()

    def _export_to_group(self):
        """匯出已勾選的版區"""
        sections = self._get_selected_sections()
        if sections:
            self.export_to_group_requested.emit(sections)
        else:
            QMessageBox.warning(self, "提示", "請先勾選要匯出的版區")

    def _get_selected_sections(self, visible_only: bool = False) -> List[Dict]:
        """
        取得已勾選的版區

        Args:
            visible_only: 是否只取得可見的版區（篩選後的）
        """
        sections = []

        def collect(item: QTreeWidgetItem):
            # 如果要求只取可見的，跳過隱藏的項目
            if visible_only and item.isHidden():
                return

            if item.checkState(0) == Qt.CheckState.Checked:
                fid = item.data(0, Qt.ItemDataRole.UserRole)
                if fid and not str(fid).startswith('gid_') and not str(fid).startswith('cat_'):
                    sections.append({
                        'fid': str(fid),
                        'name': item.text(1),
                        'category': item.text(3)
                    })
            for i in range(item.childCount()):
                collect(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            collect(self.tree.topLevelItem(i))

        return sections

    def _get_selected_fids(self, visible_only: bool = False) -> List[str]:
        """取得已勾選的版區 FID"""
        return [s['fid'] for s in self._get_selected_sections(visible_only)]

    def _get_selected_forum_names(self) -> Dict[str, str]:
        """取得已勾選版區的 FID -> 名稱 對應"""
        return {s['fid']: s['name'] for s in self._get_selected_sections(visible_only=True)}

    def _save_settings_silent(self):
        """儲存設定（不顯示訊息）"""
        section_settings = {}

        def collect_settings(item: QTreeWidgetItem):
            fid = item.data(0, Qt.ItemDataRole.UserRole)
            enabled = item.checkState(0) == Qt.CheckState.Checked
            category = item.text(3)

            if enabled or category:
                section_settings[fid] = {
                    'enabled': enabled,
                    'category': category
                }

            for i in range(item.childCount()):
                collect_settings(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            collect_settings(self.tree.topLevelItem(i))

        if 'forum' not in self.config:
            self.config['forum'] = {}
        self.config['forum']['section_settings'] = section_settings

        # 發送訊號讓 main_window 儲存到檔案
        self.settings_changed.emit()

    def _sync_sections(self):
        """同步版區結構"""
        if self.sync_worker and self.sync_worker.isRunning():
            QMessageBox.warning(self, "提示", "正在同步中...")
            return

        self.progress_dialog = QProgressDialog("準備同步...", "取消", 0, 0, self)
        self.progress_dialog.setWindowTitle("同步版區結構")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.show()

        self.sync_worker = SyncWorker(str(self.config_path))
        self.sync_worker.progress_signal.connect(self._on_sync_progress)
        self.sync_worker.finished_signal.connect(self._on_sync_finished)
        self.sync_worker.error_signal.connect(self._on_sync_error)
        self.sync_worker.start()

    def _on_sync_progress(self, message: str):
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.setLabelText(message)

    def _on_sync_finished(self, count: int):
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
        QMessageBox.information(self, "同步完成", f"已同步 {count} 個版區")
        self._load_sections()

    def _on_sync_error(self, error: str):
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
        QMessageBox.warning(self, "同步失敗", f"錯誤: {error}")

    # === 搜尋功能 ===

    def _do_search(self):
        """執行搜尋 - 只搜尋目前可見且勾選的版區"""
        keyword = self.txt_keyword.text().strip()
        if not keyword:
            QMessageBox.warning(self, "提示", "請輸入搜尋關鍵字")
            return

        # 只取得可見且勾選的版區
        selected_sections = self._get_selected_sections(visible_only=True)
        if not selected_sections:
            QMessageBox.warning(self, "提示", "請先勾選要搜尋的版區\n（提示：確認篩選條件是否正確）")
            return

        fids = [s['fid'] for s in selected_sections]

        if self.search_worker and self.search_worker.isRunning():
            QMessageBox.warning(self, "提示", "正在搜尋中...")
            return

        # 儲存搜尋範圍，用於過濾結果
        self._search_fids = set(fids)
        self._search_forum_names = {s['fid']: s['name'] for s in selected_sections}

        # 顯示搜尋範圍
        section_names = [s['name'] for s in selected_sections]
        if len(section_names) <= 5:
            scope_text = "、".join(section_names)
        else:
            scope_text = "、".join(section_names[:5]) + f"... 等 {len(section_names)} 個版區"
        self.lbl_search_scope.setText(f"搜尋範圍: {scope_text}")
        self.lbl_search_scope.setToolTip("搜尋範圍:\n" + "\n".join(section_names))

        self.btn_search.setEnabled(False)
        self.btn_search.setText("搜尋中...")
        self.result_table.setSortingEnabled(False)  # 暫時關閉排序以加快載入
        self.result_table.setRowCount(0)
        self.lbl_result.setText(f"正在搜尋 {len(fids)} 個版區...")

        self.search_worker = SearchWorker(str(self.config_path), keyword, fids)
        self.search_worker.progress_signal.connect(lambda msg: self.lbl_result.setText(msg))
        self.search_worker.result_signal.connect(self._on_search_result)
        self.search_worker.error_signal.connect(self._on_search_error)
        self.search_worker.start()

    def _on_search_result(self, results: list):
        """搜尋結果 - 過濾只顯示選取版區的結果"""
        self.btn_search.setEnabled(True)
        self.btn_search.setText("搜尋帖子")

        # 過濾結果：只保留在選取版區範圍內的結果
        filtered_results = []
        excluded_results = []  # 記錄被過濾的結果（用於除錯）
        search_fids = getattr(self, '_search_fids', set())
        search_forum_names = getattr(self, '_search_forum_names', {})

        # 記錄搜尋範圍（除錯用）
        logger.info(f"搜尋範圍 FIDs: {search_fids}")
        logger.info(f"搜尋範圍版區: {list(search_forum_names.values())}")

        for post in results:
            post_fid = str(post.get('fid', ''))
            post_forum_name = post.get('forum_name', '')
            matched = False
            match_reason = ''

            # 檢查是否在選取的版區範圍內
            # 方法1: 檢查 FID（優先）
            if post_fid and post_fid in search_fids:
                filtered_results.append(post)
                matched = True
                match_reason = f'FID匹配:{post_fid}'
            # 方法2: 檢查版區名稱（備用，需要嚴格匹配）
            elif post_forum_name:
                for fid, name in search_forum_names.items():
                    # 清理名稱進行比較
                    clean_result = post_forum_name.replace('『', '').replace('』', '').replace(' ', '').lower()
                    clean_selected = name.replace('『', '').replace('』', '').replace(' ', '').lower()
                    if clean_result == clean_selected:
                        filtered_results.append(post)
                        matched = True
                        match_reason = f'名稱匹配:{name}'
                        break

            if not matched:
                excluded_results.append({
                    'title': post.get('title', '')[:30],
                    'forum_name': post_forum_name,
                    'fid': post_fid
                })
            else:
                logger.debug(f"保留: [{post_forum_name}] FID:{post_fid} - {match_reason}")

        # 記錄被過濾的結果（除錯用）
        if excluded_results:
            logger.info(f"過濾掉 {len(excluded_results)} 筆非選取版區的結果:")
            for ex in excluded_results[:5]:  # 只顯示前5筆
                logger.info(f"  - [{ex['forum_name']}] (FID:{ex['fid']}) {ex['title']}")

        # 顯示過濾統計
        original_count = len(results)
        filtered_count = len(filtered_results)

        self.result_table.blockSignals(True)
        self.result_table.setRowCount(filtered_count)

        # 計算重複數量
        duplicate_count = 0

        for row, post in enumerate(filtered_results):
            tid = str(post.get('tid', ''))
            is_duplicate = tid in self.search_history

            if is_duplicate:
                duplicate_count += 1

            # 勾選框
            chk_item = QTableWidgetItem()
            chk_item.setFlags(chk_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            chk_item.setCheckState(Qt.CheckState.Unchecked)
            chk_item.setData(Qt.ItemDataRole.UserRole, post)
            self.result_table.setItem(row, 0, chk_item)

            # 標題
            title_item = QTableWidgetItem(post.get('title', ''))
            if is_duplicate:
                # 重複搜尋結果 - 標示醒目背景色
                title_item.setBackground(QBrush(QColor(255, 255, 150)))  # 淡黃色
                title_item.setToolTip("此帖子在之前的搜尋中已出現過")
            self.result_table.setItem(row, 1, title_item)

            # 版區
            forum_item = QTableWidgetItem(post.get('forum_name', ''))
            if is_duplicate:
                forum_item.setBackground(QBrush(QColor(255, 255, 150)))
            self.result_table.setItem(row, 2, forum_item)

            # 開版日期
            date_item = QTableWidgetItem(post.get('post_date', ''))
            if is_duplicate:
                date_item.setBackground(QBrush(QColor(255, 255, 150)))
            self.result_table.setItem(row, 3, date_item)

            # 將此次搜尋結果加入歷史
            if tid and tid not in self.search_history:
                self.search_history.append(tid)

        # 儲存搜尋歷史
        self._save_search_history()

        self.result_table.blockSignals(False)
        self.result_table.setSortingEnabled(True)  # 重新啟用排序

        # 更新結果計數，包含過濾與重複數量
        if original_count != filtered_count:
            # 有結果被過濾掉
            if duplicate_count > 0:
                self.lbl_result.setText(
                    f"搜尋結果 (共 {filtered_count} 筆，過濾 {original_count - filtered_count} 筆非選取版區，"
                    f"{duplicate_count} 筆重複，已選 0 筆)"
                )
            else:
                self.lbl_result.setText(
                    f"搜尋結果 (共 {filtered_count} 筆，過濾 {original_count - filtered_count} 筆非選取版區，已選 0 筆)"
                )
        elif duplicate_count > 0:
            self.lbl_result.setText(f"搜尋結果 (共 {filtered_count} 筆，{duplicate_count} 筆重複，已選 0 筆)")
        else:
            self._update_result_count()

    def _on_search_error(self, error: str):
        """搜尋錯誤"""
        self.btn_search.setEnabled(True)
        self.btn_search.setText("搜尋帖子")
        self.result_table.setSortingEnabled(True)
        self.lbl_result.setText("搜尋失敗")
        QMessageBox.warning(self, "搜尋失敗", error)

    def _on_result_selection_changed(self, item):
        """結果選擇變更"""
        if item.column() == 0:
            self._update_result_count()

    def _on_table_selection_changed(self):
        """表格選取變更"""
        # 不再用於控制按鈕狀態，改用勾選狀態
        pass

    def _on_cell_double_clicked(self, row: int, column: int):
        """雙擊儲存格 - 開啟帖子連結"""
        if column in [1, 2, 3]:  # 標題、版區、日期欄位
            item = self.result_table.item(row, 0)
            if item:
                post = item.data(Qt.ItemDataRole.UserRole)
                if post:
                    url = post.get('post_url', '')
                    if url:
                        webbrowser.open(url)

    def _show_context_menu(self, position):
        """顯示右鍵選單"""
        item = self.result_table.itemAt(position)
        if not item:
            return

        row = item.row()
        chk_item = self.result_table.item(row, 0)
        if not chk_item:
            return

        post = chk_item.data(Qt.ItemDataRole.UserRole)
        if not post:
            return

        menu = QMenu(self)

        # 開啟連結
        action_open = QAction("開啟帖子連結", self)
        action_open.triggered.connect(lambda: self._open_post_url(post.get('post_url', '')))
        menu.addAction(action_open)

        menu.addSeparator()

        # 選取/取消選取
        if chk_item.checkState() == Qt.CheckState.Checked:
            action_uncheck = QAction("取消選取", self)
            action_uncheck.triggered.connect(lambda: chk_item.setCheckState(Qt.CheckState.Unchecked))
            menu.addAction(action_uncheck)
        else:
            action_check = QAction("選取此項", self)
            action_check.triggered.connect(lambda: chk_item.setCheckState(Qt.CheckState.Checked))
            menu.addAction(action_check)

        menu.exec(QCursor.pos())

    def _open_post_url(self, url: str):
        """開啟帖子連結"""
        if url:
            webbrowser.open(url)

    def _open_checked_posts(self):
        """開啟已勾選的帖子連結"""
        opened = 0
        for row in range(self.result_table.rowCount()):
            item = self.result_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                post = item.data(Qt.ItemDataRole.UserRole)
                if post:
                    url = post.get('post_url', '')
                    if url:
                        webbrowser.open(url)
                        opened += 1

        if opened == 0:
            QMessageBox.information(self, "提示", "沒有可開啟的連結")

    def _update_result_count(self):
        """更新結果計數"""
        total = self.result_table.rowCount()
        selected = 0
        duplicate = 0

        for row in range(total):
            item = self.result_table.item(row, 0)
            if item:
                if item.checkState() == Qt.CheckState.Checked:
                    selected += 1
                # 檢查是否為重複項（背景色）
                title_item = self.result_table.item(row, 1)
                if title_item and title_item.background().color() == QColor(255, 255, 150):
                    duplicate += 1

        if duplicate > 0:
            self.lbl_result.setText(f"搜尋結果 (共 {total} 筆，{duplicate} 筆重複，已選 {selected} 筆)")
        else:
            self.lbl_result.setText(f"搜尋結果 (共 {total} 筆，已選 {selected} 筆)")

        self.btn_download.setEnabled(selected > 0)
        self.btn_open_link.setEnabled(selected > 0)

    def _select_all_results(self):
        """全選結果"""
        self.result_table.blockSignals(True)
        for row in range(self.result_table.rowCount()):
            item = self.result_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)
        self.result_table.blockSignals(False)
        self._update_result_count()

    def _clear_result_selection(self):
        """清除結果選擇"""
        self.result_table.blockSignals(True)
        for row in range(self.result_table.rowCount()):
            item = self.result_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)
        self.result_table.blockSignals(False)
        self._update_result_count()

    def _request_download(self):
        """請求下載"""
        selected_posts = []
        for row in range(self.result_table.rowCount()):
            item = self.result_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                post = item.data(Qt.ItemDataRole.UserRole)
                if post:
                    selected_posts.append(post)

        if selected_posts:
            self.download_requested.emit(selected_posts)

    def get_enabled_sections(self) -> List[Dict]:
        """取得已啟用的版區列表 (從設定)"""
        section_settings = self.config.get('forum', {}).get('section_settings', {})
        enabled_sections = []

        all_sections = self.db.get_all_forum_sections()
        for section in all_sections:
            fid = section['fid']
            settings = section_settings.get(fid, {})
            if settings.get('enabled', False):
                enabled_sections.append({
                    'fid': fid,
                    'name': section['name']
                })

        return enabled_sections

    def clear_search_history(self):
        """清除搜尋歷史"""
        self.search_history = []
        self._save_search_history()
        QMessageBox.information(self, "完成", "搜尋歷史已清除")
