"""
DLP01 GUI 主視窗
使用 PyQt6 建立的圖形介面
"""
import sys
import os
import threading
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QTextEdit, QGroupBox,
    QTabWidget, QFileDialog, QMessageBox, QListWidget, QListWidgetItem,
    QCheckBox, QComboBox, QProgressBar, QStatusBar, QMenuBar, QMenu,
    QSplitter, QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QDialogButtonBox, QInputDialog, QTreeWidget, QTreeWidgetItem,
    QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QAction, QFont, QTextCursor

import yaml

from .extract_settings_widget import ExtractSettingsWidget
from .extract_history_widget import ExtractHistoryWidget


class LogHandler:
    """捕捉 logger 輸出並發送到 GUI"""
    def __init__(self, signal):
        self.signal = signal

    def write(self, message):
        if message.strip():
            self.signal.emit(message.strip())

    def flush(self):
        pass


class CrawlerWorker(QThread):
    """爬蟲工作執行緒"""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)
    progress_signal = pyqtSignal(int, int)  # current, total

    def __init__(self, config_path: str, dry_run: bool = False):
        super().__init__()
        self.config_path = config_path
        self.dry_run = dry_run
        self.is_running = True
        self.dlp = None  # 保存 DLP01 實例以便停止

    def run(self):
        try:
            from ..main import DLP01
            from ..utils.logger import logger
            import logging

            # 設定 logger 輸出到 GUI
            class GUIHandler(logging.Handler):
                def __init__(self, signal):
                    super().__init__()
                    self.signal = signal

                def emit(self, record):
                    msg = self.format(record)
                    self.signal.emit(msg)

            handler = GUIHandler(self.log_signal)
            handler.setFormatter(logging.Formatter('%(message)s'))
            logger.addHandler(handler)

            self.dlp = DLP01(config_path=self.config_path)
            self.dlp.run(dry_run=self.dry_run)

            self.finished_signal.emit(self.dlp.stats)

        except Exception as e:
            self.log_signal.emit(f"錯誤: {str(e)}")
            self.finished_signal.emit({})
        finally:
            self.dlp = None

    def stop(self):
        """請求停止爬蟲"""
        self.is_running = False
        if self.dlp:
            self.dlp.request_stop()


class ExtractWorker(QThread):
    """解壓監控工作執行緒"""
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.is_running = True
        self.monitor = None

    def run(self):
        try:
            from ..downloader.extract_monitor import ExtractMonitor
            from ..database.db_manager import DatabaseManager
            from ..utils.logger import logger
            import logging

            # 設定 logger
            class GUIHandler(logging.Handler):
                def __init__(self, signal):
                    super().__init__()
                    self.signal = signal

                def emit(self, record):
                    msg = self.format(record)
                    self.signal.emit(msg)

            handler = GUIHandler(self.log_signal)
            handler.setFormatter(logging.Formatter('%(message)s'))
            logger.addHandler(handler)

            # 取得 JDownloader 路徑
            jd_config = self.config.get('jdownloader', {})
            jd_exe = jd_config.get('exe_path', '')
            jd_path = None
            if jd_exe:
                # 從 exe 路徑推導 JD 安裝目錄
                from pathlib import Path
                jd_exe_path = Path(jd_exe)
                # JDownloader2.exe 通常在安裝目錄下
                if jd_exe_path.exists():
                    jd_path = str(jd_exe_path.parent)

            # 建立監控器
            self.monitor = ExtractMonitor(
                download_dir=self.config['paths']['download_dir'],
                extract_dir=self.config['paths']['extract_dir'],
                winrar_path=self.config['paths']['winrar_path'],
                jd_path=jd_path,
                config=self.config  # 傳遞完整設定，包含 extract 設定
            )

            if jd_path:
                self.log_signal.emit(f"已設定 JDownloader 路徑: {jd_path}")

            # 載入密碼
            try:
                db = DatabaseManager()
                passwords = db.get_all_passwords()
                for pwd in passwords:
                    self.monitor.add_password(pwd)

                mappings = db.get_passwords_with_titles()
                for m in mappings:
                    self.monitor.add_password_mapping(
                        m['package_name'] or m['title'],
                        m['password'],
                        m.get('archive_filename')  # 傳入壓縮檔名稱
                    )
                self.log_signal.emit(f"已載入 {len(passwords)} 個密碼, {len(mappings)} 個映射")
            except Exception as e:
                self.log_signal.emit(f"載入密碼失敗: {e}")

            # 持續監控
            interval = self.config.get('extract_interval', 60)
            self.status_signal.emit("監控中")

            while self.is_running:
                try:
                    processed = self.monitor.process_archives(delete_after=True)
                    if processed > 0:
                        self.log_signal.emit(f"已處理 {processed} 個壓縮檔")
                except Exception as e:
                    self.log_signal.emit(f"處理錯誤: {e}")

                # 分段等待，以便能夠及時停止
                for _ in range(interval):
                    if not self.is_running:
                        break
                    self.msleep(1000)

            self.status_signal.emit("已停止")

        except Exception as e:
            self.log_signal.emit(f"監控錯誤: {str(e)}")
            self.status_signal.emit("錯誤")

    def stop(self):
        self.is_running = False


