<p align="center">
  <h1 align="center">🎮 TEGG Touch 蛋挞</h1>
  <p align="center">
    <strong>让每个人都能享受游戏的乐趣 | Making Games Accessible for Everyone</strong>
  </p>
  <p align="center">
    <a href="https://danta.ningshen.net/">🌐 官网 Website</a> · <a href="https://github.com/TEGGTouch/TEGG-Touch/releases">📥 下载 Download</a> · <a href="#-功能特性--features">✨ 功能 Features</a> · <a href="#-联系方式--contact">🤝 联系 Contact</a>
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

## 🥮 简介 | Introduction

**TEGG Touch 蛋挞** 是一款专为 PC 环境设计的无障碍辅助软件，永久免费、完全开源。

在 PC 游戏中，传统的操作方式通常需要左手控制键盘（WASD 移动、快捷键释放技能），右手控制鼠标（视角转动、瞄准射击）——这意味着双手缺一不可。对于单手用户、手部受伤或存在肢体障碍的玩家来说，这道门槛将他们拒之门外。

**蛋挞的解决思路很简单：只用鼠标，替代一切。**

**TEGG Touch** is a free, open-source **PC gaming accessibility tool**. Traditional PC games require both hands — keyboard for movement and skills, mouse for aiming and camera. This makes many games inaccessible to one-handed users or players with limited hand mobility.

**TEGG Touch's solution is simple: replace everything with just a mouse.**

---

## 💡 工作原理 | How It Works

蛋挞在屏幕上创建一层透明的覆盖层，用户可以自由放置各种虚拟按钮和控件。当鼠标悬停或点击这些区域时，蛋挞会自动模拟对应的键盘和鼠标操作：

TEGG Touch creates a transparent overlay on your screen where you can freely place virtual buttons and controls. When you hover over or click these areas, it automatically simulates the corresponding keyboard and mouse inputs:

- **八向轮盘 | 8-Direction Wheel** — 鼠标滑向不同方向，模拟 WASD 组合键实现角色移动 / Move mouse in different directions to simulate WASD for character movement
- **自定义按钮 | Custom Buttons** — 在屏幕任意位置放置按钮，悬停或点击触发技能、交互、跳跃等 / Place buttons anywhere, trigger skills, interactions, jumps on hover or click
- **回中带 | Center Band** — 鼠标触碰即自动回到屏幕中心，解决单手视角控制难题 / Mouse auto-returns to screen center on contact, solving one-handed camera control
- **语音指令 | Voice Commands** — 说出预设口令触发按键操作，进一步解放双手 / Speak preset voice commands to trigger key actions, hands-free
- **软键盘 | Soft Keyboard** — 运行时随时呼出虚拟键盘，应对文字输入 / On-screen keyboard for text input anytime
- **智能穿透 | Smart Passthrough** — 按钮拦截操作，空白区域穿透到游戏 / Buttons intercept input, empty areas pass clicks through to the game

---

## 👥 谁可以使用蛋挞 | Who Is It For

🦾 **单手用户 | One-Handed Gamers** — 无论是先天的肢体差异，还是后天的受伤、术后恢复，只要能操作鼠标，就能玩转需要键鼠配合的游戏。Whether from a congenital condition, injury, or post-surgery recovery — if you can use a mouse, you can play.

🎮 **手部不便的玩家 | Players with Hand Difficulties** — 手指灵活度受限、握力不足、关节疼痛等情况下，蛋挞将复杂的多键操作简化为简单的鼠标移动和点击。Limited finger dexterity, weak grip, joint pain — TEGG Touch simplifies complex multi-key operations into simple mouse movements and clicks.

♿ **需要无障碍支持的用户 | Accessibility Users** — 蛋挞为 PC 游戏提供了一种全新的无障碍交互方式，让更多人有机会体验游戏的乐趣。A new way to interact with PC games without barriers, giving more people the chance to enjoy gaming.

🖱️ **所有想要简化操作的玩家 | Anyone Who Wants Simpler Controls** — 即使你双手健全，蛋挞也可以作为辅助工具，简化某些游戏中繁琐的键位操作。Even with two healthy hands, TEGG Touch can simplify tedious key bindings in certain games.

---

## ✨ 功能特性 | Features

### 核心功能 | Core Features

