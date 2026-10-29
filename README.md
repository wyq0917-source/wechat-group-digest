# 微信群记录总结 · WeChat Group Digest

一个可复用的 **Codex Skill + 本地读取与渲染程序**：读取本人 Mac 上指定微信群的本地已同步记录，由当前 Codex 会话读完并总结，输出带消息来源的离线网页、PNG 长图、Markdown 和结构化数据。

**不需要额外模型 API Key。** `export` 只导出消息，`render` 只渲染已写好的总结；语义总结由 Codex 会话完成，不是一个脱离 Codex 的无人值守 AI 服务。

## 能做什么

- 完整群名匹配；同名群用稳定群 ID 消歧，多账号不混读。
- 最近 24 / 48 / 72 小时，或带时区的明确起止时间；窗口固定为 `[start,end)`。
- 读取实际分片、认证加密页、校验有效且已提交的 WAL，消息排序和去重。
- 文本、发言人、时间、引用、常见文章/链接/文件卡片及视频号描述。媒体未解析时只标类型，已有语音转写注明来源。
- 概览、主要话题、待办、已确认事项和未解决问题，每个重要结论关联实际消息 ID。
- 无远程字体/脚本/CDN 的离线 HTML；原始来源默认折叠；PNG 按安全高度自动编号分图。

## 兼容范围

已在 **macOS 15.7、Apple Silicon、微信 4.1.15 (270115)** 的一个本人账号上完成真实本地读取。验证了 179 条消息、32 位发言人的完整报告；真实聊天内容、账号标识、报告与截图均未公开。

这不保证其他微信版本、Intel Mac、Windows 或 Linux 可用。捕获器目前只支持已验证的 arm64 ABI；字段或认证不匹配时停止，不猜内存偏移。本地已同步记录不等于云端完整历史。

## 安装依赖

需要 macOS、Python 3.12+、Node.js/npm、Xcode Command Line Tools（提供 LLDB）、Zstandard 动态库。可通过你信任的软件包管理器安装，例如已有 Homebrew 时：

```bash
brew install python@3.12 node zstd
xcode-select --install   # 若尚未安装 Command Line Tools
```

克隆并安装：

```bash
git clone https://github.com/wyq0917-source/wechat-group-digest.git
cd wechat-group-digest
sh scripts/setup.sh
./wxreport demo
.venv/bin/python -m unittest discover -s tests -v
```

`setup.sh` 创建 `.venv`、安装固定的 Python/Playwright 版本并下载 Chromium，再生成本机 `runtime.local.json`。此配置不提交。`demo` 只使用虚构数据，不会连接微信。

## 安装 Skill

在仓库根目录执行以下命令，将技能链接到个人 Codex 技能目录。目标同名技能已经存在时，先检查其内容，不要覆盖自己的定制版本。

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$PWD/skills/wechat-group-digest" "${CODEX_HOME:-$HOME/.codex}/skills/wechat-group-digest"
```

然后在 Codex 中说：

> 使用 $wechat-group-digest，总结“我的学习群”最近 24 小时的聊天，生成网页版和 PNG 长图。

也可指定 48/72 小时、明确起止时间，或让它总结某个已有导出目录。符号链接会定位仓库；复制安装时需告诉 Codex 仓库位置，或传 `--project` / 设置 `WECHAT_REPORT_PROJECT`。不要删除运行时仓库。

## 首次准备微信副本

仅操作本人账号。官方微信的 macOS 进程保护可能阻止调试器附加。已验证方法需要一个**独立的本机 ad-hoc 签名副本**和重新登录；副本签名会改变，系统可能提示开发者工具授权。先理解并授权这一步，再由本人在本机执行。Skill 不会自动改签名、修改原版应用或关闭 SIP。

正常退出微信后，在仓库根目录运行：

```bash
mkdir -p .runtime
if [ ! -e .runtime/WeChat-reader.app ]; then
  ditto /Applications/WeChat.app .runtime/WeChat-reader.app &&
  codesign --force --deep --sign - .runtime/WeChat-reader.app
else
  echo "副本已存在，请检查版本和签名；不覆盖。"
