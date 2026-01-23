"""
統一通知管理器
支援 Windows Toast 通知和狀態列更新
"""
import sys
from typing import Optional
from PyQt6.QtWidgets import QStatusBar, QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QObject, pyqtSignal

from ..utils.logger import logger


class NotificationManager(QObject):
    """統一管理所有通知"""

    # 訊號：當通知被點擊時
    notification_clicked = pyqtSignal(str)  # (通知類型)

    def __init__(self, app_name: str = "DLP01", parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self._statusbar: Optional[QStatusBar] = None
        self._tray_icon: Optional[QSystemTrayIcon] = None
        self._use_plyer = False

        # 嘗試初始化 plyer（用於 Windows Toast）
        try:
            from plyer import notification
            self._use_plyer = True
            logger.debug("plyer 通知已啟用")
        except ImportError:
            logger.debug("plyer 未安裝，將使用系統托盤通知")

    def set_statusbar(self, statusbar: QStatusBar):
        """設定狀態列"""
        self._statusbar = statusbar

    def set_tray_icon(self, tray_icon: QSystemTrayIcon):
        """設定系統托盤圖示"""
        self._tray_icon = tray_icon

    def update_status(self, message: str, timeout: int = 0):
        """
        更新狀態列訊息

        Args:
            message: 訊息內容
            timeout: 顯示時間（毫秒），0 表示持續顯示
        """
        if self._statusbar:
            self._statusbar.showMessage(message, timeout)
        logger.info(f"狀態: {message}")

    def show_toast(self, title: str, message: str, duration: int = 5,
                   notification_type: str = "info"):
        """
        顯示 Windows Toast 通知

        Args:
            title: 標題
            message: 訊息內容
            duration: 顯示時間（秒）
            notification_type: 通知類型 (info, success, warning, error)
        """
        try:
            if self._use_plyer:
                from plyer import notification
                notification.notify(
                    title=f"{self.app_name} - {title}",
                    message=message,
                    timeout=duration,
                    app_name=self.app_name
                )
            elif self._tray_icon and self._tray_icon.isVisible():
                # 使用系統托盤通知
                icon_type = {
                    'info': QSystemTrayIcon.MessageIcon.Information,
                    'success': QSystemTrayIcon.MessageIcon.Information,
                    'warning': QSystemTrayIcon.MessageIcon.Warning,
                    'error': QSystemTrayIcon.MessageIcon.Critical
                }.get(notification_type, QSystemTrayIcon.MessageIcon.Information)

                self._tray_icon.showMessage(
                    f"{self.app_name} - {title}",
                    message,
                    icon_type,
                    duration * 1000
                )
            else:
                # 沒有可用的通知方式，僅記錄日誌
                logger.info(f"通知: [{title}] {message}")

        except Exception as e:
            logger.warning(f"顯示通知失敗: {e}")

    # ========== 預定義通知 ==========

    def notify_crawl_started(self, forum_name: str):
        """通知爬取開始"""
        self.update_status(f"正在爬取: {forum_name}...")

    def notify_crawl_complete(self, total_links: int, new_links: int):
        """通知爬取完成"""
        self.show_toast(
            "爬取完成",
            f"共發現 {total_links} 個連結，新增 {new_links} 個\n請查看 JDownloader 下載狀況",
            duration=8,
            notification_type="success"
        )
        self.update_status(f"爬取完成: 共 {total_links} 個連結，新增 {new_links} 個")

    def notify_jd_all_complete(self, count: int):
        """通知 JDownloader 全部下載完成"""
        self.show_toast(
            "下載完成",
            f"JDownloader 已完成 {count} 個檔案的下載",
            duration=5,
            notification_type="success"
        )
        self.update_status(f"JD 下載完成: {count} 個檔案")

    def notify_extract_started(self):
        """通知解壓監控開始"""
        self.update_status("解壓監控進行中...")

    def notify_extract_complete(self, success: int, failed: int):
        """通知解壓監控完成"""
        if failed > 0:
            self.show_toast(
                "解壓完成",
                f"成功: {success} 個，失敗: {failed} 個",
                duration=5,
                notification_type="warning"
            )
        else:
            self.show_toast(
                "解壓完成",
                f"成功解壓 {success} 個檔案",
                duration=5,
                notification_type="success"
            )
        self.update_status(f"解壓完成: 成功 {success} 個, 失敗 {failed} 個")

    def notify_all_complete(self, crawl_count: int, extract_count: int):
        """通知全部流程完成（爬取 + 下載 + 解壓）"""
        self.show_toast(
            "全部完成",
            f"爬取連結: {crawl_count} 個\n解壓檔案: {extract_count} 個\n\n抓取與自動解壓已全部完成！",
            duration=10,
            notification_type="success"
        )
        self.update_status("全部完成！")

    def notify_extract_auto_stopped(self, reason: str):
        """通知解壓監控自動停止"""
        self.show_toast(
            "監控已停止",
            f"原因: {reason}",
            duration=5,
            notification_type="info"
        )
        self.update_status(f"監控停止: {reason}")

    def notify_file_blacklisted(self, filename: str, failure_count: int):
        """通知檔案已放棄"""
        self.update_status(f"放棄處理: {filename} (失敗 {failure_count} 次)")

    def notify_repeated_download(self, tid: str, count: int, title: str = ""):
        """通知重複下載"""
        display_name = title if title else f"TID: {tid}"
        if count >= 3:
            self.show_toast(
                "重複下載警告",
                f"{display_name}\n已下載 {count} 次",
                duration=5,
                notification_type="warning"
            )
        self.update_status(f"重複下載: {display_name} (第 {count} 次)")

    def notify_error(self, title: str, message: str):
        """通知錯誤"""
        self.show_toast(title, message, duration=8, notification_type="error")
        self.update_status(f"錯誤: {message}")
