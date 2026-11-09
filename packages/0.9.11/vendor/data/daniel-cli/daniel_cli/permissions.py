# -*- coding: utf-8 -*-
"""账号能力矩阵：写链由**账号权限**决定，不由审批决定（TICKET-152 · P0-5）。

用户口径（2026-10-14 裁决）：Daniel 账号登录后，**它能展示的模块对应的写自动开放**；
没有权限的模块既不能用也不能写。写链对应的是**账号的使用权限**，本工程**不引入任何审批流**
（没有审批队列、没有管理员放行）。

三条判据轴，全部取自 Daniel 返回的账号事实，本地不做任何假设：

| 轴 | 取值来源 | 不放行的取值 |
|---|---|---|
| ① 系统角色 | `auth.me.systemRole`、`auth.me.role` | 不满足模块要求的角色集合 |
| ② 账号状态 | `auth.me.userStatus` | `pending`、`suspended` |
| ③ 工作区权益与配额 | `auth.me.workspace`（`planTier`／`maxBrands`／`maxSearchesPerMonth`）＋ `workspaces.activeFeatures` | 权益未开启；写操作撞上配额上限（管理角色豁免） |

模块级要求（`MODULE_RULES`）的出处是**前端实际门禁**（仓库内构建产物 `.kol-tools/_daniel_bundle/`，
逐条标注文件名与行号），不是推测：只有"页面上真能展示的模块"，CLI 才开放它的写。

关于"降级角色演练注入"：本机账号是 `super_admin`，按口径写链全部开放，因此**没有权限的路径**
平时跑不出来。`DANIEL_CLI_AUTH_FIXTURE=<文件>` 可以把一份账号快照注入进来（形如
`{"systemRole": "viewer", "userStatus": "active", "workspace": {...}}`），
让 CLI／契约引擎在**不联网**的情况下按降级角色跑一遍，用于自检与验收。
注入只改判据输入，不改任何账号事实。
"""
import json
import os
import time

from .exits import EXIT_USAGE
from .runtime import CliError

# ─────────────────────────── 常量 ───────────────────────────
#: 降级角色演练用的注入变量（指向一份 JSON 快照；只覆盖判据输入，不联网、不写任何账号）
FIXTURE_ENV = "DANIEL_CLI_AUTH_FIXTURE"

#: 前端 `RequireAuth`／`AdminRouteGuard` 认的管理角色
ADMIN_ROLES = ("super_admin", "admin")
#: 前端 `ComingSoonGuard` 额外放行的角色
PRO_ROLES = ("super_admin", "admin", "pro")
#: 前端一律不放行的账号状态（两处守卫都是同一条判据）
BLOCKED_STATUS = ("pending", "suspended")

READ = "读"
WRITE = "写"

#: 读/写两列在输出里的字段名（对外口径，help 与 JSON 同源）
K_ALLOWED = "是否允许"
K_REASON = "理由"

#: 快照缓存时效（秒）：过了就重新探测一次，避免"改了角色还用旧结论"
SNAPSHOT_TTL = 600


# ─────────────────────────── 模块要求表 ───────────────────────────
def _rule(title, evidence, roles=None, features=(), quota=None, status_required=True, note="",
          account_fact_required=True):
    """一条模块级判据。

    `account_fact_required=False`（目前只有「账号与盘点」）：该模块的写**不依赖账号事实快照**。
    唯一的例外就是它自己 —— 把凭据写进本机钥匙串、登录并刷新会话，这两件事本身就是"拿到账号
    事实"的前提：在一台**全新的机器**上还没有会话，所以那次探测必然失败；若在这里按"确认不了
    权限就不动手"处理，新用户会被自己的门禁挡在门外（TICKET-170 的原始缺陷）。
    判据仍然只有一份：模块的角色／状态／权益三轴照常判，只是"快照取不到"不再等于"不许做"。
    """
    return {"title": title, "roles": tuple(roles) if roles else None, "features": tuple(features),
            "quota": quota, "statusRequired": bool(status_required),
            "accountFactRequired": bool(account_fact_required),
            "evidence": evidence, "note": note}


