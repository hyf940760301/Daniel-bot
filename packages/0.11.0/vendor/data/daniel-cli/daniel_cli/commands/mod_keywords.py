# -*- coding: utf-8 -*-
"""keywords 模块：**检索词清单**这条业务工序的可调用入口（只读）。

为什么单独一个模块
------------------
业务语料（`kol-discovery` 的 §2.1／§2.2／§2.3）里，"检索词矩阵"的判据是**能机械判的**：
类别齐不齐、每类词量够不够、有没有重复、有没有命中负向词、有没有装饰符号、地域锚点位置对不对。
这些以前只能靠人逐条看；本模块把它们做成一条可调用、可回归的只读命令：

    daniel keywords check --file <词表文件> [--brand 3690002] [--json]

**只读到底**：读入词表文件 → 逐条判据 → 打印结论。不联网、不查任何账号／品牌档案、
不写任何文件、不触发任何采集任务。`--brand` 只作**归属标注**（写进结果，便于跨品牌归档比对）。

三条纪律
--------
① **每条判据都标注来源**（语料 §2.1.x／模板），输出里给"判据 → 来源"；
② **不可机械化的判据显式单列「需人工判断」**，并写清"为什么机器判不了"与"怎么补"——
   不许假装能判（例如"每个词可溯来源""扩圈迁移可达性""反向抽检"）；
③ **计数口径说清楚**：`count` ＝ 本次所跑判据的**违规项数**（0 ＝ 全合规），
   全量词量在 `规模` 里；交付件清单被截断时**逐行标注**，绝不静默截断。

支持的词表格式（`--help` 里也写明）
-----------------------------------
- `md`：产出标准 v2 的类别表结构（`### 类别 N ｜ 名称` + 每类一张表，表内 **Tag／长句／短尾词／条件词** 四行；
  搜索词格内用逗号或换行分隔，长句用 `<br>` 或换行分隔）；
- `csv`：表头 `类别,类型,检索词`（一行一个词面；也接受无表头的三列）；
- `json`：`{"检索词": [{"类别": …, "类型": …, "检索词": …}, …]}`（顶层直接给这个数组也可以），
  或 `{"类别": [{"类别": …, "Tag": [...], "短尾词": [...], "长句": [...], "条件词": [...]}]}`。
  类型取值：`Tag`／`长句`／`短尾词`／`条件词`。

自检
----
`daniel keywords --self-test`（本模块自带；**不接进 CLI 总自检**，待 TICKET-151 收口后由总监安排）。
自检会写**临时目录**里的夹具文件（用于格式等价性验证），不写仓库、不写数据落点。
"""
import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile

from ..exits import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE
from ..runtime import CliError

BOARD = "keywords"

# ─────────────────────────── 词面类型与类别体系 ───────────────────────────
#: 四类词面（顺序即语料里的行序，不可换）：来源 §2.1.10 A 呈现结构。
#: 其中「条件词」是只作"且"、不得单搜的那一类（§2.1.10 A 行④；§2.1.9 B2）。
ROW_TYPES = ("Tag", "长句", "短尾词", "条件词")

#: 固定 10 类（§2.1.10 B 类别体系）。名称用于"缺哪类"时给人看。
CATEGORY_NAMES = {
    1: "品类与形态",
    2: "竞品与替代品",
    3: "官方功能",
    4: "使用场景",
    5: "人群与职业",
    6: "内容形态与创作者类型",
    7: "市场与语言",
    8: "节奏与档期",
    9: "品牌与型号",
    10: "扩圈相邻垂类",
}

#: 每类词量下限与全表下限（§2.1.10 C 词量下限 · 硬指标）
MIN_PER_TYPE = {"Tag": 4, "短尾词": 5, "长句": 3}
MIN_TOTAL = 300

#: 词面里不允许出现的装饰符号（§2.1.10 A「单元格内容必须复制即用」）。
#: 引号只对"短词类"行判：长句是自然语言句子，句子里的引号是正常标点（实测样本即如此）。
DECOR_ALWAYS = {"#": "井号（Tag 行不得带井号）", "`": "反引号", "*": "Markdown 星号"}
DECOR_SHORT_ROWS = {"\"": "引号", "'": "引号", "“": "引号", "”": "引号", "‘": "引号", "’": "引号"}

#: 负向排除词（§2.1.7 排除规则 L7；§2.1.5 负向排除行）。命中即偏题：
#: 会把赠品号／折扣号／梗号召回进来。**整词匹配**（避免 `tech deals` 被 `deals-only` 误伤）。
NEGATIVE_WORDS = (
    "giveaway", "giveaways", "give away", "deals-only", "deals only", "deal only",
    "meme", "memes", "sweepstakes", "coupon code", "promo code", "discount code",
    "free stuff", "freebie", "freebies",
)
NEGATIVE_SOURCE = "§2.1.7 排除规则 L7（giveaway／deals-only／meme／无关品类）＋§2.1.5 负向排除行"

#: 地域锚点词表（模板 §0.1 与 §2.1.10 D：地域锚点必须置于**词首**，`uk office chair` ✅／`office chair uk` ❌）。
#: 只收**不会与普通英文词混淆**的形态：短词只留 us／uk／gb／eu／ca 这类市场级写法，
#: 不放 `in`／`de` 这类会误伤的片段（宁漏不误伤）。
REGION_TOKENS = (
    "north america", "latin america", "usa", "us-based", "us", "uk", "gb", "eu",
    "canada", "canadian", "america", "american", "german", "germany", "deutsch",
    "france", "french", "spain", "spanish", "italy", "italian", "polish", "poland",
    "dutch", "netherlands", "nordic", "sweden", "denmark", "finland", "norway",
    "australia", "australian", "japan", "japanese", "korea", "korean", "india",
    "indian", "brazil", "mexico", "latam", "sea", "dach", "london", "berlin",
)
REGION_SOURCE = "模板 §0.1（v2.3 · 教训 59）＋§2.1.10 D：地域锚点必须置于词首"

