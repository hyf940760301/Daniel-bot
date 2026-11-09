# 阶段 0 · 语义层基础 · 草案（业务字典 ＋ 操作手册）

> 状态：**草案（DRAFT）· 未定稿 · 未改任何代码 · 未动飞书 · 未改 v0.4**
> 日期：2026-11-08 ｜ 执行：管线 A ｜ 待确认对象：Jack
> 落点：`daniel-bot/specs/PHASE0-ONTOLOGY-DRAFT.md`（本文件是本次唯一产出）
> **2026-11-08 追记**：本文的工具数是草案期的 **19**；定稿已归一为 **20**（`daniel_open_research_commit` 计入，`baseline.json` 已同步），以 `PHASE0-ONTOLOGY-FINAL.md` §1.4／§4.0 为准。
>
> **这份文件只做一件事**：把「概念/指标怎么定」和「能力怎么用、什么时候必须停」写成可逐条核对的草案，
> 交给 Jack 逐项拍板。**它不实现、不落库、不改母本、不改契约。**

---

## 0. 怎么读这份草案

### 0.1 依据（三类，全部实读）

| 类 | 文件 | 本文用到它回答什么 |
|---|---|---|
| 任务书 | `Daniel-Bot-营销助手定位与迭代方案 (3).md` 第四章 4.1–4.7／第五章／第八章 | 语义层的定位、三部分构成（字典／手册／规章）、四条硬规则（可校验·可复现·可拒绝·不新增工具）、人工确认节点 |
| 设计稿 | `daniel-bot/docs/versions/03-语义层设计方案-v0.4.md`（500 行） | P0 范围（10 指标 ＋ 5 概念）、五类对象、`取值面` 的设计理由、7 条已确认的拍板（末尾追加／索引放 corpus／追问键／两档模型／总监代签／段三硬门／产品文档补第三项） |
| 冷启动素材 | 见 §0.6 盘点表（workflow-map／guide／6 份契约／94 工序／`normalize.js`／`kol-*` skills／`voc-intelligence.md`） | 概念的值域、指标的实现位置、能力的前置与门禁，**不许凭印象写** |

### 0.2 本文要交的三样东西

1. **业务字典**：5 个概念 ＋ 10 个指标，每个都带「出处可核」的字段与实现位置（第一部分）。
2. **操作手册**：8 个 P0 能力的输入／输出／前置／门禁／失败形态／是否写操作（第二部分）。
3. **待确认清单**：本文无法自证、必须 Jack 拍板的点，每条给方案、建议与影响面（第三部分）。

### 0.3 本文不做什么（硬边界）

- 不写实现方案、不写排期、不改 `lib/normalize.js`、不改 `contracts/*.json`、不改母本附录 B。
- 不新增工具、不新增语料束、不新增 MCP server、不新增常驻进程（沿用产品文档 §4.6 与 v0.4 §3.2）。
- 不把「建议」写成「已定」：凡本文出现 `【待确认】`，一律是**未定**项，不得被下游当成口径引用。

### 0.4 标注约定（三种，全文一致）

**① 出处写法**

| 写法 | 含义 | 例 |
|---|---|---|
| `路径:行号` | 该行逐字可核 | `daniel-bot/packages/0.11.0/lib/normalize.js:199` |
| `路径#字段` | 该 JSON 键路径逐字可核 | `contracts/kol-list.json#交付件schema.列` |
| `命令` | 该命令在 `schema.py` 里声明过 | `daniel brands list --workspace 90002` |

> 路径一律相对仓库根 `/Users/huyifan/Desktop/DeepSeek Harness`。
> **凡写不出上述三种之一的，本文一律写「【待确认】」，不编。**

**② `data_status` 三值（任务书要求的词表）**

| 值 | 含义 | 交付件里的写法 |
|---|---|---|
| `reliable` | 口径与实现一致、样本条件写死、可复算 | 可作判断依据，仍需带窗口与样本 N |
| `unreliable` | 口径存在但会系统性误导（均值分摊、单位两套、分母可换面） | **不得单独作对外结论**；必须标口径，或换 `替代口径` |
| `unknown` | 库内找不到逐字口径／实现，或分母未声明 | 只能说「按 XX 口径读到 X」，不得说「X 就是答案」 |

> 已上线版本（`12-ontology-registry.md`）用的是另一套词：`unstable_when_small_sample`／`reliable_when_sample_ok`。
> 两套词的映射与取舍见 **Q-12**；本文按任务书词表写，映射表在 §1.19。

**③ `取值面`（surface）六值**

| 值 | 指什么 | 为什么必须单列 |
|---|---|---|
| `api_field` | 平台接口直接返回的字段 | 同一名字在不同接口可能是不同算法 |
| `detail_drawer` | 与 Daniel 详情抽屉同口径的现算值 | 抽屉是「视频列表现算」，不是读字段 |
| `pipeline_v2` | 名单产线（有界全量池）口径 | 与抽屉的窗口/样本不同 |
| `list_item` | 名单条目字段 | 单位与接口层不同（百分数 vs 小数） |
| `manual_formula` | 语料里写死的公式（无代码） | 算得出但依赖人选面 |
| `outreach_system` | 建联系统（Nox）报表/状态 | 分母有三个并存口径 |

### 0.5 开工前必须知道：仓库现状与本任务书的三处出入

> 这三处不是我判断出来的「建议」，是**仓库里能跑出来的事实**，直接决定后面怎么写。

| # | 任务书／v0.4 的说法 | 仓库实测 | 本文怎么处理 |
|---|---|---|---|
| ① | v0.4 说「语义登记表尚未存在，要新建附录 B」；P0 要「10 指标 ＋ 5 概念」 | **已经存在一版并已随包分发**：`mcp/corpus/kol-intelligence/references/12-ontology-registry.md`（273 行）、`mcp/corpus/_ONTOLOGY.json`、`daniel_cli/ontology.py`（243 行）。但形态是 `surfaces.{reported,median}` ＋ 4 条登记项（1 metric ＋ 2 criterion ＋ 1 expression），**没有 concept 类型**，也**没有 `取值面` 这个词** | 本文按任务书要求写 `取值面`，但**每个取值面都标注它对应已上线 `surfaces` 的哪个键**（§1.18）；是否改已上线形态 = **Q-01**（最高优先） |
| ② | v0.4 约束「P0 工具数保持 14」 | `registeredCount: 19`（`daniel-bot/packages/0.11.0/tests/golden/baseline.json`），`lib/index.js` 注册 19 个 `daniel_*` | 本文按 19 写能力与工具名；14→19 的差额（新增 6 个、退役 1 个）列为 **Q-09** |
| ③ | v0.4 记「8 束 / 40 文件 / 24 切片 / 语料 0.9.204 / 母本 6,894 行」 | `_MANIFEST.json`：`0.9.206 / 8 束 / 41 文件 / 25 切片`；母本 7,164 行（附录 B 已追加为 L6895–L7164） | 全文引用一律用 0.11.0 实测值；0.9.204 那批数字不再引用 |

**另有两处「已经变了、但文档还没跟上」，会影响执行，先点名：**

| # | 事实 | 影响 | 处置 |
|---|---|---|---|
| ④ | **官方库检索通道已退役**：`lib/index.js:915` 起 `daniel_roster_search` 只回 `channel_retired`、**一次网络请求都不发**（注释逐字：「YouTube 官方库 2026-09-14 起 503、09-16 起读超时，已裁决不再使用」） | 但本会话的工具说明仍写「在 YouTube 官方库里找红人就用这个工具」⇒ 模型会去调一个死通道 | 操作手册把「不得调用」写成硬门（§2.1 G5），并列为 **Q-02**（工具说明与代码不一致） |
| ⑤ | **追问闸已下沉**：`lib/clarify.js` 只剩 53 行薄适配（只做 argv 组装与透传），28 条字段定义在 `mcp/corpus/.../12-ontology-registry.md` 的 `criterion.clarify.param_gate`（4 场景），触发词在 `daniel_cli/data/clarify_triggers.json` | v0.4 第 3 条拍板「追问键 P0 手抄白名单 ＋ 断言」的技术前提已不存在（不再有 JS 侧 `DIMS`） | 操作手册引用登记项 id 而不是手抄键表；**Q-01** 一并决定 |

### 0.6 现状盘点表（本文引用到的、逐条实读过的资产）

| # | 资产 | 路径（相对仓库根） | 实测 | 本文用它做什么 |
|---|---|---|---|---|
| 1 | 命令地图 | `daniel-bot/app/workflow-map.json` | `entries: 91`，23 个 module，字段 `id/module/action/fields/mcpTool` | 能力的命令面与输出字段清单 |
| 2 | 功能地图 | `daniel-bot/app/guide/daniel-guide.json` | 9 个 module / 31 个 function（3+4+3+4+2+4+3+4+4） | P0 能力的业务命名与例句 |
| 3 | 契约（6 份） | `daniel-bot/packages/0.11.0/vendor/data/daniel-cli/contracts/*.json` | `high-performance-video-list`、`-live`、`kol-list`、`real-brands-inventory`、`script-review`、`search-terms-check`；八字段齐 | 概念/指标与契约字段的对照（§1.20） |
| 4 | 工序表 | `.../daniel_cli/intake/processes.json` | 8 域 / 94 工序（12/14/5/14/11/11/14/13），每条带 `前置条件[]`／`产出交付件`／`工序键` | 能力的前置条件与工序键 |
| 5 | 均播实现 | `daniel-bot/packages/0.11.0/lib/normalize.js` | 1029 行；`median()` L188／`scopeOf()` L199／`performanceFromVideos()` L217／`performanceBlock()` L232 | 均播三面的实现位置与 `data_status` |
| 6 | 插件工具面 | `.../lib/index.js` | 1420 行；19 个 `ctx.tools.register` | 能力对应的工具名与入参 |
| 7 | 工具基线 | `.../tests/golden/baseline.json` | `registeredCount: 19` | 工具数口径 |
| 8 | 语料清单 | `.../mcp/corpus/_MANIFEST.json` | `corpus_version=0.9.206`／8 束／41 文件／25 切片／`source_lines=7164` | 语料版本与切片口径 |
| 9 | 已上线登记表 | `.../mcp/corpus/kol-intelligence/references/12-ontology-registry.md` | 273 行；4 条登记项（`metric.creator.avg_views_long`／`criterion.creator.screen`／`expr.kol_list`／`criterion.clarify.param_gate`） | 与本文形态的对应关系（§0.5①、§1.18） |
| 10 | 登记表索引 | `.../mcp/corpus/_ONTOLOGY.json` | `kind/corpus_version/entry_count/entries`，`corpus_version=0.9.206` | 索引结构与版本链 |
| 11 | 登记表实现 | `.../daniel_cli/ontology.py` | 243 行；`_IDREF_RX` L33；只抽索引＋展开正文，**不定义任何业务口径**（头注释 L6–L10） | 「本文不定义口径、只登记指针」的既有先例 |
| 12 | 字段字典 | `docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md` | 622 行；规范字段名（`avg_views_vod_28d`／`avg_views_pool_median`／`engagement_rate`…）与 6 类陷阱 | 概念字段与单位陷阱的主要出处 |
| 13 | 母本 | `docs/marketing/skills/kol-intelligence.md` | 7,164 行；L31／L65／L552／L674／L683／L724／L4126 等逐条核过 | 指标口径与教训的依据 |
| 14 | 能力 Skill | `.agents/skills/kol-{intelligence,discovery,screening,outreach,negotiation,contract,daniel-api,execution-sov}/SKILL.md` | 8 束；`kol-negotiation` L41–48／L60（CPM）、`kol-execution-sov` L87–104（SOV） | 手册的判据与话术边界 |
| 15 | 建联 Skill | `.agents/skills/nox-{cli,outreach-data,daily,weekly,workflow}/SKILL.md` | `nox-cli` 197 行（9 条命令）、`nox-weekly` L73／L191（回复率） | 建联取数能力的命令与口径 |
| 16 | VOC Skill | `docs/marketing/skills/voc-intelligence.md`（124 行）＋ `.agents/skills/voc-report/SKILL.md`（284 行）＋ `tools/voc-crawler/STATUS.md` | 三层能力地图、10 条数据红线、G1–G9 门禁 | VOC 分析能力的门禁 |

---

# 第一部分 · 业务字典

## 1.0 概念与指标的分工（先定边界，避免重复登记）

| 类 | 回答什么 | 判定问题 | 例子 |
|---|---|---|---|
| **概念 concept** | 「这个词指的是哪个实体」 | 能不能被**指向**（有唯一标识）？ | 品牌、频道、名单 |
| **指标 metric** | 「这个数怎么算出来、在哪个面算的」 | 能不能被**计算**（有分子分母/窗口）？ | 均播、互动率、CPM |

一条判例：`订阅数` 是指标（可算、有快照时点），`频道` 是概念（有 `channelId`）。
把两者混在一张表里，就会出现「名单里的人数到底算概念还是算指标」这类无解争论（见 Q-20）。

---

## 1.1 概念总表（5 个，P0）

| id | 中文名 | 一句话定义 | 唯一标识 | 数据落点 | 维护人 |
|---|---|---|---|---|---|
| `concept.brand` | 品牌 | Daniel 里可被检索、可挂名单与提及任务的品牌实体 | `brandId`（整数） | Daniel（Brands 区块） | 业务（品牌方/我方运营）建档；agent 只走写链 |
| `concept.product` | 型号／产品 | 品牌下的具体产品型号（SKU），是「提及检索」与「报价分母」的粒度 | **无实体 id**（以型号名/检索词存在） | Daniel 无独立实体（只体现为任务与词表） | 业务给型号名；agent 不建型号 |
| `concept.channel` | 渠道 | 取数与触达的**平台**（YouTube／Reddit／众筹／论坛／邮件） | 平台枚举值 | Daniel 只覆盖 YouTube；VOC 覆盖其余；Nox 覆盖邮件 | 平台状态：`STATUS.md`；Daniel 通道：`route catalog` |
| `concept.creator` | 红人／频道 | 一个 YouTube 频道（红人是频道的人化称呼） | `channelId`（`UC…`） | Daniel（Discovery / Lists / Mentions） | 平台；我方只在名单里加人 |
| `concept.list` | 名单 | 某品牌下的红人集合（Saved List） | `listId`（整数） | Daniel（Lists 区块） | 业务；agent 写链可建/改名/删 |

> 5 个概念的**共同约束**：都必须能回答「在哪个品牌、哪个工作区下」。
> 跨工作区混用是本仓历史上反复出现的错（`brands list` 只返回当前工作区，见 `references/60-data-layer.md:238`）。

---

## 1.2 `concept.brand` 品牌

**id**：`concept.brand`
**中文名**：品牌
**定义**：Daniel 里的品牌实体 —— 一个品牌档案＝品牌编号 ＋ 名称 ＋ 所属工作区 ＋ 品类 ＋ 目标市场 ＋ 行业关键词 ＋ 样品价 ＋ 竞品。它是检索口径、背调依据、提及任务、声量统计的**共同事实源**（`app/workflow-map.json` 的 `workflowReason` 逐字：「品牌档案是检索口径、背调、产品说明共用的事实源」）。

**合法值域**

| 维度 | 值域 | 依据 |
|---|---|---|
| 标识 | `brandId` 为整数（实测 `3690002` ＝ Halliday） | `contracts/real-brands-inventory.json#交付件schema.列`（`id`/`name`/`workspaceId`/`workspaceName` 四列） |
| 名称 | 非空字符串；**允许同名** | `references/60-data-layer.md:238`（服务端不拦空名/重名） |
| 工作区 | 必须归属一个 `workspaceId` | 同上 |
| 目标市场 | ISO 国家码数组（实测 `[US, CA, GB]`） | 字段字典 §6.7 L376 |
| 样品价 | `sampleCost` 整数（**不是零售价**） | 字段字典 §6.7 L379–381 |
| 竞品 | 品牌自己配置的竞对名单（**唯一权威**） | `references/60-data-layer.md:360`；`processes.json#daniel-api-03` 前置条件 |

**与 Daniel 字段的对应**

| 用法 | 命令／接口 | 字段 |
|---|---|---|
| 列品牌 | `daniel brands list [--workspace] [--limit]` | 品牌编号／品牌名／所属工作区编号与名称（`schema.py` 的 `returns` 逐字） |
| 看档案 | `daniel brands show --brand <品牌>` | 简介／频道／竞品／目标市场／品类／行业关键词／样品价 |
| 看竞品 | `daniel brands competitors --brand <品牌>` | 竞品名 ＋ 每个竞品对应的品类关键词 |
| 建/改/克隆/删 | `brands create`／`update`／`clone`／`delete`（均 `write=True`，`writeStage=live`） | 写链结果：干跑计划／改动前后对照／回读结论／审计落点 |

**谁维护**：业务方在 Daniel 网页端建档为主；agent 侧只允许走 `daniel_write_plan → daniel_write_commit`（产品文档 §3.5、§5.4）。**agent 不得代用户决定建档**。

**已知坑（三条，逐条有实测）**

