<!-- 本文件是 `docs/marketing/skills/kol-intelligence.md` L5008–L5721 的**逐字切片**（语料版本 0.9.207）；请勿在此改写判据，改动须回流源文件后重跑切分器 -->
<!-- 源节：§15 Daniel 系统数据层直连（含 §15.5.8 实测运维事实） -->

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

| 路由 | 方法 | 入参（**逐字**） | 返回要点 | 证据 |
|---|---|---|---|---|
| `auth.me` | GET | `null`（即 `{"json":null}`） | 当前账号对象（含 `email`） | `daniel_client.py` L88、L103 |
| `brands.list` | GET | **必须是对象 `{}`** —— 传 `null` 报 400 `expected object, received null` | 品牌数组，元素含 `id`／`name`／`workspaceId`／`userId`／`youtubeChannelId`／`category`／`competitors[]` | `daniel_lists.py` L9、L96；`daniel_lists.py` L101–102；`daniel_ct.py` L174 |
| `workspaces.getBrands` | GET | ⟦重建：弱证据 · 待补⟧ | 备用品牌路由（`daniel_client.py` 的 `brands()` 先试 `brands.list`，失败回落它） | `daniel_client.py` L143 |
| `lists.listByBrand` | GET | `{"brandId": <int>}` | 名单数组；元素含 `id`／`name`／`influencerCount`（或 `itemCount`） | `daniel_client.py` L152–153；`daniel_lists.py` L87–91、L115–116 |
| `lists.getItems` | GET | `{"listId": <int>}` | 成员数组（或 `{total}`） | `daniel_client.py` L155–156；`daniel_search.py`（`cmd_push` 回读复核） |
| `lists.getOverlap` | GET | `{"listIds": […], "brandId": <int>}` —— **`listIds` ≤ 10 个** | `{overlapping: […], listSizes: {listId: n}}` | 工作流 02 L380；`daniel_search.py` L19–20；`2026-10-halliday-batch7/06-dedup-report.md` L112–113 |
| `discovery.getChannelDetail` | GET | ⟦重建：弱证据 · 待补⟧（`**kw` 透传） | 频道详情 | `daniel_client.py` L158–159 |
| `discovery.getChannelInsight` | GET | ⟦重建：弱证据 · 待补⟧ | 受众洞察（`audience.genderDistribution`／`locationDistribution`（**只返回前 3 项**）／`ageDistribution`） | `daniel_client.py` L161–162；工作流 02 附录 B |
| `discovery.getChannelVideos` | GET | ⟦重建：弱证据 · 待补⟧ | 视频（**`pageSize ≤ 50`**；`pageToken` **不得传 `None`**，否则 400） | `daniel_client.py` L164–165；Skill 基线 0.9.24 条目 |

#### 15.3.3 写路由（**入参键以 bundle 调用点为准**）

| 路由 | 方法 | 入参（**逐字**） | 返回要点 | 状态 |
|---|---|---|---|---|
| `auth.login` | POST | `{"json": {"email": …, "password": …}}` | 响应头 `set-cookie: app_session_id=<JWT>` | ✅ 实测 |
| `lists.create` | POST | `{"brandId": <int>, "name": <str>}`；可选 `description` —— 🔴 **不接受 `description: null`（400）**，不传或传空串 | 新名单对象（含 `id`） | ✅ 实测（建出 listId `8070002`；全链路另建 `8070003`） |
| `lists.rename` | POST | `{"listId": <int>, "brandId": <int>, "name": <str>}` | ⟦重建：弱证据 · 待补⟧（未实跑） | ⚠️ **未实测**（怕动真实名单 · TICKET-099 L56） |
| `lists.delete` | POST | 🔴 **`{"id": <int>, "brandId": <int>}`** —— 键是 **`id`**，**不是 `listId`**（传错键报 400） | ⟦重建：弱证据 · 待补⟧ | ✅ 实测（删除 `8070002`，回读 14 → 13） |
| `lists.batchAddItems` | POST | `{"listId": <int>, "items": [{ "channelId", "channelTitle", "channelThumbnail", "subscriberCount", "country", "tier", "cqiScore", "contactEmail", "engagementRate" }]}` —— **单批 ≤100**；🔴 **`tier` 必须是数字 1–4** | `{addedCount, failed[]}` | ✅ 实测（首跑 `addedCount 100 · failed 0`） |
| `lists.batchRemoveItems` | POST | `{"listId": <int>, "channelIds": […]}` —— **删除类** | `{success, removedCount}` | ✅ **实测（2026-10-09 · TICKET-121）**：在 `8340005` 上分 3 批（100／100／51）删 251 条，`removedCount` 逐批等于送审数，回读 412 → **161** 且与计划集合**双向差集 0/0** |
| `lists.removeOverlaps` | POST | `{"targetListId": <int>, "channelIds": […], "brandId": <int>}` —— **删除类** | ⟦重建：弱证据 · 待补⟧；空入参 `{"json":{}}` → 400 `BAD_REQUEST` | ⚠️ **本批未调用**（去重在写入前完成，无需再删） |
| `lists.mergeLists` | — | ⟦重建：弱证据 · 待补⟧ | 工作流 02 L382：「**本轮未使用**」 | ⚠️ 仅定位 |
| `lists.updateItemTags` | — | ⟦重建：弱证据 · 待补⟧ | — | ⚠️ **仅定位未实测**（TICKET-099 L57） |
| `lists.generateShareLink` | — | ⟦重建：弱证据 · 待补⟧ | — | ⚠️ **仅定位未实测** |
| `lists.autoPriority…` | — | ⟦重建：弱证据 · 待补⟧（路由名以 bundle 为准） | — | ⚠️ **仅定位未实测** |

#### 15.3.4 `lists.batchAddItems` 的 item 形状与 `tier` 取值域

**item 组装（逐字 · `daniel_search.py` L642–664 `to_item()`）**：字段名与 bundle 一致，**值为空的键不写入**（不得写 `null` 覆盖）：

```python
{'channelId', 'channelTitle', 'channelThumbnail', 'subscriberCount',
 'country', 'tier', 'cqiScore', 'contactEmail', 'engagementRate'}
```
映射：`channelTitle ← title|channelTitle`；`channelThumbnail ← thumbnailUrl|channelThumbnail`；`contactEmail ← businessEmail|contactEmail`；`engagementRate` 走数值化。

🔴 **tier 数字规范（逐字 · `daniel_search.py` L107–122）** —— **这个数字是写进系统的字段**，与展示档名**口径不同**：

| 函数 | 用途 | 分界 | 标签 |
|---|---|---|---|
| `system_tier()` | **写库**（`lists.batchAddItems.tier` 要求 `number`） | `≥5e6→1`／`≥5e5→2`／`≥5e4→3`／**其余→4** | 1=Mega／2=Macro／3=Mid／4=Micro |
| `tier_of()` | **展示** | Nano <1万／Micro 1万–10万／Mid-size 10万–50万／Macro 50万–200万／Mega ≥200万 | Nano／Micro／Mid-size／Macro／Mega |

- 分界依据（逐字 · L105–106）：取自 bundle 的 `function ls(s)`（`Discovery-*.js`：`s>=5e6?1 : s>=5e5?2 : s>=5e4?3 : 4`；标签表 `St`）。
- **缺值 → 4**（与界面同：`s?s>=…:4`）（L110）。
- 🔴 **混用会写出错的档位**（CLS-50 判据一句话：**凡写进系统的枚举／档位字段，先读它的真实取值域；展示口径与写库口径分开命名、分开计算**）。

#### 15.3.5 `lists.batchAddItems` 的**字段保真边界**（2026-10-09 实测 · TICKET-120）

> **第二次复现（2026-10-10 · TICKET-123）**：另一品牌 Tenniix（`1680001`）导入 151 人，**111/151 行的回读 `tier` 与写入值不同**（写入分布 档2×1／档3×33／档4×117 → 回读 `{1:23,2:38,3:53,4:37}`），而**标题／订阅数／国家 0 处不一致**。

**事故背景**：把三个名单合并去重（412 人）后写进一个新名单，`item` 字段**逐字取自源名单那一行**（含 `tier`／`channelTitle`／`channelThumbnail`／`subscriberCount`／`country`／`cqiScore`／`contactEmail`／`engagementRate`）。写后回读：**412 行里 225 行的 `tier` 与源行不同**，且与订阅数分档对不上。

**实测结论（412 行全量比对）**：

| 字段类 | 例子 | 写入后回读 |
|---|---|---|
| **频道级事实字段** | `channelTitle`／`channelThumbnail`／`subscriberCount`／`country`／`contactEmail`／`cqiScore`／`engagementRate` | **原样保留**（412×7 全量比对，0 处不一致；仅 1 处 `country` 差异） |
| **评分与优先级（系统重算）** | `tier`／`priorityScore`／`scoreBreakdown`（含 `brandFit`／`vpr`） | **按当前规则重算**，不是写入值。样例：`brandFit` 100→15、`vpr` 100→50、`priorityScore` 70→46、`tier` 1→3 |
| **检索证据（整块丢失）** | `tags`／`matchedVideos`／`foundByKeywords`／`medianViews` | **412/412 全为空**（`[]` 或 `null`）—— 这些是**名单内那一行**的属性，不是频道的属性，`batchAddItems` 不带 |

**由此得三条纪律**：

1. 🔴 **`batchAddItems` 只保证「频道级事实」搬得过去**；`tags`／证据／`medianViews` 需要**重新富化**（`harvest_daniel_enrichment.py` 等）才有值。
2. 🔴 **跨名单的 `tier`／`priorityScore` 不可比**：同名红人在旧名单与新名单里的 `tier` 可能是两个不同时点按不同规则算出来的（实测 `tier` 与 `priorityScore` 同向：`tier`1 的 PS 50–74、`tier`4 的 PS 15–41）。**要比档位就比同一张表内的值**，不要把旧表的档位当"应该继承"的期望值。
3. 🔴 **量级门槛的边界必须显式确认**：凡「以上／以下」这类门槛（如"排除 60 万以上、1 万以下"），执行前先问清**含不含本数**，并把两侧边界人数单独报出来 —— 实测一次裁剪里恰好落在 `=10,000` 的有 2 位，「≤」与「<」两种读法结果差 2 人（124 vs 126）。
4. 🔴 **写入类任务的验收口径**：回读**必须比对**，且比对要**分类**（事实字段 vs 重算字段 vs 证据字段），不能笼统说"字段一致"；发现重算要**如实上报为系统行为**，不得当成脚本 bug 瞒掉，也不得当成"写入失败"。

### 15.4 写操作纪律（**三条内置 ＋ 删除必须显式确认**）

> **判据一句话（章程 L652）」：路由名与入参键以 bundle 里的调用点为准（不是记忆里的旧代码、也不是命名习惯）；凡写操作必须回读核对。**

**工具内置的三条（逐字 · `daniel_lists.py` docstring L14–17）**
1. **重名拦截**：同 brand 下已有同名名单 → **默认拒绝**（需 `--allow-duplicate` 显式放行）；
2. **删除必须显式确认**：`--delete` 必须同时给 `--yes`，且**删除前打印"将删除什么"**；
3. **一律写后回读**：create／rename／delete 都重新拉一遍名单，**核对结果后才算成功**。

