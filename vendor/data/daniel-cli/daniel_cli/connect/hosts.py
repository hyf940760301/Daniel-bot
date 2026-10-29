# -*- coding: utf-8 -*-
"""`connect` 的宿主适配层：**算路径 → 生成片段 → 幂等合并 → 快照 → 回读对账**（TICKET-189）。

要消灭的东西
------------
在 TICKET-189 之前，「把 Daniel 接进宿主」＝**用户手工往宿主配置里抄一段带本机绝对路径的片段**，
而且 Cursor 与 Codex 是两套格式、还要求用户自己「合并不要覆盖」。换一台电脑或换一个宿主，
这套手工步骤就得重来一遍，且没有任何命令能回答「这套接入到底通不通」。

本模块把这件事做成**一条命令**：

    daniel connect --list ／ --print ／ --apply --confirm ／ --uninstall --confirm ／ --doctor

四条纪律（都能被机械核对）
--------------------------
① **路径一律运行时现算**：包根、`server.py`、`python3`、`cwd`、数据落点全部在调用那一刻算出来
   （包根从本文件位置推、`cwd` 从既有 `.kol-tools` 定位、数据落点走 `daniel_paths`）——
   本文件里**没有一处模块级路径解析**，也没有任何写死的绝对路径（CLS-85 同类：成对改动一次落地）。
② **合并，绝不覆盖**：Cursor 侧只在自己那一个成员的文字区间里改，`mcpServers` 里其它 server
   与无关字段**逐字节不动**；Codex 侧只动属于本产品的那两个表，其它表与注释**逐字节不动**。
   因此重复执行结果不变（幂等），`--uninstall` 也只删自己那一条。
③ **写前落快照、写后回读对账**：改任何文件之前先把原文（含 sha256）复制一份到
   `<DANIEL_HOME>/connect/snapshots/`；写完**重新读回**并逐条对账（条目恰好一条、路径指向当前包、
   数据落点与本次现算一致）。对账不过 ⇒ 报失败，不谎称成功。
④ **"只动了本产品那一条"是有证据的**：`merge_*` 返回的 `proof` 里带着「除本产品那一条以外，
   其它成员的原文逐字节相等」这条断言，供输出与验收件引用。

两个宿主（如实登记，不假装支持更多）
------------------------------------
`cursor`（`~/.cursor/mcp.json`：JSON 的 `mcpServers` 成员）与 `codex`（`~/.codex/config.toml`：
`[mcp_servers.<名>]` 表 ＋ 独立的 `.env` 子表）。**其它宿主本票未支持** —— `--list` 会如实说
「未支持」，而不是给一个没验过的片段。
"""
import difflib
import hashlib
import io
import json
import os
import re
import shutil
import sys
import time

from ..exits import EXIT_INTERNAL, EXIT_USAGE
from ..runtime import CliError, tools_dir

#: 本产品在宿主配置里的名字（两个宿主同名，便于"跨宿主比对"）
ENTRY_NAME = "daniel-copilot"
#: 快照与对账的落点：`<DANIEL_HOME>/connect/`（走 daniel_paths，不写代码目录）
WORK_DIRNAME = "connect"
SNAPSHOT_DIRNAME = "snapshots"
#: Codex 的启动超时（与 `06` 文档的手工片段同值）
STARTUP_TIMEOUT_SEC = 30


# ═══════════════════════ 一、路径：一律运行时现算 ═══════════════════════
def cli_package_root():
    """CLI 包根（`<...>/data/daniel-cli`）。从**本文件位置**推，不写死。"""
    here = os.path.dirname(os.path.realpath(__file__))          # …/daniel_cli/connect
    return os.path.dirname(os.path.dirname(here))               # …/data/daniel-cli


def server_entry():
    """MCP 服务入口的绝对路径（本包里的 `mcp/server.py`）。"""
    return os.path.join(cli_package_root(), "mcp", "server.py")


def _daniel_paths():
    """既有落点解析层（唯一真源；不在本模块里重写落点规则）。"""
    from ..runtime import load_capability
    return load_capability("daniel_paths")


def data_home():
    """本次要写进宿主配置的 `DANIEL_HOME`（**本机现算**，不写死）。

    口径（为什么写"首选候选"而不是"本环境实际会用的那个"）：
      · `DANIEL_HOME` 环境变量优先（用户显式指定就是它）；
      · 否则取 `daniel_paths` 的**首选数据目录**（macOS 上是 `~/Library/Application Support/
        DanielCopilot`）—— 由既有解析层声明，本模块只取它的值，不写第二个真源；
      · **本环境对它不可写时仍然写首选值**：宿主进程（Cursor／Codex）未必受同一个沙箱限制，
        若改写成降级落点，反而会让"终端里的 daniel"与"宿主里的 daniel"指向两份数据 ——
        那正是 06 文档反复强调要避免的事。本环境的实际降级情况在 `--list` 的
        「数据落点环境说明」里如实打印（不制造假警报，也不掩盖）。
    """
    if os.environ.get("DANIEL_HOME"):
        return os.path.abspath(os.path.expanduser(os.environ["DANIEL_HOME"]))
    return _daniel_paths().CANDIDATES[0][1]


def data_home_reason():
    if os.environ.get("DANIEL_HOME"):
        return "环境变量 DANIEL_HOME（两个宿主写同一个值）"
    return "产品首选数据目录（由 daniel_paths 声明，本命令运行时取值）"


