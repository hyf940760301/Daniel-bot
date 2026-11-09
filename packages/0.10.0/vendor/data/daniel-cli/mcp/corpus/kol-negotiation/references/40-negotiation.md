<!-- 本文件是 `docs/marketing/skills/kol-intelligence.md` L3210–L3779 的**逐字切片**（语料版本 0.9.205）；请勿在此改写判据，改动须回流源文件后重跑切分器 -->
<!-- 源节：§5 阶段 4 · 报价与价格谈判 -->

## 5. 阶段 4 · 报价与价格谈判（Negotiation）［**重建版 v0.6.40 · 2026-09-13**］

> **⚠️ 重建说明（必读）**：本节原件在 2026-09-13 的一次破坏性编辑中**丢失**（事故与纪律见 §11.7 复盘 / 错题 62）。
> 以下内容由**可追溯来源**重建，未标明来源的推断一律不写：①Skill 版本记录中 15 条 §5 相关条目（原文摘录见本节末尾「附录 5-A」）；②角色章程 `docs/roles/kol-expert.md` 的 §5.2 大纲；③交付物「口径与预算基准」sheet（现随表在线）；④工具链代码（`build_halliday_xlsx.py` / `check_numeric_consistency.py` / `selfcheck_*` / `audit_*`）。
> **凡上述来源未覆盖的细节，标 `［原件缺失·待补］`，禁止凭印象补写**；后续每完成一个项目按实际执行回补一节。

### 5.0 一页执行清单（§5.2.0 · 三步一自检，不可跳序）
取官方数据 → 算口径（均播/互动率/CPM）→ 做判定（预算占比 × CPM 双判）→ 查画像硬项（年龄/性别/地域）→ 写结论（判断＋理由＋建议）→ 写条款例外 → 自检 → 交付（飞书在线 ＋ 回读校验）。
> 来源：章程 §5.2 大纲（Skill v0.6.17 十一节）。

### 5.1 CPM 初步评估参考判据（团队专家口径 · 总监转达 2026-09-08）
| 项 | 判据 |
|---|---|
| 长视频合理 CPM | **$60–80** |
| 1 长 + 1 短套餐 | **$80–100**（合并曝光口径） |
| 判读（**内部参考基准，不写进交付物**） | CPM ≤$100 视为合理范围；>$100 偏高。**交付物里的判断词只有三种**（报价合理／报价偏高／报价过高，见 §13.3），旧写法「性价比高」等已废止 |
| 砍价目标价 | 目标 CPM（单条长视频 **$80**、套餐 **$100**）× 均播 ÷ 1000，取"好看"档位 |
| **区间性质（用户 2026-09-15 口径）** | **$60–80／$80–100 是"参考基准"，不是硬门槛**——目标价须结合①**创作者实际数据表现**（均播与互动率是否扎实、长/短视频孰强）②**原始报价与议价空间**（报价越虚高，允许的目标 CPM 越可上浮）弹性设定。数据扎实 ＋ 报价明显虚高时，目标 CPM 可放宽至 **$100**（实测例：Danny McGee 长视频均播 36.4k、互动率 1.5%，报价 $6,500 → CPM $178，目标价 $3,650＝CPM $100）；**放宽须在审核表 D 列写明理由**（数据表现＋报价空间），不得只写数字 |
> 来源：口径与预算基准 sheet 第 11 行；复跑脚本 `.kol-tools/build_halliday_xlsx.py`（`_tgt_cpm = 100 if _is_bundle else 80`）。
> `［原件缺失·待补］`：垂直溢价档明细、服务商加成口径。

### 5.2 报价审核方法论（已回复 KOL · 对内审核表）

#### 5.2.1 Daniel 官方数据源接入
tRPC 同源 `/api/trpc`；`auth.login` 换 cookie；**凭证由用户提供、禁止硬编码**；`contentType` 参数被服务端忽略 → 必须客户端过滤。

#### 5.2.2 指标口径（2026-09-13 修正版）
- **均播（口径 A）**：长/短视频均播＝官方公开视频中该 `contentType` 最近 10 条播放均值；**D 列与 J 列必须逐字同串**。
- **互动率（口径 A）**：Σ(点赞+评论) ÷ Σ(播放)，分类型各取最近 10 条；**O 列＝Engage Rate（总互动热度）**。Daniel 前端把同一字段挂了两个标签（Interact Rate / Engage Rate）→ **不能按标签取数，必须按字段取值链**。
- **CPM ＝ 报价 ÷ 均播 × 1000**；1 长 + 1 短套餐用合并曝光（长均播＋短均播）；**同一行只允许一个 CPM**（建议里的目标 CPM 必须写「对应 CPM」）。
- `averageViewsPerVideo` 是**另一口径，禁作分母**。
- **抽屉弹窗接口（用户 2026-09-13 提供 · 已实测可用）**：单个 KOL 抽屉＝一次性批量拿三条路由：
  `/api/trpc/discovery.getChannelInsight,discovery.getChannelDetail,discovery.getChannelVideos?batch=1&input={"0":{"json":{"channelId":…,"timeRange":"last_28_days"}},"1":{"json":{"channelId":…}},"2":{"json":{"channelId":…,"pageSize":50,"contentType":"all"}}}`
  - **`getChannelInsight`（带 `timeRange`）** 返回 `stats.overall / stats.vod / stats.shorts`，各含 `averageViewsPerVideo`、`engagementRate`、`views`、`uniqueViewers`，另有 `averageStats`（均播/均赞/均评）与 `audience`（简介兴趣/国家/性别/年龄等）。
  - **⚠️ 不带 `timeRange` 时返回空对象**——这正是此前误判「抽屉值接口取不到」的原因。
  - **⚠️ 无 YouTube Analytics 授权的频道该路由返回空**（实测 TechMagnet / Shopping with Amy 为空，DreamSushi 有值）→ 这类频道只能用公开视频清单口径并标注。
- **抽屉磁贴的前端计算式（逐字核验自前端产物 `KOLProfile.tsx`，2026-09-13）**
  ```
  u = useMemo(() => {
    let s = U?.videos;                                   // 篮子①：抽屉所在列表项自带的视频集（原样使用，不过滤 SHORTS）
    if (!s || s.length === 0) {                          // 篮子①为空时才用篮子②
      const p = z?.videos;                               // 篮子②：getChannelVideos(pageSize:50, contentType:"all")
      if (p?.length) s = p.filter(K => K.contentType !== "SHORTS");   // 篮子②过滤掉 SHORTS
    }
    if (!s?.length) return null;
    const a = s.filter(p => (p.views ?? 0) >= 100);      // 统一门槛：播放 <100 的视频剔除
    const L = a.map(p => p.views ?? 0).filter(p => p > 0);
    medianViews = median(L);  avgViews = round(mean(L));
    engagementRate = (Σlikes + Σcomments) / Σviews * 100;   // 注意：分母/分子取同一篮子 a
    videoCount = a.length;                                   // 卡片角标「Based on last N VOD videos」的 N
  })
  ```
  卡片＝**Recent Video Performance**，三块磁贴依次为 `Average Views`（avgViews）／`Median Views`（medianViews）／`Engage Rate`（engagementRate）。
- **单 KOL Full Profile 页的请求形状（用户 2026-09-13 提供 · 实测）**——五条子请求一次拿全：
  `{"0":{channelId}}`（Detail）｜`{"1":{channelId, timeRange:"last_28_days"}}`（Insight）｜`{"2":{channelId, pageSize:20, contentType:"all", pageToken:null}, "meta":{"values":{"pageToken":["undefined"]}}}`（Recent Video Performance 篮子）｜`{"3":{channelId, pageSize:20, contentType:"vod"}}`（长视频篮子）｜`{"4":{channelId, pageSize:50, contentType:"all"}}`（视频清单）。
  - **⚠️ 服务端忽略 `pageSize`**：实测 pageSize=20 与 50 返回条数相同（上限约 50）→ **"最近 N 条"必须客户端切片**，不能靠参数。
  - **`contentType` 取值**：`all` / `vod`（短视频用 `shorts`）。
