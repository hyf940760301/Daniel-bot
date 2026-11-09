# -*- coding: utf-8 -*-
"""playbook 模块：工序契约（列清单／看一份／校验／跑一份／引擎自证）。

命令与参数全部在 `../schema.py` 里声明（单一真源），本文件只做实现。
`run` 为什么按"写操作"登记：契约**可能含写步骤**（写步骤要走
`dry-run → --confirm → 执行 → 回读校验` 三段门禁），所以它必须带 `--confirm`/`--dry-run`
两个开关（`schema --check` 的 S6 判据要求写命令带门禁）；但**读链契约不需要 --confirm**，
门禁判定在执行器内部按"契约里有没有写步骤"决定（见 `../playbook/executor.py`）。
"""
import json
import os

from ..exits import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE
from ..playbook import executor, loader, model
from ..playbook import deliverable
from ..playbook import selfcheck as engine_selfcheck
from ..playbook import validate as contract_validate
from ..runtime import CliError

BOARD = "playbook"


def _write_out(path, payload):
    path = os.path.abspath(os.path.expanduser(str(path)))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    return path


def _kv(pairs, flag, as_int=False):
    """把 `--limit 行数上限=20` 这样的「键=值」收成字典（写错即报用户错误）。"""
    out = {}
    for p in pairs or []:
        if "=" not in str(p):
            raise CliError("%s 要写成「键=值」（当前 %r）" % (flag, p), code=EXIT_USAGE,
                           hint="例：%s 行数上限=8" % flag)
        k, v = str(p).split("=", 1)
        k, v = k.strip(), v.strip()
        if not k:
            raise CliError("%s 的键不能为空（当前 %r）" % (flag, p), code=EXIT_USAGE)
        if as_int:
            try:
                v = int(v)
            except ValueError:
                raise CliError("%s %s 需要整数（当前 %r）" % (flag, k, v), code=EXIT_USAGE)
        out[k] = v
    return out


def cmd_list(ctx):
    root = loader.contracts_dir()
    rows = loader.list_contracts(root)
    bad = [r for r in rows if r["错误"]]
    for r in bad:
        ctx.warn("契约读不出来：%s（%s）" % (r["相对路径"], r["错误"]))
    ctx.emit(data={
        "契约目录": os.path.abspath(root),
        "契约数": len(rows),
        "工程契约": len([r for r in rows if not r["示例"]]),
        "示例契约": len([r for r in rows if r["示例"]]),
        "契约": rows,
        "说明": "契约是 JSON 声明式文本：判据与门禁都是可执行断言，不是文档。"
                "示例与退化样本放在 `_examples/`（退化样本用来证明门禁真的会拦）。",
    })
    return EXIT_OK


def cmd_show(ctx):
    ref = ctx.require("name", metavar="契约（写 `daniel playbook show <契约>` 或 `--name 契约`）")
    contract, path, aliases = loader.load(ref)
    verdict = contract_validate.validate_contract(contract, path)
    ctx.emit(data={"契约": contract, "路径": os.path.abspath(path),
                   "字段别名归一": aliases,
                   "契约字段": list(model.EIGHT_FIELDS),
                   "校验": {"通过": verdict["通过"], "问题数": verdict["问题数"],
                            "问题": verdict["问题"]}})
    return EXIT_OK


