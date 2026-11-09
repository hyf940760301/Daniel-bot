# -*- coding: utf-8 -*-
"""clarify 模块：**参数级追问**（`plan`／`ask`）——只读、离线、不取数。

为什么两条命令而不是一条 `--mode`
--------------------------------
`plan` 与 `ask` 的参数集和返回形状都不同（`plan` 出缺项清单，`ask` 出四模式之一）。
合成一条就会让"一份契约有两种返回形状"，`schema --check` 与 `--help` 都说不清。

数据来源：登记表索引（文案）＋ `daniel_cli/data/clarify_triggers.json`（触发词）。
逻辑实现见 `daniel_cli/clarify.py`。
"""
from ..clarify import ClarifyDataError, clarify_plan, norm_text, screen_plan
from ..exits import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE
from ..runtime import CliError

_DATA_HINT = ("随包数据缺失或过期：重装本包，或跑 "
              "`python3 mcp/check_corpus_sync.py --sync` 重建语料与索引")


def _need(ctx):
    need = ctx.get("--need")
    if not norm_text(need):
        raise CliError("need 不能为空：把用户原话或需求摘要传进来，才判断得出哪些参数已经说了。",
                       code=EXIT_USAGE)
    return need


def cmd_plan(ctx):
    try:
        data = clarify_plan(_need(ctx), ctx.get("--topic"))
    except ClarifyDataError as exc:
        raise CliError(str(exc), code=EXIT_INTERNAL, hint=_DATA_HINT)
    ctx.emit(data=data)
    return EXIT_OK


def cmd_ask(ctx):
    try:
        data = screen_plan(_need(ctx), ctx.get("--reply"), ctx.get("--round"))
    except ClarifyDataError as exc:
        raise CliError(str(exc), code=EXIT_INTERNAL, hint=_DATA_HINT)
    ctx.emit(data=data)
    return EXIT_OK


HANDLERS = {
    "plan": cmd_plan,
    "ask": cmd_ask,
}

WRITE_HANDLERS = {}
