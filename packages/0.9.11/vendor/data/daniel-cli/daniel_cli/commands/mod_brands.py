# -*- coding: utf-8 -*-
"""brands 模块：品牌档案（读链走共享客户端 `daniel_client`；写链走统一门禁链）。

写链口径与 lists 相同（权限 → 确认 → 删除凭据 → 执行 → 回读 → 审计），另有两条品牌专属守卫：
  · **重名与空名**：服务端不拦（`.kol-tools/daniel_brands.py` 实测），由本命令在客户端拦；
  · **配额**：非管理角色的工作区 `maxBrands` 用满即拒（管理角色不受配额限制，与前端一致）；
  · **删除默认只允许 `_tmp-` 前缀的测试品牌**：删真实品牌必须显式 `--allow-non-tmp`
    （沿用能力脚本的既有纪律），且仍要 `--confirm` ＋ `--delete-token <品牌名>` 两道确认。

写路由（实证出处：`.kol-tools/daniel_brands.py` 文件头表格）：
  `brands.create`／`brands.update`（局部合并，只传要改的键）／`brands.delete`，均为 POST。
"""
import re

from .. import permissions
from ..exits import EXIT_INTERNAL, EXIT_OK
from ..runtime import CliError, new_client
from ._common import STAGE_LIVE, gated_write

BOARD = "brands"

#: 服务端不校验的守卫，由本命令在客户端做（对齐既有能力脚本的纪律）
TMP_PREFIX = "_tmp-"


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip()).lower()


def _client(ctx):
    return new_client(verbose=ctx.verbose)


def _rows(client, workspace_id):
    return [r for r in (client.query("brands.list", {"workspaceId": int(workspace_id)}) or [])
            if isinstance(r, dict)]


def _target_workspace(ctx, client, auth=None):
    """写进哪个工作区：`--workspace` 优先，否则当前工作区（显式取值，不靠"活跃工作区"隐式行为）。"""
    ws = ctx.get("workspace")
    if ws is not None:
        return int(ws)
    snap, _why = (auth, None) if isinstance(auth, dict) else permissions.current_auth()
    wid = (snap or {}).get("activeWorkspaceId") or ((snap or {}).get("workspace") or {}).get("id")
    if not wid:
        raise CliError("拿不到当前工作区编号，且没有给 --workspace",
                       hint="显式指定 `--workspace <编号>`（用 daniel account workspaces 看编号）")
    return int(wid)


def _quota_check(ctx, workspace_id, count, auth):
    """非管理角色撞上工作区品牌配额 → 拒绝（管理角色豁免，与前端配额条一致）。"""
    ws = (auth or {}).get("workspace") or {}
    limit = ws.get("maxBrands")
    if limit is None:
        return None
    if int(limit) < 0:
        return None
    if (auth or {}).get("systemRole") in permissions.ADMIN_ROLES:
        return None
    if count >= int(limit):
        raise CliError("工作区「%s」的品牌配额已满：上限 %d，现有 %d。本次不新建品牌。"
                       % (ws.get("name") or ws.get("id"), int(limit), count),
                       hint="换一个还有余量的工作区（--workspace），或由管理角色处理配额")
    return {"limit": int(limit), "used": count}


# ─────────────────────────── 读 ───────────────────────────
def cmd_list(ctx):
    """列品牌：走跨工作区索引（**不依赖当前所在工作区**）。"""
    d = _client(ctx)
    ctx.progress("正在读取品牌索引（跨全部工作区）")
    try:
        idx = d.brand_index(refresh=bool(ctx.get("refresh")))
    except OSError as e:
        raise CliError("品牌索引无法写入落点：%s" % e, code=EXIT_INTERNAL,
                       hint="用 DANIEL_HOME 指定可写的数据落点，或先执行 daniel account paths 查看落点")
    rows = list(idx.get("brands") or [])
    ws = ctx.get("workspace")
    if ws is not None:
        rows = [r for r in rows if r.get("workspaceId") == int(ws)]
    limit = ctx.get("limit") or 200
    rows = sorted(rows, key=lambda r: str(r.get("name") or "").lower())[:int(limit)]
    ctx.emit(data={"count": len(rows), "workspaceFilter": ws,
                   "indexBuiltAt": idx.get("builtAt"),
                   "indexWorkspaceCount": idx.get("workspaceCount"),
                   "brands": rows},
             route="auth.listMyWorkspaces + brands.list(workspaceId)")
    return EXIT_OK


