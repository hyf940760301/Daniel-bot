#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_corpus_sync.py —— 「包内语料 vs 源束」漂移门禁（TICKET-159 · 总监红线）。

为什么要这道门禁
----------------
用户口径：**语料必须包含在整个 MCP 里**，别的电脑注册 MCP server 后自动获得，无需再装任何东西。
为此我们把 8 束语料**随包分发**到 `data/daniel-cli/mcp/corpus/`。

代价是：同一份语料在仓库里有**两份物理副本**
  源束（切分产物）：`.agents/skills/kol-*/`
  包内（分发物）  ：`data/daniel-cli/mcp/corpus/kol-*/`

两份副本天然就是"第二真源"的形状。如果包内副本会**静默漂移**，那么"新机器装完就有完整语料"
这条能力会在某次语料更新后**悄悄退化成旧版**，而且没有任何人会发现 —— 比功能没做更糟。
所以本文件把漂移变成**会红的断言**，而不是靠一次性的 sha256 对账。

三件事
------
  ① **门禁**（默认）：重算包内语料**逐文件 sha256**，与 `_MANIFEST.json` 里记录的
     「源束路径 ＋ 逐文件 sha256」比对；再（源束在本机时）与源束本体逐文件比对。
     任何差异＝红，并打印**哪个文件、期望哪个哈希、实际哪个哈希**。
  ② **重生成**（`--sync`）：**复用 TICKET-148 的语料束切分器**（不另写导出器）把源文件重新
     切进包内目录，然后重写 `_MANIFEST.json`；写完立刻自检一次，不绿即非零退出。
  ③ **自检**（`--self-test`）：正控＋六类退化输入，**全部在临时副本上跑**（不动活仓）。

用法
----
  python3 data/daniel-cli/mcp/check_corpus_sync.py                # 门禁（0＝绿，2＝红）
  python3 data/daniel-cli/mcp/check_corpus_sync.py --json
  python3 data/daniel-cli/mcp/check_corpus_sync.py --sync         # 源束更新后：重导出＋重写清单
  python3 data/daniel-cli/mcp/check_corpus_sync.py --write-manifest   # 只重写清单（先断言两侧相等）
  python3 data/daniel-cli/mcp/check_corpus_sync.py --self-test

边界（刻意为之，别当缺陷）
--------------------------
  · 源束**不在本机**时（分发物上的正常情形），"与源束比对"一项记 `跳过（源束不在本机）`，
    **不算失败** —— 否则这道门禁在分发物上永远红、等于没有。
  · 本文件**不做任何活仓计数当判据**：包内文件数、命令数这类数字只作信息行打印，
    判据只有"哈希是否相等"。
  · 不联网、不写除 `mcp/corpus/` 之外的任何路径、不碰 `~/.agents/skills/`。
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))        # 工作区根
PKG_ROOT = os.path.dirname(HERE)                                      # data/daniel-cli

if PKG_ROOT not in sys.path:
    sys.path.insert(0, PKG_ROOT)

from daniel_cli import corpus                                         # noqa: E402

MANIFEST_REL = os.path.join("data", "daniel-cli", "mcp", "corpus", corpus.MANIFEST_NAME)
SOURCE_BUNDLES_REL = ".agents/skills"
SPLITTER_REL = "docs/product/daniel-copilot/_impl/TICKET-148-语料束切分器.py"
SOURCE_DOC_REL = "docs/marketing/skills/kol-intelligence.md"

#: 脱敏状态（**必须如实标注**：状态不明说就等于谎报 —— 与「跳过 ≠ 通过 ≠ 失败」同一条纪律）。
#: 本期包内语料是源束的**逐字副本**，没有做任何脱敏，所以是 `false`。
#: 用户 2026-10-15 裁决：产品级 CLI **目前仅内部推广**，语料库**不存在敏感内容、默认全部语料都通过**
#: ⇒ **不做脱敏、不建零命中门禁**（TICKET-164 已降级为"只出清单"）。范围清单见
#: `**飞书《测试与结论》第四节 TC-09 模块**`。将来对外分发时按段二启用脱敏。
REDACTED_KEY = "已脱敏"
REDACT_NOTE_KEY = "脱敏说明"
REDACT_NOTE = ("当前口径（用户 2026-10-15 裁决）：内部推广阶段默认全部语料通过、不做脱敏；"
               "范围清单见 **飞书《测试与结论》第四节 TC-09 模块**")
#: 脱敏工具在清单里的键（将来对外分发、段二启用时填相对路径）。
#: **接线约定**：`python3 <脱敏工具> --in <源束根> --out <输出根>`，退出码 0 ＝ 在输出根下
#: 产出**与源束同布局**的分发版语料（`<域>/…`）。段二用它把源束算成"期望的分发版"再比对。
REDACT_TOOL_KEY = "脱敏工具"
#: 🔴 **顺序不可颠倒**：导出 → 脱敏 → 算分发版哈希 → 漂移校验。
#: 先脱敏后算哈希，清单里记的才是**分发版的指纹**；反过来会记成"未脱敏的指纹"，
#: 脱敏一落地，清单与门禁同时失真（而且没人看得出来）。

