# -*- coding: utf-8 -*-
"""authenticity 模块：真实性核验（读链复用既有仪器 `daniel_authenticity.py`）。"""
from ..runtime import use_instrument
from ._common import append_flag

BOARD = "authenticity"
SCRIPT = "daniel_authenticity.py"


def cmd_channel(ctx):
    argv = ["--channel", ctx.require("--channel", "--channel（频道链接/@handle/频道编号）")]
    append_flag(argv, "--videos-json", ctx.get("videos_json"))
    argv.append("--json")
    ctx.progress("正在读取频道数据并计算真实性评分")
    return use_instrument(ctx, SCRIPT, argv, route="discovery.getChannelDetail")


def cmd_weights(ctx):
    ctx.progress("正在读取评分权重口径（离线）")
    return use_instrument(ctx, SCRIPT, ["--explain-weights"])


HANDLERS = {
    "channel": cmd_channel,
    "weights": cmd_weights,
}

WRITE_HANDLERS = {}
