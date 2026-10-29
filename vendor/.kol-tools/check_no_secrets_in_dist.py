#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分发物凭据断言（TICKET-144 §6 建立；TICKET-151 C2 提速改版）。

用法
  python3 check_no_secrets_in_dist.py <目录> [<目录> …]        # 命中即非零退出（1）
  python3 check_no_secrets_in_dist.py "<工作区根>" --allow-repo-root   # 只报警不失败（用户要求保留现有文件）
  python3 check_no_secrets_in_dist.py --self-test              # 正控必报 + 真阴性 0 命中
  python3 check_no_secrets_in_dist.py --surface                # 只看"扫描面自报"（复核没扫漏）

判据分层（避免把"源码里提到环境变量名"误判成泄漏）
  ERROR（失败）：① 凭据/密钥**文件名**；② 数据文件（.json/.yaml/.env/.txt/.csv/.ini/.xml…）里出现
                 邮件+密码键值对、`password: "<值>"`、`DANIEL_PASSWORD=<值>`；③ 任意文本文件里出现
                 JWT（`eyJ….….…`）或 `app_session_id=<JWT>`。
  WARN（不失败）：`.py`/`.md`/`.sh` 等**源码/文档**仅提到 `DANIEL_EMAIL`/`DANIEL_PASSWORD`/
                 `daniel_cred`/`daniel_session` 等名字（无字面量密钥）—— 记录但不阻塞打包。

扫描边界（**先看这里：什么不扫、为什么**；TICKET-151 C2 起生效，`--help` 末尾有同一份摘要）
  ① **二进制不扫内容**。只有"文本扩展名"的文件才跑内容判据：数据类 `.json .jsonl .yaml .yml .env
     .txt .csv .tsv .ini .conf .cfg .toml .xml .properties .sql .md5`、源码类 `.py .md .sh .bash
     .zsh .js .ts .jsx .tsx .html .css .rb .go`，**另加无扩展名文件**（按文本处理，例如 `bin/daniel`）。
     其余扩展名（图片、压缩包 `.zip/.gz/.whl`、可执行 `.so/.node/.exe`、字库、办公文档 `.xlsx/.pdf`、
     日志 `.log/.out/.err` 等）**只做文件名判据**——把假凭据串嵌进这些文件里，本工具**不会**报出。
  ② **>4 MiB 只扫头尾**。单文件超过 `FULL_SCAN_MAX`（4 MiB）时，只读**头 `HEAD_WINDOW`（1 MiB）
     ＋ 尾 `TAIL_WINDOW`（256 KiB）**，中段不扫；命中条目标 `truncated: true`，报告里逐条标注
     「已按上限扫描」，尾窗口行号是近似下界。该阈值与旧版 `MAX_BYTES=4 MiB` 同值，且旧版对
     >4 MiB 的文件**完全不扫**，故本改版对每个文件的覆盖只增不减；`--full-scan` 可关掉窗口。
  ③ **目录剪枝**：`.git`、`node_modules`、`__pycache__`、`.venv`、`venv`、`.mypy_cache`、
     `.pytest_cache`，以及 `_archive*` 前缀目录（历史归档；`--scan-archives` 可放开）。
  ④ **已知不判 ERROR 的形状**（既有口径，不是本次改版引入）：`password: hunter2`（值未加引号）
     不命中 `password_literal`（该规则要求引号包裹）；把变量名本身拆行写成 `DANIEL_PASS` ＋ 换行 ＋
     `WORD=x` 不命中（正则按整词匹配）；`.log/.out` 等非文本扩展名不扫内容（见 ①）。

  剪枝与截断**全部计入"扫描面自报"**（每次扫描报告尾部，或 `--surface`／`--json` 的 `scanSurface`），
  不存在静默跳过。

  提速做法（TICKET-151 C2，两条都用）：先**字节级 needle 预筛**——只有命中
  `eyj/email/password/app_session_id/daniel_cred/daniel_session` 之一的文件才解码＋跑正则
  （每条规则的**必要字面量**都在 needle 表里，故不漏报；自检 S4 逐文件断言该性质）；
  再**按文件切分并行**（`ThreadPoolExecutor`，默认 8 线程，`--jobs`／`KOL_DIST_SCAN_JOBS` 可调），
  命中集合最后按「路径/行号/规则」排序，**输出与并发数无关**。

退出码：0=干净（或仅 --allow-repo-root 下的告警）｜1=命中 ERROR｜2=用法错误｜3=自检不通过
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SELF = os.path.abspath(__file__)

# ─────────────────────────── 剪枝口径 ───────────────────────────
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"}
#: 历史归档目录按前缀剪枝（默认剪枝；`--scan-archives` 放开）。
#: 剪掉的目录会逐条打印进"扫描面自报"，便于复核是不是剪过头。
SKIP_DIR_PREFIXES = ("_archive",)

# ① 文件名（大小写不敏感，全名匹配；`\.[\w.-]*` 覆盖 .bak/.verify-bak 等变体，
#    但**不会**误伤源码模块 daniel_credentials.py / daniel_session_helper.py）
BAD_NAME_PATTERNS = [
    r"^\.?daniel_cred(\.[\w.-]*)?$", r"^\.?daniel_session(\.[\w.-]*)?$", r"^\.daniel_[\w.-]*$",
    r"^credentials.*\.json$", r"^secrets?.*\.json$", r"^\.env(\..*)?$",
    r"^id_rsa.*", r".*\.pem$", r".*\.p12$", r".*\.keychain(-db)?$", r"^\.netrc$",
]
# ② 数据类扩展名（可含字面量密钥）
DATA_EXT = {".json", ".jsonl", ".yaml", ".yml", ".env", ".txt", ".csv", ".tsv",
            ".ini", ".conf", ".cfg", ".toml", ".xml", ".properties", ".sql", ".md5"}
# 源码/文档扩展名（只查 JWT 类硬泄漏，名字提及降级为 WARN）
SRC_EXT = {".py", ".md", ".sh", ".bash", ".zsh", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".rb", ".go"}
# ③ 显式点名的"二进制/归档/媒体/办公"扩展名：它们本来就不在 DATA_EXT ∪ SRC_EXT 里
#    （旧版同样不扫内容），此处只为把剪枝**分类记账**，让"二进制不扫"这条边界在自报里看得见。
#    **不得与 DATA_EXT/SRC_EXT 重叠**（自检 S3 有断言，防止把文本误剪）。
BINARY_EXT = {
    ".zip", ".gz", ".tgz", ".tar", ".bz2", ".xz", ".7z", ".rar", ".whl", ".egg",
    ".node", ".so", ".dylib", ".dll", ".exe", ".bin", ".dat", ".o", ".a", ".class",
    ".jar", ".war", ".pyc", ".pyo", ".pyd", ".wasm",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tif", ".tiff",
    ".psd", ".ai", ".eps", ".svgz", ".pdf", ".xls", ".xlsx", ".doc", ".docx", ".ppt", ".pptx",
    ".mp3", ".mp4", ".m4a", ".mov", ".avi", ".mkv", ".wav", ".flac", ".ogg", ".webm",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".sqlite", ".sqlite3", ".db", ".parquet", ".arrow", ".feather", ".pkl", ".npy", ".npz",
    ".pt", ".onnx", ".h5", ".pb", ".log", ".out", ".err", ".dSYM",
}

CONTENT_RULES = [
    # 任意文本文件都查：JWT / 会话 cookie
    ("jwt", "ERROR", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,}")),
    ("session_cookie", "ERROR", re.compile(r"app_session_id\s*[=:]\s*[\"']?eyJ")),
    # 仅数据文件查：字面量密码
    ("password_literal", "ERROR", re.compile(r"[\"']?password[\"']?\s*[:=]\s*[\"'][^\"'\s]{3,}[\"']", re.I)),
    ("daniel_password_literal", "ERROR", re.compile(r"DANIEL_PASSWORD\s*[:=]\s*[\"']?[^\s\"']{3,}")),
    ("email_password_pair", "ERROR", re.compile(r"[\"']?email[\"']?\s*[:=]\s*[\"'][^\"'\s]+@[^\"'\s]+[\"'][\s\S]{0,200}?[\"']?password[\"']?\s*[:=]", re.I)),
]
# ③ 仅这些"数据文件"跑 password_literal 等规则（源码不算）
DATA_ONLY = {"password_literal", "daniel_password_literal", "email_password_pair"}
# ④ 源码/文档里的"仅提及"信号 → WARN
MENTION_RE = re.compile(r"DANIEL_(EMAIL|PASSWORD)|daniel_cred|daniel_session|\.daniel_cred\.json|\.daniel_session\.json")
# ⑤ 同一行明显是"自检夹具/脱敏样例" → 把 JWT/cookie 命中降级为 WARN（例：daniel_mentions.py 的自检）
FIXTURE_RE = re.compile(r"scrub|redact|self[-_]?test|fixture|fake|脱敏|自检|example\.invalid|zzzsecret|hunter2", re.I)

