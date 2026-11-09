# -*- coding: utf-8 -*-
"""调度层的**判据常量**：终态四态、退避策略、HTTP 状态分类、受管触发类命令（TICKET-181）。

本文件只描述"什么叫成功／失败／超时／配额耗尽"与"重试怎么退避"，不做 IO、不落盘、不联网 ——
IO 在 `store.py`，执行在 `runner.py`。这样"判据"只有一份，命令层与自检都从这一份取。

终态四态（**不许把"未完成"当"完成"**）
--------------------------------------
成功 ｜ 失败 ｜ 超时 ｜ 配额耗尽 —— 四个词就是四个终态，任何一步结束后必须落在这四个里；
"进行中／排队中／待执行"是**非终态**，它们**不等于成功**（报告里也从不写成成功）。
判定顺序是"先分类、再定终态"：可重试类失败在次数／时限未用尽前**不是**终态。

退避（429／5xx）
----------------
指数退避 ＋ 上限 ＋ 抖动：`delay(n) = min(上限, 基数 × 倍数^(n-1))`，再乘 `1 ± 抖动比例` 的随机因子。
三条纪律：
  · **抖动不可关**（除非显式设 `DANIEL_SCHED_JITTER=0`）：并发任务同时被限流时，同步重试会把
    限流打成脉冲；
  · **每一次重试都要有可见进度**（`runner` 往 stderr 打一行"第 n 次尝试／原因／退避多少秒"），
    不允许静默重试到超时；
  · **上限与时限同时生效**：次数用完 → 按最后一次原因定终态；时限用完 → 终态是**超时**（不是失败，
    也不是成功）。
"""
import os
import random

# ─────────────────────────── 终态四态 ───────────────────────────
ST_SUCCESS = "成功"
ST_FAIL = "失败"
ST_TIMEOUT = "超时"
ST_QUOTA = "配额耗尽"
TERMINAL_STATES = (ST_SUCCESS, ST_FAIL, ST_TIMEOUT, ST_QUOTA)

# 非终态（**都不是成功**；报告与状态文件里如实区分）
ST_PENDING = "待执行"
ST_INTERRUPTED = "中断"
ST_SKIPPED_DONE = "跳过（已完成）"

#: 任务状态用词：终态四态 ＋ `进行中`
TASK_RUNNING = "进行中"
TASK_STATES = (TASK_RUNNING,) + TERMINAL_STATES

#: 队列条目状态
Q_WAITING = "排队中"
Q_RUNNING = "运行中"
Q_DONE = "已完成"
Q_INTERRUPTED = "中断（进程已不存在）"

# ─────────────────────────── HTTP 状态分类 ───────────────────────────
#: 可重试：429（限流／配额）与 5xx（服务端）。其余 4xx 是"这次请求本身不对"，重试无意义。
RETRYABLE_STATUS = (429, 500, 502, 503, 504)
QUOTA_STATUS = 429
SERVER_ERROR_STATUS = (500, 502, 503, 504)

#: 命令步骤的**文本分类标记**：既有仪器／CLI 把服务端状态写在 stderr 或输出里时用它判"可重试"。
#: 只在"退出码非 0 且输出里出现这些标记"时判可重试；判不出来一律按**失败**（宁可少重试，
#: 不可把"重复执行一个不明原因失败的写动作"当成常规操作 —— 本层只跑只读命令，但口径照旧从严）。
RETRYABLE_MARKERS = ("429", "rate limit", "rateLimit", "Too Many Requests",
                     "500", "502", "503", "504", "Internal Server Error",
                     "Bad Gateway", "Service Unavailable", "Gateway Timeout")


def classify_http(status):
    """HTTP 状态码 → `(是否可重试, 次数用尽时的终态, 人话原因)`。"""
    if 200 <= status < 300:
        return False, ST_SUCCESS, "HTTP %d" % status
    if status == QUOTA_STATUS:
        return True, ST_QUOTA, "HTTP 429（限流／配额已耗尽）"
    if status in SERVER_ERROR_STATUS:
        return True, ST_FAIL, "HTTP %d（服务端错误）" % status
    return False, ST_FAIL, "HTTP %d（请求本身不被接受，重试无意义）" % status


