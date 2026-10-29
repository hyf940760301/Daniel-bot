# -*- coding: utf-8 -*-
"""契约校验器（TICKET-146 §2 任务内容 2；D3 裁决的落地处；TICKET-152 写权限口径）。

挡的是四类结构性缺陷：

  ① **格式不全**：八项必填字段缺一（输入／前置／步骤／判据／门禁／交付件schema／自检／失败模式）；
  ② **幻觉命令**（D3）：步骤引用了 `schema.py` 里**不存在的命令或参数** —— 契约与 CLI 单一真源
     焊死，新增能力必须先在 `schema.py` 登记，契约不可能"自己发明一条命令"；
  ③ **装饰性声明**：门禁少声明一道、失败模式没有落到任何机制上、写步骤没有回读断言、
     判据引用了不存在的步骤/输入/限额 —— 这些在运行期都拦不住，必须在校验期报出来；
  ④ **写步骤没说清写哪个模块**（TICKET-152）：写链开放与否按**账号对该模块的写权限**判
     （账号的使用权限，不是审批），模块认不出来就核不了权限。静态可判的部分（模块缺没缺、
     在不在 `schema.py` 里）在本文件报出；"当前账号到底有没有该模块的写权限"是运行期门禁
     「写权限」的事（`gates.py` ＋ `daniel_cli/permissions.py`），校验期不做账号假设。

校验通过 ≠ 跑得通：运行期还会再核一遍（`executor.py`），两处口径同源（都读 `model.py`）。
"""
import ast
import re

from .. import schema as cli_schema
from . import actions, assertions, deliverable, gates, model

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

#: `运行.*` / `交付件.*` / `契约.*` 的静态字段表（写错即报，不靠运行期）
RUN_FIELDS = model.RUN_FIELDS
DELIVERABLE_FIELDS = ("状态", "名称", "路径", "行数", "列", "必填列", "校验", "明细", "数据",
                      # TICKET-175 出件模板：交付物工厂对外暴露的可断言事实
                      "格式", "落点", "文件名", "sha256", "文件行数", "文件表头数",
                      "入池行数", "出件行数", "剔除行数", "列数",
                      "非占位计数", "占位计数", "去重计数", "关键桶", "计数对账",
                      "出件自检", "写后对账", "阶梯", "判据全过后行数", "产物", "附表",
                      "违规", "违规数",
                      # TICKET-186 · A4 印刷级 PDF 出件：文档型出件多暴露两段事实
                      # （PDF 保真＝A4／叠字／md↔PDF 三条的实测值；可复制版＝随件落的 .md）
                      "PDF 保真", "可复制版")
CONTRACT_FIELDS = ("id", "名称", "版本", "路径", "示例", "含写步骤")
STEP_FIELDS = ("状态", "动作", "操作", "命令", "退出码", "条目数", "数据", "路径",
               "内容", "存在", "模块", "明细", "耗时毫秒")


def _problems():
    return []


def _item_problems(items, get_id, where, problems):
    """列表项：必须是对象、id 唯一、有说明。"""
    seen = set()
    for i, it in enumerate(items or []):
        if not isinstance(it, dict):
            problems.append("%s第 %d 项必须是对象" % (where, i + 1))
            continue
        sid = get_id(it)
        if not sid:
            problems.append("%s第 %d 项缺 id" % (where, i + 1))
        elif sid in seen:
            problems.append("%s里 id 重复：%s" % (where, sid))
        else:
            seen.add(sid)
    return seen


def _check_list_field(contract, field, problems):
    v = contract.get(field)
    if not isinstance(v, list):
        problems.append("`%s` 必须是数组" % field)
        return []
    return v


# ─────────────────────────── ① 顶层字段 ───────────────────────────
def check_fields(contract):
    p = _problems()
    for f in model.REQUIRED_FIELDS:
        if f not in contract:
            p.append("缺必填字段：`%s`" % f)
    for f in contract:
        if f not in model.ALL_FIELDS:
            p.append("不认识字段：`%s`（可用：%s）" % (f, "／".join(model.ALL_FIELDS)))
    if contract.get(model.F_VERSION) != model.CONTRACT_VERSION:
        p.append("`%s` 必须是 %s（当前 %r）"
                 % (model.F_VERSION, model.CONTRACT_VERSION, contract.get(model.F_VERSION)))
    cid = contract.get(model.F_ID)
    if not isinstance(cid, str) or not ID_RE.match(cid or ""):
        p.append("`%s` 必须是小写字母/数字/点/横线组成的标识（当前 %r）" % (model.F_ID, cid))
    for f in (model.F_NAME, model.F_SUMMARY):
        if not isinstance(contract.get(f), str) or not contract.get(f).strip():
            p.append("`%s` 必须是非空文本" % f)
    for f in model.EIGHT_FIELDS:
        if f == model.F_DELIVERABLE:
            if f in contract and not isinstance(contract[f], dict):
                p.append("`%s` 必须是对象" % f)
            continue
        if f in contract:
            _check_list_field(contract, f, p)
    if model.F_LIMITS in contract and not isinstance(contract[model.F_LIMITS], dict):
        p.append("`%s` 必须是对象（键是上限名）" % model.F_LIMITS)
    if model.F_EXPECT in contract and not isinstance(contract[model.F_EXPECT], dict):
        p.append("`%s` 必须是对象" % model.F_EXPECT)
    # `需要联网`（TICKET-153 · 方案 A）：必须是布尔 —— 写别的值（"true"、1、null）会让
    # selfcheck 的跳过判定静默失真，所以在这里挡掉。
    if model.F_NEEDS_NETWORK in contract and not isinstance(contract[model.F_NEEDS_NETWORK], bool):
        p.append("`%s` 必须是布尔（true/false），当前 %r"
                 % (model.F_NEEDS_NETWORK, contract[model.F_NEEDS_NETWORK]))
    return p


