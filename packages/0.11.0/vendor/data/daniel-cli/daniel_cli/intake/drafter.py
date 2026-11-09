# -*- coding: utf-8 -*-
"""工序契约草稿：把这次匹配到的工序落成一份**能给 `playbook validate` 过**的契约草稿。

用户裁决（2026-10-14 第 3 项）
-----------------------------
> 「匹配结果 → 生成一份"本次任务"的**工序契约草稿**（含本次输入／判据／交付件／门禁），
>   **用户确认后执行**；草稿必须能被 `playbook validate` 通过」

三条纪律
--------
① **不编造输入值**：能查到的（品牌等上下文）用真查到的值；查不到的（"人提供"）留**空占位**
   并在报告里单列「待你确认／补充」，绝不写一个看起来像真的假值；
② **步骤只引用真命令**：草稿的每一步都是工序表里声明过的 `daniel <模块> <子命令>`（只读），
   与 `schema.py` 单一真源焊死（引擎的 D3 判据会核对，这里先自己核对一遍）；
③ **交付件形状要真**：交付件从**真查到的产出**里取子表（键与列都来自实际返回），
   形状还没确证时如实把期望写成"失败／1"并说明怎么补，不假装能出件。

草稿落点（为什么不默认写进引擎的契约目录）
------------------------------------------
`playbook validate` 只在**契约目录**（`data/daniel-cli/contracts/`，可用 `DANIEL_CONTRACTS_DIR`
覆盖）里按文件名／id 找契约；而 `playbook selfcheck` 会把该目录里**每一份**契约按它声明的期望
各跑一遍 —— 每任务一份的数据依赖草稿留在那里，会让引擎自证变成一堆不确定断言。因此草稿默认落在
`data/daniel-cli/drafts/`（引擎目录之外），并在报告里给出**可直接粘贴的复核命令**：
`DANIEL_CONTRACTS_DIR=<草稿目录> daniel playbook validate <草稿文件名>`。
"""
import json
import os
import time

from ..exits import EXIT_USAGE
from ..runtime import CliError
from . import catalog, modes

#: 本包位置：`<仓库根>/data/daniel-cli/daniel_cli/intake/<本文件>` → 上溯三层是 `data/daniel-cli`
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DRAFT_DIR = os.path.join(_PKG_ROOT, "drafts")

#: 交付件行数上限（超限报错退出、不静默截断；硬上限给足，免得真实名单条目量被误伤）
LIMIT_DEFAULT = 500
LIMIT_HARD = 2000

#: 失败模式用到的既有缺陷类（与 `.kol-tools/check_defect_classes.py` 的登记表同源）
DEFECTS = ("CLS-65", "CLS-67", "CLS-72", "CLS-46", "CLS-76")

GATES = (
    ("样本上限", "超限报错退出、不静默截断（限额「行数上限」；--limit 行数上限=N 可覆盖，"
                "但不得超过硬上限）"),
    ("写权限", "本工序契约的取数步骤全是只读，没有写步骤；这道门禁不适用（写动作走 CLI 写命令，"
              "带 --confirm 人工确认后执行）"),
    ("只读默认", "读链默认零写：写动作只能来自契约里声明为写的步骤；本契约四类动作都是取数"),
    ("写步骤确认", "本契约没有写步骤，无需确认；若后续把回写动作并进本契约，必须走"
                  " dry-run → --confirm → 执行 → 回读"),
    ("回读校验", "写执行后必须回读核对；本契约无写，无回读对象"),
)


def draft_id(process):
    return "intake-%s" % process["工序键"]


def default_out(process):
    return os.path.join(DEFAULT_DRAFT_DIR, "%s.json" % draft_id(process))