**§15.4 额外纪律**
- 🔴 **删除类写操作**：先打印「**将删除哪个名单、多少人、都是谁**」，**不带显式确认只预览不执行**；批量或不可逆操作**先给计划**（工作流 02「写操作与安全」一）；
- **跨 workspace 或批量删除**：先出计划并取用户明确同意（章程 L654）；
- **只读随时可跑**：`--brands`／`--lists` **不做确认要求**（章程 L655）。

**重名判定口径（逐字 · `daniel_lists.py` L46–61）**：名单名归一 ＝ **去首尾空白 ＋ 折叠内部空白 ＋ 小写**；**子串不算同名**（`agent test` ≠ `agent test list`）；退化输入（`None`／非列表）→ **不拦**（返回 `None`）。

**删除预览文案（逐字 · `daniel_lists.py` L83–91）**：`将删除：品牌「%s」下的名单「%s」（listId %s，含 %s 个 creator）`；数量缺失写「**未知数量**」，**不得致崩**。

**写后回读判据（逐字 · `daniel_lists.py` `cmd_create` L132–143）**：create 返回 `id` 后**重拉名单**，**回读里找不到该 id ⇒ 视为失败**；打印「名单数 N → M」与命中对象。

### 15.5 硬限与坑（每条都实测过 · v0.9.174 复核 · 2026-09-30）

> 全部硬限的共同纪律（CLS-48／49／50 的「结构性修复」列）：**① 🔴 接口硬限先实测（长度／批量／取值域）；② 🔴 错误体打原始 HTTP（客户端会吞）；③ 🔴 展示口径与写库口径分开；④ 长文本先压成指令再提交。**

| # | 硬限／坑 | 实测值 | 证据 |
|---|---|---|---|
| 1 | `brands.list` 入参**必须是对象** | 传 `null` → 400 `expected object, received null` | `daniel_lists.py` L9；CLS-46（`_DEFECT-CLASSES.md` L59） |
| 2 | `lists.delete` 的键是 **`id`**（不是 `listId`）＋ 需 `brandId` | `{listId}` → 400；bundle 调用点 `Ve.mutate({id:i.id,brandId:z})` | `daniel_lists.py` L11；CLS-46 |
| 3 | `lists.create` **不接受 `description: null`** | 400 | `daniel_search.py` docstring L19–21（v0.9.174 第八批实测） |
| 4 | `lists.getOverlap.listIds` **≤ 10 个** | 传 11 → 400 `Too big: expected array to have <=10 items` ⇒ 复核**拆多次调用** | `daniel_search.py` L19–20；`2026-10-halliday-batch8/_build/overlap-evidence.json` L36；`_build/step6_overlap_witness.py` L5 |
| 5 | `lists.batchAddItems.tier` **必须是数字** | 传档名 → 400 `expected number, received string`（`path: items[0].tier`） | CLS-50（`_DEFECT-CLASSES.md` L61）；`daniel_search.py` L107–122 |
| 6 | `lists.getOverlap` **不接受 POST** | `Unsupported POST-request to query procedure at path "lists.getOverlap"`（**读类必须 GET**） | `2026-10-halliday-batch8/_build/overlap-probe.json` L50 |
| 7 | `lists.removeOverlaps` **语义 ≠ 自动比对去重** | 空入参 → 400 `BAD_REQUEST`；语义＝**从指定名单里删掉指定的这批频道** | `2026-10-halliday-batch7/06-dedup-report.md` L123–L141 |
| 8 | **旧客户端快照静默失效**（CLS-46） | `daniel_client.py` 里写死的旧路由会**静默失效**；报裸 400 但**不说"我过时了"** | `daniel_lists.py` L12；CLS-46 |
| 9 | 名单计数实测 | `agent test list` 建前 13 → 建后 **14**；删除回读 **14 → 13** | TICKET-099 L29–30 |
| 10 | 实测锚点值 | 品牌 Halliday `3690002`／workspace `90002`／userId `53130001`；全链路落库 `8070003`（addedCount 100 · failed 0 · 回读 100 条） | TICKET-099 L28；`_CHANGELOG` L111（0.9.157） |

**同族硬限（属 §17，此处仅交叉引用以免重复）**：`discovery.startSearchJob.query` **≤501 字符**（502 → 500 `Failed query: insert into search_jobs (…)`）—— `daniel_search.py` L48–55；`discovery.enrichChannels` **≤100** ／ `discovery.enrichEmails` **≤50**（**不得类推**）—— `daniel_search.py` L54–62。

### 15.6 Compare Lists：`getOverlap` ／ `removeOverlaps` ／ `mergeLists`

> **本节对应 §15 的「名单去重（Compare Lists）」工序**（工作流 02 节点 N10）。

| 路由 | 语义 | 入参 | 用法要点 |
|---|---|---|---|
| `lists.getOverlap` | **取权威重叠证据** | `{listIds, brandId}`，`listIds ≤ 10` | 传「新名单 ＋ 历史名单」；返回 `overlapping` 与 `listSizes` |
| `lists.removeOverlaps` | **从目标名单删掉指定频道**（**不是自动比对去重**） | `{targetListId, channelIds, brandId}` | **删除类**：先预览再确认；无必要即不执行 |
| `lists.mergeLists` | 合并名单（按需） | ⟦重建：弱证据 · 待补⟧ | 工作流 02：**本轮未使用** |

**工序（工作流 02 N10）**
1. **读名单成员**：`lists.listByBrand({brandId})` ＋ `lists.getItems({listId})` —— **先把历史名单的频道编号全集读下来，本地排除**；
2. 写库后**重叠核对**：`lists.getOverlap` 取权威证据；
3. **去重（删重叠）按需**：`lists.removeOverlaps`，先预览再确认。

**🔴 两条实测纪律**
1. **`listIds` 超 10 个必须拆调用** —— 第八批对 11 个名单的复核因此**拆成两次**（`daniel_search.py` L19–20；`step8_acceptance_selfcheck.py` L70–71 亦按 9＋… 拆）。
2. **重叠人数出现两种读法不一致时，两种读法都写进报告**（工作流 02 N10 失败兜底）：本批实测两种读法分别是 **0 人**（只按"新名单 vs 某名单"）与 **1 人**（按"去重前候选池 vs 该名单"）——**避免任一单一说法误导**。
3. **两种读法都给**是本节的硬性输出要求（`2026-10-halliday-batch7/06-dedup-report.md` L104）。
4. **去重在写入之前完成、写入后复核重叠为 0 ⇒ 无需调用 `removeOverlaps`／`batchRemoveItems`**（两者都是"从指定名单里删除指定频道"的删除类写操作，作用在真实名单上，**无必要即不执行 —— §15.4**）。

### 15.7 仪器与验收判据

| 仪器 | 自检 | 覆盖 |
|---|---|---|
| `.kol-tools/daniel_lists.py --self-test` | **16/16**（本轮实测） | 判重（含大小写／全角空格／中文名／子串不算／六类退化输入）／品牌解析（空值／歧义／类型）／删除预览（缺数量）／**无 `--yes` 不得调写接口** |
| `.kol-tools/daniel_client.py` | 无 `--self-test`；入口脚本跑 `login → whoami → brands` | 传输层与认证 |

**验收判据（可执行，逐条对应能力地图 acceptance）**
1. **路由与入参以 bundle 实测为准** —— 新路由首次使用**先只读探测**（§15.2）；
2. **写后回读核对** —— create／rename／delete 回读后核对结果，**回读找不到即视为失败**；
3. **重名拦截** —— 同名默认拒绝，子串不算同名；
4. **删除需 `--yes`** —— 不带 `--yes` **只预览不执行**并 `exit 1`。

**实测验收证据（TICKET-099 L26–34）**：身份 `jack.hu@globaloneclick.com` · workspace `90002` · brand Halliday `3690002`；建名单 ✅；删名单 ✅；重名拦截 ✅（`--create --brand Halliday --name "Halliday—第六批"` → 拒绝并指向既有 listId `8010003`，**无写入**）；dry-run ✅；删除守卫 ✅；离线自检 **16/16**。

### 15.8 范例路径

| 类型 | 路径 |
|---|---|
| 主仪器 | `.kol-tools/daniel_lists.py` |
| 传输层 | `.kol-tools/daniel_client.py` |
| 会话缓存（勿外发） | `.kol-tools/.daniel_session.json` |
| 凭证（勿入库） | 环境变量 `DANIEL_EMAIL`／`DANIEL_PASSWORD` 或 `.daniel_cred.json` |
| 全链路落库工具（用本章写路由） | `.kol-tools/daniel_search.py` |
| 任务单 | `tickets/TICKET-099-daniel-lists-write-path.md` |
| 去重报告范例（第七批） | `docs/marketing/kol/2026-10-halliday-batch7/06-dedup-report.md` |
| 重叠证据范例（第八批） | `docs/marketing/kol/2026-10-halliday-batch8/_build/overlap-evidence.json` |
| 工作流（本章工序的展开版） | `docs/marketing/workflow/02-agent-daniel-workflow.md` N10／N11／「写操作与安全」／附录 A |

**工具用法（逐字 · `daniel_lists.py` docstring L19–25）**

```bash
python3 .kol-tools/daniel_lists.py --brands
python3 .kol-tools/daniel_lists.py --lists Halliday
python3 .kol-tools/daniel_lists.py --create --brand Halliday --name "agent test list"
python3 .kol-tools/daniel_lists.py --rename --list-id 8070002 --name "new name"
python3 .kol-tools/daniel_lists.py --delete --list-id 8070002 --yes
python3 .kol-tools/daniel_lists.py --self-test          # 离线自检（不联网）
```

---

### 15.5 Daniel 其它区块全链路（Brands ／ Brand Mentions ／ Intelligence 核心 ／ SOV 全家桶 · 2026-10-10）

> **一次性把四个区块从"未打通"做到"读全通、写可控"**。全部路由**从 bundle 调用点反查**（不是猜的），遵循同一套纪律：**只读先行 → 类型非法探针探形状（零副作用）→ 写/触发最小可逆 → 写后回读**。
> 交付文档：`docs/marketing/kol/_daniel-integration/01-brands.md`／`02-brand-mentions.md`／`03-intel-core.md`／`04-sov.md`；仪器：`.kol-tools/daniel_brands.py`（自检 24/24）／`daniel_mentions.py`（28/28）／`daniel_intel.py`（25/25）＋`daniel_authenticity.py`（21/21）／`daniel_sov.py`（35/35）。

