#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daniel 系统 · Brand Mentions（品牌提及）仪器。

来源：TICKET-132（真源 `tickets/TICKET-132-daniel-brand-mentions.md`）。
路由与入参键**全部取自前端 bundle 调用点**（`.kol-tools/_daniel_bundle/BrandMentions-CbA4Ooa0.js`），
并以真实 HTTP 探测（400 报文的 `path`／`values`）复核取值域；文档见
`docs/marketing/kol/_daniel-integration/02-brand-mentions.md`。

纪律（§15.2／§15.4＋本 Ticket）
  1. **只读优先**：7 条读类路由随时可跑（GET，零副作用）。
  2. **触发类默认 dry-run**：`--run`／`--collect-sources`／`--deep-review`／`--high-attention`／
     `--retry`／`--retry-replay`／`--cancel`／`--delete` 不带 `--yes` **只打印将发出的请求**，不执行。
  3. **删除／取消 must `--yes`**，且先打印"将作用于哪个 jobId"。
  4. **错误体打原始 HTTP**：客户端会吞错误体，本仪器在失败时重放一次原始请求并打印 body。
  5. **凭证纪律**：cookie 由 `daniel_client.Daniel` 管理（`.daniel_session.json`，勿外发）；
     输出一律经 `scrub()`，不打印 cookie／token。

用法
  python3 .kol-tools/daniel_mentions.py --jobs
  python3 .kol-tools/daniel_mentions.py --status <jobId>
  python3 .kol-tools/daniel_mentions.py --results <jobId> [--page 1] [--page-size 50] [--sort-by compositeIndex]
  python3 .kol-tools/daniel_mentions.py --chart <jobId>
  python3 .kol-tools/daniel_mentions.py --top-channels <jobId> [--limit 25]
  python3 .kol-tools/daniel_mentions.py --evidence <jobId> --brand Halliday
  python3 .kol-tools/daniel_mentions.py --export <jobId> [--exclude-official]
  python3 .kol-tools/daniel_mentions.py --run --brand Halliday --days 7 --max-videos 100        # dry-run
  python3 .kol-tools/daniel_mentions.py --run --brand Halliday --days 7 --max-videos 100 --yes  # 真跑（消耗配额）
  python3 .kol-tools/daniel_mentions.py --self-test

读结果出口（TICKET-150）
  `--json` 出**读结果信封**：stdout 有且只有一个 JSON 文档（`daniel.read.v1`：result／total／
  returned／paging／truncated／truncatedReason），人读提示走 stderr。
  · 不再按字符截断（旧版把结果截到 200000 字符 ⇒ 调用方只能拿到半截 JSON）；
  · `--results` 用服务端分页：信封带 total／totalPages／nextPage，触顶/还有后续页时 truncated=true；
  · `--jobs`／`--top-channels` 是服务端按 `--limit` 截取且**不返回总数**：返回条数触顶时
    truncated=true 并说明"可能还有更多、怎么再取"；
  · `--max-chars N` 是唯一的字符预算开关（默认 0＝不限），触发时**只丢整条不切字符**，
    并写明被收窄了多少条与续取游标。
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from daniel_client import BASE, Daniel  # noqa: E402
import daniel_io  # noqa: E402  （TICKET-168：`--json` 出口的唯一收口层）

# ---------------------------------------------------------------- 常量（实测）
READ_ROUTES = [
    "brandMentions.listJobs", "brandMentions.getStatus", "brandMentions.getResults",
    "brandMentions.getChartData", "brandMentions.getTopChannels", "brandMentions.getVideoEvidence",
    "brandMentions.exportMentions",
]
TRIGGER_ROUTES = [  # POST（有副作用／消耗配额）
    "brandMentions.runAnalysis", "brandMentions.collectVideoSources",
    "brandMentions.runVideoDeepReview", "brandMentions.analyzeHighAttention",
]
GUARDED_ROUTES = [  # POST（作用在真实任务上；删除／取消类）
    "brandMentions.cancelJob", "brandMentions.deleteJob", "brandMentions.retryJob",
    "brandMentions.retryVideoReplay",
]
ALL_ROUTES = READ_ROUTES + TRIGGER_ROUTES + GUARDED_ROUTES

SORT_BY = ["compositeIndex", "videoViews", "viewsRatio", "likesRatio", "commentsRatio",
           "erRatio", "authenticityScore", "publishedAt"]
SORT_DIR = ["asc", "desc"]
RELEVANCE_FILTER = ["all", "confirmed", "confirmed_likely"]
FORMAT_FILTER = ["shorts", "long_form", "unknown"]
AUTHENTICITY_FILTER = ["Excellent", "Good", "Fair", "Poor"]
PERFORMANCE_FILTER = ["Strong Outperform", "Outperform", "Average", "Underperform", "Strong Underperform"]
VIDEO_TYPE_FILTER = ["review", "comparison", "tutorial", "unboxing", "sponsored", "news", "mention", "other"]
LANGUAGE_FILTER = ["en", "zh", "ja", "ko", "es", "fr", "de", "pt", "it", "ru", "th", "ar", "hi", "tr"]
SEARCH_MODE = ["brand", "sku"]
REGION_CODES = ["US", "GB", "CA", "AU", "DE", "FR", "JP", "KR", "BR", "IN"]

PAGE_MIN, PAGE_SIZE_MIN, PAGE_SIZE_MAX = 1, 10, 200
DAYS_MIN, DAYS_MAX = 7, 1095
MAXVID_MIN, MAXVID_MAX = 100, 5000

DEFAULT_BRAND_HINT = "Halliday"


class ParamError(ValueError):
    """**用户入参不合法**（越界／错枚举／缺键）：归一成退出码 2 ＋ 一句人话，不打 traceback。

    为什么单列一类：全局退出码语义是 2＝用户错误／1＝内部错误（`data/daniel-cli/README.md`）。
    原先本地校验直接抛 `ValueError`，仪器带 traceback 以 1 退出 ⇒ 上层会把它误判成"我们的故障"
    而不是"你给的值不合法"。真故障（网络、500、解析失败）仍是 1。
    """


# ---------------------------------------------------------------- 纯函数（可离线自检）
def resolve_brand(brand, brands):
    """brand: int/str(数字) 或 名称 → brandId(int)。名字歧义／未命中 → 抛错（不猜）。"""
    if isinstance(brand, bool):
        raise ParamError("品牌参数不能是布尔值")
    if isinstance(brand, int):
        return brand
    s = str(brand).strip()
    if not s:
        raise ParamError("缺少品牌：请给 --brand 品牌名或编号")
    if s.lstrip("-").isdigit():
        return int(s)
    hits = [b for b in (brands or []) if str(b.get("name", "")).strip().lower() == s.lower()]
    if not hits:
        raise ParamError("找不到品牌「%s」；请改用 --brand <品牌编号> 指定" % s)
    if len(hits) > 1:
        ids = ", ".join(str(b.get("id")) for b in hits)
        raise ParamError("品牌名「%s」不唯一（%s）；请改用 --brand <品牌编号> 指定" % (s, ids))
    return int(hits[0]["id"])


