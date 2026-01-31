import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

from ..utils.logger import logger


class LinkExtractor:
    """下載連結提取器"""

    # 支援的檔案主機連結正則
    LINK_PATTERNS = [
        # Google Drive (GD)
        (r'https?://drive\.google\.com/file/d/[A-Za-z0-9_-]+(?:/[^\s<>"\']*)?', 'GoogleDrive'),
        (r'https?://drive\.google\.com/open\?id=[A-Za-z0-9_-]+', 'GoogleDrive'),
        (r'https?://drive\.google\.com/uc\?[^\s<>"\']+', 'GoogleDrive'),
        (r'https?://drive\.google\.com/drive/folders/[A-Za-z0-9_-]+', 'GoogleDrive'),

        # MEGA
        (r'https?://mega\.nz/(?:file|folder)/[A-Za-z0-9_-]+(?:#[A-Za-z0-9_-]+)?', 'MEGA'),
        (r'https?://mega\.co\.nz/[^\s<>"\']+', 'MEGA'),

        # Gofile
        (r'https?://gofile\.io/d/[A-Za-z0-9]+', 'Gofile'),

        # Transfer.sh / Transfer.it
        (r'https?://transfer\.sh/[^\s<>"\']+', 'Transfer'),
        (r'https?://transfer\.it/[^\s<>"\']+', 'Transfer'),

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

    # 密碼提取正則 - 只提取明確的密碼格式
    PASSWORD_PATTERNS = [
        # FastZone 格式密碼 (最常見)
        r'(FAST[A-Za-z0-9]{8,}_by_FastZone\.ORG)',
        # 其他站點格式密碼
        r'([A-Za-z0-9_]+_by_(?:OKFUN|MEGAFUNPRO|FCBZONE|21AV)\.(?:ORG|COM|NET))',
        # s數字_by_FastZone.ORG 格式
        r'(s\d+_by_FastZone\.ORG)',
    ]

    # 有明確密碼標記的模式 (密碼:xxx, PW:xxx 等)
    PASSWORD_LABELED_PATTERNS = [
        r'(?:解[壓压])?密[碼码]\s*[：:=]\s*([A-Za-z0-9@#$%^&*()_+=\-\.]{4,60})',
        r'[Pp]ass(?:word)?\s*[：:=]\s*([A-Za-z0-9@#$%^&*()_+=\-\.]{4,60})',
        r'PW\s*[：:=]\s*([A-Za-z0-9@#$%^&*()_+=\-\.]{4,60})',
    ]

    # 隱藏內容標記 - 用於上下文提取
    HIDDEN_CONTENT_MARKERS = [
        r'隱藏限制通過',
        r'超過\s*\d+\s*日期限',
        r'感謝您對作者的支持',
        r'嚴禁公開隱藏內容',
        r'隱藏內容已顯示',
    ]

    # 下載方式標記
    DOWNLOAD_SECTION_MARKERS = [
        r'【下載方式】',
        r'【下载方式】',
        r'\[下載方式\]',
        r'\[下载方式\]',
        r'下載方式[：:]',
        r'下载方式[：:]',
        r'下載連結[：:]',
        r'下载链接[：:]',
        r'Download[：:]',
    ]

    # 通用 URL 提取正則 (用於上下文提取)
    GENERIC_URL_PATTERN = r'https?://[^\s<>"\'）\)】\]]+[A-Za-z0-9/]'

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
        # 也取得以換行分隔的純文字版本，保留行結構
        full_text_lines = '\n'.join(area.get_text(separator='\n') for area in content_areas)

        # 檢查是否還有隱藏內容標記
        if '需要感謝' in full_text or '隱藏內容' in full_text or '感謝後才能看' in full_text:
            logger.debug("頁面仍顯示需要感謝才能看的提示")

        # 階段 1: 使用標準正則提取連結
        links = self._extract_links(full_html)

        # 階段 2: 如果沒找到連結，嘗試上下文提取（隱藏內容標記後的下載區塊）
        if not links:
            logger.debug("標準提取未找到連結，嘗試上下文提取...")
            links = self._extract_links_by_context(full_text_lines, full_html)

        # 密碼提取：優先檢查「密碼:」或「【解壓密碼】」後換行的格式
        password = None

        # 移除全形空格後檢查是否有密碼標記
        text_no_space = re.sub(r'[\u3000]+', '', full_text_lines)
        # 支援【解壓密碼】、【解壓密碼】：、【密碼】、密碼: 等格式
        if re.search(r'(?:^|\n)\s*(?:【(?:解[壓压])?密[碼码]】[：:]?|密[碼码]\s*[：:])\s*(?:\n|$)', text_no_space):
            logger.debug("偵測到密碼標記換行格式，使用上下文提取...")
            password = self._extract_password_by_context(full_text_lines)

        # 如果上下文提取沒找到，使用標準正則提取
        if not password:
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
        """提取所有下載連結 - 優先從 <a href> 屬性提取"""
        links = []
        seen_urls = set()
        href_domains = set()  # 記錄從 href 提取到的連結域名

        # 階段 1: 從 <a href="..."> 屬性提取連結 (最可靠)
        href_pattern = r'<a[^>]+href=["\']([^"\']+)["\']'
        href_matches = re.findall(href_pattern, html, re.IGNORECASE)

        for href in href_matches:
            href = self._clean_url(href)
            if not href or href in seen_urls:
                continue

            # 判斷連結類型
            link_type = self._detect_link_type(href)
            if link_type:
                seen_urls.add(href)
                # 記錄已處理的域名
                href_domains.add(link_type)
                links.append({'url': href, 'type': link_type})
                logger.debug(f"從 href 提取連結: {href} ({link_type})")

        # 階段 2: 用正則模式從 HTML 內容提取 (備用)
        # 跳過已經從 href 找到連結的域名類型
        for pattern, link_type in self.LINK_PATTERNS:
            # 如果這個類型已經從 href 提取過，跳過 (避免重複/截斷連結)
            if link_type in href_domains:
                continue

            matches = re.findall(pattern, html, re.IGNORECASE)
            for url in matches:
                url = self._clean_url(url)
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    links.append({
                        'url': url,
                        'type': link_type
                    })
                    logger.debug(f"從內容提取連結: {url} ({link_type})")

        return links

    def _extract_links_by_context(self, text: str, html: str) -> List[Dict]:
        """
        透過上下文標記提取連結（備用方法）
        尋找隱藏內容標記和下載方式標記後的連結
        """
        links = []
        seen_urls = set()

        # 階段 1: 優先從 HTML 的 <a href> 屬性提取
        href_pattern = r'<a[^>]+href=["\']([^"\']+)["\']'
        href_matches = re.findall(href_pattern, html, re.IGNORECASE)

        for href in href_matches:
            href = self._clean_url(href)
            if not href or href in seen_urls:
                continue
            link_type = self._detect_link_type(href)
            if link_type:
                seen_urls.add(href)
                links.append({'url': href, 'type': link_type})
                logger.debug(f"上下文從 href 提取連結: {href} ({link_type})")

        # 如果已經找到連結，直接返回
        if links:
            return links

        # 階段 2: 從文字內容按上下文提取
        lines = text.split('\n')
        in_download_section = False
        found_hidden_marker = False

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # 檢查隱藏內容標記
            for marker in self.HIDDEN_CONTENT_MARKERS:
                if re.search(marker, line_stripped):
                    found_hidden_marker = True
                    break

            # 檢查下載方式標記
            for marker in self.DOWNLOAD_SECTION_MARKERS:
                if re.search(marker, line_stripped, re.IGNORECASE):
                    in_download_section = True
                    logger.debug(f"找到下載區塊標記: {line_stripped[:50]}")
                    break

            # 如果在下載區塊內或剛找到隱藏標記，尋找連結
            if in_download_section or found_hidden_marker:
                # 先嘗試用已知模式提取
                for pattern, link_type in self.LINK_PATTERNS:
                    matches = re.findall(pattern, line_stripped, re.IGNORECASE)
                    for url in matches:
                        url = self._clean_url(url)
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            links.append({'url': url, 'type': link_type})
                            logger.debug(f"上下文提取連結: {url}")

                # 如果還沒找到，用通用 URL 模式
                if not links:
                    generic_matches = re.findall(self.GENERIC_URL_PATTERN, line_stripped, re.IGNORECASE)
                    for url in generic_matches:
                        url = self._clean_url(url)
                        if url and url not in seen_urls:
                            link_type = self._detect_link_type(url)
                            if link_type:
                                seen_urls.add(url)
                                links.append({'url': url, 'type': link_type})
                                logger.debug(f"通用模式提取連結: {url} ({link_type})")

            # 如果找到連結了且遇到空行或新區塊，重置狀態
            if links and (not line_stripped or '【' in line_stripped):
                in_download_section = False

            # 重置隱藏標記（只對下一行有效）
            if found_hidden_marker and i > 0:
                found_hidden_marker = False

        # 也嘗試從 HTML 中用通用模式提取
        if not links:
            generic_matches = re.findall(self.GENERIC_URL_PATTERN, html, re.IGNORECASE)
            for url in generic_matches:
                url = self._clean_url(url)
                if url and url not in seen_urls:
                    link_type = self._detect_link_type(url)
                    if link_type:
                        seen_urls.add(url)
                        links.append({'url': url, 'type': link_type})

        return links

    def _detect_link_type(self, url: str) -> Optional[str]:
        """從 URL 判斷連結類型"""
        url_lower = url.lower()
        if 'drive.google.com' in url_lower:
            return 'GoogleDrive'
        elif 'mega.nz' in url_lower or 'mega.co.nz' in url_lower:
            return 'MEGA'
        elif 'gofile.io' in url_lower:
            return 'Gofile'
        elif 'transfer.sh' in url_lower or 'transfer.it' in url_lower:
            return 'Transfer'
        elif 'katfile.com' in url_lower:
            return 'Katfile'
        elif 'rosefile.net' in url_lower:
            return 'Rosefile'
        elif 'rapidgator.net' in url_lower:
            return 'Rapidgator'
        elif '1fichier.com' in url_lower:
            return '1fichier'
        elif 'uploaded.net' in url_lower:
            return 'Uploaded'
        elif 'mediafire.com' in url_lower:
            return 'Mediafire'
        return None

    def _extract_password_by_context(self, text: str) -> Optional[str]:
        """
        透過上下文標記提取密碼（備用方法）
        在 PW/密碼/解壓密碼 標記後尋找密碼
        整行內容就是密碼（不分割）
        """
        lines = text.split('\n')
        found_pw_marker = False

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            # 移除全形空格來比對標記
            line_no_space = re.sub(r'[\s\u3000]+', '', line_stripped)

            # 檢查密碼標記 - 支援多種格式（移除空格後比對）
            # 【解壓密碼】、【解壓密碼】：、【密碼】、密碼:、PW:、Password: 等
            if re.search(r'(?:【(?:解[壓压])?密[碼码]】[：:]?|(?:^|\s)(?:PW|[Pp]ass(?:word)?|密[碼码]|解[壓压]密[碼码])\s*[：:=]?)\s*$', line_no_space):
                found_pw_marker = True
                continue

            # 如果找到密碼標記，開始尋找密碼
            if found_pw_marker:
                # 跳過空行，繼續找下一行
                if not line_stripped:
                    continue

                # 跳過 URL
                if 'http' in line_stripped.lower():
                    continue

                # 跳過隱藏內容提示行
                if '隱藏限制通過' in line_stripped or '嚴禁公開隱藏內容' in line_stripped:
                    continue

                # 跳過方括號包圍的提示文字
                if line_stripped.startswith('[') and line_stripped.endswith(']'):
                    continue

                # 清理密碼
                potential_pwd = line_stripped.strip()

                # 移除開頭的編號 (01. 02. 等)
                potential_pwd = re.sub(r'^\d+\.\s*', '', potential_pwd)

                # 移除常見後綴
                for suffix in ['歡迎大家下載', '欢迎大家下载', '複製代碼', '复制代码']:
                    if potential_pwd.endswith(suffix):
                        potential_pwd = potential_pwd[:-len(suffix)].strip()

                # 檢查是否包含 _by_ 或常見密碼站點格式（整行就是密碼）
                if '_by_' in potential_pwd or re.search(r'_(?:FastZone|FCBZONE|FDZone|OKFUN)\.', potential_pwd, re.IGNORECASE):
                    logger.debug(f"上下文提取密碼: {potential_pwd}")
                    return potential_pwd

                # 找到非密碼內容，停止搜尋
                found_pw_marker = False

        return None

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
        """
        提取解壓密碼 (嚴格模式，每篇帖子最多 4 個密碼)

        只接受以下格式：
        1. FastZone 格式: FAST...._by_FastZone.ORG
        2. 其他站點格式: xxx_by_OKFUN.ORG 等
        3. 有明確標記的密碼: 密碼:xxx, PW:xxx
        """
        passwords = []
        MAX_PASSWORDS = 4  # 一篇帖子最多 4 個密碼

        # 擴展黑名單：這些絕對不是密碼
        blacklist = {
            # 網域名稱
            'http', 'https', 'www', 'com', 'org', 'net', 'html', 'htm', 'php',
            'mega.nz', 'gofile.io', 'transfer.it', 'transfer.sh', 'katfile.com',
            'rapidgator.net', 'mediafire.com', 'drive.google.com', '1fichier.com',
            'mega', 'gofile', 'transfer', 'katfile', 'rapidgator', 'mediafire',
            # 檔案相關
            'rar', 'zip', '7z', 'part', 'file', 'download', 'avi', 'mp4', 'mkv', 'wmv',
            # 常見詞
            'copy', 'code', 'chrome', 'google', 'http', 'https',
            # 中文
            '複製', '代碼', '代码', '下載', '下载', '連結', '链接',
        }

        def is_valid_password(pwd: str) -> bool:
            """嚴格檢查是否為有效的密碼"""
            if not pwd or len(pwd) < 8 or len(pwd) > 80:
                return False
            pwd_lower = pwd.lower()

            # 檢查是否在黑名單中
            if pwd_lower in blacklist:
                return False

            # 檢查是否包含黑名單詞（作為子字串）
            for blocked in blacklist:
                if blocked in pwd_lower and '_by_' not in pwd_lower:
                    return False

            # 檢查是否為網域名稱格式 (xxx.xx)
            if re.match(r'^[a-z0-9]+\.[a-z]{2,4}$', pwd_lower):
                return False

            # 檢查是否為 URL
            if pwd_lower.startswith(('http://', 'https://', 'www.')):
                return False

            # 必須包含字母和數字的組合（純數字或純字母通常不是密碼）
            has_letter = any(c.isalpha() for c in pwd)
            has_digit = any(c.isdigit() for c in pwd)
            if not (has_letter and has_digit):
                # 除非是 _by_ 格式
                if '_by_' not in pwd:
                    return False

            return True

        def clean_password(pwd: str) -> str:
            """清理密碼"""
            pwd = pwd.strip()
            # 移除常見的後綴文字
            pwd = pwd.rstrip('.,;:!?\'"')
            # 移除中文後綴
            suffixes = ['複製代碼', '复制代码', 'Copy', 'copy', '複製', '代碼', '歡迎大家下載', '欢迎大家下载']
            for suffix in suffixes:
                if pwd.endswith(suffix):
                    pwd = pwd[:-len(suffix)].strip()
            return pwd.strip()

        def add_password(pwd: str) -> bool:
            """添加密碼到列表"""
            pwd = clean_password(pwd)
            if is_valid_password(pwd) and pwd not in passwords:
                passwords.append(pwd)
                logger.debug(f"找到有效密碼: {pwd}")
            return len(passwords) >= MAX_PASSWORDS

        # ===== 階段 1: 尋找 FastZone/_by_ 格式的密碼 (最可靠) =====
        for pattern in self.PASSWORD_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                pwd = match if isinstance(match, str) else match[0]
                if add_password(pwd):
                    break
            if len(passwords) >= MAX_PASSWORDS:
                break

        # ===== 階段 2: 尋找有明確標記的密碼 =====
        if len(passwords) < MAX_PASSWORDS:
            for pattern in self.PASSWORD_LABELED_PATTERNS:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    pwd = match if isinstance(match, str) else match[0]
                    if add_password(pwd):
                        break
                if len(passwords) >= MAX_PASSWORDS:
                    break

        # ===== 階段 3: 處理隱藏內容標記後的密碼 =====
        # 格式: 解壓密碼: → [隱藏內容提示] → 實際密碼
        if len(passwords) < MAX_PASSWORDS:
            lines = text.split('\n')
            for i, line in enumerate(lines):
                # 找到密碼標籤行
                if re.search(r'(?:解[壓压])?密[碼码]\s*[：:]', line, re.IGNORECASE):
                    # 從下一行開始找密碼
                    for j in range(i + 1, min(i + 5, len(lines))):  # 最多看後面 4 行
                        next_line = lines[j].strip()
                        if not next_line:
                            continue
                        # 跳過隱藏內容標記行
                        is_marker = False
                        for marker in self.HIDDEN_CONTENT_MARKERS:
                            if re.search(marker, next_line):
                                is_marker = True
                                break
                        if is_marker:
                            continue
                        # 跳過明顯不是密碼的行（太長或包含中文說明）
                        if len(next_line) > 80 or re.search(r'[，。！？、]', next_line):
                            continue
                        # 嘗試提取這行作為密碼
                        # 移除可能的括號
                        potential_pwd = re.sub(r'^[\[\(【\[]+|[\]\)】\]]+$', '', next_line).strip()
                        if potential_pwd and is_valid_password(potential_pwd):
                            if add_password(potential_pwd):
                                break
                        break  # 只檢查第一個非標記行
                if len(passwords) >= MAX_PASSWORDS:
                    break

        # 返回密碼（用 | 分隔）或 None
        if passwords:
            logger.debug(f"提取到 {len(passwords)} 個密碼: {passwords}")
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
