# -*- coding: utf-8 -*-
"""`daniel pack --check` 的断言编排：五条断言（票面 B），每条都作用在**真实产物**上。

  A1 结构完整      ：包内入口与关键文件在位（可执行位、单一真源、随包语料、能力目录）
  A2 引用闭合      ：包内代码**按名字引用**的能力模块，包里必须都有（这条守住"最小完整集"）
  A3 干净（③＋④）  ：凭据与令牌（复用既有断言器）／本机绝对路径／legacy 凭据与会话文件／
                     包内 `.py` 写死本机路径
  A4 差集对账（⑤）  ：包内文件 ⊆ 源目录；源 − 包 == 排除清单（逐项）
  A5 隔离复现（①②）：临时 HOME ＋ 哨兵钥匙串服务 ＋ 包副本在源目录之外，真跑包内入口
                     （`--version`／`schema --check`／`connect --apply`／`connect --doctor`）
                     ＋ **反控**：同一隔离环境里"无凭据"时**不得**取到真实数据

每条断言都返回 `通过` 三态：`True`／`False`／`None`（**未取得** —— 例如没给凭据时"接入可用"
这一条要求真取一次数，本函数不会把它按通过处理，也不会按失败处理，而是如实登记）。
"""
import io
import os
import re

from ..exits import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE
from ..runtime import CliError
from . import builder, isolation, scanner, spec

#: A1 要求必须存在的关键文件（相对包根）与它们的理由
REQUIRED_FILES = (
    ("data/daniel-cli/bin/daniel", "CLI 入口（`connect` 写进宿主配置的间接入口，也是用户唯一要敲的路径）"),
    ("data/daniel-cli/daniel_cli/schema.py", "单一真源（`schema --check` 的比对对象）"),
    ("data/daniel-cli/daniel_cli/cli.py", "入口分发与退出码收口"),
    ("data/daniel-cli/mcp/server.py", "MCP 服务（`connect` 写进宿主配置的就是它）"),
    ("data/daniel-cli/mcp/client_check.py", "接入自检复用的既有仪器（doctor 第 ② 项）"),
    ("data/daniel-cli/mcp/corpus/_MANIFEST.json", "随包语料清单（doctor 第 ① 项判「包完整性」）"),
    ("data/daniel-cli/contracts/_examples/engine-smoke.json", "契约引擎最小契约（引擎自证要用）"),
    (".kol-tools/daniel_client.py", "共享客户端（鉴权与跨工作区品牌解析）"),
    (".kol-tools/daniel_paths.py", "落点唯一真源"),
    (".kol-tools/daniel_credentials.py", "凭据存储（钥匙串／环境变量／legacy 四处来源）"),
    (".kol-tools/daniel_io.py", "仪器 `--json` 出口的收口层"),
    (".kol-tools/check_no_secrets_in_dist.py", "凭据断言器（本包自检复用它）"),
)

#: A2 的加载点规则（**只认加载点**，理由见 `static_reference_closure` 的说明）
_LOADER_RULES = (
    ("load_capability", re.compile(r"""load_capability\(\s*["']([A-Za-z0-9_]+)["']""")),
    ("_load_sibling", re.compile(r"""_load_sibling\(\s*["']([A-Za-z0-9_]+)["']""")),
    ("_sibling", re.compile(r"""(?<!_load)_sibling\(\s*["']([A-Za-z0-9_]+)["']""")),
    ("_load(别名, 文件)", re.compile(r"""_load\(\s*["'][^"']+["']\s*,\s*["']([A-Za-z0-9_]+)\.py["']""")),
    ("文件名字面量", re.compile(r"""["']([A-Za-z0-9_]+)\.py["']""")),
    ("spec_from_file_location(模块名)", re.compile(r"""spec_from_file_location\(\s*["']([A-Za-z0-9_]+)["']""")),
    ("import", re.compile(r"""^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)\b""", re.M)),
)


def _item(aid, judge, ok, evidence, extra=None):
    """一条断言。`通过` 只允许三态：`True`／`False`／`None`（未取得）。

    ⚠️ 这里**强制 `bool()`**：`ok` 若是列表／字符串（例如误把 `os.listdir()` 的结果当条件，
    真值判断"看起来对"但值不是布尔），下游按 `is False` 找失败项时会把失败**静默漏掉**。
    这个坑在 TICKET-193 自测里真出现过（A2 的"通过"渲染成了一个文件名列表），故在此收口。
    """
    row = {"编号": aid, "判据": judge,
           "通过": (None if ok is None else bool(ok)), "证据": evidence}
    if extra:
        row["明细"] = extra
    return row


