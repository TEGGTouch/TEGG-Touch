<p align="center">
  <h1 align="center">🎮 TEGG Touch 蛋挞</h1>
  <p align="center">
    <strong>免费开源的触屏按键映射工具 | Free & Open-Source Touch-to-Key Mapper</strong>
  </p>
  <p align="center">
    <a href="#-快速开始--quick-start">快速开始 Quick Start</a> · <a href="#-功能特性--features">功能特性 Features</a> · <a href="#-项目结构--project-structure">项目结构 Structure</a> · <a href="#-联系方式--contact">联系方式 Contact</a>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-blue" alt="Platform">
    <img src="https://img.shields.io/badge/python-3.10%2B-green" alt="Python">
    <img src="https://img.shields.io/badge/license-CC%20BY--NC%204.0-orange" alt="License">
    <img src="https://img.shields.io/badge/version-v0.1.1-brightgreen" alt="Version">
    <img src="https://img.shields.io/badge/i18n-中文%20%7C%20English-blueviolet" alt="i18n">
  </p>
</p>

---

## 🥮 简介 | Introduction

**TEGG Touch 蛋挞** 是一款永久免费、完全开源的 Windows 无障碍辅助软件。

仅仅用鼠标简单的移动和点击，就能替代大部分的游戏操作。我们希望能帮到有需求的用户，让大家都能体会到游戏的乐趣。

适用场景：触屏玩 PC 游戏、远程桌面操控、辅助操作、游戏直播等。

**TEGG Touch** is a free, open-source accessibility tool for Windows that maps touch/mouse input to keyboard actions.

With simple mouse movements and clicks, it can replace most game controls — bringing the joy of gaming to everyone.

Use cases: touchscreen PC gaming, remote desktop control, assistive operation, game streaming, etc.

---

## ✨ 功能特性 | Features

| 功能 Feature | 说明 Description |
|------|------|
| 🎮 **触摸按键映射 Touch-to-Key** | 全屏透明覆盖层，任意位置放置触摸按钮，支持悬停 / 左右键 / 中键 / 滚轮 / 侧键，支持组合键 · Full-screen transparent overlay with customizable touch buttons (hover, click, scroll, side-buttons, combos) |
| 🎡 **中心轮盘 Center Wheel** | 8方向虚拟摇杆，默认映射 WASD 方向组合，每个扇区可自定义 · 8-direction virtual joystick with WASD mapping, each sector customizable |
| 📐 **回中带 Auto-Center Band** | 鼠标进入后自动归位屏幕中心，零延迟，配合轮盘模拟摇杆回中 · Mouse instantly returns to screen center on contact, zero-delay |
| 🔀 **三态穿透 3-State Pass-Through** | 穿透ON（完全穿透）/ 穿透OFF（智能穿透）/ 不穿透（全部拦截） · ON (full) / OFF (smart) / Block (all intercepted) |
| 📋 **多方案管理 Multi-Profile** | 为不同游戏保存独立配置，支持新建 / 复制 / 重命名 / 导入导出 · Save profiles per game, import/export JSON |
| ⌨️ **浮动软键盘 Soft Keyboard** | 108键标准布局，快速输入按键映射，支持粘滞键和组合键 · 108-key floating keyboard with sticky modifier keys |
| ⚙️ **自定义快捷键 Custom Hotkeys** | 所有功能键均可在设置面板中自定义，支持自定义回中延迟 · All hotkeys customizable in settings panel |
| 🌐 **多语言 i18n** | 中文 / English 双语切换 · Chinese & English UI |

---

## 🚀 快速开始 | Quick Start

### 环境要求 | Requirements

- **操作系统 OS**：Windows 10 / 11
- **Python**：3.10+
- **依赖库 Dependencies**：`keyboard`（全局键盘钩子 global keyboard hooks）、`Pillow`（图片加载 image loading）

### 安装运行 | Install & Run

```bash
# 克隆项目 Clone
git clone https://github.com/TEGGTouch/TEGG-Touch.git
cd TEGG-Touch

# 安装依赖 Install dependencies
pip install keyboard Pillow

# 以管理员权限运行 Run as Administrator (required by keyboard lib)
python main.py
```

或者直接右键 `run.bat` → 以管理员身份运行。

Or right-click `run.bat` → Run as Administrator.

> ⚠️ `keyboard` 库需要管理员权限才能全局监听键盘事件。
> 
> ⚠️ The `keyboard` library requires administrator privileges for global keyboard hooks.

### 基本流程 | Basic Workflow

1. **启动 Launch** → 全屏透明覆盖层 + 底部编辑工具栏 · Full-screen transparent overlay + bottom toolbar
2. **添加按钮 Add Button** → 点击「按键」在画布上创建触摸区域 · Click "Button" to create a touch zone
3. **编辑按钮 Edit Button** → 双击按钮打开编辑面板，设置按键映射 · Double-click to open editor, set key mapping
4. **拖拽/缩放 Drag/Resize** → 拖拽移动，右下角三角手柄缩放 · Drag to move, corner handle to resize
5. **启动运行 Start** → 点击「▶ 启动」进入运行模式 · Click "▶ Start" to enter run mode
6. **停止 Stop** → 按 F12 返回编辑模式 · Press F12 to return to edit mode

---

## ⌨️ 默认快捷键 | Default Hotkeys

