# -*- coding: utf-8 -*-
"""派生器②③：schema → MCP tool list ＋ DSH `defineTool` 草稿（TICKET-145 §2）。

本模块**只打印，不实现 server**（票面口径）。三样东西同源，因此不会出现"CLI 能跑但工具清单里
没有"或"MCP 参数与 CLI 参数不一致"的情况：`daniel schema --check` 会把派生的参数集合与
CLI 实际注册的参数集合逐条核对。
"""
from . import CLI_NAME
from .schema import SCHEMA
from .exits import name_of

_TYPE_MAP = {"str": "string", "int": "integer", "float": "number",
             "flag": "boolean", "path": "string", "choice": "string"}


def tool_name(module_key, command_name):
    return "%s_%s_%s" % (CLI_NAME, module_key, command_name.replace("-", "_"))


def arg_name(option_name):
    return option_name.lstrip("-").replace("-", "_")


def _describe_option(opt):
    bits = [opt["help"] or ""]
    if opt["type"] == "path":
        bits.append("（文件路径）")
    if opt["choices"]:
        bits.append("（可选：%s）" % "／".join(opt["choices"]))
    if opt["repeat"]:
        bits.append("（可重复传入）")
    return "".join(b for b in bits if b)


def _property_for(opt):
    t = _TYPE_MAP[opt["type"]]
    extra = {"writeOnly": True} if opt.get("secret") else {}
    if opt["type"] == "choice":
        return {"type": t, "enum": list(opt["choices"]), "description": _describe_option(opt),
                **extra}
    if opt["repeat"]:
        return {"type": "array", "items": {"type": t}, "description": _describe_option(opt),
                **extra}
    return {"type": t, "description": _describe_option(opt), **extra}


def input_schema(cmd):
    """命令级 JSON Schema（供 MCP `inputSchema` 与 DSH `parameters` 共用）。"""
    props, required = {}, []
    for opt in cmd["options"]:
        key = arg_name(opt["name"])
        props[key] = _property_for(opt)
        if opt["required"] and key not in required:
            required.append(key)
    if cmd["write"]:
        props["confirm"] = {"type": "boolean",
                            "description": "显式确认执行这次写；缺省为 false。"
                                           "权限（账号能不能写）与确认（防手滑）是两件事："
                                           "没有写权限时即便 confirm=true 也会以退出码 2 说明理由。"}
        props["dry_run"] = {"type": "boolean",
                            "description": "只打印将要做什么，不执行；缺省为 true。"}
        if cmd.get("deleteTarget"):
            props["delete_token"] = {
                "type": "string",
                "description": "删除类的二次确认：把%s原样再写一遍（写错即拒绝、退出码 2，"
                               "且不做任何删除）。" % cmd["deleteTarget"]}
    return {"type": "object", "properties": props, "required": required,
            "additionalProperties": False}


def _cli_equivalent(module_key, cmd):
    parts = [CLI_NAME, module_key, cmd["name"]]
    for opt in cmd["options"]:
        if opt.get("positional"):
            parts.append("<%s>" % (opt["metavar"] or opt["name"]))
        elif opt["required"]:
            parts.append("%s <%s>" % (opt["name"], opt["metavar"] or arg_name(opt["name"])))
    return " ".join(parts) + " --json"


def read_only_of(cmd):
    """`True/False` 是固定事实；`None` 表示**取决于运行期输入**（例如 `playbook run` 取决于
    契约里有没有写步骤）。这类命令不写死布尔注解 —— 写死就是假话（P0-3 修正）。"""
    if cmd.get("readOnlyDynamic"):
        return None
    return not cmd["write"]


def exposure_of(cmd):
    """**MCP 暴露档位**（`TICKET-202`·`Q14`：这是**唯一真源**，协议面与自省载荷都用它）。

    为什么必须是同一个函数（而不是两处各写一遍）：同一命令在**两个载荷**里的口径必须一致 ——
    协议面（`mcp/server.py` 的 `tools/list`）与自省载荷（`daniel schema --mcp --json`）先前各自
    判一次，于是出现了"同一件事两种说法"。判据落在一个函数上，再由 `mcp/client_check.py` 的
    `exposure_mismatches()` **逐工具比对两个载荷**（不一致即红）。

    四档（语义见 `mcp/exposure-register.json`）：
      · `read-only`     —— 只读链，**直接执行**（`readOnlyHint=true`）；
      · `sandbox-only`  —— 只读性取决于契约（`playbook run`）：**可直接执行**，写动作只落本次
                           运行的沙箱、永不转发 `--confirm`；
      · `local-output`  —— **会往本机落点写文件、不写 Daniel 远端**（`playbook deliver`）：
                           **可直接执行**（不是写链），但**不是纯只读**（`readOnlyHint=false`）；
      · `confirm-ticket`—— 写链：注册为**确认单工具**，永不执行。
    """
    if cmd.get("localWriteNote"):
        return "local-output"
    if cmd.get("readOnlyDynamic") and cmd.get("writeStage") == "sandbox":
        return "sandbox-only"
    if cmd["write"]:
        return "sandbox-only" if cmd.get("writeStage") == "sandbox" else "confirm-ticket"
    return "read-only"


