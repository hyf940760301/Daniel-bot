# -*- coding: utf-8 -*-
"""需求识别与匹配（只做路由与缺件，**不替业务下结论**）。

口径（用户裁决）
----------------
> 「需求可能并不是完全死板的，所以就会存在业务工序的灵活安排 …… 可以准确识别需求，
>   准确匹配对应的业务能力，以及准确告知需要提供的前置信息」

因此本模块干三件事，也只干三件事：

  ① **识别**：一句话需求 → 候选**工序**（不是"能力域"这一层，因为前置条件细到工序）；
  ② **排序**：每个候选取 `置信度 ＋ 理由 ＋ 档位`，理由必须是人能复核的（命中了哪个说法、
     哪些业务关键词、属于哪个能力域），不是"模型觉得像"；
  ③ **不越界**：匹配结果只是"这条需求像哪道工序"，判据仍在语料与工序里 —— 置信度低就
     如实说低并给出"请补充一句"的建议，**不做硬匹配**（真阴性场景）。

算法（可复核、可回归、零依赖）
------------------------------
中文没有词边界，所以匹配面用**字符二元组**（bigram）而不是分词：

  · 语料侧：每道工序的匹配面 ＝ 工序名 ＋ 触发语义 ＋ 全部同义说法 ＋ 能力域标题 ＋ 产出交付件；
  · 权重：同义说法（用户会怎么开口）权重最高，触发语义与工序名次之，标题与交付件最低；
  · 稀有度：用**逆文档频率**压掉"名单／品牌／KOL"这类到处都有的词，让"砍价／母版／检索词"
    这类真正区分工序的词起作用；
  · 相似度：`余弦相似度`（整体像不像）＋ `最优同义说法的 Dice 相似度`（用户原话像不像），
    两者加权求和 ＝ 置信度（0–1，**定义与阈值都写在报告里**，不含黑箱）。

阈值是**声明式常量**（见 `T_*`），`intake --self-test` 用真实历史需求做正控、用完全无关的
需求做真阴性来钉住它们；改阈值必须重跑自检。
"""
import math
import re
from collections import Counter

from . import catalog

# ─────────────────────────── 阈值（改这里必须重跑自检） ───────────────────────────
T_CANDIDATE = 0.18          # 低于它连候选都不列（"不像既有的哪道工序"）
T_ROUTE = 0.30              # 达到它才算"匹配上了"（否则不做硬匹配）
T_HIGH = 0.55               # 高置信度档
T_MID = 0.35                # 中置信度档（其余为低）

W_COSINE = 0.55             # 置信度 = 三项加权和（余弦 ＋ 最优同义说法 ＋ 工序名整词命中）
W_PHRASE = 0.45
#: 工序名／能力域标题里的**整词**出现在用户话里时的加成（用户往往直接说工序的名字：
#: 「出一份对内审核表」里的「审核表」＝工序「审核表-出件」的第一段）。加成有上限，
#: 免得一个词就把别的信号全压死。
#: 需求句子**开头那个小句**的权重加成：中文需求常常是「<做什么活儿>，<细节要求>」，
#: 开头小句说的是"哪类活儿"，后面小句往往只是验收细节（"把价格合理性都写上"）。
#: 这条与其它信号一样是声明式常量，理由里会写明用了它。
W_HEAD_CLAUSE = 1.35
W_NAME_TERM = 0.13
#: 工序名的整词出现在**开头小句**里时的额外倍率：开头小句说的通常就是"要出的东西"，
#: 尾部小句多半是验收细节（"把…建议动作都写上"）。
W_NAME_TERM_HEAD = 1.6
#: 整词加成的"太泛不给分"门槛：一个词若出现在超过这个比例的工序匹配面里（如「名单」「候选」），
#: 它区分不了工序，给了加成只会把噪声抬起来。
TERM_TOO_COMMON = 0.20
W_DOMAIN_TERM = 0.05
#: 交付件措辞加成：用户往往会直接说"要出什么"（"出一份声量份额报告"里的「声量份额报告」）。
#: 命中工序 `产出交付件` 里的整段措辞就给分（同样过"太泛不给分"的过滤）。
W_DELIVERABLE_TERM = 0.10
BONUS_CAP = 0.30

#: 匹配面各部分的权重（同义说法 ＝ 用户会怎么开口，权重最高）
W_PARTS = {"同义说法": 3.0, "触发语义": 2.0, "工序": 2.0, "能力域标题": 1.0, "产出交付件": 1.0}

