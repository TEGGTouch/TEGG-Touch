# 桌面产品维护约定

- 维护前先读 [GitHub 同步、发布与云效归档规则](deploy/README.md)。
- `origin` 为茶叶蛋云效 `69bd03dc706afd34aa5fa6c3/TEGGTouch.git`；`github` 继续指向开源仓库 `TEGGTouch/TEGG-Touch`。主分支为 `main`，代码和新增版本标签按原规则同步两端。
- 旧组织 `65e7c5e1db165442182db326/Yuntou/TEGGTouch.git` 已删除，不再使用或重建。
- Windows 打包、GitHub Release 与现有 OSS 上传沿用原流程。云效流水线 5274494 负责源码及已发布安装包归档，不代替 Windows 构建。
- 新版本发出后同步维护 `TEGGTouch-Web` 官网；源码归档与官网发布是两条独立流水线。
- 保留 `.gitignore` 中本机配置、用户资料和 OSS 辅助文件的排除规则，不将凭证、运行日志或构建临时文件提交或公开。
