---
name: kol-daniel-api
version: 0.9.204
description: "Daniel 平台能力的**接口与工序**：Saved Lists 等读／写（用途、只读探测先行、接口清单、写操作纪律、硬限与坑、Compare Lists、仪器与验收判据、范例路径）、其它区块全链路（Brands／Brand Mentions／Intelligence 核心／SOV 全家桶）、接管验收、工作区隔离协议、凭据与会话落点纪律、品牌提及原生表现评级与广告投放候选清单口径、品牌名单归属判据、名单类交付件字段完整性与排序、原生筛选维度、写链＝权限驱动四轴＋写操作四道闸、§15.5.8 品牌提及／Deep Review 的实测运维事实（13 条：错误语义／分页取全／Rated Score 算式／两标签反推规则／Deep Review 停住）；Creator Tracker 建链（参数表先行、路由清单）；KOL 全链路检索。Use when 要调用或新增 Daniel 数据层能力、跑 Saved Lists／Brands／Brand Mentions／SOV／Creator Tracker、做接管验收或工作区隔离；关键词：Daniel、Saved Lists、Brands、Brand Mentions、SOV、Creator Tracker、接管、工作区、凭据落点、写链权限、运维事实、分页重复、Rated Score。"
whenToUse: "任何要走 Daniel 接口的任务开工前加载；写操作前先过 §15.5.7 写操作四道闸与 §15.4 写纪律。"
metadata:
  corpus_version: "0.9.204"
  corpus_source: "docs/marketing/skills/kol-intelligence.md"
  corpus_sha256: "b82b58cfe969f133dd808146982d96bacaf7af67a2f6a3f22e1feae9de89b986"
  corpus_slices: "L5008-L5721,L5722-L5900,L5901-L6376"
  generated_by: "TICKET-148-语料束切分器.py"
---

# Daniel 系统数据层直连 · Creator Tracker · KOL 全链路检索

> 本束是 `docs/marketing/skills/kol-intelligence.md`（版本 0.9.204）的**逐字切片**：判据原文在 `references/`，本文件只做导航与逐字摘录，**不改写任何判据**。

## 一、本束覆盖的源节

| 切片文件 | 源行区间 | 源节标题（逐字） |
|---|---|---|
| `references/60-data-layer.md` | L5008–L5721 | §15 Daniel 系统数据层直连（含 §15.5.8 实测运维事实） |
| `references/61-creator-tracker.md` | L5722–L5900 | §16 Creator Tracker（红人追踪）建链 |
| `references/62-full-chain-search.md` | L5901–L6376 | §17 KOL 全链路检索 |

> 读法：先看本文件的「核心判据速查」；需要完整判据时按上表 `read` 对应切片。

## 二、核心判据速查（逐字摘录 · 带源行号）

### §15 Daniel 系统数据层直连（含 §15.5.8 实测运维事实）（源 L5008–L5062 逐字摘录）

## 15. Daniel 系统数据层直连（Saved Lists 等读／写）

> **能力地图登记（逐字 · `_CAPABILITY-MAP.json` L156–180）**：`id`＝`daniel-lists`｜`name`＝Daniel 名单级读写（Saved Lists）｜`entry`＝`## 15. Daniel 系统数据层直连`｜`charter`＝`**7.70 Daniel 名单级读写`｜`instruments`＝`.kol-tools/daniel_lists.py`｜`shape`＝Daniel 系统内名单（另可导出 CSV）
> **acceptance**：① 路由与入参以 bundle 实测为准 ② 写后回读核对 ③ 重名拦截 ④ 删除需 `--yes`
> **触发词**：建名单／新建 list／saved list／名单改名／删名单／加人到名单／创建 list／list
> **版本溯源**：Skill **0.9.155** 新增本章（`_CHANGELOG` L115）｜章程 **0.2.117** §7.70（`docs/roles/kol-expert.md` L649–655）｜缺陷类 **CLS-46**（`_DEFECT-CLASSES.md` L59）｜教训 **208**｜TICKET-099（done）

### 15.1 用途与适用面

**用途**：在 Daniel 系统里**直接做名单级操作** —— 列品牌、列名单、建名单、改名、删名单；并可往上叠"往名单加人／读名单成员／比对重叠"（见 §15.3 写路由、§15.6 Compare Lists）。

**适用面**
- 用户说"在 **jack 下的 Halliday** 这个 brand 下，创建一个新的 list，就叫 `agent test list`"这类**名单级**指令；
- 上游全链路检索的落库环节（§17）也走本章的 `lists.create` ＋ `lists.batchAddItems`。

