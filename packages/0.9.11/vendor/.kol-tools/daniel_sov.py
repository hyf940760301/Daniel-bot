#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daniel_sov.py —— Daniel 系统「SOV 全家桶」直连工具（Exposure SOV／SEO SOV／竞品与品类／Dashboard 汇总）。

**为什么要有它**（TICKET-134）：把 Intelligence 里的 SOV／竞品／品类链路从「每次现探 bundle」
变成一条命令 —— 读类直接出数，触发类带守卫，写类**默认不执行**。

通路（实证 · 2026-10-10）：前端 React SPA ＋ tRPC 同源 `/api/trpc`（`daniel_client.py`）。
  · 读类 **GET**（POST 到读路由 → 405 `Unsupported POST-request to query procedure`）；
  · 触发／写类 **POST**（body `{"json": <input>}`）。

🔴 路由与入参键以 **前端 bundle 调用点** 为准（不是命名习惯、也不是旧记忆）：
  · `ExposureSov-BACjvFSE.js`／`SeoSov-CnjOeuuP.js`／`CategorySettings-D9ndCfX1.js`
    ／`CategoryManagement--zl5ZQFQ.js`／`DashboardNew-DxKykGgd.js`
    ／`useBrandCategory-hjhnbjk3.js`（profile 解析）。
  · 品牌 → 品类档案：`sovCategories.getByBrand({brandId})`，元素里 **`assocId` 才是 `categoryProfileId`**、
    **`id` 是 `categoryId`**、`countries` 就是 `monitoringMarkets`。

入参键（逐字 · bundle 调用点）
  · `exposureSov.getSummary`   ← `{categoryProfileId, categoryId, country, days, brandId}`
  · `exposureSov.getBrandVideos` ← `{categoryProfileId, categoryId, country, brand, days, limit, brandId}`
  · `exposureSov.runCollection` ← `{categoryProfileId, categoryId, country, brandId}`
  · `exposureSov.forceRefresh`  ← 同上 ＋ **`confirmation:"FORCE_REFRESH"`（必需字面量，缺失／错值 → 400）**
  · `exposureSov.getTaskStatus` ← `{taskId}`
  · `seoSov.listWeeks`／`getConfigurationStatus`／`getHeatmap`／`getKeywordDetail`（＋`weekOf`／`keyword`）
    ← `{categoryProfileId, brandId, categoryId, country}`；`seoSov.runCollection` 同键；`seoSov.getTaskStatus` ← `{taskId}`
  · `sovCategories.list` ← 无入参；`sovCategories.getByBrand` ← `{brandId}`；`sovCategories.getFilterStats` ← `{categoryProfileId}`
  · `dashboard.getSovOverview` ← `{categoryProfileId, categoryId, country, days, brandId}`
  · `dashboard.getAvailableBrands` ← `{categoryProfileId, categoryId, brandId, country}`

🔴 三条纪律（本工具内置）
  ① **触发类必须显式确认**：`--run-exposure`／`--run-seo`／`--force-refresh` 不带 `--yes` 只打印计划并 `exit 1`；
     `--dry-run` 打印计划并 `exit 0`（不发送请求）。**一次只跑一个，不得反复触发**。
  ② **写类默认不执行**：`--write-cmd <route>` 只回显已定位的入参键，**永远不执行**（需总监指令后另行放开）。
  ③ **写后回读**：触发类拿到 `taskId` 后必须轮询 `getTaskStatus` 直到终态或超时，并打印耗时。

用法：
  python3 .kol-tools/daniel_sov.py --exposure-summary
  python3 .kol-tools/daniel_sov.py --brand-videos --video-brand "Halliday"
  python3 .kol-tools/daniel_sov.py --task-status --kind exposure --task-id <uuid>
  python3 .kol-tools/daniel_sov.py --run-exposure --dry-run          # 只打印计划
  python3 .kol-tools/daniel_sov.py --run-exposure --yes              # 真跑（1 次，最小范围）
  python3 .kol-tools/daniel_sov.py --seo-weeks
  python3 .kol-tools/daniel_sov.py --seo-heatmap [--week 2026-W41]
  python3 .kol-tools/daniel_sov.py --seo-keyword --keyword "ai glasses review"
  python3 .kol-tools/daniel_sov.py --run-seo --yes
  python3 .kol-tools/daniel_sov.py --categories
  python3 .kol-tools/daniel_sov.py --competitors
  python3 .kol-tools/daniel_sov.py --sov-overview
  python3 .kol-tools/daniel_sov.py --write-cmd sovCategories.unlinkBrand
  python3 .kol-tools/daniel_sov.py --self-test                        # 离线自检（不联网）
