#!/usr/bin/env python3
"""
DLP01 GUI 啟動器
"""
import sys
import os
from pathlib import Path

# 抑制 Qt 字型警告
os.environ['QT_LOGGING_RULES'] = '*.debug=false;qt.qpa.fonts=false'

# 加入專案路徑
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from src.gui.styles import apply_nord_theme


def main():
    # 啟用高 DPI 支援
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)

    # 設定應用程式資訊
    app.setApplicationName("DLP01")
    app.setApplicationDisplayName("DLP01 - 論壇自動下載程式")
    app.setOrganizationName("DLP01")

    # 設定預設字型 (避免 MS Sans Serif 警告)
    font = QFont("Microsoft JhengHei UI", 9)  # 微軟正黑體
    app.setFont(font)

    # 設定樣式
    app.setStyle("Fusion")

    # 套用 Nord 深色主題
    apply_nord_theme(app)

    # 載入主視窗
    from src.gui.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
