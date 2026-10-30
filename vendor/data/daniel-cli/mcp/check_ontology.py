#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_ontology.py —— 语义登记表的静态门禁（C19 系）。

为什么不塞进 capability_gate.py
------------------------------
`capability_gate.py` 是 900 多行的既有总门禁，改它风险大、也难回退。
按「新增优先」原则，语义登记表的检查单独成文件，作为 C19 系列的落点；
将来若要合并，把这个文件的函数搬进去即可，判定口径不变。

四项断言
--------
  C19-a  索引版本 ≡ 清单版本（`_ONTOLOGY.json.corpus_version == _MANIFEST.json.corpus_version`）
  C19-b  正文引用的每个登记项 id 都能在索引里命中（引用不能指向空气）
  C19-c  每条登记项 `owner` 非空、`status != draft`（无主的登记项不许进交付路径）
  C19-e  带 `surfaces` 的指标必须声明 `external_only`（对外只认一个口径）

用法
----
  python3 mcp/check_ontology.py            # 0＝绿，2＝红
  python3 mcp/check_ontology.py --json
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
CORPUS = os.path.join(HERE, "corpus")
INDEX = os.path.join(CORPUS, "_ONTOLOGY.json")
MANIFEST = os.path.join(CORPUS, "_MANIFEST.json")
IDREF = re.compile(r"\b((?:metric|criterion|expr|concept|constraint)\.[A-Za-z0-9_.\-]+)")


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _referenced_ids():
    """扫 8 束语料正文，收集被引用的登记项 id → {id: [出现位置]}"""
    hits = {}
    for root, _dirs, files in os.walk(CORPUS):
        for name in files:
            if not name.endswith(".md"):
                continue
            p = os.path.join(root, name)
            rel = os.path.relpath(p, CORPUS)
            try:
                text = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for m in IDREF.finditer(text):
                hits.setdefault(m.group(1), []).append(rel)
    return hits


def run():
    items = []

    def add(cid, ok, detail):
        items.append({"id": cid, "ok": ok, "detail": detail})

    if not os.path.isfile(INDEX):
        add("C19-a", False, "找不到索引：%s（先跑 check_corpus_sync.py --sync 或重建索引）" % INDEX)
        return items
    doc = _load(INDEX)
    entries = doc.get("entries", [])
    by_id = {e.get("id"): e for e in entries}

    # C19-a 版本一致
    ver_ok, ver_detail = False, "缺 _MANIFEST.json"
    if os.path.isfile(MANIFEST):
        man = _load(MANIFEST)
        a, b = doc.get("corpus_version"), man.get("corpus_version")
        ver_ok = a == b
        ver_detail = "索引 %s ｜ 清单 %s" % (a, b)
    add("C19-a", ver_ok, ver_detail)

    # C19-b 引用可解析
    refs = _referenced_ids()
    missing = sorted(i for i in refs if i not in by_id)
    add("C19-b", not missing,
        "引用 %d 个 id，未命中 %d 个%s" % (len(refs), len(missing),
                                    ("：" + "、".join(missing[:5])) if missing else ""))

    # C19-c owner 与状态
    badc = [e.get("id") for e in entries
            if not str(e.get("owner") or "").strip() or str(e.get("status") or "") == "draft"]
    add("C19-c", not badc,
        "登记项 %d 条，无 owner 或 draft %d 条%s" % (len(entries), len(badc),
                                             ("：" + "、".join(badc[:5])) if badc else ""))

    # C19-e 对外唯一口径
    bade = []
    for e in entries:
        raw = e.get("raw") or ""
        if "surfaces:" in raw and "external_only:" not in raw:
            bade.append(e.get("id"))
    add("C19-e", not bade,
        "带多口径面的指标 %d 条，未声明对外唯一 %d 条%s"
        % (sum(1 for e in entries if "surfaces:" in (e.get("raw") or "")), len(bade),
           ("：" + "、".join(bade[:5])) if bade else ""))
    return items


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    items = run()
    ok = all(i["ok"] for i in items)
    if "--json" in argv:
        print(json.dumps({"ok": ok, "checks": items}, ensure_ascii=False, indent=1))
    else:
        print("=== 语义登记表门禁（C19） ===")
        for i in items:
            print("  %-6s %s  %s" % (i["id"], "OK  " if i["ok"] else "FAIL", i["detail"]))
        print("结论：%s" % ("绿" if ok else "红"))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
