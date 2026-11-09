# -*- coding: utf-8 -*-
"""`connect --doctor`：把「这套接入到底通不通」变成**可复算的断言**（TICKET-189 §B）。

为什么它是本票的灵魂
--------------------
在 TICKET-189 之前，"能不能用"的判据是「打开 Cursor → Settings → MCP → 看状态」——
一句**人眼观察**，不可复算，也不回答"这条接入到底对不对"。本模块把这句话拆成五项断言，
**全部在宿主的 MCP 进程之外**跑得出来（不需要打开任何宿主）：

  D1 包完整性           ：`skills list` 的能力域数、语料版本与指纹
  D2 server 起得来      ：**复用既有仪器** `mcp/client_check.py`（不重造 MCP 客户端），
                          用它按**本次生成的注册片段**真起一次 server 并跑通只读工具
  D3 工具数 == schema 声明数：`server.py --describe` 的 registered／cliDeclared
                          ＋ CLI 自己声明的命令数，三者必须相等
  D4 只读命令取到真实数据：真跑一条只读命令（`brands list`）并断言拿到了真实记录
  D5 每个宿主的接入状态 ：配置文件存在、本产品条目**恰好一条**、路径指向**当前包**
                          （不是旧副本）、两宿主的数据落点一致

任一项不过 ⇒ 整体退出码非 0，且**每项都带一行可执行修法**（例如
`daniel connect --host cursor --apply --confirm`）。
宿主的模型侧"会话里真的跑通"仍由用户自己做，但那一步只验"宿主是否认这份配置"，
**不是**判据的唯一来源 —— 本命令已经能回答接入正确性。
"""
import io
import json
import os
import subprocess
import tempfile

from ..exits import EXIT_INTERNAL, EXIT_OK

from . import hosts


def _cli_bin():
    return os.path.join(hosts.cli_package_root(), "bin", "daniel")


def _run(argv, timeout=300, cwd=None):
    """跑一个子进程并拿回 `(退出码, stdout, stderr)`；超时当场记成失败（不静默）。"""
    try:
        p = subprocess.run([str(a) for a in argv],
                           capture_output=True, text=True, timeout=timeout,
                           cwd=cwd or hosts.workspace_cwd())
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return None, "", "超时（%s 秒）" % timeout
    except OSError as e:
        return None, "", "%s: %s" % (type(e).__name__, e)


def _cli_json(argv, timeout=300):
    """跑一条 CLI 只读命令并取回它的 `--json` 信封（取不到就如实返回 None）。"""
    rc, out, err = _run([hosts.interpreter(), _cli_bin()] + list(argv) + ["--json"],
                        timeout=timeout)
    if rc != 0:
        return None, (out or err or "").strip().splitlines()[-1:] or ["退出码 %s" % rc]
    try:
        return json.loads(out), []
    except ValueError:
        return None, ["输出不是合法 JSON（仪器输出格式变了？）"]


def _item(name, ok, evidence, fix=None, extra=None):
    row = {"项": name, "通过": bool(ok), "证据": evidence}
    if extra:
        row["细节"] = extra
    if not ok:
        row["修法"] = fix or "（无）"
    return row


# ─────────────────────────── D1 包完整性 ───────────────────────────
def check_package():
    doc, bad = _cli_json(["skills", "list"])
    if doc is None:
        return _item("① 包完整性（能力束）", False,
                     "取不到能力束清单：%s" % "；".join(bad),
                     "跑 `daniel skills list` 看详细报错；能力包不完整时重装能力包")
    d = doc.get("data") or {}
    domains = d.get("能力域") or []
    fps = [x.get("整束sha256") for x in domains if x.get("整束sha256")]
    ok = (doc.get("ok") is True and d.get("完整性") == "一致" and
          int(d.get("能力域数") or 0) == len(domains) and len(domains) > 0 and bool(fps))
    ev = ("能力域 %s 个 ｜ 完整性 %s ｜ 语料版本 %s ｜ 源文件sha256 %s ｜ 逐束指纹 %d 条"
          % (d.get("能力域数"), d.get("完整性"), d.get("语料版本"),
             str(d.get("源文件sha256"))[:12], len(fps)))
    return _item("① 包完整性（能力束）", ok, ev,
                 "重装／重新同步能力包，再跑 `daniel skills list` 确认「8 个能力域 ｜ 完整性 一致」",
                 extra={"语料根": d.get("语料根"), "定位方式": d.get("定位方式")})


