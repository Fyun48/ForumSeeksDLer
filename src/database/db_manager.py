import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


class DatabaseManager:
    """SQLite 資料庫管理器"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "data" / "dlp.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def get_connection(self):
        """取得資料庫連線"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """初始化資料庫結構"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # posts 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    author TEXT,
                    forum_section TEXT,
                    post_url TEXT NOT NULL,
                    host_type TEXT,
                    first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    thanked_at DATETIME,
                    thanks_success BOOLEAN DEFAULT FALSE,
                    content_extracted BOOLEAN DEFAULT FALSE
                )
            ''')

            # downloads 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    link_url TEXT NOT NULL,
                    link_type TEXT,
                    password TEXT,
                    archive_filename TEXT,
                    jd_package_name TEXT,
                    sent_to_jd_at DATETIME,
                    download_status TEXT DEFAULT 'pending',
                    extracted_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (post_id) REFERENCES posts(id)
                )
            ''')

            # run_history 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS run_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    ended_at DATETIME,
                    posts_found INTEGER DEFAULT 0,
                    posts_new INTEGER DEFAULT 0,
                    thanks_sent INTEGER DEFAULT 0,
                    links_extracted INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'running'
                )
            ''')

            # 為現有資料庫增加欄位
            new_columns = [
                ('extract_success', 'BOOLEAN DEFAULT NULL'),
                ('archive_filename', 'TEXT'),
                ('extract_dest_path', 'TEXT'),
                ('files_extracted', 'INTEGER'),
                ('files_skipped', 'INTEGER'),
                ('files_filtered', 'INTEGER'),
                ('archive_size', 'INTEGER'),
                ('extracted_size', 'INTEGER'),
                ('nested_level', 'INTEGER DEFAULT 0'),
                ('parent_download_id', 'INTEGER'),
                ('error_message', 'TEXT'),
                ('download_count', 'INTEGER DEFAULT 1'),
                ('first_download_time', 'DATETIME'),
                ('jd_complete_time', 'DATETIME'),
            ]

            for column_name, column_type in new_columns:
                try:
                    cursor.execute(f'ALTER TABLE downloads ADD COLUMN {column_name} {column_type}')
                except sqlite3.OperationalError:
                    pass  # 欄位已存在

            # download_history 表 - 追蹤每次下載時間
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS download_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tid TEXT NOT NULL,
                    download_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    filename TEXT,
                    post_id INTEGER,
                    FOREIGN KEY (post_id) REFERENCES posts(id)
                )
            ''')

            # forum_sections 表 - 論壇版區結構
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS forum_sections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fid TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    parent_fid TEXT,
                    level INTEGER DEFAULT 0,
                    post_count INTEGER,
                    last_updated DATETIME,
                    FOREIGN KEY (parent_fid) REFERENCES forum_sections(fid)
                )
            ''')

            # search_results 表 - 搜尋結果暫存
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS search_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    tid TEXT NOT NULL,
                    title TEXT NOT NULL,
                    author TEXT,
                    post_date TEXT,
                    fid TEXT,
                    forum_name TEXT,
                    post_url TEXT,
                    selected BOOLEAN DEFAULT FALSE,
                    processed BOOLEAN DEFAULT FALSE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

    def post_exists(self, thread_id: str) -> bool:
        """檢查帖子是否已存在 (只是瀏覽過)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM posts WHERE thread_id = ?', (thread_id,))
            return cursor.fetchone() is not None

    def is_downloaded(self, thread_id: str) -> bool:
        """檢查帖子是否已下載過 (有產生 crawljob 並送到 JDownloader)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 1 FROM posts p
                JOIN downloads d ON p.id = d.post_id
                WHERE p.thread_id = ? AND d.sent_to_jd_at IS NOT NULL
            ''', (thread_id,))
            return cursor.fetchone() is not None

    def add_post(self, thread_id: str, title: str, author: str,
                 forum_section: str, post_url: str, host_type: str = None) -> int:
        """新增帖子，回傳 post_id"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO posts
                (thread_id, title, author, forum_section, post_url, host_type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (thread_id, title, author, forum_section, post_url, host_type))

            if cursor.rowcount == 0:
                cursor.execute('SELECT id FROM posts WHERE thread_id = ?', (thread_id,))
                return cursor.fetchone()[0]
            return cursor.lastrowid

    def mark_thanked(self, thread_id: str, success: bool = True):
        """標記帖子已感謝"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE posts SET thanked_at = ?, thanks_success = ?
                WHERE thread_id = ?
            ''', (datetime.now().isoformat(), success, thread_id))

    def get_unthanked_posts(self) -> List[Dict[str, Any]]:
        """取得尚未感謝的帖子"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM posts WHERE thanked_at IS NULL
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def add_download(self, post_id: int, link_url: str,
                     link_type: str = None, password: str = None,
                     archive_filename: str = None) -> int:
        """新增下載連結"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO downloads (post_id, link_url, link_type, password, archive_filename)
                VALUES (?, ?, ?, ?, ?)
            ''', (post_id, link_url, link_type, password, archive_filename))
            return cursor.lastrowid

    def mark_sent_to_jd(self, download_id: int, package_name: str):
        """標記已送到 JDownloader"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE downloads SET sent_to_jd_at = ?, jd_package_name = ?
                WHERE id = ?
            ''', (datetime.now().isoformat(), package_name, download_id))

    def start_run(self) -> int:
        """開始新的執行紀錄"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO run_history DEFAULT VALUES')
            return cursor.lastrowid

    def end_run(self, run_id: int, posts_found: int, posts_new: int,
                thanks_sent: int, links_extracted: int, status: str = 'completed'):
        """結束執行紀錄"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE run_history SET
                    ended_at = ?, posts_found = ?, posts_new = ?,
                    thanks_sent = ?, links_extracted = ?, status = ?
                WHERE id = ?
            ''', (datetime.now().isoformat(), posts_found, posts_new,
                  thanks_sent, links_extracted, status, run_id))

    def get_all_passwords(self) -> List[str]:
        """取得所有不重複的解壓密碼"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT password FROM downloads
                WHERE password IS NOT NULL AND password != ''
            ''')
            return [row[0] for row in cursor.fetchall()]

    def get_password_for_package(self, package_name: str) -> Optional[str]:
        """根據 JDownloader 套件名稱取得對應的密碼"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # 搜尋包含此套件名稱的記錄
            cursor.execute('''
                SELECT password FROM downloads
                WHERE jd_package_name LIKE ? AND password IS NOT NULL AND password != ''
                LIMIT 1
            ''', (f'%{package_name}%',))
            row = cursor.fetchone()
            return row[0] if row else None

    def get_passwords_with_titles(self) -> List[Dict[str, str]]:
        """取得所有密碼與對應的標題和壓縮檔名稱 (用於匹配檔案名稱)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT d.password, d.jd_package_name, p.title, d.archive_filename
                FROM downloads d
                JOIN posts p ON d.post_id = p.id
                WHERE d.password IS NOT NULL AND d.password != ''
            ''')
            return [{
                'password': row[0],
                'package_name': row[1],
                'title': row[2],
                'archive_filename': row[3]
            } for row in cursor.fetchall()]

    def mark_extracted(self, download_id: int = None, package_name: str = None,
                       success: bool = True):
        """標記下載項目已解壓 (可用 download_id 或 package_name 查找)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            if download_id:
                cursor.execute('''
                    UPDATE downloads SET extracted_at = ?, extract_success = ?
                    WHERE id = ?
                ''', (now, success, download_id))
            elif package_name:
                # 用套件名稱模糊匹配
                cursor.execute('''
                    UPDATE downloads SET extracted_at = ?, extract_success = ?
                    WHERE jd_package_name LIKE ?
                ''', (now, success, f'%{package_name}%'))

    def mark_extracted_by_title(self, title_pattern: str, success: bool = True):
        """根據帖子標題標記解壓狀態"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute('''
                UPDATE downloads SET extracted_at = ?, extract_success = ?
                WHERE post_id IN (
                    SELECT id FROM posts WHERE title LIKE ?
                )
            ''', (now, success, f'%{title_pattern}%'))

    def record_extraction_result(self, archive_name: str, success: bool,
                                  dest_path: str = None, files_extracted: int = 0,
                                  files_skipped: int = 0, files_filtered: int = 0,
                                  archive_size: int = 0, extracted_size: int = 0,
                                  nested_level: int = 0, parent_download_id: int = None,
                                  error_message: str = None, used_password: str = None) -> Optional[int]:
        """
        記錄詳細的解壓結果

        Returns:
            更新的 download_id，如果找不到則回傳 None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            # 清理檔案名稱
            clean_name = archive_name.lower()
            for ext in ['.rar', '.zip', '.7z']:
                if clean_name.endswith(ext):
                    clean_name = clean_name[:-len(ext)]
                    break
            for suffix in ['.part01', '.part1', '.part001']:
                if clean_name.endswith(suffix):
                    clean_name = clean_name[:-len(suffix)]
                    break

            # 嘗試找到對應的 download 記錄
            cursor.execute('''
                SELECT id FROM downloads
                WHERE (jd_package_name LIKE ? OR archive_filename LIKE ?)
                AND extracted_at IS NULL
                ORDER BY created_at DESC
                LIMIT 1
            ''', (f'%{clean_name}%', f'%{clean_name}%'))

            row = cursor.fetchone()
            if row:
                download_id = row[0]
                cursor.execute('''
                    UPDATE downloads SET
                        extracted_at = ?,
                        extract_success = ?,
                        extract_dest_path = ?,
                        files_extracted = ?,
                        files_skipped = ?,
                        files_filtered = ?,
                        archive_size = ?,
                        extracted_size = ?,
                        nested_level = ?,
                        parent_download_id = ?,
                        error_message = ?
                    WHERE id = ?
                ''', (now, success, dest_path, files_extracted, files_skipped,
                      files_filtered, archive_size, extracted_size, nested_level,
                      parent_download_id, error_message, download_id))
                return download_id

            # 如果找不到，嘗試用標題匹配
            cursor.execute('''
                UPDATE downloads SET
                    extracted_at = ?,
                    extract_success = ?,
                    extract_dest_path = ?,
                    files_extracted = ?,
                    files_skipped = ?,
                    files_filtered = ?,
                    archive_size = ?,
                    extracted_size = ?,
                    nested_level = ?,
                    parent_download_id = ?,
                    error_message = ?
                WHERE post_id IN (
                    SELECT id FROM posts WHERE title LIKE ?
                )
                AND extracted_at IS NULL
            ''', (now, success, dest_path, files_extracted, files_skipped,
                  files_filtered, archive_size, extracted_size, nested_level,
                  parent_download_id, error_message, f'%{clean_name}%'))

            if cursor.rowcount > 0:
                cursor.execute('SELECT last_insert_rowid()')
                return cursor.fetchone()[0]

            return None

    def get_extraction_history(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """取得解壓歷史記錄（含詳細資訊）"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    d.id,
                    d.archive_filename,
                    d.jd_package_name,
                    d.password,
                    d.extracted_at,
                    d.extract_success,
                    d.extract_dest_path,
                    d.files_extracted,
                    d.files_skipped,
                    d.files_filtered,
                    d.archive_size,
                    d.extracted_size,
                    d.nested_level,
                    d.parent_download_id,
                    d.error_message,
                    d.created_at,
                    p.title,
                    p.post_url
                FROM downloads d
                LEFT JOIN posts p ON d.post_id = p.id
                WHERE d.extracted_at IS NOT NULL
                ORDER BY d.extracted_at DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset))
            return [dict(row) for row in cursor.fetchall()]

    def get_nested_extractions(self, parent_id: int) -> List[Dict[str, Any]]:
        """取得巢狀解壓記錄"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    d.id,
                    d.archive_filename,
                    d.extracted_at,
                    d.extract_success,
                    d.files_extracted,
                    d.nested_level,
                    d.error_message
                FROM downloads d
                WHERE d.parent_download_id = ?
                ORDER BY d.nested_level, d.extracted_at
            ''', (parent_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_extraction_stats(self) -> Dict[str, Any]:
        """取得解壓統計資訊"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) FROM downloads WHERE extract_success = 1')
            success_count = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM downloads WHERE extract_success = 0')
            failed_count = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM downloads WHERE extracted_at IS NULL AND sent_to_jd_at IS NOT NULL')
            pending_count = cursor.fetchone()[0]

            cursor.execute('SELECT SUM(files_extracted) FROM downloads WHERE extract_success = 1')
            total_files = cursor.fetchone()[0] or 0

            cursor.execute('SELECT SUM(files_skipped) FROM downloads WHERE extract_success = 1')
            total_skipped = cursor.fetchone()[0] or 0

            cursor.execute('SELECT SUM(files_filtered) FROM downloads WHERE extract_success = 1')
            total_filtered = cursor.fetchone()[0] or 0

            cursor.execute('SELECT SUM(archive_size) FROM downloads WHERE extract_success = 1')
            total_archive_size = cursor.fetchone()[0] or 0

            cursor.execute('SELECT SUM(extracted_size) FROM downloads WHERE extract_success = 1')
            total_extracted_size = cursor.fetchone()[0] or 0

            return {
                'success_count': success_count,
                'failed_count': failed_count,
                'pending_count': pending_count,
                'total_files_extracted': total_files,
                'total_files_skipped': total_skipped,
                'total_files_filtered': total_filtered,
                'total_archive_size': total_archive_size,
                'total_extracted_size': total_extracted_size
            }

    def cleanup_old_records(self, retention_days: int) -> Dict[str, int]:
        """清理超過保留天數的舊記錄"""
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 先取得要刪除的 post_ids
            cursor.execute('''
                SELECT id FROM posts WHERE first_seen_at < ?
            ''', (cutoff_date,))
            old_post_ids = [row[0] for row in cursor.fetchall()]

            deleted_downloads = 0
            deleted_posts = 0
            deleted_runs = 0

            if old_post_ids:
                # 刪除相關的 downloads
                placeholders = ','.join('?' * len(old_post_ids))
                cursor.execute(f'''
                    DELETE FROM downloads WHERE post_id IN ({placeholders})
                ''', old_post_ids)
                deleted_downloads = cursor.rowcount

                # 刪除舊的 posts
                cursor.execute(f'''
                    DELETE FROM posts WHERE id IN ({placeholders})
                ''', old_post_ids)
                deleted_posts = cursor.rowcount

            # 刪除舊的執行記錄
            cursor.execute('''
                DELETE FROM run_history WHERE started_at < ?
            ''', (cutoff_date,))
            deleted_runs = cursor.rowcount

            return {
                'deleted_posts': deleted_posts,
                'deleted_downloads': deleted_downloads,
                'deleted_runs': deleted_runs
            }

    def clear_all_records(self) -> Dict[str, int]:
        """清除所有記錄 (一鍵清除)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) FROM downloads')
            downloads_count = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM posts')
            posts_count = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM run_history')
            runs_count = cursor.fetchone()[0]

            cursor.execute('DELETE FROM downloads')
            cursor.execute('DELETE FROM posts')
            cursor.execute('DELETE FROM run_history')

            return {
                'deleted_posts': posts_count,
                'deleted_downloads': downloads_count,
                'deleted_runs': runs_count
            }

    def get_download_history(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """取得下載/解壓歷史記錄"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    d.id,
                    d.link_url,
                    d.link_type,
                    d.password,
                    d.jd_package_name,
                    d.sent_to_jd_at,
                    d.download_status,
                    d.extracted_at,
                    d.extract_success,
                    d.created_at,
                    p.thread_id,
                    p.title,
                    p.author,
                    p.forum_section,
                    p.post_url
                FROM downloads d
                JOIN posts p ON d.post_id = p.id
                ORDER BY d.created_at DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset))
            return [dict(row) for row in cursor.fetchall()]

    def get_download_stats(self) -> Dict[str, int]:
        """取得下載統計資訊"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) FROM posts')
            total_posts = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM downloads')
            total_downloads = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM downloads WHERE sent_to_jd_at IS NOT NULL')
            sent_to_jd = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM downloads WHERE extract_success = 1')
            extract_success = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM downloads WHERE extract_success = 0')
            extract_failed = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM downloads WHERE extracted_at IS NULL AND sent_to_jd_at IS NOT NULL')
            pending_extract = cursor.fetchone()[0]

            return {
                'total_posts': total_posts,
                'total_downloads': total_downloads,
                'sent_to_jd': sent_to_jd,
                'extract_success': extract_success,
                'extract_failed': extract_failed,
                'pending_extract': pending_extract
            }

    # ========== 下載次數追蹤 ==========

    def has_thanked(self, thread_id: str) -> bool:
        """檢查帖子是否已感謝過"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 1 FROM posts WHERE thread_id = ? AND thanks_success = 1
            ''', (thread_id,))
            return cursor.fetchone() is not None

    def record_download_attempt(self, thread_id: str, filename: str, post_id: int = None) -> int:
        """
        記錄下載嘗試，回傳該 TID 的下載次數
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            # 記錄到 download_history
            cursor.execute('''
                INSERT INTO download_history (tid, download_time, filename, post_id)
                VALUES (?, ?, ?, ?)
            ''', (thread_id, now, filename, post_id))

            # 計算該 TID 的下載次數
            cursor.execute('''
                SELECT COUNT(*) FROM download_history WHERE tid = ?
            ''', (thread_id,))
            count = cursor.fetchone()[0]

            return count

    def get_download_count(self, thread_id: str) -> int:
        """取得該 TID 的下載次數"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM download_history WHERE tid = ?
            ''', (thread_id,))
            return cursor.fetchone()[0]

    def get_download_times(self, thread_id: str) -> List[Dict[str, Any]]:
        """取得該 TID 的所有下載時間記錄"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, download_time, filename
                FROM download_history
                WHERE tid = ?
                ORDER BY download_time ASC
            ''', (thread_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_repeated_downloads(self, min_count: int = 2) -> List[Dict[str, Any]]:
        """取得下載次數 >= min_count 的帖子列表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    dh.tid,
                    COUNT(*) as download_count,
                    MAX(dh.download_time) as last_download,
                    MIN(dh.download_time) as first_download,
                    dh.filename,
                    p.title,
                    p.post_url
                FROM download_history dh
                LEFT JOIN posts p ON dh.tid = p.thread_id
                GROUP BY dh.tid
                HAVING download_count >= ?
                ORDER BY download_count DESC, last_download DESC
            ''', (min_count,))
            return [dict(row) for row in cursor.fetchall()]

    # ========== JDownloader 下載完成追蹤 ==========

    def mark_jd_complete(self, download_id: int = None, thread_id: str = None):
        """標記 JDownloader 下載完成"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            if download_id:
                cursor.execute('''
                    UPDATE downloads SET jd_complete_time = ?, download_status = 'completed'
                    WHERE id = ?
                ''', (now, download_id))
            elif thread_id:
                cursor.execute('''
                    UPDATE downloads SET jd_complete_time = ?, download_status = 'completed'
                    WHERE post_id IN (SELECT id FROM posts WHERE thread_id = ?)
                    AND jd_complete_time IS NULL
                ''', (now, thread_id))

    def get_pending_jd_downloads(self, run_id: int = None) -> List[Dict[str, Any]]:
        """取得等待 JD 完成的下載項目"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = '''
                SELECT
                    d.id, d.link_url, d.jd_package_name, d.archive_filename,
                    d.sent_to_jd_at, d.jd_complete_time,
                    p.thread_id, p.title
                FROM downloads d
                JOIN posts p ON d.post_id = p.id
                WHERE d.sent_to_jd_at IS NOT NULL
                AND d.jd_complete_time IS NULL
            '''
            if run_id:
                query += ' AND d.id IN (SELECT download_id FROM run_downloads WHERE run_id = ?)'
                cursor.execute(query, (run_id,))
            else:
                cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]

    def check_all_jd_complete(self, thread_ids: List[str]) -> bool:
        """檢查指定的 TID 列表是否全部下載完成"""
        if not thread_ids:
            return True
        with self.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(thread_ids))
            cursor.execute(f'''
                SELECT COUNT(*) FROM downloads d
                JOIN posts p ON d.post_id = p.id
                WHERE p.thread_id IN ({placeholders})
                AND d.sent_to_jd_at IS NOT NULL
                AND d.jd_complete_time IS NULL
            ''', thread_ids)
            pending = cursor.fetchone()[0]
            return pending == 0

    # ========== 版區結構管理 ==========

    def save_forum_section(self, fid: str, name: str, parent_fid: str = None,
                           level: int = 0, post_count: int = None):
        """儲存版區資訊"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute('''
                INSERT OR REPLACE INTO forum_sections
                (fid, name, parent_fid, level, post_count, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (fid, name, parent_fid, level, post_count, now))

    def save_forum_sections_batch(self, sections: List[Dict]):
        """批次儲存版區資訊"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            for section in sections:
                cursor.execute('''
                    INSERT OR REPLACE INTO forum_sections
                    (fid, name, parent_fid, level, post_count, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    section['fid'],
                    section['name'],
                    section.get('parent_fid'),
                    section.get('level', 0),
                    section.get('post_count'),
                    now
                ))

    def get_all_forum_sections(self) -> List[Dict[str, Any]]:
        """取得所有版區"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT fid, name, parent_fid, level, post_count, last_updated
                FROM forum_sections
                ORDER BY level, name
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def get_forum_sections_tree(self) -> List[Dict[str, Any]]:
        """取得版區樹狀結構"""
        sections = self.get_all_forum_sections()

        # 建立 fid -> section 映射
        section_map = {s['fid']: {**s, 'children': []} for s in sections}

        # 建立樹狀結構
        roots = []
        for section in sections:
            fid = section['fid']
            parent_fid = section['parent_fid']

            if parent_fid and parent_fid in section_map:
                section_map[parent_fid]['children'].append(section_map[fid])
            else:
                roots.append(section_map[fid])

        return roots

    def get_forum_section(self, fid: str) -> Optional[Dict[str, Any]]:
        """取得單一版區"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT fid, name, parent_fid, level, post_count, last_updated
                FROM forum_sections WHERE fid = ?
            ''', (fid,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_sections_last_updated(self) -> Optional[str]:
        """取得版區最後更新時間"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT MAX(last_updated) FROM forum_sections')
            row = cursor.fetchone()
            return row[0] if row else None

    def clear_forum_sections(self):
        """清空版區資料"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM forum_sections')

    # ========== 搜尋結果管理 ==========

    def create_search_session(self) -> str:
        """建立新的搜尋 session，回傳 session_id"""
        import uuid
        return str(uuid.uuid4())[:8]

    def save_search_result(self, session_id: str, tid: str, title: str,
                           author: str = None, post_date: str = None,
                           fid: str = None, forum_name: str = None,
                           post_url: str = None):
        """儲存搜尋結果"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO search_results
                (session_id, tid, title, author, post_date, fid, forum_name, post_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (session_id, tid, title, author, post_date, fid, forum_name, post_url))

    def save_search_results_batch(self, session_id: str, results: List[Dict]):
        """批次儲存搜尋結果"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for r in results:
                cursor.execute('''
                    INSERT INTO search_results
                    (session_id, tid, title, author, post_date, fid, forum_name, post_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    session_id,
                    r['tid'],
                    r['title'],
                    r.get('author'),
                    r.get('post_date'),
                    r.get('fid'),
                    r.get('forum_name'),
                    r.get('post_url')
                ))

    def get_search_results(self, session_id: str) -> List[Dict[str, Any]]:
        """取得搜尋結果"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, tid, title, author, post_date, fid, forum_name,
                       post_url, selected, processed
                FROM search_results
                WHERE session_id = ?
                ORDER BY created_at DESC
            ''', (session_id,))
            return [dict(row) for row in cursor.fetchall()]

    def update_search_result_selected(self, result_id: int, selected: bool):
        """更新搜尋結果的選取狀態"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE search_results SET selected = ? WHERE id = ?
            ''', (selected, result_id))

    def update_search_result_processed(self, result_id: int, processed: bool):
        """更新搜尋結果的處理狀態"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE search_results SET processed = ? WHERE id = ?
            ''', (processed, result_id))

    def get_selected_search_results(self, session_id: str) -> List[Dict[str, Any]]:
        """取得已勾選的搜尋結果"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, tid, title, author, post_date, fid, forum_name,
                       post_url, selected, processed
                FROM search_results
                WHERE session_id = ? AND selected = 1 AND processed = 0
                ORDER BY created_at
            ''', (session_id,))
            return [dict(row) for row in cursor.fetchall()]

    def clear_search_results(self, session_id: str = None):
        """清空搜尋結果"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if session_id:
                cursor.execute('DELETE FROM search_results WHERE session_id = ?', (session_id,))
            else:
                cursor.execute('DELETE FROM search_results')

    def cleanup_old_search_results(self, days: int = 7):
        """清理舊的搜尋結果"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            cursor.execute('DELETE FROM search_results WHERE created_at < ?', (cutoff,))
