# -*- coding: utf-8 -*-
"""链路的编排层：把「识别 → 匹配 → 前置条件告知 → 契约草稿」串成一次调用。

分工不越界：
  · `matcher` 只算"这条需求像哪道工序"；
  · `preflight` 只负责"能查的真去查／查不到的如实说"；
  · `drafter` 只负责"把匹配结果写成一份能过 `playbook validate` 的草稿"；
  · 本文件把它们按用户的入口顺序串起来，并**统一决定退出码语义**：
    可继续 ＝ 0（缺件也是 0，但 `可执行=false`），参数错误 ＝ 2。
"""
import os

from . import catalog, drafter, matcher, modes, preflight as pf

#: 深查深度：默认只对 Top1 做完整实查（其余候选给声明清单，省时间也省调用）
DEFAULT_TOP = 3


def _candidate_row(row, probe, need, brand, live, timeout, mode, extra_vars, declare_only):
    process = catalog.by_key(row["工序键"])
    check = pf.analyse(process, need=need, brand=brand, live=live, timeout=timeout, mode=mode,
                       runner=probe.runner, capability_set=probe.capability_set,
                       extra_vars=extra_vars, declare_only=declare_only)
    out = dict(row)
    out["前置条件清单"] = check["前置条件"]
    out["缺件"] = check["缺件"]
    out["待确认"] = check["待确认"]
    out["可执行"] = check["可执行"]
    out["结论"] = check["结论"]
    out["深度"] = check["深度"]
    out["实查记录"] = check["实查记录"]
    out["模式能力"] = pf.capability_summary(
        process, mode=mode, capability_set=probe.capability_set,
        brand=(check.get("品牌") or {}).get("值"))
    if declare_only:
        out["前置条件"] = row["前置条件"]
    return out


def route(need, top=DEFAULT_TOP, brand=None, live=True, timeout=pf.DEFAULT_TIMEOUT, mode=None,
          check_all=False, runner=None, capability_set=None, extra_vars=None,
          routes=None):
    """一次完整的需求识别＋能力匹配＋前置条件告知。

    `routes`：自检可以塞一份现成的匹配结果进来（避免重复算）；不给就现算。
    返回报告字典（`可执行` 与 `缺件清单` 是结论字段）。
    """
    mode = modes.current_mode(mode)
    matched = routes or matcher.route(need, top=max(int(top or DEFAULT_TOP), DEFAULT_TOP))
    probe = pf.Probe(live=live, timeout=timeout, runner=runner, mode=mode,
                     capability_set=capability_set)
    cands = []
    for i, row in enumerate(matched["候选"]):
        deep = (i == 0) or bool(check_all)
        cands.append(_candidate_row(row, probe, need, brand, live, timeout, mode,
                                    extra_vars, declare_only=not deep))
    top1 = cands[0] if cands else None
    missing = list((top1 or {}).get("缺件") or [])
    confirm = list((top1 or {}).get("待确认") or [])
    executable = bool(top1 and top1["可执行"] and matched["是否匹配上"])
    if not matched["是否匹配上"]:
        nxt = ["这句话不像既有工序里的任何一道（匹配门槛 %.2f）：请补一句「要什么产出、给谁用」，"
               "或直接点名工序" % matcher.T_ROUTE]
        concl = matched["说明"]
    elif missing:
        nxt = ["先补齐 %d 项缺件：%s" % (len(missing),
                                    "；".join("「%s」→ %s" % (m["名称"], m["怎么补"])
                                             for m in missing[:3]))]
        nxt.append("补齐后重跑 `daniel intake route --need \"…\"` 确认可执行，"
                   "或直接 `daniel intake draft --need \"…\"` 生成本次任务的工序契约草稿")
        concl = "匹配到「%s」，但前置条件不齐：先补齐再开工（缺什么见「缺件清单」）" % top1["工序"]
    else:
        nxt = ["可以开工"]
        if confirm:
            nxt = ["执行前需要你确认写动作：%s"
                   % "；".join(c.get("可直接执行的命令") or "" for c in confirm)]
            nxt.append("确认后再执行；确认单见「待确认」")
        nxt.append("要把它变成可执行的工序契约：`daniel intake draft --need \"…\"`")
        concl = "匹配到「%s」，前置条件齐备%s" % (
            top1["工序"], "；最后一步是写动作，需要你确认" if confirm else "")
    if top1 and top1.get("深度") == "声明":
        concl += "（Top1 之外只给了声明清单，未逐条实查）"
    return {
        "需求": need,
        "模式": modes.fact_lines(mode),
        "语料版本": matched["语料版本"],
        "工序总数": matched["工序总数"],
        "候选": cands,
        "Top1": top1,
        "前置条件清单": (top1 or {}).get("前置条件清单") or [],
        "缺件清单": missing,
        "待确认": confirm,
        "可执行": executable,
        "是否匹配上": matched["是否匹配上"],
        "匹配门槛": matched["门槛"],
        "结论": concl,
        "下一步": nxt,
        "模式能力": (top1 or {}).get("模式能力") or {},
        "实查记录": (top1 or {}).get("实查记录") or [],
        "说明": "本命令只做「路由 ＋ 缺件」：判据仍在语料与工序里，不替业务下结论；"
                "全程只读（不写任何 Daniel 数据、不触发采集）。",
    }


