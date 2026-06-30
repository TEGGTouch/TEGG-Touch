# TEGGTouch-PyQt6 Agent 集成调查与架构方案

> 状态：**阶段0 地基已实现**（分支 `feature/agent-integration`）；阶段1+ 设计中。
> 本文是 Agent 能力的总纲文档 + 开发者接入指南，后续讨论与拆分都基于它迭代。
>
> **想直接接 agent 的开发者**：跳到下方「接入 Agent：开发者指南」一节。

## Context

TEGGTouch（蛋挞触控）是一款 Windows 无障碍辅助工具，通过全屏透明覆盖层把鼠标/触屏操作映射为键盘/鼠标/手柄输入，帮助残障用户操作需要键盘/手柄的游戏与软件。

现规划新增 **Agent 能力**，让蛋挞从"用户触摸 → 固定按键/宏"升级为"理解用户自然语言意图 → 自动执行"。两个方向：

1. **Agent 操作电脑**：通过 agent 控制鼠标、键盘、手柄（实际发输入）。
2. **Agent 配置助手**：帮用户设置蛋挞自己的按键绑定与各种参数。

Agent 的"大脑"为**云端多模态模型**（不绑定具体厂商；用户本地 PC 不一定能跑大模型；性能允许时可云/本地混合）。多模态意味着 agent 需要"看屏幕"的能力。

交互是**双路并行**：
- **本地快路**：现有 Vosk 语音继续处理简单固定指令，低延迟、离线。
- **智能慢路**：完整自然语言（语音转写或文字）交给云端 agent 做交互。
- 另需文字聊天入口 + 对外 API（供外部程序/SDK 调用）。

---

## 设计哲学

**帮助优先，知情透明。**

服务对象是残障用户，他们对自动化帮助的需求，往往高于对隐私的顾虑。因此在"能力 vs 隐私/安全"的取舍上，**向能力倾斜**——但前提是**用户始终知情、始终可控**：

- 截屏等敏感动作**始终告知用户**，用户拥有最大限度的能力开关。
- 直接操作真实输入有误操作风险，默认**先确认再执行**；信任后用户可开 **auto 模式**自动执行。
- 一切自动行为**可随时中断**。

后续所有设计取舍都向这条哲学看齐。

---

## 已锁定的架构决策

| # | 决策点 | 结论 |
|---|--------|------|
| 1 | 工具层形态 | **先进程内直调**，但接口按"日后可抽成独立进程 + 本地 IPC/HTTP"设计，不被实现方式绑死（为对外 API / 进程隔离留路） |
| 2 | action 协议 | **复用现有标签语法 + 宏 schema**（`mouse:left` / `gp:A` / `recenter:…` / `xmacro:…`），agent 输出即蛋挞可执行，零翻译损耗 |
| 3 | 安全模型 | 默认 **先确认再执行**；用户可开 **auto 模式** 跳过确认；一切可中断 |
| 4 | Agent 数量 | **单一 agent**，靠切换 **toolset**（配置工具集 / 控制工具集）区分场景 |
| 5 | 截屏/隐私 | 截屏**始终告知用户** + 用户掌握最大限度截屏能力；遵循"帮助优先、知情透明" |

---

## 已实现（阶段0 地基）

阶段0 的目标是让 agent **无需懂 UI、即可程序化操作蛋挞**，并保证基建与 agent 解耦、可并行开发。已落地：

| 能力 | 实现 | 文件 |
|---|---|---|
| **Agent 工具层**（控制 + 配置两套 toolset） | `ControlTools` / `ConfigTools`，纯 headless、无 Qt 依赖、返回可序列化 dict | `agent/tool_layer.py` |
| **执行服务**（宏/应用/屏幕回中） | 从 RunController 抽出的纯逻辑，运行时与 agent **共用同一份** | `core/action_service.py` |
| **配置热生效** | 运行中重读 profile 应用到场景，不退编辑模式/不重启 | `OverlayWindow.reload_active_profile()`、`RunController.prepare_hot_reload()`、`OverlayScene.clear_all_items()` |
| **鼠标绝对定位** | `mouse_move(x, y)`（G5 的精准定位部分） | `core/input_engine.py` |
| **验证脚本** | 工具层全路径演示 / 热重载机制测试 | `agent/headless_demo.py`、`agent/test_hot_reload.py` |