fi
./wxreport doctor --app "$PWD/.runtime/WeChat-reader.app"
```

准备前应确认副本路径不存在；如已有副本，跳过复制并检查其版本/签名。系统若拒绝操作，停止并查看错误，不关闭保护功能。副本不随仓库分发。微信更新后需要重新检查兼容性，旧副本不可视为长期兼容承诺。

## 读取与生成报告

建议直接调用 Skill。手动入口也支持所有参数：

```bash
.venv/bin/python skills/wechat-group-digest/scripts/start_capture.py \
  --group '我的学习群' --hours 24 --timezone Asia/Shanghai --launch
```

该入口正常退出微信、启动已有副本并打开 Terminal。只有以下步骤需要本人操作：

1. 在 `Password:` 后输入 Mac 管理员密码并回车，输入不回显。不要将密码或密钥发送到 Codex。
2. 等显示“调试断点已就绪”之后，再登录原账号。

读取完成后返回 Codex，让它读完 `export_directory` 下全部消息批次，编写 `report.json`，随后渲染。状态日志在本次 `.runtime/skill-capture-*` 目录，不记录输入的密码。

```bash
./wxreport batch outputs/本次目录 1
# 由当前 Codex 会话完整读完全部批次，按 SUMMARIZE.md 写 report.json
./wxreport render outputs/本次目录
./wxreport verify outputs/本次目录
open outputs/本次目录/index.html
```

自定义时间把 `--hours` 换成：

```text
--start '2026-10-27T09:00:00+08:00' --end '2026-10-28T09:00:00+08:00' --timezone Asia/Shanghai
```

多账号用 `--account '账号目录名'`；同名群消歧后用 `--group-id '稳定ID@chatroom'`。建议显式传入 IANA 时区；公开版未指定时区时使用 UTC。

## 输出与验证

每次独立目录至少包含：

| 文件 | 用途 |
|---|---|
| `messages.json` / `messages.txt` | 结构化消息、统计元数据和可读正文 |
| `report.json` | 含消息 ID 引用的结构化总结 |
| `summary.md` | 中文总结及来源摘录 |
| `index.html` | 可直接打开的离线报告 |
| `report.png` | PNG 长图；过长时另有 `report-02.png` 等 |
| `render-manifest.json` | 图像尺寸、分图范围及渲染检查 |

`verify` 能检查引用存在性、阅读批次登记和统计一致性；是否真的读完、结论是否被证据支持，仍由总结会话负责。虚构测试成功不等于真实微信读取成功。验证记录见 [docs/VALIDATION.md](docs/VALIDATION.md)。

## 隐私与已知限制

- 原库只读；DB/WAL 整组两次稳定捕获，解密 SQLite 仅在 RAM，无临时明文数据库。不是跨库事务快照，不能保证云端同步完整。
- 密钥不写文件/日志/配置，禁用 core dump；尽可能清理敏感缓冲区。Python 内部不可变副本及系统 swap 无法承诺物理零残留。
- 输出本身包含聊天内容，是需要自行保管的明文资料。默认 gitignore，目录 0700、数据文件 0600；不自动上传、发送或部署报告。
- 不 OCR、不听写未转写语音、不分析视频画面；昵称可能与群内备注不同。
- 每次新读取需要重新捕获；不能直接复用上次密钥。仅对已有导出重新总结不需要微信登录。
- 对话中的价格、观点和产品能力陈述按成员自述记录，不自动当作已核实事实；收到/感谢不等于同意或完成。
- `zsh: command not found`：路径含空格时需完整引号，密码仅在 Password 提示后输入。
- 调试器 25 秒未就绪或捕获 300 秒超时：检查副本、开发者工具授权和登录时机，先停止再针对原因处理。
- 快照、页认证或字段校验失败：停止读取；不要用空报告伪装成功。
- Chromium 在受限沙箱无法启动：允许本机浏览器进程运行，或从普通 Terminal 渲染；无需网络。

## 来源与许可

MIT License。研究来源固定到 GreenBubbles 提交 `69f19c7089d7ef011e9ba43d44c6fb4e6e5be98b`，保留第三方许可说明；参见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 [研究说明](docs/RESEARCH.md)。
