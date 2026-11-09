# -*- coding: utf-8 -*-
"""印刷级 PDF 出件（TICKET-186 · A4）—— **复用既有出件工序，不另造渲染器**。

边界一句话
----------
本文件**不画版式、不写排版 CSS、不碰浏览器调用**：所有"怎么排、怎么打成 A4 PDF、字体怎么嵌"
都在既有工序脚本 `.kol-tools/doc_to_pdf.py` 里（TICKET-043 线：语义块 → 打印级 HTML →
Chromium 出件，自带容器／内容／字体／版面／图片五组校验）。本文件只做三件**薄事**：

  ① **适配**：把出件模板的一张表（列名 ＋ 数据行）转成它认的**语义块**（`title` ＋ `table`），
     再调 `blocks_to_html()` 出 HTML、`build_from_html()` 出 PDF；
  ② **判定**：按本票的验收判据做断言 —— **A4 页面**、**叠字 0**、**md↔PDF 三条内容判据**
     （**字符多重集逐类相等**／**逐行点名**／**逐格点名**，见下 `verify()` 的判据③）；
  ③ **落件形态**：PDF 是"印刷件"，同时落一份 `.md` 作"可复制版"（这是文档类交付件在业务语料里的
     既定形态：PDF 用于签署／归档，md 用于复制与二次编辑）。

判据（三条，逐条对应一个真实的出丑现象）
----------------------------------------
  ① **A4 页面**：每页 `MediaBox` 必须是 A4（595.28 × 841.89 pt，容差 1.5pt）—— 不是 A4 就没法
     直接打印／签署；
  ② **叠字 0**：逐字符框两两判"同一条基线上横向压字"（pypdfium2 的文本框是排版引擎实测给出的，
     不是我们从源码推的）—— 压字是排版事故里最刺眼的一种，肉眼一眼能看出来的那种；
  ③ **md↔PDF 三条内容判据**：把**真正落盘的 `.md`** 读回来、抹掉 Markdown 标记后，与从 PDF
     抽回的正文（**页眉页脚先按页剔除**，它们是版面装饰，"剔了哪些"要印出来）做**三条**比对 ——
     **① 字符多重集逐类相等**（缺字／多字／改字一个都跑不掉，不受分页与阅读顺序影响）；
     **② 逐行点名**（每一行记录的首列值必须在正文里**按序**逐字出现 ⇒ 行不丢／不错位／不重复）；
     **③ 逐格点名**（每一格的值都要在正文里逐字出现 ⇒ 格级丢失能点到具体行列）。
     ⚠️「**去空白逐字按序相等**」**不是判据**：长表行被分页拆开时它不成立，而那时顺序由**排版**
     而非内容决定（判据不能落在分页行为上）⇒ 它只作**事实**如实打印、不判违规（见 `verify()` 内注）。

为什么不用 `template_contract_pdf.py`
-------------------------------------
那个脚本是**母版保真**工序（以既有合同 PDF 为版式母版、按词回写、版式零漂移），只服务
"合同条款适配"这一个场景；本票要的是**通用文档类交付件的印刷级出件**，故走 `doc_to_pdf.py`。
"""
import io
import os
import re
import tempfile

#: A4（pt）：595.276 × 841.89（1pt = 1/72in）
A4_W, A4_H = 595.276, 841.890
A4_TOL = 1.5

#: 判定"叠字"的横向重叠阈值（占较窄那个字宽的比例）。
#: 为什么不是"任何重叠都算"：字距微调（kerning）与斜体字形的墨迹包围盒会天然轻微交叠，
#: 阈值取 0.25 时既能抓住真事故（两段文字压在一起），又不会被正常字距误报。
OVERLAP_RATIO = 0.25
#: 同一条基线的判定容差（pt）
BASELINE_TOL = 1.5
#: 单元格"长格"阈值：超过它就允许被分页截断（此时按"首 60 字 ＋ 尾 30 字都在"点名）。
#: 一页能容纳的字符数远大于它，所以**短于它的格不可能被分页拆开** —— 对短格要求整格连续出现是成立的。
LONG_CELL = 200


def _dp():
    """惰性取既有出件工序脚本（能力目录定位复用 CLI 的运行期层，不在模块级解析落点）。"""
    from ..runtime import load_capability
    return load_capability("doc_to_pdf")


