"""
TEGG Touch 蛋挞 (PyQt6) - overlay_window.py
全屏透明覆盖窗口 — 替代旧版 FloatingApp。
"""

import logging

from PyQt6.QtWidgets import QGraphicsView, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter

from core.i18n import t, load_locale
from core.constants import APP_VERSION, PT_ON, PT_OFF, PT_BLOCK, DEFAULT_TRANSPARENCY, DEFAULT_GRID_SIZE
from core.config_manager import (
    init_profiles, load_hotkeys, get_active_profile_name,
    load_profile, save_profile, set_active_profile,
)
from core.input_engine import install_wheel_hook, uninstall_wheel_hook
from scene.overlay_scene import OverlayScene
from engine.run_controller import RunController
from engine.passthrough_manager import PassthroughManager

from views.edit_toolbar import EditToolbar
from views.run_toolbar import RunToolbar
from views.button_editor_dialog import ButtonEditorDialog
from views.center_band_dialog import CenterBandDialog
from views.profile_manager_dialog import ProfileManagerDialog
from views.hotkey_settings_dialog import HotkeySettingsDialog
from views.about_dialog import AboutDialog
from views.virtual_keyboard import VirtualKeyboard
from views.voice_settings_dialog import VoiceSettingsDialog
from views.toast_widget import ToastWidget
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

        # ── 窗口属性 ──
        self.setWindowTitle(f"{t('app.title')} v{APP_VERSION}")

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
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
        screen = QApplication.primaryScreen().geometry()
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
        self._edit_toolbar.about_clicked.connect(self._open_about)
        self._edit_toolbar.quit_clicked.connect(self.close)

        # 连接运行工具栏信号
        self._run_toolbar.stop_clicked.connect(self.to_edit)
        self._run_toolbar.voice_toggle_clicked.connect(self._toggle_voice)
        self._run_toolbar.auto_center_clicked.connect(self._toggle_auto_center)
        self._run_toolbar.toggle_buttons_clicked.connect(self._toggle_buttons_visibility)
        self._run_toolbar.soft_keyboard_clicked.connect(self._toggle_soft_keyboard)
        self._run_toolbar.pt_clicked.connect(self._on_pt_clicked)

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

        # ── 虚拟光标 ──
        self._virtual_cursor = VirtualCursorItem()
        self._virtual_cursor.setVisible(False)
        self._scene.addItem(self._virtual_cursor)

        # ── 智能穿透轮询定时器 (编辑模式) ──
        self._smart_pt_timer = QTimer(self)
        self._smart_pt_timer.setInterval(16)  # ~60fps，与原版 update_loop 对齐
        self._smart_pt_timer.timeout.connect(self._poll_smart_passthrough)

        # 连接场景信号
        self._scene.button_double_clicked.connect(self._open_button_editor)

        # ── 默认透明度 (与工具栏滑块初始值一致) ──
        self._apply_item_opacity(DEFAULT_TRANSPARENCY)

        # ── 加载配置 ──
        self._load_profile()

        # 连接按钮信号到运行控制器
        self._wire_button_signals()

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
        if self._scene.ring_item:
            self._wire_single_item(self._scene.ring_item)

    def _wire_single_item(self, item):
        """将单个 Item 的信号连接到运行控制器"""
        item.hoverActivated.connect(self._run_controller.on_hover_activated)
        item.hoverDeactivated.connect(self._run_controller.on_hover_deactivated)
        item.actionTriggered.connect(self._run_controller.on_action_triggered)

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
        cfg = self._scene._config
        saved_x = cfg.get('run_toolbar_x') if cfg else None
        saved_y = cfg.get('run_toolbar_y') if cfg else None
        self._run_toolbar.set_saved_position(saved_x, saved_y)
        self._run_toolbar.show()
        self._voice_active = False
        self._run_toolbar.update_voice_state(False)
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
        if self._scene.ring_item:
            visible = (self._scene.wheel_visible and self._scene._wheel_enlarged
                       and self._scene._wheel_center_ring_visible)
            self._scene.ring_item.setVisible(visible)

        self._run_toolbar.hide()
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

    def _on_pt_clicked(self, mode):
        """工具栏穿透按钮点击 → 同步 manager + toolbar + 光标"""
        self._pt_manager.set_mode(mode)
        self._run_toolbar.update_pt_mode(mode)
        # 同步虚拟光标类型
        cursor_type = self._PT_CURSOR_MAP.get(mode, 'cursor')
        self._virtual_cursor.set_cursor_type(cursor_type)

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
        if self._scene.ring_item:
            if self._buttons_hidden:
                self._scene.ring_item.setVisible(False)
            else:
                visible = (self._scene.wheel_visible and self._scene._wheel_enlarged
                           and self._scene._wheel_center_ring_visible)
                self._scene.ring_item.setVisible(visible)
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
        config = self._scene._config or {}
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
        if self._scene._config:
            self._scene._config['run_toolbar_x'] = x
            self._scene._config['run_toolbar_y'] = y

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
        if self._scene._config:
            self._scene._config['grid_size'] = gs

    def _on_opacity_changed(self, value):
        """编辑模式背景透明度调整 — 仅影响按钮/轮盘，不影响虚拟光标"""
        # value: 0.1 ~ 0.9 (来自滑块 10%-90%)
        self._apply_item_opacity(value)
        # 持久化到 config（下次 save_config 时写入文件）
        if self._scene._config:
            self._scene._config['transparency'] = value

    def _apply_item_opacity(self, value):
        """对按钮和轮盘设置透明度，虚拟光标和进度条保持完全不透明"""
        self._current_opacity = value
        for item in self._scene.button_items:
            item.setOpacity(value)
        for item in self._scene.wheel_items:
            item.setOpacity(value)
        if self._scene.ring_item:
            self._scene.ring_item.setOpacity(value)

    # ── 弹窗 ──

    def _open_button_editor(self, item):
        """打开按钮编辑弹窗 — 回中带使用简化弹窗"""
        if hasattr(item.data, 'btn_type') and item.data.btn_type == BTN_TYPE_CENTER_BAND:
            dialog = CenterBandDialog(item, self)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.deleted.connect(lambda it: self._on_button_deleted(it))
            dialog.copied.connect(lambda it: self._on_button_copied(it))
            dialog.show()
            return
        macros = self._scene._config.get('macros', [])
        dialog = ButtonEditorDialog(item, self, macros=macros)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.macros_changed.connect(self._on_macros_changed)
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

    def _on_button_copied(self, item):
        """按钮复制后"""
        new_item = self._scene.copy_button(item)
        if new_item:
            self._wire_single_item(new_item)
            self._scene.save_config()

    def _on_macros_changed(self, macros_list):
        """宏列表变更 → 写入 config 并保存"""
        if self._scene._config is not None:
            self._scene._config['macros'] = macros_list
            self._scene.save_config()
            logger.info("Macros updated: %d macros", len(macros_list))

    def _open_profile_manager(self):
        """打开方案管理弹窗"""
        dialog = ProfileManagerDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.profile_switched.connect(self._on_profile_switched)
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
        if self._scene.ring_item:
            self._scene.removeItem(self._scene.ring_item)
            self._scene.ring_item = None
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

    def _open_voice_settings(self):
        """打开语音指令设置弹窗"""
        config = self._scene._config or {}
        voice_commands = config.get('voice_commands', [])
        voice_language = config.get('voice_language', None)
        voice_mic_device = config.get('voice_mic_device', None)
        macros = config.get('macros', [])
        dialog = VoiceSettingsDialog(voice_commands, voice_language, voice_mic_device, self, macros=macros)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.settings_saved.connect(self._on_voice_settings_saved)
        dialog.show()

    def _on_voice_settings_saved(self):
        """语音设置保存后 → 写入 config"""
        dialog = self.sender()
        if dialog and hasattr(dialog, 'get_result'):
            result = dialog.get_result()
            if self._scene._config:
                self._scene._config['voice_commands'] = result.get('voice_commands', [])
                self._scene._config['voice_language'] = result.get('voice_language', 'zh-CN')
                self._scene._config['voice_enabled'] = result.get('voice_enabled', False)
                self._scene._config['voice_mic_device'] = result.get('voice_mic_device')
            self._scene.save_config()
            logger.info("Voice settings saved: %d commands", len(result.get('voice_commands', [])))

    def _open_hotkey_settings(self):
        """打开快捷键设置弹窗"""
        dialog = HotkeySettingsDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.settings_saved.connect(self._on_settings_saved)
        dialog.defaults_reset.connect(self._on_defaults_reset)
        dialog.language_changed.connect(self._on_language_changed)
        dialog.show()

    def _on_settings_saved(self):
        """设置保存后"""
        # 运行控制器重新读取热键
        self._run_controller.reload_hotkeys()

    def _on_defaults_reset(self):
        """设置面板重置默认 → 重置透明度 + 清除运行工具栏保存的位置"""
        default_opacity = DEFAULT_TRANSPARENCY
        # 重置透明度
        self._apply_item_opacity(default_opacity)
        self._edit_toolbar.set_opacity(default_opacity)
        if self._scene._config:
            self._scene._config['transparency'] = default_opacity
        # 清除运行工具栏位置（下次进入运行模式将使用居中默认位置）
        if self._scene._config:
            self._scene._config['run_toolbar_x'] = None
            self._scene._config['run_toolbar_y'] = None
        # 重置网格大小
        self._scene.set_grid_size(DEFAULT_GRID_SIZE)
        self._edit_toolbar.set_grid_size(DEFAULT_GRID_SIZE)
        if self._scene._config:
            self._scene._config['grid_size'] = DEFAULT_GRID_SIZE
        # 重置运行工具栏到默认居中位置
        self._run_toolbar._position_toolbar()
        logger.info("Defaults reset: transparency=%.2f, grid=%d, run_toolbar position cleared",
                     default_opacity, DEFAULT_GRID_SIZE)

    def _on_language_changed(self, lang):
        """语言切换后刷新 UI"""
        # 重建工具栏（语言变更影响所有文字）
        # 简单方式：关闭重新打开
        logger.info(f"Language changed to {lang}")

    def _open_about(self):
        """打开关于弹窗"""
        dialog = AboutDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()

    # ── 事件处理 ──

    def showEvent(self, event):
        super().showEvent(event)
        self._pt_manager.init_hwnd()
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
        uninstall_wheel_hook()
        self._scene.save_config()
        # 关闭所有非模态弹窗
        from PyQt6.QtWidgets import QDialog
        for child in self.findChildren(QDialog):
            child.close()
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
