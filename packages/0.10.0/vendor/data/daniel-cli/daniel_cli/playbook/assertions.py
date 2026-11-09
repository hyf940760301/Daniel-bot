# -*- coding: utf-8 -*-
"""断言引擎：把契约里声明的判据／门禁／自检变成**可执行断言**（TICKET-146 §2 任务内容）。

取值引用（写 `<前缀>.<路径>` 即视为引用，否则按字面量处理）：

| 引用 | 含义 | 例 |
|---|---|---|
| `运行.*` | 本次运行的运行期事实 | `运行.样本模式`、`运行.沙箱目录` |
| `输入.*` | 契约 `输入` 的取值（默认值或 `--input` 覆盖） | `输入.品牌` |
| `变量.*` | 步骤产出的变量 | `变量.写入结果.回读内容` |
| `限额.*.{默认\|硬上限\|实际}` | 样本上限 | `限额.行数上限.实际` |
| `步骤.<id>.<字段>` | 某步骤的结果（状态／退出码／条目数／数据／路径／内容／存在） | `步骤.S3.条目数` |
| `交付件.*` | 交付件的产出事实 | `交付件.行数` |
| `契约.*` | 契约自身 | `契约.id` |

字符串里出现 `${表达式}` 时按模板展开（例：`${运行.沙箱目录}/写入证明.txt`）。

**退化纪律**：取值取不到时**不许静默当成通过** —— 引用不存在 → 判据记 `失败`；
依赖的步骤被门禁拦下而未执行 → 判据记 `跳过`（`Unavailable`），计数照样对得上。
"""
import os
import re

from . import model

REF_RE = re.compile(r"^(%s)\.[^\s]+$" % "|".join(model.REF_ROOTS))
TPL_RE = re.compile(r"\$\{([^}]+)\}")


class Unavailable(Exception):
    """取值不可得：依赖的步骤被拦下／跳过，而不是值本身错了。"""


class UnknownRef(Exception):
    """引用了不存在的取值路径（契约写错了）。"""


def _dig(obj, path, ref):
    cur = obj
    for part in path:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise UnknownRef(ref)
    return cur


def lookup(ref, state):
    parts = ref.split(".")
    root, rest = parts[0], parts[1:]
    if root == "运行":
        return _dig(state.运行, rest, ref)
    if root == "契约":
        return _dig(state.契约摘要, rest, ref)
    if root == "输入":
        return _dig(state.输入值, rest, ref)
    if root == "变量":
        return _dig(state.变量, rest, ref)
    if root == "限额":
        name = rest[0] if rest else None
        if name not in state.限额:
            raise UnknownRef(ref)
        field = rest[1] if len(rest) > 1 else "实际"
        return _dig(state.限额[name], [field], ref)
    if root == "步骤":
        sid = rest[0] if rest else None
        if sid not in state.步骤:
            raise UnknownRef(ref)
        res = state.步骤[sid]
        if res.get("状态") == model.ST_SKIP:
            raise Unavailable("步骤 %s 未执行（被门禁拦下或前置未通过）" % sid)
        # TICKET-156：`步骤.<id>` 后面的**整段路径**都要走完。旧写法只取 `rest[1]`，
        # 把后面的路径段丢掉 ⇒ `步骤.S1.数据.count` 取成整个 dict（断言报错还看得见），
        # 而 `条目数不超过 取值 步骤.S1.数据.brands` 会对 dict 取 len() 得"键数"——**假通过**。
        # 只写 `步骤.<id>`（不给字段）时保持老口径：默认看该步骤的状态。
        return _dig(res, rest[1:] or ["状态"], ref)
    if root == "交付件":
        if state.交付件.get("状态") == model.ST_SKIP:
            raise Unavailable("交付件未生成")
        return _dig(state.交付件, rest, ref)
    if root == "自身":
        return _dig(state.自身, rest, ref)
    raise UnknownRef(ref)


def expand_template(text, state):
    """展开 `${表达式}` 模板；表达式取不到就抛错（不静默留空）。"""
    if not isinstance(text, str) or "${" not in text:
        return text

    def _sub(m):
        raw = m.group(1).strip()
        if not REF_RE.match(raw):
            raise UnknownRef("${%s}" % raw)
        return str(lookup(raw, state))

    return TPL_RE.sub(_sub, text)


