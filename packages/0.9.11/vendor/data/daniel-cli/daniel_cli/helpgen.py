# -*- coding: utf-8 -*-
"""派生器①：schema → CLI 的 `--help` 文本（TICKET-145 §2）。

`--help` **不手写第二份**：argparse 解析器完全由 `schema.py` 构建，帮助文本就是 schema 里的
`summary` / `description` / `help` / `examples` / `exitCodes` 渲染出来的。因此"帮助与实际可跑
子命令不一致"这类漂移在结构上不可能发生；`schema --check` 再把它机器化验证一遍。
"""
import argparse
import sys

from . import __version__
from .exits import exit_code_lines, name_of
from .schema import SCHEMA, module_map, rewrite_aliases

FORMATTER = argparse.RawDescriptionHelpFormatter


class _AliasAwareParser(argparse.ArgumentParser):
    """解析前按 schema **声明的** argv 别名重写一次（唯一真源：`schema.cmd_aliases()`）。

    为什么放在解析器上、而不是 CLI 入口里：本仓有多个解析入口（CLI 入口、`schema --check`
    的示例自证、自检），放在解析器上这些入口一次性获得同一种行为，不会出现"某个入口不认别名"。
    别名的声明只在 schema 里，这里不硬编码任何别名表。
    """

    def parse_known_args(self, args=None, namespace=None):
        argv = list(sys.argv[1:] if args is None else args)
        return super().parse_known_args(rewrite_aliases(argv), namespace)


def _common_parent():
    """`--json` / `--verbose` 挂到每一层，`daniel --json brands list` 与
    `daniel brands list --json` 都能用。

    ⚠️ 必须 `default=SUPPRESS`：否则子解析器会用默认值把父层已经解析出来的 `True` 覆盖掉
    （argparse 的经典陷阱），`daniel --json brands list` 会静默变成非 JSON 输出。
    """
    p = argparse.ArgumentParser(add_help=False)
    for opt in SCHEMA["globalOptions"]:
        if opt["name"] in ("--version", "--self-test"):
            continue                      # 只在根层注册
        p.add_argument(opt["name"], action="store_true", default=argparse.SUPPRESS,
                       help=opt["help"])
    return p


#: `--confirm` 的三种说法（按写命令的**开放级别**派生）。帮助必须与该命令的**真实副作用**一致：
#: `live` 会真写；`gated` 加了确认也**不执行**（本工序只到干跑）；`sandbox` 的写动作只落本次运行的
#: 沙箱目录（工序契约引擎的离线假动作）。
CONFIRM_HELP_LIVE = "确认执行这次写；不给则只做干跑（打印将要做什么，不写任何东西）"
CONFIRM_HELP_GATED = ("确认执行；但本工序的真实写尚未接通：权限与确认齐了也只做干跑、不写任何东西"
                      "（退出码 1；未加 --confirm 时退出码 3）")
CONFIRM_HELP_SANDBOX = ("确认执行（只有契约里声明了写步骤时才需要；写类动作是沙箱内的离线假动作，"
                        "不碰任何 Daniel 写路由）")

#: 逐命令的 `--confirm` 说法覆盖（真源在 schema 的 `confirm_help`）：写语义更细的命令
#: （例如"把凭据写进本机钥匙串"）用自己的话说明**究竟会写什么**，不套通用句。
CONFIRM_HELP_BY_STAGE = {"live": CONFIRM_HELP_LIVE, "gated": CONFIRM_HELP_GATED,
                         "sandbox": CONFIRM_HELP_SANDBOX}


def confirm_help_for(cmd):
    """这条写命令的 `--confirm` 帮助文本（命令自带说法优先，否则按开放级别派生）。"""
    if cmd.get("confirmHelp"):
        return cmd["confirmHelp"]
    return CONFIRM_HELP_BY_STAGE.get(cmd.get("writeStage"), CONFIRM_HELP_LIVE)


def _write_note(cmd):
    """写命令的统一提示（三道闸：权限 → 确认 → 删除凭据）。

    `writeNote` 是给"写语义更细"的命令（例如 `playbook run`：只有契约里声明了写步骤时才需要
    确认）用的 —— 它自带说法，帮助文本必须说真话。S6 的机器判据不受影响。
    """
    if not cmd["write"]:
        return []
    if cmd.get("writeNote"):
        return [""] + list(cmd["writeNote"])
    lines = ["",
             "本命令是**写操作**，写链有三道闸：",
             "  ① 权限：由**账号的使用权限**决定 —— 账号对这个模块有写权限才放行；没有权限时"
             "退出码 2，并用一行理由说明是系统角色／账号状态／工作区权益／配额哪一轴不满足"
             "（`daniel account capabilities` 给出完整能力矩阵）；",
             "  ② 确认：不带 --confirm 只做干跑（打印将要做什么＋影响范围），**不执行任何写**"
             "（退出码 3）；"]
    if cmd.get("deleteTarget"):
        lines.append("  ③ 删除凭据：删除类操作在 --confirm 之外必须再给 --delete-token <%s>"
                     "（把%s原样再写一遍；写错即拒、退出码 2、**不做任何删除**）。"
                     % (cmd["deleteTarget"], cmd["deleteTarget"]))
    else:
        lines.append("  ③ 执行：带 --confirm 才真正执行，执行后**回读校验**并留一条可导出的审计"
                     "记录（`daniel account audit`）。")
    if cmd.get("danger"):
        lines += ["", "风险提示：%s。" % cmd["danger"]]
    if cmd.get("writeStage") == "gated":
        lines += ["", "本命令在本工序**只到干跑**：权限与确认齐了也不执行，真实执行不在本工序交付范围。"]
    elif cmd.get("writeStage") == "live":
        lines += ["", "本命令的真实写链**已接通**：带 --confirm 会真的写，写后回读校验并留痕。"]
    return lines