**不适用（边界）**
- **红人追踪（Creator Tracker）不并入本链路**（2026-09-30 用户裁决 · 章程 L637）—— 名单检索与达人合作是**两个独立方向**，各自管理 ⇒ 走 §16；
- 跨账号／跨 workspace 操作：**停下说明，不做跨账号操作**（工作流 02 N10 前置输入）。

### 15.2 工序：**只读探测先行**

> **判据（TICKET-099 L57–58「未实测」段）**：**首次使用照 §15.2 工序先只读探测** —— 已定位但未实测的路由（`batchAddItems`／`updateItemTags`／`mergeLists`／`generateShareLink`／`autoPriority…`）**第一次用先跑一次 GET 只读探测**，不要直接写。

**标准工序**

| 步 | 动作 | 说明 |
|---|---|---|
| 0 | **路由取证**：入口 HTML → `assets/index-*.js` → `import("./X-*.js")` 列 chunk → 到对应 chunk grep 调用点 | **以调用点写出的键为准**（`_DEFECT-CLASSES.md` CLS-46 判据 ①） |
| 1 | **列品牌** `brands.list` → 解析 `brandId`（名字歧义 → 抛错要用户给 id，**不猜**） | `daniel_lists.py` L64–80 |
| 2 | **只读探测**目标路由（GET，零副作用） | 本节判据 |
| 3 | **写**（带 dry-run／--yes 守卫） | §15.4 |
| 4 | **回读核对** | §15.4 第 ③ 条 |

### 15.3 接口清单（路由 ＋ 入参 ＋ 返回要点）

#### 15.3.1 通路与认证（逐字 · `.kol-tools/daniel_client.py` docstring L3–14）

| 项 | 事实 | 行号 |
|---|---|---|
| 站点 | `https://daniel-agent.com` | `daniel_client.py` L23 |
| 数据层 | 前端是 React SPA，数据层为 **tRPC**（同源 `/api/trpc`），**非 tRPC REST** | L7 |
| 登录路由 | **`auth.login`（mutation）** | L7 |
| 会话 | 登录成功以 `set-cookie: app_session_id=<JWT>` 维持会话（**1 年有效**），后续请求带该 cookie 即可 | L8 |
| 读类路由 | **GET**：`/api/trpc/<route>?batch=1&input=<urlencoded {"0":{"json":<input>}}>` | L9 |
| 写／登录类 | **POST**：body `{"json": <input>}`（含 `meta.values` 处理 Date 字段，**本项目用不到**） | L10 |
| 响应形态 | GET → `[{"result":{"data":{"json":…}}}]`；POST → `{"result":{"data":{"json":…}}}` | L11 |
| 凭证纪律 | 账号密码从环境变量 `DANIEL_EMAIL`／`DANIEL_PASSWORD` 或 `.daniel_cred.json` 读取（**勿入库**），**脚本内不硬编码明文**；会话 cookie 缓存到 `.kol-tools/.daniel_session.json`（含 JWT，**勿外发**） | L13–14 |

**实现要点（逐字 · `daniel_client.py`）**
- `query(route, inp=None)`：`inp=None` 时传 `{"json": null}`（L103）；响应若为 list 取 `[0]`（L112–113）；`"error"` 键存在即抛（L114–115）；取 `data["result"]["data"]["json"]`（L116）；失败重试 **3 次**，退避 `1.2*(k+1)` 秒（L107、L121），命中 `UNAUTHORIZED` → `login(force=True)`（L119–120）。
- `mutate(route, inp=None)`：POST `/api/trpc/<route>`，body `{"json": inp}`（L125、L129–130）；同样取 `result.data.json`（L135）；重试 **3 次**（L127、L138）。
- `whoami()`：`auth.me` → `.email`（L88）。
- 会话文件权限 `0o600`（L60）。

#### 15.3.2 读路由

> ⟪摘录止于 L5062；`references/60-data-layer.md` 尚有 L5063–L5721 未摘录⟫

### §16 Creator Tracker（红人追踪）建链（源 L5722–L5776 逐字摘录）

## 16. Creator Tracker（红人追踪）建链