# ─────────────────────────── A1 结构完整 ───────────────────────────
def structure(pack_root):
    missing, present = [], []
    for rel, why in REQUIRED_FILES:
        full = os.path.join(pack_root, rel)
        if os.path.isfile(full):
            present.append({"文件": rel, "字节": os.path.getsize(full), "理由": why})
        else:
            missing.append({"文件": rel, "理由": why})
    entry = os.path.join(pack_root, "data", "daniel-cli", "bin", "daniel")
    executable = bool(os.path.isfile(entry) and (os.stat(entry).st_mode & 0o111))
    corpus = os.path.join(pack_root, "data", "daniel-cli", "mcp", "corpus")
    corpus_files = sum(len(f) for _d, _s, f in os.walk(corpus)) if os.path.isdir(corpus) else 0
    empty_dirs = [os.path.relpath(os.path.join(d, n), pack_root).replace(os.sep, "/")
                  for d, dn, _f in os.walk(pack_root) for n in dn
                  if not os.listdir(os.path.join(d, n))]
    ok = (not missing) and executable and corpus_files > 0 and not empty_dirs
    ev = ("关键文件 %d/%d 在位 ｜ 入口可执行位 %s ｜ 随包语料 %d 个文件 ｜ 空目录 %d 个"
          % (len(present), len(REQUIRED_FILES), "有" if executable else "**无**",
             corpus_files, len(empty_dirs)))
    return _item("A1", "结构完整：入口与关键文件在位（含可执行位与随包语料）", ok, ev,
                 extra={"缺失": missing, "空目录": empty_dirs,
                        "包内关键文件": present})


# ─────────────────────────── A2 引用闭合 ───────────────────────────
def static_reference_closure(pack_root, source_root=None):
    """包内代码**按名字引用**的能力模块，包里必须都有。

    只认七类**加载点**（`load_capability` / `_load_sibling` / `_sibling` / `_load(别名, 文件)` /
    文件名字面量 / `spec_from_file_location(模块名)` / `import`），且**只判源目录 `.kol-tools/`
    里真实存在的名字**（别名如 `dc`／`_dc` 不判）—— 这一条实测过：宽口径
    `os.path.join(…, "X.py")` 会把自检夹具名与探测名当成依赖（实测 7 个假阳性：
    `app.py`／`client.py`／`config_reader.py`／`extractor.py`／`identity_redactor.py`／
    `server.py`／`check_corpus_sync.py`），故**不采用**宽口径。
    """
    kol_dir = None
    if source_root:
        cand = os.path.join(source_root, ".kol-tools")
        if os.path.isdir(cand):
            kol_dir = cand
    refs = {}
    for dirpath, dirnames, filenames in os.walk(pack_root):
        dirnames.sort()
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, pack_root).replace(os.sep, "/")
            try:
                with io.open(full, encoding="utf-8") as fh:
                    text = fh.read()
            except (OSError, UnicodeDecodeError):
                continue
            for label, rx in _LOADER_RULES:
                for m in rx.finditer(text):
                    name = m.group(1)
                    if kol_dir is not None and not os.path.isfile(os.path.join(kol_dir, name + ".py")):
                        continue
                    refs.setdefault(name, set()).add("%s@%s" % (label, rel))
    missing = [n for n in sorted(refs)
               if not os.path.isfile(os.path.join(pack_root, ".kol-tools", n + ".py"))]
    jsref_used = _text_mentions(pack_root, "_daniel_jsref")
    jsref_dir = os.path.join(pack_root, ".kol-tools", "_daniel_jsref")
    jsref_files = sorted(os.listdir(jsref_dir)) if os.path.isdir(jsref_dir) else []
    jsref_ok = (not jsref_used) or bool(jsref_files)
    ok = bool((not missing) and jsref_ok)
    ev = ("按名字引用到的能力模块 %d 个 ｜ 缺件 %d 个 ｜ `_daniel_jsref` %s"
          % (len(refs), len(missing),
             ("被引用且在位（%d 个文件）" % len(jsref_files) if (jsref_used and jsref_ok) else
              ("被引用但**缺失**" if jsref_used else "未被引用，不判"))))
    return _item("A2", "引用闭合：包内代码按名字引用的能力模块，包里都有", ok, ev,
                 extra={"引用到的模块": {k: sorted(v)[:4] for k, v in sorted(refs.items())},
                        "缺失": missing,
                        "jsref 文件": jsref_files,
                        "口径": "只认七类加载点；只判源目录 `.kol-tools/` 里真实存在的名字"})


def _text_mentions(pack_root, needle):
    for dirpath, _dn, filenames in os.walk(pack_root):
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            try:
                with io.open(os.path.join(dirpath, fn), encoding="utf-8") as fh:
                    if needle in fh.read():
                        return True
            except (OSError, UnicodeDecodeError):
                continue
    return False


