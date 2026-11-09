# -*- coding: utf-8 -*-
"""search 模块：红人检索（读链＝共享客户端只读通路 ＋ 既有检索仪器；写链走统一门禁链）。

`submit`（A1 起真实执行已接通）走的是既有仪器 `.kol-tools/daniel_search.py` 实测过的同一条
两步通路：`discovery.startSearchJob`（POST，建任务）→ `discovery.executeSearchJob`（POST，开跑）。
**入参键沿用仪器的口径**（`query／brandId／brandName／brandCompetitors／brandCategory／country／
minSubscribers／maxSubscribers`），不在这里自造第二份；`query` 有 501 字符硬上限（仪器二分实测），
超限本地拦下、不发包。
"""
import os

from ..exits import EXIT_OK, EXIT_USAGE
from .. import permissions
from ..runtime import CliError, new_client, read_instrument, use_instrument
from ._common import live_managed_write

BOARD = "search"

#: `discovery.startSearchJob` 的 `query` 硬上限（仪器 2026-09-30 二分实测：501 → 200，502 → 500）
MAX_QUERY_LEN = 501

#: 任务终态用词（服务端口径，出处：前端 `BrandMentions`／`Discovery` 构建产物与仪器 `_poll_job`）
DONE_STATES = ("done", "completed", "completed_with_warnings")
FAILED_STATES = ("failed", "error", "cancelled")


def cmd_history(ctx):
    """最近的检索记录。走只读通路 `discovery.getSearchHistory`（不触发任何检索）。"""
    d = new_client(verbose=ctx.verbose)
    limit = ctx.get("limit") or 10
    ctx.progress("正在读取最近的检索记录")
    rows = d.query("discovery.getSearchHistory", {"limit": int(limit)}) or []
    rows = [r for r in rows if isinstance(r, dict)]
    ctx.emit(data={"count": len(rows), "searches": rows},
             route="discovery.getSearchHistory")
    return EXIT_OK


def cmd_job_status(ctx):
    """复用既有检索仪器的只读入口（`--job-status`）。"""
    job = ctx.require("--job", "--job（检索任务编号）")
    ctx.progress("正在查询检索任务状态")
    return use_instrument(ctx, "daniel_search.py", ["--job-status", job],
                          route="discovery.getSearchJob")


#: 富化两条链路的批量上限**不一样**（与仪器 `daniel_search.py` 的常量同源，不得互相类推）
ENRICH_HINT = (
    "两种给法任选一种：\n"
    "  ① `--channel-ids UCxxxxxxxxxxxxxxxxxxxxxx,UCyyyyyyyyyyyyyyyyyyyyyy`"
    "（英文逗号分隔；就是频道编号）\n"
    "  ② `--items-file ./kol-items.json`（检索结果导出的 JSON 数组，或 `[\"UC…\", …]` 字符串数组）\n"
    "  要连商务邮箱一起补，再加 `--emails`（邮箱链路每批 ≤50，比频道链路更慢）"
)


def cmd_enrich(ctx):
    """**只读**补齐频道公开数据（订阅数／国家／标签，可选商务邮箱）。

    为什么不是写命令：这两条路由（`discovery.enrichChannels`／`discovery.enrichEmails`）在平台上
    登记为 mutation 动词，但只取数据、不改任何对象 —— 命令声明 `write=False`，**不发确认、不落写审计、
    不写任何文件**；取数由仪器 `daniel_search.py` 走只读通道（`--enrich-ids`／`--enrich-file`）完成，
    批量上限与合并口径留在仪器里（单一真源）。
    """
    ids = (ctx.get("channel_ids") or "").strip()
    path = str(ctx.get("items_file") or "").strip()
    if not ids and not path:
        raise CliError("缺少输入：这次要富化哪些频道？", code=EXIT_USAGE, hint=ENRICH_HINT)
    if ids and path:
        raise CliError("`--channel-ids` 与 `--items-file` 只能给一个（两个都给了，无法判断以哪个为准）",
                       code=EXIT_USAGE, hint=ENRICH_HINT)
    if path and not os.path.isfile(os.path.expanduser(path)):
        raise CliError("条目文件不存在：%s" % path, code=EXIT_USAGE,
                       hint="确认路径后重试；也可以直接用 `--channel-ids UC…,UC…` 给编号。"
                            "本次没有发出任何请求")
    argv = ["--json"]
    if ids:
        argv += ["--enrich-ids", ids]
    else:
        argv += ["--enrich-file", os.path.expanduser(path)]
    if ctx.get("emails"):
        argv.append("--emails")
    route = "discovery.enrichChannels" + (" + discovery.enrichEmails" if ctx.get("emails") else "")
    ctx.progress("正在按频道编号补齐公开数据（只读：不改任何数据、不写任何文件）")
    return read_instrument(ctx, "daniel_search.py", argv, route=route)


HANDLERS = {
    "history": cmd_history,
    "job-status": cmd_job_status,
    "enrich": cmd_enrich,
}