### 解耦现状（关键）

依赖是**单向**的，agent 是**纯增量**——删掉 `agent/` 整个目录，蛋挞照常运行：

```
agent/  ──依赖──▶  core/ (input_engine · action_service · config_manager · constants)
                   └─ engine/gamepad_engine (惰性)
              ╳ 不依赖  views/ · scene/ · 任何 Qt/UI

core · engine · views  ──▶  从不 import agent/   (基建不知道 agent 存在)
```

→ **基建与 agent 可独立开发**，但共享一份"契约"（见下方指南的"稳定契约"）。两者仍在同一进程（决策 #1：先进程内，接口按可抽 IPC 设计）。

---

## 接入 Agent：开发者指南

本节给"要把一个 agent（或任何自动化）接到蛋挞上"的开发者。**只依赖下面列出的稳定面，不要碰基建内部。**

### 1. 稳定契约（可放心依赖）

| 接入面 | 说明 |
|---|---|
| `agent.tool_layer.ControlTools` | 把"标签语法"翻译成真实输入（键盘/鼠标/手柄/绝对移动/宏/应用/回中） |
| `agent.tool_layer.ConfigTools` | 程序化读写 profile 绑定与参数 |
| `core.action_service` | 宏/应用/屏幕回中的纯函数（工具层底下，需要时也可直接用） |
| `OverlayWindow.reload_active_profile()` | 改完配置后让运行中的蛋挞热生效（**唯一伸进活应用的口子**） |
| **数据 schema + 标签语法 + action 名** | profile JSON 字段、`mouse:`/`gp:`/`xmacro:`/`app:`/`recenter:` 标签、`click/press/release` |

> ⚠️ **内部、随时会变，别直接依赖**：`RunController._smart_trigger` 及其私有方法、scene/UI 内部结构。

### 2. action 协议（决策 #2：复用现有语法）

- **action**：`click`（按下+短延迟+释放）| `press`（按住）| `release`（松开）
- **token**（多个用 `+` 连，普通键合并为组合键一次触发）：
  - 普通键：`w`、`ctrl`、`f4`、`ctrl+f4` …
  - 鼠标键：`mouse:left` / `right` / `middle` / `x1` / `x2`；滚轮 `mouse:wheelup` / `mouse:wheeldown`
  - 手柄：`gp:A` `gp:B` `gp:X` `gp:Y` `gp:LB` `gp:RB` `gp:LT` `gp:RT` `gp:Start` `gp:Back` `gp:Guide` `gp:D-Up/D-Down/D-Left/D-Right` `gp:L3` `gp:R3`
  - 宏：`xmacro:<名>`（统一池，推荐）/ `gpmacro:<名>` / `macro:<名>`
  - 启动应用：`app:<应用名>`（从 profile 的 apps 池解析路径）
  - 回中：`recenter:screen` ✅ 可 headless；`recenter:wheel` / `recenter:stick:<名>` / `recenter:center_ring` ⛔ 需运行中的窗口几何，headless 返回 `deferred`
- **返回**：`{key_str, action, ok, steps:[{part, kind, status, detail, ...}]}`，`status ∈ ok | error | skip | deferred`。

### 3. 控制工具（ControlTools）

所有方法 `@staticmethod`，**支持 `dry_run`**（决策 #3：先预演给用户确认，确认/auto 后再真跑）：

```python
from agent.tool_layer import ControlTools

# 单个绑定值（组合键正确成立）
ControlTools.run_keys("ctrl+f4", action="click", dry_run=True)        # 预演
ControlTools.run_keys("ctrl+f4", action="click")                     # 真跑

# 鼠标绝对定位
ControlTools.move_mouse(960, 540)

# 动作序列：每步 = {"keys",...} | {"delay_ms":N} | {"move":[x,y]}
ControlTools.run_sequence([
    {"keys": "ctrl+c", "action": "click", "after_ms": 50},
    {"delay_ms": 100},
    {"move": [200, 200]},
    {"keys": "mouse:wheelup", "action": "click"},
], profile=None)   # profile=None → 当前活跃方案（宏/应用从该方案查）
```

