# -*- coding: utf-8 -*-
"""单一真源的一致性自证（`daniel schema --check`）。

要挡住的是**两份真源**这类结构性缺陷：
  - schema 声明了某条子命令，但 CLI 里没注册（用户看得见、跑不了）；
  - 命令注册表里有实现，但 schema 没声明（跑得了、清单里查不到、派生工具定义里也没有）；
  - 派生的参数集合与 CLI 实际接受的参数不一致（MCP/DSH 工具定义会传错参数）；
  - 示例里写了不存在的参数（文档骗人）。
"""
import shlex

from . import exports, permissions, schema
from .commands import REGISTRY
from .helpgen import (build_parser, declared_options, registered_commands, registered_modules,
                      registered_options)

#: 每层解析器都会带的通用开关 + argparse 自带的帮助开关（比对参数集合时不算差异）
_AMBIENT_OPTIONS = {"-h", "--help", "--json", "--verbose"}


def _check(cid, desc, ok, detail=""):
    return {"id": cid, "desc": desc, "ok": bool(ok), "detail": detail}


def _declared_command(key):
    """`<模块>.<子命令>` → schema 里的命令定义（没有则 None）。"""
    mod_key, _, cmd_name = str(key).partition(".")
    return schema.find_command(mod_key, cmd_name)


def _permission_matrix_check():
    """S10：权限矩阵覆盖全部业务模块，且"能写"与"不能写"两条路都判得出来。

    这条断言把"写链由账号权限决定"从文档口径变成可机器验证的事实：
      · 12 个业务模块**每个**都有判据（缺失即报）；
      · 判据表里每条都带**前端出处**（不许凭印象给模块定权限）；
      · 用管理角色快照跑一遍：12 个模块写全开（与用户口径一致）；
      · 用一个降级角色快照跑一遍：必须出现写不放行，且理由里点出具体是哪一轴（不能只说"拒绝了"）。
    """
    business = set(schema.cli_modules())
    problems = []
    missing = sorted(business - set(permissions.rule_keys()))
    if missing:
        problems.append("这些业务模块没有权限判据：%s" % "／".join(missing))
    no_evidence = [k for k, r in permissions.MODULE_RULES.items() if not r.get("evidence")]
    if no_evidence:
        problems.append("这些模块的判据没有写出处：%s" % "／".join(sorted(no_evidence)))

    admin = permissions.auth_from_inputs("super_admin", "active", source="schema-check")
    rows = permissions.capability_matrix(admin)
    not_allowed = [r["模块"] for r in rows if not r["写"][permissions.K_ALLOWED]]
    if len(rows) != len(business):
        problems.append("能力矩阵行数 %d 与业务模块数 %d 不一致" % (len(rows), len(business)))
    if not_allowed:
        problems.append("管理角色下仍不放行的模块：%s" % "／".join(not_allowed))

    viewer = permissions.auth_from_inputs("viewer", "pending", features=(), plan_tier="starter",
                                          max_brands=0, source="schema-check")
    vrows = permissions.capability_matrix(viewer)
    denied = [r for r in vrows if not r["写"][permissions.K_ALLOWED]]
    if not denied:
        problems.append("降级角色下没有任何模块被拒（权限维度等于没生效）")
    for r in denied:
        v = permissions.verdict(r["模块"], permissions.WRITE, viewer)
        if not v["deniedAxes"]:
            problems.append("%s 被拒但没说清是哪一轴不满足" % r["模块"])
        if not permissions.denial_message(r["模块"], permissions.WRITE, v):
            problems.append("%s 被拒但给不出人话理由" % r["模块"])
    detail = ("12 个业务模块判据齐备；管理角色 12/12 可写；降级角色可写 %d/12（被拒：%s）"
              % (len(vrows) - len(denied), "／".join(r["模块"] for r in denied)))
    return _check("S10", "权限矩阵覆盖 12 个业务模块，且管理角色全开、降级角色被拒并给出理由",
                  not problems, "；".join(problems) or detail)