#: 生成工具的自报口径（写进清单，供后来人知道"这份语料是谁生成的"）
GENERATOR = ("TICKET-148 语料束切分器（%s）＋ TICKET-159 随包分发（mcp/check_corpus_sync.py）"
             % SPLITTER_REL)


# ─────────────────────────── 基础件 ───────────────────────────
def sha256_file(path):
    with io.open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def tree_hashes(root):
    """目录 → `{相对路径: sha256}`（相对路径用 `/`，跨平台一致）。"""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            out[rel] = sha256_file(full)
    return out


def bundle_digest(hashes):
    h = hashlib.sha256()
    for rel in sorted(hashes):
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(hashes[rel].encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


class Ledger:
    def __init__(self):
        self.items = []

    def add(self, name, ok, detail="", skip=False):
        self.items.append({"name": name, "ok": bool(ok), "skip": bool(skip), "detail": detail})
        mark = "跳过" if skip else ("通过" if ok else "未过")
        print(" [%s] %s%s" % (mark, name, ("  ｜ " + detail) if detail else ""), flush=True)
        return bool(ok)

    @property
    def failed(self):
        return [i for i in self.items if not i["ok"] and not i["skip"]]

    @property
    def passed(self):
        return sum(1 for i in self.items if i["ok"])


def diff_table(expected, actual, limit=12):
    """逐文件差异表：`文件 ｜ 期望 ｜ 实际`（截断到 limit 条，另报总数）。"""
    keys = sorted(set(expected) | set(actual))
    bad = [k for k in keys if expected.get(k) != actual.get(k)]
    rows = []
    for k in bad[:limit]:
        rows.append("      %s ｜ 期望 %s ｜ 实际 %s"
                    % (k, _short(expected.get(k)), _short(actual.get(k))))
    if len(bad) > limit:
        rows.append("      …另有 %d 个文件不一致（只列前 %d 个）" % (len(bad) - limit, limit))
    return bad, rows


def _short(dig):
    if dig is None:
        return "（缺失）"
    if dig == "<缺失>":
        return "（缺失）"
    return dig[:16] + "…"


def _names(bad, limit=4):
    """差异文件名（进台账 detail，便于人一眼看到是哪个文件、也让自检能断言"点名了"）。"""
    if not bad:
        return ""
    head = "、".join(bad[:limit])
    return "：%s%s" % (head, "…" if len(bad) > limit else "")


def _pkg_hashes(root):
    """包内目录 → `{(束,相对文件): sha256}`（排除根清单本身）。"""
    out = {}
    for name in corpus.SKILL_ORDER:
        sdir = os.path.join(root, name)
        if not os.path.isdir(sdir):
            continue
        for rel, dig in tree_hashes(sdir).items():
            out["%s/%s" % (name, rel)] = dig
    return out


# ─────────────────────────── ① 门禁 ───────────────────────────
def _stage_label(doc):
    """当前跑的是哪一段（段一＝逐字复制，段二＝脱敏后）。"""
    return "段二：源束→脱敏→期望分发版" if doc.get(REDACTED_KEY) else "段一：包内 == 源束（逐字）"


def _flatten(src_root, prefix_names=None):
    """源束根 → `{域/相对文件: sha256}`。"""
    out = {}
    for name in (prefix_names or corpus.SKILL_ORDER):
        sdir = os.path.join(src_root, name)
        if not os.path.isdir(sdir):
            out["%s/（束目录缺失）" % name] = "<缺失>"
            continue
        for rel, dig in tree_hashes(sdir).items():
            out["%s/%s" % (name, rel)] = dig
    return out


def expected_distribution(doc, src_root):
    """「期望的分发版」逐文件哈希 —— **两段式门禁**的核心。

    段一（当前，`已脱敏 == false`）：期望的分发版 ＝ **源束原文**（逐字复制，复制无损是本段要证的）。
    段二（TICKET-164 落地后，`已脱敏 == true`）：期望的分发版 ＝ **源束经同一份脱敏工具处理后的结果**，
      用清单里记的 `脱敏工具` 现场重算再比对（**不比原文** —— 脱敏之后原文与分发版必然不相等，
      写成"必须相等"的单一形态到那时会假红）。

    切换条件：清单 `脱敏工具` 字段填写 ＋ `已脱敏` 置 `true`（两者同时具备才走段二；
    只置 `true` 却没接线 → **红**，因为"宣称脱敏了却没有可复核的脱敏工具"本身就是不实登记）。

    返回 `(哈希表 或 None, 口径说明, 不通过时的理由)`。
    """
    if not doc.get(REDACTED_KEY):
        return (_flatten(src_root), "段一口径：源束原文逐字（已脱敏=false）", None)
    tool_rel = doc.get(REDACT_TOOL_KEY)
    if not tool_rel:
        return (None, "", "清单宣称 已脱敏=true，但没有 `%s` 字段：无法复核脱敏结果。"
                          "TICKET-164 落地时按约定接线"
                          "（`python3 <脱敏工具> --in <源束根> --out <输出根>`）" % REDACT_TOOL_KEY)
    tool = os.path.join(ROOT, tool_rel)
    if not os.path.isfile(tool):
        return (None, "", "清单记的脱敏工具不存在：%s" % tool)
    out_root = tempfile.mkdtemp(prefix="corpus-expected-dist-")
    try:
        p = subprocess.run([sys.executable or "python3", tool, "--in", src_root, "--out", out_root],
                           cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if p.returncode != 0:
            return (None, "", "脱敏工具失败（退出码 %d）：%s"
                    % (p.returncode, (p.stderr or "").strip()[:200]))
        return (_flatten(out_root), "段二口径：源束经 %s 脱敏后" % tool_rel, None)
    finally:
        shutil.rmtree(out_root, ignore_errors=True)


def gate(led, pkg_root, src_root, manifest_path):
    """跑全部断言。返回 `(ok, 信息)`。"""
    info = {"pkgRoot": pkg_root, "sourceRoot": src_root, "manifest": manifest_path,
            "bundles": [], "tables": []}

    # S1 清单存在且结构齐备（含"必须记源"这条）
    if not os.path.isfile(manifest_path):
        led.add("清单存在：%s" % manifest_path, False, "找不到随包语料清单")
        return False, info
    try:
        doc = json.loads(io.open(manifest_path, encoding="utf-8").read())
    except ValueError as e:
        led.add("清单可解析：%s" % manifest_path, False, "JSON 解析失败：%s" % e)
        return False, info
    led.add("清单可解析：%s" % manifest_path, True, "%d 字节" % os.path.getsize(manifest_path))

    for key in ("corpus_version", "source", "source_sha256", "generated_at", "generated_by",
                "bundles"):
        if not doc.get(key):
            led.add("清单字段齐备：%s" % key, False, "缺字段 %s（清单不完整＝无法追源）" % key)
            return False, info
    led.add("清单字段齐备（版本／源文件／源哈希／生成时间／生成工具／逐束）", True,
            "语料版本 %s ｜ 生成于 %s" % (doc["corpus_version"], doc["generated_at"]))

    bundles = doc["bundles"]
    missing_domains = [n for n in corpus.SKILL_ORDER if n not in bundles]
    led.add("清单覆盖 8 个能力域", not missing_domains,
            "缺：%s" % ("、".join(missing_domains) if missing_domains else "无（8/8）"))

    # S2 逐束：清单字段齐备（源束路径／源束整束 sha256／逐文件 sha256／生成工具）
    field_problems, ver_set = [], set()
    for name in corpus.SKILL_ORDER:
        b = bundles.get(name)
        if not isinstance(b, dict):
            field_problems.append("%s：清单无此束" % name)
            continue
        for key in ("source_bundle", "source_bundle_sha256", "bundle_sha256", "files_sha256",
                    "corpus_version", "generated_at", "generated_by", "bytes", "files", "slices"):
            if not b.get(key) and b.get(key) != 0:
                field_problems.append("%s：缺 %s" % (name, key))
        if b.get("source_bundle") and not str(b["source_bundle"]).endswith(name):
            field_problems.append("%s：source_bundle 指向的不是本束（%s）"
                                  % (name, b["source_bundle"]))
        if b.get("source_bundle_sha256") != b.get("bundle_sha256"):
            field_problems.append("%s：源束整束 sha256 与包内整束 sha256 不等"
                                  "（%s vs %s）——写入时两侧就不一致"
                                  % (name, _short(b.get("source_bundle_sha256")),
                                     _short(b.get("bundle_sha256"))))
        if b.get("corpus_version"):
            ver_set.add(b["corpus_version"])
    led.add("逐束清单记源：源束路径 ＋ 源束整束 sha256 ＋ 逐文件 sha256 ＋ 生成时间 ＋ 生成工具",
            not field_problems,
            "；".join(field_problems[:6]) if field_problems else
            "8 束齐备（无源路径的清单等于自证，故这条是硬判据）")

    # S3 包内逐文件 sha256 ≡ 清单记录
    pkg = _pkg_hashes(pkg_root)
    rec = {}
    for name in corpus.SKILL_ORDER:
        b = bundles.get(name) or {}
        for rel, dig in (b.get("files_sha256") or {}).items():
            rec["%s/%s" % (name, rel)] = dig
    bad, rows = diff_table(rec, pkg)
    led.add("包内语料逐文件 sha256 ≡ 清单记录（差一即红）", not bad,
            "比对 %d 个文件 ｜ 不一致 %d 个%s"
            % (len(set(rec) | set(pkg)), len(bad), _names(bad)))
    for line in rows:
        print(line)
    info["tables"].append({"check": "包内 vs 清单记录", "bad": bad, "rows": rows})

    # S4 「期望的分发版」≡ 包内（**两段式**：按清单的 `已脱敏` 决定比什么）
    if REDACTED_KEY not in doc:
        led.add("脱敏状态已如实标注（清单里有 `%s` 字段）" % REDACTED_KEY, False,
                "缺 `%s` 字段 —— 状态不明说就等于谎报（应填 false 并注明 TICKET-164）"
                % REDACTED_KEY)
    else:
        led.add("脱敏状态已如实标注：%s=%s ｜ %s"
                % (REDACTED_KEY, json.dumps(doc[REDACTED_KEY], ensure_ascii=False),
                   doc.get(REDACT_NOTE_KEY) or "（缺说明）"),
                bool(doc.get(REDACT_NOTE_KEY)),
                "本期包内语料＝源束的逐字副本，未脱敏；%s" % REDACT_NOTE)

    if not os.path.isdir(src_root):
        led.add("「期望的分发版」逐文件 sha256 ≡ 包内（%s）" % _stage_label(doc),
                True,
                "跳过：源束不在本机（分发物上的正常情形；本机可查的部分已由「包内 ≡ 清单记录」覆盖）",
                skip=True)
        info["sourceCompare"] = "跳过（源束不在本机）"
    else:
        expect, how, why = expected_distribution(doc, src_root)
        if expect is None:
            led.add("「期望的分发版」逐文件 sha256 ≡ 包内（%s）" % _stage_label(doc), False,
                    why)
            info["sourceCompare"] = "红：%s" % why
        else:
            bad2, rows2 = diff_table(expect, pkg)
            led.add("「期望的分发版」逐文件 sha256 ≡ 包内（%s）" % _stage_label(doc), not bad2,
                    "%s ｜ 比对 %d 个文件 ｜ 不一致 %d 个%s"
                    % (how, len(set(expect) | set(pkg)), len(bad2), _names(bad2)))
            for line in rows2:
                print(line)
            info["tables"].append({"check": "包内 vs 期望分发版", "bad": bad2, "rows": rows2})
            info["sourceCompare"] = "一致" if not bad2 else "不一致 %d 个文件" % len(bad2)
            info["expectedHow"] = how

    # S5 版本自洽：8 束同一语料版本，且与清单／源文件哈希对得上
    led.add("版本自洽：8 束同一语料版本 ＝ 清单 corpus_version", len(ver_set) == 1
            and list(ver_set)[0] == doc["corpus_version"],
            "束版本集合 %s ｜ 清单 %s" % ("／".join(sorted(ver_set)) or "（空）",
                                       doc["corpus_version"]))

    # S6 每束的 _CORPUS.json 声明的切片文件都真的在包里，且题注一致
    slice_problems = []
    for name in corpus.SKILL_ORDER:
        sdir = os.path.join(pkg_root, name)
        cj_path = os.path.join(sdir, "_CORPUS.json")
        if not os.path.isfile(cj_path):
            slice_problems.append("%s：缺 _CORPUS.json" % name)
            continue
        cj = json.loads(io.open(cj_path, encoding="utf-8").read())
        for sl in cj.get("slices") or []:
            fp = os.path.join(sdir, sl["file"])
            if not os.path.isfile(fp):
                slice_problems.append("%s：切片文件缺失 %s" % (name, sl["file"]))
        if cj.get("source_sha256") != doc.get("source_sha256"):
            slice_problems.append("%s：_CORPUS.json 的源文件 sha256 与清单不一致" % name)
    led.add("切片齐备：每束 _CORPUS.json 声明的切片文件都在包里，且源文件哈希与清单一致",
            not slice_problems, "；".join(slice_problems[:6]) if slice_problems
            else "%d 个切片文件齐备" % doc.get("total_slices", 0))

    # 逐束对账表（人可读）
    print("   --- 逐束对账表（包内 vs 源束 vs 清单）---")
    for name in corpus.SKILL_ORDER:
        b = bundles.get(name) or {}
        got = bundle_digest({k.split("/", 1)[1]: v for k, v in pkg.items()
                             if k.startswith(name + "/")})
        row = {"domain": name, "manifest": b.get("bundle_sha256"), "package": got,
               "source": (bundle_digest(tree_hashes(os.path.join(src_root, name)))
                          if os.path.isdir(os.path.join(src_root, name)) else None),
               "files": len([k for k in pkg if k.startswith(name + "/")]),
               "bytes": b.get("bytes"), "slices": b.get("slices"),
               "version": b.get("corpus_version")}
        info["bundles"].append(row)
        print("   %-20s 版本 %-8s 切片 %2s ｜ 文件 %2s ｜ 整束 %s ｜ 清单 %s ｜ 源束 %s"
              % (name, row["version"], row["slices"], row["files"],
                 _short(row["package"]), _short(row["manifest"]), _short(row["source"])))

    ok = not led.failed
    return ok, info


# ─────────────────────────── ② 重写清单 ───────────────────────────
def build_manifest(pkg_root, src_root, strict=True):
    """从**源束**（本机存在时）构造清单；源束不在本机时退回包内自描述。

    `strict=True` 时要求包内 ≡ 源束，否则拒绝写清单 —— 否则写清单＝把漂移洗白。
    """
    bundles, tot_b, tot_f, tot_s = {}, 0, 0, 0
    ver_set, src_doc, src_doc_sha, src_lines = set(), None, None, None
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    for name in corpus.SKILL_ORDER:
        pdir = os.path.join(pkg_root, name)
        if not os.path.isdir(pdir):
            raise SystemExit("包内缺这一束：%s（先跑 --sync 重导出）" % pdir)
        pkg = tree_hashes(pdir)
        cj = json.loads(io.open(os.path.join(pdir, "_CORPUS.json"), encoding="utf-8").read())
        sdir = os.path.join(src_root, name)
        if os.path.isdir(sdir):
            src = tree_hashes(sdir)
            if strict and src != pkg:
                bad, rows = diff_table(src, pkg)
                raise SystemExit("包内语料与源束不一致（%d 个文件），拒绝写清单以免把漂移洗白：\n%s"
                                 % (len(bad), "\n".join(rows)))
            src_dig = bundle_digest(src)
            src_path = os.path.join(SOURCE_BUNDLES_REL, name).replace(os.sep, "/")
        else:
            src_dig, src_path = bundle_digest(pkg), "（源束不在本机：本清单由包内自描述生成）"
        b = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _, fs in os.walk(pdir) for f in fs)
        bundles[name] = {
            "corpus_version": cj["corpus_version"],
            "source_doc": cj["source"],
            "source_doc_sha256": cj["source_sha256"],
            "source_doc_lines": cj["source_lines"],
            "source_bundle": src_path,
            "source_bundle_sha256": src_dig,
            "bundle_sha256": bundle_digest(pkg),
            "bytes": b, "files": len(pkg), "slices": len(cj.get("slices") or []),
            "files_sha256": pkg,
            "generated_at": now, "generated_by": GENERATOR,
        }
        tot_b += b
        tot_f += len(pkg)
        tot_s += len(cj.get("slices") or [])
        ver_set.add(cj["corpus_version"])
        src_doc, src_doc_sha, src_lines = cj["source"], cj["source_sha256"], cj["source_lines"]
    return {
        "manifestVersion": "2.0",
        "generated_by": GENERATOR,
        "generated_at": now,
        REDACTED_KEY: False,
        REDACT_NOTE_KEY: REDACT_NOTE,
        REDACT_TOOL_KEY: None,
        "corpus_version": sorted(ver_set)[0] if len(ver_set) == 1 else "／".join(sorted(ver_set)),
        "source": src_doc, "source_sha256": src_doc_sha, "source_lines": src_lines,
        "source_bundles": SOURCE_BUNDLES_REL,
        "source_splitter": SPLITTER_REL,
        "source_doc": SOURCE_DOC_REL,
        "bundles": bundles,
        "bundleCount": len(bundles),
        "total_bytes": tot_b, "total_files": tot_f, "total_slices": tot_s,
        "digest_rule": "整束 sha256 ＝ 对「相对路径\\0文件sha256\\n」按路径排序后串联求 sha256",
        "gateStages": {
            "段一": "包内 == 源束（逐字）。判据条件：`%s == false`。用于证明**复制无损**。" % REDACTED_KEY,
            "段二": "包内 == 源束经 `%s` 脱敏后的结果（同一份工具现场重算）。判据条件："
                    "`%s == true` 且 `%s` 已填写。TICKET-164 落地后**段二替换段一**。"
                    % (REDACT_TOOL_KEY, REDACTED_KEY, REDACT_TOOL_KEY),
            "为什么两段": "脱敏之后源束与分发版**必然不相等**；把门禁写成只有「必须相等」一种形态，"
                          "164 一落地就会假红。",
            "顺序": "导出 → 脱敏 → 算分发版哈希 → 漂移校验（**不可颠倒**：先脱敏后算哈希，"
                    "清单里记的才是分发版的指纹）。",
        },
        "resync": ("源文件更新后：① 重切源束（%s）② python3 data/daniel-cli/mcp/"
                   "check_corpus_sync.py --sync ③ 【脱敏步骤位：TICKET-164 在此把包内语料脱敏，"
                   "然后重跑 --write-manifest 把分发版哈希写回清单】④ python3 data/daniel-cli/mcp/"
                   "check_corpus_sync.py（须绿）" % SPLITTER_REL),
        "order": list(corpus.SKILL_ORDER),
        "domainLabels": {k: corpus.DOMAIN_LABELS[k] for k in corpus.SKILL_ORDER},
    }


def write_manifest(pkg_root, src_root, strict=True):
    doc = build_manifest(pkg_root, src_root, strict=strict)
    path = os.path.join(pkg_root, corpus.MANIFEST_NAME)
    io.open(path, "w", encoding="utf-8").write(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    return path, doc


def run_splitter(pkg_root):
    """**复用** TICKET-148 的语料束切分器把源文件重新切进包内目录（不另写导出器）。"""
    splitter = os.path.join(ROOT, SPLITTER_REL)
    if not os.path.isfile(splitter):
        raise SystemExit("找不到 TICKET-148 语料束切分器：%s" % splitter)
    argv = [sys.executable or "python3", splitter, "--out", pkg_root]
    print("· 重导出：%s" % " ".join(argv))
    p = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tail = (p.stdout or "").strip().splitlines()[-2:]
    for line in tail:
        print("  " + line)
    if p.returncode != 0:
        raise SystemExit("切分器失败（退出码 %d）：%s" % (p.returncode, (p.stderr or "")[:300]))
    return p.returncode


#: 导出链的**脱敏步骤位**（TICKET-164 落地时填实现）。
#: 位置固定在这里：`run_splitter()` 之后、`write_manifest()` 之前 —— 顺序即口径。
REDACTION_STEP = None


def redact_step(pkg_root):
    """导出链上的**脱敏步骤占位**：`导出 → 脱敏 → 算分发版哈希 → 漂移校验`。

    现在它什么都不做，但**必须存在且被调用**，并且**必须排在算哈希之前**：
    清单里记的哈希要么是"源束原文的指纹"（段一，`已脱敏=false`），
    要么是"脱敏后分发版的指纹"（段二，`已脱敏=true`）；顺序反了就会记成前者而宣称后者，
    门禁与清单同时失真且没人看得出来。

    TICKET-164 接线方式：把 `REDACTION_STEP` 指向脱敏工具的相对路径，
    或直接把实现写在这里；两者都要求**在 `write_manifest()` 之前完成对 `pkg_root` 的改写**。
    """
    if not REDACTION_STEP:
        print("· 脱敏步骤位：**本期未接线**（清单 `%s=false`）——%s" % (REDACTED_KEY, REDACT_NOTE))
        return False
    tool = os.path.join(ROOT, REDACTION_STEP)
    print("· 脱敏：%s --in <源束根> --out %s" % (REDACTION_STEP, pkg_root))
    p = subprocess.run([sys.executable or "python3", tool, "--in", pkg_root, "--out", pkg_root],
                       cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise SystemExit("脱敏失败（退出码 %d）：%s" % (p.returncode, (p.stderr or "")[:300]))
    return True


# ─────────────────────────── ③ 自检 ───────────────────────────
def self_test():
    """正控 ＋ 六类退化输入。**全部在临时副本上跑**，不动活仓、不依赖活仓计数。"""
    checks = []
    src_real = os.path.join(ROOT, SOURCE_BUNDLES_REL)
    pkg_real = corpus.corpus_dir()
    if not os.path.isdir(src_real):
        print("自检需要源束在本机：%s（缺失则无法跑退化输入）" % src_real)
        return 3
    if not os.path.isdir(pkg_real):
        print("自检需要包内语料：%s" % pkg_real)
        return 3

    tmp = tempfile.mkdtemp(prefix="corpus-sync-selftest-")
    try:
        good_pkg = os.path.join(tmp, "pkg-good")
        good_src = os.path.join(tmp, "src-good")
        shutil.copytree(pkg_real, good_pkg)
        shutil.copytree(src_real, good_src)
        man_good = os.path.join(good_pkg, corpus.MANIFEST_NAME)

        def run(pkg, src, manifest=None):
            led = Ledger()
            _ok, _info = gate(led, pkg, src, manifest or os.path.join(pkg, corpus.MANIFEST_NAME))
            return led

        # 正控 1：清单与两侧都一致 → 全绿
        led = run(good_pkg, good_src)
        checks.append(("正控：包内 ≡ 清单 ≡ 源束 → 全绿", not led.failed,
                       "通过 %d 项，未过 %d 项" % (led.passed, len(led.failed))))

        # 正控 2：源束不在本机 → 「跳过」而非失败（分发物上的正常情形）
        led = run(good_pkg, os.path.join(tmp, "no-such-source"))
        checks.append(("正控：源束不在本机 → 记跳过且仍绿（否则门禁在分发物上永远红）",
                       not led.failed and any(i["skip"] for i in led.items),
                       "跳过 %d 项，未过 %d 项"
                       % (sum(1 for i in led.items if i["skip"]), len(led.failed))))

        # 退化 1：包内某文件被改一个字节 → 必须红，且指出是哪个文件
        bad_pkg = os.path.join(tmp, "pkg-tampered")
        shutil.copytree(good_pkg, bad_pkg)
        target = os.path.join(bad_pkg, "kol-screening", "references", "20-due-diligence.md")
        raw = io.open(target, encoding="utf-8").read()
        io.open(target, "w", encoding="utf-8").write(raw + "\n<!-- tampered -->\n")
        led = run(bad_pkg, good_src)
        named = any(i["detail"] and "20-due-diligence.md" in i["detail"] for i in led.items)
        checks.append(("退化：包内文件被改一字节 → 红且点名该文件", bool(led.failed) and named,
                       "未过 %d 项 ｜ 点名 %s" % (len(led.failed), "是" if named else "否")))

        # 退化 2：源束被改（包内未动）→ 必须红（防"只更新源束忘了同步进包"）
        bad_src = os.path.join(tmp, "src-tampered")
        shutil.copytree(good_src, bad_src)
        target2 = os.path.join(bad_src, "kol-discovery", "SKILL.md")
        io.open(target2, "a", encoding="utf-8").write("\n<!-- drift -->\n")
        led = run(good_pkg, bad_src)
        checks.append(("退化：源束被改而包内未同步 → 红（这就是「静默退化成旧版」的形状）",
                       bool(led.failed), "未过 %d 项" % len(led.failed)))

        # 退化 3：清单被改（哈希被篡改）→ 必须红
        bad_man_pkg = os.path.join(tmp, "pkg-badmanifest")
        shutil.copytree(good_pkg, bad_man_pkg)
        mpath = os.path.join(bad_man_pkg, corpus.MANIFEST_NAME)
        doc = json.loads(io.open(mpath, encoding="utf-8").read())
        first = corpus.SKILL_ORDER[0]
        k = sorted(doc["bundles"][first]["files_sha256"])[0]
        doc["bundles"][first]["files_sha256"][k] = "0" * 64
        io.open(mpath, "w", encoding="utf-8").write(json.dumps(doc, ensure_ascii=False, indent=1))
        led = run(bad_man_pkg, good_src)
        checks.append(("退化：清单里的逐文件哈希被篡改 → 红", bool(led.failed),
                       "未过 %d 项" % len(led.failed)))

        # 退化 4：清单缺"源束路径"字段 → 必须红（没有源路径的清单等于自证）
        no_src_pkg = os.path.join(tmp, "pkg-nosource")
        shutil.copytree(good_pkg, no_src_pkg)
        mpath2 = os.path.join(no_src_pkg, corpus.MANIFEST_NAME)
        doc2 = json.loads(io.open(mpath2, encoding="utf-8").read())
        doc2["bundles"][first].pop("source_bundle", None)
        io.open(mpath2, "w", encoding="utf-8").write(json.dumps(doc2, ensure_ascii=False, indent=1))
        led = run(no_src_pkg, good_src)
        checks.append(("退化：清单缺 source_bundle → 红（追不了源）", bool(led.failed),
                       "未过 %d 项" % len(led.failed)))

        # 退化 8：清单缺"已脱敏"字段 → 必须红（状态不明说就等于谎报）
        no_flag_pkg = os.path.join(tmp, "pkg-noflag")
        shutil.copytree(good_pkg, no_flag_pkg)
        mpath3 = os.path.join(no_flag_pkg, corpus.MANIFEST_NAME)
        doc3 = json.loads(io.open(mpath3, encoding="utf-8").read())
        doc3.pop(REDACTED_KEY, None)
        io.open(mpath3, "w", encoding="utf-8").write(json.dumps(doc3, ensure_ascii=False, indent=1))
        led = run(no_flag_pkg, good_src)
        checks.append(("退化：清单缺「%s」字段 → 红（脱敏状态不明说＝谎报）" % REDACTED_KEY,
                       bool(led.failed), "未过 %d 项" % len(led.failed)))

        # 退化 9：宣称已脱敏却没有脱敏工具 → 必须红（宣称了就要能复核）
        claim_pkg = os.path.join(tmp, "pkg-claimredacted")
        shutil.copytree(good_pkg, claim_pkg)
        mpath4 = os.path.join(claim_pkg, corpus.MANIFEST_NAME)
        doc4 = json.loads(io.open(mpath4, encoding="utf-8").read())
        doc4[REDACTED_KEY] = True
        io.open(mpath4, "w", encoding="utf-8").write(json.dumps(doc4, ensure_ascii=False, indent=1))
        led = run(claim_pkg, good_src)
        checks.append(("退化：宣称 %s=true 但没接线脱敏工具 → 红" % REDACTED_KEY, bool(led.failed),
                       "未过 %d 项" % len(led.failed)))

        # 正控（段二接线演练）：造一个**恒等脱敏器**，把清单切到段二 —— 期望口径变成
        # 「源束经该工具处理后」，包内若与该结果一致则绿；不一致则红。
        # 这不是在实现脱敏（规则集归 TICKET-164），只是证明**段二这条线是真的通的**、不是空话。
        ident = os.path.join(tmp, "identity_redactor.py")
        io.open(ident, "w", encoding="utf-8").write(
            "import argparse, os, shutil\n"
            "a = argparse.ArgumentParser(); a.add_argument('--in', dest='src', required=True)\n"
            "a.add_argument('--out', dest='dst', required=True)\n"
            "n = a.parse_args()\n"
            "if os.path.isdir(n.dst): shutil.rmtree(n.dst)\n"
            "shutil.copytree(n.src, n.dst)\n")
        stage2_pkg = os.path.join(tmp, "pkg-stage2")
        shutil.copytree(good_pkg, stage2_pkg)
        mpath5 = os.path.join(stage2_pkg, corpus.MANIFEST_NAME)
        doc5 = json.loads(io.open(mpath5, encoding="utf-8").read())
        doc5[REDACTED_KEY] = True
        doc5[REDACT_TOOL_KEY] = ident
        io.open(mpath5, "w", encoding="utf-8").write(json.dumps(doc5, ensure_ascii=False, indent=1))
        led = run(stage2_pkg, good_src)
        checks.append(("正控：段二接线后（%s=true ＋ 脱敏工具可跑）→ 绿" % REDACTED_KEY,
                       not led.failed,
                       "未过 %d 项 ｜ 口径 %s" % (len(led.failed),
                                                (led.items and "见上") or "")))
        # 段二的退化：脱敏器把内容改了 → 包内与"期望分发版"不等 → 必须红
        s2_bad = os.path.join(tmp, "pkg-stage2-drift")
        shutil.copytree(stage2_pkg, s2_bad)
        target3 = os.path.join(s2_bad, "kol-screening", "SKILL.md")
        io.open(target3, "a", encoding="utf-8").write("\n<!-- x -->\n")
        led = run(s2_bad, good_src)
        checks.append(("退化：段二下包内与「期望分发版」不符 → 红", bool(led.failed),
                       "未过 %d 项" % len(led.failed)))

        # 退化 5：整束目录缺失 → 必须红
        miss_pkg = os.path.join(tmp, "pkg-missing")
        shutil.copytree(good_pkg, miss_pkg)
        shutil.rmtree(os.path.join(miss_pkg, "kol-contract"))
        led = run(miss_pkg, good_src)
        checks.append(("退化：整束目录缺失 → 红", bool(led.failed), "未过 %d 项" % len(led.failed)))

        # 退化 6：清单文件整个缺失 → 必须红（且不崩）
        empty_pkg = os.path.join(tmp, "pkg-nomanifest")
        shutil.copytree(good_pkg, empty_pkg)
        os.remove(os.path.join(empty_pkg, corpus.MANIFEST_NAME))
        led = run(empty_pkg, good_src)
        checks.append(("退化：清单文件缺失 → 红且不崩", bool(led.failed),
                       "未过 %d 项" % len(led.failed)))

        # 退化 7：strict 写清单在两侧不一致时必须拒绝（不许把漂移洗白）
        refused = False
        try:
            build_manifest(bad_pkg, good_src, strict=True)
        except SystemExit:
            refused = True
        checks.append(("退化：包内与源束不一致时 --write-manifest 必须拒绝（不洗白漂移）",
                       refused, "拒绝" if refused else "竟然写了"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, ok, _ in checks if ok)
    print("=== check_corpus_sync 自检 ===")
    for name, ok, detail in checks:
        print(" %s %s%s" % ("[通过]" if ok else "[未过]", name,
                            ("  ｜ " + detail) if detail else ""))
    print("自检 %d/%d" % (passed, len(checks)))
    return 0 if passed == len(checks) else 1


# ─────────────────────────── 入口 ───────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="包内语料 vs 源束 漂移门禁（TICKET-159）")
    ap.add_argument("--json", action="store_true", help="机器可读汇总")
    ap.add_argument("--sync", action="store_true",
                    help="复用 TICKET-148 切分器把语料重导出进包内目录，然后重写清单并自检")
    ap.add_argument("--write-manifest", action="store_true", help="只重写清单（先断言两侧相等）")
    ap.add_argument("--source-root", default=None, help="源束根（默认 <工作区>/.agents/skills）")
    ap.add_argument("--corpus-root", default=None, help="包内语料根（默认按包自身位置定位）")
    ap.add_argument("--self-test", action="store_true", help="正控＋退化输入（在临时副本上跑）")
    a = ap.parse_args(argv)

    if a.self_test:
        return self_test()

    pkg_root = os.path.abspath(os.path.expanduser(a.corpus_root)) if a.corpus_root \
        else corpus.corpus_dir()
    src_root = os.path.abspath(os.path.expanduser(a.source_root)) if a.source_root \
        else os.path.join(ROOT, SOURCE_BUNDLES_REL)
    manifest_path = os.path.join(pkg_root, corpus.MANIFEST_NAME)

    if a.sync:
        print("=== 重导出：源文件 → 包内语料（顺序：导出 → 脱敏 → 算哈希）===")
        run_splitter(pkg_root)                 # ① 导出（复用 TICKET-148 切分器）
        redact_step(pkg_root)                  # ② 脱敏（TICKET-164 的步骤位；本期不接线）
        path, doc = write_manifest(pkg_root, src_root, strict=False)   # ③ 算分发版哈希
        print("· 已重写清单：%s（语料版本 %s ｜ %d 束 ｜ %d 文件 ｜ %d 切片 ｜ %s=%s）"
              % (path, doc["corpus_version"], doc["bundleCount"], doc["total_files"],
                 doc["total_slices"], REDACTED_KEY,
                 json.dumps(doc[REDACTED_KEY], ensure_ascii=False)))
        print("=== 重导出后立刻跑一遍门禁（④ 漂移校验）===")

    print("=== 包内语料 vs 源束 漂移门禁 ===")
    print("包内：%s" % pkg_root)
    print("源束：%s%s" % (src_root, "" if os.path.isdir(src_root) else "（不在本机）"))
    led = Ledger()
    ok, info = gate(led, pkg_root, src_root, manifest_path)
    print("--- 汇总 ---")
    print("检查项：%d 条，通过 %d 条，未过 %d 条，跳过 %d 条"
          % (len(led.items), led.passed, len(led.failed),
             sum(1 for i in led.items if i["skip"])))
    print("结论：%s" % ("绿 —— 包内语料与清单／源束一致" if ok else "红 —— 包内语料已漂移"))
    if a.json:
        print(json.dumps({"ok": ok, "checks": led.items, "info": info},
                         ensure_ascii=False, indent=1))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
