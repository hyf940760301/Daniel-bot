#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daniel_authenticity.py —— Daniel「Authenticity（真实性）」分数的**逐字复算器**。

## 为什么有这个文件（TICKET-133 专项结论）
Daniel 前端 `/authenticity` 页面**没有对应后端算分路由**：页面只用三条**只读**路由
（`discovery.resolveChannelInput` / `discovery.getChannelDetail` / `discovery.getChannelVideos`），
分数在**浏览器里现算** ⇒ **Authenticity 不可写**（详见
`docs/marketing/kol/_daniel-integration/03-intel-core.md`）。
本文件把该算分口径**逐字移植成 Python**，使我们能在**交付物**（表格/报告/名单）里交付同一个数——
与 Daniel 页面同口径、可复算、可离线自检。

## 逐字口径来源
`https://daniel-agent.com` 前端 chunk → `.kol-tools/_daniel_bundle/authenticityScore-a-IZvxEl.pretty.js`
（页面入口 `.kol-tools/_daniel_bundle/Authenticity-BbKZOlW8.pretty.js`，见其
`x=i.useMemo(()=>D(h.data?.videos,l.data?.subscriberCount||0),[...])`，`D` ＝ 本文件 `authenticity_from_videos`）。

### 入口：`je(videos, subscriberCount)`（逐字）
```js
function je(e,t){
  const o=(e??[]).filter(i=>Number(i.views??0)>=100).slice(0,50);
  return o.length<3?null:{
    ...ve({views:o.map(i=>Number(i.views??0)),likes:o.map(i=>Number(i.likes??0)),
           comments:o.map(i=>Number(i.comments??0)),subscriberCount:Math.max(0,t||0)}),
    sampleSize:o.length,samplePolicy:"latest_50_min_100_views"
  }
}
```
⇒ 取样口径：**观看量 ≥100 的视频，取前 50 条，少于 3 条不出分**。

### 总分：`ve({views,likes,comments,subscriberCount})`（逐字，权重行）
```js
const O=Math.max(0,Math.min(100,Math.round(p*.4+h*.2+b*.12+F*.08+C*.2)));
```
| 维度 | 变量 | 权重 | 满分 | 上限 |
|---|---|---|---|---|
| View-Engagement Match（评论/播放匹配） | `p` | **0.40** | 40 | — |
| Interact Rate（互动率） | `h` | **0.20** | 20 | — |
| Subscriber Engagement（订阅互动 VPR） | `C` | **0.20** | 20 | — |
| Fluctuation（播放波动 CV） | `b` | **0.12** | 12 | — |
| Like/Comment（点赞评论比） | `F` | **0.08** | 8 | — |
| 合计 | | **1.00** | 100 | 结果 `clamp(0,100,round(Σ))` |

### 等级（两套，逐字）
- `ve` 返回 `label`：`>=80 "Highly Authentic"` / `>=60 "Normal"` / `>=40 "Some Concerns"` / else `"Suspicious"`
- `Me(score)`（`AuthenticityRings` 徽标用）：`>=80 "Authentic"` / `>=60 "Normal"` / `>=40 "Concerns"` / else `"Suspicious"`
- 颜色：`>=70 text-emerald-600` / `>=40 text-amber-600` / else `text-red-500`
- 分数 **-1 ＝ 数据不足（Insufficient Data）**，不是"0 分"。

### 分段打分器 `V(e,t,o,n,i,r,s,M)`（逐字，5 个信号共用）
```js
function V(e,t,o,n,i,r,s,M={}){
  const{inverted:l=!1,hardCeiling:f,hardFloor:p}=M;
  if(f!==void 0&&e>f||p!==void 0&&e<p)return 0;
  if(l){
    if(e>=n)return 100;
    if(e>=o)return 100-Math.round((n-e)/(n-o)*20);
    if(e>=t)return 80-Math.round((o-e)/(o-t)*30);
    const d=t-e,g=t*.8;return Math.max(0,g>0?50-Math.round(d/g*50):0)
  }else{
    if(e<=n)return 100;
    if(e<=i)return 100-Math.round((e-n)/(i-n)*20);
    if(e<=r)return 80-Math.round((e-i)/(r-i)*25);
    if(e<=s)return 55-Math.round((e-r)/(s-r)*25);
    const d=e-s,g=s*.5;return Math.max(0,30-Math.round(d/g*30))
  }
}
```
> 阈值语义（**这是"分母"**）：非反向时 `e<=n →100`；`n..i` 段 100→80；`i..r` 段 80→55；`r..s` 段 55→30；
> 超过 `s` 后按 `s*0.5` 线性掉到 0。反向时 `e>=n →100`，往下对称衰减。