# ─────────────────────────── A3 干净 ───────────────────────────
def cleanliness(pack_root):
    c = scanner.cleanliness(pack_root)
    ev = ("凭据断言器退出码 %s ｜ 本机路径命中 %d ｜ 点名排除命中 %d ｜ 包内 .py 写死本机路径 %d"
          % (c["凭据与令牌（复用既有断言器）"]["退出码"],
             c["机器特征（本机绝对路径）"]["命中数"],
             c["点名排除（legacy 凭据／会话／台账）"]["命中数"],
             c["包内 .py 写死本机路径"]["命中数"]))
    return _item("A3", "干净：凭据与机器特征 0 命中（③ 凭据与机器特征 ＋ ④ 源码面写死路径）",
                 c["通过"], ev, extra=c)


# ─────────────────────────── A4 差集对账 ───────────────────────────
def reconcile(pack_root, source_root=None, out_dir=None):
    """包内文件 ⊆ 源目录；`源 − 包 == 排除清单`（逐项）。"""
    pack_files = builder.walk_pack(pack_root)
    pack_set = set(pack_files)
    pack_bytes = sum(os.path.getsize(os.path.join(pack_root, r)) for r in pack_files)
    detail = {"包内文件数": len(pack_files), "包内总字节": pack_bytes}
    receipt, receipt_path = builder.read_receipt(out_dir) if out_dir else (None, None)

    if source_root and os.path.isdir(os.path.join(source_root, ".kol-tools")):
        p = builder.plan(source_root)
        face = set(r["文件"] for r in p["包含"]) | set(r["文件"] for r in p["排除"])
        included = set(r["文件"] for r in p["包含"])
        excluded = {r["文件"]: r for r in p["排除"]}
        extra = sorted(pack_set - face)
        missing = sorted(included - pack_set)
        recomputed = sorted((face - pack_set))
        excludes_ok = (set(recomputed) == set(excluded))
        ledger = builder.named_ledger(source_root, pack_root)
        ledger_src = sum(r["源目录命中数"] for r in ledger)
        ledger_pack = sum(r["包内命中数"] for r in ledger)
        ok = (not extra) and (not missing) and excludes_ok and ledger_pack == 0
        ev = ("源候选面 %d 个文件（含 %d／排 %d）｜ 包内 %d 个文件、%d 字节 ｜ "
              "源 − 包 复算 %d 项 == 排除清单 %d 项：%s ｜ 包内多出（源里没有）%d 项 ｜ "
              "点名排除 %d 条规则点到源目录 %d 项、包内命中 %d 项"
              % (len(face), len(included), len(excluded), len(pack_files), pack_bytes,
                 len(recomputed), len(excluded), "逐项相等 ✅" if excludes_ok else "**不相等** ❌",
                 len(extra), len(ledger), ledger_src, ledger_pack))
        return _item("A4", "差集对账：包内 ⊆ 源，且 源 − 包 == 排除清单（逐项）", ok, ev,
                     extra={"源根": source_root, "包内多出（源里没有）": extra[:20],
                            "源里有、包里没有但不在排除清单": missing[:20],
                            "源 − 包 与 排除清单 的差集": sorted(
                                set(recomputed) ^ set(excluded))[:20],
                            "逐项排除清单": [{"文件": k, "规则": v["规则"]} for k, v in
                                             sorted(excluded.items())],
                            "点名排除逐项账": ledger,
                            **detail})

    # 源目录不可用 ⇒ 用收据复算（并如实登记"与源的差集未取得"）
    if receipt is None:
        return _item("A4", "差集对账：包内 ⊆ 源，且 源 − 包 == 排除清单（逐项）", False,
                     "源目录与出包清单都没有 ⇒ 差集无从复算（**未取得**，不按通过处理）",
                     extra=dict(detail, 收据路径=receipt_path))
    want = set(r["文件"] for r in receipt.get("包含") or [])
    extra = sorted(pack_set - want)
    missing = sorted(want - pack_set)
    bad_hash = []
    for row in receipt.get("包含") or []:
        full = os.path.join(pack_root, row["文件"])
        if os.path.isfile(full) and builder._sha256(full) != row.get("sha256"):   # noqa: SLF001
            bad_hash.append(row["文件"])
    ok = (not extra) and (not missing) and (not bad_hash)
    ev = ("源目录未提供 ⇒ 用出包清单复算：清单 %d 项 ｜ 包内 %d 项 ｜ 多出 %d ｜ 缺 %d ｜ "
          "sha256 不符 %d（**与源的差集未取得**）"
          % (len(want), len(pack_files), len(extra), len(missing), len(bad_hash)))
    return _item("A4", "差集对账：包内 ⊆ 源，且 源 − 包 == 排除清单（逐项）", ok, ev,
                 extra={"收据路径": receipt_path, "包内多出": extra[:20], "缺失": missing[:20],
                        "sha256 不符": bad_hash[:20], **detail,
                        "未取得": "本机没有源目录 ⇒ 「源 − 包 == 排除清单」这一半不可复算"})


