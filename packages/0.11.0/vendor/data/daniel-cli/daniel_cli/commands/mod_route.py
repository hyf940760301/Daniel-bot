# -*- coding: utf-8 -*-
"""route 模块：数据通路体检（只读探测；清单来自既有仪器 `daniel_route_probe.py` 的候选表）。

`sweep`（A1 起真实执行已接通）：逐条探测候选通路，**一律用只读 GET**。
候选表里凡标注 POST 的（`inbox.getCreatorContactHistory`）也照样用 GET 探 —— 写类通路对 GET
的回应是 `405 Unsupported GET-request to mutation procedure`，**这本身就证明了"路由存在、只是写语义"**
（口径见 `data/daniel-cli/A3-未实测路由补齐登记.md` §四），因此体检**不需要**执行任何写动作。
"""
import json
import os
import time

from ..exits import EXIT_OK, EXIT_USAGE
from ..runtime import CliError, load_capability, new_client, parse_json_arg
from ._common import live_managed_write

BOARD = "route"

#: 逐条探测之间的间隔（秒）：体检是"打一排轻请求"，不追求快，避免把服务端当压力靶
PROBE_INTERVAL = 0.4

#: 只允许"读语义"的通路被探测：最后一段以这些前缀开头才算只读。
_READ_PREFIXES = ("get", "list", "search", "resolve", "find", "count",
                  "fetch", "read", "query", "detail", "index", "history")

#: 探针样例的默认截断长度（字符）。**截断必须可见**（TICKET-222）：曾经这里只把样本切成 400 字
#: 却不留任何痕迹，而频道详情有 11 个字段、`handle` 恰好排在最后 —— 调用方看到样本里没有 handle
#: 就误判"平台没有这个字段"。所以现在的口径是：**判断字段是否存在只能看 `fields` 列表；
#: `sample` 只用于看数据形态**，且被截断时样本末尾带显式标记 ＋ `sample_truncated=true`。
SAMPLE_LIMIT = 400

#: 截断标记（跟在被截断样本的末尾，一眼就能看出"后面还有"）
TRUNCATED_MARK = "…（样本已截断：完整 %d 字符，此处只留前 %d；要看完整样例加 --full-sample；" \
                 "判断字段是否存在只看 fields 列表，sample 只用于看数据形态）"

#: 结果里随样本一起给出的阅读口径（人读与 JSON 都在）
SAMPLE_HOW_TO_READ = ("判断字段是否存在**只能看 fields 列表**（它来自整包返回的全部字段名）；"
                      "sample 只用于看数据形态，且默认会被截断 —— 样本里没看到某个字段，"
                      "不等于平台没有这个字段。")


def _assert_read_only(route):
    last = str(route).split(".")[-1].lower()
    if not last.startswith(_READ_PREFIXES):
        raise CliError("「%s」不是只读通路，本工序拒绝探测（只做读链）" % route,
                       code=EXIT_USAGE,
                       hint="只读通路的名字以 get/list/search/resolve/find 这类动词开头；"
                            "写类通路的存在性用 `daniel route sweep` 以 GET 判定（405＝存在、写语义）")


