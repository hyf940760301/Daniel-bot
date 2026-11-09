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
from ._common import STAGE_LIVE, gated_write, paged, scrub_text


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


# ─────────────────────── 写：批量加人（lists.batchAddItems） ───────────────────────
# 路由实证：`lists.batchAddItems({listId, items:[…]})`，单批 ≤100；`tier` 必须是数字 1–4
# （出处：`mcp/corpus/kol-daniel-api/references/60-data-layer.md` §15.3.3／§15.3.4，
# 与 `.kol-tools/daniel_search.py::cmd_push` 的落库实现一致）。
# 本命令**不重写检索/筛选**：只负责"把给定的条目安全写进名单"，筛选与去重口径仍在检索侧。
ADD_ITEM_FIELDS = ("channelId", "channelTitle", "subscriberCount", "country", "tier",
                   "cqiScore", "contactEmail", "engagementRate")
ADD_BATCH_LIMIT = 100
_ADD_DETAIL_MAX = 20


def _system_tier(subs):
    """系统口径的体量档（写库用数字 1–4）。

    单一真源在 `.kol-tools/daniel_search.py::system_tier`（与 bundle 的 `function ls`
    逐字一致）。这里只**调用**它，不复制分界表 —— 两套分界一定会漂移。
    """
    from ..runtime import load_capability
    return load_capability("daniel_search").system_tier(subs)


