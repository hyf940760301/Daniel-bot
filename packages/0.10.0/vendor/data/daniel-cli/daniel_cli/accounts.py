# -*- coding: utf-8 -*-
"""多账号：**分区规则的单一真源**（TICKET-186 · A2）。

一句话：**单 home ＋ 凭据按账号分条 ＋ 数据按账号分区**。
本文件是"某个账号的数据落在哪个目录"这个问题的**唯一**答案 —— 任何地方要算分区，
都调 `partition_home()`，不许在别处再写一遍拼接逻辑。

口径（用户 2026-10-02／2026-10-14 裁决 ＋ TICKET-186）
------------------------------------------------------
· **单 home**：仍然只有一个数据落点根（`DANIEL_BASE_HOME`，默认＝`daniel_paths.home()`），
  不引入"多 home 管理界面"。分区是这**一个根之下的子目录**。
· **分区**：`<根>/accounts/<分区名>/`；分区名由邮箱确定性派生（`slug()`，本地部分 ＋ 邮箱摘要
  前 8 位），既能人眼认出是哪个账号、又不会把两个账号撞到同一个目录。
· **未指定账号时不分**：没有当前账号指针时，落点**就是根目录本身** —— 出厂状态与既有安装
  一个字都不变（既有会话／缓存／产出原地不动，不做迁移、不做搬运）。
· **凭据按账号分条**：钥匙串条目本来就按账号分条（`-s daniel-copilot -a <邮箱>`，见
  `.kol-tools/daniel_credentials.py`）。本文件只负责把**当前账号**钉给凭据层
  （`DANIEL_KEYCHAIN_ACCOUNT`），从而"切回免重输"；**不写、不改、不删任何凭据**。

怎么让既有仪器也跟着分区（**零改动**）
--------------------------------------
`daniel_paths.home()` 的第一优先就是环境变量 `DANIEL_HOME`。所以 `apply_environment()`
把 `<根>/accounts/<分区>` 写进本进程的 `DANIEL_HOME`，**既有仪器（会话／缓存／调度／出件）
天然写进分区**，`.kol-tools/**` 一行都不用改；子进程（`subprocess` 不带 `env=`）自动继承。

落点来源说明（`home_reason` 一类）
---------------------------------
`partition_facts()` 同时给出：**根在哪、根是怎么选出来的、当前分区在哪、凭据钉在哪个账号**。
根的理由沿用 `daniel_paths.home_reason()` 的原话（`default-macos`／`unwritable-app-support`／
`fallback-workspace`…），分区再叠一层 `partition:<分区名>` —— 让"数据到底落在哪、为什么落这"
在 `daniel account paths` 里一眼可见，不用翻代码。

边界（本文件不做的事）
----------------------
· 不碰凭据值：只传账号名，不读密码，不回显任何凭据；
· 不删改任何既有数据：切账号只写一个指针文件 ＋ 建目录，**不动任何既有文件**；
· 不联网：全部是本地文件操作，命令可以离线跑。
"""
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import time

#: 数据落点根（分区前的那个"单 home"）。由 `apply_environment()` 注入，供子进程复用。
BASE_ENV = "DANIEL_BASE_HOME"
#: 分区目录名（在根之下的一级目录）
PARTITIONS_SUBDIR = "accounts"
#: 账号状态文件（当前账号指针 ＋ 已存账号注册表）；下划线开头，与分区名不会撞
STATE_NAME = "_state.json"
SCHEMA = "daniel.accounts.v1"

_UNSET = object()

#: 落点根"为什么选在这里"的人话（键是统一落点解析层给出的原因码）。
#: 为什么要这一份：`unwritable-app-support` 这类原因码对用户是黑话，
#: 而"数据落在哪、为什么"必须让人看懂（用户视角三问第一问）。
REASON_WORDS = {
    "env:DANIEL_HOME": "你自己用环境变量指定了数据落点，就按你指定的位置放。",
    "default-macos": "按系统惯例放在你的「应用支持」目录里（macOS 默认位置）。",
    "unwritable-app-support": "首选位置（系统的应用支持目录）存在但当前不可写，"
                              "于是自动退回到本项目目录下的数据目录。",
    "uncreatable-app-support": "首选位置（系统的应用支持目录）建不出来，"
                               "于是自动退回到本项目目录下的数据目录。",
    "unwritable-candidate": "候选位置存在但不可写，于是换到了能写的位置。",
    "uncreatable-candidate": "候选位置建不出来，于是换到了能建的位置。",
    "fallback-workspace": "系统默认位置不可用，于是退回到本项目目录下的数据目录。",
    "fallback-unwritable": "系统默认位置与本项目目录都不可写，落点可能写不进去，请检查权限。",
}


