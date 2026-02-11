"""
DLP01 GUI 主視窗
使用 PyQt6 建立的圖形介面
"""
import sys
import os
import threading
from pathlib import Path
from typing import Optional, List, Dict

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QTextEdit, QGroupBox,
    QTabWidget, QFileDialog, QMessageBox, QListWidget, QListWidgetItem,
    QCheckBox, QComboBox, QProgressBar, QStatusBar, QMenuBar, QMenu,
    QSplitter, QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QDialogButtonBox, QInputDialog, QTreeWidget, QTreeWidgetItem,
    QScrollArea, QSystemTrayIcon, QToolTip
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QFont, QTextCursor, QIcon, QColor, QBrush

import yaml

from .extract_settings_widget import ExtractSettingsWidget
from .notifications import NotificationManager
from .download_history_widget import DownloadTimesDialog
from .section_search_manager_widget import SectionSearchManagerWidget
from .search_download_worker import SearchDownloadWorker
from .web_download_widget import WebDownloadWidget
from .workers import CrawlerWorker, ExtractWorker
from .tag_widget import TagWidget
from .styles import HINT_LABEL, DANGER_BUTTON, NordColors


class MainWindow(QMainWindow):
    """主視窗"""

    def __init__(self):
        super().__init__()

        # 設定視窗屬性 - 確保可拖曳、縮放、關閉
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        # 初始化設定檔管理器
        from ..utils.profile_manager import ProfileManager
        self.profile_manager = ProfileManager()

        # 載入目前設定檔
        self.current_profile = self.profile_manager.get_current_profile()
        self.config_path = self.profile_manager.get_profile_config_path()
        self.config = self._load_config()

        self.crawler_worker: Optional[CrawlerWorker] = None
        self.extract_worker: Optional[ExtractWorker] = None
        self.search_download_worker: Optional[SearchDownloadWorker] = None

        # 初始化通知管理器
        self.notification_manager = NotificationManager("DLP01", self)

        # 初始化 JD 狀態輪詢器
        self.jd_poller = None

        # 追蹤當次爬取的連結數量
        self._current_crawl_links: List[Dict] = []

        # 延遲載入追蹤 - 記錄哪些分頁已載入資料
        self._tabs_loaded: Dict[str, bool] = {}

        self._init_ui()
        self._load_settings_to_ui()
        self._update_window_title()

        # 設定通知管理器的狀態列
        self.notification_manager.set_statusbar(self.statusBar())

        # 延遲 3 秒後檢查更新 (讓視窗先完成載入)
        QTimer.singleShot(3000, self._check_for_updates_startup)

    def _load_config(self) -> dict:
        """載入設定檔"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception:
            return {}

    def _save_config(self):
        """儲存設定檔"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
            self.statusBar().showMessage("設定已儲存", 3000)
        except Exception as e:
            QMessageBox.warning(self, "錯誤", f"儲存設定失敗: {e}")

    def _update_window_title(self):
        """更新視窗標題"""
        from ..version import get_window_title
        self.setWindowTitle(get_window_title(self.current_profile))

    def _init_ui(self):
        """初始化介面"""
        self.setMinimumSize(900, 700)

        # 主要 Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主佈局
        main_layout = QVBoxLayout(central_widget)

        # 設定檔選擇區
        profile_group = QGroupBox("設定檔")
        profile_layout = QHBoxLayout(profile_group)

        profile_layout.addWidget(QLabel("目前設定檔:"))

        self.combo_profile = QComboBox()
        self.combo_profile.setMinimumWidth(150)
        self._refresh_profile_list()
        self.combo_profile.currentTextChanged.connect(self._on_profile_changed)
        profile_layout.addWidget(self.combo_profile)

        btn_new_profile = QPushButton("新增")
        btn_new_profile.clicked.connect(self._create_new_profile)
        profile_layout.addWidget(btn_new_profile)

        btn_copy_profile = QPushButton("複製")
        btn_copy_profile.clicked.connect(self._copy_profile)
        profile_layout.addWidget(btn_copy_profile)

        btn_rename_profile = QPushButton("重命名")
        btn_rename_profile.clicked.connect(self._rename_profile)
        profile_layout.addWidget(btn_rename_profile)

        btn_delete_profile = QPushButton("刪除")
        btn_delete_profile.clicked.connect(self._delete_profile)
        profile_layout.addWidget(btn_delete_profile)

        profile_layout.addStretch()

        main_layout.addWidget(profile_group)

        # 建立分頁
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # 分頁 1: 主控制台
        self.tabs.addTab(self._create_main_tab(), "主控制台")

        # 分頁 2: 路徑設定
        self.tabs.addTab(self._create_paths_tab(), "路徑設定")

        # 分頁 3: 版區搜尋管理 (整合版區管理和搜尋)
        self.section_search_manager_widget = SectionSearchManagerWidget(
            config=self.config,
            config_path=self.config_path
        )
        self.section_search_manager_widget.settings_changed.connect(self._on_section_settings_changed)
        self.section_search_manager_widget.export_to_group_requested.connect(self._on_export_to_section_group)
        self.section_search_manager_widget.download_requested.connect(self._on_search_download_requested)
        self.tabs.addTab(self.section_search_manager_widget, "版區搜尋管理")

        # 分頁 4: 版區群組 (原有的群組管理)
        self.tabs.addTab(self._create_sections_tab(), "版區群組")

        # 分頁 5: 下載關鍵字
        self.tabs.addTab(self._create_keywords_tab(), "下載關鍵字")

        # 分頁 6: 下載歷史
        self.tabs.addTab(self._create_history_tab(), "下載歷史")

        # 分頁 6: 網頁下載
        self.web_download_widget = WebDownloadWidget(config_path=str(self.config_path))
        self.tabs.addTab(self.web_download_widget, "網頁下載")

        # 分頁 7: 解壓縮設定
        self.tabs.addTab(self._create_extract_settings_tab(), "解壓縮設定")

        # 分頁 9: 進階設定
        self.tabs.addTab(self._create_advanced_tab(), "進階設定")

        # 連接分頁切換信號 - 延遲載入
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # 狀態列
        self.statusBar().showMessage("就緒")

        # 選單
        self._create_menu()

    def _create_menu(self):
        """建立選單"""
        menubar = self.menuBar()

        # 檔案選單
        file_menu = menubar.addMenu("檔案")

        save_action = QAction("儲存設定", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_config)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        exit_action = QAction("結束", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 操作選單
        action_menu = menubar.addMenu("操作")

        start_crawler_action = QAction("開始爬取", self)
        start_crawler_action.setShortcut("F5")
        start_crawler_action.triggered.connect(self._start_crawler)
        action_menu.addAction(start_crawler_action)

        stop_crawler_action = QAction("停止爬取", self)
        stop_crawler_action.setShortcut("Escape")
        stop_crawler_action.triggered.connect(self._stop_crawler)
        action_menu.addAction(stop_crawler_action)

        action_menu.addSeparator()

        start_extract_action = QAction("監控解壓", self)
        start_extract_action.setShortcut("F6")
        start_extract_action.triggered.connect(self._start_extract_monitor)
        action_menu.addAction(start_extract_action)

        stop_extract_action = QAction("停止解壓", self)
        stop_extract_action.triggered.connect(self._stop_extract_monitor)
        action_menu.addAction(stop_extract_action)

        action_menu.addSeparator()

        refresh_action = QAction("重新整理歷史", self)
        refresh_action.setShortcut("Ctrl+R")
        refresh_action.triggered.connect(self._refresh_history)
        action_menu.addAction(refresh_action)

        # 說明選單
        help_menu = menubar.addMenu("說明")

        check_update_action = QAction("檢查更新", self)
        check_update_action.triggered.connect(self._check_for_updates_manual)
        help_menu.addAction(check_update_action)

        help_menu.addSeparator()

        about_action = QAction("關於", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _on_tab_changed(self, index: int):
        """分頁切換時的處理 - 延遲載入"""
        tab_name = self.tabs.tabText(index)

        # 如果此分頁尚未載入資料，則載入
        if tab_name not in self._tabs_loaded:
            self._tabs_loaded[tab_name] = True

            # 根據分頁名稱載入對應資料
            if tab_name == "下載歷史":
                self._refresh_history()
            elif tab_name == "網頁下載":
                if hasattr(self, 'web_download_widget'):
                    self.web_download_widget.load_data()

    def _create_main_tab(self) -> QWidget:
        """建立主控制台分頁"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 上方控制區
        control_group = QGroupBox("控制面板")
        control_layout = QHBoxLayout(control_group)

        # 爬蟲控制
        crawler_frame = QFrame()
        crawler_layout = QVBoxLayout(crawler_frame)

        crawler_label = QLabel("論壇爬蟲")
        crawler_label.setFont(QFont("", 12, QFont.Weight.Bold))
        crawler_layout.addWidget(crawler_label)

        self.btn_start_crawler = QPushButton("開始爬取")
        self.btn_start_crawler.setMinimumHeight(40)
        self.btn_start_crawler.clicked.connect(self._start_crawler)
        crawler_layout.addWidget(self.btn_start_crawler)

        self.btn_stop_crawler = QPushButton("停止爬取")
        self.btn_stop_crawler.setMinimumHeight(40)
        self.btn_stop_crawler.setEnabled(False)
        self.btn_stop_crawler.clicked.connect(self._stop_crawler)
        crawler_layout.addWidget(self.btn_stop_crawler)

        self.chk_dry_run = QCheckBox("試執行模式 (不實際感謝/下載)")
        crawler_layout.addWidget(self.chk_dry_run)

        self.chk_redownload_thanked = QCheckBox("已感謝帖子仍嘗試下載")
        self.chk_redownload_thanked.setToolTip("勾選後會重新下載曾經感謝過的帖子連結")
        crawler_layout.addWidget(self.chk_redownload_thanked)

        self.crawler_status = QLabel("狀態: 閒置")
        crawler_layout.addWidget(self.crawler_status)

        control_layout.addWidget(crawler_frame)

        # 分隔線
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        control_layout.addWidget(line)

        # 解壓監控控制
        extract_frame = QFrame()
        extract_layout = QVBoxLayout(extract_frame)

        extract_label = QLabel("解壓監控")
        extract_label.setFont(QFont("", 12, QFont.Weight.Bold))
        extract_layout.addWidget(extract_label)

        self.btn_start_extract = QPushButton("監控解壓")
        self.btn_start_extract.setMinimumHeight(40)
        self.btn_start_extract.clicked.connect(self._start_extract_monitor)
        extract_layout.addWidget(self.btn_start_extract)

        self.btn_stop_extract = QPushButton("停止")
        self.btn_stop_extract.setMinimumHeight(40)
        self.btn_stop_extract.setEnabled(False)
        self.btn_stop_extract.clicked.connect(self._stop_extract_monitor)
        extract_layout.addWidget(self.btn_stop_extract)

        self.extract_status = QLabel("狀態: 閒置")
        extract_layout.addWidget(self.extract_status)

        control_layout.addWidget(extract_frame)

        layout.addWidget(control_group)

        # 統計資訊
        stats_group = QGroupBox("統計資訊")
        stats_layout = QGridLayout(stats_group)

        self.lbl_posts_found = QLabel("找到帖子: 0")
        self.lbl_posts_new = QLabel("新帖子: 0")
        self.lbl_thanks_sent = QLabel("感謝成功: 0")
        self.lbl_links_extracted = QLabel("提取連結: 0")

        stats_layout.addWidget(self.lbl_posts_found, 0, 0)
        stats_layout.addWidget(self.lbl_posts_new, 0, 1)
        stats_layout.addWidget(self.lbl_thanks_sent, 1, 0)
        stats_layout.addWidget(self.lbl_links_extracted, 1, 1)

        layout.addWidget(stats_group)

        # 日誌區域
        log_group = QGroupBox("執行日誌")
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_text)

        btn_clear_log = QPushButton("清除日誌")
        btn_clear_log.clicked.connect(lambda: self.log_text.clear())
        log_layout.addWidget(btn_clear_log)

        layout.addWidget(log_group)

        return tab

    def _create_paths_tab(self) -> QWidget:
        """建立路徑設定分頁"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 路徑設定
        paths_group = QGroupBox("目錄設定")
        paths_layout = QGridLayout(paths_group)

        # 下載目錄
        paths_layout.addWidget(QLabel("下載目錄:"), 0, 0)
        self.txt_download_dir = QLineEdit()
        paths_layout.addWidget(self.txt_download_dir, 0, 1)
        btn_download_dir = QPushButton("瀏覽...")
        btn_download_dir.clicked.connect(lambda: self._browse_dir(self.txt_download_dir))
        paths_layout.addWidget(btn_download_dir, 0, 2)

        # 解壓目錄
        paths_layout.addWidget(QLabel("解壓目錄:"), 1, 0)
        self.txt_extract_dir = QLineEdit()
        paths_layout.addWidget(self.txt_extract_dir, 1, 1)
        btn_extract_dir = QPushButton("瀏覽...")
        btn_extract_dir.clicked.connect(lambda: self._browse_dir(self.txt_extract_dir))
        paths_layout.addWidget(btn_extract_dir, 1, 2)

        layout.addWidget(paths_group)

        # 程式路徑
        programs_group = QGroupBox("程式路徑")
        programs_layout = QGridLayout(programs_group)

        # WinRAR
        programs_layout.addWidget(QLabel("WinRAR:"), 0, 0)
        self.txt_winrar_path = QLineEdit()
        programs_layout.addWidget(self.txt_winrar_path, 0, 1)
        btn_winrar = QPushButton("瀏覽...")
        btn_winrar.clicked.connect(lambda: self._browse_file(self.txt_winrar_path, "WinRAR (*.exe)"))
        programs_layout.addWidget(btn_winrar, 0, 2)

        # JDownloader 主程式
        programs_layout.addWidget(QLabel("JDownloader 主程式:"), 1, 0)
        self.txt_jd_exe = QLineEdit()
        self.txt_jd_exe.setPlaceholderText("JDownloader2.exe 路徑 (可選，用於自動啟動)")
        programs_layout.addWidget(self.txt_jd_exe, 1, 1)
        btn_jd_exe = QPushButton("瀏覽...")
        btn_jd_exe.clicked.connect(lambda: self._browse_file(self.txt_jd_exe, "JDownloader (*.exe)"))
        programs_layout.addWidget(btn_jd_exe, 1, 2)

        # JDownloader FolderWatch
        programs_layout.addWidget(QLabel("JDownloader Folderwatch:"), 2, 0)
        self.txt_jd_folderwatch = QLineEdit()
        programs_layout.addWidget(self.txt_jd_folderwatch, 2, 1)
        btn_jd = QPushButton("瀏覽...")
        btn_jd.clicked.connect(lambda: self._browse_dir(self.txt_jd_folderwatch))
        programs_layout.addWidget(btn_jd, 2, 2)

        # 自動啟動選項
        self.chk_auto_start_jd = QCheckBox("開始爬取時自動啟動 JDownloader (如果未執行)")
        self.chk_auto_start_jd.setChecked(True)
        programs_layout.addWidget(self.chk_auto_start_jd, 3, 0, 1, 3)

        # SMG 主程式
        programs_layout.addWidget(QLabel("SMG 主程式:"), 4, 0)
        self.txt_smg_exe = QLineEdit()
        self.txt_smg_exe.setPlaceholderText("SimpleMediaGrabber.exe 路徑 (用於某些雲端空間下載)")
        programs_layout.addWidget(self.txt_smg_exe, 4, 1)
        btn_smg_exe = QPushButton("瀏覽...")
        btn_smg_exe.clicked.connect(lambda: self._browse_file(self.txt_smg_exe, "SMG (*.exe)"))
        programs_layout.addWidget(btn_smg_exe, 4, 2)

        # SMG 下載目錄
        programs_layout.addWidget(QLabel("SMG 下載目錄:"), 5, 0)
        self.txt_smg_download_dir = QLineEdit()
        self.txt_smg_download_dir.setPlaceholderText("SMG 下載檔案儲存目錄 (可選)")
        programs_layout.addWidget(self.txt_smg_download_dir, 5, 1)
        btn_smg_dir = QPushButton("瀏覽...")
        btn_smg_dir.clicked.connect(lambda: self._browse_dir(self.txt_smg_download_dir))
        programs_layout.addWidget(btn_smg_dir, 5, 2)

        layout.addWidget(programs_group)

        # Cookie 設定
        cookie_group = QGroupBox("登入 Cookie 設定")
        cookie_layout = QVBoxLayout(cookie_group)

        cookie_info = QLabel("貼上從瀏覽器導出的 Cookie (JSON 格式):")
        cookie_layout.addWidget(cookie_info)

        self.txt_cookie = QTextEdit()
        self.txt_cookie.setPlaceholderText(
            '[\n'
            '  {"name": "cookie_name", "value": "cookie_value", "domain": ".example.com"},\n'
            '  ...\n'
            ']\n\n'
            '或使用 EditThisCookie 等擴充功能導出的 JSON 格式'
        )
        self.txt_cookie.setMaximumHeight(150)
        cookie_layout.addWidget(self.txt_cookie)

        cookie_btn_layout = QHBoxLayout()

        btn_load_cookie = QPushButton("載入現有 Cookie")
        btn_load_cookie.clicked.connect(self._load_cookie_file)
        cookie_btn_layout.addWidget(btn_load_cookie)

        btn_import_browser = QPushButton("從瀏覽器自動導入")
        btn_import_browser.clicked.connect(self._import_cookie_from_browser)
        cookie_btn_layout.addWidget(btn_import_browser)

        btn_save_cookie = QPushButton("儲存 Cookie")
        btn_save_cookie.clicked.connect(self._save_cookie)
        cookie_btn_layout.addWidget(btn_save_cookie)

        btn_test_cookie = QPushButton("測試登入狀態")
        btn_test_cookie.clicked.connect(self._test_cookie)
        cookie_btn_layout.addWidget(btn_test_cookie)

        cookie_layout.addLayout(cookie_btn_layout)

        self.lbl_cookie_status = QLabel("Cookie 狀態: 未知")
        cookie_layout.addWidget(self.lbl_cookie_status)

        layout.addWidget(cookie_group)

        # 儲存按鈕
        btn_save = QPushButton("儲存所有設定")
        btn_save.clicked.connect(self._save_paths_settings)
        layout.addWidget(btn_save)

        layout.addStretch()

        return tab

    def _create_sections_tab(self) -> QWidget:
        """建立版區設定分頁 (支援群組化與暫停功能)"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 版區群組樹狀結構
        sections_group = QGroupBox("目標版區 (群組管理)")
        sections_layout = QVBoxLayout(sections_group)

        # 說明文字
        info_label = QLabel("✓ 已啟用  ✗ 已暫停  |  勾選群組會同時影響其下所有版區")
        info_label.setStyleSheet(HINT_LABEL)
        sections_layout.addWidget(info_label)

        # 樹狀結構顯示群組和版區
        self.tree_sections = QTreeWidget()
        self.tree_sections.setHeaderLabels(["名稱", "FID", "狀態"])
        self.tree_sections.setColumnWidth(0, 250)
        self.tree_sections.setColumnWidth(1, 60)
        self.tree_sections.setColumnWidth(2, 60)
        self.tree_sections.itemChanged.connect(self._on_section_item_changed)
        sections_layout.addWidget(self.tree_sections)

        # 群組操作按鈕
        group_btn_layout = QHBoxLayout()

        btn_add_group = QPushButton("新增群組")
        btn_add_group.clicked.connect(self._add_section_group)
        group_btn_layout.addWidget(btn_add_group)

        btn_rename_group = QPushButton("重新命名")
        btn_rename_group.clicked.connect(self._rename_section_item)
        group_btn_layout.addWidget(btn_rename_group)

        btn_toggle_group = QPushButton("啟用/暫停")
        btn_toggle_group.clicked.connect(self._toggle_section_item)
        group_btn_layout.addWidget(btn_toggle_group)

        btn_remove_group = QPushButton("刪除")
        btn_remove_group.clicked.connect(self._remove_section_item)
        group_btn_layout.addWidget(btn_remove_group)

        sections_layout.addLayout(group_btn_layout)

        # 版區操作按鈕
        section_btn_layout = QHBoxLayout()

        btn_add_section = QPushButton("新增版區")
        btn_add_section.clicked.connect(self._add_section)
        section_btn_layout.addWidget(btn_add_section)

        btn_move_up = QPushButton("↑ 上移")
        btn_move_up.clicked.connect(self._move_section_up)
        section_btn_layout.addWidget(btn_move_up)

        btn_move_down = QPushButton("↓ 下移")
        btn_move_down.clicked.connect(self._move_section_down)
        section_btn_layout.addWidget(btn_move_down)

        sections_layout.addLayout(section_btn_layout)

        layout.addWidget(sections_group)

        # 儲存按鈕
        btn_save = QPushButton("儲存設定")
        btn_save.clicked.connect(self._save_sections_settings)

        return tab

    def _create_keywords_tab(self) -> QWidget:
        """建立下載關鍵字分頁"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 說明
        hint = QLabel("輸入基礎關鍵字，系統自動產生 @xxx, @ xxx, xxx@, xxx @ 四種比對規則")
        hint.setStyleSheet(HINT_LABEL)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 標題篩選關鍵字 (JDownloader 下載)
        filters_group = QGroupBox("標題篩選關鍵字 (JDownloader 下載)")
        filters_layout = QVBoxLayout(filters_group)
        self.tag_title_filters = TagWidget("輸入關鍵字，例如: mega")
        filters_layout.addWidget(self.tag_title_filters)
        layout.addWidget(filters_group)

        # 手動網頁下載篩選關鍵字
        web_group = QGroupBox("手動網頁下載篩選關鍵字")
        web_layout = QVBoxLayout(web_group)
        self.tag_web_keywords = TagWidget("輸入關鍵字，例如: gd")
        web_layout.addWidget(self.tag_web_keywords)
        layout.addWidget(web_group)

        # SMG 篩選關鍵字
        smg_group = QGroupBox("SMG 篩選關鍵字")
        smg_layout = QVBoxLayout(smg_group)
        self.tag_smg_keywords = TagWidget("輸入關鍵字，例如: smg")
        smg_layout.addWidget(self.tag_smg_keywords)
        layout.addWidget(smg_group)

        # 儲存按鈕
        btn_save = QPushButton("儲存設定")
        btn_save.clicked.connect(self._save_keywords_settings)
        layout.addWidget(btn_save)

        layout.addStretch()

        return tab

    def _save_keywords_settings(self):
        """儲存下載關鍵字設定"""
        if 'forum' not in self.config:
            self.config['forum'] = {}

        self.config['forum']['title_filters'] = self.tag_title_filters.get_tags()
        self.config['forum']['web_download_keywords'] = self.tag_web_keywords.get_tags()
        self.config['forum']['smg_keywords'] = self.tag_smg_keywords.get_tags()

        self._save_config()
        self.statusBar().showMessage("下載關鍵字已儲存", 3000)

    def _create_history_tab(self) -> QWidget:
        """建立下載歷史分頁"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 統計資訊
        stats_group = QGroupBox("下載統計")
        stats_layout = QGridLayout(stats_group)

        self.lbl_total_posts = QLabel("總帖子: 0")
        self.lbl_total_downloads = QLabel("總下載: 0")

        stats_layout.addWidget(self.lbl_total_posts, 0, 0)
        stats_layout.addWidget(self.lbl_total_downloads, 0, 1)

        layout.addWidget(stats_group)

        # 歷史記錄表格
        history_group = QGroupBox("下載/解壓歷史")
        history_layout = QVBoxLayout(history_group)

        # 搜尋/篩選列
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("搜尋:"))
        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("輸入標題、密碼或版區...")
        self.history_search.textChanged.connect(self._on_history_search_changed)
        self.history_search.setMaximumWidth(250)
        filter_layout.addWidget(self.history_search)

        filter_layout.addSpacing(10)
        btn_refresh = QPushButton("重新整理")
        btn_refresh.clicked.connect(self._refresh_history)
        filter_layout.addWidget(btn_refresh)

        btn_clear_history = QPushButton("清空")
        btn_clear_history.clicked.connect(self._clear_download_history)
        filter_layout.addWidget(btn_clear_history)

        filter_layout.addStretch()

        # 提示文字
        hint_label = QLabel("提示：點擊密碼欄位複製，雙擊標題開啟帖子，右鍵更多操作")
        hint_label.setStyleSheet(HINT_LABEL)
        filter_layout.addWidget(hint_label)

        history_layout.addLayout(filter_layout)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(8)
        self.history_table.setHorizontalHeaderLabels([
            "TID", "標題", "下載次數", "類型", "壓縮檔名", "密碼", "版區", "建立時間"
        ])

        # 設定欄寬 - 允許使用者調整
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # 標題自動延伸
        # 設定預設寬度
        self.history_table.setColumnWidth(0, 70)   # TID
        self.history_table.setColumnWidth(2, 60)   # 下載次數
        self.history_table.setColumnWidth(3, 80)   # 類型
        self.history_table.setColumnWidth(4, 150)  # 壓縮檔名
        self.history_table.setColumnWidth(5, 200)  # 密碼
        self.history_table.setColumnWidth(6, 100)  # 版區
        self.history_table.setColumnWidth(7, 120)  # 建立時間

        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # 啟用表格排序
        self.history_table.setSortingEnabled(True)
        # 點擊處理 (密碼複製、下載次數詳細)
        self.history_table.cellClicked.connect(self._on_history_cell_clicked)
        # 雙擊開啟帖子頁面
        self.history_table.cellDoubleClicked.connect(self._on_history_cell_double_clicked)
        # 右鍵選單
        self.history_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_table.customContextMenuRequested.connect(self._on_history_context_menu)

        history_layout.addWidget(self.history_table)

        layout.addWidget(history_group)

        return tab

    def _create_extract_settings_tab(self) -> QWidget:
        """建立解壓縮設定分頁"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 使用捲動區域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        # 解壓縮設定元件
        self.extract_settings_widget = ExtractSettingsWidget()
        scroll.setWidget(self.extract_settings_widget)

        layout.addWidget(scroll)

        # 儲存按鈕
        btn_save = QPushButton("儲存解壓縮設定")
        btn_save.clicked.connect(self._save_extract_settings)
        layout.addWidget(btn_save)

        return tab

    def _save_extract_settings(self):
        """儲存解壓縮設定"""
        extract_settings = self.extract_settings_widget.get_settings()

        # 合併到主設定
        self.config.update(extract_settings)
        self._save_config()
        self.statusBar().showMessage("解壓縮設定已儲存", 3000)

    def _create_advanced_tab(self) -> QWidget:
        """建立進階設定分頁"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 爬蟲設定
        scraper_group = QGroupBox("爬蟲設定")
        scraper_layout = QGridLayout(scraper_group)

        scraper_layout.addWidget(QLabel("每版區檢查頁數:"), 0, 0)
        self.spin_pages = QSpinBox()
        self.spin_pages.setRange(1, 10)
        self.spin_pages.setValue(1)
        scraper_layout.addWidget(self.spin_pages, 0, 1)

        scraper_layout.addWidget(QLabel("每版區檢查帖子數:"), 1, 0)
        self.spin_posts = QSpinBox()
        self.spin_posts.setRange(5, 100)
        self.spin_posts.setValue(15)
        scraper_layout.addWidget(self.spin_posts, 1, 1)

        scraper_layout.addWidget(QLabel("請求間隔 (秒):"), 2, 0)
        self.spin_delay = QSpinBox()
        self.spin_delay.setRange(1, 30)
        self.spin_delay.setValue(2)
        scraper_layout.addWidget(self.spin_delay, 2, 1)

        scraper_layout.addWidget(QLabel("感謝間隔 (秒):"), 3, 0)
        self.spin_thanks_delay = QSpinBox()
        self.spin_thanks_delay.setRange(1, 60)
        self.spin_thanks_delay.setValue(5)
        scraper_layout.addWidget(self.spin_thanks_delay, 3, 1)

        layout.addWidget(scraper_group)

        # 檔案大小限制
        size_group = QGroupBox("檔案大小限制")
        size_layout = QGridLayout(size_group)

        size_layout.addWidget(QLabel("最大檔案大小 (MB):"), 0, 0)
        self.spin_max_size = QSpinBox()
        self.spin_max_size.setRange(100, 102400)  # 100MB - 100GB
        self.spin_max_size.setValue(2048)  # 2GB
        self.spin_max_size.setSingleStep(1024)
        size_layout.addWidget(self.spin_max_size, 0, 1)

        layout.addWidget(size_group)

        # 解壓監控設定
        extract_group = QGroupBox("解壓監控設定")
        extract_layout = QGridLayout(extract_group)

        extract_layout.addWidget(QLabel("檢查間隔 (秒):"), 0, 0)
        self.spin_extract_interval = QSpinBox()
        self.spin_extract_interval.setRange(10, 600)
        self.spin_extract_interval.setValue(60)
        extract_layout.addWidget(self.spin_extract_interval, 0, 1)

        layout.addWidget(extract_group)

        # 資料庫管理設定
        db_group = QGroupBox("資料庫管理")
        db_layout = QGridLayout(db_group)

        # 記錄保留天數
        db_layout.addWidget(QLabel("記錄保留天數:"), 0, 0)
        self.spin_retention_days = QSpinBox()
        self.spin_retention_days.setRange(1, 365)
        self.spin_retention_days.setValue(90)
        self.spin_retention_days.setToolTip("帖子、下載記錄的保留天數（預設 90 天）")
        db_layout.addWidget(self.spin_retention_days, 0, 1)

        # 感謝記錄保留年數
        db_layout.addWidget(QLabel("感謝記錄保留年數:"), 1, 0)
        self.spin_thanked_retention_years = QSpinBox()
        self.spin_thanked_retention_years.setRange(1, 10)
        self.spin_thanked_retention_years.setValue(1)
        self.spin_thanked_retention_years.setToolTip("已感謝帖子的 TID 保留年數（用於避免重複感謝）")
        db_layout.addWidget(self.spin_thanked_retention_years, 1, 1)

        # 清除記錄按鈕
        btn_clear_records = QPushButton("清除記錄...")
        btn_clear_records.clicked.connect(self._show_clear_records_dialog)
        db_layout.addWidget(btn_clear_records, 0, 2, 2, 1)

        layout.addWidget(db_group)

        # 儲存按鈕
        btn_save = QPushButton("儲存設定")
        btn_save.clicked.connect(self._save_advanced_settings)
        layout.addWidget(btn_save)

        layout.addStretch()

        return tab

    def _load_settings_to_ui(self):
        """載入設定到介面"""
        if not self.config:
            return

        # 路徑設定
        paths = self.config.get('paths', {})
        self.txt_download_dir.setText(paths.get('download_dir', ''))
        self.txt_extract_dir.setText(paths.get('extract_dir', ''))
        self.txt_winrar_path.setText(paths.get('winrar_path', ''))

        jd = self.config.get('jdownloader', {})
        self.txt_jd_exe.setText(jd.get('exe_path', ''))
        self.txt_jd_folderwatch.setText(jd.get('folderwatch_path', ''))
        self.chk_auto_start_jd.setChecked(jd.get('auto_start', True))

        # SMG 設定
        smg = self.config.get('smg', {})
        self.txt_smg_exe.setText(smg.get('exe_path', ''))
        self.txt_smg_download_dir.setText(smg.get('download_dir', ''))

        # 版區設定 (群組化)
        self._load_sections_to_tree()

        # 關鍵字篩選 — 載入並自動遷移舊格式
        forum = self.config.get('forum', {})
        self.tag_title_filters.set_tags(self._migrate_keywords(forum.get('title_filters', [])))
        self.tag_web_keywords.set_tags(self._migrate_keywords(forum.get('web_download_keywords', [])))
        self.tag_smg_keywords.set_tags(self._migrate_keywords(forum.get('smg_keywords', [])))

        # 爬蟲設定
        scraper = self.config.get('scraper', {})
        self.spin_pages.setValue(scraper.get('pages_per_section', 1))
        self.spin_posts.setValue(scraper.get('posts_per_section', 15))
        self.spin_delay.setValue(scraper.get('delay_between_requests', 2))
        self.spin_thanks_delay.setValue(scraper.get('delay_between_thanks', 5))

        # 檔案大小限制
        self.spin_max_size.setValue(scraper.get('max_file_size_mb', 2048))

        # 解壓監控設定
        self.spin_extract_interval.setValue(self.config.get('extract_interval', 60))

        # 資料庫管理設定
        db_settings = self.config.get('database', {})
        self.spin_retention_days.setValue(db_settings.get('retention_days', 30))

        # 解壓縮設定
        if hasattr(self, 'extract_settings_widget'):
            self.extract_settings_widget.set_settings(self.config)

    def _browse_dir(self, line_edit: QLineEdit):
        """瀏覽目錄"""
        dir_path = QFileDialog.getExistingDirectory(self, "選擇目錄", line_edit.text())
        if dir_path:
            line_edit.setText(dir_path)

    def _browse_file(self, line_edit: QLineEdit, filter_str: str):
        """瀏覽檔案"""
        file_path, _ = QFileDialog.getOpenFileName(self, "選擇檔案", line_edit.text(), filter_str)
        if file_path:
            line_edit.setText(file_path)

    def _save_paths_settings(self):
        """儲存路徑設定"""
        if 'paths' not in self.config:
            self.config['paths'] = {}

        self.config['paths']['download_dir'] = self.txt_download_dir.text()
        self.config['paths']['extract_dir'] = self.txt_extract_dir.text()
        self.config['paths']['winrar_path'] = self.txt_winrar_path.text()

        if 'jdownloader' not in self.config:
            self.config['jdownloader'] = {}
        self.config['jdownloader']['exe_path'] = self.txt_jd_exe.text()
        self.config['jdownloader']['folderwatch_path'] = self.txt_jd_folderwatch.text()
        self.config['jdownloader']['auto_start'] = self.chk_auto_start_jd.isChecked()

        # SMG 設定
        if 'smg' not in self.config:
            self.config['smg'] = {}
        self.config['smg']['exe_path'] = self.txt_smg_exe.text()
        self.config['smg']['download_dir'] = self.txt_smg_download_dir.text()

        self._save_config()

    def _get_cookie_path(self) -> Path:
        """取得 Cookie 檔案路徑"""
        return self.profile_manager.get_profile_cookie_path()

    def _load_cookie_file(self):
        """載入現有的 Cookie 檔案"""
        import json
        cookie_path = self._get_cookie_path()

        if cookie_path.exists():
            try:
                with open(cookie_path, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                self.txt_cookie.setPlainText(json.dumps(cookies, indent=2, ensure_ascii=False))
                self.lbl_cookie_status.setText(f"Cookie 狀態: 已載入 {len(cookies)} 個 cookie")
                self.statusBar().showMessage(f"已載入 Cookie: {cookie_path}", 3000)
            except Exception as e:
                QMessageBox.warning(self, "錯誤", f"載入 Cookie 失敗: {e}")
        else:
            QMessageBox.information(self, "提示", f"Cookie 檔案不存在: {cookie_path}")

    def _save_cookie(self):
        """儲存 Cookie 到檔案"""
        import json
        cookie_text = self.txt_cookie.toPlainText().strip()

        if not cookie_text:
            QMessageBox.warning(self, "錯誤", "請先輸入 Cookie 內容")
            return

        try:
            # 解析 JSON
            cookies = json.loads(cookie_text)

            # 驗證格式
            if not isinstance(cookies, list):
                QMessageBox.warning(self, "錯誤", "Cookie 必須是 JSON 陣列格式")
                return

            # 儲存到檔案
            cookie_path = self._get_cookie_path()
            cookie_path.parent.mkdir(parents=True, exist_ok=True)

            with open(cookie_path, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, indent=2, ensure_ascii=False)

            self.lbl_cookie_status.setText(f"Cookie 狀態: 已儲存 {len(cookies)} 個 cookie")
            self.statusBar().showMessage(f"Cookie 已儲存到: {cookie_path}", 3000)
            QMessageBox.information(self, "成功", f"已儲存 {len(cookies)} 個 Cookie")

        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "JSON 格式錯誤", f"Cookie JSON 格式不正確:\n{e}")
        except Exception as e:
            QMessageBox.warning(self, "錯誤", f"儲存 Cookie 失敗: {e}")

    def _test_cookie(self):
        """測試 Cookie 登入狀態"""
        import json

        cookie_path = self._get_cookie_path()
        if not cookie_path.exists():
            # 嘗試從輸入框讀取
            cookie_text = self.txt_cookie.toPlainText().strip()
            if not cookie_text:
                QMessageBox.warning(self, "錯誤", "請先輸入或載入 Cookie")
                return
            try:
                cookies = json.loads(cookie_text)
            except json.JSONDecodeError:
                QMessageBox.warning(self, "錯誤", "Cookie JSON 格式不正確")
                return
        else:
            try:
                with open(cookie_path, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
            except Exception as e:
                QMessageBox.warning(self, "錯誤", f"讀取 Cookie 失敗: {e}")
                return

        # 測試登入
        self.lbl_cookie_status.setText("Cookie 狀態: 測試中...")
        self.statusBar().showMessage("正在測試登入狀態...", 0)

        try:
            import requests

            session = requests.Session()

            # 載入 cookies 到 session
            for cookie in cookies:
                session.cookies.set(
                    cookie.get('name', ''),
                    cookie.get('value', ''),
                    domain=cookie.get('domain', ''),
                    path=cookie.get('path', '/')
                )

            # 測試訪問論壇
            base_url = self.config.get('forum', {}).get('base_url', 'https://fastzone.org')
            response = session.get(f"{base_url}/forum.php", timeout=10)

            # 檢查是否已登入 (檢查頁面中是否有登出連結或使用者名稱)
            if '退出' in response.text or '登出' in response.text or 'logout' in response.text.lower():
                self.lbl_cookie_status.setText("Cookie 狀態: 登入成功 ✓")
                self.statusBar().showMessage("登入狀態正常", 3000)
                QMessageBox.information(self, "測試成功", "Cookie 有效，已成功登入論壇！")
            elif '登錄' in response.text or '登入' in response.text or 'login' in response.text.lower():
                self.lbl_cookie_status.setText("Cookie 狀態: 未登入 ✗")
                self.statusBar().showMessage("Cookie 無效或已過期", 3000)
                QMessageBox.warning(self, "測試失敗", "Cookie 無效或已過期，請重新導出 Cookie")
            else:
                self.lbl_cookie_status.setText("Cookie 狀態: 無法確定")
                self.statusBar().showMessage("無法確定登入狀態", 3000)
                QMessageBox.information(self, "測試結果", "無法確定登入狀態，請手動確認")

        except requests.exceptions.RequestException as e:
            self.lbl_cookie_status.setText("Cookie 狀態: 連線失敗")
            self.statusBar().showMessage("連線失敗", 3000)
            QMessageBox.warning(self, "連線錯誤", f"無法連線到論壇:\n{e}")
        except Exception as e:
            self.lbl_cookie_status.setText("Cookie 狀態: 測試失敗")
            self.statusBar().showMessage("測試失敗", 3000)
            QMessageBox.warning(self, "錯誤", f"測試失敗:\n{e}")

    def _save_sections_settings(self):
        """儲存版區設定 (群組化)"""
        if 'forum' not in self.config:
            self.config['forum'] = {}

        # 從樹狀結構取得群組設定
        section_groups = self._get_sections_from_tree()
        self.config['forum']['section_groups'] = section_groups

        # 同時更新 target_sections 以保持向後相容 (只包含啟用的版區)
        active_sections = self._get_active_sections()
        self.config['forum']['target_sections'] = active_sections

        self._save_config()
        self.statusBar().showMessage("版區設定已儲存", 3000)

    def _save_advanced_settings(self):
        """儲存進階設定"""
        if 'scraper' not in self.config:
            self.config['scraper'] = {}

        self.config['scraper']['pages_per_section'] = self.spin_pages.value()
        self.config['scraper']['posts_per_section'] = self.spin_posts.value()
        self.config['scraper']['delay_between_requests'] = self.spin_delay.value()
        self.config['scraper']['delay_between_thanks'] = self.spin_thanks_delay.value()

        # 檔案大小限制
        self.config['scraper']['max_file_size_mb'] = self.spin_max_size.value()

        # 解壓監控設定
        self.config['extract_interval'] = self.spin_extract_interval.value()

        # 資料庫管理設定
        if 'database' not in self.config:
            self.config['database'] = {}
        self.config['database']['retention_days'] = self.spin_retention_days.value()

        self._save_config()

    def _load_sections_to_tree(self):
        """載入版區設定到樹狀結構"""
        self.tree_sections.clear()
        self.tree_sections.blockSignals(True)  # 暫時阻止信號以避免觸發 itemChanged

        forum_config = self.config.get('forum', {})
        section_groups = forum_config.get('section_groups', [])

        # 如果沒有群組，嘗試從舊的 target_sections 轉換
        if not section_groups:
            old_sections = forum_config.get('target_sections', [])
            if old_sections:
                # 建立一個預設群組
                section_groups = [{
                    'name': '預設群組',
                    'enabled': True,
                    'sections': old_sections
                }]

        for group in section_groups:
            group_name = group.get('name', '未命名群組')
            group_enabled = group.get('enabled', True)

            # 建立群組項目
            group_item = QTreeWidgetItem(self.tree_sections)
            group_item.setText(0, group_name)
            group_item.setText(1, "")
            group_item.setText(2, "✓" if group_enabled else "✗")
            group_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'group', 'enabled': group_enabled})
            group_item.setExpanded(True)

            # 設定群組項目樣式
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)

            if not group_enabled:
                group_item.setForeground(0, QColor(*NordColors.POLAR_NIGHT_3))
                group_item.setForeground(2, QColor(*NordColors.AURORA_RED))

            # 加入該群組的版區
            for section in group.get('sections', []):
                section_name = section.get('name', '')
                section_fid = section.get('fid', '')
                section_enabled = section.get('enabled', True)

                section_item = QTreeWidgetItem(group_item)
                section_item.setText(0, f"  {section_name}")
                section_item.setText(1, str(section_fid))
                section_item.setText(2, "✓" if section_enabled else "✗")
                section_item.setData(0, Qt.ItemDataRole.UserRole, {
                    'type': 'section',
                    'fid': section_fid,
                    'enabled': section_enabled
                })

                if not section_enabled or not group_enabled:
                    section_item.setForeground(0, QColor(*NordColors.POLAR_NIGHT_3))
                    section_item.setForeground(1, QColor(*NordColors.POLAR_NIGHT_3))
                    section_item.setForeground(2, QColor(*NordColors.AURORA_RED))

        self.tree_sections.blockSignals(False)

    def _on_section_item_changed(self, item, column):
        """當樹狀項目變更時"""
        pass  # 目前用按鈕控制，不用這個

    def _on_section_settings_changed(self):
        """版區管理設定變更時 - 自動儲存到檔案"""
        self._save_config()
        self.statusBar().showMessage("版區設定已儲存", 3000)

    def _on_export_to_section_group(self, sections: list):
        """將版區管理的選擇匯出到版區群組"""
        if not sections:
            return

        # 詢問要建立的群組名稱
        group_name, ok = QInputDialog.getText(
            self, "匯出到版區群組",
            f"將匯出 {len(sections)} 個版區\n請輸入群組名稱:",
            text="匯入的版區"
        )

        if not ok or not group_name:
            return

        # 建立群組項目
        group_item = QTreeWidgetItem(self.tree_sections)
        group_item.setText(0, group_name)
        group_item.setText(1, "")
        group_item.setText(2, "✓")
        group_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'group', 'enabled': True})
        group_item.setExpanded(True)

        font = group_item.font(0)
        font.setBold(True)
        group_item.setFont(0, font)

        # 加入版區
        for section in sections:
            section_item = QTreeWidgetItem(group_item)
            section_item.setText(0, f"  {section['name']}")
            section_item.setText(1, str(section['fid']))
            section_item.setText(2, "✓")
            section_item.setData(0, Qt.ItemDataRole.UserRole, {
                'type': 'section',
                'fid': section['fid'],
                'enabled': True
            })

        # 切換到版區群組分頁
        self.tabs.setCurrentIndex(3)  # 版區群組的索引

        QMessageBox.information(self, "完成", f"已匯出 {len(sections)} 個版區到群組「{group_name}」")
        self.statusBar().showMessage(f"已匯出 {len(sections)} 個版區，請記得儲存設定", 5000)

    def _on_search_download_requested(self, selected_posts: list):
        """版區搜尋請求批次下載"""
        if not selected_posts:
            QMessageBox.warning(self, "提示", "沒有選取任何帖子")
            return

        # 確認下載
        reply = QMessageBox.question(
            self, "確認下載",
            f"將下載 {len(selected_posts)} 個帖子，是否繼續？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # 建立批次下載工作執行緒
        self.search_download_worker = SearchDownloadWorker(
            selected_posts=selected_posts,
            config_path=str(self.config_path),
            config=self.config
        )

        # 連接訊號
        self.search_download_worker.log_signal.connect(self._append_log)
        self.search_download_worker.progress_signal.connect(self._on_search_download_progress)
        self.search_download_worker.finished_signal.connect(self._on_search_download_finished)
        self.search_download_worker.error_signal.connect(self._on_search_download_error)

        # 開始執行
        self.search_download_worker.start()

        # 切換到主控制台顯示日誌
        self.tabs.setCurrentIndex(0)
        self._append_log(f"開始批次下載 {len(selected_posts)} 個帖子...")

    def _on_search_download_progress(self, current: int, total: int, title: str):
        """批次下載進度更新"""
        self.statusBar().showMessage(f"下載進度: {current}/{total} - {title}")

    def _on_search_download_finished(self, stats: dict):
        """批次下載完成"""
        self.statusBar().showMessage("批次下載完成", 5000)

        # 顯示統計
        msg = (
            f"批次下載完成!\n\n"
            f"成功: {stats.get('success', 0)}\n"
            f"失敗: {stats.get('failed', 0)}\n"
            f"提取連結數: {stats.get('links_extracted', 0)}"
        )
        if stats.get('web_downloads', 0) > 0:
            msg += f"\n網頁下載: {stats.get('web_downloads', 0)}"
        if stats.get('smg_downloads', 0) > 0:
            msg += f"\nSMG 下載: {stats.get('smg_downloads', 0)}"
        QMessageBox.information(self, "完成", msg)

        # 清理
        self.search_download_worker = None

    def _on_search_download_error(self, error: str):
        """批次下載錯誤"""
        self.statusBar().showMessage(f"下載錯誤: {error}", 5000)
        QMessageBox.warning(self, "錯誤", f"批次下載失敗: {error}")
        self.search_download_worker = None

    def _add_section_group(self):
        """新增版區群組"""
        name, ok = QInputDialog.getText(self, "新增群組", "群組名稱:")
        if ok and name:
            # 建立群組項目
            group_item = QTreeWidgetItem(self.tree_sections)
            group_item.setText(0, name)
            group_item.setText(1, "")
            group_item.setText(2, "✓")
            group_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'group', 'enabled': True})
            group_item.setExpanded(True)

            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)

            self.statusBar().showMessage(f"已新增群組: {name}", 3000)

    def _add_section(self):
        """新增版區到選中的群組"""
        current = self.tree_sections.currentItem()
        if not current:
            QMessageBox.warning(self, "提示", "請先選擇一個群組")
            return

        # 找到群組項目
        data = current.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get('type') == 'section':
            # 如果選中的是版區，則使用其父群組
            group_item = current.parent()
        elif data and data.get('type') == 'group':
            group_item = current
        else:
            QMessageBox.warning(self, "提示", "請先選擇或建立一個群組")
            return

        name, ok1 = QInputDialog.getText(self, "新增版區", "版區名稱:")
        if ok1 and name:
            fid, ok2 = QInputDialog.getText(self, "新增版區", "版區 FID:")
            if ok2 and fid:
                section_item = QTreeWidgetItem(group_item)
                section_item.setText(0, f"  {name}")
                section_item.setText(1, str(fid))
                section_item.setText(2, "✓")
                section_item.setData(0, Qt.ItemDataRole.UserRole, {
                    'type': 'section',
                    'fid': fid,
                    'enabled': True
                })
                group_item.setExpanded(True)
                self.statusBar().showMessage(f"已新增版區: {name} (fid={fid})", 3000)

    def _rename_section_item(self):
        """重新命名選中的項目"""
        current = self.tree_sections.currentItem()
        if not current:
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        old_name = current.text(0).strip()
        new_name, ok = QInputDialog.getText(self, "重新命名", "新名稱:", text=old_name)
        if ok and new_name:
            if data.get('type') == 'group':
                current.setText(0, new_name)
            else:
                current.setText(0, f"  {new_name}")

    def _toggle_section_item(self):
        """切換選中項目的啟用/暫停狀態"""
        current = self.tree_sections.currentItem()
        if not current:
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        # 切換狀態
        new_enabled = not data.get('enabled', True)
        data['enabled'] = new_enabled
        current.setData(0, Qt.ItemDataRole.UserRole, data)

        # 更新顯示
        current.setText(2, "✓" if new_enabled else "✗")

        if new_enabled:
            current.setForeground(0, QColor(*NordColors.SNOW_STORM_2))
            current.setForeground(1, QColor(*NordColors.SNOW_STORM_2))
            current.setForeground(2, QColor(*NordColors.AURORA_GREEN))
        else:
            current.setForeground(0, QColor(*NordColors.POLAR_NIGHT_3))
            current.setForeground(1, QColor(*NordColors.POLAR_NIGHT_3))
            current.setForeground(2, QColor(*NordColors.AURORA_RED))

        # 如果是群組，同時更新所有子版區的顯示
        if data.get('type') == 'group':
            for i in range(current.childCount()):
                child = current.child(i)
                if new_enabled:
                    child_data = child.data(0, Qt.ItemDataRole.UserRole)
                    child_enabled = child_data.get('enabled', True) if child_data else True
                    if child_enabled:
                        child.setForeground(0, QColor(*NordColors.SNOW_STORM_2))
                        child.setForeground(1, QColor(*NordColors.SNOW_STORM_2))
                        child.setForeground(2, QColor(*NordColors.AURORA_GREEN))
                else:
                    child.setForeground(0, QColor(*NordColors.POLAR_NIGHT_3))
                    child.setForeground(1, QColor(*NordColors.POLAR_NIGHT_3))
                    child.setForeground(2, QColor(*NordColors.AURORA_RED))

        status = "啟用" if new_enabled else "暫停"
        self.statusBar().showMessage(f"已{status}: {current.text(0).strip()}", 3000)

    def _remove_section_item(self):
        """移除選中的項目"""
        current = self.tree_sections.currentItem()
        if not current:
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type = "群組" if data.get('type') == 'group' else "版區"
        name = current.text(0).strip()

        reply = QMessageBox.question(
            self, "確認刪除",
            f"確定要刪除{item_type} \"{name}\" 嗎？" +
            ("\n(群組內的所有版區也會一併刪除)" if data.get('type') == 'group' else ""),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            parent = current.parent()
            if parent:
                parent.removeChild(current)
            else:
                index = self.tree_sections.indexOfTopLevelItem(current)
                self.tree_sections.takeTopLevelItem(index)
            self.statusBar().showMessage(f"已刪除{item_type}: {name}", 3000)

    def _move_section_up(self):
        """上移選中的版區"""
        self._move_section(-1)

    def _move_section_down(self):
        """下移選中的版區"""
        self._move_section(1)

    def _move_section(self, direction: int):
        """移動選中的版區 (direction: -1 上移, 1 下移)"""
        current = self.tree_sections.currentItem()
        if not current:
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get('type') != 'section':
            QMessageBox.information(self, "提示", "請選擇一個版區來移動")
            return

        parent = current.parent()
        if not parent:
            return

        index = parent.indexOfChild(current)
        new_index = index + direction

        if new_index < 0 or new_index >= parent.childCount():
            return

        # 移除並重新插入
        parent.removeChild(current)
        parent.insertChild(new_index, current)
        self.tree_sections.setCurrentItem(current)

    def _get_sections_from_tree(self):
        """從樹狀結構取得版區設定"""
        section_groups = []

        if not hasattr(self, 'tree_sections'):
            return section_groups

        for i in range(self.tree_sections.topLevelItemCount()):
            group_item = self.tree_sections.topLevelItem(i)
            group_data = group_item.data(0, Qt.ItemDataRole.UserRole)

            if not group_data or group_data.get('type') != 'group':
                continue

            group = {
                'name': group_item.text(0).strip(),
                'enabled': group_data.get('enabled', True),
                'sections': []
            }

            for j in range(group_item.childCount()):
                section_item = group_item.child(j)
                section_data = section_item.data(0, Qt.ItemDataRole.UserRole)

                if section_data and section_data.get('type') == 'section':
                    group['sections'].append({
                        'name': section_item.text(0).strip(),
                        'fid': section_data.get('fid', ''),
                        'enabled': section_data.get('enabled', True)
                    })

            section_groups.append(group)

        return section_groups

    def _get_active_sections(self):
        """取得所有啟用中的版區 (用於主程式)"""
        active_sections = []
        section_groups = self._get_sections_from_tree()

        for group in section_groups:
            if not group.get('enabled', True):
                continue  # 跳過暫停的群組

            for section in group.get('sections', []):
                if section.get('enabled', True):
                    active_sections.append({
                        'name': section['name'],
                        'fid': section['fid']
                    })

        return active_sections

    @staticmethod
    def _migrate_keywords(keywords: list) -> list:
        """將舊格式關鍵字遷移為基礎關鍵字

        舊格式: ['@mg', '@ mg', 'mg@', 'mg @']
        新格式: ['mg']

        @ 在中間的關鍵字（如 MG@JD）會被丟棄
        """
        if not keywords:
            return []

        # 檢查是否有包含 @ 的關鍵字（舊格式）
        has_at = any('@' in kw for kw in keywords)
        if not has_at:
            # 已是新格式
            return keywords

        # 反推基礎關鍵字 — 只處理 @ 在開頭或結尾的
        base_keywords = []
        for kw in keywords:
            stripped = kw.strip()
            if not stripped:
                continue

            if '@' not in stripped:
                # 沒有 @ 的直接保留
                base = stripped.lower()
            elif stripped.startswith('@') or stripped.startswith('@ '):
                # @ 在開頭: @mg, @ mg
                base = stripped.lstrip('@ ').strip().lower()
            elif stripped.endswith('@') or stripped.endswith(' @'):
                # @ 在結尾: mg@, mg @
                base = stripped.rstrip('@ ').strip().lower()
            else:
                # @ 在中間 (如 MG@JD) — 丟棄
                continue

            if base and base not in base_keywords:
                base_keywords.append(base)
        return base_keywords

    def _is_jdownloader_running(self) -> bool:
        """檢查 JDownloader 是否正在執行"""
        import subprocess
        try:
            # Windows: 用 tasklist 檢查程序
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq JDownloader2.exe'],
                capture_output=True, text=True, timeout=10
            )
            return 'JDownloader2.exe' in result.stdout
        except Exception:
            return False

    def _start_jdownloader(self) -> bool:
        """啟動 JDownloader"""
        import subprocess
        jd_path = self.txt_jd_exe.text().strip()

        if not jd_path:
            return False

        jd_exe = Path(jd_path)
        if not jd_exe.exists():
            self._append_log(f"JDownloader 路徑不存在: {jd_path}")
            return False

        try:
            # 使用 Windows start 命令在背景啟動 (避免權限問題)
            # start "" "path" 會在新視窗開啟程式
            subprocess.Popen(
                f'start "" "{jd_exe}"',
                shell=True,
                cwd=str(jd_exe.parent)
            )
            self._append_log(f"已啟動 JDownloader: {jd_exe.name}")
            return True
        except Exception as e:
            self._append_log(f"啟動 JDownloader 失敗: {e}")
            return False

    def _import_cookie_from_browser(self):
        """從瀏覽器自動導入 Cookie (使用 browser-cookie3)"""
        import json

        # 取得論壇域名
        base_url = self.config.get('forum', {}).get('base_url', 'https://fastzone.org')
        domain = base_url.replace('https://', '').replace('http://', '').split('/')[0]

        self.lbl_cookie_status.setText("Cookie 狀態: 正在讀取瀏覽器...")
        self.statusBar().showMessage("正在從瀏覽器讀取 Cookie...", 0)
        QApplication.processEvents()

        try:
            import browser_cookie3
        except ImportError:
            QMessageBox.warning(
                self, "缺少套件",
                "需要安裝 browser-cookie3 套件。\n\n"
                "請執行: pip install browser-cookie3"
            )
            return

        cookies_found = []
        browser_used = None

        # 嘗試各種瀏覽器
        browsers = [
            ('Chrome', browser_cookie3.chrome),
            ('Edge', browser_cookie3.edge),
            ('Firefox', browser_cookie3.firefox),
            ('Brave', browser_cookie3.brave),
            ('Opera', browser_cookie3.opera),
        ]

        for browser_name, browser_func in browsers:
            try:
                cj = browser_func(domain_name=domain)
                for cookie in cj:
                    cookies_found.append({
                        'name': cookie.name,
                        'value': cookie.value,
                        'domain': cookie.domain,
                        'path': cookie.path,
                        'expirationDate': cookie.expires,
                        'secure': cookie.secure,
                        'httpOnly': cookie.has_nonstandard_attr('HttpOnly')
                    })
                if cookies_found:
                    browser_used = browser_name
                    break
            except Exception as e:
                self._append_log(f"讀取 {browser_name} Cookie: {e}")
                continue

        if cookies_found:
            # 轉換為 JSON 格式並顯示
            self.txt_cookie.setPlainText(json.dumps(cookies_found, indent=2, ensure_ascii=False))
            self.lbl_cookie_status.setText(f"Cookie 狀態: 從 {browser_used} 導入 {len(cookies_found)} 個 cookie")
            self.statusBar().showMessage(f"已從 {browser_used} 導入 {len(cookies_found)} 個 Cookie", 3000)
            QMessageBox.information(
                self, "導入成功",
                f"已從 {browser_used} 導入 {len(cookies_found)} 個 Cookie\n\n"
                f"請點擊「儲存 Cookie」按鈕儲存，然後測試登入狀態。"
            )
        else:
            self.lbl_cookie_status.setText("Cookie 狀態: 未找到")
            self.statusBar().showMessage("未能從瀏覽器找到 Cookie", 3000)
            QMessageBox.warning(
                self, "導入失敗",
                f"無法從瀏覽器自動讀取 {domain} 的 Cookie。\n\n"
                "可能原因:\n"
                "1. 瀏覽器未登入該論壇\n"
                "2. 瀏覽器正在執行中 (需關閉瀏覽器)\n\n"
                "建議:\n"
                "- 先關閉所有瀏覽器視窗後再試\n"
                "- 或使用 EditThisCookie 等擴充功能手動導出"
            )

    def _get_browser_cookie_paths(self) -> dict:
        """取得各瀏覽器的 Cookie 檔案路徑"""
        import os
        local_app_data = os.environ.get('LOCALAPPDATA', '')
        app_data = os.environ.get('APPDATA', '')

        return {
            'Chrome': os.path.join(local_app_data, r'Google\Chrome\User Data\Default\Network\Cookies'),
            'Chrome (舊版)': os.path.join(local_app_data, r'Google\Chrome\User Data\Default\Cookies'),
            'Edge': os.path.join(local_app_data, r'Microsoft\Edge\User Data\Default\Network\Cookies'),
            'Edge (舊版)': os.path.join(local_app_data, r'Microsoft\Edge\User Data\Default\Cookies'),
            'Firefox': self._find_firefox_cookie_path(),
            'Brave': os.path.join(local_app_data, r'BraveSoftware\Brave-Browser\User Data\Default\Network\Cookies'),
        }

    def _find_firefox_cookie_path(self) -> str:
        """尋找 Firefox Cookie 路徑"""
        import os
        app_data = os.environ.get('APPDATA', '')
        firefox_profiles = os.path.join(app_data, 'Mozilla', 'Firefox', 'Profiles')

        if not os.path.exists(firefox_profiles):
            return ''

        # 尋找 default 設定檔
        for item in os.listdir(firefox_profiles):
            if item.endswith('.default-release') or item.endswith('.default'):
                cookie_path = os.path.join(firefox_profiles, item, 'cookies.sqlite')
                if os.path.exists(cookie_path):
                    return cookie_path
        return ''

    def _read_browser_cookies(self, browser_name: str, cookie_path: str, domain: str) -> list:
        """讀取瀏覽器 Cookie"""
        import sqlite3
        import shutil
        import tempfile

        # 複製一份 Cookie 檔案 (避免鎖定問題)
        temp_dir = tempfile.mkdtemp()
        temp_cookie = os.path.join(temp_dir, 'cookies.db')

        try:
            shutil.copy2(cookie_path, temp_cookie)

            conn = sqlite3.connect(temp_cookie)
            cursor = conn.cursor()

            cookies = []

            if 'Firefox' in browser_name:
                # Firefox 格式
                cursor.execute('''
                    SELECT name, value, host, path, expiry, isSecure, isHttpOnly
                    FROM moz_cookies
                    WHERE host LIKE ?
                ''', (f'%{domain}%',))

                for row in cursor.fetchall():
                    cookies.append({
                        'name': row[0],
                        'value': row[1],
                        'domain': row[2],
                        'path': row[3],
                        'expirationDate': row[4],
                        'secure': bool(row[5]),
                        'httpOnly': bool(row[6])
                    })
            else:
                # Chromium 系列 (Chrome, Edge, Brave)
                cursor.execute('''
                    SELECT name, value, host_key, path, expires_utc, is_secure, is_httponly, encrypted_value
                    FROM cookies
                    WHERE host_key LIKE ?
                ''', (f'%{domain}%',))

                for row in cursor.fetchall():
                    value = row[1]
                    encrypted_value = row[7]

                    # 如果 value 是空的但有加密值，嘗試解密
                    if not value and encrypted_value:
                        try:
                            value = self._decrypt_chrome_cookie(encrypted_value, browser_name)
                        except Exception:
                            continue  # 解密失敗則跳過

                    if value:  # 只加入有值的 cookie
                        cookies.append({
                            'name': row[0],
                            'value': value,
                            'domain': row[2],
                            'path': row[3],
                            'expirationDate': row[4],
                            'secure': bool(row[5]),
                            'httpOnly': bool(row[6])
                        })

            conn.close()
            return cookies

        except Exception as e:
            self._append_log(f"讀取 {browser_name} Cookie 錯誤: {e}")
            return []
        finally:
            # 清理暫存檔
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except Exception:
                pass

    def _decrypt_chrome_cookie(self, encrypted_value: bytes, browser_name: str) -> str:
        """解密 Chrome 系列的 Cookie (Windows)"""
        try:
            import base64
            import json
            import os

            # Chrome 80+ 使用 AES-256-GCM 加密
            if encrypted_value[:3] == b'v10' or encrypted_value[:3] == b'v11':
                # 需要 DPAPI 和 AES 解密
                # 取得加密金鑰
                local_app_data = os.environ.get('LOCALAPPDATA', '')

                if 'Edge' in browser_name:
                    local_state_path = os.path.join(local_app_data, r'Microsoft\Edge\User Data\Local State')
                elif 'Brave' in browser_name:
                    local_state_path = os.path.join(local_app_data, r'BraveSoftware\Brave-Browser\User Data\Local State')
                else:
                    local_state_path = os.path.join(local_app_data, r'Google\Chrome\User Data\Local State')

                if not os.path.exists(local_state_path):
                    return ''

                with open(local_state_path, 'r', encoding='utf-8') as f:
                    local_state = json.load(f)

                encrypted_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])
                # 移除 'DPAPI' 前綴
                encrypted_key = encrypted_key[5:]

                # 使用 Windows DPAPI 解密金鑰
                import ctypes
                import ctypes.wintypes

                class DATA_BLOB(ctypes.Structure):
                    _fields_ = [
                        ('cbData', ctypes.wintypes.DWORD),
                        ('pbData', ctypes.POINTER(ctypes.c_char))
                    ]

                def decrypt_dpapi(encrypted_data):
                    blob_in = DATA_BLOB(len(encrypted_data), ctypes.cast(encrypted_data, ctypes.POINTER(ctypes.c_char)))
                    blob_out = DATA_BLOB()

                    if ctypes.windll.crypt32.CryptUnprotectData(
                        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
                    ):
                        data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
                        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
                        return data
                    return None

                key = decrypt_dpapi(encrypted_key)
                if not key:
                    return ''

                # 使用 AES-GCM 解密 cookie 值
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM

                nonce = encrypted_value[3:15]
                ciphertext = encrypted_value[15:]
                aesgcm = AESGCM(key)
                decrypted = aesgcm.decrypt(nonce, ciphertext, None)
                return decrypted.decode('utf-8')

            else:
                # 舊版 Chrome 使用 DPAPI 直接加密
                import ctypes
                import ctypes.wintypes

                class DATA_BLOB(ctypes.Structure):
                    _fields_ = [
                        ('cbData', ctypes.wintypes.DWORD),
                        ('pbData', ctypes.POINTER(ctypes.c_char))
                    ]

                blob_in = DATA_BLOB(len(encrypted_value), ctypes.cast(encrypted_value, ctypes.POINTER(ctypes.c_char)))
                blob_out = DATA_BLOB()

                if ctypes.windll.crypt32.CryptUnprotectData(
                    ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
                ):
                    data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
                    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
                    return data.decode('utf-8')

                return ''

        except ImportError:
            # 沒有 cryptography 庫
            return ''
        except Exception:
            return ''

    def _start_crawler(self):
        """開始爬取"""
        # 先儲存版區設定，確保使用最新的啟用狀態
        self._save_sections_settings()

        # 檢查是否有啟用的版區
        active_sections = self.config.get('forum', {}).get('target_sections', [])
        if not active_sections:
            self._append_log("錯誤: 沒有啟用任何版區，請先在版區設定中啟用至少一個版區")
            return

        # 顯示目前使用的設定檔
        self._append_log("=" * 50)
        self._append_log(f"【開始爬取】使用設定檔: {self.current_profile}")
        self._append_log(f"啟用版區: {', '.join(s['name'] for s in active_sections)}")
        self._append_log("=" * 50)

        # 檢查是否需要自動啟動 JDownloader
        if self.chk_auto_start_jd.isChecked():
            if not self._is_jdownloader_running():
                jd_path = self.txt_jd_exe.text().strip()
                if jd_path:
                    self._append_log("JDownloader 未執行，正在啟動...")
                    self._start_jdownloader()
                    # 等待一下讓 JD 啟動
                    import time
                    time.sleep(2)
                else:
                    self._append_log("提示: JDownloader 未執行，且未設定 JDownloader 主程式路徑")
            else:
                self._append_log("JDownloader 已在執行中")

        self.btn_start_crawler.setEnabled(False)
        self.btn_stop_crawler.setEnabled(True)
        self.crawler_status.setText(f"狀態: 執行中 [{self.current_profile}]")

        self.crawler_worker = CrawlerWorker(
            str(self.config_path),
            dry_run=self.chk_dry_run.isChecked(),
            re_download_thanked=self.chk_redownload_thanked.isChecked()
        )
        self.crawler_worker.log_signal.connect(self._append_log)
        self.crawler_worker.finished_signal.connect(self._crawler_finished)
        self.crawler_worker.start()

    def _stop_crawler(self):
        """停止爬取"""
        if self.crawler_worker:
            try:
                self.crawler_worker.stop()
                # 等待執行緒結束，但不要無限等待
                if not self.crawler_worker.wait(3000):
                    # 3 秒後仍未結束，強制終止
                    self._append_log("爬蟲執行緒未在時限內結束，強制終止")
                    self.crawler_worker.terminate()
                    self.crawler_worker.wait(1000)
            except Exception as e:
                self._append_log(f"停止爬蟲時發生錯誤: {e}")
            finally:
                self.crawler_worker = None

        self.btn_start_crawler.setEnabled(True)
        self.btn_stop_crawler.setEnabled(False)
        self.crawler_status.setText("狀態: 已停止")

    def _crawler_finished(self, stats: dict):
        """爬蟲完成"""
        self.btn_start_crawler.setEnabled(True)
        self.btn_stop_crawler.setEnabled(False)
        self.crawler_status.setText("狀態: 完成")

        if stats:
            self.lbl_posts_found.setText(f"找到帖子: {stats.get('posts_found', 0)}")
            self.lbl_posts_new.setText(f"新帖子: {stats.get('posts_new', 0)}")
            self.lbl_thanks_sent.setText(f"感謝成功: {stats.get('thanks_sent', 0)}")
            self.lbl_links_extracted.setText(f"提取連結: {stats.get('links_extracted', 0)}")

            # 顯示通知
            total_links = stats.get('links_extracted', 0)
            new_links = stats.get('posts_new', 0)
            self.notification_manager.notify_crawl_complete(total_links, new_links)

            # 如果有提取連結，啟動 JD 狀態輪詢器
            if total_links > 0:
                self._start_jd_polling()

            # 刷新網頁下載記錄
            web_downloads = stats.get('web_downloads', 0)
            if web_downloads > 0 and hasattr(self, 'web_download_widget'):
                self.web_download_widget.load_data()

    def _start_jd_polling(self):
        """啟動 JDownloader 狀態輪詢"""
        try:
            from ..downloader.jd_status_poller import JDStatusPoller
            from ..database.db_manager import DatabaseManager

            # 取得 JD 路徑
            jd_exe = self.config.get('jdownloader', {}).get('exe_path', '')
            if not jd_exe:
                self._append_log("[JD監控] 未設定 JDownloader 路徑，無法監控下載狀態")
                return

            from pathlib import Path
            jd_exe_path = Path(jd_exe)

            # 嘗試找到正確的 JD 路徑 (支援 Portable 版本)
            jd_path = None
            possible_paths = [
                jd_exe_path.parent,  # 普通安裝
                jd_exe_path.parent.parent.parent,  # Portable: App/JDownloader2/JDownloader2.exe
            ]

            for p in possible_paths:
                cfg_path = p / 'cfg'
                if not cfg_path.exists():
                    cfg_path = p / 'App' / 'JDownloader2' / 'cfg'
                if cfg_path.exists():
                    jd_path = str(p)
                    self._append_log(f"[JD監控] 找到 JD cfg 路徑: {cfg_path}")
                    break

            if not jd_path:
                jd_path = str(jd_exe_path.parent)
                self._append_log(f"[JD監控] 使用預設路徑: {jd_path}")

            # 建立或重用輪詢器
            if self.jd_poller is None:
                self.jd_poller = JDStatusPoller(jd_path, self)
                self.jd_poller.file_complete.connect(self._on_jd_file_complete)
                self.jd_poller.all_complete.connect(self._on_jd_all_complete)
                self.jd_poller.progress_updated.connect(self._on_jd_progress)
                self._append_log(f"[JD監控] 建立輪詢器，JD 路徑: {jd_path}")
            else:
                # 重置現有輪詢器
                self.jd_poller.reset()
                self._append_log("[JD監控] 重置現有輪詢器")

            # 設定預期的檔案列表 (從資料庫取得最近送到 JD 的記錄)
            db = DatabaseManager()
            pending = db.get_pending_jd_downloads()
            self._append_log(f"[JD監控] 資料庫查詢到 {len(pending)} 個待下載項目")

            if pending:
                expected_files = []
                for record in pending:
                    pkg_name = record.get('jd_package_name') or record.get('title')
                    expected_files.append({
                        'tid': record.get('thread_id'),
                        'package_name': pkg_name,
                        'filename': record.get('archive_filename'),
                        'link_url': record.get('link_url')
                    })
                    self._append_log(f"[JD監控] 預期: {pkg_name[:50]}...")

                self.jd_poller.set_expected_files(expected_files)
                self.jd_poller.start_polling(interval=15000)  # 每 15 秒檢查一次
                self._append_log(f"[JD監控] 開始輪詢 ({len(expected_files)} 個檔案，間隔 15 秒)")
            else:
                self._append_log("[JD監控] 沒有待下載的檔案，跳過監控")

        except Exception as e:
            self._append_log(f"[JD監控] 啟動失敗: {e}")
            import traceback
            self._append_log(traceback.format_exc())

    def _on_jd_file_complete(self, package_name: str, filename: str):
        """單一檔案下載完成"""
        self._append_log(f"[JD] 下載完成: {package_name}")
        self._append_log(f"[JD] 實際檔名: {filename if filename else '(未取得)'}")

    def _on_jd_progress(self, completed: int, total: int):
        """JD 下載進度更新"""
        self.crawler_status.setText(f"狀態: JD 下載中 ({completed}/{total})")

    def _on_jd_all_complete(self, count: int):
        """所有 JD 下載完成"""
        self._append_log(f"[JD] 全部 {count} 個檔案下載完成！")
        self.crawler_status.setText("狀態: JD 下載完成")
        self.notification_manager.show_toast(
            "下載完成",
            f"JDownloader 已完成 {count} 個檔案下載",
            notification_type="success"
        )

    def _start_extract_monitor(self):
        """開始批次解壓"""
        self.btn_start_extract.setEnabled(False)
        self.btn_stop_extract.setEnabled(True)
        self.extract_status.setText("狀態: 啟動中...")

        config = self.config.copy()
        config['extract_interval'] = self.spin_extract_interval.value()

        # 批次解壓模式: 同步 JD 檔名 → 處理全部 → 結束
        self.extract_worker = ExtractWorker(config)
        self.extract_worker.log_signal.connect(self._append_log)
        self.extract_worker.status_signal.connect(
            lambda s: self.extract_status.setText(f"狀態: {s}")
        )
        self.extract_worker.finished_signal.connect(self._extract_monitor_finished)
        self.extract_worker.auto_stopped_signal.connect(self._on_extract_auto_stopped)
        self.extract_worker.start()

        self.notification_manager.notify_extract_started()

    def _stop_extract_monitor(self):
        """停止解壓監控"""
        if self.extract_worker:
            self.extract_worker.stop()
            self.extract_worker.wait(5000)
            self.extract_worker = None

        self.btn_start_extract.setEnabled(True)
        self.btn_stop_extract.setEnabled(False)
        self.extract_status.setText("狀態: 已停止")

    def _extract_monitor_finished(self, stats: dict):
        """解壓監控完成"""
        self.btn_start_extract.setEnabled(True)
        self.btn_stop_extract.setEnabled(False)

        success = stats.get('total_success', 0)
        failed = stats.get('total_failed', 0)
        self.notification_manager.notify_extract_complete(success, failed)

        # 顯示放棄的檔案
        blacklisted = stats.get('blacklisted_files', [])
        if blacklisted:
            self._append_log(f"以下檔案因失敗次數過多而放棄: {', '.join(blacklisted)}")

    def _on_extract_auto_stopped(self, reason: str):
        """解壓監控自動停止"""
        self.notification_manager.notify_extract_auto_stopped(reason)
        self.extract_worker = None

    def _append_log(self, message: str):
        """添加日誌"""
        self.log_text.append(message)
        # 自動滾動到底部
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)

    def _show_about(self):
        """顯示關於對話框"""
        from ..version import get_about_text, APP_NAME
        QMessageBox.about(
            self,
            f"關於 {APP_NAME}",
            get_about_text()
        )

    def _check_for_updates_startup(self):
        """啟動時背景檢查更新"""
        from .update_dialog import UpdateCheckWorker, UpdateSettings

        settings = UpdateSettings()
        if not settings.is_auto_check_enabled():
            return

        self._update_worker = UpdateCheckWorker(use_cache=True)
        self._update_worker.finished.connect(self._on_update_check_finished)
        self._update_worker.start()

    def _check_for_updates_manual(self):
        """手動檢查更新"""
        from .update_dialog import UpdateCheckWorker

        self.statusBar().showMessage("正在檢查更新...")

        self._update_worker = UpdateCheckWorker(use_cache=False)
        self._update_worker.finished.connect(
            lambda result: self._on_update_check_finished(result, show_no_update=True)
        )
        self._update_worker.error.connect(
            lambda err: QMessageBox.warning(self, "檢查更新失敗", f"無法檢查更新:\n{err}")
        )
        self._update_worker.start()

    def _on_update_check_finished(self, result, show_no_update: bool = False):
        """更新檢查完成"""
        from .update_dialog import UpdateDialog, UpdateSettings

        self.statusBar().clearMessage()

        if result.has_error:
            if show_no_update:
                QMessageBox.warning(self, "檢查更新", f"檢查更新時發生錯誤:\n{result.error}")
            return

        if result.available:
            # 檢查是否跳過此版本
            settings = UpdateSettings()
            if not show_no_update and not settings.should_show_update(result.latest_version):
                return

            # 顯示更新對話框
            dialog = UpdateDialog(result, self)
            dialog.exec()

            # 儲存跳過的版本
            skipped = dialog.get_skipped_version()
            if skipped:
                settings.set_skipped_version(skipped)
        else:
            if show_no_update:
                from ..version import VERSION
                QMessageBox.information(
                    self,
                    "檢查更新",
                    f"您使用的已是最新版本。\n\n目前版本: v{VERSION}"
                )

    def _refresh_history(self):
        """重新整理下載歷史"""
        try:
            from ..database.db_manager import DatabaseManager
            db = DatabaseManager()

            # 同步 JDownloader 實際下載檔名到資料庫
            self._sync_jd_filenames_to_db(db)

            # 更新統計資訊
            stats = db.get_download_stats()
            self.lbl_total_posts.setText(f"總帖子: {stats.get('total_posts', 0)}")
            self.lbl_total_downloads.setText(f"總下載: {stats.get('total_downloads', 0)}")

            # 更新歷史記錄表格 - 按 tid 合併記錄
            history = db.get_download_history(limit=500)
            merged = self._merge_history_by_tid(history)

            # 暫停 UI 更新以提升效能
            self.history_table.setUpdatesEnabled(False)
            self.history_table.setRowCount(len(merged))

            for row, record in enumerate(merged):
                tid = record.get('thread_id', '')
                title = record.get('title', '')
                download_count = record.get('download_count', 1)

                # TID
                self.history_table.setItem(row, 0, QTableWidgetItem(tid))

                # 標題 - 儲存完整記錄供雙擊使用
                title_item = QTableWidgetItem(title)
                title_item.setData(Qt.ItemDataRole.UserRole, record)
                self.history_table.setItem(row, 1, title_item)

                # 下載次數 - 可點擊，帶醒目顯示
                count_item = QTableWidgetItem(f"[{download_count}]")
                count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                count_item.setData(Qt.ItemDataRole.UserRole, tid)

                # 根據次數設定顏色
                if download_count >= 3:
                    count_item.setForeground(QColor(*NordColors.AURORA_RED))  # 紅色
                    count_item.setFont(QFont("", -1, QFont.Weight.Bold))
                elif download_count >= 2:
                    count_item.setForeground(QColor(*NordColors.AURORA_ORANGE))  # 橘色

                self.history_table.setItem(row, 2, count_item)

                # 類型
                link_types = record.get('link_types', [])
                type_text = ', '.join(set(link_types)) if link_types else ''
                self.history_table.setItem(row, 3, QTableWidgetItem(type_text))

                # 壓縮檔名
                archive_names = record.get('archive_filenames', [])
                archive_text = archive_names[0] if archive_names else ''
                archive_item = QTableWidgetItem(archive_text[:30] + '...' if len(archive_text) > 30 else archive_text)
                archive_item.setToolTip('\n'.join(archive_names) if archive_names else '')
                self.history_table.setItem(row, 4, archive_item)

                # 密碼 - 可點擊複製
                password = record.get('password', '') or ''
                password_item = QTableWidgetItem(password)
                if password:
                    password_item.setForeground(QColor(*NordColors.AURORA_RED))
                self.history_table.setItem(row, 5, password_item)

                # 版區
                self.history_table.setItem(row, 6, QTableWidgetItem(record.get('forum_section', '')))

                # 建立時間
                created = record.get('created_at', '')
                if created:
                    created = created[:16].replace('T', ' ')
                self.history_table.setItem(row, 7, QTableWidgetItem(created))

            # 恢復 UI 更新
            self.history_table.setUpdatesEnabled(True)

            self.statusBar().showMessage(f"已載入 {len(merged)} 筆記錄 ({len(history)} 個連結)", 3000)

        except Exception as e:
            QMessageBox.warning(self, "錯誤", f"載入歷史記錄失敗: {e}")

    def _clear_download_history(self):
        """清空下載歷史"""
        if self.history_table.rowCount() == 0:
            QMessageBox.information(self, "提示", "沒有記錄可清空")
            return

        reply = QMessageBox.question(
            self, "確認",
            "確定要清空所有下載歷史記錄嗎？\n此操作無法復原。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                from ..database.db_manager import DatabaseManager
                db = DatabaseManager()
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM downloads')
                    cursor.execute('DELETE FROM posts')
                self._refresh_history()
                self.statusBar().showMessage("已清空下載歷史", 3000)
            except Exception as e:
                QMessageBox.warning(self, "錯誤", f"清空失敗: {e}")

    def _merge_history_by_tid(self, history: list) -> list:
        """按 thread_id 合併下載歷史記錄"""
        merged = {}
        for record in history:
            tid = record.get('thread_id', '')
            if tid not in merged:
                merged[tid] = {
                    'thread_id': tid,
                    'title': record.get('title', ''),
                    'post_url': record.get('post_url', ''),
                    'forum_section': record.get('forum_section', ''),
                    'password': record.get('password', ''),
                    'sent_to_jd_at': record.get('sent_to_jd_at', ''),
                    'extract_success': record.get('extract_success'),
                    'created_at': record.get('created_at', ''),
                    'download_count': 0,
                    'link_types': [],
                    'archive_filenames': [],
                    'link_urls': []
                }
            m = merged[tid]
            m['download_count'] += 1

            # 收集連結類型
            link_type = record.get('link_type', '')
            if link_type and link_type not in m['link_types']:
                m['link_types'].append(link_type)

            # 收集壓縮檔名 - 優先使用 jd_actual_filename（JD 實際下載的檔名）
            jd_actual = record.get('jd_actual_filename', '')
            archive_name = record.get('archive_filename', '')
            # 優先用 JD 實際檔名
            filename_to_use = jd_actual or archive_name
            if filename_to_use:
                for name in filename_to_use.split('|'):
                    if name and name not in m['archive_filenames']:
                        m['archive_filenames'].append(name)

            # 收集連結
            link_url = record.get('link_url', '')
            if link_url and link_url not in m['link_urls']:
                m['link_urls'].append(link_url)

            # 保留最新時間
            if record.get('created_at', '') > m['created_at']:
                m['created_at'] = record.get('created_at', '')

            # 保留密碼
            if record.get('password') and not m['password']:
                m['password'] = record.get('password')

            # 保留解壓狀態（優先顯示成功）
            if record.get('extract_success') is True:
                m['extract_success'] = True
            elif m['extract_success'] is None and record.get('extract_success') is False:
                m['extract_success'] = False

        # 轉換為列表並按時間排序
        result = list(merged.values())
        result.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return result

    def _sync_jd_filenames_to_db(self, db):
        """從 JDownloader 同步實際下載檔名到資料庫"""
        try:
            # 取得 JDownloader 路徑
            jd_folder = self.config.get('jdownloader', {}).get('folderwatch_path', '')
            if not jd_folder:
                return

            # 從 folderwatch 路徑推算 JD 根目錄
            from pathlib import Path
            jd_path = Path(jd_folder)
            # folderwatch 通常在 JDownloader2/folderwatch 或 App/JDownloader2/folderwatch
            while jd_path.name not in ('JDownloader2', 'JDownloader', '') and jd_path.parent != jd_path:
                jd_path = jd_path.parent
            if jd_path.name == '':
                return

            # 如果是 App/JDownloader2 結構，往上一層
            if jd_path.parent.name == 'App':
                jd_path = jd_path.parent.parent

            from ..downloader.jd_history_reader import JDHistoryReader
            reader = JDHistoryReader(str(jd_path))

            # 讀取已完成的下載
            completed = reader.get_completed_downloads()
            if not completed:
                return

            updated_count = 0
            for record in completed:
                package_name = record.get('package_name', '')
                file_name = record.get('file_name', '')

                if package_name and file_name:
                    # 嘗試更新資料庫
                    count = db.update_jd_actual_filename(package_name, file_name)
                    if count > 0:
                        updated_count += count

            if updated_count > 0:
                from ..utils.logger import logger
                logger.info(f"已從 JD 同步 {updated_count} 筆檔名記錄")

        except Exception as e:
            from ..utils.logger import logger
            logger.debug(f"同步 JD 檔名時發生錯誤: {e}")

    def _on_history_cell_clicked(self, row: int, column: int):
        """處理歷史表格點擊 - 密碼複製、下載次數詳細"""
        # 密碼欄位 (column 5) - 點擊複製
        if column == 5:
            item = self.history_table.item(row, column)
            if item:
                password = item.text()
                if password:
                    from PyQt6.QtWidgets import QApplication
                    from PyQt6.QtGui import QCursor
                    clipboard = QApplication.clipboard()
                    clipboard.setText(password)
                    QToolTip.showText(QCursor.pos(), "複製成功", self.history_table, self.history_table.rect(), 1500)
            return

        # 下載次數欄位 (column 2) - 彈出詳細記錄
        if column == 2:
            item = self.history_table.item(row, 2)
            if not item:
                return

            tid = item.data(Qt.ItemDataRole.UserRole)
            if not tid:
                return

            # 取得標題
            title_item = self.history_table.item(row, 1)
            title = title_item.text() if title_item else ""

            # 取得下載時間記錄並顯示對話框
            try:
                from ..database.db_manager import DatabaseManager
                db = DatabaseManager()
                times = db.get_download_times(tid)

                if times:
                    dialog = DownloadTimesDialog(tid, title, times, self)
                    dialog.exec()
            except Exception as e:
                self._append_log(f"載入下載時間失敗: {e}")

    def _on_history_cell_double_clicked(self, row: int, column: int):
        """處理歷史表格雙擊 - 開啟帖子頁面"""
        import webbrowser
        title_item = self.history_table.item(row, 1)
        if title_item:
            record = title_item.data(Qt.ItemDataRole.UserRole)
            if record:
                post_url = record.get('post_url', '')
                if post_url:
                    if not post_url.startswith('http'):
                        post_url = f"https://fastzone.org/{post_url}"
                    webbrowser.open(post_url)

    def _on_history_search_changed(self, text: str):
        """搜尋文字變更"""
        self._apply_history_filter()

    def _apply_history_filter(self):
        """套用歷史記錄篩選"""
        search_text = self.history_search.text().lower()

        for row in range(self.history_table.rowCount()):
            # 取得各欄位資料
            title_item = self.history_table.item(row, 1)  # 標題
            password_item = self.history_table.item(row, 5)  # 密碼
            section_item = self.history_table.item(row, 6)  # 版區

            title = title_item.text().lower() if title_item else ''
            password = password_item.text().lower() if password_item else ''
            section = section_item.text().lower() if section_item else ''

            # 搜尋條件
            match_search = (
                not search_text or
                search_text in title or
                search_text in password or
                search_text in section
            )

            # 顯示或隱藏行
            self.history_table.setRowHidden(row, not match_search)

    def _on_history_context_menu(self, pos):
        """顯示歷史記錄右鍵選單"""
        row = self.history_table.rowAt(pos.y())
        if row < 0:
            return

        title_item = self.history_table.item(row, 1)
        if not title_item:
            return

        record = title_item.data(Qt.ItemDataRole.UserRole)
        if not record:
            return

        menu = QMenu(self)

        # 開啟帖子
        action_open_post = QAction("開啟帖子頁面", self)
        action_open_post.triggered.connect(lambda: self._open_post_from_record(record))
        menu.addAction(action_open_post)

        menu.addSeparator()

        # 複製密碼
        password = record.get('password', '')
        if password:
            action_copy_password = QAction(f"複製密碼: {password}", self)
            action_copy_password.triggered.connect(lambda: self._copy_to_clipboard(password, "密碼"))
            menu.addAction(action_copy_password)

        # 複製標題
        action_copy_title = QAction("複製標題", self)
        action_copy_title.triggered.connect(lambda: self._copy_to_clipboard(record.get('title', ''), "標題"))
        menu.addAction(action_copy_title)

        # 複製 TID
        action_copy_tid = QAction(f"複製 TID: {record.get('thread_id', '')}", self)
        action_copy_tid.triggered.connect(lambda: self._copy_to_clipboard(record.get('thread_id', ''), "TID"))
        menu.addAction(action_copy_tid)

        menu.addSeparator()

        # 複製下載連結
        link_urls = record.get('link_urls', [])
        if link_urls:
            action_copy_links = QAction(f"複製下載連結 ({len(link_urls)} 個)", self)
            action_copy_links.triggered.connect(lambda: self._copy_to_clipboard('\n'.join(link_urls), "下載連結"))
            menu.addAction(action_copy_links)

        menu.exec(self.history_table.mapToGlobal(pos))

    def _open_post_from_record(self, record: dict):
        """從記錄開啟帖子頁面"""
        import webbrowser
        post_url = record.get('post_url', '')
        if post_url:
            if not post_url.startswith('http'):
                post_url = f"https://fastzone.org/{post_url}"
            webbrowser.open(post_url)

    def _copy_to_clipboard(self, text: str, label: str = ""):
        """複製文字到剪貼簿"""
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QCursor
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        QToolTip.showText(QCursor.pos(), f"已複製{label}", self, self.rect(), 1500)

    def _show_clear_records_dialog(self):
        """顯示清除記錄對話框"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QRadioButton, QButtonGroup

        dialog = QDialog(self)
        dialog.setWindowTitle("清除記錄")
        dialog.setMinimumWidth(350)
        layout = QVBoxLayout(dialog)

        # 取得 UI 設定值
        retention_days = self.spin_retention_days.value()
        thanked_years = self.spin_thanked_retention_years.value()

        # 清除選項
        radio_group = QButtonGroup(dialog)

        radio_by_days = QRadioButton(f"清除超過 {retention_days} 天的舊記錄")
        radio_by_days.setChecked(True)
        radio_group.addButton(radio_by_days, 1)
        layout.addWidget(radio_by_days)

        radio_all = QRadioButton("清除全部記錄")
        radio_group.addButton(radio_all, 2)
        layout.addWidget(radio_all)

        # 說明文字
        info_label = QLabel(
            f"\n說明：\n"
            f"• 感謝記錄將保留 {thanked_years} 年（避免重複感謝）\n"
            f"• 此操作無法復原"
        )
        info_label.setStyleSheet("color: gray;")
        layout.addWidget(info_label)

        # 按鈕
        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(dialog.reject)
        btn_confirm = QPushButton("確定清除")
        btn_confirm.setStyleSheet("background-color: #d9534f; color: white;")
        btn_confirm.clicked.connect(dialog.accept)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_confirm)
        layout.addLayout(btn_layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            is_clear_all = (radio_group.checkedId() == 2)

            # 全部清除需要二次確認
            if is_clear_all:
                confirm = QMessageBox.warning(
                    self, "警告",
                    "確定要清除所有記錄嗎？\n\n"
                    f"• 所有帖子、下載記錄和執行歷史將被刪除\n"
                    f"• 感謝記錄將保留 {thanked_years} 年\n"
                    "• 此操作無法復原！",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if confirm != QMessageBox.StandardButton.Yes:
                    return

            try:
                from ..database.db_manager import DatabaseManager
                db = DatabaseManager()
                result = db.clear_records(
                    retention_days=retention_days if not is_clear_all else 0,
                    thanked_retention_years=thanked_years
                )

                msg = f"已清除:\n" \
                      f"- 帖子: {result['deleted_posts']} 筆\n" \
                      f"- 下載記錄: {result['deleted_downloads']} 筆\n" \
                      f"- 網頁下載: {result['deleted_web_downloads']} 筆\n" \
                      f"- 執行記錄: {result['deleted_runs']} 筆"

                if result.get('deleted_thanked', 0) > 0:
                    msg += f"\n- 過期感謝記錄: {result['deleted_thanked']} 筆"

                QMessageBox.information(self, "清除完成", msg)

                # 重新整理歷史
                self._refresh_history()

            except Exception as e:
                QMessageBox.warning(self, "錯誤", f"清除失敗: {e}")

    # ===== 設定檔管理方法 =====

    def _refresh_profile_list(self):
        """重新整理設定檔列表"""
        self.combo_profile.blockSignals(True)
        self.combo_profile.clear()

        profiles = self.profile_manager.get_profile_list()
        for p in profiles:
            self.combo_profile.addItem(p['name'])

        # 選擇目前的設定檔
        current = self.profile_manager.get_current_profile()
        index = self.combo_profile.findText(current)
        if index >= 0:
            self.combo_profile.setCurrentIndex(index)

        self.combo_profile.blockSignals(False)

    def _on_profile_changed(self, name: str):
        """設定檔切換事件"""
        if not name or name == self.current_profile:
            return

        # 詢問是否儲存目前設定
        reply = QMessageBox.question(
            self, "切換設定檔",
            f"是否先儲存目前設定檔「{self.current_profile}」的變更？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Cancel:
            # 取消切換，恢復選擇
            self._refresh_profile_list()
            return

        if reply == QMessageBox.StandardButton.Yes:
            self._save_config()

        # 切換設定檔
        if self.profile_manager.set_current_profile(name):
            self.current_profile = name
            self.config_path = self.profile_manager.get_profile_config_path()
            self.config = self._load_config()
            self._load_settings_to_ui()
            self._update_window_title()
            self.statusBar().showMessage(f"已切換到設定檔: {name}", 3000)
        else:
            QMessageBox.warning(self, "錯誤", f"切換設定檔失敗: {name}")
            self._refresh_profile_list()

    def _create_new_profile(self):
        """建立新設定檔"""
        name, ok = QInputDialog.getText(
            self, "新增設定檔",
            "請輸入設定檔名稱 (最多10個字):",
            QLineEdit.EchoMode.Normal, ""
        )

        if ok and name:
            name = name.strip()[:10]
            if not name:
                QMessageBox.warning(self, "錯誤", "設定檔名稱不能為空")
                return

            if self.profile_manager.create_profile(name, description=""):
                self._refresh_profile_list()
                self.statusBar().showMessage(f"已建立設定檔: {name}", 3000)
            else:
                QMessageBox.warning(self, "錯誤", "建立設定檔失敗，可能名稱已存在或超過數量限制")

    def _copy_profile(self):
        """複製目前設定檔"""
        name, ok = QInputDialog.getText(
            self, "複製設定檔",
            f"複製「{self.current_profile}」為新設定檔，請輸入名稱 (最多10個字):",
            QLineEdit.EchoMode.Normal, f"{self.current_profile}_複製"[:10]
        )

        if ok and name:
            name = name.strip()[:10]
            if not name:
                QMessageBox.warning(self, "錯誤", "設定檔名稱不能為空")
                return

            # 先儲存目前設定
            self._save_config()

            if self.profile_manager.create_profile(name, copy_from=self.current_profile):
                self._refresh_profile_list()
                self.statusBar().showMessage(f"已複製設定檔: {name}", 3000)
            else:
                QMessageBox.warning(self, "錯誤", "複製設定檔失敗，可能名稱已存在或超過數量限制")

    def _rename_profile(self):
        """重新命名設定檔"""
        new_name, ok = QInputDialog.getText(
            self, "重新命名設定檔",
            f"將「{self.current_profile}」重新命名為 (最多10個字):",
            QLineEdit.EchoMode.Normal, self.current_profile
        )

        if ok and new_name:
            new_name = new_name.strip()[:10]
            if not new_name:
                QMessageBox.warning(self, "錯誤", "設定檔名稱不能為空")
                return

            if new_name == self.current_profile:
                return

            if self.profile_manager.rename_profile(self.current_profile, new_name):
                self.current_profile = new_name
                self.config_path = self.profile_manager.get_profile_config_path()
                self._refresh_profile_list()
                self._update_window_title()
                self.statusBar().showMessage(f"已重新命名設定檔: {new_name}", 3000)
            else:
                QMessageBox.warning(self, "錯誤", "重新命名失敗，可能名稱已存在")

    def _delete_profile(self):
        """刪除設定檔"""
        profiles = self.profile_manager.get_profile_list()
        if len(profiles) <= 1:
            QMessageBox.warning(self, "錯誤", "至少要保留一個設定檔")
            return

        reply = QMessageBox.warning(
            self, "確認刪除",
            f"確定要刪除設定檔「{self.current_profile}」嗎？\n\n"
            "此操作無法復原！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            old_name = self.current_profile
            if self.profile_manager.delete_profile(old_name):
                # 切換到新的目前設定檔
                self.current_profile = self.profile_manager.get_current_profile()
                self.config_path = self.profile_manager.get_profile_config_path()
                self.config = self._load_config()
                self._refresh_profile_list()
                self._load_settings_to_ui()
                self._update_window_title()
                self.statusBar().showMessage(f"已刪除設定檔: {old_name}", 3000)
            else:
                QMessageBox.warning(self, "錯誤", "刪除設定檔失敗")

    def closeEvent(self, event):
        """關閉視窗事件"""
        # 停止所有工作執行緒
        if self.crawler_worker and self.crawler_worker.isRunning():
            self.crawler_worker.stop()
            if not self.crawler_worker.wait(3000):
                self.crawler_worker.terminate()

        if self.extract_worker and self.extract_worker.isRunning():
            self.extract_worker.stop()
            if not self.extract_worker.wait(3000):
                self.extract_worker.terminate()

        if self.search_download_worker and self.search_download_worker.isRunning():
            self.search_download_worker.stop()
            if not self.search_download_worker.wait(3000):
                self.search_download_worker.terminate()

        # 停止 JD 輪詢器
        if self.jd_poller and self.jd_poller.is_polling():
            self.jd_poller.stop_polling("程式關閉")

        event.accept()
