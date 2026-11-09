#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daniel 系统（daniel-agent.com）官方数据客户端。

来源=用户提供的官方数据入口（jack.hu 账号 · Halliday brand 下 Saved Lists）。
实现要点（实证）：
  - 前端是 React SPA，数据层为 tRPC（同源 `/api/trpc`），非 tRPC REST；登录路由 `auth.login`（mutation）。
  - 登录成功以 `set-cookie: app_session_id=<JWT>` 维持会话（1 年有效），后续请求带该 cookie 即可。
  - 读类路由用 GET：`/api/trpc/<route>?batch=1&input=<urlencoded {"0":{"json":<input>}}>`；
    写/登录类用 POST：body `{"json": <input>}`（含 meta.values 处理 Date 字段，本项目用不到）。
  - 响应形态：GET → `[{"result":{"data":{"json":...}}}]`；POST → `{"result":{"data":{"json":...}}}`。

凭证纪律（TICKET-144 · P0-1 改造后）：
  - **凭据**：① 系统钥匙串（macOS `security`，service `daniel-copilot`）→ ② `DANIEL_EMAIL`/`DANIEL_PASSWORD`
    → ③ **旧**明文文件 `<工作区根>/.daniel_cred.json`（只读兼容，不修改）→ ④ 明文降级文件
    `$DANIEL_HOME/secrets/credentials.json`（**仅** `DANIEL_ALLOW_PLAINTEXT=1`，权限 600，用则打警告）。
    脚本内不硬编码明文；详见 `daniel_credentials.py`。
  - **落点**：会话 `$DANIEL_HOME/session/session.json`、缓存 `$DANIEL_HOME/cache/brand-index.json`
    （旧位置 `.kol-tools/.daniel_session.json`、`.kol-tools/_cache/brand-index.json` **仍可读**，不再新写）；
    详见 `daniel_paths.py`（`DANIEL_HOME` 覆盖，默认 `~/Library/Application Support/DanielCopilot`）。
  - **端点**：`DANIEL_BASE_URL` 覆盖，默认 `https://daniel-agent.com`。
  - 会话 cookie 含 JWT（勿外发）；凭据/会话**不得进入任何分发物**（`check_no_secrets_in_dist.py` 断言）。

错误面纪律（TICKET-179）：
  - **服务端已经把原因写在响应体里**（tRPC 信封 `{"error":{"json":{"message":…,"data":{…}}}}`），
    而 `urllib.request.urlopen` 在非 2xx 时抛 `HTTPError` —— **不读 `HTTPError.read()` 就等于把
    服务端原因扔掉**，只剩 `HTTP Error 500: Internal Server Error`。
  - 于是"凭据不对"（服务端明写 `Invalid email or password`）会被报成"内部错误 1"，并把用户
    引向 "加 --verbose 看调用栈"这种**完全错误**的排查方向。
  - 现在的口径：**读体 → 解 tRPC 信封 → 分类**
      · 凭据／账号类 ⇒ `CredentialError`（SystemExit 系，CLI 映射**退出码 2＝用户错误**）
        ＋ 人话 ＋ 可执行下一步；
      · 其它带信封的服务端错误 ⇒ `TRPCError`（**保留服务端原文**，走"内部错误 1"）；
      · **没有 tRPC 信封的真 5xx ⇒ 原样抛 `HTTPError`**（仍是内部错误 1，保留 --verbose 建议）。
