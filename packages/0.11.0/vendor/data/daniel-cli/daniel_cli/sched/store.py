# -*- coding: utf-8 -*-
"""调度层的**落点与状态存储**（TICKET-181）：任务检查点 ＋ 队列 ＋ 进程间锁。

落点纪律（本票红线）
--------------------
  · 一律走 `daniel_paths`：`$DANIEL_HOME/sched/…`（**不写代码目录**；分发后代码目录只读）；
  · **惰性解析**：所有路径都在函数里现算，**没有模块级落点常量** —— 模块级解析会在
    `import` 期就把落点钉死（装到 PATH 的软链调用、临时 `DANIEL_HOME` 都会因此出错，
    这正是 C15「路径归一化不变量」与 C16「产品可用性不变量」要挡的形态）。

目录布局（全部在 `$DANIEL_HOME/sched/` 下）
-------------------------------------------
    tasks/<任务>.json          任务状态（检查点：每一步的状态／结果／指纹／尝试次数）
    tasks/<任务>.spec.json     任务规格副本（续跑不必再让用户找那份 JSON）
    tasks/<任务>.result.json   结果文件（**只在任务到达终态时写**；续跑前后可逐字比对）
    queue.json                 队列（并发上限 ＋ 逐条入队记录）
    queue.lock                 队列的进程间互斥（`O_CREAT|O_EXCL`，含陈旧锁回收）

写盘一律"临时文件 ＋ `os.replace`"：中断发生在写一半时，读者看到的仍是**上一个完整版本**，
不会读到半截 JSON 被误判成"任务没了／步骤没了"。
"""
import errno
import io
import json
import os
import time

#: 队列／任务文件的写盘重试上限（拿到锁还写不进去就是真故障，不静默吞）
_WRITE_TRIES = 3
#: 陈旧锁／僵尸条目的判定阈值（秒）：持有者进程已不存在、且记录早于此刻这么久 → 回收
STALE_SECONDS = 900.0


def _paths_module():
    """加载既有落点解析层（`.kol-tools/daniel_paths.py`）——**懒加载**，不在模块级调用。"""
    from ..runtime import load_capability
    return load_capability("daniel_paths")


def home():
    """本机生效的 `$DANIEL_HOME`（每次现算，不缓存成模块级常量）。"""
    return _paths_module().resolve("home")


def home_reason():
    try:
        return _paths_module().home_reason()
    except Exception:                                          # noqa: BLE001（只影响措辞，不影响落点）
        return "未知"


def sched_dir():
    """调度层的落点根：`<DANIEL_HOME>/sched`（走 daniel_paths 的 home，不新造解析器）。"""
    return os.path.join(home(), "sched")


def tasks_dir():
    return os.path.join(sched_dir(), "tasks")


def queue_file():
    return os.path.join(sched_dir(), "queue.json")


def lock_file():
    return os.path.join(sched_dir(), "queue.lock")


def landing_snapshot():
    """落点快照（进报告与 `--json`：出问题时第一眼要能看见东西落在哪）。"""
    return {"DANIEL_HOME": home(), "落点选择理由": home_reason(), "调度落点": sched_dir(),
            "任务目录": tasks_dir(), "队列文件": queue_file()}


def ensure_dirs():
    """建目录（幂等）。建不出来就抛 —— 落点不可写属于**真故障**，不静默降级到代码目录。"""
    from ..runtime import CliError
    from ..exits import EXIT_INTERNAL
    for d in (sched_dir(), tasks_dir()):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as e:
            raise CliError("调度落点不可写：%s（%s）" % (d, e), code=EXIT_INTERNAL,
                           hint="落点由 $DANIEL_HOME 决定（见 `daniel account paths`）；"
                                "设一个可写目录后重试")
    return sched_dir()


# ─────────────────────────── 基础 IO ───────────────────────────
def _read_json(path, default=None):
    if not os.path.isfile(path):
        return default
    try:
        with io.open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return default


def _write_json(path, payload):
    """原子写（临时文件 → `os.replace`）；**失败即抛**，不让调用方以为写成功了。"""
    from ..runtime import CliError
    from ..exits import EXIT_INTERNAL
    tmp = "%s.tmp-%d" % (path, os.getpid())
    last = None
    for _ in range(_WRITE_TRIES):
        try:
            with io.open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
            return path
        except OSError as e:
            last = e
            time.sleep(0.05)
    try:
        os.remove(tmp)
    except OSError:
        pass
    raise CliError("状态写盘失败：%s（%s）" % (path, last), code=EXIT_INTERNAL,
                   hint="检查落点是否可写（`daniel account paths`）与磁盘空间")


