"""
解壓縮相關的資料模型
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Dict
from datetime import datetime


@dataclass
class ArchiveInfo:
    """壓縮檔分析結果"""
    path: Path
    size: int
    root_is_single_folder: bool
    root_folder_name: Optional[str]
    all_entries: List[str]
    file_count: int

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class FilterResult:
    """過濾結果"""
    kept: List[str]
    excluded: List[str]

    @property
    def kept_count(self) -> int:
        return len(self.kept)

    @property
    def excluded_count(self) -> int:
        return len(self.excluded)


@dataclass
class DuplicateResult:
    """重複檔案處理結果"""
    processed: List[Path] = field(default_factory=list)
    skipped: List[Path] = field(default_factory=list)
    renamed: List[Tuple[Path, Path]] = field(default_factory=list)

    @property
    def processed_count(self) -> int:
        return len(self.processed)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    @property
    def renamed_count(self) -> int:
        return len(self.renamed)


@dataclass
class ExtractResult:
    """解壓完整結果"""
    success: bool
    archive_path: Path
    dest_path: Optional[Path] = None
    archive_size: int = 0
    extracted_size: int = 0
    files_extracted: int = 0
    files_skipped: int = 0
    files_filtered: int = 0
    nested_level: int = 0
    parent_id: Optional[int] = None
    error_message: Optional[str] = None
    should_retry: bool = False
    used_password: Optional[str] = None

    @property
    def is_failed(self) -> bool:
        return not self.success


@dataclass
class ExtractConfig:
    """解壓縮設定"""
    # 巢狀解壓設定
    nested_enabled: bool = True
    nested_max_depth: int = 3

    # 重複檔案處理
    duplicate_mode: str = "smart"  # smart = 依大小判斷

    # 排除副檔名
    exclude_extensions: List[str] = field(default_factory=lambda: [
        ".txt", ".nfo", ".url", ".htm", ".html", ".lnk"
    ])

    # 刪除設定
    delete_enabled: bool = True
    delete_permanent: bool = True

    # 智慧資料夾結構
    smart_folder_enabled: bool = True
    min_files_for_folder: int = 2

    @classmethod
    def from_dict(cls, data: dict) -> 'ExtractConfig':
        """從字典建立設定"""
        extract_config = data.get('extract', {})

        nested = extract_config.get('nested', {})
        duplicate = extract_config.get('duplicate', {})
        delete = extract_config.get('delete', {})
        smart_folder = extract_config.get('smart_folder', {})

        return cls(
            nested_enabled=nested.get('enabled', True),
            nested_max_depth=nested.get('max_depth', 3),
            duplicate_mode=duplicate.get('mode', 'smart'),
            exclude_extensions=extract_config.get('exclude_extensions', [
                ".txt", ".nfo", ".url", ".htm", ".html", ".lnk"
            ]),
            delete_enabled=delete.get('enabled', True),
            delete_permanent=delete.get('permanent', True),
            smart_folder_enabled=smart_folder.get('enabled', True),
            min_files_for_folder=smart_folder.get('min_files_for_folder', 2)
        )

    def to_dict(self) -> dict:
        """轉換為字典"""
        return {
            'extract': {
                'nested': {
                    'enabled': self.nested_enabled,
                    'max_depth': self.nested_max_depth
                },
                'duplicate': {
                    'mode': self.duplicate_mode
                },
                'exclude_extensions': self.exclude_extensions,
                'delete': {
                    'enabled': self.delete_enabled,
                    'permanent': self.delete_permanent
                },
                'smart_folder': {
                    'enabled': self.smart_folder_enabled,
                    'min_files_for_folder': self.min_files_for_folder
                }
            }
        }


@dataclass
class FailureTracker:
    """追蹤當次監控的失敗狀態"""
    file_failures: Dict[str, int] = field(default_factory=dict)  # {檔案路徑: 失敗次數}
    max_failures: int = 5

    def record_failure(self, filepath: str) -> bool:
        """
        記錄失敗，回傳是否已達上限

        Returns:
            True 如果已達失敗上限（應放棄此檔案）
        """
        self.file_failures[filepath] = self.file_failures.get(filepath, 0) + 1
        return self.file_failures[filepath] >= self.max_failures

    def is_blacklisted(self, filepath: str) -> bool:
        """檢查是否已放棄（達到失敗上限）"""
        return self.file_failures.get(filepath, 0) >= self.max_failures

    def get_failure_count(self, filepath: str) -> int:
        """取得失敗次數"""
        return self.file_failures.get(filepath, 0)

    def get_blacklisted_files(self) -> List[str]:
        """取得所有已放棄的檔案"""
        return [f for f, count in self.file_failures.items() if count >= self.max_failures]

    def reset(self):
        """重置失敗記錄"""
        self.file_failures.clear()

    def has_active_files(self) -> bool:
        """檢查是否還有可嘗試的檔案（非放棄狀態）"""
        # 如果沒有任何失敗記錄，表示沒有正在處理的檔案
        if not self.file_failures:
            return False
        # 檢查是否所有記錄的檔案都已放棄
        return any(count < self.max_failures for count in self.file_failures.values())
