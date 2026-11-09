# -*- coding: utf-8 -*-
"""intel 模块：内容情报（读链复用既有仪器 `daniel_intel.py` 的只读子命令）。

读链口径（TICKET-150）：仪器 `--json` 出**读结果信封**（`daniel.read.v1`），本模块用
`read_instrument` 直接消费 —— `data` 是服务端原样返回的业务载荷（键与仪器口径逐字一致），
`read` 带条数、分页游标与"是否被收窄"的标注。
旧版仪器把 JSON 截到 12000 字符，CLI 只能抢救出第 1 条完整动作 —— 现在取的是全量。

分页口径（不含任何业务判据，只搬事实）：
  · 不给 `--limit`：`actions` 一次取全量（实测 40 条），`read.truncated=false`；
  · 给了 `--limit N`：取前 N 条，`read.truncated=true` ＋ `read.paging.nextCursor`；
  · 想接着取：仪器侧用 `--offset`（本工序已接好透传，CLI 的 `--offset` 待 schema 注册，
    见回报「留给总监的注册项」）；在那之前可用 `--status` 按状态分批取。
"""
from ..runtime import new_client, read_instrument
from ._common import append_flag, append_repeat

BOARD = "intel"
SCRIPT = "daniel_intel.py"


def _argv(ctx, subcommand):
    d = new_client(verbose=ctx.verbose)
    bid = d.resolve_brand_ref(ctx.require("--brand"))["id"]
    argv = [subcommand, "--brand", str(bid), "--json"]
    append_flag(argv, "--max-chars", ctx.get("max_chars"))       # 字符预算：不设即为不限
    return argv


def _read(ctx, subcommand, route, *, with_limit=False, with_offset=False):
    argv = _argv(ctx, subcommand)
    if with_limit:
        append_flag(argv, "--limit", ctx.get("limit"))
    if with_offset:
        append_flag(argv, "--offset", ctx.get("offset"))
    return read_instrument(ctx, SCRIPT, argv, route=route)


def cmd_actions(ctx):
    argv = _argv(ctx, "actions")
    append_repeat(argv, "--status", ctx.get("status"))
    append_flag(argv, "--limit", ctx.get("limit"))
    append_flag(argv, "--offset", ctx.get("offset"))
    ctx.progress("正在读取待办动作")
    return read_instrument(ctx, SCRIPT, argv, route="actionCenter.actions.list")


def cmd_keywords(ctx):
    ctx.progress("正在读取追踪中的关键词")
    return _read(ctx, "keywords", "actionCenter.keywords.listKeywords")


def cmd_topics(ctx):
    ctx.progress("正在读取选题清单")
    return _read(ctx, "topics", "actionCenter.topics.list")


def cmd_reviews(ctx):
    ctx.progress("正在读取内容审核单")
    return _read(ctx, "reviews", "actionCenter.reviews.list")


HANDLERS = {
    "actions": cmd_actions,
    "keywords": cmd_keywords,
    "topics": cmd_topics,
    "reviews": cmd_reviews,
}

WRITE_HANDLERS = {}
