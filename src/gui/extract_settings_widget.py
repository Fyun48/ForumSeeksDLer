"""
解壓縮設定 GUI 元件
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QCheckBox, QSpinBox, QRadioButton,
    QPushButton, QListWidget, QListWidgetItem, QLineEdit,
    QButtonGroup, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal

from ..models.extract_models import ExtractConfig


class ExtractSettingsWidget(QWidget):
    """解壓縮設定元件"""

    # 設定變更訊號
    settings_changed = pyqtSignal(dict)

    # 預設排除副檔名
    DEFAULT_EXCLUDE_EXTENSIONS = ['.txt', '.nfo', '.url', '.htm', '.html', '.lnk']

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        """初始化介面"""
        layout = QVBoxLayout(self)

        # 巢狀解壓設定
        nested_group = QGroupBox("巢狀解壓")
        nested_layout = QGridLayout(nested_group)

        self.chk_nested_enabled = QCheckBox("啟用巢狀解壓")
        self.chk_nested_enabled.setChecked(True)
        self.chk_nested_enabled.stateChanged.connect(self._on_nested_enabled_changed)
        nested_layout.addWidget(self.chk_nested_enabled, 0, 0, 1, 2)

        nested_layout.addWidget(QLabel("最大層數:"), 1, 0)
        self.spin_max_depth = QSpinBox()
        self.spin_max_depth.setRange(1, 10)
        self.spin_max_depth.setValue(3)
        nested_layout.addWidget(self.spin_max_depth, 1, 1)

        layout.addWidget(nested_group)

        # 分隔線
        layout.addWidget(self._create_separator())

        # 重複檔案處理
        duplicate_group = QGroupBox("重複檔案處理")
        duplicate_layout = QVBoxLayout(duplicate_group)

        self.radio_smart = QRadioButton("智慧判斷 (大小相同跳過，不同則重新命名)")
        self.radio_smart.setChecked(True)
        duplicate_layout.addWidget(self.radio_smart)

        layout.addWidget(duplicate_group)

        # 分隔線
        layout.addWidget(self._create_separator())

        # 刪除設定
        delete_group = QGroupBox("解壓後刪除原始壓縮檔")
        delete_layout = QVBoxLayout(delete_group)

        self.chk_delete_enabled = QCheckBox("解壓成功後刪除原始壓縮檔")
        self.chk_delete_enabled.setChecked(True)
        self.chk_delete_enabled.stateChanged.connect(self._on_delete_enabled_changed)
        delete_layout.addWidget(self.chk_delete_enabled)

        self.radio_permanent = QRadioButton("永久刪除")
        self.radio_permanent.setChecked(True)
        delete_layout.addWidget(self.radio_permanent)

        self.radio_recycle = QRadioButton("移至資源回收桶")
        delete_layout.addWidget(self.radio_recycle)

        self.delete_btn_group = QButtonGroup(self)
        self.delete_btn_group.addButton(self.radio_permanent)
        self.delete_btn_group.addButton(self.radio_recycle)

        layout.addWidget(delete_group)

        # 分隔線
        layout.addWidget(self._create_separator())

        # 智慧資料夾結構
        folder_group = QGroupBox("智慧資料夾結構")
        folder_layout = QGridLayout(folder_group)

        self.chk_smart_folder = QCheckBox("啟用智慧資料夾結構")
        self.chk_smart_folder.setChecked(True)
        self.chk_smart_folder.setToolTip(
            "根據壓縮檔內容決定是否建立外層資料夾：\n"
            "• 若壓縮檔根目錄是單一資料夾 → 不額外包一層\n"
            "• 若是散落檔案 → 依檔案數量決定"
        )
        self.chk_smart_folder.stateChanged.connect(self._on_smart_folder_changed)
        folder_layout.addWidget(self.chk_smart_folder, 0, 0, 1, 3)

        folder_layout.addWidget(QLabel("過濾後"), 1, 0)
        self.spin_min_files = QSpinBox()
        self.spin_min_files.setRange(1, 10)
        self.spin_min_files.setValue(2)
        folder_layout.addWidget(self.spin_min_files, 1, 1)
        folder_layout.addWidget(QLabel("個檔案以上才建立外層資料夾"), 1, 2)

        layout.addWidget(folder_group)

        # 分隔線
        layout.addWidget(self._create_separator())

        # 排除副檔名
        exclude_group = QGroupBox("排除副檔名")
        exclude_layout = QVBoxLayout(exclude_group)

        self.list_exclude = QListWidget()
        self.list_exclude.setMaximumHeight(120)
        exclude_layout.addWidget(self.list_exclude)

        # 新增/刪除按鈕列
        btn_layout = QHBoxLayout()

        self.txt_new_ext = QLineEdit()
        self.txt_new_ext.setPlaceholderText("例如: .exe")
        self.txt_new_ext.setMaximumWidth(100)
        btn_layout.addWidget(self.txt_new_ext)

        btn_add = QPushButton("+新增")
        btn_add.clicked.connect(self._add_extension)
        btn_layout.addWidget(btn_add)

        btn_remove = QPushButton("刪除選取")
        btn_remove.clicked.connect(self._remove_extension)
        btn_layout.addWidget(btn_remove)

        btn_reset = QPushButton("重設為預設值")
        btn_reset.clicked.connect(self._reset_extensions)
        btn_layout.addWidget(btn_reset)

        btn_layout.addStretch()

        exclude_layout.addLayout(btn_layout)

        layout.addWidget(exclude_group)

        # 加入彈性空間
        layout.addStretch()

        # 載入預設值
        self._reset_extensions()

    def _create_separator(self) -> QFrame:
        """建立分隔線"""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _on_nested_enabled_changed(self, state):
        """巢狀解壓開關變更"""
        self.spin_max_depth.setEnabled(state == Qt.CheckState.Checked.value)

    def _on_delete_enabled_changed(self, state):
        """刪除開關變更"""
        enabled = state == Qt.CheckState.Checked.value
        self.radio_permanent.setEnabled(enabled)
        self.radio_recycle.setEnabled(enabled)

    def _on_smart_folder_changed(self, state):
        """智慧資料夾開關變更"""
        self.spin_min_files.setEnabled(state == Qt.CheckState.Checked.value)

    def _add_extension(self):
        """新增排除副檔名"""
        ext = self.txt_new_ext.text().strip()
        if not ext:
            return

        # 確保以點開頭
        if not ext.startswith('.'):
            ext = '.' + ext

        ext = ext.lower()

        # 檢查是否已存在
        for i in range(self.list_exclude.count()):
            if self.list_exclude.item(i).text().lower() == ext:
                QMessageBox.information(self, "提示", f"副檔名 {ext} 已存在")
                return

        self.list_exclude.addItem(ext)
        self.txt_new_ext.clear()

    def _remove_extension(self):
        """移除選取的副檔名"""
        current = self.list_exclude.currentRow()
        if current >= 0:
            self.list_exclude.takeItem(current)

    def _reset_extensions(self):
        """重設為預設值"""
        self.list_exclude.clear()
        for ext in self.DEFAULT_EXCLUDE_EXTENSIONS:
            self.list_exclude.addItem(ext)

    def get_settings(self) -> dict:
        """取得目前設定值"""
        exclude_exts = []
        for i in range(self.list_exclude.count()):
            exclude_exts.append(self.list_exclude.item(i).text())

        return {
            'extract': {
                'nested': {
                    'enabled': self.chk_nested_enabled.isChecked(),
                    'max_depth': self.spin_max_depth.value()
                },
                'duplicate': {
                    'mode': 'smart'  # 目前只支援 smart 模式
                },
                'exclude_extensions': exclude_exts,
                'delete': {
                    'enabled': self.chk_delete_enabled.isChecked(),
                    'permanent': self.radio_permanent.isChecked()
                },
                'smart_folder': {
                    'enabled': self.chk_smart_folder.isChecked(),
                    'min_files_for_folder': self.spin_min_files.value()
                }
            }
        }

    def set_settings(self, config: dict):
        """設定介面值"""
        extract_config = config.get('extract', {})

        # 巢狀解壓
        nested = extract_config.get('nested', {})
        self.chk_nested_enabled.setChecked(nested.get('enabled', True))
        self.spin_max_depth.setValue(nested.get('max_depth', 3))

        # 刪除設定
        delete = extract_config.get('delete', {})
        self.chk_delete_enabled.setChecked(delete.get('enabled', True))
        if delete.get('permanent', True):
            self.radio_permanent.setChecked(True)
        else:
            self.radio_recycle.setChecked(True)

        # 智慧資料夾
        smart_folder = extract_config.get('smart_folder', {})
        self.chk_smart_folder.setChecked(smart_folder.get('enabled', True))
        self.spin_min_files.setValue(smart_folder.get('min_files_for_folder', 2))

        # 排除副檔名
        exclude_exts = extract_config.get('exclude_extensions', self.DEFAULT_EXCLUDE_EXTENSIONS)
        self.list_exclude.clear()
        for ext in exclude_exts:
            self.list_exclude.addItem(ext)

        # 觸發狀態更新
        self._on_nested_enabled_changed(
            Qt.CheckState.Checked.value if self.chk_nested_enabled.isChecked() else Qt.CheckState.Unchecked.value
        )
        self._on_delete_enabled_changed(
            Qt.CheckState.Checked.value if self.chk_delete_enabled.isChecked() else Qt.CheckState.Unchecked.value
        )
        self._on_smart_folder_changed(
            Qt.CheckState.Checked.value if self.chk_smart_folder.isChecked() else Qt.CheckState.Unchecked.value
        )
