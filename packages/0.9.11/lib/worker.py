"""Daniel 常驻工作进程（插件内部使用）。

为什么需要它：插件每次调用如果都新起一个 python 进程，光是解释器＋客户端构造＋会话读取
就接近 1 秒；而真正慢的是上游接口（1–10 秒）。常驻进程把「进程启动」「会话解析」「HTTP 连接」
都摊薄成一次，并支持**在进程内并行**发多个只读请求，因此单次 KOL 档案从「多次调用 × 每次 2–3 秒」
压到「一次调用、内部并行、约 3–5 秒」。

协议：stdin/stdout 逐行 JSON（NDJSON）。请求 {"id":1,"op":"...","args":{...}}
响应 {"id":1,"ok":true,"data":{...}} 或 {"id":1,"ok":false,"error":{"kind":"...","message":"..."}}
只读：本进程不执行任何写操作。
"""
import hashlib
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

#: 官方库熔断：503/超时后 5 分钟内直接快速失败，避免把"不可用"放大成两分半等待
_ROSTER_DOWN_UNTIL = 0.0
_ROSTER_DOWN_SECONDS = 300

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


# ───────────── 闸账本：淘汰数必须是**实测**，不许是编的（TICKET-217 · 方案 C）─────────────
#
# 口径（总监拍板）：
#   · 白名单工具返回成功时，「排除分块」段必须是三者之一：真实闸记录／明确「本次无筛选环节」／
#     「本次溯源不可用（缺：哪一闸）」——**严禁编造通过／淘汰数**；
#   · 状态只有入选／排除两档；受众数据缺失只标注不判状态；报价不参与名单类判断。
#
# 怎么算出真数：官方库只给「这套条件命中了多少」，不给「每道闸各淘汰多少」。
# 所以逐闸**实测**一遍：把闸按固定顺序串成链，取「只加前 k 道闸」时的命中总数，
#   第 k 道闸的淘汰数 ＝ 只加前 k-1 道闸的总数 － 只加前 k 道闸的总数。
# 每一步都是平台真实返回的计数（不是比例推算、不是抽样外推）；取不到就写「缺」，不猜。
#
# 落点：<DANIEL_HOME>/out/trace/<任务标识>/ledger.json（可用 DANIEL_TRACE_DIR 覆盖）；
# 任务标识由**入参指纹**决定 —— 并发两个任务参数不同即落不同目录，账本不会串号。
LEDGER_MODE = (os.environ.get("DANIEL_LEDGER") or "auto").strip().lower()
LEDGER_ENABLED = LEDGER_MODE not in ("off", "0", "false", "no")
#: 基线样本上限：一次带这么多条候选，用于「典型例子」与排除明细（不参与计数）
LEDGER_SAMPLE_MAX = int(os.environ.get("DANIEL_LEDGER_SAMPLE_MAX") or 60)
#: 账本时间预算（秒）：超预算就放弃剩余探测，把没取到的闸如实写进「缺」
LEDGER_BUDGET = float(os.environ.get("DANIEL_LEDGER_BUDGET") or 20)
#: 单次探测超时（秒）：比主调用更短 —— 账本不该把主调用拖慢
LEDGER_PROBE_TIMEOUT = float(os.environ.get("DANIEL_LEDGER_PROBE_TIMEOUT") or 12)
LEDGER_TYPICAL_MAX = 3
LEDGER_VERSION = "1.0"

_COUNTRY_SPLIT = re.compile(r"[,\s]+")


def _num_or_none(v):
    """数字归一：空值 → None；能转就转（整数值一律用 int，保证与 JS 侧指纹一致）。"""
    if v is None or v == "" or v == []:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if float(f).is_integer() else f


def _str_or_none(v):
    if v is None or v == []:
        return None
    s = str(v).strip()
    return s or None


def _fmt_count(n):
    """数量写法（业务看得懂）：10000 → 1万；600000 → 60万；8 → 8。"""
    try:
        v = float(n)
    except (TypeError, ValueError):
        return str(n)
    if v >= 1e8:
        return ("%.2f" % (v / 1e8)).rstrip("0").rstrip(".") + "亿"
    if v >= 1e4:
        return ("%.2f" % (v / 1e4)).rstrip("0").rstrip(".") + "万"
    return str(int(v)) if v == int(v) else ("%.1f" % v)


def _title_of(c):
    return _str_or_none(c.get("title")) or _str_or_none(c.get("channelTitle")) or "（未命名频道）"


def _country_ok(actual, want):
    a = _str_or_none(actual)
    if not a:
        return False
    wanted = [x for x in _COUNTRY_SPLIT.split(str(want or "").upper()) if x]
    return a.upper() in wanted


def _category_ok(actual, want):
    a = _str_or_none(actual)
    if not a:
        return False
    norm = lambda s: re.sub(r"[_\-]+", " ", str(s).lower()).strip()
    return norm(want) in norm(a)


