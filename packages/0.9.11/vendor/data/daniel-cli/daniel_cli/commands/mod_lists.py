# -*- coding: utf-8 -*-
"""lists 模块：红人名单（读链走共享客户端；写链走统一门禁链，真实执行已接通）。

写链口径（TICKET-152）：
  · 权限轴：账号对「红人名单」有没有写权限，由 `permissions` 的能力矩阵判定（退出码 2 说明理由）；
  · 确认轴：不带 `--confirm` 只做干跑（打印将要发生什么＋影响范围），退出码 3，零写入；
  · 删除凭据轴：`delete` 是删除类，除 `--confirm` 外必须再给 `--delete-token <名单名>`
    （把名单名原样再写一遍，写错即拒、退出码 2、零删除）；
  · 执行后**回读校验**（重新拉一遍名单核对），并留一条审计记录（`daniel account audit`）。

写路由（实证，出处 `.kol-tools/daniel_lists.py` 的文件头注释）：
  `lists.create({brandId, name})`／`lists.rename({listId, brandId, name})`／
  `lists.delete({id, brandId})`（注意 delete 的键是 `id` 不是 `listId`）。
"""
import re
import sys

from ..exits import EXIT_OK
from ..runtime import CliError, new_client
from ._common import STAGE_LIVE, gated_write, paged


BOARD = "lists"


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip()).lower()


def _client(ctx):
    return new_client(verbose=ctx.verbose)


def _brand(ctx, client):
    """品牌引用 → 品牌行（跨工作区解析；它同时给出 brandId 与 workspaceId）。"""
    return client.resolve_brand_ref(ctx.require("--brand"))


def _rows(client, brand_id):
    return [r for r in (client.lists(brand_id) or []) if isinstance(r, dict)]


def _brief(brand):
    return "%s(编号 %s)" % (brand.get("name"), brand.get("id"))


# ─────────────────────────── 读 ───────────────────────────
def cmd_by_brand(ctx):
    d = _client(ctx)
    b = d.resolve_brand_ref(ctx.require("--brand"))
    ctx.progress("正在读取「%s」下的名单" % (b.get("name") or b.get("id")))
    rows = _rows(d, b["id"])
    ctx.emit(data={"brand": b.get("name"), "brandId": b.get("id"), "count": len(rows),
                   "lists": rows}, route="lists.listByBrand")
    return EXIT_OK


def cmd_items(ctx):
    d = _client(ctx)
    list_id = int(ctx.require("--list-id"))
    ctx.progress("正在读取名单 %d 的条目" % list_id)
    rows = [r for r in (d.items(list_id) or []) if isinstance(r, dict)]
    total = len(rows)
    rows = paged(rows, ctx.get("limit"), ctx.get("offset"))
    data = {"listId": list_id, "total": total, "returned": len(rows), "items": rows}
    # `--with-handle`：显式开关才逐条补 @handle（TICKET-222 第 3 项）。
    # 为什么不做默认：`lists.getItems` 不返回 handle，补它必须逐条打频道详情接口 ——
    # 那是额外 N 次网络请求，不能让"只想看名单有谁"的调用平白变慢。
    # 不带开关时 data 的键与顺序**与改造前逐字节一致**（只是走上面那条原路）。
    if ctx.get("with-handle"):
        rows, lookup = _fill_handle(ctx, d, rows)
        data["items"] = rows
        data["handleLookup"] = lookup
    ctx.emit(data=data, route="lists.getItems")
    return EXIT_OK


def _fill_handle(ctx, client, rows):
    """给每条名单条目补 `handle`（走频道详情，复用客户端 15 分钟进程内缓存）。

    纪律：**补不到就写字**，不留 null —— 详情接口偶发 5xx、重试仍失败时，
    `handle` 是「未取到（详情接口重试 5 次仍失败）」而不是 null；这种情况下条目本身仍然可用。
    """
    before = dict(_detail_stats(client))
    out = []
    cache_hits = 0
    failed = 0
    for i, row in enumerate(rows, 1):
        cid = str(row.get("channelId") or "").strip()
        row = dict(row)
        if not cid:
            row["handle"] = "未取到（该条目没有频道编号）"
            failed += 1
            out.append(row)
            continue
        ctx.progress("补 handle（%d/%d）：%s" % (i, len(rows), cid))
        try:
            detail = client.channel_detail(channelId=cid) or {}
            if detail.get("从缓存命中") is True:
                cache_hits += 1
            handle = str(detail.get("handle") or "").strip()
            if handle:
                row["handle"] = handle if handle.startswith("@") else "@" + handle
            else:
                row["handle"] = "未取到（详情接口返回里没有 handle 字段）"
                failed += 1
        except Exception as e:                                           # noqa: BLE001
            row["handle"] = "未取到（详情接口失败：%s）" % str(e)[:120]
            failed += 1
        out.append(row)
    after = _detail_stats(client)
    lookup = {
        "requested": len(rows),
        "filled": len(rows) - failed,
        "notFilled": failed,
        "servedFromCache": cache_hits,
        "networkRequests": after["networkRequests"] - before["networkRequests"],
        "detailCacheTtlSeconds": after["ttlSeconds"],
        "how": "逐条用频道详情接口补齐 handle；同一 channelId 在 %d 秒内重复出现时走进程内缓存，"
               "不发网络请求" % after["ttlSeconds"],
    }
    return out, lookup