def safe_name(task_id):
    """任务编号 → 安全文件名（**不改语义**：只把路径分隔符等换成 `-`，并附短指纹防撞名）。"""
    import hashlib
    raw = str(task_id or "").strip()
    keep = []
    for ch in raw:
        keep.append(ch if (ch.isalnum() or ch in "-_.") else "-")
    name = "".join(keep).strip("-.") or "task"
    if name != raw:
        name = "%s-%s" % (name[:48], hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8])
    return name


def task_file(task_id):
    return os.path.join(tasks_dir(), safe_name(task_id) + ".json")


def spec_file(task_id):
    return os.path.join(tasks_dir(), safe_name(task_id) + ".spec.json")


def result_file(task_id):
    return os.path.join(tasks_dir(), safe_name(task_id) + ".result.json")


def load_task(task_id):
    return _read_json(task_file(task_id))


def save_task(task_id, state):
    ensure_dirs()
    return _write_json(task_file(task_id), state)


def save_spec(task_id, spec):
    ensure_dirs()
    return _write_json(spec_file(task_id), spec)


def load_spec(task_id):
    return _read_json(spec_file(task_id))


def save_result(task_id, payload):
    ensure_dirs()
    return _write_json(result_file(task_id), payload)


def list_tasks():
    """全部任务状态（按更新时间倒序）。**读不动某一份就跳过**并记在返回值里（不静默丢）。"""
    d = tasks_dir()
    out, broken = [], []
    if not os.path.isdir(d):
        return out, broken
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json") or fn.endswith(".spec.json") or fn.endswith(".result.json"):
            continue
        path = os.path.join(d, fn)
        doc = _read_json(path)
        if not isinstance(doc, dict):
            broken.append(fn)
            continue
        doc["_文件"] = path
        out.append(doc)
    out.sort(key=lambda x: str((x.get("更新时间") or x.get("创建时间") or "")), reverse=True)
    return out, broken


# ─────────────────────────── 进程间锁 ───────────────────────────
def _pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError as e:
        if e.errno == errno.ESRCH:
            return False
        return True
    except (TypeError, ValueError):
        return False
    return True


class Lock:
    """队列的进程间互斥（`O_CREAT|O_EXCL`）。

    为什么不用 `fcntl.flock`：本层要能在**任意宿主**里跑（Windows 上 `fcntl` 不存在），而
    `O_CREAT|O_EXCL` 在 POSIX 与 Windows 上语义一致（`O_EXCL` 都是原子的创建即独占）。
    陈旧锁（持有者进程已死）会被回收 —— 否则一次 `kill -9` 会把队列永久锁死。
    """

    def __init__(self, path=None, timeout=15.0, poll=0.05):
        self.path = path or lock_file()
        self.timeout = timeout
        self.poll = poll

    def _stale(self):
        try:
            st = os.stat(self.path)
        except OSError:
            return False
        holder = 0
        try:
            with io.open(self.path, "r", encoding="utf-8") as fh:
                holder = int((fh.read() or "0").strip() or 0)
        except (OSError, ValueError):
            holder = 0
        return (not _pid_alive(holder)) and (time.time() - st.st_mtime > 1.0)

    def acquire(self):
        from ..runtime import CliError
        from ..exits import EXIT_INTERNAL
        ensure_dirs()
        deadline = time.time() + self.timeout
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, str(os.getpid()).encode("ascii"))
                os.close(fd)
                return self
            except FileExistsError:
                if self._stale():
                    try:
                        os.remove(self.path)
                    except OSError:
                        pass
                    continue
                if time.time() > deadline:
                    raise CliError("队列锁等待超时（%s 秒）：%s" % (self.timeout, self.path),
                                   code=EXIT_INTERNAL,
                                   hint="若有进程被强杀，删掉这个锁文件即可（陈旧锁会自动回收，"
                                        "这里超时说明确实有活进程在持有）")
                time.sleep(self.poll)
            except OSError as e:
                raise CliError("队列锁创建失败：%s（%s）" % (self.path, e), code=EXIT_INTERNAL)

    def release(self):
        try:
            os.remove(self.path)
        except OSError:
            pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
        return False


# ─────────────────────────── 队列 ───────────────────────────
def queue_doc():
    doc = _read_json(queue_file(), None)
    if not isinstance(doc, dict):
        doc = {"上限": None, "条目": [], "更新时间": None}
    doc.setdefault("条目", [])
    return doc