# ⑥ 字节级门（TICKET-151 C2 提速的关键；**改上面任何规则时必须同步核这里**）。
#    每条规则列出它的**必要字面量**：只要有一个不在字节里，这条规则无论怎么扫都不可能命中，
#    于是整条跳过（既不解码也不跑正则）。**大小写按规则本身的敏感度来**——正则区分大小写的
#    就用精确大小写门（更严、更省），正则带 re.I 的才用小写门：
#      jwt                     → "eyJ"（正则区分大小写；用精确大小写可挡掉 base64 里偶然出现的 "eyj"）
#      session_cookie          → "app_session_id"（区分大小写）
#      password_literal        → "password"（re.I）
#      daniel_password_literal → "DANIEL_PASSWORD"（区分大小写；比 "password" 严得多）
#      email_password_pair     → "email" **且** "password"（re.I，两个都要）
#      mention:*               → DANIEL_EMAIL／DANIEL_PASSWORD／daniel_cred／daniel_session（区分大小写；
#                                `\.daniel_cred\.json` 之类都含前两者之一）
#    故"门为空"⇒"任何规则都不可能命中"，预筛不会漏报。自检 S4 对语料**逐规则逐文件**断言该性质。
#: (规则名, 精确大小写 needle, 需要全部命中的小写 needle)
RULE_GATES = (
    ("jwt", (b"eyJ",), ()),
    ("session_cookie", (b"app_session_id",), ()),
    ("password_literal", (), (b"password",)),
    ("daniel_password_literal", (b"DANIEL_PASSWORD",), ()),
    ("email_password_pair", (), (b"email", b"password")),
    ("mention", (b"DANIEL_EMAIL", b"DANIEL_PASSWORD", b"daniel_cred", b"daniel_session"), ()),
)
#: 文件级 needle（任一命中才值得看内容）；＝ 全部精确 needle ＋ 全部小写 needle 的并集
NEEDLES = tuple(sorted({n for _r, exact, ci in RULE_GATES for n in exact + ci}))


def _gates(raw):
    """算出"哪几条规则值得跑"（与规则的大小写敏感度对齐，且**少扫几遍**就是快）。

    逐规则的等价性论证见 `RULE_GATES` 上方注释。实现上把"全缓冲区扫一遍"的次数压到最少：
    小写 1 遍（re.I 规则用）、"password" 1 遍、"eyJ"/"app_session_id" 各 1 遍、
    DANIEL/daniel 1~2 遍；其余 needle 只在上一层已命中时才对比（例如 "DANIEL_PASSWORD" 只在
    文件确实含 DANIEL/daniel 时才查）——常见情形（一个 needle 都没有）只付 5 遍。

    返回 frozenset(规则名)；空集＝这个文件一条规则都不需要跑（既不解码也不跑正则）。
    自检 S4 对语料**逐规则逐文件**断言"门没开的规则一定不命中"，不靠人眼。
    """
    on = set()
    low = raw.lower()                                        # 1 遍：re.I 规则（password_literal／email_password_pair）
    if b"password" in low:
        on.add("password_literal")
        if b"email" in low:                                  # 只有含 password 的文件才付这一遍
            on.add("email_password_pair")
    if b"eyJ" in raw:
        on.add("jwt")
    if b"app_session_id" in raw:
        on.add("session_cookie")
    if b"DANIEL" in raw or b"daniel" in raw:
        if b"DANIEL_PASSWORD" in raw:
            on.add("daniel_password_literal")
        if (b"DANIEL_PASSWORD" in raw or b"DANIEL_EMAIL" in raw
                or b"daniel_cred" in raw or b"daniel_session" in raw):
            on.add("mention")
    return frozenset(on)

# ⑦ 扫描上限（TICKET-151 C2）：≤FULL_SCAN_MAX 全量读（**与旧版 MAX_BYTES 同值，灵敏度零变化**）；
#    >FULL_SCAN_MAX 只读头 HEAD_WINDOW ＋ 尾 TAIL_WINDOW（旧版对这种文件**完全不扫**，故只增不减）。
FULL_SCAN_MAX = 4 * 1024 * 1024
HEAD_WINDOW = 1 * 1024 * 1024
TAIL_WINDOW = 256 * 1024
UNLIMITED = 1 << 62                           # `--full-scan` 的"无限大"哨兵（整数，便于进 JSON）
MAX_BYTES = FULL_SCAN_MAX                     # 旧名保留，指向同一阈值

#: 内容扫描并发（可用 --jobs / --procs / 环境变量覆盖）
DEFAULT_JOBS = 8
JOBS_ENV = "KOL_DIST_SCAN_JOBS"
#: 进程层并发：剩下的活是 CPU（`lower`／`find`／正则）而不是 I/O，线程会被 GIL 串起来，
#: 所以用少量进程真并行；`--procs 1` 可关掉（退回线程池）。
DEFAULT_PROCS = 6
PROCS_ENV = "KOL_DIST_SCAN_PROCS"
#: 文件数少于这个规模就不起进程（自检夹具／小目录：起进程比扫还贵）
PROC_MIN_FILES = 400

#: scan_dir 逐文件的处置标记（进"扫描面自报"）
S_FULL, S_WINDOW, S_NAME_ONLY, S_BINARY, S_UNREADABLE = (
    "scan-full", "scan-window", "name-only", "binary-skipped", "unreadable")


def _is_text(path, ext):
    return ext in DATA_EXT or ext in SRC_EXT or ext == ""


def redact(matched):
    """**绝不回显命中内容**：只回长度与形状，避免把真凭据打进日志/终端。"""
    s = matched or ""
    return "<%d 字符已脱敏>" % len(s)


def _rules_match(text, ext):
    """**只给自检用**：跳过门直接跑全部规则，回答"这段文本是否可能命中任何规则"。"""
    if MENTION_RE.search(text):
        return True
    for rule, _sev, rx in CONTENT_RULES:
        if rule in DATA_ONLY and ext not in DATA_EXT:
            continue
        if rx.search(text):
            return True
    return False


def _hit(severity, rule, path, line, snippet, window=""):
    h = {"severity": severity, "rule": rule, "path": path, "line": line, "snippet": snippet}
    if window:
        h["truncated"] = True
        h["window"] = window
    return h


#: 每条规则的"候选起点"口径（TICKET-151 C2 提速）：(needle, 是否大小写不敏感, 起点是否可比 needle 早 1 字符)
#: 依据是各条正则的**开头**：`["']?password`／`["']?email` 的 `["']?` 最多吃掉 1 个字符，所以真实命中
#: 的起点只可能是 needle 位置本身或它前一格；`\beyJ` 的 `\b` 是零宽的，只需 needle 位置本身。
#: `mention` 不在表里（它的备选里有 `\.daniel_cred\.json` 这种真正多一个字符的形状，且它本来就便宜）。
RULE_STARTS = {
    "jwt": (b"eyJ", False, False),
    "session_cookie": (b"app_session_id", False, False),
    "password_literal": (b"password", True, True),
    "daniel_password_literal": (b"DANIEL_PASSWORD", False, False),
    "email_password_pair": (b"email", True, True),
}
#: 需要小写文本才能找候选的规则（＝ re.I 的那几条）
CI_RULES = frozenset(r for r, (_n, ci, _l) in RULE_STARTS.items() if ci)


