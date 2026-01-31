#!/usr/bin/env python3
"""
DLP01 完整打包腳本

自動化整個打包流程:
1. 使用 PyInstaller 打包成執行檔
2. 使用 Inno Setup 建立安裝程式

使用方式:
    python build_installer.py

需要:
    - PyInstaller: pip install pyinstaller
    - Inno Setup: 從 https://jrsoftware.org/isinfo.php 下載安裝
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# 加入專案路徑
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.version import VERSION, APP_NAME


# Inno Setup 常見安裝路徑
ISCC_PATHS = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    r"C:\Program Files\Inno Setup 5\ISCC.exe",
]


def find_iscc():
    """尋找 Inno Setup 編譯器"""
    for path in ISCC_PATHS:
        if Path(path).exists():
            return path

    # 嘗試從 PATH 尋找
    try:
        result = subprocess.run(['where', 'ISCC.exe'], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip().split('\n')[0]
    except Exception:
        pass

    return None


def update_iss_version():
    """更新 .iss 檔案中的版本號"""
    iss_file = PROJECT_ROOT / 'installer' / 'dlp01_setup.iss'

    if not iss_file.exists():
        print(f"錯誤: 找不到 {iss_file}")
        return False

    content = iss_file.read_text(encoding='utf-8')

    # 更新版本號
    import re
    content = re.sub(
        r'#define MyAppVersion ".*?"',
        f'#define MyAppVersion "{VERSION}"',
        content
    )

    iss_file.write_text(content, encoding='utf-8')
    print(f"已更新 .iss 版本號為 {VERSION}")
    return True


def build_executable():
    """使用 PyInstaller 打包"""
    print("=" * 60)
    print("步驟 1: 使用 PyInstaller 打包")
    print("=" * 60)

    # 執行 build.py
    cmd = [sys.executable, 'build.py']
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode != 0:
        print("PyInstaller 打包失敗!")
        return False

    # 檢查輸出
    dist_dir = PROJECT_ROOT / 'dist' / APP_NAME
    if not dist_dir.exists():
        print(f"錯誤: 找不到輸出目錄 {dist_dir}")
        return False

    exe_file = dist_dir / f'{APP_NAME}.exe'
    if not exe_file.exists():
        print(f"錯誤: 找不到執行檔 {exe_file}")
        return False

    print(f"執行檔大小: {exe_file.stat().st_size / 1024 / 1024:.1f} MB")
    return True


def build_installer():
    """使用 Inno Setup 建立安裝程式"""
    print("\n" + "=" * 60)
    print("步驟 2: 使用 Inno Setup 建立安裝程式")
    print("=" * 60)

    # 尋找 ISCC
    iscc = find_iscc()
    if not iscc:
        print("警告: 找不到 Inno Setup Compiler (ISCC.exe)")
        print("請從 https://jrsoftware.org/isinfo.php 下載安裝 Inno Setup")
        print("\n您可以手動使用 Inno Setup Compiler 開啟:")
        print(f"  {PROJECT_ROOT / 'installer' / 'dlp01_setup.iss'}")
        return False

    print(f"使用 ISCC: {iscc}")

    # 更新版本號
    if not update_iss_version():
        return False

    # 執行 ISCC
    iss_file = PROJECT_ROOT / 'installer' / 'dlp01_setup.iss'
    cmd = [iscc, str(iss_file)]

    print(f"執行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode != 0:
        print("Inno Setup 編譯失敗!")
        return False

    # 檢查輸出
    installer_file = PROJECT_ROOT / 'dist' / f'{APP_NAME}_Setup_v{VERSION}.exe'
    if installer_file.exists():
        print(f"\n安裝程式已建立: {installer_file}")
        print(f"檔案大小: {installer_file.stat().st_size / 1024 / 1024:.1f} MB")
        return True
    else:
        print("警告: 找不到安裝程式輸出檔案")
        return False


def main():
    print("=" * 60)
    print(f"DLP01 完整打包腳本 v{VERSION}")
    print("=" * 60)

    # 步驟 1: PyInstaller
    if not build_executable():
        print("\n打包失敗!")
        sys.exit(1)

    # 步驟 2: Inno Setup
    if not build_installer():
        print("\n安裝程式建立失敗 (但執行檔已完成)")
        print(f"執行檔位置: {PROJECT_ROOT / 'dist' / APP_NAME}")
        sys.exit(1)

    # 完成
    print("\n" + "=" * 60)
    print("打包完成!")
    print("=" * 60)
    print(f"\n輸出檔案:")
    print(f"  執行檔目錄: {PROJECT_ROOT / 'dist' / APP_NAME}")
    print(f"  安裝程式:   {PROJECT_ROOT / 'dist' / f'{APP_NAME}_Setup_v{VERSION}.exe'}")

    print("\n發佈步驟:")
    print("  1. 測試安裝程式確認功能正常")
    print("  2. 在 GitHub 建立新的 Release")
    print("  3. 上傳安裝程式到 Release")
    print("  4. 更新 src/version.py 中的 GITHUB_OWNER 和 GITHUB_REPO")


if __name__ == '__main__':
    main()
