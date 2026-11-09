# -*- coding: utf-8 -*-
"""写操作审计留痕（TICKET-152 · P0-5）。

三条不因"取消审批"而放松的纪律之三（TICKET-152 §四）：**每次写生成一条可导出的审计记录**。
记录落在数据落点 `DANIEL_HOME/logs/write-audit.jsonl`（一行一条，追加写，不覆盖历史）。

每条记录回答六个问题（票面口径）：
  时间／账号／工作区／品牌／动作／影响范围／回读结果／是否回滚

本模块**只写审计**：不做任何业务判断，也不接触凭据 —— 记录里的账号一律是**掩码邮箱**，
与 `permissions.audit_fields()` 的白名单同源。
"""
import json
import os
import time

from .exits import EXIT_INTERNAL, EXIT_USAGE
from .runtime import CliError

FILE_NAME = "write-audit.jsonl"

#: 记录字段（`daniel account audit` 的列口径来自这里，帮助文本与导出同源）
FIELDS = ("ts", "time", "account", "systemRole", "userStatus", "workspaceId", "workspaceName",
          "planTier", "module", "command", "action", "target", "brand", "impact",
          "permissionSource", "permissionAllowed", "permissionReason", "dryRun", "executed",
          "ok", "exitCode", "mutation", "readback", "readbackOk", "rolledBack", "rollbackNote",
          "failureKind", "exceptionType", "errorSummary",          # TICKET-196：执行轴抛异常时的留痕
          "notes")

#: 失败／被拒的**可判定原因**（TICKET-196）：一条记录只要 `ok=False`，就必须带这里的某个取值，
#: 否则"失败了但不知道为什么"—— 对账式（尝试 == 成功 ＋ 失败 ＋ 拒绝）也只认得这八个原因。
#:   `permission`            ＝ 权限轴不满足（退出码 2，未进入执行分支）
#:   `delete-token-missing`  ＝ 删除类缺 `--delete-token`（退出码 2，零删除）
#:   `delete-token-mismatch` ＝ `--delete-token` 与目标名不一致（退出码 2，零删除）
#:   `stage-not-live`        ＝ 本工序只到干跑（退出码 1，未进入执行分支）
#:   `plan-rejected`         ＝ 计划轴拒绝（重名／目标解析不到／非测试对象／非空名单…）；
#:                             零副作用、零发包，但**也是一次尝试**，照样留一笔（TICKET-196 实测补齐）
#:   `readback`              ＝ 执行了但回读校验没过（退出码 1，真执行过）
#:   `exception`             ＝ 执行函数抛异常（TICKET-196 账二；`executed=True` 的语义逐字是
#:                             「**尝试执行但抛异常**」，没有取得终态）
#:   `unsettled`             ＝ 异常穿出执行轴却没有异常对象可取（进程被中断／分支漏落终态）
FAILURE_KINDS = ("permission", "delete-token-missing", "delete-token-mismatch",
                 "stage-not-live", "plan-rejected", "readback", "exception", "unsettled")


def log_dir():
    """审计落点：数据落点真源 `daniel_paths` 的 `logs/`（不在这里自造第二份口径）。"""
    from .runtime import load_capability
    dpaths = load_capability("daniel_paths")
    return dpaths.paths()["logs_dir"]


def log_path(out_dir=None):
    return os.path.join(out_dir or log_dir(), FILE_NAME)


def record(entry, out_dir=None):
    """追加一条审计记录；返回落盘后的记录（含 `path`）。写不进去就抛内部错误。

    审计是写链的一部分：**审计写不下去时不许把写说成"完成"** —— 所以这里失败是硬失败，
    由调用方决定怎么处置（CLI 侧会把它报成内部错误，退出码 1）。
    """
    row = {"ts": time.time(), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    row.update({k: v for k, v in (entry or {}).items() if k in FIELDS or k == "path"})
    path = log_path(out_dir)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as e:
        raise CliError("审计记录写不进去：%s（%s）" % (path, e), code=EXIT_INTERNAL,
                       hint="检查 DANIEL_HOME 下的 logs 目录是否可写：daniel account paths")
    row["path"] = path
    return row


def read_records(limit=None, out_dir=None, module=None, command=None):
    """读回审计记录（旧→新）。文件不存在＝还没有写过（返回空列表，不是错误）。"""
    path = log_path(out_dir)
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except ValueError:
                rows.append({"time": "", "ok": False, "notes": "该行不是合法 JSON（已跳过内容）"})
                continue
            if not isinstance(doc, dict):
                continue
            if module and doc.get("module") != module:
                continue
            if command and doc.get("command") != command:
                continue
            rows.append(doc)
    if limit:
        rows = rows[-int(limit):]
    return rows


def summarize(rows):
    """给人看的小结（导出时一并给出，避免调用方自己数）。"""
    executed = [r for r in rows if r.get("executed")]
    failed = [r for r in rows if r.get("executed") and not r.get("ok")]
    rolled = [r for r in rows if r.get("rolledBack")]
    dry = [r for r in rows if not r.get("executed")]
    last = rows[-1] if rows else None
    return {"记录条数": len(rows), "真执行": len(executed), "未执行（干跑或被拒）": len(dry),
            "执行失败": len(failed), "已回滚": len(rolled),
            "最近一条": ({"时间": last.get("time"), "动作": "%s %s" % (last.get("module"),
                                                                    last.get("command")),
                          "是否执行": bool(last.get("executed"))} if last else None),
            "落点": log_path()}


def export(out_path=None, limit=None, out_dir=None):
    """导出审计（`daniel account audit --json` 的结果体）。给了 `out_path` 就落一份文件。"""
    rows = read_records(limit=limit, out_dir=out_dir)
    payload = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "源文件": log_path(out_dir),
               "字段口径": list(FIELDS), "小结": summarize(rows), "记录": rows}
    if out_path:
        p = os.path.abspath(os.path.expanduser(str(out_path)))
        try:
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
        except OSError as e:
            raise CliError("审计导出写不进去：%s（%s）" % (p, e), code=EXIT_USAGE)
        payload["导出文件"] = p
    return payload


__all__ = ["FIELDS", "record", "read_records", "summarize", "export", "log_dir", "log_path"]
