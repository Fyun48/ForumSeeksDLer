import os
import json
import time
from pathlib import Path
from typing import List, Optional, Dict
import re

from ..utils.logger import logger


class JDownloaderIntegration:
    """JDownloader 整合 (Folderwatch 方式)"""

    def __init__(self, folderwatch_path: str = None, download_dir: str = None):
        self.folderwatch_path = self._find_folderwatch_path(folderwatch_path)
        self.download_dir = download_dir or "c:\\dl\\dl\\"

        if self.folderwatch_path:
            logger.info(f"JDownloader Folderwatch 路徑: {self.folderwatch_path}")
        else:
            logger.warning("無法找到 JDownloader Folderwatch 路徑")

    def _find_folderwatch_path(self, custom_path: str = None) -> Optional[str]:
        """尋找 JDownloader Folderwatch 目錄"""
        if custom_path and Path(custom_path).exists():
            return custom_path

        # 常見的 JDownloader 安裝路徑
        possible_paths = [
            # Jimmy's JDownloader Portable
            Path('C:/Users/Jimmy/Downloads/JDownloaderPortable/azofreeware.com/App/JDownloader2/folderwatch'),
            # Windows
            Path(os.environ.get('APPDATA', '')) / 'JDownloader 2.0' / 'folderwatch',
            Path(os.environ.get('LOCALAPPDATA', '')) / 'JDownloader 2.0' / 'folderwatch',
            Path('C:/JDownloader 2.0/folderwatch'),
            Path('C:/Program Files/JDownloader 2/folderwatch'),
            Path('C:/Program Files (x86)/JDownloader 2/folderwatch'),
            # 使用者目錄
            Path.home() / 'JDownloader 2.0' / 'folderwatch',
            Path.home() / 'JDownloader' / 'folderwatch',
            Path.home() / 'Downloads' / 'JDownloaderPortable' / 'azofreeware.com' / 'App' / 'JDownloader2' / 'folderwatch',
        ]

        for path in possible_paths:
            if path.exists():
                return str(path)

        # 嘗試從執行中的 JDownloader 找路徑
        jd_cfg_path = Path(os.environ.get('APPDATA', '')) / 'JDownloader 2.0' / 'cfg'
        if jd_cfg_path.exists():
            folderwatch = jd_cfg_path.parent / 'folderwatch'
            folderwatch.mkdir(exist_ok=True)
            return str(folderwatch)

        return None

    def create_crawljob(self, links: List[Dict], package_name: str,
                        password: str = None, auto_start: bool = True) -> bool:
        """
        建立 .crawljob 檔案

        Args:
            links: 連結列表 [{'url': '...', 'type': '...'}]
            package_name: 套件名稱
            password: 解壓密碼
            auto_start: 是否自動開始下載
        """
        if not self.folderwatch_path:
            logger.error("Folderwatch 路徑未設定")
            return False

        if not links:
            logger.warning("沒有連結可加入")
            return False

        # 清理套件名稱
        safe_name = self._sanitize_filename(package_name)

        # 合併所有連結 URL (一個 crawljob 可以包含多個連結)
        all_urls = '\n'.join(link['url'] for link in links)

        # 建立 crawljob 內容 (正確格式)
        crawljob_lines = [
            f"packageName={safe_name}",
            f"text={all_urls}",
            f"downloadFolder={self.download_dir}",
            "enabled=TRUE",
            f"autoStart={'TRUE' if auto_start else 'FALSE'}",
            "forcedStart=TRUE",
            "autoConfirm=TRUE",
            "deepAnalyseEnabled=TRUE",
        ]

        # 如果有密碼，設定自動解壓
        if password:
            crawljob_lines.append("extractAfterDownload=TRUE")
            crawljob_lines.append(f'extractPasswords=["{password}"]')

        # 寫入檔案
        filename = f"{safe_name}_{int(time.time())}.crawljob"
        filepath = Path(self.folderwatch_path) / filename

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(crawljob_lines))

            logger.info(f"已建立 crawljob: {filename} ({len(links)} 個連結)")
            return True

        except Exception as e:
            logger.error(f"建立 crawljob 失敗: {e}")
            return False

    def _sanitize_filename(self, name: str) -> str:
        """清理檔案名稱"""
        # 移除不合法字元
        name = re.sub(r'[<>:"/\\|?*]', '', name)
        # 限制長度
        name = name[:100]
        return name.strip() or 'download'

    def add_links(self, urls: List[str], package_name: str = None,
                  password: str = None) -> bool:
        """簡化的加入連結方法"""
        links = [{'url': url, 'type': 'Unknown'} for url in urls]
        return self.create_crawljob(links, package_name or 'Download', password)

    def check_jdownloader_running(self) -> bool:
        """檢查 JDownloader 是否在執行"""
        try:
            import subprocess
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq JDownloader2.exe'],
                capture_output=True, text=True
            )
            return 'JDownloader2.exe' in result.stdout
        except Exception:
            return False

    def clear_folderwatch(self) -> int:
        """清空 folderwatch 資料夾中的 crawljob 檔案"""
        if not self.folderwatch_path:
            return 0

        cleared = 0
        folderwatch = Path(self.folderwatch_path)

        try:
            for crawljob in folderwatch.glob('*.crawljob'):
                try:
                    crawljob.unlink()
                    cleared += 1
                    logger.debug(f"已刪除: {crawljob.name}")
                except Exception as e:
                    logger.warning(f"刪除 {crawljob.name} 失敗: {e}")

            if cleared > 0:
                logger.info(f"已清空 folderwatch 資料夾 ({cleared} 個 crawljob 檔案)")

        except Exception as e:
            logger.error(f"清空 folderwatch 失敗: {e}")

        return cleared

    def wait_for_jd_pickup(self, timeout: int = 10) -> bool:
        """
        等待 JDownloader 讀取 crawljob 檔案

        Args:
            timeout: 最長等待秒數

        Returns:
            True 如果 folderwatch 已清空 (JD 已處理), False 如果超時
        """
        if not self.folderwatch_path:
            return True

        folderwatch = Path(self.folderwatch_path)
        start_time = time.time()

        while time.time() - start_time < timeout:
            crawljobs = list(folderwatch.glob('*.crawljob'))
            if not crawljobs:
                logger.info("JDownloader 已接收所有 crawljob")
                return True
            time.sleep(1)

        # 超時，手動清空
        remaining = list(folderwatch.glob('*.crawljob'))
        if remaining:
            logger.warning(f"等待 JDownloader 處理超時，清空剩餘 {len(remaining)} 個 crawljob")
            self.clear_folderwatch()

        return False