#: 模块 → 判据。`roles=None` 表示"任何登录角色都能看到该模块"（前端对该路由没有角色守卫）。
MODULE_RULES = {
    "brands": _rule(
        "品牌档案",
        "前端 `/brands` 路由无角色守卫；侧边栏底部「Brands」对全部登录用户展示"
        "（DashboardLayout.tsx 的底部导航数组不过滤角色）",
        quota="brands",
        note="写操作受工作区品牌配额约束：前端在管理角色下隐藏用量条，故管理角色不受配额拦截"),
    "lists": _rule(
        "红人名单",
        "前端 `/lists` 路由无角色守卫；侧边栏「Saved Lists」对全部登录用户展示"
        "（DashboardLayout.tsx 的保留名单 C 里始终包含 Saved Lists）"),
    "search": _rule(
        "红人检索",
        "前端 `/discovery` 路由无角色守卫；侧边栏「AI Creator Search」对全部登录用户展示"
        "（仅其中 YouTube Official 子页要求管理角色，见 Discovery 第 40 行的状态＋角色双轴判据）",
        quota="searches",
        note="提交检索会消耗工作区每月检索额度（maxSearchesPerMonth）"),
    "mentions": _rule(
        "品牌提及",
        "前端 BrandMentions 第 39 行：`userStatus ∉ {pending, suspended}` 且"
        "（`role === \"admin\"` 或 `systemRole ∈ {super_admin, admin, pro}`）",
        roles=PRO_ROLES),
    "intel": _rule(
        "内容情报",
        "前端 `/intelligence/action-center` 走 `RequireAuth` 双轴守卫："
        "`systemRole ∈ {super_admin, admin}` 且 `userStatus ∉ {pending, suspended}`"
        "（App.tsx 第 125 行的守卫组件，index 构建产物 RequireAuth 实现）",
        roles=ADMIN_ROLES),
    "sov": _rule(
        "声量份额",
        "前端 ExposureSov 第 1 行：`systemRole ∈ {super_admin, admin}`；"
        "侧边栏「Social Intelligence」项在非管理角色下还要求工作区开启 social_intelligence 权益",
        roles=ADMIN_ROLES, features=("social_intelligence",)),
    "ct": _rule(
        "合作追踪",
        "前端 `/campaigns`、`/campaigns/:id`、`/inbox`、`/email-templates` 走 `AdminRouteGuard` ＋ "
        "`ComingSoonGuard`（App.tsx 第 93/97/111/141 行）；"
        "侧边栏「Outreach」项在非管理角色下还要求工作区开启 outreach 权益",
        roles=PRO_ROLES, features=("outreach",)),
    "authenticity": _rule(
        "真实性核验",
        "前端 `/authenticity` 路由无角色守卫；侧边栏「Authenticity」对全部登录用户展示"),
    "route": _rule(
        "数据通路体检",
        "运维级诊断模块（前端没有对应页面）：按账号的管理角色判定，"
        "与 `RequireAuth` 同一条判据（`systemRole ∈ {super_admin, admin}`）",
        roles=ADMIN_ROLES),
    "takeover": _rule(
        "接管验收",
        "运维级诊断模块（前端没有对应页面）：按账号的管理角色判定，判据同 `RequireAuth`",
        roles=ADMIN_ROLES),
    "parity": _rule(
        "口径一致性",
        "运维级诊断模块（前端没有对应页面）：按账号的管理角色判定，判据同 `RequireAuth`",
        roles=ADMIN_ROLES),
    "account": _rule(
        "账号与盘点",
        "前端 `/settings` 路由无角色守卫；账号信息对本人始终可见",
        status_required=False,
        account_fact_required=False,
        note="查自己的账号与数据落点是排障前提，因此不因账号状态被拦；"
             "把凭据写进本机钥匙串、登录刷新会话同样不受账号状态拦截，"
             "且**不依赖账号权限快照** —— 新机器上还没有会话时，这两件事正是拿到账号事实的前提"),
}


def rule_keys():
    """有判据的全部模块（12 个业务模块）。"""
    return tuple(MODULE_RULES)


def rule_for(module_key):
    return MODULE_RULES.get(module_key)


