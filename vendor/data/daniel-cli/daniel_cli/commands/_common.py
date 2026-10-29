# -*- coding: utf-8 -*-
"""命令实现层的公共件。

三条实现纪律：
  ① 读命令**只调既有能力**：共享客户端 `daniel_client`（含跨工作区品牌解析与鉴权）或
     `.kol-tools/` 下既有仪器脚本 —— 不在这里重写任何业务判据；
  ② 写命令**一律走同一条门禁链**（TICKET-152）：权限 → 确认 → 删除凭据 → 执行 → 回读 → 留痕。
     门禁链只有这一处实现，任何写命令都不许自造第二条；
  ③ 品牌引用一律先经共享客户端的跨工作区解析（`resolve_brand_ref`）再往下传，
     避免把"名字"直接喂给仪器后撞上"多工作区同名"的歧义。

写链口径（用户 2026-10-14 裁决）：
  · **能不能做**由**账号权限**决定（`permissions.verdict`）：账号看不到的模块，写也不开放；
    没有权限时退出码 2 并给出"人话理由"（哪一轴不满足：系统角色／账号状态／工作区权益／配额）；
  · **手滑防护**由 `--confirm` 承担：不带 `--confirm` 一律只做干跑（打印将要做什么），退出码 3，
    零写入；
  · **删除类**在 `--confirm` 之外必须再给 `--delete-token <目标名>`（把目标名原样再写一遍，
    写错即拒、退出码 2、零删除）。
  权限与确认是两件事：前者决定"能不能做"，后者只防"做错"。
"""
import os
import re
import time

from .. import audit, permissions
from ..exits import EXIT_INTERNAL, EXIT_NEEDS_CONFIRM, EXIT_OK, EXIT_USAGE
from ..runtime import CliError, load_capability, new_client, tools_dir

#: 写命令的开放级别（写进 schema 的 `writeStage`，帮助文本与门禁标记同源）
STAGE_LIVE = "live"      # 真实执行已接通：带 --confirm 会真的写，并回读校验
STAGE_GATED = "gated"    # 本工序只交付权限门禁＋干跑＋审计；真实执行不在本工序范围
STAGES = (STAGE_LIVE, STAGE_GATED)


# ─────────────────────────── 品牌解析 ───────────────────────────
def resolve_brand_ref(ctx, opt="--brand", client=None):
    """品牌名或编号 → 品牌行（含 id / workspaceId）。解析逻辑复用共享客户端。"""
    ref = ctx.require(opt)
    d = client or new_client(verbose=ctx.verbose)
    return d.resolve_brand_ref(ref)


def resolve_brand_id(ctx, opt="--brand", client=None):
    return resolve_brand_ref(ctx, opt, client=client)["id"]


# ─────────────────────────── 仪器调用 ───────────────────────────
def oracle_path():
    """口径一致性仪器用的前端算法还原件（仪器默认值是仓库相对路径，这里换成绝对路径，
    这样从任意工作目录调用都能跑）。"""
    return os.path.join(tools_dir(), "_daniel_jsref", "authenticityScore.extract.mjs")


def append_flag(argv, name, value):
    if value is not None:
        argv += [name, str(value)]
    return argv


def append_repeat(argv, name, values):
    for v in values or []:
        argv += [name, str(v)]
    return argv


# ─────────────────────────── 凭据 / 路径（只读盘点） ───────────────────────────
def credential_status():
    """凭据来源盘点。**不回显任何密码**（掩码与原件一致）。"""
    creds = load_capability("daniel_credentials")
    return creds.DanielCredentialStore().status()


def paths_snapshot():
    dpaths = load_capability("daniel_paths")
    return dpaths.paths()


# ─────────────────────────── 读结果规整 ───────────────────────────
def as_list(obj, *keys):
    """从接口返回里取出列表：直接是 list 就返回；是 dict 则按 keys 里的第一个命中的键取。"""
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, list):
                return v
    return []


def paged(rows, limit=None, offset=None):
    rows = list(rows or [])
    if offset:
        rows = rows[int(offset):]
    if limit:
        rows = rows[:int(limit)]
    return rows


