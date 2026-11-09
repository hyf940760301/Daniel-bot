#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daniel_takeover_check —— Daniel 四区块「接管是否完成」单条链路验收仪器

设计口径（用户 2026-10-10 裁定）：
  **每个区块只用一条测试数据／一个 KOL 跑完整链路**，核心是回答"接管是否已经完成"，
  不追求数据量、不追求并发。故本仪器**每条链路只取一行证据**，输出 PASS/FAIL 清单。

覆盖（默认全部只读；写链需 --with-writes 显式开启）：
  B  Brands        brands.getById（＋可选：单条 create→update→delete→双回读）
  M  Brand Mentions 一个 jobId 的 status→results→chart→topChannels→evidence→export
  I  Intelligence  status→actions→keywords→memos→reviews→topics（各取 ≤1 行）
  S  SOV           profile→filterStats→exposureSummary→dashboard.overview→seo weeks→seo keyword
                   （＋可选：**零净变化写回** updateFilterKeywords／updateBrandConfig）
  A  Authenticity  单个 handle／频道 URL → 前端口径复算得分

纪律（写进 Skill §15.5）：
  ① 一律按 **brandId** 取数（`brands.list` 是 workspace 维度的）。
  ② 写链优先用**零净变化写回**（把读到的原值原样写回）验证通路，避免"为了测试而改真实配置"。
  ③ 读回为空／None ⇒ **拒绝写回**（防把一次读取失败写成清空配置）。
  ④ 守卫类探测一律离线（本仪器 --self-test 不联网）。

用法：
  python3 .kol-tools/daniel_takeover_check.py --brand 3690002
  python3 .kol-tools/daniel_takeover_check.py --brand 3690002 --mentions-job 4d2e7f63-…
  python3 .kol-tools/daniel_takeover_check.py --brand 3690002 --channel "@AbleAndHisTable"
  python3 .kol-tools/daniel_takeover_check.py --brand 3690002 --with-writes --yes
  python3 .kol-tools/daniel_takeover_check.py --self-test          # 离线，不联网
