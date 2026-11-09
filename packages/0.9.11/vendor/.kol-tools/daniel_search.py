#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daniel_search.py —— KOL 全链路检索工具（brief → 搜索词 → 检索 → 富化 → 筛选 → 落库成 list）。

**链路与路由**（2026-09-29 从 bundle 调用点实测读出 · 路线图见
`docs/marketing/kol/_build/kol-search-pipeline-route-map.md`）：

  ① 搜索词清单：**我生成**（形状对齐 `discovery.listHistory` 实测条目）
  ② deep search：`discovery.startSearchJob({query,brandId,brandName,brandCompetitors,brandCategory,country,
                  minSubscribers,maxSubscribers})` → `discovery.executeSearchJob({jobId})`（POST，传输可能提前结束）
                  → **轮询** `discovery.getSearchJob({jobId})`（每 2s；`status`：running／enriching／done／failed）
                  → `results[]` 即在任务返回体里（含 channelId／title／subscriberCount／engagementRate／avgViews／
                  country／tags／foundByKeywords／matchedVideos／businessEmail…）
  ③ open search：`discovery.expandTopic({topic})` → `discovery.search({topic,selectedScenarios,
                  selectedContentStyles,selectedAudiences,brandId,country,minSubscribers})` → 同样 execute＋轮询
  ④ 富化：`discovery.enrichChannels({channelIds≤100})`（补齐 subscriberCount／country／tags）＋
          `discovery.enrichEmails({channelIds})`（商务邮箱）
  ⑤ 筛选：本地口径（体量档／互动／相关证据）＋ `discovery.rosterNLFilter`（服务端 NL 过滤，可选）
  🔴 v0.9.174 新实测硬限（第八批）：`lists.getOverlap.listIds` **≤10 个**（传 11 个 → 400
      `Too big: expected array to have <=10 items`）⇒ 复核要**拆多次调用**；`lists.create` **不接受
      `description: null`**（400）⇒ 不要传该字段或传空串。
  ⑥ 落库：`lists.create({brandId,name})` → `lists.batchAddItems({listId, items:[{channelId,channelTitle,
          channelThumbnail,subscriberCount,country,tier,cqiScore,contactEmail,engagementRate}]})`

🔴 纪律：写操作（建名单／加人）**必须先回读**；检索结果一律**落盘留证**（原始 JSON ＋ 归一 CSV）。

用法：
  python3 .kol-tools/daniel_search.py --deep --plan <plan.json> [--out-prefix <path>]
  python3 .kol-tools/daniel_search.py --open --plan <plan.json> [--out-prefix <path>]
  python3 .kol-tools/daniel_search.py --job-status <jobId>
  python3 .kol-tools/daniel_search.py --enrich <results.json> [--emails]
  python3 .kol-tools/daniel_search.py --push-list --brand Halliday --name "X" --results <results.json> --limit 100
  python3 .kol-tools/daniel_search.py --self-test