"""
import copy
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


def _load_sibling(name):
    """加载同目录兄弟模块（本文件可能被 `import`，也可能被 importlib 按路径 exec）。"""
    import importlib.util
    if HERE not in sys.path:
        sys.path.append(HERE)
    mod = sys.modules.get(name)
    if mod is not None and os.path.dirname(os.path.abspath(getattr(mod, "__file__", "") or "")) == HERE:
        return mod
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
dpaths = _load_sibling("daniel_paths")
_creds = _load_sibling("daniel_credentials")

DEFAULT_BASE = "https://daniel-agent.com"


def base_url():
    """端点可配：`DANIEL_BASE_URL` 覆盖，默认不变（TICKET-144 §4）。"""
    return (os.environ.get("DANIEL_BASE_URL") or DEFAULT_BASE).rstrip("/")


BASE = base_url()                                                  # 兼容旧 import（脚本会 `from daniel_client import BASE`）

# 落点（新位置；旧位置只读兼容）—— 名字保持与改造前一致，语义见 daniel_paths.py
SESSION_FILE = dpaths.resolve("session_file")
BRAND_INDEX_PATH = dpaths.resolve("brand_index")
CRED_FILE = dpaths.resolve("legacy_credentials_fallback")          # 旧明文凭据路径（内容不动）
LEGACY_SESSION_FILE = dpaths.legacy_path("session_file")
LEGACY_BRAND_INDEX_PATH = dpaths.legacy_path("brand_index")
LEGACY_CRED_FILE = CRED_FILE


def _iso_now():
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


def _atomic_json(path, obj):
    """原子写 JSON（临时文件 ＋ os.replace）—— 与 safe_text_patch 同纪律：禁止先截断。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _cred():
    """凭据解析（钥匙串 → 环境变量 → 旧明文 → 显式降级明文）。逻辑在 daniel_credentials.py。"""
    return _creds.resolve_credentials()


def _read_session_cookie():
    """按"新位置 → 旧位置"顺序读会话 cookie。返回 (cookie, 是否来自旧位置)。"""
    for i, path in enumerate(dpaths.read_candidates("session_file")):
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:                                          # noqa: BLE001
            continue
        if d.get("cookie"):
            return d["cookie"], (i > 0)
    return None, False


def _read_brand_index(path, ttl_days):
    """读缓存索引；不存在／过期／损坏 → None（触发重建）。"""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            idx = json.load(f)
        age = time.time() - float(idx.get("builtAtUnix") or 0)
    except Exception:                                              # noqa: BLE001
        return None
    if age < ttl_days * 86400 and idx.get("brands"):
        return idx
    return None


# ─────────────────────────── 错误面：读体 → 解 tRPC 信封 → 分类（TICKET-179）───────────────────────────
#: 服务端消息 → 业务分类。**只认消息形态**（HTTP 码不可信：Daniel 用 500 返回"密码不对"）。
FAILURE_KINDS = (
    # （正则，分类键）顺序即优先级
    (r"invalid email or password|incorrect password|password is incorrect|invalid credentials"
     r"|wrong password|邮箱或密码|密码不正确", "credential"),
    (r"user not found|no user found|account (is )?(not found|disabled|locked|suspended)"
     r"|账号不存在|账号已停用", "account"),
)

#: 分类 → 人话（**不回贴服务端原文**；原文另附，见 `CredentialError.human`）
FAILURE_HUMAN = {
    "credential": "邮箱或密码不正确：Daniel 没有接受这组凭据。",
    "account": "这个账号在 Daniel 侧不可用（未找到，或已停用／锁定）。",
}
#: 分类 → 可执行下一步（**写给用户看**，不是写给开发者看）
FAILURE_NEXT = {
    "credential": "重跑 `daniel account credentials set --email <你的邮箱> --confirm` 重新写入凭据"
                  "（或先用 `daniel account credentials` 核对邮箱拼写），再跑 `daniel account login --confirm`。",
    "account": "先用 `daniel account credentials` 核对写入的邮箱是不是你要用的那个账号；"
               "若账号确实被停用，请联系 Daniel 侧管理员恢复后再登录。",
}


def classify_failure(message):
    """服务端 message → 分类键（`credential`／`account`）；不命中 → None。"""
    m = str(message or "").lower()
    if not m:
        return None
    for pat, kind in FAILURE_KINDS:
        if re.search(pat, m):
            return kind
    return None


