<!-- 本文件是 `docs/marketing/skills/kol-intelligence.md` L1494–L3209 的**逐字切片**（语料版本 0.9.204）；请勿在此改写判据，改动须回流源文件后重跑切分器 -->
<!-- 源节：§4 阶段 3 · Pitch 外联（结构 ＋ EN 模板库 ＋ §4.13–§4.24 信型骨架） -->

## 4. 阶段 3 · Pitch 外联（结构 + EN 模板库 v1）

> v0.3.0 升级：本阶段由"要素占位"升级为**完整 EN 模板库**（来源 = 真实语料分析 `docs/marketing/kol/2026-09-kol-pitch-email-analysis.md` §3/§4；2026-09-08 总监批准回写 P1–P7）。模板均为**通用化 [变量] 文本与写作规则**，不含真实人名/机构/报价（内部语料纪律）；对外以 EN 交付。
> 语义注（2026-09-08 修正）：语料（FED Fitness / Yarbo）即 MRP 项目邮件——T1–T5 为**写作框架参考**，邮件条款一律以 §4.7 MRP 规范为权威（邮件链路唯一=MRP，见 §4.7.1）。
> 写作纪律：个性化位=niche 描述词（须按目标频道内容替换，非通用词硬贴）；条款数值（权利期/日期/提及次数/付款比例）全信一致；每封发出前过 §4.5 发前变量校对清单。

### 4.0 邮件产品段写法标准（品牌口径优先 · v0.4.10 新增，来源=用户反馈 2026-09-10）

> **背景**：用户反馈"产品描述段过于扁平、缺差异化，根因是对产品剖析不深"；改造目标 = 让读者**直观感受到产品差异性与核心特点**。同时确立硬约束：**产品相关英文表述必须严格对齐品牌方口径，不得自由发挥**。

**A. 结构（四段式，替代"通用卖点罗列"）**

| 段 | 写法 | 反例（旧稿病灶） |
|---|---|---|
| ① 一句品类定义 | `[Product] is a [一句话品类解释] designed for [目标用户/场景]。`——取品牌官方定位句改写（是谁 / 给谁 / 干嘛），**不堆功能** | "display AI glasses built for work, conversation and everyday life — useful information appears naturally in your field of view"（无品牌依据、泛化） |
| ② 核心差异化 + 内容角度 | `What makes it especially interesting for content is [核心差异化]，which creates a natural story around [创作者内容角度/转变]。`——差异化**必须取品牌书明确标注的差异点**（如 THE CORE DIFFERENTIATOR 对比框），并翻译成"创作者可拍的故事线" | 只写 "It's not a gadget for one niche"（无对比、无画面感） |
| ③ Highlights 3 条 | **功能 / 日常 / 硬件** 三块各一条；每条 = **加粗命名 + 破折号 + benefit 句**（feature→benefit，禁参数堆砌、禁 "best in class" 式主观断言）；命名与措辞取品牌功能区**官方命名** | 参数并列堆砌（"high-brightness dual-eye display, a 4-mic array…49g frame"） |
| ④ SKU 行 + Content potential | SKU：单 SKU 产品写明"单 SKU 适配"（一支视频仅 1 个 SKU，额外 SKU 另报价）；组合产品给每 SKU 一行 `best for…`。Content potential：给 **3–5 个可拍内容角度**（依品牌书场景 + Brief），并注明可自由改编 | 占位 `[Product A, if any]` 未落地 / 无内容角度 |

**B. 纪律（硬门禁）**
1. **品牌口径唯一来源**：产品英文表述只能取自品牌官方物料（Brand Book / 官网原话），**禁止自由发挥、禁止编造参数与 SKU**；
2. **每份邮件必须附「品牌口径摘录表」**：逐条 = 口径项 / 品牌书英文原话（逐字）/ **页码**；邮件内每段产品句须能回溯到摘录表某行；
3. **品牌书未覆盖的表述** → 标 `[待品牌确认]` 并列入待确认清单（**不得**用行业通识或竞品话术补齐）；
4. **旧稿遗留参数须复核**：品牌物料未出现的数字（重量/语言数/亮度等）一律删除或待确认（实测：旧稿 49g、45+ languages 在 Brand Book 中不存在）；
5. **术语一致性（全称优先，与 §2.3.3 一致）**：同一功能在品牌书中若有官方命名，邮件须用官方命名，且**产品形态/功能术语必须用官方全称，禁简写/缩略/近似写法**（实测：品牌书写 "Halliday AI Assistant"/"Quick Research"，与口语化的 "AI Q&A" 不一致；定义句误用简写 "binocular display"、官方全称为 "binocular waveguide display"（p9）→ 一律以全称为准），存疑者列待确认；
6. **条款数值不外溢**：产品段只谈产品；usage/日期/提及次数等条款数值集中在条款段，且与独立条款邮件口径差异须显式列出请用户裁决（**不擅自统一**）。
7. **首封 / 条款分工口径（用户裁决 2026-09-10）**：**默认首封 = 产品说服 + 报价邀请（不含条款块）**；完整条款由**后续独立条款邮件**承担（Halliday 链路即此分工）。该口径**取代 MRP spec §1.1「一次写全关键条款、避免多轮往复」的默认解读**——后续新实例不得再默认把条款块内嵌首封；若项目另有要求内嵌条款，**以当次指令为准**。承接方式：首封 Timeline 句只写"发布窗口 + usage 期限"，其余条款（deliverables/preview/posting/payment/权利细节）全部落第二封，且两封对 usage 口径须一致。
8. **术语纪律（用户裁决 2026-09-10）**：产品功能/功能区的英文术语**一律采用品牌官方命名**（Brand Book / 官网原话），**禁用自造词、近似词与口语化改写**；同一功能在品牌物料中已有命名时，邮件须逐字使用（实测：口语化 "AI Q&A" → 品牌书 p14 官方命名 **"Halliday AI Assistant"**，并列可用 p12 "Quick Research"）；品牌物料中无对应命名的功能，标 `[待品牌确认]`，不得自行命名。
9. **跨品牌 Other Opportunities 标准段（用户裁决 2026-09-10 · 可复用资产）**：当项目隶属 **Google creator marketing program** 时，邮件末段可附"其他付费合作机会"标准段，格式为 **段首固定句 + 逐行"品牌 — 品类"清单 + 结尾两句（邀请提及 / 欢迎给组合价）**。当前品牌清单（11 个，用户确认版本）：

```
We're also supporting other paid YouTube collaborations through a Google creator marketing program, including:
- Boulies — gaming & ergonomic chairs
- FED Fitness — home fitness equipment
- Halliday — AI smart glasses
- INIA — beauty tech
- Laifen — personal care tech
- Shokz — open-ear audio
- Tenniix — smart tennis training
- UGREEN — consumer tech & smart home
- Velotric — e-bikes
- Waydoo — electric hydrofoil boards
- Yarbo — robotic yard care

If any of these brands also feel relevant to your channel, feel free to mention them in your reply. If you're open to multiple collaborations, you're also welcome to share a package rate.
```

> **使用纪律**：该段为**逐字资产**，套用时**不得改写品牌名与品类词**；**品牌清单变更须经用户确认后**方可更新（本 Skill 与实例文件同步）；若某次指令未提及该计划，则不出此段（默认不含）。实例落地：`docs/marketing/kol/2026-09-halliday-g2-pitch-email-draft.md` v4.2。

**C. 范本（Halliday G2 · 用户给定优化句，正例）**

- 差异化段：`works *during* the conversation, not just after it — most AI meeting tools record, transcribe and summarize what already happened, while the G2 is built for the moment when a decision is forming, a commitment is being made, or a question needs an answer right now.`（来源：Brand Book p10/p11 THE CORE DIFFERENTIATOR，逐字 + 只加"内容角度"过渡句）
- Highlights（三条，功能/日常/硬件）：
  - `**Meeting Flow** — works during the conversation, not just after it, helping you follow fast-moving discussions, get quick context, track decisions and commitments as they happen, and close the loop with clear summaries and follow-ups.`（p12 三支柱）
  - `**Everyday Features** — real-time multilingual translation, notes and talking points visible in your lenses, AI Q&A, notifications, a glanceable Dashboard, hands-free calls, and music & audio — all without constantly reaching for your phone.`（p14 六项官方命名）
  - `**Best-in-category Hardware** — a binocular waveguide display for clearer, more comfortable viewing, a 4-mic array tuned for meeting audio, built-in speakers, a camera-free design, prescription-lens support, and a lightweight frame built for all-day comfort.`（p9 + p6/p7）
- 落地实例（完整成品稿 + 品牌口径摘录表 + 待确认清单）：`docs/marketing/kol/2026-09-halliday-g2-pitch-email-draft.md`（v4.0）。

### 4.1 冷邮件要素结构（写前框架 · 8 步）

1. **Subject line**：公式 `[Brand] Paid [Platform] Collaboration | [OutcomeHook]`——品牌 + 付费属性 + **观众结果型卖点句**（如 "A Leaf Blower That Cleans the Yard on Its Own" / "35+ Exercises in One Home Gym"）；避免营销词堆砌。
2. **称呼 + 问候**：`Hi,` + `Hope you're doing well!`（统一称呼；个体化靠第 4 步 niche 词）。
3. **自我介绍**：`This is [SenderName] from [Agency], reaching out on behalf of [Brand].`（第三方代理明示与品牌关系）。
4. **个性化钩子 + 强匹配声明**：`We've been following your [NicheDescriptor] content and think your channel would be a strong fit for a paid collaboration featuring the [Product].`——niche 描述词=全文唯一"真个性化位"，按频道内容替换；轻夸（followed your content）+ 强匹配（strong fit），不吹捧过度、不点名具体视频亦可成立（软钩子）。
5. **价值段（problem→solution，1–2 句）**：卖"观众能获得的结果/场景"（建完整家庭健身房 / 大院子省时省力），**不堆参数**。
6. **Why bullets（3–6 条）**：每条 = **加粗利益点 + 冒号 + 支撑句**（feature→benefit 对，如 "Powerful performance: 21N blowing force, 174 MPH, 607 CFM"）；参数只出现在 bullet 支撑里，无 "best in class" 式主观断言。
7. **材料链接**：`Product: [URL]`（官网 / 零售 / collection 链接，与产品一一对应）。
8. **报价引导 + 条款块 + CTA**：详见 T1/§4.3；条款一次写全供红人定价，CTA 低门槛收尾。

### 4.2 EN 模板库（T1–T5 · 变量替换后即可发）

> ⚠️ **本节各模板的现行地位（2026-09-16 定 · 防多版本冲突）**：
> | 模板 | 地位 | 唯一权威 |
|---|---|---|
> | **T1** 首触 Cold Pitch | **写作框架参考**（可作为通用冷邮件结构；**MRP 项目不得直接用**——其条款含 `Usage rights [N] days`／`Mention [Brand] at least [N] times`／特写要求，属 §4.7.4 红线明令不得并入的条款） | 首封 → **§4.9**（MRP 最佳实践）／**§4.8**（MRP 标准模板） |
> | **T2** Follow-Up 1 | **已作废**（骨架与问价句均被 §4.11 取代） | **§4.11** |
> | **T3** Follow-Up 2 | **已作废**（旧「稀缺感＋样机」骨架） | **§4.11 第 10 条** |
> | **T4** 报价后确认 | **现行有效**（§4 无重复版本） | 本节 |
> | **T5** 婉拒 | **现行有效**（§4 无重复版本） | 本节 |
>
> **本节的排版骨架、变量表仍可复用**；但凡与上表「唯一权威」冲突处，**一律以权威节为准**。

> 每个模板附 ZH 用途注。变量清单见 §4.3 与各模板内 [变量]；**套用后必须过 §4.5 校对清单**。

**T1 · Cold Pitch（首触）**

```
Subject: [Brand] Paid [Platform] Collaboration | [OutcomeHook]

Hi,

Hope you're doing well! This is [SenderName] from [Agency], reaching out on behalf of [Brand].

We've been following your [NicheDescriptor] content and think your channel would be a strong fit for a paid collaboration featuring the [Product].

[One-line problem→solution for the viewer, audience-result framing — no spec dump here]

Why the [Product] is worth featuring:
- [BenefitPhrase]: [supporting facts tied to the benefit]
- [BenefitPhrase]: [supporting facts]
- [BenefitPhrase]: [supporting facts]     (3–6 bullets, benefit first)

Product: [ProductURL]

If you're interested, please share your rate based on the following requirements:
- Deliverables: [Deliverables]
- Usage rights: [N] days of usage rights, including Brand Partner Access, re-editing, cross-platform promotion, and paid advertising.
- Video Timeline: Once the collaboration is confirmed, we'll ship the product as soon as possible, and we hope to have the video published around [TargetDate].
- Preview Link: Within [X weeks] of receiving the product, please send us an unlisted preview link for review and make any necessary revisions based on our feedback. Our review will be limited to product information and factual accuracy, so you're free to maintain your own creative style.
- Posting requirements: Include [ProductName] in the video title and add our product link and hashtags to the description. Mention [Brand] at least [N] times, show the product in use, and include at least one clear product close-up.
- Payment: 50% of the payment will be made upon receipt of the preview link. The remaining 50% will be paid after the video is successfully published. Please let us know if this is okay for you!
[optional] - Content approach: [demo points to hit]

[optional product-specific] Please include any applicable [production/assembly/return-shipping] costs in your total quote. [optional] Please also share [context questions needed to match product/environment].

[optional backup] If the [Product] isn't the right fit, we're also looking for creators to feature [BackupProduct or BackupCampaign]. Please let us know if either opportunity sounds more relevant to you.

We'd love to hear your thoughts and explore a collaboration.

Best,
[SenderName]
[Agency]
```

- ZH 用途注：Subject=品牌+付费属性+观众结果钩子；钩子段=轻夸+匹配声明（niche 词真个性化）；价值段=卖结果不卖参数；bullets=利益点+支撑对；**报价引导="please share your rate"——主动权给红人，不先亮预算**（红人回价后用 §5.1 CPM 判据对照，见 §4.6）；条款块=一次写全供其定价；付款=50/50 绑定可核验节点（预览收到付 50%、发布成功付 50%）；复审边界句=限事实准确性、让渡创作自由（保创作意愿+守合规底线）；备选 offer=主品不合适不流失；发布要求全部可核查（title/描述 link+hashtags/提及次数/使用展示/特写）。

**T2 · Follow-Up 1（轻提醒 · 首触后 ~7 天）**

```
Following Up: [Product] Paid Collaboration

Hi,

Hope you're doing well!

Just wanted to follow up in case my previous email got buried in your inbox 😊

With [Season/Event] just around the corner, this is when [AudienceGroup] start looking for [Problem/Topic]. We think a timely review of the [Product] could be especially relevant to your viewers and well positioned to capture seasonal search interest.

[1–2 lines restating sharpest value + differentiator vs the conventional solution]

Would you be interested in exploring this paid collaboration? If so, please share your rate for the package outlined in my previous email and let us know whether you could complete the video preview by [Date].

Looking forward to hearing what you think!

Best,
[SenderName]
[Agency]
```

- ZH 用途注：轻提醒（buried-in-inbox 自嘲 + 😊 降压力）；**不重发整段条款**（引"previous email 的 package"）；给"时机/相关性理由"（季节/事件/搜索热度）而非催促；再问并给时限锚（如预览完成日）把球推回。

**T3 · Follow-Up 2（再 ~7 天后）｜ ⚠️ 本节骨架已作废，现行口径见 §4.11 第 10 条（价值提案型）**

```
Following Up: [Product] Paid Collaboration

Hi,

Hope you're doing well!

Just wanted to follow up once more in case my previous emails got buried in your inbox 😊

We're still inviting a few creators to test the [Product], and your [NicheDescriptor] content was one of the reasons we thought of reaching out.

We'd genuinely love to see how the [Product] performs in your [real-use scenario]—[scenario detail 1], [scenario detail 2], and [scenario detail 3].

If it sounds interesting, we'd be happy to provide a [Product] unit for filming and discuss a paid collaboration. Please feel free to share your rate and availability if you'd like to explore it with us.

Looking forward to hearing what you think!

Best,
[SenderName]
[Agency]
```

- ZH 用途注：终次标 **Final**；稀缺感（still inviting a few creators）+ 个人理由重申（你的内容是找你的原因之一）+ **真实场景使用愿景**（激发创作者画面感）；offer 样机；仍不重复条款、不施压。

**T4 · 报价后确认（红人回价后 · 成交前对齐信）**

```
Subject: [Product] Collaboration — Confirming a Few Details

Hi,

Thank you for your interest and for sharing your video packages.

Before we decide which package would be the best fit, could you please help us confirm a few details?
1. Do your quoted rates include [N] days of usage rights, including Brand Partner Access, re-editing, cross-platform promotion, and paid advertising?
2. We're aiming to have the content published around [Date]. Would that work with your current schedule?
3. An unlisted preview link within [X weeks] of receiving the product, with revisions based on our feedback. Our review will only cover product information and factual accuracy, so you can maintain your own creative style.
4. Would you be open to testing the [Product] in [real-use condition]? Possible content angles include:
   - [Angle 1: common pain point with the old way]
   - [Angle 2: real-material / real-scenario test]
   - [Angle 3: performance, coverage, ease-of-use evaluation]
   - [Angle 4: signature capability demo]
   - [Angle 5: comparison vs the conventional alternative]
These are reference ideas only—you can select the angles that best fit your creative style and filming conditions.

To help us determine which [product variant / offer] would suit your channel best, could you also share:
- [Context Q1: location / seasonality]
- [Context Q2: environment size / usage scale]
- [Context Q3: variant-relevant condition, e.g., heavy snowfall / leaf fall]

Looking forward to hearing your thoughts!

Best,
[SenderName]
[Agency]
```

- ZH 用途注：成交前**对齐信**——①条款逐条复述确认（防误解成交后扯皮：权利期是否含在报价、档期、预览规则）；②内容角度给 **5 条"参考 ideas 非指令"** 并显式声明创作自由；③采集环境/场景信息（位置/场地大小/季节条件）用于**匹配哪款产品/怎样拍**（产品选择变成"按对方环境匹配"）。不作"已锁档"宣告。

**T5 · 婉拒（不合适 · 关系维护）**

```
Subject: Re: [Product] Collaboration — [BriefRef]

Hi,

Thank you so much for getting back to us and for sharing your rates and thoughts on the [Product]. We really appreciate your time and the great work you do!

After reviewing our budget allocation and overall campaign scope for this specific round of promotions, we unfortunately won't be able to move forward with the [QuoteTier] package at this moment.

Given how well your audience aligns with [Brand], we would love to keep in touch and consider future opportunities when new budget tiers or different campaign formats become available.

Thank you again for your interest, and we wish you all the best with your upcoming content!

Best regards,
[SenderName]
[Agency]
```

- ZH 用途注：拒绝点=**本轮具体报价档/本轮范围**（公司侧理由：budget allocation / campaign scope），**不点破红人问题**（不评价报价贵、频道不够好）；明确夸受众匹配 + 承诺未来档位/格式（红人池是长线资产，婉拒即关系维护邮件）。

### 4.3 条款块变量表（P1 · 术语默认来自真实语料常用值，按项目调整）

> ⚠️ **现行地位（2026-09-16）**：本表是**通用条款变量/措辞参考**。**MRP 项目的权威条款清单＝§4.7.3**（其上级权威为 `docs/marketing/kol/_spec-mrp-pitch-email-2026-09.md`）＋**§4.10**（合作条款邮件最佳实践）。**本表不得作为 MRP 邮件的条款依据**——其中部分条目属 §4.7.4 红线明令不得并入者（如 30/60 天 usage、提及次数 ≥3、特写要求）。