> **能力地图登记（逐字 · `_CAPABILITY-MAP.json` L181–205）**：`id`＝`daniel-campaign`｜`name`＝Creator Tracker 建 campaign（红人追踪）｜`entry`＝`## 16. Creator Tracker`｜`charter`＝`**7.71 Creator Tracker 建链`｜`instruments`＝`.kol-tools/daniel_ct.py`｜`shape`＝Daniel 系统内 campaign
> **acceptance**：① 口语输入自动归一 ＋ 回显 ② 结束日期与 Evergreen 互斥 ③ 频道给 `UC…` ID ④ 写后回读
> **触发词**：campaign／建 campaign／红人追踪／creator tracker／追踪项目
> **版本溯源**：Skill **0.9.156** 新增本章（`_CHANGELOG` L113）｜章程 **0.2.118** §7.71（`docs/roles/kol-expert.md` L640–647）｜缺陷类 **CLS-47**（`_DEFECT-CLASSES.md` L60）｜教训 **209–210**｜TICKET-100（done）
>
> ⚠️ **本章子节编号说明**：**§16.2**（参数表先行 · TICKET-100 L17）与 **§16.4**（归一化与回显 · CLS-47「结构性修复」列）**两处节号由外部逐字引用坐实**；**§16.1／§16.3／§16.5–§16.9 的编号为重建分配**，标题为重建命名。**并入前建议由总监核对原编号。**

### 16.1 用途与适用面

**用途**：在 Daniel 的 **Creator Tracker（红人追踪）** 里**自动化建 Campaign**，并把用户的口语输入（不规范日期、口语 Evergreen）**归一成接口要的机器写法**，且**回显"我替你补了什么"**。

**本轮范围（逐字 · `daniel_ct.py` docstring L5）**：**Campaign** 的列／建／改（**Deals、Videos 留待下一步**，路由已定位见本章）。
**已知边界**：`ct.deals.create`（给 campaign 加达人合作）**已定位、未实测**（TICKET-100 L60）。
**方向边界（逐字 · 章程 L637）**：**红人追踪（Creator Tracker）不并入 KOL 全链路检索链路**（2026-09-30 用户裁决）—— 名单检索与达人合作是两个独立方向。

### 16.2 参数表：`ct.campaigns.create` 的 8 键（「**参数表先行**」）

> **任务书工序第 ① 条（逐字 · TICKET-100 L17）**：「① **参数表先行**：从 bundle 调用点逐键读出 **8 个入参**，明确"**哪 4 项要人填、哪 3 项自动带**"（**Skill §16.2**）」
> **本节对应原 Skill §16.2** —— 节号由 TICKET-100 的验收项**逐字坐实**。路由清单见 **§16.3**。

> **入参与界面校验（逐字 · `daniel_ct.py` docstring L10–17；bundle 调用点逐键读出，`CreatorTracker.tsx:294` 起 modal）**

```
ct.campaigns.create({ brandId, title, brandName, brandHandle, brandYoutubeChannel,
                      startDate, endDate, isEvergreen, brief })
```

| 键 | 谁填 | 规则 |
|---|---|---|
| `title` | **人填（必填）** | 名称；**建后不可改**（要改只能删了重建） |
| `brandYoutubeChannel` | **人填（必填）** | 品牌 YouTube 频道；**建议给 `UC…` ID** |
| `startDate` | **人填（必填）** | 开始日期（`YYYY-MM-DD`） |
| `endDate` / `isEvergreen` | **人填（二选一必填）** | `endDate` 或 `isEvergreen = true`；🔴 **勾 Evergreen 时 `endDate` 必须不传** |
| `brief` | 选填 | 为空则**不传** |
| `brandName` | **自动带** | 由品牌档案自动带（`brand.get('name')`，**无需人填**） |
| `brandHandle` | **自动带** | 由品牌档案自动带（`brand.get('youtubeChannelId')`） |
| `brandId` | **自动带** | 由品牌解析得到 |

**组装规则的机器化（逐字 · `daniel_ct.py` `build_payload()` L151–190）**
- 品牌无效（缺 `id`）→ `ValueError('品牌无效（缺 id）')`；
- `title` 归一后为空 → `'必须填写 Campaign 名称'`；
- `startDate` 归一失败 → `'开始日期无法识别为日期（收到：…）—— 支持 2026-08-01／26年8月1号／2026/8/1／Aug 1 2026'`；
- 既无 `endDate` 又非 Evergreen → `'必须填写结束日期，或设为 Evergreen（收到：…）'`（**文案与界面一致**）；
- Evergreen **与** `endDate` 同时给 → `'Evergreen 与结束日期互斥：勾 Evergreen 时不得给结束日期'`；
- `endDate < startDate` → `'结束日期不得早于开始日期（… < …）'`；
- 频道为空且档案也没有 → `'必须填写 Brand YouTube Channel（品牌档案里也没有 youtubeChannelId）'`；
- 最后 **剔除值为 `None` 的键**（`{k: v for k, v in payload.items() if v is not None}`）。

### 16.3 路由清单（命名空间 `ct.*`）

