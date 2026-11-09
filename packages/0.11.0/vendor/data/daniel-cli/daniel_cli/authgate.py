# -*- coding: utf-8 -*-
"""授权门禁（TICKET-194）—— **单一真源**：一条命令"未登录时能不能跑"只在这里回答。

用户 2026-10-16 逐字要求
------------------------
> 「对于接入的部分，**daniel cli 和 mcp 的起点一定是授权和登陆**（也就是我安装后，要使用，
> 那么就需要输入正确的账号密码，**否则是无法跳过授权进入到实际对 daniel 的模块调用**中的）」

以及授权登录的**唯一正路**（同一用户逐字裁定）：
> 「逻辑**并不是直接在 codex 里面直接输入账号密码**，而是需要**支持跳转到 Daniel 的登陆页面**，
> 在 Daniel 完成登陆后，**对应的用户信息被读取和完成授权**」

于是本文件只做三件事：
  ① **判"登录了没有"**（本地会话 ＋ 一次轻量服务端校验），给出**可脚本判定**的三态；
  ② **判"这条命令要不要先登录"**（白名单单一真源 `WHITELIST`，逐条带理由）；
  ③ 把"未登录"写成**人话 ＋ 一行修法 ＋ 结构化错误**，交给 CLI 与 MCP 两侧同一个出口。

为什么门禁只放在**模块分发层的单一入口**
----------------------------------------
`daniel_cli/cli.py::main()` 是**唯一**把"模块＋子命令"变成"处理函数"的地方
（`find_command` → `handler_for`）。前置检查放在这里 ⇒ 一条实现管住 84 条命令；
任何子命令都不需要、也不允许自己再写一份"登录了吗"的判断。

两档，**无第三态**
------------------
| 档 | 判据 | 未登录时的行为 |
|---|---|---|
| **白名单**（`WHITELIST`） | 用途属于 **接入／自救／随包自检** 三类之一 | 照常可跑（用户得先把登录这件事做完） |
| **受门禁** | 其余全部（凡要读／写 Daniel 数据、或要跑 Daniel 工序的） | **fail-fast**：退出码 2 ＋「请先登录」＋ 一行修法，**零真实数据、不静默降级** |

判据是"**用途**"而不是"**是不是本地操作**"：`daniel sched status`（纯本地队列）也受门禁 ——
因为未登录的人不会有用得上的队列，而"这条命令没登录也能跑"本身就是一处让人困惑的面。

未登录时的**主路径**（人用）
----------------------------
  `daniel account login --browser`
    → 打开 Daniel 登录页（`https://daniel-agent.com/auth`）→ 账号密码**只在 Daniel 页面上**输
    → 把浏览器里的会话粘回 CLI → **先校验后落盘**（`$DANIEL_HOME/session/session.json`，600）。

无头／CI 的**备用**路（**不是给人用的主路径**）：环境变量 `DANIEL_EMAIL`／`DANIEL_PASSWORD`
＋ `daniel account login --confirm`。

会话读取**不另造第二套**
------------------------
会话只有一个落点：`daniel_paths.resolve("session_file")`（`$DANIEL_HOME/session/session.json`），
读法只有一处：既有共享客户端 `daniel_client._read_session_cookie()`。本文件**只调它**，
不自己解析、不自己落盘。
"""
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

from .exits import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE

#: 机器可读的错误类别（`--json` 信封 `error.kind`；MCP 侧据此给结构化"未登录"）
KIND_UNAUTHENTICATED = "unauthenticated"

#: 未登录时**一行可执行的修法**（主路径；备用路写在帮助与文档里）
LOGIN_COMMAND = "daniel account login --browser --confirm"
LOGIN_HINT = ("%s（打开 Daniel 登录页，在页面上完成登录后把会话粘回来）"
              "—— 无头／CI 用环境变量 DANIEL_EMAIL／DANIEL_PASSWORD ＋ "
              "`daniel account login --confirm`（不是给人用的主路径）" % LOGIN_COMMAND)

#: 服务端校验的默认超时秒数（`auth status` 的 `--timeout` 默认值；单一真源）
VERIFY_TIMEOUT = 25