def cmd_probe(ctx):
    route = ctx.require("--route")
    _assert_read_only(route)
    inp = parse_json_arg(ctx.get("input"))
    full_sample = bool(ctx.get("full-sample"))
    d = new_client(verbose=ctx.verbose)
    ctx.progress("正在探测通路可用性（只读）")
    t0 = time.time()
    try:
        obj = d.query(route, inp)
        seconds = round(time.time() - t0, 2)
        if isinstance(obj, dict):
            keys = list(obj.keys())            # **完整**字段名（不截断：它才是"有没有这个字段"的依据）
            shape = "dict"
        elif isinstance(obj, list):
            keys = list(obj[0].keys()) if obj and isinstance(obj[0], dict) else []
            shape = "list[%d]" % len(obj)
        else:
            keys, shape = [], type(obj).__name__
        raw = json.dumps(obj, ensure_ascii=False)
        sample_chars = len(raw)
        truncated = (not full_sample) and sample_chars > SAMPLE_LIMIT
        if full_sample:
            sample = raw
        elif truncated:
            sample = raw[:SAMPLE_LIMIT] + TRUNCATED_MARK % (sample_chars, SAMPLE_LIMIT)
        else:
            sample = raw
        ctx.emit(data={"route": route, "method": "GET", "available": True, "seconds": seconds,
                       "shape": shape, "fields": keys, "field_count": len(keys),
                       "sample": sample,
                       "sample_chars": sample_chars,
                       "sample_truncated": truncated,
                       "fieldsNote": SAMPLE_HOW_TO_READ,
                       "sample_limit": SAMPLE_LIMIT,
                       "note": ("样本已截断到前 %d 字符（完整 %d 字符）；要完整样例请加 --full-sample。"
                                % (SAMPLE_LIMIT, sample_chars)) if truncated
                               else ("样本未截断（完整 %d 字符）。" % sample_chars)},
                 route=route)
        return EXIT_OK
    except Exception as e:                                              # noqa: BLE001
        seconds = round(time.time() - t0, 2)
        ctx.warn("通路不可用：%s" % str(e)[:200])
        ctx.emit_raw(ok=True, exit_code=EXIT_OK,
                     data={"route": route, "method": "GET", "available": False,
                           "seconds": seconds, "error": str(e)[:200],
                           "fieldsNote": SAMPLE_HOW_TO_READ}, route=route)
        return EXIT_OK


def cmd_catalog(ctx):
    """离线：列出候选通路（来自既有仪器的候选表，不联网、不探测）。"""
    probe_mod = load_capability("daniel_route_probe")
    rows = []
    for item in getattr(probe_mod, "CANDIDATES", []):
        route, method, inp, note = (list(item) + [None] * 4)[:4]
        last = str(route).split(".")[-1].lower()
        rows.append({"route": route, "method": method, "note": note,
                     "probeSupportedInThisWorkOrder": method == "GET" and last.startswith(_READ_PREFIXES),
                     "defaultInput": inp})
    ctx.emit(data={"count": len(rows),
                   "note": "本清单是候选通路表；只有只读通路可以用 `daniel route probe` 探测。",
                   "routes": rows},
             route="daniel_route_probe.CANDIDATES")
    return EXIT_OK


HANDLERS = {
    "probe": cmd_probe,
    "catalog": cmd_catalog,
}

def _plan_sweep(ctx, client):
    """离线读候选表，算出这次扫描会覆盖多少条通路（并点名其中写语义的那几条）。"""
    probe_mod = load_capability("daniel_route_probe")
    rows = list(getattr(probe_mod, "CANDIDATES", []))
    non_read = []
    for item in rows:
        route, method = (list(item) + [None, None])[:2]
        last = str(route).split(".")[-1].lower()
        if method != "GET" or not last.startswith(_READ_PREFIXES):
            non_read.append(route)
    limit = _limit_of(ctx, len(rows))
    return {
        "targetName": "通路清单", "brand": None, "workspaceId": None,
        "impact": "会逐条用**只读 GET** 探测 %d 条候选通路（共 %d 条，本次取前 %d 条）；"
                  "其中 %d 条是写语义通路 —— 对它们 GET 会拿到 405，"
                  "这**只证明路由存在**，不执行任何写动作"
                  % (limit, len(rows), limit, len(non_read)),
        "changes": {"route.sweep": {"total": len(rows), "probed": limit,
                                    "writeSemanticsRoutes": non_read[:20]}},
        "writesDatabase": False,
    }


def _limit_of(ctx, total):
    raw = ctx.get("limit")
    if raw in (None, ""):
        return total
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise CliError("--limit 必须是整数：%r" % raw, code=EXIT_USAGE)
    if n < 1:
        raise CliError("--limit 至少为 1（本次没有探测任何通路）", code=EXIT_USAGE)
    return min(n, total)


