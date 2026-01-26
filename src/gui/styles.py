"""
GUI 樣式表統一管理 - Nord 深色主題
集中管理所有 PyQt6 StyleSheet，便於維護
"""

# =============================================================================
# Nord 色彩定義
# =============================================================================

# Nord Polar Night (背景色系)
NORD0 = "#2E3440"  # 最深 - 主背景
NORD1 = "#3B4252"  # 次深 - 卡片/面板背景
NORD2 = "#434C5E"  # 中間 - 懸停狀態
NORD3 = "#4C566A"  # 淺深 - 邊框/分隔線

# Nord Snow Storm (文字色系)
NORD4 = "#D8DEE9"  # 次要文字
NORD5 = "#E5E9F0"  # 一般文字
NORD6 = "#ECEFF4"  # 主要文字（最亮）

# Nord Frost (強調色系)
NORD7 = "#8FBCBB"   # 青綠 - 連結/可點擊
NORD8 = "#88C0D0"   # 冰藍 - 主要強調
NORD9 = "#81A1C1"   # 灰藍 - 次要強調
NORD10 = "#5E81AC"  # 深藍 - 選中狀態

# Nord Aurora (語意色系)
NORD11 = "#BF616A"  # 紅 - 錯誤/危險
NORD12 = "#D08770"  # 橙 - 警告
NORD13 = "#EBCB8B"  # 黃 - 提醒
NORD14 = "#A3BE8C"  # 綠 - 成功
NORD15 = "#B48EAD"  # 紫 - 特殊標記

# =============================================================================
# 基礎元件樣式
# =============================================================================

# 主視窗背景
MAIN_WINDOW_STYLE = f"""
    QMainWindow, QWidget {{
        background-color: {NORD0};
        color: {NORD5};
    }}
    QDialog {{
        background-color: {NORD0};
        color: {NORD5};
    }}
"""

# 標籤樣式
LABEL_STYLE = f"""
    QLabel {{
        color: {NORD5};
    }}
"""

# =============================================================================
# 文字樣式（用於 setStyleSheet）
# =============================================================================

# 提示/說明文字
HINT_LABEL = f"color: {NORD4}; font-size: 11px;"

# 錯誤訊息
ERROR_LABEL = f"color: {NORD11};"
ERROR_BOLD = f"color: {NORD11}; font-weight: bold;"

# 成功訊息
SUCCESS_LABEL = f"color: {NORD14}; font-weight: bold;"

# 警告標題
WARNING_TITLE = f"color: {NORD12};"

# =============================================================================
# 按鈕樣式
# =============================================================================

BUTTON_STYLE = f"""
    QPushButton {{
        background-color: {NORD2};
        color: {NORD5};
        border: 1px solid {NORD3};
        padding: 6px 16px;
        border-radius: 4px;
    }}
    QPushButton:hover {{
        background-color: {NORD3};
        border-color: {NORD8};
    }}
    QPushButton:pressed {{
        background-color: {NORD1};
    }}
    QPushButton:disabled {{
        background-color: {NORD1};
        color: {NORD3};
        border-color: {NORD2};
    }}
"""

# 主要按鈕（強調）
BUTTON_PRIMARY = f"""
    QPushButton {{
        background-color: {NORD10};
        color: {NORD6};
        border: none;
        padding: 6px 16px;
        border-radius: 4px;
    }}
    QPushButton:hover {{
        background-color: {NORD9};
    }}
    QPushButton:pressed {{
        background-color: {NORD3};
    }}
"""

# 危險按鈕
BUTTON_DANGER = f"""
    QPushButton {{
        background-color: {NORD11};
        color: {NORD6};
        border: none;
        padding: 6px 16px;
        border-radius: 4px;
    }}
    QPushButton:hover {{
        background-color: #CC5A63;
    }}
    QPushButton:pressed {{
        background-color: #A34E56;
    }}
"""