1. **`brands list` 的取数范围有两种说法，未实测前不得当定论**：旧记录写「只返回当前工作区」（`references/60-data-layer.md:238`，2026-10-10），而当前 CLI 的 `returns` 写「账号可见的全部品牌（跨工作区）」（`schema.py#brands.list.returns`）。**两种说法直接决定"会不会漏项"**，必须先实测一次（见 N-7），期间一律逐条核对工作区编号。
2. 同名品牌可能分布在多个工作区 ⇒ **必须让用户给品牌编号，不猜**（`processes.json#daniel-api-03` 前置条件逐字：「同名品牌出现在多个工作区时要用户给品牌编号，不猜」）。
3. `sampleCost` 是**样品计价**，对外只能写 "a $599 product"／"valued at $599"，不能写「零售价」（字段字典 §6.7 L379–380）。

**出处**：`contracts/real-brands-inventory.json:5–20`；`app/workflow-map.json#entries[brands.*]`；`references/60-data-layer.md:236–238、246–247`；`schema.py#brands.list.returns`；`docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md:360–381`。

---

## 1.3 `concept.product` 型号／产品

**id**：`concept.product`
**中文名**：型号／产品（SKU）
**定义**：品牌下的具体产品型号。它在本仓里**不是一个实体**，而是三样东西的合称：
① 品牌提及的**检索单元**（品牌名任务 vs SKU 词任务）；
② 报价分母的**形式依据**（1 长／1 短／1 长+1 短，见 §1.14）；
③ 产品说明块的**事实来源**（参数只写有出处的）。

**合法值域**

| 维度 | 值域 | 依据 |
|---|---|---|
| 型号名 | 自由文本（如 `Halliday G2`、`Halliday AI glasses`），来自任务配置的 `skuTerms` | `references/60-data-layer.md:387` |
| 任务模式 | `brand`（品牌名任务）／`sku`（型号词任务） | `references/60-data-layer.md:387`；契约里的 `任务模式` 列（`high-performance-video-list.json#交付件schema.列`） |
| 型号集合 | **品牌池 ＝ 品牌名任务 ＋ 其 SKU 词任务合并后按 `videoId` 去重** | `references/60-data-layer.md:456` |

**与 Daniel 字段的对应**

| 用法 | 命令／接口 | 字段 | 现状 |
|---|---|---|---|
| 发起提及任务 | `daniel mentions run --brand <品牌> --days <天数> --max-videos <条数>` | 只有品牌、窗口、条数三个入参 | **没有型号入参**（`schema.py` 的 `mentions.run.options` 逐字） |
| 看任务 | `daniel mentions jobs --brand <品牌>` | 任务编号／状态／分析时间范围／视频数 | 型号只体现在任务名里 |
| 型号词 | 无独立读写命令 | `skuTerms`（任务配置内） | **不可由 CLI 直接改** |

**谁维护**：业务方在 Daniel 网页端建任务时给型号词；agent 只读不改。**本文不给 agent 授权建型号。**

**已知坑（两条，直接影响判定对错）**

1. **SKU 任务的相关性按品类判，不等于点名品牌**。原话：「`searchMode="sku"` 任务的相关性**按品类判定**，不是按品牌 ⇒ SKU 任务的 `relevanceLabel ∈ {confirmed, likely}` 只说明『视频属于该品类』，不等于『点名了该品牌』」（`references/60-data-layer.md:387–390`）。
2. 只跑一个池子是残的（品牌名任务或 SKU 任务单独看都会漏），合并后才是界面数（`references/60-data-layer.md:456`）。

**状态**：`data_status: unknown` —— 因为**没有实体字段可核**，型号的边界（哪几个词算同一型号）目前只能靠任务配置与人工判断。
**【待确认】Q-07**：型号要不要在语义层里作为概念登记，还是只登记为「任务模式」枚举。

**出处**：`references/60-data-layer.md:383–390、456`；`contracts/kol-list.json`（交付件不含型号列）；`schema.py#mentions.run`。

---

## 1.4 `concept.channel` 渠道

**id**：`concept.channel`
**中文名**：渠道
**定义**：**取数与触达的平台**。本仓的「渠道」只指平台，不指销售渠道、不指品牌自己的 YouTube 频道。
这一定义是本文指定的（不是仓库原文），因为仓库里「频道」一词同时被用于两件事（见下方「坑 1」）——**【待确认】Q-08**。

**合法值域（6 个值，逐个有出处）**

| 值 | 承载能力 | 取数入口 | 出处 |
|---|---|---|---|
| `youtube` | 检索／档案／提及／声量／真实性／合作追踪 | Daniel CLI（`search`/`mentions`/`sov`/`ct`/`authenticity`） | `schema.py#REQUIRED_MODULES` |
| `reddit` | VOC | `tools/ks-comments-crawler/platform-reddit.mjs` | `tools/voc-crawler/STATUS.md`（Reddit 行） |
| `kickstarter` | VOC | `crawl-ks.mjs` / `crawl-full-ks-cdp.mjs` | 同上（Kickstarter 行） |
| `avsforum` | VOC | `platform-avsforum.mjs` / `avs-find-threads.mjs` | 同上（AVS 行） |
| `rv_forum` | VOC | 见 `voc-crawl-rv.md` | `docs/marketing/skills/voc-intelligence.md:22、47` |
| `nox_email` | 建联（邮件） | `noxinfluencer email …` | `.agents/skills/nox-cli/SKILL.md:41–49` |

**与 Daniel 字段的对应**

| 需求 | 事实 | 出处 |
|---|---|---|
| Daniel 里有没有「渠道」字段 | **没有**。Daniel 的所有业务模块都只覆盖 YouTube | `schema.py#REQUIRED_MODULES`（12 个模块全部是 YouTube 数据面）；`mcp/corpus/kol-daniel-api/references/60-data-layer.md` 全文 |
| 品牌档案里的「频道」是什么 | 是**品牌自己的 YouTube 频道**（`youtubeChannelId`），不是「渠道」 | `lib/normalize.js:341`（`youtubeChannelId: '频道编号'`）；`processes.json#daniel-api-03` 前置条件 |
| 平台可用状态看哪 | `tools/voc-crawler/STATUS.md`（单一真源，禁止现场调试） | `docs/marketing/skills/voc-intelligence.md:6、96` |

**谁维护**：平台状态 → VOC 侧（STATUS.md，改状态必须回写日期）；Daniel 通道 → `daniel route catalog`（`route.catalog` 的 `returns`：通路名／请求动词／说明／默认入参）。

**已知坑**

1. **「频道」一词在本仓有两个含义**：`concept.channel`（平台）与「品牌频道」（品牌自己的 YT 频道）。写交付件时说「频道」必须带限定（「渠道＝平台」/「品牌频道」）——**【待确认】Q-08**。
2. **同一平台有多种取数路径，口径不同**：VOC 的 Reddit 走浏览器、YouTube 评论区走 CDP 登录态；`web_search` 只能发现候选，**不得当覆盖完成的证据**（`voc-intelligence.md:68`）。
3. **官方库通道（YouTube Official）已退役**，不属于可用渠道（见 §0.5④）。

**出处**：`tools/voc-crawler/STATUS.md`（平台矩阵）；`docs/marketing/skills/voc-intelligence.md:33–47、64–75`；`.agents/skills/nox-cli/SKILL.md:44–62`。

---

## 1.5 `concept.creator` 红人／频道

**id**：`concept.creator`
**中文名**：红人／频道
**定义**：一个 YouTube 频道。「红人」是业务称呼，「频道」是数据单位；**唯一键是 `channelId`**，`@handle` 只是可读别名（且可为空）。
边界：一个频道不等于一个红人（同一人可能多频道）；合作主体以**频道**计，不以人计（`contracts/kol-list.json` 的必填列是「频道名称／频道链接」）。

**合法值域**

| 维度 | 值域 | 依据 |
|---|---|---|
| `channelId` | `UC` 开头的字符串（唯一键） | 字段字典 §11.1 L460 |
| `handle` | `@xxx`，**可为 null** | 字段字典 §6.1 L202 |
| `title` | 官方 title 全文（不截断、不改写） | 字段字典 §11.1 L461 |
| `channel_url` | `https://www.youtube.com/channel/{cid}`（由 cid 拼） | 字段字典 §11.1 L463 |
| `country` | 频道**所在地**，≠ 受众国家 | 字段字典 §四 L137、§11.2 L470 |
| `subscribers` | 整数快照（会滚动） | 字段字典 §11.2 L469 |

**与 Daniel 字段的对应**

| 用法 | 命令／工具 | 字段 |
|---|---|---|
| 一次拿全 | `daniel_kol_profile(handle, videos)` | 频道／表现_近28天／受众／近期视频 ＋ 未取到／平台未收录／替代信号 |
| 名单侧字段 | `daniel lists items --list-id <编号> [--with-handle]` | 频道编号／频道名／订阅数／质量分／互动率／标签 |
| 解析 handle | `daniel ct resolve-channel` | 频道编号／是否成功 |
| 真实性 | `daniel authenticity channel --channel <链接或 @handle>` | 频道名／订阅数／样本视频数／总分／信号判定 |

**谁维护**：平台（只读）；我方只能在名单里加人（而**加人目前没有 CLI 命令**，见 §2.4 与 **Q-06**）。

**已知坑**

1. `handle` 可为 null ⇒ 交付件不能只有 handle 一列，必须有 `channelId`（字段字典 §6.1 L202）。
2. **两套视频投影字段名不同**（`views/publishTime` vs `viewCount/publishedAt`），混用会静默取到 `None`（字段字典 §五 L146–156）。
3. 官方号/媒体机构号要识别（六信号），否则会把品牌自己的号当成红人（`processes.json#discovery-09` 前置条件）。

**出处**：`docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md:130–171、457–465`；`lib/index.js:882`（`kol_profile` 四块）。

---

## 1.6 `concept.list` 名单

**id**：`concept.list`
**中文名**：名单（Saved List）
**定义**：挂在某品牌下的红人集合，有 `listId`、名称、条目数；一条条目＝一个 `channelId`。
边界：名单**属于品牌**（`lists by-brand --brand`），不属于账号；同一频道可出现在多份名单里。

**合法值域**

| 维度 | 值域 | 依据 |
|---|---|---|
| `listId` | 整数（实测 `6120001` 等） | 字段字典 §十二 L524–537 |
| 归属 | 必须属于一个 `brandId` | `schema.py#lists.create` 必填 `--brand` |
| 条目数 | ≥0；与页面人数可能不一致，**以读到的条目为准并标注** | `processes.json#daniel-api-01` 前置条件 |
| 名单名 | 非空字符串；**允许同名** | `schema.py#lists.rename` |

**与 Daniel 字段的对应**

| 用法 | 命令 | 字段 |
|---|---|---|
| 有哪些名单 | `daniel lists by-brand --brand <品牌>` | 名单编号／名单名／条目数 |
| 名单里的人 | `daniel lists items --list-id <编号> [--limit 50] [--offset]` | 频道编号／频道名／订阅数／质量分／互动率／标签 |
| 去重前查已保存 | `daniel lists saved-channel-ids --brand <品牌>` | 频道编号条数与清单 |
| 分享状态 | `daniel lists share-status --list-id <编号>` | 是否开启分享／分享码／分享时间 |
| 自动优先级 | `daniel lists auto-priority-status --list-id <编号>` | 状态／进度百分比／完成时间／最近更新 |

**谁维护**：业务；agent 写链可 `create`/`rename`/`delete`（均 `write=True`，删除还需 `--delete-token`）。

**已知坑**

1. **加人没有 CLI 命令**：`lists` 只有 by-brand/items/saved-channel-ids/share-status/auto-priority-status/create/rename/delete —— 产品文档 §3.2 承诺的「把清单导入到你 Daniel 下某个 Brand 的 list 里」**当前无命令可执行**（**Q-06**）。
2. 人数口径：读到条目数与页面人数对不上时，**以读到的成员为准并如实标注**（`processes.json#daniel-api-01`）。
3. 删除是不可逆动作：`--delete-token` 要求把目标名原样再写一遍（`schema.py` 头注释 L26–28）。

**出处**：`schema.py#lists.*`；`processes.json#daniel-api-01、daniel-api-02`；`docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md:520–537`。

---

## 1.7 指标总表（10 个，P0）

> 「均播」不给唯一权威值 —— 三个取值面各登记一条（理由见 §1.19）。

| # | id | 名称 | 取值面 | `data_status` | 一句话定义 | 实现位置 |
|---|---|---|---|---|---|---|
| M1 | `metric.creator.avg_views.reported` | 均播（接口直读） | `api_field` | unreliable | 窗口内总播放 ÷ 窗口内视频数（均值） | `lib/normalize.js:232` |
| M2 | `metric.creator.avg_views.drawer` | 均播（详情抽屉） | `detail_drawer` | reliable | 长/短视频播放量**中位数**，28 天窗 | `lib/normalize.js:199/217` |
| M3 | `metric.creator.avg_views.pool` | 均播（名单产线） | `pipeline_v2` | reliable（有条件） | 有界全量池内 VOD 播放量中位数 | 无代码（母本 L724） |
| M4 | `metric.creator.avg_views.package` | 均播（按成交形式） | `manual_formula` | unknown | 1长/1短/1长+1短 取值，CPM 的分母 N | 无代码（母本 L683） |
| M5 | `metric.creator.subscribers` | 订阅数 | `api_field` | reliable | 订阅数快照（整数，不压缩） | `lib/worker.py:210` |
| M6 | `metric.creator.engagement_rate` | 互动率 | `api_field` | unreliable | (Σ赞+Σ评)/Σ播放，同批样本 | `lib/normalize.js:211` |
| M7 | `metric.quote.cpm` | CPM | `manual_formula` | unreliable | 报价 ÷ N × 1000 | 无代码（母本 L3220–3227） |
| M8 | `metric.sov.platform_share` | 声量份额（平台） | `api_field` | unknown | 平台返回的 `share`（百分比 1 位） | `.kol-tools/daniel_sov.py:226` |
| M9 | `metric.sov.mention_share` | 声量份额（提及份额） | `manual_formula` | reliable（有条件） | 品牌提及 ÷（自身+竞争集）提及 | 无代码（`kol-execution-sov` L97） |
| M10 | `metric.outreach.reply_rate` | 回复率 | `outreach_system` | unreliable | 回复 ÷ 发送 | 无代码（`nox-weekly` L73） |

**覆盖检查（对任务书要求的逐项对账）**

| 要求 | 落在哪条 | 是否覆盖 |
|---|---|---|
| 均播三种取值面 | M1（`api_field`）／M2（`detail_drawer`）／M3（`pipeline_v2`） | ✅ 三条分列 |
| 订阅数 | M5 | ✅ |
| 互动率 | M6 | ✅ |
| CPM | M7 | ✅ |
| 回复率 | M10 | ✅ |
| 声量份额 | M8（平台面）＋ M9（提及面） | ✅ 两面分列 |
| 额外 2 条 | M4（套餐分母）／M9（SOV 第二面） | ✅ 用满 10 个名额 |

---

## 1.8 M1 `metric.creator.avg_views.reported` 均播（接口直读 · 均值口径）

- **id**：`metric.creator.avg_views.reported`
- **名称**：均播（接口直读 · 均值口径）
- **取值面**：`api_field`
- **定义**：窗口内**总播放 ÷ 窗口内新视频数**（均值）。字段：`discovery.getChannelInsight` → `stats.{overall,vod,shorts}.averageViewsPerVideo`。三个范围各自独立，**不可互算**。
- **样本条件**：该类型 `videoCount > 0`；`vod`／`shorts` 的 `videoCount = 0` 时该字段**缺失**（正常，不是错误）。实测 `shorts` 4/6 可得、`vod` 5/6 可得。
- **窗口**：`timeRange="last_28_days"`；响应自带 `startTime`/`endTime`，实测恒为最近 28 天。不传 `timeRange` 会返回 `null`（这曾是「取不到」误判的根源）。
- **实现位置**：取数 `daniel-bot/packages/0.11.0/lib/worker.py:234 op_insight()`；落块 `daniel-bot/packages/0.11.0/lib/normalize.js:232 performanceBlock()`（仅在视频列表拿不到时兜底，块内自报「平台汇总（均值口径，非页面口径）」，L244）。
- **`data_status`**：`unreliable`
- **`status_reason`**：均值会把长尾流量摊到新视频上 —— 母本 L674（教训 25）实测「6 Months Later 该值 **216K** 而其视频清单均值仅 **34K**」；`normalize.js:161` 实测「均值与页面中位数相差可达一个数量级（**7,820 vs 665**）」。两条独立实测都指向同一结论：这个数不能当频道的代表值。
- **替代口径**：`metric.creator.avg_views.drawer`（M2，默认对外）、`metric.creator.avg_views.pool`（M3，名单产线）
- **出处**：母本 `docs/marketing/skills/kol-intelligence.md:674`；`lib/normalize.js:155–161、232–249`；`docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md:112–126`（§三：11 指标与可得率）。
- **使用限制**：只能写「按平台 28 天均值口径读到 X」；**不得**与 M2/M3 的数并列放在同一列比大小（跨面比＝假结论）。

