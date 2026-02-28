"""
TEGG Touch (PyQt6) - voice_test_dialog.py
语音指令测试弹窗 — 实时声波可视化 + 识别日志。
"""

import struct
import time

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QWidget, QScrollArea, QFrame, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, QElapsedTimer
from PyQt6.QtGui import (
    QFont, QPainter, QPen, QColor, QLinearGradient,
    QPainterPath, QFontDatabase,
)

from core.i18n import t, get_font
from engine.voice_engine import VoiceEngine

# ── 颜色常量 (复用项目风格) ──
C_PM_BG = "#1E1E1E"
C_CYBER = "#00D4FF"
C_CYBER_H = "#00B8E6"
C_CYBER_DIM = "#0891B2"
C_GREEN = "#10B981"
C_AMBER = "#F59E0B"
C_CLOSE = "#3A3A3A"
C_CLOSE_H = "#EF4444"
C_GRAY = "#333333"
C_GRAY_H = "#444444"

# ── 图标字体检测 ──
_ICON_FONT = None

def _detect_icon_font():
    global _ICON_FONT
    if _ICON_FONT is not None:
        return _ICON_FONT
    families = QFontDatabase.families()
    if "Segoe Fluent Icons" in families:
        _ICON_FONT = "Segoe Fluent Icons"
    elif "Segoe MDL2 Assets" in families:
        _ICON_FONT = "Segoe MDL2 Assets"
    else:
        _ICON_FONT = ""
    return _ICON_FONT

def _make_font(name, px, bold=False):
    f = QFont(name)
    f.setPixelSize(px)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


