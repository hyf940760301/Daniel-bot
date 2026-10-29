#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""read_parity_check.py —— 读链回归：**仪器路径**与 **CLI 路径**的结果集合是否一致（TICKET-150）。

**要解决的问题**：CLI 的 `--json` 与既有仪器原本各说各话 —— 仪器出中文表格／被截断的 JSON，
CLI 只能从文本里"抢救"结构化结果，于是两条路给出的集合可能既不同名也不同条数，
而调用方（模型／别的宿主）无从判断该信哪一条。

**判据（集合关系用键比对，不比字符串）**：
  ① 同一查询在两条路径下 **条目数相同**；
  ② 逐条 **键集合相同**、且 **键顺序相同**（`json.loads` 保序）；
  ③ 分页游标一致（`total／returned／truncated／paging.nextCursor／nextPage`）；
  ④ **口径回显一致**（`filter.echo` 与实际用的过滤条件、服务端自报的被排除条数）；
  ⑤ **两个相关度口径都断言**：默认只给与本品相关的（`confirmed_likely`）与显式全量（`all`）——
     防止"默认视图悄悄把不相关的挡掉、调用方却以为拿到的是全量"。

用法
  python3 data/daniel-cli/read_parity_check.py                 # 在线只读（默认 Euhomy 夹具）
  python3 data/daniel-cli/read_parity_check.py --brand <编号>
  python3 data/daniel-cli/read_parity_check.py --job <任务编号>   # 默认取该品牌最近一条
  python3 data/daniel-cli/read_parity_check.py --self-test     # 离线：比对判据自检（含反例）
  python3 data/daniel-cli/read_parity_check.py --json          # 机器可读结论

退出码：0＝全部一致（**跳过**的项会显式列出，不算通过）；1＝有一致性缺口（当缺陷处理）；2＝取数失败（不得当通过）。
纪律：只用标准库、只跑只读子命令（`--json`）、不触发任何采集／写操作、不打印凭据。
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                  # data/daniel-cli
CLI = os.path.join(HERE, "bin", "daniel")

#: 默认夹具（Euhomy 的真实已完成任务；只有 job 用这个默认值时才断言 96／114 这两个具体数字）
DEFAULT_BRAND = "4560003"
DEFAULT_JOB = "d8e9b6fb-fd51-4b52-be82-2ae8a423b789"
EXPECT_DEFAULT_TOTAL = 96          # 默认口径 confirmed_likely
EXPECT_ALL_TOTAL = 114             # 显式全量口径 all


def tools_dir():
    """能力目录（`.kol-tools`）：环境变量优先，否则从本文件向上找。"""
    env = os.environ.get("DANIEL_CLI_TOOLS")
    cands = [env] if env else []
    up = ROOT
    for _ in range(6):
        cands.append(os.path.join(up, ".kol-tools"))
        nxt = os.path.dirname(up)
        if nxt == up:
            break
        up = nxt
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "daniel_client.py")):
            return os.path.abspath(c)
    raise SystemExit("找不到能力目录（.kol-tools，需含 daniel_client.py）：可用 DANIEL_CLI_TOOLS 指定")


def run(argv):
    p = subprocess.run([sys.executable] + argv, capture_output=True, text=True, timeout=1800)
    return p.returncode, p.stdout or "", p.stderr or ""


def parse_doc(text):
    """从一条命令的 stdout 里取出那**一个** JSON 文档（取不出来 → None）。"""
    try:
        return json.loads(text)
    except ValueError:
        return None


def cli_supports(module, sub, option):
    """该子命令已经注册了这个参数吗？（用于"待注册"的显式跳过，而不是静默放过）"""
    rc, out, err = run([CLI, module, sub, "--help"])
    return rc == 0 and option in (out + err)


# ─────────────────────────── 判据（离线可自检）───────────────────────────
def row_keys(rows):
    """→ [键顺序列表]（只对字典行有意义；非字典行记为 None）。"""
    return [list(r) if isinstance(r, dict) else None for r in (rows or [])]


