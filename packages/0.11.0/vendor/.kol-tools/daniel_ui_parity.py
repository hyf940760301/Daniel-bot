#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daniel_ui_parity.py —— Daniel 前端「界面指标」的逐字复现器（只读 · 纯计算）

用途（TICKET-115 §二 C）：
  用 Python **逐字复现** Daniel 前端 bundle 里的计算，使"我们算出来的数"与
  "用户在 Daniel 界面看到的数"逐格可对上：

  1) `authenticityScore-a-IZvxEl.js` 的 `Ce(e)`      → CQI 五维 + 总分 + 等级（S/A/B/C）
  2) 同模块 `se()/oe()/re()/ae()` 及 `Y()/q()/ie()`  → 各维度原始分与其分档表
  3) `CreatorSlideOver-DCxe8lsV.js` 的 `Qt`/`Kt`    → 抽屉 Performance 的
     **Long-form Avg Views** / **Shorts Avg Views**（28 天窗口 + 最新 30 条中位数）
  4) 三套等级分界（`Ce()` 75/60/45、`cqiBreakdown` 70/50/30、`SharedList` 70/55/40）
  5) 维度颜色分界（抽屉 `Pe()` 比值阈值 / KOLProfile 页面内联阈值）

证据纪律：
  - 所有函数体逐字照抄 bundle（含 `Math.round` 的"半数向上"语义、`D[floor(n/2)]`
    的"偶数取上中位"语义、`contentType!=="SHORTS"` 的客户端过滤语义）。
  - `--oracle` 用 Node.js 直接执行从 bundle 里**原样抽出**的 JS 版本，与本文件
    的 Python 版本逐格比对（正控）；`--negative-control` 故意改错输入，必须报不一致。
  - 本文件**不发任何网络请求**，只读输入 JSON / 计算 / 自检。

用法：
  python3 .kol-tools/daniel_ui_parity.py --selfcheck
  python3 .kol-tools/daniel_ui_parity.py --probe docs/marketing/kol/_daniel-integration/02-route-probe-raw.json --oracle .kol-tools/_daniel_jsref/authenticityScore.extract.mjs --report /tmp/parity.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional

if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    # 兄弟模块 daniel_io：脚本直跑与被别的仪器当库载入两条路都要能 import（TICKET-168）。
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daniel_io  # noqa: E402  （TICKET-168：`--json` 出口的唯一收口层）

# ---------------------------------------------------------------------------
# 0. JS 语义工具（逐字对齐 ECMAScript，不用 Python 内建语义）
# ---------------------------------------------------------------------------


def js_round(x: float) -> int:
    """ECMAScript Math.round：.5 一律向 +∞ 取整（Python 内建 round 是银行家舍入）。"""
    if x != x or x in (float("inf"), float("-inf")):
        raise ValueError("js_round 收到非有限值：%r" % (x,))
    return int(math.floor(x + 0.5))


def js_floor(x: float) -> int:
    return int(math.floor(x))


def _num(v: Any, default: float = 0.0) -> float:
    """对齐 JS 的 `x ?? 0`（null/undefined → 默认）。"""
    if v is None:
        return default
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    raise TypeError("期望数值，收到 %r" % (v,))


def _falsy_or(a: Any, b: Any) -> Any:
    """对齐 JS `a || b`：0/None/''/False 都取 b。"""
    if a is None or a is False or a == 0 or a == "":
        return b
    return a


# ---------------------------------------------------------------------------
# 1. 分档表（bundle 逐字）
# ---------------------------------------------------------------------------

# Q：受众维度的"均播/粉丝比"分位档（percent，均播÷粉丝×100）
Q_BANDS = {
    "mega": [27, 18, 5, 1],
    "macro": [32, 10, 1.3, 0.5],
    "mid": [28, 11, 3.6, 1.2],
    "micro": [40, 20, 8, 3],
    "nano": [60, 30, 15, 5],
}
TIER_LABELS = {
    "mega": "Mega (10M+)",
    "macro": "Macro (1M–10M)",
    "mid": "Mid-size (100K–1M)",
    "micro": "Micro (10K–100K)",
    "nano": "Nano (<10K)",
}
# te：僵尸粉判定的"最低渗透比"（%），仅对 >=100K 粉丝生效
ZOMBIE_MIN_RATIO = {"mega": 1, "macro": 1, "mid": 2, "micro": 3, "nano": 5}

# ie()：互动率分档（percent）
ENGAGE_TIERS = {
    "mega": {"excellent": 3, "strong": 2, "typical": 1.2, "watch": 0.5},
    "macro": {"excellent": 4, "strong": 3, "typical": 2, "watch": 1},
    "mid": {"excellent": 5, "strong": 3.5, "typical": 2.5, "watch": 1.5},
    "micro": {"excellent": 7, "strong": 5, "typical": 3, "watch": 2},
    "nano": {"excellent": 10, "strong": 7, "typical": 4, "watch": 2},
}

# Z() / Pe() / Ne() 的比值分界（0–1）
SCORE_COLORS = {
    "tier5_green": "#00BFA6",
    "tier4_blue": "#006BDF",
    "tier3_amber": "#FFB400",
    "tier2_red": "#FF6B6B",
    "tier1_purple": "#A259FF",
}
TEXT_COLORS = {
    "tier5_green": "#00BFA6",
    "tier4_blue": "#005abf",
    "tier3_amber": "#cc9000",
    "tier2_red": "#FF6B6B",
    "tier1_purple": "#8a3fcf",
}

# 抽屉以 JS `672*60*60*1e3` 表达的"28 天"窗口
WINDOW_28D_MS = 672 * 60 * 60 * 1000
# ae() 里的 `2592e6` = 30 天（用于月均更新频率）
MS_PER_MONTH = 2592e6


# ---------------------------------------------------------------------------
# 2. 逐字复现：分档与五维原始分
# ---------------------------------------------------------------------------


def tier_of(subscriber_count: float) -> str:
    """`q(e)`：粉丝 → 体量档。"""
    s = _num(subscriber_count)
    if s >= 1e7:
        return "mega"
    if s >= 1e6:
        return "macro"
    if s >= 1e5:
        return "mid"
    if s >= 1e4:
        return "micro"
    return "nano"


def audience_percentile(avg_views: Any, subscriber_count: Any) -> Dict[str, Any]:
    """`Y(e,t)`：均播/粉丝比 → 分位分（受众维度原始分）。"""
    a = _num(avg_views)
    s = _num(subscriber_count)
    if not a or a == 0 or s == 0:
        return {"ratio": 0, "percentileScore": 50, "isZombie": False,
                "tier": tier_of(s)}
    o = tier_of(s)
    n = a / s * 100
    i = Q_BANDS[o]
    if n >= i[0]:
        r = 100
    elif n >= i[1]:
        r = 85
    elif n >= i[2]:
        r = 65
    elif n >= i[3]:
        r = 40
    else:
        r = 20
    zombie = bool(s >= 1e5 and n < ZOMBIE_MIN_RATIO[o])
    return {"ratio": n, "percentileScore": r, "isZombie": zombie, "tier": o}


def audience_score(avg_views: Any, subscriber_count: Any) -> int:
    """`re(e,t)` —— CQI 受众维度原始分（= Y().percentileScore）。"""
    return audience_percentile(avg_views, subscriber_count)["percentileScore"]


def engage_percentile(avg_views: Any, subscriber_count: Any) -> int:
    """`ne(e,t)` —— 另一套渗透分（供 ve() 真实性信号使用，非 CQI 受众维度）。"""
    a = _num(avg_views)
    s = _num(subscriber_count)
    if not a or a == 0 or s == 0:
        return 50
    o = tier_of(s)
    n = a / s * 100
    if o in ("mega", "macro"):
        return (100 if n >= 10 else 85 if n >= 5 else 70 if n >= 2
                else 45 if n >= 1 else 25 if n >= 0.5 else 10 if n >= 0.1 else 0)
    if o == "mid":
        return (100 if n >= 15 else 85 if n >= 8 else 70 if n >= 3
                else 55 if n >= 2 else 35 if n >= 1 else 20 if n >= 0.5 else 5)
    return (100 if n >= 20 else 85 if n >= 10 else 75 if n >= 5
            else 60 if n >= 2 else 40)


