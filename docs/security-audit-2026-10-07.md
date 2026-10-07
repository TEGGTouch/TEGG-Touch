# 开源源码与历史安装包凭证检查

检查日期：2026-10-07。此次提交目标仅为 Codeup 的 `feature/ui-inputegg`；不推送 GitHub，不创建新 Release 或上传安装包。

## 结果

**发现历史公开安装包带入开发密钥；未在已公开 Git 源码历史中检出这些密钥。**

| GitHub Release | 安装包中开发配置 | 非空凭证字段 |
| --- | --- | --- |
| v0.4.7 | `settings/agent.json` | `api_key` |
| v0.4.8 | `settings/agent.json` | `api_key`、`asr_api_key` |
| v0.5.0 | `TEGGTouch_v0.5.0/settings/agent.json` | `api_key`、`asr_api_key` |
| v0.5.1 | `settings/agent.json` | `api_key`、`asr_api_key` |
| v0.5.2 | 未含 `agent.json` | 本次检查未发现 |

v0.5.1 安装包中的两项凭证与检查时本机开发配置一致。需要立即在相应服务后台撤销并重新生成这两项密钥；清理下载文件不能代替撤销。此检查没有调用密钥验证接口，也不能判定是否已被使用。

其余 13 个公开版本（v0.1、v0.1.1、v0.2.0、v0.2.1、v0.3.1、v0.3.2、v0.4.0～v0.4.6）在本次配置检查中未发现非空凭证字段。`_internal/certifi/cacert.pem` 为公共 CA 证书，不是开发私钥。

## 范围与证据

- 从无凭证 GitHub URL 独立镜像 `TEGGTouch/TEGG-Touch` 的全部公开 refs：21 个分支 / 标签引用，211 个提交；默认分支为 `main` 的 `2b91464f37a6622261b6778acc2eb6a3377d7aa6`。检查时无公开 PR refs、子模块或 LFS 配置。
- Gitleaks v8.30.1 工具下载校验 SHA256 后运行，公开历史扫描为零命中；本地全部分支 226 个提交也为零命中。
- 对公开历史 1,240 个 blob 和本地全部分支 1,599 个 blob 逐个进行精确内容比较，包含二进制及 UTF-16 编码；本机 GitHub 令牌、OSS AccessKey ID / Secret、AI / 语音密钥和 Codeup 令牌均未命中。提交及标签消息也未命中。
- 额外检查私钥头、带凭证 URL、JWT 与长字符串凭证赋值，未检出新增命中。
- 旧源码曾包含 `config.json`、`settings/hotkeys.json`、`fkb.log`、`teggtouch.log`。前两项是窗口布局与快捷键；本次扫描没有在这些历史文件中检出凭证。
- 使用 GitHub 公开安装包 URL 的 HTTP 字节范围读取全部 18 个 ZIP 的目录与配置文件。密钥只在内存中比较；日志及本文均不含密钥值。没有执行包内程序。
- 本机 GitHub remote 含嵌入式令牌，位于本地 `.git/config`，没有进入上述 Git blob 或提交 / 标签消息；本次只推送 Codeup。

## 修复

根因是 `build.bat` 整目录复制本机 `settings`，将不受 Git 跟踪的开发配置带入公开 ZIP。

- 构建改为创建空 `settings`，由程序内置默认值初始化；保留默认方案和功能资源。
- 新增 `scripts/check_release_config.py`，构建 / 压缩前后 / 发布清单生成前检查目录或 ZIP。拦截开发设置、缓存、私钥文件及嵌套非空凭证字段；错误只显示文件名。
- 五项回归检查覆盖旧包目录布局、非空密钥、运行缓存、私钥以及正常默认方案 / 公共证书。与历史索引和 OSS 更新检查合计 27 项通过；本机 v0.5.2 ZIP 通过新校验。

## 未执行的外部处置与限制

本次没有修改服务账户、撤销密钥、删除或替换 GitHub / OSS 历史安装包，也没有重写 Git 历史。仍需处理这两项密钥和受影响下载文件；其他镜像 / 缓存可能已保留旧包。

“源码未检出”不等于所有公开产物均安全。安装包检查覆盖目录和可读配置 / 文本中的凭证，不包含对全部 EXE / DLL 的逆向分析，也不证明密钥是否已被使用或是否存在已删除且不可访问的历史资产。
