# -*- coding: utf-8 -*-
"""auth 模块：**授权是起点**（TICKET-194）。

用户 2026-10-16 逐字裁定：
> 「daniel cli 和 mcp 的起点一定是授权和登陆 …… 否则是无法跳过授权进入到实际对 daniel
>   的模块调用中的」

本模块只做一件事：把"**登录了没有**"做成**一条可脚本判定**的命令（`daniel auth status`），
判据与门禁**同源**（`daniel_cli/authgate.py`，单一真源），因此
"`auth status` 说没登录、业务命令却跑通了"在结构上不可能发生。

三档退出码（照飞书项目 CLI 的口径；`--json` 里另有 `reason` 字段，同样三档）：

| 退出码 | 含义 | 下一步 |
|---|---|---|
| **0** | 通过：本地会话有效，且服务端确认了这个账号 | 正常调用业务模块 |
| **1** | 无 token，或 token 被服务端拒 | **去登录**（`daniel account login --browser`） |
| **2** | 服务端不可达（网络／5xx） | **稍后重试**；本地会话**没有**被判失效，**不要**重新登录 |

🔴 本命令**不回显会话值**：会话 cookie 只在一次 HTTP 请求头里出现，任何输出（含 `--json`、
含出错时的原文）里都只有掩码邮箱与判定事实。
"""
from .. import authgate
from ..exits import EXIT_OK, EXIT_USAGE
from ..runtime import CliError

BOARD = "auth"


def _human(data):
    """给人看的一段话（结论优先，再给落点与下一步）。"""
    who = ((data.get("server") or {}).get("账号(掩码)") or "").strip()
    head = "登录状态：%s" % data["reason"]
    if data["state"] == authgate.VERIFY_OK:
        head += "（会话有效%s）" % ("，账号 " + who if who else "")
    lines = [head]
    loc = data.get("local") or {}
    if loc.get("本机会话文件"):
        lines.append("本机会话文件：%s" % loc["本机会话文件"])
    if loc.get("会话落盘在 DANIEL_HOME 之内") is False:
        lines.append("⚠️  会话文件**不在**当前数据落点之内 —— 跑 `daniel account paths` 核对")
    if data["state"] == authgate.VERIFY_REJECTED:
        lines.append("说明：%s" % ((data.get("server") or {}).get("服务端原文")
                                 or (data.get("server") or {}).get("理由") or "本机没有可用会话"))
    if data["state"] == authgate.VERIFY_UNREACHABLE:
        lines.append("说明：%s" % ((data.get("server") or {}).get("理由")
                                 or (data.get("server") or {}).get("服务端原文") or "服务端不可达"))
    lines.append("下一步：%s" % data["next"])
    return "\n".join(lines)


def cmd_status(ctx):
    """看登录状态：本地会话 ＋ **一次**轻量服务端校验（只读 `auth.me`）。"""
    timeout = int(ctx.get("timeout") or authgate.VERIFY_TIMEOUT)
    ctx.progress("正在校验登录状态（本地会话 ＋ 一次服务端校验）")
    try:
        data = authgate.status(timeout=timeout)
    except CliError:
        raise
    except Exception as e:                                            # noqa: BLE001
        # 校验本身崩了：**按"稍后重试"收口**（不是"去登录"），绝不把不确定说成没登录
        data = {"authenticated": False, "reason": "稍后重试", "state": authgate.VERIFY_UNREACHABLE,
                "exitCode": EXIT_USAGE, "local": {}, "server": {"理由": str(e)[:200]},
                "next": authgate.STATUS_NEXT[authgate.VERIFY_UNREACHABLE]}

    ctx.notes.append("判据与门禁同源（daniel_cli/authgate.py）；本命令不回显任何会话值")
    ctx.notes.append("退出码：0＝通过／1＝去登录／2＝服务端不可达（稍后重试）")
    if data["exitCode"] == EXIT_OK:
        ctx.emit(data=data, human=_human(data), route="auth.me")
        return EXIT_OK
    ctx.warn(_human(data))
    ctx.emit_raw(ok=False, exit_code=data["exitCode"], data=data, human=_human(data),
                 route="auth.me")
    return data["exitCode"]


HANDLERS = {"status": cmd_status}
WRITE_HANDLERS = {}
