# -*- coding: utf-8 -*-
"""离线假动作（TICKET-146 · D4 写链验收口径）。

**为什么要有一组"假动作"**：写链开不开放由**账号对该模块的写权限**决定（TICKET-152），
但契约引擎**自己**的写动作只用离线假动作（真实写走 daniel CLI 的写命令），而门禁的
`dry-run → 确认 → 执行 → 回读校验` 机制必须被真实验证 —— 于是写类动作只在**本地沙箱目录**里
落一个文件，完全不碰任何 Daniel 写路由。

三条硬约束（都在这里落地，不靠契约自觉）：
  ① 只有"声明为写的步骤"才允许调用写类假动作；
  ② 写类假动作的落点**必须在本次运行的沙箱目录内**（越界即拒绝，退出码 2）；
  ③ 每次写动作都记进台账（`写动作台账`），供"无写发生"这类断言当证据用。

TICKET-153 追加一个**读类**动作 `取子表`：真实只读命令的产出往往是对象
（例：`brands list` → `{count, brands:[…]}`），而交付件只能由"产出是条目列表"的步骤出件。
`取子表` 把某个前置步骤产出里的数组**原样**搬出来当本步骤的条目 —— 不联网、不写任何东西。
它**不改变任何既有动作的行为**（老契约一个字不用改）。
"""
import os
import time

from ..exits import EXIT_USAGE
from ..runtime import CliError
from . import model

A_WRITE_FILE = "写文件"
A_READ_FILE = "回读文件"
A_MAKE_ROWS = "生成多条"
A_TAKE_ROWS = "取子表"
#: TICKET-175：读**离线夹具**（`.json`／`.jsonl`）。出件模板要有可复算的固定样本，
#: 于是给一个只读动作：路径相对**契约目录**解析，越出契约目录即拒绝（夹具不许指向任意文件）。
A_LOAD_ROWS = "读夹具"
#: TICKET-175：把多个步骤的子表**按顺序拼成一张池**（品牌池＝品牌名任务＋其 SKU 词任务，
#: Skill §15.5.6 规则3），并可按来源步骤盖一列标记（如「任务模式」）。
A_MERGE_ROWS = "合并子表"

#: 假动作注册表：契约步骤的 `操作` 只能取这里的名字（与 schema.py 对命令的约束同理）
FIXTURE_ACTIONS = {
    A_WRITE_FILE: {"写": True, "必需": ("路径", "内容"), "说明": "把固定内容写进沙箱内的一个文件"},
    A_READ_FILE: {"写": False, "必需": ("路径",), "说明": "读回沙箱内一个文件的内容与行数"},
    A_MAKE_ROWS: {"写": False, "必需": ("数量",), "说明": "离线生成 N 条样本条目（用来演练样本上限）"},
    # TICKET-153：真实只读命令的产出常常是对象（例：`brands list` → `{count, brands:[…]}`），
    # 而交付件只能由"产出是条目列表"的步骤出件。本动作把**真实产出里的子表**原样取出来当条目
    # —— 不联网、不写任何东西、不改一个字段，只是把取值位置显式写进契约。
    A_TAKE_ROWS: {"写": False, "必需": ("来源步骤", "键"),
                  "说明": "从另一个步骤的产出里取出一张子表（如 brands）当本步骤的条目；"
                          "只读取本步骤链的产出，不联网、不写任何东西"},
    # TICKET-175：离线夹具（固定样本，用来把"出件 → 自检 → 落盘"整条链跑成可复算的回归）
    A_LOAD_ROWS: {"写": False, "必需": ("路径",),
                  "说明": "读一份离线夹具（相对契约目录解析，越界即拒绝）当本步骤的条目；"
                          "只读、不联网、不做任何写"},
    A_MERGE_ROWS: {"写": False, "必需": ("来源步骤", "键"),
                   "说明": "把多个步骤的同名子表按声明顺序拼成一张池（例：品牌名任务 ＋ 其 SKU 词任务"
                           "＝品牌池），可用 `加列` 按来源步骤盖一列标记；不联网、不写任何东西"},
}


def action_names():
    return tuple(FIXTURE_ACTIONS)


def is_write_action(name):
    return bool((FIXTURE_ACTIONS.get(name) or {}).get("写"))


def _fail(msg, hint=None):
    return {"状态": model.ST_FAIL, "明细": msg, "条目数": 0}


def _inside(path, sandbox):
    try:
        p = os.path.realpath(path)
        s = os.path.realpath(sandbox)
    except OSError:
        return False
    return p == s or p.startswith(s + os.sep)


