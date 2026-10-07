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

官网在浏览器端读取 OSS JSON，自动更新最新版本/下载地址和独立历史版本页，普通发版不再需要更新网站代码或推送官网。只有功能介绍、双语手册或页面代码变化时，才按官网仓库的 `网站发布注意事项.md` 发布内容。源码归档与官网内容发布仍相互独立。

## v0.5.2 起的 OSS 更新发布

客户端只读取公开的 `https://sea-of-time.oss-cn-shanghai.aliyuncs.com/teggtouch/latest.json`，
不需要 GitHub API、代理或 OSS 密钥。清单格式见 `core/update_manifest.py`。
`pack_release.bat` 只生成本地 ZIP，不再隐式上传；本机旧辅助脚本及凭证继续忽略，不提交。

1. Windows 构建并完成测试，ZIP 文件名仍为 `TEGGTouch_v<版本>.zip`。`build.bat` 不复制本机 `settings`；缺少配置时程序使用内置默认值。构建 / 压缩 / 发布前运行 `scripts/check_release_config.py`，拦截开发凭证、`agent.json`、运行缓存及嵌套非空密钥字段；公共 CA 证书与不含凭证的方案 / 快捷键保留。
2. 在 `docs/release-notes/<版本>.md` 写更新说明；执行 `python scripts/publish_release.py` 只做本地校验。
3. 获准正式发布后执行 `python scripts/publish_release.py --publish`：先上传 ZIP，回读并验证大小/SHA256，追加 `releases.json` 历史索引，再发布 `latest.json`（两份 JSON 均 no-cache）。不要并发运行发布脚本。
4. ZIP 不覆盖同名历史版本，拒绝 preview 进入 stable 清单，拒绝将清单降级或用不同文件替换同一版本。
5. 将代码及版本标签同步 origin/github，发布同名 GitHub Release 和同一份 ZIP，供旧客户端迁移。新版运行时不依赖它。
6. 官网访问时自动读取两份 JSON。需要更新介绍/手册时才另行发布官网；最后重跑源码/二进制归档并验证。

历史索引首次建立或补录已有 OSS 文件：`python scripts/publish_release.py --sync-history`。
它只列出本项目 `teggtouch/TEGGTouch_v` 前缀的正式 ZIP，验证公开 HEAD/大小后发布 `releases.json`，不改变 `latest.json` 或安装包。正常发版自动追加，不需要每次执行补录。

旧版只认识 GitHub，不能靠上传 JSON 改变它的行为。GitHub 不通的用户需从官网手动升级一次。
SHA256 用于完整性校验，不等于发布者数字签名；清单和下载必须使用 HTTPS，OSS 写权限仅留在发布端。

## 云效归档流程

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
