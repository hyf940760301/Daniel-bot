# -*- coding: utf-8 -*-
"""契约执行器：把契约跑成"有证据的运行"（TICKET-146 · 任务内容 2/3/4/5）。

一次运行的顺序（每一步都为报告留证据）：

    ① 输入与限额      —— 样本模式是默认；超硬上限 → 报错退出（不静默截断）
    ② 前置            —— 声明的前置条件不成立就不往下跑（不装作跑过）
    ③ 门禁：写权限    —— 每条写步骤按它所属模块核对**当前账号有没有写权限**（权限驱动，
                        不是审批）；没有权限、认不出模块、拿不到账号快照 → 拦下（退出码 2）
    ④ 步骤            —— 调用命令（复用本 CLI）／离线假动作；写步骤走三段门禁
    ⑤ 判据            —— 契约声明的判据逐条变成断言结果（通过/失败/跳过）
    ⑥ 交付件          —— 按 `交付件schema` 出件并核对列与行数
    ⑦ 门禁（收尾）    —— 只读默认／写步骤确认／回读校验 的台账核对
    ⑧ 自检            —— 契约声明的必过项 + 计数自洽
    ⑨ 报告            —— 含计数自洽（声明项数＝实跑项数＝通过＋失败＋跳过）

退出码只用既有四码（不新增第五个）：
  `0` 通过｜`1` 执行期失败（步骤失败／必过项未过／回读对不上）｜
  `2` 用户错误（超限、幻觉命令、非法覆盖值）｜`3` 需确认（写步骤未加 --confirm）。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from ..exits import EXIT_INTERNAL, EXIT_NEEDS_CONFIRM, EXIT_OK, EXIT_USAGE
from ..runtime import CliError
from . import actions, assertions, deliverable, gates, model

_HERE = os.path.dirname(os.path.abspath(__file__))
CLI_PATH = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "bin", "daniel")

DEFAULT_OPTS = {
    "样本模式": True,       # v0.1 默认（也是唯一）模式
    "全量": False,          # `--full`：v0.1 直接报错退出
    "确认": False,          # `--confirm`
    "干跑": False,          # `--dry-run`（显式干跑优先于确认）
    "留存": False,          # `--keep`：保留本次自建的临时沙箱（不清理）
    "限额覆盖": {},         # {上限名: 整数}
    "输入覆盖": {},         # {输入名: 值}
    "沙箱": None,           # 离线假动作的落点根目录
    "契约目录": None,
    "交付落点": None,       # 模板式出件的落点覆盖（空＝走 daniel_paths 默认值）
}


# ─────────────────────────── 运行状态 ───────────────────────────
class RunState:
    """一次运行的上下文：也是断言取值引用（`运行.*` / `步骤.*` …）的唯一解析处。"""

    def __init__(self, contract, path, opts, sandbox, sandbox_plan=None):
        self.contract = contract
        self.契约路径 = path or ""
        self.opts = opts
        self.沙箱目录 = sandbox
        self.输入值 = {}
        self.变量 = {}
        self.限额 = {}
        self.步骤 = {}
        self.明细步骤 = []
        self.写动作台账 = []
        self.交付件 = {"状态": model.ST_SKIP, "明细": "未生成"}
        self.计数 = {}
        self.停止 = None
        self.契约摘要 = {
            "id": contract.get(model.F_ID),
            "名称": contract.get(model.F_NAME),
            "版本": contract.get(model.F_VERSION),
            "路径": os.path.abspath(path) if path else None,
            "示例": bool(path and loader_is_example(path)),
            "含写步骤": bool(model.write_steps(contract)),
        }
        self.运行 = {
            "样本模式": bool(opts["样本模式"]),
            "全量请求": bool(opts["全量"]),
            "确认": bool(opts["确认生效"]),
            "干跑": bool(opts["干跑"]),
            "沙箱目录": sandbox,
            "沙箱保留": (sandbox_plan or {}).get("沙箱保留", "保留"),
            "沙箱保留理由": (sandbox_plan or {}).get("沙箱保留理由", ""),
            "契约目录": opts.get("契约目录") or "",
            "能力目录": "",
            "CLI路径": CLI_PATH,
            "工作目录": os.getcwd(),
            "契约路径": os.path.abspath(path) if path else "",
            "写动作条数": 0,
            #: 本次写权限判定用的是哪份账号上下文（契约声明／注入快照／本地缓存／真探测／拿不到）
            "写权限来源": "未评估",
            #: TICKET-175：出件落点覆盖（`playbook deliver --out DIR`）。
            #: 为空＝走 daniel_paths 的默认值（`$DANIEL_HOME/output/<契约id>/`），不写代码目录。
            model.O_DELIVER_OUT: (opts.get("交付落点") or ""),
        }

    def expand(self, value):
        """展开模板（字符串／字典／列表都递归），供步骤参数与路径使用。"""
        if isinstance(value, str):
            return assertions.expand_template(value, self)
        if isinstance(value, dict):
            return {k: self.expand(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.expand(v) for v in value]
        return value


def loader_is_example(path):
    from . import loader
    try:
        return loader.is_example(path)
    except Exception:                                                       # noqa: BLE001
        return False


def _entry(ident, desc, status, detail="", **extra):
    row = {"id": ident, "说明": desc, "状态": status, "明细": detail}
    row.update(extra)
    return row


def _block(declared, evaluated):
    out = {"明细": evaluated}
    out.update(model.counts(declared, evaluated))
    return out


# ─────────────────────────── 输入 / 限额 ───────────────────────────
def _resolve_inputs(state):
    contract = state.contract
    declared = contract.get(model.F_INPUTS) or []
    overrides = dict(state.opts["输入覆盖"])
    known = {i.get("名称") for i in declared if isinstance(i, dict)}
    unknown = sorted(set(overrides) - known)
    if unknown:
        raise CliError("`--input` 引用了契约里没有声明的输入：%s" % "／".join(unknown),
                       code=EXIT_USAGE,
                       hint="本契约声明的输入：%s" % ("／".join(sorted(known)) or "无"))
    rows = []
    for spec in declared:
        if not isinstance(spec, dict):
            continue
        name = spec.get("名称")
        t = spec.get("类型", "str")
        if name in overrides:
            raw, source = overrides[name], "覆盖"
        elif spec.get("默认") is not None:
            raw, source = spec.get("默认"), "默认"
        elif spec.get("必填"):
            raise CliError("缺少必填输入：%s（用 `--input %s=值` 给）" % (name, name),
                           code=EXIT_USAGE)
        else:
            raw, source = None, "未给"
        value = _coerce_input(name, t, raw)
        state.输入值[name] = value
        rows.append({"名称": name, "类型": t, "必填": bool(spec.get("必填")),
                     "说明": spec.get("说明", ""), "取值": value, "来源": source})
    return rows


def _coerce_input(name, t, raw):
    if raw is None:
        return None
    if t == "int":
        try:
            return int(raw)
        except (TypeError, ValueError):
            raise CliError("输入「%s」需要整数（当前 %r）" % (name, raw), code=EXIT_USAGE)
    if t == "float":
        try:
            return float(raw)
        except (TypeError, ValueError):
            raise CliError("输入「%s」需要数字（当前 %r）" % (name, raw), code=EXIT_USAGE)
    if t == "flag":
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "是", "on")
    return raw if isinstance(raw, str) else str(raw)


def _resolve_limits(state, board):
    """样本上限：默认值 → `--limit` 覆盖；覆盖超硬上限即拦下（报错退出，不截断）。"""
    spec_rows = model.limit_rows(state.contract)
    overrides = dict(state.opts["限额覆盖"])
    unknown = sorted(set(overrides) - set(spec_rows))
    if unknown:
        raise CliError("`--limit` 引用了契约里没有声明的上限：%s" % "／".join(unknown),
                       code=EXIT_USAGE,
                       hint="本契约声明的上限：%s" % "／".join(sorted(spec_rows)))
    for name, spec in spec_rows.items():
        actual = overrides.get(name, spec.get(model.L_DEFAULT))
        problem = gates.sample_override_problem(name, spec, actual)
        if problem:
            board.block(model.G_SAMPLE, problem)
            state.限额[name] = {"默认": spec.get(model.L_DEFAULT), "硬上限": spec.get(model.L_HARD),
                              "实际": actual, "说明": spec.get(model.L_NOTE),
                              "覆盖": name in overrides}
            return False
        board.note(model.G_SAMPLE, "「%s」实际 %s（默认 %s／硬上限 %s）%s"
                   % (name, actual, spec.get(model.L_DEFAULT), spec.get(model.L_HARD),
                      "（由 --limit 覆盖）" if name in overrides else ""))
        state.限额[name] = {"默认": spec.get(model.L_DEFAULT), "硬上限": spec.get(model.L_HARD),
                          "实际": actual, "说明": spec.get(model.L_NOTE),
                          "覆盖": name in overrides}
    board.note(model.G_SAMPLE, "样本模式：%s（v0.1 不实现全量）"
               % ("开" if state.运行["样本模式"] else "关"))
    return True


def _runtime_limit_problem(state):
    """步骤产出超上限 → 拦下（不静默截断）。返回问题文案或 None。"""
    for name, spec in model.limit_rows(state.contract).items():
        sid = spec.get(model.L_STEPS)
        if not sid:
            continue
        res = state.步骤.get(sid)
        if not res or res.get("状态") != model.ST_PASS:
            continue
        problem = gates.sample_runtime_problem(name, state.限额.get(name, {}), res.get("条目数"))
        if problem:
            return problem
    return None


# ─────────────────────────── 步骤 ───────────────────────────
def _command_args(step, state):
    raw = step.get(model.S_COMMAND) or ""
    parts = raw.split()
    if len(parts) != 2:
        raise CliError("步骤 %s 的 `命令` 必须写成「<模块> <子命令>」" % step.get(model.S_ID),
                       code=EXIT_USAGE)
    argv = [sys.executable, CLI_PATH, parts[0], parts[1]]
    for key, value in sorted((step.get(model.S_PARAMS) or {}).items()):
        v = state.expand(value)
        if v is True:
            argv.append(key)
        elif v is False or v is None:
            continue
        elif isinstance(v, list):
            for item in v:
                argv += [key, str(item)]
        else:
            argv += [key, str(v)]
    argv.append("--json")
    return argv


def _run_command_step(step, state, timeout=600):
    argv = _command_args(step, state)
    t0 = time.time()
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _entry(step.get(model.S_ID), step.get(model.S_DESC), model.ST_FAIL,
                      "步骤超时（%d 秒）：%s" % (timeout, step.get(model.S_COMMAND)),
                      动作=model.ACT_CALL, 命令=step.get(model.S_COMMAND), 退出码=None)
    elapsed = int((time.time() - t0) * 1000)
    data = None
    try:
        doc = json.loads(p.stdout)
        data = doc.get("data", doc.get("text"))
    except ValueError:
        doc = None
    status = model.ST_PASS if p.returncode == 0 else model.ST_FAIL
    detail = ("命令「%s」退出码 %d" % (step.get(model.S_COMMAND), p.returncode))
    if status == model.ST_FAIL:
        tail = (p.stderr or p.stdout or "").strip().splitlines()
        detail += "：" + (tail[-1] if tail else "无输出")
    return _entry(step.get(model.S_ID), step.get(model.S_DESC), status, detail,
                  动作=model.ACT_CALL, 命令=step.get(model.S_COMMAND),
                  退出码=p.returncode, 条目数=_item_count(data), 数据=data,
                  耗时毫秒=elapsed)


def _item_count(data):
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        if isinstance(data.get("count"), int):
            return data["count"]
        lists = [len(v) for v in data.values() if isinstance(v, list)]
        return max(lists) if lists else 0
    return 1 if data is not None else 0


def _fixture_step(step, state):
    res = actions.perform(step, state)
    status = res.pop("状态")
    detail = res.pop("明细", "")
    row = _entry(step.get(model.S_ID), step.get(model.S_DESC), status, detail,
                 动作=model.ACT_FIXTURE, 操作=step.get(model.S_OPERATION),
                 条目数=res.pop("条目数", 0))
    row.update(res)
    return row


def _run_steps(state, board):
    steps = state.contract.get(model.F_STEPS) or []
    for step in steps:
        sid = step.get(model.S_ID)
        if state.停止:
            state.明细步骤.append(_entry(sid, step.get(model.S_DESC), model.ST_SKIP,
                                        "未执行：%s" % state.停止["原因"],
                                       动作=step.get(model.S_ACTION), 退出码=None))
            state.步骤[sid] = state.明细步骤[-1]
            continue
        if step.get(model.S_WRITE) and not state.opts["确认生效"]:
            # 门禁：写步骤未确认 → dry-run（只打印计划），不执行任何写
            plan = gates.plan_for(step, state)
            board.block(model.G_WRITE_CONFIRM,
                        "写步骤 %s 未加 --confirm：已 dry-run，**未执行任何写**（计划：%s）"
                        % (sid, json.dumps(plan, ensure_ascii=False)))
            problem, detail = gates.not_written_problem(step, state)
            if problem:
                board.block(model.G_READBACK, problem)
            elif detail:
                board.note(model.G_READBACK, detail)
            row = _entry(sid, step.get(model.S_DESC), model.ST_SKIP,
                         "被门禁「%s」拦下，未执行（已 dry-run）" % model.G_WRITE_CONFIRM,
                         动作=step.get(model.S_ACTION), 退出码=None, 计划=plan, 条目数=0)
            state.步骤[sid] = row
            state.明细步骤.append(row)
            state.停止 = {"原因": "写步骤 %s 需要 --confirm（已 dry-run，未执行任何写）" % sid,
                        "退出码": EXIT_NEEDS_CONFIRM, "结果": model.R_CONFIRM}
            continue

        if step.get(model.S_ACTION) == model.ACT_CALL:
            row = _run_command_step(step, state)
        else:
            row = _fixture_step(step, state)
        state.步骤[sid] = row
        state.明细步骤.append(row)

        if step.get(model.S_WRITE) and row.get("状态") == model.ST_PASS:
            rb = gates.readback_of(step)
            st, detail = assertions.evaluate(rb, state)
            board.note(model.G_READBACK, "步骤 %s 回读：%s" % (sid, detail))
            if st != model.ST_PASS:
                board.block(model.G_READBACK, "步骤 %s 回读校验不通过：%s" % (sid, detail))
                row["状态"] = model.ST_FAIL
                state.停止 = {"原因": "写步骤 %s 回读校验不通过" % sid,
                            "退出码": EXIT_INTERNAL, "结果": model.R_FAIL}

        if row.get("状态") == model.ST_FAIL and not state.停止:
            state.停止 = {"原因": "步骤 %s 执行失败" % sid,
                        "退出码": EXIT_INTERNAL, "结果": model.R_FAIL}

        problem = _runtime_limit_problem(state)
        if problem and not state.停止:
            board.block(model.G_SAMPLE, problem)
            state.停止 = {"原因": problem, "退出码": EXIT_USAGE, "结果": model.R_BLOCK}
    for step in steps:                      # 写步骤记下它所属的模块（权限判定按模块判）
        sid = step.get(model.S_ID)
        if step.get(model.S_WRITE) and sid in state.步骤:
            state.步骤[sid]["模块"] = gates.module_of(step)
    return state.明细步骤


# ─────────────────────────── 断言组（前置／判据／自检） ───────────────────────────
def _extra_keys(item):
    """判据／自检项可以显式声明 `必过`（默认 true）；步骤与门禁项没有这个开关。"""
    return {"必过": bool(item["必过"])} if "必过" in item else {}


def _assertion_problems(declared, state):
    rows = []
    for item in declared:
        cond = _condition(item, state)
        if cond is not None:
            rows.append(_entry(item.get(model.S_ID), item.get(model.S_DESC), model.ST_SKIP,
                               cond, **_extra_keys(item)))
            continue
        st, detail = assertions.evaluate(item.get("断言") or {}, state)
        rows.append(_entry(item.get(model.S_ID), item.get(model.S_DESC), st, detail,
                           **_extra_keys(item)))
    return rows


def _condition(item, state):
    """`当` 条件：不成立（或无法评估）→ 记「跳过」，明细写明原因（不静默通过）。"""
    cond = item.get(model.F_WHEN)
    if not isinstance(cond, dict):
        return None
    st, detail = assertions.evaluate(cond, state)
    if st == model.ST_PASS:
        return None
    return "不适用：条件不成立（%s）——%s" % (detail, cond.get(model.A_TYPE))


# ─────────────────────────── 交付件 ───────────────────────────
# 两代写法共用同一个钩子（TICKET-175）：**声明了 `格式`** 就是模板式出件 —— 交给
# `deliverable.deliver()`（出件模板 ＋ 五条出件自检 ＋ daniel_paths 落盘）；
# 没声明就还是老行为（JSON 落本次运行的沙箱）—— 老契约一个字不用改。
def _deliverable(state):
    spec = state.contract.get(model.F_DELIVERABLE) or {}
    if state.停止:
        return {"状态": model.ST_SKIP, "名称": spec.get(model.D_NAME),
                "明细": "本次运行被拦下（%s），未出件" % state.停止["原因"]}
    src = spec.get(model.D_SOURCE)
    res = state.步骤.get(src)
    if not res or res.get("状态") != model.ST_PASS:
        return {"状态": model.ST_SKIP, "名称": spec.get(model.D_NAME),
                "明细": "来源步骤 %s 未成功产出，未出件" % src}
    rows = res.get("数据") or []
    if not isinstance(rows, list):
        return {"状态": model.ST_FAIL, "名称": spec.get(model.D_NAME),
                "明细": "来源步骤 %s 的产出不是条目列表" % src}
    if deliverable.is_template(spec):
        return _deliverable_template(state, spec, rows)
    return _deliverable_legacy(state, spec, rows)


def _deliverable_template(state, spec, rows):
    """模板式出件：出件模板 ＋ 五条自检 ＋ 落点（`$DANIEL_HOME/output/<契约id>/`）。

    落点由**调用方**决定时可覆盖（`playbook deliver --out DIR`）；未指定时默认值走
    `daniel_paths`（落点规范 TICKET-154 §一.3）。
    """
    step_counts = {sid: {"条目数": (r or {}).get("条目数")} for sid, r in state.步骤.items()}
    return deliverable.deliver(
        spec, rows,
        contract_id=state.契约摘要.get("id"),
        step_counts=step_counts,
        limits=state.限额,
        inputs=state.输入值,
        out_dir=state.运行.get(model.O_DELIVER_OUT),
        row_limit=spec.get(model.D_ROW_LIMIT),
    )


def _deliverable_legacy(state, spec, rows):
    """遗留式出件（未声明 `格式`）：行为与 TICKET-146 时一致 —— JSON 落本次运行的沙箱。"""
    required = list(spec.get(model.D_REQUIRED_COLUMNS) or [])
    missing = []
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            missing.append("第 %d 行不是对象" % i)
            continue
        for col in required:
            if row.get(col) in (None, ""):
                missing.append("第 %d 行缺「%s」" % (i, col))
    ref = spec.get(model.D_ROW_LIMIT)
    cap = (state.限额.get(ref) or {}).get("实际") if ref else None
    over = ("行数 %d 超过上限「%s」= %s" % (len(rows), ref, cap)
            if cap is not None and len(rows) > cap else None)
    path = os.path.join(state.沙箱目录, spec.get(model.D_FILE) or "交付件.json")
    payload = {"名称": spec.get(model.D_NAME), "样本模式": state.运行["样本模式"],
               "生成时间": time.strftime("%Y-%m-%d %H:%M:%S"),
               "列": spec.get(model.D_COLUMNS) or [], "行数": len(rows), "行": rows,
               "上限": {ref: cap} if ref else {}}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    problems = missing + ([over] if over else [])
    return {"状态": model.ST_FAIL if problems else model.ST_PASS,
            "名称": spec.get(model.D_NAME), "路径": path, "行数": len(rows),
            "列": spec.get(model.D_COLUMNS) or [], "必填列": required, "数据": rows,
            "校验": "不通过：%s" % "；".join(problems[:5]) if problems else "通过",
            "明细": "按《%s》出件，%d 行%s" % (spec.get(model.D_NAME), len(rows),
                                          "，受上限「%s」约束" % ref if ref else "")}


# ─────────────────────────── 主流程 ───────────────────────────
def run_contract(contract, path=None, opts=None):
    """跑一份契约：返回 `(报告, 退出码)`。**不做任何 Daniel 写操作**。

    沙箱处置（P0-1 修正）：本次自建的临时沙箱在 `finally` 里清理（成功、报错、被门禁拦下
    三种情况都清）；用户指定了落点（`DANIEL_PLAYBOOK_SANDBOX`）或显式 `--keep` 时一律保留，
    并在报告的 `运行.沙箱保留` / `运行.沙箱保留理由` 里写清是哪一种。
    """
    o = dict(DEFAULT_OPTS)
    o.update(opts or {})
    o["确认生效"] = bool(o["确认"]) and not bool(o["干跑"])
    if o["全量"]:
        raise CliError("`--full`（全量口径）在 v0.1 不实现：本工序一律走样本模式",
                       code=EXIT_USAGE,
                       hint="去掉 --full 即按契约声明的样本上限运行；"
                            "生产全量口径是后续工序的事（本工序不开口子）")
    sandbox, owned, plan = _sandbox(o)
    try:
        report, code = _execute(contract, path, o, sandbox, plan)
    finally:
        final_note = _release_sandbox(sandbox, owned, plan)
    report["运行"].update(final_note)
    if final_note["沙箱保留"] == "已清理":
        report["交付件"] = dict(report["交付件"], 清理="交付件随本次临时沙箱一并清理；"
                                                   "如需留存请加 --keep 或设 DANIEL_PLAYBOOK_SANDBOX")
    return report, code


def _execute(contract, path, o, sandbox, sandbox_plan):
    """一次运行的主体（沙箱已就绪；清理由 `run_contract` 的 `finally` 负责）。"""
    board = gates.GateBoard(contract)
    state = RunState(contract, path, o, sandbox, sandbox_plan)
    t0 = time.time()

    from ..runtime import tools_dir
    try:
        state.运行["能力目录"] = tools_dir()
    except CliError as e:
        state.运行["能力目录"] = "（缺失：%s）" % e.message

    # ① 输入与限额
    inputs = _resolve_inputs(state)
    limits_ok = _resolve_limits(state, board)
    if not limits_ok:
        state.停止 = {"原因": "样本上限被突破（已报错退出，未做任何截断）",
                    "退出码": EXIT_USAGE, "结果": model.R_BLOCK}

    # ② 前置
    pres_declared = contract.get(model.F_PRECONDITIONS) or []
    if state.停止:
        pres = [_entry(p.get(model.S_ID), p.get(model.S_DESC), model.ST_SKIP,
                       "未评估：%s" % state.停止["原因"]) for p in pres_declared]
    else:
        pres = _assertion_problems(pres_declared, state)
        bad = [r for r in pres if r["状态"] == model.ST_FAIL]
        if bad:
            state.停止 = {"原因": "前置条件不成立：%s" % bad[0]["id"],
                        "退出码": EXIT_INTERNAL, "结果": model.R_FAIL}

    # ③ 门禁：写权限（运行期）—— 每条写步骤按所属模块核对"当前账号有没有写权限"
    #    口径：写链开放由**账号的使用权限**决定，不是审批；判定比步骤早一步发生，
    #    所以被拦下时一次写都不会发生（并回读证明目标不存在）。
    wp, wp_notes, _auth = gates.write_permission_problems(contract, state)
    if wp:
        board.block(model.G_WRITE_PERMISSION, "；".join(wp))
        gates.blocked_write_evidence(board, contract, state)
        if not state.停止:
            state.停止 = {"原因": "写权限门禁拦下本次运行：%s" % wp[0],
                        "退出码": EXIT_USAGE, "结果": model.R_BLOCK,
                        "门禁": model.G_WRITE_PERMISSION}
    else:
        for detail in wp_notes:
            board.note(model.G_WRITE_PERMISSION, detail)

    # ④ 步骤
    steps_rows = _run_steps(state, board)
    state.运行["写动作条数"] = len(state.写动作台账)      # 台账条数也是可断言的运行期事实

    # ⑤ 判据
    crit_declared = contract.get(model.F_CRITERIA) or []
    crit = _assertion_problems(crit_declared, state)
    must_fail = [r for r in crit if r["状态"] == model.ST_FAIL and r.get("必过", True)]

    # ⑥ 交付件
    state.交付件 = _deliverable(state)

    # ⑦ 门禁收尾
    has_write = bool(model.write_steps(contract))
    blocked_by_permission = bool(state.停止 and state.停止.get("门禁") == model.G_WRITE_PERMISSION)
    if not has_write:
        board.skip(model.G_WRITE_CONFIRM, "本契约没有写步骤（读链默认零写），无需确认")
        board.skip(model.G_READBACK, "本契约没有写步骤，无回读对象")
    elif blocked_by_permission:
        board.note(model.G_WRITE_CONFIRM, "本次运行在写权限门禁处被拦下：写步骤未执行，"
                                          "确认与执行两段都没有走到（未执行任何写）")
    elif o["确认生效"]:
        board.note(model.G_WRITE_CONFIRM, "写步骤已带 --confirm：dry-run → 执行 → 回读三段已跑")
    stray = gates.readonly_problem(contract, state)
    if stray:
        board.block(model.G_READONLY, stray)
    else:
        board.note(model.G_READONLY, "写动作台账 %d 条，全部来自声明为写的步骤"
                   % len(state.写动作台账))

    # ⑧ 自检：普通项先评 → 计数齐备 → `计数自洽` 项再评（按声明顺序回填）
    self_declared = contract.get(model.F_SELFCHECKS) or []
    deferred = [i for i in self_declared if (i.get("断言") or {}).get(model.A_TYPE) == "计数自洽"]
    self_rows, plain_rows = _selfcheck_rows(self_declared, deferred, state)
    state.计数 = _counts_now(state, pres, steps_rows, crit, board, self_declared, plain_rows)
    state.计数["自检"] = model.counts(self_declared, self_rows)      # 实跑项数＝声明项数
    for item in deferred:
        row = [r for r in self_rows if r["id"] == item.get(model.S_ID)][0]
        cond = _condition(item, state)
        if cond is not None:
            row["状态"], row["明细"] = model.ST_SKIP, cond
            continue
        st, detail = assertions.evaluate(item.get("断言") or {}, state)
        row["状态"], row["明细"] = st, detail
    state.计数["自检"] = model.counts(self_declared, self_rows)

    # ⑨ 报告
    groups = {
        "前置": _block(pres_declared, pres),
        "步骤": _block(contract.get(model.F_STEPS) or [], steps_rows),
        "判据": _block(crit_declared, crit),
        "门禁": board.report(),
        "自检": _block(self_declared, self_rows),
    }
    total = model.merge_counts(groups)
    self_fail = [r for r in self_rows if r["状态"] == model.ST_FAIL and r.get("必过", True)]
    deliverable_fail = state.交付件.get("状态") == model.ST_FAIL

    if state.停止:
        code, result = state.停止["退出码"], state.停止["结果"]
        summary = state.停止["原因"]
    elif must_fail or self_fail or deliverable_fail or not total[model.C_SELF]:
        code, result = EXIT_INTERNAL, model.R_FAIL
        bits = []
        if must_fail:
            bits.append("必过判据未过：%s" % "／".join(r["id"] for r in must_fail))
        if self_fail:
            bits.append("必过自检未过：%s" % "／".join(r["id"] for r in self_fail))
        if deliverable_fail:
            bits.append("交付件校验不通过")
        if not total[model.C_SELF]:
            bits.append("计数不自洽")
        summary = "；".join(bits)
    else:
        code, result = EXIT_OK, model.R_PASS
        summary = "判据 %d 条全过、门禁 %d 道无拦截、自检 %d 项全过、计数自洽" % (
            len(crit), len(board.rows()), len(self_rows))

    report = {
        "契约": state.契约摘要,
        "运行": dict(state.运行, 沙箱目录=state.沙箱目录,
                     耗时毫秒=int((time.time() - t0) * 1000)),
        "输入": inputs,
        "限额": state.限额,
        "前置": groups["前置"],
        "步骤": groups["步骤"],
        "判据": groups["判据"],
        "门禁": groups["门禁"],
        "交付件": state.交付件,
        "自检": groups["自检"],
        "失败模式": contract.get(model.F_FAILURE_MODES) or [],
        "写动作台账": state.写动作台账,
        "计数": {"分组": {k: {kk: v[kk] for kk in (model.C_DECLARED, model.C_RUN,
                                                  model.C_PASS, model.C_FAIL, model.C_SKIP,
                                                  model.C_SELF)}
                          for k, v in groups.items()},
                 "合计": total},
        "结论": {"通过": code == EXIT_OK, "结果": result, "退出码": code,
                 "摘要": summary, "计数自洽": bool(total[model.C_SELF])},
    }
    return report, code


def _counts_now(state, pres, steps_rows, crit, board, self_declared, plain_rows):
    """评估 `计数自洽` 断言时的计数快照。

    此时 `计数自洽` 项自己还没评（它要用这份快照），所以按"已实跑"计入：
    实跑项数 ＝ 已评项数 ＋ 待评项数 ＝ 声明项数，公式照样成立（见 `_selfcheck_rows`）。
    """
    claimed = plain_rows + [_entry(None, None, model.ST_PASS, "本轮末评估")
                            for _ in range(len(self_declared) - len(plain_rows))]
    return {
        "前置": model.counts(state.contract.get(model.F_PRECONDITIONS) or [], pres),
        "步骤": model.counts(state.contract.get(model.F_STEPS) or [], steps_rows),
        "判据": model.counts(state.contract.get(model.F_CRITERIA) or [], crit),
        "门禁": board.counts(),
        "自检": model.counts(self_declared, claimed),
    }


def _selfcheck_rows(self_declared, deferred, state):
    """自检项：普通项按声明顺序先评；`计数自洽` 项等计数齐备后再评（主流程回填）。

    返回 `(按声明顺序的行, 已评的普通行)`。
    """
    rows = []
    for item in self_declared:
        if item in deferred:
            rows.append(_entry(item.get(model.S_ID), item.get(model.S_DESC), model.ST_PASS,
                               "待评（本轮末评估，见主流程）", **_extra_keys(item)))
            continue
        cond = _condition(item, state)
        if cond is not None:
            rows.append(_entry(item.get(model.S_ID), item.get(model.S_DESC), model.ST_SKIP,
                               cond, **_extra_keys(item)))
            continue
        st, detail = assertions.evaluate(item.get("断言") or {}, state)
        rows.append(_entry(item.get(model.S_ID), item.get(model.S_DESC), st, detail,
                           **_extra_keys(item)))
    pending = "待评（本轮末评估，见主流程）"
    return rows, [r for r in rows if r["明细"] != pending]


def _sandbox(opts):
    """决定本次运行的沙箱落点与**处置方式**（P0-1 修正）。

    三种情形：
      - 用户指定了落点（`--sandbox` 参数／`DANIEL_PLAYBOOK_SANDBOX`）→ 一律**保留**，引擎不删；
      - 没指定落点但显式加了 `--keep` → 自建临时沙箱但**保留**（供人工检查）；
      - 都没有 → 自建临时沙箱，**跑完在 `finally` 里清理**（不留垃圾，也不删用户指定的落点）。

    返回值 `(路径, 是否本次自建, 计划)`；`计划` 会先写进报告，运行结束再被最终处置覆盖。
    """
    base = opts.get("沙箱") or os.environ.get("DANIEL_PLAYBOOK_SANDBOX")
    if base:
        path = os.path.abspath(os.path.expanduser(str(base)))
        os.makedirs(path, exist_ok=True)
        who = "DANIEL_PLAYBOOK_SANDBOX" + ("／--keep" if opts.get("留存") else "")
        plan = {"沙箱保留": "保留",
                "沙箱保留理由": "用户指定落点（%s）：引擎不清理，落点 %s" % (who, path)}
        return path, False, plan
    path = tempfile.mkdtemp(prefix="daniel-playbook-")
    if opts.get("留存"):
        plan = {"沙箱保留": "保留",
                "沙箱保留理由": "本次运行显式加了 --keep：保留临时沙箱供人工检查，落点 %s" % path}
        return path, False, plan
    plan = {"沙箱保留": "将清理",
            "沙箱保留理由": "临时沙箱（本次运行自建），跑完即清理；如需留存请加 --keep 或设 "
                        "DANIEL_PLAYBOOK_SANDBOX"}
    return path, True, plan


def _release_sandbox(path, owned, plan):
    """按计划处置沙箱：**异常路径也会走到**（`run_contract` 的 `finally` 调用）。"""
    if not owned:
        return dict(plan)
    if not os.path.isdir(path):
        return {"沙箱保留": "已不存在", "沙箱保留理由": "沙箱目录已不存在（无需清理）"}
    try:
        shutil.rmtree(path)
    except OSError as e:
        return {"沙箱保留": "保留",
                "沙箱保留理由": "清理失败：%s（落点 %s，请人工处置）" % (e, path)}
    return {"沙箱保留": "已清理", "沙箱保留理由": plan.get("沙箱保留理由") or "临时沙箱，跑完即清理"}
