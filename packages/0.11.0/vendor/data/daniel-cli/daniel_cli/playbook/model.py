# -*- coding: utf-8 -*-
"""工序契约的字段口径（TICKET-146 · P0-3 契约化骨架）。

字段名对齐 `docs/product/daniel-copilot/03-工序契约-screen-run-v0.1（草案）.md`：

    输入 / 前置 / 步骤 / 判据 / 门禁 / 交付件schema / 自检 / 失败模式

（草案 §6 写作「交付件 schema」，契约文件里省掉空格；加载时按别名归一，见 `FIELD_ALIASES`。）

本文件**只描述"契约长什么样"**：字段名、枚举、必填项、退出码映射、报告字段名。
解析在 `loader.py`、校验在 `validate.py`、执行在 `executor.py` —— 各管一段，
避免"格式、校验、执行各写一份口径"。引擎全程只用标准库。
"""

# ─────────────────────────── 契约文件字段 ───────────────────────────
CONTRACT_VERSION = "1.0"

F_VERSION = "契约版本"
F_ID = "id"
F_NAME = "名称"
F_SUMMARY = "说明"
F_INPUTS = "输入"
F_PRECONDITIONS = "前置"
F_STEPS = "步骤"
F_CRITERIA = "判据"
F_GATES = "门禁"
F_DELIVERABLE = "交付件schema"
F_SELFCHECKS = "自检"
F_FAILURE_MODES = "失败模式"
F_LIMITS = "限额"
F_EXPECT = "期望"

#: 票面要求的八项（缺一即validate拒绝）
EIGHT_FIELDS = (F_INPUTS, F_PRECONDITIONS, F_STEPS, F_CRITERIA, F_GATES,
                F_DELIVERABLE, F_SELFCHECKS, F_FAILURE_MODES)
REQUIRED_FIELDS = (F_VERSION, F_ID, F_NAME, F_SUMMARY) + EIGHT_FIELDS
#: `需要联网`（TICKET-153 · 方案 A）：契约自报"这次自证要联网／要有效会话"。
#: 声明了它，`playbook selfcheck` 会先做一次轻量可用性探测；探不通就把这条运行记成
#: 「跳过（需要联网）」——**不是通过、也不是失败**（与门禁的「跳过」同口径），
#: 并在汇总里显式计数（`跳过（需联网）`）。`--require-network`（或环境变量
#: `DANIEL_PLAYBOOK_REQUIRE_NETWORK=1`）能把这种跳过改回**失败**，避免"永远跳过"变成逃逸通道。
F_NEEDS_NETWORK = "需要联网"
OPTIONAL_FIELDS = (F_LIMITS, F_EXPECT, F_NEEDS_NETWORK)
ALL_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS

#: 允许的别名写法（加载时归一成规范字段名）
FIELD_ALIASES = {
    "交付件 schema": F_DELIVERABLE,
    "交付件 Schema": F_DELIVERABLE,
    "交付件": F_DELIVERABLE,
}

# ─────────────────────────── 步骤 ───────────────────────────
S_ID = "id"
S_DESC = "说明"
S_ACTION = "动作"
S_COMMAND = "命令"
S_PARAMS = "参数"
S_OPERATION = "操作"
S_WRITE = "写"
S_READBACK = "回读"
#: 写步骤声明"要写哪个模块"（可选字段：`调用命令` 步骤也能从命令反推，见 `gates.module_of`）。
#: 写链是否开放由**账号对该模块的写权限**决定，所以模块必须能解析出来才判得了。
S_MODULE = "模块"

ACT_CALL = "调用命令"
ACT_FIXTURE = "本地假动作"
STEP_ACTIONS = (ACT_CALL, ACT_FIXTURE)

# ─────────────────────────── 断言 ───────────────────────────
A_TYPE = "类型"
A_VALUE = "取值"
A_EXPECT = "期望"
A_THRESHOLD = "阈值"

#: 取值引用的命名空间前缀（写 `<前缀>.<路径>` 即视为引用；否则按字面量处理）
REF_ROOTS = ("运行", "输入", "变量", "限额", "步骤", "交付件", "契约")

#: 可执行断言表：类型 → 需要的操作数字段
ASSERTION_VOCAB = {
    "等于": (A_VALUE, A_EXPECT),
    "不等于": (A_VALUE, A_EXPECT),
    "大于": (A_VALUE, A_THRESHOLD),
    "大于等于": (A_VALUE, A_THRESHOLD),
    "小于": (A_VALUE, A_THRESHOLD),
    "小于等于": (A_VALUE, A_THRESHOLD),
    "非空": (A_VALUE,),
    "为空": (A_VALUE,),
    "包含": (A_VALUE, A_EXPECT),
    "不包含": (A_VALUE, A_EXPECT),
    "条目数等于": (A_VALUE, A_EXPECT),
    "条目数不超过": (A_VALUE, A_THRESHOLD),
    "存在": (A_VALUE,),
    "不存在": (A_VALUE,),
    "内容一致": (A_VALUE, A_EXPECT),
    "无写发生": (),
    "计数自洽": (),
    "真": (A_VALUE,),
}