| 区块 | 路由 | 状态 | 关键入参键与坑 |
|---|---|---|---|
| **Brands** | 7（`list`／`getById`／`create`／`update`／`delete`／`suggestCompetitors`／`verifyChannel`） | ✅ 读＋写全通（测试品牌建删 8 个；2026-10-10 按单条链路复验 1 条：建→改→删＋**双回读**，零残留） | `getById` 键是 **`id`**（不是 brandId）；`list` **只返回当前工作区**；`update` 是**局部合并**；`description` 不接受 `null`。🔴 **写必须显式给 `workspaceId`**（否则落在**当时活跃**的工作区；实测两次临时品牌各落在 510002／90002）且**回读范围必须跟随写入目标工作区**（未跟随会把「建到 510002 的成功」读成失败——已修，自检 27/27）；🔴 **服务端不拦空名／重名／计划上限**；🔴 **`delete` 删不存在的 id 也回 `success:true`** ⇒ **必须双回读**（列表不命中 ＋ getById 为 null） |
| **Brand Mentions** | 15（7 读 ＋ 4 触发 ＋ 4 守卫） | ✅ 读 7/7、触发实跑 1 次（41s done）、守卫 0 执行；2026-10-10 单条链路复验 7/7 | `getResults.pageSize` **10–200**；`sortBy` 8 值／`relevanceFilter` 3 值／`formatFilter` 3 值／`authenticityFilter` 4 值；读类 POST→405、触发类 GET→405；`exportMentions` 走**非 batch** 形态。🔴 三个实测坑：① `getResults` **缺省＝`confirmed`**（同一 41 条视频的任务只回 1 行）⇒ 要看全量必须显式 `relevanceFilter:'all'`，**"命中很少"多半是过滤缺省造成的假象**；② `getTopChannels.limit` 合法区间 **5–50**（`1／3／100` → 400），且 `confirmed`／`confirmed_likely` 在同一数据集回 **0 行**而 `all` 回 6 行（每行 `relevanceLabel` 均为 `confirmed`）⇒ **服务端过滤字段与展示字段不一致，取数一律用 `all` 再本地过滤**；③ `listJobs` 行的 **`id`（自增）≠ `jobId`（UUID）**，拿 `id` 去匹配 UUID 会静默取不到任务 |
| **Intelligence 核心** | 25（真实前缀是 **`actionCenter.*`**；`videos.*` 实为 **`ct.videos.*`**） | ✅ 读 17/17（2026-10-10 单条链路复验 6/6）；写/触发 13 条**只定位未执行**（`memos`／`reviews`／`keywords.add*` **无删除路由** ⇒ 建了不可逆，按纪律不建） | `reviews.*` 要 `stage∈{pre_production,final_packaging}`＋`topicLabel`；`topics.startVideoEvidence` 不存在 → **500**（不是 404）；`actions.*` **没有 create** ⇒ 造不出自己的 action，不碰真实动作 |
| **SOV 全家桶** | 24（`exposureSov` 5／`seoSov` 6／`sovCategories` 11／`dashboard` 2） | ✅ 读 16/16；触发各 ≤1 次；写类 9 条中 **3 条已用「零净变化写回」验通**（`updateFilterKeywords` ×2 ＋ `updateBrandConfig`，见 §15.5.1），其余 6 条仍未执行 | 🔴 **`assocId` 是 `categoryProfileId`、`id` 是 `categoryId`**（Halliday：2310001／360001，市场 US,CA,GB）；`sovCategories.list` 无入参、跨 workspace；`getBrandVideos.limit` 是**上限且无分页**（`offset` 静默忽略） |

**四条实测出的系统行为（写进纪律）**：
1. 🔴 **Authenticity 在界面上是一个「输入框式查询工具」**（用户 2026-10-10 说明）：**丢进红人的 handle／频道 URL，点「检查」即时出分**，不落库、不保存 —— 所以"写入"这条需求本身不存在。对应能力＝**用前端口径当场复算**：仪器 `.kol-tools/daniel_authenticity.py --channel "@handle"`／`--channel "<频道URL>"`（也可 `--channel-id UC…`）**逐字镜像该输入框**。原结论（不可写）与三条证据见下：`/authenticity` 页只有 3 条只读路由，分数**前端自算**；全 bundle 148 条写路由**无写入点**；名单表该字段 3438/3438 全 `null`（`scoreBreakdown.authenticity` 是服务端 Auto-Priority 的另一回事，**不可互替**）⇒ 该指标**由我方按前端口径复算并写进交付物**（仪器 `daniel_authenticity.py`，与前端 JS 600/600 逐位一致；`-1`＝数据不足，不是 0 分）。
2. 🔴 **workspace 纪律（用户 2026-10-10 裁定）**：**工作区固定为 Jack 下的 Halliday（`workspaceId 90002`）**；**非用户明确指令，一律不得调用 `auth.switchWorkspace`**（本代理从未调用过；实测该字段会被**同账号的其它会话／浏览器**改掉）。**所有脚本一律按 `brandId` 直接取数，禁用按品牌名解析**（`brands.list` 是 workspace 维度的，会静默返回别的工作区的品牌）。
3. 🔴 **活跃 workspace 是账号级共享状态**：`auth.me.activeWorkspaceId` 会被**同账号的其它会话／浏览器**改掉（实测 90002 → 510002 后，`brands.list` 只返回 510002 的品牌）⇒ **所有脚本一律按 `brandId` 直接取数，禁用按品牌名解析**；按名字失败时错误信息必须回显 `activeWorkspaceId` 与当前可见品牌。
4. 🔴 **守卫探测不要拿真实接口试服务端校验**（Brands 的空名探测真的建出了记录）⇒ 守卫一律**离线自检**；线上探形状统一用**类型非法入参**（tRPC 校验先于 resolver ⇒ 零副作用）。
5. 🟢 **Exposure 采集 worker 已于 2026-10-10 上线**（原"未部署"结论作废）：同一任务 `b8866824…` 由 `TRIGGER_FAILED:WORKER_NOT_DEPLOYED`（1.7s failed）变为 **completed**（`10:15:05Z` 起 · `10:22:22Z` 完成），Exposure SOV 首次返回真实大盘（**4,840 条视频／107,386,664 次观看**；Halliday 归属 9,140,520）。**新纪律**：判"未部署"前先看 `latestTask` 的**当前**状态 —— **worker 可被平台侧上线，瞬时失败不等于能力缺失**。`seoSov.runCollection` 仍**按配置指纹幂等**（配置未变不新建任务），前端"already running"文案与事实不符。

### 15.5.1 接管验收（单条链路 · 2026-10-10 用户裁定口径）

> **用户口径（逐字）**：「我对于你测试的预期在于，你只需要使用**一条测试数据（或者一个 kol）**进行完整链路测试即可，核心在于**验证整个接管是否已经完成**而不在于数据量或者并发。」
> 故"接管"的验收**不看条数、不看并发**：**每个区块取一条真实数据跑通 读 → 写／触发 → 回读**，能给出一张 PASS/FAIL 清单即算完成。仪器：**`.kol-tools/daniel_takeover_check.py`**（离线自检 **23/23**）。

**一条命令跑完全部验收**：

```bash
python3 .kol-tools/daniel_takeover_check.py --brand 3690002 \
  --mentions-job <UUID> --channel "@handle"                 # 只读轮（默认，零写操作）
python3 .kol-tools/daniel_takeover_check.py --brand 3690002 --with-writes --yes   # 写链轮
```

**验收结果（2026-10-10 实跑 · 写链轮）**：**26 PASS ／ 1 WARN ／ 1 SKIP** —— Brands（读＋单条建改删＋双回读）／Brand Mentions（一个任务的六条读链）／Intelligence 核心（六条读链）／SOV（读 ＋ 三条零净变化写回）／Authenticity（单频道复算 88/100）全通；唯一 WARN 是 `getTopChannels` 的过滤字段不一致（见上表），唯一 SKIP 是 Intelligence 写链（**无删除路由，建了不可逆**）。

🔴 **零净变化写回（No-op Write-back）—— 本轮新增纪律**：对**不可逆或高风险的配置类写路由**（改竞品／过滤词／品牌配置），验证通路**不必真改数据**：
① 先读回当前值 → ② 把**原值原样写回** → ③ 再读回比对**短哈希**与逐项相等。`success=true` ＋ 哈希不变 ⇒ **写链可用且零净变化**（本轮 `updateFilterKeywords`×2 ＋ `updateBrandConfig` 三条以此验通，Halliday 品类档案净变化 False）。
**安全闸（已进自检 ③④⑤，不可绕过）**：读回为 `None`／空列表／非列表 ⇒ **拒绝写回** —— 防把"一次读取失败"写成"清空配置"。

**验收报告（可复核）**：`docs/marketing/kol/_daniel-integration/05-takeover-acceptance.md`；证据 JSON：`_takeover-check-20261010.json`（只读轮）／`_takeover-check-20261010-writes.json`（写链轮）。
**未纳入本轮（等指令）**：Intelligence 写链（不可逆）／视频级三链路（`collectVideoSources`／`runVideoDeepReview`／`retryVideoReplay`，触发即真实消耗）／Authenticity 批量（按用户口径单条即可）／`seoSov.getSnapshot` 与 `brandMentions.deepAnalyticsV4.*`（仍是盲区）。

### 15.5.2 工作区隔离协议（活跃工作区是账号级状态 · 2026-10-10 实测）

> **用户的问题**：在 PC 端 Daniel 里切工作区，会不会影响我方接管时用的工作区？**能不能互相不影响？**
> **答**：会互相影响，但**可以做到互不影响** —— 前提是把"工作区"从上下文变成**每次请求的显式入参**。

**事实（`auth.me` 实测字段 ＋ 前端调用点原文）**：
- `auth.me` 同时返回 **`activeWorkspaceId`** 与 **`workspaceId`** ＋ **`workspace` 对象**（实测 `{"id":90002,"name":"jack","planTier":"starter","maxBrands":2}`）⇒ **活跃工作区存在用户记录上，是账号级状态**，不是浏览器本地状态。
- 前端 `WorkspaceContext` 的 `switchWorkspace` ＝ `auth.switchWorkspace.useMutation` + `utils.invalidate()`（**不进 token、不改本地开关**），`BrandContext` 直接读 **`user.workspace`** 渲染 ⇒ **你在 PC 上一切，任何以同一账号登录的客户端（含我方 API 会话）看到的活跃工作区同时变**。反向同理：**若我方调用 `auth.switchWorkspace`，你的浏览器也会跟着变** —— 故纪律是**永不调用**（除非用户明确指令）。
- 实测轨迹：`activeWorkspaceId` 在 90002 ↔ 510002 之间被改过两次（**均非我方所为**；我方从未调用该路由）。

**能不能独立？能 —— 路由分两类**：

| 类别 | 代表路由 | 行为 |
|---|---|---|
| ✅ **接受显式工作区入参** | `brands.list {workspaceId}`／`brands.create {…, workspaceId}`／`workspaces.getBrands {workspaceId}` | **按请求定向，与活跃工作区无关**（前端原文：`brands.create.mutate({...a, ...S?{workspaceId:S}:{}})`）。实测：活跃工作区为 **90002** 时，`brands.list{workspaceId:510002}` 正常返回 `Aosulife`；`brands.create{workspaceId:510002}` 建出的品牌回读 **`workspaceId=510002`** |
| ⚠️ **不接受工作区入参** | `brands.list {}`（默认吃活跃工作区）／`sovCategories.list`（无入参、跨工作区）／`workspaces.*` 之外的无参路由 | 取数范围**取决于活跃工作区** ⇒ **这是唯一的耦合面** |

