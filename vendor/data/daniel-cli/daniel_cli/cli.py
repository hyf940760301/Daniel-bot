# -*- coding: utf-8 -*-
"""入口与分发：解析 → 定位实现 → 执行 → 退出码。

约定（写进 `--help`，也是本文件的行为）：
  - `daniel`（不带参数）打印总帮助，退出码 0；
  - `daniel <模块>`（不给子命令）打印该模块帮助到 **stderr**，退出码 2（缺参＝用户错误）；
  - `--help` / `--version` 走 argparse 原生行为（stdout，退出码 0）；
  - 结果 → stdout，进度/提示/错误说明 → stderr；`--json` 时 stdout 有且只有一个 JSON 文档。
"""
import sys
import traceback

from .exits import EXIT_INTERNAL, EXIT_NEEDS_CONFIRM, EXIT_OK, EXIT_USAGE
from .helpgen import build_parser, subparser_choices
from .runtime import CliError, Context, Emitter
from .schema import find_command, module_map
from .selftest import run_selftest

_KIND_BY_CODE = {EXIT_USAGE: "usage", EXIT_NEEDS_CONFIRM: "needs-confirm", EXIT_INTERNAL: "internal"}


def _module_help_to_stderr(parser, module_key):
    mod_parser = subparser_choices(parser).get(module_key)
    if mod_parser is not None:
        mod_parser.print_help(file=sys.stderr)


def _read_permission_block(emitter, module_key, command):
    """读链的权限轴：账号**看不到**的模块，读也不放行（用户 2026-10-14 口径）。

    三条自我约束：
      · 只对"有角色或权益要求"的模块做判定（对任何登录角色都可见的模块直接放行，
        不为了一次判定多打一次网络调用）；
      · 拿不到账号事实时**不拦读**（读链的真实门禁在服务端，CLI 不自造一道可能误伤的闸）；
      · 写链不受这条影响：写链一律要拿到快照才动手（见 `commands/_common.py`）。
    """
    from . import permissions
    rule = permissions.rule_for(module_key)
    if rule is None or (rule["roles"] is None and not rule["features"]):
        return None
    auth, _why = permissions.current_auth()
    if auth is None:
        return None
    v = permissions.verdict(module_key, permissions.READ, auth)
    if v["是否允许"]:
        return None
    emitter.error(permissions.denial_message(module_key, permissions.READ, v), EXIT_USAGE, "usage",
                  hint="跑 `daniel account capabilities` 看这个账号完整的能力矩阵",
                  module=module_key, command=command)
    return EXIT_USAGE


def _usage_failure(emitter, message, hint, module_key=None, command=None):
    """用户错误（缺参／类型非法／缺子命令）的**统一出口**。

    `--json` 时必须仍然给出**恰好一个** JSON 文档：否则机器消费者拿到的是空 stdout，
    只能靠退出码猜（TICKET-150 判据：stdout 有且只有一个 JSON 文档）。
    """
    if emitter.json_mode:
        emitter.error(message, EXIT_USAGE, "usage", hint=hint, module=module_key, command=command)
    else:
        print(message, file=sys.stderr)
        if hint:
            print("处理建议：" + hint, file=sys.stderr)
    return EXIT_USAGE


