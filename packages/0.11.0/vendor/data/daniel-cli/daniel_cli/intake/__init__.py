# -*- coding: utf-8 -*-
"""`intake` 能力包核心：需求识别 → 能力匹配 → 前置条件告知 → 工序契约草稿。

用户口径（2026-10-14 裁决，写进代码与文档的纪律）
------------------------------------------------
> 「不管是 mcp 还是 cli，在用户完整根据流程安装和接入的时候，一条完整的工作流能力包括
>   需求识别→能力匹配→前置条件告知就需要完整的内置了 …… cli 和 mcp 两种模式，
>   但是每一个模式都是完全独立且全量的能力链路」

由此定下两条架构纪律（本包是它的落地处）：

  ① **`intake` 属能力包核心**：真源在 `daniel_cli/intake/`，CLI 与 MCP 只是两种**承载模式**
     （`cli.py` 直接调用；MCP server 落成一次 `daniel intake … --json` 子进程调用），
     因此不存在"某能力只在一种模式里存在"的第二份实现；
  ② **每个模式都能独立跑完整链路**：`route`（匹配＋缺件）与 `draft`（工序契约草稿）在
     两种模式下都可达；两个模式**各自可用**的能力集合由 `modes.py` 在运行期真查，
     差集（例如 MCP 本期不注册写链）作为 `模式能力` 前置条件如实告知，不静默降级。

分工（各管一段，不互相抄口径）
------------------------------
| 文件 | 管什么 |
|---|---|
| `catalog.py` | 工序与前置条件表（真源 `processes.json`）＋ 声明合法性自证（防幻觉命令） |
| `modes.py` | 当前模式**真实可用**的能力集合（CLI 侧取 schema，MCP 侧取 server 的注册口径） |
| `matcher.py` | 需求识别与匹配：候选工序排序 ＋ 理由 ＋ 置信度（只做路由，不替业务下结论） |
| `preflight.py` | 前置条件实查：**能查的真的去查**（真调只读命令），查不到才写"需你提供" |
| `drafter.py` | 把匹配结果生成一份本次任务的工序契约草稿（能过 `playbook validate`） |
| `parity.py` | 模式对等断言：CLI 与 MCP 的能力集合／技能集合／语料版本键比对 |
| `selfcheck.py` | 模块自检：正控（真实历史需求）＋ 真阴性（无关需求不硬匹配）＋ 缺件场景 ＋ 草稿过 validate |

本包**全程只读**：不写任何 Daniel 数据、不触发任何采集、不做任何写操作
（`draft` 只在 `--out` 落一份草稿文件；`processes.json` 是随包分发的静态真源）。
"""
from . import (catalog, drafter, matcher, modes, parity, planner,   # noqa: F401
               preflight)

__all__ = ["catalog", "modes", "matcher", "preflight", "drafter", "parity", "planner",
           "selfcheck"]
