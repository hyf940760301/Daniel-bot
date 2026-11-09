# -*- coding: utf-8 -*-
"""ct 模块：合作追踪（Creator Tracker）。

读链走共享客户端的单条只读通路（`ct.campaigns.list`）＋共享的品牌解析：
既有 `daniel_ct.py` 的同名读入口只打中文表格、没有 JSON 出口，直接走通路才能给出
结构化结果，同时不新增任何业务判据（品牌解析与传输都在共享客户端里）。
"""
from ..exits import EXIT_OK, EXIT_USAGE
from ..runtime import CliError, new_client
from ._common import STAGE_LIVE, gated_write, live_managed_write

BOARD = "ct"


def cmd_campaigns(ctx):
    d = new_client(verbose=ctx.verbose)
    b = d.resolve_brand_ref(ctx.require("--brand"))
    ctx.progress("正在读取「%s」的合作活动" % (b.get("name") or b.get("id")))
    rows = d.query("ct.campaigns.list", {"brandId": b["id"]}) or []
    rows = [r for r in rows if isinstance(r, dict)]
    ctx.emit(data={"brand": b.get("name"), "brandId": b.get("id"), "count": len(rows),
                   "campaigns": rows}, route="ct.campaigns.list")
    return EXIT_OK


# ─────────── 读：A3 逐条只读实测后补上的子通路（TICKET-186） ───────────
# 以下五条是"未实测不承诺"里**能通的**那一半 —— 2026-10-15 逐条只读实测全部返回 200
# （每条的命令与返回原文见 TICKET-186 回报）。能力清单里原先写着
# 「合作追踪：订单与视频明细两条路由未实测 ⇒ 未实测不承诺」，本条把它们补成命令。
# 仍然**不补命令**的是写类路由：只读实测证实 `ct.deals.create`／`ct.deals.update`／
# `ct.videos.create`／`ct.videos.unlink`／`ct.videos.refreshAsync` **存在但是 mutation**
# （GET 报 405 `Unsupported GET-request to mutation procedure`）—— 本工序只做只读，
# 故按"写语义、本工序不承诺"登记，**不在这里假装覆盖**，也不写成"不支持"。

def _campaign_id(ctx):
    return int(ctx.require("--campaign"))


def cmd_campaign_stats(ctx):
    """活动统计（`ct.campaigns.getStats`）：订单数／达人数／应有与已关联视频数等。

    返回体**自带活动对象**（`campaign`），所以"看这个活动的详情"也走这一条 ——
    另立一条只回活动对象的命令没有意义（同一次调用里就有）。
    """
    d = new_client(verbose=ctx.verbose)
    cid = _campaign_id(ctx)
    ctx.progress("正在读取活动 %d 的统计" % cid)
    obj = d.query("ct.campaigns.getStats", {"campaignId": cid}) or {}
    ctx.emit(data=obj, route="ct.campaigns.getStats")
    return EXIT_OK


def cmd_deals(ctx):
    """订单明细（`ct.deals.listWithVideoStats`）：活动下的达人合作单 ＋ 视频表现。"""
    d = new_client(verbose=ctx.verbose)
    cid = _campaign_id(ctx)
    ctx.progress("正在读取活动 %d 的订单明细" % cid)
    rows = d.query("ct.deals.listWithVideoStats", {"campaignId": cid}) or []
    rows = [r for r in rows if isinstance(r, dict)]
    ctx.emit(data={"campaignId": cid, "count": len(rows), "deals": rows},
             route="ct.deals.listWithVideoStats")
    return EXIT_OK


def cmd_videos(ctx):
    """视频明细（`ct.videos.list`）：活动下已关联的共创视频。"""
    d = new_client(verbose=ctx.verbose)
    cid = _campaign_id(ctx)
    ctx.progress("正在读取活动 %d 的视频明细" % cid)
    rows = d.query("ct.videos.list", {"campaignId": cid}) or []
    rows = [r for r in rows if isinstance(r, dict)]
    ctx.emit(data={"campaignId": cid, "count": len(rows), "videos": rows},
             route="ct.videos.list")
    return EXIT_OK