| 条款项 | 变量 / EN 默认写法 | ZH 说明 |
|---|---|---|
| Deliverables | One dedicated YouTube video of at least 8 minutes and one 60-second YouTube Short | 交付物（时长下限 + 短视频配发）按项目改 |
| Usage rights | [30/60] days of usage rights, including Brand Partner Access, re-editing, cross-platform promotion, and paid advertising | 权利期按项目（语料常见 30/60 天）；"paid advertising" 含付费投流须法务口径确认 |
| Video Timeline | ship as soon as possible after confirmation；publish around [TargetDate] | 发布目标日=季节/需求高峰锚（P7）；不承诺物流硬日期 |
| Preview Link | unlisted preview within [2 weeks] of receiving product；revisions per feedback | 复审边界句：review limited to product information and factual accuracy + creative freedom 让渡（必写） |
| Posting requirements | product name in title；product link and hashtags in description；mention [Brand] ≥[3] times；show product in use；≥1 clear close-up | 全部"可核查可回传"动作（便于验收与 tracking link 归因） |
| Payment | 50% upon receipt of preview link；50% after successful publish | 绑定可核验节点；金额口径（一次性/CPM/佣金%）另按 §5 |
| Content approach（可选） | Demo points to hit | **须与主推产品一致**（见 §4.5 红线 1 教训） |
| 附加成本（可选） | production / assembly / return-shipping costs in total quote | 按项目（样机寄回/组装/关税等） |
| 备选 offer（可选） | If [Product] isn't the right fit, we're also looking for creators to feature [Backup]… | 主品不合适→二产品/二 campaign，防一次性流失 |

### 4.4 跟进节奏与 Subject 轮次规则（P2）｜ ⚠️ **本节标题公式与轮次口径已被 §4.11 取代（2026-09-16）**，保留仅作沿革；**执行一律以 §4.11 为准**

- 节奏：首触 → ~7 天 **Follow-Up 1** → ~7 天 **Follow-Up 2（Final）** → 归档"无回应"（总触达 ≤3 次，与 §4.1 第 8 步纪律一致）。
- Subject 显式标轮次：首触=`[Brand] Paid…Collaboration | [hook]`；FU1=`Following Up on the …`；FU2=`Final Follow-Up: …`。
- FU1 内容=轻提醒 + 时机/季节理由 + 再问给时限；FU2 内容=稀缺 + 个人理由 + 使用愿景 + offer 样机；两者都**不重复整段条款**、无催促措辞。
- 渠道记录状态机不变：`待发 → 已发 → 已回复 → 跟进中 → 已约谈 / 婉拒 / 无回应`。

### 4.5 发前变量校对清单（P5 · 每封发出前逐项过）

- [ ] **产品名全信一致**：Subject / 价值段 / Why bullets 首词 / Product 链接 / Content approach 行 各处引用的产品名与型号一致（⚠️ 教训红线：真实语料曾出现 SR2 邮件 Content approach 行误写另一型号 MW5 的变量错位 bug——模板多槽位复用必逐槽交叉校对）
- [ ] 链接与产品对应（官网/零售/collection URL 无串品）
- [ ] 条款数值一致（权利期天数/发布日期/提及次数/付款比例 在"条款块"与后续 T4 复述两处同值）
- [ ] niche descriptor 与目标频道内容一致（非通用词硬贴）
- [ ] 备选 offer 的产品/campaign 名方向写对（主品↔备选不写反）
- [ ] 占位符清零（无 [变量]、无残留模板标记）
- 沿用本阶段既有检查：每封 ≥1 处真实个性化引用；未同模板无差别群发；未承诺预算外条件；渠道可测时如实记录打开/回复率；跟进 ≤3 次。

### 4.6 报价回传衔接（P6）与季节/真实环境锚定（P7）

- **share your rate → CPM 对照流程（P6）**：cold pitch/FU/确认信统一"请红人 share your rate"（不先亮预算，条款块=其定价依据）→ 收到报价后先折算 CPM（合作费用÷预估播放×1,000）对照 §5.1 区间判断是否离谱 → 定价档落入合理带即按 §5 目标价/上限流程走；偏贵→以市场带为锚谈（§5.1 谈判砍价应用）；上限不破、超限回报总监。
- **季节/真实环境锚定（P7 · 贯穿选品→pitch→执行）**：pitch 时机、FU 理由、T4 场景采集与内容角度、发布目标日均按**目标市场季节与真实使用环境**锚定（庭院类=秋季落叶/冬季除雪、发布卡需求高峰；安防/婴儿类=真实家庭/夜间场景）；产品匹配与"内容适季"是同一逻辑。

### 4.7 项目打标（Tag）机制 与 [MRP 建联邮件] 标签块

**4.7.1 邮件链路打标（2026-09-08 语义修正：当前邮件链路唯一 = MRP 建联邮件）**
- **当前唯一邮件链路 = [MRP 建联邮件]**：用户确认——FED Fitness / Yarbo 参考邮件**本身就是 MRP 项目邮件**；**不存在"通用 vs MRP"双路径**（v0.3.1 的并列标签为误设，已修正）。
- 语料/模板与规范的关系：§4.2 T1–T5 模板库与 §4.3 条款变量 = 由 MRP 项目邮件语料提炼的**写作框架/结构参考**（仍有效）；MRP 规范 `docs/marketing/kol/_spec-mrp-pitch-email-2026-09.md` = **条款权威**（§1.1 常规 6 项 + §1.2 Google 官方视频要求 5 项 + 审核门禁）；两者冲突处以规范与当次指令为准。
- **今后"邮件生成"任务默认走 MRP 链路**：MRP 条款（§4.7.3）+ 发前审核门禁（§4.7.2），不再设标签选择；**若未来出现非 MRP 的新邮件链路，由用户显式告知后再新建标签**（禁止自行推广适用）。
- 链路特性提醒：MRP 条款含 Google 官方视频要求（口头提及 ≥1 / Shorts ≤60s / 实际使用演示 / 单 SKU / 发布后 30 天 Brand Partner Access 等）；spec 外条款（如 30/60 天 usage、提及次数 ≥3、特写要求）不并入邮件。

**4.7.2 [MRP 建联邮件] 适用与流程**
- 适用：MRP 项目建联 Pitch Email；**流程 = 撰写（一次写全关键条款，避免多轮往复）→ 发前审核 → 批准后业务人工发送（代理不直发）**。
- **发前审核门禁：默认审核人=总监；若当次指令指定其他审核人，以当次指令为准**（Skill 内不复制审核人姓名；详细原要求含历史备注见 spec 文件）。
- 中文要求（spec §1）为**权威**；§4.7.3 的 EN 措辞为本角色起草的**建议草案 v1**，发前仍须按 spec/审核校准。

**4.7.3 MRP Pitch Email 必含条款（EN 邮件条款块 v1 草案 + ZH 注）**

> **权威顺序**：中文要求（spec §1）**为权威** → 本节 EN 措辞为起草草案 → §4.10 为合作条款邮件最佳实践。三者冲突时按此顺序。


*常规条款 6 项（按 spec §1.1 起草）：*

```
- Format, rate & payment: please confirm the video format, your rate, and your preferred payment method in one reply so we can keep things moving quickly. [常规1]
- Payment schedule: payment will be split into two installments — the first after you share the unlisted preview link, and the second after the video is published. We'll also work with the payment method that suits you best. [常规2]
- Timeline: can you share an unlisted preview link within two weeks of receiving the product? [常规3]
- Content brief & revisions: we'll share a content brief for your reference; please review the final cut against it and make revisions where there are factual errors or promotional/marketing language mistakes. Beyond factual and promotional accuracy, creative direction stays yours. [常规4]
- Title & description: please include the product name in the video title, and add our purchase tracking link and hashtags to the description. [常规5]
- Footage permission: may we ask for permission to reuse clips from your video for promotional campaigns on other platforms, including reposting and re-editing? [常规6]
```

*Google 官方视频要求对应条款 5 项（按 spec §1.2 并入）：*

```
- Brand mention: the video must include at least one verbal mention of the brand on camera. [Google1]
- Shorts length: Shorts must be ≤60 seconds (we strongly recommend shorter than 60s so they loop cleanly in Partnership Ads). [Google2]
- Product demo: the video must show real, in-use demonstration of the product. [Google3]
- Single-SKU: each video may promote only one product SKU; adjacent or series products count as additional SKUs and will incur an extra fee. [Google4]
- Brand Partner Access: after publication, please grant 30-day Brand Partner Access to the brand (per the Google program requirement). [Google5]
```

- ZH 注：常规 1–6 = 视频形式/报价/付款方式一次写清 ｜ 分两次付款（综合网红付款方式留弹性）｜ 两周内非公开 preview ｜ content brief 拍摄 + 仅"事实错误或宣传语言错误"可改 ｜ 标题产品名 + 追踪链接 + hashtags ｜ 片段跨平台转发与二次剪辑授权**询问**。Google 1–5 = 口头提及 ≥1 ｜ Shorts ≤60s（建议 <60s 保 Partnership Ads 投流）｜ 实际使用画面演示 ｜ 单 SKU（系列=额外 SKU 加费）｜ 发布后 30 天 Brand Partner Access。
- **红线**：MRP 块只含 spec 已有要求；**不得添加 spec 未含的条款**（如 30/60 天 usage 权利、提及次数 ≥3、特写要求等通用语料条款**不并入** MRP 邮件）。

**4.7.4 差异提示表（MRP 规范 vs 语料写法 T1–T5 · 同属 MRP 链路，条款以 MRP 规范为准）**

| 维度 | 语料写法观察（T1–T5 提炼 · 仅写作框架参考） | MRP 规范条款（权威） |
|---|---|---|
| 付款 | 50% preview + 50% 发布（"如可接受请告知"） | 分两次付款 + **综合网红提出付款方式给弹性** |
| 拍摄/修改 | review 限"产品信息与事实准确性" | 按 **content brief** 拍摄；仅"事实错误或宣传语言错误"可改 |
| 品牌提及 | 提及 ≥3 次 + 特写等 | **口头提及 ≥1 次** + 实际使用画面演示 |
| SKU | 未限制 | **单 SKU**（相邻/系列=额外 SKU 加费） |
| Shorts | 60-second Short（语料默认） | ≤60s（建议 <60s 保 Partnership Ads） |
| 权利 | 30/60 天 usage（含 Brand Partner Access 等） | 发布后 **30 天 Brand Partner Access**（Google 要求） |
| 片段授权 | usage rights 已含 re-editing/cross-platform，未单独询问 | **明确询问**跨平台转发与二次剪辑授权 |
| 审核 | 无强制审核记录 | **发前审核门禁**（默认总监，批准后业务人工发送） |

**渠道与记录**：邮箱（品牌域名邮箱优先）/官网 contact 表单/私信（按平台规则，不绕权限）；状态机见 §4.4。

**检查清单（阶段 3 交付前）**
- [ ] 已套用 T1–T5 对应模板并替换全部 [变量]
- [ ] 通过 §4.5 发前变量校对 6 项
- [ ] 条款数值跨位置一致；付款/权利期/日期有总监预算与法务口径支撑
- [ ] 报价回传已按 §4.6 CPM 对照流程评估
- [ ] 未承诺预算外/未经批准的条件；记录打开/回复率（如实）
- [ ]（邮件任务默认 MRP 链路）发前已过 §4.7.2 审核门禁（默认总监；当次指令另有审核人以当次为准），批准后交业务人工发送

### 4.8 MRP 首封标准模板（用户提供的真实样例 · v0.6.3 收录为规范）

> 来源：用户 2026-09-10 提供的真实 MRP 首封邮件（Halliday G2）。**本模板即"标准格式与措辞基准"**——格式、段落划分、措辞精确度均以本样例为准；实例落地见 `docs/marketing/kol/2026-09-halliday-g2-pitch-email-draft.md` v4.5。

**结构（7 段 · 无小标题 · 无项目符号清单化产品段）**
1. **问候 + 自我介绍（同一段）**：`Hi,` 换行 `Hope you're doing well! This is [Sender] from [Agency], a leading digital marketing agency based in China, trusted by brands like [背书品牌…], etc. We're reaching out on behalf of [Brand] about a paid [Platform] collaboration featuring the [Product].`
2. **匹配声明（通用表述，无 niche 占位）**：`We've been following your content and think the product could fit naturally into the kind of content your audience already enjoys.`
3. **产品段**：一句官方定义 → `A few quick highlights:` → 3 条不缩进要点（功能/日常/硬件）——文本见 §2.3.5 正例。
4. **链接行**：`You can take a quick look here: [URL]`
5. **条款行**：`The content needs to be published around [Month] and will include [N] days of YouTube Brand Partner Access.`
6. **报价询问（三档）**：`If you're interested, could you share your rates separately for:` + ①视频(8+ min)+Short ②视频(8+ min) ③Short(≤60s)
7. **跨品牌机会段**：`We're also supporting other paid YouTube collaborations through a Google creator marketing program, including:` + **纯文本逐行"品牌 — 品类"清单**（不用项目符号、不含当前品牌本身）+ 结尾两句（邀请提及 / 欢迎给组合价）；署名 `Best,` / `[Sender]` / `[Agency]`

**格式纪律（实测差异点，务必对齐）**
- 问候与自我介绍**同段**（不拆两段）；产品段与 Highlights 之间**不空行**；品牌清单**不用 `-` 符号**；署名用 **`Best,`**（非 `Best regards,`）；
- 产品段**不加** `About the Product` 之类小标题；**不加** SKU 行 / Content potential / 氛围图占位（除非当次指令要求）；
- 措辞**精确到样例用词**：`around October`、`YouTube Brand Partner Access`（非 "paid usage"）、`could you share your rates separately for`（默认不加 `in USD`）；如需偏离，须先向总监/用户确认。

### 4.9 MRP 首封 Pitch Email 最佳实践（v0.6.27 · 来源＝用户指定的 `inf-docs/Halliday 新版本pitch email.md`）

> **权威来源**：新项目要发首封 pitch 时，**直接按该文件的格式、排版与措辞产出**（下文为其结构与逐字骨架）。适用：MRP（Google creator marketing program）链路的付费 YouTube 合作建联首封。

**邮件结构（顺序固定）**
1. **Subject**：`<品牌> Paid Collaboration | <一句话产品钩子>`（例：`Halliday Paid Collaboration | AI Glasses That Enhance Every Moment`）。
2. **开场自我介绍**：`Hope you're doing well! This is <署名> from **Global OneClick**, a leading digital marketing agency based in China, trusted by brands like **DJI, OPPO, Anker Innovations, etc.** We're reaching out on behalf of **<品牌>** about a paid YouTube collaboration featuring the **<产品全称>**.` ＋ 一句个性化：`We've been following your content and think the product could fit naturally into the kind of content your audience already enjoys.`
3. **产品定义句（品牌官方口径）**：`<产品> is a **<品类定义>**, built to <核心价值> — designed for **<人群>**, with <关键差异点>.`（术语必须用品牌官方全称，见 §2.3.3）
4. **A few quick highlights（三条）**：① 核心场景功能（Meeting Flow 式，讲「在场景里解决什么」）② Everyday Features（日常功能串写一行）③ Best-in-category Hardware（硬件/形态/舒适度）；每条格式 `- **<小标题>** — <一到两句>`；三条之后给官网产品链接一行。
5. **发布窗口与权益**：`The content needs to be **published around <时间>** and will include **60 days of YouTube Brand Partner Access**.`（窗口与 usage 期限须与后续条款邮件一致）
6. **问价段（三档并列，格式固定）**：`If you're interested, could you share your rates separately for:` ＋ 三个 bullet：`**1 dedicated YouTube video (8+ minutes) + 1 YouTube Short**`／`**1 dedicated YouTube video (8+ minutes)**`／`**1 YouTube Short (up to 60 seconds)**`。
7. **Other Opportunities 段（仅 MRP 链路）**：`We're also supporting other paid YouTube collaborations through a **Google creator marketing program**, including:` ＋ 逐行「**品牌** — 品类」清单 ＋ `If any of these brands also feel relevant to your channel, feel free to mention them in your reply. If you're open to multiple collaborations, you're also welcome to share a **package rate**.`（品牌清单逐字不改写；非 MRP 项目删除本段）
8. **落款**：`Best,`／署名／`Global OneClick`（三行）。

**格式与排版纪律**：纯文本（星号在邮件客户端渲染为粗体）；段与段之间**空一行**；highlight 与问价用 `- ` bullet；关键信息（品牌名、产品名、时间、BPA 天数、档位、package rate）加粗；**首封不含条款块**（条款走独立第二封，见 §4.10 与 §4.0 第 7 条）；不承诺价格、不自造规格。

### 4.10 合作条款邮件最佳实践（v0.6.27 · 同源）

> ⚠️ **条款体系的唯一权威链（2026-09-16 定）**：`_spec-mrp-pitch-email-2026-09.md`（中文规范·**最高权威**）→ **§4.7.3**（MRP 必含条款 EN 草案）→ **§4.10**（本节·合作条款邮件写法）。**§4.3 仅为通用变量参考**，不作为 MRP 条款依据。

**开场（固定句）**：致谢兴趣 → `**Please note that all terms listed below are open for discussion**` → `We would appreciate it if you could **include your response** to each of these terms in your reply email:`。

**七条条款（顺序与措辞固定，编号 1–7）**
1. **Content**：`one dedicated YouTube video of at least 8 minutes` ＋ `an agreed collaboration fee of **[XXX USD]**`
2. **Shipping & Schedule**：发货与预计送达 **7–10 天**、期望发布时间（如 October）、询问档期
3. **Draft Preview**：① 发布前给 **unlisted preview link** 供审核（`We will only check for objective mistakes relating to the product introduction while respecting your creativity`）② 长视频预览**收货后 14 天内**、短视频**7 天内**；否则请对方给出所需时间
4. **Partner Access & Usage**：① 发布后发 **Brand Partner Access 邀请、60 天**，请接受以便关联官方频道做活动追踪 ② 征求再剪辑与在**社媒/官网/Facebook ads/Google ads** 使用的授权
5. **Payment**：**50% 收到预览链接后支付，剩余 50% 最后一条视频发布后支付**
6. **Publishing Requirements**：标题含品牌与产品名、描述区加我们提供的 **tracking link 与 hashtags**、视频**至少保留一年**
7. **Deliverables**：拍摄前提供 **brief**（产品要点、建议 talking points、拍摄参考），尊重创作自由；需**真实使用产品**且**出镜口头提及品牌至少一次**

**收尾（固定句）**：确认细节后发 contract → `We are open to discussing any adjustments needed.`；`If everything above looks good to you, we'd be happy to move forward and share the content brief.` ＋ `Best regards,`／署名／`Global OneClick`。

**排版纪律**：编号列表 1–7；每条**加粗小标题＋冒号**；子项用二级编号；金额、天数、期限、链接、hashtag 等**可执行要素加粗**；不新增品牌方未给出的条款。

### 4.11 Follow Up 邮件（首轮未读/未回 · 两轮上限 · v0.6.34 按最佳实践重写）

> **权威来源**：用户 2026-09-13 给定的最佳实践（Shokz OpenRun Pro 2 实例；**第二轮骨架已于 2026-09-15 改为价值提案型**，见第 10 条）。**后续所有项目的 follow up 阶段邮件一律按此标准产出**；本节的"两轮"取代早期版本中"二次 bump 保留三档问价"的写法。

