# -*- coding: utf-8 -*-
"""隔离复现：在**临时 HOME ＋ 哨兵钥匙串服务 ＋ 包副本在源目录之外**下真跑包内入口。

为什么必须这么跑（TICKET-193 的核心教训）
----------------------------------------
`.kol-tools/daniel_paths.py` 的 legacy 落点按**能力目录与它的上一级**算：

    <能力目录>/.daniel_session.json          （legacy 会话 JWT）
    <能力目录>/_cache/brand-index.json       （legacy 品牌索引）
    <上一级>/.daniel_cred.json               （legacy 明文凭据）

于是只要包还待在源目录里跑，"包内能取到真实数据"就可能是**读了源目录里的明文凭据**换来的
—— 那是**假绿**：换到一台真·干净机器上照样跑不起来。本模块用三件事把假绿堵死：

  ① 把包**拷到源目录之外**的临时目录再跑（否则 `<上一级>` 仍指向源目录）；
  ② `HOME` 指向临时目录（模拟新机器：没有会话、没有缓存、没有落点）；
  ③ 钥匙串服务名换成**哨兵名**（`DANIEL_KEYCHAIN_SERVICE`，本机真钥匙串够不着）。

再加一条**反控**：在"无凭据"的那次运行里跑一条只读业务命令（`brands list`），
它**必须取不到真实数据**；若它竟然还能取到（说明存在别的越界回退），本条**报红**。

凭据怎么来（如实写明，不藏）
----------------------------
"包内接入可用"这一条要真取一次数（`connect --doctor` 的第 ④ 项就是"只读命令取到真实数据"），
所以它需要凭据。本模块**只从调用方的环境变量**取（`DANIEL_EMAIL`／`DANIEL_PASSWORD`，
即产品文档里那条"凭据来源②环境变量"），**注入子进程环境、不落盘、不回显**；
调用方没给就**不注入**，并把第 ④ 项如实记为"未取得（未提供凭据）"—— 绝不编造一个绿灯。
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

from ..connect import hosts as connect_hosts
from . import builder

#: 已支持的宿主（唯一真源在 `connect/hosts.py`；这里只取，不写第二份）
SUPPORTED_HOSTS = tuple(connect_hosts.SUPPORTED)

#: 哨兵钥匙串服务名：本机真钥匙串里的 `daniel-copilot` 条目**够不着**（用来模拟"干净机器"）。
SENTINEL_KEYCHAIN_SERVICE = "daniel-pack-isolation-sentinel"

#: 进隔离环境前必须抹掉的环境变量（否则"临时 HOME"是假的）。
_STRIP_ENV = ("DANIEL_HOME", "DANIEL_CLI_TOOLS", "DANIEL_CORPUS_DIR", "DANIEL_CONTRACTS_DIR",
              "DANIEL_ALLOW_PLAINTEXT", "DANIEL_KEYCHAIN_ACCOUNT", "DANIEL_SECURITY_BIN",
              "DANIEL_BASE_URL", "DANIEL_CONNECT_PYTHON", "DANIEL_PLAYBOOK_SANDBOX",
              "PYTHONPATH", "PYTHONHOME")

_CRED_ENV = ("DANIEL_EMAIL", "DANIEL_PASSWORD")


def isolated_env(home, creds=None, interpreter=None):
    """构造隔离子进程的环境：临时 HOME ＋ 哨兵钥匙串服务 ＋ 抹掉本机状态类变量。"""
    env = dict(os.environ)
    for k in _STRIP_ENV:
        env.pop(k, None)
    for k in _CRED_ENV:
        env.pop(k, None)
    env["HOME"] = home
    env["DANIEL_KEYCHAIN_SERVICE"] = SENTINEL_KEYCHAIN_SERVICE
    env["DANIEL_CONNECT_PYTHON"] = interpreter or sys.executable   # 让写进宿主配置的解释器可复算
    if creds:
        email, password = creds
        env["DANIEL_EMAIL"] = email
        env["DANIEL_PASSWORD"] = password
    return env


def _run(argv, env, cwd, timeout=900):
    try:
        p = subprocess.run([str(a) for a in argv], capture_output=True, text=True,
                           timeout=timeout, env=env, cwd=cwd)
        return {"命令": " ".join(str(a) for a in argv), "退出码": p.returncode,
                "stdout": p.stdout or "", "stderr": p.stderr or ""}
    except subprocess.TimeoutExpired:
        return {"命令": " ".join(str(a) for a in argv), "退出码": None,
                "stdout": "", "stderr": "超时（%s 秒）" % timeout}


def _tail(run, lines=8):
    out = [ln for ln in (run["stdout"] or "").strip().splitlines() if ln.strip()]
    err = [ln for ln in (run["stderr"] or "").strip().splitlines() if ln.strip()]
    return {"命令": run["命令"], "退出码": run["退出码"],
            "stdout尾部": out[-lines:], "stderr尾部": err[-4:]}


def _json_of(run):
    try:
        return json.loads(run["stdout"])
    except ValueError:
        return None


def _real_brands(run):
    """这条命令有没有取到**真实数据**（`brands list` 的 JSON 信封里有没有品牌行）。"""
    doc = _json_of(run)
    if not isinstance(doc, dict) or doc.get("ok") is not True:
        return 0
    d = doc.get("data") or {}
    rows = d.get("品牌") or d.get("brands") or d.get("rows") or []
    if isinstance(rows, dict):
        rows = rows.get("品牌") or []
    return len(rows) if isinstance(rows, list) else 0


def reproduce(pack_root, host=None, creds=None, keep=False, interpreter=None):
    """把包拷到源目录之外，在临时 HOME 下跑完 ① ② 与反控，返回结构化结果。

    `host=None` ⇒ **两个宿主都做**（Cursor 与 Codex 各接入一次，再跑不带 `--host` 的
    `connect --doctor`：这样连"跨宿主数据落点一致"那一条也在内，与源仓库基线的 7 项同形）；
    给了 `--host` ⇒ 只做那一个宿主（doctor 也带 `--host`）。
    `creds=None` ⇒ 不做"包内接入可用"的绿灯断言（doctor 第 ④ 项要真取一次数，如实记「未取得」）。
    `keep=True` ⇒ 保留现场（排查用），返回里给出临时目录路径。
    """
    keys = [host] if host else list(SUPPORTED_HOSTS)
    src_pack = os.path.realpath(pack_root)
    work = tempfile.mkdtemp(prefix="daniel-pack-isolation-")
    copy_root = os.path.join(work, "pack")          # 包副本：在源目录之外
    home = os.path.join(work, "home")               # 临时 HOME：模拟新机器
    try:
        shutil.copytree(src_pack, copy_root, symlinks=True)
        os.makedirs(home)
        entry = os.path.join(copy_root, "data", "daniel-cli", "bin", "daniel")
        interp = interpreter or sys.executable

        env_iso = isolated_env(home, creds=None, interpreter=interp)
        env_cred = isolated_env(home, creds=creds, interpreter=interp) if creds else None

        # ── ① 包内可跑（不需要任何凭据）──
        r_version = _run([interp, entry, "--version"], env_iso, copy_root, timeout=300)
        r_schema = _run([interp, entry, "schema", "--check", "--json"], env_iso, copy_root,
                        timeout=600)
        schema_doc = _json_of(r_schema)
        schema_data = (schema_doc or {}).get("data") or {}
        schema_all = bool(schema_doc and schema_doc.get("ok") is True)
        schema_line = "汇总：%s ｜ 命令数 %s ｜ 模块数 %s" % (
            schema_data.get("summary"), schema_data.get("commandCount"),
            schema_data.get("moduleCount"))

        # ── 反控：无凭据时**不得**取到真实数据 ──
        r_leak = _run([interp, entry, "brands", "list", "--limit", "3", "--json"],
                      env_iso, copy_root, timeout=600)
        leaked = _real_brands(r_leak)

        # ── ② 包内接入可用（有凭据时要求全绿；没有则如实记「未取得」）──
        apply_runs, doc_run, doc_doc = [], None, None
        if env_cred is not None:
            for k in keys:
                apply_runs.append(_run(
                    [interp, entry, "connect", "--host", k, "--apply", "--confirm"],
                    env_cred, copy_root, timeout=600))
            argv = [interp, entry, "connect", "--host", host, "--doctor", "--json"] if host else \
                [interp, entry, "connect", "--doctor", "--json"]
            doc_run = _run(argv, env_cred, copy_root, timeout=1800)
            doc_doc = _json_of(doc_run)
        r_skills = _run([interp, entry, "skills", "list", "--json"], env_iso, copy_root, timeout=600)
        skills_doc = _json_of(r_skills)

        doc_data = (doc_doc or {}).get("data") or {}
        doc_items = doc_data.get("检查项") or []
        doc_rows = [{"项": i.get("项"), "通过": i.get("通过"), "证据": (i.get("证据") or "")[:160]}
                    for i in doc_items]
        if doc_doc is not None:
            doc_state = bool(doc_data.get("通过") is True)
            doc_note = doc_data.get("结论") or ""
        elif env_cred is None:
            doc_state, doc_note = None, (
                "未取得（未提供凭据）：doctor 的第 ④ 项「只读命令取到真实数据」要真取一次数，"
                "本命令**不**在没有凭据时编造绿灯")
        else:
            doc_state, doc_note = None, (
                "未取得（`connect --doctor --json` 的输出取不到 JSON）：%s"
                % ((doc_run or {}).get("stderr") or "")[-160:])

        return {
            "工作目录": work,
            "包副本": copy_root,
            "临时 HOME": home,
            "解释器": interp,
            "哨兵钥匙串服务": SENTINEL_KEYCHAIN_SERVICE,
            "是否注入凭据": bool(creds),
            "隔离复现的宿主": keys,
            "步骤": {
                "①-a `--version`": _tail(r_version),
                "①-b `schema --check --json`": _tail(r_schema),
                "反控 无凭据 `brands list`": _tail(r_leak),
                "②-a `connect --host <宿主> --apply --confirm`":
                    ([_tail(r) for r in apply_runs] or "未执行（未提供凭据）"),
                "②-b `connect --doctor --json`": (_tail(doc_run) if doc_run else "未执行（未提供凭据）"),
                "附 `skills list`（随包语料）": _tail(r_skills),
            },
            "断言": {
                "① 包内可跑（--version ＋ schema --check 10/10）":
                    bool(r_version["退出码"] == 0 and r_schema["退出码"] == 0 and schema_all),
                "① 原文": {"version": (r_version["stdout"] or "").strip(),
                           "schema": schema_line},
                "② 包内接入可用（connect ＋ doctor 全绿）": doc_state,
                "② doctor 逐项": doc_rows,
                "② doctor 结论": doc_note,
                "反控 无凭据不得取到真实数据": (leaked == 0),
                "反控 原文": {"取到品牌条数": leaked,
                              "退出码": r_leak["退出码"],
                              "stdout尾部": _tail(r_leak)["stdout尾部"][-2:],
                              "stderr尾部": _tail(r_leak)["stderr尾部"][-2:]},
                "随包语料完整（skills list 完整性=一致）":
                    bool(skills_doc and (skills_doc.get("data") or {}).get("完整性") == "一致"),
            },
            "清理": (None if keep else "已删除临时目录（含包副本与临时 HOME）"),
        }
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)


def pack_absent_from_source(pack_root, source_root):
    """包目录是否落在源目录之外（隔离成立与否的先决条件）。"""
    p = os.path.realpath(pack_root)
    r = os.path.realpath(source_root)
    return not (p == r or p.startswith(r + os.sep))


def write_json_report(path, obj):
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")
