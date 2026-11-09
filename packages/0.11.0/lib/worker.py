"""Daniel 常驻工作进程（插件内部使用）。

为什么需要它：插件每次调用如果都新起一个 python 进程，光是解释器＋客户端构造＋会话读取
就接近 1 秒；而真正慢的是上游接口（1–10 秒）。常驻进程把「进程启动」「会话解析」「HTTP 连接」
都摊薄成一次，并支持**在进程内并行**发多个只读请求，因此单次 KOL 档案从「多次调用 × 每次 2–3 秒」
压到「一次调用、内部并行、约 3–5 秒」。

协议：stdin/stdout 逐行 JSON（NDJSON）。请求 {"id":1,"op":"...","args":{...}}
响应 {"id":1,"ok":true,"data":{...}} 或 {"id":1,"ok":false,"error":{"kind":"...","message":"..."}}
写边界：**只有两条检索通道会提交检索任务**（deep 的 commit 段＝`research_submit`、
open 本身＝`open_submit`：建任务＋开跑）；其余 op 一律只读，本进程从不改名单／品牌／提及等业务数据。
官方库通道（`discovery.searchRoster`）已退役：`roster_search` 现在零发包，只回"该走哪条通道"。
"""
import json
import os
import re
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

# 数据落点：与插件 JS 侧一致——显式 env > 本机已有落点（否则会落到包内 vendor/.daniel-home 而变成"未登录"）
if not os.environ.get("DANIEL_HOME"):
    _cand = os.path.expanduser("~/Library/Application Support/DanielCopilot")
    if os.path.isdir(_cand):
        os.environ["DANIEL_HOME"] = _cand

KOL_DIR = os.environ.get("DANIEL_KOL_DIR") or os.path.join(os.path.dirname(__file__), "..", "vendor", ".kol-tools")
sys.path.insert(0, KOL_DIR)

import daniel_client as dc  # noqa: E402

_client = None

# ───────────── 频道详情：重试加厚 ＋ 进程内缓存（TICKET-222）─────────────
#: 5xx 指数退避（秒）：5 次尝试 / 4 段退避，累计 1+2+4+8 = 15 秒。
#: 为什么在 worker 层再做一遍：worker 用的是**包内 vendor 的客户端**（随包分发，不能跟着
#: 仓库里 `.kol-tools/daniel_client.py` 一起改），而 `discovery.getChannelDetail` 在服务端抖动时
#: 会连续十几秒回 500 —— 老口径「3 次 × 1.2/2.4/3.6 秒 ≈ 7 秒窗口」在这种持续故障下必然全灭，
#: 于是"一次失败"被误读成"这个红人没有数据"。
DETAIL_BACKOFF = tuple(float(x) for x in
                       (os.environ.get("DANIEL_DETAIL_BACKOFF") or "1,2,4,8").split(",") if x.strip())
#: 详情缓存 TTL（秒）：默认 900。worker 是**常驻进程**，同一批红人反复取详情时
#: 缓存命中就是 0 次网络请求（这正是第十批 17 个频道 × 逐条补 handle 最需要的）。
DETAIL_CACHE_TTL = float(os.environ.get("DANIEL_DETAIL_CACHE_TTL") or 900)
_DETAIL_CACHE = {}
_STATS = {"networkRequests": 0, "cacheHits": 0, "retry5xx": 0, "detailCalls": 0}
_LOCK = threading.Lock()

#: 视为"瞬时故障、值得再试"的判据：**两种写法都要认**——客户端抛的 `TRPCError` 描述是
#: `HTTP 500；服务端码 …`，而原生 `urllib.error.HTTPError` 的 str 是 `HTTP Error 500: …`。
_RETRYABLE_RE = re.compile(r"HTTP(?:\s+Error)?\s*(?:码\s*)?(500|502|503|504)\b")


def detail_cache_stats():
    """缓存／重试计数器（全部非空：没有请求就是 0，不留 null）。"""
    now = time.time()
    with _LOCK:
        alive = sum(1 for v in _DETAIL_CACHE.values() if v.get("expiresAt", 0) > now)
        entries = len(_DETAIL_CACHE)
        stats = dict(_STATS)
    stats.update({"entries": alive, "entriesStale": entries - alive,
                  "ttlSeconds": int(DETAIL_CACHE_TTL),
                  "backoffSeconds": list(DETAIL_BACKOFF)})
    return stats


def _cache_get(channel_id):
    with _LOCK:
        hit = _DETAIL_CACHE.get(channel_id)
    if not hit:
        return None
    left = hit.get("expiresAt", 0) - time.time()
    if left <= 0:
        with _LOCK:
            _DETAIL_CACHE.pop(channel_id, None)
        return None
    with _LOCK:
        _STATS["cacheHits"] += 1
    return {"data": hit["data"], "ttlLeft": max(1, int(left))}