# ─────────────────────────── 写门禁链 ───────────────────────────
class _LazyClient:
    """按需登录的客户端代理：写命令的"只读解析"用不到它时，就不打这次网络调用。

    写链里只有"解析目标／回读核对"需要客户端；像 `account login` 这种不需要解析目标的命令，
    干跑阶段完全可以离线完成。
    """

    def __init__(self, verbose=False):
        self._verbose = verbose
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = new_client(verbose=self._verbose)
        return self._client

    def __getattr__(self, item):
        return getattr(self.client, item)


def _plan_from_args(ctx):
    """把这次"本来要做的写"的参数列出来（不含任何凭据；写命令不接收密码类参数）。"""
    plan = {}
    for k, v in sorted(vars(ctx.args).items()):
        if k.startswith("_") or k in ("json", "verbose", "confirm", "dry_run", "delete_token"):
            continue
        if v in (None, False, [], ""):
            continue
        plan[k] = v
    return plan


def _audit(ctx, module, command, action_text, auth, verdict_row, plan, executed, ok, exit_code,
           mutation=None, readback=None, rolled_back=None, rollback_note=None, note=None,
           hard=False, failure_kind=None, exception=None):
    """留一条审计记录（TICKET-152 §四：每次写一条可导出记录）。

    真执行过的写：审计写不进去 → 硬失败（不许把"写了但没留痕"说成完成）；
    干跑与被拒的写：审计写不进去只降级为提示，不许盖过原本的结论。

    `failure_kind`／`exception`（TICKET-196 账二）：执行轴抛异常时的留痕。异常对象**只**取
    "类型名 ＋ 脱敏后的消息"两样进审计（`audit.FIELDS` 的 `exceptionType`／`errorSummary`），
    凭据／会话值一律不落盘 —— 理由见 `scrub_text()`。
    """
    entry = dict(permissions.audit_fields(auth))
    entry.update({
        "module": module, "command": command, "action": action_text,
        "target": (plan or {}).get("targetName"), "brand": (plan or {}).get("brand"),
        "impact": (plan or {}).get("impact"),
        "permissionAllowed": bool((verdict_row or {}).get("是否允许")),
        "permissionReason": (verdict_row or {}).get("reason"),
        "dryRun": not executed, "executed": bool(executed), "ok": bool(ok),
        "exitCode": int(exit_code), "mutation": mutation,
        "readback": (readback or {}).get("detail") if isinstance(readback, dict) else readback,
        "readbackOk": (readback or {}).get("verified") if isinstance(readback, dict) else None,
        "rolledBack": rolled_back, "rollbackNote": rollback_note,
        "failureKind": failure_kind,
        "exceptionType": type(exception).__name__ if exception is not None else None,
        "errorSummary": scrub_text(exception) if exception is not None else None,
        "notes": list(ctx.notes) + ([note] if note else []),
    })
    try:
        return audit.record(entry)
    except CliError as e:
        if hard:
            raise
        ctx.warn("审计记录没写进去（本次没有执行写，结论不受影响）：%s" % e.message)
        return None


def _emit_write(ctx, data, ok, exit_code):
    ctx.emit_raw(ok=ok, exit_code=exit_code, data=data)


# ───────────── 执行轴异常留痕（TICKET-196 账二）：脱敏 ＋ 单条终态 ─────────────
#: 异常消息脱敏口径：与 `selftest.py::_scrub` 同一套"键=值"规则（写链不另造第二份判据）。
#: 关键词里另加 `session`／`app_session_id`：本产品的会话值就挂在 `app_session_id` 这个响应头上，
#: 它是**能做事的凭据**（1 年有效），一旦进了审计就是永久泄漏 —— 审计是追加写、不回改历史的。
_CRED_SCRUB_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|cookie|session|app_session_id|authorization)"
    r"(\"?\s*[:=]\s*)\S+")

#: 异常消息进审计的截断长度（审计是给人读的；过长的堆栈文本没有增量信息）
_ERROR_SUMMARY_LIMIT = 300


def scrub_text(text, limit=_ERROR_SUMMARY_LIMIT):
    """把文本里的"键=值"抹成"键=<已脱敏>"，压成一行并截断。

    为什么在**入口**就脱敏、而不是"审计时再过滤"：审计文件是**追加写、不回改历史**的，
    写进去就收不回来；所以判据放在落盘之前，且只保留"异常类型 ＋ 这一行消息"两样。
    环境变量里的密码／会话值也一并抹掉（与 `selftest.py` 同一手）。
    """
    out = _CRED_SCRUB_RE.sub(lambda m: m.group(1) + m.group(2) + "<已脱敏>", str(text or ""))
    for env_key in ("DANIEL_PASSWORD", "DANIEL_SESSION", "DANIEL_SESSION_ID"):
        val = os.environ.get(env_key)
        if val:
            out = out.replace(val, "<已脱敏>")
    return " ".join(out.split())[:limit]