#: 需人工判断的判据（**不可机械化**，显式单列；每条都给"为什么判不了"与"怎么补"）。
MANUAL_JUDGEMENTS = (
    {
        "项": "每个词可溯来源（产品页原话／用户语言／竞品对标／媒体盘点），来源列写清文件＋节行",
        "来源": "§2.1.2 选词纪律；模板 §0.1 填写纪律",
        "为什么机器判不了": "来源是文件外的证据，本命令只看词表自身；词表里写没写来源、来源是不是真的，"
                            "机器判不出来（写个来源串很容易，判真假很难）",
        "怎么补": "交付前逐类抽查：任取 5 个词回溯到产品页／VOC／竞品材料；无来源的词标「待用户确认」或删除",
    },
    {
        "项": "锚点法则：每条检索式至少含 1 个锚点（形态/品类锚点或竞品品牌锚点），"
                "能力/场景/人群词只能与锚点 AND 组合、不得单独成词",
        "来源": "§2.1.9 B1／B2；模板 §0.1 锚点法则",
        "为什么机器判不了": "锚点词表随品类与竞品变化（本品类形态词＋本期竞品品牌），无法从词表自身稳定推出；"
                            "且语料对「内容形态词（类别 6）／地域词（类别 7）／节奏词（类别 8）」允许单独直搜，"
                            "一刀切机器判会把这些类整体误伤",
        "怎么补": "按项目给一份锚点词表（形态锚点＋竞品品牌锚点）后人工逐行过；本命令已把"
                  "「条件词被当成短尾词单搜」这一条可机械化的部分单独判了（判据 COND）",
    },
    {
        "项": "每个扩圈词的迁移可达性一句话：从这个词命中的创作者，为什么会愿意／适合做我们的产品",
        "来源": "§2.1.9 B3；§2.1.8 A2 每个扩圈类型写「绑定约束」",
        "为什么机器判不了": "这是判断，不是格式：同能力异形态（翻译机→AI 眼镜）与同空间同动机"
                            "（除雪机→家庭庭院自动化）在词面上看不出区别",
        "怎么补": "类别 10 每个垂直写一句话迁移可达性（样本 §类别 10 的写法可直接照抄结构）",
    },
    {
        "项": "反向抽检：对每个扩圈／场景词随机抽 3–5 个命中频道，逐条回答「受众与内容形态与本产品有交集吗」",
        "来源": "§2.1.9 C 反向抽检 SOP（矩阵交付前必做）",
        "为什么机器判不了": "需要真实召回结果与频道内容，本命令离线只读词表文件，拿不到命中频道",
        "怎么补": "按 SOP 抽样后把「词 → 抽检频道 → 结论」留痕进交付物",
    },
    {
        "项": "扩圈表独占性双闸门：量闸门（本品类语境占比）＋质闸门（锚点类型偏离度），阈值须给簇间间隙依据",
        "来源": "§2.1.5 扩圈 LT-E 双闸门（教训 81）",
        "为什么机器判不了": "两个闸门都要用语料统计分布定阈值，依赖当批召回数据",
        "怎么补": "按块逐块报数、不达标整块删除，并复查被删垂直的措辞是否残留表内",
    },
    {
        "项": "词量回测：用语料逐词回测命中频道数；0 命中词标「观察词」并降级，不占主力检索位",
        "来源": "§2.1.10 D 词量回测纪律；模板 §0.1",
        "为什么机器判不了": "需要自有名单语料（频道标题＋简介），本命令拿不到语料",
        "怎么补": "交付前跑一次逐词回测并把数字写进交付物（样本把实测数写在各行的「实测命中」列）",
    },
    {
        "项": "强锚点必须配「负向语境」词表，且负向表不得含本品类核心内容短语",
        "来源": "§2.1.10 D 末＋§2.2 负向表红线（教训 70／D5）",
        "为什么机器判不了": "负向语境是每个强锚点的多义语境（`chair`→yoga／pilates…），"
                            "是否误伤本品类核心短语要用本品类语料反查",
        "怎么补": "每个强锚点成对给负向语境并逐行报数；填表前用本品类语料的检索词表反查一次",
    },
    {
        "项": "改版只增不减：新版本词量低于上一版必须逐条说明取舍依据",
        "来源": "§2.1.10 C 改版只增不减",
        "为什么机器判不了": "需要上一版词表做逐条比对；本命令只读当前一份文件",
        "怎么补": "把上一版文件一起交过来做人工对照，或交付物内单列「本版删除／降级词及理由」",
    },
)


# ─────────────────────────── 判据表（可执行断言） ───────────────────────────
def judge_specs():
    """12 条可机械化判据：编号／名称／判据／来源。

    每条都可能给出"违规条数"，契约与报告都按这个编号取数（`--only <编号>`）。
    """
    return (
        {
            "编号": "FMT", "名称": "词表可解析",
            "判据": "文件能读成「类别 → Tag／长句／短尾词／条件词」四类词面；"
                    "搜索词格内用逗号或换行分隔（长句一条一行）；至少识别到一个类别区块",
            "来源": "§2.1.10 A 呈现结构（一个类别 = 一张完整表格）；模板 §二",
        },
        {
            "编号": "CAT", "名称": "十类别齐备",
            "判据": "固定 10 类每类都有区块（缺哪类报哪类）：1 品类与形态／2 竞品与替代品／3 官方功能／"
                    "4 使用场景／5 人群与职业／6 内容形态与创作者类型／7 市场与语言／8 节奏与档期／"
                    "9 品牌与型号／10 扩圈相邻垂类",
            "来源": "§2.1.10 B 类别体系（固定 10 类）",
        },
        {
            "编号": "CATQ", "名称": "每类词量下限",
            "判据": "每类 Tag ≥4、短尾词 ≥5、长句 ≥3",
            "来源": "§2.1.10 C 词量下限；模板 §0.1 交付前自查（硬指标）",
        },
        {
            "编号": "TOTAL", "名称": "全表词量下限",
            "判据": "全表合计（Tag ＋ 短尾词 ＋ 条件词 ＋ 长句）≥ %d 条" % MIN_TOTAL,
            "来源": "§2.1.10 C；模板 §0.1（不达标不得交付）",
        },
        {
            "编号": "DUP", "名称": "类内重复词面",
            "判据": "同一类别内 Tag 行与短尾词行的词面不得完全重复（两行都是「可直接使用」的词，"
                    "重复即冗余；去重时词归位 Tag 行并按语料／官方型号等量补词）",
            "来源": "§2.1.10 A（Tag 行与短尾词行不得出现完全重复条目）",
        },
        {
            "编号": "COND", "名称": "条件词被单搜",
            "判据": "条件词（仅作「且」、不得单搜）不得出现在同一类的短尾词行"
                    "（短尾词行是关键词框直搜、可单独使用的词）",
            "来源": "§2.1.10 A 行④；§2.1.9 B2（能力/场景词只能做 AND 约束，禁止单独成词）",
        },
        {
            "编号": "DECO", "名称": "词面装饰符号",
            "判据": "词面格内不得出现井号／Markdown 星号／反引号；Tag／短尾词／条件词行另不得出现引号"
                    "（要整格复制即用）",
            "来源": "§2.1.10 A（单元格内容必须「复制即用」：Tag 不带 #、长句不带行号、短尾词不带引号）",
        },
        {
            "编号": "NEG", "名称": "命中负向排除词",
            "判据": "词面不得命中 giveaway／deals-only／meme 类负向词（整词匹配）；命中即会召回偏题号",
            "来源": NEGATIVE_SOURCE,
        },
        {
            "编号": "BAN", "名称": "命中词表自带的禁用词",
            "判据": "词面不得出现词表自带的「禁用词」清单里的表述（品牌书未覆盖／未核验的表述不得进检索式）；"
                    "词表没有禁用词清单时本判据不适用",
            "来源": "模板 §5 交付前自检；样本 §3 排除清单与禁用词",
        },
        {
            "编号": "SENT", "名称": "长句格式",
            "判据": "长句一条一行、每条以英文句号收尾",
            "来源": "§2.1.10 A 飞书排版硬规则（长句必须自带英文句号）",
        },
        {
            "编号": "REGION", "名称": "地域锚点位置",
            "判据": "词面里出现地域锚点时必须置于词首（`uk office chair` ✅／`office chair uk` ❌）",
            "来源": REGION_SOURCE,
        },
        {
            "编号": "COUNT", "名称": "计数自洽（导语表 vs 明细）",
            "判据": "全书导语表声明的每类 Tag／短尾词／条件词／长句数 == 明细实点数；"
                    "文件没有导语表时本判据不适用",
            "来源": "§2.1.10 A 全书导语表；§2.2.6 计数自洽（教训 67／CLS-67）",
        },
    )


def judge_ids():
    return tuple(j["编号"] for j in judge_specs())