def _cache_put(channel_id, data):
    if DETAIL_CACHE_TTL <= 0 or not isinstance(data, dict) or not data:
        return
    with _LOCK:
        _DETAIL_CACHE[channel_id] = {"expiresAt": time.time() + DETAIL_CACHE_TTL,
                                     "data": data}


def _retryable(msg):
    return bool(_RETRYABLE_RE.search(str(msg or "")))


def client():
    global _client
    if _client is None:
        _client = dc.Daniel(verbose=False)
    return _client


def _query(route, payload, retries=None, timeout=None):
    """发一次只读请求。`retries` 交给客户端控制（worker 自己那层重试另有节奏）。"""
    t0 = time.time()
    try:
        if retries is None and timeout is None:
            data = client().query(route, payload)
        elif timeout is None:
            data = client().query(route, payload, retries=retries)
        else:
            data = client().query(route, payload, retries=retries, timeout=timeout)
    except TypeError:
        # 包内 vendor 客户端版本更老（没有 retries/timeout 形参）：退回单次调用，
        # 重试节奏仍由下面 `_detail_fetch` 这一层保证。
        data = client().query(route, payload)
    return {"route": route, "seconds": round(time.time() - t0, 2), "data": data}


def _detail_fetch(channel_id):
    """取一次频道详情：**5 次尝试 / 1-2-4-8 秒指数退避**（只对 5xx 这类瞬时故障重试）。"""
    t0 = time.time()
    attempts = max(1, len(DETAIL_BACKOFF) + 1)
    last = None
    tries = 0
    while tries < attempts:
        tries += 1
        with _LOCK:
            _STATS["networkRequests"] += 1
        try:
            r = _query("discovery.getChannelDetail", {"channelId": channel_id}, retries=1)
            return r, tries
        except Exception as e:                      # noqa: BLE001
            last = e
            if tries < attempts and _retryable(str(e)):
                wait = DETAIL_BACKOFF[min(tries - 1, len(DETAIL_BACKOFF) - 1)]
                with _LOCK:
                    _STATS["retry5xx"] += 1
                time.sleep(wait)
                continue
            break
    raise RuntimeError(json.dumps({
        "kind": "detail_unavailable",
        "seconds": round(time.time() - t0, 1),
        "attempts": tries,
        "maxAttempts": attempts,
        "detail": str(last)[:300],
        "说明": "频道详情接口连续 %d 次失败（5xx 已按 1/2/4/8 秒退避重试，累计约 15 秒）。"
                "这只说明**接口此刻取不到**，不等于这个红人没有数据。"
                % tries,
        "建议": ["过 1–2 分钟再试（服务端瞬时故障）",
                 "先用 handle 解析拿 channelId 确认账号本身可达",
                 "**不要**据此判定「平台没有这个字段」或「这个红人没有数据」"],
    }, ensure_ascii=False))


def op_resolve(args):
    """handle（@xxx 或频道地址）→ channelId。两条路由依次尝试，避免整体失败。"""
    handle = str(args.get("handle") or "").strip()
    last = None
    for route, payload in (
        ("discovery.resolveChannelInput", {"input": handle}),
        ("ct.resolveChannel", {"input": handle}),
    ):
        try:
            r = _query(route, payload)
            d = r["data"] or {}
            cid = d.get("channelId") or (d.get("data") or {}).get("channelId")
            if cid:
                return {"handle": handle, "channelId": cid, "route": route, "seconds": r["seconds"]}
        except Exception as e:  # noqa: BLE001
            last = str(e)
    raise RuntimeError("解析频道失败：%s" % (last or "未返回 channelId"))


def op_detail(args):
    """频道详情：**进程内缓存优先**（命中 → 0 次网络请求）＋ 5xx 指数退避重试。

    缓存键是 channelId，TTL 默认 900 秒（`DANIEL_DETAIL_CACHE_TTL` 可覆盖，0 关闭）。
    返回结构与改造前一致（`route`/`seconds`/`data`），只在后面**追加**三项可选说明：
    `cacheHit`（本次是否命中缓存）、`cacheTtlSeconds`（缓存有效期）、`attempts`（本次用了几次尝试）。
    """
    cid = str(args.get("channelId") or "").strip()
    if not cid:
        raise RuntimeError("channelId 必填")
    with _LOCK:
        _STATS["detailCalls"] += 1
    hit = _cache_get(cid)
    if hit is not None:
        return {"route": "discovery.getChannelDetail", "seconds": 0.0,
                "data": hit["data"], "cacheHit": True,
                "cacheTtlSeconds": hit["ttlLeft"], "attempts": 0}
    r, attempts = _detail_fetch(cid)
    _cache_put(cid, r.get("data"))
    r["cacheHit"] = False
    r["cacheTtlSeconds"] = int(DETAIL_CACHE_TTL)
    r["attempts"] = attempts
    return r


