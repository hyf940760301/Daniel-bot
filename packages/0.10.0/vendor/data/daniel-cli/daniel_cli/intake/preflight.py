# -*- coding: utf-8 -*-
"""前置条件实查：**能查的必须去查**，查不到才写"需你提供"。

用户口径
--------
> 「**前置于工序的告知必须准确：能查的必须去查，不许把该查的写成请提供**」

所以本模块对每一条前置条件按来源类型分流：

| 来源类型 | 本模块做什么 |
|---|---|
| `人提供` | 不猜、不补：状态记「需你提供」，并写清"缺了怎么补" |
| `系统内已有` | **真调一次只读命令**（子进程跑 `daniel <模块> <子命令> --json`），把退出码／条数／耗时当证据 |
| `可推导` | 同上：先把原料取到手（口径在语料里，本模块不替业务算结论） |
| `模式能力` | 按当前模式**真实可用**的能力集合判三态（`可直接执行`／`需人工确认后执行`／`当前模式不可用`）；写动作给出确认单与可直接执行的命令 |

三条纪律
--------
① **不硬跑**：前置不齐时不执行任何工序动作，只输出"缺什么＋怎么补"（缺件阻断）；
② **不假装**：占位符（如"哪个品牌"）没确定时状态是「待定」并说明怎么确定，**不谎称已满足**；
   实查失败（链路异常）如实记「取数失败」，**不降级成"请你提供"**；
③ **措辞按产品级口径**（用户 2026-10-15 裁决）：MCP 模式下遇到写动作**不许**说"不支持／能力缺失"，
   要说「本工序最后一步是<动作>，需要你确认；确认单与可执行命令如下」。
"""
import json
import os
import shlex
import subprocess
import sys
import time

from . import catalog, modes

#: 命令占位符 → 变量名（这些是"只有用户能给的上下文"，不能瞎猜）
V_BRAND = "品牌"

#: 公共前置条件（对每一道工序都成立）：取数链路本身可用。它不是"某道工序的输入"，
#: 但它是**必须真查**的 —— 链路不通时后面所有"系统内已有"的项都无从谈起。
COMMON_ITEM = {
    "名称": "Daniel 取数链路可用（当前账号会话有效）",
    "来源类型": catalog.SOURCE_SYSTEM,
    "取数方式": "daniel account whoami",
    "说明": "这次要真去 Daniel 取数，先确认会话能用；不能取数时本工序只能停在告知阶段",
}

ST_OK = "已满足"
ST_MISSING = "缺失"
ST_PENDING = "待定"
ST_NEED_YOU = "需你提供"
ST_FAILED = "取数失败"
ST_NOT_PROBED = "未实查"

#: 本包位置：`<仓库根>/data/daniel-cli/daniel_cli/intake/<本文件>` → 上溯三层是 `data/daniel-cli`
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_TIMEOUT = 30


def cli_entry():
    """本 CLI 的可执行入口（`bin/daniel`）。"""
    return os.path.join(_PKG_ROOT, "bin", "daniel")


def _workdir():
    """取数时的工作目录：仓库根（相对路径类命令才有稳定含义；定位不到就用手头目录）。"""
    up = os.path.dirname(os.path.dirname(_PKG_ROOT))          # data/daniel-cli → 仓库根
    return up if os.path.isdir(up) else os.getcwd()


def _run_argv(argv, timeout=DEFAULT_TIMEOUT):
    t0 = time.time()
    try:
        p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, cwd=_workdir())
    except subprocess.TimeoutExpired:
        return {"退出码": None, "超时": True, "耗时毫秒": int((time.time() - t0) * 1000),
                "stdout": "", "stderr": "探测超时（%d 秒）" % timeout}
    except OSError as e:
        return {"退出码": None, "超时": False, "耗时毫秒": int((time.time() - t0) * 1000),
                "stdout": "", "stderr": "起不来：%s" % e}
    return {"退出码": p.returncode, "超时": False, "耗时毫秒": int((time.time() - t0) * 1000),
            "stdout": p.stdout or "", "stderr": p.stderr or ""}


