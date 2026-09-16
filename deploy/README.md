# GitHub 开源同步与云效归档

2026-09-16 起，云效副本迁入茶叶蛋组织：

- `origin`：`git@codeup.aliyun.com:69bd03dc706afd34aa5fa6c3/TEGGTouch.git`。
- `github`：原有 <https://github.com/TEGGTouch/TEGG-Touch>，继续开源。
- 主开发分支 `main`；原有历史分支和版本标签完整保留。
- 原 `65e7c5e1db165442182db326/Yuntou/TEGGTouch.git` 已按用户要求从旧组织删除。历史已完整迁入新仓库，并另存经过验证的 Git bundle；不要再使用或重新创建旧仓库。

## 保留现有发布规则

应用仍在 Windows 上通过 `build.bat`、`pack_release.bat` 打包；本机已有的 OSS 上传辅助配置继续使用。
GitHub Release / OSS 下载地址、版本标签和官网版本更新方式保持现有规则。
提交代码后分别执行 `git push origin main` 和 `git push github main`；新增版本标签也推送到两端。
云效不保存 GitHub 写入令牌，不代替既有 Windows 打包或重新发布历史 Release。

每次发版同时按官网仓库的 `网站发布注意事项.md` 更新版本号、下载链接、双语手册和版本历史，再推送 `TEGGTouch-Web` 的 `master`。桌面源码归档不等于官网已经更新。

## 新增云效归档

流水线[“蛋挞产品版本归档”（5274494）](https://flow.aliyun.com/pipelines/5274494)由新仓库 main 的 push 触发，定义为 `deploy/pipeline.yaml`。
每次归档包含：

1. 当前 Git 提交的源码压缩包，仅含 Git 跟踪文件。
2. 若该应用版本已有 GitHub Release，下载其已发布 Windows ZIP，优先使用现有 OSS 镜像；校验 GitHub 记录的 SHA256、大小及 EXE 文件名后保存副本。
3. `manifest.json` 记录源码提交、已发布版本标签对应的提交、文件大小和 SHA256。源码提交可以包含发布后的文档更新，因此与二进制的发布标签分别记录。

未发布版本只归档源码，并在清单中明确 `binaryArchived: false`。发布 GitHub Release 后手动重跑流水线，即可补存安装包。
下载或校验失败会让已发布版本的归档失败，不把损坏文件当成功制品。
云效制品名 `teggtouch_desktop`，每次流水线序号对应独立版本；源码库和 GitHub Release 继续保留原有版本记录。

`node deploy/yunxiao.mjs status` 查看归档状态；`run` 重跑；修改 YAML 后执行 `apply`。
本机管理令牌通过 `YUNXIAO_TOKEN` / `YUNXIAO_TOKEN_FILE` 提供，本工作区默认使用与照明蛋相同的受控令牌文件；不复制到仓库或构建环境。
