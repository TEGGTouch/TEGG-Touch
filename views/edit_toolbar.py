"""
TEGG Touch 蛋挞 (PyQt6) - edit_toolbar.py
编辑模式工具栏 — 浮动在场景底部，匹配原版 Tkinter 布局。

原版布局:
  Row 1: DragHandle | Profile | Add | CenterBand | Wheel | Sep | Keyboard | Run  ...  About | Settings | Close
  Row 2:            | SimMode label+btn | Sep | Opacity label + slider + value%
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QFrame, QSlider,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QFontDatabase

from core.i18n import t, get_font
from core.constants import (
    TOOLBAR_WIDTH, TOOLBAR_HEIGHT, TOOLBAR_RADIUS,
    TOOLBAR_BOTTOM_MARGIN,
)
from views.toolbar_tip_widget import ToolbarTipWidget

# ── 颜色常量 (与原版 widgets.py 完全一致) ──
C_CYBER = "#0C4A6E"
C_CYBER_H = "#0284C7"
C_GRAY = "#3A3A3A"
C_GRAY_H = "#505050"
C_AMBER = "#F59E0B"
C_AMBER_D = "#D97706"
C_CLOSE = "#6E1E1E"
C_CLOSE_H = "#8B2020"
C_PANEL = "#2D2D2D"
C_TOOL = "#4A4A4A"
C_TOOL_H = "#5A5A5A"
C_WH_ON = "#E11D48"       # 玫瑰红 (rose-600)
C_WH_ON_H = "#F43F5E"     # 玫瑰红 hover (rose-500)

# ── 图标字体检测 ──
_ICON_FONT = None


def _detect_icon_font():
    global _ICON_FONT
    if _ICON_FONT is not None:
        return
    families = QFontDatabase.families()
    if "Segoe Fluent Icons" in families:
        _ICON_FONT = "Segoe Fluent Icons"
    elif "Segoe MDL2 Assets" in families:
        _ICON_FONT = "Segoe MDL2 Assets"
    else:
        _ICON_FONT = ""


def _make_font(name, pixel_size, bold=False):
    f = QFont(name)
    f.setPixelSize(pixel_size)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


# ── 拖拽把手 (原版: 4行×2列圆点 + 分隔线) ──
class _DragHandle(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(30)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = 14, self.height() // 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#666"))
        for dy in [-12, -4, 4, 12]:
            for dx in [-4, 4]:
                p.drawEllipse(cx + dx - 2, cy + dy - 2, 4, 4)
        p.setPen(QPen(QColor("#444"), 1))
        p.drawLine(28, 4, 28, self.height() - 4)


# ── 竖分隔线 (原版: #555, 1px) ──
class _VSep(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(12)

    def paintEvent(self, event):
        p = QPainter(self)
        x = self.width() // 2
        p.setPen(QPen(QColor("#555"), 1))
        p.drawLine(x, 4, x, self.height() - 4)


# ── 图标+文字按钮 (自适应宽度, 深灰小圆角) ──
class _IconTextBtn(QPushButton):
    """带图标字体和文字的工具栏按钮 — 宽度自适应内容。"""

    def __init__(self, icon_char, fallback, text, bg, bg_hover,
                 fg="#E0E0E0", width=None, height=40, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedHeight(height)
        if width:
            self.setFixedWidth(width)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bg = bg
        self._bg_h = bg_hover
        self._apply_style()

        fn = get_font()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(4)

        # Icon
        if _ICON_FONT:
            self._icon_lbl = QLabel(icon_char)
            self._icon_lbl.setFont(_make_font(_ICON_FONT, 20))
        elif fallback:
            self._icon_lbl = QLabel(fallback)
            self._icon_lbl.setFont(_make_font(fn, 16, bold=True))
        else:
            self._icon_lbl = None

        if self._icon_lbl:
            self._icon_lbl.setStyleSheet(f"color: {fg}; background: transparent;")
            self._icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lay.addWidget(self._icon_lbl)

        # Text
        self._text_lbl = QLabel(text)
        self._text_lbl.setFont(_make_font(fn, 16))
        self._text_lbl.setStyleSheet(f"color: {fg}; background: transparent;")
        self._text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self._text_lbl)

    def sizeHint(self):
        lay = self.layout()
        if lay:
            m = self.contentsMargins()
            s = lay.sizeHint()
            return QSize(
                s.width() + m.left() + m.right(),
                max(s.height() + m.top() + m.bottom(), self.minimumHeight())
            )
        return super().sizeHint()

    def _apply_style(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background: {self._bg}; border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {self._bg_h}; }}
        """)

    def set_colors(self, bg, bg_hover):
        self._bg = bg
        self._bg_h = bg_hover
        self._apply_style()

    def set_icon_text(self, icon_char, fallback=None):
        if self._icon_lbl:
            self._icon_lbl.setText(icon_char if _ICON_FONT else (fallback or ""))

    def set_label(self, text):
        self._text_lbl.setText(text)