def build_run_analysis(brand_id, days=7, max_videos=100, search_mode="brand", sku_terms=None,
                       competitor_name=None, region_code=None, date_from=None, date_to=None):
    """构造 runAnalysis 入参（键与 bundle 调用点一致）；越界**本地拦截**，不发请求。"""
    inp = {"brandId": int(brand_id)}
    if search_mode not in SEARCH_MODE:
        raise ParamError("检索方式只能是 %s" % "、".join(SEARCH_MODE))
    inp["searchMode"] = search_mode
    d = int(days)
    if not (DAYS_MIN <= d <= DAYS_MAX):
        raise ParamError("回溯天数最少 %d 天、最多 %d 天，你给的是 %d" % (DAYS_MIN, DAYS_MAX, d))
    inp["timeRangeDays"] = d
    mv = int(max_videos)
    if not (MAXVID_MIN <= mv <= MAXVID_MAX):
        raise ParamError("最多分析视频条数最少 %d 条、最多 %d 条，你给的是 %d"
                          % (MAXVID_MIN, MAXVID_MAX, mv))
    inp["maxVideos"] = mv
    if search_mode == "sku":
        terms = [t.strip() for t in (sku_terms or []) if str(t).strip()]
        if not terms:
            raise ParamError("按 SKU 检索时必须给出至少 1 个关键词（--sku）")
        inp["skuTerms"] = terms
    if competitor_name:
        inp["competitorName"] = competitor_name
    if region_code:
        if region_code not in REGION_CODES:
            raise ParamError("市场只能是 %s（不给＝全球）" % "、".join(REGION_CODES))
        inp["regionCode"] = region_code
    if date_from:
        inp["dateFrom"] = date_from
    if date_to:
        inp["dateTo"] = date_to
    return inp


def build_get_results(job_id, page=1, page_size=50, sort_by="compositeIndex", sort_dir="desc",
                      relevance_filter="confirmed_likely", performance_filter=None, video_type_filter=None,
                      format_filter=None, authenticity_filter=None, language_filter=None, search=None):
    """构造 getResults 入参；越界／错枚举**本地拦截**（实测 400 的取值域写死在这里）。"""
    p, ps = int(page), int(page_size)
    if p < PAGE_MIN:
        raise ParamError("页码从 %d 起（不能小于 %d）" % (PAGE_MIN, PAGE_MIN))
    if not (PAGE_SIZE_MIN <= ps <= PAGE_SIZE_MAX):
        raise ParamError("每页条数最少 %d 条、最多 %d 条，你给的是 %d"
                          % (PAGE_SIZE_MIN, PAGE_SIZE_MAX, ps))
    if sort_by not in SORT_BY:
        raise ParamError("排序字段只能是 %s" % "、".join(SORT_BY))
    if sort_dir not in SORT_DIR:
        raise ParamError("排序方向只能是 %s" % "、".join(SORT_DIR))
    if relevance_filter not in RELEVANCE_FILTER:
        raise ParamError("相关度筛选只能是 %s" % "、".join(RELEVANCE_FILTER))
    inp = {"jobId": job_id, "page": p, "pageSize": ps, "sortBy": sort_by,
           "sortDir": sort_dir, "relevanceFilter": relevance_filter}
    for k, v, dom in (("performanceFilter", performance_filter, PERFORMANCE_FILTER),
                      ("videoTypeFilter", video_type_filter, VIDEO_TYPE_FILTER),
                      ("formatFilter", format_filter, FORMAT_FILTER),
                      ("authenticityFilter", authenticity_filter, AUTHENTICITY_FILTER),
                      ("languageFilter", language_filter, LANGUAGE_FILTER)):
        if v is None or v == "" or v == "all":
            continue
        if v not in dom:
            raise ParamError("%s 只能是 %s" % (k, "、".join(dom)))
        inp[k] = v
    if search:
        inp["search"] = str(search)
    return inp


def build_export_query(job_id, relevance_filter="confirmed_likely", exclude_official=False, language_filter=None):
    """exportMentions 走**原始 fetch**（bundle 调用点）→ 非 batch 形态 `input={"json":…}`。"""
    inp = {"jobId": job_id, "relevanceFilter": relevance_filter, "excludeOfficial": bool(exclude_official)}
    if language_filter:
        inp["languageFilter"] = language_filter
    return inp


def trigger_allowed(dry_run, yes):
    """触发类执行闸门：默认 dry-run；只有 `--yes` 且未显式 dry-run 才执行。"""
    if dry_run:
        return False
    return bool(yes)


def scrub(text):
    """输出脱敏：cookie／JWT／Bearer／token／邮箱。顺序固定，保证 JWT 与 token 值一定被吃掉。"""
    s = str(text)
    s = re.sub(r"app_session_id=[^;\s\"']+", "app_session_id=<REDACTED>", s)          # 1 会话 cookie
    s = re.sub(r"eyJ[A-Za-z0-9_\-\.]{10,}", "<REDACTED_JWT>", s)                       # 2 JWT 本体
    s = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+", "Bearer <REDACTED>", s)             # 3 Bearer 值
    s = re.sub(r"(?i)\b(cookie|authorization|token)\b\s*[:=]\s*[^\s,;\"']+", r"\1=<REDACTED>", s)  # 4 头值
    s = re.sub(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "<REDACTED_EMAIL>", s)          # 5 邮箱
    return s


def parse_zod_error(body):
    """把 tRPC 400 报文里的 zod issue 列表抽成 [(path, code, detail)]。"""
    out = []
    try:
        raw = json.loads(body)
        if isinstance(raw, list):
            raw = raw[0]
        msg = raw["error"]["json"]["message"]
        issues = json.loads(msg)
        for it in issues:
            path = ".".join(str(x) for x in (it.get("path") or []))
            detail = it.get("values") or it.get("message") or ""
            out.append((path, it.get("code", ""), detail))
    except Exception:
        pass
    return out


# ------------------------------------------------- 读结果信封（TICKET-150）
# 与 `.kol-tools/daniel_intel.py` 同口径、同字段名（两份仪器各自独立，故各自实现一份）：
# 读结果一律**不按字符截断**，改成"整条分页 ＋ 游标 ＋ 显式标注"。
# 🔴 口径纪律：本层只搬运事实（有多少条、取到了哪几条、下一页怎么取、被谁截了），
#    不含任何业务判据（判据在能力层 bundle／Skill 里）。
READ_SCHEMA = "daniel.read.v1"
DEFAULT_MAX_CHARS = 0
NO_TOTAL_NOTE = "接口不返回总数：只有返回条数等于上限时才能推断可能还有更多"
ROW_FIELDS = ("items", "results", "rows", "videos", "channels", "batches")

#: **过滤类**入参键（只用于把"本次真正发给服务端的过滤条件"原样抄进信封，不含任何判据）。
#: 为什么要回显：`relevanceFilter` 默认 `confirmed_likely`，它会把与本品不相关的提及挡在结果外 ——
#: 调用方必须能一眼看出"这份结果是哪个口径"，否则两份数字摆在桌上会以为是数据打架。
FILTER_KEYS = ("relevanceFilter", "performanceFilter", "videoTypeFilter", "formatFilter",
               "authenticityFilter", "languageFilter", "search", "excludeOfficial")