# ─────────────────────────── D2 复用 client_check 起 server ───────────────────────────
def check_server():
    """**复用既有仪器**：把本次生成的注册片段落成临时文件，交给 `mcp/client_check.py` 起 server。

    片段取值与写进宿主的那一份**同源**（`hosts.entry_payload()`）；片段形态用 JSON，
    因为 `client_check.py` 的 `--snippet` 只认 JSON（它是"按注册片段起 server"的既有入口）。
    """
    snippet = json.dumps({"mcpServers": {hosts.ENTRY_NAME: hosts.entry_payload()}},
                         ensure_ascii=False, indent=2) + "\n"
    tmpdir = tempfile.mkdtemp(prefix="daniel-connect-doctor-")
    snippet_path = os.path.join(tmpdir, "注册片段.json")
    with io.open(snippet_path, "w", encoding="utf-8") as fh:
        fh.write(snippet)
    checker = os.path.join(hosts.cli_package_root(), "mcp", "client_check.py")
    rc, out, err = _run([hosts.interpreter(), checker, "--snippet", snippet_path,
                         "--work-dir", os.path.join(tmpdir, "check")], timeout=600)
    summary = ""
    for line in (out or "").splitlines():
        if line.startswith("检查项：") or line.startswith("结论："):
            summary = summary + line.strip() + " ｜ "
    ok = rc == 0
    ev = ("按片段起 server：%s ｜ 仪器 %s ｜ %s"
          % ("、".join([hosts.entry_payload()["command"]] + hosts.entry_payload()["args"]),
             "mcp/client_check.py", summary.strip(" ｜") or (err or "").strip()[-160:]))
    return _item("② MCP server 起得来（复用既有仪器）", ok, ev,
                 "跑 `python3 <包>/data/daniel-cli/mcp/client_check.py --self-test` 定位；"
                 "若片段里的路径是旧副本，跑 `daniel connect --host cursor --apply --confirm` 刷新",
                 extra={"片段文件": snippet_path, "工作目录": os.path.join(tmpdir, "check")})


# ─────────────────────────── D3 工具数 == 声明数 ───────────────────────────
def check_tool_count():
    desc_path = hosts.server_entry()
    rc, out, err = _run([hosts.interpreter(), desc_path, "--describe"], timeout=300)
    if rc != 0:
        return _item("③ 工具数 == schema 声明数", False,
                     "`server.py --describe` 退出码 %s：%s" % (rc, (err or out).strip()[-160:]),
                     "先查 `daniel --self-test`；server 起不来时 ② 会一起红")
    try:
        desc = json.loads(out)
    except ValueError:
        return _item("③ 工具数 == schema 声明数", False, "`--describe` 输出不是合法 JSON",
                     "跑 `daniel --self-test` 定位（schema 与实现可能漂移）")
    counts = desc.get("counts") or {}
    registered = counts.get("registered")
    declared_by_server = counts.get("cliDeclared")
    doc, bad = _cli_json(["schema"])
    cli_declared = None
    if doc is not None:
        mods = ((doc.get("data") or {}).get("modules")) or []
        cli_declared = sum(len(m.get("commands") or []) for m in mods)
    ok = (registered == declared_by_server == cli_declared and registered is not None)
    ev = ("MCP 实注册 %s ｜ server 声明 %s ｜ CLI 声明 %s 条"
          % (registered, declared_by_server, cli_declared))
    if doc is None:
        ev += "（CLI 声明数取不到：%s）" % "；".join(bad)
    return _item("③ 工具数 == schema 声明数", ok, ev,
                 "跑 `daniel schema --check`（应 10/10）与 `daniel --self-test`；"
                 "两者报出的差异清单就是修法来源")


