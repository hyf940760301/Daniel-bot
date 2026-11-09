#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stdout_contract_check.py —— `--json` 时 stdout **恰好一个 JSON 文档** 的契约检查（TICKET-150）。

**要解决的问题**（总监 2026-10-15 裁决 · 比退出码更严重）：一条命令失败时若在 stdout 先打了
"结果信封"、再打一份"错误信封"，上层（模型/宿主）**解析第一个文档就当成功**，错误被静默吞掉。

**判据（严格，不只靠 json.loads）**：用 `json.JSONDecoder().raw_decode` 从 stdout 逐段吃 JSON：
  · `--json` 模式：**文档数恰好 1，且吃掉这一个之后剩余全是空白**；
  · 非 `--json` 模式：stdout **不含** JSON 信封（人读文本走 stdout，进度与错误走 stderr）。
`json.loads` 对"一个文档 + 尾随日志行"报错、对"两个文档"也报错，无法区分"几个"；
`raw_decode` 能数清楚，这正是本检查要的判据。

用法
  python3 data/daniel-cli/stdout_contract_check.py                 # 在线只读：跑成功／用户错误／需确认／内部错误四类路径
  python3 data/daniel-cli/stdout_contract_check.py --audit-source   # 离线：静态审计"先出结果再报错"的同函数路径
  python3 data/daniel-cli/stdout_contract_check.py --self-test      # 离线：判据自检（含"两个文档"反例）