# ─────────────────────────── 落点根（单 home） ───────────────────────────
def _dpaths():
    """惰性取落点解析层（**不在模块级解析落点**：加 `DANIEL_HOME` 注入后必须每次现算）。"""
    from .runtime import load_capability
    return load_capability("daniel_paths")


def base_home():
    """数据落点**根**（分区之前的那个目录）。

    解析顺序：`DANIEL_BASE_HOME`（本层注入的）→ 已分区形态的 `DANIEL_HOME` 反推回根
    → 用户给的 `DANIEL_HOME`（当作根）→ `daniel_paths.home()`（系统默认／工作区降级）。
    **不做模块级缓存**：同一进程里注入前后必须是两个不同的值。
    """
    env_base = os.environ.get(BASE_ENV)
    if env_base:
        return os.path.abspath(os.path.expanduser(env_base))
    env_home = os.environ.get("DANIEL_HOME")
    if env_home:
        p = os.path.abspath(os.path.expanduser(env_home))
        if os.path.basename(os.path.dirname(p)) == PARTITIONS_SUBDIR:
            return os.path.dirname(os.path.dirname(p))
        return p
    return _dpaths().home()


def base_home_reason():
    """根是怎么选出来的（**未分区视角**的原话）。

    为什么要把 `DANIEL_HOME` 暂时摘掉再问：一旦注入生效，`daniel_paths.home_reason()` 会回答
    `env:DANIEL_HOME`（那是"我注入的分区"，不是"根怎么选出来的"）。这里只临时摘掉再放回，
    不改变进程最终的环境。
    """
    saved_home = os.environ.pop("DANIEL_HOME", None)
    saved_base = os.environ.pop(BASE_ENV, None)
    try:
        dpaths = _dpaths()
        dpaths._home_cache, dpaths._home_reason = None, None      # 清掉它自己的进程内缓存
        return dpaths.home_reason()
    finally:
        if saved_base is not None:
            os.environ[BASE_ENV] = saved_base
        if saved_home is not None:
            os.environ["DANIEL_HOME"] = saved_home


# ─────────────────────────── 分区规则（单一真源） ───────────────────────────
def slug(account):
    """账号 → 分区目录名（确定性、可比对、不撞车）。

    `<本地部分摘要>-<邮箱 sha256 前 8 位>`：本地部分让人一眼认出是谁，摘要保证
    "同一本地部分、不同域名"以及各种奇怪字符都不会撞到同一个目录。
    结果只含 `[a-z0-9.-]`，因此永远是合法目录名。
    """
    email = str(account or "").strip().lower()
    local = email.split("@", 1)[0]
    local = re.sub(r"[^a-z0-9]+", ".", local).strip(".")[:32] or "account"
    return "%s-%s" % (local, hashlib.sha256(email.encode("utf-8")).hexdigest()[:8])


def partitions_dir():
    return os.path.join(base_home(), PARTITIONS_SUBDIR)


def partition_home(account):
    """**分区规则的单一真源**：账号 → 该账号的数据落点。

    · `account` 为空（None／空串）⇒ **根目录本身**（未指定账号＝兼容区，既有数据原地不动）；
    · 否则 ⇒ `<根>/accounts/<slug(账号)>`（永远落在 `DANIEL_HOME` 之下，绝不落代码目录）。
    """
    acct = str(account or "").strip()
    if not acct:
        return base_home()
    return os.path.join(base_home(), PARTITIONS_SUBDIR, slug(acct))


def state_path():
    return os.path.join(partitions_dir(), STATE_NAME)


# ─────────────────────────── 状态文件（指针 ＋ 注册表） ───────────────────────────
def _empty_state():
    return {"schema": SCHEMA, "active": None, "accounts": []}