def cmd_resolve_channel(ctx):
    """把频道输入（@handle／链接／UC 编号）解析成频道编号（`ct.campaigns.resolveChannel`）。

    🔴 入参键是 **`channelInput`**（实测证实）：按语料里写的 `input` 传会 400
    （服务端 zod 原文 `expected string, path ["channelInput"]`）。
    """
    d = new_client(verbose=ctx.verbose)
    raw = ctx.require("频道")
    ctx.progress("正在解析频道输入")
    obj = d.query("ct.campaigns.resolveChannel", {"channelInput": str(raw)}) or {}
    ctx.emit(data=obj, route="ct.campaigns.resolveChannel")
    return EXIT_OK


def cmd_interests(ctx):
    """频道兴趣画像（`ct.videos.getChannelInterests`）。"""
    d = new_client(verbose=ctx.verbose)
    ch = ctx.require("--channel")
    ctx.progress("正在读取频道兴趣")
    obj = d.query("ct.videos.getChannelInterests", {"channelId": str(ch)}) or {}
    ctx.emit(data=obj, route="ct.videos.getChannelInterests")
    return EXIT_OK


HANDLERS = {
    "campaigns": cmd_campaigns,
    "campaign-stats": cmd_campaign_stats,
    "deals": cmd_deals,
    "videos": cmd_videos,
    "resolve-channel": cmd_resolve_channel,
    "interests": cmd_interests,
}

def _campaign_rows(client, brand_id):
    rows = client.query("ct.campaigns.list", {"brandId": int(brand_id)}) or []
    return [r for r in rows if isinstance(r, dict)]


def _norm(s):
    import re
    return re.sub(r"\s+", " ", str(s or "").strip()).lower()


def _plan_create_campaign(ctx, client):
    """只读解析目标品牌，把将新建的活动讲清楚（不发任何写）。"""
    b = client.resolve_brand_ref(ctx.require("--brand"))
    title = str(ctx.require("--title"))
    start = str(ctx.require("--start"))
    end = None if ctx.get("evergreen") else ctx.get("end")
    if not ctx.get("evergreen") and not end:
        raise CliError("没给结束日期：要么给 --end <日期>，要么显式加 --evergreen（长期有效）",
                       code=EXIT_USAGE,
                       hint="本次没有发起任何写")
    before = _campaign_rows(client, b["id"])
    dup = [r for r in before if _norm(r.get("title")) == _norm(title)]
    if dup:
        raise CliError("品牌「%s」下已经有同名活动「%s」（编号 %s）：拒绝建重名"
                       % (b.get("name"), title, dup[0].get("id")), code=EXIT_USAGE,
                       hint="换一个标题（验收用请带 `-验收-` 前缀）后重试")
    return {
        "targetName": title, "brand": "%s(编号 %s)" % (b.get("name"), b.get("id")),
        "workspaceId": b.get("workspaceId"),
        "impact": "会在品牌「%s」下新建合作活动「%s」：起 %s、止 %s；"
                  "建完立刻回读活动清单核对（本次请求数：1 次发包 ＋ 1 次回读）"
                  % (b.get("name"), title, start, end or "长期有效"),
        "changes": {"ct.campaigns.create": {"brandId": b.get("id"), "title": title,
                                           "startDate": start, "endDate": end,
                                           "isEvergreen": bool(ctx.get("evergreen"))}},
        "existingCampaignCount": len(before),
        "writesDatabase": True,
    }


