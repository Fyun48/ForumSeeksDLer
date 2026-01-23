"""
搜尋結果批次下載工作執行緒
處理搜尋結果中選定的帖子：感謝 + 提取連結 + 送 JDownloader
"""
import time
from typing import List, Dict

from PyQt6.QtCore import QThread, pyqtSignal

from ..crawler.forum_client import ForumClient
from ..crawler.thanks_handler import ThanksHandler
from ..downloader.link_extractor import LinkExtractor
from ..downloader.jd_integration import JDownloaderIntegration
from ..database.db_manager import DatabaseManager
from ..utils.logger import logger


class SearchDownloadWorker(QThread):
    """搜尋結果批次下載工作執行緒"""

    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int, str)  # current, total, current_title
    finished_signal = pyqtSignal(dict)  # stats
    error_signal = pyqtSignal(str)

    def __init__(self, selected_posts: List[Dict], config_path: str, config: dict):
        super().__init__()
        self.selected_posts = selected_posts
        self.config_path = config_path
        self.config = config
        self.is_running = True

    def run(self):
        """執行批次下載"""
        stats = {
            'total': len(self.selected_posts),
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'links_extracted': 0
        }

        try:
            # 初始化元件
            client = ForumClient(self.config_path)

            if not client.check_login():
                self.error_signal.emit("未登入，請先設定 Cookie")
                return

            thanks_handler = ThanksHandler(client)
            extractor = LinkExtractor()
            jd = JDownloaderIntegration(
                folderwatch_path=self.config.get('jdownloader', {}).get('folderwatch_path'),
                download_dir=self.config.get('paths', {}).get('download_dir')
            )
            db = DatabaseManager()

            delay_between_thanks = self.config.get('scraper', {}).get('delay_between_thanks', 5)

            # 處理每個帖子
            for i, post in enumerate(self.selected_posts):
                if not self.is_running:
                    self.log_signal.emit("使用者中斷")
                    break

                tid = post.get('tid')
                title = post.get('title', f'TID: {tid}')

                self.progress_signal.emit(i + 1, len(self.selected_posts), title[:50])
                self.log_signal.emit(f"處理 [{i+1}/{len(self.selected_posts)}]: {title[:60]}...")

                # 檢查是否已下載過
                if db.is_downloaded(tid):
                    self.log_signal.emit(f"  跳過已下載: {title[:40]}...")
                    stats['skipped'] += 1
                    continue

                # 發送感謝
                self.log_signal.emit(f"  發送感謝...")
                time.sleep(delay_between_thanks)
                success = thanks_handler.send_thanks(tid)

                if not success:
                    self.log_signal.emit(f"  感謝失敗")
                    stats['failed'] += 1
                    continue

                # 儲存帖子到資料庫
                post_id = db.add_post(
                    thread_id=tid,
                    title=title,
                    author=post.get('author', ''),
                    forum_section=post.get('forum_name', ''),
                    post_url=post.get('post_url', ''),
                    host_type=''
                )
                db.mark_thanked(tid, True)

                # 等待並取得頁面內容
                links_found = False
                max_retries = 3
                wait_times = [3, 5, 8]

                for attempt in range(max_retries):
                    wait_time = wait_times[attempt] if attempt < len(wait_times) else 8
                    self.log_signal.emit(f"  等待 {wait_time} 秒後取得頁面 (嘗試 {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)

                    html = client.get_thread_page(tid)
                    if html:
                        result = extractor.extract_from_html(html)
                        if result['links']:
                            links = result['links']
                            password = result['password']
                            archive_names = result.get('archive_names', [])

                            self.log_signal.emit(f"  找到 {len(links)} 個連結")
                            if password:
                                self.log_signal.emit(f"  密碼: {password}")

                            # 儲存到資料庫
                            archive_filename = '|'.join(archive_names) if archive_names else None
                            for link in links:
                                download_id = db.add_download(
                                    post_id=post_id,
                                    link_url=link['url'],
                                    link_type=link['type'],
                                    password=password,
                                    archive_filename=archive_filename
                                )
                                db.mark_sent_to_jd(download_id, title)

                            # 建立 crawljob 送到 JDownloader
                            jd.create_crawljob(links, title, password)

                            stats['success'] += 1
                            stats['links_extracted'] += len(links)
                            links_found = True
                            break
                        else:
                            self.log_signal.emit(f"  第 {attempt + 1} 次未找到連結")

                if not links_found:
                    self.log_signal.emit(f"  無法提取連結")
                    stats['failed'] += 1

            # 完成
            self.log_signal.emit("")
            self.log_signal.emit("=" * 50)
            self.log_signal.emit("批次下載完成")
            self.log_signal.emit(f"成功: {stats['success']}, 失敗: {stats['failed']}, 跳過: {stats['skipped']}")
            self.log_signal.emit(f"提取連結數: {stats['links_extracted']}")
            self.log_signal.emit("=" * 50)

            self.finished_signal.emit(stats)

        except Exception as e:
            logger.error(f"批次下載失敗: {e}")
            self.error_signal.emit(str(e))

    def stop(self):
        """停止執行"""
        self.is_running = False
