# -*- coding: utf-8 -*-
"""干净度扫描：凭据、机器特征、legacy 凭据／会话文件、包内 `.py` 的写死本机路径。

四条判据与各自的口径（**先说清不扫什么**，否则"0 命中"会被误读成"绝对安全"）
--------------------------------------------------------------------------
  ③-a **凭据与令牌**：**复用既有断言器** `.kol-tools/check_no_secrets_in_dist.py`
       （TICKET-144／TICKET-151 的扫描口径：明文密码／token、`.daniel_cred.json`、
       `secrets/**`、JWT 形串…；退出码 0＝干净、1＝命中、3＝自检不过）。
       **不另造第二份凭据规则** —— 既有断言器的边界（非文本扩展名只查文件名、>4 MiB 只扫头尾、
       部分目录剪枝）就是本包的边界，票面要求"复用既有扫描口径"。
  ③-b **机器特征（本机绝对路径）**：这一条既有断言器**不含**（票面 ③ 明确要求覆盖），
       故在本模块补上，规则唯一且可复算：文本文件里出现家目录前缀 ＋ 一个非空名字（`/Users/<名>`
       或 `/home/<名>`）即命中。扫描面与 ③-a 同口径（文本扩展名 ＋ 无扩展名文件；>8 MiB 只扫头尾）。
       **为什么单列成一条而不是塞进凭据断言器**：那是 `.kol-tools/` 下的既有仪器（本票不动它），
       而本条的判据属于"包干不干净"，归包的自检。
  ③-c **legacy 凭据／会话文件按名字点名**：`spec.NAMED_EXCLUSIONS` 逐项匹配包内相对路径
       （`.daniel_cred.json`／`.daniel_session.json`／`_cache/*`／`.daniel-home/*`／`secrets/*` …）。
       **这一条是"不许偷偷回退"的直接守卫**：只要包里出现这些名字的文件，拿到包的人就可能在
       未登录状态下取到真实数据。
  ④  **包内 `.py` 不得写死本机路径**（CLS-84）：判据是 ③-b 的同一根针，作用面收窄到 `.py`。
       为什么与 ③-b 分开报：票面把"干净（含本机路径）"与"无写死绝对路径（源码面）"列为两条断言，
       分开报才能一眼看出"是源码写死"还是"某个数据文件夹带了机器特征"。
"""
import io
import os
import subprocess
import sys

from ..runtime import CliError, tools_dir
from . import spec

#: 本机绝对路径的前缀（macOS 的 `/Users/` 与 Linux 的 `/home/`）。
#: 🔴 **按片段拼接、不写成完整字面量**：本检查器自己也在包里、也会被同一条判据扫描，
#: 源码里若出现完整的家目录前缀，它就会把自己判红（自指陷阱）。这不是为了绕过检查，
#: 恰恰是为了让"这条检查抓得住任何夹带"这句话在本文件上也成立。
HOME_PREFIXES = ("/" "Users" "/", "/" "home" "/")

#: 跑内容判据的文本扩展名（与既有断言器同口径：数据类 ＋ 源码类，另加无扩展名文件）。
TEXT_EXTS = (".json", ".jsonl", ".yaml", ".yml", ".env", ".txt", ".csv", ".tsv", ".ini",
             ".conf", ".cfg", ".toml", ".xml", ".properties", ".sql", ".md5",
             ".py", ".md", ".sh", ".bash", ".zsh", ".js", ".ts", ".jsx", ".tsx",
             ".html", ".css", ".rb", ".go")

#: 单文件超过这个大小只扫头尾（与既有断言器"不静默跳过"的口径一致：报告里标注 truncated）。
FULL_SCAN_MAX = 8 * 1024 * 1024
HEAD_WINDOW = 1 * 1024 * 1024
TAIL_WINDOW = 256 * 1024

#: 目标机器上会当成"本机路径"的东西：命中即失败。
def _is_text(rel):
    ext = os.path.splitext(rel)[1].lower()
    return (ext in TEXT_EXTS) or (ext == "")


