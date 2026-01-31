import time
import re
from typing import Optional, Dict
from bs4 import BeautifulSoup

from .forum_client import ForumClient
from ..utils.logger import logger


class ThanksHandler:
    """感謝按鈕處理器"""

    def __init__(self, client: ForumClient):
        self.client = client
        self.base_url = client.base_url

    def send_thanks(self, thread_id: str) -> bool:
        """
        發送感謝請求

        重要流程 (兩步驟):
        1. 先訪問帖子頁面 (建立 viewid cookie，這是論壇驗證的關鍵)
        2. 發送第一個 GET 請求，獲取確認彈窗 (感謝作者 V3.0)
        3. 發送第二個 POST 請求，提交感謝 (點擊「確定」按鈕)
        """
        try:
            # 步驟 1: 先訪問帖子頁面 (建立 viewid cookie)
            # 這是關鍵！論壇會檢查 cookie 中的 viewid 是否對應當前帖子
            logger.debug(f"訪問帖子頁面建立 session: tid={thread_id}")
            page_url = f"{self.base_url}/forum.php?mod=viewthread&tid={thread_id}"

            page_resp = self.client.session.get(page_url, timeout=15)

            if page_resp.status_code != 200:
                logger.error(f"無法訪問帖子頁面: tid={thread_id}, status={page_resp.status_code}")
                return False

            # 檢查是否已經感謝過
            # 方法1: 頁面上有明確標記
            if '已感謝' in page_resp.text or '您已經感謝過' in page_resp.text:
                logger.info(f"已經感謝過 (標記): tid={thread_id}")
                return True

            # 方法2: 原文中已有實際的下載連結或解壓密碼
            if self.check_already_thanked(page_resp.text):
                logger.info(f"已經感謝過 (有載點): tid={thread_id}")
                return True

            # 從頁面提取 formhash (需要用於 POST 請求)
            formhash = self._extract_formhash(page_resp.text)
            logger.debug(f"取得 formhash: {formhash}")

            headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': page_url,
                'Accept': '*/*',
            }

            # 步驟 2: 發送第一個 GET 請求 - 獲取確認彈窗
            thanks_get_url = (
                f"{self.base_url}/plugin.php"
                f"?id=thanks:ajax"
                f"&op=thanks"
                f"&tid={thread_id}"
                f"&infloat=yes"
                f"&handlekey=thanks"
                f"&inajax=1"
                f"&ajaxtarget=fwin_content_thanks"
            )

            resp = self.client.session.get(thanks_get_url, headers=headers, timeout=10)

            if resp.status_code != 200:
                logger.error(f"感謝請求 (GET) 失敗: tid={thread_id}, status={resp.status_code}")
                return False

            logger.debug(f"感謝 GET 回應: {resp.text[:300]}")

            # 檢查是否已經感謝過
            if '已經' in resp.text or '已感謝' in resp.text or 'already' in resp.text.lower():
                logger.info(f"已經感謝過: tid={thread_id}")
                return True

            # 檢查是否顯示了確認彈窗 (感謝作者 V3.0)
            if '感謝作者' in resp.text or '確定' in resp.text or 'thankssubmit' in resp.text:
                logger.debug(f"收到確認彈窗，發送 POST 確認請求")
                time.sleep(0.5)

                # 步驟 3: 發送第二個 POST 請求 - 提交感謝（點擊「確定」按鈕）
                thanks_post_url = (
                    f"{self.base_url}/plugin.php"
                    f"?id=thanks:ajax"
                    f"&op=thanks"
                    f"&thankssubmit=yes"
                    f"&infloat=yes"
                    f"&inajax=1"
                )

                # POST 請求需要帶上 formhash, tid, handlekey 和 rate
                # rate=1 是「+1 感謝」選項，這是必填欄位
                post_data = {
                    'formhash': formhash if formhash else '',
                    'tid': thread_id,
                    'handlekey': 'thanks',
                    'rate': '1',  # 評分數目，1 = +1 感謝
                    'comment': '',  # 感謝留言，可選
                }

                resp2 = self.client.session.post(
                    thanks_post_url,
                    data=post_data,
                    headers=headers,
                    timeout=10
                )

                logger.debug(f"感謝 POST 回應: {resp2.text[:300]}")

                if resp2.status_code == 200:
                    # 檢查回應是否表示成功
                    if self._check_thanks_response(resp2.text):
                        logger.info(f"感謝成功 (POST 確認): tid={thread_id}")
                        return True
                    # 有些成功回應可能不包含明確的成功標記，但也沒有錯誤
                    if 'error' not in resp2.text.lower() and '錯誤' not in resp2.text:
                        logger.info(f"感謝已發送: tid={thread_id}")
                        return True

                logger.warning(f"感謝 POST 可能失敗: tid={thread_id}")
                return False

            # 如果第一次 GET 請求直接成功了（某些情況下可能不需要確認）
            if self._check_thanks_response(resp.text):
                logger.info(f"感謝成功 (直接): tid={thread_id}")
                return True

            logger.warning(f"感謝可能失敗: tid={thread_id}")
            logger.debug(f"回應內容: {resp.text[:500]}")
            return False

        except Exception as e:
            logger.error(f"感謝請求異常: tid={thread_id}, error={e}")
            return False

    def _extract_formhash(self, html: str) -> Optional[str]:
        """從 HTML 中提取 formhash"""
        # 嘗試多種模式
        patterns = [
            r'formhash=([a-f0-9]+)',
            r'name="formhash"\s+value="([a-f0-9]+)"',
            r'name="formhash"\s*value="([a-f0-9]+)"',
            r'"formhash":"([a-f0-9]+)"',
            r'formhash["\s:=]+([a-f0-9]{8})',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _check_thanks_response(self, response_text: str) -> bool:
        """檢查感謝回應是否成功"""
        # Discuz AJAX 成功通常會包含特定文字
        success_indicators = [
            '感謝成功',
            '感谢成功',
            'succeedhandle',
            'succeed',
            '操作成功',
            '已成功',
        ]
        error_indicators = ['error', 'fail', '失敗', '錯誤', '權限']

        text_lower = response_text.lower()

        # 如果有成功指標
        has_success = any(ind.lower() in text_lower for ind in success_indicators)
        has_error = any(ind.lower() in text_lower for ind in error_indicators)

        if has_success and not has_error:
            return True

        # 有些論壇成功時會返回空的成功標記
        if 'succeedhandle' in text_lower:
            return True

        return False

    def get_hidden_content(self, thread_id: str) -> Optional[str]:
        """感謝後重新獲取帖子內容（包含原本隱藏的部分）"""
        html = self.client.get_thread_page(thread_id)
        return html

    def check_needs_thanks(self, html: str) -> bool:
        """檢查帖子是否需要感謝才能看到內容"""
        soup = BeautifulSoup(html, 'lxml')

        # 常見的需要感謝才能看的標記
        thanks_hints = [
            '回復後才能看',
            '回覆後才能看',
            '感謝後才能看',
            '需要感謝',
            '隱藏內容',
            'hide',
            'thank to see',
        ]

        text = soup.get_text().lower()
        return any(hint.lower() in text for hint in thanks_hints)

    def check_already_thanked(self, html: str) -> bool:
        """
        檢查帖子是否已經被感謝過

        判斷依據：必須同時滿足以下條件
        1. 有「隱藏限制通過」或「超過 90 日期限」的提示文字
        2. 有實際的下載連結 (mega.nz, gofile.io 等完整 URL)
        3. 有解壓密碼 (FAST... 格式)

        只有三者都存在，才代表已經感謝過且內容已解鎖
        """
        soup = BeautifulSoup(html, 'lxml')

        # 找到第一個帖子的內容區域 (原文，非回覆)
        first_post = soup.find('td', class_='t_f')
        if not first_post:
            first_post = soup.find('div', class_='t_fsz')
        if not first_post:
            first_post = soup.find('td', id=re.compile(r'^postmessage_'))

        if not first_post:
            return False

        post_text = first_post.get_text()
        post_html = str(first_post)

        # 條件 1: 檢查是否有「隱藏限制通過」或「超過 90 日期限」的提示
        unlock_indicators = [
            r'隱藏限制通過',
            r'隐藏限制通过',
            r'超過\s*\d+\s*日期限',
            r'超过\s*\d+\s*日期限',
            r'感謝您對作者的支持',
            r'感谢您对作者的支持',
        ]

        has_unlock_indicator = False
        for pattern in unlock_indicators:
            if re.search(pattern, post_text):
                has_unlock_indicator = True
                logger.debug(f"發現解鎖提示: {pattern}")
                break

        if not has_unlock_indicator:
            logger.debug("未發現解鎖提示文字，判定未感謝")
            return False

        # 條件 2: 檢查是否有實際的下載連結 (完整 URL)
        download_link_patterns = [
            # Google Drive
            r'https?://drive\.google\.com/file/d/[A-Za-z0-9_-]+',
            r'https?://drive\.google\.com/open\?id=',
            # Transfer.it / Transfer.sh
            r'https?://transfer\.it/[^\s<>"\']+',
            r'https?://transfer\.sh/[^\s<>"\']+',
            # MEGA
            r'https?://mega\.nz/(?:file|folder)/[A-Za-z0-9_-]+',
            r'https?://mega\.co\.nz/',
            # Other hosts
            r'https?://gofile\.io/d/[A-Za-z0-9]+',
            r'https?://katfile\.com/[A-Za-z0-9]+',
            r'https?://rapidgator\.net/file/',
            r'https?://uploaded\.net/file/',
            r'https?://rosefile\.net/[A-Za-z0-9]+',
            r'https?://1fichier\.com/\?[A-Za-z0-9]+',
            r'https?://(?:www\.)?mediafire\.com/',
        ]

        has_download_link = False
        for pattern in download_link_patterns:
            if re.search(pattern, post_html, re.IGNORECASE):
                has_download_link = True
                logger.debug(f"發現下載連結: {pattern}")
                break

        if not has_download_link:
            logger.debug("未發現有效下載連結，判定未感謝")
            return False

        # 條件 3: 檢查是否有解壓密碼
        password_patterns = [
            r'FAST[A-Za-z0-9]{8,}_by_FastZone\.ORG',
            r'[A-Za-z0-9_]+_by_(?:OKFUN|MEGAFUNPRO|FCBZONE|21AV)\.(?:ORG|COM|NET)',
            r's\d+_by_FastZone\.ORG',  # s13943013_by_FastZone.ORG 格式
        ]

        has_password = False
        for pattern in password_patterns:
            if re.search(pattern, post_text):
                has_password = True
                logger.debug(f"發現解壓密碼: {pattern}")
                break

        if not has_password:
            logger.debug("未發現解壓密碼，判定未感謝")
            return False

        # 三個條件都滿足，才判定為已感謝
        logger.debug("同時發現解鎖提示、下載連結、解壓密碼，判定已感謝")
        return True