# ── 声波可视化 Widget ──
class _WaveformWidget(QWidget):
    """实时声波可视化 — Cyber 青色渐变"""

    BAR_COUNT = 64         # 柱状条数量
    BAR_GAP = 2            # 间距
    MIN_BAR_H = 2          # 最低柱高 (静默呼吸)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setMinimumWidth(200)
        self._amplitudes = [0.0] * self.BAR_COUNT
        self._target_amps = [0.0] * self.BAR_COUNT
        self._breath_phase = 0.0

        # 平滑动画定时器
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)  # ~30fps
        self._anim_timer.timeout.connect(self._animate)
        self._anim_timer.start()

    def feed_audio(self, pcm_bytes: bytes):
        """接收 PCM int16 数据，计算每个 bar 的振幅"""
        n_samples = len(pcm_bytes) // 2
        if n_samples == 0:
            return
        samples = struct.unpack(f'<{n_samples}h', pcm_bytes)

        # 将样本分到 BAR_COUNT 个桶
        step = max(1, n_samples // self.BAR_COUNT)
        for i in range(self.BAR_COUNT):
            start = i * step
            end = min(start + step, n_samples)
            if start >= n_samples:
                self._target_amps[i] = 0.0
                continue
            chunk = samples[start:end]
            rms = (sum(s * s for s in chunk) / len(chunk)) ** 0.5
            # 归一化到 0~1 (int16 max = 32768)
            self._target_amps[i] = min(1.0, rms / 8000.0)

    def _animate(self):
        """平滑插值 + 呼吸动画"""
        import math
        self._breath_phase += 0.05
        changed = False
        for i in range(self.BAR_COUNT):
            target = self._target_amps[i]
            # 缓慢上升、缓慢衰减
            diff = target - self._amplitudes[i]
            if abs(diff) > 0.001:
                self._amplitudes[i] += diff * 0.3
                changed = True
            # 呼吸最低值
            breath = 0.03 + 0.02 * math.sin(self._breath_phase + i * 0.15)
            if self._amplitudes[i] < breath:
                self._amplitudes[i] = breath
                changed = True
        if changed:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        mid_y = h / 2

        bar_w = max(2, (w - self.BAR_GAP * (self.BAR_COUNT - 1)) / self.BAR_COUNT)
        total_w = bar_w * self.BAR_COUNT + self.BAR_GAP * (self.BAR_COUNT - 1)
        offset_x = (w - total_w) / 2

        for i in range(self.BAR_COUNT):
            amp = self._amplitudes[i]
            bar_h = max(self.MIN_BAR_H, amp * (h * 0.9))
            x = offset_x + i * (bar_w + self.BAR_GAP)
            y = mid_y - bar_h / 2

            # 渐变: 中心 cyan → 边缘 深蓝
            grad = QLinearGradient(x, y, x, y + bar_h)
            alpha = int(180 + 75 * amp)
            grad.setColorAt(0.0, QColor(0, 212, 255, alpha))
            grad.setColorAt(0.5, QColor(8, 145, 178, alpha))
            grad.setColorAt(1.0, QColor(0, 212, 255, int(alpha * 0.5)))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawRoundedRect(int(x), int(y), int(bar_w), int(bar_h), 1, 1)

        # 中线发光
        glow_pen = QPen(QColor(0, 212, 255, 40), 1)
        painter.setPen(glow_pen)
        painter.drawLine(0, int(mid_y), w, int(mid_y))

        painter.end()


# ── 单条日志行 ──
class _LogEntry(QWidget):
    """简洁识别日志行 — 纯文本，撑满宽度"""

    def __init__(self, phrase, keys, action, elapsed_str, latency_ms, fn, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(8)

        phrase_lbl = QLabel(phrase)
        phrase_lbl.setFont(_make_font(fn, 14))
        phrase_lbl.setStyleSheet("color: #CCC; background: transparent;")
        lay.addWidget(phrase_lbl, 4)

        keys_lbl = QLabel(keys or "—")
        keys_lbl.setFont(_make_font(fn, 14))
        keys_lbl.setStyleSheet(f"color: {C_AMBER}; background: transparent;")
        lay.addWidget(keys_lbl, 4)

        action_map = {"click": t("voice_dialog.action_click"),
                      "press": t("voice_dialog.action_press"),
                      "release": t("voice_dialog.action_release")}
        action_lbl = QLabel(action_map.get(action, action))
        action_lbl.setFont(_make_font(fn, 14))
        action_lbl.setStyleSheet(f"color: {C_CYBER}; background: transparent;")
        lay.addWidget(action_lbl, 2)

        time_lbl = QLabel(elapsed_str)
        time_lbl.setFont(_make_font(fn, 14))
        time_lbl.setStyleSheet("color: #666; background: transparent;")
        lay.addWidget(time_lbl, 2)

        lat_lbl = QLabel(f"{latency_ms}ms")
        lat_lbl.setFont(_make_font(fn, 14))
        lat_lbl.setStyleSheet("color: #666; background: transparent;")
        lay.addWidget(lat_lbl, 2)


# ── 主弹窗 ──
class VoiceTestDialog(QDialog):
    """语音指令测试弹窗 — 声波 + 识别日志"""

    WIN_W = 620
    WIN_H = 600
    PAD = 20

    def __init__(self, commands, language, parent=None):
        super().__init__(parent)
        self._commands = commands
        self._language = language
        self._engine = None
        self._count = 0
        self._elapsed = QElapsedTimer()
        self._drag_pos = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIN_W, self.WIN_H)

        _detect_icon_font()
        self._init_ui()
        self._center_on_screen()

        # 运行计时器
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._update_clock)

        # 打开后自动开始
        QTimer.singleShot(100, self._start_test)

    def _init_ui(self):
        fn = get_font()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("vt_container")
        container.setStyleSheet(f"""
            QFrame#vt_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(self.PAD, self.PAD, self.PAD, self.PAD)
        root.setSpacing(12)

        # ── Title bar ──
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        icon_lbl = QLabel("\uE720" if _ICON_FONT else "\U0001F3AF")
        if _ICON_FONT:
            icon_lbl.setFont(_make_font(_ICON_FONT, 20))
        else:
            icon_lbl.setFont(_make_font(fn, 20))
        icon_lbl.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(icon_lbl)

        title_lbl = QLabel(t("voice_test.title"))
        title_lbl.setFont(_make_font(fn, 18, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        # 状态指示灯
        self._status_dot = QLabel("●")
        self._status_dot.setFont(_make_font(fn, 14))
        self._status_dot.setStyleSheet(f"color: {C_AMBER}; background: transparent;")
        title_row.addWidget(self._status_dot)

        self._status_lbl = QLabel(t("voice_test.loading"))
        self._status_lbl.setFont(_make_font(fn, 13))
        self._status_lbl.setStyleSheet("color: #AAA; background: transparent;")
        title_row.addWidget(self._status_lbl)
        title_row.addSpacing(8)

        close_btn = QPushButton("\uE711" if _ICON_FONT else "\u2715")
        close_btn.setFixedSize(36, 36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setFont(_make_font(_ICON_FONT, 18))
        else:
            close_btn.setFont(_make_font(fn, 16, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.close)
        title_row.addWidget(close_btn)
        root.addLayout(title_row)

        # ── 声波可视化 ──
        self._waveform = _WaveformWidget()
        self._waveform.setStyleSheet(f"""
            background: #141414;
            border: 1px solid #333;
            border-radius: 8px;
        """)
        root.addWidget(self._waveform)

        # ── 提示文字 ──
        self._hint_lbl = QLabel(t("voice_test.hint"))
        self._hint_lbl.setFont(_make_font(fn, 13))
        self._hint_lbl.setStyleSheet("color: #666; background: transparent;")
        self._hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._hint_lbl)

        # ── 表头 ──
        header = QHBoxLayout()
        header.setContentsMargins(8, 0, 8, 0)
        header.setSpacing(8)
        for text, stretch in [
            (t("voice_test.col_cmd"), 4),
            (t("voice_test.col_keys"), 4),
            (t("voice_test.col_action"), 2),
            (t("voice_test.col_time"), 2),
            (t("voice_test.col_latency"), 2),
        ]:
            lbl = QLabel(text)
            lbl.setFont(_make_font(fn, 14))
            lbl.setStyleSheet("color: #555; background: transparent;")
            header.addWidget(lbl, stretch)
        root.addLayout(header)

        # 分割线
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #333;")
        root.addWidget(sep)

        # ── 日志滚动区域 ──
        self._log_scroll = QScrollArea()
        self._log_scroll.setWidgetResizable(True)
        self._log_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._log_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 6px; border: none;
            }
            QScrollBar::handle:vertical {
                background: #404040; border-radius: 3px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        self._log_content = QWidget()
        self._log_content.setStyleSheet("background: transparent;")
        self._log_layout = QVBoxLayout(self._log_content)
        self._log_layout.setContentsMargins(0, 0, 0, 0)
        self._log_layout.setSpacing(10)
        self._log_layout.addStretch()
        self._log_scroll.setWidget(self._log_content)
        root.addWidget(self._log_scroll, 1)

        # ── 底部状态栏 ──
        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        self._count_lbl = QLabel(t("voice_test.count").replace("{n}", "0"))
        self._count_lbl.setFont(_make_font(fn, 13))
        self._count_lbl.setStyleSheet("color: #888; background: transparent;")
        bottom.addWidget(self._count_lbl)

        sep2 = QLabel("┊")
        sep2.setFont(_make_font(fn, 13))
        sep2.setStyleSheet("color: #444; background: transparent;")
        bottom.addWidget(sep2)

        self._time_lbl = QLabel(t("voice_test.runtime").replace("{time}", "00:00"))
        self._time_lbl.setFont(_make_font(fn, 13))
        self._time_lbl.setStyleSheet("color: #888; background: transparent;")
        bottom.addWidget(self._time_lbl)

        bottom.addStretch()

        stop_btn = QPushButton(t("voice_test.stop"))
        stop_btn.setFixedHeight(36)
        stop_btn.setFixedWidth(120)
        stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        stop_btn.setFont(_make_font(fn, 14, bold=True))
        stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #E0E0E0;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; color: #FFF; }}
        """)
        stop_btn.clicked.connect(self.close)
        bottom.addWidget(stop_btn)
        root.addLayout(bottom)

    # ── 引擎控制 ──

    def _start_test(self):
        """启动语音引擎（仅识别，不执行按键）"""
        if not self._commands:
            self._status_dot.setStyleSheet("color: #EF4444; background: transparent;")
            self._status_lbl.setText(t("voice_test.no_commands"))
            return

        self._engine = VoiceEngine(self)
        self._engine.command_recognized.connect(self._on_command)
        self._engine.audio_data_ready.connect(self._waveform.feed_audio)
        self._engine.status_changed.connect(self._on_status)
        self._engine.error_occurred.connect(self._on_error)
        self._engine.start(self._commands, self._language)
        self._elapsed.start()
        self._clock_timer.start()

    def _on_command(self, phrase, keys, action, latency_ms=0):
        """识别到指令 → 添加日志行"""
        self._count += 1
        elapsed_ms = self._elapsed.elapsed()
        mins = elapsed_ms // 60000
        secs = (elapsed_ms % 60000) // 1000
        elapsed_str = f"{mins:02d}:{secs:02d}"

        fn = get_font()
        entry = _LogEntry(phrase, keys, action, elapsed_str, latency_ms, fn)

        # 插入到 stretch 之前
        idx = self._log_layout.count() - 1
        self._log_layout.insertWidget(idx, entry)

        # 自动滚动到底部
        QTimer.singleShot(50, lambda: self._log_scroll.verticalScrollBar().setValue(
            self._log_scroll.verticalScrollBar().maximum()))

        # 更新计数
        self._count_lbl.setText(
            t("voice_test.count").replace("{n}", str(self._count)))

        # 隐藏提示
        self._hint_lbl.hide()

    def _on_status(self, status_key):
        if status_key == "voice.status_listening":
            self._status_dot.setStyleSheet(f"color: {C_GREEN}; background: transparent;")
            self._status_lbl.setText(t("voice_test.listening"))
        elif status_key == "voice.status_loading":
            self._status_dot.setStyleSheet(f"color: {C_AMBER}; background: transparent;")
            self._status_lbl.setText(t("voice_test.loading"))
        elif status_key == "voice.status_stopped":
            self._status_dot.setStyleSheet("color: #666; background: transparent;")
            self._status_lbl.setText(t("voice_test.stopped"))

    def _on_error(self, error_key):
        self._status_dot.setStyleSheet("color: #EF4444; background: transparent;")
        # 简化错误显示
        if ":" in error_key:
            _, detail = error_key.split(":", 1)
            self._status_lbl.setText(detail[:30])
        else:
            self._status_lbl.setText(t("voice_test.error"))

    def _update_clock(self):
        if self._elapsed.isValid():
            elapsed_ms = self._elapsed.elapsed()
            mins = elapsed_ms // 60000
            secs = (elapsed_ms % 60000) // 1000
            self._time_lbl.setText(
                t("voice_test.runtime").replace("{time}", f"{mins:02d}:{secs:02d}"))

    def _cleanup(self):
        """清理资源（不调用 self.close()，由 closeEvent 调用）"""
        self._clock_timer.stop()
        if self._engine:
            self._engine.stop()
            self._engine = None

    # ── 定位 ──

    def _center_on_screen(self):
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    # ── 拖拽 ──

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def closeEvent(self, event):
        self._cleanup()
        super().closeEvent(event)