def terminal_for_last_failure(kind):
    """最后一次尝试的失败类别 → 终态（次数／时限用尽时调用）。

    `kind` ∈ `quota`／`timeout`／`fail`／`network`。**不许因为"试了很多次"就把失败说成成功。**

    用词要准（说错终态会把排查方向引偏）：
      · `quota`   → **配额耗尽**（429：限流／额度用尽，再重试也是这个结论）；
      · `timeout` → **超时**（单次请求超时，或退避所需时间超过单步时限）；
      · `network` → **失败**（连接被拒／解析不了主机名 —— 这是"打不通"，不是"超时"）；
      · `fail`    → **失败**（4xx／5xx 用尽重试，或不可重试的确定性失败）。
    """
    if kind == "quota":
        return ST_QUOTA
    if kind == "timeout":
        return ST_TIMEOUT
    return ST_FAIL


# ─────────────────────────── 退避策略 ───────────────────────────
class Backoff:
    """指数退避＋上限＋抖动的**唯一**实现（任务级可覆盖，命令行可再覆盖）。"""

    def __init__(self, base=1.0, factor=2.0, cap=30.0, jitter=0.3, attempts=4,
                 step_timeout=30.0, deadline=120.0):
        self.base = float(base)
        self.factor = float(factor)
        self.cap = float(cap)
        self.jitter = max(0.0, min(1.0, float(jitter)))
        self.attempts = max(1, int(attempts))
        self.step_timeout = float(step_timeout)
        self.deadline = float(deadline)
        self._rng = random.Random(_seed())

    def delay(self, attempt):
        """第 `attempt` 次尝试**失败后**该等多久（秒）。`attempt` 从 1 起。"""
        raw = min(self.cap, self.base * (self.factor ** max(0, attempt - 1)))
        if self.jitter <= 0:
            return round(raw, 3)
        lo = raw * (1.0 - self.jitter)
        hi = raw * (1.0 + self.jitter)
        return round(self._rng.uniform(lo, hi), 3)

    def as_dict(self):
        return {"基数秒": self.base, "倍数": self.factor, "上限秒": self.cap,
                "抖动比例": self.jitter, "最多尝试次数": self.attempts,
                "单步超时秒": self.step_timeout, "总时限秒": self.deadline}


def _seed():
    """抖动随机源：`DANIEL_SCHED_SEED` 给了就确定性（便于复跑取证），否则用系统熵。"""
    raw = os.environ.get("DANIEL_SCHED_SEED")
    if raw not in (None, ""):
        try:
            return int(raw)
        except ValueError:
            return abs(hash(raw)) % (2 ** 31)
    return random.SystemRandom().randrange(2 ** 31)


#: 任务规格里可覆盖的策略字段（`限额` 段）→ `Backoff` 构造参数
LIMIT_KEYS = {
    "重试次数": "attempts", "退避基数秒": "base", "退避倍数": "factor",
    "退避上限秒": "cap", "抖动比例": "jitter", "单步超时秒": "step_timeout",
    "总时限秒": "deadline",
}


def backoff_from_limits(limits=None, overrides=None):
    """任务规格的 `限额` ＋ 命令行覆盖 → `Backoff`（不认识的键**报错**，不静默忽略）。"""
    kwargs = {}
    for src in (limits or {}, overrides or {}):
        for k, v in src.items():
            if k not in LIMIT_KEYS:
                raise KeyError(k)
            kwargs[LIMIT_KEYS[k]] = v
    return Backoff(**kwargs)


# ─────────────────────────── 队列：受管触发类命令 ───────────────────────────
#: 并发上限的配置键（默认**保守**：一次只跑一条）
CONCURRENCY_ENV = "DANIEL_SCHED_CONCURRENCY"
CONCURRENCY_DEFAULT = 1

#: 远端取数的显式开关（默认**只允许回环地址**：本票正控一律用假端点／夹具）
ALLOW_REMOTE_ENV = "DANIEL_SCHED_ALLOW_REMOTE"

#: 受管触发类命令（票面点名的四条：会触发采集／检索的那四条写命令）。
#: TICKET-188（A1）起它们**真实执行已接通**（`writeStage=live`），并**一律经这条统一队列**：
#: 执行前先拿并发位（`DANIEL_SCHED_CONCURRENCY`，默认 1），执行中命中 429／5xx 按 `Backoff`
#: 指数退避，结束时把终态（成功／失败／超时／配额耗尽）写进队列记录。
MANAGED_TRIGGER_COMMANDS = (
    ("search", "submit", "提交一条新的红人检索任务（会触发检索）"),
    ("mentions", "run", "发起一次品牌提及分析（会触发采集）"),
    ("sov", "run-exposure", "发起一次曝光采集（会触发采集）"),
    ("route", "sweep", "全量扫描通路（逐条发包探测；只读 GET）"),
    ("ct", "create-campaign", "新建合作活动（写业务对象）"),
    ("takeover", "check-writes", "含写链的接管验收（自检工序）"),
)


