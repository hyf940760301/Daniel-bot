---
name: kol-contract
version: 0.9.205
description: "KOL 合作合同的**出具与返工**：母版保真判据、母版与实测版面值、四步出件工序、PDF＝签署件／md＝可复制版的交付形态、未取得字段的留法、条款适配的唯一依据、rev2／rev3 返工版纪律、改版标黄、rev 版工程化与飞书「就地改章」、文档类交付件印刷级 PDF、系统功能指南写法、按 KOL 适配出件、合同上飞书（DocxXML 插入＋改动标黄）、飞书写入的破坏性操作纪律（CLS-86／CLS-87）、门禁长期口径（判定面／边界面／`--strict`／版本区与建票纪律 · §14.17）。Use when 要出具／返工 KOL 合作合同、做条款替换、出签署版 PDF、把合同推到飞书；关键词：合同、contract、母版、保真、条款、PDF、rev、DocxXML、标黄。"
whenToUse: "出合同前加载；交付前必过保真检查，不过不得交付。"
metadata:
  corpus_version: "0.9.205"
  corpus_source: "docs/marketing/skills/kol-intelligence.md"
  corpus_sha256: "54adc91c62b09c92e86597343fc0859a8665066603555cf1cec1d617233da57d"
  corpus_slices: "L4342-L5007"
  generated_by: "TICKET-148-语料束切分器.py"
---

# KOL 合同出具（母版保真）

> 本束是 `docs/marketing/skills/kol-intelligence.md`（版本 0.9.205）的**逐字切片**：判据原文在 `references/`，本文件只做导航与逐字摘录，**不改写任何判据**。

## 一、本束覆盖的源节

| 切片文件 | 源行区间 | 源节标题（逐字） |
|---|---|---|
| `references/50-contract.md` | L4342–L5007 | §14 合同出具（母版保真） |

> 读法：先看本文件的「核心判据速查」；需要完整判据时按上表 `read` 对应切片。

## 二、核心判据速查（逐字摘录 · 带源行号）

### §14 合同出具（母版保真）（源 L4342–L4397 逐字摘录）

## 14. 合同出具（母版保真）

> **本章定位**：把谈定的条款落进一份**正式合同**并发给对方签署。能力地图登记（逐字 · `_CAPABILITY-MAP.json` L100–127）：
> `id`＝`contract-issue`｜`entry`＝`## 14. 合同出具`｜`charter`＝`**7.60 合同出具`｜`instruments`＝`.kol-tools/check_contract_fidelity.py`／`.kol-tools/doc_to_pdf.py`｜`shape`＝PDF（签署件）＋ md（可复制版）
> **acceptance**：① 模板只许适配条款不许重排版 ② `check_contract_fidelity.py` 通过 ③ 改版标黄 ④ 未确认字段按下划线留白
> **登记纪律**（`_CAPABILITY-MAP.json` `_meta`）：本章为一级章，**必须在地图登记**（否则能力门 C10 FAIL）；锚点一律写「编号＋标题」整串。

### 14.1 合同出具＝「母版保真」（判据一句话）

> **用户原话（逐字 · `docs/roles/kol-expert.md` L797 ＝ 章程 §7.60）**：「我给你的那个模板文件，**保留所有的格式内容**，只是针对其中的条款进行对应 KOL 的适配，**你现在连格式都改了**。」

🔴 **判据一句话**：**合同是法律文件，版式即格式的一部分 —— 换版式＝换文件。** 第一版按自己的审美重排（US Letter／Times／3 页），**条款一字不差仍被退回**：格式是**客户与法务认这份文件的方式**，不是排版偏好。（逐字 · 章程 L798）

**通用化（逐字 · 章程 L804）**：凡「**用户给了母版、只要适配内容**」的交付物（合同／审核表／话术模板／PPT），**一律母版保真**：先量母版版式值，再只换内容。

**适用面**：合同（Marketing Service Agreement）、以及任何"给了母版只要适配内容"的交付物。
**豁免面**：用户明确要求重排版；或内容体量远超母版固定坐标容量 ⇒ 转 §14.7（保**版式语言**、正文自然下排）。

### 14.2 母版与实测版面值（逐字 · `docs/marketing/kol/_contracts/README.md` §二）

**版式母版** ＝ `inf-docs/@JordanPulmano_MarketingServiceAgreementSIGNED.pdf`