**我方执行协议（四条 · 已进仪器）**：
1. 🔴 **读一律按实体 id**（`brandId`／`categoryProfileId`／`listId`／`jobId`），**不把"当前工作区"当上下文**；
2. 🔴 **写必须显式给目标工作区**（`workspaceId` 入参），并在**目标工作区回读**；
3. 🔴 **读类路由永不调用 `auth.switchWorkspace`；触发类任务必须先切并回读**（2026-10-14 用户明确指令修正：「记住要先切换 workspace 和 brand 后，再进行 sov 和 brand mentions 的更新」——`runCollection`／`runAnalysis` 不吃工作区入参、按账号级活跃工作区落库，实测动手前活跃工作区是 1020002 Susie）；
4. 🔴 无工作区入参的路由，取数后**核对返回体里的 `workspaceId`／`brandId`**，不符即报"当前活跃工作区不是预期那个"，**不猜、不静默**。

**要彻底隔离（零共享）**：给自动化单独开一个账号／令牌（只挂 Halliday），或把 Halliday 放到独立工作区 —— 否则"账号级活跃工作区"这一层永远共享；我方协议只能把**我方行为**与它解耦，**不能改变它本身是账号级的**这一事实。

### 15.5.2b 凭据与会话落点纪律（2026-10-14 剥离实测后固化）

🔴 **判据：凭据、会话、缓存、产出四类落点都必须可配置，且默认落用户数据目录 —— 不得落在代码目录或仓库根。**

实测（`.kol-tools/daniel_client.py`）：

```
23: BASE = "https://daniel-agent.com"                            # 端点硬编码
26: SESSION_FILE = os.path.join(HERE, ".daniel_session.json")     # 会话 JWT（1 年有效）→ 代码目录
27: CRED_FILE    = os.path.join(ROOT, ".daniel_cred.json")        # 账号密码明文 JSON → 仓库根
28: BRAND_INDEX_PATH = os.path.join(HERE, "_cache", "brand-index.json")  # 缓存 → 代码目录
```

后果：**分发给别人后代码目录只读 ⇒ 三者全部写不进去**；更严重的是把**账号密码**留在应用资源目录（比模型 Key 更重的安全项）。
同类先例：本仓 `AGENTS.md §9` 记 lark-cli 令牌库路径硬编码；`§10` 记 meegle 用环境变量注入实现免落盘。

**四条要求**：① 端点、账号、数据目录一律环境变量可覆盖（`DANIEL_HOME`／`DANIEL_EMAIL`／`DANIEL_PASSWORD`／`DANIEL_BASE_URL`）；
② 凭据**首选系统钥匙串**，环境变量次之，**明文文件只作显式降级**；③ 会话与缓存落**用户数据目录并按账号分区**；
④ 交付前跑一遍"代码目录置只读"的回归（`chmod -R a-w` 后仍能跑通一条只读链路），并把"无明文凭据落在代码目录"写成断言。

### 15.5.3 品牌提及的原生表现评级 ／「广告投放候选清单」口径（2026-10-14 用户返工指令后固化）

**需求方的判据必须用原生字段，不许自造代理口径**（本次返工的核心教训）：
广告团队要的是「Daniel 里评估为 **High Organic Performance** 的视频」，其**逐字映射**取自前端 bundle
`.kol-tools/_daniel_bundle/BrandMentions-CbA4Ooa0.js`：

| 后端字段 `overallPerformance` | Daniel 界面标签 | 旧版遗留推荐位 |
|---|---|---|
| **`Strong Outperform`** | **High Organic Performance**（Organic 表现优秀） | `highly_recommended` |
| `Outperform` | Good Organic Performance（Organic 表现良好） | `recommended` |
| `Average` | Average Organic Performance | `neutral` |
| `Underperform`／`Strong Underperform` | Low Organic Performance | `not_recommended` |

> 旁证（同一 bundle）：深度分析入口的提示语＝「No videos match **High Organic Performance + Confirmed relevance + Long-form (> 120s)**」
> —— 系统自己认定的"可投放候选"就是这三条的组合。**别再用"品牌内观看量前 25%"之类的代理口径去顶替它**
> （上一版这么做，导致 80 行里 30 行没有评级，被需求方打回；见 CLS-73）。

**配套字段口径**：相关性 `relevanceLabel ∈ {confirmed, likely, unlikely}`（`unlikely` 多为品牌名同名噪声，
实测 `Halliday` 的高表现 61 条里 59 条是足球运动员／歌手等同名内容）；内容类型 `videoType`（`filtered_irrelevant`
＝系统判无关、`sponsored`＝付费内容）；推广旁证 `promotionStatus`；**读结果一律带 `relevanceFilter:"all"`**
（缺省只回"确认相关"，会漏掉绝大多数行）。

**🔴 触发类任务吃"账号级活跃工作区"——必须"先切 + 回读"**（对 §15.5.2 第 3 条的**用户授权例外**）：
`exposureSov.runCollection`／`brandMentions.runAnalysis` **不接受工作区入参**，落库归属＝当时的 `activeWorkspaceId`。
2026-10-14 实测：动手前 `activeWorkspaceId = 1020002（Susie）` —— 不切就会把采集落到别人的工作区。
用户当次明确指令「**记住要先切换 workspace 和 brand 后，再进行 sov 和 brand mentions 的更新**」⇒ 工序固定为：
`auth.me` 读取 →（不符则）`auth.switchWorkspace {workspaceId: 90002}` → **回读 `auth.me` 断言 workspaceId 正确** →
`brands.list {workspaceId}` 确认品牌 → 才触发采集。**读类路由仍按 §15.5.2 用实体 id，不依赖活跃工作区。**

**三条实测运维事实（都会导致"假失败"或空等）**：
1. `brandMentions.getStatus` 的**终态不止 `done`** —— 实测 XREAL 停在 `completed_with_warnings`（完成但带告警）；
   终态集合取 `{done, completed_with_warnings, failed, cancelled, canceled, error}`，只认 `done` 会一直空等；
2. 连续触发多个分析任务会撞 **`HTTP 429 Too Many Requests`** —— 退避重试（45s×n）即可成功，
   **不是能力缺失、也不是终态**（与 `TRIGGER_FAILED:WORKER_NOT_DEPLOYED` 属同类瞬时态）；
3. `searchMode="sku"` 的 `skuTerms` **最多 2 项**（bundle 调用点 `[ot.trim(), ct.trim()].filter(Boolean)`，
   界面只有两个输入框）—— 传 3 项返回 `HTTP 400 Bad Request`，别误判成"不支持 SKU 检索"。

4. 🔴 **重新分析会让评分漂移**（2026-10-14 实测）：同一条视频再跑一次分析，`compositeIndex`（Rated Score）与 `overallPerformance` 会变
   —— 系统**按本次候选池重算频道基准**。实测交集 431 条中：**5 条评级迁移**（3 条由"显著超出基准"掉到"平均"，分数被打到 **1.0**）、**16 条分数被改成 1.0**（疑似回退值）。
   ⇒ **不同批次／不同窗口的数据不是同一把尺子**：若把新窗口数据与旧批次数据混进同一张对比表，品牌之间的对比会带系统性偏差。
   处置：交付件固定用**同一批次快照**；新增窗口的数据**单独成表并标注**，不混入主口径。

**竞对名单的真源**：`sovCategories.getByBrand {brandId}` 返回的品类档案里，品牌**自己配置的 `competitors`**
就是"核心竞对"的权威名单（Halliday 实测 7 个：Ray-Ban Meta／Oakley Meta／XREAL／Rokid／VITURE／Brilliant Labs／RayNeo），
**不要用"份额前三 ＋ 形态相关性"自行收窄**（上一版只拉 3 个，被需求方打回）。
本品侧若品牌名任务噪声过大（同名/近名），用 `searchMode="sku"` ＋ 产品词再拉一遍
（实测：Halliday 品牌名任务 245 条里高表现仅 2 条可用；SKU 词任务 271 条里高表现 101 条、确认相关 38 条）。

**实现与机器判据（2026-10-10 落地）**：
- 🔴 **跨工作区品牌索引**：`Daniel.brand_index()` 用 `auth.listMyWorkspaces` × `brands.list {workspaceId}` 建索引
  （实测 **109 工作区／257 品牌／构建 68s**，落盘 `.kol-tools/_cache/brand-index.json`，默认 TTL 7 天）；`Daniel.resolve_brand_ref(ref)`
  ＝ **数字走 `brands.getById`（跨工作区）、名字走索引**。**名字在多工作区同名 ⇒ 拒绝解析并要求 brandId（不猜）** ——
  实测 `Halliday`／`Yarbo` 都命中 3 个工作区，故**入口一律用 brandId**。
- 🔴 **判据仪器 `check_workspace_independence.py`**（离线自检 **10/10**；在线只读默认开）：
  **A 静态**（A1 活跃工作区只许出现在提示信息里／A2 任何 `brands.list` 必须带 `workspaceId` 或有 `ambient-workspace-ok` 受限标注／
  A3 代码里不得出现 `auth.switchWorkspace`／A4 品牌解析必须走 `resolve_brand_ref`／A5 写类必须显式给 `workspaceId`）；
  **B 动态**（B1 按 id 取数与 `activeWorkspaceId` 无关／B2 **挑一个活跃工作区看不到的品牌**验证名字解析跨工作区命中／
  B3 索引与 `getById` 给出同一 `workspaceId`）。实跑：**A 全过（11 个在用仪器）+ B 3/3 通过**（B2 样例：活跃 90002 时解析 `Jackery` → ws 60003 命中）。
- **反事实演示**：活跃工作区 90002 时，对**非活跃**工作区品牌（`Aosulife` ws 510002）跑品牌级链路正常返回；名字歧义时按设计拒绝并列出全部候选。
- **历史一次性管线**（`b10_stage.py`／`b10_regression.py`／`harvest_daniel_enrichment.py`）仍有 2 处无参 `brands.list`：
  已登记为"不驱动取数"，**复用前必须先过本判据**。


### 15.5.4 品牌名单的归属判据：视频必须「点名到品牌」（2026-10-14 第二轮返工后固化）

**事故（第三轮做法：按任务来源归属，已被取代 —— 执行以 §15.5.4 为准）**：给 12 个品牌跑完品牌提及后，我按**任务来源**归属品牌 —— 跑 `Halliday-SKU` 任务的视频就记作本品。实测两个后果：
1. **别家的视频进了本品名单**：`Even Realities G2 + R1 Review`、`Top 10 Best AI Smart Glasses 2026`、`I Tried Gaming with AI GLASSES` 都被记作 Halliday 候选；
2. **竞品被"吃掉"**：同一条横评视频会在本品与多个竞品任务里各命中一次，先跑的本品任务整批吃掉 ⇒ **Brilliant Labs 从 15 条压到 5 条**（其实它的高表现视频被算给了本品）。

