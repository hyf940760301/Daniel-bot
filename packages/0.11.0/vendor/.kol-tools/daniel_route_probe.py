#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daniel_route_probe.py —— 路线可用性探测器（把"待定/未知"路线一次探清并落盘）

背景（2026-09-17 缺陷清单）：
  ① 是否存在**视频级检索路由**（若存在，"数视频/统计品牌视频量"可从数千次降到数十次）；
  ② `inbox.getCreatorContactHistory` 的**正确动词**（GET 报 405，字典标"待复验"）；
  ③ `discovery.getSearchHistory` 的**参数名**（空参 400）；
  ④ `discovery.searchRoster` 是否仍不可用（曾读超时）。
纪律：**只做只读探测**（GET 一律用 query；未知动词先 GET 再 POST），**单次调用间隔 ≥1.5s**，
      每个候选记录 `<状态码/错误码> + <响应键> + <是否有视频级数组含 publishTime>`；结果落盘供字典回填。
用法：python3 .kol-tools/daniel_route_probe.py [--out data/crawl/daniel-probe/route_probe_<ts>.json]
"""
import argparse
import importlib.util
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
spec = importlib.util.spec_from_file_location('dc', os.path.join(ROOT, '.kol-tools/daniel_client.py'))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)

# (route, method, input, 说明)
CANDIDATES = [
    # ① 视频级检索候选
    ('discovery.searchVideos', 'GET', {'keywords': ['smart glasses'], 'limit': 5}, '视频级检索候选'),
    ('discovery.searchVideo', 'GET', {'keyword': 'smart glasses'}, '视频级检索候选'),
    ('discovery.videoSearch', 'GET', {'keywords': ['smart glasses']}, '视频级检索候选'),
    ('videos.search', 'GET', {'keyword': 'smart glasses'}, '视频级检索候选'),
    ('search.videos', 'GET', {'keyword': 'smart glasses'}, '视频级检索候选'),
    ('discovery.search', 'GET', {'keywords': ['smart glasses']}, '通用检索候选'),
    # ② 联系人历史（动词复验）
    ('inbox.getCreatorContactHistory', 'GET', {'channelId': 'UCBocAY5hJQ5-EQh1QFoLS1Q'}, '字典标 GET 报 405'),
    ('inbox.getCreatorContactHistory', 'POST', {'channelId': 'UCBocAY5hJQ5-EQh1QFoLS1Q'}, '改 POST 复验'),
    # ③ 检索历史参数名
    ('discovery.getSearchHistory', 'GET', {}, '空参 400'),
    ('discovery.getSearchHistory', 'GET', {'limit': 5}, '参数名候选 limit'),
    ('discovery.getSearchHistory', 'GET', {'pageSize': 5}, '参数名候选 pageSize'),
    # ④ 官方检索（曾读超时）
    ('discovery.searchRoster', 'GET', {'keywords': ['smart glasses']}, '曾读超时'),
    # ⑤ 对照：已知可用路线（真阴性对照，必须成功）
    ('discovery.resolveChannelInput', 'GET', {'input': '@Harveyinchina'}, '已知可用（对照）'),
]


def probe(d, route, method, inp):
    t0 = time.time()
    try:
        r = d.query(route, inp) if method == 'GET' else d.mutate(route, inp)
        dt = time.time() - t0
        keys = list(r.keys())[:12] if isinstance(r, dict) else ('list[%d]' % len(r) if isinstance(r, list) else type(r).__name__)
        # 是否有视频级数组且含发布时间
        s = json.dumps(r, ensure_ascii=False)[:200000]
        has_video_arr = any(k in s for k in ['"publishTime"', '"publishedAt"'])
        return {'route': route, 'method': method, 'result': 'OK', 'seconds': round(dt, 2),
                'keys': keys, 'has_publishTime': has_video_arr, 'sample': s[:300]}
    except Exception as e:
        return {'route': route, 'method': method, 'result': 'FAIL', 'seconds': round(time.time() - t0, 2),
                'error': str(e)[:220]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    d = dc.Daniel(verbose=False)
    out = []
    for route, method, inp, note in CANDIDATES:
        res = probe(d, route, method, inp)
        res['note'] = note
        out.append(res)
        flag = '✅' if res['result'] == 'OK' else '❌'
        extra = ('键=%s ｜含publishTime=%s' % (res.get('keys'), res.get('has_publishTime'))) if res['result'] == 'OK' else res.get('error', '')
        print('%s %-42s %-4s %5.1fs ｜ %s' % (flag, route, method, res['seconds'], extra))
        time.sleep(1.6)
    path = a.out or os.path.join(CACHE_DIR, 'daniel-probe', 'route_probe_%s.json' % time.strftime('%Y%m%d-%H%M%S'))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(out, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n落盘：%s' % os.path.relpath(path, ROOT))
    ok = sum(1 for x in out if x['result'] == 'OK')
    print('可用 %d／%d' % (ok, len(out)))


if __name__ == '__main__':
    sys.exit(main())
