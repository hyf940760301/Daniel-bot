#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clarify_parity_check.py —— 澄清闸的**三级对拍门禁**（L1 语义／L2 键序／L3 渲染哈希）。

为什么需要它
------------
`clarify.js`（旧实现）与 `daniel clarify plan/ask`（新实现）必须**逐字节同输出**，
否则插件 golden 会红、用户也会看到两份不一样的清单。本脚本把这条判据做成常设门禁：
改任一边（登记表文案、触发词、CLI 逻辑）都会红。

三级判据
--------
  L1 语义等价：`data` 的键集合、每个值、数组顺序都相同（键序不敏感）
  L2 键序一致：递归比较"每一层的键序列"（含 8 种嵌套项），键序变了 L2 红
  L3 渲染哈希：`sha256(紧凑 JSON)` —— 与插件 golden 的 `sha256(JSON.stringify(out))` 同口径

用法
----
  python3 clarify_parity_check.py --capture      # 用 JS 冻结期望（**只在切插件之前用一次**）
  python3 clarify_parity_check.py --check        # 只读：跑 CLI 60 次，与期望比（门禁）
  python3 clarify_parity_check.py --accept-text-change --reason "..."   # 窄门：文案变更后更新期望

退出码：0＝全绿；2＝有差异或数据缺失。
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))          # data/daniel-cli
WORKSPACE = os.path.dirname(os.path.dirname(HERE))
CLI = os.path.join(HERE, "bin", "daniel")
FIXTURE = os.path.join(HERE, "contracts", "_fixtures", "clarify-needs.jsonl")
EXPECTED = os.path.join(HERE, "contracts", "_fixtures", "clarify-needs.expected.json")
JS_DEFAULT = os.path.join(WORKSPACE, "daniel-plugins", "a-v2", "lib", "clarify.js")
SCHEMA = "clarify.parity.v1"
COMMANDS = ("plan", "ask")


def _sha(obj):
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sig(v):
    """键序签名：对象＝键序列（递归），数组＝逐元素签名，标量＝val。"""
    if isinstance(v, dict):
        return ["obj", [[k, _sig(x)] for k, x in v.items()]]
    if isinstance(v, list):
        return ["arr", [_sig(x) for x in v]]
    return ["val"]


def _first_path(a, b, path="$"):
    """找两个签名第一处不同，返回可读路径（给差异报告用）。"""
    if type(a) is not type(b):
        return path
    if isinstance(a, list):
        if a and a[0] == "obj":
            ka = [k for k, _ in a[1]]
            kb = [k for k, _ in b[1]]
            if ka != kb:
                for i in range(min(len(ka), len(kb))):
                    if ka[i] != kb[i]:
                        return "%s.%s（键序：%s vs %s）" % (path, ka[i], ka[i], kb[i])
                return "%s（键数 %d vs %d：%s vs %s）" % (path, len(ka), len(kb), ka, kb)
            for (k, va), (_, vb) in zip(a[1], b[1]):
                p = _first_path(va, vb, path + "." + str(k))
                if p:
                    return p
            return None
        if a and a[0] == "arr":
            if len(a[1]) != len(b[1]):
                return "%s（数组长度 %d vs %d）" % (path, len(a[1]), len(b[1]))
            for i, (va, vb) in enumerate(zip(a[1], b[1])):
                p = _first_path(va, vb, "%s[%d]" % (path, i))
                if p:
                    return p
            return None
    return None


def _first_value_path(a, b, path="$"):
    """值差异的第一处路径（L1 用；标量也能报出位置）。"""
    if type(a) is not type(b):
        return path
    if isinstance(a, dict):
        for k in a:
            if k not in b:
                return "%s.%s" % (path, k)
            p = _first_value_path(a[k], b[k], "%s.%s" % (path, k))
            if p:
                return p
        for k in b:
            if k not in a:
                return "%s.%s" % (path, k)
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return path
        for i, (x, y) in enumerate(zip(a, b)):
            p = _first_value_path(x, y, "%s[%d]" % (path, i))
            if p:
                return p
        return None
    return None if a == b else path


def load_fixture(path=FIXTURE):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ─────────────────────────── capture（JS 冻结期望）───────────────────────────
_RUNNER = r"""
import { pathToFileURL } from 'node:url'
import { readFileSync } from 'node:fs'
const [jsPath, fixturePath] = process.argv.slice(-2)
const m = await import(pathToFileURL(jsPath).href)
const rows = readFileSync(fixturePath, 'utf8').split('\n').filter(Boolean).map(JSON.parse)
const out = {}
for (const r of rows) {
  const empty = String(r.need || '').trim() === ''
  const one = {}
  for (const cmd of ['plan', 'ask']) {
    if (empty) { one[cmd] = { kind: 'usage' }; continue }
    if (cmd === 'plan') {
      const d = Object.assign({}, m.clarifyPlan(r.need, r.topic ?? undefined),
                              { 选择面: m.screenPlan(r.need).选择面 })
      one[cmd] = { kind: 'ok', data: d }
    } else {
      one[cmd] = { kind: 'ok', data: m.screenPlan(r.need, r.reply ?? undefined, r.round ?? undefined) }
    }
  }
  out[r.id] = one
}
process.stdout.write(JSON.stringify(out))
"""