**根因（bundle 与实测）**：`searchMode="sku"` 任务的相关性**按品类判定**，不是按品牌。实测 `Halliday-SKU`（`skuTerms=['Halliday G2','Halliday AI glasses']`）的判定依据原文：
> "The video title '10 Best Smart Glasses in 2026 …' clearly indicates a discussion of smart glasses, **a target product category**."

⇒ **SKU 任务的 `relevanceLabel ∈ {confirmed, likely}` 只说明"视频属于该品类"，不等于"点名了该品牌"**。品牌名任务的噪声同理（`Halliday` 高表现 61 条里 59 条是足球运动员 Andy Halliday／歌手 Johnny Hallyday）。

**规则（四条 · 已进脚本 `_rework/rework_step7_build_final.py`）**：

| # | 规则 | 判据 |
|---|---|---|
| 1 | **归属看内容证据，不看任务来源** | 一条视频满足下列之一才算"点名到品牌 B"：① 标题／话题标签出现品牌或产品名；② 频道名含品牌（官方号）；③ `relevanceReasoning` 里**正面点名**到 B 或其产品（如 "explicitly mentions 'Halliday G2' at 0:01:00"） |
| 2 | **否定句是负证据** | 解析 `relevanceReasoning` 前先剔除否定句（`no exact mention`／`does not mention`／`does not specify`／`without mentioning`／`implicitly`）—— 否则 `No exact mention of "Halliday G2"` 这类句子会被当成点名证据（**实测假阳性来源**） |
| 3 | **证据取并集、读数取最高分** | "是否点名"在该视频**全部通过筛选的记录**上取并集（不同任务的判定依据写的不是同一件事）；但**一条视频只保留 `compositeIndex` 最高的一条记录**做读数，避免同一份交付件里同一视频出现两个评级 |
| 3b | 🔴 **证据还要跨快照取并集**（2026-10-14 实测） | **重新分析会重新生成判定文本** —— 同一批次重跑时，系统把某条视频的点名原话引用删掉了（该条在上一批次里有明确引用）。点名属**内容层证据**（与评分口径不同），因此**必须跨快照取并集**；只认最新快照会把**已点名**的视频误标为"未点名" |
| 4 | **交付件内自洽** | 说明页里"各品牌可选量（High／Good／Average／Low）"必须与主表**同口径、同脚本**产出（主表 5 条、说明写 4 条＝不合格） |

**品类级视频的处置**：只沾品类、不点名任何目标品牌的高表现视频（本轮实测候选 1,040 条中 **236 条**属此类）**不进任何品牌名单**；若投放侧确实需要"品类语境"的投放载体，**另出一张表**并在表内逐行标明"未点名任何目标品牌"，不得混进品牌名单。

**配套验收判据（写进 `rework_step9_selfcheck_final.py`，10 项）**：主表每行必须有"品牌点名位置"；本品表不得出现仅属竞品的视频；「品牌＋videoId」唯一（同一视频可在多个品牌名单里，同一品牌内不重复）；每品牌 ≤ 15 条；品牌内排名连续且分数降序；SOV 补充同 §15.5.3；说明页无 markdown 记号。

**本轮结果（2026-10-14 第四轮）**：主表 **146 条**（本品 **5** ＋ 竞品 **141**）＋ SOV 补充 **13 条** ＝ **159 条**；11 个竞对全覆盖（Ray-Ban Meta／Oakley Meta／XREAL／Rokid／Even Realities／RayNeo／MemoMind／VITURE 各 15，Solos 11，Dymesty 9，Brilliant Labs 1）。**本品只有 5 条是数据事实**：近 180 天内点名到 Halliday 产品、且相关性通过、≥1,000 观看的视频共 27 条，其中 High 5／Good 4／Average 6／Low 12 —— 需求方口径只要 High，故为 5 条。



### 15.5.5 名单类交付件的字段完整性与排序（2026-10-14 第五轮 · 需求方第四次反馈）

**需求方原话**：「**每行数据，视频对应的红人，粉丝量级，频道信息，以及播放数据都要完整**，并且需要**按照播放量从高到低排序**输出，
我看了一下 brand mentions 里面本品和竞品的视频数量**已经足够了**，所以**不需要再用 sov 的数据了**，
只需要把 **brand mentions 下所有 High Organic Performance 部分的视频**整理即可」

**判据（五条）**：

| # | 规则 | 落地 |
|---|---|---|
| 1 | **需求方说"够了"就不要自己收敛** | 取消"每品牌前 15 条"这类**自加上限**（它是我为了"清单易读"加的，需求方要的是品牌提及里 High 档**全收**）；确实需要收敛时必须先问 |
| 2 | **红人／频道字段逐行齐** | 频道名／频道账号（@handle）／频道链接／**订阅数（粉丝量级）**／频道平均观看／频道平均互动率；无公开数据的字段写「无官方数据」，**不留空** |
| 3 | **播放数据逐行齐** | 观看量／点赞／评论／互动率（(点赞＋评论)÷观看量）／观看表现档／互动表现档／表现评级；视频本身再给时长与发布时间 |
| 4 | **排序＝需求方指定的字段** | 交付表内**按观看量降序**，并给"播放量排名"列（名次与排序一致，便于引用"第 3 条"） |
| 5 | **数据源按需求方指定** | 需求方说"只用品牌提及"时，**不要再拼 SOV／曝光库数据**（口径混杂会让读者无法判断两条数据的可比性）；SOV 只在需求方明确要"关键词维度"时单独成表 |

**验收（写进自检脚本）**：① 子表清单与需求方要求一致（本版＝本品视频／竞品视频／说明与口径，**无 SOV 表**）；
⑥ 两表按观看量降序且名次连续；⑧ 上述字段逐行非空（None/空串即失败，`无官方数据` 视为已填）。
—— 本轮实测：主表 **821 条**（本品 5 ＋ 竞品 816），字段缺失 0，排序与名次全对。

**与 §15.5.4 的分工**：§15.5.4 管**谁能进名单**（点名证据），本节管**进了名单之后每行长什么样、按什么排序**。

### 15.5.6 品牌提及的原生筛选维度要用足（2026-10-14 第六轮 · 需求方第五次反馈）

**事故**：需求方在系统里看到「Halliday 品牌提及 · High Organic Performance」＝ **54 条**，我们交付的本品只有 **5 条**。差在三处：
① 我只用了 `sortBy/sortDir/relevanceFilter` 三个参数，**没用好系统原生的筛选维度**（视频形式 long/short、内容类型测评/对比/开箱、Rated Score、真实性、语言）；
② 我叠加了自造判据；
③ **品牌名任务与其 SKU 词任务没有合并成一个品牌池去重**（合并后才是 54 条，不合并只有 29 条）。

**字段口径（逐字取自 bundle，勿再自造）**

| 系统里看到的 | 后端字段 | 取值 |
|---|---|---|
| **Rated Score（0–5）** | `compositeIndex` | 加权分：观看 **40%**／互动率 **25%**／点赞 **20%**／评论 **15%**，四项都与该频道自身历史基准比较后加权；满分 5.00 |
| **表现评级：显著超出基准** | `overallPerformance == "Strong Outperform"` | 其余：超出基准 `Outperform`／平均 `Average`／低于基准 `Underperform`·`Strong Underperform` |
| 视频形式 | `videoFormat` | `long_form`（长视频）／`shorts`（短视频） |
| 内容类型 | `videoType` | 测评 `review`／对比 `comparison`／开箱 `unboxing`／教程 `tutorial`／提及 `mention`／新闻 `news`／其它 `other`／已筛除·不相关 `filtered_irrelevant`／赞助内容 `sponsored` |
| 单维度表现 | `viewsPerf`／`likesPerf`／`commentsPerf`／`erPerf` | 同评级枚举；四个维度可单独设门槛 |

**`getResults` 的服务端筛选参数（用足，别在本地重造）**：
`brandMentions.getResults({ jobId, page, pageSize, sortBy, sortDir, performanceFilter, videoTypeFilter, formatFilter, authenticityFilter, search, relevanceFilter, languageFilter })`
—— 证据：bundle 调用点 `getResults.useQuery({… performanceFilter: D, videoTypeFilter: A, formatFilter: X, authenticityFilter: re, search: N, relevanceFilter: _, languageFilter: K})`。

**四条规则**
1. **需求方给的门槛逐字执行**（本轮：Rated Score 严格 > 3.8、播放量严格 > 2,000、总体评级显著超出基准），并写进交付件说明页；
2. **先对齐界面数再往下加门槛**：复算"该品牌任务池里 High Organic Performance ＋ 相关性确认"的条数，**必须等于需求方在系统里看到的数字**（本品 54）——对不上说明池子合并/去重做错了，先修池子再谈筛选；
3. **品牌池＝品牌名任务 ＋ 其 SKU 词任务合并后按 videoId 去重**（一轮任务只覆盖品牌名或只覆盖产品词时，池子都是残的）；
4. **交付件必须给多口径梯度对照**（逐级：不要求点名 → 加 Rated Score → 加播放量 → 加点名），并逐品牌列出，让需求方看到每一道门槛的代价与"哪几家会归零"。

6. **"放宽窗口/放宽范围能不能补到东西"必须先实测再承诺**：本轮把本品窗口从 180 天放宽到 183 天并实跑两个任务（品牌名 709 条／SKU 413 条，远未触及 2,000 条上限），
   真正落在新增 3 天内的视频 **20 条**、其中点名品牌的仅 **2 条**（Rated Score **2.82／0.10**，均低于门槛）。
   **更正（0.9.194）**：更准确的说法是"前六条条件候选 **11 → 12 条**"（多出的 1 条落在第 180–183 天，观看 54,146／Rated Score 4.06），但**点名到品牌的那 1 条不变** ⇒ 结论方向不变（本品少的根因是"点名品牌 ＋ 高表现"的内容稀缺），但**不要说成"一条都没多"**。
   结论写法：本品名单薄的原因是"点名品牌且高表现的内容本身稀缺"，**不是窗口太窄或没取全**；不要用"再放宽一点就有了"来回避口径取舍。

**本轮实测（2026-10-14）**：口径一（显著超出基准＋相关性，合并池去重）本品 **54**／合计 1,090；＋Rated Score > 3.8 → 13／155；＋播放量 > 2,000 → 13／146；＋点名到品牌 → **本品 1／合计 90**（Dymesty／Brilliant Labs／Solos 三家归零）。结论：**"只要高表现"与"必须点名品牌"同时成立时，本品名单会薄到不可用** —— 这种冲突必须把代价摊给需求方看，由他选，不得自行放宽或加严。

### 15.5.7 写链＝权限驱动（四轴）＋ 写操作四道闸（2026-10-14 用户裁决后固化）

**用户口径（逐字要点）**：「Daniel 账号登陆后，**只要这个账号能够展示的模块对应的写自动开放**，对应**没有权限的模块就不能使用**
（写链对应的是**账号的使用权限，而不是审批**）」；追加：**保留执行前确认**；**删除类再确认一次**。