#: 口语虚词（先整体抠掉再切二元组）：抠掉它们能让"帮我审一下这批红人的报价"落到"审·红人·报价"
_STOP_PHRASES = (
    "帮我", "帮忙", "麻烦", "请帮我", "请你", "能不能", "可不可以", "帮我看看", "看一下", "看看",
    "这批", "这些", "这个", "那个", "那些", "这份", "这批人的", "一下", "一下子", "以及",
    "然后", "顺便", "就是", "现在", "目前", "想要", "需要", "我要", "我要你", "我希望", "帮我做",
    "帮我出", "给我", "做个", "做一份", "出一份", "出来", "一份", "一个", "一些", "有没有",
    "怎么样", "如何", "怎么办", "是什么", "什么", "多少", "为什么", "然后呢",
)
#: 口语单字虚词（逐字抠）
_STOP_CHARS = "的了吗呢吧啊呀哦嗯啦着过和与及把给对从在是为我等您你他它们这那有能会要就都也很更"


def _normalize(text):
    """归一：小写 → 抠掉口语虚词 → 切成「有意义的片段」。"""
    s = str(text or "").lower()
    for ph in sorted(_STOP_PHRASES, key=len, reverse=True):
        s = s.replace(ph, "|")
    out, buf = [], []
    for ch in s:
        if ch in _STOP_CHARS:
            buf.append("|")
        elif ch.isalnum() or ch == "#":
            buf.append(ch)
        elif ch == "@":                       # @handle 保留（频道名是实词）
            buf.append(ch)
        else:
            buf.append("|")
    for seg in "".join(buf).split("|"):
        if seg:
            out.append(seg)
    return out


_CLAUSE_SPLIT_RE = re.compile(r"[，,。；;：:\n]")


def _need_tokens(need):
    """需求 → 二元组计数：**开头小句加权**（它说的是"哪类活儿"）。"""
    text = str(need or "")
    counts = _tokens(text)
    head = _CLAUSE_SPLIT_RE.split(text)[0].strip()
    if head and head != text.strip():
        extra = W_HEAD_CLAUSE - 1.0
        for tok, n in _tokens(head).items():
            counts[tok] += int(round(n * extra)) or 1
    return counts


def _tokens(text):
    """一段文本 → 二元组计数（长片段额外补一条整段，让"报价审核表"这种术语能整体命中）。"""
    counts = Counter()
    for seg in _normalize(text):
        if len(seg) == 1:
            counts[seg] += 1
        else:
            for i in range(len(seg) - 1):
                counts[seg[i:i + 2]] += 1
            if 2 < len(seg) <= 5:
                counts[seg] += 1
    return counts


def _tokens_of_process(p):
    """一道工序的匹配面（各部分的二元组按权重相加）。"""
    counts = Counter()
    for part, weight in W_PARTS.items():
        value = p.get(part)
        if part == "同义说法":
            for phrase in value or []:
                for tok, n in _tokens(phrase).items():
                    counts[tok] += n * weight
        else:
            for tok, n in _tokens(value or "").items():
                counts[tok] += n * weight
    return counts


def _index():
    """建倒排/统计（带缓存）：工序向量、DF、IDF、同义说法的二元组集合。"""
    cache = getattr(_index, "_cache", None)
    if cache is not None:
        return cache
    doc = catalog.load()
    vecs, phrase_sets = [], []
    df = Counter()
    for p in doc["工序"]:
        vec = _tokens_of_process(p)
        vecs.append(vec)
        for tok in vec:
            df[tok] += 1
        phrase_sets.append([_tokens(ph) for ph in p["同义说法"]])
    n = max(len(doc["工序"]), 1)
    idf = {tok: math.log((n + 1) / (d + 0.5)) + 1.0 for tok, d in df.items()}
    # 整词（工序名/域标题的片段）在多少道工序的匹配面里出现过 —— 用来滤掉太泛的词
    faces = [" ".join([p["工序"], p["触发语义"], p["能力域标题"], p["产出交付件"]]
                      + p["同义说法"]) for p in doc["工序"]]
    term_df = {}
    for p in doc["工序"]:
        for t in set(_name_terms(p) + _domain_terms(p)):
            term_df[t] = sum(1 for f in faces if t in f)
    out = {"doc": doc, "vecs": vecs, "phrase_sets": phrase_sets, "idf": idf, "n": n,
           "term_df": term_df}
    _index._cache = out
    return out


