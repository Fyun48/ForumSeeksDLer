import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

from ..utils.logger import logger


class LinkExtractor:
    """下載連結提取器"""

    # 支援的檔案主機連結正則
    LINK_PATTERNS = [
        # MEGA
        (r'https?://mega\.nz/(?:file|folder)/[A-Za-z0-9_-]+(?:#[A-Za-z0-9_-]+)?', 'MEGA'),
        (r'https?://mega\.co\.nz/[^\s<>"\']+', 'MEGA'),

        # Gofile
        (r'https?://gofile\.io/d/[A-Za-z0-9]+', 'Gofile'),

        # Transfer.sh
        (r'https?://transfer\.sh/[^\s<>"\']+', 'Transfer'),

        # Katfile
        (r'https?://katfile\.com/[A-Za-z0-9]+(?:/[^\s<>"\']*)?', 'Katfile'),

        # Rosefile
        (r'https?://rosefile\.net/[A-Za-z0-9]+(?:/[^\s<>"\']*)?', 'Rosefile'),

        # Rapidgator
        (r'https?://rapidgator\.net/file/[^\s<>"\']+', 'Rapidgator'),

        # 1fichier
        (r'https?://1fichier\.com/\?[A-Za-z0-9]+', '1fichier'),

        # Uploaded
        (r'https?://uploaded\.net/file/[^\s<>"\']+', 'Uploaded'),

        # Mediafire
        (r'https?://(?:www\.)?mediafire\.com/(?:file|download)/[^\s<>"\']+', 'Mediafire'),
    ]

    # 密碼提取正則 (會依序嘗試)
    PASSWORD_PATTERNS = [
        # FastZone 多密碼格式 (用 * 分隔): 取第一個密碼
        r'(FAST[A-Za-z0-9]+_by_FastZone\.ORG)(?:\*|$)',
        # 其他站點密碼格式
        r'([A-Za-z0-9_]+_by_(?:OKFUN|MEGAFUNPRO|FCBZONE)\.(?:ORG|COM))',
        # 一般格式
        r'密[碼码][：:]\s*([a-zA-Z0-9@#$%^&*()_+=\-\.]+)',
        r'解[壓压]密[碼码][：:]\s*([a-zA-Z0-9@#$%^&*()_+=\-\.]+)',
        r'[Pp]ass(?:word)?[：:]\s*([a-zA-Z0-9@#$%^&*()_+=\-\.]+)',
        r'PW[：:]\s*([a-zA-Z0-9@#$%^&*()_+=\-\.]+)',
        r'解[压壓][：:]\s*([a-zA-Z0-9@#$%^&*()_+=\-\.]+)',
    ]

    # 壓縮檔名稱提取正則
    ARCHIVE_NAME_PATTERNS = [
        # 常見格式: 檔名.partXX.rar, 檔名.rar, 檔名.zip, 檔名.7z
        r'[\u4e00-\u9fff\w\.\-\(\)\[\]]+\.(?:part\d+\.)?rar(?=\s|$|<|")',
        r'[\u4e00-\u9fff\w\.\-\(\)\[\]]+\.zip(?=\s|$|<|")',
        r'[\u4e00-\u9fff\w\.\-\(\)\[\]]+\.7z(?=\s|$|<|")',
        # MEGA 連結後面的檔名 (file/xxx#yyy/檔名)
        r'mega\.nz/(?:file|folder)/[^/]+/([^\s<>"\']+\.(?:rar|zip|7z))',
    ]

    def extract_from_html(self, html: str) -> Dict:
        """從 HTML 提取下載連結、密碼和壓縮檔名稱"""
        soup = BeautifulSoup(html, 'lxml')

        # 取得帖子內容區域
        content_areas = soup.select('td.t_f, div.t_fsz, div.pcb')
        if not content_areas:
            # 備用：取整個 postlist
            content_areas = soup.select('div#postlist')

        logger.debug(f"找到 {len(content_areas)} 個內容區域")

        full_html = '\n'.join(str(area) for area in content_areas)
        full_text = '\n'.join(area.get_text(separator=' ') for area in content_areas)

        # 檢查是否還有隱藏內容標記
        if '需要感謝' in full_text or '隱藏內容' in full_text or '感謝後才能看' in full_text:
            logger.debug("頁面仍顯示需要感謝才能看的提示")

        # 提取連結
        links = self._extract_links(full_html)

        # 提取密碼
        password = self._extract_password(full_text)

        # 提取壓縮檔名稱
        archive_names = self._extract_archive_names(full_text, full_html)

        logger.info(f"提取到 {len(links)} 個連結, 密碼: {password if password else '無'}, 壓縮檔: {archive_names if archive_names else '無'}")

        return {
            'links': links,
            'password': password,
            'archive_names': archive_names
        }

    def _extract_links(self, html: str) -> List[Dict]:
        """提取所有下載連結"""
        links = []
        seen_urls = set()

        for pattern, link_type in self.LINK_PATTERNS:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for url in matches:
                # 清理 URL
                url = self._clean_url(url)
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    links.append({
                        'url': url,
                        'type': link_type
                    })

        return links

    def _clean_url(self, url: str) -> Optional[str]:
        """清理 URL"""
        if not url:
            return None

        # 移除尾端的特殊字元
        url = url.rstrip('.,;:!?\'"<>')

        # 移除 HTML 實體
        url = url.replace('&amp;', '&')

        # 驗證 URL 基本格式
        if not url.startswith('http'):
            return None

        return url

    def _extract_password(self, text: str) -> Optional[str]:
        """提取解壓密碼 (如有多個密碼，用 | 分隔返回)"""
        passwords = []

        # 先找 FastZone 格式的密碼（可能有多個用 * 分隔）
        multi_pattern = r'(FAST[A-Za-z0-9]+_by_FastZone\.ORG(?:\*[A-Za-z0-9_]+_by_[A-Za-z]+\.(?:ORG|COM))*)'
        multi_match = re.search(multi_pattern, text)
        if multi_match:
            # 分割多個密碼
            password_str = multi_match.group(1)
            for pwd in password_str.split('*'):
                pwd = pwd.strip()
                if pwd and pwd not in passwords:
                    passwords.append(pwd)

        # 如果沒找到多密碼格式，嘗試其他模式
        if not passwords:
            for pattern in self.PASSWORD_PATTERNS:
                match = re.search(pattern, text)
                if match:
                    password = match.group(1).strip()
                    # 清理密碼 - 移除常見的後綴文字
                    password = password.rstrip('.,;:!?\'"')
                    # 移除「複製代碼」等後綴
                    for suffix in ['複製代碼', '复制代码', 'Copy', 'copy']:
                        if password.endswith(suffix):
                            password = password[:-len(suffix)]
                    # 過濾太短或太長的密碼
                    if 2 <= len(password) <= 100 and password not in passwords:
                        passwords.append(password)

        # 返回所有密碼（用 | 分隔）或 None
        if passwords:
            return '|'.join(passwords)
        return None

    def _extract_archive_names(self, text: str, html: str) -> List[str]:
        """從帖子內容提取壓縮檔名稱"""
        archive_names = []
        seen = set()

        # 合併文字和 HTML 來搜尋
        combined = text + ' ' + html

        for pattern in self.ARCHIVE_NAME_PATTERNS:
            matches = re.findall(pattern, combined, re.IGNORECASE)
            for name in matches:
                # 清理檔名
                name = self._clean_archive_name(name)
                if name and name not in seen:
                    seen.add(name)
                    archive_names.append(name)

        # 額外嘗試從常見格式提取
        # 格式: "檔名: xxxx.rar" 或 "File: xxxx.rar"
        extra_patterns = [
            r'檔[案名][：:]\s*([\w\.\-\(\)\[\]]+\.(?:rar|zip|7z))',
            r'[Ff]ile\s*[：:]\s*([\w\.\-\(\)\[\]]+\.(?:rar|zip|7z))',
            r'下載檔案[：:]\s*([\w\.\-\(\)\[\]]+\.(?:rar|zip|7z))',
        ]

        for pattern in extra_patterns:
            matches = re.findall(pattern, combined, re.IGNORECASE)
            for name in matches:
                name = self._clean_archive_name(name)
                if name and name not in seen:
                    seen.add(name)
                    archive_names.append(name)

        return archive_names

    def _clean_archive_name(self, name: str) -> Optional[str]:
        """清理壓縮檔名稱"""
        if not name:
            return None

        # 移除常見的前綴
        name = name.strip()

        # 移除 URL 編碼
        try:
            from urllib.parse import unquote
            name = unquote(name)
        except Exception:
            pass

        # 移除副檔名之後的東西
        for ext in ['.rar', '.zip', '.7z']:
            if ext in name.lower():
                idx = name.lower().rfind(ext)
                name = name[:idx + len(ext)]
                break

        # 過濾太短的名稱
        if len(name) < 5:
            return None

        return name

    def filter_by_type(self, links: List[Dict], allowed_types: List[str]) -> List[Dict]:
        """根據類型篩選連結"""
        if not allowed_types:
            return links
        return [l for l in links if l['type'] in allowed_types]
