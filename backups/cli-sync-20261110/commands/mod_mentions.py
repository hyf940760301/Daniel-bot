# -*- coding: utf-8 -*-
"""mentions 模块：品牌提及（读链全部复用既有仪器 `daniel_mentions.py` 的只读开关）。

品牌引用先经共享客户端跨工作区解析成编号再传给仪器：仪器按"名字"解析时会撞上
"多工作区同名"（实测 Halliday 在 6 个工作区命中），传编号才没有歧义。

读链口径（TICKET-150）：仪器 `--json` 出**读结果信封**（`daniel.read.v1`），本模块用
`read_instrument` 直接消费 —— `data` 是服务端原样返回的业务载荷，`read` 带条数、分页游标与
"是否被收窄"的标注。**不再从中文表格里抢救 JSON**，也不再出现"截断即丢数据"。
"""
from ..exits import EXIT_OK, EXIT_USAGE
from ..runtime import CliError, new_client, read_instrument
from ._common import append_flag, live_managed_write

BOARD = "mentions"
SCRIPT = "daniel_mentions.py"

#: 本地预检用的任务清单上限（与前端 `brandMentions.listJobs` 调用点一致：brandId ＋ limit）
JOB_LOOKUP_LIMIT = 10

#: `brandMentions.runAnalysis` 的入参边界（与仪器 `daniel_mentions.py` 同源：本地先拦，不发包）
DAYS_MIN, DAYS_MAX = 7, 1095
MAXVID_MIN, MAXVID_MAX = 100, 5000

#: 任务终态用词（服务端口径；出处：前端 `BrandMentions` 构建产物 `["done","completed_with_warnings"]`）
DONE_STATES = ("done", "completed_with_warnings")
FAILED_STATES = ("failed", "error", "cancelled")


def _brand_id(ctx):
    d = new_client(verbose=ctx.verbose)
    return d.resolve_brand_ref(ctx.require("--brand"))["id"]


def _job_precheck(ctx, brand_id, job):
    """本地预检：**能不能断定**"这个品牌没有这个任务编号"？（TICKET-150 · 总监裁决）

    为什么需要：服务端对**未知任务编号**返回的是 **500**（实测，不是 404/400），而 500 按全局口径
    属"内部错误"（1）。500 本身区分不出"编号不存在"与"服务端真故障"，所以**能在本地判定的**才拦：
      · 清单里没有该编号 **且** 清单没触上限 ⇒ 可断定不存在 → 退出码 2 ＋ 列出该品牌现有任务编号；
      · 清单**触上限** ⇒ 不能断定（可能存在更早的任务）⇒ 不拦，但把"请先核对编号"写进提示，
        让后续真故障的报错里也带上这句人话（"我是怎么判的"要说清）。
    预检自身出错（网络等）**不拦人**：走原路径，真故障照旧报 1。
    """
    try:
        d = new_client(verbose=ctx.verbose)
        rows = d.query("brandMentions.listJobs",
                       {"brandId": int(brand_id), "limit": JOB_LOOKUP_LIMIT}) or []
        rows = [r for r in rows if isinstance(r, dict)]
    except Exception:                                             # noqa: BLE001（预检失败不拦人）
        return None
    if str(job) in [str(r.get("jobId")) for r in rows]:
        return None
    if len(rows) >= JOB_LOOKUP_LIMIT:
        ctx.note("该品牌任务较多（清单已触上限 %d 条），无法断定编号是否存在："
                 "请先跑 `daniel mentions jobs --brand <品牌>` 核对任务编号"
                 % JOB_LOOKUP_LIMIT)
        return None
    existing = "、".join("%s（%s，%s）" % (r.get("jobId"), str(r.get("createdAt"))[:19], r.get("status"))
                        for r in rows[:5]) or "该品牌名下暂时没有任务"
    raise CliError("这个品牌下没有任务编号 %s（本地核对过该品牌的任务清单，只有 %d 条，未触上限）。"
                   "该品牌现有任务：%s" % (job, len(rows), existing),
                   code=EXIT_USAGE,
                   hint="用 `daniel mentions jobs --brand <品牌>` 看完整清单（含创建时间与状态）"
                        "后再重试；本次没有发起任何分析。")


def cmd_jobs(ctx):
    argv = ["--jobs", "--brand", str(_brand_id(ctx)), "--json"]
    append_flag(argv, "--limit", ctx.get("limit"))
    ctx.progress("正在读取品牌的提及分析任务列表")
    return read_instrument(ctx, SCRIPT, argv, route="brandMentions.listJobs")


def cmd_status(ctx):
    job = ctx.require("--job", "--job（任务编号）")
    _job_precheck(ctx, _brand_id(ctx), job)
    argv = ["--status", job, "--brand", str(_brand_id(ctx)), "--json"]
    ctx.progress("正在读取提及任务的进度与汇总")
    return read_instrument(ctx, SCRIPT, argv, route="brandMentions.getStatus")


