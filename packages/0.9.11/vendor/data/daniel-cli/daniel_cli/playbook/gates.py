# -*- coding: utf-8 -*-
"""门禁框架（TICKET-146 · 任务内容 3；D4 写链验收口径；TICKET-152 · P0-5 权限驱动）。

**门禁挂在执行器内部**（`executor.py` 直接调用本模块），不依赖任何宿主 hook ——
第三方宿主（另一个模型／一个 MCP 壳／一台没有 DSH 的机器）没有 hook 通道，
所以"门禁"不能是宿主的东西，只能是**引擎自己的东西**。

五道内置门禁（契约必须全部声明，不允许静默放弃）：

| 门禁 | 拦什么 | 拦下时退出码 |
|---|---|---|
| `样本上限` | 覆盖值超过硬上限、或步骤产出超过上限 → 报错，**不静默截断** | 2 用户错误 |
| `写权限` | 写步骤引用不了模块、拿不到账号权限快照、或**当前账号对该模块没有写权限** → 拦下；权限具备但引用了真实写命令也拦下（写动作只允许沙箱内的离线假动作） | 2 用户错误 |
| `只读默认` | 读链默认零写：写动作只能来自"声明为写的步骤" | 1 内部错误 |
| `写步骤确认` | 写步骤未加 `--confirm` → dry-run（只打印计划），**不执行任何写** | 3 需确认 |
| `回读校验` | 写执行完必须回读核对；被拦下的写必须证明"目标不存在" | 1 内部错误 |

判据口径（用户 2026-10-14 裁决）：**写链开放与否由账号的使用权限决定，不是审批** ——
账号能展示的模块对应的写自动开放，没有权限的模块不能用也不能写；本工程不引入任何审批流。
权限判据本身在 `daniel_cli/permissions.py`（模块 × 读/写 × 三条判据轴），本模块只负责
"把契约里的每一个写步骤按它声明（或命令反推）的模块送进判据，不许的拦下"。

报告口径：门禁状态与其它组一致（通过／失败／跳过），另用 `拦截` 字段标明"是否拦下了本次运行"，
这样"声明项数＝实跑项数＝通过＋失败＋跳过"这条计数自洽对五组通用。
"""
import os

from . import model


class GateBoard:
    """门禁台账：五道门禁各一条，记录明细与结论。"""

    def __init__(self, contract):
        declared = {}
        for g in contract.get(model.F_GATES) or []:
            if isinstance(g, dict) and g.get(model.S_ID) in model.GATE_TYPES:
                declared[g[model.S_ID]] = g.get(model.S_DESC) or ""
        self._rows = []
        for t in model.GATE_TYPES:
            self._rows.append({"id": t, "类型": t,
                               "说明": declared.get(t) or "（契约未声明说明）",
                               "状态": model.ST_PASS, "拦截": False,
                               "退出码": model.GATE_EXIT_CODES[t], "明细": []})

    def _row(self, gate_type):
        for r in self._rows:
            if r["类型"] == gate_type:
                return r
        raise KeyError(gate_type)

    def note(self, gate_type, detail):
        self._row(gate_type)["明细"].append(detail)

    def skip(self, gate_type, detail):
        row = self._row(gate_type)
        if row["状态"] == model.ST_PASS and not row["拦截"]:
            row["状态"] = model.ST_SKIP
        row["明细"].append(detail)

    def block(self, gate_type, detail):
        """拦下本次运行：状态记失败、拦截记真，明细写清理由。"""
        row = self._row(gate_type)
        row["状态"] = model.ST_FAIL
        row["拦截"] = True
        row["明细"].append("拦截：" + detail)

    def rows(self):
        """对外快照：明细收成一行（**不改内部列表**，可重复调用）。"""
        out = []
        for r in self._rows:
            row = dict(r)
            detail = r["明细"]
            row["明细"] = "；".join(detail) if isinstance(detail, list) else detail
            row["明细"] = row["明细"] or "不适用"
            out.append(row)
        return out

    def counts(self):
        return model.counts([r for r in self._rows], self._rows)

    def report(self):
        """给运行报告用的门禁组：明细（五道门禁各一行）＋ 计数。"""
        out = {"明细": self.rows()}
        out.update(self.counts())
        return out

    def intercepted(self):
        for r in self._rows:
            if r["拦截"]:
                return r
        return None


# ─────────────────────────── G1 样本上限 ───────────────────────────
def sample_override_problem(name, spec, value):
    """覆盖值超过硬上限 → 报错文案（含当前值／上限／建议做法），**不截断**。"""
    hard = spec.get(model.L_HARD)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        return "限额「%s」的取值必须是正整数（当前 %r）" % (name, value)
    if hard is not None and value > hard:
        return ("限额「%s」超出上限：当前值 %d ／ 硬上限 %d ／ 建议做法："
                "用不超过 %d 的样本量跑（全量口径 v0.1 不实现，`--full` 会直接报错退出）"
                % (name, value, hard, hard))
    return None