def _audit_unsettled(ctx, module, command, action_text, auth, verdict_row, plan, kind, exc=None):
    """执行轴的**兜底**留痕：这次尝试没有走到终态（抛异常／被中断），照样落一条。

    `executed=True` 的真实语义是「**尝试执行但抛异常**」（`executed` 的既有消费者口径是
    "进过执行分支＝真执行"，见 `audit.summarize`）—— 所以既不谎称写成功（`ok=False`），
    也不谎称没执行（`executed=True`）；"有没有取得终态"由 `failureKind`／`exceptionType`／
    `notes` 说清。`hard=False`：审计写不进去时**不许盖掉原异常**，只降级为提示。
    """
    note = ("执行函数抛异常：本次**尝试执行但没有取得终态**（异常类型 %s）；"
            "没有写成功记录，也没有回读结论。" % type(exc).__name__) if exc is not None else \
        "执行轴没有走到终态（进程被中断或异常已穿出执行轴）：本次尝试没有取得终态。"
    return _audit(ctx, module, command, action_text, auth, verdict_row, plan,
                  True, False, EXIT_INTERNAL, note=note, hard=False,
                  failure_kind=kind, exception=exc)


def _permission_block(ctx, module, command, action_text, kind=permissions.WRITE):
    """权限轴：拿不到快照或模块不放行 → 返回 `(verdict, exit_code 或 None)`。"""
    auth, why = permissions.current_auth()
    v = permissions.verdict(module, kind, auth)
    if v["是否允许"]:
        return auth, v, why, None
    # 无权路径：退出码 2（用户错误）＋ 人话理由（含"哪一轴不满足"）
    msg = permissions.denial_message(module, kind, v)
    ctx.warn(msg)
    plan = {"targetName": None, "impact": "未执行任何写（权限不满足，写链未进入执行分支）"}
    entry = _audit(ctx, module, command, action_text, auth, v, plan, False, False, EXIT_USAGE,
                   note=msg, failure_kind="permission")
    _emit_write(ctx, {
        "action": action_text,
        "permission": {"allowed": False, "reason": v["reason"], "axes": v["axes"],
                       "deniedAxes": v["deniedAxes"], "source": (auth or {}).get("source"),
                       "sourceNote": why},
        "executed": False, "dryRun": True, "plan": plan,
        "reason": msg, "auditPath": (entry or {}).get("path"),
    }, False, EXIT_USAGE)
    return auth, v, why, EXIT_USAGE


# ────────────── 统一队列 ＋ 429／5xx 退避（受管触发类写命令 · A1） ──────────────
#: 失败文本里的 HTTP 状态码（`daniel_client` 把服务端原文挂在异常里，这里只做**分类**）
_HTTP_STATUS_RE = re.compile(r"HTTP[ ]?(\d{3})")


def classify_write_failure(text):
    """失败文本 → `(可重试, 终态候选, 人话原因)`。判据**只有一份**：`sched.policy`。

    两处细节值得写在这里：
      · **429 是"配额耗尽"而不是"失败"**（`policy.classify_http` 的决定），这样报告里的四态
        才与调度层一致；重试用尽后仍按 429 的终态收口，不会因为"试了几次"就说成成功；
      · **判不出可重试标记就一律不可重试** —— 宁可少重试：写命令重试的代价是"可能重复发包"。
    """
    from ..sched import policy as sched_policy
    raw = str(text or "")
    m = _HTTP_STATUS_RE.search(raw)
    if m:
        retryable, terminal, reason = sched_policy.classify_http(int(m.group(1)))
        return retryable, terminal, reason
    for marker in sched_policy.RETRYABLE_MARKERS:
        if marker in raw:
            kind = "quota" if marker == "429" else "fail"
            return True, sched_policy.terminal_for_last_failure(kind), \
                "输出里出现可重试标记 %r（按指数退避重试）" % marker
    return False, sched_policy.ST_FAIL, "判不出可重试标记，按失败收口（不重试）"