### 4. 配置工具（ConfigTools）

读写 profile；纯文件 IO + 原子写，**任意线程安全**。改完要在运行中生效，见第 6 节。

```python
from agent.tool_layer import ConfigTools

ConfigTools.list_profiles()                  # {"active": "...", "profiles": [...]}
ConfigTools.summarize_profile()              # 给 agent 看的精简摘要(按钮绑定/轮盘/语音/宏/应用)
ConfigTools.read_profile("方案名")           # 完整 dict
ConfigTools.set_button_binding(0, "hover", "ctrl+f4")   # 改按钮0的 hover 并落盘
ConfigTools.set_param("transparency", 0.5)              # 改顶层参数并落盘
```

`set_button_binding` 的 `field` 白名单：`hover/lclick/rclick/mclick/wheelup/wheeldown/xbutton1/xbutton2/hover_delay/hover_release_delay/hover_mode/hover_toggle/recenter_target`。

### 5. 线程规则（重要，别踩）

| 操作 | 可在哪个线程 |
|---|---|
| `ControlTools` 发输入（input_engine / gamepad） | **任意线程**（宏线程已这么做） |
| `ConfigTools` 读写 profile（文件 IO） | **任意线程**（原子写） |
| `reload_active_profile()` 及一切动 scene/UI 的操作 | **必须 Qt 主(GUI)线程** |

→ agent 子线程**不要直接调 `reload_active_profile()`**；应 `emit` 一个 pyqtSignal，让主线程槽函数去调（QueuedConnection 自动跨线程）。

### 6. 配置改完如何热生效

```python
# agent 子线程里：改配置（文件 IO，安全）
ConfigTools.set_button_binding(0, "hover", "ctrl+f4")
# 然后发信号回主线程
self.config_changed.emit()           # 自定义信号

# 主线程槽函数：
def _on_config_changed(self):
    self._overlay_window.reload_active_profile()   # 运行中立即生效，无需退编辑模式
```

### 7. 接一个云端 Agent 循环（照 `core/update_checker.py` 的 QThread 范式）

```python
class AgentThread(QThread):
    actions_ready = pyqtSignal(list)     # 云端返回的动作列表
    config_changed = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        # 子线程：阻塞式云端调用（HTTP/WebSocket）+ 可选截屏(需告知用户)
        result = self._call_cloud(self._prompt, screenshot=...)
        self.actions_ready.emit(result["actions"])

# 主线程接线：
agent.actions_ready.connect(self._apply_agent_actions)   # 控制类: 可直接 ControlTools.run_sequence
agent.config_changed.connect(lambda: self._window.reload_active_profile())  # 配置类: 主线程热生效
```

安全层（决策 #3）建议套在主线程"应用动作"前：默认先把动作 `dry_run` 给用户确认，auto 模式直接执行，并提供紧急中断（D4 定状态机）。

### 8. 跑验证脚本

```bash
python -m agent.headless_demo     # 工具层全路径(安全, dry-run); --live 才真实发输入
python -m agent.test_hot_reload   # 配置热重载机制(offscreen)
```

---

## 现状评估：为什么不需要大重构

蛋挞本质就是"把意图翻译成输入"的引擎，agent 要的能力它大半已有雏形。**唯一算结构改造的核心工作是抽出统一的 Agent 工具层**，其余是补能力、加接口。

### 可复用的现成能力（强）

| 层 | 现状 | 关键位置 |
|---|---|---|
| **配置层** | `config_manager` 已有完整公开 API（`load_profile`/`save_profile`/`load_hotkeys`/`save_hotkeys`）；数据是纯 dataclass（`ButtonData`/`GamepadStickData`/`VoiceCommandData` 等，带 `to_dict`/`from_dict`）；原子写（`_atomic_write_json`）。**UI 只是编辑器，不是真值来源**，可绕过 UI 程序化读写 | `core/config_manager.py`、`models/*.py` |
| **执行分派中枢** | `_smart_trigger(key_str, action)` 已按前缀分流：`mouse:` / `gp:` / `macro:` / `xmacro:` / `app:` / `recenter:` —— 这就是工具层的雏形 | `engine/run_controller.py:681` |
| **动作原语** | 键盘 `trigger/press_key/release_key`、鼠标 `mouse_press/release/wheel`、手柄 `press_button/release_button/set_stick/set_trigger/flush`、`_do_recenter`、`_launch_app`、`_execute_macro` | `core/input_engine.py`、`engine/gamepad_engine.py`、`engine/run_controller.py` |
| **并发范式** | `QThread + pyqtSignal` 已被 `VoiceEngine`/宏线程反复验证；`UpdateChecker` 已在子线程跑网络 IO 并用信号回主线程 —— 云端 agent 循环可直接照搬 | `engine/voice_engine.py`、`core/update_checker.py` |