# ─────────────────────────── 词表解析 ───────────────────────────
#: 模板空壳里的占位符写法（模板 §二 的「（待填：…）」）：它不是词面，不计入词量，
#: 也不该被当成"装饰符号不合规"来报 —— 但它必须被**说出来**（见提示「待填占位符」）。
_PLACEHOLDER_RE = re.compile(r"^[（(\[*`\s]*待填")
_CAT_RE = re.compile(r"^#{2,4}\s*类别\s*(\d+)\s*[｜|]\s*(.*?)\s*$")
_OVERVIEW_RE = re.compile(r"^\|\s*(\d{1,2})\s*[.．、]\s*([^|]*)\|")
_TYPE_LABEL_RE = {
    "Tag": re.compile(r"^\**\s*Tag\b"),
    "长句": re.compile(r"^\**\s*长句\b"),
    "短尾词": re.compile(r"^\**\s*短尾词\b"),
    "条件词": re.compile(r"^\**\s*条件词\b"),
}


def is_placeholder(word):
    """是不是模板占位符（「待填…」）：模板空壳不是"不合规的词表"，是要先填的表。"""
    return bool(_PLACEHOLDER_RE.match(str(word or "")))


def _clean_category(number, raw_name):
    name = re.sub(r"[*`]", "", raw_name or "").strip()
    name = name.split("——")[0].split("—")[0].strip()
    return "%d %s" % (number, name or CATEGORY_NAMES.get(number, ""))


def parse_markdown(text):
    """解析产出标准 v2 的 md 结构；返回 `(词表, 导语表声明, 提示)`。

    词表：`{类别键: {类型: [词面, …]}}`；导语表声明：`{类别号: {类型: 条数}}`（没有则 `{}`）。
    """
    rows = {}
    declared = {}
    notes = []
    placeholders = 0
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        m = _CAT_RE.match(stripped)
        if m:
            current = _clean_category(int(m.group(1)), m.group(2))
            rows.setdefault(current, {t: [] for t in ROW_TYPES})
            continue
        if stripped.startswith("## ") and not stripped.startswith("### "):
            current = None                      # 离开类别区块（附录／排除清单等）
            continue

        # 全书导语表：`| 1. 品类与形态 | 用途 | Tag 数 | 短尾数 | 条件词数 | 长句数 |`（§2.1.10 A）
        if stripped.startswith("|"):
            om = _OVERVIEW_RE.match(stripped)
            if om:
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                if len(cells) >= 6 and all(re.fullmatch(r"\d+", c or "") for c in cells[2:6]):
                    declared[int(om.group(1))] = {
                        "Tag": int(cells[2]), "短尾词": int(cells[3]),
                        "条件词": int(cells[4]), "长句": int(cells[5]),
                    }
            if current is None:
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) < 2:
                continue
            kind = None
            for label, pattern in _TYPE_LABEL_RE.items():
                if pattern.match(cells[0]):
                    kind = label
                    break
            if kind is None:
                continue
            body = cells[1]
            if is_placeholder(body):
                # 整格都是模板写法（例：「（待填：`锚点 + 能力` 组合式，如 `smart glasses meeting notes`）」）
                # → 整格按占位符跳过：不能把它按逗号切开，把提示语的后半截当成一个词面来报违规。
                placeholders += 1
                continue
            if "<br" in body:
                note = ("长句格用 <br> 分隔（本地 md 的常规写法，按「一条一行」解析）："
                        "若这份词表要导入飞书文档，<br> 必须换成多个 <p>（软换行不给段间距）"
                        "——来源：§2.1.10 A 飞书排版硬规则；发布后回读校验 <br> 计数须为 0")
                if note not in notes:
                    notes.append(note)
            parts = re.split(r"<br\s*/?>|\n", body) if kind == "长句" \
                else re.split(r"[,，\n]|<br\s*/?>", body)
            for part in parts:
                word = part.strip()
                if is_placeholder(word):
                    placeholders += 1   # 模板占位符（「待填…」）不是词面：单独提示，不计入词量
                    continue
                if word:
                    rows[current][kind].append(word)

    # 去掉类别区块里"整行空着"的假象：没有词的行仍然保留（缺失本身就是要报的事实）
    for key, table in rows.items():
        for kind in ROW_TYPES:
            table.setdefault(kind, [])
    if placeholders:
        notes.append({
            "提示": "文件里有「待填」占位符",
            "词面": "（待填…）",
            "处数": placeholders,
            "为什么只提示不判违规": "这是模板空壳的写法（模板 §二），不是「不合规的词面」：按占位符跳过、"
                                    "不计入词量，也不算装饰符号或长句格式违规；"
                                    "词量判据（CATQ／TOTAL）会把「还没填」这件事如实报出来",
            "来源": "模板 §二（空壳写法）",
        })
    return rows, declared, notes


def parse_rows(flat_rows):
    """把「一行一个词面」的扁平结构聚成类别词表（csv／json 共用；顺序即出现顺序）。"""
    rows = {}
    for item in flat_rows:
        if not isinstance(item, dict):
            raise CliError("词表格式不对：每条记录都必须是对象（含 类别／类型／检索词）")
        cat = str(item.get("类别") or "").strip()
        kind = str(item.get("类型") or "").strip()
        word = str(item.get("检索词") or "").strip()
        if not cat or not kind or not word:
            raise CliError("词表格式不对：类别／类型／检索词 三项都不能为空（问题记录：%r）" % (item,))
        if kind not in ROW_TYPES:
            raise CliError("词表格式不对：类型只能是 %s（收到 %r）" % ("／".join(ROW_TYPES), kind))
        if cat not in rows:
            rows[cat] = {t: [] for t in ROW_TYPES}
        if is_placeholder(word):
            continue                    # 模板占位符不是词面（与 md 口径一致）
        rows[cat][kind].append(word)
    return rows


def parse_csv(text):
    reader = csv.reader(io.StringIO(text))
    flat = []
    header = None
    for raw in reader:
        cells = [c.strip() for c in raw]
        if not any(cells):
            continue
        if header is None:
            if cells[:3] == ["类别", "类型", "检索词"]:
                header = cells
                continue
            header = ["类别", "类型", "检索词"]
        if len(cells) < 3:
            raise CliError("csv 词表每行需要三列：类别,类型,检索词（问题行：%s）" % ",".join(cells))
        flat.append({"类别": cells[0], "类型": cells[1], "检索词": cells[2]})
    if not flat:
        raise CliError("csv 词表里没有任何词面（表头应为 类别,类型,检索词，一行一个词面）")
    return parse_rows(flat)


def parse_json(text):
    try:
        doc = json.loads(text)
    except ValueError as e:
        raise CliError("json 词表不是合法 JSON：%s" % e)
    if isinstance(doc, list):
        return parse_rows(doc)
    if not isinstance(doc, dict):
        raise CliError("json 词表的顶层必须是对象或数组")
    if isinstance(doc.get("检索词"), list):
        return parse_rows(doc["检索词"])
    if isinstance(doc.get("类别"), list):
        rows = {}
        for item in doc["类别"]:
            if not isinstance(item, dict) or not item.get("类别"):
                raise CliError("json 词表格式不对：类别项需要 {\"类别\": …, \"Tag\": [...], …}")
            cat = str(item["类别"]).strip()
            rows[cat] = {t: [str(x).strip() for x in (item.get(t) or []) if str(x).strip()]
                         for t in ROW_TYPES}
        return rows
    raise CliError("json 词表里找不到词面：请给 `检索词` 数组或 `类别` 数组（格式见 --help）")


