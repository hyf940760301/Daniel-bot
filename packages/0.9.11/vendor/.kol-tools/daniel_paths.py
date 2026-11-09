#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daniel Copilot 数据落点统一解析层（TICKET-144 · P0-1）。

**只回答一个问题**：某类文件应该落哪儿。不做任何业务判据，不 import 业务模块。

落点规则
--------
`DANIEL_HOME` 环境变量优先；未设置时按顺序探测：
  ① `~/Library/Application Support/DanielCopilot`（macOS 默认）
  ② `~/.daniel-bot`（沙箱/无写权限时的**降级落点**，`--json` 里标 `home_reason=fallback-user-home`）

🔴 TICKET-223 · 降级落点**迁出包外** ＋ 「不得写进包根」守卫
------------------------------------------------------------
起因（用户 2026-10-21 拍板）：旧降级落点是 `<工作区根>/.daniel-home`，即**包内**。客户机上只要
系统数据目录不可写（只读环境／沙箱／CI／权限受限），程序就会**静默**把 `session/session.json`
（约一年有效的登录会话）、`logs/write-audit.jsonl`（写审计）、`cache/`、`output/`、`trace/`
写进**包内** —— 一旦把包外发，等于把凭据与业务留痕一起带出去
（本机实测：沙箱里跑几次不带 `DANIEL_HOME` 的命令，`vendor/.daniel-home` 会自动重建）。

现在的三条口径（缺一条就是没做到）：
  ① **降级落点改为 `~/.daniel-bot`**（用户主目录，包外）；
  ② **不自动搬运凭据**：旧落点存在且非空时只**打印迁移提示 ＋ 可复制的迁移命令**，
     搬不搬、何时搬由人决定（静默搬密钥比留在原地更危险）；
  ③ **绝不写进包根**：解析结果若落在**交付副本根**（`daniel-bot/`、`*/vendor/` 这类会被打包外发
     的目录）之内，或落在**任何副本根（含开发工作区）顶层的旧 `.daniel-home`** 之内
     ⇒ 一律按"不可用"处理并**继续回退**；全都没有可写落点时**抛 `NoWritableHome` 明确报错**，
     绝不静默降级（判据见 `refuse_reason()`，落点判定见 `home()`）。

**候选是否可用＝真实写探测**（TICKET-149 修正）：在目标目录建临时文件 → 写入 → 删除，
失败即判不可用并回退到下一个候选。不能用 `os.makedirs(exist_ok=True)` 代替 —— 目录
**已存在**时它直接返回成功、不产生任何写操作，于是"存在但不可写"会被误判为可用
（本沙箱实测：`~/Library/Application Support/DanielCopilot` 存在、写入被拒，却仍被选为落点）。

落点理由（`home_reason`，`--json` 里同名）
  `env:DANIEL_HOME`（用户显式指定）｜ `default-macos`（系统默认）｜
  `fallback-user-home`（首选不可用，已退到 `~/.daniel-bot` —— TICKET-223 新增枚举值）

被拒候选与拒因（`home_refusals()`；`--json` 里同名数组，逐条报"哪个候选、为什么被拒"）
  `unwritable-app-support`（首选**存在但不可写**，已回退）｜ `uncreatable-app-support`（首选不存在且建不出来）
  ｜ `unwritable-candidate` ｜ `uncreatable-candidate`
  ｜ `inside-package-root`（落在交付副本根内 ⇒ 拒写，TICKET-223）｜
  `legacy-fallback-path`（落在旧 `.daniel-home` 内 ⇒ 拒写，TICKET-223）

子目录：
  `session/`（会话 JWT） · `cache/`（品牌索引等） · `output/`（交付物） · `logs/` · `secrets/`（**仅当显式降级到明文凭据时**才用）

旧位置（**只读兼容**，永不新写；**TICKET-194 起必须落在 `DANIEL_HOME` 之内才允许读**）
  `.kol-tools/.daniel_session.json` · `.kol-tools/_cache/brand-index.json` · `<工作区根>/.daniel_cred.json`

读取顺序 = **新位置优先 → 旧位置兜底**（见 `read_candidates()`）。
（票面写的是"旧位置存在时优先读旧位置"；若字面实现，新位置刷新出的缓存会被旧文件永久遮蔽，
 故按"新优先 + 旧兜底 + 首次读到旧值时迁移到新位置"实现，差异已记入 `_impl` 说明文档。）

🔴 TICKET-194 · C：**旧位置不再越界**（CLS-84 同类）
----------------------------------------------------------------------
起因（用户 2026-10-16 实测反例）：`DANIEL_HOME=/tmp/... daniel brands list` 在**干净临时 HOME**
下**照样拿到 200 条真实品牌**，`daniel account whoami` 直接报出真实账号 —— 根因就是上面那三个
旧位置**写死在仓库根、不随 `DANIEL_HOME` 走**。于是：
  ① **落点隔离形同虚设**（`DANIEL_HOME` 之外还有一份凭据／会话／缓存被读到）；
  ② **未登录可调用模块**（违反"授权是起点"）；
  ③ **打包泄漏风险**（把仓库交出去等于把管理员明文凭据交出去）。

