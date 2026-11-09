# -*- coding: utf-8 -*-
"""mentions 模块：品牌提及（读链全部复用既有仪器 `daniel_mentions.py` 的只读开关）。

品牌引用先经共享客户端跨工作区解析成编号再传给仪器：仪器按"名字"解析时会撞上
"多工作区同名"（实测 Halliday 在 6 个工作区命中），传编号才没有歧义。

读链口径（TICKET-150）：仪器 `--json` 出**读结果信封**（`daniel.read.v1`），本模块用
`read_instrument` 直接消费 —— `data` 是服务端原样返回的业务载荷，`read` 带条数、分页游标与
"是否被收窄"的标注。**不再从中文表格里抢救 JSON**，也不再出现"截断即丢数据"。
"""
import re

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


# ── 提及四视图（只读）：图表／头部频道／视频证据／导出 ────────────────────────
# 四条路由的入参键与返回形状**全部取自前端 bundle 调用点 ＋ 实测**
# （`docs/marketing/kol/_daniel-integration/02-brand-mentions.md` §1 路由总表）：
#   · getChartData      {jobId} → 5 个分布块
#   · getTopChannels    {jobId, limit(5–50), relevanceFilter} → 频道数组（16 键）
#   · getVideoEvidence  {jobId, brandId} → 对象（10 键，含 videos[]）
#   · exportMentions    {jobId, relevanceFilter, excludeOfficial, languageFilter?} → 行数组（14 列）
# 这一层只做两件事：**本地边界拦截**（越界不发包）与**把服务端字段名翻成业务语言**；
# 取数仍由仪器 `daniel_mentions.py` 完成（参数与分页口径的单一真源）。

#: `getTopChannels.limit` 的合法区间（实测 1／3／100 都被 400 拒；见 02-brand-mentions.md §2.1）
TOP_LIMIT_MIN, TOP_LIMIT_MAX = 5, 50

# 口径候选值（`--relevance-filter` 三值、`--language` 14 个语言码）不在这里另存一份：
# 唯一真源在 `schema.py` 的 `o(..., choices=[...])`，argparse 会按那份拦非法值；
# 本模块只读 `ctx.get("relevance_filter")` / `ctx.get("language")` 并原样传给仪器。


def _num_or_text(value):
    """服务端常把数字用字符串给回来（`"542578.0000"`／`"6"`）：纯数字就还原成数字，其余原样。"""
    if isinstance(value, bool) or not isinstance(value, str):
        return value
    text = value.strip()
    if not re.match(r"^-?\d+(\.\d+)?$", text):
        return value
    number = float(text)
    return int(number) if "." not in text else number


def _shape_rows(rows, mapping):
    """按映射把服务端字段名换成业务字段名；**没登记的字段不丢**，集中放进「未登记字段」。"""
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        item = {}
        for key, label in mapping.items():
            if key in row and row[key] not in (None, ""):
                item[label] = _num_or_text(row[key])
        extra = {k: v for k, v in row.items()
                 if k not in mapping and v not in (None, "", [])}
        if extra:
            item["未登记字段"] = extra
        out.append(item)
    return out


_CHART_BLOCKS = (
    ("performanceDist", "表现分布", {"performance": "表现档位", "count": "条数"}),
    ("authDist", "真实性分布", {"label": "真实性档位", "count": "条数"}),
    ("videoTypeDist", "视频类型分布", {"videoType": "视频类型", "count": "条数"}),
    ("promotionDist", "推广建议分布", {"recommendation": "推广建议", "count": "条数"}),
    ("monthlyTrend", "月度趋势", {"month": "月份", "count": "条数",
                                  "avgViews": "平均播放", "avgComposite": "平均综合分"}),
)

_TOP_CHANNEL_FIELDS = {
    "channelId": "频道编号", "channelTitle": "频道名", "subscriberCount": "订阅数",
    "videoCount": "视频数", "avgComposite": "平均综合分", "avgViews": "平均播放",
    "totalViews": "总播放", "avgAuthenticity": "平均真实性", "channelScore": "频道得分",
    "isRostered": "是否已在名单", "relevanceLabel": "相关性",
    "highPerformanceCount": "强表现视频数", "goodPerformanceCount": "良好表现视频数",
    "averagePerformanceCount": "一般表现视频数", "lowPerformanceCount": "低表现视频数",
    "unratedPerformanceCount": "未评级视频数",
}

_EVIDENCE_FIELDS = {
    "status": "状态", "matchingCount": "匹配视频数", "eligibleCount": "符合条件数",
    "selectedCount": "入选视频数", "analyzedCount": "已分析数",
    "remainingEligibleCount": "剩余可入选数", "remainingAnalysisCount": "剩余待分析数",
    "batchStarted": "是否已开始分批", "batches": "批次数",
}

_EVIDENCE_VIDEO_FIELDS = {
    "resultId": "视频编号", "videoTitle": "视频标题", "progress": "分析进度",
}

_EXPORT_FIELDS = {
    "channelName": "频道名", "channelHandle": "频道账号", "channelUrl": "频道链接",
    "videoTitle": "视频标题", "videoUrl": "视频链接", "views": "播放量",
    "subscribers": "订阅数", "compositeScore": "综合分", "organicPerformance": "自然表现",
    "relevance": "相关性", "type": "视频类型", "isOfficial": "是否官方",
    "language": "语言", "email": "邮箱",
}


def _with_job(data, job):
    out = {"任务编号": job}
    out.update(data)
    return out