def _gates_of(args):
    """本次**真正执行**的筛选闸（顺序固定：国家 → 粉丝区间 → 品类）。

    只列用户给了的条件：维度随本次实际执行的闸走，不套固定模板；没执行就不出现。
    """
    gates = []
    country = _str_or_none(args.get("country"))
    if country:
        gates.append({
            "闸": "国家 %s" % country,
            "判据": "频道登记国家须在 %s 内" % country,
            "payload": {"country": country},
            "匹配": lambda c, w=country: _country_ok(c.get("country"), w),
            "取值": lambda c: "登记国 %s" % (_str_or_none(c.get("country")) or "未标注"),
        })
    mn = _num_or_none(args.get("minSubscribers"))
    mx = _num_or_none(args.get("maxSubscribers"))
    if mn is not None or mx is not None:
        lo = _fmt_count(mn) if mn is not None else "不限"
        hi = _fmt_count(mx) if mx is not None else "不限"
        payload = {}
        if mn is not None:
            payload["minSubscribers"] = mn
        if mx is not None:
            payload["maxSubscribers"] = mx

        def _subs_ok(c, lo=mn, hi=mx):
            v = _num_or_none(c.get("subscriberCount"))
            if v is None:
                return False                      # 订阅数都没给，无法核验 → 不算通过
            if lo is not None and v < lo:
                return False
            if hi is not None and v > hi:
                return False
            return True

        gates.append({
            "闸": "粉丝区间 %s–%s" % (lo, hi),
            "判据": "订阅数落在 %s–%s 之间" % (lo, hi),
            "payload": payload,
            "匹配": _subs_ok,
            "取值": lambda c: "订阅 %s" % (_fmt_count(c.get("subscriberCount"))
                                          if c.get("subscriberCount") is not None else "未标注"),
        })
    cat = _str_or_none(args.get("category"))
    if cat:
        gates.append({
            "闸": "品类 %s" % cat,
            "判据": "平台登记的品类须匹配 %s" % cat,
            "payload": {"category": cat},
            "匹配": lambda c, w=cat: _category_ok(c.get("category"), w),
            "取值": lambda c: "品类 %s" % (_str_or_none(c.get("category")) or "未标注"),
        })
    return gates


def trace_base_dir():
    """账本落点的根目录：DANIEL_TRACE_DIR 显式覆盖 > <DANIEL_HOME>/out/trace。"""
    explicit = _str_or_none(os.environ.get("DANIEL_TRACE_DIR"))
    if explicit:
        return explicit
    home = _str_or_none(os.environ.get("DANIEL_HOME"))
    if home:
        return os.path.join(home, "out", "trace")
    return None


