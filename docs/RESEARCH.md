# 已核查实现依据

研究时核查了开源仓库元信息、许可证、实际捕获/校验/数据库查询源码，未仅依据项目标题判断兼容。

采用研究依据：[GreenBubbles 固定提交](https://github.com/bojieli/greenbubbles/tree/69f19c7089d7ef011e9ba43d44c6fb4e6e5be98b)，MIT。

核查文件：`Sources/GreenBubblesAcquire/LLDBCaptureScript.swift`、`SQLCipherKeyVerifier.swift`、`Native` 下的 `wal.rs`、`live_query.rs`、`docs/WECHAT_DATABASE_FORMAT.md` 和 `docs/PASSPHRASE_ACQUISITION.md`。上游公开捕获范围为 4.1.12/4.1.13；本项目另对本机 4.1.15 (270115) 完成真实认证与读取。

- arm64 在系统 `CCKeyDerivationPBKDF` 符号断点读取长度 32 的输入；使用 ABI 寄存器 x1/x2，不硬编码微信内存偏移。
- SQLCipher profile：4096 字节页、16 字节 salt、80 字节 reserve、PBKDF2-HMAC-SHA512 256000 次、MAC 密钥派生 2 次与 salt XOR 0x3A；页号 little-endian。候选值和所有使用的加密页面需要 HMAC 通过。
- `Msg_` 加群 ID 的 MD5 定位消息表；`Name2Id.rowid` 关联发送人，实际表列先检查，时间单位按数据检测。
- 上游所查 WAL 循环未完整实施滚动 checksum；本实现按 [SQLite WAL 格式](https://www.sqlite.org/fileformat2.html#walformat) 校验 header、帧 checksum、salt 与最后提交边界，随后再认证应用的加密页。不是直接照搬上游 WAL 循环。
- 只读捕获所需账号 DB/WAL，整组字节与元数据连续两次一致才接受；捕获前后分片集合必须一致。SQLite 明文通过 deserialize 进入内存，integrity_check 成功后只查询目标群和时间范围。

其他候选：WeChatMsg 历史实现主要面向 Windows，未采用；wechat-decrypt 仓库访问受限无法核验，未采用镜像；其他需要持久密钥、版本不匹配或许可证不明确的方案未用于本实现。

[SQLCipher 官方设计](https://www.zetetic.net/sqlcipher/design/)提供加密格式背景。公开仓库不包含任何本人/他人聊天内容、密钥、微信程序或账户数据。
