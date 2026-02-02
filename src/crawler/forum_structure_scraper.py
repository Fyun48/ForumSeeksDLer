"""
論壇版區結構爬取器
爬取論壇的完整版面結構（支援 Discuz! 論壇）
針對 fastzone.org 的特定 HTML 結構優化
"""
import re
from typing import List, Dict, Optional, Set
from bs4 import BeautifulSoup

from .forum_client import ForumClient
from ..database.db_manager import DatabaseManager
from ..utils.logger import logger


class ForumStructureScraper:
    """論壇版區結構爬取器"""

    def __init__(self, client: ForumClient, max_depth: int = 4):
        """
        初始化

        Args:
            client: 論壇客戶端
            max_depth: 最大遞迴深度
        """
        self.client = client
        self.max_depth = max_depth
        self.base_url = client.base_url
        self._visited_fids: Set[str] = set()

    def scrape_all_sections(self, deep_scrape: bool = True) -> List[Dict]:
        """
        爬取完整版區結構

        Args:
            deep_scrape: 是否深入爬取各版區頁面的子版區

        Returns:
            樹狀結構的版區列表
        """
        logger.info("開始爬取論壇版區結構...")
        self._visited_fids.clear()

        # 先爬取論壇首頁
        html = self._get_forum_index()
        if not html:
            logger.error("無法取得論壇首頁")
            return []

        # 解析主分類和版區
        sections = self._parse_forum_index(html)
        logger.info(f"從首頁解析到 {len(sections)} 個主分類")

        # 深入爬取各版區的子版區
        if deep_scrape:
            self._deep_scrape_subforums(sections)

        # 計算總版區數
        total_count = self._count_sections(sections)
        logger.info(f"共解析到 {total_count} 個版區")

        return sections

    def _deep_scrape_subforums(self, sections: List[Dict], depth: int = 0):
        """
        深入爬取各版區頁面的子版區

        Args:
            sections: 版區列表
            depth: 當前深度
        """
        if depth >= self.max_depth:
            return

        for section in sections:
            fid = section['fid']

            # 跳過分類 ID
            if fid.startswith('gid_') or fid.startswith('cat_'):
                # 遞迴處理子項目
                if section.get('children'):
                    self._deep_scrape_subforums(section['children'], depth)
                continue

            # 爬取此版區頁面尋找子版區
            subforums = self._scrape_forum_page_subforums(fid)
            if subforums:
                # 合併到現有子版區
                existing_fids = {c['fid'] for c in section.get('children', [])}
                for subforum in subforums:
                    if subforum['fid'] not in existing_fids:
                        subforum['parent_fid'] = fid
                        subforum['level'] = section.get('level', 1) + 1
                        if 'children' not in section:
                            section['children'] = []
                        section['children'].append(subforum)
                        logger.info(f"  發現子版區: {subforum['name']} (FID: {subforum['fid']})")

            # 遞迴處理子版區
            if section.get('children'):
                self._deep_scrape_subforums(section['children'], depth + 1)

    def _scrape_forum_page_subforums(self, fid: str) -> List[Dict]:
        """
        爬取單個版區頁面，找出其子版區

        結構：
        <div id="subforum_XX" class="bm_c">
            <div class="forum-icon">
                <a href="forum.php?mod=forumdisplay&fid=YY">
            <p class="mb-0"><a href="...fid=YY">子版區名稱</a></p>
        </div>
        """
        try:
            url = f"{self.base_url}/forum.php?mod=forumdisplay&fid={fid}"
            resp = self.client.get(url)
            if not resp:
                return []

            soup = BeautifulSoup(resp.text, 'lxml')

            # 找子版區區塊
            subforum_div = soup.find('div', id=re.compile(f'^subforum_{fid}$'))
            if not subforum_div:
                return []

            subforums = []

            # 找所有子版區連結
            for p_tag in subforum_div.find_all('p', class_='mb-0'):
                link = p_tag.find('a', href=re.compile(r'mod=forumdisplay.*fid=\d+'))
                if link:
                    sub_fid = self._extract_fid(link.get('href', ''))
                    if sub_fid and sub_fid not in self._visited_fids:
                        self._visited_fids.add(sub_fid)
                        name = link.get_text(strip=True)
                        name = self._clean_forum_name(name)
                        subforums.append({
                            'fid': sub_fid,
                            'name': name,
                            'parent_fid': fid,
                            'level': 2,
                            'children': []
                        })

            return subforums

        except Exception as e:
            logger.debug(f"爬取版區 {fid} 子版區失敗: {e}")
            return []

    def _count_sections(self, sections: List[Dict]) -> int:
        """計算版區總數"""
        count = 0
        for section in sections:
            # 不計算分類本身 (gid_ 或 cat_ 開頭)
            if not section['fid'].startswith('gid_') and not section['fid'].startswith('cat_'):
                count += 1
            count += self._count_sections(section.get('children', []))
        return count

    def scrape_and_save(self) -> int:
        """
        爬取並儲存到資料庫

        Returns:
            儲存的版區數量
        """
        sections = self.scrape_all_sections()
        if not sections:
            return 0

        # 扁平化樹狀結構
        flat_sections = self._flatten_sections(sections)

        # 儲存到資料庫
        db = DatabaseManager()
        db.save_forum_sections_batch(flat_sections)

        logger.info(f"已儲存 {len(flat_sections)} 個版區到資料庫")
        return len(flat_sections)

    def _get_forum_index(self) -> Optional[str]:
        """取得論壇首頁 HTML"""
        resp = self.client.get(f"{self.base_url}/forum.php")
        if resp:
            return resp.text
        return None

    def _parse_forum_index(self, html: str) -> List[Dict]:
        """
        解析論壇首頁，取得主分類和版區

        結構分析:
        - 主分類: <div class="bm bmw flg cl"> 包含 <div id="category_X" class="bm_c">
        - 分類標題: <a href="forum.php?gid=X">分類名稱</a>
        - 版區: <div class="row py-1 cat-box"> 內的 <a href="...fid=X">
        - 子版區: 在 <p class="mb-0"> 內用 ├─ 標示
        """
        soup = BeautifulSoup(html, 'lxml')
        sections = []

        # 找所有主分類區塊 (div.bm.bmw.flg.cl)
        for category_block in soup.find_all('div', class_=re.compile(r'bm\s+bmw.*flg')):
            category_info = self._parse_category_block_v2(category_block)
            if category_info:
                sections.append(category_info)

        # 如果上面方法沒找到，用備用方法
        if not sections:
            logger.info("使用備用方法解析版區結構...")
            sections = self._parse_forum_index_fallback(soup)

        return sections

    def _parse_category_block_v2(self, category_block) -> Optional[Dict]:
        """解析單個分類區塊 (新版)"""
        # 找分類標題 (在 bm_h 內)
        header = category_block.find('div', class_='bm_h')
        if not header:
            return None

        # 取得分類名稱和 gid
        category_name = "未分類"
        category_gid = None

        title_link = header.find('a', href=re.compile(r'gid=\d+'))
        if title_link:
            category_name = title_link.get_text(strip=True)
            # 清理名稱中的特殊字元
            category_name = re.sub(r'[\【\】\[\]]', '', category_name).strip()
            href = title_link.get('href', '')
            gid_match = re.search(r'gid=(\d+)', href)
            if gid_match:
                category_gid = f"gid_{gid_match.group(1)}"

        if not category_gid:
            # 嘗試從 category_X id 取得
            content_div = category_block.find('div', id=re.compile(r'category_\d+'))
            if content_div:
                cat_id = content_div.get('id', '')
                match = re.search(r'category_(\d+)', cat_id)
                if match:
                    category_gid = f"gid_{match.group(1)}"

        if not category_gid:
            category_gid = f"cat_{hash(category_name) % 10000}"

        # 找版區內容區 (bm_c)
        content_div = category_block.find('div', class_='bm_c')
        if not content_div:
            return None

        # 解析該分類下的所有版區
        children = self._parse_forums_in_category(content_div, category_gid)

        if children:
            return {
                'fid': category_gid,
                'name': category_name,
                'parent_fid': None,
                'level': 0,
                'children': children
            }

        return None

    def _parse_forums_in_category(self, content_div, parent_gid: str) -> List[Dict]:
        """解析分類內的版區列表

        HTML 結構分析:
        - 所有版區都在一個 <div class="row py-1 cat-box"> 內
        - 每個版區由 <div class="forum-icon"> 開始
        - 版區資訊在後續的 <div class="col-xl-4"> 內
        - 子版區在 <p class="mb-0"> 內用 ├─ 標示
        """
        forums = []

        # 找所有 forum-icon div，每個代表一個版區
        forum_icons = content_div.find_all('div', class_=re.compile(r'forum-icon'))

        for icon_div in forum_icons:
            forum_info = self._parse_forum_from_icon(icon_div, parent_gid)
            if forum_info:
                forums.append(forum_info)

        # 如果沒找到 forum-icon，用備用方法
        if not forums:
            forums = self._parse_forum_links_direct(content_div, parent_gid)

        return forums

    def _parse_forum_from_icon(self, icon_div, parent_gid: str) -> Optional[Dict]:
        """從 forum-icon div 開始解析版區資訊"""
        # 找版區連結 (在 icon_div 內或相鄰的 col div 內)
        main_link = icon_div.find('a', href=re.compile(r'mod=forumdisplay.*fid=\d+'))

        # 找到 icon_div 後面的內容區 (col-xl-4)
        info_div = icon_div.find_next_sibling('div', class_=re.compile(r'col-xl-4|col-lg-4'))
        if not info_div:
            # 可能在同層其他地方
            parent = icon_div.parent
            if parent:
                info_div = parent.find('div', class_=re.compile(r'col-xl-4|col-lg-4'))

        if not info_div:
            return None

        # 在資訊區找主版區連結
        main_forum_link = None
        sub_forum_links = []

        for p_tag in info_div.find_all('p', class_='mb-0'):
            p_text = p_tag.get_text()
            p_html = str(p_tag)

            # 檢查是否是子版區區塊 (包含 ├)
            if '├' in p_html:
                # 這是子版區列表
                for link in p_tag.find_all('a', href=re.compile(r'mod=forumdisplay.*fid=\d+')):
                    sub_forum_links.append(link)
            else:
                # 這是主版區
                link = p_tag.find('a', href=re.compile(r'mod=forumdisplay.*fid=\d+'))
                if link and not main_forum_link:
                    main_forum_link = link

        # 如果在 p 標籤內沒找到主連結，用 icon_div 內的連結
        if not main_forum_link:
            main_forum_link = main_link

        if not main_forum_link:
            return None

        # 提取主版區資訊
        href = main_forum_link.get('href', '')
        main_fid = self._extract_fid(href)
        if not main_fid or main_fid in self._visited_fids:
            return None

        self._visited_fids.add(main_fid)

        # 取得版區名稱
        main_name = main_forum_link.get_text(strip=True)
        main_name = self._clean_forum_name(main_name)

        # 解析子版區
        sub_forums = []
        for sub_link in sub_forum_links:
            sub_href = sub_link.get('href', '')
            sub_fid = self._extract_fid(sub_href)
            if sub_fid and sub_fid not in self._visited_fids:
                self._visited_fids.add(sub_fid)
                sub_name = sub_link.get_text(strip=True)
                sub_name = self._clean_forum_name(sub_name)

                sub_forums.append({
                    'fid': sub_fid,
                    'name': sub_name,
                    'parent_fid': main_fid,
                    'level': 2,
                    'children': []
                })

        return {
            'fid': main_fid,
            'name': main_name,
            'parent_fid': parent_gid,
            'level': 1,
            'children': sub_forums
        }

    def _clean_forum_name(self, name: str) -> str:
        """清理版區名稱"""
        # 移除開頭符號
        name = re.sub(r'^[◎○●@◇]\s*', '', name)
        # 移除 (NEW!!)
        name = re.sub(r'\s*\(\s*NEW\s*!*\s*\)\s*$', '', name, flags=re.IGNORECASE)
        # 移除多餘空白
        name = name.strip()
        return name

    def _parse_forum_links_direct(self, content_div, parent_gid: str) -> List[Dict]:
        """直接解析所有版區連結 (備用方法)"""
        forums = []

        for link in content_div.find_all('a', href=re.compile(r'mod=forumdisplay.*fid=\d+')):
            fid = self._extract_fid(link.get('href', ''))
            if fid and fid not in self._visited_fids:
                self._visited_fids.add(fid)
                name = link.get_text(strip=True)
                name = re.sub(r'^[◎○●]\s*', '', name)
                if name and len(name) > 1:
                    forums.append({
                        'fid': fid,
                        'name': name,
                        'parent_fid': parent_gid,
                        'level': 1,
                        'children': []
                    })

        return forums

    def _parse_forum_index_fallback(self, soup) -> List[Dict]:
        """備用解析方法: 直接找所有版區連結"""
        sections = []
        current_category = {
            'fid': 'cat_default',
            'name': '所有版區',
            'parent_fid': None,
            'level': 0,
            'children': []
        }

        for link in soup.find_all('a', href=re.compile(r'mod=forumdisplay.*fid=\d+')):
            fid = self._extract_fid(link.get('href', ''))
            if fid and fid not in self._visited_fids:
                self._visited_fids.add(fid)
                name = link.get_text(strip=True)
                name = re.sub(r'^[◎○●]\s*', '', name)
                if name and len(name) > 1:
                    current_category['children'].append({
                        'fid': fid,
                        'name': name,
                        'parent_fid': 'cat_default',
                        'level': 1,
                        'children': []
                    })

        if current_category['children']:
            sections.append(current_category)

        return sections

    def _extract_fid(self, href: str) -> Optional[str]:
        """從連結中提取 fid"""
        match = re.search(r'fid=(\d+)', href)
        if match:
            return match.group(1)
        return None

    def _flatten_sections(self, sections: List[Dict], result: List[Dict] = None) -> List[Dict]:
        """將樹狀結構扁平化"""
        if result is None:
            result = []

        for section in sections:
            # 複製一份，不含 children
            flat_section = {
                'fid': section['fid'],
                'name': section['name'],
                'parent_fid': section.get('parent_fid'),
                'level': section.get('level', 0),
                'post_count': section.get('post_count')
            }
            result.append(flat_section)

            # 遞迴處理子版區
            if section.get('children'):
                self._flatten_sections(section['children'], result)

        return result


