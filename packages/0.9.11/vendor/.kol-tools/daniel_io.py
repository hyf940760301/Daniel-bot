#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daniel_io.py —— 仪器侧 `--json` 出口的**唯一**收口层（TICKET-168）。

要解决的问题（缺陷类 `CLS-81` 第二形）
--------------------------------------
`data/daniel-cli/contracts/read-envelope.md` 定了契约：`--json` 时 **stdout 有且只有一个
JSON 文档**，退出码 `0 成功／1 内部错误／2 用户错误／3 需确认`。CLI 侧已收口，但**仪器直跑**
时仍有两处漏网：

  ① 读请求失败后，仪器把中文错误行打到 **stdout** 并以 **exit 0** 结束
     ⇒ 调用方（人／模型／宿主）会把错误文字**当成成功数据**；
  ② 真故障时 stdout **为空**、只有 stderr 的 traceback
     ⇒ 有退出码、但**没有机器可读面**。

本模块把这两件事收在**一个地方**：所有仪器都从自己的入口函数 `cli()` 转调
`daniel_io.cli(main, ...)`，失败出口、退出码归一、单文档保证都在这里实现
（**逐命令重复 catch 不算收口**）。

对外只承诺三件事
----------------
1. 失败时 `--json` 的 stdout **恰好一个** `{"ok": false, …, "error": {…}}` 文档；
   错误文字**不走 stdout**（人读模式走 stderr，真故障的 traceback 照旧打到 stderr）。
2. 退出码按表：入参类 4xx（400／422）与本地入参校验 → 2；真故障（5xx／不可达／解析失败／
   404 等"本地断不了"的情形）→ 1；成功 0；写链需确认 3。
3. stdout 上的 JSON 文档数**用 `raw_decode` 真数**：已经出过文档就**绝不再补一份**
   （补第二份正是"上层把错误当成成功"的病根）。

不做什么
--------
不含任何业务判据；不碰网络；不改调用方的入参；不重写各仪器的人读输出。

用法（各仪器入口照抄）
----------------------
    from daniel_io import cli as _cli_entry, ParamError      # 同一目录，脚本直跑时 sys.path[0] 即本目录

    def cli(argv=None):
        return _cli_entry(main, argv, usage_errors=(ParamError,))

    if __name__ == "__main__":
        sys.exit(cli())
