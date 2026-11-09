# -*- coding: utf-8 -*-
"""`daniel install`：**一条命令的安装向导**（TICKET-195）。

| 文件 | 管什么 |
|---|---|
| `source.py` | **「包从哪来」的唯一抽象点**（分发渠道的缝：现在本地，将来 npm 只换这里） |
| `wizard.py` | 四步的判据与执行：① 装 CLI ② 装能力束 ③ 写宿主接入（复用 `connect`）④ 起登录 ＋ `--check` 自检 |

设计口径见 `wizard.py` 的文件头；用户口径（逐字）见 `tickets/TICKET-195-install-wizard.md`。
"""
from . import source, wizard                                                    # noqa: F401

__all__ = ["source", "wizard"]