def op_query(args):
    route = str(args.get("route") or "").strip()
    payload = args.get("input") or {}
    if not route:
        raise RuntimeError("route 必填")
    return _query(route, payload)


COMPACT_FIELDS = (
    "channelId", "title", "subscriberCount", "country", "defaultLanguage",
    "viewCount", "videoCount", "tags", "topics", "joinedDate",
)


def _compact(d):
    """只留业务要看的字段，避免把整包原始 JSON 塞进模型上下文。"""
    if not isinstance(d, dict):
        return d
    out = {}
    for k in COMPACT_FIELDS:
        if k in d and d[k] not in (None, "", [], {}):
            out[k] = d[k]
    stats = d.get("statistics") or d.get("stats")
    if isinstance(stats, dict):
        for k in ("viewCount", "videoCount", "subscriberCount"):
            if k in stats and k not in out:
                out[k] = stats[k]
    for k in ("engagementRate", "averageViews", "medianViews"):
        if isinstance(d.get(k), (int, float)):
            out[k] = d[k]
    return out


def op_insight(args):
    """频道表现与受众（默认近 28 天）：performance / audience(性别·年龄·地区·兴趣)。"""
    cid = str(args.get("channelId") or "").strip()
    if not cid:
        raise RuntimeError("channelId 必填")
    window = str(args.get("timeRange") or "last_28_days")
    return _query("discovery.getChannelInsight", {"channelId": cid, "timeRange": window})


def op_videos(args):
    """频道近期视频（默认 5 条）"""
    cid = str(args.get("channelId") or "").strip()
    if not cid:
        raise RuntimeError("channelId 必填")
    limit = int(args.get("limit") or 5)
    return _query("discovery.getChannelVideos", {"channelId": cid, "limit": limit})