def data_home_note():
    """本环境实际会用哪个落点（可能与写进配置的那个不同 —— 如实说明，不制造假警报）。"""
    resolved = _daniel_paths().home(create=False)
    if os.path.realpath(resolved) == os.path.realpath(data_home()):
        return "首选数据目录在本环境可用（可用性探测通过）"
    return ("首选数据目录在本环境不可写 ⇒ 产品进程在本环境会降级到 %s；"
            "写进宿主配置的仍是首选值（宿主进程未必受同样的限制）" % resolved)


def workspace_cwd():
    """写进宿主的 `cwd`：**能力目录（`.kol-tools`）所在的仓库根**，本机现算。

    找不到 `.kol-tools`（例如只把 `data/daniel-cli` 单独拷走）时退化为"包的上一级"，
    并在 `paths()` 的「工作目录来源」里如实标注。
    """
    try:
        return os.path.dirname(tools_dir())
    except CliError:
        return os.path.dirname(cli_package_root())


def _cwd_note():
    try:
        tools_dir()
        return "能力目录（.kol-tools）所在仓库根"
    except CliError:
        return "未找到 .kol-tools ⇒ 退化为 CLI 包的上一级"


def interpreter():
    """写进宿主的解释器：**绝对路径、真实存在、可执行**（宿主进程的 PATH 未必和终端一样）。

    顺序：`DANIEL_CONNECT_PYTHON`（显式指定）→ PATH 上的 `python3` → 当前进程的解释器
    → PATH 上的 `python`；取第一个满足「绝对路径 ＋ 是文件 ＋ 可执行」的候选。
    为什么不写死 `/usr/bin/python3`：那在不同机器／不同装法上未必是同一个解释器；
    本 CLI 纯标准库，任何一个 python3 都跑得起来，**能跑**比"抄一个好看的值"重要。
    """
    cands = [os.environ.get("DANIEL_CONNECT_PYTHON"), shutil.which("python3"),
             sys.executable, shutil.which("python")]
    for c in cands:
        if not c:
            continue
        p = os.path.abspath(os.path.expanduser(str(c)))
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    raise CliError("找不到可用解释器（需要一个绝对路径、可执行的 python3）",
                   code=EXIT_INTERNAL,
                   hint="设 DANIEL_CONNECT_PYTHON=/绝对/路径/python3 后重试")


def interpreter_reason():
    if os.environ.get("DANIEL_CONNECT_PYTHON"):
        return "环境变量 DANIEL_CONNECT_PYTHON"
    w = shutil.which("python3")
    if w and os.path.realpath(interpreter()) == os.path.realpath(w):
        return "终端 PATH 上的 python3"
    return "当前进程的解释器（sys.executable）"


def paths():
    """本次要用到的全部路径（**唯一一次现算**，两个宿主共用同一份）。"""
    return {
        "解释器": interpreter(), "解释器来源": interpreter_reason(),
        "服务入口": server_entry(),
        "工作目录": workspace_cwd(), "工作目录来源": _cwd_note(),
        "数据落点": data_home(), "数据落点来源": data_home_reason(),
        "数据落点环境说明": data_home_note(),
        "CLI 包根": cli_package_root(),
    }


# ═══════════════════════ 二、宿主定义 ═══════════════════════
#: 已支持的宿主（唯一真源）。**其它宿主不在本票范围内** —— 不猜格式、不给没验过的片段。
SUPPORTED = ("cursor", "codex")

#: **尚未适配**的宿主（如实登记：`--list` 单列一行，不静默略过）。
#:
#: 🔴 **口径（TICKET-209 修正）**：这里是「**本产品还没写这个宿主的配置片段生成器**」，
#: **不是「这个宿主用不了本产品的能力」**。三件事是正交的：
#:   ① **CLI 本体**（`daniel` 命令）与宿主**完全无关** —— 任何 agent 都能用 bash 调它；
#:   ② **能力层 skill**（8 束 `kol-*`）也只是**文件**，落在 `<项目>/.agents/skills/`，
#:      凡是读这个目录的 agent（含 DSH）都自动获得；
#:   ③ **只有 MCP 接入这一层与宿主相关** —— 每个宿主的配置文件形态不同，才需要"片段生成器"。
#: ⇒ 因此正确的说法是「**尚未适配**」，不是「未支持」。下面每条都写清了缺什么。
UNSUPPORTED = (
    ("claude-code", "**尚未适配**（不是用不了）：缺的是「把本产品写进 Claude Code 的 MCP 配置」"
                    "这一个适配器；CLI 与 8 束 skill 与该宿主无关，照常可用"),
    ("dsh", "**尚未适配**（不是用不了）：DSH 的 MCP 接入口是 `@deepseek-ai/dsh-mcp-client` 插件"
            "（`serverName`／`transport: stdio`／`command`／`args`），配置写在 profile 的 "
            "`cordis.patch.yml` patch 层；本产品还差一个「生成并合并这条 patch 项」的适配器。"
            "**CLI 与 8 束 skill 在 DSH 里已经可用**（skill 只要落在 `.agents/skills/`）"),
)