def resolve(raw, state):
    """解析一个操作数：引用 → 取值；含 `${}` 的字符串 → 模板；其余 → 字面量。"""
    if isinstance(raw, dict) and set(raw) == {"字面量"}:
        return raw["字面量"]
    if isinstance(raw, str):
        if REF_RE.match(raw):
            return lookup(raw, state)
        if "${" in raw:
            return expand_template(raw, state)
    return raw


def _brief(v):
    s = repr(v)
    return s if len(s) <= 160 else s[:157] + "..."


def _num(v):
    if isinstance(v, bool):
        raise ValueError("布尔值不能参与大小比较")
    return float(v)


def evaluate(spec, state):
    """执行一条断言：返回 `(状态, 明细)`。"""
    if not isinstance(spec, dict):
        return model.ST_FAIL, "断言必须是对象（含 `类型` 与操作数）"
    t = spec.get(model.A_TYPE)
    if t not in model.ASSERTION_VOCAB:
        return model.ST_FAIL, "未知断言类型：%r（可用：%s）" % (t, "／".join(model.ASSERTION_VOCAB))
    need = model.ASSERTION_VOCAB[t]
    missing = [k for k in need if k not in spec]
    if missing:
        return model.ST_FAIL, "断言「%s」缺操作数：%s" % (t, missing)

    try:
        args = {k: resolve(spec[k], state) for k in need}
    except Unavailable as e:
        return model.ST_SKIP, str(e)
    except (UnknownRef, KeyError) as e:
        return model.ST_FAIL, "取值不可解析：%s" % e

    try:
        return _run(t, args, state)
    except (TypeError, ValueError) as e:
        return model.ST_FAIL, "断言「%s」无法比较：%s（取值 %s）" % (t, e, _brief(list(args.values())))


def _run(t, a, state):
    if t == "等于":
        ok = a[model.A_VALUE] == a[model.A_EXPECT]
        return _res(ok, "%s ＝ %s" % (_brief(a[model.A_VALUE]), _brief(a[model.A_EXPECT])))
    if t == "不等于":
        ok = a[model.A_VALUE] != a[model.A_EXPECT]
        return _res(ok, "%s ≠ %s" % (_brief(a[model.A_VALUE]), _brief(a[model.A_EXPECT])))
    if t in ("大于", "大于等于", "小于", "小于等于"):
        x, y = _num(a[model.A_VALUE]), _num(a[model.A_THRESHOLD])
        ok = {"大于": x > y, "大于等于": x >= y, "小于": x < y, "小于等于": x <= y}[t]
        return _res(ok, "%s %s %s" % (x, t, y))
    if t == "非空":
        ok = bool(a[model.A_VALUE]) or a[model.A_VALUE] == 0
        return _res(ok, "取值 %s" % _brief(a[model.A_VALUE]))
    if t == "为空":
        ok = not a[model.A_VALUE] and a[model.A_VALUE] != 0
        return _res(ok, "取值 %s" % _brief(a[model.A_VALUE]))
    if t in ("包含", "不包含"):
        v, needle = a[model.A_VALUE], a[model.A_EXPECT]
        ok = needle in v if isinstance(v, (str, list, tuple, dict)) else False
        if t == "不包含":
            ok = not ok
        return _res(ok, "%s %s %s" % (_brief(v), "包含" if t == "包含" else "不包含", _brief(needle)))
    if t in ("条目数等于", "条目数不超过"):
        v = a[model.A_VALUE]
        n = len(v) if isinstance(v, (list, tuple, dict, str)) else 1
        if t == "条目数等于":
            ok = n == _num(a[model.A_EXPECT])
            return _res(ok, "条目数 %d ＝ %s" % (n, a[model.A_EXPECT]))
        ok = n <= _num(a[model.A_THRESHOLD])
        return _res(ok, "条目数 %d ≤ %s" % (n, a[model.A_THRESHOLD]))
    if t in ("存在", "不存在"):
        p = a[model.A_VALUE]
        ok = isinstance(p, str) and os.path.exists(p)
        if t == "不存在":
            ok = not ok
        return _res(ok, "%s：%s" % ("存在" if ok else "不存在", _brief(p)))
    if t == "内容一致":
        p, want = a[model.A_VALUE], a[model.A_EXPECT]
        if not (isinstance(p, str) and os.path.isfile(p)):
            return model.ST_FAIL, "回读目标不存在：%s" % _brief(p)
        with open(p, encoding="utf-8") as fh:
            got = fh.read()
        return _res(got == want, "回读内容 %s ／ 期望 %s" % (_brief(got), _brief(want)))
    if t == "无写发生":
        n = len(state.写动作台账)
        return _res(n == 0, "写动作台账 %d 条%s" % (n, "" if n == 0 else "：" + _brief(state.写动作台账)))
    if t == "计数自洽":
        bad = [name for name, c in state.计数.items() if not c.get(model.C_SELF)]
        detail = "；".join("%s：声明 %d＝实跑 %d＝通过 %d＋失败 %d＋跳过 %d"
                          % (name, c[model.C_DECLARED], c[model.C_RUN], c[model.C_PASS],
                             c[model.C_FAIL], c[model.C_SKIP])
                          for name, c in state.计数.items())
        return _res(not bad, detail + ("｜不自洽：%s" % bad if bad else ""))
    if t == "真":
        return _res(bool(a[model.A_VALUE]) or a[model.A_VALUE] == 0, "取值 %s" % _brief(a[model.A_VALUE]))
    return model.ST_FAIL, "断言「%s」没有实现" % t