def cmd_results(ctx):
    job = ctx.require("--job", "--job（任务编号）")
    brand = _brand_id(ctx)
    _job_precheck(ctx, brand, job)
    argv = ["--results", job, "--brand", str(brand), "--json"]
    append_flag(argv, "--page", ctx.get("page"))
    append_flag(argv, "--page-size", ctx.get("page_size"))
    # 相关度口径：默认只给与本品相关的提及（仪器默认 confirmed_likely）。
    # 要看全部（含不相关的）必须显式指定，取值域与仪器 `RELEVANCE_FILTER` 同源。
    append_flag(argv, "--relevance", ctx.get("relevance_filter"))
    ctx.progress("正在读取提及任务的结果分页")
    return read_instrument(ctx, SCRIPT, argv, route="brandMentions.getResults")


HANDLERS = {
    "jobs": cmd_jobs,
    "status": cmd_status,
    "results": cmd_results,
}

def _plan_run(ctx, client):
    """只读解析目标品牌与参数（不发任何采集）。"""
    b = client.resolve_brand_ref(ctx.require("--brand"))
    days = _bound(ctx, "days", "--days", "回溯天数", DAYS_MIN, DAYS_MAX, default=7)
    cap = _bound(ctx, "max_videos", "--max-videos", "最多分析视频条数",
                 MAXVID_MIN, MAXVID_MAX, default=100)
    return {
        "targetName": b.get("name"), "brand": "%s(编号 %s)" % (b.get("name"), b.get("id")),
        "workspaceId": b.get("workspaceId"),
        "impact": "会在品牌「%s」下发起一次品牌提及分析：回溯 %s 天、最多分析 %s 条视频；"
                  "任务会真实抓取并入库（产生采集用量）。本次请求数：**1 次发包**"
                  "（runAnalysis），另加 1 次只读回读" % (b.get("name"), days, cap),
        "changes": {"brandMentions.runAnalysis": {"brandId": b.get("id"), "searchMode": "brand",
                                                 "timeRangeDays": days, "maxVideos": cap}},
        "writesDatabase": True,
    }


def _bound(ctx, key, opt, label, lo, hi, default):
    """入参边界：**本地先拦**（与仪器同一条判据），越界不发包。"""
    raw = ctx.get(key)
    value = default if raw in (None, "") else raw
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise CliError("%s 必须是整数：%r" % (opt, value), code=EXIT_USAGE)
    if not (lo <= n <= hi):
        raise CliError("%s最少 %d、最多 %d，你给的是 %d" % (label, lo, hi, n), code=EXIT_USAGE,
                       hint="本次没有发起任何分析（本地边界拦截，服务端没收到请求）")
    return n


def _run_run(ctx, client, plan):
    """真跑：发起分析 → **一次只读回读**核对任务已建起来。

    请求数固定 2 次（`brandMentions.runAnalysis` ＋ `brandMentions.getStatus`）：与检索链路同理，
    命令只负责"把任务真的发起来并回读确认"；跑没跑完由 `daniel mentions status --brand … --job …`
    单独回读（那也是验收件里的回读项）。
    """
    b = client.resolve_brand_ref(ctx.require("--brand"))
    days = _bound(ctx, "days", "--days", "回溯天数", DAYS_MIN, DAYS_MAX, default=7)
    cap = _bound(ctx, "max_videos", "--max-videos", "最多分析视频条数",
                 MAXVID_MIN, MAXVID_MAX, default=100)
    payload = {"brandId": int(b["id"]), "searchMode": "brand",
               "timeRangeDays": days, "maxVideos": cap}
    started = client.mutate("brandMentions.runAnalysis", payload) or {}
    job_id = started.get("jobId") or started.get("id")
    if not job_id:
        raise CliError("服务端没返回任务编号（runAnalysis 返回：%s）" % str(started)[:200],
                       code=EXIT_USAGE,
                       hint="用 `daniel mentions jobs --brand <品牌>` 核对任务清单")
    back = client.query("brandMentions.getStatus", {"jobId": job_id, "brandId": int(b["id"])})
    back = back if isinstance(back, dict) else {}
    status = str(back.get("status") or "未知")
    terminal = _terminal_of(status)
    verified = bool(back) and str(back.get("jobId") or job_id) == str(job_id)
    reason = "" if verified else "回读没拿到这个任务（getStatus 返回空）"
    return {
        "mutation": {"route": "brandMentions.runAnalysis", "request": payload},
        "readback": {"verified": verified, "reason": reason,
                     "detail": {"任务编号": job_id, "回读到状态": status, "终态判定": terminal,
                                "进度": back.get("progressPercent"),
                                "完成说明": back.get("progressStep")},
                     "how": "发起后用 brandMentions.getStatus 回读该编号：对象存在且编号一致"},
        "rolledBack": None,
        "rollbackNote": "采集任务**不可撤**：接口虽有 `brandMentions.deleteJob`，但那是**对生产品牌"
                        "的删除类写**，本票红线禁止 ⇒ 只登记任务编号，不假装可逆",
        "terminal": terminal,
        "detail": {"任务编号": job_id, "回读到状态": status},
    }


def _terminal_of(status):
    s = str(status or "").lower()
    if s in DONE_STATES:
        return "成功"
    if s in FAILED_STATES:
        return "失败"
    return "进行中（非终态，**不算成功**）"


WRITE_HANDLERS = {
    "run": live_managed_write(BOARD, "run", "发起一次品牌提及分析（会触发采集）",
                              plan_fn=_plan_run, run_fn=_run_run,
                              danger="会真的触发采集并入库（产生采集用量）"),
}
