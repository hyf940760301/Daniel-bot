#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 Daniel Bot 左栏「动态执行轨迹」的字段级映射表。

产出：
  · daniel-bot/app/workflow-map.json  —— 机器可消费（91 条 CLI 命令逐条归属）
  · daniel-bot/app/workflow-map.md    —— 人读摘要（按模块分组 / 覆盖统计 / 推断项）

设计纪律
--------
1. **命令全集不手抄**：91 条命令、`--help` 摘要、是否写操作、MCP 工具名，全部在运行时
   从 `daniel_cli/schema.py`（唯一真源）与 `exports.mcp_payload()` 读取；脚本断言条数＝91，
   真源一变就失败（宁可报错，不要静默少映射）。
2. **字段必须有证据**：每条字段都在生成时到四个事实源里查一遍，按
   `code`（commands/*.py 里的键/参数）→ `route`（60-data-layer.md 的返回字段）→
   `schema`（schema.py 该命令的返回说明）→ `dict`（字段字典的源字段）
   的顺序取证；四级都查不到才标 `inferred`。证据字符串写进 `fieldEvidence`。
3. **幂等**：输出不含时间戳、不含随机量；条目顺序固定（按 schema 模块顺序）。
   `--check` 只重算并与磁盘比对，不写文件。

用法：
  python3 daniel-bot/app/scripts/gen-workflow-map.py
  python3 daniel-bot/app/scripts/gen-workflow-map.py --check   # CI 用：不一致则退出码 1
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ─────────────────────────── 路径与真源 ───────────────────────────
ROOT = Path(__file__).resolve().parents[3]
CLI_DIR = ROOT / "daniel-bot/packages/0.11.0/vendor/data/daniel-cli"
#: 随包语料根（8 束 `kol-*`）：助手自写阶段的依据只能从这里取。
CORPUS_DIR = CLI_DIR / "mcp/corpus"

if str(CLI_DIR) not in sys.path:
    sys.path.insert(0, str(CLI_DIR))

from daniel_cli import exports, schema as schema_mod  # noqa: E402

REPO = ROOT

REL = {
    "skill": "daniel-bot/packages/0.11.0/vendor/data/daniel-cli/mcp/corpus/"
             "kol-intelligence/SKILL.md",
    "capability": "daniel-bot/packages/0.11.0/vendor/data/daniel-cli/mcp/corpus/"
                  "kol-intelligence/references/02-capability-map.md",
    "capmap": "docs/marketing/skills/_CAPABILITY-MAP.json",
    "dict": "docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md",
    "schema": "daniel-bot/packages/0.11.0/vendor/data/daniel-cli/daniel_cli/schema.py",
    "commands": "daniel-bot/packages/0.11.0/vendor/data/daniel-cli/daniel_cli/commands/*.py",
    "route": "daniel-bot/packages/0.11.0/vendor/data/daniel-cli/mcp/corpus/"
             "kol-daniel-api/references/60-data-layer.md",
}
PATH = {k: REPO / v for k, v in REL.items()}

OUT_JSON = REPO / "daniel-bot/app/workflow-map.json"
OUT_MD = REPO / "daniel-bot/app/workflow-map.md"

EXPECTED_COMMANDS = 91

#: 能力条目里以 Daniel 仪器为载体的 → CLI 模块。用来核对「能力层（45 条）→ 命令面（91 条）」
#: 没有断层：条目在、但模块一条命令都没有，就说明映射漏了。
INSTRUMENT_MODULE = {
    "daniel_brands": "brands", "daniel_lists": "lists", "daniel_ct": "ct",
    "daniel_mentions": "mentions", "daniel_intel": "intel", "daniel_sov": "sov",
    "daniel_takeover_check": "takeover", "daniel_search": "search",
    "daniel_authenticity": "authenticity",
}

#: 能力地图 7 阶段 → 本表工作流（0 起）。阶段 6（SOV）与 7（热点）合并为 `sov`；
#: `contract` 不在 7 阶段表里（8 束语料中的独立能力），`data`/`ops` 为跨阶段层与平台层。
PHASE_WORKFLOW = {
    0: "stage0-product", 1: "discovery", 2: "screening", 3: "outreach",
    4: "negotiation", 5: "execution", 6: "sov", 7: "sov",
}


def _phase_rows(text: str, label: str) -> list[tuple[int, str]]:
    """从 `## 1. 能力地图（7 阶段总览）` 一节里读 0–7 八行。读不出即失败。"""
    m = re.search(r"^## 1\. 能力地图（7 阶段总览）\s*$", text, re.M)
    if not m:
        raise SystemExit("%s 里找不到 §1 能力地图（7 阶段总览）" % label)
    tail = text[m.end():]
    nxt = re.search(r"^## ", tail, re.M)
    section = tail[:nxt.start()] if nxt else tail
    rows: list[tuple[int, str]] = []
    for line in section.splitlines():
        mm = re.match(r"^\|\s*(\d)\s*\|\s*(.+?)\s*\|", line)
        if mm:
            name = re.sub(r"\*\*|`", "", mm.group(2)).strip()
            rows.append((int(mm.group(1)), name))
    if [r[0] for r in rows] != list(range(8)):
        raise SystemExit("%s 的阶段表读不出 0–7 八行：%r" % (label, rows))
    return rows


def load_phases() -> list[tuple[int, str]]:
    """阶段表的**唯一真源**是 A 包内 `kol-intelligence/SKILL.md` §1（源 L68–L82）；
    `references/02-capability-map.md` 是它的逐字切片，两处必须一致（不一致即失败）。"""
    rows = _phase_rows(PATH["skill"].read_text(encoding="utf-8"), "SKILL.md")
    slice_rows = _phase_rows(PATH["capability"].read_text(encoding="utf-8"),
                             "02-capability-map.md")
    if rows != slice_rows:
        raise SystemExit("SKILL.md §1 与其切片 02-capability-map.md 不一致：%r vs %r"
                         % (rows, slice_rows))
    return rows


def load_capmap() -> list[dict]:
    """读 `_CAPABILITY-MAP.json`（45 条能力）。条数不符即失败：它是「能力层有没有新增/删除」的
    第一道信号，静默放过会让映射表与能力层悄悄漂移。"""
    data = json.loads(PATH["capmap"].read_text(encoding="utf-8"))
    entries = data.get("entries") or []
    if len(entries) != 45:
        raise SystemExit("_CAPABILITY-MAP.json 的 entries 不是 45 条（实际 %d）" % len(entries))
    return entries


def capmap_links(entries: list[dict]) -> list[dict]:
    """能力条目 → CLI 模块（只取以 Daniel 仪器为载体、且仪器名能对上模块的那些）。"""
    out = []
    for e in entries:
        mods = []
        for ins in e.get("instruments") or []:
            stem = Path(str(ins)).stem
            mod = INSTRUMENT_MODULE.get(stem)
            if mod and mod not in mods:
                mods.append(mod)
        if mods:
            out.append({"id": e["id"], "name": e.get("name") or "", "modules": mods})
    return out


# 字段证据档位（从强到弱）。`schema` 与 `dict` 仍是文件里逐字存在的字段名/描述，
# 只是不是「接口返回的键」本身，故单独计数，不混进「源码字段名」。
TIERS = ("code", "route", "schema", "dict", "inferred")
TIER_LABEL = {
    "code": "commands/*.py 字段名/参数",
    "route": "60-data-layer 返回字段",
    "schema": "schema.py 返回说明",
    "dict": "字段字典源字段",
    "inferred": "推断·无直接证据",
}

# ─────────────────────────── 工作流定义（A 的能力地图） ───────────────────────────
# 唯一依据：A 包内 `mcp/corpus/kol-intelligence/SKILL.md` §1（7 阶段总览，源 L68–L82）
# ＋ 8 束语料（`kol-*`）。**不使用另一条管线的模块名**（D-058/D-059；见 md §九）。
# `contract` 不在 7 阶段表里：8 束语料中 `kol-contract` 是独立能力，按包内顺序排在谈判与执行之间。
# `data` 与 `ops` 是 D-058 指定的两个横向层：前者是跨阶段平台能力（品牌/名单/提及/CT），
# 后者是平台运维（全部 `internal: true`）。
WORKFLOWS = [
    {"id": "stage0-product", "name": "产品说明与 Key Feature",
     "steps": ["产品事实", "Key Feature 提炼", "官方说明块"]},
    {"id": "discovery", "name": "发现", "steps": ["检索词矩阵（含参数澄清）", "跑检索", "名单产线"]},
    {"id": "screening", "name": "背调", "steps": ["评分卡", "真实性核验", "shortlist"]},
    {"id": "outreach", "name": "外联（KOL Pitch）", "steps": ["首封 Pitch", "跟进", "回复处置"]},
    {"id": "negotiation", "name": "谈判", "steps": ["问价", "砍价", "审核表"]},
    {"id": "contract", "name": "合同", "steps": ["条款适配", "出具合同", "签署归档"]},
    {"id": "execution", "name": "执行", "steps": ["审稿", "发布", "数据回收"]},
    {"id": "sov", "name": "SOV 与热点", "steps": ["固定竞争集", "份额与情感", "热点追踪"]},
    {"id": "data", "name": "数据层", "steps": ["读取", "写入（含回读）"]},
    {"id": "ops", "name": "平台运维", "steps": ["需求路由", "环境与账号", "安装与接入", "自检与出包"]},
]

# ───────────────── 助手自写阶段的依据（5 个阶段 · 用户裁决 D-060） ─────────────────
# 这 5 个阶段没有随包仪器，作业由助手按能力语料自己完成；左栏显示「本阶段由助手完成，
# 无工具调用」＋一段「我为什么这么写」。口径是**第一人称的判断过程**，不是出处引用：
# 用户要的是「助手怎么想的」，不是「依据出自哪份文件的第几节」。
# 展示字段 `title`／`thinking`／`output` 禁内部标识（断言见 `assert_rationale`）；
# 证据只落在 `trace`（文件 ＋ 行号），供 QA 回溯，不展示给用户。
#: 必须覆盖的 5 个阶段（少一个即生成失败）。
AGENT_RATIONALE_WORKFLOWS = ("stage0-product", "outreach", "negotiation", "contract", "execution")

_CORPUS = "daniel-bot/packages/0.11.0/vendor/data/daniel-cli/mcp/corpus/"

AGENT_RATIONALE: dict[str, list[dict]] = {
    "stage0-product": [
        {"title": "产品说明只写有出处的参数",
         "thinking": "我写的每个参数和功能名，都能在品牌书或官网里翻到原话，翻不到的就留白标待确认。"
                     "因为这个说明会被对方拿去比对官网——编一个数字，整封邮件立刻被判定成群发模板，"
                     "后面再解释也拉不回来。宁可少写一句，也不写一句没人背书的话。",
         "output": "产品说明块（英文）",
         "trace": {"file": _CORPUS + "kol-discovery/references/10-discovery-steps.md", "line": 1280}},
        {"title": "卖点为什么按七个维度核",
         "thinking": "品类定位、差异化、主要功能、日常功能、硬件、生态、背书，我逐项打勾，缺哪项就明说缺哪项。"
                     "因为漏掉的卖点不会自己长回来：KOL 照着这份说明写脚本，没写进去的就不会出现在视频里，"
                     "等上线再补只能重拍。多核一遍的成本，远低于补拍一次。",
         "output": "完整性核对表 ＋ 缺口清单",
         "trace": {"file": _CORPUS + "kol-discovery/references/10-discovery-steps.md", "line": 1299}},
    ],
    "outreach": [
        {"title": "产品段怎么写",
         "thinking": "我把产品参数和使用场景放在最前面，因为对方判断要不要继续聊，看的是「你到底用没用过这东西」。"
                     "形容词堆得再多，也不如一句具体参数；写得太像模板，对方连回都不会回。"
                     "所以这一段每句话，我都要能在品牌物料里找到出处。",
         "output": "首封邮件正文（英文）",
         "trace": {"file": _CORPUS + "kol-outreach/SKILL.md", "line": 40}},
        {"title": "首封要不要带条款",
         "thinking": "首封我只讲产品、请他报价，交付、授权、付款这些条款留到第二封。"
                     "因为第一次接触就甩一整套条款，对方会当成群发的合同模板直接不回；"
                     "先把产品聊明白，条款反而更好谈。",
         "output": "首封邮件（英文）＋ 条款邮件（英文）",
         "trace": {"file": _CORPUS + "kol-outreach/SKILL.md", "line": 56}},
    ],
    "negotiation": [
        {"title": "报价贵不贵怎么判",
         "thinking": "我不看粉丝量，先把这个号的报价按它最近的实际平均播放折成千次播放成本，再判合理、偏高还是过高。"
                     "因为粉丝可以买、播放买不了：二十万粉但条均五千播放的号，报出来的单价会高得离谱，"
                     "只看总价根本比不出问题。",
         "output": "对内审核表（价格判断三选一）",
         "trace": {"file": _CORPUS + "kol-negotiation/SKILL.md", "line": 60}},
        {"title": "目标价为什么不一刀切",
         "thinking": "数据扎实又明显报高价的号，我把目标价往上放；常规号就按参考区间往下谈。"
                     "因为同一套折扣砍所有号，遇到真强的号会直接谈崩；对方一旦觉得你不识货，"
                     "后面再想拉回来就很难。",
         "output": "砍价邮件（英文）＋ 目标价",
         "trace": {"file": _CORPUS + "kol-negotiation/SKILL.md", "line": 48}},
    ],
    "contract": [
        {"title": "合同为什么只换字不动版",
         "thinking": "我在原母版上换掉条款文字，页边距、字号、行距、签署区一个都不动。"
                     "因为这份文件的版式就是客户和法务认它的方式：我试过把条款一字不差地重排一遍，还是被退回——"
                     "对方看到的已经不是同一份文件了。",
         "output": "合同签署版（PDF）＋ 可复制版",
         "trace": {"file": _CORPUS + "kol-contract/SKILL.md", "line": 41}},
        {"title": "条款改动为什么压到最少",
         "thinking": "我先列出必须替换的段落，只改这几处，其余照抄母版。"
                     "因为改动越多，对方越会怀疑「这合同是不是有问题」，然后重新拉一轮谈判，"
                     "签署周期会拖长一倍。",
         "output": "条款替换清单",
         "trace": {"file": _CORPUS + "kol-contract/SKILL.md", "line": 69}},
    ],
    "execution": [
        {"title": "审稿到底卡多严",
         "thinking": "我只卡三件事：方向讲得对不对、事实有没有错、卖点有没有讲到位，不要求他逐字照品牌方的说明念。"
                     "因为真人拍视频不可能一字不差，卡太严只会拖到错过发布窗口；"
                     "但价格、规格这类事实错误必须当场改，那是品牌方要背书的部分。",
         "output": "逐句审稿意见",
         "trace": {"file": _CORPUS + "kol-execution-sov/SKILL.md", "line": 55}},
        {"title": "回收为什么用同一套字段",
         "thinking": "发布时间、链接、播放点赞评论、转化信号、授权和付款状态，我按同一套字段记。"
                     "因为字段各记各的，后面复盘和声量就对不上账，既回答不了这波投放值不值，"
                     "也没法跟下一批比。",
         "output": "回收清单",
         "trace": {"file": _CORPUS + "kol-execution-sov/SKILL.md", "line": 42}},
    ],
}

#: 展示字段里禁止出现的内部标识（文件名／章节号／内部代号／工作流 id）。
#: 用户视角：他不需要知道「依据出自哪个文件第几节」，只需要知道「我为什么这么写」。
DISPLAY_FORBIDDEN = re.compile(
    r"SKILL|§|CLS-|CS-|TICKET-|\.md\b|stage0-product|kol-|corpus|references/")

#: 空话黑名单：不承载信息的套话命中即失败（宁可没有，也不要凑字数）。
EMPTY_PHRASES = ("按照标准", "依据规范", "确保质量", "符合要求", "按标准流程", "标准化流程",
                 "按照规范", "依据标准", "保证质量", "按流程执行")


def assert_rationale() -> None:
    """5 个阶段每个至少 1 条（或显式 `missing`），最多 3 条；展示字段禁内部标识与空话；
    `trace` 必须指到语料里真实存在、且该行非空的文件:行号（不许编）。"""
    for wid in AGENT_RATIONALE_WORKFLOWS:
        rows = AGENT_RATIONALE.get(wid) or []
        if not rows:
            raise SystemExit("助手自写阶段 %s 没有依据说明（至少 1 条，或显式标 missing）" % wid)
        if len(rows) > 3:
            raise SystemExit("%s 的依据说明 %d 条，超过 3 条上限" % (wid, len(rows)))
        for i, row in enumerate(rows, 1):
            if "missing" in row:
                if not str(row["missing"]).strip():
                    raise SystemExit("%s 第 %d 条标了 missing 但没写原因" % (wid, i))
                continue
            for key in ("title", "thinking", "output"):
                val = str(row.get(key) or "").strip()
                if not val:
                    raise SystemExit("%s 第 %d 条缺 %s" % (wid, i, key))
                hit = DISPLAY_FORBIDDEN.search(val)
                if hit:
                    raise SystemExit("%s 第 %d 条的展示文案 %s 出现内部标识「%s」：%s"
                                     % (wid, i, key, hit.group(0), val))
                for phrase in EMPTY_PHRASES:
                    if phrase in val:
                        raise SystemExit("%s 第 %d 条的展示文案 %s 是空话（命中「%s」）：%s"
                                         % (wid, i, key, phrase, val))
            if len(str(row.get("thinking") or "")) < 40:
                raise SystemExit("%s 第 %d 条的 thinking 太短，讲不清判断（至少 40 字）" % (wid, i))
            tr = row.get("trace") or {}
            rel, line = str(tr.get("file") or ""), tr.get("line")
            path = REPO / rel
            if not rel or not path.is_file():
                raise SystemExit("%s 第 %d 条的追溯文件不存在：%s" % (wid, i, rel or "（空）"))
            if CORPUS_DIR not in path.parents:
                raise SystemExit("%s 第 %d 条的追溯文件不在随包语料内：%s" % (wid, i, rel))
            if not isinstance(line, int) or line < 1:
                raise SystemExit("%s 第 %d 条的追溯行号非法：%r" % (wid, i, line))
            lines = path.read_text(encoding="utf-8").splitlines()
            if line > len(lines):
                raise SystemExit("%s 第 %d 条的追溯行号越界：%s:%d（共 %d 行）"
                                 % (wid, i, rel, line, len(lines)))
            if not lines[line - 1].strip():
                raise SystemExit("%s 第 %d 条的追溯行是空行：%s:%d" % (wid, i, rel, line))


#: 归类唯一真源：命令 id → (工作流, 0 起步骤)。91 条逐条登记，缺一条即失败。
CLASSIFY = {
    "auth.status": ("ops", 1),

    "brands.list": ("data", 0), "brands.show": ("data", 0),
    "brands.competitors": ("data", 0), "brands.create": ("data", 1),
    "brands.update": ("data", 1), "brands.clone": ("data", 1),
    "brands.delete": ("data", 1),

    "lists.by-brand": ("data", 0), "lists.items": ("data", 0),
    "lists.saved-channel-ids": ("data", 0), "lists.share-status": ("data", 0),
    "lists.auto-priority-status": ("data", 0), "lists.create": ("data", 1),
    "lists.rename": ("data", 1), "lists.delete": ("data", 1),

    "search.history": ("discovery", 1), "search.job-status": ("discovery", 1),
    "search.submit": ("discovery", 1),

    "mentions.jobs": ("data", 0), "mentions.status": ("data", 0),
    "mentions.results": ("data", 0), "mentions.run": ("data", 1),

    "intel.actions": ("data", 0), "intel.keywords": ("data", 0),
    "intel.topics": ("data", 0), "intel.reviews": ("data", 0),

    "sov.overview": ("sov", 1), "sov.categories": ("sov", 0),
    "sov.brand-videos": ("sov", 1), "sov.run-exposure": ("sov", 1),

    "ct.campaigns": ("data", 0), "ct.campaign-stats": ("data", 0),
    "ct.deals": ("data", 0), "ct.videos": ("data", 0),
    "ct.resolve-channel": ("data", 0), "ct.interests": ("data", 0),
    "ct.create-campaign": ("data", 1), "ct.delete-campaign": ("data", 1),

    "authenticity.channel": ("screening", 1), "authenticity.weights": ("screening", 0),

    "route.probe": ("ops", 3), "route.catalog": ("ops", 3), "route.sweep": ("ops", 3),
    "takeover.check": ("ops", 3), "takeover.check-writes": ("ops", 3),
    "parity.selfcheck": ("ops", 3), "parity.compare": ("ops", 3),
    "account.whoami": ("ops", 1), "account.workspaces": ("ops", 1),
    "account.capabilities": ("ops", 1), "account.audit": ("ops", 1),
    "account.credentials": ("ops", 1), "account.credentials-set": ("ops", 1),
    "account.paths": ("ops", 1), "account.list": ("ops", 1),
    "account.switch": ("ops", 1), "account.login": ("ops", 1),
    "keywords.check": ("discovery", 0),
    "skills.list": ("ops", 1), "skills.read": ("ops", 1),
    "playbook.list": ("ops", 3), "playbook.show": ("ops", 3),
    "playbook.validate": ("ops", 3), "playbook.run": ("ops", 3),
    "playbook.deliver": ("ops", 3), "playbook.selfcheck": ("ops", 3),
    "sched.run": ("ops", 3), "sched.retry": ("ops", 3),
    "sched.status": ("ops", 3), "sched.queue": ("ops", 3),
    "connect.list": ("ops", 2), "connect.print": ("ops", 2),
    "connect.apply": ("ops", 2), "connect.uninstall": ("ops", 2),
    "connect.doctor": ("ops", 2),
    "pack.out": ("ops", 3), "pack.check": ("ops", 3),
    "install.run": ("ops", 2), "install.check": ("ops", 2), "install.upgrade": ("ops", 2),
    "intake.route": ("ops", 0), "intake.draft": ("ops", 0),
    "intake.parity": ("ops", 0), "intake.catalog": ("ops", 0),
    "schema.show": ("ops", 1), "schema.mcp": ("ops", 1),
    "schema.dsh-tools": ("ops", 1), "schema.check": ("ops", 1),
    "clarify.plan": ("discovery", 0), "clarify.ask": ("discovery", 0),
}

#: 模块级归类理由（逐条 rationale 的基座；个别命令在 REASON_OVERRIDE 里单独写）
MODULE_REASON = {
    "auth": "登录态是全部业务命令的前置",
    "brands": "品牌档案是检索口径、背调、产品说明共用的事实源",
    "lists": "名单是跨阶段载体：发现落库、背调取人、外联取联系方式",
    "search": "检索产出候选长名单 longlist，是阶段 1 的产线",
    "mentions": "品牌提及是平台级证据能力，供 SOV/热点与背调复用",
    "intel": "Action Center 是平台内容情报（动作/选题/审核单），跨阶段复用",
    "sov": "SOV 是阶段 6（份额+情感）与阶段 7（热点）的载体",
    "ct": "Creator Tracker 是平台级合作追踪（订单/视频/统计），跨阶段复用",
    "authenticity": "真实性与造假检测是阶段 2 的判据",
    "keywords": "检索词清单是阶段 1 的词表校验",
    "clarify": "找红人的参数澄清发生在检索之前，属阶段 1 入口",
    "route": "通路体检是平台自检，不面向业务阶段",
    "takeover": "接管验收是平台验收，不面向业务阶段",
    "parity": "口径一致性自检是平台验收",
    "account": "账号/工作区/凭据/审计是平台环境",
    "skills": "随包语料是各阶段判据的来源，本身是平台资产",
    "playbook": "工序契约引擎是平台执行器",
    "sched": "调度是平台执行器",
    "connect": "宿主接入属于安装动作",
    "pack": "出包属于分发动作",
    "install": "安装向导属于安装动作",
    "intake": "需求路由是平台入口",
    "schema": "命令清单是平台元数据",
}

#: 同模块内需要单独说明的命令（其余按模块＋步骤生成）
#: 一条 CLI 命令对应的**插件工具口径**（同一能力有两种分发形态：CLI MCP 与 DSH 插件，工具名不同）。
#: 键＝命令 id；值＝(主工具, 同一命令族的其它工具…)。左栏按主工具匹配，其余列进 `mcpTools` 备查。
#: 为什么要有这张表：`search` 三命令的真执行入口在插件侧（`daniel_deep_research`／
#: `daniel_open_research`／`daniel_research_status`），CLI MCP 的老工具名不再代表现行通道。
MCP_TOOL_OVERRIDE = {
    "search.submit": ("daniel_deep_research", ["daniel_deep_research_commit", "daniel_open_research"]),
    "search.job-status": ("daniel_research_status", ["daniel_deep_research", "daniel_open_research"]),
}

REASON_OVERRIDE = {
    "brands.show": "品牌档案详情：产品说明与各阶段共用的事实源（品类/竞品/目标市场/简介）",
    "lists.items": "名单成员读取（含频道、订阅数、质量分、互动率、标签），背调与外联取人都用它",
    "search.history": "检索历史用于复用词表与复盘，属阶段 1 的检索记录",
    "ct.resolve-channel": "频道实体解析：把 @handle／链接／UC 编号解析成频道编号",
    "sov.categories": "SOV 的固定竞争集：品类档案里的登记竞品以品牌自配置为准",
    "authenticity.channel": "按前端口径当场复算真实性评分（该页不落库）",
    "keywords.check": "检索词清单的格式/词量/重复/计数校验，是阶段 1 的词表门禁",
    "clarify.plan": "找红人的参数缺口清单（不取数），属阶段 1 的入口澄清",
    "clarify.ask": "找红人的五类选择面与动态追问（不取数），属阶段 1 的入口澄清",
    "mentions.run": "发起品牌提及分析（触发采集；写链带确认与回读），产出归数据层",
    "sov.run-exposure": "发起曝光采集（SOV 的取数触发；写链带确认与回读）",
}


#: 0 条命令的工作流：作业载体在 `.kol-tools/` 仪器与 Skill 章节，不在 91 条 CLI 里。
#: 每条给能力条目 id（生成时到 `_CAPABILITY-MAP.json` 里取仪器名，取不到即失败）。
ZERO_CARRIERS = [
    ("outreach",
     ["edm-first-pitch", "edm-pitch", "edm-followup", "edm-reply", "edm-correction",
      "edm-shipping-info", "edm-confirm-ack"],
     "CLI 不发邮件；首封/跟进/回复是邮件作业"),
    ("negotiation",
     ["terms-response", "four-tables", "review-table-fill", "edm-quote-request",
      "edm-bargain", "edm-rate-im", "edm-terms-contract"],
     "CLI 不做问价/砍价/审核表；这些是判据与四表作业"),
    ("contract",
     ["contract-issue", "contract-kol-adapt", "contract-feishu-sync"],
     "CLI 不出合同；合同是文档作业"),
    ("execution",
     ["review-recovery", "script-review", "edm-progress-brief"],
     "CLI 不做审稿/回收；执行期数据由 data 层的 CT 与提及提供"),
]


def workflow_reason(cid: str, wf_id: str, step: int, module_key: str) -> str:
    """一条命令的归类依据（人读一句话）。"""
    if cid in REASON_OVERRIDE:
        return REASON_OVERRIDE[cid]
    base = MODULE_REASON.get(module_key, "")
    if wf_id == "data":
        head = "跨阶段平台数据的读取" if step == 0 else "跨阶段平台数据的写入（确认＋回读）"
        return "%s；%s（D-058：平台能力归 data）" % (head, base)
    if wf_id == "sov":
        head = "SOV 的固定竞争集（品类档案＋竞品）" if step == 0 else "SOV 份额/热点的取数与明细"
        return "%s；%s" % (head, base)
    if wf_id == "discovery":
        head = "发现阶段的词表/参数准备" if step == 0 else "发现阶段的检索执行与记录"
        return "%s；%s" % (head, base)
    if wf_id == "screening":
        head = "背调评分口径" if step == 0 else "背调的真实性核验"
        return "%s；%s" % (head, base)
    if wf_id == "ops":
        wf = next(w for w in WORKFLOWS if w["id"] == "ops")
        return "平台运维 · %s；%s" % (wf["steps"][step], base)
    return base


TIER_ORDER = ("code", "route", "schema", "dict", "inferred")
#: 只由 schema.py 描述其结构的命令（工具清单/参数清单）：schema 档优先于 route
SCHEMA_FIRST = ("schema", "code", "route", "dict", "inferred")


def F(display: str, *keys: str, order: tuple[str, ...] | None = None) -> tuple[str, list[str], tuple[str, ...]]:
    """一条字段：展示名 ＋ 候选键 ＋ 取证顺序。

    `order` 只在需要改默认顺序时给：例如「工具名」的键是 `name`，而 `name` 在 60-data-layer
    里出现过（别的路由的字段），默认顺序会把它误判成 `route`；这类命令的工具清单结构只在
    schema.py 的返回说明里，所以用 `order=("schema","code","route","dict","inferred")`。
    """
    return (display, list(keys), order or TIER_ORDER)


# ─────────────────────── 策展表（页面 / 步骤 / 字段） ───────────────────────
# 说明：这里只做「模块→页面」「命令→工作流步骤」「命令→字段」的**编辑判断**；
# 命令是否存在、是否写操作、摘要、MCP 工具名全部由 schema.py 派生并校验。
# fields 里的候选键必须能在下面四个索引里查到，否则自动落 `inferred`。
CURATED: dict[str, dict] = {
    # ── 授权 ──────────────────────────────────────────────
    "auth.status": dict(module="授权", page="登录状态", fields=[
        F("登录状态", "authenticated"), F("判定理由", "reason"),
        F("会话落点", "本机会话文件"), F("退出码", "exitCode")]),

    # ── 品牌资产 ──────────────────────────────────────────
    "brands.list": dict(module="品牌资产", page="品牌列表", fields=[
        F("品牌名", "name"), F("品类", "category"),
        F("目标市场", "targetCountries"), F("竞品", "competitors")]),
    "brands.show": dict(module="品牌资产", page="品牌详情", fields=[
        F("品牌编号", "id"), F("简介", "description"),
        F("频道", "youtubeChannelId"), F("竞品", "competitors"),
        F("目标市场", "targetCountries")]),
    "brands.competitors": dict(module="品牌资产", page="竞品清单", fields=[
        F("竞品名", "name"), F("品类关键词", "categoryKeywords")]),
    "brands.create": dict(module="品牌资产", page="新建品牌", fields=[
        F("品牌名", "name"), F("简介", "description"), F("品类", "category"),
        F("行业关键词", "industryKeywords"), F("目标市场", "targetCountries"),
        F("样品价", "sampleCost"), F("竞品", "competitors")]),
    "brands.update": dict(module="品牌资产", page="品牌编辑", fields=[
        F("品牌名", "name"), F("简介", "description"), F("品类", "category"),
        F("行业关键词", "industryKeywords"), F("目标市场", "targetCountries"),
        F("样品价", "sampleCost"), F("竞品", "competitors")]),
    "brands.clone": dict(module="品牌资产", page="品牌克隆", fields=[
        F("新品牌名", "name"), F("目标工作区", "workspaceId"), F("简介", "description"),
        F("品类", "category"), F("目标市场", "targetCountries"),
        F("样品价", "sampleCost"), F("竞品", "competitors")]),
    "brands.delete": dict(module="品牌资产", page="品牌删除", fields=[
        F("品牌名", "name"), F("工作区", "workspaceId"), F("删除凭据", "delete-token", "deleteTokenRequired")]),

    # ── 红人名单 ──────────────────────────────────────────
    "lists.by-brand": dict(module="红人名单", page="名单列表", fields=[
        F("名单编号", "id"), F("名单名", "name"), F("红人数", "influencerCount")]),
    "lists.items": dict(module="红人名单", page="名单成员", fields=[
        F("频道编号", "channelId"), F("频道名", "channelTitle"),
        F("订阅数", "subscriberCount"), F("质量分", "cqiScore"),
        F("互动率", "engagementRate"), F("标签", "tags")]),
    "lists.saved-channel-ids": dict(module="红人名单", page="已存频道", fields=[
        F("频道编号", "channelIds"), F("编号条数", "count")]),
    "lists.share-status": dict(module="红人名单", page="名单分享", fields=[
        F("是否开启分享", "是否开启分享"), F("分享码", "分享码"), F("分享时间", "分享时间")]),
    "lists.auto-priority-status": dict(module="红人名单", page="自动优先级", fields=[
        F("自动优先级状态", "自动优先级状态"), F("进度百分比", "进度百分比"),
        F("完成时间", "完成时间"), F("最近更新时间", "最近更新时间")]),
    "lists.create": dict(module="红人名单", page="新建名单", fields=[
        F("名单名", "name"), F("品牌", "brandId")]),
    "lists.rename": dict(module="红人名单", page="名单改名", fields=[
        F("名单编号", "listId"), F("名单名", "name"), F("品牌", "brandId")]),
    "lists.delete": dict(module="红人名单", page="删除名单", fields=[
        F("名单编号", "id"), F("名单名", "name"),
        F("红人数", "influencerCount"), F("删除凭据", "delete-token", "deleteTokenRequired")]),

    # ── 红人检索 ──────────────────────────────────────────
    "search.history": dict(module="红人检索", page="检索历史", fields=[
        F("检索式", "query"), F("检索方式", "检索方式"), F("发起时间", "发起时间")]),
    # 两条任务式通道（官方库通道已退役）：deep（有品牌）／open（无品牌、自由描述）。
    # 阶段固定五档（排队中／检索中／富化中／完成／失败），由插件侧统一映射，前端左栏同一口径。
    "search.job-status": dict(module="红人检索", page="检索任务进度（五档阶段）", fields=[
        F("任务状态", "status"), F("进度", "进度")]),
    "search.submit": dict(module="红人检索", page="发起检索（deep／open）", fields=[
        F("检索式", "query"), F("品牌", "brandId"), F("候选上限", "limit")]),

    # ── 品牌提及 ──────────────────────────────────────────
    "mentions.jobs": dict(module="品牌提及", page="提及任务列表", fields=[
        F("任务编号", "jobId"), F("状态", "status"),
        F("分析时间范围", "分析时间范围"), F("视频数", "视频")]),
    "mentions.status": dict(module="品牌提及", page="任务进度与汇总", fields=[
        F("进度百分比", "progressPercent"), F("当前阶段", "currentStage"),
        F("已分析数", "analyzedCount"), F("完成说明", "完成说明"), F("结果汇总", "结果汇总")]),
    "mentions.results": dict(module="品牌提及", page="视频级评分结果", fields=[
        F("视频标题", "视频标题"), F("频道", "频道"), F("播放量", "播放量"),
        F("表现评级", "overallPerformance"), F("相关性", "relevanceLabel")]),
    "mentions.run": dict(module="品牌提及", page="发起提及分析", fields=[
        F("品牌", "brandId"), F("检索方式", "searchMode"),
        F("回溯天数", "timeRangeDays"), F("最多视频数", "maxVideos")]),

    # ── 内容情报 ──────────────────────────────────────────
    "intel.actions": dict(module="内容情报", page="待办动作", fields=[
        F("动作编号", "动作编号"), F("类型", "类型"), F("标题", "标题"),
        F("依据", "依据"), F("建议做法", "建议做法")]),
    "intel.keywords": dict(module="内容情报", page="追踪关键词", fields=[
        F("关键词", "关键词"), F("来源", "来源"),
        F("启用状态", "启用状态"), F("上限与余量", "上限与余量")]),
    "intel.topics": dict(module="内容情报", page="选题", fields=[
        F("选题编号", "选题编号"), F("标题", "标题"),
        F("主要关键词", "主要关键词"), F("支撑词", "支撑词")]),
    "intel.reviews": dict(module="内容情报", page="内容审核单", fields=[
        F("审核单", "审核单"), F("阶段", "stage"), F("选题标签", "topicLabel")]),

    # ── 声量份额 ──────────────────────────────────────────
    "sov.overview": dict(module="声量份额", page="声量总览", fields=[
        F("播放量", "播放量"), F("视频数", "视频数"), F("份额占比", "份额占比")]),
    "sov.categories": dict(module="声量份额", page="品类档案与竞品", fields=[
        F("品类档案", "categoryProfileId"), F("登记竞品", "competitors")]),
    "sov.brand-videos": dict(module="声量份额", page="品牌视频明细", fields=[
        F("视频标题", "视频标题"), F("频道", "频道"),
        F("播放量", "播放量"), F("发布时间", "发布时间")]),
    "sov.run-exposure": dict(module="声量份额", page="发起曝光采集", fields=[
        F("品类档案", "categoryProfileId"), F("市场", "country"), F("统计窗口", "days")]),

    # ── 合作追踪 ──────────────────────────────────────────
    "ct.campaigns": dict(module="合作追踪", page="合作活动列表", fields=[
        F("活动编号", "id"), F("标题", "name"), F("起止日期", "起止日期"), F("活动码", "活动码")]),
    "ct.campaign-stats": dict(module="合作追踪", page="活动统计", fields=[
        F("订单数", "订单数"), F("达人数", "达人数"),
        F("应有视频数", "应有视频数"), F("已关联视频数", "已关联视频数")]),
    "ct.deals": dict(module="合作追踪", page="订单明细", fields=[
        F("订单条数", "订单条数"), F("合作单", "合作单"), F("视频统计", "视频统计")]),
    "ct.videos": dict(module="合作追踪", page="共创视频", fields=[
        F("视频条数", "视频条数"), F("逐条明细", "逐条明细")]),
    "ct.resolve-channel": dict(module="合作追踪", page="频道解析", fields=[
        F("频道编号", "频道编号"), F("是否成功", "是否成功")]),
    "ct.interests": dict(module="合作追踪", page="频道兴趣画像", fields=[
        F("兴趣来源", "兴趣来源"), F("兴趣列表", "兴趣列表")]),
    "ct.create-campaign": dict(module="合作追踪", page="新建活动", fields=[
        F("活动名", "title"), F("开始日期", "startDate"),
        F("结束日期", "endDate"), F("是否常青", "isEvergreen")]),
    "ct.delete-campaign": dict(module="合作追踪", page="删除活动", fields=[
        F("活动编号", "campaignId"), F("活动名", "title")]),

    # ── 真实性核验 ────────────────────────────────────────
    "authenticity.channel": dict(module="真实性核验", page="频道真实性评分", fields=[
        F("频道名", "频道名"), F("订阅数", "订阅数"), F("样本视频数", "样本视频数"),
        F("总分", "总分"), F("信号判定", "信号判定")]),
    "authenticity.weights": dict(module="真实性核验", page="评分权重", fields=[
        F("信号名称", "信号名称"), F("权重", "权重")]),

    # ── 数据通路 ──────────────────────────────────────────
    "route.probe": dict(module="数据通路", page="通路探测", fields=[
        F("是否可用", "available"), F("字段清单", "fields"),
        F("字段数", "field_count"), F("数据样本", "sample")]),
    "route.catalog": dict(module="数据通路", page="通路清单", fields=[
        F("通路名", "route"), F("请求动词", "method"),
        F("说明", "note"), F("默认入参", "defaultInput")]),
    "route.sweep": dict(module="数据通路", page="全量通路扫描", fields=[
        F("可用性", "可用性"), F("出口文件", "out")]),

    # ── 接管验收 ──────────────────────────────────────────
    "takeover.check": dict(module="接管验收", page="只读验收", fields=[
        F("区块", "区块"), F("检查项", "checks"), F("结论", "结论"), F("证据", "证据")]),
    "takeover.check-writes": dict(module="接管验收", page="含写链验收", fields=[
        F("检查项", "checks"), F("状态", "status"),
        F("临时对象残留", "临时对象残留"), F("回读结论", "readback")]),

    # ── 口径一致性 ────────────────────────────────────────
    "parity.selfcheck": dict(module="口径一致性", page="口径自检", fields=[
        F("检查项", "逐项检查"), F("通过情况", "通过情况"), F("差异", "差异")]),
    "parity.compare": dict(module="口径一致性", page="页面逐字比对", fields=[
        F("逐字段比对", "逐字段比对"), F("页面抓取数据", "probe")]),

    # ── 账号与工作区 ──────────────────────────────────────
    "account.whoami": dict(module="账号与工作区", page="当前账号", fields=[
        F("账号邮箱", "email"), F("系统角色", "systemRole"),
        F("账号状态", "userStatus"), F("当前工作区", "activeWorkspaceId")]),
    "account.workspaces": dict(module="账号与工作区", page="工作区列表", fields=[
        F("工作区编号", "id"), F("工作区名称", "name"),
        F("是否当前", "isActive"), F("配额", "配额")]),
    "account.capabilities": dict(module="账号与工作区", page="能力矩阵", fields=[
        F("系统角色", "systemRole"), F("账号状态", "userStatus"),
        F("模块", "module"), F("读写结论", "读写结论"), F("配额", "maxBrands")]),
    "account.audit": dict(module="账号与工作区", page="写操作审计", fields=[
        F("记录条数", "记录条数"), F("真执行", "真执行"),
        F("未执行", "未执行"), F("已回滚", "已回滚"), F("最近一条", "最近一条")]),
    "account.credentials": dict(module="账号与工作区", page="凭据来源", fields=[
        F("凭据来源", "source"), F("掩码邮箱", "email_masked"), F("钥匙串可用性", "keychain")]),
    "account.credentials-set": dict(module="账号与工作区", page="写入凭据", fields=[
        F("凭据来源", "凭据来源"), F("掩码邮箱", "email_masked"),
        F("明文文件是否写入", "plaintextWrite"), F("服务名", "service")]),
    "account.paths": dict(module="账号与工作区", page="数据落点", fields=[
        F("会话", "会话"), F("缓存", "缓存"), F("产出", "产出"),
        F("日志", "日志"), F("账号分区", "账号分区")]),
    "account.list": dict(module="账号与工作区", page="本机账号", fields=[
        F("当前账号", "当前账号"), F("分区落点", "分区落点"),
        F("已存账号", "已存账号"), F("钥匙串", "钥匙串")]),
    "account.switch": dict(module="账号与工作区", page="切换账号", fields=[
        F("切换前后账号", "切换前后"), F("生效落点", "生效落点"), F("回读对账", "回读对账")]),
    "account.login": dict(module="账号与工作区", page="登录", fields=[
        F("回读到的账号", "回读到的账号"), F("系统角色", "系统角色"),
        F("会话落点", "sessionFile"), F("回读校验", "回读校验")]),

    # ── 检索词清单 ────────────────────────────────────────
    "keywords.check": dict(module="检索词清单", page="检索词清单校验", fields=[
        F("词表规模", "词表规模"), F("违规项", "违规项"),
        F("判据结论", "判据"), F("检索词清单", "检索词清单")]),

    # ── 业务语料 ──────────────────────────────────────────
    "skills.list": dict(module="业务语料", page="能力域清单", fields=[
        F("语料版本", "语料版本"), F("能力域", "能力域"),
        F("前置条件", "前置条件"), F("整束sha256", "sha256"), F("切片数", "切片数")]),
    "skills.read": dict(module="业务语料", page="语料正文", fields=[
        F("模式", "模式"), F("切片清单", "切片清单"),
        F("正文", "正文"), F("检索命中", "命中")]),

    # ── 工序契约 ──────────────────────────────────────────
    "playbook.list": dict(module="工序契约", page="契约清单", fields=[
        F("契约编号", "契约编号"), F("名称", "名称"),
        F("是否示例", "是否示例"), F("是否含写步骤", "是否含写步骤")]),
    "playbook.show": dict(module="工序契约", page="契约详情", fields=[
        F("契约全文", "契约"), F("落点路径", "路径"), F("校验结论", "校验")]),
    "playbook.validate": dict(module="工序契约", page="契约校验", fields=[
        F("检查结论", "检查结论"), F("问题明细", "问题")]),
    "playbook.run": dict(module="工序契约", page="契约执行", fields=[
        F("模式", "模式"), F("步骤明细", "步骤"),
        F("门禁", "门禁"), F("自检", "自检"), F("交付件落点", "交付件落点")]),
    "playbook.deliver": dict(module="工序契约", page="出件", fields=[
        F("交付物落点", "交付物落点"), F("行数", "行数"),
        F("sha256", "sha256"), F("出件自检", "出件自检")]),
    "playbook.selfcheck": dict(module="工序契约", page="契约引擎自证", fields=[
        F("期望结果", "期望"), F("实际结果", "实际"), F("不变量", "不变量")]),

    # ── 调度 ──────────────────────────────────────────────
    "sched.run": dict(module="调度", page="任务续跑", fields=[
        F("任务状态", "状态"), F("进度", "进度"),
        F("逐步明细", "逐步明细"), F("结果指纹", "结果指纹")]),
    "sched.retry": dict(module="调度", page="失败重试", fields=[
        F("本次跳过", "本次跳过"), F("结果指纹", "结果指纹"), F("步骤条数", "步骤条数")]),
    "sched.status": dict(module="调度", page="任务状态", fields=[
        F("任务列表", "任务列表"), F("状态计数", "状态计数"), F("逐步明细", "逐步明细")]),
    "sched.queue": dict(module="调度", page="统一队列", fields=[
        F("并发上限", "并发上限"), F("上限来源", "上限来源"),
        F("队列条目", "队列条目"), F("受管清单", "受管清单自证")]),

    # ── 宿主接入 ──────────────────────────────────────────
    "connect.list": dict(module="宿主接入", page="宿主状态", fields=[
        F("现算路径", "现算路径"), F("宿主", "宿主"),
        F("配置文件", "配置文件"), F("本产品条目数", "本产品条目数")]),
    "connect.print": dict(module="宿主接入", page="配置片段", fields=[
        F("宿主", "宿主"), F("配置片段", "片段"), F("片段sha256", "片段sha256")]),
    "connect.apply": dict(module="宿主接入", page="接入宿主", fields=[
        F("diff 明细", "diff"), F("快照落点", "快照"), F("回读对账", "回读对账")]),
    "connect.uninstall": dict(module="宿主接入", page="移除接入", fields=[
        F("将删片段", "片段"), F("diff 明细", "diff"), F("快照落点", "快照")]),
    "connect.doctor": dict(module="宿主接入", page="接入自检", fields=[
        F("逐项结论", "逐项结论"), F("证据", "证据"),
        F("修法", "修法"), F("总结论", "总结论")]),

    # ── 出包 ──────────────────────────────────────────────
    "pack.out": dict(module="出包", page="出包", fields=[
        F("计数", "计数"), F("规则表", "规则"), F("包根", "包根"),
        F("出包清单", "出包清单"), F("回读对账", "回读对账")]),
    "pack.check": dict(module="出包", page="包自检", fields=[
        F("五条断言", "五条断言"), F("判据", "判据"),
        F("通过与否", "通过与否"), F("证据", "证据")]),

    # ── 安装向导 ──────────────────────────────────────────
    "install.run": dict(module="安装向导", page="安装", fields=[
        F("入口与 PATH", "入口"), F("能力束", "能力束"),
        F("宿主接入", "宿主接入"), F("登录", "登录"), F("回读对账", "回读对账")]),
    "install.check": dict(module="安装向导", page="安装自检", fields=[
        F("四项判据", "判据"), F("证据", "证据"),
        F("总结论", "结论"), F("修法", "修法")]),
    "install.upgrade": dict(module="安装向导", page="升级", fields=[
        F("改指条目", "改指"), F("自检结论", "自检"), F("快照落点", "快照")]),

    # ── 需求入口 ──────────────────────────────────────────
    "intake.route": dict(module="需求入口", page="需求路由", fields=[
        F("候选工序", "候选工序"), F("前置条件", "前置条件"),
        F("缺件清单", "缺件清单"), F("可执行", "可执行"), F("置信度", "置信度")]),
    "intake.draft": dict(module="需求入口", page="契约草稿", fields=[
        F("草稿落点", "草稿落点"), F("校验结论", "校验"),
        F("取数步骤数", "取数步骤数"), F("待确认清单", "待你确认或补充")]),
    "intake.parity": dict(module="需求入口", page="模式对等", fields=[
        F("四组断言", "四组断言"), F("键比对", "键比对"), F("未落地项", "未落地项")]),
    "intake.catalog": dict(module="需求入口", page="工序目录", fields=[
        F("能力域", "能力域"), F("工序", "工序"),
        F("前置条件", "前置条件"), F("依据", "依据")]),

    # ── 命令清单 ──────────────────────────────────────────
    "schema.show": dict(module="命令清单", page="命令清单", fields=[
        F("模块", "module", order=SCHEMA_FIRST), F("命令", "command", order=SCHEMA_FIRST),
        F("参数", "options", order=SCHEMA_FIRST),
        F("是否写操作", "write", order=SCHEMA_FIRST), F("退出码", "exitCodes", order=SCHEMA_FIRST)]),
    "schema.mcp": dict(module="命令清单", page="MCP 工具清单", fields=[
        F("工具名", "name", order=SCHEMA_FIRST), F("描述", "description", order=SCHEMA_FIRST),
        F("入参结构", "inputSchema", order=SCHEMA_FIRST)]),
    "schema.dsh-tools": dict(module="命令清单", page="DSH 工具定义", fields=[
        F("工具名", "name", order=SCHEMA_FIRST), F("描述", "description", order=SCHEMA_FIRST),
        F("参数", "parameters", order=SCHEMA_FIRST)]),
    "schema.check": dict(module="命令清单", page="清单自证", fields=[
        F("差异清单", "差异清单"), F("结论", "结论")]),

    # ── 澄清 ──────────────────────────────────────────────
    "clarify.plan": dict(module="澄清", page="参数缺口清单", fields=[
        F("缺项", "缺项"), F("为什么问", "为什么问"),
        F("默认值", "默认值"), F("优先补", "优先补"), F("下一步", "下一步")]),
    "clarify.ask": dict(module="澄清", page="五类选择面追问", fields=[
        F("选择面", "选择面"), F("模式", "模式"), F("缺口", "缺口"),
        F("追问", "追问"), F("未确认项", "未确认项")]),
}

# 不面向业务用户的模块（平台/工具链）。它们仍逐条出现在 entries 里，只是 `internal: true`
# 且归到 `ops` 工作流，避免左栏把安装/自检显示成业务动作。
INTERNAL_MODULES = {
    "auth", "route", "takeover", "parity", "account", "skills", "playbook",
    "sched", "connect", "pack", "install", "intake", "schema",
}

# 离线计算/校验类命令（action=compute）；其余按 schema 的 write 标记分 read/write。
COMPUTE_COMMANDS = {
    "authenticity.channel", "authenticity.weights", "keywords.check", "parity.selfcheck",
    "parity.compare", "clarify.plan", "clarify.ask", "account.capabilities",
    "playbook.validate", "playbook.selfcheck", "playbook.run", "playbook.deliver",
    "intake.route", "intake.draft", "intake.catalog", "intake.parity",
    "sched.run", "sched.retry", "takeover.check", "schema.check",
}


# ─────────────────────────── 源码索引与取证 ───────────────────────────
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CJK_RE = re.compile(r"[\u4e00-\u9fa5]")


def tokens_of(line: str) -> set[str]:
    """从一行源码/文档里抽「可能是字段名」的 token。

    只收三类：① 引号里的标识符（name／channelTitle／本机会话文件）；② `--kebab-case` 参数；
    ③ 反引号里的标识符。**不收**带空格的句子、纯数字、markdown 链接。
    """
    out: set[str] = set()
    for m in re.finditer(r'"([^"\n]{1,40})"|\'([^\'\n]{1,40})\'', line):
        raw = m.group(1) if m.group(1) is not None else m.group(2)
        if IDENT_RE.match(raw):
            out.add(raw)
        elif CJK_RE.search(raw) and " " not in raw and len(raw) <= 24:
            out.add(raw)
    for opt in re.findall(r"--([a-z0-9][a-z0-9-]*)", line):
        out.add(opt)
    for ref in re.findall(r"`([^`\n]{1,60})`", line):
        ref = ref.strip()
        if IDENT_RE.match(ref):
            out.add(ref)
            continue
        if CJK_RE.search(ref) and " " not in ref and len(ref) <= 24:
            out.add(ref)
            continue
        # `key: value` / `key=value` 形态（60-data-layer 里大量这样写）只取键名：
        # 例如 `progressPercent: 50` → progressPercent；不取冒号后面的值。
        head = re.split(r"[:=]", ref, 1)[0].strip()
        if IDENT_RE.match(head):
            out.add(head)
            continue
        # `batches[0].currentStage` 这类路径取最后一段（限长标识符，避免把 list/id/get 这类
        # 通用词也收进来造成误命中）。
        tail = re.split(r"\.", head)[-1].strip(")（(） ").strip()
        if IDENT_RE.match(tail) and len(tail) >= 5:
            out.add(tail)
    return out


class SourceIndex:
    """文件 → token → 首个出现的行号（只做「证据在不在」，不做语义）。"""

    def __init__(self, path: Path):
        self.path = path
        self.lines = path.read_text(encoding="utf-8").splitlines()
        self.index: dict[str, list[int]] = {}
        for no, line in enumerate(self.lines, 1):
            for tok in tokens_of(line):
                self.index.setdefault(tok, []).append(no)

    def find(self, token: str) -> int | None:
        hits = self.index.get(token) or []
        return hits[0] if hits else None


def norm(text: str) -> str:
    """比对用的归一：折叠空白、去掉「的」与并列表述里的分隔符 —— 让「逐行 diff」与
    「逐行diff」、「关联视频的统计」与「关联视频统计」、「读／写结论」与「读写结论」能对上
    （只用于 schema 返回说明里的中文短语）。"""
    return re.sub(r"[\s的／/、·]", "", text or "")


class Gen:
    def __init__(self) -> None:
        self.schema_index = SourceIndex(PATH["schema"])
        self.route_index = SourceIndex(PATH["route"])
        self.dict_index = SourceIndex(PATH["dict"])
        self.module_index: dict[str, SourceIndex] = {}
        self.module_files: dict[str, Path] = {}
        for p in sorted((PATH["commands"].parent).glob("*.py")):
            key = p.stem.replace("mod_", "")
            self.module_index[key] = SourceIndex(p)
            self.module_files[key] = p
        # `_common.py` 是全部写命令共用的门禁链（deleteToken 等字段只在这里）；写命令取证时兜底查它。
        self.common_index = self.module_index.get("_common")

        self.phase_rows = load_phases()
        self.cap_entries = load_capmap()
        self.cap_links = capmap_links(self.cap_entries)

        self.modules = schema_mod.SCHEMA["modules"]
        self.commands: list[dict] = []
        for m in self.modules:
            for c in m["commands"]:
                self.commands.append({"module": m, "cmd": c,
                                      "id": "%s.%s" % (m["key"], c["name"])})

        # MCP 工具名由 schema 派生（与 exports 的同一份真源逐条核对，差一条就报）
        self.mcp_by_cli = {}
        for t in exports.mcp_payload()["tools"]:
            ann = t.get("annotations") or {}
            cli = str(ann.get("cli") or "").strip()
            m = re.match(r"daniel\s+(\S+)\s+(\S+)", cli)
            if m:
                self.mcp_by_cli["%s.%s" % (m.group(1), m.group(2))] = t["name"]

        # 0 条工作流的载体条目必须真的在能力地图里（否则 md 会写成空话）
        cap_ids = {e["id"] for e in self.cap_entries}
        for wid, ids, _why in ZERO_CARRIERS:
            missing = [i for i in ids if i not in cap_ids]
            if missing:
                raise SystemExit("工作流 %s 的载体条目不在 _CAPABILITY-MAP.json：%s"
                                 % (wid, "、".join(missing)))

    def _carriers(self, ids: list[str]) -> str:
        """把能力条目 id 渲染成「id（仪器）」串；仪器取包内能力地图的 instruments。"""
        out = []
        for e in self.cap_entries:
            if e["id"] not in ids:
                continue
            ins = [Path(str(x)).name for x in (e.get("instruments") or [])]
            out.append("`%s`%s" % (e["id"], "（%s）" % "、".join(ins) if ins else ""))
        return "；".join(out) or "—"

    # ── 单条命令的证据文本 ──────────────────────────────
    @staticmethod
    def cmd_text(cmd: dict) -> str:
        return " ".join([
            cmd.get("summary") or "", cmd.get("description") or "",
            cmd.get("returns") or "",
            " ".join(o["name"] for o in cmd.get("options") or []),
        ])

    def resolve(self, cmd_id: str, module_key: str,
                field: tuple[str, list[str], tuple[str, ...]]) -> tuple[str, str]:
        display, keys, order = field
        mod_idx = self.module_index.get(module_key)
        text = norm(self.cmd_text(self._cmd(cmd_id)))
        dict_text = norm(PATH["dict"].read_text(encoding="utf-8"))
        for tier in order:
            if tier == "code":
                for key in keys:
                    if mod_idx is not None:
                        line = mod_idx.find(key)
                        if line:
                            rel = self.module_files[module_key].relative_to(REPO)
                            return ("code", "%s:%d `%s`" % (rel, line, key))
                if self.common_index is not None:
                    for key in keys:
                        line = self.common_index.find(key)
                        if line:
                            rel = self.module_files["_common"].relative_to(REPO)
                            return ("code", "%s:%d `%s`" % (rel, line, key))
            elif tier == "route":
                for key in keys:
                    line = self.route_index.find(key)
                    if line:
                        return ("route", "%s:%d `%s`" % (REL["route"], line, key))
            elif tier == "schema":
                if norm(display) and norm(display) in text:
                    return ("schema", "%s %s 返回说明「%s」" % (REL["schema"], cmd_id, display))
                for key in keys:
                    if norm(key) and norm(key) in text:
                        return ("schema", "%s %s 返回说明「%s」" % (REL["schema"], cmd_id, key))
            elif tier == "dict":
                for key in keys:
                    line = self.dict_index.find(key)
                    if line:
                        return ("dict", "%s:%d `%s`" % (REL["dict"], line, key))
                if norm(display) and norm(display) in dict_text:
                    return ("dict", "%s 「%s」" % (REL["dict"], display))
        return ("inferred", "四个事实源里都没有该字段名")

    def _cmd(self, cmd_id: str) -> dict:
        for row in self.commands:
            if row["id"] == cmd_id:
                return row["cmd"]
        raise KeyError(cmd_id)

    # ── 生成 entries ────────────────────────────────────
    def entries(self) -> list[dict]:
        out = []
        for row in self.commands:
            cid = row["id"]
            if cid not in CURATED:
                raise SystemExit("策展表缺命令：%s（schema 有、映射表没有）" % cid)
            spec = CURATED[cid]
            mkey, cname = cid.split(".", 1)
            if cid not in CLASSIFY:
                raise SystemExit("归类表缺命令：%s（schema 有、CLASSIFY 没有）" % cid)
            wf_id, step = CLASSIFY[cid]
            wf_def = next((w for w in WORKFLOWS if w["id"] == wf_id), None)
            if wf_def is None:
                raise SystemExit("%s 指向未知工作流 %s" % (cid, wf_id))
            if not (0 <= step < len(wf_def["steps"])):
                raise SystemExit("%s 的步骤号越界：%s" % (cid, step))

            action = "write" if row["cmd"].get("write") else ("compute" if cid in COMPUTE_COMMANDS else "read")

            fields, evidence, inferred_fields = [], {}, []
            for f in spec["fields"]:
                display = f[0]
                if display in evidence:
                    raise SystemExit("%s 字段重复：%s" % (cid, display))
                tier, loc = self.resolve(cid, mkey, f)
                fields.append(display)
                evidence[display] = "%s: %s" % (tier, loc)
                if tier == "inferred":
                    inferred_fields.append(display)

            entry = {
                "id": cid,
                "match": {"kind": "cli", "command": "%s %s" % (mkey, cname)},
                "module": spec["module"],
                "page": spec["page"],
                "action": action,
                "workflow": {"id": wf_id, "step": step},
                "fields": fields,
                "summary": clean_summary(row["cmd"].get("summary") or ""),
                "workflowReason": workflow_reason(cid, wf_id, step, mkey),
            }
            if row["cmd"].get("write"):
                # 写链的开放级别（live＝真写／sandbox＝只落在沙箱）——左栏可以据此把「写」
                # 分成「会真改数据」与「沙箱演练」，不让用户误以为每次写都动了生产数据。
                entry["writeStage"] = row["cmd"].get("writeStage")
            if mkey in INTERNAL_MODULES:
                entry["internal"] = True
            tool = self.mcp_by_cli.get(cid)
            override = MCP_TOOL_OVERRIDE.get(cid)
            if override:
                entry["mcpTool"] = override[0]
                if override[1]:
                    entry["mcpTools"] = [override[0]] + list(override[1])
            elif tool:
                entry["mcpTool"] = tool
            entry["inferred"] = bool(inferred_fields)
            entry["fieldEvidence"] = evidence
            if inferred_fields:
                entry["inferredFields"] = inferred_fields
            out.append(entry)

        known_modules = {r["id"].split(".", 1)[0] for r in self.commands}
        for link in self.cap_links:
            missing = [m for m in link["modules"] if m not in known_modules]
            if missing:
                raise SystemExit("能力条目 %s 指向的模块在 schema 里没有命令：%s"
                                 % (link["id"], "、".join(missing)))

        extra_cls = sorted(set(CLASSIFY) - {r["id"] for r in self.commands})
        if extra_cls:
            raise SystemExit("CLASSIFY 里有 schema 不存在的命令：%s" % "、".join(extra_cls))
        missing_cls = sorted({r["id"] for r in self.commands} - set(CLASSIFY))
        if missing_cls:
            raise SystemExit("CLASSIFY 缺命令：%s" % "、".join(missing_cls))

        extra = sorted(set(CURATED) - {r["id"] for r in self.commands})
        if extra:
            raise SystemExit("策展表里有 schema 不存在的命令：%s" % "、".join(extra))
        if len(out) != EXPECTED_COMMANDS:
            raise SystemExit("命令条数变了：%d（期望 %d）。schema 是本表的真源，"
                             "请先复核改了什么再更新 EXPECTED_COMMANDS。"
                             % (len(out), EXPECTED_COMMANDS))
        return out

    # ── 统计 ────────────────────────────────────────────
    @staticmethod
    def stats(entries: list[dict]) -> dict:
        tier_counts = {t: 0 for t in TIERS}
        total_fields = 0
        inferred_rows = []
        for e in entries:
            for f in e["fields"]:
                total_fields += 1
                tier = e["fieldEvidence"][f].split(":", 1)[0]
                tier_counts[tier] = tier_counts.get(tier, 0) + 1
                if tier == "inferred":
                    inferred_rows.append((e["id"], f))
        by_action = {}
        by_wf = {}
        for e in entries:
            by_action[e["action"]] = by_action.get(e["action"], 0) + 1
            by_wf[e["workflow"]["id"]] = by_wf.get(e["workflow"]["id"], 0) + 1
        return {
            "commands": len(entries),
            "mapped": len(entries),
            "internal": sum(1 for e in entries if e.get("internal")),
            "business": sum(1 for e in entries if not e.get("internal")),
            "by_action": by_action,
            "by_workflow": by_wf,
            "fields_total": total_fields,
            "tiers": tier_counts,
            "inferred_rows": inferred_rows,
            "entries_with_inferred": sum(1 for e in entries if e["inferred"]),
            "mcp_tools": sum(1 for e in entries if e.get("mcpTool")),
        }

    # ── 输出 ────────────────────────────────────────────
    def build_json(self, entries: list[dict]) -> str:
        workflows = []
        for w in WORKFLOWS:
            item = dict(w)
            rows = AGENT_RATIONALE.get(w["id"])
            if rows:
                # 深拷贝一层：`trace` 是嵌套对象，避免产物与常量共享引用。
                item["agentRationale"] = [
                    {k: (dict(v) if isinstance(v, dict) else v) for k, v in row.items()}
                    for row in rows
                ]
            workflows.append(item)
        payload = {
            "schema": "daniel.workflow-map.v1",
            "generated_from": [REL["skill"], REL["capability"], REL["capmap"], REL["dict"],
                               REL["schema"], REL["commands"], REL["route"]],
            "workflows": workflows,
            "entries": entries,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    def build_md(self, entries: list[dict]) -> str:
        st = self.stats(entries)
        L: list[str] = []
        by_wf: dict[str, list[dict]] = {}
        for e in entries:
            by_wf.setdefault(e["workflow"]["id"], []).append(e)

        def wf_name(wid: str) -> str:
            return next(w["name"] for w in WORKFLOWS if w["id"] == wid)

        def step_name(wid: str, step: int) -> str:
            w = next(w for w in WORKFLOWS if w["id"] == wid)
            return w["steps"][step]

        L.append("# Daniel Bot 执行轨迹 · 字段级映射表（workflow-map）")
        L.append("")
        L.append("> 本文件由 `daniel-bot/app/scripts/gen-workflow-map.py` 生成，**勿手改**。")
        L.append("> 机器可消费版本：`daniel-bot/app/workflow-map.json`（schema `daniel.workflow-map.v1`）。")
        L.append("> 重跑：`python3 daniel-bot/app/scripts/gen-workflow-map.py`；核对：`… --check`。")
        L.append("> 工作流口径的**唯一来源**：A 包内 `mcp/corpus/kol-intelligence/SKILL.md` §1"
                 "（7 阶段总览，源 L68–L82）＋ 8 束 `kol-*` 语料；不使用另一条管线的模块名"
                 "（D-058/D-059，见 §九 9.3）。")
        L.append("")
        L.append("## 一、它解决什么")
        L.append("")
        L.append("左栏要在用户发一句话后实时显示：Bot 调了哪条命令 → 对应 Daniel 的哪个**模块/页面** → "
                 "正在读或写**哪些字段** → 处在**哪一阶段第几步**。本表就是这三层的对照：")
        L.append("")
        L.append("- `match`：命令面（CLI 写法；同时给 `mcpTool`，MCP 工具调用可落到同一条）；")
        L.append("- `module` / `page`：业务模块与页面（人读，不暴露内部模块键）；")
        L.append("- `fields`：左栏要显示的字段清单，逐条带 `fieldEvidence`（证据出处）；")
        L.append("- `workflow` / `step`：能力阶段与 0 起的步骤号；`workflowReason` 是逐条的归类依据。")
        L.append("")
        L.append("## 二、工作流定义（10 条）")
        L.append("")
        L.append("| id | 名称 | 步骤（`step` 为 0 起下标） | 命令数 |")
        L.append("|---|---|---|---|")
        for w in WORKFLOWS:
            steps = " → ".join("%d. %s" % (i, s) for i, s in enumerate(w["steps"]))
            L.append("| `%s` | %s | %s | %d |"
                     % (w["id"], w["name"], steps, len(by_wf.get(w["id"], []))))
        L.append("")
        L.append("**这 10 条怎么来的**：")
        L.append("")
        L.append("- 业务阶段链按 D-058：`stage0-product`（阶段 0）→ `discovery`（1）→ `screening`（2）→ "
                 "`outreach`（3）→ `negotiation`（4）→ `contract`（合同束）→ `execution`（5）→ "
                 "`sov`（6 与 7 合并：SOV 追踪 ＋ 热点/趋势）。")
        L.append("- `contract` **不在 7 阶段表的 8 行里**：8 束语料中 `kol-contract` 是独立能力束，"
                 "D-058 把它列为 A 阶段链的一环（谈判之后、执行之前），故单列一条。")
        L.append("- `data` 与 `ops` 是 D-058 指定的两个横向层：`data` ＝ 跨阶段的平台数据能力"
                 "（品牌／名单／提及／CT 等，同一份数据同时服务多个阶段）；`ops` ＝ 平台运维，"
                 "全部 `internal: true`（%d 条）。" % st["internal"])
        L.append("")
        L.append("## 三、能力地图 7 阶段 → 本表工作流")
        L.append("")
        L.append("| 阶段 | 名称（`SKILL.md` §1 逐字） | 工作流 | 该阶段命令数 |")
        L.append("|---|---|---|---|")
        for no, name in self.phase_rows:
            wid = PHASE_WORKFLOW[no]
            n = len(by_wf.get(wid, [])) if no in (1, 2, 3, 4, 5) else (
                len(by_wf.get(wid, [])) if no == 6 else 0)
            note = ""
            if no == 7:
                note = "（与 6 合并；热点复用 data 层的提及证据）"
            L.append("| %d | %s | `%s`%s | %d |" % (no, name, wid, note, n))
        L.append("")
        L.append("### 3.1 为什么有 5 条工作流是 0 条命令")
        L.append("")
        L.append("**CLI 是数据层，不是作业层**：阶段 0（产品说明）、3（外联）、4（谈判）、5（执行）"
                 "与 `contract` 的作业载体是 `.kol-tools/` 的仪器与 Skill 章节，不在 91 条命令里。"
                 "这不是漏映射，是边界——左栏若要把这些阶段也点亮，需要把下列仪器接成第二条轨迹源。")
        L.append("")
        L.append("| 工作流 | 0 条的原因 | 现有载体（能力条目 → 仪器） |")
        L.append("|---|---|---|")
        L.append("| `stage0-product` | CLI 没有「产品事实 → 说明块」的命令；产出是文档 | "
                 "方法在 `SKILL.md` §2.3；45 条能力条目里没有对应仪器 |")
        for wid, ids, why in ZERO_CARRIERS:
            L.append("| `%s` | %s | %s |" % (wid, why, self._carriers(ids)))
        L.append("")
        L.append("### 3.2 两个横向层为什么吸收这些命令")
        L.append("")
        L.append("- **`data` 吸收品牌/名单/提及/CT/情报**：这五组是「同一份数据被多个阶段读」的平台能力"
                 "（例如同一份名单同时服务发现落库、背调取人、外联取联系方式），按 D-058 归数据层，"
                 "不按「谁先用它」归阶段。")
        L.append("- **`ops` 吸收账号/安装/接入/出包/自检/工序引擎**：它们不产出 KOL 业务数据，"
                 "只维护运行环境；若塞进业务阶段，左栏会把运维动作显示成业务动作。")
        L.append("")
        L.append("### 3.3 45 条能力条目里的「Daniel 直连」条目 → CLI 模块")
        L.append("")
        L.append("| 能力条目 | 覆盖的 CLI 模块 | 该模块命令数 |")
        L.append("|---|---|---|")
        for link in self.cap_links:
            mods = "／".join(link["modules"])
            n = sum(1 for e in entries if e["id"].split(".", 1)[0] in link["modules"])
            L.append("| `%s` | %s | %d |" % (link["id"], mods, n))
        L.append("")
        L.append("其余 %d 条能力条目（邮件、合同、交付物预检、维护卫生…）不对应 CLI 命令；"
                 "本表不把它们硬塞进 entries——左栏只在 Bot 真的调 Daniel 命令时才有字段可显示。"
                 % (len(self.cap_entries) - len(self.cap_links)))
        L.append("")
        L.append("## 四、覆盖统计")
        L.append("")
        L.append("| 项 | 数 | 说明 |")
        L.append("|---|---|---|")
        L.append("| CLI 命令总数 | %d | `daniel schema --check` 声明的集合（脚本断言） |" % st["commands"])
        L.append("| 已映射 | %d | 每条都有 module/page/action/workflow/fields/workflowReason |" % st["mapped"])
        L.append("| 其中 `internal` | %d | 平台/工具链，不面向业务用户 |" % st["internal"])
        L.append("| 业务命令 | %d | 会出现在业务左栏 |" % st["business"])
        L.append("| 未映射 | %d | 无（两种漂移都会让脚本失败） |" % (st["commands"] - st["mapped"]))
        L.append("| 带 MCP 工具名 | %d | `daniel_<模块>_<命令>`，与 `schema.mcp` 同源 |" % st["mcp_tools"])
        L.append("")
        L.append("**动作分布**：" + "／".join("%s %d" % (k, v) for k, v in sorted(st["by_action"].items())) + "。")
        L.append("")
        L.append("**未映射命令清单**：无（0 条）。脚本对「schema 有、CLASSIFY 没有」与"
                 "「CLASSIFY 有、schema 没有」两种漂移都会直接失败，不会静默输出半张表。")
        L.append("")
        L.append("### 按模块（命令数）")
        L.append("")
        L.append("| 模块 | 命令数 | 其中 internal |")
        L.append("|---|---|---|")
        by_mod: dict[str, list[dict]] = {}
        for e in entries:
            by_mod.setdefault(e["module"], []).append(e)
        for mod, rows in by_mod.items():
            L.append("| %s | %d | %d |"
                     % (mod, len(rows), sum(1 for r in rows if r.get("internal"))))
        L.append("")
        L.append("## 五、字段证据覆盖")
        L.append("")
        L.append("字段**不是手写的**：每条字段都在生成时到四个事实源里查一遍，按 "
                 "`code`（commands/*.py 的键/参数）→ `route`（60-data-layer.md 返回字段）→ "
                 "`schema`（schema.py 该命令的返回说明）→ `dict`（字段字典）取第一个命中；"
                 "四级都没有才标 `inferred`。")
        L.append("")
        L.append("> 行号是该键在文件里**首次出现**的位置（证明确实有这个字段名），不保证就是本命令的"
                 "读写行；要看读写点，按同一个键在该文件里再搜。")
        L.append("")
        L.append("| 证据档位 | 字段数 | 占比 |")
        L.append("|---|---|---|")
        for t in TIERS:
            n = st["tiers"][t]
            L.append("| `%s`（%s） | %d | %.1f%% |"
                     % (t, TIER_LABEL[t], n, 100.0 * n / max(1, st["fields_total"])))
        L.append("| **合计** | **%d** | 100%% |" % st["fields_total"])
        L.append("")
        strong = st["tiers"]["code"] + st["tiers"]["route"]
        L.append("> `dict` 档 0 命中是**预期**：字段字典集中在频道画像（均播/受众/兴趣），对应到本表"
                 "就是 `lists.items` 的几项，而它们已被 `route` 档先命中（同一批字段在 60-data-layer 里"
                 "也有）。字典在本表的实际用途是**核对展示名与源字段**（§11 规范字段表）＋ §6.7 的"
                 "`brands.list` 实测返回（`targetCountries`／`sampleCost`）；它仍列在 `generated_from` 里。")
        L.append("")
        L.append("**口径**：`code`＋`route` 是「接口/命令里真实存在的字段名」，合计 **%d/%d（%.1f%%）**；"
                 "`schema` 与 `dict` 是文件里逐字存在的业务字段描述（仍可追溯，只是不是接口键本身）；"
                 "`inferred` 为 **%d/%d（%.1f%%）**。"
                 % (strong, st["fields_total"], 100.0 * strong / max(1, st["fields_total"]),
                    st["tiers"]["inferred"], st["fields_total"],
                    100.0 * st["tiers"]["inferred"] / max(1, st["fields_total"])))
        L.append("")
        weak = [e for e in entries
                if all(e["fieldEvidence"][f].split(":", 1)[0] in ("schema", "dict") for f in e["fields"])]
        weak_biz = [e for e in weak if not e.get("internal")]
        biz_fields = [f for e in entries if not e.get("internal") for f in e["fields"]]
        biz_strong = sum(1 for e in entries if not e.get("internal") for f in e["fields"]
                         if e["fieldEvidence"][f].split(":", 1)[0] in ("code", "route"))
        biz_ratio = 100.0 * biz_strong / max(1, len(biz_fields))
        if st["inferred_rows"]:
            L.append("### 标 `inferred: true` 的清单")
            L.append("")
            L.append("| 命令 | 字段 | 为什么拿不到证据 |")
            L.append("|---|---|---|")
            for cid, f in st["inferred_rows"]:
                L.append("| `%s` | %s | 四个事实源里都没有该字段名 |" % (cid, f))
            L.append("")
        else:
            L.append("### 标 `inferred: true` 的清单")
            L.append("")
            L.append("无。全部字段都能在四个事实源里逐字查到。")
            L.append("")
        L.append("> **证据边界**：`daniel_cli/commands/*.py` 对 intel／sov／ct 是**薄壳**——"
                 "真正的字段读写在 `.kol-tools/daniel_*.py` 仪器里，而它不在任务给定的四个事实源内，"
                 "本表**不把它算作证据**（否则等于偷偷换真源）。下面这 %d 条要升到 `code` 档，"
                 "得先决定是否把仪器源码纳入证据源。" % len(weak_biz))
        L.append("")
        L.append("**只看业务命令（%d 条，%d 个字段）**：`code`＋`route` 强证据 **%d/%d（%.1f%%）**，"
                 "其余 %d 个字段来自这些命令自己的返回说明。%s"
                 % (st["business"], len(biz_fields), biz_strong, len(biz_fields), biz_ratio,
                    len(biz_fields) - biz_strong,
                    "业务左栏可以放心用这一档。" if biz_ratio >= 80
                    else "也就是说：榜单/统计/画像类命令（intel／sov／ct／authenticity）的接口字段名"
                         "不在 CLI 源码里（它们复用 `.kol-tools/` 仪器），只能以命令返回说明为据——"
                         "这类条目**建议用真实返回再核一遍**，见下面的弱证据清单。"))
        L.append("")
        if weak:
            L.append("**证据最弱的一档（全部字段只有 `schema`/`dict` 档，建议人工复核）**：共 %d 条"
                     "（业务 %d 条、平台 %d 条）。业务那 %d 条是要优先复核的：它们的接口键在 "
                     "`commands/*.py` 与 60-data-layer 里都没有，只有命令返回说明"
                     "（例外：`clarify` 两条的键其实在 `daniel_cli/clarify.py`，但按本表 code 档口径"
                     "只认 `commands/*.py`，故仍列在这里）。"
                     % (len(weak), len(weak_biz), len(weak) - len(weak_biz), len(weak_biz)))
            L.append("")
            L.append("| 命令 | 页面 | 范围 | 字段数 |")
            L.append("|---|---|---|---|")
            for e in weak:
                L.append("| `%s` | %s | %s | %d |"
                         % (e["match"]["command"], e["page"],
                            "平台" if e.get("internal") else "**业务**", len(e["fields"])))
            L.append("")
        L.append("## 六、映射表（按模块分组）")
        L.append("")
        L.append("证据列写作 `code/route/schema/dict` 的字段数；`⚠️N` 表示该条有 N 个推断字段。"
                 "归类依据逐条见 §七。")
        L.append("")
        for mod, rows in by_mod.items():
            L.append("### %s（%d 条）" % (mod, len(rows)))
            L.append("")
            L.append("| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |")
            L.append("|---|---|---|---|---|---|")
            for e in rows:
                tiers = {t: 0 for t in TIERS}
                for f in e["fields"]:
                    tiers[e["fieldEvidence"][f].split(":", 1)[0]] += 1
                ev = " / ".join("%s %d" % (t, tiers[t]) for t in TIERS if tiers[t])
                if e["inferred"]:
                    ev += " ⚠️%d" % len(e.get("inferredFields") or [])
                wid, step = e["workflow"]["id"], e["workflow"]["step"]
                L.append("| `%s` | %s | %s | %s · %d %s | %s | %s |"
                         % (e["match"]["command"], e["page"], e["action"], wf_name(wid),
                            step, step_name(wid, step), "、".join(e["fields"]), ev))
            L.append("")
        L.append("## 七、归类依据（91 条逐条）")
        L.append("")
        L.append("按工作流分组；每条给「命令 → 阶段 · 步 → 为什么」。")
        L.append("")
        for w in WORKFLOWS:
            rows = by_wf.get(w["id"], [])
            if not rows:
                continue
            L.append("### %s（`%s`，%d 条）" % (w["name"], w["id"], len(rows)))
            L.append("")
            L.append("| 命令 | 阶段 · 步 | 归类依据 |")
            L.append("|---|---|---|")
            for e in rows:
                wid, step = e["workflow"]["id"], e["workflow"]["step"]
                L.append("| `%s` | %s · %d %s | %s |"
                         % (e["match"]["command"], wf_name(wid), step,
                            step_name(wid, step), e["workflowReason"]))
            L.append("")
        L.append("## 八、助手自写阶段的依据")
        L.append("")
        L.append("这 5 个阶段**没有随包仪器**，作业由助手按能力语料自己完成（§3.1 的「0 条命令」）。"
                 "左栏对它们不显示工具调用，只显示一句「本阶段由助手完成」，再加下面这张表——"
                 "让用户看到**助手是怎么判断的**，而不是依据出自哪份文件。")
        L.append("")
        L.append("| 阶段 | 这一条讲什么 | 我为什么这么写 | 产出物 |")
        L.append("|---|---|---|---|")
        for wid in AGENT_RATIONALE_WORKFLOWS:
            name = wf_name(wid)
            rows = AGENT_RATIONALE.get(wid) or []
            for row in rows:
                if "missing" in row:
                    L.append("| %s | — | 缺依据：%s | — |" % (name, row["missing"]))
                    continue
                L.append("| %s | %s | %s | %s |"
                         % (name, row["title"], row["thinking"], row["output"]))
        L.append("")
        L.append("**口径**：写成第一人称的判断过程——我怎么看这件事、为什么这样更好、不这样会怎样。"
                 "**文件名、章节号、内部代号一概不出现**：用户不需要知道依据出自哪份文件，"
                 "只需要知道这个人为什么这么写。")
        L.append("")
        L.append("如果左栏要实现「本阶段由助手完成」这一态，消费 `workflows[].agentRationale` 即可："
                 "`title` 是这条的小标题，`thinking` 是展示正文，`output` 是产出物。"
                 "`trace`（文件:行号）只给 QA 回溯，**不进左栏**。")
        L.append("")
        L.append("> 生成器断言：5 个阶段每个至少 1 条依据（或显式标 `missing`）、最多 3 条；"
                 "`title`／`thinking`／`output` 命中内部标识正则（`SKILL`、`§`、`CLS-`、`TICKET-`、"
                 "`*.md` 等）或空话词表（「按照标准」「依据规范」「确保质量」等）即失败；"
                 "`thinking` 少于 40 字即失败；`trace` 必须落在随包语料里、行号存在且该行非空，否则失败。")
        L.append("")
        L.append("## 九、不确定项（需要知道的判断）")
        L.append("")
        L.append("### 9.1 字段级")
        L.append("")
        if st["inferred_rows"]:
            for cid, f in st["inferred_rows"]:
                L.append("- `%s` · %s：接口/命令/返回说明里都没有字段名，按命令语义推断，"
                         "**不得当作接口字段对外承诺**。" % (cid, f))
        else:
            L.append("- 无字段级推断：全部字段都能在四个事实源里逐字查到。")
            L.append("- 但「能查到」不等于「是接口键」：有 %d 条命令的字段只有 `schema` 档证据"
                     "（见 §五的弱证据清单），其中 %d 条是业务命令。这批字段在接入真实返回时"
                     "要再核一遍键名，尤其是 intel／sov／ct／authenticity 四组。"
                     % (len(weak), len(weak_biz)))
        L.append("")
        L.append("### 9.2 映射级（不是字段问题，而是编辑判断）")
        L.append("")
        L.append("- **`lists.*` 归 `data` 而不归 `discovery`**：能力地图阶段 1 的产出含「名单产线」，"
                 "但同一份名单同时服务发现落库、背调取人、外联取联系方式；按 D-058 的「跨阶段平台能力」"
                 "口径归 `data`，不按「谁先用」归阶段。")
        L.append("- **`ct.*` 归 `data` 而不归 `execution`**：CT 的订单/视频/统计确实是执行期回收的数据，"
                 "但它同时被 SOV 与复盘复用；D-058 明确把 CT 列入数据层。")
        L.append("- **`intel.*` 归 `data`**：Action Center（动作/关键词/选题/审核单）跨阶段复用，"
                 "无法唯一归到某一阶段。")
        L.append("- **`sov.categories` 放 0「固定竞争集」**（品类档案与登记竞品是 SOV 的口径起点），"
                 "其余 `sov.*` 放 1「份额与情感」。")
        L.append("- **`authenticity.weights` 放 0「评分卡」**（权重口径），`authenticity.channel` 放 1"
                 "「真实性核验」。")
        L.append("- **`discovery` 的「名单产线」与 `screening` 的「shortlist」两步 0 条**：名单读写统一归"
                 "`data`；shortlist 的落盘是文档产出，不是命令。")
        L.append("- **`authenticity.channel` 的动作标 `compute`**：它读频道数据后用前端口径**当场复算**"
                 "（60-data-layer §15.5 实测：该页不落库、分数前端自算），所以不是纯 read。")
        L.append("- **`playbook.run` 是 `write` 但只写沙箱**：schema 的 `writeStage=sandbox`（写动作只落在"
                 "本次运行的沙箱目录），条目里带 `writeStage` 就是给左栏区分「真写」与「沙箱演练」用的；"
                 "其余 22 条写命令都是 `live`。")
        L.append("")
        L.append("### 9.3 禁用词说明（D-058/D-059）")
        L.append("")
        L.append("本表**禁用**另一条管线（B 管线）的模块名：建联 / 舆情 / VOC。A 的能力只按包内能力地图"
                 "命名；这些词出现在本表即视为污染（隔离契约 D-058/D-059）。生成器里已加断言："
                 "`workflow-map.json` 出现任一禁用词即拒绝写盘。")
        L.append("")
        L.append("## 十、最容易错的两处（写映射时踩过的坑）")
        L.append("")
        L.append("### 坑 1：`returns` 文本 ≠ 实际返回字段（少写字段）")
        L.append("")
        L.append("`daniel brands list` 的 `schema.py` 返回说明只写「品牌编号、品牌名、所属工作区编号与名称」，"
                 "但 60-data-layer §15.3.2 的 `brands.list` 实际返回含 `category`／`competitors[]`，"
                 "`_DANIEL-FIELD-DICTIONARY.md` §6.7 的实测返回还含 `sampleCost`／`targetCountries`。"
                 "**只按 `returns` 建表，左栏会漏掉「品类/目标市场/竞品/样品价」四项**——这正是本表"
                 "把 `route` 与 `code` 排在 `schema` 之前的原因。")
        L.append("")
        L.append("反向的坑同样致命：`tier` 在写库（`lists.batchAddItems.tier`）里是**数字 1–4**，"
                 "在界面上是**档名**（Mega/Macro/Mid/Micro，且展示分档的分界与写库分界不是同一套，"
                 "见 60-data-layer §15.3.4）。同名字段两套取值域，左栏若直接显示数字会与用户看到的档名对不上。")
        L.append("")
        L.append("### 坑 2：同一个「名单编号」在不同命令里键名不同")
        L.append("")
        L.append("`lists.rename` 用 `listId`，而 `lists.delete` **必须用 `id`**（60-data-layer §15.5 硬限 #2："
                 "传 `listId` → 400）；`lists.create` 的入参是 `brandId`＋`name`。"
                 "同一个业务概念「名单编号」，三条命令对应两个键名——若按「字段名统一」去渲染或回填，"
                 "删除会静默 400。同类还有 `ct.resolve-channel` 的入参键是 `channelInput`（不是 `input`，"
                 "语料里写错过，见 `mod_ct.py` 的 docstring）。")
        L.append("")
        L.append("### 附带一条口径提醒")
        L.append("")
        L.append("`mentions.results` 的默认口径是 `confirmed_likely`（只回与本品相关的提及），"
                 "`all` 才是全量；两者字段一样但**条数不同**（实测 96 vs 114，60-data-layer §15.5.8 第 4 条）。"
                 "左栏若要显示「读取 N 条」，必须带上口径，否则用户会以为数据丢了。")
        L.append("")
        L.append("## 十一、生成方法（哪一步从哪个文件取）")
        L.append("")
        L.append("| 步骤 | 取什么 | 从哪取 |")
        L.append("|---|---|---|")
        L.append("| 1 | 91 条命令、模块、摘要、是否写操作、参数、返回说明 | "
                 "`daniel_cli/schema.py`（`SCHEMA.modules[].commands[]`；脚本 import 后遍历，不手抄） |")
        L.append("| 2 | MCP 工具名 | `daniel_cli/exports.py::mcp_payload()` 的 `annotations.cli` "
                 "（与 `schema.py` 同一真源，逐条核对） |")
        L.append("| 3 | 模块/页面的业务命名 | 票面示例（`品牌资产 · 品牌列表`）＋ `schema.py` 的模块 `title` "
                 "＋ Daniel 页面语义 |")
        L.append("| 4 | 7 阶段名称与顺序 | A 包内 `mcp/corpus/kol-intelligence/SKILL.md` §1（源 L68–L82）"
                 "＋ 其逐字切片 `references/02-capability-map.md`（两处必须一致，脚本断言） |")
        L.append("| 5 | 工作流归类（91 条） | `CLASSIFY` 表（生成器内唯一真源）；逐条依据写在 "
                 "`workflowReason`，按 `MODULE_REASON` ＋ `REASON_OVERRIDE` 生成 |")
        L.append("| 6 | 能力层覆盖核对 | `_CAPABILITY-MAP.json`（断言 45 条）里以 Daniel 仪器为载体的"
                 "条目 → CLI 模块（§3.3）；指到的模块若一条命令都没有即失败 |")
        L.append("| 7 | 字段候选键 | `daniel_cli/commands/*.py`（payload/emit 键）＋ "
                 "`60-data-layer.md`（路由返回字段）＋ `_DANIEL-FIELD-DICTIONARY.md`（规范字段名的源字段列） |")
        L.append("| 8 | 字段取证（逐字段） | 生成时按 `code → route → schema → dict` 查索引，"
                 "命中即写 `fieldEvidence`（文件:行号）；四级不中才 `inferred` |")
        L.append("| 9 | 覆盖与隔离自证 | 断言「schema 命令集 ≡ CLASSIFY 命令集」且条数＝91；"
                 "断言 JSON 无禁用词；跑 `node scripts/check-isolation.mjs` 须 6/6 |")
        L.append("")
        L.append("**没有修改 `daniel-bot/packages/0.11.0/` 下的任何文件**：脚本只读该目录，"
                 "产出全部落在 `daniel-bot/app/`。")
        L.append("")
        return "\n".join(L) + "\n"


def clean_summary(text: str) -> str:
    """去掉 schema 摘要里「（写操作／…）」「（只读…）」这类操作提示——动作已由 `action` 表达。"""
    def fix(m: re.Match) -> str:
        inner = m.group(1)
        if "写操作" not in inner and "只读" not in inner:
            return m.group(0)          # 与操作无关的括号（字段枚举等）原样保留
        parts = [p.strip() for p in re.split(r"[；;／/，,]", inner) if p.strip()]
        kept = [p for p in parts if "写操作" not in p and "只读" not in p]
        return "（%s）" % "；".join(kept) if kept else ""
    out = re.sub(r"（([^（）]*)）", fix, text)
    return re.sub(r"\s+", " ", out).strip()


#: 隔离契约 D-058/D-059：A 的能力标签**禁用**另一条管线的模块名。
#: 生成器里加断言（ISOLATION.md §四「词汇互借：改文案，并加断言」）。
BANNED_TERMS = ("建联", "舆情", "VOC")


def assert_no_banned(text: str, label: str, allow_marked: bool = False) -> None:
    """逐行扫禁用词。`allow_marked=True` 时只放行含「禁用」二字的行（md 的禁用词说明段）。"""
    for i, line in enumerate(text.splitlines(), 1):
        for term in BANNED_TERMS:
            if term in line and not (allow_marked and "禁用" in line):
                raise SystemExit("%s 第 %d 行出现禁用词「%s」：%s"
                                 % (label, i, term, line.strip()[:160]))


def _rationale_brief() -> str:
    """一行摘要：5 个阶段各几条依据、有没有 missing。"""
    parts, missing = [], []
    for wid in AGENT_RATIONALE_WORKFLOWS:
        rows = AGENT_RATIONALE.get(wid) or []
        miss = [r for r in rows if "missing" in r]
        if miss:
            missing.append(wid)
        parts.append("%s %d 条" % (wid, len(rows) - len(miss)))
    tail = "｜missing：%s" % "、".join(missing) if missing else "｜missing：无"
    return "／".join(parts) + tail


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 Daniel Bot workflow-map.json / .md")
    ap.add_argument("--check", action="store_true", help="只核对磁盘产物是否与重算一致（不写文件）")
    args = ap.parse_args()

    assert_rationale()
    gen = Gen()
    entries = gen.entries()
    js = gen.build_json(entries)
    md = gen.build_md(entries)
    assert_no_banned(js, "workflow-map.json")
    assert_no_banned(md, "workflow-map.md", allow_marked=True)

    if args.check:
        bad = []
        for path, want in ((OUT_JSON, js), (OUT_MD, md)):
            if not path.exists():
                bad.append("%s 不存在" % path)
            elif path.read_text(encoding="utf-8") != want:
                bad.append("%s 与重算结果不一致（请重跑脚本）" % path)
        if bad:
            print("✗ " + "\n✗ ".join(bad), file=sys.stderr)
            return 1
        print("✓ workflow-map.json / workflow-map.md 与重算一致（%d 条）" % len(entries))
        print("  助手自写阶段依据：%s" % _rationale_brief())
        return 0

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(js, encoding="utf-8")
    OUT_MD.write_text(md, encoding="utf-8")

    st = gen.stats(entries)
    print("✓ 写入 %s" % OUT_JSON.relative_to(REPO))
    print("✓ 写入 %s" % OUT_MD.relative_to(REPO))
    print("  命令 %d 条｜internal %d｜业务 %d｜未映射 0"
          % (st["commands"], st["internal"], st["business"]))
    print("  字段 %d 个｜code %d｜route %d｜schema %d｜dict %d｜inferred %d"
          % (st["fields_total"], st["tiers"]["code"], st["tiers"]["route"],
             st["tiers"]["schema"], st["tiers"]["dict"], st["tiers"]["inferred"]))
    print("  助手自写阶段依据：%s" % _rationale_brief())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