def concurrency_limit(explicit=None):
    """并发上限：命令行 → `DANIEL_SCHED_CONCURRENCY` → 默认（1，保守）。返回 `(上限, 来源)`。"""
    if explicit not in (None, ""):
        return max(1, int(explicit)), "命令行（--concurrency）"
    raw = os.environ.get(CONCURRENCY_ENV)
    if raw not in (None, ""):
        try:
            return max(1, int(raw)), "环境变量 %s" % CONCURRENCY_ENV
        except ValueError:
            return CONCURRENCY_DEFAULT, "环境变量 %s 取值非法（%r），已回退默认" % (CONCURRENCY_ENV, raw)
    return CONCURRENCY_DEFAULT, "默认（保守：一次只跑一条）"


def remote_allowed():
    return os.environ.get(ALLOW_REMOTE_ENV) == "1"


def managed_trigger_rows():
    """受管触发类命令的**人读行**（`sched queue` 直接打印；真源就是上面那张表）。"""
    return [{"模块": m, "命令": c, "说明": d, "排队口径": "统一队列准入（并发上限 × 退避策略）"}
            for m, c, d in MANAGED_TRIGGER_COMMANDS]


def trigger_selfcheck():
    """受管清单 ↔ `schema.py` 单一真源的自证（**不猜、不写第二份**）。

    判据三条：
      ① 每条受管命令都在单一真源里声明，且声明为**写操作**；
      ② 每条受管命令的真实执行**必须是接通的**（`writeStage == "live"`）——
         TICKET-188（A1）之前这里的判据是"必须是 gated"（当时真实执行还未接通）；
         接通之后判据随之翻面：**仍停在 gated 的受管命令 = 名不副实**，逐条列出；
      ③ 真源里全部写命令中**未纳入**受管清单的，逐条给出理由（不静默漏）。
    返回 `{"一致": bool, "受管": [...], "未接通": [...], "未纳入": [...], "问题": [...]}`。
    """
    try:
        from ..schema import SCHEMA
    except Exception as e:                                    # noqa: BLE001（并发改动可能暂不可导入）
        return {"一致": False, "受管": [], "未接通": [], "未纳入": [], "问题": ["schema 不可导入：%s" % e]}
    declared = {}
    for mod in SCHEMA["modules"]:
        for cmd in mod["commands"]:
            if cmd["write"]:
                declared[(mod["key"], cmd["name"])] = cmd.get("writeStage")
    problems, managed, not_live = [], [], []
    for m, c, _d in MANAGED_TRIGGER_COMMANDS:
        stage = declared.get((m, c))
        if stage is None:
            problems.append("%s %s：真源里没有声明这条写命令" % (m, c))
        elif stage != "live":
            problems.append("%s %s：受管前提是真实执行已接通（writeStage=live），实际 %s"
                            % (m, c, stage))
            not_live.append("%s %s（%s）" % (m, c, stage))
        managed.append("%s %s" % (m, c))
    # 未纳入：真源里**不是沙箱**的其它写命令（沙箱写不碰远端，本就不需要排队）
    left = ["%s %s" % (k[0], k[1]) for k, v in sorted(declared.items())
            if v != "sandbox" and ("%s %s" % (k[0], k[1])) not in managed]
    why = {
        "ct create-campaign": "新建合作活动是业务写，不触发采集／检索（但它有逆操作 ct delete-campaign 可回滚）",
        "ct delete-campaign": "删除合作活动是业务写，用途是回滚建错的测试活动",
        "takeover check-writes": "含写链的接管验收是自检工序，不是采集触发（写链自带用后即删）",
        "brands create": "品牌档案是业务写，不触发采集／检索",
        "brands update": "品牌档案是业务写，不触发采集／检索",
        "brands delete": "品牌档案是业务写，不触发采集／检索",
        "lists create": "红人名单是业务写，不触发采集／检索",
        "lists rename": "红人名单是业务写，不触发采集／检索",
        "lists delete": "红人名单是业务写，不触发采集／检索",
        "account credentials-set": "本机凭据写入，不触达远端采集",
        "account switch": "本机数据分区切换，不触达远端采集",
        "account login": "登录并落本机会话，不触发采集",
    }
    return {"一致": not problems and not not_live, "受管": managed, "未接通": not_live,
            "未纳入": [{"命令": k, "理由": why.get(k, "未纳入（待判定）")} for k in left],
            "问题": problems}