**最佳实践共性（逐条照抄）**
1. **标题公式（不写 `Subject:` 前缀）**：**第一轮 = `Following Up: <Product> Paid Collaboration`**。
   - 🔴 **2026-09-16 用户裁定：本条只是「第一轮」的标准与规范。** 用户原话：「定版口径是 follow up **第一轮**对应的标准和规范，跟 follow up **第二轮**的标准和规范是**两封邮件内容**」。
   - **因此第二轮不由本条推导**：`2026-09-halliday-g2-followup-email-draft.md` 第二轮写 `Final Follow-Up:` **暂不改动**（用户明确"暂时先不动"）；**第二轮专项规范待用户给出后再固化**——在此之前第 10 条只约束**内容骨架**（价值提案型三点结构、180–220 词），**不约束第二轮标题**。
   - **沿革留痕（防误引）**：**0.6.87** 曾把标题公式写成"两轮统一、第二轮去掉 `Final`"，该解读**已由本次裁定收窄为仅第一轮**，**不得再据 0.6.87 推导第二轮标题**。
   - 两轮封顶，第二轮之后不再联系。
2. **第一轮的五段骨架（⚠️ 第二轮不用此骨架——第二轮用第 10 条的三点价值提案结构）**：`Hi,` → `Hope you're doing well!` → **`Just wanted to follow up once more in case my previous emails got buried in your inbox 😊`** → 个性化 + 场景句 → 问价句 → `Looking forward to hearing what you think!` ＋ `Best,` / 署名 / `Global One Click`。
3. **个性化锚点必写**：引用对方内容类型（`your tech review content`），第一轮可加一句"这也是我们想联系你的原因"；第二轮压成 `felt like a great fit`。
4. **产品段＝首封 pitch 的「两句法」精炼（2026-09-13 用户裁决，**取代**早期「只写场景句、不写产品」的写法）**
   - **句①＝差异性与品类定义**：把首封定义句压缩，**必须保留品牌差异点**——`camera-free`（对佩戴者与周围人的隐私）＋ `binocular waveguide display`（信息直接显示在镜片里）；不写参数、不写 `best-in-class` 式自夸。
   - **句②＝核心特性**：只挑**官方命名的 3–4 项**最关键功能一句连写（`notes / talking points / real-time translation in your lenses`、`Halliday AI Assistant`、`hands-free calls`）；**不列 bullet、不做场景枚举**；句末可挂 ≤8 词的个性化锚点（`A natural fit for your tech review content.`）。
   - **第二轮的产品句**：按第 10 条"价值提案型"写法——产品差异化特性要**嵌在"为什么适合他的观众"论证里**（不再单独压缩成一句定义），但**仍必须保留官方差异点与官方术语**（camera-free／binocular waveguide display／invisible display）。
   - **门禁**：**第一轮** 产品段 ≤2 句、≤65 词，正文 90–120 词（实测 Halliday 第一轮 120）；**第二轮**为「价值提案型」三点结构、正文 **180–220 词**（见 §4.11 第 10 条；旧「第二轮 ≤50 词」已作废）。出现「场景清单式枚举却没有差异点」即不合格（错题 59）。
   - 措辞只能取自首封 pitch／品牌物料原话（遵循 §4.0 纪律 1–2），禁止自造卖点。
5. **问价句统一**：`If it sounds interesting, we'd be happy to provide a <Product> for filming and discuss a paid collaboration. Please feel free to share your rate and availability if you'd like to explore it with us.`
6. **篇幅**：**第一轮**约 90–126 词、5–6 行正文（极简 check-in）；**第二轮**按第 10 条为 **180–220 词**（价值提案型，需容纳证据与曝光承诺）；两轮共同禁写：**不写**产品**长**定义段（产品信息按第 4 条两句法精炼）、Highlights 列表、三档报价清单、其他品牌合作段。
7. **语气低压力**：一个 😊（开场句末）；不写"最后机会/涨价前锁档/请尽快回复"，不设回复期限。
8. **两轮封顶**：第二轮无回复即停止，不做第三轮。
9. **回信方式**：一律在原线程内回复，仅替换标题的轮次前缀。
   **标题写法（2026-09-16 用户口径）**：follow-up 的邮件标题**不写 `Subject:` 前缀**——它是原线程的回复、标题由线程继承，草稿里带前缀既多余、又容易被整段复制进标题栏。**标题即正文首行、直接写文本**（如 `Following Up: Halliday G2 Paid Collaboration`），模板中的 `Subject:` 标签一律不出现在交付稿里。
10. **第二轮＝「价值提案型」（2026-09-15 用户给定新模板 · 取代此前的"同一低压力骨架＋只做减法"）**

> **口径变更原因（用户原话）**：第二轮应"**从和我们合作如何对网红有好处**"来写，而不是再礼貌提醒一次。旧版（极简 check-in）保留为**第一轮**的写法。

**固定三点结构（顺序不可换）**
| # | 角度 | 硬要求 |
|---|---|---|
| ① | **合作价值先说清** | 开头即给"**可提供价值 $X 的样品 ＋ 讨论付费合作**"；$X 必须取**官方售价**（Halliday G2 = **$599**，官网产品页实测 2026-09-15），**禁编造金额** |
| ② | **符合观众兴趣** | 先写观众是谁/关心什么 → 再给**产品差异化特性（官方术语）** → 落到"为什么适合他的观众"；**必须附往期表现好的同类视频作为证据**（格式：`标题 — XXK views: 链接`，1–3 条，优先"同类创作者 × 同品类产品"、播放量最好者） |
| ③ | **额外曝光** | 说明会通过**品牌官方渠道／产品页／付费加热**帮助内容触达频道之外的观众；**只承诺可执行项**，未获品牌方保底不得承诺具体播放量 |

**保留不动的纪律**：原线程回复；**只问 rate and availability**（不列档位、不列 feature 清单）；**不施压**（禁 `this will be my last note`／`if the timing isn't right…` 等收束表达）；两轮封顶；术语一律官方口径；正文不写产品长定义段与三档报价清单。

**证据纪律（新增 · 硬门禁）**：视频**链接必须真实可点**——自有语料若只存了标题与播放量（无 videoId），**必须先用 `getChannelVideos` 补出 videoId 再生成链接**；**链接未补齐前不得发送**；播放量用 `XXK views`（取整到千，来源为官方数据）；**禁编造链接或夸大播放量**。

**校验**：正文 180–220 词；三点齐全；样品金额来自官方；两条例证含真实链接；无禁用词；无施压语气。



**错题（follow up 线）**
- **错题 61**：把用户的「第二轮只是更精炼」误读成「两轮要写得明显不同」，第二轮改用了 `I don't want to keep filling your inbox, so this will be my last note on this one.`、`If the timing isn't right, no problem at all`、`Thanks either way` 等收束／施压语气 —— 用户 2026-09-13 第二次退回并给出 Shokz Final 轮模板：**第二轮与第一轮共用同一套低压力骨架（含"可能被淹没"句与问价句），只在 Subject、相关性句动词、产品句精炼度三处做减法**。（同日第一次退回是"两轮一模一样"；两次都是对"差异化"的理解偏差，正解见 §4.11 第 10 条修正版。）
- **错题 61-旧**：第一轮与第二轮 follow up 除 Subject 与产品句长度外几乎逐字相同（同一句"可能被淹没"、同一问价句、同一收尾"期待你的想法"）——用户 2026-09-13 退回："我怎么感觉你产出的 follow up 第一轮和第二轮邮件内容没有区别？"。正解＝§4.11 第 10 条：两轮按"软提醒 / 最后一封"两种角色分别写，起句、产品句长度、问价句尾、收尾句四处必须换，逐段对照门禁。
- **错题 59**：follow up 邮件产品段只写「使用场景清单」（meetings、note-taking、notifications…），既没有差异点也没有核心特性 —— 用户 2026-09-13 退回：「需要在首封 pitch 内容的基础上进行更精炼的提炼，但要提出产品的差异性和核心特性」。正解＝§4.11 第 4 条两句法：句①差异点（camera-free ＋ binocular waveguide display）＋句②官方命名的 3–4 项核心特性。


### 4.12 对外审核 list 同步话术（**项目无关标准** · v0.6.85 · 2026-09-16 由用户最佳实践固化）

**适用场景**：红人审核 list 交付给品牌方时随附的同步话术（发群或邮件）。**每个项目都要出这一份，按本节标准生成**。
**权威来源**：用户在 FED Fitness 与 Halliday G2 两个项目上给出的最佳实践——
FED 版奠定**四段结构**，Halliday G2 第一批版给出**第一点的选词标准正例**（本节的核心）。

> **为什么它是「项目无关」的**：下面给的不是「AI 眼镜该怎么写」，而是一套**从任意 Brief 推导两组词的流程**（§三）。
> 换品类只需重跑那套流程，不需要改本节的任何判据。

---

#### 一、固定四段式（缺段即不合格）

| 段 | 内容 | 必写要素 |
|---|---|---|
| ① 交付说明 | 一句话 ＋ `辛苦查收～` | 项目名 ＋ 第几批 ＋ `红人审核 list` |
| ② **本轮 Pitch 情况** | 三段小结构（见下） | 五类数字**必须闭合** |
| ③ 审核表引用 | 文档引用块 | 用 `<cite type="doc">`，**不写裸 URL**（引用块渲染成标题，品牌方一眼可点） |
| ④ 需反馈＋我方建议 | 截止时间 ＋ 推进建议 | **具体到「周几下班前」** ＋ `我们建议可以先尽快敲定…` |

**第 ② 段骨架（逐字可套用）**

```
本轮 Pitch 情况：
本轮主要从【第一组：品类及功能方向，4–6 个】等品类及功能方向，以及【第二组：使用场景，4–6 个】
等多样化使用场景进行延伸，共筛选发布过相关内容的网红【初筛量】位。
在首轮名单基础上进一步筛选，主要排除【排除原因】，一轮共 Pitch 了【Pitch量】位，目前收到回复的共【回复量】位。
结合回复情况、内容匹配度及报价，本轮给到【提审量】位网红审核。剩下的【未提审量】位网红我们评估【未提审原因】，
近两天也会新 pitch 一批【补充方向】做扩展，收到回复后会给到第二批网红 list 的审核。
```

**五类数字与闭合铁律**

| # | 数字 | 含义 | 必须满足 |
|---|---|---|---|
| ① | 初筛量 | 检索命中的相关创作者总量 | `初筛 ≥ Pitch ≥ 回复` |
| ② | Pitch 量 | 初筛基础上进一步筛选后**实际建联**的量 | 与初筛量**是不同环节，不得写成同一个** |
| ③ | 回复量 | Pitch 后的反馈量 | — |
| ④ | 提审量 | 本轮给品牌方审核的名单量 | **`提审 ＋ 未提审 ＝ 回复`** |
| ⑤ | 未提审量 | 回复了但未提审的量 | **必须交代原因 ＋ 下一步计划** |

> 实测（Halliday G2）：516 初筛 → 484 Pitch → 36 回复 ＝ **14 提审 ＋ 22 未提审** ✅
> **教训 54**：不同环节的数字不得写成同一个、不得互相替换。

**第 ② 段的三个「必须有」**

1. **Pitch 段必须写排除原因**（如「主要排除频道内容相关性低的网红」）——让品牌方知道 516→484 是**有标准地筛**，不是随手砍。
2. **未提审的必须交代**：数量 ＋ 原因（如「报价实在太高或内容相对没那么适配」）＋ **下一步计划**（如「新 pitch 一批非科技测评类型做扩展」）。
   **只报提审数、不解释剩下的，品牌方会疑惑。**
3. **回复之后的推进承诺**（首轮场景）：如「后续我们会持续跟进回复情况，同步整理新增回复」。

---

#### 二、【核心】第一点选词标准 —— 什么是「好的关键词选择」

> 品牌方看这一段，判断的**不是「你筛了多少人」，而是「你懂不懂我的产品」**。
> 选错（混类、过泛、堆词、抄词表），品牌方会立刻判定「这家没读 Brief」。

##### 二·0 心智模型：话术的词 ≠ 词表的词

| | 检索词矩阵 | **对外话术第一点** |
|---|---|---|
| 用途 | 投喂平台去捞人 | **向品牌方证明「我懂你的产品」** |
| 数量 | 全量（数百条） | **8–12 条代表词** |
| 来源 | 品类／竞品／功能／场景／地域／人群多维铺开 | **从 Brief 反推**（不是从词表里挑） |
| 含竞品 | ✅ 是主力 | ❌ **一律不出现** |

**这是最容易做错的地方**：把词表的词挑几个贴进话术 → 必然混类、必然过泛。
**正解是：拿 Brief 重新推一遍**，词表只用来交叉验证「我推的词在平台上真的能命中」。

##### 二·1 两组必须「性质纯粹」，严禁混类

| 组 | 性质 | 回答的问题 | 词的形态 |
|---|---|---|---|
| **第一组** | **品类及功能** | 你们找的是**什么产品／什么能力** | 名词短语，**必须含品类名词** |
| **第二组** | **多样化使用场景** | 你们找的是**在哪些场合用** | 场景／形态／顾虑短语，**不含品类名词** |

**通用判据（任意品类都适用）**：**词里含品类名词的 → 第一组；不含的 → 第二组。**
- 品类名词 ＝ 「能买到的那类产品名」（`glasses` / `camera` / `mower` / `rack` / `vacuum` / `printer` …）
- ❌ **混类实例**（我方 2026-09-15 版被用户纠正）：把 `smart glasses for meetings/work` 放进**第二组**——
  它含品类名词 `glasses`，属**第一组**。
- ❌ **跨组重复实例**（FED 例子中存在，勿沿用）：`plate-loaded home gym` 与 `cable machine` **同时出现在两组**——
  **同一个词不得跨两组出现**。

##### 二·2 第一组公式：`1 个品类基本盘 ＋ N 个「功能限定的品类」`

| 位置 | 该放什么 | 通用做法 |
|---|---|---|
| 品类基本盘 | **无限定词**的品类名，覆盖整个垂类 | 取 Brief 里的品类上位词（`smart glasses`） |
| **差异化** | 把产品**独有差异点**写进品类名 | 取 Brief 的 differentiator（`camera-free AI glasses`） |
| 核心功能 | 每个**核心能力**各造一个「功能限定品类名」 | 取 Brief 的主要功能（`translation glasses` / `meeting assistant glasses`） |

**最容易做错的一点：功能要融进品类名，而不是单列功能短句。**

| | 写法 | 品牌方的感受 |
|---|---|---|
| ✅ | `translation glasses`、`meeting assistant glasses`、`camera-free AI glasses` | 「他在按**产品能力找创作者**」——这是**选人标准** |
| ❌ | `translate conversations in real time`、`take notes hands-free`、`readable display in bright light` | 「他在**罗列功能清单**」——这是说明书，不是选人 |

**上限 4–6 个**：Brief 的能力可能有七八项，**不要全放**——按 Brief 的**层级**取最高的几项（差异化必放，核心功能取 2–3）。

##### 二·3 第二组公式：覆盖「场合 ＋ 形态 ＋ 顾虑」，每词反向对应一个产品能力

| 类别 | 定义 | 通用做法 | Halliday G2 实例 |
|---|---|---|---|
| **场合** | 谁在什么情况下用 | Brief 的人群 × 使用时刻 | `meetings & video calls`、`business travel`、`multilingual conversations`、`conferences & expos` |
| **形态** | 工作／生活方式形态 | Brief 的人群怎么工作／生活 | `work-from-home` |
| **顾虑** | **客户为什么选你**（价值取向／排斥项） | Brief 的差异点反面的顾虑 | `privacy`（无相机的理由） |

**两条反直觉但重要的规律**

1. **允许并鼓励「词表里没有、但 Brief 要求」的词**
   Halliday 实例中 `work-from-home` 与 `privacy` **都不在**源关键词表里，是按 Brief 人群与差异点**反推补进去的**。
   → **话术的词从 Brief 反推**；词表只用于事后验证能否命中。
2. **「顾虑词」必须进第二组**
   `privacy` 不是场景，但它是**客户为什么选无相机**的理由。**品牌方最想看到的就是「你理解我的差异点」**——
   只写场景不写顾虑，等于没读懂 Brief。

##### 二·4 数量与措辞

- **每组 4–6 个**，全篇 8–12 个；**不罗列全量词表**（全量走附件／看板）
- 用**类别名收尾**：`等品类及功能方向` ／ `等多样化使用场景进行延伸`——表明是**代表词而非全部**，是专业信号
- 结果句写 **`共筛选发布过相关内容的网红 N 位`**——强调**内容相关**，不是粉丝量

##### 二·5 必排三类词

| 排除项 | 理由 | 反例 |
|---|---|---|
| **竞品品牌名** | 用户 2026-09-15 裁决：对外话术**不出现任何竞品** | `Ray-Ban Meta`、`Even Realities`、`XREAL` |
| **过泛品类词** | 会把结果拉向纯 Reviewer，与「内容匹配度优先」相悖 | `AI glasses`（单独太泛）、`AR glasses`、`XR glasses` |
| **人群词／痛点词** | 它们是**描述**不是**关键词**，品牌方看不出你要找什么内容 | `professionals`、`productivity creators`、`note fatigue`、`25–50 岁男性` |

> 同一条纪律也适用于**检索词矩阵的对外版本**（见 `kol-skill-1-search-matrix.md` §10 边界）。

---

#### 三、新项目的生成流程（照此执行 · 4 步）

```
Step 1  读 Brief，列出「产品能力清单」
        └ 逐条摘：品类上位词 / 差异化点 / 主要功能 / 日常功能 / 目标人群 / 目标市场 / 明确排斥项

Step 2  造第一组（品类及功能）
        ├ 品类基本盘 ×1（无限定词）
        ├ 差异化 ×1（必放）
        └ 核心功能 ×2–3（按 Brief 层级取最高）
        ⇒ 检查：每个词都含品类名词？功能是「融进品类名」而非单列短句？总数 4–6？

Step 3  造第二组（使用场景）
        ├ 场合 ×2–4（Brief 人群 × 使用时刻）
        ├ 形态 ×1（工作／生活方式）
        └ 顾虑 ×1（客户为什么选你）
        ⇒ 检查：每个词都不含品类名词？每个词都能反向指回 Step 1 的某个能力？总数 4–6？

Step 4  排雷自检（六查）
        ① 无混类（含品类名词的词都在第一组）
        ② 无跨组重复（同一个词不得出现两次）
        ③ 零竞品品牌名
        ④ 无过泛品类词（单独出现会拉回纯 Reviewer 的）
        ⑤ 无人群词／痛点词
        ⑥ 五类数字闭合（提审 ＋ 未提审 ＝ 回复）
```

**填表产出（交付前先填这张，再写话术）**

| 组 | 类别 | 词 | 反向对应的 Brief 卖点 |
|---|---|---|---|
| 一 | 品类基本盘 | | — |
| 一 | 差异化 | | |
| 一 | 核心功能 1／2／3 | | |
| 二 | 场合 | | |
| 二 | 形态 | | |
| 二 | 顾虑 | | |

> **没有「反向对应卖点」的词，一律删掉**——这一栏填不出来的词，就是「凑数词」。

---

#### 四、自带自检清单（每份话术交付前逐项过）

- [ ] 四段式完整（交付说明／本轮 Pitch 情况／审核表引用／需反馈＋建议）
- [ ] 第 ② 段三段小结构完整；**Pitch 段写了排除原因**
- [ ] 五类数字齐备且闭合（`提审 + 未提审 = 回复`）
- [ ] **未提审的写了数量＋原因＋下一步计划**
- [ ] 第一组每个词都含品类名词；第二组每个词都不含
- [ ] 无跨组重复词
- [ ] 第一组含差异化词；功能是「融进品类名」而非单列功能短句
- [ ] 第二组覆盖场合＋形态＋顾虑三类
- [ ] 每个词都能反向指回一个 Brief 卖点（填表产出已交）
- [ ] 每组 4–6 个，全篇 8–12 个；用类别名收尾
- [ ] **零竞品品牌名**；无过泛品类词；无人群词／痛点词
- [ ] 审核表用文档引用块，非裸 URL
- [ ] 截止时间具体到「周几下班前」；有我方推进建议
- [ ] 无内部词（通过率／门槛／CPM／判定规则／口径／分档／综合分）

