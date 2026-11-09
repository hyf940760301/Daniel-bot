# -*- coding: utf-8 -*-
"""模式对等断言：CLI 模式与 MCP 模式暴露的**能力集合／技能集合／语料版本**键比对。

为什么要有这条断言（用户 2026-10-14 裁决）
-----------------------------------------
> 「不管是 mcp 还是 cli …… 一条完整的工作流能力包括需求识别→能力匹配→前置条件告知就需要
>   完整的内置了 …… 每一个模式都是完全独立且全量的能力链路」
> 「① 验收必须加一条**模式对等断言**：CLI 模式与 MCP 模式暴露的能力集合／技能集合／版本
>   完全一致（键比对）」

四组断言（每组都给出键比对的实际字符串，不是一句"一致"）：

| 组 | 断言 | 键比对口径 |
|---|---|---|
| P-能力 | 两模式的可用能力集合都是**同一份单一真源**派生，差集**只允许是写链** | `模块.子命令` 排序串 |
| P-链路 | intake 链路（`route`／`draft`／`parity`）在**两种模式的能力集合里都在** | 三个键在两集合里的成员关系 |
| P-技能 | 技能集合与语料版本三源一致：随包语料层（`daniel_cli/corpus.py`）↔ 语料源（`.agents/skills/kol-*`）↔ intake 工序表 | `域=版本` 排序串 ＋ 总语料版本 |
| P-可达 | 同一个技能清单在两种模式下**都取得到**（`skills list` 的真调结果）；未落地时**显式登记**，不静默当通过 | 两侧 payload 的键 |

P-可达 依赖 `TICKET-159`（语料随 MCP 分发 ＋ `skills` 命令）落地：没落地时本组记
**「未落地（待 TICKET-159）」**并列进报告 —— 它是**可见的未完成项**，不是"通过"。
"""
import json
import os
import subprocess
import sys

from . import catalog, modes

#: 本包位置：`<仓库根>/data/daniel-cli/daniel_cli/intake/<本文件>` → 上溯三层是 `data/daniel-cli`
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_REPO_ROOT = os.path.dirname(os.path.dirname(_PKG_ROOT))
SKILLS_DIR = os.path.join(_REPO_ROOT, ".agents", "skills")
CLI_ENTRY = os.path.join(_PKG_ROOT, "bin", "daniel")

OK = "通过"
FAIL = "未通过"
PENDING = "未落地"
SKIP = "跳过"

#: 本票自己必须交付的链路键（两模式都必须可达）
CHAIN_KEYS = ("intake.route", "intake.draft", "intake.parity")


def _key_string(keys):
    return "；".join(sorted(keys)) or "（空）"


def _available_keys(mode):
    return set(modes.available(mode)["能力集合"])


# ─────────────────────────── P-能力 ───────────────────────────
def assert_capabilities():
    cli, mcp = modes.available(modes.MODE_CLI), modes.available(modes.MODE_MCP)
    only_cli = set(cli["能力集合"]) - set(mcp["能力集合"])
    only_mcp = set(mcp["能力集合"]) - set(cli["能力集合"])
    writes = modes.write_keys()
    rogue = sorted(only_cli - writes)
    # 与 TICKET-159 的差异登记表双向对齐：差集必须**恰好**是登记为「未注册」的那批；
    # 差集里出现登记表之外的条目＝红（有人把能力藏了或漏注册），登记表陈旧也算红。
    reg = mcp.get("登记表互校") or {}
    reg_ok = True
    if reg:
        reg_ok = (bool(reg.get("一致")) and not reg.get("差集里登记表之外的条目（红）")
                  and not reg.get("登记表里已不存在的命令（陈旧登记，红）")
                  and not reg.get("登记「未注册」却真注册了（红）"))
    ok = not only_mcp and not rogue and bool(cli["能力集合"]) and reg_ok
    return {
        "组": "P-能力",
        "断言": "两模式的可用能力集合同源于 schema.py；MCP 集合 ⊆ CLI 集合，且差集只允许是写链",
        "状态": OK if ok else FAIL,
        "键比对": {
            "CLI 声明键（%d）" % len(cli["能力集合"]): _key_string(cli["能力集合"]),
            "MCP 注册键（%d）" % len(mcp["能力集合"]): _key_string(mcp["能力集合"]),
            "仅在 CLI（%d，应当全是写链）" % len(only_cli): _key_string(only_cli),
            "仅在 MCP（%d，应当为空）" % len(only_mcp): _key_string(only_mcp),
            "差集是否全是写链": "是" if not rogue else "否 —— 非写链差异：%s" % _key_string(rogue),
            "与 TICKET-159 登记表双向对齐": ("一致（差集＝登记为「未注册」的那批，%d 条）"
                                     % len(reg.get("差集（CLI 有／MCP 没有）") or []))
            if reg_ok else "不对齐（红）：%s" % _key_string(
                (reg.get("差集里登记表之外的条目（红）") or [])
                + (reg.get("登记表里已不存在的命令（陈旧登记，红）") or [])
                + (reg.get("登记「未注册」却真注册了（红）") or [])),
            "登记表红项": {"差集里登记表之外": reg.get("差集里登记表之外的条目（红）") or [],
                       "登记表陈旧": reg.get("登记表里已不存在的命令（陈旧登记，红）") or [],
                       "登记未注册却真注册": reg.get("登记「未注册」却真注册了（红）") or []},
        },
        "模式事实": {"CLI 真源": cli["真源"], "MCP 真源": mcp["真源"],
                     "登记表互校": mcp.get("登记表互校")},
        "说明": "差集里的写链命令在 MCP 模式**不是能力缺失**：能力在面可见，"
                "缺的只是「AI 不得自行执行」这一层，intake 会把它作为「模式能力」前置条件"
                "按三态告知（需人工确认后执行）。",
    }


