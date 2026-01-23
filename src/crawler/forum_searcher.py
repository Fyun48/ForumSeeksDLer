"""
論壇帖子搜尋器
支援論壇搜尋 API 和本地篩選兩種模式
支援多關鍵字搜尋：空格=AND, |=OR, "..."=精確詞組
"""
import re
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote
from bs4 import BeautifulSoup

from .forum_client import ForumClient
from .post_parser import PostParser
from ..utils.logger import logger


class KeywordParser:
    """
    關鍵字解析器

    支援語法：
    - 空格分隔 = AND（都要符合）
    - | 分隔 = OR（任一符合）
    - "..." = 精確詞組
    - 混合使用: "ROSE Vol" | 玫瑰  (精確詞組 OR 玫瑰)
    """

    @staticmethod
    def parse(keyword: str) -> Tuple[str, List[Dict]]:
        """
        解析關鍵字字串

        Returns:
            (api_keyword, conditions)
            - api_keyword: 用於 API 搜尋的主關鍵字
            - conditions: 條件列表，每個條件是 {'type': 'and'|'or', 'terms': [...]}
        """
        if not keyword:
            return '', []

        keyword = keyword.strip()

        # 檢查是否有 OR 運算子
        if '|' in keyword:
            # OR 模式
            parts = [p.strip() for p in keyword.split('|') if p.strip()]
            all_terms = []
            for part in parts:
                terms = KeywordParser._parse_single_group(part)
                all_terms.extend(terms)

            # 使用第一個詞作為 API 搜尋關鍵字
            api_keyword = all_terms[0] if all_terms else keyword
            return api_keyword, [{'type': 'or', 'terms': all_terms}]
        else:
            # AND 模式（空格分隔）
            terms = KeywordParser._parse_single_group(keyword)
            api_keyword = terms[0] if terms else keyword
            return api_keyword, [{'type': 'and', 'terms': terms}]

    @staticmethod
    def _parse_single_group(text: str) -> List[str]:
        """解析單一群組（處理引號內的精確詞組）"""
        terms = []
        # 先提取引號內的詞組
        quoted_pattern = r'"([^"]+)"'
        quoted_matches = re.findall(quoted_pattern, text)
        terms.extend(quoted_matches)

        # 移除已提取的引號詞組
        remaining = re.sub(quoted_pattern, ' ', text)

        # 分割剩餘的詞
        for word in remaining.split():
            word = word.strip()
            if word:
                terms.append(word)

        return terms

    @staticmethod
    def matches(title: str, conditions: List[Dict]) -> bool:
        """
        檢查標題是否符合條件

        Args:
            title: 帖子標題
            conditions: 條件列表
        """
        if not conditions:
            return True

        title_lower = title.lower()

        for condition in conditions:
            cond_type = condition['type']
            terms = condition['terms']

            if cond_type == 'and':
                # AND: 所有詞都要符合
                if all(term.lower() in title_lower for term in terms):
                    return True
            elif cond_type == 'or':
                # OR: 任一詞符合即可
                if any(term.lower() in title_lower for term in terms):
                    return True

        return False


