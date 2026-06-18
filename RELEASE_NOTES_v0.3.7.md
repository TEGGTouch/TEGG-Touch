## TEGG Touch 蛋挞 v0.3.7 (测试版)

> v0.3.5 / v0.3.6 的升级器有两个 bug 导致自动升级失败，这一版修了。

### 🐛 Bug 修复

**1. PowerShell spawn flag 错误，子进程秒退**
- 原: `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` — 在 Win11 上让 powershell 立刻被关掉，updater 根本没跑
- 改: `CREATE_NO_WINDOW` + stdin/stdout/stderr 全 DEVNULL — 后台稳跑

**2. updater.ps1 错误地把第一个子目录当成源**
- 原: 解压后 `Get-ChildItem -Directory | Select -First 1`, 按字母序取 `assets/` 作为 robocopy 源
- 改: 智能判定 — 先看 zip 根有没有 TEGGTouch.exe (我们 pack_release.bat 是平铺打包), 没有再找子目录里包了 exe 的那个

### 🛠 关键代码位置

- `core/update_installer.py:apply_update()` — spawn flags
- `core/update_installer.py:_UPDATER_PS1` + `scripts/updater_template.ps1` — src 判定 (两份必须同步)

### ⚠️ v0.3.5 / v0.3.6 用户必须手动升级一次

因为升级器代码被冻进 .exe 了，v0.3.5/v0.3.6 自己的升级器还是坏的，没法自动升 v0.3.7。

**手动办法**：
1. 从 GH 下载 `TEGGTouch_v0.3.7.zip`
2. 解压到任意空目录
3. 把解压出来的所有文件 (除了 `profiles/`、`settings/`、`logs/`、`config.json`) 覆盖到旧装目录
4. 启动 TEGGTouch.exe → 验证关于页是 v0.3.7

之后从 v0.3.7 开始自动升级就正常了，下版 v0.3.8 测试自动升级链路。