def _res(ok, detail):
    return (model.ST_PASS if ok else model.ST_FAIL), detail


def check_spec(spec, where, problems):
    """静态检查一条断言声明（`validate` 用）：类型存在、操作数齐备、引用前缀合法。"""
    if not isinstance(spec, dict):
        problems.append("%s：断言必须是对象" % where)
        return
    t = spec.get(model.A_TYPE)
    if t not in model.ASSERTION_VOCAB:
        problems.append("%s：未知断言类型 %r" % (where, t))
        return
    for k in model.ASSERTION_VOCAB[t]:
        if k not in spec:
            problems.append("%s：断言「%s」缺操作数 %s" % (where, t, k))
    for k, v in spec.items():
        if k == model.A_TYPE or not isinstance(v, str):
            continue
        for expr in ([v] if REF_RE.match(v) else []) + TPL_RE.findall(v):
            if REF_RE.match(expr) or REF_RE.match(expr.strip()):
                continue
            problems.append("%s：`%s` 里的引用 `%s` 前缀不合法（可用：%s）"
                            % (where, k, expr, "／".join(model.REF_ROOTS)))


# ─────────────── 引擎级断言自证（TICKET-156：嵌套取值不得静默错值／假通过） ───────────────
#: 自证用的假步骤：**不掺任何真实运行数据**，只是把"对象里带标量、带数组"这两种形状摆出来。
#:
#: 形状取自真实只读命令的产出（例：`brands list` → `{count, brands:[…]}`）：顶层既是对象、
#: 里面有数字、也有数组 —— `步骤.S1.数据.<键>` 这类嵌套路径必须真的走到最后一段。
_SELFTEST_STEPS = {
    "S1": {"状态": model.ST_PASS, "条目数": 5, "退出码": 0,
           "数据": {"count": 5, "brands": ["b1", "b2", "b3", "b4", "b5"]}},
    "S2": {"状态": model.ST_SKIP},
}


class _SelfTestState(object):
    """自证用的最小状态对象：只提供 `步骤.*` 取值需要的那一层。"""

    def __init__(self):
        self.步骤 = _SELFTEST_STEPS
        self.写动作台账 = []
        self.计数 = {}