def _dice(a, b):
    """两个二元组集合的 Dice 相似度（0–1）。"""
    if not a or not b:
        return 0.0
    inter = sum(min(a[t], b[t]) for t in a if t in b)
    return 2.0 * inter / (sum(a.values()) + sum(b.values()))


def _cosine(need, vec, idf):
    if not need or not vec:
        return 0.0
    num = sum(w * idf.get(t, 1.0) * need[t] * 1.0 for t, w in vec.items() if t in need)
    na = math.sqrt(sum((v * idf.get(t, 1.0)) ** 2 for t, v in need.items()))
    nb = math.sqrt(sum((v * idf.get(t, 1.0)) ** 2 for t, v in vec.items()))
    if na == 0 or nb == 0:
        return 0.0
    return num / (na * nb)


def _name_terms(p):
    """工序名与能力域标题里的**整词**（`审核表-出件` → `审核表`／`出件`）。"""
    out = []
    for part in re.split(r"[-—·／/、\s]+", str(p.get("工序") or "")):
        if len(part) >= 2 and part not in out:
            out.append(part)
    return out


def _domain_terms(p):
    out = []
    for part in re.split(r"[-—·／/、\s]+", str(p.get("能力域标题") or "")):
        if len(part) >= 2 and part not in out:
            out.append(part)
    return out


def _deliverable_terms(p):
    """工序 `产出交付件` 里的整段措辞（`SOV 声量份额报告（含竞品对照）` → `SOV`／`声量份额报告`）。"""
    out = []
    for part in re.split(r"[、，,／/＋+（）()\s]+", str(p.get("产出交付件") or "")):
        part = part.strip()
        if 2 <= len(part) <= 10 and part not in out:
            out.append(part)
    return out


def _term_bonus(p, raw_need):
    """整词命中加成：工序名里的词出现在用户话里 → 加，可复核（理由里会写出来）。

    出现在**开头小句**里的整词加得更重（开头小句说的是"要出的东西"）。
    """
    text = str(raw_need or "").lower()
    head = _CLAUSE_SPLIT_RE.split(str(raw_need or ""))[0].strip().lower()
    common = _common_terms()
    hit_head = [t for t in _name_terms(p) if t.lower() in head and t not in common]
    hit_tail = [t for t in _name_terms(p)
                if t not in hit_head and t.lower() in text and t not in common]
    hit_name = hit_head + hit_tail
    hit_domain = [t for t in _domain_terms(p)
                  if t.lower() in text and t not in hit_name and t not in common]
    hit_deliv = [t for t in _deliverable_terms(p)
                 if t.lower() in text and t not in hit_name and t not in common]
    bonus = min(BONUS_CAP, W_NAME_TERM * (W_NAME_TERM_HEAD * len(hit_head) + len(hit_tail))
                + W_DOMAIN_TERM * len(hit_domain) + W_DELIVERABLE_TERM * len(hit_deliv))
    return bonus, hit_name + hit_deliv, hit_domain


def _common_terms():
    """太泛、区分不了工序的整词（如「名单」「候选」）—— 不给加成。"""
    idx = _index()
    n = max(idx["n"], 1)
    return {t for t, d in (idx.get("term_df") or {}).items() if d / n > TERM_TOO_COMMON}


def _grade(score):
    return "高" if score >= T_HIGH else ("中" if score >= T_MID else "低")


def _reasons(p, score, cosine, phrase_best, hits, runner_up=None, name_hits=(), bonus=0.0):
    """理由必须是人能复核的（命中了哪句话、哪些词、属于哪个域）。"""
    out = []
    if name_hits:
        out.append("工序名里的「%s」在你的话里出现了（+%.2f）" % ("」「".join(name_hits), bonus))
    if phrase_best and phrase_best[1] > 0:
        out.append("用户的说法与这道工序的常用说法最接近：「%s」（相似度 %.2f）"
                   % (phrase_best[0], phrase_best[1]))
    if hits:
        out.append("命中的业务关键词：%s" % "、".join(hits[:10]))
    out.append("所属能力域：%s（%s）" % (p["能力域标题"], p["能力域"]))
    out.append("这道工序本身：%s —— %s" % (p["工序"], p["触发语义"] or "（无触发语义）"))
    out.append("整体相似度 %.2f（余弦）／常用说法相似度 %.2f（最优）／合计置信度 %.2f"
               % (cosine, phrase_best[1] if phrase_best else 0.0, score))
    if runner_up:
        out.append("与第二候选「%s」相差 %.2f" % (runner_up[0], runner_up[1]))
    return out


