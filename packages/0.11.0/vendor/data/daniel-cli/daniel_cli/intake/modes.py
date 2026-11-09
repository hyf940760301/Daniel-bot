# -*- coding: utf-8 -*-
"""两种承载模式的**真实可用能力集合**（运行期派生，不手写任何名单）。

模式定位（用户 2026-10-15 裁决 · 产品级口径）
--------------------------------------------
| 模式 | 形态 | 读链 | 写链 |
|---|---|---|---|
| `cli` | 完整能力集成的落地形态（终端／Cursor／Codex 里装好后就是全量能力） | 直接执行 | **人工确认（`--confirm`）后真执行** |
| `mcp` | Daniel 数据层接入面（能力模块调度） | 直接执行 | **只出确认单，AI 永不自行执行**（由 `TICKET-161` 落地确认卡片通道） |

关键区别**不是**"能力缺失"，而是"**AI 不得自行执行**"这一层：写动作在两种模式下**都可见**，
只是 MCP 模式必须停下来把确认单交给用户（拿命令到 CLI／桌面壳执行）。因此 intake 遇到写动作时
的措辞是「本工序最后一步是<动作>，需要你确认；确认单与可执行命令如下」——
**不许**写成"MCP 不支持"／"能力缺失"（见 `三态` 与 `selfcheck.py` 的措辞断言）。

三态（`模式能力` 前置条件的状态取值）
-------------------------------------
| 状态 | 含义 | 是否阻断 |
|---|---|---|
| `可直接执行` | 该步在**当前模式**下能真跑（读链） | 不阻断 |
| `需人工确认后执行` | 该步是**写动作**：CLI 模式走 `--confirm` 人工确认；MCP 模式出确认单、由人拿到 CLI 执行 | 不算缺件（但执行前必须有人点头） |
| `当前模式不可用` | 真缺失（该命令在当前模式的能力集合里根本不存在） | **硬缺件** → `可执行=false` |

真源（两条路，都从单一真源派生，**没有第二份"哪些命令不可用"的名单**）
----------------------------------------------------------------------
① 首选：`data/daniel-cli/mcp/exposure-register.json`（`TICKET-159` 的差异显式登记表；
   存在就消费，并与运行时派生**互校**，不一致要报出来）；
② 否则：运行时求差集 —— CLI 侧取 `schema.py` 声明的命令集合，MCP 侧取 MCP server
   **自己的注册口径**（`mcp/server.py` 的 `build_registry()`；文件不可定位时退回
   `exports.mcp_tools()` 的注解等价口径）。报告里的 `真源` 字段会写明这次用的是哪条路。
"""
import importlib.util
import json
import os
import re

from .. import exports
from .. import schema as cli_schema

MODE_CLI = "cli"
MODE_MCP = "mcp"
MODES = (MODE_CLI, MODE_MCP)
MODE_ENV = "DANIEL_CLI_MODE"                 # MCP server 起子进程时置为 mcp（见 mcp/server.py）

#: 本包位置：`<仓库根>/data/daniel-cli/daniel_cli/intake/<本文件>` → 上溯三层是 `data/daniel-cli`
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MCP_SERVER_PATH = os.path.join(_PKG_ROOT, "mcp", "server.py")
EXPOSURE_REGISTER_PATH = os.path.join(_PKG_ROOT, "mcp", "exposure-register.json")

#: 三态取值（措辞纪律见文件头；报告与自检都按这三个字面值判）
ST_READY = "可直接执行"
ST_CONFIRM = "需人工确认后执行"
ST_UNAVAILABLE = "当前模式不可用"
MODE_STATUSES = (ST_READY, ST_CONFIRM, ST_UNAVAILABLE)

_CACHE = {}


def mode_label(mode):
    return {"cli": "CLI 模式（完整能力集成）", "mcp": "MCP 模式（Daniel 数据层接入面）"}.get(
        mode, mode)


def current_mode(explicit=None):
    """当前模式：显式 `--mode` 优先（便于自检两侧对等），其次环境变量，缺省 `cli`。"""
    raw = str(explicit or "").strip().lower() or os.environ.get(MODE_ENV, "").strip().lower()
    return MODE_MCP if raw == MODE_MCP else MODE_CLI


def declared_keys():
    return set(cli_schema.declared_command_keys())


def write_keys():
    """声明为写操作的命令键（`--confirm` 才执行；MCP 模式只出确认单）。"""
    return {"%s.%s" % (mod["key"], cmd["name"])
            for mod in cli_schema.SCHEMA["modules"] for cmd in mod["commands"] if cmd["write"]}


def is_write(key):
    return key in write_keys()