#: Daniel 登录页路由（实读前端 bundle：`client/src/pages/Auth.tsx`，前端路由 `/auth`）
LOGIN_PAGE_PATH = "/auth"

# ─────────────────────────── 白名单（未登录可用）的单一真源 ───────────────────────────
# 键 = (模块, 子命令)；值 = **为什么它是自救命令**（进帮助、进文档、进回报，不许只有代码知道）。
# 三类的分界写在这里，新增命令时必须落进其中一档 —— 没有第三态。
#   ① 接入：把 CLI 接到宿主上（不取任何 Daniel 数据）
#   ② 自救：账号／凭据／落点／登录本身（未登录时用户唯一能自救的地方）
#   ③ 随包自检：随包语料与命令清单的离线自检（证明"装好了"，不证明"登录了"）
WHITELIST = {
    # ① 接入（TICKET-189）：写的是本机宿主配置，取不到任何线上数据
    ("connect", "list"): "接入自检：列出已知宿主与本机接入状态（只读本机配置）",
    ("connect", "print"): "接入自检：打印将要写进宿主配置的内容（不写）",
    ("connect", "apply"): "接入：把 CLI 接到宿主（只写本机配置文件，不取任何 Daniel 数据）",
    ("connect", "uninstall"): "接入自救：撤掉本机接入（只动本机配置文件）",
    ("connect", "doctor"): "接入自检：逐项确认随包语料与 import 路径是否完整（离线）",

    # ② 自救：登录／凭据／落点／账号指针 —— 未登录时用户唯一能走的路
    ("account", "login"): "自救：**登录入口本身**（跳转登录页 → 回读会话）；它就是修法那一条命令",
    ("account", "credentials"): "自救：看凭据从哪来（不回显任何密码），判断「我为什么登录不上」",
    ("account", "credentials-set"): "自救：把凭据写进本机钥匙串（备用路；主路径是浏览器登录）",
    ("account", "whoami"): "自救：确认登录的是谁（未登录时它会如实报「拿不到账号」）",
    ("account", "paths"): "自救：看会话／缓存／产出落在哪，排查「会话没落盘」",
    ("account", "list"): "自救：看本机有哪些账号分区与钥匙串条目（只读本机状态）",
    ("account", "switch"): "自救：切到某个账号的数据分区（只写本机指针文件，不取数据）",
    ("auth", "status"): "自救：**登录状态本身**（退出码三档，可脚本判定）—— 未登录时最该跑的一条",

    # ③ 随包自检：命令清单／随包语料／本地文件，一律离线
    ("schema", "show"): "随包自检：命令清单真源（离线）",
    ("schema", "mcp"): "随包自检：派生出来的 MCP 工具定义（离线）",
    ("schema", "dsh-tools"): "随包自检：派生出来的 DSH 工具定义（离线）",
    ("schema", "check"): "随包自检：声明与实现是否自洽（离线；装完第一件事）",
    ("skills", "list"): "随包语料自检：列出随包业务语料（离线）",
    ("skills", "read"): "随包语料自检：读一段随包业务语料（离线）",
    ("clarify", "plan"): "随包自检：参数级追问清单（只读随包登记表与触发词，离线、不取数）",
    ("clarify", "ask"): "随包自检：找红人的动态追问（只读随包登记表与触发词，离线、不取数）",
    ("intake", "route"): "随包语料自检：需求 → 工序路由（离线）",
    ("intake", "draft"): "随包语料自检：需求草稿（离线）",
    ("intake", "parity"): "随包语料自检：入口与契约是否一致（离线）",
    ("intake", "catalog"): "随包语料自检：随包语料目录（离线）",
    ("playbook", "list"): "随包自检：列出随包工序契约（离线）",
    ("playbook", "show"): "随包自检：看一份随包工序契约（离线）",
    ("playbook", "validate"): "随包自检：校验随包工序契约（离线）",
    ("playbook", "selfcheck"): "随包自检：契约引擎自证（离线，不取 Daniel 数据）",
    ("parity", "selfcheck"): "随包自检：判定口径与页面实现是否逐字一致（离线）",
    ("keywords", "check"): "随包自检：检索词清单只读校验（只读本地文件，不联网）",
    # 为什么把 `route catalog` 也放进来（**它是声明面，不是探测面**）：
    #   ① 它自己写着"离线：列出候选通路（来自既有仪器的候选表，不联网、不探测）"；
    #   ② 随包契约 `contracts/_examples/engine-smoke.json` 的第 S1 步就是跑它 ——
    #      若把它拦下，`daniel playbook selfcheck`（白名单里的随包自检）在**未登录**时会红，
    #      于是"未登录时哪些能跑"这件事自相矛盾。`route probe`／`route sweep`（**真探测**）
    #      仍然受门禁 —— 分档跟着"是否触达数据面"走，不跟着模块名走。
    ("route", "catalog"): "随包自检：通路清单是**声明面**（离线读候选表，不联网、不探测）；"
                          "`route probe`／`sweep` 才是真探测，仍受门禁",
    ("pack", "out"): "接入：出可交付能力包（只读本地文件，不取任何 Daniel 数据）",
    ("pack", "check"): "接入自检：包是否完整、干不干净（离线；换机器前跑）",

    # ① 接入（TICKET-195）：**安装向导本身就是"怎么把授权做起来"的路**
    # —— 它最后的第 ④ 步就是登录入口；未登录的人必须能跑它，否则授权这件事没有起点。
    ("install", "run"): "接入＋自救：**安装向导**（装 CLI／能力束／宿主接入／起登录四步）——"
                        "它不取任何 Daniel 数据，且第 ④ 步就是登录本身（新机器上的第一件事）",
    ("install", "check"): "接入自检：装完复核四项（入口／能力束／接入／登录态），离线＋一次只读校验",
    ("install", "upgrade"): "接入：就地升级到另一份包并重跑自检（只动本机落点，不取任何 Daniel 数据）",
}

