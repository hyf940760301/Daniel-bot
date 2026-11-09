#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨宿主一致性比对器（TICKET-153 Part A 第 3 项 · 本票核心产出）。

要证的那句话
------------
「在 DSH 里跑得通」不等于「在别的宿主里也跑得通」。所以本工具拿**两份交付物**做机械比对：
同一份契约在**直接 CLI 路径**（等价 DSH 侧的调用方式）与**经 MCP server 路径**
（Cursor 侧将来走的同一条路）各跑一次，产出的两个产物必须**同字段、同排序、同条数**。

比对口径（三条都是机械判据，不是"看起来一样"）
--------------------------------------------
  ① **同字段**：同一层级对象的字段**名字集合**必须相同（A 独有／B 独有分别列出）；
  ② **同排序**：共同字段的**键序列**必须相同（字典的插入顺序就是排序，键序不同即报）；
  ③ **同条数**：每个数组的**长度**必须相同（逐下标递归比对元素）。

在此基础上再比**取值**（第 4 层），并且**不比字符串格式差异**：
  · 每次运行必然不同的**落点字符串**按"运行根目录"归一化后再比
    （`--norm-a / --norm-b` 指定；不给则自动从产物里的 `运行.沙箱目录` 推）；
  · 只差首尾空白的字符串算相等（计入"仅格式差异"）；
  · 时间戳一类**天生逐次不同**的字段，用 `--volatile <字段名>` 显式声明后跳过取值比对，
    跳过的次数会打印出来 —— **不做隐式忽略**。

用法
----
  python3 compare_hosts.py --a A.json --b B.json \
      --label-a 直接CLI --label-b 经MCP --norm-a /tmp/x/a --norm-b /tmp/x/b \
      --volatile 生成时间
  python3 compare_hosts.py --a A.json --b B.json --strict     # 不做任何归一化／忽略，必须差异 0
  python3 compare_hosts.py --a A.json --b B.json --json       # 机器可读

退出码：0 差异为 0；2 存在差异；1 工具自身出错。
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))

ROOT_PLACEHOLDER = "<RUN_ROOT>"
SANDBOX_PLACEHOLDER = "daniel-playbook-<SANDBOX>"

#: 归一化规则②：契约引擎自建临时沙箱的目录名（`daniel-playbook-<8 位随机>`）。
#: 为什么单列一条：没指定 `DANIEL_PLAYBOOK_SANDBOX` 时，落点根（`$TMPDIR`）两侧相同，
#: 差异只剩这一段随机后缀 —— 只按"运行根目录"归一化会把它留在字符串里，
#: 于是"差异 0"永远达不成（总监 2026-10-14 实测缺口）。
SANDBOX_NAME_RE = re.compile(r"daniel-playbook-[A-Za-z0-9_]{4,16}")

#: "仪表值"字段名：只拿来**提示**（"差异全部落在耗时上"），**绝不自动忽略** ——
#: 忽略必须由 `--volatile` 显式声明并打印出来。
TIMING_KEYS = ("耗时毫秒", "耗时", "elapsedMs", "seconds", "耗时(秒)")


