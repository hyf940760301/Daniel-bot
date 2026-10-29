# -*- coding: utf-8 -*-
"""parity 模块：口径一致性（读链复用既有仪器 `daniel_ui_parity.py`，离线）。"""
from ..runtime import use_instrument
from ._common import append_flag, oracle_path

BOARD = "parity"
SCRIPT = "daniel_ui_parity.py"


def cmd_selfcheck(ctx):
    argv = ["--selfcheck", "--json", "--oracle", oracle_path()]
    ctx.progress("正在核对判定口径与页面实现是否逐字一致（离线）")
    return use_instrument(ctx, SCRIPT, argv, route="ui_parity.selfcheck")


def cmd_compare(ctx):
    argv = ["--probe", ctx.require("--probe", "--probe（页面抓取数据文件）")]
    append_flag(argv, "--report", ctx.get("report"))
    ctx.progress("正在做逐字段比对（离线）")
    return use_instrument(ctx, SCRIPT, argv, route="ui_parity.compare")


HANDLERS = {
    "selfcheck": cmd_selfcheck,
    "compare": cmd_compare,
}

WRITE_HANDLERS = {}