def op_kol_profile(args):
    """KOL 完整档案（一次调用拿全）：解析 → 档案 ＋ 表现与受众 ＋ 近期视频，全部并行。

    表现块的数据源（TICKET-230）：抽屉是拿**视频列表**现算的，不是读 insight。
    所以这里按页面的取数口径拉一批"计算样本"（页面 `pageSize:50`；平台实测只给
    20 条，`limit` 无效，见 TICKET-232），展示条数仍按调用方的 `videos` 裁。
    """
    handle = str(args.get("handle") or "").strip()
    if not handle:
        raise RuntimeError("handle 必填")
    videos_limit = int(args.get("videos") or 5)
    t0 = time.time()
    resolved = op_resolve({"handle": handle})
    cid = resolved["channelId"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_detail = pool.submit(op_detail, {"channelId": cid})
        f_insight = pool.submit(op_insight, {"channelId": cid})
        f_videos = pool.submit(op_videos, {"channelId": cid, "limit": 50})
        detail = f_detail.result()
        insight_error = None
        try:
            insight = f_insight.result()
        except Exception as e:      # noqa: BLE001
            insight = None          # 受众数据拿不到不影响其它块
            insight_error = str(e)[:200]
        try:
            videos = f_videos.result()
        except Exception:
            videos = None
    d = detail.get("data") or {}
    all_videos = (((videos or {}).get("data") or {}).get("videos") or []) or None
    shown = all_videos[:videos_limit] if all_videos else None
    return {
        "handle": handle,
        "channelId": cid,
        "channel": _compact(d),
        # 缺块语义（TICKET-233）：ok=有值／empty=接口正常但没数据（平台未收录）／error=取数失败
        "insightStatus": ("ok" if (insight or {}).get("data")
                          else ("error" if insight_error else "empty")),
        "raw": {                     # 供插件做业务视图，字段都在这里翻译
            "detail": d,
            "insight": (insight or {}).get("data"),
            "insightStatus": ("ok" if (insight or {}).get("data")
                              else ("error" if insight_error else "empty")),
            "videos": shown,         # 展示用（按 videos 参数裁）
            "videosAll": all_videos, # 计算用（页面同源口径，最多 50/实测 20 条）
        },
        "seconds": round(time.time() - t0, 2),
        "blocks": {
            "detail": bool(d),
            "insight": bool((insight or {}).get("data")),
            "videos": bool(all_videos),
        },
    }


# ───────────── 红人检索：两条任务式通道（官方库通道已退役）─────────────
#
# 背景（已核实，不再论证）：YouTube 官方库通道 `discovery.searchRoster` 自 2026-09-14 起 503、
# 2026-09-16 起读超时，**已裁决不再使用**。现在只剩两条任务式通道：
#
#   ① Brand Deep Research：`discovery.startSearchJob` → `discovery.executeSearchJob`
#        → 轮询 `discovery.getSearchJob`（`results[]` 就在任务返回体里）
#        ⇒ 需要品牌上下文（brandId／竞品／品类），**有品牌时走这条**
#   ② AI Open Research：`discovery.expandTopic` → `discovery.search` → 执行 ＋ 轮询
#        ⇒ 自由描述/主题，**无品牌时走这条**
#
# 🔴 两条通道的入参与提交序列**不在这里重写**：全部复用已验证的仪器
#    `vendor/.kol-tools/daniel_search.py`（`deep_payload`／`open_payload`／`start_job`）。
#    本进程只补仪器没有的三件事：
#      ① deep 的**第一步只出计划、不提交**（零写请求，见 `op_research_plan`）；
#      ② 提交后**不阻塞**：建任务＋开跑＋一次只读回读就立刻返回 jobId；
#      ③ 把任务状态读成结构化数据（五档阶段映射在 JS 侧 `lib/research.js`，只做一处）。
CHANNEL_RETIRED_KIND = "channel_retired"
#: open 通道未给品牌时的兜底引用（与仪器 `daniel_search.py` 的默认一致，可显式改）
OPEN_DEFAULT_BRAND = os.environ.get("DANIEL_OPEN_DEFAULT_BRAND") or "Halliday"
#: 自动默认项：expandTopic 每组标签最多取几个（服务端实测每组返回 5 个）
AUTO_SELECTION_MAX = 5
#: 状态回读时最多带多少条候选摘要（完整结果请用检索结果文件／名单，不在这里堆全量）
STATUS_RESULT_MAX = 10


def _search_mod():
    """已验证的检索仪器（同目录 daniel_search.py）：复用其入参口径与提交序列，不重写检索逻辑。"""
    import daniel_search as _ds      # noqa: WPS433（与 worker 一起分发）
    return _ds


def op_roster_search(args):
    """官方库通道**已退役**：不发任何网络请求，直接给出该走哪条通道。

    为什么连 `client()` 都不构造：退役口径必须是"零发包"。一旦这里还去读会话／探接口，
    用户就会在"官方库超时"和"通道已换"之间来回猜（2026-09-14 起 503、09-16 起读超时，
    已裁决不再使用）。
    """
    raise RuntimeError(json.dumps({
        "kind": CHANNEL_RETIRED_KIND,
        "message": "YouTube 官方库通道已停用（2026-09-14 起 503、09-16 起读超时，已裁决不再使用）",
        "该怎么走": [
            "有品牌上下文 → daniel_deep_research（品牌深度研究：先出计划，用户确认后才提交）",
            "无品牌／自由描述 → daniel_open_research（AI 开放研究：自动选默认项并执行）",
            "看进度 → 两条通道都用 daniel_research_status(jobId)",
        ],
        "本次是否发包": "没有（不读会话、不调任何接口）",
    }, ensure_ascii=False))


def _deep_plan_of(args):
    """入参 → 仪器口径的 plan（品牌／检索式／筛选）。缺项在这里就报人话，不发包。"""
    brand = str(args.get("brand") or "").strip()
    query = str(args.get("query") or "").strip()
    if not brand:
        raise RuntimeError("brand 必填（品牌名或品牌编号）：deep 通道要用品牌上下文做检索")
    if not query:
        raise RuntimeError("query 必填（检索式：描述要找什么样的红人）")
    filters = {}
    for key in ("country", "minSubscribers", "maxSubscribers"):
        if args.get(key) not in (None, "", []):
            filters[key] = args[key]
    return {"brand": brand, "deepQuery": query, "filters": filters}


def _job_read(d, job_id):
    """一次只读回读（读不到就返回空 dict：**不把"回读失败"说成"任务不存在"**）。"""
    try:
        back = d.query("discovery.getSearchJob", {"jobId": job_id})
    except Exception:                            # noqa: BLE001
        return {}
    return back if isinstance(back, dict) else {}


def _int_or(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def op_research_plan(args):
    """deep 通道**第一步**：只出计划，不提交（零写请求）。

    只做只读的两件事：解析品牌（`brands.getById`／跨工作区索引）＋ 检索式归一（本地长度校验）。
    **不调** startSearchJob／executeSearchJob ⇒ 不建任务、不写检索记录、不消耗额度。
    """
    ds = _search_mod()
    plan = _deep_plan_of(args)
    built = ds.deep_payload(client(), plan, trim=bool(args.get("trim")))
    b = built["brand"]
    return {
        "channel": "deep",
        "brand": {
            "id": b.get("id"),
            "name": b.get("name"),
            "category": b.get("category"),
            "workspaceId": b.get("workspaceId"),
            "competitors": [c.get("name") for c in (b.get("competitors") or []) if c.get("name")],
        },
        "query": built["query"],
        "queryChars": len(built["query"]),
        "maxQueryChars": ds.MAX_QUERY_LEN,
        "normalizedNote": built["note"],
        "limit": int(args.get("limit") or 10),
        "payloadKeys": sorted(built["payload"].keys()),
        "submitted": False,
    }


def op_research_submit(args):
    """deep 通道**第二步**：真提交（建任务 ＋ 开跑），**不阻塞**。

    提交序列复用仪器 `start_job`；随后**一次只读回读**确认任务真的存在，再立刻返回 jobId。
    任务要跑多久由服务端定：进度交给 `daniel_research_status`，这里不做轮询。
    """
    ds = _search_mod()
    d = client()
    plan = _deep_plan_of(args)
    built = ds.deep_payload(d, plan, trim=bool(args.get("trim")))
    started = ds.start_job(d, "discovery.startSearchJob", built["payload"])
    job_id = started.get("jobId")
    if not job_id:
        raise RuntimeError(json.dumps({
            "kind": "submit_failed",
            "message": "服务端没有返回任务编号（任务可能没建起来）",
            "建议": ["用 daniel_run 跑 [\"search\",\"history\"] 核对检索记录",
                     "稍后重试；检索式过长可先压短（上限 %d 字符）" % ds.MAX_QUERY_LEN],
        }, ensure_ascii=False))
    back = _job_read(d, job_id)
    limit = int(args.get("limit") or 10)
    audit = _audit_deep_commit(built.get("query"), built.get("brand"), built, started, back, job_id, limit)
    return {
        "channel": "deep",
        "jobId": job_id,
        "brand": {"id": built["brand"].get("id"), "name": built["brand"].get("name")},
        "audit": audit,
        "query": built["query"],
        "limit": int(args.get("limit") or 10),
        "status": back.get("status"),
        "progressCompleted": _int_or(back.get("progressCompleted")),
        "progressTotal": _int_or(back.get("progressTotal")),
        "foundCount": _int_or(back.get("foundCount")),
        "execNote": started.get("execNote") or None,
        "readback": bool(back),
    }


def auto_selections(expand):
    """open 通道的「自动默认项」：**不逐项追问**，直接采用 expandTopic 返回的三组标签。

    为什么默认全选：扩写结果本身就是服务端按主题给出的候选角度（实测每组 5 个），
    逐一让用户确认会把"一次检索"拖成四轮问答；用户要改，改的是结果复核，不是提交前拦一道。
    返回里**如实标注来源**：扩写失败／没返回标签时写"没有可用的自动选项"，不编标签。
    """
    raw = expand if isinstance(expand, dict) else {}
    err = raw.get("error")

    def take(key):
        vals = raw.get(key)
        if isinstance(vals, dict):
            vals = vals.get("items") or vals.get("values") or []
        if not isinstance(vals, list):
            return []
        out = []
        for v in vals:
            s = v if isinstance(v, str) else (v.get("name") if isinstance(v, dict) else None)
            s = str(s).strip() if s else ""
            if s and s not in out:
                out.append(s)
        return out[:AUTO_SELECTION_MAX]

    scen, styles, auds = take("scenarios"), take("contentStyles"), take("audiences")
    any_tag = bool(scen or styles or auds)
    if any_tag:
        source = "主题扩写返回的三组标签，自动全选（无需逐项确认；要改直接改结果复核）"
    elif err:
        source = "主题扩写失败，本次没有可用的自动选项（按主题自由检索）"
    else:
        source = "主题扩写没有返回标签，本次没有可用的自动选项（按主题自由检索）"
    return {
        "selections": {"scenarios": scen, "contentStyles": styles, "audiences": auds},
        "source": source,
        "expandError": (str(err)[:200] if err else None),
    }


def _open_defaults_list(args, brand_ref, brand, auto, filters):
    """「自动选了哪些默认项」——逐项列出取值与依据，方便用户复核（这是 open 通道的交付要求）。"""
    def join_or(vals, empty="（扩写未返回）"):
        return "；".join(vals) if vals else empty

    sel = auto["selections"]
    country = filters.get("country")
    min_subs = filters.get("minSubscribers")
    brand_given = str(args.get("brand") or "").strip()
    return [
        {"项": "品牌上下文", "取值": brand.get("name") or brand_ref,
         "依据": "按入参" if brand_given else "未指定品牌 → 沿用默认品牌（%s）" % OPEN_DEFAULT_BRAND},
        {"项": "场景", "取值": join_or(sel["scenarios"]), "依据": auto["source"]},
        {"项": "内容风格", "取值": join_or(sel["contentStyles"]), "依据": auto["source"]},
        {"项": "受众", "取值": join_or(sel["audiences"]), "依据": auto["source"]},
        {"项": "国家", "取值": country or "不限", "依据": "按入参" if country else "未指定 → 不限"},
        {"项": "订阅数下限", "取值": min_subs if min_subs is not None else "不限",
         "依据": "按入参" if min_subs is not None else "未指定 → 不限"},
    ]


def _cli_audit():
    """加载 CLI 的审计模块（**审计口径只有一份**：不在这里自造第二个 jsonl 字段表）。

    插件形态下 `vendor/data/daniel-cli` 与本文件同属一个包；把它加进 sys.path 后
    直接复用 `daniel_cli.audit` 的 `record()`（落点由 `daniel_paths` 解析，
    与 `daniel account audit` 读的是同一个文件）。
    """
    import os as _os
    cli_dir = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..",
                                              "vendor", "data", "daniel-cli"))
    if _os.path.isdir(cli_dir) and cli_dir not in sys.path:
        sys.path.insert(0, cli_dir)
    from daniel_cli import audit as cli_audit   # noqa: WPS433（随包分发的 CLI 模块）
    return cli_audit