# ─────────────────────────── 行号索引 ───────────────────────────
def index_lines(text):
    """扫一遍 JSON 文本，建立 `路径 → 行号` 索引（用于"逐条列出时给出字段名与行号"）。

    路径元素：对象字段用字符串，数组元素用整数下标。行号是**该字段名/值出现的那一行**。
    """
    idx = {}
    i, n, line = 0, len(text), 1
    stack = []                                   # [{kind, path, key, next}]

    def note(p):
        idx.setdefault(tuple(p), line)

    def advance(cur):
        if cur is None:
            return
        if cur["kind"] == "arr":
            cur["next"] += 1
        else:
            cur["key"] = None

    while i < n:
        ch = text[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch in " \t\r,:":
            i += 1
            continue
        if ch == '"':
            start_line = line
            j = i + 1
            while j < n:
                c = text[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "\n":
                    line += 1
                if c == '"':
                    break
                j += 1
            raw = text[i:j + 1]
            try:
                val = json.loads(raw)
            except ValueError:
                val = raw[1:-1]
            k = j + 1
            while k < n and text[k] in " \t\r\n":
                k += 1
            cur = stack[-1] if stack else None
            base = tuple(cur["path"]) if cur else ()
            if k < n and text[k] == ":":
                idx.setdefault(base + (val,), start_line)
                if cur is not None:
                    cur["key"] = val
            else:
                note((base + (cur["key"],)) if cur and cur["kind"] == "obj"
                     else (base + (cur["next"],)) if cur else ())
                advance(cur)
            i = j + 1
            continue
        if ch in "{[":
            cur = stack[-1] if stack else None
            if cur is None:
                p = ()
            elif cur["kind"] == "obj":
                p = tuple(cur["path"]) + (cur["key"],)
            else:
                p = tuple(cur["path"]) + (cur["next"],)
            note(p)
            stack.append({"kind": "obj" if ch == "{" else "arr", "path": p,
                          "key": None, "next": 0})
            advance(cur)
            i += 1
            continue
        if ch in "}]":
            if stack:
                stack.pop()
            i += 1
            continue
        j = i
        while j < n and text[j] not in ",}] \t\r\n":
            j += 1
        cur = stack[-1] if stack else None
        if cur is not None:
            note(tuple(cur["path"]) + ((cur["key"],) if cur["kind"] == "obj"
                                       else (cur["next"],)))
        advance(cur)
        i = j
    return idx


def load(path):
    text = io.open(path, encoding="utf-8").read()
    return json.loads(text), text, index_lines(text)


# ─────────────────────────── 取值归一化 ───────────────────────────
class Identity:
    """严格模式用的空归一化器（原样返回，全部命中数恒为 0）。"""

    enabled = True

    def __init__(self, sandbox=True):
        self.use_sandbox = bool(sandbox)
        self.stats = {"root": 0, "sandbox": 0}

    def __call__(self, val):
        return val


class Normalizer:
    """把"逐次必然不同"的落点字符串换成占位符再比（**只动落点，不动业务取值**）。

    两条规则，都只在**字符串取值**上生效，字段名与结构一概不动：
      ① 运行根目录（`--norm-a/--norm-b` 或从产物 `运行.沙箱目录` 自动推）→ `<RUN_ROOT>`；
      ② 契约引擎自建临时沙箱名 `daniel-playbook-<随机>` → `daniel-playbook-<SANDBOX>`
         （`--no-sandbox-normalize` 可关掉，`--strict` 两条都关）。
    """

    def __init__(self, prefix, sandbox=True):
        self.prefix = (prefix or "").rstrip(os.sep) if prefix else ""
        self.use_sandbox = bool(sandbox)
        self.stats = {"root": 0, "sandbox": 0}

    def __call__(self, val):
        if not isinstance(val, str):
            return val
        out = val
        if self.prefix and self.prefix in out:
            self.stats["root"] += out.count(self.prefix)
            out = out.replace(self.prefix, ROOT_PLACEHOLDER)
        if self.use_sandbox:
            out, n = SANDBOX_NAME_RE.subn(SANDBOX_PLACEHOLDER, out)
            self.stats["sandbox"] += n
        return out


def _autodetect_root(obj, given):
    if given:
        return given
    if isinstance(obj, dict):
        sb = ((obj.get("运行") or {}).get("沙箱目录")) if isinstance(obj.get("运行"), dict) else None
        if isinstance(sb, str) and sb:
            return os.path.dirname(sb.rstrip(os.sep)) or sb
    return None


# ─────────────────────────── 比对 ───────────────────────────
def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _fmt(v, limit=220):
    if isinstance(v, (dict, list)):
        s = json.dumps(v, ensure_ascii=False)
    elif v is None:
        s = "null"
    elif isinstance(v, bool):
        s = "true" if v else "false"
    else:
        s = str(v)
    return s if len(s) <= limit else s[:limit] + "…（共 %d 字）" % len(s)


class Result:
    def __init__(self):
        self.diffs = []
        self.objects = 0
        self.fields = 0
        self.arrays = 0
        self.values = 0
        self.volatile_skipped = []
        self.format_only = 0
        self.order_mismatch = 0
        self.missing = 0
        self.extra = 0
        self.count_mismatch = 0

    @property
    def structural(self):
        return self.order_mismatch + self.missing + self.extra + self.count_mismatch

    @property
    def value_diffs(self):
        return len([d for d in self.diffs if d["kind"] == "取值不同"
                    or d["kind"] == "类型不同"])

    @property
    def total(self):
        return len(self.diffs)


def compare(va, vb, path, res, volatile, norm_a, norm_b, la, lb, idx_a, idx_b):
    if isinstance(va, dict) and isinstance(vb, dict):
        res.objects += 1
        ka, kb = list(va.keys()), list(vb.keys())
        res.fields += len(ka)
        missing = [k for k in ka if k not in vb]
        extra = [k for k in kb if k not in va]
        for k in missing:
            res.missing += 1
            res.diffs.append({"kind": "A 独有字段", "path": path + [k],
                              "lineA": idx_a.get(tuple(path + [k])),
                              "lineB": None, "a": _fmt(va[k]), "b": "（缺）"})
        for k in extra:
            res.extra += 1
            res.diffs.append({"kind": "B 独有字段", "path": path + [k],
                              "lineA": None,
                              "lineB": idx_b.get(tuple(path + [k])),
                              "a": "（缺）", "b": _fmt(vb[k])})
        common_a = [k for k in ka if k in vb]
        common_b = [k for k in kb if k in va]
        if common_a != common_b:
            res.order_mismatch += 1
            res.diffs.append({"kind": "字段顺序不同", "path": path,
                              "lineA": idx_a.get(tuple(path)),
                              "lineB": idx_b.get(tuple(path)),
                              "a": " → ".join(common_a), "b": " → ".join(common_b)})
        for k in common_a:
            compare(va[k], vb[k], path + [k], res, volatile, norm_a, norm_b,
                    la, lb, idx_a, idx_b)
        return
    if isinstance(va, list) and isinstance(vb, list):
        res.arrays += 1
        if len(va) != len(vb):
            res.count_mismatch += 1
            res.diffs.append({"kind": "数组条数不同", "path": path,
                              "lineA": idx_a.get(tuple(path)),
                              "lineB": idx_b.get(tuple(path)),
                              "a": "%d 条" % len(va), "b": "%d 条" % len(vb)})
        for i in range(min(len(va), len(vb))):
            compare(va[i], vb[i], path + [i], res, volatile, norm_a, norm_b,
                    la, lb, idx_a, idx_b)
        return
    if (isinstance(va, dict) and isinstance(vb, list)) or (isinstance(va, list)
                                                           and isinstance(vb, dict)):
        res.diffs.append({"kind": "类型不同", "path": path,
                          "lineA": idx_a.get(tuple(path)), "lineB": idx_b.get(tuple(path)),
                          "a": _fmt(va), "b": _fmt(vb)})
        return

    key = path[-1] if path else None
    if isinstance(key, str) and key in volatile:
        res.volatile_skipped.append(".".join(str(p) for p in path))
        return
    res.values += 1
    a2, b2 = norm_a(va), norm_b(vb)
    if a2 == b2:
        return
    if _is_num(a2) and _is_num(b2) and float(a2) == float(b2):
        return
    if isinstance(a2, str) and isinstance(b2, str) and a2.strip() == b2.strip():
        res.format_only += 1
        return
    res.diffs.append({"kind": "取值不同", "path": path,
                      "lineA": idx_a.get(tuple(path)), "lineB": idx_b.get(tuple(path)),
                      "a": _fmt(a2), "b": _fmt(b2)})


def _path_str(path):
    out = ""
    for p in path:
        if isinstance(p, int):
            out += "[%d]" % p
        else:
            out += ("." if out else "") + str(p)
    return out or "（根）"


# ─────────────────────────── 入口 ───────────────────────────
RULES = (
    ("root", "运行根目录 → <RUN_ROOT>", ROOT_PLACEHOLDER),
    ("sandbox", "契约引擎临时沙箱名 daniel-playbook-<随机> → daniel-playbook-<SANDBOX>",
     SANDBOX_PLACEHOLDER),
)


def run(args, out=None):
    out = out or sys.stdout
    a, ta, ia = load(args.a)
    b, tb, ib = load(args.b)
    use_sandbox = not getattr(args, "no_sandbox_normalize", False)
    if args.strict:
        na, nb = Identity(False), Identity(False)
        ra = rb = None
    else:
        ra = _autodetect_root(a, args.norm_a)
        rb = _autodetect_root(b, args.norm_b)
        na, nb = Normalizer(ra, use_sandbox), Normalizer(rb, use_sandbox)
    volatile = set(args.volatile or [])
    res = Result()
    compare(a, b, [], res, volatile, na, nb, args.label_a, args.label_b, ia, ib)

    rule_rows = []
    for key, desc, ph in RULES:
        if key == "sandbox" and (args.strict or not use_sandbox):
            rule_rows.append((desc, ph, "已关闭", "已关闭"))
        else:
            rule_rows.append((desc, ph, "%d 处" % na.stats[key], "%d 处" % nb.stats[key]))

    print("=== 跨宿主一致性比对（同字段／同排序／同条数）===", file=out)
    print("A（%s）：%s" % (args.label_a, os.path.abspath(args.a)), file=out)
    print("B（%s）：%s" % (args.label_b, os.path.abspath(args.b)), file=out)
    if args.strict:
        print("口径：严格模式 —— 不做任何落点归一化、不跳过任何字段", file=out)
    else:
        print("口径：落点根来源：%s"
              % ("两侧均自动从产物「运行.沙箱目录」推得"
                 if not args.norm_a and not args.norm_b
                 else ("命令行 --norm-a/--norm-b 指定"
                       + ("（其一自动推得）" if not (args.norm_a and args.norm_b) else ""))),
              file=out)
        print("口径：已归一化的易变片段（只作用在字符串取值上；字段名与结构一概不动）", file=out)
        for desc, ph, ha, hb in rule_rows:
            print("      规则｜%s ｜ A %s ｜ B %s" % (desc, ha, hb), file=out)
        if ra or rb:
            print("      具体落点根：A=%s ／ B=%s" % (ra or "（无）", rb or "（无）"), file=out)
        print("口径：易变键（只跳过取值比对，仍比字段名与顺序）：%s"
              % ("、".join(sorted(volatile)) if volatile else "无"), file=out)
    print("结构层：字段集合差异 %d（A 独有 %d／B 独有 %d）｜ 字段顺序差异 %d ｜ 数组条数差异 %d"
          % (res.missing + res.extra, res.missing, res.extra,
             res.order_mismatch, res.count_mismatch), file=out)
    print("  比对规模：对象 %d 个 ｜ 字段 %d 个 ｜ 数组 %d 个 ｜ 取值 %d 个（易变键跳过 %d 处）"
          % (res.objects, res.fields, res.arrays, res.values, len(res.volatile_skipped)), file=out)
    print("取值层：差异 %d（仅首尾空白差异 %d 处，按口径不算差异）"
          % (res.value_diffs, res.format_only), file=out)
    if res.diffs:
        print("--- 差异逐条（字段名／位置与行号／两侧取值）---", file=out)
        for n, d in enumerate(res.diffs, 1):
            print("[%02d] %s ｜ 字段：%s ｜ 行号：A=%s B=%s"
                  % (n, d["kind"], _path_str(d["path"]),
                     d["lineA"] if d["lineA"] else "—", d["lineB"] if d["lineB"] else "—"),
                  file=out)
            print("     A（%s）：%s" % (args.label_a, d["a"]), file=out)
            print("     B（%s）：%s" % (args.label_b, d["b"]), file=out)
    verdict = ("差异 0" if res.total == 0
               else "差异 %d 条（结构层 %d 条 ＋ 取值层 %d 条）"
                    % (res.total, res.structural, res.value_diffs))
    # 只差"耗时"这类仪表值时的提示（**只提示，不隐式忽略**）：真实网络读的耗时逐次必然不同，
    # 但它不是业务取值 —— 说清楚该怎么显式排除，比让人对着两条差异猜要好。
    timing_only = bool(res.diffs) and all(
        d["path"] and str(d["path"][-1]) in TIMING_KEYS for d in res.diffs)
    if timing_only:
        hint_keys = sorted({str(d["path"][-1]) for d in res.diffs})
        print("提示：%d 条差异**全部**落在耗时类字段（%s）—— 这类值逐次必然不同（真实网络读尤其明显），"
              "按口径不隐式忽略；确认只是耗时的话，加 `--volatile %s` 显式声明后复核"
              % (res.total, "／".join(hint_keys), " --volatile ".join(hint_keys)), file=out)
    print("--- 结论 ---", file=out)
    print("总差异：%s" % verdict, file=out)
    print("同字段：%s ｜ 同排序：%s ｜ 同条数：%s"
          % ("是" if res.missing == 0 and res.extra == 0 else "否",
             "是" if res.order_mismatch == 0 else "否",
             "是" if res.count_mismatch == 0 else "否"), file=out)
    print("判定：%s" % ("两份产物同字段、同排序、同条数，差异 0"
                       if res.total == 0 else "存在差异，见上方逐条明细"), file=out)
    payload = {
        "a": os.path.abspath(args.a), "b": os.path.abspath(args.b),
        "labelA": args.label_a, "labelB": args.label_b,
        "strict": bool(args.strict),
        "normalize": {
            "rootA": ra, "rootB": rb,
            "rules": [{"rule": k, "placeholder": ph,
                       "hitsA": na.stats[k], "hitsB": nb.stats[k],
                       "enabled": not (args.strict or (k == "sandbox" and not use_sandbox))}
                      for k, _desc, ph in RULES],
        },
        "volatile": sorted(volatile),
        "scale": {"objects": res.objects, "fields": res.fields, "arrays": res.arrays,
                  "values": res.values, "volatileSkipped": len(res.volatile_skipped)},
        "structural": {"fieldSet": res.missing + res.extra, "onlyA": res.missing,
                       "onlyB": res.extra, "order": res.order_mismatch,
                       "count": res.count_mismatch},
        "valueDiffs": res.value_diffs, "formatOnly": res.format_only,
        "diffCount": res.total,
        "diffs": [dict(d, path=_path_str(d["path"])) for d in res.diffs],
        "sameFields": res.missing == 0 and res.extra == 0,
        "sameOrder": res.order_mismatch == 0,
        "sameCount": res.count_mismatch == 0,
        "verdict": verdict,
    }
    if args.out:
        io.open(args.out, "w", encoding="utf-8").write(
            json.dumps(payload, ensure_ascii=False, indent=1))
    return payload


def self_test():
    """自检：正控（相同产物必须差异 0）＋ 退化输入（字段缺／多／顺序／条数／取值／坏文件）。"""
    import tempfile
    checks = []

    def ok(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    class A:
        strict = False
        no_sandbox_normalize = False
        label_a, label_b = "A", "B"
        out = None
        volatile = []

    def mk(doc, name, d):
        p = os.path.join(d, name)
        io.open(p, "w", encoding="utf-8").write(json.dumps(doc, ensure_ascii=False, indent=1))
        return p

    with tempfile.TemporaryDirectory() as d:
        base = {"甲": 1, "乙": [{"序号": 1}, {"序号": 2}], "丙": {"丁": "x"}}
        p1 = mk(base, "a.json", d)
        p2 = mk(dict(base), "b.json", d)
        a = A()
        a.a, a.b, a.norm_a, a.norm_b = p1, p2, None, None
        r = run(a, out=io.StringIO())
        ok("正控：完全相同的两份产物 → 差异 0", r["diffCount"] == 0, r["verdict"])

        g = A()
        g.a, g.b, g.norm_a, g.norm_b = p1, mk({"甲": 1, "乙": [{"序号": 1}], "丙": {"丁": "x"}},
                                              "c.json", d), None, None
        r = run(g, out=io.StringIO())
        ok("[degenerate] 数组少一条 → 报「数组条数不同」",
           r["structural"]["count"] == 1 and "数组条数不同" in [x["kind"] for x in r["diffs"]],
           r["verdict"])

        g = A()
        g.a, g.b, g.norm_a, g.norm_b = p1, mk({"甲": 1, "乙": [{"序号": 1}, {"序号": 2}]},
                                              "d.json", d), None, None
        r = run(g, out=io.StringIO())
        ok("[degenerate] B 少一个字段 → 报「A 独有字段」", r["structural"]["onlyA"] == 1,
           r["verdict"])

        g = A()
        g.a, g.b, g.norm_a, g.norm_b = p1, mk({"甲": 1, "乙": [{"序号": 1}, {"序号": 2}],
                                               "丙": {"丁": "x"}, "戊": 9}, "e.json", d), None, None
        r = run(g, out=io.StringIO())
        ok("[degenerate] B 多一个字段 → 报「B 独有字段」", r["structural"]["onlyB"] == 1,
           r["verdict"])

        g = A()
        g.a, g.b, g.norm_a, g.norm_b = p1, mk({"乙": [{"序号": 1}, {"序号": 2}], "甲": 1,
                                               "丙": {"丁": "x"}}, "f.json", d), None, None
        r = run(g, out=io.StringIO())
        ok("[degenerate] 字段顺序不同 → 报「字段顺序不同」（同字段也不放过）",
           r["structural"]["order"] == 1 and r["sameFields"], r["verdict"])

        g = A()
        g.a, g.b, g.norm_a, g.norm_b = p1, mk({"甲": 2, "乙": [{"序号": 1}, {"序号": 2}],
                                               "丙": {"丁": "x"}}, "g.json", d), None, None
        r = run(g, out=io.StringIO())
        ok("[degenerate] 取值不同 → 报「取值不同」并给出两侧取值",
           r["valueDiffs"] == 1 and r["diffs"][0]["a"] == "1" and r["diffs"][0]["b"] == "2",
           r["verdict"])

        g = A()
        g.a, g.b, g.norm_a, g.norm_b = p1, mk({"甲": 1.0, "乙": [{"序号": 1}, {"序号": 2}],
                                               "丙": {"丁": "x"}}, "h.json", d), None, None
        r = run(g, out=io.StringIO())
        ok("[degenerate] 1 与 1.0 视为同值（数字比数值，不比字面格式）", r["diffCount"] == 0)

        g = A()
        g.a, g.b, g.norm_a, g.norm_b = p1, mk({"甲": 1, "乙": [{"序号": 1}, {"序号": 2}],
                                               "丙": {"丁": " x "}}, "i.json", d), None, None
        r = run(g, out=io.StringIO())
        ok("[degenerate] 仅首尾空白差异 → 不算差异（只计入「仅格式差异」）",
           r["diffCount"] == 0 and r["formatOnly"] == 1)

        # 落点归一化：两侧路径不同，归一化后必须差异 0
        doc_a = {"运行": {"沙箱目录": "/tmp/xh/a/sandbox"}, "交付件": {"路径": "/tmp/xh/a/sandbox/骨架.json"}}
        doc_b = {"运行": {"沙箱目录": "/tmp/xh/b/sandbox"}, "交付件": {"路径": "/tmp/xh/b/sandbox/骨架.json"}}
        pa, pb = mk(doc_a, "j1.json", d), mk(doc_b, "j2.json", d)
        g = A()
        g.a, g.b, g.norm_a, g.norm_b = pa, pb, "/tmp/xh/a", "/tmp/xh/b"
        r = run(g, out=io.StringIO())
        rl = {x["rule"]: x for x in r["normalize"]["rules"]}
        ok("正控：落点不同的两份产物 → 归一化后差异 0", r["diffCount"] == 0,
           "规则①命中 A %d 处／B %d 处" % (rl["root"]["hitsA"], rl["root"]["hitsB"]))
        g.strict = True
        r = run(g, out=io.StringIO())
        ok("正控：严格模式下同一对产物 → 报出落点差异（归一化确实在起作用）",
           r["diffCount"] == 2, r["verdict"])

        # 易变键只跳取值、仍比字段
        g = A()
        g.a, g.b, g.norm_a, g.norm_b = mk({"生成时间": "2026-10-14 21:11:49"}, "k1.json", d), \
            mk({"生成时间": "2026-10-14 21:12:00"}, "k2.json", d), None, None
        g.volatile = ["生成时间"]
        r = run(g, out=io.StringIO())
        ok("正控：--volatile 声明的字段只跳取值比对 → 差异 0 且打印跳过处数",
           r["diffCount"] == 0 and r["scale"]["volatileSkipped"] == 1)
        g.volatile = []
        r = run(g, out=io.StringIO())
        ok("[degenerate] 不声明易变键时时间戳差异必须如实报出（不隐式忽略）",
           r["diffCount"] == 1)

        # 行号
        g = A()
        g.a, g.b, g.norm_a, g.norm_b = p1, mk({"甲": 2, "乙": [{"序号": 1}, {"序号": 2}],
                                               "丙": {"丁": "x"}}, "l.json", d), None, None
        r = run(g, out=io.StringIO())
        ok("正控：差异条目带行号", r["diffs"][0]["lineA"] == 2 and r["diffs"][0]["lineB"] == 2,
           "A 第 %s 行／B 第 %s 行" % (r["diffs"][0]["lineA"], r["diffs"][0]["lineB"]))

        # 坏文件
        bad = os.path.join(d, "bad.json")
        io.open(bad, "w", encoding="utf-8").write("{不是 JSON")
        g = A()
        g.a, g.b, g.norm_a, g.norm_b = bad, p1, None, None
        try:
            run(g, out=io.StringIO())
            ok("[degenerate] 非法 JSON 输入 → 明确报错（不静默通过）", False)
        except ValueError as e:
            ok("[degenerate] 非法 JSON 输入 → 明确报错（不静默通过）", True, str(e)[:60])
        g = A()
        g.a, g.b, g.norm_a, g.norm_b = os.path.join(d, "nope.json"), p1, None, None
        try:
            run(g, out=io.StringIO())
            ok("[degenerate] 文件不存在 → 明确报错", False)
        except IOError:
            ok("[degenerate] 文件不存在 → 明确报错", True)

        # 耗时类差异的"提示"（只提示、不隐式忽略）
        buf = io.StringIO()
        g = A()
        g.a, g.b, g.norm_a, g.norm_b = mk({"运行": {"耗时毫秒": 100}}, "t1.json", d), \
            mk({"运行": {"耗时毫秒": 250}}, "t2.json", d), None, None
        r = run(g, out=buf)
        ok("正控：差异全部落在耗时字段 → 报差异并给「可用 --volatile 显式声明」的提示",
           r["diffCount"] == 1 and "--volatile 耗时毫秒" in buf.getvalue(), r["verdict"])
        buf2 = io.StringIO()
        g = A()
        g.a, g.b, g.norm_a, g.norm_b = mk({"运行": {"耗时毫秒": 100, "样本模式": True}}, "t3.json", d), \
            mk({"运行": {"耗时毫秒": 250, "样本模式": False}}, "t4.json", d), None, None
        r = run(g, out=buf2)
        ok("真阴性：差异不止耗时 → 不出现那条提示（免得把真差异也说成'只是耗时'）",
           r["diffCount"] == 2 and "--volatile 耗时毫秒" not in buf2.getvalue(), r["verdict"])

    # ── 真实产物回归对：Cursor 经 MCP（2026-10-14 用户在宿主内实测）× DSH 直接 CLI ──
    # 这两个文件就是当时落盘的原件（sha256 记在同目录 README.md），不重新生成、不改一个字节。
    fx = os.path.join(HERE, "_fixtures", "cross-host")
    fa = os.path.join(fx, "cursor-mcp-run.json")
    fb = os.path.join(fx, "dsh-cli-run.json")
    if not (os.path.isfile(fa) and os.path.isfile(fb)):
        ok("正控 回归对：真实产物两份夹具存在", False, "缺 %s" % fx)
    else:
        g = A()
        g.a, g.b, g.norm_a, g.norm_b = fa, fb, None, None
        g.label_a, g.label_b = "Cursor 经 MCP", "DSH 直接 CLI"
        r = run(g, out=io.StringIO())
        ok("正控 回归对（Cursor 经 MCP × DSH 直接 CLI）：同字段／同排序／同条数 → 差异 0",
           r["diffCount"] == 0 and r["sameFields"] and r["sameOrder"] and r["sameCount"],
           "结构层 %d 条 ｜ 取值层 %d 条 ｜ 规模 %d 字段/%d 取值 ｜ %s"
           % (sum(r["structural"].values()), r["valueDiffs"], r["scale"]["fields"],
              r["scale"]["values"], r["verdict"]))
        rules = {x["rule"]: x for x in r["normalize"]["rules"]}
        ok("正控 回归对：临时沙箱名归一化确实生效（两侧各命中 ≥1 处）",
           rules["sandbox"]["hitsA"] >= 1 and rules["sandbox"]["hitsB"] >= 1,
           "规则②命中 A %d 处／B %d 处" % (rules["sandbox"]["hitsA"],
                                          rules["sandbox"]["hitsB"]))
        gs = A()
        gs.a, gs.b, gs.norm_a, gs.norm_b = fa, fb, None, None
        gs.strict = True
        r2 = run(gs, out=io.StringIO())
        ok("真阴性 回归对：关掉归一化（--strict）后必须报出那 3 处沙箱落点差异（证明 0 不是掩盖出来的）",
           r2["structural"]["fieldSet"] == 0 and r2["structural"]["order"] == 0
           and r2["structural"]["count"] == 0 and r2["valueDiffs"] == 3,
           r2["verdict"])
        gns = A()
        gns.a, gns.b, gns.norm_a, gns.norm_b = fa, fb, None, None
        gns.no_sandbox_normalize = True
        r3 = run(gns, out=io.StringIO())
        ok("真阴性 回归对：只关「沙箱名」这条规则（保留根归一化）→ 仍必须报出 3 处",
           r3["valueDiffs"] == 3, r3["verdict"])

        # 真阴性：人为改一个字段值 → 必须报出
        with tempfile.TemporaryDirectory() as d:
            mut = json.load(io.open(fb, encoding="utf-8"))
            mut["结论"]["摘要"] = mut["结论"]["摘要"].replace("门禁 5 道", "门禁 4 道")
            mp = mk(mut, "mut-value.json", d)
            gv = A()
            gv.a, gv.b, gv.norm_a, gv.norm_b = fa, mp, None, None
            r4 = run(gv, out=io.StringIO())
            ok("真阴性 回归对：人为改一个字段值 → 必须报出 1 条取值差异",
               r4["valueDiffs"] == 1 and r4["diffs"][0]["path"] == "结论.摘要",
               "字段 %s ｜ %s" % (r4["diffs"][0]["path"] if r4["diffs"] else "—", r4["verdict"]))
            # 真阴性：人为删一个字段 → 必须报出结构差异
            mut2 = json.load(io.open(fb, encoding="utf-8"))
            mut2.pop("失败模式", None)
            mp2 = mk(mut2, "mut-struct.json", d)
            gs2 = A()
            gs2.a, gs2.b, gs2.norm_a, gs2.norm_b = fa, mp2, None, None
            r5 = run(gs2, out=io.StringIO())
            ok("真阴性 回归对：人为删一个字段 → 必须报出结构差异（A 独有 1）",
               r5["structural"]["onlyA"] == 1, r5["verdict"])
            # 真阴性：人为调换字段顺序 → 必须报出
            mut3 = json.load(io.open(fb, encoding="utf-8"))
            ks = list(mut3.keys())
            ks[0], ks[1] = ks[1], ks[0]
            mp3 = mk({k: mut3[k] for k in ks}, "mut-order.json", d)
            go = A()
            go.a, go.b, go.norm_a, go.norm_b = fa, mp3, None, None
            r6 = run(go, out=io.StringIO())
            ok("真阴性 回归对：人为调换字段顺序 → 必须报出字段顺序差异",
               r6["structural"]["order"] == 1 and r6["sameFields"], r6["verdict"])

    passed = sum(1 for _, v, _ in checks if v)
    print("=== compare_hosts 自检 ===")
    for name, good, detail in checks:
        print(" %s %s%s" % ("[通过]" if good else "[未过]", name,
                            ("  ｜ " + detail) if detail else ""))
    print("自检 %d/%d" % (passed, len(checks)))
    return 0 if passed == len(checks) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="跨宿主交付物一致性比对（TICKET-153 Part A）")
    ap.add_argument("--a", help="A 侧产物（JSON 文件）")
    ap.add_argument("--b", help="B 侧产物（JSON 文件）")
    ap.add_argument("--label-a", default="A", help="A 侧标签（例如「直接 CLI」）")
    ap.add_argument("--label-b", default="B", help="B 侧标签（例如「经 MCP server」）")
    ap.add_argument("--norm-a", default=None, help="A 侧要归一化的运行根目录")
    ap.add_argument("--norm-b", default=None, help="B 侧要归一化的运行根目录")
    ap.add_argument("--volatile", action="append", default=[],
                    help="逐次必然不同的字段名（只跳过取值比对，仍比字段名与顺序）；可多次")
    ap.add_argument("--strict", action="store_true", help="严格模式：不归一化、不跳过任何字段")
    ap.add_argument("--no-sandbox-normalize", dest="no_sandbox_normalize", action="store_true",
                    help="只关掉「临时沙箱名」这条归一化规则（保留运行根归一化）")
    ap.add_argument("--json", action="store_true", help="机器可读结果")
    ap.add_argument("--out", default=None, help="把比对报告写到这个文件（JSON）")
    ap.add_argument("--self-test", action="store_true", help="自检（正控＋退化输入）")
    a = ap.parse_args(argv)

    if a.self_test:
        return self_test()
    if not a.a or not a.b:
        ap.error("需要 --a 与 --b（两份产物）")
    payload = run(a)
    if a.json:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
    return 0 if payload["diffCount"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
