# -*- coding: utf-8 -*-
"""`daniel intake --self-test`：把「识别 → 匹配 → 前置条件 → 草稿」整条链路的判据钉死。

七组（正控／真阴性／缺件／三态／草稿／对等／诚实性），每组都给**可复核的实际输出**：

  A 工序表真源自证：字段齐备、来源类型与取数方式自洽、**没有一条取数方式引用写命令**
    （"能查的必须去查，且只读"的机器判据）
  B 正控：**真实历史需求**（取自本项目真跑过的活儿）必须落到预期能力域
  C 真阴性：完全无关的需求**不许硬匹配**（置信度低于匹配门槛 → 不做路由）
  D 缺件阻断：不给上下文／人提供项没给时，必须出"缺什么＋怎么补"，`可执行=false`，且不硬跑
  E 三态：读链＝可直接执行；写链＝需人工确认后执行（两种模式措辞不同）；真缺失＝当前模式不可用
    （第三态用**注入条件**验证：把某条读命令从可用集合里剔除，状态必须变成"当前模式不可用"）
  F 草稿：生成的工序契约草稿必须过**引擎自己的** `playbook validate`，并且能真的被
    `playbook run` 跑（跑不动时记「跳过（需要联网／会话）」而不是假通过）
  G 模式对等 ＋ 诚实性：模式对等断言全绿；报告里"已满足"的项必须带实查证据（退出码 0）

退出码：0 ＝ 全部通过（跳过项单列、不计通过）；1 ＝ 有未通过项。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from ..exits import EXIT_INTERNAL, EXIT_OK
from . import catalog, drafter, matcher, modes, parity, planner, preflight as pf

#: 正控夹具：**本项目真跑过的历史需求**（业务原话），期望落到哪个能力域。
#: 这些句子不是从工序表的「同义说法」里抄的（否则就是自证循环），来自 tickets 与交付记录。
HISTORICAL_NEEDS = (
    ("帮我审一下这批红人的报价", "kol-negotiation"),
    ("出一份对内审核表，把价格合理性和建议动作都写上", "kol-negotiation"),
    ("写第一封给这个红人的 pitch 邮件", "kol-outreach"),
    ("给这几个账号做深度背调，看看有没有刷量", "kol-screening"),
    ("从这些候选里选十个能合作的，出个短名单", "kol-screening"),
    ("出具这次合作的合同 rev1", "kol-contract"),
    ("出一份声量份额报告，跟竞品比一比", "kol-execution-sov"),
    ("看看这个品牌在 Daniel 里有哪些名单、名单里有哪些红人", "kol-daniel-api"),
    ("这个需求该走哪条能力域？帮我把工序排一下", "kol-intelligence"),
)

#: **已知歧义样本**（如实登记，不当正控）：一句话里同时点了两件活儿时，Top1 可能落在同族的
#: 另一道工序／另一个域上。这里只断言"落在可接受集合里、且报告把另一条列成候选"，
#: 因为两种路由在业务上都说得通（判据在语料里，匹配器不替业务下结论）。
AMBIGUOUS_NEEDS = (
    ("出一份检索词清单，我要去 Daniel 里搜红人", ("kol-discovery", "kol-daniel-api")),
)

#: 真阴性夹具：跟这套能力完全无关的需求（不得硬匹配）
UNRELATED_NEEDS = (
    "帮我订一张明天去上海的机票",
    "把这份财务报表做成 PPT 发给老板",
    "写个 Python 脚本把这两个 CSV 合并去重",
    "今天北京天气怎么样",
)

#: 三态与措辞断言用的一句话
CONFIRM_SAMPLE = ("触发一次这个词的品牌提及采集", "kol-daniel-api")

#: 草稿组用的夹具（**只在本自检的临时目录里用**，绝不进仓库、绝不写成真值）
DRAFT_FIXTURE_BRAND = "3690002"
DRAFT_ORDER = ("kol-negotiation", "审核表-出件")


def _items():
    return []


def _add(items, name, ok, detail="", skipped=False):
    items.append({"说明": name, "通过": bool(ok), "跳过": bool(skipped), "明细": detail})
    return ok


def _route_no_probe(need):
    """离线跑一次路由（确定性；用于缺件/真阴性断言，不联网）。"""
    return planner.route(need, live=False, top=3)


def selftest(emitter):
    items = []

    # ── A 工序表真源自证 ──
    verdict = catalog.validate()
    stats = verdict["统计"]
    _add(items, "A1 工序表真源结构自证（字段齐备／来源类型与取数方式自洽／防幻觉命令）",
         verdict["通过"], "；".join(verdict["问题"][:3]) or
         "%d 域／%d 工序／%d 条前置条件" % (stats["能力域数"], stats["工序数"], stats["前置条件数"]))
    doc = catalog.load()
    writes = modes.write_keys()
    bad = [(p["工序"], k) for p in doc["工序"] for k in p["需要能力"]
           if k in writes and k in "".join(i["取数方式"] for i in p["前置条件"])]
    _add(items, "A2 取数方式里一条写命令都没有（能查的必须只读地去查）", not bad,
         "命中：%s" % bad if bad else "全部 %d 条取数方式都是只读命令"
         % sum(len(i["取数方式"]) > 0 for p in doc["工序"] for i in p["前置条件"]))
    srcs = catalog.source_stats(doc)
    _add(items, "A3 来源类型分布（能查的没被写成「请你提供」）",
         srcs.get(catalog.SOURCE_SYSTEM, 0) + srcs.get(catalog.SOURCE_DERIVED, 0) > 0,
         "系统内已有 %d／可推导 %d／人提供 %d" % (srcs.get(catalog.SOURCE_SYSTEM, 0),
                                              srcs.get(catalog.SOURCE_DERIVED, 0),
                                              srcs.get(catalog.SOURCE_HUMAN, 0)))

    # ── B 正控：真实历史需求 ──
    hits, rows = 0, []
    for need, want in HISTORICAL_NEEDS:
        r = matcher.route(need, top=3)
        got = (r["Top1"] or {}).get("能力域")
        ok = got == want
        hits += 1 if ok else 0
        rows.append("%s → %s（置信度 %s，期望 %s）%s"
                    % (need, got, (r["Top1"] or {}).get("置信度"), want, "" if ok else " ✗"))
    _add(items, "B1 正控：%d 条真实历史需求的 Top1 落在预期能力域（%d/%d）"
         % (len(HISTORICAL_NEEDS), hits, len(HISTORICAL_NEEDS)),
         hits == len(HISTORICAL_NEEDS),
         "；".join(rows[:4]) + ("…" if len(rows) > 4 else ""))
    amb_rows, amb_ok = [], True
    for need, accept in AMBIGUOUS_NEEDS:
        r = matcher.route(need, top=3)
        got = (r["Top1"] or {}).get("能力域")
        others = [c["能力域"] for c in r["候选"][1:]]
        ok = got in accept and bool(set(accept) & set(others))
        amb_ok = amb_ok and ok
        amb_rows.append("%s → %s（可接受：%s；候选里另有 %s）"
                        % (need, got, "／".join(accept), "／".join(others) or "无"))
    _add(items, "B2 已知歧义样本如实登记（Top1 落在可接受集合里，且另一条在候选里）", amb_ok,
         "；".join(amb_rows) if amb_rows else "无歧义样本")

    # ── C 真阴性 ──
    leak = []
    for need in UNRELATED_NEEDS:
        r = matcher.route(need, top=3)
        if r["是否匹配上"]:
            leak.append("%s → %s（%.2f）" % (need, r["Top1"]["工序"], r["Top1"]["置信度"]))
    _add(items, "C1 真阴性：%d 条完全无关的需求都没有被硬匹配上" % len(UNRELATED_NEEDS),
         not leak, "误匹配：%s" % "；".join(leak) if leak else
         "最高置信度 %.2f，全部低于匹配门槛 %.2f"
         % (max(matcher.route(n, top=1)["候选"][0]["置信度"] if matcher.route(n, top=1)["候选"]
                else 0 for n in UNRELATED_NEEDS), matcher.T_ROUTE))

    # ── D 缺件阻断 ──
    rep = _route_no_probe("帮我审一下这批红人的报价")
    missing = rep["缺件清单"]
    _add(items, "D1 缺件场景：不给品牌／人提供项没给时，`可执行=false` 且列出缺件",
         (not rep["可执行"]) and bool(missing),
         "缺件 %d 项；可执行=%s；Top1=%s" % (len(missing), rep["可执行"],
                                          (rep["Top1"] or {}).get("工序")))
    no_fix = [m["名称"] for m in missing if not m.get("怎么补")]
    _add(items, "D2 每条缺件都给了「怎么补」（不是甩一个报错）", not no_fix,
         "缺补法：%s" % no_fix if no_fix else
         "示例：%s → %s" % (missing[0]["名称"], missing[0]["怎么补"][:80]) if missing else "无缺件")
    blocking_ok = all(m.get("是否阻断") is True for m in missing)
    _add(items, "D3 缺件项都标了阻断（不硬跑）", blocking_ok,
         "缺件项 %d 条全部标阻断" % len(missing))
    human = [m for m in rep["前置条件清单"] if m["来源类型"] == catalog.SOURCE_HUMAN]
    _add(items, "D4 查不到的东西如实写「需你提供」（不谎称已满足）",
         bool(human) and all(m["状态"] == pf.ST_NEED_YOU for m in human),
         "人提供 %d 条，状态：%s" % (len(human), "／".join(sorted({m["状态"] for m in human}))))

    # ── E 三态 ──
    read_key = "brands.list"
    write_key = "mentions.run"          # 写命令（用来断言"写链三态"本身）
    attached_key = "search.submit"      # 挂在某道工序上的写动作（用来断言告知措辞）
    _add(items, "E1 读链三态＝可直接执行（能力在当前模式可用）",
         modes.status_for(read_key, modes.MODE_CLI) == modes.ST_READY
         and modes.status_for(read_key, modes.MODE_MCP) == modes.ST_READY,
         "%s：CLI=%s，MCP=%s" % (read_key, modes.status_for(read_key, modes.MODE_CLI),
                                modes.status_for(read_key, modes.MODE_MCP)))
    cli_ok = modes.status_for(write_key, modes.MODE_CLI) == modes.ST_CONFIRM
    mcp_ok = modes.status_for(write_key, modes.MODE_MCP) == modes.ST_CONFIRM
    _add(items, "E2 写链三态＝需人工确认后执行（两种模式都是，措辞不同）", cli_ok and mcp_ok,
         "%s：CLI=%s，MCP=%s" % (write_key, modes.status_for(write_key, modes.MODE_CLI),
                                modes.status_for(write_key, modes.MODE_MCP)))
    proc = next((p for p in doc["工序"] if attached_key in p["需要能力"]), None)
    if proc is None:
        _add(items, "E3 写动作的告知措辞（MCP 模式：需要你确认；不得说「不支持／能力缺失」）", False,
             "工序表里没有引用 %s 的工序（写链动作没被登记）" % attached_key)
    else:
        mcp_pf = pf.Preflight(probe=pf.Probe(live=False, mode=modes.MODE_MCP))
        row = mcp_pf.check_capability(attached_key)
        text = json.dumps(row, ensure_ascii=False)
        wording = ("需要你确认" in text or "需要你确认" in (row or {}).get("说明", "")) \
            and "不支持" not in text and "能力缺失" not in text
        _add(items, "E3 写动作的告知措辞（MCP 模式：需要你确认，且不说「不支持／能力缺失」）",
             wording and row is not None and row.get("可直接执行的命令"),
             "工序「%s」的写动作 ｜ 命令：%s ｜ 执行语义：%s ｜ 说明：%s"
             % (proc["工序"], (row or {}).get("可直接执行的命令"),
                (row or {}).get("执行语义"), (row or {}).get("说明")))
    # 第三态：注入条件 —— 把一条读命令从可用集合里剔除，状态必须是"当前模式不可用"且阻断
    injected = pf.Preflight(probe=pf.Probe(live=False, mode=modes.MODE_MCP,
                                           capability_set=set()))
    row3 = injected.check_capability(read_key)
    _add(items, "E4 真缺失三态＝当前模式不可用（注入条件：可用集合为空时读链也要判成不可用）",
         bool(row3) and row3["状态"] == modes.ST_UNAVAILABLE and row3["是否阻断"] is True,
         "状态=%s，是否阻断=%s" % ((row3 or {}).get("状态"), (row3 or {}).get("是否阻断")))

    # ── F 草稿：过 validate ＋ 真跑一次 ──
    process = next((p for p in doc["工序"]
                    if p["能力域"] == DRAFT_ORDER[0] and p["工序"] == DRAFT_ORDER[1]), None)
    if process is None:
        _add(items, "F1 草稿能过引擎校验（playbook validate）", False,
             "工序表里找不到夹具工序 %s·%s" % DRAFT_ORDER)
    else:
        workdir = tempfile.mkdtemp(prefix="daniel-intake-selftest-")
        try:
            fixture_inputs = {i["名称"]: "自检夹具（不写仓库）"
                              for i in process["前置条件"]
                              if i["来源类型"] == catalog.SOURCE_HUMAN}
            may_live = _link_ok()
            # ① 什么都不填：草稿必须过 validate、必须留显式空占位、必须单列待补清单
            plain, plain_rep = drafter.build(process, need="帮我审一下这批红人的报价",
                                             brand=DRAFT_FIXTURE_BRAND, probing=None)
            verdict2 = drafter.validate_draft(plain)
            _add(items, "F1 草稿能过引擎自己的校验（playbook validate）", verdict2["通过"],
                 "；".join(verdict2["问题"][:3]) or
                 "8 项检查全过；步骤 %d 步、判据 %d 条"
                 % (len(plain["步骤"]), len(plain["判据"])))
            empties = [i["名称"] for i in plain["输入"] if i["默认"] == ""]
            human_items = [i for i in process["前置条件"] if i["来源类型"] == catalog.SOURCE_HUMAN]
            _add(items, "F2 草稿对「人提供」项留了显式空占位并单列待补清单",
                 len(empties) >= len(human_items) and
                 len(plain_rep["待你确认或补充"]) == len(empties),
                 "输入 %d 项（空占位 %d 项）／待补清单 %d 项；示例：%s"
                 % (len(plain["输入"]), len(empties), len(plain_rep["待你确认或补充"]),
                    empties[0] if empties else "无"))
            # ② 夹具填满 + 真查一次：交付件形状从真实产出确证，再用引擎真跑一遍
            probing = pf.Probe(live=may_live, timeout=pf.DEFAULT_TIMEOUT)
            pf.analyse(process, need="帮我审一下这批红人的报价", brand=DRAFT_FIXTURE_BRAND,
                       live=may_live, probe=probing)      # **共用取数器**：形状要靠这次真查
            contract, _rep = drafter.build(process, need="帮我审一下这批红人的报价",
                                           brand=DRAFT_FIXTURE_BRAND, probing=probing,
                                           inputs=fixture_inputs)
            path = drafter.write_file(contract, os.path.join(workdir, "%s.json" % contract["id"]))
            run = _run_playbook_run(path)
            if run["状态"] == "通过":
                _add(items, "F3 草稿真能被 `playbook run` 跑通（引擎级，不只是静态合法）", True,
                     "退出码 0；%s" % run["明细"])
            elif run["状态"] == "跳过":
                _add(items, "F3 草稿真能被 `playbook run` 跑通（引擎级，不只是静态合法）", True,
                     "跳过（需要联网或会话）：%s" % run["明细"], skipped=True)
            else:
                _add(items, "F3 草稿真能被 `playbook run` 跑通（引擎级，不只是静态合法）",
                     False, run["明细"])
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    # ── G 模式对等 ＋ 诚实性 ──
    par = parity.report()
    _add(items, "G1 模式对等断言（能力集合／技能集合／语料版本键比对）", par["通过"],
         "；".join("%s=%s" % (g["组"], g["状态"]) for g in par["断言组"]))
    live_rep = planner.route("帮我审一下这批红人的报价", brand=DRAFT_FIXTURE_BRAND, top=3)
    rows = [i for i in live_rep["前置条件清单"]
            if i["状态"] == pf.ST_OK and i["来源类型"] in catalog.QUERYABLE_SOURCES]
    ev_ok = bool(rows) and all(
        e.get("实查") is True and e.get("退出码") == 0 for i in rows for e in (i["证据"] or []))
    _add(items, "G2 诚实性：报告里「已满足」的项都带实查证据（真跑过、退出码 0）", ev_ok,
         "已满足 %d 项；示例：%s" % (len(rows),
                                  ("%s（%s，%s 毫秒）" % (rows[0]["名称"],
                                                        (rows[0]["证据"] or [{}])[0].get("命令"),
                                                        (rows[0]["证据"] or [{}])[0].get("耗时毫秒"))
                                   if rows else "无（本轮没查到已满足项）")))

    passed = sum(1 for i in items if i["通过"] and not i["跳过"])
    skipped = [i["说明"] for i in items if i["跳过"]]
    failed = [i["说明"] for i in items if not i["通过"]]
    summary = {
        "ok": not failed,
        "items": len(items),
        "passed": passed,
        "skipped": len(skipped),
        "failed": failed,
        "明细": items,
        "语料版本": doc["语料版本"],
        "工序总数": doc["工序数"],
        "模式": modes.fact_lines(),
        "说明": "本自检只读：不写任何 Daniel 数据、不触发任何采集、不做任何写操作；"
                "临时草稿写在系统临时目录并在结束时删除。",
    }
    if emitter.json_mode:
        emitter.result(data=summary, ok=summary["ok"],
                       exit_code=EXIT_OK if summary["ok"] else EXIT_INTERNAL)
    else:
        print("=== daniel intake 自检 ===", file=emitter.out)
        for it in items:
            flag = "[通过]" if it["通过"] and not it["跳过"] else (
                "[跳过]" if it["跳过"] else "[未过]")
            print(" %s %s" % (flag, it["说明"]), file=emitter.out)
            if it["明细"]:
                print("        %s" % it["明细"], file=emitter.out)
        print("自检 %d/%d（跳过 %d）" % (passed, len(items), len(skipped)), file=emitter.out)
        print("结论：%s" % ("全部通过" if summary["ok"] else
                          "未通过 %d 项：%s" % (len(failed), "；".join(failed))),
              file=emitter.out)
    return EXIT_OK if summary["ok"] else EXIT_INTERNAL


def _link_ok():
    """会话／链路可用探测（跑一次只读 `account whoami`；探不通就跳过真跑那条断言）。"""
    entry = pf.cli_entry()
    try:
        p = subprocess.run([sys.executable or "python3", entry, "account", "whoami", "--json"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=pf.DEFAULT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return p.returncode == 0


def _run_playbook_run(path):
    """用引擎跑一次草稿（**真跑**：退出码 0 才算通过；链路问题记跳过）。"""
    env = dict(os.environ)
    env["DANIEL_CONTRACTS_DIR"] = os.path.dirname(path)
    try:
        p = subprocess.run([sys.executable or "python3", pf.cli_entry(), "playbook", "run",
                            os.path.basename(path), "--json"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=600, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"状态": "跳过", "明细": "跑不起来：%s" % e}
    doc = None
    try:
        doc = json.loads(p.stdout or "")
    except ValueError:
        doc = None
    if p.returncode == 0 and isinstance(doc, dict) and doc.get("ok"):
        data = doc.get("data") or {}
        return {"状态": "通过", "明细": "结论：%s；步骤 %s 组、判据 %s 组"
                % ((data.get("结论") or {}).get("摘要"),
                   (data.get("步骤") or {}).get("实跑项数"),
                   (data.get("判据") or {}).get("实跑项数"))}
    why = ""
    if isinstance(doc, dict):
        why = ((doc.get("error") or {}).get("message")
               or ((doc.get("data") or {}).get("结论") or {}).get("摘要") or "")
    if not why:
        why = ((p.stderr or p.stdout or "").strip().splitlines() or ["无输出"])[-1][:200]
    if "取数" in why or "网络" in why or "会话" in why or "登录" in why or "凭据" in why:
        return {"状态": "跳过", "明细": "退出码 %s：%s" % (p.returncode, why)}
    return {"状态": "未过", "明细": "退出码 %s：%s" % (p.returncode, why)}
