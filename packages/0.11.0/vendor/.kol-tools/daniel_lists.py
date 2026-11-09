#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daniel_lists.py —— Daniel 系统「已保存名单（Saved Lists）」的读写直连工具。

**为什么要有它**（2026-09-29 用户指令 · Skill §4.18）：用户验收「你已经把这一条的自动化搞定了，
也就是我可以直接让你帮忙创建 list」⇒ 把"建一个名单"从**每次现探 bundle** 变成一条命令。

通路（实证 · 2026-09-29）：前端 React SPA ＋ tRPC 同源 `/api/trpc`；
  · 读：`brands.list`（GET，**入参必须是对象 `{}`**，传 null 报 `expected object, received null`）、
        `lists.listByBrand({brandId})`（GET）；
  · 写：`lists.create({brandId, name})`／`lists.rename({listId, brandId, name})`／`lists.delete({**id**, brandId})`（POST；注意 delete 的键是 `id` 不是 `listId` —— 传错键报 400）—— create 已实测建出 listId `8070002` 并回读确认。
  路由以 **前端 bundle 实测为准**（chunk `Lists-*.js` 里的调用点）；`daniel_client.py` 里写死的旧路由会**静默失效**（CLS-46）。

🔴 三条写操作纪律（本工具内置）：
  ① **重名拦截**：同 brand 下已有同名名单 → 默认拒绝（需 `--allow-duplicate` 显式放行）；
  ② **删除必须显式确认**：`--delete` 必须同时给 `--yes`，且删除前打印"将删除什么"；
  ③ **一律写后回读**：create／rename／delete 都重新拉一遍名单，核对结果后才算成功。

用法：
  python3 .kol-tools/daniel_lists.py --brands
  python3 .kol-tools/daniel_lists.py --lists Halliday
  python3 .kol-tools/daniel_lists.py --create --brand Halliday --name "agent test list"
  python3 .kol-tools/daniel_lists.py --rename --list-id 8070002 --name "new name"
  python3 .kol-tools/daniel_lists.py --delete --list-id 8070002 --yes
  python3 .kol-tools/daniel_lists.py --self-test          # 离线自检（不联网）