#: 页内条目"唯一编号"的候选字段（按界面实际字段名取，取不到就不判 —— 本层不发明字段）
ROW_ID_FIELDS = ("resultId", "id", "jobId", "videoId", "channelId", "topicReportId",
                 "memoId", "reviewId", "keywordId")


def row_id_field(rows):
    """→ 页内条目的编号字段名（第一行里有哪个就用哪个）；没有就 None。"""
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        for k in ROW_ID_FIELDS:
            if k in rows[0]:
                return k
    return None


def dedup_of_page(rows):
    """页内自检：**返回条数 == 不同编号数** 吗？（TICKET-150 · 总监裁决：不许把重复行交出去）

    → `{"field":…, "rows":n, "unique":m, "ok":bool}`；取不到编号字段 → `ok: null`（不判，不冒充）。
    """
    field = row_id_field(rows)
    if field is None:
        return {"field": None, "rows": len(rows) if isinstance(rows, list) else None,
                "unique": None, "ok": None}
    vals = [r.get(field) for r in rows if isinstance(r, dict)]
    uniq = len({json.dumps(v, ensure_ascii=False, sort_keys=True) for v in vals})
    return {"field": field, "rows": len(vals), "unique": uniq, "ok": uniq == len(vals)}


def filter_echo(inp, result):
    """读到的事实：本次实际使用的过滤条件 ＋ 服务端自报的**任务级**排除条数。

    🔴 语义（2026-10-15 总监裁决）：`excludedIrrelevant` 是**任务级统计** ——
    本次分析共多少条被判为不相关、不计入推广建议；**与本次请求的筛选项无关**
    （实测：`--relevance all` 时服务端**照样**返回 18）。因此：
      · 只被搬运、**不自行计算**；
      · 字段名带 `taskLevel`，不暗示"本次被过滤了多少"；
      · 若要表达"本次请求隐藏了多少" ⇒ 只能用**两个口径的服务端 total 相减**，
        而且必须标明是算术推导（本仪器不做这件事，也不假装它是服务端字段）。
    """
    echo = {k: inp[k] for k in FILTER_KEYS if isinstance(inp, dict) and k in inp}
    excluded = None
    if isinstance(result, dict):
        for k in ("excludedIrrelevant", "excludedCount"):
            v = result.get(k)
            if isinstance(v, int) and not isinstance(v, bool):
                excluded = v
                break
    return {"echo": echo,
            "taskLevelExcluded": {
                "count": excluded,
                "serverField": "excludedIrrelevant",
                "note": "任务级统计：本次分析共有 %s 条被判为不相关、不计入推广建议；"
                        "与本次请求的筛选项无关（本仪器只搬运，不自行计算）" % (
                            excluded if excluded is not None else "?")}}


def _json_text(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1)


def _server_total(result):
    """服务端返回里**自带**的总数（`{results[], total}` 之类）；没有就返回 None —— 不猜。"""
    if isinstance(result, dict):
        for k in ("total", "totalCount", "count"):
            v = result.get(k)
            if isinstance(v, int) and not isinstance(v, bool):
                return v
    return None


def _row_field(result):
    """→ (字段名, 该字段的列表)；不是"字典里挂着列表"就返回 (None, None)。只按字段名取。"""
    if isinstance(result, dict):
        for k in ROW_FIELDS:
            if isinstance(result.get(k), list):
                return k, result[k]
    return None, None


def _fit_count(n, budget, measure):
    """在 0..n 里取满足字符预算的最大条数（**只丢整条，绝不切字符**）。→ (k, 是否收窄)。"""
    if not budget or budget <= 0 or not n:
        return n, False
    if len(_json_text(measure(n))) <= budget:
        return n, False
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(_json_text(measure(mid))) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return lo, True


def read_envelope(route, result, inp=None, method="GET", kind="none",
                  limit=None, offset=0, page=None, page_size=None,
                  max_chars=DEFAULT_MAX_CHARS, note=None):
    """把一次只读结果装成统一信封（与 intel 仪器同字段、同顺序 ⇒ 跨宿主可做键比对）。

    kind（数据的形状，不是业务判据）：
      `none` 单对象或一次返回即全量；`server-limit` 服务端按上限截取且不给总数；
      `server-page` 服务端分页（总数由服务端给）；`offset` 本机按 --limit/--offset 取窗口。
    `truncated` ＋ `truncatedReason`：凡被收窄（用户上限／服务端截取／字符预算）必为 true。
    """
    lim = None if limit is None else max(0, int(limit))
    off = max(0, int(offset or 0))
    budget = int(max_chars or 0)
    field, rows = (None, result) if isinstance(result, list) else _row_field(result)
    server_total = _server_total(result)
    full_count = len(rows) if isinstance(rows, list) else None
    total = server_total if server_total is not None else full_count

    def shrink(obj, k):
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
        stability_note = None
        dedup = dedup_of_page(rows_here) if isinstance(rows_here, list) else \
            {"field": None, "rows": None, "unique": None, "ok": None}
        sort_key = (inp or {}).get("sortBy") or "排序键"
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
            server_pages = _server_pages(obj)
            if server_pages:
                total_pages = server_pages
            cur = int(page) if page else 1
            if server_total is not None and isinstance(total, int) and page_size:
                has_more = cur < (total_pages or cur)
            else:
                has_more = total_pages is not None and cur < total_pages
            if has_more:
                next_page = cur + 1
                how = ("本页 %d 条，共 %s 条、%s 页：用 --page %s 取下一页"
                       % (returned, total, total_pages or "?", next_page))
                reason = "服务端分页：本次只返回第 %s 页（共 %s 页、%s 条）" % (
                    cur, total_pages or "?", total)
                if isinstance(total, int) and total <= PAGE_SIZE_MAX:
                    how += ("；但总数 %d ≤ 单页上限 %d，**建议加 --page-size %d 一次取完**"
                            "（按页翻取在排序键并列时可能重复或遗漏）"
                            % (total, PAGE_SIZE_MAX, PAGE_SIZE_MAX))
            else:
                how = "已是最后一页（共 %s 页、%s 条）" % (total_pages or "?", total)
            if (total_pages or 1) > 1:
                stability_note = ("该列表按 %s 排序，排序键存在并列：**按页翻取可能重复或遗漏条目**；"
                                  "总数不超过单页上限 %d 时请把 --page-size 提到 %d 一页取完，"
                                  "并把 --page 逐页结果按编号去重后再用"
                                  % (sort_key, PAGE_SIZE_MAX, PAGE_SIZE_MAX))
        elif kind == "server-limit":
            how = ("服务端按上限 %s 截取；%s" % (lim, NO_TOTAL_NOTE)) if lim is not None else \
                  "服务端未声明上限"
            if lim is not None and returned is not None and returned >= lim:
                reason = ("服务端按上限截取：本次返回 %d 条＝上限 %s，可能还有更多（%s）"
                          % (returned, lim, NO_TOTAL_NOTE))
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
            "input": redact_input(inp),
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
                "singlePageMax": PAGE_SIZE_MAX,
                "rowsUnique": dedup["unique"], "dedupOk": dedup["ok"],
                "stabilityNote": stability_note,
                "howToContinue": how,
            },
            "truncated": bool(reason),
            "truncatedReason": reason,
        }

    rows_base = base if isinstance(base, list) else (
        base.get(field) if (isinstance(base, dict) and field) else None)
    dedup = dedup_of_page(rows_base)
    if dedup.get("ok") is False:
        # 页内重复 ⇒ **明确标注不可信**（不许把重复行当正常数据交出去）
        note = ("本批 %d 条 ≠ 不同编号数 %d（编号字段 %s）：这批数据不可信，"
                "请按编号去重后再用，或改用一次取全（--page-size 上限内）" %
                (dedup["rows"], dedup["unique"], dedup["field"]))
    n = len(base) if isinstance(base, list) else (
        len(base[field]) if (isinstance(base, dict) and field) else None)
    if n is not None and budget > 0:
        k, hit = _fit_count(n, budget, lambda kk: doc(shrink(base, kk), True))
        while k > 0 and len(_json_text(doc(shrink(base, k), True))) > budget:
            k -= 1
        env = doc(shrink(base, k), hit)
    else:
        env = doc(base, False)
    if note:
        env["notes"] = [note]
    return env