退出码：0＝全部合规；1＝有违例（当缺陷处理）；2＝取数/环境失败（**不得当通过**）。
纪律：不触发任何写（需确认类只做干跑）、不打印凭据、内部错误路径用**临时夹具目录**离线构造。
"""
import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                     # data/daniel-cli
CLI = os.path.join(HERE, "bin", "daniel")
PKG = os.path.join(HERE, "daniel_cli")
REAL_TOOLS = None                                                # 惰性定位


# ─────────────────────────── 判据 ───────────────────────────
def doc_count(text):
    """**数** stdout 里有几个 JSON 文档。→ `(文档数, 剩余非空白片段)`。

    从第一个非空白字符起反复 `raw_decode`：吃得下就 +1，吃不下就把余下内容当"剩余"返回。
    `剩余 == ""` 才说明 stdout 里**只有** json 文档（尾随空白允许）。
    """
    dec = json.JSONDecoder()
    i, n = 0, 0
    while i < len(text):
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        if i >= len(text):
            break
        try:
            _obj, end = dec.raw_decode(text, i)
        except ValueError:
            return n, text[i:i + 120]
        n += 1
        i = end
    return n, ""


def single_doc_ok(text):
    """`--json` 模式的判据：恰好一个 JSON 文档 ＋ 其余全空白。→ (是否合规, 说明)。"""
    n, rest = doc_count(text)
    if n == 1 and rest == "":
        return True, "stdout 恰好 1 个 JSON 文档（无尾随内容）"
    if n == 1:
        return False, "stdout 有 1 个 JSON 文档，但**尾随了非 JSON 内容**：%r" % rest
    if n == 0:
        return False, "stdout 里没有 JSON 文档（%s）" % (("剩余：%r" % rest) if rest else "只有空白")
    return False, "stdout 里有 **%d 个 JSON 文档**（应恰好 1 个）" % n


def clean_stdout_ok(text):
    """非 `--json` 模式的判据：stdout 不该出现 JSON 信封。→ (是否合规, 说明)。"""
    n, rest = doc_count(text)
    if n == 0:
        return True, "stdout 无 JSON 信封（人读文本／空）"
    return False, "非 --json 模式的 stdout 里出现了 %d 个 JSON 文档" % n


# ─────────────────────────── 用例（全部只读／干跑）───────────────────────────
def stub_tools(script, body):
    """造一个临时能力目录：`daniel_client.py` 原样拷入 ＋ 指定仪器换成桩（用于离线构造内部错误）。"""
    d = tempfile.mkdtemp(prefix="daniel-stdout-fixture-")
    shutil.copy(os.path.join(tools_dir(), "daniel_client.py"), os.path.join(d, "daniel_client.py"))
    with open(os.path.join(d, script), "w", encoding="utf-8") as fh:
        fh.write(body)
    return d


def empty_tools():
    """只有 daniel_client.py、没有仪器的目录（触发"能力脚本缺失"＝内部错误，且不联网）。"""
    d = tempfile.mkdtemp(prefix="daniel-stdout-empty-")
    shutil.copy(os.path.join(tools_dir(), "daniel_client.py"), os.path.join(d, "daniel_client.py"))
    return d


def tools_dir():
    global REAL_TOOLS
    if REAL_TOOLS:
        return REAL_TOOLS
    env = os.environ.get("DANIEL_CLI_TOOLS")
    cands = [env] if env else []
    up = ROOT
    for _ in range(6):
        cands.append(os.path.join(up, ".kol-tools"))
        nxt = os.path.dirname(up)
        if nxt == up:
            break
        up = nxt
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "daniel_client.py")):
            REAL_TOOLS = os.path.abspath(c)
            return REAL_TOOLS
    raise SystemExit("找不到能力目录（.kol-tools）；可用 DANIEL_CLI_TOOLS 指定")


#: 桩仪器：在 stdout 打一个 JSON 文档后以 1 退出（复刻"仪器失败"现场）
STUB_FAIL = """import json, sys
print(json.dumps({"ok": True, "from": "stub"}, ensure_ascii=False))
sys.stderr.write("桩仪器：模拟内部故障\\n")
sys.exit(1)
"""


def cases(brand, job):
    """→ [(名字, argv, 期望退出码, 环境变量, 期望错误种类或 None, 只对人读模式断言吗)]"""
    return [
        ("成功·只读（品牌清单）", ["brands", "list", "--limit", "3"], 0, None, None, False),
        ("成功·读链信封（intel actions）",
         ["intel", "actions", "--brand", brand, "--limit", "3"], 0, None, None, False),
        ("用户错误·参数越界（page 0）",
         ["mentions", "results", "--brand", brand, "--job", job, "--page", "0"], 2, None, "usage", False),
        ("用户错误·缺必填参数", ["lists", "by-brand"], 2, None, "usage", False),
        ("用户错误·参数类型非法", ["lists", "items", "--list-id", "not-a-number"], 2, None, "usage", False),
        ("需确认·写操作干跑（零写）",
         ["lists", "create", "--brand", brand, "--name", "自检占位-勿建"], 3, None, None, False),
        ("内部错误·仪器非零退出（离线桩）",
         ["search", "job-status", "--job", "stub"], 1, ("STUB", "daniel_search.py"), "internal", False),
        ("内部错误·能力脚本缺失（离线）",
         ["mentions", "jobs", "--brand", brand], 1, ("EMPTY", None), "internal", False),
    ]


def run(argv, extra_env=None):
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    p = subprocess.run([sys.executable, CLI] + list(argv), capture_output=True, text=True,
                       timeout=1800, env=env)
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(description="`--json` 时 stdout 恰好一个 JSON 文档的契约检查（只读）")
    ap.add_argument("--brand", default="3690002", help="品牌编号（默认 3690002）")
    ap.add_argument("--job", default="d8e9b6fb-fd51-4b52-be82-2ae8a423b789",
                    help="提及任务编号（默认 Euhomy 的实测任务；仅用于参数越界用例，不会真取结果）")
    ap.add_argument("--audit-source", action="store_true", help="离线：静态审计潜在双文档路径")
    ap.add_argument("--self-test", action="store_true", help="离线：判据自检（含反例）")
    ap.add_argument("--json", action="store_true", help="输出机器可读结论")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if a.audit_source:
        return audit_source()

    rows, gaps, envfail = [], [], False
    for name, cargv, want_rc, fixture, want_kind, _ in cases(a.brand, a.job):
        extra = None
        if fixture:
            kind, script = fixture
            extra = {"DANIEL_CLI_TOOLS": stub_tools(script, STUB_FAIL) if kind == "STUB"
                     else empty_tools()}
        pj = run(list(cargv) + ["--json"], extra)
        ph = run(list(cargv), extra)
        okj, whyj = single_doc_ok(pj.stdout)
        okh, whyh = clean_stdout_ok(ph.stdout)
        kind_got = None
        try:
            kind_got = (json.loads(pj.stdout) or {}).get("error", {}).get("kind")
        except ValueError:
            pass
        ok = (pj.returncode == want_rc and okj and okh
              and (want_kind is None or kind_got == want_kind))
        if pj.returncode != want_rc:
            envfail = True
        if not ok:
            gaps.append(name)
        rows.append({"用例": name, "命令": " ".join(cargv), "期望退出码": want_rc,
                     "JSON模式退出码": pj.returncode, "人读模式退出码": ph.returncode,
                     "JSON模式文档数": doc_count(pj.stdout)[0], "JSON模式结论": whyj,
                     "人读模式结论": whyh, "错误种类": kind_got, "期望错误种类": want_kind,
                     "结论": "合规" if ok else "违例"})
    if a.json:
        print(json.dumps({"案例": rows, "违例": gaps}, ensure_ascii=False, indent=1))
    else:
        print("stdout 契约检查（`--json` 时恰好一个 JSON 文档）")
        for r in rows:
            print("\n【%s】%s" % (r["用例"], r["结论"]))
            print("   命令：%s" % r["命令"])
            print("   退出码：JSON %s ／ 人读 %s（期望 %s） ｜ 错误种类：%s（期望 %s）"
                  % (r["JSON模式退出码"], r["人读模式退出码"], r["期望退出码"],
                     r["错误种类"], r["期望错误种类"]))
            print("   JSON 模式：%s" % r["JSON模式结论"])
            print("   人读模式：%s" % r["人读模式结论"])
        print("\n结论：%s" % ("全部合规" if not gaps else "有违例：%s" % "、".join(gaps)))
    return 1 if gaps else 0


# ─────────────────────────── 静态审计（离线）───────────────────────────
EMIT_NAMES = ("emit", "emit_raw", "result", "error")


def _emit_lines(fn):
    out = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in EMIT_NAMES:
            out.append((node.lineno, node.func.attr))
    return sorted(out)


def scan_source(src, rel="<内存>"):
    """扫一份源码，返回 `{"双文档高危": [...], "出结果后raise": [...], "stdout直写": [...]}`。

    判据（顺序关系，不看语义）：
      · 双文档高危：同一函数里 **先** 出结果（emit／emit_raw／result）**后** 调 error；
      · 出结果后 raise：同一函数里先出结果、之后又有 raise（异常被上层接住时会再打一份错误文档）；
      · stdout 直写：`print(...)` 且没有显式指向 stderr 的点。
    """
    double_doc, raise_after, prints = [], [], []
    tree = ast.parse(src)
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        emits = _emit_lines(fn)
        raises = sorted(n.lineno for n in ast.walk(fn) if isinstance(n, ast.Raise))
        for el, ename in emits:
            if ename == "error":
                before = [e for e in emits if e[0] < el and e[1] != "error"]
                if before:
                    double_doc.append({"文件": rel, "函数": fn.name, "先出结果行": before[-1][0],
                                       "先出结果的调用": before[-1][1], "错误出口行": el})
                continue
            later = [r for r in raises if r > el]
            if later:
                raise_after.append({"文件": rel, "函数": fn.name, "出结果行": el, "调用": ename,
                                    "之后 raise 行": later[0]})
    for i, line in enumerate(src.splitlines(), 1):
        st = line.strip()
        if not st.startswith("print("):
            continue
        if any(t in st for t in ("stderr", "self.err", "emitter.err")):
            continue                                      # 明确打到 stderr：不算污染 stdout
        prints.append({"文件": rel, "行": i, "代码": st[:100]})
    return {"双文档高危": double_doc, "出结果后raise": raise_after, "stdout直写": prints}


def audit_files(paths):
    out = {"双文档高危": [], "出结果后raise": [], "stdout直写": []}
    for path in paths:
        rel = os.path.relpath(path, ROOT)
        for k, v in scan_source(open(path, encoding="utf-8").read(), rel).items():
            out[k] += v
    return out


def audit_source():
    """离线静态审计：把 CLI 全部实现按"顺序关系"扫一遍，给出可能吐两个文档的清单。

    为什么要静态审计：双文档只出现在"已经打过一个文档、之后又打了错误文档"这个顺序上，
    只跑几条用例覆盖不全；顺带把"直接往 stdout 打字"的点也列出来人工判读。
    """
    files = [os.path.join(PKG, f) for f in ("cli.py", "runtime.py")]
    for sub in ("commands", "playbook"):
        d = os.path.join(PKG, sub)
        files += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".py")]
    found = audit_files(files)
    print("静态审计（只读，不联网）：扫 %d 个实现文件" % len(files))
    print("\n① 出结果之后又调 error 的位置（**双文档高危**）：")
    print("   无" if not found["双文档高危"] else "")
    for f in found["双文档高危"]:
        print("   · %s::%s ｜ 第 %d 行 %s → 第 %d 行 error" % (f["文件"], f["函数"], f["先出结果行"],
                                                              f["先出结果的调用"], f["错误出口行"]))
    print("\n② 出结果之后又 raise 的位置（异常若被上层接住，会再打一份错误文档）：")
    print("   无" if not found["出结果后raise"] else "")
    for f in found["出结果后raise"]:
        print("   · %s::%s ｜ 第 %d 行 %s → 第 %d 行 raise" % (f["文件"], f["函数"], f["出结果行"],
                                                              f["调用"], f["之后 raise 行"]))
    print("\n③ 直接往 stdout 打字的点（`--json` 模式下需自行保证不打文本）：")
    print("   无" if not found["stdout直写"] else "")
    for p in found["stdout直写"]:
        print("   · %s:%d ｜ %s" % (p["文件"], p["行"], p["代码"]))
    print("\n说明：①/②里的位置不一定都是缺陷 —— 若 emit 与错误出口分处互斥分支"
          "（例如 `if emitter.json_mode: … else: …`），就只会出一个文档；"
          "在线那一轮（不带 --audit-source）用真命令把这些路径跑一遍。")
    return 0


# ─────────────────────────── 判据自检（离线）───────────────────────────
def self_test():
    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    one = '{"ok": true, "data": [1, 2]}\n'
    two = '{"ok": true}\n{"ok": false}\n'
    one_tail = '{"ok": true}\n· 提示：这是日志行\n'
    ck("判据：恰好一个文档 → 合规", single_doc_ok(one) == (True, "stdout 恰好 1 个 JSON 文档（无尾随内容）"),
       str(single_doc_ok(one)))
    ck("判据：一个文档 + 尾随空白 → 合规", single_doc_ok(one + "\n\n  \n")[0])
    ck("反例：两个文档 → 违例", (not single_doc_ok(two)[0]) and "2 个 JSON 文档" in single_doc_ok(two)[1],
       single_doc_ok(two)[1])
    ck("反例：一个文档 + 尾随日志行 → 违例",
       (not single_doc_ok(one_tail)[0]) and "尾随" in single_doc_ok(one_tail)[1], single_doc_ok(one_tail)[1])
    ck("反例：stdout 无文档（空白）→ 违例", not single_doc_ok("   \n")[0], single_doc_ok("   \n")[1])
    ck("反例：stdout 是纯文本 → 违例", not single_doc_ok("jobs n=3\njobId 1\n")[0])
    ck("人读模式判据：纯文本 → 合规", clean_stdout_ok("jobs n=3\njobId …\n")[0])
    ck("人读模式反例：出现 JSON 信封 → 违例", not clean_stdout_ok(one)[0])
    ck("数文档：尾部空白不计", doc_count('{"a":1}  \n') == (1, ""))
    ck("数文档：三个文档数得清", doc_count('{"a":1}{"b":2}[3]')[0] == 3)
    ck("判据：非 JSON 开头 → 0 文档 + 剩余片段", doc_count("错误：缺参数")[0] == 0)
    ck("CLI 入口存在", os.path.isfile(CLI), CLI)

    # 正控：审计判据必须能抓出"先出结果、后打错误文档"的旧形状（就是修掉的那个缺陷）
    bad = ("def f(ctx):\n"
           "    ctx.emit_raw(ok=False, exit_code=1, data={})\n"
           "    ctx.emitter.error('失败', 1, 'internal')\n")
    ck("正控：审计抓得出「出结果后又 error」", len(scan_source(bad)["双文档高危"]) == 1,
       str(scan_source(bad)["双文档高危"]))
    good = ("def f(ctx):\n"
            "    if ctx.json_mode:\n"
            "        ctx.emitter.error('失败', 2, 'usage')\n"
            "    else:\n"
            "        print('错误：失败', file=ctx.emitter.err)\n")
    ck("真阴性：互斥分支（要么出结果要么报错）→ 不误报",
       not scan_source(good)["双文档高危"] and not scan_source(good)["出结果后raise"]
       and not scan_source(good)["stdout直写"], str(scan_source(good)))
    ck("正控：审计抓得出「出结果后又 raise」",
       len(scan_source("def g(ctx):\n    ctx.emit(data={})\n    raise ValueError('x')\n")["出结果后raise"]) == 1)

    passed = sum(1 for _, c, _ in checks if c)
    for name, cond, detail in checks:
        print("%s %s%s" % ("PASS" if cond else "FAIL", name, (" · " + detail) if detail else ""))
    print("self-test: %d/%d" % (passed, len(checks)))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