def capture(js_path=JS_DEFAULT):
    if not os.path.isfile(js_path):
        raise SystemExit("找不到 JS 实现：%s（--capture 只在切插件之前用一次）" % js_path)
    rows = load_fixture()
    tmp = tempfile.mkdtemp(prefix="clarify-js-")
    try:
        runner = os.path.join(tmp, "runner.mjs")
        with open(runner, "w", encoding="utf-8") as fh:
            fh.write(_RUNNER)
        p = subprocess.run(["node", runner, js_path, FIXTURE],
                           capture_output=True, text=True, timeout=180)
        if p.returncode != 0:
            raise SystemExit("JS 冻结失败（退出码 %d）：%s" % (p.returncode, (p.stderr or "")[:400]))
        got = json.loads(p.stdout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    cases = {}
    for r in rows:
        per = {}
        for cmd in COMMANDS:
            item = got[r["id"]][cmd]
            if item["kind"] != "ok":
                per[cmd] = {"kind": "usage"}
            else:
                data = item["data"]
                per[cmd] = {"kind": "ok", "sha256": _sha(data), "sig": _sig(data), "data": data}
        cases[r["id"]] = per

    with open(js_path, "rb") as fh:
        js_sha = hashlib.sha256(fh.read()).hexdigest()
    doc = {
        "schema": SCHEMA,
        "source_js": os.path.relpath(js_path, WORKSPACE),
        "source_js_sha256": js_sha,
        "fixture": os.path.relpath(FIXTURE, WORKSPACE),
        "case_count": len(rows),
        "note": "期望由切插件前的 JS 实现冻结；--check 只与这份期望比（不再依赖 JS）",
        "changes": [],
        "cases": cases,
    }
    with open(EXPECTED, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("已冻结期望：%s（%d 条样本 × 2 条命令；JS sha %s…）"
          % (os.path.relpath(EXPECTED, WORKSPACE), len(rows), js_sha[:12]))
    return 0


# ─────────────────────────── check（CLI 对期望）───────────────────────────
def _run_cli(row, cmd, home):
    argv = [sys.executable, CLI, "clarify", cmd, "--need", row["need"], "--json"]
    if cmd == "plan" and row.get("topic"):
        argv += ["--topic", str(row["topic"])]
    if cmd == "ask":
        if row.get("reply") is not None:
            argv += ["--reply", str(row["reply"])]
        if row.get("round") is not None:
            argv += ["--round", str(row["round"])]
    env = dict(os.environ)
    env["DANIEL_HOME"] = home
    env["DANIEL_NO_OPEN"] = "1"
    p = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=120)
    try:
        doc = json.loads(p.stdout)
    except ValueError:
        return {"kind": "bad_stdout", "exit": p.returncode,
                "detail": (p.stdout or "")[:160] or (p.stderr or "")[-160:]}
    if doc.get("ok"):
        return {"kind": "ok", "data": doc.get("data"), "exit": p.returncode}
    err = doc.get("error") or {}
    return {"kind": err.get("kind") or "error", "exit": p.returncode, "message": err.get("message", "")}


def check(expected_path=EXPECTED):
    if not os.path.isfile(expected_path):
        raise SystemExit("找不到期望文件：%s（先跑 --capture）" % expected_path)
    with open(expected_path, encoding="utf-8") as fh:
        exp = json.load(fh)
    rows = load_fixture()
    tmp_home = tempfile.mkdtemp(prefix="clarify-home-")

    total = 0
    l1 = l2 = l3 = 0
    fails = []
    shapes = {"plan": set(), "ask": set()}
    try:
        for r in rows:
            rid = r["id"]
            for cmd in COMMANDS:
                total += 1
                want = exp["cases"][rid][cmd]
                got = _run_cli(r, cmd, tmp_home)
                if want["kind"] != "ok":
                    shapes[cmd].add("__" + want["kind"])
                if want["kind"] != got["kind"]:
                    fails.append({"id": rid, "cmd": cmd, "level": "L1",
                                  "detail": "类型 %s vs %s（exit=%s）" % (want["kind"], got["kind"], got.get("exit"))})
                    continue
                if want["kind"] != "ok":
                    if got.get("exit") != 2:
                        fails.append({"id": rid, "cmd": cmd, "level": "L1",
                                      "detail": "usage 期望退出码 2，实际 %s" % got.get("exit")})
                    else:
                        l1 += 1; l2 += 1; l3 += 1
                    continue
                data = got["data"]
                shapes[cmd].add(_sha(data))
                if data != want["data"]:
                    fails.append({"id": rid, "cmd": cmd, "level": "L1",
                                  "detail": "值不同（首处：%s）" % (_first_value_path(want["data"], data) or "?")})
                    continue
                l1 += 1
                if _sig(data) != want["sig"]:
                    fails.append({"id": rid, "cmd": cmd, "level": "L2",
                                  "detail": "键序不同（首处：%s）" % (_first_path(want["sig"], _sig(data)) or "?")})
                    continue
                l2 += 1
                if _sha(data) != want["sha256"]:
                    fails.append({"id": rid, "cmd": cmd, "level": "L3", "detail": "渲染哈希不同"})
                    continue
                l3 += 1
    finally:
        shutil.rmtree(tmp_home, ignore_errors=True)

    report = {
        "schema": SCHEMA,
        "cases": len(rows),
        "comparisons": total,
        "L1_pass": l1, "L2_pass": l2, "L3_pass": l3,
        "independent": {"plan": len(shapes["plan"]), "ask": len(shapes["ask"]),
                        "total": len(shapes["plan"]) + len(shapes["ask"])},
        "failures": fails,
        "ok": l3 == total,
    }
    return report


def check_text(report, reason, expected_path=EXPECTED):
    """窄门：确认是"文案变更"（L1 之外无结构差异）后，用 CLI 输出重录期望。"""
    structural = [f for f in report["failures"] if f["level"] in ("L2",)]
    if structural:
        print("拒绝重录：存在 L2（键序）差异，这不是文案变更：%s" % structural[:3])
        return 2
    with open(expected_path, encoding="utf-8") as fh:
        exp = json.load(fh)
    rows = load_fixture()
    tmp_home = tempfile.mkdtemp(prefix="clarify-home-")
    changed = []
    try:
        for r in rows:
            for cmd in COMMANDS:
                got = _run_cli(r, cmd, tmp_home)
                key = r["id"]
                old = exp["cases"][key][cmd]
                if got["kind"] == "ok":
                    new = {"kind": "ok", "sha256": _sha(got["data"]), "sig": _sig(got["data"]), "data": got["data"]}
                else:
                    new = {"kind": got["kind"]}
                if new != old:
                    changed.append({"case": key, "cmd": cmd,
                                    "old_sha": old.get("sha256"), "new_sha": new.get("sha256")})
                    exp["cases"][key][cmd] = new
    finally:
        shutil.rmtree(tmp_home, ignore_errors=True)
    exp.setdefault("changes", []).append({"reason": reason, "changed": len(changed),
                                          "items": changed[:20]})
    with open(expected_path, "w", encoding="utf-8") as fh:
        json.dump(exp, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("已按文案窄门重录：%d 处变化（理由：%s）" % (len(changed), reason))
    return 0


def print_report(rep):
    print("=== 澄清闸三级对拍（L1 语义 / L2 键序 / L3 渲染哈希）===")
    print("样本 %d 条 × 2 条命令 = **%d 次比对**" % (rep["cases"], rep["comparisons"]))
    print("L1 通过 %d ／ L2 通过 %d ／ L3 通过 %d" % (rep["L1_pass"], rep["L2_pass"], rep["L3_pass"]))
    print("独立形态：plan %d ＋ ask %d ＝ **%d**（ask 侧同形样本按 1 个形态计）"
          % (rep["independent"]["plan"], rep["independent"]["ask"], rep["independent"]["total"]))
    if rep["failures"]:
        print("差异 %d 条：" % len(rep["failures"]))
        for f in rep["failures"][:20]:
            print("  [%s] %s/%s：%s" % (f["level"], f["id"], f["cmd"], f["detail"]))
    print("结论：%s" % ("绿 —— 0 差异" if rep["ok"] else "红 —— 见上"))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(description="澄清闸三级对拍门禁")
    ap.add_argument("--capture", action="store_true", help="用 JS 冻结期望（切插件之前用一次）")
    ap.add_argument("--check", action="store_true", help="只读：跑 CLI 与期望比")
    ap.add_argument("--accept-text-change", action="store_true", help="窄门：文案变更后重录期望")
    ap.add_argument("--reason", default="", help="与 --accept-text-change 配套的理由")
    ap.add_argument("--js", default=JS_DEFAULT, help="JS 实现路径（仅 --capture 用）")
    ap.add_argument("--fixture", default=FIXTURE)
    ap.add_argument("--expected", default=EXPECTED)
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    a = ap.parse_args(argv)

    if a.capture:
        return capture(a.js)
    rep = check(a.expected)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print_report(rep)
    if a.accept_text_change:
        if rep["ok"]:
            print("无需重录：已经 0 差异")
            return 0
        return check_text(rep, a.reason or "（未写理由）", a.expected)
    return 0 if rep["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