# ─────────────────────────── 门禁 ───────────────────────────
G_SAMPLE = "样本上限"
#: 原「禁止真写」升级为「写权限」（TICKET-152 · P0-5）：判据从"写链一律不开放"改成
#: "**当前账号对该模块有没有写权限**"（账号的使用权限，不是审批；本引擎不引入审批流）。
G_WRITE_PERMISSION = "写权限"
G_READONLY = "只读默认"
G_WRITE_CONFIRM = "写步骤确认"
G_READBACK = "回读校验"

#: 引擎内置门禁（契约必须**全部**声明，不允许静默放弃任何一道）
GATE_TYPES = (G_SAMPLE, G_WRITE_PERMISSION, G_READONLY, G_WRITE_CONFIRM, G_READBACK)
MANDATORY_GATE_TYPES = GATE_TYPES

#: 每道门禁拦下运行时用的退出码（只用既有四码，不新增第五个）
GATE_EXIT_CODES = {
    G_SAMPLE: 2,             # 用户输入超限（当前值／上限／建议做法）
    G_WRITE_PERMISSION: 2,   # 账号没有该模块的写权限／写步骤没说模块／拿不到账号权限快照
    G_READONLY: 1,           # 读链出现未声明的写 —— 引擎自身不变量被破坏
    G_WRITE_CONFIRM: 3,      # 需要确认：写步骤未加 --confirm
    G_READBACK: 1,           # 回读校验不通过：写发生了但对不上
}

# ─────────────────── 写权限的账号上下文（契约可声明，离线可跑） ───────────────────
#: 契约 `输入` 里可选的三个账号上下文输入：**有就用**（离线、确定性），
#: 没有就回落到 `permissions.current_auth()`（注入快照／本地缓存／真探测）。
IN_ROLE = "账号角色"          # 例：viewer／pro／admin／super_admin
IN_STATUS = "账号状态"        # 例：active／pending／suspended
IN_FEATURES = "工作区权益"    # 逗号分隔，例：social_intelligence,outreach；空串表示没有额外权益
ACCOUNT_INPUTS = (IN_ROLE, IN_STATUS, IN_FEATURES)

# ─────────────────────────── 期望（退化样本的自证口径） ───────────────────────────
#: 三条可自证的运行路径：默认（什么都不加）／干跑（`--dry-run`）／带确认（`--confirm`）。
#: 三条路径各自声明"期望结果 + 退出码"，`playbook selfcheck` 逐条跑、逐条核对。
E_DEFAULT = "默认"
E_DRY = "干跑"
E_CONFIRMED = "带确认"
EXPECT_PATHS = (E_DEFAULT, E_DRY, E_CONFIRMED)
E_RESULT = "结果"
E_EXIT = "退出码"

R_PASS = "通过"
R_FAIL = "失败"
R_CONFIRM = "需确认"
R_BLOCK = "拦截"
EXPECT_RESULTS = (R_PASS, R_FAIL, R_CONFIRM, R_BLOCK)

# ─────────────────────────── 限额 ───────────────────────────
L_DEFAULT = "默认"
L_HARD = "硬上限"
L_NOTE = "说明"
L_STEPS = "适用步骤"

#: 运行期事实（`运行.*` 引用的字段表，与 validate.RUN_FIELDS 同源）
#: 注：`沙箱保留` 在运行期是**计划值**（`将清理`／`保留`），报告里是**最终值**（`已清理`／`保留`）——
#: 清理发生在运行之后（`executor.run_contract` 的 `finally`），契约断言因此看到的是计划。
RUN_FIELDS = ("样本模式", "全量请求", "确认", "干跑", "沙箱目录", "沙箱保留", "沙箱保留理由",
              "契约目录", "能力目录", "CLI路径", "工作目录", "契约路径", "写动作条数",
              "写权限来源", "交付落点")

#: 条件字段：判据／自检项可以声明"什么情况下适用"，条件不成立即记「跳过」（不是静默通过）
F_WHEN = "当"

# ─────────────────────────── 交付件 schema ───────────────────────────
D_NAME = "名称"
D_FILE = "文件名"
D_SOURCE = "来源步骤"
D_COLUMNS = "列"
D_REQUIRED_COLUMNS = "必填列"
D_ROW_LIMIT = "行数上限引用"

