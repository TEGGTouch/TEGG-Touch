"""
TEGG Touch (PyQt6) - ai_assistant_dialog.py
AI 蛋挞 配置助手 — 文本对话面板 (阶段1)。

用自然语言让 MiniMax-M3 帮忙读取/修改蛋挞按键配置。窗口持有对外部 AgentThread
的引用 (由 OverlayWindow 创建并持久化, 保留多轮会话历史)。

面板特性:
- **常驻**: OverlayWindow 创建一次并 hide/show; 运行/编辑模式都在, 切模式不消失,
  直到用户点「收起」。
- **可拖动 (标题栏) + 可缩放 (右下角手柄)**: 均钳制在屏幕内 + 持久化。
- **位置/尺寸持久化**: 存 settings/agent.json。
- 对话用 QTextEdit 富文本; 蛋挞回复走轻量 Markdown → HTML。

配置改动经 AgentThread.config_changed → OverlayWindow.reload_active_profile() 热生效。
"""

import html
import os
import re

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QWidget,
    QLabel, QFrame, QTextEdit, QLineEdit, QApplication, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase, QPixmap, QPen, QColor, QPainter, QTextCursor

from core.i18n import get_font
from core.constants import APP_DIR
from core import agent_settings
from core.shadow_helper import SHADOW_MARGIN, SHADOW_BLUR, SHADOW_OFFSET_Y, SHADOW_COLOR
from agent import conversation_log as clog
from agent import safety

# 图标字体 (软键盘同款: Segoe MDL2/Fluent, 无则退回 ▲)
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


# ── 颜色 ──
C_BG = "#1E1E1E"
C_USER = "#38BDF8"      # 你: 蓝 (标签 + 正文都蓝)
C_ASSIST = "#E8E8E8"    # 蛋挞正文
C_BOT = "#F59E0B"       # 蛋挞名 / 参数修改行: 琥珀
C_ERR = "#EF4444"       # 错误: 红
C_DIM = "#8A8A8A"
C_CODE_FG = "#22C55E"   # 行内代码: 绿字 (无底色, 复用之前参数绿)
C_SEND = "#D97706"      # 发送按钮: 与启动按钮同款深橙
C_SEND_H = "#F59E0B"
C_CLOSE = "#3A3A3A"     # 收起按钮: 灰 (仿软键盘)
C_CLOSE_H = "#4A4A4A"
C_INPUT_BG = "#2A2A2A"


def _md_to_html(text: str) -> str:
    """把模型常用的轻量 Markdown 转成富文本 HTML。

    覆盖: **粗体**、`行内代码`、# 标题(降级为粗体)、- / * 项目符号、换行。
    斜体(单 *)不处理, 避免与粗体/符号冲突。
    """
    out = html.escape(text)
    out = re.sub(r'`([^`]+)`',
                 rf'<code style="color:{C_CODE_FG};font-family:Consolas,monospace;">\1</code>',
                 out)
    out = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', out)
    lines = []
    for ln in out.split('\n'):
        m = re.match(r'^\s*#{1,6}\s+(.*)$', ln)
        if m:
            lines.append(f'<b>{m.group(1)}</b>')
            continue
        m = re.match(r'^\s*[-*]\s+(.*)$', ln)
        if m:
            lines.append(f'• {m.group(1)}')
            continue
        lines.append(ln)
    return '<br>'.join(lines)


def _make_font(name, px, bold=False):
    f = QFont(name)
    screen = QApplication.primaryScreen()
    dpi = screen.logicalDotsPerInch() if screen else 96.0
    f.setPointSizeF(px * 72.0 / dpi)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


class _DragBar(QWidget):
    """可拖动标题栏: 拖它移动整窗 (frameless 靠这个, 比依赖事件冒泡可靠)。"""

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self._win = win
        self._press = None
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._press is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self._win._move_clamped(e.globalPosition().toPoint() - self._press)
            e.accept()

    def mouseReleaseEvent(self, e):
        if self._press is not None:
            self._press = None
            self._win._persist_geometry()
            e.accept()


