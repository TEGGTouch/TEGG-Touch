<p align="center">
  <h1 align="center">🎮 TEGG Touch 蛋挞</h1>
  <p align="center">
    <strong>让每个人都能享受游戏的乐趣</strong>
  </p>
  <p align="center">
    <strong>Free & Open-Source PC Gaming Accessibility Tool</strong>
  </p>
  <p align="center">
    <a href="#-快速开始--quick-start">快速开始</a> · <a href="#-功能特性--features">功能特性</a> · <a href="#-项目结构--project-structure">项目结构</a> · <a href="#-联系方式--contact">联系方式</a>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-blue" alt="Platform">
    <img src="https://img.shields.io/badge/python-3.10%2B-green" alt="Python">
    <img src="https://img.shields.io/badge/framework-PyQt6-41CD52" alt="PyQt6">
    <img src="https://img.shields.io/badge/license-CC%20BY--NC%204.0-orange" alt="License">
    <img src="https://img.shields.io/badge/version-v0.2.0-brightgreen" alt="Version">
    <img src="https://img.shields.io/badge/i18n-中文%20%7C%20English-blueviolet" alt="i18n">
  </p>
</p>

---

> **中文** ｜ [English](#english)

## 🥮 TEGG Touch 蛋挞 — 让每个人都能享受游戏的乐趣

**TEGG Touch 蛋挞** 是一款专为 PC 环境设计的无障碍辅助软件，永久免费、完全开源。

在 PC 游戏中，传统的操作方式通常需要左手控制键盘（WASD 移动、快捷键释放技能），右手控制鼠标（视角转动、瞄准射击）——这意味着双手缺一不可。对于单手用户、手部受伤或存在肢体障碍的玩家来说，这道门槛将他们拒之门外。

**蛋挞的解决思路很简单：只用鼠标，替代一切。**

蛋挞在屏幕上创建一层透明的覆盖层，用户可以自由放置各种虚拟按钮和控件。当鼠标悬停或点击这些区域时，蛋挞会自动模拟对应的键盘和鼠标操作。这意味着：

- **八向轮盘**：鼠标滑向不同方向，即可模拟 WASD 组合键实现角色移动
- **自定义按钮**：在屏幕任意位置放置按钮，悬停或点击触发技能、交互、跳跃等操作
- **回中带**：鼠标触碰即自动回到屏幕中心，解决单手操作时视角控制的难题
- **语音指令**：说出预设的语音口令即可触发按键操作，进一步解放双手
- **软键盘**：运行时可随时呼出虚拟键盘，应对临时的文字输入需求
- **智能穿透**：按钮区域拦截操作，空白区域的点击直接穿透到游戏，完全不影响正常的鼠标操作

### 谁可以使用蛋挞？

🦾 **单手用户** — 无论是先天的肢体差异，还是后天的受伤、术后恢复，只要能操作鼠标，就能玩转需要键鼠配合的游戏。

🎮 **手部不便的玩家** — 手指灵活度受限、握力不足、关节疼痛等情况下，蛋挞将复杂的多键操作简化为简单的鼠标移动和点击。

♿ **需要无障碍支持的用户** — 蛋挞为 PC 游戏提供了一种全新的无障碍交互方式，让更多人有机会体验游戏的乐趣。

🖱️ **所有想要简化操作的玩家** — 即使你双手健全，蛋挞也可以作为辅助工具，简化某些游戏中繁琐的键位操作。

### 设计理念

蛋挞的名字来自 **TEGG Touch**（Touch-Enabled Game Gateway），寓意「触碰即可通往游戏世界的大门」。我们相信，游戏的快乐不应该被身体条件所限制。一个简单的鼠标，加上蛋挞，就足够了。

---

## ✨ 功能特性 | Features

### 核心功能

| 功能 | 说明 |
|------|------|
| 🎮 **触摸按键映射** | 全屏透明覆盖层，任意位置放置触摸按钮，支持悬停 / 左右键 / 中键 / 滚轮 / 侧键，支持组合键 |
| 🎡 **中心轮盘** | 8方向虚拟摇杆 + 中心环，5种布局模式（small/large/double/triple/dual），每个扇区可自定义 |
| 📐 **回中带** | 鼠标进入后自动归位屏幕中心，零延迟，配合轮盘模拟摇杆回中 |
| 🔀 **三态穿透模式** | 穿透ON（完全穿透）/ 穿透OFF（智能穿透）/ 不穿透（全部拦截） |
| 🎤 **语音指令** | 离线语音识别（Vosk），支持中英文，自定义语音指令触发按键或宏 |
| 🔄 **宏系统** | 录制/编辑按键宏（多步骤 + 延迟 + 重复次数），可绑定到按钮或语音指令 |

### 辅助功能

| 功能 | 说明 |
|------|------|
| 📋 **多方案管理** | 为不同游戏保存独立配置，支持新建 / 复制 / 重命名 / 导入导出 |
| ⌨️ **浮动软键盘** | 108键标准布局，快速输入按键映射，支持粘滞键和组合键 |
| ⚙️ **自定义快捷键** | 所有功能键均可在设置面板中自定义，支持自定义回中延迟 |
| 🌐 **多语言支持** | 中文 / English 双语切换 |
| 🎡 **轮盘样式管理** | 5种轮盘样式一键切换：小轮盘 / 大轮盘 / 双环 / 三环 / 单环双轮盘 |
| 🎙️ **语音测试** | 实时声波可视化 + 识别日志，测试语音指令效果 |
| 🎤 **麦克风选择** | 支持指定麦克风设备，WASAPI 优先，自动检测可用设备 |
| 🖱️ **虚拟光标** | 运行模式下显示虚拟光标，实时指示穿透状态 |
| 🛡️ **按键卡住防护** | 退出运行模式或关闭程序时自动释放所有残留按键 |
| ⏱️ **Hover 状态机** | 按钮悬停支持延迟激活和充能进度条，防误触 |

---

## 🚀 快速开始 | Quick Start

### 方式一：下载即用（推荐）

前往 [Releases](https://github.com/TEGGTouch/TEGG-Touch/releases) 下载最新版 `TEGGTouch_v0.2.0.zip`，解压后右键以管理员身份运行 `TEGGTouch.exe` 即可。

### 方式二：源码运行

#### 环境要求

- **操作系统**：Windows 10 / 11
- **Python**：3.10+
- **核心依赖**：`PyQt6`（UI 框架）、`keyboard`（全局键盘钩子）
- **可选依赖**：`vosk`（离线语音识别）、`sounddevice`（麦克风输入）

#### 安装运行

```bash
# 克隆项目
git clone https://github.com/TEGGTouch/TEGG-Touch.git
cd TEGG-Touch

# 安装依赖
pip install -r requirements.txt

# 以管理员权限运行（keyboard 库需要）
python main.py
```

或者直接右键 `run.bat` → 以管理员身份运行。

> ⚠️ `keyboard` 库需要管理员权限才能全局监听键盘事件。

### 基本流程

1. **启动** → 全屏透明覆盖层 + 底部编辑工具栏
2. **添加按钮** → 点击「按键」在画布上创建触摸区域
3. **编辑按钮** → 双击按钮打开编辑面板，设置按键映射
4. **拖拽/缩放** → 拖拽移动，右下角三角手柄缩放
5. **轮盘** → 工具栏切换轮盘显示，双击扇区自定义按键
6. **语音** → 工具栏打开语音设置，添加语音指令
7. **启动运行** → 点击「▶ 启动」进入运行模式
8. **停止** → 按 F12 返回编辑模式

---

## ⌨️ 默认快捷键

| 快捷键 | 功能 | Key | Function |
|--------|------|-----|----------|
| F5 | 语音识别 开/关 | F5 | Toggle Voice |
| F6 | 自动回中 开/关 | F6 | Toggle Auto-Center |
| F7 | 显示/隐藏按键 | F7 | Show/Hide Buttons |
| F8 | 软键盘 | F8 | Soft Keyboard |
| F9 | 穿透ON | F9 | Pass-Through ON |
| F10 | 穿透OFF | F10 | Pass-Through OFF |
| F11 | 不穿透 | F11 | Block Mode |
| F12 | 停止（回编辑） | F12 | Stop (Edit Mode) |

> 所有快捷键可在 ⚙ 设置面板中自定义。

---

## 📁 项目结构 | Project Structure

```
TEGGTouch-PyQt6/
├── main.py                 # 启动入口 / Entry point
├── run.bat                 # Windows 快速启动 / Quick launch
├── build.bat               # PyInstaller 打包 / Build script
├── pack_release.bat        # 发布包打包 / Release packaging
├── requirements.txt        # Python 依赖 / Dependencies
│
├── core/                   # 核心逻辑 / Core logic
│   ├── constants.py        # 全局常量 / Constants & defaults
│   ├── config_manager.py   # 配置方案管理 / Config & profile manager
│   ├── input_engine.py     # 键盘模拟引擎 / Key simulation (SendInput API)
│   └── i18n.py             # 国际化翻译引擎 / i18n translation engine
│
├── engine/                 # 运行引擎 / Run engine
│   ├── run_controller.py   # 运行模式控制器 / Run mode controller
│   ├── hover_state_machine.py  # Hover 状态机 / Hover state machine
│   ├── passthrough_manager.py  # 窗口穿透管理 / Pass-through manager
│   └── voice_engine.py     # 语音识别引擎 / Voice recognition (Vosk)
│
├── scene/                  # 场景层 / Scene layer (QGraphicsScene)
│   ├── overlay_scene.py    # 主场景 / Main scene
│   ├── button_item.py      # 按钮图元 / Button graphics item
│   ├── wheel_sector_item.py  # 轮盘扇区 / Wheel sector item
│   ├── wheel_ring_item.py  # 轮盘中心环 / Wheel center ring
│   └── virtual_cursor_item.py  # 虚拟光标 / Virtual cursor
│
├── views/                  # 视图层 / Views (QWidgets & Dialogs)
│   ├── overlay_window.py   # 主窗口 / Main overlay window (QGraphicsView)
│   ├── edit_toolbar.py     # 编辑工具栏 / Edit toolbar
│   ├── run_toolbar.py      # 运行工具栏 / Run toolbar
│   ├── button_editor_dialog.py  # 按钮编辑弹窗 / Button editor
│   ├── center_band_dialog.py    # 回中带编辑 / Center band editor
│   ├── macro_editor_dialog.py   # 宏编辑器 / Macro editor
│   ├── voice_settings_dialog.py # 语音设置 / Voice settings
│   ├── voice_test_dialog.py     # 语音测试 / Voice test
│   ├── wheel_style_dialog.py    # 轮盘样式 / Wheel style manager
│   ├── profile_manager_dialog.py  # 方案管理 / Profile manager
│   ├── hotkey_settings_dialog.py  # 快捷键设置 / Hotkey settings
│   ├── virtual_keyboard.py # 浮动软键盘 / Soft keyboard
│   ├── voice_hud_widget.py # 语音指令HUD / Voice command HUD
│   ├── toast_widget.py     # Toast通知 / Toast notification
│   └── about_dialog.py     # 关于对话框 / About dialog
│
├── models/                 # 数据模型 / Data models
│   └── button_data.py      # 按钮数据模型 / Button data model
│
├── locales/                # 语言包 / Locale files
│   ├── en.json             # English
│   └── zh-CN.json          # 简体中文
│
├── models/vosk/            # 语音模型 / Voice models (Vosk)
├── profiles/               # 用户方案 / User profiles (JSON)
├── assets/                 # 静态资源 / Static assets
├── settings/               # 设置 / Settings
│   └── hotkeys.json        # 快捷键配置 / Hotkey config
├── tests/                  # 测试 / Tests
└── docs/                   # 开发文档 / Dev docs
```

---

## 🏗️ 架构设计 | Architecture

### PyQt6 分层架构

```
OverlayWindow (QGraphicsView)
  ├── OverlayScene (QGraphicsScene)
  │     ├── ButtonItem (QGraphicsRectItem)       → 触摸按钮
  │     ├── WheelSectorItem (QGraphicsPathItem)  → 轮盘扇区
  │     ├── WheelRingItem (QGraphicsEllipseItem) → 中心环
  │     └── VirtualCursorItem                    → 虚拟光标
  ├── RunController (QObject)                    → 运行模式控制器
  │     ├── HoverStateMachine                    → 按钮悬停状态机
  │     └── VoiceEngine (QThread)                → 语音识别引擎
  └── PassthroughManager                         → 窗口穿透管理
```

### 两种模式 | Two Modes

| | 编辑模式 Edit | 运行模式 Run |
|---|---|---|
| 工具栏 Toolbar | 底部固定 Bottom-fixed | 可拖拽 Draggable |
| 按钮交互 Buttons | 双击编辑/拖拽/缩放 | 悬停/点击触发按键 |
| 窗口 Window | 智能穿透（空白区域透传） | 无焦点（不抢游戏） |
| 光标 Cursor | 系统光标 | 虚拟光标（显示穿透状态） |
| 语音 Voice | 设置面板配置 | F5 切换开关 |

---

## 📦 打包分发 | Build & Distribution

```bash
pip install pyinstaller PyQt6 keyboard

# 使用项目提供的打包脚本
build.bat

# 打包发布版（含压缩）
pack_release.bat
```

> ⚠️ 打包后的 EXE 需以管理员身份运行（`keyboard` 库需要全局钩子权限）。

---

## 📄 开源协议 | License

本项目采用 [**CC BY-NC 4.0**](https://creativecommons.org/licenses/by-nc/4.0/) 协议。

### 你可以 | You may:
- ✅ 自由使用、复制、分发本软件
- ✅ 自由修改、二次开发
- ✅ 需注明原作者及出处

### 你不可以 | You may NOT:
- ❌ 将本软件用于任何商业目的
- ❌ 在不注明出处的情况下分发

---

## 🤝 联系方式 | Contact

| 方式 | 信息 |
|------|------|
| 💬 **微信 WeChat** | `teggwx` |
| 📧 **邮箱 Email** | `life.is.like.a.boat@gmail.com` |
| 🔗 **GitHub** | [TEGGTouch/TEGG-Touch](https://github.com/TEGGTouch/TEGG-Touch) |

欢迎提问、建议、反馈，看到一定会解答 :)

---

<a id="english"></a>

## 🇬🇧 English

### What is TEGG Touch?

**TEGG Touch** (蛋挞) is a free, open-source **PC gaming accessibility tool** designed to help users who can only use one hand, have limited hand mobility, or face other physical challenges play PC games that normally require both keyboard and mouse.

**The idea is simple: replace everything with just a mouse.**

TEGG Touch creates a transparent overlay on your screen where you can place virtual buttons and controls. When you hover over or click these areas, TEGG Touch automatically simulates the corresponding keyboard and mouse inputs.

### Who is it for?

- 🦾 **One-handed gamers** — Whether from a congenital condition, injury, or post-surgery recovery, if you can use a mouse, you can play games that require keyboard + mouse
- 🎮 **Players with hand difficulties** — Limited finger dexterity, weak grip, joint pain — TEGG Touch simplifies complex multi-key operations into simple mouse movements and clicks
- ♿ **Accessibility users** — A new way to interact with PC games without barriers
- 🖱️ **Anyone who wants simpler controls** — Even with two healthy hands, TEGG Touch can simplify tedious key bindings

### Key Features

- **8-Direction Wheel** — Move mouse in different directions to simulate WASD combinations
- **Custom Buttons** — Place buttons anywhere, trigger actions on hover or click
- **Center Band** — Mouse auto-returns to screen center on contact
- **Voice Commands** — Offline voice recognition (Vosk), supports Chinese & English
- **Macro System** — Record/edit key sequences with delays, bind to buttons or voice
- **5 Wheel Layouts** — Small / Large / Double / Triple / Dual ring configurations
- **Smart Passthrough** — Buttons intercept input, empty areas pass clicks through to the game
- **Soft Keyboard** — On-screen 108-key keyboard for quick text input
- **Profile Manager** — Save/load/import/export configurations for different games
- **Bilingual** — Chinese / English UI

### Quick Start

Download from [Releases](https://github.com/TEGGTouch/TEGG-Touch/releases) — extract and run `TEGGTouch.exe` as Administrator.

Or build from source:

```bash
git clone https://github.com/TEGGTouch/TEGG-Touch.git
cd TEGG-Touch
pip install -r requirements.txt
python main.py    # Run as Administrator
```

### License

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — Free to use & modify, **no commercial use**.

### Contact

- **WeChat**: `teggwx`
- **Email**: `life.is.like.a.boat@gmail.com`
- **GitHub**: [TEGGTouch/TEGG-Touch](https://github.com/TEGGTouch/TEGG-Touch)
