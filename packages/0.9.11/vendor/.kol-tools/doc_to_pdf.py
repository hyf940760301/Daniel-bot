#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
doc_to_pdf.py —— 飞书云文档（DocxXML）→ 印刷级 PDF（v0.9.92 · 2026-09-28 首建）

**要解决的问题**：把飞书云文档做成"能直接发出去"的 PDF。飞书自带的导出排版朴素（正文与标题层级、
表格边框、callout 都按网页默认样式渲染），而对外交付件要求 **A4 版面 ＋ 中文正文排版 ＋ 表头/页码 ＋
分页控制（标题不落页尾、表行不被切断）**。

**流水线（三段，职责分离）**
  ① **解析**：飞书 `docs +fetch --doc-format xml --detail full` 的 DocxXML → 语义块（title／p／callout／
     h1／h2／ul／ol／table／b）；
  ② **排版**：语义块 → 印刷级 HTML（A4 `@page` ＋ 中文字体栈 ＋ 表格/引用框/列表样式 ＋ 分页规则）；
  ③ **出件**：Chromium（Playwright 内核）打印为 PDF —— 页眉页脚与"第 X 页 / 共 Y 页"由浏览器生成。

**为什么用 Chromium 而不是自绘**：本合同类交付件的自绘 PDF（`template_contract_pdf.py`）是为了**母版保真**；
而本文档类交付件要的是**中文排版质量**（字体回退／断行／避头尾／表格自适应），浏览器引擎在这件事上最稳，
且**字体子集会被嵌入**（离线可读、不依赖收件人装字体）。

**判据（硬）**
  ① **内容保真**：源文档正文文本的**字符多重集**必须等于 PDF 抽回文本的字符多重集（去空白）——
     抓增字/漏字/错字，且不受分页与阅读顺序影响（与 Skill §2.2.14 同源）；
  ② **容器合法**：PDF 必须能被标准阅读器打开（`pypdf` 读页数 ＋ `pypdfium2` 渲染成图不报错）；
  ③ **可读性**：分页处不得出现"标题落单在页尾"或"表头与首行分离"（由 CSS 的 `break-*` 规则保证，
     并在 `--verify-shots` 出图后人工复核）。

用法：
  # 出件（XML 由 `lark-cli docs +fetch --doc-format xml --detail full` 得到）
  python3 .kol-tools/doc_to_pdf.py --xml <doc.xml> --out <out.pdf> [--html-out <out.html>] [--footer-note 文本]
  # 自检（纯逻辑，不起浏览器）
  python3 .kol-tools/doc_to_pdf.py --self-test
退出码 0 ＝ 成功；1 ＝ 内容保真或容器校验失败（**不得交付**）。
"""
import argparse
import html as _html
import io
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 字体栈（2026-09-28 实测后定版）─────────────────────────────────────────────
# 🔴 为什么不直接用苹方：Chromium 导出 PDF 时对 **TTC 字体集合**（PingFang.ttc／Songti.ttc／
#    Hiragino Sans GB.ttc／STHeiti.ttc）走 Type3 轮廓回退，实测后果两条：
#      ① 字体不是"嵌入子集"而是 Type3 过程（渲染没错，但体积大、语义弱）；
#      ② **从 PDF 复制出来的文字是康熙部首码位**（`用`→`⽤`、`行`→`⾏`、`页`→`⻚`）——
#         搜索/粘贴/二次加工全坏（实测 pypdf 抽取：CJK 部首 38 类、约 100 处）。
#    改用**真 TTF**（Noto Sans SC 可变字重；兜底 Arial Unicode MS）后：CIDFontType2 ＋ FontFile2
#    真子集嵌入，且抽取回来的就是标准汉字。**判据：交付前必须用"字符多重集"比对源文与 PDF 抽取文本。**
FONT_FACE = ("@font-face { font-family: 'DocCJK'; font-weight: 400; "
             "src: url('%s') format('truetype'); }\n"
             "@font-face { font-family: 'DocCJK'; font-weight: 700; "
             "src: url('%s') format('truetype'); }")
FONTS_DIR = os.path.join(ROOT, '.kol-tools', 'assets', 'fonts')
FONT_REGULAR = os.path.join(FONTS_DIR, 'NotoSansSC-Regular.ttf')
FONT_BOLD = os.path.join(FONTS_DIR, 'NotoSansSC-Bold.ttf')
FONT_STACK = ("'DocCJK', 'Arial Unicode MS', 'Hiragino Sans GB', 'PingFang SC', "
              "'Microsoft YaHei', sans-serif")


# ── 版面常量 ──────────────────────────────────────────────────────────────
FURN_LO = 42.0              # 页眉/页脚带（pt）：正文只在这两条线之间判版面
ACCENT = '#2B5CE6'          # 主强调色（标题竖条 / 列表符号 / 页码）
INK = '#1F2329'             # 正文墨色
INK_SOFT = '#4E5969'        # 次级文字
RULE = '#E5E6EB'            # 分隔线
ZEBRA = '#FAFBFC'           # 表格斑马纹
MONO_STACK = '"SF Mono", Menlo, Consolas, "Noto Sans SC", monospace'


def font_face_css(regular=None, bold=None):
    """生成 @font-face（本地 file:// 静态 TTF；Chromium 用 `--allow-file-access-from-files` 读本地字体）。

    🔴 只能用**静态 glyf TTF**：实测（2026-09-28）
      - 可变字体（Noto Sans SC VF，truetype-variations）→ Chromium 退成 **Type3 轮廓**（复制出的文字是部首码位）；
      - CFF/OTF（NotoSansSC-Regular.otf）→ **Type3**；
      - 系统 TTC（PingFang／Songti／Hiragino／Heiti）→ **Type3**；
      - **静态 glyf TTF** → Type0 ＋ FontFile2 **真子集嵌入** ✓。
    静态 TTF 由 VF 现场 instance 得到（`fontTools.varLib.instancer`，见 assets/fonts/README.md）。
    """
    r = regular or FONT_REGULAR
    b = bold or FONT_BOLD
    if os.path.exists(r) and os.path.exists(b):
        return FONT_FACE % ('file://%s' % os.path.abspath(r), 'file://%s' % os.path.abspath(b))
    return ''


def print_css(footer_note='', font_face=''):
    """印刷级 CSS：A4 版面 / 字号层级 / 表格 / 引用框 / 分页规则。"""
    return (font_face or '') + """
@page { size: A4 portrait; margin: 17mm 16mm 16mm 16mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; color: %(INK)s; background: #fff;
       font-family: %(FONT)s; font-size: 10.5pt; line-height: 1.9;
       text-align: justify; text-justify: inter-ideograph;
       -webkit-font-smoothing: antialiased; }
article.doc { max-width: 100%%; }

/* ── 文档标题区 ── */
h1.doc-title { font-size: 20pt; line-height: 1.45; font-weight: 700; letter-spacing: .2px;
       margin: 0 0 4mm; padding: 0 0 3mm; border-bottom: 2.5px solid %(ACCENT)s;
       break-after: avoid; }
p.lead { font-size: 11pt; color: %(INK_SOFT)s; margin: 0 0 5mm; line-height: 1.85;
       padding-left: 3mm; border-left: 3px solid %(RULE)s; break-after: avoid; }

/* ── 章节层级：正文 h1→h2.sec，正文 h2→h3.sub ── */
h2.sec { font-size: 14.5pt; font-weight: 700; line-height: 1.5; margin: 8mm 0 3mm;
       padding: 1.6mm 0 1.6mm 3.2mm; border-left: 4px solid %(ACCENT)s;
       background: linear-gradient(90deg, rgba(43,92,230,.055), rgba(43,92,230,0)); }
h3.sub { font-size: 11.5pt; font-weight: 700; color: #111827; margin: 5mm 0 2mm;
       padding-left: 3.2mm; position: relative; }
/* 🔴 标题不许落在页尾：Chromium **不支持** `break-after: avoid`（实测两处标题仍落页尾）⇒
   改用"标题 ＋ 紧随块"包一层 `.keep`（`break-inside: avoid` 是 Chromium 支持的），
   由生成器在产出 HTML 时自动成组，而不是靠 CSS 的 avoid 语义。 */
.keep { break-inside: avoid; page-break-inside: avoid; }
.keep > h2.sec, .keep > h3.sub { margin-bottom: 2mm; }
h2.sec, h3.sub { break-after: avoid; page-break-after: avoid; }
h3.sub::before { content: ""; position: absolute; left: 0; top: .52em; width: 1.5mm;
       height: 1.5mm; border-radius: 50%%; background: %(ACCENT)s; }

/* ── 正文段落 ── */
p { margin: 0 0 3.2mm; orphans: 2; widows: 2; }
p:last-child { margin-bottom: 0; }
strong, b { font-weight: 700; }
code { font-family: %(MONO)s; font-size: .92em; background: #F5F6F7;
       border: 1px solid %(RULE)s; border-radius: 3px; padding: 0 3px; }
a { color: %(ACCENT)s; text-decoration: none; border-bottom: 1px solid rgba(43,92,230,.35); }