def compare_rows(a, b):
    """键比对：条数 ＋ 逐条键集合与顺序。→ (是否一致, 说明)。不比字符串值。"""
    ka, kb = row_keys(a), row_keys(b)
    if len(ka) != len(kb):
        return False, "条数不同：仪器 %d 条 ／ CLI %d 条" % (len(ka), len(kb))
    for i, (x, y) in enumerate(zip(ka, kb), 1):
        if x != y:
            return False, "第 %d 条键不一致：仪器 %s ／ CLI %s" % (i, x, y)
    return True, "同名同序同条数（%d 条）" % len(ka)


def compare_paging(pa, pb):
    """分页游标比对：只比"事实字段"，不评价内容。→ (是否一致, 说明)。"""
    fields = ("total", "returned", "truncated")
    bad = [f for f in fields if (pa or {}).get(f) != (pb or {}).get(f)]
    na = ((pa or {}).get("paging") or {}).get("nextCursor")
    nb = ((pb or {}).get("paging") or {}).get("nextCursor")
    npa = ((pa or {}).get("paging") or {}).get("nextPage")
    npb = ((pb or {}).get("paging") or {}).get("nextPage")
    if na != nb:
        bad.append("paging.nextCursor")
    if npa != npb:
        bad.append("paging.nextPage")
    if bad:
        return False, "分页字段不一致：%s（仪器 total=%s returned=%s ／ CLI total=%s returned=%s）" % (
            "、".join(bad), (pa or {}).get("total"), (pa or {}).get("returned"),
            (pb or {}).get("total"), (pb or {}).get("returned"))
    return True, "总数／条数／截断标注／游标一致（total=%s，nextCursor=%s，nextPage=%s）" % (
        (pa or {}).get("total"), na, npa)


def task_excluded(entry):
    """取"服务端自报的**任务级**排除条数"（字段语义见契约文档；本函数只搬运不推导）。"""
    return ((entry or {}).get("filter") or {}).get("taskLevelExcluded", {}).get("count")


def compare_filter(pa, pb):
    """口径回显比对：两条路必须报同一个口径（默认只给相关的／显式全量）。→ (是否一致, 说明)。"""
    fa = (pa or {}).get("filter") or {}
    fb = (pb or {}).get("filter") or {}
    if fa.get("echo") != fb.get("echo"):
        return False, "过滤条件回显不一致：仪器 %s ／ CLI %s" % (fa.get("echo"), fb.get("echo"))
    if task_excluded(pa) != task_excluded(pb):
        return False, "任务级排除条数不一致：仪器 %s ／ CLI %s" % (task_excluded(pa), task_excluded(pb))
    return True, "口径回显一致：%s ｜ 服务端自报任务级排除 %s 条（与本次筛选项无关）" % (
        fa.get("echo"), task_excluded(pa))


def pick(rows, path):
    """按点分路径取值（例如 `result` / `data` / `result.results`）；`.` 或空串＝整体。"""
    if path in ("", "."):
        return rows
    cur = rows
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


# ─────────────────────────── 回归用例 ───────────────────────────
def cases(brand, job):
    """每条 = 一个字典：名字／仪器 argv／CLI argv／取列表的路径对／取分页的路径对／CLI 需要的参数。"""
    tools = tools_dir()
    t = os.path.join(tools, "daniel_mentions.py")
    ti = os.path.join(tools, "daniel_intel.py")
    return [
        {"名字": "intel actions（待办动作全量）",
         "仪器": [ti, "--brand", str(brand), "actions", "--json"],
         "CLI": [CLI, "intel", "actions", "--brand", str(brand), "--json"],
         "列路径": ("result", "data"), "分页路径": ("", "read")},
        {"名字": "mentions jobs（任务列表）",
         "仪器": [t, "--jobs", "--brand", str(brand), "--limit", "5", "--json"],
         "CLI": [CLI, "mentions", "jobs", "--brand", str(brand), "--limit", "5", "--json"],
         "列路径": ("result", "data"), "分页路径": ("", "read")},
        {"名字": "mentions results（默认口径 confirmed_likely）",
         "仪器": [t, "--results", job, "--brand", str(brand), "--page", "1",
                  "--page-size", "20", "--json"],
         "CLI": [CLI, "mentions", "results", "--brand", str(brand), "--job", job,
                 "--page", "1", "--page-size", "20", "--json"],
         "列路径": ("result.results", "data.results"), "分页路径": ("", "read")},
        {"名字": "mentions results（显式全量口径 all）",
         "仪器": [t, "--results", job, "--brand", str(brand), "--page", "1",
                  "--page-size", "20", "--relevance", "all", "--json"],
         "CLI": [CLI, "mentions", "results", "--brand", str(brand), "--job", job,
                 "--page", "1", "--page-size", "20", "--relevance-filter", "all", "--json"],
         "列路径": ("result.results", "data.results"), "分页路径": ("", "read"),
         "需要参数": ("mentions", "results", "--relevance-filter")},
    ]


