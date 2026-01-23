"""
版區管理元件
管理論壇版區的啟用/停用、分類設定
"""
from typing import Dict, List, Optional
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QComboBox, QLineEdit, QGroupBox, QMessageBox,
    QHeaderView, QInputDialog, QProgressDialog, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont

from ..database.db_manager import DatabaseManager
from ..utils.logger import logger


class SyncWorker(QThread):
    """同步版區結構的工作執行緒"""
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int)  # 回傳儲存的版區數量
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


class SectionManagerWidget(QWidget):
    """版區管理元件"""

    # 訊號
    settings_changed = pyqtSignal()
    export_to_group_requested = pyqtSignal(list)  # 匯出到版區群組

    def __init__(self, config: dict, config_path: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.config_path = config_path
        self.db = DatabaseManager()
        self.sync_worker = None

        self._init_ui()
        self._load_data()

    def _init_ui(self):
        """初始化介面"""
        layout = QVBoxLayout(self)

        # 頂部工具列
        toolbar = QHBoxLayout()

        # 分類篩選
        toolbar.addWidget(QLabel("分類篩選:"))
        self.combo_category_filter = QComboBox()
        self.combo_category_filter.addItem("全部")
        self.combo_category_filter.currentTextChanged.connect(self._apply_filter)
        toolbar.addWidget(self.combo_category_filter)

        # 搜尋
        toolbar.addWidget(QLabel("搜尋:"))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("輸入版區名稱...")
        self.txt_search.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.txt_search)

        toolbar.addStretch()

        # 同步按鈕
        self.btn_sync = QPushButton("同步版區結構")
        self.btn_sync.clicked.connect(self._sync_sections)
        toolbar.addWidget(self.btn_sync)

        layout.addLayout(toolbar)

        # 版區樹狀結構
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["啟用", "版區名稱", "FID", "分類", "帖子數"])
        self.tree.setColumnCount(5)

        # 設定欄寬
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        layout.addWidget(self.tree)

        # 快速操作
        action_group = QGroupBox("快速操作")
        action_layout = QHBoxLayout(action_group)

        action_layout.addWidget(QLabel("將勾選項目設為:"))

        btn_set_favorite = QPushButton("我的最愛")
        btn_set_favorite.clicked.connect(lambda: self._set_selected_category("我的最愛"))
        action_layout.addWidget(btn_set_favorite)

        btn_set_common = QPushButton("常用")
        btn_set_common.clicked.connect(lambda: self._set_selected_category("常用"))
        action_layout.addWidget(btn_set_common)

        btn_set_other = QPushButton("其他")
        btn_set_other.clicked.connect(lambda: self._set_selected_category("其他"))
        action_layout.addWidget(btn_set_other)

        action_layout.addStretch()

        btn_export_group = QPushButton("匯出到版區群組")
        btn_export_group.setToolTip("將已勾選的版區匯出到「版區群組」分頁")
        btn_export_group.clicked.connect(self._export_to_section_group)
        action_layout.addWidget(btn_export_group)

        layout.addWidget(action_group)

        # 分類管理
        category_group = QGroupBox("分類管理")
        category_layout = QHBoxLayout(category_group)

        self.lbl_categories = QLabel()
        category_layout.addWidget(self.lbl_categories)

        category_layout.addStretch()

        btn_add_category = QPushButton("新增分類")
        btn_add_category.clicked.connect(self._add_category)
        category_layout.addWidget(btn_add_category)

        btn_remove_category = QPushButton("移除分類")
        btn_remove_category.clicked.connect(self._remove_category)
        category_layout.addWidget(btn_remove_category)

        layout.addWidget(category_group)

        # 底部資訊
        bottom_layout = QHBoxLayout()

        self.lbl_last_sync = QLabel("最後同步: 從未")
        bottom_layout.addWidget(self.lbl_last_sync)

        bottom_layout.addStretch()

        btn_save = QPushButton("儲存設定")
        btn_save.clicked.connect(self._save_settings)
        bottom_layout.addWidget(btn_save)

        layout.addLayout(bottom_layout)

    def _load_data(self):
        """載入資料"""
        # 載入版區結構
        self._load_sections()

        # 載入分類列表
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
            self.lbl_last_sync.setText("最後同步: 從未 (請點擊「同步版區結構」)")

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

        # 啟用勾選框
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

        # 帖子數
        post_count = section.get('post_count')
        item.setText(4, str(post_count) if post_count else '')

        # 儲存 fid 到 item data
        item.setData(0, Qt.ItemDataRole.UserRole, fid)

        # 遞迴處理子版區
        for child in section.get('children', []):
            self._add_section_to_tree(child, item, section_settings)

    def _load_categories(self):
        """載入分類列表"""
        categories = self.config.get('forum', {}).get('categories', ['我的最愛', '常用', '其他'])

        # 更新下拉選單
        self.combo_category_filter.blockSignals(True)
        self.combo_category_filter.clear()
        self.combo_category_filter.addItem("全部")
        for cat in categories:
            self.combo_category_filter.addItem(cat)
        self.combo_category_filter.blockSignals(False)

        # 更新標籤
        self.lbl_categories.setText(f"分類: {', '.join(categories)}")

    def _apply_filter(self):
        """套用篩選"""
        category_filter = self.combo_category_filter.currentText()
        search_text = self.txt_search.text().lower()

        def filter_item(item: QTreeWidgetItem) -> bool:
            """遞迴篩選項目"""
            # 檢查子項目
            child_visible = False
            for i in range(item.childCount()):
                if filter_item(item.child(i)):
                    child_visible = True

            # 檢查自身
            name = item.text(1).lower()
            category = item.text(3)

            name_match = not search_text or search_text in name
            category_match = category_filter == "全部" or category == category_filter

            visible = (name_match and category_match) or child_visible
            item.setHidden(not visible)

            return visible

        # 套用篩選到所有頂層項目
        for i in range(self.tree.topLevelItemCount()):
            filter_item(self.tree.topLevelItem(i))

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        """項目變更事件"""
        if column == 0:  # 啟用勾選框
            # 級聯勾選：父系勾選時子系也自動勾選
            self.tree.blockSignals(True)
            self._cascade_check_state(item)
            self.tree.blockSignals(False)
            self.settings_changed.emit()

    def _cascade_check_state(self, item: QTreeWidgetItem):
        """級聯設定子項目的勾選狀態"""
        check_state = item.checkState(0)
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, check_state)
            # 遞迴處理子項目的子項目
            self._cascade_check_state(child)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """項目雙擊事件 - 編輯分類"""
        if column == 3:  # 分類欄位
            self._edit_item_category(item)

    def _edit_item_category(self, item: QTreeWidgetItem):
        """編輯項目分類"""
        categories = self.config.get('forum', {}).get('categories', ['我的最愛', '常用', '其他'])
        current_category = item.text(3)

        # 顯示選擇對話框
        category, ok = QInputDialog.getItem(
            self, "選擇分類",
            f"為「{item.text(1)}」選擇分類:",
            ['(無)'] + categories,
            categories.index(current_category) + 1 if current_category in categories else 0,
            False
        )

        if ok:
            new_category = '' if category == '(無)' else category
            item.setText(3, new_category)
            self.settings_changed.emit()

    def _sync_sections(self):
        """同步版區結構"""
        if self.sync_worker and self.sync_worker.isRunning():
            QMessageBox.warning(self, "提示", "正在同步中，請稍候...")
            return

        # 建立進度對話框
        self.progress_dialog = QProgressDialog("準備同步...", "取消", 0, 0, self)
        self.progress_dialog.setWindowTitle("同步版區結構")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.show()

        # 建立工作執行緒
        self.sync_worker = SyncWorker(str(self.config_path))
        self.sync_worker.progress_signal.connect(self._on_sync_progress)
        self.sync_worker.finished_signal.connect(self._on_sync_finished)
        self.sync_worker.error_signal.connect(self._on_sync_error)
        self.sync_worker.start()

    def _on_sync_progress(self, message: str):
        """同步進度更新"""
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.setLabelText(message)

    def _on_sync_finished(self, count: int):
        """同步完成"""
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()

        QMessageBox.information(self, "同步完成", f"已同步 {count} 個版區")
        self._load_data()

    def _on_sync_error(self, error: str):
        """同步錯誤"""
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()

        QMessageBox.warning(self, "同步失敗", f"錯誤: {error}")

    def _add_category(self):
        """新增分類"""
        name, ok = QInputDialog.getText(self, "新增分類", "請輸入分類名稱:")
        if ok and name:
            categories = self.config.get('forum', {}).get('categories', [])
            if name not in categories:
                categories.append(name)
                if 'forum' not in self.config:
                    self.config['forum'] = {}
                self.config['forum']['categories'] = categories
                self._load_categories()
                self.settings_changed.emit()
            else:
                QMessageBox.warning(self, "錯誤", "分類已存在")

    def _remove_category(self):
        """移除分類"""
        categories = self.config.get('forum', {}).get('categories', [])
        if not categories:
            return

        category, ok = QInputDialog.getItem(
            self, "移除分類", "選擇要移除的分類:",
            categories, 0, False
        )

        if ok and category:
            categories.remove(category)
            self.config['forum']['categories'] = categories
            self._load_categories()
            self.settings_changed.emit()

    def _save_settings(self):
        """儲存設定"""
        section_settings = {}

        def collect_settings(item: QTreeWidgetItem):
            """遞迴收集設定"""
            fid = item.data(0, Qt.ItemDataRole.UserRole)
            enabled = item.checkState(0) == Qt.CheckState.Checked
            category = item.text(3)

            # 只儲存有設定的項目
            if enabled or category:
                section_settings[fid] = {
                    'enabled': enabled,
                    'category': category
                }

            # 遞迴處理子項目
            for i in range(item.childCount()):
                collect_settings(item.child(i))

        # 收集所有項目的設定
        for i in range(self.tree.topLevelItemCount()):
            collect_settings(self.tree.topLevelItem(i))

        # 更新設定
        if 'forum' not in self.config:
            self.config['forum'] = {}
        self.config['forum']['section_settings'] = section_settings

        self.settings_changed.emit()
        QMessageBox.information(self, "儲存成功", "版區設定已儲存")

    def get_enabled_sections(self) -> List[Dict]:
        """取得已啟用的版區列表"""
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

    def _set_selected_category(self, category: str):
        """將已勾選的項目設定為指定分類"""
        count = 0

        def set_category_recursive(item: QTreeWidgetItem):
            nonlocal count
            if item.checkState(0) == Qt.CheckState.Checked:
                # 只設定實際的版區 (非分類)
                fid = item.data(0, Qt.ItemDataRole.UserRole)
                if fid and not str(fid).startswith('gid_') and not str(fid).startswith('cat_'):
                    item.setText(3, category)
                    count += 1

            for i in range(item.childCount()):
                set_category_recursive(item.child(i))

        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            set_category_recursive(self.tree.topLevelItem(i))
        self.tree.blockSignals(False)

        if count > 0:
            self.settings_changed.emit()
            QMessageBox.information(self, "完成", f"已將 {count} 個版區設為「{category}」")
        else:
            QMessageBox.warning(self, "提示", "請先勾選要設定的版區")

    def _export_to_section_group(self):
        """匯出已勾選的版區到版區群組"""
        enabled_sections = []

        def collect_enabled(item: QTreeWidgetItem):
            if item.checkState(0) == Qt.CheckState.Checked:
                fid = item.data(0, Qt.ItemDataRole.UserRole)
                name = item.text(1)
                # 只收集實際的版區 (非分類)
                if fid and not str(fid).startswith('gid_') and not str(fid).startswith('cat_'):
                    enabled_sections.append({
                        'fid': str(fid),
                        'name': name
                    })

            for i in range(item.childCount()):
                collect_enabled(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            collect_enabled(self.tree.topLevelItem(i))

        if enabled_sections:
            self.export_to_group_requested.emit(enabled_sections)
        else:
            QMessageBox.warning(self, "提示", "請先勾選要匯出的版區")

    def get_enabled_sections_from_tree(self) -> List[Dict]:
        """從樹狀結構取得已勾選的版區列表 (用於版區搜尋)"""
        enabled_sections = []

        def collect_enabled(item: QTreeWidgetItem):
            if item.checkState(0) == Qt.CheckState.Checked:
                fid = item.data(0, Qt.ItemDataRole.UserRole)
                name = item.text(1)
                # 只收集實際的版區 (非分類)
                if fid and not str(fid).startswith('gid_') and not str(fid).startswith('cat_'):
                    enabled_sections.append({
                        'fid': str(fid),
                        'name': name
                    })

            for i in range(item.childCount()):
                collect_enabled(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            collect_enabled(self.tree.topLevelItem(i))

        return enabled_sections
