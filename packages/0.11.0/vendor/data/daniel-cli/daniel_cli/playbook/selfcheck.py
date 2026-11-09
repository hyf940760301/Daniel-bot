# -*- coding: utf-8 -*-
"""引擎自证（TICKET-146 · 任务内容 4「自检引擎」的引擎侧）。

契约自己带 `自检` 项（跑一次契约就出报告）；本模块管的是**引擎自己**：
把契约目录里每一份契约按它**声明的期望**（`期望.默认` / `期望.带确认`）各跑一遍，
核对「实际结果／退出码」是否与声明一致 —— 于是**退化样本也能自证**：
"这份契约必须被门禁拦下"这句话是**跑出来的**，不是文档里写的。

三条不变量（每次运行都核）：

  ① 计数自洽：声明项数 ＝ 实跑项数 ＝ 通过＋失败＋跳过（五组通用，对齐 CLS-67）；
  ② 读链零写：不含写步骤的契约，写动作台账必须为空；
  ③ 明细齐备：报告里每组的明细条数 ＝ 该组声明项数。

运行路径（P0-2 修正）：契约声明了哪几条就跑哪几条 —— `期望.默认`（什么都不加）、
`期望.干跑`（`--dry-run`）、`期望.带确认`（`--confirm`）；含写步骤的契约三条都必须声明。

联网契约（TICKET-153 · 方案 A）
------------------------------
真实数据契约（例如 `contracts/real-brands-inventory.json`）要点真实只读通路，因此**不再全离线可跑**。
契约顶层声明 `需要联网: true` 即表示"我这条自证要联网／要有效会话"：本模块会先做**一次**轻量可用性
探测（`account whoami`，一次运行只探一次），探不通就把这条运行记成 **`跳过（需要联网）`**，
**不计入未通过项**，并在汇总里单列一栏 `跳过（需联网）N` —— **跳过 ≠ 通过、跳过 ≠ 失败**，
与门禁的「跳过」同口径，且在结论文案与 stderr 提示里都显式说出来（不许静默）。

`--require-network`（或环境变量 `DANIEL_PLAYBOOK_REQUIRE_NETWORK=1`）把这种跳过改判为**失败**：
需要联网的 CI 用它防"永远跳过"变成逃逸通道。
"""
import os

from ..exits import EXIT_INTERNAL, EXIT_OK
from ..runtime import CliError
from . import assertions, executor, loader, model, validate


def _contract_title(contract, path, root):
    rel = os.path.relpath(path, root) if root else os.path.basename(path)
    return contract.get(model.F_ID) or rel, rel


# ─────────────────────── 联网契约的可用性探测（TICKET-153 · 方案 A） ───────────────────────
#: 探测用的只读命令：`account whoami` 是既有最小读链（一次 auth.me），
#: 「探得通」就等于"这次自证真能把需要联网的契约跑起来"。探测结果**一次运行只探一次**（缓存）。
_PROBE_ARGV = ("account", "whoami", "--json")
PROBE_TIMEOUT = 20


def network_probe(timeout=PROBE_TIMEOUT):
    """轻量可用性探测：返回 `(是否可用, 说明)`。只跑读命令，不做任何写。"""
    import subprocess
    import sys
    argv = [sys.executable, executor.CLI_PATH] + list(_PROBE_ARGV)
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "探测超时（%d 秒）：%s" % (timeout, " ".join(_PROBE_ARGV))
    except OSError as e:
        return False, "探测起不来：%s" % e
    if p.returncode == EXIT_OK:
        return True, "探测通过（%s 退出码 0）" % " ".join(_PROBE_ARGV)
    # 失败时优先取 JSON 信封里的 error.message（人话），拿不到才退回末行文本
    why = ""
    try:
        import json as _json
        doc = _json.loads(p.stdout)
        err = doc.get("error") if isinstance(doc, dict) else None
        if isinstance(err, dict) and err.get("message"):
            why = str(err["message"])
    except ValueError:
        why = ""
    if not why:
        tail = [x for x in ((p.stderr or "") + (p.stdout or "")).strip().splitlines()
                if x.strip() and x.strip() not in ("}", "{", "]", "[")]
        why = tail[-1][:200] if tail else "无输出"
    return False, "探测失败（%s 退出码 %d）：%s" % (" ".join(_PROBE_ARGV), p.returncode, why)


def _needs_network(contract):
    return bool((contract or {}).get(model.F_NEEDS_NETWORK))


