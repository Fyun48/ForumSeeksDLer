"""
DLP01 版本管理模組

集中管理程式版本資訊，支援未來的自動更新功能
"""
from typing import Tuple, Optional
from datetime import datetime

# =============================================================================
# 版本資訊 - 更新時只需修改這裡
# =============================================================================

VERSION = "1.3.4"
VERSION_DATE = "2026-02-04"

# 應用程式資訊
APP_NAME = "DLP01"
APP_DISPLAY_NAME = "DLP01 - 論壇自動下載程式"
APP_AUTHOR = "DLP01 開發團隊"

# GitHub 資訊 (用於自動更新檢查)
GITHUB_OWNER = "Fyun48"
GITHUB_REPO = "ForumSeeksDLer"

# =============================================================================
# 版本工具函式
# =============================================================================


def get_version() -> str:
    """取得版本號"""
    return VERSION


def get_version_tuple() -> Tuple[int, int, int]:
    """
    取得版本號元組 (major, minor, patch)

    例如: "1.2.3" -> (1, 2, 3)
    """
    parts = VERSION.split('.')
    return (
        int(parts[0]) if len(parts) > 0 else 0,
        int(parts[1]) if len(parts) > 1 else 0,
        int(parts[2]) if len(parts) > 2 else 0
    )


def get_version_info() -> dict:
    """取得完整版本資訊"""
    major, minor, patch = get_version_tuple()
    return {
        'version': VERSION,
        'version_date': VERSION_DATE,
        'major': major,
        'minor': minor,
        'patch': patch,
        'app_name': APP_NAME,
        'display_name': APP_DISPLAY_NAME,
    }


def compare_versions(version1: str, version2: str) -> int:
    """
    比較兩個版本號

    Args:
        version1: 第一個版本號 (例如 "1.2.3")
        version2: 第二個版本號 (例如 "1.2.4")

    Returns:
        -1: version1 < version2
         0: version1 == version2
         1: version1 > version2
    """
    def parse_version(v: str) -> Tuple[int, ...]:
        # 移除 'v' 前綴 (如果有)
        v = v.lstrip('vV')
        parts = v.split('.')
        return tuple(int(p) for p in parts)

    try:
        v1 = parse_version(version1)
        v2 = parse_version(version2)

        # 補齊長度
        max_len = max(len(v1), len(v2))
        v1 = v1 + (0,) * (max_len - len(v1))
        v2 = v2 + (0,) * (max_len - len(v2))

        if v1 < v2:
            return -1
        elif v1 > v2:
            return 1
        else:
            return 0
    except (ValueError, AttributeError):
        return 0


def is_newer_version(remote_version: str) -> bool:
    """
    檢查遠端版本是否比目前版本新

    Args:
        remote_version: 遠端版本號

    Returns:
        True 如果遠端版本較新
    """
    return compare_versions(remote_version, VERSION) > 0


def get_window_title(profile_name: str = None) -> str:
    """
    取得視窗標題

    Args:
        profile_name: 設定檔名稱 (可選)

    Returns:
        格式化的視窗標題
    """
    title = f"{APP_DISPLAY_NAME} v{VERSION}"
    if profile_name:
        title += f" 【{profile_name}】"
    return title


def get_about_text() -> str:
    """取得關於對話框的文字"""
    return f"""
{APP_DISPLAY_NAME}

版本: v{VERSION}
發佈日期: {VERSION_DATE}

這是一個論壇自動下載工具，支援：
- 自動爬取論壇帖子
- 自動發送感謝解鎖隱藏內容
- 提取下載連結並發送到 JDownloader
- 自動解壓縮下載的檔案
""".strip()


# =============================================================================
# 模組初始化
# =============================================================================

if __name__ == "__main__":
    # 測試版本資訊
    print(f"Version: {VERSION}")
    print(f"Version Tuple: {get_version_tuple()}")
    print(f"Version Info: {get_version_info()}")
    print(f"Window Title: {get_window_title('測試')}")
    print()
    print("Version Comparison Tests:")
    print(f"  1.0.0 vs 1.0.1: {compare_versions('1.0.0', '1.0.1')}")
    print(f"  1.1.0 vs 1.0.9: {compare_versions('1.1.0', '1.0.9')}")
    print(f"  2.0.0 vs 1.9.9: {compare_versions('2.0.0', '1.9.9')}")
    print(f"  1.0.0 vs 1.0.0: {compare_versions('1.0.0', '1.0.0')}")
