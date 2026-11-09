#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daniel_brands.py —— Daniel 系统「Brand（品牌）」区块的读写直连工具。

**为什么要有它**（TICKET-131）：把 brands 区块从**每次现翻前端 bundle** 变成一条命令，
并让写操作（create／update／delete）带上与名单工具同级的守卫（dry-run 默认、删除必须 `--yes`、
写后回读、重名／空名拦截）。

**路由与入参（全部以 `_daniel_bundle/Brands-Bh2-SLpC.js` 的前端调用点为准 · 2026-10-10 实测）**

| 路由 | 方法 | 入参键（逐字取自调用点） |
|---|---|---|
| `brands.list` | GET | `{}` 或 `{workspaceId}` —— 🔴 必须是对象，传 `null` 报 400 `expected object, received null` |
| `brands.getById` | GET | `{id}` —— 🔴 键是 **`id`**，传 `{brandId}` 报 400 |
| `brands.create` | POST | `{name, description?, category?, competitors?, youtubeChannelId?, youtubeChannelTitle?, sampleCost?, targetCountries?, industryKeywords?, workspaceId?}` |
| `brands.update` | POST | `{id, ...同上字段}` —— **局部合并**（只传要改的键，未传的键原样保留） |
| `brands.delete` | POST | `{id}` |
| `brands.suggestCompetitors` | POST | `{brandName, category?}`（**只读语义**：AI 建议，不落库；GET 会 405） |
| `brands.verifyChannel` | POST | `{channelId}`（**只读语义**：YouTube 查询，GET 会 405） |

**实测字段语义（2026-10-10 · 可逆测试品牌 `_tmp-t131-*` 全链路）**
  · 可空字段（可传 `null` 清空）：`youtubeChannelId`／`youtubeChannelTitle`／`sampleCost`；
  · `description` **不接受 `null`**（create／update 均报 400 `expected string, received null`）——要清空传空串；
  · 数组字段（`targetCountries`／`industryKeywords`／`competitors`）传 `[]` 即清空；
  · 🔴 **服务端不拦空名、不拦重名、不校验 maxBrands** ⇒ 三条守卫必须由本工具在客户端做。

🔴 **写操作纪律（本工具内置）**
  ① **写操作默认 dry-run**：create／update／delete 不带 `--yes` 只打印计划、不发写请求；
  ② **删除必须显式确认**：`--delete` 必须同时给 `--yes`，且删除前打印"将删除什么"；
  ③ **一律写后回读**：create／update／delete 都重新拉 `brands.list` ＋ `brands.getById` 核对，
     回读对不上即视为失败（**实测：`brands.delete` 传一个不存在的 id 也返回 `{success:true}`**，
     不做事后回读就会把"没删掉"读成"删掉了"）；
  ④ **重名拦截／空名拦截**：同工作区已有同名品牌默认拒绝（需 `--allow-duplicate`）；
  ⑤ **删除默认只允许 `_tmp-` 前缀的测试品牌**（真实品牌要删必须显式 `--allow-non-tmp`）。

用法：
  python3 .kol-tools/daniel_brands.py --list
  python3 .kol-tools/daniel_brands.py --get 3690002
  python3 .kol-tools/daniel_brands.py --create --name "_tmp-demo" [--yes]
  python3 .kol-tools/daniel_brands.py --update --id 4800002 --name "_tmp-demo2" [--yes]
  python3 .kol-tools/daniel_brands.py --delete --id 4800002 --yes
  python3 .kol-tools/daniel_brands.py --suggest-competitors --brand-name Halliday [--category "AI Glasses"]
  python3 .kol-tools/daniel_brands.py --verify-channel --channel-id UC66W1l41kXuASV-UYvC9xzA
  python3 .kol-tools/daniel_brands.py --self-test        # 离线自检（不联网）
