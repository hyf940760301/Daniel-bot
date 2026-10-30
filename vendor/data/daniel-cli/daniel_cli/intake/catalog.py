# -*- coding: utf-8 -*-
"""工序与前置条件表（intake 的**真源**：`processes.json`，随包分发）。

为什么是真源文件而不是散在代码里
--------------------------------
用户裁决「前置条件**细到工序**」：8 个能力域各自列出**工序**，每个工序声明
`工序名 / 所属能力域 / 触发语义 / 前置条件[{名称, 来源类型, 取数方式}] / 产出交付件 / 对应契约`。
这张表同时被四件事消费，所以必须只有一份：

  - `matcher.py`  按 `触发语义 ＋ 同义说法` 做需求匹配（路由）；
  - `preflight.py` 按 `前置条件` 逐条**真查**（能查的必须去查）；
  - `drafter.py`  按 `前置条件 ＋ 产出交付件` 生成本次任务的工序契约草稿；
  - `parity.py`   按 `需要能力` 做模式能力对等断言（CLI 模式 vs MCP 模式）。

来源类型四种（第四种是本票新增）
--------------------------------
| 来源类型 | 含义 | 取数方式 |
|---|---|---|
| `人提供` | 系统里查不到，只在用户手上／邮件里／外部表里 | 必须为空串 |
| `系统内已有` | Daniel 里现在就有，直接查 | **必须**给一条真实存在的只读命令 |
| `可推导` | 由查到的数据算出来（口径在语料里） | **必须**给一条真实存在的只读命令 |
| `模式能力` | 这道工序的某个步骤需要某条命令，而**当前模式不提供**（例如 MCP 本期不注册写链） | 由 `modes.py` 在运行期派生，不写死在表里 |

`模式能力` 这一项**不在 JSON 里手写**：代码按每个工序的 `需要能力`（从 `取数方式` 解析，
外加显式声明的写链能力键）与**当前模式真实可用的能力集合**求差集得出 —— 「哪些命令在 MCP
不可用」这件事因此不存在第二份名单（第二真源是本项目明令禁止的）。

自证（`validate()`）
--------------------
表里的每条 `取数方式` 都必须指向 `schema.py` 里**真实存在**的命令（防幻觉命令，与工序契约
的 D3 判据同源）。这条自证由 `intake --self-test` 与 `parity` 报告一起跑。
"""
import json
import os
import re

from .. import schema as cli_schema
from ..exits import EXIT_INTERNAL, EXIT_USAGE
from ..runtime import CliError

_HERE = os.path.dirname(os.path.abspath(__file__))
PROCESSES_PATH = os.path.join(_HERE, "processes.json")

#: 四种来源类型（第四种「模式能力」由代码在运行期派生，不写进表）
SOURCE_HUMAN = "人提供"
SOURCE_SYSTEM = "系统内已有"
SOURCE_DERIVED = "可推导"
SOURCE_MODE = "模式能力"
SOURCE_TYPES = (SOURCE_HUMAN, SOURCE_SYSTEM, SOURCE_DERIVED)
ALL_SOURCE_TYPES = SOURCE_TYPES + (SOURCE_MODE,)

#: 需要「真去查」的来源类型（照这张表决定要不要跑命令）
QUERYABLE_SOURCES = (SOURCE_SYSTEM, SOURCE_DERIVED)

#: 从「取数方式」里认出 `daniel <模块> <子命令>`（可多条，用「＋」或「，」分隔）
_CMD_RE = re.compile(r"\bdaniel\s+([a-z][a-z0-9-]*)\s+([a-z][a-z0-9-]*)")
#: 「取数方式」里的占位符 `--brand <品牌>`：认出它才能判断"还差哪个变量"
_PLACEHOLDER_RE = re.compile(r"<([^<>\s]+)>")

_CACHE = {}


def processes_path():
    return PROCESSES_PATH