def _candidate_starts(hay, needle, lead):
    """needle 在 hay 里的全部出现位置（`lead` 为真时再补上前一格），**直接产出升序列表**。

    不用 set/sorted：needle 位置本身已升序，每个位置最多再补一个"前一格"，顺序天然有序，
    去重只需比对上一个元素——命中密集的大文件（一个 4MB crawl 里几万处 "email"）就靠这步省时间。
    """
    out = []
    i = hay.find(needle)
    while i != -1:
        if lead and i and (not out or out[-1] != i - 1):
            out.append(i - 1)
        if not out or out[-1] != i:
            out.append(i)
        i = hay.find(needle, i + 1)
    return out


def _anchored_finditer(rx, text, starts):
    """只在候选起点上跑 `rx.match`，**复刻 `rx.finditer` 的"从左到右、互不重叠"语义**。

    等价性：规则的必要字面量必定出现在每个真实命中里，且候选集包含了"字面量位置 ± 允许的前导"，
    所以任何真实命中的起点都在候选集内；再按 `finditer` 的规则（命中后从 `m.end()` 继续、跳过更早
    的位置）遍历，得到的命中序列与全文件 `finditer` 完全一致——把"整文件扫一遍正则"降成
    "几次 `str.find` ＋ 少量锚定尝试"，命中的行号/片段长度都不变。
    """
    pos = 0
    for q in starts:
        if q < pos:
            continue
        m = rx.match(text, q)
        if m is not None:
            yield m
            pos = m.end()


def _scan_text(text, ext, strict_jwt, hits, path, line_offset=0, window="", gates=None):
    """在**已解码文本**上跑规则（与旧版逐行等价；只多 line_offset/window 与 gate 三个提速参数）。

    两条提速（TICKET-151 C2）：
      · 行号用**增量游标**算（`cursor` 只前进、不回头），把旧版"每命中一次就从文件头
        `count("\\n")`"的 O(命中数 × 文件长度) 降成 O(文件长度)——命中密集的大文件正是旧版最慢处；
      · 命中候选**锚定**在必要字面量的位置上（见 `_anchored_finditer`），把"整文件跑正则"降成
        "几次 `str.find` ＋ 少量 `rx.match`"。非 ASCII 文本（大小写映射会错位）退回原 `finditer`。
    """
    run_all = gates is None
    cred_context = None
    low = None
    if run_all or (gates & CI_RULES):
        low = text.lower() if text.isascii() else None
    for rule, sev, rx in CONTENT_RULES:
        if not run_all and rule not in gates:
            continue
        if rule in DATA_ONLY and ext not in DATA_EXT:
            continue
        if rule == "jwt" and cred_context is None:
            cred_context = bool(MENTION_RE.search(text)) or "app_session_id" in text
        starts = None
        if rule in RULE_STARTS:
            needle, ci, lead = RULE_STARTS[rule]
            hay = low if ci else text
            if hay is not None:
                starts = _candidate_starts(hay, needle.decode("ascii"), lead)
        finder = rx.finditer(text) if starts is None else _anchored_finditer(rx, text, starts)
        line_no, line_start, cursor = 1, 0, 0
        for m in finder:
            pos = m.start()
            seg = text[cursor:pos]
            nl = seg.count("\n")
            if nl:
                line_no += nl
                line_start = cursor + seg.rfind("\n") + 1
            cursor = pos
            le = text.find("\n", pos)
            line_text = text[line_start:le if le != -1 else len(text)]
            rule_name, severity = rule, sev
            if rule in ("jwt", "session_cookie") and FIXTURE_RE.search(line_text):
                # 同一行出现 scrub/redact/fake/自检夹具 等标记 → 自检样例，不是真凭据
                severity, rule_name = "WARN", rule + ":likely-test-fixture"
            elif rule == "jwt" and not (strict_jwt or cred_context):
                # 与本项目凭据无关的 JWT 形串（第三方源码/data 里的公开 token）→ 降级为告警，
                # 避免把 yt-dlp 之类的 vendored 测试 token 当成我们的泄漏而阻塞打包。
                severity, rule_name = "WARN", "jwt:no-cred-context"
            hits.append(_hit(severity, rule_name, path, line_no + line_offset,
                             redact(m.group(0)), window))
    if run_all or "mention" in gates:
        line_no, cursor = 1, 0
        for m in MENTION_RE.finditer(text):
            pos = m.start()
            line_no += text.count("\n", cursor, pos)
            cursor = pos
            hits.append(_hit("WARN", "mention:%s" % m.group(0), path, line_no + line_offset,
                             m.group(0), window))
            # ↑ 只是变量名/文件名，非密钥
    return hits


def _window_texts(path, size):
    """>FULL_SCAN_MAX 的文件：读头 HEAD_WINDOW ＋ 尾 TAIL_WINDOW。

    返回 `(segs, is_binary)`，segs ＝ [(line_offset, window_name, text, gates)]。窗口含 NUL 字节
    → `is_binary=True`（按"二进制不扫"处理）。头窗口行号精确（自第 1 行起）；尾窗口行号以
    "头窗口行数＋1"起算，是**近似下界**（中段未读），报告里会标注。窗口里门全空
    → 该窗口不进 segs（无需解码、无需跑正则）。
    """
    with open(path, "rb") as f:
        head = f.read(HEAD_WINDOW)
        tail = b""
        if size > HEAD_WINDOW:
            f.seek(max(0, size - TAIL_WINDOW))
            tail = f.read()
    if b"\x00" in head:
        return [], True
    out = []
    head_gates = _gates(head)
    head_text = head.decode("utf-8", errors="ignore") if head_gates else ""
    if head_gates:
        out.append((0, "head", head_text, head_gates))
    if tail and b"\x00" not in tail:
        tail_gates = _gates(tail)
        if tail_gates:
            out.append((head_text.count("\n") + 1, "tail",
                        tail.decode("utf-8", errors="ignore"), tail_gates))
    return out, False


def scan_path(path, strict_jwt=False, size=None):
    """扫单个文件，返回 (hits, 处置标记, 文件大小字节)。

    处置标记 ∈ S_FULL（内容全量扫）／S_WINDOW（按上限扫头尾）／S_NAME_ONLY（非文本扩展名，
    只看文件名）／S_BINARY（文本扩展名但内容是二进制，不扫）／S_UNREADABLE（stat/读 失败，
    例如断链符号链接）。片段一律脱敏，文件名可显示。
    """
    hits = []
    base = os.path.basename(path)
    if size is None:
        try:
            size = os.path.getsize(path)
        except OSError:
            return hits, S_UNREADABLE, -1
    for pat in BAD_NAME_PATTERNS:
        if re.match(pat, base, re.I):
            hits.append({"severity": "ERROR", "rule": "filename:%s" % pat, "path": path,
                         "line": 0, "snippet": base})       # 文件名本身不是密钥，可显示
            break
    ext = os.path.splitext(base)[1].lower()
    if not _is_text(path, ext) or os.path.abspath(path) == SELF:
        return hits, S_NAME_ONLY, size                            # 非文本扩展名 → 二进制不扫
    if size <= FULL_SCAN_MAX:
        # 与旧版同口径：整文件读取；严格 UTF-8 解码失败（二进制）→ 只看文件名。
        # 提速点①：先算字节门；门为空 ⇒ 任何规则都不可能命中 → 不解码、不跑正则，直接过。
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError:
            return hits, S_UNREADABLE, size
        gates = _gates(raw)
        if not gates:
            return hits, S_FULL, size
        try:
            text = raw.decode("utf-8")            # errors="strict"：与旧版一致
        except UnicodeDecodeError:
            return hits, S_BINARY, size           # 文本扩展名但内容是二进制 → 不扫
        _scan_text(text, ext, strict_jwt, hits, path, gates=gates)
        return hits, S_FULL, size
    # 旧版在此处**整文件不扫**；新版按上限扫头尾（覆盖只增不减）。
    try:
        segs, window_binary = _window_texts(path, size)
    except OSError:
        return hits, S_UNREADABLE, size
    if window_binary:
        return hits, S_BINARY, size               # 窗口含 NUL → 按"二进制不扫"处理
    for off, win, text, gates in segs:
        _scan_text(text, ext, strict_jwt, hits, path, line_offset=off, window=win, gates=gates)
    return hits, S_WINDOW, size