def _plan_submit(ctx, client):
    """只读解析目标品牌，把"将发生什么＋影响范围"讲清楚（不发任何检索）。"""
    b = client.resolve_brand_ref(ctx.require("--brand"))
    query = str(ctx.require("--query"))
    if len(query) > MAX_QUERY_LEN:
        raise CliError("检索式 %d 个字符，超过服务端硬上限 %d（仪器二分实测：501 通过、502 被拒）"
                       % (len(query), MAX_QUERY_LEN), code=EXIT_USAGE,
                       hint="缩短检索式后重试；本次没有发起任何检索")
    quota = (permissions.current_auth()[0] or {}).get("workspace") or {}
    return {
        "targetName": b.get("name"), "brand": "%s(编号 %s)" % (b.get("name"), b.get("id")),
        "workspaceId": b.get("workspaceId"),
        "impact": "会在品牌「%s」下发起一条新检索（检索式：%s）%s；检索任务会消耗工作区每月检索额度"
                  "（上限 %s），并把结果写进检索记录。本次请求数：**2 次发包**"
                  "（建任务 ＋ 开跑），另加 1 次只读回读"
                  % (b.get("name"), query,
                     ("，期望返回 %s 个候选" % ctx.get("limit")) if ctx.get("limit") else "",
                     quota.get("maxSearchesPerMonth")),
        "changes": {"discovery.startSearchJob": {"brandId": b.get("id"), "query": query},
                    "discovery.executeSearchJob": {"jobId": "<建任务返回的编号>"}},
        "writesDatabase": True,
    }


def _submit_payload(b, query):
    """`discovery.startSearchJob` 入参：**逐键沿用既有仪器 `cmd_deep` 的口径**，不新增未实测键。"""
    competitors = [c.get("name") for c in (b.get("competitors") or []) if c.get("name")]
    payload = {
        "query": query,
        "brandId": b["id"],
        "brandName": b.get("name"),
        "brandCompetitors": competitors,
        "brandCategory": b.get("category"),
        "country": _country_of(b),
    }
    return {k: v for k, v in payload.items() if v is not None and v != []}


def _country_of(brand):
    """市场：取品牌档案里的第一个运营市场（没有就不传这个键）。"""
    markets = brand.get("operatingMarkets") or brand.get("markets") or []
    if isinstance(markets, str):
        markets = [markets]
    return markets[0] if markets else None


def _run_submit(ctx, client, plan):
    """真跑：建任务 → 开跑 → **一次只读回读**核对任务已存在。

    请求数固定 3 次（`startSearchJob` ＋ `executeSearchJob` ＋ `getSearchJob`），**不轮询到完成**：
    检索任务要跑多久由服务端定，命令只负责"把任务真的建起来并回读确认"；跑没跑完由
    `daniel search job-status --job <编号>` 单独回读（那也是验收件里的回读项）。
    """
    b = client.resolve_brand_ref(ctx.require("--brand"))
    query = str(ctx.require("--query"))
    payload = _submit_payload(b, query)
    started = client.mutate("discovery.startSearchJob", payload) or {}
    job_id = started.get("jobId") or started.get("id")
    if not job_id:
        raise CliError("服务端没返回任务编号（startSearchJob 返回：%s）"
                       % str(started)[:200], code=EXIT_USAGE,
                       hint="任务可能没有建起来；用 `daniel search history` 核对检索记录")
    ctx.progress("已建任务 %s，正在开跑（executeSearchJob）" % job_id)
    exec_note = ""
    try:
        client.mutate("discovery.executeSearchJob", {"jobId": job_id})
    except Exception as e:                                             # noqa: BLE001
        # 仪器实测过：这一请求可能"提前结束"（服务端先落任务再异步跑），此时按轮询口径处理
        exec_note = "执行请求提前结束（按服务端口径改为轮询）：%s" % str(e)[:160]
        ctx.warn(exec_note)
    back = client.query("discovery.getSearchJob", {"jobId": job_id})
    back = back if isinstance(back, dict) else {}
    status = str(back.get("status") or "未知")
    terminal = _terminal_of(status)
    verified = bool(back) and str(back.get("jobId") or job_id) == str(job_id)
    reason = "" if verified else "回读没拿到这个任务（getSearchJob 返回空）"
    return {
        "mutation": {"route": "discovery.startSearchJob + discovery.executeSearchJob",
                     "request": payload},
        "readback": {"verified": verified, "reason": reason,
                     "detail": {"任务编号": job_id,
                                "回读到状态": status,
                                "终态判定": terminal,
                                "建任务返回": {k: v for k, v in started.items()
                                              if k not in ("query", "keywords")}},
                     "how": "建任务后立刻用 discovery.getSearchJob 回读该编号：对象存在且编号一致"},
        "rolledBack": None,
        "rollbackNote": "采集／检索任务**不可撤**（本 CLI 不提供删除检索任务的命令，"
                        "也禁止对生产品牌做删除类写）⇒ 只登记任务编号，不假装可逆",
        "terminal": terminal,
        "detail": {"任务编号": job_id, "回读到状态": status, "执行请求": exec_note or "正常返回"},
    }


def _terminal_of(status):
    s = str(status or "").lower()
    if s in DONE_STATES:
        return "成功"
    if s in FAILED_STATES:
        return "失败"
    return "进行中（非终态，**不算成功**）"


WRITE_HANDLERS = {
    "submit": live_managed_write(BOARD, "submit", "提交一条新的红人检索任务（会触发检索）",
                                 plan_fn=_plan_submit, run_fn=_run_submit,
                                 danger="会真的发起检索任务并消耗每月检索额度"),
}
