# -*- coding: utf-8 -*-
"""intake 模块：需求识别 → 能力匹配 → 前置条件告知 → 工序契约草稿（**能力包核心的入口**）。

三条命令（全部只读；命令与参数在 `../schema.py` 里声明，本文件只做实现）：

| 命令 | 干什么 | 退出码 |
|---|---|---|
| `daniel intake route --need "…"` | 一句话需求 → 候选工序（排序＋理由＋置信度）＋ 前置条件清单（每项带来源类型与**当前状态**）＋ 缺件清单 | 可继续＝0（缺件也是 0，但报告里 `可执行=false`）；参数错误＝2 |
| `daniel intake draft --need "…" [--out 文件]` | 同一句话 → 生成本次任务的**工序契约草稿**（输入／步骤／判据／门禁／交付件／自检），并就地用引擎校验器校验 | 草稿生成且校验通过＝0；校验不通过＝1；匹配不上／上下文中够不着＝2 |
| `daniel intake parity` | 模式对等断言：CLI 与 MCP 暴露的**能力集合／技能集合／语料版本**键比对 | 全绿＝0；有未通过＝1 |

两种承载模式（用户 2026-10-14／15 口径）
--------------------------------------
CLI 与 MCP 是**两种模式**，每一种都内置完整链路：本模块的实现只有一份，
MCP 侧的工具落成一次 `daniel intake … --json` 子进程调用。写动作在两种模式下都**可见**，
区别只在"谁按确认"：CLI 走 `--confirm`，MCP 出确认单交给人在 CLI／桌面壳执行。
"""
import json
import os

from ..exits import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE
from ..intake import catalog, drafter, modes, parity, planner, preflight as pf
from ..intake import selfcheck as intake_selfcheck
from ..runtime import CliError

BOARD = "intake"

#: 人读状态标签（业务语言；与 `preflight` 的状态取值一一对应）
_STATUS_LABEL = {
    pf.ST_OK: "已满足",
    pf.ST_MISSING: "缺失",
    pf.ST_PENDING: "待定",
    pf.ST_NEED_YOU: "需你提供",
    pf.ST_FAILED: "取数失败",
    pf.ST_NOT_PROBED: "未实查",
    modes.ST_READY: "可直接执行",
    modes.ST_CONFIRM: "需人工确认后执行",
    modes.ST_UNAVAILABLE: "当前模式不可用",
}


def _kv(pairs, flag):
    """把 `--input 品牌=Halliday` 收成字典（写错即报用户错误）。"""
    out = {}
    for p in pairs or []:
        if "=" not in str(p):
            raise CliError("%s 要写成「名字=值」（当前 %r）" % (flag, p), code=EXIT_USAGE,
                           hint="例：%s 品牌=Halliday" % flag)
        k, v = str(p).split("=", 1)
        if not k.strip():
            raise CliError("%s 的名字不能为空（当前 %r）" % (flag, p), code=EXIT_USAGE)
        out[k.strip()] = v.strip()
    return out


def _mode(ctx):
    return modes.current_mode(ctx.get("mode"))


# ─────────────────────────── 人读渲染 ───────────────────────────
def _fmt_item(it):
    label = _STATUS_LABEL.get(it.get("状态"), it.get("状态") or "?")
    bits = ["[%s] %s" % (label, it.get("名称"))]
    bits.append("来源：%s" % it.get("来源类型"))
    if it.get("取数方式"):
        bits.append("取数方式：%s" % it["取数方式"])
    for ev in it.get("证据") or []:
        if ev.get("实查"):
            bits.append("已实查：%s（退出码 %s，%s 毫秒%s）"
                        % (ev.get("命令"), ev.get("退出码"), ev.get("耗时毫秒"),
                           "，条数 %s" % ev.get("条数") if ev.get("条数") is not None else ""))
        else:
            bits.append("未实查：%s" % ev.get("说明") or "")
    if it.get("可直接执行的命令"):
        bits.append("可直接执行的命令：%s" % it["可直接执行的命令"])
    if it.get("需要确认"):
        bits.append("（需要你确认后执行）")
    if it.get("怎么补"):
        bits.append("怎么补：%s" % it["怎么补"])
    return "  - " + " ｜ ".join(b for b in bits if b and b != "None")