现在的判据（唯一、可复算，见 `legacy_allowed()`）：
  · **任何旧位置只有在 `DANIEL_HOME` 之内才允许读**；在之外 ⇒ **一律拒读**（`legacy_path()` 返回
    `None`），并在 `--print-paths`／`--json` 里**如实报出"被拒 + 为什么"**（不许静默）；
  · **明文凭据**的旧位置再叠一道**显式开关**：`DANIEL_ALLOW_LEGACY_CRED=1`（**默认关**）。
    两层都满足才读，读到就打警告 —— 这是票面 C 要求的形态。
  · 新增的会话／缓存落点不受影响：**本来就是新位置优先**，只是"兜底"现在被限定了范围。


命令行
------
  python3 daniel_paths.py --print-paths     # 人类可读的解析结果（含回退说明）
  python3 daniel_paths.py --json            # 机器可读（含 home 选择理由）
  python3 daniel_paths.py --make-dirs       # 建目录（幂等；只读环境不报错，返回非零）
"""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # 工作区根
if HERE not in sys.path:          # 兄弟模块 daniel_io：脚本直跑与被别的仪器当库载入两条路都要能 import
    sys.path.insert(0, HERE)
import daniel_io  # noqa: E402  （TICKET-168：`--json` 出口的唯一收口层）

DEFAULT_HOME_MACOS = os.path.join(
    os.path.expanduser("~"), "Library", "Application Support", "DanielCopilot")
#: 🔴 TICKET-223：降级落点从 `<工作区根>/.daniel-home`（**包内**）改为 `~/.daniel-bot`（**包外**）。
#: 为什么必须出包：旧落点会把会话 JWT（约一年有效）与写审计一起写进分发目录，
#: 把包交给客户就等于把凭据与业务留痕一起交出去。用户 2026-10-21 拍板用 `~/.daniel-bot`。
FALLBACK_USER_HOME = os.path.join(os.path.expanduser("~"), ".daniel-bot")
#: 兼容别名：`FALLBACK_HOME` 仍表示"降级落点"，但**它已经不在包内了**（引用这个名字的旧代码
#: 语义随之改变 —— 这正是本票要的效果；不要在别处再拼 `ROOT/.daniel-home`）。
FALLBACK_HOME = FALLBACK_USER_HOME
#: 旧降级落点（本副本根顶层 `.daniel-home`）：**已退休**。只用于两件事 ——
#: ① 迁移提示（`migration_notice()`）② 写守卫拒写（`refuse_reason()`）。**绝不再写入。**
LEGACY_FALLBACK_HOME = os.path.join(ROOT, ".daniel-home")

#: 数据落点环境变量名（单一真源；别处一律用常量，避免拼错后静默不生效）
DANIEL_HOME_ENV = "DANIEL_HOME"

# 候选链（顺序即优先级）：DANIEL_HOME 环境变量 → 系统应用数据目录 → 用户主目录降级落点
CANDIDATES = (("default-macos", DEFAULT_HOME_MACOS),
              ("fallback-user-home", FALLBACK_USER_HOME))

SUBDIRS = ("session", "cache", "output", "logs", "secrets")

# kind -> 文件名（相对 home）；目录类 kind 见 SUBDIRS
FILES = {
    "session_file": ("session", "session.json"),
    "brand_index": ("cache", "brand-index.json"),
    "credentials_fallback": ("secrets", "credentials.json"),   # 仅 DANIEL_ALLOW_PLAINTEXT=1
}

# kind -> 旧位置（只读兼容；**能否真读见 legacy_allowed()** —— TICKET-194 起必须落在
# DANIEL_HOME 之内，明文凭据还要额外的显式开关。这里保留"声明面"以便如实报出被拒的落点。）
LEGACY = {
    "session_file": os.path.join(HERE, ".daniel_session.json"),
    "brand_index": os.path.join(HERE, "_cache", "brand-index.json"),
    "credentials_fallback": os.path.join(ROOT, ".daniel_cred.json"),
}

#: 明文凭据旧位置的**显式开关**（默认关）。为什么默认关：旧明文文件是"仓库根写死路径"里
#: 最危险的一份（邮箱＋密码原文）；默认关掉之后，**把仓库交出去不再等于把管理员凭据交出去**。
ALLOW_LEGACY_CRED_ENV = "DANIEL_ALLOW_LEGACY_CRED"

#: 需要**额外显式开关**才允许读的 kind（目前只有明文凭据）
LEGACY_NEEDS_SWITCH = ("credentials_fallback",)

#: 旧位置被拒的原因码（进 `--json` 的 `legacy_gate`，让人一眼看懂"为什么没读到"）
LEGACY_REFUSE_OUTSIDE = "outside-DANIEL_HOME"       # 旧位置不在 DANIEL_HOME 之内
LEGACY_REFUSE_NO_SWITCH = "need-DANIEL_ALLOW_LEGACY_CRED"   # 明文凭据没打开显式开关

# 兼容别名：票面/文档里用的名字 → kind
_ALIASES = {
    "session": "session_file",
    "session_json": "session_file",
    "brand-index": "brand_index",
    "brand_index_path": "brand_index",
    "cred": "credentials_fallback",
    "cred_file": "credentials_fallback",
    "credentials": "credentials_fallback",
    "legacy_cred_file": "legacy_credentials_fallback",
    "legacy_session_file": "legacy_session_file",
    "legacy_brand_index": "legacy_brand_index",
}

# 落点理由里的"已降级"标记；`--print-paths` 见到它就把"为什么降级"（`home_refusals()`）一并打印
FALLBACK_REASONS = ("fallback-user-home",)

#: 写守卫的拒因码（TICKET-223）：解析结果落在这些面上 ⇒ 按不可用处理、继续回退
REFUSE_INSIDE_PACKAGE = "inside-package-root"
REFUSE_LEGACY_FALLBACK = "legacy-fallback-path"
#: 候选**自身不可用**的拒因码（TICKET-149 起一直如此，现在与"包根拒写"并列报出）
REFUSE_UNWRITABLE_SUPPORT = "unwritable-app-support"
REFUSE_UNCREATABLE_SUPPORT = "uncreatable-app-support"
REFUSE_UNWRITABLE_CAND = "unwritable-candidate"
REFUSE_UNCREATABLE_CAND = "uncreatable-candidate"

#: 旧降级落点迁移提示的开关（`0` 只关打印，**不改任何落点判据**）
MIGRATION_NOTICE_ENV = "DANIEL_MIGRATION_NOTICE"

_PROBE_PREFIX = ".daniel-write-probe-"

_home_cache = None
_home_reason = None
_home_refusals = []          # [{"候选":…, "路径":…, "拒因":…}] —— `--json` 如实报出
_migration_notice_shown = False

# ═════════ TICKET-223：包根识别与写守卫（"绝不写进包根"的唯一判据） ═════════
# **什么是"包根"**：会被**打包外发**的目录。判据用结构识别而不是写死绝对路径（客户机路径不同）：
#   · 副本根＝含 `.kol-tools/daniel_paths.py` 的目录（本仓的每一个副本都是这个形态）；
#   · 其中**没有开发工作区标记**（`AGENTS.md`／`tickets/`／`docs/roles/`）的，就是"要交付出去的
#     副本根" ⇒ 它整棵树都不许当数据落点（本仓实测命中：`daniel-bot/`、
#     `daniel-dsh-plugin/vendor/`、`daniel-codex-package/vendor/`）；
#   · 开发工作区根自身不算包根（那里要能跑仪器、要能往 `tmp/` 写夹具），但它**顶层的
#     `.daniel-home`** 仍按"旧降级落点"拒写（见 `LEGACY_FALLBACK_HOME`）。
_COPY_ROOT_MARKER = os.path.join(".kol-tools", "daniel_paths.py")
_DEV_WORKSPACE_MARKERS = ("AGENTS.md", "tickets", os.path.join("docs", "roles"))
#: 已知的交付副本相对位置（结构识别之外的"兜底点名"，防止标记文件被裁掉后漏判）
_DELIVERY_COPY_RELS = ("daniel-bot",
                       os.path.join("daniel-dsh-plugin", "vendor"),
                       os.path.join("daniel-codex-package", "vendor"),
                       "vendor")

_package_roots_cache = None


def _norm(path):
    """归一化到绝对路径（`~` 展开；**不解析软链** —— 与 rest of 落点解析保持同一口径）。"""
    return os.path.abspath(os.path.expanduser(str(path)))


def _same_or_under(path, root):
    """`path` 是否等于 `root` 或落在其下（两侧都已归一化）。"""
    p, r = _norm(path), _norm(root)
    return p == r or p.startswith(r + os.sep)


def _is_delivery_copy_root(d):
    """`d` 是不是"要交付出去的副本根"（副本根形态 ＋ 没有开发工作区标记）。"""
    if not os.path.isfile(os.path.join(d, _COPY_ROOT_MARKER)):
        return False
    return not any(os.path.exists(os.path.join(d, m)) for m in _DEV_WORKSPACE_MARKERS)


def package_roots():
    """本次运行可见的**交付副本根**清单（本副本根 ＋ 已知交付副本）。只读，不创建任何东西。"""
    global _package_roots_cache
    if _package_roots_cache is not None:
        return list(_package_roots_cache)
    out = []

    def _add(d):
        d = _norm(d)
        if d not in out and _is_delivery_copy_root(d):
            out.append(d)

    _add(ROOT)
    for rel in _DELIVERY_COPY_RELS:
        _add(os.path.join(ROOT, rel))
    _package_roots_cache = tuple(out)
    return list(out)


def refuse_reason(path):
    """**该落点禁止写入吗？** → 拒因码（`None` ＝允许）。这是"绝不写进包根"的唯一判据。

    两条禁写面（TICKET-223）：
      ① `inside-package-root`：落在**交付副本根**之内。写进去就等于把会话／审计／缓存随包发出去
         —— 打包排除规则（`daniel_cli/pack/spec.py` X23／`NAMED_EXCLUSIONS`）**只排得掉目录名**，
         排不掉"客户机上运行期新建"，所以必须在**落点解析这一步**就拒。
      ② `legacy-fallback-path`：落在**任何副本根（含开发工作区）顶层的 `.daniel-home`** 之内
         —— 那是本票之前的旧降级落点，已退休；允许再写回去等于本票白做。
    注意：本函数**只看路径**，不建目录、不写探测文件（纯判据，可在任何阶段调用）。
    """
    p = _norm(path)
    for r in package_roots():
        if _same_or_under(p, r):
            return REFUSE_INSIDE_PACKAGE
    for base in [ROOT] + package_roots():
        if _same_or_under(p, os.path.join(_norm(base), ".daniel-home")):
            return REFUSE_LEGACY_FALLBACK
    return None


#: 拒因码 → 人话（打印用；不改判据）
REFUSE_TEXT = {
    REFUSE_INSIDE_PACKAGE: "落在**交付副本根**内（会被打包外发，绝不写进去）",
    REFUSE_LEGACY_FALLBACK: "落在**旧降级落点** `.daniel-home` 内（已退休，绝不写回去）",
    REFUSE_UNWRITABLE_SUPPORT: "系统的应用支持目录存在、但**不可写**（真实写探测失败）",
    REFUSE_UNCREATABLE_SUPPORT: "系统的应用支持目录不存在、且创建被拒",
    REFUSE_UNWRITABLE_CAND: "候选落点存在、但不可写",
    REFUSE_UNCREATABLE_CAND: "候选落点不存在、且创建被拒",
}


class NoWritableHome(RuntimeError):
    """**没有任何可写的数据落点** —— 必须明确报错，不许静默降级（TICKET-223）。

    为什么抛异常而不是"退到某个包内目录凑合用"：静默降级正是本票要消灭的行为。宁可让命令
    失败并把"该改哪个环境变量／该放开哪个目录的权限"讲清楚，也不要把凭据写进分发目录。
    """

    def __init__(self, refusals, candidates):
        self.refusals = list(refusals)
        self.candidates = list(candidates)
        RuntimeError.__init__(self, self._message())

    def _message(self):
        lines = ["没有任何可写的数据落点（TICKET-223：绝不把数据写进包根，也不静默降级）",
                 "  已尝试的候选："]
        for label, path in self.candidates:
            lines.append("    %-22s %s" % (label, path))
        if self.refusals:
            lines.append("  被拒原因：")
            for r in self.refusals:
                lines.append("    %-22s %s ｜ %s" % (r.get("候选", ""), r.get("路径", ""),
                                                    REFUSE_TEXT.get(r.get("拒因"),
                                                                    r.get("拒因"))))
        lines.append("  怎么办：① 用 `%s=<你自己指定的可写目录>` 显式指定落点；"
                     "② 或让上表里某个候选目录可写（例如 `mkdir -p %s` 并确认权限）。"
                     % (DANIEL_HOME_ENV, FALLBACK_USER_HOME))
        return "\n".join(lines)


def _warn(msg):
    """把提示打到 **stderr**（`--json` 时 stdout 必须是且只是一个 JSON 文档，提示不许混进去）。

    用 `print(..., file=sys.stderr)` 而不是 `sys.stderr.write(...)`：后者会被
    `check_write_landings.py` 数成一个"写点"（DYNAMIC），凭空给落点盘点加噪声。
    """
    try:
        print(str(msg).rstrip("\n"), file=sys.stderr)
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


def _shell_quote(p):
    try:
        import shlex
        return shlex.quote(str(p))
    except Exception:                                             # noqa: BLE001
        return "'%s'" % str(p).replace("'", "'\\''")


def legacy_fallback_dirs():
    """**旧降级落点**目录清单（存在才算）：本副本根 ＋ 已知交付副本根顶层的 `.daniel-home`。"""
    out = []
    for base in [ROOT] + package_roots():
        p = os.path.join(_norm(base), ".daniel-home")
        if p not in out and os.path.isdir(p):
            out.append(p)
    return out


def _dir_nonempty(p):
    try:
        return bool(os.listdir(p))
    except OSError:
        return False


def migration_notice():
    """旧落点 → 新落点 的**迁移提示**（只打印，**绝不自动搬运凭据**）。

    为什么"只提示、不自动搬"（用户口径 ②）：自动把 `session.json`（一年有效的登录会话）从
    包内拷到别处，是一次**静默的凭据搬运** —— 用户既不知道发生了，也无从判断搬的是哪份、
    是否该搬。所以这里只做三件事：说清旧/新落点、给**可复制**的命令、说明"删不删由你"。
    没有旧落点（或旧落点为空）时返回 `None`（不打扰用户）。
    """
    olds = [d for d in legacy_fallback_dirs() if _dir_nonempty(d)]
    if not olds:
        return None
    new = FALLBACK_USER_HOME
    lines = ["⚠️  数据落点已迁出包外（TICKET-223）· 旧落点迁移提示："
             "旧的降级落点里还有数据，本程序**不会自动搬运凭据或留痕**，要不要搬由你决定。"]
    for old in olds:
        lines.append("    旧落点：%s" % old)
    lines.append("    新落点：%s" % new)
    lines.append("    要沿用旧的登录会话与留痕，请自己执行（**复制**，不动原目录）：")
    for old in olds:
        lines.append("      mkdir -p %s && cp -a %s/. %s/"
                     % (_shell_quote(new), _shell_quote(old), _shell_quote(new)))
    lines.append("    只搬登录会话的话：")
    lines.append("      mkdir -p %s/session && cp -a %s/session/session.json %s/session/"
                 % (_shell_quote(new), _shell_quote(olds[0]), _shell_quote(new)))
    lines.append("    确认新落点可用后，旧目录请自己手工删除（本程序不会替你删）。")
    return "\n".join(lines)


def _note_migration_once():
    """进程内**只打印一次**迁移提示（`%s=0` 可关掉打印，落点判据不受影响）。"""
    global _migration_notice_shown
    if _migration_notice_shown:
        return
    _migration_notice_shown = True
    if os.environ.get(MIGRATION_NOTICE_ENV) == "0":
        return
    txt = migration_notice()
    if txt:
        _warn(txt)


def _usable_dir(path):
    """**不产生副作用**的可用性判断（`create=False` 用）：现有且可写，或父目录存在可写（可创建）。

    注意：只看文件系统属性（`os.access`）。默认路径（`create=True`）一律走 `_probe_write()`
    真写探测 —— 属性判断在沙箱/ACL 场景下会误判（`os.access` 与内核实际裁决并不总是一致）。
    """
    if os.path.isdir(path):
        return os.access(path, os.W_OK)
    parent = os.path.dirname(path)
    return os.path.isdir(parent) and os.access(parent, os.W_OK)


def _probe_write(path):
    """**真实写探测**：建目录（幂等）→ 建临时文件 → 写入 → 删除。任一步失败即判不可用。

    为什么必须真写（TICKET-149 真缺陷）：
      旧实现 `_probe_create()` 只做 `os.makedirs(path, exist_ok=True)`；**目录已存在时它不写任何
      东西就直接成功**，于是"存在但不可写"的目录被判为可用 —— 本沙箱里
      `~/Library/Application Support/DanielCopilot`（存在、`os.access(W_OK)=False`、写入抛
      PermissionError）被选作 DANIEL_HOME，后续写入要失败在更远的地方，且报错信息误导。
    """
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return False
    probe = os.path.join(path, _PROBE_PREFIX + str(os.getpid()))
    try:
        fh = io.open(probe, "w", encoding="utf-8")
        try:
            fh.write("daniel-path-probe")
            fh.flush()
        finally:
            fh.close()
    except OSError:
        return False
    try:
        os.remove(probe)
    except OSError:
        pass          # 探测文件删不掉不影响"可写"结论，但不留残留更好；忽略即可
    return True


def _unusable_code(path):
    """候选**自身**不可用的原因代码（"存在但不可写"／"建不出来"），用于如实报拒因。"""
    exists = os.path.isdir(path)
    if _norm(path) == _norm(DEFAULT_HOME_MACOS):
        return REFUSE_UNWRITABLE_SUPPORT if exists else REFUSE_UNCREATABLE_SUPPORT
    return REFUSE_UNWRITABLE_CAND if exists else REFUSE_UNCREATABLE_CAND


def _record_refusal(path, code, label):
    """记一条"候选被拒"（供 `home_refusals()`／`--json`／报错文案共用同一份事实）。"""
    item = {"候选": label, "路径": _norm(path), "拒因": code,
            "拒绝理由": REFUSE_TEXT.get(code, code)}
    if item not in _home_refusals:
        _home_refusals.append(item)
    return item


def home(create=True):
    """返回本机生效的 DANIEL_HOME。`create=False` 时不做落盘写探测（只看文件系统属性）。

    🔴 TICKET-223 的判定顺序（每一步都不许省）：
      ① `DANIEL_HOME` 显式给了 → **先过写守卫**（`refuse_reason()`）：落在包根／旧 `.daniel-home`
         内 ⇒ 按不可用处理、打警告、**继续回退**（不写进去）；
      ② 候选链 `default-macos` → `fallback-user-home`（`~/.daniel-bot`），逐个过写守卫 ＋ 真写探测；
      ③ **全都不可用 ⇒ 抛 `NoWritableHome` 明确报错**（不再退到任何包内目录）。
    """
    global _home_cache, _home_reason
    env = os.environ.get(DANIEL_HOME_ENV)
    if env:
        p = _norm(env)
        why = refuse_reason(p)
        if why is None:
            _note_migration_once()
            return p
        _record_refusal(p, why, "DANIEL_HOME")
        _warn("⚠️  DANIEL_HOME=%s %s ⇒ 按不可用处理，继续回退（TICKET-223：不写进包根）"
              % (p, REFUSE_TEXT.get(why, why)))
    if _home_cache:
        _note_migration_once()
        return _home_cache
    for label, cand in CANDIDATES:
        why = refuse_reason(cand)
        if why:                                   # 落在包根/旧落点 ⇒ 连探测都不做
            _record_refusal(cand, why, label)
            continue
        ok = _probe_write(cand) if create else _usable_dir(cand)
        if ok:
            _home_cache, _home_reason = cand, label
            _note_migration_once()
            return cand
        _record_refusal(cand, _unusable_code(cand), label)
    _note_migration_once()
    raise NoWritableHome(_home_refusals, CANDIDATES)


def home_reason():
    """落点**为什么在这里**：`env:DANIEL_HOME` ｜ `default-macos` ｜ `fallback-user-home`
    ｜ `no-writable-home`（一个可写落点都没有 —— 见下）。

    TICKET-223 起 `home_reason` 只回答"选中了哪一档"，**"为什么没选前面的档"** 由
    `home_refusals()` 逐条回答（两层分开，才既能让机器判据稳定、又能让人看懂）。

    为什么这里**不抛** `NoWritableHome`（而 `home()` 抛）：本函数是**纯汇报**面 —— 典型调用方是
    `daniel account paths` 的"根是怎么选出来的"一栏，它要回答的是**假设不注入 `DANIEL_HOME`** 时
    根会落在哪（`accounts.base_home_reason()` 会临时摘掉该变量再问）。这条路上"一个可写落点都没有"
    是**一个事实**，应该被如实写进报告（`no-writable-home`），而不是让整条只读命令失败；
    "必须明确报错"的职责在 `home()`：任何真要用落点的地方都会立刻拿到 `NoWritableHome`。
    """
    env = os.environ.get(DANIEL_HOME_ENV)
    if env and refuse_reason(env) is None:
        return "env:DANIEL_HOME"
    try:
        home(create=True)
    except NoWritableHome:
        return "no-writable-home"
    return _home_reason or "unknown"


def home_refusals():
    """本次运行里**被拒的候选**（逐条：哪个候选、哪个路径、什么拒因）—— 如实报出，不静默。"""
    return [dict(x) for x in _home_refusals]


def reset_cache():
    """清掉进程内缓存（`accounts.py` 注入/摘除 `DANIEL_HOME` 前后必须现算）。"""
    global _home_cache, _home_reason, _migration_notice_shown, _package_roots_cache
    _home_cache, _home_reason = None, None
    del _home_refusals[:]
    _migration_notice_shown = False
    _package_roots_cache = None


def legacy_allowed(kind):
    """旧位置**能不能读**？→ `(允许?, 原因码, 人话)`（TICKET-194 · C 的**唯一判据**）。

    两条都满足才允许：
      ① **旧位置必须落在生效的 `DANIEL_HOME` 之内**（否则它读的是 `DANIEL_HOME` 之外的一份
         凭据／会话／缓存 —— 那正是"干净临时 HOME 照样拿到真实数据"的根因）；
      ② 明文凭据还必须有**显式开关** `DANIEL_ALLOW_LEGACY_CRED=1`（**默认关**）。
    """
    k = _ALIASES.get(str(kind).strip(), str(kind).strip())
    p = LEGACY.get(k)
    if not p:
        return False, "no-legacy", "该落点没有旧位置"
    if not _inside_home(p):
        return (False, LEGACY_REFUSE_OUTSIDE,
                "旧位置 %s **不在** 当前数据落点 %s 之内 ⇒ 拒读"
                "（TICKET-194：旧位置只允许落在 DANIEL_HOME 之内）" % (p, home()))
    if k in LEGACY_NEEDS_SWITCH and os.environ.get(ALLOW_LEGACY_CRED_ENV) != "1":
        return (False, LEGACY_REFUSE_NO_SWITCH,
                "旧明文凭据位置 %s 在数据落点之内，但**没有打开显式开关** %s=1 ⇒ 拒读"
                "（默认关：旧明文文件里的邮箱＋密码原文不再被默认读取）"
                % (p, ALLOW_LEGACY_CRED_ENV))
    return True, "allowed", "允许读（在数据落点之内%s）" % (
        "，且已显式打开 %s=1" % ALLOW_LEGACY_CRED_ENV if k in LEGACY_NEEDS_SWITCH else "")


def _inside_home(path):
    """路径是否落在生效的 `DANIEL_HOME` 之内（含相等）。"""
    h = os.path.abspath(home())
    p = os.path.abspath(str(path))
    return p == h or p.startswith(h + os.sep)


def legacy_path(kind):
    """**可读的**旧位置路径；没有旧位置映射、或被判拒读时返回 None。

    被拒时不再返回路径 —— 这是本票的关键改动：调用方（会话／缓存／凭据读取）拿到 None
    就**不会去读**那份越界文件。被拒的**声明路径与原因**仍可从 `legacy_declared()`／
    `legacy_report()` 取到（如实报出，不静默）。
    """
    allowed, _code, _why = legacy_allowed(kind)
    if not allowed:
        return None
    k = _ALIASES.get(str(kind).strip(), str(kind).strip())
    return LEGACY.get(k)


def legacy_declared(kind):
    """旧位置的**声明路径**（不看是否允许读；用于报"这里本来有个旧位置，但被拒了"）。"""
    k = _ALIASES.get(str(kind).strip(), str(kind).strip())
    return LEGACY.get(k)


def legacy_report():
    """全部旧位置的**逐条判定**（`--print-paths`／`--json`／`account paths` 共用同一份）。"""
    out = {}
    for k in LEGACY:
        allowed, code, why = legacy_allowed(k)
        out[k] = {"旧位置": LEGACY[k], "是否允许读": bool(allowed),
                  "为什么": why, "原因码": code,
                  "文件是否存在": os.path.exists(LEGACY[k])}
    return out


def resolve(kind):
    """kind → 绝对路径。

    kind 取值：home ｜ session_dir/cache_dir/output_dir/logs_dir/secrets_dir
               ｜ session_file ｜ brand_index ｜ credentials_fallback
               ｜ legacy_session_file ｜ legacy_brand_index ｜ legacy_credentials_fallback
               （`legacy_*` 若无旧位置映射、或**被判拒读**，返回 None —— 见 `legacy_allowed()`）
    """
    if not kind:
        raise ValueError("kind 不能为空")
    k = str(kind).strip()
    k = _ALIASES.get(k, k)
    if k == "home":
        return home()
    if k in SUBDIRS:
        return os.path.join(home(), k)
    if k.endswith("_dir"):
        sub = k[: -len("_dir")]
        if sub in SUBDIRS:
            return os.path.join(home(), sub)
    if k.startswith("legacy_"):
        base = k[len("legacy_"):]
        base = _ALIASES.get(base, base)
        if base not in LEGACY:
            raise KeyError("未知 kind: %s" % kind)
        return legacy_path(base)
    if k in FILES:
        sub, name = FILES[k]
        return os.path.join(home(), sub, name)
    raise KeyError("未知 kind: %s" % kind)


def read_candidates(kind):
    """读取候选路径列表：**新位置优先，旧位置兜底**（旧位置**须判为可读**才进候选）。"""
    out = [resolve(kind)]
    lg = legacy_path(kind)
    if lg and lg not in out:
        out.append(lg)
    return out


def ensure_dir(path):
    """尽力建目录（含父目录）。成功 True，被拒 False —— **绝不抛异常**（只读代码目录也要能跑）。"""
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except OSError:
        return False


def ensure_parent(path):
    """为要写的文件建父目录（尽力）。"""
    return ensure_dir(os.path.dirname(os.path.abspath(path)))


def paths():
    """全部落点的字典快照（给 --json 与排障用）。

    `legacy`：旧位置的**声明面**（历史形态，保留兼容）；
    `legacy_gate`：**逐条判定**（TICKET-194 · C）—— 每个旧位置"允不允许读、为什么"，
    被拒的旧位置在 `legacy_<kind>` 里是 `None`（调用方据此不会去读那份越界文件）。
    TICKET-223 追加（`--json` 里如实可见）：`home_refusals`（被拒的候选与拒因）、
    `package_roots`（本次认可的交付副本根）、`legacy_fallback`（旧降级落点与迁移提示）。
    """
    d = {"home": home(), "home_reason": home_reason(),
         "home_refusals": home_refusals(),
         "package_roots": package_roots(),
         "legacy_fallback": {
             "旧降级落点(本副本根)": LEGACY_FALLBACK_HOME,
             "存在": os.path.isdir(LEGACY_FALLBACK_HOME),
             "存在且非空的旧落点": [x for x in legacy_fallback_dirs() if _dir_nonempty(x)],
             "新降级落点": FALLBACK_USER_HOME,
             "是否自动搬运": False,
             "迁移提示": migration_notice(),
         },
         "legacy": {k: v for k, v in LEGACY.items()},
         "legacy_gate": legacy_report()}
    for sub in SUBDIRS:
        d[sub + "_dir"] = resolve(sub + "_dir")
    for k in FILES:
        d[k] = resolve(k)
        d["legacy_" + k] = legacy_path(k)
    return d


def _print_human():
    d = paths()
    print("DANIEL_HOME = %s   (%s)" % (d["home"], d["home_reason"]))
    # 🔴 TICKET-149：回退必须**看得见原因** —— 否则"落点为什么不是系统默认"要翻代码才知道
    # 🔴 TICKET-223：降级落点已出包（`~/.daniel-bot`）；"为什么没选系统默认"由 `home_refusals()` 逐条说
    if d["home_reason"] in FALLBACK_REASONS:
        print("  落点已降级：首选落点 %s 不可用 ⇒ 退到 %s（包外，TICKET-223）"
              % (DEFAULT_HOME_MACOS, d["home"]))
        for r in d.get("home_refusals") or []:
            print("  被拒候选：%s ← %s ｜ %s" % (r.get("候选"), r.get("路径"),
                                            REFUSE_TEXT.get(r.get("拒因"), r.get("拒因"))))
    guard = package_roots()
    print("写守卫（绝不写进包根）：%s" % ("已启用；本次认可的交付副本根："
                               + ("、".join(guard) if guard else "（未发现）")))
    for sub in SUBDIRS:
        print("  %-10s %s" % (sub + "/", d[sub + "_dir"]))
    print("落点文件：")
    for k in ("session_file", "brand_index", "credentials_fallback"):
        print("  %-22s %s" % (k, d[k]))
    print("旧位置（只读兼容，不再新写；🔴 必须落在数据落点之内才允许读）：")
    for k in ("session_file", "brand_index", "credentials_fallback"):
        lp = d.get("legacy_" + k)
        gate = (d.get("legacy_gate") or {}).get(k) or {}
        mark = "" if os.path.exists(str(gate.get("旧位置"))) else "  [不存在]"
        if lp:
            print("  %-22s %s  [允许读]%s" % (k, lp, mark))
        else:
            print("  %-22s %s  [**拒读**：%s]%s" % (k, gate.get("旧位置"),
                                                 gate.get("原因码"), mark))
    note = (d.get("legacy_fallback") or {}).get("迁移提示")
    print("旧降级落点（TICKET-223 已迁出包外）：%s"
          % ("仍存在且非空，见下方迁移提示" if note else "无（或已空）"))
    if note:
        print(note)
    plain = os.environ.get("DANIEL_ALLOW_PLAINTEXT") == "1"
    print("明文降级（secrets/）：%s" % ("已启用 DANIEL_ALLOW_PLAINTEXT=1" if plain else "未启用"))
    print("旧明文凭据显式开关：%s" % ("已启用 %s=1" % ALLOW_LEGACY_CRED_ENV
                                  if os.environ.get(ALLOW_LEGACY_CRED_ENV) == "1"
                                  else "未启用（默认关：旧明文凭据文件不被读取）"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Daniel Copilot 落点解析（TICKET-144）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（含 home 选择理由）")
    ap.add_argument("--print-paths", action="store_true", help="输出人类可读的解析结果")
    ap.add_argument("--kind", help="只解析一个 kind")
    ap.add_argument("--make-dirs", action="store_true", help="创建 session/cache/output/logs 目录（幂等）")
    ap.add_argument("--make-secrets-dir", action="store_true",
                    help="额外创建 secrets/（仅显式降级到明文凭据时才需要）")
    a = ap.parse_args(argv)

    if a.kind:
        try:
            p = resolve(a.kind)
        except (KeyError, ValueError) as e:
            print(str(e), file=sys.stderr)
            return 2
        print(p if not a.json else json.dumps({"kind": a.kind, "path": p}, ensure_ascii=False))
        return 0

    if a.make_dirs or a.make_secrets_dir:
        subs = list(SUBDIRS) if a.make_secrets_dir else [s for s in SUBDIRS if s != "secrets"]
        bad = [s for s in subs if not ensure_dir(resolve(s))]
        if bad:
            print("以下目录无法创建（只读或被拒）：%s" % ", ".join(bad), file=sys.stderr)
            return 1
        print("已就绪：%s" % resolve("home"))
        return 0

    if a.json:
        print(json.dumps(paths(), ensure_ascii=False, indent=1))
        return 0
    _print_human()
    return 0


def cli(argv=None):
    """入口包装：**退出码归一 ＋ 失败时恰好一个 JSON 文档**（收口只有这一处，TICKET-168）。

    本仪器原先只把错误写到 stderr 就 `return 2／1`：退出码是对的，但 `--json` 时 stdout 上
    **没有** `ok=false` 信封 —— 调用方拿不到机器可读的失败理由。现在交给 `daniel_io.cli` 统一收口。
    """
    return daniel_io.cli(main, argv)


if __name__ == "__main__":
    sys.exit(cli())