def cmd_validate(ctx):
    root = loader.contracts_dir()
    ref = ctx.get("name")
    paths = [loader.resolve(ref, root)] if ref else loader.contract_files(root)
    results = []
    for path in paths:
        rel = os.path.relpath(path, root)
        try:
            contract, _aliases = model.normalize(loader.read_json(path))
        except CliError as e:
            results.append({"契约": rel, "路径": os.path.abspath(path), "通过": False,
                            "问题数": 1, "问题": [e.message], "检查项": []})
            continue
        verdict = contract_validate.validate_contract(contract, path)
        results.append({"契约": verdict["契约"], "名称": verdict["名称"],
                        "路径": os.path.abspath(path), "通过": verdict["通过"],
                        "问题数": verdict["问题数"], "问题": verdict["问题"],
                        "检查项": [{"id": c["id"], "说明": c["说明"], "通过": c["通过"],
                                    "问题数": len(c["问题"])} for c in verdict["检查项"]]})
    ok = bool(results) and all(r["通过"] for r in results)
    data = {"契约目录": os.path.abspath(root), "校验数": len(results),
            "通过数": len([r for r in results if r["通过"]]),
            "结论": "全部通过（%d/%d）" % (len(results), len(results)) if ok
                    else "未通过：%s" % "；".join(r["契约"] for r in results if not r["通过"]),
            "明细": results}
    if ok:
        ctx.emit(data=data)
        return EXIT_OK
    ctx.warn("契约校验未通过：%s" % data["结论"])
    ctx.emit_raw(ok=False, exit_code=EXIT_USAGE, data=data)
    return EXIT_USAGE


def cmd_run(ctx):
    ref = ctx.require("name", metavar="契约（写 `daniel playbook run <契约>` 或 `--name 契约`）")
    root = loader.contracts_dir()
    contract, path, _aliases = loader.load(ref, root)
    verdict = contract_validate.validate_contract(contract, path)
    if not verdict["通过"]:
        ctx.warn("契约校验不通过，拒绝执行：%s" % (verdict["问题"] or ["未知问题"])[0])
        ctx.emit_raw(ok=False, exit_code=EXIT_USAGE,
                     data={"契约": verdict["契约"], "路径": os.path.abspath(path),
                           "校验": {"通过": False, "问题数": verdict["问题数"],
                                    "问题": verdict["问题"]}})
        return EXIT_USAGE

    full = bool(ctx.get("full"))
    write_steps = model.write_steps(contract)
    ctx.read_only = not write_steps            # 信封里的"是否只读"与契约实际一致
    opts = {
        "样本模式": not full,
        "全量": full,
        "确认": ctx.confirm,
        "干跑": ctx.dry_run,
        "留存": bool(ctx.get("keep")),         # `--keep`：保留本次自建的临时沙箱（不清理）
        "限额覆盖": _kv(ctx.get("limit"), "--limit", as_int=True),
        "输入覆盖": _kv(ctx.get("input"), "--input"),
        "契约目录": os.path.abspath(root),
    }
    report, code = executor.run_contract(contract, path, opts)
    out = ctx.get("out")
    if out:
        report["报告落点"] = _write_out(out, report)
    if code == EXIT_OK:
        ctx.emit(data=report)
        return EXIT_OK
    ctx.warn(report["结论"]["摘要"])
    ctx.emit_raw(ok=False, exit_code=code, data=report)
    return code