# 次要按鈕（淡化）
BUTTON_SUBTLE = f"""
    QPushButton {{
        background-color: transparent;
        color: {NORD4};
        border: 1px solid {NORD3};
        padding: 6px 16px;
        border-radius: 4px;
    }}
    QPushButton:hover {{
        background-color: {NORD2};
        color: {NORD5};
    }}
"""

# 特殊按鈕（保留相容性）
DANGER_BUTTON = BUTTON_DANGER
FAVORITE_BUTTON = f"QPushButton {{ color: {NORD13}; font-weight: bold; }}"
COMMON_BUTTON = f"QPushButton {{ color: {NORD8}; font-weight: bold; }}"
MUTED_BUTTON = f"QPushButton {{ color: {NORD4}; }}"

# =============================================================================
# 輸入元件樣式
# =============================================================================

INPUT_STYLE = f"""
    QLineEdit, QTextEdit, QPlainTextEdit {{
        background-color: {NORD1};
        color: {NORD6};
        border: 1px solid {NORD3};
        border-radius: 4px;
        padding: 6px 8px;
        selection-background-color: {NORD10};
        selection-color: {NORD6};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border-color: {NORD8};
    }}
    QLineEdit:disabled, QTextEdit:disabled {{
        background-color: {NORD2};
        color: {NORD4};
    }}
"""

COMBOBOX_STYLE = f"""
    QComboBox {{
        background-color: {NORD1};
        color: {NORD6};
        border: 1px solid {NORD3};
        border-radius: 4px;
        padding: 6px 8px;
        min-width: 80px;
    }}
    QComboBox:hover {{
        border-color: {NORD8};
    }}
    QComboBox:focus {{
        border-color: {NORD8};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid {NORD4};
        margin-right: 8px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {NORD1};
        color: {NORD6};
        selection-background-color: {NORD10};
        selection-color: {NORD6};
        border: 1px solid {NORD3};
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{
        padding: 6px 8px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: {NORD2};
    }}
"""

SPINBOX_STYLE = f"""
    QSpinBox, QDoubleSpinBox {{
        background-color: {NORD1};
        color: {NORD6};
        border: 1px solid {NORD3};
        border-radius: 4px;
        padding: 4px 8px;
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {NORD8};
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        background-color: {NORD2};
        border: none;
        width: 20px;
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover,
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
        background-color: {NORD3};
    }}
"""

# =============================================================================
# 表格樣式
# =============================================================================

TABLE_STYLE = f"""
    QTableWidget, QTableView {{
        background-color: {NORD0};
        alternate-background-color: {NORD1};
        color: {NORD5};
        gridline-color: {NORD2};
        border: 1px solid {NORD3};
        border-radius: 4px;
        selection-background-color: {NORD10};
        selection-color: {NORD6};
    }}
    QTableWidget::item, QTableView::item {{
        padding: 4px 8px;
    }}
    QTableWidget::item:selected, QTableView::item:selected {{
        background-color: {NORD10};
        color: {NORD6};
    }}
    QTableWidget::item:hover, QTableView::item:hover {{
        background-color: {NORD2};
    }}
    QHeaderView::section {{
        background-color: {NORD1};
        color: {NORD6};
        border: none;
        border-bottom: 2px solid {NORD3};
        border-right: 1px solid {NORD2};
        padding: 8px 6px;
        font-weight: bold;
    }}
    QHeaderView::section:hover {{
        background-color: {NORD2};
    }}
    QHeaderView::section:last {{
        border-right: none;
    }}
"""

# 表格語意顏色
TABLE_CELL_SUCCESS = f"color: {NORD14};"
TABLE_CELL_WARNING = f"color: {NORD13};"
TABLE_CELL_ERROR = f"color: {NORD11};"
TABLE_CELL_INFO = f"color: {NORD8};"
TABLE_CELL_MUTED = f"color: {NORD4};"

# =============================================================================
# 分頁標籤樣式
# =============================================================================

