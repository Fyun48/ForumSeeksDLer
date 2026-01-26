"""
網頁下載 Widget
顯示無法透過 JDownloader 下載的連結記錄
"""
import webbrowser
import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QMessageBox, QAbstractItemView,
    QApplication, QToolTip, QMenu, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QFont, QColor, QCursor

from ..database.db_manager import DatabaseManager
from ..utils.logger import logger
from .styles import HINT_LABEL


class WebDownloadWidget(QWidget):
    """網頁下載記錄 Widget"""

    # 訊號
    refresh_requested = pyqtSignal()

    # 預設欄位寬度 [勾選, 標題, 關鍵字, 下載連結, 密碼, 狀態, 時間, 操作]
    DEFAULT_COLUMN_WIDTHS = [30, 300, 80, 200, 150, 60, 80, 60]

    def __init__(self, config_path: str = None, parent=None):
        super().__init__(parent)
        self.db = DatabaseManager()
        self.config_path = config_path
        self._settings_file = self._get_settings_file_path()
        self._init_ui()
        self._restore_column_widths()

    def _get_settings_file_path(self) -> Path:
        """取得設定檔路徑"""
        if self.config_path:
            return Path(self.config_path).parent / 'web_download_widget_settings.json'
        return Path.home() / '.dp01' / 'web_download_widget_settings.json'

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 標題與按鈕列
        header_layout = QHBoxLayout()

        lbl_title = QLabel("網頁下載")
        lbl_title.setFont(QFont("", 12, QFont.Weight.Bold))
        header_layout.addWidget(lbl_title)

        header_layout.addStretch()

        # 統計
        self.lbl_count = QLabel("共 0 筆記錄")
        header_layout.addWidget(self.lbl_count)

        header_layout.addStretch()

        # 操作按鈕
        btn_select_all = QPushButton("全選")
        btn_select_all.setToolTip("勾選所有項目")
        btn_select_all.clicked.connect(self._select_all)
        header_layout.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("取消全選")
        btn_deselect_all.setToolTip("取消勾選所有項目")
        btn_deselect_all.clicked.connect(self._deselect_all)
        header_layout.addWidget(btn_deselect_all)

        btn_open_checked = QPushButton("開啟勾選")
        btn_open_checked.setToolTip("開啟勾選項目的下載連結")
        btn_open_checked.clicked.connect(self._open_checked_links)
        header_layout.addWidget(btn_open_checked)

        btn_mark_selected = QPushButton("標記已下載")
        btn_mark_selected.setToolTip("將勾選的項目標記為已下載，並記錄到下載歷史")
        btn_mark_selected.clicked.connect(self._mark_checked_downloaded)
        header_layout.addWidget(btn_mark_selected)

        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self._refresh)
        header_layout.addWidget(btn_refresh)

        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self._clear_all)
        header_layout.addWidget(btn_clear)

        layout.addLayout(header_layout)

        # 說明文字
        lbl_hint = QLabel("提示：勾選項目後點擊「開啟勾選」開啟連結，雙擊標題開啟帖子頁面，點擊連結/密碼欄位複製")
        lbl_hint.setStyleSheet(HINT_LABEL)
        layout.addWidget(lbl_hint)

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "", "標題", "關鍵字", "下載連結", "密碼", "狀態", "時間", "操作"
        ])

        # 設定欄位寬度 - 允許使用者拖曳調整
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        # 勾選欄固定寬度
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 30)
        # 標題欄自動伸展填滿剩餘空間
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        # 監聽欄位寬度變更，自動儲存
        header.sectionResized.connect(self._on_column_resized)

        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # 啟用表格排序
        self.table.setSortingEnabled(True)

        # 雙擊開啟帖子
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        # 單擊密碼欄位複製
        self.table.cellClicked.connect(self._on_cell_clicked)

        # 右鍵選單
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)

        layout.addWidget(self.table)

    def _refresh(self):
        """刷新資料"""
        self.load_data()
        self.refresh_requested.emit()

    def load_data(self):
        """載入資料"""
        records = self.db.get_web_downloads(limit=500)
        # 按 thread_id 合併記錄
        merged = self._merge_records_by_tid(records)
        self._populate_table(merged)
        self.lbl_count.setText(f"共 {len(merged)} 筆記錄 ({len(records)} 個連結)")

    def _merge_records_by_tid(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按 thread_id 合併記錄，同一帖子的多個連結合併成一筆"""
        merged = {}
        for record in records:
            tid = record.get('thread_id', '')
            if tid not in merged:
                merged[tid] = {
                    'thread_id': tid,
                    'title': record.get('title', ''),
                    'post_url': record.get('post_url', ''),
                    'keyword': record.get('keyword', ''),
                    'password': record.get('password', ''),
                    'created_at': record.get('created_at', ''),
                    'downloaded_at': record.get('downloaded_at'),
                    'download_urls': []
                }
            # 收集所有下載連結
            url = record.get('download_url', '')
            if url and url not in merged[tid]['download_urls']:
                merged[tid]['download_urls'].append(url)
            # 保留最新時間
            if record.get('created_at', '') > merged[tid]['created_at']:
                merged[tid]['created_at'] = record.get('created_at', '')
            # 如果有密碼就保留
            if record.get('password') and not merged[tid]['password']:
                merged[tid]['password'] = record.get('password')
            # 如果有 downloaded_at 就保留
            if record.get('downloaded_at') and not merged[tid]['downloaded_at']:
                merged[tid]['downloaded_at'] = record.get('downloaded_at')

        # 轉換為列表並按時間排序（最新的在前）
        result = list(merged.values())
        result.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return result

    def _populate_table(self, records: List[Dict[str, Any]]):
        """填充表格"""
        # 暫停 UI 更新以提升效能
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(records))

        for row, record in enumerate(records):
            # 勾選框 (column 0)
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            checkbox_item.setCheckState(Qt.CheckState.Unchecked)
            checkbox_item.setData(Qt.ItemDataRole.UserRole, record)  # 儲存完整資料
            self.table.setItem(row, 0, checkbox_item)

            # 標題 (column 1)
            title = record.get('title', '') or ''
            title_item = QTableWidgetItem(title[:60] + '...' if len(title) > 60 else title)
            title_item.setToolTip(title)
            self.table.setItem(row, 1, title_item)

            # 關鍵字 (column 2)
            keyword = record.get('keyword', '') or ''
            keyword_item = QTableWidgetItem(keyword)
            keyword_item.setForeground(QColor(0, 100, 180))
            self.table.setItem(row, 2, keyword_item)

            # 下載連結 (column 3)
            download_urls = record.get('download_urls', [])
            if isinstance(download_urls, list) and len(download_urls) > 0:
                if len(download_urls) == 1:
                    url_display = download_urls[0][:40] + '...' if len(download_urls[0]) > 40 else download_urls[0]
                else:
                    url_display = f"[{len(download_urls)} 個連結]"
                url_tooltip = '\n'.join(download_urls)
            else:
                url_display = '-'
                url_tooltip = ''
            url_item = QTableWidgetItem(url_display)
            url_item.setToolTip(url_tooltip)
            url_item.setData(Qt.ItemDataRole.UserRole, download_urls)
            self.table.setItem(row, 3, url_item)

            # 密碼 (column 4)
            password = record.get('password', '') or '-'
            password_item = QTableWidgetItem(password)
            if password and password != '-':
                password_item.setForeground(QColor(180, 0, 0))
            self.table.setItem(row, 4, password_item)

            # 狀態 (column 5)
            downloaded_at = record.get('downloaded_at')
            if downloaded_at:
                status_item = QTableWidgetItem("已下載")
                status_item.setForeground(QColor(0, 128, 0))  # 綠色
                try:
                    dt = datetime.fromisoformat(downloaded_at)
                    status_item.setToolTip(f"下載時間: {dt.strftime('%Y-%m-%d %H:%M')}")
                except:
                    status_item.setToolTip(f"下載時間: {downloaded_at}")
            else:
                status_item = QTableWidgetItem("未下載")
                status_item.setForeground(QColor(180, 180, 180))  # 灰色
            self.table.setItem(row, 5, status_item)

            # 時間 (column 6)
            created_at = record.get('created_at', '')
            try:
                dt = datetime.fromisoformat(created_at)
                time_str = dt.strftime("%m-%d %H:%M")
            except:
                time_str = created_at
            self.table.setItem(row, 6, QTableWidgetItem(time_str))

            # 操作按鈕 (column 7)
            btn_open = QPushButton("開啟")
            btn_open.setProperty("download_urls", download_urls)
            btn_open.setProperty("thread_id", record.get('thread_id', ''))
            btn_open.clicked.connect(self._on_open_link_clicked)
            self.table.setCellWidget(row, 7, btn_open)

        # 恢復 UI 更新
        self.table.setUpdatesEnabled(True)

    def _on_cell_clicked(self, row: int, column: int):
        """單擊儲存格 - 密碼/連結欄位自動複製"""
        # 下載連結欄位是第 3 欄 (index 3)
        if column == 3:
            item = self.table.item(row, column)
            if item:
                urls = item.data(Qt.ItemDataRole.UserRole)
                if urls:
                    if isinstance(urls, list):
                        text = '\n'.join(urls)
                    else:
                        text = urls
                    clipboard = QApplication.clipboard()
                    clipboard.setText(text)
                    count = len(urls) if isinstance(urls, list) else 1
                    QToolTip.showText(QCursor.pos(), f"已複製 {count} 個連結", self.table, self.table.rect(), 1500)
        # 密碼欄位是第 4 欄 (index 4)
        elif column == 4:
            item = self.table.item(row, column)
            if item:
                password = item.text()
                if password and password != '-':
                    # 複製到剪貼簿
                    clipboard = QApplication.clipboard()
                    clipboard.setText(password)
                    # 顯示提示
                    QToolTip.showText(QCursor.pos(), "複製成功", self.table, self.table.rect(), 1500)

    def _on_cell_double_clicked(self, row: int, column: int):
        """雙擊儲存格"""
        item = self.table.item(row, 0)
        if item:
            record = item.data(Qt.ItemDataRole.UserRole)
            if record:
                post_url = record.get('post_url', '')
                if post_url:
                    # 補上完整網址
                    if not post_url.startswith('http'):
                        post_url = f"https://fastzone.org/{post_url}"
                    webbrowser.open(post_url)

    def _on_open_link_clicked(self):
        """點擊開啟連結按鈕"""
        btn = self.sender()
        if btn:
            urls = btn.property("download_urls")
            if urls:
                if isinstance(urls, list):
                    for url in urls:
                        webbrowser.open(url)
                else:
                    webbrowser.open(urls)

    def _on_context_menu(self, pos):
        """顯示右鍵選單"""
        row = self.table.rowAt(pos.y())
        if row < 0:
            return

        title_item = self.table.item(row, 0)
        if not title_item:
            return

        record = title_item.data(Qt.ItemDataRole.UserRole)
        if not record:
            return

        menu = QMenu(self)

        # 開啟帖子
        post_url = record.get('post_url', '')
        if post_url:
            action_open_post = menu.addAction("開啟帖子頁面")
            action_open_post.triggered.connect(lambda: self._open_post(post_url))

        # 開啟所有連結
        download_urls = record.get('download_urls', [])
        if download_urls:
            action_open_links = menu.addAction(f"開啟下載連結 ({len(download_urls)} 個)")
            action_open_links.triggered.connect(lambda: self._open_urls(download_urls))

        menu.addSeparator()

        # 標記已下載 / 取消標記
        thread_id = record.get('thread_id', '')
        downloaded_at = record.get('downloaded_at')
        if downloaded_at:
            action_unmark = menu.addAction("取消已下載標記")
            action_unmark.triggered.connect(lambda: self._unmark_downloaded(thread_id))
        else:
            action_mark = menu.addAction("標記已下載")
            action_mark.triggered.connect(lambda: self._mark_downloaded(thread_id))

        menu.addSeparator()

        # 複製連結
        if download_urls:
            action_copy_links = menu.addAction("複製下載連結")
            action_copy_links.triggered.connect(lambda: self._copy_text('\n'.join(download_urls), "下載連結"))

        # 複製密碼
        password = record.get('password', '')
        if password:
            action_copy_pwd = menu.addAction(f"複製密碼: {password}")
            action_copy_pwd.triggered.connect(lambda: self._copy_text(password, "密碼"))

        # 複製標題
        action_copy_title = menu.addAction("複製標題")
        action_copy_title.triggered.connect(lambda: self._copy_text(record.get('title', ''), "標題"))

        menu.exec(self.table.mapToGlobal(pos))

    def _open_post(self, post_url: str):
        """開啟帖子頁面"""
        if not post_url.startswith('http'):
            post_url = f"https://fastzone.org/{post_url}"
        webbrowser.open(post_url)

    def _open_urls(self, urls: list):
        """開啟多個連結"""
        for url in urls:
            webbrowser.open(url)

    def _copy_text(self, text: str, label: str):
        """複製文字到剪貼簿"""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        QToolTip.showText(QCursor.pos(), f"已複製{label}", self.table, self.table.rect(), 1500)

    def _mark_downloaded(self, thread_id: str):
        """標記為已下載"""
        if not thread_id:
            return

        count = self.db.mark_web_download_complete(thread_id, record_history=True)
        if count > 0:
            logger.info(f"已標記 thread_id={thread_id} 為已下載，並記錄到下載歷史")
            QToolTip.showText(QCursor.pos(), "已標記為已下載", self.table, self.table.rect(), 1500)
            self.load_data()  # 刷新表格
        else:
            QToolTip.showText(QCursor.pos(), "標記失敗或已標記過", self.table, self.table.rect(), 1500)

    def _unmark_downloaded(self, thread_id: str):
        """取消已下載標記"""
        if not thread_id:
            return

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE web_downloads
                SET downloaded_at = NULL
                WHERE thread_id = ?
            ''', (thread_id,))
            count = cursor.rowcount

        if count > 0:
            logger.info(f"已取消 thread_id={thread_id} 的已下載標記")
            QToolTip.showText(QCursor.pos(), "已取消標記", self.table, self.table.rect(), 1500)
            self.load_data()  # 刷新表格

    def _get_checked_rows(self) -> List[int]:
        """取得所有勾選的行"""
        checked_rows = []
        for row in range(self.table.rowCount()):
            checkbox_item = self.table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                checked_rows.append(row)
        return checked_rows

    def _select_all(self):
        """全選所有項目"""
        for row in range(self.table.rowCount()):
            checkbox_item = self.table.item(row, 0)
            if checkbox_item:
                checkbox_item.setCheckState(Qt.CheckState.Checked)

    def _deselect_all(self):
        """取消全選"""
        for row in range(self.table.rowCount()):
            checkbox_item = self.table.item(row, 0)
            if checkbox_item:
                checkbox_item.setCheckState(Qt.CheckState.Unchecked)

    def _open_checked_links(self):
        """開啟勾選項目的連結"""
        checked_rows = self._get_checked_rows()

        if not checked_rows:
            QMessageBox.information(self, "提示", "請先勾選要開啟的項目")
            return

        # 收集所有勾選項目的連結
        all_urls = []
        for row in checked_rows:
            checkbox_item = self.table.item(row, 0)
            if checkbox_item:
                record = checkbox_item.data(Qt.ItemDataRole.UserRole)
                if record:
                    urls = record.get('download_urls', [])
                    if isinstance(urls, list):
                        all_urls.extend(urls)

        if not all_urls:
            QMessageBox.information(self, "提示", "勾選的項目沒有可開啟的連結")
            return

        reply = QMessageBox.question(
            self, "確認",
            f"即將開啟 {len(all_urls)} 個連結（來自 {len(checked_rows)} 個項目），確定要繼續嗎？\n\n"
            "注意：這會在瀏覽器開啟多個分頁",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            for url in all_urls:
                webbrowser.open(url)

    def _mark_checked_downloaded(self):
        """標記勾選的項目為已下載"""
        checked_rows = self._get_checked_rows()

        if not checked_rows:
            QMessageBox.information(self, "提示", "請先勾選要標記的項目")
            return

        # 收集所有勾選項目的 thread_id
        thread_ids = []
        for row in checked_rows:
            checkbox_item = self.table.item(row, 0)
            if checkbox_item:
                record = checkbox_item.data(Qt.ItemDataRole.UserRole)
                if record:
                    tid = record.get('thread_id', '')
                    # 只標記尚未下載的
                    if tid and not record.get('downloaded_at'):
                        thread_ids.append(tid)

        if not thread_ids:
            QMessageBox.information(self, "提示", "勾選的項目都已標記為已下載")
            return

        # 批次標記
        marked_count = 0
        for tid in thread_ids:
            count = self.db.mark_web_download_complete(tid, record_history=True)
            if count > 0:
                marked_count += 1

        if marked_count > 0:
            logger.info(f"批次標記 {marked_count} 個項目為已下載")
            QMessageBox.information(
                self, "完成",
                f"已將 {marked_count} 個項目標記為已下載，\n並記錄到下載歷史。"
            )
            self.load_data()  # 刷新表格

    def _clear_all(self):
        """清空所有記錄"""
        count = self.db.get_web_downloads_count()
        if count == 0:
            QMessageBox.information(self, "提示", "沒有記錄可清空")
            return

        reply = QMessageBox.question(
            self, "確認",
            f"確定要清空所有 {count} 筆記錄嗎？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.db.clear_web_downloads()
            self.load_data()

    def add_record(self, thread_id: str, title: str, post_url: str,
                   keyword: str, download_url: str, password: str = None):
        """新增記錄（供外部呼叫）"""
        # 檢查是否已存在
        if not self.db.web_download_exists(thread_id, download_url):
            self.db.add_web_download(
                thread_id=thread_id,
                title=title,
                post_url=post_url,
                keyword=keyword,
                download_url=download_url,
                password=password
            )

    def _on_column_resized(self, index: int, old_size: int, new_size: int):
        """欄位寬度變更時儲存"""
        # 延遲儲存，避免頻繁寫入
        if not hasattr(self, '_save_timer'):
            from PyQt6.QtCore import QTimer
            self._save_timer = QTimer()
            self._save_timer.setSingleShot(True)
            self._save_timer.timeout.connect(self._save_column_widths)
        self._save_timer.start(500)  # 500ms 後儲存

    def _save_column_widths(self):
        """儲存欄位寬度到設定檔"""
        try:
            widths = []
            for i in range(self.table.columnCount()):
                widths.append(self.table.columnWidth(i))

            settings = {'column_widths': widths}

            # 確保目錄存在
            self._settings_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self._settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f)

            logger.debug(f"已儲存欄位寬度: {widths}")
        except Exception as e:
            logger.warning(f"儲存欄位寬度失敗: {e}")

    def _restore_column_widths(self):
        """從設定檔還原欄位寬度"""
        try:
            if self._settings_file.exists():
                with open(self._settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)

                widths = settings.get('column_widths', [])
                if widths and len(widths) == self.table.columnCount():
                    for i, width in enumerate(widths):
                        # 跳過第 0 欄（勾選框 Fixed）和第 1 欄（標題 Stretch）
                        if i > 1:
                            self.table.setColumnWidth(i, width)
                    logger.debug(f"已還原欄位寬度: {widths}")
                    return

            # 使用預設寬度
            for i, width in enumerate(self.DEFAULT_COLUMN_WIDTHS):
                # 跳過第 0 欄（勾選框）和第 1 欄（標題）
                if i > 1:
                    self.table.setColumnWidth(i, width)

        except Exception as e:
            logger.warning(f"還原欄位寬度失敗: {e}")
            # 使用預設寬度
            for i, width in enumerate(self.DEFAULT_COLUMN_WIDTHS):
                if i != 0:
                    self.table.setColumnWidth(i, width)