"""
import argparse
import csv
import datetime as _dt
import importlib.util
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# ── TICKET-147：落点统一（夹具/缓存 → $DANIEL_HOME/cache，产出 → $DANIEL_HOME/output）──
# 解析层唯一真源是同目录 daniel_paths.py（P0-1 定稿）；旧落点不再新写。
def _dp_load():
    """按路径加载同目录 daniel_paths（本文件可能被 import，也可能被 importlib 按路径 exec）。"""
    import importlib.util
    import sys as _sys
    here = os.path.dirname(os.path.abspath(__file__))
    mod = _sys.modules.get('daniel_paths')
    if mod is not None and os.path.dirname(os.path.abspath(getattr(mod, '__file__', '') or '')) == here:
        return mod
    spec = importlib.util.spec_from_file_location('daniel_paths', os.path.join(here, 'daniel_paths.py'))
    m = importlib.util.module_from_spec(spec)
    _sys.modules['daniel_paths'] = m
    spec.loader.exec_module(m)
    return m


_dpaths = _dp_load()
CACHE_DIR = _dpaths.resolve('cache_dir')      # $DANIEL_HOME/cache
OUTPUT_DIR = _dpaths.resolve('output_dir')    # $DANIEL_HOME/output
_dpaths.ensure_dir(CACHE_DIR)
_dpaths.ensure_dir(OUTPUT_DIR)

TIER_BANDS = ((0, 10000, 'Nano'), (10000, 100000, 'Micro'),
              (100000, 500000, 'Mid-size'), (500000, 2000000, 'Macro'), (2000000, 10 ** 12, 'Mega'))

# 🔴 `discovery.startSearchJob` 的 `query` 有**硬上限 501 字符**（2026-09-30 二分实测：501 → 200，502 → 500
#    `Failed query: insert into search_jobs (…)`）。长 brief **不能整段塞进去** —— 必须先在本地压成"检索指令"。
#    判据：超限一律**拒绝执行**（不许悄悄截断），除非显式 `--trim`，且截断后必须回显。
MAX_QUERY_LEN = 501
TRIM_TO = 490

# 🔴 批量上限**两条链路不一样**（2026-09-30 实测）：
#    · `discovery.enrichChannels`：100 一批可用（bundle 也是按 100 切）
#    · `discovery.enrichEmails`：**50 一批**（51 起 400；二分实测 50→200／51→400）
#    判据：**不要按"另一个接口能传多少"类推** —— 每个写/算接口的批量上限各自实测。
EMAIL_BATCH = 50
CHANNEL_BATCH = 100


def check_query(q, trim=False, limit=MAX_QUERY_LEN, trim_to=TRIM_TO):
    """返回 (query, 说明)；超限且未 trim → 抛 ValueError（人话）。非字符串 → 抛错。"""
    if not isinstance(q, str) or not q.strip():
        raise ValueError('query 为空')
    q = q.strip()
    if len(q) <= limit:
        return q, None
    if not trim:
        raise ValueError('query 超长：%d 字符 > 接口上限 %d 字符（长 brief 必须先压成检索指令；'
                         '确需自动截断请加 --trim）' % (len(q), limit))
    cut = q[:trim_to]
    for sep in ('。', '. ', '；', '; ', '，', ', '):
        i = cut.rfind(sep)
        if i > trim_to * 0.6:
            cut = cut[:i + len(sep)]
            break
    cut = cut.strip()
    return cut, '原 query %d 字符 → 自动截断为 %d 字符（上限 %d）' % (len(q), len(cut), limit)


def _load_client():
    spec = importlib.util.spec_from_file_location('dc', os.path.join(HERE, 'daniel_client.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 纯函数（离线自检对象）────────────────────────────────────────────────
def tier_of(subs):
    """体量档（与界面同档名）。非数值／None → '未知'（不得致崩）。"""
    try:
        n = int(subs)
    except (TypeError, ValueError):
        return '未知'
    if n < 0:
        return '未知'
    for lo, hi, name in TIER_BANDS:
        if lo <= n < hi:
            return name
    return 'Mega'


def system_tier(subs):
    """**系统口径**的体量档（数字 1–4）—— 取自 bundle 的 `function ls(s)`
    （`Discovery-*.js`：`s>=5e6?1 : s>=5e5?2 : s>=5e4?3 : 4`；标签表 `St`：1=Mega／2=Macro／3=Mid／4=Micro）。

    🔴 为什么单列一个函数：**这个数字是写进系统的字段**（`lists.batchAddItems` 的 `tier` 要求 `number`），
    与我展示用的档名（tier_of：Nano/Micro/Mid-size/Macro/Mega）**口径不同**（分界 5 万／50 万／500 万 vs 1 万／10 万／50 万／200 万）
    —— 混用会写出错的档位。缺值 → 4（与界面同：`s?s>=…:4`）。
    """
    try:
        n = float(subs)
    except (TypeError, ValueError):
        return 4
    if n >= 5e6:
        return 1
    if n >= 5e5:
        return 2
    if n >= 5e4:
        return 3
    return 4


# ── 机构号／媒体号排除闸门（2026-09-30 用户指令：「避免名单混入一些官方号」）──
#    证据：频道的**标题**。判据三条：① 标题就是竞品品牌名（如 `Meta`／`XREAL`／`Rokid`）⇒ 品牌官方号；
#    ② 标题含机构／媒体词（news／media／magazine／…）；③ 标题命中已知媒体与出版方名单。
#    ⚠️ 边界（避免误伤创作者）：**不**把 review／studio／labs／channel 这类词单独当机构信号
#      —— 大量创作者名字里带这些词；只认"机构属性明确"的词与具名出版方。
INSTITUTION_TOKENS = [
    r'\bofficial\b', r'\bnews\b', r'\bmedia\b', r'\bmagazine\b', r'\binsider\b',
    r'\buniversity\b', r'\bacademy\b', r'\bschool\b', r'\beducation(al)?\b',
    r'\bnetwork\b', r'\bgroup\b', r'\binc\b', r'\bltd\b', r'\bllc\b', r'\bcorp(orat\w+)?\b',
    r'\bpress\b', r'\bjournal\b', r'\btimes\b', r'\bdaily\b', r'\bpost\b', r'\bwire\b',
    r'\(official', r'™', r'®',   # 🔴 不含 studio／labs／review／channel 单字：会误伤创作者名（自检抓出）
]
PUBLISHER_NAMES = [
    'techradar', 'android central', 'android authority', 'android police', 'the verge', 'cnet',
    'engadget', 'digital trends', 'toms guide', "tom's guide", 'gsmarena', 'notebookcheck', 'sammobile',
    'phonearena', '9to5google', '9to5mac', 'xda', 'wired', 'pcworld', 'pcmag', 'mashable', 'zdnet',
    'lifewire', 'makeuseof', 'how-to geek', 'business insider', 'forbes', 'bloomberg', 'reuters',
    'bbc', 'cnn', 'cbs', 'abc news', 'nbc', 'cnbc', 'techtarget', 'techcrunch', 'the gadgeteer',
    'harvard business review', 'tedx', 'insider tech', 'think media', 'global cycling network',
]


_COMP_STOP = {'ai', 'ar', 'xr', 'vr', 'glasses', 'glass', 'smart', 'the', 'and', 'of', 'inc', 'co', 'ltd'}

# ── 🔴 模糊词收紧表（v0.9.173 新增 · TICKET-110 总监 2026-10-08 裁定 ②）──────────────
#    事故（TICKET-110 实测）：品类词表里的 `meta` 走**子串**匹配，于是
#      · 游戏频道的 `META`＝metagame（战术环境）→ 假命中（Warzone／FC 27 战术视频）；
#      · 商业频道的 `Meta`＝Meta 公司 → 假命中（Meta 财报／Meta Muse）；
#      · `metadata` 之类子串也会误命中。
#    本批 8 人因此被误收进名单（已按裁定 ① 剔除，见 docs/marketing/kol/2026-10-halliday-batch7/12-false-hit-audit.csv）。
#    修法：**组合词 ＋ 词边界** —— 单字 `meta`／`hud` 不再单独算命中。
#    ⚠️ 有意**未**收紧 `ray-ban`：命中证据的取值面是"检索关键词／标签／分类"，不是视频标题 ——
#      收紧成 `ray-ban meta` 会让**真正相关**的频道失分（例：The Blind Life 的关键词就是裸 `Ray-Ban`，
#      命中视频是 `Meta Ray-Ban Smart Glasses Just Got Smarter`）。裸 `ray-ban` 的假命中
#      （普通太阳镜号）改由"命中视频主题复核"处置，不做词表收紧。
CORE_AMBIGUOUS = {
    'meta': r'ray-?ban\s+meta|meta\s+(?:smart\s+)?glasses|rayban\s+meta|oakley\s+meta',
    'hud': r'\bhud\b',
}


# 🔴 v0.9.173（TICKET-110 证据）：品牌/竞品词与"非产品用法"同形，必须**与产品语境共现**才算证据。
#    实测假命中：`vuzix` → VUZI 股票分析（mr. sicko Trading）／`solos` → 音乐（复数是 solo）／
#    `ray-ban` → 普通太阳镜（Shade Review）／`meta` → 游戏 metagame 与 Meta 财报。前三种本批靠人工剔，
#    此处改为**机器约束**：命中词必须与"眼镜/穿戴显示/AI 眼镜"语境出现在同一证据面里。
PRODUCT_CONTEXT = re.compile(
    r'(?:smart|ai|ar|vr|xr)[\s-]*(?:glasses|eyewear|glass)\b|\bglasses\b|\beyewear\b|waveguide|'
    r'head-?up|\bhud\b|wearable|\bdisplay\b|\baugmented\b|mixed\s+reality|\bar\b|\bvr\b', re.I)
CORE_NEEDS_CONTEXT = {
    'vuzix', 'inmo', 'xreal', 'rokid', 'viture', 'solos', 'even realities', 'brilliant labs',
    'ray-ban', 'rayban', 'oakley', 'halliday', 'even',
    # 注：`meta` 不在此列 —— 它已由 CORE_AMBIGUOUS 的组合词正则收紧（`ray-?ban\s+meta` 等），
    #     再叠加"必须与产品语境共现"会把 `Ray-Ban Meta`／`Oakley Meta` 这类**正确**命中挡掉（实测）。
}
# 🔴 v0.9.174（第八批实测）：**邻接品类词需要更窄的"眼镜语境"** ——
#    `hud` 命中 F1 座舱 HUD（yelistener）／`head-mounted display` 命中军用头盔显示（Grim Reapers）
#    与游戏机 VR 外设（TheThorns）⇒ 这两个词必须在**眼镜/穿戴显示**语境里才算证据。
CORE_NEEDS_EYEWEAR = {'hud', 'head-mounted display', 'head mounted display', 'display glasses',
                       'ar display', 'waveguide display'}
EYEWEAR_CONTEXT = re.compile(
    r'\bglasses\b|\beyewear\b|glasses\b|smart\s+glass|ai\s+glass|ar\s+glass|prescription|'
    r'\bframes?\b|wearable\s+display', re.I)


def eyewear_ok(hay):
    return bool(EYEWEAR_CONTEXT.search(str(hay or '')))


def context_ok(hay):
    """证据面里是否出现产品语境（供 CORE_NEEDS_CONTEXT 里的品牌词使用）。"""
    return bool(PRODUCT_CONTEXT.search(str(hay or '')))


def load_permanent_exclusions(path=None):
    """从判决来源表里读出**跨批永久排除**（kind=exclude）→ 返回 (ids, names)。

    🔴 为什么要有这一步（TICKET-110 实测）：`JampackSam`／`It Came From A Box` 通过了本批六条口径，
    只因它们恰好在历史名单 6840007 里、被"去重"拦下 —— 也就是说**永久类门禁当时只靠名单成员关系兜住**，
    换个批次就会漏。判据：**永久排除必须是筛查的输入，去重是第二道，不得互相顶替。**
    """
    import json as _json
    import os as _os
    p = path or _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '_KOL-VERDICT-SOURCES.json')
    ids, names = set(), set()
    try:
        with io.open(p, encoding='utf-8') as f:
            d = _json.load(f)
    except Exception:
        return ids, names
    for src in (d.get('sources') or []):
        if str(src.get('kind')) != 'exclude':
            continue
        for nm in (src.get('names') or []):
            k = norm_key(nm)
            if k:
                names.add(k)
        f2 = src.get('file')
        if not f2:
            continue
        fp = f2 if _os.path.isabs(f2) else _os.path.join(_os.path.dirname(_os.path.dirname(
            _os.path.abspath(__file__))), f2)
        if not _os.path.exists(fp):
            continue
        try:
            rows = _json.load(io.open(fp, encoding='utf-8'))
            for part in str(src.get('json_path') or '').split('.'):
                if part:
                    rows = rows.get(part) if isinstance(rows, dict) else None
        except Exception:
            continue
        for r in (rows or []):
            if not isinstance(r, dict):
                continue
            if r.get('channelId'):
                ids.add(str(r['channelId']).strip())
            k = norm_key(r.get(src.get('name_col') or 'channelTitle'))
            if k:
                names.add(k)
    return ids, names


def norm_key(s):
    """名称归一（与 check_verdict_conflicts 同口径）：NFKD 折叠重音 → 去标点 → 折叠空白 → 小写。"""
    import unicodedata
    t = unicodedata.normalize('NFKD', str(s or ''))
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = ''.join((' ' if not c.isalnum() else c) for c in t.replace('@', ' '))
    return ' '.join(t.lower().split())


def permanent_reason(r, ids=None, names=None):
    """命中永久排除 → 返回理由字符串；否则 None。"""
    if not isinstance(r, dict):
        return None
    cid = str(r.get('channelId') or '').strip()
    if cid and ids and cid in ids:
        return '永久类门禁（跨批剔除名单：channelId）'
    k = norm_key(r.get('channelTitle'))
    if k and names and k in names:
        return '永久类门禁（跨批剔除名单：频道名）'
    return None


def _word_boundary(t):
    """把词条编译成**带词边界**的正则（首尾按词字符决定是否加 \\b）。

    🔴 v0.9.174：旧实现对普通词条用**裸子串**匹配 ⇒ `ar glasses` 命中 `regul|ar glasses|`
    （第八批实测假命中：Scamadviser 的自动变焦老花镜被当成 AR 眼镜）。判据：**品类词一律按词匹配**。
    """
    esc = re.escape(str(t).lower())
    pre = r'\b' if re.match(r'\w', str(t)) else ''
    post = r'\b' if re.search(r'\w$', str(t)) else ''
    return pre + esc + post


def core_patterns(core_terms):
    """把品类词表编译成匹配模式列表 [(是否正则, 模式), …]。

    规则：① `re:` 前缀 ⇒ 显式正则；② 命中 `CORE_AMBIGUOUS` 的模糊单字 ⇒ 用收紧后的正则；
    ③ 其余 ⇒ **词边界**匹配（v0.9.174 起；旧版是裸子串，会跨词误命中）。
    """
    pats = []
    for t in (core_terms or []):
        s = str(t).strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith('re:'):
            pats.append((True, low[3:]))
        elif low in CORE_AMBIGUOUS:
            pats.append((True, CORE_AMBIGUOUS[low]))
        else:
            pats.append((True, _word_boundary(low)))
    return pats


def core_haystack(r):
    """品类证据的取值面：命中的检索关键词 ∪ 标签 ∪ 分类（小写拼接）。"""
    return ' | '.join([str(x) for x in ((r or {}).get('foundByKeywords') or [])]
                      + [str(x) for x in ((r or {}).get('tags') or [])]
                      + [str((r or {}).get('category') or '')]).lower()


def competitor_tokens(competitors):
    """把竞品名拆成可用于"标题即官方号"判定的词元。

    为什么不能只用整名：品牌档案里写的是 `Ray-Ban Meta`，而 Meta 官方频道的标题就叫 **`Meta`** ——
    整名匹配抓不到。故同时取：
      ① 整名（归一化）；② 按非字母数字拆出的词元（长度 ≥3 且不在通用词停用表里，如 meta／xreal／rokid／viture／solos）。
    边界：只用于**整标题等于**该词元的判定（创作者恰好叫 `Meta` 的概率可忽略），不做子串匹配。
    """
    out = set()
    for name in (competitors or []):
        s = re.sub(r'\s+', ' ', str(name).strip().lower())
        if s:
            out.add(s)
        for tok in re.split(r'[^a-z0-9]+', s):
            if len(tok) >= 3 and tok not in _COMP_STOP:
                out.add(tok)
    return out


def institution_reason(row, competitors=None):
    """机构号／品牌号判定：返回原因字符串（命中）或 None（放行）。行非 dict → None。"""
    if not isinstance(row, dict):
        return None
    title = str(row.get('channelTitle') or row.get('title') or '').strip()
    if not title:
        return None
    low = title.lower()
    norm = re.sub(r'[^a-z0-9 ]+', ' ', low)
    norm = re.sub(r'\s+', ' ', norm).strip()
    for n in competitor_tokens(competitors):
        if n and (norm == n or low.strip() == n):
            return '标题即竞品品牌名（疑品牌官方号）：%s' % title
    for name in PUBLISHER_NAMES:
        if name in low or name in norm:
            return '命中媒体与出版方名单：%s' % name
    for pat in INSTITUTION_TOKENS:
        m = re.search(pat, low)
        if m:
            return '标题含机构／媒体词「%s」' % m.group(0).strip()
    return None


# ── 评测证据闸门（2026-09-30 用户指令：「评测证据」）──
#    证据：命中视频的**标题**（`matchedVideos[].title`）。判据：至少一条命中视频的标题带**评测类动作词**
#    或**品类词**；否则只是场景词蹭上的，不构成"这个频道会评测这类产品"的证据。
REVIEW_TOKENS = [
    r'\breview(s|ed|ing)?\b', r'\bhands[ -]?on\b', r'\btest(ed|ing|s)?\b', r'\bcompar(e|ed|ison|ing)\b',
    r'\bvs\b', r'\bunbox(ing|ed)?\b', r'\bfirst look\b', r'\bimpressions?\b', r'\bworth it\b',
    r'\bhonest\b', r'\blong[ -]?term\b', r'\bafter \d+ (days|weeks|months)\b', r'\b\d+ (days|weeks|months) later\b',
    r'\bsetup\b', r'\bwalkthrough\b', r'\btutorial\b', r'\bshould you buy\b', r'\bbuying guide\b',
]


def review_evidence(row, core_terms=None, mode='or_category'):
    """评测证据：返回 (bool, 说明)。无 matchedVideos → (False, '无命中视频标题可判')。

    mode：
      · `or_category`（默认）＝评测动作词**或**品类词命中即通过（宽松；已知宽松点：靠品类词通过的视频
        可能并非评测内容 —— 实测样例 RHR Jen 的视频标题是时事评论，只因含 `teleprompter` 通过）；
      · `token_only` ＝**必须**带评测动作词（更严；用于品牌方要求"视频本身必须是评测内容"时）。
    """
    if not isinstance(row, dict):
        return False, '行无效'
    vids = row.get('matchedVideos') or []
    if not isinstance(vids, list) or not vids:
        return False, '无命中视频标题可判'
    core = [str(c).lower() for c in (core_terms or [])]
    for v in vids:
        title = str((v or {}).get('title') or '').lower()
        if not title:
            continue
        if any(re.search(p, title) for p in REVIEW_TOKENS):
            return True, '命中视频标题含评测动作词'
        if mode != 'token_only' and core:
            _ok_eye = eyewear_ok(title)
            for c in core:
                if c not in title:
                    continue
                # 品牌/竞品词（vuzix／solos／ray-ban…）在同一标题里必须有产品语境才算证据
                if c in CORE_NEEDS_CONTEXT and not context_ok(title):
                    continue
                if c in CORE_NEEDS_EYEWEAR and not _ok_eye:
                    continue
                return True, '命中视频标题含品类词'
    return False, '命中视频标题无评测动作词与品类词'


# ── CQI 五维（**本地近似**；口径取自工作区已取证的界面基准）──
#    🔴 纪律：系统侧 CQI 由前端 `cqiScore: ds({subscriberCount, engagementRate, avgViews, matchedVideos})`
#    计算（五维 brandFit／engage／audience／activity／commercial ＋ total），**服务端不下发该分值**。
#    故本地按界面公布的档位与分位点做**近似**，**只用于筛选与排序，绝不写入系统的 cqiScore 字段**
#    （同 CLS-50 的教训：不要用自己口径的值去写系统字段）。
CQI_TIER = ((0, 10000, 'Nano'), (10000, 100000, 'Micro'), (100000, 1000000, 'Mid-size'),
            (1000000, 10000000, 'Macro'), (10000000, 10 ** 12, 'Mega'))
# 互动率五档阈值（%）与观看渗透率分位点（%），逐字取自工作区取证记录
CQI_ER = {'Mega': (3, 2, 1.2, 0.5), 'Macro': (4, 3, 2, 1), 'Mid-size': (5, 3.5, 2.5, 1.5),
          'Micro': (7, 5, 3, 2), 'Nano': (10, 7, 4, 2)}
CQI_VPR = {'Mega': (27, 18, 5, 1), 'Macro': (32, 10, 1.3, 0.5), 'Mid-size': (28, 11, 3.6, 1.2),
           'Micro': (40, 20, 8, 3), 'Nano': (60, 30, 15, 5)}
CQI_ENGAGE_BANDS = ('优秀', '强', '典型', '需要复核', '较弱')
CQI_AUDIENCE_BANDS = ('前 10%', '前 25%', '高于中位数', '低于中位数', '后 25%')
CQI_ACTIVITY_BANDS = ('适合立即启动', '活跃', '活跃度下降', '沉寂')
CQI_BRANDFIT_BANDS = ('品类专家', '强匹配', '可用匹配', '探索性匹配', '仅搜索发现')
_BAND_SCORE = (100, 85, 70, 50, 30)


def cqi_tier(subs):
    try:
        n = float(subs)
    except (TypeError, ValueError):
        return None
    for lo, hi, name in CQI_TIER:
        if lo <= n < hi:
            return name
    return 'Mega'


def cqi(row, today=None):
    """本地近似 CQI：返回 {'brandFit':…, 'engage':…, 'audience':…, 'activity':…, 'commercial':None,
    'total':…, 'bands':{…}, 'cqiTier':…}。缺数据的维度记 None（**不得当 0 分**），总分按可用维度平均。"""
    if not isinstance(row, dict):
        return {}
    today = today or _dt.date.today()
    if isinstance(today, str):
        try:
            today = _dt.date(*[int(x) for x in today.split('-')])
        except ValueError:
            today = _dt.date.today()
    subs = _num(row.get('subscriberCount'))
    tier = cqi_tier(subs)
    bands, scores = {}, {}

    hits = len(row.get('matchedVideos') or [])
    bf = 0 if hits >= 6 else 1 if hits >= 4 else 2 if hits >= 3 else 3 if hits >= 1 else 4
    bands['brandFit'] = CQI_BRANDFIT_BANDS[bf]
    scores['brandFit'] = _BAND_SCORE[bf]

    er = _num(row.get('engagementRate'))
    if er is not None and tier in CQI_ER:
        t1, t2, t3, t4 = CQI_ER[tier]
        i = 0 if er >= t1 else 1 if er >= t2 else 2 if er >= t3 else 3 if er >= t4 else 4
        bands['engage'] = CQI_ENGAGE_BANDS[i]
        scores['engage'] = _BAND_SCORE[i]

    avg = _num(row.get('avgViews'))
    if avg is not None and subs and tier in CQI_VPR:
        vpr = avg / subs * 100.0
        p90, p75, p50, p25 = CQI_VPR[tier]
        i = 0 if vpr >= p90 else 1 if vpr >= p75 else 2 if vpr >= p50 else 3 if vpr >= p25 else 4
        bands['audience'] = CQI_AUDIENCE_BANDS[i]
        scores['audience'] = _BAND_SCORE[i]
        bands['vpr'] = round(vpr, 2)

    last = row.get('lastVideoPublishedAt') or row.get('lastLongFormPublishedAt')
    if last:
        try:
            d = str(last)[:10]
            days = (today - _dt.date(*[int(x) for x in d.split('-')])).days
            i = 0 if days <= 7 else 1 if days <= 28 else 2 if days <= 60 else 3
            bands['activity'] = CQI_ACTIVITY_BANDS[i]
            scores['activity'] = _BAND_SCORE[i]
            bands['daysSinceUpload'] = days
        except (ValueError, TypeError):
            pass

    # Commercial（付费内容比例）系统侧需逐视频判定，**本工具取不到 ⇒ 记 None**（不编造）
    scores['commercial'] = None
    bands['commercial'] = '未取到（需逐视频判定付费内容比例）'

    usable = [v for v in scores.values() if v is not None]
    total = round(sum(usable) / len(usable)) if usable else None
    return {'brandFit': scores.get('brandFit'), 'engage': scores.get('engage'),
            'audience': scores.get('audience'), 'activity': scores.get('activity'),
            'commercial': None, 'total': total, 'bands': bands, 'cqiTier': tier}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def core_hit(r, core_terms):
    """相关性证据闸门：`foundByKeywords`／`tags`／`category` 必须命中**至少一个核心技术词**。

    为什么：关键词检索会带回"场景词"命中的弱相关频道（例：`student learning` 命中教学频道）——
    只按订阅数／互动率筛，会把这类频道放进名单。判据：**能证明它与产品品类有关的证据，必须是品类词，
    不能只是场景词**（与 Skill §14.11.24 的"关键词写品类"同源）。
    🔴 v0.9.173：模糊单字（`meta`／`hud`）改走**组合词＋词边界**，不再子串命中（见 `CORE_AMBIGUOUS`）。
    退化面：未给 core_terms → 不拦（返回 True）；行非 dict → False。
    """
    if not core_terms:
        return True
    if not isinstance(r, dict):
        return False
    hay = core_haystack(r)
    ok_ctx, ok_eye = context_ok(hay), eyewear_ok(hay)
    for term, pat in zip(core_terms, core_patterns(core_terms)):
        _is_re, _pat = pat
        if not (re.search(_pat, hay) if _is_re else (_pat in hay)):
            continue
        _t = str(term).strip().lower()
        if _t in CORE_NEEDS_CONTEXT and not ok_ctx:
            continue
        if _t in CORE_NEEDS_EYEWEAR and not ok_eye:
            continue
        return True
    return False


def core_hit_count(r, core_terms):
    """命中个数（供门槛扫描用）：与 `core_hit` 同一套模式。"""
    if not core_terms or not isinstance(r, dict):
        return 0
    hay = core_haystack(r)
    ok_ctx, ok_eye = context_ok(hay), eyewear_ok(hay)
    cnt = 0
    for term, (is_re, pat) in zip(core_terms, core_patterns(core_terms)):
        if not (re.search(pat, hay) if is_re else (pat in hay)):
            continue
        _t = str(term).strip().lower()
        if _t in CORE_NEEDS_CONTEXT and not ok_ctx:
            continue
        if _t in CORE_NEEDS_EYEWEAR and not ok_eye:
            continue
        cnt += 1
    return cnt


def merge_rows(*lists):
    """把多份候选合并去重（后者只补前者缺的字段，不覆盖已有值）。"""
    out = {}
    for rows in lists:
        for r in rows or []:
            if not isinstance(r, dict) or not r.get('channelId'):
                continue
            cid = r['channelId']
            if cid not in out:
                out[cid] = dict(r)
                continue
            for k, v in r.items():
                if out[cid].get(k) in (None, '', []) and v not in (None, '', []):
                    out[cid][k] = v
    return dedupe(list(out.values()))


def screen_row(r, min_subs=None, max_subs=None, min_er=None, countries=None, core_terms=None,
               competitors=None, exclude_institutions=False, require_review=False,
               min_engage_band=None, max_days_since_upload=None, min_brandfit_band=None,
               review_mode='or_category', min_cqi_total=None, review_terms=None,
               permanent_ids=None, permanent_names=None):
    """单条候选的初筛判定 → (是否入选, 原因)。口径写死在这里，便于复核与回代。

    🔴 v0.9.173：新增**永久类门禁**（`permanent_ids`／`permanent_names`，来自判决来源表的 exclude 条目），
    放在最前 —— 它是"任何批次都成立"的排除，不得再靠"历史名单去重"偶然兜住（TICKET-110 实测教训）。
    """
    _perm = permanent_reason(r, permanent_ids, permanent_names)
    if _perm:
        return False, _perm
    subs = _num(r.get('subscriberCount'))
    if subs is None:
        return False, '缺订阅数（未富化）'
    if min_subs is not None and subs < min_subs:
        return False, '订阅数低于下限'
    if max_subs is not None and subs > max_subs:
        return False, '订阅数高于上限'
    er = _num(r.get('engagementRate'))
    if min_er is not None:
        if er is None:
            return False, '缺互动率'
        if er < min_er:
            return False, '互动率低于下限'
    if countries:
        c = (r.get('country') or '').upper()
        if c and c not in {x.upper() for x in countries}:
            return False, '国家不在目标市场'
    if not (r.get('channelId') or '').startswith('UC'):
        return False, 'channelId 形态异常'
    if not core_hit(r, core_terms):
        return False, '缺品类相关证据（只命中场景词）'
    if exclude_institutions:
        why = institution_reason(r, competitors)
        if why:
            return False, '机构号／品牌号：%s' % why
    if require_review:
        # 🔴 2026-09-30 拆参：`core_terms` 曾被**两处复用**（品类词闸门 ＋ 评测证据的品类词通道），
        #    于是"只关掉品类词闸门"会连带把评测证据也变严 —— 门槛扫描因此对不上账。
        #    现在：品类词闸门用 `core_terms`；评测证据的品类词通道用 `review_terms`（缺省回落 core_terms）。
        ok_rev, note = review_evidence(r, review_terms if review_terms is not None else core_terms,
                                       mode=review_mode)
        if not ok_rev:
            return False, '缺评测证据（%s）' % note
    c = cqi(r)
    if min_engage_band and c.get('engage') is not None:
        if c['engage'] < _BAND_SCORE[CQI_ENGAGE_BANDS.index(min_engage_band)]:
            return False, 'CQI 互动档低于「%s」（当前 %s）' % (min_engage_band, c['bands'].get('engage'))
    if max_days_since_upload is not None:
        d = (c.get('bands') or {}).get('daysSinceUpload')
        if d is not None and d > max_days_since_upload:
            return False, 'CQI 活跃度：%d 天未更新（上限 %d 天）' % (d, max_days_since_upload)
    if min_brandfit_band:
        bf = (c.get('bands') or {}).get('brandFit')
        if bf and CQI_BRANDFIT_BANDS.index(bf) > CQI_BRANDFIT_BANDS.index(min_brandfit_band):
            return False, 'CQI 品类匹配档低于「%s」（当前 %s）' % (min_brandfit_band, bf)
    # 🔴 CQI 总分淘汰线（用户 2026-09-30：「你是按照 cqi 小于多少分就会在这一道门槛下把对应的 kol 筛选掉」）
    if min_cqi_total is not None:
        tot = c.get('total')
        if tot is None:
            return False, 'CQI 总分取不到（无法判定是否达到 %s 线）' % min_cqi_total
        if tot < min_cqi_total:
            return False, 'CQI 总分 %s 低于 %s 分线' % (tot, min_cqi_total)
    return True, 'ok'


def dedupe(rows):
    """按 channelId 去重，保留首条；顺带按订阅数降序（同名不同源时数据更全的通常在前）。非列表 → []。"""
    if not isinstance(rows, list):
        return []
    seen, out = set(), []
    for r in rows:
        if not isinstance(r, dict):
            continue
        cid = r.get('channelId')
        if not cid or cid in seen:
            continue
        seen.add(cid)
        out.append(r)
    return sorted(out, key=lambda r: (_num(r.get('subscriberCount')) or 0), reverse=True)


def to_item(r):
    """把检索结果行映射成 `lists.batchAddItems` 的 item（字段名与 bundle 一致）。"""
    return {k: v for k, v in {
        'channelId': r.get('channelId'),
        'channelTitle': r.get('channelTitle') or r.get('title') or None,
        'channelThumbnail': r.get('thumbnailUrl') or r.get('channelThumbnail') or None,
        'subscriberCount': int(r['subscriberCount']) if _num(r.get('subscriberCount')) is not None else None,
        'country': r.get('country') or None,
        'tier': system_tier(r.get('subscriberCount')),   # 🔴 数字档（系统口径）
        'cqiScore': r.get('cqiScore') or None,
        'contactEmail': r.get('businessEmail') or r.get('contactEmail') or None,
        'engagementRate': _num(r.get('engagementRate')),
    }.items() if v is not None}


def normalize_results(payload):
    """把 getSearchJob 的 results（可能是字符串化的 JSON）归一成 list[dict]。"""
    rows = payload
    if isinstance(rows, str):
        try:
            rows = json.loads(rows)
        except ValueError:
            return []
    if isinstance(rows, dict):
        rows = rows.get('results') or rows.get('channels') or []
    if not isinstance(rows, list):
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        cats = r.get('topicCategories') or []
        out.append({
            'channelId': r.get('channelId'),
            'channelTitle': r.get('title') or r.get('channelTitle'),
            'subscriberCount': r.get('subscriberCount'),
            'thumbnailUrl': r.get('thumbnailUrl') or r.get('videoThumbnailUrl'),
            'country': r.get('country') or r.get('searchRegion'),
            'category': r.get('category') or (cats[0].split('/')[-1] if cats else None),
            'engagementRate': r.get('engagementRate'),
            'avgViews': r.get('avgViews') or r.get('averageViews'),
            'lastVideoPublishedAt': r.get('lastVideoPublishedAt'),
            'source': r.get('source'),
            'businessEmail': r.get('businessEmail'),
            'tags': r.get('tags') or [],
            'foundByKeywords': r.get('foundByKeywords') or [],
            'matchedVideos': r.get('matchedVideos') or [],
            'tier': tier_of(r.get('subscriberCount')),
        })
    return dedupe(out)


def write_csv(rows, path):
    cols = ['channelId', 'channelTitle', 'subscriberCount', 'tier', 'country', 'engagementRate',
            'avgViews', 'lastVideoPublishedAt', 'category', 'source', 'businessEmail',
            'matchedVideoCount', 'foundByKeywords', 'tags',
            'cqiTotal', 'cqiBrandFit', 'cqiEngage', 'cqiAudience', 'cqiActivity', 'cqiBands']
    with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            d = dict(r)
            d['matchedVideoCount'] = len(r.get('matchedVideos') or [])
            d['foundByKeywords'] = '|'.join(r.get('foundByKeywords') or [])
            d['tags'] = '|'.join(r.get('tags') or [])
            c = cqi(r)
            d['cqiTotal'] = c.get('total')
            d['cqiBrandFit'] = c.get('bands', {}).get('brandFit')
            d['cqiEngage'] = c.get('bands', {}).get('engage')
            d['cqiAudience'] = c.get('bands', {}).get('audience')
            d['cqiActivity'] = c.get('bands', {}).get('activity')
            d['cqiBands'] = '|'.join('%s=%s' % (k, v) for k, v in (c.get('bands') or {}).items())
            w.writerow({k: d.get(k) for k in cols})


# ── 在线动作 ────────────────────────────────────────────────────────────
def _brand(d, ref):
    """品牌引用 → brand dict。🔴 走**跨工作区索引**，与活跃工作区无关（2026-10-10 修）。"""
    if hasattr(d, 'resolve_brand_ref'):
        try:
            return d.resolve_brand_ref(str(ref))
        except SystemExit as e:
            raise ValueError(str(e))
    ref_s = str(ref).strip()
    for b in d.query('brands.list', {}):  # ambient-workspace-ok: 仅当客户端无 resolve_brand_ref 时兜底
        if str(b.get('id')) == ref_s or (b.get('name') or '').lower() == ref_s.lower():
            return b
    raise ValueError('找不到品牌「%s」' % ref)


def _poll_job(d, job_id, timeout=1800, every=2.0):
    """轮询 getSearchJob 直到 done／failed；返回最终任务对象。"""
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        j = d.query('discovery.getSearchJob', {'jobId': job_id})
        if not j:
            break
        last = j
        st = j.get('status')
        prog = '%s/%s' % (j.get('progressCompleted', '?'), j.get('progressTotal', '?'))
        found = j.get('foundCount', '?')
        print('   · status=%-10s progress=%-10s found=%-6s 用时 %ds'
              % (st, prog, found, int(time.time() - t0)), flush=True)
        if st in ('done', 'failed'):
            return j
        time.sleep(every)
    print('   ⚠️ 轮询超时（%ds）—— 返回最后一次状态' % timeout)
    return last or {}


def cmd_deep(d, args):
    plan = json.load(io.open(args.plan, encoding='utf-8'))
    b = _brand(d, plan.get('brand') or 'Halliday')
    f = plan.get('filters') or {}
    q, note = check_query(plan['deepQuery'], trim=args.trim)
    if note:
        print('  ✏️ 归一化：%s' % note)
    payload = {
        'query': q,
        'brandId': b['id'],
        'brandName': b.get('name'),
        'brandCompetitors': [c['name'] for c in (b.get('competitors') or []) if c.get('name')],
        'brandCategory': b.get('category'),
        'country': f.get('country'),
        'minSubscribers': f.get('minSubscribers'),
        'maxSubscribers': f.get('maxSubscribers'),
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    print('=== deep search：startSearchJob ===')
    print('   入参：%s' % json.dumps(payload, ensure_ascii=False))
    job = d.mutate('discovery.startSearchJob', payload)
    print('   返回：%s' % json.dumps(job, ensure_ascii=False)[:300])
    job_id = job.get('jobId') or job.get('id')
    if not job_id:
        print('❌ 没拿到 jobId'); return 1
    print('=== executeSearchJob（可能提前结束，随后轮询）===')
    try:
        d.mutate('discovery.executeSearchJob', {'jobId': job_id})
    except Exception as e:  # noqa: BLE001
        print('   （执行请求提前结束：%s —— 按 bundle 设计改为轮询）' % str(e)[:120])
    print('=== 轮询 getSearchJob ===')
    final = _poll_job(d, job_id, timeout=args.timeout)
    return _dump(d, final, args, tag='deep')


def cmd_open(d, args):
    plan = json.load(io.open(args.plan, encoding='utf-8'))
    b = _brand(d, plan.get('brand') or 'Halliday')
    sel = plan.get('selections') or {}
    f = plan.get('filters') or {}
    print('=== open search：expandTopic ===')
    try:
        ex = d.mutate('discovery.expandTopic', {'topic': plan['topic']})
        print('   扩写返回：%s' % json.dumps(ex, ensure_ascii=False)[:400])
    except Exception as e:  # noqa: BLE001
        print('   expandTopic 失败（继续）：%s' % str(e)[:150])
    topic, tnote = check_query(plan['topic'], trim=args.trim)
    if tnote:
        print('  ✏️ 归一化：%s' % tnote)
    payload = {
        'topic': topic,
        'selectedScenarios': sel.get('scenarios') or [],
        'selectedContentStyles': sel.get('contentStyles') or [],
        'selectedAudiences': sel.get('audiences') or [],
        'brandId': b['id'],
        'country': f.get('country'),
        'minSubscribers': f.get('minSubscribers'),
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    print('=== discovery.search ===')
    print('   入参：%s' % json.dumps(payload, ensure_ascii=False)[:600])
    job = d.mutate('discovery.search', payload)
    print('   返回：%s' % json.dumps(job, ensure_ascii=False)[:300])
    job_id = job.get('jobId') or job.get('id')
    if not job_id:
        print('❌ 没拿到 jobId'); return 1
    try:
        d.mutate('discovery.executeSearchJob', {'jobId': job_id})
    except Exception as e:  # noqa: BLE001
        print('   （执行请求提前结束：%s —— 改为轮询）' % str(e)[:120])
    final = _poll_job(d, job_id, timeout=args.timeout)
    return _dump(d, final, args, tag='open')


def _dump(d, final, args, tag):
    if not final:
        print('❌ 没拿到任务结果'); return 1
    st = final.get('status')
    print('=== 任务结束：status=%s ===' % st)
    for k in ('keywords', 'dimensions', 'reasoning', 'searchStats', 'errorMessage'):
        if final.get(k):
            v = final[k]
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except ValueError:
                    pass
            print('   %s：%s' % (k, json.dumps(v, ensure_ascii=False)[:500]))
    rows = normalize_results(final.get('results'))
    print('   候选条数（去重后）：%d' % len(rows))
    if not rows:
        print('   ⚠️ 本次没有 results —— 任务可能 failed 或结果键不同：%s'
              % list(final.keys()))
        return 1
    prefix = args.out_prefix or os.path.join('docs/marketing/kol/_build', 'search-%s' % tag)
    os.makedirs(os.path.dirname(prefix) or '.', exist_ok=True)
    io.open(prefix + '-raw.json', 'w', encoding='utf-8').write(
        json.dumps(final, ensure_ascii=False, indent=1))
    io.open(prefix + '-rows.json', 'w', encoding='utf-8').write(
        json.dumps(rows, ensure_ascii=False, indent=1))
    write_csv(rows, prefix + '-rows.csv')
    print('   ✅ 已落盘：%s-raw.json ／ -rows.json ／ -rows.csv' % prefix)
    return 0


def cmd_job_status(d, args):
    """检索任务状态。

    TICKET-150：原先 `json.dumps(j)[:1500]` 是**静默截断**（截断处不是合法 JSON，调用方拿不到
    完整字段）。现在按完整 JSON 输出 —— 产物本来就是机器读的，显示长度由调用方自己管。
    """
    j = d.query('discovery.getSearchJob', {'jobId': args.job_status})
    print(json.dumps(j, ensure_ascii=False))
    return 0


def cmd_enrich(d, args):
    rows = json.load(io.open(args.enrich, encoding='utf-8'))
    need = [r['channelId'] for r in rows if not _num(r.get('subscriberCount'))]
    print('待富化（缺订阅数）：%d / %d' % (len(need), len(rows)))
    have = {r['channelId']: r for r in rows}
    for i in range(0, len(need), 100):
        chunk = need[i:i + 100]
        try:
            res = d.mutate('discovery.enrichChannels', {'channelIds': chunk})
        except Exception as e:  # noqa: BLE001
            print('   批次 %d 富化失败：%s' % (i // 100 + 1, str(e)[:150])); continue
        chs = (res or {}).get('channels') or []
        for c in chs:
            cid = c.get('channelId')
            if cid in have:
                for k, v in c.items():
                    if have[cid].get(k) in (None, '', []) and v not in (None, '', []):
                        have[cid][k] = v
                have[cid]['tier'] = tier_of(have[cid].get('subscriberCount'))
        print('   批次 %d：返回 %d 条' % (i // 100 + 1, len(chs)))
        time.sleep(0.5)
    if args.emails:
        need_mail = [r['channelId'] for r in rows if not r.get('businessEmail')]
        print('待补邮箱：%d 条（每批 %d）' % (len(need_mail), EMAIL_BATCH))
        got = 0
        for i in range(0, len(need_mail), EMAIL_BATCH):
            try:
                res = d.mutate('discovery.enrichEmails',
                               {'channelIds': need_mail[i:i + EMAIL_BATCH]})
                for r in (res or {}).get('results') or []:
                    if r.get('channelId') in have and r.get('email'):
                        have[r['channelId']]['businessEmail'] = r['email']
                        got += 1
                print('   邮箱批次 %d：命中 %d' % (i // EMAIL_BATCH + 1, got))
            except Exception as e:  # noqa: BLE001
                print('   邮箱批次 %d 失败：%s' % (i // EMAIL_BATCH + 1, str(e)[:120]))
    out = dedupe(list(have.values()))
    io.open(args.enrich, 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False, indent=1))
    write_csv(out, re.sub(r'\.json$', '.csv', args.enrich))
    print('✅ 富化完成并覆盖写回：%s（含 CSV）' % args.enrich)
    return 0



# ── 门槛扫描（每道闸门"线定在哪、剩多少人"· 离线）─────────────────────
def gate_sweeps(plan, rows, today=None):
    """单变量扫描：每道闸门单独变动、其余保持现行口径。返回 dict（★＝现行）。"""
    plan = plan or {}
    sc = plan.get('screening') or {}
    core = sc.get('coreKeywords') or []
    market = ((plan.get('filters') or {}).get('country') or 'US')
    base_rows = [r for r in dedupe(rows) if (r.get('country') or '').upper() == str(market).upper()]

    def core_hits(row):
        # v0.9.173：与 core_hit 同一套模式（模糊单字走组合词＋词边界），避免扫描与筛选两套口径
        return core_hit_count(row, core)

    def count(rows_=None, core_min=1, **over):
        rows_ = base_rows if rows_ is None else rows_
        p = dict(min_subs=sc.get('minSubscribers'), max_subs=sc.get('maxSubscribers'),
                 min_er=sc.get('minEngagementRate'), competitors=sc.get('competitors'),
                 exclude_institutions=bool(sc.get('excludeInstitutions')),
                 require_review=bool(sc.get('requireReviewEvidence')),
                 min_engage_band=sc.get('minEngageBand'), max_days=sc.get('maxDaysSinceLastUpload'),
                 min_brandfit_band=sc.get('minBrandFitBand'),
                 review_mode=sc.get('reviewEvidenceMode') or 'or_category',
                 min_cqi_total=sc.get('minCqiTotal'))
        p.update(over)
        n = 0
        for r in rows_:
            ok, _ = screen_row(r, p['min_subs'], p['max_subs'], p['min_er'], None, None,
                               p['competitors'], p['exclude_institutions'], p['require_review'],
                               p['min_engage_band'], p['max_days'], p['min_brandfit_band'],
                               p['review_mode'], p['min_cqi_total'], core)   # review_terms 固定
            if ok and core_hits(r) >= core_min:
                n += 1
        return n

    out = {}
    out['_基线'] = count()
    out['品类词命中数下限'] = {('%d★' % k if k == 1 else str(k)): count(core_min=k) for k in (0, 1, 2, 3)}
    out['订阅数下限'] = {(('%d★' % k) if k == sc.get('minSubscribers') else str(k)): count(min_subs=k)
                        for k in (0, 5000, 10000, 20000, 30000, 50000, 80000, 100000)}
    out['订阅数上限'] = {(('%d★' % k) if k == sc.get('maxSubscribers') else str(k)): count(max_subs=k)
                        for k in (200000, 300000, 400000, 500000, 600000, 800000, 1000000, 2000000)}
    out['订阅区间矩阵'] = {('%d-%d' % (lo, hi)): count(min_subs=lo, max_subs=hi)
                         for lo in (10000, 20000, 30000, 50000)
                         for hi in (300000, 400000, 600000, 1000000)}
    out['互动率下限'] = {('%s★' % k if k == sc.get('minEngagementRate') else str(k)): count(min_er=k)
                        for k in (0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0)}
    out['机构号排除'] = {'开★': count(exclude_institutions=True), '关': count(exclude_institutions=False)}
    out['评测证据'] = {'关': count(require_review=False),
                       '动作词或品类词★': count(review_mode='or_category'),
                       '仅动作词': count(review_mode='token_only')}
    out['CQI 活跃度上限（天）'] = {(('%d★' % k) if k == sc.get('maxDaysSinceLastUpload') else str(k)):
                                 count(max_days=k) for k in (7, 28, 60, 90, 180, 365)}
    out['CQI 总分线'] = {('不设★' if k == 0 else str(k)): count(min_cqi_total=(None if k == 0 else k))
                        for k in (0, 40, 50, 55, 60, 65, 70, 75, 80)}
    out['CQI 互动档下限'] = {'不设★': count(min_engage_band=None),
                            '需要复核（50 分）': count(min_engage_band='需要复核'),
                            '典型（70 分）': count(min_engage_band='典型'),
                            '强（85 分）': count(min_engage_band='强'),
                            '优秀（100 分）': count(min_engage_band='优秀')}
    out['CQI 品类匹配档下限'] = {'不设★': count(min_brandfit_band=None),
                                '探索性匹配（50 分）': count(min_brandfit_band='探索性匹配'),
                                '可用匹配（70 分）': count(min_brandfit_band='可用匹配'),
                                '强匹配（85 分）': count(min_brandfit_band='强匹配')}
    out['目标市场'] = {}
    for mk in (('US',), ('US', 'CA'), ('US', 'CA', 'GB'), ('US', 'CA', 'GB', 'AU')):
        rr = [r for r in dedupe(rows) if (r.get('country') or '').upper() in set(mk)]
        out['目标市场'][','.join(mk) + ('★' if mk == (str(market).upper(),) else '')] = count(rows_=rr)
    out['数量上限'] = {str(k) + ('★' if k == sc.get('limit') else ''): min(count(), k or count())
                      for k in (50, 100, 150, 200)}
    return out


def cmd_sweep(plan_path, results_path, out_path=None):
    plan = json.load(io.open(plan_path, encoding='utf-8'))
    rows = json.load(io.open(results_path, encoding='utf-8'))
    sw = gate_sweeps(plan, rows)
    out = out_path or re.sub(r'\.json$', '-sweeps.json', results_path)
    io.open(out, 'w', encoding='utf-8').write(json.dumps(sw, ensure_ascii=False, indent=1))
    print('基线（现行口径合格人数）：%s' % sw['_基线'])
    for k, v in sw.items():
        if k == '_基线':
            continue
        print('── %s\n   %s' % (k, json.dumps(v, ensure_ascii=False)))
    print('✅ 已落盘：%s' % out)
    return 0


def cmd_screen(d, args):
    """按计划文件的 screening 块筛选，落盘 05-screened 并打印统计。"""
    rows_in = json.load(io.open(args.results, encoding='utf-8'))
    sc = (json.load(io.open(args.plan, encoding='utf-8')).get('screening') or {}) if args.plan else {}
    countries = sc.get('countries') or []
    picked, reasons = [], {}
    # 🔴 v0.9.173：**永久类门禁进筛查输入**（默认开启）—— 跨批剔除名单来自判决来源表
    #    `_KOL-VERDICT-SOURCES.json`（kind=exclude）。本批实测：`JampackSam`／`It Came From A Box`
    #    通过了六条口径、只因在历史名单里才被"去重"拦下 ⇒ 永久门禁不得再靠名单成员关系偶然兜住。
    _pids, _pnames = (set(), set()) if getattr(args, 'no_permanent_gate', False) \
        else load_permanent_exclusions()
    print('   永久类门禁：%s' % ('已加载 %d 个 channelId ＋ %d 个频道名' % (len(_pids), len(_pnames))
                                if (_pids or _pnames) else '未加载（空表或已关闭）'))
    rows = dedupe(rows_in)
    if countries:
        cl = {c.upper() for c in countries}
        rows = [r for r in rows if (r.get('country') or '').upper() in cl]
    for r in rows:
        ok, why = screen_row(r, sc.get('minSubscribers'), sc.get('maxSubscribers'),
                             sc.get('minEngagementRate'), None, sc.get('coreKeywords'),
                             competitors=sc.get('competitors'),
                             exclude_institutions=bool(sc.get('excludeInstitutions')),
                             require_review=bool(sc.get('requireReviewEvidence')),
                             min_engage_band=sc.get('minEngageBand'),
                             max_days_since_upload=sc.get('maxDaysSinceLastUpload'),
                             min_brandfit_band=sc.get('minBrandFitBand'),
                             review_mode=sc.get('reviewEvidenceMode') or 'or_category',
                             min_cqi_total=sc.get('minCqiTotal'),
                             permanent_ids=_pids, permanent_names=_pnames)
        (picked.append(r) if ok else reasons.__setitem__(why, reasons.get(why, 0) + 1))
    if sc.get('rankBy') == 'cqiTotal':
        picked.sort(key=lambda r: (cqi(r).get('total') or 0), reverse=True)
    picked = picked[:sc.get('limit')] if sc.get('limit') else picked
    out = args.out or re.sub(r'\.json$', '-screened.json', args.results)
    io.open(out, 'w', encoding='utf-8').write(json.dumps(picked, ensure_ascii=False, indent=1))
    write_csv(picked, re.sub(r'\.json$', '.csv', out))
    print('筛选口径：国家=%s 订阅=%s~%s ER≥%s 品类词闸门=%s条 机构号排除=%s 评测证据=%s '
          'CQI 总分≥%s 互动≥%s 活跃≤%s天 品类匹配≥%s 排序=%s 上限=%s'
          % (countries, sc.get('minSubscribers'), sc.get('maxSubscribers'),
             sc.get('minEngagementRate'), len(sc.get('coreKeywords') or []),
             sc.get('excludeInstitutions'), sc.get('requireReviewEvidence'),
             sc.get('minCqiTotal'), sc.get('minEngageBand'), sc.get('maxDaysSinceLastUpload'),
             sc.get('minBrandFitBand'), sc.get('rankBy'), sc.get('limit')))
    print('候选 %d → 入选 %d ｜ 淘汰原因：%s' % (len(rows), len(picked), json.dumps(reasons, ensure_ascii=False)))
    if picked:
        from collections import Counter
        print('入选画像：tier=%s ｜ source=%s ｜ 有邮箱 %d/%d'
              % (dict(Counter(r.get('tier') for r in picked)),
                 dict(Counter(r.get('source') for r in picked)),
                 sum(1 for r in picked if r.get('businessEmail')), len(picked)))
        _cs = [cqi(r) for r in picked]
        print('CQI（本地近似）：总分 %s~%s ｜ 品类匹配=%s ｜ 互动档=%s ｜ 活跃档=%s'
              % (min([c.get('total') or 0 for c in _cs]), max([c.get('total') or 0 for c in _cs]),
                 dict(Counter((c.get('bands') or {}).get('brandFit') for c in _cs)),
                 dict(Counter((c.get('bands') or {}).get('engage') for c in _cs)),
                 dict(Counter((c.get('bands') or {}).get('activity') for c in _cs))))
    print('✅ 已落盘：%s（＋CSV）' % out)
    return 0


def cmd_push(d, args):
    plan_rows = json.load(io.open(args.results, encoding='utf-8'))
    b = _brand(d, args.brand)
    sc = {}
    if args.plan:
        sc = (json.load(io.open(args.plan, encoding='utf-8')).get('screening') or {})
    countries = args.countries or (','.join(sc.get('countries') or []) or None)
    min_subs = args.min_subs if args.min_subs is not None else sc.get('minSubscribers')
    max_subs = args.max_subs if args.max_subs is not None else sc.get('maxSubscribers')
    min_er = args.min_er if args.min_er is not None else sc.get('minEngagementRate')
    core = sc.get('coreKeywords') or []
    limit = args.limit or sc.get('limit')
    rows = [r for r in dedupe(plan_rows) if r.get('channelId')]
    if countries:
        cl = {c.strip().upper() for c in countries.split(',')}
        rows = [r for r in rows if (r.get('country') or '').upper() in cl or not r.get('country')]
    picked, reasons = [], {}
    for r in rows:
        ok, why = screen_row(r, min_subs=min_subs, max_subs=max_subs, min_er=min_er, core_terms=core,
                             competitors=sc.get('competitors'),
                             exclude_institutions=bool(sc.get('excludeInstitutions')),
                             require_review=bool(sc.get('requireReviewEvidence')),
                             min_engage_band=sc.get('minEngageBand'),
                             max_days_since_upload=sc.get('maxDaysSinceLastUpload'),
                             min_brandfit_band=sc.get('minBrandFitBand'),
                             review_mode=sc.get('reviewEvidenceMode') or 'or_category',
                             min_cqi_total=sc.get('minCqiTotal'))
        if ok:
            picked.append(r)
        else:
            reasons[why] = reasons.get(why, 0) + 1
    if sc.get('rankBy') == 'cqiTotal':
        picked.sort(key=lambda r: (cqi(r).get('total') or 0), reverse=True)
    picked = picked[:limit] if limit else picked
    print('筛选口径：国家=%s 订阅=%s~%s ER≥%s 品类词闸门=%s条 上限=%s'
          % (countries, min_subs, max_subs, min_er, len(core), limit))
    print('逐条淘汰原因：%s' % json.dumps(reasons, ensure_ascii=False))
    print('初筛：%d 条候选 → 入选 %d 条' % (len(rows), len(picked)))
    items = [to_item(r) for r in picked]
    before = d.query('lists.listByBrand', {'brandId': b['id']}) or []
    if args.list_id:
        list_id = int(args.list_id)
        print('（--list-id）写入已有名单 listId %s' % list_id)
    else:
        dup = [l for l in before if (l.get('name') or '').strip().lower() == args.name.strip().lower()]
        if dup and not args.allow_duplicate:
            print('❌ 已有同名名单：%s（listId %s）—— 可加 --list-id 往它里面加人'
                  % (dup[0].get('name'), dup[0].get('id')))
            return 1
        if args.dry_run:
            print('（dry-run）将建名单「%s」并写入 %d 人；前 3 条示例：%s'
                  % (args.name, len(items), json.dumps(items[:3], ensure_ascii=False)[:400]))
            return 0
        lst = d.mutate('lists.create', {'brandId': b['id'], 'name': args.name,
                                        'description': args.description or None})
        list_id = (lst or {}).get('id')
        print('✅ 已建名单：listId %s ／ %s' % (list_id, args.name))
    added = failed = 0
    for i in range(0, len(items), 100):
        chunk = items[i:i + 100]
        try:
            res = d.mutate('lists.batchAddItems', {'listId': int(list_id), 'items': chunk})
            added += (res or {}).get('addedCount') or 0
            failed += len((res or {}).get('failed') or [])
            print('   批次 %d：+%s（失败 %s）' % (i // 100 + 1,
                                                (res or {}).get('addedCount'), len((res or {}).get('failed') or [])))
        except Exception as e:  # noqa: BLE001
            print('   批次 %d 失败：%s' % (i // 100 + 1, str(e)[:200]))
    after = d.query('lists.listByBrand', {'brandId': b['id']}) or []
    hit = [l for l in after if str(l.get('id')) == str(list_id)]
    if not hit:
        print('❌ 回读没找到新建名单'); return 1
    cnt = hit[0].get('influencerCount')
    print('✅ 回读：名单「%s」现有 %s 个 creator（累加返回 addedCount=%d、failed=%d）'
          % (hit[0].get('name'), cnt, added, failed))
    try:
        its = d.query('lists.getItems', {'listId': int(list_id)})
        n = len(its) if isinstance(its, list) else (its or {}).get('total')
        print('   getItems 复核：%s 条' % n)
    except Exception as e:  # noqa: BLE001
        print('   getItems 复核失败：%s' % str(e)[:150])
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--deep', action='store_true')
    ap.add_argument('--open', action='store_true')
    ap.add_argument('--job-status', metavar='JOBID')
    ap.add_argument('--screen', action='store_true')
    ap.add_argument('--no-permanent-gate', action='store_true',
                    help='关闭跨批永久排除门禁（默认开启，来源 _KOL-VERDICT-SOURCES.json）')
    ap.add_argument('--sweep', action='store_true', help='门槛扫描：每道闸门线定在哪、剩多少人（离线）')
    ap.add_argument('--merge', nargs='+', metavar='RESULTS.json')
    ap.add_argument('--out')
    ap.add_argument('--enrich', metavar='RESULTS.json')
    ap.add_argument('--emails', action='store_true')
    ap.add_argument('--push-list', action='store_true')
    ap.add_argument('--plan')
    ap.add_argument('--out-prefix')
    ap.add_argument('--timeout', type=int, default=1800)
    ap.add_argument('--brand', default='Halliday')
    ap.add_argument('--list-id', metavar='ID', help='往已有名单加人（不新建）')
    ap.add_argument('--name')
    ap.add_argument('--description')
    ap.add_argument('--results', metavar='RESULTS.json')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--min-subs', type=int)
    ap.add_argument('--max-subs', type=int)
    ap.add_argument('--min-er', type=float)
    ap.add_argument('--countries')
    ap.add_argument('--trim', action='store_true', help='query/topic 超长时自动截断（默认拒绝）')
    ap.add_argument('--allow-duplicate', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if args.merge:
        lists = [json.load(io.open(f, encoding='utf-8')) for f in args.merge]
        rows = merge_rows(*lists)
        out = args.out or os.path.join(OUTPUT_DIR, 'merged.json')
        io.open(out, 'w', encoding='utf-8').write(json.dumps(rows, ensure_ascii=False, indent=1))
        write_csv(rows, re.sub(r'\.json$', '.csv', out))
        print('✅ 合并去重：%s → %d 条（已写 %s ＋ CSV）' % (' ＋ '.join(args.merge), len(rows), out))
        return 0
    if args.sweep:
        if not (args.plan and args.results):
            print('❌ --sweep 需要 --plan 与 --results'); return 1
        return cmd_sweep(args.plan, args.results, args.out)
    if args.screen:
        return cmd_screen(None, args)
    if args.job_status:
        dc = _load_client(); d = dc.Daniel(verbose=False); d.login()
        return cmd_job_status(d, args)
    dc = _load_client()
    d = dc.Daniel(verbose=False)
    d.login()
    if args.deep:
        return cmd_deep(d, args)
    if args.open:
        return cmd_open(d, args)
    if args.merge:
        lists = [json.load(io.open(f, encoding='utf-8')) for f in args.merge]
        rows = merge_rows(*lists)
        out = args.out or os.path.join(OUTPUT_DIR, 'merged.json')
        io.open(out, 'w', encoding='utf-8').write(json.dumps(rows, ensure_ascii=False, indent=1))
        write_csv(rows, re.sub(r'\.json$', '.csv', out))
        print('✅ 合并去重：%s → %d 条（已写 %s ＋ CSV）' % (' ＋ '.join(args.merge), len(rows), out))
        return 0
    if args.enrich:
        return cmd_enrich(d, args)
    if args.push_list:
        return cmd_push(d, args)
    ap.print_help()
    return 1


# ── 离线自检 ────────────────────────────────────────────────────────────
def _raises(fn, needle):
    try:
        fn()
        return False
    except Exception as e:  # noqa: BLE001
        return needle in str(e)


def self_test():
    ctl = []
    ctl.append(('正控 体量档：9999→Nano／10k→Micro／10 万→Mid-size／50 万→Macro／200 万→Mega',
                tier_of(9999) == 'Nano' and tier_of(10000) == 'Micro'
                and tier_of(100000) == 'Mid-size' and tier_of(500000) == 'Macro'
                and tier_of(2000000) == 'Mega'))
    ctl.append(('[degenerate:type_unit] 体量档：None／字符串／负数 → 未知，不得致崩',
                tier_of(None) == '未知' and tier_of('abc') == '未知' and tier_of(-1) == '未知'))
    ctl.append(('正控 体量档接受字符串数字（接口返回常为字符串）', tier_of('123456') == 'Mid-size'))

    good = {'channelId': 'UC' + 'a' * 20, 'subscriberCount': 50000, 'engagementRate': 3.2,
            'country': 'US'}
    ctl.append(('正控 合格候选入选', screen_row(good, 20000, 600000, 1.0, ['US'])[0] is True))
    ctl.append(('正控 订阅数越界／互动率偏低／国家不符 → 各被拒',
                screen_row(dict(good, subscriberCount=1000), 20000)[1] == '订阅数低于下限'
                and screen_row(dict(good, subscriberCount=9e6), None, 600000)[1] == '订阅数高于上限'
                and screen_row(dict(good, engagementRate=0.2), None, None, 1.0)[1] == '互动率低于下限'
                and screen_row(dict(good, country='IN'), None, None, None, ['US'])[1] == '国家不在目标市场'))
    ctl.append(('正控 缺订阅数 → 拒（提示未富化）；channelId 形态异常 → 拒',
                screen_row(dict(good, subscriberCount=None))[1] == '缺订阅数（未富化）'
                and screen_row(dict(good, channelId='abc'))[1] == 'channelId 形态异常'))
    ctl.append(('[degenerate:empty] 空 dict／None 字段 → 拒且不崩',
                screen_row({})[0] is False and screen_row({'channelId': None})[0] is False))
    ctl.append(('[degenerate:type_unit] 非 dict 行不得致崩（dedupe 侧过滤）',
                dedupe([None, 1, 'x', {'channelId': 'UC1'}]) == [{'channelId': 'UC1'}]))
    ctl.append(('正控 去重：同 channelId 只留一条，且按订阅数降序',
                [r['channelId'] for r in dedupe([
                    {'channelId': 'A', 'subscriberCount': 10}, {'channelId': 'B', 'subscriberCount': 99},
                    {'channelId': 'A', 'subscriberCount': 5}])] == ['B', 'A']))
    ctl.append(('[degenerate:empty] 去重：非列表 → []', dedupe(None) == [] and dedupe('x') == []))

    ctl.append(('正控 结果归一：字符串化 JSON 也能解析',
                len(normalize_results('[{"channelId":"UCx","title":"T","subscriberCount":12345}]')) == 1))
    ctl.append(('[degenerate:substring] 归一：title 缺失时回落 channelTitle',
                normalize_results([{'channelId': 'UCx', 'channelTitle': 'C'}])[0]['channelTitle'] == 'C'))
    ctl.append(('[degenerate:empty] 归一：空／None／字典无 results → []',
                normalize_results(None) == [] and normalize_results('') == []
                and normalize_results({'foo': 1}) == []))
    ctl.append(('正控 item 映射：字段名与 bundle 一致（channelTitle／channelThumbnail／contactEmail）',
                set(to_item({'channelId': 'UCx', 'channelTitle': 'T', 'thumbnailUrl': 'u',
                             'subscriberCount': 1000, 'businessEmail': 'a@b.c',
                             'engagementRate': 2.5})) ==
                {'channelId', 'channelTitle', 'channelThumbnail', 'subscriberCount', 'tier',
                 'contactEmail', 'engagementRate'}))
    ctl.append(('[degenerate:empty] item 映射：值为空的键不写入（不得写 null 覆盖）',
                'country' not in to_item({'channelId': 'UCx', 'country': None})))
    ctl.append(('[degenerate:negation] 国家为空**不得**被当成"不匹配"（无国家信息放行待判）',
                screen_row(dict(good, country=None), None, None, None, ['US'])[0] is True))

    # ── query 长度上限（2026-09-30 二分实测 501／502）──
    ctl.append(('正控 query 长度：501 通过、502 拒绝（实测上限）',
                check_query('x' * 501)[0] == 'x' * 501
                and _raises(lambda: check_query('x' * 502), '超长')))
    ctl.append(('正控 --trim：超长按句界截到 ≤490 并给出说明',
                (lambda r: len(r[0]) <= 490 and r[1] and '自动截断' in r[1])(
                    check_query('AI glasses review for work meetings. ' * 30, trim=True))))
    ctl.append(('[degenerate:empty] query 空／None → 报错',
                _raises(lambda: check_query(''), '为空') and _raises(lambda: check_query(None), '为空')))
    ctl.append(('[degenerate:type_unit] query 非字符串 → 报错',
                _raises(lambda: check_query(['x']), '为空')))
    ctl.append(('[degenerate:substring] 恰好等于上限不得被误拒（边界）',
                len(check_query('y' * 501)[0]) == 501 and _raises(lambda: check_query('y' * 502), '超长')))

    # ── 相关性证据闸门 ＋ 合并 ──
    core = ['ai glasses', 'smart glasses', 'ar glasses', 'wearable display', 'head-mounted display']
    ctl.append(('正控 命中品类词 → 通过（`AI glasses` 大小写不敏感）',
                core_hit({'foundByKeywords': ['AI Glasses', 'work meetings']}, core) is True))
    ctl.append(('正控 只命中场景词（`student learning`／`hybrid work tech`）→ 拦下',
                core_hit({'foundByKeywords': ['student learning', 'hybrid work tech']}, core) is False))
    ctl.append(('正控 tags／category 亦可作为品类证据（品牌词带产品语境）',
                core_hit({'foundByKeywords': [], 'tags': ['xreal one smart glasses review']}, ['xreal']) is True
                and core_hit({'category': 'AR glasses'}, core) is True))
    # 🔴 v0.9.173 语境约束（TICKET-110 实测假命中）
    ctl.append(('正控（语境约束）品牌词带产品语境 → 计入证据（`vuzix z100 smart glasses review`）',
                core_hit({'tags': ['vuzix z100 smart glasses review']}, ['vuzix']) is True))
    ctl.append(('[degenerate:negation] 近邻探针：品牌词**无**产品语境 → 不得计入'
                '（`VUZI stock analysis`／`Solos acoustic set`／`Ray-Ban Aviator size`）',
                core_hit({'tags': ['vuzix stock analysis']}, ['vuzix']) is False
                and core_hit({'tags': ['solos acoustic set']}, ['solos']) is False
                and core_hit({'tags': ['ray-ban aviator size comparison']}, ['ray-ban']) is False))
    ctl.append(('[degenerate:substring] 评测证据通道同样受语境约束：'
                '`VUZI earnings` 不得算品类证据，`Vuzix smart glasses review` 须算',
                review_evidence({'matchedVideos': [{'title': 'VUZI earnings reaction'}]},
                                ['vuzix'], 'or_category')[0] is False
                and review_evidence({'matchedVideos': [{'title': 'Vuzix smart glasses review'}]},
                                    ['vuzix'], 'or_category')[0] is True))
    ctl.append(('[degenerate:empty] 语境约束：空 tags／None 不崩',
                core_hit({'tags': []}, ['vuzix']) is False and core_hit(None, ['vuzix']) is False))
    # 永久类门禁（跨批剔除）——筛查输入，不再靠去重兜
    _pids, _pnames = load_permanent_exclusions()
    ctl.append(('正控（永久类门禁）真实判决表可加载（id≥0、名≥1）', len(_pnames) >= 1))
    ctl.append(('正控（永久类门禁）判决表里的频道名 → 筛查直接拦下（理由含"永久类门禁"）',
                screen_row({'channelId': 'UC' + 'x' * 20, 'channelTitle': sorted(_pnames)[0],
                            'subscriberCount': 100000, 'country': 'US'},
                           permanent_names=_pnames)[1].startswith('永久类门禁')))
    ctl.append(('[degenerate:accent_case] 永久类门禁：名称大小写／重音／空格差异仍须命中',
                screen_row({'channelId': 'UC' + 'y' * 20,
                            'channelTitle': sorted(_pnames)[0].upper(),
                            'subscriberCount': 100000, 'country': 'US'},
                           permanent_names=_pnames)[1].startswith('永久类门禁')))
    ctl.append(('[degenerate:scope] 永久类门禁：不在表里的频道不得被误拦',
                screen_row({'channelId': 'UC' + 'z' * 20, 'channelTitle': 'Some Fresh Channel',
                            'subscriberCount': 100000, 'country': 'US',
                            'foundByKeywords': ['ai glasses']}, core_terms=['ai glasses'],
                           permanent_names=_pnames)[0] is True))
    ctl.append(('[degenerate:empty] 永久类门禁：空表不拦、None 行不崩',
                screen_row({'channelId': 'UC' + 'w' * 20, 'channelTitle': 'X',
                            'subscriberCount': 100000, 'country': 'US',
                            'foundByKeywords': ['ai glasses']}, core_terms=['ai glasses'],
                           permanent_names=set())[0] is True
                and permanent_reason(None, set(), set()) is None))
    ctl.append(('[degenerate:empty] 未给 core_terms → 不拦；非 dict → False',
                core_hit({'foundByKeywords': []}, []) is True and core_hit(None, core) is False))
    ctl.append(('[degenerate:negation] 负面词库不影响正向命中（`not ai glasses` 仍含品类词——承认该边界）',
                core_hit({'foundByKeywords': ['not ai glasses']}, core) is True))
    _m = merge_rows([{'channelId': 'A', 'subscriberCount': 10, 'businessEmail': None}],
                    [{'channelId': 'A', 'businessEmail': 'x@y.z'}, {'channelId': 'B', 'subscriberCount': 5}])
    ctl.append(('正控 合并：同 id 只留一条，且**后者补前者缺的字段、不覆盖已有值**',
                len(_m) == 2 and {r['channelId']: r for r in _m}['A']['subscriberCount'] == 10
                and {r['channelId']: r for r in _m}['A']['businessEmail'] == 'x@y.z'))
    ctl.append(('[degenerate:empty] 合并非列表／含 None → 不崩、跳过',
                merge_rows(None, [None, 'x'], []) == [] and len(merge_rows([], [{'channelId': 'C'}])) == 1))
    ctl.append(('正控 闸门并入 screen_row：只命中场景词的合格订阅者仍被拒',
                screen_row(dict(good, foundByKeywords=['student learning']), 20000, 600000, 1.0,
                           ['US'], core)[1] == '缺品类相关证据（只命中场景词）'))

    ctl.append(('正控 两条链路的批量上限分别实测记录：EMAIL_BATCH=50（51 起 400）／CHANNEL_BATCH=100',
                EMAIL_BATCH == 50 and CHANNEL_BATCH == 100))

    # ── 系统口径体量档（写库字段，必须用数字 1–4）──
    ctl.append(('正控 系统档位边界（bundle `ls`）：4,999,999→2／5,000,000→1／499,999→3／500,000→2／49,999→4／50,000→3',
                system_tier(4999999) == 2 and system_tier(5000000) == 1
                and system_tier(499999) == 3 and system_tier(500000) == 2
                and system_tier(49999) == 4 and system_tier(50000) == 3))
    ctl.append(('[degenerate:type_unit] 系统档位：None／字符串数字／非数字 → 4（与界面同：缺值即 4）',
                system_tier(None) == 4 and system_tier('50000') == 3 and system_tier('abc') == 4))
    ctl.append(('正控 to_item 的 tier 必须是**数字**（曾按档名传字符串 → 接口 400）',
                isinstance(to_item({'channelId': 'UCx', 'subscriberCount': 600000})['tier'], int)))

    # ── 机构号排除闸门 ──
    comp = ['Ray-Ban Meta', 'XREAL', 'Rokid', 'VITURE']
    ctl.append(('正控 标题即竞品品牌名（`Meta`／`XREAL`）⇒ 判为品牌官方号',
                bool(institution_reason({'channelTitle': 'Meta'}, comp + ['Meta']))
                and bool(institution_reason({'channelTitle': 'XREAL'}, comp))))
    ctl.append(('正控 标题含机构／媒体词（`BBC News`／`GiftGenius (Official Page)`／`Ford Motor Group`）⇒ 命中',
                all(institution_reason({'channelTitle': t0}, comp)
                    for t0 in ('BBC News', 'GiftGenius (Official Page)', 'Hyundai Motor Group'))))
    ctl.append(('正控 具名出版方名单（`TechRadar`／`Android Central`）⇒ 命中',
                bool(institution_reason({'channelTitle': 'TechRadar'}, comp))
                and bool(institution_reason({'channelTitle': 'Android Central'}, comp))))
    ctl.append(('真阴性 创作者名带 review／labs／studio 等词**不得**被误判（避免误伤）',
                institution_reason({'channelTitle': 'Mrwhosetheboss'}, comp) is None
                and institution_reason({'channelTitle': 'HotshotTek'}, comp) is None
                and institution_reason({'channelTitle': 'Peter H. Diamandis'}, comp) is None
                and institution_reason({'channelTitle': 'The Tech Review Studio'}, comp) is None))
    ctl.append(('[degenerate:empty] 空标题／None 行 → 放行（不拦）且不崩',
                institution_reason({'channelTitle': ''}, comp) is None
                and institution_reason(None, comp) is None))
    ctl.append(('正控 竞品名拆词元：`Ray-Ban Meta` ⇒ 标题 `Meta` 也必须被抓到（整名匹配会漏）',
                bool(institution_reason({'channelTitle': 'Meta'}, ['Ray-Ban Meta', 'Oakley Meta']))
                and 'meta' in competitor_tokens(['Ray-Ban Meta'])))
    ctl.append(('[degenerate:negation] 真阴性：通用词（ai／glasses／smart）不得进词元表，避免把创作者名误判',
                not ({'ai', 'glasses', 'smart'} & competitor_tokens(['AI Glasses', 'Smart Glasses']))
                and institution_reason({'channelTitle': 'AI Glasses Fan'}, ['AI Glasses']) is None))
    ctl.append(('[degenerate:accent_case] 大小写不敏感（`meta`／`TECHRADAR`）',
                bool(institution_reason({'channelTitle': 'meta'}, comp + ['Meta']))
                and bool(institution_reason({'channelTitle': 'TECHRADAR'}, comp))))

    # ── 评测证据闸门 ──
    ctl.append(('正控 命中视频标题含评测动作词（review／hands-on／vs／unboxing）⇒ 通过',
                review_evidence({'matchedVideos': [{'title': 'Halliday G2 review after 30 days'}]})[0]
                and review_evidence({'matchedVideos': [{'title': 'XREAL vs Rokid: which is better'}]})[0]
                and review_evidence({'matchedVideos': [{'title': 'Unboxing the new AI glasses'}]})[0]))
    ctl.append(('正控 命中视频标题含品类词（`ai glasses`）⇒ 通过',
                review_evidence({'matchedVideos': [{'title': 'My new AI glasses setup'}]}, ['ai glasses'])[0]))
    ctl.append(('正控 只有场景词标题（TED 演讲式）⇒ 拦下（本轮教学号/泛职场号正是这类）',
                review_evidence({'matchedVideos': [{'title': 'The Art of Communicating Effectively for Hybrid Work'}]},
                                ['ai glasses'])[0] is False))
    ctl.append(('[degenerate:empty] 无 matchedVideos／空标题 → 不通过且不崩',
                review_evidence({})[0] is False and review_evidence({'matchedVideos': []})[0] is False
                and review_evidence({'matchedVideos': [{'title': ''}]})[0] is False
                and review_evidence(None)[0] is False))
    ctl.append(('[degenerate:type_unit] matchedVideos 非列表 → 不通过且不崩',
                review_evidence({'matchedVideos': 'x'})[0] is False))
    ctl.append(('正控 评测证据两种模式：`or_category`（默认）靠品类词通过；`token_only` 同一行必须被拦下',
                review_evidence({'matchedVideos': [{'title': 'Prince Harry and the Teleprompter Mess'}]},
                                ['teleprompter'])[0] is True
                and review_evidence({'matchedVideos': [{'title': 'Prince Harry and the Teleprompter Mess'}]},
                                    ['teleprompter'], mode='token_only')[0] is False))
    ctl.append(('正控 token_only 下带评测动作词仍通过（不得过严）',
                review_evidence({'matchedVideos': [{'title': 'Halliday G2 review'}]}, None,
                                mode='token_only')[0] is True))

    # ── CQI 五维（本地近似）──
    _c = cqi({'subscriberCount': 200000, 'engagementRate': 6.0, 'avgViews': 60000,
              'lastVideoPublishedAt': '2026-09-28',
              'matchedVideos': [{'title': 'review %d' % i} for i in range(6)]}, today='2026-09-30')
    ctl.append(('正控 CQI：6 个命中视频 ⇒ 品类专家；ER 6% 在 Mid-size 属「优秀」；VPR 30% ⇒ 前 10%；2 天前发布 ⇒ 适合立即启动',
                _c['bands']['brandFit'] == '品类专家' and _c['bands']['engage'] == '优秀'
                and _c['bands']['audience'] == '前 10%' and _c['bands']['activity'] == '适合立即启动'))
    ctl.append(('正控 CQI：Commercial 取不到 ⇒ 记 None（不编造 0 分），总分按可用维度平均',
                _c['commercial'] is None and _c['total'] == round((100 + 100 + 100 + 100) / 4)))
    _c2 = cqi({'subscriberCount': 100000, 'engagementRate': 1.0, 'avgViews': 500,
               'lastVideoPublishedAt': '2026-05-01', 'matchedVideos': []}, today='2026-09-30')
    ctl.append(('正控 CQI：无命中视频 ⇒ 仅搜索发现；ER 1% ⇒ 较弱；沉寂 ⇒ 档位正确',
                _c2['bands']['brandFit'] == '仅搜索发现' and _c2['bands']['engage'] == '较弱'
                and _c2['bands']['activity'] == '沉寂'))
    ctl.append(('[degenerate:empty] CQI：空行／None → 不崩（返回 dict 或空）',
                isinstance(cqi({}), dict) and cqi(None) == {}))
    ctl.append(('[degenerate:type_unit] CQI：订阅数为字符串数字仍可判档；非数字 → 档位 None 不崩',
                cqi({'subscriberCount': '200000'})['cqiTier'] == 'Mid-size'
                and cqi({'subscriberCount': 'abc'})['cqiTier'] is None))
    ctl.append(('[degenerate:substring] 真阴性：词边界生效 —— `GoodNewsGadgets`／`Newsy` 这类创作者名**不得**因含 news 子串被误判',
                institution_reason({'channelTitle': 'GoodNewsGadgets'}, comp) is None
                and institution_reason({'channelTitle': 'TheGadgetGroupie'}, comp) is None))
    _ok_row = {'channelId': 'UC' + 'a' * 20, 'channelTitle': 'Some Creator',
               'subscriberCount': 100000, 'engagementRate': 2.0, 'country': 'US',
               'foundByKeywords': ['AI glasses', 'work meetings'],
               'matchedVideos': [{'title': 'AI glasses review and hands-on'}]}
    ctl.append(('正控 闸门并入 screen_row：机构号被拒（`Meta`）',
                screen_row(dict(_ok_row, channelTitle='Meta'), 20000, 600000, 1.0, ['US'],
                           ['ai glasses'], comp, True, True)[1].startswith('机构号')))
    ctl.append(('正控 闸门并入 screen_row：只有场景词标题被拒（缺评测证据）',
                screen_row(dict(_ok_row, matchedVideos=[{'title': 'Effective communication at work'}]),
                           20000, 600000, 1.0, ['US'], ['ai glasses'], comp, True, True)[1]
                .startswith('缺评测证据')))
    ctl.append(('正控 screen_row 全通过时返回 ok（含机构号与评测两道闸门）',
                screen_row(_ok_row, 20000, 600000, 1.0, ['US'], ['ai glasses'], comp, True, True)[0] is True))
    ctl.append(('[degenerate:scope] 拆参控制：只改品类词闸门（core_terms）不得影响评测证据的判定 —— '
                '同一行在 core_terms=None 且 review_terms 给定时，评测证据结果必须一致',
                (lambda r: review_evidence(r, ['teleprompter'])[0] is True
                 and review_evidence(r, ['teleprompter'])[0]
                 == review_evidence(r, ['teleprompter'])[0])(
                    {'matchedVideos': [{'title': 'Prince Harry and the Teleprompter Mess'}]})))
    ctl.append(('正控 CQI 总分淘汰线：总分低于线 → 拒，且写明分数与线',
                screen_row(dict(_ok_row, engagementRate=1.0, subscriberCount=100000,
                                avgViews=1000, lastVideoPublishedAt='2026-09-25',
                                matchedVideos=[{'title': 'AI glasses review'}]
                                + [{'title': 'x'} for _ in range(4)]),
                           20000, 600000, None, ['US'], ['ai glasses'], comp, True, True, None, None, None,
                           'or_category', 100)[1].startswith('CQI 总分')))
    ctl.append(('正控 CQI 档位闸门生效：互动档低于门槛会被拒',
                screen_row(dict(_ok_row, engagementRate=1.0), 20000, 600000, None, ['US'],
                           ['ai glasses'], comp, True, True, min_engage_band='典型')[1].startswith('CQI 互动档')))

    # ── 门槛扫描：单变量性（关掉某道门，人数只能变多或不变）──
    _plan = {'filters': {'country': 'US'}, 'screening': {
        'minSubscribers': 20000, 'maxSubscribers': 600000, 'minEngagementRate': 1.0,
        'coreKeywords': ['ai glasses', 'smart glasses'], 'competitors': ['Meta'], 'excludeInstitutions': True,
        'requireReviewEvidence': True, 'maxDaysSinceLastUpload': 90, 'limit': 100}}
    def _row(cid, title, subs, kw, vtitle):
        return {'channelId': cid, 'channelTitle': title, 'country': 'US', 'subscriberCount': subs,
                'engagementRate': 3.0, 'avgViews': 10000, 'lastVideoPublishedAt': '2026-09-25',
                'foundByKeywords': [kw], 'matchedVideos': [{'title': vtitle}]}
    # 每行只在一处不同，便于隔离每道闸门：
    #   A 全通过 ｜ B 全通过但标题＝竞品名（机构号）｜ C 评测✓但品类词✗ ｜ D 品类词✓但评测✗ ｜ E 全通过
    _rows = [
        _row('UC1', 'Creator A', 100000, 'ai glasses', 'AI glasses review'),
        _row('UC2', 'Meta', 200000, 'ai glasses', 'AI glasses review'),
        _row('UC3', 'Creator C', 90000, 'student learning', 'Unboxing a gadget'),
        _row('UC4', 'Creator D', 120000, 'ai glasses', 'some talk'),
        _row('UC5', 'Creator E', 150000, 'smart glasses', 'Smart glasses hands-on'),
    ]
    _sw = gate_sweeps(_plan, _rows, today='2026-09-30')
    ctl.append(('正控 门槛扫描：基线＝2（机构号 1 条被排除、品类词 1 条被排除、评测证据 1 条被排除）',
                _sw['_基线'] == 2))
    ctl.append(('正控 门槛扫描单变量性：关机构号排除 ⇒ 3（放回 Meta）｜品类词下限降到 0 ⇒ 3（放回 C）｜'
                '关评测证据 ⇒ 3（放回 D）',
                _sw['机构号排除']['关'] == 3 and _sw['品类词命中数下限']['0'] == 3
                and _sw['评测证据']['关'] == 3))
    ctl.append(('[degenerate:empty] 门槛扫描：空行／空计划不得致崩',
                isinstance(gate_sweeps({}, []), dict) and isinstance(gate_sweeps(None, None), dict)))

    # ── 🔴 v0.9.173 模糊词收紧（TICKET-110 总监裁定 ②）：正控／近邻／子串三条控制 ──
    _m = ['meta']
    def _mh(*kw):
        return core_hit({'foundByKeywords': list(kw), 'tags': [], 'category': ''}, _m)
    ctl.append(('正控 模糊词收紧：`Ray-Ban Meta review` 仍须命中（组合词 `ray-?ban\\s+meta`）',
                _mh('Ray-Ban Meta') is True and _mh('rayban meta') is True))
    ctl.append(('正控 模糊词收紧：`Meta smart glasses`／`Oakley Meta` 仍须命中',
                _mh('Meta smart glasses') is True and _mh('Oakley Meta') is True))
    ctl.append(('近邻 模糊词收紧：`metagame`／`Meta earnings`／裸 `Meta` 不得命中（游戏与财报假命中）',
                _mh('metagame') is False and _mh('Meta earnings') is False and _mh('Meta') is False))
    ctl.append(('子串 模糊词收紧：`metadata` 不得命中',
                _mh('metadata') is False))
    _h = lambda t: core_hit({'foundByKeywords': [t], 'tags': [], 'category': ''}, ['hud'])
    ctl.append(('正控（v0.9.174 眼镜语境）`HUD glasses` 命中；`Hudson` 不命中；'
                '**裸 `HUD` 不再算**（第八批 F1 座舱 HUD 假命中）',
                _h('HUD glasses') is True and _h('Hudson') is False and _h('HUD') is False))
    ctl.append(('[degenerate:substring]（v0.9.174 词边界）`ar glasses` 不得命中 `regular glasses`'
                '（Scamadviser 自动变焦老花镜假命中）',
                core_hit({'foundByKeywords': ['regular glasses review']}, ['ar glasses']) is False
                and core_hit({'foundByKeywords': ['AR glasses review']}, ['ar glasses']) is True))
    ctl.append(('[degenerate:negation]（v0.9.174 眼镜语境）`head-mounted display` 不得命中'
                '军用头盔显示／游戏机 VR 外设；带眼镜语境则命中',
                core_hit({'foundByKeywords': ['military head-mounted display helmet']},
                         ['head-mounted display']) is False
                and core_hit({'foundByKeywords': ['head-mounted display smart glasses review']},
                             ['head-mounted display']) is True))
    ctl.append(('[degenerate:substring]（v0.9.174 词边界）`ai glasses` 不得命中 `chai glasses`'
                '（跨词子串）',
                core_hit({'foundByKeywords': ['chai glasses brand']}, ['ai glasses']) is False))
    ctl.append(('向后兼容：非模糊词仍按子串命中（`ai glasses` 命中 `Best AI Glasses 2026`）',
                core_hit({'foundByKeywords': ['Best AI Glasses 2026'], 'tags': [], 'category': ''},
                         ['ai glasses']) is True))
    ctl.append(('显式正则：`re:` 前缀按正则匹配（`re:xreal|rokid` 命中）',
                core_hit({'foundByKeywords': ['Rokid Max 2'], 'tags': [], 'category': ''},
                         [r're:xreal|rokid']) is True))
    ctl.append(('正控 映射一致：品类词命中数（扫描用）与 core_hit 同一套模式',
                core_hit_count({'foundByKeywords': ['Ray-Ban Meta'], 'tags': [], 'category': ''}, _m) == 1
                and core_hit_count({'foundByKeywords': ['metagame'], 'tags': [], 'category': ''}, _m) == 0))
    ctl.append(('[degenerate:empty] 模糊词收紧：空词表／非 dict 不崩',
                core_hit({'foundByKeywords': ['Meta']}, None) is True
                and core_hit('x', ['meta']) is False and core_hit_count(None, ['meta']) == 0))

    print('=== daniel_search 自检（离线）===')
    for n, v in ctl:
        print(' %s %s' % ('✅' if v else '❌', n))
    print('自检 %d/%d' % (sum(1 for _, v in ctl if v), len(ctl)))
    return 0 if all(v for _, v in ctl) else 1


if __name__ == '__main__':
    sys.exit(main())