class _ResizeGrip(QWidget):
    """右下角缩放手柄 — 自绘 + 自己处理拖拽 resize (QSizeGrip 在半透明 frameless 下不稳)。"""

    SIZE = 20

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self._win = win
        self._press = None
        self._start = None
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#666"))
        pen.setWidth(2)
        p.setPen(pen)
        s = self.SIZE
        for off in (0, 6, 12):
            p.drawLine(s - 3, s - 3 - off, s - 3 - off, s - 3)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._start = (self._win.width(), self._win.height())
            e.accept()

    def mouseMoveEvent(self, e):
        if self._press is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            d = e.globalPosition().toPoint() - self._press
            scr = self._win._screen_rect()
            w = max(self._win.MIN_W, min(self._start[0] + d.x(), scr.width()))
            h = max(self._win.MIN_H, min(self._start[1] + d.y(), scr.height()))
            self._win.resize(w, h)
            e.accept()

    def mouseReleaseEvent(self, e):
        if self._press is not None:
            self._press = None
            self._win._persist_geometry()
            e.accept()


class AIAssistantDialog(QDialog):
    """AI 蛋挞 配置助手 (常驻、可拖动缩放、文本对话)。需传入外部 AgentThread。"""

    DEFAULT_W = 580
    DEFAULT_H = 680
    MIN_W = 380
    MIN_H = 440
    PAD = 18

    collapsed = pyqtSignal()   # 用户点「收起」时发出 (供工具栏同步按钮态)
    voice_wake_toggle_requested = pyqtSignal(bool)   # 蛋挞唤醒词开关变化 (供 OverlayWindow 启停引擎)

    def __init__(self, agent_thread, parent=None, on_before_send=None):
        super().__init__(parent)
        self._thread = agent_thread
        self._on_before_send = on_before_send
        self._drag_pos = None
        self._busy = False
        self._ready = False
        # 退出全局阴影安装器 (它会 setFixedSize + 逐次加边距, 与"可缩放/记忆尺寸"冲突);
        # 本对话框自己在 _init_ui 里装一次阴影 + 固定预留边距。
        self._shadow_installed = True

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(self.MIN_W, self.MIN_H)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._persist_geometry)

        self._init_ui()
        self._restore_geometry()
        self._wire_thread()

        had_history = self._load_history()
        if not agent_settings.is_configured():
            self._append_error(
                "尚未配置 API 密钥。请在 settings/agent.json 里填写 \"api_key\", "
                "或设置环境变量 MINIMAX_API_KEY (国内站 platform.minimaxi.com 申请)。")
            self._input.setEnabled(False)
            self._send_btn.setEnabled(False)
            self._input.setPlaceholderText("配置密钥后重开本窗口…")
            self._status_lbl.setText("未配置")
        elif had_history:
            self._append_system("── 以上为历史记录，可继续对话 ──")
        else:
            self._append_system("你好！我是蛋挞助手，可以帮你改按键配置。例如："
                                "“把第一个按钮的 hover 改成 ctrl+f4”、“把透明度调到 0.5”。")
        self._ready = True
        # 蛋挞唤醒词按钮初始配色 (反映持久化的 voice_wake_enabled)
        self._refresh_wake_btn(
            bool(agent_settings.load_agent_settings().get("voice_wake_enabled", True)))

    # ── UI ──
    def _init_ui(self):
        _detect_icon_font()
        fn = get_font()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)

        container = QFrame()
        container.setObjectName("ai_container")
        container.setStyleSheet(f"""
            QFrame#ai_container {{
                background: {C_BG}; border-radius: 6px; border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)
        self._container = container

        # 自装阴影 (一次性; 不改窗口尺寸 → 不与缩放/记忆尺寸冲突)
        eff = QGraphicsDropShadowEffect(container)
        eff.setBlurRadius(SHADOW_BLUR)
        eff.setOffset(0.0, float(SHADOW_OFFSET_Y))
        eff.setColor(SHADOW_COLOR)
        container.setGraphicsEffect(eff)

        root = QVBoxLayout(container)
        root.setContentsMargins(self.PAD, self.PAD, self.PAD, self.PAD)
        root.setSpacing(12)

        # ── 标题栏 (可拖动: logo + 标题 + 状态 + 收起) ──
        title_bar = _DragBar(self)
        title_row = QHBoxLayout(title_bar)
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        logo = QLabel()
        logo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        _logo_path = os.path.join(APP_DIR, "assets", "icon.ico")
        if os.path.exists(_logo_path):
            pm = QPixmap(_logo_path)
            if not pm.isNull():
                logo.setPixmap(pm.scaled(26, 26, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
        title_row.addWidget(logo)

        title_lbl = QLabel("AI 蛋挞")
        title_lbl.setFont(_make_font(fn, 19, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        title_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        collapse_btn = QPushButton()
        collapse_btn.setFixedSize(34, 34)
        collapse_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        collapse_btn.setAutoDefault(False)
        collapse_btn.setDefault(False)
        collapse_btn.setToolTip("收起面板 (随时可从工具栏 AI 按钮再打开)")
        if _ICON_FONT:
            collapse_btn.setText("")   # ChevronUp
            collapse_btn.setFont(_make_font(_ICON_FONT, 16))
        else:
            collapse_btn.setText("▲")   # ▲ fallback
            collapse_btn.setFont(_make_font(fn, 15, bold=True))
        collapse_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_CLOSE}; color: #DDD; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        collapse_btn.clicked.connect(self._on_collapse)
        title_row.addWidget(collapse_btn)
        root.addWidget(title_bar)

        # ── 对话记录 ──
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(_make_font(fn, 16))
        self._log.setStyleSheet(f"""
            QTextEdit {{
                background: #161616; color: {C_ASSIST};
                border: 1px solid #333; border-radius: 8px; padding: 10px;
            }}
            QScrollBar:vertical {{ background: transparent; width: 8px; border: none; margin: 0; }}
            QScrollBar::handle:vertical {{ background: #404040; border-radius: 4px; min-height: 30px; }}
            QScrollBar::handle:vertical:hover {{ background: #555; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)
        root.addWidget(self._log, 1)

        # (执行确认改为独立弹窗 views/confirm_popup.py, 由 OverlayWindow 收口, 不再内嵌于此)

        # ── 状态行 (输入框上方独占一行: 就绪 / 思考中… + 急停) ──
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self._status_lbl = QLabel("就绪")
        self._status_lbl.setFont(_make_font(fn, 13))
        self._status_lbl.setStyleSheet(f"color: {C_DIM}; background: transparent;")
        status_row.addWidget(self._status_lbl)
        status_row.addStretch()
        from views.edit_toolbar import _IconTextBtn   # 复用体系图标+文字按钮 (icon-font)
        self._stop_btn = _IconTextBtn("", "⏹", "急停", "#3A2A2A", "#EF4444",
                                      fg="#EF4444", height=36)
        self._stop_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # 防回车/空格误触发急停
        self._stop_btn.setToolTip("立即中断 agent 的所有执行 (全局热键: Ctrl+Alt+空格)")
        self._stop_btn.clicked.connect(self._on_stop)
        # 蛋挞唤醒词 toggle (急停左侧; 绿=启用, 灰=关闭) — icon 沿用工具栏语音按钮话筒
        self._wake_btn = _IconTextBtn("", "\U0001F3A4", "蛋挞",
                                      "#2A2A2A", "#3A3A3A", height=36)
        self._wake_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._wake_btn.setToolTip("蛋挞唤醒词 — 开启后说「蛋挞」即可语音输入给 AI")
        self._wake_btn.clicked.connect(self._on_toggle_wake)
        status_row.addWidget(self._wake_btn)
        status_row.addWidget(self._stop_btn)
        root.addLayout(status_row)

        # ── 输入行 (加大) ──
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self._input = QLineEdit()
        self._input.setFont(_make_font(fn, 16))
        self._input.setMinimumHeight(48)
        self._input.setPlaceholderText("说点什么… (回车发送)")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C_INPUT_BG}; color: #EEE;
                border: 1px solid #444; border-radius: 8px; padding: 8px 12px;
            }}
            QLineEdit:focus {{ border: 1px solid {C_SEND}; }}
        """)
        self._input.returnPressed.connect(self._on_send)
        input_row.addWidget(self._input, 1)

        self._send_btn = QPushButton("发送")
        self._send_btn.setFixedSize(100, 48)
        self._send_btn.setAutoDefault(False)
        self._send_btn.setDefault(False)
        self._send_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # 焦点常驻输入框, 按钮只鼠标点
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setFont(_make_font(fn, 16, bold=True))
        self._send_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_SEND}; color: #FFF; border: none; border-radius: 8px; }}
            QPushButton:hover {{ background: {C_SEND_H}; }}
            QPushButton:disabled {{ background: #333; color: #666; }}
        """)
        self._send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self._send_btn)
        root.addLayout(input_row)

        # ── 右下角缩放手柄 ──
        self._grip = _ResizeGrip(self, container)

    # ── 线程接线 (常驻期间保持连接) ──
    def _wire_thread(self):
        self._thread.reply_ready.connect(self._on_reply)
        self._thread.tool_ran.connect(self._on_tool_ran)
        self._thread.error.connect(self._on_error)
        self._thread.busy.connect(self._set_busy)

    # ── 蛋挞唤醒词开关 ──
    def _refresh_wake_btn(self, enabled: bool):
        """按开关状态刷新按钮配色: 绿=启用 (同工具栏语音开), 灰=关闭。"""
        if enabled:
            self._wake_btn.set_colors("#176F2C", "#1E8E38")
        else:
            self._wake_btn.set_colors("#2A2A2A", "#3A3A3A")

    def _on_toggle_wake(self):
        """翻转 voice_wake_enabled: 持久化 + 刷新配色 + 通知 OverlayWindow 启停引擎。"""
        s = agent_settings.load_agent_settings()
        new_val = not s.get("voice_wake_enabled", True)
        s["voice_wake_enabled"] = new_val
        agent_settings.save_agent_settings(s)
        self._refresh_wake_btn(new_val)
        self.voice_wake_toggle_requested.emit(new_val)

    # ── 急停 (确认弹窗由 OverlayWindow 独立管理) ──
    def _on_stop(self):
        """急停: 置位中断 + 解除等待中的确认(若有) + 松开已按住的输入。"""
        safety.request_abort()
        try:
            from core.input_engine import release_all_keys
            release_all_keys()
        except Exception:
            pass
        if safety.confirm_pending():           # 有待确认 → 走收口(关弹窗 + resolve False)
            safety.resolve_pending(False)
        self._append_error("已急停,已中断执行并松开按键。")

    # ── 对外: 打开/收起 ──
    def show_panel(self):
        self._clamp_into_screen()
        self.show()
        self.raise_()
        self.activateWindow()
        agent_settings.save_ui_open(True)   # 记住"已打开", 下次启动恢复
        if self._input.isEnabled():
            self._input.setFocus()

    def _on_collapse(self):
        self._persist_geometry()
        agent_settings.save_ui_open(False)  # 记住"已收起"
        self.hide()
        self.collapsed.emit()

    # ── 收发 ──
    def _on_send(self):
        if self._busy:
            return
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._append_user(text)
        if callable(self._on_before_send):
            try:
                self._on_before_send()
            except Exception:
                pass
        self._thread.ask(text)

    def submit_text(self, text: str) -> bool:
        """程序化提交一条消息 (语音输入用): 等同用户打字并回车。忙时返回 False。"""
        text = (text or "").strip()
        if not text or self._busy:
            return False
        self._input.clear()
        self._append_user(text)
        if callable(self._on_before_send):
            try:
                self._on_before_send()
            except Exception:
                pass
        self._thread.ask(text)
        return True

    def _on_reply(self, text: str):
        self._append_assistant(text)

    def _on_tool_ran(self, info: dict):
        name = info.get("name", "")
        result = info.get("result", {}) or {}
        if not result.get("ok", True) and result.get("error"):
            self._append_tool(f"✗ {name}: {result['error']}", error=True)
            return
        if result.get("screenshot"):   # 截屏: 明确告知用户 (决策#5 知情透明)
            self._append_tool(f"📸 蛋挞看了下屏幕 ({result.get('w')}×{result.get('h')}，不含蛋挞界面)")
            return
        if name in ("run_action", "run_sequence"):   # 执行类
            if result.get("cancelled"):
                self._append_tool(f"✋ 已取消执行: {result.get('value','')}")
            elif result.get("executed") and result.get("ok"):
                self._append_tool(f"▶ 已执行: {result.get('value','')}")
                if result.get("note"):     # 焦点警告 (如没有目标窗口)
                    self._append_tool(result["note"], error=True)
            else:
                self._append_tool(f"✗ 执行失败: {result.get('error') or result.get('value','')}",
                                  error=True)
            return
        if "before" in result and "after" in result:
            field = result.get("field") or result.get("key", "")
            idx = result.get("button_index")
            if idx is None:
                idx = result.get("index")
            tgt = f"按钮{idx} {field}" if idx is not None else f"参数 {field}"
            self._append_tool(f"✓ 已改 {tgt}: {result.get('before')!r} → {result.get('after')!r}")
        else:
            self._append_tool(f"· {name}")

    def _on_error(self, msg: str):
        self._append_error(msg)

    def _set_busy(self, busy: bool):
        self._busy = busy
        self._send_btn.setEnabled(not busy)   # 思考中禁用发送 → 一次一条来回
        self._input.setEnabled(not busy)
        if busy:
            self._status_lbl.setText("● 蛋挞思考中…")
            self._status_lbl.setStyleSheet(f"color: {C_BOT}; background: transparent;")
        else:
            self._status_lbl.setText("就绪")
            self._status_lbl.setStyleSheet(f"color: {C_DIM}; background: transparent;")
        if not busy and self.isVisible():
            self._input.setFocus()

    # ── 追加消息 (HTML) ──
    # 段落上间距: 消息(你/蛋挞) 间距要明显大于蛋挞长回复内部的换行行距
    GAP_MSG = 18      # 一轮消息之间 (你 / 蛋挞)
    GAP_TOOL = 12     # 参数修改 / 工具执行行 (也要与上文拉开)
    GAP_NOTE = 12     # 系统提示 / 错误 / 分隔线

    def _append(self, html_str: str, center: bool = False, top_margin: int = GAP_MSG):
        self._log.append(html_str)
        # 显式设定本段对齐 + 上间距 (对齐: 防居中分隔线让后续继承居中; 间距: 拉开消息)
        cur = self._log.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        fmt = cur.blockFormat()
        fmt.setAlignment(Qt.AlignmentFlag.AlignHCenter if center
                         else Qt.AlignmentFlag.AlignLeft)
        fmt.setTopMargin(float(top_margin))
        cur.setBlockFormat(fmt)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _append_user(self, text: str):
        self._append(f'<b style="color:{C_USER};">你: </b>'
                     f'<span style="color:{C_USER};">{html.escape(text)}</span>',
                     top_margin=self.GAP_MSG)

    def _append_assistant(self, text: str):
        self._append(f'<b style="color:{C_BOT};">蛋挞: </b>'
                     f'<span style="color:{C_ASSIST};">{_md_to_html(text)}</span>',
                     top_margin=self.GAP_MSG)

    def _append_tool(self, text: str, error: bool = False):
        color = C_ERR if error else C_BOT   # 参数修改行用蛋挞同款琥珀
        self._append(f'<span style="color:{color};font-size:14px;">'
                     f'{html.escape(text)}</span>',
                     top_margin=self.GAP_TOOL)

    def _append_system(self, text: str):
        self._append(f'<span style="color:{C_DIM};font-style:italic;">'
                     f'{html.escape(text)}</span>', top_margin=self.GAP_NOTE)

    def _append_error(self, text: str):
        self._append(f'<span style="color:{C_ERR};">⚠ {html.escape(text)}</span>',
                     top_margin=self.GAP_NOTE)

    def _append_session_sep(self, ts: str = ""):
        label = f"── 会话 {ts} ──" if ts else "── 新会话 ──"
        self._append(f'<span style="color:{C_DIM};font-size:13px;">{html.escape(label)}</span>',
                     center=True, top_margin=self.GAP_NOTE)

    # ── 历史回看 ──
    def _load_history(self) -> bool:
        events = clog.load_recent()
        rendered = False
        for ev in events:
            t = ev.get("type")
            if t == "session":
                self._append_session_sep(ev.get("ts", ""))
            elif t == "user":
                self._append_user(ev.get("text", ""))
                rendered = True
            elif t == "assistant":
                self._append_assistant(ev.get("text", ""))
                rendered = True
            elif t == "tool":
                self._on_tool_ran({"name": ev.get("name", ""), "result": ev.get("result", {})})
                rendered = True
            elif t == "error":
                self._append_error(ev.get("text", ""))
                rendered = True
        return rendered

    # ── 几何: 恢复 / 钳制 / 持久化 ──
    def _screen_rect(self) -> QRect:
        scr = QApplication.primaryScreen()
        return scr.availableGeometry() if scr else QRect(0, 0, 1920, 1080)

    def _restore_geometry(self):
        g = agent_settings.load_ui_geometry()
        scr = self._screen_rect()
        w = int(g.get("dialog_w") or self.DEFAULT_W)
        h = int(g.get("dialog_h") or self.DEFAULT_H)
        w = max(self.MIN_W, min(w, scr.width()))
        h = max(self.MIN_H, min(h, scr.height()))
        self.resize(w, h)
        if g.get("dialog_x") is not None and g.get("dialog_y") is not None:
            x, y = self._clamp_pos(int(g["dialog_x"]), int(g["dialog_y"]))
        else:
            x = scr.left() + (scr.width() - w) // 2
            y = scr.top() + (scr.height() - h) // 2
        self.move(x, y)

    def _clamp_pos(self, x: int, y: int) -> tuple:
        scr = self._screen_rect()
        w, h = self.width(), self.height()
        x = max(scr.left(), min(x, scr.right() - w + 1))
        y = max(scr.top(), min(y, scr.bottom() - h + 1))
        return x, y

    def _clamp_into_screen(self):
        x, y = self._clamp_pos(self.x(), self.y())
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    def _move_clamped(self, point):
        x, y = self._clamp_pos(point.x(), point.y())
        self.move(x, y)

    def _persist_geometry(self):
        if not self._ready:
            return
        agent_settings.save_ui_geometry(self.x(), self.y(), self.width(), self.height())

    # ── 事件 ──
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_grip", None) is not None and getattr(self, "_container", None) is not None:
            self._grip.move(self._container.width() - self._grip.width() - 3,
                            self._container.height() - self._grip.height() - 3)
            self._grip.raise_()
        if self._ready:
            self._save_timer.start()

    def moveEvent(self, event):
        super().moveEvent(event)
        if self._ready:
            self._save_timer.start()

    def hideEvent(self, event):
        self._persist_geometry()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._persist_geometry()
        super().closeEvent(event)
