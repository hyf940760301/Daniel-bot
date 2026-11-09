#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_clarify_registry.py —— 澄清闸的**双向对账门禁**（C20）。

为什么单独一个文件
------------------
C19 只管"登记表自己长什么样"（结构）；本文件管"登记表与触发词文件**是不是同一份清单**"。
把两者放一起会让"改一个词"的红灯来源说不清。

四条断言
--------
  C20-a  双向一一对应：登记表每个 (场景, dim key) 在触发词文件里**恰好一条**；反之不得有幽灵条目
  C20-b  每条 `hit` 非空；每条 `hitRe` 能编译
  C20-c  数据规范：`hitRe` 不得出现 `\\d`（必须 `[0-9]`，JS/Python 对全角数字判定不同）；
          `\\s` 必须以 `[\\s\\uFEFF]` 形式出现（JS 的 `\\s` 含 BOM，Python 不含）
  C20-d  `topicHints` 覆盖且仅覆盖 3 个场景（list_ops → brand_setup → kol_search），
          分词总数 18（6／4／8）

用法
----
  python3 mcp/check_clarify_registry.py            # 0＝绿，2＝红
  python3 mcp/check_clarify_registry.py --json
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
PKG = os.path.dirname(HERE)
INDEX = os.path.join(HERE, "corpus", "_ONTOLOGY.json")
TRIGGERS = os.path.join(PKG, "daniel_cli", "data", "clarify_triggers.json")

REGISTRY_ID = "criterion.clarify.param_gate"
SCREEN_ID = "criterion.creator.screen"
HINT_ORDER = ["list_ops", "brand_setup", "kol_search"]
HINT_COUNTS = {"list_ops": 6, "brand_setup": 4, "kol_search": 8}
WS_OK = "[\\s\\uFEFF]"


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def run():
    items = []

    def add(cid, ok, detail):
        items.append({"id": cid, "ok": ok, "detail": detail})

    if not os.path.isfile(INDEX) or not os.path.isfile(TRIGGERS):
        missing = [p for p in (INDEX, TRIGGERS) if not os.path.isfile(p)]
        add("C20-a", False, "缺文件：%s（先跑 `mcp/check_corpus_sync.py --sync`）" % "、".join(missing))
        return items

    doc = _load(INDEX)
    trig = _load(TRIGGERS)
    by_id = {e.get("id"): e for e in doc.get("entries", [])}
    entry = by_id.get(REGISTRY_ID) or {}
    trig_sc = trig.get("scenarios") or {}

    # C20-a 双向一一对应
    reg_pairs, trig_pairs = [], []
    for sc in entry.get("scenarios") or []:
        for d in sc.get("dims") or []:
            reg_pairs.append((sc.get("key"), d.get("key")))
    for sk, dims in trig_sc.items():
        for dk in dims or {}:
            trig_pairs.append((sk, dk))
    dup_reg = sorted(p for p in set(reg_pairs) if reg_pairs.count(p) > 1)
    dup_trig = sorted(p for p in set(trig_pairs) if trig_pairs.count(p) > 1)
    only_reg = sorted(set(reg_pairs) - set(trig_pairs))
    only_trig = sorted(set(trig_pairs) - set(reg_pairs))
    probs = []
    if dup_reg:
        probs.append("登记表重复 %d" % len(dup_reg))
    if dup_trig:
        probs.append("触发词重复 %d" % len(dup_trig))
    if only_reg:
        probs.append("登记表有、触发词缺 %d（%s）" % (len(only_reg), "、".join("%s.%s" % p for p in only_reg[:3])))
    if only_trig:
        probs.append("触发词有、登记表无 %d（%s）" % (len(only_trig), "、".join("%s.%s" % p for p in only_trig[:3])))
    add("C20-a", not probs,
        "对账 %d 条，双向一致" % len(reg_pairs) if not probs else "；".join(probs))

    # C20-b hit 非空 ＋ hitRe 可编译
    probs = []
    for sk, dims in trig_sc.items():
        for dk, spec in (dims or {}).items():
            hit = spec.get("hit")
            if not isinstance(hit, list) or not [x for x in hit if str(x).strip()]:
                probs.append("%s.%s 的 hit 为空" % (sk, dk))
            for pat in spec.get("hitRe") or []:
                try:
                    re.compile(pat)
                except re.error as exc:
                    probs.append("%s.%s 正则编译失败：%r（%s）" % (sk, dk, pat, exc))
    add("C20-b", not probs, "hit／hitRe 全部可用" if not probs else "；".join(probs[:4]))

    # C20-c 数据规范（\d → [0-9]；\s → [\s\uFEFF]）
    probs = []
    for sk, dims in trig_sc.items():
        for dk, spec in (dims or {}).items():
            for pat in spec.get("hitRe") or []:
                if "\\d" in pat:
                    probs.append("%s.%s 用了 \\d（应写 [0-9]）" % (sk, dk))
                rest = pat.replace(WS_OK, "")
                if "\\s" in rest:
                    probs.append("%s.%s 有裸 \\s（应写 %s）" % (sk, dk, WS_OK))
    add("C20-c", not probs, "数字位／空白类写法规范" if not probs else "；".join(probs[:4]))

    # C20-d topicHints
    probs = []
    hints = trig.get("topicHints") or []
    keys = [h[0] for h in hints if isinstance(h, list) and h]
    if keys != HINT_ORDER:
        probs.append("顺序＝%s，应为 %s" % (keys, HINT_ORDER))
    for h in hints:
        if isinstance(h, list) and len(h) == 2:
            topic, words = h[0], h[1] or []
            if topic in HINT_COUNTS and len(words) != HINT_COUNTS[topic]:
                probs.append("%s 分词 %d≠%d" % (topic, len(words), HINT_COUNTS[topic]))
    total = sum(len(h[1]) for h in hints if isinstance(h, list) and len(h) == 2)
    if total != 18:
        probs.append("分词合计 %d≠18" % total)
    add("C20-d", not probs, "topicHints 3 场景／18 词" if not probs else "；".join(probs[:4]))
    return items


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    items = run()
    ok = all(i["ok"] for i in items)
    if "--json" in argv:
        print(json.dumps({"ok": ok, "checks": items}, ensure_ascii=False, indent=1))
    else:
        print("=== 澄清闸登记表 ↔ 触发词 对账（C20） ===")
        for i in items:
            print("  %-6s %s  %s" % (i["id"], "OK  " if i["ok"] else "FAIL", i["detail"]))
        print("结论：%s" % ("绿" if ok else "红"))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