#: 白名单的**类别标签**（帮助与文档按这三类呈现，不逐条罗列 30 行）
CATEGORY_LABELS = {
    "connect": "接入",
    "account": "自救",
    "auth": "自救",
    "schema": "随包自检",
    "skills": "随包自检",
    "intake": "随包自检",
    "clarify": "随包自检",
    "playbook": "随包自检",
    "parity": "随包自检",
    "route": "随包自检",
    "keywords": "随包自检",
    "pack": "接入",
    "install": "接入",
}


def is_whitelisted(module_key, command_name):
    """未登录时这条命令能不能跑（**唯一判据**）。"""
    return (str(module_key or ""), str(command_name or "")) in WHITELIST


def whitelist_reason(module_key, command_name):
    return WHITELIST.get((str(module_key or ""), str(command_name or "")))


def whitelist_rows():
    """给文档／帮助／自检用的清单（按类别、模块、子命令排序）。"""
    rows = []
    for (mod, cmd), why in sorted(WHITELIST.items(),
                                  key=lambda kv: (CATEGORY_LABELS.get(kv[0][0], "其他"),
                                                  kv[0][0], kv[0][1])):
        rows.append({"类别": CATEGORY_LABELS.get(mod, "其他"), "模块": mod, "子命令": cmd,
                     "为什么算自救命令": why,
                     "命令行": "daniel %s %s" % (mod, cmd)})
    return rows


# ─────────────────────────── 本地会话（读法只有一处） ───────────────────────────
def _client_mod():
    from .runtime import load_capability
    return load_capability("daniel_client")


def local_session():
    """本机会话事实：`{hasToken, sessionFile, fromLegacy, error}`。**只读，不落盘。**"""
    facts = {"hasToken": False, "sessionFile": None, "fromLegacy": None, "error": None}
    try:
        dc = _client_mod()
        cookie, from_legacy = dc._read_session_cookie()               # noqa: SLF001（既有唯一读法）
        facts["sessionFile"] = dc.SESSION_FILE
        facts["fromLegacy"] = bool(from_legacy)
        facts["hasToken"] = bool(cookie)
        facts["_cookie"] = cookie
    except Exception as e:                                            # noqa: BLE001
        # 能力目录缺失／会话文件读不了：如实记下来，但**不把异常当"已登录"**
        facts["error"] = "%s: %s" % (type(e).__name__, str(e)[:200])
    return facts