def _human_route(rep):
    lines = ["需求：%s" % rep["需求"],
             "语料版本：%s（工序 %d 道）" % (rep["语料版本"], rep["工序总数"]),
             "模式：%s ｜ 当前模式可用能力 %d 条（可直接执行 %d／需人工确认后执行 %d）"
             % (rep["模式"]["当前模式说明"], rep["模式"]["当前模式可用能力数"],
                rep["模式"]["当前模式可直接执行"], rep["模式"]["当前模式需人工确认后执行"]),
             "能力真源：%s" % rep["模式"]["能力真源"],
             ""]
    top = rep["Top1"]
    if top:
        lines.append("匹配结论：%s" % rep["结论"])
        lines.append("为什么是它（工序「%s」，能力域：%s，置信度 %.2f／档位 %s）："
                     % (top["工序"], top["能力域标题"], top["置信度"], top["档位"]))
        for r in top["理由"]:
            lines.append("  · %s" % r)
        lines.append("")
    lines.append("候选工序（前 %d 条）：" % len(rep["候选"]))
    for i, c in enumerate(rep["候选"], 1):
        lines.append("  %d. %s ｜ %s ｜ 置信度 %.2f（%s）｜ 产出：%s"
                     % (i, c["工序"], c["能力域标题"], c["置信度"], c["档位"],
                        c["产出交付件"] or "（未登记）"))
    lines.append("")
    lines.append("Top1 的前置条件（%d 项；能查的本次都真查了一遍）：" % len(rep["前置条件清单"]))
    for it in rep["前置条件清单"]:
        lines.append(_fmt_item(it))
    if rep["缺件清单"]:
        lines.append("")
        lines.append("缺件清单（%d 项，补齐前不硬跑）：" % len(rep["缺件清单"]))
        for m in rep["缺件清单"]:
            lines.append("  - %s（%s）→ %s" % (m["名称"], _STATUS_LABEL.get(m["状态"], m["状态"]),
                                          m.get("怎么补") or "见上"))
    mc = rep.get("模式能力") or {}
    if mc.get("明细"):
        lines.append("")
        lines.append("模式能力三态（%s）：可直接执行 %d 条／需人工确认后执行 %d 条／"
                     "当前模式不可用 %d 条"
                     % (mc["模式说明"], len(mc["可直接执行"]), len(mc["需人工确认后执行"]),
                        len(mc["当前模式不可用"])))
        for it in mc["明细"]:
            extra = (" ｜ 命令：%s" % it["可直接执行的命令"]) if it.get("可直接执行的命令") else ""
            lines.append("  - [%s] %s（%s）%s" % (it["状态"], it["动作"], it["能力键"], extra))
    if rep["待确认"]:
        lines.append("")
        lines.append("待你确认（写动作；确认前 AI 不执行）：")
        for c in rep["待确认"]:
            lines.append("  - %s ｜ 命令：%s" % (c["名称"], c.get("可直接执行的命令") or "见上"))
    lines.append("")
    lines.append("可执行：%s" % ("是" if rep["可执行"] else "否"))
    lines.append("下一步：")
    for n in rep["下一步"]:
        lines.append("  - %s" % n)
    return "\n".join(lines)


def _human_draft(rep):
    d = rep["草稿"]
    lines = ["需求：%s" % rep["需求"],
             "匹配结论：工序「%s」（%s）｜置信度 %.2f／档位 %s"
             % (rep["候选Top1"]["工序"], rep["候选Top1"]["能力域标题"],
                rep["候选Top1"]["置信度"], rep["候选Top1"]["档位"]),
             "模式：%s" % rep["模式"]["当前模式说明"],
             "",
             "草稿：%s" % d["草稿落点"],
             "契约编号：%s ｜ 取数步骤 %d 步 ｜ 交付件：%s（来源步骤 %s）"
             % (d["契约id"], d["步骤数"], d["交付件"]["名称"], d["交付件"]["来源步骤"]),
             "引擎校验：%s（问题 %d 条）" % ("通过" if d["校验"]["通过"] else "未通过",
                                        d["校验"]["问题数"]),
             "复核命令：%s" % d["复核命令"],
             "期望：%s（%s）" % (json.dumps(d["期望"], ensure_ascii=False), d["期望说明"]),
             ""]
    if d["待你确认或补充"]:
        lines.append("待你确认或补充（%d 项）：" % len(d["待你确认或补充"]))
        for t in d["待你确认或补充"]:
            lines.append("  - %s（%s）→ %s" % (t["项"], t["类型"], t["怎么补"]))
    if d["待补充后才能加入的取数步骤"]:
        lines.append("待补充后才能加入的取数步骤（%d 步）：" % len(d["待补充后才能加入的取数步骤"]))
        for t in d["待补充后才能加入的取数步骤"]:
            lines.append("  - %s → 缺：%s" % (t["取数方式"], "、".join(t["缺的上下文"])))
    if d["写动作确认单"]:
        lines.append("写动作确认单（%d 项；确认前 AI 不执行）：" % len(d["写动作确认单"]))
        for c in d["写动作确认单"]:
            lines.append("  - %s ｜ 命令：%s ｜ 影响：%s"
                         % (c["动作"], c["命令"], c["影响范围"]))
    lines.append("")
    lines.append("结论：%s" % rep["结论"])
    return "\n".join(lines)