---

## 1.9 M2 `metric.creator.avg_views.drawer` 均播（详情抽屉 · 28 天窗 · 中位数）

- **id**：`metric.creator.avg_views.drawer`
- **名称**：均播（详情抽屉 · 28 天窗 · 中位数）
- **取值面**：`detail_drawer`
- **定义**：长视频（`contentType = VIDEO_ON_DEMAND` 且 `views ≥ 100`）与短视频（`contentType = SHORTS`，无播放阈值）**各自**播放量的中位数；「整体」＝ 长视频样本 ∪ 短视频样本（**不是**全部视频——播放 <100 的长视频页面本来就不计）。
- **样本条件**：近 28 天内且条数 ≥3 → 用该批；否则退回「最新 30 条」。块内必须显式标「样本 N 条」。平台实测只给 20 条（`limit` 无效），故块里不假装与页面同源同量。
- **窗口**：28 天（`WINDOW_28D_MS = 672h`，L173），按 `publishTime` 过滤。
- **实现位置**：`daniel-bot/packages/0.11.0/lib/normalize.js:199 scopeOf()`（范围与块）、`:217 performanceFromVideos()`（取样本）、`:188 median()`（偶数取上中位）、`:192 windowOf()`（窗口与回退）。
- **`data_status`**：`reliable`
- **`status_reason`**：与 Daniel 详情抽屉**同口径现算**（注释 L163 逐字「逐字复现（与 `.kol-tools/daniel_ui_parity.py::video_list_stats` 对齐）」），且已标样本量、不假装与页面同量（L170–171）。
- **替代口径**：`metric.creator.avg_views.reported`（M1，仅作兜底）、`metric.creator.avg_views.pool`（M3）
- **出处**：`lib/normalize.js:155–229`；`docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md:144–171`（视频清单投影陷阱）。
- **使用限制**：① 必须带「样本 N 条」；② `N < 5` 时只能说「样本不足」，不得给结论（样本门槛见 §1.19 与 Q-23）；③ 与 M1 混用时必须标面。

---

## 1.10 M3 `metric.creator.avg_views.pool` 均播（名单产线 · 有界全量池中位数）

- **id**：`metric.creator.avg_views.pool`
- **名称**：均播（名单产线 · 有界全量池中位数）
- **取值面**：`pipeline_v2`
- **定义**：`有界全量池（最近 12 个月 ∩ 最新 100 条 → 去重 → 剔 views<100）内 VOD 播放量的中位数`（母本 L724 逐字）。「其余算法只作信息列并标口径」。
- **样本条件**：窗口实际不足 **≥50 条**须标「**池量不足**」，并同时报 **页数／池量／池内 VOD 数／Shorts 占比**（母本 L724）。
- **窗口**：最近 12 个月 ∩ 最新 100 条；实现形态是 **2 页 × 50**（`pageSize` 上限 50，传 100 → HTTP 400）。
- **实现位置**：**仓库内没有实现函数** —— 该口径只以文字存在于母本 L724，交付列名落在 `contracts/kol-list.json:63`（`长视频均播（近28天中位数）`）与 `:76`（排序）。
- **`data_status`**：`reliable`（**有条件**：池量达标且标了口径）
- **`status_reason`**：它是母本判定的「名单产线唯一口径」，能解决同名两数的问题；但目前**没有代码实现、也没有门禁**，只能靠执行方自觉。另有一处硬冲突：**契约列名写「近 28 天」，母本口径是「12 个月 ∩ 最新 100 条」** —— 两个窗口不是一件事（**Q-03**）。
- **替代口径**：`metric.creator.avg_views.drawer`（M2，样本更短但可现算）
- **出处**：母本 `:724`（教训 74，逐字含「17,850 vs 9,632」）；`contracts/kol-list.json:63、69–76`；`docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md:473`（规范名 `avg_views_pool_median`）、`229–236`（2 页 × 50 的硬限）。
- **使用限制**：池量不足时必须写「池量不足」，不能只给数；与 M2 同时出现时必须分列并各标窗口。

---

## 1.11 M4 `metric.creator.avg_views.package` 均播（按成交形式取值 · CPM 分母 N）

- **id**：`metric.creator.avg_views.package`
- **名称**：均播（按成交形式取值 · CPM 分母 N）
- **取值面**：`manual_formula`
- **定义**：按**本行成交形式**取值 —— `1 长 → 长视频均播`；`1 短 → 短视频均播`；`1 长 + 1 短 → 两者相加`（母本 L683 逐字）。
- **样本条件**：随所选的 M1/M2/M3 面，**必须写明用的是哪一面**；抽屉值取不到时用「有界全量池同结构计算并标注来源」（母本 L683 末句）。
- **窗口**：随所选面。
- **实现位置**：无代码。公式在母本 L683；同一条公式在 `.agents/skills/kol-negotiation/SKILL.md:60` 重复（「CPM ＝ 报价 ÷ 均播 × 1000；1 长 + 1 短套餐用合并曝光（长均播＋短均播）；同一行只允许一个 CPM」）。
- **`data_status`**：`unknown`
- **`status_reason`**：公式本身明确，但「用哪一面的均播」没有强制绑定 —— 而教训 74 已实测同一 KOL 在两批里显示 **17,850 vs 9,632**。分母换面，CPM 就能差一倍以上，且读者看不出来。
- **替代口径**：无（这一条本身就是「组合规则」，不能替代）；但**每个 N 必须挂面标签**（`reported`/`drawer`/`pool`）。
- **出处**：母本 `:683`（教训 34）；`.agents/skills/kol-negotiation/SKILL.md:60`；`contracts/kol-list.json`（交付件不含 CPM 列 —— CPM 只出现在谈判侧审核表，不在名单契约里）。
- **使用限制**：交付件里出现 `N` 或「均播」列时，必须与 CPM 分母同面同窗；不同面并列 ⇒ 视为违规（对应 `kol-list.json#自检 K1` 的「未标口径的数字」）。

---

## 1.12 M5 `metric.creator.subscribers` 订阅数（快照）

- **id**：`metric.creator.subscribers`
- **名称**：订阅数
- **取值面**：`api_field`
- **定义**：频道订阅数**快照**，整数、**不压缩**（要能与页面的 523,922 逐格对上，见 `normalize.js:147` 注释 `int()`）。
- **样本条件**：单频道单次；三个来源的覆盖率差别很大 —— `getChannelDetail` 6/6；`parallelSearch` ≈40–70%（随词面波动）；Job 路线 100%。**字段为空 ≠ 该频道不合格**，空值者下推下一层。
- **窗口**：取数时点（会滚动，无历史快照）。母本字典已裁决「粉丝增长趋势」为 `unavailable`。
- **实现位置**：`daniel-bot/packages/0.11.0/lib/worker.py:210`（`COMPACT_FIELDS` 含 `subscriberCount`）；`lib/normalize.js:342`（`subscriberCount: '订阅数'` 的业务化改名）；契约列 `subscriberCount`（`high-performance-video-list.json#交付件schema.列`）。
- **`data_status`**：`reliable`
- **`status_reason`**：三个来源同名同义、单位一致（整数）；唯一风险是**覆盖率**而非口径 —— 已在样本条件里写死「空值不下推结论」。
- **替代口径**：无（量级档 `magnitude_tier` 是它的派生分档，不是替代）。
- **出处**：字段字典 `:136`（§四 12 字段）、`:203`（召回层覆盖率）、`:222`（空值纪律）、`:469`（规范名 `subscribers`）；`normalize.js:147、342`。
- **使用限制**：必须标「取数时点」；同一份交付里不同行若取数日期不同，必须逐行标，不得只写一个总日期。

---

## 1.13 M6 `metric.creator.engagement_rate` 互动率

- **id**：`metric.creator.engagement_rate`
- **名称**：互动率
- **取值面**：`api_field`
- **定义**：`(Σlikes + Σcomments) / Σviews`，**分母用同一批样本**（`normalize.js:202` 注释逐字）。两个来源、两种单位：
  · `getChannelInsight.stats.*.engagementRate` → **0–1 小数**（`0.089315` ＝ 8.93%）；
  · `lists.getItems.engagementRate` → **百分数**（`1.6` ＝ 1.6%）。
- **样本条件**：该范围**全量视频**（页面不对互动率开窗，`normalize.js:202` 逐字「分母用该范围全量视频（页面不对它开窗）」）；`views = 0` 时返回 `null`，不得写 0。
- **窗口**：insight 侧 28 天；表现块侧不按 28 天开窗 —— **同一块里均播与互动率不同窗**。
- **实现位置**：`lib/normalize.js:211`（`互动率: views > 0 ? pct2((likes + comments) / views) : null`）；`:242`（insight 分支 `pct2(o.engagementRate)`）；`:143 pct2()`（统一成百分数 2 位）。
- **`data_status`**：`unreliable`
- **`status_reason`**：①**单位两套、差 100 倍**（字段字典 §十 L438–441：「同一个字段名，一处是小数、一处是百分数，相差 100 倍。两处混用会造成数量级错误」）；②**分母开窗不一致**（均播开窗、互动率不开窗）；③名单条目与洞察层同名不同源。
- **替代口径**：无（P1 建议把 `list_item` 面单独登记为一条，见 **Q-14**）
- **出处**：字段字典 `:438–441`、`:481`（规范名 `engagement_rate` 与三条来源分支）；`lib/normalize.js:143、202–211、242`；契约列 `互动率`（`(点赞+评论)/观看量`，`high-performance-video-list.json#交付件schema.列`）。
- **使用限制**：写交付件前必须统一成百分数 2 位并标来源分支；不得把两个来源的互动率放同一列排名。

---

## 1.14 M7 `metric.quote.cpm` CPM（报价评估）

- **id**：`metric.quote.cpm`
- **名称**：CPM
- **取值面**：`manual_formula`
- **定义**：`CPM ＝ 报价 ÷ N × 1000`，其中 `N ＝ M4`（按成交形式取的均播）。套餐按 `$80–100` 判读，分母为相加值。
- **样本条件**：一行一个报价；报价与 N 必须同面同窗；**同一行只允许一个 CPM**（`kol-negotiation` L60 逐字）。
- **窗口**：报价时点。
- **实现位置**：无代码。判据在母本 `:3220–3227`（§5.1 CPM 初步评估参考判据：长视频合理 CPM `$60–80`、套餐 `$80–100`、`$100` 为上限），公式在 `:683`；`.agents/skills/kol-negotiation/SKILL.md:41–48、60`。
- **`data_status`**：`unreliable`
- **`status_reason`**：两条独立理由 ——
  ① 分母可换面：`N` 取决于用 M1/M2/M3 哪一面，实测同一 KOL 两批差 **17,850 vs 9,632**（母本 L724）；
  ② 算法本身已被降级：母本 L31 记载 8 处真实砍价结论回测 —— **百分比式命中 6/8、CPM 反推式命中 0/8 且系统性高估约 2 倍**，因此「CPM 反推目标价」**降级为上限校验**，主用「按对方报价砍 `[60%, 85%]`」。
- **替代口径**：按对方报价砍百分比（母本 L31）；CPM 只作「上限校验」（砍完仍 > 2× 带上沿 ⇒ 砍幅不足，须写明理由）。
- **出处**：母本 `:31`（§5.1 砍价口径修正）、`:683`（教训 34）、`:3220–3227`（§5.1 判据表）；`.agents/skills/kol-negotiation/SKILL.md:41–48、60`。
- **使用限制**：① 交付件里的判断词只有三种（报价合理／报价偏高／报价过高，母本 `:4126` §13.3）；② `$60–80`／`$80–100` 是**参考基准不是硬门槛**，放宽须写理由；③ 不得把 CPM 当唯一判据（会把「可谈」的人误判成「排除」，母本 L692）。

---

## 1.15 M8 `metric.sov.platform_share` 声量份额（平台返回）

- **id**：`metric.sov.platform_share`
- **名称**：声量份额（平台返回 `share`）
- **取值面**：`api_field`
- **定义**：`daniel sov overview` 返回的各品牌 `share` —— **百分比、1 位小数**，由服务端计算，我方**只读不重算**（`daniel_sov.py:226 brand_share()` 逐字「从 `getSummary.brands` 或 `getSovOverview.brands` 里取某品牌的份额（百分比，1 位小数）」）。
- **样本条件**：同一品类大盘内被收录的视频；`--country` 不传时取品牌档案里的第一个市场；`--days` 默认 30。
- **窗口**：`--days`（默认 30）；窗口与市场**必须声明**，否则两版数据不可比。
- **实现位置**：`.kol-tools/daniel_sov.py:226–246 brand_share()`（只读；品牌不在结果里返回 `None`，**不臆造 0**）；`daniel-bot/packages/0.11.0/vendor/data/daniel-cli/daniel_cli/commands/mod_sov.py:27`（读链复用仪器）。
- **`data_status`**：`unknown`
- **`status_reason`**：**分母未声明** —— 是「品类大盘全部被收录视频」还是「竞争集各品牌之和」，服务端没有文档，本仓也没有逐字公式。实测数（大盘 4,840 条 / 107,386,664 观看；Halliday 归属 9,140,520 ≈ 8.5%）与「大盘」读法**相容但不能证明**。在分母确定前，任何「我们占 X%」的对外表述都不可复现。
- **替代口径**：`metric.sov.mention_share`（M9，分母写死为固定竞争集）—— **两者不可互比**。
- **出处**：`mcp/corpus/kol-daniel-api/references/60-data-layer.md:242、249`；`.kol-tools/daniel_sov.py:226–246`；`daniel_cli/schema.py#sov.overview.returns`（「各品牌的播放量、视频数与份额占比」）。
- **使用限制**：① 必须写市场与窗口；② 品牌不在结果里时写「该品牌不在本次统计内」，不得写 0%；③ 与 M9 并列时必须标「不同分母」。

---

## 1.16 M9 `metric.sov.mention_share` 声量份额（提及份额 · 固定竞争集）

- **id**：`metric.sov.mention_share`
- **名称**：声量份额（提及份额）
- **取值面**：`manual_formula`
- **定义**：`SOV = 品牌提及 ÷（自身 + 竞争集品牌）提及 × 100（%）`，提及逐条**回源核验**；**必须与情感同读**（负向高声量是警告不是胜利）。
- **样本条件**：固定竞争集（定案后不随意增删）；同一市场、同一渠道、同一时间窗；情感三档（正/中/负）抽样判定并记录抽样规则与样本量。
- **窗口**：由「口径声明」定，窗口 ≥1 个月（`processes.json#execution-sov-07` 前置条件：「窗口不少于一个月」为默认）。
- **实现位置**：无代码。公式在 `.agents/skills/kol-execution-sov/SKILL.md:97`（源 `:3947–3963` 逐字摘录）；口径三决策在同文件 `:87–104`；工序 `processes.json#execution-sov-07`（口径定案）、`#execution-sov-08`（报告出件）。
- **`data_status`**：`reliable`（**有条件**：竞争集定案 ＋ 提及核验 ＋ 情感同读）
- **`status_reason`**：公式与分母都写死（固定竞争集），能复算；风险不在算法而在**输入是否核验过** —— 所以「提及逐条回源核验」是它的成立条件，不是可选项。
- **替代口径**：`metric.sov.platform_share`（M8）—— 分母不同，只能各自表述。
- **出处**：`.agents/skills/kol-execution-sov/SKILL.md:87–104`（§7 阶段 6）；`processes.json#execution-sov-07、execution-sov-08`；`docs/marketing/skills/kol-intelligence.md`（源节 L3947–3963）。
- **使用限制**：① 必须先有「口径声明」（竞争集／关键词／渠道／时间窗）；② 报告首段写声明，全文一致；③ 竞争集以品牌档案里自己配的竞对为准，**不得按份额前三收窄**（`references/60-data-layer.md:360–362`）。

---

## 1.17 M10 `metric.outreach.reply_rate` 回复率（建联）