def _num(value, field, idx, integer=False):
    """文件里的数值字段 → 数字；不合法就报人话（不静默当空）。

    为什么不做"猜"：`tier` 是**写进系统的字段**，猜一个档位等于把错数据写进名单。
    空值返回 None（调用方据此保留"未取到"），非空但不合法则拒绝。
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise CliError("第 %d 条的 %s 不是数字：%r（布尔值不能当数值用）" % (idx, field, value))
    if isinstance(value, (int, float)):
        n = float(value)
    else:
        s = str(value).strip().replace(",", "")
        if s.endswith("%"):
            s = s[:-1].strip()
        if not s:
            return None
        try:
            n = float(s)
        except ValueError:
            raise CliError("第 %d 条的 %s 不是数字：%r（给数字，例如 120000／3.2）"
                           % (idx, field, value))
    if n != n or n in (float("inf"), float("-inf")):
        raise CliError("第 %d 条的 %s 不是有限数字：%r" % (idx, field, value))
    if integer:
        if int(n) != n:
            raise CliError("第 %d 条的 %s 必须是整数：%r" % (idx, field, value))
        return int(n)
    return int(n) if float(n).is_integer() else n


def _coerce_item(raw, idx):
    """一行文件条目 → `batchAddItems` 的 item；返回 `(item, 未知字段, tier 是否推导)`。"""
    if not isinstance(raw, dict):
        raise CliError("第 %d 条不是对象（JSON 数组里每一项都要是对象）：%r"
                       % (idx, type(raw).__name__))
    unknown = sorted(set(raw) - set(ADD_ITEM_FIELDS))
    cid = str(raw.get("channelId") or "").strip()
    if not cid:
        raise CliError("第 %d 条缺 channelId：每条都要有频道编号（形如 UCxxxxxxxxxxxxxxxxxxxxxx）"
                       % idx)
    item = {"channelId": cid}
    title = raw.get("channelTitle")
    if title not in (None, ""):
        item["channelTitle"] = str(title).strip()
    subs = _num(raw.get("subscriberCount"), "subscriberCount", idx, integer=True)
    if subs is not None:
        item["subscriberCount"] = subs
    country = raw.get("country")
    if country not in (None, ""):
        item["country"] = str(country).strip().upper()
    tier = _num(raw.get("tier"), "tier", idx, integer=True)
    derived = False
    if tier is not None:
        if tier not in (1, 2, 3, 4):
            raise CliError("第 %d 条的 tier 必须是 1–4 的数字（当前 %r）："
                           "档名不能直接写进系统字段" % (idx, raw.get("tier")))
        item["tier"] = tier
    elif subs is not None:
        # 与检索落库同一口径（system_tier 的真源在 daniel_search.py，这里只调用）
        item["tier"] = _system_tier(subs)
        derived = True
    cqi = _num(raw.get("cqiScore"), "cqiScore", idx)
    if cqi is not None:
        item["cqiScore"] = cqi
    email = raw.get("contactEmail")
    if email not in (None, ""):
        item["contactEmail"] = str(email).strip()
    er = _num(raw.get("engagementRate"), "engagementRate", idx)
    if er is not None:
        item["engagementRate"] = er
    return item, unknown, derived


def _read_items_file(path, ctx):
    """读 `--items-file`：JSON 数组，逐条校验；返回 `(items, 统计)`。"""
    import io
    import json
    import os
    p = os.path.abspath(os.path.expanduser(str(path).strip()))
    if not os.path.isfile(p):
        raise CliError("条目文件不存在：%s" % p,
                       hint="给一个 JSON 数组文件的路径，例如 --items-file ./kol-items.json；"
                            "最小写法 [{\"channelId\":\"UCxxxxxxxxxxxxxxxxxxxxxx\"}]")
    try:
        with io.open(p, encoding="utf-8") as fh:
            raw = json.load(fh)
    except ValueError as e:
        raise CliError("条目文件不是合法 JSON：%s（%s）" % (p, e),
                       hint="顶层要是一个数组，例如 [{\"channelId\":\"UC...\"}]")
    except OSError as e:
        raise CliError("条目文件读不出来：%s（%s）" % (p, e))
    if not isinstance(raw, list):
        raise CliError("条目文件的顶层必须是数组（当前是 %s）：%s"
                       % (type(raw).__name__, p),
                       hint="写法：[{\"channelId\":\"UC...\",\"channelTitle\":\"频道名\"}]")
    if not raw:
        raise CliError("条目文件里是空数组：没有可加的人（%s）" % p,
                       hint="至少给一条，例如 [{\"channelId\":\"UC...\"}]")
    items, unknown, errors = [], set(), []
    derived = 0
    for i, row in enumerate(raw, 1):
        try:
            item, unk, der = _coerce_item(row, i)
        except CliError as e:
            errors.append(e.message)
            continue
        items.append(item)
        unknown |= set(unk)
        derived += 1 if der else 0
    if errors:
        more = "" if len(errors) <= 3 else "；另有 %d 条同类问题" % (len(errors) - 3)
        raise CliError("条目文件有 %d 条不合法，第一条问题：%s%s"
                       % (len(errors), errors[0], more),
                       hint="逐条改好后重跑；不合法条目不会写入")
    return items, {"文件": p, "原始条数": len(raw), "未知字段已忽略": sorted(unknown),
                   "tier 按订阅数推导": derived}


def _parse_channel_ids(text):
    """`--channel-ids` → 去重后的编号列表（逗号或空白分隔都接受）。"""
    parts = [p.strip() for p in re.split(r"[,\s]+", str(text or "")) if p.strip()]
    if not parts:
        raise CliError("--channel-ids 里没有可用的频道编号",
                       hint="写法：--channel-ids 123456,234567")
    out, seen, dup = [], set(), 0
    for cid in parts:
        if cid in seen:
            dup += 1
            continue
        seen.add(cid)
        out.append(cid)
    return out, dup


def _items_rows(raw):
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        for key in ("items", "results", "rows", "list", "data"):
            val = raw.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
    return []


def _items_count(raw, rows):
    if isinstance(raw, dict):
        for key in ("total", "count", "totalCount"):
            val = raw.get(key)
            if isinstance(val, int) and not isinstance(val, bool):
                return val
    return len(rows)


def _read_list(client, list_id):
    """读名单条目：返回 `{rows, total, ids}`；读不到明细就拒绝（不能盲写）。"""
    try:
        raw = client.items(list_id)
    except Exception as e:                                               # noqa: BLE001
        raise CliError("读不到名单 %d 的条目：%s" % (list_id, scrub_text(e)),
                       hint="先用 `daniel lists by-brand --brand <品牌>` 确认名单编号；"
                            "编号不对时不会执行任何写")
    rows = _items_rows(raw)
    total = _items_count(raw, rows)
    if not rows and total > 0:
        raise CliError("名单 %d 的接口只返回了总数（%d），读不到条目明细：无法预检重复，已拒绝写入"
                       % (list_id, total),
                       hint="先用 `daniel lists items --list-id %d` 看条目；"
                            "确认接口恢复后重跑" % list_id)
    ids = {str(r.get("channelId")).strip() for r in rows
           if str(r.get("channelId") or "").strip()}
    return {"rows": rows, "total": total, "ids": ids}


def _first_num(*vals):
    for v in vals:
        if v in (None, "") or isinstance(v, bool):
            continue
        try:
            n = float(v)
        except (TypeError, ValueError):
            continue
        if n == n and n not in (float("inf"), float("-inf")):
            return int(n) if float(n).is_integer() else n
    return None


def _detail_to_item(cid, detail):
    """频道详情 → item（只搬详情里**真实存在**的字段；缺的键不写）。"""
    d = detail if isinstance(detail, dict) else {}
    stats = d.get("statistics") if isinstance(d.get("statistics"), dict) else (
        d.get("stats") if isinstance(d.get("stats"), dict) else {})
    item = {"channelId": cid}
    title = d.get("title") or d.get("channelTitle")
    if title not in (None, ""):
        item["channelTitle"] = str(title).strip()
    subs = _first_num(d.get("subscriberCount"), stats.get("subscriberCount"))
    if subs is not None:
        item["subscriberCount"] = subs
    country = d.get("country")
    if country not in (None, ""):
        item["country"] = str(country).strip().upper()
    tier = d.get("tier")
    if isinstance(tier, int) and not isinstance(tier, bool) and tier in (1, 2, 3, 4):
        item["tier"] = tier
    elif subs is not None:
        item["tier"] = _system_tier(subs)
    cqi = _first_num(d.get("cqiScore"), d.get("cqi"))
    if cqi is not None:
        item["cqiScore"] = cqi
    email = d.get("businessEmail") or d.get("contactEmail") or d.get("email")
    if email not in (None, ""):
        item["contactEmail"] = str(email).strip()
    er = _first_num(d.get("engagementRate"), d.get("engagementRatePercent"))
    if er is not None:
        item["engagementRate"] = er
    return item


def _item_missing(item):
    return [f for f in ADD_ITEM_FIELDS if item.get(f) in (None, "")]


def _enrich_by_detail(ctx, client, ids):
    """只给 ID 时：逐条回查频道详情补齐；补不到就留空并记「未取到」。"""
    items, not_filled, errors = [], [], 0
    miss_by_field = {f: 0 for f in ADD_ITEM_FIELDS if f != "channelId"}
    for i, cid in enumerate(ids, 1):
        ctx.progress("回查频道详情（%d/%d）：%s" % (i, len(ids), cid))
        err = ""
        detail = {}
        try:
            detail = client.channel_detail(channelId=cid) or {}
        except Exception as e:                                          # noqa: BLE001
            err = scrub_text(e) or "频道详情接口失败"
            errors += 1
        item = _detail_to_item(cid, detail)
        miss = _item_missing(item)
        if miss:
            for f in miss:
                miss_by_field[f] += 1
            not_filled.append({"channelId": cid, "缺字段": miss,
                               "原因": err or ("频道详情里没有这些字段" if detail
                                               else "频道详情返回空")})
        items.append(item)
    report = {
        "requested": len(ids),
        "detailFailed": errors,
        "notFilled": not_filled[:_ADD_DETAIL_MAX],
        "notFilledCount": len(not_filled),
        "notFilledTruncated": len(not_filled) > _ADD_DETAIL_MAX,
        "missingByField": {k: "%d/%d" % (v, len(ids)) for k, v in miss_by_field.items()},
    }
    return items, report


def _dedupe_items(items):
    out, seen, dup = [], set(), 0
    for it in items:
        cid = it["channelId"]
        if cid in seen:
            dup += 1
            continue
        seen.add(cid)
        out.append(it)
    return out, dup


def _source_of(ctx):
    """条目来源：二选一。两个都给／都不给都在这里报**可操作**的人话。"""
    file_arg = ctx.get("items-file")
    ids_arg = ctx.get("channel-ids")
    has_file = bool(str(file_arg or "").strip())
    has_ids = bool(str(ids_arg or "").strip())
    if has_file and has_ids:
        raise CliError("条目来源只能二选一，这次两个都给了（--items-file 与 --channel-ids）。"
                       "没有执行任何写。",
                       hint="① 用文件：`--items-file ./kol-items.json`（JSON 数组）；"
                            "② 用编号：`--channel-ids 123456,234567`。任选一种重新跑。")
    if not has_file and not has_ids:
        raise CliError("条目来源二选一，这次一个都没给。没有执行任何写。",
                       hint="① `--items-file <路径>`：给一个 JSON 数组文件（从检索结果直接导出即可；"
                            "最小写法 [{\"channelId\":\"UC...\"}]，"
                            "常用写法 [{\"channelId\":\"UC...\",\"channelTitle\":\"频道名\","
                            "\"subscriberCount\":120000}]）；"
                            "② `--channel-ids 123456,234567`：直接给频道编号（会自动回查频道详情"
                            "补齐，补不到的标「未取到」）。任选一种重新跑。")
    return "items-file" if has_file else "channel-ids"


def _plan_add_items(ctx, client):
    """只读地算出"将往哪张名单加多少人、跳过谁、拆几批"；写入发生在 run_fn。"""
    list_id = int(ctx.require("--list-id"))
    limit = ctx.get("limit")
    if limit is not None:
        limit = int(limit)
        if limit <= 0:
            raise CliError("--limit 必须是大于 0 的整数（当前 %s）" % ctx.get("limit"),
                           hint="不给 --limit 表示全加；要限制人数就给一个正整数，例如 --limit 50")
    source = _source_of(ctx)
    meta = {"来源": source}
    if source == "items-file":
        raw_items, file_meta = _read_items_file(ctx.get("items-file"), ctx)
        meta.update(file_meta)
        raw_count = len(raw_items)
        items, dup = _dedupe_items(raw_items)
        meta["条目内重复"] = dup
        meta["文件原始条数"] = raw_count
    else:
        ids, dup = _parse_channel_ids(ctx.get("channel-ids"))
        raw_count = len(ids) + dup
        items = [{"channelId": cid} for cid in ids]
        meta.update({"channelIds": len(ids), "条目内重复": dup, "文件原始条数": raw_count})

    existing = _read_list(client, list_id)
    to_add = [it for it in items if it["channelId"] not in existing["ids"]]
    skipped_existing = len(items) - len(to_add)
    skipped_limit = 0
    if limit is not None and len(to_add) > limit:
        skipped_limit = len(to_add) - limit
        to_add = to_add[:limit]
    if not to_add:
        raise CliError("没有可加的新条目：候选 %d 人，其中条目内重复 %d 人、已在名单 %d 人。"
                       "没有执行任何写。" % (raw_count, int(meta.get("条目内重复") or 0),
                                           skipped_existing),
                       hint="换一批频道编号，或先 `daniel lists items --list-id %d` 看名单里已有谁"
                            % list_id)

    fill = None
    if source == "channel-ids":
        to_add, fill = _enrich_by_detail(ctx, client, [it["channelId"] for it in to_add])
    coverage = {}
    for f in ADD_ITEM_FIELDS:
        filled = sum(1 for it in to_add if it.get(f) not in (None, ""))
        coverage[f] = "%d/%d" % (filled, len(to_add))
    not_filled = list((fill or {}).get("notFilled") or [])
    if source != "channel-ids":
        # 文件方式不额外回查（不替用户补数据）：缺的字段如实列出来，并说明怎么补
        for it in to_add:
            miss = _item_missing(it)
            if miss:
                not_filled.append({"channelId": it["channelId"], "缺字段": miss,
                                   "原因": "文件里没有提供（要补就加进文件后重跑）"})
    not_filled_count = (fill or {}).get("notFilledCount", len(not_filled))
    if source != "channel-ids":
        not_filled_count = len(not_filled)

    batches = [to_add[i:i + ADD_BATCH_LIMIT] for i in range(0, len(to_add), ADD_BATCH_LIMIT)]
    skipped_total = int(meta.get("条目内重复") or 0) + skipped_existing + skipped_limit
    notes = [
        "如果你希望连邮箱一起导入，需要在文件里提供 contactEmail（字段名与检索结果导出一致）；"
        "只给频道编号时邮箱通常取不到，会标「未取到」。",
        "想在名单里看到订阅数／国家／评分，请提供 subscriberCount／country／cqiScore；"
        "缺的字段会留空并标「未取到」，不会编造。",
        "已在名单里的人会自动跳过；同一批里重复的频道会自动去重，不会重复写入。",
        "单批上限 100 人：本次会自动拆成 %d 批，逐批写入并逐批记录结果；"
        "回读条数增加量与计划不一致会报错退出。" % len(batches),
    ]
    if any(it["channelId"] == "" for it in to_add):                       # 理论不可达，防御性
        raise CliError("有条目缺频道编号，已拒绝写入")
    plan = {
        "targetName": "名单 %d" % list_id,
        "listId": list_id,
        "来源": ("条目文件 %s" % meta.get("文件")) if source == "items-file"
                else "频道编号 %d 个" % len(items),
        "将加人数": len(to_add),
        "跳过人数": skipped_total,
        "跳过明细": {
            "条目内重复": int(meta.get("条目内重复") or 0),
            "已在名单": skipped_existing,
            "超出 --limit": skipped_limit,
        },
        "候选人数": raw_count,
        "名单现有条数": existing["total"],
        "预计批数": len(batches),
        "批次": {"每批上限": ADD_BATCH_LIMIT, "批数": len(batches),
                 "每批人数": [len(b) for b in batches]},
        "字段补齐情况": coverage,
        "未取到": {"人数": not_filled_count,
                   "明细": not_filled[:_ADD_DETAIL_MAX],
                   "是否截断": not_filled_count > _ADD_DETAIL_MAX},
        "样本": [{k: it.get(k) for k in ("channelId", "channelTitle", "subscriberCount")
                  if it.get(k) not in (None, "")} for it in to_add[:3]],
        "impact": ("名单 %d 现有 %d 人 → 本次计划新增 %d 人（跳过 %d 人：已在名单 %d／"
                   "条目内重复 %d／超出 --limit %d），分 %d 批写入（每批 ≤%d）；"
                   "写后回读名单条数必须从 %d 增到 %d。"
                   % (list_id, existing["total"], len(to_add), skipped_total, skipped_existing,
                      int(meta.get("条目内重复") or 0), skipped_limit, len(batches),
                      ADD_BATCH_LIMIT, existing["total"], existing["total"] + len(to_add))),
        "changes": {"lists.batchAddItems": {"listId": list_id, "batchCount": len(batches),
                                            "itemCount": len(to_add)}},
        "补充提示": notes,
        "审计": {"写入前": "本次干跑会留一条（是否执行=false，退出码 3）",
                 "写入后": "带 --confirm 真跑后再留一条（是否执行=true，含回读结果）",
                 "查看": "daniel account audit"},
        "readbackExpect": {"before": existing["total"], "delta": len(to_add),
                           "after": existing["total"] + len(to_add)},
        "sourceMeta": meta,
    }
    if fill:
        plan["补齐统计"] = fill
    ctx._add_items = {"listId": list_id, "items": to_add}
    return plan


def _run_add_items(ctx, client, plan):
    """真跑：逐批 `lists.batchAddItems` → 回读核对条数增加量 → 如实报差异。"""
    cached = getattr(ctx, "_add_items", None) or {}
    items = list(cached.get("items") or [])
    list_id = int(plan.get("listId") or cached.get("listId") or ctx.require("--list-id"))
    if not items:
        # 理论上 gated_write 一定先跑过 plan_fn；这里兜底（直接调用 run 的测试/脚本）
        _plan_add_items(ctx, client)
        items = list((getattr(ctx, "_add_items", None) or {}).get("items") or [])
    if not items:
        raise CliError("没有可写入的条目（计划轴没有产出条目），已拒绝写入")

    before = _read_list(client, list_id)
    sent = []
    batch_rows = []
    errors = []
    for i in range(0, len(items), ADD_BATCH_LIMIT):
        chunk = items[i:i + ADD_BATCH_LIMIT]
        batch_no = i // ADD_BATCH_LIMIT + 1
        ids = [it["channelId"] for it in chunk]
        sent.extend(ids)
        try:
            res = client.mutate("lists.batchAddItems",
                                {"listId": list_id, "items": chunk}) or {}
            added = int(res.get("addedCount") or 0)
            failed = res.get("failed") or []
            batch_rows.append({"批次": batch_no, "送入": len(chunk), "addedCount": added,
                               "failed": len(failed) if isinstance(failed, list) else 0})
            ctx.progress("第 %d/%d 批：送入 %d 人，服务端返回新增 %d 人"
                         % (batch_no, (len(items) + ADD_BATCH_LIMIT - 1) // ADD_BATCH_LIMIT,
                            len(chunk), added))
        except Exception as e:                                           # noqa: BLE001
            msg = "第 %d 批写入失败：%s" % (batch_no, scrub_text(e))
            errors.append(msg)
            batch_rows.append({"批次": batch_no, "送入": len(chunk), "error": scrub_text(e)})
            ctx.warn(msg + "（已停止后续批次，先回读核对已写入的部分）")
            break

    after = _read_list(client, list_id)
    delta = after["total"] - before["total"]
    expected = len(items)
    added_sum = sum(int(b.get("addedCount") or 0) for b in batch_rows)
    missing_after = [cid for cid in sent if cid not in after["ids"]]
    verified = (not errors) and delta == expected and added_sum == expected and not missing_after
    if verified:
        reason = ""
    elif errors:
        reason = errors[0]
    elif delta != expected:
        reason = ("回读条数增加 %d，与计划新增 %d 不一致（差 %+d）"
                  % (delta, expected, delta - expected))
    elif added_sum != expected:
        reason = ("服务端返回的新增合计是 %d，与计划新增 %d 不一致" % (added_sum, expected))
    else:
        reason = ("回读名单里找不到本次写入的 %d 个频道（条数看起来增加了，但成员对不上）"
                  % len(missing_after))
    return {
        "mutation": {
            "route": "lists.batchAddItems",
            "request": {"listId": list_id, "batchCount": len(batch_rows),
                        "itemCount": expected},
            "batches": batch_rows,
        },
        "readback": {
            "verified": verified,
            "reason": reason,
            "detail": {
                "before": {"count": before["total"]},
                "after": {"count": after["total"]},
                "delta": delta,
                "planned": expected,
                "addedCountSum": added_sum,
                "missingInReadbackCount": len(missing_after),
                "missingInReadback": missing_after[:_ADD_DETAIL_MAX],
                "batchErrors": errors,
            },
            "how": "重新调用 lists.getItems 核对：条数增加量必须等于计划新增数，"
                   "且本次送入的每个频道编号都能在回读里找到",
        },
        "rolledBack": False,
        "rollbackNote": "新增条目可在 Daniel 名单页手动移除；本命令不提供自动回滚"
                        "（没有把新增条目删掉的 CLI 命令）",
        "detail": {"名单编号": list_id, "计划新增": expected, "实际新增": delta,
                   "跳过": int((plan.get("跳过人数") or 0)),
                   "批数": len(batch_rows)},
    }


HANDLERS = {
    "by-brand": cmd_by_brand,
    "items": cmd_items,
    "saved-channel-ids": cmd_saved_channel_ids,
    "share-status": cmd_share_status,
    "auto-priority-status": cmd_auto_priority_status,
}

WRITE_HANDLERS = {
    "add-items": gated_write(BOARD, "add-items", "往名单里批量加人", stage=STAGE_LIVE,
                             plan_fn=_plan_add_items, run_fn=_run_add_items,
                             danger="会往名单里写入频道条目；已在名单里的人自动跳过，"
                                    "超过 100 人自动拆批，回读不一致会报错退出"),
    "create": gated_write(BOARD, "create", "在品牌下新建名单", stage=STAGE_LIVE,
                          plan_fn=_plan_create, run_fn=_run_create),
    "rename": gated_write(BOARD, "rename", "重命名名单", stage=STAGE_LIVE,
                          plan_fn=_plan_rename, run_fn=_run_rename),
    "delete": gated_write(BOARD, "delete", "删除名单（不可逆）", stage=STAGE_LIVE,
                          plan_fn=_plan_delete, run_fn=_run_delete,
                          delete="名单名",
                          danger="不可逆：名单与其条目一并删除"),
}
