#!/usr/bin/env python3
"""
監控下載目錄，自動解壓並刪除 RAR
獨立執行，與主程式分開
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import yaml
from src.downloader.extract_monitor import ExtractMonitor
from src.utils.logger import logger


def main():
    parser = argparse.ArgumentParser(description='DLP01 - 下載監控與自動解壓')
    parser.add_argument('--interval', '-i', type=int, default=60,
                        help='檢查間隔 (秒)')
    parser.add_argument('--no-delete', action='store_true',
                        help='解壓後不刪除原始檔案')
    parser.add_argument('--once', action='store_true',
                        help='只執行一次，不持續監控')
    parser.add_argument('--password', '-p', type=str,
                        help='加入解壓密碼')
    args = parser.parse_args()

    # 載入設定
    config_path = Path(__file__).parent / 'config' / 'config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 建立監控器
    monitor = ExtractMonitor(
        download_dir=config['paths']['download_dir'],
        extract_dir=config['paths']['extract_dir'],
        winrar_path=config['paths']['winrar_path']
    )

    # 加入密碼
    if args.password:
        monitor.add_password(args.password)

    # 從資料庫載入已知密碼和對應的檔案名稱
    try:
        from src.database.db_manager import DatabaseManager
        db = DatabaseManager()

        # 載入所有密碼
        passwords = db.get_all_passwords()
        for pwd in passwords:
            monitor.add_password(pwd)
        logger.info(f"已從資料庫載入 {len(passwords)} 個密碼")

        # 載入密碼與標題的對應關係
        password_mappings = db.get_passwords_with_titles()
        for mapping in password_mappings:
            monitor.add_password_mapping(
                mapping['package_name'] or mapping['title'],
                mapping['password']
            )
        logger.info(f"已載入 {len(password_mappings)} 個密碼對應")
    except Exception as e:
        logger.warning(f"載入資料庫密碼失敗: {e}")

    delete_after = not args.no_delete

    if args.once:
        # 只執行一次
        processed = monitor.process_archives(delete_after)
        logger.info(f"處理完成，共處理 {processed} 個壓縮檔")
    else:
        # 持續監控
        monitor.run_monitor(interval=args.interval, delete_after=delete_after)


if __name__ == '__main__':
    main()