def _audit_commit(*, command, action, target, brand, impact, mutation, readback,
                  readback_ok, rollback_note, notes):
    """两条检索通道**提交后**共用的写审计（`daniel account audit` 可见）。

    为什么由 worker 写而不是 JS 写：审计字段表与落点解析都在 CLI 侧（`daniel_cli/audit.py`
    ＋ `daniel_paths`）。在这里调用同一份实现，才能保证"审计里有什么字段"只有一种说法。
    两条通道（open／deep）只有 `command`／`action`／`mutation` 不同，**字段集完全一致**
    （2026-11-08 补齐 deep：此前只有 open 有提交审计，deep 提交后查不到痕迹）。
    """
    try:
        cli_audit = _cli_audit()
        row = cli_audit.record({
            "module": "search",
            "command": command,
            "action": action,
            "target": str(target or "")[:120],
            "brand": brand,
            "impact": impact,
            "dryRun": False,
            "executed": True,
            "ok": True,
            "exitCode": 0,
            "mutation": mutation,
            "readback": readback,
            "readbackOk": readback_ok,
            "rolledBack": False,
            "rollbackNote": rollback_note,
            "notes": notes,
        })
        return {"已落盘": True, "路径": row.get("path"), "时间": row.get("time")}
    except Exception as e:                       # noqa: BLE001
        # 审计写不进去**不改写"任务已提交"这个事实**；但必须如实告诉调用方，不能静默
        return {"已落盘": False, "错误": str(e)[:200],
                "说明": "检索任务已提交，但审计没写进去；请用 `daniel account audit` 核对落点是否可写"}