def _server_pages(obj):
    """服务端自报的总页数（`totalPages`）；没有就返回 None。"""
    if isinstance(obj, dict):
        v = obj.get("totalPages")
        if isinstance(v, int) and not isinstance(v, bool):
            return v
    return None


def redact_input(inp):
    """入参进信封前做一次输出脱敏（避免把 cookie／token 类值转述出去）。"""
    if inp is None:
        return None
    return json.loads(scrub(json.dumps(inp, ensure_ascii=False)))


def emit_json(env):
    """机器口唯一出口：stdout 有且只有一个 JSON 文档（读结果信封）。

    走 `daniel_io.emit` 而不是自己 print：出口层要记账"已经出过文档"，失败时才不会**再补一份**
    （第二份文档正是"上层把错误当成成功"的病根，TICKET-168）。
    """
    daniel_io.emit(env)


def describe(obj, depth=0):
    """返回形状描述（键／类型／长度／样例），用于只读探测记录。"""
    pad = "  " * depth
    if isinstance(obj, dict):
        lines = ["%s{ %d keys }" % (pad, len(obj))]
        for k in sorted(obj.keys()):
            v = obj[k]
            lines.append("%s  %s: %s" % (pad, k, describe(v, depth + 1).strip()))
        return "\n".join(lines)
    if isinstance(obj, list):
        if not obj:
            return "%s[] (0)" % pad
        return "%s[ %d ] first→ %s" % (pad, len(obj), describe(obj[0], depth + 1).strip())
    if obj is None:
        return "%snull" % pad
    if isinstance(obj, str):
        return '%sstr("%s")' % (pad, obj[:48])
    return "%s%s(%s)" % (pad, type(obj).__name__, str(obj)[:32])


# ---------------------------------------------------------------- 传输（原始错误体可见）
def call(d, route, inp, method="GET", batch=True):
    """走 daniel_client；失败时重放一次原始请求拿**原始 HTTP 状态码 ＋ 错误体**（§15.5 纪律 ②）。

    `method`：
      · `GET`（默认）——batch 形态的读；
      · `GET_PLAIN` —— **非 batch** 形态的读（`exportMentions` 在前端是原始 fetch，见
        `02-brand-mentions.md` §1.1 `@330578`）；
      · 其它 —— 写／触发（`mutate`）。

    TICKET-168：拿到真回执后抛 `daniel_io.ServerError`，把"退出码该是 2 还是 1"的判断交给
    出口层（入参类 400／422 → 2；5xx／不可达／404 等 → 1）。原先是"任何非 200 都报 2"，
    那会把服务端 5xx 说成"你的参数错" —— 上游据此给出错误的处置建议。
    """
    try:
        if method == "GET":
            return d.query(route, inp)
        if method == "GET_PLAIN":
            return d.query_plain(route, inp)
        return d.mutate(route, inp)
    except Exception as e:  # noqa: BLE001
        status, body = raw_call(d, route, inp, method=method, batch=batch)
        # 原始状态码与错误体随异常交给出口层：它挑一句人话放 stderr，
        # 并把"要改哪个参数／服务端原话是什么"写进 `--json` 的 error.hint
        # —— stdout 因此仍只有那**一个**文档，stderr 也不会被错误体淹掉（TICKET-168）。
        raise daniel_io.ServerError(route, status, body, cause=e)


def raw_call(d, route, inp, method="GET", batch=True):
    """返回 (status, body)。

    batch=True 用 `{"0":{"json":inp}}`；False 用 `{"json":inp}`（exportMentions）。
    `method="GET_PLAIN"` 一律走非 batch（与 `query_plain` 同一形态）。
    """
    if method in ("GET", "GET_PLAIN"):
        use_batch = bool(batch) and method == "GET"
        payload = {"0": {"json": inp}} if use_batch else {"json": inp}
        q = ("batch=1&" if use_batch else "") + "input=" + urllib.parse.quote(json.dumps(payload))
        req = urllib.request.Request(BASE + "/api/trpc/" + route + "?" + q, headers=d._headers())
    else:
        req = urllib.request.Request(BASE + "/api/trpc/" + route, data=json.dumps({"json": inp}).encode(),
                                     method="POST", headers=d._headers())
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def resolve_brand_online(d, brand):
    """id 或名字 → brandId。🔴 名字走**跨工作区索引**（与活跃工作区无关）。"""
    if isinstance(brand, int) or str(brand).strip().lstrip("-").isdigit():
        return int(brand)
    if not hasattr(d, "resolve_brand_ref"):
        raise SystemExit("该客户端无 resolve_brand_ref ⇒ 请直接给 --brand <brandId>")
    return int(d.resolve_brand_ref(str(brand))["id"])


def brand_id_of(d, args):
    """把 `--brand`（id 或名称）解析成 brandId，进程内缓存（名称只查一次 brands.list）。"""
    if getattr(args, "_brand_id", None) is None:
        args._brand_id = resolve_brand_online(d, args.brand)
    return args._brand_id


# ---------------------------------------------------------------- 各子命令
def cmd_jobs(d, args):
    bid = brand_id_of(d, args)
    inp = {"brandId": bid, "limit": int(args.limit)}
    jobs = call(d, "brandMentions.listJobs", inp)
    if args.json:
        emit_json(read_envelope("brandMentions.listJobs", jobs, inp,
                                kind="server-limit", limit=int(args.limit),
                                max_chars=args.max_chars))
        return 0
    print("jobs n=%d (brandId=%s)" % (len(jobs), brand_id_of(d, args)))
    print("（服务端按上限 %s 截取，本次 %d 条；全量请用 --json，信封里带总数与游标）"
          % (args.limit, len(jobs)))
    print("%-38s %-24s %-20s %6s %6s %-7s %s" %
          ("jobId", "status", "createdAt", "days", "maxVid", "mode", "resultSummary"))
    for j in jobs:
        rs = j.get("resultSummary") or {}
        head = "videos=%s channels=%s views=%s" % (rs.get("totalVideos"), rs.get("uniqueChannels"), rs.get("totalViews"))
        print("%-38s %-24s %-20s %6s %6s %-7s %s" % (j.get("jobId"), j.get("status"),
              str(j.get("createdAt"))[:19], j.get("timeRangeDays"), j.get("maxVideos"),
              j.get("searchMode"), head if rs else "-"))
    return 0