def walk_files(target, scan_archives=False):
    """`os.scandir` 递归列文件（按目录名剪枝；断链/不可读目录单独记账，不静默丢）。

    同级条目按名排序，保证遍历与计数可复现；命中集合最后统一排序，故并发不影响结果。
    """
    files, pruned_dirs, unreadable = [], [], []
    stack = [target]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            unreadable.append({"path": d, "error": exc.strerror or str(exc)})
            continue
        for e in entries:
            if e.is_dir(follow_symlinks=False):        # 与 os.walk(followlinks=False) 同语义
                if e.name in SKIP_DIRS:
                    pruned_dirs.append({"path": e.path, "reason": "固定目录名"})
                    continue
                if not scan_archives and e.name.startswith(SKIP_DIR_PREFIXES):
                    pruned_dirs.append({"path": e.path, "reason": "归档目录前缀"})
                    continue
                stack.append(e.path)
            else:
                files.append(e)
    return files, pruned_dirs, unreadable


def _default_jobs():
    raw = os.environ.get(JOBS_ENV)
    if raw:
        try:
            n = int(raw)
            if n >= 1:
                return n
        except ValueError:
            pass
    return DEFAULT_JOBS


def _default_procs():
    raw = os.environ.get(PROCS_ENV)
    if raw:
        try:
            n = int(raw)
            if n >= 1:
                return n
        except ValueError:
            pass
    return min(DEFAULT_PROCS, os.cpu_count() or 1)


def _scan_shard(paths, strict_jwt, acc):
    """扫一段文件清单，把结果累加进 `acc`（子进程里跑；只回传这份**汇总**，不回传逐文件结果）。"""
    for p in paths:
        h, flag, size = scan_path(p, strict_jwt=strict_jwt)
        _accumulate(p, h, flag, size, acc)
    return acc


def _new_acc():
    return {"hits": [], "counts": {S_FULL: 0, S_WINDOW: 0, S_NAME_ONLY: 0, S_BINARY: 0,
                                   S_UNREADABLE: 0},
            "bytesRead": 0, "truncated": [], "nameOnlyOther": {}, "nameOnlyBinary": 0}


def _accumulate(path, hits, flag, size, acc):
    """把单文件结果并进汇总（进程内外共用同一套记账，避免两条路算出两个口径）。"""
    acc["hits"].extend(hits)
    acc["counts"][flag] = acc["counts"].get(flag, 0) + 1
    if flag == S_FULL:
        acc["bytesRead"] += max(size or 0, 0)
    elif flag == S_WINDOW:
        acc["bytesRead"] += min(size or 0, HEAD_WINDOW) + (TAIL_WINDOW if (size or 0) > HEAD_WINDOW else 0)
        acc["truncated"].append({"path": path, "bytes": size})
    elif flag == S_NAME_ONLY:
        ext = os.path.splitext(os.path.basename(path))[1].lower()
        if ext in BINARY_EXT:
            acc["nameOnlyBinary"] += 1
        else:
            key = ext or "<无扩展名>"
            acc["nameOnlyOther"][key] = acc["nameOnlyOther"].get(key, 0) + 1
    return acc


def _merge_acc(dst, src):
    dst["hits"].extend(src["hits"])
    for k, v in src["counts"].items():
        dst["counts"][k] = dst["counts"].get(k, 0) + v
    dst["bytesRead"] += src["bytesRead"]
    dst["truncated"].extend(src["truncated"])
    dst["nameOnlyBinary"] += src["nameOnlyBinary"]
    for k, v in src["nameOnlyOther"].items():
        dst["nameOnlyOther"][k] = dst["nameOnlyOther"].get(k, 0) + v
    return dst


def can_fork():
    """这台机器／这个平台能不能用 fork 分片。

    **Windows 没有 `os.fork`**，所以不能写死"用进程"：拿不到就返回 False，调用方自动退回线程池
    ——功能不降级、结果不变、也不报错，只影响快慢。
    """
    return (os.name == "posix" and hasattr(os, "fork")
            and sys.platform not in ("win32", "cygwin"))


def _reap(pids, blocking):
    """回收子进程，返回"异常退出"的个数（`blocking=False` 时只收已结束的，用于异常路径兜底）。"""
    bad = 0
    for pid in list(pids):
        try:
            wpid, status = os.waitpid(pid, 0 if blocking else os.WNOHANG)
        except OSError:                     # 已被回收／不存在 → 无需再管
            pids.remove(pid)
            continue
        if wpid == 0:                       # WNOHANG：还没结束，留着下轮再收
            continue
        pids.remove(pid)
        if not (os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0):
            bad += 1
    return bad


def _fork_scan(paths, strict_jwt, procs):
    """用 fork 起 `procs` 个子进程各扫一片，**经临时文件**回传汇总；失败抛异常由调用方回退。

    为什么不用 `ProcessPoolExecutor`：它要把 worker 函数按"模块名.函数名"序列化到子进程，
    而本模块既可能被当脚本跑、也可能被别的脚本 import（`__main__`／自定义模块名解析会失败，
    实测报 `Can't pickle … import of module … failed`）。fork ＋ 临时文件只需要回传**普通数据**，
    且天然继承父进程内存（`--full-scan` 改过的阈值也一并继承），没有这层脆弱性。

    为什么读结果用临时文件而不是管道：子进程结果可能超过管道缓冲区，父进程若串行读会死锁；
    临时文件没有这个限制。

    资源卫生：**所有 fork 出来的子进程都会被 `waitpid` 回收**——正常路径阻塞回收，异常路径
    （fork 半途失败等）在 `finally` 里非阻塞兜底回收，不留僵尸。
    """
    import pickle
    import tempfile
    n = min(procs, len(paths))
    size = (len(paths) + n - 1) // n
    shards = [paths[i:i + size] for i in range(0, len(paths), size)]
    tmpdir = tempfile.mkdtemp(prefix="t151-scan-")
    out_paths, pids = [], []
    try:
        for i, shard in enumerate(shards):
            fd, p = tempfile.mkstemp(dir=tmpdir, prefix="shard%d-" % i)
            try:
                pid = os.fork()
            except OSError:
                os.close(fd)
                raise
            if pid == 0:                                   # 子进程
                code = 0
                try:
                    acc = _scan_shard(shard, strict_jwt, _new_acc())
                    with os.fdopen(fd, "wb") as fh:
                        pickle.dump(acc, fh, protocol=4)
                except BaseException:                      # noqa: BLE001（任何失败都让父进程回退）
                    code = 1
                finally:
                    os._exit(code)
            os.close(fd)
            pids.append(pid)
            out_paths.append(p)
        bad = _reap(pids, blocking=True)
        if bad:
            raise RuntimeError("%d 个扫描子进程异常退出" % bad)
        acc = _new_acc()
        for p in out_paths:
            with open(p, "rb") as fh:
                _merge_acc(acc, pickle.load(fh))
        return acc
    finally:
        _reap(pids, blocking=False)                        # 异常路径兜底：不留僵尸
        shutil.rmtree(tmpdir, ignore_errors=True)


def _scan_entries(paths, strict_jwt, jobs, procs):
    """返回 (汇总 acc, 实际用的进程数)。并发层不改变结果：命中最后统一排序，逐文件记账同一套。

    进程层：`procs > 1` 且文件够多且**平台支持 fork**（`can_fork()`）时才走；任何异常都静默
    退回线程池——不报错、不降功能，只是慢一点（Windows 走的就是这条路）。线程层：`jobs > 1`。
    """
    if procs > 1 and len(paths) >= PROC_MIN_FILES and can_fork():
        try:
            return _fork_scan(paths, strict_jwt, procs), min(procs, len(paths))
        except Exception:                                  # noqa: BLE001（起不来就回退，不改变结果）
            pass
    acc = _new_acc()
    if jobs > 1 and len(paths) > 1:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for p, (h, flag, size) in zip(paths, pool.map(
                    lambda q: scan_path(q, strict_jwt=strict_jwt), paths)):
                _accumulate(p, h, flag, size, acc)
    else:
        for p in paths:
            h, flag, size = scan_path(p, strict_jwt=strict_jwt)
            _accumulate(p, h, flag, size, acc)
    return acc, 0


