# -*- coding: utf-8 -*-
"""clarify.py —— 澄清闸（`clarify plan` / `clarify ask`）的**纯本地逻辑**。

数据从哪来（不在这里写死业务口径）
----------------------------------
* **文案**（项名／为什么问／默认值／影响／口径类／五类方向）：随包语料索引
  `mcp/corpus/_ONTOLOGY.json` 的 `criterion.clarify.param_gate`（28 条 dims ＋ 4 场景）
  与 `criterion.creator.screen`（5 组）。改文案改登记表，不改本文件。
* **触发词与正则**（判断"用户原话里提到没"）：`daniel_cli/data/clarify_triggers.json`，
  按 `场景.dim key` 与登记表一一对应（由 `mcp/check_clarify_registry.py` 的 C20 双向对账）。
* **容量常量**（8／3／2／每轮 3）：本文件顶部，属产品口径，改它要重跑对拍。

与 JS 旧实现的关系
------------------
本文件是 `daniel-plugins/a-v2/lib/clarify.js` 的**逐字节等价实现**（键序、文案、命中规则都不动）。
已知偏差按 bug-compatible 保留（`inferTopic` 的"品牌"优先级、`screenPlan` 的 need 死参等），
分别在 TICKET-282 / 283 / 284 里另案处理 —— **本文件不许顺手修**。

本模块不联网、不读账号、不写盘：只读上面两个本地文件。
"""

import json
import os
import re

from . import ontology

# ─────────────────────────── 容量常量（产品口径）───────────────────────────
MAX_ITEMS = 8        # `plan` 的「缺项」最多列几条（超出写进「其余按默认口径执行」）
TOP_N = 3            # 「优先补」给几条
MAX_ROUNDS = 2       # `ask` 追问轮数上限（到上限按默认跑）
ROUND_ASK = 3        # `ask` 每轮最多问几项（与 TOP_N 同值不同义，别合并）

VALID_TOPICS = ("kol_search", "list_ops", "brand_setup")

NEXT_STEP = ("你可以只答其中几项（按编号说就行）；没答的部分我按上面写的默认口径直接开工，"
             "并在结论里逐条标注「按默认口径处理」，你看到哪条不认同随时改。")
NEXT_STEP_READY = ("这次需求里的参数已经齐了，不需要再问你；直接影响结论的口径判断我会在结论里"
                   "单列一段标注，你看到哪条不认同随时改。")
CALIBER_TAIL = "属口径判断，插件不代拟 —— 由我方给默认口径，或需你确认"

REGISTRY_ID = "criterion.clarify.param_gate"
SCREEN_ID = "criterion.creator.screen"

# 五类信号的判据（与登记表的 5 个组一一对应；只认 key，文案从登记表取）
FORM_RX = re.compile(r"(上手|测评|评测|开箱|资讯|对比|体验|长视频|短视频)")
COUNTRY_RX = re.compile(r"(美国|加拿大|北美|英国|德国|法国|日本|韩国|澳洲|澳大利亚|欧洲|全球)")
COMM_RX = re.compile(r"(竞品|同类|合作过|合作经验)")
EXCL_RX = re.compile(r"(排除|不要|不含|剔掉|剔除)")
FANS_RX = re.compile(r"粉丝")
NUM_TAIL = r"[^，。；]{0,10}?([0-9]+(?:\.[0-9]+)?)[\s\uFEFF]*(万|w|k|%)?"


class ClarifyDataError(Exception):
    """随包数据缺失或对不上（不是用户错误，退出码 1）。"""


# ─────────────────────────── 文本归一（跨语言对齐的关键）───────────────────────────
def norm_text(s):
    """对齐 JS `String(x).trim()`：

    ① 先按 Python 的 Unicode 空白 strip（含 NBSP／U+2028／U+3000）；
    ② 再去掉 JS 会去、Python 不去的 BOM；
    ③ 再去一次空白（`"\\ufeff x"` 这种要露出来）。
    """
    s = "" if s is None else str(s)
    s = s.strip()
    s = s.strip("\ufeff")
    s = s.strip()
    return s


def js_lower(s):
    return str("" if s is None else s).lower()


# ─────────────────────────── 数据装载 ───────────────────────────
_CACHE = {}


def _triggers_path():
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), "data", "clarify_triggers.json")


def _load_json(path, what):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise ClarifyDataError("缺少随包数据：%s（%s）。请重装或跑 `python3 mcp/check_corpus_sync.py --sync`" % (path, what))
    except ValueError as exc:
        raise ClarifyDataError("随包数据不是合法 JSON：%s（%s）：%s" % (path, what, exc))


