import requests
import time
from pathlib import Path
from typing import Optional, Dict
import yaml

from ..utils.cookie_loader import load_cookies_from_json, apply_cookies_to_session
from ..utils.logger import logger
from ..utils.paths import get_config_dir
from ..utils.profile_manager import ProfileManager


class ForumClient:
    """論壇 HTTP 客戶端"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            # 使用 profile manager 取得目前設定檔路徑
            profile_mgr = ProfileManager()
            config_path = profile_mgr.get_profile_config_path()

        self.config_path = Path(config_path)
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        self.base_url = self.config.get('forum', {}).get('base_url', 'https://fastzone.org')
        self.session = requests.Session()
        self._setup_session()
        self._load_cookies()

    def _setup_session(self):
        """設定 session headers"""
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
        })

    def _load_cookies(self):
        """載入 cookies"""
        cookie_file_cfg = self.config.get('auth', {}).get('cookie_file', 'config/cookies.json')
        cookie_path = Path(cookie_file_cfg)

        # 如果是相對路徑，以 config 檔案所在目錄為基準
        if not cookie_path.is_absolute():
            cookie_path = self.config_path.parent / cookie_file_cfg

        try:
            cookies = load_cookies_from_json(str(cookie_path))
            apply_cookies_to_session(self.session, cookies)
            logger.info(f"已載入 {len(cookies)} 個 cookies，來源: {cookie_path}")
        except FileNotFoundError:
            logger.warning(f"Cookie 檔案不存在: {cookie_path}")
            logger.warning("請從瀏覽器匯出 cookies 或在設定中導入")

    def check_login(self) -> bool:
        """檢查是否已登入"""
        try:
            resp = self.session.get(f"{self.base_url}/home.php?mod=space", timeout=10)
            # 如果能存取個人空間且不是登入頁面，表示已登入
            if 'login' not in resp.url and '登錄' not in resp.text[:1000]:
                logger.info("登入狀態: 已登入")
                return True
            logger.warning("登入狀態: 未登入")
            return False
        except Exception as e:
            logger.error(f"檢查登入狀態失敗: {e}")
            return False

    def get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """GET 請求"""
        try:
            delay = self.config.get('scraper', {}).get('delay_between_requests', 2)
            time.sleep(delay)
            resp = self.session.get(url, timeout=30, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as e:
            logger.error(f"GET 請求失敗 {url}: {e}")
            return None

    def get_forum_page(self, fid: str, page: int = 1) -> Optional[str]:
        """取得版區頁面 HTML"""
        url = f"{self.base_url}/forum.php?mod=forumdisplay&fid={fid}&page={page}"
        resp = self.get(url)
        if resp:
            return resp.text
        return None

    def get_thread_page(self, tid: str) -> Optional[str]:
        """取得帖子頁面 HTML"""
        url = f"{self.base_url}/forum.php?mod=viewthread&tid={tid}"
        resp = self.get(url)
        if resp:
            return resp.text
        return None
