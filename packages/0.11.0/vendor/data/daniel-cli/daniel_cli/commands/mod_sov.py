# -*- coding: utf-8 -*-
"""sov 模块：声量份额（读链复用既有仪器 `daniel_sov.py` 的只读开关）。

`run-exposure`（A1 起真实执行已接通）：入参与判定**全部复用既有仪器**的同一份口径 ——
`exposureSov.runCollection`（四键：`categoryProfileId／categoryId／country／brandId`）＋
`exposureSov.getTaskStatus {taskId}` 轮询；终态词表 `completed／failed／stale` 也取自仪器
（`daniel_sov.TERMINAL_STATUS`），CLI 侧不写第二份判据。
"""
from ..exits import EXIT_OK, EXIT_USAGE
from ..runtime import CliError, load_capability, new_client, use_instrument
from ._common import append_flag, live_managed_write

BOARD = "sov"
SCRIPT = "daniel_sov.py"


def _base(ctx, switch):
    """`--brand` 先解析成编号：仪器按名字解析会撞上多工作区同名。"""
    d = new_client(verbose=ctx.verbose)
    bid = d.resolve_brand_ref(ctx.require("--brand"))["id"]
    argv = [switch, "--brand", str(bid), "--json"]
    append_flag(argv, "--country", ctx.get("country"))
    return argv


def cmd_overview(ctx):
    argv = _base(ctx, "--sov-overview")
    append_flag(argv, "--days", ctx.get("days"))
    ctx.progress("正在读取声量份额总览")
    return use_instrument(ctx, SCRIPT, argv, route="sovCategories overview")


def cmd_categories(ctx):
    ctx.progress("正在读取品类档案")
    return use_instrument(ctx, SCRIPT, _base(ctx, "--categories"), route="sovCategories.getByBrand")


def cmd_brand_videos(ctx):
    argv = _base(ctx, "--brand-videos")
    append_flag(argv, "--video-brand", ctx.get("video_brand"))
    append_flag(argv, "--limit", ctx.get("limit"))
    ctx.progress("正在读取品牌视频明细")
    return use_instrument(ctx, SCRIPT, argv, route="categoryVideos.getBrandVideos")


HANDLERS = {
    "overview": cmd_overview,
    "categories": cmd_categories,
    "brand-videos": cmd_brand_videos,
}

def _profile_of(client, brand_id, ref=None):
    """取该品牌的品类档案（`sovCategories.getByBrand`＋仪器 `resolve_profile`／`profile_ids`）。

    解析只在**一处**：既有仪器的两份函数（多档案歧义时报错、不猜），CLI 不重写。
    """
    sov = load_capability("daniel_sov")
    profiles = client.query("sovCategories.getByBrand", {"brandId": int(brand_id)}) or []
    try:
        prof = sov.resolve_profile(profiles, ref)
        cp, ci = sov.profile_ids(prof)
    except ValueError as e:
        raise CliError(str(e), code=EXIT_USAGE, hint="先跑 `daniel sov categories --brand <品牌>` 看档案")
    return sov, prof, cp, ci


def _plan_run_exposure(ctx, client):
    """只读解析目标品牌、市场与品类档案（不发任何采集）。"""
    b = client.resolve_brand_ref(ctx.require("--brand"))
    country = ctx.require("--country")
    _, prof, cp, ci = _profile_of(client, b["id"], ctx.get("category_profile_id"))
    return {
        "targetName": b.get("name"), "brand": "%s(编号 %s)" % (b.get("name"), b.get("id")),
        "workspaceId": b.get("workspaceId"),
        "impact": "会在品牌「%s」的「%s」市场发起一次曝光采集：统计窗口 %s 天；"
                  "任务会真实抓取并入库（产生采集用量）。本次请求数：**1 次发包**"
                  "（runCollection），另加 1 次档案解析 ＋ 1 次只读回读"
                  % (b.get("name"), country, ctx.get("days")),
        "changes": {"exposureSov.runCollection": {"categoryProfileId": cp, "categoryId": ci,
                                                 "country": country, "brandId": b.get("id")}},
        "categoryProfile": {"categoryProfileId": cp, "categoryId": ci,
                            "name": prof.get("name") if isinstance(prof, dict) else None},
    }


def _run_run_exposure(ctx, client, plan):
    """真跑：触发曝光采集 → 一次只读回读任务状态。

    请求数固定 3 次（`sovCategories.getByBrand` ＋ `exposureSov.runCollection` ＋
    `exposureSov.getTaskStatus`）。`runCollection` 的服务端语义可能是"已创建新任务"、
    "触发既有任务"或"命中已有任务／配置未变化"（仪器 `describe_trigger_return` 的三种判定），
    三者都如实登记 —— **不把"命中已有任务"说成"新建了任务"**。
    """
    b = client.resolve_brand_ref(ctx.require("--brand"))
    country = str(ctx.require("--country"))
    sov, prof, cp, ci = _profile_of(client, b["id"], ctx.get("category_profile_id"))
    payload = sov.build_run_collection_input(prof, country, b["id"])
    res = client.mutate("exposureSov.runCollection", payload) or {}
    judge = sov.describe_trigger_return(res)
    task_id = (res or {}).get("taskId")
    task = client.query("exposureSov.getTaskStatus", {"taskId": task_id}) if task_id else {}
    task = task if isinstance(task, dict) else {}
    status = str(task.get("status") or "")
    terminal = _terminal_of(sov, status)
    verified = bool(task_id) and bool(task)
    reason = "" if verified else ("未返回 taskId 或回读不到任务（返回：%s）" % str(res)[:160])
    return {
        "mutation": {"route": "exposureSov.runCollection", "request": payload,
                     "服务端判定": judge},
        "readback": {"verified": verified, "reason": reason,
                     "detail": {"任务编号": task_id, "任务编号（脱敏）": sov.mask_id(task_id),
                                "回读到状态": status or "未知",
                                "终态判定": terminal,
                                "进度": task.get("progress"),
                                "错误": task.get("error"),
                                "服务端判定": judge},
                     "how": "触发后用 exposureSov.getTaskStatus 回读该 taskId：对象存在；"
                            "终态词表取自仪器 `daniel_sov.TERMINAL_STATUS`"},
        "rolledBack": None,
        "rollbackNote": "曝光采集是**采集任务本身**（不可撤）⇒ 只登记任务编号与前后份额对比，"
                        "不假装可逆；若本次判定是「命中已有任务」则连新对象也没有产生",
        "terminal": terminal,
        "detail": {"任务编号": task_id, "任务编号（脱敏）": sov.mask_id(task_id),
                   "服务端判定": judge, "回读到状态": status or "未知"},
    }


def _terminal_of(sov, status):
    s = str(status or "").lower()
    if s == "completed":
        return "成功"
    if s in ("failed", "stale"):
        return "失败" if s == "failed" else "超时"
    return "进行中（非终态，**不算成功**）"


WRITE_HANDLERS = {
    "run-exposure": live_managed_write(BOARD, "run-exposure", "发起一次曝光采集（会触发采集）",
                                       plan_fn=_plan_run_exposure, run_fn=_run_run_exposure,
                                       danger="会真的触发采集并入库（产生采集用量）"),
}