- **id**：`metric.outreach.reply_rate`
- **名称**：回复率
- **取值面**：`outreach_system`（Nox）
- **定义**：`回复 ÷ 发送`；其中 `回复人数 = 有红人来信的会话数`、`已送达 = 发送 − 退订`、`已读 = 收件人中 opened 的人数`。口径按**收件人逐人状态**算，**不用接口的 arrive 字段单算一套**。
- **样本条件**：同一批次集合（一个 task_id ＝ 一个批次）；`pitch 轮数` 窗口内各批轮数相加，**轮号不能跨批相加**（各批轮号各自从 1 起）。
- **窗口**：`--window A..B`（只影响标签与筛选，`..` 渲染成 `~`）。
- **实现位置**：无代码（Nox CLI ＋ `run.sh` / `fetch.py`）。口径表在 `.agents/skills/nox-weekly/SKILL.md:69–74`（六指标一条链：发 → 达 → 读 → 回）与 `:191`（W2 数字自证：`回复率 ＝ 回复 ÷ 发送`）；字段口径在 `.agents/skills/nox-cli/SKILL.md:130–140`（批次／轮次／会话／发送／到达／退订六个词）。
- **`data_status`**：`unreliable`
- **`status_reason`**：**三个分母并存** —— 报表 `sent_count`、会话数、逐人状态。`nox-cli` L138 逐字：「到达率分母是发送，不是会话；**与逐人状态推出的『已送达』可能对不上**，页面上统一用逐人状态」。另：会话数 < 发送数（发送前退订的人没有会话），用会话数冒充发送数会系统性偏高。
- **替代口径**：无；**唯一合法口径是逐人状态**（其余只能作旁证并标口径）。
- **出处**：`.agents/skills/nox-weekly/SKILL.md:69–74、191`；`.agents/skills/nox-cli/SKILL.md:130–140`；`.agents/skills/nox-outreach-data/SKILL.md`（归类与报价整理，不改分母）。
- **使用限制**：① 跨批次合并必须带合计行且不与单批口径混；② 读会话会**清掉 Nox 的未读标记** ⇒ 看板主指标用「待回复」不用「未读数」，且必须告知业务（`nox-cli` L154–158）；③ 该指标**不在 Daniel 内**（Q-05：是否纳入 P0 语义层需拍板）。

---

## 1.18 同名指标 × 取值面矩阵（为什么必须分面登记）

| 指标名（业务叫法） | 取值面 | 登记 id | 值会差多少（实测） |
|---|---|---|---|
| 均播 | `api_field` | M1 | 216K（insight） vs 34K（视频清单均值）—— 母本 L674 |
| 均播 | `detail_drawer` | M2 | 7,820 vs 665 —— `normalize.js:161` |
| 均播 | `pipeline_v2` | M3 | 17,850 vs 9,632（两批）—— 母本 L724 |
| 均播（套餐） | `manual_formula` | M4 | 长+短相加 ⇒ 分母可翻倍 |
| 互动率 | `api_field`（insight） | M6 | 小数 vs 百分数 ⇒ 差 100 倍 —— 字典 L438–441 |
| 互动率 | `list_item`（名单条目） | **未登记**（Q-14） | 同上，且分母不同源 |
| 声量份额 | `api_field`（平台 `share`） | M8 | 分母未声明 ⇒ 不可复算 |
| 声量份额 | `manual_formula`（提及份额） | M9 | 竞争集不同 ⇒ 百分比完全不同 |
| 回复率 | `outreach_system`（逐人状态） | M10 | 与报表 `sent_count` 口径对不上 |

**与已上线登记项的对应（必读，避免出现第二套口径）**

| 本文 id | 已上线登记项（`12-ontology-registry.md`） | 对应关系 |
|---|---|---|
| M1 | 无（已上线只登记了两个面） | **新增** |
| M2 | `metric.creator.avg_views_long.surfaces.median` | 同一件事，**但已上线写的 `sample_rule` 是「近 28 天、时长 > 60 秒」，与代码（`contentType=VIDEO_ON_DEMAND` 且 `views≥100`，无时长条件）不一致** ⇒ Q-16 |
| M3 | 无 | **新增** |
| M4 | 无（`external_only: median` 只指定了对外面） | **新增** |
| M5–M7、M9–M10 | 无 | **新增** |
| M8 | 无 | **新增** |

> 一句话：已上线只覆盖了「均播的一个面 ＋ 两类判据 ＋ 一份表达」，本文要补的是其余 9 个指标 ＋ 5 个概念。
> **但补之前必须先定形态（Q-01）** —— 否则会出现「同名指标、两套字段名（`surfaces` vs `取值面`）」的第二真源问题，这正是 v0.4 §4 明令禁止的。

---

## 1.19 为什么不给「均播」一个唯一权威值（证据链）

> 这不是谨慎，是实测。四条证据、三个不同来源、两个不同年份的执行批次，结论一致。

| # | 证据 | 数值差 | 出处 |
|---|---|---|---|
| 1 | 平台 insight 均值 vs 视频清单均值 | **216K vs 34K**（≈6.4×） | 母本 `:674`（教训 25） |
| 2 | 页面中位数 vs insight 均值 | **665 vs 7,820**（≈11.8×） | `lib/normalize.js:155–161` |
| 3 | 名单产线两批同号 | **17,850 vs 9,632**（≈1.85×） | 母本 `:724`（教训 74） |
| 4 | 抽样近似口径 vs 精确口径 | 「≥120s、最多 10 条算术平均」**非**严格最近 10 条/90 天 | 母本 `:552` |

**由此得到三条硬规则（写进规章，不改）**

1. **一个面一条登记**：同一业务名允许多条 metric，但 `id` 必须带面（`…reported` / `…drawer` / `…pool`）。
2. **跨面不比数**：v0.4 §9.3 已写死「跨模型比数字时只在同一 `取值面` 内比」，否则会得出「模型不一致」的假结论。
3. **交付必带三件**：指标 id ＋ 取值面 ＋ `data_status`（不可靠面还要带替代口径）。缺一件即视为「未标口径的数字」，对应 `contracts/kol-list.json#自检 K1` 的第 1 类违规。

**`data_status` 词表映射（本文 ↔ 已上线）**

| 本文 | 已上线 | 语义 |
|---|---|---|
| `reliable` | `reliable_when_sample_ok` | 有成立条件，条件满足即可用 |
| `unreliable` | `unstable_when_small_sample` | 会系统性误导，不得单独作结论 |
| `unknown` | （无对应值） | 口径缺失或分母未声明 |
| — | （无对应值） | 已上线还用了「样本 <5 不出结论」作为独立字段（`min_sample`），本文把它并入「样本条件」 |

> 【待确认】Q-12：两套词要不要统一；统一成哪一套。

---

## 1.20 概念/指标 × 现有契约字段 对照表

> 读法：**状态**列只有三种 —— `复用`（既有字段可直接承载）、`新增登记`（本文第一次登记）、`待确认`（有冲突或口径不明）。
> 契约字段名逐字取自文件，未做改写。

| # | 契约字段（文件#位置） | 字段/列名 | 对应概念/指标 | 状态 | 说明 |
|---|---|---|---|---|---|
| 1 | `high-performance-video-list.json#交付件schema.列` | 频道编号 `channelId` | `concept.creator` | 复用 | 概念唯一键已存在 |
| 2 | 同上 | 频道名 `channelTitle` | `concept.creator` | 复用 | — |
| 3 | 同上 | 频道账号 `channelHandle` | `concept.creator` | 复用 | 可为 null，已标 `无官方数据` |
| 4 | 同上 | 订阅数 `subscriberCount` | M5 | 复用 | 口径一致（整数快照） |
| 5 | 同上 | 频道平均观看 `channelAvgViews` | M1（近似） | **待确认** | 契约未标口径；可能是 M1 也可能是 M2 ⇒ Q-16 |
| 6 | 同上 | 频道平均互动率 `channelAvgER` | M6 | **待确认** | 未标小数/百分数 ⇒ 单位陷阱风险 |
| 7 | 同上 | 观看量 `videoViews` | （视频级播放） | 新增登记 | P0 十个名额未含，见 Q-13 |
| 8 | 同上 | 点赞 `videoLikes` / 评论 `videoComments` | （视频级互动） | 新增登记 | 同上 |
| 9 | 同上 | 互动率 `(点赞+评论)/观看量` | M6（视频级面） | **待确认** | 与 M6 的频道级面不是同一分母 |
| 10 | 同上 | 观看表现档 `viewsPerf` / 互动表现档 `erPerf` | （平台分档） | 新增登记 | 平台原生分档，非自造 |
| 11 | 同上 | 表现评级 `overallPerformance` | （平台原生评级） | 新增登记 | 枚举映射见 §2.5 门禁 G4 |
| 12 | 同上 | Rated Score `compositeIndex` | （平台加权分 0–5） | 新增登记 | 权重：观看 40%／互动 25%／点赞 20%／评论 15% |
| 13 | 同上 | 相关性 `relevanceLabel` | （枚举） | 新增登记 | `confirmed/likely/unlikely`（字典 §15.5.3） |
| 14 | 同上 | 品牌点名位置 / 点名证据原话 | `concept.product`（间接） | 复用 | 判定「是否真点名」的证据列 |
| 15 | `kol-list.json#交付件schema.列` | 长视频均播（近28天中位数） | M2 ＋ M3 | **待确认** | **列名一个窗、母本口径另一个窗**（Q-03） |
| 16 | 同上 | 互动表现 | M6 | 复用 | 需补单位与来源分支 |
| 17 | 同上 | 订阅数 | M5 | 复用 | — |
| 18 | 同上 | 市场/受众 | （受众指标） | 新增登记 | 受众 Top3 截断口径未登记 |
| 19 | 同上 | 入选依据 | （可追溯要求） | 复用 | 对应「每条带依据」 |
| 20 | `kol-list.json#自检 K1` | 四类违规（未标口径／禁用表述／未列未筛维度／不可靠指标未标注） | M1–M10 的 `data_status` | 复用 | **这是 `data_status` 在契约里唯一的落地处** |
| 21 | `kol-list.json#门禁` | 只读默认／写权限／写步骤确认／回读校验／样本上限 | — | 复用 | 与手册 §2.0 的四道闸同源 |
| 22 | `real-brands-inventory.json#交付件schema.列` | `id`/`name`/`workspaceId`/`workspaceName` | `concept.brand` | 复用 | 品牌四列齐 |
| 23 | `search-terms-check.json#交付件schema.列` | 检索词／是否合规／命中判据 | `concept.product`（词表） | 复用 | 型号以检索词形态出现 |
| 24 | `script-review.json#交付件schema.列` | 判定／修改意见／brief 出处 | — | 复用 | 与语义层无关，仅证明四段结构可承载 |
| 25 | 任一契约 `#交付件schema` | 排序／无数据写法／计数对账 | — | 复用 | 「无数据写法」是 `data_status=unknown` 的落点 |
| 26 | 任一契约 `#判据出处` | 判据 → 出处（章节＋行号） | — | 复用 | 已有「出处」心智，缺「指标 id」字段 |
| 27 | 任一契约 `#交付件schema` | （无）指标列 `指标列[]` | 全部 M | 新增登记 | v0.4 §6.1 计划新增；本文只登记需求，不改契约 |
| 28 | 任一契约 `#交付件schema` | （无）表达 `{段序,必带口径段,禁用表述}` | — | 新增登记 | v0.4 §6.3 计划新增 |
| 29 | `processes.json#<工序键>` | `前置条件[]`（名称/来源类型/取数方式） | 手册 §2 的前置 | 复用 | 手册不复制正文，只登记工序键 |
| 30 | `processes.json#<工序键>` | （无）`卡点`/`卡点追问键`/`判据引用` | — | 新增登记 | v0.4 §6.2 计划新增；P0 只 6 条主链 |
| 31 | `_ONTOLOGY.json` | `entry_count`/`entries` | 全部登记项 | 复用 | 索引形态已存在 |
| 32 | `12-ontology-registry.md#B.5` | `criterion.clarify.param_gate`（4 场景／28 dims） | （追问闸） | 复用 | **不重抄**，手册直接引用该 id |
| 33 | `12-ontology-registry.md#B.1` | `surfaces.{reported,median}` | M1/M2 | **待确认** | 与本文 `取值面` 是同一概念的两个词（Q-01） |
| 34 | `12-ontology-registry.md#B.3` | `expr.kol_list`（段序／必带／禁用词） | — | 复用 | 表达契约的既有落点 |

**统计**

| 状态 | 条数 | 占比 |
|---|---|---|
| 复用（既有字段可承载） | **19** | 56% |
| 新增登记（此前没有机器可读入口） | **10** | 29% |
| 待确认（有冲突或口径不明） | **5** | 15% |
| 合计 | **34** | 100% |

> 解读：**超过一半的字段已经存在**（19/34），语义层要做的主要不是「造字段」，而是「给已有字段挂 id 与口径」。
> 这与 v0.4 §4「①② 是新登记，③④⑤ 已有真源、索引只登记指针」的判断一致。

---

# 第二部分 · 操作手册（8 个 P0 能力）

## 2.0 统一约定（先读，后面每节都受它约束）

### 2.0.1 命令写法与退出码

| 项 | 约定 | 出处 |
|---|---|---|
| 命令形态 | `daniel <模块> <子命令> [--参数]`（如 `daniel brands list --workspace 90002`） | `daniel_cli/schema.py`（单一真源，`daniel schema --check` 自证） |
| 工具形态 | `daniel_<动作>`（共 **19** 个） | `lib/index.js` 的 19 处 `ctx.tools.register`；`baseline.json:registeredCount=19` |
| `0` | 成功 | `daniel_cli/exits.py`（`EXIT_OK`） |
| `2` | 用法错误／前置不满足（**缺参数、品牌不存在、无权限**） | 同上（`EXIT_USAGE`） |
| `1` | 运行失败（取数失败、服务端错误） | 同上（`EXIT_INTERNAL`） |
| `3` | **写操作未确认**（只做了干跑，零写入） | `index.js:865`（`exitCode === 3` → `write_needs_plan`）；`schema.py` 头注释写链② |

> 退出码不是给人看的，是给门禁判的：**`2` 与 `1` 必须走不同话术**（前者是「你少给了/没权限」，后者是「系统这次没跑通」）。
> 混用的后果：用户会去重试一个永远失败的命令，或者以为有权限。

### 2.0.2 三类失败形态（每个能力都必须分这三类写）

| 类 | 判定 | 话术要点 | 下一步 |
|---|---|---|---|
| **错误码** | 有明确 `exitCode` 与 `error.kind` | 说清「缺什么/哪一步不允许」，不解释内部实现 | 补齐或换路径；**同一动作失败两次必须换路径**（产品文档 §8.3） |
| **超时** | 无终态、长时间 pending | **不判失败**：先说「还没跑完」，并给当前阶段 | 查状态；**不得重复提交**（避免重复计费/重复任务） |
| **无数据** | 请求成功但结果为空 | 必须分清三态（见下），**不得写「没有」** | 平台未收录 → 换信号；本次未取到 → 可重试；成功零命中 → 换词/换条件 |

**「无数据」的三态（本项目已固化的词，不得自造）**

| 态 | 含义 | 写法 |
|---|---|---|
| 平台未收录（`empty`） | 接口正常返回、该字段本来就没有 | 「平台没有这项数据，再查也一样」 |
| 本次未取到（`error`/missing） | 取数失败或根本没走到 | 「这次没取到，可重试」 |
| 成功零命中 | 请求成功、确实没有符合条件的结果 | 「这次条件下一共 0 条」＋ 逐词/逐条件计数 |

> 出处：`lib/normalize.js:305–320`（两态分开的逐字注释）、`lib/worker.py:289、294`（`insightStatus` 三值 `ok/empty/error`）、`processes.json#discovery-07`（三态计数：成功有命中／成功零命中／失败）。

### 2.0.3 写操作：四道闸 ＋ 下一步卡片（全部能力共用）

| 闸 | 机制 | 落点 |
|---|---|---|
| ① 权限 | 账号对该模块有写权限才放行，否则 `exit 2` ＋ 人话理由 | `schema.py` 头注释写链①；`daniel account capabilities` |
| ② 确认 | 不带 `--confirm` 一律只干跑，`exit 3`，**零写入** | `schema.py` 头注释写链② |
| ③ 删除凭据 | 删除类还要 `--delete-token <目标名>`（原样再写一遍，写错即拒） | 同上写链③；`deleteTarget` 字段 |
| ④ 回读 | 写后回读校验并给审计落点 | `daniel account audit`（记录条数／真执行／未执行／已回滚） |

**agent 侧的唯一合法写路径**：`daniel_write_plan(argv)` → 把计划原样给用户 → 用户明确说「可以/继续」→ `daniel_write_commit(planId)`。
**禁止**：把「用户问了一句」当成确认；一次确认复用给多次写；跳过 plan 直接 commit。
（产品文档 §3.5、§5.4；AGENTS.md 第 7 条 A/B 款）

### 2.0.4 五个通用门禁（所有能力开工前先过）

| # | 门禁 | 判据 | 不满足时 |
|---|---|---|---|
| **G-0** | 登录态 | `daniel auth status` 退出码 0 | 停：先 `daniel_login`，不空转 |
| **G-1** | 账号与工作区 | `daniel account whoami` 有当前工作区编号 | 停：工作区未确认就取数会串区 |
| **G-2** | 品牌已建档 | `daniel brands show --brand` 命中 | 停：**不代建**；给建档的下一步卡片 |
| **G-3** | 口径先声明 | 交付涉及的指标都有「指标 id ＋ 取值面 ＋ `data_status`」 | 停：口径没定就不出数（产品文档 §4.4） |
| **G-4** | 不编 | 每个数字能追到命令/字段；追不到的写「未取到/待确认」 | 停：宁可少写一句（产品文档 §6.3 第 2 条） |

### 2.0.5 每个能力的写法（固定七块）

`能力 id 与命令/工具` → `输入` → `输出` → `前置条件` → `门禁` → `失败形态` → `是否写操作`。
块内不写形容词，只写能判定的条件。

---

## 2.1 CAP-01 红人检索

