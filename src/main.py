#!/usr/bin/env python3
"""
DLP01 - 論壇自動下載程式
自動爬取 fastzone.org 論壇，篩選帖子並透過 JDownloader 下載
"""

import argparse
import time
import sys
from pathlib import Path
from typing import List, Dict

import yaml

# 加入專案路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crawler.forum_client import ForumClient
from src.crawler.post_parser import PostParser
from src.crawler.thanks_handler import ThanksHandler
from src.downloader.link_extractor import LinkExtractor
from src.downloader.jd_integration import JDownloaderIntegration
from src.downloader.clipboard_sender import ClipboardSender
from src.downloader.smg_integration import SMGIntegration, extract_smg_code
from src.database.db_manager import DatabaseManager
from src.utils.logger import logger
from src.utils.paths import get_config_dir
from src.utils.profile_manager import ProfileManager


def expand_keywords(base_keywords: list) -> list:
    """將基礎關鍵字展開為 4 種匹配變體

    例如: ['mg'] -> ['@mg', '@ mg', 'mg@', 'mg @']
    """
    expanded = []
    for kw in base_keywords:
        kw = kw.strip()
        if not kw:
            continue
        expanded.extend([
            f'@{kw}',
            f'@ {kw}',
            f'{kw}@',
            f'{kw} @',
        ])
    return expanded


