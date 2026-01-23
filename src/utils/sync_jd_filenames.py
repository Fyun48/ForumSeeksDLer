"""
一次性腳本：從 JDownloader 記錄同步壓縮檔名稱到資料庫
用於修復舊記錄缺少 archive_filename 的問題
"""
import sys
from pathlib import Path

# 添加專案路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database.db_manager import DatabaseManager
from src.downloader.jd_history_reader import JDHistoryReader


def sync_jd_filenames(jd_path: str):
    """
    從 JD 記錄同步壓縮檔名稱到資料庫

    Args:
        jd_path: JDownloader 安裝路徑
    """
    print(f"JDownloader 路徑: {jd_path}")

    # 讀取 JD 記錄
    reader = JDHistoryReader(jd_path)
    history = reader.read_download_history()

    if not history:
        print("找不到 JDownloader 下載記錄")
        return

    print(f"從 JD 讀取到 {len(history)} 筆記錄")

    # 建立 套件名稱 -> 檔名列表 的對應
    package_to_files = {}
    for record in history:
        package_name = record.get('package_name', '')
        file_name = record.get('file_name', '')

        if package_name and file_name:
            if package_name not in package_to_files:
                package_to_files[package_name] = []
            if file_name not in package_to_files[package_name]:
                package_to_files[package_name].append(file_name)

    print(f"整理出 {len(package_to_files)} 個套件的檔名對應")

    # 更新資料庫
    db = DatabaseManager()
    updated = 0

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # 取得所有下載記錄
        cursor.execute('''
            SELECT d.id, d.jd_package_name, p.title, d.archive_filename
            FROM downloads d
            JOIN posts p ON d.post_id = p.id
            WHERE d.archive_filename IS NULL OR d.archive_filename = ''
        ''')
        rows = cursor.fetchall()

        print(f"找到 {len(rows)} 筆需要更新的記錄")

        for row in rows:
            download_id = row[0]
            jd_package_name = row[1]
            title = row[2]

            # 嘗試用 jd_package_name 或 title 匹配
            matched_files = None

            # 方法 1: 用 jd_package_name 精確匹配
            if jd_package_name and jd_package_name in package_to_files:
                matched_files = package_to_files[jd_package_name]

            # 方法 2: 用 title 匹配
            if not matched_files and title:
                for pkg_name, files in package_to_files.items():
                    if title in pkg_name or pkg_name in title:
                        matched_files = files
                        break

            # 方法 3: 部分匹配
            if not matched_files and title:
                title_lower = title.lower()
                for pkg_name, files in package_to_files.items():
                    pkg_lower = pkg_name.lower()
                    # 取前 20 個字元比較
                    if title_lower[:20] in pkg_lower or pkg_lower[:20] in title_lower:
                        matched_files = files
                        break

            if matched_files:
                # 合併檔名 (用 | 分隔)
                archive_filename = '|'.join(matched_files)
                cursor.execute('''
                    UPDATE downloads SET archive_filename = ? WHERE id = ?
                ''', (archive_filename, download_id))
                updated += 1
                print(f"  更新: {title[:40]}... -> {matched_files[0]}")

        conn.commit()

    print(f"\n完成！已更新 {updated} 筆記錄")


def main():
    # 預設 JD 路徑，可以從命令列參數覆寫
    jd_path = r"F:\常用免安裝工軟體\JDownloaderPortable\azofreeware.com"

    if len(sys.argv) > 1:
        jd_path = sys.argv[1]

    sync_jd_filenames(jd_path)


if __name__ == '__main__':
    main()