def _epilog_for_command(cmd):
    lines = []
    if cmd["returns"]:
        lines += ["返回内容：", "  " + cmd["returns"], ""]
    if cmd["examples"]:
        lines += ["示例："] + ["  " + e for e in cmd["examples"]]
    if cmd.get("cliAliases"):
        # 别名在真源里声明、由解析器按声明重写 argv（见 `_AliasAwareParser`），这里只如实列出。
        lines += ["", "等价写法（与上面完全一样，任选一种）："]
        lines += ["  %s %s …" % (SCHEMA["cli"], a) for a in cmd["cliAliases"]]
    lines += _write_note(cmd)
    lines += ["", "退出码："]
    lines += ["  %d = %s" % (code, name_of(code)) for code in sorted(cmd["exitCodes"])]
    return "\n".join(lines).strip()


def _epilog_for_module(mod):
    lines = ["模块：「%s」%s" % (mod["title"], mod["summary"])]
    if mod["usageNote"]:
        lines += ["", mod["usageNote"]]
    if mod["flagCommands"]:
        pairs = ["%s（等同 `daniel %s %s`）" % (flag, mod["key"], name)
                 for flag, name in sorted(mod["flagCommands"].items())]
        lines += ["", "快捷开关：" + "；".join(pairs)]
    lines += ["", "退出码："] + ["  %d = %s" % (e["code"], e["name"]) for e in SCHEMA["exitCodes"]]
    return "\n".join(lines)


def _add_option(parser, opt):
    if opt.get("positional"):
        # 位置参数（如 `playbook run <契约>`）：可选写法，缺参由运行期报用户错误。
        # ⚠️ default 必须 SUPPRESS：位置参数与同名 `--name` 共用 dest，若给 None 默认值，
        # 它会**覆盖**已经由 `--name` 解析出来的值（argparse 的经典陷阱）。
        parser.add_argument(opt["name"], nargs="?", default=argparse.SUPPRESS,
                            metavar=opt["metavar"] or opt["name"], help=opt["help"])
        return
    kwargs = {"help": opt["help"]}
    if opt["type"] == "flag":
        kwargs["action"] = "store_true"
        if opt["name"] == "--json":
            kwargs["default"] = argparse.SUPPRESS
    else:
        kwargs["metavar"] = opt["metavar"] or opt["name"].lstrip("-").upper()
        if opt["type"] == "int":
            kwargs["type"] = int
        elif opt["type"] == "float":
            kwargs["type"] = float
        if opt["choices"]:
            kwargs["choices"] = opt["choices"]
        if opt["repeat"]:
            kwargs["action"] = "append"
            kwargs["default"] = None
        elif opt["default"] is not None:
            kwargs["default"] = opt["default"]
        if opt["required"]:
            kwargs["required"] = True
    parser.add_argument(opt["name"], **kwargs)