def schema_consistency():
    parser = build_parser()
    declared = schema.declared_command_keys()
    cli_keys = registered_commands(parser)
    impl_keys = set(REGISTRY)

    checks = []

    checks.append(_check(
        "S1", "CLI 实际注册的子命令集合 ≡ schema 声明的集合",
        declared == cli_keys,
        "仅 schema 有：%s ｜ 仅 CLI 有：%s" % (sorted(declared - cli_keys) or "无",
                                            sorted(cli_keys - declared) or "无")))

    checks.append(_check(
        "S2", "每条声明的子命令都有实现（注册表齐备）",
        declared == impl_keys,
        "缺实现：%s ｜ 多实现：%s" % (sorted(declared - impl_keys) or "无",
                                    sorted(impl_keys - declared) or "无")))

    mods_declared = set(schema.module_keys())
    mods_cli = registered_modules(parser)
    missing_required = [k for k in schema.REQUIRED_MODULES if k not in mods_declared]
    checks.append(_check(
        "S3", "12 个业务模块齐备（外加元模块 schema）",
        mods_declared == mods_cli and not missing_required,
        "声明 %d 个模块；缺票面模块：%s" % (len(mods_declared), missing_required or "无")))

    decl_opts = declared_options()
    cli_opts = registered_options(parser)
    diffs = []
    for key in sorted(declared | set(cli_opts)):
        d, c = decl_opts.get(key, set()), cli_opts.get(key, set())
        extra = sorted(c - d - _AMBIENT_OPTIONS)
        miss = sorted(d - c)
        if extra or miss:
            diffs.append("%s：CLI 多 %s；CLI 缺 %s" % (key, extra or "无", miss or "无"))
    checks.append(_check("S4", "每条命令的参数集合与清单一致（派生工具定义才可信）",
                         not diffs, "；".join(diffs[:6]) or "全部一致"))

    vague = []
    for mod in schema.SCHEMA["modules"]:
        for cmd in mod["commands"]:
            if not cmd["summary"] or not cmd["returns"] or not cmd["examples"]:
                vague.append("%s.%s" % (mod["key"], cmd["name"]))
    checks.append(_check("S5", "每条命令都有摘要、返回说明与示例", not vague,
                         "缺项：%s" % (vague or "无")))

    gating = []
    local_exempt = []
    for mod in schema.SCHEMA["modules"]:
        for cmd in mod["commands"]:
            key = "%s.%s" % (mod["key"], cmd["name"])
            opts = cli_opts.get(key, set())
            if not cmd["write"]:
                if "--confirm" in opts:
                    gating.append("%s 是读操作却带 --confirm" % key)
                if "--delete-token" in opts:
                    gating.append("%s 是读操作却带 --delete-token" % key)
                continue
            # 写命令：三道闸都要真的注册出来（声明了就必须有，不许只在文档里写）
            if not {"--confirm", "--dry-run"} <= opts:
                gating.append("%s 缺 --confirm/--dry-run" % key)
            if cmd.get("writeStage") not in ("live", "gated", "sandbox"):
                gating.append("%s 没声明写命令的开放级别（writeStage）" % key)
            # 「非业务模块的写级别只能是 sandbox」**唯一例外**＝`schema.LOCAL_WRITE_MODULES`
            # （写本机文件、不是 Daniel 数据，见那张表的逐条理由）。豁免必须**显式打印**，
            # 不做静默分支 —— 静默豁免就是门禁自己骗自己。
            if mod["key"] in schema.LOCAL_WRITE_MODULES:
                local_exempt.append(key)
            elif mod["key"] not in schema.REQUIRED_MODULES and cmd.get("writeStage") != "sandbox":
                gating.append("%s 属于元模块/引擎模块，写级别只能是 sandbox（本地副作用类模块须登记进 "
                              "schema.LOCAL_WRITE_MODULES 并写明理由）" % key)
            if cmd.get("deleteTarget"):
                if "--delete-token" not in opts:
                    gating.append("%s 是删除类却没注册 --delete-token" % key)
            elif "--delete-token" in opts:
                gating.append("%s 不是删除类却带 --delete-token" % key)
            if mod["key"] in schema.REQUIRED_MODULES and mod["key"] not in permissions.MODULE_RULES:
                gating.append("%s 所属模块没有权限判据（写链不能没有权限维度）" % key)
    detail6 = "；".join(gating) or "全部合规"
    if local_exempt:
        detail6 += ("（本机副作用类模块豁免 sandbox-only 约束，显式登记：%s —— 理由见 "
                    "schema.LOCAL_WRITE_MODULES）" % "、".join(sorted(local_exempt)))
    checks.append(_check(
        "S6", "写命令三道闸齐备（权限判据＋确认开关＋删除类 token 开关），读操作不带这些开关",
        not gating, detail6))

    # S6 的第二半：门禁**真的装上了**（实现层标记），而不只是参数存在
    unmarked = []
    for key in sorted(declared):
        cmd = _declared_command(key)
        if not (cmd and cmd["write"]):
            continue
        handler = REGISTRY.get(key)
        mark = getattr(handler, "_danielWriteGate", None)
        if cmd.get("writeStage") == "sandbox":
            continue                       # 契约引擎的写动作只落沙箱，门禁在执行器内部（见 playbook）
        if not mark:
            unmarked.append("%s 的实现没有装写门禁" % key)
            continue
        if mark.get("module") != key.split(".")[0] or mark.get("command") != key.split(".", 1)[1]:
            unmarked.append("%s 的门禁标记与声明不一致" % key)
        if not (mark.get("permissionGated") and mark.get("confirmGated")):
            unmarked.append("%s 的门禁缺权限轴或确认轴" % key)
        if bool(cmd.get("deleteTarget")) != bool(mark.get("deleteToken")):
            unmarked.append("%s 的删除凭据开关与实现不一致" % key)
    checks.append(_check(
        "S7", "每条写命令的实现真的装了写门禁（权限轴＋确认轴＋删除凭据轴与声明一致）",
        not unmarked, "；".join(unmarked) or "全部已装"))

    tools = exports.mcp_tools()
    names = [t["name"] for t in tools]
    dsh = exports.dsh_tools()
    bad = [t["name"] for t in tools
           if not set(t["inputSchema"]["required"]) <= set(t["inputSchema"]["properties"])]
    checks.append(_check("S8", "派生出的 MCP / DSH 工具定义自洽（名字唯一、必填项在属性里）",
                         len(names) == len(set(names)) and not bad
                         and len(dsh) == len(tools) == len(declared),
                         "工具数 %d（声明 %d）｜重名或坏必填：%s"
                         % (len(names), len(declared), (bad or "无"))))

    # 示例必须真能解析（防止文档里写了不存在的参数/写法）
    broken = []
    for mod in schema.SCHEMA["modules"]:
        for cmd in mod["commands"]:
            for ex in cmd["examples"]:
                argv = shlex.split(ex)
                if argv and argv[0] == schema.SCHEMA["cli"]:
                    argv = argv[1:]
                try:
                    parser.parse_known_args(argv)
                except SystemExit:
                    broken.append(ex)
    checks.append(_check("S9", "清单里的示例命令都能被本 CLI 解析（示例不骗人）", not broken,
                         "解析失败：%s" % (broken or "无")))

    checks.append(_permission_matrix_check())

    ok = all(c["ok"] for c in checks)
    failed = [c["id"] for c in checks if not c["ok"]]
    return {
        "ok": ok,
        "summary": "全部通过（%d/%d）" % (len(checks), len(checks)) if ok
                   else "未通过：%s" % "、".join(failed),
        "source": schema.SCHEMA["generatedBy"],
        "commandCount": len(declared),
        "moduleCount": len(mods_declared),
        "checks": checks,
    }
