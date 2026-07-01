"""
TEGG Touch (PyQt6) - ai_assistant_dialog.py
AI 配置助手聊天窗口 (阶段1)。

用自然语言让 MiniMax-M3 帮忙读取/修改蛋挞按键配置。窗口持有对外部
AgentThread 的引用 (由 OverlayWindow 创建并持久化, 以保留多轮会话历史)。
本窗口只负责: 收发文本、显示工具执行记录与错误、忙碌态禁用输入。

配置改动经 AgentThread.config_changed → OverlayWindow.reload_active_profile() 热生效,
本窗口不直接动 scene/UI (线程规则见 docs/agent-integration-design.md 第5节)。
"""

import html

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFrame, QTextEdit, QLineEdit, QApplication,
)
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QFont

from core.i18n import get_font
from core import agent_settings
from agent import conversation_log as clog

# ── 颜色 (复用项目深色风格) ──
C_BG = "#1E1E1E"
C_USER = "#0EA5E9"      # 用户气泡: 青蓝
C_ASSIST = "#E0E0E0"    # 助手文本
C_TOOL = "#10B981"      # 工具执行: 绿
C_ERR = "#EF4444"       # 错误: 红
C_DIM = "#777"
C_SEND = "#0284C7"
C_SEND_H = "#0EA5E9"
C_CLOSE = "#3A3A3A"
C_CLOSE_H = "#EF4444"
C_INPUT_BG = "#2A2A2A"


def _make_font(name, px, bold=False):
    f = QFont(name)
    screen = QApplication.primaryScreen()
    dpi = screen.logicalDotsPerInch() if screen else 96.0
    f.setPointSizeF(px * 72.0 / dpi)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