def perform(step, state):
    """执行一条 `本地假动作` 步骤，返回该步骤的结果字典。"""
    op = step.get(model.S_OPERATION)
    spec = FIXTURE_ACTIONS.get(op)
    sid = step.get(model.S_ID)
    if spec is None:
        return _fail("未知的本地假动作：%r（可用：%s）" % (op, "／".join(action_names())))
    for key in spec["必需"]:
        if step.get(key) in (None, ""):
            return _fail("本地假动作「%s」缺参数：%s" % (op, key))

    sandbox = state.沙箱目录
    path = state.expand(step.get("路径")) if step.get("路径") is not None else None

    if op == A_WRITE_FILE:
        if not bool(step.get(model.S_WRITE)):
            return _fail("写类假动作「%s」只能出现在声明为写的步骤里（门禁 只读默认）" % op)
        if not _inside(path, sandbox):
            raise CliError("离线假动作的落点越出本次沙箱：%s" % path, code=EXIT_USAGE,
                           hint="写类假动作只允许写在沙箱目录 %s 内" % sandbox)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        content = str(state.expand(step.get("内容")))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        state.写动作台账.append({"步骤": sid, "操作": op, "路径": path,
                             "字节": len(content.encode("utf-8")),
                             "时刻": time.strftime("%Y-%m-%d %H:%M:%S")})
        return {"状态": model.ST_PASS, "操作": op, "路径": path, "存在": True,
                "内容": content, "条目数": 1,
                "明细": "已写入沙箱内文件（不涉及任何 Daniel 写路由）"}

    if op == A_READ_FILE:
        exists = os.path.isfile(path)
        content = ""
        if exists:
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
        rows = [ln for ln in content.splitlines() if ln.strip()]
        return {"状态": model.ST_PASS, "操作": op, "路径": path, "存在": exists,
                "内容": content, "条目数": len(rows),
                "数据": [{"序号": i + 1, "行": ln} for i, ln in enumerate(rows)],
                "明细": "文件存在，共 %d 行" % len(rows) if exists else "文件不存在（未写入）"}

    if op == A_MAKE_ROWS:
        try:
            n = int(state.expand(step.get("数量")))
        except (TypeError, ValueError):
            return _fail("本地假动作「%s」的 `数量` 必须是整数（可用 `${输入.某输入}` 引用输入）" % op)
        if n < 0:
            return _fail("本地假动作「%s」的 `数量` 不能为负" % op)
        rows = [{"序号": i + 1, "条目": "样本条目-%03d" % (i + 1), "来源": sid} for i in range(n)]
        return {"状态": model.ST_PASS, "操作": op, "条目数": len(rows), "数据": rows,
                "明细": "离线生成 %d 条样本条目" % len(rows)}

    if op == A_TAKE_ROWS:
        src = str(state.expand(step.get("来源步骤")))
        key = str(state.expand(step.get("键")))
        prev = state.步骤.get(src)
        if not prev:
            return _fail("「%s」的来源步骤 %s 还没有产出（步骤顺序反了？）" % (op, src))
        if prev.get("状态") != model.ST_PASS:
            return _fail("「%s」的来源步骤 %s 没有成功产出（状态：%s）"
                         % (op, src, prev.get("状态")))
        data = prev.get("数据")
        if not isinstance(data, dict):
            return _fail("「%s」要从 %s 的产出里取子表，但它的产出不是对象（%s）"
                         % (op, src, type(data).__name__))
        rows = data.get(key)
        if not isinstance(rows, list):
            return _fail("「%s」在 %s 的产出里找不到数组 `%s`（现有键：%s）"
                         % (op, src, key, "／".join(sorted(str(k) for k in data)) or "无"))
        return {"状态": model.ST_PASS, "操作": op, "来源步骤": src, "键": key,
                "条目数": len(rows), "数据": rows,
                "明细": "从 %s 的产出里取出「%s」，共 %d 条（原样搬运，未改一个字段）"
                        % (src, key, len(rows))}

    if op == A_LOAD_ROWS:
        return _load_fixture(step, state)

    if op == A_MERGE_ROWS:
        return _merge_rows(step, state)

    return _fail("本地假动作「%s」没有实现" % op)


