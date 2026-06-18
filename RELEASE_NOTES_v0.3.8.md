## TEGG Touch 蛋挞 v0.3.8 (测试版)

> 这一版**没有功能改动**，只是真正测试 v0.3.7 修过 bug 的自动升级器：v0.3.7 用户应该能点「立即更新」→ 自动下载 → 解压覆盖 → 保留 profiles/settings → 重启到 v0.3.8。

### 怎么测

1. 装好的 v0.3.7 先**别启动**
2. 删 `<安装目录>\settings\last_update_check.json`（清掉 24h 检查冷却）
3. 启动 `TEGGTouch.exe`
4. **等 3 秒**，应该弹「发现新版本 v0.3.8」
5. 点「立即更新」→ 进度条走完到 100% → 状态变「正在重启完成升级…」
6. 主程序自动退出 → 等 1-2 秒 → 新版自动启动
7. 打开设置→关于：版本应该是 `v0.3.8`、更新日期 `2026.06.19`
8. 检查 `profiles/` `settings/hotkeys.json` 都没被动
9. 检查 `%TEMP%\teggtouch_update\` 应该是空的（zip 和临时解压目录被删了）

### 失败排查

`%TEMP%\teggtouch_updater.log` 是 PowerShell 升级器的全程日志，出问题先看这个。
`<安装目录>\logs\` 里最新的 log 是主程序的，下载阶段的日志在这里。

### 这一版改了什么

- `core/constants.py`: `APP_VERSION` `0.3.7` → `0.3.8`
- `views/hotkey_settings_dialog.py`: `_ABOUT_LAST_UPDATE` `2026.06.18` → `2026.06.19`（升级是否成功的肉眼标志）