class ForumSearcher:
    """論壇帖子搜尋器"""

    def __init__(self, client: ForumClient):
        """
        初始化

        Args:
            client: 論壇客戶端
        """
        self.client = client
        self.base_url = client.base_url

    def search(self, keyword: str, fids: List[str],
               max_pages: int = 3, use_api_first: bool = True) -> List[Dict]:
        """
        搜尋帖子

        支援多關鍵字語法：
        - 空格 = AND（都要符合）: "ROSE JAV" 找包含 ROSE 且包含 JAV 的帖子
        - | = OR（任一符合）: "ROSE|玫瑰" 找包含 ROSE 或玫瑰的帖子
        - "..." = 精確詞組: '"ROSE Vol"' 找包含完整 "ROSE Vol" 的帖子

        Args:
            keyword: 搜尋關鍵字（支援 AND/OR 語法）
            fids: 要搜尋的版區 ID 列表
            max_pages: 每個版區最多爬幾頁 (本地模式用)
            use_api_first: 是否優先使用論壇搜尋 API

        Returns:
            帖子列表，每筆包含:
            - tid, title, author, post_date, fid, forum_name, post_url
        """
        if not keyword or not fids:
            return []

        # 解析關鍵字
        api_keyword, conditions = KeywordParser.parse(keyword)
        logger.info(f"搜尋關鍵字: {keyword}")
        logger.info(f"  API 關鍵字: {api_keyword}")
        logger.info(f"  條件: {conditions}")
        logger.info(f"  版區: {fids}")

        all_results = []

        for fid in fids:
            # 跳過分類 ID
            if fid.startswith('gid_') or fid.startswith('cat_'):
                continue

            results = []

            # 優先使用論壇搜尋 API（使用解析後的主關鍵字）
            if use_api_first:
                results = self._search_via_api(api_keyword, fid)

            # 如果 API 沒有結果，改用本地爬取篩選
            if not results:
                logger.info(f"版區 {fid} API 搜尋無結果，改用本地篩選")
                results = self._search_via_scraping(api_keyword, fid, max_pages)

            all_results.extend(results)

        # 合併去重
        merged = self._merge_results(all_results)

        # 套用多關鍵字條件過濾
        if conditions and len(conditions[0].get('terms', [])) > 1:
            before_filter = len(merged)
            merged = [
                post for post in merged
                if KeywordParser.matches(post.get('title', ''), conditions)
            ]
            after_filter = len(merged)
            if before_filter != after_filter:
                logger.info(f"多關鍵字過濾: {before_filter} -> {after_filter} 筆")

        logger.info(f"搜尋完成，共找到 {len(merged)} 筆結果")

        return merged

    def _search_via_api(self, keyword: str, fid: str) -> List[Dict]:
        """
        使用論壇搜尋 API

        Discuz! 搜尋 URL:
        search.php?mod=forum&searchsubmit=yes&srchtxt=關鍵字&searchsort=lastpost&fid=版區ID
        """
        try:
            encoded_keyword = quote(keyword)
            url = (
                f"{self.base_url}/search.php?"
                f"mod=forum&searchsubmit=yes&srchtxt={encoded_keyword}"
                f"&searchsort=lastpost&fid={fid}"
            )

            resp = self.client.get(url)
            if not resp:
                return []

            html = resp.text

            # 檢查是否需要登入或有錯誤
            if '登錄' in html[:1000] or '沒有找到' in html:
                return []

            # 解析搜尋結果頁面
            return self._parse_search_results(html, fid)

        except Exception as e:
            logger.warning(f"API 搜尋失敗: {e}")
            return []

    def _parse_search_results(self, html: str, fid: str) -> List[Dict]:
        """解析搜尋結果頁面"""
        soup = BeautifulSoup(html, 'lxml')
        results = []

        # Discuz! 搜尋結果結構
        # 結果列表在 <li class="pbw">
        for item in soup.select('li.pbw'):
            try:
                result = self._parse_search_item(item, fid)
                if result:
                    results.append(result)
            except Exception as e:
                logger.debug(f"解析搜尋結果項目失敗: {e}")
                continue

        # 另一種搜尋結果結構 (threadlist)
        if not results:
            for item in soup.select('div.threadlist ul li'):
                try:
                    result = self._parse_search_item_alt(item, fid)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.debug(f"解析搜尋結果項目失敗: {e}")
                    continue

        return results

    def _parse_search_item(self, item, fid: str) -> Optional[Dict]:
        """解析單個搜尋結果項目"""
        # 標題連結
        title_link = item.select_one('h3 a') or item.select_one('a.xst')
        if not title_link:
            return None

        title = title_link.get_text(strip=True)
        href = title_link.get('href', '')

        # 提取 tid
        tid = self._extract_tid(href)
        if not tid:
            return None

        # 解析結構：<p><span>日期</span> - <span>回復</span> - <span>作者</span> - <span><a>版區</a></span></p>
        # 找最後一個 p 標籤（包含日期、作者、版區資訊）
        info_p = item.select('p')[-1] if item.select('p') else None

        author = ''
        post_date = ''
        forum_name = ''
        actual_fid = ''  # 從搜尋結果中解析的實際 FID

        if info_p:
            spans = info_p.find_all('span')
            if len(spans) >= 1:
                # 第一個 span 是日期
                post_date = spans[0].get_text(strip=True)
            if len(spans) >= 3:
                # 第三個 span 是作者
                author = spans[2].get_text(strip=True)
            if len(spans) >= 4:
                # 第四個 span 包含版區連結
                forum_link = spans[3].find('a')
                if forum_link:
                    forum_name = forum_link.get_text(strip=True)
                    # 從連結中提取實際 FID
                    forum_href = forum_link.get('href', '')
                    fid_match = re.search(r'fid[=\-](\d+)', forum_href)
                    if fid_match:
                        actual_fid = fid_match.group(1)
                else:
                    forum_name = spans[3].get_text(strip=True)

        # 如果沒找到版區，嘗試其他選擇器
        if not forum_name or not actual_fid:
            forum_elem = item.select_one('a.xi1[href*="fid"]') or item.select_one('a[href*="forumdisplay"]')
            if forum_elem:
                if not forum_name:
                    forum_name = forum_elem.get_text(strip=True)
                if not actual_fid:
                    forum_href = forum_elem.get('href', '')
                    fid_match = re.search(r'fid[=\-](\d+)', forum_href)
                    if fid_match:
                        actual_fid = fid_match.group(1)

        return {
            'tid': tid,
            'title': title,
            'author': author,
            'post_date': post_date,
            'fid': actual_fid if actual_fid else fid,  # 優先使用實際 FID
            'forum_name': forum_name,
            'post_url': href if href.startswith('http') else f"{self.base_url}/{href}"
        }

    def _parse_search_item_alt(self, item, fid: str) -> Optional[Dict]:
        """解析另一種搜尋結果項目格式"""
        link = item.select_one('a')
        if not link:
            return None

        title = link.get_text(strip=True)
        href = link.get('href', '')

        tid = self._extract_tid(href)
        if not tid:
            return None

        return {
            'tid': tid,
            'title': title,
            'author': '',
            'post_date': '',
            'fid': fid,
            'forum_name': '',
            'post_url': href if href.startswith('http') else f"{self.base_url}/{href}"
        }

    def _search_via_scraping(self, keyword: str, fid: str, max_pages: int) -> List[Dict]:
        """
        爬取版區頁面後本地篩選

        Args:
            keyword: 搜尋關鍵字
            fid: 版區 ID
            max_pages: 最多爬幾頁
        """
        results = []
        keyword_lower = keyword.lower()

        for page in range(1, max_pages + 1):
            html = self.client.get_forum_page(fid, page)
            if not html:
                break

            # 解析帖子列表
            posts = self._parse_forum_list(html, fid)

            # 篩選符合關鍵字的帖子
            for post in posts:
                if keyword_lower in post['title'].lower():
                    results.append(post)

            # 如果這頁帖子很少，可能已經到最後一頁
            if len(posts) < 10:
                break

        return results

    def _parse_forum_list(self, html: str, fid: str) -> List[Dict]:
        """解析版區帖子列表"""
        soup = BeautifulSoup(html, 'lxml')
        posts = []

        # 取得版區名稱
        forum_name = ''
        title_elem = soup.select_one('h1.xs2 a') or soup.select_one('#pt .z a:last-child')
        if title_elem:
            forum_name = title_elem.get_text(strip=True)

        # Discuz 論壇的帖子列表結構
        for thread in soup.select('tbody[id^="normalthread_"]'):
            try:
                post = self._parse_thread_item(thread, fid, forum_name)
                if post:
                    posts.append(post)
            except Exception as e:
                logger.debug(f"解析帖子失敗: {e}")
                continue

        return posts

    def _parse_thread_item(self, thread_elem, fid: str, forum_name: str) -> Optional[Dict]:
        """解析單個帖子項目"""
        # 提取 thread_id
        elem_id = thread_elem.get('id', '')
        match = re.search(r'normalthread_(\d+)', elem_id)
        if not match:
            return None
        tid = match.group(1)

        # 提取標題和連結
        title_elem = thread_elem.select_one('a.s.xst')
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        href = title_elem.get('href', '')

        # 提取作者
        author_elem = thread_elem.select_one('td.by cite a')
        author = author_elem.get_text(strip=True) if author_elem else ''

        # 提取日期
        date_elem = thread_elem.select_one('td.by em span') or thread_elem.select_one('td.by em')
        post_date = date_elem.get_text(strip=True) if date_elem else ''

        return {
            'tid': tid,
            'title': title,
            'author': author,
            'post_date': post_date,
            'fid': fid,
            'forum_name': forum_name,
            'post_url': href if href.startswith('http') else f"{self.base_url}/{href}"
        }

    def _extract_tid(self, href: str) -> Optional[str]:
        """從連結中提取 tid"""
        match = re.search(r'tid[=\-](\d+)', href)
        if match:
            return match.group(1)
        # 另一種格式: thread-123-1-1.html
        match = re.search(r'thread-(\d+)-', href)
        if match:
            return match.group(1)
        return None

    def _merge_results(self, results: List[Dict]) -> List[Dict]:
        """合併並去重搜尋結果"""
        seen_tids = set()
        merged = []

        for result in results:
            tid = result['tid']
            if tid not in seen_tids:
                seen_tids.add(tid)
                merged.append(result)

        return merged