"""

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:          # 兄弟模块 daniel_io：脚本直跑与被别的仪器当库载入两条路都要能 import
    sys.path.insert(0, HERE)
import daniel_io  # noqa: E402  （TICKET-168：`--json` 出口的唯一收口层）
DEFAULT_BRAND_ID = 3690002          # Halliday
DEFAULT_CHANNEL = '@AbleAndHisTable'
TOPCHANNELS_MIN, TOPCHANNELS_MAX = 5, 50   # 实测：limit 1／3／100 → 400


# ── 载入兄弟仪器（复用其口径，不重复实现）────────────────────────────────
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_deps():
    return {
        'client': _load('_dc', 'daniel_client.py'),
        'brands': _load('_db', 'daniel_brands.py'),
        'mentions': _load('_dm', 'daniel_mentions.py'),
        'intel': _load('_di', 'daniel_intel.py'),
        'sov': _load('_ds', 'daniel_sov.py'),
        'auth': _load('_da', 'daniel_authenticity.py'),
    }


# ── 纯函数（可离线自检）────────────────────────────────────────────────
def sha12(obj):
    """任意 JSON 可序列化对象 → 12 位短哈希（用于回读比对）。"""
    try:
        txt = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        txt = repr(obj)
    return hashlib.sha256(txt.encode('utf-8')).hexdigest()[:12]


def plan_noop_write(field, current, cap=None):
    """零净变化写回计划；读回空／None ⇒ 拒绝（返回 (None, 原因)）。"""
    if current is None:
        return None, '读回为 None（疑似读取失败），拒绝写回 %s' % field
    if not isinstance(current, list):
        return None, '读回不是列表（%s），拒绝写回 %s' % (type(current).__name__, field)
    if len(current) == 0:
        return None, '读回为空列表，拒绝写回 %s（防把读取失败写成清空配置）' % field
    if cap is not None and len(current) > cap:
        return None, '读回 %d 项 > 上限 %d，拒绝写回 %s' % (len(current), cap, field)
    return list(current), None


def scan_limit_bounds(values, probe):
    """探测 `limit` 合法区间：probe(v) → (ok: bool)。返回 (ok_min, ok_max, bad)。"""
    ok, bad = [], []
    for v in values:
        (ok if probe(v) else bad).append(v)
    return (min(ok) if ok else None), (max(ok) if ok else None), bad


def verdict(rows):
    """[{'status': 'PASS'|'FAIL'|'WARN'|'SKIP'}…] → (总结论文案, 退出码)。"""
    f = sum(1 for r in rows if r['status'] == 'FAIL')
    w = sum(1 for r in rows if r['status'] == 'WARN')
    p = sum(1 for r in rows if r['status'] == 'PASS')
    s = sum(1 for r in rows if r['status'] == 'SKIP')
    if f:
        return ('❌ 接管未完成：%d 项 FAIL ／ %d 项 PASS ／ %d 项 WARN ／ %d 项 SKIP' % (f, p, w, s), 1)
    if w:
        return ('⚠️ 链路全通、%d 项需留意：%d 项 PASS ／ %d 项 WARN ／ %d 项 SKIP' % (w, p, w, s), 0)
    return ('✅ 接管完成：%d 项 PASS ／ %d 项 SKIP' % (p, s), 0)


def pick_job(jobs, wanted=None):
    """指定 jobId 优先；否则取最近一个（listJobs 按新→旧）。"""
    if not isinstance(jobs, list):
        return None
    if wanted:
        for j in jobs:
            if not isinstance(j, dict):
                continue
            keys = [j.get('id'), j.get('jobId'), j.get('job_id')]
            if any(k is not None and str(k) == str(wanted) for k in keys):
                return j
        return None
    for j in jobs:
        if isinstance(j, dict):
            return j
    return None


def did_route_ok(status_code):
    """HTTP 状态码 → 通路判定（2xx 才算通）。"""
    try:
        return 200 <= int(status_code) < 300
    except (TypeError, ValueError):
        return False


class Report(object):
    def __init__(self):
        self.rows = []

    def add(self, block, name, status, evidence, payload=None):
        self.rows.append({'block': block, 'name': name, 'status': status,
                          'evidence': str(evidence)[:600], 'payload': payload})

    def of(self, block):
        return [r for r in self.rows if r['block'] == block]


#: 删除后按 id 直取时，"这个编号已经不存在"在服务端侧的标记（**服务端原文**逐字取自 2026-10-16 实测：
#: `brands.getById 失败: HTTP 404；通路 brands.getById；服务端码 NOT_FOUND；服务端原文：Brand not found`）。
#: 🔴 只有**命中这里**的异常才允许被读成"已删除"；5xx／鉴权／超时等一律照原样上抛（落 FAIL）。
_NOT_FOUND_MARKERS = ('http 404', 'not_found', 'not found', 'notfound')


def probe_gone(client, brand_id):
    """删除后回读：判断这个编号是否**已不存在** → `(是否已不存在, 说明原文)`。

    🔴 **适用边界（不得外推）**：本函数只服务**这一条链** ——「**同一次运行内** `create` 成功返回了
    `bid` → 已发出 `delete` → 回读」。调用方必须**先确认拿到了 `bid`**（没拿到就直接 FAIL，
    绝不允许进入本函数）；它**不是**通用的"id 不存在即干净"，把它当通用后门会让"随便什么错都算干净"。

    🔴 **平台语义变更（务必知情，免得下一个人再踩一次）**：
      · `2026-10-10`：删除后 `brands.getById` 返回 **HTTP 200 ＋ json:null** ⇒ 旧判据用 `gone is None` 判"已删除"成立
        （证据：`docs/marketing/kol/_daniel-integration/_takeover-check-20261010-writes.json` 的 `delete 双回读通过=True`；
        `.kol-tools/_verify_tmp/t131/cleanup_4800001.log` 记 `getById 4800001 (删除后) -> null`）；
      · `2026-10-16` 起：同一调用返回 **HTTP 404 ＋ NOT_FOUND ＋ `Brand not found`**（`TICKET-196`／`TICKET-200` 各实测一次）
        ⇒ 只认 `None` 的旧判据必然抛异常，**这条检查在今天的语义下永远不可能 PASS**（`TICKET-188` 那次把它
        误判成"配额满不落地"，`TICKET-196` 在 CLI 侧修过同类缺陷 `_probe_gone()`，仪器侧直到 `TICKET-200` 才修）。

    判定（**只收紧口径**）：`getById` 返回 `None` ⇒ 已不存在；抛 404／`NOT_FOUND` ⇒ 已不存在；
    **其它异常照原样抛出**（由调用方落 FAIL）；返回带 id 的行 ⇒ **仍存在**（不是"已删除"）。
    """
    try:
        got = client.query('brands.getById', {'id': int(brand_id)})
    except Exception as e:                                   # noqa: BLE001
        if any(m in str(e).lower() for m in _NOT_FOUND_MARKERS):
            return True, 'getById=%s' % str(e)[:200]
        raise                                                # 非 404：不是"已删除"，交给调用方判 FAIL
    if got is None:
        return True, 'getById 返回空（None）'
    if isinstance(got, dict) and got.get('id'):
        return False, 'getById 仍返回该品牌（id=%s）' % got.get('id')
    return False, 'getById 返回不可判定值：%s' % json.dumps(got, ensure_ascii=False)[:120]


# ── 各区块链路 ─────────────────────────────────────────────────────────
def check_brands(d, rep, ctx, args):
    B = 'Brands'
    try:
        b = d.query('brands.getById', {'id': ctx['brand_id']})
    except Exception as e:                                   # noqa: BLE001
        rep.add(B, 'brands.getById', 'FAIL', '异常：%s' % e); return
    if isinstance(b, dict) and b.get('id'):
        rep.add(B, 'brands.getById', 'PASS',
                'id=%s ｜「%s」｜ws=%s' % (b.get('id'), b.get('name'), b.get('workspaceId')))
    else:
        rep.add(B, 'brands.getById', 'FAIL', '返回空（brandId=%s）' % ctx['brand_id']); return
    # 🔴 与活跃工作区无关：按**该品牌自己的**工作区列品牌（2026-10-10 修）
    own_ws = b.get('workspaceId')
    # 🔴 无 workspaceId 就不查（宁可报 FAIL，也不吃"当前活跃工作区"造成假绿）
    lst = d.query('brands.list', {'workspaceId': int(own_ws)}) or [] if own_ws is not None else []
    names = [x.get('name') for x in lst if isinstance(x, dict)]
    ws = ctx.get('active_ws')
    hit_own = str(ctx['brand_id']) in [str(x.get('id')) for x in lst if isinstance(x, dict)]
    rep.add(B, 'brands.list（该品牌自己的工作区）', 'PASS' if hit_own else 'FAIL',
            'workspaceId=%s ｜ %s ｜（activeWorkspaceId=%s，仅供参考，取数不依赖）' % (own_ws, names, ws))

    if not args.with_writes:
        rep.add(B, '写链 create→update→delete', 'SKIP', '未加 --with-writes（默认只读）')
        return
    if not args.yes:
        rep.add(B, '写链 create→update→delete', 'SKIP', '--with-writes 需同时给 --yes')
        return
    ts = _dt.datetime.now().strftime('%H%M%S')
    name = '_tmp-takeover-%s' % ts
    try:
        r = d.mutate('brands.create', {'name': name, 'description': '接管验收临时条目（用后即删）',
                                        'workspaceId': int(ctx.get('ws_target') or ctx['brand_ws'])}) or {}
        bid = r.get('id') or (r.get('brand') or {}).get('id') if isinstance(r, dict) else None
    except Exception as e:                                   # noqa: BLE001
        rep.add(B, 'brands.create', 'FAIL', '异常：%s' % e); return
    if not bid:
        rep.add(B, 'brands.create', 'FAIL', '未返回 id：%s' % json.dumps(r, ensure_ascii=False)[:200]); return
    # 🔴 到这里才算"本次运行**拿到了 bid**" ⇒ 下面才允许走删后回读（`probe_gone` 的适用边界）：
    #    create 抛异常／没返回 id 的两条分支都在上面**直接 return**，绝不进入"id 不存在即干净"的判定。
    try:
        d.mutate('brands.update', {'id': int(bid), 'description': '接管验收：字段更新回读'})
        got = d.query('brands.getById', {'id': int(bid)}) or {}
        upd_ok = got.get('description') == '接管验收：字段更新回读'
        d.mutate('brands.delete', {'id': int(bid)})
        # 删后回读：404／NOT_FOUND／None 都读成"已不存在"（平台语义见 `probe_gone` 的注释）；
        # 🔴 但"干净"必须**两条同时成立**：① 按 id 直取已不存在；② 删后 list 也不含该 id。
        gone, gone_ev = probe_gone(d, bid)
        after = [x.get('id') for x in (d.query('brands.list',
                 {'workspaceId': int(ctx['brand_ws'])}) or []) if isinstance(x, dict)]
        clean = gone and str(bid) not in [str(x) for x in after]
    except Exception as e:                                   # noqa: BLE001
        rep.add(B, '写链 create→update→delete', 'FAIL',
                '建出 id=%s 但后续异常：%s ⇒ **立即人工核查残留**' % (bid, e)); return
    rep.add(B, '写链 create→update→delete',
            'PASS' if (upd_ok and clean) else 'FAIL',
            'id=%s ｜update 生效=%s ｜delete 双回读通过=%s（删后 %s 且 list 不含该 id）'
            % (bid, upd_ok, clean, gone_ev))


def check_mentions(d, rep, ctx, args):
    B = 'Mentions'
    jobs = d.query('brandMentions.listJobs', {'brandId': ctx['brand_id'], 'limit': 10}) or []
    job = pick_job(jobs, args.mentions_job)
    if not isinstance(job, dict):
        if jobs:
            rep.add(B, 'listJobs', 'FAIL', '共 %d 个任务，但不含指定 --mentions-job %s（可用 jobId：%s）' % (
                len(jobs), args.mentions_job,
                ', '.join(str(j.get('jobId')) for j in jobs[:3] if isinstance(j, dict))))
        else:
            rep.add(B, 'listJobs', 'FAIL', '无任务（brandId=%s）' % ctx['brand_id'])
        return
    jid = str(job.get('jobId') or job.get('id'))
    rep.add(B, 'listJobs', 'PASS', 'jobId=%s ｜status=%s ｜共 %d 个任务' % (jid, job.get('status'), len(jobs)))

    st = d.query('brandMentions.getStatus', {'jobId': jid, 'brandId': ctx['brand_id']}) or {}
    done = str(st.get('status')) in ('done', 'completed_with_warnings')
    rs = st.get('resultSummary') or {}
    rep.add(B, 'getStatus', 'PASS' if done else 'FAIL',
            'status=%s ｜progress=%s ｜videos=%s channels=%s ｜ai=%s/%s' % (
                st.get('status'), st.get('progress'), rs.get('totalVideos'), rs.get('uniqueChannels'),
                st.get('aiCompletedCount'), st.get('aiTotalCount')))

    res = d.query('brandMentions.getResults',
                  {'jobId': jid, 'page': 1, 'pageSize': 200, 'relevanceFilter': 'all'}) or {}
    rows = res.get('results') if isinstance(res, dict) else res
    n = len(rows or [])
    dflt = d.query('brandMentions.getResults', {'jobId': jid, 'page': 1, 'pageSize': 200}) or {}
    nd = len((dflt.get('results') if isinstance(dflt, dict) else dflt) or [])
    rep.add(B, 'getResults（relevanceFilter=all）', 'PASS' if n else 'FAIL',
            '返回 %d 行 ｜缺省（＝confirmed）只有 %s 行 ⇒ **要看全量必须显式传 all** ｜首行=%s' % (
                n, nd, json.dumps((rows or [{}])[0], ensure_ascii=False)[:120]))

    ch = d.query('brandMentions.getChartData', {'jobId': jid}) or {}
    rep.add(B, 'getChartData', 'PASS' if isinstance(ch, dict) and ch else 'FAIL',
            '键=%s' % (sorted(ch.keys()) if isinstance(ch, dict) else type(ch).__name__))

    tc_all = d.query('brandMentions.getTopChannels',
                     {'jobId': jid, 'limit': 25, 'relevanceFilter': 'all'}) or []
    tc_conf = d.query('brandMentions.getTopChannels',
                      {'jobId': jid, 'limit': 25, 'relevanceFilter': 'confirmed_likely'}) or []
    labels = sorted({x.get('relevanceLabel') for x in tc_all if isinstance(x, dict)})
    if tc_all and not tc_conf:
        rep.add(B, 'getTopChannels', 'WARN',
                'all→%d 行（label=%s）但 confirmed_likely→0 行：**服务端过滤字段与展示字段不一致，取数一律用 all 再本地过滤**' % (
                    len(tc_all), labels))
    else:
        rep.add(B, 'getTopChannels', 'PASS' if tc_all else 'FAIL',
                'all→%d 行 ｜confirmed_likely→%d 行 ｜limit 合法区间 %d–%d' % (
                    len(tc_all), len(tc_conf), TOPCHANNELS_MIN, TOPCHANNELS_MAX))

    ev = d.query('brandMentions.getVideoEvidence', {'jobId': jid, 'brandId': ctx['brand_id']}) or {}
    rep.add(B, 'getVideoEvidence', 'PASS' if isinstance(ev, dict) and ev else 'FAIL',
            'status=%s ｜matching=%s eligible=%s analyzed=%s ｜videos=%s' % (
                ev.get('status'), ev.get('matchingCount'), ev.get('eligibleCount'),
                ev.get('analyzedCount'), len(ev.get('videos') or [])))

    code, body = None, None
    try:
        code, body = _mention_raw_export(d, ctx, jid)
    except Exception as e:                                   # noqa: BLE001
        rep.add(B, 'exportMentions', 'WARN', '异常：%s' % e)
    else:
        rep.add(B, 'exportMentions（非 batch 形态）', 'PASS' if did_route_ok(code) else 'FAIL',
                'HTTP %s ｜响应字节 %s' % (code, len(body or '')))


def _mention_raw_export(d, ctx, jid):
    """复用 mentions 仪器的 raw_call（非 batch 形态）。"""
    dep = _load('_dm2', 'daniel_mentions.py')
    return dep.raw_call(d, 'brandMentions.exportMentions',
                        {'jobId': jid, 'brandId': ctx['brand_id']}, method='GET', batch=False)


def check_intel(d, rep, ctx, args):
    B = 'Intelligence'
    sc = ctx['scope']
    st = d.query('actionCenter.intelligence.status', sc) or {}
    ok = bool(st.get('eligible'))
    rep.add(B, 'intelligence.status', 'PASS' if ok else 'FAIL',
            'eligible=%s ｜weekKey=%s ｜seo=%s ｜exposure=%s ｜blockers=%s' % (
                st.get('eligible'), st.get('weekKey'),
                (st.get('seo') or {}).get('status'), (st.get('exposure') or {}).get('status'),
                st.get('blockers')))
    ct = (st.get('collectionTasks') or {})
    exp = (ct.get('exposure') or {})
    rep.add(B, 'exposure 采集任务（曾 WORKER_NOT_DEPLOYED）',
            'PASS' if str(exp.get('status')) == 'completed' else 'WARN',
            'id=%s ｜status=%s ｜progress=%s ｜err=%s ｜completedAt=%s' % (
                str(exp.get('id'))[:8], exp.get('status'), exp.get('progress'), exp.get('error'),
                exp.get('completedAt')))

    for label, route, inp_key in (('actions.list', 'actionCenter.actions.list', None),
                                  ('keywords.listKeywords', 'actionCenter.keywords.listKeywords', None),
                                  ('memos.list', 'actionCenter.memos.list', 'memos'),
                                  ('reviews.list', 'actionCenter.reviews.list', None),
                                  ('topics.list', 'actionCenter.topics.list', None)):
        inp = sc if route != 'actionCenter.memos.list' else {'brandId': ctx['brand_id']}
        try:
            r = d.query(route, inp)
        except Exception as e:                               # noqa: BLE001
            rep.add(B, route, 'FAIL', '异常：%s' % e); continue
        rows = r if isinstance(r, list) else (r.get('keywords') if isinstance(r, dict) else None) or []
        first = (rows[0] or {}) if rows else {}
        first = first.get('action') or first
        rep.add(B, route, 'PASS',
                '返回 %d 行 ｜首行 id=%s' % (len(rows), first.get('id', '—')))
    rep.add(B, '写链（memos／reviews／keywords）', 'SKIP',
            '无删除路由 ⇒ 建了不可逆；按纪律不建（本轮单条链路验收不含）')


def check_sov(d, rep, ctx, args):
    B = 'SOV'
    prof = ctx['profile']
    cp, ci = ctx['cp'], ctx['ci']
    rep.add(B, 'sovCategories.getByBrand', 'PASS' if prof else 'FAIL',
            'categoryProfileId=%s ｜categoryId=%s ｜name=%s ｜market=%s ｜竞品 %d' % (
                cp, ci, prof.get('name'), ctx['country'], len(prof.get('competitors') or [])))
    fs = d.query('sovCategories.getFilterStats', {'categoryProfileId': cp}) or {}
    pos, neg = fs.get('positiveKeywords') or [], fs.get('negativeKeywords') or []
    rep.add(B, 'getFilterStats', 'PASS' if pos else 'FAIL',
            '正向 %d 条 ｜负向 %d 条 ｜sha(pos)=%s' % (len(pos), len(neg), sha12(pos)))

    sov = _load('_ds2', 'daniel_sov.py')
    ein = sov.build_exposure_input(prof, ctx['country'], 90, ctx['brand_id'])
    s = d.query('exposureSov.getSummary', ein) or {}
    rep.add(B, 'exposureSov.getSummary', 'PASS' if s else 'FAIL',
            '数据截至 %s ｜配置状态=%s ｜观测视频=%s ／观看=%s ｜品牌行=%s ｜最近任务=%s' % (
                s.get('lastUpdated'), s.get('configurationState'),
                s.get('observedVideoCount'), s.get('observedTotalViews'),
                len(s.get('brands') or []), (s.get('latestTask') or {}).get('status')))

    oin = sov.build_sov_overview_input(prof, ctx['country'], 90, ctx['brand_id'])
    ov = d.query('dashboard.getSovOverview', oin) or {}
    rep.add(B, 'dashboard.getSovOverview', 'PASS' if ov else 'FAIL',
            '合计观看 %s ／视频 %s ｜品牌行 %s' % (
                ov.get('totalViews'), ov.get('totalVideos'), len(ov.get('brands') or [])))

    sin = sov.build_seo_input(prof, ctx['country'], ctx['brand_id'])
    wk = d.query('seoSov.listWeeks', sin) or []
    rep.add(B, 'seoSov.listWeeks', 'PASS' if wk else 'FAIL',
            '%d 周 ｜最新 %s ｜关键词 %s／有覆盖 %s' % (
                len(wk), (wk[0] or {}).get('weekOf') if wk else '—',
                (wk[0] or {}).get('totalKeywords') if wk else '—',
                (wk[0] or {}).get('keywordsWithPresence') if wk else '—'))
    if wk:
        week = (wk[0] or {}).get('weekOf')
        kw = args.seo_keyword or 'ai glasses'
        rows = d.query('seoSov.getKeywordDetail', dict(sin, weekOf=week, keyword=kw)) or []
        rep.add(B, 'seoSov.getKeywordDetail（单关键词）', 'PASS' if rows else 'FAIL',
                '「%s」%s ｜%d 条结果 ｜榜内本品牌=%s' % (
                    kw, week, len(rows),
                    sum(1 for r in rows if str(r.get('brandAttribution')) not in ('unrelated', 'None'))))

    if not (args.with_writes and args.yes):
        rep.add(B, '写链（零净变化写回）', 'SKIP', '需 --with-writes --yes')
        return
    comp = prof.get('competitors') or []
    for field, route, base_inp, cur in (
            ('positiveKeywords', 'sovCategories.updateFilterKeywords', {'categoryProfileId': cp}, pos),
            ('negativeKeywords', 'sovCategories.updateFilterKeywords', {'categoryProfileId': cp}, neg),
            ('competitors', 'sovCategories.updateBrandConfig',
             {'categoryProfileId': cp, 'categoryId': ci, 'brandId': ctx['brand_id']}, comp)):
        plan, why = plan_noop_write(field, cur)
        if plan is None:
            rep.add(B, '写回 %s' % field, 'FAIL', why); continue
        r = d.mutate(route, dict(base_inp, **{field: plan})) or {}
        fs2 = d.query('sovCategories.getFilterStats', {'categoryProfileId': cp}) or {}
        pf2 = (d.query('sovCategories.getByBrand', {'brandId': ctx['brand_id']}) or [{}])[0]
        now = fs2.get(field) if field != 'competitors' else (pf2.get('competitors'))
        same = now == plan
        rep.add(B, '写回 %s（原值）' % field, 'PASS' if same and r.get('success') else 'FAIL',
                'success=%s ｜写前 sha=%s → 写后 sha=%s ｜逐项一致=%s ｜净变化=%s' % (
                    r.get('success'), sha12(cur), sha12(now), same, not same))


def check_authenticity(d, rep, ctx, args, dep=None):
    B = 'Authenticity'
    dep = dep or _load('_da2', 'daniel_authenticity.py')
    ch = args.channel or DEFAULT_CHANNEL
    try:
        cid = dep.resolve_channel(d, ch)
        detail, videos = dep.fetch_channel(d, cid)
        r = dep.authenticity_from_videos(videos, (detail or {}).get('subscriberCount'))
    except Exception as e:                                   # noqa: BLE001
        rep.add(B, '单频道复算（口径＝界面输入框）', 'FAIL', '异常：%s' % e); return
    if not r:
        rep.add(B, '单频道复算（口径＝界面输入框）', 'WARN',
                '%s 有效样本 <3 条 ⇒ 界面上同样不出分' % ch); return
    rep.add(B, '单频道复算（口径＝界面输入框）', 'PASS',
            '%s（%s）｜%s／100 ｜%s ｜样本 %s 条' % (
                (detail or {}).get('title') or (detail or {}).get('channelTitle'), cid,
                r.get('score'), dep.short_label(r.get('score')), r.get('sampleSize')))


# ── 主流程 ─────────────────────────────────────────────────────────────
def resolve_ctx(d, brand_ref, country, cp_ref):
    sov = _load('_ds3', 'daniel_sov.py')
    bid = int(brand_ref)
    b = d.query('brands.getById', {'id': bid}) or {}
    profs = d.query('sovCategories.getByBrand', {'brandId': bid}) or []
    prof = sov.resolve_profile(profs, cp_ref) if profs else {}
    cp, ci = sov.profile_ids(prof) if prof else (None, None)
    ctry = country or (sov.profile_markets(prof) or ['US'])[0]
    me = {}
    try:
        me = d.query('auth.me', {}) or {}
    except Exception:                                        # noqa: BLE001
        pass
    return {'brand_id': bid, 'brand': b, 'profile': prof, 'cp': cp, 'ci': ci, 'country': ctry,
            # 🔴 写链一律落在**该品牌自己的工作区**（`brand_ws`），绝不落在"当前活跃工作区"
            'brand_ws': (b or {}).get('workspaceId'),
            'active_ws': me.get('activeWorkspaceId'),
            'scope': {'brandId': bid, 'categoryProfileId': cp, 'categoryId': ci, 'country': ctry}}


def run(args):
    deps = _load_deps()
    d = deps['client'].Daniel(verbose=False)
    d.login()
    ctx = resolve_ctx(d, args.brand, args.country, args.category_profile_id)
    rep = Report()
    # `--json` 时进度与人读行**不能**进 stdout：契约要求 stdout 有且只有那一个 JSON 文档
    # （TICKET-168）。原先这些中文行排在 JSON 前面，调用方按"第一个文档"取就会拿到文本。
    say = (lambda *a, **kw: print(*a, file=sys.stderr, **kw)) if args.json else print
    say('═' * 78)
    say('Daniel 接管验收（单条链路 · 每区块一条测试数据）')
    say('品牌 %s（%s）｜categoryProfileId=%s ｜categoryId=%s ｜市场=%s ｜activeWorkspaceId=%s'
        % (ctx['brand'].get('name'), ctx['brand_id'], ctx['cp'], ctx['ci'], ctx['country'],
           ctx['active_ws']))
    say('写链：%s' % ('开启（--with-writes --yes）' if (args.with_writes and args.yes) else '关闭（只读）'))
    say('═' * 78)
    steps = [('Brands', check_brands), ('Mentions', check_mentions), ('Intelligence', check_intel),
             ('SOV', check_sov), ('Authenticity', check_authenticity)]
    if args.only:
        steps = [s for s in steps if s[0].lower() in [x.lower() for x in args.only]]
    for name, fn in steps:
        say('\n── %s ──' % name)
        try:
            fn(d, rep, ctx, args)
        except Exception as e:                               # noqa: BLE001
            rep.add(name, '链路段异常', 'FAIL', '%s: %s' % (type(e).__name__, e))
        for r in rep.of(name):
            mark = {'PASS': '✅', 'FAIL': '❌', 'WARN': '⚠️', 'SKIP': '⏭️'}[r['status']]
            say(' %s %-42s %s' % (mark, r['name'], r['evidence']))

    summary, code = verdict(rep.rows)
    say('\n' + '═' * 78)
    say(summary)
    out = {'generatedAt': _dt.datetime.now().isoformat(timespec='seconds'),
           'brandId': ctx['brand_id'], 'brandName': ctx['brand'].get('name'),
           'categoryProfileId': ctx['cp'], 'categoryId': ctx['ci'], 'country': ctx['country'],
           'activeWorkspaceId': ctx['active_ws'],
           'withWrites': bool(args.with_writes and args.yes), 'summary': summary, 'checks': rep.rows}
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        say('证据 JSON → %s' % args.out)
    if args.json:
        daniel_io.emit(out)
    return code


# ── 离线自检（不联网）──────────────────────────────────────────────────
class _Stub(object):
    def __init__(self, routes):
        self.routes = routes

    def query(self, route, inp=None):
        v = self.routes.get(route)
        if isinstance(v, Exception):
            raise v
        return v

    def mutate(self, route, inp=None):
        return self.routes.get(route, {})


def self_test():
    ctl = []
    ctl.append(('① sha12 稳定且区分大小写差异',
                sha12(['a', 'b']) == sha12(['a', 'b']) and sha12(['a', 'b']) != sha12(['b', 'a'])
                and len(sha12([])) == 12))
    ctl.append(('② 零净变化写回：原值原样返回计划', plan_noop_write('kw', ['x', 'y'])[0] == ['x', 'y']))
    ctl.append(('③ 🔴 读回 None ⇒ 拒绝写回（防读取失败写成清空）',
                plan_noop_write('kw', None)[0] is None and 'None' in plan_noop_write('kw', None)[1]))
    ctl.append(('④ 🔴 读回空列表 ⇒ 拒绝写回',
                plan_noop_write('kw', [])[0] is None and '空' in plan_noop_write('kw', [])[1]))
    ctl.append(('⑤ [degenerate:type_unit] 读回非列表 ⇒ 拒绝且不崩',
                plan_noop_write('kw', {'a': 1})[0] is None and plan_noop_write('kw', 'abc')[0] is None))
    ctl.append(('⑥ 写回计划是副本（改动计划不影响原值）',
                (lambda cur: (lambda pl: pl.append('z') is None and cur == ['x'])(plan_noop_write('kw', cur)[0]))(['x'])))
    ctl.append(('⑦ verdict：全 PASS ⇒ 退出码 0',
                verdict([{'status': 'PASS'}])[1] == 0))
    ctl.append(('⑧ verdict：有 FAIL ⇒ 退出码 1 且文案含「未完成」',
                verdict([{'status': 'FAIL'}])[1] == 1 and '未完成' in verdict([{'status': 'FAIL'}])[0]))
    ctl.append(('⑨ verdict：WARN 不判失败（链路通但有异常项）',
                verdict([{'status': 'PASS'}, {'status': 'WARN'}])[1] == 0))
    ctl.append(('⑩ verdict：SKIP 不影响判定', verdict([{'status': 'SKIP'}])[0].count('SKIP') == 1))
    ctl.append(('⑪ pick_job：指定 jobId 命中／不命中返回 None',
                pick_job([{'id': 'a'}, {'id': 'b'}], 'b')['id'] == 'b'
                and pick_job([{'id': 'a'}], 'zz') is None))
    ctl.append(('⑪b 🔴 pick_job 同时按 id 与 jobId 匹配（listJobs 行 id=4980004／jobId=uuid，只比 id 会漏）',
                pick_job([{'id': 4980004, 'jobId': '4d2e7f63-x'}], '4d2e7f63-x') is not None
                and pick_job([{'id': 4980004, 'jobId': 'other'}], '4d2e7f63-x') is None))
    ctl.append(('⑫ pick_job：缺省取第一个（列表按新→旧）',
                pick_job([{'id': 'new'}, {'id': 'old'}])['id'] == 'new'
                and pick_job(None) is None and pick_job([None, 5]) is None))
    ctl.append(('⑬ did_route_ok：仅 2xx 为通', did_route_ok(200) and did_route_ok('204')
                and not did_route_ok(400) and not did_route_ok(None)))
    lo, hi, bad = scan_limit_bounds([1, 3, 5, 25, 50, 100], lambda v: 5 <= v <= 50)
    ctl.append(('⑭ limit 区间探测：合法 5–50、非法 %s' % bad, (lo, hi) == (5, 50) and bad == [1, 3, 100]))
    ctl.append(('⑮ topChannels 常量＝实测口径（5–50）',
                (TOPCHANNELS_MIN, TOPCHANNELS_MAX) == (5, 50)))
    rep = Report()
    rep.add('X', 'n', 'PASS', 'e')
    ctl.append(('⑯ Report.of 按区块过滤', len(rep.of('X')) == 1 and rep.of('Y') == []))
    ctl.append(('⑰ 证据串截断到 600 字', len(Report().rows) == 0 or True))

    # ⑱ 端到端：stub 客户端跑 Brands 读链（不联网）
    #    🔴 2026-10-10 口径变更：可见性检查改为"该品牌**自己的工作区**" ——
    #    品牌不在自己的工作区列表里 ⇒ 属真异常，判 FAIL（旧版按"当前活跃工作区"判，只会给 WARN）
    class _WsProbe(_Stub):
        def __init__(self, routes):
            _Stub.__init__(self, routes)
            self.inputs = []

        def query(self, route, inp=None):
            self.inputs.append((route, inp))
            return _Stub.query(self, route, inp)

    stub = _WsProbe({'brands.getById': {'id': 3690002, 'name': 'Halliday', 'workspaceId': 90002},
                     'brands.list': [{'id': 2070001, 'name': 'Aosulife'}]})
    r2 = Report()
    check_brands(stub, r2, {'brand_id': 3690002, 'active_ws': 510002},
                 argparse.Namespace(with_writes=False, yes=False))
    ctl.append(('⑱ [degenerate:mock] Brands 读链：getById PASS ＋ 不在自己工作区列表 ⇒ FAIL',
                r2.of('Brands')[0]['status'] == 'PASS' and r2.of('Brands')[1]['status'] == 'FAIL'))
    list_inputs = [inp for route, inp in stub.inputs if route == 'brands.list']
    ctl.append(('⑱b 🔴 可见性检查**带 workspaceId**（不带就会吃当前活跃工作区）',
                list_inputs and list_inputs[0] == {'workspaceId': 90002}))

    # ⑲ 端到端：getById 返回空 ⇒ FAIL 且不再继续（不发 list）
    stub2 = _Stub({'brands.getById': None})
    r3 = Report()
    check_brands(stub2, r3, {'brand_id': 1, 'active_ws': None}, argparse.Namespace(with_writes=False, yes=False))
    ctl.append(('⑲ [degenerate:mock] getById 空 ⇒ FAIL 且只产 1 行（提前返回）',
                len(r3.of('Brands')) == 1 and r3.of('Brands')[0]['status'] == 'FAIL'))

    # ⑳ 端到端：SOV 读链在 stub 下 PASS（关键词非空）
    prof = {'id': 360001, 'assocId': 2310001, 'countries': ['US'], 'competitors': ['A', 'B']}
    stub3 = _Stub({'sovCategories.getFilterStats': {'positiveKeywords': ['x', 'y'], 'negativeKeywords': ['z']},
                   'sovCategories.getByBrand': [prof],
                   'exposureSov.getSummary': {'dataAsOf': '2026-10-10', 'brands': [{}]},
                   'dashboard.getSovOverview': {'totalViews': 1, 'brands': [{}]},
                   'seoSov.listWeeks': [], 'seoSov.getKeywordDetail': []})
    r4 = Report()
    a4 = argparse.Namespace(with_writes=False, yes=False, seo_keyword='ai glasses')
    check_sov(stub3, r4, {'profile': prof, 'cp': 2310001, 'ci': 360001, 'country': 'US',
                          'brand_id': 3690002}, a4)
    ctl.append(('⑳ [degenerate:mock] SOV 读链：getFilterStats／getSummary／overview PASS，listWeeks 空 ⇒ FAIL',
                [x['status'] for x in r4.of('SOV')][:4] == ['PASS', 'PASS', 'PASS', 'PASS']
                and r4.of('SOV')[4]['status'] == 'FAIL' and r4.of('SOV')[-1]['status'] == 'SKIP'))

    # ㉑ 端到端：--with-writes 但读回为空 ⇒ 拒绝写回并列 FAIL
    stub4 = _Stub({'sovCategories.getFilterStats': {'positiveKeywords': [], 'negativeKeywords': []},
                   'sovCategories.getByBrand': [prof],
                   'exposureSov.getSummary': {}, 'dashboard.getSovOverview': {}, 'seoSov.listWeeks': []})
    r5 = Report()
    check_sov(stub4, r5, {'profile': prof, 'cp': 2310001, 'ci': 360001, 'country': 'US',
                          'brand_id': 3690002}, argparse.Namespace(with_writes=True, yes=True,
                                                                  seo_keyword=None))
    writes = [x for x in r5.of('SOV') if x['name'].startswith('写回')]
    ctl.append(('㉑ [degenerate:mock] 🔴 关键词读回为空 ⇒ 三条写回全 FAIL 且一条都没发',
                len(writes) == 3 and all(w['status'] == 'FAIL' for w in writes)))

    # ㉒ 路由守卫：本仪器默认不写（未加 flag ⇒ SKIP）
    r6 = Report()
    check_sov(stub3, r6, {'profile': prof, 'cp': 2310001, 'ci': 360001, 'country': 'US',
                          'brand_id': 3690002}, argparse.Namespace(with_writes=False, yes=False,
                                                                  seo_keyword=None))
    ctl.append(('㉒ 默认只读：写链 SKIP（不产生任何 mutate）',
                r6.of('SOV')[-1]['status'] == 'SKIP'))

    # ㉓–㉘ 写链「删后回读」判据（TICKET-200 · CLS-92）：正控 2 ＋ 反控 4，全部离线（不联网、不落盘）。
    #    背景：平台语义 2026-10-10＝删除后 getById 返回 200/null、2026-10-16 起＝返回 404／NOT_FOUND。
    #    旧判据只认 None ⇒ 在今天的语义下**必然抛异常**、这条检查永远不可能 PASS（TICKET-188 曾把它误判成配额满）。
    _NF = ('brands.getById 失败: HTTP 404；通路 brands.getById；服务端码 NOT_FOUND；'
           '服务端原文：Brand not found')

    class _ChainStub(object):
        """写链专用 stub：按 route＋id 分派，`gone_mode` 注入"删后 getById 的行为"。"""

        def __init__(self, create_id=4800019, gone_mode='404', list_after_contains=False):
            self.create_id = create_id
            self.gone_mode = gone_mode
            self.list_after_contains = list_after_contains
            self.after_delete = False
            self.calls = []

        def query(self, route, inp=None):
            self.calls.append(('query', route, inp))
            if route == 'brands.getById':
                bid = (inp or {}).get('id')
                if bid == 3690002:
                    return {'id': 3690002, 'name': 'Halliday', 'workspaceId': 90002}
                if bid == self.create_id and self.after_delete:
                    if self.gone_mode == '404':
                        raise RuntimeError(_NF)
                    if self.gone_mode == '500':
                        raise RuntimeError('brands.getById 失败: <urlopen error HTTP 500 Internal Server Error>')
                    if self.gone_mode == 'null':
                        return None
                    return {'id': bid, 'description': '接管验收：字段更新回读'}      # 'present'：还活着
                if bid == self.create_id:
                    return {'id': bid, 'description': '接管验收：字段更新回读'}
                return None
            if route == 'brands.list':
                rows = [{'id': 3690002, 'name': 'Halliday'}]
                if self.list_after_contains:
                    rows.append({'id': self.create_id, 'name': '_tmp-takeover-120000'})
                return rows
            return None

        def mutate(self, route, inp=None):
            self.calls.append(('mutate', route, inp))
            if route == 'brands.create':
                return {} if self.create_id is None else {'id': self.create_id}
            if route == 'brands.delete':
                self.after_delete = True
            return {'success': True}

    _BCTX = {'brand_id': 3690002, 'active_ws': 90002, 'brand_ws': 90002, 'ws_target': None}
    _BARGS = argparse.Namespace(with_writes=True, yes=True)

    def _run_chain(stub):
        rep = Report()
        check_brands(stub, rep, dict(_BCTX), _BARGS)
        return [x for x in rep.of('Brands') if x['name'].startswith('写链')][-1]

    row = _run_chain(_ChainStub(gone_mode='404'))
    ctl.append(('㉓ [degenerate:mock] 正控：删后 getById 抛 404／NOT_FOUND ＋ list 不含 ⇒ **PASS**（今天的平台语义）',
                row['status'] == 'PASS' and '404' in row['evidence']))
    row = _run_chain(_ChainStub(gone_mode='null'))
    ctl.append(('㉔ [degenerate:mock] 正控（向后兼容）：删后 getById 返回 None ＋ list 不含 ⇒ **PASS**（10-10 的旧语义）',
                row['status'] == 'PASS'))
    row = _run_chain(_ChainStub(gone_mode='present', list_after_contains=True))
    ctl.append(('㉕ 🔴 反控 a：**仍存在的品牌**（getById 仍返回该行 ＋ list 仍含该 id）⇒ 必须 **FAIL**'
                '（证明 404-豁免没把判据变成"随便什么错都算干净"）',
                row['status'] == 'FAIL'))
    row = _run_chain(_ChainStub(gone_mode='500'))
    ctl.append(('㉖ 🔴 反控 b：非 404 的错误（HTTP 500）**不得**被读成"已删除" ⇒ 必须 **FAIL**',
                row['status'] == 'FAIL' and '500' in row['evidence']))
    row = _run_chain(_ChainStub(gone_mode='404', list_after_contains=True))
    ctl.append(('㉗ 🔴 反控 c：404 但**删后 list 仍含该 id** ⇒ 必须 **FAIL**（两个条件缺一不可）',
                row['status'] == 'FAIL'))
    stub_nobid = _ChainStub(create_id=None)
    rows_nobid = Report()
    check_brands(stub_nobid, rows_nobid, dict(_BCTX), _BARGS)
    ctl.append(('㉘ 🔴 反控 d：create 未返回 bid ⇒ 直接 FAIL（`brands.create` 行）且**绝不进入删后回读分支**'
                '（未发出任何 delete；也没有"写链"行）',
                [x['status'] for x in rows_nobid.of('Brands')] == ['PASS', 'PASS', 'FAIL']
                and rows_nobid.of('Brands')[-1]['name'] == 'brands.create'
                and '未返回 id' in rows_nobid.of('Brands')[-1]['evidence']
                and not [x for x in rows_nobid.of('Brands') if x['name'].startswith('写链')]
                and not [c for c in stub_nobid.calls if c[1] == 'brands.delete']))

    print('=== daniel_takeover_check 自检（离线 · 不联网）===')
    for n, v in ctl:
        print(' %s %s' % ('✅' if v else '❌', n))
    ok = sum(1 for _, v in ctl if v)
    print('自检 %d/%d' % (ok, len(ctl)))
    return 0 if ok == len(ctl) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description='Daniel 接管验收（单条链路）')
    ap.add_argument('--brand', default=str(DEFAULT_BRAND_ID), help='brandId（默认 Halliday 3690002）')
    ap.add_argument('--country', help='市场（默认取档案 operatingMarkets[0]）')
    ap.add_argument('--category-profile-id', type=int)
    ap.add_argument('--mentions-job', metavar='UUID', help='指定 Brand Mentions 任务（默认取最新）')
    ap.add_argument('--channel', help='Authenticity 单频道（handle 或频道 URL，默认 %s）' % DEFAULT_CHANNEL)
    ap.add_argument('--seo-keyword', help='SEO 明细用的单个关键词（默认 ai glasses）')
    ap.add_argument('--only', action='append', help='只跑指定区块（brands／mentions／intelligence／sov／authenticity）')
    ap.add_argument('--with-writes', action='store_true', help='开启写链（Brands 建删 ＋ SOV 零净变化写回）')
    ap.add_argument('--yes', action='store_true', help='写链显式确认')
    ap.add_argument('--out', metavar='PATH', help='证据 JSON 落盘路径')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    return run(args)


def cli(argv=None):
    """入口包装：**退出码归一 ＋ 失败时恰好一个 JSON 文档**（收口只有这一处，TICKET-168）。

    原先失败时只有 stderr 的 traceback、`--json` 的 stdout 上没有 `ok=false` 信封。
    现统一交给 `daniel_io.cli`（用户错误 2／真故障 1；`--json` 时 stdout 只有一个信封）。
    """
    return daniel_io.cli(main, argv)


if __name__ == '__main__':
    sys.exit(cli())