# ─────────────────────────── ② 输入与限额 ───────────────────────────
def check_inputs(contract):
    p = _problems()
    names = _item_problems(contract.get(model.F_INPUTS), lambda x: x.get("名称"),
                           "输入：", p)
    for it in contract.get(model.F_INPUTS) or []:
        if not isinstance(it, dict):
            continue
        t = it.get("类型", "str")
        if t not in cli_schema.OPTION_TYPES:
            p.append("输入「%s」的类型 %r 不认识（可用：%s）"
                     % (it.get("名称"), t, "／".join(cli_schema.OPTION_TYPES)))
        if not isinstance(it.get("说明", ""), str) or not it.get("说明"):
            p.append("输入「%s」缺 `说明`" % it.get("名称"))
        # 账号上下文输入（TICKET-152）：写权限判定要拿它造快照，取值必须是文本，
        # 否则"账号角色=admin"这类声明会被类型转换悄悄改写成别的值。
        if it.get("名称") in model.ACCOUNT_INPUTS and t != "str":
            p.append("输入「%s」是账号上下文输入，类型必须是 str（当前 %r）——"
                     "它的取值直接进写权限判定" % (it.get("名称"), t))
    return p, names


def check_limits(contract):
    p = _problems()
    rows = model.limit_rows(contract)
    step_ids = {s.get(model.S_ID) for s in contract.get(model.F_STEPS) or []
                if isinstance(s, dict)}
    if not rows:
        p.append("`%s` 不能为空：样本模式必须有上限（超限报错、不静默截断）" % model.F_LIMITS)
    for name, spec in rows.items():
        for k in (model.L_DEFAULT, model.L_HARD):
            v = spec.get(k)
            if not isinstance(v, int) or isinstance(v, bool) or v < 1:
                p.append("限额「%s」的 `%s` 必须是正整数（当前 %r）" % (name, k, v))
        if isinstance(spec.get(model.L_DEFAULT), int) and isinstance(spec.get(model.L_HARD), int) \
                and spec[model.L_HARD] < spec[model.L_DEFAULT]:
            p.append("限额「%s」的 `%s` 不能小于 `%s`" % (name, model.L_HARD, model.L_DEFAULT))
        if spec.get(model.L_STEPS) and spec[model.L_STEPS] not in step_ids:
            p.append("限额「%s」的 `%s` 指向不存在的步骤：%s"
                     % (name, model.L_STEPS, spec[model.L_STEPS]))
    return p, rows


# ─────────────────────────── ③ 步骤（D3：与单一真源联动） ───────────────────────────
def _check_command_step(step, where, p):
    raw = step.get(model.S_COMMAND)
    if not isinstance(raw, str) or len(raw.split()) != 2:
        p.append("%s：`%s` 必须写成「<模块> <子命令>」（当前 %r）" % (where, model.S_COMMAND, raw))
        return None
    mod_key, cmd_name = raw.split()
    cmd = cli_schema.find_command(mod_key, cmd_name)
    if cmd is None:
        p.append("%s：`%s` 引用了 schema 里不存在的命令「%s」（D3：契约只能引用已声明的命令；"
                 "先加到 daniel_cli/schema.py）" % (where, model.S_COMMAND, raw))
        return None
    if cmd["write"]:
        p.append("%s：`%s` 引用了写操作命令「%s」——契约引擎的写动作只允许沙箱内的离线假动作；"
                 "真实写请走 daniel CLI 的写命令（带 --confirm，删除类再加 --delete-token）"
                 % (where, model.S_COMMAND, raw))
    declared = {o["name"]: o for o in cmd["options"]}
    params = step.get(model.S_PARAMS) or {}
    if not isinstance(params, dict):
        p.append("%s：`%s` 必须是对象（键是参数名）" % (where, model.S_PARAMS))
        params = {}
    for k, v in params.items():
        if k not in declared:
            p.append("%s：命令「%s」没有参数 `%s`（可用：%s）"
                     % (where, raw, k, "／".join(sorted(declared)) or "无"))
            continue
        opt = declared[k]
        if opt["type"] == "flag":
            if not isinstance(v, bool):
                p.append("%s：参数 `%s` 是开关，取值必须是 true/false（当前 %r）" % (where, k, v))
        elif isinstance(v, bool):
            p.append("%s：参数 `%s` 是取值型参数，不能用布尔" % (where, k))
        elif opt["type"] == "int" and not isinstance(v, int) and not _is_ref(v):
            p.append("%s：参数 `%s` 需要整数（当前 %r）" % (where, k, v))
        elif opt["type"] == "choice" and v not in (opt["choices"] or []) and not _is_ref(v):
            p.append("%s：参数 `%s` 只能取 %s（当前 %r）"
                     % (where, k, "／".join(opt["choices"] or []), v))
    missing = [o["name"] for o in cmd["options"] if o["required"] and o["name"] not in params]
    if missing:
        p.append("%s：命令「%s」缺必填参数：%s" % (where, raw, "／".join(missing)))
    # 读/写标记必须与单一真源一致
    if model.S_WRITE in step and bool(step[model.S_WRITE]) != bool(cmd["write"]):
        p.append("%s：`%s` 标为 %s，但 schema 里「%s」是%s操作 —— 两处口径不一致"
                 % (where, model.S_WRITE, "写" if step[model.S_WRITE] else "读",
                    raw, "写" if cmd["write"] else "读"))
    return cmd


