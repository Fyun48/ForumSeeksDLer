"""
JDownloader 下載記錄讀取器
讀取 JD 的 downloadList.zip 來取得實際下載的檔案名稱
"""
import json
import zipfile
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote

from ..utils.logger import logger


class JDHistoryReader:
    """讀取 JDownloader 下載記錄"""

    def __init__(self, jd_path: str):
        """
        初始化

        Args:
            jd_path: JDownloader 安裝路徑 (包含 cfg 目錄的路徑)
        """
        self.jd_path = Path(jd_path)
        self.cfg_path = self._find_cfg_path()

    def _find_cfg_path(self) -> Optional[Path]:
        """尋找 JDownloader 的 cfg 目錄"""
        possible_paths = [
            self.jd_path / 'cfg',
            self.jd_path / 'App' / 'JDownloader2' / 'cfg',  # Portable 版本
            self.jd_path,
        ]

        for path in possible_paths:
            if path.exists() and (path / 'downloadList1867.zip').exists():
                return path
            # 檢查是否有任何 downloadList*.zip
            if path.exists():
                download_lists = list(path.glob('downloadList*.zip'))
                if download_lists:
                    return path

        logger.warning(f"找不到 JDownloader cfg 目錄: {self.jd_path}")
        return None

    def get_latest_download_list(self) -> Optional[Path]:
        """取得最新的 downloadList.zip 檔案"""
        if not self.cfg_path:
            return None

        download_lists = list(self.cfg_path.glob('downloadList*.zip'))
        if not download_lists:
            return None

        # 按修改時間排序，取最新的
        download_lists.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return download_lists[0]

    def read_download_history(self) -> List[Dict]:
        """
        讀取下載記錄

        Returns:
            包含下載記錄的列表，每筆記錄包含:
            - package_name: 套件名稱 (crawljob 標題)
            - file_name: 實際下載的檔案名稱
            - download_folder: 下載目錄
            - status: 下載狀態 (FINISHED, etc.)
            - crawljob_source: crawljob 來源檔案
        """
        download_list = self.get_latest_download_list()
        if not download_list:
            logger.warning("找不到 JDownloader downloadList")
            return []

        results = []

        try:
            with zipfile.ZipFile(download_list, 'r') as zf:
                # 取得所有檔案名稱
                names = zf.namelist()

                # 找出所有 package (不含底線的檔案)
                packages = [n for n in names if '_' not in n and n != 'extraInfo']

                for pkg_name in packages:
                    try:
                        # 讀取 package 資訊
                        pkg_data = json.loads(zf.read(pkg_name).decode('utf-8'))
                        package_name = pkg_data.get('name', '')
                        download_folder = pkg_data.get('downloadFolder', '')

                        # 找出這個 package 的所有 links
                        link_files = [n for n in names if n.startswith(f"{pkg_name}_")]

                        for link_file in link_files:
                            try:
                                link_data = json.loads(zf.read(link_file).decode('utf-8'))

                                # 取得實際檔名 (優先使用 FINAL_FILENAME)
                                properties = link_data.get('properties', {})
                                file_name = properties.get('FINAL_FILENAME') or link_data.get('name', '')

                                # 取得 crawljob 來源
                                url_origin = properties.get('URL_ORIGIN', '')
                                crawljob_source = ''
                                if url_origin:
                                    # 解碼 URL
                                    crawljob_source = unquote(url_origin)
                                    # 提取檔名
                                    if '/' in crawljob_source:
                                        crawljob_source = crawljob_source.split('/')[-1]

                                results.append({
                                    'package_name': package_name,
                                    'file_name': file_name,
                                    'download_folder': download_folder,
                                    'status': link_data.get('finalLinkState', 'UNKNOWN'),
                                    'crawljob_source': crawljob_source,
                                    'url': link_data.get('url', ''),
                                    'size': link_data.get('size', 0),
                                })

                            except (json.JSONDecodeError, KeyError) as e:
                                logger.debug(f"解析 link 失敗 {link_file}: {e}")

                    except (json.JSONDecodeError, KeyError) as e:
                        logger.debug(f"解析 package 失敗 {pkg_name}: {e}")

        except Exception as e:
            logger.error(f"讀取 downloadList 失敗: {e}")

        return results

    def get_filename_to_package_mapping(self) -> Dict[str, str]:
        """
        取得 實際檔名 -> 套件名稱 的對應

        Returns:
            dict: {實際檔名: 套件名稱}
        """
        history = self.read_download_history()
        mapping = {}

        for record in history:
            file_name = record.get('file_name', '')
            package_name = record.get('package_name', '')

            if file_name and package_name:
                # 移除副檔名和 .partXX 後綴
                clean_name = self._clean_filename(file_name)
                mapping[clean_name] = package_name

                # 也加入原始檔名
                mapping[file_name.lower()] = package_name

        return mapping

    def _clean_filename(self, filename: str) -> str:
        """清理檔名 (移除副檔名和 .partXX)"""
        name = filename.lower()

        # 移除副檔名
        for ext in ['.rar', '.zip', '.7z']:
            if name.endswith(ext):
                name = name[:-len(ext)]
                break

        # 移除 .partXX
        name = re.sub(r'\.part\d+$', '', name)

        return name

    def find_package_for_archive(self, archive_name: str) -> Optional[str]:
        """
        根據壓縮檔名稱尋找對應的套件名稱

        Args:
            archive_name: 壓縮檔名稱

        Returns:
            套件名稱 (帖子標題) 或 None
        """
        mapping = self.get_filename_to_package_mapping()
        clean_name = self._clean_filename(archive_name)

        # 精確匹配
        if clean_name in mapping:
            return mapping[clean_name]

        # 包含匹配
        for file_name, package_name in mapping.items():
            if clean_name in file_name or file_name in clean_name:
                return package_name

        return None

    def get_completed_downloads(self) -> List[Dict]:
        """取得所有已完成的下載"""
        history = self.read_download_history()
        return [r for r in history if r.get('status') == 'FINISHED']

    def get_latest_linkgrabber_list(self) -> Optional[Path]:
        """取得最新的 linkgrabber/linkcollector zip 檔案"""
        if not self.cfg_path:
            return None

        # JDownloader 可能使用 linkcollectorlist 或 linkgrabberlist
        patterns = ['linkcollectorlist*.zip', 'linkgrabberlist*.zip']

        for pattern in patterns:
            files = list(self.cfg_path.glob(pattern))
            if files:
                files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                return files[0]

        return None

    def read_linkgrabber_list(self) -> List[Dict]:
        """
        讀取 linkgrabber 列表（JD 解析後但尚未開始下載的連結）

        Returns:
            包含連結資訊的列表，每筆記錄包含:
            - package_name: 套件名稱
            - file_name: JD 解析出的檔名
            - url: 原始連結
            - status: 狀態 (ONLINE, OFFLINE, UNKNOWN 等)
            - size: 檔案大小
        """
        linkgrabber_list = self.get_latest_linkgrabber_list()
        if not linkgrabber_list:
            logger.debug("找不到 JDownloader linkgrabber 列表")
            return []

        results = []

        try:
            with zipfile.ZipFile(linkgrabber_list, 'r') as zf:
                names = zf.namelist()

                # 找出所有 package (不含底線的檔案，排除 extraInfo)
                packages = [n for n in names if '_' not in n and n != 'extraInfo']

                for pkg_name in packages:
                    try:
                        pkg_data = json.loads(zf.read(pkg_name).decode('utf-8'))
                        package_name = pkg_data.get('name', '')

                        # 找出這個 package 的所有 links
                        link_files = [n for n in names if n.startswith(f"{pkg_name}_")]

                        for link_file in link_files:
                            try:
                                link_data = json.loads(zf.read(link_file).decode('utf-8'))

                                # linkcollector 結構: link_data.downloadLink 包含實際連結資訊
                                download_link = link_data.get('downloadLink', {})
                                if download_link:
                                    # 從 downloadLink 取得資訊
                                    properties = download_link.get('properties', {})
                                    file_name = (
                                        properties.get('FINAL_FILENAME') or
                                        download_link.get('name', '')
                                    )
                                    url = download_link.get('url', '')
                                    status = download_link.get('availablestatus', 'UNKNOWN')
                                    size = download_link.get('size', 0)
                                else:
                                    # 舊格式: 直接在 link_data 中
                                    properties = link_data.get('properties', {})
                                    file_name = (
                                        properties.get('FINAL_FILENAME') or
                                        link_data.get('name', '')
                                    )
                                    url = link_data.get('url', '')
                                    status = link_data.get('availability', 'UNKNOWN')
                                    size = link_data.get('size', 0)

                                results.append({
                                    'package_name': package_name,
                                    'file_name': file_name,
                                    'url': url,
                                    'status': status,
                                    'size': size,
                                })

                            except (json.JSONDecodeError, KeyError) as e:
                                logger.debug(f"解析 linkgrabber link 失敗 {link_file}: {e}")

                    except (json.JSONDecodeError, KeyError) as e:
                        logger.debug(f"解析 linkgrabber package 失敗 {pkg_name}: {e}")

        except Exception as e:
            logger.error(f"讀取 linkgrabber 列表失敗: {e}")

        logger.debug(f"讀取 linkgrabber 列表: {len(results)} 筆")
        return results

    def get_online_links_from_grabber(self) -> List[Dict]:
        """取得 linkgrabber 中狀態為 ONLINE 的連結"""
        links = self.read_linkgrabber_list()
        return [r for r in links if r.get('status') == 'ONLINE']


def test_reader():
    """測試讀取器"""
    # 測試用
    jd_path = r"F:\常用免安裝工軟體\JDownloaderPortable\azofreeware.com"
    reader = JDHistoryReader(jd_path)

    print("=== JDownloader 下載記錄 ===")
    history = reader.read_download_history()

    for record in history[:10]:  # 只顯示前 10 筆
        print(f"Package: {record['package_name']}")
        print(f"  File: {record['file_name']}")
        print(f"  Status: {record['status']}")
        print(f"  Crawljob: {record['crawljob_source']}")
        print()


if __name__ == '__main__':
    test_reader()