def assertion_selftest():
    """引擎级自证：返回 `[{用例, 期望, 通过, 明细}, ...]`（`playbook selfcheck` 每次都跑）。

    为什么要有它（TICKET-156）：引擎自己写错过一次取值 —— 对 `步骤.*` 只取前两段，
    后面的路径段被丢掉，于是"不存在的键"会被解析成整个对象，`条目数不超过` 对这个对象
    取 `len()` 得到**键数**，**假通过**（数字看着对、其实量错了东西）。所以这份自证里
    **真阴性是主角**：路径不存在**必须**报「取值不可解析」，绝不许退化成 `len(dict)`。

    自证只跑纯函数（`lookup`／`evaluate`），不联网、不写任何东西、不依赖任何外部状态。
    """
    state = _SelfTestState()
    rows = []

    def case(name, want, fn):
        try:
            ok, detail = fn()
        except Exception as e:                       # 用例自身崩了也记不通过，不静默
            ok, detail = False, "用例抛异常：%s: %s" % (type(e).__name__, e)
        rows.append({"用例": name, "期望": want, "通过": bool(ok), "明细": detail})

    def case_eq(name, ref, expect):
        def run():
            st, detail = evaluate({model.A_TYPE: "等于", model.A_VALUE: ref,
                                   model.A_EXPECT: expect}, state)
            return st == model.ST_PASS, "断言「等于 %s ＝ %r」→ %s（%s）" % (ref, expect, st, detail)
        case(name, "通过", run)

    # ① 正控：嵌套路径取到**真实数字**（旧实现取成整个对象，这一条会失败）
    case_eq("正控·嵌套标量路径取到真数字", "步骤.S1.数据.count", 5)

    # ② 正控：嵌套路径取到**真数组**（旧实现取成整个对象 —— 键数 2，不是 5）
    case_eq("正控·嵌套数组路径取到真数组（条目数）", "步骤.S1.数据.brands", ["b1", "b2", "b3", "b4", "b5"])

    # ③ 真阴性（本票的主角）：路径不存在 → **必须**「取值不可解析」，不许对 dict 取 len 假通过
    def _missing_key():
        st, detail = evaluate({model.A_TYPE: "条目数不超过",
                               model.A_VALUE: "步骤.S1.数据.根本没有这个键",
                               model.A_THRESHOLD: 100}, state)
        ok = (st == model.ST_FAIL) and ("不可解析" in detail)
        return ok, ("断言「条目数不超过 步骤.S1.数据.根本没有这个键 ≤ 100」→ %s（%s）"
                    "｜真阴性判据：不得记「通过」（旧实现会取 len(dict)=2 假通过）"
                    % (st, detail))
    case("真阴性·不存在的键必须报不可解析（不得退化成 len）", "失败＋取值不可解析", _missing_key)

    # ④ 真阴性：不存在的步骤 id 同样必须报不可解析（老口径不许被这次改动带坏）
    def _missing_step():
        st, detail = evaluate({model.A_TYPE: "真", model.A_VALUE: "步骤.S9.数据"}, state)
        ok = (st == model.ST_FAIL) and ("不可解析" in detail)
        return ok, "断言「真 步骤.S9.数据」→ %s（%s）" % (st, detail)
    case("真阴性·不存在的步骤 id 必须报不可解析", "失败＋取值不可解析", _missing_step)

    # ⑤ 回归：浅路径（老契约全部在用的写法）口径一个字没变
    def _shallow():
        got_条目数 = lookup("步骤.S1.条目数", state)
        got_数据 = lookup("步骤.S1.数据", state)
        got_状态 = lookup("步骤.S1", state)
        ok = (got_条目数 == 5 and got_数据 == _SELFTEST_STEPS["S1"]["数据"]
              and got_状态 == model.ST_PASS)
        return ok, ("步骤.S1.条目数＝%r；步骤.S1.数据＝整个产出（%d 个键）；步骤.S1＝%r（默认看状态）"
                    % (got_条目数, len(got_数据) if isinstance(got_数据, dict) else 0, got_状态))
    case("回归·浅路径与「整段数据」的老口径不变", "与旧实现一致", _shallow)

    # ⑥ 回归：被门禁拦下（未执行）的步骤仍记「跳过」而不是「失败」（取值不可得 ≠ 值错了）
    def _skipped():
        st, detail = evaluate({model.A_TYPE: "真", model.A_VALUE: "步骤.S2.数据"}, state)
        return st == model.ST_SKIP, "断言「真 步骤.S2.数据」→ %s（%s）" % (st, detail)
    case("回归·未执行步骤记跳过（不是失败）", "跳过", _skipped)

    return rows