- **✅ 两套口径已分别锁定（2026-09-13 · 用户现场读数 + 前端源码双向校准）**
  > **关键认知：审核表的 N 与 O 来自 Daniel 的两个不同卡片、两套不同篮子，绝不能用一个篮子同时算。**（此前对不上号的根因）

  **口径 A ＝ 审核表 N 列（Avg Views）｜来源＝右侧抽屉弹窗 →「YT Data Insight」卡片**
  前端 `CreatorSlideOver.tsx` 逐字逻辑：
  ```
  basket = [contentType=="VIDEO_ON_DEMAND" 且 views>=100] ∪ [全部 contentType=="SHORTS"]
  recent = basket 中「发布 ≤ 28 天」的视频
  if len(recent) >= 3:  median = sorted(recent.views)[floor(n/2)]        // 0-based 上中位
  else:                 median = sorted(basket[:30].views)[floor(n/2)]
  抽屉磁贴「Avg Views」显示的就是这个 median（标签写 Avg，实际是 median —— Daniel UI 口径如此）
  ```
  - 无 Analytics 授权的频道 → 抽屉切到「**Public Data**」变体，此时 Avg Views 用 **roster 的 `medianViews`**（缺失则 `订阅数 × 0.15`）——**这正是本表此前 N 值来源，也是与抽屉对不上的原因**。
  - 分类型：`vod` 篮子＝VOD 且 views≥100；`shorts` 篮子＝全部 SHORTS（无 views 门槛）。

  **口径 B ＝ 审核表 O 列（Engage Rate）｜来源＝full profile →「Recent Video Performance」卡片**
  ```
  basket = getChannelVideos {pageSize:20, contentType:"vod"} → 再剔 views<100   // pageSize 必须 20
  ER = Σ(likes + comments) / Σ(views) × 100
  同卡片另两块磁贴：Average Views = 该篮子 mean；Median Views = 该篮子 median；角标 N = 篮子条数
  ```

  **校准证据（逐项吻合）**
  | 频道 | 用户现场读数 | 接口复现（本 Skill 口径） |
  |---|---|---|
  | DreamSushi · N（抽屉） | **8.7k** | **8,655**（28 天窗口 n=9）✅ |
  | DreamSushi · O（profile） | **5.9%** | **5.92%** ✅ |
  | JMTech · O（profile） | **2.7%** | **2.73%** ✅ |
  | JMTech · N（抽屉） | 待核对 | 预测 **176,136**（28 天窗口 n=12） |
  | TechMagnet（09-12 记录） | 40,500 / 2.80% | 41,572 / 2.84% ✅ |
  | Shopping with Amy（09-12 记录） | 101,500 / 2.30% | 102,080 / 2.27% ✅ |

  **采集脚本**：`.kol-tools/harvest_drawer_basket.py` → `data/crawl/halliday-replies/drawer_basket.json`
  （含每频道的 抽屉 overall/vod/shorts median + 窗口来源 + profile 卡片的 median/mean/ER/N + roster 原值对照 + 28 天 insight 兜底，并记录 `runDate`）。
  **✅ 与用户权威表（`sheet=0nPcyO`）的对齐核验（2026-09-13，只读）**：Engage Rate **10/10 对齐（最大差 0.09pp）**；Avg Views **8/10 对齐（偏差 ≤4%）**；Followers / 国家(ISO) / CPM **10/10 对齐**（CPM 表内自洽＝价÷N×1000）。
  未对齐 2 行：Tech with Benefits（权威表 23,495＝名单行 `medianViews` 原值，计算式 29,122）、Tech Court（5,142 vs 6,575）→ 说明**这两行权威表取的是名单原值**，需现场读数确认抽屉是哪条分支；Yoma 偏差 -7.5%（该频道无授权→抽屉 Public Data→应显示 roster 值）。
  **结论**：口径 A/B 双通道成立；残余偏差集中在「有/无 Analytics 授权的抽屉分支」与「名单原值 vs 抽屉实时值」，采集时须逐频道记录所用分支。
  **跨天不可复现**：篮子随时间滚动（高频更新频道尤甚）→ 同一份表内所有数字必须同一天采集，并在数据来源列标注 `抽屉口径（读取日 YYYY-MM-DD）`。
- **由此得到的两条硬结论**：①**抽屉的 Average Views / Engage Rate 不是 `insight` 的字段，而是前端按「当前篮子」现算的**——因此「抽屉值取不到」的旧结论作废，但**必须复现篮子才能对上**；②`getChannelInsight`（带 `timeRange`）提供的是**另一套口径**（28 天窗口 `stats.overall / vod / shorts` 的 `averageViewsPerVideo`、`engagementRate`），**两者不可混用**。
- **待校准（Open · 关键阻塞 · 已收窄）**：篮子已收窄为「最新 N 条（contentType=all，views≥100）」，其中 N 疑似 10–20（Tech/Amy 命中 20，DreamSushi 命中 10）。~~待用户提供一次现场读数…锁定前不得改表。~~ **⚠️ 本阻塞已于 2026-09-13 解除**（§5.2.17 已封版、§5.2.18 已固化口径；N 按套餐形式取值、篮子＝有界全量）。此段为历史留痕，**不构成执行限制**。
- **`insight.audience` 字段字典（2026-09-13 补 · 此前因猜键名导致误判）**：`locationDistribution`（**受众国家占比**，形如 `{"IN":0.2994,"PK":0.0643,"US":0.0679}`）、`genderDistribution`（male/female/userSpecified）、`ageDistribution`（age18To24…age65Plus）、`affinityInterests` / `inMarketInterests` / `shoppingInterests`（兴趣分群，各含 `audienceSharePercentage` 与 `relativeRelevance`）。
  - **纪律：取 `audience` 时必须 dump 整个对象（`json.dumps` 或递归列出全部键）后再取值，禁止按印象猜键名**——曾因只查 `topCountries` / `countryDistribution` 而把受众国家误标为「无官方数据」（错题 67）。
  - 受众国家 / 性别 / 年龄均为品牌方 Brief 硬项：**美国、欧洲占比偏低时必须显式写出结论**（例：「受众以印度为主（IN 29.9%）、美国仅 6.8%，不符合 US / CA / EU 要求」），不得只罗列数字。
- **Daniel 抽屉值的旧结论（已作废，保留供追溯）**：YT Data Insight 的 `Avg Views`、Video Performance 的分类型均播、个人主页 `Engage Rate` 在 API 中不可得（`avgViews` 为 null、`medianViews` 不等同）→ 只能用用户提供的截图/导出，或按用户口径标「无官方数据」。

#### 5.2.3 判定与排除规则

> **价格越线不单独构成排除 ·「可谈」档（用户 2026-09-15 口径固化）**：报价超过总预算一半（或 >$6,000／>60%）且**形式可用、身份合规、有品类匹配证据**者，一律**提报品牌方并给出建议砍价金额**——写明①目标价 ②对应 CPM ③参照行（同类已评估行的 CPM 带）④处理口径"砍得下来就合作，砍不下来就算了"；**不得因价格单独静默排除**。建议砍价金额须由我方可复核口径算出（N 与本行档位同口径），并在说明页留算术依据。反例（Danny McGee 首版）：三档全超预算即判"排除、不推进"，未给目标价 → 已改为"提报品牌方，建议砍价至 $1,800（CPM $220，1 条短视频口径）"。
- **双判**：占总预算比例 × CPM 效率。
- 报价 **>$6,000（＝总预算的 60% 以上）**，或单个 KOL 已占**总预算一半以上** → 价格过高。
- 预算基准（Halliday 实例）：活动总预算 **$10,000**、目标 **4 条视频（2 长 + 2 短）** → 单条均分 $2,500。
- 一 KOL 一档报价；取价优先级见 §5.2.11。
- 排除口径：①价格过高 ②形式不符（只做中插／不做独立视频）③法律或品类冲突 ④未提供报价或无意向；排除项须附 CPM 效率并把"预算性排除"与"非预算性排除"分开。

#### 5.2.4 结论表述标准 8 条（最高优先级 · 用户连续 6 轮评审提炼）
①只给判断、不做信息翻译（反例：整张 rate card 原样填入）；②结论带来源标注，无数据只写「无官方数据」（不写"未授权 Analytics"这类内部原因）；③必须有归纳性综合结论（正向 → 风险 → 建议）；④建议限定在品牌方既定需求内；⑤业务话术，禁技术术语与「基准」字样；⑥频道定位要点明与产品场景的交叉点与偏差；⑦删除对已排除对象的动作尾巴；⑧同一行内不得自相矛盾。
> 来源：Skill 版本记录 0.6.13 条（原文摘录见附录 5-A）。

#### 5.2.5 交付物结构（现行 11 列版 · 2026-09-13 用户精简后）

> **表间移动的信息随行（2026-09-15 固化 · 教训 46）**：KOL 从排除表回流审核表（或反向）时，**原表里品牌方与其他角色已填的内容必须逐列原样迁移**（荣荣/佳岚/Ash审核反馈、Halliday 审核反馈、Terms 例外项等），**留空＝信息丢失**；迁移后逐列回读比对（文本逐字一致）并在回报中列明迁移清单。

> **可复用空壳模板**：`docs/marketing/kol/_TEMPLATE-kol-review-table.md`（v1.0 · 2026-09-14）——含 3 个子表结构、逐列填写规范、**N（Avg Views）按成交形式取值与相加规则**、判定与判据速查、交付前自检清单；新项目复制即用。


`KOL ｜ 频道链接和邮箱地址 ｜ PIC初步审核反馈 ｜ 荣荣/佳岚/Ash审核反馈 ｜ 视频形式 ｜ 价格 ｜ CPM ｜ Followers ｜ Avg Views ｜ Engage Rate ｜ 国家/地区`
- **PIC初步审核反馈只写一行「不合作理由」**（见 §5.2.16 第 7 条）；**审核反馈列留空由审核人填**；通过表与排除表共用同一套逻辑与块格式。
- 早期 25 列版（含「报价与总预算占比」「数据来源与非官方标注」等）已按用户裁决删除；产出目录只放**一个**交付文件 ＋ **一个**飞书在线交付。