TAB_STYLE = f"""
    QTabWidget::pane {{
        border: 1px solid {NORD3};
        border-radius: 4px;
        background-color: {NORD0};
        top: -1px;
    }}
    QTabBar::tab {{
        background-color: {NORD1};
        color: {NORD4};
        border: 1px solid {NORD3};
        border-bottom: none;
        padding: 8px 16px;
        margin-right: 2px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
    }}
    QTabBar::tab:selected {{
        background-color: {NORD0};
        color: {NORD6};
        border-bottom: 2px solid {NORD8};
    }}
    QTabBar::tab:hover:!selected {{
        background-color: {NORD2};
        color: {NORD5};
    }}
"""

# =============================================================================
# 捲軸樣式
# =============================================================================

SCROLLBAR_STYLE = f"""
    QScrollBar:vertical {{
        background-color: {NORD0};
        width: 12px;
        margin: 0;
        border-radius: 6px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {NORD3};
        border-radius: 6px;
        min-height: 30px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {NORD9};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
    QScrollBar:horizontal {{
        background-color: {NORD0};
        height: 12px;
        margin: 0;
        border-radius: 6px;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {NORD3};
        border-radius: 6px;
        min-width: 30px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {NORD9};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
    }}
"""

# =============================================================================
# 其他元件樣式
# =============================================================================

TOOLTIP_STYLE = f"""
    QToolTip {{
        background-color: {NORD1};
        color: {NORD6};
        border: 1px solid {NORD3};
        border-radius: 4px;
        padding: 6px 10px;
    }}
"""

CHECKBOX_STYLE = f"""
    QCheckBox {{
        color: {NORD5};
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid {NORD3};
        border-radius: 4px;
        background-color: {NORD1};
    }}
    QCheckBox::indicator:checked {{
        background-color: {NORD10};
        border-color: {NORD10};
    }}
    QCheckBox::indicator:hover {{
        border-color: {NORD8};
    }}
    QCheckBox::indicator:disabled {{
        background-color: {NORD2};
        border-color: {NORD2};
    }}
"""

RADIO_STYLE = f"""
    QRadioButton {{
        color: {NORD5};
        spacing: 8px;
    }}
    QRadioButton::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid {NORD3};
        border-radius: 10px;
        background-color: {NORD1};
    }}
    QRadioButton::indicator:checked {{
        background-color: {NORD10};
        border-color: {NORD10};
    }}
    QRadioButton::indicator:hover {{
        border-color: {NORD8};
    }}
"""

GROUPBOX_STYLE = f"""
    QGroupBox {{
        color: {NORD6};
        font-weight: bold;
        border: 1px solid {NORD3};
        border-radius: 6px;
        margin-top: 12px;
        padding-top: 8px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        background-color: {NORD0};
    }}
"""

PROGRESSBAR_STYLE = f"""
    QProgressBar {{
        background-color: {NORD1};
        border: 1px solid {NORD3};
        border-radius: 4px;
        text-align: center;
        color: {NORD6};
    }}
    QProgressBar::chunk {{
        background-color: {NORD10};
        border-radius: 3px;
    }}
"""

MENU_STYLE = f"""
    QMenu {{
        background-color: {NORD1};
        color: {NORD5};
        border: 1px solid {NORD3};
        border-radius: 4px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 24px 6px 12px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background-color: {NORD10};
        color: {NORD6};
    }}
    QMenu::separator {{
        height: 1px;
        background-color: {NORD3};
        margin: 4px 8px;
    }}
    QMenuBar {{
        background-color: {NORD1};
        color: {NORD5};
    }}
    QMenuBar::item:selected {{
        background-color: {NORD2};
    }}
"""

STATUSBAR_STYLE = f"""
    QStatusBar {{
        background-color: {NORD1};
        color: {NORD4};
        border-top: 1px solid {NORD3};
    }}
"""