def engine_selfcheck(root=None, only=None, require_network=False, probe=None):
    """逐契约自证：返回 `{通过, 契约目录, 契约数, 运行数, 实跑数, 跳过（需联网）,
    引擎断言自证, 明细[], 问题[]}`。

    `引擎断言自证`（TICKET-156）是**引擎自己**的正控／真阴性用例（纯函数，每次运行都跑）：
    契约再怎么写都盖不住"引擎把值取错了"，所以取值解析器自己的用例在这里兜底；
    任何一条不通过都会进 `问题`、让本次自证整体不通过。

    `require_network`（或用环境变量 `DANIEL_PLAYBOOK_REQUIRE_NETWORK=1`）＝把"因需联网而跳过"
    改判为**失败**：需要联网的 CI 用它防"永远跳过"。
    """
    root = root or loader.contracts_dir()
    require_network = bool(require_network) or _env_require_network()
    problems = []
    details = []
    skipped_online = 0
    probe_cache = {}

    def _probe():
        if "r" not in probe_cache:
            probe_cache["r"] = (probe or network_probe)()
        return probe_cache["r"]

    files = loader.contract_files(root)
    if only:
        files = [p for p in files if only in (os.path.basename(p), contract_id(p))]
    for path in files:
        contract, _aliases = model.normalize(loader.read_json(path))
        cid, rel = _contract_title(contract, path, root)
        verdict = validate.validate_contract(contract, path)
        if not verdict["通过"]:
            problems.append("%s：契约本身不合法（%s）" % (rel, "；".join(verdict["问题"][:3])))
            details.append({"契约": cid, "路径": rel, "阶段": "校验", "一致": False,
                            "问题": verdict["问题"][:5]})
            continue
        # 联网契约：先探一次可用性；探不通就不跑（免得把"没网"记成"契约坏了"）
        available, why = (True, "本契约未声明「%s」，无需探测" % model.F_NEEDS_NETWORK)
        if _needs_network(contract):
            available, why = _probe()
        if _needs_network(contract) and not available:
            state = model.SC_SKIP_ONLINE
            reason = ("本契约声明了「%s」，但本次联网探测没通过：%s"
                      % (model.F_NEEDS_NETWORK, why))
            if require_network:
                state = model.ST_FAIL
                reason += "｜已开启「需要联网」强制口径（--require-network／环境变量）："
                reason += "这里记**失败**而不是跳过"
                problems.append("%s：%s" % (rel, reason))
            else:
                skipped_online += 1
            details.append({"契约": cid, "路径": rel, "阶段": "联网探测",
                            "跳过": state, "一致": None, "跳过理由": reason,
                            "探测": {"可用": available, "说明": why}, "实际": None})
            continue
        expect = contract.get(model.F_EXPECT) or {}
        # 三条运行路径：默认（什么都不加）／干跑（--dry-run）／带确认（--confirm）。
        # 契约声明了哪条就跑哪条（含写步骤的契约三条都要声明，见 validate.check_expect）。
        for label, opts in ((model.E_DEFAULT, {}),
                            (model.E_DRY, {"干跑": True}),
                            (model.E_CONFIRMED, {"确认": True})):
            spec = expect.get(label)
            if not spec:
                continue
            row = {"契约": cid, "路径": rel, "路径类型": label,
                   "期望": {"结果": spec.get(model.E_RESULT), "退出码": spec.get(model.E_EXIT)},
                   "是否带确认": bool(opts.get("确认")), "是否干跑": bool(opts.get("干跑")),
                   "一致": False, "不变量": []}
            try:
                report, code = executor.run_contract(contract, path, opts)
            except CliError as e:
                row["实际"] = {"结果": "内部错误", "退出码": e.code, "说明": e.message}
                row["问题"] = [e.message]
                problems.append("%s（%s）：%s" % (rel, label, e.message))
                details.append(row)
                continue
            concl = report["结论"]
            row["实际"] = {"结果": concl["结果"], "退出码": code, "摘要": concl["摘要"]}
            row["一致"] = (code == spec.get(model.E_EXIT)
                         and concl["结果"] == spec.get(model.E_RESULT))
            if not row["一致"]:
                problems.append("%s（%s）：期望 %s/%s，实际 %s/%s"
                                % (rel, label, spec.get(model.E_RESULT), spec.get(model.E_EXIT),
                                   concl["结果"], code))
            total = report["计数"]["合计"]
            checks = [
                ("计数自洽", bool(total[model.C_SELF]),
                 "声明 %d＝实跑 %d＝通过 %d＋失败 %d＋跳过 %d"
                 % (total[model.C_DECLARED], total[model.C_RUN], total[model.C_PASS],
                    total[model.C_FAIL], total[model.C_SKIP])),
                ("读链零写", bool(model.write_steps(contract)) or not report["写动作台账"],
                 "写动作台账 %d 条" % len(report["写动作台账"])),
                ("明细齐备",
                 all(report[g]["实跑项数"] == report[g]["声明项数"]
                     for g in ("前置", "步骤", "判据", "门禁", "自检")),
                 "／".join("%s %d/%d" % (g, report[g]["实跑项数"], report[g]["声明项数"])
                          for g in ("前置", "步骤", "判据", "门禁", "自检"))),
            ]
            for name, ok, detail in checks:
                row["不变量"].append({"名称": name, "通过": bool(ok), "明细": detail})
                if not ok:
                    problems.append("%s（%s）：不变量「%s」不通过 —— %s" % (rel, label, name, detail))
            row["计数"] = {k: total[k] for k in (model.C_DECLARED, model.C_RUN, model.C_PASS,
                                                model.C_FAIL, model.C_SKIP, model.C_SELF)}
            row["写动作台账"] = len(report["写动作台账"])
            details.append(row)

    # 引擎级断言自证（TICKET-156）：契约再怎么写都盖不住"引擎自己取错值"——
    # 取值解析器自己的正控／真阴性用例每次自证都跑一遍（纯函数、不联网、不写任何东西）。
    try:
        engine_cases = assertions.assertion_selftest()
    except Exception as e:                       # 自证自己崩了也算不通过，不静默、不留空
        engine_cases = [{"用例": "引擎断言自证自身", "期望": "跑得起来", "通过": False,
                         "明细": "自证用例跑不起来：%s: %s" % (type(e).__name__, e)}]
    engine_bad = [c for c in engine_cases if not c["通过"]]
    for c in engine_bad:
        problems.append("引擎断言自证「%s」不通过：%s" % (c["用例"], c["明细"]))

    ok = not problems and bool(details)
    if not files:
        problems.append("契约目录里没有任何契约：%s" % root)
        ok = False
    ran = len(details) - skipped_online
    eng_note = "；引擎断言自证 %d 条用例全部通过（嵌套取值／真阴性／回归）" % len(engine_cases)
    # 结论文案必须把"跳过"单独说出来 —— 跳过不是通过（TICKET-153 · 方案 A 的可见性要求）
    if ok and skipped_online:
        concl = ("%d 份契约／%d 次运行全部与契约声明的期望一致；另有 %d 次因「%s」被跳过"
                 "（跳过 ≠ 通过）" % (len(files), ran, skipped_online, model.F_NEEDS_NETWORK) + eng_note)
    elif ok:
        concl = ("%d 份契约／%d 次运行全部与契约声明的期望一致" % (len(files), ran)) + eng_note
    else:
        concl = "有未通过项：%s" % "；".join(problems[:5])
        if skipped_online:
            concl += "（另有 %d 次因「%s」被跳过，未计入未通过项）" % (skipped_online,
                                                              model.F_NEEDS_NETWORK)
    return {
        "通过": ok,
        "契约目录": os.path.abspath(root),
        "契约数": len(files),
        "运行数": len(details),
        "实跑数": ran,
        model.SC_SKIP_COLUMN: skipped_online,
        "强制联网": bool(require_network),
        "引擎断言自证": {"用例数": len(engine_cases),
                         "通过数": len(engine_cases) - len(engine_bad),
                         "明细": engine_cases},
        "不通过数": len(problems),
        "明细": details,
        "问题": problems,
        "结论": concl,
    }


def _env_require_network():
    """环境变量开关（给不便改命令行的 CI 用）；与 `--require-network` 同义。"""
    return os.environ.get("DANIEL_PLAYBOOK_REQUIRE_NETWORK", "").strip().lower() in (
        "1", "true", "yes", "on", "是")


def contract_id(path):
    try:
        raw, _ = model.normalize(loader.read_json(path))
        return raw.get(model.F_ID)
    except CliError:
        return None


def exit_code_of(result):
    return EXIT_OK if result.get("通过") else EXIT_INTERNAL
