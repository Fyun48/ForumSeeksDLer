#!/usr/bin/env python3
"""快速測試連線和登入狀態"""

import sys
import io
from pathlib import Path

# 設定 stdout 編碼
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))

from src.crawler.forum_client import ForumClient
from src.downloader.jd_integration import JDownloaderIntegration
from src.utils.logger import logger


def test_connection():
    """測試連線"""
    print("=" * 50)
    print("DLP01 連線測試")
    print("=" * 50)

    # 測試 Cookie 和登入
    print("\n1. 測試登入狀態...")
    try:
        client = ForumClient()
        if client.check_login():
            print("   [OK] 已登入")
        else:
            print("   [FAIL] 未登入 - 請檢查 config/cookies.json")
            print("   提示: 從瀏覽器匯出 cookies 到 config/cookies.json")
            return False
    except Exception as e:
        print(f"   [ERROR] {e}")
        return False

    # 測試爬取版區
    print("\n2. 測試爬取版區...")
    try:
        html = client.get_forum_page("77", 1)  # 成人短片專用區
        if html and len(html) > 1000:
            print(f"   [OK] 成功取得頁面 ({len(html)} bytes)")
        else:
            print("   [FAIL] 頁面內容異常")
            return False
    except Exception as e:
        print(f"   [ERROR] {e}")
        return False

    # 測試 JDownloader
    print("\n3. 測試 JDownloader...")
    jd = JDownloaderIntegration()
    if jd.folderwatch_path:
        print(f"   [OK] Folderwatch 路徑: {jd.folderwatch_path}")
        if jd.check_jdownloader_running():
            print("   [OK] JDownloader 正在執行")
        else:
            print("   [WARN] JDownloader 未執行 (可稍後啟動)")
    else:
        print("   [FAIL] 找不到 JDownloader")
        print("   提示: 請確認 JDownloader 2 已安裝")

    print("\n" + "=" * 50)
    print("測試完成")
    print("=" * 50)
    return True


if __name__ == '__main__':
    test_connection()
