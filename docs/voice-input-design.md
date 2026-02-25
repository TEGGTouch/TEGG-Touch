# TEGGTouch-PyQt6 语音输入功能设计方案

## Context

TEGGTouch（蛋挞触控）是一款 Windows 无障碍辅助工具，通过全屏透明覆盖层将鼠标/触屏操作映射为键盘按键，帮助用户玩需要键盘操控的游戏。现需新增**语音输入**功能：用户预设"语音指令 → 按键"映射，运行模式下麦克风持续监听，识别到匹配指令后触发对应按键操作。

---

## 技术选型

### 语音识别：Vosk（离线 + 语法约束）

| 维度 | Vosk | faster-whisper | Windows SAPI |
|------|------|---------------|-------------|
| 离线 | ✅ | ✅ | ✅ |
| 延迟 | ~50-150ms（语法约束） | ~200-500ms | ~100-200ms |
| 中文支持 | ✅ small-cn 模型 ~50MB | ✅ | 有限 |
| 词汇约束 | ✅ Grammar API | ❌ 全文转写 | ✅ 但 Python API 复杂 |
| Python API | pip install vosk | pip install faster-whisper | 需 comtypes/win32com |

**选择 Vosk 理由**：
1. **Grammar（语法约束）模式** — 将识别范围限定为用户预设的指令词，大幅提高速度和准确率
2. 离线运行，无网络依赖，符合游戏场景
3. 中英文小模型各约 40-50MB，足够轻量
4. Python API 简洁，pip 安装无需编译

### 音频采集：sounddevice

选择 `sounddevice` 而非 `pyaudio`：Windows 下 pip 直接安装（自带 PortAudio 二进制），无需手动编译。支持 callback 模式实现低延迟连续采集。

### 新增依赖

```
vosk>=0.3.45
sounddevice>=0.4.6
```

Vosk 模型需用户手动下载至 `models/vosk/` 目录（不打包进安装包，避免体积膨胀）。

---

## 架构设计

### 线程模型

```
Main Thread (Qt Event Loop)              Worker Thread (QThread)
───────────────────────────              ───────────────────────

VoiceEngine(QObject)                     _VoiceWorker(QObject)
  ├─ _thread: QThread                      ├─ _recognizer: vosk.KaldiRecognizer
  ├─ _worker: _VoiceWorker                 ├─ _audio_queue: queue.Queue
  ├─ start(commands, lang)                 └─ _run_loop():
  ├─ stop()                                     while running:
  │                                                chunk = queue.get()
  │  Signals:                                      if recognizer.AcceptWaveform(chunk):
  │  command_recognized(phrase, keys, action)         text = parse result
  │  status_changed(str)                              if text in command_map:
  │  error_occurred(str)                                emit command_recognized
  │
  └─ Audio callback (PortAudio thread):
       indata → queue.put(bytes)
```

**关键设计**：
- 音频采集在 PortAudio 线程（sounddevice callback），仅做 bytes 入队
- Vosk 识别在 QThread worker 中运行，不阻塞主线程
- 通过 Qt queued signal 跨线程传递识别结果到主线程
- Grammar 约束让 Vosk 仅匹配预设指令，消除误识别

### 信号流（识别到触发）

```
_VoiceWorker.command_recognized(phrase, keys, action)
  → [queued connection]
  → RunController._on_voice_command(phrase, keys, action)
    → input_engine.trigger(keys, action)   # 复用现有按键模拟
```

### 与现有 RunController 集成

语音识别是**信号驱动**（非轮询），不插入 `_tick()` 循环。这是因为语音本质上是异步的，且已有 QThread 信号机制完美匹配。

---

## 数据模型

### VoiceCommandData（新建 `models/voice_model.py`）

```python
@dataclass
class VoiceCommandData:
    phrase: str = ""      # 语音指令，如 "跳"、"jump"
    keys: str = ""        # 触发按键，"+" 分隔，如 "space"、"w+shift"
    action: str = "c"     # 动作类型：'c'=点击, 'p'=按下, 'r'=释放
```

### Profile JSON 扩展

```json
{
  "buttons": [...],
  "voice_commands": [
    { "phrase": "跳", "keys": "space", "action": "c" },
    { "phrase": "攻击", "keys": "j", "action": "c" },
    { "phrase": "前进", "keys": "w", "action": "p" },
    { "phrase": "停", "keys": "w", "action": "r" }
  ],
  "voice_language": "zh-CN",
  "voice_enabled": true
}
```

动作类型说明：
- **click (c)**：说出即触发一次按键（按下+释放），适合"跳"、"攻击"
- **press (p)**：说出后按下并保持，适合"前进"持续移动
- **release (r)**：说出后释放按键，与 press 配对使用，如"停"释放 W 键

---

## 新建文件（3个）

### 1. `models/voice_model.py`
- `VoiceCommandData` dataclass + `to_dict()` / `from_dict()`

### 2. `engine/voice_engine.py`
- `VoiceEngine(QObject)` — 管理线程、模型加载、Grammar 构建
- `_VoiceWorker(QObject)` — worker 线程中运行识别循环
- 音频 callback → queue → Vosk 识别 → signal 发射
- `start(commands, language)` / `stop()` 生命周期
- Vosk model 路径检测与错误处理

### 3. `views/voice_settings_dialog.py`
- 语音指令配置对话框，遵循现有 HotkeySettingsDialog 双栏深色主题模式
- 左栏：语言选择 + 指令列表（phrase/keys/action）+ 添加/删除 + 麦克风测试
- 右栏：按键面板（复用 ButtonEditorDialog 的 KEY_CATEGORIES）

