# -*- coding: utf-8 -*-
"""`daniel --self-test`：本 CLI 的自检（TICKET-145 §4；TICKET-146 增补 P 组；TICKET-152 增补 W 组）。

八组：

  A  单一真源一致（schema ↔ CLI 注册 ↔ 实现注册表 ↔ 派生工具定义 ↔ 权限判据覆盖）
  E  退出码语义（缺参=2；写操作无 --confirm=3；无权=2；工作令红线动作=1，且都明说未执行写）
  R  12 模块只读子命令可达（真调只读通路/既有只读入口，逐个断言退出码 0 且结果是 JSON）
     ——TICKET-151 C1：**受控并发**跑（纯 I/O 等待，默认 6 线程），汇总仍按 `SMOKE` 的固定
     模块顺序输出，失败承诺不变（哪一条 + 原始错误）
  J  `--json` 输出可被 `json.loads` 整体解析（并顺带核对 stdout 只有一个 JSON 文档）
  Z  零 DSH 依赖（PATH 只留 python3 再跑一次只读命令；另做源码级 import 扫描）
  C  凭据来源矩阵（有钥匙串→keychain；无钥匙串且有 env→env）**且不写钥匙串**
  P  契约引擎自证（TICKET-146 · 引擎级最小）：契约能加载／校验、最小契约跑通且计数自洽、
     门禁五道齐备、沙箱处置写明、D3 拒幻觉命令、零 DSH 依赖
     （**逐契约期望核对**由 `daniel playbook selfcheck` 单一入口承担，不在这里重复跑）
  W  权限与门禁（TICKET-152）：能力矩阵覆盖 12 模块、降级角色注入下被拒且理由可读、
     无权模块的读也不放行、删除类缺凭据零删除、干跑零写（会话文件指纹不变）、审计可导出

退出码：0＝全部通过；1＝有未通过项（与 CLI 的退出码语义一致：1＝内部错误）。
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import schema
from .checks import schema_consistency
from .exits import EXIT_INTERNAL, EXIT_NEEDS_CONFIRM, EXIT_OK, EXIT_USAGE
from .runtime import load_capability, repo_root, tools_dir

#: 12 个模块各选一条"只读且不需要外部 id"的命令做冒烟（票面 §1 的"真实返回数据"）
SMOKE = [
    ("brands", ["brands", "list", "--limit", "5", "--json"]),
    ("lists", ["lists", "by-brand", "--brand", "3690002", "--json"]),
    ("search", ["search", "history", "--limit", "5", "--json"]),
    ("mentions", ["mentions", "jobs", "--brand", "3690002", "--limit", "3", "--json"]),
    ("intel", ["intel", "actions", "--brand", "3690002", "--json"]),
    ("sov", ["sov", "overview", "--brand", "3690002", "--json"]),
    ("ct", ["ct", "campaigns", "--brand", "3690002", "--json"]),
    ("authenticity", ["authenticity", "channel", "--channel", "@Mrwhosetheboss", "--json"]),
    ("route", ["route", "probe", "--route", "discovery.resolveChannelInput",
               "--input", '{"input": "@Harveyinchina"}', "--json"]),
    ("takeover", ["takeover", "check", "--brand", "3690002", "--only", "brands", "--json"]),
    ("parity", ["parity", "selfcheck", "--json"]),
    ("account", ["account", "whoami", "--json"]),
]

#: 自检夹具（**不是真凭据**，只在"无钥匙串 + 有 env"这条分支里当输入用；不写任何存储）
FAKE_EMAIL = "selftest-fake@example.invalid"
FAKE_PASSWORD = "selftest-only-not-a-real-credential"      # noqa: S105（自检夹具，非真凭据）


def cli_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "daniel")


def run_cli(argv, env=None, timeout=900, python_only=False):
    """跑本 CLI 的子进程（返回 CompletedProcess；文本模式）。"""
    e = dict(os.environ)
    if env:
        e.update(env)
    if python_only:
        e = _strip_env(e)
    return subprocess.run([sys.executable, cli_path()] + list(argv),
                          capture_output=True, text=True, timeout=timeout, env=e)


def _json_or_none(text):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


#: W 组用的降级角色快照（**离线注入**，不是真账号；只影响判据输入，不联网、不写任何账号）
_VIEWER_FIXTURE = {
    "systemRole": "viewer", "role": "user", "userStatus": "active",
    "emailMasked": "se***@example.invalid", "activeWorkspaceId": 90002,
    "workspace": {"id": 90002, "name": "自检注入工作区", "planTier": "starter",
                  "status": "active", "maxBrands": 0, "maxSearchesPerMonth": 0,
                  "maxEmailsPerMonth": 0},
    "workspaces": [{"id": 90002, "name": "自检注入工作区", "planTier": "starter",
                    "memberRole": "member"}],
    "enabledFeatures": [],
}


def viewer_fixture():
    """把降级角色快照写进临时文件，返回路径（**不落仓库**，供 W 组与 E 组注入用）。"""
    if "path" not in viewer_fixture.__dict__:
        tmp = tempfile.mkdtemp(prefix="daniel-auth-fixture-")
        path = os.path.join(tmp, "viewer.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(_VIEWER_FIXTURE, fh, ensure_ascii=False)
        viewer_fixture.path = path
    return viewer_fixture.path


def _strip_env(env):
    """把 PATH 收成"只含 python3"的最小环境（零 DSH 依赖的判据）。"""
    tmp = tempfile.mkdtemp(prefix="daniel-cli-pathonly-")
    link = os.path.join(tmp, "python3")
    try:
        os.symlink(sys.executable, link)
    except OSError:
        shutil.copy2(sys.executable, link)
    keep = {k: v for k, v in env.items()
            if k in ("HOME", "DANIEL_HOME", "LANG", "LC_ALL", "TMPDIR", "USER")}
    keep["PATH"] = tmp
    return keep


class _Reporter:
    def __init__(self, emitter):
        self.emitter = emitter
        self.groups = []
        self.items = []

    def group(self, gid, title):
        self.group_id = gid
        if not self.emitter.json_mode:
            print("\n【%s】%s" % (gid, title), file=self.emitter.out, flush=True)

    def item(self, desc, ok, detail=""):
        self.items.append({"group": getattr(self, "group_id", "?"), "desc": desc,
                           "ok": bool(ok), "detail": detail})
        if not self.emitter.json_mode:
            print("  %s %s%s" % ("通过" if ok else "不通过", desc,
                                 ("  —— " + detail) if detail else ""),
                  file=self.emitter.out, flush=True)
        return bool(ok)

    def note(self, text):
        """补一条不与断言绑定的说明（JSON 模式下不打印，保持 stdout 是单个 JSON 文档）。"""
        if not self.emitter.json_mode:
            print(text, file=self.emitter.out, flush=True)


# ─────────────────────────── A：单一真源一致 ───────────────────────────
def group_schema(rep):
    rep.group("A", "单一真源一致（schema ↔ CLI 实际注册 ↔ 实现注册表 ↔ 派生工具定义）")
    report = schema_consistency()
    for c in report["checks"]:
        rep.item("%s %s" % (c["id"], c["desc"]), c["ok"], "" if c["ok"] else c["detail"])
    rep.item("声明命令数 %d ／ 模块数 %d" % (report["commandCount"], report["moduleCount"]),
             report["commandCount"] > 0 and report["moduleCount"] >= 13,
             "12 个业务模块 ＋ 元模块 schema")
    return report["ok"]


# ─────────────────────────── E：退出码语义 ───────────────────────────
def group_exit_codes(rep):
    rep.group("E", "退出码语义（0 成功／2 用户错误／3 需确认／1 内部错误）")

    # ① 缺参 → 2
    p = run_cli(["lists", "by-brand", "--json"], timeout=120)
    rep.item("缺必填参数（lists by-brand 不给 --brand）→ 退出码 %d（期望 %d）"
             % (p.returncode, EXIT_USAGE), p.returncode == EXIT_USAGE,
             "stderr 摘要：" + (p.stderr.strip().splitlines()[-1] if p.stderr.strip() else "无"))

    # ② 非法取值 → 2（这里是"参数不是整数"，由解析器拦下）
    p = run_cli(["lists", "items", "--list-id", "not-a-number", "--json"], timeout=120)
    rep.item("参数类型非法（--list-id not-a-number）→ 退出码 %d（期望 %d）"
             % (p.returncode, EXIT_USAGE), p.returncode == EXIT_USAGE)

    # ③ 写操作无 --confirm → 3，且明确说明没有执行写（这一条**不会**建任何名单）
    p = run_cli(["lists", "create", "--brand", "3690002", "--name", "自检占位-勿建", "--json"],
                timeout=120)
    said_no_write = "没有执行任何写" in (p.stdout + p.stderr)
    rep.item("写操作未加 --confirm → 退出码 %d（期望 %d）且明说未执行写"
             % (p.returncode, EXIT_NEEDS_CONFIRM),
             p.returncode == EXIT_NEEDS_CONFIRM and said_no_write)

    # ④ 写操作带 --confirm 但**账号没有该模块写权限** → 2，且理由说清是哪一轴不满足（零写）
    p = run_cli(["mentions", "run", "--brand", "3690002", "--days", "7", "--confirm", "--json"],
                env={"DANIEL_CLI_AUTH_FIXTURE": viewer_fixture()}, timeout=120)
    doc = _json_or_none(p.stdout)
    reason = ((doc or {}).get("data") or {}).get("reason") or ""
    executed = ((doc or {}).get("data") or {}).get("executed")
    rep.item("无权路径：写命令带 --confirm → 退出码 %d（期望 %d），理由点出角色轴且零写"
             % (p.returncode, EXIT_USAGE),
             p.returncode == EXIT_USAGE and "系统角色" in reason and executed is False,
             "理由摘要：" + (reason[:80] or "无"))

    # ⑤ 受管触发类写命令的**第四道闸（回读）与队列准入**：离线核对"真跑的准入点"。
    #    TICKET-188（A1）之前这一条断言的是"有权路径仍不执行"（当时真实执行未接通、退出码 1）。
    #    A1 接通真实执行后，这条断言随之翻面 —— 但**自检本身绝不许触发真实采集**：
    #    所以这里改成"离线核对两件事"：① 干跑（不带 --confirm）里带出统一队列口径且不占位；
    #    ② 实现层的门禁标记声明了 queueManaged（真跑必须经队列）＋ writeStage=live。
    p = run_cli(["mentions", "run", "--brand", "3690002", "--days", "7", "--json"], timeout=120)
    doc = _json_or_none(p.stdout)
    data = (doc or {}).get("data") or {}
    queue = (data.get("plan") or {}).get("排队") or {}
    from .commands import REGISTRY
    marks = {k: (getattr(REGISTRY.get(k), "_danielWriteGate", None) or {})
             for k in ("mentions.run", "search.submit", "sov.run-exposure", "route.sweep")}
    gated_ok = all(m.get("stage") == "live" and m.get("queueManaged") for m in marks.values())
    rep.item("受管触发类：干跑→退出码 %d（期望 %d）且计划里有队列口径（受管＋并发上限）"
             % (p.returncode, EXIT_NEEDS_CONFIRM),
             p.returncode == EXIT_NEEDS_CONFIRM and queue.get("受管") is True
             and queue.get("本次是否占队列位") is False and data.get("executed") is False
             and isinstance(queue.get("并发上限"), int),
             "队列：受管=%s 并发上限=%s" % (queue.get("受管"), queue.get("并发上限")))
    rep.item("受管触发类四条实现层都声明了 live ＋ queueManaged（真跑必经统一队列）", gated_ok,
             "／".join("%s:%s" % (k, "已声明" if (m.get("stage") == "live"
                                                  and m.get("queueManaged")) else "未声明")
                       for k, m in sorted(marks.items())))

    # ⑥ 只读命令 → 0（用最轻的一条：离线目录清单）
    p = run_cli(["route", "catalog", "--json"], timeout=120)
    rep.item("只读命令 → 退出码 %d（期望 %d）" % (p.returncode, EXIT_OK), p.returncode == EXIT_OK)
    return True


# ─────────────────────────── R + J：只读冒烟与 JSON 可解析 ───────────────────────────
#: R 组并发度（TICKET-151 C1）：12 条只读冒烟全是网络/子进程等待，用线程池**受控并发**即可
#: （无需多进程）。并发度只影响墙钟，**不影响结果**：下面汇总严格按 `SMOKE` 的固定模块顺序输出。
SMOKE_WORKERS_ENV = "DANIEL_SELFTEST_SMOKE_WORKERS"
SMOKE_WORKERS_DEFAULT = 6

#: 失败诊断要打印"原始错误"，但**凭据值不进日志**：只脱掉"键=值"里的值，其余原样保留。
_CRED_SCRUB_RE = re.compile(r"(?i)\b(password|passwd|secret|token|cookie|app_session_id|authorization)"
                            r"(\"?\s*[:=]\s*)\S+")


def _scrub(text):
    """把诊断文本里的"键=值"抹成"键=<已脱敏>"；其余字符原样保留（原始错误照样看得见）。"""
    out = _CRED_SCRUB_RE.sub(lambda m: m.group(1) + m.group(2) + "<已脱敏>", text or "")
    for val in (os.environ.get("DANIEL_PASSWORD"), FAKE_PASSWORD):
        if val:
            out = out.replace(val, "<已脱敏>")
    return out


def smoke_workers():
    """R 组并发度：环境变量优先，非法值退回默认；下限 1（＝串行，便于对照复跑）。"""
    raw = os.environ.get(SMOKE_WORKERS_ENV)
    if raw:
        try:
            n = int(raw)
            if n >= 1:
                return n
        except ValueError:
            pass
    return SMOKE_WORKERS_DEFAULT


def run_cli_smoke(module_key, argv, timeout):
    """跑一条只读冒烟并**把原始错误一起带回**（本函数不抛异常，失败也返回结果字典）。

    返回 {module, argv, rc, stdout, stderr, timed_out, spawn_error}。
    """
    r = {"module": module_key, "argv": list(argv), "rc": None, "stdout": "", "stderr": "",
         "timed_out": False, "spawn_error": ""}
    try:
        p = run_cli(argv, timeout=timeout)
    except subprocess.TimeoutExpired:
        r["timed_out"] = True
        return r
    except OSError as exc:                     # 子进程都起不来（例如解释器路径被删）
        r["spawn_error"] = "子进程启动失败：%s" % exc
        return r
    r.update({"rc": p.returncode, "stdout": p.stdout or "", "stderr": p.stderr or ""})
    return r


def smoke_all(timeout, workers):
    """并发跑全部冒烟，返回 {模块: 结果字典}；键固定，数量恒等于 `SMOKE`（不缺项）。"""
    results = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(SMOKE)))) as pool:
        futures = {pool.submit(run_cli_smoke, k, a, timeout): (k, a) for k, a in SMOKE}
        for fut in as_completed(futures):
            k, a = futures[fut]
            try:
                results[k] = fut.result()
            except Exception as exc:           # 兜底：worker 自身炸了也要记到具体模块上
                results[k] = {"module": k, "argv": list(a), "rc": None, "stdout": "",
                              "stderr": "", "timed_out": False,
                              "spawn_error": "冒烟线程异常：%r" % (exc,)}
    return results


def _err_head(r):
    """取原始错误的最后一行非空 stderr（失败诊断用；无 stderr 则退回 stdout 末行）。"""
    for src in (r.get("stderr"), r.get("stdout")):
        lines = [ln.strip() for ln in (src or "").splitlines() if ln.strip()]
        if lines:
            return _scrub(lines[-1])[:200]
    return "（无 stderr／stdout 输出）"


def group_smoke(rep, timeout=900, workers=None):
    """R 组：12 条只读冒烟**受控并发**，汇总按固定模块顺序（与完成先后无关）。

    失败承诺不变：任一条失败 → 本组返回 False（该步非零退出），并逐条打印**是哪一条**与
    **原始错误**（stderr 原文，凭据值已脱敏）。
    """
    rep.group("R", "12 模块只读子命令可达（真调只读通路或既有只读入口）")
    workers = workers or smoke_workers()
    rep.note("  并发度 %d（纯 I/O 等待的线程池；%s 可覆盖，1＝串行对照）；"
             "汇总顺序固定为契约里的模块顺序，与完成先后无关" % (workers, SMOKE_WORKERS_ENV))
    results = smoke_all(timeout, workers)

    ok_all, payloads, failures = True, {}, []
    for module_key, argv in SMOKE:
        desc = "%s：%s" % (module_key, " ".join(argv))
        r = results.get(module_key) or {"module": module_key, "argv": list(argv), "rc": None,
                                        "stdout": "", "stderr": "", "timed_out": False,
                                        "spawn_error": "冒烟未产出结果"}
        if r["timed_out"]:
            why = "超时（>%ds）" % timeout
            failures.append((r, why))
            ok_all &= rep.item(desc, False, why)
            continue
        if r.get("spawn_error"):
            why = r["spawn_error"]
            failures.append((r, why))
            ok_all &= rep.item(desc, False, why)
            continue
        try:
            doc = json.loads(r["stdout"])
        except ValueError:
            why = "stdout 不是单个 JSON 文档；退出码 %s；原始错误：%s" % (r["rc"], _err_head(r))
            failures.append((r, why))
            ok_all &= rep.item(desc, False, why)
            continue
        payloads[module_key] = doc
        has_result = ("data" in doc) or ("text" in doc)
        ok = r["rc"] == EXIT_OK and doc.get("ok") is True and has_result
        if ok:
            detail = "结果字段：%s" % ("data" if "data" in doc else "text")
        else:
            detail = ("退出码 %s（期望 %s）、ok=%s、结果字段=%s；原始错误：%s"
                      % (r["rc"], EXIT_OK, doc.get("ok"), "有" if has_result else "无", _err_head(r)))
            failures.append((r, detail))
        ok_all &= rep.item(desc, ok, detail)

    if failures:
        rep.note("")
        rep.note("失败明细（哪一条 ＋ 原始错误；凭据值已脱敏，其余原样）：")
        for r, why in failures:
            rep.note("  · %s：%s" % (r["module"], " ".join(r["argv"])))
            rep.note("    %s" % why)
            for ln in [x for x in _scrub(r.get("stderr") or "").splitlines() if x.strip()][-12:]:
                rep.note("    stderr｜ %s" % ln[:400])
            out = _scrub(r.get("stdout") or "").strip()
            if out:
                rep.note("    stdout｜ %s" % out[:400].replace("\n", " "))

    rep.group("J", "`--json` 输出可被 json.loads 整体解析（结果只走 stdout）")
    rep.item("12 个模块的 --json 输出均为单个合法 JSON 文档", len(payloads) == len(SMOKE),
             "解析成功 %d／%d" % (len(payloads), len(SMOKE)))
    bad_envelope = [k for k, d in payloads.items()
                    if not {"ok", "cli", "module", "command", "exitCode"} <= set(d)]
    rep.item("每个 JSON 文档都有统一外层（ok/cli/module/command/exitCode）", not bad_envelope,
             "缺字段：%s" % (bad_envelope or "无"))
    return ok_all and len(payloads) == len(SMOKE)


# ─────────────────────────── Z：零 DSH 依赖 ───────────────────────────
def group_no_dsh(rep):
    rep.group("Z", "零 DSH 依赖（PATH 只留 python3 仍可跑；源码不 import 任何 DSH 模块）")
    p = run_cli(["account", "whoami", "--json"], python_only=True, timeout=300)
    ok = p.returncode == EXIT_OK
    detail = ""
    if ok:
        try:
            doc = json.loads(p.stdout)
            ok = doc.get("ok") is True and bool((doc.get("data") or {}).get("email"))
            detail = "账号字段：" + ("有" if ok else "无")
        except ValueError:
            ok, detail = False, "stdout 不是 JSON"
    else:
        detail = "退出码 %d；stderr 摘要：%s" % (
            p.returncode, (p.stderr.strip().splitlines()[-1] if p.stderr.strip() else "无"))
    rep.item("PATH 只含 python3 时 account whoami --json 仍成功（退出码 %d）" % p.returncode,
             ok, detail)

    pkg = os.path.dirname(os.path.abspath(__file__))
    offenders = []
    for base, _dirs, files in os.walk(pkg):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            text = open(os.path.join(base, fn), encoding="utf-8").read()
            if re.search(r"^\s*(import|from)\s+dsh", text, re.M):
                offenders.append(os.path.relpath(os.path.join(base, fn), pkg))
    rep.item("源码里没有任何 DSH 模块 import", not offenders, "命中：%s" % (offenders or "无"))
    return ok and not offenders


# ─────────────────────────── C：凭据来源矩阵 ───────────────────────────
def group_credentials(rep):
    rep.group("C", "凭据来源矩阵（有钥匙串→keychain；无钥匙串且有 env→env）—— 不写钥匙串")
    creds = load_capability("daniel_credentials")

    real = creds.DanielCredentialStore().status()
    kc = real.get("keychain") or {}
    env_set = bool((real.get("env") or {}).get("set"))
    src = real.get("source")

    if kc.get("available") and kc.get("found"):
        ok = src == "keychain"
        rep.item("本机有钥匙串条目时来源为 keychain（实测 source=%s）" % src, ok,
                 "" if ok else "加密优先被绕过：期望 keychain")
    elif kc.get("available") and env_set:
        ok = src == "env"
        rep.item("钥匙串可用但无条目、且有环境变量时来源为 env（实测 source=%s）" % src, ok)
    else:
        rep.item("本机钥匙串不可用或未配置（source=%s）—— 该分支不作断言，仅记录" % src, True,
                 "可用性：available=%s found=%s env=%s" % (kc.get("available"),
                                                           kc.get("found"), env_set))

    # 模拟"无钥匙串 + 有 env"：把钥匙串 CLI 指到不存在的路径 ＋ PATH 收成只含 python3
    # （`daniel_credentials.py` 默认用绝对路径 /usr/bin/security，只清 PATH 是关不掉它的；
    #   它还有一层"退化为裸命令 security"的兜底，所以两条要一起断掉）
    code = (
        "import sys, json\n"
        "sys.path.insert(0, %r)\n"
        "import importlib.util\n"
        "spec = importlib.util.spec_from_file_location('creds', %r)\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "st = m.DanielCredentialStore().status()\n"
        "print(json.dumps({'source': st['source'], 'keychain_available': st['keychain']['available'],\n"
        "                  'email_masked': st['email_masked']}, ensure_ascii=False))\n"
    ) % (tools_dir(), os.path.join(tools_dir(), "daniel_credentials.py"))
    env = _strip_env(dict(os.environ))
    env["DANIEL_SECURITY_BIN"] = os.path.join(env["PATH"], "security-selftest-absent")
    env["DANIEL_EMAIL"] = FAKE_EMAIL
    env["DANIEL_PASSWORD"] = FAKE_PASSWORD
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env=env, timeout=120)
    try:
        doc = json.loads(p.stdout.strip().splitlines()[-1])
        ok = doc["source"] == "env" and doc["keychain_available"] is False
        rep.item("无钥匙串 + 有环境变量时来源为 env（实测 source=%s、keychain.available=%s）"
                 % (doc["source"], doc["keychain_available"]), ok,
                 "" if ok else "期望 source=env 且 keychain.available=false")
    except (ValueError, IndexError, KeyError):
        ok = False
        rep.item("无钥匙串 + 有环境变量分支断言", False,
                 "子进程输出不可解析：%s" % (p.stdout.strip()[:120] or p.stderr.strip()[:120]))

    # 断言"自检不写钥匙串"：本文件里不得出现任何写入子命令的调用。
    # 判据串**拼接构造**，否则这段检查会把自身当成命中（第一版就踩了这个坑）。
    src_text = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "selftest.py"), encoding="utf-8").read()
    forbidden = ["store" + "-set", "keychain" + "_set", "store" + "_set"]
    hit = [w for w in forbidden if w in src_text]
    no_write = not hit
    rep.item("自检全程不写钥匙串（源码里没有写入子命令的调用）", no_write,
             "命中：%s" % (["<写入子命令>"] * len(hit) if hit else "无"))
    return ok and no_write


# ─────────────────────────── P：契约引擎自证 ───────────────────────────
#: P 组只跑"最小契约"；逐契约期望核对（对例／退化样本／写链三路径）归 `playbook selfcheck`。
#: 幻觉命令契约在临时目录现造，不进仓库。
PB_SMOKE = "engine-smoke"


def _pb_json(p):
    """把一条 playbook 命令的 stdout 解析成 JSON；解析不了返回 None（由调用方记账）。"""
    try:
        return json.loads(p.stdout)
    except ValueError:
        return None


def _gate_types():
    """引擎内置门禁的名字（与 `playbook/model.py` 同源，避免自检夹具写死旧名）。"""
    from .playbook import model as pb_model
    return tuple(pb_model.GATE_TYPES)


def _hallucinated_contract():
    """造一份"引用了不存在命令/参数/写路由"的契约，用来验 D3（只在校验期用，不落仓库）。"""
    return {
        "契约版本": "1.0", "id": "hallucinated", "名称": "幻觉命令契约", "说明": "自检用",
        "输入": [{"名称": "品牌", "类型": "str", "必填": False, "默认": "3690002", "说明": "自检用"}],
        "前置": [{"id": "P1", "说明": "自检用", "断言": {"类型": "存在", "取值": "运行.沙箱目录"}}],
        "步骤": [
            {"id": "S1", "说明": "幻觉命令", "动作": "调用命令", "命令": "brands nonexistent",
             "参数": {}, "读": True, "写": False},
            {"id": "S2", "说明": "幻觉参数", "动作": "调用命令", "命令": "brands show",
             "参数": {"--brand": "3690002", "--nope": 1}, "读": True, "写": False},
            {"id": "S3", "说明": "引用真实写路由", "动作": "调用命令", "命令": "mentions run",
             "参数": {"--brand": "3690002"}, "读": True, "写": False},
        ],
        "判据": [{"id": "C1", "说明": "自检用", "断言": {"类型": "无写发生"}, "必过": True}],
        # 门禁清单与引擎同源：引擎改门禁名时不必手改这份自检夹具（改一次忘一次就会假绿）
        "门禁": [{"id": t, "说明": "自检用"} for t in _gate_types()],
        "交付件schema": {"名称": "占位", "文件名": "p.json", "来源步骤": "S1",
                     "列": ["序号"], "必填列": ["序号"], "行数上限引用": "行数上限"},
        "自检": [{"id": "V1", "说明": "自检用", "断言": {"类型": "计数自洽"}, "必过": True}],
        "失败模式": [{"缺陷类": "CLS-46", "现象": "自检用", "对策": "判据.C1"}],
        "限额": {"行数上限": {"默认": 1, "硬上限": 2, "适用步骤": "S1", "说明": "自检用"}},
        "期望": {"默认": {"结果": "通过", "退出码": 0}},
    }


def group_playbook(rep, timeout=600):
    """P 组：**引擎级最小自证**（P1-6 去重）。

    "逐契约期望核对"（含退化样本与对例）由 `daniel playbook selfcheck` 这一个入口承担
    （`selfcheck.sh` 第 4 步直接调它）；本组只回答"引擎本身还好不好使"：
    能加载契约目录、一条最小契约能跑通且计数自洽、门禁五道齐备、D3 能拒幻觉、零 DSH 依赖。
    """
    rep.group("P", "契约引擎自证（引擎级最小：加载／跑通／门禁齐备／D3 拒幻觉／零 DSH 依赖）")

    def item(desc, p, cond, detail=""):
        return rep.item(desc, cond, detail or ("退出码 %d" % p.returncode))

    # ① 能加载契约目录 + 契约本身都合法
    p = run_cli(["playbook", "list", "--json"], timeout=120)
    doc = _pb_json(p)
    n = ((doc or {}).get("data") or {}).get("契约数") or 0
    item("playbook list 能加载契约目录（契约 %d 份）" % n, p,
         p.returncode == EXIT_OK and n >= 4, "" if doc else "stdout 不是 JSON")

    p = run_cli(["playbook", "validate", "--json"], timeout=120)
    doc = _pb_json(p)
    d = (doc or {}).get("data") or {}
    item("playbook validate 契约全部合法（%s/%s）" % (d.get("通过数"), d.get("校验数")), p,
         p.returncode == EXIT_OK and d.get("通过数") == d.get("校验数") and bool(d.get("校验数")))

    # ② 一条最小契约跑通：判据真评、计数自洽
    p = run_cli(["playbook", "run", PB_SMOKE, "--json"], timeout=timeout)
    doc = _pb_json(p)
    d = (doc or {}).get("data") or {}
    crit = d.get("判据") or {}
    total = (d.get("计数") or {}).get("合计") or {}
    item("最小契约跑通（退出码 %d，期望 %d）" % (p.returncode, EXIT_OK), p,
         p.returncode == EXIT_OK and (d.get("结论") or {}).get("结果") == "通过",
         "" if doc else "stdout 不是 JSON")
    item("报告逐条给出判据明细（%d 条：%s）"
         % (crit.get("实跑项数") or 0,
            "／".join("%s=%s" % (x.get("id"), x.get("状态")) for x in (crit.get("明细") or []))),
         p, bool(crit.get("明细")) and crit.get("失败") == 0)
    item("计数自洽（声明 %s＝实跑 %s＝通过 %s＋失败 %s＋跳过 %s）"
         % (total.get("声明项数"), total.get("实跑项数"), total.get("通过"),
            total.get("失败"), total.get("跳过")), p, bool(total.get("自洽")))

    # ③ 门禁五道齐备（引擎内置门禁一道都不能少，且报告里逐道有结论）
    from .playbook import model as pb_model          # 懒导入：只在 P 组用，且与门禁表同源
    gates = [(g.get("id"), g.get("状态")) for g in ((d.get("门禁") or {}).get("明细") or [])]
    want = list(pb_model.GATE_TYPES)
    item("门禁五道齐备且逐道给出结论（%s）"
         % "／".join("%s=%s" % (g, s) for g, s in gates), p,
         [g for g, _s in gates] == want)

    # ④ 沙箱处置在报告里写明（P0-1：默认自建临时沙箱跑完即清理）
    keep = (d.get("运行") or {}).get("沙箱保留")
    item("报告写明沙箱处置（运行.沙箱保留=%s）" % keep, p,
         keep in ("已清理", "保留", "已不存在") and bool((d.get("运行") or {}).get("沙箱保留理由")))

    # ⑤ D3：引用了不存在命令/参数/写路由的契约，必须在校验期被拒
    tmp = tempfile.mkdtemp(prefix="daniel-playbook-selftest-")
    with open(os.path.join(tmp, "hallucinated.json"), "w", encoding="utf-8") as fh:
        json.dump(_hallucinated_contract(), fh, ensure_ascii=False)
    p = run_cli(["playbook", "validate", "--json"], env={"DANIEL_CONTRACTS_DIR": tmp}, timeout=120)
    said = ("schema 里不存在" in p.stdout) and ("写操作命令" in p.stdout)
    item("D3：契约引用了 schema 没声明的命令/参数/写路由 → 校验期拒绝", p,
         p.returncode == EXIT_USAGE and said)

    # ⑥ 零 DSH 依赖：PATH 只留 python3 也能跑一份契约；源码里不许 import 任何 DSH 模块
    p = run_cli(["playbook", "run", PB_SMOKE, "--json"], python_only=True, timeout=timeout)
    item("PATH 只含 python3 时契约仍跑通", p, p.returncode == EXIT_OK)

    pkg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playbook")
    offenders = []
    for base, _dirs, files in os.walk(pkg):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            text = open(os.path.join(base, fn), encoding="utf-8").read()
            if re.search(r"^\s*(import|from)\s+dsh", text, re.M):
                offenders.append(os.path.relpath(os.path.join(base, fn), pkg))
    rep.item("契约引擎源码里没有任何 DSH 模块 import", not offenders,
             "命中：%s" % (offenders or "无"))
    return not [i for i in rep.items if i["group"] == "P" and not i["ok"]]


# ─────────────────────────── W：权限与门禁（TICKET-152） ───────────────────────────
def _sha256(path):
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def group_permissions(rep, timeout=300):
    """W 组：写链由账号权限决定（能力矩阵、无权路径、删除凭据、审计留痕）。

    三条自我约束：
      · 全部断言**零写入**：只跑读命令、干跑与被拒路径；
      · 降级角色用**注入快照**（临时文件）模拟，不碰任何真实账号；
      · 不在真目标上演练"删除凭据写错"（测试本身不许成为破坏源）——
        那条路径在验收时用**当场新建的临时对象**演练（见回报与说明文档）。
    """
    rep.group("W", "权限与门禁（能力矩阵／无权路径／删除凭据／审计留痕／干跑零写）")
    from . import permissions                      # 懒导入：与判据同源

    # ① 能力矩阵：本机账号（管理角色）12 个业务模块写列应当全开，理由要点出角色轴
    p = run_cli(["account", "capabilities", "--json"], timeout=timeout)
    doc = _json_or_none(p.stdout)
    d = (doc or {}).get("data") or {}
    rows = d.get("能力矩阵") or []
    live_rows = list(rows)
    allowed = [r for r in rows if (r.get("写") or {}).get("是否允许")]
    role_reason = all("systemRole" in ((r.get("写") or {}).get("理由") or "") for r in rows)
    rep.item("权限探针：能力矩阵 %d 个模块、写列放行 %d 个（退出码 %d）"
             % (len(rows), len(allowed), p.returncode),
             p.returncode == EXIT_OK and len(rows) == len(permissions.rule_keys())
             and len(allowed) == len(rows), "理由写角色轴的模块：%s" % ("全部" if role_reason else "有缺"))
    rep.item("能力矩阵每条都给出理由与前端出处",
             all((r.get("写") or {}).get("理由") and r.get("前端出处") for r in rows))

    # ② 降级角色注入：同一份判据必须给出 denied ＋ 明确理由（哪一轴不满足）
    fx = {"DANIEL_CLI_AUTH_FIXTURE": viewer_fixture()}
    p = run_cli(["account", "capabilities", "--json"], env=fx, timeout=timeout)
    doc = _json_or_none(p.stdout)
    rows = ((doc or {}).get("data") or {}).get("能力矩阵") or []
    denied = [r for r in rows if not (r.get("写") or {}).get("是否允许")]
    axis_named = all("系统角色" in ((r.get("写") or {}).get("理由") or "") for r in denied)
    rep.item("降级角色（注入快照）下：%d/%d 个模块写被拒，且理由点出具体轴"
             % (len(denied), len(rows)),
             p.returncode == EXIT_OK and bool(denied) and axis_named,
             "被拒：%s" % "／".join(r["模块"] for r in denied[:6]))

    # ③ 无权模块的读也不放行（用户口径：没有权限的模块就不能使用）
    p = run_cli(["sov", "overview", "--brand", "3690002", "--json"], env=fx, timeout=timeout)
    doc = _json_or_none(p.stdout)
    msg = ((doc or {}).get("error") or {}).get("message") or ""
    rep.item("无权模块的读被拒 → 退出码 %d（期望 %d）且理由可读"
             % (p.returncode, EXIT_USAGE),
             p.returncode == EXIT_USAGE and "没有读权限" in msg and "系统角色" in msg,
             "理由摘要：" + (msg[:70] or "无"))

    # ④ 删除类缺 --delete-token → 2，且**不解析目标、不做任何删除**（确定性、离线）
    p = run_cli(["lists", "delete", "--list-id", "999999999", "--brand", "3690002",
                 "--confirm", "--json"], timeout=timeout)
    doc = _json_or_none(p.stdout)
    d = (doc or {}).get("data") or {}
    rep.item("删除类只给 --confirm、不给 --delete-token → 退出码 %d（期望 %d）且零删除"
             % (p.returncode, EXIT_USAGE),
             p.returncode == EXIT_USAGE and d.get("executed") is False
             and "--delete-token" in (d.get("reason") or ""))

    # ⑤ 删除闸写在帮助里（帮助必须说真话）
    p = run_cli(["lists", "delete", "--help"], timeout=120)
    rep.item("删除类命令的帮助里写明 --delete-token 与「把目标名原样再写一遍」",
             "--delete-token" in p.stdout and "原样再写一遍" in p.stdout)

    # ⑥ 干跑零写：会话文件在干跑前后逐字节一致（写命令不带 --confirm 时零副作用）
    sess = os.path.join(os.environ.get("DANIEL_HOME") or
                        os.path.expanduser("~/.daniel"), "session", "session.json")
    before = _sha256(sess)
    p = run_cli(["account", "login", "--json"], timeout=timeout)
    doc = _json_or_none(p.stdout)
    d = (doc or {}).get("data") or {}
    after = _sha256(sess)
    rep.item("干跑（未加 --confirm）→ 退出码 %d（期望 %d）、executed=false、会话文件未变"
             % (p.returncode, EXIT_NEEDS_CONFIRM),
             p.returncode == EXIT_NEEDS_CONFIRM and d.get("executed") is False and before == after,
             "会话文件指纹：%s → %s" % ((before or "无")[:12], (after or "无")[:12]))

    # ⑦ 审计可导出：字段口径覆盖票面八项
    p = run_cli(["account", "audit", "--json", "--limit", "5"], timeout=120)
    doc = _json_or_none(p.stdout)
    d = (doc or {}).get("data") or {}
    fields = set(d.get("字段口径") or [])
    want = {"time", "account", "workspaceId", "brand", "module", "command", "impact", "readback",
            "rolledBack"}
    rep.item("审计可导出（记录 %d 条）且字段覆盖时间／账号／工作区／品牌／动作／影响范围／回读／回滚"
             % len(d.get("记录") or []),
             p.returncode == EXIT_OK and want <= fields,
             "缺字段：%s" % (sorted(want - fields) or "无"))

    # ⑧ 权限口径同源：能力矩阵的结论 ≡ 写门禁实际调用的判据（用本机账号的矩阵比对）
    auth, _why = permissions.current_auth()
    mismatched = []
    for r in live_rows:
        v = permissions.verdict(r["模块"], permissions.WRITE, auth)
        if v["是否允许"] != (r.get("写") or {}).get("是否允许"):
            mismatched.append(r["模块"])
    rep.item("能力矩阵结论与写门禁调用的判据同源（%d 个模块逐条比对，不存在两套口径）"
             % len(live_rows), not mismatched, "不一致：%s" % (mismatched or "无"))
    return not [i for i in rep.items if i["group"] == "W" and not i["ok"]]


# ─────────────────────────── 入口 ───────────────────────────

def group_module_selftests(rep, timeout=900):
    """把**所有声明了模块自带自检的模块**接进 CLI 总自检（通用化 · 2026-10-15）。

    来源与理由：TICKET-158 先加了一个只覆盖单模块的接线函数；TICKET-159 加了 `skills` 模块、
    TICKET-160 加了 `intake` 模块 —— 后者的 `intake --self-test`（19 项）一度**没进总自检**，
    于是"`daniel --self-test` 全过"并不等于"所有模块自检都过"。
    ⇒ 改成**数据驱动**：凡 `schema` 里声明了 `selfTest` 的模块**自动**纳入本组，
    新增模块不必再手工接线；并加一条**覆盖断言**，防止"声明了却没接线"再次发生。

    口径：**不重写任何模块的判据**，直接调模块自带自检（`commands.selftest_for(key)`）；
    拿不到实现时**报失败**，不倒过来算通过。
    """
    from .schema import SCHEMA
    from .commands import selftest_for
    from .runtime import Emitter
    declared = [m["key"] for m in SCHEMA["modules"] if m.get("selfTest")]
    rep.group("K", "模块自带自检（凡 schema 声明 selfTest 的模块，逐个子进程外调）")
    covered = 0
    for key in declared:
        fn = selftest_for(key)
        if fn is None:
            rep.item("%s 模块自带自检可被调用（schema 声明与实现一致）" % key, False,
                     "拿不到 %s 的自检实现：schema 的 selfTest 声明与 commands 注册表漂移" % key)
            continue
        sub = Emitter(json_mode=True)
        try:
            code = int(fn(sub))
        except Exception as exc:                          # noqa: BLE001
            rep.item("%s 模块自带自检跑通" % key, False, "异常：%s" % str(exc)[:160])
            continue
        detail = ""
        try:
            payload = getattr(sub, "data", None)
            if isinstance(payload, dict):
                detail = str(payload.get("summary") or payload.get("摘要") or "")[:160]
        except Exception:                                 # noqa: BLE001
            detail = ""
        rep.item("%s 模块自带自检跑通（判据真源在模块内，不重写）" % key, code == 0,
                 detail or ("退出码 %d" % code))
        if code == 0:
            covered += 1
    rep.item("声明 selfTest 的模块全部被本组覆盖", covered == len(declared),
             "声明 %d 个（%s）／通过 %d 个" % (len(declared), "、".join(declared) or "无", covered))
    return covered == len(declared)


def run_selftest(emitter):
    rep = _Reporter(emitter)
    if not emitter.json_mode:
        print("Daniel CLI 自检（TICKET-145）", file=emitter.out)
        print("能力目录：%s" % tools_dir(), file=emitter.out)
        print("数据落点：DANIEL_HOME=%s" % (os.environ.get("DANIEL_HOME") or "（未设置，走真源默认）"),
              file=emitter.out)
    results = [
        group_schema(rep),
        group_exit_codes(rep),
        group_smoke(rep),
        group_no_dsh(rep),
        group_credentials(rep),
        group_playbook(rep),
        group_permissions(rep),
        group_module_selftests(rep),
    ]
    passed = sum(1 for x in results if x)
    all_ok = all(results) and all(i["ok"] for i in rep.items)
    failed = [i for i in rep.items if not i["ok"]]
    summary = {"ok": all_ok, "groups": len(results), "groupsPassed": passed,
               "items": len(rep.items), "itemsFailed": len(failed),
               "summary": "全部通过（%d 组／%d 项）" % (len(results), len(rep.items)) if all_ok
                          else "未通过 %d 项：%s" % (len(failed),
                                                  "；".join(i["desc"] for i in failed[:6])),
               "details": rep.items,
               "smokeCommands": [" ".join(a) for _m, a in SMOKE]}
    if emitter.json_mode:
        emitter.result(data=summary, ok=all_ok,
                       exit_code=EXIT_OK if all_ok else EXIT_INTERNAL)
    else:
        print("\n结论：%s" % summary["summary"], file=emitter.out, flush=True)
    return EXIT_OK if all_ok else EXIT_INTERNAL


__all__ = ["run_selftest", "SMOKE", "cli_path", "run_cli", "repo_root", "schema"]