def read_state():
    """读账号状态。文件不存在／不合法 ⇒ 空状态（**不报错**：出厂状态就是合法的）。"""
    path = state_path()
    if not os.path.exists(path):
        return _empty_state()
    try:
        with io.open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return _empty_state()
    if not isinstance(doc, dict):
        return _empty_state()
    doc.setdefault("schema", SCHEMA)
    doc.setdefault("active", None)
    rows = doc.get("accounts")
    doc["accounts"] = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    return doc


def write_state(state):
    """原子写（临时文件 → `os.replace`），权限 600；父目录尽力建。**只落 `DANIEL_HOME` 之下**。"""
    path = state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)
    return path


def active_account():
    """当前账号（邮箱原文，供凭据层钉账号用）；未指定 ⇒ None。"""
    acct = read_state().get("active")
    return str(acct).strip() or None if acct else None


def accounts():
    """已存账号注册表（原样，不改写）。"""
    return list(read_state().get("accounts") or [])


def register_account(account, note=None):
    """把一个账号登记进注册表（**只新增／只更新这一行，绝不删改别人的行**）。

    返回 `(注册表, 该行是否是新增)`。
    """
    acct = str(account or "").strip()
    if not acct:
        raise ValueError("账号不能为空")
    state = read_state()
    rows = state["accounts"]
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    hit = None
    for r in rows:
        if str(r.get("email") or "").strip().lower() == acct.lower():
            hit = r
            break
    fresh = hit is None
    if fresh:
        hit = {"email": acct, "partition": slug(acct), "firstSeen": now}
        rows.append(hit)
    hit["lastUsed"] = now
    if note:
        hit["note"] = note
    if not state.get("active"):
        state["active"] = acct
    write_state(state)
    return rows, fresh


# ─────────────────────────── 凭据：只看"条目在不在" ───────────────────────────
def _mask(email):
    from .runtime import load_capability
    return load_capability("daniel_credentials").mask_email(email)


def keychain_service():
    creds = _credentials_module()
    return creds.keychain_service()


def _credentials_module():
    from .runtime import load_capability
    return load_capability("daniel_credentials")


def keychain_has(account):
    """该账号在钥匙串里**有没有条目**。

    🔴 **不带 `-w`**：只让 `security` 回报"找到／没找到"与条目属性，**绝不把密码读出来**。
    找不到／没有钥匙串 ⇒ False（调用方据此报用户错误，不去猜）。
    """
    acct = str(account or "").strip()
    if not acct:
        return False
    creds = _credentials_module()
    rc, _out, _err = creds._security(["find-generic-password", "-s", creds.keychain_service(),
                                      "-a", acct])
    return rc == 0


# ─────────────────────────── 环境注入（让既有仪器跟着分区） ───────────────────────────
def apply_environment(account=_UNSET):
    """把"当前账号的分区"注入本进程环境；返回落点事实。

    · `DANIEL_BASE_HOME` 一律设成根（子进程据此仍能算回根）；
    · 有当前账号 ⇒ `DANIEL_HOME=<根>/accounts/<分区>` ＋ `DANIEL_KEYCHAIN_ACCOUNT=<账号>`
      （凭据读取被钉到该账号 ⇒ 切回免重输）；
    · 没有当前账号 ⇒ **不动 `DANIEL_HOME`**（保持出厂／用户自设语义），也不钉凭据账号。
    """
    acct = active_account() if account is _UNSET else (str(account).strip() or None if account else None)
    os.environ[BASE_ENV] = base_home()
    if acct:
        os.environ["DANIEL_HOME"] = partition_home(acct)
        os.environ["DANIEL_KEYCHAIN_ACCOUNT"] = acct
    return partition_facts(acct)


def partition_facts(account=_UNSET):
    """落点事实（给 `account paths`／`account list`／`account switch` 共用同一份口径）。"""
    acct = active_account() if account is _UNSET else (str(account).strip() or None if account else None)
    base = base_home()
    part = partition_home(acct) if acct else None
    reason = base_home_reason()
    plan = {
        "schema": SCHEMA,
        "数据落点根": base,
        "根的选择理由": reason,
        "根的选择理由(人话)": REASON_WORDS.get(
            reason, "落点根由本机环境决定（取自统一落点解析层的结果）"),
        "分区规则": "账号 → <根>/%s/<本地部分>-<邮箱摘要8位>（单一真源 daniel_cli/accounts.py::partition_home）"
                    % PARTITIONS_SUBDIR,
        "分区目录": partition_home("<账号>") if not acct else part,
        "当前账号(掩码)": _mask(acct) if acct else None,
        "当前账号分区": part,
        "是否已分区": bool(acct),
        "生效落点": part or base,
        "落点来源": ("partition:%s" % slug(acct)) if acct else "base（未指定账号，使用根目录）",
        "凭据账号钉在哪": acct,
        "账号状态文件": state_path(),
    }
    return plan