def _is_ref(v):
    return isinstance(v, str) and (assertions.REF_RE.match(v) or "${" in v)


def _check_fixture_step(step, where, p):
    op = step.get(model.S_OPERATION)
    spec = actions.FIXTURE_ACTIONS.get(op)
    if spec is None:
        p.append("%s：`%s` 引用了未注册的本地假动作 %r（可用：%s）"
                 % (where, model.S_OPERATION, op, "／".join(actions.action_names())))
        return
    for key in spec["必需"]:
        if step.get(key) in (None, ""):
            p.append("%s：本地假动作「%s」缺参数 `%s`" % (where, op, key))
    if model.S_WRITE in step and bool(step[model.S_WRITE]) != bool(spec["写"]):
        p.append("%s：本地假动作「%s」是%s动的，但步骤标为%s"
                 % (where, op, "写" if spec["写"] else "读",
                    "写" if step.get(model.S_WRITE) else "读"))


def check_steps(contract):
    p = _problems()
    steps = contract.get(model.F_STEPS) or []
    ids = _item_problems(steps, lambda x: x.get(model.S_ID), "步骤：", p)
    # 写步骤必须能解析出所属模块：权限是按模块判的（TICKET-152），认不出模块就核不了权限。
    # 这里只做静态可判的部分；**账号有没有该模块的写权限**是运行期的事（见 gates/executor）。
    p += gates.module_problems(contract)
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        sid = step.get(model.S_ID) or ("#%d" % (i + 1))
        where = "步骤 %s" % sid
        if not step.get(model.S_DESC):
            p.append("%s：缺 `说明`" % where)
        if model.S_WRITE not in step or not isinstance(step.get(model.S_WRITE), bool):
            p.append("%s：必须显式声明 `%s`（读链默认零写，写步骤要走三段门禁）"
                     % (where, model.S_WRITE))
        act = step.get(model.S_ACTION)
        if act not in model.STEP_ACTIONS:
            p.append("%s：`%s` 只能是 %s（当前 %r）"
                     % (where, model.S_ACTION, "／".join(model.STEP_ACTIONS), act))
            continue
        if act == model.ACT_CALL:
            _check_command_step(step, where, p)
        else:
            _check_fixture_step(step, where, p)
            # `合并子表` 的来源步骤必须存在、且声明在它**之前**（顺序反了运行期必然失败）
            if step.get(model.S_OPERATION) == actions.A_MERGE_ROWS:
                refs = step.get("来源步骤")
                refs = [refs] if isinstance(refs, str) else (refs or [])
                for ref in refs:
                    if not isinstance(ref, str) or not ref.strip():
                        p.append("%s：`来源步骤` 里有空项" % where)
                        continue
                    if ref not in ids:
                        p.append("%s：`来源步骤` 指向不存在的步骤：%s" % (where, ref))
                    elif ref not in {s.get(model.S_ID) for s in steps[:i]}:
                        p.append("%s：`来源步骤` 的 %s 声明在它之后（拼接顺序必须自前向后）"
                                 % (where, ref))
                extra = step.get("加列") or {}
                if isinstance(extra, dict):
                    for col, values in extra.items():
                        if not isinstance(values, list) or len(values) != len(refs):
                            p.append("%s：`加列.%s` 必须与 `来源步骤` 等长（%d 个来源）"
                                     % (where, col, len(refs)))
        if step.get(model.S_WRITE):
            rb = step.get(model.S_READBACK)
            if not isinstance(rb, dict):
                p.append("%s：写步骤必须声明 `%s` 断言（dry-run → 确认 → 执行 → **回读校验**，"
                         "缺回读等于没验证）" % (where, model.S_READBACK))
            else:
                assertions.check_spec(rb, "%s 回读" % where, p)
        elif isinstance(step.get(model.S_READBACK), dict):
            assertions.check_spec(step[model.S_READBACK], "%s 回读" % where, p)
    return p, ids


# ─────────────────────────── ④ 门禁 ───────────────────────────
def check_gates(contract):
    p = _problems()
    gates = contract.get(model.F_GATES) or []
    _item_problems(gates, lambda x: x.get(model.S_ID), "门禁：", p)
    declared_types = []
    for g in gates:
        if not isinstance(g, dict):
            continue
        t = g.get(model.S_ID)
        if t not in model.GATE_TYPES:
            p.append("门禁「%s」不是引擎内置门禁（可用：%s）" % (t, "／".join(model.GATE_TYPES)))
            continue
        declared_types.append(t)
        if not g.get(model.S_DESC):
            p.append("门禁「%s」缺 `说明`" % t)
    for t in model.MANDATORY_GATE_TYPES:
        if t not in declared_types:
            p.append("门禁少声明一道：`%s`（引擎内置门禁必须全部声明，不允许静默放弃）" % t)
    return p