def _count_of(data):
    """从命令产出里取"条数"（报告里的证据；取不到就 None，不编）。"""
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("count", "条数", "总数", "total", "条目数"):
            v = data.get(key)
            if isinstance(v, int) and not isinstance(v, bool):
                return v
        for key in ("lists", "brands", "items", "campaigns", "searches", "workspaces",
                    "videos", "actions", "keywords", "topics", "reviews", "results",
                    "competitors", "routes", "检查项"):
            v = data.get(key)
            if isinstance(v, list):
                return len(v)
    return None


class Probe:
    """一次路由过程中的取数器：同一个命令只跑一次（带缓存），并留下证据。"""

    def __init__(self, live=True, timeout=DEFAULT_TIMEOUT, runner=None, mode=None,
                 capability_set=None, argv_prefix=None):
        self.live = bool(live)
        self.timeout = int(timeout or DEFAULT_TIMEOUT)
        self.runner = runner or (lambda argv, timeout: _run_argv(argv, timeout))
        self.mode = modes.current_mode(mode)
        self.capability_set = capability_set          # 自检注入用（默认取当前模式真实集合）
        self.argv_prefix = argv_prefix or [sys.executable or "python3", cli_entry()]
        self.calls = []
        self._cache = {}
        self._data = {}

    def capabilities(self):
        if self.capability_set is not None:
            return set(self.capability_set)
        return set(modes.available(self.mode)["能力集合"])

    def run(self, key, params_echo, argv):
        """跑一条只读命令（同一条只跑一次）。返回证据字典（不含完整产出）。"""
        ck = tuple(argv)
        if ck in self._cache:
            return self._cache[ck]
        if not self.live:
            row = {"命令": "daniel %s%s" % (key.replace(".", " "), params_echo),
                   "退出码": None, "耗时毫秒": 0, "条数": None, "实查": False,
                   "说明": "本次未实查（--no-probe）：状态按声明给出，不谎称已满足"}
            self._cache[ck] = row
            self.calls.append(row)
            return row
        out = self.runner(list(self.argv_prefix) + list(argv) + ["--json"], self.timeout)
        doc, data = None, None
        text = (out.get("stdout") or "").strip()
        if text:
            try:
                doc = json.loads(text)
                data = (doc or {}).get("data")
            except ValueError:
                doc = None
        where = None
        if isinstance(doc, dict):
            err = doc.get("error")
            if isinstance(err, dict):
                where = err.get("message")
        row = {"命令": "daniel %s%s" % (key.replace(".", " "), params_echo),
               "退出码": out.get("退出码"), "耗时毫秒": out.get("耗时毫秒"),
               "条数": _count_of(data), "实查": True, "超时": bool(out.get("超时")),
               "错误": where}
        self._cache[ck] = row
        self.calls.append(row)
        self._data[ck] = data
        if data is not None:
            self._last_data = data
        return row

    def data_of(self, row):
        """取回某条证据的完整产出（内部用；不进报告）。"""
        for ck, r in self._cache.items():
            if r is row:
                return self._data.get(ck)
        return None

    def data_of_key(self, key):
        """按能力键（`<模块>.<子命令>`）取回产出（草稿要拿真实产出的形状，内部用）。"""
        head = "daniel %s" % str(key).replace(".", " ")
        for ck, r in self._cache.items():
            if str(r.get("命令") or "").startswith(head):
                return self._data.get(ck)
        return None

    def list_keys(self, key):
        """产出里"是列表且元素是对象"的键（能给交付件当子表的那些）。"""
        data = self.data_of_key(key)
        out = []
        if isinstance(data, list) and data and isinstance(data[0], dict):
            out.append(None)
        elif isinstance(data, dict):
            out = [k for k, v in data.items() if isinstance(v, list) and v
                   and isinstance(v[0], dict)]
        return out