def _human_parity(rep):
    lines = ["模式对等断言：%s" % rep["结论"], ""]
    for g in rep["断言组"]:
        lines.append("[%s] %s" % (g["状态"], g["断言"]))
        kb = g.get("键比对")
        if isinstance(kb, dict):
            for k, v in kb.items():
                lines.append("    %s：%s" % (k, v if not isinstance(v, dict)
                                          else json.dumps(v, ensure_ascii=False)))
        lines.append("")
    return "\n".join(lines)


# ─────────────────────────── 三条命令 ───────────────────────────
def cmd_route(ctx):
    need = ctx.require("need", metavar="--need \"一句话需求\"")
    rep = planner.route(need, top=int(ctx.get("top") or 3), brand=ctx.get("brand"),
                        live=not ctx.get("no_probe"), timeout=int(ctx.get("timeout") or
                                                                 pf.DEFAULT_TIMEOUT),
                        mode=_mode(ctx), check_all=bool(ctx.get("check_all")))
    ctx.emit(data=rep, human=_human_route(rep))
    return EXIT_OK


def cmd_draft(ctx):
    need = ctx.require("need", metavar="--need \"一句话需求\"")
    rep = planner.draft(need, out=ctx.get("out"), brand=ctx.get("brand"),
                        inputs=_kv(ctx.get("input"), "--input"),
                        live=not ctx.get("no_probe"),
                        timeout=int(ctx.get("timeout") or pf.DEFAULT_TIMEOUT), mode=_mode(ctx))
    ctx.emit(data=rep, human=_human_draft(rep))
    if not rep["草稿"]["校验"]["通过"]:
        ctx.warn("草稿没通过引擎校验：%s" % "；".join(rep["草稿"]["校验"]["问题"][:3]))
        return EXIT_INTERNAL
    return EXIT_OK


def cmd_parity(ctx):
    rep = parity.report()
    ctx.emit(data=rep, human=_human_parity(rep))
    if rep["通过"]:
        if rep.get("未落地（待其他票）"):
            ctx.note("另有未落地项（已显式登记，未计入未通过）：%s"
                     % "、".join(rep["未落地（待其他票）"]))
        return EXIT_OK
    ctx.warn("模式对等断言有未通过项：%s" % "、".join(rep["未通过"]))
    return EXIT_INTERNAL


def cmd_catalog(ctx):
    """看工序表本身（只读）：8 个能力域各有哪些工序、每个工序要哪些前置条件。"""
    doc = catalog.load()
    domain = ctx.get("domain")
    rows = []
    for dom in doc["能力域"]:
        if domain and dom["技能束"] != domain:
            continue
        rows.append({"能力域": dom["技能束"], "能力域标题": dom["能力域标题"],
                     "语料版本": dom["语料版本"], "工序数": dom["工序数"],
                     "工序": [{"工序": p["工序"], "工序键": p["工序键"],
                              "触发语义": p["触发语义"],
                              "前置条件": [{"名称": i["名称"], "来源类型": i["来源类型"],
                                        "取数方式": i["取数方式"], "说明": i["说明"]}
                                       for i in p["前置条件"]],
                              "产出交付件": p["产出交付件"], "对应契约": p["对应契约"],
                              "需要能力": p["需要能力"], "依据": p["依据"]}
                             for p in doc["按域"][dom["技能束"]]]})
    data = {"真源": doc["真源"], "语料版本": doc["语料版本"], "能力域数": doc["能力域数"],
            "工序数": doc["工序数"], "前置条件数": doc["前置条件数"],
            "来源类型统计": catalog.source_stats(doc),
            "自证": catalog.validate(),
            "能力域": rows,
            "说明": "工序与前置条件表是本链路的真源：匹配按 `触发语义＋同义说法`，"
                    "前置条件按 `来源类型＋取数方式` 在运行期真查；"
                    "「模式能力」这一类由当前模式真实可用的能力集合在运行期派生。"}
    if domain and not rows:
        raise CliError("没有这个能力域：%s" % domain, code=EXIT_USAGE,
                       hint="可选：%s" % "、".join(d["技能束"] for d in doc["能力域"]))
    ctx.emit(data=data)
    return EXIT_OK


HANDLERS = {
    "route": cmd_route,
    "draft": cmd_draft,
    "parity": cmd_parity,
    "catalog": cmd_catalog,
}

WRITE_HANDLERS = {}

#: 模块自带自检（由 `cli.py` 的模块级钩子分发：`daniel intake --self-test`）
SELFTEST = intake_selfcheck.selftest