def _compile(spec):
    """`(?i)` 前缀在 Python 里就是 flags，直接用；编译失败照样报数据错。"""
    try:
        return re.compile(spec)
    except re.error as exc:
        raise ClarifyDataError("触发词正则编译失败：%r（%s）" % (spec, exc))


def load():
    """读登记表索引 ＋ 触发词文件，合成运行期需要的结构（结果缓存）。"""
    if _CACHE.get("registry"):
        return _CACHE["registry"]

    doc = ontology.load()
    if not doc:
        raise ClarifyDataError(
            "语义登记表索引未随包（%s）。先跑 `python3 mcp/check_corpus_sync.py --sync` 再试" % ontology.index_path())
    by_id = {e.get("id"): e for e in doc.get("entries", [])}

    entry = by_id.get(REGISTRY_ID)
    if not entry or not entry.get("scenarios"):
        raise ClarifyDataError("登记表里没有可用的 %s（4 场景 / 28 条）" % REGISTRY_ID)
    screen = by_id.get(SCREEN_ID)
    if not screen or not screen.get("groups"):
        raise ClarifyDataError("登记表里没有可用的 %s（5 组）" % SCREEN_ID)

    trig = _load_json(_triggers_path(), "clarify 触发词")
    trig_sc = trig.get("scenarios") or {}
    hints = trig.get("topicHints") or []

    scenarios = {}
    for sc in entry["scenarios"]:
        dims = []
        for d in sc.get("dims") or []:
            t = (trig_sc.get(sc["key"]) or {}).get(d["key"])
            if not t:
                raise ClarifyDataError("触发词缺项：%s.%s（C20 对账未通过）" % (sc["key"], d["key"]))
            dims.append({
                "key": d["key"],
                "ask": d["ask"],
                "why": d["why"],
                "default": d["default"],
                "impact": d["impact"],
                "hit": [js_lower(x) for x in (t.get("hit") or [])],
                "hitRe": [_compile(x) for x in (t.get("hitRe") or [])],
            })
        scenarios[sc["key"]] = {
            "key": sc["key"],
            "label": sc["label"],
            "dims": dims,
            "calibers": [{"ask": c["ask"], "impact": c["impact"]} for c in (sc.get("calibers") or [])],
        }

    for key in VALID_TOPICS:
        if key not in scenarios:
            raise ClarifyDataError("登记表缺场景：%s" % key)
    if "generic" not in scenarios:
        raise ClarifyDataError("登记表缺场景：generic")

    registry = {
        "scenarios": scenarios,
        "groups": [{"key": g["key"], "label": g["label"], "example": g["example"],
                    "default": g["default"], "weight": g["weight"]} for g in screen["groups"]],
        "topicHints": [[str(t), [js_lower(w) for w in (ws or [])]] for t, ws in hints],
    }
    _CACHE["registry"] = registry
    return registry


# ─────────────────────────── 场景判定 ───────────────────────────
def clarify_topic_of(topic):
    t = js_lower(norm_text(topic))
    return t if t in VALID_TOPICS else "generic"


def infer_topic(need):
    text = js_lower("" if need is None else need)
    for topic, words in load()["topicHints"]:
        if any(w and w in text for w in words):
            return topic
    return "generic"


# ─────────────────────────── plan ───────────────────────────
def _said(need_lower, need_raw, dim):
    for kw in dim["hit"]:
        if kw and kw in need_lower:
            return True
    for rx in dim["hitRe"]:
        if rx.search(need_raw):
            return True
    return False


def clarify_plan(need, topic=None):
    """返回今天 `daniel_clarify` 的 `data`（含末尾的「选择面」）。"""
    reg = load()
    raw = norm_text(need)
    given = clarify_topic_of(topic)
    key = infer_topic(raw) if given == "generic" else given
    sc = reg["scenarios"].get(key) or reg["scenarios"]["generic"]
    key = sc["key"]

    need_lower = js_lower(raw)
    known, opened = [], []
    for d in sc["dims"]:
        if _said(need_lower, raw, d):
            known.append(d["ask"])
        else:
            opened.append(d)

    listed = opened[:MAX_ITEMS]
    rest = opened[MAX_ITEMS:]

    data = {}
    data["场景"] = sc["label"]
    data["场景依据"] = ("按需求原话自动判断（要指定场景就传 topic）"
                    if (given == "generic" and key != "generic") else "按调用方给的 topic")
    data["已识别项"] = known
    data["缺项"] = [{"项名": d["ask"], "为什么问": d["why"], "不答的默认值": d["default"]} for d in listed]
    data["优先补"] = [{"项名": d["ask"], "为什么先补": d["impact"]} for d in listed[:TOP_N]]
    data["口径类"] = [{"项名": c["ask"], "影响": "%s；%s" % (c["impact"], CALIBER_TAIL)} for c in sc["calibers"]]
    data["下一步"] = NEXT_STEP if listed else NEXT_STEP_READY
    if rest:
        data["其余按默认口径执行"] = ("其余按默认口径执行：还有 %d 项影响较小，这一轮不列出来（%s），"
                               "直接按各自的默认口径走。" % (len(rest), "、".join(d["ask"] for d in rest)))
    if not listed:
        data["结论"] = "需求参数已齐，不需要追问，直接开工"
    data["选择面"] = _faces(reg)
    return data


