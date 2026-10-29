# 捕获入口与排障

项目路径是本仓库根目录，可用 `WECHAT_REPORT_PROJECT` 或启动器 `--project` 指定。本 skill 依赖项目 `.venv`、`wechat_report`、`runtime.local.json` 和用户授权创建的 `.runtime/WeChat-reader.app`。首次安装与副本准备见根目录 README。账号、微信二进制、私密报告都不进入技能仓库。

先读取项目 README；更换客户端或需要改读取器时再读 `docs/RESEARCH.md`、`docs/VALIDATION.md`。采用的开源研究来源、固定提交与 MIT 许可在 `THIRD_PARTY_NOTICES.md`，不要重复联网下载未经核查的取密钥工具。

以下示例中的群名只用于演示，实际替换为本次目标。`SKILL_DIR` 表示本 SKILL.md 所在目录；正常安装为 `~/.codex/skills/wechat-group-digest`。

```bash
cd '/path/to/wechat-group-digest'
.venv/bin/python skills/wechat-group-digest/scripts/start_capture.py \
  --group '完整群名' --hours 24 --launch
```

- 支持 `--hours 48` / `--hours 72`。
- 自定义窗口使用 `--start '2026-10-27T09:00:00-07:00' --end '2026-10-28T09:00:00-07:00' --timezone America/Los_Angeles`，不额外传 `--hours`。
- 多账号追加 `--account '账号目录名'`；已消歧群追加 `--group-id '稳定ID@chatroom'`。
- 去掉 `--launch` 只生成并检查启动脚本，不退出微信、不捕获、不要求密码。用来验证入口即可，不把它称为读取成功。
- 项目移动后提供 `--project '/新的项目路径'`，或设置环境变量 `WECHAT_REPORT_PROJECT`；不是跨平台独立软件包。

入口返回 `.runtime/skill-capture-*/capture.command` 和独立 `status.log`。通过 Terminal 执行以保证管理员密码在用户本机的交互提示输入。无须取得密码。不要用模型工具填写密码、不要读取 Terminal 全部滚屏或 shell history 来寻找密码。

用户配合只有两步：
1. 在 `Password:` 后输入本机 Mac 管理员登录密码并回车；没有星号或字符回显是正常现象。
2. 日志显示“调试断点已就绪”后，在微信副本登录原账号。若自动登录提前完成，说明原因后重新按流程登录。

读取 `status.log` 中明确的错误或 `export_directory`。程序结束不代表成功。导出后不用继续持有密钥；从输出目录完成总结。

常见阻碍：

| 现象 | 下一步 |
|---|---|
| `zsh: command not found` | 使用已生成并正确引用路径的 `.command`；不要把提示文字或密码当命令。 |
| 微信尚未退出/多个进程 | 请求用户完成正常退出；不强制杀进程。 |
| 25 秒断点未就绪 | 核查已签副本路径、系统开发者工具授权及具体错误；未就绪前不要提示登录。 |
| 300 秒捕获超时 | 本次停止，检查是否在就绪后登录、是否选中正确账号。不要无限重试。 |
| Hardened Runtime/新版本认证失败 | 停止导出并记录版本；检查研究文档，不猜参数或偏移，不自动重签或关闭 SIP。 |
| 同名群 | 根据错误候选、稳定群 ID 和必要元信息请用户选择；不自动取第一个。 |
| 多账号 | 先在普通用户环境检测账号，再传精确 --account；不要 sudo 后按 root HOME 猜账号。 |
| 浏览器启动沙箱失败 | 申请本机 Chromium 执行权限或在普通 Terminal 渲染，仍保持完全离线。 |
| 本地同步不足 | 说明最早/最近本地记录与窗口，不宣称云端完整；用户若需补同步再让其操作微信。 |
