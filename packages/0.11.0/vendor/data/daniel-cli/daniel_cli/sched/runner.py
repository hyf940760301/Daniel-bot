# -*- coding: utf-8 -*-
"""调度层的**执行器**：把一份任务规格跑成"可续、可重试、终态分明"的一次运行（TICKET-181）。

一次运行（每一步都为续跑留证据）
--------------------------------
    ① 校验规格  —— 步骤动作、命令白名单（**只读**）、地址白名单（**默认只允许回环**）
    ② 载入检查点 —— 有状态文件就从中断点续跑；没有就按全新任务跑（**不报错**）
    ③ 逐步骤    —— 队列准入 → 取数／调用命令 → 429／5xx 按退避重试 → 定终态 → **立刻落盘**
    ④ 汇总      —— 按规格顺序（不是完成顺序）算**结果指纹**，到达终态时落结果文件
    ⑤ 报告      —— 任务状态／进度／逐步明细／终态；非成功终态一律非零退出

三条纪律
--------
  · **不重跑已完成的取数**：步骤记了"成功 ＋ 结果指纹"，且指纹与存档结果对得上 → 跳过；
    对不上（存档被改／缺字段）→ 视为未完成，重跑（宁可多跑一次，不可拿对不上的旧结果当结论）；
  · **重试幂等**：步骤记录按 `id` 覆盖，汇总按规格顺序算 —— 同一份规格跑 N 次，落盘记录条数
    与结果指纹**逐字一致**（不追加、不重复计数）；
  · **不把未完成当完成**：只有全部步骤到「成功」才是「已完成」；任何一步是失败／超时／配额耗尽，
    任务状态就是那一个词，并且退出码非 0。被中断时状态是「进行中」，同样**不是**成功。

只跑只读命令、只取夹具端点
--------------------------
`调用命令` 步骤只接受 `schema.py` 里声明为**只读**的命令（写命令在校验期即拒绝，含四个触发类）；
`取数` 步骤默认只允许回环地址（要指向远端必须显式设 `DANIEL_SCHED_ALLOW_REMOTE=1`）。
两条合起来：**本层不可能替你发起真实采集**（本票红线）。
"""
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from ..exits import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE
from ..runtime import CliError
from . import policy, store

_HERE = os.path.dirname(os.path.abspath(__file__))
CLI_PATH = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "bin", "daniel")

#: 单步结果里保留的正文上限（超出即截断，并在结果里**如实标注**截断，不静默丢）
TEXT_CAP = 20000

ACT_FETCH = "取数"
ACT_COMMAND = "调用命令"
STEP_ACTIONS = (ACT_FETCH, ACT_COMMAND)

STEP_ID = "id"
STEP_DESC = "说明"
STEP_ACTION = "动作"
STEP_URL = "地址"
STEP_CMD = "命令"
STEP_PARAMS = "参数"

F_TASK_ID = "id"
F_TASK_NAME = "名称"
F_TASK_NOTE = "说明"
F_STEPS = "步骤"
F_LIMITS = "限额"

#: 任务状态用词（与 policy 同源）
TASK_RUNNING = policy.TASK_RUNNING