def test_scraper():
    """測試爬取器"""
    from pathlib import Path
    config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"

    client = ForumClient(str(config_path))
    if not client.check_login():
        print("未登入")
        return

    scraper = ForumStructureScraper(client)
    sections = scraper.scrape_all_sections()

    def print_tree(sections, indent=0):
        for s in sections:
            print("  " * indent + f"[{s['fid']}] {s['name']}")
            if s.get('children'):
                print_tree(s['children'], indent + 1)

    print_tree(sections)


def test_local_html():
    """測試本地 HTML 檔案"""
    from pathlib import Path
    import sys

    # 設定輸出編碼
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    html_path = Path(__file__).parent.parent.parent / "docs" / "無限討論區 - Powered by Discuz!.html"
    if not html_path.exists():
        print(f"找不到檔案: {html_path}")
        return

    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # 建立假的 scraper 來測試解析
    class FakeScraper(ForumStructureScraper):
        def __init__(self):
            self._visited_fids = set()
            self.base_url = "https://fastzone.org"

    scraper = FakeScraper()
    sections = scraper._parse_forum_index(html)

    def print_tree(sections, indent=0):
        for s in sections:
            try:
                print("  " * indent + f"[{s['fid']}] {s['name']}")
            except:
                print("  " * indent + f"[{s['fid']}] (name encoding error)")
            if s.get('children'):
                print_tree(s['children'], indent + 1)

    def count_by_level(sections, level_counts=None):
        if level_counts is None:
            level_counts = {}
        for s in sections:
            level = s.get('level', 0)
            level_counts[level] = level_counts.get(level, 0) + 1
            if s.get('children'):
                count_by_level(s['children'], level_counts)
        return level_counts

    print("=== 版區結構 ===")
    print_tree(sections)
    print()
    print(f"=== 統計 ===")
    print(f"主分類數量: {len(sections)}")
    print(f"總版區數量: {scraper._count_sections(sections)}")

    level_counts = count_by_level(sections)
    for level, count in sorted(level_counts.items()):
        level_name = ["主分類", "版區", "子版區", "子子版區"][level] if level < 4 else f"Level {level}"
        print(f"  {level_name}: {count}")


if __name__ == '__main__':
    test_local_html()
