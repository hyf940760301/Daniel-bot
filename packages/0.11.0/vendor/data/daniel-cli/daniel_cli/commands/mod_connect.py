# -*- coding: utf-8 -*-
"""connect 模块：把「接入」做成 CLI 自带能力（TICKET-189）的 **CLI 接线层**。

五条命令（都能用**快捷开关**写法调用，两种写法等价）：

    list        `daniel connect --list`                  本机支持哪些宿主、各自接没接上（只读）
    print       `daniel connect --host cursor --print`   只打印该宿主该写的那一段（不改文件）
    apply       `daniel connect --host cursor --apply --confirm`    自己算路径 ＋ 幂等合并写入
    uninstall   `daniel connect --host cursor --uninstall --confirm`  只删自己那一条
    doctor      `daniel connect --doctor`                端到端断言：这套接入到底通不通（只读）

三条自我约束
------------
① **判据不在这里**：路径现算／片段生成／幂等合并／快照／回读对账全在 `daniel_cli/connect/`，
   本文件只做"参数 → 调用 → 输出"；
② **写链走既有门禁链**：`apply`／`uninstall` 用 `commands/_common.gated_write`（权限轴 ＋ 确认轴
   ＋ 干跑 ＋ 回读 ＋ 审计），**不自造第二条写链**。挂上它之后，干跑必然先给出逐行 diff，
   而 `--print` 与 `--apply` 的内容必然同源（同一个生成器）；
③ **一次只给一个开关**：同时给两个快捷开关（例如 `--apply` 与 `--uninstall`）当场拒绝，
   不猜用户想干哪一件事。
"""
import os

from ..connect import doctor as doctor_mod
from ..connect import hosts
from ..exits import EXIT_OK, EXIT_USAGE
from ..runtime import CliError
from ._common import STAGE_LIVE, gated_write

#: 快捷开关（与 schema 的 `flagCommands` 同源；这里只用于"一次只给一个"的自查）
FLAG_NAMES = ("list", "print", "apply", "uninstall", "doctor")


def _check_single_flag(ctx):
    """快捷开关写法下，一次只许给一个开关（避免"以为在卸载、其实在写入"）。"""
    given = sorted(k for k in FLAG_NAMES if bool(ctx.get(k)))
    if len(given) > 1:
        raise CliError("一次只给一个开关：你给了 %s" % "、".join("--" + g for g in given),
                       code=EXIT_USAGE,
                       hint="例如 `daniel connect --host cursor --apply --confirm`；"
                            "本命令不猜你想干哪一件事")


def _require_host(ctx):
    key = ctx.get("host")
    if not key:
        raise CliError("缺少宿主：请给 `--host <宿主>`（可选：%s）" % "／".join(hosts.SUPPORTED),
                       code=EXIT_USAGE,
                       hint="跑 `daniel connect --list` 看本机各宿主的检测结果")
    return hosts.host_meta(key)["key"]


def _host_note(key):
    """本机对该宿主的检测结论（"未检测到"就如实说，不假装）。"""
    path = hosts.config_path(key)
    if not hosts.host_detected(key):
        return "未检测到（%s 不存在）" % os.path.dirname(path)
    return "检测到（%s 存在）" % os.path.dirname(path)


def _state_text(ctx, key):
    """一个宿主的接入状态（**只读**）：已接入／未接入／有重复／判不出来，都写明原因。"""
    st = hosts.read_state(key)
    if not st.get("宿主是否检测到"):
        return st, "未接入（未检测到宿主：%s 不存在）" % os.path.dirname(st["配置文件"])
    if not st.get("存在"):
        return st, "未接入（配置文件不存在：%s）" % st["配置文件"]
    if st.get("解析错误"):
        return st, "判不出来（%s）" % st["解析错误"]
    if st.get("条目数") == 0:
        return st, "未接入（配置文件里没有本产品条目）"
    if st.get("条目数") > 1:
        return st, "接入有重复（本产品条目 %d 条，应当恰好 1 条）" % st["条目数"]
    diffs = doctor_mod.entry_diffs(key, st)                     # 与 doctor 同一判据，不写第二份
    if not diffs:
        return st, "已接入（指向当前包）"
    return st, "已接入但%s：%s" % ("指向旧副本" if any("服务入口" in d for d in diffs)
                                  else "与本机现算不一致", "；".join(diffs))


# ─────────────────────────── list ───────────────────────────
def cmd_list(ctx):
    """看本机支持哪些宿主、各自接没接上（含路径是否指向当前包）—— 只读。"""
    _check_single_flag(ctx)
    keys = ([hosts.host_meta(ctx.get("host"))["key"]] if ctx.get("host")
            else hosts.host_keys())
    rows = []
    for key in keys:
        st, state = _state_text(ctx, key)
        rows.append({
            "宿主": "%s（%s）" % (key, hosts.host_meta(key)["title"]),
            "结论": state,
            "配置文件": st["配置文件"],
            "宿主检测": _host_note(key),
            "本产品条目数": st.get("条目数"),
            "其它 server": "、".join(st.get("其它成员") or []) or "无",
        })
    ctx.emit(data={
        "现算路径": hosts.paths(),
        "宿主": rows,
        "尚未适配的宿主（能力不受影响，只缺该宿主的配置片段生成器）": [{"宿主": k, "说明": why} for k, why in hosts.UNSUPPORTED],
        "说明": "接入只有一条命令：`daniel connect --host <宿主> --apply --confirm`"
                "（换机器、换宿主都是同一条）。判断「通不通」用 `daniel connect --doctor`。",
        "复核命令": ["daniel connect --host cursor --print", "daniel connect --doctor"],
    })
    return EXIT_OK