### 逐信号口径（逐字常量）
1. **View-Engagement Match**：`g = Σviews/Σcomments`（无评论时 `g=99999`）
   参数表（按订阅数分档，`hardCeiling`）：
   | 订阅数 | t | o | n | i | r | s | hardCeiling |
   |---|---|---|---|---|---|---|---|
   | ≥1e7 | 360 | 360 | 634 | 1127 | 2596 | 3429 | 15000 |
   | ≥2e6 | 382 | 382 | 612 | 1005 | 1830 | 2474 | 10000 |
   | ≥5e5 | 296 | 296 | 467 | 856 | 2115 | 4244 | 15000 |
   | ≥1e5 | 175 | 175 | 385 | 758 | 1680 | 2637 | 10000 |
   | else | 144 | 144 | 265 | 539 | 1508 | 2020 | 8000 |
   额外扣分（`d` ＝ VPR%）：`d>12` 时 `m = d>65 ? round((100-a)*.5) : d>30 ? round((100-a)*.35) : round((100-a)*.2)`，`p = max(0, a-m)`。
   特例：评论数为 0 时 `p = d>10 ? 0 : 15`。
2. **Interact Rate**：`S = (Σlikes+Σcomments)/Σviews*100`，反向打分（`hardFloor:0.1`）：
   | 订阅数 | t | o | n | i | r | s |
   |---|---|---|---|---|---|---|
   | ≥1e7 | 1.16 | 1.81 | 2.94 | 3.99 | 6.1 | 7.21 |
   | ≥2e6 | 1.24 | 1.91 | 3.02 | 4.64 | 7.54 | 8.74 |
   | ≥5e5 | 1.21 | 2.05 | 3.36 | 4.79 | 6.44 | 7.97 |
   | ≥1e5 | 0.8 | 1.68 | 3.22 | 5.27 | 7.46 | 7.88 |
   | else | 1.07 | 1.73 | 3.25 | 5.49 | 8.27 | 9.84 |
3. **Fluctuation**：`CV = sqrt(Σ(v-mean)^2/n)/mean`
   | 订阅数 | y | L | A | k | x |
   |---|---|---|---|---|---|
   | ≥1e7 | .36 | .47 | .60 | .87 | 1.13 |
   | ≥2e6 | .35 | .47 | .70 | 1.03 | 1.76 |
   | ≥5e5 | .39 | .49 | .76 | 1.12 | 1.79 |
   | ≥1e5 | .43 | .58 | .91 | 1.40 | 1.82 |
   | else | .46 | .67 | 1.02 | 1.44 | 1.86 |
   分段：`CV<.1→5`；`<y→5+round((CV-.1)/(y-.1)*25)`；`<L→30+round((CV-y)/(L-y)*30)`；
   `<A→85+round((A-CV)/(A-L)*10)`；`<k→70+round((k-CV)/(k-A)*15)`；`<x→50+round((x-CV)/(x-k)*20)`；
   `<x*1.5→30+round((x*1.5-CV)/(x*.5)*20)`；else `max(10, 30-round((CV-x*1.5)/x*20))`。
4. **Like/Comment**：`Σlikes/Σcomments`，非反向 `V(a,3.96,7.72,14.15,23.13,37.1,51.37,{hardCeiling:200})`。
   特例：likes=0 且 comments=0 → **20**；likes>0 且 comments=0 → **15**。
5. **Subscriber Engagement**：`VPR% = mean(views)/subs*100`，`ne(avgViews, subs)`：
   - mega / macro：`>=10→100 / >=5→85 / >=2→70 / >=1→45 / >=.5→25 / >=.1→10 / else 0`
   - mid：`>=15→100 / >=8→85 / >=3→70 / >=2→55 / >=1→35 / >=.5→20 / else 5`
   - micro / nano：`>=20→100 / >=10→85 / >=5→75 / >=2→60 / else 40`
   - `subs==0 或 avgViews==0 → 50`

## 纪律
- **只读**：本文件联网时只调 `discovery.resolveChannelInput` / `discovery.getChannelDetail` /
  `discovery.getChannelVideos`（与 Daniel 页面**同三条**），**不发任何写请求**。