class AIAssistantDialog(QDialog):
    """AI 配置助手对话框。需传入外部 AgentThread。"""

    WIN_W = 560
    WIN_H = 640
    PAD = 18

    def __init__(self, agent_thread, parent=None, on_before_send=None):
        super().__init__(parent)
        self._thread = agent_thread
        # 发指令前的主线程回调 (用于把编辑模式下未保存的改动落盘, 让 agent 读到最新)
        self._on_before_send = on_before_send
        self._drag_pos = None
        self._busy = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIN_W, self.WIN_H)

        self._init_ui()
        self._center_on_screen()
        self._wire_thread()

        # 先回渲历史记录 (关窗重开 / 重启后仍可见), 再放开场白 / 无密钥引导
        had_history = self._load_history()

        if not agent_settings.is_configured():
            self._append_error(
                "尚未配置 API 密钥。请在 settings/agent.json 里填写 \"api_key\", "
                "或设置环境变量 MINIMAX_API_KEY (国内站 platform.minimaxi.com 申请)。")
            # 禁用输入直到配置 (非忙碌态, 状态显示"未配置")
            self._input.setEnabled(False)
            self._send_btn.setEnabled(False)
            self._input.setPlaceholderText("配置密钥后重开本窗口…")
            self._status_lbl.setText("未配置")
        elif had_history:
            self._append_system("── 以上为历史记录，可继续对话 ──")
        else:
            self._append_system("你好! 我可以帮你改蛋挞的按键配置。例如: "
                                "“把第一个按钮的 hover 改成 ctrl+f4”、“把透明度调到 0.5”。")

    # ── UI ──
    def _init_ui(self):
        fn = get_font()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("ai_container")   # *_container → 全局阴影自动识别
        container.setStyleSheet(f"""
            QFrame#ai_container {{
                background: {C_BG};
                border-radius: 6px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(self.PAD, self.PAD, self.PAD, self.PAD)
        root.setSpacing(12)

        # ── 标题栏 ──
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_lbl = QLabel("AI 配置助手")
        title_lbl.setFont(_make_font(fn, 17, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        self._status_lbl = QLabel("就绪")
        self._status_lbl.setFont(_make_font(fn, 12))
        self._status_lbl.setStyleSheet(f"color: {C_DIM}; background: transparent;")
        title_row.addWidget(self._status_lbl)
        title_row.addSpacing(6)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(34, 34)
        close_btn.setAutoDefault(False)   # 否则它是 dialog 默认按钮, 回车会误触发→关窗
        close_btn.setDefault(False)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFont(_make_font(fn, 15, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_CLOSE}; color: #FFF; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.close)
        title_row.addWidget(close_btn)
        root.addLayout(title_row)

        # ── 对话记录 ──
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(_make_font(fn, 13))
        self._log.setStyleSheet(f"""
            QTextEdit {{
                background: #161616; color: {C_ASSIST};
                border: 1px solid #333; border-radius: 8px; padding: 8px;
            }}
            QScrollBar:vertical {{ background: transparent; width: 6px; }}
            QScrollBar::handle:vertical {{ background: #404040; border-radius: 3px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        root.addWidget(self._log, 1)

        # ── 输入行 ──
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self._input = QLineEdit()
        self._input.setFont(_make_font(fn, 13))
        self._input.setPlaceholderText("说点什么… (回车发送)")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C_INPUT_BG}; color: #EEE;
                border: 1px solid #444; border-radius: 6px; padding: 8px 10px;
            }}
            QLineEdit:focus {{ border: 1px solid {C_SEND}; }}
        """)
        self._input.returnPressed.connect(self._on_send)
        input_row.addWidget(self._input, 1)

        self._send_btn = QPushButton("发送")
        self._send_btn.setFixedSize(76, 38)
        self._send_btn.setAutoDefault(False)   # 回车统一走 QLineEdit.returnPressed, 避免双发/关窗
        self._send_btn.setDefault(False)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setFont(_make_font(fn, 13, bold=True))
        self._send_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_SEND}; color: #FFF; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_SEND_H}; }}
            QPushButton:disabled {{ background: #333; color: #666; }}
        """)
        self._send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self._send_btn)
        root.addLayout(input_row)

    # ── 线程接线 ──
    def _wire_thread(self):
        self._thread.reply_ready.connect(self._on_reply)
        self._thread.tool_ran.connect(self._on_tool_ran)
        self._thread.error.connect(self._on_error)
        self._thread.busy.connect(self._set_busy)

    def _unwire_thread(self):
        for sig, slot in (
            (self._thread.reply_ready, self._on_reply),
            (self._thread.tool_ran, self._on_tool_ran),
            (self._thread.error, self._on_error),
            (self._thread.busy, self._set_busy),
        ):
            try:
                sig.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    # ── 收发 ──
    def _on_send(self):
        if self._busy:
            return
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._append_user(text)
        # 先把当前 (可能拖动过但未保存的) 编辑状态落盘, 再让 agent 读取最新 profile
        if callable(self._on_before_send):
            try:
                self._on_before_send()
            except Exception:
                pass
        self._thread.ask(text)

    def _on_reply(self, text: str):
        self._append_assistant(text)

    def _on_tool_ran(self, info: dict):
        name = info.get("name", "")
        result = info.get("result", {}) or {}
        if not result.get("ok", True) and result.get("error"):
            self._append_tool(f"✗ {name}: {result['error']}", error=True)
            return
        # set_button_binding / set_param 带 before/after, 显示得人性化
        if "before" in result and "after" in result:
            field = result.get("field") or result.get("key", "")
            idx = result.get("button_index")
            tgt = f"按钮{idx} {field}" if idx is not None else f"参数 {field}"
            self._append_tool(f"✓ 已改 {tgt}: {result.get('before')!r} → {result.get('after')!r}")
        else:
            self._append_tool(f"· {name}")

    def _on_error(self, msg: str):
        self._append_error(msg)

    def _set_busy(self, busy: bool):
        self._busy = busy
        self._send_btn.setEnabled(not busy)
        self._input.setEnabled(not busy)
        self._status_lbl.setText("思考中…" if busy else "就绪")
        if not busy:
            self._input.setFocus()

    # ── 追加气泡 (HTML) ──
    def _append(self, html_str: str):
        self._log.append(html_str)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _append_user(self, text: str):
        self._append(f'<div style="margin:4px 0;"><b style="color:{C_USER};">你: </b>'
                     f'<span style="color:#DDD;">{html.escape(text)}</span></div>')

    def _append_assistant(self, text: str):
        body = html.escape(text).replace("\n", "<br>")
        self._append(f'<div style="margin:4px 0;"><b style="color:#9CA3AF;">助手: </b>'
                     f'<span style="color:{C_ASSIST};">{body}</span></div>')

    def _append_tool(self, text: str, error: bool = False):
        color = C_ERR if error else C_TOOL
        self._append(f'<div style="margin:2px 0 2px 12px;color:{color};font-size:12px;">'
                     f'{html.escape(text)}</div>')

    def _append_system(self, text: str):
        self._append(f'<div style="margin:4px 0;color:{C_DIM};font-style:italic;">'
                     f'{html.escape(text)}</div>')

    def _append_session_sep(self, ts: str = ""):
        label = f"── 会话 {ts} ──" if ts else "── 新会话 ──"
        self._append(f'<div style="margin:10px 0;text-align:center;color:{C_DIM};'
                     f'font-size:11px;">{html.escape(label)}</div>')

    # ── 历史回看 ──
    def _load_history(self) -> bool:
        """把持久化的对话回渲到窗口。返回是否有历史 (决定是否显示开场白)。"""
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
                # 复用实时渲染逻辑 (只读 name/result, 与 tool_ran 一致)
                self._on_tool_ran({"name": ev.get("name", ""), "result": ev.get("result", {})})
                rendered = True
            elif t == "error":
                self._append_error(ev.get("text", ""))
                rendered = True
            # meta (token/模型) 仅供 debug, 不回渲
        return rendered

    def _append_error(self, text: str):
        self._append(f'<div style="margin:4px 0;color:{C_ERR};">⚠ {html.escape(text)}</div>')

    # ── 定位 + 拖拽 ──
    def _center_on_screen(self):
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        self.move((screen.width() - self.width()) // 2,
                  (screen.height() - self.height()) // 2)

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
        # 断开本窗口与外部线程的连接 (线程由 OverlayWindow 持有, 不在此停)
        self._unwire_thread()
        super().closeEvent(event)
