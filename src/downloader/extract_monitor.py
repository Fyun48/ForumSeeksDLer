"""
監控下載目錄，下載完成後自動解壓並刪除 RAR
支援：巢狀解壓、重複檔案處理、排除副檔名、智慧資料夾結構
"""
import os
import re
import time
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta

from PyQt6.QtCore import QObject, pyqtSignal

from ..utils.logger import logger
from ..models.extract_models import (
    ArchiveInfo, FilterResult, DuplicateResult, ExtractResult, ExtractConfig
)


class ExtractError(Exception):
    """解壓錯誤基類"""
    pass


class PasswordError(ExtractError):
    """密碼錯誤"""
    pass


class CorruptedArchiveError(ExtractError):
    """壓縮檔損壞"""
    pass


class DiskSpaceError(ExtractError):
    """磁碟空間不足"""
    pass


class ExtractSignals(QObject):
    """解壓監控器的訊號"""
    started = pyqtSignal(str, int)        # (檔案名稱, 檔案大小)
    progress = pyqtSignal(str, int)       # (檔案名稱, 百分比 0-100)
    file_extracted = pyqtSignal(str)      # (檔案名稱)
    finished = pyqtSignal(object)         # (ExtractResult)
    error = pyqtSignal(str, str)          # (檔案名稱, 錯誤訊息)
    nested_found = pyqtSignal(str, int)   # (檔案名稱, 層級)
    file_skipped = pyqtSignal(str, str)   # (檔案名稱, 原因)
    stats_updated = pyqtSignal(dict)      # (統計資料)