---

## 修改文件（8个）

### 4. `core/constants.py`
- 新增语音相关常量：`VOICE_MODELS_DIR`, `VOICE_SAMPLE_RATE=16000`, `VOICE_CHUNK_SIZE=4000`

### 5. `core/config_manager.py`
- `load_config_from_file()` 中读取 `voice_commands`, `voice_language`, `voice_enabled`
- `save_config_to_file()` 中写入这三个字段

### 6. `engine/run_controller.py`
- `__init__`: 新增 `self._voice_engine = None`
- `start()`: 检查语音配置，若有则启动 VoiceEngine
- `stop()`: 停止 VoiceEngine
- 新增 `_on_voice_command(phrase, keys, action)` 槽函数，调用 `trigger(keys, action)`
- 新增 `voice_command_triggered = pyqtSignal(str)` 信号，供 UI 反馈

### 7. `views/edit_toolbar.py`
- Row 1 中在"软键盘"按钮后添加"语音"按钮（麦克风图标 `\uE720`）
- 新增 `voice_clicked = pyqtSignal()`

### 8. `views/run_toolbar.py`
- 添加语音状态切换按钮（麦克风图标 + 状态指示）
- 新增 `voice_toggle_clicked = pyqtSignal()`
- `update_voice_status(active: bool)` 方法

### 9. `views/overlay_window.py`
- 连接 `edit_toolbar.voice_clicked` → `_open_voice_settings()`
- 连接 `run_toolbar.voice_toggle_clicked` → 运行时切换语音
- 连接 `run_controller.voice_command_triggered` → 运行工具栏反馈
- `to_run()` 中传递语音配置给 RunController

### 10. `locales/zh-CN.json` + `locales/en.json`
- 新增 `voice.*` 翻译键（title, phrase, keys, action, mic_ok, mic_fail, model_missing 等）

### 11. `scene/overlay_scene.py`
- `save_config()` / `load_from_config()` 中处理 `voice_commands` 字段

---

## UI 设计

### 语音设置对话框（voice_settings_dialog.py）

```
+--------------------------------------------------------------------+
| [mic icon] 语音指令设置                                       [X]   |
| 添加语音指令，运行模式下说出指令即可触发按键                          |
+--------------------------------------------------------------------+
|                                                                     |
|  左栏 (420px)                     | 右栏 (480px)                    |
|                                   |                                 |
|  语言: [中文] [English]           | ── 按键面板 ──                   |
|                                   |                                 |
|  ┌─ 指令列表 ─────────────────┐   | (与 ButtonEditorDialog 相同的    |
|  │ [语音指令] [按键] [动作] X  │   |  可滚动按键面板，点击插入到      |
|  │ "跳"    [space]  点击    X  │   |  当前聚焦的 TagInput 字段)      |
|  │ "攻击"  [j]      点击    X  │   |                                 |
|  │ "前进"  [w]      按下    X  │   |                                 |
|  │ "停"    [w]      释放    X  │   |                                 |
|  │                             │   |                                 |
|  │ [+ 添加指令]                │   |                                 |
|  └─────────────────────────────┘   |                                 |
|                                    |                                 |
|  麦克风状态: [绿点] 就绪           |                                 |
|  [测试麦克风]                      |                                 |
|                                    |                                 |
|              [保存]                |                                 |
+--------------------------------------------------------------------+
```

### 编辑工具栏

在"软键盘"按钮后添加麦克风图标按钮，点击打开语音设置对话框。

### 运行工具栏

在穿透模式按钮前添加语音状态切换按钮：
- 绿色脉冲点 = 正在监听
- 灰色点 = 已配置但暂停
- 点击切换语音开/关

---

## 错误处理与优雅降级

| 场景 | 处理方式 |
|------|---------|
| vosk/sounddevice 未安装 | `try/except ImportError`，语音相关 UI 隐藏/禁用 |
| 无麦克风 | `sounddevice.query_devices()` 检测，toast 提示，正常运行无语音 |
| Vosk 模型缺失 | 对话框中显示下载提示，语音引擎不启动 |
| 音频流中断 | worker 捕获异常，发 error 信号，其他输入方式继续工作 |
| 识别到未知词 | Vosk 返回 `[unk]`，直接忽略 |

**核心原则**：语音功能完全是可选附加项，任何失败都不影响现有功能。

---

## 实施顺序

1. `models/voice_model.py` — 数据模型（无依赖）
2. `core/constants.py` — 新增常量
3. `core/config_manager.py` — 配置读写扩展
4. `engine/voice_engine.py` — 核心语音引擎
5. `views/voice_settings_dialog.py` — 配置 UI
6. `views/edit_toolbar.py` — 编辑工具栏按钮
7. `views/run_toolbar.py` — 运行工具栏状态
8. `engine/run_controller.py` — 集成到运行控制器
9. `views/overlay_window.py` — 总线连接
10. `scene/overlay_scene.py` — 场景配置
11. `locales/*.json` — 国际化翻译

---

## 验证方式

1. 安装依赖：`pip install vosk sounddevice`
2. 下载 Vosk 中文小模型至 `models/vosk/vosk-model-small-cn-0.22/`
3. 启动应用，编辑模式点击"语音"按钮，添加指令如 "跳" → space → click
4. 保存，进入运行模式，对麦克风说"跳"
5. 验证 space 键被触发
6. 测试 press/release 配对：添加"前进"→w→press 和"停"→w→release
7. 验证说"前进"后 W 持续按下，说"停"后 W 释放
8. 测试无麦克风/无模型场景下的错误提示和优雅降级