def shape_chart(payload):
    """`getChartData` → 五个分布块（块名与行字段都用业务语言）。"""
    chart = payload if isinstance(payload, dict) else {}
    data = {}
    for key, label, mapping in _CHART_BLOCKS:
        data[label] = _shape_rows(chart.get(key), mapping)
    known = {key for key, _, _ in _CHART_BLOCKS}
    extra = {k: v for k, v in chart.items() if k not in known and v not in (None, "", [])}
    if extra:
        data["其他分布"] = extra
    data["分布块数"] = len([1 for key, _, _ in _CHART_BLOCKS
                        if isinstance(chart.get(key), list)])
    return data


def shape_top_channels(rows, limit, relevance):
    rows = rows if isinstance(rows, list) else []
    items = _shape_rows(rows, _TOP_CHANNEL_FIELDS)
    return {
        "频道数": len(items),
        "本次口径": relevance,
        "本次上限": limit,
        "可能还有更多": ("是（返回条数已到上限 %d；调大 --limit 或换口径再看）" % limit
                     if len(items) >= limit else "否（返回条数没到上限）"),
        "频道": items,
    }


def shape_evidence(payload):
    evidence = payload if isinstance(payload, dict) else {}
    data = {}
    for key, label in _EVIDENCE_FIELDS.items():
        if key in evidence and evidence[key] is not None:
            data[label] = _num_or_text(evidence[key])
    videos = evidence.get("videos")
    data["视频"] = _shape_rows(videos if isinstance(videos, list) else [],
                            _EVIDENCE_VIDEO_FIELDS)
    data["视频数"] = len(data["视频"])
    known = set(_EVIDENCE_FIELDS) | {"videos"}
    extra = {k: v for k, v in evidence.items() if k not in known and v not in (None, "", [])}
    if extra:
        data["其他字段"] = extra
    return data


def shape_export(rows):
    rows = rows if isinstance(rows, list) else []
    items = _shape_rows(rows, _EXPORT_FIELDS)
    no_mail = sum(1 for row in rows
                  if isinstance(row, dict) and not str(row.get("email") or "").strip())
    return {
        "条数": len(items),
        "邮箱缺失条数": no_mail,
        "提及": items,
    }


def _top_limit(ctx):
    """`--limit` 本地边界：5–50（服务端 1／3／100 都 400）。越界**不发包**。"""
    raw = ctx.get("limit")
    default = 10
    value = default if raw in (None, "") else raw
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise CliError("--limit 必须是整数：%r" % value, code=EXIT_USAGE,
                       hint="取 5–50 之间的整数（实测 1／3／100 都会被服务端拒）；"
                            "本次没有发出任何请求")
    if not (TOP_LIMIT_MIN <= number <= TOP_LIMIT_MAX):
        raise CliError("--limit 最少 %d、最多 %d，你给的是 %d"
                       % (TOP_LIMIT_MIN, TOP_LIMIT_MAX, number), code=EXIT_USAGE,
                       hint="例如 `--limit 25`；本次没有发出任何请求（本地边界拦截）")
    return number


def cmd_chart(ctx):
    job = ctx.require("--job", "--job（任务编号）")
    _job_precheck(ctx, _brand_id(ctx), job)
    ctx.progress("正在读取提及任务的表现分布")
    return read_instrument(ctx, SCRIPT, ["--chart", str(job), "--json"],
                           route="brandMentions.getChartData",
                           shape=lambda payload: _with_job(shape_chart(payload), job))


def cmd_top_channels(ctx):
    job = ctx.require("--job", "--job（任务编号）")
    limit = _top_limit(ctx)
    relevance = ctx.get("relevance_filter") or "all"
    _job_precheck(ctx, _brand_id(ctx), job)
    argv = ["--top-channels", str(job), "--limit", str(limit), "--relevance", relevance, "--json"]
    ctx.progress("正在读取提及任务的头部频道（最多 %d 个）" % limit)
    return read_instrument(ctx, SCRIPT, argv, route="brandMentions.getTopChannels",
                           shape=lambda payload: _with_job(
                               shape_top_channels(payload, limit, relevance), job))


def cmd_evidence(ctx):
    job = ctx.require("--job", "--job（任务编号）")
    brand = _brand_id(ctx)
    _job_precheck(ctx, brand, job)
    # 入参键只有 jobId ＋ brandId（实测缺任一都 400）；**不需要视频编号** ——
    # 视频编号在返回的 videos[] 里（要拿它去触发深析，是另一条写链，不在本命令范围）。
    argv = ["--evidence", str(job), "--brand", str(brand), "--json"]
    ctx.progress("正在读取提及任务的视频证据")
    return read_instrument(ctx, SCRIPT, argv, route="brandMentions.getVideoEvidence",
                           shape=lambda payload: _with_job(shape_evidence(payload), job))


def cmd_export(ctx):
    job = ctx.require("--job", "--job（任务编号）")
    _job_precheck(ctx, _brand_id(ctx), job)
    argv = ["--export", str(job), "--json"]
    append_flag(argv, "--relevance", ctx.get("relevance_filter"))
    append_flag(argv, "--language", ctx.get("language"))
    if ctx.get("exclude_official"):
        argv.append("--exclude-official")
    ctx.progress("正在导出提及明细（可能较慢：服务端会顺带抓邮箱）")
    return read_instrument(ctx, SCRIPT, argv, route="brandMentions.exportMentions",
                           shape=lambda payload: _with_job(shape_export(payload), job))


HANDLERS = {
    "jobs": cmd_jobs,
    "status": cmd_status,
    "results": cmd_results,
    "chart": cmd_chart,
    "top-channels": cmd_top_channels,
    "evidence": cmd_evidence,
    "export": cmd_export,
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