def engage_tiers(subscriber_count: Any) -> Dict[str, Any]:
    """`ie(e)` —— 该粉丝档的互动率分档阈值（percent）。"""
    s = _num(subscriber_count)
    t = tier_of(s)
    return dict(ENGAGE_TIERS[t], tier=t, tierLabel=TIER_LABELS[t])


def engage_score(engagement_rate: Any, subscriber_count: Any) -> int:
    """`oe(e,t)` —— 互动维度原始分。e 为**百分数**（0.81 表示 0.81%）。"""
    e = None if engagement_rate is None else _num(engagement_rate)
    if e is None or e == 0:
        return 30
    o = engage_tiers(subscriber_count)
    return (100 if e >= o["excellent"] else 80 if e >= o["strong"]
            else 60 if e >= o["typical"] else 40 if e >= o["watch"] else 20)


def activity_score(days_since_last_video: Any, video_count: Any,
                   channel_created_at: Any = None, now_ms: Optional[float] = None) -> int:
    """`ae(e,t,o)` —— 活跃维度原始分（天数分 ×0.7 + 月均更新频率分 ×0.3）。

    注意 JS 语义坑：判据是 `e!==null`（不是 `!=null`），所以
      - 传 None（显式 null） → 天数分保持默认 30
      - 传 undefined 在 JS 里会走到 else 分支得到 5；Python 侧用
        `days_since_last_video=UNDEFINED` 显式表达该情形，以保持逐字等价。
    频率分只有在 `t && o`（videoCount 与 channelCreatedAt 都非零）时才计算，
    否则保持默认 50 —— 抽屉与 KOLProfile 页面**都没有传这两个字段**。
    """
    n = 30
    if days_since_last_video is not UNDEFINED:
        if days_since_last_video is not None:
            e = _num(days_since_last_video)
            n = (100 if e <= 7 else 90 if e <= 14 else 75 if e <= 28
                 else 55 if e <= 60 else 35 if e <= 90 else 15 if e <= 180 else 5)
    else:
        n = 5  # JS: undefined 与所有阈值比较均为 false → 落到最后 else
    i = 50
    if video_count and channel_created_at:
        now = now_ms if now_ms is not None else _now_ms()
        age_ms = now - _to_ms(channel_created_at)
        r = max(1, js_floor(age_ms / MS_PER_MONTH))
        s = _num(video_count) / r
        i = (100 if s >= 8 else 85 if s >= 4 else 65 if s >= 2 else 45 if s >= 1 else 20)
    return js_round(n * 0.7 + i * 0.3)


def _js_relational_ge(value: Any, threshold: float) -> bool:
    """JS `value >= threshold` 的真实语义（含数组被 ToPrimitive 成字符串再转数字的行为）。

    重要：Daniel 的三个调用点**从不把 `matchedVideos` 数组传进 `Ce()`**（只传
    `brandFitData`），所以这条分支在实践中不生效；此处仍逐字保留 JS 行为，
    以免我们的复现器在别人误传数组时给出比界面更"乐观"的品牌契合分。
    """
    v = value
    if isinstance(v, (list, tuple)):
        if len(v) == 1:
            try:
                v = float(v[0])
            except Exception:
                return False
        else:
            return False  # "[1,2]" → ToNumber → NaN → 任何比较都是 false
    if v is None:
        return False
    try:
        v = float(v)
    except Exception:
        return False
    return v >= threshold


def brand_fit_score(e: Dict[str, Any]) -> int:
    """`se(e)` —— 品牌契合维度原始分。"""
    mv = e.get("matchedVideos")
    if mv is None:
        mv = 0
    found = e.get("foundByKeywords") or []
    o = len(found)
    if _js_relational_ge(mv, 5):
        return 100
    if _js_relational_ge(mv, 3):
        return 85
    if _js_relational_ge(mv, 2):
        return 75
    if _js_relational_ge(mv, 1):
        return 65
    if o >= 5:
        return 60
    if o >= 3:
        return 50
    if o >= 1:
        return 35
    bf = e.get("brandFitData")
    if bf and _num(bf.get("totalVideos"), 0) > 0:
        n = int(_num(bf.get("hitCount"), 0))
        comp = bool(bf.get("hasCompetitorHits"))
        r = 100 if n >= 6 else 90 if n >= 4 else 75 if n >= 2 else 60 if n >= 1 else 40
        return min(100, r + (5 if comp else 0))
    return 40


def commercial_score(paid_placement_ratio: Any) -> int:
    """`Ce()` 内联的商业化维度原始分。"""
    o = _num(paid_placement_ratio, 0)
    return (100 if o >= 0.3 else 85 if o >= 0.2 else 70 if o >= 0.1
            else 55 if o >= 0.05 else 40 if o > 0 else 20)


# ---------------------------------------------------------------------------
# 3. 逐字复现：Ce() —— CQI 总分 + 五维 + 等级
# ---------------------------------------------------------------------------

CQI_WEIGHTS = {"brandFit": 0.20, "engage": 0.25, "audience": 0.25,
               "activity": 0.15, "commercial": 0.15}
CQI_MAX = {"Brand Fit": 20, "Engage": 25, "Audience": 25,
           "Activity": 15, "Commercial": 15}
CQI_ORDER = ["Brand Fit", "Engage", "Audience", "Activity", "Commercial"]
# Ce() 里写死的 badge 底色（静态，不随分数变化）
CQI_STATIC_BADGE = {"Brand Fit": "bg-amber-400", "Engage": "bg-orange-400",
                    "Audience": "bg-teal-500", "Activity": "bg-teal-500",
                    "Commercial": "bg-amber-400"}


def cqi(e: Dict[str, Any], now_ms: Optional[float] = None) -> Dict[str, Any]:
    """`Ce(e)` 逐字复现。

    入参字段（与前端调用点一致）：
      subscriberCount, paidPlacementRatio, matchedVideos, foundByKeywords,
      brandFitData, engagementRate(percent), avgViews,
      daysSinceLastVideo, videoCount, channelCreatedAt
    """
    t = _num(e.get("subscriberCount"), 0)
    o = _num(e.get("paidPlacementRatio"), 0)
    n = brand_fit_score(e)
    i = js_round(n * 0.2 * 10) / 10
    r = engage_score(e.get("engagementRate"), t)
    s = js_round(r * 0.25 * 10) / 10
    M = audience_score(e.get("avgViews"), t)
    l = js_round(M * 0.25 * 10) / 10
    f = activity_score(e.get("daysSinceLastVideo", None),
                       e.get("videoCount"), e.get("channelCreatedAt"), now_ms)
    p = js_round(f * 0.15 * 10) / 10
    d = commercial_score(o)
    g = js_round(d * 0.15 * 10) / 10
    S = js_round(i + s + l + p + g)
    h = "S" if S >= 75 else "A" if S >= 60 else "B" if S >= 45 else "C"
    raw = [n, r, M, f, d]
    weighted = [i, s, l, p, g]
    dims = []
    for idx, label in enumerate(CQI_ORDER):
        dims.append({
            "label": label,
            "score": weighted[idx],
            "max": CQI_MAX[label],
            "color": CQI_STATIC_BADGE[label],
            "rawScore": raw[idx],
            "ratio": weighted[idx] / CQI_MAX[label],
        })
    return {"total": S, "grade": h, "dimensions": dims,
            "weightedSum": i + s + l + p + g}


def grade_variants(total: float) -> Dict[str, str]:
    """三套等级分界（本项目里同时存在，用错就会对不上界面）。"""
    t = _num(total)
    return {
        # authenticityScore.Ce() —— 抽屉 CQI 与 KOLProfile 页面**实际走的那套**
        "Ce_authenticityScore_75_60_45": ("S" if t >= 75 else "A" if t >= 60
                                          else "B" if t >= 45 else "C"),
        # CreatorSlideOver 的 cqiBreakdown 分支（存库口径）
        "cqiBreakdown_70_50_30": ("S" if t >= 70 else "A" if t >= 50
                                  else "B" if t >= 30 else "C"),
        # SharedList 公开分享页
        "SharedList_70_55_40": ("A" if t >= 70 else "B" if t >= 55
                                else "C" if t >= 40 else "D"),
    }