def route(need, top=3, min_score=None):
    """把一句话需求匹配到工序。

    返回 `{需求, 候选[], Top1 或 None, 是否匹配上, 门槛, 说明}`；
    `候选` 每项含 `工序/工序键/能力域/能力域标题/置信度/档位/理由/信号/产出交付件/对应契约/前置条件/需要能力`。
    """
    min_score = T_CANDIDATE if min_score is None else float(min_score)
    need = str(need or "").strip()
    idx = _index()
    doc = idx["doc"]
    need_vec = _need_tokens(need)
    rows = []
    for i, p in enumerate(doc["工序"]):
        cos = _cosine(need_vec, idx["vecs"][i], idx["idf"])
        phrase_best = max(((ph, _dice(need_vec, sets))
                           for ph, sets in zip(p["同义说法"], idx["phrase_sets"][i])),
                          key=lambda x: x[1], default=("", 0.0))
        bonus, name_hits, _dom_hits = _term_bonus(p, need)
        score = min(1.0, W_COSINE * cos + W_PHRASE * phrase_best[1] + bonus)
        hits = sorted((t for t in need_vec if t in idx["vecs"][i]),
                      key=lambda t: -idx["idf"].get(t, 1.0))
        rows.append({"工序": p, "分": score, "余弦": cos, "最优说法": phrase_best,
                     "命中词": hits, "名命中": name_hits, "加成": bonus})
    rows.sort(key=lambda r: (-r["分"], r["工序"]["工序"]))
    cands = [r for r in rows if r["分"] >= min_score][:max(1, int(top))]
    if not cands:
        cands = rows[:1] if rows else []

    out = []
    for n, r in enumerate(cands):
        p = r["工序"]
        nxt = rows[n + 1] if n + 1 < len(rows) else None
        runner = None
        if nxt is not None:
            runner = (nxt["工序"]["工序"], r["分"] - nxt["分"])
        out.append({
            "工序": p["工序"], "工序键": p["工序键"],
            "能力域": p["能力域"], "能力域标题": p["能力域标题"],
            "置信度": round(r["分"], 3), "档位": _grade(r["分"]),
            "产出交付件": p["产出交付件"], "对应契约": p["对应契约"],
            "前置条件": p["前置条件"], "需要能力": p["需要能力"],
            "依据": p["依据"],
            "信号": {"余弦相似度": round(r["余弦"], 3),
                     "最优同义说法": r["最优说法"][0],
                     "最优同义说法相似度": round(r["最优说法"][1], 3),
                     "命中关键词": r["命中词"][:12],
                     "工序名整词命中": r["名命中"], "整词加成": round(r["加成"], 3)},
            "理由": _reasons(p, r["分"], r["余弦"], r["最优说法"], r["命中词"], runner,
                            r["名命中"], r["加成"]),
        })
    best = out[0]["置信度"] if out else 0.0
    matched = bool(out) and best >= T_ROUTE
    return {
        "需求": need,
        "候选": out,
        "Top1": out[0] if out else None,
        "是否匹配上": matched,
        "门槛": {"候选门槛": T_CANDIDATE, "匹配门槛": T_ROUTE,
                 "高": T_HIGH, "中": T_MID,
                 "口径": "置信度 ＝ %.2f×余弦相似度 ＋ %.2f×最优同义说法相似度 "
                         "＋ 工序名整词命中加成（每词 %.2f，上限 %.2f）；"
                         "低于匹配门槛时不做硬匹配（真阴性）"
                         % (W_COSINE, W_PHRASE, W_NAME_TERM, BONUS_CAP)},
        "说明": ("匹配到工序「%s」（置信度 %.2f，档位 %s）" % (out[0]["工序"], best, out[0]["档位"]))
                if matched else
                ("这句话不像既有工序里的任何一道（最高置信度 %.2f，低于匹配门槛 %.2f）"
                 "—— 请补一句「要什么产出、给谁用」，或直接点名工序" % (best, T_ROUTE)),
        "语料版本": doc["语料版本"],
        "工序总数": doc["工序数"],
    }


def all_needs(counts_only=True):
    """真源里全部同义说法（自检的正控语料直接来自这里，不另写一份）。"""
    out = []
    for p in catalog.load()["工序"]:
        for ph in p["同义说法"]:
            out.append({"需求": ph, "期望工序": p["工序"], "能力域": p["能力域"]})
    return out