def _detail_stats(client=None):
    """读共享客户端的缓存／请求计数器。

    **必须读"这个客户端实例所属的那个模块"**：CLI 的能力加载器（`runtime.load_client`）与
    直接 `import daniel_client` 可能是两份模块实例，各自有一套计数器 —— 读错那一份就会把
    "确实发了 1 次请求"报成 0。实在读不到就退化成 0 与默认 TTL（不留 null）。
    """
    mod = None
    if client is not None:
        mod = sys.modules.get(type(client).__module__)
    if mod is None:
        try:
            from ..runtime import load_client
            mod = load_client()
        except Exception:                                                # noqa: BLE001
            mod = None
    fn = getattr(mod, "detail_cache_stats", None)
    if callable(fn):
        try:
            return fn()
        except Exception:                                                # noqa: BLE001
            pass
    return {"networkRequests": 0, "cacheHits": 0, "ttlSeconds": 900}


# ─────────────────────────── 写：新建 ───────────────────────────
def _plan_create(ctx, client):
    b = _brand(ctx, client)
    name = str(ctx.require("--name")).strip()
    if not name:
        raise CliError("名单名不能为空", hint="给一个能被一眼认出来的名单名，例如「临时名单-验收」")
    rows = _rows(client, b["id"])
    dup = [r for r in rows if _norm(r.get("name")) == _norm(name)]
    if dup:
        raise CliError("品牌「%s」下已经有同名名单「%s」（编号 %s）：拒绝新建重名名单"
                       % (b.get("name"), name, dup[0].get("id")),
                       hint="换一个名字，或先用 `daniel lists items --list-id %s` 看那份名单"
                            % dup[0].get("id"))
    return {
        "targetName": name, "brand": _brief(b), "workspaceId": b.get("workspaceId"),
        "impact": "在品牌「%s」下新增 1 个空名单；不影响该品牌下已有的 %d 份名单"
                  % (b.get("name"), len(rows)),
        "changes": {"lists.create": {"brandId": b.get("id"), "name": name}},
        "existingListCount": len(rows),
    }


def _run_create(ctx, client, plan):
    b = client.resolve_brand_ref(ctx.require("--brand"))
    name = plan["targetName"]
    before = _rows(client, b["id"])
    client.mutate("lists.create", {"brandId": int(b["id"]), "name": name})
    after = _rows(client, b["id"])
    hit = [r for r in after if _norm(r.get("name")) == _norm(name)]
    created = hit[-1] if hit else None
    delta = len(after) - len(before)
    verified = bool(created) and delta == 1
    reason = "" if verified else ("回读未看到新名单（名单数 %d → %d，同名命中 %d 条）"
                                  % (len(before), len(after), len(hit)))
    return {
        "mutation": {"route": "lists.create",
                     "request": {"brandId": int(b["id"]), "name": name}},
        "readback": {"verified": verified, "reason": reason,
                     "detail": {"before": {"listCount": len(before)},
                                "after": {"listCount": len(after),
                                          "newListId": (created or {}).get("id"),
                                          "newListName": (created or {}).get("name"),
                                          "influencerCount": (created or {}).get("influencerCount")}},
                     "how": "重新调用 lists.listByBrand 核对：名单数 +1 且名字逐字命中"},
        "rolledBack": False,
        "rollbackNote": "新建对象如需清理，用 `daniel lists delete --list-id %s --brand %s "
                        "--confirm --delete-token \"%s\"`" % ((created or {}).get("id"),
                                                             b.get("id"), name),
        "detail": {"新名单编号": (created or {}).get("id")},
    }


