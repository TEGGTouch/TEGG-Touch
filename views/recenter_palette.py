"""
TEGG Touch 蛋挞 (PyQt6) - recenter_palette.py
「回中目标」单选列表 — 一行一个目标 (屏幕中心/中心环/方向盘/各摇杆)。
选中的高亮。被回中带按钮编辑器 + 语音「回中」模式 Tab 共用。
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QScrollArea
from PyQt6.QtCore import Qt, pyqtSignal

from core.i18n import t, get_font
from views.button_editor_dialog import (
    _make_font, C_GRAY, C_GRAY_H, C_CYBER, C_CAT_LABEL,
)

_C_HINT = "#888"


class RecenterPaletteWidget(QWidget):
    """回中目标单选列表。选中 → target_selected(key)。"""

    target_selected = pyqtSignal(str)

    def __init__(self, targets=None, current_key="screen", fn=None, parent=None):
        super().__init__(parent)
        self._fn = fn or get_font()
        self._targets = list(targets or [])
        self._current = current_key or "screen"
        self._rows: dict = {}
        self._build_ui()
        self._rebuild()

    def _build_ui(self):
        self.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 10)
        lay.setSpacing(8)
        cat = QLabel(f"── {t('recenter.tab')} ──")
        cat.setFont(_make_font(self._fn, 14, bold=True))
        cat.setStyleSheet(f"color: {C_CAT_LABEL}; background: transparent;")
        lay.addWidget(cat)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 8px; border: none; }
            QScrollBar::handle:vertical { background: #404040; border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        self._host = QWidget()
        self._host.setStyleSheet("background: transparent;")
        self._list = QVBoxLayout(self._host)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(5)
        self._scroll.setWidget(self._host)
        lay.addWidget(self._scroll, 1)

    def set_targets(self, targets, current_key=None):
        self._targets = list(targets or [])
        if current_key is not None:
            self._current = current_key
        self._rebuild()

    def current_key(self) -> str:
        return self._current

    def _rebuild(self):
        while self._list.count():
            it = self._list.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        self._rows = {}
        if not self._targets:
            lbl = QLabel(t("recenter.empty"))
            lbl.setFont(_make_font(self._fn, 13))
            lbl.setStyleSheet(f"color: {_C_HINT}; background: transparent;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._list.addWidget(lbl)
            self._list.addStretch()
            return
        for tgt in self._targets:
            key = tgt.get("key", "")
            btn = QPushButton(tgt.get("label", key))
            btn.setFixedHeight(38)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(_make_font(self._fn, 14))
            btn.clicked.connect(lambda _, k=key: self._on_pick(k))
            self._rows[key] = btn
            self._list.addWidget(btn)
        self._list.addStretch()
        self._restyle()

    def _on_pick(self, key: str):
        self._current = key
        self._restyle()
        self.target_selected.emit(key)

    def _restyle(self):
        for key, btn in self._rows.items():
            if key == self._current:
                btn.setStyleSheet("""
                    QPushButton { background: #10B981; color: #1A1A1A; border: none;
                        border-radius: 6px; padding: 0 10px; text-align: left; }
                    QPushButton:hover { background: #34D399; }
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{ background: {C_GRAY}; color: #E0E0E0; border: none;
                        border-radius: 6px; padding: 0 10px; text-align: left; }}
                    QPushButton:hover {{ background: {C_GRAY_H}; }}
                """)