def _split_optional(text):
    """把命令模板拆成"必写段"与"可写段 `[...]`"。

    可写段里若还有未确定的变量（例如 `--limit <条数>`），整段去掉即可 —— 于是同一条前置条件
    在"上下文不全"时仍能真查一次，而不是一律记成待定。
    """
    required, optional, buf, depth = [], [], [], 0
    for ch in str(text or ""):
        if ch == "[":
            if depth == 0:
                buf = []
            depth += 1
            continue
        if ch == "]":
            if depth == 1:
                optional.append("".join(buf))
                buf = []
                depth = 0
                continue
            depth = max(0, depth - 1)
        if depth >= 1:
            buf.append(ch)
        else:
            required.append(ch)
    if buf:
        optional.append("".join(buf))            # 未闭合的 `[` 当可写段处理（模板写歪了也不崩）
    return "".join(required), optional


def _substitute(text, variables):
    """把占位符换成实参；返回 `(填好的文本, 未确定的变量名列表)`。"""
    out = str(text or "")
    missing = []
    for name in catalog.placeholders_of(out):
        value = variables.get(name)
        if value in (None, ""):
            if name not in missing:
                missing.append(name)
        else:
            out = out.replace("<%s>" % name, str(value))
    return out, missing


def _command_pieces(how):
    """一段"取数方式" → `[(能力键, 参数文本)]`（一条前置条件可能给多条命令，用「＋」分隔）。"""
    pieces = []
    for chunk in str(how or "").replace("＋", "|").replace("，", "|").split("|"):
        keys = catalog.command_keys_of(chunk)
        if not keys:
            continue
        key = keys[0]
        head = "daniel %s" % key.replace(".", " ")
        params = chunk.split(head, 1)[1] if head in chunk else ""
        pieces.append((key, params.strip()))
    return pieces


def _required_params(key, variables):
    """写命令的必填参数拼成一段文本（能确定的就填真值，其余留给占位符）。

    目的：确认单里给出的命令必须**能照着跑**（例如 `mentions run` 必须要 `--brand`），
    不能只给一条半截命令让人猜。`variables` 是已解析的变量（`{品牌: …}`）。
    """
    spec = _command_spec(key) or {}
    variables = variables if isinstance(variables, dict) else {}
    bits = []
    for opt in spec.get("options") or []:
        if not opt.get("required"):
            continue
        name = opt["name"]
        value = variables.get({"--brand": V_BRAND}.get(name)) or None
        bits.append("%s %s" % (name, value if value else "<%s>" % (opt.get("metavar")
                                                                 or name.lstrip("-"))))
    return " ".join(bits)


def _register_row(key):
    """`TICKET-159` 差异登记表里这条命令的登记（没有就 None）。"""
    try:
        rows, _why, _sem = modes.read_exposure_register()
    except Exception:                                            # noqa: BLE001
        return None
    return (rows or {}).get(key)


def _register_semantics(key):
    """这条命令在 MCP 侧的执行语义（`执行`／`确认单不执行`／`未注册`）；没登记就 None。"""
    return ((_register_row(key) or {}).get("执行语义") or None)


def _command_spec(key):
    from .. import schema as cli_schema
    mod, _, cmd = str(key).partition(".")
    return cli_schema.find_command(mod, cmd)


def _argv_of(params_text):
    """把参数文本切成 argv（去掉占位符残渣与多余空白）。"""
    text = str(params_text or "").replace("<", "").replace(">", "").strip()
    if not text:
        return []
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _params_echo(params_text):
    text = " ".join(str(params_text or "").split())
    return (" " + text) if text else ""