# ─────────────────────────── A5 隔离复现 ───────────────────────────
def reproduction(pack_root, source_root=None, host=None, creds=None, keep=False,
                 interpreter=None):
    outside = True
    if source_root:
        outside = isolation.pack_absent_from_source(pack_root, source_root)
    res = isolation.reproduce(pack_root, host=host, creds=creds, keep=keep,
                              interpreter=interpreter)
    a = res["断言"]
    ok = bool(a["① 包内可跑（--version ＋ schema --check 10/10）"]
              and a["反控 无凭据不得取到真实数据"]
              and (a["② 包内接入可用（connect ＋ doctor 全绿）"] in (True, None))
              and outside)
    ev = ("① 包内可跑 %s ｜ ② 包内接入可用 %s ｜ 反控（无凭据不得取到真实数据）%s ｜ "
          "包在源目录之外 %s ｜ 隔离复现的宿主 %s"
          % ("✅" if a["① 包内可跑（--version ＋ schema --check 10/10）"] else "❌",
             ("✅" if a["② 包内接入可用（connect ＋ doctor 全绿）"] else
              ("未取得" if a["② 包内接入可用（connect ＋ doctor 全绿）"] is None else "❌")),
             "✅" if a["反控 无凭据不得取到真实数据"] else "❌",
             "✅" if outside else "❌（包还在源目录里，隔离不成立）",
             "、".join(res.get("隔离复现的宿主") or [])))
    return _item("A5", "隔离复现：临时 HOME ＋ 哨兵钥匙串服务 ＋ 包在源目录之外（① ② ＋ 反控）",
                 ok, ev, extra=res)


# ─────────────────────────── 编排 ───────────────────────────
def run_check(pack_root, source_root=None, out_dir=None, host=None, creds=None,
              keep=False, interpreter=None, skip_isolation=False):
    """跑完 A1–A5，返回 `{通过, 断言, 结论, 计数}`。

    一条口径写在最前面：**源目录＝包自身时，与源的差集无从复算**（拿自己跟自己比永远相等），
    这时按"未取得"处理（`source_root=None` ⇒ 用出包清单复算并在证据里写明），
    绝不把它算成"差集对账通过"。

    `skip_isolation=True`（`--fast`）只跑 A1–A4，A5 如实记「未取得（按用户要求跳过）」——
    跳过≠通过：结论里会点出未取得项，验收用的默认跑法**不含**这个开关。
    """
    pack_root = os.path.abspath(os.path.expanduser(pack_root))
    if not os.path.isdir(pack_root):
        raise CliError("包目录不存在：%s" % pack_root, code=EXIT_USAGE,
                       hint="先出包：`daniel pack --out <目录> --confirm`")
    if source_root and os.path.realpath(source_root) == os.path.realpath(pack_root):
        source_root = None
    if skip_isolation:
        a5 = _item("A5", "隔离复现：临时 HOME ＋ 哨兵钥匙串服务 ＋ 包在源目录之外（① ② ＋ 反控）",
                   None, "未取得（--fast：按用户要求跳过 A5；本跑法**不**用于验收）")
    else:
        a5 = reproduction(pack_root, source_root=source_root, host=host, creds=creds, keep=keep,
                          interpreter=interpreter)
    items = [
        structure(pack_root),
        static_reference_closure(pack_root, source_root),
        cleanliness(pack_root),
        reconcile(pack_root, source_root=source_root, out_dir=out_dir),
        a5,
    ]
    failed = [i for i in items if i["通过"] is False]
    unknown = [i["编号"] for i in items if i["通过"] is None]
    pack_files = builder.walk_pack(pack_root)
    return {
        "通过": not failed,
        "断言": items,
        "计数": {"包内文件数": len(pack_files),
                 "包内总字节": sum(os.path.getsize(os.path.join(pack_root, r)) for r in pack_files),
                 "未取得项": unknown, "未过项": [i["编号"] for i in failed]},
        "结论": ("全部通过（%d 条断言；未取得项：%s）" % (len(items), "、".join(unknown) or "无")
                 if not failed else
                 "未通过：%s（逐条见「断言」里那几条的证据与明细）"
                 % "、".join(i["编号"] for i in failed)),
        "包根": pack_root,
    }


def exit_code_for(result):
    return EXIT_OK if result.get("通过") else EXIT_INTERNAL