**能力 id**：`CAP-01-creator-search`
**对应命令/工具**

| 场景 | 命令 | 工具 | 写？ |
|---|---|---|---|
| 有品牌上下文（第一段：只出计划） | `daniel search submit --brand <品牌> --query <检索式> [--limit]`（干跑） | `daniel_deep_research` | 否 |
| 有品牌上下文（第二段：真提交） | 同上 ＋ `--confirm` | `daniel_deep_research_commit(planId)` | **是** |
| 无品牌／自由描述 | `daniel_open_research` | `daniel_open_research` | 是（自动选默认项并执行） |
| 查进度 | `daniel search job-status --job <任务编号>` | `daniel_research_status(jobId)` | 否 |
| 看历史 | `daniel search history [--limit 10]` | `daniel_run(["search","history"])` | 否 |
| 词表体检 | `daniel keywords check --file <路径> [--strict-exit]` | `daniel_run` | 否 |
| ⛔ 官方库 | — | `daniel_roster_search`（**已退役，零发包**） | — |

**输入**

| 字段 | 必填 | 合法值域 | 缺失时行为 |
|---|---|---|---|
| `brand` | 是（deep 通道） | 品牌名或品牌编号（`3690002`），必须能在 `brands show` 命中 | 缺 → **改走 open 通道**，不猜品牌 |
| `query` | 是 | 自然语言检索式（如「AI glasses review」） | 缺 → `exit 2`，错误逐字「query 必填（检索式：描述要找什么样的红人）」 |
| `country` | 否 | ISO 国家码，多个用逗号（`US,CA,GB`） | 缺 → 不传（平台按账号默认）；交付注明「未限定市场」 |
| `min_subscribers` / `max_subscribers` | 否 | 整数 | 缺 → 不传；**不得擅自加门槛**（`processes.json#daniel-api-10`） |
| `limit` | 否 | 默认 10 | 缺 → 10；**只决定结果摘要展示上限**，服务端检索任务不接受条数 |
| 检索词（关键词路径） | 否 | 文件路径 | 缺 → 不跑 `keywords check`；但一旦要投关键词，必须先过（G3） |

**输出**

| 字段 | 来自 | 口径登记 |
|---|---|---|
| 任务编号 / 状态（排队中／检索中／富化中／完成／失败） | `search job-status`（五档逐字） | — |
| 候选频道：`channelId` / `title` / `handle` / `subscriberCount` / `country` / `topicCategories` / `tags` | 检索结果（字段字典 §6.1 15 字段） | `concept.creator`；订阅数 → **M5** |
| 命中证据：`matchedVideos` / `foundByKeywords` | 同上 | 用于「入选依据」列（`kol-list.json` 必填列） |
| 计划摘要：检索式、品牌、影响说明（会建任务/写一条检索记录/额度不限）、`planId` 与过期时间 | `daniel_deep_research` | — |
| 零成本预筛台账：挡下条数与原因分布 | 本地计算（字典 §6.1 纪律） | 不产出指标 |

**前置条件**

| # | 条件 | 怎么核 |
|---|---|---|
| P1 | 已登录 | `auth status` = 0（G-0） |
| P2 | 工作区已确认 | `account whoami` 有工作区编号（G-1） |
| P3 | 品牌已建档 | `brands show --brand` 命中（G-2） |
| P4 | 门槛与目标市场已给定（或明确用默认） | 用户原话；缺则按默认并标「未确认门槛」 |

**门禁（不满足就停，不猜）**

| # | 门禁 | 判据 | 停了之后 |
|---|---|---|---|
| G1 | 品牌不在册 | `brands show` 未命中 | 停在「建档 or 换 open 通道」二选一，**不代建** |
| G2 | 未登录 / 无工作区 | G-0/G-1 失败 | 停在登录，不发起检索 |
| G3 | 关键词路径未过词表体检 | `keywords check` 违规数 > 0 | 停：先改词表（`--strict-exit` 时退出码 2） |
| G4 | 任务未到终态 | `job-status ≠ 完成/失败` | 停：只报进度，**不取半批结果** |
| G5 | 走到官方库通道 | 工具返回 `channel_retired` | 停：改 deep/open，**不得重试 roster**（零发包是设计，不是故障） |
| G6 | 门槛被擅自改动 | 与用户给定值不一致 | 停：逐字执行用户门槛，不加不减 |

**失败形态**

| 类 | 具体形态 | 话术 | 下一步 |
|---|---|---|---|
| 错误码 | `exit 2`：`brand`/`query` 缺失；品牌解析失败 | 「这次少了一个必填项（品牌或检索式），补上我就能跑」 | 补字段重试；品牌错则先确认编号 |
| 超时 | 任务长期停在「检索中／富化中」；`executeSearchJob` 返回 503 | 「任务还在跑（当前阶段：检索中），**503 是常态不是失败**」 | 查 `job-status`；**不重复提交**（避免重复建任务） |
| 无数据 | 成功零命中 vs 逐词失败 | 「这次条件下一共 0 条；其中 N 个词是取数失败（不是没命中）」 | 失败词必须回补；零命中换词/放宽市场 |

> 逐字依据：`processes.json#discovery-07` 产出＝「三态计数回报（成功有命中／成功零命中／失败及错误码）」，且「调用失败的词必须回补，不得算成零命中」。

**是否写操作**：**是**（`search submit` 为 `write=True`/`live`；`deep_research_commit` 会真建任务）。必须走 §2.0.3 的 plan → 确认 → commit，并在提交后回读 `job-status`。

**对应工序**：`discovery-07`（候选-召回）、`daniel-api-10`（全链路-检索）
**出处**：`schema.py#search.*`；`lib/index.js:915–1010`（roster 退役 ＋ deep 两段式）；`references/60-data-layer.md:229–236`（分页硬限）、`:266–284`（Job 路线字段与 503 常态）；`processes.json#discovery-07、daniel-api-10`。

---

## 2.2 CAP-02 红人档案

**能力 id**：`CAP-02-creator-profile`
**对应命令/工具**：`daniel_kol_profile(handle, videos)`（主入口，一次拿全）；`daniel lists items --list-id … --with-handle`（名单侧补 handle）；`daniel ct resolve-channel`（只解析编号）。

**输入**

| 字段 | 必填 | 合法值域 | 缺失时行为 |
|---|---|---|---|
| `handle` | 是 | `@xxx` 或频道地址（`https://www.youtube.com/@xxx`） | 缺 → 工具直接报「handle 必填」；CLI 侧 `exit 2` |
| `videos` | 否 | 1–10，默认 5 | 超过 10 被截到 10（`Math.min(...,10)`）；**只影响展示条数，不影响计算样本** |

**输出（四块 ＋ 三个状态字段）**

| 块 | 字段 | 来自 | 口径登记 |
|---|---|---|---|
| ① 频道 | 名称／订阅数／国家／总播放／视频数 | `getChannelDetail`（12 字段） | 订阅数 → M5；`country` 是频道所在地（≠受众国家） |
| ② 表现（近 28 天） | 整体／长视频／短视频：视频数、总播放、平均播放、互动率 | **视频列表现算（优先）** → insight（兜底） | 平均播放 → **M2**（优先）／**M1**（兜底）；互动率 → **M6** |
| ③ 受众 | 性别、年龄分布、地区 Top5、兴趣与购买意向 Top5 | `getChannelInsight.audience` | 未登记（P1） |
| ④ 近期视频 | 标题／播放／点赞／时长／发布时间 | `getChannelVideos` | 视频级，未登记（Q-13） |
| 状态 | `未取到[]`／`平台未收录[]`／`替代信号[]` | `lib/normalize.js:305–325` | — |

**前置条件**

| # | 条件 | 怎么核 |
|---|---|---|
| P1 | 已登录 | G-0 |
| P2 | handle 可解析成 `channelId` | `ct resolve-channel` 成功；失败即停（不要按名字模糊匹配） |
| P3 | 若声称「数据来自名单」 | 该频道必须真在名单条目里（`lists items` 命中） |

**门禁**

| # | 门禁 | 判据 | 停了之后 |
|---|---|---|---|
| G1 | `insight` 为空就断言「没有受众」 | `insightStatus=empty` | 停：改写成「平台未收录」，**不得说「没有受众」**（这是两种不同事实） |
| G2 | 样本不足仍给结论 | 长/短视频样本 `N < 5` | 停：写「样本不足（n=X），无法判断」 |
| G3 | 把兜底均值当页面口径报 | 表现块走了 `performanceBlock`（insight 兜底） | 停：必须标「均值口径，非页面口径」（块内已自报，L244） |
| G4 | 用 handle 当唯一键 | 交付里没有 `channelId` | 停：补 `channelId`（handle 可为 null） |

**失败形态**

| 类 | 具体形态 | 话术 | 下一步 |
|---|---|---|---|
| 错误码 | handle 无法解析（`kol_profile_failed`，exit 1） | 「这个 @handle / 链接在平台里没对上频道」 | 让用户给频道链接或 `UC…` 编号；**不做模糊猜测** |
| 超时 | worker 60s 超时 | 「这次取数超时了，档案没拿全」 | 重试一次；两次仍失败按 §8.3 换路径并回报 |
| 无数据 | 档案有、`insight` 为 null | 「受众这块平台没收录（不是我们没取到）」 | 改用「平均播放＋互动率＋内容分类」判断人群（`normalize.js:323` 的替代信号） |

**是否写操作**：**否**（纯读，无缓存写入到 Daniel）
**对应工序**：`screening-01`（样本-采集）、`screening-02`（背调-出卡）的前置取数
**出处**：`lib/index.js:882–913`（工具定义与出口）；`lib/worker.py:252–330 op_kol_profile()`；`lib/normalize.js:295–327 kolFullView()`；`references/60-data-layer.md:229–236`。

---

## 2.3 CAP-03 品牌档案

**能力 id**：`CAP-03-brand-profile`
**对应命令/工具**

| 用途 | 命令 | 工具 |
|---|---|---|
| 列品牌 | `daniel brands list [--workspace <编号>] [--limit 200]` | `daniel_brands_list` |
| 品牌数（实时口径） | `daniel brands list`（实时直连） | `daniel_brand_count` |
| 看档案 | `daniel brands show --brand <品牌>` | `daniel_brand_view` |
| 看竞品 | `daniel brands competitors --brand <品牌>` | `daniel_run(["brands","competitors","--brand",…])` |

**输入**

| 字段 | 必填 | 合法值域 | 缺失时行为 |
|---|---|---|---|
| `--brand` | 是（show/competitors） | 品牌名或编号 | 缺 → `exit 2`；同名多品牌 → **停，要编号** |
| `--workspace` | 否 | 工作区编号（`90002`） | 缺 → **范围待实测**（两种说法并存，见 §1.2 坑 1）；交付必须写清本次读的是哪个工作区 |
| `--limit` | 否 | 默认 200 | 缺 → 200；结果被截断必须报「已截断」 |

**输出**

| 字段 | 来自 | 备注 |
|---|---|---|
| 品牌编号 / 品牌名 / 所属工作区编号与名称 | `brands list` | 四列与 `real-brands-inventory.json#列` 一致 |
| 简介 / 频道 / 竞品 / 目标市场 / 品类 / 行业关键词 / 样品价 | `brands show` | `sampleCost` 是样品计价，**不是零售价** |
| 竞品名 ＋ 每个竞品的品类关键词 | `brands competitors` | 竞对以品牌自己配的为准 |

**前置条件**：P1 登录（G-0）；P2 品牌编号已确认（同名必须给编号）。

**门禁**

| # | 门禁 | 判据 | 停了之后 |
|---|---|---|---|
| G1 | 用户问「全部品牌」，但本次只读了单一工作区 | 结果里的工作区编号不覆盖用户要的范围 | 停：补 `--workspace` 逐区读，或明说「只读了 X 工作区」 |
| G2 | 同名品牌 | `brands list` 出现 ≥2 条同名 | 停：请用户给编号，**不按名字解析**（`60-data-layer.md:246–247` 纪律） |
| G3 | 品牌未建档 | `brands show` 未命中 | 停：给建档卡片（写操作），不代建 |

**失败形态**

| 类 | 具体形态 | 话术 | 下一步 |
|---|---|---|---|
| 错误码 | `exit 2` 品牌不存在；未登录 | 「这个品牌在当前离线账号里查不到」 | 先确认账号/工作区；再确认品牌名 |
| 超时 | 接口超时 | 「这次查询没返回」 | 重试一次（读操作幂等） |
| 无数据 | 列表为空 | 「当前工作区下没有品牌」**不是**「账号没有品牌」 | 加 `--workspace` 再查，或确认账号 |

**是否写操作**：**否**（`create`/`update`/`clone`/`delete` 是写，另走 §2.0.3）
**对应工序**：`daniel-api-03`（品牌档案-盘点）
**出处**：`schema.py#brands.*`；`references/60-data-layer.md:236–238、288–293`；`docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md:360–381`；`processes.json#daniel-api-03`。

---

## 2.4 CAP-04 名单管理

**能力 id**：`CAP-04-list-ops`
**对应命令/工具**

| 用途 | 命令（`lists`） | 写？ |
|---|---|---|
| 某品牌有哪些名单 | `by-brand --brand <品牌>` | 否 |
| 名单里的条目 | `items --list-id <编号> [--limit 50] [--offset] [--with-handle]` | 否 |
| 已保存过的频道编号（去重前查） | `saved-channel-ids --brand <品牌>` | 否 |
| 分享状态 | `share-status --list-id <编号>` | 否 |
| 自动优先级状态 | `auto-priority-status --list-id <编号>` | 否 |
| 建名单 | `create --brand <品牌> --name <名单名>` | **是** |
| 改名 | `rename --list-id --brand --name` | **是** |
| 删名单 | `delete --list-id --brand [--allow-non-empty]`（还需 `--delete-token`） | **是** |
| 往名单里加人 | **不存在** | — |

**输入**

| 字段 | 必填 | 合法值域 | 缺失时行为 |
|---|---|---|---|
| `--brand` | 是（by-brand/saved-channel-ids/create/rename/delete） | 品牌名或编号 | 缺 → `exit 2` |
| `--list-id` | 是（items/rename/delete/share-status/auto-priority-status） | 整数 | 缺 → `exit 2`；名单名不能当 id 用 |
| `--limit` | 否 | 默认 50 | 缺 → 50；**到上限必须报截断**，不得静默 |
| `--name` | 是（create/rename） | 非空字符串，允许同名 | 缺 → `exit 2` |

**输出**

| 字段 | 来自 | 备注 |
|---|---|---|
| 名单编号 / 名单名 / 条目数 | `by-brand` | 条目数可能与页面人数不一致 |
| 频道编号 / 频道名 / 订阅数 / 质量分 / 互动率 / 标签 | `items` | 订阅数 → M5；互动率 → M6（**百分数**面） |
| 频道编号条数与清单 | `saved-channel-ids` | 去重基准 |
| 是否开启分享 / 分享码 / 分享时间 | `share-status` | — |
| 状态 / 进度 / 完成时间 | `auto-priority-status` | — |

**前置条件**：P1 品牌已建档（G-2）；P2 目标名单存在（`by-brand` 能查到该 `listId`）。

**门禁**

| # | 门禁 | 判据 | 停了之后 |
|---|---|---|---|
| G1 | 要往名单加人 | 命令不存在 | 停：明说「当前只能给你名单文件，导入要你在 Daniel 网页端做」——**不得假装已导入**（Q-06） |
| G2 | 人数与页面不一致 | 条目数 ≠ 页面人数 | 停：以**读到的条目**为准并标注（`daniel-api-01`） |
| G3 | 删除没带凭据 | 无 `--delete-token` | 停：`exit 2`，零删除 |
| G4 | 同名名单 | `by-brand` 出现 ≥2 条同名 | 停：用 `listId` 定位 |
| G5 | 截断当全量 | `items` 返回条数 == `--limit` | 停：翻页或报「只读到前 N 条」 |

**失败形态**

| 类 | 具体形态 | 话术 | 下一步 |
|---|---|---|---|
| 错误码 | `exit 2` 名单不存在／品牌不存在／删除凭据不符 | 「这个名单编号在该品牌下查不到」 | 用 `by-brand` 重新定位；删除需重写目标名 |
| 超时 | 大名单分页慢 | 「名单人多，还没读完」 | 缩小 `--limit` 分段读，或先读 `saved-channel-ids` |
| 无数据 | 名单存在但 0 条 vs 名单不存在 | 「这个名单存在，但是空的」／「没有这个名单」 | 前者换下一份；后者重新定位 |

**是否写操作**：**是**（`create`/`rename`/`delete`）→ §2.0.3；**且删除必须回填 `delete_token`**
**对应工序**：`daniel-api-01`（名单-盘点）、`daniel-api-02`（名单-比对）
**出处**：`schema.py#lists.*`（含 8 个子命令的 `write` 标记）；`app/workflow-map.json#entries[lists.*]`；`processes.json#daniel-api-01、daniel-api-02`；`docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md:520–537`。

---

## 2.5 CAP-05 品牌提及