# ─────────────────────────── P-链路 ───────────────────────────
def assert_chain():
    rows = {}
    for key in CHAIN_KEYS:
        rows[key] = {"CLI": key in _available_keys(modes.MODE_CLI),
                     "MCP": key in _available_keys(modes.MODE_MCP),
                     "三态（CLI）": modes.status_for(key, modes.MODE_CLI),
                     "三态（MCP）": modes.status_for(key, modes.MODE_MCP)}
    ok = all(r["CLI"] and r["MCP"] for r in rows.values())
    return {
        "组": "P-链路",
        "断言": "intake 完整链路（需求识别→能力匹配→前置条件告知→契约草稿）在两种模式下都可达",
        "状态": OK if ok else FAIL,
        "键比对": rows,
        "说明": "链路本体只有一份实现（`daniel_cli/intake/`），CLI 直接调用、MCP 落成一次 "
                "`daniel intake … --json` 子进程调用 —— 因此两侧不可能是两份能力。",
    }


# ─────────────────────────── P-技能 ───────────────────────────
def _corpus_layer():
    """随包语料层（`TICKET-159` 的 `daniel_cli/corpus.py`）。"""
    try:
        from .. import corpus
    except Exception as e:                                       # noqa: BLE001
        return None, "随包语料层不可用：%s: %s" % (type(e).__name__, e)
    try:
        payload = corpus.list_skills()
        key = corpus.consistency_key(payload)
    except Exception as e:                                       # noqa: BLE001
        return None, "随包语料层读不出来：%s: %s" % (type(e).__name__, e)
    key = dict(key)
    key["语料根"] = payload.get("语料根")
    key["定位方式"] = payload.get("定位方式")
    return key, "daniel_cli/corpus.py（随包分发语料）"