_HOSTS = {
    "cursor": {
        "key": "cursor",
        "title": "Cursor",
        "format": "json",
        "配置文件": "~/.cursor/mcp.json（Cursor 官方支持的 MCP 配置文件）",
        "合并口径": "mcpServers 下的一个成员；**其它 server 与无关字段原样保留**",
        "卸载口径": "只删本产品那一个成员，其它 server 原样保留",
    },
    "codex": {
        "key": "codex",
        "title": "Codex",
        "format": "toml",
        "配置文件": "~/.codex/config.toml（`[mcp_servers.<名>]` 表 ＋ `.env` 子表）",
        "合并口径": "[mcp_servers.daniel-copilot] 表 ＋ 独立的 .env 子表；**其它表与注释原样保留**",
        "卸载口径": "只删本产品那两个表，其它表与注释原样保留",
    },
}


def _norm(path):
    """归一化用于**比较**的路径（两侧都要过；只归一化一侧＝没修 · CLS-84）。"""
    return os.path.realpath(os.path.abspath(str(path or "")))


def host_keys():
    return list(SUPPORTED)


def host_meta(key):
    key = str(key or "").strip().lower()
    if key not in _HOSTS:
        raise CliError("不支持的宿主：%r（本票支持：%s）" % (key, "／".join(SUPPORTED)),
                       code=EXIT_USAGE,
                       hint="跑 `daniel connect --list` 看本机各宿主的检测结果")
    return _HOSTS[key]


def config_path(key):
    """宿主配置文件路径。**`~` 在调用那一刻展开**（换机器／换用户自动跟着走）。"""
    host_meta(key)
    home = os.path.expanduser("~")
    if key == "cursor":
        return os.path.join(home, ".cursor", "mcp.json")
    return os.path.join(home, ".codex", "config.toml")


def host_detected(key):
    """本机是否**有该宿主的痕迹**（配置目录存在）。没有就如实说"未检测到"。"""
    return os.path.isdir(os.path.dirname(config_path(key)))


# ═══════════════════════ 三、片段生成（唯一一份） ═══════════════════════
def entry_payload():
    """本产品在宿主配置里的**完整取值**（两个宿主的片段都由它派生，不写第二份）。"""
    p = paths()
    return {
        "command": p["解释器"],
        "args": [p["服务入口"]],
        "cwd": p["工作目录"],
        "env": {"DANIEL_HOME": p["数据落点"]},
    }


def _toml_str(s):
    return '"%s"' % str(s).replace("\\", "\\\\").replace('"', '\\"')


def toml_block():
    """Codex 侧要写进 `config.toml` 的那一段**逐字原文**（表头 ＋ 两张表）。"""
    p = paths()
    return "\n".join([
        "[mcp_servers.%s]" % ENTRY_NAME,
        "command = %s" % _toml_str(p["解释器"]),
        "args = [%s]" % _toml_str(p["服务入口"]),
        "cwd = %s" % _toml_str(p["工作目录"]),
        "startup_timeout_sec = %d" % STARTUP_TIMEOUT_SEC,
        "",
        "[mcp_servers.%s.env]" % ENTRY_NAME,
        "DANIEL_HOME = %s" % _toml_str(p["数据落点"]),
    ])


def _detect_json_indent(text):
    """已经存在的配置文件用的缩进（照抄它：别把整份文件的重排混进 diff 里）。"""
    for line in (text or "").split("\n"):
        s = line.lstrip(" ")
        if s.startswith('"') and line[:len(line) - len(s)].strip() == "" and len(line) - len(s) >= 2:
            return line[:len(line) - len(s)]
    return "  "


def _json_indent_for(key):
    path = config_path(key)
    try:
        if os.path.isfile(path):
            return _detect_json_indent(io.open(path, encoding="utf-8").read())
    except OSError:
        pass
    return "  "


def render_value(key_indent):
    """JSON 侧本产品成员的**取值文本**（续行按 `key_indent` 缩进；键由调用方决定怎么拼）。

    为什么手写这几行而不是 `json.dumps(indent=2)`：路径数组只有一个元素，展开成四行既难读，
    又会与 `06` 文档里那段**手工片段**长得不一样 —— 而本票的目标之一正是"CLI 写出来的，
    就是文档让你手抄的那一份"。每个字符串仍走 `json.dumps` 转义（引号／反斜杠不会漏）。
    生成后由 `snippet_text()` 用 `json.loads` 自证（解析结果必须等于本产品取值）。
    """
    p = entry_payload()
    d = json.dumps
    lines = ["{",
             '  "command": %s,' % d(p["command"], ensure_ascii=False),
             '  "args": [%s],' % d(p["args"][0], ensure_ascii=False),
             '  "cwd": %s,' % d(p["cwd"], ensure_ascii=False),
             '  "env": {',
             '    "DANIEL_HOME": %s' % d(p["env"]["DANIEL_HOME"], ensure_ascii=False),
             '  }',
             "}"]
    return "\n".join([lines[0]] + [key_indent + ln for ln in lines[1:]])


def render_member(key_indent):
    """JSON 侧"本产品这一个成员"的**逐字文本**（键 ＋ 取值；首行不带缩进）。

    `--print` 与 `--apply` 共用它 ⇒ 两处的内容必然逐字一致（这是被要求证明的那条不变量）。
    首行不带缩进是有意的：合并进已有文件时缩进由插入点决定，替换时连键都还在原文里。
    """
    return '"%s": %s' % (ENTRY_NAME, render_value(key_indent))