| 必须保留 | 母版实测值 |
|---|---|
| 页面／边距 | **A4 595.25 × 842**、左边距 **x=90**、右界 **505.25**、项目符号缩进 x=111 |
| 字号层级 | 大标题 **26.05pt 粗**（左对齐）／副标题 **15.95pt 粗**（居中）／节标题 **15.0pt 粗**／正文 **11.05pt** |
| 行距 | 正文 **15.2pt**；段落间距 ≥20.7pt |
| 重点加粗 | 模板对关键短语**真的加粗**（例：§2.2 `within **five (5) working days of** receipt…`），**必须逐字保留** |
| 项目符号 | Wingdings 实心圆点 → 回写为 bullet（矢量实心圆，直径 **5.60pt**、圆心在基线以上 **2.87pt**） |
| 署名区 | **两栏**：Party A 栏 x=90、Party B 栏 **x=339.84** |
| 结构 | 8 节：1 Term／2 Party A 义务／3 Party B 义务／4 Payment／5 IP／6 Confidentiality／7 Governing Law(HKIAC)／8 Miscellaneous ＋ `IN WITNESS WHEREOF` 双栏签署块 |

**字体事实（逐字 · 同表下方）**：Arial 在模板里是 **Type0 子集**（按字形 ID `<0055>Tj` 绘制）→ **无法原地改字**；回写用 metrically-compatible 的 base-14 **Helvetica / Helvetica-Bold**（字宽表**从模板实测**：`LTChar.width ÷ size`，复核误差 **±0.4pt**），故换行位置与模板一致。

🔴 **母版宽度表只覆盖母版出现过的字符**（逐字 · `README.md` §八 第 7 条）：正文改写用到新字符时 `text_width()` 会抛 `MissingWidth`（**故意失败要响**，不静默按 0 宽排版）⇒ 到 `template_contract_pdf.EXTRA_WIDTHS` 补标准字宽（实测：用户手改用了**直角撇号** `'`，字宽 191/238 与弯引号 222/278 不同）。

### 14.3 出件工序（四步 · 逐字 · `README.md` §三 ＋ 工作流节点 10＋`_samples/node-10` §二）

```bash
# ① 先看要替换哪几段（只报告、不写文件）
python3 .kol-tools/template_contract_pdf.py --report
# ② 把条款差异落成替换规则（编辑 SUBS / LINE_REWRITE）
# ③ 出 PDF ＋ 同源 md
python3 .kol-tools/template_contract_pdf.py \
  --out docs/marketing/kol/_contracts/<KOL名>-MarketingServiceAgreement-<YYYY-MM-DD>.pdf \
  --md  docs/marketing/kol/_contracts/<KOL名>-MarketingServiceAgreement-<YYYY-MM-DD>.md
# ④ 保真检查（不过不得交付）
python3 .kol-tools/check_contract_fidelity.py --template <母版> --new <新件> [--md <新件.md>]
```

**出完必验三项（逐字 · `README.md` §三「出完必验」）**
1. **叠字**：同一 y 上不得有文字区间交叉（曾因段落从中间被劈开而叠字）；
2. **位置键**：`(页, y, x, 文本)` 逐词比对模板 —— 未改动的词必须**逐词同坐标**，差异**只允许**出现在被替换字段上；
3. **页面**：页数、MediaBox（A4 595.25×842）与模板一致。

### 14.3.1 交付形态：**PDF ＝ 签署件 ／ md ＝ 同内容的可复制版**（强证据 · `_CHANGELOG` L279 · 0.9.62；§14.3.1 标题逐字见该条上下文）

> ⟪摘录止于 L4397；`references/50-contract.md` 尚有 L4398–L5007 未摘录⟫

## 三、版本与追溯（E6）

| 项 | 值 |
|---|---|
| 语料版本 | `0.9.205` |
| 源文件 | `docs/marketing/skills/kol-intelligence.md` |
| 源文件 sha256 | `54adc91c62b09c92e86597343fc0859a8665066603555cf1cec1d617233da57d` |
| 本束源行区间 | `L4342-L5007` |
| 切分器 | `docs/product/daniel-copilot/_impl/TICKET-148-语料束切分器.py` |
| 零丢失校验 | `python3 docs/product/daniel-copilot/_impl/TICKET-148-语料束切分器.py --verify` |

> 产物回填口径：交付物/回报中写明「本次用语料版本 0.9.205」。