# ─────────────────────────── 写：改名 ───────────────────────────
def _find_list(client, ctx, list_id):
    b = _brand(ctx, client)
    rows = _rows(client, b["id"])
    hit = [r for r in rows if str(r.get("id")) == str(list_id)]
    if not hit:
        raise CliError("品牌「%s」下找不到名单编号 %s" % (b.get("name"), list_id),
                       hint="先用 `daniel lists by-brand --brand %s` 看该品牌下的名单编号"
                            % b.get("id"))
    return b, hit[0], rows


def _plan_rename(ctx, client):
    list_id = int(ctx.require("--list-id"))
    new_name = str(ctx.require("--name")).strip()
    b, target, rows = _find_list(client, ctx, list_id)
    if _norm(target.get("name")) == _norm(new_name):
        raise CliError("新名字与原名一致（「%s」）：没有必要改名" % target.get("name"),
                       hint="给一个不同的名字，或不做这次写")
    dup = [r for r in rows if _norm(r.get("name")) == _norm(new_name) and r.get("id") != target.get("id")]
    if dup:
        raise CliError("品牌「%s」下已经有叫「%s」的名单（编号 %s）：拒绝改成重名"
                       % (b.get("name"), new_name, dup[0].get("id")))
    return {"targetName": target.get("name"), "brand": _brief(b),
            "workspaceId": b.get("workspaceId"),
            "impact": "把名单「%s」（编号 %s，含 %s 个 creator）改名为「%s」；名单里的条目不动"
                      % (target.get("name"), target.get("id"),
                         target.get("influencerCount"), new_name),
            "changes": {"lists.rename": {"listId": int(target.get("id")),
                                         "brandId": int(b.get("id")), "name": new_name}},
            "currentName": target.get("name"), "newName": new_name}


def _run_rename(ctx, client, plan):
    b = client.resolve_brand_ref(ctx.require("--brand"))
    list_id = int(ctx.require("--list-id"))
    new_name = plan["newName"]
    before = _rows(client, b["id"])
    client.mutate("lists.rename", {"listId": list_id, "brandId": int(b["id"]), "name": new_name})
    after = _rows(client, b["id"])
    hit = [r for r in after if str(r.get("id")) == str(list_id)]
    verified = bool(hit) and _norm(hit[0].get("name")) == _norm(new_name)
    reason = "" if verified else ("回读到的名字是「%s」，与写入值「%s」不一致"
                                  % ((hit[0].get("name") if hit else "（名单不见了）"), new_name))
    return {
        "mutation": {"route": "lists.rename",
                     "request": {"listId": list_id, "brandId": int(b["id"]), "name": new_name}},
        "readback": {"verified": verified, "reason": reason,
                     "detail": {"before": {"name": plan.get("currentName")},
                                "after": {"name": (hit[0] if hit else {}).get("name"),
                                          "influencerCount": (hit[0] if hit else {}).get("influencerCount")},
                                "listCountChanged": len(after) - len(before)},
                     "how": "重新调用 lists.listByBrand 核对：该编号的名字逐字等于写入值"},
        "rolledBack": False,
        "rollbackNote": "如需还原，再跑一次 rename 把名字改回「%s」" % plan.get("currentName"),
        "detail": {"新名字": new_name},
    }


# ─────────────────────────── 写：删除（删除类，二次确认） ───────────────────────────
def _plan_delete(ctx, client):
    list_id = int(ctx.require("--list-id"))
    b, target, rows = _find_list(client, ctx, list_id)
    n = target.get("influencerCount")
    if isinstance(n, int) and n > 0 and not ctx.get("allow-non-empty"):
        raise CliError("名单「%s」（编号 %s）里还有 %d 个 creator：默认拒绝删除非空名单"
                       % (target.get("name"), target.get("id"), n),
                       hint="确认要连条目一起删，请显式加 --allow-non-empty（仍需 --confirm 与 "
                            "--delete-token）；只想清空条目请用名单页面操作")
    return {"targetName": target.get("name"), "brand": _brief(b),
            "workspaceId": b.get("workspaceId"),
            "impact": "删除品牌「%s」下的名单「%s」（编号 %s，含 %s 个 creator）；"
                      "删除后该名单与其条目一并消失，不可逆"
                      % (b.get("name"), target.get("name"), target.get("id"),
                         target.get("influencerCount")),
            "changes": {"lists.delete": {"id": int(target.get("id")),
                                         "brandId": int(b.get("id"))}},
            "deleteTokenExample": target.get("name"),
            "influencerCount": target.get("influencerCount"),
            "existingListCount": len(rows)}