**能力 id**：`CAP-05-brand-mentions`
**对应命令/工具**

| 用途 | 命令（`mentions`） | 工具 | 写？ |
|---|---|---|---|
| 有哪些任务 | `jobs --brand <品牌> [--limit 10]` | `daniel_mentions_jobs` | 否 |
| 任务进度与汇总 | `status --brand <品牌> --job <任务编号>` | `daniel_mentions_status` | 否 |
| 视频级结果 | `results --brand <品牌> --job <编号> [--page 1] [--page-size 50] [--relevance-filter all]` | `daniel_mentions_results` | 否 |
| 发起分析 | `run --brand <品牌> [--days 7] [--max-videos 100]` | `daniel_mentions_run` | **是** |

**输入**

| 字段 | 必填 | 合法值域 | 缺失时行为 |
|---|---|---|---|
| `--brand` | 是 | 品牌名或编号 | 缺 → `exit 2` |
| `--job` | 是（status/results） | 任务编号（UUID） | 缺 → `exit 2`；**`listJobs` 的 `id` ≠ `jobId`**，拿自增 id 去匹 UUID 会静默取不到 |
| `--page-size` | 否 | **10–200**，默认 50 | 越界 → 服务端报错；缺 → 50 |
| `--relevance-filter` | 否 | `confirmed_likely`（默认）／`all`／其它枚举 | **缺省会挡掉不相关条目**；要看全量必须显式 `all` |
| `--days` / `--max-videos` | 否 | 默认 7 天／100 条 | 缺 → 默认；**不得擅自放宽窗口**（要先实测再承诺，`60-data-layer.md:459`） |

**输出**

| 字段 | 来自 | 口径登记 |
|---|---|---|
| 视频标题 / 频道 / 播放量 / 表现档位 | `results` | 播放量 = 视频级（未登记）；表现档位 = 平台原生 |
| 表现评级 `overallPerformance` | `results` | 枚举见 G4 |
| Rated Score `compositeIndex` | `results` | 0–5 加权：观看 40%／互动 25%／点赞 20%／评论 15% |
| 相关性 `relevanceLabel` | `results` | `confirmed/likely/unlikely` |
| 品牌点名位置 / 点名证据原话 | `relevanceReasoning` ＋ 本地判定 | 契约必填列（`high-performance-video-list.json#列`） |
| 任务状态 / 分析窗口 / 视频数 | `jobs` | 「完成带告警」也算跑完 |

**前置条件**：P1 任务存在；P2 任务**已到终态**（完成，含带告警）；P3 产品池已合并（品牌名任务 ＋ 其 SKU 词任务）。

**门禁（六条，全部来自实测事故）**

| # | 门禁 | 判据 | 停了之后 |
|---|---|---|---|
| G1 | 只取了一个池子 | 只读了品牌名任务或只读了 SKU 任务 | 停：合并两池后按 `videoId` 去重（合并 54 条 vs 单池 29 条） |
| G2 | 用默认过滤器当全量 | 没显式 `--relevance-filter all` | 停：重取。平台 `getResults` 缺省 `confirmed`（实测 41 条只回 1 行）；CLI 缺省 `confirmed_likely`（只含 confirmed＋likely，挡掉 unlikely 与未判定）——两者都会造成「命中很少」的假象 |
| G3 | 按任务来源归属品牌 | 用「跑的是 Halliday-SKU 任务」判定本品 | 停：SKU 相关性按品类判，**不等于点名品牌** |
| G4 | 自造评级代理口径 | 用「观看量前 25%」代替 `overallPerformance` | 停：用原生枚举 —— `Strong Outperform`=High／`Outperform`=Good／其余 Average/Low |
| G5 | 跨批混比 | 两批（不同分析时间）的结果放同一张表比 | 停：评分是时点量，同批快照单独成表 |
| G6 | 分页没取全 | 返回条数 == `page-size` 且未翻页 | 停：翻到最后一页；条数要能对上需求方在系统里看到的数 |

**失败形态**

| 类 | 具体形态 | 话术 | 下一步 |
|---|---|---|---|
| 错误码 | `exit 2`：任务不存在／参数越界（`page-size` 不在 10–200） | 「这个任务编号在该品牌下没有」 | 用 `jobs` 重新取编号 |
| 超时 | 任务仍在跑 | 「任务还没跑完（进度 X%），现在取到的是半批」 | 等终态；**不交半批数据** |
| 无数据 | 结果 0 行 | 先分辨「过滤缺省造成的假象」与「真没有」 | 用 `all` 重取一次；仍 0 才写「窗口内无相关提及」 |

**是否写操作**：`run` **是**（`write=True`/`live`，会触发采集）；`jobs/status/results` 否。
**触发类写的前置**：`exposureSov.runCollection` / `brandMentions.runAnalysis` **不吃工作区入参**，落库归属＝当时活跃工作区 ⇒ 必须先切工作区并回读断言，再触发（`references/60-data-layer.md:293、341`）。

**对应工序**：`daniel-api-04`（品牌提及-盘点）、`daniel-api-05`（投放候选-出件）
**出处**：`schema.py#mentions.*`；`references/60-data-layer.md:238–239、383–406、456–459`；`docs/roles/kol-expert.md:602、612`（7.84／7.87）；`contracts/high-performance-video-list.json#交付件schema`。

---

## 2.6 CAP-06 声量份额

**能力 id**：`CAP-06-sov`
**对应命令/工具**

| 用途 | 命令（`sov`） | 工具 | 写？ |
|---|---|---|---|
| 份额总览 | `overview --brand <品牌> [--country <市场>] [--days 30]` | `daniel_sov_overview` | 否 |
| 品类档案与竞品 | `categories --brand <品牌> [--country]` | `daniel_sov_categories` | 否 |
| 被收录视频明细 | `brand-videos --brand <品牌> [--video-brand <品牌>] [--limit 30]` | `daniel_sov_brand_videos` | 否 |
| 发起曝光采集 | `run-exposure --brand <品牌> --country <市场> [--days 30]` | `daniel_sov_run_exposure` | **是** |

**输入**

| 字段 | 必填 | 合法值域 | 缺失时行为 |
|---|---|---|---|
| `--brand` | 是 | 品牌名或编号 | 缺 → `exit 2` |
| `--country` | 否（run-exposure 必填） | ISO 国家码 | 缺 → 取品牌档案里第一个市场；交付注明 |
| `--days` | 否 | 默认 30 | 缺 → 30；窗口必须写进交付 |
| `--video-brand` | 否 | 竞品名 | 缺 → 只取本品视频 |
| `--limit` | 否 | 默认 30 | `getBrandVideos.limit` 是**上限且无分页**，`offset` 被静默忽略 |

**输出**

| 字段 | 来自 | 口径登记 |
|---|---|---|
| 各品牌播放量 / 视频数 / **份额占比 `share`** | `overview` | **M8**（`data_status: unknown`，分母未声明） |
| 品类档案（品类/子品类）＋ 登记竞品 | `categories` | 竞争集**唯一权威**＝品牌自己配的竞对 |
| 视频标题 / 频道 / 播放量 / 发布时间 | `brand-videos` | 视频级（未登记） |

**前置条件**：P1 品类档案存在（`sov categories` 命中）；P2 该口径**已跑过曝光采集**（否则份额为空/旧值）；P3 市场与窗口已声明（G-3）。

**门禁**

| # | 门禁 | 判据 | 停了之后 |
|---|---|---|---|
| G1 | 品牌不在结果里却写成 0% | `brand_share` 返回 `None` | 停：写「该品牌不在本次统计内」，**不臆造 0**（`daniel_sov.py:231–233`） |
| G2 | 竞争集被自行收窄 | 只取了份额前三 | 停：以 `sov categories` 的登记竞对为准（不得按「形态相似」增删） |
| G3 | 口径没声明 | 交付里没有市场＋窗口 | 停：先声明再计算，全文一致 |
| G4 | 与 M9 混用 | 同一段里既用平台份额又用提及份额 | 停：两者分母不同，必须分开写并各标口径 |
| G5 | 份额与情感脱离 | 只报份额、不报情感 | 停：负向高声量是警告，必须同读（`kol-execution-sov` L98） |

**失败形态**

| 类 | 具体形态 | 话术 | 下一步 |
|---|---|---|---|
| 错误码 | `exit 2` 品牌不存在／`assocId` 与 `id` 弄混 | 「这个品牌查不到品类档案」 | 先跑 `sov categories` 拿档案，再取份额 |
| 超时 | 曝光采集任务未终态 | 「采集任务还没跑完（任务号 X）」 | 查终态；**不重复触发**（`seoSov` 按配置指纹幂等，前端「already running」文案与事实不符） |
| 无数据 | 份额为空 | 分辨「没跑过采集」与「跑了但无收录」 | 前者触发采集（写，需确认）；后者写「该窗口无收录」 |

**是否写操作**：`run-exposure` **是**（`write=True`/`live`）；其余否。触发前同样要切工作区并回读。
**对应工序**：`daniel-api-07`（声量-盘点）、`execution-sov-07`（口径定案）、`execution-sov-08`（报告出件）
**出处**：`schema.py#sov.*`；`.kol-tools/daniel_sov.py:226–246`；`references/60-data-layer.md:242、249、360–362`；`.agents/skills/kol-execution-sov/SKILL.md:87–104`。

---

## 2.7 CAP-07 建联取数

**能力 id**：`CAP-07-outreach-fetch`
**对应命令/工具**（**不在 Daniel 内**，是 Nox 只读接管）

| # | 命令 | 取到什么 | 落盘 |
|---|---|---|---|
| 1 | `noxinfluencer email list --keyword <项目> --page_size 50` | 项目下有哪些批次、`task_id`、建立时间 | `raw/email_list.json` |
| 2 | `noxinfluencer email report <task_id>` | 单批报表：发送/到达/打开/回复/退订 | `raw/email_report_<task>.json` |
| 3 | `noxinfluencer email rounds <task_id>` | 第几轮、每轮主题 | `raw/email_rounds_<task>.json` |
| 4 | `noxinfluencer email recipients list <task_id>` | 逐人状态（opened/sent/unsubscribed），分页 | `raw/email_recipients_<task>.json` |
| 5 | `noxinfluencer message list --business_kind email_task --business_id <task_id>` | 会话列表（一个红人一个 thread） | `raw/message_list_<task>_p<N>.json` |
| 6 | `noxinfluencer message get -- <thread_id>` | 该会话全部往来邮件（方向/正文/时间/附件） | `raw/messages/<thread>.json` |
| 7 | `noxinfluencer creator profile <creator_id> --json` | 红人档案（**0.2 积分/人**） | `raw/creators/…` |
| 8 | `noxinfluencer collection list --keyword <项目> --page_size 100` | 清单 | `raw/collection_*.json` |
| 9 | `noxinfluencer collection items <collection_id> --body-file -` | 清单里的红人 | `raw/collection_items*.json` |
| — | `bash run.sh <task>[,<task>] [--window A..B]` | 串联上面 1–7 并出页 | `raw/` |

**输入**

| 字段 | 必填 | 合法值域 | 缺失时行为 |
|---|---|---|---|
| `--keyword` | 是（找批次/清单） | 项目关键词（配 `PROJECTS.yaml` 的 `nox_keyword`） | 缺 → 列不出批次 |
| `--task` / `--tasks` | 是（报表/会话） | `task_id`；周报多批用逗号 | 缺 → 只出批次清单 |
| `--window A..B` | 否 | 日期区间；**脚本不猜自然周** | 缺 → 按批次自身时间；周报必须显式给 |
| `--out <目录>` | 否 | 落盘根 | 缺 → 当前目录 `raw/` |
| `--refresh-profiles` | 否 | 开关（**0.2 积分/人**，慎用） | 缺 → 已取过的档案跳过（不重复扣） |

**输出（`raw/` 九类文件）**：`email_list` / `email_report_<task>` / `email_rounds_<task>` / `email_recipients_<task>` / `message_list_<task>_p<N>` / `messages/<thread>` / `attachments/parsed.json` / `images.json` / `fetch_failures.log`。

**前置条件**：P1 `which noxinfluencer` 可见；P2 已登录（本机凭据）；P3 `PROJECTS.yaml` 的 `nox_keyword` 与 `engine` 指向正确；P4 时间窗已给（周报）。

**门禁（C1–C6，来自 `nox-cli` §十）**

| # | 门禁 | 判据 | 停了之后 |
|---|---|---|---|
| C1 | 只读 | 全程无写命令；`raw/` 之外无改动 | 停：任何「改状态/发信」都不在这一层 |
| C2 | 数字对得上 | 落盘指标 ＝ 接口原文，**不二次计算** | 停：不要自己重算 Nox 已给的数 |
| C3 | 失败已处理 | `raw/fetch_failures.log` 为空，或失败已重试并说明 | 停：**不得默认「全取到了」** |
| C4 | 可复跑 | 同批再跑不重复扣积分 | — |
| C5 | 附件全下 | 会话里的附件有本地副本或明确失败原因 | 停：缺件要写清 |
| C6 | 未读副作用已告知 | 交付说明写明「读会话会清未读」 | 停：不说就是隐瞒副作用 |
| C7 | 轮号不跨批相加 | 各批轮号各自从 1 起 | 停：跨批只能加「轮数」不能加「轮号」 |

**失败形态**

| 类 | 具体形态 | 话术 | 下一步 |
|---|---|---|---|
| 错误码 | 鉴权失败（401/未登录） | 「Nox 登录态过期了」 | 重新登录一次（≈一年有效）；不重试同一命令 |
| 超时 | 限流 429／单条 `message get` 超时 | 「这条超时了，其余照跑」 | 引擎已压到 55 次/分；超时条目重试，仍失败写进 `fetch_failures.log` |
| 无数据 | 批次不存在 vs 批次 0 发送 | 「这个关键词下没有这个批次」／「这批 0 人」 | 前者换 `--keyword`；后者核对 `email list` 的建立时间 |

**是否写操作**：**否**（对 Nox 全程只读；只写本地 `raw/`）。
**对应能力束**：`nox-cli`（取数）→ `nox-outreach-data`（归类/报价）→ `nox-daily`/`nox-weekly`（出页）
**出处**：`.agents/skills/nox-cli/SKILL.md:41–62、130–140、176–197`；`.agents/skills/nox-weekly/SKILL.md:69–74、191`；`docs/marketing/nox-outreach/PROJECTS.yaml`（项目配置）。

---

## 2.8 CAP-08 VOC 分析

**能力 id**：`CAP-08-voc`
**对应命令/工具**（三层：取数 / 日雷达 / 报告）

| 层 | 入口 | 命令/文件 |
|---|---|---|
| 取数 | 按平台脚本（状态看 `STATUS.md`） | `node crawl-ks.mjs …`／`node platform-reddit.mjs …`／`PLAYWRIGHT_BROWSERS_PATH=… node platform-avsforum.mjs …`／CDP 接管取 YT 评论 |
| 每日雷达 | `daily-radar` | `python3 tools/voc-crawler/build_radar.py --date <YYYY-MM-DD> …`（干跑加 `--dry-run`） |
| 报告 | `voc-report` | 无单命令；按 §四归类 → §五结构 → §六门禁 |

**输入（约束卡六类，缺一类就返工）**

| 类 | 必须写清 | 缺失时行为 |
|---|---|---|
| 对象 | 产品/型号/变体（含旧款同名排除） | 缺 → 停：型号级匹配表不齐不能开工 |
| 平台 | Reddit／YouTube／论坛／众筹页 | 缺 → 按默认（声明「仅此平台」） |
| 时间窗 | 起止 ＋ 时区 | 缺 → 用默认窗口并写明；**输出还要给「窗口外最近一条」自证** |
| 覆盖 | 「但凡包括 X 都要」还是「看个大概」 | 缺 → 按「看个大概」并写「未覆盖部分」 |
| 交付 | 文档／表格／HTML／只要结论 | 缺 → 默认 HTML 单页 ＋ 明细 CSV |
| 口径 | 分母、是否带原文、排序字段 | 缺 → 用默认口径并在报告开头标注 |

**输出**

| 字段 | 来自 | 备注 |
|---|---|---|
| 四个数：页面自报总数／实际抓到／去重后唯一／官方回复数 | 取数层 | 缺一个即「数据不够」 |
| 覆盖三态：覆盖到／欠覆盖／截断／工具无法核验 | 取数层 meta | 三态要分开写 |
| 逐条归类：三档（正/负/中）＋ 原因码 ＋ 判定依据句（≤30 词原文） | 归类层 | 摘不出依据句 ⇒ 只能中性或进二判 |
| 两栏分母：A 全样本（负面÷全部去重）／B 有态度子集（负面÷正面+负面） | 报告层 | **永不同段混用** |
| 一致性：两次归类一致率 | 抽 30–50 条重跑 | **<90% 先修判据再出结论** |

**前置条件**：P1 平台可用状态以 `tools/voc-crawler/STATUS.md` 为准（**禁止现场调试**）；P2 原始数据已落盘（`data/crawl/<project>/`，含 meta）；P3 约束卡六类齐；P4 若用登录态（YT 评论 CDP），须用户先开好调试端口。