def _audit_open_commit(topic, brand, built, started, back, job_id):
    """open 通道提交后的审计（`command=open-research-commit`）。"""
    return _audit_commit(
        command="open-research-commit",
        action="提交 AI 开放研究检索任务",
        target=topic,
        brand=(brand or {}).get("name") or (brand or {}).get("id"),
        impact="创建 1 条开放检索任务并立即执行；写 1 条检索记录",
        mutation={"route": "discovery.search",
                  "request": {"topic": built.get("topic"),
                              "brandId": (brand or {}).get("id")}},
        readback={"jobId": job_id,
                  "status": back.get("status"),
                  "execNote": started.get("execNote") or None,
                  "readbackOk": bool(back)},
        readback_ok=bool(back),
        rollback_note="检索任务已提交，没有自动回滚；如需停止请到 Daniel 检索记录里处置",
        notes=["由 daniel_open_research_commit 提交（两段式第二步：先 plan、用户确认后才执行）"],
    )


def _audit_deep_commit(query, brand, built, started, back, job_id, limit=None):
    """deep 通道提交后的审计（`command=deep-research-commit`，字段与 open 逐项对齐）。

    `mutation.request` 记的是**真正提交出去的那几个字段**（`deep_payload` 的 payload 里没有
    `limit`，条数是入参定的），所以 `limit` 单独传进来，不从 payload 猜。
    """
    b = brand or {}
    payload = built.get("payload") if isinstance(built.get("payload"), dict) else {}
    request = {k: payload.get(k) for k in ("brandId", "brandName", "query", "country",
                                           "minSubscribers", "maxSubscribers")
               if payload.get(k) is not None}
    request["limit"] = _int_or(limit, 10)
    return _audit_commit(
        command="deep-research-commit",
        action="提交品牌深度研究检索任务",
        target=query,
        brand=b.get("name") or b.get("id"),
        impact="创建 1 条品牌深度研究任务并立即执行；写 1 条检索记录",
        mutation={"route": "discovery.startSearchJob",
                  "request": request},
        readback={"jobId": job_id,
                  "status": back.get("status"),
                  "progressCompleted": _int_or(back.get("progressCompleted")),
                  "foundCount": _int_or(back.get("foundCount")),
                  "execNote": started.get("execNote") or None,
                  "readbackOk": bool(back)},
        readback_ok=bool(back),
        rollback_note="检索任务已提交，没有自动回滚；如需停止请到 Daniel 检索记录里处置",
        notes=["由 daniel_deep_research_commit 提交（两段式第二步：先 plan、用户确认后才执行）"],
    )