- `--self-test` **纯离线**（≥10 项），含从 Daniel 前端 JS **实跑得到的黄金值**（见 `GOLDEN`）。
"""
import argparse
import json
import math
import os
import sys

if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    # 兄弟模块 daniel_io：脚本直跑与被别的仪器当库载入两条路都要能 import（TICKET-168）。
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daniel_io  # noqa: E402  （TICKET-168：`--json` 出口的唯一收口层）

# ---------------------------------------------------------------- 逐字常量
# Q（Re 用的分位表）：mega/macro/mid/micro/nano
TIER_PERCENTILE = {
    "mega": (27, 18, 5, 1),
    "macro": (32, 10, 1.3, .5),
    "mid": (28, 11, 3.6, 1.2),
    "micro": (40, 20, 8, 3),
    "nano": (60, 30, 15, 5),
}
TIER_LABEL = {
    "mega": "Mega (10M+)",
    "macro": "Macro (1M–10M)",
    "mid": "Mid-size (100K–1M)",
    "micro": "Micro (10K–100K)",
    "nano": "Nano (<10K)",
}
# te：僵尸号判定下限（ratio%）
ZOMBIE_MIN_RATIO = {"mega": 1, "macro": 1, "mid": 2, "micro": 3, "nano": 5}

SAMPLE_MIN_VIEWS = 100
SAMPLE_MAX = 50
MIN_SAMPLE = 3

# 信号权重（逐字：p*.4 + h*.2 + b*.12 + F*.08 + C*.2）
WEIGHTS = {"view_engagement": .4, "interact_rate": .2, "subscriber_engagement": .2,
           "fluctuation": .12, "like_comment": .08}

# 维度 1 / 2 / 3 的分档参数（逐字表）
VIEW_ENGAGEMENT_TABLE = [  # (min_subs, t, o, n, i, r, s, hard_ceiling)
    (10_000_000, 360, 360, 634, 1127, 2596, 3429, 15000),
    (2_000_000, 382, 382, 612, 1005, 1830, 2474, 10000),
    (500_000, 296, 296, 467, 856, 2115, 4244, 15000),
    (100_000, 175, 175, 385, 758, 1680, 2637, 10000),
    (0, 144, 144, 265, 539, 1508, 2020, 8000),
]
INTERACT_RATE_TABLE = [  # (min_subs, t, o, n, i, r, s)  inverted, hardFloor .1
    (10_000_000, 1.16, 1.81, 2.94, 3.99, 6.1, 7.21),
    (2_000_000, 1.24, 1.91, 3.02, 4.64, 7.54, 8.74),
    (500_000, 1.21, 2.05, 3.36, 4.79, 6.44, 7.97),
    (100_000, .8, 1.68, 3.22, 5.27, 7.46, 7.88),
    (0, 1.07, 1.73, 3.25, 5.49, 8.27, 9.84),
]
FLUCTUATION_TABLE = [  # (min_subs, y, L, A, k, x)
    (10_000_000, .36, .47, .6, .87, 1.13),
    (2_000_000, .35, .47, .7, 1.03, 1.76),
    (500_000, .39, .49, .76, 1.12, 1.79),
    (100_000, .43, .58, .91, 1.4, 1.82),
    (0, .46, .67, 1.02, 1.44, 1.86),
]
LIKE_COMMENT_THRESHOLDS = (3.96, 7.72, 14.15, 23.13, 37.1, 51.37)
LIKE_COMMENT_CEILING = 200


def js_round(x):
    """JS `Math.round`（.5 向上取整），与 Python 内建 banker's rounding **不同**。"""
    return math.floor(x + .5) if x >= 0 else -math.floor(-x + .5)


