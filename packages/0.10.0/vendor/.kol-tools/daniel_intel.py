#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daniel_intel.py —— Daniel **Intelligence（Action Center / 关键词 / Memo / Review / Topic / 读类）** 仪器。

来源与口径：`.kol-tools/_daniel_bundle/*.pretty.js` 的**调用点**（路由名与入参键以 bundle 为准，
不是记忆里的旧代码、也不是命名习惯 —— Skill §15.4 / CLS-46 判据）。
实测状态与逐字证据见 `docs/marketing/kol/_daniel-integration/03-intel-core.md`（TICKET-133）。

## 三条硬纪律（本工具内置）
1. 🔴 **读类随时可跑**（`GET`）；写／触发类**默认 `--dry-run`**，只有显式 `--run` 才发 `POST`。
2. 🔴 **不猜入参**：每个写路由都在 `--shape` 模式下用**类型非法入参**打一次，让服务端返回 zod 路径，
   **不产生任何副作用**（tRPC 的入参校验在 resolver 之前）；`--shape` 用于首次接触新路由。
3. 🔴 **回读核对**：`--run` 成功后自动回读对应读路由（`--no-verify` 可关）。

## 用法速查
```bash
python3 .kol-tools/daniel_intel.py --brand Halliday scope                 # 解析 scope（4 键）
python3 .kol-tools/daniel_intel.py --brand Halliday status                 # 每周洞察状态
python3 .kol-tools/daniel_intel.py --brand Halliday actions               # Action Center 列表
python3 .kol-tools/daniel_intel.py --brand Halliday keywords memos topics  # 关键词 / Memo / Topic
python3 .kol-tools/daniel_intel.py --brand Halliday write memos-create --content "x" --run
python3 .kol-tools/daniel_intel.py --brand Halliday --shape write memos-create   # 只探入参，无副作用
python3 .kol-tools/daniel_intel.py --routes                               # 路由表（markdown）
python3 .kol-tools/daniel_intel.py --self-test                            # 离线自检（不联网）
```

## 读结果只走一条路：`--json` 出**读结果信封**（TICKET-150）
```bash
python3 .kol-tools/daniel_intel.py --brand 3690002 actions --json            # 全量 ＋ 条数 ＋ 分页游标
python3 .kol-tools/daniel_intel.py --brand 3690002 actions --json --limit 5  # 前 5 条（游标=5，truncated=true）
python3 .kol-tools/daniel_intel.py --brand 3690002 actions --json --offset 5 --limit 5   # 翻到下一批
python3 .kol-tools/daniel_intel.py --brand 3690002 actions --json --max-chars 3000       # 字符预算（只丢整条）
```
- `--json` 时 **stdout 有且只有一个 JSON 文档**（`daniel.read.v1` 信封：`result`／`total`／`returned`／
  `paging`／`truncated`／`truncatedReason`），人读的入参提示走 stderr；
- **不设隐式字符上限**（旧版会截到 12000 字符 ⇒ 调用方只能抢救前几条）。要收窄只有两条明路：
  `--limit/--offset`（按条分页）或 `--max-chars N`（字符预算）——两条都会写清"上限值、被截了多少条、
  游标在哪、怎么取全"；
- 人读模式（不带 `--json`）仍是原来的中文摘要，摘要行会写明"全量请用 `--json`"。