#: 提及结果列表的单页上限（仪器 `PAGE_SIZE_MAX`；实测每页最少 10、最多 200）
SINGLE_PAGE_MAX = 200
#: 翻页保护：最多翻这么多页就停（防止在服务端返回异常 totalPages 时无限翻）
MAX_PAGES = 30

#: 页内条目"唯一编号"的候选字段（按界面实际字段名取，取不到就不判 —— 不发明字段）
ROW_ID_FIELDS = ("resultId", "id", "jobId", "videoId", "channelId", "reportId", "actionId")


def row_id_field(rows):
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        for k in ROW_ID_FIELDS:
            if k in rows[0]:
                return k
    return None


def unique_count(rows, field):
    """不同编号数；取不到编号字段就返回 None（**不猜**）。"""
    if field is None:
        return None
    return len({json.dumps(r.get(field), ensure_ascii=False, sort_keys=True)
                for r in rows if isinstance(r, dict)})


def fetch_all_rows(tool, job, brand, extra=None, page_size=SINGLE_PAGE_MAX):
    """把一份列表**读全**：取数收口 ＋ 去重断言（TICKET-150 · 总监裁决）。

    规则（缺陷类 CLS-82 的对策）：
      ① **取数收口**：先按单页上限取一页；服务端说 `totalPages == 1` ⇒ 这就是全量，**不翻页**；
      ② 确认要翻页时逐页取，最后断言「累计条数 == 不同编号数」；
      ③ 断言不过 ⇒ `trusted=False`，调用方**不许**把这份数据当结果交出去。

    → `{"rows": [...], "pages": n, "rowsUnique": m, "idField": f, "trusted": bool, "note": str}`
    """
    argv = [tool, "--results", job, "--brand", str(brand), "--page", "1",
            "--page-size", str(page_size), "--json"] + list(extra or [])
    rc, out, err = run(argv)
    doc = parse_doc(out)
    if rc != 0 or doc is None:
        return {"rows": [], "pages": 0, "rowsUnique": None, "idField": None, "trusted": False,
                "note": "取数失败：%s（退出码 %s）" % ((err or out).strip()[:120], rc)}
    rows = pick(doc, "result.results") or []
    pages_total = (doc.get("paging") or {}).get("totalPages") or 1
    field = row_id_field(rows)
    collected, pages = list(rows), 1
    if pages_total > 1:                        # 只有确实超过单页上限才翻页
        for p in range(2, min(pages_total, MAX_PAGES) + 1):
            rc, out, err = run([tool, "--results", job, "--brand", str(brand), "--page", str(p),
                                "--page-size", str(page_size), "--json"] + list(extra or []))
            doc = parse_doc(out)
            if rc != 0 or doc is None:
                return {"rows": collected, "pages": p - 1, "rowsUnique": unique_count(collected, field),
                        "idField": field, "trusted": False,
                        "note": "第 %s 页取数失败，未取全：%s" % (p, (err or out).strip()[:120])}
            collected += pick(doc, "result.results") or []
            pages = p
    uniq = unique_count(collected, field)
    if uniq is None:
        note = "取不到条目编号字段，**无法**做去重断言（%d 条，%d 页）—— 不许当成已验证" % (
            len(collected), pages)
        return {"rows": collected, "pages": pages, "rowsUnique": None, "idField": None,
                "trusted": False, "note": note}
    ok = uniq == len(collected)
    how = ("取数收口：单页取全（%d 条，1 页）" % len(collected) if pages == 1
           else "翻页取全（%d 页，单页上限 %d）" % (pages, page_size))
    note = "%s；去重断言：%d 条 == %d 个不同编号（%s）" % (how, len(collected), uniq, field)
    if not ok:
        note += " ⇒ **不通过：分页存在重复或遗漏，这批数据不可信（缺陷类 CLS-82）**"
    return {"rows": collected, "pages": pages, "rowsUnique": uniq, "idField": field,
            "trusted": bool(ok), "note": note}