def js_fixed(x, n):
    """JS `Number.prototype.toFixed(n)` 的显示口径（四舍五入、.5 远离 0）；**只影响文案，不影响分数**。"""
    from decimal import Decimal, ROUND_HALF_UP
    q = Decimal(1).scaleb(-n)
    return str(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def tier_of(subs):
    """逐字 `q(e)`：>=1e7 mega / >=1e6 macro / >=1e5 mid / >=1e4 micro / else nano。"""
    subs = subs or 0
    if subs >= 10_000_000:
        return "mega"
    if subs >= 1_000_000:
        return "macro"
    if subs >= 100_000:
        return "mid"
    if subs >= 10_000:
        return "micro"
    return "nano"


def tier_percentile(subs):
    """逐字 `Re(e)`：分档 + p90/p75/p50/p25 门槛（**展示口径**，非写库口径）。"""
    t = tier_of(subs)
    o, n, i, r = TIER_PERCENTILE[t]
    return {"tier": t, "tierLabel": TIER_LABEL[t], "p90": o, "p75": n, "p50": i, "p25": r}


def percentile_score(avg_views, subs):
    """逐字 `Y(e,t)`：只有 `percentileScore` 参与总分之外的信息；`isZombie` 供风控提示。"""
    if not avg_views or avg_views == 0 or subs == 0:
        return {"ratio": 0, "percentileScore": 50, "isZombie": False, "tier": tier_of(subs)}
    o = tier_of(subs)
    n = avg_views / subs * 100
    i = TIER_PERCENTILE[o]
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
    return {"ratio": n, "percentileScore": r,
            "isZombie": subs >= 100_000 and n < ZOMBIE_MIN_RATIO[o], "tier": o}


def subscriber_engagement_score(avg_views, subs):
    """逐字 `ne(e,t)`：VPR% 分档（维度 5 的"Active/Audience"信号）。"""
    if not avg_views or avg_views == 0 or subs == 0:
        return 50
    o = tier_of(subs)
    n = avg_views / subs * 100
    if o in ("mega", "macro"):
        return 100 if n >= 10 else 85 if n >= 5 else 70 if n >= 2 else 45 if n >= 1 else 25 if n >= .5 else 10 if n >= .1 else 0
    if o == "mid":
        return 100 if n >= 15 else 85 if n >= 8 else 70 if n >= 3 else 55 if n >= 2 else 35 if n >= 1 else 20 if n >= .5 else 5
    return 100 if n >= 20 else 85 if n >= 10 else 75 if n >= 5 else 60 if n >= 2 else 40


def piecewise(e, t, o, n, i, r, s, inverted=False, hard_ceiling=None, hard_floor=None):
    """逐字 `V(e,t,o,n,i,r,s,M)`。"""
    if (hard_ceiling is not None and e > hard_ceiling) or (hard_floor is not None and e < hard_floor):
        return 0
    if inverted:
        if e >= n:
            return 100
        if e >= o:
            return 100 - js_round((n - e) / (n - o) * 20)
        if e >= t:
            return 80 - js_round((o - e) / (o - t) * 30)
        d = t - e
        g = t * .8
        return max(0, 50 - js_round(d / g * 50) if g > 0 else 0)
    if e <= n:
        return 100
    if e <= i:
        return 100 - js_round((e - n) / (i - n) * 20)
    if e <= r:
        return 80 - js_round((e - i) / (r - i) * 25)
    if e <= s:
        return 55 - js_round((e - r) / (s - r) * 25)
    d = e - s
    g = s * .5
    return max(0, 30 - js_round(d / g * 30))


def _row(table, subs):
    for row in table:
        if subs >= row[0]:
            return row
    return table[-1]


def authenticity_score(views, likes, comments, subscriber_count):
    """逐字 `ve({views,likes,comments,subscriberCount})`。

    返回 `{"score": int|-1, "label", "shortLabel", "color", "signals":[...], "ratio","isZombie"}`。
    **score == -1 ⇒ 数据不足**（`views` 少于 3 条）。
    """
    views = [int(v or 0) for v in (views or [])]
    likes = [int(v or 0) for v in (likes or [])]
    comments = [int(v or 0) for v in (comments or [])]
    subs = max(0, int(subscriber_count or 0))
    if len(views) < MIN_SAMPLE:
        return {"score": -1, "label": "Insufficient Data", "shortLabel": "Insufficient Data",
                "color": "text-muted-foreground", "signals": [], "sampleSize": len(views)}
    s = sum(views)
    m = sum(likes)
    l = sum(comments)
    f = s / len(views)
    d = f / subs * 100 if subs > 0 else 0
    g = s / l if l > 0 else 99999
    signals = []

    # ---- 1. View-Engagement Match
    if l == 0:
        p = 0 if d > 10 else 15
        signals.append({"name": "View-Engagement Match", "status": "fail", "rawScore": p,
                        "detail": "No comments with %s%% View/Sub — highly suspicious" % js_fixed(d, 1)})
    else:
        row = _row(VIEW_ENGAGEMENT_TABLE, subs)
        a = piecewise(g, row[1], row[2], row[3], row[4], row[5], row[6], hard_ceiling=row[7])
        pen = 0
        if d > 12 and a < 100:
            pen = js_round((100 - a) * (.5 if d > 65 else .35 if d > 30 else .2))
        p = max(0, a - pen)
        status = "pass" if p >= 70 else "warn" if p >= 40 else "fail"
        tail = "(comments healthy)" if p >= 70 else "(comments not scaling with views)" if p >= 40 else "(views inflated — comments far behind)"
        signals.append({"name": "View-Engagement Match", "status": status, "rawScore": p,
                        "detail": "%s views/comment %s%s" % (js_fixed(g, 0), tail, " [+%dpt penalty: View/Sub %s%%]" % (pen, js_fixed(d, 0)) if pen > 0 else "")})

    # ---- 2. Interact Rate
    ir = (m + l) / s * 100 if s > 0 else 0
    row = _row(INTERACT_RATE_TABLE, subs)
    h = piecewise(ir, row[1], row[2], row[3], row[4], row[5], row[6], inverted=True, hard_floor=.1)
    signals.append({"name": "Interact Rate", "status": "pass" if h >= 70 else "warn" if h >= 40 else "fail",
                    "rawScore": h,
                    "detail": "%s%% %s" % (js_fixed(ir, 2), "(healthy)" if h >= 70 else "(low)" if h >= 40 else "(very low — suspicious)")})

    # ---- 3. Fluctuation
    mean = f
    var = sum((v - mean) ** 2 for v in views) / len(views)
    cv = math.sqrt(var) / mean if mean > 0 else 0
    y, L, A, k, x = _row(FLUCTUATION_TABLE, subs)[1:6]
    if cv < .1:
        b = 5
    elif cv < y:
        b = 5 + js_round((cv - .1) / (y - .1) * 25)
    elif cv < L:
        b = 30 + js_round((cv - y) / (L - y) * 30)
    elif cv < A:
        b = 85 + js_round((A - cv) / (A - L) * 10)
    elif cv < k:
        b = 70 + js_round((k - cv) / (k - A) * 15)
    elif cv < x:
        b = 50 + js_round((x - cv) / (x - k) * 20)
    elif cv < x * 1.5:
        b = 30 + js_round((x * 1.5 - cv) / (x * .5) * 20)
    else:
        b = max(10, 30 - js_round((cv - x * 1.5) / x * 20))
    cv_txt = ("(very stable)" if b >= 85 else "(stable with bursts)" if b >= 70 else "(volatile)" if b >= 50
              else "(too uniform or too volatile)" if b >= 30 else "(suspicious uniformity)")
    signals.append({"name": "Fluctuation", "status": "pass" if b >= 70 else "warn" if b >= 40 else "fail",
                    "rawScore": b, "detail": "CV %s %s" % (js_fixed(cv, 2), cv_txt)})

    # ---- 4. Subscriber Engagement（注：JS 里该信号先 push，再 push Like/Comment）
    ratio = percentile_score(f, subs)
    C = subscriber_engagement_score(f, subs)
    B = ratio["ratio"]
    if C >= 85:
        r_txt = "VPR %s%% — excellent subscriber engagement" % js_fixed(B, 2)
    elif C >= 70:
        r_txt = "VPR %s%% — strong subscriber engagement" % js_fixed(B, 2)
    elif C >= 55:
        r_txt = "VPR %s%% — healthy subscriber engagement" % js_fixed(B, 2)
    elif C >= 40:
        r_txt = "VPR %s%% — moderate engagement" % js_fixed(B, 2)
    elif C >= 20:
        r_txt = "VPR %s%% — low views vs subscribers" % js_fixed(B, 2)
    elif C >= 5:
        r_txt = "VPR %s%% — very low views vs subscribers (likely zombie followers)" % js_fixed(B, 2)
    else:
        r_txt = "VPR %s%% — nearly zero real viewership (zombie followers)" % js_fixed(B, 3)
    signals.append({"name": "Subscriber Engagement", "status": "pass" if C >= 70 else "warn" if C >= 40 else "fail",
                    "rawScore": C, "detail": r_txt})

    # ---- 5. Like/Comment
    if l == 0 and m == 0:
        F = 20
        signals.append({"name": "Like/Comment", "status": "fail", "rawScore": F, "detail": "No engagement"})
    elif l == 0:
        F = 15
        signals.append({"name": "Like/Comment", "status": "fail", "rawScore": F,
                        "detail": "Likes but zero comments — suspicious"})
    else:
        a = m / l
        F = piecewise(a, *LIKE_COMMENT_THRESHOLDS, hard_ceiling=LIKE_COMMENT_CEILING)
        signals.append({"name": "Like/Comment", "status": "pass" if F >= 70 else "warn" if F >= 40 else "fail",
                        "rawScore": F,
                        "detail": "%s:1 %s" % (js_fixed(a, 1), "(normal)" if F >= 70 else "(borderline)" if F >= 40 else "(abnormal)")})

    total = max(0, min(100, js_round(p * .4 + h * .2 + b * .12 + F * .08 + C * .2)))
    label = ("Highly Authentic" if total >= 80 else "Normal" if total >= 60
             else "Some Concerns" if total >= 40 else "Suspicious")
    color = "text-emerald-600" if total >= 70 else "text-amber-600" if total >= 40 else "text-red-500"
    return {"score": total, "label": label, "shortLabel": short_label(total), "color": color,
            "signals": signals, "viewToSubRatio": ratio["ratio"], "isZombie": ratio["isZombie"],
            "tier": tier_of(subs), "sampleSize": len(views)}


def short_label(score):
    """逐字 `Me(score)`（`AuthenticityRings` 徽标口径；与 `ve` 的 label 用词不同）。"""
    return "Authentic" if score >= 80 else "Normal" if score >= 60 else "Concerns" if score >= 40 else "Suspicious"


def authenticity_from_videos(videos, subscriber_count):
    """逐字 `je(videos, subscriberCount)`：取样 → 算分；样本 <3 返回 `None`。"""
    pool = [v for v in (videos or []) if int((v or {}).get("views") or 0) >= SAMPLE_MIN_VIEWS][:SAMPLE_MAX]
    if len(pool) < MIN_SAMPLE:
        return None
    r = authenticity_score([int(v.get("views") or 0) for v in pool],
                           [int(v.get("likes") or 0) for v in pool],
                           [int(v.get("comments") or 0) for v in pool],
                           max(0, int(subscriber_count or 0)))
    r["sampleSize"] = len(pool)
    r["samplePolicy"] = "latest_50_min_100_views"
    return r


def explain(score_result):
    """把分数摊成人话（交付物里给业务看的版本；内部口径不进主体）。"""
    if not score_result or score_result.get("score") == -1:
        return "样本不足（有效视频少于 3 条），不出分。"
    s = score_result["score"]
    if s >= 80:
        head = "真实性高，互动自然，未见异常信号。"
    elif s >= 60:
        head = "真实性正常，个别维度有波动但不构成风险。"
    elif s >= 40:
        head = "存在疑点，建议人工复核互动与订阅互动两项。"
    else:
        head = "真实性存疑，存在刷量/僵粉嫌疑，建议合作前人工复核。"
    weak = [x["name"] for x in score_result["signals"] if x["rawScore"] < 40]
    if weak:
        head += "（偏低项：%s）" % "、".join(weak)
    return head


# ---------------------------------------------------------------- 实跑（只读）
CHANNEL_VIDEOS_INPUT = {"pageSize": SAMPLE_MAX, "contentType": "all"}


def _client():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from daniel_client import Daniel  # noqa: E402
    return Daniel(verbose=False)


def resolve_channel(d, text):
    r = d.query("discovery.resolveChannelInput", {"input": text})
    if not r or not r.get("resolved"):
        raise SystemExit("无法解析该输入为 YouTube 频道：%s" % (r,))
    return r.get("channelId")


def fetch_channel(d, channel_id):
    detail = d.query("discovery.getChannelDetail", {"channelId": channel_id})
    videos = d.query("discovery.getChannelVideos", dict(CHANNEL_VIDEOS_INPUT, channelId=channel_id))
    return detail, (videos or {}).get("videos") or []


def cmd_channel(args):
    d = _client()
    cid = args.channel_id or resolve_channel(d, args.channel)
    detail, videos = fetch_channel(d, cid)
    res = authenticity_from_videos(videos, (detail or {}).get("subscriberCount") or 0)
    payload = {"channelId": cid, "channelTitle": (detail or {}).get("title"),
               "subscriberCount": (detail or {}).get("subscriberCount"),
               "videoPool": len([v for v in videos if int((v or {}).get("views") or 0) >= SAMPLE_MIN_VIEWS]),
               "authenticity": res}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        return
    if not res:
        print("真实性：**样本不足**（有效视频 <3 条）—— Daniel 页面同口径不出分")
        return
    print("频道：%s（%s）｜订阅 %s" % (payload["channelTitle"], cid, payload["subscriberCount"]))
    print("真实性得分：%d/100（%s）" % (res["score"], res["label"]))
    print("判读：%s" % explain(res))
    print("取样：最近 %d 条（口径 %s）" % (res["sampleSize"], res["samplePolicy"]))
    for s in res["signals"]:
        print("  - %-24s %3d  %s" % (s["name"], s["rawScore"], s["detail"]))


def cmd_videos_json(args):
    raw = json.load(open(args.videos_json, encoding="utf-8")) if args.videos_json != "-" else json.load(sys.stdin)
    videos = raw.get("videos") if isinstance(raw, dict) else raw
    subs = args.subs if args.subs is not None else (raw.get("subscriberCount") if isinstance(raw, dict) else 0)
    res = authenticity_from_videos(videos, subs)
    print(json.dumps(res, ensure_ascii=False, indent=1) if args.json else
          ("样本不足，不出分" if not res else "score=%d label=%s" % (res["score"], res["label"])))


# ---------------------------------------------------------------- 离线自检
GOLDEN = [  # 由 Daniel 前端 chunk 在 node v22 实跑得到（`tmp/daniel-auth-verify/golden.mjs`）
    ("basic_50k", [1000, 1200, 900], [50, 40, 30], [5, 4, 3], 50000, 81, [100, 100, 6, 60, 100]),
    ("zero_comments", [10000, 11000, 12000], [500, 400, 600], [0, 0, 0], 100000, 39, [0, 100, 5, 85, 15]),
    ("no_engagement", [10000, 11000, 12000], [0, 0, 0], [0, 0, 0], 100000, 19, [0, 0, 5, 85, 20]),
    ("likes_no_comments", [10000, 11000, 12000], [100, 100, 100], [0, 0, 0], 100000, 30, [0, 54, 5, 85, 15]),
    ("mega", [5000000, 4200000, 6100000, 3800000], [200000, 180000, 240000, 150000],
     [12000, 9000, 15000, 7000], 25000000, 89, [100, 100, 13, 100, 92]),
    ("micro", [3000, 2500, 4000], [150, 120, 200], [30, 20, 40], 20000, 86, [100, 100, 12, 85, 100]),
    ("uniform", [100000] * 4, [1000] * 4, [100] * 4, 2000000, 66, [80, 43, 5, 85, 100]),
    ("zombie", [200, 300, 250], [2, 3, 2], [0, 1, 0], 5000000, 55, [93, 41, 11, 0, 100]),
    ("low_views_filtered", [50, 99, 100, 5000, 6000], [1, 1, 5, 100, 120], [0, 0, 1, 10, 12], 200000, 81,
     [95, 87, 91, 35, 100]),
]


def _self_test():
    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    # 1..9 黄金值（与前端 JS 实跑逐位对比：总分 + 5 个信号 rawScore + 顺序）
    for name, views, likes, comments, subs, exp_score, exp_sig in GOLDEN:
        r = authenticity_from_videos(
            [{"views": v, "likes": l, "comments": c} for v, l, c in zip(views, likes, comments)], subs)
        got_sig = [s["rawScore"] for s in r["signals"]] if r else []
        ck("golden:%s" % name, r and r["score"] == exp_score and got_sig == exp_sig,
           "score=%s(want %s) signals=%s(want %s)" % (r and r["score"], exp_score, got_sig, exp_sig))

    # 10. 样本 <3 ⇒ None（页面显示"数据不足"）
    ck("sample_lt3_is_none", authenticity_from_videos([{"views": 1000}, {"views": 900}], 50000) is None)
    # 11. 取样口径：先过滤 views>=100，再取前 50
    many = [{"views": 50, "likes": 1, "comments": 1}] * 10 + [{"views": 1000, "likes": 10, "comments": 2}] * 60
    r = authenticity_from_videos(many, 100000)
    ck("sample_policy_50_min100", r and r["sampleSize"] == 50 and r["samplePolicy"] == "latest_50_min_100_views",
       "size=%s" % (r and r["sampleSize"]))
    # 12. 权重和 = 1.00（.4+.2+.12+.08+.2）
    ck("weights_sum_1", abs(sum(WEIGHTS.values()) - 1.0) < 1e-12, str(WEIGHTS))
    # 13. 总分恒在 0..100 且为整数
    r = authenticity_score([10 ** 9] * 3, [10 ** 8] * 3, [10 ** 7] * 3, 1000)
    ck("total_bounded", isinstance(r["score"], int) and 0 <= r["score"] <= 100, str(r["score"]))
    # 14. 等级阈值边界（逐字 80/60/40；短标签 Me 同界）
    ck("labels_boundary",
       short_label(80) == "Authentic" and short_label(79) == "Normal" and short_label(60) == "Normal"
       and short_label(59) == "Concerns" and short_label(40) == "Concerns" and short_label(39) == "Suspicious")
    # 15. 分段打分器 V：非反向/反向/硬上限（黄金值来自 JS 实跑）
    ck("V_noninverted", piecewise(500, 360, 360, 634, 1127, 2596, 3429) == 100
       and piecewise(900, 360, 360, 634, 1127, 2596, 3429) == 89
       and piecewise(99999, 360, 360, 634, 1127, 2596, 3429, hard_ceiling=15000) == 0)
    ck("V_inverted", piecewise(3.0, 1.16, 1.81, 2.94, 3.99, 6.1, 7.21, inverted=True, hard_floor=.1) == 100
       and piecewise(0.05, 1.16, 1.81, 2.94, 3.99, 6.1, 7.21, inverted=True, hard_floor=.1) == 0
       and piecewise(1.2, 1.16, 1.81, 2.94, 3.99, 6.1, 7.21, inverted=True, hard_floor=.1) == 52)
    # 16. 分档边界（q）：1e7/1e6/1e5/1e4
    ck("tier_boundaries", tier_of(10_000_000) == "mega" and tier_of(9_999_999) == "macro"
       and tier_of(1_000_000) == "macro" and tier_of(1_000_000 - 1) == "mid"
       and tier_of(100_000) == "mid" and tier_of(99_999) == "micro"
       and tier_of(10_000) == "micro" and tier_of(9_999) == "nano")
    # 17. VPR 分档（ne）黄金值：1e5 档 1000/1e5=1% ⇒ 35；1e6 档 0.1% ⇒ 10；0 views ⇒ 50
    ck("vpr_tiers", subscriber_engagement_score(1000, 100_000) == 35
       and subscriber_engagement_score(1000, 1_000_000) == 10
       and subscriber_engagement_score(0, 50_000) == 50)
    # 18. js_round ≠ Python round（.5 向上）
    ck("js_round_half_up", js_round(0.5) == 1 and js_round(1.5) == 2 and js_round(2.5) == 3)
    # 19. subscriberCount 负数被夹到 0（Math.max(0,t||0)）
    r = authenticity_from_videos([{"views": 1000, "likes": 10, "comments": 2}] * 3, -5)
    ck("subs_clamped", r is not None and r["signals"][-1]["name"] == "Like/Comment")
    # 20. explain() 对 -1 不出误导结论
    ck("explain_insufficient", "样本不足" in explain({"score": -1}))

    ok = sum(1 for _, p, _ in checks if p)
    for name, p, detail in checks:
        print("%s %s%s" % ("PASS" if p else "FAIL", name, "" if p else "  <- " + detail))
    print("self-test: %d/%d" % (ok, len(checks)))
    return ok == len(checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Daniel Authenticity 逐字复算器（只读）")
    ap.add_argument("--channel", help="YouTube 频道 URL / @handle / UC… id（走 discovery 只读路由）")
    ap.add_argument("--channel-id", help="已知 channelId，跳过解析")
    ap.add_argument("--videos-json", help="离线：视频 JSON 文件（[{views,likes,comments}] 或 {videos,subscriberCount}）")
    ap.add_argument("--subs", type=int, help="离线模式的订阅数")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--explain-weights", action="store_true", help="只打印权重口径")
    ap.add_argument("--self-test", action="store_true", help="离线自检（不联网）")
    a = ap.parse_args(argv)
    if a.self_test:
        return 0 if _self_test() else 1
    if a.json and a.explain_weights:
        # `--json` 的契约是 stdout 有且只有一个 JSON 文档；权重表是人读文本 —— 二选一（TICKET-168）。
        raise SystemExit("--json 与 --explain-weights 不能同用（后者打的是人读权重表）—— 请二选一")
    if a.explain_weights:
        total = 0
        for k, v in WEIGHTS.items():
            print("%-24s %5.2f  ⇒ 满分 %d" % (k, v, round(v * 100)))
            total += v
        print("%-24s %5.2f" % ("合计", total))
        return 0
    if a.videos_json:
        cmd_videos_json(a)
        return 0
    if a.channel or a.channel_id:
        cmd_channel(a)
        return 0
    # `--json` 时帮助文本走 stderr：stdout 只能有那**一个** JSON 文档（TICKET-168）。
    ap.print_help(file=sys.stderr) if a.json else ap.print_help()
    # 什么都没干就报 0 会被当成"查到了"：与同类仪器口径一致改成 2（用户错误，TICKET-168）。
    return 2


def cli(argv=None):
    """入口包装：**退出码归一 ＋ 失败时恰好一个 JSON 文档**（收口只有这一处，TICKET-168）。

    原先没有这一层：`SystemExit("无法解析该输入为 YouTube 频道…")`（用户错误）会带 traceback
    以 1 退出，上游据此判成"工具故障"；`--json` 时 stdout 上也没有 `ok=false` 信封。
    """
    return daniel_io.cli(main, argv)


if __name__ == "__main__":
    sys.exit(cli())