# ─────────────────────────── 服务端校验（一次轻量请求） ───────────────────────────
#: 校验结果三态（与 `auth status` 的退出码一一对应）
VERIFY_OK = "ok"                 # 会话有效（0）
VERIFY_REJECTED = "rejected"     # 无 token／token 被服务端拒 ⇒ 去登录（1）
VERIFY_UNREACHABLE = "unreachable"   # 服务端不可达 ⇒ 稍后重试，**不要**引导重新登录（2）


def _trpc_envelope_message(payload):
    """从 tRPC 错误信封里取服务端原文（**只取 message，不取任何凭据**）。"""
    try:
        doc = json.loads(payload)
    except ValueError:
        return None
    items = doc if isinstance(doc, list) else [doc]
    for it in items:
        if not isinstance(it, dict):
            continue
        err = it.get("error")
        if isinstance(err, dict):
            inner = err.get("json") if isinstance(err.get("json"), dict) else err
            if inner.get("message"):
                return str(inner["message"])
    return None


def _trpc_json(payload):
    """从 tRPC 成功信封里取 `result.data.json`（取不到 → None）。"""
    try:
        doc = json.loads(payload)
    except ValueError:
        return None
    items = doc if isinstance(doc, list) else [doc]
    for it in items:
        if not isinstance(it, dict):
            continue
        res = it.get("result")
        if isinstance(res, dict) and isinstance(res.get("data"), dict) \
                and "json" in res["data"]:
            return res["data"]["json"]
    return None