def _read_raw():
    if not os.path.isfile(PROCESSES_PATH):
        raise CliError("工序表真源缺失：%s" % PROCESSES_PATH, code=EXIT_INTERNAL,
                       hint="该文件随包分发（daniel_cli/intake/processes.json）；"
                            "分发物里缺了它 intake 链路就无从路由")
    try:
        with open(PROCESSES_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError as e:
        raise CliError("工序表不是合法 JSON：%s" % e, code=EXIT_INTERNAL)
    except OSError as e:
        raise CliError("工序表读不出来：%s" % e, code=EXIT_INTERNAL)


def command_keys_of(text):
    """从一段「取数方式」文本里解析出能力键（`<模块>.<子命令>`），按出现顺序去重。"""
    out = []
    for mod, cmd in _CMD_RE.findall(str(text or "")):
        key = "%s.%s" % (mod, cmd)
        if key not in out:
            out.append(key)
    return out


def placeholders_of(text):
    """一段命令里出现的占位符名（`--brand <品牌>` → `品牌`），按出现顺序去重。"""
    out = []
    for name in _PLACEHOLDER_RE.findall(str(text or "")):
        if name not in out:
            out.append(name)
    return out


def _norm_item(raw, where, problems):
    """归一一条前置条件；结构性缺陷收进 `problems`（不抛异常，交给自证报告逐条说）。"""
    if not isinstance(raw, dict):
        problems.append("%s：前置条件必须是对象" % where)
        return None
    name = str(raw.get("名称") or "").strip()
    src = str(raw.get("来源类型") or "").strip()
    how = str(raw.get("取数方式") or "").strip()
    note = str(raw.get("说明") or "").strip()
    if not name:
        problems.append("%s：前置条件缺 `名称`" % where)
    if src not in SOURCE_TYPES:
        problems.append("%s「%s」的来源类型 %r 不认识（可用：%s）"
                        % (where, name or "?", src, "／".join(SOURCE_TYPES)))
    if not note:
        problems.append("%s「%s」缺 `说明`（为什么需要它／缺了怎么补）" % (where, name or "?"))
    if src == SOURCE_HUMAN:
        if how:
            problems.append("%s「%s」是「%s」，取数方式必须为空（不该把要用户给的东西写成能查）"
                            % (where, name, SOURCE_HUMAN))
    elif src in QUERYABLE_SOURCES:
        if not how:
            problems.append("%s「%s」是「%s」却没有取数方式 —— 能查的必须去查"
                            "（挂空就是让用户去干系统能干的事）" % (where, name, src))
        else:
            keys = command_keys_of(how)
            if not keys:
                problems.append("%s「%s」的取数方式里认不出 `daniel <模块> <子命令>`：%r"
                                % (where, name, how))
            for key in keys:
                mod, _, cmd = key.partition(".")
                if cli_schema.find_command(mod, cmd) is None:
                    problems.append("%s「%s」的取数方式引用了 CLI 不存在的命令「%s」"
                                    "（防幻觉命令：只能引用 schema.py 已声明的命令）"
                                    % (where, name, key))
    return {"名称": name, "来源类型": src, "取数方式": how, "说明": note}


def _norm_process(raw, domain, where, problems):
    if not isinstance(raw, dict):
        problems.append("%s：工序必须是对象" % where)
        return None
    name = str(raw.get("工序") or "").strip()
    if not name:
        problems.append("%s：工序缺 `工序`（工序名）" % where)
        return None
    w = "%s·%s" % (where, name)
    items = []
    for i, it in enumerate(raw.get("前置条件") or []):
        got = _norm_item(it, "%s 前置条件#%d" % (w, i + 1), problems)
        if got:
            items.append(got)
    if not items:
        problems.append("%s：前置条件不能为空（每个工序都要声明它需要什么输入）" % w)
    phrases = [str(x).strip() for x in (raw.get("同义说法") or []) if str(x).strip()]
    if not phrases:
        problems.append("%s：缺 `同义说法`（匹配器的主要语料，用户会怎么开口）" % w)
    need = []
    for it in items:
        for key in command_keys_of(it["取数方式"]):
            if key not in need:
                need.append(key)
    for key in (raw.get("需要能力") or []):
        key = str(key).strip()
        if key and key not in need:
            need.append(key)
        if key and cli_schema.find_command(*key.split(".", 1)) is None:
            problems.append("%s：声明的 `需要能力` 里「%s」不是 CLI 已声明的命令" % (w, key))
    trig = str(raw.get("触发语义") or "").strip()
    if not trig:
        problems.append("%s：缺 `触发语义`（一句话，用于匹配）" % w)
    return {
        "工序": name,
        "工序键": str(raw.get("工序键") or "").strip(),
        "能力域": domain["技能束"],
        "能力域标题": domain["能力域标题"],
        "域说明": domain.get("域说明") or "",
        "触发语义": trig,
        "同义说法": phrases,
        "前置条件": items,
        "产出交付件": str(raw.get("产出交付件") or "").strip(),
        "对应契约": str(raw.get("对应契约") or "").strip(),
        "依据": str(raw.get("依据") or "").strip(),
        "需要能力": need,
        "判据引用": [str(x) for x in (raw.get("判据引用") or [])],
    }


def _corpus_version_single_source():
    """**唯一真源**里当前的语料版本（随包语料清单 `mcp/corpus/_MANIFEST.json` 的 `corpus_version`）。

    为什么不在工序表里手写版本号（TICKET-173）：`processes.json` 的 8 个能力域各有一处
    `语料版本`，语料升版时它们是**手写常量** ⇒ 必然漂（实测 0.9.198 升版后工序表仍写 0.9.196，
    把 `daniel --self-test` 的 G1「模式对等断言」打成红）。现在改成**在加载路径上从真源注入**：
    语料升版 ⇒ 工序表自动跟上，产品面不会再有"工序表落后"。

    读取路径复用 `daniel_cli/corpus.py`（它已经是随包语料的唯一读取器，且不依赖本模块 ⇒
    无循环导入）。**取不到真源时返回 (None, 原因)**，此时回退到表内声明值并如实登记，
    而不是假装成功。
    """
    try:
        from .. import corpus as _corpus
        ver = (_corpus.manifest() or {}).get("corpus_version")
    except Exception as e:                                     # noqa: BLE001
        return None, "随包语料真源不可用（%s）" % str(e)[:80]
    ver = str(ver or "").strip()
    return (ver, "referenced") if ver else (None, "随包语料清单里没有 corpus_version")


def load():
    """读入并归一工序表（带缓存）。返回：

    `{语料版本, 真源, 能力域[], 工序[], 工序数, 前置条件数, 按域{}, 按键{}}`
    """
    if "doc" in _CACHE:
        return _CACHE["doc"]
    raw = _read_raw()
    problems = []
    domains, processes = [], []
    seen_names, seen_keys = set(), set()
    for i, dom in enumerate(raw.get("能力域") or []):
        where = "能力域#%d" % (i + 1)
        if not isinstance(dom, dict):
            problems.append("%s：必须是对象" % where)
            continue
        key = str(dom.get("技能束") or "").strip()
        if not key:
            problems.append("%s：缺 `技能束`（语料束名，例如 kol-negotiation）" % where)
            continue
        if key in seen_keys:
            problems.append("%s：技能束重复：%s" % (where, key))
            continue
        seen_keys.add(key)
        domain = {"技能束": key, "能力域标题": str(dom.get("能力域标题") or "").strip(),
                  "域说明": str(dom.get("域说明") or "").strip(),
                  "语料版本": str(dom.get("语料版本") or "").strip(), "工序数": 0}
        if not domain["能力域标题"]:
            problems.append("%s（%s）：缺 `能力域标题`" % (where, key))
        for j, one in enumerate(dom.get("工序") or []):
            got = _norm_process(one, domain, "%s（%s）工序#%d" % (where, key, j + 1), problems)
            if not got:
                continue
            if got["工序"] in seen_names:
                problems.append("工序名重复：%s（工序名必须唯一，草稿 id 与路由都靠它）"
                                % got["工序"])
                continue
            seen_names.add(got["工序"])
            processes.append(got)
            domain["工序数"] += 1
        if not domain["工序数"]:
            problems.append("%s（%s）：该能力域一道工序都没有" % (where, key))
        domains.append(domain)
    if not processes:
        problems.append("工序表里没有任何工序")

    # 工序键：域内序号补齐（表里给了就用手写的，没给用 `<域短键>-<两位序号>`）
    for dom in domains:
        mine = [p for p in processes if p["能力域"] == dom["技能束"]]
        short = dom["技能束"][4:] if dom["技能束"].startswith("kol-") else dom["技能束"]
        used = set()
        for n, p in enumerate(mine, 1):
            if not p["工序键"]:
                p["工序键"] = "%s-%02d" % (short, n)
            if p["工序键"] in used:
                problems.append("工序键重复：%s" % p["工序键"])
            used.add(p["工序键"])

    # ── 语料版本：**运行期从唯一真源注入**（TICKET-173）──
    # 表里的 8 处 `语料版本` 只是**切分时的声明值**；生效值一律取随包语料清单的真源，
    # 这样"语料升版 ⇒ 工序表自动跟上"是结构性的，而不是靠人记住改 8 处。
    declared = sorted({d["语料版本"] for d in domains if d["语料版本"]})
    src_ver, src_how = _corpus_version_single_source()
    if src_ver:
        for d in domains:
            d["声明版本"] = d["语料版本"]
            d["语料版本"] = src_ver
    versions = sorted({d["语料版本"] for d in domains if d["语料版本"]})
    doc = {
        "语料版本": versions[0] if len(versions) == 1 else "／".join(versions),
        "版本集合": versions,
        "语料版本真源": ("随包语料清单（`mcp/corpus/_MANIFEST.json` 的 `corpus_version`，"
                       "经 `daniel_cli/corpus.py` 读取）→ 加载时注入覆盖表内声明值"
                       if src_ver else "不可用（%s）→ 已回退到表内声明值，不算通过" % src_how),
        "语料版本注入": bool(src_ver),
        "工序表声明版本": declared,
        "声明版本一致": bool(src_ver) and declared == [src_ver],
        "真源": PROCESSES_PATH,
        "表版本": raw.get("表版本"),
        "生成方式": raw.get("生成方式"),
        "能力域": domains,
        "工序": processes,
        "工序数": len(processes),
        "能力域数": len(domains),
        "前置条件数": sum(len(p["前置条件"]) for p in processes),
        "按域": {d["技能束"]: [p for p in processes if p["能力域"] == d["技能束"]]
                 for d in domains},
        "按键": {p["工序键"]: p for p in processes},
        "问题": problems,
    }
    _CACHE["doc"] = doc
    return doc


def validate():
    """表自身的一致性自证（结构性缺陷 ＋ 幻觉命令）。返回 `{通过, 问题[], 统计}`。"""
    doc = load()
    return {
        "通过": not doc["问题"],
        "问题": list(doc["问题"]),
        "统计": {"能力域数": doc["能力域数"], "工序数": doc["工序数"],
                 "前置条件数": doc["前置条件数"], "真源": doc["真源"],
                 "语料版本": doc["语料版本"],
                 "语料版本真源": doc["语料版本真源"],
                 "工序表声明版本": "／".join(doc["工序表声明版本"]) or "（无）",
                 "声明版本一致": doc["声明版本一致"]},
    }


def by_key(key):
    return load()["按键"].get(key)


def domain_titles():
    return {d["技能束"]: d["能力域标题"] for d in load()["能力域"]}


def batch_add_processes(items, domain_meta):
    """**只给合并脚本用**：把一份外部工序表并入真源（本票的 8 域工序表合并）。

    返回 `(新增工序数, 问题[])`；不写文件（写文件由合并脚本自己做，便于复核 diff）。
    """
    problems, added = [], 0
    domain = {"技能束": domain_meta.get("技能束"), "能力域标题": domain_meta.get("能力域标题"),
              "域说明": domain_meta.get("域说明")}
    for i, one in enumerate(items or []):
        got = _norm_process(one, domain, "%s 工序#%d" % (domain["技能束"], i + 1), problems)
        if got:
            added += 1
    if added != len(items or []):
        problems.append("有工序没有归一成功：%d/%d" % (added, len(items or [])))
    return added, problems


def source_stats(doc=None):
    """按来源类型统计（报告里要能一眼看出"能查的有没有写成请你提供"）。"""
    doc = doc or load()
    out = {t: 0 for t in ALL_SOURCE_TYPES}
    for p in doc["工序"]:
        for it in p["前置条件"]:
            out[it["来源类型"]] = out.get(it["来源类型"], 0) + 1
    return out


def main_selfcheck():                                        # pragma: no cover（给手工排障用）
    v = validate()
    print(json.dumps(v, ensure_ascii=False, indent=1))
    return EXIT_USAGE if not v["通过"] else 0