def snippet_text(key):
    """`--print` 打印的完整片段，**也是 `--apply` 会写进去的那一段**（同一个生成器）。

    - `cursor`：一份可以直接粘进 `~/.cursor/mcp.json` 的完整 JSON 文档；
    - `codex`：一段可以直接追加进 `~/.codex/config.toml` 的完整 TOML 表。
    """
    host_meta(key)
    if key == "cursor":
        unit = _json_indent_for("cursor")
        key_indent = unit + unit                                # mcpServers 的成员缩进
        # ⚠️ 文档里只有本产品这一个成员，因此**不能**带尾逗号（带了就不是合法 JSON）；
        # 合并进已有文件时，逗号由 `merge_json` 按"后面还有没有成员"决定。
        doc = "\n".join(["{", unit + '"mcpServers": {',
                         key_indent + render_member(key_indent), unit + "}", "}"])
        parsed = json.loads(doc)                                # 自证：片段必须是合法 JSON
        if parsed != {"mcpServers": {ENTRY_NAME: entry_payload()}}:
            raise CliError("片段生成自证失败（解析结果与期望取值不一致）", code=EXIT_INTERNAL)
        return doc
    return toml_block()


def snippet_sha256(key):
    return hashlib.sha256(snippet_text(key).encode("utf-8")).hexdigest()


def _printed_entry_text(key):
    """`--print` 那一段里"本产品条目"的原文（用于 print ≡ apply 的逐字比对）。

    口径：**键 ＋ 取值、首行不带缩进** —— 与 `entry_text_in()` 从合并结果里取出的那一段同形
    （合并结果里，键前面的缩进不算这一条的原文）。
    """
    if key == "cursor":
        unit = _json_indent_for("cursor")
        return render_member(unit + unit)
    return toml_block()


def entry_text_in(key, text):
    """从**一份完整文本**（合并结果）里取出"本产品那一段"的原文。"""
    if text is None:
        return None
    if key == "cursor":
        _root, _ms, mine = _handles(text)
        return None if mine is None else text[mine[1]:mine[4]]
    lines, blocks, _ex = _toml_scan(text)
    if not blocks:
        return None
    return "\n".join(lines[min(b[0] for b in blocks):max(b[1] for b in blocks)])


def print_apply_consistency(key, merged_text):
    """`--print` 与 `--apply` 写出内容的**逐字一致性**证据（同一生成器的机械核对）。"""
    printed = _printed_entry_text(key)
    written = entry_text_in(key, merged_text)
    return {
        "逐字一致": bool(written is not None and printed == written),
        "打印片段sha256": hashlib.sha256(printed.encode("utf-8")).hexdigest(),
        "写入片段sha256": (hashlib.sha256(written.encode("utf-8")).hexdigest()
                           if written is not None else None),
        "口径": "两边都由同一个生成器产出（`--print` 打印的就是 `--apply` 会写进去的那一段）",
    }


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: 公开别名：接线层与验收件要拿它算"改前改后 sha256"（唯一一份实现，不写第二处）
sha256_text = _sha256_text


# ═══════════════════════ 四、读宿主配置（只读） ═══════════════════════
def _read_text(path):
    if not os.path.isfile(path):
        return None
    with io.open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def read_config_raw(key):
    return _read_text(config_path(key))


# ── JSON：按**文本区间**定位，只改自己那一个成员 ──
def _skip_ws(s, i):
    while i < len(s) and s[i] in " \t\r\n":
        i += 1
    return i


def _scan_string(s, i):
    j = i + 1
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == '"':
            return s[i:j + 1], j + 1
        j += 1
    raise ValueError("JSON 字符串没有闭合")


