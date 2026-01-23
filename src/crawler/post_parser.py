import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

from ..utils.logger import logger


class PostParser:
    """帖子解析器"""

    def __init__(self, title_filters: List[str], max_posts: int = 15):
        self.title_filters = title_filters
        self.max_posts = max_posts

    def parse_forum_list(self, html: str, forum_section: str) -> List[Dict]:
        """解析版區帖子列表"""
        soup = BeautifulSoup(html, 'lxml')
        posts = []

        # Discuz 論壇的帖子列表結構
        thread_list = soup.select('tbody[id^="normalthread_"]')

        # 只處理前 max_posts 筆
        for thread in thread_list[:self.max_posts]:
            try:
                post = self._parse_thread_item(thread, forum_section)
                if post and self._matches_filter(post['title']):
                    posts.append(post)
            except Exception as e:
                logger.debug(f"解析帖子失敗: {e}")
                continue

        logger.info(f"從 {forum_section} 解析到 {len(posts)} 個符合條件的帖子 (檢查前 {self.max_posts} 筆)")
        return posts

    def _parse_thread_item(self, thread_elem, forum_section: str) -> Optional[Dict]:
        """解析單個帖子項目"""
        # 提取 thread_id
        elem_id = thread_elem.get('id', '')
        match = re.search(r'normalthread_(\d+)', elem_id)
        if not match:
            return None
        thread_id = match.group(1)

        # 提取標題和連結
        title_elem = thread_elem.select_one('a.s.xst')
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        href = title_elem.get('href', '')

        # 提取作者
        author_elem = thread_elem.select_one('td.by cite a')
        author = author_elem.get_text(strip=True) if author_elem else 'Unknown'

        # 判斷 host_type
        host_type = self._detect_host_type(title)

        # 從標題提取檔案大小 (格式: [xxx@數字MB] 或 [xxx@數字GB])
        file_size_mb = self._extract_file_size(title)

        return {
            'thread_id': thread_id,
            'title': title,
            'author': author,
            'forum_section': forum_section,
            'post_url': href if href.startswith('http') else f"forum.php?mod=viewthread&tid={thread_id}",
            'host_type': host_type,
            'file_size_mb': file_size_mb
        }

    def _extract_file_size(self, title: str) -> float:
        """從標題中提取檔案大小 (MB)"""
        # 尋找 [xxx@數字MB] 或 [xxx@數字GB] 格式
        # 例如: [MEGA@IE@163.4MB] 或 [Gofile@HTTP@1.2GB]
        match = re.search(r'\[.*?@([\d.]+)\s*(MB|GB|TB)\s*\]', title, re.IGNORECASE)
        if match:
            size = float(match.group(1))
            unit = match.group(2).upper()
            if unit == 'GB':
                size *= 1024
            elif unit == 'TB':
                size *= 1024 * 1024
            return size
        return 0

    def _matches_filter(self, title: str) -> bool:
        """檢查標題是否符合篩選條件"""
        return any(f.lower() in title.lower() for f in self.title_filters)

    def _detect_host_type(self, title: str) -> str:
        """從標題偵測檔案主機類型"""
        title_lower = title.lower()
        if 'mg@jd' in title_lower or 'mega' in title_lower:
            return 'MEGA'
        elif 'transfer' in title_lower:
            return 'Transfer'
        elif 'gofile' in title_lower:
            return 'Gofile'
        elif 'katfile' in title_lower:
            return 'Katfile'
        return 'Unknown'


class ThreadContentParser:
    """帖子內容解析器"""

    # 常見的下載連結正則
    LINK_PATTERNS = [
        (r'https?://mega\.nz/[^\s<>"\']+', 'MEGA'),
        (r'https?://gofile\.io/d/[^\s<>"\']+', 'Gofile'),
        (r'https?://transfer\.sh/[^\s<>"\']+', 'Transfer'),
        (r'https?://katfile\.com/[^\s<>"\']+', 'Katfile'),
        (r'https?://rosefile\.net/[^\s<>"\']+', 'Rosefile'),
        (r'https?://rapidgator\.net/[^\s<>"\']+', 'Rapidgator'),
    ]

    # 密碼正則
    PASSWORD_PATTERNS = [
        r'密[碼码][：:]\s*([^\s<>]+)',
        r'解[壓压]密[碼码][：:]\s*([^\s<>]+)',
        r'[Pp]ass(?:word)?[：:]\s*([^\s<>]+)',
        r'PW[：:]\s*([^\s<>]+)',
    ]

    def parse_thread_content(self, html: str) -> Dict:
        """解析帖子內容，提取連結和密碼"""
        soup = BeautifulSoup(html, 'lxml')

        # 找到帖子內容區域
        content_divs = soup.select('td.t_f')
        if not content_divs:
            content_divs = soup.select('div.t_fsz')

        full_text = ' '.join(div.get_text() for div in content_divs)
        full_html = ' '.join(str(div) for div in content_divs)

        # 提取連結
        links = []
        for pattern, link_type in self.LINK_PATTERNS:
            matches = re.findall(pattern, full_html, re.IGNORECASE)
            for url in matches:
                # 清理 URL
                url = url.split('"')[0].split("'")[0].split('<')[0]
                if url not in [l['url'] for l in links]:
                    links.append({'url': url, 'type': link_type})

        # 提取密碼
        password = None
        for pattern in self.PASSWORD_PATTERNS:
            match = re.search(pattern, full_text)
            if match:
                password = match.group(1).strip()
                break

        return {
            'links': links,
            'password': password
        }