def cmd_show(ctx):
    d = _client(ctx)
    ref = ctx.require("--brand")
    ctx.progress("正在解析品牌并读取档案")
    b = d.resolve_brand_ref(ref)
    detail = d.get_brand(b["id"])
    data = detail if isinstance(detail, dict) and detail.get("id") else b
    ctx.emit(data=data, route="brands.getById")
    return EXIT_OK


def cmd_competitors(ctx):
    d = _client(ctx)
    b = d.resolve_brand_ref(ctx.require("--brand"))
    detail = d.get_brand(b["id"]) or {}
    comps = detail.get("competitors") or []
    ctx.emit(data={"brand": detail.get("name") or b.get("name"), "brandId": b.get("id"),
                   "count": len(comps), "competitors": comps})
    return EXIT_OK


# ─────────────────────────── 写：新建品牌 ───────────────────────────
def _plan_create(ctx, client):
    name = str(ctx.require("--name")).strip()
    if not name:
        raise CliError("品牌名不能为空", hint="给一个能一眼认出来的品牌名")
    auth, _why = permissions.current_auth()
    wid = _target_workspace(ctx, client, auth)
    rows = _rows(client, wid)
    dup = [r for r in rows if _norm(r.get("name")) == _norm(name)]
    if dup:
        raise CliError("工作区 %d 里已经有同名品牌「%s」（编号 %s）：拒绝新建重名品牌"
                       % (wid, name, dup[0].get("id")),
                       hint="同名品牌存在时，用 `daniel brands update --brand %s` 改资料"
                            % dup[0].get("id"))
    quota = _quota_check(ctx, wid, len(rows), auth)
    payload = {"name": name}
    for opt, key, parse in _FIELD_SPECS:
        if opt == "--name":
            continue
        raw = ctx.get(opt)
        if raw is None:
            continue
        val = parse(raw) if parse else raw
        if key == "sampleCost":
            try:
                val = int(val)
            except (TypeError, ValueError):
                raise CliError("--sample-cost 需要一个整数", hint="例如 --sample-cost 599")
        payload[key] = val
    payload["workspaceId"] = wid
    return {
        "targetName": name, "brand": None, "workspaceId": wid,
        "impact": "在工作区 %d 新增 1 个品牌；该工作区现有品牌 %d 个%s"
                  % (wid, len(rows), ("，配额 %d" % quota["limit"]) if quota else "（无配额上限）"),
        "changes": {"brands.create": payload},
        "existingBrandCount": len(rows), "quota": quota,
    }


def _run_create(ctx, client, plan):
    payload = dict(plan["changes"]["brands.create"])
    wid = payload["workspaceId"]
    before = _rows(client, wid)
    client.mutate("brands.create", payload)
    after = _rows(client, wid)
    hit = [r for r in after if _norm(r.get("name")) == _norm(payload["name"])]
    created = hit[-1] if hit else None
    verified = bool(created) and len(after) == len(before) + 1
    reason = "" if verified else "回读未看到新品牌（品牌数 %d → %d）" % (len(before), len(after))
    return {
        "mutation": {"route": "brands.create", "request": payload},
        "readback": {"verified": verified, "reason": reason,
                     "detail": {"before": {"brandCount": len(before)},
                                "after": {"brandCount": len(after),
                                          "newBrandId": (created or {}).get("id"),
                                          "newBrandName": (created or {}).get("name")}},
                     "how": "重新调用 brands.list(workspaceId) 核对：品牌数 +1 且名字逐字命中"},
        "rolledBack": False,
        "rollbackNote": "如需清理，用 `daniel brands delete --brand %s --confirm "
                        "--delete-token \"%s\"`%s"
                        % ((created or {}).get("id"), payload["name"],
                           "" if str(payload["name"]).startswith(TMP_PREFIX)
                           else "（非 _tmp- 前缀的品牌还需 --allow-non-tmp）"),
        "detail": {"新品牌编号": (created or {}).get("id")},
    }


# ─────────────────────────── 写：改资料 ───────────────────────────
#: 可改字段（与 schema 的参数一一对应；服务端是局部合并，只传要改的键）
def _csv(value):
    """`a,b,c` → ['a','b','c']（去空、去重保序）；空串 → []（显式清空的语义）。"""
    if value is None:
        return None
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    items = [x.strip() for x in str(value).split(",")]
    out, seen = [], set()
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _competitors(value):
    """竞品写法：`名称:关键词1|关键词2;名称2:关键词` → [{name, categoryKeywords}]。

    也接受 JSON 数组（[{"name":..., "categoryKeywords":[...]}]），便于脚本与 agent 直接给结构化值。
    """
    if value is None:
        return None
    if isinstance(value, list):
        return value
    text = str(value).strip()
    if text.startswith("["):
        import json as _json
        data = _json.loads(text)
        if not isinstance(data, list):
            raise CliError("--competitors 的 JSON 必须是数组", hint="形如 [{\"name\":\"X\",\"categoryKeywords\":[\"k1\"]}]")
        return data
    out = []
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, kws = chunk.partition(":")
        name = name.strip()
        if not name:
            continue
        kws = (kws or "").replace("|", ",")
        out.append({"name": name, "categoryKeywords": _csv(kws) or []})
    return out