# ─────────────────────────── D4 只读命令取到真实数据 ───────────────────────────
def check_live_read():
    doc, bad = _cli_json(["brands", "list", "--limit", "3"], timeout=300)
    if doc is None:
        return _item("④ 只读命令取到真实数据", False,
                     "`daniel brands list` 没跑通：%s" % "；".join(bad),
                     "跑 `daniel account credentials` 看凭据来源；"
                     "新机器上走三步：`daniel account credentials set --from-env --confirm` → "
                     "`daniel account login --confirm` → 再跑本条")
    d = doc.get("data") or {}
    rows = d.get("品牌") or d.get("brands") or d.get("rows") or []
    if isinstance(rows, dict):
        rows = rows.get("品牌") or []
    n = len(rows) if isinstance(rows, list) else 0
    ok = bool(doc.get("ok")) and n > 0
    first = ""
    if n and isinstance(rows[0], dict):
        first = "%s（编号 %s）" % (rows[0].get("品牌名") or rows[0].get("name"),
                                  rows[0].get("品牌编号") or rows[0].get("id"))
    return _item("④ 只读命令取到真实数据", ok,
                 "`daniel brands list` 返回 %d 条真实品牌%s" % (n, ("，例如 " + first) if first else ""),
                 "同 ④ 的修法：先修凭据／登录，再复跑 `daniel brands list --json`")


# ─────────────────────────── D5 每个宿主的接入状态 ───────────────────────────
def entry_diffs(key, st):
    """本机那段接入与"本次现算"的逐字段差异（**只读判定，不写任何东西**）。

    `--list` 与 `--doctor` 共用它 —— 同一判据只写一份，"两处说法不一样"在结构上不可能发生。
    """
    want = hosts.entry_payload()
    got = st.get("取值") or {}
    diffs = []
    if got.get("command") and hosts._norm(got.get("command")) != hosts._norm(want["command"]):  # noqa: SLF001
        diffs.append("解释器 %s ⇒ %s" % (got.get("command"), want["command"]))
    got_args = got.get("args") or []
    if got_args and hosts._norm(got_args[0]) != hosts._norm(want["args"][0]):          # noqa: SLF001
        diffs.append("服务入口 %s ⇒ %s" % (got_args[0], want["args"][0]))
    if got.get("cwd") and hosts._norm(got.get("cwd")) != hosts._norm(want["cwd"]):     # noqa: SLF001
        diffs.append("工作目录 %s ⇒ %s" % (got.get("cwd"), want["cwd"]))
    home_got = (got.get("env") or {}).get("DANIEL_HOME")
    if home_got and hosts._norm(home_got) != hosts._norm(want["env"]["DANIEL_HOME"]):  # noqa: SLF001
        diffs.append("数据落点 %s ⇒ %s" % (home_got, want["env"]["DANIEL_HOME"]))
    return diffs