# ───────────────── 出件模板（TICKET-175 · P0 地基③ 交付物工厂）─────────────────
# `交付件schema` 有两代写法，**同一份字段**，不另造机制：
#   · **遗留式**（只声明 名称／文件名／来源步骤／列／必填列）：出 JSON 到本次运行的沙箱，
#     跑完随沙箱清理；行为一个字没变（老契约零回归）。
#   · **模板式**（多声明一个 `格式`）：按模板渲染成 CSV／XLSX／MD，**出件前自动跑五条自检**，
#     过了才落盘到 daniel_paths 解析出的 `$DANIEL_HOME/output/<契约id>/`。
# 判据（票面 C）：自检是**出件的组成部分**（自动跑，不是可选步骤）；不过 → 逐条点出违规行
# ＋ 非零退出 ＋ **落点上不产出文件**。
D_FORMAT = "格式"                  # CSV／XLSX／MD／JSON／PDF；出现即"模板式"
D_SORT = "排序"                    # [{"键": 列名, "方向": 降序/升序}]
D_NULL_TEXT = "无数据写法"          # 无数据时的统一写法（Skill §15.5.5 判据2：不留空）
D_NO_NULL_COLUMNS = "不得占位列"    # 这些列不允许写占位符（防「无官方数据」被当遮羞布）
D_ROW_CRITERIA = "行判据"           # 行的准入判据（逐字取自 Skill，每条带出处）
D_BUCKETS = "关键桶"                # 关键桶非 0（票面 C⑤）
D_RECONCILE = "计数对账"            # 主表行数 == 文件行数；入池 ≥ 出件且差额可解释
D_SOURCES = "判据出处"              # 判据 → Skill 章节＋行号（便于回查）
D_EXTRA = "附表"                    # 说明与口径表（Skill §15.5.5 判据1：子表清单）

#: 出件格式（渲染器全部只用标准库；XLSX 用 zipfile ＋ 最小 SpreadsheetML，零第三方依赖。
#: **PDF** ＝ 印刷级出件（TICKET-186 · A4）：渲染交给既有工序脚本 `.kol-tools/doc_to_pdf.py`
#: —— 语义块 → 打印级 HTML → Chromium 出件，**本仓不另造渲染器**。PDF 是**文档型**出件：
#: 除 PDF 本身外同时落一份 `.md` 作"可复制版"，并多跑判据（A4 页面／叠字 0／md↔PDF 三条内容判据：
#: 字符多重集逐类相等 ＋ 逐行点名 ＋ 逐格点名 ——「去空白逐字按序相等」只作事实、不判违规）。
FORMATS = ("CSV", "XLSX", "MD", "JSON", "PDF")
SORT_DESC = "降序"
SORT_ASC = "升序"
SORT_DIRECTIONS = (SORT_DESC, SORT_ASC)

#: 列声明的三种"来源"（票面 A：列名／来源／必填或可空／无数据时的写法）
SRC_FIELD = "字段"      # 取产出里某个键（真实接口的字段名）
SRC_COMPUTE = "计算"    # 由同行其它列算出来（表达式只允许 + - * / 与列名）
SRC_TEMPLATE = "模板"   # 由同行其它列拼出来（`${列名}` 插值，做链接一类）
SRC_GENERATE = "生成"   # 引擎生成：排名／点名位置
GEN_RANK = "排名"
GEN_MENTION = "点名位置"
COL_KEYS = ("列名", "来源", "必填", "无数据写法", "出处", "格式")

#: 行判据的关系（引擎通用；判据条文本身逐字取自 Skill，出处逐条登记）
REL_EQ = "等于"
REL_NE = "不等于"
REL_GT = "大于"
REL_GE = "大于等于"
REL_LT = "小于"
REL_LE = "小于等于"
REL_NOT_NULL = "非空"
REL_NOT_PLACEHOLDER = "非占位"
REL_IN = "含任一"
REL_NOT_IN = "不含任一"
#: 点名至品牌（Skill §15.5.4 规则1／规则2）：标题/话题标签含品牌或产品名 → 或频道名含品牌 →
#: 或判定依据里**正面**点名；解析判定依据前先剔除否定句（否定句是负证据）。
REL_MENTION = "点名至品牌"
#: 唯一读数（Skill §15.5.4 规则3）：同一视频只保留读数最高的那一条记录。
REL_DEDUP = "按视频去重取最高"
ROW_RELATIONS = (REL_EQ, REL_NE, REL_GT, REL_GE, REL_LT, REL_LE, REL_NOT_NULL,
                 REL_NOT_PLACEHOLDER, REL_IN, REL_NOT_IN, REL_MENTION, REL_DEDUP)