def cmd_status(d, args):
    inp = {"jobId": args.job, "brandId": brand_id_of(d, args)}
    s = call(d, "brandMentions.getStatus", inp)
    if args.json:
        emit_json(read_envelope("brandMentions.getStatus", s, inp,
                                max_chars=args.max_chars))
        return 0
    print("jobId=%s\nbrandId=%s status=%s\nprogress=%s%% · %s\n%s\nai: %s/%s (fallback %s, failed %s)\nresultSummary=%s\nwarningSummary=%s\nerrorMessage=%s\nisStuck=%s" % (
              s.get("jobId"), s.get("brandId"), s.get("status"), s.get("progressPercent"),
              s.get("progressStep"), s.get("progressDetail"), s.get("aiCompletedCount"),
              s.get("aiTotalCount"), s.get("aiFallbackCount"), s.get("aiFailedCount"),
              json.dumps(s.get("resultSummary"), ensure_ascii=False), s.get("warningSummary"),
              s.get("errorMessage"), s.get("isStuck")))
    return 0


def cmd_results(d, args):
    inp = build_get_results(args.job, page=args.page, page_size=args.page_size, sort_by=args.sort_by,
                            sort_dir=args.sort_dir, relevance_filter=args.relevance,
                            performance_filter=args.performance, video_type_filter=args.video_type,
                            format_filter=args.format, authenticity_filter=args.authenticity,
                            language_filter=args.language, search=args.search)
    res = call(d, "brandMentions.getResults", inp)
    if args.json:
        emit_json(read_envelope("brandMentions.getResults", res, inp, kind="server-page",
                                page=args.page, page_size=args.page_size,
                                max_chars=args.max_chars))
        return 0
    rows = res.get("results", [])
    print("total=%s page=%s totalPages=%s returned=%d" % (res.get("total"), res.get("page"),
                                                          res.get("totalPages"), len(rows)))
    for r in rows:
        print("  %-8s %-6s %-6s %s | %s | views=%s | %s" % (
            r.get("compositeIndex"), r.get("overallPerformance"), r.get("relevanceLabel"),
            str(r.get("videoFormat")), str(r.get("channelTitle"))[:28], r.get("videoViews"),
            str(r.get("videoTitle"))[:56]))
    return 0


def cmd_chart(d, args):
    inp = {"jobId": args.job}
    c = call(d, "brandMentions.getChartData", inp)
    if args.json:
        emit_json(read_envelope("brandMentions.getChartData", c, inp, max_chars=args.max_chars))
        return 0
    for block in ("performanceDist", "authDist", "videoTypeDist", "promotionDist", "monthlyTrend"):
        v = c.get(block)
        print("%s (%s):" % (block, ("%d rows" % len(v)) if isinstance(v, list) else type(v).__name__))
        for row in (v or [])[:14]:
            print("   ", json.dumps(row, ensure_ascii=False)[:160])
    return 0


def cmd_top_channels(d, args):
    inp = {"jobId": args.job, "limit": int(args.limit), "relevanceFilter": args.relevance}
    rows = call(d, "brandMentions.getTopChannels", inp)
    if args.json:
        emit_json(read_envelope("brandMentions.getTopChannels", rows, inp,
                                kind="server-limit", limit=int(args.limit),
                                max_chars=args.max_chars))
        return 0
    print("channels n=%d (limit=%s relevanceFilter=%s)" % (len(rows), args.limit, args.relevance))
    for r in rows:
        print("  %-13s subs=%-9s videos=%-3s avgComposite=%-6s totalViews=%-10s relevance=%s" % (
            r.get("channelId"), r.get("subscriberCount"), r.get("videoCount"),
            round(float(r.get("avgComposite") or 0), 3), r.get("totalViews"), r.get("relevanceLabel")))
    return 0


def cmd_evidence(d, args):
    inp = {"jobId": args.job, "brandId": brand_id_of(d, args)}
    e = call(d, "brandMentions.getVideoEvidence", inp)
    if args.json:
        emit_json(read_envelope("brandMentions.getVideoEvidence", e, inp, max_chars=args.max_chars))
        return 0
    print("status=%s matching=%s eligible=%s selected=%s analyzed=%s remainingEligible=%s remainingAnalysis=%s batches=%s" % (
        e.get("status"), e.get("matchingCount"), e.get("eligibleCount"), e.get("selectedCount"),
        e.get("analyzedCount"), e.get("remainingEligibleCount"), e.get("remainingAnalysisCount"),
        len(e.get("batches") or [])))
    for v in (e.get("videos") or []):
        st = ((v.get("progress") or {}).get("stages") or {})
        print("  resultId=%-8s %-28s %s" % (v.get("resultId"), str(v.get("videoTitle"))[:28],
              {k: (s or {}).get("status") for k, s in st.items()}))
    return 0


def cmd_export(d, args):
    inp = build_export_query(args.job, relevance_filter=args.relevance,
                             exclude_official=args.exclude_official, language_filter=args.language)
    # 走客户端里那条"非 batch GET"通路（与前端调用点同一形态）；失败时 `call()` 仍会重放一次
    # 原始请求拿状态码与错误体 —— 与改造前 `raw_call` 的报错面一致，但**不再自己发 HTTP**
    # （自己发就绕过了客户端的凭据／错误分类，也没法在离线测试里替换数据源）。
    rows = call(d, "brandMentions.exportMentions", inp, method="GET_PLAIN", batch=False)
    if isinstance(rows, dict):
        # 兼容服务端把行数组再包一层的形态（实测非 batch 直接返回数组；这里只防御）
        rows = rows.get("rows") or rows.get("data") or []
    rows = rows if isinstance(rows, list) else []
    if args.json:
        emit_json(read_envelope("brandMentions.exportMentions", rows, inp, max_chars=args.max_chars))
        return 0
    print("rows n=%d" % len(rows))
    if rows:
        print("keys:", sorted(rows[0].keys()))
        print("sample(masked):", scrub(json.dumps(rows[0], ensure_ascii=False))[:600])
    return 0


def _print_plan(route, inp, method, extra=""):
    print("[dry-run] %s %s" % (method, route))
    print("[dry-run] input = %s" % scrub(json.dumps(inp, ensure_ascii=False)))
    if extra:
        print("[dry-run] %s" % extra)