def _run_create_campaign(ctx, client, plan):
    """真跑：建活动 → 回读活动清单核对（建→读）。

    入参键取自前端构建产物 `CreatorTracker-CEhsfuHf.js` 的调用点
    （`{brandId,title,brandName,brandHandle,brandYoutubeChannel,startDate,endDate,isEvergreen,brief}`）；
    这里只发**已知键**，`brandHandle／brandYoutubeChannel` 取品牌档案里的频道编号（取不到就不传）。
    """
    b = client.resolve_brand_ref(ctx.require("--brand"))
    title = str(ctx.require("--title"))
    start = str(ctx.require("--start"))
    end = None if ctx.get("evergreen") else ctx.get("end")
    channel = b.get("youtubeChannelId") or b.get("channelId")
    payload = {"brandId": int(b["id"]), "title": title, "brandName": b.get("name"),
               "startDate": start, "isEvergreen": bool(ctx.get("evergreen"))}
    if end:
        payload["endDate"] = end
    if channel:
        payload["brandHandle"] = channel
        payload["brandYoutubeChannel"] = channel
    if ctx.get("brief"):
        payload["brief"] = str(ctx.get("brief"))
    before = _campaign_rows(client, b["id"])
    created = client.mutate("ct.campaigns.create", payload) or {}
    after = _campaign_rows(client, b["id"])
    new_id = created.get("id") or created.get("campaignId")
    hit = [r for r in after if str(r.get("id")) == str(new_id)] if new_id else []
    if not hit:
        hit = [r for r in after if _norm(r.get("title")) == _norm(title)
               and str(r.get("id")) not in [str(x.get("id")) for x in before]]
    created_row = hit[-1] if hit else None
    verified = bool(created_row) and len(after) == len(before) + 1
    reason = "" if verified else ("回读没看到新活动（活动数 %d → %d，编号命中 %s）"
                                 % (len(before), len(after), bool(created_row)))
    return {
        "mutation": {"route": "ct.campaigns.create", "request": payload,
                     "服务端返回": {k: v for k, v in created.items()
                                    if k in ("id", "campaignCode", "syncError", "title")}},
        "readback": {"verified": verified, "reason": reason,
                     "detail": {"before": {"campaignCount": len(before)},
                                "after": {"campaignCount": len(after),
                                          "newCampaignId": (created_row or {}).get("id"),
                                          "newCampaignTitle": (created_row or {}).get("title"),
                                          "campaignCode": (created_row or {}).get("campaignCode"),
                                          "status": (created_row or {}).get("status")}},
                     "how": "重新调用 ct.campaigns.list 核对：活动数 +1 且新编号／标题逐字命中"},
        "rolledBack": False,
        "rollbackNote": "本次活动未回滚（新建活动是业务对象）。验收用完请回滚："
                        "`daniel ct delete-campaign --campaign %s --brand %s --confirm "
                        "--delete-token \"%s\"`" % ((created_row or {}).get("id"), b.get("id"), title),
        "detail": {"新活动编号": (created_row or {}).get("id"),
                   "活动码": (created_row or {}).get("campaignCode")},
    }


# ─────────────────────────── 写：删除活动（删除类，二次确认） ───────────────────────────
def _find_campaign(client, brand_id, campaign_id):
    rows = _campaign_rows(client, brand_id)
    hit = [r for r in rows if str(r.get("id")) == str(campaign_id)]
    if not hit:
        raise CliError("品牌编号 %s 下找不到活动编号 %s" % (brand_id, campaign_id),
                       code=EXIT_USAGE,
                       hint="先用 `daniel ct campaigns --brand <品牌>` 看活动编号")
    return hit[0], rows


def _plan_delete_campaign(ctx, client):
    b = client.resolve_brand_ref(ctx.require("--brand"))
    cid = ctx.require("--campaign")
    row, rows = _find_campaign(client, b["id"], cid)
    return {
        "targetName": row.get("title"), "brand": "%s(编号 %s)" % (b.get("name"), b.get("id")),
        "workspaceId": b.get("workspaceId"),
        "impact": "删除品牌「%s」下的合作活动「%s」（编号 %s，活动码 %s，状态 %s）："
                  "**不可逆**，活动与其关联数据一并消失"
                  % (b.get("name"), row.get("title"), row.get("id"), row.get("campaignCode"),
                     row.get("status")),
        "changes": {"ct.campaigns.deleteCampaign": {"campaignId": int(row.get("id"))}},
        "deleteTokenExample": row.get("title"),
        "existingCampaignCount": len(rows),
        "writesDatabase": True,
    }