| 功能 Feature | 说明 Description |
|------|------|
| 🎮 **触摸按键映射 Touch-to-Key** | 全屏透明覆盖层，任意位置放置按钮，支持悬停/左右键/中键/滚轮/侧键/组合键 — Full-screen transparent overlay, place buttons anywhere, supports hover/click/scroll/combos |
| 🎡 **中心轮盘 Wheel** | 8方向虚拟摇杆 + 中心环，5种布局（small/large/double/triple/dual）— 8-direction virtual joystick + center ring, 5 layout modes |
| 📐 **回中带 Center Band** | 鼠标触碰自动归位屏幕中心，配合轮盘模拟摇杆回中 — Auto-return to screen center on contact |
| 🔀 **三态穿透 Passthrough** | 穿透ON / 智能穿透 / 不穿透 三种模式 — ON / Smart / OFF three passthrough modes |
| 🎤 **语音指令 Voice** | 离线语音识别（Vosk），支持中英文，自定义语音指令触发按键或宏 — Offline voice recognition (Vosk), Chinese & English, trigger keys or macros |
| 🔄 **宏系统 Macros** | 录制/编辑按键宏（多步骤+延迟+重复），可绑定到按钮或语音 — Record/edit key macros with delays, bind to buttons or voice |

### 辅助功能 | Additional Features

| 功能 Feature | 说明 Description |
|------|------|
| 📋 **方案管理 Profiles** | 为不同游戏保存独立配置，支持新建/复制/导入导出 — Save per-game configs, import/export |
| ⌨️ **软键盘 Soft Keyboard** | 108键标准布局，支持粘滞键和组合键 — 108-key layout with sticky keys & combos |
| 🎡 **轮盘样式 Wheel Styles** | 5种样式一键切换：小轮盘/大轮盘/双环/三环/单环双轮盘 — 5 styles: small/large/double/triple/dual |
| 🎙️ **语音测试 Voice Test** | 实时声波可视化 + 识别日志 — Real-time waveform + recognition log |
| 🌐 **多语言 i18n** | 中文 / English 双语切换 — Bilingual UI |
| 🖱️ **虚拟光标 Virtual Cursor** | 运行模式下显示虚拟光标，指示穿透状态 — Shows passthrough status in run mode |
| 🛡️ **卡键防护 Key Stuck Guard** | 退出时自动释放所有残留按键 — Auto-releases all held keys on exit |
| ⏱️ **Hover 状态机 Hover SM** | 悬停延迟激活 + 充能进度条，防误触 — Hover delay activation with charge progress bar |

---

## 🚀 快速开始 | Quick Start

### 下载即用（推荐）| Download & Run (Recommended)