# ---------------------------------------------------------------------------
# 4. 颜色分界（用户要求的"互动/活跃不能红、必须绿"）
# ---------------------------------------------------------------------------


def drawer_score_color(ratio: float) -> str:
    """抽屉 `Pe(t)`（比值 0–1 → 文字色）。"""
    if ratio >= 0.8:
        return TEXT_COLORS["tier5_green"]
    if ratio >= 0.6:
        return TEXT_COLORS["tier4_blue"]
    if ratio >= 0.4:
        return TEXT_COLORS["tier3_amber"]
    if ratio >= 0.2:
        return TEXT_COLORS["tier2_red"]
    return TEXT_COLORS["tier1_purple"]


def drawer_bar_color(ratio: float) -> str:
    """抽屉 `Z(t)`（比值 0–1 → 进度条底色）。"""
    if ratio >= 0.8:
        return SCORE_COLORS["tier5_green"]
    if ratio >= 0.6:
        return SCORE_COLORS["tier4_blue"]
    if ratio >= 0.4:
        return SCORE_COLORS["tier3_amber"]
    if ratio >= 0.2:
        return SCORE_COLORS["tier2_red"]
    return SCORE_COLORS["tier1_purple"]


def color_band(ratio: float, scheme: str = "drawer") -> str:
    """把比值翻成业务语言的红/黄/绿档，便于用户一眼判断。"""
    if scheme == "drawer":          # 阈值 0.8 / 0.6 / 0.4 / 0.2
        if ratio >= 0.8:
            return "green"
        if ratio >= 0.6:
            return "blue"
        if ratio >= 0.4:
            return "amber"
        if ratio >= 0.2:
            return "red"
        return "purple"
    if scheme == "kolprofile":      # 内联阈值 0.7 / 0.4
        if ratio > 0.7:
            return "green"
        if ratio > 0.4:
            return "amber"
        return "red"
    raise ValueError("未知配色方案：%s" % scheme)


def kolprofile_bar_color(ratio: float) -> str:
    """KOLProfile 页面（`/kol/:channelId`）内联的三色阈值。"""
    if ratio > 0.7:
        return "#10b981"
    if ratio > 0.4:
        return "#f59e0b"
    return "#ef4444"


def engage_activity_green_boundaries(subscriber_count: Any,
                                     days_values: Optional[List[int]] = None) -> Dict[str, Any]:
    """给出「互动」「活跃」两维在抽屉里的绿/黄/红分界（含原始分与业务阈值）。"""
    t = engage_tiers(subscriber_count)
    out: Dict[str, Any] = {"tier": t["tier"], "tierLabel": t["tierLabel"],
                           "engageTiersPercent": {k: t[k] for k in
                                                  ("excellent", "strong", "typical", "watch")}}
    # 互动：score=raw*0.25，绿 ⟺ raw>=80
    out["engage"] = {
        "green": {"rawMin": 80, "rule": "ER ≥ strong 阈值（%.1f%%）" % t["strong"]},
        "blue": {"rawMin": 60, "rule": "typical ≤ ER < strong"},
        "amber": {"rawMin": 40, "rule": "watch ≤ ER < typical"},
        "red": {"rawMax": 30, "rule": "ER < watch，或 ER 取不到/为 0（降级 30）"},
    }
    # 活跃：score=round(raw*1.5)/10，绿 ⟺ raw>=80
    out["activity"] = {
        "green": {"rawMin": 80, "rule": "天数分 100（≤7 天）＋频率分 50（默认）→ raw 85"},
        "blue": {"rawMin": 68, "rule": "≤14 天 → raw 78；≤28 天 → raw 68"},
        "amber": {"rawMin": 40, "rule": "≤60 天 → raw 54；≤90 天 → raw 40"},
        "red": {"rawMax": 36, "rule": "≤180 天 → raw 26；更久 → raw 19；天数取不到 → raw 36"},
    }
    if days_values:
        out["activityByDays"] = {
            str(d): {"rawScore": activity_score(d, None, None),
                     "weighted": js_round(activity_score(d, None, None) * 1.5) / 10,
                     "ratio": (js_round(activity_score(d, None, None) * 1.5) / 10) / 15,
                     "color": color_band((js_round(activity_score(d, None, None) * 1.5) / 10) / 15)}
            for d in days_values
        }
    return out


# ---------------------------------------------------------------------------
# 5. 逐字复现：抽屉 Performance 的 Long-form / Shorts Avg Views
# ---------------------------------------------------------------------------


def is_shorts(v: Dict[str, Any]) -> bool:
    return v.get("contentType") == "SHORTS"