---

#### 五、正例（Halliday G2 第一批 · 用户给定最佳实践 · 逐字保留）

```
hello，早上好，这个是 Halliday G2 第一批红人审核 list，辛苦查收～

本轮 Pitch 情况：
本轮主要从smart glasses、camera-free AI glasses、translation glasses、meeting assistant glasses等品类及功能方向，
以及meetings&video calls、work-from-home、business travel、multilingual conversations、privacy、conferences & expos等
多样化使用场景进行延伸，共筛选发布过相关内容的网红516位。
在首轮名单基础上进一步筛选，主要排除频道内容相关性低的网红，一轮共Pitch了484位，目前收到回复的共36位。
结合回复情况、内容匹配度及报价，本轮给到14位网红审核。剩下的22位网红我们评估网红报价实在太高或内容相对没那么适配，
近两天也会新pitch一批非科技测评类型的网红做扩展，收到回复后会给到第二批网红list的审核。
Halliday G2 红人审核表（对外）

辛苦Halliday团队在周四下班前给到反馈，我们建议可以先尽快敲定第一批合作红人list，推进发货和红人内容制作。
```

**对照自检（正例为什么合格）**

| 检查项 | 结果 |
|---|---|
| 两组性质纯粹？ | ✅ 第一组 4 个全含品类名词 `glasses`；第二组 6 个无一含 |
| 无跨组重复？ | ✅ 无 |
| 第一组含差异化？ | ✅ `camera-free AI glasses` |
| 功能融进品类名？ | ✅ 全部为「功能限定品类名」，无功能短句 |
| 第二组覆盖三类？ | ✅ 场合 4 ＋ 形态 1（wfh）＋ 顾虑 1（privacy） |
| 每词可反向指回卖点？ | ✅ 翻译→`translation glasses`；无相机→`camera-free`／`privacy` |
| 排除三类词？ | ✅ 零竞品、无 `AI glasses` 这类泛词、无人群／痛点词 |
| 数字闭合？ | ✅ 516 → 484 → 36 ＝ 14 ＋ 22 |
| 有未提审说明？ | ✅ 数量＋原因＋下一步 |
| 有具体截止日＋建议？ | ✅ `周四下班前` ＋ `建议尽快敲定第一批` |

---

#### 六、参考：格式来源（FED Fitness 第二批 · 四段结构的出处）

```
hello，早上好，这个是第二批红人审核list，辛苦查收～

本轮Pitch情况：
两轮围绕2个SKU进行了网红筛选，主要从home gym equipment、squat rack、power rack、all-in-one squat rack、
squat rack with cable machine、cable machine、functional trainer、plate-loaded home gym、power rack with cable attachment等方向，
以及 plate-loaded home gym、multi gym station、cable machine、full-body workout、bodybuilding machine 等延伸方向，
共筛选相关垂直类网红739位。
在初筛名单基础上筛选后，两轮共Pitch了520位，目前收到回复的共34位，后续我们会持续跟进回复情况，同步整理新增回复。
结合回复情况、条款确认情况、内容匹配度及brief红人数据要求，目前新增提审5位红人。
GOC_MRP_FED Fitness 项目红人看板——Share

辛苦FED Fitness 团队在周三下班前给到反馈，我们建议可以先尽快敲定第一批合作红人list，推进发货和红人内容制作。
```

> **本段仅作「四段结构」的出处参考**；其**选词**存在两处问题，勿沿用：
> ① 跨组重复（`plate-loaded home gym`、`cable machine` 同时出现在两组）；
> ② 第二组混入了品类词与训练目标（`full-body workout`、`bodybuilding machine`），不够纯粹。
> **选词一律以 §五 Halliday G2 版为准。**

---


---

# 重建碎片 A：§4.13–§4.24 对外邮件信型章节

> **性质**：`docs/marketing/skills/kol-intelligence.md` 的**重建碎片**（2026-09-30 截断事故补救 · 见 `_INCIDENT-2026-09-30-skill-truncated.md`）。
> **并入位置**：接在基线 v0.9.27 的 §4.12 之后（`docs/marketing/skills/kol-intelligence.md:1760` 起为 §4.12）。
> **重建依据**：仪器源码逐字（`.kol-tools/check_email_tone.py`）、章程平行条款（`docs/roles/kol-expert.md`）、变更日志（`_CHANGELOG-kol-intelligence.md`）、已认可语料（`.kol-tools/_fixtures/emails/*.txt`）、能力地图（`_CAPABILITY-MAP.json`）。
> **证据等级标注**：`逐字` ＝ 仪器常量表／定版语料原文；`强` ＝ 章程同源条款＋能力地图验收判据；`中` ＝ 变更日志描述；`弱` ＝ 仅知节名与用途（正文需重写）。
> **未复原处一律标 `⟦重建：弱证据 · 待补⟧`，不代以推测句。**
> **标题层级依据**：`_CAPABILITY-MAP.json` 的 `entry` 值逐字给出 —— `### 4.15`／`### 4.16`／`### 4.17`／`### 4.18`／`### 4.19`／`### 4.21`／`### 4.22`／`### 4.23`／`### 4.24` 为 **H3**；`#### 4.13.2` 为 **H4**（故 §4.13.1–§4.13.4／§4.15.1／§4.16.5／§4.18.1–§4.18.5 一律 H4）。「§4.22 A／B」「§4.24 A／B」仅在 `_VOICE-PAIRS.md` 以 **`§4.22 A`／`§4.22 B`／`§4.24 A`／`§4.24 B`** 形式出现（无编号点），故本节用**加粗标签**而非标题号，不代原文编号。

---

### 4.13 对外邮件语气禁令：不写元评论、不自夸（v0.9.36 · 2026-09-18 用户当场纠正 · 教训 111 · CLS-08）

> **权威来源**：2026-09-18 用户当场纠正。事故句为拒信里的 `I'd rather tell you straight than leave you waiting on an answer.`
> **用户原话**：「与其让你等待答复，不如直接告诉你更合适。**这种表述不合适**」。
> **这类句子语法与礼貌都没错，所以任何格式检查都抓不到** —— 问题在语用层：① 把"及时回信"这件分内事包装成恩惠；② 主动提"等待"＝承认对方等了很久，在拒信里放大负面感受；③ 读者读到的是"你在为自己的沟通行为辩解"。
> **判据一句话**：**邮件正文里凡出现「描述我方沟通行为／自评沟通质量」的句式 → 报出；改成只写「决定 ＋ 依据 ＋ 下一步」。**

**禁写句式表（13 条 · 中英对照 · 逐字取自仪器 `BANNED`）**

| # | 命中式（正则原文） | 代表写法 |
|---|---|---|
| 1 | `rather than\s+leave\s+you\s+waiting` | `I'd rather … than leave you waiting` |
| 2 | `I'?d\s+rather\s+tell\s+you\s+straight` | `I'd rather tell you straight` |
| 3 | `I'?d\s+rather\s+be\s+upfront` | `I'd rather be upfront` |
| 4 | `rather\s+than\s+let\s+it\s+drift` | `rather than let it drift` |
| 5 | `I\s+wanted\s+to\s+give\s+you\s+a\s+definite\s+answer` | `I wanted to give you a definite answer rather than …` |
| 6 | `just\s+wanted\s+to\s+be\s+(upfront\|honest)\s+with\s+you` | `just wanted to be upfront/honest with you` |
| 7 | `I'?m\s+being\s+transparent` | `I'm being transparent` |
| 8 | `I\s+wanted\s+to\s+get\s+back\s+to\s+you\s+quickly` | `I wanted to get back to you quickly` |
| 9 | `与其让你等` | 与其让你等…不如… |
| 10 | `我宁愿直接(说\|告诉)` | 我宁愿直接说／告诉 |
| 11 | `我想给你(一个)?明确(的)?答复，?而不是` | 我想给你明确答复，而不是… |
| 12 | `只是想让(你\|您)知道` | 只是想让您知道 |
| 13 | `我(很\|比较)坦诚` | 我很坦诚 |

**唯一豁免（白名单 `ALLOW` 3 条）**：**对方明确抱怨过回复慢时**允许一句致歉，仍不得追加自夸式元评论。

| # | 豁免式（正则原文） |
|---|---|
| 1 | `apolog(?:y\|ies\|ise\|ize)[^.]{0,40}(?:slow\|delay\|late)` |
| 2 | `sorry[^.]{0,30}(?:slow\|delay\|late)` |
| 3 | `抱歉[^。]{0,20}(?:慢\|晚\|延迟)` |

**硬判据**

| # | 判据 | 合格线 |
|---|---|---|
| ① | 禁写句式 | 13 条**全部 0 命中**（否则退出码 1，**不得发出**） |
| ② | 致歉豁免 | 仅当对方**抱怨过回复慢**才可用；且必须在交付留痕里说明触发依据 |
| ③ | 保留可执行半句 | 对方要"确定答复以便排期"时，**保留可执行的那半句**（例：`Please plan your October and November slots on that basis.`）、**删掉元评论那半句** |
| ④ | 与 §4.15.1 同源 | "对外文本每多一句就多一个对方可回问／讨论的点"—— 不必要的话默认不写 |

**仪器档位**：无 `--kind`（默认档，`scan()`）。

```bash
python3 .kol-tools/check_email_tone.py --text-file <邮件.md>
```

**边界与豁免**：① 豁免白名单只作用于**紧邻 60 字符窗口内**出现的致歉句；② 中文稿同样扫（第 9–13 条为中文对应式）；③ 该仪器**不管"好与不好"**，只挡"禁写"（§20.3／CLS-60）。

**已认可语料路径**：`.kol-tools/_fixtures/emails/`（18 份，逐份断言「禁语 0 命中」）。

---

#### 4.13.1 拒信禁「过度肯定」（v0.9.38 · 2026-09-18 用户第二次纠正 · 教训 112 · CLS-09）

> **用户原话**（针对拒信里那句 `… were genuinely well received — … is exactly the kind of fit we look for.`）：
> 「**不要这么说，显得他们频道非常合适，很可能对方会觉得有进一步沟通空间**」。
> **机理**：拒信里出现**匹配度评价**，与"本次不推进"**自相矛盾** → 对方推断**问题不在匹配度、而在某个可谈的条件**（预算／形式／时机）→ **等于主动邀请对方回来谈**。
> **判据一句话**：**拒信只确认「看过了」，不评价「合不合适」**；判据是**同一封信里同时出现【拒绝信号】与【匹配度评价】才报出**（单独出现匹配度评价，如首封 pitch，属正常、不报）。

**硬判据表**

| # | 项 | 内容 |
|---|---|---|
| ① | 拒绝信号（`DECLINE` · 14 条） | `won't/not able to move forward`／`won't be moving forward`／`unable to proceed`／`can't move forward on\|with this`／`budget … doesn't stretch\|cover\|allow`／**`budget … is not sufficient`**／**`budget … is insufficient`**／`预算…（确实）不足`／`预算…不够`／`预算…有限`／`本次不推进`／`暂不合作`／`这次不推进` |
| ② | 匹配度评价（`FIT_PRAISE` · 9 条） | `exactly the kind of fit`／`(a) strong\|great\|perfect\|ideal\|natural\|excellent fit`／`good fit`／`well received`／`exactly what we look for`／`the kind of audience\|channel\|creator\|partner we look for`／`would be a great partner`／`非常合适`／`正是我们要找` |
| ③ | 判定 | ①**且**② 同时命中 → 报出（退出码 1） |
| ④ | 可写 | `I shared your proposal and media kit with the team, and we went through everything together.` |

> 🔴 **本条即「预算不足本身也是拒绝信号」的来源**：首版 `DECLINE` 漏了"预算不足"，导致只有"预算不足"而无收口句的邮件**根本不被认成拒信** → 收口句检查与道歉检查**双双失效**（两个自检失败就是这条造成的）。

**仪器档位**：无 `--kind`（默认档，`scan_rejection_praise()`）。

**边界与豁免**：① 单独出现匹配度评价**不报**（防误伤 pitch／跟进／报价谈判）；② 判定为**同信内共现**，不跨信；③ 中文稿与全大写变体同样判定。

**已认可语料路径**：`.kol-tools/_fixtures/hold/hold-lexy-optimized.txt`（调优版，禁语 0 命中）。

---

#### 4.13.2 拒信三段式定版（v0.9.40 ＋ v0.9.41 修正 · 2026-09-18 品牌方评审评论口径 · 教训 113 · CLS-10）

> **来源**：2026-09-18 **品牌方评审评论口径**（评审原话：「简单回复即可，无需给到太多恭维/原因说明，**避免对方做下一轮跟进**」「核心目的：简单告知我们的评估结论即可」）。
> **定版授权**：`docs/marketing/skills/_CAPABILITY-MAP.json` 条目 `edm-reject-hold` 的 `entry` ＝ `#### 4.13.2 拒信三段式定版`。

**定版三段（只写这三段，多一句都不行）**

| 段 | 内容 | 逐字要点 |
|---|---|---|
| ① | 感谢详细介绍和跟进 | 只致谢，不评价匹配度 |
| ② | 经过评估 ＋ 预算确实不足 ＋ **因此本次不推进**（**合为一句**） | 见下方 🔴 |
| ③ | 后续有机会再联系 | 中性收口 |

> 🔴 **v0.9.41 修正（用户裁决「加上吧」）**：评审给的三段清单里**没有收口句**，只写到「本次预算确实不足」；按字面执行会招来**降价反提案**、反而制造下一轮跟进，与评审「避免对方做下一轮跟进」的目的冲突 ⇒ **必须加收口句**。
> **明确 v1 的问题不是"多了收口句"，而是"把'经过评估'拆成独立句并用 Unfortunately 软化"**。

**硬判据表**

| # | 纪律 | 说明 |
|---|---|---|
| ① | **只写三段不得多加** | 但**收口句必须写** |
| ② | **拒信不得道歉** | 评审原话「也无需道歉」；机理＝拒信道歉是**主动承认我方拖延**，而对方并未抱怨过。**确需致歉时用 `--allow-apology` 显式放行并留痕** |
| ③ | **不得评价匹配度** | 见 §4.13.1 |
| ④ | **同类邮件逐封校验措辞、禁整句照搬** | 评审说两封「修改方向一致」＝方向一致、**非同一句话**；凡正文出现**指代性描述**（详细介绍／报价明细／上次沟通／你提到的时间安排…）**须逐封回到该收件人实际来信核对一次**。🔴 **机器判据（2026-10-12 补）**：批量产出（≥2 封）交付前必跑 **`check_batch_diversity.py --drafts <草稿>`**，退出码必须为 0 —— 它查「非白名单句子在 ≥2 封里逐字相同」与「两封整体相似度 ≥0.5」，只放行称呼与落款。**事故**：2026-10-12 我把 10 封不推进回信的第②③段写成逐字相同，用户当场指出「每一个回复邮件的内容都一模一样了」 |
| ⑤ | 邮件身份 | 每封在**小节标题**写明「回复其第 N 封跟进邮件」（答评审「具体是要回复哪封邮件？」） |

**收口句词表（`CLOSING` · 10 条 · 逐字）**

`won't be moving forward`／`not be moving forward`／`won't be able to move forward`／`not able to move forward`／`won't be proceeding`／`decided not to (move|proceed)`／`not going ahead`／`本次不推进`／`暂不推进`／`本次不予推进`

**道歉词表（`APOLOGY` · 4 条）**：`apolog(y|ies|ise|ize)`／`\bsorry\b`／`抱歉`／`对不起`

**仪器档位**：无 `--kind`（默认档；`scan_missing_closing()`／`scan_rejection_apology()`）。

**边界与豁免**：① 判定顺序＝**先有拒绝信号才查道歉与收口句**；② **软性 hold 类无拒绝词的邮件不适用本门控** → 走 §4.13.3 的 `--kind hold`（该场景按 CLS-08／§4.13.3 追加 `scan_apology_any()`，**不做门控**）；③ 草稿文件含「内部留痕」段时，仪器**只喂 `---` 之前的正文**（`--body-only`）；④ 🔴 **不要为了让对方「感到被读到」而承认其合作模式／条款**（2026-10-12 用户裁决：「这个不需要特意说了，**不要给下一轮留口**」）——例如对方说「我们只做中插整合」，回信里再认一句就等于告诉他「那个档次我们听懂了」⇒ 他会接着报价或换包件再谈。致谢只谢「回信」这件事本身，**不预告任何可谈的口子**。

**已认可语料路径**：`.kol-tools/_fixtures/hold/`（`hold-lexy-original.txt` 真阳性／`hold-lexy-optimized.txt` 真阴性）。

---

#### 4.13.3 不推进的软性 hold（KOL 二次跟进后的简短回复）（v0.9.60 · 2026-09-22 品牌方评论 c1–c4）

> **场景**：这批 KOL 都是**评估后不推进**的，但要**维持关系** → 只回一封**简短**邮件。
> **来源**：《KOL二次跟进后的简短回复》（飞书 wiki `QcY1wsmV3icyLMki3accAywbnPh`），评论人 **Blossom 江荣荣**（4 条）。
> **判据一句话**：**只写三段 —— 致谢（不带道歉）／正在评估中 ＋ 有进度再同步／落款；不给任何「看好·在推进·很想合作」的预期。**

**定版三段**

| 段 | 内容 |
|---|---|
| ① | 致谢 —— **只留致谢，不道歉**（评论 c2：保留前半句） |
| ② | **正在评估中 ＋ 有进度会同步**（评论 c3：简单说即可） |
| ③ | 落款 |

**四条评论口径（逐字）**

| 条 | 口径 |
|---|---|
| c1 | 直接回复网红**不需要 Subject** |
| c2 | **不道歉**（没等很久）＋ 致谢只留前半句 |
| c3 | **简单说即可**（正在评估中，有进度会同步） |
| c4 | **不推进就不要给"看好／在推进／很想合作"的预期** |

**硬判据表**

| # | 判据 | 合格线 |
|---|---|---|
| ① | 禁语（`HOLD_BANNED` · 10 条） | **0 命中**：`looks great on our side`／`everything looks great\|good`／`moving forward`／`in active discussions`／`align on the final decision`／`as excited as you are`／`make this happen`／`appreciate your patience`／`confirmed answer`／`the moment we have` |
| ② | 必含三件（`HOLD_REQUIRED` · 3 条） | 致谢一句 ／ 说明"正在评估中" ／ "有进度会同步"的表述 |
| ③ | 无 Subject 行 | 不得出现 `^\s*Subject\s*[:：]` |
| ④ | 长度 | 正文 **≤ 60 词**（`HOLD_MAX_WORDS`） |
| ⑤ | 不道歉 | 本场景**不设拒绝信号门控**，一律扫道歉 |

> 🔴 **原稿实测命中 9 处**（`everything looks great on our side`／`moving forward`／`in active discussions`／`as excited as you are`／`make this happen`／`appreciate your patience` …）。
> 🔴 **本轮最值钱的一条**：**原稿跑旧仪器是「全绿」的** —— 评论的 4 处问题一处都没抓到；根因是 `scan_rejection_apology()` **要求先命中 `DECLINE` 才检查道歉**，而这类邮件**没有拒绝词** → **整条判据被跳过**。
> **结构性修复** ＝ 新增 `scan_apology_any()`（不做门控）＋ `--kind hold`。**元纪律：凡"先判 A 再查 B"的判据，都要问一句「B 在 A 不成立时还需不需要查」**，并把这句话作为固化必答项。