def parse_file(path):
    """按扩展名选解析器；返回 `(词表, 导语表声明, 提示, 格式名)`。"""
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as e:
        raise CliError("词表文件读不出来：%s（%s）" % (path, e), code=EXIT_USAGE)
    except UnicodeDecodeError:
        raise CliError("词表文件不是 UTF-8 文本：%s" % path, code=EXIT_USAGE)
    if ext in (".md", ".markdown", ""):
        rows, declared, notes = parse_markdown(text)
        return rows, declared, notes, "md"
    if ext == ".csv":
        return parse_csv(text), {}, [], "csv"
    if ext == ".json":
        return parse_json(text), {}, [], "json"
    raise CliError("不认识的词表格式：%s（支持 md／csv／json，见 --help）" % (ext or "（无扩展名）"),
                   code=EXIT_USAGE)


def resolve_file(raw, start=None):
    """定位词表文件：绝对路径直接用；相对路径按「当前目录 → 逐级向上 → 仓库根」找。

    为什么要逐级向上：契约与命令可能从任意子目录被调起（宿主不同、cwd 不同），
    而契约里写的词表路径是**工作区根**的相对路径 —— 这样换宿主也能跑通。
    """
    p = os.path.abspath(os.path.expanduser(str(raw)))
    if os.path.isfile(p):
        return p
    if os.path.isabs(str(raw)):
        return None
    cur = os.path.abspath(start or os.getcwd())
    for _ in range(8):
        cand = os.path.join(cur, str(raw))
        if os.path.isfile(cand):
            return cand
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        cur = nxt
    try:                                        # 再退一步：能力目录所在的仓库根
        from ..runtime import repo_root
        cand = os.path.join(repo_root(), str(raw))
        if os.path.isfile(cand):
            return cand
    except Exception:                                                       # noqa: BLE001
        pass
    return None


# ─────────────────────────── 逐条判据 ───────────────────────────
def _word_hits(text, needles):
    """整词匹配（避免 `tech deals` 被 `deals-only` 那条误伤）。"""
    low = text.lower()
    out = []
    for needle in needles:
        if re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(needle.lower()), low):
            out.append(needle)
    return out


def _find_banned_words(text):
    """找词表自带的「禁用词」清单（模板 §5 与样本 §3 都写在含"禁用词"的那一行冒号后）。"""
    items = []
    for line in text.splitlines():
        if "禁用词" not in line or "：" not in line and ":" not in line:
            continue
        tail = re.split(r"[：:]", line, 1)[-1]
        tail = tail.strip().lstrip("*").strip()
        for piece in re.split(r"[、，,；;/]", tail):
            piece = piece.strip().strip("。*`（）() ")
            if len(piece) >= 3 and not piece.startswith("- ["):
                items.append(piece)
    return sorted(set(items))


