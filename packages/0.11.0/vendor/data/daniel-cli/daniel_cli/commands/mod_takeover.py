# -*- coding: utf-8 -*-
"""takeover 模块：接管验收（读链复用既有仪器 `daniel_takeover_check.py`；写链走统一门禁链）。

`check-writes`（A1 起真实执行已接通）：把仪器的 `--with-writes --yes` 真正跑起来 ——
仪器自己的写链纪律是**零净变化／用后即删**：
  · Brands 区块：建一个临时品牌 `_tmp-takeover-<时分秒>` → 改一个字段 → 回读 → 删除 → 双回读；
  · SOV 区块：把读到的原值**原样写回**（`updateFilterKeywords`／`updateBrandConfig`），
    读回为空／None 时**拒绝写回**（防把一次读取失败写成清空配置）。
CLI 侧**只做范围收窄与回读核对**，不重写任何判据：默认只跑 Brands 单区块（最小可得），
并在仪器之外**再独立回读一次**「有没有 `_tmp-takeover-` 残留」。
"""
from ..exits import EXIT_OK, EXIT_USAGE
from ..runtime import CliError, new_client, run_instrument, use_instrument, extract_json_detailed
from ._common import append_flag, append_repeat, live_managed_write

BOARD = "takeover"
SCRIPT = "daniel_takeover_check.py"

#: 临时对象的命名前缀（仪器的约定；回读残留用它判）
TMP_PREFIX = "_tmp-takeover-"

#: 默认的写链范围：只跑 Brands（建→改→删→双回读）。为什么要收窄：见 `_plan_check_writes`。
DEFAULT_ONLY = ("brands",)


def cmd_check(ctx):
    d = new_client(verbose=ctx.verbose)
    bid = d.resolve_brand_ref(ctx.require("--brand"))["id"]
    argv = ["--brand", str(bid), "--json"]
    append_repeat(argv, "--only", ctx.get("only"))
    append_flag(argv, "--out", ctx.get("out"))
    ctx.progress("正在跑只读接管验收（品牌/提及/情报/声量/真实性）")
    return use_instrument(ctx, SCRIPT, argv, route="takeover(read-only)")


HANDLERS = {
    "check": cmd_check,
}


def _plan_check_writes(ctx, client):
    """只读解析目标品牌（不执行任何写）。"""
    b = client.resolve_brand_ref(ctx.require("--brand"))
    only = [str(x) for x in (ctx.get("only") or DEFAULT_ONLY)]
    return {
        "targetName": b.get("name"), "brand": "%s(编号 %s)" % (b.get("name"), b.get("id")),
        "workspaceId": b.get("workspaceId"),
        "impact": "会对品牌「%s」跑一遍含写链的接管验收（区块：%s）。写链是**用后即删／零净变化**："
                  "brands 区块建一个临时品牌改一个字段后删掉并双回读；sov 区块把读到的原值原样写回。"
                  "默认只跑 brands（最小可得）。请求数由仪器内部决定（brands 单区块约 8 次）"
                  % (b.get("name"), "、".join(only)),
        "changes": {"takeover.checkWrites": {"brandId": b.get("id"), "only": only}},
        "writesDatabase": True,
    }


def _run_check_writes(ctx, client, plan):
    """真跑：跑仪器的写链（`--with-writes --yes`）→ 解析通过／不通过／跳过清单 → 独立回读残留。"""
    b = client.resolve_brand_ref(ctx.require("--brand"))
    only = [str(x) for x in (ctx.get("only") or DEFAULT_ONLY)]
    argv = ["--brand", str(b["id"]), "--json", "--with-writes", "--yes"]
    append_repeat(argv, "--only", only)
    append_flag(argv, "--out", ctx.get("out"))
    ctx.progress("正在跑含写链的接管验收（区块：%s；写链用后即删）" % "、".join(only))
    run = run_instrument(SCRIPT, argv, timeout=900)
    report, _meta = extract_json_detailed(run.stdout)
    if not isinstance(report, dict) or "checks" not in report:
        tail = [ln for ln in (run.stderr or run.stdout or "").strip().splitlines() if ln.strip()]
        raise CliError("接管验收（含写链）没有产出检查清单（退出码 %d）：%s"
                       % (run.returncode, tail[-1][:200] if tail else "无输出"),
                       code=EXIT_INTERNAL,
                       hint="该工序的写链是「建临时对象→改→删」，失败时请先人工核查残留："
                            "`daniel brands list --limit 50` 找 %s 开头的品牌" % TMP_PREFIX)
    rows = [c for c in (report.get("checks") or []) if isinstance(c, dict)]
    count = lambda st: len([c for c in rows if str(c.get("status") or "").upper() == st])
    passed, failed, skipped, warned = count("PASS"), count("FAIL"), count("SKIP"), count("WARN")

    # 独立回读：仪器的临时品牌有没有留下残留（不看仪器的自述，自己再查一次）
    ws = b.get("workspaceId")
    left = client.query("brands.list", {"workspaceId": int(ws)}) if ws is not None else []
    left = [r for r in (left or []) if isinstance(r, dict)
            and str(r.get("name") or "").startswith(TMP_PREFIX)]
    verified = bool(rows) and not failed and not left
    reason = ""
    if failed:
        reason = "有 %d 项 FAIL：%s" % (failed, "／".join(
            str(c.get("name")) for c in rows if str(c.get("status")) == "FAIL"))
    elif left:
        reason = "独立回读发现临时对象残留：%s" % "、".join(
            "%s(%s)" % (r.get("name"), r.get("id")) for r in left[:3])
    elif not rows:
        reason = "检查清单为空（checks 为空）"
    return {
        "mutation": {"route": "takeover.checkWrites（仪器 daniel_takeover_check.py --with-writes --yes）",
                     "request": {"brandId": b.get("id"), "only": only, "withWrites": True}},
        "readback": {"verified": verified, "reason": reason,
                     "detail": {"通过": passed, "不通过": failed, "跳过": skipped, "留意": warned,
                                "临时对象残留": len(left),
                                "仪器退出码": run.returncode,
                                "仪器小结": report.get("summary"),
                                "清单": rows},
                     "how": "三段回读：① 仪器 `--json` 的 checks 清单（PASS/FAIL/SKIP 逐项）；"
                            "② CLI 侧独立回读该工作区品牌清单，确认没有 %s 开头的残留；"
                            "③ 仪器自身对临时品牌做了「删除后双回读（getById=None 且 list 不含该 id）」"
                            % TMP_PREFIX},
        "rolledBack": True,
        "rollbackNote": "仪器自带回滚：临时品牌在建完同一个流程里删掉并双回读；"
                        "CLI 侧再独立回读一次确认无 %s 残留（本次残留 %d 个）" % (TMP_PREFIX, len(left)),
        "terminal": "成功" if verified else "失败",
        "detail": {"通过": passed, "不通过": failed, "跳过": skipped, "留意": warned,
                   "临时对象残留": len(left), "仪器小结": report.get("summary")},
    }


WRITE_HANDLERS = {
    "check-writes": live_managed_write(BOARD, "check-writes", "含写链的接管验收",
                                       plan_fn=_plan_check_writes,
                                       run_fn=_run_check_writes,
                                danger="含真实写：建一个临时品牌改字段后删掉（用后即删）＋ "
                                       "可选的零净变化写回"),
}
