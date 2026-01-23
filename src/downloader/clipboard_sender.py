"""
透過剪貼簿發送連結到 JDownloader
JDownloader 的剪貼簿監視器會自動偵測
"""
import time
from typing import List, Dict
import subprocess

from ..utils.logger import logger


class ClipboardSender:
    """透過剪貼簿發送連結"""

    def __init__(self, download_dir: str = None):
        self.download_dir = download_dir or "c:\\dl\\dl\\"

    def send_links(self, links: List[Dict], package_name: str = None,
                   password: str = None) -> bool:
        """
        發送連結到剪貼簿
        JDownloader 會自動偵測並加入下載列表
        """
        if not links:
            logger.warning("沒有連結可發送")
            return False

        # 組合連結文字
        link_text = '\n'.join(link['url'] for link in links)

        try:
            # 使用 PowerShell 設定剪貼簿
            ps_command = f'''
            Set-Clipboard -Value @"
{link_text}
"@
'''
            result = subprocess.run(
                ['powershell', '-Command', ps_command],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                logger.info(f"已複製 {len(links)} 個連結到剪貼簿")
                if password:
                    logger.info(f"密碼: {password}")
                return True
            else:
                logger.error(f"複製到剪貼簿失敗: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"複製到剪貼簿時發生錯誤: {e}")
            return False

    def check_jdownloader_running(self) -> bool:
        """檢查 JDownloader 是否在執行"""
        try:
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq JDownloader2.exe'],
                capture_output=True, text=True
            )
            if 'JDownloader2.exe' in result.stdout:
                return True

            # 也檢查 javaw.exe (JDownloader 可能用這個執行)
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq javaw.exe'],
                capture_output=True, text=True
            )
            return 'javaw.exe' in result.stdout
        except Exception:
            return False
