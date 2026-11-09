# -*- coding: utf-8 -*-
"""install 模块：**一条命令的安装向导** 的 CLI 接线层（TICKET-195）。

三条命令（后两条也能用**快捷开关**写法调用，两种写法等价）：

    run      `daniel install [--confirm]`              装 CLI ＋ 装能力束 ＋ 写宿主接入 ＋ 起登录
    check    `daniel install --check`                  装完自检：四步逐条给结论（只读，不写）
    upgrade  `daniel install --upgrade [--confirm]`    就地升级（改指到另一份包）＋ **重跑自检**

三条自我约束
------------
① **判据不在这里**：四步的实现与"包从哪来"都在 `daniel_cli/install/`（`source.py` ＋ `wizard.py`），
   本文件只做"参数 → 调用 → 输出"；
② **写链走既有门禁链**：`run`／`upgrade` 用 `commands/_common.gated_write`（权限轴 ＋ 确认轴 ＋
   干跑 ＋ 回读 ＋ 审计），**不自造第二条写链**；③ 宿主那一份**不重造**，直接调
   `daniel connect --host <宿主> --apply --confirm`；
③ **`--check` 只读**：不写任何文件；它跑的 `connect --doctor` 与 `auth status` 都是只读命令，
   **它也不会调起任何浏览器**。

🔴 **自动化不许弹窗（2026-10-16 事故后固化）**：`install` 是给人用的，人在真终端里跑时第 ④ 步
可以打开 Daniel 登录页；但**自检／验收／CI／Agent 调用一律不得产生"真人可见的副作用"**。
落地方式是**代码默认行为**（环境变量 `DANIEL_NO_OPEN=1`／显式 `--no-open`／非交互终端，三条任一
命中即不开），判据只有一处（`commands/mod_account.no_open_decision`）。
"""
from ..install import source as source_mod
from ..install import wizard
from ._common import STAGE_LIVE, gated_write


# ─────────────────────────── 参数 ───────────────────────────
def _plan_run(ctx, _client):
    """干跑与真执行共用的算账：四步**将要做什么**（只读，不写任何文件）。"""
    return wizard.wizard_plan(ctx)


def _run_run(ctx, _client, plan):
    """真执行四步：每一步都先判"现状是否已是目标"（幂等），写前落快照、写后回读对账。"""
    return wizard.wizard_run(ctx, plan)


def _plan_upgrade(ctx, _client):
    return wizard.upgrade_plan(ctx)


def _run_upgrade(ctx, _client, plan):
    out = wizard.upgrade_run(ctx, plan)
    return out


# ─────────────────────────── check（只读） ───────────────────────────
def cmd_check(ctx):
    """只读自检：① 装 CLI ② 能力束 ③ 接入（复用 `connect --doctor`）④ 登录态（`auth status` 三档）。"""
    report, code = wizard.check_all(ctx)
    data = dict(report)
    data["复核命令"] = ["daniel install --check", "daniel connect --doctor", "daniel auth status"]
    if report["通过"]:
        ctx.progress("四步全部通过：装好了，可以正常用")
    else:
        ctx.warn(report["结论"])
    ctx.emit_raw(ok=report["通过"], exit_code=code, data=data)
    return code


# ─────────────────────────── 写链 ───────────────────────────
def _dry_run_wins(ctx):
    """同时给了 `--dry-run` 与 `--confirm` 时**按干跑**走（与 `connect`／`pack` 同口径）。

    安装会改 PATH 与宿主配置 ⇒ 宁可不装，也不在用户没打算装的时候动手。
    """
    if ctx.dry_run and ctx.confirm:
        ctx.warn("同时给了 --dry-run 与 --confirm：按 --dry-run 处理，不写任何文件")
        try:
            setattr(ctx.args, "confirm", False)
        except Exception:                                              # noqa: BLE001
            pass
        ctx.confirm = False


def _gate(command):
    if command == "run":
        action = "装 Daniel CLI：入口进 PATH ＋ 8 束能力束软链 ＋ 宿主接入 ＋ 起登录（四步一条命令）"
        danger = ("会写三处本机内容：① `~/.local/bin/daniel` 一条软链 ＋ `~/.zshrc` 一行 PATH；"
                  "② 宿主技能目录下 8 条 `kol-*` 软链；③ 宿主配置里本产品那一条（经 connect，"
                  "幂等、写前落快照）。**不改任何 Daniel 数据、不触发采集、不要你的账号密码**")
    else:
        action = "就地把本机安装改指到另一份包，并**重跑自检**"
        danger = ("会改指入口软链与 8 束技能软链，并经 `connect` 刷新宿主配置里本产品那一条"
                  "（写前落快照、写后回读对账）；升级后自动跑一遍 `daniel install --check`")
    return gated_write("install", command, action, stage=STAGE_LIVE,
                       plan_fn=_plan_run if command == "run" else _plan_upgrade,
                       run_fn=_run_run if command == "run" else _run_upgrade,
                       danger=danger)


def _wrap(gate, command):
    """把门禁标记**原样挂到外层**（`schema --check` 的 S7 读的是注册表里那个函数对象）。"""

    def handler(ctx):
        _dry_run_wins(ctx)
        if not ctx.confirm:
            # 干跑：把"这一步到底会改哪些文件"先摆出来（与 connect／pack 同一体例）
            plan = _plan_run(ctx, None) if command == "run" else _plan_upgrade(ctx, None)
            for name, step in (plan.get("四步") or {}).items():
                ctx.progress("%s → %s" % (name, step["结论"]))
        return gate(ctx)

    handler.__name__ = "cmd_" + command
    handler.__doc__ = ("（%s）写操作门禁链：权限 → 确认 → 执行 → 快照与回读对账 → 审计留痕。"
                       % command)
    handler._danielWriteGate = getattr(gate, "_danielWriteGate", None)      # noqa: SLF001
    return handler


def _preflight(ctx):
    """真跑之前把"包够不够格装"先判一次（包不完整 ⇒ 当场拒绝，别只写一半）。"""
    return source_mod.resolve(ctx.get("from"))


# ─────────────────────────── 注册 ───────────────────────────
HANDLERS = {
    "check": cmd_check,
}

WRITE_HANDLERS = {
    "run": _wrap(_gate("run"), "run"),
    "upgrade": _wrap(_gate("upgrade"), "upgrade"),
}

__all__ = ["HANDLERS", "WRITE_HANDLERS", "cmd_check"]
