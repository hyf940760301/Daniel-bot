# -*- coding: utf-8 -*-
"""出包（`--out`）：按 `spec` 复算候选面 → 逐文件复制 → 落一份**出包清单**（receipt）。

三条实现纪律
------------
① **不走"手抄清单"**：候选面、排除集、包含集全部由 `spec.classify()` 现算；清单只是**这次的
   算账结果**，不是下一次的依据 —— 源目录变了，清单跟着变。
② **清单落在包目录之外**（`<out>/_PACK_MANIFEST.json`）：包内必须严格满足
   「包内文件 ⊆ 源目录」，出包时新生成的清单若放进包里就破了这条；放在包外，它同时充当收据。
③ **不得往工作区里出包**（票面工作纪律）：包根若落在源目录之内，**当场拒绝**（退出码 2）——
   那会污染门禁扫描面与仪器台账，也会让"包内可跑"变成"偷读仓库根凭据"的假绿。
"""
import hashlib
import io
import json
import os
import shutil
import time

from ..runtime import CliError
from ..exits import EXIT_USAGE
from . import PACK_DIRNAME, MANIFEST_NAME, spec


# ─────────────────────────── 源根定位 ───────────────────────────
def cli_package_root():
    """本 CLI 的包根（`<…>/data/daniel-cli`）。从**本文件位置**推，不写死。"""
    here = os.path.dirname(os.path.realpath(__file__))          # …/daniel_cli/pack
    return os.path.dirname(os.path.dirname(here))               # …/data/daniel-cli


def source_root(explicit=None):
    """源目录（团队工作区根，含 `data/daniel-cli/` 与 `.kol-tools/`）。

    给 `--source` 就用它；否则从包根往上推（`<仓库根>/data/daniel-cli` ⇒ `<仓库根>`）。
    **必须是真源**：不满足"同时有 `data/daniel-cli/daniel_cli/schema.py` 与
    `.kol-tools/daniel_client.py`"的目录当场拒绝 —— 差集对账没有源就无从复算，与其给个假通过，
    不如说清缺什么。
    """
    root = os.path.abspath(os.path.expanduser(explicit)) if explicit else \
        os.path.dirname(os.path.dirname(cli_package_root()))
    missing = [rel for rel in ("data/daniel-cli/daniel_cli/schema.py",
                               ".kol-tools/daniel_client.py")
               if not os.path.isfile(os.path.join(root, rel))]
    if missing:
        raise CliError(
            "这不是出包用的源目录（缺 %s）：%s" % ("、".join(missing), root),
            code=EXIT_USAGE,
            hint="从完整的工作区里跑 `daniel pack --out <目录>`；或在只有包的时候用 "
                 "`daniel pack --check <包目录> --source <源目录>` 指定源")
    return root


def pack_root_of(out_dir):
    """出包目录 → 包根（`<out>/daniel-bot`）。"""
    return os.path.join(os.path.abspath(os.path.expanduser(out_dir)), PACK_DIRNAME)


def receipt_path_of(out_dir):
    """出包目录 → 出包清单路径（**在包目录之外**）。"""
    return os.path.join(os.path.abspath(os.path.expanduser(out_dir)), MANIFEST_NAME)


def assert_outside_source(pack_root, root):
    """包根不得落在源目录之内（票面工作纪律：不许往工作区里出包）。"""
    p = os.path.realpath(pack_root)
    r = os.path.realpath(root)
    if p == r or p.startswith(r + os.sep):
        raise CliError("出包落点在源目录之内（%s ⊆ %s），本命令拒绝在这里出包" % (p, r),
                       code=EXIT_USAGE,
                       hint="换一个工作区外的目录，例如 `--out /tmp/交付包`；"
                            "往仓库里出包会污染门禁扫描面与仪器台账")


