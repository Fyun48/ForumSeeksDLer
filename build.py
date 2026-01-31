#!/usr/bin/env python3
"""
DLP01 打包腳本

自動化 PyInstaller 打包流程，產生可發佈的執行檔

使用方式:
    python build.py          # 打包成目錄
    python build.py --onefile # 打包成單一 exe (較大，啟動較慢)
    python build.py --clean   # 清理舊的打包檔案
"""

import os
import sys
import shutil
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# 加入專案路徑
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.version import VERSION, APP_NAME, APP_DISPLAY_NAME


def create_version_info():
    """建立 Windows 版本資訊檔案"""
    # 解析版本號
    parts = VERSION.split('.')
    major = int(parts[0]) if len(parts) > 0 else 1
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0

    # 取得年份
    year = datetime.now().year

    version_info = f'''# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040404B0',
          [
            StringStruct(u'CompanyName', u'{APP_NAME}'),
            StringStruct(u'FileDescription', u'{APP_DISPLAY_NAME}'),
            StringStruct(u'FileVersion', u'{VERSION}'),
            StringStruct(u'InternalName', u'{APP_NAME}'),
            StringStruct(u'LegalCopyright', u'Copyright (c) {year}'),
            StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
            StringStruct(u'ProductName', u'{APP_DISPLAY_NAME}'),
            StringStruct(u'ProductVersion', u'{VERSION}'),
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1028, 1200])])
  ]
)
'''

    version_file = PROJECT_ROOT / 'file_version_info.txt'
    with open(version_file, 'w', encoding='utf-8') as f:
        f.write(version_info)

    print(f"已建立版本資訊檔案: {version_file}")
    return version_file


def clean_build():
    """清理舊的打包檔案"""
    dirs_to_clean = ['build', 'dist', '__pycache__']
    files_to_clean = ['file_version_info.txt']

    for dir_name in dirs_to_clean:
        dir_path = PROJECT_ROOT / dir_name
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"已刪除: {dir_path}")

    for file_name in files_to_clean:
        file_path = PROJECT_ROOT / file_name
        if file_path.exists():
            file_path.unlink()
            print(f"已刪除: {file_path}")

    # 清理 src 目錄下的 __pycache__
    for pycache in PROJECT_ROOT.rglob('__pycache__'):
        shutil.rmtree(pycache)
        print(f"已刪除: {pycache}")

    print("清理完成")


def build(onefile: bool = False):
    """執行打包"""
    print("=" * 60)
    print(f"開始打包 {APP_NAME} v{VERSION}")
    print("=" * 60)

    # 1. 建立版本資訊
    create_version_info()

    # 2. 確保 assets 目錄存在
    assets_dir = PROJECT_ROOT / 'assets'
    assets_dir.mkdir(exist_ok=True)

    # 3. 檢查是否有圖示檔
    icon_path = assets_dir / 'icon.ico'
    if not icon_path.exists():
        print(f"警告: 找不到圖示檔案 {icon_path}")
        print("       將使用預設圖示")

    # 4. 執行 PyInstaller
    print("\n執行 PyInstaller...")

    if onefile:
        # 單一檔案模式
        cmd = [
            sys.executable, '-m', 'PyInstaller',
            '--onefile',
            '--windowed',
            '--name', APP_NAME,
            '--add-data', 'config;config',
            '--hidden-import', 'PyQt6.sip',
            '--hidden-import', 'plyer.platforms.win.notification',
        ]

        if icon_path.exists():
            cmd.extend(['--icon', str(icon_path)])

        cmd.append('dlp01_gui.py')
    else:
        # 使用 spec 檔案
        cmd = [sys.executable, '-m', 'PyInstaller', 'dlp01.spec']

    print(f"命令: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode != 0:
        print("\n打包失敗!")
        return False

    # 5. 複製額外檔案到輸出目錄
    dist_dir = PROJECT_ROOT / 'dist' / APP_NAME
    if dist_dir.exists():
        # 建立 data 目錄
        (dist_dir / 'data').mkdir(exist_ok=True)

        # 複製 README (如果有)
        readme = PROJECT_ROOT / 'README.md'
        if readme.exists():
            shutil.copy(readme, dist_dir / 'README.md')

        print(f"\n打包完成!")
        print(f"輸出目錄: {dist_dir}")
        print(f"\n目錄內容:")
        for item in sorted(dist_dir.iterdir()):
            size = item.stat().st_size if item.is_file() else 0
            if size > 1024 * 1024:
                size_str = f"{size / 1024 / 1024:.1f} MB"
            elif size > 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size} bytes" if size > 0 else "<DIR>"
            print(f"  {item.name:<40} {size_str}")

    return True


def main():
    parser = argparse.ArgumentParser(description=f'{APP_NAME} 打包腳本')
    parser.add_argument('--clean', action='store_true', help='清理舊的打包檔案')
    parser.add_argument('--onefile', action='store_true', help='打包成單一 exe')

    args = parser.parse_args()

    if args.clean:
        clean_build()
        return

    # 檢查 PyInstaller
    try:
        import PyInstaller
        print(f"PyInstaller 版本: {PyInstaller.__version__}")
    except ImportError:
        print("錯誤: 找不到 PyInstaller")
        print("請先安裝: pip install pyinstaller")
        sys.exit(1)

    success = build(onefile=args.onefile)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