def scan_dir(target, strict_jwt=False, jobs=None, scan_archives=False, procs=None):
    """扫一个目录，返回 (hits, surface)。hits 已按 (路径, 行号, 规则, 严重级) 排序 → 并发不改结果。"""
    if jobs is None:
        jobs = _default_jobs()
    if procs is None:
        procs = _default_procs()

    entries, pruned_dirs, unreadable_dirs = walk_files(target, scan_archives)
    acc, used_procs = _scan_entries([e.path for e in entries], strict_jwt, jobs, procs)

    hits = acc["hits"]
    counts = acc["counts"]
    n_full = counts.get(S_FULL, 0)
    n_window = counts.get(S_WINDOW, 0)
    n_name = counts.get(S_NAME_ONLY, 0)
    n_bin = counts.get(S_BINARY, 0)
    n_bad = counts.get(S_UNREADABLE, 0)
    truncated_files = acc["truncated"]
    name_only_other = acc["nameOnlyOther"]
    n_binary_ext = acc["nameOnlyBinary"]
    n_bytes = acc["bytesRead"]

    hits.sort(key=lambda h: (h["path"], h["line"], h["rule"], h["severity"]))
    surface = {
        "target": os.path.abspath(target),
        "totalFiles": len(entries),
        "prunedDirs": pruned_dirs,
        "prunedDirCount": len(pruned_dirs),
        "nameOnlyFiles": n_name,
        "nameOnlyBinaryExt": n_binary_ext,
        "nameOnlyOtherExt": name_only_other,
        "scannedFull": n_full,
        "scannedWindow": n_window,
        "binarySkippedFiles": n_bin,
        "truncatedFiles": truncated_files,
        "unreadableFiles": n_bad,
        "unreadableDirs": unreadable_dirs,
        "bytesRead": n_bytes,
        "jobs": jobs,
        "procs": used_procs,
        "fullScanMaxBytes": FULL_SCAN_MAX,
        "headWindowBytes": HEAD_WINDOW,
        "tailWindowBytes": TAIL_WINDOW,
    }
    return hits, surface


def merge_surfaces(surfaces):
    """把多个目录的扫描面合成一份（报告口径）。"""
    merged = {
        "totalFiles": 0, "nameOnlyFiles": 0, "scannedFull": 0, "scannedWindow": 0,
        "unreadableFiles": 0, "bytesRead": 0, "prunedDirCount": 0, "nameOnlyBinaryExt": 0,
        "binarySkippedFiles": 0, "prunedDirs": [], "truncatedFiles": [], "unreadableDirs": [],
        "nameOnlyOtherExt": {}, "jobs": None, "procs": None, "targets": [],
        "fullScanMaxBytes": FULL_SCAN_MAX,
        "headWindowBytes": HEAD_WINDOW, "tailWindowBytes": TAIL_WINDOW,
    }
    for s in surfaces:
        merged["targets"].append(s["target"])
        for k in ("totalFiles", "nameOnlyFiles", "scannedFull", "scannedWindow",
                  "binarySkippedFiles", "unreadableFiles", "bytesRead", "prunedDirCount",
                  "nameOnlyBinaryExt"):
            merged[k] += s[k]
        merged["prunedDirs"] += s["prunedDirs"]
        merged["truncatedFiles"] += s["truncatedFiles"]
        merged["unreadableDirs"] += s["unreadableDirs"]
        for ext, n in s["nameOnlyOtherExt"].items():
            merged["nameOnlyOtherExt"][ext] = merged["nameOnlyOtherExt"].get(ext, 0) + n
        merged["jobs"] = s["jobs"]
        merged["procs"] = s.get("procs")
    return merged