前往 [Releases](https://github.com/TEGGTouch/TEGG-Touch/releases) 下载最新版 `TEGGTouch_v0.2.0.zip`，解压后右键以管理员身份运行 `TEGGTouch.exe`。

Download `TEGGTouch_v0.2.0.zip` from [Releases](https://github.com/TEGGTouch/TEGG-Touch/releases), extract and run `TEGGTouch.exe` as Administrator.

### 源码运行 | Build from Source

```bash
git clone https://github.com/TEGGTouch/TEGG-Touch.git
cd TEGG-Touch
pip install -r requirements.txt
python main.py    # 以管理员运行 / Run as Administrator
```

> ⚠️ `keyboard` 库需要管理员权限 / `keyboard` module requires Administrator privileges.

### 基本流程 | Basic Workflow

1. **启动 Launch** → 全屏透明覆盖层 + 底部工具栏 / Full-screen overlay + bottom toolbar
2. **添加按钮 Add Buttons** → 点击「按键」创建触摸区域 / Click "Button" to create touch zones
3. **编辑 Edit** → 双击按钮设置按键映射 / Double-click to set key mapping
4. **轮盘 Wheel** → 工具栏切换轮盘，双击扇区自定义 / Toggle wheel, double-click sectors to customize
5. **语音 Voice** → 打开语音设置，添加语音指令 / Open voice settings, add voice commands
6. **启动运行 Run** → 点击「▶ 启动」进入运行模式 / Click "▶ Start" to enter run mode
7. **停止 Stop** → 按 F12 返回编辑 / Press F12 to return to edit mode

---

## ⌨️ 默认快捷键 | Default Hotkeys

| 快捷键 Key | 功能 Function |
|--------|------|
| F5 | 语音识别 开/关 Toggle Voice |
| F6 | 自动回中 开/关 Toggle Auto-Center |
| F7 | 显示/隐藏按键 Show/Hide Buttons |
| F8 | 软键盘 Soft Keyboard |
| F9 | 穿透ON Pass-Through ON |
| F10 | 穿透OFF Pass-Through OFF |
| F11 | 不穿透 Block Mode |
| F12 | 停止 Stop (Edit Mode) |

> 所有快捷键可在 ⚙ 设置中自定义 / All hotkeys are customizable in Settings.

---

## 📦 打包分发 | Build & Distribution

```bash
pip install pyinstaller PyQt6 keyboard

# 打包 / Build
build.bat

# 发布包 / Release package
pack_release.bat
```

> ⚠️ 打包后 EXE 需管理员运行 / Packaged EXE requires Administrator.

---

## 📁 项目结构 | Project Structure

```
TEGGTouch-PyQt6/
├── main.py                 # 入口 / Entry point
├── core/                   # 核心逻辑 / Core logic
│   ├── constants.py        # 常量 / Constants
│   ├── config_manager.py   # 配置管理 / Config manager
│   ├── input_engine.py     # 键盘模拟 / Key simulation (SendInput)
│   └── i18n.py             # 国际化 / i18n engine
├── engine/                 # 运行引擎 / Run engine
│   ├── run_controller.py   # 运行控制器 / Run mode controller
│   ├── hover_state_machine.py  # Hover 状态机 / Hover SM
│   ├── passthrough_manager.py  # 穿透管理 / Passthrough manager
│   └── voice_engine.py     # 语音引擎 / Voice engine (Vosk)
├── scene/                  # 场景层 / Scene layer
│   ├── overlay_scene.py    # 主场景 / Main scene
│   ├── button_item.py      # 按钮 / Button item
│   ├── wheel_sector_item.py  # 轮盘扇区 / Wheel sector
│   ├── wheel_ring_item.py  # 中心环 / Center ring
│   └── virtual_cursor_item.py  # 虚拟光标 / Virtual cursor
├── views/                  # 视图层 / Views
│   ├── overlay_window.py   # 主窗口 / Main window
│   ├── edit_toolbar.py     # 编辑工具栏 / Edit toolbar
│   ├── run_toolbar.py      # 运行工具栏 / Run toolbar
│   ├── button_editor_dialog.py  # 按钮编辑 / Button editor
│   ├── macro_editor_dialog.py   # 宏编辑 / Macro editor
│   ├── voice_settings_dialog.py # 语音设置 / Voice settings
│   ├── voice_test_dialog.py     # 语音测试 / Voice test
│   ├── wheel_style_dialog.py    # 轮盘样式 / Wheel styles
│   ├── profile_manager_dialog.py  # 方案管理 / Profiles
│   └── virtual_keyboard.py # 软键盘 / Soft keyboard
├── locales/                # 语言包 / Locale files
│   ├── en.json             # English
│   └── zh-CN.json          # 简体中文
└── models/vosk/            # 语音模型 / Voice models
```

---

## 📄 开源协议 | License

本项目采用 [**CC BY-NC 4.0**](https://creativecommons.org/licenses/by-nc/4.0/) 协议。

This project is licensed under [**CC BY-NC 4.0**](https://creativecommons.org/licenses/by-nc/4.0/).

- ✅ 自由使用、复制、修改、分发 / Free to use, copy, modify, distribute
- ✅ 需注明原作者及出处 / Attribution required
- ❌ 禁止商业用途 / No commercial use

---

## 🤝 联系方式 | Contact

| 方式 Channel | 信息 Info |
|------|------|
| 🌐 **官网 Website** | [danta.ningshen.net](https://danta.ningshen.net/) |
| 🔗 **GitHub** | [TEGGTouch/TEGG-Touch](https://github.com/TEGGTouch/TEGG-Touch) |
| 💬 **微信 WeChat** | `teggwx` |
| 📧 **邮箱 Email** | `life.is.like.a.boat@gmail.com` |

欢迎提问、建议、反馈，看到一定会解答 :)

Questions, suggestions, and feedback are always welcome!
