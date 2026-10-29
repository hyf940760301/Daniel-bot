# -*- coding: utf-8 -*-
"""交付物工厂（TICKET-175 · P0 地基③）：出件模板机制 ＋ 出件自检门禁 ＋ 本地落盘。

**它解决的问题**：交付物是用户唯一真正拿到手的东西，而在此之前引擎只有"把行落成一个
JSON 文件"的钩子 —— 没有字段口径、没有排序声明、没有计数对账、没有出件自检，也没有
一条把落点统一到 `$DANIEL_HOME` 的路。本文件把 `交付件schema` 补成一张**声明式出件模板**
（字段清单／排序／计数对账／出件格式／行判据／判据出处），并在出件时**自动**跑五条自检。

**五条自检（票面 C；出件的组成部分，不是可选步骤）**：

| # | 断言 | 不过的后果 |
|---|---|---|
| ① | 全表闭合：每条记录都有全部必填列 | 逐条点出**第几行缺哪一列** |
| ② | 计数对账：主表行数 == 出件文件行数；入池数 ≥ 出件数且差额可解释 | 两边的实际值都印出来 |
| ③ | 排序键单调：按模板声明的排序键与方向单调 | 点出**第一处逆序的行号** |
| ④ | 无「无数据写法」以外的空值（也不许自造 N/A／- 之类的占位） | 点出行号＋列名 |
| ⑤ | 关键桶非 0 | 点出哪个桶是 0、下限是多少 |

**"不过不得出件"怎么做到**（这一步是硬约束，不靠自觉）：
    渲染 → 写进**系统临时文件** → 回读做计数对账 → 五条全过才 `os.replace` 到落点。
    任一条不过：临时文件删除、**落点上不存在任何文件**、返回 `状态=失败`（执行器据此非零退出）。

**落点**（票面 A；落点规范 TICKET-154 §一）：
    默认 `daniel_paths.resolve('output_dir')`，即 `$DANIEL_HOME/output/<契约id>/`；
    调用方可用 `playbook deliver --out DIR` 覆盖（落点由调用方决定时只改默认值，不写死）。
    **不写代码目录**：本文件里没有任何工作区相对字面落点。

零第三方依赖：CSV／MD 用标准库，XLSX 用 `zipfile` ＋ 最小 SpreadsheetML（inlineStr），
回读也用标准库 —— 「写后对账」才可能在没有 openpyxl 的机器上照样跑。
"""
import ast
import csv
import hashlib
import io
import json
import os
import re
import tempfile
import zipfile

from ..exits import EXIT_USAGE
from ..runtime import CliError
from . import model
from . import pdfout

# ─────────────────────────── daniel_paths：落点解析 ───────────────────────────
# 落点唯一真源是 `.kol-tools/daniel_paths.py`（TICKET-144／147）。这里按路径加载，
# 与 CLI 其余部分同一口径：先 `DANIEL_CLI_TOOLS`，再从本包位置逐级向上找 `.kol-tools`。
# **注意**：必须写成 `<_dp>.resolve('output_dir')` 这种形态 —— 落点门禁
# （`.kol-tools/check_write_landings.py`）按这个哨兵认"已统一到用户数据目录"。
_PATHS_CACHE = {}


def _paths():
    if "mod" in _PATHS_CACHE:
        return _PATHS_CACHE["mod"]
    import importlib.util
    import sys
    from ..runtime import tools_dir
    path = os.path.join(tools_dir(), "daniel_paths.py")
    if not os.path.isfile(path):
        raise CliError("落点解析层缺失：%s（交付物落点必须走 daniel_paths）" % path,
                       code=EXIT_USAGE,
                       hint="确认能力目录完整（`.kol-tools/daniel_paths.py`）")
    name = "daniel_cli_cap_daniel_paths"
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    _PATHS_CACHE["mod"] = mod
    return mod


OUTPUT_DIR = None      # 兼容占位：真值由 `output_dir()` 惰性解析（**不要在 import 期解析**）


def output_dir():
    """交付物默认落点目录：`daniel_paths.resolve('output_dir')` ＝ `$DANIEL_HOME/output`。

    **为什么是函数、不是模块级常量**（CLS-85 的现场教训）：模块级调用会在 **import 那一刻**
    就去解析 `$DANIEL_HOME`，而解析先要定位 `.kol-tools` —— 于是"把包拷到别处（没有能力目录）
    也能 import、`daniel skills list` 照样可用"这条产品可用性不变量**当场被破**
    （C15 路径归一化不变量实测：拷走的包里直接抛 `CliError: 找不到 Daniel 能力目录`）。
    落点只在**真出件**那一刻才需要，所以解析也必须推迟到那一刻 —— 声明与实现同一批落地，
    中间态（只改了实现或只改了声明）都不允许存在。
    """
    return _paths().resolve("output_dir")     # 落点门禁认这个哨兵＝"已统一到用户数据目录"


def default_out_dir(contract_id):
    """默认落点：`$DANIEL_HOME/output/<契约id>/`（一个契约一个目录，便于回查）。"""
    return os.path.join(output_dir(), _safe_name(contract_id or "contract"))


def _safe_name(name):
    return re.sub(r"[^0-9A-Za-z._\u4e00-\u9fff-]+", "_", str(name)) or "contract"


# ─────────────────────────── 模板口径 ───────────────────────────
def is_template(spec):
    """是不是**模板式**出件（声明了 `格式`）。遗留式（没声明）行为一个字不变。"""
    return bool(isinstance(spec, dict) and spec.get(model.D_FORMAT))


def normalize_spec(spec):
    """把 `交付件schema` 归一成统一口径（列一律是对象；缺省值补齐）。"""
    spec = dict(spec or {})
    null_text = spec.get(model.D_NULL_TEXT) or "无官方数据"
    cols = []
    for raw in spec.get(model.D_COLUMNS) or []:
        if isinstance(raw, str):
            cols.append({"列名": raw, "来源": raw, "必填": True, "无数据写法": None,
                         "出处": None, "格式": None})
            continue
        if isinstance(raw, dict):
            c = dict(raw)
            c.setdefault("列名", None)
            c.setdefault("来源", c.get("列名"))
            c.setdefault("必填", True)
            c.setdefault("无数据写法", None)
            c.setdefault("出处", None)
            c.setdefault("格式", None)
            cols.append(c)
    return {
        "名称": spec.get(model.D_NAME),
        "文件名": spec.get(model.D_FILE),
        "来源步骤": spec.get(model.D_SOURCE),
        "格式": spec.get(model.D_FORMAT) or "JSON",
        "排序": list(spec.get(model.D_SORT) or []),
        "无数据写法": null_text,
        "不得占位列": list(spec.get(model.D_NO_NULL_COLUMNS) or []),
        "行判据": list(spec.get(model.D_ROW_CRITERIA) or []),
        "关键桶": list(spec.get(model.D_BUCKETS) or []),
        "计数对账": list(spec.get(model.D_RECONCILE) or []),
        "判据出处": list(spec.get(model.D_SOURCES) or []),
        "附表": list(spec.get(model.D_EXTRA) or []),
        "行数上限引用": spec.get(model.D_ROW_LIMIT),
        "列": cols,
        "必填列": list(spec.get(model.D_REQUIRED_COLUMNS) or []),
        "_raw": spec,
    }


