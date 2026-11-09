# -*- coding: utf-8 -*-
"""pack 模块：出包（`--out`）与只读自检（`--check`）的 **CLI 接线层**（TICKET-193）。

两条命令（都能用**快捷开关**写法调用，两种写法等价）：

    out     `daniel pack --out <目录> [--confirm]`   出一份可交付的能力包（默认干跑）
    check   `daniel pack --check <包目录>`           只读自检：五条断言逐条给结论（不产出）

三条自我约束
------------
① **判据不在这里**：源清单规则在 `daniel_cli/pack/spec.py`、出包在 `builder.py`、
   干净度扫描在 `scanner.py`、隔离复现在 `isolation.py`、五条断言编排在 `verify.py`；
   本文件只做"参数 → 调用 → 输出"。
② **写链走既有门禁链**：`out` 用 `commands/_common.gated_write`（权限轴 ＋ 确认轴 ＋ 干跑 ＋
   回读 ＋ 审计），**不自造第二条写链**。回读对账是**真的重新读盘**：包内文件集合、逐文件
   sha256、点名排除命中数、结构断言、引用闭合断言，五条全过才算写成功。
③ **`--check` 只读**：不写任何文件、不产出任何东西；它跑的隔离复现是在**系统临时目录**里做的，
   用完即删（`--keep` 只用于排查）。
"""
import os

from ..pack import builder, verify
from ..runtime import CliError
from ._common import STAGE_LIVE, gated_write


# ─────────────────────────── 参数 ───────────────────────────
def _out_dir(ctx):
    return ctx.require("out_dir", metavar="目录（`daniel pack --out <目录>`）")


def _source_or_none(ctx, required=False):
    """源目录：`--source` 优先；否则从本 CLI 的包根往上推。

    `required=True`（出包）时推不出来就报用户错误；`required=False`（自检）时返回 None，
    由 `verify` 把"与源的差集"如实记成**未取得**（不按通过处理，也不编一个源出来）。
    """
    explicit = ctx.get("source")
    if explicit:
        return builder.source_root(explicit)
    try:
        return builder.source_root(None)
    except CliError:
        if required:
            raise
        return None


def _creds_from_env():
    """`--check` 的隔离复现要真取一次数时用的凭据：**只从环境变量取**（产品文档里的来源②）。

    没给就返回 None ⇒ 第 ② 条断言如实记「未取得（未提供凭据）」。**不回显、不落盘**。
    """
    email = os.environ.get("DANIEL_EMAIL")
    password = os.environ.get("DANIEL_PASSWORD")
    return (email, password) if (email and password) else None


# ─────────────────────────── out（写） ───────────────────────────
def _plan_out(ctx, _client):
    """干跑与真执行共用的算账：这次会包含什么、排除什么、包落在哪。"""
    root = _source_or_none(ctx, required=True)
    out_dir = _out_dir(ctx)
    pack_root = builder.pack_root_of(out_dir)
    builder.assert_outside_source(pack_root, root)
    p = builder.plan(root)
    counts = p["计数"]
    return {
        "targetName": pack_root,
        "impact": ("在 %s 下写出一份完整拷贝：包含 %d 个文件／%d 字节，排除 %d 个文件；"
                   "包内不含任何凭据与你的数据（出包时按规则逐项排除，并对结果做凭据与机器特征扫描）"
                   % (pack_root, counts["包含文件数"], counts["包含字节"], counts["排除文件数"])),
        "包根": pack_root,
        "出包清单": builder.receipt_path_of(out_dir),
        "源目录": root,
        "候选面": p["候选面"],
        "计数": counts,
        "规则表": p["规则表"],
        "排除样例（前 10 项；逐项清单见出包清单）": p["排除"][:10],
        "点名排除逐项账": builder.named_ledger(root),
        "排除清单说明": ("逐项排除清单（%d 项，每项带规则编号与理由）落在包目录**之外**的 "
                         "`%s`：包内必须严格满足「包内文件 ⊆ 源目录」，故清单不放进包里。"
                         % (len(p["排除"]), builder.receipt_path_of(out_dir))),
        "未命中任何规则": p["未命中任何规则"],
        "复核命令": ["daniel pack --check %s" % pack_root],
    }