def _merge_rows(step, state):
    """把多个步骤的子表按声明顺序拼成一张池；可选 `加列` 按来源步骤盖值。

    `加列` 写法：`{"任务模式": ["品牌名任务", "品牌名任务", "SKU 词任务", "SKU 词任务"]}`
    —— 数组与 `来源步骤` 一一对应（个数不等即拒绝，不猜）。
    """
    refs = step.get("来源步骤")
    if isinstance(refs, str):
        refs = [refs]
    if not isinstance(refs, list) or not refs:
        return _fail("「%s」的 `来源步骤` 必须是非空数组（按声明顺序拼接）" % A_MERGE_ROWS)
    key = str(state.expand(step.get("键")))
    extra = step.get("加列") or {}
    if not isinstance(extra, dict):
        return _fail("「%s」的 `加列` 必须是对象（列名 → 与来源步骤一一对应的取值数组）" % A_MERGE_ROWS)
    for col, values in extra.items():
        if not isinstance(values, list) or len(values) != len(refs):
            return _fail("「%s」的 `加列.%s` 必须是与 `来源步骤` 等长的数组（%d 个来源）"
                         % (A_MERGE_ROWS, col, len(refs)))
    rows, parts = [], []
    for i, sid in enumerate(refs):
        sid = str(state.expand(sid))
        prev = state.步骤.get(sid)
        if not prev:
            return _fail("「%s」的来源步骤 %s 还没有产出（步骤顺序反了？）" % (A_MERGE_ROWS, sid))
        if prev.get("状态") != model.ST_PASS:
            return _fail("「%s」的来源步骤 %s 没有成功产出（状态：%s）"
                         % (A_MERGE_ROWS, sid, prev.get("状态")))
        data = prev.get("数据")
        if not isinstance(data, dict):
            return _fail("「%s」要从 %s 取子表，但它的产出不是对象（%s）"
                         % (A_MERGE_ROWS, sid, type(data).__name__))
        sub = data.get(key)
        if not isinstance(sub, list):
            return _fail("「%s」在 %s 的产出里找不到数组 `%s`（现有键：%s）"
                         % (A_MERGE_ROWS, sid, key, "／".join(sorted(str(k) for k in data)) or "无"))
        for r in sub:
            row = dict(r) if isinstance(r, dict) else {"值": r}
            for col, values in extra.items():
                row[col] = state.expand(values[i])
            rows.append(row)
        parts.append("%s=%d" % (sid, len(sub)))
    return {"状态": model.ST_PASS, "操作": A_MERGE_ROWS, "来源步骤": refs, "键": key,
            "条目数": len(rows), "数据": rows,
            "明细": "按顺序拼接 %s，共 %d 条（原样搬运，只按来源盖了 %s）"
                    % ("／".join(parts), len(rows), "／".join(extra) or "（无）")}


def _load_fixture(step, state):
    """读一份离线夹具：路径相对**契约目录**解析；越出契约目录即拒绝（退出码 2）。

    支持两种写法：
      · `.jsonl`：一行一条记录（推荐 —— 契约目录里 **`.json` 一律被当成契约**，
        夹具用 `.jsonl` 就不会被 `playbook list` 误当成契约）；
      · `.json`：顶层是数组，或是带 `键` 指定子表的对象。
    """
    import json

    from ..exits import EXIT_USAGE
    from ..runtime import CliError
    from . import loader

    raw = str(state.expand(step.get("路径")) or "")
    root = os.path.realpath(loader.contracts_dir())
    path = os.path.realpath(raw if os.path.isabs(raw) else os.path.join(root, raw))
    if path != root and not path.startswith(root + os.sep):
        raise CliError("夹具越出契约目录：%s" % raw, code=EXIT_USAGE,
                       hint="夹具只允许放在契约目录 %s 内（相对路径即相对该目录）" % root)
    if not os.path.isfile(path):
        return _fail("夹具不存在：%s（相对契约目录 %s）" % (raw, root))
    try:
        if path.endswith(".jsonl"):
            rows = []
            with open(path, encoding="utf-8") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if ln:
                        rows.append(json.loads(ln))
        else:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            key = step.get("键")
            if isinstance(doc, list):
                rows = doc
            elif isinstance(doc, dict) and key:
                rows = doc.get(key)
            else:
                rows = None
    except ValueError as e:
        return _fail("夹具不是合法 JSON：%s（%s）" % (raw, e))
    except OSError as e:
        return _fail("夹具读不出来：%s（%s）" % (raw, e))
    if not isinstance(rows, list):
        return _fail("夹具 %s 里没有条目列表（.jsonl 一行一条；.json 顶层数组或给 `键` 取子表）" % raw)
    if not all(isinstance(r, dict) for r in rows):
        return _fail("夹具 %s 里有不是对象的条目（出件模板只吃对象数组）" % raw)
    return {"状态": model.ST_PASS, "操作": A_LOAD_ROWS, "路径": path, "存在": True,
            "条目数": len(rows), "数据": rows,
            "明细": "读入离线夹具 %s，共 %d 条（只读，不联网、不做任何写）" % (raw, len(rows))}