class Preflight:
    """对一道工序跑一遍前置条件实查。"""

    def __init__(self, probe=None, need="", brand=None):
        self.probe = probe or Probe()
        self.need = need or ""
        self.brand_arg = brand
        self._brand = None
        self._brand_why = None
        self._brand_probe = None

    # ── 变量解析（品牌：你给的 → 需求里认出来 → 都没有就说"还没确定"） ──
    def brand(self):
        if self._brand is not None or self._brand_why is not None:
            return self._brand, self._brand_why, self._brand_probe
        if self.brand_arg:
            self._brand, self._brand_why = str(self.brand_arg), "你给定了品牌（--brand）"
            return self._brand, self._brand_why, None
        row = self.probe.run("brands.list", " --limit 200", ["brands", "list", "--limit", "200"])
        self._brand_probe = row
        names = []
        data = self.probe.data_of(row)
        if isinstance(data, dict):
            for one in data.get("brands") or []:
                if isinstance(one, dict) and one.get("name"):
                    names.append(str(one["name"]).strip())
        low = self.need.lower()
        hit = None
        for name in sorted(names, key=len, reverse=True):
            if len(name) >= 3 and name.lower() in low:
                hit = name
                break
        if hit:
            self._brand = hit
            self._brand_why = "从需求里认出品牌「%s」（先把 Daniel 的品牌清单真查了一遍再比对）" % hit
        else:
            self._brand = None
            n = row.get("条数")
            self._brand_why = ("需求里没点明品牌（Daniel 里现有 %s 个品牌，已实查）"
                               "—— 请给 `--brand <品牌名或编号>`" % (n if n is not None else "若干"))
        return self._brand, self._brand_why, self._brand_probe

    def variables(self):
        brand, why, _probe = self.brand()
        return {V_BRAND: brand}, why

    # ── 逐条前置条件 ──
    def check_item(self, item, extra_vars=None):
        src = item["来源类型"]
        base = {"名称": item["名称"], "来源类型": src, "取数方式": item["取数方式"],
                "说明": item["说明"]}
        if src == catalog.SOURCE_HUMAN:
            base.update({"状态": ST_NEED_YOU, "是否阻断": True, "证据": None,
                         "怎么补": item["说明"] or "请提供这一项后再开工"})
            return base
        variables, why = self.variables()
        variables.update(extra_vars or {})
        pieces = _command_pieces(item["取数方式"])
        if not pieces:
            base.update({"状态": ST_MISSING, "是否阻断": True, "证据": None,
                         "怎么补": "这条前置条件的取数方式没写清（工序表里的缺陷，请回报）"})
            return base
        evidences, states, fixes = [], [], []
        for key, params in pieces:
            filled, missing = _substitute(params, variables)
            required_part, optional_parts = _split_optional(filled)
            keep_optional = [o for o in optional_parts if not catalog.placeholders_of(o)]
            dropped = [o for o in optional_parts if catalog.placeholders_of(o)]
            still = catalog.placeholders_of(required_part)
            if missing and not still:
                still = [m for m in missing]
            if still:
                states.append(ST_PENDING)
                fixes.append("先确定「%s」（%s）—— 确定之后这条能直接取到" %
                             ("、".join(still), why or "缺上下文"))
                continue
            params_text = required_part + "".join(keep_optional)
            row = dict(self.probe.run(key, _params_echo(params_text),
                                      key.split(".") + _argv_of(params_text)))
            if dropped:
                row["略去可选参数"] = [d.strip() for d in dropped]
            evidences.append(row)
            if not row.get("实查"):
                states.append(ST_NOT_PROBED)
                fixes.append("去掉 `--no-probe` 后重跑即可实查")
                continue
            code = row.get("退出码")
            if code == 0 and row.get("条数") == 0:
                states.append(ST_MISSING)
                fixes.append("这条命令跑通了但取到 0 条 —— 该对象在 Daniel 里还是空的"
                             "（先看 `daniel brands list`／`daniel lists by-brand`）")
            elif code == 0:
                states.append(ST_OK)
            elif code == 2:
                states.append(ST_MISSING)
                fixes.append(row.get("错误")
                             or "Daniel 里没有这个对象／这个账号看不到它（先用 daniel brands list 看一眼）")
            else:
                states.append(ST_FAILED)
                fixes.append("取数失败（退出码 %s）：%s；链路问题先跑 `daniel account whoami` 复核"
                             % (code, row.get("错误") or row.get("说明") or "接口或网络异常"))
        state = ST_OK
        for st in (ST_FAILED, ST_MISSING, ST_PENDING, ST_NOT_PROBED, ST_OK):
            if st in states:
                state = st
                break
        blocking = state in (ST_FAILED, ST_MISSING, ST_PENDING)
        base.update({"状态": state, "是否阻断": blocking, "证据": evidences,
                     "怎么补": "；".join(dict.fromkeys(fixes)) if fixes else "无需补充（系统里已有）"})
        return base

    # ── 模式能力（三态） ──
    def check_capability(self, key):
        mode = self.probe.mode
        caps = self.probe.capabilities()
        spec = _command_spec(key) or {}
        action = (spec.get("summary") or key).split("（")[0].strip() or key
        if modes.is_write(key):
            line = modes.confirm_command(key, _required_params(key, self.variables()[0]))
            sem = _register_semantics(key)
            reg_row = _register_row(key) or {}
            if mode == modes.MODE_MCP:
                how = ("本工序最后一步是「%s」，需要你确认（MCP 模式下 AI 不自行执行写动作）："
                       "把下面这条命令拿到 CLI／桌面壳里跑即可" % action)
            else:
                how = ("本工序最后一步是「%s」，是写操作：先跑不带 --confirm 的干跑"
                       "（打印将要做什么与影响范围），你点头后加 --confirm 执行" % action)
            if sem:
                how += "｜模式能力真源：%s（该命令在 MCP 侧的执行语义：%s）" % (
                    reg_row.get("工具名") or "exposure-register.json", sem)
            return {"名称": "写动作：%s" % action, "来源类型": catalog.SOURCE_MODE,
                    "取数方式": line, "状态": modes.ST_CONFIRM,
                    "是否阻断": False, "是否需要确认": True, "说明": how,
                    "能力键": key, "模式": mode, "可直接执行的命令": line,
                    "执行语义": sem or None,
                    "替代路径": reg_row.get("替代路径") or None,
                    "确认单": {"动作": action, "能力键": key, "命令": line,
                             "影响范围": spec.get("danger") or "见该命令帮助里写明的写语义",
                             "回读方式": "执行后回读校验（写命令自带回读与审计留痕）",
                             "执行语义": sem or None}}
        if key in caps:
            return None                       # 读链在当前模式可用 → 不是前置条件（无需列）
        return {"名称": "本模式缺少的能力：%s" % action, "来源类型": catalog.SOURCE_MODE,
                "取数方式": "daniel %s" % key.replace(".", " "),
                "状态": modes.ST_UNAVAILABLE, "是否阻断": True,
                "说明": "当前模式（%s）的能力集合里没有这条命令，本工序在当前模式下做不完整"
                        % modes.mode_label(mode),
                "能力键": key, "模式": mode,
                "怎么补": "换到有此能力的模式执行（CLI 模式是完整能力集成），"
                          "或先把这条能力登记进模式能力真源（schema.py 单一真源）"}