**仪器档位**：`--kind hold`（自检 61/61 → 75/75；原稿报 12 项、退出码 1；调优版 0 命中）。

```bash
python3 .kol-tools/check_email_tone.py --text-file <回复邮件.md> --kind hold
```

**边界与豁免**：① 调优版**待用户认可**，故其语料放在 `_fixtures/hold/`（**不放** `emails/` —— 否则那条「认可版 0 命中」护栏会失败）；② 本档不判截止日／承诺／目的句（本信型无需对方行动）。

**已认可语料路径**：`.kol-tools/_fixtures/hold/`（含 `README.md` 的真阳性专区约定）。

---

#### 4.13.4 「柔和」＝只改语气层，不改请求层（v0.9.77 · 2026-09-23 用户当场纠正 · CLS-19）

> **用户原话**：「我说的柔和**不是模棱两可**，只是在表述上使用更友好的预期让人读起来不会觉得生硬，**哪怕下面每一项只给个大概区间也足够我们起步了比如这种就是模棱两可，你需要区分一下**：首先我们要在**问的部分足够清晰准确**，其次只是在整个邮件的**话术表达部分**，需要更友好，不要让 KOL 觉得有被冒犯或者态度强硬」。
> **事故**：把「柔和」做成了「把要求降级」—— 问价句后加了 `Even a rough range for each option below would be plenty to get us started.` 与 `…we are happy to work from whatever format suits you best.`
> ⇒ **请求层被模糊化**（「每一项的报价」→「大概区间」；「三档 SKU」→「你自己的套餐」），拿回来的价**不可横向比较、不可落表、不可对账**；而这类句子**语法与礼貌都挑不出错**，当时仪器 94/94 全过。
> **判据一句话**：**柔和只作用于语气层（句式是否友好），绝不作用于请求层（要什么、几项、按什么口径报必须精确）；凡降低"被请求对象"的精度或范围 ＝ 模棱两可，不是柔和。**
> **辅助判句**：**柔和是「怎么说」，不是「要多少」。**

**两轴分离表**

| 轴 | 必须 | 可动 |
|---|---|---|
| **请求层** | 精确：多项必写逐项限定 `for each of the following`／`separately`／`分别`；口径与首封**逐字一致** | ❌ 不动 |
| **语气层** | 缓冲句式 `Would you be open to…`／点名对方**具体作品**替代空泛恭维／**不替对方表态** | ✅ 在这里做柔和 |

**禁写四类（`VAGUE_ASK` · 12 条模式 · 逐字举例）**

| 类 | 代表命中式 | 为什么 |
|---|---|---|
| ① 精度降级 | `even/just a rough\|approximate\|approx.\|ballpark\|general\|broad range\|idea\|sense\|figure(s)\|number(s)\|estimate\|indication`／`even (just) a rough\|approximate\|ballpark` | 把「每项报价」降级为「大概区间」→ 价不可横向比较 |
| ② 门槛自我降低 | `would\|will\|should be plenty\|enough\|helpful\|a great start\|a good start … get us started\|to start\|for now\|to begin`／`good\|great\|fine\|enough\|plenty to get us started` | 声明我们可以接受不完整的报价 |
| ③ 对象放宽 | `if it's easier to begin\|start\|work from`／`send\|share (over) your\|whatever\|any (own) packages?\|rate cards?\|price lists?`／`whatever\|any format\|structure\|shape\|package\|way\|version suits\|works for\|is easiest for you`／`happy\|glad\|fine to work from\|with whatever`／`anything\|whatever you can\|are able to\|feel free\|able to share\|send\|give` | 请求对象从既定 SKU 放宽为「你自己的套餐／任意形式」 |
| ④ 中文同族 | `(大概\|粗略\|大致的?) (区间\|范围\|数字\|价位)`／`(随便\|任意) (报\|给) (个\|一个)? (价\|数)`／`(什么\|任何) (形式\|格式\|套餐) (都\|也)? (可以\|行\|OK)` | 内部评审稿同样禁 |

**豁免面（`VAGUE_ASK_ALLOW` · 2 条）**：命中词**紧前**出现否定／排除语境时**不算降级** —— `do not／don't／does not／doesn't／no need／needn't／not ask(ed) for／without／rather than`（例：`we do not need a rough range — just the exact rate for each option`）／`不需要｜不用｜无需｜不必`。
**渠道弹性放行**：`just send them here / by email` 一类**渠道**弹性**不影响请求精度**，放行。

**精度提醒（不进退出码 · `DISTRIBUTIVE_MARKERS` 8 条）**：列了 **≥2 项**交付物却**没有**逐项限定词（`each`／`per option`／`for each of the following`／`separately`／`priced each|separately`／`one for each`／`分别`／`每一项`）⇒ 提醒一次（"对方可能只回一个总价，无法对齐三档"）。

**仪器档位**：`--kind quote`（或显式 `--vague-ask`）。**场景门控**：仅问价场景生效 —— 砍价／授权／hold 等场景里的"区间／范围"是**正常表述**，不扫。

```bash
python3 .kol-tools/check_email_tone.py --text-file <话术文档.md> --kind quote --extract-code
```

**边界与豁免**：① 话术类文档**同时**放"可发送正文"与"讲评用反面教材"时，**只扫可发送正文**（`--body-only` 取 `---` 之前／`--extract-code` 取代码块）—— 否则反面教材会被当成我方写的句子；② 否定语境豁免只作用于**紧前 80 字符窗口**。
**写完自问**：「这封信要对方做哪个具体动作？我删改的句子有没有动到那个动作的精度？」

**已认可语料路径**：`.kol-tools/_fixtures/emails/user-approved-rate-ask.txt`（问价定版）／`user-approved-wechat-open.txt`（IM 三档清单）。

---

#### 4.13.5 回信意图判定：先看对方说了什么，再选骨架（2026-10-12 用户纪正 · 教训 251 · CLS-70）

> **用户原话**：「freshandfelicia@gmail.com 这个邮箱对应的 kol 的回复表示 `so we should probably skip this cooperation.`，
> 这个就属于红人对于本次合作的拒绝的，那你的回复邮件就表示一下感谢回复，并且希望下次有机会合作就行，
> 这说明你对于**邮件本身的理解还是太过于机械化**，你所谓的差异性并没有很好的对邮件进行理解后进行对应的回复邮件的生成」

**判据一句话**：**回复邮件的第一步不是写，而是判来信意图** —— 同一批回信可以措辞各异却仍然「错得一样」，
因为「差异化」如果只做同义改写、不做意图区分，就只是表面功夫。

| 来信意图 | 判定信号（例） | 我方回信骨架 |
|---|---|---|
| `decline` **对方拒绝** | `we should probably skip this cooperation`／`we'll pass`／`not interested`／`have to pass` | 🔴 **禁止出现我方收口句**（`won't be moving forward` 等）—— 拒绝权在对方，重复宣告像在掩饰；只写**致谢 ＋ 期待下次合作**（对方若提了「以后看别的产品」，就顺着回一句） |
| `quote` 对方报价／给条件 | 金额、`rate(s)`、`quote`、`licensing` | 砍价走 §5.4／§5.4.3（`could you accept £X`）；本次不推进走 §4.13.2 收口句骨架 |
| `advance` 对方想推进 | `super excited`／`get started`／要 brief／要换渠道（微信） | 若我方本次不推进：一句收口 ＋ 期待后续；**不得**写「很想合作／可协商」（§5.4 成交预期纪律） |
| `info` 要信息／其它 | — | 事务型回复骨架（§4.16） |

**仪器**：`python3 .kol-tools/check_reply_intent.py --incoming <来信> --reply <回信>`（或 `--batch <草稿>`；离线自检 **11/11**）——
`decline` 时**禁止我方收口句**、**必须**有致谢与「后续再合作」；另有精度面控制：`We do not accept unpaid/gifted placements`（对方的合作模式陈述）**不得**被误判成「拒绝我们」。
**事故留痕（2026-10-12）**：Fresh and Felicia 在来信里明确说「因与 Ray-Ban/Meta 的诉讼，本次合作先跳过」，我却回了「经过内部评估，很遗憾项目不再推进」—— 把对方给的拒绝又替他说了一遍，且读起来像掩饰；
已改为「致谢 ＋ 会记着你们 ＋ 期待将来合作」。

### 4.14 送审邮件「四件套」（v0.9.53 · 2026-09-21 用户给定最佳实践后固化 · 教训 123）

> **场景**：把「我方计划怎么回对方」送品牌方审核。
> **用户原话**：「关于给到审核的邮件，其实一般我们是需要说一下**上一封邮件内容包括目的背景**的，这样方便后面**审核的人知道上下文**」。
> **判据一句话**：**送审四件齐，缺 ①② 审核人无法判断对错。**

**四件套（每个 KOL 一段）**

| # | 件 | 要求 |
|---|---|---|
| ① | **背景说明** | 为什么现在发 —— 写**触发点／品牌方反馈原话** |
| ② | **上一封邮件** | **逐字原文，不得摘要改写** |
| ③ | **计划回复的邮件内容** | 带 `To：`／`Subject：` |
| ④ | **回复邮件调优版** | 按该信型骨架与仪器档产出 |

**硬判据表**

| # | 判据 | 来源 |
|---|---|---|
| ① | 四件缺一即不合格 | 用户原话 |
| ② | ②必须**逐字原文** | "不得摘要改写" |
| ③ | 判据不得只写「我自己想到的句式／语境」 | 教训 123 · 同族第 3 次 → 回退重做 |
| ④ | 每新增一条禁语／必备要素，**必须同时放一份真实产物进语料库回代** | 元纪律 |

> 🔴 **本条是「真实产物回归语料」制度的诞生地**：实测中 `ask_accept` 认不出 `we were wondering if you would be open to £1,010 …`；术语规则只禁不辨语境、把用户已认可的授权信判成违规。**结构性修复** ＝ 建 `.kol-tools/_fixtures/emails/`，`--self-test` **强制对每份语料断言「禁语／术语 0 命中」**。
> **判据一句话（元纪律）**：**自己造的样例，永远测不出自己没想到的写法。**

**仪器档位**：无专档；四件套中的 ④ 按其信型取 `--kind`（§4.16.5 矩阵）。

**边界与豁免**：① 送审件本身是**对内**件，语气禁令（§4.13）只作用于其中的 ③④；② 引文（品牌方反馈原话、上一封原文）**不按我方措辞判定**（`mask_quotes()` 口径，见 §4.16 边界）。
**⟦重建：弱证据 · 待补⟧**：送审件的**文件命名约定与落盘目录**（`docs/marketing/kol/…`）原文未留存。

**已认可语料路径**：`.kol-tools/_fixtures/emails/`（四件套中的 ③④ 以其为回归基准）。

---

### 4.15 发货信息征询（v0.9.65 · 2026-09-22 用户订正）

> **用户原话**：「我们要地址**不是**为了写合同里，是**要发货**，所以整体方向调整一下」。
> **事故**：合同签署区按母版留了 `Address:` 下划线，我就在邮件里请对方「去合同那一栏补上收货地址」。
> **根因**：把"合同里恰好有一栏地址"当成了"索要地址的入口"，而两者**用途与形式都不同**。
> **判据一句话**：**索取信息的动作必须与用途对齐** —— 为发货要地址，就在邮件里**直接给清单让对回填**，不把对方引去正式文件的某一栏。

**定版做法（v0.9.65）**

| 项 | 内容 |
|---|---|
| 时机 | 发货信息与「请签署」**同封一次性索取**（见 §4.15.1） |
| 形式 | 给**清单** ＋ 一句 `You can simply reply with these filled in.` |

**清单（五项 · 逐字）**

```
- Full Name
- Full Shipping Address
- City / State / ZIP Code
- Country
- Phone Number
```

**四条要点**

| # | 要点 |
|---|---|
| ① | **字段与物流实际需要对齐**（承运商要电话 ⇒ 必收 `Phone Number`） |
| ② | **一次性清单优于分散追问** |
| ③ | **不要让对方去正式文件里找某一栏**（合同 Party B 地址栏按母版保留、**不作为索要入口**） |
| ④ | **收到的信息进寄样台账、不回灌进合同** |

**硬判据表**

| # | 判据 | 来源 |
|---|---|---|
| ① | 索取动作的用途＝发货（不得写成"为了写进合同"） | 用户订正原话 |
| ② | 五项清单齐（含 `Phone Number`） | 定版文案 |
| ③ | 附一句回填说明（`You can simply reply with these filled in.`） | 定版文案 |
| ④ | **默认不写"电子签署也可以"**（→ §4.15.1） | 用户 2026-09-22 订正 |

**仪器档位**：`check_email_tone.py`（默认档；冗余句用 `scan_superfluous()`，**只提醒、不改退出码**）。

**边界与豁免**：**物流台账**（收货五项 ＋ 运单号 ＋ 承运商 ＋ 状态 ＋ 跟进）在 v0.9.172 时**尚无落点**，工作流文档已登记为建议回填项（`docs/marketing/workflow/01-marketing-chain-workflow.md:1250`）。
**⟦重建：弱证据 · 待补⟧**：本节事故原文（用户给出的成品文案逐字）未留存，上表清单取自 `user-approved-contract-final-send.txt`。

**已认可语料路径**：`.kol-tools/_fixtures/emails/user-approved-contract-final-send.txt`（含五项清单）／`docs/marketing/kol/2026-09-halliday-techiteasy-contract-sign-email-draft.md`（本地留档）。

---

#### 4.15.1 合同发送邮件的「请签署」段默认写法（v0.9.66 · 2026-09-22 用户订正）

> **用户原话**（针对我自加的 `An electronic signature is fine.`）：「这句话**默认也是不需要的**，不用改文档」。
> **判据一句话**：**默认不写「电子签署也可以」。**

**定版两段**

| 段 | 内容 |
|---|---|
| ① | 感谢条款反馈 |
| ② | 合同已发出 ＋ 请签署 |

**两条理由**

| # | 理由 |
|---|---|
| ① | 合同本身已写明 `may be executed electronically` ⇒ 这句**冗余** |
| ② | 对外文本**每多一句就多一个对方可回问／讨论的点**（与 §4.13「只写决定＋依据＋下一步」同源） |

**硬判据表**

| # | 判据 | 合格线 |
|---|---|---|
| ① | `An electronic signature is fine.` | 默认**不写**（命中 → **只提醒，不改退出码**：它不属语气缺陷，属"不必要"） |
| ② | 同类写法 `electronic signatures? (are\|is) (acceptable\|okay\|ok)` | 同上 |
| ③ | 两条模式**互不重叠** | 首版重叠会同一句报两次（已修） |

**仪器档位**：`check_email_tone.py`（默认档；`scan_superfluous()` 2 条模式，**只提醒**）。
自检：**77/77**（v0.9.66 时点 · 新增正控 ＋ 真阴性各 1）。

**边界与豁免**：① 该句**不符合语气缺陷**定义，故不进退出码；② v0.9.66 时点，**已交付的飞书邮件文档未改动**（该句仍在文档里，属用户自己发送时删）。

**已认可语料路径**：`.kol-tools/_fixtures/emails/user-approved-contract-final-send.txt`（定版：`Thank you for confirming everything on the agreement — the final version is attached.` ＋ `Could you please sign it when you have a moment?`）。

---

### 4.16 事务型回复邮件（Reply EDM）定版骨架（v0.9.90 · 2026-09-28 用户给定版后固化 · 教训 136 · CLS-22／CLS-13 第 3 形）

> **来源**：2026-09-28 用户给定「调整后的话术」（Tech It Easy 开票信息回信）并明确要求「**你需要学习一下 EDM 邮件的写作思路以及怎么才是一封好的 EDM 回复邮件**」。
> **复盘全文**：`docs/marketing/skills/_RETRO-2026-09-28-techiteasy-reply-edm-gap.md`。
> **判据一句话**：**办事型回复邮件的价值不在「信息给到了」，而在「对方读完知道做什么、什么时候做，并感到被我方善待」。**

**我的原稿 vs 用户定版（逐句对照 · 五处差距全在"可执行性与关系维护"，不在语法礼貌）**

| # | 我的原稿 | 用户定版 | 判据 |
|---|---|---|---|
| ① | `We have noted your shipping details and will arrange the shipment to:` ＋ **6 行收货地址** | **不复述**（对方给的地址直接进台账） | 对方要**逐字核对**＝零增值，**抄错还是我方责任** → `echo_leadin`／`echo_block` |
| ② | `One note on timing: our China team will be on the National Day holiday from 30 September, so payments may not be processed in time during that period.` | `We'd also love to give you a quick sense of our timing so we can keep everything running smoothly. Our office will be closed for the National Day holiday from September 30, and our finance team won't be able to process any payments during the October 1 to 7 holiday period.` | 无目的句／**责任主体错位**（是"财务团队"不是"中国团队"）／`may not be processed in time` 模糊 |
| ③ | `If it is possible for you, sending the deposit invoice over before 30 September would allow us to pay the deposit without delay.` | `If it's convenient for you, could you please send the deposit invoice over to us by September 29?` | **该"请求"写成了条件陈述**（假设＋后果，全句没有动作句）→ `no_request` |
| ④ | `before 30 September` | `by September 29` | **边界歧义**（当天算不算？）且**与我方限制起始日同日＝零缓冲** → `vague_deadline`／`no_buffer_day` |
| ⑤ | **无收尾开放句** | `Thanks so much, and please let us know if you need anything else from our side.` | → `no_closing` |

> 用户定版把 4 段压成 3 段，而**对方能做的动作多一个、时间点明确一个、我方承诺多一句**。

**六段骨架（缺一不可）**

| 段 | 内容 | 要求 |
|---|---|---|
| ① | **致谢** | 暖 ＋ **具体事由**（`Thank you so much for your patience throughout the contract review process, and for signing the agreement — we really appreciate it.`） |
| ② | **对方要的信息** | 齐即可；**我方信息块必须带标签**（带标签即豁免复述判据） |
| ③ | **限制四件套** | 目的句 ＋ 具体区间（**谁**、从哪天到哪天不能做什么）＋ **明确截止日** ＋ **我方承诺** |
| ④ | **带缓冲的请求** | `If it's convenient for you, could you please <动作> by <日期>?` |
| ⑤ | **收尾开放句** | 致谢 ＋「还需要我们这边提供什么随时说」 |
| ⑥ | **落款** | `Best regards,`／署名／`Global OneClick` |

**八类硬判据（`--kind reply` 逐项 · 代码名 → 含义 → 改法）**

| # | code | 含义 | 改法 |
|---|---|---|---|
| ① | `echo_leadin`／`echo_block` | 复述了对方刚给的信息（明示句／无标签地址块） | 删复述段；**确要书面确认时放到真正发货那一封**（一封信一个主题）；本信主题就是确认信息时 `--allow-info-echo` 显式放行 |
| ② | `no_deadline` | 说了我方时间限制，却没有给对方明确截止日 | 补一个可直接抄进日历的确定日期（例：`by September 29`） |
| ③ | `vague_deadline` | 截止日写成「某日之前」（`before`／`prior to`） | 改用 `by <Month D>`，让对方无歧义地知道哪天算迟 |
| ④ | `no_buffer_day` | 对方动作的截止日**不早于**我方限制起始日 | 把截止日提前到限制起始日之前（限制 9/30 起 → 截止日写 9/29） |
| ⑤ | `imperative_no_buffer`／`no_request` | 请求写成祈使句无缓冲 ／ 有截止时间却没有请求动作（写成了陈述） | 改成 `If it's convenient for you, could you please …?`（双层缓冲）／把条件陈述改成明确请求 —— **请求层必须精确（CLS-19）** |
| ⑥ | `no_commitment` | 只说了我方限制，没写"我方会做什么" | **同一段里**给出我方动作（`We'll arrange the payment as soon as possible.`） |
| ⑦ | `no_purpose` | 限制段缺"为什么现在跟你讲这件事"的目的句 | 在限制之前加一句（`so we can keep everything running smoothly`） |
| ⑧ | `no_closing` | 缺收尾开放句 | 落款前补 `Thanks so much, and please let us know if you need anything else from our side.` |