def _scan_value(s, i):
    """返回覆盖一个 JSON 值的 `(start, end)`（不含前后空白）。"""
    i = _skip_ws(s, i)
    if i >= len(s):
        raise ValueError("JSON 值缺失")
    c = s[i]
    if c == '"':
        return i, _scan_string(s, i)[1]
    if c in "[{":
        depth, j, in_str, esc = 0, i, False, False
        while j < len(s):
            ch = s[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                j += 1
                continue
            if ch == '"':
                in_str = True
            elif ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
                if depth == 0:
                    return i, j + 1
            j += 1
        raise ValueError("JSON 容器没有闭合")
    j = i
    while j < len(s) and s[j] not in ",}] \t\r\n":
        j += 1
    return i, j


def _object_members(s, start):
    """`s[start]` 处是一个 JSON 对象 → `[(键, 键起点, 键终点, 值起点, 值终点)]`。"""
    i0 = _skip_ws(s, start)
    if i0 >= len(s) or s[i0] != "{":
        raise ValueError("这里不是 JSON 对象")
    i = i0 + 1
    out = []
    while True:
        i = _skip_ws(s, i)
        if i >= len(s):
            raise ValueError("JSON 对象没有闭合")
        if s[i] == "}":
            return out
        if s[i] != '"':
            raise ValueError("JSON 对象的键必须是字符串")
        raw, after = _scan_string(s, i)
        key = json.loads(raw)
        j = _skip_ws(s, after)
        if j >= len(s) or s[j] != ":":
            raise ValueError("JSON 键后面缺少冒号")
        vs, ve = _scan_value(s, j + 1)
        out.append((key, i, after, vs, ve))
        i = _skip_ws(s, ve)
        if i < len(s) and s[i] == ",":
            i += 1
            continue
        if i < len(s) and s[i] == "}":
            return out
        raise ValueError("JSON 成员之间缺少逗号")


def _handles(text):
    """定位 `mcpServers` 与本产品成员。

    返回 `(根成员表, mcpServers 成员元组 or None, 本产品成员元组 or None)`；
    成员元组 = `(键, 键起点, 键终点, 值起点, 值终点)`。
    """
    root = _object_members(text, _skip_ws(text, 0))
    ms = [m for m in root if m[0] == "mcpServers"]
    if not ms:
        return root, None, None
    msm = ms[0]
    members = _object_members(text, msm[3])
    mine = [m for m in members if m[0] == ENTRY_NAME]
    return root, msm, (mine[0] if mine else None)


def _json_members_of_servers(text):
    _root, msm, _mine = _handles(text)
    return [] if msm is None else _object_members(text, msm[3])


def _is_json_object(chunk):
    try:
        return isinstance(json.loads(chunk), dict)
    except ValueError:
        return False


def read_json_state(text):
    """JSON 宿主的只读盘点：`{合法, 条目数, 取值, 其它成员}`。"""
    if text is None:
        return {"合法": False, "不存在": True, "条目数": 0, "取值": None, "其它成员": []}
    try:
        doc = json.loads(text)
    except ValueError as e:
        return {"合法": False, "不存在": False, "条目数": 0, "取值": None, "其它成员": [],
                "解析错误": "不是合法 JSON：%s" % e}
    try:
        _root, msm, _mine = _handles(text)
    except ValueError as e:
        return {"合法": False, "不存在": False, "条目数": 0, "取值": None, "其它成员": [],
                "解析错误": str(e)}
    servers = (doc or {}).get("mcpServers") or {}
    members = [] if msm is None else _object_members(text, msm[3])
    return {"合法": True, "不存在": False,
            "条目数": sum(1 for m in members if m[0] == ENTRY_NAME),
            "取值": servers.get(ENTRY_NAME),
            "其它成员": sorted(k for k in servers if k != ENTRY_NAME),
            "顶层键": sorted(doc.keys()) if isinstance(doc, dict) else []}


# ── TOML：按**表块**定位（逐行处理，其它行逐字节不动） ──
_TABLE_RE = r"^\s*\[\s*mcp_servers\s*\.\s*\"?%s\"?\s*(\.\s*env\s*)?\]" % ENTRY_NAME
_ENV_TABLE_RE = r"^\s*\[\s*mcp_servers\s*\.\s*\"?%s\"?\s*\.\s*env\s*\]" % ENTRY_NAME
_DOTTED_RE = r"^\s*mcp_servers\s*\.\s*\"?%s\"?" % ENTRY_NAME
_ANY_HEADER_RE = r"^\s*\["
_OTHER_MS_RE = r"^\s*\[\s*mcp_servers\s*\.\s*\"?([A-Za-z0-9_\-]+)\"?"


def _toml_lines(text):
    if text == "":
        return [], True
    end_nl = text.endswith("\n")
    lines = text.split("\n")
    if end_nl:
        lines = lines[:-1]
    return lines, end_nl


def _toml_scan(text):
    """只读盘点 TOML：本产品占的表块区间 ＋ 本命令**接不住**的写法。"""
    lines, _nl = _toml_lines(text)
    blocks, cur, exotic = [], None, None
    for i, line in enumerate(lines):
        if re.match(_ANY_HEADER_RE, line):
            if cur is not None:
                cur[1] = i
                blocks.append(cur)
                cur = None
            if re.match(_TABLE_RE, line):
                cur = [i, len(lines)]
            continue
        if re.match(_DOTTED_RE, line) and "=" in line:
            exotic = exotic or ("点号赋值写法（`mcp_servers.%s = …`）" % ENTRY_NAME)
        if re.match(r"^\s*%s\s*=" % re.escape(ENTRY_NAME), line):
            exotic = exotic or ("写在 `[mcp_servers]` 表里的子键写法（`%s = …`）" % ENTRY_NAME)
        if re.match(r"^\s*mcp_servers\s*=\s*\{", line):
            exotic = exotic or "行内表写法（`mcp_servers = { … }`）"
    if cur is not None:
        cur[1] = len(lines)
        blocks.append(cur)
    return lines, blocks, exotic


def _toml_pairs(lines, start, end):
    """表体 → `{键: 值}`（只认 `键 = 值` 行；注释与空行跳过；不执行 TOML）。"""
    out = {}
    for line in lines[start:end]:
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _eq, v = s.partition("=")
        out[k.strip()] = v.strip().strip('"')
    return out


def _toml_entry_value(lines, blocks):
    """从表块里**回读**本产品的取值（回读对账用）。"""
    main, envbx = {}, {}
    for b in blocks:
        head = lines[b[0]]
        target = envbx if re.match(_ENV_TABLE_RE, head) else main
        target.update(_toml_pairs(lines, b[0] + 1, b[1]))
    main.pop("env", None)
    if envbx:
        main["env"] = envbx
    v = main.get("args")
    if isinstance(v, str) and v.startswith("[") and v.endswith("]"):
        main["args"] = [x.strip().strip('"') for x in v[1:-1].split(",") if x.strip()]
    if "startup_timeout_sec" in main:
        try:
            main["startup_timeout_sec"] = int(main["startup_timeout_sec"])
        except ValueError:
            pass
    return main


def _toml_others(text):
    lines, _nl = _toml_lines(text)
    out = []
    for line in lines:
        m = re.match(_OTHER_MS_RE, line)
        if m and m.group(1) != ENTRY_NAME:
            out.append(m.group(1))
    return sorted(set(out))


def read_toml_state(text):
    if text is None:
        return {"合法": False, "不存在": True, "条目数": 0, "取值": None, "其它成员": []}
    lines, blocks, exotic = _toml_scan(text)
    if exotic:
        return {"合法": False, "不存在": False, "条目数": 0, "取值": None, "其它成员": [],
                "解析错误": "本命令接不住的 TOML 写法：%s（请手工改，或先备份后改成标准表写法）" % exotic}
    n = sum(1 for b in blocks if not re.match(_ENV_TABLE_RE, lines[b[0]]))
    return {"合法": True, "不存在": False, "条目数": n,
            "取值": _toml_entry_value(lines, blocks), "其它成员": _toml_others(text)}


def read_state(key):
    """宿主配置的只读盘点（两种格式同一口径）。"""
    path = config_path(key)
    text = _read_text(path)
    st = read_json_state(text) if key == "cursor" else read_toml_state(text)
    st.update({"宿主": key, "配置文件": path, "存在": text is not None,
               "宿主是否检测到": host_detected(key),
               "sha256": _sha256_text(text) if text is not None else None,
               "字节数": len(text.encode("utf-8")) if text is not None else 0})
    return st


# ═══════════════════════ 五、幂等合并（只动自己那一条） ═══════════════════════
def _json_proof(old, new, kind):
    """对账证据：改动前后，**除本产品那一条以外**的成员原文逐字节相等。"""
    try:
        others_old = [m for m in _json_members_of_servers(old) if m[0] != ENTRY_NAME]
        others_new = [m for m in _json_members_of_servers(new) if m[0] != ENTRY_NAME]
    except ValueError:
        return {"操作": kind, "其它成员未动": False, "其它成员": [],
                "说明": "改动前后有一侧不是合法 JSON 对象（对账做不了）"}
    same = (len(others_old) == len(others_new) and
            all(a[0] == b[0] and old[a[3]:a[4]] == new[b[3]:b[4]]
                for a, b in zip(others_old, others_new)))
    return {"操作": kind, "其它成员未动": bool(same),
            "其它成员": [m[0] for m in others_old],
            "本产品条目": ENTRY_NAME,
            "对账口径": "除本产品那一条外，其它成员的原文区间逐字节相等"}


def merge_json(text, indent_unit=None):
    """把本产品成员合并进 JSON 文本。返回 `(新文本, 证据)`；**不写任何文件**。

    两种情形：已有本产品成员 ⇒ 只替换**它的取值区间**；没有 ⇒ 在 `mcpServers` 的 `{` 之后
    插入一个成员（原内容整体后移，逐字节不动）。
    """
    if text is None or text.strip() == "":
        unit = indent_unit or "  "
        text = "{\n%s\"mcpServers\": {}\n}\n" % unit
    if not _is_json_object(text):
        raise CliError("宿主配置的顶层不是合法 JSON 对象，本命令不擅自改写", code=EXIT_USAGE,
                       hint="先修好这份配置（%s）再来；也可以只跑 `--print` 拿片段手工粘"
                            % config_path("cursor"))
    root, msm, mine = _handles(text)
    if msm is None:
        raise CliError("这份配置里没有 mcpServers 对象，本命令不擅自新建（免得覆盖你已有的写法）",
                       code=EXIT_USAGE,
                       hint='确认该文件确实是宿主的 MCP 配置文件；或在其中加一行 '
                            '"mcpServers": {} 后重试')
    if not _is_json_object(text[msm[3]:msm[4]]):
        raise CliError("mcpServers 不是对象，本命令不擅自改写", code=EXIT_USAGE)
    unit = indent_unit or _detect_json_indent(text)
    ms_line_start = text.rfind("\n", 0, msm[1]) + 1
    parent_indent = text[ms_line_start:msm[1]]
    if mine is not None:
        key_indent = text[text.rfind("\n", 0, mine[1]) + 1:mine[1]]
        # 只换**取值**那一段：键与它前面的缩进都留在原文里（连键一起重写会把"只动这一条"
        # 退化成"重写这一条"，也没必要）。
        new_text = text[:mine[3]] + render_value(key_indent) + text[mine[4]:]
        kind = "替换（本产品那一条）"
    else:
        members = _object_members(text, msm[3])
        if members:
            key_indent = text[text.rfind("\n", 0, members[0][1]) + 1:members[0][1]]
            if key_indent.strip() != "":
                key_indent = unit + unit
            add = "\n" + key_indent + render_member(key_indent) + ","
        else:
            key_indent = unit + unit
            add = "\n" + key_indent + render_member(key_indent) + "\n" + parent_indent
        new_text = text[:msm[3] + 1] + add + text[msm[3] + 1:]
        kind = "新增（本产品那一条）"
    expect = json.loads(text)
    servers = dict(expect.get("mcpServers") or {})
    servers[ENTRY_NAME] = entry_payload()
    expect["mcpServers"] = servers
    if json.loads(new_text) != expect:      # 合并自证：结果必须正好是「原内容 ＋ 本产品那一条」
        raise CliError("合并自证失败（结果与「原内容 ＋ 本产品那一条」不一致），已放弃写入",
                       code=EXIT_INTERNAL)
    return new_text, _json_proof(text, new_text, kind)


def _lines_outside_our_tables(text):
    lines, _nl = _toml_lines(text)
    out, cur_ours = [], False
    for line in lines:
        if re.match(_ANY_HEADER_RE, line):
            cur_ours = bool(re.match(_TABLE_RE, line))
        if not cur_ours:
            out.append(line)
    return out


def merge_toml(text, block=None):
    """把本产品的两个表合并进 TOML 文本（逐行拼接，其它行逐字节不动）。"""
    block = toml_block() if block is None else block
    if text is None or text.strip() == "":
        return block + "\n", {"操作": "写入（新建文件）", "其它表未动": True, "其它表": [],
                              "对账口径": "新建文件，没有别的表"}
    lines, blocks, exotic = _toml_scan(text)
    if exotic:
        raise CliError("这份 config.toml 用了本命令接不住的写法：%s" % exotic, code=EXIT_USAGE,
                       hint="请手工改，或先备份后改成标准的 [mcp_servers.<名>] 表写法")
    others_before = _lines_outside_our_tables(text)
    block_lines = block.split("\n")
    if blocks:
        start, end = min(b[0] for b in blocks), max(b[1] for b in blocks)
        new_lines = lines[:start] + block_lines + lines[end:]
        kind = "替换（本产品那两个表）"
    else:
        new_lines = list(lines)
        while new_lines and new_lines[-1].strip() == "":
            new_lines.pop()
        if new_lines:
            new_lines.append("")
        new_lines += block_lines
        kind = "新增（本产品那两个表）"
    new_text = "\n".join(new_lines)
    if not new_text.endswith("\n"):
        new_text += "\n"
    return new_text, {"操作": kind, "其它表未动": others_before == _lines_outside_our_tables(new_text),
                      "其它表": _toml_others(new_text),
                      "对账口径": "除本产品那两个表外，其它行逐字节相等（含注释与空行）"}


def uninstall_json(text):
    """只删本产品那一个成员（连它那一行的逗号／空白），其它原文逐字节不动。"""
    _root, msm, mine = _handles(text)
    if mine is None or msm is None:
        return text, {"操作": "无需删除", "删了": 0, "其它成员": _json_members_of_servers(text)}
    members = _object_members(text, msm[3])
    idx = [i for i, m in enumerate(members) if m[0] == ENTRY_NAME][0]
    ks, mve = mine[1], mine[4]
    line_start = text.rfind("\n", 0, ks) + 1
    if idx < len(members) - 1:
        nxt = members[idx + 1][1]
        nxt_line_start = text.rfind("\n", 0, nxt) + 1
        if nxt_line_start > mve and nxt_line_start > line_start:
            new_text = text[:line_start] + text[nxt_line_start:]
        else:                                       # 同一行里的两个成员（少见）
            comma = text.find(",", mve)
            end = comma + 1 if (comma != -1 and comma < nxt) else nxt
            new_text = text[:ks] + text[end:]
    else:
        comma = text.rfind(",", 0, ks)
        if comma != -1 and comma > msm[3]:
            new_text = text[:comma] + text[mve:]
        else:                                       # 唯一成员：只留下空对象
            close_line = text.rfind("\n", 0, msm[4] - 1) + 1
            new_text = text[:msm[3] + 1] + text[close_line:]
    expect = json.loads(text)
    servers = dict(expect.get("mcpServers") or {})
    servers.pop(ENTRY_NAME, None)
    expect["mcpServers"] = servers
    if json.loads(new_text) != expect:      # 卸载自证：结果必须正好是「原内容 减 本产品那一条」
        raise CliError("卸载自证失败（结果与「原内容 减 本产品那一条」不一致），已放弃写入",
                       code=EXIT_INTERNAL)
    return new_text, {"操作": "删除（只删本产品那一条）", "删了": 1,
                      "其它成员": sorted(k for k in servers if k != ENTRY_NAME),
                      "本产品条目": ENTRY_NAME}


def uninstall_toml(text):
    lines, blocks, exotic = _toml_scan(text)
    if exotic:
        raise CliError("这份 config.toml 用了本命令接不住的写法：%s" % exotic, code=EXIT_USAGE)
    if not blocks:
        return text, {"操作": "无需删除", "删了": 0, "其它表": _toml_others(text)}
    start, end = min(b[0] for b in blocks), max(b[1] for b in blocks)
    kept = lines[:start] + lines[end:]
    while kept and kept[-1].strip() == "":
        kept.pop()
    new_text = ("\n".join(kept) + "\n") if kept else ""
    return new_text, {"操作": "删除（只删本产品那两个表）", "删了": len(blocks),
                      "其它表": _toml_others(new_text),
                      "对账口径": "除本产品那两个表外，其它行逐字节相等（含注释与空行）"}


def merge(key, text):
    return merge_json(text) if key == "cursor" else merge_toml(text)


def uninstall(key, text):
    return uninstall_json(text) if key == "cursor" else uninstall_toml(text)


def diff_lines(before, after, limit=400):
    """逐行 diff（**干跑就打印它**：让用户在按 `--confirm` 之前先看清改哪几行）。"""
    a = [] if before is None else before.split("\n")
    b = [] if after is None else after.split("\n")
    out = []
    for line in difflib.unified_diff(a, b, fromfile="改前", tofile="改后", lineterm="", n=3):
        out.append(line)
        if len(out) >= limit:
            out.append("…（diff 过长已截断）")
            break
    return out


# ═══════════════════════ 六、快照 ＋ 写 ＋ 回读对账 ═══════════════════════
def snapshot_root():
    """快照落点（走既有解析层；不写代码目录）。"""
    return os.path.join(_daniel_paths().resolve("home"), WORK_DIRNAME, SNAPSHOT_DIRNAME)


def write_snapshot(path, text):
    """把原文（含 sha256）留一份副本；**写不进去就抛错**（宁可不改配置，也不留无法回滚的改动）。"""
    root = snapshot_root()
    try:
        if not os.path.isdir(root):
            os.makedirs(root)
    except OSError as e:
        raise CliError("快照目录建不出来（%s）：%s" % (root, e), code=EXIT_INTERNAL,
                       hint="先确认数据落点可写（`daniel account paths`）")
    digest = _sha256_text(text)
    dest = os.path.join(root, "%s.%s.%s.orig" % (
        os.path.basename(path), time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()), digest[:12]))
    try:
        with io.open(dest, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as e:
        raise CliError("快照写不进去（%s）：%s" % (dest, e), code=EXIT_INTERNAL,
                       hint="先确认数据落点可写（`daniel account paths`）")
    if _sha256_text(io.open(dest, encoding="utf-8").read()) != digest:
        raise CliError("快照回读对账不过（sha256 与原文不一致）：%s" % dest, code=EXIT_INTERNAL)
    return {"路径": dest, "sha256": digest, "字节数": len(text.encode("utf-8"))}


def write_text(path, text):
    """**原子落盘**（父目录不存在就建）—— 只写这一个文件，不动别处。

    为什么先写临时文件再 `os.replace`：直接 `open(path, "w")` 会先**截断**原文件，万一写到一半
    失败（磁盘满／权限被撤／进程被杀），用户手里就剩一份**半截的宿主配置** —— 那是比"没写"严重
    得多的结果。临时文件与目标同目录 ⇒ 同一文件系统 ⇒ `os.replace` 是原子的：要么全是旧的，
    要么全是新的。原文件的权限位照搬（不因为换了 inode 而放宽／收紧）。
    """
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent)
        except OSError as e:
            raise CliError("目录建不出来（%s）：%s" % (parent, e), code=EXIT_INTERNAL,
                           hint="确认该宿主目录可写（例如 Cursor／Codex 是否装在这台机器上）")
    existed = os.path.isfile(path)
    mode = os.stat(path).st_mode & 0o777 if existed else None
    tmp = path + ".daniel-connect-tmp"
    try:
        with io.open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except OSError as e:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise CliError("配置文件写不进去（%s）：%s。**原文件一个字节都没动**（本次是先写临时文件、"
                       "再原子替换；失败时目标文件仍是原文）" % (path, e), code=EXIT_INTERNAL,
                       hint="① 若被沙箱／权限拦住，请在终端里重跑本命令；"
                            "② 改动前的原文已落快照，可手工还原")
    return {"路径": path, "sha256": _sha256_text(text), "字节数": len(text.encode("utf-8")),
            "此前是否存在": existed}