def op_open_submit(args):
    """open 通道：**自动选默认项 ＋ 直接执行**，返回 jobId（不阻塞）。

    默认项来自 `expandTopic`（场景／内容风格／受众），一律回填进 `discovery.search`；
    返回体里逐项列出"自动选了什么＋依据"，用户据此复核，而不是提交前逐项确认。
    """
    ds = _search_mod()
    topic = str(args.get("topic") or "").strip()
    if not topic:
        raise RuntimeError("topic 必填（主题／检索式：想找什么样的红人）")
    brand_ref = str(args.get("brand") or "").strip() or OPEN_DEFAULT_BRAND
    d = client()
    expand = ds.expand_topic(d, topic)
    auto = auto_selections(expand)
    filters = {}
    for key in ("country", "minSubscribers"):
        if args.get(key) not in (None, "", []):
            filters[key] = args[key]
    plan = {"topic": topic, "brand": brand_ref, "selections": auto["selections"], "filters": filters}
    built = ds.open_payload(d, plan, trim=bool(args.get("trim")))
    started = ds.start_job(d, "discovery.search", built["payload"])
    job_id = started.get("jobId")
    if not job_id:
        raise RuntimeError(json.dumps({
            "kind": "submit_failed",
            "message": "服务端没有返回任务编号（开放研究任务可能没建起来）",
            "建议": ["稍后重试；主题过长可先压短（上限 %d 字符）" % ds.MAX_QUERY_LEN,
                     "用 daniel_run 跑 [\"search\",\"history\"] 核对检索记录"],
        }, ensure_ascii=False))
    back = _job_read(d, job_id)
    audit = _audit_open_commit(built.get("topic"), built.get("brand"), built, started, back, job_id)
    return {
        "channel": "open",
        "jobId": job_id,
        "topic": built["topic"],
        "brand": {"id": built["brand"].get("id"), "name": built["brand"].get("name")},
        "audit": audit,
        "autoSelections": auto["selections"],
        "autoSource": auto["source"],
        "expandError": auto["expandError"],
        "defaults": _open_defaults_list(args, brand_ref, built["brand"], auto, filters),
        "status": back.get("status"),
        "progressCompleted": _int_or(back.get("progressCompleted")),
        "progressTotal": _int_or(back.get("progressTotal")),
        "foundCount": _int_or(back.get("foundCount")),
        "execNote": started.get("execNote") or None,
        "readback": bool(back),
    }


def op_research_status(args):
    """读一条检索任务的状态（两条通道通用）。

    返回**原始 status** ＋ 进度数字 ＋ 前 N 条候选摘要；五档阶段映射由 JS 侧
    `lib/research.js::mapResearchStage` 统一做（只做一处，前端左栏与工具返回一致）。
    """
    job_id = str(args.get("jobId") or "").strip()
    if not job_id:
        raise RuntimeError("jobId 必填（daniel_deep_research／daniel_open_research 返回的任务编号）")
    ds = _search_mod()
    d = client()
    job = _job_read(d, job_id)
    if not job:
        raise RuntimeError(json.dumps({
            "kind": "job_not_found",
            "message": "没读到这个任务（任务编号可能不对，或服务端暂时读不到）",
            "建议": ["核对 jobId 后重试", "用 daniel_run 跑 [\"search\",\"history\"] 看最近的任务"],
        }, ensure_ascii=False))
    rows = ds.normalize_results(job.get("results"))
    done = _int_or(job.get("progressCompleted"), len(rows))
    total = _int_or(job.get("progressTotal"))
    pct = _int_or(job.get("progressPercent"))
    if pct is None and total:
        pct = max(0, min(100, int(round(done * 100.0 / total))))
    brief = [{
        "红人": r.get("channelTitle"),
        "频道编号": r.get("channelId"),
        "订阅数": r.get("subscriberCount"),
        "国家": r.get("country"),
        "品类": r.get("category"),
        "均播": r.get("avgViews"),
        "互动率": r.get("engagementRate"),
        "体量档": r.get("tier"),
    } for r in rows[:STATUS_RESULT_MAX]]
    return {
        "jobId": job_id,
        "status": job.get("status"),
        "progressCompleted": done,
        "progressTotal": total,
        "progressPercent": pct,
        "foundCount": _int_or(job.get("foundCount")),
        "resultCount": len(rows),
        "results": brief,
        "resultsTruncated": len(rows) > STATUS_RESULT_MAX,
        "errorMessage": job.get("errorMessage") or None,
        "keywords": job.get("keywords") or None,
    }