**判据词表（逐字 · 该档的"可判定要素"）**

| 表 | 条数 | 作用 |
|---|---|---|
| `REPLY_RESTRICTION` | 8 | 我方时间限制（`national day holiday`／`office\|team\|company is\|are\|will be closed\|shut`／`will be closed for`／`holiday from\|period\|season\|closure`／`public holiday`／`won't\|will not\|cannot\|can't\|unable to … process\|handle\|arrange\|complete (any) payments?\|transfers?\|the payment\|invoices?`／`payments? may\|might\|will not be processed`／`放假\|假期\|休假\|长假\|无法(及时)处理\|暂停处理`） |
| `REPLY_RESTRICTION_NEG` | 否定守卫 | 排除「我们并没有关门／不受影响」（`is\|are\|was\|were\|will be not closed\|affected\|a holiday\|on holiday`／`no holiday`／`not on holiday`／`不受影响`／`不放假`／`照常`） |
| `REPLY_ECHO_LEADIN` | 5 | 复述的**明示句**入口（**宾语必须绑定"收货/联系信息"**） |
| `REPLY_ECHO_OURINFO` | 8 | 我方信息块（带标签即豁免；`\bour\b` **必须有词边界**，否则 `your shipping details` 会因子串被判成我方块） |
| `REPLY_ADDR_SIGNAL` | 6 | 无标签地址块信号（≥3 连续短行 ＋ ≥2 类信号才报） |
| `REPLY_REQUEST_BUFFERED` | 12 | 带缓冲的请求（含 `check／verify／review／sign／fill in／complete／upload／update／return／take a look／have a look` 与 `re-?issue／re-?send／re-?do／correct／revise／amend／update` ＋ 中文「重开／重发／更正／修改／更新／换开／发送／发给／发来／发到／提供／确认／回传／安排／报价」） |
| `REPLY_REQUEST_IMPERATIVE` | 3 | 裸祈使（`please send\|share\|provide\|confirm\|issue\|return\|sign\|check\|verify\|review\|fill in\|complete\|upload\|update`／行首 `send us`／中文「请(?!您)…」） |
| `REPLY_BUFFER` | 10 | 缓冲句式（`could you`／`would you`／`if it is convenient`／`if possible`／`at your convenience`／`方便的话`…） |
| `REPLY_COMMIT` | 3 | 我方承诺（**作用域＝限制所在段 ＋ 紧接着那一段**） |
| `REPLY_PURPOSE` | 9 | 目的句（`so (that) we\|you can`／`to make sure`／`in order to`／`为了(保证\|确保\|让)`／`以便`…） |
| `REPLY_CLOSING` | 9 | 收尾开放句（`let us know if you need anything`／`don't hesitate to reach out`／`feel free to reach out\|get in touch`／`happy to help … anything`／`随时(告诉\|联系)我们`…） |

**仪器档位**：`--kind reply`。

```bash
python3 .kol-tools/check_email_tone.py --text-file <回复邮件.md> --kind reply --body-only
```

**边界与豁免（逐条如实登记）**

| # | 边界 |
|---|---|
| ① | **退化输入守卫**：去空白后 <60 字符不做"骨架缺件"判定 |
| ② | **判据 ②③④（截止日类）作用域**：`kind != 'progress'` 才生效（同步档里假期是**信息**、不是限制） |
| ③ | **`no_commitment` 作用域**：承诺必须落在**限制（或截止日）所在那一段或紧接着那一段**（首版全文搜 ⇒ 与请求无关的前一段也能蒙混） |
| ④ | **`no_closing` 在全文搜索收尾句**（不在末段也能通过）—— **已知边界，v0.9.91 时点未修** |
| ⑤ | **引文不按我方措辞判定**：`mask_quotes()` 遮罩**段落级引文**（段首段尾成对引号 ＋ 内文 ≥40 字符，支持嵌套引号）；**短引文（<40 字符）不豁免** |
| ⑥ | **摘要诚实性**：无时间限制／无截止日时判据 ②③④⑥⑦ **未触发** ⇒ 摘要**不得宣称**"截止日明确且有缓冲／请求动作带缓冲"齐备（CLS-45） |
| ⑦ | 草稿含内部留痕时**只喂正文**（`--body-only` 取 `---` 之前） |

**已认可语料路径**：
- 真阴性（定版）：`.kol-tools/_fixtures/emails/user-approved-techiteasy-invoicing-reply.txt`
- 真阳性（我的原稿）：`.kol-tools/_fixtures/reply/techiteasy-invoicing-reply-MY-DRAFT-original.txt`（附 `_fixtures/reply/README.md` 的专区约定）

---

#### 4.16.5 用户给定版处置工序（三件）＋ 信型 × 骨架 × 仪器档矩阵（v0.9.91 新建 · v0.9.172 更新）

> **来源**：2026-09-28 全天复盘落账（复盘 `docs/marketing/skills/_RETRO-2026-09-28-full-day.md`）。
> **触发**：用户已 **4 次**给定版 —— 09-18 拒信／09-20 砍价／09-21 议价／09-28 事务型回复。

**① 处置三件（收到任何"用户给定版／最佳版"都必须做）**

| # | 工序 | 落点要求 |
|---|---|---|
| ① | **逐句差异分析** | **落盘复盘，不得只在对话里说** |
| ② | **定版入回归语料** | `.kol-tools/_fixtures/emails/`（**被否决版入对应真阳性专区并写 README**，例 `_fixtures/reply/`／`_fixtures/hold/`） |
| ③ | **差异转成可判定判据 ＋ 仪器档** | 新判据必须同时进**退出码表达式** |

> **判据一句话**：**只写"下次注意"＝未固化。**

**② 新增判据的两类强制探针**（`_checker-hygiene.json` 的 `_建议追加类别`）

| 探针 | 做法 | 防什么 |
|---|---|---|
| **过宽探针 `nearmiss`** | 写一句"沾边但不该命中"的话，断言**不报** | 判据过宽（假警报） |
| **作用域探针 `scope`** | 把判据依赖的元素**移到别处**，断言行为符合设计（**含放宽侧的真阴性**） | 判据过严／作用域过大 |

> **判据一句话**：**「能报出该报的」只是及格线，「不报不该报的」才是可用性。**
> **配套纪律（③④）**：**数字与引用一律程序化取值**（节号先 `grep` 现状再定；凡"从 A 涨到 B"的数字，**两个数都必须来自命令输出**）；**信型矩阵缺口如实登记**（禁假装已覆盖）。

**③ 信型 × 骨架 × 仪器档矩阵（以 §4.21–§4.24 为准 · v0.9.172 已补齐）**

| 信型 | 骨架 | 仪器档 | 已认可语料 |
|---|---|---|---|
| 首封 Pitch | §4.21 | `--kind pitch` | `user-approved-pitch-a.txt` |
| 合作条款（清单） | §4.22 A | `--kind terms` | `user-approved-terms-first.txt` |
| 合同往返（谈判／发签署） | §4.22 B | `--kind contract` | `-contract-negotiation.txt`／`-contract-final-send.txt` |
| Follow Up（两轮） | §4.23 | `--kind followup` | `-followup-1.txt`／`-followup-2.txt` |
| 问价 | §4.24 A | `--kind quote` | `-rate-ask.txt` |
| 微信话术（IM） | §4.24 B | `--kind im` | `-wechat-open.txt` |
| 拒信／软性 hold | §4.13.2／§4.13.3 | `--kind hold` | `_fixtures/hold/` |
| 砍价／后续议价 | §5.4／§5.4.2 | `--kind bargain`（＋`--bargain-phase followup`） | `user-approved-bargain-warm.txt` |
| 送审邮件 | §4.14 | 无专档（按 ④ 的信型取档） | — |
| 发货信息征询 | §4.15／§4.15.1 | 无专档 | `user-approved-contract-final-send.txt` |
| 发货／运单同步 | §4.18（判据 ⑥） | `--kind progress` | `user-approved-shipping-tracking-sync.txt`（**用户给的参考样例**） |
| Review Guideline 同步 | §4.18 | `--kind progress` | `user-approved-review-guideline-sync.txt`（**用户给的参考样例**） |
| 事务型回复 | §4.16 | `--kind reply` | `user-approved-techiteasy-invoicing-reply.txt` |
| 更正类回信 | §4.17 | `--kind correction` | `-techiteasy-invoice-address-correction.txt`／`-brief-reference-correction.txt` |
| 进度同步 ＋ brief | §4.18 | `--kind progress` | `user-approved-techiteasy-progress-brief.txt` |
| 信息核实类 | §4.19 | `--kind reply`（引文遮罩后 0 退出） | `-techiteasy-account-confirmation.txt` |
| 回执／致谢类 | §4.20 | `--kind ack` | `-techiteasy-payment-ack.txt` |

> 🔴 **矩阵沿革（防误引）**：v0.9.91 首版矩阵把**首封 pitch／Follow-up 两轮／条款邮件／发货征询／送审邮件五类**标为「只有骨架、无独立仪器档（待补）」。**该状态已由 v0.9.172 取代** —— 前四类已建档并补定版语料；**送审邮件（§4.14）仍无专档**。
> 工作流文档已登记此矛盾（`docs/marketing/workflow/01-marketing-chain-workflow.md:1248`）：**按矩阵做会误判「没有标准件」⇒ 一律以 §4.21–§4.24 与本表为准。**
> **标准件定义（v0.9.172 · 教训 240 · CLS-62）**：**逐字语料 ＋ 骨架 ＋ 仪器档 ＋ 能力地图条目**四件齐才算标准件；**参考样例分开存放**（`.kol-tools/_fixtures/reference/stage-examples/`）。
> **实测时点规模**：认可语料 **18 份**（`.kol-tools/_fixtures/emails/*.txt`）／仪器自检 **249/249**。

**仪器档位**：矩阵本身即档位索引；新增档位**必须同步退出码表达式** `return 1 if (… or ai or si)`，且必须有**正控**证明退出码真能拦（教训 239 · CLS-45 第 4 形）。

**已认可语料路径**：`.kol-tools/_fixtures/emails/`（18 份）＋ `_fixtures/reply/`（真阳性）＋ `_fixtures/hold/`（真阳性＋调优版）＋ `_fixtures/reference/stage-examples/`（19 个阶段的**参考样例**，非定版）。

---

### 4.17 更正类回信（我方失误 → 请求更正／重开）定版骨架（v0.9.153 ＋ v0.9.154 补判据 ⑥ · 2026-09-29 · 教训 206／207 · CLS-45／CLS-19 第二形）

> **场景**：我方此前给错信息（地址／抬头／金额／日期），或我方文件有误 ⇒ 需**请对方重开或更正**。
> 本件 ＝ Tech It Easy 发票地址更正（旧地址 → `46th Floor, Lee Garden One, 33 Hysan Avenue, Causeway Bay, HK`）。
> **判据一句话**：**道歉只就「我方给错了信息」这个事实；请求仍须精确可执行；并把对方的返工量说得越小越好。**
> **v0.9.154 用户第二次纠正原话**：「请您重新开具以下更新后的发票，仅需更新地址栏信息 **这个语气有点生硬**，还是**需要加一些麻烦之类的话**的，**毕竟是我们的问题**」。

**六段骨架（次序与 §4.16 不同 —— 主题是我方失误，故致歉在开场而非收尾）**

| 段 | 内容 | 逐字示例 |
|---|---|---|
| ① | 称呼 | `Hi Alex,` |
| ② | **致歉 ＋ 失误定性 ＋ 后果（依据）** | `Apologies — that was our mistake: the company address we sent you for the invoice is our old one, and our finance team can't approve the payment against it.` |
| ③ | **精确请求 ＋ 缩小返工量** | `Sorry to trouble you with this — could you please reissue the invoice with the updated details below? Only the address line needs updating.` |
| ④ | **我方信息块（带标签）** | `Name of beneficiary: …`／`Company address: …` |
| ⑤ | **我方承诺（与请求成对）** | `We'll arrange the payment as soon as the updated invoice comes through.` |
| ⑥ | **收尾：致谢 ＋ 第二次致歉 ＋ 开放句** | `Thanks so much — and sorry again for the extra step. Please let us know if you need anything else from our side.` |

**硬判据表（判据 ①–⑤ 为 §4.17 原有；⑥–⑩ 为 v0.9.153／0.9.154 仪器判据）**

| # | 判据 | 合格线 |
|---|---|---|
| ① | **致歉只就事实** | 禁自我检讨式元评论（`I should have double-checked…`／`sorry for my carelessness`） |
| ② | **请求动词必须可被认出** | `reissue／resend／correct／revise／update` 都算请求动作（仪器原词表只有 `send／share／provide／confirm／issue` —— 本封 `Could you please reissue …` 曾被判「未检出请求动作」，见 CLS-45） |
| ③ | **写一句缩小对方返工量的话** | "只动哪一处" —— 更正类**独有的价值点** |
| ④ | **不复述旧信息、不把对方引去第二个文档** | 本次有意不写旧地址；也不提"合同里已经是新地址" |
| ⑤ | **报告诚实性** | 无时间限制／无截止日时 §4.16 判据 ②③④⑥⑦ **未触发** ⇒ 摘要不得宣称齐备（CLS-45） |
| ⑥ | `no_trouble_note`（v0.9.154） | **"麻烦对方"的致意必须落在请求段或紧邻前／后一段**；**只写在收尾句里不算**（收尾那句 `sorry again for the extra step` 离请求太远，读者读到的是"通知我改一下"） |
| ⑦ | `no_own_fault`（v0.9.154） | **开场须有"我方失误"的定性**（道歉要有由来）；作用域＝请求段**之前**的段落；请求落在首段时跳过 |
| ⑧ | 两轴分离（CLS-19 第二形） | **柔和只加在语气层，请求动词（`reissue`）与对象（`the invoice`）一字不动** |
| ⑨ | `ci` 纳入退出码 | 新增档位必须真拦截（"打印了但不拦截"＝仪器失效） |

**致意词表（`CORRECTION_TROUBLE` · 7 条 · 逐字）**：`sorry|apolog(y|ies|ise|ize) to trouble|bother|inconvenience`／`sorry|apology …(≤70 字符) trouble|inconvenienc|bother|extra step|work|effort|round|mile`／`thanks (so much) for your|the patience|help|understanding with this`／`appreciate your patience|help|understanding with this`／`麻烦(你|您|了)`／`给您添麻烦`／`辛苦(你|您)`
**失误定性词表（`CORRECTION_OWN_FAULT` · 6 条）**：`our mistake|error|oversight|fault`／`that was on us|our mistake|error`／`my mistake|error|oversight`／`we sent|gave|provided|shared (you) the wrong|incorrect|outdated|old`／`是(我们|我方)(的)失误|问题|错误|疏忽`／`我们(给|发|提供)错`

**仪器档位**：`--kind correction`（**须与 `scan_reply()` 一起用** —— 本档只加两条特有判据；自检 145/145 → **158/158**）。

```bash
python3 .kol-tools/check_email_tone.py --text-file <更正邮件.md> --kind correction --body-only
```

**边界与豁免（作用域纪律 · 逐字）**

| # | 边界 |
|---|---|
| ① | **致意搜索面 ＝ 请求段 ＋ 紧邻前一段或后一段，排除收尾区**（收尾区 ＝ 第一条收尾开放句 `REPLY_CLOSING` 所在段落**及其之后**）。理由：上一版正是因为"收尾那句也算"，旧稿带着 `sorry again for the extra step` 一路绿灯 |
| ② | 退化面：段落切不出来时退回"收尾句之前的全文"，**宁可漏报也不假报** |
| ③ | `no_own_fault` 在请求落在首段（无前置段）时跳过 |
| ④ | 引文遮罩同 §4.16（`mask_quotes()`） |

**已认可语料路径**：`.kol-tools/_fixtures/emails/user-approved-techiteasy-invoice-address-correction.txt`（地址更正）／`user-approved-brief-reference-correction.txt`（brief 指位更正 —— 同族「我方给错信息」的信型，含 `Apologies — that was my mistake:` 开场 ＋ 两条指位参考）。
**交付件**：`docs/marketing/kol/2026-09-29-techiteasy-invoice-address-correction-email-draft.md`（`--kind reply --body-only` 退出码 0）。

---

> ⟦重建说明⟧ 原文件曾出现 §4.18.2／§4.18.3／§4.18.4 的编号引用，但**任何证据文件（变更日志／章程／缺陷类／能力地图／Ticket）均未引用这三节** ⇒ 判定为编号误记，**重建版不设这三节**（避免出现无来源的假章节）。

### 4.18 进度同步 ＋ 拍摄 brief 前置沟通（v0.9.164 新增骨架 · v0.9.165–0.9.169 五轮补判据 · 2026-09-30 · 教训 228–232 · CLS-55／56／57）

> **场景**：执行期（合同已签、定金发票已回传、款项在走流程／样品在寄送）**主动同步进度**，并提前把品牌方的创作参考给到 KOL。
> **用户指令（v0.9.164）**：告知财务已处理首款／样品发货正常／提前沟通拍摄 brief。
> **判据一句话（v0.9.164）**：**「进度同步」不是汇报，而是「让对方不用问也知道到哪一步了」** —— 每条进度落到**状态 ＋ 我方下一步承诺**。
> **判据一句话（v0.9.169 定版）**：**执行期同步信不是「汇报进度」，而是「让对方知道到哪一步了、自己要做什么、接下来会发生什么」；** 连贯靠自然过渡（时间／因果连接词），不靠标签与清单 —— **语气层要像同事说话，结构层仍要一件事一段、每段给目的或承诺。**

> 🔴 **首轮路由暴露真实能力缺口**：Skill 无此档、路由器先**误命中 Follow Up** ⇒ CLS-55（信型目录缺一档 ⇒ 只能凭感觉写）。

#### 4.18.1 骨架表（定版语料反查 · 段 3／4／5 示例为 v0.9.169 自然过渡定版）

> **权威来源**：`.kol-tools/_fixtures/emails/user-approved-techiteasy-progress-brief.txt`（用户 2026-09-30 认可定版，逐字）。
> **「七段骨架」的段数与出处** ＝ 变更日志 0.9.164「补七段骨架＋五条判据＋边界」。
> ⟦重建：中证据 · **段名**按定版语料反查归纳，原文段名待补⟧

| 段 | 作用 | 定版逐字示例 |
|---|---|---|
| ① | 称呼 | `Hi Alex,` |
| ② | **暖开场 ＋ 本信目的**（不罗列事项） | `Hope you're doing well. I'd like to share a few updates with you.` |
| ③ | **款项进度**（状态 ＋ 我方下一步承诺） | `Our finance team has already submitted the deposit payment. If it doesn't go through today, we'll make sure it goes out first thing once we're back after the National Day holiday (October 1 to 7).` |
| ④ | **快递／样品**（v0.9.165：**有单号必须写齐四件套**） | `In the meantime, your samples are already on their way. They've been shipped and are in transit to you now — the tracking number is YT2627100707354863, and you can follow the delivery here: https://www.17track.net/en. I'll keep an eye on it as well and let you know as soon as anything changes.` |
| ⑤ | **brief 前置**（链接 ＋ 目录名 ＋ 页码，三件齐全） | `One more thing — to make filming easier for you, we've sent over the content brief. The direction we think suits your channel best is Shooting Storyline 2, so when you're writing the script, we'd love for you to reference it:` ＋ 两条 `- Long-form video: <Canva 链接> — please see "Shooting Storyline 2" in the contents on page 2 (pages 10–12 of the document).`／`- Short video: <Canva 链接> — same reference: …` |
| ⑥ | **反馈请求（带缓冲且留余地）** | `Have a look when you get a moment and let us know if this direction works for you — and if you'd prefer a different angle, we're happy to talk it through together.` |
| ⑦ | **下一步预告 ＋ 暖收尾** | `Once the samples are with you, we'll go through the details and the timeline with you.` ＋ `Thanks so much, and please let us know if you need anything else from our side.` ＋ `Best regards,`／署名／`Global OneClick` |