def run_judges(rows, declared_counts, file_text, only=None):
    """跑判据；返回 `(判据结论列表, 全部违规, 提示, 统计)`。"""
    selected = set(only or judge_ids())
    unknown = sorted(selected - set(judge_ids()))
    if unknown:
        raise CliError("未知判据编号：%s（可用：%s）"
                       % ("／".join(unknown), "／".join(judge_ids())), code=EXIT_USAGE,
                       hint="用 `daniel keywords check --file <词表> --json` 看每条判据的编号与来源")

    cats = list(rows)
    numbers = []
    for key in cats:
        m = re.match(r"^(\d+)", key)
        if m:
            numbers.append(int(m.group(1)))
    missing = [n for n in sorted(CATEGORY_NAMES) if n not in numbers]

    totals = {t: sum(len(rows[c][t]) for c in cats) for t in ROW_TYPES}
    total_all = sum(totals.values())

    results = []
    all_violations = []
    notes = []

    def add(spec, violations, ok_detail, extra=None):
        results.append({
            "编号": spec["编号"], "名称": spec["名称"], "判据": spec["判据"], "来源": spec["来源"],
            "可机械化": True,
            "结论": "通过" if not violations else "违规",
            "违规条数": len(violations),
            "明细": (violations[:20] if violations else [ok_detail]) + (
                ["……另有 %d 条，用 --json 取全量" % (len(violations) - 20)] if len(violations) > 20 else []),
            "补充": extra or [],
        })
        all_violations.extend(violations)

    #: 格式都读不出来时，后续判据**一律记「不适用」**：拿一份解析不到词面的文件去报
    #: "十类缺十类／词量为 0" 是**假判**（不是判不了，是没得判）—— 机器不许在这里假装有结论。
    format_ok = bool(cats)

    for spec in judge_specs():
        jid = spec["编号"]
        if jid not in selected:
            results.append({"编号": jid, "名称": spec["名称"], "判据": spec["判据"],
                            "来源": spec["来源"], "可机械化": True, "结论": "未跑",
                            "违规条数": 0, "明细": ["本次只跑了指定的判据（--only），本判据未评估"],
                            "补充": []})
            continue

        if not format_ok and jid != "FMT":
            results.append({"编号": jid, "名称": spec["名称"], "判据": spec["判据"],
                            "来源": spec["来源"], "可机械化": True, "结论": "不适用",
                            "违规条数": 0,
                            "明细": ["词表格式读不出来（没有识别到任何类别区块），本判据无从评起；"
                                      "先按 `daniel keywords --help` 的「词表格式」改写文件"
                                      "（支持 md 类别表结构／csv／json 三种写法）"],
                            "补充": []})
            continue

        if jid == "FMT":
            bad = [] if cats else [{"类别": "（整个文件）", "类型": "—", "词面": "",
                                    "违规判据": jid, "违规说明": "没有解析到任何类别区块",
                                    "来源": spec["来源"]}]
            empty = [c for c in cats if not any(rows[c][t] for t in ROW_TYPES)]
            for c in empty:
                bad.append({"类别": c, "类型": "—", "词面": "", "违规判据": jid,
                            "违规说明": "该类别区块里没有任何词面行", "来源": spec["来源"]})
            add(spec, bad, "解析到 %d 个类别区块、%d 条词面" % (len(cats), total_all))

        elif jid == "CAT":
            bad = [{"类别": "%d %s" % (n, CATEGORY_NAMES[n]), "类型": "—", "词面": "",
                    "违规判据": jid, "违规说明": "固定 10 类里缺这一类", "来源": spec["来源"]}
                   for n in missing]
            add(spec, bad, "十类别齐备（%s）" % "／".join("%d" % n for n in sorted(numbers)))

        elif jid == "CATQ":
            bad = []
            for c in cats:
                for t, floor in MIN_PER_TYPE.items():
                    n = len(rows[c][t])
                    if n < floor:
                        bad.append({"类别": c, "类型": t, "词面": "",
                                    "违规判据": jid,
                                    "违规说明": "本类 %s 只有 %d 条，低于下限 %d 条" % (t, n, floor),
                                    "来源": spec["来源"]})
            add(spec, bad, "每类 Tag ≥4、短尾词 ≥5、长句 ≥3 全部达标")

        elif jid == "TOTAL":
            bad = []
            if total_all < MIN_TOTAL:
                bad.append({"类别": "（全表）", "类型": "—", "词面": "",
                            "违规判据": jid,
                            "违规说明": "全表合计只有 %d 条，低于下限 %d 条" % (total_all, MIN_TOTAL),
                            "来源": spec["来源"]})
            add(spec, bad, "全表合计 %d 条（下限 %d 条）" % (total_all, MIN_TOTAL))

        elif jid == "DUP":
            bad = []
            for c in cats:
                shared = sorted(set(rows[c]["Tag"]) & set(rows[c]["短尾词"]))
                for w in shared:
                    bad.append({"类别": c, "类型": "Tag／短尾词", "词面": w,
                                "违规判据": jid,
                                "违规说明": "同一类别内 Tag 行与短尾词行完全重复（应归位 Tag 行并等量补词）",
                                "来源": spec["来源"]})
            add(spec, bad, "类内 Tag 行与短尾词行无完全重复条目")

        elif jid == "COND":
            bad = []
            for c in cats:
                shared = sorted(set(rows[c]["条件词"]) & set(rows[c]["短尾词"]))
                for w in shared:
                    bad.append({"类别": c, "类型": "条件词／短尾词", "词面": w,
                                "违规判据": jid,
                                "违规说明": "条件词只能作「且」、不得单搜，却出现在短尾词行",
                                "来源": spec["来源"]})
            add(spec, bad, "没有任何条件词被当成短尾词单搜")

        elif jid == "DECO":
            bad = []
            for c in cats:
                for t in ROW_TYPES:
                    for w in rows[c][t]:
                        table = dict(DECOR_ALWAYS)
                        if t != "长句":
                            table.update(DECOR_SHORT_ROWS)
                        hits = [why for ch, why in table.items() if ch in w]
                        if hits:
                            bad.append({"类别": c, "类型": t, "词面": w, "违规判据": jid,
                                        "违规说明": "词面里有装饰符号：%s（要整格复制即用）"
                                                    % "／".join(sorted(set(hits))),
                                        "来源": spec["来源"]})
            add(spec, bad, "词面都是「复制即用」的干净写法")

        elif jid == "NEG":
            bad = []
            for c in cats:
                for t in ROW_TYPES:
                    for w in rows[c][t]:
                        hits = _word_hits(w, NEGATIVE_WORDS)
                        if hits:
                            bad.append({"类别": c, "类型": t, "词面": w, "违规判据": jid,
                                        "违规说明": "命中负向排除词：%s（命中即偏题，会把赠品号／折扣号／"
                                                    "梗号召回进来）" % "／".join(hits),
                                        "来源": spec["来源"]})
            add(spec, bad, "没有任何词命中负向排除词（giveaway／deals-only／meme 类）")

        elif jid == "BAN":
            banned = _find_banned_words(file_text)
            if not banned:
                results.append({"编号": jid, "名称": spec["名称"], "判据": spec["判据"],
                                "来源": spec["来源"], "可机械化": True, "结论": "不适用",
                                "违规条数": 0,
                                "明细": ["词表里没有「禁用词」清单（品牌书未给未核验表述时属正常），本判据不适用"],
                                "补充": []})
                continue
            bad = []
            for c in cats:
                for t in ROW_TYPES:
                    for w in rows[c][t]:
                        hits = [b for b in banned if b.lower() in w.lower()]
                        if hits:
                            bad.append({"类别": c, "类型": t, "词面": w, "违规判据": jid,
                                        "违规说明": "命中词表自带的禁用词：%s" % "／".join(hits),
                                        "来源": spec["来源"]})
            add(spec, bad, "没有词命中词表自带的禁用词清单",
                extra=["本次使用的禁用词清单：%s" % "／".join(banned)])

        elif jid == "SENT":
            bad = []
            for c in cats:
                for w in rows[c]["长句"]:
                    if not w.rstrip().endswith("."):
                        bad.append({"类别": c, "类型": "长句", "词面": w, "违规判据": jid,
                                    "违规说明": "长句没有以英文句号收尾（分句边界与读者观感都靠它）",
                                    "来源": spec["来源"]})
            add(spec, bad, "长句均一条一行、以英文句号收尾")

        elif jid == "REGION":
            # 只判「投喂短词」三类（Tag／短尾词／条件词）：语料实测的是**短词**投喂结果
            # （`us office chair` ✅／`office chair uk` ❌），而长句是喂给语义搜索的自然语言句子，
            # 语料明说「长句按原样投喂即可」（§2.1.10 D 末）。拿长句来判就是误伤。
            bad = []
            ordered = sorted(REGION_TOKENS, key=len, reverse=True)
            for c in cats:
                for t in ("Tag", "短尾词", "条件词"):
                    for w in rows[c][t]:
                        hits = _word_hits(w, REGION_TOKENS)
                        if not hits:
                            continue
                        if any(w.lower().startswith(tok) for tok in ordered):
                            continue
                        bad.append({"类别": c, "类型": t, "词面": w, "违规判据": jid,
                                    "违规说明": "地域锚点没在词首（命中：%s）：后缀写法召回到的行不可用"
                                                "（拿不到订阅量／所在地）" % "／".join(hits),
                                    "来源": spec["来源"]})
            add(spec, bad, "凡带地域锚点的投喂短词，地域词都在词首")

        elif jid == "COUNT":
            if not declared_counts:
                results.append({"编号": jid, "名称": spec["名称"], "判据": spec["判据"],
                                "来源": spec["来源"], "可机械化": True, "结论": "不适用",
                                "违规条数": 0,
                                "明细": ["文件里没有「全书导语表」（类别｜用途｜Tag｜短尾词｜条件词｜长句），"
                                          "本判据不适用"], "补充": []})
                continue
            bad = []
            actual = {}
            for c in cats:
                m = re.match(r"^(\d+)", c)
                if m:
                    actual[int(m.group(1))] = {t: len(rows[c][t]) for t in ROW_TYPES}
            for n, decl in sorted(declared_counts.items()):
                got = actual.get(n)
                if got is None:
                    bad.append({"类别": "%d %s" % (n, CATEGORY_NAMES.get(n, "")), "类型": "—",
                                "词面": "", "违规判据": jid,
                                "违规说明": "导语表声明了这一类，但明细里没有这一类区块",
                                "来源": spec["来源"]})
                    continue
                for t in ROW_TYPES:
                    if decl.get(t) != got[t]:
                        bad.append({"类别": "%d %s" % (n, CATEGORY_NAMES.get(n, "")), "类型": t,
                                    "词面": "", "违规判据": jid,
                                    "违规说明": "导语表声明 %d 条，明细实点 %d 条"
                                                % (decl.get(t), got[t]),
                                    "来源": spec["来源"]})
            add(spec, bad, "导语表声明的每类词量与明细实点数逐格一致",
                extra=["导语表覆盖 %d 个类别" % len(declared_counts)])

    # 提示（不计违规）：跨类别重复词面 —— 语料的「零重合」纪律是**跨文件**（扩圈词表 vs 同项目垂直词表）
    # 且定于 2026-09-17（教训 81/83），单份文件判不了"是否已被投喂过"，只报出来供人工复核。
    seen = {}
    for c in cats:
        for t in ("Tag", "短尾词", "长句"):
            for w in rows[c][t]:
                if w in seen and seen[w][0] != c:
                    notes.append({
                        "提示": "跨类别出现同一词面",
                        "词面": w, "首见": "%s／%s" % (seen[w][0], seen[w][1]),
                        "再现": "%s／%s" % (c, t),
                        "为什么只提示不判违规": "语料的「零重合」纪律是跨文件纪律（扩圈词表对同项目垂直词表，"
                                                "教训 81／83，2026-09-17 定），单份文件判不出"
                                                "「是否已被垂直批次投喂过」",
                        "来源": "§2.1.10 D；模板 §二（扩圈零重合）",
                    })
                else:
                    seen.setdefault(w, (c, t))
    if "待填" in file_text and not any("待填" in str(n) for n in notes):
        notes.append({"提示": "文件里有「待填」占位符", "词面": "待填",
                      "为什么只提示不判违规": "模板空壳与未完成的词表都会命中；词量判据（CATQ／TOTAL）"
                                              "会把「还没填」这件事如实报出来",
                      "来源": "模板 §二（空壳写法）"})

    stats = {"类别数": len(cats), "类别号": sorted(numbers), "缺类别": missing,
             "逐类": [dict({"类别": c}, **{t: len(rows[c][t]) for t in ROW_TYPES}) for c in cats],
             "分类型": totals, "合计": total_all}
    return results, all_violations, notes, stats