def capability_summary(process, mode=None, capability_set=None, brand=None):
    """一道工序的「模式能力」三态总账（**直接把三态摆出来**，不是只在缺件时才出现）。

    返回 `{模式, 能力真源, 可直接执行[], 需人工确认后执行[], 当前模式不可用[], 说明}`：
      · `可直接执行`：该步在当前模式下能真跑（读链）；
      · `需人工确认后执行`：该步是写动作（CLI 走 --confirm；MCP 出确认单，由人拿到 CLI 跑）；
      · `当前模式不可用`：真缺失（当前模式的能力集合里没有这条命令）——**只有这一态才是硬缺件**。
    """
    mode = modes.current_mode(mode)
    caps = set(capability_set) if capability_set is not None else set(
        modes.available(mode)["能力集合"])
    buckets = {modes.ST_READY: [], modes.ST_CONFIRM: [], modes.ST_UNAVAILABLE: []}
    rows = []
    for key in process.get("需要能力") or []:
        spec = _command_spec(key) or {}
        action = (spec.get("summary") or key).split("（")[0].strip() or key
        if modes.is_write(key):
            state, extra = modes.ST_CONFIRM, {
                "可直接执行的命令": modes.confirm_command(
                    key, _required_params(key, {V_BRAND: brand})),
                "执行语义": _register_semantics(key)}
        elif key in caps:
            state, extra = modes.ST_READY, {}
        else:
            state, extra = modes.ST_UNAVAILABLE, {}
        row = {"能力键": key, "动作": action, "状态": state,
               "何时用到": "这道工序的最后一步（写动作）" if state == modes.ST_CONFIRM
                           else "取数步骤"}
        row.update(extra)
        rows.append(row)
        buckets[state].append(row)
    return {
        "模式": mode, "模式说明": modes.mode_label(mode),
        "能力真源": modes.available(mode)["真源"],
        "可直接执行": buckets[modes.ST_READY],
        "需人工确认后执行": buckets[modes.ST_CONFIRM],
        "当前模式不可用": buckets[modes.ST_UNAVAILABLE],
        "明细": rows,
        "说明": "三态口径：`可直接执行`＝读链能真跑；`需人工确认后执行`＝写动作要人点头"
                "（CLI 走 --confirm；MCP 出确认单，由人拿到 CLI／桌面壳执行）；"
                "`当前模式不可用`＝真缺失，**只有这一态才是硬缺件阻断**。",
    }


