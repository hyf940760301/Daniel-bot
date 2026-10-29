#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daniel_ct.py —— Daniel「Creator Tracker（红人追踪）」读／写直连工具。

**本轮范围**：**Campaign** 的列／建／改（Deals、Videos 留待下一步，路由已定位见 Skill §16）。

通路（实证 · 2026-09-29）：tRPC 同源 `/api/trpc`，命名空间 **`ct.*`**（不是 `campaigns.*` —— 后者是另一处
"内容 Campaign"模块，两者别混）。取证底稿：`docs/marketing/kol/_build/creator-tracker-campaign-create-schema.md`。

🔴 建 campaign 的入参与界面校验（bundle 调用点逐键读出，`CreatorTracker.tsx:294` 起 modal）：
    ct.campaigns.create({ brandId, title, brandName, brandHandle, brandYoutubeChannel,
                          startDate, endDate, isEvergreen, brief })
  · **必填**：title（名称）／brandYoutubeChannel（频道）／startDate（开始日期）
  · **二选一必填**：endDate 或 isEvergreen=true（勾 Evergreen 时 **endDate 必须不传**）
  · brief 选填；brandName／brandHandle 由品牌档案自动带（无需人填）
  · 频道建议给 `UC…` ID：`ct.campaigns.resolveChannel` 实测对 `@handle`／URL 返回 success:false
    （界面仍会原样提交，由服务端创建时再解析，可能带回 syncError）

用法：
  python3 .kol-tools/daniel_ct.py --campaigns --brand Halliday
  python3 .kol-tools/daniel_ct.py --create-campaign --brand Halliday --title "halliday summer test" \
      --start 2026-08-01 --evergreen --channel UC66W1l41kXuASV-UYvC9xzA
  python3 .kol-tools/daniel_ct.py --create-campaign ... --dry-run
  python3 .kol-tools/daniel_ct.py --self-test
