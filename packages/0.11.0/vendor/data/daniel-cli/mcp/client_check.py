#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""脚本化 MCP 客户端：协议级验证（TICKET-153 Part A 第 2 项）。

它证明什么
----------
用**纯标准库**起一个真的 `server.py` 子进程，走 stdio 完成
`initialize` → `notifications/initialized` → `ping` → `tools/list` → `tools/call`，
并且是**键比对**式的断言，不是"看起来跑通了"：

  1. `tools/list` 与 CLI 自己声明的 `daniel schema --mcp --json` 一致 ——
     **两侧条数都打印**，名字集合做集合比对（缺失/多余分别列出）；
  2. 至少一次 `tools/call` 成功：调只读工序 `daniel_playbook_run` 跑
     `minimal-skeleton` 契约，返回结构里含 `data`，并把交付物落到指定目录；
  3. **PATH 里没有 `dsh` 时全部照跑**：自造最小 PATH 复跑一遍 1）与 2），
     证明这条链路零 DSH 依赖（宿主换成 Cursor 时不会因为少一个 npm 全局命令而断）。

用法
----
  python3 data/daniel-cli/mcp/client_check.py                  # 全量协议级检查
  python3 data/daniel-cli/mcp/client_check.py --self-test      # 全量检查 ＋ 正控与退化输入自检
  python3 data/daniel-cli/mcp/client_check.py --playbook --out-dir DIR [--sandbox DIR]
                                                              # 只跑一次 tools/call，产物落 DIR
  python3 data/daniel-cli/mcp/client_check.py --json           # 机器可读汇总

退出码：0 全部通过；2 有检查未过；1 客户端自身出错。
"""
import argparse
import io
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))
PKG_ROOT = os.path.dirname(HERE)                                  # data/daniel-cli
REPO_ROOT = os.path.dirname(os.path.dirname(PKG_ROOT))            # 工作区根
DANIEL_BIN = os.path.join(PKG_ROOT, "bin", "daniel")
SERVER = os.path.join(HERE, "server.py")

#: 路径比较的归一化口（**两侧都要过**，见下的 `_under()`）。
#: 为什么必须有：macOS 上 `/tmp` 是 `/private/tmp` 的软链，而服务端/CLI 报出来的是**真实路径** ——
#: 拿 `"/private/tmp/x".startswith("/tmp/x")` 判会**恒假**（断言写错而不是产品坏了）。
#: 这与 `bin/daniel` 那次 `abspath(__file__)` 不解析软链是**同一类**缺陷：
#: 路径要么两侧都归一化，要么别比。只归一化一侧＝没修。
def _norm(path):
    """归一化用于**比较**的路径（解析软链 ＋ 绝对化）。"""
    return os.path.realpath(os.path.abspath(str(path or "")))


def _under(child, parent):
    """`child` 是否在 `parent` 目录内（**两侧同时归一化**；按目录边界比，不用裸 startswith）。"""
    c, p = _norm(child), _norm(parent)
    return c == p or c.startswith(p.rstrip(os.sep) + os.sep)

PLAYBOOK_TOOL = "daniel_playbook_run"
PLAYBOOK_CONTRACT = "minimal-skeleton"
READ_TIMEOUT = 120.0

#: 「CLI 有、MCP 没有」的差异**显式登记表**（随包分发）。差集与它必须**恰好相等**。
EXPOSURE_REGISTER = os.path.join(HERE, "exposure-register.json")
#: 语料两条工具（名字来自单一真源派生，这里只用于断言它们真的注册了、不是笔误）
CORPUS_LIST_TOOL = "daniel_skills_list"
CORPUS_READ_TOOL = "daniel_skills_read"
#: 语料一致性断言用的样本域与切片（取一束切片体量适中的，便于逐字比对）
CORPUS_SAMPLE_DOMAIN = "kol-screening"
CORPUS_SAMPLE_SECTION = 1
#: 分片断言用的样本（体量最大的一束：一次读完会把宿主上下文淹掉，必须能分片）
CORPUS_BIG_DOMAIN = "kol-discovery"
CORPUS_BIG_SECTION = 1


# ─────────────────────────── 起 server 的方式（可被 --snippet 替换） ───────────────────────────
_SPAWN = None                 # 由 --snippet 载入的注册片段（dict：argv/cwd/env）

#: 片段里"落点类"的变量：最小 PATH 复跑时也要保留，否则两个宿主看到的不是同一套落点
_SNIPPET_KEEP = ("DANIEL_HOME", "DANIEL_CLI_TOOLS", "DANIEL_CONTRACTS_DIR",
                 "DANIEL_PLAYBOOK_SANDBOX")


def spawn_spec(env=None):
    """本次要起的 server 进程的 argv／cwd／env。没有片段时就是本目录的 server.py。"""
    if _SPAWN is None:
        return {"argv": [sys.executable or "python3", SERVER], "cwd": REPO_ROOT,
                "env": env if env is not None else dict(os.environ)}
    merged = dict(os.environ)
    merged.update(_SPAWN.get("env") or {})
    if env is not None:
        merged = dict(env)
        for k in _SNIPPET_KEEP:
            v = (_SPAWN.get("env") or {}).get(k)
            if v:
                merged.setdefault(k, v)
    return {"argv": list(_SPAWN["argv"]), "cwd": _SPAWN.get("cwd") or REPO_ROOT, "env": merged}


def load_snippet(path):
    """读注册片段（`.json` 或含 ```json 代码块的 `.md`），返回 `{argv, cwd, env}`。

    读的是**要交付给总监的那一段原话**，不是另抄一份 —— 这样"片段能不能用"也被脚本证明了。
    """
    text = io.open(path, encoding="utf-8").read()
    doc = None
    try:
        doc = json.loads(text)
    except ValueError:
        m = re.search(r"```json\s*\n(.*?)```", text, re.S)
        if not m:
            raise ValueError("片段里找不到 JSON（既不是 .json，也没有 ```json 代码块）：%s" % path)
        doc = json.loads(m.group(1))
    servers = doc.get("mcpServers") or doc.get("servers") or {}
    if "daniel-copilot" in servers:
        spec = servers["daniel-copilot"]
    elif servers:
        spec = list(servers.values())[0]
    else:
        raise ValueError("片段里没有 mcpServers 条目：%s" % path)
    argv = [spec["command"]] + list(spec.get("args") or [])
    return {"argv": argv, "cwd": spec.get("cwd") or REPO_ROOT, "env": dict(spec.get("env") or {})}


# ─────────────────────────── 一个最小的 stdio MCP 客户端 ───────────────────────────
class McpClient:
    """起 server 子进程，按行收发 JSON-RPC。纯标准库，不依赖任何 MCP SDK。"""

    def __init__(self, env=None, server=SERVER, argv=None, cwd=None):
        spec = spawn_spec(env) if argv is None else {"argv": argv, "cwd": cwd or REPO_ROOT,
                                                     "env": env if env is not None
                                                     else dict(os.environ)}
        self.argv = spec["argv"]
        self.proc = subprocess.Popen(
            self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            env=spec["env"], cwd=spec["cwd"])
        self.inbox = queue.Queue()
        self.stderr_lines = []
        self._closed = False
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self._next_id = 0

    # ── 读 ──
    def _read_stdout(self):
        try:
            for line in self.proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    self.inbox.put(json.loads(line))
                except ValueError:
                    self.inbox.put({"__unparsed__": line})
        except Exception:                                            # noqa: BLE001
            pass
        finally:
            self.inbox.put(None)                                     # EOF 哨兵

    def _read_stderr(self):
        try:
            for line in self.proc.stderr:
                self.stderr_lines.append(line.rstrip("\n"))
        except Exception:                                            # noqa: BLE001
            pass

    def next_message(self, timeout=READ_TIMEOUT):
        try:
            return self.inbox.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError("等待 server 回包超时（%s 秒）" % timeout)

    # ── 写 ──
    def send_raw(self, text):
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()

    def send(self, obj):
        self.send_raw(json.dumps(obj, ensure_ascii=False))

    def notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.send(msg)

    def request(self, method, params=None, timeout=READ_TIMEOUT, rid=None):
        if rid is None:
            self._next_id += 1
            rid = self._next_id
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self.send(msg)
        deadline = time.time() + timeout
        while True:
            left = max(0.1, deadline - time.time())
            got = self.next_message(timeout=left)
            if got is None:
                raise RuntimeError("server 进程提前退出（stderr 末尾：%s）"
                                   % " ｜ ".join(self.stderr_lines[-3:]))
            if isinstance(got, dict) and got.get("id") == rid:
                return got
            # 非本次请求的回包（通知等）忽略

    def expect_silence(self, timeout=1.5):
        """断言在 timeout 内没有任何回包（用于"通知不该有回包"）。"""
        try:
            got = self.next_message(timeout=timeout)
        except TimeoutError:
            return None
        return got

    def initialize(self, protocol="2025-06-18", name="client_check"):
        res = self.request("initialize", {
            "protocolVersion": protocol,
            "capabilities": {"roots": {"listChanged": False}},
            "clientInfo": {"name": name, "version": "0.1.0"},
        })
        self.notify("notifications/initialized")
        return res

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.proc.stdin.close()
        except Exception:                                            # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=10)
        except Exception:                                            # noqa: BLE001
            self.proc.kill()


# ─────────────────────────── 检查台账 ───────────────────────────
class Ledger:
    def __init__(self):
        self.items = []

    def add(self, name, ok, detail=""):
        self.items.append({"name": name, "ok": bool(ok), "detail": detail})
        print(" %s %s%s" % ("[通过]" if ok else "[未过]", name,
                            ("  ｜ " + detail) if detail else ""), flush=True)
        return bool(ok)

    @property
    def passed(self):
        return sum(1 for i in self.items if i["ok"])

    @property
    def total(self):
        return len(self.items)