#: 写操作可改／可建的字段：(命令行开关, payload 键, 解析器)
_FIELD_SPECS = (
    ("--name", "name", None),
    ("--description", "description", None),
    ("--category", "category", None),
    ("--industry-keywords", "industryKeywords", _csv),
    ("--target-countries", "targetCountries", _csv),
    ("--sample-cost", "sampleCost", None),
    ("--competitors", "competitors", _competitors),
)
_UPDATABLE = tuple((opt, key) for opt, key, _p in _FIELD_SPECS)


def _plan_update(ctx, client):
    b = client.resolve_brand_ref(ctx.require("--brand"))
    detail = client.get_brand(b["id"]) or {}
    changes = {}
    for opt, key, parse in _FIELD_SPECS:
        raw = ctx.get(opt)
        if raw is None:
            continue
        val = parse(raw) if parse else raw
        if key == "sampleCost":
            try:
                val = int(val)
            except (TypeError, ValueError):
                raise CliError("--sample-cost 需要一个整数", hint="例如 --sample-cost 599")
        changes[key] = val
    if not changes:
        raise CliError("没有给出要改的内容：至少给一个改动的字段",
                       hint="可用字段：%s" % "／".join(o for o, _k in _UPDATABLE))
    same = {k: v for k, v in changes.items() if detail.get(k) == v}
    if len(same) == len(changes):
        raise CliError("给出的新值与现值完全一致：没有必要写",
                       hint="改一个真正不同的值，或不做这次写")
    lines = []
    for k, v in changes.items():
        cur = detail.get(k)
        lines.append("%s：「%s」→「%s」" % (k, str(cur)[:60] if cur is not None else "（空）",
                                          str(v)[:60]))
    return {
        "targetName": detail.get("name") or b.get("name"), "brand": "%s(编号 %s)" % (
            detail.get("name") or b.get("name"), b.get("id")),
        "workspaceId": detail.get("workspaceId") or b.get("workspaceId"),
        "impact": "修改品牌「%s」（编号 %s）的 %d 个字段：%s；其余字段不动（服务端按局部合并处理）"
                  % (detail.get("name") or b.get("name"), b.get("id"), len(changes),
                     "；".join(lines)),
        "changes": {"brands.update": dict({"id": int(b["id"])}, **changes)},
        "before": {k: detail.get(k) for k in changes},
        "after": changes,
        "rollbackHint": "如需还原，把上面的原值再写一遍（品牌资料改动是可逆的）",
    }


def _run_update(ctx, client, plan):
    request = dict(plan["changes"]["brands.update"])
    bid = request["id"]
    before = client.get_brand(bid) or {}
    client.mutate("brands.update", request)
    after = client.get_brand(bid) or {}
    want = {k: v for k, v in request.items() if k != "id"}
    mismatched = [k for k, v in want.items() if after.get(k) != v]
    # 服务端自己会动的字段（例如 updatedAt）不能算"未请求的字段却变了"，否则每次写都会误判回读失败
    volatile = {"updatedAt"}
    unchanged = [k for k in before
                 if k not in want and k not in volatile and after.get(k) != before.get(k)]
    verified = bool(after.get("id")) and not mismatched and not unchanged
    if mismatched:
        reason = "回读与写入值不一致的字段：%s" % "／".join(
            "%s(写入 %r，回读 %r)" % (k, want[k], after.get(k)) for k in mismatched)
    elif unchanged:
        reason = "未请求修改的字段却变了：%s" % "／".join(unchanged)
    elif not after.get("id"):
        reason = "回读时该品牌已取不到（brands.getById 返回空）"
    else:
        reason = ""
    return {
        "mutation": {"route": "brands.update", "request": request},
        "readback": {"verified": verified, "reason": reason,
                     "detail": {"before": {k: before.get(k) for k in want},
                                "after": {k: after.get(k) for k in want},
                                "untouchedFieldsStable": not unchanged},
                     "how": "重新调用 brands.getById 核对：写入字段逐字相等，且未请求的字段没有变化"},
        "rolledBack": False,
        "rollbackNote": "本次改动未回滚；如需还原，用原值再跑一次 brands update（零净变化测试请跑两遍）",
        "detail": {"修改字段": list(want), "品牌编号": bid},
    }