/* 「对应图表：…」这类提示行 —— 只加一条左侧细线把"图表锚点"与正文分开（不加内容） */
p.chart-note { font-size: 10pt; color: %(INK_SOFT)s; margin: 0 0 4mm; padding: 0 0 0 3mm;
       border-left: 2px solid #C9CDD4; break-after: avoid; }
p.chart-note strong { color: %(INK)s; }

/* ── 引用框（callout：沿用文档自带底色/描边色，只改圆角与内边距）── */
div.callout { display: flex; gap: 3mm; align-items: flex-start; margin: 0 0 5mm;
       padding: 3.4mm 4mm; border-radius: 2mm; border: 1px solid var(--co-border, #82A7FC);
       border-left-width: 2.5px; background: var(--co-bg, #F0F4FF); break-inside: avoid; }
div.callout div.co-body { flex: 1 1 auto; }
div.callout div.co-body > p:last-child { margin-bottom: 0; }
span.co-emoji { font-size: 12pt; line-height: 1.5; }

/* ── 列表 ── */
ul, ol { margin: 1mm 0 3.6mm; padding-left: 6.4mm; }
li { margin: 0 0 1.6mm; padding-left: .6mm; }
li::marker { color: %(ACCENT)s; font-weight: 700; }
ul { list-style: none; padding-left: 5.6mm; }
ul > li { position: relative; }
ul > li::before { content: ""; position: absolute; left: -4mm; top: .62em; width: 1.4mm;
       height: 1.4mm; border-radius: 50%%; background: %(ACCENT)s; }
ul ul > li::before { background: #A9B4C0; }
ol { list-style: decimal; }
ol > li::marker { font-weight: 700; }

/* ── 表格 ── */
table { width: 100%%; border-collapse: collapse; table-layout: fixed;
       margin: 2mm 0 5mm; font-size: 10pt; line-height: 1.72; text-align: left;
       break-inside: auto; }
thead { display: table-header-group; }   /* 跨页时表头自动重复 */
tr { break-inside: avoid; }
th, td { border: 1px solid %(RULE)s; padding: 2.4mm 3mm; vertical-align: top;
       word-break: break-word; text-align: left; }
th { background: #F5F6F7; font-weight: 700; color: #111827; }
tbody tr:nth-child(even) td { background: %(ZEBRA)s; }
table p { margin: 0; }

/* ── 分页与页面装饰由浏览器页眉页脚模板负责（见 build_pdf）── */
""" % {'INK': INK, 'INK_SOFT': INK_SOFT, 'ACCENT': ACCENT, 'RULE': RULE,
       'ZEBRA': ZEBRA, 'FONT': FONT_STACK, 'MONO': MONO_STACK}


# ─────────────────────────────────────────────────────────────────────────────
# ① DocxXML → 语义块
# ─────────────────────────────────────────────────────────────────────────────
def parse_docx_xml(xml_text):
    """把飞书 DocxXML 解析成 [(tag, attrs, children/str)] 的**扁平语义块**列表。

    只认结构、不做取舍：未知标签**保留其子节点**并把标签名记入 `unknown`（供回报），
    避免"不认识就静默丢内容"（CLS-11：内容增删静默不可见）。
    """
    src = '<root>%s</root>' % (xml_text or '')
    try:
        root = ET.fromstring(src)
    except ET.ParseError as ex:                     # 退化输入：非法 XML 必须报错而不是吞掉
        raise ValueError('DocxXML 解析失败：%s' % ex)
    unknown = []

    def inline(node):
        """行内序列 → HTML 片段（b→strong，a 保留链接，其余按文本处理）。"""
        out = []
        if node.text:
            out.append(_html.escape(node.text))
        for ch in list(node):
            if ch.tag == 'b':
                out.append('<strong>%s</strong>' % inline(ch))
            elif ch.tag == 'a':
                href = _html.escape(ch.get('href', ''), quote=True)
                out.append('<a href="%s">%s</a>' % (href, inline(ch)))
            elif ch.tag == 'code':
                out.append('<code>%s</code>' % inline(ch))
            elif ch.tag in ('br',):
                out.append('<br/>')
            else:
                if ch.tag not in unknown:
                    unknown.append(ch.tag)
                out.append(inline(ch))          # 未知行内标签：保留文本
            if ch.tail:
                out.append(_html.escape(ch.tail))
        return ''.join(out)

    def cell_html(cell):
        """表格单元格：把内部 <p> 合并为单元格内容（多段则各自成段）。"""
        ps = [inline(p) for p in cell.findall('p')]
        ps = [p for p in ps if p.strip()]
        if not ps:
            return inline(cell)
        if len(ps) == 1:
            return ps[0]
        return ''.join('<p>%s</p>' % p for p in ps)

    blocks = []
    for node in list(root):
        tag = node.tag
        if tag in ('title',):
            blocks.append(('title', {}, inline(node)))
        elif tag == 'p':
            txt = inline(node)
            blocks.append(('p', {}, txt))
        elif tag == 'callout':
            blocks.append(('callout',
                           {'bg': node.get('background-color', ''),
                            'border': node.get('border-color', ''),
                            'emoji': node.get('emoji', '')},
                           [('p', {}, inline(p)) for p in node.findall('p')]))
        elif tag in ('h1', 'h2', 'h3'):
            blocks.append((tag, {}, inline(node)))
        elif tag in ('ul', 'ol'):
            items = []
            for li in node.findall('li'):
                items.append(inline(li))
            blocks.append((tag, {}, items))
        elif tag == 'table':
            cols = []
            cg = node.find('colgroup')
            if cg is not None:
                for c in cg.findall('col'):
                    try:
                        cols.append(int(c.get('width', '0') or 0))
                    except ValueError:
                        cols.append(0)
            head, body = [], []
            th = node.find('thead')
            if th is not None:
                for tr in th.findall('tr'):
                    head.append([cell_html(td) for td in tr.findall('th')])
            tb = node.find('tbody')
            if tb is not None:
                for tr in tb.findall('tr'):
                    body.append([cell_html(td) for td in tr.findall('td')])
            blocks.append(('table', {'cols': cols}, (head, body)))
        elif tag in ('img', 'source', 'whiteboard', 'sheet', 'bitable', 'synced_reference'):
            if tag not in unknown:
                unknown.append(tag)
            blocks.append(('unsupported', {'tag': tag}, ''))
        else:
            if tag not in unknown:
                unknown.append(tag)
            txt = inline(node).strip()
            if txt:
                blocks.append(('p', {}, txt))
    return blocks, unknown


# ─────────────────────────────────────────────────────────────────────────────
# ② 语义块 → 印刷级 HTML
# ─────────────────────────────────────────────────────────────────────────────
def blocks_to_html(blocks, title='', footer_note='', cjk_font_file=None):
    """语义块 → 印刷级 HTML。

    两处**工序性**设计（不是样式偏好）：
      ① **字体**：内嵌真 TTF（`@font-face`）而不是依赖系统 TTC —— 否则 Chromium 会退成 Type3 且
         复制出来的文字是康熙部首（见 FONT_STACK 注释）；
      ② **标题成组**：标题与其**紧随的段落/引用框**包进 `.keep`，靠 `break-inside: avoid` 防"标题落页尾"
         （Chromium 不支持 `break-after: avoid`，实测两处标题仍落在页尾）。
    """
    font_face = font_face_css(cjk_font_file) if cjk_font_file else font_face_css()
    out, first_p_done = [], False

    def p_html(tag, payload):
        nonlocal first_p_done
        if not str(payload).strip():
            return ''
        cls = ''
        if not first_p_done:
            cls, first_p_done = ' class="lead"', True
        if re.match(r'^\s*<strong>[^<]{0,8}图表[^<]{0,4}</strong>', str(payload)):
            cls = ' class="chart-note"'
        return '<p%s>%s</p>' % (cls, payload)

    def callout_html(attrs, payload):
        style = []
        if attrs.get('bg'):
            style.append('--co-bg:%s' % attrs['bg'])
        if attrs.get('border'):
            style.append('--co-border:%s' % attrs['border'])
        emoji = attrs.get('emoji') or ''
        inner = ''.join('<p>%s</p>' % p for _t, _a, p in payload if str(p).strip())
        return '<div class="callout"%s>%s<div class="co-body">%s</div></div>' % (
            ' style="%s"' % ';'.join(style) if style else '',
            ('<span class="co-emoji">%s</span>' % _html.escape(emoji)) if emoji else '', inner)

    i = 0
    while i < len(blocks):
        tag, attrs, payload = blocks[i]
        if tag == 'title':
            out.append('<h1 class="doc-title">%s</h1>' % payload)
        elif tag == 'p':
            out.append(p_html(tag, payload))
        elif tag == 'callout':
            out.append(callout_html(attrs, payload))
        elif tag in ('h1', 'h2', 'h3'):
            head = ('<h2 class="sec">%s</h2>' % payload if tag == 'h1'
                    else '<h3 class="sub">%s</h3>' % payload)
            nxt = blocks[i + 1] if i + 1 < len(blocks) else None
            nxt_html = ''
            if nxt is not None and nxt[0] == 'p':
                nxt_html = p_html(nxt[0], nxt[2])
            elif nxt is not None and nxt[0] == 'callout':
                nxt_html = callout_html(nxt[1], nxt[2])
            if nxt_html:
                out.append('<div class="keep">%s%s</div>' % (head, nxt_html))
                i += 2
                continue
            out.append(head)
        elif tag in ('ul', 'ol'):
            lis = ''.join('<li>%s</li>' % it for it in payload if str(it).strip())
            out.append('<%s>%s</%s>' % (tag, lis, tag))
        elif tag == 'table':
            head_rows, body = payload
            cols = attrs.get('cols') or []
            cg = ''
            if cols and sum(cols) > 0:
                pct = [max(8.0, 100.0 * c / float(sum(cols))) for c in cols]
                scale = 100.0 / sum(pct)
                cg = '<colgroup>%s</colgroup>' % ''.join(
                    '<col style="width:%.3f%%"/>' % (x * scale) for x in pct)
            head_html = ''
            if head_rows:
                head_html = '<thead>%s</thead>' % ''.join(
                    '<tr>%s</tr>' % ''.join('<th>%s</th>' % c for c in row) for row in head_rows)
            body_html = ''
            if body:
                body_html = '<tbody>%s</tbody>' % ''.join(
                    '<tr>%s</tr>' % ''.join('<td>%s</td>' % c for c in row) for row in body)
            out.append('<table>%s%s%s</table>' % (cg, head_html, body_html))
        elif tag == 'unsupported':
            out.append('<!-- 未支持的块：%s（内容未渲染，必须在回报中声明）-->' % attrs.get('tag', '?'))
        i += 1
    return ('<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8"/>\n'
            '<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n<article class="doc">\n%s\n'
            '</article>\n</body>\n</html>\n'
            % (_html.escape(title or ''), print_css(footer_note, font_face), '\n'.join(out)))


# ─────────────────────────────────────────────────────────────────────────────
# ③ HTML → PDF（Chromium via Playwright）
# ─────────────────────────────────────────────────────────────────────────────
_HTML_EXPECT = {}


def build_from_html(html_path, pdf_path, doc_title='', header_text='', footer_mark=None):
    """HTML → 印刷级 PDF（并在同一趟浏览器会话里采集"打印可见文本 / 标题 / CSS 标记"）。

    **为什么要一趟**：① 内容保真的对比对象必须是**打印时真正可见的文本**（屏幕上的侧栏目录在
    `@media print` 里 `display:none`，不算内容）；② CSS counter 生成的编号（`.steps`、`<ol>`）
    会出现在 PDF 里但不在 HTML 源码里，必须一并计入"期望侧"；③ 只启动一次 Chromium，快且口径一致。
    返回 (pdf_path, expect_text, headings, header_text)。
    """
    js = _playwright()
    exe = find_chromium()
    if not (js and exe):
        raise RuntimeError('找不到 Chromium 或 playwright-core')
    script = r'''
const { chromium } = require(%(JS)s);
(async () => {
  const browser = await chromium.launch({ executablePath: %(EXE)s, headless: true,
      args: ['--allow-file-access-from-files', '--font-render-hinting=none'] });
  const page = await browser.newPage();
  await page.goto('file://' + %(HTML)s, { waitUntil: 'load' });
  await page.evaluate(async () => { await document.fonts.ready; });
  await page.waitForFunction(() => document.fonts.status === 'loaded', null, { timeout: 60000 });
  await page.emulateMedia({ media: 'print' });
  const picked = await page.evaluate(() => {
    const hidden = (el) => {
      for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
        const cs = getComputedStyle(n);
        if (cs.display === 'none' || cs.visibility === 'hidden') return true;
      }
      return false;
    };
    const parts = [];
    const walk = (el) => {
      if (el.nodeType === 1 && hidden(el)) return;
      if (el.nodeType === 3) { parts.push(el.nodeValue); return; }
      if (el.nodeType !== 1) return;
      for (const c of el.childNodes) walk(c);
    };
    walk(document.body);
    // CSS 生成的编号（列表标记 / 步骤序号）不在文本节点里，单独补进"期望侧"
    let markers = '';
    document.querySelectorAll('ol').forEach(ol => {
      if (hidden(ol)) return;
      // 🔴 只有"浏览器真的会画编号"的列表才计入期望侧：`list-style:none` 的列表（如目录/流程清单）
      //    编号是写在文本里的，再补一遍就会让内容比对报"缺数字"（实测缺 1/2/3 各一处）。
      if (getComputedStyle(ol).listStyleType === 'none') return;
      const n = [...ol.children].filter(li => li.tagName === 'LI' && !hidden(li)).length;
      for (let i = 1; i <= n; i++) markers += i + '.';
    });
    // CSS 伪元素里的**文字**（如「提示 / 注意 / 限制」标签）也会被画进 PDF，
    // 但不在 DOM 文本里 —— 必须计入"期望侧"，否则内容比对会报"多字"（实测 +9 提示、+7 注意）。
    let gen = '';
    document.querySelectorAll('*').forEach(el => {
      if (hidden(el)) return;
      for (const ps of ['::before', '::after']) {
        const c = getComputedStyle(el, ps).content;
        if (!c || c === 'none' || c === 'normal') continue;
        if (/^counter\(/.test(c)) continue;          // 计数器已由上面的 markers 处理
        gen += c.replace(/^["']|["']$/g, '');
      }
    });
    const heads = [...document.querySelectorAll('h1,h2,h3,h4')]
      .filter(h => !hidden(h)).map(h => h.innerText.trim()).filter(Boolean);
    const ths = [...document.querySelectorAll('th')]
      .filter(th => !hidden(th)).map(th => th.innerText.trim()).filter(Boolean);
    return { text: parts.join(' '), markers: markers + gen, headings: heads, th_texts: ths };
  });
  const hdr = %(HEADER)s;
  const header = `<div style="width:100%%;font-size:7.4pt;color:#98A0A8;font-family:Helvetica,Arial,sans-serif;
      padding:0 15mm;display:flex;justify-content:space-between;"><span>${hdr}</span><span></span></div>`;
  // 页脚：左＝品牌小图（data URI：页脚模板是**独立文档**，读不到页面里的相对路径），中＝页码
  const mark = %(MARK)s;
  const footer = `<div style="width:100%%;font-size:7.4pt;color:#98A0A8;font-family:Helvetica,Arial,sans-serif;
      padding:0 15mm;display:flex;align-items:center;justify-content:space-between;">`
      + (mark ? `<img src="${mark}" style="height:12px;vertical-align:middle;"/>` : `<span></span>`)
      + `<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`;
  await page.pdf({ path: %(OUT)s, format: 'A4', printBackground: true,
                   displayHeaderFooter: true, headerTemplate: header, footerTemplate: footer,
                   margin: { top: '16mm', bottom: '16mm', left: '15mm', right: '15mm' } });
  console.log('@@JSON@@' + JSON.stringify(picked));
  await browser.close();
})().catch(e => { console.error(String(e)); process.exit(1); });
''' % {'JS': repr(js), 'EXE': repr(exe), 'HTML': repr(os.path.abspath(html_path)),
        'OUT': repr(os.path.abspath(pdf_path)), 'HEADER': repr(header_text or ''),
        'MARK': repr(footer_mark or '')}
    import json as _json
    import subprocess
    r = subprocess.run(['node', '-e', script], capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        raise RuntimeError('Chromium 出件失败：%s%s' % (r.stdout[-600:], r.stderr[-600:]))
    expect, heads = '', []
    for line in (r.stdout or '').splitlines():
        if line.startswith('@@JSON@@'):
            d = _json.loads(line[len('@@JSON@@'):])
            expect, heads = d.get('text', ''), d.get('headings', [])
            _HTML_EXPECT.update({'text': expect, 'markers': d.get('markers', ''),
                                 'headings': heads, 'th_texts': d.get('th_texts', [])})
    return pdf_path, expect, heads, header_text


def find_chromium():
    """定位 Chromium：优先 DSH 缓存里的 playwright 内核，其次系统 Chrome。"""
    import glob
    home = os.path.expanduser('~')
    pats = [os.path.join(home, 'Library/Caches/ms-playwright/chromium-*/chrome-mac*/'
                               'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
            os.path.join(home, 'Library/Caches/ms-playwright/chromium-*/chrome-mac*/'
                               'Chromium.app/Contents/MacOS/Chromium'),
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    for p in pats:
        hits = sorted(glob.glob(p))
        if hits:
            return hits[-1]
    return None


def _playwright():
    """加载 playwright-core（仓库内已随工具链安装）。"""
    import importlib.util
    cands = []
    for base in ('tools/ks-comments-crawler', 'tools/voc-crawler'):
        cands.append(os.path.join(ROOT, base, 'node_modules', 'playwright-core',
                                  'index.js'))
    env = os.environ.get('PLAYWRIGHT_CORE')
    if env:
        cands.insert(0, env)
    for js in cands:
        if os.path.exists(js):
            return js
    return None


def build_pdf(html_path, pdf_path, doc_title='', footer_note=''):
    """用 Chromium 打印 PDF（页眉：文档标题；页脚：第 X 页 / 共 Y 页）。"""
    js = _playwright()
    exe = find_chromium()
    if not (js and exe):
        raise RuntimeError('找不到 Chromium 或 playwright-core（--html-only 可只出 HTML）')
    script = r'''
const { chromium } = require(%(JS)s);
(async () => {
  const browser = await chromium.launch({ executablePath: %(EXE)s, headless: true,
    args: ['--allow-file-access-from-files', '--font-render-hinting=none'] });
  const page = await browser.newPage();
  await page.goto('file://' + %(HTML)s, { waitUntil: 'load' });
  // 🔴 必须等字体就绪再打印：实测 20MB 的 CJK 字体在 load 事件后仍在解析，
  //    此时 page.pdf() 会**回退到系统字体**（TTC → Type3、复制出部首码位）。
  await page.evaluate(async () => { await document.fonts.ready; });
  await page.waitForFunction(() => document.fonts.status === 'loaded', null, { timeout: 60000 });
  await page.emulateMedia({ media: 'print' });
  const esc = (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  // 页眉页脚**不得含 CJK**：Chromium 在独立文档里渲染它们，取不到页面里的 @font-face，
  // 落到系统 TTC 字体 ⇒ Type3 ⇒ 从 PDF 复制出来的页码文字会变成康熙部首（实测 `页`→`⻚`）。
  const header = `<div style="width:100%%;font-size:7.4pt;color:#98A0A8;font-family:Helvetica,Arial,sans-serif;
      padding:0 16mm;display:flex;justify-content:space-between;">
      <span>${esc(%(TITLE_LATIN)s)}</span><span>%(FOOTNOTE)s</span></div>`;
  const footer = `<div style="width:100%%;font-size:7.4pt;color:#98A0A8;font-family:Helvetica,Arial,sans-serif;
      padding:0 16mm;text-align:center;"><span class="pageNumber"></span> / <span class="totalPages"></span></div>`;
  await page.pdf({ path: %(OUT)s, format: 'A4', printBackground: true,
                   displayHeaderFooter: true, headerTemplate: header, footerTemplate: footer,
                   margin: { top: '17mm', bottom: '16mm', left: '16mm', right: '16mm' } });
  await browser.close();
})().catch(e => { console.error(String(e)); process.exit(1); });
''' % {'JS': repr(js), 'EXE': repr(exe), 'HTML': repr(os.path.abspath(html_path)),
       'OUT': repr(os.path.abspath(pdf_path)), 'TITLE': repr(doc_title),
       'TITLE_LATIN': repr(footer_note or ''),
       'FOOTNOTE': _html.escape(footer_note or '')}
    import subprocess
    r = subprocess.run(['node', '-e', script], capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        raise RuntimeError('Chromium 出件失败：%s%s' % (r.stdout[-800:], r.stderr[-800:]))
    return pdf_path


# ─────────────────────────────────────────────────────────────────────────────
# 校验（内容保真 ＋ 容器合法）
# ─────────────────────────────────────────────────────────────────────────────
def plain_text_of_blocks(blocks):
    """语义块 → 纯文本（用于字符多重集比对）。"""
    parts = []

    def walk(tag, _a, p):
        if tag in ('title', 'p', 'h1', 'h2', 'h3'):
            parts.append(re.sub(r'<[^>]+>', '', str(p)))
        elif tag == 'callout':
            for _t, _aa, pp in p:
                parts.append(re.sub(r'<[^>]+>', '', str(pp)))
        elif tag in ('ul', 'ol'):
            for it in p:
                parts.append(re.sub(r'<[^>]+>', '', str(it)))
        elif tag == 'table':
            head, body = p
            for row in (head or []) + (body or []):
                for c in row:
                    parts.append(re.sub(r'<[^>]+>', '', str(c)))
    for b in blocks:
        walk(*b)
    return '\n'.join(parts)


def chars_multiset(text, drop_emoji=True):
    t = re.sub(r'\s+', '', text or '')
    if drop_emoji:
        t = re.sub(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]', '', t)
    return t


def verify_pdf(pdf_path, source_text, verbose=True, header_texts=None, drop_furniture=True,
               expect_extra='', repeat_ok=()):
    """① 内容保真（字符多重集）② 容器合法（pypdf 读 ＋ pypdfium2 渲染）。返回 (ok, report)

    `drop_furniture`：剔除**页眉页脚**（文档标题／页码）后再比对 —— 它们是版面装饰、不是正文内容
    （判据要写在正确的对比面上，否则"页眉在每页重复"会被误读成"多字"）。
    """
    import collections
    rep = []
    ok = True
    try:
        from pypdf import PdfReader
        rd = PdfReader(pdf_path)
        pages = len(rd.pages)
        got = '\n'.join((pg.extract_text() or '') for pg in rd.pages)
    except Exception as ex:                          # pragma: no cover
        return False, ['❌ PDF 无法读取（容器非法或损坏）：%s' % ex]
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(pdf_path)
        n_render = len(doc)
        doc[0].render(scale=1).to_pil()
        rep.append('  ✅ 容器合法：pypdf 读 %d 页／pypdfium2 列 %d 页且可渲染' % (pages, n_render))
    except Exception as ex:
        ok = False
        rep.append('  ❌ 渲染失败：%s' % ex)

    # 版面装饰（每页一份）＝页眉（标题＋脚注）＋ 页码；把它们**加到期望侧**而不是从观测侧删
    # —— 否则正文里的同名字符串会被误删（CLS-04：判据的对比面必须精确）。
    furniture = ''
    if drop_furniture:
        # 页眉/页脚现在只含 ASCII（页码 `i / N`）⇒ 期望侧补上同样字符即可（判据的对比面要精确）
        furniture = ''.join(header_texts or []) * max(1, pages)
        furniture += ''.join('%d/%d' % (i + 1, pages) for i in range(pages))
        # CSS 生成的**有序列表标记**（`1.` `2.` …）由浏览器画出、不属于源文档文本 ⇒ 计入期望侧
        furniture += expect_extra or ''
    body = got
    ms_src = collections.Counter(chars_multiset(source_text + furniture))
    ms_pdf = collections.Counter(chars_multiset(body))
    missing = ms_src - ms_pdf
    extra = ms_pdf - ms_src
    # **布局驱动的合法重复**（必须在"多出"里被解释掉，否则视为内容异常）：
    #   ① 跨页表格每页重复表头（CSS `thead{display:table-header-group}`）；
    #   ② 被分页拆开的伪元素标签（Chromium 会在两个片段上各画一次）。
    if repeat_ok and extra:
        n_ok = 0
        for tok in repeat_ok:
            tok = (tok or '').strip()
            if not tok:
                continue
            k = body.count(tok) - (source_text + furniture).count(tok)
            if k > 0:
                for c in tok:
                    take = min(extra.get(c, 0), k)
                    if take:
                        extra[c] -= take
                        n_ok += take
        extra = +extra
        rep_extra_note = n_ok
    else:
        rep_extra_note = 0
    n_src, n_pdf = sum(ms_src.values()), sum(ms_pdf.values())
    if drop_furniture:
        rep.append('  字符多重集（已剔除页眉页脚）：源 %d ／ PDF 抽取 %d' % (n_src, n_pdf))
    else:
        rep.append('  字符多重集（含页眉页脚）：源 %d ／ PDF 抽取 %d' % (n_src, n_pdf))
    if missing:
        ok = False
        rep.append('  ❌ PDF 缺字符 %d 类：%s' % (len(missing), dict(list(missing.items())[:12])))
    if extra:
        ok = False
        rep.append('  ❌ PDF 多字符 %d 类：%s' % (len(extra), dict(list(extra.items())[:12])))
    if rep_extra_note:
        rep.append('  说明：另有 %d 处"多出"由**布局驱动的重复**解释（跨页重复表头／被拆分的标签）'
                   % rep_extra_note)
    if not (missing or extra):
        rep.append('  ✅ 内容保真：丢失 0 处、且无无法解释的多字（%d 字符逐类对齐）' % n_src)
    return ok, rep


# ─────────────────────────────────────────────────────────────────────────────
# 复制粘贴可用性：修 ToUnicode（康熙部首码位 → 标准汉字）
# ─────────────────────────────────────────────────────────────────────────────
def _iter_fonts(reader):
    out = []
    for page in reader.pages:
        res = page.get('/Resources')
        if not res:
            continue
        fonts = res.get('/Font')
        if not fonts:
            continue
        for _name, f in fonts.get_object().items():
            fo = f.get_object()
            out.append(fo)
            for df in (fo.get('/DescendantFonts') or []):
                out.append(df.get_object())
    return out


def radical_fix_map(font_cmap=None):
    """部首码位 → 标准汉字。

    **两条来源（缺一不可）**：
      ① **NFKC**：康熙部首（U+2F00–U+2FD5）有规范分解（`⽤`→`用`、`⾏`→`行`）；
      ② **字体 cmap 反查**：CJK 部首补充区（U+2E80–U+2EF3，如 `⻚` U+2EDA、`⻓` U+2ED3）
         **没有** NFKC 分解 ⇒ 只能问字体"这个部首形与哪个标准汉字共用字形"
         （实测 Noto Sans SC 里 `⻚`／`页` 同字形）→ 对每个 gid 取**标准汉字**作为规范形。

    **为什么必须修**：Chromium 内嵌 CJK 字体时，共享字形的"部首形"与"汉字"共用同一 glyph，
    其文本层可能映射到**部首码位**（实测：`用`→`⽤`、`行`→`⾏`、`页`→`⻚` 共 38 类、约 100 处）。
    渲染完全正常，但**从 PDF 复制出来的文字是部首码位** —— 搜索、粘贴、二次加工全都会坏。
    """
    import unicodedata
    mp = {}
    for cp in list(range(0x2E80, 0x2EF4)) + list(range(0x2F00, 0x2FD6)):
        ch = chr(cp)
        nf = unicodedata.normalize('NFKC', ch)
        if len(nf) == 1 and nf != ch and 0x4E00 <= ord(nf) <= 0x9FFF:
            mp[ch] = nf
    if font_cmap:                                  # ② 字体反查（覆盖 NFKC 管不到的部首补充区）
        inv = {}
        for cp, gid in font_cmap.items():
            if any(lo <= cp <= hi for lo, hi in ((0x3400, 0x4DBF), (0x4E00, 0x9FFF),
                                                 (0xF900, 0xFAFF), (0x20000, 0x2FA1F))):
                inv.setdefault(gid, cp)
        for cp, gid in font_cmap.items():
            if 0x2E80 <= cp <= 0x2FDF and gid in inv and inv[gid] != cp:
                mp.setdefault(chr(cp), chr(inv[gid]))
    return mp


# 字形别名归一：字体把"中文排版用的全宽破折号"与"西文破折号"做成同一字形时，
# Chromium 的文本层会挑中"另一个码位"（实测 `—`(U+2014)→`―`(U+2015)、`–`(U+2013)→`‒`(U+2012)）。
# **只在**"源文档用的是标准形、且没有用别名形"时才替换 —— 否则会改坏真的用了别名的文档。
ALIAS_PREF = {'\u2015': '\u2014', '\u2012': '\u2013'}


def alias_pref_map(source_text):
    src = set(source_text or '')
    return {a: b for a, b in ALIAS_PREF.items() if b in src and a not in src}


def _fix_cmap_text(data, mp, exact=None):
    """在 ToUnicode CMap 文本里把**目标码位**从部首换成标准汉字（UTF-16 长度不变时才换）。

    CMap 的两种写法都要处理，且**只改目标侧**（源侧是字形 ID，不能动）：
      - `beginbfchar`  ：`<srcCode> <dstUnicode>`   → 改第 2 个 token
      - `beginbfrange` ：`<lo> <hi> <dstUnicode>`   → 改第 3 个 token

    `exact` ＝ `{cid: 源文档里的那个字符}`（**最高优先级**）：字体的 cmap 常把多个 Unicode 指向同一字形
    （`户`/`戶`、`用`/`⽤`、`—`/`―`），Chromium 写的 ToUnicode 只能挑一个 ⇒ 用**源文档逐字符回写**最准。
    """
    txt = data.decode('latin-1')
    if 'beginbf' not in txt:
        return None, 0
    n = 0
    out_lines = []
    mode = None

    def fix(hexs, src=None):
        nonlocal n
        if src is not None and exact and src in exact:
            want = ''.join('%04X' % ord(c) for c in exact[src])
            if want != hexs and len(want) == len(hexs):
                n += 1
                return want
        if len(hexs) % 4:
            return hexs
        try:
            s = ''.join(chr(int(hexs[i:i + 4], 16)) for i in range(0, len(hexs), 4))
        except ValueError:
            return hexs
        new = ''.join(mp.get(c, c) for c in s)
        if new == s:
            return hexs
        nh = ''.join('%04X' % ord(c) for c in new)
        if len(nh) != len(hexs):
            return hexs
        n += 1
        return nh

    for line in txt.splitlines():
        s = line.strip()
        # 🔴 关键字判定必须用 `in` 而不是 `startswith`：真实 CMap 的块头是 **`100 beginbfchar`**
        #    （数量前缀在前）——首版用 startswith 判定 ⇒ 永远进不了 bfchar 模式 ⇒
        #    "归一 0 处"，而抽取出来的仍是康熙部首（CLS-04：对输入格式的假设错）。
        if 'beginbfchar' in s:
            mode = 'char'
            out_lines.append(line)
            continue
        if 'beginbfrange' in s:
            mode = 'range'
            out_lines.append(line)
            continue
        if 'endbfchar' in s or 'endbfrange' in s:
            mode = None
            out_lines.append(line)
            continue
        if mode and s.startswith('<'):
            toks = re.findall(r'<([0-9A-Fa-f]+)>', s)
            idxs = []
            if mode == 'char':
                idxs = list(range(1, len(toks), 2))          # 目标位：第 2、4、6… 个
            elif mode == 'range' and len(toks) >= 3:
                idxs = [2]
            for idx in idxs:
                src = None
                if mode == 'char' and idx >= 1:
                    try:
                        src = int(toks[idx - 1], 16)
                    except ValueError:
                        src = None
                fixed = fix(toks[idx], src)
                if fixed != toks[idx]:
                    line = line.replace('<%s>' % toks[idx], '<%s>' % fixed, 1)
        out_lines.append(line)
    if n == 0:
        return None, 0
    return '\n'.join(out_lines).encode('latin-1'), n


def _cmap_stream(mapping):
    """gid → 字符 的映射 → ToUnicode CMap 流内容（Identity-H 下 CID == GID）。"""
    items = sorted(mapping.items())
    head = ('/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n'
            '/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n'
            '/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n'
            '1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n')
    body, i = [], 0
    while i < len(items):
        chunk = items[i:i + 100]
        body.append('%d beginbfchar\n' % len(chunk))
        for gid, ch in chunk:
            uni = ch.encode('utf-16-be').hex().upper()      # 非 BMP 自动成 8 位代理对
            body.append('<%04X> <%s>\n' % (gid, uni))
        body.append('endbfchar\n')
        i += 100
    tail = 'endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n'
    return head + ''.join(body) + tail


def _font_cmap(fo):
    """取 Type0 字体里内嵌字体文件的 cmap（**码位 → GID**）；不可用时返回 (None, None)。"""
    import importlib
    if os.path.isdir(os.path.join(ROOT, '.kol-tools', '_libs')):
        sys.path.insert(0, os.path.join(ROOT, '.kol-tools', '_libs'))
    try:
        TTFont = importlib.import_module('fontTools.ttLib').TTFont
    except Exception:
        return None, None
    desc = (fo.get('/DescendantFonts') or [None])[0]
    if desc is None:
        return None, None
    dfo = desc.get_object()
    fd = dfo.get('/FontDescriptor')
    if fd is None:
        return None, None
    fd = fd.get_object()
    for k in ('/FontFile2', '/FontFile3', '/FontFile'):
        if k in fd:
            try:
                data = fd[k].get_object().get_data()
                fobj = TTFont(io.BytesIO(data), fontNumber=0, lazy=True)
                # 🔴 fontTools 的 cmap 是 **码位 → 字形名**；PDF 里要的是 **GID**
                #    （Identity-H 下 CID == GID）。首版忘了这一步，注入时把字形名当 GID 用 ⇒ 一条都注入不了，
                #    而抽取器只能靠字形名反查 ⇒ 拿到的是 `uni2F64`（康熙部首）而不是 `用`。
                cm = fobj.getBestCmap() or {}
                return {cp: fobj.getGlyphID(n) for cp, n in cm.items()}, data
            except Exception:
                return None, None
    return None, None


def fix_text_layer(pdf_in, pdf_out, source_text, title=None):
    """让"从 PDF 复制出来的文字"就是**标准汉字**。

    两条路（按字体实际情况自动选）：
      ① **已有 ToUnicode**：只做**部首码位归一**（`⽤`→`用`，见 `radical_fix_map`）；
      ② **没有 ToUnicode**（Chromium 的常态）：**现场注入**一份 —— 用源文档字符集反查字体 cmap 得到
         `gid → 字符`，写成标准 `ToUnicode` CMap。CID 与 GID 在 Identity-H 下相同，所以映射可直接用。

    **为什么必须做**：Noto Sans SC 的 cmap 把 `用`(U+7528) 与康熙部首 `⽤`(U+2F64) 指向**同一个字形**，
    抽取器反向查找时挑中了部首码位 ⇒ 实测 38 类、约 100 处字符复制出来全是部首（搜索/粘贴全坏）。
    渲染不受影响（只改文本层）。
    返回 (注入字体数, 归一替换数)。
    """
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    import importlib
    if os.path.isdir(os.path.join(ROOT, '.kol-tools', '_libs')):
        sys.path.insert(0, os.path.join(ROOT, '.kol-tools', '_libs'))
    try:
        TTFont = importlib.import_module('fontTools.ttLib').TTFont
    except Exception:
        TTFont = None
    wanted = sorted(set(ch for ch in (source_text or '') if ch.strip()))
    mp = radical_fix_map()          # 先用 NFKC 兜底；解析到字体后再补"部首补充区"（见 _font_cmap）
    wr = PdfWriter(clone_from=pdf_in)
    try:                      # 元数据：去掉 Chromium 写进去的浏览器 UA，换成可读来源
        wr.add_metadata({'/Title': title or '', '/Producer': 'GlobalOneClick document pipeline',
                         '/Creator': 'GlobalOneClick · doc_to_pdf (Chromium print engine)'})
    except Exception:
        pass
    n_inj, n_fix = 0, 0
    seen = set()
    for page in wr.pages:
        res = page.get('/Resources')
        if not res:
            continue
        fonts = res.get('/Font')
        if not fonts:
            continue
        for _name, f in fonts.get_object().items():
            fo = f.get_object()
            if fo.get('/Subtype') != '/Type0':
                continue
            cmap, fdata = _font_cmap(fo)
            exact = {}
            if cmap:
                for ch in wanted:                    # 源文档逐字符 → 该字体里的 gid
                    g = cmap.get(ord(ch))
                    if g:
                        exact.setdefault(g, ch)
            tu = fo.get('/ToUnicode')
            if tu is not None:                              # ① 已有：只归一
                m_use = dict(radical_fix_map(cmap) if cmap else mp)
                m_use.update(alias_pref_map(source_text))
                obj = tu.get_object()
                key = getattr(tu, 'idnum', None) or id(obj)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    new, cnt = _fix_cmap_text(obj.get_data(), m_use, exact)
                except Exception:
                    continue
                if new is not None:
                    obj.set_data(new)
                    n_fix += cnt
                continue
            # ② 没有：注入
            desc = (fo.get('/DescendantFonts') or [None])[0]
            if desc is None or TTFont is None:
                continue
            base = str(fo.get('/BaseFont', ''))
            key = ('inj', base)
            if key in seen:
                continue
            seen.add(key)
            if cmap is None:
                continue
            mapping = dict(exact)
            if not mapping:
                continue
            st = DecodedStreamObject()
            st.set_data(_cmap_stream(mapping).encode('latin-1'))
            fo[NameObject('/ToUnicode')] = wr._add_object(st)
            n_inj += 1
    wr.write(pdf_out)
    return n_inj, n_fix


# ─────────────────────────────────────────────────────────────────────────────
# 版面校验（无渲染能力时的"替代视觉检查"：框越界／孤行标题／空页／表头重复／字体嵌入）
# ─────────────────────────────────────────────────────────────────────────────
def font_coverage(text, fonts=None):
    """检查交付文本里的**每个字符是否都被所嵌字体覆盖** —— 未被覆盖的字符会触发字体回退。

    **为什么必须查**：Chromium 只在"字体真覆盖"时才走 Type0 子集嵌入；一旦某个字符回退到
    系统字体（macOS 的 CJK 字体是 TTC），那部分字形就变成 **Type3**，复制粘贴会取到错误码位
    （实测：`用`→`⽤`、`页`→`⻚`；emoji 与 ✔/✕/⚠ 这类符号最容易触发回退）。
    返回 (missing_sorted, fonts_used)。
    """
    import importlib
    if os.path.isdir(os.path.join(ROOT, '.kol-tools', '_libs')):
        sys.path.insert(0, os.path.join(ROOT, '.kol-tools', '_libs'))
    try:
        TTFont = importlib.import_module('fontTools.ttLib').TTFont
    except Exception:
        return None, []                      # 无 fontTools 时跳过（不阻断出件）
    paths = fonts or [f for f in (FONT_REGULAR, FONT_BOLD) if os.path.exists(f)]
    if not paths:
        return None, []
    have = set()
    for fp in paths:
        try:
            have |= set(TTFont(fp, lazy=True).getBestCmap().keys())
        except Exception:
            pass
    missing = sorted({c for c in (text or '') if c.strip() and ord(c) not in have})
    return missing, paths


def verify_container(pdf_path):
    """容器**结构**合法（不是"宽容解析器读得出来"）：严格模式读 ＋ `/Root` 必须是 `/Catalog`
    ＋ 每页 `/Type` 必须是 `/Page`。

    判据一句话：**「内容对 ≠ 文件能打开」**（CLS-15）—— 自生成的 PDF 必须先证结构合法，
    再谈内容与版面；宽容解析器（pdfminer 等）能把损坏件读出全部文字，所以不能拿它当"能打开"的证据。
    """
    from pypdf import PdfReader
    rep, ok = [], True
    try:
        rd = PdfReader(pdf_path, strict=True)
    except Exception as ex:
        return False, ['  ❌ 严格模式解析失败（容器结构可疑）：%s' % ex]
    root = rd.trailer.get('/Root')
    rtype = str(root.get('/Type')) if root is not None else 'None'
    if rtype != '/Catalog':
        ok = False
        rep.append('  ❌ trailer /Root 的 /Type 是 %s（必须是 /Catalog）' % rtype)
    else:
        rep.append('  ✅ /Root → /Catalog（严格模式解析通过）')
    bad = [i + 1 for i, pg in enumerate(rd.pages) if str(pg.get('/Type')) != '/Page']
    if bad:
        ok = False
        rep.append('  ❌ 以下页对象的 /Type 不是 /Page：%s' % bad)
    else:
        rep.append('  ✅ %d 页对象的 /Type 均为 /Page' % len(rd.pages))
    return ok, rep


def verify_layout(pdf_path, headings=(), furniture=(), table_groups=()):
    """替代视觉检查：**没有渲染能力时，"版面好不好"也必须能被机器判**。

    五条判据（每条都能对应一个真实会出丑的现象）：
      ① **字体全部嵌入** —— 否则收件人机器上会回退成别的字体（甚至方框）；
      ② **内容框不越出页面** —— 抓"长表格/长链接把内容挤出可打印区"；
      ③ **无孤行标题** —— 标题落在页尾、正文在下页（最典型的排版事故；CSS 用 `break-after: avoid` 防，这里验）；
      ④ **无空页／近空页**；
      ⑤ **跨页表格自动重复表头**（`thead` 每页重现，否则续页的表格列义不明）。
    """
    rep, ok = [], True
    import pypdfium2 as pdfium
    from pypdf import PdfReader
    doc = pdfium.PdfDocument(pdf_path)
    rd = PdfReader(pdf_path)

    # ① 字体嵌入
    not_emb, t3 = [], []
    for page in rd.pages:
        res = page.get('/Resources') or {}
        fonts = res.get('/Font')
        if not fonts:
            continue
        for _n, f in fonts.get_object().items():
            fo0 = f.get_object()
            if fo0.get('/Subtype') == '/Type3':
                t3.append(str(_n))          # Type3：字形过程自包含（emoji 等），不算"未嵌入"
                continue
            stack, emb, base = [fo0], False, '?'
            while stack:
                fo = stack.pop()
                base = str(fo.get('/BaseFont', base))
                for df in (fo.get('/DescendantFonts') or []):
                    stack.append(df.get_object())
                fd = fo.get('/FontDescriptor')
                if fd is not None:
                    fd = fd.get_object()
                    if any(k in fd for k in ('/FontFile', '/FontFile2', '/FontFile3')):
                        emb = True
            if not emb:
                not_emb.append(base)
    if len(t3) > 3 and not any('+' in b for b in not_emb):
        # Type3 数量异常 ⇒ 说明正文走了 Chromium 的"轮廓回退"路径：
        #   实测该路径下 ① 字体不是真子集嵌入；② 从 PDF 复制出来的文字会变成康熙部首码位。
        #   （emoji 等少量 Type3 属正常，故阈值取 3。）
        ok = False
        rep.append('  ❌ 检测到 %d 个 Type3 字体（正文疑似走了轮廓回退：复制出的文字会坏）'
                   '→ 检查 CJK 字体是否为**静态 glyf TTF**（可变字体/CFF/TTC 都会退成 Type3）' % len(t3))
    if not_emb:
        ok = False
        rep.append('  ❌ 有字体未嵌入（收件人可能看到方框/回退字形）：%s' % sorted(set(not_emb))[:6])
    else:
        rep.append('  ✅ 字体全部嵌入（离线可读，不依赖收件人装字体）'
                   + ('；另有 Type3 自包含字形 %d 个（emoji 等）' % len(t3) if t3 else ''))

    # ② 逐页内容框 + 抽行（同时准备 ③④⑤ 的输入）
    pages = []
    for i in range(len(doc)):
        pg = doc[i]
        W, H = pg.get_size()
        tp = pg.get_textpage()
        n = tp.count_chars()
        box = None
        for k in range(n):
            l, b, r, tp_ = tp.get_charbox(k)
            box = (l, b, r, tp_) if box is None else (
                min(box[0], l), min(box[1], b), max(box[2], r), max(box[3], tp_))
        # 🔴 行序必须**按坐标**取，不能用抽取顺序：实测抽取顺序会把页眉页脚排在末尾、
        #    并把大字号标题的字符拆成两"行"（CLS-04：不能拿"我以为的顺序"当版面顺序）。
        chars = []
        for k in range(n):
            ch = tp.get_text_range(k, 1)
            l, b, r, tp_ = tp.get_charbox(k)
            if ch.strip():
                chars.append(((b + tp_) / 2.0, l, ch))
        vis = [y for y, _l, _c in chars if FURN_LO < y < H - FURN_LO]   # 只留正文带
        chars = [c for c in chars if FURN_LO < c[0] < H - FURN_LO]
        chars.sort(key=lambda x: -x[0])                # y 大 = 靠上 → 从上到下
        lines = []
        for y, l, ch in chars:
            if lines and abs(lines[-1][0] - y) <= 3.0:
                lines[-1][1].append((l, ch))
            else:
                lines.append([y, [(l, ch)]])
        lines = [(''.join(c for _l, c in sorted(seg)), y) for y, seg in lines]
        pages.append({'i': i + 1, 'W': W, 'H': H, 'box': box,
                      'lines': [s for s, _y in lines], 'n_body': len(vis)})
        if box and n:
            tol = 2.0
            if box[0] < -tol or box[1] < -tol or box[2] > W + tol or box[3] > H + tol:
                ok = False
                rep.append('  ❌ 第 %d 页内容越出页面框：(%.1f,%.1f)-(%.1f,%.1f) vs 页面 %.1f×%.1f'
                           % (i + 1, box[0], box[1], box[2], box[3], W, H))
    rep.append('  ✅ 逐页内容框均在页面内（%d 页）' % len(pages))

    # 正文行 = 去掉页眉/页脚（版面装饰不进判定：判据必须作用在正确的对象上）
    def body_lines(pg):
        # 正文带已经按坐标切掉页眉页脚（FURN_LO），这里只需再兜一层文本匹配
        out = []
        for l in pg['lines']:
            if re.match(r'^第\s*\d+\s*页', l):
                continue
            if any(f and l.replace(' ', '') == f.replace(' ', '') for f in furniture):
                continue
            out.append(l)
        return out

    orphan = [(pg['i'], bl[-1]) for pg in pages for bl in [body_lines(pg)]
              if bl and any(bl[-1] == h for h in headings)]
    if orphan:
        ok = False
        rep.append('  ❌ 孤行标题（标题落页尾、正文在下页）：%s'
                   % ['第%d页「%s」' % x for x in orphan])
    else:
        rep.append('  ✅ 无孤行标题（%d 个标题均未落在页尾）' % len(headings))

    # 🔴 空白页判定必须**计入图片**：只放一张整幅截图的页面不是空页
    #    （首版只看文字行数 ⇒ 把"图 5 独占一页"误判为疑似空白页；判据要判在正确的对象上）
    img_pages = set()
    for i in range(len(doc)):
        for ob in doc[i].get_objects():
            if ob.type == 3:                      # FPDF_PAGEOBJ_IMAGE
                img_pages.add(i + 1)
                break
    empt = [pg['i'] for pg in pages if len(body_lines(pg)) <= 1 and pg['i'] not in img_pages]
    if empt and (len(empt) > 1 or empt[0] != len(pages)):
        ok = False
        rep.append('  ❌ 疑似空白页：%s' % empt)
    else:
        rep.append('  ✅ 无空页（每页均有正文或有整幅图）')

    if table_groups:
        bad = []
        for pg in pages:
            txt = '\n'.join(body_lines(pg))
            for head_terms, row_terms in table_groups:
                if (sum(1 for x in row_terms if x in txt) >= 2
                        and not all(x in txt for x in head_terms)):
                    bad.append(pg['i'])
        if bad:
            ok = False
            rep.append('  ❌ 续页表格缺表头（列义不明）：第 %s 页' % sorted(set(bad)))
        else:
            rep.append('  ✅ 跨页表格每页都带表头')
    return ok, rep


def self_test():
    ctl = []
    SRC = ('<title id="a">示例文档</title><p id="b">第一段。</p>'
           '<callout id="c" background-color="rgb(240,244,255)" border-color="rgb(130,167,252)" emoji="🎯">'
           '<p id="d"><b>推荐用法：</b>先看总览。</p></callout>'
           '<h1 id="e">章节一</h1><p id="f"><b>对应图表：</b>环形图。</p><h2 id="g">怎么看</h2>'
           '<ul><li id="h">要点 A</li><li id="i">要点 B</li></ul>'
           '<table id="j"><colgroup><col width="175"/><col width="281"/><col width="282"/></colgroup>'
           '<thead><tr><th><p id="k">列一</p></th><th><p id="l">列二</p></th><th><p id="m">列三</p></th></tr></thead>'
           '<tbody><tr><td><p id="n">甲</p></td><td><p id="o">乙</p></td><td><p id="p">丙</p></td></tr></tbody></table>'
           '<h1 id="q">章节二</h1><ol><li id="r"><b>先看</b>声量。</li></ol><p id="s"></p>')
    blocks, unknown = parse_docx_xml(SRC)
    html = blocks_to_html(blocks, title='示例文档', footer_note='内部')
    ctl.append(('正控 标题/正文/callout/列表/表格/有序列表都被渲染',
                all(k in html for k in ('doc-title', 'class="lead"', 'class="callout"',
                                        'class="sec"', 'class="sub"', 'class="chart-note"',
                                        '<ul>', '<ol>', '<table>', 'colgroup'))))
    ctl.append(('正控 callout 沿用文档自带底色/描边色（--co-bg/--co-border）',
                '--co-bg:rgb(240,244,255)' in html and '--co-border:rgb(130,167,252)' in html))
    ctl.append(('正控 A4 版面与分页规则在 CSS 里（@page A4 / keep 容器 / 表头重复）',
                'size: A4 portrait' in html and 'break-inside: avoid' in html
                and 'display: table-header-group' in html))
    ctl.append(('正控 「对应图表：…」行被识别为 chart-note（内容一字不改）',
                '<p class="chart-note"><strong>对应图表：</strong>环形图。</p>' in html))
    ctl.append(('正控 空段落被丢弃、且不影响其后段落判定',
                '<p></p>' not in html and html.count('class="lead"') == 1))
    _w = [float(x) for x in re.findall(r'width:([\d.]+)%', html)]
    ctl.append(('正控 表格列宽按源文档比例归一（175/281/282 → 合计 100、比例保持）',
                len(_w) == 3 and abs(sum(_w) - 100.0) < 0.01
                and abs(_w[1] / _w[0] - 281 / 175.0) < 0.01))
    ctl.append(('🔴 正控 标题与其紧随段落被包进 .keep（Chromium 不支持 break-after: avoid，'
                '标题落页尾只能靠这个容器防）',
                '<div class="keep"><h2 class="sec">章节一</h2><p class="chart-note">' in html
                and html.count('class="keep"') == 1))
    ctl.append(('[degenerate:substring] 标题的"紧随块"是列表时不能乱包（不得把列表吞进 keep）',
                '<div class="keep"><h3 class="sub">怎么看</h3><ul>' not in html))
    ctl.append(('[degenerate:empty] 空 XML → 不炸、产出空正文骨架',
                blocks_to_html(parse_docx_xml('')[0], title='T').count('<article') == 1))
    ctl.append(('[degenerate:nonlatin] 纯非拉丁（日文）正文原样保留',
                'ご連絡ありがとう' in blocks_to_html(parse_docx_xml('<p>ご連絡ありがとう</p>')[0])))
    ctl.append(('[degenerate:accent_case] HTML 特殊字符被转义（不得原样漏出）',
                '&lt;script&gt;' in blocks_to_html(
                    parse_docx_xml('<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>')[0])))
    ctl.append(('[degenerate:substring] 「图表」只作前缀判定：正文中间的「图表」不得被误判成提示行',
                'class="chart-note"' not in blocks_to_html(
                    parse_docx_xml('<h1>T</h1><p>本节图表较多，见图一。</p>')[0])))
    ctl.append(('[degenerate:type_unit] 非法 XML 必须报错而不是静默返回空',
                _raises(lambda: parse_docx_xml('<p>未闭合'))))
    ctl.append(('[degenerate:negation] 空 <p> 不算内容（不得因"有段落"就判成有正文）',
                plain_text_of_blocks(parse_docx_xml('<p></p><p>  </p>')[0]).strip() == ''))
    _src = plain_text_of_blocks(blocks)
    ctl.append(('正控 字符多重集判据能抓出漏字',
                chars_multiset(_src) != chars_multiset(_src.replace('章节二', '章节'))))
    ctl.append(('真阴性 同一文本的空白差异不得被判成内容差异',
                chars_multiset(_src) == chars_multiset(_src.replace('。', '。\n'))))
    ctl.append(('真阴性 emoji 不参与内容比对（图标不是正文）',
                chars_multiset('🎯要点') == chars_multiset('要点')))
    _b, _u = parse_docx_xml('<p>x</p><bitable token="t"/>')
    ctl.append(('正控 未支持的块必须进 unknown 并在 HTML 里留痕（禁静默丢内容）',
                'bitable' in _u and '未支持的块' in blocks_to_html(_b)))
    # ── 文本层（复制粘贴可用性）判据 ──
    _map = radical_fix_map()
    ctl.append(('🔴 正控 康熙部首码位必须被归一为标准汉字（实测 38 类／约 100 处）',
                _map.get('⽤') == '用' and _map.get('⾏') == '行' and _map.get('⼈') == '人'))
    # CJK 部首补充区（U+2E80–U+2EF3）**没有 NFKC 分解** ⇒ 必须能从字体 cmap 反查推导
    _synth = {0x9875: 7, 0x2EDA: 7, 0x957F: 9, 0x2ED3: 9, 0x7528: 11, 0x2F64: 11}
    _map2 = radical_fix_map(_synth)
    ctl.append(('🔴 正控 部首补充区必须靠"字体反查"补上（NFKC 管不到 `⻚`/`⻓`）',
                _map2.get('⻚') == '页' and _map2.get('⻓') == '长' and _map2.get('⽤') == '用'))
    ctl.append(('[degenerate:negation] 字体反查不得把标准汉字改掉（映射表只含部首码位）',
                radical_fix_map(_synth).get('页') is None))
    ctl.append(('真阴性 标准汉字不得被改（归一表只含部首码位）',
                all(_map.get(c) is None for c in '用行页人一高文')))
    _real_cmap = ('/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n'
                  '1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n'
                  '2 beginbfchar\n<492C> <2F64>\n<2246> <4E0E>\nendbfchar\nendcmap\n')
    _fixed, _cnt = _fix_cmap_text(_real_cmap.encode('latin-1'), _map2)
    ctl.append(('🔴 正控 真实 CMap 格式（块头是 `2 beginbfchar`，带数量前缀）必须能被归一：'
                '`<492C> <2F64>` → `<492C> <7528>`',
                _cnt == 1 and b'<492C> <7528>' in (_fixed or b'')
                and b'<2246> <4E0E>' in (_fixed or b'')))
    ctl.append(('[degenerate:substring] 无数量前缀的块头同样要认（两种写法都不得漏）',
                _fix_cmap_text(_real_cmap.replace('2 beginbfchar', 'beginbfchar').encode('latin-1'), _map2)[1] == 1))
    ctl.append(('[degenerate:negation] 非部首目标位不得被动（标准汉字的映射保持原样）',
                b'<2246> <4E0E>' in (_fix_cmap_text(_real_cmap.encode('latin-1'), _map2)[0] or b'')))
    _olb, _ = parse_docx_xml('<ol><li><b>先看</b>A。</li><li>B。</li><li>C。</li></ol>')
    ctl.append(('正控 有序列表标记（CSS 生成）必须计入"期望侧"（否则会报多字 `1.` `2.` `3.`）',
                ''.join('%d.' % i for i in range(1, 4)) == '1.2.3.'
                and _olb[0][0] == 'ol' and len(_olb[0][2]) == 3))
    ctl.append(('🔴 正控 破折号别名归一：源用 `—` 时，`―`(U+2015)→`—`(U+2014)',
                alias_pref_map('行业位置—内容效率') == {'\u2015': '\u2014'}))
    ctl.append(('[degenerate:negation] 源文档用的就是 `―` 时**不得**被改（判据要有反向豁免）',
                alias_pref_map('用 ― 表示区间') == {}))
    ctl.append(('[degenerate:empty] 空文本时别名表为空（不误伤）', alias_pref_map('') == {}))
    _cm = _cmap_stream({1: '用', 2: 'A', 3: '，'})
    ctl.append(('正控 注入的 ToUnicode CMap 结构完整（bfchar ＋ codespacerange ＋ 4 位十六进制）',
                'beginbfchar' in _cm and '<0001> <7528>' in _cm and '<0000> <FFFF>' in _cm))
    ctl.append(('[degenerate:empty] 空映射不得产出非法 CMap（不崩）',
                'begincmap' in _cmap_stream({})))
    ctl.append(('[degenerate:accent_case] 非 BMP 字符（emoji）写进 CMap 必须用 8 位代理对且不崩',
                '<0001> <D83CDFAF>' in _cmap_stream({1: '🎯'})))
    ctl.append(('正控 字体档位注释与实现一致：只用静态 glyf TTF（可变字体/CFF/TTC 会退 Type3）',
                'truetype-variations' not in font_face_css() and 'fontTools' in io.open(
                    os.path.abspath(__file__), encoding='utf-8').read()))
    _miss, _ = font_coverage('用行页文 ABC 123，。')
    ctl.append(('正控 字体覆盖检查：常规中英文字符必须全覆盖', _miss == []))
    _miss2, _ = font_coverage('🎯✔✕⚠⛔')
    ctl.append(('🔴 正控 字体覆盖检查必须抓出 emoji/符号（它们会回退系统字体 → Type3）',
                _miss2 is None or len(_miss2) >= 3))
    ctl.append(('[degenerate:empty] 空文本不得致崩', font_coverage('')[0] in ([], None)))
    _a = _ctl_assets()
    ctl.append(('正控 图片越出页面必须报出',
                _img_overflow((-5.0, 40.0, 500.0, 700.0), 595.9, 842.9)[0] is True))
    ctl.append(('正控 正文区图片越出内容框左右边界必须报出',
                _img_overflow((30.0, 100.0, 560.0, 700.0), 595.9, 842.9)[0] is True))
    ctl.append(('真阴性 页脚带内的品牌标记不得被误判为越界',
                _img_overflow((460.0, 18.0, 500.0, 40.0), 595.9, 842.9)[0] is False))
    ctl.append(('真阴性 正常落在内容框内的图片不得误报',
                _img_overflow((42.5, 100.0, 553.4, 700.0), 595.9, 842.9)[0] is False))
    ctl.append(('正控 本地资源闸门：引用的图不存在必须报出（图会静默消失、alt 会变成文字）', _a[0]))
    ctl.append(('真阴性 存在的图与 data URI 不得被误报为缺失', _a[1]))
    ctl.append(('真阴性 封面主视觉与页脚标记不得被当成"缩得太小"',
                (_img_too_narrow((100, 400, 250, 600), 1)[0] is False)
                and (_img_too_narrow((40, 10, 90, 40), 3)[0] is False)))
    ctl.append(('正控 正文区被高度卡住的长图（83mm 宽 × 页面高）必须报出（截图字会很小）',
                _img_too_narrow((42.5, 300, 278, 844), 3)[0] is True))
    ctl.append(('真阴性 正文区正常宽度的截图（165mm）不得被误报',
                _img_too_narrow((42.5, 300, 510, 844), 3)[0] is False))
    print('=== doc_to_pdf 自检 ===')
    for n, v in ctl:
        print(' %s %s' % ('✅' if v else '❌', n))
    print('自检 %d/%d' % (sum(1 for _, v in ctl if v), len(ctl)))
    return 0 if all(v for _, v in ctl) else 1


def _ctl_assets():
    """资源闸门自检：缺图必报（真阳性）、图在不得误报（真阴性）。"""
    import tempfile
    d = tempfile.mkdtemp()
    io.open(os.path.join(d, 'ok.png'), 'wb').write(b'x')
    a = local_asset_refs('<img src="ok.png"/><img src="gone.png"/>', d)
    b = local_asset_refs('<img src="ok.png"/><img src="data:image/png;base64,AA"/>', d)
    return [(a[0] == 2 and a[1] == ['gone.png']), (b[0] == 1 and b[1] == [])]


def _raises(fn):
    try:
        fn()
    except ValueError:
        return True
    except Exception:
        return False
    return False


def main():
    if '--self-test' in sys.argv:
        return self_test()
    ap = argparse.ArgumentParser(description='飞书 DocxXML / HTML → 印刷级 PDF')
    ap.add_argument('--xml', help='飞书 DocxXML（`lark-cli docs +fetch --doc-format xml --detail full`）')
    ap.add_argument('--html', help='已有 HTML（用于"指南/手册"这类自撰交付件：同源出 HTML ＋ PDF）')
    ap.add_argument('--header', default='', help='页眉文字（**必须 ASCII**：含 CJK 会退 Type3、复制粘贴坏）')
    ap.add_argument('--font-var', default='--font', help='HTML 里的字体 CSS 变量名（HTML 模式用它前置内嵌字体）')
    ap.add_argument('--footer-mark', help='页脚品牌小图（PNG，会以 data URI 内嵌到每页页脚；HTML 模式）')
    ap.add_argument('--out', required=True)
    ap.add_argument('--html-out')
    ap.add_argument('--title')
    ap.add_argument('--footer-note', default='')
    ap.add_argument('--html-only', action='store_true')
    ap.add_argument('--verify-shots', help='把 PDF 渲染成 PNG 的目录（人工复核分页）')
    ap.add_argument('--no-tounicode-fix', action='store_true',
                    help='不修 ToUnicode（默认修：让"复制出来的文字"是标准汉字而不是康熙部首）')
    a = ap.parse_args()
    if not (a.xml or a.html):
        print('用法：--xml <DocxXML> 或 --html <已有 HTML>（二选一）'); return 1
    if a.html:
        return run_html_mode(a)

    blocks, unknown = parse_docx_xml(io.open(a.xml, encoding='utf-8').read())
    title = a.title or next((re.sub(r'<[^>]+>', '', p) for t, _x, p in blocks if t == 'title'), '')
    headings = [re.sub(r'<[^>]+>', '', p) for t, _x, p in blocks if t in ('h1', 'h2', 'h3')]
    html = blocks_to_html(blocks, title=title, footer_note=a.footer_note)
    hp = a.html_out or (os.path.splitext(a.out)[0] + '.html')
    os.makedirs(os.path.dirname(os.path.abspath(hp)) or '.', exist_ok=True)
    io.open(hp, 'w', encoding='utf-8').write(html)
    print('① 语义块 %d 个（未支持块：%s）' % (len(blocks), unknown or '无'))
    print('② HTML → %s' % hp)
    if a.html_only:
        return 0
    build_pdf(hp, a.out, doc_title=title, footer_note=a.footer_note)
    print('③ PDF  → %s（%.1f KB）' % (a.out, os.path.getsize(a.out) / 1024.0))
    print('④ 文本层与元数据处理：', end='')
    tmp = a.out + '.tmp'
    try:
        n_inj, n_fix = fix_text_layer(a.out, tmp, plain_text_of_blocks(blocks), title=title)
        os.replace(tmp, a.out)
        print('注入 ToUnicode %d 个字体／归一码位 %d 处／元数据已重写' % (n_inj, n_fix))
    except Exception as ex:
        if os.path.exists(tmp):
            os.remove(tmp)
        print('跳过（%s）' % ex)
    ol_marks = ''
    for tg, _x, pl in blocks:
        if tg == 'ol':
            n_ol = len([1 for it in pl if str(it).strip()])
            ol_marks += ''.join('%d.' % i for i in range(1, n_ol + 1))
    ok0, rep0 = verify_container(a.out)
    print('=== 交付前校验（容器结构）===')
    for line in rep0:
        print(line)
    ok, rep = verify_pdf(a.out, plain_text_of_blocks(blocks),
                         header_texts=[a.footer_note], expect_extra=ol_marks)
    print('=== 交付前校验（内容）===')
    for line in rep:
        print(line)
    groups = []
    for tg, _x, pl in blocks:
        if tg == 'table':
            head, body = pl
            if head and body:
                groups.append(([re.sub(r'<[^>]+>', '', c).strip() for c in head[0]],
                               [re.sub(r'<[^>]+>', '', r[0]).strip() for r in body]))
    ok2, rep2 = verify_layout(a.out, headings=headings,
                              furniture=[title, a.footer_note], table_groups=groups)
    print('=== 交付前校验（版面）===')
    for line in rep2:
        print(line)
    if a.verify_shots:
        import pypdfium2 as pdfium
        os.makedirs(a.verify_shots, exist_ok=True)
        doc = pdfium.PdfDocument(a.out)
        for i in range(len(doc)):
            doc[i].render(scale=2).to_pil().save(os.path.join(a.verify_shots, 'page-%02d.png' % (i + 1)))
        print('   出图 %d 页 → %s' % (len(doc), a.verify_shots))
    return 0 if (ok0 and ok and ok2) else 1


def local_asset_refs(html, base_dir):
    """抽出 HTML 里引用的**本地资源**并核对是否存在（相对路径按 base_dir 解析）。

    为什么单列一个判据：中间件换目录（如打印版 HTML 落到 `_build/`）时相对路径会失效 ——
    图不会报错，只会**静默消失**，`<img>` 还会把 alt 渲染成文字（本轮实测：PDF 少了 1.26MB 图、
    文本里多出 2 个 "Daniel"）。判据一句话：**"图在不在"必须显式验，不能靠肉眼看渲染结果。**
    """
    missing, checked = [], 0
    for m in re.finditer(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', html or '', re.I):
        u = m.group(1).strip()
        if not u or u.startswith(('data:', 'http:', 'https:', '#', 'mailto:', 'javascript:')):
            continue
        p = u[7:].split('#')[0] if u.startswith('file://') else u.split('#')[0]
        if not p or p.endswith('/'):
            continue
        p = p if os.path.isabs(p) else os.path.join(base_dir, p)
        checked += 1
        if not os.path.exists(os.path.normpath(p)):
            missing.append(u)
    return checked, missing



def _img_overflow(bounds, page_w, page_h, margin_l=42.5, margin_r=42.5, footer_band=45.0, tol=1.0):
    """判一张图是否越界。返回 (是否越界, 原因)。

    **为什么要单独判图**：文字越界有 `verify_layout` 的坐标判据兜住，而**图片既可能被排版挤出页面，
    也可能被 `overflow:hidden` 悄悄裁掉**（长图限高时最容易发生）——出件后必须单独验一次。
    页脚品牌标记位于页边距内（设计如此）⇒ 以"是否落在页脚带"区分，不参与内容框判定。
    """
    left, bottom, right, top = bounds
    if left < -tol or bottom < -tol or right > page_w + tol or top > page_h + tol:
        return True, '越出页面（%.1f, %.1f, %.1f, %.1f）' % bounds
    if top <= footer_band + tol:                      # 页脚带内的标记
        return False, ''
    if left < margin_l - tol or right > page_w - margin_r + tol:
        return True, '越出内容框左右边界（%.1f–%.1f）' % (left, right)
    return False, ''


MIN_PRINT_WIDTH_MM = 100.0


def _img_too_narrow(bounds, page_no, footer_band=45.0, min_mm=None):
    """正文区的图在纸面上缩得太小？（v0.9.136 新增 · 教训 187）

    **为什么**：中等长图（比例 2–3）在纸面上被高度卡住后，宽度只剩一半 ——
    截图里的字会缩到几乎认不出（“图在纸上看不清”等于没配图）。判据：**宽度 < 100mm 就提醒分段**。
    封面主视觉与页脚标记（缩小是设计）不参与判定。
    """
    left, bottom, right, top = bounds
    if page_no == 1:                      # 封面主视觉：小是设计
        return False, 0.0
    if top <= footer_band:                # 页脚带内的品牌标记
        return False, 0.0
    mm = (right - left) / 72.0 * 25.4
    if mm < 20.0:                         # 小标记／图标（品牌标记等）不是截图，不参与
        return False, mm
    return mm < (min_mm or MIN_PRINT_WIDTH_MM), mm


def verify_images(pdf_path, header_band=60.0):
    """逐页核对图片对象：完整落在页面内；正文区的图还要落在内容框内。"""
    rep, ok = [], True
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return True, ['  ⚠️ 未安装 pypdfium2，跳过图片位置检查']
    doc = pdfium.PdfDocument(pdf_path)
    n_img, bad, tiny, narrows = 0, [], [], []
    for i in range(len(doc)):
        pg = doc[i]
        W, H = pg.get_size()
        for ob in pg.get_objects():
            if ob.type != 3:                          # 3 = FPDF_PAGEOBJ_IMAGE
                continue
            n_img += 1
            over, why = _img_overflow(ob.get_bounds(), W, H)
            if over:
                ok = False
                bad.append('p%d %s' % (i + 1, why))
            narrow, mm = _img_too_narrow(ob.get_bounds(), i + 1)
            if narrow:
                narrows.append((i + 1, ob.get_bounds(), mm))
    if bad:
        rep.append('  ❌ 有 %d 张图片越界（可能被裁或挤出页面）：%s' % (len(bad), '；'.join(bad[:6])))
    else:
        rep.append('  ✅ %d 张图片均完整落在页面内（正文区图片未越出内容框）' % n_img)
    # 并排成对（同一页、同一水平带、左右各一张）＝ .tall 极端长图的分半工序 ⇒ 不再提醒
    for pg, bd, mm in narrows:
        l, b, r, t = bd
        paired = any(op == pg and abs(ob2[3] - t) < 20 and (ob2[2] <= l + 1 or ob2[0] >= r - 1)
                     for op, ob2, _m in narrows)
        if not paired:
            tiny.append('p%d %.0fmm' % (pg, mm))
    if tiny:
        rep.append('  ⚠️ 有 %d 张图在纸面上宽度不足 100mm（截图里的字会很小）：%s —— 长图建议按上下两段分段显示'
                   % (len(tiny), '；'.join(tiny[:6])))
    else:
        rep.append('  ✅ 正文区图片在纸面上的宽度都不小于 100mm（截图字迹可读）')
    return ok, rep


def print_fingerprint(pdf_path):
    """出件后打「交付指纹」：页数 · 字节 · SHA256 前 12 位 · 出件时间。

    为什么固化在仪器里：**同名文件原位更新时，用户打开的往往是旧副本**（浏览器标签没刷新、
    PDF 阅读器缓存），于是"我已经改好了"与"我怎么还看到老内容"会反复对不上。
    指纹就是双方确认"你看的是哪一版"的唯一凭据 —— 每次出件必须打印，并在回话里给用户。
    """
    import datetime
    import hashlib
    try:
        from pypdf import PdfReader          # 函数内导入：本仪器其余部分也是按需导入
        data = io.open(pdf_path, 'rb').read()
        pages = len(PdfReader(pdf_path).pages)
        print('④ 交付指纹 → %s ｜ %s 页 ｜ %.1f KB ｜ SHA256 %s ｜ 出件 %s'
              % (os.path.basename(pdf_path), pages, len(data) / 1024.0,
                 hashlib.sha256(data).hexdigest()[:12],
                 datetime.datetime.now().strftime('%Y-%m-%d %H:%M')))
    except Exception as exc:                                  # 指纹打不出不影响出件
        print('④ 交付指纹：生成失败（%s）' % exc)


def run_html_mode(a):
    """HTML 交付件 → 同时产出 PDF，并跑同一套五组校验（容器/内容/字体/版面/重叠）。

    **同源异验**：HTML 与 PDF 内容同源（同一份 HTML），但**校验走独立路径** ——
    从 PDF 抽回文本，与"打印时可见的文本 ＋ CSS 生成的编号"逐字符比对（字符多重集）。
    """
    html = io.open(a.html, encoding='utf-8').read()
    m = re.search(r'<title>(.*?)</title>', html, re.S)
    title = a.title or (m.group(1).strip() if m else '')
    face = font_face_css()
    if face and '@font-face' not in html:
        # 把内嵌字体**前置到页面的字体变量**（默认 `--font`）；找不到变量就补一条 body 规则。
        # 只前置不替换：保留原回退链，缺字时仍能回退到系统字体（但会退 Type3，故出件后由判据兜住）。
        var = a.font_var or '--font'
        pat = re.compile(r'(%s\s*:\s*)' % re.escape(var))
        if pat.search(html):
            html = pat.sub(lambda m: m.group(1) + "'DocCJK', ", html, count=1)
            print('   字体注入：已把 DocCJK 前置到 %s 变量' % var)
        else:
            html = html.replace('</style>', face + "\nbody{font-family:'DocCJK',sans-serif;}\n</style>", 1)
            print('   字体注入：未找到 %s 变量，已改为覆盖 body 字体' % var)
        html = html.replace('</style>', face + '\n</style>', 1)
    # 交付目录只留「一个 HTML ＋ 一个 PDF」：打印版 HTML 是中间件，落到 <输出目录>/_build/
    # （2026-09-28 用户反馈「根目录只需要最终版本的一个 html ＋ 一个 pdf，现在有两个我都分不清要用哪个」）
    _bd = os.path.join(os.path.dirname(os.path.abspath(a.out)), '_build')
    if not os.path.isdir(_bd):
        os.makedirs(_bd)
    tmp_html = os.path.join(_bd, os.path.basename(os.path.splitext(a.out)[0]) + '.print.html')
    # 🔴 中间件换目录后，源 HTML 里的相对路径会失效 ⇒ 注入 <base> 指回源目录（图必须照旧能取到）
    _base = 'file://' + os.path.dirname(os.path.abspath(a.html)) + '/'
    if '<base ' not in html:
        if re.search(r'<head[^>]*>', html, re.I):
            html = re.sub(r'(<head[^>]*>)', r'\1\n<base href="%s"/>' % _base, html, count=1, flags=re.I)
        else:
            html = '<base href="%s"/>' % _base + html
    _n, _missing = local_asset_refs(html, os.path.dirname(os.path.abspath(a.html)))
    print('   本地资源引用 %d 个%s' % (_n, '（全部存在）' if not _missing else ''))
    if _missing:
        print('   ❌ 有 %d 个本地资源取不到（图会静默消失、alt 会被渲染成文字）：%s'
              % (len(_missing), sorted(set(_missing))[:6]))
        return 1
    io.open(tmp_html, 'w', encoding='utf-8').write(html)
    print('① 打印版 HTML → %s' % tmp_html)
    header = a.header or ''
    if re.search(r'[\u4e00-\u9fff]', header):
        print('   ⚠️ 页眉含 CJK —— Chromium 页眉是独立文档、取不到内嵌字体，会退 Type3'
              '（复制粘贴坏）；已替换为 ASCII 占位')
        header = 'Daniel System Guide'
    mark = ''
    if a.footer_mark and os.path.exists(a.footer_mark):
        import base64
        mark = 'data:image/png;base64,' + base64.b64encode(io.open(a.footer_mark, 'rb').read()).decode()
    build_from_html(tmp_html, a.out, doc_title=title, header_text=header, footer_mark=mark)
    expect = _HTML_EXPECT['text'] + _HTML_EXPECT['markers']
    heads = _HTML_EXPECT['headings']
    print('② PDF → %s（%.1f KB）｜打印可见文本 %d 字符｜标题 %d 个'
          % (a.out, os.path.getsize(a.out) / 1024.0, len(expect), len(heads)))
    if not a.no_tounicode_fix:
        tmp = a.out + '.tmp'
        n_inj, n_fix = fix_text_layer(a.out, tmp, expect, title=title)
        os.replace(tmp, a.out)
        print('③ 文本层与元数据：注入 ToUnicode %d 个字体／归一码位 %d 处／元数据已重写'
              % (n_inj, n_fix))
    miss, _fonts = font_coverage(expect)
    okc = True
    print('=== 校验（字体覆盖）===')
    if miss is None:
        print('  ⚠️ 未安装 fontTools，跳过覆盖检查（--pip .kol-tools/_libs fonttools）')
    elif miss:
        okc = False
        print('  ❌ 有 %d 个字符不在所嵌字体里（会回退系统字体 → Type3 → 复制粘贴坏）：%s'
              % (len(miss), ' '.join('%s(U+%04X)' % (c, ord(c)) for c in miss[:30])))
    else:
        print('  ✅ 交付文本的每个字符都被所嵌字体覆盖（不会触发字体回退）')
    ok0, rep0 = verify_container(a.out)
    print('=== 校验（容器结构）===')
    for line in rep0:
        print(line)
    css_labels = re.findall(r'content\s*:\s*"([^"]{1,12})"', html)
    repeat_ok = list(_HTML_EXPECT.get('th_texts', [])) + css_labels
    ok, rep = verify_pdf(a.out, expect, header_texts=[header], repeat_ok=repeat_ok)
    print('=== 校验（内容）===')
    for line in rep:
        print(line)
    ok2, rep2 = verify_layout(a.out, headings=heads, furniture=[header])
    print('=== 校验（版面）===')
    for line in rep2:
        print(line)
    ok3, rep3 = verify_images(a.out)
    print('=== 校验（图片位置）===')
    for line in rep3:
        print(line)
    print_fingerprint(a.out)          # 🔴 必须在文本层修复之后：否则打的是中间态哈希（实测两次不一致）
    return 0 if (ok0 and ok and ok2 and ok3 and okc) else 1


def _plain_of_html(path):
    """HTML → 纯文本（用于 ToUnicode 的"源字符集"：只要字符集合，不需要顺序）。"""
    import re as _re
    h = io.open(path, encoding='utf-8').read()
    h = _re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=_re.S | _re.I)
    h = _re.sub(r'<!--.*?-->', ' ', h, flags=_re.S)
    h = _re.sub(r'<[^>]+>', ' ', h)
    return _html.unescape(h)


if __name__ == '__main__':
    sys.exit(main())