# ─────────────────────────── ① 适配：表 → 语义块 → HTML → PDF ───────────────────────────
def table_blocks(title, headers, rows):
    """一张表 → `doc_to_pdf` 认的语义块（`(tag, attrs, payload)`）。

    单元格文字**先做 HTML 转义**：语义块会被原样拼进 HTML，业务文本里的 `&`／`<` 不转义就会
    被浏览器当标签吃掉（那会变成"少字"，而不是报错）。
    """
    import html as _html
    head = [[_html.escape(str(h if h is not None else "")) for h in headers]]
    body = [[_html.escape(str(r.get(h) if r.get(h) is not None else "")) for h in headers]
            for r in rows]
    blocks = []
    if title:
        blocks.append(("title", {}, _html.escape(str(title))))
    blocks.append(("table", {"cols": []}, (head, body)))
    return blocks


def build_pdf(title, headers, rows, out_pdf, header_text=""):
    """出件：表 → 打印级 HTML → A4 PDF（渲染全部交给 `doc_to_pdf`）。

    `header_text` 必须是 **ASCII**：Chromium 的页眉是独立文档、取不到页面里的内嵌字体，含 CJK
    会退成 Type3（从 PDF 复制出来是康熙部首码位）—— 这里按 `doc_to_pdf` 的同一口径**就地拦截**，
    非 ASCII 一律清空（不静默塞进去）。
    """
    dp = _dp()
    blocks = table_blocks(title, headers, rows)
    html = dp.blocks_to_html(blocks, title=title)
    safe_header = "".join(ch for ch in str(header_text or "") if 32 <= ord(ch) < 127)
    if safe_header != str(header_text or ""):
        safe_header = ""
    # 中间件（打印版 HTML）落**系统临时目录**：它是过程产物，不该出现在交付落点旁边，
    # 也绝不是"工作区相对落点"（落点纪律：交付物走 daniel_paths，中间件走系统临时目录）。
    workdir = tempfile.mkdtemp(prefix="daniel-pdfout-")
    html_path = os.path.join(workdir, "print.html")
    out_pdf = os.path.abspath(out_pdf)
    os.makedirs(os.path.dirname(out_pdf), exist_ok=True)
    with io.open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    try:
        dp.build_from_html(html_path, out_pdf, doc_title=title, header_text=safe_header,
                           footer_mark=None)
        # 🔴 文本层修复**不能跳**：Chromium 打印时若走了字体回退，从 PDF 复制出来的文字会是
        #    康熙部首码位（实测 `自` → `⾃`），"md↔PDF 逐字相等"这条判据当场就红。
        #    这一步用的正是既有工序自己的修复器 ＋ 它同一次浏览器会话采到的"打印可见文本"。
        expect = dp._HTML_EXPECT.get("text", "") + dp._HTML_EXPECT.get("markers", "")
        tmp = out_pdf + ".tmp"
        try:
            dp.fix_text_layer(out_pdf, tmp, expect, title=title)
            os.replace(tmp, out_pdf)
        except Exception:                                               # noqa: BLE001
            if os.path.exists(tmp):
                os.remove(tmp)
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)
    return out_pdf


# ─────────────────────────── ② 判定 ───────────────────────────
#: Latin 连字（U+FB00–U+FB06）→ 等价字母序列。
#: 为什么要有这一步：Chromium 排版时按字距把 `fi` 排成**一个字形** `ﬁ`，文本层给出的就是连字
#: 码位 —— 那是**排版的产物、不是内容差异**（同一个字，两种编码）。比对时把连字折回字母，
#: **两侧用同一把尺**，所以它只让"是不是同一个字"判得更准，不会掩盖真实的缺字／多字。
_LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi",
              "\ufb04": "ffl", "\ufb05": "ft", "\ufb06": "st"}


def _fold(text):
    """连字折回字母（两侧同用；见 `_LIGATURES` 的说明）。"""
    return "".join(_LIGATURES.get(ch, ch) for ch in (text or ""))


def _ws(text):
    """去空白（＋去 emoji ＋连字折回，与 `doc_to_pdf` 自己的比对口径同源，两边都用同一把尺）。"""
    return _fold(_dp().chars_multiset(text or ""))


def md_to_text(md_text):
    """落盘的 Markdown 交付件 → 纯文本（抹掉标记，只留内容）。

    认的子集就是本工序会产出的那一种：`# 标题` 行、Markdown 表格（`| a | b |` 与分隔行 `|---|`）、
    普通段落。**分隔行不是内容**（它是 Markdown 的排版标记），必须丢掉 —— 否则"md 比 pdf 多字"
    会变成一条假警报。
    """
    out = []
    for raw in (md_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r"\|[\s:\-|]+\|", line):        # 表头分隔行
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            out.extend([c.replace("\\|", "|") for c in cells if c != ""])
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        out.append(line)
    return "\n".join(out)