def _faces(reg):
    return [{"方向": g["label"], "举例": g["example"], "不给就按": g["default"]} for g in reg["groups"]]


# ─────────────────────────── ask ───────────────────────────
def _has_number_near(text, head):
    return re.search(head + NUM_TAIL, text, re.I) is not None


def parse_screen_reply(reply):
    """返回命中的组 key（顺序固定：内容→受众→表现→商业→排除）。"""
    t = "" if reply is None else str(reply)
    covered = []
    if FORM_RX.search(t):
        covered.append("content_vertical")
    if COUNTRY_RX.search(t):
        covered.append("audience_geo")
    if _has_number_near(t, "均播") or _has_number_near(t, "播放") or _has_number_near(t, "互动") or FANS_RX.search(t):
        covered.append("performance_scale")
    if COMM_RX.search(t):
        covered.append("commercial")
    if EXCL_RX.search(t):
        covered.append("exclusions")
    return covered


def screen_plan(need, reply=None, round=None):
    """返回今天 `daniel_screen_ask` 的 `data`（四模式之一）。"""
    reg = load()
    base = {"场景": reg["scenarios"]["kol_search"]["label"], "选择面": _faces(reg)}

    if norm_text(reply) == "":
        out = dict(base)
        out["模式"] = "选择面"
        out["已识别项"] = []
        out["说明"] = "这五类可以一次说完（例如「美国、长视频均播 30 万、排除已合作」），也可以只说重点，其余按默认。"
        out["下一步"] = "你把想要的方向说一句就行；没说到的我按「不给就按」那栏的默认走，并在结论里逐条标注。"
        return out

    covered = parse_screen_reply(reply)
    gaps = [g for g in reg["groups"] if g["key"] not in covered]
    gaps.sort(key=lambda g: 0 if g["weight"] == "高" else 1)   # 稳定排序：两个「高」保持原序

    try:
        cur = int(round)
    except (TypeError, ValueError):
        cur = 1
    if cur <= 0:
        cur = 1

    labels = {g["key"]: g["label"] for g in reg["groups"]}
    covered_labels = [labels[k] for k in covered if k in labels]

    def _unconfirmed():
        return [{"方向": g["label"], "按默认": g["default"]} for g in gaps]

    def _gaps():
        return [{"组": g["label"], "示例": g["example"], "默认": g["default"], "权重": g["weight"]} for g in gaps]

    if not gaps or len(covered) >= 3:
        out = dict(base)
        out["模式"] = "确认"
        out["已识别项"] = covered_labels
        out["缺口"] = []
        out["追问"] = []
        out["未确认项"] = _unconfirmed()
        out["结论"] = "一次说清，可以直接开工"
        out["下一步"] = "我按你说的这些筛，没说到的按默认；开工前会把「本次筛选维度／本次未筛维度」列给你确认。"
        return out

    if cur >= MAX_ROUNDS:
        out = dict(base)
        out["模式"] = "到上限按默认"
        out["已识别项"] = covered_labels
        out["缺口"] = _gaps()
        out["追问"] = []
        out["未确认项"] = _unconfirmed()
        out["结论"] = "不再追问，按默认口径开工"
        out["下一步"] = "没确认的部分会在结论里标「未确认」，你看到哪条不对随时改。"
        return out

    ask = gaps[:ROUND_ASK]
    out = dict(base)
    out["模式"] = "动态追问"
    out["轮次"] = cur
    out["已识别项"] = covered_labels
    out["缺口"] = _gaps()
    out["追问"] = [{"方向": g["label"], "问": "这次的「%s」怎么定？" % g["label"],
                   "举例": g["example"], "不给就按": g["default"]} for g in ask]
    out["其余按默认"] = ([{"方向": g["label"], "按默认": g["default"]} for g in gaps[ROUND_ASK:]]
                     if len(gaps) > len(ask) else [])
    out["下一步"] = "答这几项就行；不答的按「不给就按」那栏走。"
    return out