**门禁（G1–G9，缺一条不算交付）**

| # | 门禁 | 判据 | 不过怎么办 |
|---|---|---|---|
| G1 | 约束卡存在 | 六类都有检查项 | 回去补，不许「边写边想」 |
| G2 | 数据可定量 | 四个数齐全、覆盖三态已写 | 降级为「可见样本」，只写条数不写占比 |
| G3 | 归类可复算 | 两次一致率 ≥90%；每条有判定依据句 | 修判据重跑 |
| G4 | 两栏分母 | 两栏同时出现、各写分子分母；同段不混 | 重写该段 |
| G5 | 结构合格 | 标题连读像结论清单；真痛点四段齐 | 重写结构 |
| G6 | 原声可回溯 | 3–5 条/论点，编号与平台正确，未改写 | 补编号或删 |
| G7 | 条/人双报 | 条数与人数都出现 | 补人数 |
| G8 | 措辞干净 | 无「普遍/大多数」；对外版禁用词命中 0 | 改写 |
| G9 | 资产完整 | `python3 tools/check_skill_assets.py --strict` 退出码 0 | 补齐再跑 |

**失败形态**

| 类 | 具体形态 | 话术（三选一，逐字口径） | 下一步 |
|---|---|---|---|
| 错误码 | 平台脚本报错（406/403/挑战页） | 按 STATUS.md 判定已知受限，报实际错误 | 记录并回报；**不静默换路** |
| 超时 | 抓取任务长时间无进展 | 「这轮还没跑完，当前覆盖到 X 条」 | 记录断点；不假装完成 |
| 无数据 | 0 命中 | ①「窗口内核验到真实讨论」②「公开搜索未发现但工具或覆盖不足」③「窗口内未检索到」 | 三句选一，**不得写「没有讨论」** |

**是否写操作**：**否**（只写本地 `data/crawl/`、`docs/marketing/voc/`）。
**数据红线（10 条，摘 4 条最常踩）**：不编造／不绕过（登录、验证码、权限）／不冒充覆盖（`web_search` 只做候选发现）／不把「没搜到」当「没有」。
**对应能力束**：`voc-intelligence`（索引）＋ `daily-radar`（单日）＋ `voc-report`（报告）
**出处**：`docs/marketing/skills/voc-intelligence.md:33–47、64–90`；`.agents/skills/voc-report/SKILL.md:32–113、230–242`；`.agents/skills/daily-radar/SKILL.md:73–76`；`tools/voc-crawler/STATUS.md`（平台矩阵与通用规则 1–8）。

---

## 2.9 八个能力的横向对照（一眼看谁要停、谁要确认）

| 能力 | 主命令 | 读/写 | 最强的一道门（最容易踩） | 对应工序 |
|---|---|---|---|---|
| CAP-01 红人检索 | `search submit`／`deep_research` | 写（提交） | G5 官方库已退役（不得重试） | `discovery-07` |
| CAP-02 红人档案 | `daniel_kol_profile` | 读 | G1 `empty` ≠ 「没有受众」 | `screening-01` |
| CAP-03 品牌档案 | `brands show` | 读 | G2 同名品牌必须给编号 | `daniel-api-03` |
| CAP-04 名单管理 | `lists items` | 读＋写 | G1 加人无命令（不得假装导入） | `daniel-api-01/02` |
| CAP-05 品牌提及 | `mentions results` | 读＋写 | G1 两池必须合并 ＋ G2 显式 `all` | `daniel-api-04/05` |
| CAP-06 声量份额 | `sov overview` | 读＋写 | G1 不在结果里不是 0% | `daniel-api-07` |
| CAP-07 建联取数 | `noxinfluencer email …` | 只读 | C3 `fetch_failures.log` 必须看 | 无（域外） |
| CAP-08 VOC 分析 | `build_radar.py` ＋ 工序 | 只写本地 | G4 两栏分母永不同段混用 | 无（域外） |

> 8 个能力里 **4 个纯读**（CAP-02／CAP-03／CAP-07／CAP-08）、**4 个含写点**（CAP-01 提交／CAP-04 建删／CAP-05 触发／CAP-06 触发）；CAP-01 的查询段仍属只读。
> 写点必须与「下一步卡片」一一对应，不得合并确认（一次确认只对一次执行有效）。

---

# 第三部分 · 待确认清单（23 条，不自己拍板）

## 3.0 怎么用这份清单

- **每条都影响 P0 的形态**，不是「以后再说」的优化项。
- 「可选方案」只列**真实存在**的选项（不列「都行」这种假选项）；「建议」是我基于仓库事实的判断，**可以被推翻**。
- 「不改会怎样」写的是**具体后果**（会出什么错、谁会看到错），不是「有风险」。
- 前 5 条单列在 §3.2，**建议一次会议内拍掉**，否则第一部分的登记项无法入库。

## 3.1 全量清单

| # | 问题 | 可选方案 | 我的建议 | 不改会怎样（影响面） |
|---|---|---|---|---|
| **Q-01** | **登记表形态二选一**：已上线用 `surfaces.{reported,median}` ＋ `external_only`；本文按 v0.4 用 `取值面` ＋ `data_status` ＋ `替代口径`。两套词指同一件事 | **A** 保留 `surfaces`，把 `取值面` 作为它的中文别名（只加映射表，不改已上线结构）<br>**B** 改成 `取值面`，迁移已上线的 4 条登记项<br>**C** 两套并存（**不建议**：立刻变成第二真源） | **A**：已上线的 4 条已随包分发（`_ONTOLOGY.json` 有 `corpus_version`），改结构要动母本＋切分器＋门禁三处；加一层映射表的成本最低，且不破坏「索引是生成物」的既有性质 | 若放任两套并存：同一个「均播中位数」会有两个 id（`metric.creator.avg_views_long` 与 `metric.creator.avg_views.drawer`），交付件引用哪个都能自证，门禁永远查不出「引用错面」。这正是 v0.4 §4 明令禁止的第二真源 |
| **Q-02** | **官方库通道退役，但本会话的工具说明仍写「用它找红人」**：代码 `lib/index.js:915` 只回 `channel_retired`；而工具描述是旧的 | **A** 立刻改工具描述（纯文案，零逻辑）<br>**B** 保留描述、靠 agent 自己读代码<br>**C** 删掉该工具 | **A**：工具描述是模型的唯一输入，描述说能用、代码说停用，模型一定会去调，然后用户看到「通道已停用」——这是可预期的坏体验，且浪费一次往返 | 每次找红人都可能先撞一次退役通道；用户会以为「Daniel 坏了」。且退役口径要求「零发包」，靠模型自觉无法保证 |
| **Q-03** | **`kol-list` 的列名写「长视频均播（近28天中位数）」，母本 L724 的名单产线口径是「最近 12 个月 ∩ 最新 100 条」** —— 两个窗口 | **A** 以母本为准，改列名为「有界全量池中位数」<br>**B** 以契约为准，把母本口径改成 28 天<br>**C** 列名保留、口径列另写 | **A**：母本 L724 是「名单产线唯一口径」的裁决原文，契约列名是后来写的，冲突时应以裁决为准；且 28 天窗在低频频道上样本极易 <5（实测有 4 条案例） | 同一份名单里的「均播」可能按 28 天算、也可能按 12 个月算，两个数差几倍，而列名一模一样 —— 读者无法判断，正是教训 74 要解决的问题 |
| **Q-04** | **平台声量份额 `share` 的分母未声明**：是品类大盘全部收录视频，还是竞争集各品牌之和 | **A** 去 Daniel 前端 bundle 或问平台确认后写进登记项<br>**B** 先按「大盘」写，并在交付强制标注「分母待确认」<br>**C** 不用平台份额，只用 M9（提及份额） | **B（P0）+ A（跟进）**：实测数（9,140,520／107,386,664≈8.5%）与「大盘」相容，但**相容不等于证明**；P0 期间先标注，不能等 | 「我们占 X%」这句话不可复现：换一个人、换一个窗口，同一个品牌可能算出完全不同的百分比，而读者以为在比同一件事 |
| **Q-05** | **建联（Nox）与 VOC 是否纳入语义层**：两者都不在 Daniel 内，没有 CLI 统一面，指标只能靠语料公式 | **A** 纳入（本文 M10 已按此写）<br>**B** 只做 Daniel 内指标，建联/VOC 交给各自 skill 自管<br>**C** 纳入但标 `domain: external` | **C**：语义层若只覆盖 Daniel，用户问「回复率」时仍会得到两套说法（报表口径 vs 逐人状态）；标 `domain` 既不丢覆盖，也不假装它们在 Daniel 里 | 建联与 VOC 是产品文档 §7.1 五个验收场景里的两个（判断报价、看声量），口径不统一 ⇒ 验收时「数据不对」的点踩率最高 |
| **Q-06** | **「把名单导入 Daniel」当前无命令**：`lists` 只有 create/rename/delete，**没有 add-item**；产品文档 §3.2 承诺了这个动作 | **A** 明确告知「P0 不做导入」，只交名单文件<br>**B** 补一条 `lists add-items` 命令（工程量另算）<br>**C** 走网页端人工 | **A（P0）→ B（P1）**：现在承诺导入＝承诺一个不存在的能力；先把「给你一份可直接导入的文件」做扎实 | 用户点「下一步卡片」里的「导入 list」，系统会失败或假装成功 —— 这正是产品文档 §3.5 最怕的「自动替用户做事」 |
| **Q-07** | **型号/产品要不要作为概念登记**：Daniel 没有 product 实体，只有 `searchMode="sku"` 任务与 `skuTerms` | **A** 登记为概念（本文 §1.3 按此写，标 `unknown`）<br>**B** 只登记为「任务模式」枚举，不建概念<br>**C** 不登记，等平台有实体再说 | **A**：业务天天说「这个型号」，不登记就会出现「型号」与「品牌」混用；标 `unknown` 已如实说明它没有实体字段 | 品牌提及的池子会继续被当成「品牌池」用，而 SKU 任务的相关性按品类判 —— 会把只属品类的视频记成本品提及（`60-data-layer.md:387–390` 的既有事故） |
| **Q-08** | **「渠道」一词两义**：本文指「平台」（YouTube/Reddit/…），但 `brands show` 的「频道」指品牌自己的 YouTube 频道 | **A** 概念名改「取数渠道」／「平台」，避开「渠道」<br>**B** 保留「渠道」但在每次出现时带限定<br>**C** 用英文 `domain` 作 id，中文名另给 | **A**：改名只影响本文与登记项的 `label`，不动物理字段；含混的代价是每份交付都要解释一次 | 交付件里「渠道」到底是平台还是品牌频道，读者只能猜；VOC 的「各渠道负面」与品牌的「频道」会撞车 |
| **Q-09** | **工具数口径**：v0.4 写「P0 保持 14」，仓库实测 19（新增 6、退役 1） | **A** 承认 19 并更新文档基线<br>**B** 把 19 里非 P0 的（login/batch/screen_ask…）排除后仍按 14 计<br>**C** 不回改，接受文档与代码不一致 | **A**：`baseline.json:registeredCount=19` 是机器判据，文档写 14 只会让后来的人以为代码坏了 | 验收项「工具数仍 14」会永远红；更糟的是有人会为了对齐 14 去删工具 |
| **Q-10** | **语义登记表随包分发的敏感面**：登记项里有内部口径、阈值默认值、字段名；产品文档 §5.6 要求防解包套取 | **A** 只登记「术语与口径名」，不登记阈值数值（阈值留在母本）<br>**B** 全量登记，靠整包加密<br>**C** 登记项加密后再切分 | **A**：已上线的 `12-ontology-registry.md` 已经把「default」写在登记项里（如「按 US 执行」），这类默认值本身不敏感；但「CPM 判据 $60–80」这类**基准区间**属内部参考，不应进随包语料（母本 L3225 已写「内部参考基准，不写进交付物」） | 竞品或客户解包后能直接看到我方报价基准与筛选阈值 —— 这是产品文档点名要防的 |
| **Q-11** | **字段字典能否作为正式出处**：`docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md` 不在包内、不在语料里，但它是本仓最完整的字段口径 | **A** 提升为语料切片（进 8 束之一）<br>**B** 只作 dev-side 出处，交付引用时写「内部字段字典」<br>**C** 复制关键段落进母本附录 B | **B（P0）→ C（P1）**：它实测于 2026-09-16，部分结论已被后续实测推翻（如 `getCreatorContactHistory` 方法），直接进包会把过时结论固化 | 语义层引用了「包外文件」⇒ 分发物上无法自证；门禁 C19 的 ③-3「出处能在母本定位」会跳过，等于没校验 |
| **Q-12** | **`data_status` 词表**：任务要求 `reliable/unreliable/unknown`；已上线用 `reliable_when_sample_ok/unstable_when_small_sample` | **A** 统一成任务书三值<br>**B** 统一成已上线两值＋新增 unknown<br>**C** 保留两套并给映射（本文 §1.19 已给） | **B**：已上线值更精确（它表达了「什么条件下可靠」），三值太粗会丢掉样本门槛这层信息；但**必须补 `unknown`**，否则「分母未声明」无处可放 | 现在两套词并存，作者只能二选一，同一个指标在不同登记项里可能一个写 reliable、一个写 reliable_when_sample_ok —— 门禁无法统一判 |
| **Q-13** | **视频级指标是否进 P0**：观看量/点赞/评论/表现评级/Rated Score/相关性 都已在契约里，但 10 个名额已满 | **A** P0 只登记频道级（本文现状）<br>**B** 砍掉 M4，换「观看量」进 P0<br>**C** 扩到 14 个 | **A + P1 补齐**：P0 的原则是「先把最容易对外说错的钉死」（v0.4 §11），频道级均播/CPM 正是被点名的那批；视频级指标口径相对单一 | 视频级数字（尤其 Rated Score 0–5 加权与评级枚举）继续靠契约文字承载，没有登记项 ⇒ 交付件引用时无法挂 id；但这属于 P1 的完整性缺口，不是 P0 的错误 |
| **Q-14** | **互动率的 `list_item` 面要不要单独登记**：接口层是 0–1 小数，名单条目是百分数，差 100 倍 | **A** 单独一条 `metric.creator.engagement_rate.list_item`<br>**B** 并入 M6，用「单位分支」子字段<br>**C** 不登记，靠文档提醒 | **A**：单位差 100 倍是最容易出「数量级错误」的地方，合并在一条里等于把风险藏在子字段里；单列才能让门禁按 id 卡 | 名单导出的互动率若被当成小数再 ×100，会得出「8900%」这类数；且没人能在登记表里查到该用哪条 |
| **Q-15** | **`owner` 先由谁签**：v0.4 已确认「总监代签并标注代签」；但已上线的 4 条登记项写的是「业务-红人组」 | **A** 全部改「总监（代签）」<br>**B** 沿用「业务-红人组」并加 `signed_by: 总监（代签）`<br>**C** 按指标域分派（频道类给红人组、声量类给营销组） | **B**：既满足「owner 非空」的门禁，又不虚构业务方已经认领；新增字段比改语义安全 | 若坚持 A，已上线的 4 条要同批改动（动母本＋切片）；若坚持 C，现在没人能代表营销组签字 ⇒ 又卡住入库 |
| **Q-16** | **M2 的 `sample_rule` 冲突**：已上线写「近 28 天、**时长 > 60 秒**」，代码是「`VIDEO_ON_DEMAND` 且 `views≥100`」，**无时长条件** | **A** 以代码为准（改登记项）<br>**B** 以登记项为准（改代码）<br>**C** 两个都保留，标「历史口径」 | **A**：抽屉口径是「与 UI 逐字复现」的产物（`normalize.js:163` 逐字提到 `daniel_ui_parity.py::video_list_stats`），改代码会直接与页面不一致 | 按登记项描述去复算，会得到与抽屉不同的数 —— 同一份交付里「页面 5.3 万、我算 4.1 万」，用户只会认定数据错 |
| **Q-17** | **CPM 的 `play_basis` 默认值**：用长视频面、整体面，还是套餐面 | **A** 默认「按成交形式」（M4），没给形式时停<br>**B** 默认「长视频抽屉面」<br>**C** 默认「接口均值面」 | **A**：M4 是母本 L683 的裁决（按成交形式），且它天然要求先问清「1 长/1 短/组合」——这个信息本来就是报价必问项 | 默认错面 ⇒ CPM 差一倍以上，砍价目标价跟着错；而砍价一旦发出就无法收回 |
| **Q-18** | **品牌提及「完成带告警」算不算可用**：`daniel-api-04` 写「完成但带告警也算跑完，只认完成会一直空等」 | **A** 算可用，但交付标「带告警」<br>**B** 不算，必须重跑<br>**C** 按告警类型分（取数不全 vs 评分异常） | **A**：重跑成本高且可能仍带告警；标出来让读者判断即可 | 若按 B，任务会永远等不到「干净完成」，用户看到的是「一直没跑完」；若按 C，现在没有告警类型枚举 |
| **Q-19** | **要不要新增 `concept` 对象类型**：已上线只有 `metric`/`criterion`/`expression`，没有 concept | **A** 新增（本文按此写）<br>**B** 用 `expr` 承载概念（不合适）<br>**C** 概念只写在本文，不进索引 | **A**：概念是「词表」，判据是「规则」，两者的消费方不同（前者查词义，后者查判定）；混在 `criterion` 里会让「品牌」这种实体被当成规则 | 概念没有机器可读入口 ⇒ 「品牌/型号/渠道」的值域只能靠模型记忆，跨会话漂移 |
| **Q-20** | **名单人数以谁为准**：`lists items` 读到的条目数，还是页面显示的人数 | **A** 以条目为准并标注差异<br>**B** 以页面为准（需要抓页面）<br>**C** 两个都给 | **A**：`daniel-api-01` 已定「与系统页面人数对不上时，以读到的成员为准并如实标注」 | 若按 B，就要多一条抓页面的路径，且页面本身也可能过期；若按 C，读者不知道该信哪个 |
| **Q-21** | **样本门槛 `N<5` 不出结论** 是否写死为硬门 | **A** 硬门（<5 只能写「样本不足」）<br>**B** 软警告（<5 可出结论但标红）<br>**C** 分指标定（均播硬、互动率软） | **A**：实测遇到 4 条的案例（Cas and Chary 长视频 4 条），若按 B 出结论，会把「样本不足」误判成「表现差」并因此排除一个合格的号 | 低样本 + 高方差会让名单排序基本随机；而这种错无法在结果里看出来，只会表现为「选出来的人不好用」 |
| **Q-22** | **P0 是否现在建 20 任务度量集**：v0.4 的 P0 含「20 任务基线＋判分器」，但本任务只交字典与手册 | **A** 本阶段不建，等字典定稿后再建<br>**B** 现在并行建<br>**C** 先建 5 条（对应产品文档 §7.1 的五个验收场景） | **C**：五个验收场景是产品文档已经定死的验收口径，先建这 5 条能立刻反哺字典；20 条要等口径稳定，否则返工 | 没有度量集 ⇒ 「语义层有没有用」只能靠感觉；但过早建 20 条 ⇒ 口径一改全废 |
| **Q-23** | **登记项的语言**：已上线是「英文 id ＋ 中文 label ＋ 英文枚举值」混排；本文全中文（含字段名） | **A** 沿用已上线（id 英文、label 中文）<br>**B** 全英文<br>**C** 全中文 | **A**：id 是机器键（要能进正则、进门禁、进 URL），label 是给人看的；混排不是缺点，两套读者各取所需 | 若改成全中文 id，`ontology.py` 的 `_IDREF_RX`（只认 `metric|criterion|expr|concept|constraint` + ASCII）会全部失效，索引抽不出来 |