def schema_enum_parity():
    """schema 里声明的 `--relevance-filter` 取值域 == 仪器实际的 `RELEVANCE_FILTER`。

    为什么要这条：同一个枚举有两处副本（schema 给用户看、仪器真正校验）。一边加取值、另一边没加，
    用户会拿到退出码 2 却不知道该信谁 —— 所以**锁死**：不一致即红。
    """
    import importlib.util
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    path = os.path.join(tools_dir(), "daniel_mentions.py")
    spec = importlib.util.spec_from_file_location("_rp_instr", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    want = list(getattr(mod, "RELEVANCE_FILTER", []))
    try:
        from daniel_cli import schema as sch
    except Exception as e:                                        # noqa: BLE001（并发改动可能暂不可导入）
        return {"ok": False, "instrument": want, "schema": None,
                "note": "schema 不可导入（可能有并发改动）：%s" % e}
    got = None
    for m in sch.SCHEMA["modules"]:
        if m["key"] != "mentions":
            continue
        for c in m["commands"]:
            if c["name"] != "results":
                continue
            for opt in c["options"]:
                if opt["name"] == "--relevance-filter":
                    got = list(opt.get("choices") or [])
    if got is None:
        return {"ok": False, "instrument": want, "schema": None,
                "note": "schema 里还没有声明 --relevance-filter"}
    ok = got == want
    return {"ok": ok, "instrument": want, "schema": got,
            "note": "一致：%s" % want if ok else "**不一致**：schema %s ／ 仪器 %s" % (got, want)}


def first_job(brand):
    """取该品牌最近一条提及任务编号（仪器路径，只读）。"""
    t = os.path.join(tools_dir(), "daniel_mentions.py")
    rc, out, err = run([t, "--jobs", "--brand", str(brand), "--limit", "1", "--json"])
    rows = pick(parse_doc(out) or {}, "result") or []
    if rc != 0 or not rows:
        raise SystemExit("取不到提及任务编号（退出码 %s）：%s" % (rc, (err or out).strip()[:200]))
    return rows[0].get("jobId")


def filter_views(brand, job, expect=(EXPECT_DEFAULT_TOTAL, EXPECT_ALL_TOTAL)):
    """两个相关度口径都要断言（总监裁决）：默认口径 96 条、显式全量 114 条（默认夹具）。

    判据：① 两个口径的 `total` **必须不同**（默认口径确实在过滤）；
          ② 默认口径 `total` ＋ 服务端自报被排除条数 ＝ 全量口径 `total`（账要算得平）。
    只在用默认夹具任务时核对 96／114 两个具体数字；换任务只核关系，并把实测值如实打出来。
    """
    t = os.path.join(tools_dir(), "daniel_mentions.py")
    rows, gaps, views = [], [], {}
    for label, extra in (("默认（confirmed_likely）", []), ("全量（all）", ["--relevance", "all"])):
        rc, out, err = run([t, "--results", job, "--brand", str(brand), "--page", "1",
                            "--page-size", "20", "--json"] + extra)
        doc = parse_doc(out)
        if rc != 0 or doc is None:
            gaps.append("相关度口径·%s" % label)
            rows.append({"口径": label, "结论": "取数失败", "说明": (err or out).strip()[:160]})
            continue
        views[label] = doc
        rows.append({"口径": label, "结论": "已取数", "总数（服务端字段 total）": doc.get("total"),
                     "本页条数": doc.get("returned"),
                     "回显过滤条件（服务端口径）": (doc.get("filter") or {}).get("echo"),
                     "服务端自报·任务级排除": task_excluded(doc),
                     "总页数": (doc.get("paging") or {}).get("totalPages")})
    d, al = views.get("默认（confirmed_likely）"), views.get("全量（all）")
    if d and al:
        same = d.get("total") == al.get("total")
        if same:
            gaps.append("相关度口径未生效")
        rows.append({"口径": "口径差异断言（硬判据）", "结论": "不通过" if same else "通过",
                     "说明": "默认 %s 条 ／ 全量 %s 条（两个**服务端字段**）—— "
                             "默认口径确实在过滤，调用方不能把默认视图当全量"
                             % (d.get("total"), al.get("total"))})
        derived = (al.get("total") or 0) - (d.get("total") or 0)
        task = task_excluded(d)
        rows.append({"口径": "本次请求隐藏条数（**算术推导**，不是服务端字段）",
                     "结论": "观察（不作通过条件）",
                     "说明": "推导式：全量口径 total(%s) − 本次口径 total(%s) ＝ %s 条；"
                             "服务端自报的**任务级**排除是 %s 条 —— 两者在本夹具上相等，"
                             "但语义不同（前者随筛选项变，后者与筛选项无关），不得互相替代"
                             % (al.get("total"), d.get("total"), derived, task)})
        if job == DEFAULT_JOB:
            want_d, want_a = expect
            ok_exact = d.get("total") == want_d and al.get("total") == want_a
            rows.append({"口径": "夹具数字断言", "结论": "通过" if ok_exact else "不通过",
                         "说明": "默认应 %s、全量应 %s；实测 %s／%s"
                                 % (want_d, want_a, d.get("total"), al.get("total"))})
            if not ok_exact:
                gaps.append("夹具数字不符")
    return rows, gaps


def main(argv=None):
    ap = argparse.ArgumentParser(description="读链回归：仪器路径与 CLI 路径的结果集合比对（只读）")
    ap.add_argument("--brand", default=DEFAULT_BRAND,
                    help="品牌编号（默认 %s＝Euhomy 夹具）" % DEFAULT_BRAND)
    ap.add_argument("--job", help="提及任务编号（默认自动取该品牌最近一条）")
    ap.add_argument("--json", action="store_true", help="输出机器可读结论")
    ap.add_argument("--paging-job", metavar="任务编号",
                    help="另一个结果数**超过单页上限 200** 的任务编号：用来跑「必须翻页」那条"
                         "分支（去重断言在真实数据上的表现）。不给则显式跳过。")
    ap.add_argument("--self-test", action="store_true", help="离线自检（比对判据，不联网）")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()

    job = a.job or first_job(a.brand)
    results, gaps, skipped, failed_fetch = [], [], [], False
    for case in cases(a.brand, job):
        need = case.get("需要参数")
        if need and not cli_supports(*need):
            skipped.append("%s（CLI 的 %s 尚未注册）" % (case["名字"], need[2]))
            results.append({"案例": case["名字"], "结论": "跳过",
                            "说明": "CLI 的 %s 还没注册（已登记在回报里待总监安排）；"
                                    "仪器路径的同一口径在下面「相关度口径」一节断言" % need[2]})
            continue
        rc1, out1, err1 = run(case["仪器"])
        rc2, out2, err2 = run(case["CLI"])
        d1, d2 = parse_doc(out1), parse_doc(out2)
        if rc1 != 0 or rc2 != 0 or d1 is None or d2 is None:
            failed_fetch = True
            results.append({"案例": case["名字"], "结论": "取数失败",
                            "仪器": "退出码 %s ｜ %s" % (rc1, (err1 or "").strip().splitlines()[-1:]),
                            "CLI": "退出码 %s ｜ %s" % (rc2, (err2 or "").strip().splitlines()[-1:])})
            continue
        rowsi, rowsc = pick(d1, case["列路径"][0]) or [], pick(d2, case["列路径"][1]) or []
        pagei, pagec = pick(d1, case["分页路径"][0]) or {}, pick(d2, case["分页路径"][1]) or {}
        ok_rows, why_rows = compare_rows(rowsi, rowsc)
        ok_page, why_page = compare_paging(pagei, pagec)
        ok_filter, why_filter = compare_filter(pagei, pagec)
        ok = ok_rows and ok_page and ok_filter
        if not ok:
            gaps.append(case["名字"])
        results.append({"案例": case["名字"], "结论": "一致" if ok else "不一致",
                        "集合": why_rows, "分页": why_page, "口径": why_filter,
                        "仪器条数": len(rowsi), "CLI条数": len(rowsc),
                        "仪器 total": pagei.get("total"), "CLI total": pagec.get("total"),
                        "仪器截断": pagei.get("truncated"), "CLI截断": pagec.get("truncated")})

    views, vgaps = filter_views(a.brand, job)
    gaps += vgaps

    # 取数收口 ＋ 去重断言（全量口径：114 条 ≤ 单页上限 200 ⇒ 必须单页取全、且条数 == 不同编号数）
    tool = os.path.join(tools_dir(), "daniel_mentions.py")
    fetch = fetch_all_rows(tool, job, a.brand, extra=["--relevance", "all"])
    if not (fetch["trusted"] and fetch["pages"] == 1 and fetch["rowsUnique"] == len(fetch["rows"])):
        gaps.append("取数收口/去重断言")
    # 必须翻页的那条分支（可选）：总数 > 单页上限时，逐页取 + 去重断言
    if a.paging_job:
        paging = fetch_all_rows(tool, a.paging_job, a.brand, extra=["--relevance", "all"])
        if paging["pages"] < 2:
            paging_note = "该任务结果数未超过单页上限，没能跑到翻页分支：%s" % paging["note"]
            paging_ok = None
        else:
            paging_note = paging["note"]
            paging_ok = paging["trusted"]
            if not paging_ok:
                # 真数据上抓到了"分页重复或遗漏"（缺陷类 CLS-82）：这条**不许当通过**，
                # 数据按不可信处理（调用方不得直接使用）。
                gaps.append("翻页去重断言（CLS-82：分页重复或遗漏，数据不可信）")
    else:
        paging, paging_ok = None, None
        paging_note = "未给 --paging-job ⇒ 显式跳过（**不算通过**）：默认夹具只有 114 条，跑不到翻页分支"
    # 枚举一致性：schema 的 choices 必须与仪器 RELEVANCE_FILTER 逐字一致
    enum = schema_enum_parity()
    if not enum["ok"]:
        gaps.append("相关度取值域与 schema 不一致")

    if a.json:
        print(json.dumps({"brand": a.brand, "job": job, "案例": results, "相关度口径": views,
                          "取数收口与去重": fetch, "翻页分支": paging, "翻页分支结论": paging_note,
                          "取值域一致性": enum,
                          "取数失败": failed_fetch, "不一致": gaps, "跳过": skipped},
                         ensure_ascii=False, indent=1))
    else:
        print("读链回归：仪器路径 ↔ CLI 路径（品牌 %s，任务 %s）" % (a.brand, job))
        for r in results:
            print("\n【%s】%s" % (r["案例"], r["结论"]))
            for k, v in r.items():
                if k not in ("案例", "结论"):
                    print("   %s：%s" % (k, v))
        print("\n—— 相关度口径（TICKET-150：两个口径都要断言）——")
        for r in views:
            print("\n【%s】%s" % (r["口径"], r["结论"]))
            for k, v in r.items():
                if k not in ("口径", "结论"):
                    print("   %s：%s" % (k, v))
        print("\n—— 取数收口 ＋ 去重断言（总数 ≤ 单页上限 %d 时必须一次取全）——" % SINGLE_PAGE_MAX)
        print("   %s" % ("通过" if fetch["trusted"] and fetch["pages"] == 1 else "不通过"))
        print("   %s" % fetch["note"])
        print("\n—— 翻页分支（总数 > 单页上限时逐页取 ＋ 去重断言）——")
        print("   %s" % ("通过" if paging_ok else ("不通过" if paging_ok is False else "跳过")))
        print("   %s" % paging_note)
        print("\n—— 取值域一致性（schema 声明 vs 仪器常量）——")
        print("   %s ｜ %s" % ("通过" if enum["ok"] else "不通过", enum["note"]))
        if skipped:
            print("\n跳过（**显式列出**，不算通过）：")
            for sk in skipped:
                print("   · %s" % sk)
        print("\n结论：%s" % ("全部一致" if not gaps and not failed_fetch
                            else ("有一致性缺口：%s" % "、".join(gaps) if gaps else "取数失败，不得当通过")))
    if failed_fetch:
        return 2
    return 1 if gaps else 0


# ─────────────────────────── 离线自检 ───────────────────────────
def self_test():
    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    a = [{"id": 1, "title": "x"}, {"id": 2, "title": "y"}]
    b = [{"id": 9, "title": "z"}, {"id": 8, "title": "w"}]
    ok, why = compare_rows(a, b)
    ck("键比对：同键不同值 → 一致（不比字符串）", ok, why)
    ok2, why2 = compare_rows(a, a[:1])
    ck("反例：条数不同 → 不一致", (not ok2) and "条数不同" in why2, why2)
    ok3, why3 = compare_rows(a, [{"title": "x", "id": 1}, {"title": "y", "id": 2}])
    ck("反例：键序不同 → 不一致", (not ok3) and "键不一致" in why3, why3)
    ok4, _ = compare_rows(a, [{"id": 1, "title": "x", "extra": 1}, {"id": 2, "title": "y"}])
    ck("反例：多一个键 → 不一致", not ok4)

    pa = {"total": 40, "returned": 40, "truncated": False,
          "paging": {"nextCursor": None, "nextPage": None}}
    ck("分页比对：同事实 → 一致", compare_paging(pa, json.loads(json.dumps(pa)))[0])
    pc = json.loads(json.dumps(pa))
    pc["paging"]["nextCursor"] = 5
    ck("反例：游标不同 → 不一致", not compare_paging(pa, pc)[0], compare_paging(pa, pc)[1])
    pd = json.loads(json.dumps(pa))
    pd["truncated"] = True
    ck("反例：截断标注不同 → 不一致", not compare_paging(pa, pd)[0])

    f1 = {"total": 96, "returned": 20, "paging": {},
          "filter": {"echo": {"relevanceFilter": "confirmed_likely"},
                     "taskLevelExcluded": {"count": 18, "serverField": "excludedIrrelevant",
                                           "note": "任务级统计，与本次请求的筛选项无关"}}}
    ck("口径回显：同口径 → 一致", compare_filter(f1, json.loads(json.dumps(f1)))[0])
    f3 = json.loads(json.dumps(f1))
    f3["filter"]["echo"] = {"relevanceFilter": "all"}
    ck("反例：口径回显不同（默认 vs 全量）→ 不一致",
       (not compare_filter(f1, f3)[0]) and "过滤条件回显不一致" in compare_filter(f1, f3)[1])
    f4 = json.loads(json.dumps(f1))
    f4["filter"]["taskLevelExcluded"]["count"] = 0
    ck("反例：任务级排除条数不同 → 不一致", not compare_filter(f1, f4)[0],
       compare_filter(f1, f4)[1])
    ck("任务级排除条数：只搬运服务端字段（缺失即 None，不推导）",
       task_excluded(f1) == 18 and task_excluded({"filter": {}}) is None)

    ck("取列表：点分路径与整体", pick({"result": {"results": [1, 2]}}, "result.results") == [1, 2]
       and pick({"data": [1]}, "data") == [1] and pick({"a": 1}, "") == {"a": 1}
       and pick({"a": 1}, ".") == {"a": 1} and pick({}, "data") is None)
    ck("解析：非 JSON 文本 → None", parse_doc("jobs n=3\njobId ...") is None
       and parse_doc('{"a": 1}') == {"a": 1})
    ck("CLI 入口存在", os.path.isfile(CLI), CLI)

    # 取数收口/去重判据的零件（在线那一轮用真数据跑完整流程）
    ck("编号字段：识别 resultId", row_id_field([{"resultId": 1, "t": "x"}]) == "resultId")
    ck("编号字段：认不出就不判", row_id_field([{"title": "无编号"}]) is None
       and unique_count([{"title": "a"}], None) is None)
    ck("去重计数：2 条 1 个编号", unique_count([{"resultId": 1}, {"resultId": 1}], "resultId") == 1)
    ck("去重计数：2 条 2 个编号", unique_count([{"resultId": 1}, {"resultId": 2}], "resultId") == 2)
    ck("翻页保护常量合理（单页上限 200、翻页上限 >1）", SINGLE_PAGE_MAX == 200 and MAX_PAGES > 1)

    # 取值域一致性（离线：读 schema 与仪器常量逐字比对）
    enum = schema_enum_parity()
    ck("schema 的 --relevance-filter 取值域 == 仪器 RELEVANCE_FILTER", enum["ok"], enum["note"])

    passed = sum(1 for _, c, _ in checks if c)
    for name, cond, detail in checks:
        print("%s %s%s" % ("PASS" if cond else "FAIL", name, (" · " + detail) if detail else ""))
    print("self-test: %d/%d" % (passed, len(checks)))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