def _print_surface(surface, out=None):
    out = out or sys.stdout
    print("── 扫描面自报（复核用：剪了什么、截了什么，都在这儿）──", file=out)
    print("  目录：%s" % "、".join(surface["targets"] or ["<无>"]), file=out)
    print("  文件总数 %d ＝ 内容全量扫 %d ＋ 按上限扫 %d ＋ 非文本扩展名只看文件名 %d "
          "＋ 内容是二进制不扫 %d ＋ 不可读 %d"
          % (surface["totalFiles"], surface["scannedFull"], surface["scannedWindow"],
             surface["nameOnlyFiles"], surface.get("binarySkippedFiles", 0),
             surface["unreadableFiles"]), file=out)
    print("  剪枝跳过：目录 %d 个；非文本扩展名文件 %d 个（其中二进制/归档/媒体/办公扩展名 %d 个）"
          % (surface["prunedDirCount"], surface["nameOnlyFiles"], surface["nameOnlyBinaryExt"]),
          file=out)
    other = surface["nameOnlyOtherExt"]
    if other:
        top = sorted(other.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
        print("  非文本扩展名分布（前 12；含无扩展名）：%s"
              % "、".join("%s×%d" % (k, v) for k, v in top), file=out)
    _layers = ("进程 %d 个（各进程串行扫一片，进程内不再起线程）" % surface["procs"]
               if surface.get("procs")
               else "线程 %s（进程层未启用：平台不支持 fork／文件数不足 %d／用户给了 --procs 1）"
                    % (surface.get("jobs"), PROC_MIN_FILES))
    print("  按上限扫描（头 %d KiB＋尾 %d KiB，实际读取约 %.1f MB）：%d 个文件；并发层：%s"
          % (HEAD_WINDOW // 1024, TAIL_WINDOW // 1024, surface["bytesRead"] / 1e6,
             surface["scannedWindow"], _layers), file=out)
    if surface["truncatedFiles"]:
        for t in surface["truncatedFiles"][:200]:
            print("    · 已按上限扫描：%s（%.2f MB）" % (t["path"], (t["bytes"] or 0) / 1e6), file=out)
        extra = len(surface["truncatedFiles"]) - 200
        if extra > 0:
            print("    · …另有 %d 个（完整清单见 --json 的 scanSurface.truncatedFiles）" % extra,
                  file=out)
    if surface["prunedDirs"]:
        for d in surface["prunedDirs"][:20]:
            print("    · 目录剪枝（%s）：%s" % (d["reason"], d["path"]), file=out)
        extra = len(surface["prunedDirs"]) - 20
        if extra > 0:
            print("    · …另有 %d 个剪枝目录（完整清单见 --json 的 scanSurface.prunedDirs）" % extra,
                  file=out)
    for d in surface["unreadableDirs"][:10]:
        print("    · 目录不可读（跳过）：%s —— %s" % (d["path"], d["error"]), file=out)
    print("  边界：非文本扩展名不扫内容；>%d MiB 只扫头尾（--help 有完整边界说明）"
          % (FULL_SCAN_MAX // 1024 // 1024), file=out)


def report(targets, hits, args, surface=None):
    errs = [h for h in hits if h["severity"] == "ERROR"]
    warns = [h for h in hits if h["severity"] == "WARN"]
    if args.json:
        doc = {"targets": targets, "errors": errs, "warnings": warns,
               "errorCount": len(errs), "warnCount": len(warns)}
        if surface is not None:
            doc["scanSurface"] = surface
        print(json.dumps(doc, ensure_ascii=False, indent=1))
        return
    for h in errs:
        print("❌ [%s] %s:%s  %s%s" % (h["rule"], h["path"], h["line"], h["snippet"],
                                      _window_mark(h)))
    for h in warns[:40]:
        print("⚠️  [%s] %s:%s%s" % (h["rule"], h["path"], h["line"], _window_mark(h)))
    if len(warns) > 40:
        print("⚠️  … 另有 %d 条同名提及（源码/文档引用，非泄漏）" % (len(warns) - 40))
    if surface is not None:
        print()
        _print_surface(surface)


def _window_mark(h):
    """命中落在">4 MiB 只扫头尾"的窗口里时，逐条标注（不做静默截断）。"""
    if not h.get("truncated"):
        return ""
    return "　（已按上限扫描：%s 窗口内，行号为近似值）" % ("头部" if h.get("window") == "head" else "尾部")


# ─────────────────────────── 自检 ───────────────────────────
def _write(path, text, mode="w"):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    kw = {} if "b" in mode else {"encoding": "utf-8"}
    with open(path, mode, **kw) as f:
        f.write(text)
    return path


def _fixtures(tmp):
    """造夹具并返回 (root, meta)。旧 6 条 + TICKET-151 新增：真阴性 5 条、正控 2 条、语料 1 组。"""
    FAKE_PW = "hunter2-fake-value"
    FAKE_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmYWtlIn0.SflKxwRJSMeKKF2QT4"
    meta = {"FAKE_PW": FAKE_PW, "FAKE_JWT": FAKE_JWT}

    # 正控：含假凭据
    pos = os.path.join(tmp, "positive")
    _write(os.path.join(pos, ".daniel_cred.json"),
           '{"email": "fake-user@example.invalid", "password": "%s"}\n' % FAKE_PW)
    _write(os.path.join(pos, "secrets", "session.json"),
           '{"cookie": "app_session_id=%s"}\n' % FAKE_JWT)
    _write(os.path.join(pos, "notes.txt"), "DANIEL_PASSWORD=%s\n" % FAKE_PW)

    # 真阴性（旧）：干净目录
    neg = os.path.join(tmp, "negative")
    _write(os.path.join(neg, "README.md"), "# 打包说明\n全部为公开产物。\n")
    _write(os.path.join(neg, "data.json"), '{"brands": [{"id": 1, "name": "Halliday"}]}\n')
    _write(os.path.join(neg, "app.py"), "import os\nprint(os.name)\n")

    # 真阴性（旧）：仅提及（源码引用环境变量名）→ 0 ERROR
    men = os.path.join(tmp, "mention-only")
    _write(os.path.join(men, "client.py"),
           'import os\nE = os.environ.get("DANIEL_EMAIL")\nP = os.environ.get("DANIEL_PASSWORD")\n')

    # 真阴性（旧）：第三方 JWT（vendored 公开测试 token，无本项目凭据上下文）→ 0 ERROR
    vend = os.path.join(tmp, "vendored")
    _write(os.path.join(vend, "extractor.py"), 'TOKEN = "%s"\n' % FAKE_JWT)

    # ── TICKET-151 新增真阴性 5 条 ──────────────────────────────────────
    # TN1：变量名带后缀 → 0 ERROR（仅提及，最多 WARN）
    tn1 = os.path.join(tmp, "tn1-suffix-vars")
    _write(os.path.join(tn1, "config_reader.py"),
           'import os\n'
           'P2 = os.environ.get("DANIEL_PASSWORD_2")\n'
           'E2 = os.environ.get("DANIEL_EMAIL_PRIMARY")\n'
           'P3 = os.environ.get("DANIEL_PASSWORD_BACKUP")\n')

    # TN2：二进制文件里嵌入假凭据字符串 → 按设计跳过（"二进制不扫"）
    tn2 = os.path.join(tmp, "tn2-binary-blob")
    _write(os.path.join(tn2, "assets", "blob.bin"),
           b"\x89PNG\r\n\x1a\n\x00\x00" + ("DANIEL_PASSWORD=%s" % FAKE_PW).encode() +
           b"\x00" + ("app_session_id=%s" % FAKE_JWT).encode() + b"\x00\xff\xfe", "wb")
    _write(os.path.join(tn2, "assets", "icon.png"), b"\x89PNG\x00" + FAKE_JWT.encode(), "wb")

    # TN3：凭据拆行写入、值未加引号 → 0 ERROR（既有口径边界，已写进 --help）
    tn3 = os.path.join(tmp, "tn3-split-lines")
    _write(os.path.join(tn3, "notes.txt"), "password:\n%s\n" % FAKE_PW)
    _write(os.path.join(tn3, "creds.txt"),
           "email: fake-user@example.invalid\npassword:\n%s\n" % FAKE_PW)

    # TN4：干净的大文件（>FULL_SCAN_MAX）→ 0 命中，且被记为"按上限扫描"
    pad = '{"name": "public-row", "value": 12345}\n' * 300000       # ≈ 11 MB
    tn4 = os.path.join(tmp, "tn4-big-clean")
    _write(os.path.join(tn4, "big_clean.json"), pad)

    # TN5：非文本扩展名（.log/.out）里嵌入假凭据 → 按剪枝设计跳过（边界已写进 --help）
    tn5 = os.path.join(tmp, "tn5-nontext-ext")
    _write(os.path.join(tn5, "run.log"), "DANIEL_PASSWORD=%s\n" % FAKE_PW)
    _write(os.path.join(tn5, "dump.out"), "app_session_id=%s\n" % FAKE_JWT)

    # P4：大文件**尾部窗口**内藏凭据 → 必被报出且 truncated=true（旧版完全扫不到）
    p4 = os.path.join(tmp, "p4-big-tail")
    _write(os.path.join(p4, "big_tail.json"), pad + '{"t": "leak", "password": "%s"}\n' % FAKE_PW)

    # P5：`DANIEL_PASSWORD=` 的值写在**下一行** → 仍必被报出（\s* 跨行）
    p5 = os.path.join(tmp, "p5-split-assign")
    _write(os.path.join(p5, "env.txt"), "DANIEL_PASSWORD=\n%s\n" % FAKE_PW)

    # 语料：混合大小写 / 近似形状 / 只含 email 不含 password（本工作区 53% 的文件就是这种），
    # 用于**逐规则**断言"字节门不放过的规则，在任何文件上都不会命中"
    corpus = os.path.join(tmp, "corpus")
    _write(os.path.join(corpus, "mixed_case.json"),
           '{\n  "Email": "someone@example.invalid",\n  "passWord": "%s"\n}\n' % FAKE_PW)
    _write(os.path.join(corpus, "shouty.txt"), "PASSWORD: '%s'\n" % FAKE_PW)
    _write(os.path.join(corpus, "almost_jwt.txt"), "eyj-not-a-jwt\nEYJ0eXAiOiJKV1QifQ\n")
    _write(os.path.join(corpus, "words.txt"), "emails are passwords, daniel_credentialish\n")
    _write(os.path.join(corpus, "plain.json"), '{"note": "no credential here"}\n')
    # 关键负例：只含 email（无 password）→ password_literal／email_password_pair 的门必须关，
    # 且这两条规则确实不可能命中（旧版会给这种文件白跑 5 条正则，本工作区有 2.8 万个这种文件）
    _write(os.path.join(corpus, "email_only.json"),
           '{"email": "someone@example.invalid", "name": "nobody"}\n')
    # 只含 app_session_id 值但不是 JWT → session_cookie 门开、规则不命中
    _write(os.path.join(corpus, "cookie_not_jwt.txt"), "app_session_id=not-a-jwt\n")
    meta["corpus"] = corpus
    return tmp, meta


def self_test():
    """逐条断言并**打印用例条数**；任一条不过 → 退出码 3。

    分组：正控（必被报出）／真阴性（必须 0 命中）／开关与一致性（strict-jwt、并发确定性、
    字节预筛不漏报、扩展名口径不重叠）／退出码约定。
    """
    tmp = tempfile.mkdtemp(prefix="t144-distcheck-")
    checks = []

    def ck(cid, kind, desc, ok, detail=""):
        checks.append({"id": cid, "kind": kind, "desc": desc, "ok": bool(ok), "detail": detail})
        return bool(ok)

    try:
        _root, meta = _fixtures(tmp)
        FAKE_PW, FAKE_JWT = meta["FAKE_PW"], meta["FAKE_JWT"]
        pos, neg = os.path.join(tmp, "positive"), os.path.join(tmp, "negative")
        men, vend = os.path.join(tmp, "mention-only"), os.path.join(tmp, "vendored")
        tn1, tn2 = os.path.join(tmp, "tn1-suffix-vars"), os.path.join(tmp, "tn2-binary-blob")
        tn3, tn4 = os.path.join(tmp, "tn3-split-lines"), os.path.join(tmp, "tn4-big-clean")
        tn5, p4 = os.path.join(tmp, "tn5-nontext-ext"), os.path.join(tmp, "p4-big-tail")
        p5, corpus = os.path.join(tmp, "p5-split-assign"), meta["corpus"]

        ph, psurf = scan_dir(pos)
        nh = scan_dir(neg)[0]
        mh = scan_dir(men)[0]
        vh = scan_dir(vend)[0]
        pe = [h for h in ph if h["severity"] == "ERROR"]
        ne = [h for h in nh if h["severity"] in ("ERROR", "WARN")]
        me = [h for h in mh if h["severity"] == "ERROR"]
        ve = [h for h in vh if h["severity"] == "ERROR"]

        ck("C1", "正控", "含假凭据的目录必被报出（ERROR 命中 %d 条，规则：%s）"
           % (len(pe), "、".join(sorted({h["rule"] for h in pe}))), bool(pe), "期望 ≥1")
        leaked = [h for h in ph + mh + vh
                  if FAKE_PW in h.get("snippet", "") or FAKE_JWT in h.get("snippet", "")]
        ck("C2", "正控", "片段脱敏：回显里出现假凭据原文 %d 处（只回长度）" % len(leaked),
           not leaked, "期望 0")
        ck("N1", "真阴性", "干净目录（md/json/py）命中 %d 条" % len(ne), not ne, "期望 0")
        ck("N2", "真阴性", "仅提及环境变量名的源码 ERROR %d 条（WARN %d 条）"
           % (len(me), len([h for h in mh if h["severity"] == "WARN"])), not me, "期望 0")
        ck("N3", "真阴性", "第三方 JWT（无凭据上下文）ERROR %d 条（WARN %d 条）"
           % (len(ve), len([h for h in vh if h["severity"] == "WARN"])), not ve, "期望 0")
        strict_v = [h for h in scan_dir(vend, strict_jwt=True)[0] if h["severity"] == "ERROR"]
        ck("S1", "开关", "--strict-jwt 下同一目录 ERROR %d 条" % len(strict_v), strict_v, "期望 ≥1")

        n_tn1 = [h for h in scan_dir(tn1)[0] if h["severity"] == "ERROR"]
        ck("TN1", "真阴性", "变量名带后缀（DANIEL_PASSWORD_2／_BACKUP、DANIEL_EMAIL_PRIMARY）ERROR %d 条"
           % len(n_tn1), not n_tn1, "期望 0：只是提及，最多 WARN")

        nh2, s_tn2 = scan_dir(tn2)
        ck("TN2", "真阴性", "二进制文件内嵌假凭据（.bin/.png）命中 %d 条（该目录 %d/%d 个文件只看文件名）"
           % (len(nh2), s_tn2["nameOnlyFiles"], s_tn2["totalFiles"]), not nh2,
           "期望 0：按设计**二进制不扫内容**，见 --help 边界①")

        n_tn3 = [h for h in scan_dir(tn3)[0] if h["severity"] == "ERROR"]
        ck("TN3", "真阴性", "凭据拆行且值未加引号（password:＋换行＋值）ERROR %d 条" % len(n_tn3),
           not n_tn3, "期望 0：既有口径要求引号包裹，见 --help 边界④")

        nh4, s_tn4 = scan_dir(tn4)
        ck("TN4", "真阴性", "干净的大文件（>%.0f MiB）命中 %d 条、按上限扫描 %d 个文件"
           % (FULL_SCAN_MAX / 1024 / 1024, len(nh4), s_tn4["scannedWindow"]),
           not nh4 and s_tn4["scannedWindow"] == 1, "期望 0 命中且 scannedWindow=1")

        nh5 = scan_dir(tn5)[0]
        ck("TN5", "真阴性", "非文本扩展名（.log/.out）内嵌假凭据命中 %d 条" % len(nh5), not nh5,
           "期望 0：扩展名剪枝不扫内容，见 --help 边界①")

        p4e = [h for h in scan_dir(p4)[0] if h["severity"] == "ERROR"]
        ck("P4", "正控", "大文件**尾部窗口**内的凭据必被报出（ERROR %d 条，truncated=%s）"
           % (len(p4e), sorted({bool(h.get("truncated")) for h in p4e})), p4e,
           "期望 ≥1 且 truncated=true（旧版对 >4 MiB 完全不扫）")

        p5e = [h for h in scan_dir(p5)[0] if h["severity"] == "ERROR"]
        ck("P5", "正控", "DANIEL_PASSWORD= 的值写在下一行仍必被报出（ERROR %d 条）" % len(p5e),
           p5e, "期望 ≥1（\\s* 跨行）")

        h1 = scan_dir(pos, jobs=1)[0]
        h8 = scan_dir(pos, jobs=8)[0]
        key = lambda hs: sorted((h["path"], h["line"], h["rule"], h["severity"]) for h in hs)
        ck("S2", "一致性", "并发 8 与串行 1 的命中集合完全一致（各 %d 条）" % len(h1),
           key(h1) == key(h8), "期望一致（命中已按 路径/行号/规则 排序）")

        # S6：**并发层不影响结果**——串行／线程池／fork 分片三条路必须给出同一份命中集合与同一份汇总
        # （TICKET-151 C2 硬要求：命中集合与汇总计数都不许随并发数变化）
        paths6 = []
        for dp, _dn, fn in os.walk(pos):
            paths6 += [os.path.join(dp, f) for f in sorted(fn)]
        paths6 = [q for q in paths6 if os.path.isfile(q)]

        def _acc_key(a):
            return (sorted((h["path"], h["line"], h["rule"], h["severity"], h["snippet"])
                           for h in a["hits"]),
                    sorted(a["counts"].items()), a["bytesRead"], a["nameOnlyBinary"],
                    sorted(a["truncated"], key=lambda d: d["path"] or ""),
                    sorted(a["nameOnlyOther"].items()))

        serial_acc = _new_acc()
        for q in paths6:
            _scan_shard([q], False, serial_acc)
        pool_acc = _new_acc()
        with ThreadPoolExecutor(max_workers=4) as _tp:
            for q, (hh, ff, ss) in zip(paths6, _tp.map(lambda z: scan_path(z), paths6)):
                _accumulate(q, hh, ff, ss, pool_acc)
        same3 = _acc_key(serial_acc) == _acc_key(pool_acc)
        fork_note = "本平台不支持 fork，进程层跳过（自动退回线程池，结果不变）"
        if can_fork():
            try:
                same3 = same3 and _acc_key(serial_acc) == _acc_key(_fork_scan(paths6, False, 3))
                fork_note = "fork 分片 3 份与串行一致"
            except Exception as exc:                        # noqa: BLE001
                same3, fork_note = False, "fork 分片失败：%r" % (exc,)
        ck("S6", "一致性", "串行／线程池／进程分片的命中集合与汇总计数完全一致（%d 个文件；%s）"
           % (len(paths6), fork_note), same3, "期望三路一致")

        # S7：**不支持 fork 也必须能跑**（Windows／受限环境）：关掉 fork 开关后走线程池，结果不变
        _keep_cf = globals()["can_fork"]
        try:
            globals()["can_fork"] = lambda: False
            nh_fb, s_fb = scan_dir(pos, procs=6)
            fallback_ok = (key(nh_fb) == key(h1)) and s_fb["procs"] == 0
        finally:
            globals()["can_fork"] = _keep_cf
        ck("S7", "一致性", "不支持 fork 时自动退回线程池（命中与串行一致、进程层=0）", fallback_ok,
           "期望一致且 procs=0")

        overlap = sorted(BINARY_EXT & (DATA_EXT | SRC_EXT))
        ck("S3", "一致性", "剪枝扩展名与文本扩展名不重叠（交集 %s）" % (overlap or "空"), not overlap,
           "期望空集：剪枝不会误剪文本")

        # 逐规则等价性：门没开的规则，**在任何文件上都不得命中**（把"预筛不降灵敏度"做成断言）
        gaps, n_corpus, n_skipped_all = [], 0, 0
        for dp, _dn, fn in os.walk(corpus):
            for f in fn:
                fp = os.path.join(dp, f)
                ext = os.path.splitext(f)[1].lower()
                raw = open(fp, "rb").read()
                n_corpus += 1
                gates = _gates(raw)
                if not gates:
                    n_skipped_all += 1
                text = raw.decode("utf-8", errors="ignore")
                for rule, _sev, rx in CONTENT_RULES:
                    if rule not in gates and rx.search(text):
                        gaps.append("%s 规则=%s（门未开却可命中）" % (fp, rule))
                if "mention" not in gates and MENTION_RE.search(text):
                    gaps.append("%s 规则=mention（门未开却可命中）" % fp)
        ck("S4", "一致性", "字节门逐规则不漏报（语料 %d 个文件：%d 个门全空、其余按规则开；"
           "门未开却可命中的 %d 处）" % (n_corpus, n_skipped_all, len(gaps)), not gaps,
           "命中：%s" % (gaps[:6] or "无"))

        want_keys = ("totalFiles", "prunedDirCount", "scannedFull", "scannedWindow",
                     "truncatedFiles", "nameOnlyFiles", "bytesRead")
        missing = [k for k in want_keys if k not in psurf]
        ck("S5", "一致性", "扫描面自报字段齐备（缺 %s）" % (missing or "无"), not missing,
           "期望 %s 全在" % "、".join(want_keys))

        ok_exit = _exit_code_contract(pos, neg)
        ck("X1", "退出码", "退出码约定：命中→1、干净→0", ok_exit, "见上一行")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for c in checks:
        line = "  %s [%s][%s] %s" % ("通过" if c["ok"] else "不通过", c["id"], c["kind"], c["desc"])
        if c["detail"] and not c["ok"]:
            line += "  —— " + c["detail"]
        print(line)
    n_ok = sum(1 for c in checks if c["ok"])
    kinds = {}
    for c in checks:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    print("self-test 用例 %d 条（通过 %d ／ 不通过 %d）：%s"
          % (len(checks), n_ok, len(checks) - n_ok,
             "、".join("%s %d 条" % (k, v) for k, v in sorted(kinds.items()))))
    ok = n_ok == len(checks)
    if not ok:
        print("不通过项：%s" % "；".join(c["id"] for c in checks if not c["ok"]))
    print("self-test %s" % ("通过 ✅" if ok else "不通过 ❌"))
    return 0 if ok else 3


def _exit_code_contract(pos, neg):
    """核对退出码约定：命中 → 1；干净 → 0。"""
    class A:
        json = False
        allow_repo_root = False
    a = A()
    e_pos = _run_exit(pos, a)
    e_neg = _run_exit(neg, a)
    print("退出码约定：命中=%d（期望 1）、干净=%d（期望 0）→ %s"
          % (e_pos, e_neg, "✅" if (e_pos == 1 and e_neg == 0) else "❌"))
    return e_pos == 1 and e_neg == 0


def _run_exit(target, args):
    hits, _ = scan_dir(target)
    errs = [h for h in hits if h["severity"] == "ERROR"]
    return 1 if (errs and not args.allow_repo_root) else 0


def _epilog():
    return (
        "扫描边界（不扫什么，先说清）："
        "① 非文本扩展名不扫内容、只做文件名判据——内容扫描白名单＝"
        + "、".join(sorted(DATA_EXT | SRC_EXT)) + "，另加无扩展名文件；"
          "图片/压缩包(.zip/.gz/.whl)/可执行(.so/.node)/字库/办公文档(.xlsx/.pdf)/日志(.log/.out/.err)"
          " 等一律只查文件名；"
        "② 单文件 >%.0f MiB 只扫头 %.0f MiB ＋ 尾 %.0f KiB（中段不扫），命中标 truncated=true 并标注"
          "「已按上限扫描」；≤%.0f MiB 全量扫（与旧版同值，灵敏度不变），--full-scan 可强制全量；"
        "③ 目录剪枝：%s，以及 _archive* 前缀（--scan-archives 放开）；"
        "④ 值未加引号的 password: hunter2 不判 ERROR（规则要求引号）；"
        "⑤ 剪枝与截断全部计入「扫描面自报」，不发生静默跳过。"
        " 并发与可移植：默认「进程 min(%d, CPU 核数) ＋ 不支持 fork 时自动退回线程池（默认 %d 线程）」——"
        "去掉正则与整文件查找后，剩下的瓶颈是 CPU（lower/find/name 正则）而不是 I/O，线程会被 GIL 串起来，"
        "所以用少量进程真并行；**Windows 等没有 fork 的平台只会变慢，不会报错、不会改变结果**；"
        "文件数少于 %d 时也不起进程；`--procs 1` 完全等价于纯线程池回退。"
        "命中集合与汇总计数与并发度无关（自检 S6/S7 逐条断言）。"
        % (FULL_SCAN_MAX / 1024 / 1024, HEAD_WINDOW / 1024 / 1024, TAIL_WINDOW / 1024,
           FULL_SCAN_MAX / 1024 / 1024, "、".join(sorted(SKIP_DIRS)),
           DEFAULT_PROCS, DEFAULT_JOBS, PROC_MIN_FILES))


def main(argv=None):
    global FULL_SCAN_MAX, MAX_BYTES      # `--full-scan` 会把上限抬到无穷（改慢，仅排查用）
    ap = argparse.ArgumentParser(
        description="分发物凭据断言（TICKET-144；TICKET-151 C2 提速改版）", epilog=_epilog())
    ap.add_argument("targets", nargs="*", help="要检查的目录（打包目录）")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--allow-repo-root", action="store_true",
                    help="扫描工作区根时只报警不失败（用户要求保留现有 .daniel_cred.json/.daniel_session.json）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict-jwt", action="store_true",
                    help="把任意 JWT 形串都当 ERROR（默认：无本项目凭据上下文的 JWT 只告警）")
    ap.add_argument("--surface", action="store_true",
                    help="只打印扫描面自报（扫了多少／剪掉多少／截断多少），不判命中")
    ap.add_argument("--jobs", type=int, default=None,
                    help="并发线程数（默认 %d，可用环境变量 %s 覆盖；输出与并发数无关）"
                         % (DEFAULT_JOBS, JOBS_ENV))
    ap.add_argument("--procs", type=int, default=None,
                    help="并发进程数（默认 %d，可用环境变量 %s 覆盖；1＝不起进程、退回线程池。"
                         "剩下的活是 CPU（lower/find/正则），线程被 GIL 串起来，所以用少量进程真并行；"
                         "文件数少于 %d 时自动不起进程）"
                         % (DEFAULT_PROCS, PROCS_ENV, PROC_MIN_FILES))
    ap.add_argument("--scan-archives", action="store_true",
                    help="连 _archive* 归档目录一起扫（默认剪枝；剪掉的目录会逐条打印在扫描面自报里）")
    ap.add_argument("--full-scan", action="store_true",
                    help=">%.0f MiB 的文件也全量读（默认只扫头尾；会变慢，仅排查可疑大文件时用）"
                         % (FULL_SCAN_MAX / 1024 / 1024))
    a = ap.parse_args(argv)

    if a.self_test:
        return self_test()
    if not a.targets:
        ap.print_help()
        print("\n需要至少一个目录参数（分发物/打包目录）。", file=sys.stderr)
        return 2

    if a.full_scan:
        FULL_SCAN_MAX = UNLIMITED           # 整数哨兵：JSON 里不会出现 Infinity
        MAX_BYTES = FULL_SCAN_MAX

    total_e, all_hits, nfiles = 0, [], 0
    surfaces = []
    for t in a.targets:
        if not os.path.exists(t):
            print("目录不存在：%s" % t, file=sys.stderr)
            return 2
        hits, surface = scan_dir(t, strict_jwt=a.strict_jwt, jobs=a.jobs,
                                 scan_archives=a.scan_archives, procs=a.procs)
        all_hits += hits
        surfaces.append(surface)
        nfiles += surface["totalFiles"]
        total_e += len([h for h in hits if h["severity"] == "ERROR"])
    surface = merge_surfaces(surfaces)
    if a.surface:
        _print_surface(surface)
        return 0
    report(a.targets, all_hits, a, surface)

    is_repo_root = any(os.path.abspath(t) == os.path.abspath(ROOT) for t in a.targets)
    if total_e and a.allow_repo_root:
        out = sys.stderr if a.json else sys.stdout          # --json 时保持 stdout 是纯 JSON
        print("\n⚠️  扫描 %s 个文件，命中 %d 条 ERROR —— 因 --allow-repo-root（用户要求保留现有凭据文件）"
              "**仅报警，不作失败**。" % (nfiles, total_e), file=out)
        print("   → 打包/分发前必须排除：仓库根 .daniel_cred.json、.kol-tools/.daniel_session.json、"
              "以及任何 DANIEL_HOME/secrets/ 内容。", file=out)
        if not is_repo_root:
            print("   注意：--allow-repo-root 只应用于工作区根扫描。", file=out)
        return 0
    if total_e:
        print("\n❌ 发现 %d 条凭据痕迹 —— 该目录**不得**作为分发物（退出码 1）。" % total_e)
        return 1
    print("✅ %s：扫描 %d 个文件，0 条凭据痕迹（可安全分发）。" % (", ".join(a.targets), nfiles))
    return 0


if __name__ == "__main__":
    sys.exit(main())
