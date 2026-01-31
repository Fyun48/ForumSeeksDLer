# -*- mode: python ; coding: utf-8 -*-
"""
DLP01 PyInstaller 配置檔

使用方式:
    pyinstaller dlp01.spec

或使用 build.py 腳本:
    python build.py
"""

import sys
from pathlib import Path

# 專案根目錄
PROJECT_ROOT = Path(SPECPATH)

# 從 version.py 讀取版本資訊
sys.path.insert(0, str(PROJECT_ROOT))
from src.version import VERSION, APP_NAME

# 分析入口點
a = Analysis(
    ['dlp01_gui.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # 設定檔目錄
        ('config', 'config'),
        # 資料目錄 (會在執行時建立，但先包含空目錄結構)
    ],
    hiddenimports=[
        # PyQt6 相關
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        # 其他相依
        'requests',
        'bs4',
        'lxml',
        'yaml',
        'cryptography',
        'plyer',
        'plyer.platforms',
        'plyer.platforms.win',
        # 專案模組
        'src',
        'src.version',
        'src.updater',
        'src.main',
        'src.database',
        'src.database.db_manager',
        'src.crawler',
        'src.crawler.forum_client',
        'src.crawler.post_parser',
        'src.crawler.thanks_handler',
        'src.crawler.forum_searcher',
        'src.crawler.forum_structure_scraper',
        'src.downloader',
        'src.downloader.link_extractor',
        'src.downloader.jd_integration',
        'src.downloader.extract_monitor',
        'src.downloader.jd_history_reader',
        'src.downloader.jd_status_poller',
        'src.gui',
        'src.gui.main_window',
        'src.gui.styles',
        'src.gui.notifications',
        'src.gui.update_dialog',
        'src.gui.workers',
        'src.utils',
        'src.utils.logger',
        'src.utils.profile_manager',
        'src.models',
        'src.models.extract_models',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的模組
        'tkinter',
        'unittest',
        'test',
        'tests',
    ],
    noarchive=False,
    optimize=0,
)

# 打包成單一目錄
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI 程式不需要控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if Path('assets/icon.ico').exists() else None,
    version='file_version_info.txt' if Path('file_version_info.txt').exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