# ═══════════════════════════════════════════════════════════════
class EditToolbar(QWidget):
    """编辑模式工具栏 — 浮动在场景底部"""

    # 信号
    add_button_clicked = pyqtSignal()
    add_center_band_clicked = pyqtSignal()
    keyboard_clicked = pyqtSignal()
    run_clicked = pyqtSignal()
    wheel_clicked = pyqtSignal()
    opacity_changed = pyqtSignal(float)
    grid_changed = pyqtSignal(int)
    profile_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    about_clicked = pyqtSignal()
    quit_clicked = pyqtSignal()
    moved = pyqtSignal()  # 工具栏被拖拽移动时发出，用于同步软键盘位置

    def __init__(self, parent=None):
        super().__init__(parent)
        _detect_icon_font()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._wheel_on = False
        self._drag_pos = None
        self._tip = ToolbarTipWidget()
        self._init_ui()
        self._position_toolbar()

    # ── UI 构建 ──────────────────────────────────────────────

    def _init_ui(self):
        fn = get_font()

        # 外层透明，内层容器有背景
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("et_container")
        container.setStyleSheet(f"""
            QFrame#et_container {{
                background: {C_PANEL};
                border-radius: 4px;
                border: 1px solid #444;
            }}
            QToolTip {{
                background: #1A1A1A;
                color: #E0E0E0;
                border: 1px solid #333;
                padding: 4px 8px;
                font-size: 12px;
            }}
        """)
        outer.addWidget(container)

        main = QVBoxLayout(container)
        main.setContentsMargins(0, 10, 10, 10)
        main.setSpacing(10)

        # ════ Row 1 ════
        r1 = QHBoxLayout()
        r1.setSpacing(10)

        # 拖拽把手
        r1.addWidget(_DragHandle())

        # 方案选择器 (220px, #0C4A6E)
        self._profile_btn = self._build_profile_btn(fn)
        self._profile_btn.setToolTip(t("tooltip.profiles"))
        self._install_tip(self._profile_btn)
        r1.addWidget(self._profile_btn)

        # 添加按钮
        add_btn = _IconTextBtn("\uE710", "\uff0b", t("toolbar.add_button"),
                               C_GRAY, C_GRAY_H)
        add_btn.setToolTip(t("tooltip.add_button"))
        self._install_tip(add_btn)
        add_btn.clicked.connect(self.add_button_clicked.emit)
        r1.addWidget(add_btn)

        # 回中带
        cb_btn = _IconTextBtn("\uE710", "\uff0b", t("toolbar.add_center_band"),
                              C_GRAY, C_GRAY_H)
        cb_btn.setToolTip(t("tooltip.center_band"))
        self._install_tip(cb_btn)
        cb_btn.clicked.connect(self.add_center_band_clicked.emit)
        r1.addWidget(cb_btn)

        # 中心轮盘 toggle
        self._wheel_btn = _IconTextBtn(
            "\uE739", "\u25a3", t("toolbar.center_wheel"),
            C_GRAY, C_GRAY_H)
        self._wheel_btn.setToolTip(t("tooltip.wheel"))
        self._install_tip(self._wheel_btn)
        self._wheel_btn.clicked.connect(self._on_wheel_toggle)
        r1.addWidget(self._wheel_btn)

        # 分隔线
        r1.addWidget(_VSep())

        # 软键盘
        kb_btn = _IconTextBtn("\uE765", "\u2328", t("toolbar.keyboard"),
                              C_GRAY, C_GRAY_H)
        kb_btn.setToolTip(t("tooltip.keyboard"))
        self._install_tip(kb_btn)
        kb_btn.clicked.connect(self.keyboard_clicked.emit)
        r1.addWidget(kb_btn)

        # 启动按钮 (琥珀色)
        run_btn = _IconTextBtn("\uE768", "\u25b6", t("toolbar.start"),
                               C_AMBER_D, C_AMBER, fg="#FFF")
        run_btn.setToolTip(t("tooltip.start"))
        self._install_tip(run_btn)
        run_btn.clicked.connect(self.run_clicked.emit)
        r1.addWidget(run_btn)

        # 弹簧 → 将右侧按钮推到最右
        r1.addStretch()

        # 右上角: 关于 | 设置 | 关闭
        r1_right = QHBoxLayout()
        r1_right.setSpacing(6)
        about_btn = self._build_sq_btn(
            "\uE946", "\u24d8", C_TOOL, C_TOOL_H, "#CCC", self.about_clicked)
        about_btn.setToolTip(t("tooltip.about"))
        self._install_tip(about_btn)
        r1_right.addWidget(about_btn)
        settings_btn = self._build_sq_btn(
            "\uE713", "\u2699", C_TOOL, C_TOOL_H, "#CCC", self.settings_clicked)
        settings_btn.setToolTip(t("tooltip.settings"))
        self._install_tip(settings_btn)
        r1_right.addWidget(settings_btn)
        close_btn = self._build_sq_btn(
            "\uE711", "\u2715", C_CLOSE, C_CLOSE_H, "#FFF", self.quit_clicked)
        close_btn.setToolTip(t("tooltip.quit"))
        self._install_tip(close_btn)
        r1_right.addWidget(close_btn)
        r1.addLayout(r1_right)

        main.addLayout(r1)

        # ════ Row 2 ════
        r2 = QHBoxLayout()
        r2.setSpacing(0)

        # 左对齐空白 (对齐拖拽把手 + 间距)
        sp = QWidget()
        sp.setFixedWidth(38)
        r2.addWidget(sp)

        # 模拟模式标签
        sm_lbl = QLabel(t("toolbar.sim_mode"))
        sm_lbl.setFont(_make_font(fn, 14, bold=True))
        sm_lbl.setStyleSheet("color: #AAA; background: transparent;")
        r2.addWidget(sm_lbl)
        r2.addSpacing(8)

        # 模拟模式按钮 (#0C4A6E)
        sm_btn = QPushButton(t("toolbar.sim_keyboard") + " \u25BC")
        sm_btn.setFixedHeight(30)
        sm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sm_btn.setFont(_make_font(fn, 13, bold=True))
        sm_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER}; color: #E0E0E0; border: none;
                border-radius: 6px; padding: 0 12px;
            }}
            QPushButton:hover {{ background: {C_CYBER_H}; }}
        """)
        sm_btn.setToolTip(t("toolbar.sim_tooltip"))
        r2.addWidget(sm_btn)

        r2.addSpacing(14)
        r2.addWidget(_VSep())
        r2.addSpacing(14)

        # 透明度标签
        op_lbl = QLabel(t("toolbar.opacity"))
        op_lbl.setFont(_make_font(fn, 14, bold=True))
        op_lbl.setStyleSheet("color: #AAA; background: transparent;")
        r2.addWidget(op_lbl)
        r2.addSpacing(12)

        # 透明度滑块 (原版: track #404040, fill amber, thumb #DDD)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setFixedHeight(24)
        self._slider.setRange(10, 90)
        self._slider.setValue(75)
        self._slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #404040; height: 8px; border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: #F59E0B; border-radius: 4px;
            }
            QSlider::add-page:horizontal {
                background: #404040; border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #DDD; border: 1px solid #999;
                width: 18px; height: 18px; margin: -5px 0; border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #F59E0B; border-color: #D97706;
            }
        """)
        self._slider.valueChanged.connect(self._on_opacity)
        r2.addWidget(self._slider, 1)

        r2.addSpacing(8)

        # 百分比数值
        self._val_lbl = QLabel("75%")
        self._val_lbl.setFont(_make_font(fn, 14, bold=True))
        self._val_lbl.setStyleSheet(f"color: {C_AMBER}; background: transparent;")
        self._val_lbl.setFixedWidth(40)
        self._val_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        r2.addWidget(self._val_lbl)

        r2.addSpacing(14)
        r2.addWidget(_VSep())
        r2.addSpacing(14)

        # 网格标签
        grid_lbl = QLabel(t("toolbar.grid"))
        grid_lbl.setFont(_make_font(fn, 14, bold=True))
        grid_lbl.setStyleSheet("color: #AAA; background: transparent;")
        r2.addWidget(grid_lbl)
        r2.addSpacing(12)

        # 网格滑块 (50-100, step 10)
        self._grid_slider = QSlider(Qt.Orientation.Horizontal)
        self._grid_slider.setFixedHeight(24)
        self._grid_slider.setRange(60, 100)
        self._grid_slider.setSingleStep(10)
        self._grid_slider.setPageStep(10)
        self._grid_slider.setValue(100)
        self._grid_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #404040; height: 8px; border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: #10B981; border-radius: 4px;
            }
            QSlider::add-page:horizontal {
                background: #404040; border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #DDD; border: 1px solid #999;
                width: 18px; height: 18px; margin: -5px 0; border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #10B981; border-color: #059669;
            }
        """)
        self._grid_slider.valueChanged.connect(self._on_grid_changed)
        r2.addWidget(self._grid_slider, 1)

        r2.addSpacing(8)

        # 网格数值 (px)
        self._grid_val_lbl = QLabel("100px")
        self._grid_val_lbl.setFont(_make_font(fn, 14, bold=True))
        self._grid_val_lbl.setStyleSheet("color: #10B981; background: transparent;")
        self._grid_val_lbl.setFixedWidth(48)
        self._grid_val_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        r2.addWidget(self._grid_val_lbl)

        main.addLayout(r2)

    # ── 组件构建辅助 ─────────────────────────────────────────

    def _build_profile_btn(self, fn):
        """方案选择器: Icon | Name | DropdownArrow (#0C4A6E, 原版 220px)"""
        btn = QPushButton()
        btn.setFixedHeight(40)
        btn.setMinimumWidth(220)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER}; border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CYBER_H}; }}
        """)
        btn.clicked.connect(self.profile_clicked.emit)

        lay = QHBoxLayout(btn)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(6)

        # 图标
        if _ICON_FONT:
            ic = QLabel("\uE765")
            ic.setFont(_make_font(_ICON_FONT, 20))
        else:
            ic = QLabel("\U0001F4C4")
        ic.setStyleSheet("color: #E0E0E0; background: transparent;")
        ic.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(ic)

        # 名称
        self._prof_name_lbl = QLabel("Default")
        self._prof_name_lbl.setFont(_make_font(fn, 16))
        self._prof_name_lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        self._prof_name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self._prof_name_lbl, 1)

        # 下拉箭头
        if _ICON_FONT:
            ar = QLabel("\uE700")
            ar.setFont(_make_font(_ICON_FONT, 14))
        else:
            ar = QLabel("\u2630")
        ar.setStyleSheet("color: #AAA; background: transparent;")
        ar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(ar)

        return btn

    def _build_sq_btn(self, icon_char, fallback, bg, bg_h, fg, signal):
        """36×36 方形图标按钮 (关于/设置/关闭)"""
        btn = QPushButton()
        btn.setFixedSize(40, 40)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            btn.setText(icon_char)
            btn.setFont(_make_font(_ICON_FONT, 20))
        else:
            btn.setText(fallback)
            btn.setFont(_make_font(get_font(), 16, bold=True))
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg}; color: {fg}; border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {bg_h}; }}
        """)
        btn.clicked.connect(signal.emit)
        return btn

    # ── 回调 ─────────────────────────────────────────────────

    def _on_wheel_toggle(self):
        self._wheel_on = not self._wheel_on
        if self._wheel_on:
            self._wheel_btn.set_colors(C_WH_ON, C_WH_ON_H)
            self._wheel_btn.set_icon_text("\uE73E", "\u2611")
        else:
            self._wheel_btn.set_colors(C_GRAY, C_GRAY_H)
            self._wheel_btn.set_icon_text("\uE739", "\u25a3")
        self.wheel_clicked.emit()

    def _on_opacity(self, value):
        self._val_lbl.setText(f"{value}%")
        self.opacity_changed.emit(value / 100.0)

    def _on_grid_changed(self, value):
        """网格滑块回调 — 吸附到 10px 步进"""
        snapped = round(value / 10) * 10
        snapped = max(60, min(100, snapped))
        if snapped != value:
            self._grid_slider.blockSignals(True)
            self._grid_slider.setValue(snapped)
            self._grid_slider.blockSignals(False)
        self._grid_val_lbl.setText(f"{snapped}px")
        self.grid_changed.emit(snapped)

    def set_opacity(self, value: float):
        """外部设置透明度 (0.1~0.9)，同步滑块和标签"""
        int_val = max(10, min(90, int(value * 100)))
        self._slider.blockSignals(True)
        self._slider.setValue(int_val)
        self._slider.blockSignals(False)
        self._val_lbl.setText(f"{int_val}%")

    def set_grid_size(self, gs: int):
        """外部设置网格大小 (60-100)，同步滑块和标签"""
        gs = max(60, min(100, round(gs / 10) * 10))
        self._grid_slider.blockSignals(True)
        self._grid_slider.setValue(gs)
        self._grid_slider.blockSignals(False)
        self._grid_val_lbl.setText(f"{gs}px")

    # ── 定位 ─────────────────────────────────────────────────

    def _position_toolbar(self):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        # 宽度取内容自适应与原版 TOOLBAR_WIDTH 的较大值，但不超出屏幕
        self.adjustSize()
        w = min(max(TOOLBAR_WIDTH, self.sizeHint().width()), screen.width() - 40)
        h = self.sizeHint().height()
        x = (screen.width() - w) // 2
        y = screen.height() - h - TOOLBAR_BOTTOM_MARGIN
        self.setGeometry(x, y, w, h)

    # ── 外部接口 ─────────────────────────────────────────────

    def set_profile_name(self, name: str):
        self._prof_name_lbl.setText(name)

    def set_wheel_state(self, visible: bool):
        """同步轮盘按钮外观 — 配置加载/切换时调用"""
        self._wheel_on = visible
        if visible:
            self._wheel_btn.set_colors(C_WH_ON, C_WH_ON_H)
            self._wheel_btn.set_icon_text("\uE73E", "\u2611")
        else:
            self._wheel_btn.set_colors(C_GRAY, C_GRAY_H)
            self._wheel_btn.set_icon_text("\uE739", "\u25a3")

    # ── Tip 事件过滤器 ───────────────────────────────────────

    def _install_tip(self, widget):
        """为按钮安装 hover 事件过滤器，触发下方 tip 浮窗。"""
        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.Enter:
            tip_text = obj.toolTip()
            if tip_text:
                self._tip.show_tip(tip_text, self)
        elif event.type() == QEvent.Type.Leave:
            self._tip.hide_tip()
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        self._tip.hide_tip()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._tip.close()
        super().closeEvent(event)

    # ── 拖拽 ─────────────────────────────────────────────────

    def mousePressEvent(self, event):
        self.raise_()
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            # 屏幕边缘保护：不允许拖出屏幕
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().geometry()
            x = max(screen.left(), min(new_pos.x(), screen.right() - self.width() + 1))
            y = max(screen.top(), min(new_pos.y(), screen.bottom() - self.height() + 1))
            self.move(x, y)
            self.moved.emit()  # 同步软键盘位置
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)