# ─────────────────────────── ⑤ 交付件 schema / 自检 / 失败模式 / 期望 ───────────────────────────
def check_deliverable(contract, step_ids):
    p = _problems()
    d = contract.get(model.F_DELIVERABLE) or {}
    if not isinstance(d, dict):
        return p
    for k in (model.D_NAME, model.D_FILE, model.D_SOURCE, model.D_COLUMNS,
              model.D_REQUIRED_COLUMNS):
        if not d.get(k):
            p.append("`%s` 缺 `%s`" % (model.F_DELIVERABLE, k))
    src = d.get(model.D_SOURCE)
    if src and src not in step_ids:
        p.append("`%s.来源步骤` 指向不存在的步骤：%s" % (model.F_DELIVERABLE, src))
    if not deliverable.is_template(d):
        # ── 遗留式（没声明 `格式`）：口径与行为一个字没变 ──
        cols, req = d.get(model.D_COLUMNS) or [], d.get(model.D_REQUIRED_COLUMNS) or []
        if not isinstance(cols, list) or not cols:
            p.append("`%s.列` 必须是非空数组" % model.F_DELIVERABLE)
        if not isinstance(req, list):
            p.append("`%s.必填列` 必须是数组" % model.F_DELIVERABLE)
        for c in req if isinstance(req, list) else []:
            if c not in cols:
                p.append("`%s.必填列` 里的「%s」不在 `列` 里" % (model.F_DELIVERABLE, c))
        ref = d.get(model.D_ROW_LIMIT)
        if ref and ref not in model.limit_rows(contract):
            p.append("`%s.行数上限引用` 指向不存在的限额：%s" % (model.F_DELIVERABLE, ref))
        return p
    p += _check_template(d, contract, step_ids)
    return p