#: 需要 `阈值`；需要 `词表`；需要 `取最大`
RELATION_NEEDS_THRESHOLD = (REL_EQ, REL_NE, REL_GT, REL_GE, REL_LT, REL_LE, REL_IN, REL_NOT_IN)
RELATION_NEEDS_WORDS = (REL_MENTION,)

CRC_ID = "id"
CRC_DESC = "说明"
CRC_FIELD = "字段"
CRC_RELATION = "关系"
CRC_THRESHOLD = "阈值"
CRC_WORDS = "品牌词"
CRC_NEGATIVE = "否定词"
CRC_HINT_FIELDS = "旁证列"          # 点名的另外两条证据路径（标题／频道名）
CRC_MAX = "取最大"
CRC_SOURCE = "出处"
CRC_LEFT = "左"
CRC_RIGHT = "右"
CRC_DELTA = "差额说明"
CRC_VALUE = "取值"
CRC_FLOOR = "下限"
CRC_BUCKET = "名称"

#: `运行.*` 里的出件落点覆盖（`playbook deliver --out`）——落点由**调用方**决定，
#: 未指定时默认值走 daniel_paths（落点规范 TICKET-154 §一.3）。
O_DELIVER_OUT = "交付落点"

# ─────────────────────────── 运行期状态 ───────────────────────────
ST_PASS = "通过"
ST_FAIL = "失败"
ST_SKIP = "跳过"

#: 引擎自证（`playbook selfcheck`）里"因需联网而跳过"的状态名与摘要栏名（TICKET-153 · 方案 A）。
#: 与门禁的「跳过」同口径：**跳过 ≠ 通过，跳过 ≠ 失败**，报告里必须是两种状态、不许混为一谈。
SC_SKIP_ONLINE = "跳过（需要联网）"
SC_SKIP_COLUMN = "跳过（需联网）"

#: 计数自洽的字段名（声明项数 ＝ 实跑项数 ＝ 通过＋失败＋跳过）
C_DECLARED = "声明项数"
C_RUN = "实跑项数"
C_PASS = "通过"
C_FAIL = "失败"
C_SKIP = "跳过"
C_SELF = "自洽"


def counts(declared, evaluated):
    """计数自洽（对齐 CLS-67 的四口径一致）：声明项数 ＝ 实跑项数 ＝ 通过＋失败＋跳过。"""
    passed = sum(1 for e in evaluated if e.get("状态") == ST_PASS)
    failed = sum(1 for e in evaluated if e.get("状态") == ST_FAIL)
    skipped = sum(1 for e in evaluated if e.get("状态") == ST_SKIP)
    n_declared, n_run = len(declared), len(evaluated)
    return {
        C_DECLARED: n_declared,
        C_RUN: n_run,
        C_PASS: passed,
        C_FAIL: failed,
        C_SKIP: skipped,
        C_SELF: n_declared == n_run == passed + failed + skipped,
    }


def merge_counts(groups):
    """把多组计数合成一份总账（自洽＝每组都自洽）。"""
    total = {C_DECLARED: 0, C_RUN: 0, C_PASS: 0, C_FAIL: 0, C_SKIP: 0}
    for name, c in groups.items():
        for k in total:
            total[k] += int(c.get(k, 0))
    total[C_SELF] = all(bool(c.get(C_SELF)) for c in groups.values()) if groups else True
    return total


def normalize(raw):
    """把契约字典的别名键归一成规范字段名；返回 `(规范化副本, 用到的别名列表)`。"""
    out, used = {}, []
    for k, v in dict(raw or {}).items():
        if k in FIELD_ALIASES:
            canon = FIELD_ALIASES[k]
            used.append("%s → %s" % (k, canon))
            out[canon] = v
        else:
            out[k] = v
    return out, used


def limit_rows(contract):
    """把 `限额` 声明整理成 `{名称: {默认, 硬上限, 说明, 适用步骤}}`（缺省值补全）。"""
    rows = {}
    for name, spec in (contract.get(F_LIMITS) or {}).items():
        spec = spec if isinstance(spec, dict) else {L_DEFAULT: spec}
        rows[name] = {
            L_DEFAULT: spec.get(L_DEFAULT),
            L_HARD: spec.get(L_HARD, spec.get(L_DEFAULT)),
            L_NOTE: spec.get(L_NOTE) or "",
            L_STEPS: spec.get(L_STEPS),
        }
    return rows


def write_steps(contract):
    """契约里声明为写的步骤（读链默认零写：这些步骤必须走三段门禁）。"""
    return [s for s in (contract.get(F_STEPS) or []) if bool((s or {}).get(S_WRITE))]