def _tool_key_index():
    """`<工具名>` → `<模块>.<子命令>`（名字由 `exports.tool_name` 算，不手写）。"""
    idx = {}
    for mod in cli_schema.SCHEMA["modules"]:
        for cmd in mod["commands"]:
            idx[exports.tool_name(mod["key"], cmd["name"])] = "%s.%s" % (mod["key"], cmd["name"])
    return idx


def _via_mcp_server():
    """MCP 侧能力集合：**直接用 MCP server 自己的注册口径**（不是我们另写一份规则）。"""
    if not os.path.isfile(MCP_SERVER_PATH):
        return None, "MCP server 文件不可定位：%s" % MCP_SERVER_PATH
    try:
        spec = importlib.util.spec_from_file_location("daniel_cli_mcp_server_probe",
                                                     MCP_SERVER_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        registry = mod.build_registry()
    except Exception as e:                                       # noqa: BLE001
        return None, "MCP server 注册口径取不到：%s: %s" % (type(e).__name__, e)
    idx = _tool_key_index()
    keys = set()
    for tool_name in registry:
        if tool_name in idx:
            keys.add(idx[tool_name])
    return keys, "mcp/server.py 的 build_registry()（该 server 自己的注册口径）"


def _via_annotations():
    """等价口径（server.py 不可定位时）：`exports.mcp_tools()` 的注解 ＋ 既有暴露规则。

    规则与 server.py 的 `_exposure` 同构：只读性固定的读链命令 ＋ `readOnly=contract-dependent`
    且 `writeStage=sandbox` 的引擎命令；其余写链**不注册**。
    """
    keys = set()
    for mod in cli_schema.SCHEMA["modules"]:
        for cmd in mod["commands"]:
            key = "%s.%s" % (mod["key"], cmd["name"])
            if not cmd["write"] and exports.read_only_of(cmd) is True:
                keys.add(key)
            elif (exports.read_only_of(cmd) is None and cmd.get("writeStage") == "sandbox"):
                keys.add(key)
    return keys, "schema 派生的只读注解（与 mcp/server.py 的暴露规则同构）"


_KEY_RE = re.compile(r"^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$")


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            for x in _walk(v):
                yield x
    elif isinstance(obj, list):
        for v in obj:
            for x in _walk(v):
                yield x


def read_exposure_register():
    """读 `TICKET-159` 的差异登记表（`mcp/exposure-register.json`，存在才读）。

    它把「CLI 有、MCP 没有」这类差异**逐条登记**（命令／工具名／未暴露原因／替代路径／执行语义），
    断言规则是双向的：**差集里出现登记表之外的条目＝红**（有人偷偷把能力藏了或漏注册），
    **登记表里出现已不存在的命令＝红**（陈旧登记）。

    返回 `({键: 登记条目}, 说明, 执行语义表)`；文件不在或形状不认识时返回 `(None, 原因, {})`
    —— 不猜、不假装读到了。
    """
    if not os.path.isfile(EXPOSURE_REGISTER_PATH):
        return None, "登记表不存在（%s）" % EXPOSURE_REGISTER_PATH, {}
    try:
        with open(EXPOSURE_REGISTER_PATH, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (ValueError, OSError) as e:
        return None, "登记表读不出来：%s" % e, {}
    declared = declared_keys()
    idx = _tool_key_index()
    tool_to_key = {v: k for k, v in idx.items()}          # 工具名 → 键
    rows, semantics = {}, {}
    for node in _walk(doc):
        if not isinstance(node, dict):
            continue
        raw_cmd = node.get("命令") or node.get("cli") or node.get("能力")
        key = None
        if isinstance(raw_cmd, str):
            parts = raw_cmd.replace(".", " ").split()
            if len(parts) == 2:
                key = "%s.%s" % (parts[0], parts[1])
        if key is None:
            tool = node.get("工具名")
            if isinstance(tool, str):
                key = tool_to_key.get(tool)
        if not key or key not in declared:
            continue
        row = dict(node)
        rows[key] = row
        sem = row.get("执行语义")
        if isinstance(sem, str) and sem.strip():
            semantics[key] = sem.strip()
    if not rows:
        return None, "登记表里没认出任何 `模块.子命令` 键（形状不认识，不猜）", semantics
    return rows, "mcp/exposure-register.json（TICKET-159 的差异显式登记表）", semantics


def available(mode=None):
    """某个模式的可用能力集合。返回 `{模式, 能力集合, 会话键, 读链, 写链, 真源, 说明}`。"""
    mode = current_mode(mode)
    cache_key = "av:" + mode
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    declared = declared_keys()
    writes = write_keys()
    if mode == MODE_CLI:
        doc = {"模式": MODE_CLI, "模式说明": mode_label(MODE_CLI),
               "能力集合": declared, "读链": declared - writes, "写链": writes,
               "会话键": declared,
               "真源": "daniel_cli/schema.py 的声明（单一真源）",
               "说明": "CLI 模式：读链直接执行；写链在人工确认（--confirm）后真执行。"}
    else:
        keys, why = _via_mcp_server()
        if keys is None:
            keys, why2 = _via_annotations()
            why = "%s；已改用等价口径：%s" % (why, why2)
        reg_rows, reg_why, semantics = read_exposure_register()
        cross = None
        if reg_rows is not None:
            diff_keys = declared - keys                      # CLI 有、MCP 没有
            unregistered = {k for k, v in reg_rows.items()
                            if str(v.get("执行语义") or "") == "未注册"}
            cross = {"一致": diff_keys == unregistered,
                     "差集（CLI 有／MCP 没有）": sorted(diff_keys),
                     "登记表「未注册」集合": sorted(unregistered),
                     "差集里登记表之外的条目（红）": sorted(diff_keys - set(reg_rows)),
                     "登记表里已不存在的命令（陈旧登记，红）": sorted(set(reg_rows) - declared),
                     # 只有"登记为未注册、却真的注册了"才是红；登记为「执行／确认单不执行」的
                     # （例如 playbook run）本来就在 MCP 集合里，不算异常。
                     "登记「未注册」却真注册了（红）": sorted(unregistered & keys),
                     "说明": reg_why}
        doc = {"模式": MODE_MCP, "模式说明": mode_label(MODE_MCP),
               "能力集合": keys, "读链": set(keys) - writes, "写链": set(keys) & writes,
               "会话键": set(keys),
               "真源": why,
               "登记表互校": cross,
               "写链执行语义": semantics,
               "说明": "MCP 模式：读链直接执行；写链只出确认单、由人拿到 CLI／桌面壳执行"
                       "（写动作在能力面上可见，缺的只是「AI 不得自行执行」这一层）。"}
    _CACHE[cache_key] = doc
    return doc


def diff():
    """两模式的能力差集（键比对）：报告与自检都用它，不另写名单。"""
    cli, mcp = available(MODE_CLI), available(MODE_MCP)
    only_cli = sorted(cli["能力集合"] - mcp["能力集合"])
    only_mcp = sorted(mcp["能力集合"] - cli["能力集合"])
    writes = write_keys()
    return {
        "CLI 能力数": len(cli["能力集合"]),
        "MCP 能力数": len(mcp["能力集合"]),
        "仅在 CLI 可用": only_cli,
        "仅在 MCP 可用": only_mcp,
        "仅差在线写链": sorted(set(only_cli)) == sorted(set(only_cli) & writes),
        "两模式共有": sorted(cli["能力集合"] & mcp["能力集合"]),
        "结论": "MCP 可用集合是 CLI 的子集，且差集恰好是写链未注册部分"
                if (not only_mcp and set(only_cli) <= writes)
                else "两侧存在非写链差异（需要人看一眼）",
    }


def status_for(key, mode=None):
    """某个能力键在某个模式下的三态状态。**写动作在两种模式下都是"需人工确认后执行"**。"""
    mode = current_mode(mode)
    key = str(key or "")
    if is_write(key):
        return ST_CONFIRM
    return ST_READY if key in available(mode)["能力集合"] else ST_UNAVAILABLE


def confirm_command(key, params=None):
    """写动作的**可直接执行的命令**（MCP 模式的确认单里要贴给人照着跑）。

    `params` 是已解析的实参文本（例如 `--brand Halliday`）；删除类命令会自动补
    `--delete-token` 的提醒（该凭据要人自己再写一遍目标名，本函数不代填）。
    """
    mod, _, cmd = str(key).partition(".")
    spec = cli_schema.find_command(mod, cmd)
    if spec is None:
        return "daniel %s %s" % (mod, cmd)
    tail = (" " + params.strip()) if params and params.strip() else ""
    line = "daniel %s %s%s --confirm" % (mod, cmd, tail)
    if spec.get("deleteTarget"):
        line += " --delete-token \"<%s>\"" % spec["deleteTarget"]
    return line


def fact_lines(mode=None):
    """给人看的模式事实（`intake` 报告的抬头用）。"""
    mode = current_mode(mode)
    av = available(mode)
    return {
        "当前模式": av["模式"],
        "当前模式说明": av["模式说明"],
        "当前模式可用能力数": len(av["能力集合"]),
        "当前模式可直接执行": len(av["读链"]),
        "当前模式需人工确认后执行": len(av["写链"]),
        "能力真源": av["真源"],
        "登记表互校": av.get("登记表互校"),
    }
