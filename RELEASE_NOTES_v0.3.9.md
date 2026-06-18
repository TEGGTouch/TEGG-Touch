## TEGG Touch 蛋挞 v0.3.9 (测试版)

> 修升级体验：v0.3.7→v0.3.8 实测时发现「主程序退出 → 新版启动」之间有 **15-20 秒空白**，用户看不到任何 UI，以为 crash 了。这版补救。

### 🪟 升级中 splash 窗口

升级器现在弹一个深色 splash 窗口（标题「蛋挞 正在升级到新版本」+ 实时状态），覆盖整个升级过程：
- 等待主程序退出...
- 正在解压新版本 (约 10-15 秒)...
- 正在替换文件...
- 正在启动新版本...

新版启动后 splash 自动关闭。

### ⏱ 主程序延迟 2 秒退出

`apply_update()` 不再立即 `app.quit()`，改用 `QTimer.singleShot(2000, app.quit)`，让 UpdateDialog 的「正在重启完成升级…」文案至少能被读到。

### 🛠 文件

- `core/update_installer.py`:
  - 嵌入的 `_UPDATER_PS1`: 加 WinForms splash + 实时状态更新
  - `apply_update()`: spawn 后延迟 2s 退出
- `scripts/updater_template.ps1`: 同步

### 怎么验证

跟 v0.3.8 测试方法一样（删 cooldown 文件 → 启动 v0.3.8 → 弹 v0.3.9 → 点立即更新），但这次：
- 升级中应该看到一个 520×220 的深色窗口，标题「蛋挞 正在升级到新版本」
- 状态行随着各阶段切换文字
- 新版启动后窗口消失