def run_managed_write(ctx, module, command, run_fn, client, plan, attempts=2):
    """受管触发类写命令的**唯一**执行路径：统一队列准入 → 执行（429／5xx 退避）→ 定终态 → 释放并发位。

    为什么要有这一层（A1 · `08` 第二节）：触发类命令会真的发包消耗平台额度，所以它们**不许
    各自直接发包** —— 一律先经统一队列（并发上限可配：`DANIEL_SCHED_CONCURRENCY`，默认 1）拿到
    一个并发位，再执行；执行中命中 429／5xx 时按 `sched.policy.Backoff` 指数退避＋抖动重试，
    **每一次重试都往 stderr 打一行**（不静默重试到超时）；结束时把终态（成功／失败／超时／
    配额耗尽）写进队列记录，并归入本次结果。

    「一次只发一次包」的默认值：`attempts=2`（首次 ＋ 至多一次退避重试）。写命令重试的代价是
    "可能重复触发"，所以上限刻意压到最小；`--retry` 类参数没有暴露给用户，避免误用。
    """
    from ..sched import policy as sched_policy, store as sched_store
    limit, limit_src = sched_policy.concurrency_limit(ctx.get("concurrency"))
    backoff = sched_policy.Backoff(attempts=attempts)
    entry_id = "%s.%s#%s-p%d" % (module, command, time.strftime("%Y%m%d-%H%M%S"), os.getpid())
    t0 = time.time()
    deadline = t0 + backoff.deadline
    ctx.progress("统一队列准入：并发上限 %d（来源：%s）" % (limit, limit_src))

    def on_wait(info):
        ctx.progress("排队等待中（前面 %d 条在跑，并发上限 %d，已等 %.1f 秒）"
                     % (info["前面在跑"], info["上限"], info["已等待秒"]))

    queued = sched_store.acquire_slot({"编号": entry_id, "任务": "%s %s（真跑）" % (module, command),
                                       "步骤": "触发", "模块": module, "命令": command},
                                      limit, on_wait=on_wait, wait_timeout=backoff.deadline)
    if queued is None:
        raise CliError("排队等待超过 %.0f 秒仍未获准入（并发上限 %d，来源：%s）"
                       % (backoff.deadline, limit, limit_src), code=EXIT_INTERNAL,
                       hint="看 `daniel sched queue` 里谁在占位；或调大 %s 后重试"
                            % sched_policy.CONCURRENCY_ENV)
    settled, attempt_no, last = False, 0, ""
    try:
        while True:
            attempt_no += 1
            sched_store.bump_attempts(entry_id, attempt_no)
            if attempt_no > 1:
                ctx.progress("第 %d 次尝试（上一次：%s）" % (attempt_no, last))
            try:
                result = dict(run_fn(ctx, client, plan) or {})
            except CliError:
                # 入参类错误：重试没有意义，也不该记成"失败终态"（用户改参数再来）
                sched_store.finish_slot(entry_id, sched_policy.ST_FAIL,
                                        "本次尝试被本地拦下（用户错误），未发包")
                settled = True
                raise
            except Exception as e:                                     # noqa: BLE001
                last = str(e)[:300]
                retryable, terminal, reason = classify_write_failure(last)
                remaining = deadline - time.time()
                if not retryable or attempt_no >= backoff.attempts:
                    note = "%s；%s" % (last, reason if not retryable
                                       else "已用完重试次数（%d 次），按终态「%s」如实上报"
                                            % (backoff.attempts, terminal))
                    sched_store.finish_slot(entry_id, terminal, note)
                    settled = True
                    raise CliError(note, code=EXIT_INTERNAL,
                                   hint="队列记录：%s（`daniel sched queue` 可见）" % entry_id)
                delay = backoff.delay(attempt_no)
                if delay >= remaining:
                    note = ("%s；按退避还需等 %.1f 秒，超过总时限剩余 %.1f 秒 —— 不再空等，"
                            "按终态「超时」上报" % (last, delay, remaining))
                    sched_store.finish_slot(entry_id, sched_policy.ST_TIMEOUT, note)
                    settled = True
                    raise CliError(note, code=EXIT_INTERNAL)
                ctx.warn("%s → 第 %d/%d 次尝试后退避 %.2f 秒（%s）"
                         % (last, attempt_no, backoff.attempts, delay, reason))
                time.sleep(max(0.0, delay))
                continue
            # 队列记录的终态：**对外的动作结局**（成功／失败／超时／配额耗尽）。
            # 判据只有一条：run_fn 报出的终态落在四态里就用它；报的是"进行中"（非终态，例如
            # "发包成功、作业还在跑"）则队列记**成功**，作业状态另记 —— 绝不把"进行中"写成成功，
            # 也绝不把"发出去了"写成失败。
            job_terminal = result.get("terminal")
            if job_terminal in sched_policy.TERMINAL_STATES:
                terminal = job_terminal
            else:
                terminal = result.get("queue_terminal") or sched_policy.ST_SUCCESS
            note = "第 %d 次尝试；本次触发执行终态由 %s 判定" % (attempt_no, module)
            if job_terminal:
                note += "；作业终态：%s" % job_terminal
            sched_store.finish_slot(entry_id, terminal, note)
            settled = True
            result["queue"] = {"编号": entry_id, "并发上限": limit, "上限来源": limit_src,
                               "尝试次数": attempt_no, "队列终态": terminal,
                               "作业终态": job_terminal,
                               "退避策略": backoff.as_dict(), "队列查询": "daniel sched queue",
                               "本次占队列位": True}
            return result
    finally:
        if not settled:
            # 任何"没走到终态"的退出路径（含被中断）都要把并发位还回去，否则队列会被自己锁死
            sched_store.finish_slot(entry_id, sched_policy.ST_FAIL,
                                    "本次尝试未产生终态（进程退出／被中断），未落终态")