def verify_session(cookie=None, timeout=VERIFY_TIMEOUT):
    """**一次**轻量服务端校验：`auth.me`（GET，只读）。

    返回 `(state, detail)`：`state ∈ {ok, rejected, unreachable}`；
    `detail` 只含**判定所需的最小事实**（掩码邮箱／HTTP 码／服务端原文分类），
    **绝不含会话值本身**（cookie 只在请求头里出现一次，永不进任何输出）。
    """
    cookie = cookie if cookie is not None else local_session().get("_cookie")
    if not cookie:
        return VERIFY_REJECTED, {"理由": "本机没有会话（没有 token 可校验）", "stage": "local"}
    try:
        dc = _client_mod()
        base = dc.base_url()
    except Exception as e:                                            # noqa: BLE001
        return VERIFY_UNREACHABLE, {"理由": "取不到 Daniel 端点配置：%s" % str(e)[:160],
                                    "stage": "config"}
    url = "%s/api/trpc/auth.me?batch=1&input=%s" % (
        base, urllib.parse.quote(json.dumps({"0": {"json": None}})))
    req = urllib.request.Request(url, headers={
        "Content-Type": "application/json", "Origin": base, "Referer": base + "/",
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"})
    body, status = "", None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = getattr(r, "status", 200)
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            body = e.read().decode("utf-8", "replace")               # 服务端原因在响应体里
        except Exception:                                             # noqa: BLE001
            body = ""
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        return VERIFY_UNREACHABLE, {"理由": "连不上 Daniel（%s）" % type(e).__name__,
                                    "stage": "network", "endpoint": base}

    data = _trpc_json(body)
    server_msg = _trpc_envelope_message(body)
    if status == 200 and isinstance(data, dict) and data.get("email"):
        return VERIFY_OK, {"stage": "server", "http": status,
                           "账号(掩码)": _mask(data.get("email")),
                           "系统角色": data.get("systemRole"),
                           "账号状态": data.get("userStatus"),
                           "服务端原文": None}
    if status in (401, 403) or (server_msg and "login" in server_msg.lower()):
        return VERIFY_REJECTED, {"stage": "server", "http": status,
                                 "服务端原文": server_msg or "（未给原文）"}
    if status == 200 and data is None:
        # `auth.me` 在**未登录**时是 200 + `{"json":null}`（设计使然）⇒ 会话被服务端当作无效
        return VERIFY_REJECTED, {"stage": "server", "http": status,
                                 "服务端原文": server_msg or "auth.me 返回 null（未登录态）"}
    if server_msg:
        return VERIFY_UNREACHABLE, {"stage": "server", "http": status,
                                    "服务端原文": server_msg}
    return VERIFY_UNREACHABLE, {"stage": "unknown", "http": status,
                                "服务端原文": (body or "")[:200] or None}


def _mask(email):
    """掩码邮箱（**沿用既有掩码口径**：与 `account credentials` 等处一致，绝不回显原值）。"""
    from .runtime import load_capability
    for mod_name in ("daniel_credentials", "daniel_client"):
        try:
            fn = getattr(load_capability(mod_name), "mask_email", None)
            if callable(fn):
                return fn(email)
        except Exception:                                             # noqa: BLE001
            continue
    s = str(email or "")
    if "@" not in s:
        return (s[:1] + "***") if s else ""
    local, _, dom = s.partition("@")
    tld = ("." + dom.rsplit(".", 1)[1]) if "." in dom else ""
    return "%s***@***%s" % (local[:1], tld)


# ─────────────────────────── `auth status` 的三态结论 ───────────────────────────
#: 三态 → 退出码（照飞书项目 CLI 的口径，写进帮助与文档）
STATUS_EXIT = {VERIFY_OK: EXIT_OK, VERIFY_REJECTED: 1, VERIFY_UNREACHABLE: EXIT_USAGE}

#: 三态 → **下一步**（人话；"服务端不可达"绝不引导重新登录）
STATUS_NEXT = {
    VERIFY_OK: "可以正常调用业务模块。",
    VERIFY_REJECTED: "去登录：%s。" % LOGIN_COMMAND,
    VERIFY_UNREACHABLE: "服务端不可达 —— **过一会儿再试**（本地会话没有失效，不要重新登录）。",
}


def status(timeout=VERIFY_TIMEOUT):
    """登录状态三态结论：`{authenticated, reason, ...}` ＋ 退出码。

    `reason` 的三档（**可脚本判定**，也是给人看的）：
      · 通过：本地会话有效，且服务端确认了这个账号；
      · 去登录：本机没有会话，或会话被服务端拒绝；
      · 稍后重试：服务端不可达（网络／5xx），本地会话**没有**被判定失效。
    """
    sess = local_session()
    local = {
        "本机会话文件": sess.get("sessionFile"),
        "本机有没有会话": bool(sess.get("hasToken")),
        "会话来自旧位置": sess.get("fromLegacy"),
        "会话落盘在 DANIEL_HOME 之内": None,
        "本机会话读取异常": sess.get("error"),
    }
    if sess.get("sessionFile"):
        local["会话落盘在 DANIEL_HOME 之内"] = _inside_home(sess["sessionFile"])
    if not sess.get("hasToken"):
        detail = {"stage": "local", "理由": ("本机没有会话文件，或会话文件里没有会话"
                                            if not sess.get("error") else
                                            "读不到本机会话：%s" % sess.get("error"))}
        return {"authenticated": False, "reason": "去登录", "state": VERIFY_REJECTED,
                "exitCode": STATUS_EXIT[VERIFY_REJECTED], "local": local, "server": detail,
                "next": STATUS_NEXT[VERIFY_REJECTED]}
    state, detail = verify_session(sess.get("_cookie"), timeout=timeout)
    authenticated = state == VERIFY_OK
    reason = {VERIFY_OK: "通过", VERIFY_REJECTED: "去登录", VERIFY_UNREACHABLE: "稍后重试"}[state]
    return {"authenticated": authenticated, "reason": reason, "state": state,
            "exitCode": STATUS_EXIT[state], "local": local, "server": detail,
            "next": STATUS_NEXT[state]}


def _inside_home(path):
    """该路径是否落在生效的 `DANIEL_HOME` 之内（TICKET-194 · C 的同一判据，只为如实回读）。"""
    try:
        from .runtime import load_capability
        home = load_capability("daniel_paths").home()
    except Exception:                                                 # noqa: BLE001
        return None
    import os
    p, h = os.path.abspath(path), os.path.abspath(home)
    return p == h or p.startswith(h + os.sep)


# ─────────────────────────── 门禁的判定与出口 ───────────────────────────
#: 与"未登录"配套的两句人话（**唯一措辞**，CLI 与 MCP 两侧同一份）
GATE_MESSAGE = "请先登录：`{cmd}` 属于 Daniel 的业务模块调用，未登录时不放行。"
GATE_MESSAGE_TAIL = "本次没有连接 Daniel、没有取任何数据。"


def gate(module_key, command_name):
    """这条命令要不要先登录？→ `None`（放行）或一个结构化判定 dict。

    **不判登录态**：只有不在白名单里才去读会话（白名单命令一次文件都不读，
    因此"未登录时能不能跑"这件事不受会话状态影响）。
    """
    if is_whitelisted(module_key, command_name):
        return None
    sess = local_session()
    if sess.get("hasToken"):
        return None
    cmd = "daniel %s %s" % (module_key, command_name)
    return {
        "kind": KIND_UNAUTHENTICATED,
        "exitCode": EXIT_USAGE,
        "authenticated": False,
        "module": module_key,
        "command": command_name,
        "message": (GATE_MESSAGE.format(cmd=cmd) + GATE_MESSAGE_TAIL),
        "hint": LOGIN_HINT,
        "fix": LOGIN_COMMAND,
        "reason": ("本机没有会话文件" if not sess.get("error") else
                   "读不到本机会话：%s" % sess.get("error")),
        "local": {"本机会话文件": sess.get("sessionFile"),
                  "本机有没有会话": bool(sess.get("hasToken"))},
        "docs": "跑 `daniel auth status` 看三态；跑 `daniel --help` 看未登录时哪些命令可用",
    }


def gate_error_payload(verdict):
    """给 `--json` 信封 `error.data` 的**机器可读**未登录结构（MCP 也读这一份）。"""
    return {
        "authenticated": False,
        "未登录": True,
        "kind": verdict["kind"],
        "module": verdict["module"],
        "command": verdict["command"],
        "reason": verdict["reason"],
        "fix": verdict["fix"],
        "next": "修好后重跑同一条命令；期间业务模块一律不放行（不是空数据）。",
    }


def help_lines():
    """`--help` 里的「授权是起点」段落（从 `WHITELIST` 派生，**不手写第二份清单**）。"""
    by_cat = {}
    for row in whitelist_rows():
        by_cat.setdefault(row["类别"], []).append(row["命令行"].replace("daniel ", ""))
    lines = [
        "授权是起点：**未登录时业务模块一律不放行**（退出码 2 ＋「请先登录」＋ 一行修法），"
        "不返回任何真实数据、不静默降级。",
        "",
        "第一次使用这样登录（账号密码**只在 Daniel 页面上**输入，CLI 绝不追问）：",
        "  ① daniel account login --browser --confirm   # 打开登录页并给出回读步骤",
        "  ② 在浏览器里完成登录                  # https://daniel-agent.com/auth",
        "  ③ 把浏览器里的会话粘回 CLI            # 先校验后落盘（$DANIEL_HOME/session/）",
        "  ④ daniel auth status                  # 0＝通过／1＝去登录／2＝服务端不可达",
        "无头／CI 可用环境变量 DANIEL_EMAIL／DANIEL_PASSWORD ＋ `daniel account login --confirm`"
        " —— **那是 CI 用的备用路，不是给人用的主路径**。",
        "",
        "未登录时**仍然可用**的命令（接入／自救／随包自检三类）：",
    ]
    for cat in ("接入", "自救", "随包自检", "其他"):
        if cat in by_cat:
            lines.append("  · %s：%s" % (cat, "、".join(by_cat[cat])))
    lines += [
        "  另有：`daniel --help`／`daniel --version`／`daniel <模块> <子命令> --help`（帮助与版本）。",
        "",
        "其余命令未登录时**一律 fail-fast**（退出码 2），完整分档见 `daniel schema --json`。",
    ]
    return lines


__all__ = ["KIND_UNAUTHENTICATED", "LOGIN_COMMAND", "LOGIN_HINT", "LOGIN_PAGE_PATH",
           "WHITELIST", "CATEGORY_LABELS", "is_whitelisted", "whitelist_reason",
           "whitelist_rows", "local_session", "verify_session", "status", "gate",
           "gate_error_payload", "help_lines", "STATUS_EXIT", "STATUS_NEXT",
           "VERIFY_OK", "VERIFY_REJECTED", "VERIFY_UNREACHABLE", "VERIFY_TIMEOUT"]
