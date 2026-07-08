"""
TEGGTouch 蛋挞 — 常驻唤醒 + 自由听写引擎 (对 AI 助手说话)

流程 (用户设计):
  常听唤醒词「蛋挞」(Vosk grammar 约束, 快且少误触)
    → 命中 → 进入捕获态: 录下你接下来说的一整句 (能量 VAD, 静音自动断句)
    → 送 SiliconFlow SenseVoice 转文字
    → 交给主线程灌进 AI 助手对话自动发送
  捕获期间主线程会压制运行态的游戏语音指令, 发完恢复。

复用 engine.voice_engine 的 Vosk/sounddevice 基建 (_ensure_imports / resolve_mic_device /
_safe_model_path / 常量)。独立 mic 流, 与游戏指令引擎互不干扰 (Windows 共享模式可并存)。
无阻塞主线程: 采集+识别+转写都在本 QThread。
"""

from __future__ import annotations

import json
import logging
import os
import queue
import time as _time

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from core.constants import (VOICE_MODELS_DIR, VOICE_SAMPLE_RATE, VOICE_MODEL_MAP)
from engine.voice_engine import _ensure_imports, resolve_mic_device, _safe_model_path
from core import agent_settings
from agent import asr

logger = logging.getLogger(__name__)

# 捕获态参数
_CHUNK = 1600                # 100ms @16k (比游戏指令小, VAD 更细、唤醒更跟手)
_CHUNK_MS = _CHUNK * 1000 // VOICE_SAMPLE_RATE
_SILENCE_MS = 1500           # 说完后静音多久算结束
_MAX_CAPTURE_MS = 15000      # 单次最长录音
_LEAD_TIMEOUT_MS = 6000      # 唤醒后一直没说话 → 放弃
_MIN_SPEECH_RMS = 400.0      # int16 RMS 语音下限
_SPEECH_FACTOR = 3.5         # 语音阈值 = max(下限, 环境噪声*该系数)

_ST_LISTEN = "listening"
_ST_CAPTURE = "capturing"
_ST_RECOGNIZE = "recognizing"


def _rms(pcm: bytes) -> float:
    import numpy as np
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(a * a))) if a.size else 0.0