def column_names(spec):
    return [c["列名"] for c in normalize_spec(spec)["列"]]


def source_field(col):
    """列来源 → `(类型, 参数)`。字符串 = 产出里的字段名；对象 = 计算／模板／生成。"""
    src = col.get("来源")
    if isinstance(src, dict):
        if model.SRC_COMPUTE in src:
            return model.SRC_COMPUTE, src[model.SRC_COMPUTE]
        if model.SRC_TEMPLATE in src:
            return model.SRC_TEMPLATE, src[model.SRC_TEMPLATE]
        if model.SRC_GENERATE in src:
            return model.SRC_GENERATE, src[model.SRC_GENERATE]
        if model.SRC_FIELD in src:
            return model.SRC_FIELD, src[model.SRC_FIELD]
        return None, None
    return model.SRC_FIELD, src


# ─────────────────────────── 列计算（表达式求值） ───────────────────────────
_ALLOWED_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult,
                  ast.Div, ast.USub, ast.UAdd, ast.Constant, ast.Name, ast.Load)


def eval_formula(expr, row):
    """按列名求值一个只含 `+ - * / ( )` 的表达式（白名单 AST，**不用 eval**）。

    取不到列或列不是数字 → 抛 `ValueError`（该行该列记违规，不静默给 0）。
    """
    try:
        tree = ast.parse(str(expr), mode="eval")
    except SyntaxError as e:
        raise ValueError("表达式语法错误：%s" % e)
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError("表达式里出现了不允许的语法：%s" % type(node).__name__)
    env = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in row:
                raise ValueError("表达式引用了不存在的列：%s" % node.id)
            v = row[node.id]
            try:
                env[node.id] = float(str(v).replace(",", "").replace("%", ""))
            except (TypeError, ValueError):
                raise ValueError("列「%s」不是数字（当前 %r）" % (node.id, v))
    return eval(compile(tree, "<列计算>", "eval"), {"__builtins__": {}}, env)   # noqa: S307


def format_value(value, fmt):
    """列的显示格式：整数／百分比／数字／文本。"""
    if value is None:
        return None
    if fmt in (None, "", "文本"):
        return value if isinstance(value, str) else _auto_text(value)
    try:
        num = float(value)
    except (TypeError, ValueError):
        return value
    if fmt == "整数":
        return str(int(round(num)))
    if fmt == "百分比":
        return "%.2f%%" % (num * 100)
    if fmt == "百分数":
        # 值本身已经是百分数（Daniel 的 ER 字段口径：1.08 ＝ 1.08%），只补一个 % 号
        return "%.2f%%" % num
    if fmt == "数字":
        return ("%.4f" % num).rstrip("0").rstrip(".")
    return _auto_text(value)


def _auto_text(value):
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        return ("%.4f" % value).rstrip("0").rstrip(".")
    return str(value)


def _is_blank(v):
    return v is None or (isinstance(v, str) and not v.strip())


#: 常见的"自造占位"（Skill §15.5.5 判据2 只认「无官方数据」这一种写法）
FAKE_PLACEHOLDERS = ("-", "--", "—", "n/a", "N/A", "na", "null", "None", "无", "暂无",
                     "未知", "missing", "N.A.", "?")


# ─────────────────────────── 行判据（逐字取自 Skill） ───────────────────────────
def _negation_stripped(text, negatives):
    """Skill §15.5.4 规则2：解析判定依据前先剔除否定句（否定句是**负证据**）。

    做法：把命中否定词的**那一句**整句去掉，再看剩下的文本里有没有正面点名 ——
    否则 `No exact mention of "Halliday G2"` 这类句子会被当成点名证据（实测假阳性来源）。
    """
    if not text:
        return ""
    kept = []
    for sentence in re.split(r"(?<=[.。;；!?！？\n])", str(text)):
        low = sentence.lower()
        if any(neg.lower() in low for neg in negatives or []):
            continue
        kept.append(sentence)
    return " ".join(kept)


def _mention_position(row, crit):
    """返回点名的位置（标题／话题标签／频道名／判定依据原话），没点名返回 None。

    判据条文（Skill §15.5.4 规则1，逐字）：一条视频满足下列之一才算"点名到品牌 B"：
    ① 标题／话题标签出现品牌或产品名；② 频道名含品牌（官方号）；
    ③ `relevanceReasoning` 里**正面**点名到 B 或其产品。
    """
    words = [str(w) for w in (crit.get(model.CRC_WORDS) or []) if str(w).strip()]
    if not words:
        return None
    hint = crit.get(model.CRC_HINT_FIELDS) or []
    title_col = hint[0] if len(hint) > 0 else None
    channel_col = hint[1] if len(hint) > 1 else None

    def has(value):
        text = str(value or "").lower()
        return any(w.lower() in text for w in words)

    if title_col and has(row.get(title_col)):
        return title_col
    if channel_col and has(row.get(channel_col)):
        return channel_col
    ev = row.get(crit.get(model.CRC_FIELD))
    if has(_negation_stripped(ev, crit.get(model.CRC_NEGATIVE))):
        return crit.get(model.CRC_FIELD)
    return None


def _num_of(value):
    try:
        return float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def apply_relation(row, crit, null_text):
    """一条行判据对一行 → `(是否通过, 原因)`；原因只在**不通过**时给（带列名与取值）。"""
    rel = crit.get(model.CRC_RELATION)
    field = crit.get(model.CRC_FIELD)
    value = row.get(field) if field else None
    if rel in (model.REL_NOT_NULL, model.REL_NOT_PLACEHOLDER):
        if _is_blank(value):
            return False, "列「%s」为空（%s）" % (field, rel)
        if rel == model.REL_NOT_PLACEHOLDER and str(value).strip() == null_text:
            return False, "列「%s」是占位「%s」，该列不允许占位" % (field, null_text)
        return True, ""
    if rel in (model.REL_EQ, model.REL_NE):
        want = crit.get(model.CRC_THRESHOLD)
        hit = str(value) == str(want)
        if (hit if rel == model.REL_EQ else not hit):
            return True, ""
        if rel == model.REL_EQ:
            return False, "列「%s」取值 %r ≠ Skill 门槛 %r" % (field, value, want)
        return False, "列「%s」取值 %r 命中了排除值 %r" % (field, value, want)
    if rel in (model.REL_GT, model.REL_GE, model.REL_LT, model.REL_LE):
        x, y = _num_of(value), _num_of(crit.get(model.CRC_THRESHOLD))
        if x is None:
            return False, "列「%s」不是数字（当前 %r），无法与门槛 %s 比较" % (
                field, value, crit.get(model.CRC_THRESHOLD))
        ok = {model.REL_GT: x > y, model.REL_GE: x >= y,
              model.REL_LT: x < y, model.REL_LE: x <= y}[rel]
        return ok, "" if ok else "列「%s」取值 %s 不满足 %s %s（Skill 门槛）" % (
            field, _auto_text(x), rel, _auto_text(y))
    if rel in (model.REL_IN, model.REL_NOT_IN):
        words = [str(w) for w in (crit.get(model.CRC_THRESHOLD) or [])]
        hit = any(w == str(value) for w in words)
        if rel == model.REL_NOT_IN:
            hit = not hit
        return hit, "" if hit else "列「%s」取值 %r 不在允许集合 %s 里" % (field, value, words)
    if rel == model.REL_MENTION:
        pos = _mention_position(row, crit)
        return bool(pos), "" if pos else "未在标题／话题标签／频道名／判定依据里正面点名到品牌"
    return False, "未知的行判据关系：%r" % rel