def _probe_one(client, route, inp, method):
    """一条通路的只读探测。**只发 GET**（`method` 只用于标注它"本来的"语义）。"""
    t0 = time.time()
    try:
        obj = client.query(route, inp)
        shape = ("dict" if isinstance(obj, dict)
                 else "list[%d]" % len(obj) if isinstance(obj, list) else type(obj).__name__)
        return {"route": route, "declaredMethod": method, "available": True, "http": 200,
                "seconds": round(time.time() - t0, 2), "shape": shape}
    except Exception as e:                                             # noqa: BLE001
        text = str(e)
        http = 0
        for tok in text.replace("HTTP ", "HTTP").split():
            if tok.startswith("HTTP") and tok[4:7].isdigit():
                http = int(tok[4:7])
        write_semantics = ("Unsupported GET-request to mutation procedure" in text)
        missing = ("No procedure found" in text)
        return {"route": route, "declaredMethod": method, "available": False,
                "http": http or None,
                "kind": ("写语义通路（存在，GET 不接受）" if write_semantics
                         else "路由不存在" if missing else "探测失败"),
                "exists": bool(write_semantics),
                "seconds": round(time.time() - t0, 2), "error": text[:200]}


def _run_sweep(ctx, client, plan):
    """真跑：逐条 GET 探测候选通路 → 逐条登记 → 回读核对条数与候选表。

    请求数＝本次探测条数（`--limit`，默认全部）；**一条通路一次请求，不做重试、不做并发**
    （并发与退避由统一队列那一层负责，命令自身不制造额外流量）。
    """
    probe_mod = load_capability("daniel_route_probe")
    rows = list(getattr(probe_mod, "CANDIDATES", []))
    limit = _limit_of(ctx, len(rows))
    picked = [(list(item) + [None, None, None, None])[:4] for item in rows[:limit]]
    results = []
    for route, method, inp, note in picked:
        ctx.progress("探测 %s（GET，声明为 %s）" % (route, method))
        r = _probe_one(client, route, inp or {}, method)
        r["note"] = note
        results.append(r)
        if len(results) < len(picked):
            time.sleep(PROBE_INTERVAL)

    # 回读核对：候选表条数与探测条数必须与本次计划一致（不一致说明在跑的过程中清单变了）
    catalog = list(getattr(probe_mod, "CANDIDATES", []))
    ok_http = [r for r in results if r.get("http") == 200]
    write_sem = [r for r in results if r.get("exists")]
    not_found = [r for r in results if r.get("http") == 404]
    others = [r for r in results
              if r.get("http") not in (200, 404) and not r.get("exists")]
    verified = (len(catalog) == len(rows) and len(results) == limit)
    reason = "" if verified else ("候选表在本次扫描前后不一致（%d → %d）或探测条数不符（预期 %d，实得 %d）"
                                 % (len(rows), len(catalog), limit, len(results)))
    dump = ctx.get("out")
    if dump:
        path = _write_dump(dump, results)
    else:
        path = None
    return {
        "mutation": {"route": "route.sweep（只读 GET 逐条探测）",
                     "request": {"probed": len(results), "routes": [r["route"] for r in results]}},
        "readback": {"verified": verified, "reason": reason,
                     "detail": {"candidatesInCatalog": len(catalog),
                                "probed": len(results),
                                "available": len(ok_http),
                                "writeSemantics（存在但 GET 不被接受）": len(write_sem),
                                "notFound": len(not_found),
                                "other": len(others)},
                     "how": "逐条 GET 探测后，回读候选表（`daniel route catalog` 的同一份表）"
                            "核对条数：候选表 %d 条、本次探测 %d 条" % (len(catalog), len(results))},
        "rolledBack": None,
        "rollbackNote": "只读探测，没有任何写动作，无需回滚",
        "detail": {"通路清单": results, "落盘": path},
    }


def _write_dump(path, results):
    import io
    p = os.path.abspath(os.path.expanduser(str(path)))
    with io.open(p, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)
    return p


WRITE_HANDLERS = {
    "sweep": live_managed_write(BOARD, "sweep", "全量扫描通路可用性（只读 GET 探测）",
                                plan_fn=_plan_sweep, run_fn=_run_sweep,
                                danger="逐条发包探测（只读 GET；写类通路以 405 判定存在性，不执行写）"),
}
