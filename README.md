<p align="center">
  <h1 align="center">🎮 TEGG Touch 蛋挞 — PyQt6 重构版</h1>
  <p align="center">
    <strong>免费开源的触屏按键映射工具 | Free & Open-Source Touch-to-Key Mapper</strong>
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

## 🥮 简介

**TEGG Touch 蛋挞 PyQt6** 是原版 [TEGG Touch](https://github.com/TEGGTouch/TEGG-Touch)（Tkinter）的完整重构版本，基于 **PyQt6 QGraphicsView/QGraphicsScene** 架构重写。

仅用鼠标简单的移动和点击，就能替代大部分游戏操作。我们希望帮到有需求的用户，让大家都能体会到游戏的乐趣。

适用场景：触屏玩 PC 游戏、远程桌面操控、辅助操作、游戏直播等。

### 🆕 相比原版的改进

| 改进 | 说明 |
|------|------|
| 🏗️ **PyQt6 架构** | 从 Tkinter Canvas Mixin 重构为 QGraphicsView/Scene，渲染更流畅、扩展性更强 |
| 🎤 **语音识别** | 集成 Vosk 离线语音引擎，支持语音指令触发按键/宏 |
| 🔄 **宏系统** | 支持录制和编辑宏序列（按键+延迟），可绑定到按钮或语音指令 |
| 🎡 **多种轮盘模式** | small / large / double / dual 四种轮盘布局，内外双圈可独立配置 |
| 🛡️ **按键卡住防护** | 退出运行模式或关闭程序时自动释放所有残留按键，防止卡键 |
| ⏱️ **Hover 状态机** | 按钮悬停支持延迟激活和充能进度条，防误触 |
| 🖱️ **虚拟光标** | 运行模式下显示虚拟光标，实时指示穿透状态 |

---

## ✨ 功能特性 | Features

| 功能 | 说明 |
|------|------|
| 🎮 **触摸按键映射** | 全屏透明覆盖层，任意位置放置触摸按钮，支持悬停 / 左右键 / 中键 / 滚轮 / 侧键，支持组合键 |
| 🎡 **中心轮盘** | 8方向虚拟摇杆 + 中心环，多种布局模式（small/large/double/dual），每个扇区可自定义 |
| 📐 **回中带** | 鼠标进入后自动归位屏幕中心，零延迟，配合轮盘模拟摇杆回中 |
| 🔀 **三态穿透模式** | 穿透ON（完全穿透）/ 穿透OFF（智能穿透）/ 不穿透（全部拦截） |
| 📋 **多方案管理** | 为不同游戏保存独立配置，支持新建 / 复制 / 重命名 / 导入导出 |
| ⌨️ **浮动软键盘** | 108键标准布局，快速输入按键映射，支持粘滞键和组合键 |
| 🎤 **语音指令** | 离线语音识别（Vosk），自定义语音指令触发按键或宏 |
| 🔄 **宏序列** | 录制/编辑按键宏（多步骤 + 延迟 + 重复次数），可绑定到按钮或语音 |
| ⚙️ **自定义快捷键** | 所有功能键均可在设置面板中自定义，支持自定义回中延迟 |
| 🌐 **多语言支持** | 中文 / English 双语切换 |

---

## 🚀 快速开始 | Quick Start

### 环境要求

- **操作系统**：Windows 10 / 11
- **Python**：3.10+
- **核心依赖**：`PyQt6`（UI 框架）、`keyboard`（全局键盘钩子）
- **可选依赖**：`vosk`（离线语音识别）、`sounddevice`（麦克风输入）

### 安装运行

```bash
# 克隆项目
git clone <repo-url>
cd TEGGTouch-PyQt6

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
6. **启动运行** → 点击「▶ 启动」进入运行模式
7. **停止** → 按 F12 返回编辑模式

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
│   ├── macro_editor_dialog.py   # 宏编辑器 / Macro editor
│   ├── voice_settings_dialog.py # 语音设置 / Voice settings
│   ├── profile_manager_dialog.py  # 方案管理 / Profile manager
│   ├── hotkey_settings_dialog.py  # 快捷键设置 / Hotkey settings
│   ├── virtual_keyboard.py # 浮动软键盘 / Soft keyboard
│   └── about_dialog.py     # 关于对话框 / About dialog
│
├── models/                 # 数据模型 / Data models
│   └── button_data.py      # 按钮数据模型 / Button data model
│
├── locales/                # 语言包 / Locale files
│   ├── en.json             # English
│   └── zh-CN.json          # 简体中文
│
├── profiles/               # 用户方案 / User profiles (JSON)
├── assets/                 # 静态资源 / Static assets
├── settings/               # 设置 / Settings
│   └── hotkeys.json        # 快捷键配置 / Hotkey config
├── tests/                  # 测试 / Tests
└── docs/                   # 开发文档 / Dev docs
```

---

## 🏗️ 架构设计 | Architecture

### PyQt6 分层架构（替代原版 Tkinter Mixin）

```
OverlayWindow (QGraphicsView)
  ├── OverlayScene (QGraphicsScene)
  │     ├── ButtonItem (QGraphicsRectItem)     → 触摸按钮
  │     ├── WheelSectorItem (QGraphicsPathItem) → 轮盘扇区
  │     ├── WheelRingItem (QGraphicsEllipseItem) → 中心环
  │     └── VirtualCursorItem                   → 虚拟光标
  ├── RunController (QObject)                   → 运行模式控制器
  │     ├── HoverStateMachine                   → 按钮悬停状态机
  │     └── VoiceEngine                         → 语音识别引擎
  └── PassthroughManager                        → 窗口穿透管理
```

### 坐标系 | Coordinate System

采用**中心原点坐标系**：原点 `(0,0)` 在屏幕正中心，方便按钮在不同分辨率下保持相对位置。

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

欢迎提问、建议、反馈，看到一定会解答 :)

---

<a id="english"></a>

## 🇬🇧 English

### What is TEGG Touch PyQt6?

**TEGG Touch PyQt6** is a complete rewrite of the original [TEGG Touch](https://github.com/TEGGTouch/TEGG-Touch) (Tkinter) using the **PyQt6 QGraphicsView/Scene** framework. It's a free, open-source accessibility tool for Windows that maps touch/mouse input to keyboard actions.

### Key Improvements over v0.1 (Tkinter)

- **PyQt6 Architecture** — QGraphicsView/Scene replaces Tkinter Canvas Mixin for smoother rendering
- **Voice Recognition** — Offline voice commands via Vosk engine
- **Macro System** — Record/edit key sequences with delays, bind to buttons or voice
- **Multiple Wheel Layouts** — small / large / double / dual with independent inner/outer rings
- **Key Stuck Protection** — Auto-releases all held keys when stopping or closing
- **Hover State Machine** — Configurable activation delay with charge progress bar

### Quick Start

```bash
git clone <repo-url>
cd TEGGTouch-PyQt6
pip install -r requirements.txt
python main.py    # Run as Administrator
```

### License

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — Free to use & modify, **no commercial use**.

### Contact

- **WeChat**: `teggwx`
- **Email**: `life.is.like.a.boat@gmail.com`