def _params_of(process, piece_params, variables, overrides, problems):
    """把一条 `--brand <品牌>` 形式的参数文本变成契约 `参数` 对象（值是引用或字面量）。

    返回 `(参数 dict, 用到的输入名[], 未确定的占位符[])`。
    """
    from .. import schema as cli_schema
    from . import preflight as pf
    key, _ = piece_params
    text, missing = pf._substitute(piece_params[1], dict(variables, **overrides))
    required, optional = pf._split_optional(text)
    required, missing_req = pf._substitute(required, dict(variables, **overrides))
    still = catalog.placeholders_of(required) or list(missing_req)
    if still:
        return {}, [], still
    argv = pf._argv_of(required)
    spec = cli_schema.find_command(*key.split(".", 1)) or {"options": []}
    declared = {o["name"]: o for o in spec["options"]}
    params, used = {}, []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if not str(tok).startswith("--"):
            i += 1
            continue
        val = argv[i + 1] if i + 1 < len(argv) else None
        i += 2
        if val is None:
            continue
        opt = declared.get(tok)
        if opt is None:
            problems.append("参数 %s 不在命令「%s」的声明里（工序表里写错了？）" % (tok, key))
            continue
        ref = None
        for name, value in dict(variables, **overrides).items():
            if value not in (None, "") and str(value) == str(val):
                ref = "${输入.%s}" % name
                if name not in used:
                    used.append(name)
                break
        if ref:
            params[tok] = ref
        elif opt["type"] == "int":
            try:
                params[tok] = int(val)
            except ValueError:
                params[tok] = val
        elif opt["type"] == "flag":
            params[tok] = str(val).lower() in ("1", "true", "yes")
        else:
            params[tok] = val
    return params, used, []


