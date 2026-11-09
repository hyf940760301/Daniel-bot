# -*- coding: utf-8 -*-
"""sched 模块：调度层（断点续跑 ＋ 采集排队与限流退避）的**可调用面**（TICKET-181）。

命令面（4 条，另有一条等价别名 `sched resume` → `sched run`）：

    run    跑一个任务（有状态文件就**从检查点续跑**；没有就按全新任务跑）
    retry  重试未成功的步骤（已成功且校验一致的步骤一律不动 —— 幂等）
    status 看任务与进度（进行中／已完成／失败／超时／配额耗尽）
    queue  看统一队列（并发上限、受管触发类命令、逐条入队记录）

三条自我约束：
  ① **状态落 `$DANIEL_HOME`**（走 `daniel_paths`，惰性解析；不写代码目录）；
  ② **只读 Daniel**：本模块不碰任何 Daniel 写路由、不触发采集；步骤里引用的命令必须是
     `schema.py` 声明的**只读**命令，取数地址默认只允许回环（假端点／夹具）；
  ③ **进度可见**：排队、每次尝试、每次退避都往 stderr 打一行 —— 不许静默重试到超时。
"""
import io
import json
import os

from ..exits import EXIT_OK, EXIT_USAGE
from ..runtime import CliError
from ..sched import policy, runner, store

#: 命令行 → 策略键（`--retry` 覆盖重试次数上限、`--deadline` 覆盖单步时限）
LIMIT_OPTIONS = {"retry": "重试次数", "deadline": "总时限秒"}


def _read_spec(path):
    p = os.path.abspath(os.path.expanduser(str(path)))
    if not os.path.isfile(p):
        raise CliError("任务规格文件不存在：%s" % p, code=EXIT_USAGE,
                       hint="规格是一份 JSON：见 `daniel sched run --help` 的字段说明")
    try:
        with io.open(p, "r", encoding="utf-8") as fh:
            return json.load(fh), p
    except ValueError as e:
        raise CliError("任务规格不是合法 JSON：%s（%s）" % (p, e), code=EXIT_USAGE)


def _resolve_spec(ctx):
    """本次要跑的规格：`--spec` 优先，其次任务目录里存的规格副本（续跑不必再找那份文件）。"""
    task_id = ctx.get("任务") or ctx.get("task")
    task_id = str(task_id).strip() if task_id else None
    path = ctx.get("spec")
    if path:
        spec, real = _read_spec(path)
        return spec, real, task_id
    if task_id:
        spec = store.load_spec(task_id)
        if isinstance(spec, dict):
            return spec, store.spec_file(task_id), task_id
        raise CliError("任务 %s 既没有状态文件、也没有规格副本：给 --spec <文件> 才能新建" % task_id,
                       code=EXIT_USAGE,
                       hint="跑 `daniel sched status` 看现有任务")
    raise CliError("给一个任务编号（`daniel sched run <编号>`）或一份规格（`--spec <文件>`）",
                   code=EXIT_USAGE)


def _overrides(ctx):
    out = {}
    for opt, key in LIMIT_OPTIONS.items():
        value = ctx.get(opt)
        if value is not None:
            out[key] = value
    return out


def _run(ctx, mode):
    spec, real, task_id = _resolve_spec(ctx)
    report, code = runner.execute(spec, task_id=task_id, mode=mode, limit=ctx.get("concurrency"),
                                  progress=ctx.progress, overrides=_overrides(ctx))
    report["规格文件"] = real
    ctx.notes.append("任务状态：%s（%s）" % (report["状态"], report["说明"]))
    if code != EXIT_OK:
        ctx.warn("本次未达成功终态：%s —— 已完成的步骤留了检查点，"
                 "确认原因后可用 `daniel sched run %s` 续跑（不会重跑已完成的取数）"
                 % (report["状态"], report["任务"]["id"]))
    ctx.emit_raw(ok=(code == EXIT_OK), exit_code=code, data=report)
    return code


def cmd_run(ctx):
    """跑一个任务：有检查点就从检查点续跑，没有就按全新任务跑（**每一步立刻落盘**）。"""
    return _run(ctx, "运行")


def cmd_retry(ctx):
    """重试：只重跑未成功的步骤（已成功且结果指纹一致的步骤不动，落盘记录条数不变）。"""
    return _run(ctx, "重试")


def cmd_status(ctx):
    """看任务与进度：进行中／已完成／失败／超时／配额耗尽 —— 「进行中」不等于「已完成」。"""
    task_id = ctx.get("任务") or ctx.get("task")
    task_id = str(task_id).strip() if task_id else None
    if task_id:
        ctx.emit(data=runner.task_detail(task_id))
        return EXIT_OK
    ctx.emit(data=runner.task_rows())
    return EXIT_OK


def cmd_queue(ctx):
    """看统一队列：并发上限（含来源）、受管触发类命令、逐条入队记录、受管清单自证。"""
    limit, src = policy.concurrency_limit(None)
    data = dict(store.queue_snapshot())
    data.update({
        "并发上限": limit,
        "上限来源": src,
        "上限配置": "命令行 `--concurrency` ＞ 环境变量 %s ＞ 默认 %d（保守）"
                    % (policy.CONCURRENCY_ENV, policy.CONCURRENCY_DEFAULT),
        "受管触发类命令": policy.managed_trigger_rows(),
        "受管清单自证": policy.trigger_selfcheck(),
        "远端取数开关": {"环境变量": policy.ALLOW_REMOTE_ENV,
                        "当前": "已允许" if policy.remote_allowed() else
                                "未允许（只允许回环地址＝假端点／夹具）"},
        "说明": "触发类命令的真实执行**已接通**（TICKET-188 · A1），**准入点就是这条队列**："
                "带 --confirm 真跑时先拿并发位（上限见上），执行中命中 429／5xx 按指数退避重试，"
                "结束时把终态（成功／失败／超时／配额耗尽）写进逐条入队记录。"
                "干跑不占位、不写队列文件、不发包。",
    })
    ctx.emit(data=data)
    return EXIT_OK


HANDLERS = {
    "run": cmd_run,
    "retry": cmd_retry,
    "status": cmd_status,
    "queue": cmd_queue,
}