#### 5.2.6 列级规范与格式标准

> **订正类写入的列白名单（2026-09-15 固化）**：对既有交付表做"数据订正"时，必须①明确**可写列白名单**（只写有权威来源的列）②**人工已确认列**（如红人复用表「合作品牌」）**永不写入** ③**只覆盖权威源有值的格**（权威源为空则保留原值，避免清空）④写后逐列回读比对（"权威源有值但目标表不一致"的残留须为 0）并抽查受保护列未变。列映射与受保护列清单见 `docs/marketing/kol/_NOTE-reuse-sheet-protected-columns.md`。
- 单位与用词统一＝见 **§5.2.16**（均播 D↔J 同串、粉丝量 k/M、国家 ISO GB、竞品固定句、I 列三段短句、禁内部门槛与方法表述）。
- 金额 `"$"#,##0`、计数 `#,##0`、比率 `0.00%`；文本列左对齐＋顶部对齐；块间空行；**L 列 Terms 只写需评估的例外项、无例外留空**。
- **🔴 A 列 KOL 名称必须写全（2026-09-13 用户退回）**：名称取 **Daniel 频道官方 `title` 全文**（`discovery.getChannelDetail.title`），**不得用邮件签名、昵称或简称**；第二行写官方 `handle`。示例：频道 title `Spencer Scott Pugh` ＋ handle `@SpencerScottPugh` → A 列写两行即为 `Spencer Scott Pugh` / `@SpencerScottPugh`（写成 `Spencer Pugh` 即不合格）。**自检**：新增/复核行时用 `getChannelDetail` 逐行比对 title 与 handle（可复用 `.kol-tools/align_with_sheet.py` 的核验逻辑），简称、缺 handle、handle 与 title 不匹配均需修正。
- **🔴 单元格自动换行（2026-09-13 用户裁决 · 全表强制）**：所有**文本型长内容列**（A/B/D/I/J/L 等）必须开启**自动换行**（`word_wrap = auto-wrap`），让他人打开表格时能看到完整内容而不被截断；行高随内容自适应。**写入时即设**：`+cells-set --cells` 每个单元格带 `cell_styles.word_wrap="auto-wrap"`；已存在的列可用 `+cells-set-style --range … --word-wrap auto-wrap` 批量补设。**自检项**：交付前抽查最长文本列（D/I/J/L）是否均为 auto-wrap；出现 `overflow`/`word-clip` 即不合格。
- 单元格文本禁区：Markdown 星号、技术黑话、无依据建议、内部口径与门槛。

#### 5.2.7 交付前自检（**唯一权威链路 · 2026-09-16 收敛**）

> ⚠️ **本节是「交付前必跑链路」的唯一权威定义**（此前 §11 有两处顺序相反的列表，已改为指向本节）。

**标准链路（按序执行）**
```
daniel_client.py（取数）
  → harvest_daniel_enrichment.py（官方富化）
  → refetch_halliday_shorts.py（样本回补 · 按需）
  → build_halliday_xlsx.py（建表）
  → 【推送前重读表头，按列名定位】
  → selfcheck_halliday_review.py（交付规格）
  → audit_halliday_review.py（业务口径 39 项）
  → check_numeric_consistency.py（逐行数字一致性）
  → 推飞书 → 逐格 diff 回读
（排除表另跑 fix_excluded_sheet.py）
```
**三脚本职责**：`selfcheck` ＝交付规格（结构/格式）｜`audit` ＝业务口径（§5.2.12 八组 39 项）｜`check_numeric_consistency` ＝逐行数字一致性。**三者都过才可交付**。
`.kol-tools/selfcheck_halliday_review.py`（交付规格）→ `.kol-tools/audit_halliday_review.py`（业务口径 20 项）→ `.kol-tools/check_numeric_consistency.py`（逐行数字一致性）。

#### 5.2.8 错题集

> ⚠️ **编号纪律（2026-09-16 补 · 必须遵守）**：本文存在**两套编号**且历史上曾撞号——
> **「教训 N」**＝§2.2.8 教训库 ／ §11 复盘提炼的规则编号（现到 57）；**「错题 N」**＝本错题集的 before→after 案例编号（现存 56–69）。
> **52–58 两套都有**（如「教训 52」与「错题 52」不是同一条）。**引用时必须带类别前缀**（写「教训 52」或「错题 52」），**禁止只写数字**；新增条目一律取该序列的**下一个未用号**，并在写入时核对两序列不撞。
- **现存条目**：**错题 56–69**（散见 §5.2.16／§11.7／§11.10／§11.13；**顺序非递增，查找请按编号检索**）。
- **错题 1–55 明细随本次原件丢失**；重建索引＝附录 5-A 中提及「教训/错题」的版本条目（含教训 25/26 等），后续按项目回补为完整条目。
> `［原件缺失·待补］`：原 22 条 → 55 条的逐条正文。

#### 5.2.9 在线交付（飞书）与工具链
- 链路：`+workbook-import` 保格式 → 列级写入（**每格带 `word_wrap="auto-wrap"`**）→ **必须回读校验** → `+formula-verify`；D 列加粗须验 run 级 `<b val="true">`；样式缺失时用 `+cells-set-style --word-wrap auto-wrap` 补齐。
- **并发编辑纪律（2026-09-13 事故）**：用户会同时手改在线表 → **写入前重读表头、按表头名称定位列、写后按名称逐格核对**；`+cells-set --writes` 批量写可能静默跳过 → 全量 diff 后按需补写。