# ═══════════ 出件模板（TICKET-175 · 交付物工厂）的静态校验 ═══════════
# 票面 A 的三条硬要求落在这里：**缺字段、排序键不存在、必填列与「无数据写法」缺失 → 报错**。
# 校验期挡住的东西越多，运行期就越不可能"出一份看着齐全、其实缺列少判据的件"。
def _check_template(d, contract, step_ids):
    p = _problems()
    where = "`%s`" % model.F_DELIVERABLE
    spec = deliverable.normalize_spec(d)
    cols = spec["列"]

    # ① 格式
    if spec["格式"] not in model.FORMATS:
        p.append("%s.`%s` 只能是 %s（当前 %r）"
                 % (where, model.D_FORMAT, "／".join(model.FORMATS), spec["格式"]))

    # ② 列与必填列
    names = []
    for i, c in enumerate(cols, 1):
        if not c.get("列名") or not isinstance(c.get("列名"), str):
            p.append("%s.`%s` 第 %d 项缺 `列名`" % (where, model.D_COLUMNS, i))
            continue
        names.append(c["列名"])
        kind, arg = deliverable.source_field(c)
        if kind is None:
            p.append("%s.`%s` 的「%s」`来源` 写法不认识（可用：字段名字符串／"
                     "`{%s:表达式}`／`{%s:${列名}}`／`{%s:排名|点名位置}`）"
                     % (where, model.D_COLUMNS, c["列名"], model.SRC_COMPUTE, model.SRC_TEMPLATE,
                        model.SRC_GENERATE))
        if kind == model.SRC_COMPUTE:
            # 计算列按**列名**求值，被引用的列必须声明在它前面（列顺序就是求值顺序）
            try:
                tree = ast.parse(str(arg), mode="eval")
                used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
            except SyntaxError as e:
                p.append("%s.`%s` 的「%s」表达式语法错误：%s" % (where, model.D_COLUMNS,
                                                        c["列名"], e))
                used = set()
            before = set(names[:names.index(c["列名"])]) if c["列名"] in names else set()
            for ref in sorted(used - before):
                p.append("%s.`%s` 的「%s」`%s` 引用了不在它之前的列「%s」"
                         % (where, model.D_COLUMNS, c["列名"], model.SRC_COMPUTE, ref))
        if kind == model.SRC_TEMPLATE:
            for ref in re.findall(r"\$\{([^}]+)\}", str(arg)):
                if ref not in names:
                    p.append("%s.`%s` 的「%s」`%s` 引用了不在它之前的列「%s」"
                             % (where, model.D_COLUMNS, c["列名"], model.SRC_TEMPLATE, ref))
        if kind == model.SRC_GENERATE and arg not in (model.GEN_RANK, model.GEN_MENTION):
            p.append("%s.`%s` 的「%s」生成了不认识的东西：%r（可用：%s／%s）"
                     % (where, model.D_COLUMNS, c["列名"], arg, model.GEN_RANK, model.GEN_MENTION))
        if c.get("格式") not in (None, "", "文本", "整数", "百分比", "百分数", "数字"):
            p.append("%s.`%s` 的「%s」`格式` 不认识：%r" % (where, model.D_COLUMNS, c["列名"],
                                                       c.get("格式")))
    dup = sorted({x for x in names if names.count(x) > 1})
    if dup:
        p.append("%s.`%s` 有重复列名：%s" % (where, model.D_COLUMNS, "／".join(dup)))
    for c in spec["必填列"]:
        if c not in names:
            p.append("%s.`%s` 里的「%s」不在 `列` 里" % (where, model.D_REQUIRED_COLUMNS, c))
    for c in spec["不得占位列"]:
        if c not in names:
            p.append("%s.`%s` 里的「%s」不在 `列` 里" % (where, model.D_NO_NULL_COLUMNS, c))

    # ③ 排序（票面 A：排序键与方向必须写进模板；排序键不存在 → 报错）
    if not spec["排序"]:
        p.append("%s 声明了 `%s`（模板式出件）就必须声明 `%s`：排序键与方向"
                 % (where, model.D_FORMAT, model.D_SORT))
    for i, s in enumerate(spec["排序"], 1):
        if not isinstance(s, dict):
            p.append("%s.`%s` 第 %d 项必须是对象" % (where, model.D_SORT, i))
            continue
        key, direction = s.get("键"), s.get("方向")
        if not key:
            p.append("%s.`%s` 第 %d 项缺 `键`" % (where, model.D_SORT, i))
        elif key not in names:
            p.append("%s.`%s` 的排序键「%s」不在 `列` 里（排序键不存在＝排序无从验证）"
                     % (where, model.D_SORT, key))
        if direction not in model.SORT_DIRECTIONS:
            p.append("%s.`%s` 的「%s」方向只能是 %s（当前 %r）"
                     % (where, model.D_SORT, key or i, "／".join(model.SORT_DIRECTIONS), direction))

    # ④ 无数据写法（票面 A：缺失即报错 —— 没有它就没法区分"没数据"和"漏填"）
    if not isinstance(d.get(model.D_NULL_TEXT), str) or not d.get(model.D_NULL_TEXT, "").strip():
        p.append("%s 声明了 `%s` 就必须声明 `%s`（无数据时的统一写法；Skill §15.5.5 判据2："
                 "无公开数据的字段写「无官方数据」，不留空）"
                 % (where, model.D_FORMAT, model.D_NULL_TEXT))

    # ⑤ 行判据（逐字取自 Skill；每条必须带出处）
    if not spec["行判据"]:
        p.append("%s 声明了 `%s` 就必须声明 `%s`（行的准入判据，逐字取自 Skill 并带出处）"
                 % (where, model.D_FORMAT, model.D_ROW_CRITERIA))
    seen = set()
    for i, c in enumerate(spec["行判据"], 1):
        if not isinstance(c, dict):
            p.append("%s.`%s` 第 %d 项必须是对象" % (where, model.D_ROW_CRITERIA, i))
            continue
        cid = c.get(model.CRC_ID)
        tag = "%s.`%s` %s" % (where, model.D_ROW_CRITERIA, cid or "#%d" % i)
        if not cid:
            p.append("%s 缺 `id`" % tag)
        elif cid in seen:
            p.append("%s `id` 重复" % tag)
        else:
            seen.add(cid)
        for k in (model.CRC_DESC, model.CRC_RELATION, model.CRC_SOURCE):
            if not c.get(k):
                p.append("%s 缺 `%s`" % (tag, k))
        rel = c.get(model.CRC_RELATION)
        if rel and rel not in model.ROW_RELATIONS:
            p.append("%s 的 `%s` 不认识：%r（可用：%s）"
                     % (tag, model.CRC_RELATION, rel, "／".join(model.ROW_RELATIONS)))
            continue
        field = c.get(model.CRC_FIELD)
        if rel != model.REL_DEDUP or True:
            if not field:
                p.append("%s 缺 `%s`" % (tag, model.CRC_FIELD))
            elif field not in names:
                p.append("%s 的 `%s`「%s」不在 `列` 里" % (tag, model.CRC_FIELD, field))
        if rel in model.RELATION_NEEDS_THRESHOLD and c.get(model.CRC_THRESHOLD) is None:
            p.append("%s（%s）缺 `%s`" % (tag, rel, model.CRC_THRESHOLD))
        if rel == model.REL_MENTION:
            words = c.get(model.CRC_WORDS)
            neg = c.get(model.CRC_NEGATIVE)
            if not isinstance(words, list) or not words:
                p.append("%s（点名至品牌）缺 `%s`（品牌／产品名词表，取自 Skill）"
                         % (tag, model.CRC_WORDS))
            if not isinstance(neg, list) or not neg:
                p.append("%s（点名至品牌）缺 `%s`（否定句词表 —— 否定句是负证据，"
                         "Skill §15.5.4 规则2）" % (tag, model.CRC_NEGATIVE))
            for hint in c.get(model.CRC_HINT_FIELDS) or []:
                if hint not in names:
                    p.append("%s 的 `%s` 里的「%s」不在 `列` 里" % (tag, model.CRC_HINT_FIELDS, hint))
        if rel == model.REL_DEDUP:
            mx = c.get(model.CRC_MAX)
            if not mx:
                p.append("%s（按视频去重取最高）缺 `%s`" % (tag, model.CRC_MAX))
            elif mx not in names:
                p.append("%s 的 `%s`「%s」不在 `列` 里" % (tag, model.CRC_MAX, mx))

    # ⑥ 判据出处（票面 B：每条判据都要能指到 Skill 的章节与行号）
    srcs = spec["判据出处"]
    if not srcs:
        p.append("%s 声明了 `%s` 就必须声明 `%s`（判据 → Skill 章节／行号，便于回查）"
                 % (where, model.D_FORMAT, model.D_SOURCES))
    for i, s in enumerate(srcs, 1):
        if not isinstance(s, dict) or not s.get("判据") or not s.get("出处"):
            p.append("%s.`%s` 第 %d 项必须同时有 `判据` 与 `出处`（缺一即无法回查）"
                     % (where, model.D_SOURCES, i))
            continue
        if s["判据"] not in seen:
            p.append("%s.`%s` 的「%s」不是本模板里的行判据 id" % (where, model.D_SOURCES, s["判据"]))

    # ⑦ 计数对账与关键桶（票面 C②⑤：引用必须可解析 —— 静态可判的部分不留给运行期）
    if not spec["计数对账"]:
        p.append("%s 声明了 `%s` 就必须声明 `%s`（主表行数 == 出件文件行数；入池 ≥ 出件）"
                 % (where, model.D_FORMAT, model.D_RECONCILE))
    for i, r in enumerate(spec["计数对账"], 1):
        tag = "%s.`%s` %s" % (where, model.D_RECONCILE, (r or {}).get(model.CRC_ID) or "#%d" % i)
        if not isinstance(r, dict) or not r.get(model.CRC_ID):
            p.append("%s 缺 `id`" % tag)
            continue
        rel = r.get(model.CRC_RELATION)
        if rel not in (model.REL_EQ, model.REL_GE):
            p.append("%s 的 `%s` 只能是 %s／%s（当前 %r）"
                     % (tag, model.CRC_RELATION, model.REL_EQ, model.REL_GE, rel))
        for side in (model.CRC_LEFT, model.CRC_RIGHT):
            ref = r.get(side)
            if not ref:
                p.append("%s 缺 `%s`" % (tag, side))
            else:
                _check_deliverable_ref(ref, names, contract, step_ids, tag, p)
        if rel == model.REL_GE and not r.get(model.CRC_DELTA):
            p.append("%s 用了「%s」＝入池 ≥ 出件，必须写 `%s`（差额怎么解释）"
                     % (tag, model.REL_GE, model.CRC_DELTA))

    if not spec["关键桶"]:
        p.append("%s 声明了 `%s` 就必须声明 `%s`（关键桶非 0 是出件自检的第五条）"
                 % (where, model.D_FORMAT, model.D_BUCKETS))
    for i, b in enumerate(spec["关键桶"], 1):
        tag = "%s.`%s` %s" % (where, model.D_BUCKETS, (b or {}).get(model.CRC_BUCKET) or "#%d" % i)
        if not isinstance(b, dict) or not b.get(model.CRC_BUCKET):
            p.append("%s 缺 `%s`" % (tag, model.CRC_BUCKET))
            continue
        ref = b.get(model.CRC_VALUE)
        if not ref:
            p.append("%s 缺 `%s`" % (tag, model.CRC_VALUE))
        else:
            _check_deliverable_ref(ref, names, contract, step_ids, tag, p)
        floor = b.get(model.CRC_FLOOR, 1)
        if not isinstance(floor, int) or isinstance(floor, bool) or floor < 1:
            p.append("%s 的 `%s` 必须是 ≥1 的整数（桶为 0 就该拦下）" % (tag, model.CRC_FLOOR))

    # ⑧ 附表（说明与口径）
    for i, tab in enumerate(spec["附表"], 1):
        tag = "%s.`%s` 第 %d 项" % (where, model.D_EXTRA, i)
        if not isinstance(tab, dict):
            p.append("%s 必须是对象" % tag)
            continue
        for k in ("名称", "文件名", "格式", "生成"):
            if not tab.get(k):
                p.append("%s 缺 `%s`" % (tag, k))
        if tab.get("格式") and tab["格式"] not in model.FORMATS:
            p.append("%s 的 `格式` 只能是 %s" % (tag, "／".join(model.FORMATS)))
        for gen in tab.get("生成") or []:
            if gen not in deliverable.EXTRA_GENERATORS:
                p.append("%s 的生成器 %r 不认识（可用：%s）"
                         % (tag, gen, "／".join(deliverable.EXTRA_GENERATORS)))
    # ⑨ 行数上限引用
    ref = spec["行数上限引用"]
    if ref and ref not in model.limit_rows(contract):
        p.append("%s.`%s` 指向不存在的限额：%s" % (where, model.D_ROW_LIMIT, ref))
    return p


