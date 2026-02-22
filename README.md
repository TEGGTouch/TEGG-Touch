<p align="center">
  <h1 align="center">🎮 TEGG Touch 蛋挞</h1>
  <p align="center">
    <strong>免费开源的触屏按键映射工具 | Free & Open-Source Touch-to-Key Mapper</strong>
  </p>
  <p align="center">
    <a href="#-快速开始--quick-start">快速开始</a> · <a href="#-功能特性--features">功能特性</a> · <a href="#-项目结构--project-structure">项目结构</a> · <a href="#-联系方式--contact">联系方式</a>
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

> **中文** ｜ [English](#english)

## 🥮 简介

**TEGG Touch 蛋挞** 是一款永久免费、完全开源的 Windows 无障碍辅助软件。

仅仅用鼠标简单的移动和点击，就能替代大部分的游戏操作。我们希望能帮到有需求的用户，让大家都能体会到游戏的乐趣。

适用场景：触屏玩 PC 游戏、远程桌面操控、辅助操作、游戏直播等。

---

## ✨ 功能特性 | Features

| 功能 | 说明 |
|------|------|
| 🎮 **触摸按键映射** | 全屏透明覆盖层，任意位置放置触摸按钮，支持悬停 / 左右键 / 中键 / 滚轮 / 侧键，支持组合键 |
| 🎡 **中心轮盘** | 8方向虚拟摇杆，默认映射 WASD 方向组合，每个扇区可自定义 |
| 📐 **回中带** | 鼠标进入后自动归位屏幕中心，零延迟，配合轮盘模拟摇杆回中 |
| 🔀 **三态穿透模式** | 穿透ON（完全穿透）/ 穿透OFF（智能穿透）/ 不穿透（全部拦截） |
| 📋 **多方案管理** | 为不同游戏保存独立配置，支持新建 / 复制 / 重命名 / 导入导出 |
| ⌨️ **浮动软键盘** | 108键标准布局，快速输入按键映射，支持粘滞键和组合键 |
| ⚙️ **自定义快捷键** | 所有功能键均可在设置面板中自定义，支持自定义回中延迟 |
| 🌐 **多语言支持** | 中文 / English 双语切换 |

---

## 🚀 快速开始 | Quick Start

### 环境要求

- **操作系统**：Windows 10 / 11
- **Python**：3.10+
- **依赖库**：`keyboard`（全局键盘钩子）、`Pillow`（图片加载）

### 安装运行

```bash
# 克隆项目
git clone https://github.com/TEGGTouch/TEGG-Touch.git
cd TEGG-Touch

# 安装依赖
pip install keyboard Pillow

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
5. **启动运行** → 点击「▶ 启动」进入运行模式
6. **停止** → 按 F12 返回编辑模式

---

## ⌨️ 默认快捷键

| 快捷键 | 功能 | Key | Function |
|--------|------|-----|----------|
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
TEGGTouch/
├── main.py                 # 启动入口 / Entry point
├── run.bat                 # Windows 快速启动 / Quick launch
├── build.bat               # PyInstaller 打包 / Build script
│
├── core/                   # 核心逻辑 / Core logic
│   ├── constants.py        # 全局常量 / Constants & defaults
│   ├── config_manager.py   # 配置方案管理 / Config & profile manager
│   ├── input_engine.py     # 键盘模拟引擎 / Key simulation engine
│   └── i18n.py             # 国际化翻译引擎 / i18n translation engine
│
├── ui/                     # 界面层 / UI layer (Tkinter Canvas)
│   ├── app.py              # 主应用 (Mixin 架构) / Main app
│   ├── toolbar.py          # 编辑/运行工具栏 / Edit & Run toolbars
│   ├── canvas_renderer.py  # 画布渲染 / Canvas rendering
│   ├── button_editor.py    # 按钮编辑弹窗 / Button editor dialog
│   ├── button_manager.py   # 按钮增删改 / Button CRUD (Mixin)
│   ├── run_engine.py       # 运行模式引擎 / Run mode engine (Mixin)
│   ├── window_manager.py   # 窗口穿透管理 / Window style (Mixin)
│   ├── profile_manager.py  # 方案管理弹窗 / Profile manager
│   ├── hotkey_settings.py  # 快捷键设置 / Hotkey settings
│   ├── virtual_keyboard.py # 浮动软键盘 / Soft keyboard
│   ├── widgets.py          # 通用组件 / Common widgets
│   └── about_dialog.py     # 关于对话框 / About dialog
│
├── locales/                # 语言包 / Locale files
│   ├── en.json             # English
│   └── zh-CN.json          # 简体中文
│
├── profiles/               # 用户方案 / User profiles (JSON)
├── assets/                 # 静态资源 / Static assets
├── settings/               # 设置 / Settings
│   └── hotkeys.json        # 快捷键配置 / Hotkey config
└── docs/                   # 开发文档 / Dev docs
```

---

## 🏗️ 架构设计 | Architecture

### Mixin 组合架构

```
FloatingApp
  ├── WindowStyleMixin   → 窗口穿透/焦点控制 / Window pass-through
  ├── RunEngineMixin     → 运行模式核心循环 / Run mode loop
  └── ButtonManagerMixin → 按钮增删改拖拽缩放 / Button CRUD & drag
```

### 坐标系 | Coordinate System

采用**中心原点坐标系**：原点 `(0,0)` 在屏幕正中心，方便按钮在不同分辨率下保持相对位置。

Center-origin coordinate system: `(0,0)` at screen center, preserving relative button positions across resolutions.

### 两种模式 | Two Modes

| | 编辑模式 Edit | 运行模式 Run |
|---|---|---|
| 工具栏 Toolbar | 底部固定 Bottom-fixed | 可拖拽 Draggable |
| 按钮交互 Buttons | 双击编辑/拖拽/缩放 | 悬停/点击触发按键 |
| 窗口 Window | 普通（可交互） | 无焦点（不抢游戏） |
| 光标 Cursor | 系统光标 | 虚拟光标（显示穿透状态） |

---

## 📦 打包分发 | Build & Distribution

```bash
pip install pyinstaller Pillow

# 使用项目提供的打包脚本
build.bat
```

或手动：

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

---

## 📄 开源协议 | License

本项目采用 [**CC BY-NC 4.0**](https://creativecommons.org/licenses/by-nc/4.0/) 协议。

This project is licensed under [**Creative Commons Attribution-NonCommercial 4.0 International**](https://creativecommons.org/licenses/by-nc/4.0/).

### 你可以 | You may:
- ✅ 自由使用、复制、分发本软件 / Use, copy, and distribute freely
- ✅ 自由修改、二次开发 / Modify and create derivative works
- ✅ 需注明原作者及出处 / Must give appropriate credit

### 你不可以 | You may NOT:
- ❌ 将本软件用于任何商业目的 / Use for any commercial purpose
- ❌ 在不注明出处的情况下分发 / Distribute without attribution

详见 [LICENSE](./LICENSE) 文件。See [LICENSE](./LICENSE) for details.

---

## 🤝 联系方式 | Contact

| 方式 | 信息 |
|------|------|
| 💬 **微信 WeChat** | `teggwx` |
| 📧 **邮箱 Email** | `life.is.like.a.boat@gmail.com` |

欢迎提问、建议、反馈，看到一定会解答 :)

Questions, suggestions, and feedback are always welcome!

---

<a id="english"></a>

## 🇬🇧 English

### What is TEGG Touch?

**TEGG Touch** is a free, open-source accessibility tool for Windows that maps touch/mouse input to keyboard actions. With simple mouse movements and clicks, it can replace most game controls — bringing the joy of gaming to everyone.

### Key Features

- **Touch-to-Key Mapping** — Full-screen transparent overlay with customizable touch buttons (hover, click, scroll, side-buttons, combos)
- **Center Wheel** — 8-direction virtual joystick with WASD mapping
- **Auto-Center Band** — Mouse instantly returns to screen center on contact
- **3-State Pass-Through** — ON (full) / OFF (smart) / Block (all intercepted)
- **Multi-Profile** — Save profiles per game, import/export JSON
- **Soft Keyboard** — 108-key floating keyboard with sticky modifier keys
- **i18n** — English & Chinese UI

### Quick Start

```bash
git clone https://github.com/TEGGTouch/TEGG-Touch.git
cd TEGG-Touch
pip install keyboard Pillow
python main.py    # Run as Administrator
```

### License

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — Free to use & modify, **no commercial use**.

### Contact

- **WeChat**: `teggwx`
- **Email**: `life.is.like.a.boat@gmail.com`