"""
import argparse
import datetime as _dt
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_client():
    spec = importlib.util.spec_from_file_location('dc', os.path.join(HERE, 'daniel_client.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 纯函数（离线自检对象）────────────────────────────────────────────────
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def valid_date(s):
    """`YYYY-MM-DD` 且真实存在（挡住 2026-02-30 这类）。非字符串/空 → False。"""
    if not isinstance(s, str) or not DATE_RE.match(s.strip()):
        return False
    try:
        _dt.date(*[int(x) for x in s.strip().split('-')])
        return True
    except ValueError:
        return False


def norm_title(s):
    return re.sub(r'\s+', ' ', str(s or '').strip())


# ── 口语／不规范输入的归一化（2026-09-29 用户指令：「日期输入不规范但是你可以进行自动化纠正」）──
_MONTHS = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
           'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
EVERGREEN_RE = re.compile(
    r'^(evergreen|no\s+end\s*date|长期|永久|无期限|无结束日期|不设结束(日期)?|没有结束日期|一直)$', re.I)
NOT_EVERGREEN_RE = re.compile(r'不是|并非|not\s+evergreen|no\s+longer', re.I)


def norm_date(raw, today=None):
    """把口语／不规范日期归一成 `YYYY-MM-DD`；识别不了 → (None, None)。

    支持：`2026-8-1`／`2026/8/1`／`2026.8.1`／`2026年8月1日`／`2026年8月1号`／
         `26年8月1号`（两位年 ⇒ 20xx）／`8月1日`／`8/1`（**无年份 ⇒ 今年**，并给说明）／
         `Aug 1, 2026`／`August 1 2026`／`1 Aug 2026`。
    一律做**真实性校验**（`2026年2月30日` → None）。第二个返回值是"我替你补了什么"的说明，用于回显。
    """
    s = str(raw or '').strip()
    if not s:
        return None, None
    # 🔴 中文输入法会打出全角分隔符（／ ． － 　）—— 先折半再解析（2026-09-29 自检抓出）
    s = s.translate(str.maketrans({'／': '/', '．': '.', '－': '-', '　': ' '}))
    today = today or _dt.date.today().isoformat()
    cur_y = int(str(today)[:4])
    notes = []

    def _iso(y, m, dd, assumed_year=False, two_digit=False):
        try:
            out = _dt.date(y, m, dd).isoformat()
        except ValueError:
            return None, None
        if two_digit:
            notes.append('两位年份「%s」⇒ %d' % (s, y))
        if assumed_year:
            notes.append('未给年份 ⇒ 按今年 %d' % y)
        return out, ('；'.join(notes) or None)

    # ① 全数字分隔：2026-8-1 / 2026/8/1 / 2026.8.1
    m = re.match(r'^(\d{2,4})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})$', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            return _iso(2000 + y, mo, d, two_digit=True)
        return _iso(y, mo, d)
    # ② 中文：2026年8月1日/号；26年8月1号；8月1日
    m = re.match(r'^(?:(\d{2,4})\s*年)?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?$', s)
    if m:
        if m.group(1):
            y = int(m.group(1))
            if y < 100:
                return _iso(2000 + y, int(m.group(2)), int(m.group(3)), two_digit=True)
            return _iso(y, int(m.group(2)), int(m.group(3)))
        return _iso(cur_y, int(m.group(2)), int(m.group(3)), assumed_year=True)
    # ③ 只有月-日（数字）：8/1 → 今年
    m = re.match(r'^(\d{1,2})\s*[-/.]\s*(\d{1,2})$', s)
    if m:
        return _iso(cur_y, int(m.group(1)), int(m.group(2)), assumed_year=True)
    # ④ 英文月名：Aug 1, 2026 / August 1 2026 / 1 Aug 2026
    m = re.match(r'^([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})$', s)
    if m and m.group(1)[:3].lower() in _MONTHS:
        return _iso(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
    m = re.match(r'^(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})$', s)
    if m and m.group(2)[:3].lower() in _MONTHS:
        return _iso(int(m.group(3)), _MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
    # ⑤ 已是 ISO
    if DATE_RE.match(s):
        try:
            return _dt.date(*[int(x) for x in s.split('-')]).isoformat(), None
        except ValueError:
            return None, None
    return None, None


def norm_end(raw, today=None):
    """结束日期归一：返回 `'evergreen'` / `'YYYY-MM-DD'` / None（＋说明）。

    口语形态（`evergreen`／`长期`／`不设结束日期`）→ `'evergreen'`；
    **否定形态（`不是长期`）→ None**（否定守卫：不得被当成 evergreen）。
    """
    s = str(raw or '').strip()
    if not s:
        return None, None
    if NOT_EVERGREEN_RE.search(s):
        return None, '「%s」含否定词 ⇒ 不按 Evergreen 处理' % s
    if EVERGREEN_RE.match(s):
        return 'evergreen', '「%s」⇒ Evergreen（不传 endDate）' % s
    return norm_date(s, today)


def build_payload(brand, title, start, end, evergreen, channel, brief):
    """按界面同款规则组装入参；**校验不过直接抛错**（错误文案与界面一致）。

    日期与结束形态先过归一化（§norm_date／§norm_end）：`26年8月1号`、`2026/8/1`、`evergreen` 都收。
    """
    if not isinstance(brand, dict) or not brand.get('id'):
        raise ValueError('品牌无效（缺 id）')
    t = norm_title(title)
    if not t:
        raise ValueError('必须填写 Campaign 名称')
    start_iso, _ = norm_date(start)
    if not start_iso:
        raise ValueError('开始日期无法识别为日期（收到：%r）—— 支持 2026-08-01／26年8月1号／2026/8/1／Aug 1 2026' % (start,))
    end_norm, _ = norm_end(end) if end else (None, None)
    if end_norm == 'evergreen':
        evergreen = True
        end_norm = None
    if not evergreen and not end_norm:
        raise ValueError('必须填写结束日期，或设为 Evergreen（收到：%r）' % (end,))
    if evergreen and end_norm:
        raise ValueError('Evergreen 与结束日期互斥：勾 Evergreen 时不得给结束日期')
    if end_norm and end_norm < start_iso:
        raise ValueError('结束日期不得早于开始日期（%s < %s）' % (end_norm, start_iso))
    ch = (channel or brand.get('youtubeChannelId') or '').strip()
    if not ch:
        raise ValueError('必须填写 Brand YouTube Channel（品牌档案里也没有 youtubeChannelId）')
    payload = {
        'brandId': brand['id'],
        'title': t,
        'brandName': brand.get('name') or '',
        'brandHandle': brand.get('youtubeChannelId') or None,
        'brandYoutubeChannel': ch,
        'startDate': start_iso,
        'isEvergreen': bool(evergreen),
    }
    if not evergreen:
        payload['endDate'] = end_norm
    if brief and str(brief).strip():
        payload['brief'] = str(brief).strip()
    return {k: v for k, v in payload.items() if v is not None}


def normalization_echo(start, end, today=None):
    """回显"我替你把口语输入补成了什么"（用户 2026-09-29：「日期输入不规范但你可以自动化纠正」）。

    只在真的做了推定（补年份／两年前缀／Evergreen 口语）时才输出，**原样 ISO 不刷屏**。
    """
    out = []
    s_iso, s_note = norm_date(start, today)
    if s_note:
        out.append('开始日期 「%s」 ⇒ %s（%s）' % (start, s_iso, s_note))
    e_norm, e_note = norm_end(end, today) if end else (None, None)
    if e_note:
        out.append('结束日期 「%s」 ⇒ %s（%s）' % (end, e_norm, e_note))
    return out


def warnings_for(payload, existing, today=None):
    """软提醒（不拦）：同名已存在／开始日期在过去／频道不是 UC… 形态。"""
    out = []
    today = today or _dt.date.today().isoformat()
    key = norm_title(payload.get('title')).lower()
    same = [c for c in (existing or []) if isinstance(c, dict)
            and norm_title(c.get('title')).lower() == key]
    if same:
        out.append('已有同名 campaign %d 条（界面允许重名，故只提醒不拦）：%s'
                   % (len(same), ', '.join(str(c.get('id')) for c in same)))
    if payload.get('startDate', '') < today:
        out.append('开始日期 %s 早于今天 %s（如需修正可走 ct.campaigns.update 的 startDate）'
                   % (payload.get('startDate'), today))
    if not str(payload.get('brandYoutubeChannel', '')).startswith('UC'):
        out.append('频道不是 UC… ID 形态，创建时可能解析失败并带回 syncError')
    return out


# ── 在线动作 ────────────────────────────────────────────────────────────
def _resolve_brand(d, ref):
    """品牌引用 → brand dict。🔴 走**跨工作区索引**，与活跃工作区无关。"""
    if hasattr(d, 'resolve_brand_ref'):
        return d.resolve_brand_ref(str(ref))
    brands = d.query('brands.list', {})  # ambient-workspace-ok: 仅当客户端无 resolve_brand_ref 时兜底
    ref_s = str(ref or '').strip()
    for b in brands:
        if str(b.get('id')) == ref_s:
            return b
    hits = [b for b in brands if norm_title(b.get('name')).lower() == ref_s.lower()]
    if len(hits) == 1:
        return hits[0]
    raise ValueError('找不到品牌「%s」（可选：%s）'
                     % (ref_s, ', '.join(str(b.get('name')) for b in brands)))


def cmd_campaigns(d, args):
    b = _resolve_brand(d, args.brand)
    cs = d.query('ct.campaigns.list', {'brandId': b['id']}) or []
    print('品牌「%s」（id %s）共 %d 个 campaign：' % (b['name'], b['id'], len(cs)))
    for c in cs:
        print('  id=%-9s %-28s %s → %s%s' % (
            c.get('id'), c.get('title'), c.get('startDate'),
            c.get('endDate') or ('(Evergreen)' if c.get('isEvergreen') else '-'),
            ('  code=%s' % c.get('campaignCode')) if c.get('campaignCode') else ''))
    return 0


def cmd_create(d, args):
    b = _resolve_brand(d, args.brand)
    existing = d.query('ct.campaigns.list', {'brandId': b['id']}) or []
    payload = build_payload(b, args.title, args.start, args.end, args.evergreen,
                            args.channel, args.brief)
    # 🔴 归一化回显：把"我替你补的"明确写出来，让人有机会当场纠正（而不是悄悄替你猜）
    for line in normalization_echo(args.start, args.end):
        print('  ✏️ 归一化：%s' % line)
    for w in warnings_for(payload, existing):
        print('  ⚠️ %s' % w)
    print('待创建：%s' % json.dumps(payload, ensure_ascii=False))
    if args.dry_run:
        print('（dry-run）不执行')
        return 0
    res = d.mutate('ct.campaigns.create', payload)
    # 🔴 写后回读（CLS-46 纪律）
    after = d.query('ct.campaigns.list', {'brandId': b['id']}) or []
    hit = [c for c in after if str(c.get('id')) == str((res or {}).get('id'))]
    if not hit:
        print('❌ 创建返回 id=%s，回读没找到 —— 视为失败' % (res or {}).get('id'))
        return 1
    c = hit[0]
    print('✅ 已创建：id=%s ／ %s ／ %s → %s%s' % (
        c.get('id'), c.get('title'), c.get('startDate'),
        c.get('endDate') or ('(Evergreen)' if c.get('isEvergreen') else '-'),
        ('  code=%s' % c.get('campaignCode')) if c.get('campaignCode') else ''))
    if (res or {}).get('syncError'):
        print('  ⚠️ syncError：%s' % res['syncError'])
    print('  回读：campaign 数 %d → %d' % (len(existing), len(after)))
    print('  完整对象：%s' % json.dumps(c, ensure_ascii=False)[:600])
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--campaigns', action='store_true')
    ap.add_argument('--create-campaign', action='store_true')
    ap.add_argument('--brand', metavar='BRAND')
    ap.add_argument('--title')
    ap.add_argument('--start', metavar='YYYY-MM-DD')
    ap.add_argument('--end', metavar='YYYY-MM-DD')
    ap.add_argument('--evergreen', action='store_true')
    ap.add_argument('--channel', metavar='UC… | @handle | URL')
    ap.add_argument('--brief')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not (args.campaigns or args.create_campaign):
        ap.print_help()
        return 1
    if not args.brand:
        print('❌ 需要 --brand')
        return 1
    dc = _load_client()
    d = dc.Daniel(verbose=False)
    d.login()
    # 🔴 校验失败必须是**人话报错**（不是 Python 栈）：参数问题由用户改参，不是程序崩溃
    try:
        return cmd_campaigns(d, args) if args.campaigns else cmd_create(d, args)
    except ValueError as e:
        print('❌ %s' % e)
        return 1


# ── 离线自检 ────────────────────────────────────────────────────────────
def _raises(fn, needle):
    try:
        fn()
        return False
    except Exception as e:  # noqa: BLE001
        return needle in str(e)


def self_test():
    B = {'id': 3690002, 'name': 'Halliday', 'youtubeChannelId': 'UC66W1l41kXuASV-UYvC9xzA'}
    ctl = []
    ctl.append(('正控 正常 Evergreen 入参：endDate 必须**不出现**、isEvergreen=true',
                (lambda p: 'endDate' not in p and p['isEvergreen'] is True
                 and p['startDate'] == '2026-08-01' and p['brandName'] == 'Halliday'
                 and p['brandHandle'] == 'UC66W1l41kXuASV-UYvC9xzA')(
                     build_payload(B, 'halliday summer test', '2026-08-01', None, True, None, None))))
    ctl.append(('正控 正常有结束日期：endDate 传值、isEvergreen=false',
                (lambda p: p.get('endDate') == '2026-12-31' and p['isEvergreen'] is False)(
                    build_payload(B, 't', '2026-08-01', '2026-12-31', False, None, None))))
    ctl.append(('正控 标题前后空白被归一，brief 为空则不传',
                (lambda p: p['title'] == 'a b' and 'brief' not in p)(
                    build_payload(B, '  a   b  ', '2026-08-01', None, True, None, '   '))))
    ctl.append(('正控 给了 brief 则传', 'brief' in build_payload(
        B, 't', '2026-08-01', None, True, None, '对象：东南亚')))
    ctl.append(('正控 缺频道时回落品牌档案的 youtubeChannelId',
                build_payload(B, 't', '2026-08-01', None, True, None, None)['brandYoutubeChannel']
                == 'UC66W1l41kXuASV-UYvC9xzA'))
    ctl.append(('正控 显式频道优先于档案',
                build_payload(B, 't', '2026-08-01', None, True, 'UCabcdefghijklmnopqrstuv', None)
                ['brandYoutubeChannel'] == 'UCabcdefghijklmnopqrstuv'))

    ctl.append(('正控 二选一必填：都不给 → 报错（文案同界面）',
                _raises(lambda: build_payload(B, 't', '2026-08-01', None, False, None, None),
                        '或设为 Evergreen')))
    ctl.append(('正控 互斥：Evergreen 与 endDate 同时给 → 报错',
                _raises(lambda: build_payload(B, 't', '2026-08-01', '2026-12-31', True, None, None),
                        '互斥')))
    ctl.append(('正控 结束日期早于开始日期 → 报错',
                _raises(lambda: build_payload(B, 't', '2026-08-01', '2026-07-01', False, None, None),
                        '不得早于')))
    ctl.append(('正控 标题为空 → 报错', _raises(
        lambda: build_payload(B, '   ', '2026-08-01', None, True, None, None), 'Campaign 名称')))
    ctl.append(('正控 品牌缺 id → 报错', _raises(
        lambda: build_payload({}, 't', '2026-08-01', None, True, None, None), '品牌无效')))
    ctl.append(('正控 档案也没有频道 → 报错',
                _raises(lambda: build_payload({'id': 1, 'name': 'X'}, 't', '2026-08-01', None, True,
                                              None, None), 'Brand YouTube Channel')))

    ctl.append(('正控 日期格式：2026-02-30 这类不存在的日期必须判假',
                (not valid_date('2026-02-30')) and valid_date('2024-02-29')))
    ctl.append(('[degenerate:empty] 空／None 日期 → False，且 build_payload 报「YYYY-MM-DD」',
                (not valid_date('')) and (not valid_date(None))
                and _raises(lambda: build_payload(B, 't', '', None, True, None, None), '无法识别')))
    ctl.append(('[degenerate:type_unit] 非字符串日期不崩', (not valid_date(20260801))
                and (not valid_date(['2026-08-01']))))
    ctl.append(('[degenerate:substring] 日期不得被子串放过（`2026-8-1`／`2026-08-01x` 均判假）',
                (not valid_date('2026-8-1')) and (not valid_date('2026-08-01x'))))
    ctl.append(('[degenerate:nonlatin] 中文标题可正常归一',
                norm_title('  Halliday　夏季测试 ') == 'Halliday 夏季测试'))
    ctl.append(('[degenerate:accent_case] 同名判重大小写不敏感（软提醒侧）',
                bool(warnings_for({'title': 'Halliday Summer Test', 'startDate': '2999-01-01',
                                   'brandYoutubeChannel': 'UCx'},
                                  [{'id': 1, 'title': 'halliday summer test'}]))))
    ctl.append(('[degenerate:negation] 无同名时不得误报重名提醒',
                not any('同名' in w for w in warnings_for(
                    {'title': 'x', 'startDate': '2999-01-01', 'brandYoutubeChannel': 'UCx'},
                    [{'id': 1, 'title': 'y'}]))))
    ctl.append(('正控 过去日期／非 UC 频道各产生一条软提醒（且都只是提醒）',
                len(warnings_for({'title': 'x', 'startDate': '2000-01-01',
                                  'brandYoutubeChannel': '@handle'}, [], today='2026-09-29')) == 2))

    # ── 口语／不规范输入的归一化（用户 2026-09-29：「日期输入不规范但你可以自动化纠正」）──
    T = '2026-09-29'
    ctl.append(('正控 中文口语「26年8月1号」⇒ 2026-08-01，并说明两位年份推定',
                norm_date('26年8月1号', T) == ('2026-08-01', '两位年份「26年8月1号」⇒ 2026')))
    ctl.append(('正控 「2026年8月1日」「2026/8/1」「2026.8.1」「2026-8-1」⇒ 2026-08-01',
                all(norm_date(x, T)[0] == '2026-08-01'
                    for x in ('2026年8月1日', '2026/8/1', '2026.8.1', '2026-8-1'))))
    ctl.append(('正控 无年份「8月1日」「8/1」⇒ 今年 2026-08-01（并注明按今年）',
                norm_date('8月1日', T) == ('2026-08-01', '未给年份 ⇒ 按今年 2026')
                and norm_date('8/1', T)[0] == '2026-08-01'))
    ctl.append(('正控 英文月名「Aug 1, 2026」「1 August 2026」⇒ 2026-08-01',
                norm_date('Aug 1, 2026', T)[0] == '2026-08-01'
                and norm_date('1 August 2026', T)[0] == '2026-08-01'))
    ctl.append(('正控 Evergreen 口语：「evergreen」／「长期」／「不设结束日期」／「no end date」⇒ evergreen',
                all(norm_end(x, T)[0] == 'evergreen'
                    for x in ('evergreen', 'Evergreen', '长期', '不设结束日期', 'no end date'))))
    ctl.append(('正控 `end=evergreen` 时入参自动转 isEvergreen=true 且**不传 endDate**',
                (lambda p: p['isEvergreen'] is True and 'endDate' not in p)(
                    build_payload(B, 't', '26年8月1号', 'evergreen', False, None, None))))
    ctl.append(('正控 不存在的日期「2026年2月30日」⇒ 不识别（不得悄悄顺延成 3/2）',
                norm_date('2026年2月30日', T) == (None, None)
                and _raises(lambda: build_payload(B, 't', '2026年2月30日', None, True, None, None),
                            '无法识别')))
    ctl.append(('[degenerate:empty] 空／None 日期 → (None, None)，且 build_payload 报错',
                norm_date('', T) == (None, None) and norm_date(None, T) == (None, None)
                and norm_end('', T) == (None, None)))
    ctl.append(('[degenerate:type_unit] 非字符串日期不崩',
                norm_date(20260801, T) == (None, None)
                and norm_date(['2026-08-01'], T) == (None, None)))
    ctl.append(('[degenerate:substring] 脏尾缀不被放过（`2026-08-01x`／`2026年8月` 均不识别）',
                norm_date('2026-08-01x', T) == (None, None)
                and norm_date('2026年8月', T) == (None, None)))
    ctl.append(('[degenerate:negation] **否定守卫**：「不是长期」不得被当成 Evergreen',
                norm_end('不是长期', T)[0] is None
                and _raises(lambda: build_payload(B, 't', '2026-08-01', '不是长期', False, None, None),
                            '结束日期')))
    ctl.append(('[degenerate:accent_case] 全大写 EVERGREEN／AUG 1 2026 仍识别',
                norm_end('EVERGREEN', T)[0] == 'evergreen'
                and norm_date('AUG 1 2026', T)[0] == '2026-08-01'))
    ctl.append(('[degenerate:nonlatin] 中文全角分隔（`2026／8／1`）识别',
                norm_date('2026／8／1', T)[0] == '2026-08-01'))
    ctl.append(('正控 回显只在"真的做了推定"时出现（原样 ISO 不刷屏）',
                normalization_echo('2026-08-01', '2026-12-31', T) == []
                and len(normalization_echo('26年8月1号', 'evergreen', T)) == 2))

    print('=== daniel_ct 自检（离线）===')
    for n, v in ctl:
        print(' %s %s' % ('✅' if v else '❌', n))
    print('自检 %d/%d' % (sum(1 for _, v in ctl if v), len(ctl)))
    return 0 if all(v for _, v in ctl) else 1


if __name__ == '__main__':
    sys.exit(main())