def apply_row_criteria(rows, spec):
    """逐条施加行判据（声明顺序即门槛叠加顺序），返回 `(保留的行, 阶梯, 每个判据的剔除行)`。

    **阶梯**就是 Skill §15.5.6 规则4 要的"多口径梯度对照"：逐级给出每一道门槛的代价。
    """
    kept = [dict(r) for r in rows if isinstance(r, dict)]
    ladder, dropped = [], {}
    for crit in spec["行判据"]:
        cid = crit.get(model.CRC_ID)
        rel = crit.get(model.CRC_RELATION)
        before = len(kept)
        if rel == model.REL_DEDUP:
            key_col = crit.get(model.CRC_FIELD)
            max_col = crit.get(model.CRC_MAX)
            best = {}
            for r in kept:
                k = r.get(key_col)
                cur = best.get(k)
                if cur is None or (_num_of(r.get(max_col)) or -1) > (_num_of(cur.get(max_col)) or -1):
                    best[k] = r
            kept = list(best.values())
            reason = "同一「%s」只保留「%s」最高的一条" % (key_col, max_col)
        else:
            survived = []
            for r in kept:
                ok, _why = apply_relation(r, crit, spec["无数据写法"])
                if ok:
                    survived.append(r)
            kept = survived
            reason = crit.get(model.CRC_DESC) or rel
        ladder.append({
            "序号": len(ladder) + 1,
            "判据": cid,
            "门槛": _criterion_text(crit),
            "判据出处": crit.get(model.CRC_SOURCE),
            "入池条数": before,
            "保留条数": len(kept),
            "剔除条数": before - len(kept),
            "说明": reason,
        })
        dropped[cid] = before - len(kept)
    return kept, ladder, dropped


def _criterion_text(crit):
    rel = crit.get(model.CRC_RELATION)
    field = crit.get(model.CRC_FIELD)
    if rel == model.REL_DEDUP:
        return "%s：每个「%s」取「%s」最高的一条" % (rel, field, crit.get(model.CRC_MAX))
    if rel == model.REL_MENTION:
        return "%s：%s ∈ %s（先剔除否定句）" % (
            rel, field, "／".join(str(w) for w in (crit.get(model.CRC_WORDS) or [])))
    if crit.get(model.CRC_THRESHOLD) is None:
        return "%s：%s" % (rel, field)
    return "门槛：%s %s %s" % (field, rel, crit.get(model.CRC_THRESHOLD))


def explain_rejections(rows, spec, limit=200):
    """给出**逐行**的剔除理由（哪些行没过哪条判据），供报告与人工回查。"""
    out = []
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict):
            out.append({"池内行号": i, "判据": None, "理由": "记录不是对象"})
            continue
        for crit in spec["行判据"]:
            rel = crit.get(model.CRC_RELATION)
            if rel == model.REL_DEDUP:
                continue                     # 去重是集合级判据，逐行判不了，另报
            ok, why = apply_relation(r, crit, spec["无数据写法"])
            if not ok:
                out.append({"池内行号": i, "判据": crit.get(model.CRC_ID), "理由": why,
                            "值": str(r.get(crit.get(model.CRC_FIELD)))[:80]})
                break                        # 只报第一处不通过（人看的是"为什么它没进来"）
        if len(out) >= limit:
            break
    return out


# ─────────────────────────── 渲染与回读 ───────────────────────────
def render(fmt, headers, rows, title=None):
    """按格式把一张表渲染成字节（CSV／MD 走文本，XLSX 走最小 SpreadsheetML，
    **PDF 走既有出件工序**（`.kol-tools/doc_to_pdf.py`：语义块 → 打印级 HTML → Chromium）。

    `title` 只有 PDF 用得上（它是**文档**，要有标题）；其余格式忽略它，行为一个字不变。
    """
    fmt = (fmt or "JSON").upper()
    if fmt == "JSON":
        return json.dumps({"列": headers, "行数": len(rows), "行": rows},
                          ensure_ascii=False, indent=1).encode("utf-8"), "json"
    if fmt == "CSV":
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(headers)
        for r in rows:
            w.writerow([r.get(h) if r.get(h) is not None else "" for h in headers])
        return buf.getvalue().encode("utf-8-sig"), "csv"      # BOM：Excel 直接打开不乱码
    if fmt == "MD":
        lines = ["| " + " | ".join(_md(h) for h in headers) + " |",
                 "|" + "|".join(["---"] * len(headers)) + "|"]
        for r in rows:
            lines.append("| " + " | ".join(_md(r.get(h)) for h in headers) + " |")
        return ("\n".join(lines) + "\n").encode("utf-8"), "md"
    if fmt == "XLSX":
        return _build_xlsx(headers, rows), "xlsx"
    if fmt == "PDF":
        return _build_pdf(headers, rows, title), "pdf"
    raise ValueError("不支持的出件格式：%r（可用：%s）" % (fmt, "／".join(model.FORMATS)))


def _build_pdf(headers, rows, title):
    """PDF 字节（渲染全交给既有出件工序；这里只做"表 → 语义块"的适配与临时目录管理）。"""
    from . import pdfout
    tmp = tempfile.mkdtemp(prefix="daniel-pdf-render-")
    try:
        path = os.path.join(tmp, "render.pdf")
        pdfout.build_pdf(title or "交付件", headers, rows, path)
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def _md(value):
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


#: 最小 XLSX（零第三方依赖）：只用 inlineStr 与数字单元格，不建 sharedStrings。
_CT = ("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
       "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
       "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package."
       "relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/>"
       "<Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd."
       "openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>"
       "<Override PartName=\"/xl/worksheets/sheet1.xml\" ContentType=\"application/vnd."
       "openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/></Types>")
_RELS = ("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
         "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/"
         "relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/"
         "officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/>"
         "</Relationships>")
_WB_RELS = ("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/"
            "relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/"
            "officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/>"
            "</Relationships>")


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\"", "&quot;"))


def _col_letter(idx):
    out, idx = "", idx + 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        out = chr(65 + rem) + out
    return out


def _build_xlsx(headers, rows):
    num_re = re.compile(r"^-?\d+(\.\d+)?$")

    def cell(ref, value):
        if value is None or value == "":
            return ""
        text = str(value)
        # 只把"看起来就是数字"的单元格写成数字格：Excel 里才排得了序、算得了数；
        # 其余一律 inlineStr（不建 sharedStrings，零第三方依赖）。
        if num_re.match(text.strip()):
            return "<c r=\"%s\"><v>%s</v></c>" % (ref, text.strip())
        return "<c r=\"%s\" t=\"inlineStr\"><is><t xml:space=\"preserve\">%s</t></is></c>" % (
            ref, _esc(text))

    sheet = ["<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>",
             "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">",
             "<sheetData>"]
    sheet.append("<row r=\"1\">%s</row>" % "".join(
        cell("%s1" % _col_letter(i), h) for i, h in enumerate(headers)))
    for n, r in enumerate(rows, start=2):
        sheet.append("<row r=\"%d\">%s</row>" % (n, "".join(
            cell("%s%d" % (_col_letter(i), n), r.get(h)) for i, h in enumerate(headers))))
    sheet.append("</sheetData></worksheet>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("xl/workbook.xml",
                   "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
                   "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
                   "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
                   "<sheets><sheet name=\"Sheet1\" sheetId=\"1\" r:id=\"rId1\"/></sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", _WB_RELS)
        z.writestr("xl/worksheets/sheet1.xml", "".join(sheet))
    return buf.getvalue()


