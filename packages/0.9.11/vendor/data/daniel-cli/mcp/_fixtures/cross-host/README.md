# `_fixtures/cross-host/` —— 跨宿主比对回归对（真件，不是造的）

这两个文件是 **2026-10-14 用户与总监在真实两个宿主里跑出来的原件**，本目录里的是一个字节都没改的副本。
它们被 `compare_hosts.py --self-test` 当**正控回归对**用：每次跑自检都会把这一对重新比一遍，
保证"Cursor 经 MCP 跑出来的产物 ≡ DSH 侧直接 CLI 跑出来的产物"这条结论不会随着改动悄悄失效。

| 文件 | 来自哪个宿主 | 怎么来的 | 大小 | sha256 |
|---|---|---|---|---|
| `cursor-mcp-run.json` | **Cursor 3.24.12**（经本目录的 MCP server） | 用户在 Cursor GUI 的新会话里让 agent 调 `daniel_playbook_run`（契约 `minimal-skeleton`，带 `out`） | 6,838 B | `06df846252d108dc290ba04bce45eee9641308a28ae634012610131e21adb9dd` |
| `dsh-cli-run.json` | **DSH 侧**（直接 CLI） | 同一条工序用 `daniel playbook run minimal-skeleton --json --out …` 跑一次 | 6,838 B | `7cf9a828ba68e5ef80b11da823d486d1d0c9047d4a13ba69a7bbff7287393716` |

两份产物都是同一份契约的运行报告（顶层 14 个字段：契约／运行／输入／限额／前置／步骤／判据／门禁／交付件／自检／失败模式／写动作台账／计数／结论）。

**唯一的取值差异**是契约引擎自建的临时沙箱目录名（两侧各是一段随机后缀，例如 `daniel-playbook-52pcdem1`
与 `daniel-playbook-rp2zby8p`），以及三处引用了这个落点的字符串。这三处由 `compare_hosts.py` 的
**规则②**（临时沙箱名 → `daniel-playbook-<SANDBOX>`）归一化掉；`--strict` 关掉归一化时会如实报出这 3 条。
换句话说：**"差异 0" 不是靠忽略字段换来的，而是把这一个必然逐次不同的落点片段归一化后得到的**，
自检里专门有一条真阴性守着这件事。

两份产物里不含任何凭据、令牌或口令，只有本机路径与工序结论。