def gated_write(module, command, action_text, stage=STAGE_LIVE, plan_fn=None, run_fn=None,
                delete=None, gated_reason=None, danger="可逆（执行后会回读校验）",
                queue_managed=False):
    """把一条写命令装成"门禁链"处理器（唯一的写链实现）。

    参数：
      `module` / `command`：模块键与子命令名（权限判据与审计记录都用它）；
      `action_text`：业务语言的动作说明（例如"在品牌下新建名单"）；
      `stage`：`live`（真实执行已接通）或 `gated`（本工序只到干跑，真实执行不在范围）；
      `plan_fn(ctx, client)`：**只读**地算出"将发生什么＋影响范围"，返回
         `{"targetName": 目标名, "brand": 品牌, "impact": 影响范围文本, "changes": {...}, ...}`；
      `run_fn(ctx, client, plan)`：真正执行并回读，返回
         `{"mutation": {...}, "readback": {"verified": bool, "detail": {...},
          "before": {...}, "after": {...}}, "rolledBack": bool|None, "rollbackNote": str}`
         —— 只在 `stage=live` 且确认齐备时被调用；
      `delete`：删除类命令的目标名口径（例如 `"名单名"`）；给了它就必须再给 `--delete-token`。
    """
    if stage not in STAGES:
        raise ValueError("未知的写命令开放级别：%s" % stage)

    def handler(ctx):
        # ① 权限轴：账号看不到的模块，写也不开放（退出码 2，人话理由）
        auth, v, why, denied = _permission_block(ctx, module, command, action_text)
        if denied is not None:
            return denied

        # ② 删除凭据轴的第一半：删除类没给 --delete-token 就地拒绝（不解析目标、不碰任何东西）
        if delete and ctx.confirm and not ctx.get("delete-token"):
            msg = ("删除类操作在 --confirm 之外必须再确认一次：请用 --delete-token 把%s原样再写一遍。"
                   "没有执行任何删除。" % delete)
            ctx.warn(msg)
            plan0 = {"targetName": None, "impact": "未执行任何删除（删除凭据缺失）",
                     "deleteTokenMissing": True}
            entry = _audit(ctx, module, command, action_text, auth, v, plan0, False, False,
                           EXIT_USAGE, note=msg, failure_kind="delete-token-missing")
            _emit_write(ctx, {
                "action": action_text,
                "permission": {"allowed": True, "reason": v["reason"], "axes": v["axes"],
                               "source": (auth or {}).get("source"), "sourceNote": why},
                "plan": plan0, "danger": danger, "executed": False, "dryRun": True,
                "exitReason": "删除类操作缺 --delete-token", "reason": msg,
                "hint": "先用 `daniel lists by-brand`／`daniel brands show` 拿到目标名，"
                        "再用 --delete-token 原样写一遍",
                "auditPath": (entry or {}).get("path"),
            }, False, EXIT_USAGE)
            return EXIT_USAGE

        # ③ 计划轴：先算清"将发生什么＋影响范围"（只读），干跑与真执行共用这一份
        client = _LazyClient(ctx.verbose)
        try:
            plan = dict(plan_fn(ctx, client) or {}) if plan_fn else {}
        except Exception as exc:                                     # noqa: BLE001（见 finally）
            # 🔴 TICKET-196 实测到的第二处"零审计"（计划轴拒绝）：`daniel brands delete --brand
            #    <生产品牌> --confirm` 撞上"默认只允许删 _tmp- 测试品牌"这道闸时退出码 2、
            #    零删除、**审计 +0** —— 账上凭空少一笔，与"每次尝试都要有账"矛盾。
            #    这里**只补留痕**：计划轴零副作用、零发包，判据（拒绝条件）一个字不改，
            #    异常原样再抛（退出码语义不变）。
            failed = {"targetName": None,
                      "impact": "未执行任何写（计划轴拒绝：写链未进入执行分支）"}
            _audit(ctx, module, command, action_text, auth, v, failed, False, False,
                   getattr(exc, "code", EXIT_USAGE) or EXIT_USAGE,
                   note="计划轴拒绝：%s" % exc, failure_kind="plan-rejected")
            raise
        plan.setdefault("targetName", None)
        plan.setdefault("impact", "未声明影响范围")
        plan["requiresConfirm"] = True
        plan["isDelete"] = bool(delete)
        if delete:
            plan["deleteTokenRequired"] = True
            plan["deleteTokenHint"] = "把%s原样再写一遍（--delete-token）" % delete
        plan["arguments"] = _plan_from_args(ctx)

        base = {"action": action_text,
                "permission": {"allowed": True, "reason": v["reason"], "axes": v["axes"],
                               "source": (auth or {}).get("source"), "sourceNote": why},
                "plan": plan, "danger": danger}

        # ④ 确认轴：不带 --confirm 一律只做干跑（退出码 3，零写入）
        if not ctx.confirm:
            msg = ("「%s %s」是写操作（%s）：未加 --confirm，没有执行任何写。"
                   "当前是干跑：下面是这次将要做的动作与影响范围。" % (module, command, action_text))
            ctx.warn(msg)
            entry = _audit(ctx, module, command, action_text, auth, v, plan, False, True,
                           EXIT_NEEDS_CONFIRM, note=msg)
            payload = dict(base)
            payload.update({"executed": False, "dryRun": True, "exitReason": "需要确认（--confirm）",
                            "auditPath": (entry or {}).get("path")})
            _emit_write(ctx, payload, False, EXIT_NEEDS_CONFIRM)
            return EXIT_NEEDS_CONFIRM

        # ⑤ 删除凭据轴的第二半：给的凭据必须与目标名逐字一致（写错即拒，零删除）
        if delete:
            token = ctx.get("delete-token")
            want = plan.get("targetName")
            if str(token).strip() != str(want).strip():
                msg = ("--delete-token 与目标不一致：你写的是「%s」，本次要删的是「%s」。"
                       "写错即拒，没有执行任何删除。" % (token, want))
                ctx.warn(msg)
                entry = _audit(ctx, module, command, action_text, auth, v, plan, False, False,
                               EXIT_USAGE, note=msg, failure_kind="delete-token-mismatch")
                payload = dict(base)
                payload.update({"executed": False, "dryRun": True,
                                "exitReason": "删除凭据与目标不一致", "reason": msg,
                                "auditPath": (entry or {}).get("path")})
                _emit_write(ctx, payload, False, EXIT_USAGE)
                return EXIT_USAGE

        # ⑥ 本工序只到干跑的命令：权限与确认都齐了也不执行（如实说明，不谎称"写链未开放"）
        if stage != STAGE_LIVE:
            msg = ("「%s %s」的权限与确认都齐了，但真实执行不在本工序交付范围内：%s"
                   "本次没有执行任何写。" % (module, command,
                                          gated_reason or "本工序只交付权限门禁、干跑与审计留痕。"))
            ctx.warn(msg)
            entry = _audit(ctx, module, command, action_text, auth, v, plan, False, False,
                           EXIT_INTERNAL, note=msg, failure_kind="stage-not-live")
            payload = dict(base)
            payload.update({"executed": False, "dryRun": True, "stage": stage,
                            "exitReason": "真实执行不在本工序范围", "reason": msg,
                            "auditPath": (entry or {}).get("path")})
            _emit_write(ctx, payload, False, EXIT_INTERNAL)
            return EXIT_INTERNAL

        # ⑦ 执行轴：真写 → 回读校验 → 留痕
        # 🔴 TICKET-196 账二：**无论成功、失败还是抛异常，这一次尝试都必须落恰好一条审计**。
        #    改前这里没有任何 `try/except`：`run_fn` 一抛异常就直接穿出 `gated_write`，
        #    下面两处 `_audit` 都到不了 ⇒ 审计里零条 —— "写了（或可能写了）却没留痕"。
        #    为什么是"恰好一条"而不是"先落尝试、再落终态"：审计是**追加写、不回改历史**的
        #    jsonl，同一次尝试落两条会让「尝试数 == 成功 ＋ 失败 ＋ 拒绝」这条对账式数重。
        #    结构沿用 `run_managed_write` 自己的写法（`settled` 标记 ＋ `finally` 兜底）：
        #    异常路径由 `except` 显式落痕并**原样再抛**（不吞异常、不改退出码语义），
        #    `finally` 只兜"连异常对象都取不到"的路径（中断／某条分支漏了落终态）。
        ctx.progress("正在执行「%s %s」" % (module, command))
        settled = False
        try:
            if queue_managed:
                result = run_managed_write(ctx, module, command, run_fn, client, plan)
            else:
                result = dict(run_fn(ctx, client, plan) or {})
            readback = result.get("readback") or {}
            verified = bool(readback.get("verified"))
            payload = dict(base)
            payload.update({
                "executed": True, "dryRun": False, "stage": stage,
                "mutation": result.get("mutation"), "readback": readback,
                "rollback": {"rolledBack": result.get("rolledBack"),
                             "note": result.get("rollbackNote")},
                "detail": result.get("detail"),
                "queue": result.get("queue"),
                "terminal": result.get("terminal"),
            })
            if verified:
                entry = _audit(ctx, module, command, action_text, auth, v, plan, True, True,
                               EXIT_OK, mutation=result.get("mutation"), readback=readback,
                               rolled_back=result.get("rolledBack"),
                               rollback_note=result.get("rollbackNote"), hard=True)
                payload["auditPath"] = (entry or {}).get("path")
                payload["auditTime"] = (entry or {}).get("time")
                settled = True
                _emit_write(ctx, payload, True, EXIT_OK)
                return EXIT_OK
            msg = "写已提交，但回读校验没通过：%s（请人工核对目标对象）" % (
                readback.get("reason") or "回读结果与预期不一致")
            ctx.warn(msg)
            entry = _audit(ctx, module, command, action_text, auth, v, plan, True, False,
                           EXIT_INTERNAL, mutation=result.get("mutation"), readback=readback,
                           rolled_back=result.get("rolledBack"),
                           rollback_note=result.get("rollbackNote"), note=msg, hard=True,
                           failure_kind="readback")
            payload["auditPath"] = (entry or {}).get("path")
            settled = True
            _emit_write(ctx, payload, False, EXIT_INTERNAL)
            return EXIT_INTERNAL
        except Exception as exc:                                     # noqa: BLE001（见下方 finally）
            _audit_unsettled(ctx, module, command, action_text, auth, v, plan,
                             "exception", exc)
            settled = True
            raise
        finally:
            if not settled:
                # 连异常对象都取不到的路径（进程被中断等）：照样留一条，不留空窗
                _audit_unsettled(ctx, module, command, action_text, auth, v, plan, "unsettled")

    handler.__doc__ = "写操作门禁链（%s）：权限 → 确认 → %s执行 → 回读校验 → 审计留痕。" % (
        action_text, "删除凭据 → " if delete else "")
    handler._danielWriteGate = {                                  # noqa: SLF001（S6 断言读它）
        "module": module, "command": command, "stage": stage,
        "deleteToken": bool(delete), "deleteTarget": delete,
        "permissionGated": True, "confirmGated": True,
        "queueManaged": bool(queue_managed),
    }
    return handler


