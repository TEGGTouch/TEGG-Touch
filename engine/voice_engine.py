"""
TEGG Touch (PyQt6) - voice_engine.py
语音识别引擎 — 使用 Vosk + sounddevice 实现离线语音指令识别。

架构:
  VoiceEngine(QObject)  — 主线程 API，管理线程生命周期
  _VoiceThread(QThread)  — 子类化 QThread，直接在 run() 中执行阻塞的音频采集 + 识别

为什么用 QThread 子类而不是 moveToThread + started 信号:
  - 避免 started → blocking_run → exec() 的竞态问题
  - run() 返回即线程结束，不需要 quit() 调用 exec() 退出
  - 更简单的生命周期管理
"""

import json
import os
import logging
import queue
import threading
import time as _time

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from core.constants import VOICE_MODELS_DIR, VOICE_SAMPLE_RATE, VOICE_CHUNK_SIZE, VOICE_MODEL_MAP

logger = logging.getLogger(__name__)

# 延迟导入
_vosk = None
_sd = None


def _ensure_imports():
    """延迟导入 vosk 和 sounddevice，缺失时返回错误列表。

    使用 except Exception 而非 ImportError，因为打包环境下
    vosk DLL 缺失会抛 OSError 而非 ImportError。
    """
    global _vosk, _sd
    errors = []
    if _vosk is None:
        try:
            import vosk
            _vosk = vosk
            _vosk.SetLogLevel(-1)
        except Exception as e:
            logger.warning(f"Failed to import vosk: {e}")
            errors.append("vosk")
    if _sd is None:
        try:
            import sounddevice
            _sd = sounddevice
        except Exception as e:
            logger.warning(f"Failed to import sounddevice: {e}")
            errors.append("sounddevice")
    return errors


def resolve_mic_device(mic_name: str):
    """将麦克风设备名称解析为 sounddevice 设备索引。

    Args:
        mic_name: 设备显示名（从 config 加载）

    Returns:
        int | None: 匹配到的设备索引，未找到返回 None
    """
    if not mic_name:
        return None
    try:
        errs = _ensure_imports()
        if errs:
            return None
        devs = _sd.query_devices()
        # 精确匹配（strip 后）
        for i, d in enumerate(devs):
            if d.get('max_input_channels', 0) > 0:
                if d.get('name', '').strip() == mic_name:
                    return i
        # 子串匹配（回退）
        for i, d in enumerate(devs):
            if d.get('max_input_channels', 0) > 0:
                if mic_name in d.get('name', ''):
                    return i
    except Exception as e:
        logger.warning(f"resolve_mic_device failed: {e}")
    return None