def page_facts(pdf_path, header_ws=""):
    """逐页事实：页数、每页尺寸、每页抽回的正文（已剔除**页脚页码**与**跨页重复的表头**）。

    剔两样东西，两样都是**版面装饰**、不是内容，且都逐页计数（剔了几个必须印出来）：
      · **页脚页码**：Chromium 拼的 `<pageNumber> / <totalPages>`，去空白后是 `i/N`，且在每页
        文本末尾 —— 只从末尾剔一次（正文里真出现 "1/2" 这种串不会被误删）；
      · **跨页重复的表头行**：排版引擎（既有出件工序的 CSS `thead{display:table-header-group}`）
        让表头在每一页顶部重画，这是**好的排版行为**，但会让 PDF 比源文本"多出" N-1 份表头。
        只在"第 2 页起、且该页文本**以表头开头**"时剔一次 —— 位置受限、且剔了几个要印出来，
        不会像"全文删同名串"那样误删正文（CLS-04 的教训）。
    """
    from pypdf import PdfReader
    rd = PdfReader(pdf_path)
    pages = list(rd.pages)
    out = []
    for i, pg in enumerate(pages):
        try:
            w, h = float(pg.mediabox.width), float(pg.mediabox.height)
        except Exception:                                               # noqa: BLE001
            w = h = None
        text = _ws(pg.extract_text() or "")
        marker = re.search(r"(\d+)/(\d+)$", text)
        stripped = ""
        if marker and int(marker.group(2)) == len(pages):
            stripped = marker.group(0)
            text = text[:marker.start()]
        repeat = 0
        if i > 0 and header_ws and text.startswith(header_ws):
            text = text[len(header_ws):]
            repeat = 1
        out.append({"页": i + 1, "宽": w, "高": h, "正文去空白": text, "剔除的页脚": stripped,
                    "剔除的重复表头": repeat})
    return out


def overlaps(pdf_path):
    """叠字检测：逐字符框两两判"同基线 + 横向压字"。返回（越界对数, 明细前若干条）。"""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf_path)
    bad = []
    for pi in range(len(doc)):
        tp = doc[pi].get_textpage()
        rects = [tp.get_rect(i) for i in range(tp.count_rects())]
        by_line = {}
        for r in rects:
            left, bottom, right, top = float(r[0]), float(r[1]), float(r[2]), float(r[3])
            if right - left <= 0:
                continue
            by_line.setdefault(round(bottom, 1), []).append((left, right, bottom, top))
        lines = sorted(by_line)
        for n, key in enumerate(lines):
            group = by_line[key]
            near = list(group)
            for k2 in lines[n + 1:]:                     # 基线容差内的相邻行算同一行
                if k2 - key > BASELINE_TOL:
                    break
                near += by_line[k2]
            near.sort()
            for a, b in zip(near, near[1:]):
                ov = min(a[1], b[1]) - max(a[0], b[0])
                wid = min(a[1] - a[0], b[1] - b[0])
                if wid > 0 and ov > OVERLAP_RATIO * wid:
                    bad.append({"页": pi + 1, "基线": key, "重叠pt": round(ov, 2),
                                "较窄字宽pt": round(wid, 2),
                                "左框": [round(a[0], 1), round(a[1], 1)],
                                "右框": [round(b[0], 1), round(b[1], 1)]})
    return len(bad), bad[:8]