def roster_args_key(args):
    """入参指纹（前 16 位）：与 JS 侧 `rosterArgsKey()` **必须逐字符一致**（键序＝字典序）。"""
    args = args or {}
    canon = {
        "category": _str_or_none(args.get("category")),
        "country": _str_or_none(args.get("country")),
        "limit": _num_or_none(args.get("limit")) if _num_or_none(args.get("limit")) is not None else 10,
        "maxSubscribers": _num_or_none(args.get("maxSubscribers")),
        "minSubscribers": _num_or_none(args.get("minSubscribers")),
        "page": _num_or_none(args.get("page")) if _num_or_none(args.get("page")) is not None else 1,
        "query": str(args.get("query") or "").strip(),
    }
    raw = json.dumps(canon, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def roster_task_id(args):
    """任务标识（一个任务一个账本目录；不同入参 → 不同目录，互不串号）。"""
    return "roster-" + roster_args_key(args)


def _ledger_write(ledger):
    """把账本落到 <base>/<任务标识>/ledger.json（写不成也不报错：账本不该拖垮主调用）。"""
    base = trace_base_dir()
    if not base:
        return None
    path = os.path.join(base, ledger.get("任务标识") or "roster-unknown", "ledger.json")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(ledger, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        return path
    except Exception:                             # noqa: BLE001
        return None


def _ledger_probe(query, payload, timeout=LEDGER_PROBE_TIMEOUT):
    """一次计数探测：只关心 total（命中总数），不关心本页条数。"""
    body = {"query": query, "page": 1}
    body.update(payload or {})
    r = client().query("discovery.searchRoster", body, retries=1, timeout=timeout)
    r = r or {}
    total = _num_or_none(r.get("total"))
    return (int(total) if total is not None else None), (r.get("channels") or [])


def build_roster_ledger(args, query, actual):
    """为本次 roster_search 生成**真实**闸账本。

    铁律：**能算的必须算（逐闸实测），算不出的写「缺」，绝不编数字。**
    任何异常都就地降级，绝不上抛（账本坏了也不许把主调用搞挂）。
    """
    args = args or {}
    ledger = {
        "版本": LEDGER_VERSION,
        "工具": "daniel_roster_search",
        "任务标识": roster_task_id(args),
        "参数指纹": roster_args_key(args),
        "生成时刻": int(time.time()),
        "检索式": str(query or ""),
        "闸": [],
        "缺": [],
    }
    if not LEDGER_ENABLED:
        ledger["缺"] = ["筛选闸记录"]
        ledger["降级"] = "闸账本已按配置关闭（DANIEL_LEDGER=off），本次不产出闸计数"
        ledger["账本落点"] = _ledger_write(ledger)
        return ledger

    gates = _gates_of(args)
    t0 = time.time()

    # ── ① 基线：只给检索式、不带任何筛选条件 —— 这就是「候选总数」 ──
    try:
        cand_total, sample = _ledger_probe(query, {"limit": LEDGER_SAMPLE_MAX})
    except Exception as e:                        # noqa: BLE001
        ledger["缺"] = ["筛前候选总数（官方库基线计数未取到）"]
        ledger["降级"] = "基线计数取不到：%s" % str(e)[:120]
        ledger["账本落点"] = _ledger_write(ledger)
        return ledger
    sample = [c for c in (sample or []) if isinstance(c, dict)]
    if cand_total is None:
        cand_total = len(sample)
    ledger["候选总数"] = int(cand_total)
    ledger["样本"] = {"取到": len(sample), "候选总数": int(cand_total),
                     "覆盖": "全量" if len(sample) >= int(cand_total) else "部分"}

    # ── ② 没有任何筛选条件：显式声明「本次无筛选环节」（不编淘汰数） ──
    if not gates:
        ledger["入选数"] = int(cand_total)
        ledger["排除合计"] = 0
        ledger["无筛选环节"] = True
        ledger["排除明细"] = []
        ledger["账本落点"] = _ledger_write(ledger)
        return ledger

    # ── ③ 逐闸实测：只加前 k 道闸时的命中总数（末闸用本次真实结果，省一次请求）──
    totals = [int(cand_total)]
    prefix = {"limit": 5}
    for i, g in enumerate(gates):
        if i == len(gates) - 1:
            last = _num_or_none((actual or {}).get("total"))
            if last is None:
                try:
                    last, _ = _ledger_probe(query, dict(prefix, **g["payload"]))
                except Exception:                 # noqa: BLE001
                    last = None
            if last is None:
                break
            totals.append(int(last))
        else:
            prefix.update(g["payload"])
            if time.time() - t0 > LEDGER_BUDGET:
                ledger["缺"].append("%s 之后的实测计数（超出账本时间预算 %d 秒）"
                                    % ("、".join(x["闸"] for x in gates[:i + 1]), int(LEDGER_BUDGET)))
                break
            try:
                total, _ = _ledger_probe(query, prefix)
            except Exception as e:               # noqa: BLE001
                ledger["缺"].append("%s 之后的实测计数（探测失败：%s）" % (g["闸"], str(e)[:80]))
                break
            if total is None:
                ledger["缺"].append("%s 之后的实测计数（平台未返回命中总数）" % g["闸"])
                break
            totals.append(int(total))

    # ── ④ 样本归因：用基线里的每一位真实候选，判它先被哪道闸挡下（只用于举例与明细）──
    hit = {i: [] for i in range(len(gates))}
    for c in sample:
        for i, g in enumerate(gates):
            try:
                ok = g["匹配"](c)
            except Exception:                     # noqa: BLE001
                ok = None
            if ok is False:
                hit[i].append(c)
                break
            if ok is None:
                break
    rows = []
    for i, g in enumerate(gates):
        rec = {"闸": g["闸"], "判据": g["判据"]}
        if i + 1 < len(totals):
            rec["通过数"] = int(totals[i + 1])
            diff = int(totals[i]) - int(totals[i + 1])
            if diff < 0:
                rec["异常"] = "该闸之后计数大于上游计数（两次实测不一致），淘汰数不外推"
                ledger["缺"].append("%s 的淘汰数（实测计数不一致）" % g["闸"])
            else:
                rec["淘汰数"] = diff
        else:
            ledger["缺"].append("%s 的通过与淘汰数（未取到该闸之后的实测计数）" % g["闸"])
        rec["样本内淘汰"] = len(hit[i])
        rec["典型例子"] = [
            "%s（%s）" % (_title_of(c), g["取值"](c)) for c in hit[i][:LEDGER_TYPICAL_MAX]
        ]
        ledger["闸"].append(rec)
        for c in hit[i]:
            rows.append({
                "闸": g["闸"], "判据": g["判据"],
                "红人": _title_of(c), "频道编号": _str_or_none(c.get("channelId")) or "",
                "订阅数": c.get("subscriberCount"), "国家": _str_or_none(c.get("country")) or "",
                "品类": _str_or_none(c.get("category")) or "", "原因": g["取值"](c),
            })
    ledger["排除明细"] = rows

    if len(totals) == len(gates) + 1:
        ledger["入选数"] = int(totals[-1])
        ledger["排除合计"] = max(0, int(cand_total) - int(totals[-1]))
    ledger["账本落点"] = _ledger_write(ledger)
    return ledger


def op_roster_search(args):
    """YouTube 官方库检索（带受众数据的那一份）。

    长任务型接口：服务端排队时可能 503，客户端默认的「3 次重试 × 90 秒」会把一次调用拖成两分半。
    这里固定 **单次尝试 ＋ 45 秒超时**，把"慢/不可用"如实、快速地交回调用方。
    """
    query = str(args.get("query") or "").strip()
    if not query:
        raise RuntimeError("query 必填（描述要找什么样的红人）")
    payload = {"query": query, "limit": int(args.get("limit") or 10), "page": int(args.get("page") or 1)}
    for key in ("country", "category", "minSubscribers", "maxSubscribers"):
        if args.get(key) not in (None, "", []):
            payload[key] = args[key]
    global _ROSTER_DOWN_UNTIL
    now = time.time()
    if now < _ROSTER_DOWN_UNTIL:
        raise RuntimeError(json.dumps({
            "kind": "roster_unavailable", "seconds": 0,
            "detail": "官方库仍在熔断窗口内（上次返回 503／超时）",
            "剩余秒数": int(_ROSTER_DOWN_UNTIL - now),
            "建议": ["过一会儿再试（官方库当前过载）", "缩小条件：降 limit、去掉 country 或放宽订阅数",
                     "**不要**改用其它来源替代官方库结果；如用户同意才可换源"],
        }, ensure_ascii=False))
    t0 = time.time()
    try:
        r = client().query("discovery.searchRoster", payload, retries=1, timeout=15)
    except Exception as e:                       # noqa: BLE001
        msg = str(e)
        elapsed = round(time.time() - t0, 1)
        kind = "roster_unavailable" if "503" in msg else ("roster_timeout" if "timed out" in msg.lower() or elapsed >= 14 else "roster_failed")
        if kind in ("roster_unavailable", "roster_timeout"):
            _ROSTER_DOWN_UNTIL = time.time() + _ROSTER_DOWN_SECONDS   # 熔断 5 分钟
        raise RuntimeError(json.dumps({
            "kind": kind, "seconds": elapsed, "detail": msg[:200],
            "熔断秒数": _ROSTER_DOWN_SECONDS if kind in ("roster_unavailable", "roster_timeout") else 0,
            "建议": ["稍后重试（官方库当前可能过载）", "缩小条件：降 limit、去掉 country 或放宽订阅数",
                     "**不要**改用其它来源替代官方库结果；如用户同意才可换源"],
        }, ensure_ascii=False))
    _ROSTER_DOWN_UNTIL = 0.0                      # 成功即解除熔断
    chans = (r or {}).get("channels") or []
    out = {
        "query": query, "seconds": round(time.time() - t0, 1),
        "total": (r or {}).get("total"), "page": (r or {}).get("page"),
        "pageSize": (r or {}).get("pageSize"), "totalPages": (r or {}).get("totalPages"),
        "source": (r or {}).get("source"),
        "channels": [{
            "channelId": c.get("channelId"), "title": c.get("title"),
            "handle": c.get("handle"), "subscriberCount": c.get("subscriberCount"),
            "country": c.get("country"), "category": c.get("category"),
            "medianViews": c.get("medianViews"), "avgViews": c.get("avgViews"),
            "engagementRate": c.get("engagementRate"),
        } for c in chans],
    }
    # 闸账本（TICKET-217）：**主结果拿到之后**才算，任何失败都只降级、不影响上面的结果
    try:
        out["闸账本"] = build_roster_ledger(args, query, out)
    except Exception as e:                        # noqa: BLE001
        out["闸账本"] = {
            "版本": LEDGER_VERSION, "工具": "daniel_roster_search",
            "任务标识": roster_task_id(args), "参数指纹": roster_args_key(args),
            "生成时刻": int(time.time()), "闸": [], "排除明细": [],
            "缺": ["筛选闸记录"],
            "降级": "闸账本生成过程出错（%s），已降级且不编造计数" % str(e)[:120],
        }
    return out


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
    "roster_search": op_roster_search,
    "detail_cache": lambda args: detail_cache_stats(),
    "ping": lambda args: {"pong": True, "pid": os.getpid()},
}


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
            resp = {"id": rid, "ok": False, "error": {"kind": "worker_error", "message": str(e)[:800]}}
        out.write(json.dumps(resp, ensure_ascii=False) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