#### 5.2.10 受众性别评估标准
地域/年龄/**性别**三项均为品牌方 Brief 硬项；四档 ✅男性≥60%／⚠️50–60%／❌女性为主／❌接近均衡；**性别不匹配却仍进推荐位者，必须写「虽然…但是…」理由并降为补充位**，理由只取官方数据。

> **🔴 年龄口径（2026-09-16 定 · 曾出错）**：官方年龄为 **6 个整数分段**（`18-24 / 25-34 / 35-44 / 45-54 / 55-64 / 65+`，六档相加恒等于 1）。
> **只能做整档合并**：可写 `25–54`／`25–44`／`18–34`／`35–64`…；**不可写 `25–50`**（需劈开 45-54 档，数学上不可推导）。
> **列名必须等于实际计算的档位**——存量表曾出现列名「25–50 岁」而实算 `25-34＋35-44＋45-54`（＝25–54）的错误。**新表一律用可推导口径**；存量表按「不回溯」原则不改。

> **性别口径（同日补）**：官方为 `male/female/userSpecified` **三档且归一** → **男性占比直接用 `male`**；❌ 禁用 `male/(male+female)`（会系统性高估，实测差 5pp）。

#### 5.2.11 取价规则与报价构成披露
取价优先级；**单档 ≠ 套餐**；集成档不得写成独立长视频；地区团队档位必标；**每行写「报价构成」**；对方未报价则明确"待追问三档"，不得代填。

#### 5.2.12 全量体检（**重建版 · 2026-09-16** ｜ 依据 v0.6.19–v0.6.23 版本记录原文 ＋ 现存脚本）

**用途**：交付前对整张审核表做一次**全量机器体检**——从 Daniel 原始 JSON **重新计算全部指标**，与表内逐格比对，找出**真实数据缺陷**（不靠人眼抽查）。

**工具**：`.kol-tools/audit_halliday_review.py`（现存 · 195 行）

| 组 | 检查内容 |
|---|---|
| 结构组 | 行数/列数/表头、合并区间、空行 |
| 频道数据组 | N／长短视频均播／互动率 ↔ 原始 JSON 重算值 |
| 受众画像组 | 受众国家、性别、年龄、粉丝 Tier |
| 价格组 | 价格、CPM（＝价÷N×1000）、套餐档位一致性 |
| 文本格式组 | 换行、禁用词、Markdown 残留、单位统一 |
| 口径表组 | 口径表与本版数据自洽 |
| 判定一致性组 | 价格判断／GOC 判定／排除理由与数据有无矛盾 |
| 唯一性组 | 去重（cid 为准）、跨 sheet 一致性 |

**项数演进**：v0.6.19 首版 8 组 **35 项** → v0.6.20 增 C2 组 ＝ **38 项** → v0.6.22 增 D3 组 ＝ 38 项 → v0.6.23 D3 组改为核对 Engage Rate 口径 ＝ **39 项**。

**五条审计纪律（v0.6.19 固化 · 不可回退）**
1. **先排审计 bug，再改数据**——脚本报错先怀疑脚本，不得直接改表
2. **样本缺失必须披露，不得估算**
3. **样本不足须回补**（用 `refetch_halliday_shorts.py` 多页合并重取）
4. **同名指标只能一个口径名**
5. **列语义回到模板**——不得按记忆中的列号判断

**实测价值**（v0.6.19 首跑）：一次体检发现 **2 处真实数据缺陷**——采集页数不足导致 8 个频道样本不全；回补后修正 `Parker Burton` N 503,267→**818,853**、O 补齐 1.68%；`Custom Adventurist` N 64,743→**59,553**、O 3.41%→**2.53%**。

**回补工具**：`.kol-tools/refetch_halliday_shorts.py`（现存 · 108 行）

#### 5.2.13 数据可得性门控（**重建版 · 2026-09-16** ｜ v0.6.20）

> **用户裁决原话**：「均播取不到就明确输出取不到，**不要强行算**，CPM 可以标记为空；**所有数据和结论都不要强行创造结果**。」

**门控阈值** `MIN_SAMPLE = 5`
- 单段 `0 < n < 5` → 标「**样本不足**」
- `n = 0` → 标「**取不到**」
- 「1 长 + 1 短」套餐 → **两段都可用**才给结论

**联动改写七处（缺一即不合格）**
1. **CPM 在均播不可用时留空**（H 列「—」、不写公式）；互动率同规则置空
2. I 列判断改「**待核验（曝光数据取不到）**」，且**不给砍价目标价**
3. **超预算行不得声称「CPM 回到合理区间」**
4. J 列第 1 项改「待核验」
5. D 列报价/综合结论/均播块与 X 列**同步写明取不到原因**（含「长均播仅供参考、不作 CPM 分母」）
6. 推荐/备选组合标注「CPM 取不到」
7. 口径表同步

＋ §10 自检第 17 项；错题 33–35。

#### 5.2.14 分类型口径（**重建版 · 2026-09-16** ｜ v0.6.21 · ⚠️ **窗口部分已被 §5.2.18 取代**）

> ⚠️ **取代说明（必读）**：本节原始定义里的窗口是「公开视频清单**最近 10 条**」。后由 **§5.2.18（v0.6.44+）改为「有界全量」**（最近 12 个月 ∩ 最新 100 条；翻页→去重→剔 views<100→按类型取中位），错题 68 亦实证 `contentType:"all"` **只返回一页**。**窗口一律以 §5.2.18 为准**；本节保留的是**分类型结构**与**双口径交叉核对**。

**双口径（严格不混用）**

| 口径 | 来源 | 在表内的角色 |
|---|---|---|
| **口径 A** | 公开视频清单（窗口按 §5.2.18 ＝ 有界全量），按 VOD／SHORTS 分类型取中位 | **CPM 分母**（与用户侧第三方数据标定一致） |
| **口径 B** | Daniel 洞察 `stats.overall / vod / shorts` | **交叉核对**，**不作 CPM 分母** |

**逐段取值规则**（`segment_metrics()`）
1. 口径 A 该段样本 ≥5 → 用 A
2. 否则口径 B 该段 `videoCount ≥5` → 用 B
3. 都 <5 → 判**取不到**（走 §5.2.13 门控）
4. **「1 长 + 1 短」套餐须两段都可用**，才给**合并曝光**

**五处输出**：D 列均播块、J 列第 1 项、Y 列、O 列、口径表——按类型分别列示**长均播／短均播／合并曝光**。

＋ 错题 36–37。

#### 5.2.15 Engage Rate 口径（**重建版 · 2026-09-16** ｜ v0.6.22 ＋ v0.6.23 更正）

**O 列 ＝ Engage Rate（总互动热度）** ＝ `Σ(点赞+评论) ÷ Σ(播放)`，按 **§5.2.14 口径 A** 分类型取；套餐含两类内容时**长视频优先**；样本不足留空。

> ⚠️ **易混点（v0.6.23 更正的实质）**：Daniel 档案页卡片上那块叫 **Interact Rate**（「上手操作」比例）的是**另一个指标**，**本表不采用**。前端 **31 个 chunk 遍历确认不存在 `interactRate` 字段**。

**卡片回退链（v0.6.22 实证）**：`listItem.engagementRate → insight.stats.overall.engagementRate × 100 → 「—」`；实测本项目两个 List 的富化字段（`engagementRate`／`medianViews`／`avgViews`／`cqiScore`／`tier`）**全为 None**（245 ＋ 271 条），故页面卡片实际显示的就是**洞察整体口径**，8 位无洞察者显示「—」。

**O 列表头**：由模板原拼写「**Engagemant**」更正为「**Engage Rate**」（带样式写入并回读核对底色/加粗/居中）。

**输出与防回退纪律**
- D 列首句写明 Engage Rate 口径，并附洞察**整体值**作交叉核对、标注「概念为 Interact Rate、**本表不采用**」
- Y 列交叉核对**仅列长/短视频分类型数据，移除「整体」**（该值即 Interact Rate 同源数 · v0.6.24）
- 体检 **D3 组断言 O 列不得等于洞察整体值**（防回退）

**实测更正效果**：`DreamSushi` 3.04%→**3.99%**、`MULTIPLESHOTSFIRED` 2.67%→**4.24%**、`Tech Court` 2.31%→**0.89%**；5 行门控行按规则留空。


#### 5.2.16 审核表「单位与用词」统一（**重建版 v0.6.41** · 2026-09-13 用户例修固化）

> **起因**：用户点名「**单行 KOL 内需要确保所有数据统一口径**」——同一指标在 D 列与 J 列出现两种写法（`54,001` vs `54.0k`）即视为数据不统一，属交付事故。
> **重建说明**：本节随 §5 一并丢失，现按版本记录 + 用户例修 + 工具实现重建（规则内容与当时的执行标准一致）。

**8 条硬规则（对内审核表全部适用）**
1. **均播单位全表同规则**：数值 ≥1000 写 `X.Xk`（1 位小数），<1000 写原值（如 `240`、`776`）；**同一行 D 列（频道匹配）与 J 列（第 1 项）的均播必须逐字同串**，由同一处数据生成。
2. **粉丝量**：<1M 用 `k`（1 位小数），≥1M 用 `M`（2 位小数，如 `1.45M`）。
3. **国家/地区一律 ISO 代码**：`GB`（禁 `UK`）；P 列与 R 列同口径。
4. **竞品内容固定句**：`7个月内有N条竞品AI Glasses测评（品牌），最近是X个月前（品牌）`；无则 `7个月内无竞品AI Glasses测评`。N＝标题命中竞品 AI 眼镜品牌的视频数（按 `videoId` 去重、7 个月窗口）；**D 列与 J 列同源同数**。
5. **I 列固定三段短句**：`判断：`（**仅三种：价格合理／价格偏高／价格过高**，见 §13.3；旧写法「性价比高」「无法判读」已废止；确无报价时留空并在反馈段说明）→ `理由：`（报价金额＋占总预算比例＋CPM 与 $60–80 合理区间对比）→ `建议：`（一句话动作，给出目标价；**目标 CPM 必须写「对应 CPM」**以区别于当前 CPM）。
6. **禁止内部门槛与方法表述进入交付内容**：`超过总预算 60%`、`砍幅超 60%`、`依据：`、`曝光数据取不到`、`曝光效率不判读（缺曝光数据）`、`MRP`、`n=…中位`、`报价与条款（非官方）`；J 列第 1 项标题只用 `--合格` / `--无官方数据`。
7. **排除表「PIC初步审核反馈」列＝只写一行** `不合作理由：<客观依据> → <结论>`（不重复报价/画像/频道匹配）；**没有理由的行必须补写**。
8. **在线表并发编辑纪律**：用户会与我同时手改同一张在线表（删列/改表头都发生过）→ **写入前重读表头、按表头名称定位列（禁用旧列号）、写后按名称逐格核对**；表头数量或顺序变化即停写并重建列映射。

**工具**：`.kol-tools/fix_excluded_sheet.py`（按上述规则批量订正线上排除表并回读校验）＋ `.kol-tools/check_numeric_consistency.py`（逐行核对 D↔J 均播、报价、CPM、粉丝量、O 列）。

**错题（表／口径线）**
- **错题 56**：排除表 D 列写 `长视频均播 54,001` 而 J 列写 `54.0k` —— 同一指标两种格式，用户视为数据不统一。
- **错题 57**：J 列第 1 项标题写 `--待核验（曝光数据取不到）`、正文写 `曝光效率不判读（缺曝光数据）` —— 把采集方法写进了交付物。
- **错题 58**：D/I 列写内部预算门槛（`超过总预算 60%`、`砍幅超 60%`）—— 用户视角看不懂且不该知道。
- **错题 60**：用户在我读取与写入之间**删掉了在线表的一列**（原 C「Halliday审核反馈」），我按旧列号写入 D 列 → 实际写进了「荣荣/佳岚/Ash审核反馈」列，覆盖了该列占位内容（已逐格还原）。正解＝§5.2.16 第 8 条：写入前重读表头、按**表头名称**定位列、写后按名称核对。
- **错题 69**：把**用户手改/手填的单元格**当作"数据不一致"反复提请确认（用户回："这个是我改的，所以不要动"）。正解＝§5.2.18 第 6 条：用户手改值＝最终值，一律不改、不反复提请；核验只用于验证我方取值逻辑。
- **错题 68**：用**单页样本**（`contentType:"all"` 仅一页 ≈50 条）判断频道「长视频样本过少、不具备参考价值」——Jai Vaghela 实为 47 条长视频、均播 9.1k（翻页后）；根因＝不知道 `all` 只返回一页而 `vod` 可深翻页，且未做 `videoId` 去重。正解＝§5.2.18「池的定义＝翻页全量池（记录页数与池子条数）」。**影响**：部分频道长/短视频均播与 N 会明显变化（如 UltimateiDeviceVids 长视频均播由 45,280（45 条）改为 5,932（535 条））。
- **错题 67**：把**受众国家占比误标为「无官方数据」**——Daniel 实际有数据，只是我按印象查了 `topCountries` / `countryDistribution` 等不存在的键，未 dump `audience` 全部字段（正确键＝**`locationDistribution`**）。实例：Jai Vaghela 受众 IN 29.9% / US 6.8% / PK 6.4%，据此该行判断应由「价格低可推进」修正为「**价格低但受众市场不符**（美国仅 6.8%）」。正解＝§5.2.2「audience 字段字典＋必须 dump 全部键」纪律，且受众国家为 Brief 硬项、占比偏低须显式结论。
- **错题 66**：D 列「频道匹配」只写泛化定位（"频道主要以数码电子、电子硬件内容为主"），**没有给出基于近 5–10 条视频的品类/品牌实证，也没有匹配判断**——用户 2026-09-13 退回：「可以定制化多说一些，比如尤其以智能相机、无人机（大疆）、智能穿戴（手表/眼镜）测评为主…结合近期 5–10 条视频给出专业判断，让人知道你真的看了视频」；同时要求**简练且命中要点、不铺陈**。正解＝§5.2.19 三层要点（定位／实证／判断）＋六条门禁，工具 `channel_digest.py`。
- **错题 65**：把**前端抽屉的窗口值（近 28 天优先／回落最新 30 条）**当成交付口径 —— 低频频道样本过小，中位极不稳定，与全量口径偏差达 166%–408%（6 Months Later、MULTIPLESHOTSFIRED、TechUtopia 等）；且未把"口径来源＋采集日"写进交付物，导致与用户手抄值对不上时无法归因。正解＝§5.2.18：窗口一律用**全量篮子**，N 用**类型匹配均播**，交付物标注口径与采集日。
- **错题 64**：把 `lists.getItems` 的**名单快照字段**（`medianViews` / `engagementRate`）当成抽屉里的实时值写进表 —— 该字段随后端滚动，只有"无授权分支"下才等于抽屉显示值；正确做法＝按 §5.2.17 双分支取值，并记录采集日（实测：Tech with Benefits 名单快照 23,495 vs 抽屉现值 29,122；Tech Court 5,142 vs 6,575）。
- **错题 63**：把 KOL 邮件里的**两档报价相加**当成本行价格（Lexy Savvides 写成 `1条长视频内集成+1条短视频 = $3,500`），而用户权威表取的是**单档**（`1条短视频 $1,000`）——与「一 KOL 一档报价」口径冲突，并连带把推荐组合算错（Tech Court + Lexy）。正解＝§5.2.3「一 KOL 一档」＋§5.2.11「单档≠套餐、集成档不得写成独立长视频」：**档位必须与用户选定口径一致，禁止自行相加**。
- **错题 62**：Skill 大范围编辑**未做快照、未做行数校验**，导致 §5 整节（约 400 行，含 §5.1 CPM 判据与 §5.2.0–5.2.15）丢失，错题 1–55 与部分口径明细**永久损失**，只能从版本记录、章程与交付物重建。正解＝§12 文档编辑纪律：编辑前快照 → 定点替换并断言命中数 → 写后校验行数/字节变化量与关键锚点 → 章节编号连续性自检。

#### 5.2.17 Daniel 指标取值纪律（两套口径 · 2026-09-13 封版 · 后续新任务一律照此执行）

> 本节是**取值层的硬标准**：任何"从 Daniel 取数填表/写报告"的任务，先读本节再动手。取值方法源自前端源码逐字核验 + 用户权威表 10/10 对齐。

**① N（Avg Views）＝ 抽屉弹窗 →「YT Data Insight」卡片**
| 频道分支 | 取值 |
|---|---|
| **有 Analytics 授权**（`getChannelInsight{timeRange:"last_28_days"}` 返回非空） | **计算式中位（篮子取全量）**：篮子＝`[contentType=="VIDEO_ON_DEMAND" 且 views≥100] ∪ [全部 SHORTS]`，**取该篮子全部条目的中位** |
| **无授权**（insight 为空，实测 28 位中 8 位） | **名单行 `medianViews`**（抽屉切「Public Data」变体，实际显示的就是该字段）|

> **⚠️ 窗口规则（2026-09-13 用户裁决 · 覆盖前端实现）**：前端抽屉另有「近 28 天优先、不足 3 条回落最新 30 条」的窗口逻辑，**但用户要求我们的输出一律用「全量篮子」**——因为窗口值在低频频道上样本过小、中位极不稳定（实测 6 Months Later / MULTIPLESHOTSFIRED 等偏差可达 166%–331%）。
> ~~**我们的交付口径＝全量**：N＝整体篮子（VOD≥100 ∪ SHORTS）**全量中位**~~ **⚠️ 本句已作废（2026-09-16）**：「全量中位」描述的是**篮子（用哪些视频算）**，**不是 N 的取值维度**。N 的取值维度**一律按套餐形式**（见下方 ③ 与 §13.9）：1 长→长视频均播／1 短→短视频均播／1 长+1 短→相加。
> 正确表述＝**篮子＝有界全量（§5.2.18）；取值＝按套餐形式的类型值**。抽屉窗口值仅作现场对照，不进交付物。
> **O（Engage Rate）不变**：仍取 full profile「Recent Video Performance」卡片的 ER（已与用户权威表 10/10 校验）。
- 磁贴标签写 `Avg Views`，**实际是中位**（Daniel UI 口径如此，不要改标签、按值取）。
- **必须逐频道记录用了哪个分支 + 采集时间**。

**② O（Engage Rate）＝ full profile →「Recent Video Performance」卡片**
```
basket = getChannelVideos {channelId, pageSize:20, contentType:"vod"} → 再剔 views<100
ER = Σ(likes + comments) / Σ(views) × 100
```
- 同卡片另两块磁贴可供交叉校验：`Average Views`＝该篮子均值、`Median Views`＝该篮子中位、角标 N＝篮子条数。

**③ N 的权威定义（2026-09-14 用户澄清 · 此前逻辑有误，仅对新任务生效）**：
- **1 条长视频** → 取抽屉弹窗内 **`Long-form · Avg Views`**；
- **1 条短视频** → 取抽屉弹窗内 **`Shorts · Avg Views`**；
- **1 条长视频 + 1 条短视频** → **`Long-form Avg Views ＋ Shorts Avg Views`（两者相加）**，即"合并曝光"口径；
- **禁止**用"整体均播（overall）"或与成交形式不匹配的类型值当 N（此前的错误做法：一律取单一类型/整体中位，导致**低估曝光、高估 CPM**）；
- 若某频道取不到抽屉 per-type 值（无 Analytics 授权、或该类型无内容）→ 用 §5.2.18 有界全量池**同结构**计算（对应类型中位，按需相加），并在交付物标注来源与采集日。

**④ CPM**＝ 报价 ÷ **N（③ 的口径）** × 1000；判读区间沿用 §5.1（单条长视频 $60–80；1 长+1 短套餐 $80–100，**分母用相加后的合并曝光**）。
> **注（2026-09-15）**：上述区间为**参考基准非硬门槛**，砍价目标可按"数据表现 × 报价空间"上浮（上限可达 CPM $100），理由须写入 D 列（见 §5.1）。

**④ 三条硬纪律**
1. **同批同刻**：N 与 O 必须同一次采集拿到（篮子与名单值都会滚动；跨天复核出现 1–8% 漂移属预期，不是逻辑错）。交付物标注 `口径来源：抽屉/profile 卡片（采集日 YYYY-MM-DD）`。
2. **名单快照字段不得当抽屉值交付**：`lists.getItems` 的 `medianViews` / `engagementRate` 是**名单快照**（会滚动），只有"无授权分支"下它才等于抽屉显示值；把它当抽屉值直接写表＝错题 64。
3. **与用户权威表对齐＝核验自己逻辑的手段**：用户表是权威基准。发现差异**先自查我方取值路径（路由 → 分支 → 时点）**，**严禁改动用户表**；确认是对方旧值时只做提示。

**⑤ 接口速查（已实测）**
- 抽屉：`discovery.getChannelInsight,getChannelDetail,getChannelVideos`（3 路 batch）→ `{0:{channelId,timeRange:"last_28_days"},"1":{channelId},"2":{channelId,pageSize:50,contentType:"all"}}`
- Full profile：同上 5 路 batch → `…"2":{pageSize:20,contentType:"all",pageToken:null + meta}`、`"3":{pageSize:20,contentType:"vod"}`、`"4":{pageSize:50,contentType:"all"}`
- 坑：**`timeRange` 必填**（不传 → insight 返回 `{}`，这是"取不到"误判的根源）；**`pageSize` 只在 20 时生效**（传 50 会忽略 `contentType` 返回整份清单）；`contentType` 只认 `all` / `vod`（`shorts` 与 `vod` 同篮子，分类型必须客户端按每条视频的 `contentType` 过滤）。
- 工具：`.kol-tools/harvest_drawer_basket.py` → `data/crawl/halliday-replies/drawer_basket.json`（含 抽屉 median/分支 + profile 卡片 median/mean/ER/N + 名单原值对照 + `runDate`）。


#### 5.2.18 数据窗口标准 与 对齐核验规程（2026-09-13 复盘后固化 · 后续取数与核验一律照此执行）

**A. 窗口标准：一律「全量篮子」（禁用时间窗口）**
| 指标 | 篮子 | 窗口 | 统计量 |
|---|---|---|---|
| **N（审核表 Avg Views）** | **按本行「合作视频数量与形式」取值：1 条长视频 → 抽屉 `Long-form · Avg Views`；1 条短视频 → 抽屉 `Shorts · Avg Views`；**1 长 + 1 短 → `Long-form Avg Views ＋ Shorts Avg Views`（两者相加，合并曝光）**｜取不到抽屉值时，按有界全量池以**同结构**计算（分类型中位，按需相加）并标注来源 | **全量** | 见左（抽屉指标为中位口径；自算用中位） |
| **长视频均播**（D/J 列） | `VOD 且 views≥100` | **全量** | 中位 |
| **短视频均播**（D/J 列） | `SHORTS` | **全量** | 中位 |
| **O（Engage Rate）** | full profile「Recent Video Performance」卡片的 vod 篮子（`pageSize:20, contentType:"vod"`，剔 views<100） | 该卡片自带 | `Σ(赞+评)/Σ(播放)×100` |
| **CPM** | ＝报价 ÷ N × 1000（N 用上表定义） | — | — |

- **🔴 池的口径＝「有界全量」（2026-09-13 用户选定 B 口径 · **适用范围：后续每一个新任务、每一位新增 KOL 的评估一律按此执行**；存量已手填行不回溯）**：
  **池 = 最近 12 个月 ∩ 最新 100 条**——先按发布时间倒序**翻页**取够 100 条（`contentType:"vod"` 支持深翻页），再剔除发布超过 12 个月的条目；按 `videoId` 去重、剔 `views<100`、按每条视频自身 `contentType` 拆长/短视频后取中位；报告中记录**页数、池条数、时间范围**（harvester 的 `poolInfo`）。
  **为什么不全量历史**：翻到频道全史（200–600 条、跨多年）会把早期内容算进来，与"当前表现/界面读数"偏离更大（实测 UltimateiDeviceVids 长视频均播：全史 5,932 vs 有界 33,790）。
  **为什么至少翻页**：`contentType:"all"` 只返回一页（≈50 条）→ 曾据此误判「长视频样本过少」（错题 68）。
  **既有行不回溯**：用户已手改/手填的既有行一律不改（§5.2.18 第 6 条）。
- **🔴 池的定义＝翻页全量池（2026-09-13 用户指出后修正）**：`getChannelVideos` **必须跟随 `nextPageToken` 翻页**——实证 **`contentType:"all"` 只返回一页（约 50 条）**，而 **`contentType:"vod"` 支持深翻页**（实测 5–12+ 页、130–600 条；返回体为混合池）。做法：翻页至 `nextPageToken` 为空或达上限（默认 12 页/600 条）→ **按 `videoId` 去重** → 剔 `views<100` → 按**每条视频自身 `contentType`** 拆长/短视频 → 取中位；并在报告中记录 **页数 + 池子条数**（可追溯）。
  **⚠️ 只用单页会严重误判**：Jai Vaghela 单页仅 2 条长视频 → 误判「长视频样本过少、不具备参考价值」；翻页后实为 **47 条、均播 9.1k**（错题 68）。
- **为什么禁用窗口**：前端抽屉用「近 28 天优先、不足 3 条回落最新 30 条」，在低频频道上样本过小 —— 实测同一频道「窗口值 vs 全量值」偏差达 **166%–408%**（6 Months Later 12,500→59,822；MULTIPLESHOTSFIRED 823→972；TechUtopia 54,393→206,159）。
- **N 用「类型匹配」的依据**：用户 2026-09-13 在新增行中把 N 定为**该行档位对应的类型均播**（长视频档 $3,000 ÷ 长视频均播 45.3k → CPM $66），与既有 Lexy 行（短视频档 N＝短视频均播 4,791→4,800）一致。
- ⚠️ **既有行可能不一致**（用户手工从抽屉抄的窗口 overall 或名单快照值，如 DreamSushi 8,600、Tech with Benefits 23,495）→ **不回溯改表**，但报告/交付物须标注口径。

**B. 对齐核验 SOP（只读，五步）**
1. **读权威表**：只读拉取用户手改的表（`+csv-get --sheet-id`），**严禁写入**；解析时按**表头名称**定位列（防列增删）。
2. **取官方值**：按 A 的窗口标准同批采集（N/O/分类型/Followers/国家），记录 `runDate`。
3. **逐列比对**：输出 `表值 / 我方值 / ΔN / ΔO`；**阈值**：ΔN > **5%** 标红复核，ΔO > **0.3pp** 标红复核。
4. **归因五类**（自动判定，见 `.kol-tools/align_with_sheet.py`）：
   ① **无授权分支**：频道无 Analytics → 抽屉显示名单 `medianViews`（活值），两边时点不同即漂移；
   ② **名单快照**：表内值恰等于 roster `medianViews`（旧快照）；
   ③ **样本敏感**：篮子条数 <20 → 中位对新增视频极敏感；
   ④ **时点漂移**：以上皆非的小幅差异（篮子滚动）；
   ⑤ **口径错配**：ΔO >0.3pp 或数值方向异常 → 人工复核（可能是路由/分支取错）。
5. **结论与动作**：区分「我方逻辑错」（→ 修脚本/口径）与「时点或来源不同」（→ 只提示，**不改用户表**）；报告顶部固定写明：口径名 + 采集日 + 是否只读。
6. **用户手改值＝最终值（2026-09-13 用户明确）**：用户手工填入/修改的单元格（含 N/O/CPM 等他自选的来源口径）视为其最终决定，**一律不改**；核验结果仅用于验证我方取值逻辑，**不得作为"不一致"反复提请修改**——仅在用户主动要求复核该行时才展开分析。

**C. 工具**
- `.kol-tools/harvest_drawer_basket.py` → `data/crawl/halliday-replies/drawer_basket.json`：按频道输出 **full（标准：N/长/短 全量中位 + 均值 + 样本量）**、profile 卡片（median/mean/ER/N）、**窗口值**（对照）、roster 原值（对照）、28 天 insight（兜底）。已覆盖 30 位（含 2 位新增）。
- `.kol-tools/align_with_sheet.py`（**只读**）：`--sheet <sheet_id> [--threshold 5] [--out 报告.md]` → 输出对齐表 + 自动归因 + 偏差行统计。


#### 5.2.19 D 列「频道匹配」块写法标准（三层要点 + 近 5–10 条实证 · 2026-09-13 用户退回后固化）

> **用户原话要点**：除了频道定位，还要**定制化多说一些**——「尤其以智能相机、无人机（大疆）、智能穿戴（手表、眼镜）测评为主」；**结合 KOL 近 5–10 条视频内容给出专业判断**，让人知道你**真的去频道里看了视频并做了总结**；但**切忌过度表达**，要**简练且命中要点**，不是把内容平铺出来。

**结构（整块 ≤3 句 + 1 行数据）**
| 层 | 写什么 | 要求 |
|---|---|---|
| ① 定位 | 频道主赛道（官方 topic + 内容类型） | 1 句，沿用既有句式「频道主要以…内容为主」 |
| ② **内容聚焦（实证）** | **近 5–10 条视频里反复出现的具体品类/品牌/内容形式**，点名 **≤3 个** | 必须可从标题回溯；用官方品牌名（大疆/DJI、iPhone、XREAL…）；**不逐条列标题** |
| ③ **匹配判断** | 与本品类的**交叉点** ＋ **偏差/教育成本**，给结论词 | 结论词三选一：`与产品定位非常匹配`／`与产品场景部分重合，有品类教育成本`／`与产品定位不匹配` |
| ④ 数据行（另起一行） | 竞品句（7 个月内 N 条竞品AI Glasses测评，最近 X 个月前）＋ `长视频均播 X、短视频均播 Y，结合互动率 Z%，表现良好/一般/互动偏冷（官方数据）` | 保持既有格式，数值用**全量篮子**口径（§5.2.18） |

**六条硬门禁**
1. **必须有实证**：②的品类/品牌只能来自近 5–10 条标题，**禁止凭印象或行业通识编造**；
2. **简练优先**：整块 ≤3 句（数据行不计），每句只讲一件事；出现"标题清单式平铺"即不合格；
3. **点名 ≤3 个**品类/品牌，取与产品相关度最高的；
4. **必须有判断**：只描述不结论不合格（结论词见上表③）；
5. **实证与数据自洽**：如"以手机测评为主"应与"长视频均播/互动率"量级相符；
6. **付费占比慎用 API 字段**：`hasPaidPlacement` **实测与前端 paid 标签不一致**（如 TechMagnet 近 10 条字段全为 `False`，而实际多为展会/推广合作）→ 只作辅助信号，写表时以**前端 paid 标签/用户判断**为准或标注字段口径。

**正例 / 反例**
- ✅ `频道主要以数码电子、电子硬件内容为主，尤其以智能相机、无人机（大疆）、智能穿戴（手表、眼镜）测评为主，与产品定位非常匹配；近 10 条中有 4 条为智能手表/眼镜类测评（最近 1 个月前）。`
- ✅ `频道以 lifestyle 为主、无专业测评，近 10 条多为日式零食/美妆/独居 vlog，仅零星电子好物出镜；与产品场景部分重合，存在品类教育成本。`
- ✅（新例·实测）`频道以旧款 iPhone 长期使用回顾（"Day in the Life"）为主，另有 iPad/MacBook 与扫地机器人（Tineco/ECOVACS/Dreame）测评；近 10 条无智能穿戴或 AI 眼镜内容，与产品定位匹配度一般，需较强品类教育。`
- ❌ `频道主要以数码电子内容为主。`（只有定位、无实证、无判断）
- ❌ 把近 10 条标题逐条列出（过度表达）

**工具**：`.kol-tools/channel_digest.py --name "<频道名>" --n 10` → 输出近 N 条速览表 ＋ 自动抽取的品类/品牌线索（撰写②时以此为据，不靠记忆）。


#### 5.2.20 互动率健康度判据（含点赞/评论结构分解 · 2026-09-13 固化）

> **目的**：互动率不能只写"表现良好"——要给审核员**可说服的结构化判断**（多少、好不好、好在哪）。本节为 KOL 评估与对内审核表 PIC 结论的统一判据。

**① 指标定义（口径）**
| 指标 | 公式 | 说明 |
|---|---|---|
| 互动率 | Σ(点赞+评论) ÷ Σ播放 ×100 | 本角色既有 O 列口径（**不含分享/收藏**，与平台"互动"不完全等价） |
| 点赞率 | Σ点赞 ÷ Σ播放 ×100 | 轻互动强度 |
| 评论率 | Σ评论 ÷ Σ播放 ×100 | **讨论强度**（口碑沉淀信号） |
| 每千播放评论 | Σ评论 ÷ Σ播放 ×1000 | 便于跨量级对比 |
| 逐条中位互动率 | 各条视频互动率的中位数 | 防**大播放视频主导**加权值 |
数据源：公开视频清单（**有界全量池**：最近 12 个月 ∩ 最新 100 条，§5.2.18）；有 Analytics 授权的频道可用 `insight.stats.*.engagementRate` 交叉校验。

**② 双标定判据（绝对带 ＋ 池内分位）**
| 指标 | 弱 | 一般 | 良好 | 优秀 |
|---|---|---|---|---|
| 互动率 | <1% | 1–2% | 2–4% | >4% |
| 评论率 | <0.1% | 0.1–0.2% | >0.2% | >0.5% |
| 每千播放评论 | <1 | 1–2 | >2 | >5 |

**池内分位（30 频道实测 · 2026-09-13 · 随池更新）**：互动率 P25 0.42%｜中位 1.46%｜P75 2.55%（最高 7.6%）；评论率 P25 0.04%｜中位 0.09%｜P75 0.22%（最高 1.11%）；每千播放评论 P25 0.39｜中位 0.89｜P75 2.21（最高 11.09）。
→ **结论要给两层**：绝对带（业务直觉）＋ 池内相对位置（本轮标定）。

**③ 结构判断（点赞型 / 均衡型 / 讨论型）**
- **讨论型**：评论率 ≥ P75（0.22%）或 每千播放评论 ≥ P75（2.21）→ 评论区有真实讨论，适合需要口碑/反馈沉淀的产品；
- **均衡偏点赞型**：评论率在 中位–P75 之间；
- **点赞型（低讨论）**：评论率 < 中位（0.09%）→ 观众"爱看会点赞但不讨论"，曝光型价值高、口碑型价值弱。

**④ 表述规范（写进 PIC / D / I / J 与对客结论）**
1. 必须给「**数值 + 等级 + 结构**」三件套，禁止只写"互动率良好"；
   ✅ 正例：`互动率 2.8%（良好，池内中位–P75）｜点赞率 2.4%、评论率 0.13%、每千播放 1.3 条评论｜结构：均衡偏点赞型`
   ❌ 反例：`互动率 2.8%，表现良好（官方数据）`
2. **标注口径与来源**：公开数据（无 Analytics 授权）须注明"仅能用互动率近似，**无法看留存率/观看时长**"，不得暗示等同于平台后台口径；
3. **样本量纪律**：分类型指标 **n<5 不作类型结论**（例：TechMagnet 短视频仅 1 条 → "短视频均播 62.5k"不具参考价值，应标注或不引用）；
4. **加权＋逐条中位并给**：两者差异大时（如大播放视频主导）需说明以哪个为准；
5. **与出价联动**：互动率强 + CPM 合理 → 优先推进；CPM 便宜但互动弱（<1% 且评论率 <0.09%）→ 标"曝光便宜、转化/口碑弱"，避免只报 CPM。

**⑤ 工具**：`.kol-tools/engagement_profile.py --name "<频道名>"`（或 `--all --out 报告.md`）→ 输出整体/长/短视频三段互动率·点赞率·评论率·每千评论·等级·结构，并给出**可直接粘贴的结论文案**。


### 附录 5-A · §5 历史版本条目索引（**2026-09-16 已归档 · 移至 §5 末尾**）

> 原「§5 相关版本记录原文摘录（重建依据 · 未整理）」共 **34 行／13,415 字符**，已整体迁入 `docs/marketing/skills/_CHANGELOG-kol-intelligence.md`（按版本号可检索）。
> **§5 的重建已于 2026-09-16 完成**：§5.2.12 全量体检 ／ §5.2.13 数据可得性门控 ／ §5.2.14 分类型口径 ／ §5.2.15 Engage Rate 口径 四节已按版本记录原文 ＋ 现存脚本重建入正文。
> **仍真缺（无来源可考，不凭印象补写）**：① §5.1「垂直溢价档明细、服务商加成口径」；② §5.2.8「错题 1–55 逐条正文」——2026-09-13 事故**永久损失**，现存 56–69。


### 5.3 问价邮件（rates request · v0.9.174 重建 · 2026-09-30 · 证据来源＝仪器 `--kind quote` 判据 ＋ 已认可语料 `user-approved-rate-ask.txt`）

> **来源**：已认可语料 `.kol-tools/_fixtures/emails/user-approved-rate-ask.txt`（Tech Gear Talk 问价回信，
> 对方只给了微信号）＋ 仪器 `.kol-tools/check_email_tone.py` 的 `--kind quote` 档（`scan_quote`／`VAGUE_ASK`）＋
> 能力地图条目 `edm-quote-request`（2026-09-30 复核）。

**判据一句话**：**问价信只做一件事 —— 拿到可比较的报价，且不替对方做决定。**

| 段 | 做法 | 定版原文（节选） |
|---|---|---|
| 1 | 先接住对方的回复 | `Thanks for getting back to me, and glad this looks interesting on your side.` |
| 2 | **先要价格、渠道让给对方** | `We would like to get the rates confirmed first, and then we can continue there or wherever works best for you.` |
| 3 | **证据式赞美**（点名具体作品，证明真看过） | `Your recent XR and AI glasses coverage, including the XREAL AURA and inmo GO3 reviews, is the kind of work we had in mind for the Halliday G2.` |
| 4 | 复述**分档**问价清单 | `As in our first email, could you share your rates separately for:` ＋ 三档（1 长＋1 短／1 长／1 短） |
| 5 | 降低对方工作量 | `If you would rather start from your own packages, that works too.` |
| 6 | 收口 | `Looking forward to your rate.` |

**硬判据（仪器 `--kind quote`）**：`VAGUE_ASK`（12 条）拦"把要价写成模糊区间"（如 `What's your ballpark?`）——
问价必须让对方能给出**可比较的具体数**；`VAGUE_ASK_ALLOW`（显式豁免）用于"本信主题就是询区间价"的场景。
🔴 **边界**：**渠道听对方的**（微信／邮件都行），但**我方要的信息不放**（价格先确认）；
**三档必须分摊列出**，否则对方只回一个总额，后续无法比价。

### 5.4 砍价邮件（counter offer · v0.9.174 重建 · 2026-09-30 · 证据来源＝仪器 `scan_bargain` 判据 ＋ 已认可语料 `user-approved-bargain-warm.txt`）

> **来源**：已认可语料 `.kol-tools/_fixtures/emails/user-approved-bargain-warm.txt`（Tech It Easy 砍价回信）＋
> 仪器 `scan_bargain(text, phase)`（`BARGAIN_BANNED`／`BARGAIN_REQUIRED`，两阶段 `first`／`followup`）＋
> `_VOICE-PAIRS.md` 第 3.1 节与范例对 #14。

**判据一句话**：**砍价的三个动作 —— 限制归因"预算"而非"你不值"、报价与包件对齐、用非现金筹码补差。**

| 动作 | 定版原文（节选） |
|---|---|
| 先肯定对方 | `Thanks for your interest in working with us.` ／ `We really appreciate your enthusiasm` |
| **把限制归因预算** | `Regrettably, our current budget for this collaboration is a bit limited, and we were wondering if you could accept £1,010 for a dedicated YouTube video plus a YouTube Short and the 60-day access?`（🔴 2026-10-12 口径见下） |
| **非现金筹码补差** | `We will also send you a Halliday G2 unit to keep, worth $599.` |
| 留在可谈的句尾 | `Looking forward to hearing your thoughts, and we hope we can make this collaboration work!` |

**硬判据**：`BARGAIN_BANNED` 拦"贬低对方价值"类表述（说不值／太贵）；`BARGAIN_REQUIRED` 要求**同时**具备
「限制归因（预算）＋ 明确出价 ＋ 保留可谈余地」；两阶段区分 `first`（首次还价）与 `followup`（对方回价后再议）。
🔴 **边界**：**现金不让步时给实物/权益**（送机、加权益），而不是硬压价；出价必须**与交付包件一一对齐**，否则对方无法比较。

### 5.4.2 对方已回价后的再还价／待确认事项（round2）（2026-10-12 补建 · 教训 252 · CLS-13）

> 🔴 **本节为什么是“补回”**：能力地图与教训 122 一直引用 **§5.4.2**，但 2026-09-30 重建后**正文里没有这一节**（只存在于教训摘要）⇒ 导致 Able And His Table 第二轮砍价时我只能套 **首轮**骨架，写出“只谢回信、只说预算有限、报一个汇率精算出的怪数”的信，被用户人工重写。
> **定版语料**：`.kol-tools/_fixtures/emails/user-approved-bargain-round2.txt`（2026-10-12 用户人工定版）；同构早期语料：`user-approved-access-negotiation.txt`（2026-09-21，视频授权沟通）。

**判据一句话**：**第二轮不是重复首轮** —— 对方已让步，我方要回应那个让步，并把新要求包成“成交前要确认的一个点”。

**四段骨架**（与人工定版逐段对应）

| 段 | 做法 | 定版原文（节选） |
|---|---|---|
| 1 | **接住对方的让步与情绪**（第二轮最重要的动作；只谢“回信”不算） | `Thanks for working with us on this. We really appreciate your flexibility, and we're glad to hear you're excited about the Halliday G2 launch.` |
| 2 | **内部再讨论后的报价**；**非现金筹码嵌进包件句** | `We discussed this further with the team and wanted to see if you'd be open to £2,100 for one dedicated YouTube video, one YouTube Short, and 30-day licensing rights, with the Halliday G2 unit for you to keep.` |
| 3 | **待确认事项：定位成“成交前要确认的一个点”→给内容效果层面的理由→问法具体** | `There's also one small content point we'd like to confirm before moving forward. … Since Halliday G2 is a wearable product, it would be really helpful for viewers to see how the glasses actually look and fit when worn. Would you be comfortable including some on-camera shots showing your face while wearing and using the glasses?` |
| 4 | **单一收口句覆盖全部待确认项** | `Please let me know if this could work for you.` |

**四条硬纪律**
1. 🔴 **归因从“预算有限”换成“内部又讨论了一次”**：“因素”是首轮动作（§5.4），第二轮再讲就变成“我们没钱”；改成“我们为你又争取了一次”。
2. 🔴 **出价给人类整数，不把汇率精算写进信**；**赠品不标价**（写 `with the … unit for you to keep` 而不写 `worth $599`）——单列赠品像补偿，标价反而把“这 599 可以折”的口子给了对方。
3. 🔴 **提要求必须给“内容效果”层面的理由，不用“随你方便”自我削弱**（`Happy to work around whatever you're comfortable with.` 类句子等于替对方说“不做也行”）。
4. 🔴 **一个回复点**：价格与待确认事项收在**同一句**里（不要两个收口）。

**边界（与 §4.13.2 不冲突）**：“承认对方让步／情绪”只适用于**继续谈**的信；**收口不推进**的信里承认对方条款才是“给下一轮留口”（§4.13.2 边界 ④）。

**仪器**：`check_email_tone.py --kind bargain --bargain-phase round2`（必备件：接住让步的开场／具体金额／单一收口句；人工定版作为真阴性回归，我旧版作为正控）。

### 5.4.3 问句的「中文读法」纪律（英文写法不限）（2026-10-12 用户口径 · 教训 250 · CLS-13）

> **用户原话**：「**不是支付啊，是是否愿意接受**」。
> **当日事故与撤销（必读）**：我先把 `be open to £X` 列为禁语并改了已认可语料；但**用户同日给出的人工定版里写的就是** `wanted to see if **you'd be open to** £2,100 for …` ⇒ 该禁语会把定版判死（实测：**人工版退出码 1、我的旧版退出码 0** —— 判据与真源相反）。**当日撤销禁语、还原语料**，并把判据改为下面这条。

**判据一句话**：**英文怎么写不限**（`could you accept £X`／`would you be able to accept £X`／`you'd be open to £X`／`would you be open to £X` 均可），**但这句话翻成中文必须是「是否愿意接受这个价」**，不能读成「是否愿意**支付**」（钱是我方出、对方是收款方，主语不能反）。

**为什么不能用“禁英文句式”来解这个问题**：中文读法取决于**整句语序与上下文**，而不是某个固定短语。受控的做法是：① 让句子里出现**接受动作的主体与客体**（`you'+u '… accept £X`）；② 或把价格与包件写在同一句（`… £X for one dedicated video, one Short, and 30-day licensing rights`），读起来就是“这个包件这个价”；③ 收口用 `Please let me know if this could work for you.`（不带任何金额）。

**仪器**：`ask_accept` 认可写法包含 `accept` 系与 `be open to` 系（多句序）；旧的“拦 `be open to £X`”已撤销，对应自检控制从**正控改为真阴性**（自检 253/253 → **257/257**）。

### 5.5 对方回传条款后的处置（terms response · v0.9.174 重建 · 2026-09-30 · 证据来源＝章程 §7.66／§7.67 ＋ 已认可语料 `user-approved-contract-negotiation.txt`）

> **来源**：已认可语料 `.kol-tools/_fixtures/emails/user-approved-contract-negotiation.txt`（对方对 16 处条款提出修改后的回信）＋
> `…-contract-final-send.txt`（发最终合同 ＋ 要地址）＋ 章程 §7.66／§7.67 ＋ Skill §4.22 B（terms／contract 两档）＋
> `_VOICE-PAIRS.md` 范例对 #15。

**判据一句话**：**先给"我们接受了什么"，再谈"剩下几处"，不可让的给内部原因＋共情。**

| 段 | 做法 | 定版原文（节选） |
|---|---|---|
| 1 | **接受总述**（让对方确认哪些已被采纳） | `We've gone through everything with our team, and we're happy to accommodate most of your requests, including the payment schedule, production timeline, music licensing, YouTube reposting restrictions, likeness protections, and liability cap.` |
| 2 | 收窄剩余分歧 ＋ 共情 | `We really appreciate the time and effort that goes into your content, and there are just a few final details we'd love to align on…` |
| 3 | 不可让项 → **内部原因 ＋ 理解对方处境** | `we're required to retain the existing provisions under our company's internal contractual requirements` ＋ `we understand that Hong Kong jurisdiction isn't ideal for you as a UK-based creator, and we really appreciate your understanding here.` |
| 4 | 收口（把球踢回对方且不施压） | `Everything else looks good to us!` ／ `Thanks again for your patience and flexibility, Alex.` |
| 5 | 达成后：发最终合同 ＋ 要签署与地址 | `Thank you for confirming everything on the agreement — the final version is attached. Could you please sign it when you have a moment?` ＋ 五项地址信息清单 |

**硬判据（`--kind terms`／`--kind contract`）**：`no_stage_summary`（缺"接受了什么"的总述）／
`no_next_action`（缺明确下一步）／`no_flexibility_language`（缺让步与共情语气）。
🔴 **边界**：**对方的每条修改意见都要有对应答复**（不遗漏、不合并含糊过去）；
**不可让的条款要给"内部原因"**（公司合规要求），而不是"我们不同意"；
**收口用** `Everything else looks good to us!` 这类"其余都同意"的表述，避免让对方以为又要重谈。

---

> ⟦重建说明⟧ 本节三节（§5.3／§5.4／§5.5）在蓝图中被判"基线缺失但被能力地图引用"，重建时被漏派 ⇒
> 由总监按 **仪器判据原文＋已认可语料＋章程同源条款** 补建（证据等级：强，非逐字）。
> 定版原文一律取自 `.kol-tools/_fixtures/emails/`，未改写。