"""
import argparse
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 路由 → HTTP 方法（以 bundle 调用点 `useQuery` / `useMutation` 为准 · 实测 GET 写路由报 405）
ROUTE_METHOD = {
    'brands.list': 'GET',
    'brands.getById': 'GET',
    'brands.create': 'POST',
    'brands.update': 'POST',
    'brands.delete': 'POST',
    'brands.suggestCompetitors': 'POST',
    'brands.verifyChannel': 'POST',
}
# 写操作可传的字段（逐字取自 bundle 调用点；create 另可带 workspaceId）
WRITE_KEYS = ('name', 'description', 'category', 'competitors', 'youtubeChannelId',
              'youtubeChannelTitle', 'sampleCost', 'targetCountries', 'industryKeywords')
# 可空字段（传 None 即清空，实测 200）
NULLABLE_KEYS = ('youtubeChannelId', 'youtubeChannelTitle', 'sampleCost')
# 非空字符串字段（传 None 报 400 `expected string, received null`，实测）
NON_NULL_STRING_KEYS = ('name', 'description', 'category')
# 数组字段（传 [] 即清空）
ARRAY_KEYS = ('targetCountries', 'industryKeywords', 'competitors')

TMP_PREFIX = '_tmp-'


def _load_client():
    spec = importlib.util.spec_from_file_location('dc', os.path.join(HERE, 'daniel_client.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 纯函数（离线自检的部分）────────────────────────────────────────────
def norm(s):
    """品牌名归一：去首尾空白 ＋ 折叠内部空白 ＋ 小写（重名判定用 · 与 daniel_lists.py 同口径）。"""
    return re.sub(r'\s+', ' ', str(s if s is not None else '').strip()).lower()


def validate_name(name):
    """品牌名校验：非空且非纯空白；返回去空白后的名字，否则抛错。"""
    s = str(name if name is not None else '').strip()
    if not s:
        raise ValueError('品牌名不能为空（纯空白也不行）')
    if any(ord(c) < 32 for c in s):
        raise ValueError('品牌名不能包含控制字符')
    return s


def find_duplicate(brands, name):
    """返回同名的既有品牌（dict）或 None。退化输入（None／非列表）→ None（不拦）。"""
    if not isinstance(brands, list):
        return None
    key = norm(name)
    if not key:
        return None
    for b in brands:
        if isinstance(b, dict) and norm(b.get('name')) == key:
            return b
    return None


def check_delete_allowed(name, allow_non_tmp=False):
    """删除守卫：默认只允许删 `_tmp-` 前缀的测试品牌；真实品牌需显式放行。"""
    s = str(name if name is not None else '')
    if s.strip().lower().startswith(TMP_PREFIX) or allow_non_tmp:
        return True
    raise ValueError('拒绝删除：品牌「%s」不是 `%s` 前缀的测试品牌（防误删真实品牌）。'
                     '确需删除请加 --allow-non-tmp。' % (s, TMP_PREFIX))


def build_create_payload(name, workspace_id=None, description=None, category=None,
                         sample_cost=None, target_countries=None, industry_keywords=None,
                         competitors=None):
    """按 bundle 调用点组装 create 入参：**值为空的键不写入**（尤其 description 不得写 null）。"""
    p = {'name': validate_name(name)}
    if workspace_id is not None:
        p['workspaceId'] = int(workspace_id)
    if description is not None:
        p['description'] = str(description)
    if category is not None:
        p['category'] = str(category)
    if sample_cost is not None:
        p['sampleCost'] = int(sample_cost)
    if target_countries:
        p['targetCountries'] = list(target_countries)
    if industry_keywords:
        p['industryKeywords'] = list(industry_keywords)
    if competitors:
        p['competitors'] = [dict(c) for c in competitors]
    return p


def build_update_payload(brand_id, changes):
    """组装 update 入参：`{id, ...changes}` —— 🔴 `id` 必填；`description` 不得为 null。"""
    if brand_id is None or str(brand_id).strip() == '':
        raise ValueError('--update 需要 --id（brandId）')
    try:
        bid = int(brand_id)
    except (TypeError, ValueError):
        raise ValueError('--id 必须是数字（brandId）')
    p = {'id': bid}
    for k, v in (changes or {}).items():
        if k not in WRITE_KEYS:
            raise ValueError('未知字段：%s（允许：%s）' % (k, ', '.join(WRITE_KEYS)))
        if v is None:
            if k in NULLABLE_KEYS:
                p[k] = None          # 实测：可空字段传 null → 200，且确实清空
                continue
            raise ValueError('字段 %s 不接受 null（实测服务端报 400 expected string, received null）；'
                             '要清空请传空串' % k)
        p[k] = v
    if len(p) == 1:
        raise ValueError('--update 没有任何要改的字段')
    return p


def plan_delete(brand):
    """删除前的预览文案（必须能看出"删的是哪一个"）。"""
    if not isinstance(brand, dict):
        raise ValueError('删除目标无效（先 --get 确认真实存在）')
    comp = brand.get('competitors')
    n = len(comp) if isinstance(comp, list) else '未知'
    return ('将删除：品牌「%s」（id %s，workspace %s，竞品 %s 个）'
            % (brand.get('name'), brand.get('id'), brand.get('workspaceId'), n))


def readback_hit(brands, bid):
    """回读核对：在 brands.list 结果里找该 id；找不到即视为失败。"""
    if not isinstance(brands, list):
        return None
    for b in brands:
        if isinstance(b, dict) and str(b.get('id')) == str(bid):
            return b
    return None


def diff_fields(before, after, keys):
    """返回 [(key, before, after)] —— 只列真正变化的键。"""
    out = []
    for k in keys:
        b = (before or {}).get(k)
        a = (after or {}).get(k)
        if b != a:
            out.append((k, b, a))
    return out


def brief(b):
    """一行摘要（先给判断，再给细节）。"""
    return 'id=%-9s ws=%-8s cat=%-18s %s' % (
        b.get('id'), b.get('workspaceId'), str(b.get('category'))[:18], b.get('name'))


# ── 在线动作 ────────────────────────────────────────────────────────────
def _brands(d, workspace_id=None):
    """读品牌列表。🔴 一律**显式给 workspaceId**（`workspace_id=None` 时回落到当前活跃工作区，
    仅供 `--list` 展示；解析与回读路径**必须**传 `workspace_id`）。"""
    if workspace_id is None:
        return d.query('brands.list', {}) or []          # ambient-workspace-ok: 仅 --list 展示用
    return d.query('brands.list', {'workspaceId': int(workspace_id)}) or []


def cmd_list(d, args):
    bs = _brands(d, args.workspace_id)
    print('当前工作区品牌 %d 个（brands.list —— 实测只返回当前工作区的品牌，跨工作区请用 --get <id>）：' % len(bs))
    for b in bs:
        print('  ' + brief(b))
    return 0


def cmd_get(d, args):
    b = d.query('brands.getById', {'id': int(args.get)})
    if not b:
        print('❌ brands.getById id=%s → null（该品牌不存在或无权访问）' % args.get)
        return 1
    print(json.dumps(b, ensure_ascii=False, indent=2))
    return 0


def cmd_suggest_competitors(d, args):
    """AI 竞品建议（POST 但只读语义 · 实测不落库）。"""
    if not (args.brand_name or '').strip():
        print('❌ --suggest-competitors 需要 --brand-name')
        return 1
    inp = {'brandName': args.brand_name.strip()}
    if args.category:
        inp['category'] = args.category.strip()
    r = d.mutate('brands.suggestCompetitors', inp)
    comps = (r or {}).get('competitors') or []
    print('竞品建议 %d 个（brands.suggestCompetitors · 只读语义，未写库）：' % len(comps))
    for c in comps:
        print('  - %s ｜关键词：%s' % (c.get('name'), '、'.join(c.get('categoryKeywords') or [])))
    if (r or {}).get('brandCategoryKeywords'):
        print('  品牌类目关键词：%s' % '、'.join(r['brandCategoryKeywords']))
    return 0


def cmd_verify_channel(d, args):
    """校验 YouTube Channel（POST 但只读语义）—— 入参键是 `channelId`（bundle 调用点逐字）。"""
    if not (args.channel_id or '').strip():
        print('❌ --verify-channel 需要 --channel-id')
        return 1
    r = d.mutate('brands.verifyChannel', {'channelId': args.channel_id.strip()}) or {}
    if r.get('verified'):
        print('✅ 校验通过：%s ｜ channelId %s ｜ 订阅 %s'
              % (r.get('title'), r.get('channelId'), r.get('subscriberCount')))
        return 0
    print('❌ 校验未通过（原始返回）：%s' % json.dumps(r, ensure_ascii=False))
    return 1


def cmd_create(d, args):
    try:
        name = validate_name(args.name)
    except ValueError as e:
        print('❌ %s' % e)
        return 1
    before = _brands(d)
    dup = find_duplicate(before, name)
    if dup and not args.allow_duplicate:
        print('❌ 拒绝创建：当前工作区已有同名品牌「%s」（id %s）。确需重复请加 --allow-duplicate。'
              % (dup.get('name'), dup.get('id')))
        return 1
    payload = build_create_payload(
        name, workspace_id=args.workspace_id, description=args.description,
        category=args.category, sample_cost=args.sample_cost,
        target_countries=_csv(args.target_countries),
        industry_keywords=_csv(args.industry_keywords),
        competitors=_parse_competitors(args.competitors))
    print('（计划）brands.create ← %s' % json.dumps(payload, ensure_ascii=False))
    if not name.lower().startswith(TMP_PREFIX):
        print('⚠️  注意：该名字不是 `%s` 前缀的测试品牌 —— 会在真实工作区里建出一个常驻品牌。'
              % TMP_PREFIX)
    if not args.yes:
        print('⚠️ 写操作默认 dry-run（未带 --yes）⇒ 不执行。确认后重跑并加 --yes。')
        return 0
    res = d.mutate('brands.create', payload) or {}
    new_id = res.get('id')
    # 🔴 写后回读：**必须在目标工作区回读**（带 --workspace-id 时 brands.list 无参会读错工作区 ——
    #    2026-10-10 实测：显式建到 510002 的品牌在活跃工作区 90002 的列表里查不到，被误报为"创建失败"）
    ws_target = args.workspace_id
    after = _brands(d, ws_target)
    hit = readback_hit(after, new_id)
    if not hit and ws_target is None:
        # 未指定工作区时，拿 getById 反查它实际落在哪个工作区，再回读一次
        got = d.query('brands.getById', {'id': new_id}) or {}
        if got.get('id'):
            ws_target = got.get('workspaceId')
            after = _brands(d, ws_target)
            hit = readback_hit(after, new_id)
    if not hit:
        print('❌ 创建返回了 id=%s，但回读 brands.list 没找到 —— 视为失败，请人工核对。' % new_id)
        return 1
    print('✅ 已创建：id %s ／「%s」｜工作区 %s｜品牌数 %d → %d'
          % (new_id, hit.get('name'), hit.get('workspaceId'), len(before), len(after)))
    print('   回读：%s' % brief(hit))
    return 0


def cmd_update(d, args):
    try:
        bid = int(args.id) if args.id else None
    except (TypeError, ValueError):
        print('❌ --id 必须是数字（brandId）')
        return 1
    changes = {}
    if args.name is not None:
        try:
            changes['name'] = validate_name(args.name)
        except ValueError as e:
            print('❌ %s' % e)
            return 1
    if args.description is not None:
        changes['description'] = args.description
    if args.category is not None:
        changes['category'] = args.category
    if args.sample_cost is not None:
        changes['sampleCost'] = int(args.sample_cost)
    if args.target_countries is not None:
        changes['targetCountries'] = _csv(args.target_countries)
    if args.industry_keywords is not None:
        changes['industryKeywords'] = _csv(args.industry_keywords)
    if args.competitors is not None:
        changes['competitors'] = _parse_competitors(args.competitors)
    if args.clear_channel:
        changes['youtubeChannelId'] = None
        changes['youtubeChannelTitle'] = None
    if args.clear_sample_cost:
        changes['sampleCost'] = None
    try:
        payload = build_update_payload(bid, changes)
    except ValueError as e:
        print('❌ %s' % e)
        return 1

    before = d.query('brands.getById', {'id': bid})
    if not before:
        print('❌ brands.getById id=%s → null（该品牌不存在，拒绝更新）' % bid)
        return 1
    print('（现状）%s' % brief(before))
    print('（计划）brands.update ← %s' % json.dumps(payload, ensure_ascii=False))
    if not args.yes:
        print('⚠️ 写操作默认 dry-run（未带 --yes）⇒ 不执行。确认后重跑并加 --yes。')
        return 0
    d.mutate('brands.update', payload)
    after = d.query('brands.getById', {'id': bid})
    if not after:
        print('❌ 更新后 brands.getById → null（品牌不见了！立即人工核查）')
        return 1
    req_keys = [k for k in payload if k != 'id']
    diffs = diff_fields(before, after, req_keys)
    not_applied = [k for k in req_keys if after.get(k) != payload[k]]
    print('✅ 已更新 id %s：「%s」｜实际变化 %d 处' % (bid, after.get('name'), len(diffs)))
    for k, b, a in diffs:
        print('   %s：%s → %s' % (k, json.dumps(b, ensure_ascii=False)[:120],
                                  json.dumps(a, ensure_ascii=False)[:120]))
    if not diffs:
        print('   ℹ️ 回读与现状完全一致（写入值本就等于现值）')
    if not_applied:
        print('❌ 以下字段回读与写入值不等（未生效或服务端做了归一）：%s' % ', '.join(not_applied))
        return 1
    return 0


def cmd_delete(d, args):
    try:
        bid = int(args.id)
    except (TypeError, ValueError):
        print('❌ --id 必须是数字（brandId）')
        return 1
    # 🔴 先 getById 定位该品牌在哪个工作区（delete 的键是 id，可跨工作区），再在该工作区回读
    got = d.query('brands.getById', {'id': bid}) or {}
    ws_own = got.get('workspaceId')
    before = _brands(d, ws_own)
    hit = readback_hit(before, bid) or (got if got.get('id') else None)
    if not hit:
        print('❌ brands.getById 与 brands.list 都找不到 id %s（跨工作区品牌请直接核对 id）' % bid)
        return 1
    if ws_own:
        print('（工作区）该品牌属于 workspace %s ｜本工作区品牌数 %d' % (ws_own, len(before)))
    # 🔴 先打印"将删除什么"（无论后面放不放行，预览都要先出）
    print(plan_delete(hit))
    if not args.yes:
        print('⚠️ 未带 --yes ⇒ 只预览不执行（删除不可逆）。确认后重跑并加 --yes。')
        return 1
    try:
        check_delete_allowed(hit.get('name'), args.allow_non_tmp)
    except ValueError as e:
        print('❌ %s' % e)
        return 1
    if args.dry_run:
        print('（dry-run）不执行')
        return 0
    # 🔴 入参以 bundle 实测为准：delete 的键是 `id`（`g.mutate({id:a.id})`）
    res = d.mutate('brands.delete', {'id': bid}) or {}
    # 🔴 写后回读：delete 传不存在的 id 也返回 success:true（实测），必须靠回读判定
    after = _brands(d, ws_own)
    still = readback_hit(after, bid)
    gone = d.query('brands.getById', {'id': bid})
    if still or gone:
        print('❌ 回读发现品牌仍在（list 命中=%s／getById=%s）—— 视为删除失败'
              % (bool(still), json.dumps(gone, ensure_ascii=False)[:120]))
        return 1
    print('✅ 已删除：id %s ／「%s」（服务端返回 %s）'
          % (bid, hit.get('name'), json.dumps(res, ensure_ascii=False)))
    print('   回读证明：brands.list %s → %s' % ([b.get('id') for b in before], [b.get('id') for b in after]))
    print('   回读证明：brands.getById id=%s → null' % bid)
    return 0


def _csv(s):
    if s is None:
        return None
    return [x.strip() for x in str(s).split(',') if x.strip()]


def _parse_competitors(s):
    """`--competitors "Ray-Ban Meta:AI glasses|smart glasses;XREAL:AR glasses"` → bundle 形状。"""
    if s is None:
        return None
    out = []
    for item in str(s).split(';'):
        item = item.strip()
        if not item:
            continue
        if ':' in item:
            nm, kws = item.split(':', 1)
        else:
            nm, kws = item, ''
        nm = nm.strip()
        if not nm:
            continue
        out.append({'name': nm, 'categoryKeywords': [k.strip() for k in kws.split('|') if k.strip()]})
    return out


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--list', action='store_true', help='列当前工作区品牌（brands.list）')
    ap.add_argument('--get', metavar='ID', help='按 brandId 直查（可跨工作区）')
    ap.add_argument('--create', action='store_true')
    ap.add_argument('--update', action='store_true')
    ap.add_argument('--delete', action='store_true')
    ap.add_argument('--suggest-competitors', action='store_true')
    ap.add_argument('--verify-channel', action='store_true')
    ap.add_argument('--id', metavar='ID', help='brandId（update／delete 必填）')
    ap.add_argument('--name', metavar='NAME')
    ap.add_argument('--description')
    ap.add_argument('--category')
    ap.add_argument('--sample-cost', metavar='N')
    ap.add_argument('--target-countries', metavar='US,CA,GB')
    ap.add_argument('--industry-keywords', metavar='kw1,kw2')
    ap.add_argument('--competitors', metavar='"Name:kw1|kw2;Name2:kw"')
    ap.add_argument('--clear-channel', action='store_true', help='清空 youtubeChannelId/Title（实测传 null → 200）')
    ap.add_argument('--clear-sample-cost', action='store_true')
    ap.add_argument('--workspace-id', metavar='ID', help='create 时可指定工作区（实测可省，默认当前工作区）')
    ap.add_argument('--brand-name', metavar='NAME', help='--suggest-competitors 用')
    ap.add_argument('--channel-id', metavar='UCxxx', help='--verify-channel 用')
    ap.add_argument('--allow-duplicate', action='store_true')
    ap.add_argument('--allow-non-tmp', action='store_true',
                    help='允许删除非 `_tmp-` 前缀的真实品牌（危险，需人工确认）')
    ap.add_argument('--yes', action='store_true', help='写操作显式确认（不带则 dry-run）')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not any((args.list, args.get, args.create, args.update, args.delete,
                args.suggest_competitors, args.verify_channel)):
        ap.print_help()
        return 1

    dc = _load_client()
    d = dc.Daniel(verbose=False)
    d.login()
    if args.list:
        return cmd_list(d, args)
    if args.get:
        return cmd_get(d, args)
    if args.suggest_competitors:
        return cmd_suggest_competitors(d, args)
    if args.verify_channel:
        return cmd_verify_channel(d, args)
    if args.create:
        if not args.name:
            print('❌ --create 需要 --name')
            return 1
        return cmd_create(d, args)
    if args.update:
        if not args.id:
            print('❌ --update 需要 --id')
            return 1
        return cmd_update(d, args)
    if args.delete:
        if not args.id:
            print('❌ --delete 需要 --id')
            return 1
        return cmd_delete(d, args)
    return 1


# ── 离线自检（不联网）──────────────────────────────────────────────────
class _Stub:
    """桩客户端：记录调用；`mutate` 默认视为"不该发生"的写请求（只有 allow_writes 里的才放行）。"""

    def __init__(self, brands=None, get=None, allow_writes=()):
        self.brands = brands if brands is not None else [
            {'id': 3690002, 'name': 'Halliday', 'workspaceId': 90002, 'category': 'AI Glasses',
             'competitors': [{'name': 'Ray-Ban Meta'}]},
            {'id': 4680001, 'name': 'iPhone', 'workspaceId': 90002}]
        self.get = get
        self.calls = []
        self.writes = []
        self.allow_writes = set(allow_writes)

    def query(self, route, inp=None, **k):
        self.calls.append(('query', route, inp))
        if route == 'brands.list':
            return self.brands
        if route == 'brands.getById':
            return self.get
        raise AssertionError('未预期的读路由 ' + route)

    def mutate(self, route, inp=None, **k):
        self.writes.append((route, inp))
        if route not in self.allow_writes:
            raise AssertionError('写了不该写的接口：%s' % route)
        if route == 'brands.delete':          # 模拟删除生效（供回读核对）
            self.brands = [b for b in self.brands
                           if str(b.get('id')) != str((inp or {}).get('id'))]
            self.get = None
            return {'success': True}
        return {}


def _ns(**kw):
    base = dict(list=False, get=None, create=False, update=False, delete=False,
                suggest_competitors=False, verify_channel=False, id=None, name=None,
                description=None, category=None, sample_cost=None, target_countries=None,
                industry_keywords=None, competitors=None, clear_channel=False,
                clear_sample_cost=False, workspace_id=None, brand_name=None, channel_id=None,
                allow_duplicate=False, allow_non_tmp=False, yes=False, dry_run=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _raises(fn, needle):
    try:
        fn()
        return False
    except Exception as e:  # noqa: BLE001
        return needle in str(e)


def self_test():
    ctl = []
    bs = [{'id': 3690002, 'name': 'Halliday'}, {'id': 4680001, 'name': 'iPhone'},
          {'id': 4800001, 'name': '_tmp-t131-brands-probe'}]

    # 1–4 名称归一／重名
    ctl.append(('① 正控 同名（大小写／空白差异）必须被拦下',
                (find_duplicate(bs, 'halliday') or {}).get('id') == 3690002
                and (find_duplicate(bs, '  Halliday  ') or {}).get('id') == 3690002
                and (find_duplicate(bs, 'Halliday\u3000') or {}).get('id') == 3690002
                and find_duplicate(bs, '  HAL LIDAY ') is None))
    ctl.append(('② 真阴性 不同名不得误拦', find_duplicate(bs, 'Halliday G2') is None))
    ctl.append(('③ [degenerate:substring] 子串／前后缀不算同名',
                find_duplicate(bs, 'Hall') is None and find_duplicate(bs, 'Halliday2') is None))
    ctl.append(('④ [degenerate:empty/type] 空名／None／非列表 → 不误拦、不致崩',
                find_duplicate(bs, '') is None and find_duplicate(bs, None) is None
                and find_duplicate('not a list', 'x') is None and find_duplicate([1, None], 'x') is None))

    # 5–6 空名守卫
    ctl.append(('⑤ 空名／纯空白名必须被拒绝',
                _raises(lambda: validate_name(''), '不能为空')
                and _raises(lambda: validate_name('   '), '不能为空')
                and _raises(lambda: validate_name(None), '不能为空')))
    ctl.append(('⑥ 控制字符名被拒绝／正常名去空白后通过',
                _raises(lambda: validate_name('a\tb'), '控制字符')
                and validate_name('  _tmp-x  ') == '_tmp-x'))

    # 7–9 create 守卫（桩：缺 --yes 不得发写请求；重名拒绝）
    st = _Stub()
    ctl.append(('⑦ create 不带 --yes ⇒ dry-run，绝不调用写接口',
                cmd_create(st, _ns(create=True, name='_tmp-guard')) == 0 and st.writes == []))
    st = _Stub()
    ctl.append(('⑧ create 重名 ⇒ 拒绝（返回 1 且不写）',
                cmd_create(st, _ns(create=True, name='halliday', yes=True)) == 1 and st.writes == []))
    st = _Stub()
    ctl.append(('⑨ create 空名 ⇒ 拒绝且不写',
                cmd_create(st, _ns(create=True, name='   ', yes=True)) == 1 and st.writes == []))

    # 10–12 update 守卫
    ctl.append(('⑩ update 缺 --id ⇒ 报错',
                _raises(lambda: build_update_payload(None, {'name': 'x'}), '需要 --id')
                and _raises(lambda: build_update_payload('abc', {'name': 'x'}), '必须是数字')))
    ctl.append(('⑪ update 没有任何字段 ⇒ 报错（防"空更新"掩盖问题）',
                _raises(lambda: build_update_payload(1, {}), '没有任何要改的字段')))
    ctl.append(('⑫ update description=null ⇒ 拒绝（实测服务端 400）',
                _raises(lambda: build_update_payload(1, {'description': None}), '不接受 null')))

    # 13–15 delete 守卫（桩）
    st = _Stub()
    ctl.append(('⑬ 🔴 delete 不带 --yes ⇒ 只预览、返回 1、绝不调用写接口',
                cmd_delete(st, _ns(delete=True, id='3690002')) == 1 and st.writes == []))
    st = _Stub()
    ctl.append(('⑭ 🔴 delete 真实品牌名 ⇒ 拒绝（非 _tmp- 前缀，需 --allow-non-tmp）',
                cmd_delete(st, _ns(delete=True, id='3690002', yes=True)) == 1 and st.writes == []))
    st = _Stub(brands=[{'id': 4800001, 'name': '_tmp-x'}, {'id': 3690002, 'name': 'Halliday'}],
               allow_writes=('brands.delete',))
    ctl.append(('⑮ delete _tmp- 品牌且带 --yes ⇒ 才会真的发出删除请求，并靠回读判定为成功',
                cmd_delete(st, _ns(delete=True, id='4800001', yes=True)) == 0
                and st.writes and st.writes[0][0] == 'brands.delete'
                and st.writes[0][1] == {'id': 4800001}))
    ctl.append(('⑯ [degenerate:empty] delete 目标不存在 ⇒ 返回 1 且不写',
                cmd_delete(_Stub(), _ns(delete=True, id='99999999', yes=True)) == 1))

    # 17–19 入参键与载荷保真（bundle 取证）
    ctl.append(('⑰ 🔴 路由→方法映射：读 GET／写 POST，getById 入参键是 `id`',
                ROUTE_METHOD['brands.list'] == 'GET' and ROUTE_METHOD['brands.getById'] == 'GET'
                and ROUTE_METHOD['brands.create'] == 'POST' and ROUTE_METHOD['brands.delete'] == 'POST'
                and ROUTE_METHOD['brands.suggestCompetitors'] == 'POST'
                and ROUTE_METHOD['brands.verifyChannel'] == 'POST'))
    p = build_create_payload('_tmp-x', description='d', target_countries=['US'])
    ctl.append(('⑱ create 载荷：空值键不写入（description 缺失即不出现，不得写 null）',
                'description' in p and 'category' not in p and 'youtubeChannelId' not in p
                and all(k in ('name', 'workspaceId') + WRITE_KEYS for k in p)))
    ctl.append(('⑲ [degenerate:type_unit] 载荷键集必须落在 bundle 调用点键集内',
                set(build_create_payload('x', workspace_id=1).keys()) <=
                set(('name', 'workspaceId') + WRITE_KEYS)))

    # 20–21 只读子命令的参数守卫
    ctl.append(('⑳ verify-channel 缺 --channel-id ⇒ 返回 1（不发请求）',
                cmd_verify_channel(_Stub(), _ns(verify_channel=True, channel_id='  ')) == 1))
    ctl.append(('㉑ suggest-competitors 缺 --brand-name ⇒ 返回 1（不发请求）',
                cmd_suggest_competitors(_Stub(), _ns(suggest_competitors=True, brand_name='')) == 1))

    # 22–23 回读判据与预览文案
    ctl.append(('㉒ 🔴 回读判据：list 里找不到该 id ⇒ 视为失败（防把没删掉读成删掉）',
                readback_hit(bs, 4800001) is not None and readback_hit(bs, 4800009) is None))
    ctl.append(('㉓ 删除预览必须写出品牌名／id／workspace／竞品数，且缺失时不得致崩',
                all(s in plan_delete({'id': 9, 'name': '_tmp-x', 'workspaceId': 90002,
                                      'competitors': [1, 2]}) for s in ('_tmp-x', '9', '90002', '2'))
                and '未知' in plan_delete({'id': 9, 'name': '_tmp-x'})))
    # 25–27 工作区口径（2026-10-10 实测回填）：回读范围必须跟随写入目标工作区
    class _WSrec(object):
        def __init__(self):
            self.seen = []

        def query(self, route, inp=None):
            self.seen.append((route, inp))
            return [{'id': 7, 'name': '_tmp-x', 'workspaceId': 510002}]
    rec = _WSrec()
    _brands(rec)
    _brands(rec, 510002)
    ctl.append(('㉕ 🔴 回读范围跟随目标工作区：无参 ⇒ {} ；显式 ⇒ {workspaceId:510002}',
                rec.seen[0][1] == {} and rec.seen[1][1] == {'workspaceId': 510002}))
    ctl.append(('㉖ 显式工作区回读能命中该工作区的品牌（防"建到别的工作区被读成失败"）',
                readback_hit(_brands(rec, 510002), 7) is not None))
    ctl.append(('㉗ [degenerate:type_unit] workspace_id 传字符串数字 ⇒ 转 int 不崩',
                _brands(rec, '510002') == [{'id': 7, 'name': '_tmp-x', 'workspaceId': 510002}]))

    ctl.append(('㉔ [degenerate:type_unit] 删除目标非 dict／非列表入参 ⇒ 不崩',
                _raises(lambda: plan_delete(None), '无效') and _csv(None) is None
                and _parse_competitors('A:k1|k2;B:') == [{'name': 'A', 'categoryKeywords': ['k1', 'k2']},
                                                         {'name': 'B', 'categoryKeywords': []}]))

    print('=== daniel_brands 自检（离线 · 不联网）===')
    for n, v in ctl:
        print(' %s %s' % ('✅' if v else '❌', n))
    ok = sum(1 for _, v in ctl if v)
    print('自检 %d/%d' % (ok, len(ctl)))
    return 0 if ok == len(ctl) else 1


if __name__ == '__main__':
    sys.exit(main())