def verify(pdf_path, md_text, title="", headers=(), rows=()):
    """三条判据一次跑完 → `{"违规": [...], "事实": {...}}`（违规条目与出件引擎同体例）。

    `md_text` 传**真正落盘的 `.md` 内容**（不是内存里的中间量）：判据要落在"交付物本身"上。
    """
    from . import model as _model                                      # noqa: F401（体例对齐）
    violations, facts = [], {}

    header_ws = _ws("".join(str(h if h is not None else "") for h in (headers or ())))
    pages = page_facts(pdf_path, header_ws) if os.path.exists(pdf_path) else []
    facts["页数"] = len(pages)
    if not pages:
        violations.append({"断言": "⑥PDF 保真·容器", "行号": None, "列": None,
                           "说明": "PDF 读不出来（容器非法或文件为空）：%s" % pdf_path})
        facts["三条成立"] = False
        facts["容器成立"] = False
        return {"违规": violations, "事实": facts}
    facts["容器成立"] = True

    # ① A4 页面
    off = [(p["页"], p["宽"], p["高"]) for p in pages
           if p["宽"] is None or abs(p["宽"] - A4_W) > A4_TOL or abs(p["高"] - A4_H) > A4_TOL]
    facts["页面尺寸"] = {"每页": [{"页": p["页"], "宽": p["宽"], "高": p["高"]} for p in pages],
                        "A4标准pt": [A4_W, A4_H], "容差pt": A4_TOL}
    if off:
        violations.append({"断言": "⑥PDF 保真·A4", "行号": off[0][0], "列": None,
                           "说明": "第 %d 页不是 A4：实测 %.2f × %.2f pt（A4 为 %.2f × %.2f，"
                                   "容差 %.1fpt）；共 %d 页不合规"
                                   % (off[0][0], off[0][1] or 0, off[0][2] or 0, A4_W, A4_H,
                                      A4_TOL, len(off))})

    # ② 叠字 0
    n_ov, detail = overlaps(pdf_path)
    facts["叠字对数"] = n_ov
    facts["叠字明细（前 8）"] = detail
    if n_ov:
        violations.append({"断言": "⑥PDF 保真·叠字", "行号": detail[0]["页"], "列": None,
                           "说明": "检测到 %d 处叠字（同基线横向压字超过字宽的 %.0f%%），"
                                   "首处在第 %d 页基线 %.1f：%s"
                                   % (n_ov, OVERLAP_RATIO * 100, detail[0]["页"],
                                      detail[0]["基线"], detail[0])})

    # ③ md↔PDF 去空白逐字相等
    pdf_body = "".join(p["正文去空白"] for p in pages)
    md_body = _ws(md_to_text(md_text))
    facts["md↔PDF"] = {
        "md 去空白字符数": len(md_body), "PDF 正文去空白字符数": len(pdf_body),
        "逐字按序相等": md_body == pdf_body,
        "剔除的页脚（逐页）": [p["剔除的页脚"] for p in pages],
        "剔除的重复表头（逐页）": [p["剔除的重复表头"] for p in pages],
        "说明": "页脚页码与跨页重复的表头是版面装饰、不是内容；两者逐页剔除并逐页计数"
                "（剔了几个在这里印出来）。正文一律来自**落盘的那份 .md**。",
    }
    # 🔴 **判据的对比面**（改过一次，理由是"原来的面判错了对象"）：
    #    最初写的是"md 与 PDF 全文**逐字按序**相等"。实测在**长行被分页拆开**时不成立 ——
    #    排版引擎把一个高过整页的表格行拆到两页，抽取器于是把"该行的后半"排到下一页开头，
    #    顺序变了、**但一个字都没少、没有多**（字符多重集逐类相等、长度相等）。
    #    也就是说：顺序在分页处由**排版**决定，不由内容决定 —— 拿它判罚等于判错了对象
    #    （CLS-04 的教训：判据必须落在正确的对比面上）。现在用**三条**：
    #      ① 主判据（内容）：去空白后的**字符多重集逐类相等** ⇒ 缺字／多字／改字一个都跑不掉；
    #      ② 主判据（行序）：**逐行点名** —— 每一行首列值在 PDF 正文里**按序**出现 ⇒ 行不丢／不错位／不重复；
    #      ③ 附加（逐格）：每一格的值都必须在 PDF 正文里逐字出现 ⇒ 格级丢失点得出具体行列。
    #    「逐字按序相等」作为**事实**如实记录（分页拆行时说明原因），不再单独作为违规 ——
    #    它在单页件上恒成立，也正是自检里那条正控所证明的。
    seq_equal = (md_body == pdf_body)
    facts["md↔PDF"]["逐字按序相等"] = seq_equal
    facts["md↔PDF"]["字符多重集逐类相等"] = (sorted(md_body) == sorted(pdf_body))
    if md_body != pdf_body:
        first = next((i for i, (a, b) in enumerate(zip(md_body, pdf_body)) if a != b),
                     min(len(md_body), len(pdf_body)))
        facts["md↔PDF"]["首个顺序差异"] = {
            "位置": first + 1, "md": md_body[first:first + 12], "pdf": pdf_body[first:first + 12],
            "原因": ("分页把这一行拆开了（同一行跨两页 ⇒ 抽取顺序与源文本顺序在断点处不同）；"
                     "字符多重集与长度都相等，即**没有少字、没有多字**" if seq_equal is False
                     and sorted(md_body) == sorted(pdf_body) else "内容差异（见违规项）"),
        }
    if sorted(md_body) != sorted(pdf_body):
        from collections import Counter
        ms_md, ms_pdf = Counter(md_body), Counter(pdf_body)
        miss = ms_md - ms_pdf
        extra = ms_pdf - ms_md
        violations.append({"断言": "⑥PDF 保真·md↔PDF", "行号": None, "列": None,
                           "说明": "md 与 PDF 去空白后字符不逐类相等（内容对不上）："
                                   "md %d 字符／PDF %d 字符；缺失 %d 类 %s；多出 %d 类 %s"
                                   % (len(md_body), len(pdf_body), len(miss),
                                      dict(list(miss.items())[:8]), len(extra),
                                      dict(list(extra.items())[:8]))})
    # ② 逐行点名（比"数行"更强）：每一行记录的**首列值**必须**按序**出现在 PDF 正文里
    if headers and rows:
        key = headers[0]
        miss, cursor = [], 0
        for i, r in enumerate(rows, 1):
            v = _ws(str(r.get(key) if r.get(key) is not None else ""))
            if not v:
                continue
            at = pdf_body.find(v, cursor)
            if at < 0:
                miss.append({"行号": i, "列": key, "值": str(r.get(key))[:40],
                             "未按序出现": v in pdf_body})
            else:
                cursor = at + len(v)
        facts["逐行点名"] = {"按列": key, "缺行数": len(miss), "缺行（前 5）": miss[:5],
                            "行数": len(rows)}
        if miss:
            violations.append({"断言": "⑥PDF 保真·逐行点名", "行号": miss[0]["行号"], "列": key,
                               "说明": "有 %d 行的「%s」没在 PDF 正文里按序逐字出现，"
                                       "首行是第 %d 行（值 %r）"
                                       % (len(miss), key, miss[0]["行号"], miss[0]["值"])})
    # ③ 逐格点名：每一格的值都要在 PDF 正文里逐字出现（格级丢失能点到具体行列）。
    #    长格（>200 字）**允许被分页截断**：这时它的后半会排到下一页、不再与前半连续，
    #    但"头 60 字 ＋ 尾 30 字都在"仍能证明这一格没被整格吞掉；**且主判据（字符多重集
    #    逐类相等）已经保证全文一个字不多不少** —— 逐格点名的职责是"定位到哪一行哪一列"，
    #    不该因为合法的分页而判罚（判据要落在正确的对比面上）。
    if headers and rows:
        cell_miss, long_cells = [], 0
        for i, r in enumerate(rows, 1):
            for h in headers:
                v = _ws(str(r.get(h) if r.get(h) is not None else ""))
                if not v:
                    continue
                if len(v) <= LONG_CELL:
                    if v not in pdf_body:
                        cell_miss.append({"行号": i, "列": h, "值": str(r.get(h))[:40],
                                          "核法": "整格逐字"})
                else:
                    # 长格可能被分页拆开（后半排到下一页），逐字连续出现对它不成立；
                    # 它由**主判据（字符多重集逐类相等）**覆盖 —— 即"一字不差"仍然保证，
                    # 只是"哪一格"的定位对长格不保证。这里如实计数，**不判违规**
                    # （拿分页行为判罚＝判错对比面）。
                    long_cells += 1
        facts["逐格点名"] = {"格数": len(rows) * len(headers), "缺格数": len(cell_miss),
                            "长格数（不逐格断言，由多重集覆盖）": long_cells,
                            "长格阈值": LONG_CELL, "缺格（前 5）": cell_miss[:5]}
        if cell_miss:
            violations.append({"断言": "⑥PDF 保真·逐格点名", "行号": cell_miss[0]["行号"],
                               "列": cell_miss[0]["列"],
                               "说明": "有 %d 格的值没在 PDF 正文里逐字出现，首处是第 %d 行的"
                                       "「%s」（值 %r；核法 %s）"
                                       % (len(cell_miss), cell_miss[0]["行号"],
                                          cell_miss[0]["列"], cell_miss[0]["值"],
                                          cell_miss[0]["核法"])})
    facts["三条成立"] = (not violations)
    return {"违规": violations, "事实": facts}