"""
import argparse
import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:          # 兄弟模块 daniel_io：脚本直跑与被别的仪器当库载入两条路都要能 import
    sys.path.insert(0, HERE)
import daniel_io  # noqa: E402  （TICKET-168：`--json` 出口的唯一收口层）

DEFAULT_BRAND_ID = 3690002          # Halliday
DEFAULT_DAYS = 90
DEFAULT_LIMIT = 200
FORCE_REFRESH_LITERAL = 'FORCE_REFRESH'

# 🔴 写类路由（TICKET-134 L16）：**只定位，不执行**
WRITE_ROUTES = {
    'sovCategories.addCompetitorWithValidation': '{categoryProfileId, categoryId, brandId, competitorName}',
    'sovCategories.updateBrandConfig': '{categoryProfileId, categoryId, brandId, competitors[] | countries[]}',
    'sovCategories.updateFilterKeywords': '{categoryProfileId, positiveKeywords[] | negativeKeywords[]}',
    'sovCategories.applyDiagnosis': '{categoryProfileId, addNegative[], removeNegative[], addPositive[]}',
    'sovCategories.confirmAISetup': '{brandId, categoryName, categoryDescription, positiveKeywords[], negativeKeywords[], competitors[]}',
    'sovCategories.unlinkBrand': '{categoryProfileId, categoryId, brandId}',
    # 同属 mutation（有副作用／耗算力），同样只定位不执行：
    'sovCategories.runDiagnosis': '{categoryProfileId, country, feedback}',
    'sovCategories.aiSetup': '{brandId, productHint}',
    'sovCategories.generateFilterKeywords': '{categoryProfileId}',
}
TERMINAL_STATUS = ('completed', 'failed', 'stale')


def _load_client():
    spec = importlib.util.spec_from_file_location('dc', os.path.join(HERE, 'daniel_client.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 纯函数（可离线自检的部分）────────────────────────────────────────────
def resolve_profile(profiles, ref=None):
    """从 `sovCategories.getByBrand` 结果里选一个品类档案。

    返回 dict（含 `categoryId`＝元素 `id`、`categoryProfileId`＝元素 `assocId`）。
    退化输入（None／空列表）→ 抛错；`ref` 歧义 → 抛错，**不猜**。
    """
    if not isinstance(profiles, list) or not profiles:
        raise ValueError('该品牌下没有品类档案（sovCategories.getByBrand 返回空）')
    if ref in (None, ''):
        return profiles[0]
    rs = str(ref)
    for p in profiles:
        if isinstance(p, dict) and (str(p.get('assocId')) == rs or str(p.get('id')) == rs):
            return p
    names = ', '.join(str(p.get('name')) for p in profiles if isinstance(p, dict))
    raise ValueError('找不到品类档案「%s」；可选：%s' % (rs, names))


def profile_ids(profile):
    """把档案元素翻译成两个 id：`(categoryProfileId=assocId, categoryId=id)`。"""
    if not isinstance(profile, dict):
        raise ValueError('品类档案无效')
    cp = profile.get('assocId')
    ci = profile.get('id')
    if cp is None or ci is None:
        raise ValueError('品类档案缺少 assocId／id')
    return int(cp), int(ci)


def profile_markets(profile):
    """监控市场（＝ `country` 取值域）；缺失回落 operatingMarkets，再回落空列表。"""
    if not isinstance(profile, dict):
        return []
    for k in ('countries', 'operatingMarkets'):
        v = profile.get(k)
        if isinstance(v, list) and v:
            return [str(x) for x in v]
    return []


def build_exposure_input(profile, country, days, brand_id):
    """`exposureSov.getSummary` 入参（逐字键序与 bundle 一致）。"""
    cp, ci = profile_ids(profile)
    return {'categoryProfileId': cp, 'categoryId': ci, 'country': str(country),
            'days': int(days), 'brandId': int(brand_id)}


def build_brand_videos_input(profile, country, days, video_brand, limit, brand_id):
    """`exposureSov.getBrandVideos` 入参（多一个 `brand` 与 `limit`）。"""
    d = build_exposure_input(profile, country, days, brand_id)
    d['brand'] = str(video_brand)
    d['limit'] = int(limit)
    return d


def build_seo_input(profile, country, brand_id):
    """SEO 四读 ＋ runCollection 共用入参（注意键序：brandId 在 categoryId 之前）。"""
    cp, ci = profile_ids(profile)
    return {'categoryProfileId': cp, 'brandId': int(brand_id), 'categoryId': ci, 'country': str(country)}


def build_run_collection_input(profile, country, brand_id):
    """`exposureSov.runCollection` 入参 —— 🔴 **只有四键，不带 `days`／`limit`／`brand`**
    （逐字 · `ExposureSov-BACjvFSE.js` 调用点 `T.mutate({categoryProfileId,categoryId,country,brandId})`）。
    """
    cp, ci = profile_ids(profile)
    return {'categoryProfileId': cp, 'categoryId': ci, 'country': str(country),
            'brandId': int(brand_id)}


def build_force_refresh_input(profile, country, brand_id):
    """`exposureSov.forceRefresh` 入参 —— **`confirmation` 是必需字面量 `FORCE_REFRESH`**。"""
    d = build_run_collection_input(profile, country, brand_id)
    d['confirmation'] = FORCE_REFRESH_LITERAL
    return d


def build_sov_overview_input(profile, country, days, brand_id):
    return build_exposure_input(profile, country, days, brand_id)


def guard_trigger(args, plan_lines):
    """触发类守卫：`--dry-run` → 预览 exit 0；无 `--yes` → 预览 exit 1；否则放行（返回 None）。"""
    if args.dry_run:
        return 0
    if not getattr(args, 'yes', False):
        return 1
    return None


def guard_write(route):
    """写类守卫：**永远不放行**（TICKET-134 L16「未经指令不得改配置」）。"""
    if route not in WRITE_ROUTES:
        return 'UNKNOWN'
    return 'REFUSE'


def pick_week(weeks, ref=None):
    """从 `seoSov.listWeeks` 结果里选周次（接口按新→旧返回，默认取第 1 条）。"""
    if not isinstance(weeks, list) or not weeks:
        raise ValueError('该配置下没有 SEO 周快照（listWeeks 返回空）')
    if ref in (None, ''):
        return weeks[0]
    rs = str(ref)
    for w in weeks:
        if isinstance(w, dict) and str(w.get('weekOf')) == rs:
            return w
    avail = ', '.join(str(w.get('weekOf')) for w in weeks if isinstance(w, dict))
    raise ValueError('找不到周次「%s」；可选：%s' % (rs, avail))


def task_brief(task):
    """任务对象 → 一行摘要（退化输入不得致崩）。"""
    if not isinstance(task, dict):
        return '（无任务对象）'
    return 'id=%s status=%s progress=%s err=%s' % (
        mask_id(task.get('id')), task.get('status'), task.get('progress'), task.get('error'))


def mask_id(tid):
    """taskId 脱敏：保留前 8 位，其余打码（文档／日志用）。"""
    if not tid:
        return 'None'
    s = str(tid)
    return s[:8] + '…' if len(s) > 9 else s


def is_terminal(status):
    return str(status) in TERMINAL_STATUS


def brand_share(brands, name):
    """从 `getSummary.brands` 或 `getSovOverview.brands` 里取某品牌的份额（百分比，1 位小数）。

    返回 None ＝ 该品牌不在结果里（**不臆造 0**）。
    """
    if not isinstance(brands, list) or not name:
        return None
    key = str(name).strip().lower()
    for b in brands:
        if not isinstance(b, dict):
            continue
        n = b.get('brand') if b.get('brand') is not None else b.get('name')
        if n is not None and str(n).strip().lower() == key:
            if 'share' in b and b.get('share') is not None:
                return round(float(b['share']), 1)
            return None
    return None


def top_brands(rows, key, n=5):
    """按 `key` 降序取前 n（退化输入 → 空列表）。"""
    if not isinstance(rows, list):
        return []
    ok = [r for r in rows if isinstance(r, dict) and isinstance(r.get(key), (int, float))]
    return sorted(ok, key=lambda r: r[key], reverse=True)[:n]


def fmt_int(v):
    """整数千分位；非数值原样返回字符串（不得致崩）。"""
    try:
        return '{:,}'.format(int(v))
    except (TypeError, ValueError):
        return str(v)


def describe_trigger_return(res):
    """`runCollection`／`forceRefresh` 返回值 → 判定文案（是否真的创建了新任务）。"""
    if not isinstance(res, dict):
        return '（返回体异常）'
    if res.get('created'):
        return '已创建新任务（created=True）'
    if res.get('triggered'):
        return '已触发既有任务（triggered=True）'
    if res.get('reset'):
        return '已重置并复用任务（reset=True）'
    return '未创建新任务（命中已有任务／配置未变化）'


# ── 在线动作 ────────────────────────────────────────────────────────────
def _profile(d, brand_id, ref=None):
    profs = d.query('sovCategories.getByBrand', {'brandId': int(brand_id)}) or []
    return resolve_profile(profs, ref)


def _resolve_brand_id(d, ref):
    """品牌名或 id → brandId（名字歧义 → 报错，不猜）。

    🔴 名字走 **跨工作区索引**（`Daniel.resolve_brand_ref`）—— 与"当前活跃工作区"无关；
    旧实现用无参 `brands.list`，活跃工作区一被切就会"找不到品牌"（2026-10-10 修）。
    """
    if ref is None:
        return DEFAULT_BRAND_ID
    s = str(ref).strip()
    if s.isdigit():
        return int(s)
    if not hasattr(d, 'resolve_brand_ref'):
        raise SystemExit('该客户端无 resolve_brand_ref ⇒ 按名字解析不可用，请直接给 --brand <brandId>')
    return int(d.resolve_brand_ref(s)['id'])


def _dump(obj, args, limit=None):
    txt = json.dumps(obj, ensure_ascii=False, indent=1)
    if limit and len(txt) > limit:
        txt = txt[:limit] + '\n…（截断，完整体见 --json 输出）'
    print(txt)


def cmd_exposure_summary(d, args, ctx):
    inp = build_exposure_input(ctx['profile'], ctx['country'], args.days, ctx['brand_id'])
    s = d.query('exposureSov.getSummary', inp)
    if args.json:
        _dump(s, args); return 0
    print('Exposure SOV ｜品牌「%s」｜%s ｜近 %d 天' % (ctx['brand_name'], ctx['country'], args.days))
    print('  数据截至 %s ｜配置状态 %s ｜需刷新 %s ｜刷新中 %s'
          % (s.get('lastUpdated'), s.get('configurationState'), s.get('refreshRequired'),
             s.get('refreshInProgress')))
    print('  最近任务：%s' % task_brief(s.get('latestTask')))
    if s.get('lastTaskError'):
        print('  ⚠️ 最近任务错误：%s' % s.get('lastTaskError'))
    print('  观测样本：%s 条视频／%s 次观看；归属本品牌 %s 次'
          % (fmt_int(s.get('observedVideoCount')), fmt_int(s.get('observedTotalViews')),
             fmt_int(s.get('attributedTotalViews'))))
    print('  品牌份额（按观看）：')
    for r in top_brands(s.get('brands'), 'totalViews', 10):
        print('    %-22s %14s  views ｜ 独占 %s 条 ｜ 付费占比 %s%%'
              % (r.get('brand'), fmt_int(r.get('totalViews')), fmt_int(r.get('exclusiveCount')),
                 r.get('paidPercent')))
    ec = s.get('emergingContent') or {}
    print('  新兴内容：%s 条／%s 次观看' % (fmt_int(ec.get('videoCount')), fmt_int(ec.get('totalViews'))))
    return 0


def cmd_brand_videos(d, args, ctx):
    inp = build_brand_videos_input(ctx['profile'], ctx['country'], args.days,
                                   args.video_brand, args.limit, ctx['brand_id'])
    vids = d.query('exposureSov.getBrandVideos', inp) or []
    if args.json:
        _dump(vids, args); return 0
    print('曝光视频明细 ｜%s ｜%s ｜近 %d 天 ｜共 %d 条（limit %d）'
          % (args.video_brand, ctx['country'], args.days, len(vids), args.limit))
    for v in top_brands(vids, 'viewCount', 10):
        print('    %-12s %14s  %s ｜ %s' % (v.get('isPaid') and 'paid' or 'organic',
                                            fmt_int(v.get('viewCount')),
                                            str(v.get('publishedAt'))[:10],
                                            str(v.get('videoTitle'))[:60]))
    return 0


def cmd_task_status(d, args, ctx):
    if not args.task_id:
        print('❌ --task-status 需要 --task-id')
        return 1
    route = 'exposureSov.getTaskStatus' if args.kind == 'exposure' else 'seoSov.getTaskStatus'
    t = d.query(route, {'taskId': args.task_id})
    if t is None:
        print('（%s 返回 null：该 taskId 不存在或无权限）' % route)
        return 0
    if args.json:
        _dump(t, args); return 0
    print('%s ｜%s' % (route, task_brief(t)))
    if t.get('result'):
        print('  result: %s' % json.dumps(t['result'], ensure_ascii=False)[:500])
    return 0


def _run_trigger(d, args, ctx, route, label, inp):
    print('【%s】%s' % (label, route))
    print('  入参：%s' % json.dumps(inp, ensure_ascii=False))
    code = guard_trigger(args, None)
    if code == 0:
        print('  （dry-run）未发送请求。真跑请去掉 --dry-run 并加 --yes（**一次只跑一个**）。')
        return 0
    if code == 1:
        print('  ⚠️ 未带 --yes ⇒ 只预览不执行。确认后重跑并加 --yes。')
        return 1
    t0 = time.time()
    res = d.mutate(route, inp)
    print('  返回：%s' % json.dumps(res, ensure_ascii=False))
    print('  判定：%s' % describe_trigger_return(res))
    tid = (res or {}).get('taskId')
    if not tid:
        print('  ⚠️ 未返回 taskId —— 无法轮询。')
        return 0
    print('  taskId（脱敏）：%s' % mask_id(tid))
    status_route = 'exposureSov.getTaskStatus' if 'exposure' in route else 'seoSov.getTaskStatus'
    deadline = t0 + args.poll_seconds
    last = None
    while True:
        last = d.query(status_route, {'taskId': tid})
        el = round(time.time() - t0, 1)
        st = (last or {}).get('status')
        print('    [%ss] status=%s progress=%s' % (el, st, (last or {}).get('progress')))
        if is_terminal(st) or time.time() > deadline:
            break
        time.sleep(args.poll_interval)
    print('  终态：%s' % task_brief(last))
    if (last or {}).get('error'):
        print('  ❌ 错误：%s' % last.get('error'))
    if (last or {}).get('result'):
        print('  result：%s' % json.dumps(last['result'], ensure_ascii=False)[:400])
    print('  耗时：%ss' % round(time.time() - t0, 1))
    return 0


def cmd_run_exposure(d, args, ctx):
    inp = build_run_collection_input(ctx['profile'], ctx['country'], ctx['brand_id'])
    return _run_trigger(d, args, ctx, 'exposureSov.runCollection', '触发 Exposure 采集', inp)


def cmd_force_refresh(d, args, ctx):
    inp = build_force_refresh_input(ctx['profile'], ctx['country'], ctx['brand_id'])
    return _run_trigger(d, args, ctx, 'exposureSov.forceRefresh', '强制刷新 Exposure', inp)


def cmd_run_seo(d, args, ctx):
    inp = build_seo_input(ctx['profile'], ctx['country'], ctx['brand_id'])
    return _run_trigger(d, args, ctx, 'seoSov.runCollection', '触发 SEO 采集', inp)


def cmd_seo_weeks(d, args, ctx):
    wk = d.query('seoSov.listWeeks', build_seo_input(ctx['profile'], ctx['country'], ctx['brand_id'])) or []
    if args.json:
        _dump(wk, args); return 0
    print('SEO 周快照 ｜共 %d 周（接口按新→旧返回）' % len(wk))
    for w in wk:
        print('    %s  关键词 %s／有覆盖 %s ｜ 生成于 %s'
              % (w.get('weekOf'), w.get('totalKeywords'), w.get('keywordsWithPresence'),
                 str(w.get('createdAt'))[:19]))
    return 0


def cmd_seo_heatmap(d, args, ctx):
    base = build_seo_input(ctx['profile'], ctx['country'], ctx['brand_id'])
    wk = d.query('seoSov.listWeeks', base) or []
    week = pick_week(wk, args.week)['weekOf']
    h = d.query('seoSov.getHeatmap', dict(base, weekOf=week))
    if args.json:
        _dump(h, args); return 0
    kws = h.get('keywords') or []
    brands = h.get('brands') or []
    print('SEO 热力图 ｜%s ｜%s ｜%d 关键词 × %d 品牌' % (week, ctx['country'], len(kws), len(brands)))
    print('  品牌：%s' % ' / '.join(brands))
    hm = h.get('heatmap') or {}
    for kw in kws[:8]:
        hits = []
        for b, d2 in (hm.get(kw) or {}).items():
            if isinstance(d2, dict) and d2.get('bestRank') is not None:
                hits.append((int(d2['bestRank']), b))
        hits.sort()
        print('    %-32s %s' % (kw[:32], ' ｜ '.join('%s #%d' % (b, r) for r, b in hits[:5]) or '—'))
    return 0


def cmd_seo_keyword(d, args, ctx):
    if not args.keyword:
        print('❌ --seo-keyword 需要 --keyword')
        return 1
    base = build_seo_input(ctx['profile'], ctx['country'], ctx['brand_id'])
    wk = d.query('seoSov.listWeeks', base) or []
    week = pick_week(wk, args.week)['weekOf']
    rows = d.query('seoSov.getKeywordDetail', dict(base, weekOf=week, keyword=args.keyword)) or []
    if args.json:
        _dump(rows, args); return 0
    print('SEO 关键词明细 ｜「%s」｜%s ｜%d 条结果' % (args.keyword, week, len(rows)))
    for r in rows[:10]:
        print('    #%-3s %-14s %12s  %s' % (r.get('rank'), str(r.get('brandAttribution'))[:14],
                                            fmt_int(r.get('viewCount')), str(r.get('videoTitle'))[:56]))
    new = sum(1 for r in rows if r.get('isNew'))
    gone = sum(1 for r in rows if r.get('disappeared'))
    print('  新进 %d 条／掉出 %d 条' % (new, gone))
    return 0


def cmd_categories(d, args, ctx):
    cats = d.query('sovCategories.list') or []
    profs = d.query('sovCategories.getByBrand', {'brandId': ctx['brand_id']}) or []
    if args.json:
        _dump({'categories': cats, 'brandProfiles': profs}, args); return 0
    linked = {p.get('id') for p in profs if isinstance(p, dict)}
    print('品类清单（sovCategories.list）｜共 %d 个；※＝已挂在本品牌下' % len(cats))
    for c in cats:
        mark = '※' if c.get('id') in linked else ' '
        print('  %s id=%-9s %s' % (mark, c.get('id'), c.get('name')))
    print('本品牌（%s）品类档案：' % ctx['brand_name'])
    for p in profs:
        cp, ci = profile_ids(p)
        print('    categoryProfileId=%s ／ categoryId=%s ｜ %s ｜ 市场 %s'
              % (cp, ci, p.get('name'), ','.join(profile_markets(p))))
    return 0


def cmd_competitors(d, args, ctx):
    p = ctx['profile']
    cp, ci = profile_ids(p)
    fs = d.query('sovCategories.getFilterStats', {'categoryProfileId': cp}) or {}
    if args.json:
        _dump({'profile': p, 'filterStats': fs}, args); return 0
    print('竞品与品类配置 ｜%s ｜categoryProfileId %s ／ categoryId %s' % (ctx['brand_name'], cp, ci))
    print('  品类：%s（taxonomy: %s）' % (p.get('name'), p.get('taxonomyName')))
    print('  监控市场：%s ｜ 每品牌上限 %s' % (','.join(profile_markets(p)), p.get('maxOperatingMarketsPerBrand')))
    print('  竞品（%d）：%s' % (len(p.get('competitors') or []), ' / '.join(p.get('competitors') or [])))
    print('  已知品牌（%d）：%s' % (len(p.get('knownBrands') or []), ' / '.join(p.get('knownBrands') or [])))
    print('  正向过滤词（%d）：%s' % (len(fs.get('positiveKeywords') or []),
                                     ', '.join((fs.get('positiveKeywords') or [])[:12])))
    print('  负向过滤词（%d）：%s' % (len(fs.get('negativeKeywords') or []),
                                     ', '.join((fs.get('negativeKeywords') or [])[:12])))
    print('  最近审计：%s ｜ 审计日志 %d 条' % (fs.get('lastAuditAt') or '无', len(fs.get('auditLog') or [])))
    return 0


def cmd_sov_overview(d, args, ctx):
    inp = build_sov_overview_input(ctx['profile'], ctx['country'], args.days, ctx['brand_id'])
    o = d.query('dashboard.getSovOverview', inp)
    avail = d.query('dashboard.getAvailableBrands',
                    {'categoryProfileId': inp['categoryProfileId'], 'categoryId': inp['categoryId'],
                     'brandId': inp['brandId'], 'country': inp['country']})
    if args.json:
        _dump({'overview': o, 'availableBrands': avail}, args); return 0
    print('Dashboard SOV 汇总 ｜%s ｜%s' % (ctx['brand_name'], ctx['country']))
    print('  全品类合计：%s 次观看／%s 条视频' % (fmt_int(o.get('totalViews')), fmt_int(o.get('totalVideos'))))
    for r in top_brands(o.get('brands'), 'viewCount', 10):
        print('    %-22s share %5s%% ｜ %14s 观看 ｜ %s 条视频'
              % (r.get('name'), r.get('share'), fmt_int(r.get('viewCount')), fmt_int(r.get('videoCount'))))
    print('  可查品牌（getAvailableBrands，%d）：%s' % (len(avail or []), ' / '.join(avail or [])))
    return 0


def cmd_write(d, args, ctx):
    route = args.write_cmd
    if guard_write(route) == 'UNKNOWN':
        print('❌ 未知写路由「%s」；已定位的写路由：%s' % (route, ', '.join(sorted(WRITE_ROUTES))))
        return 2
    print('🔒 写类路由（%s）' % route)
    print('  已定位入参键：%s' % WRITE_ROUTES[route])
    print('  ⚠️ 本工具**不执行写类路由**（TICKET-134：未经总监指令不得改 %s 的竞品／品类配置）。'
          % ctx['brand_name'])
    if args.dry_run:
        print('  （dry-run）仅回显定位结果。')
    return 3


def main():
    ap = argparse.ArgumentParser(add_help=True)
    for f in ('exposure-summary', 'brand-videos', 'task-status', 'run-exposure', 'force-refresh',
              'seo-weeks', 'seo-heatmap', 'seo-keyword', 'run-seo', 'categories', 'competitors',
              'sov-overview', 'self-test'):
        ap.add_argument('--' + f, action='store_true')
    ap.add_argument('--write-cmd', metavar='ROUTE', help='写类路由：只定位入参，不执行')
    ap.add_argument('--brand', metavar='REF', help='品牌名或 brandId（默认 Halliday 3690002）')
    ap.add_argument('--country', metavar='CC', help='市场（默认取档案 countries[0]）')
    ap.add_argument('--days', type=int, default=DEFAULT_DAYS)
    ap.add_argument('--profile', metavar='ID', help='categoryProfileId（assocId）')
    ap.add_argument('--video-brand', metavar='NAME', default='Halliday', help='getBrandVideos 的 brand')
    ap.add_argument('--limit', type=int, default=DEFAULT_LIMIT)
    ap.add_argument('--kind', choices=('exposure', 'seo'), default='exposure')
    ap.add_argument('--task-id', metavar='UUID')
    ap.add_argument('--week', metavar='YYYY-Www')
    ap.add_argument('--keyword')
    ap.add_argument('--yes', action='store_true', help='触发类／写类显式确认')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--json', action='store_true', help='输出原始 JSON')
    ap.add_argument('--poll-seconds', type=float, default=900)
    ap.add_argument('--poll-interval', type=float, default=20)
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    cmds = [args.exposure_summary, args.brand_videos, args.task_status, args.run_exposure,
            args.force_refresh, args.seo_weeks, args.seo_heatmap, args.seo_keyword, args.run_seo,
            args.categories, args.competitors, args.sov_overview, bool(args.write_cmd)]
    if not any(cmds):
        # `--json` 时帮助文本走 stderr：stdout 只能有那**一个** JSON 文档（TICKET-168）。
        ap.print_help(file=sys.stderr) if args.json else ap.print_help()
        return 2

    dc = _load_client()
    d = dc.Daniel(verbose=False)
    d.login()

    brand_id = _resolve_brand_id(d, args.brand)
    brand_name = 'brand %s' % brand_id
    if hasattr(d, 'resolve_brand_ref'):        # 🔴 走跨工作区解析，不扫"当前工作区列表"
        try:
            brand_name = d.resolve_brand_ref(brand_id).get('name') or brand_name
        except SystemExit:
            pass
    profile = _profile(d, brand_id, args.profile)
    country = args.country or (profile_markets(profile) or ['US'])[0]
    ctx = {'brand_id': brand_id, 'brand_name': brand_name, 'profile': profile, 'country': country}
    cp, ci = profile_ids(profile)
    # `--json` 时这行人话**不能**进 stdout：契约要求 stdout 有且只有一个 JSON 文档，
    # 中文行排在 JSON 前面会让"吃掉第一个文档"的调用方拿到文本（TICKET-168）。改走 stderr。
    _where = ('— 品牌「%s」(%s) ／ categoryProfileId %s ／ categoryId %s ／ 市场 %s'
              % (brand_name, brand_id, cp, ci, country))
    print(_where, file=sys.stderr) if args.json else print(_where)

    if args.exposure_summary:
        return cmd_exposure_summary(d, args, ctx)
    if args.brand_videos:
        return cmd_brand_videos(d, args, ctx)
    if args.task_status:
        return cmd_task_status(d, args, ctx)
    if args.run_exposure:
        return cmd_run_exposure(d, args, ctx)
    if args.force_refresh:
        return cmd_force_refresh(d, args, ctx)
    if args.seo_weeks:
        return cmd_seo_weeks(d, args, ctx)
    if args.seo_heatmap:
        return cmd_seo_heatmap(d, args, ctx)
    if args.seo_keyword:
        return cmd_seo_keyword(d, args, ctx)
    if args.run_seo:
        return cmd_run_seo(d, args, ctx)
    if args.categories:
        return cmd_categories(d, args, ctx)
    if args.competitors:
        return cmd_competitors(d, args, ctx)
    if args.sov_overview:
        return cmd_sov_overview(d, args, ctx)
    if args.write_cmd:
        return cmd_write(d, args, ctx)
    return 1


# ── 离线自检（不联网）──────────────────────────────────────────────────
def self_test():
    ctl = []
    prof = {'id': 360001, 'assocId': 2310001, 'name': 'AI Smart Glasses',
            'countries': ['US', 'CA', 'GB'], 'competitors': ['XREAL'], 'knownBrands': ['Halliday']}

    # 1 profile 解析
    ctl.append(('正控 按 assocId 解析档案', resolve_profile([prof], '2310001')['id'] == 360001))
    ctl.append(('正控 缺省取第 1 个档案', resolve_profile([prof], None)['assocId'] == 2310001))
    ctl.append(('[degenerate:empty] 空档案列表 → 报错且提示"没有品类档案"',
                _raises(lambda: resolve_profile([], None), '没有品类档案')))
    ctl.append(('[degenerate:type_unit] 非列表 → 报错', _raises(lambda: resolve_profile(None, '1'), '没有品类档案')))
    ctl.append(('正控 找不到档案 → 报错且列出可选值',
                _raises(lambda: resolve_profile([prof], '999'), '可选')))

    # 2 id 双译名
    ctl.append(('正控 assocId→categoryProfileId／id→categoryId（这两个 id 不可混用）',
                profile_ids(prof) == (2310001, 360001)))
    ctl.append(('[degenerate:empty] 缺 assocId → 报错',
                _raises(lambda: profile_ids({'id': 1}), 'assocId')))

    # 3 市场取值
    ctl.append(('正控 countries 即 monitoringMarkets', profile_markets(prof) == ['US', 'CA', 'GB']))
    ctl.append(('[degenerate:empty] 无 countries → 回落 operatingMarkets／空列表',
                profile_markets({'operatingMarkets': ['DE']}) == ['DE'] and profile_markets({}) == []))

    # 4 入参键（逐字）
    e = build_exposure_input(prof, 'US', 90, DEFAULT_BRAND_ID)
    ctl.append(('正控 getSummary 五键齐备且无多余键',
                set(e) == {'categoryProfileId', 'categoryId', 'country', 'days', 'brandId'}))
    v = build_brand_videos_input(prof, 'US', 90, 'Halliday', 200, DEFAULT_BRAND_ID)
    ctl.append(('正控 getBrandVideos ＝ summary ＋ brand/limit',
                set(v) == set(e) | {'brand', 'limit'} and v['limit'] == 200))
    s = build_seo_input(prof, 'US', DEFAULT_BRAND_ID)
    ctl.append(('正控 SEO 入参四键（不含 days）',
                set(s) == {'categoryProfileId', 'brandId', 'categoryId', 'country'}))

    # 5 forceRefresh 字面量
    rc = build_run_collection_input(prof, 'US', DEFAULT_BRAND_ID)
    ctl.append(('正控 runCollection 只有四键（🔴 不带 days／limit／brand）',
                set(rc) == {'categoryProfileId', 'categoryId', 'country', 'brandId'}))
    f = build_force_refresh_input(prof, 'US', DEFAULT_BRAND_ID)
    ctl.append(('正控 forceRefresh ＝ runCollection ＋ confirmation 且不带 days',
                f.get('confirmation') == 'FORCE_REFRESH' and 'days' not in f
                and set(f) == set(rc) | {'confirmation'}))
    ctl.append(('正控 forceRefresh 字面量与实测一致（实测错值 → 400 invalid_value）',
                FORCE_REFRESH_LITERAL == 'FORCE_REFRESH'))

    # 6 触发守卫
    class _A:
        def __init__(self, dry, yes):
            self.dry_run, self.yes = dry, yes
    ctl.append(('正控 --dry-run → 放行预览（exit 0）', guard_trigger(_A(True, False), None) == 0))
    ctl.append(('🔴 无 --yes 的触发 → 拒绝（exit 1）', guard_trigger(_A(False, False), None) == 1))
    ctl.append(('正控 --yes → 放行执行（None）', guard_trigger(_A(False, True), None) is None))

    # 7 写类守卫
    ctl.append(('🔴 写类路由永远不放行（REFUSE）',
                guard_write('sovCategories.unlinkBrand') == 'REFUSE'
                and guard_write('sovCategories.updateBrandConfig') == 'REFUSE'
                and guard_write('sovCategories.addCompetitorWithValidation') == 'REFUSE'))
    ctl.append(('正控 未知写路由 → UNKNOWN', guard_write('sovCategories.nope') == 'UNKNOWN'))
    ctl.append(('正控 写路由清单覆盖 TICKET-134 L16 的六条',
                set(WRITE_ROUTES) >= {'sovCategories.addCompetitorWithValidation',
                                      'sovCategories.updateBrandConfig',
                                      'sovCategories.updateFilterKeywords',
                                      'sovCategories.applyDiagnosis',
                                      'sovCategories.confirmAISetup',
                                      'sovCategories.unlinkBrand'}))

    # 8 周次选择
    weeks = [{'weekOf': '2026-W41', 'id': 1800003}, {'weekOf': '2026-W37', 'id': 1440002}]
    ctl.append(('正控 缺省取最新周（接口按新→旧）', pick_week(weeks, None)['weekOf'] == '2026-W41'))
    ctl.append(('[degenerate:empty] 无周快照 → 报错', _raises(lambda: pick_week([], None), '没有 SEO 周快照')))
    ctl.append(('正控 指定不存在的周 → 报错且列出可选',
                _raises(lambda: pick_week(weeks, '2026-W01'), '可选')))

    # 9 任务与脱敏
    ctl.append(('正控 终态判定', is_terminal('completed') and is_terminal('failed') and not is_terminal('running')))
    ctl.append(('[degenerate:empty] 空任务对象摘要不得致崩', '无任务对象' in task_brief(None)))
    ctl.append(('正控 taskId 脱敏只留前 8 位',
                mask_id('b8866824-601c-4016-88ab-0065654126b9') == 'b8866824…'
                and mask_id(None) == 'None'))

    # 10 份额计算
    rows = [{'brand': 'Halliday', 'totalViews': 100}, {'name': 'XREAL', 'share': 12.34}]
    ctl.append(('正控 按名取份额（大小写不敏感／share 四舍五入 1 位）',
                brand_share(rows, 'xreal') == 12.3))
    ctl.append(('[degenerate:empty] 品牌不在结果里 → None（不臆造 0）',
                brand_share(rows, 'Nope') is None and brand_share([], 'x') is None))

    # 11 排序与格式化
    ctl.append(('正控 top_brands 按数值降序、非数值剔除',
                [r['brand'] for r in top_brands(rows, 'totalViews')] == ['Halliday']))
    ctl.append(('[degenerate:type_unit] top_brands 非列表 → 空列表', top_brands(None, 'x') == []))
    ctl.append(('正控 千分位；退化输入原样返回',
                fmt_int(9241245) == '9,241,245' and fmt_int(None) == 'None'))

    # 12 触发返回判定
    ctl.append(('正控 created=True ⇒ 已创建新任务',
                '已创建' in describe_trigger_return({'created': True})))
    ctl.append(('正控 三旗全 False ⇒ 未创建新任务（实测 SEO 命中已有任务）',
                '未创建' in describe_trigger_return({'created': False, 'reset': False, 'triggered': False})))
    ctl.append(('[degenerate:empty] 返回体非 dict 不得致崩', '异常' in describe_trigger_return(None)))

    print('=== daniel_sov 自检（离线）===')
    for n, ok in ctl:
        print(' %s %s' % ('✅' if ok else '❌', n))
    print('自检 %d/%d' % (sum(1 for _, ok in ctl if ok), len(ctl)))
    return 0 if all(ok for _, ok in ctl) else 1


def _raises(fn, needle):
    try:
        fn()
        return False
    except Exception as e:  # noqa: BLE001
        return needle in str(e)


def cli(argv=None):
    """入口包装：**退出码归一 ＋ 失败时恰好一个 JSON 文档**（收口只有这一处，TICKET-168）。

    原先失败时只有 stderr 的中文行、`--json` 的 stdout 上没有 `ok=false` 信封；用户错误
    （如品牌解析不到）也一律以 1 退出，上游据此判成"工具故障"。现统一交给 `daniel_io.cli`。
    本仪器的 `main()` 自己 parse `sys.argv`（不接 argv 形参），故这里用一层薄壳适配。
    """
    return daniel_io.cli(lambda _argv: main(), argv)


if __name__ == '__main__':
    sys.exit(cli())
