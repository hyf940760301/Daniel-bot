# -*- coding: utf-8 -*-
"""Daniel Copilot 统一命令行（TICKET-145 · P0-2）。

本包是 Daniel 能力的**唯一入口层**：
  - 不依赖 DSH（不 import 任何 DSH 模块，不要求 PATH 里有 dsh）；
  - 业务逻辑**不在本包内**，一律复用 `.kol-tools/` 下既有仪器与 `daniel_client`；
  - `daniel_cli/schema.py` 是**全部子命令与参数的单一真源**，`--help`／MCP 工具清单／
    DSH defineTool 草稿三样都从它派生（见 `helpgen.py`、`exports.py`）。
"""

__version__ = "0.1.0"
CLI_NAME = "daniel"