def _purge(doc):
    """清掉"进程已不存在"的运行中条目（如实记成**中断**，不是成功、也不是失败）。"""
    from . import policy
    now = time.time()
    for e in doc.get("条目", []):
        if e.get("状态") != policy.Q_RUNNING:
            continue
        pid = e.get("进程号")
        started = e.get("开始时间戳") or 0
        if (not _pid_alive(pid)) and (now - started > 1.0):
            e["状态"] = policy.Q_INTERRUPTED
            e["结束时间"] = _ts()
            e["说明"] = "持有进程 %s 已不存在（被中断）；该步骤未完成，续跑会重新取数" % pid
    return doc


def _ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def queue_snapshot():
    """队列快照（只读）：{上限, 条目, 运行中, 排队中, 落点}。"""
    from . import policy
    doc = _purge(queue_doc())
    rows = doc.get("条目", [])
    return {"上限": doc.get("上限"), "条目": rows,
            "运行中": [e for e in rows if e.get("状态") == policy.Q_RUNNING],
            "排队中": [e for e in rows if e.get("状态") == policy.Q_WAITING],
            "落点": queue_file(), "更新时间": doc.get("更新时间")}


def acquire_slot(entry, limit, on_wait=None, poll=0.2, wait_timeout=None):
    """**队列准入**：占一个并发位；满了就等（并把"排队中"如实记进队列文件）。

    `entry` 至少含 `编号／任务／步骤／模块／命令`。返回占位后的条目。
    等待期间每约 1 秒回调一次 `on_wait(信息)` —— 进度必须可见（不许静默排队到超时）。
    """
    from . import policy
    ensure_dirs()
    started = time.time()
    while True:
        with Lock():
            doc = _purge(queue_doc())
            doc["上限"] = int(limit)
            rows = doc["条目"]
            running = [e for e in rows if e.get("状态") == policy.Q_RUNNING]
            mine = [e for e in rows if e.get("编号") == entry.get("编号")]
            if mine:
                cur = mine[0]
            else:
                cur = dict(entry)
                cur.update({"状态": policy.Q_WAITING, "入队时间": _ts(),
                            "入队时间戳": time.time(), "进程号": os.getpid(), "尝试次数": 0})
                rows.append(cur)
            if len(running) < int(limit):
                cur.update({"状态": policy.Q_RUNNING, "开始时间": _ts(),
                            "开始时间戳": time.time(), "进程号": os.getpid()})
                doc["更新时间"] = _ts()
                _write_json(queue_file(), doc)
                return cur
            doc["更新时间"] = _ts()
            _write_json(queue_file(), doc)
            ahead = len(running)
        if on_wait is not None:
            on_wait({"前面在跑": ahead, "上限": int(limit),
                     "已等待秒": round(time.time() - started, 1)})
        if wait_timeout is not None and (time.time() - started) > float(wait_timeout):
            _finish_slot(entry.get("编号"), policy.ST_TIMEOUT,
                         "排队等待超过 %s 秒仍未获准入（前面 %d 条在跑，上限 %d）"
                         % (wait_timeout, ahead, limit))
            return None
        time.sleep(poll)


def _find(doc, entry_id):
    for e in doc.get("条目", []):
        if e.get("编号") == entry_id:
            return e
    return None


def _finish_slot(entry_id, state, note=""):
    from . import policy
    with Lock():
        doc = _purge(queue_doc())
        e = _find(doc, entry_id)
        if e is None:
            return None
        e.update({"状态": state, "结束时间": _ts(), "结束时间戳": time.time(), "说明": note})
        doc["更新时间"] = _ts()
        _write_json(queue_file(), doc)
        return e


def finish_slot(entry_id, state, note=""):
    """释放并发位并写终态（`成功／失败／超时／配额耗尽` 之一，或 `已完成`）。"""
    return _finish_slot(entry_id, state, note)


def bump_attempts(entry_id, n):
    """更新某条队列记录的尝试次数（重试要**看得见**）。"""
    with Lock():
        doc = _purge(queue_doc())
        e = _find(doc, entry_id)
        if e is None:
            return None
        e["尝试次数"] = int(n)
        doc["更新时间"] = _ts()
        _write_json(queue_file(), doc)
        return e


__all__ = ["home", "home_reason", "sched_dir", "tasks_dir", "queue_file", "lock_file",
           "landing_snapshot", "ensure_dirs", "safe_name", "task_file", "spec_file",
           "result_file", "load_task", "save_task", "save_spec", "load_spec", "save_result",
           "list_tasks", "Lock", "queue_doc", "queue_snapshot", "acquire_slot", "finish_slot",
           "bump_attempts", "STALE_SECONDS"]
