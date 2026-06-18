## TEGG Touch 蛋挞 v0.3.11 (测试版)

> v0.3.9 / v0.3.10 的自动升级实际**全部失败**：updater.ps1 缺 UTF-8 BOM, Windows PowerShell 5.x 把中文当 GBK 解析 → 整脚本编译期语法报错 → PowerShell 立刻退出 → **零文件被替换**。
> 用户感知是「点了立即更新, app 关了, 没重启」, 实际安装目录还是旧版.

### 🐛 修复

`core/update_installer.py: apply_update()` 写 updater.ps1 时用 `utf-8-sig` 编码加 BOM (`EF BB BF`):

```python
with open(ps1_path, "w", encoding="utf-8-sig") as f:
    f.write(_UPDATER_PS1)
```

Windows PowerShell 5.x 检测到 BOM 后正确按 UTF-8 解码，中文不再乱码，splash 窗口能正确创建。

### ⚠️ v0.3.9 / v0.3.10 用户必须再手动升级一次

旧 binary 写 ps1 的代码冻在 .exe 里，不会自动改。**必须手动**:

1. 从 GH 下 `TEGGTouch_v0.3.11.zip`
2. 解压到任意空目录
3. 把解压出来的所有文件 (除了 `profiles/`、`settings/`、`logs/`、`config.json`) 覆盖到旧装目录
   - 提示: 如果 `%TEMP%\teggtouch_update\TEGGTouch_v0.3.10.zip` 还在, 删掉它 (148MB)
4. 启动 `TEGGTouch.exe` → 关于页应是 `v0.3.11`

之后 v0.3.11 → v0.3.12 自动升级应该全程顺畅: splash 弹出 + 状态滚动 + 重启成功.