def _run_out(ctx, _client, plan):
    """真出包 → **重新读盘**做回读对账（五条）。"""
    root = _source_or_none(ctx, required=True)
    out_dir = _out_dir(ctx)
    receipt, pack_root = builder.execute(root, out_dir)

    want = {r["文件"]: r for r in receipt["包含"]}
    got = builder.walk_pack(pack_root)
    bad_hash = [rel for rel, row in want.items()
                if os.path.isfile(os.path.join(pack_root, rel))
                and builder._sha256(os.path.join(pack_root, rel)) != row["sha256"]]  # noqa: SLF001
    named = builder.scan_named(pack_root)
    st = verify.structure(pack_root)
    rc = verify.static_reference_closure(pack_root, root)
    checks = [
        {"项": "包内文件集合与出包清单逐项相等", "通过": set(got) == set(want),
         "实际": "包内 %d 项／清单 %d 项" % (len(got), len(want))},
        {"项": "逐文件 sha256 与出包时一致", "通过": not bad_hash,
         "实际": "不符 %d 项" % len(bad_hash)},
        {"项": "点名排除（legacy 凭据／会话／台账）0 命中", "通过": not named,
         "实际": "命中 %d 项" % len(named)},
        {"项": "A1 结构完整", "通过": st["通过"], "实际": st["证据"]},
        {"项": "A2 引用闭合", "通过": rc["通过"], "实际": rc["证据"]},
    ]
    bad = [c["项"] for c in checks if not c["通过"]]
    return {
        "mutation": {"包根": pack_root, "包含文件数": len(got),
                     "包含字节": sum(os.path.getsize(os.path.join(pack_root, r)) for r in got),
                     "排除文件数": receipt["计数"]["排除文件数"], "出包清单": builder.receipt_path_of(out_dir)},
        "readback": {"verified": not bad, "detail": {"回读逐项": checks},
                     "reason": None if not bad else "回读对账未通过：" + "；".join(bad)},
        "rolledBack": None,
        "rollbackNote": ("要撤掉本次出的包：直接删掉目录 %s（出包清单 %s 是它的收据，一并删即可）"
                         % (pack_root, builder.receipt_path_of(out_dir))),
    }


# ─────────────────────────── check（只读） ───────────────────────────
def cmd_check(ctx):
    """只读自检：A1 结构 → A2 引用闭合 → A3 干净 → A4 差集对账 → A5 隔离复现。"""
    pack_root = ctx.require("pack_dir", metavar="包目录（`daniel pack --check <包目录>`）")
    pack_root = os.path.abspath(os.path.expanduser(pack_root))
    out_dir = os.path.dirname(pack_root)
    source = _source_or_none(ctx, required=False)
    if source is not None and os.path.realpath(source) == os.path.realpath(pack_root):
        ctx.warn("源目录就是包自身（%s）⇒ 与源的差集无从复算，本项按出包清单复算并如实标注" % source)
        source = None
    host = ctx.get("host")
    creds = _creds_from_env()
    if creds is None:
        ctx.warn("环境里没有 DANIEL_EMAIL／DANIEL_PASSWORD ⇒ 隔离复现里「包内接入可用」这一条"
                 "按「未取得」登记（不注入任何凭据、不编造绿灯）")
    result = verify.run_check(pack_root, source_root=source, out_dir=out_dir, host=host,
                              creds=creds, keep=bool(ctx.get("keep")),
                              skip_isolation=bool(ctx.get("fast")))
    code = verify.exit_code_for(result)
    data = dict(result)
    data["复核命令"] = [
        "daniel pack --check %s" % pack_root,
        "daniel pack --out <目录> --confirm   # 重新出一份再自检",
    ]
    if result.get("通过"):
        ctx.progress("五条断言全部通过（包内文件数 %d，总字节 %d）"
                     % (result["计数"]["包内文件数"], result["计数"]["包内总字节"]))
    ctx.emit_raw(ok=result["通过"], exit_code=code, data=data)
    return code


# ─────────────────────────── 注册 ───────────────────────────
HANDLERS = {
    "check": cmd_check,
}


def _gate():
    return gated_write(
        "pack", "out",
        "出一份可交付的能力包（只复制到指定目录，不碰 Daniel 数据）",
        stage=STAGE_LIVE,
        plan_fn=_plan_out,
        run_fn=_run_out,
        danger=("会在 <目录>/daniel-bot 写入一份完整拷贝（实测 163 个文件／约 4.1 MB）；"
                "包目录必须为空，且不得位于工作区之内（本命令会拒绝在工作区里出包）"))


def _wrap(gate):
    """把门禁标记**原样挂到外层**（`schema --check` 的 S7 读的是注册表里那个函数对象）。

    另加一条与 `connect` 同口径的保守处置：同时给了 `--dry-run` 与 `--confirm` 时**按干跑**走
    —— 出包不是破坏性动作，但"少写一次没有代价"这条纪律在这里同样成立。
    """

    def handler(ctx):
        if ctx.dry_run and ctx.confirm:
            ctx.warn("同时给了 --dry-run 与 --confirm：按 --dry-run 处理，不写出任何文件")
            try:
                setattr(ctx.args, "confirm", False)
            except Exception:                                              # noqa: BLE001
                pass
            ctx.confirm = False
        return gate(ctx)

    handler.__name__ = "cmd_out"
    handler.__doc__ = "（out）写操作门禁链：权限 → 确认 → 执行 → 快照与回读对账 → 审计留痕。"
    handler._danielWriteGate = getattr(gate, "_danielWriteGate", None)      # noqa: SLF001
    return handler


WRITE_HANDLERS = {
    "out": _wrap(_gate()),
}