def _assert_writable_home():
    """落点可写性预检（TICKET-236）。

    为什么：品牌列表要走索引，而索引会**先联网重建、最后才写盘**——落点不可写时
    用户要等 70+ 秒才看到 "Operation not permitted"。这里先花毫秒级探一次写，
    不可写就直接给出可执行的修法。
    """
    try:
        import daniel_paths as dp   # noqa: WPS433（能力层模块，随 .kol-tools 一起分发）
    except Exception:               # noqa: BLE001
        return                      # 老版本没有这个模块：不阻断
    try:
        h = dp.home(create=True)
    except Exception as e:          # noqa: BLE001
        raise RuntimeError(
            "数据落点不可写，已跳过取数（不会再等索引重建）：%s。"
            "修法：设置 DANIEL_HOME 指向可写目录，或运行 daniel account paths 查看当前落点。" % str(e)[:160]
        )
    probe_dir = os.path.join(h, "cache")
    try:
        os.makedirs(probe_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".write-probe-", dir=probe_dir)
        os.close(fd)
        os.unlink(tmp)
    except Exception as e:          # noqa: BLE001
        raise RuntimeError(
            "数据落点不可写（%s）：%s。修法：设置 DANIEL_HOME 指向可写目录后重试。" % (h, str(e)[:160])
        )


def op_brands(args):
    """某工作区的品牌（实时：直连 brands.list）"""
    _assert_writable_home()
    ws = args.get("workspace")
    t0 = time.time()
    route, brands = client().brands(int(ws) if ws else None)
    return {"workspaceId": int(ws) if ws else None, "route": route, "count": len(brands),
            "brands": [{"id": b.get("id"), "name": b.get("name"), "workspaceId": b.get("workspaceId")} for b in brands],
            "seconds": round(time.time() - t0, 2)}


OPS = {
    "resolve": op_resolve,
    "detail": op_detail,
    "query": op_query,
    "kol_profile": op_kol_profile,
    "insight": op_insight,
    "videos": op_videos,
    "brands": op_brands,
    # 官方库通道已退役（保留 op 名只为把"该走哪条通道"结构化交回调用方；不发任何网络请求）
    "roster_search": op_roster_search,
    # 两条任务式通道：deep 分两段（plan 只出计划／submit 才提交），open 自动选默认项直接执行
    "research_plan": op_research_plan,
    "research_submit": op_research_submit,
    "open_submit": op_open_submit,
    "research_status": op_research_status,
    "detail_cache": lambda args: detail_cache_stats(),
    "ping": lambda args: {"pong": True, "pid": os.getpid()},
}


def _error_of(e):
    """异常 → 错误对象。**结构化错误就地保留 kind**（退役／任务不存在／提交失败等）。

    为什么不在调用方重新解析：本进程的 op 抛的是 JSON 串（`{"kind": …}`）时，把它降级成
    一句 `worker_error` 会把"通道已退役"这种**要按类型分支**的语义抹平，调用方只能靠文案猜。
    """
    msg = str(e)
    try:
        parsed = json.loads(msg)
    except Exception:                          # noqa: BLE001
        return {"kind": "worker_error", "message": msg[:800]}
    if isinstance(parsed, dict) and parsed.get("kind"):
        return parsed
    return {"kind": "worker_error", "message": msg[:800]}


def main():
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        rid = req.get("id")
        op = req.get("op")
        fn = OPS.get(op)
        try:
            if fn is None:
                raise RuntimeError("未知 op: %s（支持：%s）" % (op, ", ".join(sorted(OPS))))
            data = fn(req.get("args") or {})
            resp = {"id": rid, "ok": True, "data": data}
        except Exception as e:  # noqa: BLE001
            resp = {"id": rid, "ok": False, "error": _error_of(e)}
        out.write(json.dumps(resp, ensure_ascii=False) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