class TRPCError(RuntimeError):
    """服务端返回的 tRPC 错误 —— **已读响应体**，不丢服务端原因。

    字段来自信封 `{"error":{"json":{"message":…,"code":…,"data":{…}}}}`；
    读不到体时 `server_message` 为 None（那就只是"HTTP 码"这一层信息）。
    """

    def __init__(self, http_status, server_message=None, server_code=None,
                 data_code=None, path=None, raw=None):
        self.http_status = http_status
        self.server_message = server_message
        self.server_code = server_code
        self.data_code = data_code
        self.path = path
        self.raw = raw or ""
        self.kind = classify_failure(server_message)
        super().__init__(self.describe())

    def describe(self):
        bits = ["HTTP %s" % self.http_status]
        if self.path:
            bits.append("通路 %s" % self.path)
        code = self.data_code or self.server_code
        if code is not None:
            bits.append("服务端码 %s" % code)
        if self.server_message:
            bits.append("服务端原文：%s" % self.server_message)
        return "；".join(bits)


class CredentialError(SystemExit):
    """**用户错误**（凭据／账号类）：服务端已经说清原因，CLI 必须报退出码 2 而不是 1。

    为什么继承 `SystemExit`：本工程既有约定 —— `.kol-tools/` 下的能力脚本用 `SystemExit`
    报"用户可见的错误"（品牌查不到、凭据缺失…），CLI 把它统一映射成**退出码 2（用户错误）**；
    而 `RuntimeError` 会落到 CLI 的兜底分支被报成"内部错误 1"（本票要修的正是这个）。

    `human`（即 `str(e)`）＝ 人话 ＋ 可执行下一步 ＋ 服务端原文（带标签）。
    "服务端原文"必须**可回查**（TICKET-179：--verbose 与 --json 都要留），故放在同一段文本里，
    但排在**人话与下一步之后**、且带明确标签 —— 用户先看到的是"该做什么"，不是英文报错。
    """

    def __init__(self, kind, trpc=None):
        self.kind = kind
        self.trpc = trpc
        human = FAILURE_HUMAN.get(kind) or FAILURE_HUMAN["credential"]
        self.human = human
        self.next_step = FAILURE_NEXT.get(kind) or FAILURE_NEXT["credential"]
        text = "%s%s" % (human, self.next_step)
        if trpc is not None:
            text += "（服务端原文：%s）" % (trpc.server_message or trpc.describe())
        super().__init__(text)


def parse_trpc_error(body):
    """从 HTTP 错误体里解出 tRPC 错误信封；解不出（非 JSON／非信封）→ None。"""
    if not body:
        return None
    try:
        d = json.loads(body)
    except Exception:                                              # noqa: BLE001
        return None
    if isinstance(d, list):                     # batch 形态 `[{…}]`
        d = d[0] if d else None
    if not isinstance(d, dict):
        return None
    err = d.get("error")
    if not isinstance(err, dict):
        return None
    j = err.get("json") if isinstance(err.get("json"), dict) else err
    data = j.get("data") if isinstance(j.get("data"), dict) else {}
    return {"message": j.get("message"), "code": j.get("code"),
            "dataCode": data.get("code"), "httpStatus": data.get("httpStatus"),
            "path": data.get("path")}


def http_error_detail(e):
    """`HTTPError` → `TRPCError`（**读体**；体读不到就只留 HTTP 码这一层）。"""
    body = ""
    try:
        body = e.read().decode("utf-8", "replace")
    except Exception:                                              # noqa: BLE001
        body = ""
    env = parse_trpc_error(body) or {}
    return TRPCError(getattr(e, "code", None), server_message=env.get("message"),
                     server_code=env.get("code"), data_code=env.get("dataCode"),
                     path=env.get("path"), raw=body)


def _verbose_error(verbose, where, detail, body=None):
    """`--verbose` 时把服务端原始响应体/错误细节打到 stderr（**唯一**留原文的第二处）。"""
    if not verbose:
        return
    print("[%s] %s" % (where, detail.describe()), file=sys.stderr)
    if body:
        print("[%s] 服务端响应体：%s" % (where, body[:600]), file=sys.stderr)