# ─────────────────────────── 指纹与规格校验 ───────────────────────────
def canonical(obj):
    """规范化 JSON 文本（排序键、无多余空白）——**指纹的唯一算法**，逐字可比。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(obj):
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def _loopback(url):
    host = (urllib.parse.urlparse(url).hostname or "").strip().lower()
    return bool(host) and (host in ("localhost", "::1") or host.startswith("127."))


def declared_read_commands():
    """`schema.py` 里声明为**只读**的命令键集合（`{"brands list", …}`）——单一真源，不写第二份。"""
    from ..schema import SCHEMA
    out = set()
    for mod in SCHEMA["modules"]:
        for cmd in mod["commands"]:
            if not cmd["write"]:
                out.add("%s %s" % (mod["key"], cmd["name"]))
    return out


def validate_spec(spec):
    """规格 → `(问题清单, 归一后的步骤)`。问题非空即**用户错误**（退出码 2），一步都不跑。"""
    problems = []
    if not isinstance(spec, dict):
        return ["任务规格必须是一个 JSON 对象"], []
    steps = spec.get(F_STEPS)
    if not isinstance(steps, list) or not steps:
        return ["任务规格缺少非空的「步骤」列表"], []
    limits = spec.get(F_LIMITS) or {}
    if not isinstance(limits, dict):
        problems.append("「限额」必须是对象")
    else:
        for k in limits:
            if k not in policy.LIMIT_KEYS:
                problems.append("「限额」里有不认识的键：%s（允许：%s）"
                                % (k, "／".join(sorted(policy.LIMIT_KEYS))))
    known = declared_read_commands()
    seen, norm = set(), []
    for i, raw in enumerate(steps, 1):
        if not isinstance(raw, dict):
            problems.append("第 %d 个步骤不是对象" % i)
            continue
        sid = str(raw.get(STEP_ID) or "").strip()
        if not sid:
            problems.append("第 %d 个步骤缺少「id」" % i)
            continue
        if sid in seen:
            problems.append("步骤 id 重复：%s" % sid)
            continue
        seen.add(sid)
        act = raw.get(STEP_ACTION)
        if act not in STEP_ACTIONS:
            problems.append("步骤 %s 的「动作」只能是 %s" % (sid, "／".join(STEP_ACTIONS)))
            continue
        step = {STEP_ID: sid, STEP_DESC: raw.get(STEP_DESC) or "", STEP_ACTION: act}
        if act == ACT_FETCH:
            url = str(raw.get(STEP_URL) or "").strip()
            if not url:
                problems.append("步骤 %s（取数）缺少「地址」" % sid)
                continue
            if not url.startswith(("http://", "https://")):
                problems.append("步骤 %s 的「地址」必须是 http(s)：%s" % (sid, url))
                continue
            if not policy.remote_allowed() and not _loopback(url):
                problems.append("步骤 %s 的「地址」不是回环地址（%s）：本工序默认只允许假端点／夹具，"
                                "要指向远端须显式设 %s=1" % (sid, url, policy.ALLOW_REMOTE_ENV))
                continue
            step[STEP_URL] = url
        else:
            cmd = " ".join(str(raw.get(STEP_CMD) or "").split())
            if cmd not in known:
                problems.append("步骤 %s 的「命令」不可用：%r —— 只读命令白名单里没有它"
                                "（写命令／未知命令一律拒绝：本层不做任何 Daniel 写，"
                                "也不替你触发采集）" % (sid, cmd))
                continue
            params = raw.get(STEP_PARAMS) or {}
            if not isinstance(params, dict):
                problems.append("步骤 %s 的「参数」必须是对象" % sid)
                continue
            step[STEP_CMD] = cmd
            step[STEP_PARAMS] = params
        norm.append(step)
    return problems, norm


# ─────────────────────────── 一次尝试的分类结果 ───────────────────────────
class Attempt:
    """一次尝试的结果：类别／终态候选／人话原因／载荷／`Retry-After`。

    `retryable` **由产生它的那一层显式给出**（不靠事后猜文本）：HTTP 侧按状态码判，
    命令侧按输出里的可重试标记判。判不出来一律"不可重试" —— 宁可少重试，
    也不把确定性失败重试成"看起来服务端在抖"。
    """

    def __init__(self, kind, terminal, reason, payload=None, retry_after=None, status=None,
                 retryable=False):
        self.kind = kind                 # ok ｜ quota ｜ fail ｜ timeout ｜ network
        self.terminal = terminal
        self.reason = reason
        self.payload = payload
        self.retry_after = retry_after
        self.status = status
        self.retryable = bool(retryable)


def _retry_after_seconds(resp):
    try:
        raw = resp.headers.get("Retry-After")
    except Exception:                                          # noqa: BLE001
        raw = None
    if not raw:
        return None
    try:
        return float(str(raw).strip())
    except ValueError:
        return None


def fetch_once(url, timeout):
    """一次 HTTP 取数（只读 GET）。**不吞异常**：分类后交给退避层决定终态。"""
    req = urllib.request.Request(url, method="GET",
                                 headers={"Accept": "application/json",
                                          "User-Agent": "daniel-sched/1 (TICKET-181)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = int(getattr(resp, "status", 200) or 200)
            return Attempt("ok", policy.ST_SUCCESS, "HTTP %d" % status,
                           payload=payload_of(body), status=status)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:                                      # noqa: BLE001
            body = ""
        code = int(e.code)
        retryable, terminal, reason = policy.classify_http(code)
        ra = _retry_after_seconds(e)
        if retryable and ra is not None:
            reason += "（服务端要求等待 %.0f 秒）" % ra
        kind = "quota" if code == policy.QUOTA_STATUS else "fail"
        return Attempt(kind, terminal, reason, payload=payload_of(body), retry_after=ra,
                       status=code, retryable=retryable)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        why = getattr(e, "reason", e)
        if isinstance(why, TimeoutError) or "timed out" in str(why).lower():
            return Attempt("timeout", policy.ST_TIMEOUT,
                           "单次请求超时（%s 秒）：%s" % (timeout, why), retryable=True)
        return Attempt("network", policy.ST_FAIL, "连接失败：%s" % why, retryable=True)


def payload_of(body):
    """正文 → 结果载荷：能解析成 JSON 就结构化（指纹才逐字稳定），否则原样文本（超长截断并标注）。"""
    text = body or ""
    if text.strip():
        try:
            return json.loads(text)
        except ValueError:
            pass
    if len(text) > TEXT_CAP:
        return {"文本": text[:TEXT_CAP], "被截断": True,
                "说明": "正文超过 %d 字符，已截断（只影响本层留痕，不影响服务端事实）" % TEXT_CAP}
    return {"文本": text}


# ─────────────────────────── 调用命令（只读） ───────────────────────────
def command_argv(step):
    parts = step[STEP_CMD].split()
    argv = [sys.executable, CLI_PATH, parts[0], parts[1]]
    for key, value in sorted((step.get(STEP_PARAMS) or {}).items()):
        if value is True:
            argv.append(key)
        elif value in (False, None, ""):
            continue
        elif isinstance(value, list):
            for item in value:
                argv += [key, str(item)]
        else:
            argv += [key, str(value)]
    argv.append("--json")
    return argv


def command_once(step, timeout):
    """跑一条**只读** CLI 命令（复用本 CLI 入口，不重写任何业务判据）。"""
    try:
        p = subprocess.run(command_argv(step), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return Attempt("timeout", policy.ST_TIMEOUT,
                       "命令超时（%s 秒）：%s" % (timeout, step[STEP_CMD]), retryable=True)
    try:
        doc = json.loads(p.stdout)
    except ValueError:
        doc = None
    if p.returncode == 0:
        payload = (doc or {}).get("data", (doc or {}).get("text"))
        if payload is None:
            payload = {"文本": (p.stdout or "").strip()[:TEXT_CAP]}
        return Attempt("ok", policy.ST_SUCCESS, "退出码 0", payload=payload)
    blob = "%s %s" % (p.stderr or "", p.stdout or "")
    lines = [ln for ln in blob.strip().splitlines() if ln.strip()]
    reason = "退出码 %d：%s" % (p.returncode, lines[-1][:200] if lines else "无输出")
    marker = next((m for m in policy.RETRYABLE_MARKERS if m in blob), None)
    if marker:
        return Attempt("fail", policy.ST_FAIL,
                       reason + "（输出里出现可重试标记 %r，按退避重试）" % marker, retryable=True)
    return Attempt("fail", policy.ST_FAIL, reason + "（判不出可重试标记，按失败收口，不重试）")


# ─────────────────────────── 任务状态 ───────────────────────────
def _task_meta(spec, task_id):
    return {"id": task_id, "名称": spec.get(F_TASK_NAME) or task_id,
            "说明": spec.get(F_TASK_NOTE) or "",
            "规格指纹": digest(spec), "规格路径": store.spec_file(task_id)}


def _blank_state(spec, task_id, steps, now):
    return {"任务": _task_meta(spec, task_id), "状态": TASK_RUNNING,
            "进度": {"总步骤": len(steps), "已完成": 0, "未完成": len(steps), "失败": 0},
            "步骤": [], "汇总": {"结果指纹": None, "结果": None}, "被中断": False,
            "创建时间": now, "更新时间": now, "运行": {}}


def _progress_of(state, steps):
    done = [s for s in state.get("步骤", []) if s.get("状态") == policy.ST_SUCCESS]
    bad = [s for s in state.get("步骤", [])
           if s.get("状态") in (policy.ST_FAIL, policy.ST_TIMEOUT, policy.ST_QUOTA)]
    return {"总步骤": len(steps), "已完成": len(done),
            "未完成": len(steps) - len(done), "失败": len(bad)}


def _skip_reason(state, step):
    """这一步能不能跳过？→ `(是否跳过, 理由)`。"""
    for rec in state.get("步骤", []):
        if rec.get("id") != step[STEP_ID]:
            continue
        if rec.get("状态") != policy.ST_SUCCESS:
            return False, "上次终态 %s" % rec.get("状态")
        payload = rec.get("结果")
        if rec.get("结果指纹") != digest(payload):
            return False, "存档结果与指纹对不上（视为未完成，重跑）"
        return True, "已完成且结果指纹一致"
    return False, "没有这一步的记录"


def _write_state(task_id, state, steps):
    state["进度"] = _progress_of(state, steps)
    state["更新时间"] = time.strftime("%Y-%m-%d %H:%M:%S")
    store.save_task(task_id, state)


def _explain(task_state, interrupted=False):
    if interrupted:
        return "已中断（未完成）：已完成的步骤留了检查点，续跑不会重跑它们。**这不是成功。**"
    return {
        policy.ST_SUCCESS: "全部步骤成功（结果按规格顺序汇总，指纹可比）。",
        policy.ST_FAIL: "有步骤失败且不再重试（不可重试，或重试次数已用尽）。**这不是成功。**",
        policy.ST_TIMEOUT: "有步骤超时／超过单步时限。**这不是成功。**",
        policy.ST_QUOTA: "有步骤因限流（429）用尽重试次数：配额耗尽。**这不是成功。**",
        TASK_RUNNING: "还有步骤未完成。**这不是成功。**",
    }.get(task_state, "状态未知")


def execute(spec, task_id=None, mode="运行", limit=None, progress=None, overrides=None):
    """跑／续跑／重试一份任务规格 → `(报告, 退出码)`。

    `mode` 只改报告的措辞；三种入口共用同一套检查点语义（跳过已完成、覆盖式重记、按规格顺序
    算指纹），所以 `run`／`resume`／`retry` 天然幂等 —— 不存在"哪条路会重复落盘"。
    """
    store.ensure_dirs()
    problems, steps = validate_spec(spec)
    if problems:
        raise CliError("任务规格不合法，一步都没跑：%s" % "；".join(problems[:5]), code=EXIT_USAGE,
                       hint="规格字段见 `daniel sched run --help`（步骤动作：取数／调用命令）")
    spec = dict(spec)
    spec[F_STEPS] = steps
    task_id = str(task_id or spec.get(F_TASK_ID) or "").strip()
    if not task_id:
        raise CliError("任务缺少 id（在规格里写 `\"id\"`，或用 `--task <编号>`）", code=EXIT_USAGE)
    try:
        backoff = policy.backoff_from_limits(spec.get(F_LIMITS), overrides)
    except KeyError as e:
        raise CliError("「限额」里有不认识的键：%s" % e, code=EXIT_USAGE)

    limit, limit_src = policy.concurrency_limit(limit)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    state = store.load_task(task_id)
    fresh = not isinstance(state, dict)
    new_digest = digest(spec)
    if fresh:
        state = _blank_state(spec, task_id, steps, now)
        if progress:
            progress("没有 %s 的状态文件：按**全新任务**跑（这不是错误）" % task_id)
    else:
        old = str((state.get("任务") or {}).get("规格指纹") or "")
        if old and old != new_digest and progress:
            progress("警告：本次规格与状态文件里的指纹不一致（存档 %s ／ 本次 %s）；"
                     "已完成的步骤仍按各自的结果指纹校验，对不上就重跑"
                     % (old[:12], new_digest[:12]))
        state["任务"] = _task_meta(spec, task_id)
        state["被中断"] = False
    store.save_spec(task_id, spec)
    state["运行"] = {"入口": mode, "并发上限": limit, "并发上限来源": limit_src,
                     "退避策略": backoff.as_dict(), "落点": store.landing_snapshot(),
                     "本次开始时间": now, "续跑": not fresh}
    _write_state(task_id, state, steps)

    interrupted = False
    try:
        for step in steps:
            sid = step[STEP_ID]
            skip, why = _skip_reason(state, step)
            if skip:
                if progress:
                    progress("步骤 %s：跳过（%s；**不重复取数**）" % (sid, why))
                for rec in state["步骤"]:
                    if rec.get("id") == sid:
                        rec["是否续跑跳过"] = True
                _write_state(task_id, state, steps)
                continue
            rec = _run_step(step, task_id, limit, backoff, progress)
            state["步骤"] = [r for r in state["步骤"] if r.get("id") != sid] + [rec]
            order = [s[STEP_ID] for s in steps]
            state["步骤"].sort(key=lambda r: order.index(r["id"]))
            _write_state(task_id, state, steps)                 # 🔴 每步立刻落盘：中断也不丢
            if rec["状态"] != policy.ST_SUCCESS:
                if progress:
                    progress("步骤 %s 终态：%s（%s）；后续步骤本次不再执行"
                             % (sid, rec["状态"], rec.get("终态原因") or ""))
                break
    except KeyboardInterrupt:
        interrupted = True
        if progress:
            progress("已中断：本次已完成的步骤已落盘；用 `daniel sched run %s` 续跑" % task_id)

    ordered = []
    for step in steps:
        rec = next((r for r in state["步骤"] if r.get("id") == step[STEP_ID]), None)
        ordered.append(rec or {"id": step[STEP_ID], "说明": step.get(STEP_DESC) or "",
                               "动作": step[STEP_ACTION], "状态": policy.ST_PENDING,
                               "尝试次数": 0, "结果": None, "结果指纹": None,
                               "是否续跑跳过": False,
                               "终态原因": "本次未执行（前一步未成功）"})
    state["步骤"] = ordered
    bad = [r for r in ordered if r["状态"] != policy.ST_SUCCESS]
    if bad:
        first_bad = next(r for r in ordered if r["状态"] != policy.ST_SUCCESS)
        state["状态"] = (TASK_RUNNING if interrupted and first_bad["状态"] == policy.ST_PENDING
                         else (first_bad["状态"] if first_bad["状态"] in policy.TERMINAL_STATES
                               else policy.ST_FAIL))
        state["被中断"] = bool(interrupted)
    else:
        state["状态"], state["被中断"] = policy.ST_SUCCESS, False
    state["汇总"] = {"结果指纹": digest([r.get("结果") for r in ordered]),
                     "结果": [r.get("结果") for r in ordered]}
    _write_state(task_id, state, steps)

    result_path = None
    if not bad:
        result_path = store.save_result(task_id, {
            "任务": {"id": task_id, "名称": state["任务"]["名称"]},
            "状态": state["状态"], "结果指纹": state["汇总"]["结果指纹"],
            "步骤": [{"id": r["id"], "动作": r.get("动作"), "状态": r["状态"], "结果": r.get("结果")}
                     for r in ordered]})

    report = {
        "任务": state["任务"], "入口": mode, "状态": state["状态"], "进度": state["进度"],
        "步骤": [{k: r.get(k) for k in ("id", "说明", "动作", "状态", "尝试次数", "耗时毫秒",
                                       "终态原因", "结果指纹", "是否续跑跳过")} for r in ordered],
        "结果指纹": state["汇总"]["结果指纹"],
        "未成功步骤": [r["id"] for r in bad],
        "运行": dict(state["运行"], 本次结束时间=time.strftime("%Y-%m-%d %H:%M:%S")),
        "落点": {"状态文件": store.task_file(task_id), "规格文件": store.spec_file(task_id),
                 "结果文件": result_path},
        "续跑": {"无状态文件按全新任务跑": fresh, "被中断": interrupted,
                 "本次跳过（已完成）": [r["id"] for r in ordered if r.get("是否续跑跳过")]},
        "说明": _explain(state["状态"], bool(state["被中断"])),
    }
    return report, (EXIT_INTERNAL if bad else EXIT_OK)


def _run_step(step, task_id, limit, backoff, progress):
    """跑一个步骤：**队列准入 → 取数／调用命令 → 退避重试 → 定终态**。

    并发位从准入持有到终态（含退避等待）：这样"并发上限"限制的是**在途步骤数**，而不是"发包时刻"，
    429 时不会因为"睡一觉就把位子让出去"而把限流打成脉冲。
    """
    sid = step[STEP_ID]
    entry_id = "%s#%s" % (task_id, sid)
    target = step.get(STEP_URL) or step.get(STEP_CMD)
    t0 = time.time()
    step_deadline = t0 + backoff.deadline
    on_wait = (lambda info: progress("步骤 %s：排队等待中（前面 %d 条在跑，上限 %d，已等 %.1f 秒）"
                                     % (sid, info["前面在跑"], info["上限"], info["已等待秒"]))) \
        if progress else None
    queued = store.acquire_slot({"编号": entry_id, "任务": task_id, "步骤": sid,
                                 "模块": "sched", "命令": target},
                                limit, on_wait=on_wait, wait_timeout=backoff.deadline)
    if queued is None:
        return _record(step, policy.ST_TIMEOUT, 0, t0,
                       "排队等待超过单步时限（%.0f 秒）仍未获准入" % backoff.deadline, None)
    settled, attempt_no = False, 0
    try:
        while True:
            attempt_no += 1
            store.bump_attempts(entry_id, attempt_no)
            if progress:
                progress("步骤 %s：第 %d 次尝试（%s）" % (sid, attempt_no, target))
            last = (fetch_once(step[STEP_URL], backoff.step_timeout)
                    if step[STEP_ACTION] == ACT_FETCH
                    else command_once(step, backoff.step_timeout))
            if last.kind == "ok":
                settled = True
                store.finish_slot(entry_id, policy.ST_SUCCESS, last.reason)
                if progress:
                    progress("步骤 %s：成功（%s，第 %d 次尝试）" % (sid, last.reason, attempt_no))
                return _record(step, policy.ST_SUCCESS, attempt_no, t0, last.reason, last.payload)
            if not last.retryable:
                settled = True
                store.finish_slot(entry_id, last.terminal, last.reason)
                return _record(step, last.terminal, attempt_no, t0, last.reason, None)
            remaining = step_deadline - time.time()
            if attempt_no >= backoff.attempts:
                note = ("%s；已用完重试次数（%d 次）—— 按终态「%s」如实上报，**不当作成功**"
                        % (last.reason, backoff.attempts, last.terminal))
                settled = True
                store.finish_slot(entry_id, last.terminal, note)
                return _record(step, last.terminal, attempt_no, t0, note, None)
            delay = backoff.delay(attempt_no)
            if last.retry_after is not None:
                delay = max(delay, float(last.retry_after))
            if delay >= remaining:
                note = ("%s；按退避还需等 %.1f 秒，超过单步时限剩余 %.1f 秒 —— 不再空等，"
                        "按终态「超时」如实上报" % (last.reason, delay, remaining))
                settled = True
                store.finish_slot(entry_id, policy.ST_TIMEOUT, note)
                return _record(step, policy.ST_TIMEOUT, attempt_no, t0, note, None)
            if progress:
                progress("步骤 %s：%s → 第 %d/%d 次尝试后退避 %.2f 秒（单步时限剩余 %.1f 秒）"
                         % (sid, last.reason, attempt_no, backoff.attempts, delay, remaining))
            time.sleep(max(0.0, delay))
    except KeyboardInterrupt:
        store.finish_slot(entry_id, policy.Q_INTERRUPTED, "被中断（步骤未完成）")
        raise
    finally:
        if not settled:
            # 任何"没走到终态"的退出路径（含被中断）都要把并发位还回去，否则队列会被自己锁死
            store.finish_slot(entry_id, policy.ST_FAIL,
                              "本次尝试未产生终态（进程退出／被中断），该步骤未完成")


def _record(step, status, attempts, t0, reason, payload):
    return {"id": step[STEP_ID], "说明": step.get(STEP_DESC) or "",
            "动作": step[STEP_ACTION], "状态": status, "尝试次数": attempts,
            "耗时毫秒": int((time.time() - t0) * 1000),
            "终态原因": reason, "结果": payload,
            "结果指纹": digest(payload) if payload is not None else None,
            "是否续跑跳过": False,
            "完成时间": time.strftime("%Y-%m-%d %H:%M:%S")}


# ─────────────────────────── 视图 ───────────────────────────
def task_rows():
    """任务列表（`sched status`）：状态／进度／落点，逐条如实。"""
    tasks, broken = store.list_tasks()
    stat = {TASK_RUNNING: 0}
    stat.update({s: 0 for s in policy.TERMINAL_STATES})
    rows = []
    for t in tasks:
        st = t.get("状态") or "未知"
        stat[st] = stat.get(st, 0) + 1
        rows.append({"id": (t.get("任务") or {}).get("id"), "名称": (t.get("任务") or {}).get("名称"),
                     "状态": st, "进度": t.get("进度"),
                     "更新时间": t.get("更新时间"),
                     "结果指纹": (t.get("汇总") or {}).get("结果指纹"),
                     "状态文件": t.get("_文件")})
    return {"任务": rows, "统计": stat, "读不动的状态文件": broken,
            "落点": store.landing_snapshot(), "终态定义": list(policy.TERMINAL_STATES),
            "说明": "「进行中」≠「已完成」：只有全部步骤成功才记「成功」；"
                    "失败／超时／配额耗尽各自单独成态，谁也不当成成功。"}


def task_detail(task_id):
    state = store.load_task(task_id)
    if not isinstance(state, dict):
        raise CliError("没有任务 %s 的状态文件（%s）" % (task_id, store.task_file(task_id)),
                       code=EXIT_USAGE,
                       hint="跑 `daniel sched status` 看现有任务；"
                            "用 `daniel sched run --spec <文件>` 新建")
    return {"任务": state.get("任务"), "状态": state.get("状态"), "进度": state.get("进度"),
            "步骤": state.get("步骤"),
            "汇总": {"结果指纹": (state.get("汇总") or {}).get("结果指纹")},
            "运行": state.get("运行"), "被中断": state.get("被中断"),
            "创建时间": state.get("创建时间"), "更新时间": state.get("更新时间"),
            "落点": {"状态文件": store.task_file(task_id), "结果文件": store.result_file(task_id)},
            "说明": _explain(state.get("状态"), bool(state.get("被中断")))}


__all__ = ["ACT_FETCH", "ACT_COMMAND", "STEP_ACTIONS", "F_TASK_ID", "F_TASK_NAME", "F_STEPS",
           "F_LIMITS", "TASK_RUNNING", "canonical", "digest", "validate_spec", "execute",
           "task_rows", "task_detail", "declared_read_commands", "command_argv", "CLI_PATH"]
