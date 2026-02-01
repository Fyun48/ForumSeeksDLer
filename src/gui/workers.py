"""
GUI 工作執行緒模組
將耗時操作放在背景執行緒中執行
"""
import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


class LogHandler:
    """捕捉 logger 輸出並發送到 GUI"""
    def __init__(self, signal):
        self.signal = signal

    def write(self, message):
        if message.strip():
            self.signal.emit(message.strip())

    def flush(self):
        pass


class GUILogHandler(logging.Handler):
    """將 logging 輸出導向 GUI 的 Handler"""
    def __init__(self, signal):
        super().__init__()
        self.signal = signal
        self._closed = False

    def emit(self, record):
        if self._closed:
            return
        try:
            msg = self.format(record)
            self.signal.emit(msg)
        except RuntimeError:
            self._closed = True

    def close(self):
        self._closed = True
        super().close()


class CrawlerWorker(QThread):
    """爬蟲工作執行緒"""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)
    progress_signal = pyqtSignal(int, int)  # current, total

    def __init__(self, config_path: str, dry_run: bool = False,
                 re_download_thanked: bool = False):
        super().__init__()
        self.config_path = config_path
        self.dry_run = dry_run
        self.re_download_thanked = re_download_thanked
        self.is_running = True
        self.dlp = None

    def run(self):
        handler = None
        try:
            from ..main import DLP01
            from ..utils.logger import logger

            if not self.is_running:
                self.finished_signal.emit({})
                return

            handler = GUILogHandler(self.log_signal)
            handler.setFormatter(logging.Formatter('%(message)s'))
            logger.addHandler(handler)

            if not self.is_running:
                self.finished_signal.emit({})
                return

            self.dlp = DLP01(config_path=self.config_path)
            self.dlp.re_download_thanked = self.re_download_thanked
            self.dlp.run(dry_run=self.dry_run)

            if self.is_running:
                self.finished_signal.emit(self.dlp.stats if self.dlp else {})

        except Exception as e:
            if self.is_running:
                try:
                    self.log_signal.emit(f"錯誤: {str(e)}")
                except RuntimeError:
                    pass
            self.finished_signal.emit({})
        finally:
            self.dlp = None
            if handler:
                try:
                    from ..utils.logger import logger
                    logger.removeHandler(handler)
                except Exception:
                    pass

    def stop(self):
        """請求停止爬蟲"""
        self.is_running = False
        try:
            if self.dlp:
                self.dlp.request_stop()
        except Exception:
            pass


class ExtractWorker(QThread):
    """解壓批次處理工作執行緒"""
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)
    auto_stopped_signal = pyqtSignal(str)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.is_running = True
        self.monitor = None

    def run(self):
        handler = None
        try:
            from ..downloader.extract_monitor import ExtractMonitor
            from ..database.db_manager import DatabaseManager
            from ..utils.logger import logger

            handler = GUILogHandler(self.log_signal)
            handler.setFormatter(logging.Formatter('%(message)s'))
            logger.addHandler(handler)

            # 取得 JDownloader 路徑
            jd_config = self.config.get('jdownloader', {})
            jd_exe = jd_config.get('exe_path', '')
            jd_path = None
            if jd_exe:
                jd_exe_path = Path(jd_exe)
                if jd_exe_path.exists():
                    jd_path = str(jd_exe_path.parent)

            # 在解壓目錄下建立日期資料夾 (YYMMDD 格式)
            base_extract_dir = Path(self.config['paths']['extract_dir'])
            date_folder = datetime.now().strftime('%y%m%d')  # 例如: 260201
            extract_dir_with_date = base_extract_dir / date_folder

            # 建立資料夾（如果不存在）
            extract_dir_with_date.mkdir(parents=True, exist_ok=True)
            self.log_signal.emit(f"解壓目錄: {extract_dir_with_date}")

            # 建立監控器
            self.monitor = ExtractMonitor(
                download_dir=self.config['paths']['download_dir'],
                extract_dir=str(extract_dir_with_date),
                winrar_path=self.config['paths']['winrar_path'],
                jd_path=jd_path,
                config=self.config
            )

            if jd_path:
                self.log_signal.emit(f"已設定 JDownloader 路徑: {jd_path}")

            # 載入密碼
            db = None
            try:
                db = DatabaseManager()
                passwords = db.get_all_passwords()
                for pwd in passwords:
                    self.monitor.add_password(pwd)

                mappings = db.get_passwords_with_titles()
                for m in mappings:
                    actual_filename = m.get('jd_actual_filename') or m.get('archive_filename')
                    self.monitor.add_password_mapping(
                        m['package_name'] or m['title'],
                        m['password'],
                        actual_filename
                    )
                self.log_signal.emit(f"已載入 {len(passwords)} 個密碼, {len(mappings)} 個映射")
            except Exception as e:
                self.log_signal.emit(f"載入密碼失敗: {e}")

            # 執行批次解壓 (同步 JD 檔名 → 處理全部壓縮檔 → 結束)
            self.status_signal.emit("執行中...")

            stats = self.monitor.run_batch_extract(
                delete_after=True,
                db_manager=db
            )

            self.finished_signal.emit(stats)
            if stats.get('stop_reason'):
                self.auto_stopped_signal.emit(stats['stop_reason'])
            self.status_signal.emit("已完成")

        except Exception as e:
            try:
                self.log_signal.emit(f"監控錯誤: {str(e)}")
            except RuntimeError:
                pass
            self.status_signal.emit("錯誤")
            self.finished_signal.emit({'error': str(e)})
        finally:
            if handler:
                try:
                    handler.close()
                    from ..utils.logger import logger
                    logger.removeHandler(handler)
                except Exception:
                    pass

    def stop(self):
        self.is_running = False
        if self.monitor:
            self.monitor.request_stop()