**命名空间（逐字 · `daniel_ct.py` docstring L7–8）**：tRPC 同源 `/api/trpc`，命名空间 **`ct.*`**（**不是 `campaigns.*`** —— 后者是另一处"内容 Campaign"模块，**两者别混**）。
**取证底稿**：`docs/marketing/kol/_build/creator-tracker-campaign-create-schema.md`。
**传输层**：与 §15 同一套（`daniel_client.py` 的 `query`／`mutate`，GET 读／POST 写）。

> ⟪摘录止于 L5776；`references/61-creator-tracker.md` 尚有 L5777–L5900 未摘录⟫

### §17 KOL 全链路检索（源 L5901–L5959 逐字摘录）

## 17. KOL 全链路检索

> **能力一句话**：拿到 **brief／产品文档** 即可跑完整条链路并落到 Daniel 的 Saved List —— `brief → 搜索词清单 → deep search ＋ open search → 合并 → 全量富化 → 全量筛选 → 门槛扫描 → 去重 → 落库 ＋ 回读`。
> **判据一句话**：**这条链路的正确性不在"跑通"，而在"每个数字都能追到一个文件、每道门都能说清线定在哪"** —— 顺序错会误杀（§17.8 A），接口硬限想当然会断链（§17.2），错误体不看原文会查错方向（§17.3）。
> **来源**：用户指令 **2026-09-30**「我希望能真正的打通一条完整的 kol 搜索路线……最后直接作为一份 list 清单更新到系统中」＋ 口径追加「**一次跑到底**……数量级初筛控制在 **100 个左右**……我只要确保整个链路你可以完全跑通**没有卡点**」（TICKET-101 · Skill **v0.9.157**）⟦强证据⟧
> **仪器**：`.kol-tools/daniel_search.py`（登能力门 C7；离线自检 **81/81** 条控制）｜**章程** `docs/roles/kol-expert.md` §7.72／§7.79｜**能力地图**条目 `kol-fullchain-search`（锚点 `## 17. KOL 全链路检索`）
> **路线图（证据分级）**：`docs/marketing/kol/_build/kol-search-pipeline-route-map.md`

### 17.1 六段链路与路由

**判据一句话**：**每一段都有唯一入口接口，且接口名以系统前端 bundle 的调用点为准** —— 路由与入参不靠记忆、不靠猜。

**来源**：2026-09-30 从 bundle 调用点实测读出（v0.9.157；`daniel_search.py` 模块 docstring 逐字保留）⟦逐字⟧

| 段 | 干什么 | 接口（前端 bundle 的 `域.方法` 名） | 关键点 |
|---|---|---|---|
| ① | 搜索词清单 | 无接口（本地生成） | **我生成**；形状对齐 `discovery.listHistory` 的实测条目 |
| ② | deep search（品牌深搜） | `discovery.startSearchJob({query,brandId,brandName,brandCompetitors,brandCategory,country,minSubscribers,maxSubscribers})` → `discovery.executeSearchJob({jobId})` → 轮询 `discovery.getSearchJob({jobId})` | `startSearchJob` **只建任务**；`execute` 的**传输可能提前结束（设计如此）**；结果 `results[]` 就在任务返回体里 |
| ③ | open search（AI 扩圈） | `discovery.expandTopic({topic})` → `discovery.search({topic,selectedScenarios,selectedContentStyles,selectedAudiences,brandId,country,minSubscribers})` → 同样 execute ＋ 轮询 | **只接受单市场**；**无粉丝上限入参** |
| ④ | 富化 | `discovery.enrichChannels({channelIds≤100})`（补齐 subscriberCount／country／tags）＋ `discovery.enrichEmails({channelIds})`（商务邮箱） | 两条链路的批量上限**不一样**（见 §17.2） |
| ⑤ | 筛选 | 本地口径（体量档／互动／相关证据）＋ `discovery.rosterNLFilter`（服务端 NL 过滤，**可选**，未接入） | 口径写进计划文件的 `screening` 块，可复核可复现 |
| ⑥ | 落库 | `lists.create({brandId,name})` → `lists.batchAddItems({listId, items:[{channelId,channelTitle,channelThumbnail,subscriberCount,country,tier,cqiScore,contactEmail,engagementRate}]})` | **写后必须回读** |

**轮询**：`discovery.getSearchJob({jobId})` **每 2 秒**一次；`status` ∈ `running／enriching／done／failed`。轮询到 `done`／`failed` 即停。

**结果字段面**（`results[]` 每行）：`channelId`／`title`／`subscriberCount`／`engagementRate`／`avgViews`／`country`／`tags`／`foundByKeywords`／`matchedVideos`／`businessEmail`…

