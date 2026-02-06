"""
DLP01 自動更新模組

從 GitHub Releases 檢查新版本並提供下載功能
"""
import os
import re
import json
import tempfile
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from .version import VERSION, GITHUB_OWNER, GITHUB_REPO, is_newer_version
from .utils.logger import logger
from .utils.paths import get_data_dir


class UpdateChecker:
    """更新檢查器"""

    # GitHub API URL
    GITHUB_API_BASE = "https://api.github.com"

    # 快取設定
    CACHE_FILE = "update_cache.json"
    CACHE_DURATION = timedelta(hours=6)  # 快取 6 小時

    def __init__(self, owner: str = None, repo: str = None):
        """
        初始化更新檢查器

        Args:
            owner: GitHub 用戶名/組織名
            repo: GitHub 儲存庫名稱
        """
        self.owner = owner or GITHUB_OWNER
        self.repo = repo or GITHUB_REPO
        self._cache_dir = get_data_dir()
        self._cache_path = self._cache_dir / self.CACHE_FILE

    def is_configured(self) -> bool:
        """檢查是否已設定 GitHub 資訊"""
        return bool(self.owner and self.repo)

    def get_releases_url(self) -> str:
        """取得 GitHub Releases 頁面 URL"""
        if not self.is_configured():
            return ""
        return f"https://github.com/{self.owner}/{self.repo}/releases"

    def get_latest_release_api_url(self) -> str:
        """取得最新版本 API URL"""
        return f"{self.GITHUB_API_BASE}/repos/{self.owner}/{self.repo}/releases/latest"

    def _load_cache(self) -> Optional[Dict]:
        """載入快取"""
        try:
            if not self._cache_path.exists():
                return None

            with open(self._cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)

            # 檢查快取是否過期
            cached_time = datetime.fromisoformat(cache.get('cached_at', '2000-01-01'))
            if datetime.now() - cached_time > self.CACHE_DURATION:
                return None

            return cache.get('data')
        except Exception:
            return None

    def _save_cache(self, data: Dict):
        """儲存快取"""
        try:
            cache = {
                'cached_at': datetime.now().isoformat(),
                'data': data
            }
            with open(self._cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"儲存更新快取失敗: {e}")

    def check_for_updates(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        檢查是否有新版本

        Args:
            use_cache: 是否使用快取

        Returns:
            {
                'available': bool,       # 是否有新版本
                'current_version': str,  # 目前版本
                'latest_version': str,   # 最新版本
                'release_notes': str,    # 更新說明
                'download_url': str,     # 下載連結
                'html_url': str,         # GitHub 頁面連結
                'published_at': str,     # 發佈時間
                'error': str,            # 錯誤訊息 (如果有)
            }
        """
        result = {
            'available': False,
            'current_version': VERSION,
            'latest_version': None,
            'release_notes': None,
            'download_url': None,
            'html_url': None,
            'published_at': None,
            'error': None
        }

        # 檢查是否已設定
        if not self.is_configured():
            result['error'] = "尚未設定 GitHub 儲存庫資訊"
            return result

        # 嘗試使用快取
        if use_cache:
            cached = self._load_cache()
            if cached:
                # 更新目前版本為實際執行的版本
                cached['current_version'] = VERSION
                # 重新檢查是否需要更新 (可能已經更新過了)
                latest = cached.get('latest_version', '')
                cached['available'] = latest and is_newer_version(latest)
                logger.debug(f"使用快取的更新資訊 (current={VERSION}, latest={latest}, available={cached['available']})")
                return cached

        # 從 GitHub API 取得最新版本
        try:
            import urllib.request
            import ssl

            # 建立不驗證 SSL 的 context (避免某些環境的憑證問題)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            url = self.get_latest_release_api_url()
            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': f'DLP01/{VERSION}',
                    'Accept': 'application/vnd.github.v3+json'
                }
            )

            with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                data = json.loads(response.read().decode('utf-8'))

            # 解析版本號
            tag_name = data.get('tag_name', '')
            latest_version = tag_name.lstrip('vV')

            result['latest_version'] = latest_version
            result['release_notes'] = data.get('body', '')
            result['html_url'] = data.get('html_url', '')
            result['published_at'] = data.get('published_at', '')

            # 尋找安裝檔下載連結
            assets = data.get('assets', [])
            for asset in assets:
                name = asset.get('name', '').lower()
                if name.endswith('.exe') and 'setup' in name:
                    result['download_url'] = asset.get('browser_download_url')
                    break

            # 如果沒找到 setup.exe，找任何 .exe
            if not result['download_url']:
                for asset in assets:
                    if asset.get('name', '').lower().endswith('.exe'):
                        result['download_url'] = asset.get('browser_download_url')
                        break

            # 如果還是沒有，用 zip
            if not result['download_url']:
                for asset in assets:
                    if asset.get('name', '').lower().endswith('.zip'):
                        result['download_url'] = asset.get('browser_download_url')
                        break

            # 檢查是否有新版本
            if latest_version and is_newer_version(latest_version):
                result['available'] = True
                logger.info(f"發現新版本: v{latest_version} (目前: v{VERSION})")
            else:
                logger.debug(f"已是最新版本: v{VERSION}")

            # 儲存快取
            self._save_cache(result)

        except urllib.error.HTTPError as e:
            if e.code == 404:
                result['error'] = "找不到儲存庫或尚無發佈版本"
            else:
                result['error'] = f"HTTP 錯誤: {e.code}"
            logger.warning(f"檢查更新失敗: {result['error']}")

        except urllib.error.URLError as e:
            result['error'] = f"網路錯誤: {e.reason}"
            logger.warning(f"檢查更新失敗: {result['error']}")

        except Exception as e:
            result['error'] = str(e)
            logger.warning(f"檢查更新失敗: {e}")

        return result

    def open_download_page(self, url: str = None):
        """
        開啟下載頁面

        Args:
            url: 下載連結，如果為 None 則開啟 Releases 頁面
        """
        target_url = url or self.get_releases_url()
        if target_url:
            webbrowser.open(target_url)

    def download_update(self, download_url: str, progress_callback=None) -> Optional[Path]:
        """
        下載更新檔案

        Args:
            download_url: 下載連結
            progress_callback: 進度回呼函式 (received, total)

        Returns:
            下載的檔案路徑，失敗則回傳 None
        """
        try:
            import urllib.request
            import ssl

            # 從 URL 取得檔名
            filename = download_url.split('/')[-1]
            temp_dir = Path(tempfile.gettempdir()) / "dlp01_update"
            temp_dir.mkdir(parents=True, exist_ok=True)
            dest_path = temp_dir / filename

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(
                download_url,
                headers={'User-Agent': f'DLP01/{VERSION}'}
            )

            logger.info(f"開始下載更新: {filename}")

            with urllib.request.urlopen(req, timeout=300, context=ctx) as response:
                total_size = int(response.headers.get('content-length', 0))
                received = 0
                block_size = 8192

                with open(dest_path, 'wb') as f:
                    while True:
                        block = response.read(block_size)
                        if not block:
                            break
                        f.write(block)
                        received += len(block)
                        if progress_callback:
                            progress_callback(received, total_size)

            logger.info(f"下載完成: {dest_path}")
            return dest_path

        except Exception as e:
            logger.error(f"下載更新失敗: {e}")
            return None

    def run_installer(self, installer_path: Path) -> bool:
        """
        執行安裝程式

        Args:
            installer_path: 安裝程式路徑

        Returns:
            是否成功啟動
        """
        try:
            if not installer_path.exists():
                logger.error(f"安裝程式不存在: {installer_path}")
                return False

            # Windows: 使用 ShellExecute 執行
            if os.name == 'nt':
                os.startfile(str(installer_path))
            else:
                subprocess.Popen([str(installer_path)])

            logger.info(f"已啟動安裝程式: {installer_path}")
            return True

        except Exception as e:
            logger.error(f"啟動安裝程式失敗: {e}")
            return False


class UpdateResult:
    """更新檢查結果的包裝類別"""

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    @property
    def available(self) -> bool:
        return self._data.get('available', False)

    @property
    def current_version(self) -> str:
        return self._data.get('current_version', VERSION)

    @property
    def latest_version(self) -> str:
        return self._data.get('latest_version', '')

    @property
    def release_notes(self) -> str:
        return self._data.get('release_notes', '')

    @property
    def download_url(self) -> str:
        return self._data.get('download_url', '')

    @property
    def html_url(self) -> str:
        return self._data.get('html_url', '')

    @property
    def error(self) -> str:
        return self._data.get('error', '')

    @property
    def has_error(self) -> bool:
        return bool(self._data.get('error'))

    def get_formatted_notes(self, max_length: int = 500) -> str:
        """取得格式化的更新說明"""
        notes = self.release_notes or "無更新說明"
        if len(notes) > max_length:
            notes = notes[:max_length] + "..."
        return notes


# 全域更新檢查器實例
_updater: Optional[UpdateChecker] = None


def get_updater() -> UpdateChecker:
    """取得全域更新檢查器"""
    global _updater
    if _updater is None:
        _updater = UpdateChecker()
    return _updater


def check_for_updates(use_cache: bool = True) -> UpdateResult:
    """
    便捷函式：檢查更新

    Args:
        use_cache: 是否使用快取

    Returns:
        UpdateResult 物件
    """
    updater = get_updater()
    result = updater.check_for_updates(use_cache)
    return UpdateResult(result)