# ─────────────────────────── 视图（list / switch 共用） ───────────────────────────
def list_accounts():
    """已存账号一览：注册表 ＋ **钥匙串条目是否还在**（现场核，不看缓存）。"""
    state = read_state()
    active = state.get("active")
    rows = []
    for r in state.get("accounts") or []:
        email = str(r.get("email") or "").strip()
        if not email:
            continue
        rows.append({
            "邮箱(掩码)": _mask(email),
            "分区目录": r.get("partition") or slug(email),
            "分区落点": partition_home(email),
            "是否当前": bool(active) and email.lower() == str(active).lower(),
            "钥匙串条目": "有" if keychain_has(email) else "无",
            "最近使用": r.get("lastUsed"),
            "首次登记": r.get("firstSeen"),
        })
    return {
        "数据落点根": base_home(),
        "分区规则": "账号 → <根>/%s/<本地部分>-<邮箱摘要8位>；未指定账号时落根目录本身"
                    % PARTITIONS_SUBDIR,
        "当前账号(掩码)": _mask(active) if active else None,
        "当前账号分区": partition_home(active) if active else None,
        "已存账号数": len(rows),
        "已存账号": rows,
        "账号状态文件": state_path(),
        "钥匙串服务名": keychain_service(),
    }


def ensure_partition(account):
    """建好该账号的分区目录（幂等）。**只建目录，不动任何既有文件**。"""
    home = partition_home(account)
    created = []
    for sub in ("session", "cache", "output", "logs", "sched"):
        path = os.path.join(home, sub)
        if not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)
            created.append(path)
    return home, created


def partition_summary(account):
    """分区里现在有什么（切换前后对账用：**证明没动过别的账号的东西**）。"""
    home = partition_home(account)
    facts = {"落点": home, "存在": os.path.isdir(home), "子目录": {}, "文件数": 0}
    if not facts["存在"]:
        return facts
    for name in sorted(os.listdir(home)):
        p = os.path.join(home, name)
        if os.path.isdir(p):
            n = sum(len(f) for _r, _d, f in os.walk(p))
            facts["子目录"][name] = n
            facts["文件数"] += n
        else:
            facts["文件数"] += 1
    return facts


def switch(account, register=True):
    """切到某个账号：登记（只加自己那一行）→ 建分区目录 → 写指针 → 回读。

    返回 `{before, after, created, previous}`；**不写任何凭据、不删改任何既有数据**。
    """
    acct = str(account or "").strip()
    if not acct:
        raise ValueError("账号不能为空")
    before = partition_facts()
    previous = active_account()
    created = []
    if register:
        register_account(acct)
    _home, created = ensure_partition(acct)
    state = read_state()
    state["active"] = acct
    write_state(state)
    after = partition_facts(acct)
    return {"before": before, "after": after, "created": created,
            "previous": previous, "previousPartition": partition_home(previous) if previous else None}


def clear_active():
    """取消当前账号（回到"未指定账号"＝根目录）。**不删任何文件**。"""
    before = partition_facts()
    state = read_state()
    state["active"] = None
    write_state(state)
    return {"before": before, "after": partition_facts(None)}