# ─────────────────────────── 报告 ───────────────────────────
def build_report(path, fmt, brand, rows, declared, file_notes, only=None):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    results, violations, notes, stats = run_judges(rows, declared, text, only=only)
    judged = [r for r in results if r["结论"] != "未跑"]
    not_applicable = [r for r in judged if r["结论"] == "不适用"]

    # 交付件＝**校验结果清单**（一条词一行：词、类别、类型、是否合规、命中哪条判据）
    bad_index = {}
    for v in violations:
        bad_index.setdefault((v["类别"], v["类型"], v["词面"]), []).append(
            "%s（%s）" % (v["违规判据"], v["违规说明"]))
    rows_out = []
    seq = 0
    for c in rows:
        for t in ROW_TYPES:
            for w in rows[c][t]:
                seq += 1
                hits = bad_index.get((c, t, w)) or []
                rows_out.append({"序号": seq, "类别": c, "类型": t, "检索词": w,
                                 "是否合规": "否" if hits else "是",
                                 "命中判据": "；".join(hits) if hits else "—"})

    # 提示去重：解析器与判据层可能各报一条同类提示（例如「待填」占位符），只留第一条
    hints, seen_hints = [], set()
    for item in list(file_notes) + notes:
        key = item.get("提示") if isinstance(item, dict) else str(item)
        if key in seen_hints:
            continue
        seen_hints.add(key)
        hints.append(item)

    return {
        "词表": {"文件": path, "格式": fmt, "品牌": brand or None,
                 "品牌说明": "只作归属标注：本命令不联网、不查任何账号／品牌档案"},
        "count": len(violations),
        "计数口径": "count = 本次所跑判据的**违规项数**（0 表示全合规）；"
                    "全量词量见「规模」，交付件行数见「检索词清单」",
        "合规": not violations,
        "判据": results,
        "违规": violations,
        "提示": hints,
        "需人工判断": [dict(m) for m in MANUAL_JUDGEMENTS],
        "规模": stats,
        "检索词清单": rows_out,
        "展示口径": "全量展示：%d 条（未截断）" % len(rows_out),
        "结论": {
            "合规": not violations,
            "判据条数": len(judged),
            "判据通过": len([r for r in judged if r["结论"] == "通过"]),
            "判据违规": len([r for r in judged if r["结论"] == "违规"]),
            "判据不适用": len(not_applicable),
            "违规项数": len(violations),
            "需人工判断项数": len(MANUAL_JUDGEMENTS),
            "摘要": ("词表合规：%d 条判据全部通过（另有 %d 条不适用），违规 0 条；"
                     "全表 %d 条词面、%d 个类别" % (len(judged) - len(not_applicable),
                                                len(not_applicable), stats["合计"], stats["类别数"]))
            if not violations else
            ("词表不合规：%d 条判据里 %d 条报出违规，共 %d 条违规项（逐条见「违规」）"
             % (len(judged), len([r for r in judged if r["结论"] == "违规"]), len(violations))),
        },
    }


def _truncate(rows_out, limit, report):
    """样本模式：只展示前 N 条时**逐行标注**，绝不静默截断（与「跳过 ≠ 通过」同一口径）。

    标注落在两处：报告字段 `展示口径`／`被截断条数`，以及**每一行**的「展示口径」列 ——
    这样交付件（由清单直接出件）里也写着"仅展示前 N 条、全量 X 条"，读件的人不会把
    截断后的清单当成全量。
    """
    total = len(rows_out)
    if not limit or limit <= 0 or total <= limit:
        return rows_out
    label = "样本模式：仅展示前 %d 条，全量 %d 条（要取全量请用 --rows 0）" % (limit, total)
    report["展示口径"] = label
    report["被截断条数"] = total - limit
    return [dict(r, 展示口径=label) for r in rows_out[:limit]]


def render_human(report, limit=None):
    """给人看的中文陈述（业务语言，不写内部代号）。"""
    lines = []
    wl = report["词表"]
    lines.append("检索词清单校验（只读：只读入词表文件，不联网、不写任何东西）")
    lines.append("词表文件：%s（%s）" % (wl["文件"], wl["格式"]))
    if wl.get("品牌"):
        lines.append("归属品牌：%s（只作标注：本命令不联网、不查品牌档案）" % wl["品牌"])
    stats = report["规模"]
    lines.append("规模：%d 个类别，合计 %d 条词面（Tag %d｜短尾词 %d｜条件词 %d｜长句 %d）"
                 % (stats["类别数"], stats["合计"], stats["分类型"]["Tag"], stats["分类型"]["短尾词"],
                    stats["分类型"]["条件词"], stats["分类型"]["长句"]))
    lines.append("结论：%s" % report["结论"]["摘要"])
    lines.append("")

    lines.append("判据 → 来源（逐条）：")
    for r in report["判据"]:
        if r["结论"] == "未跑":
            continue
        head = "  [%s] %s：%s" % (r["编号"], r["名称"], r["结论"])
        if r["结论"] == "违规":
            head += "（违规 %d 条）" % r["违规条数"]
        lines.append(head)
        lines.append("      来源：%s" % r["来源"])
        for d in (r["明细"] or [])[:3]:
            if isinstance(d, dict):
                lines.append("      · %s／%s：%s → %s"
                             % (d.get("类别"), d.get("类型"), d.get("词面") or "（整类）",
                                d.get("违规说明")))
            else:
                lines.append("      · %s" % d)
    lines.append("")

    if report["违规"]:
        lines.append("违规项（逐条）：")
        for i, v in enumerate(report["违规"][:limit or 40], 1):
            lines.append("  %d. [%s] %s／%s：%s —— %s"
                         % (i, v["违规判据"], v["类别"], v["类型"], v["词面"] or "（整类）",
                            v["违规说明"]))
        if limit and len(report["违规"]) > limit:
            lines.append("  ……另有 %d 条，见 --json 的「违规」" % (len(report["违规"]) - limit))
    else:
        lines.append("违规项：无")
    lines.append("")

    if report["提示"]:
        lines.append("提示（不计违规，供人工复核）：")
        for n in report["提示"][:10]:
            if isinstance(n, dict) and n.get("词面"):
                if n.get("首见"):
                    lines.append("  · %s：%s（首见 %s／再现 %s）"
                                 % (n.get("提示"), n["词面"], n.get("首见"), n.get("再现")))
                else:
                    lines.append("  · %s：%s" % (n.get("提示"), n["词面"]))
            else:
                lines.append("  · %s" % (n if isinstance(n, str) else n.get("提示")))
        if any(isinstance(n, dict) and n.get("为什么只提示不判违规") for n in report["提示"]):
            lines.append("     为什么只提示不判违规：%s"
                         % next(n["为什么只提示不判违规"] for n in report["提示"]
                                if isinstance(n, dict) and n.get("为什么只提示不判违规")))
        lines.append("")

    lines.append("需人工判断（本命令判不了，交付前必须人工过一遍）：")
    for i, m in enumerate(report["需人工判断"], 1):
        lines.append("  %d. %s" % (i, m["项"]))
        lines.append("     来源：%s" % m["来源"])
        lines.append("     为什么机器判不了：%s" % m["为什么机器判不了"])
        lines.append("     怎么补：%s" % m["怎么补"])
    lines.append("")
    lines.append("交付件（检索词清单·校验结果，一条词一行）：%d 条；%s"
                 % (len(report["检索词清单"]), report["展示口径"]))
    lines.append("退出码：0＝已给出结论（看「合规」字段）；2＝词表用不了或用了 --strict-exit 时发现违规")
    return "\n".join(lines)


