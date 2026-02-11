"""
標籤式輸入元件 (Tag Chips Widget)
支援輸入關鍵字後以標籤方式顯示，可點擊 × 刪除
"""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton,
    QLabel, QFrame, QLayout, QSizePolicy, QLayoutItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QSize, QPoint


class FlowLayout(QLayout):
    """自動換行的流式佈局"""

    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._spacing = spacing

    def addItem(self, item: QLayoutItem):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._do_layout(rect)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only=False) -> int:
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effective.x()
        y = effective.y()
        row_height = 0

        for item in self._items:
            size = item.sizeHint()
            next_x = x + size.width() + self._spacing

            if next_x - self._spacing > effective.right() and row_height > 0:
                x = effective.x()
                y += row_height + self._spacing
                next_x = x + size.width() + self._spacing
                row_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), size))

            x = next_x
            row_height = max(row_height, size.height())

        return y + row_height - rect.y() + m.bottom()


class TagChip(QFrame):
    """單一標籤元件"""
    removed = pyqtSignal(str)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.tag_text = text

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        label = QLabel(text)
        label.setStyleSheet("color: #ECEFF4; background: transparent; border: none;")
        layout.addWidget(label)

        btn_close = QPushButton("×")
        btn_close.setFixedSize(18, 18)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                color: #D8DEE9;
                background: transparent;
                border: none;
                font-size: 14px;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                color: #BF616A;
            }
        """)
        btn_close.clicked.connect(lambda: self.removed.emit(self.tag_text))
        layout.addWidget(btn_close)

        self.setStyleSheet("""
            TagChip {
                background-color: #434C5E;
                border: 1px solid #5E81AC;
                border-radius: 12px;
            }
            TagChip:hover {
                background-color: #4C566A;
                border-color: #88C0D0;
            }
        """)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


class TagWidget(QWidget):
    """標籤式輸入元件"""
    tags_changed = pyqtSignal(list)

    def __init__(self, placeholder: str = "輸入關鍵字後按 Enter", parent=None):
        super().__init__(parent)
        self._tags: list[str] = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # 標籤顯示區
        self._tag_container = QWidget()
        self._tag_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._flow_layout = FlowLayout(self._tag_container, spacing=6)
        main_layout.addWidget(self._tag_container)

        # 輸入列
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)

        self._input = QLineEdit()
        self._input.setPlaceholderText(placeholder)
        self._input.returnPressed.connect(self._on_add)
        input_layout.addWidget(self._input)

        btn_add = QPushButton("新增")
        btn_add.setFixedWidth(60)
        btn_add.clicked.connect(self._on_add)
        input_layout.addWidget(btn_add)

        main_layout.addLayout(input_layout)

    def _on_add(self):
        """新增標籤"""
        text = self._input.text().strip().lower()
        if not text:
            return
        if text in self._tags:
            self._input.clear()
            return

        self._tags.append(text)
        self._add_chip(text)
        self._input.clear()
        self._input.setFocus()
        self.tags_changed.emit(self._tags.copy())

    def _add_chip(self, text: str):
        """新增標籤 chip 到顯示區"""
        chip = TagChip(text, self._tag_container)
        chip.removed.connect(self._on_remove)
        self._flow_layout.addWidget(chip)
        chip.show()
        # 觸發容器重新計算高度
        self._tag_container.updateGeometry()

    def _on_remove(self, text: str):
        """移除標籤"""
        if text in self._tags:
            self._tags.remove(text)

        # 移除對應的 chip widget
        for i in range(self._flow_layout.count()):
            item = self._flow_layout.itemAt(i)
            if item and item.widget():
                chip = item.widget()
                if isinstance(chip, TagChip) and chip.tag_text == text:
                    self._flow_layout.takeAt(i)
                    chip.deleteLater()
                    break

        self._tag_container.updateGeometry()
        self.tags_changed.emit(self._tags.copy())

    def get_tags(self) -> list[str]:
        """取得所有標籤"""
        return self._tags.copy()

    def set_tags(self, tags: list[str]):
        """設定標籤列表"""
        # 清除現有
        self._clear_chips()
        self._tags = list(tags)
        for tag in self._tags:
            self._add_chip(tag)

    def _clear_chips(self):
        """清除所有 chip"""
        while self._flow_layout.count():
            item = self._flow_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._tags.clear()