class _VoiceThread(QThread):
    """音频采集 + Vosk 识别线程 — 直接子类化 QThread"""

    command_recognized = pyqtSignal(str, str, str, int)  # phrase, keys, action, latency_ms
    status_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    audio_data_ready = pyqtSignal(bytes)  # PCM 数据（声波可视化）

    def __init__(self, commands: list, language: str, mic_device_index=None, parent=None):
        super().__init__(parent)
        self._commands = commands
        self._language = language
        self._mic_device_index = mic_device_index  # int or None
        self._running = False
        self._audio_queue = queue.Queue()
        self._emit_audio = True  # 控制音频信号发射，stop 时置 False

    def request_stop(self):
        """请求停止（线程安全）"""
        self._emit_audio = False
        self._running = False

    def run(self):
        """线程主函数 — 阻塞执行，返回即线程结束"""
        missing = _ensure_imports()
        if missing:
            self.error_occurred.emit(
                f"voice.error_dep_missing:{','.join(missing)}")
            return

        # 构建指令查找表
        cmd_map = {}
        grammar_words = []
        for cmd in self._commands:
            phrase = cmd.get('phrase', '').strip().lower()
            if phrase:
                cmd_map[phrase] = (cmd.get('keys', ''), cmd.get('action', 'click'))
                grammar_words.append(phrase)

        if not cmd_map:
            self.error_occurred.emit("voice.error_no_commands")
            return

        # 加载 Vosk 模型
        model_name = VOICE_MODEL_MAP.get(self._language)
        if not model_name:
            self.error_occurred.emit(f"voice.error_unknown_language:{self._language}")
            return

        model_path = os.path.join(VOICE_MODELS_DIR, model_name)
        if not os.path.isdir(model_path):
            self.error_occurred.emit(f"voice.error_model_missing:{model_name}")
            return

        # 检查是否已在加载前被要求停止
        if not self._emit_audio:
            return

        try:
            self.status_changed.emit("voice.status_loading")
            model = _vosk.Model(model_path)
        except Exception as e:
            self.error_occurred.emit(f"voice.error_model_load:{e}")
            return

        # 再次检查（模型加载可能耗时数秒）
        if not self._emit_audio:
            return

        grammar_json = json.dumps(grammar_words, ensure_ascii=False)
        rec = _vosk.KaldiRecognizer(model, VOICE_SAMPLE_RATE, grammar_json)

        # 打开麦克风流
        stream = None
        try:
            sd_kwargs = dict(
                samplerate=VOICE_SAMPLE_RATE,
                blocksize=VOICE_CHUNK_SIZE,
                dtype='int16',
                channels=1,
                callback=self._audio_callback,
            )
            if self._mic_device_index is not None:
                sd_kwargs['device'] = self._mic_device_index
            stream = _sd.RawInputStream(**sd_kwargs)
            stream.start()
        except Exception as e:
            self.error_occurred.emit(f"voice.error_no_mic:{e}")
            return

        self._running = True
        self.status_changed.emit("voice.status_listening")

        try:
            while self._running:
                try:
                    chunk_ts, data = self._audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                if not self._running:
                    break

                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get('text', '').strip().lower()
                    if text and text in cmd_map:
                        latency_ms = int((_time.perf_counter() - chunk_ts) * 1000)
                        keys, action = cmd_map[text]
                        if self._running:
                            self.command_recognized.emit(text, keys, action, latency_ms)
        finally:
            # 先停掉音频信号发射，再关闭流
            self._emit_audio = False
            self._running = False
            if stream:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            # 清空队列，防止残留引用
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    break
            self.status_changed.emit("voice.status_stopped")

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice 回调 — 在 PortAudio 线程中执行。

        注意: 必须检查 _emit_audio 标志，因为在 stop 过程中
        PortAudio 可能仍在调用此回调，而 Qt 对象可能已被销毁。
        """
        if not self._emit_audio:
            return
        raw = bytes(indata)
        self._audio_queue.put((_time.perf_counter(), raw))
        # 仅在安全时发射信号（避免向已销毁的 widget 发送数据）
        if self._emit_audio:
            try:
                self.audio_data_ready.emit(raw)
            except RuntimeError:
                # Qt 对象已被删除
                self._emit_audio = False


class VoiceEngine(QObject):
    """语音引擎主控制器

    Signals:
        command_recognized(phrase, keys, action, latency_ms)
        status_changed(status_key)
        error_occurred(error_key)
        audio_data_ready(bytes)
    """

    command_recognized = pyqtSignal(str, str, str, int)
    status_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    audio_data_ready = pyqtSignal(bytes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, commands: list, language: str = 'zh-CN', mic_device=None):
        """启动语音识别

        Args:
            commands: [{'phrase': ..., 'keys': ..., 'action': ...}, ...]
            language: 'zh-CN' | 'en'
            mic_device: 麦克风设备名(str)、设备索引(int)或 None(系统默认)
        """
        if self.is_running:
            self.stop()

        missing = _ensure_imports()
        if missing:
            self.error_occurred.emit(
                f"voice.error_dep_missing:{','.join(missing)}")
            return

        # 解析麦克风设备: 字符串名称 → 设备索引
        mic_index = None
        if isinstance(mic_device, int):
            mic_index = mic_device
        elif isinstance(mic_device, str) and mic_device:
            mic_index = resolve_mic_device(mic_device)
            if mic_index is None:
                logger.warning(f"Mic device '{mic_device}' not found, using default")
        # None → 系统默认

        self._thread = _VoiceThread(commands, language, mic_index, parent=self)

        # 连接信号（注意: _VoiceThread 的信号在子线程 emit，
        # 连接到主线程的 VoiceEngine 是自动 QueuedConnection）
        self._thread.command_recognized.connect(self.command_recognized)
        self._thread.status_changed.connect(self.status_changed)
        self._thread.error_occurred.connect(self._on_error)
        self._thread.audio_data_ready.connect(self.audio_data_ready)

        self._thread.start()
        logger.info(f"VoiceEngine started: lang={language}, cmds={len(commands)}, "
                     f"mic={mic_device}→idx={mic_index}")

    def stop(self):
        """停止语音识别 — 安全地清理线程和信号"""
        if not self._thread:
            return

        # 1. 请求停止 + 阻止信号发射
        self._thread.request_stop()

        # 2. 断开所有信号连接，防止延迟信号到达已销毁的接收端
        try:
            self._thread.command_recognized.disconnect()
            self._thread.status_changed.disconnect()
            self._thread.error_occurred.disconnect()
            self._thread.audio_data_ready.disconnect()
        except (TypeError, RuntimeError):
            pass  # 信号可能未连接

        # 3. 等待线程结束（run() 返回即结束，不需要 quit()）
        if self._thread.isRunning():
            if not self._thread.wait(5000):
                logger.warning("VoiceEngine: thread timeout, terminating")
                self._thread.terminate()
                self._thread.wait(2000)

        self._thread = None
        logger.info("VoiceEngine stopped")

    def _on_error(self, error_key: str):
        logger.error(f"VoiceEngine error: {error_key}")
        self.error_occurred.emit(error_key)