> 🔴 **v0.9.169 对段 3／4／5 的替换**：0.9.168 曾用「开头一句地图 ＋ 段间同一套连接词（`On the payment`→`On the samples`→`And on the video direction`）」，**该做法作废**；定版改用自然过渡 —— `In the meantime,`／`One more thing —`。**删标签、不删事项**。
> 🔴 **快递信息四件套（v0.9.165 · 判据 ⑥）**：**查询入口 ＋ 单号 ＋ 当前状态 ＋ 跟进承诺**；**有单号必须写齐四件；无单号才用承诺式；两者不得混写。**

#### 4.18.5 五条写法（v0.9.166 新增 · 用户退回首版并给参考邮件「学思路不照抄」）

> **用户退回首版原话**：「**这封 EDM 整体写得并不太好**」，并给两封**参考邮件**（发货同步／guideline 同步）。
> **病根** ＝ **汇报体**（只说"我方做到哪了"，**没给对方动作／没预告下一步**）。

| # | 写法 | 依据（参考邮件逐字） |
|---|---|---|
| ① | **每条信息配一个"对方要做什么"** | `Once you have received the shipment, please notify us and kindly inspect the product for any issues.` ＋ `Thank you in advance.` |
| ② | **预告下一步节奏** | `After reviewing the video, we'll send you the tracking link and the referral link that you can include in the description.` |
| ③ | **给链接／表单要写"为什么给你"** | 参考邮件给 form 时写明用途：`This will help us better support you and track the impact of your video on our traffic and sales.` |
| ④ | **请求带缓冲且留余地** | `If you have any changes or run into any issues, feel free to update the form anytime.` |
| ⑤ | **暖收尾** | `Please let us know if you have any questions about the product. Thank you so much for your understanding and efforts. Looking forward to your reply!` |

> 🔴 **作用域纪律（v0.9.166）**：**收尾句的 `please let us know…` 不算"对方动作"** —— 它是礼貌收口、不是给对方安排的任务；不切掉它，任何邮件都会"显得有对方动作"，判据就失效了（实测：用户否掉的那一版因为收尾句而蒙混过关）。
> 🔴 **学思路不学清单（CLS-57 第一形）**：我把参考邮件里的「收到后请通知我们并验货」当成**结构性要件**搬进本信，于是本信从三件事变四件事、且第四件与「款项还没到账」的语境不搭 ⇒ 用户第三次退回「**整个邮件太割裂了，核心只要说三件事情**」。

**判据 ①–⑫ 全表（v0.9.164–0.9.169 累积 · 代码名 → 含义）**

| # | code | 判据 | 版本 |
|---|---|---|---|
| ⑥ | — | **快递信息四件套**（查询入口／单号／当前状态／跟进承诺），**不得与"发货后给单号"混写** | 0.9.165 |
| ⑦ | `no_counterpart_action` | 通篇没有"请对方做的事"（**作用域排除收尾区**） | 0.9.166 |
| ⑧ | `no_next_step` | 没有"下一步预告" | 0.9.166 |
| ⑨ | — | **延迟／假期说明五件**：原因 ＋ 区间与责任主体 ＋ 预计影响 ＋ 我方承诺 ＋ 致谢耐心；**且不要求截止日**（同步档：假期是**信息**，不是限制） | 0.9.167 |
| ⑩ | — | **一件事一段 ＋ 事项数量由本信目的决定 ＋ 每段给目的或承诺**（0.9.168 的"开头一张地图／段间同一套标签"**作废**） | 0.9.169 改写 |
| ⑪ | `label_style_transition` | **段首禁「事项标签＋冒号」**（`On the payment:`／`Regarding the samples:`） | 0.9.169 |
| ⑫ | `item_roadmap` | **开头禁罗列事项清单**（`— on the payment, the samples, and the video direction.`） | 0.9.169 |

**「下一步预告」与「对方动作」词表（逐字）**

| 表 | 条数 | 例 |
|---|---|---|
| `PROGRESS_ACTION` | 9 | `please let us know\|notify\|contact\|tell us\|check\|inspect\|test\|take a look\|confirm\|share\|verify\|review\|fill in\|update\|send`／`let us know`／`notify us`／`kindly inspect\|test\|check\|notify\|confirm`／`feel free to`／`please do not hesitate`／`(请\|麻烦)(您\|你)?(告知\|通知\|联系\|检查\|测试\|确认\|反馈)` |
| `PROGRESS_NEXTSTEP` | 6 | `(we\|they)('ll\| will) (send\|share\|go through\|walk\|confirm\|arrange\|keep\|update\|provide\|prepare\|make sure\|carry on\|continue\|proceed\|release\|process\|pay\|handle\|start\|begin)`／`once …, we('ll\| will)`／`after …, we('ll\| will)`／`next step`／`following that`／`(我们会\|接下来我们\|后续我们会)…(发送\|同步\|安排\|确认\|跟进\|提供)` |
| `PROGRESS_LABEL_LEAD` | 2 | 行首 `(on\|regarding\|about\|as for\|with regard to\|re) the <2–26 字符>:`／行首 `… the <2–26 字符> — ` |
| `PROGRESS_ITEM_ROADMAP` | 2 | `— on the …, the …, and the …`／`updates?\|things\|items\|notes\|topics? … on the …, the …, and the …` |

**仪器档位**：`--kind progress`（自检演进：165/165 → 171/171 → 180/180）。

```bash
python3 .kol-tools/check_email_tone.py --text-file <进度邮件.md> --kind progress --body-only
python3 .kol-tools/email_quality_metrics.py --strict   # 本档同时登记度量器
```

**边界与豁免（逐条如实登记）**

| # | 边界 |
|---|---|
| ① | **判据 ②③④（截止日类）在同步档跳过** —— 假期是**信息**、对方无需动作，要求截止日就是**假阳性**（CLS-04 第 12 形） |
| ② | **判据 ⑦⑧ 作用域＝正文（`REPLY_CLOSING` 之前）**，收尾区不算 |
| ③ | **判据 ⑪⑫ 作用域＝全文**（标签可能出现在任一段首，不切收尾区）；排除面：**非段首出现**、`On the other hand,`、中文稿 |
| ④ | 🔴 **仪器能力边界（诚实登记）**：本节只能证"**没有**条款式标签与事项罗列"，**证不了"读起来连贯"** —— 后者**由人工过**，且不得在摘要里冒充已验（CLS-45／CLS-57 同族） |
| ⑤ | **不适用**：办事型回复（§4.16）、更正类（§4.17）、拒信／砍价／问价（各有骨架） |
| ⑥ | **豁免面**：一封里可同时含"进度"与"前置输入"（同一次阅读的同一件事），但**不得**混入催办／报价／条款 |

**已认可语料路径**：
- 定版：`.kol-tools/_fixtures/emails/user-approved-techiteasy-progress-brief.txt`
- 参考样例（**用户给的、非我方定版**）：`user-approved-shipping-tracking-sync.txt`（发货后运单号同步）／`user-approved-review-guideline-sync.txt`（Review Guideline 同步）／`user-approved-brief-reference-correction.txt`
- 交付件：`docs/marketing/kol/2026-09-30-halliday-techiteasy-deposit-paid-brief-email-draft.md`（`--kind progress --body-only` **退出码 0**）

---

### 4.19 信息核实类（confirm）定版骨架（v0.9.171 · 2026-09-30 用户定版后固化 · 教训 238 · CLS-61）

> **用户指令**（定版后）：「**不是留痕，是下次有类似邮件的时候，你可以按照这个标准产出**」。
> **场景**：请对方核对**一条系统提示／信息**（本件 ＝ 银行账户核实：系统提示 `payee type "Individual"` 与账户信息不匹配，附截图 ＋ 完整英文翻译）。
> **判据一句话**：**核实类的落点是"只是想再确认一次"；第三方原文必须完整、可指位；不预设承诺、不致歉。**

**四段骨架**

| 段 | 内容 | 定版逐字示例 |
|---|---|---|
| ① | **暖开场 ＋ 事由** | `Hope you're doing well. One quick thing on the deposit payment — our finance team was processing the bank payment and the interface showed a prompt asking us to confirm the account details. I've attached the screenshot.` |
| ② | **系统／第三方原文完整翻译** | `The full English translation of the prompt under the account information on the right side of the screenshot is below:` ＋ **段落级引文块**（系统原文全文，含 `"Individual"` 等嵌套引号） |
| ③ | **落点「只是想再确认一次」（陈述式）** | `So this email is just to confirm with you once more that the account details match. If everything is correct, we'll continue with the next steps.` |
| ④ | **标准收口** | `Thanks so much, and please let us know if you need anything else from our side.` ＋ `Best regards,`／署名／`Global OneClick` |

**硬判据表**

| # | 判据 | 合格线 |
|---|---|---|
| ① | **第三方原文完整引用并指明位置** | 截图非英文时**附全文翻译**；原文用**段落级引号**（段首段尾成对引号 ＋ 内文 ≥40 字符） |
| ② | **不写"我们准备付款了"这类预设承诺** | 用户否掉的写法 `we're ready to send it` ⇒ 删 |
| ③ | **落点写成陈述式**（「只是想再确认一次」） | **不写成 `Could you please …?` 式请求** |
| ④ | **不致歉** | **非我方过失** |
| ⑤ | **引文不按我方措辞判定** | `mask_quotes()` 遮罩生效 —— 引文里的 `Please confirm …`／`Please carefully verify …` 不得被读成"我方对对方下指令" |

> 🔴 **CLS-61（认可产出必须进标准层）**：**留痕** ＝ 交付稿内部记录；**标准件** ＝ **逐字入已认可语料 ＋ 骨架写进 Skill ＋ 能力地图登记**（可路由、可回归、可作基准）。**纪律：凡用户认可的产出，一律问「该进哪个标准层」。**

**仪器档位**：`--kind reply`（**引文遮罩后退出码 0**）。

```bash
python3 .kol-tools/check_email_tone.py --text-file <核实邮件.md> --kind reply --body-only
```

**边界与豁免**：① **短引文不豁免**（<40 字符，如 `"Shooting Storyline 2"`）—— 阈值只挡"整段引用"，防把"把要对方做的事塞进短引号"放过去；② 本档不判截止日类判据（本信型无需对方在某个时点做动作）；③ **温度档 3**（暖开场 ＋ 事务）。

**已认可语料路径**：`.kol-tools/_fixtures/emails/user-approved-techiteasy-account-confirmation.txt`（能力地图第 30 条登记）。

---

### 4.20 回执／致谢类（ack）定版骨架（v0.9.171 · 2026-09-30 用户定版后固化 · 教训 238 · CLS-61）

> **场景**：对方确认后回一封（本件 ＝ KOL 回复「账户信息无误」→ 回执：致谢 ＋ 已转财务 ＋ 节后第一时间付款）。
> **判据一句话**：**这封不要求对方做任何事，所以只需让他知道「收到了、我们在办、什么时候办好」。**

**四段骨架**

| 段 | 内容 | 定版逐字示例 |
|---|---|---|
| ① | **开场致谢** | `Thanks again for confirming — I've passed this on to our finance team, and they'll carry on with the payment from here.` |
| ② | **「何时继续」的我方承诺** | `As we mentioned earlier, our office will be closed for the National Day holiday from October 1 to 7. So if the payment doesn't arrive during the holiday, we'll make sure it goes out as soon as we're back.` |
| ③ | **「有问题随时沟通」独立成段** | `If you have any questions at all, please feel free to reach out at any time.` |
| ④ | **标准收口** | `Thanks so much, and please let us know if you need anything else from our side.` ＋ `Best regards,`／署名／`Global OneClick` |

**硬判据表（本档只查三件，收尾句由主干统一查）**

| # | code | 判据 | 合格线 |
|---|---|---|---|
| ① | `no_thanks` | **开场两段内必须有致谢** | **只写在收尾句里不算**（那读起来像收据不像回执）；判定时剔除称呼行与**落款式短句**（≤20 词且匹配收尾模式） |
| ② | `no_resume_commitment` | **提到我方时间安排（假期／延迟）时，必须有「何时继续」的我方承诺** | 对方读到的是「节后第一时间就办」，不是「要等」 |
| ③ | `label_style_transition`／`item_roadmap` | **禁条款体标签与开头罗列事项**（复用判据 ⑪⑫ 形态检查） | 0 命中 |
| ④ | — | **不加"麻烦你了"** | 本信型**无需对方行动** |
| ⑤ | — | **结尾两层**：先「有问题随时沟通」，再标准收口句（**合并成一行亦可**） | 用户追加要求 |

**词表（逐字）**

| 表 | 条数 | 例 |
|---|---|---|
| `ACK_THANKS` | 4 | `\bthanks?\b`／`\bthank you\b`／`\bthanks again\b`／`(谢谢\|感谢\|多谢\|辛苦了)` |
| `ACK_RESUME` | 5 | `(we\|I)('ll\| will) (make sure\|send\|arrange\|process\|pay\|release\|get\|keep\|let you know\|follow up\|update\|confirm)`／`as soon as we('re\| are)? (back\|return\|reopen\|open)`／`(right) after the holiday(s)\|break`／`(节后\|假期后\|回来\|复工)…(第一时间\|尽快\|立刻\|马上\|会)`／`(我们\|我会)…(尽快\|第一时间\|马上\|立刻)…(支付\|付款\|处理\|安排\|发送\|同步)` |

**仪器档位**：`--kind ack`（自检 200/200 → **213/213**）。

```bash
python3 .kol-tools/check_email_tone.py --text-file <回执邮件.md> --kind ack --body-only
```

**边界与豁免**

| # | 边界 |
|---|---|
| ① | **ack 档不跑 `scan_reply()`** —— 那是办事型判据（限制段要目的句／承诺／截止日），回执信里本来就无需请求、也无需截止日，跑了就会把本封判成「缺目的句」 |
| ② | **摘要只报本档自己的项**：**不列"不复述／请求动作／无时间限制"** —— 那些不适用于本信型，列进去等于自造空绿（CLS-45 同族） |
| ③ | **反向控制**：同一封信在 `reply` 档仍须报 `no_purpose`（证明信型隔离真生效） |
| ④ | **新增档位必须同步退出码表达式**（本档曾因漏改函数末尾 `return` 造成"有 ❌ 报告却退出码 0" · CLS-45 第 4 形 · 教训 239） |
| ⑤ | **温度档 4**（同事口吻） |

**已认可语料路径**：`.kol-tools/_fixtures/emails/user-approved-techiteasy-payment-ack.txt`（能力地图第 30 条登记）。

---

### 4.21 首封 Pitch 定版骨架（v0.9.172 · 2026-09-30 标准层覆盖审计后补齐 · 教训 239–240 · CLS-62）

> **来源**：2026-09-30 用户提问「之前那么多阶段对应的邮件是否都有入库为标准件」后的**审计与补齐**（审计结论：我方定版仅 **7 件**；首封／条款／Follow Up／问价／合同往返／微信话术六个阶段只有早期骨架）。
> **判据一句话**：**冷邮件的第一道门槛是可信度 —— 五件齐：背书／为什么找你／内容角度／三档报价／时间线。**

**五件必要件（`SCAFFOLD['pitch']` · 逐字取自仪器 · 判据来源＝A 版本定版）**

| # | code | 必要件 | 缺件含义 | 补法（逐字） |
|---|---|---|---|---|
| ① | `no_credibility` | **我们是谁 ＋ 服务过谁**（背书） | 冷邮件的第一道门槛是可信度 | 开场补一句（`a leading digital marketing agency … trusted by brands like DJI, OPPO …`） |
| ② | `no_why_you` | **为什么找你** | 没有这句，对方读到的是群发 | 补（`We've been following your [content category] content and think …`） |
| ③ | `no_content_angle` | **产品翻译成内容角度** | 只讲参数＝让对方自己想怎么拍 | 补（`What makes it especially interesting for content is … which creates a natural story around …`） |
| ④ | `no_rate_ask` | **三档报价请求** | 首封的落点就是拿到可比较的报价 | 补三档清单（`could you share your rates separately for: 1 dedicated YouTube video + 1 Short ／ 1 video ／ 1 Short`） |
| ⑤ | `no_timeline` | **发布时间说明** | 对方要据此判断档期 | 补（`The content needs to be published in October and will include 60 days of YouTube paid usage.`） |

**定版骨架（逐字 · `.kol-tools/_fixtures/emails/user-approved-pitch-a.txt`）**

| # | 段 | 内容 |
|---|---|---|
| 1 | Subject | `Halliday Paid Collaboration \| AI Glasses That Enhance Every Moment` |
| 2 | 开场自我介绍 ＋ 背书 | `Hope you're doing well! This is Six from Global OneClick, a leading digital marketing agency based in China, trusted by brands like DJI, OPPO, Anker Innovations, etc. reaching out on behalf of Halliday about a paid YouTube collaboration featuring the Halliday G2 AI Glasses.` |
| 3 | 为什么找你 | `We've been following your [relevant content category] content and think the product could fit naturally into the kind of content your audience already enjoys.` |
| 4 | 内容角度 | `What makes it especially interesting for content is its unobtrusive see-through display … which creates a natural story around workplace productivity testing, meeting workflow optimization and authentic day-in-the-life hands-on reviews.` |
| 5 | 三条 highlights ＋ 官网链接 | `- Meeting Flow — …`／`- Everyday Features — …`／`- Best-in-category Hardware — …` ＋ `You can take a quick look here: https://www.hallidayglobal.com/products/halliday-g2` |
| 6 | 时间线 | `The content needs to be published in October and will include 60 days of YouTube paid usage.` |
| 7 | 三档报价请求 | `If you're interested, could you share your rates separately for:` ＋ `- 1 dedicated YouTube video (8+ minutes) + 1 YouTube Short`／`- 1 dedicated YouTube video (8+ minutes)`／`- 1 YouTube Short (up to 60 seconds)` |
| 8 | 其他机会（**仅 MRP 链路**） | `We're also supporting other paid YouTube collaborations through a Google creator marketing program, including:` ＋ 逐行「品牌 — 品类」＋ `If any of these brands also feel relevant to your channel, feel free to mention them in your reply. …` |
| 9 | 落款 | `Best,`／`Six`／`Global OneClick` |

**仪器档位**：`--kind pitch`（自检 216 → **249**）。

```bash
python3 .kol-tools/check_email_tone.py --text-file <pitch.md> --kind pitch
```

**边界与豁免**

| # | 边界 |
|---|---|
| ① | **新场景先定信型**：目录里没有就先补骨架再动笔（CLS-55） |
| ② | **判据只在「我方措辞」上跑**（`mask_quotes()` 先遮罩引文）—— 引自系统提示／对方原文／合同条款的文字不得算作"我写了这一件" |
| ③ | 产品段写法与 MRP 专属段口径**以基线 §4.9 为准**（本节只补 v0.9.172 新增的必要件判据与仪器档） |
| ④ | **「其他机会」段（骨架第 8 段）仅 MRP 链路保留，非 MRP 项目删除** —— 依据基线 §4.9 第 7 条 |
| ⑤ | 温度档 **3**（热情 ＋ 可信度 ＋ 具体证据） |

