"""
JDownloader 下載狀態輪詢器
定期檢查 JDownloader 下載狀態，偵測下載完成
"""
from typing import List, Dict, Set, Optional
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..utils.logger import logger
from .jd_history_reader import JDHistoryReader


class JDStatusPoller(QObject):
    """輪詢 JDownloader 下載狀態"""

    # 訊號
    file_complete = pyqtSignal(str, str)      # (package_name, filename) 單檔完成
    all_complete = pyqtSignal(int)            # (完成數量) 全部下載完成
    progress_updated = pyqtSignal(int, int)   # (已完成數, 總數) 進度更新
    polling_started = pyqtSignal()
    polling_stopped = pyqtSignal(str)         # (停止原因)

    def __init__(self, jd_path: str, parent=None):
        super().__init__(parent)

        self.jd_path = jd_path
        self.jd_reader = JDHistoryReader(jd_path)

        # 預期的檔案列表 (package_name -> expected_files)
        self._expected_packages: Dict[str, Dict] = {}

        # 已偵測到完成的檔案
        self._completed_packages: Set[str] = set()

        # 輪詢計時器
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._poll_interval = 10000  # 預設 10 秒

        # 狀態
        self._is_polling = False
        self._last_poll_time: Optional[datetime] = None

        # 上次讀取的 JD 記錄快取
        self._jd_cache: List[Dict] = []
        self._cache_time: Optional[datetime] = None

    def set_expected_files(self, expected_files: List[Dict]):
        """
        設定預期的下載檔案列表

        Args:
            expected_files: 預期的檔案列表，每筆包含:
                - tid: 帖子 ID
                - package_name: 套件名稱 (帖子標題)
                - filename: 預期的檔案名稱 (可選)
                - link_url: 連結 URL (可選)
        """
        self._expected_packages.clear()
        self._completed_packages.clear()

        for file_info in expected_files:
            pkg_name = file_info.get('package_name', '')
            if pkg_name:
                self._expected_packages[pkg_name] = file_info

        logger.info(f"設定預期檔案: {len(self._expected_packages)} 個")

    def add_expected_file(self, package_name: str, tid: str = None,
                          filename: str = None, link_url: str = None):
        """新增單一預期檔案"""
        self._expected_packages[package_name] = {
            'tid': tid,
            'package_name': package_name,
            'filename': filename,
            'link_url': link_url
        }

    def start_polling(self, interval: int = 10000):
        """
        開始輪詢

        Args:
            interval: 輪詢間隔（毫秒）
        """
        if self._is_polling:
            return

        self._poll_interval = interval
        self._is_polling = True
        self._timer.start(interval)
        self.polling_started.emit()
        logger.info(f"開始輪詢 JDownloader 狀態 (間隔: {interval}ms)")

        # 立即執行一次
        self._poll()

    def stop_polling(self, reason: str = "使用者停止"):
        """停止輪詢"""
        if not self._is_polling:
            return

        self._timer.stop()
        self._is_polling = False
        self.polling_stopped.emit(reason)
        logger.info(f"停止輪詢 JDownloader 狀態: {reason}")

    def is_polling(self) -> bool:
        """是否正在輪詢"""
        return self._is_polling

    def _poll(self):
        """執行一次輪詢"""
        if not self._expected_packages:
            logger.debug("JD 輪詢: 沒有預期檔案，跳過")
            return

        try:
            self._last_poll_time = datetime.now()

            # 讀取 JD 下載記錄
            jd_history = self.jd_reader.read_download_history()
            self._jd_cache = jd_history
            self._cache_time = datetime.now()

            # 找出已完成的下載
            completed = self.jd_reader.get_completed_downloads()

            # 比對預期檔案 (使用模糊匹配)
            newly_completed = []
            for record in completed:
                jd_pkg_name = record.get('package_name', '')
                jd_file_name = record.get('file_name', '')

                # 嘗試匹配預期列表
                matched_pkg = self._find_matching_package(jd_pkg_name, jd_file_name)

                if matched_pkg and matched_pkg not in self._completed_packages:
                    if record.get('status') == 'FINISHED':
                        self._completed_packages.add(matched_pkg)
                        newly_completed.append(record)

                        # 直接更新資料庫，儲存實際檔名
                        if jd_file_name:
                            try:
                                from ..database.db_manager import DatabaseManager
                                db = DatabaseManager()
                                updated = db.update_jd_actual_filename(jd_pkg_name, jd_file_name)
                                logger.info(f"已儲存實際檔名: {jd_file_name} (更新 {updated} 筆)")
                            except Exception as e:
                                logger.warning(f"儲存實際檔名失敗: {e}")

                        self.file_complete.emit(jd_pkg_name, jd_file_name)
                        logger.info(f"偵測到下載完成: {jd_pkg_name} -> {jd_file_name}")

            # 發送進度更新
            total = len(self._expected_packages)
            completed_count = len(self._completed_packages)
            self.progress_updated.emit(completed_count, total)

            # 檢查是否全部完成
            if completed_count == total and total > 0:
                logger.info(f"JD 全部下載完成: {completed_count} 個")
                self.all_complete.emit(completed_count)
                self.stop_polling("全部下載完成")

        except Exception as e:
            logger.error(f"輪詢 JDownloader 狀態時發生錯誤: {e}")
            import traceback
            logger.debug(traceback.format_exc())

    def _find_matching_package(self, jd_pkg_name: str, jd_file_name: str) -> Optional[str]:
        """
        尋找匹配的預期套件名稱 (模糊匹配)

        Args:
            jd_pkg_name: JD 中的套件名稱
            jd_file_name: JD 中的檔案名稱

        Returns:
            匹配的預期套件名稱，或 None
        """
        # 精確匹配
        if jd_pkg_name in self._expected_packages:
            return jd_pkg_name

        # 模糊匹配 - 檢查是否包含
        jd_pkg_lower = jd_pkg_name.lower()
        jd_file_lower = jd_file_name.lower() if jd_file_name else ''

        for expected_name, expected_info in self._expected_packages.items():
            expected_lower = expected_name.lower()
            expected_filename = (expected_info.get('filename') or '').lower()

            # 套件名稱包含匹配
            if expected_lower in jd_pkg_lower or jd_pkg_lower in expected_lower:
                return expected_name

            # 檔案名稱匹配
            if expected_filename and jd_file_lower:
                if expected_filename in jd_file_lower or jd_file_lower in expected_filename:
                    return expected_name

        return None

    def get_completed_count(self) -> int:
        """取得已完成的數量"""
        return len(self._completed_packages)

    def get_pending_count(self) -> int:
        """取得待完成的數量"""
        return len(self._expected_packages) - len(self._completed_packages)

    def get_completed_packages(self) -> List[str]:
        """取得已完成的套件名稱列表"""
        return list(self._completed_packages)

    def get_pending_packages(self) -> List[str]:
        """取得待完成的套件名稱列表"""
        return [p for p in self._expected_packages if p not in self._completed_packages]

    def check_file_completed(self, package_name: str) -> bool:
        """檢查指定套件是否已完成下載"""
        if package_name in self._completed_packages:
            return True

        # 重新檢查 JD 記錄
        completed = self.jd_reader.get_completed_downloads()
        for record in completed:
            if record.get('package_name') == package_name and record.get('status') == 'FINISHED':
                self._completed_packages.add(package_name)
                return True

        return False

    def is_all_complete(self) -> bool:
        """檢查是否全部完成"""
        if not self._expected_packages:
            return True
        return len(self._completed_packages) >= len(self._expected_packages)

    def reset(self):
        """重置狀態"""
        self._expected_packages.clear()
        self._completed_packages.clear()
        self._jd_cache.clear()
        self._cache_time = None
        if self._is_polling:
            self.stop_polling("重置")
