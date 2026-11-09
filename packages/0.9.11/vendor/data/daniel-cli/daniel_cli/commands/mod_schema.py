# -*- coding: utf-8 -*-
"""schema 模块：自描述（清单、派生工具定义、一致性自证）。

⚠️ 本模块**不定义**任何子命令内容 —— 内容全在 `../schema.py`；这里只负责把它打印出来
或对它做自证。`show` 的输出就是"单一真源"本体，消费方（别的模型／MCP 壳／DSH）只读这一份。
"""
from .. import exports, schema
from ..exits import EXIT_INTERNAL, EXIT_OK


def cmd_show(ctx):
    ctx.emit(data=schema.SCHEMA)
    return EXIT_OK


def cmd_mcp(ctx):
    ctx.emit(data=exports.mcp_payload())
    return EXIT_OK


def cmd_dsh_tools(ctx):
    ctx.emit(data=exports.dsh_payload())
    return EXIT_OK


def cmd_check(ctx):
    from ..checks import schema_consistency      # 延迟导入：checks 要读命令注册表，避免循环导入
    report = schema_consistency()
    if report["ok"]:
        ctx.emit(data=report)
        return EXIT_OK
    ctx.warn("一致性自证未通过：%s" % report["summary"])
    ctx.emit_raw(ok=False, exit_code=EXIT_INTERNAL, data=report)
    return EXIT_INTERNAL


HANDLERS = {
    "show": cmd_show,
    "mcp": cmd_mcp,
    "dsh-tools": cmd_dsh_tools,
    "check": cmd_check,
}

WRITE_HANDLERS = {}