def _run_delete(ctx, client, plan):
    b = client.resolve_brand_ref(ctx.require("--brand"))
    list_id = int(ctx.require("--list-id"))
    before = _rows(client, b["id"])
    client.mutate("lists.delete", {"id": list_id, "brandId": int(b["id"])})
    after = _rows(client, b["id"])
    gone = not [r for r in after if str(r.get("id")) == str(list_id)]
    verified = gone and len(after) == len(before) - 1
    reason = "" if verified else ("回读仍能看到名单 %s（名单数 %d → %d）：删除没有生效"
                                  % (list_id, len(before), len(after)))
    return {
        "mutation": {"route": "lists.delete", "request": {"id": list_id, "brandId": int(b["id"])}},
        "readback": {"verified": verified, "reason": reason,
                     "detail": {"before": {"listCount": len(before), "targetPresent": True},
                                "after": {"listCount": len(after), "targetPresent": not gone}},
                     "how": "重新调用 lists.listByBrand 核对：目标编号已不存在且名单数 -1"},
        "rolledBack": None,
        "rollbackNote": "删除不可逆，没有回滚动作；本次删除对象由调用方指定并二次确认",
        "detail": {"已删除名单": plan.get("targetName"), "编号": list_id},
    }


# ─────────── 读：A3 逐条只读实测后补上的子通路（TICKET-186） ───────────
# 语料 §15.3.3 把 `lists.generateShareLink`／`lists.autoPriority`／`lists.updateItemTags` 等
# 登记为"仅定位未实测"。2026-10-15 逐条只读实测的结论是：**这些写路由都真实存在**
# （GET 报 405 `Unsupported GET-request to mutation procedure`，说明路由在、只是 mutation），
# 而它们的**状态查询**一半是只读的、实测 200 可用 —— 就把这一半补成命令；
# 写的那一半按"写语义、本工序不承诺"登记，**不写成"不支持"**（那是两回事）。

def cmd_saved_channel_ids(ctx):
    """这个品牌下所有名单里已保存过的频道编号（`lists.savedChannelIds`）。

    用途：批量加人／去重前先拿"系统里已经有哪些人"，避免把同一批人重复写进名单。
    """
    d = _client(ctx)
    b = _brand(ctx, d)
    ctx.progress("正在读取「%s」下已保存的频道编号" % (b.get("name") or b.get("id")))
    rows = d.query("lists.savedChannelIds", {"brandId": int(b["id"])}) or []
    ids = [str(x) for x in rows if x]
    ctx.emit(data={"brand": b.get("name"), "brandId": b.get("id"), "count": len(ids),
                   "channelIds": ids}, route="lists.savedChannelIds")
    return EXIT_OK


def cmd_share_status(ctx):
    """名单的分享状态（`lists.getShareStatus`）：有没有开启分享、分享码、何时分享的。"""
    d = _client(ctx)
    list_id = int(ctx.require("--list-id"))
    ctx.progress("正在读取名单 %d 的分享状态" % list_id)
    obj = d.query("lists.getShareStatus", {"listId": list_id}) or {}
    ctx.emit(data=obj, route="lists.getShareStatus")
    return EXIT_OK


def cmd_auto_priority_status(ctx):
    """名单的自动优先级状态（`lists.getAutoPriorityStatus`）：跑没跑、进度、完成时间。"""
    d = _client(ctx)
    list_id = int(ctx.require("--list-id"))
    ctx.progress("正在读取名单 %d 的自动优先级状态" % list_id)
    obj = d.query("lists.getAutoPriorityStatus", {"listId": list_id}) or {}
    ctx.emit(data=obj, route="lists.getAutoPriorityStatus")
    return EXIT_OK


HANDLERS = {
    "by-brand": cmd_by_brand,
    "items": cmd_items,
    "saved-channel-ids": cmd_saved_channel_ids,
    "share-status": cmd_share_status,
    "auto-priority-status": cmd_auto_priority_status,
}

WRITE_HANDLERS = {
    "create": gated_write(BOARD, "create", "在品牌下新建名单", stage=STAGE_LIVE,
                          plan_fn=_plan_create, run_fn=_run_create),
    "rename": gated_write(BOARD, "rename", "重命名名单", stage=STAGE_LIVE,
                          plan_fn=_plan_rename, run_fn=_run_rename),
    "delete": gated_write(BOARD, "delete", "删除名单（不可逆）", stage=STAGE_LIVE,
                          plan_fn=_plan_delete, run_fn=_run_delete,
                          delete="名单名",
                          danger="不可逆：名单与其条目一并删除"),
}