# ─────────────────────────── 写：参考某个品牌克隆一个新品牌 ───────────────────────────
CLONE_FIELDS = ("description", "category", "industryKeywords", "targetCountries",
                "sampleCost", "competitors", "youtubeChannelId", "youtubeChannelTitle")


def _plan_clone(ctx, client):
    """把「参考品牌」的业务字段整体复制到一个新品牌（最常用：参考 Halliday 建 Lymow）。"""
    src_ref = ctx.require("--from")
    name = str(ctx.require("--name")).strip()
    if not name:
        raise CliError("新品牌名不能为空", hint="例如 --name Lymow")
    src = client.resolve_brand_ref(src_ref)
    detail = client.get_brand(src["id"]) or {}
    if not detail.get("id"):
        raise CliError("参考品牌取不到：%s" % src_ref, hint="用 `daniel brands list` 确认品牌名或编号")
    auth, _why = permissions.current_auth()
    wid = _target_workspace(ctx, client, auth)
    rows = _rows(client, wid)
    dup = [r for r in rows if _norm(r.get("name")) == _norm(name)]
    if dup:
        raise CliError("工作区 %d 里已经有同名品牌「%s」（编号 %s）：拒绝新建重名品牌"
                       % (wid, name, dup[0].get("id")),
                       hint="改资料请用 `daniel brands update --brand %s`" % dup[0].get("id"))
    quota = _quota_check(ctx, wid, len(rows), auth)
    payload = {"name": name, "workspaceId": wid}
    copied = []
    for key in CLONE_FIELDS:
        val = detail.get(key)
        if val in (None, "", [], {}):
            continue
        payload[key] = val
        copied.append(key)
    if not copied:
        raise CliError("参考品牌 %s 没有可复制的业务字段" % src_ref,
                       hint="先给参考品牌补齐案材，或直接用 `brands create` 逐字段填")
    return {
        "targetName": name, "brand": None, "workspaceId": wid,
        "impact": "在工作区 %d 新建品牌「%s」，并复制参考品牌「%s」（编号 %s）的 %d 个业务字段；"
                  "该工作区现有 %d 个品牌%s"
                  % (wid, name, detail.get("name"), src["id"], len(copied), len(rows),
                     ("，配额 %d" % quota["limit"]) if quota else "（无配额上限）"),
        "changes": {"brands.create": payload},
        "copiedFields": copied,
        "existingBrandCount": len(rows), "quota": quota,
    }


def _run_clone(ctx, client, plan):
    payload = dict(plan["changes"]["brands.create"])
    wid = payload["workspaceId"]
    client.mutate("brands.create", payload)
    after = _rows(client, wid)
    hit = [r for r in after if _norm(r.get("name")) == _norm(payload["name"])]
    created = hit[-1] if hit else None
    if not created:
        raise CliError("新建品牌后回读不到（brands.list 里没有「%s」）" % payload["name"],
                       hint="到系统页面确认该工作区是否已建出；不要重复创建")
    detail = client.get_brand(created["id"]) or {}
    missing = [k for k in plan.get("copiedFields", []) if detail.get(k) in (None, "", [], {})]
    return {
        "mutation": {"route": "brands.create", "request": payload},
        "created": {"id": created["id"], "name": created["name"], "workspaceId": created.get("workspaceId")},
        "readback": {"verified": not missing,
                     "reason": ("复制后回读为空的字段：%s" % "／".join(missing)) if missing else "",
                     "how": "brands.list 定位新品牌 ＋ brands.getById 逐字段核对复制结果"},
        "detail": {"新品牌编号": created["id"], "复制字段数": len(plan.get("copiedFields", []))},
    }


# ─────────────────────────── 写：删除品牌（删除类） ───────────────────────────
def _plan_delete(ctx, client):
    b = client.resolve_brand_ref(ctx.require("--brand"))
    detail = client.get_brand(b["id"]) or {}
    name = detail.get("name") or b.get("name")
    wid = detail.get("workspaceId") or b.get("workspaceId")
    rows = _rows(client, wid) if wid else []
    if not str(name or "").startswith(TMP_PREFIX) and not ctx.get("allow-non-tmp"):
        raise CliError("品牌「%s」不是测试品牌（不以 %s 开头）：默认拒绝删除真实品牌"
                       % (name, TMP_PREFIX),
                       hint="确认要删真实品牌时显式加 --allow-non-tmp（仍需 --confirm 与 "
                            "--delete-token）")
    return {"targetName": name, "brand": "%s(编号 %s)" % (name, b.get("id")),
            "workspaceId": wid,
            "impact": "删除品牌「%s」（编号 %s，工作区 %s）：品牌档案与登记竞品一并消失，不可逆%s"
                      % (name, b.get("id"), wid,
                         "" if str(name or "").startswith(TMP_PREFIX)
                         else "；⚠️ 该品牌不是 _tmp- 测试品牌"),
            "changes": {"brands.delete": {"id": int(b["id"])}},
            "deleteTokenExample": name, "existingBrandCount": len(rows)}