def analyse(process, need="", brand=None, live=True, timeout=DEFAULT_TIMEOUT, mode=None,
            runner=None, capability_set=None, extra_vars=None, declare_only=False,
            probe=None):
    """对一道工序做完整的前置条件实查（含公共项与模式能力三态）。

    `declare_only=True`：只声明不实查（用于"只深查 Top1，其余候选先看清单"的场合）。
    `probe`：复用**同一个取数器**（草稿生成要靠它拿真实产出的形状，所以两条链路必须共用一次取数）。
    返回 `{工序, 前置条件[], 缺件[], 待确认[], 可执行, 实查记录[], 结论}`。
    """
    probe = probe or Probe(live=(live and not declare_only), timeout=timeout, runner=runner,
                           mode=mode, capability_set=capability_set)
    pf = Preflight(probe=probe, need=need, brand=brand)
    items = [pf.check_item(COMMON_ITEM, extra_vars)]
    for it in process.get("前置条件") or []:
        items.append(pf.check_item(it, extra_vars))
    for key in process.get("需要能力") or []:
        row = pf.check_capability(key)
        if row is not None:
            items.append(row)

    brand_v, brand_why, brand_probe = pf.brand()
    if brand_probe:
        for it in items:
            if it["名称"] == COMMON_ITEM["名称"]:
                it["证据"] = list(it.get("证据") or []) + [
                    dict(brand_probe, 用途="品牌清单（用来认品牌；也是「取数链路可用」的证据）")]

    missing = [i for i in items if i.get("是否阻断")]
    confirm = [i for i in items if i.get("是否需要确认")]
    ok = not missing
    if ok and confirm:
        concl = ("前置条件齐了，可以开工；最后一步是写动作，需要你先确认（%s）"
                 % "、".join(i["名称"].split("：")[-1] for i in confirm))
    elif ok:
        concl = "前置条件齐了，可以开工"
    else:
        concl = "前置条件不齐，先补齐再开工（%d 项）：%s" % (
            len(missing), "；".join("%s → %s" % (i["名称"], i["怎么补"]) for i in missing[:4]))
    return {
        "工序": process["工序"], "工序键": process["工序键"],
        "能力域": process["能力域"], "能力域标题": process["能力域标题"],
        "前置条件": items, "缺件": missing, "待确认": confirm,
        "可执行": ok, "实查记录": probe.calls, "深度": "声明" if declare_only else "实查",
        "品牌": {"值": brand_v, "来源": brand_why},
        "模式": probe.mode, "结论": concl,
    }