#: 「可以永久删除」的前置状态（服务端原文实测：HTTP 412
#: `Campaign must be archived or completed before deletion`）
DELETABLE_STATUS = ("archived", "completed")


def _run_delete_campaign(ctx, client, plan):
    """真跑：**必要时先归档** → 永久删除 → 回读活动清单证明无残留。

    🔴 服务端前置（A1 实测发现，2026-10-16）：活动处于 `active` 时直接删会被拒 ——
    HTTP 412 `PRECONDITION_FAILED`，原文 `Campaign must be archived or completed before
    deletion`。所以"删除"在服务端是**两步**：先 `ct.campaigns.archive`，再
    `ct.campaigns.deleteCampaign`。本命令把这两步按需串起来，且每一步都记进结果
    （不假装"一次调用就删掉了"）。
    """
    b = client.resolve_brand_ref(ctx.require("--brand"))
    cid = int(ctx.require("--campaign"))
    before = _campaign_rows(client, b["id"])
    steps = []
    target = [r for r in before if str(r.get("id")) == str(cid)]
    status = str((target[0] if target else {}).get("status") or "").lower()
    if target and status not in DELETABLE_STATUS:
        ctx.progress("该活动状态是「%s」：服务端要求先归档或完成才能永久删除，正在归档"
                     % (status or "未知"))
        client.mutate("ct.campaigns.archive", {"campaignId": cid})
        steps.append({"步骤": "归档（服务端前置）", "路由": "ct.campaigns.archive",
                      "前置状态": status or "未知"})
    client.mutate("ct.campaigns.deleteCampaign", {"campaignId": cid})
    steps.append({"步骤": "永久删除", "路由": "ct.campaigns.deleteCampaign"})
    after = _campaign_rows(client, b["id"])
    gone = not [r for r in after if str(r.get("id")) == str(cid)]
    verified = gone and len(after) == len(before) - 1
    reason = "" if verified else ("回读仍能看到活动 %s（活动数 %d → %d）：删除没有生效"
                                 % (cid, len(before), len(after)))
    return {
        "mutation": {"route": ("ct.campaigns.archive ＋ ct.campaigns.deleteCampaign"
                               if len(steps) > 1 else "ct.campaigns.deleteCampaign"),
                     "request": {"campaignId": cid}, "步骤": steps},
        "readback": {"verified": verified, "reason": reason,
                     "detail": {"before": {"campaignCount": len(before), "targetPresent": True,
                                           "targetStatus": status or "未知"},
                                "after": {"campaignCount": len(after), "targetPresent": not gone},
                                "remainingCampaignIds": [r.get("id") for r in after],
                                "步骤": steps},
                     "how": "重新调用 ct.campaigns.list 核对：目标编号已不存在且活动数 -1"
                            "（必要时先归档再删，两步都留痕）"},
        "rolledBack": None,
        "rollbackNote": "删除不可逆，没有回滚动作；本次删除对象由调用方指定并二次确认"
                        "（--delete-token 与活动标题逐字一致）",
        "detail": {"已删除活动": plan.get("targetName"), "编号": cid, "步骤": steps},
    }


WRITE_HANDLERS = {
    "create-campaign": live_managed_write(BOARD, "create-campaign", "新建合作活动",
                                          plan_fn=_plan_create_campaign,
                                          run_fn=_run_create_campaign,
                                          danger="会真的在品牌下建出活动（建完回读核对）"),
    "delete-campaign": gated_write(BOARD, "delete-campaign", "删除合作活动（不可逆）",
                                   stage=STAGE_LIVE, plan_fn=_plan_delete_campaign,
                                   run_fn=_run_delete_campaign, delete="活动标题",
                                   danger="不可逆：删完活动与其关联数据一并消失"),
}