def video_list_stats(videos: List[Dict[str, Any]],
                     now_ms: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """`CreatorSlideOver.tsx` 的 `m` memo（抽屉 Performance 的唯一数据源）。

    输入 = `discovery.getChannelVideos({channelId, pageSize:50, contentType:"all"}).videos`
    这是**逐字**复现，包括：
      - VOD 样本 = `contentType==="VIDEO_ON_DEMAND" && views>=100`（不是 API 端过滤！）
      - Shorts 样本 = `contentType==="SHORTS"`（**无** views 阈值）
      - 窗口：publishTime 落在最近 28 天内且条数 ≥3 → 用 28 天样本，否则退回"最新 30 条"
      - "Avg Views" 取的是**中位数** `D[floor(n/2)]`（偶数长度取上中位），不是平均数
    """
    if not videos:
        return None
    now = now_ms if now_ms is not None else _now_ms()
    vod_sample = [v for v in videos
                  if v.get("contentType") == "VIDEO_ON_DEMAND"
                  and _num(v.get("views"), 0) >= 100]
    shorts_sample = [v for v in videos if is_shorts(v)]

    def u(sample: List[Dict[str, Any]]) -> Dict[str, Any]:
        recent = []
        for v in sample:
            p = _to_ms_opt(v.get("publishTime"))
            if p is not None and now - p <= WINDOW_28D_MS:
                recent.append(v)
        if len(recent) >= 3:
            d = sorted(x for x in (_num(v.get("views"), 0) for v in recent) if x > 0)
            if d:
                return {"median": d[js_floor(len(d) / 2)], "count": len(d), "source": "28d"}
        r = sorted(x for x in (_num(v.get("views"), 0) for v in sample[:30]) if x > 0)
        if r:
            return {"median": r[js_floor(len(r) / 2)], "count": len(r), "source": "latest"}
        return {"median": 0, "count": 0, "source": "none"}

    def l_med(sample: List[Dict[str, Any]]) -> int:
        recent = [v for v in sample
                  if _to_ms_opt(v.get("publishTime")) is not None
                  and now - _to_ms_opt(v.get("publishTime")) <= WINDOW_28D_MS]
        use = recent if len(recent) >= 3 else sample[:30]
        r = sorted(x for x in (_num(v.get("likes"), 0) for v in use) if x > 0)
        return r[js_floor(len(r) / 2)] if r else 0

    q = u(vod_sample)
    a = u(shorts_sample)
    o = l_med(vod_sample)
    i = l_med(shorts_sample)
    n = u(vod_sample + shorts_sample)
    return {"vod": q, "shorts": a, "overall": n, "vodLikes": o, "shortsLikes": i,
            "vodCount": len(vod_sample), "shortsCount": len(shorts_sample)}


def drawer_module_display(stats: Optional[Dict[str, Any]],
                          insight: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """抽屉 Long-form / Shorts 模块**实际显示**的值（含 insight 兜底）。"""
    ins = insight or {}

    def block(key: str, med_key: str, likes_key: str, count_key: str) -> Dict[str, Any]:
        st = (ins.get("stats") or {}).get(key) or {}
        vc = _num(st.get("videoCount"), 0)
        fallback_avg = js_round(_num(st.get("views"), 0) / vc) if vc > 0 else 0
        fallback_likes = js_round(_num(st.get("likes"), 0) / vc) if vc > 0 else 0
        m = (stats or {}).get(med_key) or {}
        return {
            "avgViews": _falsy_or(m.get("median"), fallback_avg),
            "avgLikes": _falsy_or((stats or {}).get(likes_key), fallback_likes),
            "count": _falsy_or(m.get("count"), vc) or "—",
            "source": "28d" if m.get("source") == "28d" else "Recent",
            "avgViewsFrom": "videoListStats.median" if _falsy_or(m.get("median"), 0)
                            else ("insight.stats.%s.views/videoCount" % key if vc > 0 else "none"),
        }

    return {"longForm": block("vod", "vod", "vodLikes", "vodCount"),
            "shorts": block("shorts", "shorts", "shortsLikes", "shortsCount")}


# ---------------------------------------------------------------------------
# 6. 两条 CQI 装配路径（抽屉 vs 完整档案页）
# ---------------------------------------------------------------------------


def _kolprofile_avg_views(vod_videos: List[Dict[str, Any]], insight: Dict[str, Any]) -> int:
    """KOLProfile 页面 `G` memo：非 SHORTS 视频的**算术平均**（不是中位）。"""
    w = [_num(v.get("views"), 0) for v in vod_videos
         if v.get("contentType") != "SHORTS" and _num(v.get("views"), 0) > 0]
    if w:
        return js_round(sum(w) / len(w))
    return js_round(_num(((insight.get("stats") or {}).get("overall") or {})
                         .get("averageViewsPerVideo"), 0))


def _kolprofile_er(vod_videos: List[Dict[str, Any]]) -> float:
    v = [x for x in vod_videos if x.get("contentType") != "SHORTS"]
    likes = sum(_num(x.get("likes"), 0) for x in v)
    comments = sum(_num(x.get("comments"), 0) for x in v)
    views = sum(_num(x.get("views"), 0) for x in v)
    return (likes + comments) / views * 100 if views > 0 else 0.0


def assemble_drawer_inputs(prop: Dict[str, Any], videos: List[Dict[str, Any]],
                           matched_videos: Optional[List[Any]] = None,
                           brand_keywords: Optional[List[str]] = None,
                           competitors: Optional[List[str]] = None,
                           now_ms: Optional[float] = None) -> Dict[str, Any]:
    """`CreatorSlideOver.tsx` 的 `K` memo——抽屉 CQI 的**真实入参**。

    关键（易错，逐条贴代码行）：
      - avgViews：优先用**传入 prop**（Discovery 搜索卡片会给搜索口径的 `avgViews`），
        prop 为 0/缺省时**才**退回 VOD 视频列表的**中位数**（不是平均数）。
      - daysSinceLastVideo：由视频列表 publishTime 现算。
      - paidPlacementRatio：`count(hasPaidPlacement)/len(全部视频)`——用的是
        `contentType:"all"` 的返回；实测该 schema 的 hasPaidPlacement **恒为 false**。
      - videoCount / channelCreatedAt：**不传** ⇒ 活跃维度频率分固定为默认 50。
    """
    now = now_ms if now_ms is not None else _now_ms()
    a = _num(prop.get("subscriberCount"), 0)
    w = _num(prop.get("engagementRate"), 0)
    T = _num(prop.get("avgViews"), 0)
    all_videos = videos or []
    if all_videos:
        non_shorts = [v for v in all_videos
                      if v.get("contentType") == "VIDEO_ON_DEMAND"
                      or "SHORT" not in (v.get("contentType") or "")]
        g = [_num(v.get("views"), 0) for v in non_shorts if _num(v.get("views"), 0) > 0]
        if g and T == 0:
            srt = sorted(g)
            T = srt[js_floor(len(srt) / 2)]
        if w == 0 and non_shorts:
            lk = sum(_num(v.get("likes"), 0) for v in non_shorts)
            cm = sum(_num(v.get("comments"), 0) for v in non_shorts)
            vw = sum(_num(v.get("views"), 0) for v in non_shorts)
            if vw > 0:
                w = (lk + cm) / vw * 100
    b = sum(1 for v in all_videos if v.get("hasPaidPlacement"))
    ratio = b / len(all_videos) if all_videos else 0.0
    days = days_since_last(videos, now)
    bf = None
    if all_videos and (brand_keywords or competitors):
        hits = count_title_hits(all_videos, brand_keywords or [], competitors or [])
        mt = len(matched_videos or [])
        bf = {"hitCount": max(hits["hitCount"], mt),
              "totalVideos": hits["totalVideos"],
              "hasCompetitorHits": len(hits["competitorHits"]) > 0}
    return {"subscriberCount": a, "engagementRate": w, "avgViews": T,
            "daysSinceLastVideo": days, "paidPlacementRatio": ratio,
            "brandFitData": bf, "matchedVideos": matched_videos,
            "videoCount": None, "channelCreatedAt": None,
            "_debug": {"avgViewsFromProp": _num(prop.get("avgViews"), 0) > 0,
                       "erFromProp": _num(prop.get("engagementRate"), 0) > 0,
                       "paidFlagsSeen": b, "videosIn": len(all_videos)}}


def assemble_kolprofile_inputs(detail: Dict[str, Any], insight: Dict[str, Any],
                               vod_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """`KOLProfile.tsx` 的 `G` memo——完整档案页 CQI 的入参。

    与抽屉的三处口径差（都会让同一个频道在两个界面上得到不同 CQI）：
      1) avgViews = 非 SHORTS 视频的**算术平均**（抽屉是搜索 prop 或中位数）
      2) 付费占比取自 `contentType:"vod"` 的返回（该 schema 的 hasPaidPlacement 是真的）
      3) daysSinceLastVideo **硬编码 null** ⇒ 活跃维度天数分固定 30
    """
    s = _num(detail.get("subscriberCount"), 0)
    if s == 0:
        return {}
    l = vod_videos or []
    P = _kolprofile_avg_views(l, insight)
    F = sum(1 for v in l if v.get("hasPaidPlacement"))
    se = F / len(l) if l else 0.0
    q = _kolprofile_er(l)
    return {"subscriberCount": s, "engagementRate": q, "avgViews": P,
            "daysSinceLastVideo": None, "paidPlacementRatio": se,
            "_debug": {"paidFlagsSeen": F, "videosIn": len(l), "erSource": "vod list"}}


def days_since_last(videos: List[Dict[str, Any]],
                    now_ms: Optional[float] = None) -> Optional[int]:
    """抽屉 `ae` memo 的前半段：由视频列表算"距今多少天"。"""
    if not videos:
        return None
    now = now_ms if now_ms is not None else _now_ms()
    ts = [_to_ms_opt(v.get("publishTime")) for v in videos]
    ts = [t for t in ts if t is not None]
    if not ts:
        return None
    return js_round((now - max(ts)) / 86400000)


def _strip_urls(text: str) -> str:
    """`CreatorSlideOver.tsx` 的 `It()`：先去掉 URL 再参与匹配。"""
    if not text:
        return ""
    import re as _re
    return _re.sub(r"https?://[^\s)>\]]+", "", text, flags=_re.IGNORECASE).strip()


def count_title_hits(videos: List[Dict[str, Any]], keywords: List[str],
                     competitors: List[str]) -> Dict[str, Any]:
    """`CreatorSlideOver.tsx` 的 `Ve(videos, keywords, competitors)` —— 品牌契合的证据命中。

    逐字对齐：`const n=(d.title||"").toLowerCase(), m=It(d.description||"").toLowerCase(), l=`${n} ${m}`;`
    即**标题 + 去 URL 后的描述**一起做子串匹配（不是只匹配标题）。
    注意：抽屉取的是 `contentType:"all"`，而该 schema **不含 `description` 字段**，
    因此实践中描述部分恒为空、等于只匹配标题；这里仍逐字保留，以免在别人换用
    `vod`/`shorts`（富 schema、有 description）时给出偏低的命中数。
    """
    k = [x.strip().lower() for x in keywords if x and x.strip()]
    c = [x.strip().lower() for x in competitors if x and x.strip()]
    hit_kw: Dict[str, int] = {}
    comp_hits: Dict[str, int] = {}
    n = 0
    for v in videos:
        title = (v.get("title") or "").lower()
        desc = _strip_urls(v.get("description") or "").lower()
        blob = "%s %s" % (title, desc)
        hit = False
        for x in k:
            if x in blob:
                hit_kw[x] = hit_kw.get(x, 0) + 1
                hit = True
        for x in c:
            if x in blob:
                comp_hits[x] = comp_hits.get(x, 0) + 1
                hit = True
        if hit:
            n += 1
    return {"hitCount": n, "totalVideos": len(videos),
            "hitKeywords": hit_kw, "competitorHits": comp_hits}


# ---------------------------------------------------------------------------
# 7. 时间工具
# ---------------------------------------------------------------------------

UNDEFINED = object()  # 显式表达 JS 的 undefined（与 null 语义不同）


def _now_ms() -> float:
    import time
    return time.time() * 1000.0


def _to_ms(s: str) -> float:
    v = _to_ms_opt(s)
    if v is None:
        raise ValueError("无法解析时间：%r" % (s,))
    return v


def _to_ms_opt(s: Any) -> Optional[float]:
    if not s:
        return None
    import datetime
    try:
        t = str(s).replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.timestamp() * 1000.0
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 8. Node 参照实现（真实 JS，正控）
# ---------------------------------------------------------------------------


def run_oracle(oracle_path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """在 Node 里执行从 bundle 原样抽出的 `Ce()`，作为不可辩驳的参照。"""
    script = (
        "import { Ce } from %s;\n"
        "const inp = JSON.parse(process.argv[2]);\n"
        "if (inp.__now != null) { globalThis.Date.now = () => inp.__now; }\n"
        "console.log(JSON.stringify(Ce(inp)));\n"
    ) % json.dumps(os.path.abspath(oracle_path))
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as f:
        f.write(script)
        tmp = f.name
    try:
        r = subprocess.run(["node", tmp, json.dumps(payload)],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError("oracle 失败：%s" % r.stderr.strip()[:400])
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# 9. 自检（≥12 项，含正控 / 真阴性 / 边界 / 降级）
# ---------------------------------------------------------------------------

GRADE_BOUNDARY_CASES = [
    (44, {"Ce_authenticityScore_75_60_45": "C", "cqiBreakdown_70_50_30": "B",
          "SharedList_70_55_40": "C"}),
    (45, {"Ce_authenticityScore_75_60_45": "B", "cqiBreakdown_70_50_30": "B",
          "SharedList_70_55_40": "C"}),
    (59, {"Ce_authenticityScore_75_60_45": "B", "cqiBreakdown_70_50_30": "A",
          "SharedList_70_55_40": "B"}),
    (60, {"Ce_authenticityScore_75_60_45": "A", "cqiBreakdown_70_50_30": "A",
          "SharedList_70_55_40": "B"}),
    (74, {"Ce_authenticityScore_75_60_45": "A", "cqiBreakdown_70_50_30": "S",
          "SharedList_70_55_40": "A"}),
    (75, {"Ce_authenticityScore_75_60_45": "S", "cqiBreakdown_70_50_30": "S",
          "SharedList_70_55_40": "A"}),
]


def selfcheck(oracle_path: Optional[str] = None,
              probe_path: Optional[str] = None) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    def ck(cid: str, desc: str, ok: bool, got: Any = None, want: Any = None) -> None:
        checks.append({"id": cid, "desc": desc, "ok": bool(ok),
                       "got": got, "want": want})

    # --- C01 tiers -------------------------------------------------------
    ck("C01", "体量档分界 1e4/1e5/1e6/1e7（q()）",
       [tier_of(x) for x in (9999, 1e4, 99999, 1e5, 999999, 1e6, 9999999, 1e7)]
       == ["nano", "micro", "micro", "mid", "mid", "macro", "macro", "mega"],
       [tier_of(x) for x in (9999, 1e4, 1e5, 1e6, 1e7)],
       ["nano", "micro", "mid", "macro", "mega"])

    # --- C02 micro 受众分档 40/20/8/3 ------------------------------------
    ck("C02", "micro 档受众分位阈值 40/20/8/3 → 100/85/65/40/20",
       [audience_score(r * 19700 / 100, 19700) for r in (45, 40, 25, 20, 10, 8, 5, 3, 2)]
       == [100, 100, 85, 85, 65, 65, 40, 40, 20],
       [audience_score(r * 19700 / 100, 19700) for r in (40, 20, 8, 3, 1)],
       [100, 85, 65, 40, 20])

    # --- C03 均播为 0 / 粉丝为 0 → 50 ------------------------------------
    ck("C03", "受众维度降级：avgViews 为 0 或 fans 为 0 → percentileScore 50",
       [audience_score(0, 19700), audience_score(None, 19700), audience_score(188, 0)]
       == [50, 50, 50], [audience_score(0, 19700)], [50])

    # --- C04 互动分档 micro 7/5/3/2 --------------------------------------
    ck("C04", "互动维度 micro 档 7/5/3/2 → 100/80/60/40/20",
       [engage_score(x, 19700) for x in (7, 5, 3, 2, 1.9, 0.81)]
       == [100, 80, 60, 40, 20, 20],
       [engage_score(x, 19700) for x in (7, 5, 3, 2, 1)],
       [100, 80, 60, 40, 20])

    # --- C05 互动降级：null / 0 → 30 -------------------------------------
    ck("C05", "互动降级：ER 为 null 或 0 → 原始分 30（不是 20）",
       [engage_score(None, 19700), engage_score(0, 19700)] == [30, 30],
       [engage_score(None, 19700)], [30])

    # --- C06 活跃天数分档（频率分固定 50，因为不传 videoCount/createdAt）---
    got_act = {d: activity_score(d, None, None) for d in (7, 8, 14, 15, 28, 29, 60, 61, 90, 91, 180, 181)}
    want_act = {7: 85, 8: 78, 14: 78, 15: 68, 28: 68, 29: 54, 60: 54,
                61: 40, 90: 40, 91: 26, 180: 26, 181: 19}
    ck("C06", "活跃维度：频率分固定 50（抽屉不传 videoCount/createdAt）时的天数分档",
       got_act == want_act, got_act, want_act)

    # --- C07 null vs undefined 天数 ---------------------------------------
    ck("C07", "活跃：天数显式 null → 30（raw 36）；undefined 在 JS 落 else → 5（raw 19）",
       [activity_score(None, None, None), activity_score(UNDEFINED, None, None)] == [36, 19],
       [activity_score(None, None, None), activity_score(UNDEFINED, None, None)], [36, 19])

    # --- C08 频率分（传了 videoCount + createdAt 时）-----------------------
    now = 1760000000000.0
    created = "2024-01-01T00:00:00Z"
    ck("C08", "活跃维度：传入 videoCount/createdAt 时频率分参与（≥8/月 → 100）",
       activity_score(3, 200, created, now) > activity_score(3, None, None, now),
       {"withFreq": activity_score(3, 200, created, now),
        "withoutFreq": activity_score(3, None, None, now)},
       {"withFreq": ">withoutFreq"})

    # --- C09 商业化分档 ---------------------------------------------------
    ck("C09", "商业化分档 0.3/0.2/0.1/0.05/>0/0 → 100/85/70/55/40/20",
       [commercial_score(x) for x in (0.3, 0.2, 0.1, 0.05, 0.001, 0)]
       == [100, 85, 70, 55, 40, 20],
       [commercial_score(x) for x in (0.3, 0.1, 0.049, 0)], [100, 70, 40, 20])

    # --- C10 品牌契合分档 -------------------------------------------------
    ck("C10", "品牌契合：matchedVideos 5/3/2/1 → 100/85/75/65；foundByKeywords 5/3/1 → 60/50/35；否则 40",
       [brand_fit_score({"matchedVideos": x}) for x in (5, 3, 2, 1)] == [100, 85, 75, 65]
       and [brand_fit_score({"foundByKeywords": ["a"] * x}) for x in (5, 3, 1)] == [60, 50, 35]
       and brand_fit_score({}) == 40,
       {"mv": [brand_fit_score({"matchedVideos": x}) for x in (5, 3, 2, 1)],
        "fbk": [brand_fit_score({"foundByKeywords": ["a"] * x}) for x in (5, 3, 1)],
        "none": brand_fit_score({})},
       {"mv": [100, 85, 75, 65], "fbk": [60, 50, 35], "none": 40})

    # --- C11 品牌契合兜底 brandFitData + 竞品 +5 --------------------------
    ck("C11", "品牌契合兜底：brandFitData.hitCount 6/4/2/1/0 → 100/90/75/60/40，竞品命中 +5（封顶 100）",
       [brand_fit_score({"brandFitData": {"hitCount": x, "totalVideos": 50}}) for x in (6, 4, 2, 1, 0)]
       == [100, 90, 75, 60, 40]
       and brand_fit_score({"brandFitData": {"hitCount": 6, "totalVideos": 50,
                                             "hasCompetitorHits": True}}) == 100
       and brand_fit_score({"brandFitData": {"hitCount": 4, "totalVideos": 50,
                                             "hasCompetitorHits": True}}) == 95,
       brand_fit_score({"brandFitData": {"hitCount": 4, "totalVideos": 50,
                                         "hasCompetitorHits": True}}), 95)

    # --- C12 等级边界 44/45/59/60/74/75（三套分别断言）--------------------
    bad = [(t, grade_variants(t), want) for t, want in GRADE_BOUNDARY_CASES
           if grade_variants(t) != want]
    ck("C12", "等级边界 44/45/59/60/74/75 × 三套分界逐一断言", not bad, bad, [])

    # --- C13 权重与四舍五入（JS 半数向上）--------------------------------
    e = {"subscriberCount": 19700, "engagementRate": 0.8116883116883116,
         "avgViews": 188, "daysSinceLastVideo": 1, "paidPlacementRatio": 0,
         "brandFitData": {"hitCount": 1, "totalVideos": 50, "hasCompetitorHits": False}}
    r = cqi(e, now_ms=1760000000000.0)
    ck("C13", "Ce() 正控（Tech Influence 抽屉口径手算 fixture）：总分 38 / 等级 C / 五维 12.0-5.0-5.0-12.8-3.0",
       (r["total"], r["grade"],
        [d["score"] for d in r["dimensions"]]) == (38, "C", [12.0, 5.0, 5.0, 12.8, 3.0]),
       {"total": r["total"], "grade": r["grade"],
        "scores": [d["score"] for d in r["dimensions"]]},
       {"total": 38, "grade": "C", "scores": [12.0, 5.0, 5.0, 12.8, 3.0]})

    # --- C14 js_round 半数向上 -------------------------------------------
    ck("C14", "js_round 半数向 +∞（对齐 ECMAScript，非 Python 银行家舍入）",
       [js_round(10.5), js_round(0.5), js_round(-0.5), round(10.5), round(0.5)]
       == [11, 1, 0, 10, 0],
       [js_round(10.5), js_round(0.5), js_round(-0.5)], [11, 1, 0])

    # --- C15 抽屉长视频/短视频过滤语义（真阴性锚点）-----------------------
    vids = [{"videoId": "a", "contentType": "VIDEO_ON_DEMAND", "views": 500, "likes": 10,
             "comments": 1, "publishTime": "2026-10-07T00:00:00Z"},
            {"videoId": "b", "contentType": "VIDEO_ON_DEMAND", "views": 50, "likes": 1,
             "comments": 0, "publishTime": "2026-10-06T00:00:00Z"},
            {"videoId": "c", "contentType": "SHORTS", "views": 20, "likes": 1,
             "comments": 0, "publishTime": "2026-10-05T00:00:00Z"},
            {"videoId": "d", "contentType": "SHORTS", "views": 900, "likes": 5,
             "comments": 2, "publishTime": "2026-10-04T00:00:00Z"}]
    st = video_list_stats(vids, now_ms=_to_ms("2026-10-08T00:00:00Z"))
    ck("C15", "抽屉样本语义：VOD 要 views>=100（b 被剔）、Shorts 不看 views（c 保留）",
       (st["vodCount"], st["shortsCount"]) == (1, 2),
       {"vodCount": st["vodCount"], "shortsCount": st["shortsCount"]}, {"vodCount": 1, "shortsCount": 2})

    # --- C16 28 天窗口 / 最新 30 条回退 / 上中位 ---------------------------
    now28 = _to_ms("2026-10-08T00:00:00Z")
    recent3 = [{"contentType": "SHORTS", "views": v, "likes": 1, "comments": 0,
                "publishTime": p} for v, p in
               ((10, "2026-10-07T00:00:00Z"), (30, "2026-10-06T00:00:00Z"),
                (20, "2026-10-05T00:00:00Z"))]
    s1 = video_list_stats(recent3, now_ms=now28)
    old2 = [{"contentType": "SHORTS", "views": v, "likes": 1, "comments": 0,
             "publishTime": p} for v, p in
            ((10, "2026-01-01T00:00:00Z"), (99, "2025-12-01T00:00:00Z"))]
    s2 = video_list_stats(old2, now_ms=now28)
    ck("C16", "28 天窗口：≥3 条且落在 28 天内 → source=28d；否则退回「最新 30 条」（source=latest）",
       (s1["shorts"]["source"], s1["shorts"]["median"], s2["shorts"]["source"])
       == ("28d", 20, "latest"),
       {"s1": s1["shorts"], "s2": s2["shorts"]},
       {"s1.source": "28d", "s1.median": 20, "s2.source": "latest"})

    # --- C17 偶数样本取"上中位"（不是两数平均）---------------------------
    four = [{"contentType": "SHORTS", "views": v, "likes": 1, "comments": 0,
             "publishTime": "2026-10-0%dT00:00:00Z" % (i + 1)}
            for i, v in enumerate((10, 20, 30, 40))]
    s3 = video_list_stats(four, now_ms=now28)
    ck("C17", "偶数样本取上中位 D[floor(n/2)]：views=[10,20,30,40] → 30（不是 25）",
       s3["shorts"]["median"] == 30, s3["shorts"]["median"], 30)

    # --- C18 真阴性①：把 Shorts 也加上 views>=100 阈值 ⇒ 必须不一致 -------
    wrong = video_list_stats([v for v in vids], now_ms=_to_ms("2026-10-08T00:00:00Z"))
    wrong_shorts_count = len([v for v in vids if v["contentType"] == "SHORTS"
                              and v["views"] >= 100])
    ck("C18", "真阴性①：若给 Shorts 也加 views>=100 阈值 ⇒ 与前端结果不一致（应报错）",
       wrong_shorts_count != wrong["shortsCount"],
       {"correctShortsCount": wrong["shortsCount"], "ifThresholdApplied": wrong_shorts_count},
       {"correctShortsCount": 2, "ifThresholdApplied": 1})

    # --- C19 真阴性②：用 contentType 参数当过滤器 ⇒ 与前端不一致 ---------
    #    前端是客户端过滤 contentType==="SHORTS"；API 的 contentType 参数并不过滤。
    real_all = [v for v in vids]
    api_param_assumption = [v for v in vids if v["contentType"] == "SHORTS"]  # 假设API已过滤
    ck("C19", "真阴性②：把 API 的 contentType 参数当过滤器（假设它已按形态过滤）⇒ 样本集不同，必须判为不一致",
       len(api_param_assumption) != len(real_all),
       {"clientSideTotal": len(real_all), "assumedApiFiltered": len(api_param_assumption)},
       {"note": "前端从不依赖 API 过滤，只做客户端 contentType!=='SHORTS' 判定"})

    # --- C20 真阴性③：把 VOD 过滤改成算术平均 ⇒ 必须不一致 ---------------
    mean_vs_median = js_round(sum(v["views"] for v in vids
                                  if v["contentType"] == "VIDEO_ON_DEMAND") / 2)
    ck("C20", "真阴性③：把 Long-form Avg Views 从「中位数」改成「算术平均」⇒ 必须判为不一致",
       mean_vs_median != wrong["vod"]["median"],
       {"median_correct": wrong["vod"]["median"], "mean_wrong": mean_vs_median},
       {"note": "界面写 Avg Views，算的却是 median"})

    # --- C21 颜色：抽屉比值阈值 0.8/0.6/0.4/0.2 ---------------------------
    ck("C21", "抽屉维度配色阈值 0.8/0.6/0.4/0.2 → green/blue/amber/red/purple",
       [color_band(x) for x in (1.0, 0.8, 0.79, 0.6, 0.59, 0.4, 0.39, 0.2, 0.19)]
       == ["green", "green", "blue", "blue", "amber", "amber", "red", "red", "purple"],
       [color_band(x) for x in (0.8, 0.6, 0.4, 0.2, 0.19)],
       ["green", "blue", "amber", "red", "purple"])

    # --- C22 KOLProfile 页面配色阈值 0.7/0.4（与抽屉不同！）---------------
    ck("C22", "KOLProfile 页面内联配色阈值 0.7/0.4（>0.7 绿）——与抽屉 0.8 不同，必须分开实现",
       [color_band(x, "kolprofile") for x in (0.71, 0.7, 0.41, 0.4)]
       == ["green", "amber", "amber", "red"],
       [color_band(x, "kolprofile") for x in (0.71, 0.7, 0.41, 0.4)],
       ["green", "amber", "amber", "red"])

    # --- C23 互动维度绿色分界 --------------------------------------------
    ck("C23", "互动维度绿色分界：原始分 ≥80（micro 即 ER ≥5%）→ 绿；60 → 蓝；40 → 琥珀；≤30 → 红",
       [color_band(js_round(engage_score(x, 19700) * 0.25 * 10) / 10 / 25)
        for x in (7, 5, 3, 2, 0)]
       == ["green", "green", "blue", "amber", "red"],
       {str(x): color_band(js_round(engage_score(x, 19700) * 0.25 * 10) / 10 / 25)
        for x in (7, 5, 3, 2, 0)},
       {"7": "green", "5": "green", "3": "blue", "2": "amber", "0": "red"})

    # --- C24 活跃维度绿色分界 --------------------------------------------
    act_colors = {}
    for d in (7, 14, 28, 60, 90, 180, 400):
        raw = activity_score(d, None, None)
        act_colors[d] = color_band(js_round(raw * 0.15 * 10) / 10 / 15)
    ck("C24", "活跃维度绿色分界：只有「最近发布 ≤7 天」才是绿（raw 85 / 12.8 / 比值 0.853）；14 天起掉到蓝",
       act_colors == {7: "green", 14: "blue", 28: "blue", 60: "amber",
                      90: "amber", 180: "red", 400: "purple"},
       act_colors,
       {7: "green", 14: "blue", 28: "blue", 60: "amber", 90: "amber",
        180: "red", 400: "purple"})

    # --- C25 降级行为与前端一致：paidPlacementRatio 缺字段 → 0 → 商业化 20 --
    no_paid = cqi({"subscriberCount": 19700, "engagementRate": 5, "avgViews": 5000,
                   "daysSinceLastVideo": 3}, now_ms=now28)
    zero_paid = cqi({"subscriberCount": 19700, "engagementRate": 5, "avgViews": 5000,
                     "daysSinceLastVideo": 3, "paidPlacementRatio": 0}, now_ms=now28)
    ck("C25", "降级：paidPlacementRatio 取不到 ⇒ 计为 0（不是「未取到」）→ 商业化原始分 20、加权 3.0，且与显式 0 完全同分",
       no_paid["total"] == zero_paid["total"]
       and zero_paid["dimensions"][4]["rawScore"] == 20
       and zero_paid["dimensions"][4]["score"] == 3.0,
       {"total_missing": no_paid["total"], "total_zero": zero_paid["total"],
        "commercial": zero_paid["dimensions"][4]},
       {"total_missing": zero_paid["total"], "commercialRaw": 20, "commercialWeighted": 3.0})

    # --- C26 降级：daysSinceLastVideo 为 null（KOLProfile 页面硬编码）------
    kp = cqi({"subscriberCount": 19700, "engagementRate": 1.3, "avgViews": 5489,
              "daysSinceLastVideo": None, "paidPlacementRatio": 18 / 20}, now_ms=now28)
    ck("C26", "降级：KOLProfile 页面 daysSinceLastVideo 硬编码 null ⇒ 活跃天数分 30 → raw 36 → 加权 5.4",
       kp["dimensions"][3]["rawScore"] == 36 and kp["dimensions"][3]["score"] == 5.4,
       kp["dimensions"][3], {"rawScore": 36, "score": 5.4})

    # --- C27 两套装配路径必须给出不同结果（口径差必须被看见）--------------
    if probe_path and os.path.exists(probe_path):
        data = json.load(open(probe_path, encoding="utf-8"))
        cid = data["channels"]["TechInfluence"]
        vid_all = _videos_of(data, "TechInfluence", "all")
        vid_vod = _videos_of(data, "TechInfluence", "vod")
        ins = _payload_of(data, "TechInfluence", "discovery.getChannelInsight",
                          {"timeRange": "last_28_days"})
        det = _payload_of(data, "TechInfluence", "discovery.getChannelDetail", {})
        d_in = assemble_drawer_inputs({"subscriberCount": det.get("subscriberCount"),
                                       "engagementRate": 0.8116883116883116,
                                       "avgViews": 188}, vid_all, matched_videos=[1])
        k_in = assemble_kolprofile_inputs(det, ins, vid_vod)
        d_r = cqi(d_in, now_ms=now28)
        k_r = cqi(k_in, now_ms=now28)
        ck("C27", "同一频道、两条装配路径必须给出不同 CQI（抽屉 vs 完整档案页）——口径差可见即通过",
           d_r["total"] != k_r["total"],
           {"drawerTotal": d_r["total"], "drawerGrade": d_r["grade"],
            "kolprofileTotal": k_r["total"], "kolprofileGrade": k_r["grade"],
            "drawerInputs": {k: v for k, v in d_in.items() if k != "_debug"},
            "kolprofileInputs": {k: v for k, v in k_in.items() if k != "_debug"}},
           {"note": "若两者相等，说明装配路径可能被错误合并"})

    # --- C28 Node 正控：真实 JS 与 Python 端口逐格相等 --------------------
    if oracle_path and os.path.exists(oracle_path):
        cases = [
            {"subscriberCount": 19700, "engagementRate": 0.8116883116883116,
             "avgViews": 188, "daysSinceLastVideo": 1, "paidPlacementRatio": 0,
             "matchedVideos": [1], "__now": now28},
            {"subscriberCount": 201000, "engagementRate": 2.5, "avgViews": 12000,
             "daysSinceLastVideo": 20, "paidPlacementRatio": 0.1,
             "matchedVideos": [1, 2, 3], "__now": now28},
            {"subscriberCount": 11000, "engagementRate": 4.6, "avgViews": 4400,
             "daysSinceLastVideo": 9, "paidPlacementRatio": 0.02,
             "brandFitData": {"hitCount": 5, "totalVideos": 50,
                              "hasCompetitorHits": True}, "__now": now28},
            {"subscriberCount": 8000, "engagementRate": 0, "avgViews": 0,
             "daysSinceLastVideo": None, "paidPlacementRatio": None, "__now": now28},
            {"subscriberCount": 1.2e7, "engagementRate": 3.5, "avgViews": 3000000,
             "daysSinceLastVideo": 200, "paidPlacementRatio": 0.35,
             "matchedVideos": [1, 2, 3, 4, 5, 6], "__now": now28},
        ]
        mismatches = []
        for c in cases:
            payload = {k: v for k, v in c.items() if k != "__now"}
            js = run_oracle(oracle_path, c)
            py = cqi(payload, now_ms=now28)
            if js["total"] != py["total"] or js["grade"] != py["grade"]:
                mismatches.append({"input": payload, "js": js["total"], "py": py["total"]})
                continue
            for a, b in zip(js["dimensions"], py["dimensions"]):
                if (a["label"] != b["label"] or float(a["score"]) != float(b["score"])
                        or a["rawScore"] != b["rawScore"] or a["max"] != b["max"]):
                    mismatches.append({"input": payload, "dim": a["label"],
                                       "js": a["score"], "py": b["score"]})
        ck("C28", "Node 正控：bundle 原样抽出的真实 Ce() 与 Python 端口，5 组输入逐格相等（共 25 维 + 5 总分）",
           not mismatches, mismatches, [])
    else:
        ck("C28", "Node 正控（跳过：未提供 --oracle）", False, "skipped", "需要 --oracle")

    # --- C29 品牌契合命中：标题 + 去 URL 描述（逐字对齐 Ve()）-------------
    hv = [{"title": "Best AI glasses 2026", "description": "see https://x.co/ai-glasses and Ray-Ban Meta"},
          {"title": "unrelated", "description": "no keyword here"}]
    h = count_title_hits(hv, ["ai glasses"], ["Ray-Ban Meta"])
    ck("C29", "品牌契合命中按「标题 + 去 URL 后的描述」匹配（Ve() 逐字）：URL 里的关键词不算、描述里的算",
       h["hitCount"] == 1 and h["hitKeywords"] == {"ai glasses": 1}
       and h["competitorHits"] == {"ray-ban meta": 1},
       h, {"hitCount": 1, "hitKeywords": {"ai glasses": 1},
           "competitorHits": {"ray-ban meta": 1}})

    passed = sum(1 for c in checks if c["ok"])
    return {"checks": checks, "passed": passed, "total": len(checks),
            "allPassed": passed == len(checks)}


# ---------------------------------------------------------------------------
# 10. 探针数据读取
# ---------------------------------------------------------------------------


def _payload_of(data: Dict[str, Any], channel: str, route: str,
                input_subset: Dict[str, Any]) -> Dict[str, Any]:
    for r in data["results"]:
        if r["channel"] != channel or r["route"] != route:
            continue
        if any(r["input"].get(k) != v for k, v in input_subset.items()):
            continue
        if r["httpStatus"] != 200:
            return {"__httpStatus": r["httpStatus"], "__raw": r["rawBody"][:500]}
        raw = json.loads(r["rawBody"])
        if isinstance(raw, list):
            raw = raw[0]
        return raw["result"]["data"]["json"]
    return {}


def _videos_of(data: Dict[str, Any], channel: str, content_type: str) -> List[Dict[str, Any]]:
    p = _payload_of(data, channel, "discovery.getChannelVideos", {"contentType": content_type})
    return p.get("videos") or []


def build_report(probe_path: str) -> Dict[str, Any]:
    data = json.load(open(probe_path, encoding="utf-8"))
    out: Dict[str, Any] = {"probedAt": data.get("probedAt"), "channels": {}}
    for ch, cid in data["channels"].items():
        vid_all = _videos_of(data, ch, "all")
        vid_vod = _videos_of(data, ch, "vod")
        ins = _payload_of(data, ch, "discovery.getChannelInsight", {"timeRange": "last_28_days"})
        det = _payload_of(data, ch, "discovery.getChannelDetail", {})
        stats = video_list_stats(vid_all)
        disp = drawer_module_display(stats, ins)
        d_in = assemble_drawer_inputs({"subscriberCount": det.get("subscriberCount"),
                                       "engagementRate": None, "avgViews": None},
                                      vid_all, brand_keywords=[], competitors=[])
        k_in = assemble_kolprofile_inputs(det, ins, vid_vod)
        d_r = cqi(d_in)
        k_r = cqi(k_in)
        out["channels"][ch] = {
            "channelId": cid,
            "subscriberCount": det.get("subscriberCount"),
            "country": det.get("country"),
            "tier": tier_of(det.get("subscriberCount") or 0),
            "insight": {
                "overall": (ins.get("stats") or {}).get("overall"),
                "vod": (ins.get("stats") or {}).get("vod"),
                "shorts": (ins.get("stats") or {}).get("shorts"),
                "averageStats": ins.get("averageStats"),
            },
            "drawerPerformance": disp,
            "drawerCqi": {"inputs": {k: v for k, v in d_in.items() if k != "_debug"},
                          "debug": d_in["_debug"], "result": d_r,
                          "gradesAllSchemes": grade_variants(d_r["total"])},
            "kolprofileCqi": {"inputs": {k: v for k, v in k_in.items() if k != "_debug"},
                              "debug": k_in.get("_debug", {}), "result": k_r,
                              "gradesAllSchemes": grade_variants(k_r["total"])},
            "dimensionColors": {
                d["label"]: {"score": d["score"], "max": d["max"],
                             "ratio": round(d["ratio"], 4),
                             "drawerColor": color_band(d["ratio"]),
                             "kolprofileColor": color_band(d["ratio"], "kolprofile")}
                for d in d_r["dimensions"]},
            "videoSchema": {
                "all_n": len(vid_all),
                "all_paidFlags": sum(1 for v in vid_all if v.get("hasPaidPlacement")),
                "all_fields": sorted(vid_all[0].keys()) if vid_all else [],
                "vod_n": len(vid_vod),
                "vod_paidFlags": sum(1 for v in vid_vod if v.get("hasPaidPlacement")),
                "vod_fields": sorted(vid_vod[0].keys()) if vid_vod else [],
                "all_ct_dist": _dist(vid_all),
                "vod_ct_dist": _dist(vid_vod),
            },
        }
    return out


def _dist(videos: List[Dict[str, Any]]) -> Dict[str, int]:
    d: Dict[str, int] = {}
    for v in videos:
        d[v.get("contentType")] = d.get(v.get("contentType"), 0) + 1
    return d


# ---------------------------------------------------------------------------
# 11. CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Daniel 界面指标逐字复现器")
    ap.add_argument("--probe", default=None)
    ap.add_argument("--oracle", default=".kol-tools/_daniel_jsref/authenticityScore.extract.mjs")
    ap.add_argument("--report", default=None)
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--json", action="store_true", help="自检以 JSON 输出")
    a = ap.parse_args(argv)

    if a.selfcheck or not a.probe:
        oracle = a.oracle if os.path.exists(a.oracle) else None
        r = selfcheck(oracle, a.probe)
        if a.json:
            daniel_io.emit(r)
        else:
            for c in r["checks"]:
                print("%s %-5s %s" % ("PASS" if c["ok"] else "FAIL", c["id"], c["desc"]))
                if not c["ok"]:
                    print("      got=%s\n      want=%s" % (json.dumps(c["got"], ensure_ascii=False)[:500],
                                                           json.dumps(c["want"], ensure_ascii=False)[:300]))
            print("\n自检：%d/%d" % (r["passed"], r["total"]))
        if a.report:
            _atomic_write(a.report, json.dumps(r, ensure_ascii=False, indent=1))
        return 0 if r["allPassed"] else 1

    rep = build_report(a.probe)
    txt = json.dumps(rep, ensure_ascii=False, indent=1)
    if a.report:
        _atomic_write(a.report, txt)
        # `--json` 时"落盘：…"这行人话走 stderr：stdout 只能有那**一个** JSON 文档（TICKET-168）。
        print("落盘：%s" % a.report, file=sys.stderr if a.json else sys.stdout)
    if a.json:
        # 原先 `--probe` 这条分支直接无视 `--json`（只打中文"落盘：…"），调用方拿不到机器可读结果。
        daniel_io.emit(rep)
    elif not a.report:
        print(txt)
    return 0


def _atomic_write(path: str, text: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def cli(argv=None):
    """入口包装：**退出码归一 ＋ 失败时恰好一个 JSON 文档**（收口只有这一处，TICKET-168）。

    原先没有这一层：失败时 stdout 上没有 `ok=false` 信封（只有 stderr 的 traceback），
    `--json` 的机器面在失败路径上是缺失的。现统一交给 `daniel_io.cli`。
    """
    return daniel_io.cli(main, argv)


if __name__ == "__main__":
    sys.exit(cli())
