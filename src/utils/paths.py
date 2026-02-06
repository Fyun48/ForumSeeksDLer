"""
路徑管理工具 - 統一處理開發環境與安裝環境的路徑

PyInstaller 打包後，程式需要使用執行檔所在目錄作為基準路徑，
而非原始碼的 __file__ 路徑。
"""
import sys
import os
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def get_app_dir() -> Path:
    """
    取得應用程式根目錄

    - 開發環境: 專案根目錄 (E:\\dp01)
    - 安裝環境: 執行檔所在目錄 (如 C:\\Users\\xxx\\AppData\\Local\\Programs\\DLP01)

    Returns:
        應用程式根目錄的 Path 物件
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包後的執行檔
        # sys.executable 是執行檔的完整路徑
        return Path(sys.executable).parent
    else:
        # 開發環境 - 從此檔案往上找到專案根目錄
        # 此檔案位於 src/utils/paths.py
        return Path(__file__).parent.parent.parent


@lru_cache(maxsize=1)
def get_config_dir() -> Path:
    """
    取得設定檔目錄

    Returns:
        設定檔目錄的 Path 物件
    """
    if getattr(sys, 'frozen', False):
        # 安裝環境: 設定檔在 _internal/config
        config_dir = get_app_dir() / "_internal" / "config"
    else:
        # 開發環境
        config_dir = get_app_dir() / "config"

    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


@lru_cache(maxsize=1)
def get_profiles_dir() -> Path:
    """
    取得設定檔群組目錄

    Returns:
        設定檔群組目錄的 Path 物件
    """
    profiles_dir = get_config_dir() / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    return profiles_dir


@lru_cache(maxsize=1)
def get_data_dir() -> Path:
    """
    取得資料目錄 (存放 database, logs 等)

    Returns:
        資料目錄的 Path 物件
    """
    if getattr(sys, 'frozen', False):
        # 安裝環境: 資料存在 _internal/data
        data_dir = get_app_dir() / "_internal" / "data"
    else:
        # 開發環境
        data_dir = get_app_dir() / "data"

    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@lru_cache(maxsize=1)
def get_logs_dir() -> Path:
    """
    取得日誌目錄

    Returns:
        日誌目錄的 Path 物件
    """
    logs_dir = get_data_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_db_path() -> Path:
    """
    取得資料庫檔案路徑

    Returns:
        資料庫檔案的 Path 物件
    """
    return get_data_dir() / "dlp.db"


def is_frozen() -> bool:
    """
    檢查是否為 PyInstaller 打包後的執行檔

    Returns:
        True 如果是打包後的執行檔，否則 False
    """
    return getattr(sys, 'frozen', False)