def _cli_mcp_tools(timeout=180):
    """**独立**从 CLI 读工具清单（另起进程跑 `daniel schema --mcp --json`，不 import 服务端代码）。"""
    p = subprocess.run([sys.executable or "python3", DANIEL_BIN, "schema", "--mcp", "--json"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=REPO_ROOT, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError("`daniel schema --mcp --json` 退出码 %d：%s"
                           % (p.returncode, (p.stderr or "").strip()[:200]))
    return json.loads(p.stdout)["data"]["tools"]


def derive_expected(cli_tools):
    """从 CLI 声明派生**应该**被暴露的工具集（口径的唯一真源＝`daniel_cli/exports.exposure_of`）。

    四档（`TICKET-202`·`Q14` 起：档位一律**先读 `annotations.exposure`**，读不到才回退旧口径）：
      · `read-only`      → 只读，直接执行；
      · `sandbox-only`   → 只读性取决于契约（`playbook run`），**可直接执行**，写只落本次运行沙箱；
      · `local-output`   → **会往本机出件落点写文件、不写 Daniel 远端**（`playbook deliver`），
                           **可直接执行**（不是写链）—— 与"确认单"必须分得开；
      · `confirm-ticket` → 写链，注册为**确认单工具**（永不执行）。

    ⚠️ 回退分支存在的理由（不是兼容包袱）：`exposure` 是 `TICKET-202` 才加的标准键；旧版真源只有
    `readOnlyHint`／`readOnly`。回退让本器在"真源还没升"的包上仍给出正确期望集，而不是把
    `playbook run` 误判成写链（那会把沙箱工序算成确认单 ⇒ 计数与断言全错）。
    """
    strict, dynamic, ticket, local = set(), set(), set(), set()
    for t in cli_tools:
        ann = t.get("annotations") or {}
        exp = ann.get("exposure")
        if exp == "read-only":
            strict.add(t["name"])
        elif exp == "sandbox-only":
            dynamic.add(t["name"])
        elif exp == "local-output":
            local.add(t["name"])
        elif exp == "confirm-ticket":
            ticket.add(t["name"])
        elif ann.get("readOnlyHint") is True:
            strict.add(t["name"])
        elif ann.get("readOnly") == "contract-dependent":
            dynamic.add(t["name"])
        elif ann.get("readOnlyHint") is False:
            ticket.add(t["name"])
    return strict, dynamic, ticket, local


# ─────────── 检查 2b：**同一命令在两个载荷里的暴露口径必须一致**（TICKET-202·Q14）───────────
def exposure_mismatches(cli_tools, host_tools):
    """逐工具比对**自省载荷**（`daniel schema --mcp --json` 的 `annotations`）与**协议面**
    （真实 `tools/list` 的 `annotations` ＋ `_meta.daniel`）的暴露口径，返回不一致清单。

    为什么要这条判据（**防复发**，本条的由头就是门禁当时看不见它）：`S8` 只查"名字唯一／必填项
    在属性里"，两边**各判一次暴露档位**这件事没有任何机器判据守着 ⇒ 实测出现过"`run` 在协议面
    正确、在自省载荷缺标准键 `readOnlyHint`"与"`deliver` 两个载荷都没登记它会写本机文件"。
    判据（纯函数，好造正控）：
      ① 两载荷的**档位相同**（`ann.exposure` ↔ `_meta.daniel.exposure`）；
      ② 两载荷的 **`readOnlyHint` 相同**（缺键 ≠ False，按"缺失"单独报，不然"没写"会被当成"写了 False"）；
      ③ **非纯只读**的档位（`sandbox-only`／`local-output`）两载荷都必须带**注记**（`readOnlyNote`）；
      ④ `local-output` 档在协议面必须 `executes is True`（**可直接执行** —— 注记不得把出件堵死）。
    """
    intro = {t["name"]: (t.get("annotations") or {}) for t in cli_tools}
    out = []
    for t in host_tools:
        name = t.get("name")
        i = intro.get(name)
        if i is None:
            continue                                   # 名字集合的比对由检查 2 负责
        ann = t.get("annotations") or {}
        meta = (t.get("_meta") or {}).get("daniel") or {}
        ie, he = i.get("exposure"), meta.get("exposure")
        if ie != he:
            out.append("%s：档位不一致（自省载荷 exposure=%r ≠ 协议面 exposure=%r）" % (name, ie, he))
        for tag, a, b in (("自省载荷", i, ann),):
            if ("readOnlyHint" in a) != ("readOnlyHint" in b) or a.get("readOnlyHint") != b.get("readOnlyHint"):
                out.append("%s：readOnlyHint 不一致（%s=%r ≠ 协议面=%r）"
                           % (name, tag, a.get("readOnlyHint"), b.get("readOnlyHint")))
        if he in ("sandbox-only", "local-output"):
            if not i.get("readOnlyNote") or not meta.get("readOnlyNote"):
                out.append("%s：档位 %s 缺注记（自省载荷 readOnlyNote=%r／协议面=%r）"
                           % (name, he, bool(i.get("readOnlyNote")), bool(meta.get("readOnlyNote"))))
        if he == "local-output" and meta.get("executes") is not True:
            out.append("%s：local-output 档在协议面必须可直接执行（executes=%r）"
                       % (name, meta.get("executes")))
    return out


def minimal_path():
    """自造最小 PATH：去掉含 `dsh` 可执行文件的目录（保留 python3 与系统目录）。"""
    keep = []
    for d in (os.environ.get("PATH") or "").split(os.pathsep):
        if not d:
            continue
        if os.path.exists(os.path.join(d, "dsh")):
            continue
        keep.append(d)
    base = [d for d in ("/usr/bin", "/bin", "/usr/sbin", "/sbin") if d not in keep]
    return os.pathsep.join(keep + base)


# ─────────────────────────── 检查 0：注册片段本身可用 ───────────────────────────
def check_snippet(led, path):
    """证明**要交付给总监的那段注册片段**本身是能用的（不是另抄一份来测）。"""
    spec = load_snippet(path)
    argv, env = spec["argv"], spec["env"]
    led.add("注册片段：command 是可执行文件",
            os.path.isfile(argv[0]) and os.access(argv[0], os.X_OK),
            "command=%s" % argv[0])
    led.add("注册片段：args[0]（server 入口）真实存在",
            len(argv) > 1 and os.path.isfile(argv[1]),
            argv[1] if len(argv) > 1 else "（缺 args）")
    led.add("注册片段：cwd 真实存在", os.path.isdir(spec["cwd"]), spec["cwd"])
    led.add("注册片段：env 里给了 DANIEL_HOME（两个宿主必须同一数据落点）",
            bool(env.get("DANIEL_HOME")), env.get("DANIEL_HOME") or "（缺）")
    bad = sorted(k for k in env
                 if re.search(r"(?i)password|passwd|secret|token|credential", k))
    led.add("注册片段：不含任何凭据类环境变量", not bad,
            "命中：%s" % ("、".join(bad) if bad else "无"))
    led.add("注册片段：值里不含口令字样",
            not re.search(r"(?i)password|passwd|secret|token", json.dumps(spec, ensure_ascii=False)))
    return spec


# ─────────────────────────── 检查 1：握手 ───────────────────────────
def check_handshake(led, env=None, tag=""):
    c = McpClient(env=env)
    try:
        res = c.initialize()
        r = res.get("result") or {}
        led.add("%s握手：initialize 回包有 protocolVersion／capabilities／serverInfo" % tag,
                bool(r.get("protocolVersion")
                     and "tools" in (r.get("capabilities") or {})
                     and (r.get("serverInfo") or {}).get("name")),
                "protocolVersion=%s ｜ serverInfo=%s ｜ 工具能力=%s"
                % (r.get("protocolVersion"), (r.get("serverInfo") or {}).get("name"),
                   json.dumps((r.get("capabilities") or {}).get("tools"), ensure_ascii=False)))
        ins = r.get("instructions") or ""
        # TICKET-161：原断言是「instructions 写明『写链在 Cursor 宿主内暂不暴露』」——
        # 161 落地后那句话成了假话（写链已注册为确认单工具）。**不是删掉这条断言，
        # 而是换成更硬的两条**：能力面全量可见 ＋ 写链只出确认单。
        led.add("%s握手：instructions 写明「写链＝确认单通道」（写链已注册，不是「不暴露」）" % tag,
                "确认单" in ins and "永不执行" in ins and "永不转发" in ins
                and "暂不暴露" not in ins,
                "长度 %d 字" % len(ins))
        led.add("%s握手：instructions 写明两种模式的定位（CLI＝完整能力集成／MCP＝Daniel 接入面）" % tag,
                "CLI＝完整能力集成的落地形态" in ins and "MCP＝Daniel 数据层接入面" in ins
                and "能力面上**完全一样**" in ins,
                "含定位口径：是" if "MCP＝Daniel 数据层接入面" in ins else "缺定位口径")
        pong = c.request("ping")
        led.add("%s握手：ping 回空 result" % tag, pong.get("result") == {},
                json.dumps(pong.get("result"), ensure_ascii=False))
    finally:
        c.close()
    return c


# ─────────────────────────── 检查 2：tools/list ≡ schema ───────────────────────────
def check_tools_list(led, env=None, tag="", cli_tools=None):
    cli_tools = cli_tools if cli_tools is not None else _cli_mcp_tools()
    strict, dynamic, ticket, local = derive_expected(cli_tools)
    expected = strict | dynamic | ticket | local
    c = McpClient(env=env)
    try:
        c.initialize()
        res = c.request("tools/list")
        tools = (res.get("result") or {}).get("tools") or []
        got = {t.get("name") for t in tools}
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        led.add("%s清单一致：tools/list 名字集合 ≡ schema 派生集合（键比对）" % tag,
                not missing and not extra,
                "CLI 声明 %d 条 ｜ 派生期望 %d 条（固定只读 %d ＋ 沙箱只读 %d ＋ 本机出件 %d ＋ 确认单 %d）"
                "｜ 目录实收 %d 条 ｜ 缺失 %d 条 ｜ 多余 %d 条"
                % (len(cli_tools), len(expected), len(strict), len(dynamic), len(local), len(ticket),
                   len(got), len(missing), len(extra)))
        if missing:
            print("     缺失：%s" % "、".join(missing))
        if extra:
            print("     多余：%s" % "、".join(extra))
        led.add("%s清单一致：条数键比对（实收 == 派生）" % tag,
                len(got) == len(expected) and len(tools) == len(got),
                "tools/list 条目 %d 个 ｜ 去重后名字 %d 个 ｜ 派生 %d 个"
                % (len(tools), len(got), len(expected)))
        led.add("%s清单一致：固定只读命令一条不漏（readOnlyHint is True 全部在目录里）" % tag,
                strict <= got, "固定只读 %d 条，命中 %d 条" % (len(strict), len(strict & got)))
        # ── TICKET-161：原断言是「没有任何 live／gated 写链工具被注册」——
        # 161 落地后那条成了假话（13 条写链就是要注册）。**换成更硬的三条**：
        # 写链全部注册；每条都标成确认单（executes=false）；每条描述都写明「不会执行」。
        by_name = {t["name"]: t for t in tools}
        writes_missing = sorted(ticket - got)
        # 标签里不写死条数：写链条数会随能力增长（161 时 13 条，170 落地后 14 条）——
        # 写死数字的断言名迟早变假话，条数一律走 detail 动态打印。
        led.add("%s清单一致（161）：写链**全部**注册为确认单工具（能力面全量可见）" % tag,
                not writes_missing, "派生写链 %d 条 ｜ 目录实收 %d 条%s"
                % (len(ticket), len(ticket & got),
                   ("；缺失：" + "、".join(writes_missing)) if writes_missing else ""))
        bad_meta = []
        for name in sorted(ticket & got):
            meta = ((by_name[name].get("_meta") or {}).get("daniel") or {})
            ann = by_name[name].get("annotations") or {}
            if (meta.get("exposure") != "confirm-ticket" or meta.get("executes") is not False
                    or ann.get("destructiveHint") is not False
                    or ann.get("readOnlyHint") is not False):
                bad_meta.append("%s(exposure=%s,executes=%s,ro=%s,des=%s)"
                                % (name, meta.get("exposure"), meta.get("executes"),
                                   ann.get("readOnlyHint"), ann.get("destructiveHint")))
        led.add("%s清单一致（161）：确认单工具的注解不说谎"
                "（exposure=confirm-ticket／executes=false／readOnlyHint=false／destructiveHint=false）" % tag,
                not bad_meta, "异常：%s" % ("、".join(bad_meta) if bad_meta else
                                           "无（%d 条逐条核对）" % len(ticket & got)))
        no_warn = sorted(n for n in (ticket & got)
                         if "不会执行" not in (by_name[n].get("description") or ""))
        led.add("%s清单一致（161）：每条确认单工具的 description 都写明「不会执行」" % tag,
                not no_warn, "未写明：%s" % ("、".join(no_warn) if no_warn else
                                           "无（%d 条全部写明）" % len(ticket & got)))
        # 沙箱只读那条必须真的 writeStage == sandbox（既有的守门，保留）
        leaked = []
        for t in tools:
            meta = ((t.get("_meta") or {}).get("daniel") or {})
            if meta.get("exposure") == "sandbox-only" and meta.get("writeStage") != "sandbox":
                leaked.append(t.get("name"))
        led.add("%s清单一致：标注为沙箱只读的那条真的是 writeStage == sandbox" % tag, not leaked,
                "泄漏：%s" % ("、".join(leaked) if leaked else "无"))
        # ── TICKET-202·Q14：**两个载荷的暴露口径必须一致**（防复发：S8 看不见这一条）──
        mism = exposure_mismatches(cli_tools, tools)
        led.add("%s清单一致（202）：同一命令在**两个载荷**里的暴露口径一致"
                "（档位／readOnlyHint／非纯只读必带注记／本机出件档可直接执行）" % tag,
                not mism, "不一致：%s" % ("；".join(mism) if mism else
                                          "无（%d 条逐条比对自省载荷 ↔ 协议面）" % len(tools)))
        if mism:
            for m in mism[:6]:
                print("     口径不一致：%s" % m)
        # inputSchema 与真源的关系：**逐字一致**，唯一例外是确认单工具按真源的
        # `writeOnly` 标记**投影掉敏感参数**（确认单永不执行 ⇒ 敏感参数无用途，只留泄漏面）。
        by_src = {t["name"]: t for t in cli_tools}
        drift, bad_drop = [], []
        for t in tools:
            src = by_src.get(t["name"])
            if src is None:
                continue
            meta = ((t.get("_meta") or {}).get("daniel") or {})
            if meta.get("exposure") != "confirm-ticket":
                if t["inputSchema"] != src["inputSchema"]:
                    drift.append(t["name"])
                continue
            secret = {k for k, v in (src["inputSchema"].get("properties") or {}).items()
                      if isinstance(v, dict) and v.get("writeOnly")}
            want = dict(src["inputSchema"])
            want["properties"] = {k: v for k, v in
                                 (src["inputSchema"].get("properties") or {}).items()
                                 if k not in secret}
            want["required"] = [k for k in (src["inputSchema"].get("required") or [])
                                if k not in secret]
            if t["inputSchema"] != want:
                drift.append(t["name"])
            if set(meta.get("droppedSecretParams") or []) != secret:
                bad_drop.append("%s：剔除 %s ≠ 真源 writeOnly %s"
                                % (t["name"], sorted(meta.get("droppedSecretParams") or []),
                                   sorted(secret)))
        led.add("%s清单一致：inputSchema ≡ 单一真源"
                "（确认单工具只按真源 writeOnly 标记投影掉敏感参数，剔除项已登记）" % tag,
                not drift and not bad_drop,
                "漂移：%s%s" % ("、".join(drift) if drift else "无",
                              ("；剔除不符：" + "；".join(bad_drop)) if bad_drop else ""))
        return got
    finally:
        c.close()


# ─────────────────────────── 检查 3：tools/call 跑通只读工序 ───────────────────────────
def check_tools_call(led, out_dir, sandbox=None, env=None, tag="", contract=None):
    os.makedirs(out_dir, exist_ok=True)
    report = os.path.join(out_dir, "report.json")
    contract = contract or PLAYBOOK_CONTRACT
    child_env = dict(env if env is not None else os.environ)
    if sandbox:
        child_env["DANIEL_PLAYBOOK_SANDBOX"] = sandbox
    c = McpClient(env=child_env)
    summary = {}
    try:
        c.initialize()
        res = c.request("tools/call", {"name": PLAYBOOK_TOOL,
                                       "arguments": {"name": contract, "out": report}},
                        timeout=300)
        if "error" in res:
            led.add("%stools/call：调 %s 成功（isError=false）" % (tag, PLAYBOOK_TOOL), False,
                    "收到协议错误：%s" % json.dumps(res["error"], ensure_ascii=False)[:200])
            return None
        r = res.get("result") or {}
        led.add("%stools/call：调 %s 成功（isError=false）" % (tag, PLAYBOOK_TOOL),
                r.get("isError") is False,
                "退出码=%s" % ((r.get("_meta") or {}).get("daniel") or {}).get("exitCode"))
        sc = r.get("structuredContent") or {}
        data = sc.get("data")
        led.add("%stools/call：返回结构含 data（dict）" % tag,
                isinstance(data, dict) and len(data) > 0,
                "data 字段 %d 个：%s" % (len(data or {}), "、".join(list((data or {}).keys())[:8])))
        text = "".join(b.get("text", "") for b in (r.get("content") or []))
        led.add("%stools/call：文本内容含可读摘要与结构化 JSON" % tag,
                "退出码：0" in text and "--- 结构化结果（JSON）---" in text,
                "文本 %d 字" % len(text))
        if not isinstance(data, dict):
            return None
        art = data.get("交付件") or {}
        led.add("%stools/call：交付物落盘（交付件.路径）" % tag,
                bool(art.get("路径")) and os.path.isfile(art["路径"]),
                "路径 %s ｜ 行数 %s ｜ 校验 %s" % (art.get("路径"), art.get("行数"), art.get("校验")))
        led.add("%stools/call：运行报告按 --out 落到指定文件" % tag,
                os.path.isfile(report), report)
        if os.path.isfile(report):
            disk = json.load(io.open(report, encoding="utf-8"))
            onwire = dict(data)
            onwire.pop("报告落点", None)
            led.add("%stools/call：落盘报告 ≡ 工具返回的 data（键与取值一致）" % tag,
                    disk == onwire, "文件 %d 字段 ｜ 返回 %d 字段" % (len(disk), len(onwire)))
        cnt = (data.get("计数") or {}).get("合计") or {}
        concl = data.get("结论") or {}
        led.add("%stools/call：工序自洽（计数自洽＋判据/门禁/自检全过）" % tag,
                bool(concl.get("通过")) and bool(cnt.get("自洽")),
                "计数 声明 %s＝实跑 %s＝通过 %s＋失败 %s＋跳过 %s ｜ 结论 %s"
                % (cnt.get("声明项数"), cnt.get("实跑项数"), cnt.get("通过"),
                   cnt.get("失败"), cnt.get("跳过"), concl.get("摘要")))
        summary = {"contract": contract, "report": report, "deliverable": art.get("路径"),
                   "rows": art.get("行数"), "fields": len(data),
                   "conclusion": concl.get("摘要"), "counts": cnt}
    finally:
        c.close()
    return summary


# ─────────────────────────── 检查 5：差异显式登记（CLI 命令集 vs MCP 工具集） ───────────────────────────
def _cli_command_of(tool):
    """从派生注解里的 `cli` 字符串取回「模块 子命令」（`daniel brands create --name <名称> --json`）。"""
    cli = ((tool.get("annotations") or {}).get("cli") or "").split()
    return " ".join(cli[1:3]) if len(cli) >= 3 else ""


def check_exposure_register(led, cli_tools, registered):
    """第 3 组：**写链暴露口径的登记表**必须与盘面一致（双向断言 ＋ 三条新牙齿）。

    TICKET-159 立的口径是「CLI 命令集 ⊖ MCP 工具集 ≡ 登记表」。TICKET-161 把写链注册成
    确认单工具后**差集归零**，于是登记表登记的东西换成了「每一条写命令的**执行语义**」
    （`执行`／`确认单不执行`／`未注册`），断言口径也随之显式化 ——
    与 `daniel_cli/intake/modes.py:read_exposure_register()` **同一口径**（消除第二真源）：

      A1 字段齐备（命令／工具名／执行语义／暴露形态／动作类型／替代路径／说明）＋ 执行语义取值合法；
      A2 **漏登记**：差集 ⊆ 「执行语义=未注册」条目（差集里出现登记表之外的条目＝红）；
      A3 **陈旧／不实登记**：「执行语义=未注册」条目 ⊆ 差集（登记为未注册却真的注册了＝红）；
      A4 **陈旧登记**：登记的命令必须仍在 CLI 声明里，且「命令」与「工具名」自洽（不是手抄的第二份名字）；
      A5 **不实登记（TICKET-161 新增）**：登记为「确认单不执行」的每条，必须在 MCP 侧真注册、
         且 `_meta.exposure == confirm-ticket`、且工具 description 里写明「不会执行」
         —— 否则说明它要么根本没暴露（假话"可见"）、要么悄悄会执行（真缺陷）；
      A6 **登记不全（TICKET-161 新增）**：CLI 声明的每一条写命令都必须有登记条目
         —— 否则就是有人往能力面里加了写链却没人登记它的执行语义。

    **只删不换等于把闸门做空**：上面 A2／A3 保留了 159 的双向差集断言（差集归零时它们
    依然要成立），A5／A6 是把 161 的新事实（写链已注册但永不执行）变成会红的断言。
    """
    if not os.path.isfile(EXPOSURE_REGISTER):
        led.add("登记表存在：%s" % EXPOSURE_REGISTER, False, "随包分发的差异登记表缺失")
        return None
    try:
        reg = json.load(io.open(EXPOSURE_REGISTER, encoding="utf-8"))
    except ValueError as e:
        led.add("登记表可解析：%s" % EXPOSURE_REGISTER, False, "JSON 解析失败：%s" % e)
        return None

    allowed = set(reg.get("执行语义取值集合") or [])
    entries = reg.get("entries") or []
    by_name = {t["name"]: t for t in cli_tools}
    REQUIRED = ("命令", "工具名", "执行语义", "暴露形态", "动作类型", "替代路径", "说明")

    # A1 字段齐备 + 执行语义合法
    problems = []
    for e in entries:
        for key in REQUIRED:
            if not e.get(key):
                problems.append("%s：缺 %s" % (e.get("工具名") or e.get("命令") or "（无名字）", key))
        if e.get("执行语义") and e["执行语义"] not in allowed:
            problems.append("%s：执行语义 %r 不在允许集合 %s"
                            % (e.get("工具名"), e["执行语义"], "／".join(sorted(allowed))))
    led.add("登记表字段齐备且执行语义取值合法（%s）" % "／".join(sorted(allowed)),
            not problems, "；".join(problems[:5]) if problems
            else "%d 条登记，字段与取值齐备" % len(entries))

    # A4 工具名与命令自洽（防止登记表成为手抄的第二份名字）
    mismatch = []
    for e in entries:
        t = by_name.get(e.get("工具名"))
        if t is None:
            mismatch.append("%s：CLI 声明里没有这个工具名（命令已不存在？）" % e.get("工具名"))
            continue
        if _cli_command_of(t) != e.get("命令"):
            mismatch.append("%s：登记的命令 %r 与派生的 %r 不一致"
                            % (e.get("工具名"), e.get("命令"), _cli_command_of(t)))
    led.add("登记表的「命令」与「工具名」与单向真源自洽（不是手抄的第二份名字）",
            not mismatch, "；".join(mismatch[:5]) if mismatch else "%d 条逐条对上" % len(entries))

    # A2 / A3 双向差集比对（口径：只有「执行语义=未注册」的子集参与差集比对）
    declared = set(by_name)
    diff = declared - set(registered)
    listed = {e.get("工具名") for e in entries}
    unregistered = {e.get("工具名") for e in entries
                    if str(e.get("执行语义") or "") == "未注册"}
    unlisted = sorted(diff - unregistered)
    stale = sorted(unregistered - diff)
    led.add("A2 漏登记：差集 ⊆ 登记表「未注册」集合（没有能力被悄悄藏掉或漏登记）",
            not unlisted,
            "差集 %d 条 ｜ 未登记 %d 条%s" % (len(diff), len(unlisted),
                                          ("：" + "、".join(unlisted)) if unlisted else ""))
    led.add("A3 陈旧／不实登记：登记表「未注册」集合 ⊆ 差集"
            "（登记为未注册却真的注册了＝红；也挡住「已不存在的命令留在表里」）",
            not stale,
            "登记「未注册」%d 条 ｜ 陈旧 %d 条%s" % (len(unregistered), len(stale),
                                                ("：" + "、".join(stale)) if stale else ""))
    stale_entries = sorted(listed - declared)
    led.add("A3b 陈旧登记：登记表里的命令都还在 CLI 声明里（已删除的命令不许留在表里）",
            not stale_entries,
            "陈旧条目：%s" % ("、".join(stale_entries) if stale_entries else
                             "无（%d 条都在）" % len(listed)))

    # A5 不实登记：登记为「确认单不执行」的必须真注册 + 真标成确认单 + 描述写明不会执行
    # 判据取**宿主侧真实看到的** tools/list（不是 CLI 派生件），因为这条要证的正是"宿主看得见"。
    live = _live_tool_map()
    bad = []
    for e in entries:
        if str(e.get("执行语义") or "") != "确认单不执行":
            continue
        name = e.get("工具名")
        if name not in registered:
            bad.append("%s：登记为「确认单不执行」却**没有注册**（能力面上看不见＝假话）" % name)
            continue
        t = (live or {}).get(name)
        if t is None:
            bad.append("%s：tools/list 里取不到它的暴露口径（无法证明「确认单不执行」）" % name)
            continue
        meta = ((t.get("_meta") or {}).get("daniel") or {})
        if meta.get("exposure") != "confirm-ticket" or meta.get("executes") is not False:
            bad.append("%s：exposure=%s／executes=%s（不是确认单口径）"
                       % (name, meta.get("exposure"), meta.get("executes")))
        if "不会执行" not in (t.get("description") or ""):
            bad.append("%s：description 没写明「不会执行」" % name)
    n_confirm = sum(1 for e in entries if str(e.get("执行语义") or "") == "确认单不执行")
    led.add("A5 不实登记：登记为「确认单不执行」的每条都真注册、真标成确认单、描述写明「不会执行」",
            not bad, "；".join(bad[:4]) if bad
            else "%d 条逐条对上（真注册 ＋ exposure=confirm-ticket ＋ 描述含「不会执行」）" % n_confirm)

    # A6 登记不全：CLI 声明的每条写命令都必须有登记条目
    write_tools = {t["name"] for t in cli_tools
                   if (t.get("annotations") or {}).get("readOnlyHint") is False
                   or (t.get("annotations") or {}).get("readOnly") == "contract-dependent"}
    unlisted_writes = sorted(write_tools - listed)
    led.add("A6 登记不全：CLI 声明的每条写命令都有登记条目（执行语义一条不漏）",
            not unlisted_writes, "写命令 %d 条 ｜ 未登记 %d 条%s"
            % (len(write_tools), len(unlisted_writes),
               ("：" + "、".join(unlisted_writes)) if unlisted_writes else ""))

    print("     登记表口径：差集 %d 条（登记「未注册」%d 条）｜ 已注册工具 %d 条 ｜ CLI 声明 %d 条"
          % (len(diff), len(unregistered), len(registered), len(declared)))
    for e in entries:
        print("       · %-22s 执行语义=%s ｜ 动作类型=%s ｜ 替代路径=%s"
              % (e.get("命令"), e.get("执行语义"), e.get("动作类型"),
                 (e.get("替代路径") or "")[:52]))
    return {"diff": sorted(diff), "registered": len(registered), "declared": len(declared)}


def _live_tool_map(env=None, timeout=120):
    """**宿主侧真实看到的**工具定义：走协议 `tools/list` 取一份 `{工具名: 定义}`。

    为什么另开这条口（而不是复用 `registered`）：第 3 组的 A5 要证的是
    「宿主真的看得见、且真的标成了确认单」—— 那必须以宿主侧看到的为准。
    """
    c = McpClient(env=env)
    try:
        c.initialize()
        res = c.request("tools/list", timeout=timeout)
        tools = (res.get("result") or {}).get("tools") or []
        return {t.get("name"): t for t in tools}
    finally:
        c.close()


# ─────────────── 检查 2.5：确认单里印出的命令真能在 CLI 上跑通（TICKET-161 判据） ───────────────
def check_ticket_commands(led, tag="", cli_tools=None):
    """确认单里印出的「将执行的确切命令」必须**真的能在 CLI 上跑通**。

    判据（总监 2026-10-15 追加）：**印出来一条不存在的命令，比不印更糟**。
    最危险的是三级子命令 —— 把 `account credentials set` 拼成 `daniel account set --confirm`
    就是一条不存在的命令（TICKET-170 报的真实风险）。

    两层判据，都**离线、零副作用、不带任何业务实参**：
      ① 结构性：每条写链工具派生的 `cli` 前三个 token 必须 ≡ `daniel <模块> <子命令>`，
         且 `模块 子命令` 确实在 CLI 声明里（键比对，与 `schema --check` 的 S9 同一思路）；
      ② 行为性：`daniel <模块> <子命令> --help` 必须**退出码 0**（CLI 解析器认得它）。
    并配**负控**：一条不存在的命令（`daniel account set --help`）必须**退出码 2** ——
    否则这条断言是空的（"什么都能过"的断言等于没断言）。
    """
    cli_tools = cli_tools if cli_tools is not None else _cli_mcp_tools()
    writes = [t for t in cli_tools
              if (t.get("annotations") or {}).get("readOnlyHint") is False]
    declared = {_cli_command_of(t) for t in cli_tools if _cli_command_of(t)}
    mismatched, unrunnable = [], []
    for t in writes:
        parts = ((t.get("annotations") or {}).get("cli") or "").split()
        if len(parts) < 3 or parts[0] != "daniel":
            mismatched.append("%s：注解 cli 形状不对（%r）" % (t["name"], " ".join(parts[:3])))
            continue
        key = "%s %s" % (parts[1], parts[2])
        if key not in declared:
            mismatched.append("%s：%s 不在 CLI 声明里" % (t["name"], key))
            continue
        p = subprocess.run([sys.executable or "python3", DANIEL_BIN, parts[1], parts[2], "--help"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           cwd=REPO_ROOT, timeout=120)
        if p.returncode != 0:
            unrunnable.append("%s：`daniel %s --help` 退出码 %d" % (t["name"], key, p.returncode))
    led.add("%s[161] 确认单命令可解析：写链工具的 `daniel <模块> <子命令>` 全部在 CLI 声明里" % tag,
            not mismatched, "；".join(mismatched[:3]) if mismatched
            else "%d 条逐条对上" % len(writes))
    led.add("%s[161] 确认单命令可跑通：`daniel <模块> <子命令> --help` 对 %d 条写链全部退出码 0"
            % (tag, len(writes)),
            not unrunnable and bool(writes),
            "；".join(unrunnable[:3]) if unrunnable else "全部退出码 0（真问过 CLI 解析器）")
    # 负控：不存在的命令必须被拒 —— 证明上面那条不是"什么都能过"
    neg = subprocess.run([sys.executable or "python3", DANIEL_BIN, "account", "set", "--help"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         cwd=REPO_ROOT, timeout=120)
    led.add("%s[161] 负控：不存在的命令（daniel account set --help）退出码 2"
            "（证明上面那条断言有分辨力）" % tag,
            neg.returncode == 2, "退出码 %d" % neg.returncode)


# ─────────────── 检查 9：写链＝确认单（TICKET-161·行为断言 ＋ 零副作用） ───────────────
#: 本组要真调的确认单工具（选三条有代表性的，覆盖三种写风险）：
#:   · `lists create`   —— 写 Daniel 记录（TICKET-152 曾在此出过意外真写，CLS-78）；
#:   · `search submit`  —— 触发采集（会消耗额度，绝不能真跑）；
#:   · `brands delete`  —— 删除类（不可逆，绝不能真跑）。
CONFIRM_TICKET_CALLS = (
    ("daniel_lists_create", {"brand": "3690002", "name": "TICKET-161-零副作用探针-勿用"},
     "写 Daniel 记录"),
    ("daniel_search_submit", {"brand": "3690002", "query": "TICKET-161 零副作用探针"}, "触发采集"),
    ("daniel_brands_delete", {"brand": "3690002"}, "删除类"),
    # TICKET-170 新增的写命令。它对"印出的命令必须真能跑"这条判据最敏感
    # （三级子命令曾拼出 `daniel account set --confirm` 这种不存在的命令），
    # 也是 161 里唯一会印出 `--password` 字样的确认单 ⇒ 顺带验证"不误判选项名为凭据"。
    ("daniel_account_credentials_set", {"from_env": True}, "其他（本机副作用）"),
)
#: 确认单必备字段（与 server.py 的 `TICKET_FIELDS` 同口径；这里独立写死，避免"自己证自己"）
TICKET_FIELDS = ("将执行的确切命令", "动作类型", "影响面", "不可逆性", "所需前置", "替代路径")
IMPACT_FIELDS = ("目标工作区", "目标对象", "条数", "是否消耗配额", "只读预查")


def check_confirm_ticket(led, tag="", brand="3690002"):
    """TICKET-161 的行为断言：确认单工具**真调**，返回的是确认单形状，且**零副作用**。

    零副作用的取证方式（这是本票第一验收项）：
      ① 调 **前**：`daniel lists by-brand --brand <品牌>` 记下名单数与名单名集合；
         `daniel account audit --limit 1` 记下写审计的「真执行」计数；
      ② 经**协议真调**三条确认单工具（写记录／触发采集／删除类各一条）；
      ③ 调 **后**：同样两条只读命令再读一次 —— 名单数与集合必须完全不变、
         写审计的「真执行」计数必须**没有增加**（CLI 自己的写审计就是第三方证人）；
      ④ 断言三条返回体都是确认单形状、`_meta.executed == false`、退出码语义 3＝需确认。
    """
    before = _readback(brand)
    write_keys = {"%s.%s" % (m, c) for m, c in _write_command_pairs()}
    calls = []
    c = McpClient()
    try:
        c.initialize()
        tl = c.request("tools/list")
        names = {t.get("name") for t in ((tl.get("result") or {}).get("tools") or [])}
        for tool, args, action in CONFIRM_TICKET_CALLS:
            led.add("%s[161] 确认单工具已注册：%s（%s）" % (tag, tool, action),
                    tool in names, "tools/list 共 %d 条" % len(names))
            res = c.request("tools/call", {"name": tool, "arguments": args}, timeout=600)
            if "error" in res:
                led.add("%s[161] %s 调用返回协议错误（不该发生）" % (tag, tool), False,
                        json.dumps(res["error"], ensure_ascii=False)[:200])
                continue
            r = res.get("result") or {}
            ticket = ((r.get("structuredContent") or {}).get("确认单")) or {}
            meta = ((r.get("_meta") or {}).get("daniel") or {})
            text = "".join(b.get("text", "") for b in (r.get("content") or []))
            calls.append((tool, ticket, meta, text))
            # ① 形状：六个必备字段 + 影响面五个字段
            led.add("%s[161] %s：返回体是确认单形状（六个必备字段齐备）" % (tag, tool),
                    all(f in ticket for f in TICKET_FIELDS)
                    and all(k in (ticket.get("影响面") or {}) for k in IMPACT_FIELDS),
                    "字段：%s" % "、".join(f for f in TICKET_FIELDS if f in ticket))
            # ② 永不执行 + 退出码语义＝需确认（**不是**成功）
            led.add("%s[161] %s：永不执行且退出码语义＝需确认（没有包装成成功）" % (tag, tool),
                    ticket.get("是否执行") is False
                    and (ticket.get("退出码语义") or {}).get("退出码") == 3
                    and meta.get("executed") is False
                    and meta.get("exitCode") == 3
                    and text.startswith("Daniel 确认单工具")
                    and "未执行" in text,
                    "是否执行=%s ｜ 退出码=%s ｜ isError=%s"
                    % (ticket.get("是否执行"), (ticket.get("退出码语义") or {}).get("退出码"),
                       r.get("isError")))
            # ③ 动作类型：落在闭合枚举里，且与登记表一致
            led.add("%s[161] %s：动作类型＝%s（闭合枚举内）" % (tag, tool, ticket.get("动作类型")),
                    ticket.get("动作类型") in ("同步飞书", "写 Daniel 记录", "对外发信",
                                          "删除类", "触发采集", "其他（本机副作用）")
                    and ticket.get("动作类型") == action,
                    "期望 %s ｜ 实得 %s" % (action, ticket.get("动作类型")))
            # ④ 影响面**只来自只读预查**：给出的每条预查命令都必须是只读命令
            #    按结构化 `能力键` 判，不按展示串前缀猜（前缀猜法在 161 里错过一次）
            probes = (ticket.get("影响面") or {}).get("只读预查") or []
            write_probe = [p.get("命令") for p in probes
                           if p.get("能力键") in write_keys]
            led.add("%s[161] %s：影响面只来自只读预查（预查里没有一条写命令）" % (tag, tool),
                    bool(probes) and not write_probe
                    and "只来自只读预查" in ((ticket.get("影响面") or {}).get("影响面来源") or ""),
                    "预查 %d 条：%s" % (len(probes),
                                      "、".join(p.get("命令", "")[7:] for p in probes)))
            # ⑤ 给人跑的命令含 --confirm（能照着跑）
            cmd = ticket.get("将执行的确切命令") or ""
            led.add("%s[161] %s：确认单里的命令含 --confirm（能照着跑）" % (tag, tool),
                    "--confirm" in cmd and cmd.startswith("daniel "), cmd)
            # ⑥ **确认单里不得出现凭据**（本票红线）。
            # 判据分两层，**都不扫选项名**：`--delete-token`／`--password` 是**本 CLI 的选项名**，
            # 扫词会把正确的东西判成泄漏（我第一版就误判过 `--delete-token`）。
            #   ① **字段名**：出现 `shareToken`／`password` 这类**持有秘密的字段名**才算泄漏
            #      （键名带秘密 = 值大概率也在）；
            #   ② **值的形状**：JWT／32 位十六进制（Daniel 的 shareToken 就是 32 位十六进制）／
            #      `password=…` 赋值；以及环境里那几个凭据类变量**当前的值**。
            leaks = []
            for key in _walk_keys(ticket):
                if re.search(r"(?i)(password|passwd|secret|share_?token|share_?access_?code"
                             r"|api_?key|session_?id|credential_?value)", str(key)):
                    leaks.append("字段名 %s" % key)
            for val in _walk_strings(ticket):
                if re.search(r"eyJ[A-Za-z0-9_\-]{8,}\.", val):
                    leaks.append("JWT 形状：%s…" % val[:24])
                if re.search(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])", val):
                    leaks.append("32 位十六进制令牌形状：%s…" % val[:24])
                if re.search(r"(?i)\b(password|passwd|app_session_id)\s*[:=]\s*\S", val):
                    leaks.append("密码／会话赋值：%s…" % val[:32])
                for env_key in ("DANIEL_PASSWORD", "DANIEL_EMAIL", "DANIEL_TOKEN",
                                "DANIEL_SESSION", "DANIEL_API_KEY"):
                    ev = os.environ.get(env_key)
                    if ev and len(ev) >= 4 and ev in val:
                        leaks.append("环境变量 %s 的值" % env_key)
            led.add("%s[161] %s：整份确认单里没有任何凭据（按字段名与值的形状判，"
                    "不误判 --delete-token／--password 这类选项名）" % (tag, tool),
                    not leaks, "命中：%s" % ("；".join(sorted(set(leaks))[:3]) if leaks
                                           else "无（扫过 %d 个字段名与 %d 个字符串值）"
                                                % (len(list(_walk_keys(ticket))),
                                                   len(list(_walk_strings(ticket))))))
    finally:
        c.close()

    after = _readback(brand)
    # ⑦ 敏感参数绝不回显：**哨兵串在整个回包里出现 0 次**（本票红线）。
    # 用真实协议再证一遍（server 侧自检已证过一次）：单点 grep 人话不够 ——
    # 实测过"人话 2 次、整个回包 4 次"，所以对**整个响应**做子串计数。
    sentinel = "T161-PROTOCOL-SENTINEL-SECRET-9c3d-NEVER-ECHO"
    c = McpClient()
    try:
        c.initialize()
        res = c.request("tools/call",
                        {"name": "daniel_account_credentials_set",
                         "arguments": {"email": "probe@example.com", "password": sentinel}},
                        timeout=600)
        r = res.get("result") or {}
        whole = json.dumps(res, ensure_ascii=False)
        n_hits = whole.count(sentinel)
        led.add("%s[161] 经协议真调：password 哨兵串在**整个回包**里出现 0 次"
                "（tools/call 回包 + content + structuredContent + _meta）" % tag,
                n_hits == 0, "命中 %d 次（扫过 %d 字）" % (n_hits, len(whole)))
        text = "".join(b.get("text", "") for b in (r.get("content") or []))
        led.add("%s[161] 经协议真调：敏感参数打成占位符（口令由人在终端输入）" % tag,
                "<在终端里自行输入>" in text and sentinel not in text,
                "占位符命中：%s" % ("是" if "<在终端里自行输入>" in text else "否"))
    finally:
        c.close()
    # ⑧ 敏感参数不进 inputSchema：逐条扫全部确认单工具
    live_all = _live_tool_map()
    still = []
    for name, t in (live_all or {}).items():
        meta = ((t.get("_meta") or {}).get("daniel") or {})
        if meta.get("exposure") != "confirm-ticket":
            continue
        props = (t.get("inputSchema") or {}).get("properties") or {}
        for k in meta.get("droppedSecretParams") or []:
            if k in props:
                still.append("%s.%s" % (name, k))
    n_conf = sum(1 for t in (live_all or {}).values()
                 if ((t.get("_meta") or {}).get("daniel") or {}).get("exposure") == "confirm-ticket")
    led.add("%s[161] 逐条扫全部确认单工具：没有一条把敏感参数留在 inputSchema 里" % tag,
            not still, "仍在的：%s" % ("、".join(still) if still
                                    else "无（扫过 %d 条确认单工具）" % n_conf))
    # ⑥ 零副作用：前后回读
    led.add("%s[161] 零副作用：名单数与名单名集合调用前后完全不变（lists create 没建出新名单）" % tag,
            before.get("名单数") == after.get("名单数")
            and before.get("名单名集合") == after.get("名单名集合"),
            "前 %s 个%s ｜ 后 %s 个%s"
            % (before.get("名单数"), "" if before.get("名单名集合") == after.get("名单名集合")
               else "（集合变了！）", after.get("名单数"), ""))
    led.add("%s[161] 零副作用：写审计「真执行」计数前后没有增加（CLI 自己的写审计作证）" % tag,
            before.get("真执行") == after.get("真执行"),
            "前 真执行=%s（记录 %s 条）｜ 后 真执行=%s（记录 %s 条）"
            % (before.get("真执行"), before.get("审计记录数"),
               after.get("真执行"), after.get("审计记录数")))
    for tool, ticket, meta, _t in calls:
        print("     · %-26s 动作类型=%s ｜ 退出码=%s ｜ 是否执行=%s"
              % (tool, ticket.get("动作类型"), meta.get("exitCode"), ticket.get("是否执行")))
    return {"before": before, "after": after, "calls": [(t[0], t[1].get("动作类型")) for t in calls]}


def _walk_keys(node):
    """递归产出所有**字典键名**（用于"按字段名判凭据"）。"""
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            for x in _walk_keys(v):
                yield x
    elif isinstance(node, list):
        for v in node:
            for x in _walk_keys(v):
                yield x


def _walk_strings(node):
    """递归产出所有**字符串取值**（用于"按值的形状判凭据"）。"""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            for x in _walk_strings(v):
                yield x
    elif isinstance(node, list):
        for v in node:
            for x in _walk_strings(v):
                yield x


def _write_command_pairs(cli_tools=None):
    """CLI 声明里的写命令 `(模块, 子命令)`（用于断言「只读预查里没有一条写命令」）。

    不手写名单、也不另 import `schema.py`：直接从派生件判 ——
    **写命令的 `inputSchema` 才有 `confirm` 参数**（读命令没有），
    模块与子命令名从注解里的 `cli` 串取（与 `_cli_command_of` 同源）。
    """
    cli_tools = cli_tools if cli_tools is not None else _cli_mcp_tools()
    pairs = set()
    for t in cli_tools:
        props = (t.get("inputSchema") or {}).get("properties") or {}
        if "confirm" not in props:
            continue
        parts = ((t.get("annotations") or {}).get("cli") or "").split()
        if len(parts) >= 3:
            pairs.add((parts[1], parts[2]))
    return pairs


def _readback(brand):
    """只读回读：名单数／名单名集合／写审计「真执行」计数（**不含**任何凭据类字段）。"""
    out = {}
    try:
        lists = _cli_json(["lists", "by-brand", "--brand", brand])
        rows = lists.get("lists") or []
        out["名单数"] = lists.get("count")
        out["名单名集合"] = sorted(r.get("name") for r in rows if isinstance(r, dict))
    except (RuntimeError, ValueError) as e:
        out["名单数"] = "读取失败：%s" % e
        out["名单名集合"] = None
    try:
        # `--limit` 必须给大：`account audit` 的「小结」是**按返回的记录算的** ——
        # 用 `--limit 1` 只会统计最近一条（实测 limit=1 → 记录 1 条，limit=500 → 记录 305 条），
        # 拿它当"真执行没增加"的证据等于只看了最后一行。这里取全量。
        audit = _cli_json(["account", "audit", "--limit", "500"])
        summary = audit.get("小结") or {}
        out["真执行"] = summary.get("真执行")
        out["审计记录数"] = summary.get("记录条数")
    except (RuntimeError, ValueError) as e:
        out["真执行"] = "读取失败：%s" % e
        out["审计记录数"] = None
    return out

# ─────────────────────────── 检查 6：随包语料（MCP 真调 ＋ 与 CLI 完全相等） ───────────────────────────
def _cli_json(argv, env=None, cwd=None, timeout=300):
    """另起进程跑一次 CLI 并取 `data`（与 MCP 侧完全独立的一条路，用于两侧比对）。"""
    p = subprocess.run([sys.executable or "python3", DANIEL_BIN] + list(argv) + ["--json"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=cwd or REPO_ROOT, env=env, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError("`daniel %s --json` 退出码 %d：%s"
                           % (" ".join(argv), p.returncode, (p.stderr or "").strip()[:200]))
    return json.loads(p.stdout)["data"]


def _file_map(payload):
    """`skills list` 载荷 → `{域: {文件: sha256}}`（两侧比对的**最细一层**）。"""
    out = {}
    for s in payload.get("能力域") or []:
        out[s.get("域")] = {f.get("文件"): f.get("sha256") for f in (s.get("文件清单") or [])}
    return out


def _corpus_key(payload):
    items = sorted((s.get("域"), s.get("版本")) for s in (payload.get("能力域") or []))
    return "%s|%s" % (payload.get("语料版本"),
                      "；".join("%s=%s" % kv for kv in items))


def check_corpus(led, env=None, tag="", work_dir=None):
    """语料随包分发 ＋ 两侧完全相等（TICKET-159 的主战场）。

    用**真协议**调 `daniel_skills_list` / `daniel_skills_read`，再另起进程跑 CLI 侧的
    `daniel skills list/read`，两边做**逐键 ＋ 逐文件 sha256** 比对（差一即红）；
    最后读 resources，并与**盘上的切片文件**逐字对照。
    """
    work_dir = work_dir or os.path.join("/tmp", "daniel-mcp-check")
    c = McpClient(env=env)
    try:
        c.initialize()
        tl = c.request("tools/list")
        names = {t.get("name") for t in ((tl.get("result") or {}).get("tools") or [])}
        led.add("%s语料工具已注册（%s／%s）" % (tag, CORPUS_LIST_TOOL, CORPUS_READ_TOOL),
                CORPUS_LIST_TOOL in names and CORPUS_READ_TOOL in names,
                "tools/list 共 %d 条" % len(names))

        # ① MCP 侧真调 skills_list
        res = c.request("tools/call", {"name": CORPUS_LIST_TOOL, "arguments": {}}, timeout=300)
        r = res.get("result") or {}
        mcp_list = ((r.get("structuredContent") or {}).get("data")) or {}
        led.add("%stools/call：%s 返回 8 个能力域（含摘要／版本／前置条件）" % (tag, CORPUS_LIST_TOOL),
                r.get("isError") is False and mcp_list.get("能力域数") == 8,
                "能力域 %s ｜ 语料版本 %s ｜ 完整性 %s"
                % (mcp_list.get("能力域数"), mcp_list.get("语料版本"), mcp_list.get("完整性")))
        led.add("%s语料自检：整束 sha256 与随包清单一致（未被改过／复制不全）" % tag,
                mcp_list.get("完整性") == "一致",
                "完整性 %s ｜ 落点 %s" % (mcp_list.get("完整性"), mcp_list.get("语料根")))
        led.add("%s语料版本可追溯（一眼看出本机装的是哪一版）" % tag,
                bool(mcp_list.get("语料版本")) and bool(mcp_list.get("源文件sha256")),
                "语料版本 %s ｜ 源文件 %s ｜ 源 sha256 %s"
                % (mcp_list.get("语料版本"), mcp_list.get("源文件"),
                   (mcp_list.get("源文件sha256") or "")[:16]))
        prereq = all(s.get("前置条件") for s in (mcp_list.get("能力域") or []))
        led.add("%s每条能力域都带前置条件（何时加载）" % tag, prereq,
                "8/8" if prereq else "有缺项")

        # ② CLI 侧另起进程取同一份清单 → 完全相等（键 ＋ 逐文件 sha256）
        cli_list = _cli_json(["skills", "list"], env=env)
        same_key = _corpus_key(mcp_list) == _corpus_key(cli_list)
        led.add("%s两侧完全相等：技能集合 ＋ 语料版本（键比对）" % tag, same_key,
                "MCP %s ｜ CLI %s" % (_corpus_key(mcp_list), _corpus_key(cli_list)))
        led.add("%s两侧完全相等：两侧都恰好 8 个能力域，域键集合逐字相同" % tag,
                {s["域"] for s in (mcp_list.get("能力域") or [])}
                == {s["域"] for s in (cli_list.get("能力域") or [])},
                "MCP %d ｜ CLI %d" % (mcp_list.get("能力域数"), cli_list.get("能力域数")))
        f_mcp, f_cli = _file_map(mcp_list), _file_map(cli_list)
        n_files = sum(len(v) for v in f_mcp.values())
        led.add("%s两侧完全相等：束内文件集合 ＋ 逐文件 sha256（差一即红）" % tag,
                f_mcp == f_cli and n_files > 0,
                "比对 %d 个文件 ｜ 不一致 %d 个"
                % (n_files, len({k for k in set(f_mcp) | set(f_cli)
                                 if f_mcp.get(k) != f_cli.get(k)})))

        # ③ 正文：MCP → CLI → 盘上切片，三处逐字一致
        args = {"name": CORPUS_SAMPLE_DOMAIN, "section": CORPUS_SAMPLE_SECTION}
        res = c.request("tools/call", {"name": CORPUS_READ_TOOL, "arguments": args}, timeout=300)
        r = res.get("result") or {}
        mcp_read = ((r.get("structuredContent") or {}).get("data")) or {}
        cli_read = _cli_json(["skills", "read", "--name", CORPUS_SAMPLE_DOMAIN,
                              "--section", str(CORPUS_SAMPLE_SECTION)], env=env)
        disk = io.open(os.path.join(PKG_ROOT, "mcp", "corpus", CORPUS_SAMPLE_DOMAIN,
                                    mcp_read.get("切片文件") or ""), encoding="utf-8").read()
        led.add("%stools/call：%s 真读到判据正文（非空、非占位）" % (tag, CORPUS_READ_TOOL),
                mcp_read.get("模式") == "正文" and len(mcp_read.get("正文") or "") > 200,
                "%s 切片 %s ｜ %s ｜ %d 字"
                % (mcp_read.get("切片文件"), mcp_read.get("切片号"),
                   mcp_read.get("源行区间"), len(mcp_read.get("正文") or "")))
        led.add("%s两侧正文逐字一致（MCP ≡ CLI）" % tag,
                (mcp_read.get("正文") or "") == (cli_read.get("正文") or "")
                and bool(mcp_read.get("正文")),
                "MCP %d 字 ｜ CLI %d 字" % (len(mcp_read.get("正文") or ""),
                                          len(cli_read.get("正文") or "")))
        led.add("%s正文 ≡ 盘上的逐字切片（不是重新生成的第二份）" % tag,
                (mcp_read.get("正文") or "") == disk,
                "盘上 %d 字" % len(disk))

        # ④ 分片：大切片必须能分片续读，且拼回来与全文逐字相同
        big = {"name": CORPUS_BIG_DOMAIN, "section": CORPUS_BIG_SECTION, "max_bytes": 20000}
        res = c.request("tools/call", {"name": CORPUS_READ_TOOL, "arguments": big}, timeout=300)
        b1 = ((res.get("result") or {}).get("structuredContent") or {}).get("data") or {}
        info = b1.get("分片") or {}
        led.add("%s分片：大切片（%s 字节）自动分片，不回整段" % (tag, info.get("总字节")),
                info.get("还有更多") is True and info.get("本次字节")
                and info.get("本次字节") < info.get("总字节"),
                "本次 %s 字节 / 共 %s 字节 ｜ 下一次偏移 %s"
                % (info.get("本次字节"), info.get("总字节"), info.get("下一次偏移")))
        pieces, off, guard = [], info.get("偏移") or 0, 0
        while off is not None and guard < 40:
            guard += 1
            res = c.request("tools/call", {"name": CORPUS_READ_TOOL,
                                           "arguments": dict(big, offset=off)}, timeout=300)
            one = ((res.get("result") or {}).get("structuredContent") or {}).get("data") or {}
            pieces.append(one.get("正文") or "")
            off = (one.get("分片") or {}).get("下一次偏移")
        full = "".join(pieces)
        disk_big = io.open(os.path.join(PKG_ROOT, "mcp", "corpus", CORPUS_BIG_DOMAIN,
                                        b1.get("切片文件") or ""), encoding="utf-8").read()
        led.add("%s分片续读拼回来 ≡ 全文（%d 片逐字无损）" % (tag, len(pieces)),
                full == disk_big and len(pieces) > 1,
                "拼回 %d 字 ｜ 盘上 %d 字 ｜ 片数 %d" % (len(full), len(disk_big), len(pieces)))

        # ⑤ resources：真实内容（与盘上一致），不是"读了 URI 返回索引"
        rl = c.request("resources/list", timeout=300)
        resources = ((rl.get("result") or {}).get("resources")) or []
        uris = {x.get("uri") for x in resources}
        led.add("%sresources/list：索引 ＋ 8 束 ＋ 每个切片都列出" % tag,
                "%s://skills" % "daniel-copilot" in uris
                and len([u for u in uris if u.count("/") == 3]) >= 8 and len(resources) >= 30,
                "%d 条 resource" % len(resources))
        uri = "daniel-copilot://skills/%s/%d" % (CORPUS_SAMPLE_DOMAIN, CORPUS_SAMPLE_SECTION)
        rr = c.request("resources/read", {"uri": uri}, timeout=300)
        contents = ((rr.get("result") or {}).get("contents")) or []
        text = contents[0].get("text") if contents else None
        led.add("%sresources/read：%s 返回盘上同一份逐字切片" % (tag, uri),
                bool(text) and text == disk,
                "mimeType %s ｜ %d 字" % (contents[0].get("mimeType") if contents else "—",
                                         len(text or "")))
        bad = c.request("resources/read", {"uri": "daniel-copilot://skills/no-such-domain"})
        led.add("%s[degenerate] 不认识的域 → 协议错误（不假装成功）" % tag,
                (bad.get("error") or {}).get("code") == -32602,
                (bad.get("error") or {}).get("message", "")[:80])

        # ⑥ 落点：语料在**服务包内**，不在用户级目录
        # 两侧都过 `_under()`（内部 realpath 归一化）：服务端报的是真实路径，
        # 这里若拿未归一化的 PKG_ROOT／HOME 去比，在软链路径下会恒假。
        root = mcp_list.get("语料根") or ""
        in_pkg = _under(root, os.path.join(PKG_ROOT, "mcp", "corpus")) or \
            _under(root, os.path.join(os.path.dirname(HERE), "mcp", "corpus"))
        home = (env or os.environ).get("HOME") or os.path.expanduser("~")
        led.add("%s语料落点在服务包内，且**不在**用户级目录下" % tag,
                in_pkg and not _under(root, os.path.join(home, ".agents")),
                "语料根 %s ｜ HOME %s" % (root, home))
        return {"domains": mcp_list.get("能力域数"), "version": mcp_list.get("语料版本"),
                "root": root, "files": n_files, "resources": len(resources)}
    finally:
        c.close()


def _fresh_dir(path):
    """造一个干净的目录：先尽量清掉残留，清不掉就换一个**全新**的名字。

    为什么不能只写 `rmtree(path)`：本机 Python（Apple 的 python3.9）会把字节码缓存写进
    `$HOME/Library/Caches/com.apple.python/…`，所以在重定向 HOME 的用例里，残留目录会**很深**，
    `rmtree` 可能以 `OSError: Directory not empty` 直接炸掉整轮检查（实测过）。
    这里改成"清得掉就复用、清不掉就换名"，让**重复跑同一个 --work-dir** 也稳。
    """
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    if os.path.isdir(path):
        path = "%s-%d" % (path, os.getpid())
        shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)
    return path


def isolated_home(work_dir):
    """造一个**不含 `.agents` 的空 HOME**（并返回它）——用来证明"宿主/服务都不依赖用户级技能目录"。

    为什么用重定向而不是真的把 `~/.agents/skills` 改名：改名要写工作区之外的用户目录，
    既有破坏性（改坏了影响本机所有项目），也不是本票需要证明的东西 ——
    重定向 HOME 是**更强**的判据：它连"用户级目录存在但内容不同"这种情形都排除了。
    """
    home = _fresh_dir(os.path.join(work_dir, "isolated-home"))
    return _norm(home)


def check_package_standalone(led, work_dir):
    """分发物自足：把 `data/daniel-cli/` **单独**拷走（无 `.kol-tools`、无仓库、换 HOME 与 cwd）。

    这是"另一台机器只注册 MCP 就能拿到语料"的**本机等价物**：拷贝里没有能力脚本目录、
    没有 `docs/`、没有 `.agents/`，只有产品本体。
    """
    dst = os.path.join(work_dir, "standalone")
    _fresh_dir(dst)
    # 定位也用真实路径：`--work-dir` 可能是软链路径（macOS 的 /tmp），
    # 而服务端报出来的是真实路径 —— 拷贝落点若不归一化，后面比"语料根在拷贝内"会恒假。
    copy = _norm(os.path.join(dst, "daniel-cli"))
    shutil.copytree(PKG_ROOT, copy)
    home = os.path.join(dst, "fake-home")
    os.makedirs(home, exist_ok=True)
    env = {"PATH": os.environ.get("PATH") or "/usr/bin:/bin", "HOME": home,
           "LANG": os.environ.get("LANG") or "en_US.UTF-8", "PYTHONIOENCODING": "utf-8"}
    led.add("分发物自足：拷走的包内确实没有能力脚本目录（.kol-tools）",
            not os.path.isdir(os.path.join(copy, ".kol-tools")),
            "拷贝落点 %s" % copy)
    p = subprocess.run([sys.executable or "python3",
                        os.path.join(copy, "bin", "daniel"), "skills", "list", "--json"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=dst, env=env, timeout=300)
    ok_cli = p.returncode == 0
    data = json.loads(p.stdout)["data"] if ok_cli else {}
    led.add("分发物自足：拷走的包里 `daniel skills list` 直接可用（换 cwd／换 HOME／无能力目录）",
            ok_cli and data.get("能力域数") == 8 and data.get("完整性") == "一致",
            "退出码 %d ｜ 能力域 %s ｜ 语料根 %s"
            % (p.returncode, data.get("能力域数"), data.get("语料根")))

    c = McpClient(argv=[sys.executable or "python3", os.path.join(copy, "mcp", "server.py")],
                  cwd=dst, env=env)
    try:
        c.initialize()
        res = c.request("tools/call", {"name": CORPUS_LIST_TOOL, "arguments": {}}, timeout=300)
        r = res.get("result") or {}
        d = ((r.get("structuredContent") or {}).get("data")) or {}
        led.add("分发物自足：从拷走的包里起 MCP server，语料工具照样读到 8 个能力域",
                r.get("isError") is False and d.get("能力域数") == 8
                and _under(d.get("语料根"), copy),
                "能力域 %s ｜ 语料根 %s" % (d.get("能力域数"), d.get("语料根")))
        led.add("分发物自足：语料根落在拷贝内（按服务自身位置定位，不是写死的本仓路径）",
                _under(d.get("语料根"), copy),
                "%s ≟ %s（两侧已 realpath 归一化）" % (d.get("语料根") or "（空）", _norm(copy)))
    finally:
        c.close()
    return copy


# ─────────────────────────── 检查 7：零 DSH 依赖 ───────────────────────────
def check_no_dsh(led, work_dir, cli_tools, contract=None):
    normal = shutil.which("dsh")
    mpath = minimal_path()
    gone = shutil.which("dsh", path=mpath)
    led.add("零 DSH 依赖：正控 —— 常规 PATH 里确实找得到 dsh（否则这条测试无意义）",
            normal is not None, "常规 PATH 中的 dsh：%s" % (normal or "无"))
    led.add("零 DSH 依赖：最小 PATH 里 dsh 确实不存在",
            gone is None, "最小 PATH=%s ｜ which(dsh)=%s" % (mpath, gone or "无"))
    env = dict(os.environ)
    env["PATH"] = mpath
    env.pop("DANIEL_CLI_TOOLS", None)
    tool_names = check_tools_list(led, env=env, tag="[无 dsh] ", cli_tools=cli_tools)
    summary = check_tools_call(led, os.path.join(work_dir, "nodsh"),
                               sandbox=os.path.join(work_dir, "nodsh", "sandbox"),
                               env=env, tag="[无 dsh] ", contract=contract)
    if summary:
        print("     [无 dsh] 只读工具 %d 条可用；交付物 %s" % (len(tool_names or []),
                                                            summary.get("deliverable")))
    return summary


# ─────────────────────────── 自检：正控 ＋ 退化输入 ───────────────────────────
def degenerate_self_test(led):
    """正控与退化输入：非法 JSON-RPC、未知工具名、参数缺必填、通知不回包、进程韧性。"""
    c = McpClient()
    try:
        c.initialize()

        # 1) 非法 JSON
        c.send_raw("这不是 JSON")
        got = c.next_message(timeout=10)
        led.add("[degenerate] 非法 JSON → JSON-RPC 错误码 -32700（id 为 null）",
                isinstance(got, dict) and (got.get("error") or {}).get("code") == -32700,
                json.dumps(got, ensure_ascii=False)[:120])
        res = c.request("ping")
        led.add("[degenerate] 收到非法 JSON 后进程仍存活（ping 照常）", res.get("result") == {})

        # 2) 顶层不是对象
        c.send_raw("[1, 2, 3]")
        got = c.next_message(timeout=10)
        led.add("[degenerate] 顶层是数组 → -32600（且**只**回一条错误，不按元素各回一条）",
                isinstance(got, dict) and (got.get("error") or {}).get("code") == -32600
                and c.expect_silence(timeout=0.8) is None,
                json.dumps(got, ensure_ascii=False)[:120])

        # 3) 缺 jsonrpc 字段
        c.send({"id": 991, "method": "ping"})
        got = c.next_message(timeout=10)
        led.add("[degenerate] 缺 jsonrpc 字段 → -32600 且 id 原样回",
                isinstance(got, dict) and (got.get("error") or {}).get("code") == -32600
                and got.get("id") == 991,
                json.dumps(got, ensure_ascii=False)[:120])

        # 4) 未知方法（`resources/*` 本期**已实现**，所以拿 prompts/* 当未知方法）
        got = c.request("prompts/list", rid=992)
        led.add("[degenerate] 未知方法 → -32601 且 id 原样回",
                (got.get("error") or {}).get("code") == -32601 and got.get("id") == 992,
                (got.get("error") or {}).get("message", "")[:80])

        # 5) 未知工具名
        got = c.request("tools/call", {"name": "daniel_no_such_tool", "arguments": {}}, rid=993)
        led.add("[degenerate] 未知工具名 → -32602（协议错误，不是假装成功）",
                (got.get("error") or {}).get("code") == -32602,
                (got.get("error") or {}).get("message", "")[:90])

        # 6) arguments 不是对象
        got = c.request("tools/call", {"name": PLAYBOOK_TOOL, "arguments": "nope"}, rid=994)
        led.add("[degenerate] arguments 非对象 → -32602",
                (got.get("error") or {}).get("code") == -32602)

        # 7) 参数缺必填 → CLI 报用户错误（退出码 2），isError=true
        got = c.request("tools/call", {"name": PLAYBOOK_TOOL, "arguments": {}}, rid=995,
                        timeout=300)
        r = got.get("result") or {}
        text = "".join(b.get("text", "") for b in (r.get("content") or []))
        code = ((r.get("_meta") or {}).get("daniel") or {}).get("exitCode")
        led.add("[degenerate] 参数缺必填 → isError=true 且人话理由里带退出码 2",
                r.get("isError") is True and code == 2 and "退出码：2" in text,
                "退出码=%s ｜ 理由=%s" % (code, text.splitlines()[4][:90] if
                                        len(text.splitlines()) > 4 else text[:90]))

        # 8) 未知参数名
        got = c.request("tools/call", {"name": PLAYBOOK_TOOL,
                                       "arguments": {"name": PLAYBOOK_CONTRACT,
                                                     "no_such_arg": 1}}, rid=996)
        r = got.get("result") or {}
        text = "".join(b.get("text", "") for b in (r.get("content") or []))
        led.add("[degenerate] 未知参数名 → 拒绝并列出允许的参数（不静默丢弃）",
                r.get("isError") is True and "参数名不认识" in text, text.splitlines()[0][:90])

        # 9) 写链参数 confirm=true 必须被拒
        got = c.request("tools/call", {"name": PLAYBOOK_TOOL,
                                       "arguments": {"name": PLAYBOOK_CONTRACT,
                                                     "confirm": True}}, rid=997)
        r = got.get("result") or {}
        text = "".join(b.get("text", "") for b in (r.get("content") or []))
        # TICKET-161：原断言是拒因含「暂不暴露」—— 那句已成假话。
        # **换成更硬的一条**：拒因必须写明「本模式不执行写动作」＋「请拿确认单…到 CLI」，
        # 且 `_meta` 里必须留下"没有执行、没有转发 --confirm"的证据。
        meta = ((r.get("_meta") or {}).get("daniel") or {})
        led.add("[degenerate] 传 confirm=true → 拒绝，拒因写明「本模式不执行写动作」"
                "＋「请拿确认单…到 CLI」，且 _meta 记 executed=false／confirmForwarded=false",
                r.get("isError") is True and "本模式不执行写动作" in text
                and "请拿确认单" in text and "CLI" in text
                and meta.get("executed") is False and meta.get("confirmForwarded") is False,
                text.splitlines()[0][:100])

        # 9b) 确认单工具也必须拒收 confirm／delete_token（真调一次，走协议）
        for tool, args, banned in (
                ("daniel_lists_create", {"brand": "3690002", "name": "x", "confirm": True},
                 "confirm"),
                ("daniel_brands_delete", {"brand": "3690002", "delete_token": "3690002"},
                 "delete_token")):
            got = c.request("tools/call", {"name": tool, "arguments": args}, rid=998)
            r = got.get("result") or {}
            text = "".join(b.get("text", "") for b in (r.get("content") or []))
            meta = ((r.get("_meta") or {}).get("daniel") or {})
            led.add("[degenerate] 确认单工具 %s 收到 %s → 拒绝（永不转发），且未执行" % (tool, banned),
                    r.get("isError") is True and "本模式不执行写动作" in text
                    and meta.get("executed") is False
                    and ((r.get("structuredContent") or {}).get("确认单") is None),
                    text.splitlines()[0][:100])

        # 10) 通知不回包
        c.notify("notifications/initialized")
        c.notify("notifications/cancelled", {"requestId": 1})
        silent = c.expect_silence(timeout=1.2)
        led.add("[degenerate] 通知（无 id）不产生任何回包",
                silent is None,
                "观察 1.2 秒收到回包：%s" % (json.dumps(silent, ensure_ascii=False)[:80]
                                          if silent is not None else "0 条"))

        # 11) 字符串 id 原样回
        got = c.request("ping", rid="ping-字符串-id")
        led.add("[degenerate] 字符串 id 原样回包", got.get("id") == "ping-字符串-id")

        # 12) 认得的协议版本原样回声 / 不认得的回最新
        c2 = McpClient()
        try:
            r1 = c2.initialize(protocol="2025-03-26")
            led.add("正控：客户端要 2025-03-26，server 原样回声",
                    (r1.get("result") or {}).get("protocolVersion") == "2025-03-26")
        finally:
            c2.close()
        c3 = McpClient()
        try:
            r2 = c3.initialize(protocol="1999-01-01")
            led.add("[degenerate] 不认得的协议版本 → 回 server 最新的一个",
                    (r2.get("result") or {}).get("protocolVersion") == "2025-06-18",
                    (r2.get("result") or {}).get("protocolVersion"))
        finally:
            c3.close()

        # 13) 折腾完还能正常服务
        res = c.request("tools/list")
        led.add("正控：以上退化输入之后 tools/list 仍正常返回",
                len(((res.get("result") or {}).get("tools")) or []) > 0,
                "%d 条" % len(((res.get("result") or {}).get("tools")) or []))

        # 14) 🔴 TICKET-202·Q14 防复发判据：**两个载荷口径不一致必须报红**
        #     （本条的正控由**人为把 run 的协议面改成 confirm-ticket** 造出红 —— 不是"现状绿"）
        live = ((res.get("result") or {}).get("tools")) or []
        cli_tools = _cli_mcp_tools()
        led.add("负控（202）：现状下两个载荷口径一致 → 0 条不一致",
                exposure_mismatches(cli_tools, live) == [],
                "不一致 %d 条 ｜ 比对 %d 条工具" % (len(exposure_mismatches(cli_tools, live)), len(live)))

        def _mutate(fn):
            import copy as _copy
            tools2 = _copy.deepcopy(live)
            for t in tools2:
                if t.get("name") == "daniel_playbook_run":
                    fn(t)
            return exposure_mismatches(cli_tools, tools2)

        # 正控①：协议面档位改成 confirm-ticket（与自省载荷的 sandbox-only 故意不一致）
        got1 = _mutate(lambda t: (t.setdefault("_meta", {}).setdefault("daniel", {})
                                  .__setitem__("exposure", "confirm-ticket")))
        led.add("正控（202）：人为把 `run` 的**协议面**档位改成 confirm-ticket"
                "（与自省载荷故意不一致）→ 必须报红",
                any("daniel_playbook_run" in m and "档位不一致" in m for m in got1),
                "；".join(got1[:3]) or "**没报出来（判据失效）**")

        # 正控②：协议面把 readOnlyHint 翻成 True（自省载荷为 False）⇒ 必须报红
        got2 = _mutate(lambda t: t.setdefault("annotations", {}).__setitem__("readOnlyHint", True))
        led.add("正控（202）：人为把 `run` 的协议面 `readOnlyHint` 改成 True → 必须报红",
                any("daniel_playbook_run" in m and "readOnlyHint" in m for m in got2),
                "；".join(got2[:3]) or "**没报出来（判据失效）**")

        # 正控③：把本机出件档的注记抹掉 ⇒ 必须报红（"会写本机"这件事不许被静默藏起来）
        def _drop_note(t):
            t.setdefault("_meta", {}).setdefault("daniel", {})["readOnlyNote"] = None
        tools3 = None
        import copy as _copy2
        tools3 = _copy2.deepcopy(live)
        for t in tools3:
            if t.get("name") == "daniel_playbook_deliver":
                _drop_note(t)
                t.setdefault("_meta", {}).setdefault("daniel", {})["exposure"] = "read-only"
                t.setdefault("annotations", {})["readOnlyHint"] = True
        got3 = exposure_mismatches(cli_tools, tools3)
        led.add("正控（202）：人为把 `deliver` 改回「纯只读且无注记」→ 必须报红"
                "（档位／readOnlyHint／缺注记 至少一项命中）",
                len(got3) >= 2, "；".join(got3[:3]) or "**没报出来（判据失效）**")

        # 真阴性：给 `deliver` 的协议面注入 **executes=false**（注记把出件堵死）⇒ 必须报红
        tools4 = _copy2.deepcopy(live)
        for t in tools4:
            if t.get("name") == "daniel_playbook_deliver":
                t.setdefault("_meta", {}).setdefault("daniel", {})["executes"] = False
        got4 = exposure_mismatches(cli_tools, tools4)
        led.add("真阴性（202）：`local-output` 档在协议面被执行语义堵死（executes=false）→ 必须报红",
                any("可直接执行" in m for m in got4),
                "；".join(got4[:3]) or "**没报出来（判据失效）**")
    finally:
        c.close()


# ─────────────────────────── 入口 ───────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="MCP 协议级验证客户端（TICKET-153 Part A）")
    ap.add_argument("--self-test", action="store_true", help="全量检查 ＋ 正控与退化输入自检")
    ap.add_argument("--playbook", action="store_true", help="只跑一次 tools/call 并落产物")
    ap.add_argument("--out-dir", default=None, help="产物目录（--playbook 用）")
    ap.add_argument("--sandbox", default=None, help="契约运行的沙箱落点（可选，跨宿主比对照用）")
    ap.add_argument("--contract", default=None,
                    help="tools/call 要跑的契约（默认 %s；真实数据契约用 real-brands-inventory）"
                         % PLAYBOOK_CONTRACT)
    ap.add_argument("--work-dir", default=None, help="全量检查的工作目录（默认 /tmp/daniel-mcp-check）")
    ap.add_argument("--snippet", default=None,
                    help="按注册片段起 server（.json 或含 ```json 代码块的 .md）——"
                         "读的就是要交付的那一段原话")
    ap.add_argument("--json", action="store_true", help="机器可读汇总")
    ap.add_argument("--confirm-ticket", dest="confirm_ticket", action="store_true",
                    help="加跑第 10 组：写链＝确认单（**真调**三条确认单工具 ＋ 前后只读回读"
                         "证明零副作用）。默认不跑 —— 它要联网读写真实账号事实，"
                         "而本脚本的默认全量检查要保持离线可复现")
    a = ap.parse_args(argv)

    global _SPAWN
    if a.snippet:
        _SPAWN = load_snippet(a.snippet)

    if a.playbook:
        out_dir = a.out_dir or os.path.join("/tmp", "daniel-mcp-check", "mcp")
        led = Ledger()
        print("=== 跑一次 tools/call（%s）==="
              % ("按注册片段起 server" if a.snippet else "按本目录的 server.py 起 server"))
        print("起 server 的方式：%s（cwd=%s）" % (" ".join(spawn_spec()["argv"]),
                                              spawn_spec()["cwd"]))
        if a.snippet:
            check_snippet(led, a.snippet)
        summary = check_tools_call(led, out_dir, sandbox=a.sandbox or
                                   (spawn_spec()["env"] or {}).get("DANIEL_PLAYBOOK_SANDBOX"),
                                   contract=a.contract)
        print("产物目录：%s" % out_dir)
        print("结论：%s（%d/%d）" % ("全部通过" if led.passed == led.total else "存在未过项",
                                   led.passed, led.total))
        if a.json:
            print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0 if led.passed == led.total else 2

    work_dir = a.work_dir or os.path.join("/tmp", "daniel-mcp-check")
    os.makedirs(work_dir, exist_ok=True)
    print("=== MCP 协议级验证（daniel-copilot server）===")
    print("起 server 的方式：%s（cwd=%s）%s"
          % (" ".join(spawn_spec()["argv"]), spawn_spec()["cwd"],
             "  ← 来自注册片段 %s" % a.snippet if a.snippet else ""))
    print("工作目录：%s" % work_dir)
    led = Ledger()
    if a.snippet:
        print("--- 第 0 组：注册片段本身可用 ---")
        check_snippet(led, a.snippet)
    print("--- 第 1 组：握手 ---")
    cli_tools = _cli_mcp_tools()
    check_handshake(led, tag="")
    print("--- 第 2 组：tools/list ≡ CLI schema ---")
    registered = check_tools_list(led, tag="", cli_tools=cli_tools)
    print("--- 第 2.5 组：确认单里印出的命令真能在 CLI 上跑通（TICKET-161）---")
    check_ticket_commands(led, tag="", cli_tools=cli_tools)
    print("--- 第 3 组：差异显式登记（CLI 命令集 ⊖ MCP 工具集 ≡ exposure-register.json）---")
    check_exposure_register(led, cli_tools, registered)
    print("--- 第 4 组：随包语料（MCP 真调 ＋ 与 CLI 完全相等）---")
    corpus_summary = check_corpus(led, tag="")
    print("--- 第 5 组：随包语料：隔离用户级目录（HOME 重定向到不含 .agents 的空目录）---")
    iso_home = isolated_home(work_dir)
    iso_env = dict(os.environ)
    iso_env["HOME"] = iso_home
    print("    隔离用 HOME：%s（里面没有任何 .agents／skills）" % iso_home)
    check_corpus(led, env=iso_env, tag="[隔离用户目录] ")
    print("--- 第 6 组：分发物自足（把 data/daniel-cli 单独拷走，无 .kol-tools／无仓库）---")
    check_package_standalone(led, work_dir)
    print("--- 第 7 组：tools/call 跑通只读工序 ---")
    sandbox = os.path.join(work_dir, "cli", "sandbox")
    if a.snippet:
        sandbox = (spawn_spec()["env"] or {}).get("DANIEL_PLAYBOOK_SANDBOX") or sandbox
    call_summary = check_tools_call(led, os.path.join(work_dir, "cli"),
                                    sandbox=sandbox, tag="", contract=a.contract)
    print("--- 第 8 组：零 DSH 依赖（PATH 无 dsh 复跑）---")
    nodsh_summary = check_no_dsh(led, work_dir, cli_tools, contract=a.contract)
    if a.self_test:
        print("--- 第 9 组：自检（正控 ＋ 退化输入）---")
        degenerate_self_test(led)
    if a.confirm_ticket:
        print("--- 第 10 组：写链＝确认单（真调 ＋ 零副作用前后回读·TICKET-161）---")
        ticket_summary = check_confirm_ticket(led)
    else:
        ticket_summary = None
        print("--- 第 10 组：写链＝确认单（已跳过；加 --confirm-ticket 才真调）---")

    print("--- 汇总 ---")
    print("检查项：%d 条，通过 %d 条，未过 %d 条" % (led.total, led.passed, led.total - led.passed))
    payload = {"checks": led.items, "passed": led.passed, "total": led.total,
               "cliTools": len(cli_tools), "cliCall": call_summary, "noDshCall": nodsh_summary,
               "corpus": corpus_summary, "confirmTicket": ticket_summary}
    if a.json:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
    if call_summary:
        print("交付物（直接路径）：%s" % call_summary.get("deliverable"))
        print("运行报告（直接路径）：%s" % call_summary.get("report"))
        print("字段摘要：data %d 个字段 ｜ 交付件 %s 行 ｜ 结论：%s"
              % (call_summary.get("fields"), call_summary.get("rows"),
                 call_summary.get("conclusion")))
    if nodsh_summary:
        print("交付物（PATH 无 dsh）：%s" % nodsh_summary.get("deliverable"))
    print("结论：%s" % ("全部通过" if led.passed == led.total else "存在未过项"))
    return 0 if led.passed == led.total else 2


if __name__ == "__main__":
    sys.exit(main())