def build(process, need="", brand=None, probing=None, inputs=None, out=None, mode=None):
    """生成一份本次任务的工序契约草稿。

    - `probing`：`preflight.Probe`（本次路由的取数器；带着它就能从**真实产出**里确证交付件形状）；
    - `inputs`：`{变量名: 值}`（你手上已经有的东西；会写进 `输入` 的默认值，并在说明里注明来源）；
    - 返回 `(契约 dict, 报告 dict)`；契约没生成出来时抛 `CliError`（用户错误，退出码 2）。
    """
    from . import preflight as pf
    need = str(need or "").strip()
    overrides = {str(k): str(v) for k, v in (inputs or {}).items()}
    brand_v = brand or overrides.get(pf.V_BRAND)
    problems, pending_steps = [], []
    variables = {pf.V_BRAND: brand_v}

    # ── 步骤：工序表里声明过的取数命令（只读），占位符能确定的才进步骤 ──
    steps, step_of_item, used_inputs = [], {}, []
    n = 0
    for item in process.get("前置条件") or []:
        if item["来源类型"] not in catalog.QUERYABLE_SOURCES:
            continue
        for piece in pf._command_pieces(item["取数方式"]):
            n += 1
            sid = "S%d" % n
            params, used, still = _params_of(process, piece, variables, overrides, problems)
            if still:
                pending_steps.append({
                    "取数方式": item["取数方式"], "缺的上下文": still,
                    "怎么补": "给出「%s」后重新生成草稿，它就会作为一步进契约"
                              "（也可以用 `--input %s=<值>`）" % ("、".join(still), still[0]),
                    "来源前置条件": item["名称"]})
                n -= 1
                continue
            for u in used:
                if u not in used_inputs:
                    used_inputs.append(u)
            steps.append({"id": sid, "说明": "%s（只读取数：daniel %s）"
                                          % (item["名称"], piece[0].replace(".", " ")),
                          "动作": "调用命令", "命令": piece[0].replace(".", " "),
                          "参数": params, "读": True, "写": False})
            step_of_item.setdefault(item["名称"], sid)

    if not steps:
        raise CliError("这次还生不出可用的草稿：本工序的取数步骤都缺上下文（%s）"
                       % ("、".join(sorted({x for p in pending_steps for x in p["缺的上下文"]}))
                          or "工序表里没有可调用的取数命令"),
                       code=EXIT_USAGE,
                       hint="先给出上下文（例如 `--brand <品牌名或编号>`）再生成草稿；"
                            "缺什么见 `daniel intake route --need \"…\"` 的前置条件清单")

    # ── 交付件：从真查到的产出里取子表（键与列都来自实际返回） ──
    shape, source_step, deliverable_note = _deliverable_shape(probing, steps)
    if shape:
        sid = "S%d" % (n + 1)
        steps.append({"id": sid, "说明": "从 %s 的产出里取出「%s」当本次交付件（原样搬运，"
                                       "不改一个字段）" % (shape["来源步骤"], shape["键"]),
                      "动作": "本地假动作", "操作": "取子表", "来源步骤": shape["来源步骤"],
                      "键": shape["键"], "读": True, "写": False})
        source_step = sid
        columns, required_cols = shape["列"], shape["必填列"]
        deliverable_note = ("交付件形状来自本次真查的产出（子表键「%s」，列取自实际返回）"
                            % shape["键"])
    else:
        source_step = steps[-1]["id"]
        columns, required_cols = ["序号", "条目", "来源"], ["序号", "条目"]
        deliverable_note = ("交付件形状还没确证（本次没有实查产出可用）：先把 `--probe` 打开"
                            "重启一次，形状确证后这里会换成真实子表与真实列")

    # ── 输入：人提供项留空占位；上下文变量（品牌等）用真查到的值 ──
    inputs_doc, todo, gate_inputs = [], [], []
    for name in [pf.V_BRAND] + [u for u in used_inputs if u != pf.V_BRAND]:
        value = variables.get(name) or overrides.get(name) or ""
        inputs_doc.append({"名称": name, "类型": "str", "必填": False, "默认": value,
                           "说明": ("本次任务的上下文（你给定了）" if value else
                                   "本次任务的上下文：请补上「%s」的值后再开工" % name)})
        gate_inputs.append(name)
        if not value:
            todo.append({"项": name, "类型": "上下文",
                         "怎么补": "生成草稿时给 `--input %s=<值>`，或直接在草稿里填 `默认`" % name})
    for item in process.get("前置条件") or []:
        if item["来源类型"] != catalog.SOURCE_HUMAN:
            continue
        value = overrides.get(item["名称"], "")
        inputs_doc.append({"名称": item["名称"], "类型": "str", "必填": False, "默认": value,
                           "说明": item["说明"] or "这一项系统里查不到，需要你提供"})
        gate_inputs.append(item["名称"])
        if not value:
            todo.append({"项": item["名称"], "类型": "人提供",
                         "怎么补": item["说明"] or "请提供这一项（它是这道工序的输入）"})

    # ── 前置：沙箱/样本模式 ＋ 人提供项非空（缺件即失败，不静默放过） ──
    pre = [{"id": "P1", "说明": "沙箱目录已就绪（交付件落点）",
            "断言": {"类型": "存在", "取值": "运行.沙箱目录"}},
           {"id": "P2", "说明": "本次运行是样本模式（超上限报错退出，不静默截断）",
            "断言": {"类型": "真", "取值": "运行.样本模式"}}]
    k = 2
    for name in gate_inputs:
        k += 1
        pre.append({"id": "P%d" % k,
                    "说明": "输入「%s」已填（草稿里空占位就是没填 —— 空值不会被放过）" % name,
                    "断言": {"类型": "非空", "取值": "输入.%s" % name}})

    # ── 判据：取数步骤真跑通 ＋ 产出非空 ＋ 交付件与来源一致 ──
    crit, i = [], 0
    for st in steps:
        if st["动作"] != "调用命令":
            continue
        i += 1
        crit.append({"id": "C%d" % i,
                     "说明": "取数步骤 %s（daniel %s）真跑通（退出码 0）"
                             % (st["id"], st["命令"]),
                     "断言": {"类型": "等于", "取值": "步骤.%s.退出码" % st["id"], "期望": 0},
                     "必过": True})
    n_c = i
    for st in steps:
        if st["动作"] != "调用命令":
            continue
        n_c += 1
        crit.append({"id": "C%d" % n_c,
                     "说明": "取数步骤 %s 真返回了内容（条目数至少 1 条；空结果当失败，"
                             "避免「拿不到数据却照样出件」）" % st["id"],
                     "断言": {"类型": "大于等于", "取值": "步骤.%s.条目数" % st["id"], "阈值": 1},
                     "必过": True})

    # ── 自检 ──
    self_checks = [
        {"id": "V1", "说明": "计数自洽：声明项数＝实跑项数＝通过＋失败＋跳过",
         "断言": {"类型": "计数自洽"}, "必过": True},
        {"id": "V2", "说明": "交付件行数等于来源步骤的条目数（同一批东西不许两处数出两个数）",
         "断言": {"类型": "等于", "取值": "交付件.行数", "期望": "步骤.%s.条目数" % source_step},
         "必过": True},
        {"id": "V3", "说明": "交付件逐列校验通过（必填列不缺）",
         "断言": {"类型": "等于", "取值": "交付件.校验", "期望": "通过"}, "必过": True},
        {"id": "V4", "说明": "交付件确实带着第一列「%s」（列名与真实返回的键对齐）" % columns[0],
         "断言": {"类型": "包含", "取值": "交付件.列", "期望": columns[0]}, "必过": True},
        {"id": "V5", "说明": "读链零写：写动作台账必须为空（本工序契约全是取数动作）",
         "断言": {"类型": "无写发生"}, "必过": True},
    ]

    failure_modes = [
        {"缺陷类": "CLS-65", "现象": "拿不到真实数据却照样出件（把空表当成功交出去）",
         "对策": "判据.%s" % crit[len(crit) - 1]["id"] if crit else "自检.V1"},
        {"缺陷类": "CLS-67", "现象": "同一批数据在步骤、交付件、汇总里各数一遍，数字对不上",
         "对策": "自检.V1"},
        {"缺陷类": "CLS-67", "现象": "交付件行数与来源步骤的条数脱钩（截断后当成功）",
         "对策": "自检.V2"},
        {"缺陷类": "CLS-76", "现象": "列名与真实返回的键对不上（看着有列、其实每行都是空）",
         "对策": "自检.V3"},
        {"缺陷类": "CLS-72", "现象": "判据没跑、只看退出码就宣布完成",
         "对策": "判据.C1"},
    ]

    ready = not todo and bool(shape)
    expect = ({"默认": {"结果": "通过", "退出码": 0}} if ready else
              {"默认": {"结果": "失败", "退出码": 1}})
    summary_bits = ["本次任务的需求原话：「%s」" % need] if need else []
    summary_bits.append("路由到工序「%s」（能力域：%s）" % (process["工序"], process["能力域标题"]))
    summary_bits.append("前置条件已按来源类型分列：能查的本次都真查了一遍，"
                        "查不到的留在「输入」里当空占位等你补")
    summary_bits.append("本契约全部是只读取数动作（零写）；写动作（若有）走 `daniel` 写命令"
                        "带 --confirm 人工确认后执行")
    if todo:
        summary_bits.append("还有 %d 项「人提供」输入没有值（见 输入 里默认空着的那几项）："
                            "补齐前跑它应当在缺件处失败，补齐后把 期望.默认 改成 通过／0"
                            % len(todo))
    if pending_steps:
        summary_bits.append("还有 %d 步取数因为缺上下文没进步骤（见报告「待补充后才能加入的"
                            "取数步骤」），补上上下文后重新生成即可" % len(pending_steps))

    contract = {
        "契约版本": "1.0",
        "id": draft_id(process),
        "名称": "%s（本次任务工序契约草稿）" % process["工序"],
        "说明": "；".join(summary_bits) + "。",
        "输入": inputs_doc,
        "前置": pre,
        "步骤": steps,
        "判据": crit,
        "门禁": [{"id": gid, "说明": text} for gid, text in GATES],
        "交付件schema": {
            "名称": process["产出交付件"] or "%s（本次任务交付件）" % process["工序"],
            "文件名": "%s.json" % (process["工序键"] or "intake-draft"),
            "来源步骤": source_step,
            "列": columns,
            "必填列": required_cols,
            "行数上限引用": "行数上限",
            "备注": deliverable_note,
        },
        "自检": self_checks,
        "失败模式": failure_modes,
        "限额": {"行数上限": {"默认": LIMIT_DEFAULT, "硬上限": LIMIT_HARD,
                          "适用步骤": source_step,
                          "说明": "交付件行数上限；超限报错退出、不静默截断"}},
        "期望": expect,
        "需要联网": _needs_network(steps),
    }

    report = {
        "工序": process["工序"], "工序键": process["工序键"],
        "能力域": process["能力域"], "能力域标题": process["能力域标题"],
        "契约id": contract["id"],
        "草稿落点": os.path.abspath(out) if out else None,
        "生成时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "模式": modes.current_mode(mode),
        "步骤数": len([s for s in steps if s["动作"] == "调用命令"]),
        "交付件": {"名称": contract["交付件schema"]["名称"], "来源步骤": source_step,
                   "列": columns, "必填列": required_cols, "备注": deliverable_note},
        "待你确认或补充": todo,
        "待补充后才能加入的取数步骤": pending_steps,
        "写动作确认单": (_write_confirmations(process) if process.get("需要能力") else []),
        "期望": contract["期望"],
        "期望说明": ("输入齐备、交付件形状已确证：这份草稿现在就能跑通（playbook run 应退出码 0）"
                     if ready else
                     "这份草稿**现在还不该跑通**：还缺 %d 项输入或交付件形状未确证，"
                     "它应当在缺件处失败（这是缺件阻断的机器判据）；补齐后把「期望.默认」改成"
                     " 结果=通过／退出码=0" % len(todo)),
    }
    return contract, report