class ExtractMonitor:
    """下載完成監控與自動解壓"""

    # 支援的壓縮格式
    ARCHIVE_EXTENSIONS = ['.rar', '.zip', '.7z']
    ARCHIVE_PATTERNS = ['*.rar', '*.zip', '*.7z', '*.part01.rar', '*.part1.rar', '*.part001.rar']

    def __init__(self, download_dir: str, extract_dir: str, winrar_path: str,
                 passwords: List[str] = None, jd_path: str = None,
                 config: dict = None):
        self.download_dir = Path(download_dir)
        self.extract_dir = Path(extract_dir)
        self.winrar_path = Path(winrar_path)
        self.passwords = passwords or []
        self.jd_path = jd_path

        # 載入設定
        self.config = ExtractConfig.from_dict(config or {})

        # 密碼對應表 (檔名關鍵字 -> 密碼列表)
        self.password_mappings: Dict[str, List[str]] = {}

        # JD 檔名 -> 套件名稱 的快取
        self._jd_filename_cache: Dict[str, str] = {}
        self._jd_cache_time: Optional[datetime] = None

        # 確保目錄存在
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.extract_dir.mkdir(parents=True, exist_ok=True)

        # 已處理的檔案 (避免重複處理)
        self.processed_files = set()

        # 訊號 (用於 GUI 整合)
        self.signals = ExtractSignals()

    def update_config(self, config: dict):
        """更新設定"""
        self.config = ExtractConfig.from_dict(config)

    # ========== 壓縮檔分析 ==========

    def analyze_archive(self, archive_path: Path) -> Optional[ArchiveInfo]:
        """分析壓縮檔內容結構，不實際解壓"""
        if not archive_path.exists():
            return None

        try:
            # 使用 UnRAR 列出內容
            unrar_path = self.winrar_path.parent / 'UnRAR.exe'
            if not unrar_path.exists():
                unrar_path = self.winrar_path

            # lb = bare format list (只顯示檔案名稱)
            cmd = [str(unrar_path), 'lb', str(archive_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                # 可能需要密碼，嘗試使用已知密碼
                for pwd in self.passwords[:5]:  # 只嘗試前 5 個密碼
                    cmd = [str(unrar_path), 'lb', f'-p{pwd}', str(archive_path)]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    if result.returncode == 0:
                        break

            if result.returncode != 0:
                logger.warning(f"無法分析壓縮檔: {archive_path.name}")
                return None

            # 解析列表
            entries = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]

            if not entries:
                return None

            # 分析根目錄結構
            root_items = set()
            for entry in entries:
                # 取得第一層路徑
                parts = entry.replace('\\', '/').split('/')
                root_items.add(parts[0])

            # 判斷根目錄是否為單一資料夾
            root_is_single_folder = False
            root_folder_name = None

            if len(root_items) == 1:
                root_item = list(root_items)[0]
                # 檢查這個項目是否為資料夾（至少有一個子項目）
                has_children = any(
                    entry.replace('\\', '/').startswith(root_item + '/')
                    for entry in entries
                )
                if has_children:
                    root_is_single_folder = True
                    root_folder_name = root_item

            # 計算檔案數量（排除資料夾）
            file_count = len([e for e in entries if not e.endswith('/') and not e.endswith('\\')])

            return ArchiveInfo(
                path=archive_path,
                size=archive_path.stat().st_size,
                root_is_single_folder=root_is_single_folder,
                root_folder_name=root_folder_name,
                all_entries=entries,
                file_count=file_count
            )

        except subprocess.TimeoutExpired:
            logger.error(f"分析壓縮檔超時: {archive_path.name}")
            return None
        except Exception as e:
            logger.error(f"分析壓縮檔失敗: {archive_path.name} - {e}")
            return None

    # ========== 智慧資料夾判斷 ==========

    def should_create_folder(self, archive_info: ArchiveInfo) -> Tuple[bool, Optional[str]]:
        """
        判斷是否需要建立外層資料夾

        Returns:
            (是否建立資料夾, 目的地資料夾名稱)
        """
        if not self.config.smart_folder_enabled:
            # 功能關閉，總是建立資料夾
            return (True, self._get_clean_archive_name(archive_info.path))

        # 情境 A：根目錄是單一資料夾
        if archive_info.root_is_single_folder:
            # 直接使用該資料夾，不額外包一層
            return (False, archive_info.root_folder_name)

        # 情境 B：根目錄是散落檔案
        # 先過濾掉排除的副檔名
        filter_result = self.filter_entries(archive_info.all_entries)

        # 計算剩餘的檔案數量（排除資料夾）
        remaining_files = [
            f for f in filter_result.kept
            if not f.endswith('/') and not f.endswith('\\')
        ]

        if len(remaining_files) < self.config.min_files_for_folder:
            # 過濾後檔案數量不足，不建資料夾
            return (False, None)
        else:
            # 檔案數量達標，用壓縮檔名建立資料夾
            folder_name = self._get_clean_archive_name(archive_info.path)
            return (True, folder_name)

    def _get_clean_archive_name(self, archive_path: Path) -> str:
        """取得乾淨的壓縮檔名稱（去除副檔名和分卷後綴）"""
        name = archive_path.stem
        # 移除分卷後綴
        for suffix in ['.part01', '.part1', '.part001', '.part02', '.part2', '.part002']:
            if name.lower().endswith(suffix):
                name = name[:-len(suffix)]
                break
        return name

    # ========== 過濾檔案 ==========

    def filter_entries(self, entries: List[str]) -> FilterResult:
        """過濾要排除的副檔名"""
        kept = []
        excluded = []

        exclude_exts = [ext.lower() for ext in self.config.exclude_extensions]

        for entry in entries:
            # 取得副檔名
            entry_lower = entry.lower()
            should_exclude = False

            for ext in exclude_exts:
                if entry_lower.endswith(ext):
                    should_exclude = True
                    break

            if should_exclude:
                excluded.append(entry)
            else:
                kept.append(entry)

        return FilterResult(kept=kept, excluded=excluded)

    def remove_excluded_files(self, directory: Path) -> int:
        """從目錄中移除排除的檔案類型，回傳移除的檔案數量"""
        removed_count = 0
        exclude_exts = [ext.lower() for ext in self.config.exclude_extensions]

        for root, dirs, files in os.walk(directory):
            for filename in files:
                file_lower = filename.lower()
                for ext in exclude_exts:
                    if file_lower.endswith(ext):
                        file_path = Path(root) / filename
                        try:
                            file_path.unlink()
                            removed_count += 1
                            logger.debug(f"已移除排除檔案: {filename}")
                        except Exception as e:
                            logger.warning(f"移除檔案失敗: {filename} - {e}")
                        break

        return removed_count

    # ========== 重複檔案處理 ==========

    def handle_duplicate(self, src_file: Path, dest_file: Path) -> str:
        """
        處理單一檔案的重複情況

        Returns:
            'copied' | 'skipped' | 'renamed'
        """
        if not dest_file.exists():
            # 目的地沒有同名檔案，直接移動
            shutil.move(str(src_file), str(dest_file))
            return 'copied'

        # 比對檔案大小
        src_size = src_file.stat().st_size
        dest_size = dest_file.stat().st_size

        if src_size == dest_size:
            # 大小相同，視為相同檔案，跳過
            src_file.unlink()
            self.signals.file_skipped.emit(src_file.name, "大小相同，已跳過")
            return 'skipped'
        else:
            # 大小不同，重新命名
            new_dest = self.get_unique_filename(dest_file)
            shutil.move(str(src_file), str(new_dest))
            return 'renamed'

    def get_unique_filename(self, file_path: Path) -> Path:
        """產生不重複的檔名: file.mp4 → file(1).mp4 → file(2).mp4"""
        if not file_path.exists():
            return file_path

        stem = file_path.stem
        suffix = file_path.suffix
        parent = file_path.parent

        counter = 1
        while True:
            new_name = f"{stem}({counter}){suffix}"
            new_path = parent / new_name
            if not new_path.exists():
                return new_path
            counter += 1

    def move_with_duplicate_handling(self, src_dir: Path, dest_dir: Path) -> DuplicateResult:
        """移動檔案並處理重複"""
        result = DuplicateResult()
        dest_dir.mkdir(parents=True, exist_ok=True)

        for root, dirs, files in os.walk(src_dir):
            # 計算相對路徑
            rel_root = Path(root).relative_to(src_dir)
            target_root = dest_dir / rel_root
            target_root.mkdir(parents=True, exist_ok=True)

            for filename in files:
                src_file = Path(root) / filename
                dest_file = target_root / filename

                action = self.handle_duplicate(src_file, dest_file)

                if action == 'copied':
                    result.processed.append(dest_file)
                elif action == 'skipped':
                    result.skipped.append(dest_file)
                elif action == 'renamed':
                    new_dest = self.get_unique_filename(dest_file)
                    result.renamed.append((dest_file, new_dest))
                    result.processed.append(new_dest)

        return result

    # ========== 巢狀解壓 ==========

    def find_nested_archives(self, directory: Path) -> List[Path]:
        """在目錄中尋找壓縮檔"""
        archives = []

        for pattern in self.ARCHIVE_PATTERNS:
            for archive_path in directory.rglob(pattern):
                # 跳過分卷的非第一卷
                name = archive_path.name.lower()
                if '.part' in name:
                    if not (name.endswith('.part01.rar') or
                            name.endswith('.part1.rar') or
                            name.endswith('.part001.rar')):
                        continue
                archives.append(archive_path)

        return archives

    # ========== 解壓前檢查 ==========

    def pre_extract_check(self, archive_path: Path) -> Tuple[bool, Optional[str]]:
        """解壓前檢查"""
        # 1. 檢查檔案存在
        if not archive_path.exists():
            return (False, "檔案不存在")

        # 2. 檢查檔案大小（排除 0 byte）
        if archive_path.stat().st_size == 0:
            return (False, "檔案大小為 0")

        # 3. 檢查磁碟空間（預估解壓後大小約為原始大小的 1.5-3 倍）
        archive_size = archive_path.stat().st_size
        estimated_size = archive_size * 3
        free_space = shutil.disk_usage(self.extract_dir).free

        if estimated_size > free_space * 0.9:  # 保留 10% 緩衝
            return (False, f"磁碟空間不足，需要約 {estimated_size // 1024 // 1024} MB")

        return (True, None)

    # ========== 刪除壓縮檔 ==========

    def delete_archive(self, archive_path: Path) -> bool:
        """刪除壓縮檔 (包括分卷)"""
        if not self.config.delete_enabled:
            return True

        try:
            # 找出所有相關的分卷檔案
            base_name = self._get_clean_archive_name(archive_path)
            parent_dir = archive_path.parent

            # 刪除所有分卷
            patterns = [
                f"{base_name}.rar",
                f"{base_name}.part*.rar",
                f"{base_name}.r??",
                f"{base_name}.zip",
                f"{base_name}.7z",
            ]

            deleted = []
            for pattern in patterns:
                for f in parent_dir.glob(pattern):
                    if self.config.delete_permanent:
                        # 永久刪除
                        f.unlink()
                    else:
                        # 移到資源回收桶 (需要 send2trash 套件)
                        try:
                            import send2trash
                            send2trash.send2trash(str(f))
                        except ImportError:
                            # 沒有 send2trash，直接刪除
                            f.unlink()
                    deleted.append(f.name)

            if deleted:
                logger.info(f"已刪除壓縮檔: {', '.join(deleted)}")
            return True

        except Exception as e:
            logger.error(f"刪除壓縮檔失敗: {e}")
            return False

    # ========== 主要解壓流程 ==========

    def process_archive(self, archive_path: Path, nested_level: int = 0,
                        parent_id: int = None, db_manager=None) -> ExtractResult:
        """
        處理單一壓縮檔（支援遞迴巢狀）

        Args:
            archive_path: 壓縮檔路徑
            nested_level: 目前巢狀層級
            parent_id: 父層 download_id
            db_manager: 資料庫管理器

        Returns:
            ExtractResult
        """
        archive_name = archive_path.name
        archive_size = archive_path.stat().st_size if archive_path.exists() else 0

        # 發送開始訊號
        self.signals.started.emit(archive_name, archive_size)

        # 檢查層數限制
        if self.config.nested_enabled and nested_level > self.config.nested_max_depth:
            error_msg = f"超過最大巢狀層數 ({self.config.nested_max_depth})"
            logger.warning(f"{archive_name}: {error_msg}")
            return ExtractResult(
                success=False,
                archive_path=archive_path,
                archive_size=archive_size,
                nested_level=nested_level,
                parent_id=parent_id,
                error_message=error_msg
            )

        # 解壓前檢查
        can_extract, error_msg = self.pre_extract_check(archive_path)
        if not can_extract:
            self.signals.error.emit(archive_name, error_msg)
            return ExtractResult(
                success=False,
                archive_path=archive_path,
                archive_size=archive_size,
                error_message=error_msg
            )

        # 1. 分析壓縮檔
        archive_info = self.analyze_archive(archive_path)

        # 2. 判斷資料夾結構
        if archive_info:
            create_folder, folder_name = self.should_create_folder(archive_info)
        else:
            # 無法分析時使用預設行為
            create_folder = True
            folder_name = self._get_clean_archive_name(archive_path)

        # 3. 決定目的地路徑
        if create_folder and folder_name:
            final_dest = self.extract_dir / folder_name
        else:
            final_dest = self.extract_dir

        # 4. 解壓到暫存區
        temp_dir = Path(tempfile.mkdtemp(prefix='dlp_extract_'))

        try:
            # 執行解壓
            success, used_password = self._extract_to_directory(archive_path, temp_dir)

            if not success:
                shutil.rmtree(temp_dir, ignore_errors=True)
                error_msg = "解壓失敗，可能密碼錯誤或檔案損壞"
                self.signals.error.emit(archive_name, error_msg)
                return ExtractResult(
                    success=False,
                    archive_path=archive_path,
                    archive_size=archive_size,
                    nested_level=nested_level,
                    parent_id=parent_id,
                    error_message=error_msg,
                    should_retry=True
                )

            # 5. 過濾檔案（移除排除的副檔名）
            files_filtered = self.remove_excluded_files(temp_dir)

            # 6. 處理重複檔案並移動到目的地
            dup_result = self.move_with_duplicate_handling(temp_dir, final_dest)

            # 計算解壓後總大小
            extracted_size = sum(
                f.stat().st_size for f in final_dest.rglob('*') if f.is_file()
            )

            # 7. 建立解壓結果
            result = ExtractResult(
                success=True,
                archive_path=archive_path,
                dest_path=final_dest,
                archive_size=archive_size,
                extracted_size=extracted_size,
                files_extracted=dup_result.processed_count,
                files_skipped=dup_result.skipped_count,
                files_filtered=files_filtered,
                nested_level=nested_level,
                parent_id=parent_id,
                used_password=used_password
            )

            # 記錄到資料庫
            current_id = self._record_to_db(result, db_manager)

            # 8. 尋找並處理巢狀壓縮檔
            if self.config.nested_enabled and nested_level < self.config.nested_max_depth:
                nested_archives = self.find_nested_archives(final_dest)
                for nested_archive in nested_archives:
                    self.signals.nested_found.emit(nested_archive.name, nested_level + 1)
                    logger.info(f"發現巢狀壓縮檔 (層級 {nested_level + 1}): {nested_archive.name}")

                    # 遞迴處理
                    self.process_archive(
                        nested_archive,
                        nested_level=nested_level + 1,
                        parent_id=current_id,
                        db_manager=db_manager
                    )

            # 9. 刪除原始壓縮檔
            if result.success:
                self.delete_archive(archive_path)

            # 發送完成訊號
            self.signals.finished.emit(result)
            logger.info(
                f"解壓完成: {archive_name} -> {final_dest} "
                f"(檔案: {result.files_extracted}, 跳過: {result.files_skipped}, 過濾: {result.files_filtered})"
            )

            return result

        except Exception as e:
            logger.exception(f"處理壓縮檔時發生錯誤: {archive_name}")
            self.signals.error.emit(archive_name, str(e))
            return ExtractResult(
                success=False,
                archive_path=archive_path,
                archive_size=archive_size,
                nested_level=nested_level,
                parent_id=parent_id,
                error_message=str(e)
            )

        finally:
            # 清理暫存目錄
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _extract_to_directory(self, archive_path: Path, dest_dir: Path) -> Tuple[bool, Optional[str]]:
        """
        執行實際解壓到指定目錄

        Returns:
            (成功與否, 使用的密碼)
        """
        if not self.winrar_path.exists():
            logger.error(f"WinRAR 不存在: {self.winrar_path}")
            return (False, None)

        unrar_path = self.winrar_path.parent / 'UnRAR.exe'
        if not unrar_path.exists():
            unrar_path = self.winrar_path

        # x = 解壓並保留目錄結構
        # -o+ = 覆寫現有檔案
        # -y = 對所有詢問回答 yes
        base_cmd = [str(unrar_path), 'x', '-o+', '-y']

        # 決定要嘗試的密碼順序
        passwords_to_try = []

        # 1. 嘗試根據檔名匹配的密碼
        matched_passwords = self._find_passwords_for_archive(archive_path)
        passwords_to_try.extend(matched_passwords)

        # 2. 加入所有已知密碼
        for pwd in self.passwords:
            if pwd not in passwords_to_try:
                passwords_to_try.append(pwd)

        logger.info(f"開始解壓: {archive_path.name}")
        if passwords_to_try:
            logger.debug(f"將嘗試 {len(passwords_to_try)} 個密碼")

        # 嘗試每個密碼
        for pwd in passwords_to_try:
            cmd = base_cmd + [f'-p{pwd}', str(archive_path), str(dest_dir) + os.sep]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
                if result.returncode == 0:
                    logger.info(f"解壓成功 (有密碼): {archive_path.name}")
                    return (True, pwd)
            except subprocess.TimeoutExpired:
                logger.error(f"解壓超時: {archive_path.name}")
                return (False, None)
            except Exception as e:
                logger.debug(f"嘗試密碼失敗: {e}")

        # 最後嘗試無密碼
        cmd = base_cmd + ['-p-', str(archive_path), str(dest_dir) + os.sep]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode == 0:
                logger.info(f"解壓完成 (無密碼): {archive_path.name}")
                return (True, None)
            else:
                logger.error(f"解壓失敗: {archive_path.name}")
                logger.debug(f"錯誤輸出: {result.stderr}")
                return (False, None)

        except subprocess.TimeoutExpired:
            logger.error(f"解壓超時: {archive_path.name}")
            return (False, None)
        except Exception as e:
            logger.error(f"解壓異常: {e}")
            return (False, None)

    def _record_to_db(self, result: ExtractResult, db_manager=None) -> Optional[int]:
        """記錄解壓結果到資料庫"""
        try:
            if db_manager is None:
                from ..database.db_manager import DatabaseManager
                db_manager = DatabaseManager()

            return db_manager.record_extraction_result(
                archive_name=result.archive_path.name,
                success=result.success,
                dest_path=str(result.dest_path) if result.dest_path else None,
                files_extracted=result.files_extracted,
                files_skipped=result.files_skipped,
                files_filtered=result.files_filtered,
                archive_size=result.archive_size,
                extracted_size=result.extracted_size,
                nested_level=result.nested_level,
                parent_download_id=result.parent_id,
                error_message=result.error_message,
                used_password=result.used_password
            )
        except Exception as e:
            logger.warning(f"記錄解壓結果失敗: {e}")
            return None

    # ========== 原有方法 (保持相容性) ==========

    def find_completed_archives(self) -> List[Path]:
        """找出已下載完成的壓縮檔"""
        archives = []

        for pattern in self.ARCHIVE_PATTERNS:
            for filepath in self.download_dir.glob(pattern):
                # 跳過分卷的非第一卷
                name = filepath.name.lower()
                if '.part' in name and not (name.endswith('.part01.rar') or
                                            name.endswith('.part1.rar') or
                                            name.endswith('.part001.rar')):
                    continue

                # 跳過已處理的
                if str(filepath) in self.processed_files:
                    continue

                # 檢查是否還在下載中
                if self._is_downloading(filepath):
                    continue

                archives.append(filepath)

        return archives

    def _is_downloading(self, filepath: Path) -> bool:
        """檢查檔案是否還在下載中"""
        try:
            # 檢查 JDownloader 暫存檔
            jd_temp = filepath.with_suffix(filepath.suffix + '.part')
            if jd_temp.exists():
                return True

            # 檢查最近是否有修改 (30 秒內)
            mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
            if datetime.now() - mtime < timedelta(seconds=30):
                return True

            # 嘗試獨佔開啟檔案
            try:
                with open(filepath, 'rb+') as f:
                    pass
            except (IOError, PermissionError):
                return True

            return False

        except Exception:
            return True

    def extract_archive(self, archive_path: Path, password: str = None) -> bool:
        """解壓縮檔案 (保持原有介面)"""
        result = self.process_archive(archive_path)
        return result.success

    def process_archives(self, delete_after: bool = True, db_manager=None) -> int:
        """處理所有已完成下載的壓縮檔"""
        archives = self.find_completed_archives()
        processed = 0

        for archive in archives:
            logger.info(f"發現已完成下載: {archive.name}")

            # 使用新的處理流程
            result = self.process_archive(archive, db_manager=db_manager)

            # 標記為已處理
            self.processed_files.add(str(archive))

            if result.success:
                processed += 1

        return processed

    def add_password(self, password: str):
        """加入密碼到列表（支援 | 分隔的多密碼）"""
        if not password:
            return
        for pwd in password.split('|'):
            pwd = pwd.strip()
            if pwd and pwd not in self.passwords:
                self.passwords.append(pwd)

    def add_password_mapping(self, filename_pattern: str, password: str, archive_filename: str = None):
        """加入檔案名稱與密碼的對應"""
        if not password:
            return

        passwords = [p.strip() for p in password.split('|') if p.strip()]
        if not passwords:
            return

        if archive_filename:
            for arch_name in archive_filename.split('|'):
                arch_name = arch_name.strip()
                if arch_name:
                    key = arch_name.lower()
                    for ext in self.ARCHIVE_EXTENSIONS:
                        if key.endswith(ext):
                            key = key[:-len(ext)]
                            break
                    for suffix in ['.part01', '.part1', '.part001', '.part02', '.part2']:
                        if key.endswith(suffix):
                            key = key[:-len(suffix)]
                            break
                    if key:
                        self.password_mappings[key] = passwords

        if filename_pattern:
            self.password_mappings[filename_pattern] = passwords

    def _find_passwords_for_archive(self, archive_path: Path) -> List[str]:
        """根據壓縮檔名稱尋找對應的密碼列表"""
        archive_name = archive_path.stem.lower()
        clean_name = self._get_clean_archive_name(archive_path).lower()

        logger.debug(f"嘗試匹配密碼: {archive_path.name} -> clean: {clean_name}")

        # 從 JDownloader 記錄查找
        package_name = self._find_package_from_jd(archive_path.name)
        if package_name:
            package_lower = package_name.lower()
            for pattern, passwords in self.password_mappings.items():
                pattern_lower = pattern.lower()
                if pattern_lower in package_lower or package_lower in pattern_lower:
                    logger.info(f"透過 JD 匹配密碼: {archive_path.name}")
                    return passwords if isinstance(passwords, list) else [passwords]

        # 直接用檔名匹配
        clean_name_chars = re.sub(r'[^\u4e00-\u9fff\w]', '', clean_name)

        for pattern, passwords in self.password_mappings.items():
            pattern_lower = pattern.lower()
            pattern_chars = re.sub(r'[^\u4e00-\u9fff\w]', '', pattern_lower)

            if clean_name == pattern_lower:
                return passwords if isinstance(passwords, list) else [passwords]

            if pattern_lower in clean_name or clean_name in pattern_lower:
                return passwords if isinstance(passwords, list) else [passwords]

            if clean_name_chars and pattern_chars:
                if pattern_chars in clean_name_chars or clean_name_chars in pattern_chars:
                    return passwords if isinstance(passwords, list) else [passwords]

        return []

    def _refresh_jd_cache(self, force: bool = False):
        """刷新 JDownloader 檔名快取"""
        if not force and self._jd_cache_time:
            if datetime.now() - self._jd_cache_time < timedelta(minutes=5):
                return

        if not self.jd_path:
            return

        try:
            from .jd_history_reader import JDHistoryReader
            reader = JDHistoryReader(self.jd_path)
            self._jd_filename_cache = reader.get_filename_to_package_mapping()
            self._jd_cache_time = datetime.now()
        except Exception as e:
            logger.debug(f"刷新 JD 快取失敗: {e}")

    def _find_package_from_jd(self, archive_name: str) -> Optional[str]:
        """從 JDownloader 記錄中查找套件名稱"""
        self._refresh_jd_cache()

        if not self._jd_filename_cache:
            return None

        clean_name = archive_name.lower()
        for ext in self.ARCHIVE_EXTENSIONS:
            if clean_name.endswith(ext):
                clean_name = clean_name[:-len(ext)]
                break
        clean_name = re.sub(r'\.part\d+$', '', clean_name)

        if clean_name in self._jd_filename_cache:
            return self._jd_filename_cache[clean_name]

        for file_name, package_name in self._jd_filename_cache.items():
            if clean_name in file_name or file_name in clean_name:
                return package_name

        return None

    def run_monitor(self, interval: int = 60, delete_after: bool = True):
        """持續監控模式"""
        logger.info(f"開始監控下載目錄: {self.download_dir}")
        logger.info(f"解壓目錄: {self.extract_dir}")
        logger.info(f"檢查間隔: {interval} 秒")

        while True:
            try:
                processed = self.process_archives(delete_after)
                if processed > 0:
                    logger.info(f"本次處理了 {processed} 個壓縮檔")
            except Exception as e:
                logger.error(f"監控處理錯誤: {e}")

            time.sleep(interval)