def _auth_gate(emitter, module_key, command):
    """**授权硬门禁**（TICKET-194）—— 模块分发层的**单一入口**前置检查。

    用户 2026-10-16 逐字要求：「daniel cli 和 mcp 的起点一定是授权和登陆 …… 否则是无法跳过
    授权进入到实际对 daniel 的模块调用中的」。这条要求在这里落地，且**只有这一处实现**：
    84 条命令共用同一份判据（白名单的单一真源是 `authgate.WHITELIST`）。

    未登录 ⇒ 退出码 2（用户错误）＋「请先登录」＋ 一行修法，**零真实数据、不静默降级**；
    `--json` 时给**结构化**未登录错误（`error.kind = "unauthenticated"` ＋ `error.data`），
    MCP 侧据此给出机器可读的「未登录」而不是空数据。

    为什么放在这里：`main()` 是唯一把「模块＋子命令」变成「处理函数」的地方；
    放在权限轴之前 —— 未登录时连"你有没有权限"都无从谈起。
    """
    from . import authgate
    verdict = authgate.gate(module_key, command)
    if verdict is None:
        return None
    if emitter.json_mode:
        emitter.error(verdict["message"], verdict["exitCode"], verdict["kind"],
                      hint=verdict["hint"], module=module_key, command=command,
                      data=authgate.gate_error_payload(verdict))
    else:
        emitter.error(verdict["message"], verdict["exitCode"], verdict["kind"],
                      hint=verdict["hint"], module=module_key, command=command)
    return verdict["exitCode"]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # 解析前先看有没有 `--json`：argparse 自己在缺参/类型非法时退出 2，那时还没有 args 可读。
    json_hint = "--json" in argv
    parser = build_parser()
    try:
        args = parser.parse_args(argv)                   # 缺参/类型非法 → argparse 自行退出 2
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else EXIT_USAGE
        if code != EXIT_OK and json_hint:
            # argparse 已经把人话（缺哪个参数／类型不对／用法）打到 stderr 了；
            # 这里只补机器可读面，不重复解释。
            Emitter(json_mode=True).error("参数不合法（详细说明见 stderr 的用法提示）", code,
                                          _KIND_BY_CODE.get(code, "usage"),
                                          hint="跑 `daniel <模块> <子命令> --help` 看该子命令的参数")
        return code
    emitter = Emitter(json_mode=bool(getattr(args, "json", False)))

    # 账号分区（TICKET-186 · A2）：把"当前账号的分区"注入本进程环境，**再做任何取数**。
    # 为什么只有这一处：`daniel_paths.home()` 的第一优先就是 `DANIEL_HOME`，注入之后既有仪器
    # （会话／缓存／调度／出件／审计）**零改动**即天然分区，子进程继承同一份环境。
    # 分区规则的单一真源是 `daniel_cli/accounts.py::partition_home()`，这里只是调用方。
    # 失败（例如状态文件不可写）**不拦命令**：落点退回根目录（＝出厂语义），stderr 给提示。
    try:
        from . import accounts as _accounts
        _acct = _accounts.apply_environment()
        if _acct.get("是否已分区") and not bool(getattr(args, "quiet", False)):
            emitter.progress("当前账号 %s ⇒ 数据落点 %s"
                             % (_acct.get("当前账号(掩码)"), _acct.get("生效落点")))
    except Exception as e:                                              # noqa: BLE001
        emitter.warn("账号分区没生效（本次按未指定账号的根目录落点继续）：%s" % str(e)[:160])

    if getattr(args, "self_test", False):
        # **模块自带自检优先**：`daniel keywords --self-test` 跑的是 keywords 模块自己的自检
        # （正控 ＋ 退化正控 ＋ 反例）；`daniel --self-test`（不给模块）仍是 CLI 总自检。
        # 哪个模块带自检，由 schema 的 `selfTest` 声明、实现文件给 `SELFTEST`；
        # 两者漂移时这里拿不到实现 → 退回总自检（不会静默假通过）。
        module_key = getattr(args, "_module", None)
        if module_key:
            from .commands import selftest_for
            fn = selftest_for(module_key)
            if fn is not None:
                return int(fn(emitter))
        return run_selftest(emitter)

    module_key = getattr(args, "_module", None)
    if not module_key:
        parser.print_help()
        return EXIT_OK

    command = getattr(args, "_command", None)
    try:
        mod = module_map()[module_key]
        if not command:
            for flag, target in sorted(mod["flagCommands"].items()):
                if getattr(args, flag.lstrip("-").replace("-", "_"), False):
                    command = target
                    break
        if not command:
            if module_key == "schema":
                command = "show"                         # `daniel schema --json` 直接出清单
            elif module_key == "install":
                # `daniel install`（**不带任何子命令**）本身就是那条"一条命令"的安装向导
                # （TICKET-195）。`--check`／`--upgrade` 两个快捷开关在上面已经映射成子命令，
                # 因此这里只在"什么开关都没给"时兜到 `run` —— 不猜用户想干别的。
                command = "run"
            else:
                _module_help_to_stderr(parser, module_key)
                return _usage_failure(emitter,
                                      "缺少子命令：请给出 `daniel %s <子命令>`" % module_key,
                                      "跑 `daniel %s --help` 看可用子命令" % module_key,
                                      module_key=module_key)

        cmd = find_command(module_key, command)
        if cmd is None:
            return _usage_failure(emitter, "未知子命令：%s %s" % (module_key, command),
                                  "跑 `daniel %s --help` 看可用子命令" % module_key,
                                  module_key=module_key, command=command)

        from .commands import handler_for
        handler = handler_for(module_key, command)
        if handler is None:
            emitter.error("命令未实现：%s %s（schema 里声明了，但没有注册实现）"
                          % (module_key, command), EXIT_INTERNAL, "internal",
                          hint="跑 `daniel schema --check` 看差异清单",
                          module=module_key, command=command)
            return EXIT_INTERNAL

        # 🔴 授权硬门禁（TICKET-194）：**唯一入口**的前置检查 —— 未登录时业务模块一律不放行。
        # 放在权限轴之前：未登录时"有没有权限"无从谈起；白名单命令（接入／自救／随包自检）
        # 一次会话文件都不读，因此它们的可用性不受登录态影响。
        blocked = _auth_gate(emitter, module_key, command)
        if blocked is not None:
            return blocked

        # 权限轴（读）：账号看不到的模块，读也不放行（写命令的权限闸在它自己的门禁链里）
        if not cmd["write"]:
            blocked = _read_permission_block(emitter, module_key, command)
            if blocked is not None:
                return blocked

        ctx = Context(args, emitter, module=module_key, command=command,
                      read_only=not cmd["write"])
        return int(handler(ctx))
    except CliError as e:
        emitter.error(e.message, e.code, _KIND_BY_CODE.get(e.code, "internal"), e.hint,
                      module=module_key, command=command)
        return e.code
    except SystemExit as e:
        # 既有能力（客户端/仪器）用 SystemExit 报"用户可见的错误"（品牌查不到、凭据缺失…）
        msg = e.code if isinstance(e.code, str) else "既有能力以 SystemExit(%r) 退出" % (e.code,)
        emitter.error(str(msg), EXIT_USAGE, "usage",
                      hint="对象可能不存在或多义：品牌名多义时请直接给品牌编号；"
                           "凭据问题先跑 `daniel account credentials`",
                      module=module_key, command=command)
        return EXIT_USAGE
    except KeyboardInterrupt:
        emitter.error("已中断（未完成）", EXIT_INTERNAL, "internal",
                      module=module_key, command=command)
        return EXIT_INTERNAL
    except Exception as e:                                              # noqa: BLE001
        if getattr(args, "verbose", False):
            traceback.print_exc()
        emitter.error("内部错误：%s: %s" % (type(e).__name__, e), EXIT_INTERNAL, "internal",
                      hint="加 --verbose 打印调用栈；或跑 `daniel --self-test` 定位",
                      module=module_key, command=command)
        return EXIT_INTERNAL


if __name__ == "__main__":
    import sys
    sys.exit(main())