def _needs_network(steps):
    """这份草稿要不要联网／要有效会话：命令自己的说明里写了「离线／不联网」的就不用。

    （判据取自 `schema.py` 的命令说明原文，不另立一份"哪些命令联网"的名单。）
    """
    from .. import schema as cli_schema
    for st in steps:
        if st["动作"] != "调用命令":
            continue
        spec = cli_schema.find_command(*st["命令"].split()) or {}
        text = "%s %s" % (spec.get("summary") or "", spec.get("description") or "")
        if "离线" not in text and "不联网" not in text:
            return True
    return False


def _write_confirmations(process):
    """本工序需要的写动作：给出确认单与可直接执行的命令（两种模式措辞不同）。"""
    out = []
    for key in process.get("需要能力") or []:
        if not modes.is_write(key):
            continue
        spec = _spec(key)
        action = (spec.get("summary") or key).split("（")[0].strip()
        out.append({"能力键": key, "动作": action,
                    "命令": modes.confirm_command(key),
                    "影响范围": spec.get("danger") or "见该命令帮助里写明的写语义",
                    "说明": "本工序最后一步是「%s」，需要你确认后执行（草稿里的取数步骤不会"
                            "自动触发它）" % action})
    return out


def _spec(key):
    from .. import schema as cli_schema
    return cli_schema.find_command(*str(key).split(".", 1)) or {}


