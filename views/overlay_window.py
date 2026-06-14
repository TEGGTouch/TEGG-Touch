"""
TEGG Touch 蛋挞 (PyQt6) - overlay_window.py
全屏透明覆盖窗口 — 替代旧版 FloatingApp。
"""

import logging
import os

from PyQt6.QtWidgets import QGraphicsView, QApplication
from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QPainter, QIcon

from core.i18n import t, load_locale
from core.constants import APP_VERSION, APP_DIR, PT_ON, PT_OFF, PT_BLOCK, DEFAULT_TRANSPARENCY, DEFAULT_GRID_SIZE
from core.system_tuning import frame_interval_ms
from core.config_manager import (
    init_profiles, load_hotkeys, get_active_profile_name,
    load_profile, save_profile, set_active_profile,
)
from core.input_engine import install_wheel_hook, uninstall_wheel_hook, release_all_keys
from scene.overlay_scene import OverlayScene
from engine.run_controller import RunController
from engine.passthrough_manager import PassthroughManager

from views.edit_toolbar import EditToolbar
from views.run_toolbar import RunToolbar, CollapsedBubble
from views.button_editor_dialog import ButtonEditorDialog
from views.center_band_dialog import CenterBandDialog
from views.profile_manager_dialog import ProfileManagerDialog
from views.hotkey_settings_dialog import HotkeySettingsDialog
from views.virtual_keyboard import VirtualKeyboard
from views.voice_settings_dialog import VoiceSettingsDialog
from views.toast_widget import ToastWidget
from views.voice_hud_widget import VoiceHudWidget
from scene.virtual_cursor_item import VirtualCursorItem
from core.constants import BTN_TYPE_CENTER_BAND

logger = logging.getLogger(__name__)