**① 写开放判据＝账号权限四轴（都取账号事实，带前端出处）**

| 轴 | 字段 | 说明 |
|---|---|---|
| 系统角色 | `auth.me.systemRole`（`super_admin`／`admin`／`user`／`viewer`…） | 前端 `RequireAuth` 与 Brand Mentions／Discovery／SOV／Dashboard／品类设置等模块**要求 `super_admin` 或 `admin``**；但**有些模块本来就没有角色要求**（如「红人名单」） |
| 账号状态 | `auth.me.userStatus` | `pending`／`suspended` 直接拒 |
| 工作区权益 | 工作区上下文的 `enabledFeatures`／`hasFeature(...)` | 计划档位派生的功能开关 |
| 配额 | `maxBrands`／`maxSearchesPerMonth`／`maxEmailsPerMonth` ＋ 当前用量 | 超限即拒（用量取不到时**如实写"未取到、不拦"**，不假装有数据） |

**② 写操作四道闸**（唯一实现入口，避免散落多处）：权限 → 删除类凭据 → 确认 → token 逐字比对 → 执行 → **回读校验** → **审计留痕**。
- 无权限 ⇒ 用户错误码 ＋ 人话理由（说明**哪一轴**不满足）；**禁止**再出现"写链未开放"这种工程临时态说法；
- 删除类在 `--confirm` 之外必须 `--delete-token <目标名>`（把目标名原样再写一遍，写错即拒；**缺凭据时不解析目标**，避免误伤）；
- 未确认＝干跑：打印"将发生什么＋影响范围（工作区/品牌/目标）"，零写入；
- 回读不过 ⇒ 内部错误码（写已提交但没对上，必须人工核对）；
- 审计：时间／账号（掩码）／角色／工作区／品牌／动作／影响范围／回读结果／是否回滚，落用户数据目录并可导出。

**③ 两条实测教训（都记在缺陷类里）**
1. 🔴 **权限判据必须逐条核对前端出处，不能凭"感觉该被拒"** —— 实测曾因此**意外真写**（`lists create` 在降级角色下照样被允许，因为该模块前端本无角色要求）。
   纪律：涉及"能不能做"的判据，一律引到出处（文件＋行号）；演练先按**更严**的假设，且先用干跑验证；任何意外写入**当场回滚＋回读确认＋如实上报**（见 CLS-78）；
2. 🔴 **回读校验要排除服务端托管字段**（`updatedAt`／系统自算评分等）—— 否则"写入成功"会被判成失败（实测 2 条 `ok=false` 审计记录由此产生，修掉后 `verified=true`；见 CLS-69 第二形）。

**④ 未验证要如实标注**：本例只接通 6 条真实写（品牌 3＋名单 3）；**触发采集类写的真实执行已于 2026-10-15 接通**（`TICKET-188`：6 条触发类写升 `live`，逐条最小真跑 **5 条走通／1 条未通** —— `sov` 写链 9/9 PASS；默认 `brands` 写链因**该工作区品牌位已满（`limit 2`／`used 2`）**返回编号却不落地，是**环境事实**不是实现缺陷；验收件＝`docs/product/daniel-copilot/_impl/A1-触发采集真跑验收-2026-10-15.md`）；删除真实数据的放行路径只在当场新建的临时对象上验证过。
🔴 **请求预算是按工序形态定的，不是全局常数**（2026-10-16 · `TICKET-192` 固化 · 判据真源＝`docs/product/daniel-copilot/08-触发采集真实执行-验收清单.md` 第一节的逐链路预算表）：**单步触发类**（一条命令一次发包）**≤3**；**多步工序**（如接管验收 `takeover check-writes` ＝ 建→改→删 ＋ 双回读）按「**最小步数 ＋ 每步 1 次**」给预算（实测 `brands` ≈8、`sov` ≈18），**不可能 ≤3** —— 既不要把为单步写的上限压到多步工序上（那是拿错尺子判它超标），也不要用"多步"给单步触发类开后门。三条禁令不因分档而放宽：**禁止为验退避制造 429／禁止并发压测／禁止对生产品牌做删除类写**。
**"写命令的开放级别"要在帮助文本与工具定义里写明**（真实可执行／只到干跑／沙箱演练），不要让调用方猜。

### 15.5.8 品牌提及 ／ Deep Review 的实测运维事实（13 条 · TICKET-167 固化 · 2026-10-15）

> **本节性质**：`TICKET-167` 要固化的那批事实，此前**只散在各票回报与 `_build/` 分析报告里**（能力层之外 ⇒ 下次同一个问题会再花一遍时间）。本节把它们**连出处与复跑命令一起**固化：**每条都给可复跑的只读命令 ＋ 本会话实测输出**，**不是只写结论**。
> **票面与盘面两处不符（如实登记）**：① 票面 §二 声明「**7 条**」，**实测表内 12 行**（编号 1–6、7b、7c、7、8、9、10）；② 其中 **8／9／10 三行缺「出处」列**（相对 3 列表头少一格）。本节按**行**固化 **12 条**（编号沿用票面，便于回查），另加**本会话实测的调用入口事实 1 条**（第 13 条）＝ **13 条**。
> **本节命令一律只读**：不触发采集（`runAnalysis`／`collectVideoSources`／`runVideoDeepReview`／`analyzeHighAttention` **一律不跑**）、不做任何写。**复跑夹具**：`brandId 4560003`（Euhomy）／任务 `d8e9b6fb-fd51-4b52-be82-2ae8a423b789`；`brandId 3690002`（Halliday）／任务 `04052185-224a-4b7b-bdea-676a7461db03`、`1bcd6fd2-859e-4e52-a263-3d0645fbf430`。
> **实现面与本节的边界**：这批事实的**实现**已落在 CLI 侧（`daniel mentions results` 的帮助文本 ／ `data/daniel-cli/contracts/read-envelope.md` ／ `data/daniel-cli/read_parity_check.py`）。**Skill 只写判据与复跑命令，不复制实现**（避免第二真源 · §19）。

**🔴 第 13 条 · 调用入口（本会话实测 · 先看这条，免踩"命令找不到"）**：**`daniel` 不在 PATH** —— `command -v daniel` **无输出、退出码 1**。**两种正确写法**（等价，任选）：

```bash
# 写法 A：工作区根相对路径 —— 跑命令、写回报、落文档一律用这一种
python3 data/daniel-cli/bin/daniel mentions status --brand 4560003 --job <任务编号> --json