#: 服务端"对象已不存在"的信号（`daniel_client.query` 把最后一次错误的原文挂在 RuntimeError 里）
_NOT_FOUND_MARKERS = ("http 404", "not_found", "not found", "notfound")


def _probe_gone(client, brand_id):
    """回读探针：该编号**已经不存在**了吗？返回 `(是否不存在, 证据文本)`。

    🔴 为什么需要这个探针（TICKET-196 实测发现的缺陷）：删除后按 id 直取**必然 404** ——
    那是**预期结果**，不是错误。原来这里直接 `client.get_brand(bid)`，404 会一路抛成 RuntimeError
    ⇒ `brands delete` 以"执行函数抛异常"收场：**写其实成功了，命令却报失败、且没有任何回读结论**
    （无审计时更糟：连"删过"这件事都不留痕。本票的审计修复把这一条抓了出来）。
    判据只看服务端的"不存在"信号（404／NOT_FOUND）；**其它异常照旧抛出，不吞**。
    """
    try:
        detail = client.get_brand(brand_id)
    except Exception as e:                                            # noqa: BLE001（见上方判据）
        text = "%s %s" % (type(e).__name__, e)
        low = text.lower()
        if any(m in low for m in _NOT_FOUND_MARKERS):
            return True, text[:200]
        raise
    present = bool(isinstance(detail, dict) and detail.get("id"))
    return not present, ("brands.getById 仍返回该编号" if present else "brands.getById 返回空")


def _run_delete(ctx, client, plan):
    bid = plan["changes"]["brands.delete"]["id"]
    detail = client.get_brand(bid) or {}
    wid = detail.get("workspaceId")
    before = _rows(client, wid) if wid else []
    client.mutate("brands.delete", {"id": bid})
    gone_detail, probe_note = _probe_gone(client, bid)
    after = _rows(client, wid) if wid else []
    gone_list = not [r for r in after if str(r.get("id")) == str(bid)]
    verified = gone_detail and gone_list
    reason = "" if verified else ("回读仍能取到该品牌（byId 已不存在=%s，list 命中=%s）：删除没有生效"
                                  % (gone_detail, not gone_list))
    return {
        "mutation": {"route": "brands.delete", "request": {"id": bid}},
        "readback": {"verified": verified, "reason": reason,
                     "detail": {"before": {"brandPresentInList": True, "brandCount": len(before)},
                                "after": {"byIdGone": bool(gone_detail),
                                          "byIdProbe": probe_note,
                                          "brandPresentInList": not gone_list,
                                          "brandCount": len(after)}},
                     "how": "双重回读：brands.getById 报「不存在」（404／NOT_FOUND 视为预期）"
                            " 且 brands.list 里也没有该编号"},
        "rolledBack": None,
        "rollbackNote": "删除不可逆，没有回滚动作；本次删除对象由调用方指定并二次确认",
        "detail": {"已删除品牌": plan.get("targetName"), "编号": bid, "byId 探针": probe_note},
    }


HANDLERS = {
    "list": cmd_list,
    "show": cmd_show,
    "competitors": cmd_competitors,
}

WRITE_HANDLERS = {
    "create": gated_write(BOARD, "create", "在指定工作区新建品牌", stage=STAGE_LIVE,
                          plan_fn=_plan_create, run_fn=_run_create),
    "update": gated_write(BOARD, "update", "修改品牌资料", stage=STAGE_LIVE,
                          plan_fn=_plan_update, run_fn=_run_update),
    "clone": gated_write(BOARD, "clone", "参考某个品牌克隆一个新品牌（复制其业务字段）",
                         stage=STAGE_LIVE, plan_fn=_plan_clone, run_fn=_run_clone),
    "delete": gated_write(BOARD, "delete", "删除品牌（不可逆）", stage=STAGE_LIVE,
                          plan_fn=_plan_delete, run_fn=_run_delete,
                          delete="品牌名",
                          danger="不可逆：品牌档案与登记竞品一并删除"),
}