def build_parser():
    """按 schema 构建根解析器。返回值同时用于解析、帮助与"实际注册集合"核对。"""
    common = _common_parent()
    from . import authgate
    epilog = "\n".join(
        ["约定："] +
        ["  %s：%s" % (k, v) for k, v in SCHEMA["conventions"].items()] +
        [""] + authgate.help_lines() +
        ["", "退出码："] + ["  " + ln for ln in exit_code_lines()] +
        ["", "单一真源：本帮助由 daniel_cli/schema.py 派生；`daniel schema --json` 可拿到机器可读版本。"])
    root = _AliasAwareParser(
        prog=SCHEMA["cli"], parents=[common], formatter_class=FORMATTER,
        description="Daniel Copilot 命令行（TICKET-145）：把 Daniel 的 12 个模块收口成一套"
                    "可被任意宿主调用的入口。读操作直接出结果；写操作默认 dry-run 并要求 --confirm。",
        epilog=epilog)
    root.add_argument("--version", action="version",
                      version="%s %s" % (SCHEMA["cli"], __version__))
    root.add_argument("--self-test", action="store_true",
                      help="跑本 CLI 自检（不发任何采集任务、不做任何写）")

    mod_sub = root.add_subparsers(dest="_module", metavar="<模块>", title="模块")
    for mod in SCHEMA["modules"]:
        mp = mod_sub.add_parser(mod["key"], parents=[common], formatter_class=FORMATTER,
                                help=mod["summary"], description="%s（%s）" % (mod["summary"], mod["title"]),
                                epilog=_epilog_for_module(mod))
        for flag in sorted(mod["flagCommands"]):
            mp.add_argument(flag, action="store_true", default=argparse.SUPPRESS,
                            help="等同 `daniel %s %s`" % (mod["key"], mod["flagCommands"][flag]))
        if mod.get("selfTest"):
            # 模块**自带**自检：只有真的实现了模块级自检的模块才在 schema 里填 `selfTest`，
            # 因此这里注册出来的 `--self-test` 说的都是真话（帮助里没写就是没有）。
            mp.add_argument("--self-test", action="store_true", default=argparse.SUPPRESS,
                            help=mod["selfTest"])
        for opt in mod.get("options") or []:
            # **模块级参数**（见 `schema.m()` 的 `options` 说明）：让
            # `daniel connect --host cursor --print`（参数在开关**前面**）这种自然的写法也能解析。
            # 子命令上声明的是**同一份** `o(...)` 定义，两种写法等价。
            _add_option(mp, opt)
        csub = mp.add_subparsers(dest="_command", metavar="<子命令>", title="子命令")
        for cmd in mod["commands"]:
            help_line = cmd["summary"] if "写操作" in cmd["summary"] or not cmd["write"] \
                else cmd["summary"] + "（写操作）"
            cp = csub.add_parser(cmd["name"], parents=[common], formatter_class=FORMATTER,
                                 help=help_line, description="%s（%s · %s）"
                                 % (cmd["summary"], mod["key"], cmd["name"]),
                                 epilog=_epilog_for_command(cmd))
            for opt in cmd["options"]:
                _add_option(cp, opt)
            if cmd["write"]:
                cp.add_argument("--confirm", action="store_true", help=confirm_help_for(cmd))
                cp.add_argument("--dry-run", action="store_true",
                                help="只打印将要做什么，不执行（默认行为，可省略）")
                if cmd.get("deleteTarget"):
                    # 删除类的第二道确认：把目标名原样再写一遍（写错即拒）
                    cp.add_argument("--delete-token", metavar=cmd["deleteTarget"], default=None,
                                    help="删除类的二次确认：把%s原样再写一遍"
                                         "（写错即拒绝、退出码 2，且不做任何删除）" % cmd["deleteTarget"])
    return root


# ─────────────────────── 从解析器反读"实际注册了什么" ───────────────────────
def subparser_choices(parser):
    """拿 argparse 实际注册的子解析器 {名字: 子解析器}（没有则空 dict）。"""
    for action in parser._actions:                                     # noqa: SLF001
        if isinstance(action, argparse._SubParsersAction):              # noqa: SLF001
            return dict(action.choices)
    return {}


def registered_modules(parser):
    return set(subparser_choices(parser))


def registered_commands(parser):
    out = set()
    for mod_key, mod_parser in subparser_choices(parser).items():
        for cmd_key in subparser_choices(mod_parser):
            out.add("%s.%s" % (mod_key, cmd_key))
    return out


def registered_options(parser):
    """{命令键: 参数名集合}——派生的工具定义与 CLI 实际接受的参数是否一致，由它核对。"""
    out = {}
    for mod_key, mod_parser in subparser_choices(parser).items():
        for cmd_key, cmd_parser in subparser_choices(mod_parser).items():
            names = set()
            for action in cmd_parser._actions:                          # noqa: SLF001
                names.update(action.option_strings)
            out["%s.%s" % (mod_key, cmd_key)] = names
    return out


def declared_options():
    """{命令键: schema 声明的**选项**名集合}（含写操作自动带的门禁开关）。

    位置参数不进这个集合：argparse 的 `option_strings` 对位置参数是空的，
    两边口径要一致（否则 S4 会误报"CLI 缺 name"）。

    删除类命令的 `--delete-token` 由 `delete_target` 派生（schema 声明删除目标 ⇒ 必须有这道闸）。
    """
    out = {}
    for mod in SCHEMA["modules"]:
        for cmd in mod["commands"]:
            names = {o["name"] for o in cmd["options"] if str(o["name"]).startswith("-")}
            if cmd["write"]:
                names |= {"--confirm", "--dry-run"}
                if cmd.get("deleteTarget"):
                    names.add("--delete-token")
            out["%s.%s" % (mod["key"], cmd["name"])] = names
    return out


def help_text_for(module_key, command_name=None):
    """取某模块/某命令的帮助文本（自检里用来核对"帮助可用"）。"""
    mod = module_map().get(module_key)
    if not mod:
        raise KeyError("未知模块：%s" % module_key)
    if not command_name:
        return _epilog_for_module(mod)
    for cmd in mod["commands"]:
        if cmd["name"] == command_name:
            return _epilog_for_command(cmd)
    raise KeyError("未知子命令：%s %s" % (module_key, command_name))