def cmd_run(d, args):
    brand_id = brand_id_of(d, args)
    inp = build_run_analysis(brand_id, days=args.days, max_videos=args.max_videos,
                             search_mode=args.search_mode, sku_terms=args.sku,
                             competitor_name=args.competitor, region_code=args.region)
    if not trigger_allowed(args.dry_run, args.yes):
        _print_plan("brandMentions.runAnalysis", inp, "POST",
                    "这是**有配额消耗**的真实任务；加 --yes 才执行（实测 1 次约 1 秒返回 jobId）")
        return 0
    r = call(d, "brandMentions.runAnalysis", inp, method="POST")
    print(json.dumps(r, ensure_ascii=False))
    print("jobId=%s" % r.get("jobId"))
    return 0


def cmd_video_trigger(d, args, route, label):
    """collectVideoSources／runVideoDeepReview／analyzeHighAttention：都要 jobId(+brandId)(+resultId)。"""
    brand_id = brand_id_of(d, args)
    inp = {"jobId": args.job, "brandId": brand_id}
    if route != "brandMentions.analyzeHighAttention":
        if args.result_id is None:
            raise SystemExit("%s 需要 --result-id（实测必填；从 --evidence 取）" % route)
        inp["resultId"] = int(args.result_id)
    if not trigger_allowed(args.dry_run, args.yes):
        _print_plan(route, inp, "POST", "%s；加 --yes 才执行" % label)
        return 0
    print(json.dumps(call(d, route, inp, method="POST"), ensure_ascii=False))
    return 0


def cmd_guarded(d, args, route, label):
    """cancelJob／deleteJob／retryJob／retryVideoReplay：默认只打印，`--yes` 才动真实任务。"""
    brand_id = brand_id_of(d, args) if args.brand else None
    inp = {"jobId": args.job}
    if route in ("brandMentions.cancelJob", "brandMentions.deleteJob", "brandMentions.retryJob"):
        pass
    else:
        if args.result_id is None:
            raise SystemExit("%s 需要 --result-id（实测必填）" % route)
        inp.update({"brandId": brand_id, "resultId": int(args.result_id)})
    print("将作用对象：%s jobId=%s%s" % (label, args.job, (" resultId=%s" % args.result_id) if args.result_id else ""))
    if not trigger_allowed(args.dry_run, args.yes):
        _print_plan(route, inp, "POST", "未加 --yes ⇒ 只预览不执行")
        return 0
    print(json.dumps(call(d, route, inp, method="POST"), ensure_ascii=False))
    return 0


def cmd_routes(d, args):
    print("读类（GET，零副作用）：")
    for r in READ_ROUTES:
        print("  ", r)
    print("触发类（POST，消耗配额；默认 dry-run）：")
    for r in TRIGGER_ROUTES:
        print("  ", r)
    print("守卫类（POST，作用在真实任务上；需 --yes）：")
    for r in GUARDED_ROUTES:
        print("  ", r)
    return 0


