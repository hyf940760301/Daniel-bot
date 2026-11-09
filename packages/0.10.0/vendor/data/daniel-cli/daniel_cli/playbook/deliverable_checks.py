#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deliverable_checks.py —— KOL 名单交付件的四类自检（纯函数，零依赖）。

为什么单独一个模块
------------------
契约 `contracts/kol-list.json` 只声明「交付件长什么样、必须自证什么」；
**具体怎么查**放在这里，避免把判定逻辑塞进契约 JSON（契约是声明，不是代码）。

四类违规（对应契约自检 K1）
--------------------------
  U1 未标口径   数字出现了，但没说清是哪个指标、哪个取值面、什么时间窗
  U2 禁用表述   「非常好／绝对／大概」这类含糊词 —— 把"没判断"伪装成"判断"
  U3 未筛维度   没列出本次没筛的维度 —— 读者会误以为全维度都查过
  U4 不可靠未标注  引用了 data_status=unreliable 的指标，却没加标注

口径与阈值的来源
----------------
`spec` 由调用方传入（通常来自 `_ONTOLOGY.json` 与任务确认结果）：
  spec = {
    "指标口径": {"长视频均播（近28天中位数）": "metric.creator.avg_views_long.median", ...},
    "不可靠指标": ["metric.creator.avg_views_long.reported"],
    "禁用词": ["非常好", "绝对", "肯定没问题", "大概"],
    "未筛维度": ["受众性别/年龄", "商业合作"],
  }
本模块**不猜**阈值，也不内置业务口径 —— 没有 spec 就没有判据。
"""

BANNED_DEFAULT = ("非常好", "绝对", "肯定没问题", "大概")
#: 结构性列（编号／排名这类不是业务指标，不该要求口径）
NON_METRIC_DEFAULT = ("序号", "编号", "排名", "行号", "index", "Rank")


def _looks_numeric(v):
    if isinstance(v, bool) or v is None:
        return False
    if isinstance(v, (int, float)):
        return True
    s = str(v).strip().replace(",", "")
    if not s:
        return False
    body = s.rstrip("%")
    if body.endswith(("万", "w", "k", "K")):
        body = body[:-1]
    try:
        float(body)
        return True
    except ValueError:
        return False


def check(rows, spec):
    """跑四类自检。返回 `{违规, 违规数, 明细, 行数, 口径覆盖}`（全为业务语言）。"""
    spec = spec or {}
    cols = spec.get("指标口径") or {}
    unreliable = set(spec.get("不可靠指标") or [])
    banned = tuple(spec.get("禁用词") or BANNED_DEFAULT)
    unscreened = spec.get("未筛维度")
    non_metric = tuple(spec.get("非指标列") or NON_METRIC_DEFAULT)
    notes = spec.get("口径标注") or {}

    violations = []

    for i, row in enumerate(rows or [], start=1):
        for col, val in (row or {}).items():
            if _looks_numeric(val):
                if col in non_metric:
                    continue
                if col not in cols and col not in notes:
                    violations.append({
                        "类": "U1 未标口径", "行": i,
                        "说明": "%s「%s」是数字，但没说清口径（指标／取值面／时间窗）" % (col, val),
                    })
                elif col in cols and cols[col] in unreliable and not notes.get(col):
                    violations.append({
                        "类": "U4 不可靠未标注", "行": i,
                        "说明": "%s 用了不可靠口径 %s，却未标注" % (col, cols[col]),
                    })
            text = "" if val is None else str(val)
            for w in banned:
                if w and w in text:
                    violations.append({
                        "类": "U2 禁用表述", "行": i,
                        "说明": "%s 出现「%s」——改用可核对的判断" % (col, w),
                    })

    if not unscreened:
        violations.append({
            "类": "U3 未筛维度", "行": 0,
            "说明": "没列出本次未筛的维度（读者会误以为全维度都查过）",
        })

    return {
        "违规": violations,
        "违规数": len(violations),
        "明细": violations,
        "行数": len(rows or []),
        "口径覆盖": sorted(cols.keys()),
    }