def _check_deliverable_ref(ref, col_names, contract, step_ids, tag, p):
    """对账／关键桶里的取值引用必须静态可解析（防"写了个不存在的字段，运行期才发现"）。"""
    if not isinstance(ref, str) or "." not in ref:
        p.append("%s 的取值引用 `%s` 写法不合法（形如 `交付件.行数`）" % (tag, ref))
        return
    root, rest = ref.split(".", 1)
    parts = rest.split(".")
    if root == "交付件":
        head = parts[0]
        if head not in DELIVERABLE_FIELDS:
            p.append("%s 引用 `%s` 的字段 `%s` 不是已知字段（可用：%s）"
                     % (tag, ref, head, "／".join(DELIVERABLE_FIELDS)))
            return
        if head in ("非占位计数", "占位计数", "去重计数") and (
                len(parts) < 2 or parts[1] not in col_names):
            p.append("%s 引用 `%s` 的列 `%s` 不在 `列` 里" % (tag, ref, parts[1] if len(parts) > 1
                                                        else ""))
        return
    if root == "步骤":
        if parts[0] not in step_ids:
            p.append("%s 引用 `%s` 指向不存在的步骤：%s" % (tag, ref, parts[0]))
        return
    if root == "限额":
        if parts[0] not in model.limit_rows(contract):
            p.append("%s 引用 `%s` 指向不存在的限额：%s" % (tag, ref, parts[0]))
        return
    if root == "输入":
        names = {i.get("名称") for i in contract.get(model.F_INPUTS) or [] if isinstance(i, dict)}
        if parts[0] not in names:
            p.append("%s 引用 `%s` 指向不存在的输入：%s" % (tag, ref, parts[0]))
        return
    p.append("%s 引用 `%s` 的前缀 `%s` 不可用（出件对账只认 交付件／步骤／限额／输入）"
             % (tag, ref, root))