def _deliverable_shape(probing, steps):
    """从**真查到的产出**里确证交付件形状：哪一步的产出里有列表、键是什么、列是什么。"""
    if probing is None:
        return None, None, ""
    for st in steps:
        key = st["命令"].replace(" ", ".")
        for sub_key in probing.list_keys(key):
            data = probing.data_of_key(key)
            rows = data if sub_key is None else (data or {}).get(sub_key)
            if not isinstance(rows, list) or not rows:
                continue
            columns = list(rows[0].keys())
            required = [c for c in columns
                        if all(isinstance(r, dict) and r.get(c) not in (None, "") for r in rows)]
            if not required:
                required = columns[:1]
            return ({"来源步骤": st["id"], "键": sub_key, "列": columns,
                     "必填列": required, "行数": len(rows)}, st["id"], "")
    return None, None, ""


def write_file(contract, path):
    """把草稿写盘（只有这一处写文件；不写任何 Daniel 数据）。"""
    path = os.path.abspath(os.path.expanduser(str(path)))
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(contract, fh, ensure_ascii=False, indent=1)
    return path


def validate_draft(contract):
    """用**引擎自己的校验器**校验草稿（同一条判据，不另写一套）。"""
    from ..playbook import validate as contract_validate
    return contract_validate.validate_contract(contract, None)


def playback_command(path):
    """给用户的复核命令（`playbook validate` 只认契约目录里的文件，所以显式指目录）。"""
    path = os.path.abspath(path)
    return "DANIEL_CONTRACTS_DIR=%s daniel playbook validate %s" % (
        os.path.dirname(path), os.path.basename(path))