### 缺口与进度

| # | 缺口 | 状态 | 说明 |
|---|---|---|---|
| G1 | **Agent 工具层抽象** | ✅ 已实现 | `agent/tool_layer.py` + `core/action_service.py`；执行逻辑从 RunController 解耦，运行时与 agent 共用。仅 `recenter:wheel/stick/center_ring` 仍 deferred（本质依赖运行时窗口几何） |
| G2 | **配置程序化 + 热生效** | ✅ 已实现 | `reload_active_profile()` + `prepare_hot_reload()` + `clear_all_items()`；运行中重读 profile 即生效 |
| G5 | **鼠标绝对定位** | ✅ 部分（定位） | `input_engine.mouse_move(x,y)`；**截屏部分未做**（属 G5 多模态感知，待阶段2） |
| G3 | **自然语言双路路由** | ⬜ 待做 | Vosk 是 grammar 约束只认固定短语；本地快路保留，自由 NL 分流给 agent（ASR 需加无约束转写或音频/文本直传云端） |
| G4 | **Agent 运行时** | ⬜ 待做 | 新建 `AgentThread`（照 `UpdateChecker` 写）+ 编排 + 安全/确认/中断层（见接入指南第 7 节） |
| G5b | **多模态截屏** | ⬜ 待做 | 截屏（带告知/开关），供云端多模态 agent "看屏幕"（阶段2） |

---

## 目标架构（草图）

```
                  ┌──────────── 用户入口 ────────────┐
                  │ 语音(Vosk快路)  文字聊天  对外API │
                  └──────────────┬───────────────────┘
                                 │  完整自然语言
                                 ▼
                       ┌─────────────────┐    固定短语命中 → 直接本地执行(快路)
                       │   NL 路由分流    │────────────────────────────┐
                       └────────┬────────┘                            │
                                │ 自由语言                            │
                                ▼                                     │
        ┌──────────── Agent Runtime (AgentThread, 子线程) ─────────┐ │
        │ 云端多模态模型  ·  toolset 切换(配置/控制)  ·  编排循环   │ │
        │ 感知: 截屏(告知) · 当前 profile · 屏幕坐标                 │ │
        └────────┬─────────────────────────────────────┬──────────┘ │
                 │ 工具调用 (复用标签/宏 schema)        │ 安全层      │
                 ▼                                      ▼ (确认/auto/中断)
        ┌─────────────────── Agent 工具层 (G1) ─────────────────────┐│
        │ 控制工具集: 键盘/鼠标/手柄/鼠标绝对移动/宏/启动应用/回中   ││
        │ 配置工具集: 读写 profile / 改绑定 / 改参数 / 热生效        ││
        └────────┬──────────────────────────────┬───────────────────┘│
                 ▼                               ▼                     ▼
        input_engine / gamepad_engine    config_manager        _smart_trigger
        (现成原语)                        (现成 API + G2 热生效)  (现成分派)
```

要点：
- **工具层是唯一新增的结构件**，下接现成原语，上接 agent；进程内直调，但签名按"可抽 IPC"设计。
- **安全层夹在 agent 与工具层之间**：默认拦截待确认，auto 模式放行，随时可中断。
- **双路在 NL 路由处分叉**：Vosk 命中固定短语走原有快路；自由语言进 agent。

---

## 分阶段路线图

每阶段都"先原型/调查 → 再落地"。