def login_http_error(e, verbose=False):
    """登录失败的 HTTPError → 该抛什么就抛什么（**分类决定退出码语义**）。

    · 凭据／账号类 ⇒ `CredentialError`（CLI→退出码 2）
    · 其它带信封的服务端错误 ⇒ `TRPCError`（CLI→退出码 1，但**原文不丢**）
    · 没有信封的真 5xx ⇒ `None`（调用方原样 re-raise HTTPError，CLI→退出码 1 ＋ --verbose 建议）
    """
    detail = http_error_detail(e)
    _verbose_error(verbose, "login", detail, detail.raw)
    if detail.kind:
        return CredentialError(detail.kind, trpc=detail)
    if detail.server_message:
        return detail
    return None


# ───────────────────── 重试加厚 ＋ 详情缓存（TICKET-222）─────────────────────
#: 可重试的 HTTP 码：Daniel 的 `discovery.getChannelDetail` 在服务端抖动时返回
#: `HTTP 500 / Failed to fetch channel data. Please try again.`，实测持续十几秒。
#: 这类是**瞬时故障**，不是"没有这份数据"（一次失败 ≠ 没数据）。
RETRYABLE_HTTP = (500, 502, 503, 504)

#: 5xx 指数退避（秒）：4 段 × 5 次尝试，累计等待 1+2+4+8 = **15 秒**（票面要求 ≥10 秒）。
#: 老口径是 1.2/2.4/3.6 共约 7 秒 —— 服务端错误持续十几秒时必然全部失败。
BACKOFF_5XX = (1.0, 2.0, 4.0, 8.0)

#: 频道详情缓存 TTL（秒）：默认 900（15 分钟）。为什么不是更长：详情里的订阅数／播放数按小时级
#: 才会明显变化，15 分钟足够覆盖"同一批红人被反复取详情"的窗口，又不会给出明显过期的数。
#: `DANIEL_DETAIL_CACHE_TTL` 可覆盖（0 表示关闭缓存）。
DETAIL_CACHE_TTL = float(os.environ.get("DANIEL_DETAIL_CACHE_TTL") or 900)

#: 进程内详情缓存 {channelId: {"expiresAt": float, "data": dict}}。
#: 为什么是进程内：常驻 worker（插件 worker.py）一次进程服务很多次调用，
#: 缓存放在这里就能把"同一批红人的详情"从 N 次网络请求压到 1 次。
_DETAIL_CACHE = {}
_DETAIL_STATS = {"network": 0, "cacheHit": 0, "retry5xx": 0}
_CACHE_LOCK = threading.Lock()


def detail_cache_clear():
    """清空详情缓存（只清缓存，不动会话与其它落点）。"""
    with _CACHE_LOCK:
        n = len(_DETAIL_CACHE)
        _DETAIL_CACHE.clear()
    return {"cleared": n}


def detail_cache_stats():
    """缓存与重试的计数器（**全部非空**：没有网络请求就是 0，不是 null）。"""
    now = time.time()
    with _CACHE_LOCK:
        alive = sum(1 for v in _DETAIL_CACHE.values() if v.get("expiresAt", 0) > now)
        entries = len(_DETAIL_CACHE)
    return {"entries": alive, "entriesStale": entries - alive,
            "networkRequests": _DETAIL_STATS["network"],
            "cacheHits": _DETAIL_STATS["cacheHit"],
            "retry5xx": _DETAIL_STATS["retry5xx"],
            "ttlSeconds": int(DETAIL_CACHE_TTL)}


def _detail_cache_key(kw):
    """按 channelId 建键（也认 `id`／`channel`：不同调用方给同一个红人的入参名不一样）。"""
    if not isinstance(kw, dict):
        return None
    for name in ("channelId", "channel_id", "id", "channel"):
        v = kw.get(name)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    return None