def _read_only_note(cmd):
    return cmd.get("readOnlyNote") if cmd.get("readOnlyDynamic") else None


def _description(module, cmd):
    bits = ["[%s] %s" % (module["title"], cmd["summary"].rstrip("。"))]
    if cmd["returns"]:
        bits.append("返回：%s" % cmd["returns"].rstrip("。"))
    if cmd["write"]:
        note = (cmd.get("writeNote") or [None])[0]
        bits.append(note.rstrip("。") if note
                    else "写操作：权限由账号对该模块的使用权限决定，没有权限时退出码 2 并给出理由；"
                         "不带确认只做干跑；删除类还要把目标名原样再写一遍")
        stage = cmd.get("writeStage")
        if stage == "gated":
            bits.append("开放级别：本工序只到干跑（真实执行不在本工序范围）")
        elif stage == "sandbox":
            bits.append("开放级别：写动作只落在本次运行的沙箱目录内")
        elif stage == "live":
            bits.append("开放级别：真实执行已接通（执行后回读校验并留审计）")
    elif cmd.get("localWriteNote"):
        # 🔴 不许写成"只读操作"：它会真写本机文件（`TICKET-202`·`Q14`）。
        bits.append("**本机副作用**：%s" % cmd["localWriteNote"].rstrip("。"))
    else:
        bits.append("只读操作")
    ro_note = _read_only_note(cmd)
    if ro_note:
        bits.append("只读性：%s" % ro_note.rstrip("。"))
    codes = "／".join("%d=%s" % (c, name_of(c)) for c in cmd["exitCodes"])
    bits.append("退出码：%s" % codes)
    return " ｜ ".join(bits) + "。"


def iter_commands():
    for mod in SCHEMA["modules"]:
        for cmd in mod["commands"]:
            yield mod, cmd


def mcp_tools():
    """MCP tool list：`{"name","description","inputSchema"}`（另附注解）。

    注解口径（P0-3 修正 ＋ `TICKET-202`·`Q14` 对齐）：
      · **`exposure` 与 `readOnlyHint` 一律给**（档位由 `exposure_of` 这把唯一真源判）——
        两个载荷口径一致才有意义；协议面（`mcp/server.py`）用的是同一个函数。
      · 只读性**取决于运行期输入**的命令（`playbook run`）：`readOnlyHint=false`（按协议面）
        **并保留**补充说明键 `readOnly="contract-dependent"` ＋ `readOnlyNote`
        —— **布尔键与补充说明并存，不是二选一**。
      · **会往本机落点写文件**的命令（`playbook deliver`）：`exposure="local-output"`、
        `readOnlyHint=false`，注记同放在 `readOnlyNote`（两个载荷同一把钥匙）。
    """
    tools = []
    for mod, cmd in iter_commands():
        exp = exposure_of(cmd)
        ann = {"module": mod["key"], "cli": _cli_equivalent(mod["key"], cmd),
               "exposure": exp, "readOnlyHint": exp == "read-only"}
        if cmd.get("readOnlyDynamic"):
            ann["readOnly"] = "contract-dependent"          # 补充说明键：保留
            ann["readOnlyNote"] = _read_only_note(cmd)
        elif cmd.get("localWriteNote"):
            ann["readOnlyNote"] = cmd["localWriteNote"]     # 本机出件落点事实（与协议面同钥）
        tools.append({
            "name": tool_name(mod["key"], cmd["name"]),
            "description": _description(mod, cmd),
            "inputSchema": input_schema(cmd),
            "annotations": ann,
        })
    return tools


def dsh_tools():
    """DSH `defineTool` 草稿：`{"name","description","parameters"}`（另附 readOnly／cli 便于落地）。

    同上的精度口径：只读性不固定的命令 `readOnly` 给 `null` 并附 `readOnlyNote`；
    **会往本机落点写文件的命令**（`TICKET-202`·`Q14`）`readOnly` 给 `False`（不给 `True` ——
    它会真写本机文件），并附 `readOnlyNote` ＋ `exposure`。
    """
    tools = []
    for mod, cmd in iter_commands():
        ro = read_only_of(cmd)
        exp = exposure_of(cmd)
        tool = {
            "name": tool_name(mod["key"], cmd["name"]),
            "description": _description(mod, cmd),
            "parameters": input_schema(cmd),
            "readOnly": ro,
            "cli": _cli_equivalent(mod["key"], cmd),
            "exposure": exp,
        }
        if ro is None:
            tool["readOnlyNote"] = _read_only_note(cmd)
        elif exp == "local-output":
            tool["readOnly"] = False
            tool["readOnlyNote"] = cmd["localWriteNote"]
        tools.append(tool)
    return tools


def mcp_payload():
    return {
        "generatedBy": SCHEMA["generatedBy"],
        "protocol": "mcp-tools-list",
        "note": "草稿：本工序只产出工具定义，不实现 MCP server。",
        "tools": mcp_tools(),
    }


def dsh_payload():
    return {
        "generatedBy": SCHEMA["generatedBy"],
        "protocol": "dsh-defineTool-draft",
        "note": "草稿：本工序只产出 defineTool 定义，不在 DSH 内注册任何工具。",
        "tools": dsh_tools(),
    }