def sample_runtime_problem(name, spec, actual):
    """步骤产出超过上限 → 报错文案（**不静默截断**：静默截断正是计数不自洽的常见来源）。"""
    cap = spec.get(model.L_HARD)
    if cap is None or actual is None:
        return None
    if actual > cap:
        return ("限额「%s」被产出超限：当前值 %d ／ 上限 %d ／ 建议做法：把产出调小到 %d 以内，"
                "或由契约在硬上限内抬高上限后重跑；引擎**不会**替你截断（静默截断正是计数不"
                "自洽的常见来源）" % (name, actual, cap, cap))
    return None


# ─────────────────────────── G2 写权限 ───────────────────────────
def _cli_schema():
    from .. import schema as cli_schema
    return cli_schema


def module_of(step):
    """一条步骤要写哪个模块：显式 `模块` 优先，否则从它引用的 CLI 命令反推父模块。

    反推口径：`命令` 写成「<模块> <子命令>」，`schema.find_command` 认得的命令，
    它的父模块就是模块键 —— 契约与 `schema.py` 单一真源焊死，不另造一套模块名。
    解析不出来（写步骤既没声明 `模块`，又没有可反推的命令）→ 返回 None，由门禁拦下。
    """
    declared = (step or {}).get(model.S_MODULE)
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    if (step or {}).get(model.S_ACTION) == model.ACT_CALL:
        parts = str(step.get(model.S_COMMAND) or "").split()
        if len(parts) == 2 and _cli_schema().find_command(parts[0], parts[1]) is not None:
            return parts[0]
    return None


def known_modules():
    """`schema.py` 里声明的模块键（`模块` 只能写这里的名字）。"""
    return tuple(_cli_schema().module_keys())


def module_problems(contract):
    """静态部分：写步骤必须能解析出所属模块（校验期与执行期共用同一套口径）。

    判据是权限驱动的，而权限是按模块判的 —— 所以"写哪个模块"必须写得出来，
    否则这条写步骤的权限根本核不了，只能拦下（用户错误，退出码 2）。
    """
    problems = []
    known = known_modules()
    for step in model.write_steps(contract):
        sid = step.get(model.S_ID)
        m = module_of(step)
        if m is None:
            problems.append("步骤 %s：写步骤必须声明所属模块，才能核对账号对该模块的写权限"
                            "（在步骤里加 `\"模块\": \"<模块键>\"`；可用：%s）"
                            % (sid, "／".join(known)))
        elif m not in known:
            problems.append("步骤 %s：`模块` 写了 %r，不是 daniel_cli/schema.py 里声明的模块"
                            "（可用：%s）" % (sid, m, "／".join(known)))
    return problems


def _feature_list(raw):
    """`工作区权益` 输入：逗号分隔文本（中英文逗号都认）或数组 → 权益名列表。"""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        items = [str(x) for x in raw]
    else:
        items = str(raw).replace("，", ",").split(",")
    return [x.strip() for x in items if x.strip()]


def declared_account(state):
    """契约声明的账号上下文（离线、确定性）；没声明 `账号角色` 就返回 None。

    三个可选输入名：`账号角色`／`账号状态`／`工作区权益`。只要声明了 `账号角色`
    （且给了取值），本次判定就用这份**声明的账号事实**造快照，一次网络都不走；
    `--input 账号角色=admin` 这类覆盖走引擎既有的输入覆盖机制，照样生效。
    """
    from .. import permissions
    role = state.输入值.get(model.IN_ROLE)
    if role in (None, ""):
        return None
    return permissions.auth_from_inputs(
        system_role=str(role),
        user_status=(None if state.输入值.get(model.IN_STATUS) in (None, "")
                     else str(state.输入值.get(model.IN_STATUS))),
        features=_feature_list(state.输入值.get(model.IN_FEATURES)),
        source="契约声明")


def account_context(state):
    """账号上下文：优先契约声明的账号事实，否则走 `permissions.current_auth()`。

    返回 `(快照 或 None, 取数说明)`；拿不到就返回 `(None, 原因)` —— 写操作
    "确认不了权限就不动手"（读操作不因此被拦，真实门禁在服务端）。
    """
    declared = declared_account(state)
    if declared is not None:
        return declared, ("契约声明（账号角色=%s／账号状态=%s／工作区权益=%s）："
                          "离线判定，不探测真实账号"
                          % (declared.get("systemRole"), declared.get("userStatus"),
                             "／".join(declared.get("enabledFeatures") or []) or "无"))
    try:
        from .. import permissions
        auth, note = permissions.current_auth()
    except Exception as e:                                                # noqa: BLE001
        return None, "取数失败：%s" % str(e)[:200]
    if auth is None:
        return None, str(note)
    return auth, str(note)


def _real_write_problem(step):
    """权限具备的前提下，还不许引用真实 Daniel 写命令（写动作只允许离线假动作）。"""
    raw = step.get(model.S_COMMAND) or ""
    parts = str(raw).split()
    if len(parts) != 2:
        return None
    cmd = _cli_schema().find_command(parts[0], parts[1])
    if cmd is not None and cmd["write"]:
        return ("该模块的写权限具备，但契约引擎的写动作只允许沙箱内的离线假动作；"
                "真实写请走 daniel CLI 的写命令（带 --confirm，删除类再加 --delete-token）")
    return None