> **Authenticity 不在这里**：它没有后端路由（前端自算），见 `.kol-tools/daniel_authenticity.py`。
"""
import argparse
import json
import os
import sys

BASE = "https://daniel-agent.com"
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:          # 兄弟模块 daniel_io：脚本直跑与"被别的仪器当模块载入"两条路都要能 import
    sys.path.insert(0, HERE)
import daniel_io  # noqa: E402  （TICKET-168：`--json` 出口的唯一收口层）

# ------------------------------------------------------------------ 路由注册表（真源）
# kind: read=GET 只读 / write=POST 可逆写 / trigger=POST 触发任务
# keys: 入参键（逐字取自 bundle 调用点）
SCOPE4 = ("categoryProfileId", "brandId", "categoryId", "country")

ROUTES = {
    # ---- Intelligence（每周洞察）----
    "intelligence.status": dict(prefix="actionCenter", method="GET", kind="read",
                                keys=SCOPE4, note="返回 eligible/seo/exposure/blockers/weekKey/collectionTasks/insight"),
    "intelligence.refresh": dict(prefix="actionCenter", method="POST", kind="trigger", keys=SCOPE4,
                                 note="周洞察生成；返回 {status: blocked|in_progress|quota_exhausted|…, blockers[]}"),
    "intelligence.requestCollection": dict(prefix="actionCenter", method="POST", kind="trigger",
                                           keys=SCOPE4 + ("type",),
                                           enum={"type": ["seo_collection", "exposure_collection"]},
                                           note="返回 {triggered, dispatchPending, customerMessage}"),
    # ---- Action Center ----
    "actions.list": dict(prefix="actionCenter", method="GET", kind="read", keys=SCOPE4 + ("statuses",),
                         note="statuses 为数组，UI 传全部 5 态；返回 [{action, topic}]"),
    "actions.observationTimeline": dict(prefix="actionCenter", method="GET", kind="read",
                                        keys=SCOPE4 + ("actionId",),
                                        note="返回 {action, baseline, baselineExposure, observations[]}"),
    "actions.setStatus": dict(prefix="actionCenter", method="POST", kind="write",
                              keys=SCOPE4 + ("actionId", "status"),
                              enum={"status": ["suggested", "saved", "accepted", "dismissed", "archived"]},
                              note="🔴 只允许改**自己造出来**的 action；无 create 路由 ⇒ 实操上不要动真实动作"),
    # ---- 关键词 ----
    "keywords.listKeywords": dict(prefix="actionCenter", method="GET", kind="read", keys=SCOPE4,
                                  note="返回 {keywords[], activeCount, limit, remaining}"),
    "keywords.addCustomKeyword": dict(prefix="actionCenter", method="POST", kind="write",
                                      keys=SCOPE4 + ("keyword",),
                                      note="🔴 **无删除路由**（只有 setKeywordStatus 停用）⇒ 默认不加，只做 --shape"),
    "keywords.setKeywordStatus": dict(prefix="actionCenter", method="POST", kind="write",
                                      keys=SCOPE4 + ("keywordId", "status"),
                                      enum={"status": ["active", "disabled"]}, note="作用在真实关键词上"),
    "keywords.reviewKeywordOnce": dict(prefix="actionCenter", method="POST", kind="trigger",
                                       keys=SCOPE4 + ("keyword",),
                                       note="⚠️ 会消耗该市场的检索配额 ⇒ 未实跑"),
    # ---- Memo ----
    "memos.list": dict(prefix="actionCenter", method="GET", kind="read", keys=("brandId",),
                       note="按 brand 维度，返回 [{id, content, …}]"),
    "memos.create": dict(prefix="actionCenter", method="POST", kind="write", keys=("brandId", "content"),
                         note="🔴 **无删除路由**（只有 update 改内容）⇒ 不可逆，默认不建"),
    "memos.update": dict(prefix="actionCenter", method="POST", kind="write", keys=("memoId", "content"),
                         note="改 memoid 的正文；不存在 → 404 Memo not found"),
    # ---- Review（文档/文本审核）----
    "reviews.list": dict(prefix="actionCenter", method="GET", kind="read", keys=SCOPE4),
    "reviews.getById": dict(prefix="actionCenter", method="GET", kind="read", keys=SCOPE4 + ("reviewId",),
                            note="reviewId 必须 >0（0 → 400 Too small）；不存在 → 404 Content review not found"),
    "reviews.addTextVersion": dict(prefix="actionCenter", method="POST", kind="write",
                                   keys=SCOPE4 + ("reviewId", "brief", "script", "transcript", "title",
                                                  "creatorChannelId", "description", "chapters"),
                                   note="brief/script/transcript/title/description/chapters 至少一项非空；返回 {reviewId, versionNumber}"),
    "reviews.addDocumentVersion": dict(prefix="actionCenter", method="POST", kind="write",
                                       keys=SCOPE4 + ("reviewId", "fileName", "mimeType", "size", "base64",
                                                      "documentField"),
                                       note="文件走 base64（bundle 里 32KB 分块 btoa）"),
    "reviews.runTextReview": dict(prefix="actionCenter", method="POST", kind="trigger",
                                  keys=SCOPE4 + ("stage", "topicReportId", "topicLabel", "brief", "script",
                                                 "transcript", "title", "creatorChannelId", "description", "chapters"),
                                  enum={"stage": ["pre_production", "final_packaging"]},
                                  note="新建审阅并跑审核；无 reviewId 时创建新审阅"),
    "reviews.runDocumentReview": dict(prefix="actionCenter", method="POST", kind="trigger",
                                      keys=SCOPE4 + ("stage", "topicReportId", "topicLabel", "fileName",
                                                     "mimeType", "size", "base64", "documentField"),
                                      enum={"stage": ["pre_production", "final_packaging"]}),
    # ---- Topic ----
    "topics.list": dict(prefix="actionCenter", method="GET", kind="read", keys=SCOPE4,
                        note="返回 [{id, topicKey, title, primaryKeyword, keywords[], summary, evidence, status}]"),
    "topics.getSharedCore": dict(prefix="actionCenter", method="GET", kind="read", keys=SCOPE4,
                                 note="返回 {id, summary, brandFacts, proofPoints[], briefFoundations, evidenceFingerprint}"),
    "topics.getVideoEvidence": dict(prefix="actionCenter", method="GET", kind="read",
                                    keys=SCOPE4 + ("topicReportId",),
                                    note="返回 {status, progressPercent, selectedCount, summary, videos[]}"),
    "topics.startVideoEvidence": dict(prefix="actionCenter", method="POST", kind="trigger",
                                      keys=SCOPE4 + ("topicReportId",),
                                      note="⚠️ 不存在的 topicReportId → **500** Topic not found（不是 404）；会真跑分析"),
    # ---- Dashboard / Content / Videos（读类）----
    "dashboard.getTopCreators": dict(method="GET", kind="read",
                                     keys=SCOPE4 + ("days", "page", "pageSize", "brandFilter"),
                                     note="返回 {items[], total}；brandFilter 可省（UI 传 undefined）"),
    "dashboard.getTopContent": dict(method="GET", kind="read",
                                    keys=SCOPE4 + ("days", "page", "pageSize", "brandFilter"),
                                    note="返回 {items[], total}"),
    "content.listVideos": dict(method="GET", kind="read", keys=("brandId", "limit", "offset"),
                               note="UI：limit 50 / offset 0；返回数组"),
    "content.getStats": dict(method="GET", kind="read", keys=("brandId",),
                             note="返回 {totalVideos, totalMentions}"),
    # 以下三条属 Creator Tracker（`ct.` 前缀，非 actionCenter）
    "videos.list": dict(prefix="ct", method="GET", kind="read", keys=("campaignId",)),
    "videos.getInsight": dict(prefix="ct", method="GET", kind="read", keys=("campaignId", "videoCollabId")),
    "videos.getChannelInterests": dict(prefix="ct", method="GET", kind="read", keys=("channelId",)),
    # ---- scope 解析辅助（不属于 ticket 清单，但 scope 必需）----
    "brands.list": dict(method="GET", kind="read", keys=(), note="入参必须是对象 `{}`（传 null → 400）"),
    "sovCategories.getByBrand": dict(method="GET", kind="read", keys=("brandId",),
                                     note="scope 来源：`assocId`→categoryProfileId、`id`→categoryId、`operatingMarkets`→country"),
}

WRITE_SUBCMDS = {
    "intelligence-refresh": "intelligence.refresh",
    "intelligence-collect": "intelligence.requestCollection",
    "actions-set-status": "actions.setStatus",
    "keywords-add": "keywords.addCustomKeyword",
    "keywords-set-status": "keywords.setKeywordStatus",
    "keywords-review-once": "keywords.reviewKeywordOnce",
    "memos-create": "memos.create",
    "memos-update": "memos.update",
    "reviews-add-text": "reviews.addTextVersion",
    "reviews-add-doc": "reviews.addDocumentVersion",
    "reviews-run-text": "reviews.runTextReview",
    "reviews-run-doc": "reviews.runDocumentReview",
    "topics-start-evidence": "topics.startVideoEvidence",
}
READ_SUBCMDS = {
    "status": "intelligence.status",
    "actions": "actions.list",
    "actions-timeline": "actions.observationTimeline",
    "keywords": "keywords.listKeywords",
    "memos": "memos.list",
    "reviews": "reviews.list",
    "review-get": "reviews.getById",
    "topics": "topics.list",
    "topics-shared-core": "topics.getSharedCore",
    "topics-evidence": "topics.getVideoEvidence",
    "dashboard-creators": "dashboard.getTopCreators",
    "dashboard-content": "dashboard.getTopContent",
    "content-videos": "content.listVideos",
    "content-stats": "content.getStats",
    "ct-videos": "videos.list",
    "ct-video-insight": "videos.getInsight",
    "ct-channel-interests": "videos.getChannelInterests",
}
# `--run` 之后自动回读哪条读路由（回读核对）
VERIFY_ROUTE = {
    "memos.create": "memos.list", "memos.update": "memos.list",
    "actions.setStatus": "actions.list", "keywords.addCustomKeyword": "keywords.listKeywords",
    "keywords.setKeywordStatus": "keywords.listKeywords", "reviews.addTextVersion": "reviews.list",
    "reviews.addDocumentVersion": "reviews.list", "reviews.runTextReview": "reviews.list",
    "reviews.runDocumentReview": "reviews.list", "topics.startVideoEvidence": "topics.getVideoEvidence",
    "intelligence.refresh": "intelligence.status", "intelligence.requestCollection": "intelligence.status",
}


def full_route(name):
    """注册表短名 → 真实 tRPC 路由名（含 `actionCenter.` / `ct.` 前缀）。"""
    r = ROUTES[name]
    p = r.get("prefix")
    return ("%s.%s" % (p, name)) if p else name


def active_workspace_id(d):
    """🔴 `brands.list` **只返回当前 active workspace 的品牌** —— 先把 activeWorkspaceId 读出来，
    否则解析不到品牌时无法区分「名字打错」与「活跃 workspace 被人切了」。"""
    try:
        return (d.query("auth.me") or {}).get("activeWorkspaceId")
    except Exception:  # noqa: BLE001
        return None


def resolve_brand(d, brand):
    """按名字或 id 解析品牌；名字歧义 ⇒ 抛错要 id，**不猜**（Skill §15.2 步 1）。

    ⚠️ 实测坑（2026-10-10）：`brands.list` 是 **workspace 维度**的 —— 活跃 workspace 被切换后，
    同一个名字会"消失"。因此：① 数字 id 优先（不经 `brands.list`，用 `sovCategories.getByBrand` 校验存在性）；
    ② 名字找不到时，报错里**带上 activeWorkspaceId**，让人立刻看出是作用域问题而不是拼写问题。
    """
    s = str(brand).strip()
    if s.lstrip("-").isdigit():
        bid = int(s)
        b = d.get_brand(bid) if hasattr(d, "get_brand") else None
        if isinstance(b, dict) and b.get("id"):
            return b
        profs = d.query("sovCategories.getByBrand", {"brandId": bid}) or []
        if not profs:
            raise SystemExit("brandId=%s 不可达：brands.getById 返回空且 sovCategories.getByBrand 也为空"
                             "（活跃工作区=%s，仅供参考 —— 本解析不依赖它）。" % (bid, active_workspace_id(d)))
        return {"id": bid, "name": "<brand %s>" % bid, "category": profs[0].get("name")}
    if not hasattr(d, "resolve_brand_ref"):
        raise SystemExit("该客户端无 resolve_brand_ref ⇒ 无法按名字解析；请直接给 **--brand <brandId>**"
                         "（活跃工作区=%s，仅供参考）。" % active_workspace_id(d))
    return d.resolve_brand_ref(s)


def resolve_scope(d, brand, country=None, category_profile_id=None, category_id=None):
    """解析 4 键 scope（与前端 `useBrandCategory` 同源：`sovCategories.getByBrand`）。"""
    profs = d.query("sovCategories.getByBrand", {"brandId": brand["id"]}) or []
    if not profs:
        raise SystemExit("该 brand 下没有 category profile（sovCategories.getByBrand 返回空）")
    p = None
    if category_profile_id:
        p = next((x for x in profs if x.get("assocId") == int(category_profile_id)), None)
        if p is None:
            raise SystemExit("categoryProfileId %s 不在该 brand 的 profile 列表里：%s"
                             % (category_profile_id, [x.get("assocId") for x in profs]))
    else:
        p = profs[0]
    markets = p.get("operatingMarkets") or p.get("countries") or []
    if not markets:
        raise SystemExit("该 category profile 没有 operatingMarkets，必须用 --country 显式指定")
    ctry = country or markets[0]
    if ctry not in markets:
        raise SystemExit("country「%s」不在该 market 列表 %s 内" % (ctry, markets))
    return {"categoryProfileId": p.get("assocId"),
            "brandId": brand["id"],
            "categoryId": category_id or p.get("id"),
            "country": ctry}


def redact(obj):
    """脱敏：任何键名含 cookie/token/secret/password/email/base64 的值一律打码（防误传）。"""
    import re
    bad = ("cookie", "token", "secret", "password", "email", "base64", "authorization")
    if isinstance(obj, dict):
        return {k: ("<redacted>" if any(b in str(k).lower() for b in bad) else redact(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str) and len(obj) > 24 and re.fullmatch(r"[A-Za-z0-9._~+/=-]+", obj):
        return obj[:4] + "…<redacted>"
    return obj


def shape_of(v):
    if isinstance(v, dict):
        return {k: (("list[%d]" % len(v[k])) if isinstance(v[k], list) else
                    ("dict" if isinstance(v[k], dict) else type(v[k]).__name__)) for k in v}
    if isinstance(v, list):
        return "list[%d]" % len(v)
    return type(v).__name__


# ------------------------------------------------------------------ 读结果信封（TICKET-150）
# 为什么有这一层：读链原先把结果 JSON 直接打印并截到 12000 字符（`[:12000]`），
# 调用方只能"从被切断的文本里抢救前几条" —— 截断即丢数据，且调用方无从知道丢了多少。
# 现在的口径：**不再按字符截断**，改成"整条分页 ＋ 游标 ＋ 显式标注"。
# 🔴 口径纪律：本层只搬运**事实**（有多少条、取到了哪几条、下一页怎么取、被谁截了），
#    不判断"哪条重要""多少条算够" —— 任何业务判据都在能力层（bundle／Skill），不在这里。
READ_SCHEMA = "daniel.read.v1"
DEFAULT_MAX_CHARS = 0                      # 0 ＝ 不限字符（不设隐式上限）
NO_TOTAL_NOTE = "接口不返回总数：只有返回条数等于上限时才能推断可能还有更多"

# 各读路由的"条数从哪来"（分页口径；不是业务判据，只是数据的形状）：
#   offset        —— 入参没有分页键，本机按 --limit/--offset 在返回的全量列表上取窗口；
#   server-page   —— 入参带 page/pageSize，服务端分页（总数由服务端给）；
#   server-limit  —— 入参带 limit，服务端按上限截取且**不返回总数**；
#   server-window —— 入参带 limit/offset，服务端已切好窗口；
#   none          —— 单对象或不分页列表（一次返回即全量）。
READ_PAGING = {
    "actions.list": "offset",
    "dashboard.getTopCreators": "server-page",
    "dashboard.getTopContent": "server-page",
    "content.listVideos": "server-window",
}
READ_PAGING_DEFAULT = "none"


def read_paging_kind(route_name):
    return READ_PAGING.get(route_name, READ_PAGING_DEFAULT)


def _server_total(result):
    """服务端返回里**自带**的总数（`{items[], total}` 之类）；没有就返回 None —— 不猜。"""
    if isinstance(result, dict):
        for k in ("total", "totalCount", "count"):
            v = result.get(k)
            if isinstance(v, int) and not isinstance(v, bool):
                return v
    return None


def _json_text(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1)


#: 字典结果里承载条目的列表字段（服务端惯例）。**只按字段名取，不发明字段**。
ROW_FIELDS = ("items", "results", "rows", "videos", "keywords", "topics", "reviews", "memos", "brands")

#: **过滤类**入参键（只用于把"本次真正发给服务端的过滤条件"原样抄进信封，不含任何判据）。
FILTER_KEYS = ("statuses", "status", "days", "page", "pageSize", "brandFilter")


def filter_echo(inp, result):
    """读到的事实：本次实际使用的过滤条件 ＋ 服务端自报的"被排除条数"（有就抄，没有就给 null）。"""
    echo = {k: inp[k] for k in FILTER_KEYS if isinstance(inp, dict) and k in inp}
    excluded = None
    if isinstance(result, dict):
        for k in ("excludedIrrelevant", "excludedCount"):
            v = result.get(k)
            if isinstance(v, int) and not isinstance(v, bool):
                excluded = v
                break
    return {"echo": echo, "excludedIrrelevant": excluded,
            "excludedSource": "服务端返回字段 excludedIrrelevant（本仪器不自行计算）"}


def _row_field(result):
    """→ (字段名, 该字段的列表)；不是"字典里挂着列表"就返回 (None, None)。"""
    if isinstance(result, dict):
        for k in ROW_FIELDS:
            if isinstance(result.get(k), list):
                return k, result[k]
    return None, None


def _fit_count(n, budget, measure):
    """在 0..n 里取满足字符预算的最大条数（**只丢整条，绝不切字符**）。→ (k, 是否收窄)。

    切字符会产出非法 JSON（这正是"截断抢救"的病根）；丢整条则永远合法，
    且"丢了多少条、下一条游标是多少"都能如实写进信封。
    """
    if not budget or budget <= 0 or not n:
        return n, False
    if len(_json_text(measure(n))) <= budget:
        return n, False                          # 预算够：一条不丢，不算截断
    lo, hi = 0, n
    while lo < hi:                               # 条目越多字符越多 ⇒ 单调，可二分
        mid = (lo + hi + 1) // 2
        if len(_json_text(measure(mid))) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return lo, True


def read_envelope(route, result, inp=None, method="GET", kind=READ_PAGING_DEFAULT,
                  limit=None, offset=0, page=None, page_size=None,
                  max_chars=DEFAULT_MAX_CHARS, note=None):
    """把一次只读结果装成统一信封（字段顺序固定 ⇒ 仪器路径与 CLI 路径可做**键比对**）。

    字段含义（全部是事实字段，不含判据）：
      `result`   服务端原样返回（仅经 `redact` 脱敏）；
      `input`    本次真实入参（供调用方复核"这份结果是对谁查的"）；
      `total`    服务端给的总数；没有则＝本次取到的全量条数（列表）；单对象为 null；
      `returned` 本次真正放进 `result` 的条数；
      `paging`   分页导航（kind/limit/offset/page/pageSize/totalPages/hasMore/nextCursor/
                 nextPage/howToContinue）—— 只说"怎么翻页"，不评价数据；
      `truncated` ＋ `truncatedReason`  是否**被收窄**过（给了上限、服务端截取、字符预算
                 触发）＋ 原因与取全办法。凡触达上限必为 true，绝不静默。
    """
    lim = None if limit is None else max(0, int(limit))
    off = max(0, int(offset or 0))
    budget = int(max_chars or 0)
    field, rows = (None, result) if isinstance(result, list) else _row_field(result)
    server_total = _server_total(result)
    full_count = len(rows) if isinstance(rows, list) else None
    total = server_total if server_total is not None else full_count

    def shrink(obj, k):
        """把结果对象收窄成"前 k 条"：列表直接切；字典切它承载条目的那个列表字段。"""
        if k is None:
            return obj
        if isinstance(obj, list):
            return obj[:k]
        if field:
            out = dict(obj)
            out[field] = obj[field][:k]
            return out
        return obj

    if isinstance(result, list) and kind == "offset":
        base = result[off:] if lim is None else result[off:off + lim]
    else:
        base = result

    def doc(obj, budget_hit):
        rows_here = obj if isinstance(obj, list) else _row_field(obj)[1]
        returned = len(rows_here) if isinstance(rows_here, list) else None
        has_more = None
        next_cursor = None
        next_page = None
        total_pages = None
        reason = None
        if kind == "offset" and returned is not None:
            has_more = (off + returned < total) if isinstance(total, int) else None
            if has_more:
                next_cursor = off + returned
                how = ("本次取第 %d–%d 条（全量 %d 条）：用 --offset %d 取下一批，"
                       "或去掉 --limit 一次取全" % (off + 1, off + returned, total, next_cursor))
                reason = "按 --limit %s 分页取数：本次只放了 %d 条（全量 %d 条）" % (
                    "-" if lim is None else lim, returned, total)
            else:
                how = "已取全（全量 %s 条）" % (total if total is not None else returned)
        elif kind == "server-page":
            ps = int(page_size) if page_size else returned
            if isinstance(total, int) and ps:
                total_pages = (total + ps - 1) // ps
            cur = int(page) if page else 1
            has_more = (cur < total_pages) if total_pages else (
                (returned >= ps) if (ps and returned is not None) else None)
            if has_more:
                next_page = cur + 1
                how = ("本页 %d 条，共 %s 条、%s 页：用 --page %s 取下一页"
                       % (returned, total, total_pages or "?", next_page))
                reason = "服务端分页：本次只返回第 %s 页（共 %s 页、%s 条）" % (
                    cur, total_pages or "?", total)
            else:
                how = "已是最后一页（共 %s 页、%s 条）" % (total_pages or "?", total)
        elif kind == "server-limit":
            how = ("服务端按上限 %s 截取；%s" % (lim, NO_TOTAL_NOTE)) if lim is not None else \
                  "服务端未声明上限"
            if lim is not None and returned is not None and returned >= lim:
                reason = ("服务端按上限截取：本次返回 %d 条＝上限 %s，可能还有更多（%s）"
                          % (returned, lim, NO_TOTAL_NOTE))
        elif kind == "server-window":
            how = ("服务端已按 --limit/--offset 切好窗口（本次 %s 条）；%s"
                   % (returned, NO_TOTAL_NOTE))
        elif returned is not None:
            has_more = False
            how = "本路由不分页：接口一次返回全部 %d 条" % returned
        else:
            how = "单条结果（%s）：本路由不返回列表，无分页" % (
                "服务端总数 %s" % total if isinstance(total, int) else "接口未给总数")
        if budget_hit:
            reason = ("字符预算 --max-chars %d 触发：只放了前 %d 条（共 %s 条），"
                      "未切字符、JSON 合法；去掉 --max-chars（默认不限）或按游标翻页可取全"
                      % (budget, returned, total if total is not None else "?"))
            if isinstance(total, int):
                has_more = returned < total
            if has_more and kind == "offset" and next_cursor is None:
                next_cursor = off + returned
        return {
            "schema": READ_SCHEMA,
            "route": route,
            "method": method,
            "input": redact(inp) if inp is not None else None,
            "filter": filter_echo(inp, obj),
            "total": total,
            "returned": returned,
            "result": obj,
            "paging": {
                "kind": kind, "limit": lim, "offset": off,
                "page": int(page) if page else None,
                "pageSize": int(page_size) if page_size else None,
                "totalPages": total_pages, "hasMore": has_more,
                "nextCursor": next_cursor, "nextPage": next_page,
                "howToContinue": how,
            },
            "truncated": bool(reason),
            "truncatedReason": reason,
        }

    n = len(base) if isinstance(base, list) else (
        len(base[field]) if (isinstance(base, dict) and field) else None)
    if n is not None and budget > 0:
        k, hit = _fit_count(n, budget, lambda kk: doc(shrink(base, kk), True))
        while k > 0 and len(_json_text(doc(shrink(base, k), True))) > budget:
            k -= 1                               # 预算含信封外壳：落一次实测收口（仍只丢整条）
        env = doc(shrink(base, k), hit)
    else:
        env = doc(base, False)
    if note:
        env["notes"] = [note]
    return env


# ------------------------------------------------------------------ 客户端 / 原始 HTTP
def client():
    sys.path.insert(0, HERE)
    from daniel_client import Daniel  # noqa: E402
    return Daniel(verbose=False)


def raw_request(d, route, inp, method="POST"):
    """绕过客户端封装，拿**原始 HTTP 状态码 + 原始错误体**（客户端会把错误吞成一行）。"""
    import urllib.error
    import urllib.parse
    import urllib.request
    h = d._headers()
    if method == "GET":
        url = BASE + "/api/trpc/" + route + "?batch=1&input=" + urllib.parse.quote(json.dumps({"0": {"json": inp}}))
        req = urllib.request.Request(url, headers=h)
    else:
        req = urllib.request.Request(BASE + "/api/trpc/" + route,
                                     data=json.dumps({"json": inp}).encode(), method="POST", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


# ------------------------------------------------------------------ 入参组装
def build_input(route_name, a, scope):
    """按注册表 + CLI 参数组装入参；缺必需键 ⇒ 抛 SystemExit（**不猜**）。"""
    r = ROUTES[route_name]
    keys = list(r["keys"])
    inp = {}
    if "brandId" in keys:
        inp["brandId"] = scope["brandId"]
    for k in ("categoryProfileId", "categoryId", "country"):
        if k in keys:
            inp[k] = scope[k]
    opt = lambda v, k: (inp.__setitem__(k, v) if v is not None else None)
    if route_name == "actions.list":
        inp["statuses"] = a.status or ["suggested", "saved", "accepted", "dismissed", "archived"]
    if "actionId" in keys:
        if a.action_id is None:
            raise SystemExit("缺少 --action-id")
        inp["actionId"] = a.action_id
    if "status" in keys and route_name == "actions.setStatus":
        if not a.status_value:
            raise SystemExit("缺少 --status-value（suggested|saved|accepted|dismissed|archived）")
        inp["status"] = a.status_value
    if route_name in ("keywords.addCustomKeyword", "keywords.reviewKeywordOnce"):
        if not a.keyword:
            raise SystemExit("缺少 --keyword")
        inp["keyword"] = a.keyword
    if route_name == "keywords.setKeywordStatus":
        if a.keyword_id is None or not a.status_value:
            raise SystemExit("缺少 --keyword-id / --status-value（active|disabled）")
        inp["keywordId"] = a.keyword_id
        inp["status"] = a.status_value
    if route_name == "intelligence.requestCollection":
        if not a.collection_type:
            raise SystemExit("缺少 --collection-type（seo_collection|exposure_collection）")
        inp["type"] = a.collection_type
    if route_name in ("memos.create",):
        if a.content is None:
            raise SystemExit("缺少 --content")
        inp["content"] = a.content
    if route_name == "memos.update":
        if a.memo_id is None or a.content is None:
            raise SystemExit("缺少 --memo-id / --content")
        inp["memoId"] = a.memo_id
        inp["content"] = a.content
    if "reviewId" in keys:
        if a.review_id is None:
            raise SystemExit("缺少 --review-id（必须 >0）")
        inp["reviewId"] = a.review_id
    if "topicReportId" in keys:
        inp["topicReportId"] = a.topic_report_id if a.topic_report_id is not None else None
        if inp["topicReportId"] is None:
            if route_name == "topics.getVideoEvidence":
                raise SystemExit("缺少 --topic-report-id（先跑 `topics` 拿 id）")
            inp.pop("topicReportId")
    if route_name.startswith("reviews.run"):
        if not a.stage:
            raise SystemExit("缺少 --stage（pre_production|final_packaging）")
        inp["stage"] = a.stage
        if not a.topic_label:
            raise SystemExit("缺少 --topic-label（服务端必填）")
        inp["topicLabel"] = a.topic_label
    if route_name in ("reviews.addTextVersion", "reviews.runTextReview"):
        got = False
        for k in ("brief", "script", "transcript", "title", "creator_channel_id", "description", "chapters"):
            v = getattr(a, k, None)
            if v:
                inp[{"creator_channel_id": "creatorChannelId"}.get(k, k)] = v
                got = True
        if not got:
            raise SystemExit("至少给一项内容：--brief/--script/--transcript/--title/--creator-channel-id/--description/--chapters")
    if route_name in ("reviews.addDocumentVersion", "reviews.runDocumentReview"):
        if not a.file_name or not a.base64_file:
            raise SystemExit("文档审核需要 --file-name 与 --base64-file")
        inp["fileName"] = a.file_name
        inp["mimeType"] = a.mime_type or "application/octet-stream"
        data = open(a.base64_file, "rb").read()
        import base64 as _b64
        inp["size"] = len(data)
        inp["base64"] = _b64.b64encode(data).decode()
        inp["documentField"] = a.document_field or "script"
    if route_name.startswith("dashboard."):
        inp["days"] = a.days or 90
        inp["page"] = a.page or 1
        inp["pageSize"] = a.page_size or 10
        if a.brand_filter:
            inp["brandFilter"] = a.brand_filter
    if route_name == "content.listVideos":
        inp["limit"] = a.limit or 50
        inp["offset"] = a.offset or 0
    if route_name == "reviews.getById" and inp.get("reviewId") in (0, None):
        raise SystemExit("reviewId 必须 >0（传 0 → 400 too_small）")
    if route_name == "videos.getInsight":
        if a.campaign_id is None or a.video_collab_id is None:
            raise SystemExit("缺少 --campaign-id / --video-collab-id")
        inp["campaignId"] = a.campaign_id
        inp["videoCollabId"] = a.video_collab_id
        inp.pop("brandId", None)
    if route_name == "videos.getChannelInterests":
        inp["channelId"] = a.channel_id or ""
        inp.pop("brandId", None)
    if "campaignId" in keys and route_name not in ("videos.getInsight",):
        if a.campaign_id is None:
            raise SystemExit("缺少 --campaign-id（Creator Tracker 的 campaignId；Halliday 实测为 660001）")
        inp["campaignId"] = a.campaign_id
        inp.pop("brandId", None)
    # 只保留注册表声明的键（防手抖多传）
    return {k: v for k, v in inp.items() if k in keys or k not in ("brandId",)} if keys else inp


PROBE_INVALID = {  # `--shape` 用的**类型非法**入参：让服务端回 zod 路径，零副作用
    "intelligence.requestCollection": {"type": "__probe__"},
    "actions.setStatus": {"actionId": 99999999, "status": "__probe__"},
    "keywords.setKeywordStatus": {"keywordId": 99999999, "status": "__probe__"},
    "reviews.runTextReview": {"stage": "__probe__"},
    "reviews.runDocumentReview": {"stage": "__probe__"},
}
PROBE_DROP = {  # 直接删掉必填键：暴露 required 列表，同样零副作用
    "keywords.addCustomKeyword": ["keyword"],
    "keywords.reviewKeywordOnce": ["keyword"],
    "memos.create": ["content"],
}


def probe_shape(d, route_name, a, scope):
    """形状定位：类型非法/缺键 ⇒ 服务端 400 + zod 路径；**不产生副作用**。"""
    route = full_route(route_name)
    keys = list(ROUTES[route_name]["keys"])
    inp = {"categoryProfileId": scope["categoryProfileId"], "brandId": scope["brandId"],
           "categoryId": scope["categoryId"], "country": scope["country"]}
    if route_name == "memos.create" or "memoId" in keys:
        inp = {"brandId": scope["brandId"]}
    if route_name in ("reviews.addTextVersion",) or "reviewId" in keys:
        inp["reviewId"] = 99999999
    if route_name == "topics.startVideoEvidence":
        inp["topicReportId"] = 99999999
    inp.update(PROBE_INVALID.get(route_name, {}))
    for k in PROBE_DROP.get(route_name, []):
        inp.pop(k, None)
    st, body = raw_request(d, route, inp, "POST")
    print("--shape（零副作用）：POST %s" % route)
    print("  入参：%s" % json.dumps(inp, ensure_ascii=False))
    print("  HTTP %s" % st)
    print("  原始错误体：%s" % body[:1000])
    return 0


# ------------------------------------------------------------------ 子命令
#: `--json` 模式下**不能同用**的开关：它们的输出是人读诊断，凑不出"恰好一个 JSON 文档"。
JSON_MODE_CONFLICTS = ("raw", "shape", "routes", "self_test")


def json_mode_guard(a, names):
    """`--json` 的单文档前提（TICKET-168）：一次调用只允许**一个**数据出口。

    为什么必须在**发请求之前**挡住：`--json` 的契约是 stdout 有且只有**一个** JSON 文档。
    多子命令会出多份信封；`--raw`／`--shape`／`--routes`／`--self-test` 出的全是人读文本。
    这两种情形唯一诚实的做法是**明确报入参错误**（退出码 2），而不是悄悄再吐一份文档。
    """
    if not a.json:
        return
    bad = ["--" + f.replace("_", "-") for f in JSON_MODE_CONFLICTS if getattr(a, f, False)]
    if bad:
        raise SystemExit("--json 与 %s 不能同用（前者的契约是 stdout 有且只有一个 JSON 文档，"
                         "后者打的是人读诊断）—— 请二选一" % "、".join(bad))
    todo = [n for n in names if n not in ("read", "write")]
    if len(todo) > 1:
        raise SystemExit("--json 模式下一次只能跑一个读子命令（stdout 只能有一个 JSON 文档）；"
                         "请分次调用：%s" % " ／ ".join("%s --json" % n for n in todo))


def run_read(d, route_name, a, scope, quiet=False):
    route = full_route(route_name)
    inp = build_input(route_name, a, scope)
    if a.raw:
        st, body = raw_request(d, route, inp, "GET")
        print("GET %s → HTTP %s" % (route, st))
        print(body[:4000])
        return json.loads(body) if st == 200 else None
    try:
        v = d.query(route, inp)
    except Exception as e:  # noqa: BLE001
        st, body = raw_request(d, route, inp, "GET")
        # 错误文字一律走 stderr：`--json` 时 stdout 只能有那**一个** JSON 文档；人读模式也一样
        # —— stdout 只放数据，免得调用方把错误文字当成成功结果（这正是 TICKET-168 的那条 exit 0）。
        # `--json` 时 stderr 由出口层收敛成一句人话，所以原始报文只在该模式下不打，免得淹掉那句话。
        if not a.json:
            print("请求失败：GET %s → 原始 HTTP %s" % (route, st), file=sys.stderr)
            print("原始错误体：%s" % body[:1200], file=sys.stderr)
        raise daniel_io.ServerError(route, st, body, cause=e)
    if not quiet:
        if a.json:
            # 机器口：stdout 有且只有一个 JSON 文档（读结果信封，含条数与分页游标）；
            # 人读的入参/形状提示走 stderr，免得调用方还要从提示行里挑 JSON。
            print("GET %s  入参=%s" % (route, json.dumps(inp, ensure_ascii=False)), file=sys.stderr)
            daniel_io.emit(read_envelope(
                route, redact(v), inp, method="GET",
                kind=read_paging_kind(route_name),
                limit=a.limit, offset=a.offset or 0,
                page=a.page, page_size=a.page_size,
                max_chars=a.max_chars))
        else:
            print("GET %s  入参=%s" % (route, json.dumps(inp, ensure_ascii=False)))
            print("  形状=%s" % json.dumps(shape_of(v), ensure_ascii=False))
            print("  摘要=%s" % json.dumps(redact(v), ensure_ascii=False)[:1500])
            print("  全量（不截断、含分页游标）请用 --json：本行只是人读摘要")
    return v


def cmd_write(d, sub, a, scope):
    route_name = WRITE_SUBCMDS[sub]
    route = full_route(route_name)
    meta = ROUTES[route_name]
    if a.shape:
        return probe_shape(d, route_name, a, scope)
    try:
        inp = build_input(route_name, a, scope)
    except SystemExit as e:
        if a.run:
            raise
        print("[plan] 入参未齐（%s）—— 这是 dry-run 的预期结果；补齐参数后加 --run 才发写请求。" % e)
        return 0
    print("=" * 72)
    print("[%s] %s %s" % ("RUN" if a.run else "DRY-RUN", meta["method"], route))
    print("  kind      : %s" % meta["kind"])
    print("  入参      : %s" % json.dumps(redact(inp), ensure_ascii=False))
    if meta.get("enum"):
        for k, vs in meta["enum"].items():
            print("  取值域    : %s ∈ %s" % (k, vs))
    if meta.get("note"):
        print("  纪律注记  : %s" % meta["note"])
    print("  回读路由  : %s" % (full_route(VERIFY_ROUTE[route_name]) if route_name in VERIFY_ROUTE else "—"))
    if not a.run:
        print("  ⇒ 未执行（写/触发类默认 dry-run；确认无误后加 --run）")
        return 0
    st, body = raw_request(d, route, inp, "POST")
    print("  HTTP %s" % st)
    try:
        parsed = json.loads(body)
    except Exception:  # noqa: BLE001
        parsed = None
    print("  返回      : %s" % json.dumps(redact(parsed if parsed is not None else body[:1500]),
                                        ensure_ascii=False)[:2000])
    if st != 200:
        print("  🔴 写请求失败 —— 原始错误体已打印，**不要当成已执行**")
        return 1
    if a.no_verify or route_name not in VERIFY_ROUTE:
        return 0
    print("  ---- 回读核对：GET %s" % full_route(VERIFY_ROUTE[route_name]))
    run_read(d, VERIFY_ROUTE[route_name], a, scope, quiet=False)
    return 0


def cmd_routes(a):
    print("| 路由（真实） | 方法 | 类 | 入参键 | 说明 |")
    print("|---|---|---|---|---|")
    for k in ROUTES:
        r = ROUTES[k]
        print("| `%s` | %s | %s | %s | %s |" % (
            full_route(k), r["method"], {"read": "读", "write": "写", "trigger": "触发"}[r["kind"]],
            "`" + ", ".join(r["keys"]) + "`" if r["keys"] else "（空对象 `{}`）", r.get("note", "")))
    return 0


# ------------------------------------------------------------------ 离线自检
def _self_test():
    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    # 1. 路由前缀（ticket 清单里的短名实际都带 actionCenter. 前缀）
    ck("prefix_actionCenter", full_route("actions.list") == "actionCenter.actions.list"
       and full_route("memos.list") == "actionCenter.memos.list"
       and full_route("topics.list") == "actionCenter.topics.list")
    ck("prefix_ct", full_route("videos.list") == "ct.videos.list"
       and full_route("videos.getInsight") == "ct.videos.getInsight"
       and full_route("videos.getChannelInterests") == "ct.videos.getChannelInterests")
    # 2. ticket 清单 25 条路由全部在注册表里
    ticket = ["intelligence.refresh", "intelligence.requestCollection", "intelligence.status",
              "actions.list", "actions.observationTimeline", "actions.setStatus",
              "keywords.listKeywords", "keywords.addCustomKeyword", "keywords.setKeywordStatus",
              "keywords.reviewKeywordOnce", "memos.list", "memos.create", "memos.update",
              "reviews.list", "reviews.getById", "reviews.addDocumentVersion", "reviews.addTextVersion",
              "reviews.runDocumentReview", "reviews.runTextReview", "topics.list", "topics.getSharedCore",
              "topics.getVideoEvidence", "topics.startVideoEvidence", "dashboard.getTopCreators",
              "dashboard.getTopContent", "content.listVideos", "content.getStats", "videos.list",
              "videos.getInsight", "videos.getChannelInterests"]
    missing = [t for t in ticket if t not in ROUTES]
    ck("registry_covers_ticket", not missing, "缺：%s" % missing)
    # 3. 读类全部 GET、写/触发全部 POST（读类用错方法 ⇒ 405）
    bad = [k for k, v in ROUTES.items() if (v["kind"] == "read") != (v["method"] == "GET")]
    ck("method_matches_kind", not bad, "不一致：%s" % bad)
    # 4. scope 四键齐全（actionCenter 系）
    need = [k for k, v in ROUTES.items() if v.get("prefix") == "actionCenter" and k != "memos.list"
            and set(SCOPE4) - set(v["keys"]) and k not in ("memos.list",)]
    ck("scope4_present", all(set(SCOPE4) <= set(ROUTES[k]["keys"])
                             for k in ROUTES if ROUTES[k].get("prefix") == "actionCenter"
                             and k not in ("memos.list", "memos.create", "memos.update")
                             and k in ("actions.list", "keywords.listKeywords", "reviews.list", "topics.list")),
       str(need))
    # 5. 枚举值与 bundle 一致
    ck("enum_status", ROUTES["actions.setStatus"]["enum"]["status"] ==
       ["suggested", "saved", "accepted", "dismissed", "archived"])
    ck("enum_keyword_status", ROUTES["keywords.setKeywordStatus"]["enum"]["status"] == ["active", "disabled"])
    ck("enum_collection", ROUTES["intelligence.requestCollection"]["enum"]["type"] ==
       ["seo_collection", "exposure_collection"])
    ck("enum_stage", ROUTES["reviews.runTextReview"]["enum"]["stage"] == ["pre_production", "final_packaging"])
    # 6. memos 入参（bundle：memos.create({brandId,content}) / memos.update({memoId,content})）
    ck("memo_keys", ROUTES["memos.create"]["keys"] == ("brandId", "content")
       and ROUTES["memos.update"]["keys"] == ("memoId", "content"))
    # 7. actions.observationTimeline 用 actionId（不是 id）
    ck("timeline_key", "actionId" in ROUTES["actions.observationTimeline"]["keys"])
    ck("keyword_status_key", "keywordId" in ROUTES["keywords.setKeywordStatus"]["keys"])
    ck("topic_evidence_key", "topicReportId" in ROUTES["topics.getVideoEvidence"]["keys"])
    # 8. dashboard 用 days（不是 windowDays）
    ck("dashboard_keys", "days" in ROUTES["dashboard.getTopCreators"]["keys"]
       and "days" in ROUTES["dashboard.getTopContent"]["keys"])
    # 9. content.* 分页键
    ck("content_keys", ROUTES["content.listVideos"]["keys"] == ("brandId", "limit", "offset"))
    # 10. brands.list 是空对象入参（注册表不声明键 ⇒ 传 {}）
    ck("brands_empty_object", ROUTES["brands.list"]["keys"] == ())
    # 11. dry-run 守卫：不带 --run 不得触网
    class _NS:
        run = False
    calls = []

    class _FakeD:
        def query(self, *x, **y):
            calls.append(("query", x))
            return []

        def mutate(self, *x, **y):
            calls.append(("mutate", x))
            return {}
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--shape", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--raw", action="store_true")
    ap.add_argument("--no-verify", action="store_true")
    ns = ap.parse_args([])
    for f in ("action_id", "status_value", "keyword", "keyword_id", "collection_type", "content", "memo_id",
              "review_id", "topic_report_id", "stage", "topic_label", "brief", "script", "transcript", "title",
              "creator_channel_id", "description", "chapters", "file_name", "base64_file", "mime_type",
              "document_field", "days", "page", "page_size", "brand_filter", "limit", "offset",
              "campaign_id", "video_collab_id", "channel_id", "status"):
        setattr(ns, f, None)
    scope = {"categoryProfileId": 1, "brandId": 2, "categoryId": 3, "country": "US"}
    import contextlib as _ctx
    import io as _io
    with _ctx.redirect_stdout(_io.StringIO()):
        cmd_write(_FakeD(), "memos-create", ns, scope)
    ck("dryrun_no_network", calls == [], "dry-run 竟然调用了网络：%s" % calls)
    # 12. --schema 探针不落真实数据（只由调用方显式触发；此处只验证探针表存在且覆盖三类）
    ck("probe_invalid_table", set(PROBE_INVALID) >= {"actions.setStatus", "reviews.runTextReview",
                                                     "intelligence.requestCollection"}
       and set(PROBE_DROP) >= {"memos.create", "keywords.addCustomKeyword"})
    # 13. 脱敏：cookie/token 类键被打码
    ck("redact", redact({"cookie": "app_session_id=abc", "token": "xyz", "name": "Halliday"})["cookie"] == "<redacted>"
       and redact({"cookie": "x"})["cookie"] == "<redacted>")
    # 14. shape_of 描述
    ck("shape_of", shape_of({"a": [1, 2], "b": 1, "c": {}, "d": None}) ==
       {"a": "list[2]", "b": "int", "c": "dict", "d": "NoneType"})
    # 15. 缺必填 ⇒ 抛错而不是猜
    try:
        build_input("memos.create", ns, scope)
        ck("missing_required_raises", False, "没抛错")
    except SystemExit:
        ck("missing_required_raises", True)
    # 16. 写子命令都登记了回读路由
    ck("verify_routes_registered", all(ROUTES[k]["kind"] == "write" or k in VERIFY_ROUTE or
                                       ROUTES[k]["kind"] == "trigger"
                                       for k in WRITE_SUBCMDS.values()))
    # 17. brands.list 是 workspace 维度：数字 id 在 brands.list 里找不到时，用 sovCategories 兜底
    class _WsD:
        calls = []

        def get_brand(self, bid):
            _WsD.calls.append("brands.getById")
            return None                                    # 模拟活跃工作区里看不到该品牌

        def query(self, route, inp=None):
            _WsD.calls.append(route)
            if route == "sovCategories.getByBrand":
                return [{"id": 360001, "assocId": 2310001, "name": "X", "operatingMarkets": ["US"]}]
            if route == "auth.me":
                return {"activeWorkspaceId": 999}
            return None
    b = resolve_brand(_WsD(), "3690002")
    ck("brand_id_cross_workspace", b.get("id") == 3690002 and "sovCategories.getByBrand" in _WsD.calls)
    try:
        resolve_brand(_WsD(), "NoSuchBrand")
        ck("brand_name_without_index_refuses", False, "没抛错")
    except SystemExit as e:
        ck("brand_name_without_index_refuses", "resolve_brand_ref" in str(e) or "brandId" in str(e), str(e)[:60])
    # 18. 写类默认 dry-run 的文案存在
    ck("dryrun_flag_doc", "默认 `--dry-run`" in __doc__ or "默认 --dry-run" in __doc__)
    # 19～23. 读结果信封（TICKET-150）：完整、合法、可翻页、截断必被标注
    rows = [{"action": {"id": i, "title": "t%d" % i, "blob": "x" * 200}} for i in range(40)]
    env_full = read_envelope("actionCenter.actions.list", rows, {"brandId": 1}, kind="offset")
    ck("envelope_shape", list(env_full) == ["schema", "route", "method", "input", "filter", "total",
                                            "returned", "result", "paging", "truncated",
                                            "truncatedReason"] and env_full["schema"] == READ_SCHEMA,
       str(list(env_full)))
    ck("envelope_filter_echo",
       read_envelope("r", [], {"statuses": ["suggested"]})["filter"]["echo"] == {"statuses": ["suggested"]}
       and read_envelope("r", [], {})["filter"]["excludedIrrelevant"] is None)
    ck("envelope_full_no_truncate", env_full["total"] == 40 and env_full["returned"] == 40
       and env_full["truncated"] is False and env_full["paging"]["hasMore"] is False)
    env_lim = read_envelope("actionCenter.actions.list", rows, {}, kind="offset", limit=5)
    env_next = read_envelope("actionCenter.actions.list", rows, {}, kind="offset",
                             limit=5, offset=5)
    ck("envelope_page_cursor", env_lim["returned"] == 5 and env_lim["truncated"] is True
       and env_lim["paging"]["nextCursor"] == 5 and env_lim["truncatedReason"]
       and env_next["result"][0]["action"]["id"] == 5)
    env_budget = read_envelope("actionCenter.actions.list", rows, {}, kind="offset",
                               max_chars=3000)
    ck("envelope_budget_annotated",
       0 < env_budget["returned"] < 40 and env_budget["truncated"] is True
       and env_budget["paging"]["nextCursor"] == env_budget["returned"]
       and len(_json_text(env_budget)) <= 3000 and isinstance(env_budget["result"], list))
    ck("envelope_no_silent_cut", read_envelope("actionCenter.actions.list", rows, {},
                                               kind="offset", max_chars=0)["truncated"] is False
       and read_envelope("r", rows[:10], {}, kind="server-limit", limit=10)["truncated"] is True
       and read_envelope("r", rows[:10], {}, kind="server-limit", limit=100)["truncated"] is False)
    page_env = read_envelope("r", {"items": [{"a": i} for i in range(50)], "total": 412}, {},
                             kind="server-page", page=1, page_size=50)
    ck("envelope_server_page", page_env["total"] == 412 and page_env["returned"] == 50
       and page_env["paging"]["totalPages"] == 9 and page_env["paging"]["nextPage"] == 2
       and page_env["truncated"] is True)
    # 24. 错误出口契约（TICKET-168）：四条失败路径 ＋ 一条真阴性，跑真进程、断"恰好一个文档"。
    for name, passed, detail in _error_contract_checks():
        ck(name, passed, detail)
    ok = sum(1 for _, p, _ in checks if p)
    for name, p, detail in checks:
        print("%s %s%s" % ("PASS" if p else "FAIL", name, "" if p else "  <- " + detail))
    print("self-test: %d/%d" % (ok, len(checks)))
    return ok == len(checks)


# ------------------------------------------------------------------ 错误出口契约（TICKET-168 · 离线正控）
#: 合成能力目录里的**桩客户端**：定义 `Daniel` 并替换 `urllib.request.urlopen`，
#: 让四条失败路径与成功路径都能**离线**构造（红线：不为造 5xx 去发起任何真实请求／写操作）。
STUB_CLIENT_SOURCE = '''# -*- coding: utf-8 -*-
"""自检夹具：桩 daniel_client.py（TICKET-168）。只在被当作 daniel_intel.py 的兄弟模块载入时生效。"""
import io
import json
import os
import urllib.error
import urllib.request

BASE = "https://stub.invalid"
SCENARIO = os.environ.get("D168_SCENARIO", "ok")

#: 逐字复刻真实 400 的形状：zod 的问题数组被塞在 error.json.message 这个**字符串**里。
_ISSUES = [{"origin": "number", "code": "too_big", "maximum": 100, "inclusive": True,
            "path": ["pageSize"], "message": "Too big: expected number to be <=100"}]
ZOD_400 = json.dumps([{"error": {"json": {"message": json.dumps(_ISSUES), "code": -32600,
                                         "data": {"code": "BAD_REQUEST", "httpStatus": 400}}}}])
BODY_500 = json.dumps([{"error": {"json": {"message": "boom", "code": -32603,
                                         "data": {"code": "INTERNAL_SERVER_ERROR",
                                                  "httpStatus": 500}}}}])
UNREACHABLE = "[Errno 8] nodename nor servname provided, or not known"


def _fake_urlopen(req, timeout=None, **kw):
    """原始请求（`daniel_intel.raw_request` 走的就是它）一律不发网络。"""
    if SCENARIO == "usage400":
        raise urllib.error.HTTPError(BASE, 400, "Bad Request", {}, io.BytesIO(ZOD_400.encode()))
    if SCENARIO == "server500":
        raise urllib.error.HTTPError(BASE, 500, "Internal Server Error", {},
                                     io.BytesIO(BODY_500.encode()))
    raise urllib.error.URLError(UNREACHABLE)


urllib.request.urlopen = _fake_urlopen


class Daniel:
    def __init__(self, verbose=False):
        self.verbose = verbose

    def _headers(self):
        return {}

    def get_brand(self, bid):
        if SCENARIO == "brand404":
            raise RuntimeError("brands.getById 失败: HTTP Error 404: Not Found")
        if SCENARIO == "unreachable":
            raise urllib.error.URLError(UNREACHABLE)
        return {"id": int(bid), "name": "StubBrand"}

    def resolve_brand_ref(self, ref):
        return {"id": 3690002, "name": "StubBrand"}

    def query(self, route, inp=None):
        if route == "sovCategories.getByBrand":
            return [{"id": 360001, "assocId": 2310001, "name": "Stub",
                     "operatingMarkets": ["US"]}]
        if route == "auth.me":
            return {"activeWorkspaceId": 1}
        if SCENARIO in ("usage400", "server500", "unreachable"):
            raise RuntimeError("%s 失败: HTTP Error boom" % route)
        return [{"action": {"id": 1, "title": "t1"}, "topic": {}}]

    def mutate(self, route, inp=None):
        return {}
'''

#: (场景, 期望退出码, 期望 kind[成功为 None], stdout/JSON 里必须出现的字)
ERROR_CONTRACT_CASES = (
    ("usage400", 2, "usage", "每页最多 100 条"),
    ("server500", 1, "internal", "服务端内部错误"),
    ("brand404", 1, "internal", "404"),
    ("unreachable", 1, "internal", "网络不可达"),
    ("ok", 0, None, READ_SCHEMA),
)

#: 人读格式的错误文字标记：这些字符出现在 stdout 就说明"错误文字又被当成数据了"。
ERROR_TEXT_MARKERS = ("失败：", "原始 HTTP", "原始错误体", "Traceback", "🔴", "入参不被接受",
                      "入参不合法", "服务端查不到")


def _doc_count(text):
    """用 `raw_decode` **数** stdout 里有几个 JSON 文档 → `(文档数, 剩余非空白片段)`。

    为什么不能用 `json.loads`：它对"一个文档 ＋ 尾随错误文字"报错、对"两个文档"也报错，
    分不出"几个"—— 而本票要断言的恰是"恰好一个"。
    """
    dec = json.JSONDecoder()
    i = n = 0
    while i < len(text):
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        if i >= len(text):
            break
        try:
            _obj, end = dec.raw_decode(text, i)
        except ValueError:
            return n, text[i:i + 80]
        n += 1
        i = end
    return n, ""


def _error_contract_checks():
    """错误出口的**离线正控**（TICKET-168 验收第 2 条）→ `[(名称, 通过?, 明细)]`。

    做法：在系统临时目录里造一个"合成能力目录"（桩 `daniel_client.py` ＋ 本仪器的副本 ＋
    `daniel_io.py`），跑**真进程**、拿真实的退出码与 stdout／stderr。这样断言的是端到端行为，
    不是某个函数被单独调用时的样子；同时因为桩把 `urlopen` 换掉了，**一个真实请求都不发**。
    """
    import shutil
    import subprocess
    import tempfile
    out = []
    here = os.path.dirname(os.path.abspath(__file__))
    tmp = tempfile.mkdtemp(prefix="daniel-intel-errcontract-")
    try:
        shutil.copy(os.path.join(here, "daniel_io.py"), os.path.join(tmp, "daniel_io.py"))
        shutil.copy(os.path.join(here, "daniel_intel.py"), os.path.join(tmp, "daniel_intel.py"))
        with open(os.path.join(tmp, "daniel_client.py"), "w", encoding="utf-8") as fh:
            fh.write(STUB_CLIENT_SOURCE)
        for scen, want_rc, want_kind, want_text in ERROR_CONTRACT_CASES:
            env = dict(os.environ)
            env["D168_SCENARIO"] = scen
            env.pop("DANIEL_HOME", None)
            p = subprocess.run([sys.executable, os.path.join(tmp, "daniel_intel.py"),
                                "--brand", "3690002", "actions", "--json"],
                               capture_output=True, text=True, timeout=180, env=env,
                               cwd=tmp)
            n, rest = _doc_count(p.stdout)
            label = "errcontract_%s" % scen
            bad = []
            if p.returncode != want_rc:
                bad.append("退出码 %s（期望 %s）" % (p.returncode, want_rc))
            if n != 1 or rest:
                bad.append("stdout 有 %d 个 JSON 文档、尾随=%r" % (n, rest))
            if p.stdout and not p.stdout.lstrip().startswith(("{", "[")):
                bad.append("stdout 不是以 JSON 文档开头（说明前面混进了文本）")
            # 「错误文字不在 stdout」的判据：文档**之外**不许有任何错误文字 —— 恰好一个文档
            # 且尾随为空 ⇒ stdout 整体就是那份 JSON，错误文字只可能出现在它的 error 字段里（应当如此）。
            leaked = [m for m in ERROR_TEXT_MARKERS if m in rest]
            if leaked:
                bad.append("stdout 在 JSON 文档之外混进错误文字：%s" % leaked)
            doc = None
            try:
                doc = json.loads(p.stdout)
            except ValueError as e:
                bad.append("stdout 整体不是合法 JSON：%s" % e)
            if doc is not None:
                if want_kind is None:
                    if doc.get("schema") != READ_SCHEMA:
                        bad.append("成功路径的 schema=%r" % doc.get("schema"))
                else:
                    if doc.get("ok") is not False:
                        bad.append("ok=%r（失败路径必须是 false）" % doc.get("ok"))
                    got = (doc.get("error") or {}).get("kind")
                    if got != want_kind:
                        bad.append("error.kind=%r（期望 %r）" % (got, want_kind))
                    if doc.get("exitCode") != want_rc:
                        bad.append("信封 exitCode=%r（期望 %s）" % (doc.get("exitCode"), want_rc))
                    if want_text not in json.dumps(doc, ensure_ascii=False):
                        bad.append("信封里找不到「%s」" % want_text)
                    hint = (doc.get("error") or {}).get("hint")
                    if not hint:
                        bad.append("失败信封缺 error.hint")
            if not bad and want_kind is not None and "Traceback" in p.stderr \
                    and want_kind == "usage":
                bad.append("用户错误的 stderr 里出现了 traceback")
            out.append((label, not bad, "；".join(bad)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


# ------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(description="Daniel Intelligence 仪器（读类直跑 / 写类默认 dry-run）",
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brand", default="Halliday", help="品牌名或 brandId（默认 Halliday）")
    ap.add_argument("--country", help="市场（默认取该 profile 的 operatingMarkets[0]）")
    ap.add_argument("--category-profile-id", type=int, help="指定 category profile（默认第一个）")
    ap.add_argument("--json", action="store_true",
                    help="输出读结果信封（完整 JSON、脱敏；含条数与分页游标；stdout 只有一个 JSON 文档）")
    ap.add_argument("--raw", action="store_true", help="打原始 HTTP 状态码与响应体（错误体不打码）")
    ap.add_argument("--routes", action="store_true", help="打印路由表（markdown）")
    ap.add_argument("--self-test", action="store_true", help="离线自检（不联网）")
    ap.add_argument("--run", action="store_true", help="写/触发类真正执行（默认 dry-run）")
    ap.add_argument("--shape", action="store_true", help="形状定位：类型非法入参探 zod 路径，零副作用")
    ap.add_argument("--no-verify", action="store_true", help="跳过写后回读")
    # 各路由参数
    ap.add_argument("--action-id", type=int)
    ap.add_argument("--status", nargs="*", help="actions.list 的 statuses 过滤")
    ap.add_argument("--status-value", help="setStatus 的目标状态")
    ap.add_argument("--keyword")
    ap.add_argument("--keyword-id", type=int)
    ap.add_argument("--collection-type", choices=["seo_collection", "exposure_collection"])
    ap.add_argument("--content")
    ap.add_argument("--memo-id", type=int)
    ap.add_argument("--review-id", type=int)
    ap.add_argument("--topic-report-id", type=int)
    ap.add_argument("--stage", choices=["pre_production", "final_packaging"])
    ap.add_argument("--topic-label")
    ap.add_argument("--brief")
    ap.add_argument("--script")
    ap.add_argument("--transcript")
    ap.add_argument("--title")
    ap.add_argument("--creator-channel-id")
    ap.add_argument("--description")
    ap.add_argument("--chapters")
    ap.add_argument("--file-name")
    ap.add_argument("--base64-file", help="文档审核的文件路径（脚本内自行 base64）")
    ap.add_argument("--mime-type")
    ap.add_argument("--document-field")
    ap.add_argument("--days", type=int)
    ap.add_argument("--page", type=int)
    ap.add_argument("--page-size", type=int)
    ap.add_argument("--brand-filter")
    ap.add_argument("--limit", type=int, help="列表读结果最多取几条（本机按窗口取，超出部分由游标续取）")
    ap.add_argument("--offset", type=int, help="列表读结果从第几条开始（配合 --limit 翻页；游标见信封 nextCursor）")
    ap.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS, metavar="上限",
                    help="输出字符预算：默认 0＝不限（不设隐式上限）。设了上限也**只丢整条不切字符**，"
                         "并在信封里带 truncated=true 与 nextCursor")
    ap.add_argument("--campaign-id", type=int)
    ap.add_argument("--video-collab-id", type=int)
    ap.add_argument("--channel-id")
    ap.add_argument("group", nargs="?", help="子命令组：read | write | scope | <子命令>")
    ap.add_argument("sub", nargs="*", help="子命令名（可多个，逐个跑）")
    a = ap.parse_args(argv)
    if a.self_test:
        return 0 if _self_test() else 1
    if a.routes:
        return cmd_routes(a)

    d = client()
    brand = resolve_brand(d, a.brand)
    scope = resolve_scope(d, brand, a.country, a.category_profile_id)

    if a.group == "scope" or (a.group is None and not a.sub):
        print("brand    : %s (%s)" % (brand.get("name"), brand.get("id")))
        print("scope    : %s" % json.dumps(scope, ensure_ascii=False))
        print("read 子命令:")
        print("  " + " ".join(sorted(READ_SUBCMDS)))
        print("write 子命令:")
        print("  " + " ".join(sorted(WRITE_SUBCMDS)))
        return 0

    names = ([a.group] if a.group else []) + list(a.sub)
    json_mode_guard(a, names)                      # `--json` 的单文档前提，发请求前先挡
    rc = 0
    for n in names:
        if n in ("read", "write"):
            continue
        if n in READ_SUBCMDS:
            run_read(d, READ_SUBCMDS[n], a, scope)
        elif n in WRITE_SUBCMDS:
            rc = max(rc, cmd_write(d, n, a, scope) or 0)
        else:
            print("未知子命令：%s（read: %s / write: %s）" % (n, " ".join(sorted(READ_SUBCMDS)),
                                                        " ".join(sorted(WRITE_SUBCMDS))))
            return 2
    return rc


def cli(argv=None):
    """入口包装：**退出码归一 ＋ 失败时恰好一个 JSON 文档**（收口只有这一处，TICKET-168）。

    本仪器原先的毛病（已修）：
      · 读请求失败时把中文错误行打到 **stdout** 并 `return None`，`main()` 又丢弃返回值
        ⇒ **exit 0 ＋ 0 个 JSON 文档**，调用方把错误文字当成成功数据；
      · 品牌编号不存在时只有 traceback ＋ 空 stdout，**没有** `ok=false` 信封。

    现在失败路径全部交给 `daniel_io.cli`：用户错误（缺键、越界、服务端 400/422）→ 2；
    真故障（5xx／不可达／解析失败／404 等本地断不了的情形）→ 1；
    `--json` 时 stdout 有且只有**一个**失败信封，人话走 stderr，traceback 照旧看得见。
    """
    return daniel_io.cli(main, argv)


if __name__ == "__main__":
    sys.exit(cli())