# ─────────────────────────── 候选面：算，不抄 ───────────────────────────
def _sha256(path):
    h = hashlib.sha256()
    with io.open(path, "rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def walk_candidates(root):
    """候选面：`spec.CANDIDATE_ROOTS` 下的全部文件（相对源根的 POSIX 路径，排序输出）。"""
    out = []
    for top in spec.CANDIDATE_ROOTS:
        base = os.path.join(root, top)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames.sort()
            for fn in sorted(filenames):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                out.append(rel)
    out.sort()
    return out


def plan(root):
    """这次出包会包含什么、排除什么（**只读**；干跑与真执行共用这一份算账）。"""
    included, excluded, unknown = [], [], []
    for rel in walk_candidates(root):
        inc, exc = spec.classify(rel)
        if inc is not None and exc is not None:
            excluded.append({"文件": rel, "规则": exc["id"], "理由": exc["reason"]})
        elif inc is not None:
            included.append({"文件": rel, "规则": inc["id"]})
        elif exc is not None:
            excluded.append({"文件": rel, "规则": exc["id"], "理由": exc["reason"]})
        else:
            unknown.append(rel)            # 候选面里两边都没命中：不该发生，如实报出来
    inc_bytes = sum(os.path.getsize(os.path.join(root, r["文件"])) for r in included)
    exc_bytes = sum(os.path.getsize(os.path.join(root, r["文件"])) for r in excluded
                    if os.path.isfile(os.path.join(root, r["文件"])))
    return {
        "源根": root,
        "候选面": list(spec.CANDIDATE_ROOTS),
        "候选面文件数": len(included) + len(excluded) + len(unknown),
        "包含": included,
        "排除": excluded,
        "未命中任何规则": unknown,
        "计数": {"包含文件数": len(included), "排除文件数": len(excluded),
                 "包含字节": inc_bytes, "排除字节": exc_bytes},
        "规则表": {
            "必须包含": [dict(r) for r in spec.INCLUDE_RULES],
            "必须排除": [dict(r) for r in spec.EXCLUDE_RULES],
            "点名排除": [{"模式": p, "理由": w} for p, w in spec.NAMED_EXCLUSIONS],
        },
    }


def execute(root, out_dir):
    """真出包：建目录 → 逐文件复制（保留权限位）→ 落出包清单。返回 `(receipt, 包根)`。"""
    pack_root = pack_root_of(out_dir)
    assert_outside_source(pack_root, root)
    if os.path.isdir(pack_root) and os.listdir(pack_root):
        raise CliError("包目录已存在且非空：%s" % pack_root, code=EXIT_USAGE,
                       hint="换一个 --out 目录，或先手工删掉那个目录（本命令不替你删东西）")
    p = plan(root)
    if p["未命中任何规则"]:
        raise CliError("候选面里有 %d 个文件没命中任何规则（规则表与候选面不一致）：%s"
                       % (len(p["未命中任何规则"]), "、".join(p["未命中任何规则"][:5])),
                       code=EXIT_USAGE, hint="先修 spec.py 的规则表，再出包")

    files = []
    for row in p["包含"]:
        src = os.path.join(root, row["文件"])
        dst = os.path.join(pack_root, row["文件"])
        parent = os.path.dirname(dst)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        shutil.copy2(src, dst)                       # copy2：连权限位一起带过去（入口要可执行）
        st = os.stat(dst)
        files.append({"文件": row["文件"], "规则": row["规则"], "字节": st.st_size,
                      "sha256": _sha256(dst),
                      "可执行": bool(st.st_mode & 0o111)})

    named_hits = scan_named(pack_root)
    ledger = named_ledger(root, pack_root)
    receipt = {
        "清单版本": "1.0",
        "生成者": "daniel pack --out（TICKET-193）",
        "生成时间": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "源根": root,
        "源根说明": "仅存档：出包清单落在包目录之外，不随包分发；包内不含任何本机路径",
        "包目录名": PACK_DIRNAME,
        "包内入口": os.path.join(PACK_DIRNAME, "data", "daniel-cli", "bin", "daniel"),
        "候选面": p["候选面"],
        "规则表": p["规则表"],
        "计数": {"包含文件数": len(files),
                 "包含字节": sum(f["字节"] for f in files),
                 "排除文件数": len(p["排除"])},
        "包含": files,
        "排除": p["排除"],
        "点名排除": ledger,
        "点名排除命中": named_hits,
    }
    if named_hits:
        shutil.rmtree(pack_root, ignore_errors=True)
        raise CliError("出包时在包里发现了点名排除的文件（已把这次出的包删掉）：%s"
                       % "、".join(h["文件"] for h in named_hits[:5]),
                       code=EXIT_USAGE, hint="先查清它们是怎么进包的（源目录被改过？）")
    path = receipt_path_of(out_dir)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(receipt, ensure_ascii=False, indent=1, sort_keys=False) + "\n")
    return receipt, pack_root