def read_back(path, fmt):
    """回读产出文件 → `(表头, 数据行)`。**写后对账用**：数字一律从文件里数出来，不靠内存。"""
    fmt = (fmt or "").upper()
    if fmt == "JSON":
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        return list(doc.get("列") or []), list(doc.get("行") or [])
    if fmt == "CSV":
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
        if not rows:
            return [], []
        return rows[0], [dict(zip(rows[0], r)) for r in rows[1:] if any(x.strip() for x in r)]
    if fmt == "MD":
        with open(path, encoding="utf-8") as fh:
            lines = [ln.rstrip("\n") for ln in fh if ln.strip()]
        cells = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
        if not cells:
            return [], []
        headers = cells[0]
        body = [c for c in cells[2:]]
        return headers, [dict(zip(headers, c)) for c in body]
    if fmt == "XLSX":
        return _read_xlsx(path)
    raise ValueError("不认识的回读格式：%r" % fmt)


def _read_xlsx(path):
    import xml.etree.ElementTree as ET
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    out = []
    for row in root.iter(ns + "row"):
        cells = []
        for c in row.iter(ns + "c"):
            t = c.get("t")
            if t == "inlineStr":
                el = c.find(ns + "is/" + ns + "t")
                cells.append(el.text if el is not None and el.text is not None else "")
            else:
                v = c.find(ns + "v")
                cells.append(v.text if v is not None else "")
        out.append(cells)
    if not out:
        return [], []
    headers = out[0]
    return headers, [dict(zip(headers, r)) for r in out[1:]]


# ─────────────────────────── 五条出件自检 ───────────────────────────
def selfcheck(rows, headers, spec, ctx, file_rows=None):
    """五条断言逐条跑，返回 `(违规清单, 计数对账明细, 关键桶明细)`。

    每条违规都带**行号**（票面 C：失败时逐条点出违规行），行号用**出件表里的 1-based 行号**。
    `file_rows` 是**从临时文件回读出来的**数据行数 —— `交付件.文件行数` 取它，而不是内存里的
    `len(rows)`；两者不一致时由调用方另行报一条违规（这就是"主表行数 == CSV 行数"）。
    """
    violations, reconcile, buckets = [], [], []
    n_file = len(rows) if file_rows is None else file_rows
    null_text = spec["无数据写法"]
    required = [c["列名"] for c in spec["列"] if c.get("必填")]
    no_null = set(spec["不得占位列"])

    # ① 全表闭合：每条记录都有全部必填列
    for i, r in enumerate(rows, 1):
        for col in required:
            if _is_blank(r.get(col)):
                violations.append({"断言": "①全表闭合", "行号": i, "列": col,
                                   "说明": "第 %d 行缺必填列「%s」（必填列不允许空壳）" % (i, col)})

    # ③ 排序键单调
    for sort in spec["排序"]:
        key, direction = sort.get("键"), sort.get("方向")
        prev, prev_i = None, None
        for i, r in enumerate(rows, 1):
            cur = _num_of(r.get(key))
            if cur is None:
                violations.append({"断言": "③排序键单调", "行号": i, "列": key,
                                   "说明": "第 %d 行的排序键「%s」不是数字（当前 %r）"
                                           % (i, key, r.get(key))})
                prev, prev_i = None, None
                continue
            bad = (prev is not None and
                   ((direction == model.SORT_DESC and cur > prev) or
                    (direction == model.SORT_ASC and cur < prev)))
            if bad:
                violations.append({
                    "断言": "③排序键单调", "行号": i, "列": key,
                    "说明": "第 %d 行起排序键「%s」不再%s：第 %d 行 %s → 第 %d 行 %s"
                            % (i, key, direction, prev_i, _auto_text(prev), i, _auto_text(cur))})
            prev, prev_i = cur, i

    # ④ 无「无数据写法」以外的空值
    for i, r in enumerate(rows, 1):
        for col in headers:
            v = r.get(col)
            if _is_blank(v):
                violations.append({"断言": "④无空值", "行号": i, "列": col,
                                   "说明": "第 %d 行「%s」为空（无数据要写「%s」，不留空）"
                                           % (i, col, null_text)})
            elif isinstance(v, str) and v.strip() in FAKE_PLACEHOLDERS:
                violations.append({"断言": "④无空值", "行号": i, "列": col,
                                   "说明": "第 %d 行「%s」用了自造占位 %r；本模板只认「%s」"
                                           % (i, col, v, null_text)})
            if col in no_null and isinstance(v, str) and v.strip() == null_text:
                violations.append({"断言": "④无空值", "行号": i, "列": col,
                                   "说明": "第 %d 行「%s」是「%s」，但该列声明为不得占位"
                                           "（不许拿占位当遮羞布）" % (i, col, null_text)})

    # ② 计数对账
    for rule in spec["计数对账"]:
        left = _resolve(rule.get(model.CRC_LEFT), ctx, len(rows), n_file)
        right = _resolve(rule.get(model.CRC_RIGHT), ctx, len(rows), n_file)
        rel = rule.get(model.CRC_RELATION)
        if left is None or right is None:
            violations.append({"断言": "②计数对账", "行号": None, "列": None,
                               "说明": "对账「%s」取值不可解析（左=%r 右=%r）"
                                       % (rule.get(model.CRC_ID), rule.get(model.CRC_LEFT),
                                          rule.get(model.CRC_RIGHT))})
            reconcile.append({"对账": rule.get(model.CRC_ID), "左": rule.get(model.CRC_LEFT),
                              "右": rule.get(model.CRC_RIGHT), "关系": rel,
                              "左值": None, "右值": None, "通过": False})
            continue
        ok = (left == right) if rel == model.REL_EQ else (left >= right)
        reconcile.append({"对账": rule.get(model.CRC_ID), "左": rule.get(model.CRC_LEFT),
                          "右": rule.get(model.CRC_RIGHT), "关系": rel,
                          "左值": left, "右值": right, "通过": ok,
                          "差额": left - right,
                          "差额说明": rule.get(model.CRC_DELTA) if not ok or left != right else ""})
        if not ok:
            violations.append({"断言": "②计数对账", "行号": None, "列": None,
                               "说明": "对账「%s」不成立：%s = %s %s %s = %s（%s）"
                                       % (rule.get(model.CRC_ID), rule.get(model.CRC_LEFT), left,
                                          rel, rule.get(model.CRC_RIGHT), right,
                                          rule.get(model.CRC_DELTA) or "无数额解释")})

    # ⑤ 关键桶非 0
    for b in spec["关键桶"]:
        val = _resolve(b.get(model.CRC_VALUE), ctx, len(rows), n_file)
        floor = b.get(model.CRC_FLOOR, 1)
        ok = val is not None and val >= floor
        buckets.append({"桶": b.get(model.CRC_BUCKET), "取值": b.get(model.CRC_VALUE),
                        "实际": val, "下限": floor, "通过": ok})
        if not ok:
            violations.append({"断言": "⑤关键桶非0", "行号": None, "列": None,
                               "说明": "关键桶「%s」实际 %r，低于下限 %s（%s）"
                                       % (b.get(model.CRC_BUCKET), val, floor,
                                          b.get(model.CRC_VALUE))})
    return violations, reconcile, buckets