**已认可语料路径**：`.kol-tools/_fixtures/emails/user-approved-pitch-a.txt`（A 版本定版）＋ `.kol-tools/_fixtures/reference/stage-examples/README.md`（参考样例索引）。

---

### 4.22 合作条款 terms ＋ 合同往返 contract（v0.9.172 · 2026-09-30 补齐）

**A 版 · 合作条款邮件（可勾选回复）**

> **判据一句话**：**条款信最容易被读成最后通牒 —— 开场先给"这些都可以谈"的安全感，再要求逐条回复，并预先化解"被品牌方改内容"的抗拒。**
> **判据来源** ＝ 已认可定版 `user-approved-terms-first.txt`（＋合同往返两件）。

**四件必要件（`SCAFFOLD['terms']` · 逐字）**

| # | code | 必要件 | 缺件含义 | 补法（逐字） |
|---|---|---|---|---|
| ① | `no_open_for_discussion` | **「这些都可以谈」的安全感句** | 条款信最容易被读成最后通牒 | 开场或收尾补（`all terms listed below are open for discussion`） |
| ② | `no_itemised_reply_request` | **「请逐条回复」的引导** | 不写清，对方只会整体回一句，来回翻倍 | 补（`We would appreciate it if you could include your response to each of these terms in your reply email:`） |
| ③ | `no_creative_freedom_note` | **「尊重你的创作自由」的预先化解** | 对方最抗拒的通常是"被品牌方改内容" | 补（`We will only check for objective mistakes … while respecting your creativity.`） |
| ④ | `no_next_step_contract` | **「确认后发合同」的下一步预告** | 条款阶段必须让对方知道流程还有几步 | 补（`Once we've confirmed the details, we'd love to send over a contract …`） |

**定版骨架（逐字 · `user-approved-terms-first.txt`）**

| # | 段 | 内容 |
|---|---|---|
| 1 | 开场 | `Thank you for your interest in reviewing the Halliday G2 AI Glasses. Before proceeding, we'd like to discuss a few terms with you.` ＋ **`Please note that all terms listed below are open for discussion`** ＋ 索要发货信息（`please provide your shipping address, name, and phone number for shipment arrangements`） |
| 2 | 逐条回复引导 | `We would appreciate it if you could include your response to each of these terms in your reply email:` |
| 3 | **七条条款（编号 1–7 · 与基线 §4.10 同口径）** | `Content`／`Shipping & Schedule`／`Draft Preview`／`Partner Access & Usage`／`Payment`／`Publishing Requirements`／`Deliverables` |
| 4 | 下一步预告 | `Once we've confirmed the details, we'd love to send over a contract to make sure everything is clearly understood on both sides.` |
| 5 | 收尾 | `We are open to discussing any adjustments needed.` ＋ `If everything above looks good to you, we'd be happy to move forward and share the content brief.` ＋ `Best regards,`／署名／`Global OneClick` |

**B 版 · 合同往返（谈判回复／发合同要签署）**

> **判据一句话**：**合同阶段对方最想知道「你们到底接受了哪些」—— 先列接受、再谈剩余；不可让的给内部原因 ＋ 共情；且不能停在「看完了」，必须落一个动作。**
> **语料来源**：用户给定语料「合同条款沟通回复」（`_VOICE-PAIRS.md` 范例对 #15）。

**三件必要件（`SCAFFOLD['contract']` · 逐字）**

| # | code | 必要件 | 缺件含义 | 补法（逐字） |
|---|---|---|---|---|
| ① | `no_stage_summary` | **「进展／接受情况」的总述** | 合同阶段对方最想知道"你们到底接受了哪些" | 开场补（`We've gone through everything with our team, and we're happy to accommodate most of your requests, including …`） |
| ② | `no_next_action` | **明确的下一步** | 合同信不落一个动作，就会停在「看完了」 | 补（`Could you please sign it when you have a moment?` 或 `You can simply reply with these filled in.`） |
| ③ | `no_flexibility_language` | **让步／共情语气** | 合同往返里「我们也理解你」这句决定对方签得快不快 | 补（`We completely understand wanting to protect the time you've invested.`） |

**定版骨架（逐字要点 · `user-approved-contract-negotiation.txt`）**

| # | 段 | 内容 |
|---|---|---|
| 1 | 致谢 ＋ **接受总述** | `Thanks so much for taking the time to review the agreement and share your thoughts!` ＋ `We've gone through everything with our team, and we're happy to accommodate most of your requests, including the payment schedule, production timeline, music licensing, YouTube reposting restrictions, likeness protections, and liability cap.` |
| 2 | 剩余待对齐项总起 | `… there are just a few final details we'd love to align on to make sure everything works well for both sides.` |
| 3 | 逐条（每条：共情／内部原因 ＋ 我方提议） | `1. Termination & Payment`（`We completely understand wanting to protect the time you've invested.`）／`2. Creative Control & Usage Rights`（`We fully respect your creative freedom …` ＋ 许可证非转让 ＋ 30 天广告期起算点 `from its first paid ad launch, provided we begin within 21 days of publication` ＋ 无水印成片 ＋ BPA 覆盖两条视频）／`3. A Few Other Details`（内容下架先打招呼／联盟链接与 tracking link 优先位／**管辖法不可让并给内部原因 ＋ 共情**） |
| 4 | 收尾 | `Everything else looks good to us!` ＋ `Thanks again for your patience and flexibility, Alex. We're looking forward to working together …` ＋ `Best,`／`Six` |

**发合同要签署（逐字 · `user-approved-contract-final-send.txt`）**

| # | 段 | 内容 |
|---|---|---|
| 1 | 致谢 ＋ 合同已附 | `Thank you for confirming everything on the agreement — the final version is attached.` |
| 2 | **请签署（一个动作）** | `Could you please sign it when you have a moment?` |
| 3 | 发货五项清单 ＋ 回填说明 | 见 §4.15 |
| 4 | 承诺 ＋ 兜底 | `Once we have the signed agreement and your shipping details, we will get the product shipped and the collaboration scheduled.` ＋ `Let me know if anything looks off and we'll take care of it.` |

> 🔴 **§14.8.1 口径（v0.9.71 · 用户指令 · 与本信型同源）**：**条款清单只在"对方提出的那一轮"出现一次**；新版合同发出时只写「你提的都已改好 ＋ 新版已附 ＋ 请签署」—— **再罗列＝把每一条重新摆上谈判桌**（与"只写决定＋依据＋下一步"同源）。仍未收到的信息（发货 5 项）**同封再催**并写明用途（`to arrange the shipment`），不另开一封。

**仪器档位**：`--kind terms`／`--kind contract`（自检 216 → **249**）。

```bash
python3 .kol-tools/check_email_tone.py --text-file <条款邮件.md> --kind terms
python3 .kol-tools/check_email_tone.py --text-file <合同往返邮件.md> --kind contract
```

**边界与豁免**

| # | 边界 |
|---|---|
| ① | **合同的替换面 ＝「条款内容 ＋ KOL 信息」，条款内容的依据 ＝ 发给该 KOL 的「条款邮件」**（**不是只换名字和金额**）→ 合同出具细节见 §14 |
| ② | 不可让的条款必须给**内部原因 ＋ 共情**（能力地图 `edm-terms-contract` 的 `acceptance` 第 3 条） |
| ③ | 判据只在**我方措辞**上跑（引文遮罩） |
| ④ | 温度档 **2**（事务、清单化、留兜底句）／合同往返偏长（先列接受再谈剩余） |
| ⑤ | **新增档位必须同步退出码表达式**（本档曾漏改 ⇒ 有 ❌ 报告却退出码 0） |

**已认可语料路径**：`.kol-tools/_fixtures/emails/user-approved-terms-first.txt`／`-contract-negotiation.txt`／`-contract-final-send.txt`。

---

### 4.23 Follow Up（两轮定版）（v0.9.172 · 2026-09-30 补齐）

> **来源**：已认可定版两轮 `user-approved-followup-1.txt`（`Following Up:`）／`-2.txt`（`Final Follow-Up:`）。
> **判据一句话**：**跟进不是复述，但要再说一次原因；只要一个"回一句就行"的动作。**
> **口径沿革**：基线 §4.11（v0.6.34）为**早期骨架**；能力地图 `edm-followup` 的 `note` 明示：旧条目曾指 §4.11 —— **现以 §4.23（两轮定版骨架）为准**；工作流文档同向（`01-marketing-chain-workflow.md:367`：「§4.11 已被 §4.16.5 矩阵与 §4.23 部分取代，**以 §4.23 为准**」）。

**三件必要件（`SCAFFOLD['followup']` · 逐字）**

| # | code | 必要件 | 缺件含义 | 补法（逐字） |
|---|---|---|---|---|
| ① | `no_step_aside` | **「给对方台阶」的一句** | 跟进信最容易读成催办 | 补（`Just wanted to follow up once more in case my previous emails got buried in your inbox 😊`） |
| ② | `no_reason_again` | **「为什么仍然是你」** | 跟进不是复述，但要再说一次原因 | 补（`your tech review content was one of the reasons we reached out`） |
| ③ | `no_low_friction_ask` | **低门槛的落点** | 跟进信只要一个"回一句就行"的动作 | 补（`Please feel free to share your rate and availability if you'd like to explore it with us.`） |

**长度上限**：**≤ 200 词**（超限 code ＝ `too_long_for_followup`；"跟进／IM 一旦变长就读成复述或催办"）。

**两轮定版逐字对照**

| 轮次 | 首行／主题 | ①原因句 | ②产品句 | ③落点 |
|---|---|---|---|---|
| **第一轮** | `Following Up on the Halliday G2 Paid Collaboration` | `your tech review content was one of the reasons we reached out` | `Halliday G2 is a camera-free pair of AI glasses with a binocular waveguide display, bringing notes, talking points, real-time translation and the Halliday AI Assistant right into your lenses.` | `Please feel free to share your rate and availability if you'd like to explore it with us.` |
| **第二轮** | `Final Follow-Up: Halliday G2 Paid Collaboration` | `your tech review content felt like a great fit` | `It's a camera-free pair of AI glasses with a binocular waveguide display — notes, talking points and translations appear right in your lenses.` | 同第一轮 |

**两轮共同骨架（逐字）**：`Hi,` → `Hope you're doing well!` → **台阶句**（`Just wanted to follow up once more in case my previous emails got buried in your inbox 😊`）→ 原因句 → 产品句 → 落点句 → `Looking forward to hearing what you think!` ＋ `Best,`／`Six`／`Global One Click`。

**仪器档位**：`--kind followup`（自检 216 → **249**）。

```bash
python3 .kol-tools/check_email_tone.py --text-file <followup.md> --kind followup
```

**边界与豁免**

| # | 边界 |
|---|---|
| ① | **两轮封顶**，第二轮之后不再联系 |
| ② | **第二轮只升级明确度（主题写 `Final`），不升级压力** |
| ③ | 判据只在**我方措辞**上跑；**必要件写在引文里不得算**（`[degenerate:scope]` 控制） |
| ④ | 长度＝**最短档**（`_VOICE-PAIRS.md` 阶段长度曲线：Follow Up 相对最短）；**温度档未在 `_VOICE-PAIRS.md` 中逐信型明列** ⇒ ⟦重建：弱证据 · 待补⟧；不复述、不列档位、不写产品长定义段 |
| ⑤ | 基线 §4.11 的**标题前缀口径**（follow-up 不写 `Subject:` 前缀）与本档并存；§4.11 的"两轮内容区分"条已被本档取代 |

**已认可语料路径**：`.kol-tools/_fixtures/emails/user-approved-followup-1.txt`／`-followup-2.txt`。

---

### 4.24 问价（rate ask）＋ 微信话术（IM）（v0.9.172 · 2026-09-30 补齐）

**A 版 · 问价邮件（价格优先）**

> **判据一句话**：**价格优先 —— 先把报价确认下来，再见面的渠道／形式都可以让对方选（渠道弹性不影响请求精度）。**
> **口径出处**：`user-approved-rate-ask.txt`（定版）。**问价邮件的完整骨架与言语行为门禁见基线 §5.3**（`--kind quote`）；本节只补 v0.9.172 新增的定版骨架与档位登记。

**定版骨架（逐字 · `user-approved-rate-ask.txt`）**

| # | 段 | 内容 |
|---|---|---|
| 1 | 主题 | `Re: Halliday Paid Collaboration \| AI Glasses That Enhance Every Moment` |
| 2 | 致谢 ＋ 表态 | `Thanks for getting back to me, and glad this looks interesting on your side.` |
| 3 | **价格优先** | `We would like to get the rates confirmed first, and then we can continue there or wherever works best for you.` |
| 4 | **为什么是你（具体作品）** | `Your recent XR and AI glasses coverage, including the XREAL AURA and inmo GO3 reviews, is the kind of work we had in mind for the Halliday G2.` |
| 5 | **三档报价请求（与首封逐字一致）** | `As in our first email, could you share your rates separately for:` ＋ 三档清单 |
| 6 | **渠道／形式弹性（放行面）** | `If you would rather start from your own packages, that works too. Send over your conditions and rates, and we will take it from there.` |
| 7 | 收尾 | `Looking forward to your rate.` ＋ `Best,`／署名／`Global OneClick` |

> ⚠️ **与 §4.13.4 的边界**：第 6 段属**渠道／形式弹性**（**放行**），**不属**"对象放宽"式请求降级 —— 判别标准是**请求层（要什么／几项／按什么口径报）是否仍然精确**：本段**先给了三档清单**、再允许对方按自己的套餐回，故三档口径仍在。
> ⚠️ **`_VOICE-PAIRS.md` 范例对 #6**：否掉版 `…just send over your rates and conditions **and we'll take it from there**.` → 认可版 `…just send over your rates and conditions.`（用户原话：「你说可以发来你的报价信息，**但是不要加我们再往下推进**」）。**⟦重建：中证据 —— 定版语料第 6 段仍含 `and we will take it from there.`，与范例对 #6 的"认可版"表述存在差异，原文如何收口待补⟧**

**仪器档位**：`--kind quote`（言语行为 ＝「请你报价」；禁语框架 `QUOTE_FRAME_BANNED` 10 条；请求标记 `QUOTE_REQUEST_MARKERS` 10 条；另跑 `scan_vague_ask()` 见 §4.13.4）。

```bash
python3 .kol-tools/check_email_tone.py --text-file <问价邮件.md> --kind quote
```

**边界与豁免**：① 首轮**不亮预算**（对齐 §4.6／§5.1）；② 首封已给过条件时走**路径 A′：只引用不重复陈述**，措辞逐字一致；③ 「柔和 ≠ 模棱两可」见 §4.13.4。

**已认可语料路径**：`.kol-tools/_fixtures/emails/user-approved-rate-ask.txt`。

**B 版 · 微信／私信（IM 短文本）**

> **场景**：邮件未回 → 加微信后接上邮件触点并问价。
> **判据一句话**：**IM 里对方第一眼要确认"是不是熟人／正式来意"；换渠道必须接上上一次接触，否则像陌生人；加微信的目的就是拿到报价。**

**三件必要件（`SCAFFOLD['im']` · 逐字）**

| # | code | 必要件 | 缺件含义 | 补法（逐字） |
|---|---|---|---|---|
| ① | `no_identity` | **「我是谁、为谁做事」** | IM 里对方第一眼要确认是不是熟人／正式来意 | 开场补（`Hi Michelle — Jack here from GlobalOneClick. We look after creator partnerships for Halliday.`） |
| ② | `no_email_bridge` | **「此前发过邮件」的触点接续** | 换渠道必须接上上一次接触，否则像陌生人 | 补（`I wrote to you by email（six.gong@globaloneclick.com） a little while ago about …`，**并给出邮箱地址便于对方翻查**） |
| ③ | `no_rate_ask` | **问价落点** | 加微信的目的就是拿到报价 | 补（`Would you be open to sharing your rate for each of the following?` ＋ 三档清单） |

**长度上限**：**≤ 130 词**（超限 code ＝ `too_long_for_im`）。

**定版原文（逐字 · `user-approved-wechat-open.txt`）**

```
【微信好友验证信息】
Jack, GlobalOneClick - Halliday G2 collab.

【通过好友后的开场 ＋ 问价】
Hi Michelle — Jack here from GlobalOneClick. We look after creator partnerships for Halliday.
I wrote to you by email（six.gong@globaloneclick.com） a little while ago about a possible collaboration on our new G2 glasses. Your recent XR and AI glasses coverage — the XREAL AURA and inmo GO3 reviews in particular — is exactly the kind of work we had in mind.
Would you be open to sharing your rate for each of the following?
- 1 dedicated YouTube video (8+ minutes) + 1 YouTube Short
- 1 dedicated YouTube video (8+ minutes)
- 1 YouTube Short (up to 60 seconds)
```

**仪器档位**：`--kind im`（自检 216 → **249**）。

```bash
python3 .kol-tools/check_email_tone.py --text-file <IM话术.md> --kind im
```

**边界与豁免**

| # | 边界 |
|---|---|
| ① | **验证信息 ＋ 开场消息两段分开出**（定版即两段，标注 `【微信好友验证信息】`／`【通过好友后的开场 ＋ 问价】`） |
| ② | 三档清单与首封／问价邮件**逐字一致** |
| ③ | 对方要求加微信时**不拒绝、不立刻转、先要报价再推进**（§5.3.1 即时通讯诉求处置范式 · v0.9.44） |
| ④ | 判据只在**我方措辞**上跑 |

**已认可语料路径**：`.kol-tools/_fixtures/emails/user-approved-wechat-open.txt`。

---

### 附：仪器档位索引（`--kind` 全表 · v0.9.174）

| `--kind` | 信型 | 节 | 辅助开关 |
|---|---|---|---|
| （默认） | 语气禁令／拒信三段式／过度肯定 | §4.13／§4.13.1／§4.13.2 | `--allow-apology` |
| `hold` | 不推进的软性 hold | §4.13.3 | — |
| `quote` | 问价（＋请求降级扫描） | §5.3／§4.13.4／§4.24 A | `--vague-ask`／`--extract-code` |
| `bargain` | 砍价／后续议价 | §5.4 | `--bargain-phase first\|followup` |
| `reply` | 事务型回复／信息核实类 | §4.16／§4.19 | `--allow-info-echo`／`--body-only` |
| `correction` | 更正类回信 | §4.17 | 须与 `reply` 判据同用 |
| `progress` | 执行期同步 | §4.18 | `--body-only` |
| `ack` | 回执／致谢类 | §4.20 | `--body-only` |
| `pitch` | 首封 Pitch | §4.21 | `--body-only` |
| `terms` | 合作条款 | §4.22 A | `--terms`（交付物术语） |
| `contract` | 合同往返 | §4.22 B | — |
| `followup` | Follow Up 两轮 | §4.23 | — |
| `im` | 微信／私信 | §4.24 B | — |

> **实测时点（2026-09-30 · v0.9.172／0.9.173 后）**：`python3 .kol-tools/check_email_tone.py --self-test` ⇒ **自检 249/249 全过**；认可语料 **18 份**；`BANNED` 13／`DECLINE` 14／`CLOSING` 10／`FIT_PRAISE` 9／`HOLD_BANNED` 10／`VAGUE_ASK` 12／`QUOTE_FRAME_BANNED` 10／`CORRECTION_TROUBLE` 7／`CORRECTION_OWN_FAULT` 6／`PROGRESS_ACTION` 9／`PROGRESS_NEXTSTEP` 6／`ACK_THANKS` 4／`ACK_RESUME` 5。