def write_permission_problems(contract, state):
    """运行期门禁「写权限」：每条写步骤都要过"账号对该模块有没有写权限"。

    返回 `(问题[], 明细[], 快照 或 None)`：
      - 问题非空即拦下本次运行（退出码 2，用户错误）；
      - 明细是给报告看的判据过程（用的哪份账号上下文、每条写步骤的结论）。

    同时把 `运行.写权限来源` 写进运行期事实（**总是**写，拿不到也写原因），
    这样契约能断言"这次判定用的是哪份账号上下文"。
    """
    from .. import permissions
    problems, notes = [], []
    steps = model.write_steps(contract)
    if not steps:
        state.运行["写权限来源"] = "不适用（本契约没有写步骤）"
        return problems, ["本契约没有写步骤（读链默认零写）：写权限门禁不适用"], None

    # ① 写步骤必须能解析出模块
    problems += module_problems(contract)
    if problems:
        state.运行["写权限来源"] = "未取得（写步骤没有可判定的模块）"
        return problems, notes, None

    # ② 账号上下文：契约声明 → 注入快照／本地缓存／真探测；都拿不到就按安全口径拒绝
    auth, source = account_context(state)
    if auth is None:
        state.运行["写权限来源"] = "拿不到账号权限快照（%s）" % source
        problems.append("拿不到账号权限快照，确认不了该模块的写权限，按安全口径拒绝（%s）" % source)
        return problems, notes, None
    state.运行["写权限来源"] = source
    notes.append("账号上下文：%s" % source)

    # ③ 逐条写步骤判定：没有该模块的写权限就拦下（理由写明哪一轴不满足）
    for step in steps:
        sid = step.get(model.S_ID)
        m = module_of(step)
        v = permissions.verdict(m, permissions.WRITE, auth)
        if not v[permissions.K_ALLOWED]:
            problems.append("步骤 %s：%s" % (sid, permissions.denial_message(m, permissions.WRITE, v)))
            continue
        rw = _real_write_problem(step)
        if rw:
            problems.append("步骤 %s：%s" % (sid, rw))
            continue
        notes.append("步骤 %s：模块「%s」的写权限具备（%s）" % (sid, m, v.get("reason")))
    return problems, notes, auth


def blocked_write_evidence(board, contract, state):
    """被写权限拦下的写步骤：沿用既有"无写发生"的取证口径，回读证明目标不存在。

    **不作为二次拦截**：目标若在运行前就已存在，那本来就不是本次写出来的，
    此时只在明细里写清"这份证据不可用"，不冤枉引擎。
    """
    for step in model.write_steps(contract):
        sid = step.get(model.S_ID)
        rb = readback_of(step)
        raw = rb.get(model.A_VALUE)
        if not isinstance(raw, str) or not raw:
            continue
        problem, detail = not_written_problem(step, state)
        if problem:
            board.note(model.G_READBACK, "步骤 %s 被写权限门禁拦下、未执行写；%s"
                                        "（目标在运行前就已存在，不能作为「未写入」的证据）"
                       % (sid, problem))
        elif detail:
            board.note(model.G_READBACK, "步骤 %s 被写权限门禁拦下、未执行写；%s" % (sid, detail))


# ─────────────────────────── G3 只读默认 ───────────────────────────
def readonly_problem(contract, state):
    """读链默认零写：台账里的每一次写，都必须来自契约里声明为写的步骤。"""
    declared = {s.get(model.S_ID) for s in model.write_steps(contract)}
    stray = [x for x in state.写动作台账 if x.get("步骤") not in declared]
    if stray:
        return "出现未声明为写的写动作：%s" % stray
    return None


# ─────────────────────────── G4 写步骤确认 ───────────────────────────
def plan_for(step, state):
    """dry-run 计划：把这条写步骤**本来要做什么**列出来（不含任何凭据）。"""
    plan = {"步骤": step.get(model.S_ID), "动作": step.get(model.S_ACTION),
            "操作": step.get(model.S_OPERATION) or step.get(model.S_COMMAND),
            "说明": step.get(model.S_DESC), "已执行": False}
    for k in ("路径", "内容", "命令", "参数"):
        if step.get(k) is not None:
            plan[k] = state.expand(step[k])
    return plan


# ─────────────────────────── G5 回读校验 ───────────────────────────
def readback_of(step):
    return (step or {}).get(model.S_READBACK) or {}


def not_written_problem(step, state):
    """被拦下的写步骤：回读目标必须**不存在**（这就是"无任何写发生"的证据）。

    返回 `(问题 或 None, 明细)`：问题非空即回读校验不通过（写发生了但对不上）。
    """
    rb = readback_of(step)
    raw = rb.get(model.A_VALUE)
    try:
        target = state.expand(raw)
    except Exception:                                                   # noqa: BLE001
        return "回读目标表达式无法解析：%r" % (raw,), ""
    if not isinstance(target, str):
        return "回读目标必须是路径：%r" % (target,), ""
    if os.path.exists(target):
        return "被拦下的写步骤却留下了目标：%s" % target, ""
    return None, "回读：目标不存在（%s），证明未写入" % target