"""
import json
import os
import sys
import traceback

#: 失败信封的版本号（与成功侧的 `daniel.read.v1` 并列；字段变化时要改这里）。
ERROR_SCHEMA = "daniel.error.v1"

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_CONFIRM = 3

#: 服务端 4xx 里**属于"本次入参不合法"**的状态码。只认这两个：400「请求本身不合法」与
#: 422「语义校验不过」。401／403（凭据与权限）与 404（对象不存在／不可见）**不算**用户错误
#: —— 本地断不了，按真故障报 1（与 CLI 侧 `runtime.py` 的归类一致）。
USAGE_STATUSES = (400, 422)

#: zod 校验码 → 中文说法（只做措辞，不改判据）。服务端返回的 `code` 原样出现在这里才算命中。
ZOD_TEXT = {
    "too_big": "超出上限",
    "too_small": "低于下限",
    "invalid_type": "类型不对",
    "invalid_enum_value": "取值不在允许范围",
    "invalid_literal": "取值不对",
    "invalid_string": "格式不对",
    "invalid_union": "取值不匹配任何允许的形状",
    "unrecognized_keys": "多了服务端不认识的字段",
    "invalid_date": "日期不合法",
    "not_multiple_of": "不是允许的倍数",
    "required": "缺少必填字段",
}

#: 服务端字段名 → 业务说法（写给人看的那句话里不出现内部字段名）。
FIELD_LABEL = {
    "pageSize": "每页条数",
    "page": "页码",
    "limit": "条数上限",
    "offset": "起始位置",
    "days": "回溯天数",
    "brandId": "品牌编号",
    "jobId": "任务编号",
    "actionId": "动作编号",
    "reviewId": "审核编号",
    "memoId": "备忘编号",
    "keywordId": "关键词编号",
    "maxVideos": "最多分析条数",
    "regionCode": "市场",
    "searchMode": "检索方式",
}

#: 服务端字段名 → 本机命令行开关（hint 里让人知道"该改哪个参数"）。
FIELD_FLAG = {
    "pageSize": "--page-size",
    "page": "--page",
    "limit": "--limit",
    "offset": "--offset",
    "days": "--days",
    "brandId": "--brand",
    "jobId": "--job",
    "maxVideos": "--max-videos",
    "regionCode": "--region",
}


class ParamError(ValueError):
    """本地入参校验不过（越界／错枚举／缺键／对象多义）⇒ 用户错误（退出码 2）。

    各仪器可以有自己的 `ParamError` 同名类；把它的类传给 `cli(usage_errors=(...,))` 即可，
    不必改继承关系。
    """


class ServerError(Exception):
    """服务端**真实**回执（原始 HTTP 状态码 ＋ 原始错误体）⇒ 由本模块归成 2 或 1。

    为什么需要它：`daniel_client.query()` 会把异常压成一行 `RuntimeError`，状态码与错误体
    都在那一步丢了。仪器在失败后补打一次原始请求（`raw_request`／`raw_call`）拿到真回执，
    再用本异常把**真回执**交给出口层——退出码与"人话"都从这里来，不靠猜。
    """

    def __init__(self, route, status, body="", message=None, cause=None):
        self.route = route
        self.status = status
        self.body = body or ""
        self.cause = cause
        self.message = message
        super().__init__(message or "%s 失败: HTTP %s" % (route, status))


# ---------------------------------------------------------------- 服务端错误的读法与措辞
def _walk(obj):
    yield obj
    if isinstance(obj, dict):
        for v in obj.values():
            for x in _walk(v):
                yield x
    elif isinstance(obj, list):
        for v in obj:
            for x in _walk(v):
                yield x


def validation_issues(body):
    """从服务端错误体里挖出**它自己写的**校验问题（`{path, code, maximum, message}`）。

    只认服务端给的结构：tRPC 把 zod 的问题数组塞在 `error.json.message` 这个**字符串**里
    （字符串内容本身又是一段 JSON）。挖不到就返回空列表——**不猜**，让上层退回通用措辞。
    """
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return []
    out, seen = [], set()
    for node in _walk(parsed):
        if not isinstance(node, dict):
            continue
        cands = []
        if "path" in node and ("code" in node or "message" in node):
            cands.append(node)
        msg = node.get("message")
        if isinstance(msg, str) and msg.lstrip()[:1] in "[{":
            try:
                inner = json.loads(msg)
            except ValueError:
                inner = None
            for it in (inner if isinstance(inner, list) else [inner]):
                if isinstance(it, dict) and ("path" in it or "code" in it):
                    cands.append(it)
        for it in cands:
            key = (str(it.get("code")), tuple(it.get("path") or []), str(it.get("maximum")),
                   str(it.get("minimum")), str(it.get("message"))[:80])
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
    return out


def _field_of(issue):
    p = issue.get("path")
    if isinstance(p, list) and p:
        return str(p[-1])
    if isinstance(p, str) and p:
        return p
    return None


def describe_validation(issues):
    """把服务端校验问题写成两句人话：`(message, hint)`。写不出就给 `(None, None)`。"""
    if not issues:
        return None, None
    it = issues[0]
    field = _field_of(it)
    code = str(it.get("code") or "")
    label = FIELD_LABEL.get(field, field or "该字段")
    flag = FIELD_FLAG.get(field)
    raw = it.get("message")
    raw = raw if isinstance(raw, str) else None

    if field == "pageSize" and code == "too_big" and isinstance(it.get("maximum"), int):
        msg = "入参不被接受：该接口每页最多 %d 条。" % it["maximum"]
        hint = "把 %s 调到 %d 以内再试" % (flag or "每页条数", it["maximum"])
    elif code == "too_big" and isinstance(it.get("maximum"), int):
        msg = "入参不被接受：%s 超出上限（最多 %s）。" % (label, it["maximum"])
        hint = "把 %s 调到 %s 以内再试" % (flag or label, it["maximum"])
    elif code == "too_small" and isinstance(it.get("minimum"), int):
        msg = "入参不被接受：%s 低于下限（最少 %s）。" % (label, it["minimum"])
        hint = "把 %s 调到 %s 以上再试" % (flag or label, it["minimum"])
    elif code in ZOD_TEXT and field:
        msg = "入参不被接受：%s%s。" % (label, ZOD_TEXT[code])
        hint = ("检查 %s 的取值" % (flag or label)) if flag else "检查这次给的入参"
    elif raw:
        msg = "入参不被接受：%s。" % raw
        hint = None
    else:
        return None, None

    if raw:
        hint = ("%s（服务端原话：%s）" % (hint, raw)) if hint else "服务端原话：%s" % raw
    hint = ("%s；本次没有发起任何写操作。" % hint) if hint else "本次没有发起任何写操作。"
    return msg, hint


def server_error_kind(status, body=""):
    """服务端回执属于哪一类？→ `"usage"`（用户错误，2）／`"internal"`（真故障，1）。"""
    return "usage" if int(status or 0) in USAGE_STATUSES else "internal"


def _body_note(body, limit=300):
    """服务端原话的短摘要（进 `error.hint`，用于排障；**不**占 stdout、也不淹掉 stderr）。"""
    txt = " ".join(str(body or "").split())
    if not txt:
        return ""
    return "服务端原话：%s" % (txt[:limit] + "…" if len(txt) > limit else txt)


def describe_server_error(route, status, body="", cause=None):
    """服务端失败 → `(kind, message, hint)`，全部是人话。

    为什么把"服务端原话"放进 `hint` 而不是打到 stderr：`--json` 的契约要求 stdout 只有一个
    文档，stderr 又要能一眼看到失败原因。把原始报文塞进 JSON 的 `error.hint`，两个目标同时满足，
    排障信息也**没有丢**。
    """
    kind = server_error_kind(status, body)
    note = _body_note(body)
    if kind == "usage":
        msg, hint = describe_validation(validation_issues(body))
        if msg:
            return kind, msg, hint
        return (kind,
                "入参不被接受：服务端拒绝了这次请求（HTTP %s）。" % status,
                "按 --help 给出的取值范围核对入参；本次没有发起任何写操作。")
    if status in (401, 403):
        return (kind,
                "这次查询没有通过身份校验（HTTP %s）：当前登录态对该对象不可见。" % status,
                "重新登录或换一个有权限的账号；这不是参数格式问题。")
    if status == 404:
        return (kind,
                "服务端查不到要查的对象（HTTP 404）。",
                "请核对编号是否存在、以及当前账号是否对它可见；这不是参数格式问题。")
    if status and int(status) >= 500:
        return (kind,
                "服务端内部错误（HTTP %s），本次没有拿到数据。" % status,
                ("稍后重试；若持续出现，请把当时的入参报给维护方。" + ("　" + note if note else "")))
    return (kind,
            "服务端拒绝了这次请求（HTTP %s）。" % status,
            note or "原始报错见 stderr。")


def _status_from_text(text):
    """从异常文本里认服务端状态码（`daniel_client` 会把真回执压进一行 `… 失败: HTTP Error 400: …`）。

    为什么需要：不是所有仪器都在失败后补打原始请求（`ServerError` 那条路），有的只把
    `RuntimeError` 往上抛，状态码只剩在这行文字里。**入参类 400／422 → 用户错误（2）**
    这条判据不能因为拿不到对象就丢掉。
    """
    import re as _re
    m = _re.search(r"\bHTTP Error\s+(\d{3})\b", str(text or ""))
    return int(m.group(1)) if m else None


def humanize_exception(exc):
    """非服务端异常 → `(kind, message, hint)`。做的是**措辞**，不改判据。"""
    if isinstance(exc, ServerError):
        return describe_server_error(exc.route, exc.status, exc.body, exc.cause)
    text = str(exc) or type(exc).__name__
    low = text.lower()
    st = _status_from_text(text)
    if st in USAGE_STATUSES:
        # 状态码只存活在文字里时也照"入参类 4xx → 2"归类（措辞走同一套）。
        return describe_server_error(None, st, "", exc)
    if st == 404 or ("not found" in low and "404" in low):
        return ("internal", "服务端查不到要查的对象（HTTP 404）。",
                "请核对编号是否存在、以及当前账号是否对它可见；这不是参数格式问题。")
    if st in (401, 403) or "unauthorized" in low:
        return ("internal",
                "这次查询没有通过身份校验（HTTP %s）：登录态已失效或对该对象无权限。"
                % (st or "401/403"),
                "重新登录后重试；这不是参数格式问题。")
    if st and st >= 500:
        return ("internal", "服务端内部错误（HTTP %s），本次没有拿到数据。" % st,
                "稍后重试；若持续出现，请把当时的入参报给维护方。")
    if "unreachable" in low or "connection refused" in low or "timed out" in low \
            or "timeout" in low or "temporary failure in name resolution" in low \
            or "getaddrinfo" in low or "urlopen error" in low:
        return ("internal", "连不上服务端：网络不可达或超时。",
                "检查网络与 DANIEL_BASE_URL 指向的地址；本次没有拿到任何数据。")
    if isinstance(exc, ValueError) and "json" in low:
        return ("internal", "服务端返回的内容解析不了（不是合法 JSON）。",
                "可能是服务端异常或被中间层改写；原始报错见 stderr。")
    return ("internal", text, "原始报错见 stderr；本次没有发起任何写操作。")


# ---------------------------------------------------------------- 信封与出口
def default_exit_code(kind):
    return {"usage": EXIT_USAGE, "confirm": EXIT_CONFIRM}.get(kind, EXIT_INTERNAL)


def error_document(kind, message, hint=None, route=None, exit_code=None):
    """失败信封（机器可读面）。字段顺序固定，便于逐字比对。"""
    doc = {"ok": False, "schema": ERROR_SCHEMA}
    if route:
        doc["route"] = route
    doc["exitCode"] = default_exit_code(kind) if exit_code is None else exit_code
    doc["error"] = {"kind": kind, "message": message}
    if hint:
        doc["error"]["hint"] = hint
    return doc


#: 一次调用内的出口状态（`emit` 与 `cli` 共用；模块级单进程单次调用，够用）。
_STATE = {"json_mode": False, "emitted": 0, "out": None, "docs": None, "notes": []}


def _out():
    return _STATE.get("out") or sys.stdout


def emit(obj, indent=1):
    """成功出口：往 stdout 打**恰好一个** JSON 文档并记账。

    仪器里凡是"`--json` 时出 JSON"的地方都应改成调它（而不是自己 `print(json.dumps(...))`），
    这样出口层才知道"已经出过文档、失败时不得再补一份"。
    """
    text = json.dumps(obj, ensure_ascii=False, indent=indent)
    out = _out()
    out.write(text + "\n")
    try:
        out.flush()
    except Exception:  # noqa: BLE001
        pass
    _STATE["emitted"] = _STATE.get("emitted", 0) + 1
    return text


def document_count():
    """本次调用 stdout 上**真实**写了几个 JSON 文档（由出口层的计数器给出）。"""
    return _STATE.get("docs").count if _STATE.get("docs") is not None else _STATE.get("emitted", 0)


def notes():
    """出口层记下的契约提醒（自检用；正常路径为空）。"""
    return list(_STATE.get("notes") or [])


class _DocCounter:
    """stdout 计数代理：写透给真实 stdout（**不缓冲、不改时序**），同时用 `raw_decode`
    数清楚地写了几份 JSON 文档。"""

    #: 万一遇到永远解析不出来的残留（有人在 json 模式里打二进制/日志），到此为止不再缓存。
    MAX_BUF = 16 * 1024 * 1024

    def __init__(self, real):
        self._real = real
        self._buf = ""
        self._dec = json.JSONDecoder()
        self.count = 0

    def write(self, s):
        n = self._real.write(s)
        if isinstance(s, str):
            self._ingest(s)
        return n

    def _ingest(self, s):
        self._buf += s
        while True:
            t = self._buf.lstrip(" \t\r\n")
            if not t:
                self._buf = ""
                return
            if t[0] not in "{[":
                self._buf = t
                break
            try:
                _obj, end = self._dec.raw_decode(t)
            except ValueError:
                self._buf = t
                break
            self.count += 1
            self._buf = t[end:]
        if len(self._buf) > self.MAX_BUF:
            self._buf = ""

    def flush(self):
        return self._real.flush()

    def __getattr__(self, name):
        return getattr(self._real, name)


class _LineTee:
    """stderr 记录器：写透给真实 stderr，同时记住最后几行非空内容（用于"没有显式消息时"兜底）。"""

    KEEP = 12

    def __init__(self, real):
        self._real = real
        self.lines = []

    def write(self, s):
        n = self._real.write(s)
        if isinstance(s, str):
            for ln in s.splitlines():
                if ln.strip():
                    self.lines.append(ln.strip())
            del self.lines[:-self.KEEP]
        return n

    def flush(self):
        return self._real.flush()

    def __getattr__(self, name):
        return getattr(self._real, name)

    def tail(self):
        return self.lines[-1] if self.lines else ""


def _tidy(text):
    """把仪器写在 stderr 上的一句话整理成可当 `error.message` 用的样子。

    只做两件事：去掉首尾空白；`KeyError`／`ValueError` 抛出来的那句话常自带一层引号
    （`'未知 kind: nope'`），把它剥掉——给人看的字段里不该出现代码级的引号。
    """
    t = (text or "").strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        t = t[1:-1].strip()
    return t


def _print_err(text):
    try:
        sys.stderr.write(text + "\n")
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass


def _finish_failure(json_mode, kind, message, hint=None, route=None, exit_code=None,
                    trace_text=None):
    """失败统一出口。

    规矩（TICKET-168 验收第 1 条 ＋ 契约 §5）：
      · `--json`：stdout **恰好一个**失败信封（`ok=false` ＋ `error{kind,message,hint}`）；
        此时 stderr **只留一句人话**（就是 `message`）—— 原始报文转储与建议都收进 JSON 的
        `error.hint`，不在 stderr 上再堆一份人读错误文字。已经出过文档就**绝不补第二份**
        （那正是"上层把错误当成成功"的病根），改为只写 stderr。
      · 人读：错误文字走 **stderr**，stdout 一个字都不加（免得被当成数据）。
      · 真故障的 traceback 照旧打到 stderr（**要看得见**），并**排在最后一句人话之前** ——
        这样上游按"stderr 末行"取失败理由时拿到的是人话，而不是异常类名。
    """
    code = default_exit_code(kind) if exit_code is None else exit_code
    if trace_text:
        _print_err(trace_text.rstrip())
    if json_mode:
        if document_count() == 0:
            emit(error_document(kind, message, hint, route=route, exit_code=code))
        else:
            _STATE["notes"].append(
                "stdout 已经出过 JSON 文档，失败信封不再补第二份（错误文字改走 stderr）")
        # 仪器自己可能已经把同一句话写到 stderr（如"已经 print 过再 return 2"）—— 不重复一份。
        tee = sys.stderr
        if not (isinstance(tee, _LineTee) and _tidy(tee.tail()) == message):
            _print_err(message)
    else:
        _print_err("错误：" + message)
        if hint:
            _print_err("处理建议：" + hint)
    return code


# ---------------------------------------------------------------- 入口包装
def cli(main, argv=None, json_mode=None, usage_errors=(), confirm_codes=(EXIT_CONFIRM,)):
    """仪器入口包装：**退出码归一 ＋ 失败时恰好一个 JSON 文档**（收口就在这一个地方）。

    参数
    ----
    main          仪器的 `main(argv)`；返回值当作退出码（`None` 视作 0）。
    argv          原始参数表；默认 `sys.argv[1:]`（`main` 会被原样喂这份）。
    json_mode     是否机器可读模式；`None` ＝ 按 `--json` 是否出现在 argv 里自动判。
    usage_errors  该仪器自己的"本地入参错"异常类（如它的 `ParamError`）。
    confirm_codes 视为"需确认"的退出码（写链干跑 3）。

    退出码表
    --------
    0 成功 ｜ 2 用户错误（本地入参校验／SystemExit("人话")／argparse 参数错／服务端 400·422）
    ｜ 1 内部错误（5xx／不可达／解析失败／404 等本地断不了的情形）｜ 3 需确认
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if json_mode is None:
        json_mode = "--json" in argv

    errtee = _LineTee(sys.stderr)
    sys.stderr = errtee
    _STATE["out"] = None
    _STATE["docs"] = None
    _STATE["emitted"] = 0
    _STATE["notes"] = []
    _STATE["json_mode"] = bool(json_mode)
    if json_mode:
        # 🔴 必须把代理挂到 `sys.stdout` 上：仪器里大量地方是裸 `print(...)`（不走 emit），
        # 只有挂上去，出口层才**真的**知道"已经出过几个文档"，失败时才能保证不补第二份。
        guard = _DocCounter(sys.stdout)
        sys.stdout = guard
        _STATE["out"] = guard
        _STATE["docs"] = guard

    try:
        rc = main(argv)
        rc = 0 if rc is None else int(rc)
    except KeyboardInterrupt:
        return _finish_failure(json_mode, "internal", "本次调用被中断（Ctrl-C），没有拿到数据。",
                               "重跑一次；本次没有发起任何写操作。", exit_code=EXIT_INTERNAL)
    except SystemExit as e:                                    # argparse 与 `SystemExit("人话")`
        code = e.code
        if isinstance(code, int) and not isinstance(code, bool):
            if code == EXIT_OK:
                return EXIT_OK
            if code == EXIT_USAGE:
                last = errtee.tail()
                return _finish_failure(json_mode, "usage",
                                       "入参不被接受：%s" % (last or "参数不符合要求。"),
                                       "按 `--help` 核对取值范围与必填项；本次没有发起任何写操作。",
                                       exit_code=EXIT_USAGE)
            if code in confirm_codes:
                return _finish_failure(json_mode, "confirm",
                                       "这一步有写副作用，需要明确确认后才执行。",
                                       "确认无误后加 `--confirm`（或 `--run`）再跑一次。",
                                       exit_code=int(code))
            return _finish_failure(json_mode, "internal",
                                   "仪器以退出码 %s 结束，没有拿到数据。" % code,
                                   "原始报错见 stderr。", exit_code=int(code))
        text = str(code).strip() if code else ""
        return _finish_failure(json_mode, "usage", text or "入参不被接受。",
                               "按 `--help` 核对取值范围与必填项；本次没有发起任何写操作。",
                               exit_code=EXIT_USAGE)
    except usage_errors as e:
        return _finish_failure(json_mode, "usage", "入参不合法：%s" % e,
                               "按 `--help` 核对取值范围与必填项；本次没有发起任何写操作。",
                               exit_code=EXIT_USAGE)
    except ParamError as e:
        return _finish_failure(json_mode, "usage", "入参不合法：%s" % e,
                               "按 `--help` 核对取值范围与必填项；本次没有发起任何写操作。",
                               exit_code=EXIT_USAGE)
    except ServerError as e:
        kind, message, hint = describe_server_error(e.route, e.status, e.body, e.cause)
        return _finish_failure(json_mode, kind, message, hint, route=e.route)
    except Exception as e:                                     # noqa: BLE001  真故障要看得见
        kind, message, hint = humanize_exception(e)
        return _finish_failure(json_mode, kind, message, hint,
                               trace_text=traceback.format_exc())

    if rc == EXIT_OK:
        if json_mode:
            n = document_count()
            if n != 1:
                _print_err("契约提醒：`--json` 模式下 stdout 应有且只有一个 JSON 文档，"
                           "实测 %d 个。" % n)
                _STATE["notes"].append("success_docs=%d" % n)
        return EXIT_OK

    # `main()` **直接返回**非零（而不是抛异常）时同样要有机器可读面。
    kind = "usage" if rc == EXIT_USAGE else "confirm" if rc in confirm_codes else "internal"
    message = _tidy(errtee.tail()) or "仪器以退出码 %s 结束，没有拿到数据。" % rc
    hint = {"usage": "按 `--help` 核对取值范围与必填项；本次没有发起任何写操作。",
            "confirm": "确认无误后加 `--confirm`（或 `--run`）再跑一次。",
            "internal": "原始报错见 stderr。"}[kind]
    return _finish_failure(json_mode, kind, message, hint, exit_code=rc)


def wrap_main(main, argv=None, **kw):
    """`cli()` 的别名，便于仪器里写成 `return daniel_io.wrap_main(main, argv, …)`。"""
    return cli(main, argv, **kw)