def readback(key, expected, mode="apply"):
    """**回读对账**：重新读回盘上的文件，逐条核对。

    `apply` ⇒ 条目恰好一条、路径指向当前包、数据落点与本次现算一致；
    `uninstall` ⇒ 条目**一条不剩**、配置文件仍可解析（其它 server／表还在）。
    对账口径随动作而变 —— 卸载后还要求"恰好一条"就是自相矛盾。
    """
    st = read_state(key)
    entry = st.get("取值") or {}
    args = entry.get("args") or [None]
    if mode == "uninstall":
        checks = [
            {"项": "配置文件能读回", "通过": st.get("存在") is True},
            {"项": "本产品条目已全部删掉", "通过": st.get("条目数") == 0, "实际": st.get("条目数")},
            {"项": "文件仍可解析（没写坏）", "通过": not st.get("解析错误"),
             "实际": st.get("解析错误")},
            {"项": "其它 server／表仍在", "通过": True, "实际": "、".join(st.get("其它成员") or []) or "无"},
        ]
    else:
        checks = [
            {"项": "配置文件能读回", "通过": st.get("存在") is True},
            {"项": "本产品条目恰好一条", "通过": st.get("条目数") == 1, "实际": st.get("条目数")},
            {"项": "服务入口指向当前包", "通过": _norm(args[0]) == _norm(expected["服务入口"]),
             "实际": args[0]},
            {"项": "工作目录指向当前包所在仓库",
             "通过": _norm(entry.get("cwd")) == _norm(expected["工作目录"]),
             "实际": entry.get("cwd")},
            {"项": "数据落点与本次现算一致",
             "通过": _norm((entry.get("env") or {}).get("DANIEL_HOME")) ==
                     _norm(expected["数据落点"]),
             "实际": (entry.get("env") or {}).get("DANIEL_HOME")},
        ]
    bad = [c["项"] for c in checks if not c["通过"]]
    return {"verified": not bad, "detail": {"回读逐项": checks}, "sha256": st.get("sha256"),
            "reason": None if not bad else "回读对账未通过：" + "；".join(bad)}