# ─────────────────────────── 快照读取 ───────────────────────────
def _mask(email):
    s = str(email or "")
    if "@" not in s:
        return (s[:2] + "***") if s else ""
    name, domain = s.split("@", 1)
    keep = name[:2] if len(name) > 2 else name[:1]
    return "%s***@%s" % (keep, domain)


def _snapshot_from_me(me, workspaces=None, features=None):
    """把 `auth.me` 归一成**白名单快照**。

    只取判据用得上的字段：`auth.me` 里还有 `passwordHash`／`openId`／`googleId` 这类字段，
    它们既不是判据也可能算凭据 —— 一律**不进快照**（结构上不可能被打印出来）。
    """
    me = me if isinstance(me, dict) else {}
    ws = me.get("workspace") if isinstance(me.get("workspace"), dict) else {}
    rows = []
    for w in (workspaces or []):
        if not isinstance(w, dict) or w.get("id") is None:
            continue
        rows.append({"id": w.get("id"), "name": w.get("name"), "planTier": w.get("planTier"),
                     "memberRole": w.get("memberRole")})
    return {
        "emailMasked": _mask(me.get("email")),
        "systemRole": me.get("systemRole"),
        "role": me.get("role"),
        "userStatus": me.get("userStatus"),
        "activeWorkspaceId": me.get("activeWorkspaceId") or me.get("workspaceId"),
        "workspace": {"id": ws.get("id"), "name": ws.get("name"),
                      "planTier": ws.get("planTier"), "status": ws.get("status"),
                      "maxBrands": ws.get("maxBrands"),
                      "maxSearchesPerMonth": ws.get("maxSearchesPerMonth"),
                      "maxEmailsPerMonth": ws.get("maxEmailsPerMonth")},
        "workspaces": rows,
        "enabledFeatures": list(features or []),
    }


def _merge(base, override):
    out = dict(base or {})
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_fixture(path=None):
    """读降级角色快照（`DANIEL_CLI_AUTH_FIXTURE`）；没设就返回 None。

    注入的快照可以只写要改的字段（与一份基线深合并），例如只写
    `{"systemRole": "viewer"}` 就能把角色降到普通用户。
    """
    p = path or os.environ.get(FIXTURE_ENV)
    if not p:
        return None
    p = os.path.abspath(os.path.expanduser(p))
    if not os.path.isfile(p):
        raise CliError("降级角色快照文件不存在：%s" % p, code=EXIT_USAGE,
                       hint="%s 要指向一份 JSON 快照（例：{\"systemRole\": \"viewer\"}）"
                            % FIXTURE_ENV)
    try:
        with open(p, encoding="utf-8") as fh:
            raw = json.load(fh)
    except ValueError as e:
        raise CliError("降级角色快照不是合法 JSON：%s（%s）" % (p, e), code=EXIT_USAGE)
    except OSError as e:
        raise CliError("降级角色快照读不出来：%s（%s）" % (p, e), code=EXIT_USAGE)
    if not isinstance(raw, dict):
        raise CliError("降级角色快照的顶层必须是对象：%s" % p, code=EXIT_USAGE)
    fixture = _merge(_snapshot_from_me({}), raw)
    fixture["source"] = "fixture"
    fixture["fixturePath"] = p
    return fixture


def _cache_path():
    from . import runtime
    dpaths = runtime.load_capability("daniel_paths")
    return os.path.join(dpaths.paths()["cache_dir"], "auth-snapshot.json")


def read_cache(ttl=SNAPSHOT_TTL):
    """读本地快照缓存；过期或缺失返回 None。缓存里**没有**凭据类字段。"""
    path = _cache_path()
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or not doc.get("probedAtUnix"):
        return None
    if ttl is not None and (time.time() - float(doc["probedAtUnix"])) > ttl:
        return None
    return doc