# ─────────────────────────── 自检（只读 ＋ 纯函数） ───────────────────────────
def self_check():
    """模块级自检：分区规则的确定性、可逆、不越界；全部是纯函数与临时目录，**不碰真实数据**。

    返回 `(全部通过, [(判据, 是否通过, 细节)])`。
    """
    items = []

    def item(name, ok, detail=""):
        items.append((name, bool(ok), detail))

    a, b = "jack.hu@example.com", "jack.hu@other.com"
    item("同一账号的分区名是确定的（算两次一样）", slug(a) == slug(a), slug(a))
    item("不同域名／不同本地部分不会撞同一个分区", slug(a) != slug(b),
         "%s ≠ %s" % (slug(a), slug(b)))
    item("分区名只含合法目录字符",
         bool(re.fullmatch(r"[a-z0-9.\-]+", slug("A B+C/奇怪@例子.com"))), slug("A B+C/奇怪@例子.com"))
    item("大小写与空白不影响分区（同一账号不会分裂成两个目录）",
         slug(" Jack.Hu@Example.COM ") == slug(a), slug(" Jack.Hu@Example.COM "))

    saved = {k: os.environ.get(k) for k in (BASE_ENV, "DANIEL_HOME", "DANIEL_KEYCHAIN_ACCOUNT")}
    tmp = tempfile.mkdtemp(prefix="daniel-accounts-selfcheck-")
    try:
        os.environ[BASE_ENV] = tmp
        os.environ.pop("DANIEL_HOME", None)
        os.environ.pop("DANIEL_KEYCHAIN_ACCOUNT", None)
        item("未指定账号时落点＝根目录（既有安装原地不动）", partition_home(None) == tmp, partition_home(None))
        p1 = partition_home(a)
        p2 = partition_home(b)
        item("分区必须在根之下（不得落代码目录）",
             p1.startswith(tmp + os.sep) and p2.startswith(tmp + os.sep), p1)
        item("两个账号的分区互不包含（不串的前提）",
             not p1.startswith(p2) and not p2.startswith(p1), "%s ｜ %s" % (p1, p2))

        # 状态文件：写 → 读 → 可逆；且只落在根之下
        switch(a)
        item("切换后 active＝该账号", active_account() == a, str(active_account()))
        item("切换后分区目录已就绪（含 sched／output）",
             all(os.path.isdir(os.path.join(p1, s)) for s in ("session", "cache", "output",
                                                              "logs", "sched")), p1)
        switch(b)
        item("切到另一个账号后 active 跟着变", active_account() == b, str(active_account()))
        item("A 的分区在切到 B 之后仍然存在（切换不删任何东西）", os.path.isdir(p1), p1)
        switch(a)
        item("切回 A 后 active＝A（来回切可逆）", active_account() == a, str(active_account()))
        state = read_state()
        item("已存账号注册表两条都在（只新增、不删）",
             len(state["accounts"]) == 2
             and {str(r["email"]).lower() for r in state["accounts"]} == {a.lower(), b.lower()},
             str([r.get("email") for r in state["accounts"]]))
        item("账号状态文件落在根之下且权限 600",
             state_path().startswith(tmp + os.sep)
             and oct(os.stat(state_path()).st_mode & 0o777) == "0o600",
             "%s %s" % (state_path(), oct(os.stat(state_path()).st_mode & 0o777)))
        clear_active()
        item("取消账号后回到根目录且注册表不丢",
             active_account() is None and len(read_state()["accounts"]) == 2, str(active_account()))

        # 注入：有账号才设 DANIEL_HOME，没有账号不设
        os.environ.pop("DANIEL_HOME", None)
        apply_environment(a)
        item("注入后 DANIEL_HOME＝该账号分区",
             os.environ.get("DANIEL_HOME") == p1, str(os.environ.get("DANIEL_HOME")))
        item("注入后凭据账号被钉到该账号（切回免重输的机制）",
             os.environ.get("DANIEL_KEYCHAIN_ACCOUNT") == a,
             str(os.environ.get("DANIEL_KEYCHAIN_ACCOUNT")))
        os.environ.pop("DANIEL_HOME", None)
        apply_environment(None)
        item("没有当前账号时不注入 DANIEL_HOME（不改变出厂语义）",
             "DANIEL_HOME" not in os.environ, str(os.environ.get("DANIEL_HOME")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return all(ok for _n, ok, _d in items), items


__all__ = ["BASE_ENV", "PARTITIONS_SUBDIR", "STATE_NAME", "SCHEMA", "base_home",
           "base_home_reason", "slug", "partitions_dir", "partition_home", "state_path",
           "read_state", "write_state", "active_account", "accounts", "register_account",
           "keychain_has", "keychain_service", "apply_environment", "partition_facts",
           "list_accounts", "ensure_partition", "partition_summary", "switch", "clear_active",
           "self_check"]