def cmd_deliver(ctx):
    """出件（TICKET-175）：跑一份**模板式**契约，把交付物落到本地目录。

    与 `run` 的分工：`run` 是跑工序（含出件，落点用模板默认值），`deliver` 是**只出件**并把
    落点交给调用方（`--out`）。两者共用同一个执行器与同一套五条出件自检 —— 出件前自动跑，
    不过则**非零退出且落点上一个文件都不产出**。

    为什么是读命令（不带 `--confirm`）：本命令不做任何 Daniel 写，也不执行契约里的写步骤
    （含写步骤的契约直接拒绝并指向 `playbook run --confirm`），写链的确认语义不在这里。
    """
    ref = ctx.require("name", metavar="契约（写 `daniel playbook deliver <契约>` 或 `--name 契约`）")
    root = loader.contracts_dir()
    contract, path, _aliases = loader.load(ref, root)
    verdict = contract_validate.validate_contract(contract, path)
    if not verdict["通过"]:
        ctx.warn("契约校验不通过，拒绝出件：%s" % (verdict["问题"] or ["未知问题"])[0])
        ctx.emit_raw(ok=False, exit_code=EXIT_USAGE,
                     data={"契约": verdict["契约"], "路径": os.path.abspath(path),
                           "校验": {"通过": False, "问题数": verdict["问题数"],
                                    "问题": verdict["问题"]}})
        return EXIT_USAGE
    if model.write_steps(contract):
        raise CliError("本契约含写步骤，`deliver` 只出件、不执行写步骤", code=EXIT_USAGE,
                       hint="含写步骤的契约请用 `daniel playbook run <契约> --confirm`；"
                            "出件命令专门用于读链契约的交付物落盘")
    spec = contract.get(model.F_DELIVERABLE) or {}
    if not deliverable.is_template(spec):
        raise CliError("本契约的 `%s` 没有声明 `%s`，不是模板式出件"
                       % (model.F_DELIVERABLE, model.D_FORMAT), code=EXIT_USAGE,
                       hint="模板式出件要在 `%s` 里声明 `%s`／`%s`／`%s`／`%s`（写法见 "
                            "PLAYBOOK.md §13）；遗留式契约用 `playbook run` 即可"
                            % (model.F_DELIVERABLE, model.D_FORMAT, model.D_SORT,
                               model.D_RECONCILE, model.D_SOURCES))
    opts = {
        "样本模式": True,
        "全量": False,
        "确认": False,
        "干跑": False,
        "留存": False,
        "限额覆盖": _kv(ctx.get("limit"), "--limit", as_int=True),
        "输入覆盖": _kv(ctx.get("input"), "--input"),
        "契约目录": os.path.abspath(root),
        # 落点由调用方决定：`--out DIR`；不给则走 daniel_paths 的默认值
        "交付落点": ctx.get("out"),
    }
    report, code = executor.run_contract(contract, path, opts)
    report["出件"] = {
        "落点": (report.get("交付件") or {}).get("落点"),
        "产物": (report.get("交付件") or {}).get("产物") or [],
        "sha256": (report.get("交付件") or {}).get("sha256"),
        "行数": (report.get("交付件") or {}).get("行数"),
        "格式": (report.get("交付件") or {}).get("格式"),
        "自检": (report.get("交付件") or {}).get("出件自检") or [],
        "违规": (report.get("交付件") or {}).get("违规") or [],
    }
    if code == EXIT_OK:
        ctx.emit(data=report)
        return EXIT_OK
    ctx.warn(report["结论"]["摘要"])
    ctx.emit_raw(ok=False, exit_code=code, data=report)
    return code


def cmd_selfcheck(ctx):
    result = engine_selfcheck.engine_selfcheck(require_network=bool(ctx.get("require_network")))
    # 可见性（TICKET-153 · 方案 A）：因「需要联网」被跳过的次数必须说出来 ——
    # 跳过不是通过，不许静默；JSON 信封里也会带这条 notes。
    skipped = result.get(model.SC_SKIP_COLUMN) or 0
    if skipped:
        who = "｜已开启强制口径：这种情况记失败" if result.get("强制联网") else ""
        ctx.note("%d 次运行因契约声明「%s」被跳过（跳过 ≠ 通过，未计入未通过项）：%s%s"
                 % (skipped, model.F_NEEDS_NETWORK,
                    "／".join(str(d.get("契约")) for d in result.get("明细") or []
                              if d.get("跳过") == model.SC_SKIP_ONLINE), who))
    elif result.get("强制联网"):
        ctx.note("已开启「需要联网」强制口径：联网探测失败会记失败，而不是跳过")
    if result["通过"]:
        ctx.emit(data=result)
        return EXIT_OK
    ctx.warn("契约引擎自证未通过：%s" % result["结论"])
    ctx.emit_raw(ok=False, exit_code=EXIT_INTERNAL, data=result)
    return EXIT_INTERNAL


HANDLERS = {
    "list": cmd_list,
    "show": cmd_show,
    "validate": cmd_validate,
    "deliver": cmd_deliver,
    "selfcheck": cmd_selfcheck,
}

WRITE_HANDLERS = {
    "run": cmd_run,
}
