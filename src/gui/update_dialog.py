"""
DLP01 更新對話框

顯示更新資訊並提供下載選項
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QProgressBar, QMessageBox, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QFont

from ..updater import UpdateChecker, UpdateResult
from ..version import VERSION


class UpdateCheckWorker(QThread):
    """背景更新檢查執行緒"""

    finished = pyqtSignal(object)  # UpdateResult
    error = pyqtSignal(str)

    def __init__(self, use_cache: bool = True):
        super().__init__()
        self.use_cache = use_cache

    def run(self):
        try:
            from ..updater import check_for_updates
            result = check_for_updates(self.use_cache)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class DownloadWorker(QThread):
    """背景下載執行緒"""

    progress = pyqtSignal(int, int)  # (received, total)
    finished = pyqtSignal(str)  # file_path
    error = pyqtSignal(str)

    def __init__(self, download_url: str):
        super().__init__()
        self.download_url = download_url

    def run(self):
        try:
            from ..updater import get_updater
            updater = get_updater()

            def on_progress(received, total):
                self.progress.emit(received, total)

            result = updater.download_update(self.download_url, on_progress)
            if result:
                self.finished.emit(str(result))
            else:
                self.error.emit("下載失敗")
        except Exception as e:
            self.error.emit(str(e))


class UpdateDialog(QDialog):
    """更新對話框"""

    def __init__(self, update_result: UpdateResult, parent=None):
        super().__init__(parent)
        self.update_result = update_result
        self.download_worker = None
        self._downloaded_path = None

        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("發現新版本")
        self.setMinimumWidth(450)
        self.setMaximumWidth(600)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # 標題
        title_label = QLabel(f"🎉 DLP01 有新版本可用！")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # 版本資訊
        version_layout = QHBoxLayout()

        current_label = QLabel(f"目前版本: v{self.update_result.current_version}")
        version_layout.addWidget(current_label)

        version_layout.addStretch()

        arrow_label = QLabel("→")
        arrow_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        version_layout.addWidget(arrow_label)

        version_layout.addStretch()

        new_label = QLabel(f"最新版本: v{self.update_result.latest_version}")
        new_label.setStyleSheet("color: #A3BE8C; font-weight: bold;")
        version_layout.addWidget(new_label)

        layout.addLayout(version_layout)

        # 更新說明
        notes_label = QLabel("更新內容:")
        layout.addWidget(notes_label)

        self.notes_text = QTextEdit()
        self.notes_text.setReadOnly(True)
        self.notes_text.setMaximumHeight(150)
        self.notes_text.setPlainText(self.update_result.get_formatted_notes(1000))
        layout.addWidget(self.notes_text)

        # 進度條 (初始隱藏)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 狀態標籤
        self.status_label = QLabel("")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        # 按鈕
        button_layout = QHBoxLayout()

        self.download_btn = QPushButton("下載更新")
        self.download_btn.setDefault(True)
        self.download_btn.clicked.connect(self._on_download)
        button_layout.addWidget(self.download_btn)

        self.open_page_btn = QPushButton("開啟下載頁面")
        self.open_page_btn.clicked.connect(self._on_open_page)
        button_layout.addWidget(self.open_page_btn)

        self.later_btn = QPushButton("稍後提醒")
        self.later_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.later_btn)

        layout.addLayout(button_layout)

        # 不再提醒選項
        self.skip_checkbox = QCheckBox("跳過此版本")
        self.skip_checkbox.setToolTip("勾選後將不再提醒此版本的更新")
        layout.addWidget(self.skip_checkbox)

    def _on_download(self):
        """下載更新"""
        if not self.update_result.download_url:
            QMessageBox.warning(self, "無法下載", "找不到下載連結，請手動前往下載頁面。")
            self._on_open_page()
            return

        # 禁用按鈕
        self.download_btn.setEnabled(False)
        self.open_page_btn.setEnabled(False)
        self.later_btn.setText("取消")

        # 顯示進度
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setVisible(True)
        self.status_label.setText("正在下載...")

        # 開始下載
        self.download_worker = DownloadWorker(self.update_result.download_url)
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.error.connect(self._on_download_error)
        self.download_worker.start()

    def _on_download_progress(self, received: int, total: int):
        """下載進度更新"""
        if total > 0:
            percent = int(received * 100 / total)
            self.progress_bar.setValue(percent)

            # 顯示大小
            received_mb = received / 1024 / 1024
            total_mb = total / 1024 / 1024
            self.status_label.setText(f"正在下載... {received_mb:.1f} / {total_mb:.1f} MB")

    def _on_download_finished(self, file_path: str):
        """下載完成"""
        self._downloaded_path = file_path
        self.progress_bar.setValue(100)
        self.status_label.setText("下載完成！")

        # 詢問是否立即安裝
        reply = QMessageBox.question(
            self,
            "下載完成",
            "更新已下載完成。\n\n是否立即執行安裝程式？\n（程式將會關閉）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._run_installer()
        else:
            QMessageBox.information(
                self,
                "提示",
                f"安裝檔已儲存至:\n{file_path}\n\n您可以稍後手動執行安裝。"
            )
            self.accept()

    def _on_download_error(self, error: str):
        """下載錯誤"""
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"下載失敗: {error}")

        QMessageBox.warning(self, "下載失敗", f"無法下載更新:\n{error}")

        # 恢復按鈕
        self.download_btn.setEnabled(True)
        self.open_page_btn.setEnabled(True)
        self.later_btn.setText("稍後提醒")

    def _run_installer(self):
        """執行安裝程式"""
        if not self._downloaded_path:
            return

        from pathlib import Path
        from ..updater import get_updater

        updater = get_updater()
        if updater.run_installer(Path(self._downloaded_path)):
            # 關閉程式讓安裝程式執行
            self.accept()
            # 發送信號讓主視窗關閉
            if self.parent():
                self.parent().close()
        else:
            QMessageBox.warning(self, "錯誤", "無法啟動安裝程式，請手動執行。")

    def _on_open_page(self):
        """開啟下載頁面"""
        from ..updater import get_updater
        updater = get_updater()
        url = self.update_result.html_url or updater.get_releases_url()
        if url:
            import webbrowser
            webbrowser.open(url)

    def get_skipped_version(self) -> str:
        """取得要跳過的版本 (如果使用者勾選)"""
        if self.skip_checkbox.isChecked():
            return self.update_result.latest_version
        return ""


class UpdateSettings:
    """更新相關設定"""

    SETTINGS_KEY = "update"

    def __init__(self):
        self.settings = QSettings("DLP01", "DLP01")

    def is_auto_check_enabled(self) -> bool:
        """是否啟用自動檢查"""
        return self.settings.value(f"{self.SETTINGS_KEY}/auto_check", True, type=bool)

    def set_auto_check_enabled(self, enabled: bool):
        """設定自動檢查"""
        self.settings.setValue(f"{self.SETTINGS_KEY}/auto_check", enabled)

    def get_skipped_version(self) -> str:
        """取得跳過的版本"""
        return self.settings.value(f"{self.SETTINGS_KEY}/skipped_version", "", type=str)

    def set_skipped_version(self, version: str):
        """設定跳過的版本"""
        self.settings.setValue(f"{self.SETTINGS_KEY}/skipped_version", version)

    def should_show_update(self, latest_version: str) -> bool:
        """是否應該顯示更新對話框"""
        if not self.is_auto_check_enabled():
            return False

        skipped = self.get_skipped_version()
        if skipped and skipped == latest_version:
            return False

        return True
