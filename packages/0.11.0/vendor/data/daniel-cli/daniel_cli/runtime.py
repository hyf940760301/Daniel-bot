# -*- coding: utf-8 -*-
"""运行期公共件：能力目录定位、输出通道、上下文、子进程调用与 JSON 提取。

三条纪律在这里落地：
  ① **零 DSH 依赖**：本文件只用标准库，能力目录靠"从本包位置向上找 `.kol-tools`"或
     `DANIEL_CLI_TOOLS` 定位 —— 换宿主（MCP／别的模型／别的机器）不用改代码；
  ② **结果只走 stdout、进度只走 stderr**：`Emitter` 是唯一的输出口；
  ③ **不重写业务逻辑**：`run_instrument()` 直接跑 `.kol-tools/` 下既有仪器，`load_client()`
     直接用既有 `daniel_client`（含其跨工作区品牌解析与鉴权）。
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import time

from . import CLI_NAME, __version__
from .exits import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)                 # data/daniel-cli
_TOOLS_CACHE = {}
_MODULE_CACHE = {}


class CliError(Exception):
    """带退出码语义的受控错误。`kind` 决定退出码：usage → 2，internal → 1。"""

    def __init__(self, message, code=EXIT_USAGE, hint=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.hint = hint


# ─────────────────────────── 能力目录定位 ───────────────────────────
def _looks_like_tools(path):
    return bool(path) and os.path.isfile(os.path.join(path, "daniel_client.py"))


def tools_dir():
    """定位 `.kol-tools`（Daniel 能力脚本所在目录）。

    顺序：`DANIEL_CLI_TOOLS`（可给能力目录本身，也可给含 `.kol-tools` 的仓库根）
    → 从本包位置逐级向上找 `.kol-tools`（剥离后把本目录整体搬走也照样能用）。
    """
    if "tools" in _TOOLS_CACHE:
        return _TOOLS_CACHE["tools"]
    env = os.environ.get("DANIEL_CLI_TOOLS")
    cands = []
    if env:
        cands += [env, os.path.join(env, ".kol-tools")]
    up = _PKG_ROOT
    for _ in range(8):
        cands.append(os.path.join(up, ".kol-tools"))
        nxt = os.path.dirname(up)
        if nxt == up:
            break
        up = nxt
    for c in cands:
        c = os.path.abspath(os.path.expanduser(c))
        if _looks_like_tools(c):
            _TOOLS_CACHE["tools"] = c
            return c
    raise CliError("找不到 Daniel 能力目录（.kol-tools，需含 daniel_client.py）",
                   code=EXIT_INTERNAL,
                   hint="设置环境变量 DANIEL_CLI_TOOLS 指向能力目录或仓库根后重试；"
                        "查找起点：%s" % _PKG_ROOT)


def repo_root():
    """能力目录的上一级（仅用于把能力脚本里的默认相对路径换成绝对路径）。"""
    return os.path.dirname(tools_dir())


def load_capability(module_name):
    """按文件路径加载 `.kol-tools/` 下的既有模块（不重写、不复制业务逻辑）。"""
    if module_name in _MODULE_CACHE:
        return _MODULE_CACHE[module_name]
    path = os.path.join(tools_dir(), module_name + ".py")
    if not os.path.isfile(path):
        raise CliError("能力脚本缺失：%s" % path, code=EXIT_INTERNAL,
                       hint="该命令依赖既有仪器；请确认能力目录完整")
    spec = importlib.util.spec_from_file_location("daniel_cli_cap_" + module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    _MODULE_CACHE[module_name] = mod
    return mod


def load_client():
    """既有共享客户端（41 个脚本都在用它）。"""
    return load_capability("daniel_client")


def new_client(verbose=False):
    """建一个已登录的客户端；登录失败按"用户错误"处理（通常是凭据缺失）。"""
    dc = load_client()
    d = dc.Daniel(verbose=verbose)
    try:
        d.login()
    except SystemExit as e:                                            # 凭据缺失/登录被拒
        raise CliError(str(e) or "登录失败", code=EXIT_USAGE,
                       hint="检查凭据来源：daniel account credentials")
    return d


# ─────────────────────────── 输出通道 ───────────────────────────
_LABELS = {
    "id": "编号", "name": "名称", "title": "标题", "brandId": "品牌编号",
    "brandName": "品牌名", "workspaceId": "工作区编号", "workspaceName": "工作区",
    "status": "状态", "createdAt": "创建时间", "updatedAt": "更新时间",
    "listId": "名单编号", "channelId": "频道编号", "channelTitle": "频道名",
    "subscriberCount": "订阅数", "viewCount": "播放量", "videoCount": "视频数",
    "share": "份额", "score": "得分", "email": "邮箱", "query": "检索式",
    "jobId": "任务编号", "total": "总数", "page": "页码", "totalPages": "总页数",
    "days": "天数", "limit": "上限", "startDate": "开始日期", "endDate": "结束日期",
    "summary": "汇总", "source": "来源", "path": "路径", "exists": "是否存在",
    "categoryProfileId": "品类档案", "categoryId": "品类编号", "country": "市场",
    # 外层信封与自检报告用词（保持人读一致）
    "ok": "是否成功", "desc": "说明", "detail": "细节", "checks": "检查项",
    "commandCount": "命令数", "moduleCount": "模块数", "itemsFailed": "未通过项数",
    "items": "检查条目", "groups": "组数", "groupsPassed": "通过组数",
    "kind": "类型", "message": "消息", "hint": "建议", "error": "错误",
    "version": "版本", "module": "模块", "command": "命令", "readOnly": "是否只读",
    "exitCode": "退出码", "elapsedMs": "耗时(毫秒)", "route": "通路", "notes": "提示",
    "count": "条数", "returned": "返回条数", "brands": "品牌", "lists": "名单",
    "items_": "条目", "campaigns": "合作活动", "workspaces": "工作区",
    "requiresConfirm": "需要确认", "dryRun": "试运行", "executed": "是否已执行",
    "plan": "执行计划", "action": "动作", "keychain": "钥匙串", "env": "环境变量",
    "encrypted_first": "是否加密优先", "email_masked": "邮箱(掩码)", "home": "数据落点",
    "home_reason": "落点选择理由", "available": "可用性", "seconds": "耗时(秒)",
    "shape": "形状", "fields": "字段", "sample": "样本", "indexBuiltAt": "索引构建时间",
    "indexWorkspaceCount": "索引覆盖工作区数", "service": "服务名", "found": "是否找到",
    "usable": "是否可用", "enabled": "是否启用", "account_masked": "账号(掩码)",
    "activeWorkspaceId": "当前工作区编号", "isActive": "是否当前", "searches": "检索记录",
    "competitors": "竞品", "totalPages": "总页数", "progress": "进度",
    "brand": "品牌", "method": "请求方式", "note": "说明", "routes": "通路清单",
    "defaultInput": "默认入参", "probeSupportedInThisWorkOrder": "本工序可探测",
    "influencerCount": "红人数", "autoPriorityStatus": "自动优先级", "description": "简介",
    "campaignCode": "活动码", "campaignId": "活动编号", "subscriberCount": "订阅数",
}


def _fmt_scalar(v):
    if v is None:
        return "（空）"
    if v is True:
        return "是"
    if v is False:
        return "否"
    if isinstance(v, float):
        return ("%.4f" % v).rstrip("0").rstrip(".")
    return str(v)


def _label(k):
    return "%s（%s）" % (_LABELS[k], k) if k in _LABELS else k


def render_human(obj, indent=0, max_items=20):
    """把结构化结果渲染成给人看的中文文本（CLI 的默认输出；不打印内部通路名）。"""
    pad = "  " * indent
    if isinstance(obj, dict):
        lines = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and v:
                lines.append("%s%s：" % (pad, _label(k)))
                lines.append(render_human(v, indent + 1, max_items))
            else:
                lines.append("%s%s：%s" % (pad, _label(k), _fmt_scalar(v)))
        return "\n".join(lines)
    if isinstance(obj, list):
        if not obj:
            return pad + "（空）"
        lines = ["%s共 %d 条" % (pad, len(obj))]
        if isinstance(obj[0], dict):
            keys = list(obj[0].keys())[:6]
            for i, row in enumerate(obj[:max_items], 1):
                if isinstance(row, dict):
                    cells = " ｜ ".join("%s=%s" % (_label(k), _fmt_scalar(row.get(k))) for k in keys)
                else:
                    cells = _fmt_scalar(row)
                lines.append("%s  %d. %s" % (pad, i, cells))
        else:
            for i, row in enumerate(obj[:max_items], 1):
                lines.append("%s  %d. %s" % (pad, i, _fmt_scalar(row)))
        if len(obj) > max_items:
            lines.append("%s  …（另有 %d 条，用 --json 取全量）" % (pad, len(obj) - max_items))
        return "\n".join(lines)
    return pad + _fmt_scalar(obj)


class Emitter:
    """结果 → stdout；进度/提示/警告 → stderr。"""

    def __init__(self, json_mode=False, quiet=False, out=None, err=None):
        self.json_mode = json_mode
        self.quiet = quiet
        self.out = out or sys.stdout
        self.err = err or sys.stderr

    def progress(self, msg):
        if not self.quiet:
            print("· " + msg, file=self.err, flush=True)

    def note(self, msg):
        print("提示：" + msg, file=self.err, flush=True)

    def warn(self, msg):
        print("警告：" + msg, file=self.err, flush=True)

    def result(self, data=None, text=None, human=None, route=None, notes=None,
               ok=True, elapsed_ms=None, module=None, command=None, read_only=True,
               exit_code=EXIT_OK, read=None):
        if self.json_mode:
            payload = {"ok": bool(ok), "cli": CLI_NAME, "version": __version__,
                       "module": module, "command": command, "readOnly": bool(read_only),
                       "exitCode": exit_code}
            if elapsed_ms is not None:
                payload["elapsedMs"] = int(elapsed_ms)
            if data is not None:
                payload["data"] = data
            elif text is not None:
                payload["text"] = text
            if route:
                payload["route"] = route            # 调试字段：只在 JSON 里出现
            if read:
                payload["read"] = read              # 读链元信息：条数／分页游标／是否被收窄
            if notes:
                payload["notes"] = list(notes)
            print(json.dumps(payload, ensure_ascii=False, indent=1), file=self.out, flush=True)
            return
        if human is not None:
            print(human, file=self.out, flush=True)
            return
        if data is not None:
            print(render_human(data), file=self.out, flush=True)
            return
        if text is not None:
            print(text, file=self.out, flush=True)

    def error(self, message, code, kind, hint=None, module=None, command=None, data=None):
        """失败出口：`--json` 时 stdout 仍然**只有一个 JSON 文档**（不许再叠一份结果信封）。"""
        if self.json_mode:
            err = {"kind": kind, "message": message}
            if hint:
                err["hint"] = hint
            payload = {"ok": False, "cli": CLI_NAME, "version": __version__,
                       "module": module, "command": command, "exitCode": code}
            if data is not None:
                payload["data"] = data
            payload["error"] = err
            print(json.dumps(payload, ensure_ascii=False, indent=1), file=self.out, flush=True)
            return
        print("错误：" + message, file=self.err, flush=True)
        if hint:
            print("处理建议：" + hint, file=self.err, flush=True)


class Context:
    """一次调用的上下文：参数、模式开关、输出口、以及"要到哪儿取数"的便利方法。"""

    def __init__(self, args, emitter, module=None, command=None, read_only=True):
        self.args = args
        self.emitter = emitter
        self.json_mode = emitter.json_mode
        self.verbose = bool(getattr(args, "verbose", False))
        self.confirm = bool(getattr(args, "confirm", False))
        self.dry_run = bool(getattr(args, "dry_run", False))
        self.module = module
        self.command = command
        self.read_only = read_only
        self.notes = []
        self._t0 = time.time()

    # 参数取值
    def get(self, name, default=None):
        return getattr(self.args, name.lstrip("-").replace("-", "_"), default)

    def require(self, name, metavar=None):
        v = self.get(name)
        if v in (None, "", []):
            raise CliError("缺少必填参数 %s" % (metavar or name))
        return v

    # 输出
    def progress(self, msg):
        self.emitter.progress(msg)

    def warn(self, msg):
        self.emitter.warn(msg)
        self.notes.append(msg)

    def note(self, msg):
        self.emitter.note(msg)
        self.notes.append(msg)

    def emit(self, data=None, text=None, human=None, route=None, read=None):
        self.emitter.result(data=data, text=text, human=human, route=route,
                            notes=self.notes, elapsed_ms=(time.time() - self._t0) * 1000,
                            module=self.module, command=self.command,
                            read_only=self.read_only, read=read)

    def emit_raw(self, ok, exit_code, data=None, text=None, human=None, route=None):
        self.emitter.result(data=data, text=text, human=human, route=route, ok=ok,
                            notes=self.notes, elapsed_ms=(time.time() - self._t0) * 1000,
                            module=self.module, command=self.command,
                            read_only=self.read_only, exit_code=exit_code)


# ─────────────────────────── 复用既有仪器 ───────────────────────────
class InstrumentRun:
    def __init__(self, argv, returncode, stdout, stderr):
        self.argv = argv
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run_instrument(script_name, argv, timeout=1800):
    """跑 `.kol-tools/<script_name>`（读链命令一律只传只读开关）。"""
    script = os.path.join(tools_dir(), script_name)
    if not os.path.isfile(script):
        raise CliError("能力脚本缺失：%s" % script, code=EXIT_INTERNAL)
    argv = [str(a) for a in argv]
    try:
        p = subprocess.run([sys.executable, script] + argv,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise CliError("仪器执行超时（%s 秒）：%s" % (timeout, script_name), code=EXIT_INTERNAL,
                       hint="缩小参数范围（例如 --limit）后重试")
    return InstrumentRun([script_name] + argv, p.returncode, p.stdout, p.stderr)


def _salvage_container(text, start):
    """抢救被截断的 JSON 容器：从 `start` 处的 `{`/`[` 扫到文本末尾，

    以"容器内最后一个完整元素"为界补齐闭合符号，返回可解析的文本（不可抢救 → None）。
    必要性：既有仪器为了不刷屏会把 JSON 输出截到 12000 字符（`daniel_intel.py:459`），
    截断处的数组不是合法 JSON，直接 raw_decode 会失败、退化成"只拿到第一个元素"，
    对调用方是误导 —— 这里把它还原成"前 N 条完整记录"并标注被截断。
    """
    if not text or start >= len(text) or text[start] not in "[{":
        return None
    closer = "]" if text[start] == "[" else "}"
    depth, in_str, esc, last_boundary = 0, False, False, None
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return None                      # 本来就完整：不需要抢救
            if depth == 1:
                last_boundary = i
    if last_boundary is None:
        return None
    return text[start:last_boundary + 1] + closer


def extract_json_detailed(text):
    """取出结果 JSON，并标注是否**被截断后抢救**过。

    排序口径是"**跨度**"（起点到终点覆盖多少字符），不是"终点在文本里多靠后"：
    被截断的数组抢救后可能只覆盖到第 2 条，而它内部深处的某个嵌套列表起点更靠后、
    终点也更靠后 —— 按终点排就会把"结果本体"排成一段嵌套片段（实测踩过）。
    """
    if not text:
        return None, {"salvaged": False, "reason": "无输出"}
    dec = json.JSONDecoder()
    best = None
    for i, ch in enumerate(text):
        if ch not in "{[":
            continue
        try:
            obj, end = dec.raw_decode(text[i:])
            cand = (obj, end, False)          # end 是相对 text[i:] 的长度，即跨度
        except ValueError:
            repaired = _salvage_container(text, i)
            if repaired is None:
                continue
            try:
                obj = json.loads(repaired)
            except ValueError:
                continue
            cand = (obj, len(repaired), True)
        if best is None or cand[1] > best[1]:
            best = cand
    if best is None:
        return None, {"salvaged": False, "reason": "输出里没有可解析的 JSON"}
    obj, _span, salvaged = best
    if not salvaged:
        return obj, {"salvaged": False, "reason": "完整"}
    if isinstance(obj, list):
        how = "已还原前 %d 条完整记录" % len(obj)
    elif isinstance(obj, dict):
        how = "已还原其中 %d 个完整字段" % len(obj)
    else:
        how = "已还原可解析的部分"
    return obj, {"salvaged": True,
                 "reason": "仪器输出被截断（仪器自身有输出长度上限），%s" % how}


def extract_json(text):
    """兼容入口：只要结果对象。"""
    return extract_json_detailed(text)[0]


_KV_RE = re.compile(r"(?:^|\s)([A-Za-z][A-Za-z0-9_]*)=")


def parse_kv_output(text):
    """解析仪器"按 `键=值` 打印"的输出（例如提及任务的进度行）。

    为什么单独有这一条：`daniel_mentions.py --status` 打的是
    `brandId=… status=done` / `progress=100% · Complete` / `resultSummary={…}` 这种行，
    里面只有 `resultSummary` 是 JSON —— 直接用 JSON 提取会把结果缩成"只剩汇总"，
    丢掉任务号与进度。这里按键切分，值本身是 JSON 就地解析。
    """
    if not text:
        return {}
    marks = list(_KV_RE.finditer(text))
    out = {}
    for n, m in enumerate(marks):
        key = m.group(1)
        start = m.end()
        end = marks[n + 1].start() if n + 1 < len(marks) else len(text)
        chunk = text[start:end]
        line_end = chunk.find("\n")
        value = (chunk[:line_end] if line_end != -1 else chunk).strip()
        if not value:
            continue
        if value[:1] in "{[":
            try:
                value = json.loads(value)
            except ValueError:
                pass
        out[key] = value
    return out


#: 仪器把"用户入参不合法"写成什么样（各仪器同口径）。用于**错误归类**，不含任何业务判据。
_USER_ERROR_PREFIXES = ("入参不合法：", "ParamError: ", "ValueError: ")


def instrument_error_class(run):
    """仪器这次失败属于哪一类？→ `(是否用户错误, 人话消息)`。

    判据（只是错误归类）：
      · 仪器以退出码 2 退出（本仓口径 2＝用户错误），或
      · stderr 末尾是参数类异常（`入参不合法：…`／`ParamError: …`／`ValueError: …`）——
        兼容还没归一退出码的旧仪器。
    其余（网络、500、解析失败）→ 内部故障。
    """
    lines = [ln.strip() for ln in (run.stderr or "").strip().splitlines() if ln.strip()]
    last = lines[-1] if lines else ""
    for pre in _USER_ERROR_PREFIXES:
        if last.startswith(pre):
            return True, last[len(pre):].strip()
    if run.returncode == EXIT_USAGE:
        return True, last
    return False, last


def _relay_instrument_stderr(ctx, run, skip_last=False):
    """把仪器的 stderr 转成进度提示（`skip_last` 用于"最后一行是要报给用户的错误"时）。"""
    lines = [ln for ln in (run.stderr or "").strip().splitlines() if ln.strip()]
    if skip_last and lines:
        lines = lines[:-1]
    for line in lines:
        ctx.emitter.progress(line)


def _finish_instrument_failure(ctx, script_name, run, data=None):
    """仪器非零退出 → 统一收口：用户错误报 2 ＋ 人话；真故障报 1（带原始尾行）。"""
    is_user, msg = instrument_error_class(run)
    _relay_instrument_stderr(ctx, run, skip_last=is_user)
    if is_user:
        ctx.emitter.error(msg or "入参不被接受", EXIT_USAGE, "usage",
                          hint="参数取值范围见该子命令的 --help（`daniel %s %s --help`）；"
                               "本次没有发起任何写操作" % (ctx.module or "<模块>", ctx.command or "<子命令>"),
                          module=ctx.module, command=ctx.command,
                          data=data if data is not None else None)
        return EXIT_USAGE
    tail = (run.stderr or run.stdout or "").strip().splitlines()
    m = "仪器 %s 执行失败（退出码 %d）" % (script_name, run.returncode)
    if tail:
        m += "：" + tail[-1]
    if ctx.notes:
        # 把"我是怎么判的"一起带上：例如本地预检发现"任务清单已触上限 ⇒ 不能断定编号不存在"。
        m += "；" + "；".join(str(n) for n in ctx.notes)
    ctx.emitter.error(m, EXIT_INTERNAL, "internal", module=ctx.module, command=ctx.command,
                      data=data if data is not None else None)
    return EXIT_INTERNAL


def use_instrument(ctx, script_name, argv, route=None, timeout=1800, kv_output=False):
    """跑一条既有仪器读链并把结果交回 CLI 输出通道。

    约定：仪器的 stdout 能结构化 → 结果就是结构化数据（截断的话标注出来）；
    结构化不了 → 原样作为文本结果（仪器的中文输出本身就是给人看的结果）。
    `kv_output=True` 用于"仪器按 `键=值` 逐行打印"的场景（见 `parse_kv_output`）。
    失败：**入参不合法 → 退出码 2（用户错误）**；真故障 → 退出码 1（内部错误）。
    """
    run = run_instrument(script_name, argv, timeout=timeout)
    data, meta = extract_json_detailed(run.stdout)
    if kv_output:
        kv = parse_kv_output(run.stdout)
        if len(kv) >= 3:                       # 键值行够多才认为"这就是结果本体"
            data, meta = kv, {"salvaged": False, "reason": "按键值行解析"}
    ok = run.returncode == 0
    if not ok:
        return _finish_instrument_failure(ctx, script_name, run, data=data)
    _relay_instrument_stderr(ctx, run)
    if meta.get("salvaged"):
        ctx.note(meta["reason"])
    if data is not None:
        ctx.emit(data=data, route=route)
    else:
        body = run.stdout.strip()
        ctx.emit(text=body, human=body, route=route)
    return EXIT_OK


#: 既有仪器（`.kol-tools/daniel_intel.py`／`daniel_mentions.py`）读结果信封的版本号。
# 口径：仪器 `--json` 时 stdout 有且只有一个 JSON 文档，字段固定为
# `schema／route／method／input／total／returned／result／paging／truncated／truncatedReason`。
READ_SCHEMA = "daniel.read.v1"


def split_read_envelope(obj):
    """把仪器的读结果信封拆成 `(业务载荷, 读链元信息)`；不是信封 → `(obj, None)`。

    为什么要拆（TICKET-150）：CLI 外层信封里的 `data` 一直是**业务载荷**（人读渲染与 MCP 宿主
    都按这个口径消费），而分页游标／截断标注是**读链元信息**。拆开之后两边都不破：
    `data` 仍是原样的业务数据，`read` 里带条数、游标与"是否被收窄"。
    """
    if isinstance(obj, dict) and obj.get("schema") == READ_SCHEMA and "result" in obj:
        meta = {k: v for k, v in obj.items() if k in ("schema", "route", "method", "filter",
                                                      "total", "returned", "paging", "truncated",
                                                      "truncatedReason", "notes")}
        return obj.get("result"), meta
    return obj, None


def read_instrument(ctx, script_name, argv, route=None, timeout=1800, shape=None):
    """跑既有仪器的**结构化读链**：`data` ＝业务载荷，`read` ＝读链元信息（条数／游标／截断）。

    兼容两代仪器，换宿主（MCP／别的模型／别的机器）都不用改代码：
      · 新仪器（`--json` 出 `daniel.read.v1` 信封）：拆信封，分页游标进 `read.paging`；
      · 旧仪器（只打 JSON 或只打中文文本）：与 `use_instrument` 同口径（含"被截断后抢救"的标注）。
    **不静默截断**：仪器标注了收窄（`truncated`）就同时写进 stderr 提示与 JSON 的 `read.*`。

    `shape`：把业务载荷翻成**业务语言**的纯函数（`payload -> data`），可选。
    为什么要留这个钩子：取数与批量上限的单一真源在仪器里（不能搬走），而"交给调用方的字段名"
    属于显示口径（`performanceDist`／`subscriberCount` 这类内部名不该原样外露）。于是**取数在
    仪器、取名在本层**：`read` 元信息仍按原始载荷算（条数／游标不被整形影响），只有 `data` 换名字。
    整形函数抛错按内部错误处理 —— 不能让"整形失败"被误读成"数据为空"。
    """
    run = run_instrument(script_name, argv, timeout=timeout)
    data, meta = extract_json_detailed(run.stdout)
    payload, read_meta = split_read_envelope(data)
    ok = run.returncode == 0
    if not ok:
        return _finish_instrument_failure(ctx, script_name, run, data=data)
    _relay_instrument_stderr(ctx, run)
    if read_meta is not None:
        if read_meta.get("truncated"):
            note = (read_meta.get("truncatedReason")
                    or "结果被收窄（详见 JSON 的 read.truncatedReason）")
            how = (read_meta.get("paging") or {}).get("howToContinue")
            ctx.note("%s；%s" % (note, how) if how else note)
    elif meta.get("salvaged"):
        ctx.note(meta["reason"])
    if data is not None:
        if shape is not None:
            try:
                payload = shape(payload)
            except CliError:
                raise
            except Exception as e:                                     # noqa: BLE001
                raise CliError("读取成功，但把结果整理成业务字段时出错：%s" % str(e)[:200],
                               code=EXIT_INTERNAL,
                               hint="原始载荷仍可从 `daniel <模块> <子命令> --json` 的同一条读链取；"
                                    "这是一次显示层故障，不是数据为空")
        ctx.emit(data=payload, route=route, read=read_meta)
    else:
        body = run.stdout.strip()
        ctx.emit(text=body, human=body, route=route)
    return EXIT_OK


def parse_json_arg(raw, what="--input"):
    if raw in (None, ""):
        return None
    try:
        return json.loads(raw)
    except ValueError as e:
        raise CliError("%s 不是合法 JSON：%s" % (what, e))