class DLP01:
    """主程式類別"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            # 使用 profile manager 取得目前設定檔路徑
            profile_mgr = ProfileManager()
            config_path = profile_mgr.get_profile_config_path()

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        # 初始化元件
        self.client = ForumClient(config_path)

        # 關鍵字設定 — 讀取基礎關鍵字並展開為匹配變體
        base_title = self.config['forum'].get('title_filters', [])
        base_web = self.config['forum'].get('web_download_keywords', [])
        base_smg = self.config['forum'].get('smg_keywords', [])

        self.web_download_keywords = expand_keywords(base_web)
        self.smg_keywords = expand_keywords(base_smg)
        title_filters = expand_keywords(base_title)

        # 合併額外關鍵字 (網頁下載 + SMG)
        extra_keywords = list(self.web_download_keywords) + list(self.smg_keywords)

        max_posts = self.config['scraper'].get('posts_per_section', 15)
        self.parser = PostParser(
            title_filters,
            max_posts=max_posts,
            extra_keywords=extra_keywords if extra_keywords else None
        )
        self.thanks = ThanksHandler(self.client)
        self.extractor = LinkExtractor()
        self.jd = JDownloaderIntegration(
            folderwatch_path=self.config['jdownloader'].get('folderwatch_path'),
            download_dir=self.config['paths']['download_dir']
        )
        self.clipboard = ClipboardSender(
            download_dir=self.config['paths']['download_dir']
        )
        self.db = DatabaseManager()

        # SMG 整合
        smg_config = self.config.get('smg', {})
        self.smg = SMGIntegration(
            exe_path=smg_config.get('exe_path'),
            download_dir=smg_config.get('download_dir') or self.config['paths']['download_dir']
        )

        # 發送方式: 'folderwatch' 或 'clipboard'
        self.send_method = 'folderwatch'  # 使用 folderwatch

        # 檔案大小限制 (從設定檔讀取，預設 2048 MB)
        self.size_limit_mb = self.config.get('scraper', {}).get('max_file_size_mb', 2048)

        # 停止旗標 (用於外部中斷)
        self._stop_requested = False

        # 重新下載已感謝帖子選項
        self.re_download_thanked = self.config.get('crawler', {}).get('re_download_thanked', False)

        # 統計
        self.stats = {
            'posts_found': 0,
            'posts_new': 0,
            'thanks_sent': 0,
            'links_extracted': 0,
            'repeated_downloads': 0,
            'web_downloads': 0,
            'smg_downloads': 0
        }


    def request_stop(self):
        """請求停止執行"""
        self._stop_requested = True
        logger.info("收到停止請求，正在中斷...")

    def _check_stop(self) -> bool:
        """檢查是否需要停止"""
        return self._stop_requested

    def _get_download_type(self, title: str) -> str:
        """
        根據標題判斷下載類型

        Returns:
            'smg': 使用 SMG 下載
            'web': 記錄到網頁下載表格
            'jd': 使用 JDownloader (預設)
        """
        title_lower = title.lower()

        # 檢查 SMG 關鍵字
        for keyword in self.smg_keywords:
            if keyword.lower() in title_lower:
                return 'smg', keyword

        # 檢查網頁下載關鍵字
        for keyword in self.web_download_keywords:
            if keyword.lower() in title_lower:
                return 'web', keyword

        return 'jd', None

    def run(self, dry_run: bool = False):
        """執行主流程"""
        self._stop_requested = False  # 重置停止旗標

        logger.info("=" * 50)
        logger.info("DLP01 開始執行")
        logger.info("=" * 50)

        # 顯示篩選關鍵字
        if self.web_download_keywords:
            logger.info(f"網頁下載關鍵字: {', '.join(self.web_download_keywords)}")
        if self.smg_keywords:
            logger.info(f"SMG 關鍵字: {', '.join(self.smg_keywords)}")

        # 如果有設定 SMG 關鍵字，驗證 SMG 路徑
        if self.smg_keywords:
            valid, error_msg = self.smg.validate_path()
            if not valid:
                logger.error(f"SMG 路徑驗證失敗: {error_msg}")
                logger.error("請至設定檢查 SMG 程式路徑，或移除 SMG 關鍵字")
                return

            # 確保 SMG 已啟動
            if not dry_run and not self.smg.ensure_running():
                logger.error("無法啟動 SMG，中止執行")
                return

        # 檢查登入狀態
        if not self.client.check_login():
            logger.error("未登入，請檢查 cookies.json")
            return

        # 開始執行紀錄
        run_id = self.db.start_run()

        try:
            # 爬取每個版區
            for section in self.config['forum']['target_sections']:
                if self._check_stop():
                    logger.info("使用者中斷，停止處理")
                    break
                self._process_section(section, dry_run)

            # 處理尚未感謝的帖子
            if not self._check_stop():
                self._process_unthanked_posts(dry_run)

            # 決定完成狀態
            status = 'stopped' if self._check_stop() else 'completed'

            # 等待 JDownloader 處理 crawljob 並清空 folderwatch
            if self.stats['links_extracted'] > 0 and not dry_run:
                logger.info("等待 JDownloader 處理 crawljob...")
                self.jd.wait_for_jd_pickup(timeout=15)

            # 完成
            self.db.end_run(
                run_id,
                self.stats['posts_found'],
                self.stats['posts_new'],
                self.stats['thanks_sent'],
                self.stats['links_extracted'],
                status
            )

        except Exception as e:
            logger.error(f"執行失敗: {e}")
            self.db.end_run(run_id, 0, 0, 0, 0, 'failed')
            raise

        self._print_summary()

    def _process_section(self, section: Dict, dry_run: bool):
        """處理單個版區"""
        if self._check_stop():
            return

        fid = section['fid']
        name = section['name']
        pages = self.config['scraper']['pages_per_section']

        logger.info(f"\n處理版區: {name} (fid={fid})")

        for page in range(1, pages + 1):
            if self._check_stop():
                return

            logger.info(f"  頁面 {page}/{pages}")

            html = self.client.get_forum_page(fid, page)
            if not html:
                continue

            posts = self.parser.parse_forum_list(html, name)
            self.stats['posts_found'] += len(posts)

            for post in posts:
                if self._check_stop():
                    return
                self._process_post(post, dry_run)

    def _process_post(self, post: Dict, dry_run: bool):
        """處理單個帖子"""
        thread_id = post['thread_id']
        is_redownload = False

        # 檢查是否已處理過（已下載或已感謝）
        is_downloaded = self.db.is_downloaded(thread_id)
        is_thanked = self.db.has_thanked(thread_id)

        if is_downloaded or is_thanked:
            # 如果啟用重新下載已感謝帖子
            if self.re_download_thanked:
                is_redownload = True
                download_count = self.db.get_download_count(thread_id)
                logger.info(f"  [重新下載] {post['title'][:40]}... (第 {download_count + 1} 次)")
                self.stats['repeated_downloads'] += 1
            else:
                skip_reason = "已下載" if is_downloaded else "已感謝"
                logger.debug(f"  跳過{skip_reason}: {post['title'][:30]}...")
                return

        # 檢查檔案大小
        file_size_mb = post.get('file_size_mb', 0)
        size_limit = getattr(self, 'size_limit_mb', 2048)
        if file_size_mb > size_limit:
            return

        if not is_redownload:
            logger.info(f"  新帖子: {post['title'][:50]}...")
            self.stats['posts_new'] += 1

        # 儲存到資料庫
        post_id = self.db.add_post(
            thread_id=thread_id,
            title=post['title'],
            author=post['author'],
            forum_section=post['forum_section'],
            post_url=post['post_url'],
            host_type=post['host_type']
        )

        if dry_run:
            logger.info(f"    [DRY-RUN] 會發送感謝並提取連結")
            return

        # 發送感謝
        delay = self.config['scraper']['delay_between_thanks']
        time.sleep(delay)

        success = self.thanks.send_thanks(thread_id)
        self.db.mark_thanked(thread_id, success)

        if success:
            self.stats['thanks_sent'] += 1

        # 無論感謝是否成功，都嘗試提取連結
        # (因為帖子可能之前已被感謝過，內容已經可見)
        links_found = False
        max_retries = 3
        wait_times = [3, 5, 8]  # 每次重試等待時間遞增

        for attempt in range(max_retries):
            wait_time = wait_times[attempt] if attempt < len(wait_times) else 8
            logger.info(f"    等待 {wait_time} 秒後獲取頁面 (嘗試 {attempt + 1}/{max_retries})")
            time.sleep(wait_time)

            html = self.client.get_thread_page(thread_id)
            if html:
                result = self.extractor.extract_from_html(html)
                if result['links']:
                    # 找到連結，進行下載
                    self._extract_and_download(post_id, post['title'], html, result, thread_id,
                                               post_url=post.get('post_url'))
                    links_found = True
                    break
                else:
                    logger.info(f"    第 {attempt + 1} 次嘗試未找到連結，繼續重試...")

        if not links_found:
            logger.warning(f"    {max_retries} 次嘗試後仍未找到下載連結")

    def _process_unthanked_posts(self, dry_run: bool):
        """處理之前未成功感謝的帖子"""
        unthanked = self.db.get_unthanked_posts()
        if not unthanked:
            return

        logger.info(f"\n處理 {len(unthanked)} 個未感謝的帖子")

        for post in unthanked:
            if dry_run:
                logger.info(f"  [DRY-RUN] 會重試: {post['title'][:30]}...")
                continue

            delay = self.config['scraper']['delay_between_thanks']
            time.sleep(delay)

            success = self.thanks.send_thanks(post['thread_id'])
            self.db.mark_thanked(post['thread_id'], success)

            if success:
                self.stats['thanks_sent'] += 1

            # 無論感謝是否成功，都嘗試提取連結
            time.sleep(2)
            html = self.client.get_thread_page(post['thread_id'])
            if html:
                self._extract_and_download(post['id'], post['title'], html,
                                           thread_id=post['thread_id'],
                                           post_url=post.get('post_url'))

    def _extract_and_download(self, post_id: int, title: str, html: str,
                               result: Dict = None, thread_id: str = None,
                               post_url: str = None):
        """提取連結並根據類型分發處理"""
        if result is None:
            result = self.extractor.extract_from_html(html)
        links = result['links']
        password = result['password']
        archive_names = result.get('archive_names', [])

        # 判斷下載類型
        download_type, matched_keyword = self._get_download_type(title)

        # SMG 類型：嘗試提取 SMG 編碼
        if download_type == 'smg':
            smg_code = extract_smg_code(html)
            if smg_code:
                logger.info(f"    [SMG] 找到 SMG 編碼，發送到 SMG 下載器")
                if self.smg.send_download_with_retry(smg_code):
                    self.stats['smg_downloads'] += 1
                    # 記錄 SMG 下載到資料庫
                    self.db.add_smg_download(
                        thread_id=thread_id,
                        title=title,
                        post_url=post_url or '',
                        keyword=matched_keyword or '',
                        smg_code=smg_code,
                        password=password
                    )
                    logger.info(f"    [SMG] 任務已發送並記錄")
                else:
                    logger.error(f"    [SMG] 發送失敗")
                return
            else:
                logger.warning(f"    [SMG] 未找到 SMG 編碼，嘗試一般連結提取")
                # 繼續嘗試一般連結提取

        if not links:
            logger.warning(f"    未找到下載連結")
            return

        logger.info(f"    找到 {len(links)} 個連結")
        if password:
            logger.info(f"    密碼: {password}")
        if archive_names:
            logger.info(f"    壓縮檔: {', '.join(archive_names)}")
        self.stats['links_extracted'] += len(links)

        # 將壓縮檔名稱合併為字串 (用 | 分隔)
        archive_filename = '|'.join(archive_names) if archive_names else None

        # 儲存連結到資料庫
        for link in links:
            download_id = self.db.add_download(
                post_id=post_id,
                link_url=link['url'],
                link_type=link['type'],
                password=password,
                archive_filename=archive_filename
            )
            self.db.mark_sent_to_jd(download_id, title)

        # 網頁下載類型：記錄到 web_downloads 表格
        if download_type == 'web':
            for link in links:
                self.db.add_web_download(
                    thread_id=thread_id or '',
                    title=title,
                    post_url=post_url or f"thread-{thread_id}-1-1.html",
                    keyword=matched_keyword,
                    download_url=link['url'],
                    password=password
                )
            self.stats['web_downloads'] += len(links)
            logger.info(f"    [網頁下載] 已記錄 {len(links)} 個連結到網頁下載表格")
            return

        # JDownloader 類型：發送到 JDownloader
        if self.send_method == 'clipboard':
            # 使用剪貼簿方式
            self.clipboard.send_links(links, title, password)
            logger.info(f"    [剪貼簿] 請確認 JDownloader 已開啟剪貼簿監視器")
        else:
            # 使用 folderwatch 方式
            self.jd.create_crawljob(links, title, password)

        # 記錄下載嘗試（用於追蹤重複下載）
        if thread_id:
            filename = archive_names[0] if archive_names else title
            download_count = self.db.record_download_attempt(thread_id, filename, post_id)
            if download_count > 1:
                logger.info(f"    [重複下載] 這是第 {download_count} 次下載此帖子")

    def _print_summary(self):
        """列印執行摘要"""
        logger.info("\n" + "=" * 50)
        logger.info("執行完成")
        logger.info("=" * 50)
        logger.info(f"找到帖子: {self.stats['posts_found']}")
        logger.info(f"新帖子: {self.stats['posts_new']}")
        logger.info(f"感謝成功: {self.stats['thanks_sent']}")
        logger.info(f"提取連結: {self.stats['links_extracted']}")
        if self.stats['repeated_downloads'] > 0:
            logger.info(f"重複下載: {self.stats['repeated_downloads']}")
        if self.stats['web_downloads'] > 0:
            logger.info(f"網頁下載: {self.stats['web_downloads']}")
        if self.stats['smg_downloads'] > 0:
            logger.info(f"SMG 下載: {self.stats['smg_downloads']}")



def main():
    parser = argparse.ArgumentParser(description='DLP01 - 論壇自動下載程式')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='試執行，不實際發送感謝或下載')
    parser.add_argument('--config', '-c', type=str,
                        help='設定檔路徑')
    parser.add_argument('--schedule', '-s', action='store_true',
                        help='啟用定時執行模式')
    parser.add_argument('--no-size-limit', action='store_true',
                        help='忽略 2GB 檔案大小限制')

    args = parser.parse_args()

    dlp = DLP01(config_path=args.config)

    # 如果忽略大小限制
    if args.no_size_limit:
        dlp.size_limit_mb = float('inf')
    else:
        dlp.size_limit_mb = 2048  # 2GB

    if args.schedule:
        import schedule

        interval = dlp.config['scheduler']['interval_minutes']
        logger.info(f"啟用定時模式，每 {interval} 分鐘執行一次")

        schedule.every(interval).minutes.do(dlp.run, dry_run=args.dry_run)

        # 立即執行一次
        dlp.run(dry_run=args.dry_run)

        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        dlp.run(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