# ─────────────────────────── 命令 ───────────────────────────
def cmd_check(ctx):
    raw = ctx.require("--file", "--file（词表文件：md／csv／json）")
    brand = ctx.get("brand")
    only = ctx.get("only") or []
    rows_limit = ctx.get("rows") or 0
    path = resolve_file(raw)
    if path is None:
        raise CliError("找不到词表文件：%s" % raw, code=EXIT_USAGE,
                       hint="--file 支持 md／csv／json；相对路径会从当前目录逐级向上找，"
                            "也可以直接给绝对路径")
    ctx.progress("正在读入词表（只读）：%s" % path)
    rows, declared, file_notes, fmt = parse_file(path)
    report = build_report(path, fmt, brand, rows, declared, file_notes, only=only)
    if rows_limit:
        kept = _truncate(report["检索词清单"], rows_limit, report)
        report["检索词清单"] = kept
    if report["违规"]:
        ctx.warn("词表有 %d 条违规项（逐条见结果的「违规」）" % len(report["违规"]))
    strict = bool(ctx.get("strict_exit"))
    code = EXIT_OK
    if report["违规"] and strict:
        code = EXIT_USAGE
        ctx.warn("--strict-exit：有违规即按「当场拦下」处理，退出码 %d" % code)
    if report["违规"]:
        ctx.emit_raw(ok=False, exit_code=code, data=report, human=render_human(report, limit=rows_limit or None))
    else:
        ctx.emit(data=report, human=render_human(report, limit=rows_limit or None))
    return code


# ─────────────────────────── 自检（自带，不接进 CLI 总自检） ───────────────────────────
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLI_PATH = os.path.join(_PKG_ROOT, "bin", "daniel")


def _sample_path():
    """仓库内的合规样本（只读引用，不改）。剥离分发后可能不在，自检会如实记「跳过」。"""
    try:
        from ..runtime import repo_root
        root = repo_root()
    except Exception:                                                       # noqa: BLE001
        return None
    cand = os.path.join(root, "docs", "marketing", "kol",
                        "2026-09-halliday-g2-kol-search-matrix-v4.md")
    return cand if os.path.isfile(cand) else None


def _degraded_path():
    """随包自带的退化样本（故意不合规，用来证明真的会被拦下）。"""
    return os.path.join(_PKG_ROOT, "contracts", "_examples", "degraded-search-matrix.md")


def _run_cli(argv, timeout=300):
    p = subprocess.run([sys.executable, CLI_PATH] + list(argv),
                       capture_output=True, text=True, timeout=timeout)
    doc = None
    try:
        doc = json.loads(p.stdout)
    except ValueError:
        doc = None
    return p.returncode, doc, p.stdout or "", p.stderr or ""


def _write_json_mode_min_fixture(workdir):
    """合成一份"刚好达标"的最小合规词表（10 类 × 每类 Tag10／短尾10／条件5／长句5 ＝ 300 条）。"""
    rows = []
    for n in sorted(CATEGORY_NAMES):
        cat = "%d %s" % (n, CATEGORY_NAMES[n])
        for i in range(1, 11):
            rows.append({"类别": cat, "类型": "Tag", "检索词": "fixture cat%d tag %02d" % (n, i)})
            rows.append({"类别": cat, "类型": "短尾词",
                         "检索词": "fixture cat%d short tail %02d" % (n, i)})
        for i in range(1, 6):
            rows.append({"类别": cat, "类型": "条件词", "检索词": "fixture cat%d and %02d" % (n, i)})
            rows.append({"类别": cat, "类型": "长句",
                         "检索词": "Find creators who test fixture product model %d-%02d." % (n, i)})
    paths = {}
    jp = os.path.join(workdir, "fixture.json")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump({"检索词": rows}, fh, ensure_ascii=False, indent=1)
    paths["json"] = jp
    cp = os.path.join(workdir, "fixture.csv")
    with open(cp, "w", encoding="utf-8") as fh:
        fh.write("类别,类型,检索词\n")
        for r in rows:
            fh.write("%s,%s,%s\n" % (r["类别"], r["类型"], r["检索词"]))
    paths["csv"] = cp
    mp = os.path.join(workdir, "fixture.md")
    with open(mp, "w", encoding="utf-8") as fh:
        for n in sorted(CATEGORY_NAMES):
            cat = "%d %s" % (n, CATEGORY_NAMES[n])
            fh.write("### 类别 %d ｜ %s —— 自检夹具\n\n" % (n, CATEGORY_NAMES[n]))
            fh.write("| 类型 | 搜索词 | 用途 |\n|---|---|---|\n")
            for t in ROW_TYPES:
                words = [r["检索词"] for r in rows if r["类别"] == cat and r["类型"] == t]
                if not words:
                    continue
                fh.write("| **%s**（自检夹具） | %s | 自检用 |\n"
                         % (t, "<br>".join(words) if t == "长句" else ", ".join(words)))
            fh.write("\n")
    paths["md"] = mp
    return paths


def _source_write_scan():
    """源码级断言：**校验路径**里没有任何写文件的调用（写只允许出现在自检夹具代码里）。

    判据＝模块源码 `# ── 自检` 标记之前的行里不得出现写模式的 open。
    """
    me = os.path.abspath(__file__)
    with open(me, encoding="utf-8") as fh:
        text = fh.read()
    marker = "# ─────────────────────────── 自检"
    head = text.split(marker)[0]
    hits = [ln.strip() for ln in head.splitlines()
            if re.search(r"open\([^)]*[\"'](w|a|w\+|a\+)[\"']", ln)]
    return hits