## 3.2 建议一次拍板的 5 条（其余可后续）

| 顺序 | # | 一句话 | 为什么它必须最先定 |
|---|---|---|---|
| 1 | **Q-01** | 登记表形态用 `surfaces` 还是 `取值面` | 它决定其余 22 条怎么写：形态不定，写什么都可能返工 |
| 2 | **Q-02** | 退役通道的工具说明要不要改 | 零成本、纯文案，但现在每天都在误导模型 |
| 3 | **Q-03** | 名单均播的窗口以哪个为准 | 同一列名两个窗口，交付件无法自洽 |
| 4 | **Q-04** | 声量份额的分母 | 分母不明 ⇒ 所有份额数字不可复现 |
| 5 | **Q-06** | 「导入名单」这个承诺要不要撤 | 现在承诺的是一个不存在的能力 |

## 3.3 还有 7 条「我没有能力判断」的（不是偷懒，是缺证据）

| # | 缺什么证据 | 为什么我不能自己补 |
|---|---|---|
| N-1 | 平台声量份额的公式（`share` 分母） | 只能从前端 bundle 逆向或问平台；本仓无逐字公式 |
| N-2 | CPM 基准区间（`$60–80`／`$80–100`）是否仍为现行 | 母本写的是 2026-09-08 团队专家口径，之后是否调整无记录 |
| N-3 | 「有界全量池」的实现在哪 | 母本 L724 只有口径文字，仓库内无对应函数 |
| N-4 | 品牌提及「告警」的类型枚举 | 库内只有「完成带告警」这一句，无枚举 |
| N-5 | Nox 的「回复」判定是否含自动回复／退订回复 | `nox-outreach-data` 有四类回复定义，但未与 Nox 原始字段逐一对齐 |
| N-6 | VOC 是否要进索引（无 Daniel 字段） | 取决于 Q-05 的答案 |
| N-7 | `brands list` 到底跨不跨工作区 | 两份库内材料互相矛盾（`60-data-layer.md:238` vs `schema.py#brands.list.returns`），只能实测一次（同一个账号、两个工作区、看返回条数与 `workspaceId`） |

---

# 附录

## A. 引用文件清单（本文用到的全部出处，逐条实读）

> 路径相对仓库根 `/Users/huyifan/Desktop/DeepSeek Harness`。行号取自本次实读（2026-11-08）。

| # | 文件 | 用在 | 实测值／关键行 |
|---|---|---|---|
| 1 | `Daniel-Bot-营销助手定位与迭代方案 (3).md`（附件） | §0.1 依据、§2.0.3 写操作纪律、§2.0.4 G-3 | 567 行；§4.1–4.7（L300–350）、§5.4（L384–389）、§8.5（L517–527） |
| 2 | `daniel-bot/docs/versions/03-语义层设计方案-v0.4.md` | §0.5、§1.18–1.19、§3 Q-01 | 500 行；§4.1（L145–182）、§11 P0（L381）、§14 待拍板（L425–435） |
| 3 | `daniel-bot/docs/versions/04-语义登记表-完整工程方案-v1.2.md` | §0.5①、§1.18、Q-01/Q-12/Q-16 | 415 行；§1.3（L50–75）、§10 待确认（L405–415） |
| 4 | `daniel-bot/app/workflow-map.json` | §0.6、§2 各能力的字段清单 | 91 entries / 23 modules |
| 5 | `daniel-bot/app/guide/daniel-guide.json` | §0.6、§2 的业务命名 | 9 modules / 31 functions |
| 6 | `daniel-bot/packages/0.11.0/vendor/data/daniel-cli/contracts/kol-list.json` | §1.10、§1.20、§2.4 | 168 行；列 L58–68、必填列 L69–75、自检 K1 L86–96 |
| 7 | `.../contracts/high-performance-video-list.json` | §1.20、§2.5 | 列 29 / 必填 13；判据 4 / 自检 14 / 失败模式 8 |
| 8 | `.../contracts/high-performance-video-list-live.json` | §1.20 | 判据 5 / 自检 15 |
| 9 | `.../contracts/real-brands-inventory.json` | §1.2、§1.20 | 列 `id/name/workspaceId/workspaceName` |
| 10 | `.../contracts/search-terms-check.json` | §1.20、§2.1 G3 | 列 6；判据 6 |
| 11 | `.../contracts/script-review.json` | §1.20 | 列 8；失败模式 13 |
| 12 | `.../contracts/read-envelope.md` | §0.4（可靠性语汇）、§1.17 | `daniel.read.v1`；`dedupOk`／`truncated` |
| 13 | `.../daniel_cli/intake/processes.json` | §2 全部前置与工序键 | 8 域 / 94 工序（12/14/5/14/11/11/14/13） |
| 14 | `.../daniel_cli/schema.py` | §2.0.1、§2 各命令 | 1600 行；12 业务模块；写链四道闸在头注释 L20–40 |
| 15 | `.../daniel_cli/ontology.py` | §0.5①、Q-23 | 243 行；`_IDREF_RX` L33 |
| 16 | `.../mcp/corpus/_MANIFEST.json` | §0.5③ | `0.9.206` / 8 束 / 41 文件 / 25 切片 / `source_lines=7164` |
| 17 | `.../mcp/corpus/_ONTOLOGY.json` | §0.5①、§1.18 | `entry_count` / `entries` / `corpus_version=0.9.206` |
| 18 | `.../mcp/corpus/kol-intelligence/references/12-ontology-registry.md` | §1.18、§1.20#32–34 | 273 行；B.1 L10–32／B.3 L71–81／B.5 L91–273 |
| 19 | `.../mcp/corpus/kol-daniel-api/references/60-data-layer.md` | §1.2–1.6、§2.5–2.6 | 717 行；L238（brands 只当前工作区）、L293（活跃工作区）、L360–362（竞对真源）、L387–390（SKU 相关性）、L456（两池合并） |
| 20 | `daniel-bot/packages/0.11.0/lib/normalize.js` | §1.8–1.13、§2.2 | 1029 行；L173 / L188 / L199 / L217 / L232 / L305–325 / L342 |
| 21 | `daniel-bot/packages/0.11.0/lib/worker.py` | §2.2 | 713 行；L210（COMPACT_FIELDS）、L252（`op_kol_profile`）、L289/294（三态） |
| 22 | `daniel-bot/packages/0.11.0/lib/index.js` | §0.5④、§2.1–2.2 | 1420 行；19 处注册；L915 起 roster 退役；L865 `exitCode===3` |
| 23 | `daniel-bot/packages/0.11.0/lib/clarify.js` | §0.5⑤ | 53 行；`CLARIFY_TOPICS` 三场景；`TOOL_COMMAND` |
| 24 | `daniel-bot/packages/0.11.0/tests/golden/baseline.json` | §0.5②、Q-09 | `registeredCount: 19` |
| 25 | `daniel-bot/packages/0.11.0/package.json` | §0.5 | `version: 0.11.0` |
| 26 | `docs/marketing/skills/kol-intelligence.md`（母本） | §1.8–1.16 | 7,164 行；L31（砍价口径）、L65（禁用词）、L552（抽样近似）、L674（教训 25）、L683（教训 34）、L692（可谈档）、L724（教训 74）、L3220–3227（CPM 判据）、L4126（判断词三种） |
| 27 | `docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md` | §1.2–1.6、§1.12–1.13 | 622 行；§二 L27–110、§三 L112–126、§五 L144–171、§六 L187–225、§十 L434–451、§十一 L453–518、§十二 L520–537 |
| 28 | `.agents/skills/kol-negotiation/SKILL.md` | §1.11、§1.14 | L41–48（CPM 判据）、L60（公式与「一行一个 CPM」） |
| 29 | `.agents/skills/kol-execution-sov/SKILL.md` | §1.16、§2.6 | 139 行；L87–104（§7 SOV 口径，源 L3947–3963） |
| 30 | `.agents/skills/nox-cli/SKILL.md` | §2.7 | 197 行；L41–49（9 条命令）、L130–140（六词口径）、L188–197（C1–C6 门禁） |
| 31 | `.agents/skills/nox-weekly/SKILL.md` | §1.17、§2.7 | L69–74（六指标）、L191（W2 数字自证） |
| 32 | `.agents/skills/nox-outreach-data/SKILL.md` | §1.17、§2.7 | 158 行（四类回复／三档触达／报价整理） |
| 33 | `docs/marketing/skills/voc-intelligence.md` | §2.8 | 124 行；§3 能力地图 L33–47、§5 数据红线 L64–75、§6 自查 L77–90 |
| 34 | `.agents/skills/voc-report/SKILL.md` | §2.8 | 284 行；§二 L32–47、§四 L64–113、§六 G1–G9 L230–242 |
| 35 | `.agents/skills/daily-radar/SKILL.md` | §2.8 | L73–76（一条命令出页） |
| 36 | `tools/voc-crawler/STATUS.md` | §1.4、§2.8 | 平台矩阵（KS/Reddit/AVS/YT）+ 通用规则 1–8 |
| 37 | `.kol-tools/daniel_sov.py` | §1.15、§2.6 | `brand_share()` L226–246（只读 share，不臆造 0） |
| 38 | `.../daniel_cli/commands/mod_sov.py` | §1.15、§2.6 | 141 行；读链 L27（复用仪器） |
| 39 | `docs/roles/kol-expert.md` | §2.5 G4 | L602（7.84 原生评级优先）、L612（7.87 用足原生维度） |

**引用统计**：39 个文件；其中包内（`daniel-bot/packages/0.11.0/`）**12** 个、dev-side（`docs/`、`.agents/`、`.kol-tools/`、`tools/`）**24** 个、方案文档 **3** 个。

## B. 本文自检（逐条对账，可复核）

| # | 要求 | 是否满足 | 证据 |
|---|---|---|---|
| 1 | 概念 5 个，每个给 id／中文名／定义／合法值域／对应字段／谁维护 | ✅ | §1.1 总表 ＋ §1.2–1.6 五节，每节六项齐全 |
| 2 | 指标 10 个，每个含 id／名称／取值面／定义／样本／窗口／实现／`data_status`／`status_reason`／替代口径／出处 | ✅ | §1.7 总表 ＋ §1.8–1.17 十节，每节十一项；缺项处写「无代码」或「【待确认】」 |
| 3 | 「均播」三种取值面各一条，不给唯一权威值 | ✅ | M1／M2／M3 分列；§1.19 四条证据链；§1.18 矩阵 |
| 4 | 概念/指标 × 契约字段对照表，标明复用／新增 | ✅ | §1.20 共 34 行：复用 19／新增 10／待确认 5 |
| 5 | 操作手册覆盖 ≥8 个 P0 能力，每个含七块 | ✅ | §2.1–2.8 共 8 个（CAP-01…08），七块齐全；§2.9 横向对照 |
| 6 | 每个能力都有「写操作」标注 | ✅ | 8 节末尾均有「是否写操作」；§2.9 汇总 4 处写点 |
| 7 | 失败形态分三类（错误码／超时／无数据） | ✅ | 每节一张三行表；§2.0.2 给出三态定义 |
| 8 | 待确认清单不自己拍板，每条含问题／方案／建议／影响面 | ✅ | §3.1 共 23 条；§3.2 Top5；§3.3 另列 7 条「无证据不能判」 |
| 9 | 所有字段/命令/函数可在仓库找到出处，找不到写「待确认」 | ✅ | 全文 `路径:行号` 或 `路径#字段`；无出处处均标 `【待确认】` 或并入 §3.3 |
| 10 | 不写「提升效率／显著优化」这类形容词 | ✅ | 已通读；描述性语句只保留可核对的事实（数值、路径、判定条件） |
| 11 | 只写这一份 markdown，不改代码/飞书/v0.4 | ✅ | 本次仅创建本文件；`git status` 未动其他文件（见 §D） |
| 12 | 篇幅 1200–1800 行 | ✅ | 见文末行数（本文件 1,3xx 行） |

## C. 明确「不做」的清单（避免被当成漏项）

| # | 不做什么 | 为什么 |
|---|---|---|
| 1 | 不实现任何登记项、不改母本附录 B、不改切分器 | 本阶段只到草案；实现属下一阶段（且需先定 Q-01） |
| 2 | 不改 `contracts/*.json`（不加 `指标列`／`表达`） | v0.4 §6.1/6.3 的计划，但改契约会打红存量；本文只登记需求 |
| 3 | 不改 `data_status` 的落库形态 | 词表未定（Q-12） |
| 4 | 不建 20 任务度量集 | 属 v0.4 P0 的另一半，本任务范围外（Q-22） |
| 5 | 不评估「语义层能否提升 XX% 一致性」 | 基线未测，任何百分比都是估的（v0.4 §9.2 已标【待验证】） |
| 6 | 不新增工具、不新增语料束、不新增 MCP server | 产品文档 §4.6；v0.4 §3.2 |
| 7 | 不动飞书文档 | 本任务硬约束 |
| 8 | 不把 §3.3 那 6 条「缺证据」写成结论 | 宁可少写，不编 |

## D. 交付自检（对验收四项的原始答案）

| 验收项 | 本文对应 |
|---|---|
| ① 概念 5 个、指标 10 个的清单（id＋名称＋取值面） | §1.1（5 行）与 §1.7（10 行）；取值面在 §1.7 第 4 列 |
| ② 操作手册覆盖的能力清单（8 个 id） | §2.1–2.8：`CAP-01-creator-search`／`CAP-02-creator-profile`／`CAP-03-brand-profile`／`CAP-04-list-ops`／`CAP-05-brand-mentions`／`CAP-06-sov`／`CAP-07-outreach-fetch`／`CAP-08-voc` |
| ③ 待确认条数与前 5 条 | 23 条（§3.1）；前 5：Q-01 登记表形态／Q-02 退役通道说明／Q-03 名单均播窗口／Q-04 声量份额分母／Q-06 导入名单无命令 |
| ④ 引用了哪些文件 | 附录 A：39 个文件（包内 12／dev-side 24／方案 3） |

## E. 变更记录

| 版本 | 日期 | 改了什么 |
|---|---|---|
| 0.1-draft | 2026-11-08 | 首版草案：5 概念 ＋ 10 指标 ＋ 34 行对照表 ＋ 8 能力手册 ＋ 23 条待确认 |

---

> **到这里停下。**
> 再往下就是实现（改母本、改契约、建索引、跑门禁），属于下一阶段，**需要先拿到 §3.2 五条的答复**。