def delete_token_option(delete_target):
    """删除类命令的 `--delete-token` 选项定义（schema 与文档同源）。"""
    return {"option": "--delete-token", "targetKind": delete_target,
            "help": "删除类的二次确认：把%s原样再写一遍（写错即拒绝、退出码 2，且不做任何删除）"
                    % delete_target}


def live_managed_write(module, command, action_text, plan_fn=None, run_fn=None,
                       danger="会真的发包（执行后回读校验）"):
    """**受管触发类**写命令的薄封装（A1 起真实执行已接通）。

    与 `gated_only_write` 的差别只有一处，但这一处是关键：`queue_managed=True` —— 真跑时
    **先经统一队列拿并发位**（`DANIEL_SCHED_CONCURRENCY`，默认 1），执行中命中 429／5xx 时
    按指数退避＋抖动重试，结束时把终态（成功／失败／超时／配额耗尽）写进队列记录。

    干跑（不带 `--confirm`）**不占队列位、不写队列文件、不发任何包** —— 干跑零副作用这一条不变；
    计划里的「排队」段落与 `daniel sched queue` 打印的是**同一个对象**（口径不写第二份）。
    """

    def plan(ctx, client):
        p = dict(plan_fn(ctx, client) or {}) if plan_fn else {}
        p.setdefault("impact", "影响范围未声明")
        p["排队"] = _queue_note(module, command)
        return p

    return gated_write(module, command, action_text, stage=STAGE_LIVE, plan_fn=plan,
                       run_fn=run_fn, danger=danger, queue_managed=True)