SLIDER_STYLE = f"""
    QSlider::groove:horizontal {{
        background-color: {NORD2};
        height: 6px;
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background-color: {NORD8};
        width: 16px;
        height: 16px;
        margin: -5px 0;
        border-radius: 8px;
    }}
    QSlider::handle:horizontal:hover {{
        background-color: {NORD9};
    }}
"""

# =============================================================================
# 樣式集合（便於程式化存取）
# =============================================================================

STYLES = {
    'hint': HINT_LABEL,
    'error': ERROR_LABEL,
    'error_bold': ERROR_BOLD,
    'success': SUCCESS_LABEL,
    'warning_title': WARNING_TITLE,
    'danger_button': DANGER_BUTTON,
    'favorite_button': FAVORITE_BUTTON,
    'common_button': COMMON_BUTTON,
    'muted_button': MUTED_BUTTON,
}

# =============================================================================
# 顏色常數（用於 QColor）
# =============================================================================

class NordColors:
    """Nord 顏色常數，用於 QColor 設定"""
    # 背景色系 (RGB)
    POLAR_NIGHT_0 = (46, 52, 64)      # NORD0
    POLAR_NIGHT_1 = (59, 66, 82)      # NORD1
    POLAR_NIGHT_2 = (67, 76, 94)      # NORD2
    POLAR_NIGHT_3 = (76, 86, 106)     # NORD3

    # 文字色系 (RGB)
    SNOW_STORM_0 = (216, 222, 233)    # NORD4
    SNOW_STORM_1 = (229, 233, 240)    # NORD5
    SNOW_STORM_2 = (236, 239, 244)    # NORD6

    # 強調色系 (RGB)
    FROST_0 = (143, 188, 187)         # NORD7
    FROST_1 = (136, 192, 208)         # NORD8
    FROST_2 = (129, 161, 193)         # NORD9
    FROST_3 = (94, 129, 172)          # NORD10

    # 語意色系 (RGB)
    AURORA_RED = (191, 97, 106)       # NORD11
    AURORA_ORANGE = (208, 135, 112)   # NORD12
    AURORA_YELLOW = (235, 203, 139)   # NORD13
    AURORA_GREEN = (163, 190, 140)    # NORD14
    AURORA_PURPLE = (180, 142, 173)   # NORD15


# =============================================================================
# 套用函式
# =============================================================================

def get_full_stylesheet() -> str:
    """取得完整的樣式表"""
    return "\n".join([
        MAIN_WINDOW_STYLE,
        LABEL_STYLE,
        BUTTON_STYLE,
        INPUT_STYLE,
        COMBOBOX_STYLE,
        SPINBOX_STYLE,
        TABLE_STYLE,
        TAB_STYLE,
        SCROLLBAR_STYLE,
        TOOLTIP_STYLE,
        CHECKBOX_STYLE,
        RADIO_STYLE,
        GROUPBOX_STYLE,
        PROGRESSBAR_STYLE,
        MENU_STYLE,
        STATUSBAR_STYLE,
        SLIDER_STYLE,
    ])


def apply_nord_theme(app):
    """
    套用 Nord 主題到整個應用程式

    Args:
        app: QApplication 實例

    用法:
        from src.gui.styles import apply_nord_theme
        app = QApplication(sys.argv)
        apply_nord_theme(app)
    """
    app.setStyleSheet(get_full_stylesheet())


# =============================================================================
# 輔助函式（保留相容性）
# =============================================================================

def apply_hint_style(widget):
    """套用提示文字樣式"""
    widget.setStyleSheet(HINT_LABEL)


def apply_error_style(widget, bold: bool = False):
    """套用錯誤樣式"""
    widget.setStyleSheet(ERROR_BOLD if bold else ERROR_LABEL)


def apply_success_style(widget):
    """套用成功樣式"""
    widget.setStyleSheet(SUCCESS_LABEL)


def clear_style(widget):
    """清除樣式"""
    widget.setStyleSheet("")