class OverlayWindow(QGraphicsView):
    """全屏透明覆盖窗口 — 替代旧版 FloatingApp"""

    def __init__(self):
        self._scene = OverlayScene()
        super().__init__(self._scene)

        self._current_mode = 'edit'  # 'edit' | 'run'
        self._voice_active = False   # 运行模式中语音开关状态
        self._buttons_hidden = False
        self._profile_name = ''
        self._current_opacity = DEFAULT_TRANSPARENCY

        # 弹窗单例引用 — 防止重复打开
        self._dlg_profile = None
        self._dlg_voice = None
        self._dlg_hotkey = None

        # ── 窗口属性 ──
        self.setWindowTitle(f"{t('app.title')} v{APP_VERSION}")
        _icon_path = os.path.join(APP_DIR, "assets", "icon.ico")
        if os.path.exists(_icon_path):
            self.setWindowIcon(QIcon(_icon_path))

        # 不含 Qt.WindowType.Tool: 让窗口在任务栏出现, 可被最小化
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.setStyleSheet("background: transparent; border: none;")
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

        # ── 全屏尺寸 ──
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        self.setGeometry(screen)
        self._scene.setSceneRect(0, 0, screen.width(), screen.height())

        # ── 引擎初始化 ──
        self._pt_manager = PassthroughManager(self)
        self._run_controller = RunController(self._scene, self)

        # 连接运行控制器信号
        self._run_controller.request_edit_mode.connect(self.to_edit)
        self._run_controller.request_toggle_buttons.connect(self._toggle_buttons_visibility)
        self._run_controller.request_toggle_auto_center.connect(self._toggle_auto_center)
        self._run_controller.request_soft_keyboard.connect(self._toggle_soft_keyboard)
        self._run_controller.passthrough_changed.connect(
            lambda mode: self._pt_manager.set_mode(mode))
        self._run_controller.auto_center_progress.connect(
            self._scene.update_auto_center_bar)
        self._run_controller.cursor_on_ui.connect(
            self._pt_manager.update_smart_passthrough)
        self._run_controller.request_toggle_voice.connect(self._toggle_voice)
        self._run_controller.request_toggle_collapse.connect(self._toggle_collapse_run_toolbar)

        # ── 工具栏 (parent=self ensures Z-order above overlay) ──
        self._edit_toolbar = EditToolbar(parent=self)
        self._run_toolbar = RunToolbar(parent=self)
        self._run_toolbar.hide()

        # 连接编辑工具栏信号
        self._edit_toolbar.add_button_clicked.connect(self._on_add_button)
        self._edit_toolbar.add_center_band_clicked.connect(self._on_add_center_band)
        self._edit_toolbar.voice_clicked.connect(self._open_voice_settings)
        self._edit_toolbar.keyboard_clicked.connect(self._toggle_soft_keyboard)
        self._edit_toolbar.run_clicked.connect(self.to_run)
        self._edit_toolbar.wheel_clicked.connect(self._on_toggle_wheel)
        self._edit_toolbar.opacity_changed.connect(self._on_opacity_changed)
        self._edit_toolbar.grid_changed.connect(self._on_grid_changed)
        self._edit_toolbar.profile_clicked.connect(self._open_profile_manager)
        self._edit_toolbar.settings_clicked.connect(self._open_hotkey_settings)
        self._edit_toolbar.quit_clicked.connect(self.close)
        self._edit_toolbar.minimize_clicked.connect(self.minimize_to_taskbar)
        self._edit_toolbar.sim_mode_change_requested.connect(self._on_sim_mode_change_requested)
        self._edit_toolbar.add_gp_button_clicked.connect(self._on_add_gp_button)
        self._edit_toolbar.add_gp_stick_clicked.connect(self._on_add_gp_stick)
        self._edit_toolbar.gp_wheel_toggle_clicked.connect(self._on_gp_wheel_toggle)

        # 连接运行工具栏信号
        self._run_toolbar.stop_clicked.connect(self.to_edit)
        self._run_toolbar.voice_toggle_clicked.connect(self._toggle_voice)
        self._run_toolbar.auto_center_clicked.connect(self._toggle_auto_center)
        self._run_toolbar.toggle_buttons_clicked.connect(self._toggle_buttons_visibility)
        self._run_toolbar.soft_keyboard_clicked.connect(self._toggle_soft_keyboard)
        self._run_toolbar.pt_clicked.connect(self._on_pt_clicked)
        self._run_toolbar.collapse_clicked.connect(self._collapse_run_toolbar)

        # 折叠悬浮方块
        self._collapsed_bubble = CollapsedBubble(parent=self)
        self._collapsed_bubble.hide()
        self._collapsed_bubble.expand_requested.connect(self._expand_run_toolbar)
        self._run_collapsed = False

        # 工具栏拖拽时同步软键盘位置 (匹配原版 _dm 中的 _position_above_toolbar 调用)
        self._edit_toolbar.moved.connect(self._sync_keyboard_to_toolbar)
        self._run_toolbar.moved.connect(self._sync_keyboard_to_toolbar)

        # 运行工具栏位置持久化
        self._run_toolbar.position_changed.connect(self._on_run_toolbar_moved)

        # 连接穿透变化到运行工具栏更新
        self._run_controller.passthrough_changed.connect(
            self._run_toolbar.update_pt_mode)

        # ── 软键盘 (parent=self ensures Z-order above overlay) ──
        self._virtual_keyboard = VirtualKeyboard(parent=self)
        self._virtual_keyboard.hide()

        # ── Toast 通知 ──
        self._toast = ToastWidget(parent=self)
        self._scene.toast_requested.connect(self._toast.show_toast)

        # ── 语音指令 HUD ──
        self._voice_hud = VoiceHudWidget(parent=self)
        self._run_controller.voice_command_triggered.connect(
            self._voice_hud.show_command)

        # ── 虚拟光标 ──
        from core.constants import DEFAULT_CURSOR_STYLES, DEFAULT_WHEEL_STYLE
        self._cursor_styles = (load_hotkeys() or {}).get(
            'cursor_styles', None) or dict(DEFAULT_CURSOR_STYLES)
        _initial_style = self._cursor_styles.get(
            'cursor', DEFAULT_CURSOR_STYLES['cursor'])
        self._virtual_cursor = VirtualCursorItem('cursor', _initial_style)
        self._virtual_cursor.setVisible(False)
        self._scene.addItem(self._virtual_cursor)

        # ── 方向盘样式 (全局, 跟 cursor 一样存 hotkeys.json) ──
        self._wheel_style = (load_hotkeys() or {}).get(
            'wheel_style', None) or dict(DEFAULT_WHEEL_STYLE)

        # ── 智能穿透轮询定时器 (编辑模式, 跟随显示器刷新率) ──
        self._smart_pt_timer = QTimer(self)
        self._smart_pt_timer.setInterval(frame_interval_ms())
        self._smart_pt_timer.timeout.connect(self._poll_smart_passthrough)

        # 连接场景信号
        self._scene.button_double_clicked.connect(self._open_button_editor)
        self._scene.wheel_rebuilt.connect(self._on_wheel_rebuilt)

        # ── 默认透明度 (与工具栏滑块初始值一致) ──
        self._apply_item_opacity(DEFAULT_TRANSPARENCY)

        # ── 加载配置 ──
        self._load_profile()

        # 连接按钮信号到运行控制器
        self._wire_button_signals()

        # ── 模拟模式 (键盘 / 手柄) 初始化 ──
        # sim_mode 现在 per-profile, 从当前 profile 读; 若 profile 未设置则回退老的全局 hotkeys (一次性迁移)
        _hk = load_hotkeys() or {}
        self._gamepad_install_seen = bool(_hk.get('gamepad_install_seen', False))
        self._sim_mode = self._resolve_sim_mode_from_profile(_hk)
        self._edit_toolbar.set_sim_mode(self._sim_mode)

    def _load_profile(self):
        """加载方案配置，创建场景中的按钮"""
        profile_name, config = init_profiles()
        self._profile_name = profile_name
        # 恢复网格大小 — 必须在 load_from_config 之前设置，
        # 否则 set_grid_size 会对已经正确的坐标做二次比例缩放
        saved_grid = config.get('grid_size', DEFAULT_GRID_SIZE)
        if isinstance(saved_grid, (int, float)):
            saved_grid = max(60, min(100, round(int(saved_grid) / 10) * 10))
        else:
            saved_grid = DEFAULT_GRID_SIZE
        self._scene.grid_size = saved_grid  # 直接赋值，不触发缩放
        self._scene.load_from_config(config)
        self._edit_toolbar.set_profile_name(profile_name)
        self._run_toolbar.set_profile_name(profile_name)
        self._edit_toolbar.set_grid_size(saved_grid)
        # 同步轮盘按钮状态到工具栏
        self._edit_toolbar.set_wheel_state(self._scene.wheel_visible)
        # 同步方向盘 toggle 状态 (profile 加载后, 若已存在 gp_wheel item 则显玫红)
        self._edit_toolbar.set_gp_wheel_state(self._scene.get_gp_wheel_item() is not None)
        # 把当前 wheel_style 应用到 (可能存在的) gp_wheel item
        self._apply_wheel_style_to_current_item()
        # 恢复透明度 (从 profile 读取)
        saved_opacity = config.get('transparency', DEFAULT_TRANSPARENCY)
        if isinstance(saved_opacity, (int, float)):
            saved_opacity = max(0.1, min(0.9, float(saved_opacity)))
        else:
            saved_opacity = DEFAULT_TRANSPARENCY
        self._apply_item_opacity(saved_opacity)
        self._edit_toolbar.set_opacity(saved_opacity)

    def _wire_button_signals(self):
        """将所有按钮的信号连接到运行控制器"""
        for item in self._scene.button_items:
            self._wire_single_item(item)
        self._wire_wheel_signals()

    def _wire_wheel_signals(self):
        """将轮盘扇面和圆环的信号连接到运行控制器"""
        for item in self._scene.wheel_items:
            self._wire_single_item(item)
        for item in self._scene.outer_wheel_items:
            self._wire_single_item(item)
        if self._scene.ring_item:
            self._wire_single_item(self._scene.ring_item)
        if self._scene.inner_ring_item:
            self._wire_single_item(self._scene.inner_ring_item)
        # 中心环/中二环切分模式下的扇区
        for item in self._scene.center_ring_sector_items:
            self._wire_single_item(item)
        for item in self._scene.inner_ring_sector_items:
            self._wire_single_item(item)

    def _wire_single_item(self, item):
        """将单个 Item 的信号连接到运行控制器 (gp_stick 等无 hover 信号的 item 跳过)"""
        if not hasattr(item, 'hoverActivated'):
            return
        item.hoverActivated.connect(self._run_controller.on_hover_activated)
        item.hoverDeactivated.connect(self._run_controller.on_hover_deactivated)
        item.actionTriggered.connect(self._run_controller.on_action_triggered)

    def _on_wheel_rebuilt(self):
        """轮盘重建后:重新连接新 sector/ring item 的信号 + 同步透明度与模式
        修 bug:中心环/中二环切换 mode 时 _rebuild_wheel 会销毁旧 item 重建新 item,
        若不重连信号,新 item 的 actionTriggered 无人接收,视觉触发但按键不发送。"""
        self._wire_wheel_signals()
        self._scene.set_mode(self._current_mode)
        self._apply_item_opacity(self._current_opacity)

    # ── 模式切换 ──

    def to_run(self):
        """切换到运行模式"""
        # 关闭所有编辑模式弹窗
        from PyQt6.QtWidgets import QDialog
        for dlg in self.findChildren(QDialog):
            dlg.close()
        self._smart_pt_timer.stop()
        self._current_mode = 'run'
        self._scene.save_config()
        self._scene.set_mode('run')
        self._pt_manager.set_mode(PT_ON)
        install_wheel_hook()
        self._run_controller.start()

        self._edit_toolbar.hide()
        # 恢复运行工具栏保存的位置
        cfg = self._scene.get_config()
        saved_x = cfg.get('run_toolbar_x') if cfg else None
        saved_y = cfg.get('run_toolbar_y') if cfg else None
        self._run_toolbar.set_saved_position(saved_x, saved_y)
        self._run_toolbar.show()
        self._voice_active = False
        self._run_toolbar.update_voice_state(False)

        # 自动启用语音（如果用户在设置中勾选了"运行时启用音频"）
        cfg_voice = self._scene.get_config() or {}
        if (cfg_voice.get('voice_auto_start', True)
                and cfg_voice.get('voice_commands')):
            if self._check_microphone():
                voice_config = {
                    'voice_enabled': True,
                    'voice_commands': cfg_voice['voice_commands'],
                    'voice_language': cfg_voice.get('voice_language', 'zh-CN'),
                    'voice_mic_device': cfg_voice.get('voice_mic_device', None),
                }
                self._run_controller._start_voice(voice_config)
                self._voice_active = True
                self._run_toolbar.update_voice_state(True)
            else:
                self._toast.show_toast(t("voice_dialog.mic_not_found"))

        self._run_toolbar.update_auto_center(False)
        self._run_toolbar.update_buttons_visibility(False)
        self._run_toolbar.update_pt_mode(PT_ON)

        # 切换工具栏后，重新吸附软键盘到运行工具栏
        if self._virtual_keyboard.isVisible():
            self._virtual_keyboard.position_above_toolbar(self._run_toolbar)

        # 启动虚拟光标跟踪
        self._virtual_cursor.start_tracking()

        logger.info("Entered run mode")

    def to_edit(self):
        """切换到编辑模式"""
        self._current_mode = 'edit'
        self._run_controller.stop()
        uninstall_wheel_hook()
        self._pt_manager.set_mode(PT_OFF)
        self._scene.set_mode('edit')
        self._buttons_hidden = False
        for item in self._scene.button_items:
            item.setVisible(True)
        # 恢复轮盘可见性 (原版 toggle_buttons_visibility 隐藏的轮盘需要恢复)
        for item in self._scene.wheel_items:
            item.setVisible(self._scene.wheel_visible)
        for item in self._scene.outer_wheel_items:
            item.setVisible(self._scene.wheel_visible)
        self._scene._update_ring_visibility()

        self._run_toolbar.hide()
        self._collapsed_bubble.hide()
        self._run_collapsed = False
        self._edit_toolbar.show()
        self._smart_pt_timer.start()

        # 停止虚拟光标和软键盘
        self._virtual_cursor.stop_tracking()
        self._virtual_keyboard.hide()

        logger.info("Entered edit mode")

    # PT 模式 → 光标类型映射
    _PT_CURSOR_MAP = {
        PT_ON: 'cursor',
        PT_OFF: 'cursor_off',
        PT_BLOCK: 'cursor_block',
    }

    def _collapse_run_toolbar(self):
        """折叠运行工具栏为悬浮方块"""
        if self._current_mode != 'run' or self._run_collapsed:
            return
        tb_geo = self._run_toolbar.frameGeometry()
        # 把方块放在原工具栏的左上角附近
        bx = tb_geo.x() + max(0, (tb_geo.width() - CollapsedBubble.SIZE) // 2)
        by = tb_geo.y()
        self._run_toolbar.hide()
        self._collapsed_bubble.show_at(bx, by)
        self._run_collapsed = True

    def _expand_run_toolbar(self):
        """展开运行工具栏"""
        if not self._run_collapsed:
            return
        self._collapsed_bubble.hide()
        self._run_toolbar.show()
        self._run_toolbar.raise_()
        self._run_collapsed = False

    def _toggle_collapse_run_toolbar(self):
        """F10: 折叠/展开切换"""
        if self._current_mode != 'run':
            return
        if self._run_collapsed:
            self._expand_run_toolbar()
        else:
            self._collapse_run_toolbar()

    def _on_pt_clicked(self, mode):
        """工具栏穿透按钮点击 → 同步 manager + toolbar + 光标"""
        self._pt_manager.set_mode(mode)
        self._run_toolbar.update_pt_mode(mode)
        # 同步虚拟光标类型 + 应用对应类型的 style
        cursor_type = self._PT_CURSOR_MAP.get(mode, 'cursor')
        self._virtual_cursor.apply_styles_map(self._cursor_styles, cursor_type)

    def _toggle_buttons_visibility(self):
        """隐藏/显示所有按钮（含轮盘扇区和圆环 — 匹配原版 toggle_buttons_visibility）"""
        self._buttons_hidden = not self._buttons_hidden
        for item in self._scene.button_items:
            item.setVisible(not self._buttons_hidden)
        # 轮盘扇区也参与隐藏 (原版: self.buttons_hidden 影响整个 handle_run_interaction)
        for item in self._scene.wheel_items:
            if self._buttons_hidden:
                item.setVisible(False)
            else:
                item.setVisible(self._scene.wheel_visible)
        for item in self._scene.outer_wheel_items:
            if self._buttons_hidden:
                item.setVisible(False)
            else:
                item.setVisible(self._scene.wheel_visible)
        if self._buttons_hidden:
            if self._scene.ring_item:
                self._scene.ring_item.setVisible(False)
            if self._scene.inner_ring_item:
                self._scene.inner_ring_item.setVisible(False)
            for it in self._scene.center_ring_sector_items:
                it.setVisible(False)
            for it in self._scene.inner_ring_sector_items:
                it.setVisible(False)
        else:
            self._scene._update_ring_visibility()
        self._run_toolbar.update_buttons_visibility(self._buttons_hidden)

    @staticmethod
    def _check_microphone() -> bool:
        """检测是否有可用的麦克风输入设备（sounddevice 优先，pyaudio 回退）"""
        try:
            import sounddevice as sd
            devs = sd.query_devices()
            return any(d.get('max_input_channels', 0) > 0 for d in devs)
        except ImportError:
            pass
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            for i in range(pa.get_device_count()):
                if pa.get_device_info_by_index(i).get('maxInputChannels', 0) > 0:
                    pa.terminate()
                    return True
            pa.terminate()
            return False
        except Exception:
            return False

    def _toggle_voice(self):
        """运行模式中切换语音识别开关"""
        config = self._scene.get_config() or {}
        commands = config.get('voice_commands', [])
        language = config.get('voice_language', 'zh-CN')

        if self._voice_active:
            # 关闭语音
            self._run_controller._stop_voice()
            self._voice_active = False
            self._run_toolbar.update_voice_state(False)
            logger.info("Voice recognition disabled")
        else:
            # 开启语音 — 检查是否有配置指令
            if not commands:
                self._toast.show_toast(t("voice.error_no_commands"))
                logger.warning("Voice toggle: no commands configured")
                return
            # 检查麦克风
            if not self._check_microphone():
                self._toast.show_toast(t("voice_dialog.mic_not_found"))
                logger.warning("Voice toggle: no microphone detected")
                return
            voice_config = {
                'voice_enabled': True,
                'voice_commands': commands,
                'voice_language': language,
                'voice_mic_device': config.get('voice_mic_device', None),
            }
            self._run_controller._start_voice(voice_config)
            self._voice_active = True
            self._run_toolbar.update_voice_state(True)
            logger.info("Voice recognition enabled: %d commands", len(commands))

    def _toggle_auto_center(self):
        """切换自动回中"""
        self._run_controller.auto_center = not self._run_controller.auto_center
        self._run_toolbar.update_auto_center(self._run_controller.auto_center)

    def _toggle_soft_keyboard(self):
        """切换软键盘 — 吸附在当前活动工具栏上方 (匹配原版 toggle_soft_keyboard)"""
        if self._virtual_keyboard.isVisible():
            self._virtual_keyboard.hide()
        else:
            # 绑定到当前可见的工具栏
            toolbar = (self._run_toolbar if self._current_mode == 'run'
                       else self._edit_toolbar)
            self._virtual_keyboard.position_above_toolbar(toolbar)
            self._virtual_keyboard.show()

    def _sync_keyboard_to_toolbar(self):
        """工具栏拖拽时同步软键盘位置"""
        if self._virtual_keyboard.isVisible():
            self._virtual_keyboard.position_above_toolbar()

    def _on_run_toolbar_moved(self, x, y):
        """运行工具栏拖拽结束 → 将位置持久化到 config"""
        if self._scene.get_config():
            self._scene.get_config()['run_toolbar_x'] = x
            self._scene.get_config()['run_toolbar_y'] = y

    # ── 模拟模式 (键盘 / 手柄) ──

    def _on_sim_mode_change_requested(self, mode: str):
        """工具栏请求切换模式。切到 gamepad 时:
           - READY_OK → 静默切换 (无弹窗)
           - 任何需要用户决策的状态 (要装/更新/损坏/需重启) → 弹窗
        """
        if mode == self._sim_mode:
            return
        if mode == 'gamepad':
            from core.gamepad_install import detect_status, Status
            st, _ = detect_status()
            if st != Status.READY_OK:
                from views.gamepad_install_dialog import GamepadInstallDialog
                dlg = GamepadInstallDialog(self)
                ok = (dlg.exec() == dlg.DialogCode.Accepted)
                self._gamepad_install_seen = True
                if not ok:
                    self._persist_sim_mode_flags()
                    return
            else:
                self._gamepad_install_seen = True
        # 应用并持久化
        self._sim_mode = mode
        self._edit_toolbar.set_sim_mode(mode)
        self._persist_sim_mode_flags()

    # ── 手柄模式三类按钮添加 ──

    def _on_add_gp_button(self):
        """添加手柄键 — 调 scene factory, 创建 TouchButtonItem (btn_type=gp_button)"""
        item = self._scene.add_gp_button()
        if item:
            item.setOpacity(self._current_opacity)
            self._wire_single_item(item)

    def _on_add_gp_stick(self):
        """添加摇杆 — 调 scene factory, 创建 GpStickItem"""
        item = self._scene.add_gp_stick()
        if item:
            item.setOpacity(self._current_opacity)

    def _on_gp_wheel_toggle(self):
        """方向盘 toggle (单例) — 有就删, 没就建; 同步 toolbar 状态"""
        visible = self._scene.toggle_gp_wheel()
        # toggle 操作刚翻了 toolbar 状态, 但 scene 才是真相, 这里用 set_xxx_state 强同步
        self._edit_toolbar.set_gp_wheel_state(visible)
        if visible:
            wheel = self._scene.get_gp_wheel_item()
            if wheel:
                wheel.setOpacity(self._current_opacity)
                wheel.apply_style(self._wheel_style)
        self._scene.save_config()

    def _apply_wheel_style_to_current_item(self):
        """把当前 wheel_style 应用到 (可能存在的) gp_wheel item; 设置改动 & profile 加载后调"""
        wheel = self._scene.get_gp_wheel_item()
        if wheel:
            wheel.apply_style(self._wheel_style)

    def _resolve_sim_mode_from_profile(self, hotkeys: dict) -> str:
        """从当前 profile 读 sim_mode; 无则回退老 hotkeys (迁移), 仍无则 'keyboard'。
        若走了迁移, 顺手写回 profile config, 下次 save 即落盘。"""
        cfg = self._scene.get_config() or {}
        sm = cfg.get('sim_mode')
        if sm in ('keyboard', 'gamepad'):
            return sm
        legacy = (hotkeys or {}).get('sim_mode')
        if legacy in ('keyboard', 'gamepad'):
            cfg['sim_mode'] = legacy  # 写回, 后续保存到 profile
            return legacy
        return 'keyboard'

    def _persist_sim_mode_flags(self):
        """sim_mode 写到当前 profile, gamepad_install_seen 仍走全局 hotkeys。"""
        try:
            cfg = self._scene.get_config()
            if cfg is not None:
                cfg['sim_mode'] = self._sim_mode
                self._scene.save_config()
        except Exception as e:
            logger.warning(f"保存 sim_mode 到 profile 失败: {e}")
        try:
            from core.config_manager import save_hotkeys
            save_hotkeys({'gamepad_install_seen': self._gamepad_install_seen})
        except Exception as e:
            logger.warning(f"保存 gamepad_install_seen 失败: {e}")

    # ── 编辑操作 ──

    def _on_add_button(self):
        """工具栏添加按钮"""
        item = self._scene.add_button()
        if item:
            item.setOpacity(self._current_opacity)
            self._wire_single_item(item)

    def _on_add_center_band(self):
        """工具栏添加回中带"""
        item = self._scene.add_center_band()
        if item:
            item.setOpacity(self._current_opacity)
            self._wire_single_item(item)

    def _on_toggle_wheel(self):
        """切换轮盘显示"""
        visible = self._scene.toggle_wheel()
        # Bug 8 fix: 同步工具栏轮盘按钮状态
        self._edit_toolbar.set_wheel_state(visible)

    def _on_grid_changed(self, gs):
        """网格滑块回调 — 缩放按钮并持久化"""
        self._scene.set_grid_size(gs)
        if self._scene.get_config():
            self._scene.get_config()['grid_size'] = gs

    def _on_opacity_changed(self, value):
        """编辑模式背景透明度调整 — 仅影响按钮/轮盘，不影响虚拟光标"""
        # value: 0.1 ~ 0.9 (来自滑块 10%-90%)
        self._apply_item_opacity(value)
        # 持久化到 config（下次 save_config 时写入文件）
        if self._scene.get_config():
            self._scene.get_config()['transparency'] = value

    def _apply_item_opacity(self, value):
        """对按钮和轮盘设置透明度，虚拟光标和进度条保持完全不透明"""
        self._current_opacity = value
        for item in self._scene.button_items:
            item.setOpacity(value)
        for item in self._scene.wheel_items:
            item.setOpacity(value)
        for item in self._scene.outer_wheel_items:
            item.setOpacity(value)
        if self._scene.ring_item:
            self._scene.ring_item.setOpacity(value)
        if self._scene.inner_ring_item:
            self._scene.inner_ring_item.setOpacity(value)
        for it in self._scene.center_ring_sector_items:
            it.setOpacity(value)
        for it in self._scene.inner_ring_sector_items:
            it.setOpacity(value)

    # ── 弹窗 ──

    def _open_button_editor(self, item):
        """打开按钮编辑弹窗 — 按 btn_type 派发: 回中带 / 摇杆 / 其他 (kb + gp_btn)"""
        if hasattr(item.data, 'btn_type') and item.data.btn_type == BTN_TYPE_CENTER_BAND:
            dialog = CenterBandDialog(item, self)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.deleted.connect(lambda it: self._on_button_deleted(it))
            dialog.copied.connect(lambda it: self._on_button_copied(it))
            dialog.show()
            return
        # 摇杆: 左右双栏编辑器 (参数 + 鼠标动作; 右栏 gp 键 + gp 宏)
        from core.constants import BTN_TYPE_GP_STICK, BTN_TYPE_GP_WHEEL
        if hasattr(item.data, 'btn_type') and item.data.btn_type == BTN_TYPE_GP_STICK:
            from views.gp_stick_editor_dialog import GpStickEditorDialog
            cfg = self._scene.get_config()
            gp_macros = cfg.get('gp_macros', [])
            dialog = GpStickEditorDialog(item, self, gp_macros=gp_macros)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.saved.connect(lambda it: self._on_button_saved(it))
            dialog.deleted.connect(lambda it: self._on_button_deleted(it))
            dialog.copied.connect(lambda it: self._on_button_copied(it))
            dialog.show()
            return
        # 方向盘: 单栏编辑器 (参数 + LT/RT 模式), 删除时同步 toolbar toggle
        if hasattr(item.data, 'btn_type') and item.data.btn_type == BTN_TYPE_GP_WHEEL:
            from views.gp_wheel_editor_dialog import GpWheelEditorDialog
            dialog = GpWheelEditorDialog(item, self)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.saved.connect(lambda it: self._on_button_saved(it))
            dialog.deleted.connect(lambda it: self._on_gp_wheel_deleted(it))
            dialog.show()
            return
        cfg = self._scene.get_config()
        macros = cfg.get('macros', [])
        gp_macros = cfg.get('gp_macros', [])
        dialog = ButtonEditorDialog(item, self, macros=macros, gp_macros=gp_macros)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.macros_changed.connect(self._on_macros_changed)
        dialog.gp_macros_changed.connect(self._on_gp_macros_changed)
        dialog.saved.connect(lambda data: self._on_button_saved(item))
        dialog.deleted.connect(lambda it: self._on_button_deleted(it))
        dialog.copied.connect(lambda it: self._on_button_copied(it))
        dialog.show()

    def _on_button_saved(self, item):
        """按钮编辑保存后"""
        item.update()
        self._scene.save_config()

    def _on_button_deleted(self, item):
        """按钮删除后"""
        self._scene.delete_button(item)
        self._scene.save_config()

    def _on_gp_wheel_deleted(self, item):
        """方向盘从编辑器删除 — 同步 toolbar toggle 灰回去"""
        self._scene.delete_button(item)
        self._edit_toolbar.set_gp_wheel_state(False)
        self._scene.save_config()

    def _on_button_copied(self, item):
        """按钮复制后"""
        new_item = self._scene.copy_button(item)
        if new_item:
            self._wire_single_item(new_item)
            self._scene.save_config()

    def _on_macros_changed(self, macros_list):
        """键盘宏列表变更 → 写入 config 并保存"""
        if self._scene.get_config() is not None:
            self._scene.get_config()['macros'] = macros_list
            self._scene.save_config()
            logger.info("Macros updated: %d macros", len(macros_list))

    def _on_gp_macros_changed(self, gp_macros_list):
        """手柄宏列表变更 → 写入 config 并保存"""
        if self._scene.get_config() is not None:
            self._scene.get_config()['gp_macros'] = gp_macros_list
            self._scene.save_config()
            logger.info("GP Macros updated: %d macros", len(gp_macros_list))

    def _on_dialog_destroyed(self, attr_name):
        """弹窗销毁时清理引用的统一槽方法"""
        setattr(self, attr_name, None)

    def _open_profile_manager(self):
        """打开方案管理弹窗"""
        if self._dlg_profile and self._dlg_profile.isVisible():
            self._dlg_profile.raise_()
            self._dlg_profile.activateWindow()
            return
        dialog = ProfileManagerDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.destroyed.connect(lambda: self._on_dialog_destroyed('_dlg_profile'))
        dialog.profile_switched.connect(self._on_profile_switched)
        self._dlg_profile = dialog
        dialog.show()

    def _on_profile_switched(self, name):
        """方案切换"""
        # 保存当前方案
        self._scene.save_config()
        # Bug 1 fix: 更新索引文件中的活跃方案名（必须在保存旧方案之后、加载新方案之前）
        set_active_profile(name)
        # 清空场景中的按钮
        for item in list(self._scene.button_items):
            self._scene.removeItem(item)
        self._scene.button_items.clear()
        # 清空轮盘
        for item in list(self._scene.wheel_items):
            self._scene.removeItem(item)
        self._scene.wheel_items.clear()
        for item in list(self._scene.outer_wheel_items):
            self._scene.removeItem(item)
        self._scene.outer_wheel_items.clear()
        if self._scene.ring_item:
            self._scene.removeItem(self._scene.ring_item)
            self._scene.ring_item = None
        if self._scene.inner_ring_item:
            self._scene.removeItem(self._scene.inner_ring_item)
            self._scene.inner_ring_item = None
        for it in list(self._scene.center_ring_sector_items):
            self._scene.removeItem(it)
        self._scene.center_ring_sector_items.clear()
        for it in list(self._scene.inner_ring_sector_items):
            self._scene.removeItem(it)
        self._scene.inner_ring_sector_items.clear()
        # 加载新方案
        config = load_profile(name)
        self._profile_name = name
        # 恢复网格大小 — 必须在 load_from_config 之前设置，
        # 否则 set_grid_size 会对已经正确的坐标做二次比例缩放
        saved_grid = config.get('grid_size', DEFAULT_GRID_SIZE)
        if isinstance(saved_grid, (int, float)):
            saved_grid = max(60, min(100, round(int(saved_grid) / 10) * 10))
        else:
            saved_grid = DEFAULT_GRID_SIZE
        self._scene.grid_size = saved_grid  # 直接赋值，不触发缩放
        self._scene.load_from_config(config)
        self._wire_button_signals()
        self._edit_toolbar.set_grid_size(saved_grid)
        # 恢复新方案的透明度
        saved_opacity = config.get('transparency', DEFAULT_TRANSPARENCY)
        if isinstance(saved_opacity, (int, float)):
            saved_opacity = max(0.1, min(0.9, float(saved_opacity)))
        else:
            saved_opacity = DEFAULT_TRANSPARENCY
        self._apply_item_opacity(saved_opacity)
        self._edit_toolbar.set_opacity(saved_opacity)
        self._edit_toolbar.set_profile_name(name)
        self._run_toolbar.set_profile_name(name)
        # 同步轮盘按钮状态到工具栏
        self._edit_toolbar.set_wheel_state(self._scene.wheel_visible)
        # 同步方向盘 toggle 状态 (profile 加载后, 若已存在 gp_wheel item 则显玫红)
        self._edit_toolbar.set_gp_wheel_state(self._scene.get_gp_wheel_item() is not None)
        # 把当前 wheel_style 应用到新 profile 的 gp_wheel item (若存在)
        self._apply_wheel_style_to_current_item()
        # 恢复新 profile 的模拟模式 (无则回退全局 hotkeys, 再无则 keyboard)
        from core.config_manager import load_hotkeys
        new_mode = self._resolve_sim_mode_from_profile(load_hotkeys() or {})
        if new_mode != self._sim_mode:
            self._sim_mode = new_mode
        self._edit_toolbar.set_sim_mode(self._sim_mode)

    def _open_voice_settings(self):
        """打开语音指令设置弹窗"""
        if self._dlg_voice and self._dlg_voice.isVisible():
            self._dlg_voice.raise_()
            self._dlg_voice.activateWindow()
            return
        config = self._scene.get_config() or {}
        voice_commands = config.get('voice_commands', [])
        voice_language = config.get('voice_language', None)
        voice_mic_device = config.get('voice_mic_device', None)
        voice_auto_start = config.get('voice_auto_start', True)
        macros = config.get('macros', [])
        dialog = VoiceSettingsDialog(voice_commands, voice_language, voice_mic_device, self, macros=macros, voice_auto_start=voice_auto_start)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.destroyed.connect(lambda: self._on_dialog_destroyed('_dlg_voice'))
        dialog.settings_saved.connect(self._on_voice_settings_saved)
        self._dlg_voice = dialog
        dialog.show()

    def _on_voice_settings_saved(self):
        """语音设置保存后 → 写入 config"""
        dialog = self.sender()
        if dialog and hasattr(dialog, 'get_result'):
            result = dialog.get_result()
            if self._scene.get_config():
                self._scene.get_config()['voice_commands'] = result.get('voice_commands', [])
                self._scene.get_config()['voice_language'] = result.get('voice_language', 'zh-CN')
                self._scene.get_config()['voice_enabled'] = result.get('voice_enabled', False)
                self._scene.get_config()['voice_mic_device'] = result.get('voice_mic_device')
                self._scene.get_config()['voice_auto_start'] = result.get('voice_auto_start', True)
            self._scene.save_config()
            logger.info("Voice settings saved: %d commands", len(result.get('voice_commands', [])))

    def _open_hotkey_settings(self):
        """打开快捷键设置弹窗"""
        if self._dlg_hotkey and self._dlg_hotkey.isVisible():
            self._dlg_hotkey.raise_()
            self._dlg_hotkey.activateWindow()
            return
        dialog = HotkeySettingsDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.destroyed.connect(lambda: self._on_dialog_destroyed('_dlg_hotkey'))
        dialog.settings_saved.connect(self._on_settings_saved)
        dialog.defaults_reset.connect(self._on_defaults_reset)
        dialog.language_changed.connect(self._on_language_changed)
        self._dlg_hotkey = dialog
        dialog.show()

    def _on_settings_saved(self):
        """设置保存后"""
        # 运行控制器重新读取热键
        self._run_controller.reload_hotkeys()
        # 重新加载 cursor_styles 并应用到当前光标
        from core.constants import DEFAULT_CURSOR_STYLES, DEFAULT_WHEEL_STYLE
        from scene.virtual_cursor_item import clear_cursor_render_cache
        from scene.gp_wheel_item import clear_wheel_render_cache
        hk = load_hotkeys() or {}
        self._cursor_styles = hk.get('cursor_styles', None) or dict(DEFAULT_CURSOR_STYLES)
        clear_cursor_render_cache()
        cur_type = getattr(self._virtual_cursor, '_cursor_type', 'cursor')
        self._virtual_cursor.apply_styles_map(self._cursor_styles, cur_type)
        # 重新加载 wheel_style 并应用到当前方向盘 (若存在)
        self._wheel_style = hk.get('wheel_style', None) or dict(DEFAULT_WHEEL_STYLE)
        clear_wheel_render_cache()
        self._apply_wheel_style_to_current_item()

    def _on_defaults_reset(self):
        """设置面板重置默认 → 重置透明度 + 清除运行工具栏保存的位置"""
        from core.constants import DEFAULT_CURSOR_STYLES, DEFAULT_WHEEL_STYLE
        from scene.virtual_cursor_item import clear_cursor_render_cache
        from scene.gp_wheel_item import clear_wheel_render_cache
        self._cursor_styles = dict(DEFAULT_CURSOR_STYLES)
        clear_cursor_render_cache()
        cur_type = getattr(self._virtual_cursor, '_cursor_type', 'cursor')
        self._virtual_cursor.apply_styles_map(self._cursor_styles, cur_type)
        # 方向盘样式同步重置
        self._wheel_style = dict(DEFAULT_WHEEL_STYLE)
        clear_wheel_render_cache()
        self._apply_wheel_style_to_current_item()
        default_opacity = DEFAULT_TRANSPARENCY
        # 重置透明度
        self._apply_item_opacity(default_opacity)
        self._edit_toolbar.set_opacity(default_opacity)
        if self._scene.get_config():
            self._scene.get_config()['transparency'] = default_opacity
        # 清除运行工具栏位置（下次进入运行模式将使用居中默认位置）
        if self._scene.get_config():
            self._scene.get_config()['run_toolbar_x'] = None
            self._scene.get_config()['run_toolbar_y'] = None
        # 重置网格大小
        self._scene.set_grid_size(DEFAULT_GRID_SIZE)
        self._edit_toolbar.set_grid_size(DEFAULT_GRID_SIZE)
        if self._scene.get_config():
            self._scene.get_config()['grid_size'] = DEFAULT_GRID_SIZE
        # 重置运行工具栏到默认居中位置
        self._run_toolbar._position_toolbar()
        logger.info("Defaults reset: transparency=%.2f, grid=%d, run_toolbar position cleared",
                     default_opacity, DEFAULT_GRID_SIZE)

    def _on_language_changed(self, lang):
        """语言切换后刷新 UI"""
        # 重建工具栏（语言变更影响所有文字）
        # 简单方式：关闭重新打开
        logger.info(f"Language changed to {lang}")

    # ── 最小化 / 恢复 ──

    def minimize_to_taskbar(self):
        """最小化到任务栏: 隐藏所有独立工具栏窗口 + 主窗口最小化"""
        for w in (self._edit_toolbar, self._run_toolbar, self._virtual_keyboard):
            if w and w.isVisible():
                w.hide()
        for attr in ('_dlg_profile', '_dlg_voice', '_dlg_hotkey'):
            dlg = getattr(self, attr, None)
            if dlg and dlg.isVisible():
                dlg.hide()
        self.showMinimized()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            # 从最小化恢复 → 重新显示当前模式的工具栏
            if not (self.windowState() & Qt.WindowState.WindowMinimized):
                if self._current_mode == 'edit':
                    self._edit_toolbar.show()
                else:
                    self._run_toolbar.show()
        super().changeEvent(event)

    # ── 事件处理 ──

    def _force_taskbar_visible(self):
        """强制让窗口在 Windows 任务栏显示 (透明 frameless 窗口默认会被识别为 layered, 不进任务栏)"""
        import sys
        if sys.platform != 'win32':
            return
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            SWP_NOACTIVATE = 0x0010
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            new_ex = (ex & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            if new_ex != ex:
                user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, new_ex)
                user32.SetWindowPos(
                    hwnd, 0, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
                    | SWP_FRAMECHANGED | SWP_NOACTIVATE)
        except Exception as e:
            logger.warning("Force taskbar visible failed: %s", e)

    def showEvent(self, event):
        super().showEvent(event)
        self._pt_manager.init_hwnd()
        self._force_taskbar_visible()
        self._edit_toolbar.show()
        if self._current_mode == 'edit':
            self._smart_pt_timer.start()

    def _poll_smart_passthrough(self):
        """每帧检查光标位置，切换 WS_EX_TRANSPARENT — 对齐原版 update_loop"""
        from PyQt6.QtGui import QCursor
        global_pos = QCursor.pos()
        view_pos = self.mapFromGlobal(global_pos)
        scene_pos = self.mapToScene(view_pos)
        item = self._scene.itemAt(scene_pos, self.transform())
        self._pt_manager.update_smart_passthrough(item is not None)

    def mousePressEvent(self, event):
        """智能穿透: 空白区域的点击转发到底层窗口（轮询间隙兜底）"""
        scene_pos = self.mapToScene(event.pos())
        item = self._scene.itemAt(scene_pos, self.transform())

        if item is None:
            # 空白区域 — 无论编辑/运行模式都转发点击
            self._pt_manager.forward_click_to_game(
                event.globalPosition().toPoint(), event.button())
            event.ignore()
            return
        super().mousePressEvent(event)

    def closeEvent(self, event):
        """关闭时保存配置并退出进程"""
        self._smart_pt_timer.stop()
        self._run_controller.stop()
        release_all_keys()  # 兜底释放所有残留按键，防止卡键
        uninstall_wheel_hook()
        # 显式拔出虚拟手柄 (防止下次启动 ViGEmBus bus 累积 ghost 设备)
        try:
            from engine.gamepad_engine import GamepadEngine
            GamepadEngine.shutdown_singleton()
        except Exception as _e:
            logger.warning(f"GamepadEngine shutdown 失败: {_e}")
        self._scene.save_config()
        # 关闭所有非模态弹窗
        from PyQt6.QtWidgets import QDialog
        for child in self.findChildren(QDialog):
            child.close()
        # 显式清理弹窗引用
        self._dlg_profile = None
        self._dlg_voice = None
        self._dlg_hotkey = None
        self._edit_toolbar.close()
        self._run_toolbar.close()
        self._virtual_keyboard.close()
        self._toast.close()
        self._virtual_cursor.stop_tracking()
        event.accept()
        QApplication.quit()

    def keyPressEvent(self, event):
        """Esc 键退出"""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