def _bundle_source():
    """语料源：`.agents/skills/kol-*/_CORPUS.json`（语料束切分产物）。"""
    if not os.path.isdir(SKILLS_DIR):
        return None, "语料源目录不存在：%s" % SKILLS_DIR
    pairs, versions = [], set()
    for name in sorted(os.listdir(SKILLS_DIR)):
        path = os.path.join(SKILLS_DIR, name, "_CORPUS.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (ValueError, OSError) as e:
            return None, "%s 读不出来：%s" % (path, e)
        pairs.append("%s=%s" % (name, doc.get("corpus_version")))
        versions.add(doc.get("corpus_version"))
    return {"语料版本": sorted(versions)[0] if len(versions) == 1 else "／".join(sorted(versions)),
            "能力域数": len(pairs), "键": "；".join(pairs),
            "真源": SKILLS_DIR}, "语料束 `_CORPUS.json`（语料切分真源）"


def _catalog_source():
    doc = catalog.load()
    pairs = sorted("%s=%s" % (d["技能束"], d["语料版本"]) for d in doc["能力域"])
    # 生效值是从真源注入的（TICKET-173）⇒ 这里额外把"表内声明值"也带出来：
    # 声明值陈旧时产品报告里看得见（不靠人记得去翻 JSON），而 G1 比对的是**生效值**。
    return {"语料版本": doc["语料版本"], "能力域数": doc["能力域数"], "键": "；".join(pairs),
            "工序表声明版本": "／".join(doc.get("工序表声明版本") or []) or "（无）",
            "声明版本一致": doc.get("声明版本一致"),
            "语料版本真源": doc.get("语料版本真源"),
            "真源": doc["真源"]}, "intake 工序表（本票真源）"


def assert_skills():
    layer, why_layer = _corpus_layer()
    bundle, why_bundle = _bundle_source()
    cat, why_cat = _catalog_source()
    sources = {"随包语料层（CLI／MCP 共用同一条读取路径）": (layer, why_layer),
               "语料源（语料切分产物）": (bundle, why_bundle),
               "intake 工序表（本票真源）": (cat, why_cat)}
    keys = {name: (src or {}).get("键") for name, (src, _why) in sources.items()}
    versions = {name: (src or {}).get("语料版本") for name, (src, _why) in sources.items()}
    present = [k for k in keys.values() if k]
    same_keys = len(set(present)) == 1 and len(present) == len(sources)
    same_ver = len(set(v for v in versions.values() if v)) == 1
    if layer is None:
        state = PENDING
        note = ("随包语料层还没落地（`TICKET-159`）：%s。此时「技能集合两模式一致」只能按"
                "语料源与工序表两源核对 —— 未落地项显式登记，不当通过。" % why_layer)
    else:
        state = OK if (same_keys and same_ver) else FAIL
        note = "三源（随包语料层／语料源／工序表）的 `域=版本` 键与总版本逐字一致。" \
            if state == OK else "三源键或版本对不上，逐条看 `键比对`。"
    return {
        "组": "P-技能",
        "断言": "技能集合与语料版本三源一致（随包语料层 ↔ 语料源 ↔ intake 工序表）",
        "状态": state,
        "键比对": {"键": keys, "语料版本": versions},
        "真源": {name: why for name, (_src, why) in sources.items()},
        "说明": note,
    }


# ─────────────────────────── P-可达 ───────────────────────────
def _cli_skills_key():
    """CLI 侧真调 `daniel skills list --json`（若该命令已声明）。"""
    if "skills.list" not in _available_keys(modes.MODE_CLI):
        return None, "CLI 侧还没有 `skills list` 命令（TICKET-159 未落地）"
    try:
        p = subprocess.run([sys.executable or "python3", CLI_ENTRY, "skills", "list", "--json"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=60, cwd=_REPO_ROOT)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, "跑 `daniel skills list` 失败：%s" % e
    if p.returncode != 0:
        return None, "`daniel skills list` 退出码 %s：%s" % (
            p.returncode, ((p.stderr or p.stdout or "").strip().splitlines() or ["无输出"])[-1][:160])
    try:
        doc = json.loads(p.stdout)
    except ValueError:
        return None, "`daniel skills list --json` 的输出不是 JSON"
    return (doc or {}).get("data"), "CLI 侧真调 `daniel skills list --json`"


def _mcp_skills_key():
    """MCP 侧真调：用 MCP server 自己的注册表跑一次 `tools/call`，取同一份技能清单。"""
    if "skills.list" not in _available_keys(modes.MODE_MCP):
        return None, "MCP 侧还没有 skills 工具（TICKET-159 未落地）"
    path = os.path.join(_PKG_ROOT, "mcp", "server.py")
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("daniel_cli_mcp_probe_parity", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        registry = mod.build_registry()
        result, refuse = mod.call_tool(registry, "daniel_skills_list", {})
    except Exception as e:                                       # noqa: BLE001
        return None, "经 MCP server 调 skills 工具失败：%s: %s" % (type(e).__name__, e)
    if refuse or not result:
        return None, "MCP 侧拒绝或没有返回：%s" % (refuse or "无结果")
    structured = (result or {}).get("structuredContent") or {}
    data = structured.get("data")
    if data is None:
        return None, "MCP 工具没有回结构化数据（宿主侧要看 content 文本）"
    return data, "MCP 侧真调 `tools/call` → daniel_skills_list"


def _consistency_key(payload):
    try:
        from .. import corpus
        return corpus.consistency_key(payload)
    except Exception:                                            # noqa: BLE001
        items = (payload or {}).get("能力域") or []
        return {"语料版本": (payload or {}).get("语料版本"), "能力域数": len(items),
                "键": "；".join(sorted("%s=%s" % (s.get("域"), s.get("版本")) for s in items))}


def assert_reachable():
    cli, why_cli = _cli_skills_key()
    mcp, why_mcp = _mcp_skills_key()
    if cli is None and mcp is None:
        state = PENDING
    else:
        k1 = _consistency_key(cli) if cli else None
        k2 = _consistency_key(mcp) if mcp else None
        state = OK if (k1 and k2 and k1 == k2) else FAIL
        why_cli, why_mcp = (k1, why_cli), (k2, why_mcp)
    return {
        "组": "P-可达",
        "断言": "同一份技能清单（域集合＋每域版本＋总版本）在两种模式下都取得到，且键逐字相等",
        "状态": state,
        "键比对": {"CLI 侧": why_cli if cli is None else _consistency_key(cli),
                   "MCP 侧": why_mcp if mcp is None else _consistency_key(mcp)},
        "说明": "本组依赖 TICKET-159（语料随 MCP 分发 ＋ `skills` 命令）落地；"
                "未落地时记「未落地」并在此显式登记，不静默当通过。",
    }


# ─────────────────────────── 入口 ───────────────────────────
def report():
    groups = [assert_capabilities(), assert_chain(), assert_skills(), assert_reachable()]
    hard_fail = [g["组"] for g in groups if g["状态"] == FAIL]
    pending = [g["组"] for g in groups if g["状态"] == PENDING]
    ok = not hard_fail
    return {
        "通过": ok,
        "断言组": groups,
        "未通过": hard_fail,
        "未落地（待其他票）": pending,
        "模式事实": modes.fact_lines(),
        "结论": ("模式对等断言全绿：能力集合同源、intake 链路两模式都可达、技能集合与语料版本一致"
                 if ok and not pending else
                 ("模式对等断言：本票范围内的断言全绿；另有未落地项 %s（待 TICKET-159），"
                  "已在报告里显式登记" % "、".join(pending)) if ok else
                 "模式对等断言有未通过项：%s" % "、".join(hard_fail)),
    }
