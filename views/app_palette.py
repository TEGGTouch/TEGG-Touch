"""
TEGG Touch 蛋挞 (PyQt6) - app_palette.py
「应用」候选面板 — 搜索 + 刷新 + 本地应用列表 (一行一个: 图标 + 名称)。
点击某行 → 发 app_clicked(app_dict={name, path})。
被各编辑器 (按钮/摇杆/方向盘鼠标键/语音/宏) 的「应用」Tab 复用。
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QScrollArea,
)
from PyQt6.QtCore import Qt, QSize, QFileInfo, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon

try:
    from PyQt6.QtGui import QFileIconProvider
except ImportError:  # pragma: no cover - Qt6 下在 QtGui, 兜底 QtWidgets
    from PyQt6.QtWidgets import QFileIconProvider

from core.i18n import t, get_font
from core import app_scanner
from views.button_editor_dialog import (
    _make_font, C_GRAY, C_GRAY_H, C_INPUT_BG, C_CYBER, C_CAT_LABEL,
)

_C_HINT = "#888"

# 图标取 provider + 缓存 (按 path), 避免重复构造/重复取图标卡顿
_icon_provider = None
_icon_cache: dict = {}


def _provider():
    global _icon_provider
    if _icon_provider is None:
        _icon_provider = QFileIconProvider()
    return _icon_provider


def app_icon(path: str) -> QIcon:
    ic = _icon_cache.get(path)
    if ic is None:
        try:
            ic = _provider().icon(QFileInfo(path))
        except Exception:
            ic = QIcon()
        _icon_cache[path] = ic
    return ic


class AppPaletteWidget(QWidget):
    """应用候选面板。点击某行 → app_clicked({name, path})。"""

    app_clicked = pyqtSignal(dict)

    def __init__(self, fn=None, parent=None):
        super().__init__(parent)
        self._fn = fn or get_font()
        self._apps: list[dict] = []
        self._build_ui()
        # 异步首次加载, 避免开弹窗瞬间卡顿
        QTimer.singleShot(0, self._load_apps)

    def _build_ui(self):
        self.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 10)
        lay.setSpacing(8)

        # 搜索 + 刷新
        top = QHBoxLayout()
        top.setSpacing(6)
        self._search = QLineEdit()
        self._search.setPlaceholderText(t("app.search_placeholder"))
        self._search.setFixedHeight(32)
        self._search.setFont(_make_font(self._fn, 13))
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {C_INPUT_BG}; color: #E0E0E0;
                border: 1px solid #555; border-radius: 6px; padding: 2px 8px;
            }}
            QLineEdit:focus {{ border-color: {C_CYBER}; }}
        """)
        self._search.textChanged.connect(self._rebuild)
        top.addWidget(self._search, 1)

        self._refresh_btn = QPushButton(t("app.refresh"))
        self._refresh_btn.setFixedHeight(32)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setFont(_make_font(self._fn, 13))
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px; padding: 0 14px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        self._refresh_btn.clicked.connect(self._rescan)
        top.addWidget(self._refresh_btn)
        lay.addLayout(top)

        # 列表滚动区
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
        self._list_lay = QVBoxLayout(self._host)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(5)
        self._scroll.setWidget(self._host)
        lay.addWidget(self._scroll, 1)

    def _load_apps(self, force: bool = False):
        self._show_hint(t("app.loading"))
        self._apps = app_scanner.get_apps(force=force)
        self._rebuild()

    def _rescan(self):
        self._load_apps(force=True)

    def _clear_list(self):
        while self._list_lay.count():
            it = self._list_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()

    def _show_hint(self, text: str):
        self._clear_list()
        lbl = QLabel(text)
        lbl.setFont(_make_font(self._fn, 13))
        lbl.setStyleSheet(f"color: {_C_HINT}; background: transparent;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_lay.addWidget(lbl)
        self._list_lay.addStretch()

    def _rebuild(self):
        self._clear_list()
        kw = self._search.text().strip().lower()
        items = [a for a in self._apps if kw in a["name"].lower()] if kw else self._apps
        if not items:
            self._show_hint(t("app.empty"))
            return
        for a in items:
            self._list_lay.addWidget(self._make_row(a))
        self._list_lay.addStretch()

    def _make_row(self, app: dict) -> QPushButton:
        btn = QPushButton(app.get("name", ""))
        btn.setIcon(app_icon(app.get("path", "")))
        btn.setIconSize(QSize(20, 20))
        btn.setFixedHeight(38)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(_make_font(self._fn, 14))
        btn.setToolTip(app.get("path", ""))
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0; border: none;
                border-radius: 6px; padding: 0 10px; text-align: left;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        btn.clicked.connect(lambda _, a=app: self.app_clicked.emit(a))
        return btn