def draft(need, out=None, brand=None, inputs=None, live=True, timeout=pf.DEFAULT_TIMEOUT,
          mode=None, top=DEFAULT_TOP, runner=None, capability_set=None, extra_vars=None):
    """匹配 → 前置条件告知 → 生成本次任务的工序契约草稿（并就地用引擎校验器校验）。

    返回 `{路由报告, 草稿报告, 契约, 校验, 复核命令}`；匹配不上或生不出草稿时抛 `CliError`。
    """
    from ..exits import EXIT_USAGE
    from ..runtime import CliError
    matched = matcher.route(need, top=max(int(top or DEFAULT_TOP), DEFAULT_TOP))
    if not matched["是否匹配上"]:
        raise CliError("这句话不像既有工序里的任何一道，先不做草稿：%s" % matched["说明"],
                       code=EXIT_USAGE,
                       hint="请补一句「要什么产出、给谁用」，或直接点名工序后重试")
    top1 = matched["Top1"]
    process = catalog.by_key(top1["工序键"])
    probing = pf.Probe(live=live, timeout=timeout, runner=runner, mode=mode,
                       capability_set=capability_set)
    # **同一个取数器**跑前置条件与草稿：草稿的交付件形状要靠这次真查到的产出确证
    check = pf.analyse(process, need=need, brand=brand, live=live, timeout=timeout, mode=mode,
                       runner=runner, capability_set=capability_set, extra_vars=extra_vars,
                       probe=probing)
    contract, draft_report = drafter.build(process, need=need, brand=brand, probing=probing,
                                           inputs=inputs, out=out, mode=mode)
    verdict = drafter.validate_draft(contract)
    path = drafter.write_file(contract, out or drafter.default_out(process))
    draft_report["草稿落点"] = path
    draft_report["校验"] = {"通过": verdict["通过"], "问题数": verdict["问题数"],
                        "问题": verdict["问题"],
                        "检查项": [{"id": c["id"], "说明": c["说明"], "通过": c["通过"],
                                    "问题数": len(c["问题"])} for c in verdict["检查项"]]}
    draft_report["复核命令"] = drafter.playback_command(path)
    draft_report["契约"] = contract
    return {
        "需求": need,
        "模式": modes.fact_lines(modes.current_mode(mode)),
        "候选Top1": {k: top1[k] for k in ("工序", "工序键", "能力域", "能力域标题",
                                         "置信度", "档位", "理由", "产出交付件", "对应契约")},
        "前置条件清单": check["前置条件"],
        "缺件清单": check["缺件"],
        "待确认": check["待确认"],
        "可执行": check["可执行"],
        "草稿": draft_report,
        "结论": ("草稿已生成并通过引擎校验：%s" % path if verdict["通过"]
                 else "草稿已生成，但引擎校验未过：%s" % "；".join(verdict["问题"][:3])),
        "说明": "草稿是**待你确认**的版本：输入占位与待确认项见「草稿.待你确认或补充」；"
                "确认（补齐输入）后再执行，执行走 `daniel playbook run <草稿>`。",
    }