def gated_only_write(module, command, action_text, impact_fn=None, gated_reason=None,
                     delete=None, danger="可逆（执行后会回读校验）", managed_queue=False):
    """`stage=gated` 写命令的薄封装：权限轴与确认轴照走，真实执行不在本工序范围。

    `impact_fn(ctx, client)` 只做**只读**解析，用来把"将发生什么＋影响范围"讲清楚
    （干跑输出与审计记录都用它）。走这条路的命令**不会**碰任何写路由。
    """

    def plan_fn(ctx, client):
        plan = dict(impact_fn(ctx, client) or {}) if impact_fn else {}
        plan.setdefault("impact", "影响范围未声明（本工序不执行该动作，只出干跑计划）")
        if managed_queue:
            plan["排队"] = _queue_note(module, command)
        return plan

    return gated_write(module, command, action_text, stage=STAGE_GATED, plan_fn=plan_fn,
                       run_fn=None, delete=delete, gated_reason=gated_reason, danger=danger)


def _queue_note(module, command):
    """统一队列的**口径说明**（只读；给干跑计划用）。

    单一真源：`daniel_cli/sched/policy.py` 的受管清单与并发上限解析。这里不重写任何判据 ——
    连"这条命令是不是受管"都从那张表里查，查不到就如实说"不在受管清单里"。
    """
    from ..sched import policy as sched_policy
    limit, src = sched_policy.concurrency_limit(None)
    managed = {(m, c) for m, c, _d in sched_policy.MANAGED_TRIGGER_COMMANDS}
    hit = (module, command) in managed
    note = {
        "受管": bool(hit),
        "并发上限": limit,
        "上限来源": src,
        "上限配置": "环境变量 %s（默认 %d，保守：一次只跑一条）"
                    % (sched_policy.CONCURRENCY_ENV, sched_policy.CONCURRENCY_DEFAULT),
        "队列查询": "daniel sched queue",
        "队列落点": "由 daniel_paths 解析（$DANIEL_HOME/sched/queue.json）",
        "退避策略": "429／5xx：指数退避＋上限＋抖动（每次重试都打一行进度，不静默重试到超时）",
        "本次是否占队列位": False,
        "说明": ("这条命令是**受管触发类**：带 --confirm 真跑时会先经统一队列拿并发位再发包，"
                 "结束时把终态（成功／失败／超时／配额耗尽）写进队列记录；"
                 "**本次是干跑**：不占队列位、不写队列文件、不发任何包。"),
    }
    if not hit:
        note["说明"] = "这条命令不在统一队列的受管清单里（受管清单真源见 daniel sched queue）。"
    return note


__all__ = ["CliError", "EXIT_OK", "EXIT_USAGE", "EXIT_INTERNAL", "EXIT_NEEDS_CONFIRM",
           "resolve_brand_ref", "resolve_brand_id", "oracle_path", "append_flag",
           "append_repeat", "gated_write", "gated_only_write", "live_managed_write",
           "delete_token_option", "classify_write_failure", "run_managed_write",
           "credential_status",
           "paths_snapshot", "as_list", "paged", "new_client",
           "STAGE_LIVE", "STAGE_GATED", "STAGES"]