**硬限与坑**
- 🔴 **写操作（建名单／加人）必须先回读**；检索结果一律**落盘留证**（原始 JSON ＋ 归一 CSV）。
- 🔴 「执行请求提前结束」**不是失败** —— 转轮询即可（`--job-status <jobId>` 可单独查）。
- 🔴 某市场返回 0 条 → 先把该市场的关键词与过滤器打印出来核对，再决定是否重跑（**不做静默重试**）；任务 `failed` → 留编号与返回体，停下报告，不盲试第二遍。
- 🔴 会话（登录态）失效 → 重新登录一次，**不要连打**。

**仪器与验收判据**
- `python3 .kol-tools/daniel_search.py --deep --plan <plan.json>`／`--open --plan <plan.json>`／`--job-status <jobId>`／`--merge <results.json>…`／`--screen`／`--enrich <results.json> [--emails]`／`--push-list --brand <B> --name "<N>" --results <results.json> --limit 100`／`--self-test`。
- 每段验收：**原始返回落盘**（`-raw.json`／`-rows.json`／`-rows.csv`）＋ 该段人数打印 ＋ 该段判据达标（见 §17.4）。

**已知边界**
- 服务端 NL 筛选（`discovery.rosterNLFilter`／`rosterNLSearch`）**未接入**。
- `discovery.getRosterStats` 本次 **503**，达人库规模未取到（2026-09-30 首跑诚实标注）。
- 二分实测上限时留下约 **20 条 idle `search_jobs`** 记录（无结果数据；系统**无删除 job 路由**）。

### 17.2 三个卡点级接口硬限

**判据一句话**：**接口字段的容量／批量／取值域必须各自实测；"隔壁接口能传 100"不是证据。**

**来源**：2026-09-30 全链路首跑二分实测（v0.9.157 · 教训 212／213／214 · 缺陷类 **CLS-48／49／50**）；数值逐字取自 `daniel_search.py` 常量与注释 ⟦逐字⟧

| # | 接口 | 实测界 | 判据与处置 |
|---|---|---|---|
| 1 | `discovery.startSearchJob` 的 `query` | **≤501 字符**（**501 → 200；502 → 500**） | `MAX_QUERY_LEN = 501`；超限一律**拒绝执行**（**不许悄悄截断**），除非显式 `--trim`；截断按句界（`。`／`. `／`；`／`; `／`，`／`, `）截到 `TRIM_TO = 490`，**且必须回显**（`原 query N 字符 → 自动截断为 M 字符（上限 501）`）。长 brief **必须先压成"检索指令"** |
| 2 | `discovery.enrichChannels` 的 `channelIds` | 单批 **≤100** | `CHANNEL_BATCH = 100`（bundle 也是按 100 切） |
| 3 | `discovery.enrichEmails` 的 `channelIds` | 单批 **≤50**（**50→200／51→400**） | `EMAIL_BATCH = 50`；🔴 **不得按"另一个接口能传多少"类推** |
| 4 | `lists.batchAddItems` 的 `tier` | 必须是**数字 1–4**（传档名 → `expected number, received string`） | 写库用 `system_tier()`（数字），展示用 `tier_of()`（档名）——**两套口径分开命名、分开计算**。系统口径：`≥5e6→1 Mega／≥5e5→2 Macro／≥5e4→3 Mid／其余→4 Micro`；缺值 → **4**（与界面同） |

**另两条（同族，来自其它批次的实测，写在这里备查）**
- `brands.list` 的入参必须是**对象**（传空对象即可；传 `null` 报类型错）。
- `lists.delete` 的入参键是 **`id`**（不是 `listId`），且需要品牌编号。
- 判据：**入参键名以系统前端代码的调用点为准**，不以接口文档或我的记忆为准。

> ⟪摘录止于 L5959；`references/62-full-chain-search.md` 尚有 L5960–L6376 未摘录⟫

## 三、版本与追溯（E6）

| 项 | 值 |
|---|---|
| 语料版本 | `0.9.204` |
| 源文件 | `docs/marketing/skills/kol-intelligence.md` |
| 源文件 sha256 | `b82b58cfe969f133dd808146982d96bacaf7af67a2f6a3f22e1feae9de89b986` |
| 本束源行区间 | `L5008-L5721,L5722-L5900,L5901-L6376` |
| 切分器 | `docs/product/daniel-copilot/_impl/TICKET-148-语料束切分器.py` |
| 零丢失校验 | `python3 docs/product/daniel-copilot/_impl/TICKET-148-语料束切分器.py --verify` |

> 产物回填口径：交付物/回报中写明「本次用语料版本 0.9.204」。
