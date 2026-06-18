## TEGG Touch 蛋挞 v0.3.13 (测试版)

> 修升级器 disk-leak: 下载新 zip 前没清旧的, 每次失败留 148MB, 多次后 C 盘爆 → `Expand-Archive` 报「磁盘空间不足」.

### 🐛 修复

`UpdateInstaller.run()` 开始下载前, 先清空 `%TEMP%\teggtouch_update\` 里所有旧文件 (zip + ps1):

```python
for f in os.listdir(tmp_dir):
    fp = os.path.join(tmp_dir, f)
    if os.path.isfile(fp):
        os.remove(fp)
```

这样每次升级前自动腾出空间, 不再累积.

### ⚠️ v0.3.11 / v0.3.12 用户先手动清

旧 binary 没这逻辑, 升级前需手动删:
```
C:\Users\<你>\AppData\Local\Temp\teggtouch_update\*.zip
```

清完之后再点立即更新, 应该顺利装上 v0.3.13.