# ─────────────────────────── 包盘面 ───────────────────────────
def walk_pack(pack_root):
    """包里的全部文件（相对包根的 POSIX 路径，排序）。**空目录不计**（包内不产空目录）。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(pack_root):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            out.append(os.path.relpath(full, pack_root).replace(os.sep, "/"))
    out.sort()
    return out


def scan_named(pack_root):
    """点名排除命中扫描（包内相对路径按 `spec.NAMED_EXCLUSIONS` 匹配）。"""
    hits = []
    for rel in walk_pack(pack_root):
        for pat, why in spec.NAMED_EXCLUSIONS:
            if spec.match(rel, pat):
                hits.append({"文件": rel, "模式": pat, "理由": why})
                break
    return hits


def named_ledger(root, pack_root=None):
    """**点名排除的逐项账**：每条规则在源目录里到底点到了哪些东西（附理由与体积）。

    为什么要单独有这一份（票面追加要求）：`<源根>/.daniel_cred.json`、
    `<能力目录>/.daniel_session.json`、`<能力目录>/_cache/brand-index.json` 这三条**不在候选面里**
    （候选面只含 `data/daniel-cli/**` 与 `.kol-tools/` 白名单），若只靠"它们在别的目录所以顺带被
    排掉"来解释，那是**推断**、不是**点名**。这里把每条规则在源目录里点到的具体路径**逐个列出来**
    （含"现在是否存在"与体积），并在同一结构里给出"包内命中数"（必须为 0）。
    """
    cache = {}

    def _walk(prefix):
        if prefix in cache:
            return cache[prefix]
        base = os.path.join(root, prefix) if prefix else root
        rows = []
        if os.path.isfile(base):
            rows = [prefix]
        elif os.path.isdir(base):
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames.sort()
                for fn in sorted(filenames):
                    full = os.path.join(dirpath, fn)
                    rows.append(os.path.relpath(full, root).replace(os.sep, "/"))
        cache[prefix] = rows
        return rows

    pack_hits = {}
    if pack_root:
        for h in scan_named(pack_root):
            pack_hits.setdefault(h["模式"], []).append(h["文件"])

    out = []
    for pat, why in spec.NAMED_EXCLUSIONS:
        static = []
        for seg in pat.split("/"):
            if any(ch in seg for ch in "*?["):
                break
            static.append(seg)
        prefix = "/".join(static)
        found = [rel for rel in _walk(prefix) if spec.match(rel, pat)]
        sample = []
        for rel in found[:5]:
            full = os.path.join(root, rel)
            sample.append({"文件": rel,
                           "字节": (os.path.getsize(full) if os.path.isfile(full) else None)})
        out.append({
            "模式": pat, "理由": why,
            "源目录命中数": len(found),
            "源目录样例": sample,
            "包内命中数": len(pack_hits.get(pat, [])),
            "包内命中": pack_hits.get(pat, [])[:5],
        })
    return out


def read_receipt(out_dir):
    """读出包目录的收据（`<out>/_PACK_MANIFEST.json`）；没有则 None（如实返回，不编）。"""
    path = receipt_path_of(out_dir)
    if not os.path.isfile(path):
        return None, path
    try:
        with io.open(path, encoding="utf-8") as fh:
            return json.loads(fh.read()), path
    except ValueError as e:
        raise CliError("出包清单不是合法 JSON：%s（%s）" % (path, e), code=EXIT_USAGE)