# ---------------------------------------------------------------- 离线自检（≥10 项）
def self_test():
    checks = []

    def ok(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    # 1 路由表完整性
    ok("路由表=15 条且无重复", len(ALL_ROUTES) == 15 and len(set(ALL_ROUTES)) == 15,
       "n=%d" % len(ALL_ROUTES))
    # 2 触发类默认不执行（dry-run）
    ok("触发闸门：默认 dry-run 不执行", trigger_allowed(True, False) is False and trigger_allowed(True, True) is False)
    # 3 只有 --yes 才执行
    ok("触发闸门：--yes 放行", trigger_allowed(False, True) is True and trigger_allowed(False, False) is False)
    # 4 runAnalysis 最小范围合法
    inp = build_run_analysis(3690002, days=7, max_videos=100)
    ok("runAnalysis 最小入参键", set(inp) == {"brandId", "searchMode", "timeRangeDays", "maxVideos"}, json.dumps(inp))
    # 5 days 越界本地拦截
    try:
        build_run_analysis(3690002, days=6); ok("days<7 被拦", False)
    except ValueError:
        ok("days<7 被拦", True, "实测 min 7")
    try:
        build_run_analysis(3690002, days=1096); ok("days>1095 被拦", False)
    except ValueError:
        ok("days>1095 被拦", True, "实测 max 1095")
    # 6 maxVideos 越界本地拦截
    try:
        build_run_analysis(3690002, max_videos=99); ok("maxVideos<100 被拦", False)
    except ValueError:
        ok("maxVideos<100 被拦", True, "实测 min 100")
    try:
        build_run_analysis(3690002, max_videos=5001); ok("maxVideos>5000 被拦", False)
    except ValueError:
        ok("maxVideos>5000 被拦", True, "实测 max 5000")
    # 7 searchMode=sku 必须带 skuTerms
    try:
        build_run_analysis(3690002, search_mode="sku"); ok("sku 缺 skuTerms 被拦", False)
    except ValueError:
        ok("sku 缺 skuTerms 被拦", True)
    ok("sku 带 skuTerms 通过", build_run_analysis(3690002, search_mode="sku", sku_terms=[" x ", ""])["skuTerms"] == ["x"])
    # 8 regionCode 取值域
    try:
        build_run_analysis(3690002, region_code="ZZ"); ok("regionCode 错值被拦", False)
    except ValueError:
        ok("regionCode 错值被拦", True)
    ok("regionCode 不传＝Global", "regionCode" not in build_run_analysis(3690002))
    # 9 getResults pageSize 下限（实测 <10 → 400）
    try:
        build_get_results("j", page_size=9); ok("pageSize<10 被拦", False)
    except ValueError:
        ok("pageSize<10 被拦", True, "实测 min 10")
    try:
        build_get_results("j", page_size=201); ok("pageSize>200 被拦", False)
    except ValueError:
        ok("pageSize>200 被拦", True, "实测 max 200")
    # 10 排序／过滤枚举
    try:
        build_get_results("j", sort_by="views"); ok("sortBy 错枚举被拦", False)
    except ValueError:
        ok("sortBy 错枚举被拦", True, "实测 8 个取值")
    try:
        build_get_results("j", format_filter="vertical"); ok("formatFilter 错枚举被拦", False)
    except ValueError:
        ok("formatFilter 错枚举被拦", True, "实测 shorts|long_form|unknown")
    ok("格式过滤 all → 不入参", "formatFilter" not in build_get_results("j", format_filter="all"))
    # 11 exportMentions 的键与非 batch 形态
    exp = build_export_query("j", exclude_official=True)
    ok("exportMentions 入参键", set(exp) == {"jobId", "relevanceFilter", "excludeOfficial"}, json.dumps(exp))
    # 12 品牌解析：数字／名称／未命中／歧义／空
    bs = [{"id": 3690002, "name": "Halliday"}, {"id": 1680001, "name": "Tenniix"}]
    ok("品牌解析：数字透传", resolve_brand("3690002", bs) == 3690002)
    ok("品牌解析：名称→id", resolve_brand("halliday", bs) == 3690002)
    try:
        resolve_brand("Nope", bs); ok("品牌未命中抛错", False)
    except ValueError:
        ok("品牌未命中抛错", True)
    try:
        resolve_brand("X", [{"id": 1, "name": "X"}, {"id": 2, "name": "x"}]); ok("品牌歧义抛错", False)
    except ValueError:
        ok("品牌歧义抛错", True)
    # 13 脱敏（判据＝JWT／token 值／邮箱都不落地）
    s = scrub('Cookie: app_session_id=eyJhbGciOi.abc.def; mail a@b.com Authorization: Bearer zzzsecret')
    ok("脱敏 cookie/JWT/邮箱", ("eyJhbGciOi" not in s) and ("zzzsecret" not in s) and ("a@b.com" not in s)
       and ("<REDACTED_EMAIL>" in s) and ("<REDACTED" in s), s[:120])
    ok("脱敏：裸 cookie 头", scrub("app_session_id=eyJx.y.z") == "app_session_id=<REDACTED>",
       scrub("app_session_id=eyJx.y.z"))
    # 14 原始错误体解析
    body = ('[{"error":{"json":{"message":"[\\n  {\\n    \\"code\\": \\"too_small\\",\\n    \\"minimum\\": 10,\\n'
            '    \\"path\\": [\\n      \\"pageSize\\"\\n    ]\\n  }\\n]","code":-32600}}}]')
    iss = parse_zod_error(body)
    ok("400 报文解析出 path", iss and iss[0][0] == "pageSize", str(iss))
    # 15 形状描述器
    d = describe({"a": [1, 2], "b": None})
    ok("形状描述器含键与长度", "a:" in d and "[ 2 ]" in d and "null" in d, d.replace("\n", " ")[:90])
    # 16 守卫类入参键
    ok("守卫类结果路由需要 resultId", "resultId" in {"jobId": 1, "brandId": 2, "resultId": 3})
    # 17 读／触发／守卫三分类不重叠
    ok("三分类互不重叠", not (set(READ_ROUTES) & set(TRIGGER_ROUTES)) and
       not (set(READ_ROUTES) & set(GUARDED_ROUTES)) and not (set(TRIGGER_ROUTES) & set(GUARDED_ROUTES)))
    # 18～21 读结果信封（TICKET-150）：完整、合法、可翻页、截断必被标注
    rows = [{"resultId": i, "videoTitle": "t%d" % i, "blob": "x" * 300} for i in range(40)]
    env_full = read_envelope("r", rows, {"brandId": 1})
    ok("信封字段与顺序固定", list(env_full) == ["schema", "route", "method", "input", "filter",
                                              "total", "returned", "result", "paging", "truncated",
                                              "truncatedReason"] and env_full["schema"] == READ_SCHEMA,
       str(list(env_full)))
    fe = read_envelope("r", {"results": [], "total": 96, "excludedIrrelevant": 18},
                       {"relevanceFilter": "confirmed_likely"})["filter"]
    ok("信封：回显实际过滤条件（口径）",
       fe["echo"] == {"relevanceFilter": "confirmed_likely"}, json.dumps(fe, ensure_ascii=False)[:120])
    ok("信封：被排除条数是**任务级**语义（不暗示「本次」、只搬运）",
       fe["taskLevelExcluded"]["count"] == 18
       and fe["taskLevelExcluded"]["serverField"] == "excludedIrrelevant"
       and "任务级" in fe["taskLevelExcluded"]["note"]
       and "与本次请求的筛选项无关" in fe["taskLevelExcluded"]["note"],
       json.dumps(fe["taskLevelExcluded"], ensure_ascii=False))
    pagedupe = read_envelope("r", [{"resultId": 1}, {"resultId": 1}], {}, kind="offset")
    ok("页内重复 ⇒ 信封明确标注「不可信」（notes ＋ dedupOk=false）",
       pagedupe["paging"]["dedupOk"] is False and pagedupe.get("notes")
       and "不可信" in pagedupe["notes"][0],
       json.dumps({"dedupOk": pagedupe["paging"]["dedupOk"], "notes": pagedupe.get("notes")},
                  ensure_ascii=False))
    env_page2 = read_envelope("r", {"results": [{"resultId": i} for i in range(50)], "total": 412,
                                    "totalPages": 9}, {"sortBy": "compositeIndex"},
                              kind="server-page", page=1, page_size=50)
    ok("翻页不稳定提示（排序键并列 ⇒ 可能重复或遗漏）",
       env_page2["paging"]["stabilityNote"] and "并列" in env_page2["paging"]["stabilityNote"]
       and env_page2["paging"]["singlePageMax"] == PAGE_SIZE_MAX
       and env_page2["paging"]["dedupOk"] is True,
       (env_page2["paging"]["stabilityNote"] or "")[:90])
    env_small = read_envelope("r", {"results": [{"resultId": i} for i in range(96)], "total": 96,
                                    "totalPages": 5}, {"sortBy": "compositeIndex"},
                              kind="server-page", page=1, page_size=20)
    ok("取数收口提示：总数 ≤ 单页上限时建议一次取全",
       "一次取完" in env_small["paging"]["howToContinue"], env_small["paging"]["howToContinue"][:110])
    ok("页内去重：条数 == 不同编号数",
       dedup_of_page([{"resultId": 1}, {"resultId": 2}])["ok"] is True
       and dedup_of_page([{"resultId": 1}, {"resultId": 1}])["ok"] is False
       and dedup_of_page([{"title": "无编号字段"}])["ok"] is None)
    ok("信封：不分页路由一条不丢", env_full["total"] == 40 and env_full["returned"] == 40
       and env_full["truncated"] is False)
    env_budget = read_envelope("r", rows, {}, kind="offset", max_chars=4000)
    ok("信封：字符预算只丢整条且被标注",
       0 < env_budget["returned"] < 40 and env_budget["truncated"] is True
       and env_budget["paging"]["nextCursor"] == env_budget["returned"]
       and len(_json_text(env_budget)) <= 4000 and isinstance(env_budget["result"], list))
    page = {"results": [dict(rows[0], resultId=i) for i in range(50)], "total": 412,
            "page": 1, "totalPages": 9}
    env_page = read_envelope("r", page, {}, kind="server-page", page=1, page_size=50)
    ok("信封：服务端分页带游标", env_page["total"] == 412 and env_page["returned"] == 50
       and env_page["paging"]["totalPages"] == 9 and env_page["paging"]["nextPage"] == 2
       and env_page["truncated"] is True, json.dumps(env_page["paging"], ensure_ascii=False)[:120])
    ok("信封：触顶必标注、未触顶不虚报",
       read_envelope("r", rows[:10], {}, kind="server-limit", limit=10)["truncated"] is True
       and read_envelope("r", rows[:10], {}, kind="server-limit", limit=100)["truncated"] is False)

    passed = sum(1 for _, c, _ in checks if c)
    for name, cond, detail in checks:
        print("%s %s%s" % ("PASS" if cond else "FAIL", name, (" · " + detail) if detail else ""))
    print("self-test: %d/%d" % (passed, len(checks)))
    return 0 if passed == len(checks) else 1


# ---------------------------------------------------------------- CLI
def build_parser():
    p = argparse.ArgumentParser(description="Daniel Brand Mentions 仪器（只读优先／触发类默认 dry-run）")
    g = p.add_mutually_exclusive_group(required=False)
    g.add_argument("--jobs", action="store_true", help="列任务（listJobs）")
    g.add_argument("--status", metavar="JOBID", help="任务状态（getStatus）")
    g.add_argument("--results", metavar="JOBID", help="结果分页（getResults）")
    g.add_argument("--chart", metavar="JOBID", help="图表分布（getChartData）")
    g.add_argument("--top-channels", metavar="JOBID", help="头部频道（getTopChannels）")
    g.add_argument("--evidence", metavar="JOBID", help="视频证据（getVideoEvidence）")
    g.add_argument("--export", metavar="JOBID", help="导出提及（exportMentions）")
    g.add_argument("--run", action="store_true", help="触发分析（runAnalysis，默认 dry-run）")
    g.add_argument("--collect-sources", metavar="JOBID", help="collectVideoSources（默认 dry-run）")
    g.add_argument("--deep-review", metavar="JOBID", help="runVideoDeepReview（默认 dry-run）")
    g.add_argument("--high-attention", metavar="JOBID", help="analyzeHighAttention（默认 dry-run）")
    g.add_argument("--cancel", metavar="JOBID", help="cancelJob（需 --yes）")
    g.add_argument("--delete", metavar="JOBID", help="deleteJob（需 --yes；不可逆）")
    g.add_argument("--retry", metavar="JOBID", help="retryJob（需 --yes）")
    g.add_argument("--retry-replay", metavar="JOBID", help="retryVideoReplay（需 --yes）")
    g.add_argument("--routes", action="store_true", help="打印 15 条路由分类")
    g.add_argument("--self-test", action="store_true", help="离线自检（不联网）")

    p.add_argument("--brand", default=DEFAULT_BRAND_HINT, help="brandId 或品牌名（默认 Halliday）")
    p.add_argument("--job", help="通用 jobId（触发／守卫类）")
    p.add_argument("--result-id", type=int, help="resultId（视频级触发／重放）")
    p.add_argument("--limit", default=10,
                   help="listJobs／topChannels 的服务端上限（触达上限时信封带 truncated=true 与说明）")
    p.add_argument("--days", type=int, default=7, help="runAnalysis timeRangeDays（默认 7＝实测最小）")
    p.add_argument("--max-videos", type=int, default=100, help="runAnalysis maxVideos（默认 100＝实测最小）")
    p.add_argument("--search-mode", default="brand", choices=SEARCH_MODE)
    p.add_argument("--sku", action="append", help="SKU 关键词（可多次）")
    p.add_argument("--competitor", help="competitorName")
    p.add_argument("--region", help="regionCode（%s）" % "|".join(REGION_CODES))
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--page-size", type=int, default=50)
    p.add_argument("--sort-by", default="compositeIndex", choices=SORT_BY)
    p.add_argument("--sort-dir", default="desc", choices=SORT_DIR)
    p.add_argument("--relevance", default="confirmed_likely", choices=RELEVANCE_FILTER)
    p.add_argument("--performance", choices=PERFORMANCE_FILTER)
    p.add_argument("--video-type", choices=VIDEO_TYPE_FILTER)
    p.add_argument("--format", choices=FORMAT_FILTER)
    p.add_argument("--authenticity", choices=AUTHENTICITY_FILTER)
    p.add_argument("--language", choices=LANGUAGE_FILTER)
    p.add_argument("--search", help="标题关键词")
    p.add_argument("--exclude-official", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="触发／守卫类只打印请求（默认行为）")
    p.add_argument("--yes", action="store_true", help="确认执行触发／守卫类（真跑／真取消／真删除）")
    p.add_argument("--json", action="store_true",
                   help="输出读结果信封（完整 JSON、脱敏；含条数与分页游标；stdout 只有一个 JSON 文档）")
    p.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS, metavar="上限",
                   help="输出字符预算：默认 0＝不限（不设隐式上限）。设了上限也**只丢整条不切字符**，"
                        "并在信封里带 truncated=true 与游标")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.self_test:
        return self_test()
    if args.routes:
        return cmd_routes(None, args)
    if not any([args.jobs, args.status, args.results, args.chart, args.top_channels, args.evidence,
                args.export, args.run, args.collect_sources, args.deep_review, args.high_attention,
                args.cancel, args.delete, args.retry, args.retry_replay]):
        # `--json` 时帮助文本走 stderr：stdout 只能有那**一个** JSON 文档（TICKET-168）。
        build_parser().print_help(file=sys.stderr) if args.json else build_parser().print_help()
        return 2
    d = Daniel(verbose=False)
    if args.jobs:
        return cmd_jobs(d, args)
    if args.status:
        args.job = args.status; return cmd_status(d, args)
    if args.results:
        args.job = args.results; return cmd_results(d, args)
    if args.chart:
        args.job = args.chart; return cmd_chart(d, args)
    if args.top_channels:
        args.job = args.top_channels; return cmd_top_channels(d, args)
    if args.evidence:
        args.job = args.evidence; return cmd_evidence(d, args)
    if args.export:
        args.job = args.export; return cmd_export(d, args)
    if args.run:
        return cmd_run(d, args)
    if args.collect_sources:
        args.job = args.collect_sources
        return cmd_video_trigger(d, args, "brandMentions.collectVideoSources", "采集视频来源（消耗配额）")
    if args.deep_review:
        args.job = args.deep_review
        return cmd_video_trigger(d, args, "brandMentions.runVideoDeepReview", "深度复核（消耗配额）")
    if args.high_attention:
        args.job = args.high_attention
        return cmd_video_trigger(d, args, "brandMentions.analyzeHighAttention", "高关注度分析（消耗配额）")
    if args.cancel:
        args.job = args.cancel; return cmd_guarded(d, args, "brandMentions.cancelJob", "停止分析")
    if args.delete:
        args.job = args.delete; return cmd_guarded(d, args, "brandMentions.deleteJob", "删除分析")
    if args.retry:
        args.job = args.retry; return cmd_guarded(d, args, "brandMentions.retryJob", "重试分析")
    if args.retry_replay:
        args.job = args.retry_replay; return cmd_guarded(d, args, "brandMentions.retryVideoReplay", "重放精彩片段")
    return 2


def cli(argv=None):
    """入口包装：**退出码归一 ＋ 失败时恰好一个 JSON 文档**（收口只有这一处，TICKET-168）。

    为什么必须有这一层：仪器直接抛异常时带 traceback 以 1 退出，上层会把它误判成"工具故障"，
    而实际只是"你给的参数不合法"。归一之后：
      · `ParamError`（入参越界／错枚举／缺键）与 `SystemExit("人话")`（对象不存在、多义）→ 2；
      · `SystemExit(整数)`（argparse 的 --help=0／参数错=2）→ 原样透传；
      · 服务端 400／422（本次入参不合法）→ 2；5xx／不可达／解析失败 → 1（真故障要看得见）；
      · `--json` 时失败也**恰好一个** `ok=false` 信封，人话走 stderr，traceback 照旧保留。
      这些都在 `daniel_io.cli` 里实现 —— 本仪器不再自己 catch。
    """
    return daniel_io.cli(main, argv, usage_errors=(ParamError,))


if __name__ == "__main__":
    sys.exit(cli())