def run_selftest(emitter):
    """`daniel keywords --self-test`：本模块自带自检（正控 ＋ 退化正控 ＋ 反例）。"""
    items = []

    def item(desc, ok, detail=""):
        items.append({"说明": desc, "通过": bool(ok), "明细": detail})
        if not emitter.json_mode:
            print("  %s %s%s" % ("通过" if ok else "不通过", desc,
                                 ("  —— " + detail) if detail else ""), flush=True)
        return bool(ok)

    if not emitter.json_mode:
        print("keywords 模块自检（检索词清单校验 · 只读）", file=emitter.out)
        print("说明：正控要求合规样本通过；退化正控要求故意不合规的样本被拦下并逐条指出违规项。",
              file=emitter.out)
    workdir = tempfile.mkdtemp(prefix="daniel-keywords-selftest-")

    # ① 正控：仓库内真实合规样本必须判「合规」
    sample = _sample_path()
    if sample is None:
        item("正控：仓库内合规样本", True,
             "跳过（未找到 docs/marketing/kol/2026-09-halliday-g2-kol-search-matrix-v4.md；"
             "剥离分发后属正常）")
    else:
        code, doc, out, err = _run_cli(["keywords", "check", "--file", sample,
                                        "--brand", "3690002", "--json"])
        data = (doc or {}).get("data") or {}
        judged = [r for r in (data.get("判据") or []) if r["结论"] != "未跑"]
        item("正控：合规样本判「合规」（退出码 %d，判据 %d 条全过，违规 %d 条）"
             % (code, len(judged), len(data.get("违规") or [])),
             code == EXIT_OK and data.get("合规") is True and len(judged) == 12,
             "词量 %s 条／类别 %s 个" % ((data.get("规模") or {}).get("合计"),
                                      (data.get("规模") or {}).get("类别数")))
        item("正控：逐条判据都带来源与「是否可机械判」标注",
             bool(judged) and all(r.get("来源") and r.get("可机械化") is True for r in judged))
        item("正控：「需人工判断」项单列（%d 项，每项都写清为什么机器判不了）"
             % len(data.get("需人工判断") or []),
             all(m.get("为什么机器判不了") and m.get("怎么补")
                 for m in (data.get("需人工判断") or []))
             and len(data.get("需人工判断") or []) >= 5)
        item("正控：交付件清单一条词一行（%d 行），每行带「是否合规」与「命中判据」"
             % len(data.get("检索词清单") or []),
             bool(data.get("检索词清单"))
             and all({"序号", "类别", "类型", "检索词", "是否合规", "命中判据"} <= set(r)
                     for r in data["检索词清单"]))

    # ② 正控：三种格式等价（合成最小合规词表：10 类、合计 300 条）
    paths = _write_json_mode_min_fixture(workdir)
    verdicts = {}
    for fmt, path in sorted(paths.items()):
        code, doc, out, err = _run_cli(["keywords", "check", "--file", path, "--json"])
        data = (doc or {}).get("data") or {}
        verdicts[fmt] = (code, data.get("合规"), (data.get("规模") or {}).get("合计"),
                         tuple((r["编号"], r["结论"]) for r in (data.get("判据") or [])))
    same = len(set(verdicts.values())) == 1
    item("正控：md／csv／json 三种格式读同一份词表，结论逐条一致（%s）"
         % "／".join("%s=%s" % (k, v[1]) for k, v in sorted(verdicts.items())), same,
         "".join("%s：退出码 %s、合计 %s 条；" % (k, v[0], v[2]) for k, v in sorted(verdicts.items())))
    item("正控：最小合规词表（10 类、合计 300 条）判「合规」",
         all(v[1] is True and v[0] == EXIT_OK for v in verdicts.values()))

    # ③ 退化正控：故意不合规的样本必须被拦下，且逐条指出违规项
    deg = _degraded_path()
    key = os.path.relpath(deg, _PKG_ROOT)
    code, doc, out, err = _run_cli(["keywords", "check", "--file", deg, "--json"])
    data = (doc or {}).get("data") or {}
    violations = data.get("违规") or []
    kinds = sorted(set(v["违规判据"] for v in violations))
    item("退化正控：默认档有违规时退出码 %d（＝0，结论走 payload 的「合规」字段）" % code,
         code == EXIT_OK and data.get("合规") is False,
         "退出码 %s、合规=%s、违规 %d 条" % (code, data.get("合规"), len(violations)))
    item("退化正控：违规逐条指出（%d 条，覆盖判据 %s）" % (len(violations), "／".join(kinds)),
         len(violations) >= 3 and {"DUP", "NEG"} <= set(kinds)
         and bool({"CAT", "CATQ", "TOTAL"} & set(kinds)),
         "首条：" + (violations[0]["违规说明"] if violations else "无"))
    code2, doc2, out2, err2 = _run_cli(["keywords", "check", "--file", deg, "--strict-exit", "--json"])
    data2 = (doc2 or {}).get("data") or {}
    item("退化正控：--strict-exit 有违规即退出码 %d（期望 %d）且仍逐条给出违规项"
         % (code2, EXIT_USAGE),
         code2 == EXIT_USAGE and data2.get("合规") is False and len(data2.get("违规") or []) >= 3)
    item("退化样本随包分发（%s）且明确标注是自建夹具" % key, os.path.isfile(deg))

    # ④ 反例：文件不存在／判据编号不认识／csv 列数不足 → 用户错误（退出码 2）
    missing = os.path.join(workdir, "not-there.md")
    code3, d3, _o3, err3 = _run_cli(["keywords", "check", "--file", missing, "--json"])
    item("反例：词表文件不存在 → 退出码 %d（期望 %d）" % (code3, EXIT_USAGE), code3 == EXIT_USAGE,
         "理由：" + (((d3 or {}).get("error") or {}).get("message")
                     or (err3.strip().splitlines()[-1] if err3.strip() else "无")))
    code4, d4, _o4, _e4 = _run_cli(["keywords", "check", "--file", paths["json"],
                                    "--only", "NO_SUCH_JUDGE", "--json"])
    item("反例：--only 给了不存在的判据编号 → 退出码 %d（期望 %d）" % (code4, EXIT_USAGE),
         code4 == EXIT_USAGE,
         "理由：" + (((d4 or {}).get("error") or {}).get("message") or "无"))
    bad_csv = os.path.join(workdir, "bad.csv")
    with open(bad_csv, "w", encoding="utf-8") as fh:
        fh.write("类别,类型\n1 品类与形态,Tag\n")
    code5, d5, _o5, _e5 = _run_cli(["keywords", "check", "--file", bad_csv, "--json"])
    item("反例：csv 列数不足 → 退出码 %d（期望 %d）" % (code5, EXIT_USAGE), code5 == EXIT_USAGE,
         "理由：" + (((d5 or {}).get("error") or {}).get("message") or "无"))

    # ⑤ 只读自证：校验路径里没有任何写文件的调用（源码级扫描）
    hits = _source_write_scan()
    item("只读自证：校验路径的源码里没有写文件的调用（自检夹具除外）", not hits,
         "命中：%s" % (hits or "无"))

    passed = sum(1 for i in items if i["通过"])
    summary = {"ok": passed == len(items), "items": len(items), "passed": passed,
               "failed": [i["说明"] for i in items if not i["通过"]],
               "夹具目录（临时，未进仓库）": workdir,
               "说明": "本自检只读词表文件；临时夹具写在系统临时目录里，不写仓库、不写数据落点。"}
    if emitter.json_mode:
        emitter.result(data=summary, ok=summary["ok"],
                       exit_code=EXIT_OK if summary["ok"] else EXIT_INTERNAL)
    else:
        print("自检 %d/%d" % (passed, len(items)), file=emitter.out, flush=True)
        print("结论：%s" % ("全部通过" if summary["ok"] else
                            "未通过 %d 项：%s" % (len(summary["failed"]), "；".join(summary["failed"]))),
              file=emitter.out, flush=True)
    return EXIT_OK if summary["ok"] else EXIT_INTERNAL


HANDLERS = {
    "check": cmd_check,
}

WRITE_HANDLERS = {}

#: 模块自带自检（由 `cli.py` 的模块级钩子分发；**不接进 CLI 总自检**）
SELFTEST = run_selftest