class Daniel:
    def __init__(self, verbose=True):
        self.verbose = verbose
        self.cookie = self._load_cookie()

    # ---------- session ----------
    def _load_cookie(self):
        cookie, from_legacy = _read_session_cookie()
        if cookie and from_legacy:
            # 旧位置命中 → 迁移到 $DANIEL_HOME/session/（原子写；只读环境静默跳过，链路不受影响）
            try:
                _atomic_json(SESSION_FILE, {"cookie": cookie, "ts": time.time()})
                os.chmod(SESSION_FILE, 0o600)
                if self.verbose:
                    print("[session] 旧位置 → 新位置迁移完成: %s" % SESSION_FILE)
            except OSError as e:
                print("⚠️  会话迁移失败（只读环境可忽略）：%s" % e, file=sys.stderr)
        return cookie

    def _save_cookie(self, cookie):
        self.cookie = cookie
        try:
            _atomic_json(SESSION_FILE, {"cookie": cookie, "ts": time.time()})
            os.chmod(SESSION_FILE, 0o600)
        except OSError as e:
            # 只有写不进去（例如 DANIEL_HOME 不可写）才降级为"仅内存会话"，不让链路整体挂掉
            print("⚠️  会话落盘失败（%s）：本次仅内存会话有效" % e, file=sys.stderr)

    def login(self, force=False):
        if self.cookie and not force:
            if self.whoami():
                return self.cookie
        email, password = _cred()
        base = base_url()
        body = json.dumps({"json": {"email": email, "password": password}}).encode()
        req = urllib.request.Request(
            base + "/api/trpc/auth.login", data=body, method="POST",
            headers={"Content-Type": "application/json", "Origin": base,
                     "Referer": base + "/auth",
                     "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode()
                sc = r.headers.get("set-cookie") or ""
        except urllib.error.HTTPError as e:
            # 🔴 **必须读 `HTTPError.read()`**：服务端把"邮箱或密码不正确"写在响应体里，
            #    只留 HTTP 码就等于把用户错误报成内部错误（TICKET-179）。
            err = login_http_error(e, verbose=self.verbose)
            if err is None:
                raise                       # 无 tRPC 信封的真 5xx：原样上抛（CLI→内部错误 1）
            raise err from None
        m = [p.strip() for p in sc.split(";") if p.strip().startswith("app_session_id=")]
        if not m:
            # 未拿到会话 cookie ⇒ 仍按**用户错误**（CLI 把 SystemExit 映射成退出码 2）
            raise SystemExit("登录失败：未拿到 app_session_id（检查凭证）")
        self._save_cookie(m[0])
        if self.verbose:
            print("[login] ok")
        return self.cookie

    def whoami(self):
        """当前账号邮箱；拿不到 → None。

        ⚠️ 这里的 `except Exception` 是**设计如此**：它只当"会话还有效吗"的布尔探测用
        （`login(force=False)` 靠它决定要不要真登录），失败原因由随后的真登录路径给出。
        注意：凭据类失败抛的是 `CredentialError`（SystemExit 系，**不是** Exception），
        因此**不会被这里吞掉** —— 会如实冒到调用方（TICKET-179）。
        """
        try:
            d = self.query("auth.me")
            return (d or {}).get("email")
        except Exception:
            return None

    # ---------- transport ----------
    def _headers(self):
        base = base_url()
        h = {"Content-Type": "application/json", "Origin": base, "Referer": base + "/",
             "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"}
        if self.cookie:
            h["Cookie"] = self.cookie
        return h

    def query(self, route, inp=None, retries=3, timeout=None, backoff=None):
        """GET 读类路由。inp=None 时传 {"json":null}。

        `timeout` 省略时沿用默认 60 秒；**长任务型接口**（如官方库检索 `discovery.searchRoster`，
        服务端排队时可能 503）建议传更小的 timeout ＋ `retries=1`，否则 3×90 秒会把"一次调用"
        拖成两分半（2026-10-18 实测：单次 156–161 秒后报 503）。

        重试口径（TICKET-222，两点都实测过）：
          · **5xx（500/502/503/504）按指数退避加厚**：默认最多 5 次尝试、退避 1/2/4/8 秒，
            累计窗口 15 秒（老口径 1.2/2.4/3.6 共约 7 秒 —— `discovery.getChannelDetail` 抖动
            十几秒时必然全军覆没）。**加厚只作用于"肯等"的调用**：`retries>=3`（默认档）；
            调用方显式把 retries 压到 1–2 是在要求"快速失败"（官方库那种长任务接口），
            对它加厚会把一次调用拖成几十秒，所以按调用方意图走老节奏。
          · 非 5xx（4xx／信封错误／UNAUTHORIZED）保持原来的 1.2×(k+1) 节奏与次数不变。

        错误面（TICKET-179）：非 2xx **先读体解信封**再决定 —— 凭据类立刻以
        `CredentialError` 用户错误退出（重试没有意义），其余带信封的错误把**服务端原文**
        挂进异常文本（原来只剩 "HTTP Error 500: …"）。
        """
        _timeout = timeout if timeout else 60
        payload = {"0": {"json": inp}}
        url = f"{base_url()}/api/trpc/{route}?batch=1&input=" + urllib.parse.quote(json.dumps(payload))
        retries = int(retries or 3)
        schedule = tuple(backoff) if backoff is not None else (BACKOFF_5XX if retries >= 3 else ())
        attempts = max(retries, len(schedule) + 1) if schedule else retries
        last = None
        attempt = 0
        while attempt < attempts:
            k = attempt
            attempt += 1
            try:
                req = urllib.request.Request(url, headers=self._headers())
                with urllib.request.urlopen(req, timeout=_timeout) as r:
                    data = json.loads(r.read().decode())
                if isinstance(data, list):
                    data = data[0]
                if "error" in data:
                    raise RuntimeError(f"{route} -> {json.dumps(data['error'])[:300]}")
                return data["result"]["data"]["json"]
            except urllib.error.HTTPError as e:
                detail = http_error_detail(e)
                _verbose_error(self.verbose, route, detail, detail.raw)
                if detail.kind:
                    raise CredentialError(detail.kind, trpc=detail) from None
                last = detail
                code = getattr(e, "code", None) or detail.http_status
                if schedule and code in RETRYABLE_HTTP:
                    # 5xx：按 1/2/4/8 秒指数退避；**最后一次失败不再空等**（没有下一次了）
                    if attempt < attempts:
                        wait = schedule[min(k, len(schedule) - 1)]
                        _DETAIL_STATS["retry5xx"] += 1
                        if self.verbose:
                            print("[retry] %s HTTP %s：%.0f 秒后第 %d 次尝试（共 %d 次）"
                                  % (route, code, wait, attempt + 1, attempts), file=sys.stderr)
                        time.sleep(wait)
                else:
                    time.sleep(1.2 * (k + 1))
            except Exception as e:  # noqa: BLE001
                last = e
                if "UNAUTHORIZED" in str(e):
                    self.login(force=True)
                time.sleep(1.2 * (k + 1))
        raise RuntimeError(f"{route} 失败: {last}")

    def mutate(self, route, inp=None, retries=3):
        body = json.dumps({"json": inp}).encode()
        last = None
        for k in range(retries):
            try:
                req = urllib.request.Request(base_url() + "/api/trpc/" + route, data=body,
                                             method="POST", headers=self._headers())
                with urllib.request.urlopen(req, timeout=90) as r:
                    data = json.loads(r.read().decode())
                if "error" in data:
                    raise RuntimeError(f"{route} -> {json.dumps(data['error'])[:300]}")
                return data["result"]["data"]["json"]
            except urllib.error.HTTPError as e:              # 同 query：读体、不丢服务端原因
                detail = http_error_detail(e)
                _verbose_error(self.verbose, route, detail, detail.raw)
                if detail.kind:
                    raise CredentialError(detail.kind, trpc=detail) from None
                last = detail
                time.sleep(1.2 * (k + 1))
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(1.2 * (k + 1))
        raise RuntimeError(f"{route} 失败: {last}")

    # ---------- 业务封装 ----------
    def brands(self, workspace_id=None):
        """品牌列表。⚠️ 不带 `workspace_id` 时吃**当前活跃工作区** —— 需要与活跃工作区无关时，
        用 `brand_index()`／`resolve_brand_ref()`（跨工作区索引）。"""
        inp = {} if workspace_id is None else {"workspaceId": int(workspace_id)}
        for route in ("brands.list", "workspaces.getBrands"):
            try:
                d = self.query(route, inp)
                if d:
                    return route, d
            except Exception:
                continue
        raise SystemExit("取 brands 失败")

    # ---------- 工作区无关的品牌解析（2026-10-10 用户要求：行为不受活跃工作区影响）----------
    def active_workspace_id(self):
        """仅供**提示信息**使用；任何取数逻辑都不得依赖它。"""
        try:
            return (self.query("auth.me", {}) or {}).get("activeWorkspaceId")
        except Exception:  # noqa: BLE001
            return None

    def get_brand(self, brand_id):
        """按 id 直取（`brands.getById` **跨工作区可用**）—— 与活跃工作区无关。"""
        return self.query("brands.getById", {"id": int(brand_id)})

    def brand_index(self, refresh=False, ttl_days=7):
        """跨工作区品牌索引 {brands:[{id,name,workspaceId,workspaceName}], builtAt}，落盘缓存。

        构建方式：`auth.listMyWorkspaces` → 逐个 `brands.list {workspaceId}`（约 0.6s/工作区）。
        意义：**按名字解析品牌不再依赖"当前活跃工作区"**。

        落点：`$DANIEL_HOME/cache/brand-index.json`（新写）；旧位置 `.kol-tools/_cache/brand-index.json`
        仍可读，命中旧位置时自动迁移到新位置 —— **新位置优先**，避免刷新出的新索引被旧文件永久遮蔽。
        """
        if not refresh:
            for i, cand in enumerate(dpaths.read_candidates("brand_index")):
                idx = _read_brand_index(cand, ttl_days)
                if idx:
                    if i > 0:
                        try:
                            _atomic_json(BRAND_INDEX_PATH, idx)
                            if self.verbose:
                                print("[cache] 品牌索引旧位置 → 新位置迁移完成: %s" % BRAND_INDEX_PATH)
                        except OSError as e:
                            print("⚠️  品牌索引迁移失败（只读环境可忽略）：%s" % e, file=sys.stderr)
                    return idx
        ws = self.query("auth.listMyWorkspaces", {}) or []
        rows = []
        for w in ws:
            if not isinstance(w, dict) or w.get("id") is None:
                continue
            wid = int(w["id"])
            bs = None
            for route in ("brands.list", "workspaces.getBrands"):
                try:
                    bs = self.query(route, {"workspaceId": wid})
                    break
                except Exception:  # noqa: BLE001
                    continue
            for b in (bs or []):
                if isinstance(b, dict) and b.get("id") is not None:
                    rows.append({"id": b["id"], "name": b.get("name"),
                                 "workspaceId": b.get("workspaceId", wid),
                                 "workspaceName": w.get("name")})
        idx = {"builtAt": _iso_now(), "builtAtUnix": time.time(),
               "workspaceCount": len(ws), "brands": rows}
        _atomic_json(BRAND_INDEX_PATH, idx)
        return idx

    def resolve_brand_ref(self, ref, refresh=False):
        """品牌引用（数字 id 或名字）→ brand dict（含 workspaceId），**与活跃工作区无关**。

        ① 数字 ⇒ `brands.getById`（跨工作区）；查不到再用 `sovCategories.getByBrand` 校验存在性；
        ② 名字 ⇒ 跨工作区索引精确匹配（大小写／空白不敏感）；多命中 ⇒ 报全部候选要 id，**不猜**。
        """
        s = str(ref).strip()
        if not s:
            raise SystemExit("品牌引用为空")
        if s.lstrip("-").isdigit():
            bid = int(s)
            b = self.get_brand(bid)
            if isinstance(b, dict) and b.get("id"):
                return b
            profs = self.query("sovCategories.getByBrand", {"brandId": bid}) or []
            if profs:
                return {"id": bid, "name": "<brand %s>" % bid,
                        "workspaceId": profs[0].get("brandId") and None or None,
                        "category": profs[0].get("name")}
            raise SystemExit("brandId=%s 不可达：brands.getById 返回空且 sovCategories.getByBrand 为空。" % bid)
        idx = self.brand_index(refresh=refresh)
        hits = [b for b in idx["brands"] if str(b.get("name") or "").strip().lower() == s.lower()]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise SystemExit("品牌名「%s」在多个工作区命中，请直接给 brandId：%s"
                             % (s, ["%s(id=%s, ws=%s)" % (h["name"], h["id"], h["workspaceId"])
                                    for h in hits]))
        names = sorted({b.get("name") for b in idx["brands"] if b.get("name")})[:20]
        raise SystemExit("找不到品牌「%s」：跨 %d 个工作区的索引里无此名字（例：%s）。"
                         "索引构建于 %s；可用 brand_index(refresh=True) 刷新。"
                         % (s, idx.get("workspaceCount"), names, idx.get("builtAt")))

    def lists(self, brand_id):
        return self.query("lists.listByBrand", {"brandId": brand_id})

    def items(self, list_id):
        return self.query("lists.getItems", {"listId": list_id})

    def channel_detail(self, use_cache=True, **kw):
        """频道详情（`discovery.getChannelDetail`）＋ **进程内缓存**（TICKET-222）。

        缓存口径：按 `channelId` 缓存，TTL 默认 900 秒（`DANIEL_DETAIL_CACHE_TTL` 可覆盖，
        0 表示关闭）。命中时**不发任何网络请求**，返回体除了原字段外多两项可选说明：
        `从缓存命中=True` 与 `缓存剩余秒数`；未命中（真取）时**返回结构与改造前逐字节一致**。
        为什么要缓存：这个接口在服务端抖动时会连续十几秒 500，而"同一批红人补 handle／
        批量取档案"会反复打同一个 channelId —— 缓存把 N 次请求压成 1 次。
        """
        key = _detail_cache_key(kw)
        now = time.time()
        if key and use_cache and DETAIL_CACHE_TTL > 0:
            with _CACHE_LOCK:
                hit = _DETAIL_CACHE.get(key)
            if hit and hit.get("expiresAt", 0) > now:
                _DETAIL_STATS["cacheHit"] += 1
                data = copy.deepcopy(hit.get("data"))
                if isinstance(data, dict):
                    data["从缓存命中"] = True
                    data["缓存剩余秒数"] = max(1, int(hit["expiresAt"] - now))
                return data
        _DETAIL_STATS["network"] += 1
        data = self.query("discovery.getChannelDetail", kw)
        if key and use_cache and DETAIL_CACHE_TTL > 0 and isinstance(data, dict) and data:
            with _CACHE_LOCK:
                _DETAIL_CACHE[key] = {"expiresAt": now + DETAIL_CACHE_TTL,
                                      "data": copy.deepcopy(data)}
        return data

    def channel_insight(self, **kw):
        return self.query("discovery.getChannelInsight", kw)

    def channel_videos(self, **kw):
        return self.query("discovery.getChannelVideos", kw)


if __name__ == "__main__":
    print("endpoint:", base_url())
    print("home:", dpaths.home(), "(%s)" % dpaths.home_reason())
    print("session:", SESSION_FILE)
    print("cache:", BRAND_INDEX_PATH)
    d = Daniel()
    d.login()
    print("whoami:", d.whoami())
    route, bs = d.brands()
    print("brands route:", route)
    print(json.dumps(bs, ensure_ascii=False)[:1200])