def _read_window(path):
    """读出用于内容判据的文本（大文件只读头尾），返回 `(文本, 是否截断)`。"""
    size = os.path.getsize(path)
    if size <= FULL_SCAN_MAX:
        with io.open(path, "rb") as fh:
            raw = fh.read()
        return raw.decode("utf-8", "replace"), False
    with io.open(path, "rb") as fh:
        head = fh.read(HEAD_WINDOW)
        fh.seek(max(0, size - TAIL_WINDOW))
        tail = fh.read(TAIL_WINDOW)
    return (head.decode("utf-8", "replace") + "\n" + tail.decode("utf-8", "replace")), True


def machine_path_hits(pack_root, only_exts=None, label="③-b 机器特征（本机绝对路径）"):
    """扫包内文本文件里的家目录前缀；`only_exts` 给定时只扫那些扩展名（用于 ④ 的 `.py` 面）。

    返回 `(命中清单, 扫描面)` —— 扫描面里逐项说明扫了几个、截断了几个、跳过了几个（**不静默跳过**）。
    """
    hits, surface = [], {"扫描面": label, "全量读": 0, "按上限读": 0, "非文本跳过": 0,
                         "不可读跳过": 0, "截断清单": [], "跳过清单": []}
    for dirpath, dirnames, filenames in os.walk(pack_root):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, pack_root).replace(os.sep, "/")
            if only_exts is not None and not fn.lower().endswith(tuple(only_exts)):
                continue
            if not _is_text(rel):
                surface["非文本跳过"] += 1
                surface["跳过清单"].append(rel)
                continue
            try:
                text, truncated = _read_window(full)
            except OSError:
                surface["不可读跳过"] += 1
                surface["跳过清单"].append(rel)
                continue
            if truncated:
                surface["按上限读"] += 1
                surface["截断清单"].append(rel)
            else:
                surface["全量读"] += 1
            for lineno, line in enumerate(text.splitlines(), start=1):
                for pre in HOME_PREFIXES:
                    idx = line.find(pre)
                    while idx >= 0:
                        rest = line[idx + len(pre):]
                        name = ""
                        for ch in rest:
                            if ch.isalnum() or ch in "._-":
                                name += ch
                            else:
                                break
                        if name:
                            hits.append({"文件": rel, "行号": lineno,
                                         "命中": "%s<已脱敏>" % pre,
                                         "上下文": (line.strip()[:120] or "").replace(name, "<已脱敏>")})
                            break
                        idx = line.find(pre, idx + len(pre))
    return hits, surface


def credentials(pack_root):
    """③-a：复用既有断言器扫凭据与令牌（不另造扫描口径）。"""
    script = os.path.join(tools_dir(), "check_no_secrets_in_dist.py")
    if not os.path.isfile(script):
        raise CliError("凭据断言器缺失：%s" % script, code=1,
                       hint="能力目录不完整（本包要求随包带 `.kol-tools/check_no_secrets_in_dist.py`）")
    proc = subprocess.run([sys.executable, script, pack_root],
                          capture_output=True, text=True, timeout=1800)
    tail = [ln for ln in (proc.stdout or "").strip().splitlines() if ln.strip()]
    return {"断言器": "check_no_secrets_in_dist.py（复用既有扫描口径）",
            "退出码": proc.returncode,
            "通过": proc.returncode == 0,
            "结论行": (tail[-1][:200] if tail else (proc.stderr or "").strip()[-200:]),
            "原文尾部": tail[-6:]}


def named_exclusions(pack_root):
    """③-c：点名排除的文件是否出现在包里（按名字逐项匹配）。"""
    from . import builder
    return builder.scan_named(pack_root)


def cleanliness(pack_root):
    """③ ＋ ④ 的完整结论（`--check` 直接用它）。"""
    cred = credentials(pack_root)
    hits, surface = machine_path_hits(pack_root)
    py_hits, py_surface = machine_path_hits(pack_root, only_exts=(".py",))
    named = named_exclusions(pack_root)
    return {
        "凭据与令牌（复用既有断言器）": cred,
        "机器特征（本机绝对路径）": {"命中数": len(hits), "命中": hits[:20],
                                    "扫描面": surface},
        "点名排除（legacy 凭据／会话／台账）": {"命中数": len(named), "命中": named[:20],
                                               "规则数": len(spec.NAMED_EXCLUSIONS)},
        "包内 .py 写死本机路径": {"命中数": len(py_hits), "命中": py_hits[:20],
                                 "扫描面": py_surface},
        "通过": bool(cred["通过"] and not hits and not named and not py_hits),
    }