class MainWindow(QMainWindow):
    """主視窗"""

    def __init__(self):
        super().__init__()

        # 初始化設定檔管理器
        from ..utils.profile_manager import ProfileManager
        self.profile_manager = ProfileManager()

        # 載入目前設定檔
        self.current_profile = self.profile_manager.get_current_profile()
        self.config_path = self.profile_manager.get_profile_config_path()
        self.config = self._load_config()

        self.crawler_worker: Optional[CrawlerWorker] = None
        self.extract_worker: Optional[ExtractWorker] = None

        self._init_ui()
        self._load_settings_to_ui()
        self._update_window_title()

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
        self.setWindowTitle(f"DLP01 - 論壇自動下載程式 【{self.current_profile}】")

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

        # 分頁 3: 版區設定
        self.tabs.addTab(self._create_sections_tab(), "版區設定")

        # 分頁 4: 下載歷史
        self.tabs.addTab(self._create_history_tab(), "下載歷史")

        # 分頁 5: 解壓記錄
        self.tabs.addTab(self._create_extract_history_tab(), "解壓記錄")

        # 分頁 6: 解壓縮設定
        self.tabs.addTab(self._create_extract_settings_tab(), "解壓縮設定")

        # 分頁 7: 進階設定
        self.tabs.addTab(self._create_advanced_tab(), "進階設定")

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

        # 說明選單
        help_menu = menubar.addMenu("說明")

        about_action = QAction("關於", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

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

        self.btn_start_extract = QPushButton("開始監控")
        self.btn_start_extract.setMinimumHeight(40)
        self.btn_start_extract.clicked.connect(self._start_extract_monitor)
        extract_layout.addWidget(self.btn_start_extract)

        self.btn_stop_extract = QPushButton("停止監控")
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
        info_label.setStyleSheet("color: #666; font-size: 11px;")
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

        # 關鍵字篩選
        filters_group = QGroupBox("標題關鍵字篩選")
        filters_layout = QVBoxLayout(filters_group)

        self.list_filters = QListWidget()
        filters_layout.addWidget(self.list_filters)

        filter_btn_layout = QHBoxLayout()

        btn_add_filter = QPushButton("新增")
        btn_add_filter.clicked.connect(self._add_filter)
        filter_btn_layout.addWidget(btn_add_filter)

        btn_remove_filter = QPushButton("移除")
        btn_remove_filter.clicked.connect(self._remove_filter)
        filter_btn_layout.addWidget(btn_remove_filter)

        filters_layout.addLayout(filter_btn_layout)

        layout.addWidget(filters_group)

        # 儲存按鈕
        btn_save = QPushButton("儲存設定")
        btn_save.clicked.connect(self._save_sections_settings)
        layout.addWidget(btn_save)

        return tab

    def _create_history_tab(self) -> QWidget:
        """建立下載歷史分頁"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 統計資訊
        stats_group = QGroupBox("下載統計")
        stats_layout = QGridLayout(stats_group)

        self.lbl_total_posts = QLabel("總帖子: 0")
        self.lbl_total_downloads = QLabel("總下載: 0")
        self.lbl_sent_to_jd = QLabel("已送JD: 0")
        self.lbl_extract_success = QLabel("解壓成功: 0")
        self.lbl_extract_failed = QLabel("解壓失敗: 0")
        self.lbl_pending_extract = QLabel("待解壓: 0")

        stats_layout.addWidget(self.lbl_total_posts, 0, 0)
        stats_layout.addWidget(self.lbl_total_downloads, 0, 1)
        stats_layout.addWidget(self.lbl_sent_to_jd, 0, 2)
        stats_layout.addWidget(self.lbl_extract_success, 1, 0)
        stats_layout.addWidget(self.lbl_extract_failed, 1, 1)
        stats_layout.addWidget(self.lbl_pending_extract, 1, 2)

        layout.addWidget(stats_group)

        # 歷史記錄表格
        history_group = QGroupBox("下載/解壓歷史")
        history_layout = QVBoxLayout(history_group)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(8)
        self.history_table.setHorizontalHeaderLabels([
            "標題", "類型", "密碼", "送JD時間", "解壓時間", "解壓狀態", "版區", "建立時間"
        ])

        # 設定欄寬
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # 標題自動延伸
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)

        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setAlternatingRowColors(True)

        history_layout.addWidget(self.history_table)

        # 按鈕列
        btn_layout = QHBoxLayout()

        btn_refresh = QPushButton("重新整理")
        btn_refresh.clicked.connect(self._refresh_history)
        btn_layout.addWidget(btn_refresh)

        btn_layout.addStretch()

        history_layout.addLayout(btn_layout)

        layout.addWidget(history_group)

        return tab

    def _create_extract_history_tab(self) -> QWidget:
        """建立解壓記錄分頁"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 統計資訊
        stats_group = QGroupBox("解壓統計")
        stats_layout = QGridLayout(stats_group)

        self.lbl_extract_success_count = QLabel("成功: 0")
        self.lbl_extract_failed_count = QLabel("失敗: 0")
        self.lbl_extract_pending_count = QLabel("待解壓: 0")
        self.lbl_total_files_extracted = QLabel("總檔案數: 0")
        self.lbl_total_files_filtered = QLabel("過濾檔案: 0")
        self.lbl_total_archive_size = QLabel("總壓縮大小: 0")

        stats_layout.addWidget(self.lbl_extract_success_count, 0, 0)
        stats_layout.addWidget(self.lbl_extract_failed_count, 0, 1)
        stats_layout.addWidget(self.lbl_extract_pending_count, 0, 2)
        stats_layout.addWidget(self.lbl_total_files_extracted, 1, 0)
        stats_layout.addWidget(self.lbl_total_files_filtered, 1, 1)
        stats_layout.addWidget(self.lbl_total_archive_size, 1, 2)

        layout.addWidget(stats_group)

        # 解壓記錄元件
        self.extract_history_widget = ExtractHistoryWidget()
        self.extract_history_widget.refresh_requested.connect(self._refresh_extract_history)
        layout.addWidget(self.extract_history_widget)

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

    def _refresh_extract_history(self):
        """重新整理解壓記錄"""
        try:
            from ..database.db_manager import DatabaseManager
            db = DatabaseManager()

            # 更新統計資訊
            stats = db.get_extraction_stats()
            self.lbl_extract_success_count.setText(f"成功: {stats.get('success_count', 0)}")
            self.lbl_extract_failed_count.setText(f"失敗: {stats.get('failed_count', 0)}")
            self.lbl_extract_pending_count.setText(f"待解壓: {stats.get('pending_count', 0)}")
            self.lbl_total_files_extracted.setText(f"總檔案數: {stats.get('total_files_extracted', 0)}")
            self.lbl_total_files_filtered.setText(f"過濾檔案: {stats.get('total_files_filtered', 0)}")

            # 格式化總大小
            total_size = stats.get('total_archive_size', 0) or 0
            if total_size < 1024 * 1024 * 1024:
                size_str = f"{total_size / 1024 / 1024:.1f} MB"
            else:
                size_str = f"{total_size / 1024 / 1024 / 1024:.2f} GB"
            self.lbl_total_archive_size.setText(f"總壓縮大小: {size_str}")

            # 載入解壓記錄
            records = db.get_extraction_history(limit=200)

            # 取得巢狀記錄
            nested_records = {}
            for record in records:
                record_id = record.get('id')
                if record_id:
                    nested = db.get_nested_extractions(record_id)
                    if nested:
                        nested_records[record_id] = nested

            # 載入到元件
            self.extract_history_widget.load_records(records, nested_records)

            self.statusBar().showMessage(f"已載入 {len(records)} 筆解壓記錄", 3000)

        except Exception as e:
            QMessageBox.warning(self, "錯誤", f"載入解壓記錄失敗: {e}")

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

        db_layout.addWidget(QLabel("記錄保留天數:"), 0, 0)
        self.spin_retention_days = QSpinBox()
        self.spin_retention_days.setRange(7, 365)
        self.spin_retention_days.setValue(30)
        db_layout.addWidget(self.spin_retention_days, 0, 1)

        btn_cleanup = QPushButton("清理舊記錄")
        btn_cleanup.clicked.connect(self._cleanup_old_records)
        db_layout.addWidget(btn_cleanup, 0, 2)

        db_layout.addWidget(QLabel(""), 1, 0)  # 空行

        btn_clear_all = QPushButton("一鍵清除所有記錄")
        btn_clear_all.setStyleSheet("background-color: #ff6b6b; color: white;")
        btn_clear_all.clicked.connect(self._clear_all_records)
        db_layout.addWidget(btn_clear_all, 2, 0, 1, 3)

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

        # 版區設定 (群組化)
        self._load_sections_to_tree()

        # 關鍵字篩選
        self.list_filters.clear()
        for f in self.config.get('forum', {}).get('title_filters', []):
            self.list_filters.addItem(f)

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

        self._save_config()

    def _get_cookie_path(self) -> Path:
        """取得 Cookie 檔案路徑"""
        cookie_file = self.config.get('auth', {}).get('cookie_file', 'config/cookies.json')
        return self.config_path.parent / cookie_file

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

        # 儲存關鍵字篩選
        filters = []
        for i in range(self.list_filters.count()):
            filters.append(self.list_filters.item(i).text())
        self.config['forum']['title_filters'] = filters

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
                group_item.setForeground(0, Qt.GlobalColor.gray)
                group_item.setForeground(2, Qt.GlobalColor.red)

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
                    section_item.setForeground(0, Qt.GlobalColor.gray)
                    section_item.setForeground(1, Qt.GlobalColor.gray)
                    section_item.setForeground(2, Qt.GlobalColor.red)

        self.tree_sections.blockSignals(False)

    def _on_section_item_changed(self, item, column):
        """當樹狀項目變更時"""
        pass  # 目前用按鈕控制，不用這個

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
            current.setForeground(0, Qt.GlobalColor.black)
            current.setForeground(1, Qt.GlobalColor.black)
            current.setForeground(2, Qt.GlobalColor.darkGreen)
        else:
            current.setForeground(0, Qt.GlobalColor.gray)
            current.setForeground(1, Qt.GlobalColor.gray)
            current.setForeground(2, Qt.GlobalColor.red)

        # 如果是群組，同時更新所有子版區的顯示
        if data.get('type') == 'group':
            for i in range(current.childCount()):
                child = current.child(i)
                if new_enabled:
                    child_data = child.data(0, Qt.ItemDataRole.UserRole)
                    child_enabled = child_data.get('enabled', True) if child_data else True
                    if child_enabled:
                        child.setForeground(0, Qt.GlobalColor.black)
                        child.setForeground(1, Qt.GlobalColor.black)
                        child.setForeground(2, Qt.GlobalColor.darkGreen)
                else:
                    child.setForeground(0, Qt.GlobalColor.gray)
                    child.setForeground(1, Qt.GlobalColor.gray)
                    child.setForeground(2, Qt.GlobalColor.red)

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

    def _add_filter(self):
        """新增關鍵字"""
        from PyQt6.QtWidgets import QInputDialog
        keyword, ok = QInputDialog.getText(self, "新增關鍵字", "關鍵字:")
        if ok and keyword:
            self.list_filters.addItem(keyword)
            if 'forum' not in self.config:
                self.config['forum'] = {}
            if 'title_filters' not in self.config['forum']:
                self.config['forum']['title_filters'] = []
            self.config['forum']['title_filters'].append(keyword)

    def _remove_filter(self):
        """移除關鍵字"""
        current_row = self.list_filters.currentRow()
        if current_row >= 0:
            self.list_filters.takeItem(current_row)
            if 'forum' in self.config and 'title_filters' in self.config['forum']:
                if current_row < len(self.config['forum']['title_filters']):
                    self.config['forum']['title_filters'].pop(current_row)

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
        """從瀏覽器自動導入 Cookie"""
        import json

        # 取得論壇域名
        base_url = self.config.get('forum', {}).get('base_url', 'https://fastzone.org')
        domain = base_url.replace('https://', '').replace('http://', '').split('/')[0]

        self.lbl_cookie_status.setText("Cookie 狀態: 正在讀取瀏覽器...")
        self.statusBar().showMessage("正在從瀏覽器讀取 Cookie...", 0)

        # 支援的瀏覽器及其 Cookie 路徑
        browsers = self._get_browser_cookie_paths()

        cookies_found = []
        browser_used = None

        for browser_name, cookie_path in browsers.items():
            if not cookie_path or not Path(cookie_path).exists():
                continue

            try:
                browser_cookies = self._read_browser_cookies(browser_name, cookie_path, domain)
                if browser_cookies:
                    cookies_found = browser_cookies
                    browser_used = browser_name
                    break
            except Exception as e:
                self._append_log(f"讀取 {browser_name} Cookie 失敗: {e}")

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
                "2. 瀏覽器正在執行中 (Cookie 檔案被鎖定)\n"
                "3. 瀏覽器版本不支援\n\n"
                "建議:\n"
                "- 關閉瀏覽器後再試\n"
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
        # 顯示目前使用的設定檔
        self._append_log("=" * 50)
        self._append_log(f"【開始爬取】使用設定檔: {self.current_profile}")
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
            dry_run=self.chk_dry_run.isChecked()
        )
        self.crawler_worker.log_signal.connect(self._append_log)
        self.crawler_worker.finished_signal.connect(self._crawler_finished)
        self.crawler_worker.start()

    def _stop_crawler(self):
        """停止爬取"""
        if self.crawler_worker:
            self.crawler_worker.stop()
            self.crawler_worker.wait(5000)
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

    def _start_extract_monitor(self):
        """開始解壓監控"""
        self.btn_start_extract.setEnabled(False)
        self.btn_stop_extract.setEnabled(True)
        self.extract_status.setText("狀態: 啟動中...")

        config = self.config.copy()
        config['extract_interval'] = self.spin_extract_interval.value()

        self.extract_worker = ExtractWorker(config)
        self.extract_worker.log_signal.connect(self._append_log)
        self.extract_worker.status_signal.connect(
            lambda s: self.extract_status.setText(f"狀態: {s}")
        )
        self.extract_worker.start()

    def _stop_extract_monitor(self):
        """停止解壓監控"""
        if self.extract_worker:
            self.extract_worker.stop()
            self.extract_worker.wait(5000)
            self.extract_worker = None

        self.btn_start_extract.setEnabled(True)
        self.btn_stop_extract.setEnabled(False)
        self.extract_status.setText("狀態: 已停止")

    def _append_log(self, message: str):
        """添加日誌"""
        self.log_text.append(message)
        # 自動滾動到底部
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)

    def _show_about(self):
        """顯示關於對話框"""
        QMessageBox.about(
            self,
            "關於 DLP01",
            "DLP01 - 論壇自動下載程式\n\n"
            "自動爬取 fastzone.org 論壇，\n"
            "篩選帖子並透過 JDownloader 下載。\n\n"
            "版本: 1.0.0"
        )

    def _refresh_history(self):
        """重新整理下載歷史"""
        try:
            from ..database.db_manager import DatabaseManager
            db = DatabaseManager()

            # 更新統計資訊
            stats = db.get_download_stats()
            self.lbl_total_posts.setText(f"總帖子: {stats.get('total_posts', 0)}")
            self.lbl_total_downloads.setText(f"總下載: {stats.get('total_downloads', 0)}")
            self.lbl_sent_to_jd.setText(f"已送JD: {stats.get('sent_to_jd', 0)}")
            self.lbl_extract_success.setText(f"解壓成功: {stats.get('extract_success', 0)}")
            self.lbl_extract_failed.setText(f"解壓失敗: {stats.get('extract_failed', 0)}")
            self.lbl_pending_extract.setText(f"待解壓: {stats.get('pending_extract', 0)}")

            # 更新歷史記錄表格
            history = db.get_download_history(limit=200)
            self.history_table.setRowCount(len(history))

            for row, record in enumerate(history):
                # 標題
                self.history_table.setItem(row, 0, QTableWidgetItem(record.get('title', '')))
                # 類型
                self.history_table.setItem(row, 1, QTableWidgetItem(record.get('link_type', '')))
                # 密碼
                self.history_table.setItem(row, 2, QTableWidgetItem(record.get('password', '')))
                # 送JD時間
                sent_time = record.get('sent_to_jd_at', '')
                if sent_time:
                    sent_time = sent_time[:16].replace('T', ' ')  # 格式化時間
                self.history_table.setItem(row, 3, QTableWidgetItem(sent_time))
                # 解壓時間
                extract_time = record.get('extracted_at', '')
                if extract_time:
                    extract_time = extract_time[:16].replace('T', ' ')
                self.history_table.setItem(row, 4, QTableWidgetItem(extract_time))
                # 解壓狀態
                extract_success = record.get('extract_success')
                if extract_success is None:
                    status = "未解壓"
                elif extract_success:
                    status = "成功"
                else:
                    status = "失敗"
                self.history_table.setItem(row, 5, QTableWidgetItem(status))
                # 版區
                self.history_table.setItem(row, 6, QTableWidgetItem(record.get('forum_section', '')))
                # 建立時間
                created = record.get('created_at', '')
                if created:
                    created = created[:16].replace('T', ' ')
                self.history_table.setItem(row, 7, QTableWidgetItem(created))

            self.statusBar().showMessage(f"已載入 {len(history)} 筆記錄", 3000)

        except Exception as e:
            QMessageBox.warning(self, "錯誤", f"載入歷史記錄失敗: {e}")

    def _cleanup_old_records(self):
        """清理舊記錄"""
        retention_days = self.spin_retention_days.value()

        reply = QMessageBox.question(
            self, "確認清理",
            f"確定要清理超過 {retention_days} 天的舊記錄嗎？\n此操作無法復原。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                from ..database.db_manager import DatabaseManager
                db = DatabaseManager()
                result = db.cleanup_old_records(retention_days)

                QMessageBox.information(
                    self, "清理完成",
                    f"已清理:\n"
                    f"- 帖子: {result['deleted_posts']} 筆\n"
                    f"- 下載記錄: {result['deleted_downloads']} 筆\n"
                    f"- 執行記錄: {result['deleted_runs']} 筆"
                )

                # 重新整理歷史
                self._refresh_history()

            except Exception as e:
                QMessageBox.warning(self, "錯誤", f"清理失敗: {e}")

    def _clear_all_records(self):
        """一鍵清除所有記錄"""
        reply = QMessageBox.warning(
            self, "警告",
            "確定要清除所有資料庫記錄嗎？\n\n"
            "這將刪除所有帖子、下載記錄和執行歷史！\n"
            "此操作無法復原！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 二次確認
            confirm = QMessageBox.question(
                self, "再次確認",
                "這是最後確認，真的要清除所有記錄嗎？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if confirm == QMessageBox.StandardButton.Yes:
                try:
                    from ..database.db_manager import DatabaseManager
                    db = DatabaseManager()
                    result = db.clear_all_records()

                    QMessageBox.information(
                        self, "清除完成",
                        f"已清除:\n"
                        f"- 帖子: {result['deleted_posts']} 筆\n"
                        f"- 下載記錄: {result['deleted_downloads']} 筆\n"
                        f"- 執行記錄: {result['deleted_runs']} 筆"
                    )

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
            self.crawler_worker.wait(3000)

        if self.extract_worker and self.extract_worker.isRunning():
            self.extract_worker.stop()
            self.extract_worker.wait(3000)

        event.accept()