# ─────────────────────────── print ───────────────────────────
def cmd_print(ctx):
    """只打印该宿主应写入的那一段（**不改任何文件**），供审阅与手工粘贴。"""
    _check_single_flag(ctx)
    key = _require_host(ctx)
    text = hosts.snippet_text(key)
    if ctx.json_mode:
        ctx.emit(data={
            "宿主": key, "名称": hosts.host_meta(key)["title"],
            "配置文件": hosts.config_path(key), "片段": text,
            "片段sha256": hosts.snippet_sha256(key), "现算路径": hosts.paths(),
            "说明": "这就是 `--apply` 会写进去的那一段（同一个生成器）；"
                    "`--apply` 只把它合并进配置文件，不动其它 server／其它表。",
        })
        return EXIT_OK
    ctx.emit(text=text)                       # 纯文本：可以直接重定向成文件或粘进配置
    ctx.progress("片段 sha256：%s" % hosts.snippet_sha256(key))
    return EXIT_OK


# ─────────────────────────── apply / uninstall ───────────────────────────
def _plan_common(ctx, mode):
    """算清"将发生什么 ＋ 影响范围 ＋ 逐行 diff"（**只读**，干跑与真执行共用这一份）。"""
    key = _require_host(ctx)
    path = hosts.config_path(key)
    raw = hosts.read_config_raw(key)
    if mode == "apply":
        merged, proof = hosts.merge(key, raw)
    else:
        if raw is None:
            raise CliError("配置文件不存在，没有可卸载的东西：%s" % path, code=EXIT_USAGE,
                           hint="`daniel connect --list` 看各宿主当前的接入状态")
        merged, proof = hosts.uninstall(key, raw)
    diff = hosts.diff_lines(raw, merged)
    return key, path, raw, merged, {
        "targetName": "%s 的宿主配置" % hosts.host_meta(key)["title"],
        "宿主": key,
        "配置文件": path,
        "影响范围": ("只在本产品那一条（%s）上做「%s」；其它 server／其它表与注释逐字节不动；"
                     "写前落快照，可用 `--uninstall` 还原" % (hosts.ENTRY_NAME, proof["操作"])),
        "改前sha256": hosts.sha256_text(raw) if raw is not None else None,
        "改后sha256": hosts.sha256_text(merged),
        "无需改动": raw is not None and merged == raw,
        "逐行diff": "\n".join(diff) if diff else "（无差异：改前改后逐字节相同 ⇒ 已接入且正确）",
        "对账": proof,
        "现算路径": hosts.paths(),
        "将写入的片段": hosts.snippet_text(key) if mode == "apply" else None,
        "print与apply一致": (hosts.print_apply_consistency(key, merged) if mode == "apply"
                             else "（卸载不涉及片段生成）"),
    }


def _run_common(ctx, mode, key, path, planned_sha):
    """真执行：**重新读原文 → 快照 → 写 → 回读对账**。内容已一致时只回读，不改文件（幂等）。

    为什么重新读一遍：`plan` 是干跑那一刻算的，确认与执行之间文件可能被人（或另一个宿主）改过
    —— 拿旧结果去盖新文件就是丢数据。这里以"执行这一刻的原文"为准重算，并如实标注计划是否已过期。
    """
    raw = hosts.read_config_raw(key)
    if mode == "apply":
        merged, _proof = hosts.merge(key, raw)
    else:
        if raw is None:
            raise CliError("配置文件已不存在，卸载无从谈起：%s" % path, code=EXIT_USAGE)
        merged, _proof = hosts.uninstall(key, raw)
    stale_plan = bool(planned_sha) and hosts.sha256_text(merged) != planned_sha
    if raw is not None and merged == raw:
        rb = hosts.readback(key, hosts.paths(), mode=mode)
        return {"mutation": {"配置文件": path, "改动": "无（内容已一致，未改动文件）",
                             "计划已过期": stale_plan},
                "readback": rb, "rolledBack": None,
                "rollbackNote": "本次没有改动任何文件"}
    snap = (hosts.write_snapshot(path, raw) if raw is not None
            else {"路径": None, "sha256": None, "说明": "文件此前不存在，没有可留的原文"})
    written = hosts.write_text(path, merged)
    rb = hosts.readback(key, hosts.paths(), mode=mode)
    on_disk = hosts.read_config_raw(key)
    rb = dict(rb)
    rb["detail"] = dict(rb.get("detail") or {})
    rb["detail"]["落盘内容与本次计划一致"] = {
        "通过": (on_disk == merged) and not stale_plan,
        "写后sha256": hosts.sha256_text(on_disk or "")}
    if on_disk != merged:
        rb["verified"] = False
        rb["reason"] = "落盘内容与计划不一致（写后回读对账不过）"
    return {"mutation": {"配置文件": path,
                         "写前sha256": hosts.sha256_text(raw) if raw is not None else None,
                         "写后sha256": written["sha256"], "字节数": written["字节数"],
                         "此前是否存在": written["此前是否存在"], "快照": snap.get("路径"),
                         "计划已过期": stale_plan},
            "readback": rb, "rolledBack": None,
            "rollbackNote": ("原文快照：%s（要还原就把它复制回 %s，或跑 "
                             "`daniel connect --host %s --uninstall --confirm`）"
                             % (snap.get("路径"), path, key)) if snap.get("路径")
                            else "本次是新建文件；`--uninstall` 只删本产品那一条"}