- **阶段 0 — 地基** ✅ **已完成**：Agent 工具层（G1）+ 配置热生效（G2）+ 鼠标绝对定位（G5 定位部分）。产出"无头操作蛋挞"能力，已有验证脚本。
- **阶段 1 — 配置助手（目标2）**：风险最低、闭环最短（读 profile→改→存→热生效），**不碰真实输入、可回滚**。用它把云端 agent 全套（鉴权/超时/流式/错误处理/确认 UI）趟通。
- **阶段 2 — 任务自动化（目标1）**：agent 规划一串鼠标键盘操作，必须带确认+中断；依赖截屏(G5)与绝对定位。
- **阶段 3 — 生成蛋挞绑定**：复用阶段0配置工具 + 阶段2感知，交叉收口。
- **阶段 4 — 实时辅助控制（最后，且需重新界定）**：⚠️ 云端 agent **物理上做不到帧级实时**（网络 RTT + 推理动辄数百 ms）。此块用本地/规则，或把"实时辅助"粒度重定义为"秒级意图介入"。**不得让此阶段阻塞前三阶段。**

**排序理由**：配置助手是"延迟无所谓 + 可回滚 + 不动真实输入"的安全试验田；实时控制是延迟物理墙，放最后并降级期望。

---

## 调查待办（产出物 + 待答问题）

| 编号 | 产出物 | 要回答的问题 |
|---|---|---|
| **D1** | 本文档（架构总纲 + 接入指南）持续迭代 | ✅ 进行中：已含接入指南；待补安全状态机细化 |
| **D2** | Tool Layer headless 原型 | ✅ 完成：`agent/tool_layer.py` + `headless_demo.py`，已验证程序化改 profile + 发输入 |
| **D3** | 延迟基线测量 | ⬜ 云端 RTT + ASR 延迟实测 → **直接决定阶段4可行性与"实时"的定义** |
| **D4** | 隐私/安全评审 | 截屏告知与开关的具体形态、误操作防护、确认/auto/中断状态机 |

---

## 风险与未决

- **实时控制的延迟墙**（最大风险）：云端方案帧级实时不可行，需 D3 实测后重新界定阶段4。
- **ASR 双路成本**：自由语言转写若放云端，涉及音频外发（隐私告知）；若本地加无约束 Vosk，识别率/资源是问题。需在 G3 选型。
- **安全层的边界**：什么动作必须确认、auto 模式的信任范围、紧急中断的快捷键，需 D4 定状态机。
- **对外 API 的鉴权与隔离**：进程内先行，但抽 IPC 时要解决鉴权、崩溃隔离、并发。
- **多模态截屏的成本/带宽/隐私**：区域截取 vs 全屏、频率、本地脱敏的取舍。

---

## 附：关键代码位置速查

**已实现（agent 接入面）**

| 功能 | 文件 |
|---|---|
| Agent 工具层 `ControlTools` / `ConfigTools` | `agent/tool_layer.py` |
| 执行服务 `find_macro/run_macro/resolve_app_path/launch_app/screen_center` | `core/action_service.py` |
| 配置热生效 `reload_active_profile` | `views/overlay_window.py` |
| 热重载前释放 `prepare_hot_reload` / `_release_all_inputs` | `engine/run_controller.py` |
| 清场 `clear_all_items` | `scene/overlay_scene.py` |
| 鼠标绝对定位 `mouse_move` | `core/input_engine.py` |
| 验证脚本 | `agent/headless_demo.py`、`agent/test_hot_reload.py` |

**基建内部（参考/后续改造点，勿直接依赖）**

| 功能 | 文件 | 位置 |
|---|---|---|
| 执行分派中枢 `_smart_trigger` | `engine/run_controller.py` | ~681 |
| 语音命令接收 `_on_voice_command`（NL 分流插入点，G3） | `engine/run_controller.py` | ~1765 |
| 键盘/鼠标原语 `trigger` / `mouse_*` | `core/input_engine.py` | — |
| 手柄原语 | `engine/gamepad_engine.py` | 93-170 |
| 配置 API `load_profile/save_profile` | `core/config_manager.py` | 730-744 |
| 子线程网络范式 `UpdateChecker`（AgentThread 照此写，G4） | `core/update_checker.py` | 68-132 |
| Vosk grammar 约束（G3 改造点） | `engine/voice_engine.py` | 225-229 |