def check_host(key):
    st = hosts.read_state(key)
    path = st.get("配置文件")
    fix = "daniel connect --host %s --apply --confirm" % key
    if not st.get("宿主是否检测到"):
        return _item("⑤ 宿主 %s：接入状态" % key, False,
                     "未检测到 %s（%s 不存在）⇒ 本机没有这个宿主的痕迹，本命令不会假装" "已接入"
                     % (hosts.host_meta(key)["title"], os.path.dirname(path)),
                     "装上 %s 后复跑；确认要写就手工建目录再跑 `%s`"
                     % (hosts.host_meta(key)["title"], fix))
    if not st.get("存在"):
        return _item("⑤ 宿主 %s：接入状态" % key, False,
                     "未接入（配置文件不存在：%s）" % path, fix)
    if st.get("解析错误"):
        return _item("⑤ 宿主 %s：接入状态" % key, False,
                     "接入状态判不出来：%s" % st["解析错误"],
                     "先修好 %s（本命令不擅自改写看不懂的配置）" % path)
    n = st.get("条目数")
    if n == 0:
        return _item("⑤ 宿主 %s：接入状态" % key, False,
                     "未接入（%s 里没有本产品条目；文件里另有 server：%s）"
                     % (path, "、".join(st.get("其它成员") or []) or "无"), fix)
    if n > 1:
        return _item("⑤ 宿主 %s：接入状态" % key, False,
                     "接入有重复：本产品条目 **%d 条**（应当恰好 1 条）" % n,
                     "先手工删掉多余的那几条，再跑 `%s`（本命令只写一条，不会替你猜哪条是对的）"
                     % fix)
    diffs = entry_diffs(key, st)
    if diffs:
        stale = any("服务入口" in d for d in diffs)
        return _item("⑤ 宿主 %s：接入状态" % key, False,
                     "已接入但%s：%s" % ("指向旧副本" if stale else "与本机现算不一致",
                                        "；".join(diffs)), fix)
    return _item("⑤ 宿主 %s：接入状态" % key, True,
                 "已接入（指向当前包）：%s ｜ 本产品条目 1 条 ｜ 其它 server：%s"
                 % (path, "、".join(st.get("其它成员") or []) or "无"))


def check_cross_host(keys):
    """两宿主的数据落点必须一致（不一致的话两宿主看到的状态与产出会对不上）。"""
    rows = {}
    for k in keys:
        st = hosts.read_state(k)
        if st.get("条目数") == 1:
            rows[k] = (st.get("取值") or {}).get("env", {}).get("DANIEL_HOME")
    if len(rows) < 2:
        return None
    vals = {v for v in rows.values() if v}
    ok = len(vals) <= 1
    return _item("⑥ 跨宿主一致性", ok,
                 "两宿主数据落点：%s" % "；".join("%s=%s" % (k, v) for k, v in sorted(rows.items())),
                 "让两宿主指向同一个数据落点：`daniel connect --host cursor --apply --confirm`"
                 " ＋ `daniel connect --host codex --apply --confirm`")


def run_doctor(host=None, progress=None):
    """跑完全部断言，返回 `{通过, 检查项, 结论, 现算路径}`。"""
    keys = [host] if host else hosts.host_keys()
    for k in keys:
        hosts.host_meta(k)
    items = []
    if progress:
        progress("① 包完整性（能力束）")
    items.append(check_package())
    if progress:
        progress("② MCP server 起得来（复用 mcp/client_check.py）")
    items.append(check_server())
    if progress:
        progress("③ 工具数 == schema 声明数")
    items.append(check_tool_count())
    if progress:
        progress("④ 只读命令取到真实数据")
    items.append(check_live_read())
    for k in keys:
        if progress:
            progress("⑤ 宿主 %s 的接入状态" % k)
        items.append(check_host(k))
    cross = check_cross_host(keys)
    if cross is not None:
        items.append(cross)
    failed = [i for i in items if not i["通过"]]
    return {
        "通过": not failed,
        "检查项": items,
        "现算路径": hosts.paths(),
        "结论": ("全部通过：接入可用（%d 项）" % len(items)) if not failed else
                "未通过：%d 项（逐项修法见下面每一项的「修法」）—— 最快的整体修法是 "
                "`daniel connect --host cursor --apply --confirm`"
                " ＋ `daniel connect --host codex --apply --confirm`" % len(failed),
        "修法": [i.get("修法") for i in failed if i.get("修法")],
    }


def exit_code_for(result):
    return EXIT_OK if result.get("通过") else EXIT_INTERNAL