def _resolve(ref, ctx, n_rows, n_file_rows):
    """解一个对账／桶取值引用（`交付件.*` / `步骤.<id>.条目数` / `限额.<n>.实际` / `输入.<n>`）。"""
    if not isinstance(ref, str):
        return None
    pool = {"交付件": dict(ctx.get("交付件") or {}, 行数=n_rows, 文件行数=n_file_rows)}
    parts = ref.split(".")
    root, rest = parts[0], parts[1:]
    cur = pool.get(root, ctx.get(root))
    for p in rest:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


# ─────────────────────────── 出件主流程 ───────────────────────────
def deliver(spec_raw, source_rows, *, contract_id=None, step_counts=None, limits=None,
            inputs=None, out_dir=None, row_limit=None):
    """**出件**：模板式交付件的唯一入口。

    返回的字典同时是报告里的 `交付件` 段（键与遗留式兼容：状态／名称／路径／行数／列／
    必填列／校验／明细／数据），并追加模板式的事实（格式／落点／文件行数／sha256／
    出件自检／阶梯／关键桶／计数对账／产物）。

    **不过不得出件**：五条自检任一条不过 → 落点上**没有文件**，`状态=失败`，
    `违规` 逐条带行号（执行器据此非零退出）。
    """
    spec = normalize_spec(spec_raw)
    headers = [c["列名"] for c in spec["列"]]
    pool = [r for r in (source_rows or []) if isinstance(r, dict)]
    base = {
        "状态": model.ST_FAIL, "名称": spec["名称"], "格式": spec["格式"],
        "列": headers, "必填列": spec["必填列"] or [c["列名"] for c in spec["列"] if c.get("必填")],
        "行数": 0, "入池行数": len(pool), "数据": [],
    }

    # ① 列计算（来源＝字段／计算；生成列稍后填）—— 先投影，判据才好按**列名**写
    projected, calc_problems = _project(pool, spec)
    # ② 行判据叠加（顺序即门槛顺序）→ 阶梯
    kept, ladder, _dropped = apply_row_criteria(projected, spec)
    # ③ 排序（声明式；排完由自检③验证单调）
    kept = _sort_rows(kept, spec)
    # ④ 生成列：排名／点名位置
    kept = _generate_columns(kept, spec)
    # ⑤ 非必填列的空 → 按列声明的「无数据写法」补齐（不留空）
    rows = _fill_nulls(kept, spec)
    rows = [_strip_source(r) for r in rows]

    ctx = {"交付件": {"出件行数": len(rows), "入池行数": len(pool),
                     "列数": len(headers), "格式": spec["格式"],
                     "非占位计数": _bucket_counts(rows, headers, spec["无数据写法"], False),
                     "占位计数": _bucket_counts(rows, headers, spec["无数据写法"], True),
                     "去重计数": _distinct_counts(rows, headers)},
           "步骤": step_counts or {}, "限额": limits or {}, "输入": inputs or {}}
    ctx["交付件"]["判据全过后行数"] = len(rows)
    ctx["交付件"]["剔除行数"] = len(pool) - len(rows)

    violations = list(calc_problems)
    cap = (limits or {}).get(row_limit or "") or {}
    cap = cap.get("实际") if isinstance(cap, dict) else None
    if cap is not None and len(rows) > cap:
        violations.append({"断言": "样本上限", "行号": None, "列": None,
                           "说明": "出件行数 %d 超过上限「%s」= %s（超限报错，不静默截断）"
                                   % (len(rows), row_limit, cap)})

    # ⑥ 渲染到**系统临时文件** → 回读 → 五条自检（含计数对账）→ 全过才落盘
    #    「不过不得出件」就落在这里：违规时临时文件被删、**落点上不存在任何文件**。
    #    主表与附表（说明与口径）**一体出件**：任一张不过 → 一张都不落。
    fmt = spec["格式"]
    extras = build_extra_tables(spec, ladder, rows, pool)
    tmp_dir = tempfile.mkdtemp(prefix="daniel-deliver-")
    committed, digest, fin_rows, fin_headers, n_back = None, None, [], headers, 0
    extra_committed, extra_facts = [], []
    pdf_facts, pdf_md_path, pdf_md_text, pdf_staged_md = None, None, None, None
    try:
        tmp_path = os.path.join(tmp_dir, "staged." + fmt.lower())
        try:
            blob, ext = render(fmt, headers, rows, title=spec["名称"])
        except (ValueError, OSError) as e:
            violations.append({"断言": "渲染", "行号": None, "列": None,
                               "说明": "出件渲染失败：%s" % e})
            blob, ext = b"", fmt.lower()
        if blob:
            with open(tmp_path, "wb") as fh:
                fh.write(blob)
            if fmt == "PDF":
                # PDF 是**文档型**出件：正文＝同一张表的 Markdown 文本（可复制版随件一起落）。
                # 「从文件里数行」这条对 PDF 不适用（抽回的文本无法可靠还原行列结构），
                # 故 ② 的对账改用**三条内容判据**：**字符多重集逐类相等**（缺字／多字／改字一个
                # 都跑不掉）＋ **逐行点名**（每一行首列值必须在 PDF 正文里按序逐字出现）＋
                # **逐格点名**（每格值都要在正文里逐字出现，长格由多重集覆盖）。
                # ⚠️「去空白逐字按序相等」**不是判据** —— 长表行被分页拆开时它就不成立，
                # 那时顺序由排版而非内容决定（CLS-04：判据要落在正确的对比面上）；它只作为
                # **事实**如实打印在 `交付件.PDF 保真.md↔PDF.逐字按序相等`，不判违规。
                # 三条内容判据皆过 ⇒ 行数成立（不是放宽，是换了一把更准的尺）。
                pdf_md_text = "# %s\n\n%s" % (spec["名称"],
                                              render("MD", headers, rows)[0].decode("utf-8"))
                pdf_staged_md = os.path.join(tmp_dir, "staged.md")
                with open(pdf_staged_md, "w", encoding="utf-8") as fh:
                    fh.write(pdf_md_text)
                pdf_facts = pdfout.verify(tmp_path, pdf_md_text, title=spec["名称"],
                                          headers=headers, rows=rows)
                violations += pdf_facts["违规"]
                # 行数由上面那三条内容判据推出（一字不多不少 ＋ 逐行点名 ⇒ 内容同一），
                # 不在 PDF 里数行：抽回的文本无法可靠还原行列结构，"数行"在这里是更弱也更脆的尺。
                back_headers, back_rows = headers, rows
            else:
                back_headers, back_rows = read_back(tmp_path, fmt)
        else:
            back_headers, back_rows = headers, []
        n_back = len(back_rows)
        if back_headers != headers:
            violations.append({"断言": "①全表闭合", "行号": None, "列": None,
                               "说明": "回读出的表头与声明不一致：%r ≠ %r"
                                       % (back_headers, headers)})

        # ② 的「文件行数」口径钉在**真实读出来的**临时文件上（不是内存里的 len(rows)）
        # ① 全表闭合：**候选池与出件表两侧都判** —— 池内记录缺必填列说明这条记录连判都
        #    判不了（静默丢掉它才是"假交"），出件表缺必填列则是"空壳交付"，两处都要报。
        violations += _closure_problems(projected, spec, "池内行号", only_fields=True)
        violations += selfcheck(rows, headers, spec, ctx, n_back)[0]
        recon = selfcheck(rows, headers, spec, ctx, n_back)[1]
        buckets = selfcheck(rows, headers, spec, ctx, n_back)[2]
        if n_back != len(rows):
            violations.append({"断言": "②计数对账", "行号": None, "列": None,
                               "说明": "主表行数 %d ≠ 出件文件回读行数 %d（落点不许有对不上的件）"
                                       % (len(rows), n_back)})

        # 附表（说明与口径）：同一套「渲染 → 回读 → 自检」工序
        staged = []
        for tab in extras:
            stage = os.path.join(tmp_dir, "extra-%d.%s" % (len(staged), tab["格式"].lower()))
            try:
                t_blob, t_ext = render(tab["格式"], tab["列"], tab["行"])
            except (ValueError, OSError) as e:
                violations.append({"断言": "附表渲染", "行号": None, "列": None,
                                   "说明": "附表《%s》渲染失败：%s" % (tab["名称"], e)})
                continue
            with open(stage, "wb") as fh:
                fh.write(t_blob)
            t_headers, t_rows = read_back(stage, tab["格式"])
            if t_headers != tab["列"]:
                violations.append({"断言": "附表①全表闭合", "行号": None, "列": None,
                                   "说明": "附表《%s》回读表头不一致" % tab["名称"]})
            if len(t_rows) != len(tab["行"]):
                violations.append({"断言": "附表②计数对账", "行号": None, "列": None,
                                   "说明": "附表《%s》主表 %d 行 ≠ 文件回读 %d 行"
                                           % (tab["名称"], len(tab["行"]), len(t_rows))})
            # 附表也过 ①④：逐格非空，且不许自造占位（与主表同一条纪律）
            for i, r in enumerate(tab["行"], 1):
                for col in tab["列"]:
                    v = r.get(col)
                    if _is_blank(v):
                        violations.append({"断言": "附表①全表闭合", "行号": i, "列": col,
                                           "说明": "附表《%s》第 %d 行「%s」为空（该表声明的"
                                                   "无数据写法是「%s」）"
                                                   % (tab["名称"], i, col, tab["无数据写法"])})
                    elif isinstance(v, str) and v.strip() in FAKE_PLACEHOLDERS:
                        violations.append({"断言": "附表④无空值", "行号": i, "列": col,
                                           "说明": "附表《%s》第 %d 行「%s」用了自造占位 %r"
                                                   % (tab["名称"], i, col, v)})
            tab.pop("计数对账", None)
            staged.append((tab, stage, t_ext, len(t_rows)))
        extras = [s[0] for s in staged]

        if not violations:
            target_dir = os.path.abspath(os.path.expanduser(str(out_dir))) if out_dir \
                else default_out_dir(contract_id)
            os.makedirs(target_dir, exist_ok=True)
            target = os.path.join(target_dir, "%s.%s" % (_safe_name(spec["文件名"]), ext))
            os.replace(tmp_path, target)
            committed = target
            if fmt == "PDF" and pdf_staged_md:
                # 「PDF＝印刷件／md＝可复制版」一起落：两件同一次提交，任一件对不上就一起撤。
                md_target = os.path.join(target_dir, "%s.md" % _safe_name(spec["文件名"]))
                os.replace(pdf_staged_md, md_target)
                pdf_md_path = md_target
                try:
                    with open(md_target, encoding="utf-8") as fh:
                        back_md = fh.read()
                except OSError as e:
                    back_md = ""
                    violations.append({"断言": "⑥PDF 保真·可复制版", "行号": None, "列": None,
                                       "说明": "可复制版 md 落定后读不回来：%s" % e})
                if back_md != pdf_md_text:
                    violations.append({"断言": "⑥PDF 保真·可复制版", "行号": None, "列": None,
                                       "说明": "可复制版 md 落定后与内存里那一份不一致（写后对账失败）"})
            for tab, stage, t_ext, _n in staged:
                t_target = os.path.join(target_dir, "%s.%s" % (_safe_name(tab["文件名"]), t_ext))
                os.replace(stage, t_target)
                extra_committed.append(t_target)
            # 写后对账（CLS-87）：落定后**再回读一次**，行数当场复算（报告里印实际值）
            with open(target, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            if fmt == "PDF":
                # 落定后**在落点的文件上重跑**那三条判据（不是拿临时件的结果充数）
                fin = pdfout.verify(target, pdf_md_text or "", title=spec["名称"],
                                    headers=headers, rows=rows)
                violations += fin["违规"]
                pdf_facts = fin["事实"]
                fin_headers, fin_rows = headers, (rows if not fin["违规"] else [])
            else:
                fin_headers, fin_rows = read_back(target, fmt)
            if len(fin_rows) != len(rows) or fin_headers != headers:
                violations.append({"断言": "②计数对账", "行号": None, "列": None,
                                   "说明": "落定后回读与预期不一致：文件 %d 行／内存 %d 行"
                                           % (len(fin_rows), len(rows))})
            for tab, path in zip(extras, extra_committed):
                t_headers, t_rows = read_back(path, tab["格式"])
                with open(path, "rb") as fh:
                    digest_t = hashlib.sha256(fh.read()).hexdigest()
                extra_facts.append({"名称": tab["名称"], "落点": path, "格式": tab["格式"],
                                    "行数": len(t_rows), "预期行数": len(tab["行"]),
                                    "列数": len(t_headers), "sha256": digest_t,
                                    "计数对账": "通过" if (len(t_rows) == len(tab["行"])
                                                        and t_headers == tab["列"]) else "不通过"})
                if len(t_rows) != len(tab["行"]) or t_headers != tab["列"]:
                    violations.append({"断言": "附表②计数对账", "行号": None, "列": None,
                                       "说明": "附表《%s》落定后回读与预期不一致" % tab["名称"]})
    finally:
        if os.path.isdir(tmp_dir):
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    if violations or not committed:
        for path in [committed, pdf_md_path] + extra_committed:  # 落定后才发现对不上 → 撤件
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
        committed, extra_committed, pdf_md_path = None, [], None
        base.update({
            "校验": "不通过：%s" % "；".join(v["说明"] for v in violations[:5]),
            "违规": violations, "违规数": len(violations),
            "阶梯": ladder, "关键桶": buckets, "计数对账": recon,
            "落点": None, "sha256": None, "产物": [],
            "明细": "出件自检未通过（%d 条违规）：**未产出任何文件**（落点上不存在本件）"
                    % len(violations),
        })
        return base
    base.update({
        "状态": model.ST_PASS, "校验": "通过", "违规": [], "违规数": 0,
        "路径": committed, "落点": committed, "文件名": os.path.basename(committed),
        "行数": len(rows), "数据": rows, "sha256": digest,
        "文件行数": len(fin_rows), "文件表头数": len(fin_headers),
        # 逐列计数事实（对账与关键桶都取这里，报告里也一眼能核）
        "非占位计数": ctx["交付件"]["非占位计数"],
        "占位计数": ctx["交付件"]["占位计数"],
        "去重计数": ctx["交付件"]["去重计数"],
        "产物": ([committed] + extra_committed + ([pdf_md_path] if pdf_md_path else [])),
        "附表": extra_facts,
        # 写后对账（CLS-87）：文件存在 ＋ 行数 == 预期 ＋ 列数 == 预期 ＋ 计数对账全过，
        # 且**印实际值**（不写"若干"）。
        "写后对账": {
            "落点": committed, "格式": fmt, "文件字节": os.path.getsize(committed),
            "文件行数（实际）": len(fin_rows), "预期行数": len(rows),
            "文件表头数（实际）": len(fin_headers), "预期列数": len(headers),
            "sha256": digest,
            "断言": "文件存在 且 文件行数 == 主表行数 且 表头 == 声明列",
            "成立": bool(len(fin_rows) == len(rows) and fin_headers == headers),
            "计数对账": recon,
        },
        "阶梯": ladder, "关键桶": buckets, "计数对账": recon,
        "出件自检": [
            {"断言": "①全表闭合", "通过": True, "说明": "全部 %d 行 × %d 列都有值"
                                                        % (len(rows), len(headers))},
            {"断言": "②计数对账", "通过": True,
             "说明": ("主表 %d 行 ＝ 文件回读 %d 行；入池 %d ≥ 出件 %d（差额 %d 已由阶梯逐级解释）"
                     % (len(rows), len(fin_rows), len(pool), len(rows), len(pool) - len(rows)))
                     if fmt != "PDF" else
                     ("PDF 是文档型出件：**不从 PDF 里数行**，改用**三条内容判据** —— ①正文 md↔PDF "
                      "去空白后**字符多重集逐类相等**（%s 字符，一字不多不少）②**逐行点名**"
                      "（%d 行的首列值在正文里按序逐字命中）③**逐格点名**（每格值都在正文里逐字"
                      "出现；长格 >200 字由 ① 覆盖、不逐格断言）；行数由这三条推出"
                      % ((pdf_facts or {}).get("md↔PDF", {}).get("md 去空白字符数"),
                         len(rows)))},
            {"断言": "③排序键单调", "通过": True,
             "说明": "；".join("%s %s" % (s.get("键"), s.get("方向")) for s in spec["排序"]) or "未声明"},
            {"断言": "④无空值", "通过": True,
             "说明": "除「%s」外无空值，且无自造占位；%d 列声明不得占位"
                     % (spec["无数据写法"], len(spec["不得占位列"]))},
            {"断言": "⑤关键桶非0", "通过": True,
             "说明": "；".join("%s=%s" % (b["桶"], b["实际"]) for b in buckets)},
        ] + ([{"断言": "⑥PDF 保真", "通过": True,
               "说明": "A4 页面 %d 页（实测 %.2f×%.2f pt，标准 %.2f×%.2f ±%.1f）｜叠字 0 处｜"
                       "md↔PDF 去空白**字符多重集逐类相等**（%d 字符，一字不多不少）＋逐行点名"
                       "%d 行全命中（按列「%s」）｜逐字按序相等：%s"
                       % ((pdf_facts or {}).get("页数"),
                          (((pdf_facts or {}).get("页面尺寸") or {}).get("每页") or [{}])[0].get("宽") or 0,
                          (((pdf_facts or {}).get("页面尺寸") or {}).get("每页") or [{}])[0].get("高") or 0,
                          pdfout.A4_W, pdfout.A4_H, pdfout.A4_TOL,
                          (pdf_facts or {}).get("md↔PDF", {}).get("md 去空白字符数"),
                          ((pdf_facts or {}).get("逐行点名") or {}).get("行数"),
                          ((pdf_facts or {}).get("逐行点名") or {}).get("按列"),
                          ("是" if (pdf_facts or {}).get("md↔PDF", {}).get("逐字按序相等")
                           else "否（分页把某一行拆开 ⇒ 抽取顺序在断点不同；多重集与长度都相等，"
                                "即没有少字、没有多字，首个不同位置见「PDF 保真.首个顺序差异」）"))}]
              if fmt == "PDF" else []),
        "明细": "按《%s》出件，%d 行 × %d 列，%s，落点 %s（sha256 %s）"
                % (spec["名称"], len(rows), len(headers), fmt, committed, digest[:12]),
    })
    if fmt == "PDF":
        base["PDF 保真"] = pdf_facts
        base["可复制版"] = {"路径": pdf_md_path, "格式": "MD",
                           "字节": (os.path.getsize(pdf_md_path)
                                    if pdf_md_path and os.path.exists(pdf_md_path) else None),
                           "说明": "文档类交付件的既定形态：PDF 用于签署／归档，md 用于复制与二次编辑"}
    return base


# ─────────────────────────── 附表：说明与口径 ───────────────────────────
#: 附表列固定（少一个变量）：项目／内容／条数／判据出处。
#: 为什么要有附表：Skill §15.5.5 判据1 要求交付件给"说明与口径"；§15.5.6 规则4 要求
#: **多口径梯度对照**（让需求方看到每一道门槛的代价）。生成器名即口径，逐条带 Skill 出处。
EXTRA_HEADERS = ("项目", "内容", "条数", "判据出处")
EXTRA_GENERATORS = ("梯度对照", "来源任务覆盖", "竞对名单真源")
#: 附表里"这一格不适用"的写法（附表同样不许留空壳）
EXTRA_NULL_TEXT = "不适用"


def build_extra_tables(spec, ladder, rows, pool):
    """按 `附表` 声明生成说明与口径表的行（纯函数；不写任何文件）。

    **附表同样不许留空壳**：不适用的格子（例：竞对名单成员的「条数」）一律写该表声明的
    `无数据写法`（缺省 `不适用`），与主表 ④ 同一条纪律 —— 空单元格与"没填"分不清，
    交付物里最容易被当成"漏了"。
    """
    tables = []
    for tab in spec["附表"]:
        if not isinstance(tab, dict):
            continue
        null_text = tab.get(model.D_NULL_TEXT) or EXTRA_NULL_TEXT
        body = []
        for gen in tab.get("生成") or []:
            if gen == "梯度对照":
                body.append(_extra_row(null_text, "候选池（行判据施加前）", "来源步骤产出的全部记录",
                                       len(pool), "本模板 `来源步骤`"))
                for l in ladder:
                    body.append(_extra_row(null_text, "门槛%s %s" % (l["序号"], l["判据"]),
                                           l["门槛"], l["保留条数"], l["判据出处"]))
                body.append(_extra_row(null_text, "出件", "全部门槛通过后实际出件", len(rows),
                                       "本模板 `计数对账`"))
            elif gen == "来源任务覆盖":
                counts = {}
                for r in rows:
                    counts[str(r.get("来源任务"))] = counts.get(str(r.get("来源任务")), 0) + 1
                for name, n in sorted(counts.items()):
                    body.append(_extra_row(null_text, "来源任务 %s" % name,
                                           "出件行按任务来源分布", n, "§15.5.6 规则3（行5235）"))
                body.append(_extra_row(null_text, "来源任务去重数",
                                       "品牌名任务与其 SKU 词任务必须合并成一个品牌池",
                                       len(counts), "§15.5.6 规则3（行5235）"))
            elif gen == "竞对名单真源":
                src = spec["_raw"].get("竞对名单真源") or {}
                body.append(_extra_row(null_text, "竞对名单真源", src.get("真源") or "未声明", None,
                                       src.get("出处") or ""))
                for name in src.get("名单") or []:
                    body.append(_extra_row(null_text, "竞对 %s" % name,
                                           "权威竞对名单成员（不自行收窄）", None,
                                           src.get("出处") or ""))
                if src.get("名单"):
                    body.append(_extra_row(null_text, "竞对名单条数", "与真源实测条数一致",
                                           len(src["名单"]), src.get("出处") or ""))
        for note in tab.get("附注") or []:
            vals = list(note) + [""] * len(EXTRA_HEADERS)
            body.append(_extra_row(null_text, *vals[:len(EXTRA_HEADERS)]))
        tables.append({
            "名称": tab.get("名称"), "文件名": tab.get("文件名"),
            "格式": tab.get("格式") or "CSV", "列": list(EXTRA_HEADERS), "行": body,
            "无数据写法": null_text,
        })
    return tables


def _extra_row(null_text, 项目, 内容, 条数, 判据出处):
    """一行附表：不适用的格子写 `null_text`（**不留空**）。"""
    def cell(v):
        return null_text if v is None or (isinstance(v, str) and not v.strip()) else str(v)
    return {"项目": cell(项目), "内容": cell(内容), "条数": cell(条数),
            "判据出处": cell(判据出处)}



def _closure_problems(rows, spec, label, only_fields=False):
    """① 全表闭合：每条记录都必须带齐必填列。

    为什么池侧也要判：一条记录缺了必填列（例如没有「表现评级」），后续门槛根本判不了它 ——
    静默把它丢掉，等于拿"没判过"冒充"不合格"（CLS-73 的教训正是自造判据顶替原生判据，
    这里再退一步就是连判据都没跑）。所以缺列就是违规，并点名是**第几行缺哪一列**。
    `only_fields=True`（池侧）：只判**来自产出字段**的列 —— 排名／点名位置这类生成列、
    以及由同行算出来的列，在池阶段本来就还没值。
    """
    out = []
    for i, r in enumerate(rows, 1):
        for c in spec["列"]:
            if not c.get("必填"):
                continue
            if only_fields and source_field(c)[0] != model.SRC_FIELD:
                continue
            if _is_blank(r.get(c["列名"])):
                out.append({"断言": "①全表闭合（候选池）", "行号": i, "列": c["列名"],
                            "说明": "%s %d 缺必填列「%s」（该记录无法参与判据，不得静默丢弃）"
                                    % (label, i, c["列名"])})
    return out


def _strip_source(row):
    row.pop("_源", None)
    return row


def _project(rows, spec):
    """按列来源把产出投影成出件表（字段／计算／模板／生成）。

    **两趟**：先字段与计算（`${模板}` 要用到它们），再模板与生成列。
    返回 `(行, 计算违规)`；每个投影行里留着 `_源`（原始产出记录），供点名判据取旁证。
    """
    out, problems = [], []
    tmpl_cols = [c for c in spec["列"] if source_field(c)[0] == model.SRC_TEMPLATE]
    for i, r in enumerate(rows, 1):
        row = {}
        for col in spec["列"]:
            name = col["列名"]
            kind, arg = source_field(col)
            if kind == model.SRC_FIELD:
                v = r.get(arg)
                row[name] = format_value(v, col.get("格式")) if not _is_blank(v) else None
            elif kind == model.SRC_COMPUTE:
                # 表达式按**列名**求值（与 `列` 的声明顺序一致：被引用列必须写在它前面）
                try:
                    row[name] = format_value(eval_formula(arg, row), col.get("格式"))
                except ValueError as e:
                    row[name] = None
                    problems.append({"断言": "列计算", "行号": i, "列": name,
                                     "说明": "第 %d 行「%s」计算失败：%s" % (i, name, e)})
            else:
                row[name] = None                      # 模板／生成列：第二趟或稍后填
        for col in tmpl_cols:
            name = col["列名"]
            text = str(source_field(col)[1])
            missing = [m for m in re.findall(r"\$\{([^}]+)\}", text)
                       if _is_blank(row.get(m))]
            if missing:
                problems.append({"断言": "列模板", "行号": i, "列": name,
                                 "说明": "第 %d 行「%s」拼接缺少列：%s" % (i, name, missing)})
                continue
            row[name] = re.sub(r"\$\{([^}]+)\}", lambda m: str(row.get(m.group(1))), text)
        row["_源"] = r
        out.append(row)
    return out, problems


def _sort_rows(rows, spec):
    sorts = [s for s in spec["排序"] if s.get("键")]
    for s in reversed(sorts):
        key, desc = s.get("键"), s.get("方向") == model.SORT_DESC
        rows.sort(key=lambda r: (_num_of(r.get(key)) is None,
                                 -(_num_of(r.get(key)) or 0) if desc else (_num_of(r.get(key)) or 0)),
                  reverse=False)
    return rows


def _generate_columns(rows, spec):
    for col in spec["列"]:
        kind, arg = source_field(col)
        if kind != model.SRC_GENERATE:
            continue
        name = col["列名"]
        if arg == model.GEN_RANK:
            for i, r in enumerate(rows, 1):
                r[name] = str(i)
        elif arg == model.GEN_MENTION:
            crit = None
            for c in spec["行判据"]:
                if c.get(model.CRC_RELATION) == model.REL_MENTION:
                    crit = c
                    break
            for i, r in enumerate(rows, 1):
                pos = _mention_position(r, crit) if crit else None
                r[name] = pos
    return rows


def _fill_nulls(rows, spec):
    """非必填列的空 → 按列声明的「无数据写法」（缺省用模板级写法）补齐 —— 不留空壳。"""
    for col in spec["列"]:
        if col.get("必填"):
            continue
        text = col.get("无数据写法") or spec["无数据写法"]
        name = col["列名"]
        for r in rows:
            if _is_blank(r.get(name)):
                r[name] = text
    return rows


def _bucket_counts(rows, headers, null_text, count_placeholder):
    out = {}
    for h in headers:
        n = 0
        for r in rows:
            v = r.get(h)
            if _is_blank(v):
                continue
            if (str(v).strip() == null_text) == bool(count_placeholder):
                n += 1
        out[h] = n
    return out


def _distinct_counts(rows, headers):
    out = {}
    for h in headers:
        out[h] = len({str(r.get(h)) for r in rows if not _is_blank(r.get(h))})
    return out