# 写法 B：绝对路径 —— cwd 不在工作区根时用（bin/daniel 用 realpath 解析包根，任意 cwd 都能跑）
python3 "<工作区绝对路径>/data/daniel-cli/bin/daniel" schema --check
```

- **出处**：本会话实测（2026-10-15）。`command -v daniel` → **退出码 1**；写法 A／B 均实测 `--version` → `daniel 0.1.0`。
- **⚠️ 一个走不通的写法**：`python3 -m daniel_cli` **不可用** —— 包内无 `__main__.py`，实测报 `No module named daniel_cli.__main__; 'daniel_cli' is a package and cannot be directly executed`。
- **判据一句话**：凡是要把 daniel 命令交给别人（或写进回报/文档）时，**一律写写法 A 的完整前缀**；`daniel …` 这种写法在本机**必然 command not found**。

**一、读链与错误语义**

**第 1 条 · 未知 `jobId` 的错误语义不一致（同一页两个接口给不同的码）**

- **事实**：`brandMentions.getResults` 对**未知 jobId** 返回 **HTTP 500**（报文 `Brand Mention job not found or access denied`，**不是 404/400**）；而**同一个未知编号**调 `brandMentions.getStatus` 返回 **200 + `null`** ⇒ **同一页两个接口的错误语义不一致**（属服务端缺陷，可反馈）。
- **判据一句话**：**不能拿 `getResults` 的 500 当"编号写错"的判据**（它和内部错误同一个码）。本地能做的是**预检**：品牌任务清单**未触顶**时可断定"无此任务"（判用户错误），**触顶则不可断定**（保持内部错误）。
- **出处**：`tickets/TICKET-167-capability-layer-operational-facts.md` 表 #1（出处列：`TICKET-150` 回报直打路由复现 ＋ `TICKET-165` 独立复核稳定 3 次）；`docs/marketing/kol/_build/brand-mentions-promotion-status-独立复核.md` L89（三个非法输入各复现一次）／L150。
- **复跑命令**：
  ```bash
  # ① 绕过 CLI 本地预检、直打路由（只读 GET）—— 复现"500 vs 200+null"
  python3 data/daniel-cli/bin/daniel route probe --route brandMentions.getResults \
    --input '{"brandId":4560003,"jobId":"00000000-0000-0000-0000-000000000000","page":1,"pageSize":10,"relevanceFilter":"all"}' --json
  python3 data/daniel-cli/bin/daniel route probe --route brandMentions.getStatus \
    --input '{"brandId":4560003,"jobId":"00000000-0000-0000-0000-000000000000"}' --json
  # ② CLI 侧预检（走命令面 —— 日常用的是这一条）
  python3 data/daniel-cli/bin/daniel mentions results --brand 4560003 --job 00000000-0000-0000-0000-000000000000 --json
  ```
- **本会话实测**：① `getResults` → `"available": false` ／ `"error": "brandMentions.getResults 失败: HTTP Error 500: Internal Server Error"`；`getStatus` → `"available": true` ／ `"shape": "NoneType"` ／ `"sample": "null"`。② CLI 侧**退出码 2** ＋ 人话 `这个品牌下没有任务编号 …（本地核对过该品牌的任务清单，只有 1 条，未触上限）。该品牌现有任务：d8e9b6fb-…`；**清单触顶时**（该品牌任务 > 10 条）改报 `该品牌任务较多（清单已触上限 10 条），无法断定编号是否存在`（本会话在 Halliday 3690002 上实测到这行）。

**第 2 条 · `excludedIrrelevant` 是任务级统计，不是"本次请求排除了多少"**

- **事实**：该字段是**任务级**统计（"本次分析共有 N 条被判为不相关、不计入推广建议"），**`all` 口径下照样返回同一个值**（夹具实测两次都是 **18**）⇒ 它**与本次请求的筛选项无关**。
- **判据一句话**：**要表达"本次请求隐藏了多少"，只能用两个口径的服务端 `total` 相减**（114 − 96 ＝ 18），并**必须标明这是算术推导、不是服务端字段**。
- **出处**：`tickets/TICKET-167` 表 #2（出处列：`TICKET-150` 实测；属缺陷类 **CLS-68** 的新形）；缺陷类 `docs/marketing/skills/_DEFECT-CLASSES.md` L88；CLI 侧口径 `data/daniel-cli/contracts/read-envelope.md` §2.2（L60 起，逐字写明"不许把任务级统计说成本次被过滤"）＋ `daniel mentions results --help` 的返回说明。
- **复跑命令**：
  ```bash
  J=d8e9b6fb-fd51-4b52-be82-2ae8a423b789
  for f in "" "--relevance-filter all"; do
    python3 data/daniel-cli/bin/daniel mentions results --brand 4560003 --job $J $f --json 2>/dev/null \
      | python3 -c "import sys,json;r=json.load(sys.stdin)['read'];print('echo',r['filter']['echo'],'total',r['total'],'taskLevelExcluded',r['filter']['taskLevelExcluded']['count'])"
  done
  ```
- **本会话实测**：默认 → `echo {'relevanceFilter': 'confirmed_likely'}` ／ `total 96` ／ `taskLevelExcluded 18`；`all` → `echo {'relevanceFilter': 'all'}` ／ `total 114` ／ `taskLevelExcluded 18`（**同一个 18** ⇒ 任务级，得证）。
- **配套**：`read.filter.taskLevelExcluded.note` 逐字写着 `任务级统计：本次分析共有 18 条被判为不相关、不计入推广建议；与本次请求的筛选项无关（本仪器只搬运，不自行计算）`。

**第 7b 条 · 读结果信封（`daniel.read.v1`）的适用边界**

- **事实**：**只有 `mentions`（`jobs`／`status`／`results`）与 `intel`（`actions`／`keywords`／`topics`／`reviews`）这两组读命令的输出顶层有 `read` 键**；`brands`／`lists`／`search`／`sov`／`ct`／`authenticity`／`account` 各读命令**没有**。
- **判据一句话**：**判据只有一条 —— 顶层有没有 `read`**；**「没有 `read` 不是缺陷」**（那条命令尚未接入读链，业务载荷照常可用）；**要判"这份数据是不是全量、下一页怎么取"，只有带 `read` 的命令给得出**，不带 `read` 的必须按该路由自己的口径判。
- **出处**：`data/daniel-cli/contracts/read-envelope.md` §7（L205 起，逐模块表）；`docs/marketing/kol/_daniel-integration/02-brand-mentions.md` §8.1（L283–L299，含同一判据原文与 `TICKET-166` 逐条只读实测）。
- **复跑命令**（7 个模块一次跑完）：
  ```bash
  J=d8e9b6fb-fd51-4b52-be82-2ae8a423b789
  for c in "mentions results --brand 4560003 --job $J --page-size 10" "intel actions --brand 3690002" \
           "brands list" "lists by-brand --brand 3690002" "sov categories --brand 3690002" \
           "ct campaigns --brand 3690002" "account whoami"; do
    printf '%-42s' "$c"
    python3 data/daniel-cli/bin/daniel $c --json 2>/dev/null \
      | python3 -c "import sys,json;d=json.load(sys.stdin);print('ok=%s 顶层有 read=%s'%(d.get('ok'),'read' in d))"
  done
  ```
- **本会话实测**（7/7 与 §7 表一致）：`mentions results` 有 ／ `intel actions` 有 ／ `brands list` 无 ／ `lists by-brand` 无 ／ `sov categories` 无 ／ `ct campaigns` 无 ／ `account whoami` 无。

**二、分页与取全**

**第 3 条 · 偏移分页在并列排序下不稳定（同一份数据会既重复又漏）**

- **事实**：`pageSize=50` 分 3 页取同一份 **114 条**，实得 **114 行但只有 113 个不同 `videoId`**（**重复 1、漏 1**）⇒ 分页取数的"集合差"会被凭空放大。
- **判据一句话**：**总数 ≤ 单页上限（实测 200）时必须一次取全、不分页**；必须翻页时，取完**断言「条数 == 不同 id 数」**，**断言不过 ⇒ 该批数据不可信、不得引用**（重取或显式标注不可信）。
- **出处**：`tickets/TICKET-167` 表 #3（出处列：总监实测 ＋ `TICKET-165` 独立复现）；缺陷类 **CLS-82**（`_DEFECT-CLASSES.md` L106）；`read-envelope.md` §2.1（L44–L59，另一批实测记 114 → **110**）；规则实现 `data/daniel-cli/read_parity_check.py` 的 `fetch_all_rows()`（信封另给 `singlePageMax`／`rowsUnique`／`dedupOk`／`stabilityNote` 四个字段兜住它）。
- **复跑命令**：
  ```bash
  python3 - <<'PY'
  import json, subprocess
  J = "d8e9b6fb-fd51-4b52-be82-2ae8a423b789"; rows = []
  for p in (1, 2, 3):
      o = subprocess.run(["python3", "data/daniel-cli/bin/daniel", "mentions", "results", "--brand", "4560003",
                          "--job", J, "--page", str(p), "--page-size", "50",
                          "--relevance-filter", "all", "--json"], capture_output=True, text=True)
      rows += json.loads(o.stdout)["data"]["results"]
  ids = [r["videoId"] for r in rows]
  print("条数", len(rows), "不同 id", len(set(ids)), "重复", len(ids) - len(set(ids)))
  PY
  ```
- **本会话实测**：`条数 114 ｜ 不同 id 113 ｜ 重复 1`（**与票面逐字相符**）。对照：同一任务一页取全（`--page-size 200`）→ `rowsUnique 114 ／ dedupOk true ／ totalPages 1`。

**第 10 条 · 同一不稳定在第二个任务上独立复现（且不是"任务有问题"）**

- **事实**：Halliday 任务 `04052185…`（247 条）按 `pageSize=200` 翻两页取回 **247 行但只有 246 个不同 id** ⇒ 该批数据**不可信、不得引用**；同一批里任务 `1bcd6fd2…`（277 条）**277 = 277 通过** ⇒ **是否触发取决于排序键的并列分布，不是任务本身有问题**。
- **判据一句话**：**"这次没重复"不构成"下次安全"** —— 每次翻页取数**都要**跑去重断言，并按任务逐条报「条数／不同 id 数」。
- **出处**：`tickets/TICKET-167` 表 #10（**该行票面无「出处」列** —— 由本节补）；同源缺陷类 **CLS-82**。
- **复跑命令**：把第 3 条脚本的 `J` 换成下面两个任务、`--page-size` 改 200、页码 (1, 2)：
  `04052185-224a-4b7b-bdea-676a7461db03` ／ `1bcd6fd2-859e-4e52-a263-3d0645fbf430`（品牌用 `--brand 3690002`）。
- **本会话实测（今日复现，与票面逐字相符）**：`04052185` → 条数 247 ／ 不同 id **246** ／ 重复 1；`1bcd6fd2` → 条数 **277** ／ 不同 id **277** ／ 重复 **0**。

**三、口径隐行**

**第 4 条 · 默认口径会隐掉不相关条目（而被隐掉的 18 条里恰好有 2 条「需谨慎」）**

- **事实**：界面与 CLI 默认口径都是 `confirmed_likely`（`total 96`），全量需显式 `all`（`total 114`），**差 18 条**；服务端自报 `excludedIrrelevant = 18`，96 ＋ 18 ＝ 114 账平。被藏的 18 行**全部**是 `relevanceLabel = unlikely`，其中**需谨慎 2 条、疑似推广 0 条**。
- **判据一句话**：**查"品牌被挂到别的产品/品类上"必须看全量口径** —— 这类问题恰好落在默认视图挡掉的那一档里。
- **出处**：`tickets/TICKET-167` 表 #4（出处列：总监实测 ＋ `TICKET-165` 独立复核）；`_build/brand-mentions-promotion-status-独立复核.md` L175（**把"隐藏 23 条"更正为 18 条** —— 23 正是按自算集合差得到的错值，见第 3 条）；同源 `02-brand-mentions.md` L112（`relevanceFilter` 取值域与缺省）。
- **复跑命令**：与第 2 条同一段循环（读 `read.total` 与 `read.filter.echo`）。
- **本会话实测**：默认 `96`（`echo relevanceFilter=confirmed_likely`）→ `all` `114` → **差 18**。

**四、评分与标签**

**第 6 条 · Rated Score（`compositeIndex`）的完整算式（含两条未公示细节）**

- **事实**：① 四分量按 **观看 40／互动率 25／点赞 20／评论 15** 加权，各比率**封顶 5×**；② **某分量的"频道均值 = 0"时该分量被剔除、其余权重按比例重归一化**（**未公示**）；③ **原始观看比 < 0.3 时分数被替换为 `viewsRatio`**（官方面板公示）；④ **`promotionStatus = likely_promoted` 再 ×0.5**（**未公示**）；⑤ 结果取 2 位小数。跨样本拟合 **6,700/6,715 ＝ 99.78%**。
- **判据一句话**：**评分不是"看个分数字段"就行** —— 两条未公示细节（分母为 0 时重归一化、疑似推广砍半）会让"按公示权重手算"与平台值差出量级；**凡写"这条分数不可比／可比"之前，先确认这三条**。
- **出处**：`tickets/TICKET-167` 表 #6（出处列：`TICKET-165`，40 任务／31 品牌／6,715 行；总监独立复算确认 —— 漏掉重归一化时 104/114，补上后 113/114）；`_build/brand-mentions-promotion-status-独立复核.md` L76（`Views Ratio < 0.3` 为**官方面板公示**，`:3467`）／L102（第 ⑤ 步 ×0.5 未公示）／L110／L162；复算脚本 `docs/marketing/kol/_build/evidence-t165-independent/model3.py`（docstring ①–⑤ 与本节逐条对应）。
- **复跑命令**（离线，零网络；读同目录 `xb-*.json` 39 个跨品牌样本 ＝ 6,601 行）：
  ```bash
  python3 docs/marketing/kol/_build/evidence-t165-independent/model3.py | tail -12
  ```
- **本会话实测**：`样本文件 40 个；总行数 6715；|预测-实际|<=0.011 命中 6700（99.78%）`；`status 分布 {'normal': 5924, 'caution': 436, 'likely_promoted': 355}`；`likely_promoted 检验 n=355 命中(±0.01)=353 中位偏差=0.000`；`caution n=436 命中=436`。

**第 7 条 · 界面口径自相矛盾（5× vs 10x），**数据裁决为 5×****

- **事实**：同一页两处说法不一致 —— 表格列头写 `each ratio is capped at 5×`（`:2520`），「评分方法」面板写 `All ratios capped at 10x`（`:3454`）；**用数据可裁决：正确的是 5×** —— 夹具里 `viewsRatio` 恰好 ＝ `5.00` 的 13 条，其**原始比值（播放量 ÷ 频道均值播放量）落在 5.051–65.638** ⇒ 若封顶是 10×，这些行会记 5.05…10.00 而不是一律记 5.00。**另**：该面板**公示了权重与 `Views Ratio < 0.3` 规则，但对两个标签（疑似推广／需谨慎）只字未提**。
- **判据一句话**：**厂商面板文案与列头冲突时，以数据裁决、并把裁决过程写进交付件口径页**；**不把面板文案当判据**。
- **出处**：`tickets/TICKET-167` 表 #7（出处列：`TICKET-165`）；`_build/brand-mentions-promotion-status-独立复核.md` L49–L54（含 `data-loc` 行号 `:2520`／`:3454`／`:3467`）。
- **复跑命令**（离线，读前端 chunk）：
  ```bash
  grep -o "each ratio is capped at [0-9]*×\|All ratios capped at [0-9]*x" \
    docs/marketing/kol/_build/evidence-t165-independent/assets/BrandMentions-CbA4Ooa0.js | sort | uniq -c
  ```
- **本会话实测**：`1 All ratios capped at 10x` ／ `1 each ratio is capped at 5×`（**两句同时存在，矛盾得证**）。

**第 5 条 · `promotionStatus`（疑似推广／需谨慎）是"只出不可筛"字段**

- **事实**：向 `getResults` 入参塞 **34 个** promotion／flag 类候选键（`promotionStatusFilter`／`promotionStatus`／`promotionFilter`／`flagFilter`／`riskFilter`／`cautionFilter` …）**全部被服务端静默忽略**（不报错、也不筛）；键名 `promotionFilter` **确实存在**，但它的枚举是 `highly_recommended|recommended|neutral|not_recommended`（管"推广建议"，与这两个标签无关）。⇒ 目前**无法按标签拉全量**，只能读全量再本地筛。
- **判据一句话**：**"筛不出来"先怀疑该字段不在入参 schema 里**（探法：用非法值触发 zod 枚举报错）；**静默忽略 ≠ 筛了没结果** —— 被忽略时返回的是**未筛的全量**，按"筛出来就这几条"读会写错结论。
- **出处**：`tickets/TICKET-167` 表 #5（出处列：`TICKET-165` 独立复核）；`_build/brand-mentions-promotion-status-独立复核.md` L87（34 键清单与 schema 探测法）／L88（`exportMentions` 实际 14 列里**没有** `promotionStatus`：导出会丢标签）。
- **复跑命令**：
  ```bash
  J=d8e9b6fb-fd51-4b52-be82-2ae8a423b789
  for k in promotionStatus flagFilter statusFilter promotionFilter; do
    echo "--- $k"
    python3 data/daniel-cli/bin/daniel route probe --route brandMentions.getResults \
      --input "{\"brandId\":4560003,\"jobId\":\"$J\",\"page\":1,\"pageSize\":10,\"relevanceFilter\":\"all\",\"$k\":\"likely_promoted\"}" --json 2>/dev/null \
      | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print('available',d.get('available'),'|',str(d.get('sample'))[:60])"
  done
  ```
- **本会话实测**：`promotionStatus` → `available True`（**静默忽略**：返回的仍是未筛数据）；`flagFilter` → `available True`（同上）；`statusFilter` → `available True`（同上）；`promotionFilter` → `available False`（**枚举拒绝**，说明这个键真实存在、但取值域不含标签）。

**第 7c 条 · 两个标签的实测反推规则（**复现平台输出，不是官方判据**）**

- **事实**（2026-10-15 穷举反推 ＋ 独立保留集验证，用**已跑出的 brand mentions 数据本身**得到，未依赖 Deep Review）：**疑似推广** ＝ `播放比 viewsRatio > 2.79` 且 `互动率比 erRatio ≤ 0.295`（保留集 **89/89 ＝ 100% 覆盖、误报 2**）；**需谨慎** ＝ `综合指数 compositeIndex > 1.96` 且 `互动率表现 erPerf = Strong Underperform`（保留集 **58/69 ＝ 84%、误报 0** ⇒ 是**充分条件**，不是必要条件；第二类「低指数 ＋ 互动差、多伴随相关不匹配」**尚无零误报规则，标为未完成**）。⚠️ **阈值作用在未四舍五入的内部值上**（取整成 2.8／0.3 会多 8 条误报），与「低观看量 `viewsRatio < 0.3` 替换分数」同一形态。
- **判据一句话**：这是**复现平台输出的经验规则**，用来"解释我看到的标签"；**不得当官方判据、不得当筛选门槛**（何况该字段本来就不可筛，见第 5 条）。**样本边界**：2,358 行／2 品牌／7 任务／**同一账号**，跨账号未验；疑似推广有 **2/91 例外未复原**（不猜原因）。
- **出处**：`tickets/TICKET-167` 表 7c（出处列：`docs/marketing/kol/_build/brand-mentions-promotion-status-口径实测.md` 第七节）；该报告 **§七**（L211–L248）：规则表 L218–L221、未四舍五入 L227–L235、第二类未覆盖 L237–L239、反推边界 L242–L248。
- **复跑命令**（离线，读 39 个跨品牌样本 `xb-*.json`；**与票面的保留集不是同一批样本**）：
  ```bash
  python3 - <<'PY'
  import glob, json
  def rows_of(p):
      d = json.load(open(p))
      if isinstance(d, dict):
          if 'results' in d: return d['results']
          for v in d.values():
              if isinstance(v, dict) and 'results' in v: return v['results']
      return d if isinstance(d, list) else []
  tot = lp = lp_hit = lp_fp = ca = ca_hit = ca_fp = 0
  for p in sorted(glob.glob('docs/marketing/kol/_build/evidence-t165-independent/xb-*.json')):
      for r in rows_of(p):
          tot += 1
          vr = float(r.get('viewsRatio') or 0); er = float(r.get('erRatio') or 0)
          ci = float(r.get('compositeIndex') or 0); st = r.get('promotionStatus')
          promo = vr > 2.79 and er <= 0.295
          caut = ci > 1.96 and r.get('erPerf') == 'Strong Underperform'
          if st == 'likely_promoted': lp += 1; lp_hit += promo
          elif promo: lp_fp += 1
          if st == 'caution': ca += 1; ca_hit += caut
          elif caut: ca_fp += 1
  print('rows', tot, '｜ 疑似推广 覆盖 %d/%d 误报 %d ｜ 需谨慎 覆盖 %d/%d 误报 %d'
        % (lp_hit, lp, lp_fp, ca_hit, ca, ca_fp))
  PY
  ```
- **本会话实测**：`rows 6601 ｜ 疑似推广 覆盖 344/347 误报 20 ｜ 需谨慎 覆盖 368/429 误报 0`。⇒ **方向与票面一致**（需谨慎规则 **0 误报**、覆盖率 ~86%；疑似推广覆盖率 ~99%），但**数字不同**：票面的 89/89 与 58/69 来自**保留集（4 个全新 Halliday 任务）**，**该保留集原始件未随仓落盘** ⇒ **只能追溯到报告，不能就地复跑**（如实登记；界面回传值经四舍五入、按取整阈值判定会额外多出误报，正与 §7.2 的警告同一形态）。

**五、Deep Review 的能力边界**

**第 8 条 · 源采集会在 `transcript` 段停住、客户端无解**

- **事实**：四段采集 `metadata(skipped)/comments/transcript/replay`；`comments` 完成后 `transcript` ＋ `replay` 一直 `running`，**分段 `updatedAt` 冻结 23 分钟不动**、**总进度停在 50%**；**重发 `collectVideoSources` 返回 `reused:true`（幂等、不重新入队）且状态不变** ⇒ 界面上的「重试」按钮**只覆盖 replay 段，对 transcript 段停住无效**。另：**账号内不存在已完成的 Deep Review 证据**（抽样 5 个任务含 3 个 `eligible>0` 的，全部 `not_started`／`analyzed=0`）⇒ 想观测 `contentClassification` 字段结构**只能自己发起采集**。
- **判据一句话**：**该能力目前不可依赖** —— 工序里要写「**可能长时间无进展且无法客户端恢复**」，**不许把它排进交付关键路径**；要跑必须走"会触发采集"的授权通道（本 Skill 默认不跑）。
- **出处**：`tickets/TICKET-167` 表 #8（**该行票面无「出处」列** —— 由本节补）；现场证据 `docs/marketing/kol/_build/evidence-t165-independent/getVideoEvidence-euhomy.json`（sha256 前 16 ＝ `3c23430ac03b370b`）。
- **复跑命令**（只读探测，**不触发采集**）：
  ```bash
  python3 data/daniel-cli/bin/daniel route probe --route brandMentions.getVideoEvidence \
    --input '{"brandId":4560003,"jobId":"d8e9b6fb-fd51-4b52-be82-2ae8a423b789"}' --json
  ```
- **本会话实测**：同一任务今天再读 —— `"status": "preparing"` ／ `batches[0].currentStage: "transcript"` ／ `progressPercent: 50` ／ `analyzedCount: 0` ／ `matchingCount = selectedCount = eligibleCount = 2` ⇒ **停住状态跨小时保持**（比票面记的 23 分钟更久；本会话未做任何客户端恢复尝试，故"能否恢复"未验证）。对照：该任务的**主体分析**早已 `done`（`progressDetail: Analysis complete: 114 videos (≥500 views), 77 channels`）⇒ **停住的是 Deep Review 这一层，不是品牌提及分析**。

**第 9 条 · 入选谓词（Deep Review 的 eligible 集合）**

- **事实**：入选谓词 ＝ **`overallPerformance = Strong Outperform` ＋ 已确认相关（`relevanceLabel = confirmed`）＋ 长视频 > 120 秒**；服务端自报计数器为 `getVideoEvidence` 的 `matchingCount`／`selectedCount`／`eligibleCount`（实测**三者相等 ＝ 2**）。⚠️ 该谓词要求 `Strong Outperform`，而 `likely_promoted` 的评分**被砍半**（见第 6 条 ④）⇒ **「疑似推广」的视频很难进入选集合**；做对照实验时**必须另外确认服务端是否接受「非入选」的 `resultId`**。
- **判据一句话**：**入选范围以"服务端给的三个计数器"为准**，我方按条件复算只能作**交叉验证**（不一致时以服务端为准并回报）；该谓词要求 `Strong Outperform`，所以**"想看疑似推广的深度分析"这条路本身就被评分规则掐住了**。
- **出处**：`tickets/TICKET-167` 表 #9（**该行票面无「出处」列** —— 由本节补）；`_build/brand-mentions-promotion-status-独立复核.md` L152（独立复算命中**恰好同样的 2 条**，且两条 `promotionStatus` 都是 `normal`）；旁证 `_daniel-integration/02-brand-mentions.md` L242（盲区 B1：Halliday 现存任务 `videos[]` 都是空数组、按界面逻辑须先触发 `analyzeHighAttention` 才进 `preparing`）。
- **复跑命令**（① 服务端计数器：见第 8 条那条 probe；② 离线复算谓词）：
  ```bash
  python3 -c "
  import json
  rows = json.load(open('docs/marketing/kol/_build/evidence-t165-independent/full200-euhomy.json'))['results']
  e = [r for r in rows if r['overallPerformance']=='Strong Outperform'
       and r['relevanceLabel']=='confirmed' and r['durationSeconds']>120]
  print('eligible', len(e), [(r['id'], r['videoId'], r['durationSeconds'], r['promotionStatus']) for r in e])"
  ```
- **本会话实测**：`eligible 2 [(4441506, 'Gbgc9ZFd2TE', 614, 'normal'), (4441456, 'yzhvqZCcDYg', 651, 'normal')]` ⇒ **与 `getVideoEvidence` 的 `matchingCount/selectedCount/eligibleCount = 2` 一致**；两条 `promotionStatus` **都是 `normal`** ⇒ 想验证"疑似推广"的深度分析判据**正样本为 0**（与票面 8／9 两条的结论一致）。

