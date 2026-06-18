## TEGG Touch 蛋挞 v0.3.6 (测试版)

> 这一版**没有功能改动**，只是为了**触发自动升级流程**：v0.3.5 用户点「立即更新」应该自动下载 → 解压覆盖 → 保留 profiles/settings/config → 重启到 v0.3.6。

### 怎么验证升级成功

1. 启动 v0.3.5（已装到测试目录）
2. 打开设置 → 关于页，确认版本是 `v0.3.5`、更新日期 `2026.06.07`
3. 删 `settings/last_update_check.json` 跳过 24h 冷却 → 重启 app
4. 自动弹窗「发现新版本 v0.3.6」
5. 点「立即更新」→ 进度条走完 → app 自动重启
6. 重启后再打开关于页：
   - 版本应为 `v0.3.6`
   - 更新日期应为 `2026.06.18`
7. 确认 profiles / settings 没动；`%TEMP%` 下没有遗留的 `TEGGTouch_v0.3.6.zip`

### 升级失败排查

`%TEMP%\teggtouch_updater.log` 记录了 PowerShell 升级器的全过程，出问题先看这个。

### 这一版改了什么

- `core/constants.py`: `APP_VERSION` `0.3.5` → `0.3.6`
- `views/hotkey_settings_dialog.py`: `_ABOUT_LAST_UPDATE` `2026.06.07` → `2026.06.18`（用作升级是否成功的肉眼可见标志）

后续 v0.3.7 / v0.3.8 视情况验证镜像 fallback / 跨多版升级，全部通过后再发正式 **v0.4.0**。