def write_cache(snapshot):
    path = _cache_path()
    doc = dict(snapshot or {})
    doc["probedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    doc["probedAtUnix"] = time.time()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass                                    # 缓存不是必需品：写不进去也不许影响判据
    return doc


def probe_live(client=None):
    """真探测：`auth.me` ＋ `auth.listMyWorkspaces` ＋ `workspaces.activeFeatures`。"""
    from .runtime import new_client
    d = client or new_client()
    me = d.query("auth.me", {}) or {}
    try:
        workspaces = d.query("auth.listMyWorkspaces", {}) or []
    except Exception:                                                    # noqa: BLE001
        workspaces = []
    features = []
    try:
        feat = d.query("workspaces.activeFeatures", {}) or {}
        if isinstance(feat, dict):
            features = list(feat.get("enabledFeatures") or [])
    except Exception:                                                    # noqa: BLE001
        features = []
    snap = _snapshot_from_me(me, workspaces, features)
    snap["source"] = "live"
    return snap


def probe_usage(auth, client=None):
    """配额轴的用量（只读）。取不到就给 None，并在理由里写明"未取到用量"。"""
    from .runtime import new_client
    quota = auth.get("workspace") or {}
    ws_id = auth.get("activeWorkspaceId") or quota.get("id")
    out = {"brands": {"limit": quota.get("maxBrands"), "used": None,
                      "workspaceId": ws_id, "note": ""},
           "searches": {"limit": quota.get("maxSearchesPerMonth"), "used": None,
                        "workspaceId": ws_id, "note": "每月检索额度用量的接口在管理角色下返回空"}}
    if not ws_id:
        out["brands"]["note"] = "拿不到当前工作区编号"
        return out
    try:
        d = client or new_client()
        rows = d.query("brands.list", {"workspaceId": int(ws_id)}) or []
        out["brands"]["used"] = len(rows)
    except Exception as e:                                                # noqa: BLE001
        out["brands"]["note"] = "品牌数取不到：%s" % str(e)[:120]
    return out


def current_auth(client=None, force=False, ttl=SNAPSHOT_TTL, use_cache=True):
    """当前账号快照：注入快照 → 本地缓存 → 真探测。

    返回 `(快照 或 None, 取数说明)`。取不到时返回 `(None, 原因)`：写操作按"确认不了权限
    就不动手"处理（见 `verdict`），读操作不因此被拦。
    """
    try:
        fixture = load_fixture()
    except CliError as e:
        return None, e.message
    if fixture:
        return fixture, "使用注入快照（%s）：不联网、不改任何账号事实" % os.path.basename(
            fixture.get("fixturePath") or "")
    if use_cache and not force:
        cached = read_cache(ttl=ttl)
        if cached:
            cached["source"] = "cache"
            return cached, "使用本地快照缓存（探测于 %s）" % cached.get("probedAt")
    try:
        snap = probe_live(client=client)
    except Exception as e:                                                # noqa: BLE001
        return None, "账号信息探测失败：%s" % str(e)[:200]
    write_cache(snap)
    return snap, "实时探测 auth.me ＋ 工作区权益"


# ─────────────────────────── 判据 ───────────────────────────
def _axis(name, ok, reason):
    return {"轴": name, K_ALLOWED: bool(ok), K_REASON: reason}


def auth_from_inputs(system_role=None, user_status=None, features=None, plan_tier=None,
                     max_brands=None, max_searches=None, max_emails=None, workspace_name=None,
                     source="declared"):
    """按契约／调用方**声明**的账号事实造一份判定用快照（离线、不联网）。

    用途：契约引擎在不联网的情况下按"声明的账号上下文"核对写权限（例如某个契约要证明
    "普通角色用不了这个模块"）。声明只影响判据输入，不代表任何真实账号。
    """
    snap = _snapshot_from_me({})
    snap["systemRole"] = system_role
    snap["userStatus"] = user_status
    snap["enabledFeatures"] = list(features or [])
    snap["workspace"] = {"id": None, "name": workspace_name, "planTier": plan_tier,
                         "status": "active" if (user_status or "active") == "active" else user_status,
                         "maxBrands": max_brands, "maxSearchesPerMonth": max_searches,
                         "maxEmailsPerMonth": max_emails}
    snap["source"] = source
    return snap


def verdict(module_key, kind=WRITE, auth=None, usage=None):
    """一条模块 × 读/写 的能力判定：`{allowed, 轴[], reason, deniedAxes}`。

    `auth=None` 的处理：写操作**保守拒绝**（确认不了权限就不动手），读操作放行
    （读链的真实门禁在服务端，CLI 不在取数前自造一道可能误伤的闸）。
    """
    rule = MODULE_RULES.get(module_key)
    if rule is None:
        return {"module": module_key, "kind": kind, K_ALLOWED: True,
                "reason": "该模块没有模块级判据（元模块、引擎模块或本机副作用入口）",
                "axes": [], "deniedAxes": []}
    if auth is None:
        if kind == WRITE and rule.get("accountFactRequired", True):
            return {"module": module_key, "kind": kind, K_ALLOWED: False,
                    "reason": "拿不到账号权限快照：写操作按安全口径不执行（先跑 "
                              "daniel account capabilities 建立快照）",
                    "axes": [], "deniedAxes": ["账号信息"]}
        if kind == WRITE:
            # 例外只有「账号与盘点」：写凭据与登录**就是**拿到账号事实的前提，新机器上没有会话
            # 也必须能做（见 `_rule` 的 `account_fact_required`）。
            return {"module": module_key, "kind": kind, K_ALLOWED: True,
                    "reason": "该模块的写不依赖账号权限快照：把凭据写进本机钥匙串、登录刷新会话，"
                              "正是新机器上拿到账号事实的前提",
                    "axes": [], "deniedAxes": []}
        return {"module": module_key, "kind": kind, K_ALLOWED: True,
                "reason": "拿不到账号权限快照：读操作不因此被拦（真实门禁在服务端）",
                "axes": [], "deniedAxes": []}

    role = auth.get("systemRole")
    status = auth.get("userStatus")
    features = set(auth.get("enabledFeatures") or [])
    axes = []

    if rule["roles"] is not None:
        ok = role in rule["roles"]
        axes.append(_axis(
            "系统角色", ok,
            ("systemRole=%s 满足该模块要求（%s）" % (role, "／".join(rule["roles"]))) if ok else
            ("系统角色不满足：该模块要求 %s，当前 systemRole=%s"
             % ("／".join(rule["roles"]), role))))
    else:
        axes.append(_axis("系统角色", True,
                          "systemRole=%s：该模块在前端对全部登录角色可见，没有角色要求" % role))

    if rule["statusRequired"]:
        ok = status not in BLOCKED_STATUS
        axes.append(_axis("账号状态", ok,
                          ("userStatus=%s 正常" % status) if ok else
                          ("账号状态不满足：当前 userStatus=%s，%s 两种状态不能使用任何模块"
                           % (status, "／".join(BLOCKED_STATUS)))))
    else:
        axes.append(_axis("账号状态", True, "该模块不因账号状态被拦（查自己的账号是排障前提）"))

    if rule["features"]:
        if role in ADMIN_ROLES:
            axes.append(_axis("工作区权益", True,
                              "systemRole=%s 为管理角色：前端对管理角色不检查工作区权益" % role))
        else:
            missing = [f for f in rule["features"] if f not in features]
            axes.append(_axis("工作区权益", not missing,
                              "工作区已开启所需权益（%s）" % "／".join(rule["features"]) if not missing
                              else ("工作区权益不满足：该模块需要工作区开启 %s，当前工作区未开启"
                                    "（已开启：%s）" % ("／".join(missing),
                                                    "／".join(sorted(features)) or "无"))))

    if kind == WRITE and rule["quota"]:
        axes.append(_quota_axis(rule["quota"], auth, usage, role))

    denied = [a for a in axes if not a[K_ALLOWED]]
    reason = "；".join(a[K_REASON] for a in denied) if denied else "；".join(
        a[K_REASON] for a in axes)
    return {"module": module_key, "kind": kind, "title": rule["title"],
            K_ALLOWED: not denied, "reason": reason, "axes": axes,
            "deniedAxes": [a["轴"] for a in denied]}


def _quota_axis(which, auth, usage, role):
    ws = auth.get("workspace") or {}
    name = {"brands": "品牌数", "searches": "每月检索次数"}.get(which, which)
    limit = (usage or {}).get(which, {}).get("limit")
    if limit is None:
        limit = ws.get("maxBrands") if which == "brands" else ws.get("maxSearchesPerMonth")
    used = (usage or {}).get(which, {}).get("used")
    note = (usage or {}).get(which, {}).get("note") or ""
    if role in ADMIN_ROLES:
        return _axis("配额", True,
                     "配额轴：%s 上限 %s；systemRole=%s 为管理角色，前端对管理角色不显示也不拦配额"
                     % (name, _fmt_limit(limit), role))
    if limit is None:
        return _axis("配额", True, "配额轴：%s 未声明上限，不拦" % name)
    if limit is not None and int(limit) < 0:
        return _axis("配额", True, "配额轴：%s 上限为不限（%s）" % (name, limit))
    if used is None:
        return _axis("配额", True,
                     "配额轴：%s 上限 %s，当前用量未取到（%s），不拦"
                     % (name, _fmt_limit(limit), note or "接口未返回用量"))
    if int(used) >= int(limit):
        return _axis("配额", False,
                     "配额不满足：工作区「%s」的%s上限为 %d，已用 %d，已无余量（管理角色不受此限）"
                     % (ws.get("name") or ws.get("id"), name, int(limit), int(used)))
    return _axis("配额", True, "配额轴：%s 已用 %d／上限 %d" % (name, int(used), int(limit)))


def _fmt_limit(v):
    if v is None:
        return "未声明"
    return "不限" if int(v) < 0 else str(int(v))


def capability_matrix(auth=None, usage=None):
    """能力矩阵：模块 × 读/写 × 是否允许 ＋ 理由（`daniel account capabilities` 的结果体）。"""
    rows = []
    for key in rule_keys():
        rule = MODULE_RULES[key]
        r = verdict(key, READ, auth, usage)
        w = verdict(key, WRITE, auth, usage)
        rows.append({
            "模块": key, "名称": rule["title"],
            "读": {K_ALLOWED: r[K_ALLOWED], K_REASON: r["reason"]},
            "写": {K_ALLOWED: w[K_ALLOWED], K_REASON: w["reason"]},
            "写判据": [{"轴": a["轴"], K_ALLOWED: a[K_ALLOWED], K_REASON: a[K_REASON]}
                     for a in w["axes"]],
            "前端出处": rule["evidence"],
        })
    return rows


def summarize(rows):
    read_ok = [r["模块"] for r in rows if r["读"][K_ALLOWED]]
    write_ok = [r["模块"] for r in rows if r["写"][K_ALLOWED]]
    write_no = [r["模块"] for r in rows if not r["写"][K_ALLOWED]]
    return {"模块数": len(rows), "可读": len(read_ok), "可写": len(write_ok),
            "可写模块": write_ok, "不可写模块": write_no,
            "结论": ("%d 个模块里 %d 个可读、%d 个可写" % (len(rows), len(read_ok), len(write_ok))
                     + ("；不可写：%s" % "／".join(write_no) if write_no else ""))}


def denial_message(module_key, kind, v):
    """无权时的"人话理由"（说明是哪一轴不满足，含当前取值与要求）。"""
    rule = MODULE_RULES.get(module_key) or {}
    title = rule.get("title") or module_key
    what = "写" if kind == WRITE else "读"
    return ("账号对「%s」没有%s权限（%s）。判据：%s。"
            "该模块能不能用由账号的使用权限决定；跑 `daniel account capabilities` 看完整能力矩阵。"
            % (title, what,
               "不满足的判据轴：" + "／".join(v.get("deniedAxes") or ["账号信息"]),
               v.get("reason")))


def audit_fields(auth):
    """审计记录里的账号与工作区字段（**只放快照里的白名单字段**）。"""
    auth = auth or {}
    ws = auth.get("workspace") or {}
    return {"account": auth.get("emailMasked"), "systemRole": auth.get("systemRole"),
            "userStatus": auth.get("userStatus"),
            "workspaceId": auth.get("activeWorkspaceId") or ws.get("id"),
            "workspaceName": ws.get("name"), "planTier": ws.get("planTier"),
            "permissionSource": auth.get("source")}


__all__ = ["MODULE_RULES", "READ", "WRITE", "FIXTURE_ENV", "ADMIN_ROLES", "BLOCKED_STATUS",
           "capability_matrix", "summarize", "verdict", "denial_message", "current_auth",
           "probe_live", "probe_usage", "load_fixture", "read_cache", "write_cache",
           "audit_fields", "rule_keys", "rule_for", "auth_from_inputs"]