class _WakeThread(QThread):
    wake_detected = pyqtSignal()
    state_changed = pyqtSignal(str)     # listening / capturing / recognizing
    transcribed = pyqtSignal(str)       # 最终文本 ('' = 没听到内容)
    error_occurred = pyqtSignal(str)

    def __init__(self, wake_word, language, mic_index, asr_cfg, parent=None):
        super().__init__(parent)
        self._wake = (wake_word or "蛋挞").strip()
        self._language = language
        self._mic_index = mic_index
        self._asr = asr_cfg               # {api_key, base_url, model}
        self._running = False

    def request_stop(self):
        self._running = False

    def run(self):
        missing = _ensure_imports()
        if missing:
            self.error_occurred.emit(f"缺少依赖: {','.join(missing)}")
            return
        import vosk
        import sounddevice as sd

        model_name = VOICE_MODEL_MAP.get(self._language)
        model_path = os.path.join(VOICE_MODELS_DIR, model_name) if model_name else None
        if not model_path or not os.path.isdir(model_path):
            self.error_occurred.emit("Vosk 模型缺失, 唤醒不可用")
            return
        try:
            model = vosk.Model(_safe_model_path(model_path))
        except Exception as e:
            self.error_occurred.emit(f"Vosk 模型加载失败: {e}")
            return

        grammar = json.dumps([self._wake, "[unk]"], ensure_ascii=False)
        rec = vosk.KaldiRecognizer(model, VOICE_SAMPLE_RATE, grammar)

        q: queue.Queue = queue.Queue()

        def _cb(indata, frames, tinfo, status):
            if self._running:
                q.put(bytes(indata))

        try:
            kw = dict(samplerate=VOICE_SAMPLE_RATE, blocksize=_CHUNK,
                      dtype='int16', channels=1, callback=_cb)
            if self._mic_index is not None:
                kw['device'] = self._mic_index
            stream = sd.RawInputStream(**kw)
            stream.start()
        except Exception as e:
            self.error_occurred.emit(f"麦克风打开失败: {e}")
            return

        self._running = True
        self.state_changed.emit(_ST_LISTEN)

        state = _ST_LISTEN
        noise = 200.0
        buf = bytearray()
        speech = False
        silence_ms = 0
        cap_ms = 0
        try:
            while self._running:
                try:
                    data = q.get(timeout=0.2)
                except queue.Empty:
                    continue
                if not self._running:
                    break
                level = _rms(data)

                if state == _ST_LISTEN:
                    noise = 0.95 * noise + 0.05 * level
                    hit = False
                    if rec.AcceptWaveform(data):
                        hit = self._wake in json.loads(rec.Result()).get("text", "")
                    # 不用 PartialResult：小模型噪音误判率高，只在完整句子中确认唤醒词
                    if hit:
                        rec = vosk.KaldiRecognizer(model, VOICE_SAMPLE_RATE, grammar)
                        state = _ST_CAPTURE
                        buf = bytearray(); speech = False; silence_ms = 0; cap_ms = 0
                        self.wake_detected.emit()
                        self.state_changed.emit(_ST_CAPTURE)

                elif state == _ST_CAPTURE:
                    cap_ms += _CHUNK_MS
                    thresh = max(_MIN_SPEECH_RMS, noise * _SPEECH_FACTOR)
                    if level >= thresh:
                        speech = True; silence_ms = 0; buf += data
                    elif speech:
                        silence_ms += _CHUNK_MS; buf += data   # 保留尾部短静音
                    # 结束判定
                    end = False
                    if speech and silence_ms >= _SILENCE_MS:
                        end = True
                    elif cap_ms >= _MAX_CAPTURE_MS and speech:
                        end = True  # 超时只在有真实语音时才转写
                    elif not speech and cap_ms >= _LEAD_TIMEOUT_MS:
                        # 唤醒后没说话，或超时无语音 → 放弃, 回到常听
                        state = _ST_LISTEN
                        self.transcribed.emit("")
                        self.state_changed.emit(_ST_LISTEN)
                        continue
                    elif cap_ms >= _MAX_CAPTURE_MS and not speech:
                        # 最长录音超时但始终无语音 → 丢弃，回到常听
                        while not q.empty():
                            try: q.get_nowait()
                            except queue.Empty: break
                        rec = vosk.KaldiRecognizer(model, VOICE_SAMPLE_RATE, grammar)
                        state = _ST_LISTEN
                        self.state_changed.emit(_ST_LISTEN)
                        continue
                    if end:
                        self.state_changed.emit(_ST_RECOGNIZE)
                        text = ""
                        try:
                            text = asr.transcribe_pcm16(
                                bytes(buf), VOICE_SAMPLE_RATE,
                                api_key=self._asr["api_key"],
                                base_url=self._asr["base_url"],
                                model=self._asr["model"])
                        except Exception as e:
                            self.error_occurred.emit(str(e))
                        else:
                            self.transcribed.emit(text)
                        # 清掉转写期间堆积的旧音频, 回到常听
                        while not q.empty():
                            try: q.get_nowait()
                            except queue.Empty: break
                        rec = vosk.KaldiRecognizer(model, VOICE_SAMPLE_RATE, grammar)
                        state = _ST_LISTEN
                        self.state_changed.emit(_ST_LISTEN)
        finally:
            self._running = False
            try:
                stream.stop(); stream.close()
            except Exception:
                pass


class VoiceWakeEngine(QObject):
    """常驻唤醒引擎主控 (主线程)。信号直通 _WakeThread。"""

    wake_detected = pyqtSignal()
    state_changed = pyqtSignal(str)
    transcribed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, mic_device=None) -> bool:
        """启动常驻监听。返回是否成功启动 (未配置/依赖缺失返回 False)。"""
        if self.is_running:
            return True
        s = agent_settings.load_agent_settings()
        if not s.get("voice_wake_enabled"):
            return False
        if not s.get("asr_api_key"):
            logger.info("语音唤醒未启动: 未配置 SiliconFlow 密钥")
            return False
        if _ensure_imports():
            logger.info("语音唤醒未启动: 缺 vosk/sounddevice")
            return False

        mic_index = None
        if isinstance(mic_device, int):
            mic_index = mic_device
        elif isinstance(mic_device, str) and mic_device:
            mic_index = resolve_mic_device(mic_device)

        asr_cfg = {"api_key": s["asr_api_key"], "base_url": s["asr_base_url"],
                   "model": s["asr_model"]}
        self._thread = _WakeThread(s.get("wake_word", "蛋挞"), "zh-CN", mic_index,
                                   asr_cfg, parent=self)
        self._thread.wake_detected.connect(self.wake_detected)
        self._thread.state_changed.connect(self.state_changed)
        self._thread.transcribed.connect(self.transcribed)
        self._thread.error_occurred.connect(self.error_occurred)
        self._thread.start()
        logger.info("VoiceWakeEngine 启动 (唤醒词=%s, mic=%s)", s.get("wake_word"), mic_index)
        return True

    def stop(self):
        if not self._thread:
            return
        self._thread.request_stop()
        try:
            self._thread.wake_detected.disconnect()
            self._thread.state_changed.disconnect()
            self._thread.transcribed.disconnect()
            self._thread.error_occurred.disconnect()
        except (TypeError, RuntimeError):
            pass
        if self._thread.isRunning() and not self._thread.wait(3000):
            self._thread.terminate(); self._thread.wait(1000)
        self._thread = None
        logger.info("VoiceWakeEngine 停止")