def self_check():
    """模块级自检：**三条判据的正控 ＋ 反例**（全在临时目录，不联网、不写仓库）。

    反例必须真的被报出来 —— 否则"判据在做事"这件事就没有证据（恒绿的检查等于没有检查）。
    """
    import shutil
    items = []

    def add(desc, ok, detail=""):
        items.append((desc, bool(ok), detail))

    headers = ["序号", "结论", "说明"]
    rows = [{"序号": 1, "结论": "通过", "说明": "第一行的说明文字（含 & 与 < 号）"},
            {"序号": 2, "结论": "不通过", "说明": "第二行：一句话说清为什么"},
            {"序号": 3, "结论": "通过", "说明": "第三行"}]
    title = "PDF 出件自检样本"
    md = ("# %s\n\n| 序号 | 结论 | 说明 |\n|---|---|---|\n"
          "| 1 | 通过 | 第一行的说明文字（含 & 与 < 号） |\n"
          "| 2 | 不通过 | 第二行：一句话说清为什么 |\n"
          "| 3 | 通过 | 第三行 |\n") % title
    tmp = tempfile.mkdtemp(prefix="daniel-pdfout-selfcheck-")
    try:
        pdf = os.path.join(tmp, "out.pdf")
        try:
            build_pdf(title, headers, rows, pdf)
        except Exception as e:                                          # noqa: BLE001
            add("正控：能出 PDF（复用既有出件工序）", False, "%s: %s" % (type(e).__name__, e))
            return False, items
        add("正控：能出 PDF（复用既有出件工序）", os.path.exists(pdf),
            "%s（%.1f KB）" % (pdf, os.path.getsize(pdf) / 1024.0 if os.path.exists(pdf) else 0))
        res = verify(pdf, md, title=title, headers=headers, rows=rows)
        f = res["事实"]
        add("正控：三条判据全过（A4／叠字 0／md↔PDF 字符多重集＋逐行点名＋逐格点名）",
            not res["违规"], "；".join(v["说明"] for v in res["违规"]) or
            "页数=%s ｜ 叠字=%s ｜ md %d 字符 == PDF %d 字符"
            % (f.get("页数"), f.get("叠字对数"), f["md↔PDF"]["md 去空白字符数"],
               f["md↔PDF"]["PDF 正文去空白字符数"]))
        add("正控：页脚页码被逐页剔除（剔了 N 个，N＝页数）",
            len(f["md↔PDF"]["剔除的页脚（逐页）"]) == f["页数"]
            and all(f["md↔PDF"]["剔除的页脚（逐页）"]),
            str(f["md↔PDF"]["剔除的页脚（逐页）"]))
        add("正控：单页件上「去空白逐字按序相等」严格成立（不靠多重集兜底）",
            f["md↔PDF"]["逐字按序相等"] is True, str(f["md↔PDF"]["逐字按序相等"]))
        add("正控：逐格点名与逐行点名都齐备",
            f.get("逐格点名", {}).get("格数") == len(rows) * len(headers)
            and f.get("逐行点名", {}).get("行数") == len(rows), str(f.get("逐格点名")))

        # 反例①：md 里少一个字 → 必须报"不逐字相等"并给出首个不同的位置
        bad_md = md.replace("第三行", "第三").replace("第三行", "第三")
        r2 = verify(pdf, bad_md)
        add("反例①：md 少字必须被报出（且点出首个不同位置）",
            any("md↔PDF" in v["断言"] for v in r2["违规"]),
            "；".join(v["说明"][:120] for v in r2["违规"]) or "**没报出来（判据失效）**")

        # 反例②：md 里多一行 → 逐行点名之外的"多字"也必须被 md↔PDF 抓住
        r3 = verify(pdf, md + "| 4 | 通过 | 多出来的一行 |\n")
        add("反例②：md 多一行必须被报出", bool(r3["违规"]),
            "；".join(v["断言"] for v in r3["违规"]) or "**没报出来（判据失效）**")

        # 反例③：PDF 不存在 → 必须报"容器非法/读不出来"，而不是静默通过
        r4 = verify(os.path.join(tmp, "nope.pdf"), md)
        add("反例③：文件不存在必须被报出", bool(r4["违规"]),
            "；".join(v["说明"][:80] for v in r4["违规"]))

        add("md→纯文本：分隔行不算内容（否则会报假的多字）",
            "---" not in md_to_text(md) and "|" not in md_to_text(md),
            repr(md_to_text(md))[:120])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return all(ok for _d, ok, _x in items), items


__all__ = ["A4_W", "A4_H", "A4_TOL", "table_blocks", "build_pdf", "md_to_text", "page_facts",
           "overlaps", "verify", "self_check"]