def check_checks(contract, root_refs):
    """前置／判据／自检：断言合法 + 引用可解析（防幻觉引用）。

    允许 `当` 条件：条件不成立时该条记「跳过」而不是静默通过（退出码 3 与 0 两条路径
    可以用同一个契约自证，见 `contracts/_examples/`）。
    """
    p = _problems()
    for field in (model.F_PRECONDITIONS, model.F_CRITERIA, model.F_SELFCHECKS):
        items = contract.get(field) or []
        _item_problems(items, lambda x: x.get(model.S_ID), "%s：" % field, p)
        for it in items:
            if not isinstance(it, dict):
                continue
            where = "%s %s" % (field, it.get(model.S_ID) or "?")
            if not it.get(model.S_DESC):
                p.append("%s：缺 `说明`" % where)
            assertions.check_spec(it.get("断言"), where, p)
            _check_refs(it.get("断言") or {}, root_refs, where, p)
            if it.get(model.F_WHEN) is not None:
                if not isinstance(it[model.F_WHEN], dict):
                    p.append("%s：`%s` 必须是断言对象" % (where, model.F_WHEN))
                else:
                    assertions.check_spec(it[model.F_WHEN], "%s 条件" % where, p)
                    _check_refs(it[model.F_WHEN], root_refs, "%s 条件" % where, p)
            if field == model.F_SELFCHECKS and it.get("必过") not in (True, False):
                p.append("%s：自检项必须显式声明 `必过`（true/false）" % where)
    return p


def _collect_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            for s in _collect_strings(v):
                yield s
    elif isinstance(obj, list):
        for v in obj:
            for s in _collect_strings(v):
                yield s


def _check_refs(obj, root_refs, where, p):
    for s in _collect_strings(obj):
        cands = [s] if assertions.REF_RE.match(s) else []
        cands += [m.strip() for m in assertions.TPL_RE.findall(s)]
        for ref in cands:
            if not assertions.REF_RE.match(ref):
                p.append("%s：引用 `%s` 写法不合法（形如 `步骤.S1.条目数`）" % (where, ref))
                continue
            root, rest = ref.split(".", 1)
            parts = rest.split(".")
            allowed = root_refs.get(root)
            if allowed is not None and parts[0] not in allowed:
                p.append("%s：引用 `%s` 指向不存在的%s：%s"
                         % (where, ref, root, parts[0]))
            # 字段表校验的**取值位**随根不同（TICKET-175 修准）：
            #   `步骤.<id>.<字段>` 的第一段是**步骤 id**，字段在第二段；
            #   `运行.<字段>`／`交付件.<字段>`／`契约.<字段>` 的第一段**就是字段**。
            # 修之前一律取 `parts[1]`，于是 `运行.沙箱目录`／`交付件.行数` 这类两段引用
            # 压根没被查过（len(parts)==1 ⇒ 跳过），而 `交付件.写后对账.成立` 这种三段引用
            # 会去查「成立」这个不是字段的段 —— 一松一紧都量错了对象。
            if root in ("运行", "交付件", "契约", "步骤"):
                table = {"运行": RUN_FIELDS, "交付件": DELIVERABLE_FIELDS,
                         "契约": CONTRACT_FIELDS, "步骤": STEP_FIELDS}[root]
                idx = 1 if root == "步骤" else 0
                if len(parts) > idx and parts[idx] not in table:
                    p.append("%s：引用 `%s` 的字段 `%s` 不是已知字段（可用：%s）"
                             % (where, ref, parts[idx], "／".join(table)))


def check_steps_refs(contract, root_refs):
    """步骤参数／路径里的引用也要静态核一遍（模板写错不该等到运行期才发现）。"""
    p = _problems()
    for step in contract.get(model.F_STEPS) or []:
        if not isinstance(step, dict):
            continue
        where = "步骤 %s" % (step.get(model.S_ID) or "?")
        _check_refs(step.get(model.S_PARAMS) or {}, root_refs, where, p)
        for key in ("路径", "内容"):
            if step.get(key) is not None:
                _check_refs(step[key], root_refs, where, p)
        if isinstance(step.get(model.S_READBACK), dict):
            _check_refs(step[model.S_READBACK], root_refs, "%s 回读" % where, p)
    return p


def check_failure_modes(contract, mechanism_ids):
    """失败模式不能是装饰：每条必须落到一个真实机制（步骤／判据／门禁／自检）上。"""
    p = _problems()
    items = contract.get(model.F_FAILURE_MODES) or []
    if not items:
        p.append("`%s` 不能为空（取自既有缺陷类，实现必须覆盖）" % model.F_FAILURE_MODES)
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            p.append("失败模式第 %d 项必须是对象" % (i + 1))
            continue
        for k in ("缺陷类", "现象", "对策"):
            if not it.get(k):
                p.append("失败模式第 %d 项缺 `%s`" % (i + 1, k))
        tgt = str(it.get("对策") or "")
        if tgt and tgt not in mechanism_ids:
            p.append("失败模式「%s」的对策 `%s` 不是本契约里的机制（可用：步骤./判据./门禁./自检.<id>）"
                     % (it.get("缺陷类"), tgt))
    return p