"""
import argparse
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _load_client():
    spec = importlib.util.spec_from_file_location('dc', os.path.join(HERE, 'daniel_client.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 纯函数（可离线自检的部分）────────────────────────────────────────────
def norm(s):
    """名单名归一：去首尾空白 ＋ 折叠内部空白 ＋ 小写（重名判定用）。"""
    return re.sub(r'\s+', ' ', str(s or '').strip()).lower()


def find_duplicate(lists_, name):
    """返回同名的既有名单（dict）或 None。退化输入（None／非列表）→ None（不拦）。"""
    if not isinstance(lists_, list):
        return None
    key = norm(name)
    if not key:
        return None
    for l in lists_:
        if isinstance(l, dict) and norm(l.get('name')) == key:
            return l
    return None


def resolve_brand(brands, ref):
    """按 id 或名字（大小写／空白不敏感）解析品牌；歧义或找不到 → 抛错。"""
    if not isinstance(brands, list):
        raise ValueError('品牌列表为空')
    ref_s = str(ref or '').strip()
    if not ref_s:
        raise ValueError('未指定品牌')
    for b in brands:
        if isinstance(b, dict) and str(b.get('id')) == ref_s:
            return b
    hits = [b for b in brands if isinstance(b, dict) and norm(b.get('name')) == norm(ref_s)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ValueError('品牌名歧义：%s 命中 %d 个（请用 brandId）' % (ref_s, len(hits)))
    names = ', '.join(str(b.get('name')) for b in brands if isinstance(b, dict))
    raise ValueError('找不到品牌「%s」；可选：%s' % (ref_s, names))


def plan_delete(target, brand_name, has_items):
    """删除前的预览文案（必须能让人看出"删的是哪一个、里面有多少人"）。"""
    if not isinstance(target, dict):
        raise ValueError('删除目标无效')
    n = target.get('influencerCount')
    if n is None:
        n = target.get('itemCount')
    return '将删除：品牌「%s」下的名单「%s」（listId %s，含 %s 个 creator）' % (
        brand_name, target.get('name'), target.get('id'), n if n is not None else '未知数量')


# ── 在线动作 ────────────────────────────────────────────────────────────
def _brands(d, workspace_id=None):
    """品牌列表。带 `workspace_id` ⇒ 显式定向；不带 ⇒ 当前活跃工作区（**仅用于展示**）。"""
    if workspace_id is None:
        return d.query('brands.list', {}) or []          # ambient-workspace-ok: 仅 --brands 展示用
    return d.query('brands.list', {'workspaceId': int(workspace_id)}) or []


def cmd_brands(d, args):
    for b in _brands(d):
        print('  id=%-9s ws=%-8s user=%-9s %s' % (b.get('id'), b.get('workspaceId'),
                                                  b.get('userId'), b.get('name')))
    return 0


def _resolve(d, ref):
    """品牌引用 → (brand, brands)。🔴 走**跨工作区**解析，与活跃工作区无关。"""
    if hasattr(d, "resolve_brand_ref"):
        b = d.resolve_brand_ref(str(ref))
        return b, _brands(d, workspace_id=b.get("workspaceId"))
    brands = _brands(d)
    return resolve_brand(brands, ref), brands


def cmd_lists(d, args):
    b, _ = _resolve(d, args.lists)
    ls = d.lists(b['id']) or []
    print('品牌「%s」（id %s）共 %d 个名单：' % (b['name'], b['id'], len(ls)))
    for l in ls:
        print('  id=%-9s %s' % (l.get('id'), l.get('name')))
    return 0


def cmd_create(d, args):
    b, _ = _resolve(d, args.brand)
    before = d.lists(b['id']) or []
    dup = find_duplicate(before, args.name)
    if dup and not args.allow_duplicate:
        print('❌ 拒绝创建：品牌「%s」下已有同名名单「%s」（listId %s）。'
              '确需重复请加 --allow-duplicate。' % (b['name'], dup.get('name'), dup.get('id')))
        return 1
    if args.dry_run:
        print('（dry-run）将在品牌「%s」（id %s）下创建名单「%s」' % (b['name'], b['id'], args.name))
        return 0
    res = d.mutate('lists.create', {'brandId': b['id'], 'name': args.name})
    # 🔴 写后回读
    after = d.lists(b['id']) or []
    hit = None
    for l in after:
        if str(l.get('id')) == str((res or {}).get('id')):
            hit = l
    if not hit:
        print('❌ 创建返回了 id=%s，但回读没找到 —— 视为失败，请人工核对。' % (res or {}).get('id'))
        return 1
    print('✅ 已创建：listId %s ／ %s ／ 品牌「%s」｜名单数 %d → %d'
          % (hit.get('id'), hit.get('name'), b['name'], len(before), len(after)))
    return 0


def cmd_rename(d, args):
    b, _ = _resolve(d, args.brand) if args.brand else (None, None)
    if b is None:
        print('❌ --rename 需要 --brand（用于回读校验）')
        return 1
    before = d.lists(b['id']) or []
    tgt = [l for l in before if str(l.get('id')) == str(args.list_id)]
    if not tgt:
        print('❌ 该品牌下没有 listId %s' % args.list_id)
        return 1
    dup = find_duplicate(before, args.name)
    if dup and str(dup.get('id')) != str(args.list_id) and not args.allow_duplicate:
        print('❌ 拒绝改名：已有同名名单「%s」（listId %s）' % (dup.get('name'), dup.get('id')))
        return 1
    if args.dry_run:
        print('（dry-run）将把 listId %s 从「%s」改名为「%s」'
              % (args.list_id, tgt[0].get('name'), args.name))
        return 0
    # 🔴 入参以 bundle 实测为准：rename 需要 brandId（`{listId, brandId, name}`）
    d.mutate('lists.rename', {'listId': int(args.list_id), 'brandId': int(b['id']), 'name': args.name})
    after = d.lists(b['id']) or []
    hit = [l for l in after if str(l.get('id')) == str(args.list_id)]
    if not hit or norm(hit[0].get('name')) != norm(args.name):
        print('❌ 回读未确认改名（当前名：%s）' % (hit[0].get('name') if hit else '名单不存在'))
        return 1
    print('✅ 已改名：listId %s →「%s」' % (args.list_id, hit[0].get('name')))
    return 0


def cmd_delete(d, args):
    b, _ = _resolve(d, args.brand) if args.brand else (None, None)
    if b is None:
        print('❌ --delete 需要 --brand（用于回读校验）')
        return 1
    before = d.lists(b['id']) or []
    tgt = [l for l in before if str(l.get('id')) == str(args.list_id)]
    if not tgt:
        print('❌ 该品牌下没有 listId %s（无需删除）' % args.list_id)
        return 1
    print(plan_delete(tgt[0], b['name'], None))
    if not args.yes:
        print('⚠️ 未带 --yes ⇒ 只预览不执行（删除不可逆）。确认后重跑并加 --yes。')
        return 1
    if args.dry_run:
        print('（dry-run）不执行')
        return 0
    # 🔴 入参以 bundle 实测为准：delete 的键是 **id**（不是 listId）＋ brandId
    d.mutate('lists.delete', {'id': int(args.list_id), 'brandId': int(b['id'])})
    after = d.lists(b['id']) or []
    if any(str(l.get('id')) == str(args.list_id) for l in after):
        print('❌ 回读发现名单仍在 —— 视为删除失败')
        return 1
    print('✅ 已删除：listId %s ／ 品牌「%s」｜名单数 %d → %d'
          % (args.list_id, b['name'], len(before), len(after)))
    return 0


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--brands', action='store_true')
    ap.add_argument('--lists', metavar='BRAND')
    ap.add_argument('--create', action='store_true')
    ap.add_argument('--rename', action='store_true')
    ap.add_argument('--delete', action='store_true')
    ap.add_argument('--brand', metavar='BRAND', help='品牌名或 brandId（写操作必填）')
    ap.add_argument('--name', metavar='NAME')
    ap.add_argument('--list-id', metavar='ID')
    ap.add_argument('--allow-duplicate', action='store_true')
    ap.add_argument('--yes', action='store_true', help='删除必须显式确认')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not any((args.brands, args.lists, args.create, args.rename, args.delete)):
        ap.print_help()
        return 1

    dc = _load_client()
    d = dc.Daniel(verbose=False)
    d.login()
    if args.brands:
        return cmd_brands(d, args)
    if args.lists:
        return cmd_lists(d, args)
    if args.create:
        if not (args.brand and args.name):
            print('❌ --create 需要 --brand 与 --name')
            return 1
        return cmd_create(d, args)
    if args.rename:
        if not args.list_id or not args.name:
            print('❌ --rename 需要 --list-id 与 --name')
            return 1
        return cmd_rename(d, args)
    if args.delete:
        if not args.list_id:
            print('❌ --delete 需要 --list-id')
            return 1
        return cmd_delete(d, args)
    return 1


# ── 离线自检（不联网；六类退化输入齐备）──────────────────────────────────
def self_test():
    ctl = []
    ls = [{'id': 1, 'name': 'Halliday—第六批'}, {'id': 2, 'name': 'agent test list'}]

    ctl.append(('正控 同名（含大小写／空格差异）必须被拦下',
                (find_duplicate(ls, 'Agent Test List') or {}).get('id') == 2
                and (find_duplicate(ls, '  agent   test list  ') or {}).get('id') == 2))
    ctl.append(('真阴性 不同名不得误拦', find_duplicate(ls, 'agent test list 2') is None))
    ctl.append(('[degenerate:empty] 空名／None／空列表 → 不得误拦、不得致崩',
                find_duplicate(ls, '') is None and find_duplicate(ls, None) is None
                and find_duplicate([], 'x') is None))
    ctl.append(('[degenerate:type_unit] 非列表／非 dict 元素 → 不得致崩',
                find_duplicate('not a list', 'x') is None
                and find_duplicate([1, 2, None], 'x') is None
                and find_duplicate(None, 'x') is None))
    ctl.append(('[degenerate:substring] 子串不算同名（`agent test` ≠ `agent test list`）',
                find_duplicate(ls, 'agent test') is None))
    ctl.append(('[degenerate:nonlatin] 中文名可正常判重（`halliday—第六批`）',
                (find_duplicate(ls, 'Halliday—第六批') or {}).get('id') == 1))
    ctl.append(('[degenerate:accent_case] 全大写／全角空格仍判重',
                (find_duplicate(ls, 'AGENT\u3000TEST LIST') or {}).get('id') == 2))

    brands = [{'id': 3690002, 'name': 'Halliday'}, {'id': 4680001, 'name': 'iPhone'}]
    ctl.append(('正控 按名解析品牌（大小写不敏感）',
                resolve_brand(brands, 'halliday')['id'] == 3690002))
    ctl.append(('正控 按 id 解析品牌', resolve_brand(brands, '4680001')['id'] == 4680001))
    ctl.append(('正控 找不到品牌 → 报错且给出可选值',
                (lambda: [False for _ in [0]] and None)() is None
                and _raises(lambda: resolve_brand(brands, 'Nope'), '可选')))
    ctl.append(('[degenerate:empty] 空品牌引用 → 报错', _raises(lambda: resolve_brand(brands, '  '), '未指定')))
    ctl.append(('[degenerate:type_unit] 品牌列表非列表 → 报错', _raises(lambda: resolve_brand(None, 'x'), '为空')))

    ctl.append(('正控 删除预览必须写出品牌／名单名／listId／数量',
                all(k in plan_delete({'id': 9, 'name': 'L', 'influencerCount': 3}, 'Halliday', None)
                    for k in ('Halliday', 'L', '9', '3'))))
    ctl.append(('[degenerate:empty] 数量缺失时预览不得致崩（写"未知数量"）',
                '未知数量' in plan_delete({'id': 9, 'name': 'L'}, 'Halliday', None)))
    ctl.append(('[degenerate:type_unit] 删除目标非 dict → 报错',
                _raises(lambda: plan_delete(None, 'b', None), '无效')))
    ctl.append(('正控 args 解析：--delete 不带 --yes 时不允许执行（由 cmd_delete 判定）',
                _no_yes_guard()))

    print('=== daniel_lists 自检（离线）===')
    for n, v in ctl:
        print(' %s %s' % ('✅' if v else '❌', n))
    print('自检 %d/%d' % (sum(1 for _, v in ctl if v), len(ctl)))
    return 0 if all(v for _, v in ctl) else 1


def _raises(fn, needle):
    try:
        fn()
        return False
    except Exception as e:  # noqa: BLE001
        return needle in str(e)


def _no_yes_guard():
    """删除命令在缺 --yes 时必须返回 1（用桩对象替代真实网络调用）。"""
    class _Stub:
        def query(self, *a, **k):
            return [{'id': 3690002, 'name': 'Halliday'}]

        def lists(self, bid):
            return [{'id': 8070002, 'name': 'agent test list', 'influencerCount': 0}]

        def mutate(self, *a, **k):
            raise AssertionError('缺 --yes 时不得调用写接口')

    args = argparse.Namespace(brand='Halliday', list_id='8070002', yes=False, dry_run=False)
    return cmd_delete(_Stub(), args) == 1


if __name__ == '__main__':
    sys.exit(main())
