"""
TEGG Touch (PyQt6) - voice_engine.py
语音识别引擎 — 使用 Vosk + sounddevice 实现离线语音指令识别。

架构:
  VoiceEngine(QObject)  — 主线程，管理 worker 生命周期
  _VoiceWorker(QObject)  — 运行在 QThread 中，执行实际的音频采集 + 识别
"""

import json
import os
import logging
import queue
import time as _time

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from core.constants import VOICE_MODELS_DIR, VOICE_SAMPLE_RATE, VOICE_CHUNK_SIZE, VOICE_MODEL_MAP

logger = logging.getLogger(__name__)

# 延迟导入检查
_vosk = None
_sd = None


def _ensure_imports():
    """延迟导入 vosk 和 sounddevice，缺失时返回错误信息。"""
    global _vosk, _sd
    errors = []
    if _vosk is None:
        try:
            import vosk
            _vosk = vosk
            _vosk.SetLogLevel(-1)  # 静默 Vosk 内部日志
        except ImportError:
            errors.append("vosk")
    if _sd is None:
        try:
            import sounddevice
            _sd = sounddevice
        except ImportError:
            errors.append("sounddevice")
    return errors


class _VoiceWorker(QObject):
    """QThread worker — 音频采集 + Vosk 识别循环"""

    command_recognized = pyqtSignal(str, str, str, int)  # phrase, keys, action, latency_ms
    status_changed = pyqtSignal(str)                     # 状态文字
    error_occurred = pyqtSignal(str)                     # 错误信息
    audio_data_ready = pyqtSignal(bytes)                 # 原始 PCM 数据 (用于声波可视化)

    def __init__(self, commands: list, language: str):
        """
        Args:
            commands: [{'phrase': ..., 'keys': ..., 'action': ...}, ...]
            language: 'zh-CN' | 'en'
        """
        super().__init__()
        self._commands = commands
        self._language = language
        self._running = False
        self._audio_queue = queue.Queue()

    def stop(self):
        self._running = False

    def run(self):
        """Worker 主循环 — 在 QThread 中调用"""
        missing = _ensure_imports()
        if missing:
            self.error_occurred.emit(
                f"voice.error_dep_missing:{','.join(missing)}")
            return

        # 构建指令查找表: phrase(小写) → (keys, action)
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

        try:
            self.status_changed.emit("voice.status_loading")
            model = _vosk.Model(model_path)
        except Exception as e:
            self.error_occurred.emit(f"voice.error_model_load:{e}")
            return

        # 创建 KaldiRecognizer (带 grammar 约束，提高识别精度)
        grammar_json = json.dumps(grammar_words, ensure_ascii=False)
        rec = _vosk.KaldiRecognizer(model, VOICE_SAMPLE_RATE, grammar_json)

        # 打开麦克风流
        try:
            stream = _sd.RawInputStream(
                samplerate=VOICE_SAMPLE_RATE,
                blocksize=VOICE_CHUNK_SIZE,
                dtype='int16',
                channels=1,
                callback=self._audio_callback,
            )
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

                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get('text', '').strip().lower()
                    if text and text in cmd_map:
                        latency_ms = int((_time.perf_counter() - chunk_ts) * 1000)
                        keys, action = cmd_map[text]
                        self.command_recognized.emit(text, keys, action, latency_ms)
                else:
                    # 部分结果，不处理
                    pass
        finally:
            stream.stop()
            stream.close()
            self.status_changed.emit("voice.status_stopped")

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice 回调 — 将音频数据放入队列 + 转发给可视化"""
        raw = bytes(indata)
        self._audio_queue.put((_time.perf_counter(), raw))
        self.audio_data_ready.emit(raw)


class VoiceEngine(QObject):
    """语音引擎主控制器 — 管理 worker 线程生命周期

    Signals:
        command_recognized(phrase, keys, action) — 识别到指令
        status_changed(status_key) — 状态变化（用于 UI/日志）
        error_occurred(error_key) — 错误发生（优雅降级）
    """

    command_recognized = pyqtSignal(str, str, str, int)  # phrase, keys, action, latency_ms
    status_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    audio_data_ready = pyqtSignal(bytes)  # 转发 worker 的原始 PCM 数据

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._worker = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, commands: list, language: str = 'zh-CN'):
        """启动语音识别

        Args:
            commands: [{'phrase': ..., 'keys': ..., 'action': ...}, ...]
            language: 'zh-CN' | 'en'
        """
        if self.is_running:
            self.stop()

        # 预检查：依赖是否可用
        missing = _ensure_imports()
        if missing:
            self.error_occurred.emit(
                f"voice.error_dep_missing:{','.join(missing)}")
            return

        self._thread = QThread()
        self._worker = _VoiceWorker(commands, language)
        self._worker.moveToThread(self._thread)

        # 连接信号
        self._worker.command_recognized.connect(self.command_recognized)
        self._worker.status_changed.connect(self.status_changed)
        self._worker.error_occurred.connect(self._on_worker_error)
        self._worker.audio_data_ready.connect(self.audio_data_ready)
        self._thread.started.connect(self._worker.run)
        self._worker.status_changed.connect(self._check_stopped)

        self._thread.start()
        logger.info(f"VoiceEngine started: language={language}, commands={len(commands)}")

    def stop(self):
        """停止语音识别"""
        if self._worker:
            self._worker.stop()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)  # 最多等 3 秒
        self._cleanup()
        logger.info("VoiceEngine stopped")

    def _on_worker_error(self, error_key: str):
        """Worker 错误 → 转发 + 清理"""
        logger.error(f"VoiceEngine error: {error_key}")
        self.error_occurred.emit(error_key)
        # Worker 出错会自行退出 run()，线程会结束

    def _check_stopped(self, status: str):
        """Worker 停止后清理线程"""
        if status == "voice.status_stopped":
            if self._thread and self._thread.isRunning():
                self._thread.quit()

    def _cleanup(self):
        self._worker = None
        self._thread = None