def check_expect(contract, has_write):
    """`期望` 声明：默认路径必给；含写步骤的契约必须给全三条路径（默认／干跑／带确认）。

    P0-2 修正：引擎有三个运行开关（什么都不加／`--dry-run`／`--confirm`），
    三条路径都得有人验 —— 只声明两条的话，必有一条在自证里是空白。
    """
    p = _problems()
    exp = contract.get(model.F_EXPECT) or {}
    if not exp:
        p.append("`%s` 缺省项：默认路径必须声明期望结果与退出码（自证用）" % model.F_EXPECT)
        return p
    if model.E_DEFAULT not in exp:
        p.append("`%s` 必须声明 `%s` 路径" % (model.F_EXPECT, model.E_DEFAULT))
    if has_write:
        for path in (model.E_DRY, model.E_CONFIRMED):
            if path not in exp:
                p.append("含写步骤的契约必须声明 `%s` 路径（写链三段：什么都不加＝需确认、"
                         "`--dry-run`＝只出计划、`--confirm`＝执行并回读，三条都要自证）"
                         % (model.F_EXPECT + "." + path))
    for path, spec in exp.items():
        if path not in model.EXPECT_PATHS:
            p.append("`%s` 里有未知路径：%s（可用：%s）"
                     % (model.F_EXPECT, path, "／".join(model.EXPECT_PATHS)))
            continue
        if not isinstance(spec, dict):
            p.append("`%s.%s` 必须是对象" % (model.F_EXPECT, path))
            continue
        res, code = spec.get(model.E_RESULT), spec.get(model.E_EXIT)
        if res not in model.EXPECT_RESULTS:
            p.append("`%s.%s.结果` 只能是 %s（当前 %r）"
                     % (model.F_EXPECT, path, "／".join(model.EXPECT_RESULTS), res))
        want = {model.R_PASS: 0, model.R_FAIL: 1, model.R_BLOCK: 2, model.R_CONFIRM: 3}.get(res)
        if want is not None and code != want:
            p.append("`%s.%s` 的结果「%s」对应退出码 %d（当前 %r）"
                     % (model.F_EXPECT, path, res, want, code))
    # 三条路径的语义不能互相矛盾：默认与干跑都不执行写；带确认才执行
    dry = (exp.get(model.E_DRY) or {}).get(model.E_RESULT)
    default = (exp.get(model.E_DEFAULT) or {}).get(model.E_RESULT)
    if has_write and dry not in (None, model.R_CONFIRM, model.R_BLOCK, model.R_FAIL):
        p.append("`%s.%s.结果` 只能是「需确认」（`--dry-run` 不执行任何写），当前 %r"
                 % (model.F_EXPECT, model.E_DRY, dry))
    if has_write and default == model.R_PASS and dry == model.R_PASS:
        p.append("`%s`：默认与干跑两条路径都不执行写，结果不可能同时是「通过」" % model.F_EXPECT)
    return p


# ─────────────────────────── 入口 ───────────────────────────
def validate_contract(contract, path=None):
    """校验一份契约：返回 `{契约, 名称, 路径, 通过, 检查项[], 问题数, 问题[]}`。

    八项检查各记自己的问题，最后汇总 —— 报错要能指到"是哪一项不过"。
    """
    steps = contract.get(model.F_STEPS) or []
    step_ids = {s.get(model.S_ID) for s in steps if isinstance(s, dict) and s.get(model.S_ID)}
    input_names = {i.get("名称") for i in contract.get(model.F_INPUTS) or []
                   if isinstance(i, dict) and i.get("名称")}
    limit_names = set(model.limit_rows(contract))
    root_refs = {"输入": input_names, "限额": limit_names, "步骤": step_ids, "变量": None}

    pin, _names = check_inputs(contract)
    pl, _rows = check_limits(contract)
    ps, ids = check_steps(contract)
    mechanisms = set()
    for field, prefix in ((model.F_STEPS, "步骤"), (model.F_CRITERIA, "判据"),
                          (model.F_GATES, "门禁"), (model.F_SELFCHECKS, "自检")):
        for it in contract.get(field) or []:
            if isinstance(it, dict) and it.get(model.S_ID):
                mechanisms.add("%s.%s" % (prefix, it[model.S_ID]))

    # D3 相关的问题单独归到 D3 这一项（引用幻觉命令／参数／写路由）
    d3 = [x for x in ps if ("schema 里不存在的命令" in x or "写操作命令" in x
                            or "没有参数" in x or "缺必填参数" in x or "口径不一致" in x)]

    checks = [
        {"id": "F1", "说明": "八项字段齐备（输入／前置／步骤／判据／门禁／交付件schema／自检／失败模式）",
         "问题": check_fields(contract)},
        {"id": "F2", "说明": "输入与限额声明合法（上限为正整数、硬上限不低于默认）",
         "问题": pin + pl},
        {"id": "F3", "说明": "步骤声明合法：动作／写标记，且写步骤带回读断言",
         "问题": [x for x in ps if x not in d3]},
        {"id": "D3", "说明": "步骤只引用 schema.py 已声明的命令与参数（防幻觉命令）",
         "问题": d3},
        {"id": "F4", "说明": "门禁五道齐备（不允许静默放弃任何一道）",
         "问题": check_gates(contract)},
        {"id": "F5", "说明": "交付件 schema 与来源步骤自洽",
         "问题": check_deliverable(contract, ids)},
        {"id": "F6", "说明": "判据／自检／步骤参数里的取值引用可解析（防幻觉引用）",
         "问题": check_checks(contract, root_refs) + check_steps_refs(contract, root_refs)},
        {"id": "F7", "说明": "失败模式落到真实机制上 ＋ 期望结果与退出码自洽",
         "问题": check_failure_modes(contract, mechanisms)
                 + check_expect(contract, bool(model.write_steps(contract)))},
    ]
    for c in checks:
        c["通过"] = not c["问题"]
    problems = [x for c in checks for x in c["问题"]]
    return {"契约": contract.get(model.F_ID), "名称": contract.get(model.F_NAME),
            "路径": path, "通过": not problems, "检查项": checks,
            "问题数": len(problems), "问题": problems}