| 快捷键 Key | 功能 Function |
|--------|------|
| F6 | 自动回中 开/关 · Toggle Auto-Center |
| F7 | 显示/隐藏按键 · Show/Hide Buttons |
| F8 | 软键盘 · Soft Keyboard |
| F9 | 穿透ON · Pass-Through ON |
| F10 | 穿透OFF · Pass-Through OFF |
| F11 | 不穿透 · Block Mode |
| F12 | 停止（回编辑） · Stop (Edit Mode) |

> 所有快捷键可在 ⚙ 设置面板中自定义。
> 
> All hotkeys are customizable in the ⚙ Settings panel.

---

## 📁 项目结构 | Project Structure

```
TEGGTouch/
├── main.py                 # 启动入口 Entry point
├── run.bat                 # Windows 快速启动 Quick launch
├── build.bat               # PyInstaller 打包 Build script
│
├── core/                   # 核心逻辑 Core logic
│   ├── constants.py        # 全局常量 Constants & defaults
│   ├── config_manager.py   # 配置方案管理 Config & profile manager
│   ├── input_engine.py     # 键盘模拟引擎 Key simulation engine
│   └── i18n.py             # 国际化翻译引擎 i18n translation engine
│
├── ui/                     # 界面层 UI layer (Tkinter Canvas)
│   ├── app.py              # 主应用 (Mixin 架构) Main app
│   ├── toolbar.py          # 编辑/运行工具栏 Edit & Run toolbars
│   ├── canvas_renderer.py  # 画布渲染 Canvas rendering
│   ├── button_editor.py    # 按钮编辑弹窗 Button editor dialog
│   ├── button_manager.py   # 按钮增删改 Button CRUD (Mixin)
│   ├── run_engine.py       # 运行模式引擎 Run mode engine (Mixin)
│   ├── window_manager.py   # 窗口穿透管理 Window style (Mixin)
│   ├── profile_manager.py  # 方案管理弹窗 Profile manager
│   ├── hotkey_settings.py  # 快捷键设置 Hotkey settings
│   ├── virtual_keyboard.py # 浮动软键盘 Soft keyboard
│   ├── widgets.py          # 通用组件 Common widgets
│   └── about_dialog.py     # 关于对话框 About dialog
│
├── locales/                # 语言包 Locale files
│   ├── en.json             # English
│   └── zh-CN.json          # 简体中文
│
├── profiles/               # 用户方案 User profiles (JSON)
├── assets/                 # 静态资源 Static assets
├── settings/               # 设置 Settings
│   └── hotkeys.json        # 快捷键配置 Hotkey config
└── docs/                   # 开发文档 Dev docs
```

---

## 🏗️ 架构设计 | Architecture

### Mixin 组合架构 | Mixin Composition

```
FloatingApp
  ├── WindowStyleMixin   → 窗口穿透/焦点控制 Window pass-through
  ├── RunEngineMixin     → 运行模式核心循环 Run mode loop
  └── ButtonManagerMixin → 按钮增删改拖拽缩放 Button CRUD & drag
```

### 坐标系 | Coordinate System

采用**中心原点坐标系**：原点 `(0,0)` 在屏幕正中心，方便按钮在不同分辨率下保持相对位置。

Center-origin coordinate system: `(0,0)` at screen center, preserving relative button positions across resolutions.

### 两种模式 | Two Modes

| | 编辑模式 Edit | 运行模式 Run |
|---|---|---|
| 工具栏 Toolbar | 底部固定 Bottom-fixed | 可拖拽 Draggable |
| 按钮交互 Buttons | 双击编辑/拖拽/缩放 Edit/Drag/Resize | 悬停/点击触发按键 Hover/Click triggers |
| 窗口 Window | 普通（可交互）Normal | 无焦点（不抢游戏）No-focus |
| 光标 Cursor | 系统光标 System | 虚拟光标（显示穿透状态）Virtual |

---

## 📦 打包分发 | Build & Distribution

```bash
pip install pyinstaller Pillow

# 使用项目提供的打包脚本 Use the build script
build.bat
```

或手动 Or manually:

```bash
pyinstaller --onefile --windowed --name "TEGGTouch" ^
  --add-data "profiles;profiles" ^
  --add-data "assets;assets" ^
  --add-data "settings;settings" ^
  --add-data "locales;locales" ^
  --add-data "core/default_profile.json;core" ^
  main.py
```

> ⚠️ 打包后的 EXE 需以管理员身份运行（`keyboard` 库需要全局钩子权限）。
> 
> ⚠️ The packaged EXE must be run as Administrator (`keyboard` requires global hook privileges).

---

## 📄 开源协议 | License

本项目采用 [**CC BY-NC 4.0**](https://creativecommons.org/licenses/by-nc/4.0/) 协议。

This project is licensed under [**Creative Commons Attribution-NonCommercial 4.0 International**](https://creativecommons.org/licenses/by-nc/4.0/).

### 你可以 | You may:
- ✅ 自由使用、复制、分发本软件 · Use, copy, and distribute freely
- ✅ 自由修改、二次开发 · Modify and create derivative works
- ✅ 需注明原作者及出处 · Must give appropriate credit

### 你不可以 | You may NOT:
- ❌ 将本软件用于任何商业目的 · Use for any commercial purpose
- ❌ 在不注明出处的情况下分发 · Distribute without attribution

详见 [LICENSE](./LICENSE) 文件。See [LICENSE](./LICENSE) for details.

---

## 🤝 联系方式 | Contact

| 方式 Channel | 信息 Info |
|------|------|
| 💬 **微信 WeChat** | `teggwx` |
| 📧 **邮箱 Email** | `life.is.like.a.boat@gmail.com` |

欢迎提问、建议、反馈，看到一定会解答 :)

Questions, suggestions, and feedback are always welcome!