def _dry_run_wins(ctx):
    """同时给了 `--dry-run` 与 `--confirm` 时，**按 `--dry-run` 处理**（宁可不写）。

    既有写链的门禁是确认轴（`--confirm`），`--dry-run` 只是把默认行为显式写出来；
    两个都给时按更保守的那个走 —— 对"改用户宿主配置"这种动作，少写一次没有代价。
    """
    if ctx.dry_run and ctx.confirm:
        ctx.warn("同时给了 --dry-run 与 --confirm：按 --dry-run 处理，不写任何文件")
        try:
            setattr(ctx.args, "confirm", False)
        except Exception:                                          # noqa: BLE001
            pass
        ctx.confirm = False


def _plan_fn(ctx, mode):
    """门禁链的"计划轴"：算出这次将要做什么（`_plan_common` 的唯一入口）。"""
    return _plan_common(ctx, mode)[4]


def _run_fn(ctx, mode, plan):
    """门禁链的"执行轴"：真写 ＋ 快照 ＋ 回读对账。"""
    key = _require_host(ctx)
    return _run_common(ctx, mode, key, hosts.config_path(key),
                       (plan or {}).get("改后sha256"))


def _gate(command, mode):
    """把一条写命令装成既有门禁链的处理器（**在模块加载时装一次**，标记才挂在同一个函数对象上）。"""
    if mode == "apply":
        action = "把 Daniel 接入宿主（只动本产品那一条）"
        danger = ("改写你本机的宿主配置文件（只在本产品那一条上动；写前落快照、"
                  "写后回读对账，可 `--uninstall` 还原）")
    else:
        action = "从宿主配置里删掉本产品那一条（其它 server／表／注释不动）"
        danger = "改写你本机的宿主配置文件（只删本产品那一条；写前落快照）"
    return gated_write("connect", command, action, stage=STAGE_LIVE,
                       plan_fn=lambda ctx, _client: _plan_fn(ctx, mode),
                       run_fn=lambda ctx, _client, plan: _run_fn(ctx, mode, plan),
                       danger=danger)


def _wrap(gate, command):
    """在门禁链外面套一层"开关自查 ＋ 干跑优先"，并把门禁标记**原样挂到外层**。

    为什么必须把标记挂到外层：`daniel schema --check` 的 S7 读的是**注册表里那个函数对象**的
    `_danielWriteGate`；如果只挂在里层，门禁就变成"名义上装了、实际查不到"（这正是 S7 要防的事）。
    """

    def handler(ctx):
        _check_single_flag(ctx)
        _dry_run_wins(ctx)
        return gate(ctx)

    handler.__name__ = "cmd_" + command
    handler.__doc__ = ("（%s）写操作门禁链：权限 → 确认 → 执行 → 快照与回读对账 → 审计留痕。"
                       % command)
    handler._danielWriteGate = getattr(gate, "_danielWriteGate", None)      # noqa: SLF001
    return handler


# ─────────────────────────── doctor ───────────────────────────
def cmd_doctor(ctx):
    """端到端断言：包完整性 → server 起得来 → 工具数 → 只读取数 → 每个宿主的接入状态。"""
    _check_single_flag(ctx)
    host = ctx.get("host")
    if host:
        hosts.host_meta(host)                                      # 提前校验（用户错误 ⇒ 退出码 2）
    result = doctor_mod.run_doctor(host=host, progress=ctx.progress)
    code = doctor_mod.exit_code_for(result)
    data = dict(result)
    data["复核命令"] = ["daniel connect --doctor", "daniel connect --list"]
    ctx.emit_raw(ok=result["通过"], exit_code=code, data=data)
    return code


# ─────────────────────────── 注册 ───────────────────────────
HANDLERS = {
    "list": cmd_list,
    "print": cmd_print,
    "doctor": cmd_doctor,
}

WRITE_HANDLERS = {
    "apply": _wrap(_gate("apply", "apply"), "apply"),
    "uninstall": _wrap(_gate("uninstall", "uninstall"), "uninstall"),
}
