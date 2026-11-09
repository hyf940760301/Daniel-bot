# 阶段 0 · 语义层基础 · 定稿（业务字典 ＋ 操作手册）

> 状态：**定稿候选（FINAL-CANDIDATE）· 待 Jack 审批**；本文件不含代码改动、不新增第二个文件、未动飞书。
> 日期：2026-11-08 ｜ 执行：管线 A ｜ 审批人：Jack
> 落点：`daniel-bot/specs/PHASE0-ONTOLOGY-FINAL.md`
> 上游：`daniel-bot/specs/PHASE0-ONTOLOGY-DRAFT.md`（1,373 行）＋ `daniel-bot/specs/CAPABILITY-GAP-AUDIT.md`（199 行）＋ 本轮已确认决策 5 条。
> 本文件把草案收口为可审批的定稿：**决策已落的写进正文，未落的留在 §7，不替 Jack 拍板。**

---

## 0. 读法与口径

### 0.1 依据（五类；其中任务书与 v0.4 为草案转引，其余三类实读）

| 类 | 文件 | 本文用它回答什么 |
|---|---|---|
| 任务书 | `Daniel-Bot-营销助手定位与迭代方案 (3).md` §4.1–4.7／§5／§8 | 语义层构成、四条硬规则、人工确认节点 |
| 设计稿 | `daniel-bot/docs/versions/03-语义层设计方案-v0.4.md` | P0 范围（10 指标 ＋ 5 概念）、五类对象 |
| 草案 | `daniel-bot/specs/PHASE0-ONTOLOGY-DRAFT.md` | 每个概念／指标／能力的明细与出处链 |
| 审计 | `daniel-bot/specs/CAPABILITY-GAP-AUDIT.md` | 路由／命令／工具三面差距与 C 类清单 |
| 实测 | 包内代码与语料（逐条引在正文） | 本文件里每一个可核事实的最终依据 |

### 0.2 本文交的七样东西

| # | 交付物 | 位置 | 对应验收 |
|---|---|---|---|
| 1 | 决策记录（Q-01／Q-02／Q-03） | §1 | 验收① |
| 2 | 业务字典（5 概念 ＋ 10 指标） | §2 | 验收② |
| 3 | 登记表扩展方案（schema 变更，不新增文件） | §3 | 验收③ |
| 4 | 操作手册（CAP-01～08） | §4 | 验收④ |
| 5 | 能力可用性分级 A／B／C | §5 | 验收⑤ |
| 6 | 下一步卡片约束 | §6 | 验收⑥ |
| 7 | 收敛后的待确认清单 | §7 | 验收⑦ |

### 0.3 硬边界

- 只写本文件；不改 `lib/*`、`daniel_cli/*`、`contracts/*`、母本、`_ONTOLOGY.json`。
- 不新增语料束、不新增 MCP server、不新增常驻进程、不新建登记表文件。
- 不把「建议」写成「已定」：凡标 `【待确认 Q-xx】` 的，一律是未定项，不得被下游当口径引用。
- 不写形容词；判断只以「可核事实 ＋ 判定条件」出现。

### 0.4 三种出处写法（全文一致）

| 写法 | 含义 | 例 |
|---|---|---|
| `路径:行号` | 该行逐字可核 | `daniel-bot/packages/0.11.0/lib/normalize.js:199` |
| `路径#字段` | 该 JSON 键路径逐字可核 | `contracts/kol-list.json#交付件schema.列` |
| `命令` | 该命令在 `schema.py` 里声明过 | `daniel lists add-items --list-id 8310034` |

> 路径相对仓库根 `/Users/huyifan/Desktop/DeepSeek Harness`。写不出这三种之一的，本文件写「待确认」，不编。

### 0.5 `data_status` 三值与「面键」六值

**`data_status`（本文件全文只用这三个值）**

| 值 | 含义 | 交付件写法 |
|---|---|---|
| `reliable` | 口径与实现一致、样本条件写死、可复算 | 可作判断依据，仍需带窗口与样本 N |
| `unreliable` | 口径存在但会系统性误导 | 不得单独作对外结论；必须标口径或换替代口径 |
| `unknown` | 库内找不到逐字口径／实现，或分母未声明 | 只能写「按 XX 口径读到 X」 |

> 草案 §1.19 曾称「已上线用 `reliable_when_sample_ok`／`unstable_when_small_sample`」。**该说法不成立**：随包语料 `_ONTOLOGY.json` 与 `12-ontology-registry.md` 里没有 `data_status` 字段，也没有这两个值（全仓检索仅命中方案文档 `04-语义登记表-完整工程方案-v1.2.md:52/59`）。本文件按任务书三值首登，v1.2 两值方案不采用。此项原为 Q-12，现已关闭（§7.2）。

**面键（`surfaces` 的键，六值；不在条目上另设「取值面」字段）**

| 面键 | 指什么 | 典型实现 |
|---|---|---|
| `api_field` | 平台接口直接返回的字段 | `discovery.getChannelInsight` |
| `detail_drawer` | 与 Daniel 详情抽屉同口径的现算值 | `lib/normalize.js:217` |
| `pipeline_v2` | 名单产线（有界全量池）口径 | 母本 L724（无代码） |
| `list_item` | 名单条目字段 | `lists.getItems` |
| `manual_formula` | 语料里写死的公式（无代码） | 母本 L683 |
| `outreach_system` | 建联系统（Nox）报表／状态 | `noxinfluencer email …` |

### 0.6 三处实读差异（2026-11-08 复核：① 已对齐，②③ 仍待整改）

| # | 文档说法 | 仓库实测（2026-11-08） | 本文件处置 |
|---|---|---|---|
| ① | 工具数 19（旧口径） | **2026-11-08 已对齐**：`tests/golden/baseline.json:3` `registeredCount: 20` ≡ `lib/index.js` 20 处 `ctx.tools.register`（含 `daniel_open_research_commit`，L1204） | 全文按 **20** 写（§1.4、§4.0）；硬约束改为「**P0 不新增第 21 个工具**」 |
| ② | CLI 命令 91（审计 §1.1） | `schema.py` AST 数 `c()` ＝ **97**；差额 6 ＝ 本轮新增 `lists add-items` ＋ `mentions chart/top-channels/evidence/export` ＋ `search enrich` | 手册按 97 写（§4.0），审计的 91 标为「本轮之前」 |
| ③ | 官方库退役、指引文案已改 | `lib/index.js:926–963` 已写「已停用，请勿调用」；但同一工具的「改走」指引仍写 `daniel_open_research`「**自动选默认项并执行**」（L928、L952），与两段式冲突 | 列为 Q-02 的遗留整改项（§1.2），手册按两段式写（§4.1） |

### 0.7 与草案的差异清单（决策带来的改写）

| # | 草案位置 | 草案写法 | 定稿写法 | 依据 |
|---|---|---|---|---|
| 1 | §1.7／§1.18 | 均播 M2／M3 两个窗口混在一条契约列名下 | 拆两条登记：`…drawer_28d` ／ `…pool_12m100`，窗口进 id 与 label | Q-03 |
| 2 | §1.20#33 | `取值面` 与 `surfaces` 并存，待 Q-01 | 只保留 `surfaces`，面键＝六值；不设 `取值面` 字段 | Q-01 |
| 3 | §2.1 G5 | 官方库作为「不得重试」的门禁 | 保留门禁，同时把工具／语料的旧文案列为整改项 | Q-02 |
| 4 | §2.4 G1 | 「往名单加人没有命令」 | 改为 `lists add-items` 两段式写，含拆批／回读／审计 | 本轮新增事实 |
| 5 | §2.1 | open 研究「自动选默认项并执行」 | 改为 plan → 用户确认 → commit | 本轮新增事实 |
| 6 | §1.19 | `data_status` 两套词并存（Q-12） | 只有任务书三值；旧两值说法证伪 | 实读 |
| 7 | §3.1 | 23 条待确认 | 23 → 13（10 已解决；9 阻塞 ＋ 4 可延后） | §7 |

---

## 1. 决策记录

### 1.1 Q-01 登记表形态：扩展现有 `_ONTOLOGY.json`，用 `surfaces` 表达面

| 项 | 内容 |
|---|---|
| 决策 | **扩展现有登记表** `daniel-bot/packages/0.11.0/vendor/data/daniel-cli/mcp/corpus/_ONTOLOGY.json`（现 4 条，字段 `id/type/label/owner/status/stage`）；**不新建** `取值面` 字段，面一律写进条目的 `surfaces` 结构 |
| 不选什么 | 不新建第二份登记表文件；不把 `取值面` 作为顶层字段另起一套；不迁移到新目录 |
| 改了什么 | ① 类型加 `concept`；② `surfaces` 从「只留在 raw 文本里」升级为「键＝面键、值＝该面的 kind／window／sample_rule／min_sample／data_status／unit／source」；③ `external_only` 沿用（值域加 `none`）；④ 顶层新增 `definition`／`data_status`／`source`／`superseded_by`；⑤ 现有 4 条不删：`metric.creator.avg_views_long` 置 `status: superseded`，其余 3 条原样保留 |
| 为什么 | 已上线的 4 条已随包分发（`_ONTOLOGY.json` 有 `corpus_version`），改结构要同时动母本附录 B、切分器、重建器、门禁四处；扩展现有结构只动「附录 B ＋ 抽取函数」两处，且不产生第二真源 |
| 代价 | `daniel_cli/ontology.py` 目前只抽 `id/type/label/owner/status/stage/availability` 与 `scenarios/groups`（`ontology.py:145–182`），**不抽 `surfaces`**；要让索引层可机读 `surfaces`，需在 `parse_entries()` 增加一个抽取函数（实施项 I-2，不在本文件改） |
| 验收影响 | C19-e 要求「带 `surfaces` 的指标必须声明 `external_only`」（`mcp/check_ontology.py:141–149`）；本文件 10 条指标全部给 `external_only`（§2.7） |

### 1.2 Q-02 官方库通道退役：工具与语料文案按「零发包」改写

| 项 | 内容 |
|---|---|
| 决策 | 官方库通道（`discovery.searchRoster` → 工具 `daniel_roster_search`）**已退役**；工具说明与语料里「用它找红人」的文案一律改为「已停用，改走 deep／open」，退役口径为**零发包** |
| 代码现状（已落） | `lib/index.js:926–963`：工具描述首句「已停用，请勿调用」；`execute` 只回 `channel_retired`，`本次是否发包: '没有'`（L961） |
| 语料现状（已落） | `mcp/corpus/kol-discovery/references/10-discovery-steps.md:924–930` 已写「已停用、不再做恢复评估」「零发包」；全语料检索「官方库」无正向可用表述（过滤「退役／停用／不再／已裁决／不可用」后为 0 行） |
| **遗留（未落）** | `lib/index.js:928` 与 `:952` 的「改走」指引仍写 `daniel_open_research`「**自动选默认项并执行**」；该工具已于本轮改为两段式（L1120–1202 出计划；L1205–1252 提交），文案与行为不一致 |
| 处置 | 列入实施项 I-3：把两处「自动选默认项并执行」改为「先出计划、用户确认后才提交」；不改工具签名、不改行为 |
| 运行面提示 | 本会话的工具清单仍显示旧描述「在 YouTube 官方库里找红人就用这个工具」；说明**已安装插件未随包内代码更新**。部署后需重新装载插件，否则模型仍会先撞退役通道 |

### 1.3 Q-03 均播拆窗：抽屉 28 天 与 池「12 个月 ∩ 最新 100 条」各一条登记

| 项 | 内容 |
|---|---|
| 决策 | 均播的**权威对外口径拆成两条登记**：① 详情抽屉面（近 28 天、中位数）；② 名单产线面（最近 12 个月 ∩ 最新 100 条、中位数）。**窗口写进名字与定义**，两条各自 `id`／`label`／`definition` |
| 改了什么 | `metric.creator.avg_views.drawer_28d`（M2）与 `metric.creator.avg_views.pool_12m100`（M3）；两者在登记表里平级，不互相引用为「同一指标的别名」 |
| 契约现状 | `contracts/kol-list.json:63` 的列名是「长视频均播（近28天中位数）」，`:73` 为必填列，`:76` 排序按该列降序 ⇒ **该列只能映射到 M2（28 天）**；M3 需要另起列名（如「长视频均播（12 个月∩最新 100 条·中位数）」），改契约属下一阶段，本文件只登记 |
| 为什么不合并 | 母本 L724 的实测：同一 KOL 两批显示 **17,850 vs 9,632**；两个窗口不是同一件事。合并会让读者把两个数当同一个数 |
| 旧条目 | `metric.creator.avg_views_long` 置 `status: superseded`，`superseded_by: [metric.creator.avg_views.drawer_28d]`；其 `surfaces.reported`（最新 30 条均值）在定稿 10 条里**没有承接项**，列为 P1 待核（§7.5 N-8） |
| 保留的两条 | M1（接口 28 天均值，`unreliable`）与 M4（按成交形式组合，CPM 分母）不属于「权威对外均播」：M1 标 `external_only: none`，M4 标 `external_only: none`；它们仍登记，因为代码与谈判流程实际在用它 |

### 1.4 其余已确认口径（本轮一并写死）

| # | 项 | 定稿值 | 出处 |
|---|---|---|---|
| 1 | 工具数 | **20**（`baseline.json:registeredCount` ＝ 代码注册数）；P0 硬约束改写为「**不新增第 21 个工具**」 | `tests/golden/baseline.json:3` |
| 2 | 工具名现状 | 代码 **20** 个注册名（含 `daniel_open_research_commit`），与基线一致 | `lib/index.js` 20 处 `ctx.tools.register` |
| 3 | CLI 命令 | **97**（本轮 91 ＋ 6） | `schema.py` AST 数 `c()` |
| 4 | 语料版本 | **0.9.206** | `mcp/corpus/_MANIFEST.json` `corpus_version` |
| 5 | 语料规模 | **8 束／41 文件／25 切片／源文 7,164 行** | `_MANIFEST.json` `bundleCount/total_files/total_slices/source_lines` |
| 6 | 登记表条目 | 现 **4** 条 → 定稿 **19** 条（18 active ＋ 1 superseded） | `_ONTOLOGY.json` `entry_count`；§2.20 |

### 1.5 本轮新增事实（写进手册）

| # | 事实 | 证据 | 落在手册 |
|---|---|---|---|
| F1 | `lists add-items` 已落地：写操作、两段式（干跑 → `--confirm`）、单批 ≤100 自动拆批、已在名单自动跳过、写后回读条数与成员、干跑与真跑各留一条审计 | `schema.py:393–422`；`mod_lists.py:661–830`；`mod_lists.py:873–876`；`commands/_common.py:134–164` | CAP-04 |
| F2 | `daniel_open_research` 已拆 plan／commit 两段式，与 deep 共用计划账本（TTL 5 分钟、一次计划只能提交一次） | `lib/index.js:1120–1202`（plan）、`:1205–1252`（commit）；`lib/research.js:16` | CAP-01 |
| F3 | 新增只读命令 `mentions chart / top-channels / evidence / export` | `schema.py:548/565/592/609`；`mod_mentions.py:312–320`（只读 HANDLERS） | CAP-05 |
| F4 | 新增只读命令 `search enrich`：不改任何数据、不写文件、不发 mutate、无需 `--confirm`；频道链路每批 ≤100、邮箱链路每批 ≤50 | `schema.py:467–499`；`mod_search.py:57–92` | CAP-01 |
| F5 | `mentions top-channels --limit` 合法 **5–50**（默认 10；1／3／100 被服务端拒，本地先拦不发包） | `schema.py:590–596`；`mod_mentions.py:110/249–262` | CAP-05 |
| F6 | **open 与 deep 提交后都落一条写审计**（`daniel account audit` 可见，同一份 `write-audit.jsonl`）：open＝`open-research-commit`，deep＝`deep-research-commit`，字段逐项一致（2026-11-08 补齐 deep） | `lib/worker.py::_audit_commit`／`_audit_open_commit`／`_audit_deep_commit`；回归 `tests/test_deep_audit.py` | CAP-01 |
| F7 | 草案 Q-12 的前提不成立：随包登记表没有 `data_status` 字段，也没有两值词表 | `_ONTOLOGY.json`；`12-ontology-registry.md`（全仓检索仅命中 v1.2 方案文档） | §0.5／§7.2 |

### 1.6 决策对全文的影响（一句话版）

| 决策 | 影响的章节 |
|---|---|
| Q-01 | §2 全部（字段形态）、§2.19、§3 全部 |
| Q-02 | §0.6③、§1.2、§4.0、§4.1、§5.4、§6.3 |
| Q-03 | §1.3、§2.7、§2.9、§2.10、§2.18、§2.20、§7.3（Q-16） |


### 1.7 实施注记（不是决策项，落地时执行）

| # | 注记 | 落点 | 判据 |
|---|---|---|---|
| I-1 | 工具名冻结：不再新增工具名；基线与代码同为 **20**（含 `daniel_open_research_commit`），口径已归一，无需再在发版说明里解释差额 | `tests/golden/baseline.json`、`lib/index.js` | 不出现第 21 个工具名 |
| I-2 | `ontology.py` 增 `surfaces`／`external_only`／`data_status`／`definition`／`source` 抽取 | `daniel_cli/ontology.py` | 单测：M6 两面、M2 单面 |
| I-3 | 退役工具「改走」两处文案改为两段式 | `lib/index.js:928、:952` | 文案不再出现「自动选默认项并执行」 |
| I-4 | C19-g（面键白名单）／C19-h（顶层与面级 `data_status` 一致） | `mcp/check_ontology.py` | 反例必须报红 |

---

## 2. 业务字典

### 2.0 概念与指标的分工

| 类 | 回答什么 | 判定问题 | 例 |
|---|---|---|---|
| 概念 `concept` | 「这个词指哪个实体」 | 能不能被**指向**（有唯一标识或唯一枚举） | 品牌、频道、名单 |
| 指标 `metric` | 「这个数怎么算、在哪个面算」 | 能不能被**计算**（有分子／分母／窗口） | 均播、互动率、CPM |

判例：`订阅数` 是指标（可算、有快照时点）；`频道` 是概念（有 `channelId`）。

### 2.1 概念总表（5 个）

| id | label | 唯一键 | 数据落点 | owner | status | data_status | 出处 |
|---|---|---|---|---|---|---|---|
| `concept.brand` | 品牌 | `brandId`（整数） | Daniel Brands | 业务-红人组 | active | reliable | `contracts/real-brands-inventory.json` |
| `concept.product` | 型号／产品 | **无实体 id**（`skuTerms` 检索词） | Daniel 任务配置 | 业务-红人组 | active | unknown | `references/60-data-layer.md:387` |
| `concept.channel` | 渠道（平台） | 平台枚举（6 值） | 各取数工具 | 业务-红人组 | active | reliable | `tools/voc-crawler/STATUS.md` |
| `concept.creator` | 红人／频道 | `channelId`（`UC…`） | Daniel Discovery／Lists | 业务-红人组 | active | reliable | `_DANIEL-FIELD-DICTIONARY.md:134` |
| `concept.list` | 名单 | `listId`（整数） | Daniel Lists | 业务-红人组 | active | reliable | `schema.py#lists.*` |

> 共同约束：每个概念都必须能回答「在哪个工作区、哪个品牌下」；跨工作区混用是本仓历史错因。

### 2.2 `concept.brand` 品牌

```yaml
id: concept.brand
type: concept
label: 品牌
owner: 业务-红人组
status: active
stage: ""
key: brandId
definition: Daniel 里的品牌实体：品牌编号＋名称＋工作区＋品类＋目标市场＋行业关键词＋样品价＋竞品；是检索口径、背调、提及任务、声量统计的共同事实源。
value_domain: brandId 为整数；name 允许为空、允许同名（服务端不拦空名／重名，不可用名字当唯一键）；必须归属一个 workspaceId；targetCountries 为 ISO 国家码数组；sampleCost 为样品计价（不是零售价）；competitors 以品牌自己配置的为准。
data_status: reliable
source: "contracts/real-brands-inventory.json#交付件schema.列; references/60-data-layer.md:239,369"
```

| 项 | 内容 |
|---|---|
| 读命令 | `daniel brands list [--workspace] [--limit]`／`brands show --brand`／`brands competitors --brand` |
| 写命令 | `brands create/update/clone/delete`（均 `write=True`、`writeStage=live`） |
| 已知坑 1 | `brands list` 的取数范围两份材料冲突：`references/60-data-layer.md:239` 写「只当前工作区」，`schema.py#brands.list.returns` 写「账号可见全部」；**未实测前逐条核对工作区编号**（N-7） |
| 已知坑 2 | 同名品牌可跨工作区 ⇒ 必须让用户给编号，不猜（`processes.json#daniel-api-03` 前置条件） |
| 已知坑 3 | `sampleCost` 是样品计价；对外只能写 "a $599 product"／"valued at $599"（`_DANIEL-FIELD-DICTIONARY.md:376–381`） |

### 2.3 `concept.product` 型号／产品

```yaml
id: concept.product
type: concept
label: 型号／产品（SKU）
owner: 业务-红人组
status: active
stage: ""
key: skuTerms（无实体 id）
definition: 品牌下的具体产品型号；在本仓不是实体，而是三样东西的合称：品牌提及的检索单元、报价分母的形式依据、产品说明块的事实来源。
value_domain: 型号名为自由文本（来自任务配置的 skuTerms）；任务模式为 brand（品牌名）或 sku（型号词）；品牌池 = 品牌名任务 ∪ 其 SKU 词任务，按 videoId 去重。
data_status: unknown
source: "references/60-data-layer.md:383-390,456"
```

| 项 | 内容 |
|---|---|
| 读命令 | `daniel mentions jobs --brand`（型号只体现在任务名里）；无独立读写命令 |
| 已知坑 1 | `searchMode="sku"` 的相关性**按品类判**，不等于点名品牌；`relevanceLabel ∈ {confirmed,likely}` 只说明属于该品类（`references/60-data-layer.md:387–390`） |
| 已知坑 2 | 只跑一个池是残的；两池合并后才是界面数（`:456`） |
| 未定 | 型号是否作为概念登记（Q-07）；本条按「登记为 concept、标 unknown」写，待 Jack 确认 |

### 2.4 `concept.channel` 渠道（平台）

```yaml
id: concept.channel
type: concept
label: 渠道（平台）
owner: 业务-红人组
status: active
stage: ""
key: 平台枚举
definition: 取数与触达的平台，不指销售渠道、不指品牌自己的 YouTube 频道。
value_domain: "youtube／reddit／kickstarter／avsforum／rv_forum／nox_email（6 值）"
data_status: reliable
source: "tools/voc-crawler/STATUS.md; docs/marketing/skills/voc-intelligence.md:33-47"
```

| 值 | 承载能力 | 入口 |
|---|---|---|
| `youtube` | 检索／档案／提及／声量／真实性 | Daniel CLI（`search`/`mentions`/`sov`/`ct`/`authenticity`） |
| `reddit` | VOC | `tools/voc-crawler/platform-reddit.mjs` |
| `kickstarter` | VOC | `crawl-ks.mjs` |
| `avsforum` | VOC | `platform-avsforum.mjs` |
| `rv_forum` | VOC | `voc-crawl-rv.md` |
| `nox_email` | 建联（邮件） | `noxinfluencer email …` |

| 项 | 内容 |
|---|---|
| 已知坑 1 | 「频道」在本仓有两义：本条＝平台；`brands show` 的「频道」＝品牌自己的 YouTube 频道（`youtubeChannelId`，`lib/normalize.js:341`） |
| 已知坑 2 | 同一平台有多种取数路径、口径不同；`web_search` 只能发现候选，不得当覆盖证据（`voc-intelligence.md:68`） |
| 未定 | 概念名用「渠道」还是「平台」（Q-08） |

### 2.5 `concept.creator` 红人／频道

```yaml
id: concept.creator
type: concept
label: 红人／频道
owner: 业务-红人组
status: active
stage: ""
key: channelId
definition: 一个 YouTube 频道；「红人」是业务称呼，「频道」是数据单位。合作主体以频道计，不以人计。
value_domain: channelId 为 UC 开头的字符串（唯一键）；handle 形如 @xxx 且可为 null；title 为官方全文；country 是频道所在地，不是受众国家；subscribers 为整数快照。
data_status: reliable
source: "_DANIEL-FIELD-DICTIONARY.md:134,200-204; lib/index.js:886"
```

| 项 | 内容 |
|---|---|
| 一次拿全 | `daniel_kol_profile(handle, videos)`（四块 ＋ 三个状态字段） |
| 名单侧 | `daniel lists items --list-id --with-handle` |
| 解析 | `daniel ct resolve-channel` |
| 已知坑 1 | `handle` 可为 null ⇒ 交付件必须有 `channelId` |
| 已知坑 2 | 两套视频投影字段名不同（`views/publishTime` vs `viewCount/publishedAt`），混用会静默取到 `None` |
| 已知坑 3 | 官方号／媒体机构号要识别，否则会把品牌自己的号当红人（`processes.json#discovery-09`） |

### 2.6 `concept.list` 名单

```yaml
id: concept.list
type: concept
label: 名单（Saved List）
owner: 业务-红人组
status: active
stage: ""
key: listId
definition: 挂在某品牌下的红人集合，有 listId、名称、条目数；一条条目＝一个 channelId。名单属于品牌，不属于账号；同一频道可出现在多份名单里。
value_domain: listId 为整数；必须归属一个 brandId；条目数 ≥0，与页面人数不一致时以读到的条目为准并标注；名单名非空、允许同名。
data_status: reliable
source: "schema.py#lists.*; processes.json#daniel-api-01"
```

| 项 | 内容 |
|---|---|
| 读命令 | `by-brand`／`items`／`saved-channel-ids`／`share-status`／`auto-priority-status` |
| 写命令 | `add-items`／`create`／`rename`／`delete`（删除需 `--delete-token`） |
| 已知坑 1 | 人数口径：`processes.json#daniel-api-01` 已定「与系统页面人数对不上时，以读到的成员为准并如实标注」 |
| 已知坑 2 | 删除不可逆；`--delete-token` 要求把目标名原样再写一遍（`schema.py` 头注释写链③） |

### 2.7 指标总表（10 个）

> 每条指标在登记表里是一个 yaml 块；本表是索引。**均播按 Q-03 分成 M2／M3 两条**，窗口进名字与定义。

| # | id | type | label | owner | status | 面键 | 窗口 | data_status | 出处 |
|---|---|---|---|---|---|---|---|---|---|
| M1 | `metric.creator.avg_views.reported` | metric | 均播（接口均值 · 近 28 天） | 业务-红人组 | active | `api_field` | 近 28 天 | unreliable | `lib/worker.py:234`；`lib/normalize.js:232` |
| M2 | `metric.creator.avg_views.drawer_28d` | metric | 均播（详情抽屉 · 近 28 天 · 中位数） | 业务-红人组 | active | `detail_drawer` | 近 28 天（不足 3 条退回最新 30 条） | reliable | `lib/normalize.js:173–229` |
| M3 | `metric.creator.avg_views.pool_12m100` | metric | 均播（名单产线 · 最近 12 个月 ∩ 最新 100 条 · 中位数） | 业务-红人组 | active | `pipeline_v2` | 最近 12 个月 ∩ 最新 100 条 | reliable（有条件） | 母本 L724；`contracts/kol-list.json:63` |
| M4 | `metric.creator.avg_views.package` | metric | 均播（按成交形式取值 · CPM 分母 N） | 业务-红人组 | active | `manual_formula` | 随所选面 | unknown | 母本 L683；`kol-negotiation/SKILL.md:60` |
| M5 | `metric.creator.subscribers` | metric | 订阅数（快照） | 业务-红人组 | active | `api_field` | 取数时点 | reliable | `lib/worker.py:209`；`lib/normalize.js:342` |
| M6 | `metric.creator.engagement_rate` | metric | 互动率 | 业务-红人组 | active | `api_field` ＋ `list_item` | insight 28 天；名单条目不开窗 | unreliable | `lib/normalize.js:143/202/211/242` |
| M7 | `metric.quote.cpm` | metric | CPM（报价评估） | 业务-红人组 | active | `manual_formula` | 报价时点 | unreliable | 母本 L31／L3220–3227／L683 |
| M8 | `metric.sov.platform_share` | metric | 声量份额（平台返回 share） | 业务-红人组 | active | `api_field` | `--days`（默认 30） | unknown | `.kol-tools/daniel_sov.py:226–232` |
| M9 | `metric.sov.mention_share` | metric | 声量份额（提及份额 · 固定竞争集） | 业务-红人组 | active | `manual_formula` | ≥1 个月（口径声明定） | reliable（有条件） | `kol-execution-sov/SKILL.md:97` |
| M10 | `metric.outreach.reply_rate` | metric | 回复率（建联） | 业务-红人组 | active | `outreach_system` | `--window A..B` | unreliable | `nox-weekly/SKILL.md:73/191` |

> owner 统一沿用已上线 4 条的「业务-红人组」；是否改为「总监（代签）」或加 `signed_by` 属 Q-15，未定。
> `external_only` 本表省略，逐条见 §2.8–2.17；10 条全部声明，满足 C19-e。

### 2.8 M1 `metric.creator.avg_views.reported` 均播（接口均值 · 近 28 天）

```yaml
id: metric.creator.avg_views.reported
type: metric
label: 均播（接口均值 · 近 28 天）
owner: 业务-红人组
status: active
stage: ""
surfaces:
  api_field:
    kind: mean
    window: last_28_days
    sample_rule: 该范围 videoCount>0；vod/shorts 的 videoCount=0 时该字段缺失（正常，不是错误）
    min_sample: 1
    data_status: unreliable
    unit: 次播放
    source: "lib/worker.py:234; lib/normalize.js:232"
external_only: none
data_status: unreliable
definition: 窗口内总播放 ÷ 窗口内新视频数（均值）；字段为 discovery.getChannelInsight 的 stats.{overall,vod,shorts}.averageViewsPerVideo，三个范围各自独立、不可互算。
source: "lib/worker.py:234; lib/normalize.js:155-161,232-249; docs/marketing/skills/kol-intelligence.md:674"
```

| 项 | 内容 |
|---|---|
| 样本条件 | `timeRange="last_28_days"`；不传 `timeRange` 返回 `null`（曾是「取不到」误判的根源） |
| status_reason | 均值把长尾流量摊到新视频上：母本 L674 实测 **216K vs 视频清单均值 34K**；`normalize.js:161` 实测 **7,820 vs 665**（差一个数量级） |
| 替代口径 | M2（默认对外）、M3（名单产线） |
| 使用限制 | 只能写「按平台 28 天均值口径读到 X」；**不得**与 M2／M3 并列比大小；`external_only: none` ⇒ 不进对外交付件 |
| 实现位置 | 取数 `lib/worker.py:234 op_insight()`；兜底落块 `lib/normalize.js:232 performanceBlock()`（块内自报「平台汇总（均值口径，非页面口径）」，L244） |

### 2.9 M2 `metric.creator.avg_views.drawer_28d` 均播（详情抽屉 · 近 28 天 · 中位数）

```yaml
id: metric.creator.avg_views.drawer_28d
type: metric
label: 均播（详情抽屉 · 近 28 天 · 中位数）
owner: 业务-红人组
status: active
stage: screening
surfaces:
  detail_drawer:
    kind: median
    window: last_28_days
    sample_rule: 长视频=contentType VIDEO_ON_DEMAND 且 views>=100；短视频=SHORTS（无播放阈值）；28 天内且条数>=3 用该批，否则退回最新 30 条
    min_sample: 5
    data_status: reliable
    unit: 次播放
    source: "lib/normalize.js:173,188,192,199,217"
external_only: detail_drawer
data_status: reliable
definition: 长视频与短视频各自播放量的中位数；「整体」=长视频样本∪短视频样本（不是全部视频：播放<100 的长视频页面本来就不计）；窗口近 28 天，不足 3 条退回最新 30 条。
source: "lib/normalize.js:155-229; docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md:144-171"
```

| 项 | 内容 |
|---|---|
| 样本条件 | 窗口取样本：28 天内 ≥3 条即用该批；出结论门槛 N≥5（硬／软见 Q-21）。平台实测只给 20 条（`limit` 无效）⇒ 块内必须标「样本 N 条」，不假装与页面同源同量（`normalize.js:170–171`） |
| status_reason | 与 Daniel 详情抽屉同口径现算（注释 L163 逐字提到 `daniel_ui_parity.py::video_list_stats`）；偶数取上中位（L188） |
| 替代口径 | M1（仅兜底）、M3（名单产线） |
| 使用限制 | ① 必须带「样本 N 条」；② `N<5` 只能说「样本不足」；③ 与 M1 混用时必须标面 |
| 契约映射 | `contracts/kol-list.json:63`「长视频均播（近28天中位数）」→ **只指向本条** |
| 待确认 | 现行登记项写的 `sample_rule` 是「近 28 天、**时长 > 60 秒**」，与代码（`VIDEO_ON_DEMAND` 且 `views≥100`，无时长条件）不一致 ⇒ Q-16；本文件按代码写 |

### 2.10 M3 `metric.creator.avg_views.pool_12m100` 均播（名单产线）

```yaml
id: metric.creator.avg_views.pool_12m100
type: metric
label: 均播（名单产线 · 最近 12 个月 ∩ 最新 100 条 · 中位数）
owner: 业务-红人组
status: active
stage: screening
surfaces:
  pipeline_v2:
    kind: median
    window: last_12_months ∩ latest_100_videos
    sample_rule: 有界全量池（最近 12 个月 ∩ 最新 100 条 → 去重 → 剔 views<100）内 VOD 播放量中位数
    min_sample: 50
    data_status: reliable
    unit: 次播放
    source: "docs/marketing/skills/kol-intelligence.md:724"
external_only: pipeline_v2
data_status: reliable
definition: 有界全量池（最近 12 个月 ∩ 最新 100 条 → 去重 → 剔 views<100）内 VOD 播放量的中位数；池内样本低于 50 条时须标「池量不足」，并同时报页数／池量／池内 VOD 数／Shorts 占比。
source: "docs/marketing/skills/kol-intelligence.md:724; contracts/kol-list.json:63,73,76"
```

| 项 | 内容 |
|---|---|
| 样本条件 | 窗口实际低于 **50 条**时须标「池量不足」；实现形态是 **2 页 × 50**（`pageSize` 上限 50，传 100 → HTTP 400） |
| 实现位置 | **仓库内没有实现函数**；口径只以文字存在于母本 L724 |
| status_reason | 母本判定为「名单产线唯一口径」，能解决同名两数；但无代码、无门禁，只能靠执行方自觉 |
| 替代口径 | M2（样本更短但可现算） |
| 使用限制 | 池量不足必须写「池量不足」，不能只给数；与 M2 同时出现必须分列并各标窗口 |
| 契约缺口 | 契约只有 28 天列名；本条需要新列名（下一阶段改契约，本文件只登记） |

### 2.11 M4 `metric.creator.avg_views.package` 均播（按成交形式取值）

```yaml
id: metric.creator.avg_views.package
type: metric
label: 均播（按成交形式取值 · CPM 分母 N）
owner: 业务-红人组
status: active
stage: negotiation
surfaces:
  manual_formula:
    kind: derived
    window: 随所选面
    sample_rule: 1 长→长视频均播；1 短→短视频均播；1 长+1 短→两者相加；必须写明用的是哪个面
    min_sample: 5
    data_status: unknown
    unit: 次播放
    source: "docs/marketing/skills/kol-intelligence.md:683"
external_only: none
data_status: unknown
definition: 按本行成交形式取值：1 长→长视频均播；1 短→短视频均播；1 长+1 短→两者相加；N 的取值面必须与本行 CPM 同面同窗。
source: "docs/marketing/skills/kol-intelligence.md:683; .agents/skills/kol-negotiation/SKILL.md:60"
```

| 项 | 内容 |
|---|---|
| status_reason | 公式明确，但「用哪一面的均播」没有强制绑定；分母换面，CPM 可差一倍以上（母本 L724：17,850 vs 9,632） |
| 使用限制 | 交付件出现 `N` 或「均播」列时，必须与 CPM 分母同面同窗；不同面并列 ⇒ 视为违规（`kol-list.json#自检 K1`） |
| 待确认 | 默认面（Q-17） |

### 2.12 M5 `metric.creator.subscribers` 订阅数（快照）

```yaml
id: metric.creator.subscribers
type: metric
label: 订阅数（快照）
owner: 业务-红人组
status: active
stage: screening
surfaces:
  api_field:
    kind: snapshot
    window: 取数时点
    sample_rule: 单频道单次；来源覆盖 getChannelDetail 6/6、parallelSearch 约 40–70%、Job 路线 100%
    min_sample: 1
    data_status: reliable
    unit: 人
    source: "lib/worker.py:209; lib/normalize.js:342"
external_only: api_field
data_status: reliable
definition: 频道订阅数快照，整数、不压缩（要能与页面的 523,922 逐格对上）。
source: "lib/worker.py:209; lib/normalize.js:147,342; docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md:294"
```

| 项 | 内容 |
|---|---|
| 样本条件 | 字段为空 ≠ 该频道不合格；空值者下推下一层，不据此淘汰 |
| status_reason | 三个来源同名同义、单位一致；风险是覆盖率不是口径（已写死在样本条件） |
| 使用限制 | 必须标取数时点；不同行取数日期不同要逐行标 |

### 2.13 M6 `metric.creator.engagement_rate` 互动率（双面）

```yaml
id: metric.creator.engagement_rate
type: metric
label: 互动率
owner: 业务-红人组
status: active
stage: screening
surfaces:
  api_field:
    kind: ratio
    window: insight 近 28 天；表现块分母用该范围全量视频，不开窗
    sample_rule: (Σlikes+Σcomments)/Σviews，分母用同一批样本；views=0 返回 null
    min_sample: 1
    data_status: unreliable
    unit: 小数 0–1（insight）
    source: "lib/normalize.js:202,211,242"
  list_item:
    kind: ratio
    window: 名单条目快照
    sample_rule: lists.getItems.engagementRate 原值
    min_sample: 1
    data_status: unreliable
    unit: 百分数（1.6 = 1.6%）
    source: "lib/normalize.js:143; _DANIEL-FIELD-DICTIONARY.md:439-442"
external_only: list_item
data_status: unreliable
definition: (Σlikes+Σcomments)/Σviews，分母用同一批样本；同一业务名有两个面、两种单位，交付前统一成百分数 2 位并标来源分支。
source: "lib/normalize.js:143,202-211,242; _DANIEL-FIELD-DICTIONARY.md:439-442,481"
```

| 项 | 内容 |
|---|---|
| status_reason | ① 单位两套差 100 倍；② 分母开窗不一致（均播开窗、互动率不开窗）；③ 名单条目与洞察层同名不同源 |
| 使用限制 | 对外交付只用 `list_item` 面；`api_field` 面仅用于档案判断并标「洞察面」；两个来源不得同一列排名 |
| 结构说明 | Q-14（是否单开一条 `list_item` 指标）按 Q-01 的结构解决：面写在同一条的 `surfaces.list_item`，不新开 id；如 Jack 要求单开，只改 id 不改数据 |

### 2.14 M7 `metric.quote.cpm` CPM（报价评估）

```yaml
id: metric.quote.cpm
type: metric
label: CPM（报价评估）
owner: 业务-红人组
status: active
stage: negotiation
surfaces:
  manual_formula:
    kind: ratio
    window: 报价时点
    sample_rule: 一行一个报价；报价与 N 同面同窗；同一行只允许一个 CPM
    min_sample: 1
    data_status: unreliable
    unit: 美元／千次播放
    source: "docs/marketing/skills/kol-intelligence.md:683,3220-3227"
external_only: none
data_status: unreliable
definition: CPM = 报价 ÷ N × 1000，N = M4（按成交形式取的均播）；套餐按 $80–100 判读，分母为相加值。
source: "docs/marketing/skills/kol-intelligence.md:31,683,3220-3227; .agents/skills/kol-negotiation/SKILL.md:41-48,60"
```

| 项 | 内容 |
|---|---|
| status_reason | ① 分母可换面（母本 L724：17,850 vs 9,632）；② 母本 L31：8 处砍价回测，百分比式命中 6/8、CPM 反推式命中 0/8 且系统性高估约 2 倍 ⇒ CPM 降级为「上限校验」 |
| 使用限制 | 判断词只有三种（报价合理／报价偏高／报价过高，母本 L4126–4131）；`$60–80`／`$80–100` 是内部参考基准不是硬门槛；不得把 CPM 当唯一判据 |
| 待确认 | 基准区间是否仍现行（N-2）；是否进随包语料（Q-10） |

### 2.15 M8 `metric.sov.platform_share` 声量份额（平台返回）

```yaml
id: metric.sov.platform_share
type: metric
label: 声量份额（平台返回 share）
owner: 业务-红人组
status: active
stage: sov
surfaces:
  api_field:
    kind: share
    window: --days（默认 30）
    sample_rule: 同一品类大盘内被收录视频；--country 不传时取品牌档案第一个市场
    min_sample: 1
    data_status: unknown
    unit: 百分数 1 位小数
    source: ".kol-tools/daniel_sov.py:226-232"
external_only: api_field
data_status: unknown
definition: daniel sov overview 返回的各品牌 share，百分比 1 位小数，由服务端计算，我方只读不重算；品牌不在结果里返回 None，不臆造 0。
source: ".kol-tools/daniel_sov.py:226-246; mcp/corpus/kol-daniel-api/references/60-data-layer.md:242,249"
```

| 项 | 内容 |
|---|---|
| status_reason | **分母未声明**：是「品类大盘全部收录视频」还是「竞争集各品牌之和」，服务端无文档、本仓无逐字公式；实测数与大盆读法相容但不能证明 |
| 使用限制 | 必须写市场与窗口；品牌不在结果里写「该品牌不在本次统计内」，不写 0%；与 M9 并列必须标「不同分母」 |
| 待确认 | 分母（Q-04，可延后） |

### 2.16 M9 `metric.sov.mention_share` 声量份额（提及份额）

```yaml
id: metric.sov.mention_share
type: metric
label: 声量份额（提及份额 · 固定竞争集）
owner: 业务-红人组
status: active
stage: sov
surfaces:
  manual_formula:
    kind: share
    window: 由口径声明定，≥1 个月
    sample_rule: 品牌提及 ÷（自身+竞争集品牌）提及 ×100%；提及逐条回源核验；情感三档抽样判定并记录抽样规则与样本量
    min_sample: 1
    data_status: reliable
    unit: 百分数
    source: ".agents/skills/kol-execution-sov/SKILL.md:87-104,97"
external_only: manual_formula
data_status: reliable
definition: SOV = 品牌提及 ÷（自身+竞争集品牌）提及 ×100（%）；固定竞争集、同一市场、同一渠道、同一时间窗；必须与情感同读（负向高声量是警告不是胜利）。
source: ".agents/skills/kol-execution-sov/SKILL.md:87-104; processes.json#execution-sov-07"
```

| 项 | 内容 |
|---|---|
| status_reason | 公式与分母写死（固定竞争集），能复算；风险在输入是否核验过 ⇒ 「提及逐条回源核验」是成立条件 |
| 使用限制 | 先有口径声明；报告首段写声明、全文一致；竞争集以品牌档案自己配的竞对为准，不得按份额前三收窄（`references/60-data-layer.md:360–362`） |

### 2.17 M10 `metric.outreach.reply_rate` 回复率（建联）

```yaml
id: metric.outreach.reply_rate
type: metric
label: 回复率（建联）
owner: 业务-红人组
status: active
stage: outreach
surfaces:
  outreach_system:
    kind: ratio
    window: --window A..B
    sample_rule: 回复 ÷ 发送；回复人数=有红人来信的会话数；已送达=发送−退订；已读=收件人中 opened 人数；口径按收件人逐人状态
    min_sample: 1
    data_status: unreliable
    unit: 百分数
    source: ".agents/skills/nox-weekly/SKILL.md:73,191"
external_only: outreach_system
data_status: unreliable
definition: 回复 ÷ 发送；按收件人逐人状态算，不用接口 arrive 字段单算一套；跨批次合并须带合计行且不与单批口径混。
source: ".agents/skills/nox-weekly/SKILL.md:69-74,191; .agents/skills/nox-cli/SKILL.md:130-140"
```

| 项 | 内容 |
|---|---|
| status_reason | **三个分母并存**：报表 `sent_count`、会话数、逐人状态；`nox-cli:138` 逐字「到达率分母是发送，不是会话；与逐人状态推出的『已送达』可能对不上，页面上统一用逐人状态」；会话数 < 发送数，用会话数冒充发送数会系统性偏高 |
| 使用限制 | 唯一合法口径是逐人状态；读会话会清掉 Nox 未读标记 ⇒ 看板主指标用「待回复」不用「未读数」，且必须告知业务（`nox-cli:154–158`） |
| 待确认 | 是否纳入 P0 语义层（Q-05） |

### 2.18 均播四条的取舍（为什么是 4 条而不是 1 条）

| 条目 | 面 | 对外？ | 为什么保留 |
|---|---|---|---|
| M1 | `api_field` | 否（`none`） | insight 兜底路径实际在用；不登记会导致兜底值无 id 可挂 |
| M2 | `detail_drawer` | **是**（`detail_drawer`） | 与页面逐字复现，是对外交付默认口径 |
| M3 | `pipeline_v2` | **是**（`pipeline_v2`，名单场景） | 母本判定的名单产线唯一口径 |
| M4 | `manual_formula` | 否（`none`） | CPM 的分母 N 必须与成交形式绑定，是组合规则不是频道值 |

> 跨面不比数（v0.4 §9.3）；交付必带三件：指标 id ＋ 面键 ＋ `data_status`（不可靠面还要带替代口径）。缺一件即「未标口径的数字」，对应 `contracts/kol-list.json#自检 K1` 第 1 类违规。

### 2.19 与现有 `_ONTOLOGY.json` 的逐字段映射表

> 左侧是**现在索引里真实存在的字段**（`_ONTOLOGY.json` 条目：`id/type/label/owner/status/stage/availability/raw`，个别条目另有 `scenarios/groups`）；右侧是定稿登记项字段。

| # | 现有字段（索引层） | 现有取值／形态 | 定稿字段 | 映射方式 | 索引抽取 | 说明 |
|---|---|---|---|---|---|---|
| 1 | `id` | `metric.creator.avg_views_long` 等 4 条 | `id` | **沿用** | 是（`_ID_RX`） | 旧 id 保留为 superseded，不删除 |
| 2 | `type` | `metric`／`criterion`／`expression` | `type` | **沿用 ＋ 取值扩展** | 是（`_TYPE_RX`） | 新增 `concept`；`_IDREF_RX` 已含 concept（`ontology.py:33`） |
| 3 | `label` | 中文标签 | `label` | **沿用** | 是 | Q-03 要求均播窗口进 label |
| 4 | `owner` | 「业务-红人组」 | `owner` | **沿用** | 是 | Q-15 未定前不改 |
| 5 | `status` | `active` | `status` | **沿用 ＋ 取值扩展** | 是 | 新增 `superseded` |
| 6 | `stage` | `""`／`screening` | `stage` | **沿用** | 是 | 新增 `negotiation`／`sov`／`outreach` 三个业务段名 |
| 7 | `availability` | `[]` | `availability` | **沿用** | 是 | 语义不变 |
| 8 | `raw` | yaml 原文整块 | `raw` | **沿用** | 是 | 新字段先写进 yaml，再抽索引 |
| 9 | （raw 内）`surfaces` | 2 个键：`reported`／`median` | `surfaces` | **结构升级** | 否 → **是（本次新增抽取）** | 键改为面键六值；值增 `data_status/unit/source` |
| 10 | （raw 内）`external_only` | `median` | `external_only` | **沿用 ＋ 值域扩展** | 否 → **是** | 新增 `none`（该条不对外） |
| 11 | （raw 内）`axes` | `{content_form: long}` | `axes` | **沿用** | 否 | 仅 metric 用；P1 再抽 |
| 12 | （raw 内）`version` | `1.0.0` | `version` | **沿用** | 否 | 定稿新条目从 `2.0.0` 起 |
| 13 | （无） | — | `definition` | **新增** | 否（留在 raw） | 中文一句话定义；口径可核 |
| 14 | （无） | — | `data_status` | **新增** | **是** | 三值：reliable／unreliable／unknown |
| 15 | （无） | — | `source` | **新增** | 否（留在 raw） | 出处串（文件:行／命令） |
| 16 | （无） | — | `key` | **新增**（concept） | 否 | 唯一键名（brandId／channelId／listId／平台枚举／skuTerms） |
| 17 | （无） | — | `value_domain` | **新增**（concept） | 否 | 合法值域 |
| 18 | （无） | — | `superseded_by` | **新增** | 否 | 旧条目的接替 id 列表 |
| 19 | `scenarios`／`groups` | 判据专用 | 同名字段 | **沿用** | 是（`_parse_scenarios`／`_parse_groups`） | 不动 |
| 20 | 索引顶层 `kind`／`corpus_version`／`entry_count`／`entries` | 见 `_ONTOLOGY.json` | 同名 ＋ `schema_version` | **沿用 ＋ 1 个新增** | 是 | `kind` 仍 `daniel.ontology.v1`；新增 `schema_version: 2` |

### 2.20 现有 4 条登记项的处置

| # | 现有 id | 处置 | 去向 |
|---|---|---|---|
| 1 | `metric.creator.avg_views_long` | **superseded** | `superseded_by: [metric.creator.avg_views.drawer_28d]`；其 `reported` 面（latest_30_videos 均值）无承接项，P1 待核（N-8） |
| 2 | `criterion.creator.screen` | 原样保留 | 5 组筛选维度；手册 §4.1 直接引用该 id |
| 3 | `expr.kol_list` | 原样保留 | 段序／必带／禁用词 |
| 4 | `criterion.clarify.param_gate` | 原样保留 | 4 场景／28 条；手册 §4.1 引用该 id，不重抄 |

> 定稿后条目数：**18 active（5 concept ＋ 10 metric ＋ 2 criterion ＋ 1 expression）＋ 1 superseded = 19**。
> `_ONTOLOGY.json` 的 `entry_count` 由重建器写入，不手改（`check_corpus_sync.py:480–506`）。

### 2.21 `data_status` 与交付写法

| 指标 | data_status | 交付时必须附 | 不得写 |
|---|---|---|---|
| M1 | unreliable | 「平台 28 天均值口径」＋ 面键 | 与 M2／M3 并列比大小 |
| M2 | reliable | 「近 28 天 · 样本 N 条」 | N<5 仍给结论 |
| M3 | reliable（有条件） | 「12 个月∩最新 100 条」＋ 池量 | 池量不足只给数 |
| M4 | unknown | 所选面＋成交形式 | 不标面直接给 N |
| M5 | reliable | 取数时点 | 用订阅数推断表现 |
| M6 | unreliable | 来源分支＋统一百分数 2 位 | 两来源同列排名 |
| M7 | unreliable | 「上限校验」＋判断词三种 | CPM 当唯一判据 |
| M8 | unknown | 市场＋窗口＋「分母待确认」 | 品牌缺席写 0% |
| M9 | reliable（有条件） | 口径声明＋情感同读 | 竞争集按份额前三收窄 |
| M10 | unreliable | 逐人状态口径＋窗口 | 用会话数当发送数 |

### 2.22 P1 候选：视频级指标（不进 P0，Q-13）

| 候选 id | 指标 | 现在为什么不进 P0 | P1 的进册条件 |
|---|---|---|---|
| `metric.creator.video.views` | 单条视频播放量 | 详情接口实测只给 20 条，没有稳定全量面 | 拿到可复跑的分页口径后补 `sample_rule` 与 `source` |
| `metric.creator.video.likes` | 单条视频点赞量 | 同上；且点赞受发布时间影响，需配窗口 | 与播放量同批取回后再登记 |
| `metric.creator.video.rated_score` | 相关性／Rated Score | 只在品牌提及的原生表现里出现，Daniel 正文无字段 | 平台确认公式（N-1 同类）后才登记 |

> 本表只是**候选清单**，不写进随包语料；Q-13 默认「10 条不动」，三项留到 P1 再逐条过门禁。

---

## 3. 登记表扩展方案

### 3.1 结论与边界

| 项 | 结论 |
|---|---|
| 载体 | **继续用** `mcp/corpus/kol-intelligence/references/12-ontology-registry.md`（母本附录 B 的切片，源 `docs/marketing/skills/kol-intelligence.md:6895–7164`） |
| 不新建 | 不建第二份登记表、不建新目录、不新增语料束、不新增工具 |
| 索引 | `_ONTOLOGY.json` **仍是生成物**：`check_corpus_sync.py::_rebuild_ontology`（L480–506）重建，手改无效 |
| 改动面 | ① 母本附录 B（登记项正文）；② `ontology.py` 的 `parse_entries()`（抽 `surfaces`／`external_only`／`data_status`／`definition`／`source`）；③ `check_ontology.py`（C19-c 扩到新类型、C19-e 扩到 `none`）；④ 重跑切分器与重建器 |
| 不改 | `contracts/*.json`（列名改动属下一阶段）、`lib/*`、`mcp/server.py`、工具签名 |

### 3.2 schema 字段清单（定稿新增／沿用一览）

**条目级字段**

| # | 字段 | 类型 | 必填 | 适用类型 | 变更 | 落索引 | 说明 |
|---|---|---|---|---|---|---|---|
| 1 | `id` | string（ASCII，`metric｜criterion｜expression｜concept｜constraint` 前缀） | 是 | 全部 | 沿用 | 是 | 全局唯一；`_IDREF_RX` 只认 ASCII（`ontology.py:33`） |
| 2 | `type` | enum `metric｜criterion｜expression｜concept｜constraint` | 是 | 全部 | **取值扩展（＋concept）** | 是 | `_TYPE_RX` 不限值域，新增值不需改正则 |
| 3 | `label` | string（中文） | 是 | 全部 | 沿用 | 是 | 均播窗口写进 label |
| 4 | `owner` | string | 是 | 全部 | 沿用 | 是 | C19-c 要求非空、且 status≠draft |
| 5 | `status` | enum `active｜superseded｜draft` | 是 | 全部 | **取值扩展（＋superseded）** | 是 | `superseded` 不参与新交付引用 |
| 6 | `stage` | string | 否 | metric／criterion | 沿用 | 是 | `""`／screening／negotiation／sov／outreach |
| 7 | `availability` | list | 否 | 全部 | 沿用 | 是 | 现有为 `[]` |
| 8 | `definition` | string（中文一句话） | 是 | concept／metric | **新增** | 否（raw） | 不含阈值，只写口径 |
| 9 | `surfaces` | map<面键, surface> | metric 必填 | metric | **结构升级** | 是（新增抽取） | 键＝六值面键；见 §3.3 |
| 10 | `external_only` | 面键 或 `none` | 有 surfaces 时必填 | metric | 沿用＋**值域扩展（＋none）** | 是 | C19-e 硬门：不带即红（`check_ontology.py:141–149`） |
| 11 | `data_status` | enum `reliable｜unreliable｜unknown` | metric 必填 | metric（concept 可选） | **新增** | 是 | 顶层＝对外面（external_only）的状态；面级可覆盖 |
| 12 | `source` | string（`文件:行`／`命令`，分号分隔） | 是 | 全部 | **新增** | 否（raw） | 每个事实可追 |
| 13 | `version` | semver | 否 | 全部 | 沿用 | 否 | 新条目 `2.0.0` |
| 14 | `axes` | map | 否 | metric | 沿用 | 否 | 如 `content_form: long` |
| 15 | `key` | string | concept 必填 | concept | **新增** | 否 | brandId／channelId／listId／平台枚举／skuTerms |
| 16 | `value_domain` | string | concept 必填 | concept | **新增** | 否 | 合法值域 |
| 17 | `superseded_by` | list<id> | 否 | 全部 | **新增** | 否 | 旧条目 → 新条目 |
| 18 | `scenarios`／`groups` | list | 否 | criterion | 沿用 | 是 | 现有解析器已支持 |

**surface 子字段（`surfaces.<面键>` 下）**

| # | 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| 1 | `kind` | enum `mean｜median｜derived｜ratio｜share｜snapshot｜count` | 是 | 该面的算法类别；新增 `derived`／`snapshot`／`count` |
| 2 | `window` | string | 是 | 窗口写死；均播两条的窗口必须与 id／label 一致 |
| 3 | `sample_rule` | string | 是 | 样本条件（含剔除规则） |
| 4 | `min_sample` | int | 否 | 样本门槛；Q-21 未定前按各条现状写 |
| 5 | `data_status` | enum 三值 | 否 | 不写＝继承顶层 |
| 6 | `unit` | string | 否 | 单位（互动率两面不同，必写） |
| 7 | `source` | string | 否 | 不写＝继承顶层 |

**索引顶层字段**

| 字段 | 变更 | 说明 |
|---|---|---|
| `kind` | 沿用 `daniel.ontology.v1` | 不升版：新增字段全部可选，旧消费方按 `raw` 读不受影响 |
| `schema_version` | **新增**（整数 `2`） | 供门禁判「是不是新结构」 |
| `corpus_version` | 沿用 | 重建时写入，见 §3.6 |
| `entry_count` | 沿用 | 重建时写入 |
| `entries` | 沿用 | 每条含 §3.2 条目级字段 |

### 3.3 `surfaces` 结构规范（不设 `取值面` 字段）

**规则**

1. **面键就是「取值面」**：六值 `api_field／detail_drawer／pipeline_v2／list_item／manual_formula／outreach_system`；不另设 `取值面` 字段，不写 `face:` 子键。
2. 一条 metric 可有多面（M6 两面）；**面不同、单位不同、分母不同**时，必须在该面下写 `unit`／`sample_rule`。
3. **均播例外**：Q-03 要求 M2／M3 各一条登记，不放在同一条的 `surfaces` 下；两条各自只有一个面键。
4. `external_only` 必须是本条 `surfaces` 的键之一，或 `none`；`none` ＝ 该条不进对外交付件。
5. 顶层 `data_status` 必须等于 `external_only` 面的状态；若 `none`，顶层写该条主面的状态并在 `definition` 说明「不对外」。
6. 旧键 `reported`／`median` **不再使用**；迁移映射：`reported → api_field`（仅指面的类别，不承诺窗口相同）、`median → detail_drawer`（M2）。

**面键与旧键映射**

| 旧键（`avg_views_long`） | 新面键 | 窗口是否相同 | 处置 |
|---|---|---|---|
| `reported`（kind mean，latest_30_videos） | `api_field` | **不同**（旧=最新 30 条均值；M1=28 天 insight 均值） | 旧条目 superseded；`reported` 面无承接，P1 待核（N-8） |
| `median`（kind median，last_28_days） | `detail_drawer` | 相同（28 天） | 由 M2 承接 |

### 3.4 类型扩展：`concept`

| 项 | 内容 |
|---|---|
| 新增值 | `type: concept` |
| 必填字段 | `id/type/label/owner/status/definition/key/value_domain/source` |
| 不写 | `surfaces`／`external_only`（概念不是计算，不给面） |
| 索引影响 | `parse_entries()` 照样抽 `id/type/label/owner/status/stage/availability`；`concept` 已能被 `_IDREF_RX` 识别（`ontology.py:33`） |
| 门禁影响 | C19-c 对 concept 同样要求 owner 非空；C19-e 不适用（无 surfaces） |
| 依据 | 草案 Q-19；本轮决策要求登记表「加 concept 类型」 |

### 3.5 登记项示例（可直接落进附录 B）

**概念（brand）**

```yaml
id: concept.brand
type: concept
label: 品牌
owner: 业务-红人组
status: active
stage: ""
key: brandId
definition: Daniel 里的品牌实体：品牌编号＋名称＋工作区＋品类＋目标市场＋行业关键词＋样品价＋竞品；是检索口径、背调、提及任务、声量统计的共同事实源。
value_domain: brandId 为整数；name 允许为空、允许同名（服务端不拦空名／重名，不可用名字当唯一键）；必须归属一个 workspaceId；targetCountries 为 ISO 国家码数组；sampleCost 为样品计价；competitors 以品牌自己配置的为准。
data_status: reliable
source: "contracts/real-brands-inventory.json#交付件schema.列; references/60-data-layer.md:239,369"
version: 2.0.0
```

**指标（均播抽屉面，单面）**

```yaml
id: metric.creator.avg_views.drawer_28d
type: metric
label: 均播（详情抽屉 · 近 28 天 · 中位数）
owner: 业务-红人组
status: active
stage: screening
surfaces:
  detail_drawer:
    kind: median
    window: last_28_days
    sample_rule: 长视频=contentType VIDEO_ON_DEMAND 且 views>=100；短视频=SHORTS（无播放阈值）；28 天内且条数>=3 用该批，否则退回最新 30 条
    min_sample: 5
    data_status: reliable
    unit: 次播放
    source: "lib/normalize.js:173,188,192,199,217"
external_only: detail_drawer
data_status: reliable
definition: 长视频与短视频各自播放量的中位数；「整体」=长视频样本∪短视频样本；窗口近 28 天，不足 3 条退回最新 30 条。
source: "lib/normalize.js:155-229; docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md:144-171"
version: 2.0.0
```

**指标（互动率，双面）**

```yaml
id: metric.creator.engagement_rate
type: metric
label: 互动率
owner: 业务-红人组
status: active
stage: screening
surfaces:
  api_field:
    kind: ratio
    window: insight 近 28 天；表现块分母用该范围全量视频，不开窗
    sample_rule: (Σlikes+Σcomments)/Σviews，分母用同一批样本；views=0 返回 null
    min_sample: 1
    data_status: unreliable
    unit: 小数 0-1
    source: "lib/normalize.js:202,211,242"
  list_item:
    kind: ratio
    window: 名单条目快照
    sample_rule: lists.getItems.engagementRate 原值
    min_sample: 1
    data_status: unreliable
    unit: 百分数（1.6=1.6%）
    source: "lib/normalize.js:143; _DANIEL-FIELD-DICTIONARY.md:439-442"
external_only: list_item
data_status: unreliable
definition: (Σlikes+Σcomments)/Σviews，分母用同一批样本；两个面、两种单位，交付前统一成百分数 2 位并标来源分支。
source: "lib/normalize.js:143,202-211,242; _DANIEL-FIELD-DICTIONARY.md:439-442,481"
version: 2.0.0
```

### 3.6 版本号：`corpus_version` 怎么取

| 环节 | 取法 | 证据 |
|---|---|---|
| 母本版本区 | 文件头／页脚／变更日志三处一致，C18 强制 | `docs/marketing/skills/kol-intelligence.md:3,6609` |
| 语料清单 | `_MANIFEST.json.corpus_version` ＝ 0.9.206 | `_MANIFEST.json:8` |
| 索引重建 | **优先取源束 `kol-intelligence/_CORPUS.json.corpus_version`**；取不到再回退 `_MANIFEST.json` | `check_corpus_sync.py:494–505` |
| 登记项自身 | `version` 是**条目版本**（如 `2.0.0`），与语料版本无关 | 现有 4 条写法（`12-ontology-registry.md:31`） |

> 定稿不改版本号：当前基线 **0.9.206**。落地时改母本 → 切分器重跑 → 版本区与清单同步（预计 0.9.207）→ 重建索引 → `check_ontology.py` 绿。
> **禁止**手改 `_ONTOLOGY.json` 的 `corpus_version`：C19-a 会与清单比对（`check_ontology.py:64–72`）。

### 3.7 门禁影响（现有 + 需扩展）

| 门禁 | 现有判据 | 新结构下的影响 | 需改？ |
|---|---|---|---|
| C19-a | 索引版本 ≡ 清单版本 | 不变 | 否 |
| C19-b | 正文引用的 id 都能命中索引 | 旧 id `avg_views_long` 仍保留 ⇒ 不产生悬空引用 | 否 |
| C19-c | `owner` 非空、`status != draft` | `superseded` 通过；concept 也必须给 owner | 否（值域可加 superseded 说明） |
| C19-e | 带 `surfaces` 必须声明 `external_only` | 10 条全部声明；`none` 需被接受 | **是**（当前只判「有没有这个键」，`none` 已能通过，建议加值域白名单） |
| C19-f | 澄清闸结构（4 场景／28 条／5 组） | 不动 | 否 |
| 新增建议 | C19-g：`surfaces` 键必须是六值之一；C19-h：顶层 `data_status` ≡ external_only 面状态 | 防止「面键自造」与「状态不一致」 | **建议新增**（实施项 I-4） |

### 3.8 对代码的影响（只登记，不改）

| 文件 | 现状 | 需要什么 | 优先级 |
|---|---|---|---|
| `daniel_cli/ontology.py` | `parse_entries()` 只抽 7 个顶层键 ＋ scenarios/groups；`surfaces` 只在 `raw` 里 | 增 `_parse_surfaces()`（零依赖、按固定缩进），把面键与 `kind/window/sample_rule/min_sample/data_status/unit/source` 抽成 dict；增 `definition/data_status/source/external_only/superseded_by` | P1（不抽也能用，只是索引层看不到面） |
| `mcp/check_ontology.py` | C19-e 只判键存在 | 加面键白名单、`none` 语义、顶层与面级状态一致性 | P1 |
| `mcp/check_corpus_sync.py` | 已能重建 | 无需改 | — |
| `daniel_cli/corpus.py` | `_attach_ontology()` 按 id 注入 | 不变 | — |
| `mcp/server.py` | 91 → 97 个派生工具 | 无需改（自动派生） | — |

### 3.9 落地步骤（8 步，下一阶段执行）

| # | 动作 | 产物 | 判据 |
|---|---|---|---|
| 1 | 改母本附录 B（L6895–L7164）：4 条 → 19 条 | 母本新版本区 | C18 三处一致 |
| 2 | 重跑切分器 | `12-ontology-registry.md` 与 `kol-intelligence/SKILL.md` 同步 | 切分器退出码 0 |
| 3 | 重建索引 | `_ONTOLOGY.json`（`entry_count: 19`） | `check_corpus_sync.py --sync` |
| 4 | 跑语义门禁 | C19 a/b/c/e/f 全绿 | `python3 mcp/check_ontology.py` 退出码 0 |
| 5 | 加抽取函数 | `ontology.py` 输出 `surfaces` | 单测：M6 两面、M2 单面 |
| 6 | 加 C19-g/h | 面键白名单／状态一致性 | 反例必须报红 |
| 7 | 更新 `baseline.json` | `registeredCount` 与实际一致 | `tests/golden` 回归 |
| 8 | 回写契约列名（Q-03 的 M3） | `kol-list.json` 新增池列 | 契约门禁 |

### 3.10 不做的事

| # | 不做 | 原因 |
|---|---|---|
| 1 | 不新建 `_ONTOLOGY-V2.json` 或第二份登记表 | 决策 Q-01 |
| 2 | 不把 `取值面` 作为顶层字段 | 决策 Q-01 |
| 3 | 不在本条改契约列名 | 改契约会打红存量；§3.9 第 8 步 |
| 4 | 不改工具签名／不新增工具 | 决策 4；工具名冻结 |
| 5 | 不把阈值（如 `$60–80`）写进随包语料 | Q-10 未定；当前只在母本 |

---

## 4. 操作手册（8 个能力）

### 4.0 统一约定

**命令与工具口径**

| 项 | 定稿值 | 出处 |
|---|---|---|
| CLI 命令 | **97**（本轮新增 6） | `schema.py` AST 数 `c()`；审计基线 91 |
| MCP 工具（DSH 插件） | **20**（基线 ≡ 代码注册名） | `baseline.json:3`；`lib/index.js` 20 处 `ctx.tools.register` |
| P0 硬约束 | **P0 不新增第 21 个工具** | 决策 4（2026-11-08 按 20 口径修订） |
| 实现口径 | 新能力一律走「新增 CLI 子命令 ＋ `daniel_run`／`daniel_write_plan` 直通」；不再新增工具名 | 审计 §1.1 的层④ 两个通用直通 |
| 语料 | 0.9.206／8 束／41 文件／25 切片 | `_MANIFEST.json` |

**退出码**

| 码 | 含义 | 处置 |
|---|---|---|
| `0` | 成功 | — |
| `2` | 用法错误／前置不满足（缺参数、品牌不存在、无权限） | 补齐或换路径；**不得当系统故障重试** |
| `1` | 运行失败（取数失败、服务端错误、回读不一致） | 按失败形态处置；同一动作失败两次换路径 |
| `3` | 写操作未确认（只做干跑，零写入） | 把干跑计划给用户，拿到明确「可以／继续」后才 commit |

**失败三类（每个能力都按这三类写）**

| 类 | 判定 | 话术要点 | 下一步 |
|---|---|---|---|
| 错误码 | 有 `exitCode` 与 `error.kind` | 说清缺什么／哪一步不允许 | 补齐或换路径；两次失败换路径 |
| 超时 | 无终态、长时间 pending | 不判失败；先说「还没跑完」并给当前阶段 | 查状态；不得重复提交 |
| 无数据 | 请求成功但结果为空 | 分清三态：平台未收录／本次未取到／成功零命中 | 换信号／可重试／换词 |

**写操作四道闸（全部能力共用）**

| 闸 | 机制 | 落点 |
|---|---|---|
| ① 权限 | 账号对该模块有写权限才放行，否则 `exit 2` ＋ 人话理由 | `schema.py` 头注释写链①；`daniel account capabilities` |
| ② 确认 | 不带 `--confirm` 只干跑，`exit 3`，零写入 | `schema.py` 头注释写链② |
| ③ 删除凭据 | 删除类还要 `--delete-token <目标名>`（原样再写一遍） | 写链③；`deleteTarget` |
| ④ 回读 | 写后回读校验并给审计落点 | `daniel account audit` |

**通用门禁（开工前先过）**

| # | 门禁 | 判据 | 不满足时 |
|---|---|---|---|
| G-0 | 登录态 | `daniel auth status` 退出码 0 | 停：先 `daniel_login` |
| G-1 | 账号与工作区 | `daniel account whoami` 有当前工作区编号 | 停：工作区未确认不取数 |
| G-2 | 品牌已建档 | `daniel brands show --brand` 命中 | 停：不代建；给建档卡片 |
| G-3 | 口径先声明 | 指标有 id ＋ 面键 ＋ `data_status` | 停：口径没定不出数 |
| G-4 | 不编 | 每个数字能追到命令／字段 | 停：宁可少写一句 |

### 4.1 CAP-01 红人检索（`CAP-01-creator-search`）

**命令／路由**

| 面 | 命令／工具 | 读写 | 档 |
|---|---|---|---|
| 看检索记录 | `daniel search history [--limit]`／`daniel_run(["search","history"])` | 读 | A |
| 看任务进度 | `daniel search job-status --job <编号>`／`daniel_research_status(jobId)` | 读 | A |
| 补频道公开数据 | `daniel search enrich --channel-ids <编号,…>` 或 `--items-file <路径>` `[--emails]` | 读 | A |
| 词表体检 | `daniel keywords check --file <路径> [--strict-exit]` | 读 | A |
| 品牌深度研究·出计划 | `daniel search submit --brand <品牌> --query <检索式> [--limit]`（不带 `--confirm`）／`daniel_deep_research` | 写·第一段 | B |
| 品牌深度研究·提交 | 同上 ＋ `--confirm`／`daniel_deep_research_commit(planId)` | 写·第二段 | B |
| AI 开放研究·出计划 | `daniel_open_research(topic, brand?, country?, minSubscribers?)` | 写·第一段 | B |
| AI 开放研究·提交 | `daniel_open_research_commit(planId)` | 写·第二段 | B |
| 官方库检索 | `daniel_roster_search` | 退役 | **C** |

**输入**

| 字段 | 必填 | 合法值域 | 缺失时行为 |
|---|---|---|---|
| `brand` | 是（deep） | 品牌名或编号，必须 `brands show` 命中 | 缺 → 改走 open，不猜品牌 |
| `query`／`topic` | 是 | 自然语言检索式，**≤501 字符** | 缺 → `exit 2`；超长 → `exit 2` 并给压缩建议 |
| `country` | 否 | ISO 国家码，逗号分隔 | 缺 → 不传；交付注明「未限定市场」 |
| `minSubscribers`／`maxSubscribers` | 否 | 整数 | 缺 → 不传；不得擅自加门槛 |
| `limit` | 否 | 整数（默认 10） | 缺 → 10；只影响摘要展示，服务端检索任务不接受条数 |
| `--channel-ids`／`--items-file` | enrich 必填二选一 | 编号列表／JSON 三种写法 | 都缺或都给 → `exit 2`，零请求 |
| `--emails` | 否 | flag | 缺 → 只补订阅数／国家／标签 |

**输出**

| 字段 | 来自 | 口径登记 |
|---|---|---|
| 计划：通道／检索式／品牌／筛选／影响（会建任务、写检索记录、额度）／planId／过期时刻（**300 秒**） | plan 段 | — |
| 任务：编号／状态五档（排队中／检索中／富化中／完成／失败）／进度 | `job-status`／`research_status` | — |
| 候选：`channelId/title/handle/subscriberCount/country/topics/tags` | 检索结果 | `concept.creator`；订阅数 → M5 |
| 富化：各字段补到几个、逐条「补齐／未补到」、请求批次数、失败批次原因 | `search enrich` | 无指标 |
| 审计（open 提交）：已落盘／路径／时间 | `daniel_open_research_commit` | — |

**前置条件**

| # | 条件 | 怎么核 |
|---|---|---|
| P1 | 已登录 | G-0 |
| P2 | 工作区已确认 | G-1 |
| P3 | 品牌已建档（deep） | G-2 |
| P4 | 门槛与目标市场已给定（或明确用默认） | 用户原话；缺则按默认并标「未确认门槛」 |
| P5 | enrich 的输入是**频道编号**，不是频道名 | 本地先判；名字 → 先 `ct resolve-channel` |

**门禁**

| # | 门禁 | 判据 | 停了之后 |
|---|---|---|---|
| G1 | 品牌不在册 | `brands show` 未命中 | 停在「建档 or 换 open」二选一，不代建 |
| G2 | 计划过期／参数变更 | planId 超 300 秒或提交参数与计划不一致 | 停：重新出计划，不复用旧 planId |
| G3 | 走到官方库通道 | 工具返回 `channel_retired` | 停：改 deep／open，**不得重试 roster** |
| G4 | 任务未到终态 | `job-status` 不在「完成／失败」 | 停：只报进度，不取半批结果 |
| G5 | 关键词路径未过词表体检 | `keywords check` 违规数 > 0 | 停：先改词表 |
| G6 | 富化缺字段被写成「没有」 | 输出里有「未补到」 | 停：按「未取到」写，不写「平台没有」 |

**失败形态**

| 类 | 具体形态 | 话术 | 下一步 |
|---|---|---|---|
| 错误码 | `exit 2`：`brand`／`query` 缺失、topic 超 501、planId 不存在／过期／参数不符 | 「这次少了一个必填项／计划已过期，需要重新出计划」 | 补字段；重新 plan |
| 超时 | 任务停在检索中／富化中；`executeSearchJob` 503 | 「任务还在跑（当前阶段：检索中），503 是常态不是失败」 | 查 `job-status`；**不重复提交** |
| 无数据 | 成功零命中 vs 逐词失败 | 「这次条件下一共 0 条；其中 N 个词是取数失败（不是没命中）」 | 失败词回补；零命中换词／放宽市场 |

**是否写操作**：**是**（deep submit 与 open submit 都会建任务并开跑）。
- 唯一合法路径：plan（零发包）→ 把计划原样讲给用户 → 用户明确「可以／继续」→ commit。
- **open 与 deep 提交后各落一条写审计**（`daniel account audit`，同一份 `write-audit.jsonl`）：open＝`open-research-commit`、deep＝`deep-research-commit`，字段逐项一致（`lib/worker.py:532–614`，2026-11-08 补齐 deep）。审计写不进去时如实返回「已落盘 false」，不把提交说成"有审计"。
- 提交后用 `daniel_research_status(jobId)` 跟进；不阻塞、不轮询等待。

**出处**：`schema.py#search.*`；`lib/index.js:967–1111`（deep 两段）、`:1119–1252`（open 两段）、`:925–963`（roster 退役）；`lib/research.js:16`（TTL 300 秒）；`mod_search.py:57–92`（enrich 只读）；`processes.json#discovery-07、daniel-api-10`。

### 4.2 CAP-02 红人档案（`CAP-02-creator-profile`）

**命令／路由**

| 面 | 命令／工具 | 读写 | 档 |
|---|---|---|---|
| 一次拿全 | `daniel_kol_profile(handle, videos)` | 读 | A |
| 名单侧补 handle | `daniel lists items --list-id --with-handle` | 读 | A |
| 解析编号 | `daniel ct resolve-channel` | 读 | A |

**输入**

| 字段 | 必填 | 合法值域 | 缺失时行为 |
|---|---|---|---|
| `handle` | 是 | `@xxx` 或频道地址 | 缺 → 工具报「handle 必填」；CLI `exit 2` |
| `videos` | 否 | 1–10，默认 5 | 超 10 截到 10；只影响展示条数，不影响计算样本 |

**输出**

| 块 | 字段 | 口径登记 |
|---|---|---|
| ① 频道 | 名称／订阅数／国家／总播放／视频数 | 订阅数 → M5；`country` 是频道所在地 |
| ② 表现（近 28 天） | 整体／长视频／短视频：视频数、总播放、平均播放、互动率 | 平均播放 → M2（优先）／M1（兜底）；互动率 → M6（`api_field` 面） |
| ③ 受众 | 性别、年龄、地区 Top5、兴趣与购买意向 Top5 | 未登记（P1） |
| ④ 近期视频 | 标题／播放／点赞／时长／发布时间 | 视频级，未登记（Q-13） |
| 状态 | `未取到[]`／`平台未收录[]`／`替代信号[]` | — |

**前置条件**：P1 登录；P2 handle 可解析成 `channelId`（失败即停，不按名字模糊匹配）；P3 若声称「来自名单」，该频道必须真在名单条目里。

**门禁**

| # | 门禁 | 判据 | 停了之后 |
|---|---|---|---|
| G1 | `insight` 为空就断言「没有受众」 | `insightStatus=empty` | 改写成「平台未收录」 |
| G2 | 样本不足仍给结论 | 长／短视频样本 `N<5` | 写「样本不足（n=X），无法判断」 |
| G3 | 把兜底均值当页面口径 | 表现块走了 `performanceBlock` | 标「均值口径，非页面口径」（块内已自报，`normalize.js:244`） |
| G4 | 用 handle 当唯一键 | 交付没有 `channelId` | 补 `channelId` |

**失败形态**

| 类 | 具体形态 | 话术 | 下一步 |
|---|---|---|---|
| 错误码 | handle 无法解析（`exit 1`） | 「这个 @handle／链接在平台里没对上频道」 | 让用户给频道链接或 `UC…` 编号 |
| 超时 | worker 超时 | 「这次取数超时了，档案没拿全」 | 重试一次；两次仍失败换路径 |
| 无数据 | 档案有、`insight` 为 null | 「受众这块平台没收录（不是我们没取到）」 | 用平均播放＋互动率＋内容分类判断人群 |

**是否写操作**：**否**（纯读，无缓存写入 Daniel）。
**出处**：`lib/index.js:886–913`；`lib/worker.py:252–330`；`lib/normalize.js:295–327`；`_DANIEL-FIELD-DICTIONARY.md:134,200-204`。

### 4.3 CAP-03 品牌档案（`CAP-03-brand-profile`）

**命令／路由**

| 面 | 命令／工具 | 读写 | 档 |
|---|---|---|---|
| 列品牌 | `daniel brands list [--workspace] [--limit]`／`daniel_brands_list` | 读 | A |
| 品牌数 | 实时直连／`daniel_brand_count` | 读 | A |
| 看档案 | `daniel brands show --brand`／`daniel_brand_view` | 读 | A |
| 看竞品 | `daniel brands competitors --brand`／`daniel_run` | 读 | A |
| 建／改／克隆／删 | `brands create/update/clone/delete`／`daniel_write_plan→commit` | 写 | B |
| 渠道核验 | `brands.verifyChannel`（路由有、CLI 无） | — | **C** |
| 竞品建议 | `brands.suggestCompetitors`（路由有、CLI 无） | — | **C** |

**输入**

| 字段 | 必填 | 合法值域 | 缺失时行为 |
|---|---|---|---|
| `--brand` | 是（show／competitors） | 品牌名或编号 | 缺 → `exit 2`；同名多品牌 → 停，要编号 |
| `--workspace` | 否 | 工作区编号 | 缺 → 范围待实测（N-7）；交付写清本次读的是哪个工作区 |
| `--limit` | 否 | 默认 200 | 结果被截断必须报「已截断」 |

**输出**：品牌编号／名称／工作区编号与名称（`real-brands-inventory.json#列`）；简介／频道／竞品／目标市场／品类／行业关键词／样品价；竞品名＋每个竞品的品类关键词。

**前置条件**：P1 登录；P2 品牌编号已确认（同名必须给编号）。

**门禁**

| # | 门禁 | 判据 | 停了之后 |
|---|---|---|---|
| G1 | 「全部品牌」只读了单一工作区 | 结果的工作区编号不覆盖用户要的范围 | 补 `--workspace` 逐区读，或明说只读了 X |
| G2 | 同名品牌 | 出现 ≥2 条同名 | 请用户给编号，不按名字解析 |
| G3 | 品牌未建档 | `brands show` 未命中 | 给建档卡片（B），不代建 |
| G4 | 样品价当零售价 | 交付写「零售价」 | 改为「样品计价」 |

**失败形态**

| 类 | 具体形态 | 话术 | 下一步 |
|---|---|---|---|
| 错误码 | `exit 2` 品牌不存在／未登录 | 「这个品牌在当前离线账号里查不到」 | 先确认账号／工作区，再确认品牌名 |
| 超时 | 接口超时 | 「这次查询没返回」 | 重试一次（读操作幂等） |
| 无数据 | 列表为空 | 「当前工作区下没有品牌」不是「账号没有品牌」 | 加 `--workspace` 再查 |

**是否写操作**：读面**否**；写面（create/update/clone/delete）**是**，另走四道闸。
**出处**：`schema.py#brands.*`；`references/60-data-layer.md:239,369`；`_DANIEL-FIELD-DICTIONARY.md:360–381`；`processes.json#daniel-api-03`；审计 `§2` 第 8 行。

### 4.4 CAP-04 名单管理（`CAP-04-list-ops`）

**命令／路由**

| 面 | 命令 | 读写 | 档 |
|---|---|---|---|
| 某品牌有哪些名单 | `lists by-brand --brand` | 读 | A |
| 名单条目 | `lists items --list-id [--limit] [--offset] [--with-handle]` | 读 | A |
| 已保存频道编号 | `lists saved-channel-ids --brand` | 读 | A |
| 分享状态 | `lists share-status --list-id` | 读 | A |
| 自动优先级状态 | `lists auto-priority-status --list-id` | 读 | A |
| **往名单加人** | `lists add-items --list-id --items-file/--channel-ids [--limit] [--confirm]` | **写** | B |
| 建名单 | `lists create --brand --name` | 写 | B |
| 改名 | `lists rename --list-id --brand --name` | 写 | B |
| 删名单 | `lists delete --list-id --brand [--allow-non-empty] --delete-token` | 写 | B |
| 删人／合并／去重／分享链接／自动优先级 | 7 条路由无 CLI | — | **C** |

**输入（add-items 专列）**

| 字段 | 必填 | 合法值域 | 缺失时行为 |
|---|---|---|---|
| `--list-id` | 是 | 整数（如 8310034） | 缺 → `exit 2`；名单名不能当 id |
| `--items-file` | 与 `--channel-ids` 二选一 | JSON 数组（三种写法）／检索结果导出 | 都缺或都给 → `exit 2`，不发请求 |
| `--channel-ids` | 与 `--items-file` 二选一 | 英文逗号分隔 | 同上 |
| `--limit` | 否 | 正整数；默认全加 | 缺 → 全加；`≤0` → `exit 2` |
| `--confirm` | 否 | flag | 缺 → 干跑，`exit 3`，零写入 |

**输出（add-items）**

| 段 | 字段 |
|---|---|
| 干跑 | 名单编号、将加 N 人、跳过 M 人（已在名单／条目内重复／超出 `--limit`）、预计批数、逐字段补齐情况与「未取到」明细、影响范围、审计落点 |
| 真跑 | 逐批写入结果（送入／addedCount／failed）、回读前后条数与是否一致、审计落点 |
| 回读不一致 | `exit 1`，写明「差多少」；分「条数差」「服务端返回合计差」「成员对不上」三种原因 |

**前置条件**：P1 品牌已建档；P2 目标名单存在（`by-brand` 可查该 `listId`）；P3 条目里每条有 `channelId`（`UC…`）；P4 已在名单的人会跳过，不算失败。

**门禁**

| # | 门禁 | 判据 | 停了之后 |
|---|---|---|---|
| G1 | 干跑没给用户看就 `--confirm` | 没有「干跑计划原文 ＋ 用户确认原文」 | 停：回到干跑 |
| G2 | 名单编号给错 | `add-items` 在干跑阶段回读名单 | 停：`exit 2`，零写入 |
| G3 | 人数与页面不一致 | 条目数 ≠ 页面人数 | 以读到的条目为准并标注（`processes.json#daniel-api-01`） |
| G4 | 单批超 100 | 计划条数 >100 | 自动拆批，不截断；交付写清批数 |
| G5 | 回读不一致 | 增加量 ≠ 计划新增，或成员缺失 | `exit 1` 并报差额；不得写「已全部导入」 |
| G6 | 截断当全量 | `items` 返回条数 == `--limit` | 报「只读到前 N 条」或翻页 |
| G7 | 同名名单 | `by-brand` 出现 ≥2 条同名 | 用 `listId` 定位 |
| G8 | 删除没带凭据 | 无 `--delete-token` | `exit 2`，零删除 |

**失败形态**

| 类 | 具体形态 | 话术 | 下一步 |
|---|---|---|---|
| 错误码 | `exit 2` 名单／品牌不存在、两个输入都给、`--limit≤0`；`exit 3` 未确认 | 「这个名单编号在该品牌下查不到／这次只做了干跑，没有写入」 | 用 `by-brand` 重新定位；补 `--confirm` |
| 超时 | 大名单分页慢／批次写入慢 | 「名单人多，还没读完／写到第 X 批」 | 缩小 `--limit` 分段读；已写入部分以回读为准 |
| 无数据 | 名单存在但 0 条 vs 名单不存在 vs 全是已存在 | 「这个名单存在，但是空的」／「没有这个名单」／「候选 N 人全在名单里」 | 分别：换下一份／重新定位／换一批人 |

**是否写操作**：`add-items`／`create`／`rename`／`delete` **是**；其余 **否**。
- `add-items` 走 `daniel_write_plan` → 计划原样给用户 → 用户明确确认 → `daniel_write_commit`；CLI 侧同一套（不带 `--confirm` = 干跑 `exit 3`）。
- 干跑与真跑**各留一条审计**（计划里已声明：`mod_lists.py:763–765`；落盘：`commands/_common.py:134–164`），`daniel account audit` 可查。
- 删除必须回填 `delete_token`（名单名原样再写一遍）。

**出处**：`schema.py:393–422`（add-items）；`mod_lists.py:661–830`（计划／执行／回读）、`:873–876`（写注册）；`processes.json#daniel-api-01、daniel-api-02`；审计 §2 第 1 行／§4①。

### 4.5 CAP-05 品牌提及（`CAP-05-brand-mentions`）

**命令／路由**

| 面 | 命令／工具 | 读写 | 档 |
|---|---|---|---|
| 有哪些任务 | `mentions jobs --brand [--limit]` | 读 | A |
| 任务进度与汇总 | `mentions status --brand --job` | 读 | A |
| 视频级结果 | `mentions results --brand --job [--page] [--page-size] [--relevance-filter]` | 读 | A |
| 图表五块分布 | `mentions chart --brand --job` | 读 | A |
| 头部频道 | `mentions top-channels --brand --job [--limit 5–50] [--relevance-filter]` | 读 | A |
| 视频证据 | `mentions evidence --brand --job` | 读 | A |
| 导出明细 | `mentions export --brand --job [--relevance-filter] [--exclude-official] [--language]` | 读 | A |
| 发起分析 | `mentions run --brand [--days] [--max-videos]` | 写 | B |
| 触发守卫／重试／取消／删除任务 | 7 条路由无 CLI | — | **C** |

**输入**

| 字段 | 必填 | 合法值域 | 缺失时行为 |
|---|---|---|---|
| `--brand` | 是 | 品牌名或编号 | 缺 → `exit 2` |
| `--job` | 是（status/results/chart/top-channels/evidence/export） | 任务编号（UUID；从 `jobs` 第一列原样抄） | 缺 → `exit 2`；**`listJobs` 的自增 id ≠ `jobId`** |
| `--page-size` | 否 | 10–200，默认 50 | 越界 → 服务端报错 |
| `--relevance-filter` | 否 | `all`／`confirmed`／`confirmed_likely` | results 默认 `confirmed_likely`；**top-channels 默认 `all`**（服务端过滤字段与展示字段不一致） |
| `--limit`（top-channels） | 否 | **5–50**，默认 10 | 越界 → 本地 `exit 2`，**不发包** |
| `--days`／`--max-videos` | 否 | 7–1095 天／100–5000 条 | 缺 → 7 天／100 条；不得擅自放宽 |
| `--language`（export） | 否 | 14 种语言枚举 | 缺 → 不限 |

**输出**

| 面 | 关键字段 |
|---|---|
| chart | 五块分布：表现／真实性／视频类型／推广建议（标签＋条数）＋月度趋势（另有平均播放与平均综合分） |
| top-channels | 频道编号／名称／订阅数／视频数／平均综合分／平均播放／总播放／平均真实性／频道得分／是否已在名单／各表现档位视频数／相关性；到上限写「可能还有更多」 |
| evidence | 状态、匹配／符合／入选／已分析／剩余数、是否分批、批次数、入选视频清单（编号／标题／逐阶段进度） |
| export | 条数、邮箱缺失条数、每条：频道名／账号／链接、视频标题／链接、播放量、订阅数、综合分、自然表现、相关性、视频类型、是否官方、语言、邮箱 |
| results | 视频级评分、表现档位、`overallPerformance`、`compositeIndex`、`relevanceLabel`、点名位置／原话 |

**前置条件**：P1 任务存在；P2 任务已到终态（完成，含带告警）；P3 产品池已合并（品牌名任务 ＋ 其 SKU 词任务）。

**门禁**

| # | 门禁 | 判据 | 停了之后 |
|---|---|---|---|
| G1 | 只取了一个池 | 只读品牌名任务或只读 SKU 任务 | 合并两池后按 `videoId` 去重 |
| G2 | 用默认过滤器当全量 | results 没显式 `--relevance-filter all` | 重取；平台缺省 `confirmed`（41 条只回 1 行） |
| G3 | 按任务来源归属品牌 | 用 SKU 任务判定本品 | SKU 相关性按品类判，不等于点名品牌 |
| G4 | 自造评级代理 | 用「观看量前 25%」代替 `overallPerformance` | 用原生枚举 |
| G5 | 跨批混比 | 两批结果放同一张表 | 同批快照单独成表 |
| G6 | 分页没取全 | 返回条数 == `page-size` 且未翻页 | 翻到最后一页 |
| G7 | top-channels `--limit` 越界 | 给了 1／3／100 | 本地拦，改 5–50 |
| G8 | top-channels 用过滤口径 | 给了 `confirmed`／`confirmed_likely` | 改 `all`；否则可能回 0 条 |
| G9 | evidence 传视频编号 | 把视频编号当入参 | 不需要视频编号；编号在返回清单里 |
| G10 | export 邮箱缺失当没有 | 输出有「邮箱缺失条数」 | 写「N 条未取到邮箱」，不写「无邮箱」 |

**失败形态**

| 类 | 具体形态 | 话术 | 下一步 |
|---|---|---|---|
| 错误码 | `exit 2` 任务不存在／参数越界／品牌与任务不匹配 | 「这个任务编号在该品牌下没有」 | 用 `jobs` 重新取编号 |
| 超时 | 任务仍在跑；export 抓邮箱约 30 秒 | 「任务还没跑完（进度 X%），现在取到的是半批」／「导出在抓邮箱，稍慢」 | 等终态；export 可先去 `--exclude-official` 缩小 |
| 无数据 | 结果 0 行 | 先分辨「过滤缺省造成的假象」与「真没有」 | 用 `all` 重取；仍 0 才写「窗口内无相关提及」 |

**是否写操作**：`run` **是**（触发采集，`write=True`／`live`）；其余 7 条读面 **否**。
- 触发类写的前置：`brandMentions.runAnalysis` 不吃工作区入参，落库归属＝当时活跃工作区 ⇒ 先切工作区并回读断言再触发（`references/60-data-layer.md:293/341`）。
- `run` 走 plan → 确认 → commit。

**出处**：`schema.py#mentions.*`（chart/top-channels/evidence/export：L548/565/592/609）；`mod_mentions.py:312–320`（只读 HANDLERS）、`:403–407`（写 HANDLERS）；`references/60-data-layer.md:383–406,456`；审计 §2 第 2 行／A2。

### 4.6 CAP-06 声量份额（`CAP-06-sov`）

**命令／路由**

| 面 | 命令／工具 | 读写 | 档 |
|---|---|---|---|
| 份额总览 | `sov overview --brand [--country] [--days]`／`daniel_sov_overview` | 读 | A |
| 品类档案与竞品 | `sov categories --brand [--country]`／`daniel_sov_categories` | 读 | A |
| 被收录视频明细 | `sov brand-videos --brand [--video-brand] [--limit]`／`daniel_sov_brand_videos` | 读 | A |
| 发起曝光采集 | `sov run-exposure --brand --country [--days]`／`daniel_sov_run_exposure` | 写 | B |
| 品类档案写 9 条 | `sovCategories.aiSetup/…` | — | **C** |
| 品类读写 2 条 | `sovCategories.list/getFilterStats` | — | **C** |
| SEO SOV 读 4 条 | `seoSov.listWeeks/getHeatmap/getKeywordDetail/getTaskStatus` | — | **C** |
| SEO SOV 采集 | `seoSov.runCollection` | — | **C** |
| 强制刷新 | `exposureSov.forceRefresh` | — | **C** |

**输入**

| 字段 | 必填 | 合法值域 | 缺失时行为 |
|---|---|---|---|
| `--brand` | 是 | 品牌名或编号 | 缺 → `exit 2` |
| `--country` | run-exposure 必填；其余可选 | ISO 国家码 | 缺 → 取品牌档案第一个市场；交付注明 |
| `--days` | 否 | 默认 30 | 缺 → 30；窗口必须写进交付 |
| `--video-brand` | 否 | 竞品名 | 缺 → 只取本品视频 |
| `--limit` | 否 | 默认 30 | `getBrandVideos.limit` 是上限且无分页，`offset` 被静默忽略 |

**输出**

| 字段 | 来自 | 口径登记 |
|---|---|---|
| 各品牌播放量／视频数／份额 `share` | `overview` | **M8**（unknown，分母未声明） |
| 品类／子品类 ＋ 登记竞品 | `categories` | 竞争集唯一权威＝品牌自己配的竞对 |
| 视频标题／频道／播放量／发布时间 | `brand-videos` | 视频级（未登记） |

**前置条件**：P1 品类档案存在；P2 该口径已跑过曝光采集（否则份额为空／旧值）；P3 市场与窗口已声明。

**门禁**

| # | 门禁 | 判据 | 停了之后 |
|---|---|---|---|
| G1 | 品牌不在结果里却写 0% | `brand_share` 返回 `None` | 写「该品牌不在本次统计内」，不臆造 0 |
| G2 | 竞争集被自行收窄 | 只取份额前三 | 以 `sov categories` 的登记竞对为准 |
| G3 | 口径没声明 | 交付没有市场＋窗口 | 先声明再计算，全文一致 |
| G4 | 与 M9 混用 | 同段既用平台份额又用提及份额 | 分开写并各标「不同分母」 |
| G5 | 份额与情感脱离 | 只报份额不报情感 | 负向高声量是警告，必须同读 |
| G6 | 把 C 类当可用 | 想配品类档案／跑 SEO SOV | 停：见 §5.4，卡片不得指向 |

**失败形态**

| 类 | 具体形态 | 话术 | 下一步 |
|---|---|---|---|
| 错误码 | `exit 2` 品牌不存在／`assocId` 与 `id` 弄混 | 「这个品牌查不到品类档案」 | 先跑 `sov categories` 拿档案 |
| 超时 | 曝光采集未终态 | 「采集任务还没跑完（任务号 X）」 | 查终态；不重复触发 |
| 无数据 | 份额为空 | 分辨「没跑过采集」与「跑了但无收录」 | 前者触发采集（B，需确认）；后者写「该窗口无收录」 |

**是否写操作**：`run-exposure` **是**（`write=True`／`live`）；其余 **否**。触发前切工作区并回读。
**出处**：`schema.py#sov.*`；`.kol-tools/daniel_sov.py:226–246`；`references/60-data-layer.md:242,249,360–362`；`kol-execution-sov/SKILL.md:87–104`；审计 §2 第 4–5 行／B2–B3。

### 4.7 CAP-07 建联取数（`CAP-07-outreach-fetch`）

**命令／路由**（不在 Daniel 内，Nox 只读接管）

| # | 命令 | 取到什么 | 落盘 | 档 |
|---|---|---|---|---|
| 1 | `noxinfluencer email list --keyword <项目> --page_size 50` | 批次、`task_id`、建立时间 | `raw/email_list.json` | A |
| 2 | `noxinfluencer email report <task_id>` | 发送／到达／打开／回复／退订 | `raw/email_report_<task>.json` | A |
| 3 | `noxinfluencer email rounds <task_id>` | 轮次、每轮主题 | `raw/email_rounds_<task>.json` | A |
| 4 | `noxinfluencer email recipients list <task_id>` | 逐人状态（opened/sent/unsubscribed） | `raw/email_recipients_<task>.json` | A |
| 5 | `noxinfluencer message list --business_kind email_task --business_id <task_id>` | 会话列表 | `raw/message_list_<task>_p<N>.json` | A |
| 6 | `noxinfluencer message get -- <thread_id>` | 会话全部往来邮件 | `raw/messages/<thread>.json` | A |
| 7 | `noxinfluencer creator profile <creator_id> --json` | 红人档案（0.2 积分/人） | `raw/creators/…` | A |
| 8 | `noxinfluencer collection list --keyword <项目> --page_size 100` | 清单 | `raw/collection_*.json` | A |
| 9 | `noxinfluencer collection items <collection_id> --body-file -` | 清单里的红人 | `raw/collection_items*.json` | A |
| 10 | `bash run.sh <task>[,<task>] [--window A..B]` | 串联 1–7 并出页 | `raw/` | A |
| — | 发信／回信 | 包内 0 路由、0 工具 | — | **C** |

**输入**

| 字段 | 必填 | 合法值域 | 缺失时行为 |
|---|---|---|---|
| `--keyword` | 是（找批次／清单） | 项目关键词（配 `PROJECTS.yaml` 的 `nox_keyword`） | 缺 → 列不出批次 |
| `task_id` | 是（报表／会话） | 批次号；周报多批逗号分隔 | 缺 → 只出批次清单 |
| `--window A..B` | 周报必填 | 日期区间；脚本不猜自然周 | 缺 → 按批次自身时间 |
| `--out <目录>` | 否 | 落盘根 | 缺 → 当前 `raw/` |
| `--refresh-profiles` | 否 | 开关（0.2 积分/人） | 缺 → 已取过的跳过 |

**输出**：`raw/` 九类文件（`email_list`／`email_report_<task>`／`email_rounds_<task>`／`email_recipients_<task>`／`message_list_<task>_p<N>`／`messages/<thread>`／`attachments/parsed.json`／`images.json`／`fetch_failures.log`）。

**前置条件**：P1 `which noxinfluencer` 可见；P2 已登录（本机凭据）；P3 `PROJECTS.yaml` 的 `nox_keyword` 与 `engine` 正确；P4 时间窗已给（周报）。

**门禁（C1–C7，来自 `nox-cli` §十）**

| # | 门禁 | 判据 | 停了之后 |
|---|---|---|---|
| C1 | 只读 | 全程无写命令；`raw/` 之外无改动 | 任何「改状态／发信」不在这层 |
| C2 | 数字对得上 | 落盘指标＝接口原文，不二次计算 | 不自己重算 Nox 已给的数 |
| C3 | 失败已处理 | `fetch_failures.log` 为空，或失败已重试并说明 | 不得默认「全取到了」 |
| C4 | 可复跑 | 同批再跑不重复扣积分 | — |
| C5 | 附件全下 | 会话附件有本地副本或明确失败原因 | 缺件写清 |
| C6 | 未读副作用已告知 | 交付说明写明「读会话会清未读」 | 不说就是隐瞒副作用 |
| C7 | 轮号不跨批相加 | 各批轮号各自从 1 起 | 跨批只能加「轮数」不能加「轮号」 |

**失败形态**

| 类 | 具体形态 | 话术 | 下一步 |
|---|---|---|---|
| 错误码 | 鉴权失败（401／未登录） | 「Nox 登录态过期了」 | 重新登录（约一年有效）；不重试同一命令 |
| 超时 | 限流 429／单条 `message get` 超时 | 「这条超时了，其余照跑」 | 超时条目重试；仍失败写进 `fetch_failures.log` |
| 无数据 | 批次不存在 vs 批次 0 发送 | 「这个关键词下没有这个批次」／「这批 0 人」 | 换 `--keyword`／核对 `email list` 建立时间 |

**是否写操作**：**否**（对 Nox 全程只读；只写本地 `raw/`）。发信／回信属 C 类，不在本能力。
**出处**：`nox-cli/SKILL.md:41–62,130–140,176–197`；`nox-weekly/SKILL.md:69–74,191`；`docs/marketing/nox-outreach/PROJECTS.yaml`；审计 §3 C1。

### 4.8 CAP-08 VOC 分析（`CAP-08-voc`）

**命令／路由**（三层：取数／日雷达／报告）

| 层 | 入口 | 命令／文件 | 档 |
|---|---|---|---|
| 取数 | 按平台脚本 | `node crawl-ks.mjs …`／`node platform-reddit.mjs …`／`PLAYWRIGHT_BROWSERS_PATH=… node platform-avsforum.mjs …`／CDP 取 YT 评论 | A |
| 每日雷达 | `daily-radar` | `python3 tools/voc-crawler/build_radar.py --date <YYYY-MM-DD> …`（干跑加 `--dry-run`） | A |
| 报告 | `voc-report` | 无单命令；按 §四归类 → §五结构 → §六门禁 | A |

**输入（约束卡六类，缺一类就返工）**

| 类 | 必须写清 | 缺失时行为 |
|---|---|---|
| 对象 | 产品／型号／变体（含旧款同名排除） | 缺 → 停：型号级匹配表不齐不能开工 |
| 平台 | Reddit／YouTube／论坛／众筹页 | 缺 → 按默认并声明「仅此平台」 |
| 时间窗 | 起止＋时区 | 缺 → 默认窗口并写明；输出要给「窗口外最近一条」 |
| 覆盖 | 「但凡包括 X 都要」还是「看个大概」 | 缺 → 按「看个大概」并写未覆盖部分 |
| 交付 | 文档／表格／HTML／只要结论 | 缺 → HTML 单页＋明细 CSV |
| 口径 | 分母、是否带原文、排序字段 | 缺 → 默认口径并在报告开头标注 |

**输出**

| 字段 | 来自 | 备注 |
|---|---|---|
| 四个数：页面自报总数／实际抓到／去重后唯一／官方回复数 | 取数层 | 缺一个即「数据不够」 |
| 覆盖三态：覆盖到／欠覆盖／截断／工具无法核验 | 取数层 meta | 三态分开写 |
| 逐条归类：三档＋原因码＋判定依据句（≤30 词原文） | 归类层 | 摘不出依据句 ⇒ 中性或进二判 |
| 两栏分母：A 全样本／B 有态度子集 | 报告层 | 永不同段混用 |
| 一致性：两次归类一致率 | 抽 30–50 条重跑 | <90% 先修判据再出结论 |

**前置条件**：P1 平台状态以 `tools/voc-crawler/STATUS.md` 为准（禁止现场调试）；P2 原始数据已落盘（`data/crawl/<project>/`，含 meta）；P3 约束卡六类齐；P4 若用登录态（YT 评论 CDP），用户先开好调试端口。

**门禁（G1–G9）**

| # | 门禁 | 判据 | 不过怎么办 |
|---|---|---|---|
| G1 | 约束卡存在 | 六类都有检查项 | 回去补 |
| G2 | 数据可定量 | 四个数齐全、覆盖三态已写 | 降级为「可见样本」 |
| G3 | 归类可复算 | 两次一致率 ≥90%；每条有依据句 | 修判据重跑 |
| G4 | 两栏分母 | 两栏同时出现、各写分子分母、同段不混 | 重写该段 |
| G5 | 结构合格 | 标题连读像结论清单；真痛点四段齐 | 重写结构 |
| G6 | 原声可回溯 | 3–5 条/论点，编号与平台正确，未改写 | 补编号或删 |
| G7 | 条/人双报 | 条数与人数都出现 | 补人数 |
| G8 | 措辞干净 | 无「普遍/大多数」；禁用词命中 0 | 改写 |
| G9 | 资产完整 | `python3 tools/check_skill_assets.py --strict` 退出码 0 | 补齐再跑 |

**失败形态**

| 类 | 具体形态 | 话术（三选一） | 下一步 |
|---|---|---|---|
| 错误码 | 平台脚本报错（406/403/挑战页） | 按 STATUS.md 判定已知受限，报实际错误 | 记录并回报；不静默换路 |
| 超时 | 抓取长时间无进展 | 「这轮还没跑完，当前覆盖到 X 条」 | 记录断点；不假装完成 |
| 无数据 | 0 命中 | 「窗口内核验到真实讨论」／「公开搜索未发现但工具或覆盖不足」／「窗口内未检索到」 | 三句选一，不写「没有讨论」 |

**是否写操作**：**否**（只写本地 `data/crawl/`、`docs/marketing/voc/`）。
**数据红线**：不编造／不绕过（登录、验证码、权限）／不冒充覆盖（`web_search` 只做候选发现）／不把「没搜到」当「没有」。
**出处**：`voc-intelligence.md:33–47,64–90`；`voc-report/SKILL.md:32–113,230–242`；`daily-radar/SKILL.md:73–76`；`tools/voc-crawler/STATUS.md`。

### 4.9 八个能力横向对照

| 能力 | 主命令 | 读面 | 写面 | 必过门禁 | 工序 |
|---|---|---|---|---|---|
| CAP-01 检索 | `search submit`／`open_research` | 5 | 2（deep/open 提交） | G3 roster 退役（不得重试） | `discovery-07` |
| CAP-02 档案 | `daniel_kol_profile` | 3 | 0 | G1 `empty` ≠「没有受众」 | `screening-01` |
| CAP-03 品牌 | `brands show` | 4 | 4（create/update/clone/delete） | G2 同名必须给编号 | `daniel-api-03` |
| CAP-04 名单 | `lists items`／`add-items` | 5 | 4（加人／建／改名／删） | G5 回读不一致 `exit 1` | `daniel-api-01/02` |
| CAP-05 提及 | `mentions results` | 7 | 1（run） | G1 两池合并 ＋ G2 显式 `all` | `daniel-api-04/05` |
| CAP-06 声量 | `sov overview` | 3 | 1（run-exposure） | G1 不在结果里不是 0% | `daniel-api-07` |
| CAP-07 建联 | `noxinfluencer email …` | 9 | 0 | C3 `fetch_failures.log` 必须看 | 无（域外） |
| CAP-08 VOC | `build_radar.py` ＋ 工序 | 3 | 0（只写本地） | G4 两栏分母永不同段混用 | 无（域外） |

> 合计 **86 个能力面**：A 39／B 12／C 35（§5.3）。

---

## 5. 能力可用性分级

### 5.1 三档定义

| 档 | 定义 | 允许的调用方式 | 是否要人确认 |
|---|---|---|---|
| **A** | Bot 可直接执行，无副作用（读；含包外只读 CLI） | `daniel_run`／`daniel_batch`／`daniel_*` 专用读工具／本机只读命令 | 否 |
| **B** | 写操作，必须走确认 | `daniel_write_plan` → 用户确认 → `daniel_write_commit`；CLI 侧 `--confirm` | **是**（一次确认只对一次执行） |
| **C** | 当前不可用（无 CLI 入口／通道退役／能力本身不存在） | 禁止调用；不得用其它来源冒充 | — |

> 分级对象有两层：**能力主档**（8 个能力各一档，按「主动作」定）与**能力面**（每条命令／路由一档）。下一步卡片按**能力面**判（§6）。

### 5.2 八个能力的主档

| 能力 | 主档 | 理由 | A 面 | B 面 | C 面 |
|---|---|---|---|---|---|
| CAP-01 红人检索 | **B** | 主动作是提交检索（写） | 5 | 2 | 1 |
| CAP-02 红人档案 | **A** | 纯读 | 3 | 0 | 0 |
| CAP-03 品牌档案 | **A** | 主动作是看档案（读）；4 条写另标 B | 4 | 4 | 2 |
| CAP-04 名单管理 | **B** | 主动作含加人／建删（写） | 5 | 4 | 7 |
| CAP-05 品牌提及 | **B** | 主动作含发起分析（写） | 7 | 1 | 7 |
| CAP-06 声量份额 | **B** | 主动作含发起采集（写） | 3 | 1 | 17 |
| CAP-07 建联取数 | **A** | 全程只读 | 9 | 0 | 1 |
| CAP-08 VOC 分析 | **A** | 只写本地 | 3 | 0 | 0 |

**主档计数：A 4 ／ B 4 ／ C 0**（8 个能力全部至少有 A 或 B 路径；C 只出现在能力面层）。

### 5.3 能力面计数

| 能力 | A 面 | B 面 | C 面 | 合计 |
|---|---|---|---|---|
| CAP-01 | 5 | 2 | 1 | 8 |
| CAP-02 | 3 | 0 | 0 | 3 |
| CAP-03 | 4 | 4 | 2 | 10 |
| CAP-04 | 5 | 4 | 7 | 16 |
| CAP-05 | 7 | 1 | 7 | 15 |
| CAP-06 | 3 | 1 | 17 | 21 |
| CAP-07 | 9 | 0 | 1 | 10 |
| CAP-08 | 3 | 0 | 0 | 3 |
| **合计** | **39** | **12** | **35** | **86** |

### 5.4 C 类清单（35 条，逐条写缺什么、何时补）

| # | 能力 | C 面（路由／命令） | 缺什么 | 何时补 |
|---|---|---|---|---|
| 1 | CAP-01 | `discovery.searchRoster`／`daniel_roster_search` | 通道已退役（2026-09-14 起 503、09-16 起读超时） | **不补**；永久退役，替代 deep／open |
| 2 | CAP-03 | `brands.verifyChannel` | CLI 无命令 | P1（小） |
| 3 | CAP-03 | `brands.suggestCompetitors` | CLI 无命令 | P1（小） |
| 4 | CAP-04 | `lists.batchRemoveItems` | CLI 无命令；入参未实测 | P1（中） |
| 5 | CAP-04 | `lists.getOverlap` | CLI 无命令 | P1（中） |
| 6 | CAP-04 | `lists.removeOverlaps` | CLI 无命令 | P1（中） |
| 7 | CAP-04 | `lists.mergeLists` | CLI 无命令 | P1（中） |
| 8 | CAP-04 | `lists.updateItemTags` | CLI 无命令 | P1（中） |
| 9 | CAP-04 | `lists.generateShareLink` | CLI 无命令 | P1（中） |
| 10 | CAP-04 | `lists.autoPriority` | CLI 无命令 | P1（中） |
| 11 | CAP-05 | `brandMentions.collectVideoSources` | CLI 无命令；触发类不可撤 | P1（中，需写链设计） |
| 12 | CAP-05 | `brandMentions.runVideoDeepReview` | 同上 | P1（中） |
| 13 | CAP-05 | `brandMentions.analyzeHighAttention` | 同上 | P1（中） |
| 14 | CAP-05 | `brandMentions.retryJob` | 同上 | P1（中） |
| 15 | CAP-05 | `brandMentions.cancelJob` | 同上 | P1（中） |
| 16 | CAP-05 | `brandMentions.deleteJob` | 删除类写，对生产品牌 | P2（需单独评审） |
| 17 | CAP-05 | `brandMentions.retryVideoReplay` | CLI 无命令 | P1（中） |
| 18 | CAP-06 | `sovCategories.aiSetup` | CLI 无命令；会重建品类口径 | P1（大） |
| 19 | CAP-06 | `sovCategories.confirmAISetup` | 同上 | P1（大） |
| 20 | CAP-06 | `sovCategories.runDiagnosis` | CLI 无命令 | P1（大） |
| 21 | CAP-06 | `sovCategories.applyDiagnosis` | CLI 无命令 | P1（大） |
| 22 | CAP-06 | `sovCategories.updateBrandConfig` | CLI 无命令 | P1（大） |
| 23 | CAP-06 | `sovCategories.updateFilterKeywords` | CLI 无命令 | P1（大） |
| 24 | CAP-06 | `sovCategories.addCompetitorWithValidation` | CLI 无命令 | P1（大） |
| 25 | CAP-06 | `sovCategories.unlinkBrand` | CLI 无命令 | P1（大） |
| 26 | CAP-06 | `sovCategories.generateFilterKeywords` | CLI 无命令 | P1（大） |
| 27 | CAP-06 | `sovCategories.list` | CLI 无命令 | P1（小） |
| 28 | CAP-06 | `sovCategories.getFilterStats` | CLI 无命令 | P1（小） |
| 29 | CAP-06 | `seoSov.listWeeks` | CLI 无命令（只做了 Exposure） | P1（中） |
| 30 | CAP-06 | `seoSov.getHeatmap` | 同上 | P1（中） |
| 31 | CAP-06 | `seoSov.getKeywordDetail` | 同上 | P1（中） |
| 32 | CAP-06 | `seoSov.getTaskStatus` | 同上 | P1（中） |
| 33 | CAP-06 | `seoSov.runCollection` | CLI 无命令；采集类写 | P1（中） |
| 34 | CAP-06 | `exposureSov.forceRefresh` | CLI 无命令；绕缓存、耗配额 | P2（低优先） |
| 35 | CAP-07 | 发信／回信 | 包内 0 路由、0 工具；Nox 在独立 CLI | P2（跨系统） |

**C 类合计 35 条**：CAP-01 1／CAP-03 2／CAP-04 7／CAP-05 7／CAP-06 17／CAP-07 1。
> 审计 §3 的 C 类另有「同步飞书」「内容情报删除类写」「真实性分数写入」3 条；它们不属于本文 8 个 P0 能力面，未计入 35（见审计 §3）。

### 5.5 计数自洽

| 口径 | 数 | 算式 |
|---|---|---|
| 8 能力主档 | A 4／B 4／C 0 | §5.2 |
| 能力面 | A 39／B 12／C 35 = 86 | §5.3 |
| 审计「无任何入口 59 条」 | 41（A 组）＋18（B 组） | 审计 §3；本文只取与 8 能力重叠的 C 面 35 条，差额为用户未纳入 P0 的其它路由 |
| 工具数 | 20（基线 ≡ 代码） | §0.6① |

---

## 6. 下一步卡片的约束

### 6.1 规则

| # | 规则 | 判据 |
|---|---|---|
| 1 | 卡片只能指向 **A 或 B** 能力面 | 卡片 `action` 必须能在 §5.3 找到对应面，且档为 A／B |
| 2 | **禁止指向 C** | C 面不得出现在卡片的可执行动作里；只能出现在「为什么现在不能做」的说明里 |
| 3 | B 面卡片必须带三件 | 干跑命令／影响范围／「需要你确认后我才执行」 |
| 4 | 一次确认只对一次执行 | 不得把一张 B 卡片的确认复用给下一次写 |
| 5 | 卡片不得合并两个写动作 | 加人＋建名单必须两张卡片 |
| 6 | 卡片文案不写内部字段名 | 用业务词（名单、品牌、均播），不用 `channelId`／`batchAddItems` |

### 6.2 卡片 → 能力面映射（可用卡片）

| # | 卡片 | 指向面 | 档 | 前置 | 用户看到的话 |
|---|---|---|---|---|---|
| 1 | 看品牌档案 | `brands show` | A | 品牌已建档 | 「我先把这个品牌的档案调出来」 |
| 2 | 列出某品牌名单 | `lists by-brand` | A | 品牌已建档 | 「我先看这个品牌下有哪些名单」 |
| 3 | 看名单成员 | `lists items` | A | 有 `listId` | 「我把名单里的人读出来」 |
| 4 | 看提及任务 | `mentions jobs/status/results` | A | 任务存在 | 「我先看这个任务跑到哪了」 |
| 5 | 看提及图表 | `mentions chart` | A | 任务终态 | 「我把五块分布拉出来」 |
| 6 | 看头部频道 | `mentions top-channels` | A | 任务终态 | 「我按综合表现排前 N 个频道」 |
| 7 | 导出提及明细 | `mentions export` | A | 任务终态 | 「我把明细导成一张表（可能稍慢）」 |
| 8 | 补频道公开数据 | `search enrich` | A | 有频道编号 | 「我把订阅数／国家／标签补齐」 |
| 9 | 看声量总览 | `sov overview` | A | 品类档案存在＋采集过 | 「我读一下这个市场窗口的份额」 |
| 10 | 往名单加人 | `lists add-items` | B | 干跑已给用户看 | 「这是将要加的 N 人／跳过 M 人／预计 X 批；你确认后我才写」 |
| 11 | 建／改名／删名单 | `lists create/rename/delete` | B | 干跑＋（删除）目标名回填 | 「这是改动前后对照；你确认后我才执行」 |
| 12 | 发起提及分析 | `mentions run` | B | 工作区已切并回读 | 「会触发采集、产生用量；你确认后我才跑」 |
| 13 | 发起曝光采集 | `sov run-exposure` | B | 品类档案存在 | 「会触发采集；你确认后我才跑」 |
| 14 | 发起检索（deep/open） | `search submit`／`open_research` | B | 计划已给用户看 | 「这是计划（检索式／影响／额度）；你说可以我才提交」 |

### 6.3 C 类：卡片不得指向，只能给替代话术

| C 面 | 禁止的卡片文案 | 替代话术（照抄） |
|---|---|---|
| 官方库检索 | 「用官方库找红人」 | 「官方库通道已停用（零发包）；有品牌我走品牌深度研究，没品牌我走 AI 开放研究」 |
| 名单删人／合并／去重／分享链接 | 「帮你把两份名单合并」 | 「当前只能读名单并给你合并后的文件；写回名单要你在 Daniel 网页端做」 |
| 提及触发守卫／重试／取消 | 「失败了我帮你重试」 | 「任务失败要重跑，目前没有命令；我可以帮你重新发起一次分析（写，需你确认）」 |
| 品类档案写 | 「我先帮你建品类档案」 | 「品类档案要在 Daniel 网页端配置；配好后我能读份额」 |
| SEO SOV | 「我拉一下 SEO 声量」 | 「SEO 声量还没接命令；现在能读的是 Exposure 份额与提及份额」 |
| 发信／回信 | 「我帮你回这封邮件」 | 「发信不在当前能力内；我可以把回复草稿写给你，由你在邮箱里发」 |
| 同步飞书 | 「我同步到飞书」 | 「同步飞书还没有路由；我可以出本地文件，你上传」 |

---

## 7. 待确认清单（收敛后）

### 7.1 总账

| 项 | 数 | 明细 |
|---|---|---|
| 草案原清单 | **23** | Q-01 … Q-23 |
| 已解决 | **10** | Q-01／Q-02／Q-03／Q-06／Q-09／Q-12／Q-14／Q-19／Q-20／Q-23 |
| **仍待 Jack 拍板** | **13** | 其中 **9 条阻塞定稿入库**、**4 条可随实施推进** |
| 另有证据缺口 | 8 条 | N-1 … N-8（不是决策项，§7.5） |

### 7.2 已解决（10 条，逐条写「怎么定的／改了什么」）

| # | 原问题 | 结论 | 改了什么 |
|---|---|---|---|
| Q-01 | 登记表形态（`surfaces` vs `取值面`） | 扩展现有 `_ONTOLOGY.json`；面写进 `surfaces`，不设 `取值面` 字段 | §2 全部指标改为 `surfaces.<面键>`；§3 schema；§2.19 映射表 |
| Q-02 | 退役通道的工具／语料文案 | 按「零发包」改写；工具说明已改，语料已无正向表述 | §1.2；§4.1 G3；剩余两处「自动执行」文案列入 I-3 |
| Q-03 | 名单均播窗口冲突 | 拆两条：`drawer_28d`（28 天）／`pool_12m100`（12 个月∩100 条）；窗口进名字与定义 | §1.3；§2.9／§2.10；契约列名只映射 M2 |
| Q-06 | 「导入名单」无命令 | 已落地 `lists add-items`（写、两段式、拆批、回读、审计） | §4.4 全节；§5.2／§5.4 |
| Q-09 | 工具数口径（14 vs 19 → **20**） | 2026-11-08 按 **20** 归一（`daniel_open_research_commit` 计入）；P0 约束改「不新增第 21 个工具」 | §0.6①；§1.4；§4.0；§5.5 |
| Q-12 | `data_status` 两套词 | 前提不成立：随包登记表无 `data_status`、无两值词表 | §0.5；§2.21；v1.2 两值方案不采用 |
| Q-14 | 互动率 `list_item` 面是否单开 id | 不单开：Q-01 结构已能承载多面，写在 M6 的 `surfaces.list_item` | §2.13；如 Jack 要单开，只改 id 不改数据 |
| Q-19 | 是否新增 `concept` 类型 | 新增 | §3.4；`ontology.py:33` 已识别 concept |
| Q-20 | 名单人数以谁为准 | 既有工序已裁决：以读到的成员为准并标注 | §2.6；`processes.json#daniel-api-01` |
| Q-23 | 登记项语言 | 沿用「英文 id ＋ 中文 label」 | §3.2#1；`_IDREF_RX` 只认 ASCII（`ontology.py:33`） |

### 7.3 仍待拍板（9 条，阻塞定稿入库）

> 每条格式：问题 → 选项 → 建议 → 影响面。**2026-11-08 起这 9 条已有默认方案（§7.7）：Jack 只需否决不认同的；本表作为被否项的 A／B／C 备选保留。**

| # | 问题 | 可选 | 建议 | 影响面 |
|---|---|---|---|---|
| **Q-05** | 建联（Nox）与 VOC 是否纳入语义层 | A 纳入<br>B 只做 Daniel 内<br>C 纳入但标 `domain: external` | **A**（M10 已按此写；不纳入则「回复率」仍有两套说法） | 决定 M10 是否入册；若不纳入，10 条变 9 条 |
| **Q-07** | 型号／产品是否作为概念登记 | A 登记为 concept（标 unknown）<br>B 只登记为「任务模式」枚举<br>C 不登记 | **A** | 决定 5 个概念的第 2 条；不做则品牌池／SKU 池继续混 |
| **Q-08** | 「渠道」一词两义（平台 vs 品牌频道） | A 改名「取数渠道／平台」<br>B 保留「渠道」但每次带限定<br>C 用英文 `domain` 作 id | **A** | 决定 `concept.channel` 的 label 与全部交付措辞 |
| **Q-10** | 阈值／基准区间能否进随包语料 | A 只登记术语与口径名，不登记阈值<br>B 全量登记，靠整包加密<br>C 登记项加密后切分 | **A**（`$60–80` 属内部参考，母本 L3225 已写「不写进交付物」） | 决定 M7 的 `definition` 是否可写基准区间；影响防解包 |
| **Q-11** | 字段字典能否作正式出处 | A 提升为语料切片<br>B 只作 dev-side 出处<br>C 复制关键段落进母本 | **B（P0）→ C（P1）** | 决定 §2 各条 `source` 能否引 `_DANIEL-FIELD-DICTIONARY.md`；影响 C19-b 可自证性 |
| **Q-13** | 视频级指标是否进 P0 | A 只登记频道级（现状）<br>B 砍 M4 换「观看量」<br>C 扩到 14 条 | **A ＋ P1 补齐** | 决定 10 个名额；视频级（播放／点赞／Rated Score／相关性）继续靠契约文字 |
| **Q-15** | `owner` 先由谁签 | A 全改「总监（代签）」<br>B 沿用「业务-红人组」＋ `signed_by`<br>C 按指标域分派 | **B** | 决定 19 条登记项的 `owner` 值；C19-c 会因空 owner 报红 |
| **Q-16** | M2 的 `sample_rule` 冲突（时长>60 秒 vs `views≥100`） | A 以代码为准<br>B 以登记项为准（改代码）<br>C 两个都保留标「历史口径」 | **A** | 决定 M2 的 `sample_rule` 与抽屉复算一致性 |
| **Q-21** | 样本门槛 `N<5` 是否硬门 | A 硬门<br>B 软警告<br>C 分指标定 | **A** | 决定各条 `min_sample` 是硬门还是提示；低样本排序随机 |

### 7.4 可随实施推进（4 条，不阻塞本次入库）

| # | 问题 | 建议 | 不决的临时处置 |
|---|---|---|---|
| **Q-04** | 平台声量份额分母未声明 | B（P0 标注「分母待确认」）＋ A（跟进确认） | M8 保持 `unknown`，交付强制标「分母待确认」 |
| **Q-17** | CPM 的 `play_basis` 默认值 | A（按成交形式；没给形式时停） | 手册写「必须问清 1 长／1 短／组合」，未给则停 |
| **Q-18** | 「完成带告警」算不算可用 | A（算可用，交付标「带告警」） | CAP-05 按 A 写；如 Jack 选 B 只改话术 |
| **Q-22** | 是否现在建 20 任务度量集 | C（先建 5 条对应五个验收场景） | 本阶段不建；§3.9 之外单列下一阶段 |

### 7.5 证据缺口（8 条，不是决策项）

| # | 缺什么 | 现状 | 补法 |
|---|---|---|---|
| N-1 | 平台声量份额公式（`share` 分母） | 无逐字公式 | 前端 bundle 逆向或问平台；Q-04 跟进 |
| N-2 | CPM 基准区间是否仍现行 | 母本写 2026-09-08 团队口径 | 找业务确认；Q-10 关联 |
| N-3 | 「有界全量池」实现在哪 | 仓库无对应函数（母本 L724 只有文字） | 需要一次实现（P1） |
| N-4 | 提及「告警」类型枚举 | 库内只有「完成带告警」一句 | 平台确认；Q-18 关联 |
| N-5 | Nox「回复」是否含自动回复／退订回复 | 四类回复定义未与 Nox 原始字段逐一对齐 | 取一批样板逐条对齐 |
| N-6 | VOC 是否进索引 | 无 Daniel 字段 | 取决于 Q-05 |
| N-7 | `brands list` 跨不跨工作区 | 两份库内材料矛盾 | 同一账号、两个工作区实测一次 |
| **N-8** | `avg_views_long.surfaces.reported`（最新 30 条均值）的归属 | 定稿 10 条无承接项 | P1 决定「登记为第 11 条」或「随 legacy 下线」 |

### 7.6 审批栏（Jack 填）

| 项 | 结论（同意／改／否） | 备注 |
|---|---|---|
| 三条决策（Q-01／02／03） | | |
| 9 条阻塞项：按 §7.7 默认方案执行（**不写＝同意；否决才写 Q 号**） | | |
| 4 条可延后（Q-04／17／18／22） | | |
| 是否同意本文件作为阶段 0 定稿 | | |

---

### 7.7 阻塞项的默认方案（Jack 只需否决不认同的）

> **怎么用**：下面 9 条**默认即定稿**——Jack 只需回复「否决 Q-xx」，被否的那条再回 §7.3 选 A／B／C；没被点名的按本表执行，不再逐条等拍板。
> 每条一行：问题 → 默认方案（可直接照做）→ 理由 → 不这样的后果。方案里的字段名／取值都以 §3.2 schema 为准，不新增字段。

| 题 | 问题（一句话） | 默认方案（照此执行） | 一句话理由 | 如果不这样会怎样 |
|---|---|---|---|---|
| **Q-05** | 建联（Nox）与 VOC 是否纳入语义层 | 纳入：M10 保留为第 10 条，`external_only: outreach_system`；VOC 不单开条目，只在 M10 的 `definition` 末尾加「VOC 复核走 `voc-report`」；**不加 `domain` 字段**，外部来源一律用已有的 `external_only` 表达 | M10 已按外部系统写全（§2.17），再开 `domain` 等于给 26 个字段位再加一个取值域，门禁与解析器都要改 | 回复率两套说法（Nox 报表／交付话术）长期并存；M10 被删则 10 条变 9 条，CPM 与回复率跨表对不上 |
| **Q-07** | 型号／产品是否作为概念登记 | 登记 `concept.product`：`key: skuTerms`、`value_domain: 品牌方型号名；未知写 unknown、不造名`、`owner: 总监代签（2026-11-08）`、`version: 2.0.0` | 品牌池与 SKU 池现在混用同一串名字，只有概念层能把「品牌」与「型号」分开，且 `skuTerms` 与现有 `axes` 不冲突 | 「Halliday G1」被当品牌名写进品牌池；提及统计按品牌聚合时把型号算成一个品牌，SOV 分母被污染 |
| **Q-08** | 「渠道」一词两义（平台 vs 品牌频道） | `concept.channel` 的 `label` 改为「**取数渠道（平台）**」；`definition` 首句写死「渠道＝取数渠道，指平台（YouTube 等），不是某个品牌频道」；交付件里「渠道」单用一律写「取数渠道」 | 代码与契约里 `channel` 一直指平台（红人频道用 `channelId`），改的是 label 与措辞，不动 id、不动取数 | 同一句「渠道数据」被读成品牌频道或平台，SOV 与档案页各说一套，复核时无法判定哪个数对 |
| **Q-10** | 阈值／基准区间能否进随包语料 | **不进**：M7 的 `definition` 只写「CPM = 报价 ÷ N × 1000，N = M4」；`$60–80`／`$80–100` 只留母本 L3225，M7 的 `definition` 末尾加一句「基准区间：内部参考（不随包）」 | 母本自己已写「不写进交付物」；进包等于把内部砍价基准随插件外发，且 N-2 尚未确认该区间是否现行 | 客户装包即可读到议价底牌；未确认的区间会被当成硬门槛，报价判断从「上限校验」变成「按死价砍」 |
| **Q-11** | 字段字典能否作正式出处 | P0 **只作 dev-side 出处**：`source` 引 `_DANIEL-FIELD-DICTIONARY.md` 时后缀标「（dev-side）」，C19-b 只校验随包语料内的 id；P1 再把该字典 L144–171 提升为 `references/13-field-dictionary.md` 切片 | 把未入包的字典当正式出处，C19-b 的「引用可自证」就是空判据；标 dev-side 既不阻断 P0，也不假装它已入包 | C19-b 要么放过悬空引用（判据失效），要么全红（没人能过）；两种都让门禁失去意义 |
| **Q-13** | 视频级指标是否进 P0 | **10 条名额不动**：播放／点赞／Rated Score 不进 P0，只在 §2 末尾列「P1 候选三项」；**M4 保留**（CPM 的分母） | 视频级没有稳定取数面（详情接口实测只给 20 条），进册就得为每项配 `sample_rule`，P0 的 10 条撑不住 | 为凑视频级砍 M4 → CPM 失去分母只能退回 M1，报价判断整体失准；扩到 14 条则每条都要补 source／门禁，进度直接失控 |
| **Q-15** | `owner` 先由谁签 | 19 条 `owner` 统一写「**总监代签（2026-11-08）**」；**不新增 `signed_by` 字段**；Jack 逐条认领时只改 `owner` 的值 | C19-c 只要求 owner 非空、status≠draft；`signed_by` 要多扩一个字段和一处门禁，收益只是多一个名字 | owner 两套（业务-红人组／总监代签）并存，同一指标两个负责人，交付里「谁签字」说不清，C19-c 的报红风险留在每一条上 |
| **Q-16** | M2 的 `sample_rule` 冲突（时长>60 秒 vs `views≥100`） | **以代码为准**：M2 写「长视频＝`VIDEO_ON_DEMAND` 且 `views≥100`；短视频＝`SHORTS`（无播放阈值）；28 天内 ≥3 条用该批，否则最新 30 条」，删掉「时长>60 秒」，并在 M2 的 `definition` 末尾记一句「历史口径『时长>60 秒』已按代码更正」（schema 无 `notes` 字段，不新开） | 抽屉数字由 `normalize.js` 现算，登记项写另一套条件会让「复算对不上」变成永久缺陷 | 同一红人抽屉 N 条与登记口径算出的 N 条不同；一被抽查就判「数据造假」，且无法自证是旧口径 |
| **Q-21** | 样本门槛 `N<5` 是否硬门 | **硬门**：均播／互动率 `N<5` 一律只说「样本不足（N<5）」、不出数；M7／M10 按各自登记的 `min_sample: 1` 执行，不套 5 | M2／M3 已写 5；M7／M10 是比例型单行计算，强行套 5 会把回复率与 CPM 全部卡死 | 3 条视频的平均播放被当「均播」出结论，排序随机且无法复核；反过来一刀切 N≥5 会让报价与建联两块无数据可用 |

**4 条可延后项（不阻塞入库；按下列默认先跑，P1 再回来改）**

| 题 | 问题 | 默认方案 | 不阻塞入库的原因 |
|---|---|---|---|
| **Q-04** | 平台声量份额分母未声明 | M8 保持 `unknown`；交付强制标「分母待确认（平台未公布）」；N-1 继续跟进 | 只影响 M8 的一句话术，不改数据结构 |
| **Q-17** | CPM 的 `play_basis` 默认值 | 按成交形式取值（1 长／1 短／组合）；没给形式就停，先问清再算 | 属算子册写法，不改登记表字段 |
| **Q-18** | 「完成带告警」算不算可用 | 算可用；交付标「带告警」，并在下一步里给补采动作 | 只影响 CAP-05 的话术，接口语义不变 |
| **Q-22** | 是否现在建 20 任务度量集 | 本阶段不建；下一阶段先建 5 条对应五个验收场景 | 是实施节奏问题，与定稿入库无关 |

---

## 8. 附录

### A. 验收自检（对四项验收的原始答案）

**① 决策记录三条**

| # | 决策 | 一句话 |
|---|---|---|
| Q-01 | 登记表形态 | 扩展现有 `_ONTOLOGY.json`；不新建 `取值面` 字段，面写进 `surfaces`（键＝六值面键） |
| Q-02 | 官方库退役 | 通道退役、零发包；工具与语料文案改「已停用，改走 deep／open」；剩余两处「自动执行」文案待改 |
| Q-03 | 均播拆窗 | 拆 `drawer_28d`（近 28 天）与 `pool_12m100`（12 个月∩最新 100 条）两条；窗口进名字与定义 |

**② 登记表 schema 扩展的字段清单（26 个字段位）**

- 条目级 18 项：`id`／`type`（＋`concept`）／`label`／`owner`／`status`（＋`superseded`）／`stage`／`availability`／`definition`／`surfaces`／`external_only`（＋`none`）／`data_status`／`source`／`version`／`axes`／`key`／`value_domain`／`superseded_by`／`scenarios`・`groups`
- `surface` 子字段 7 项：`kind`／`window`／`sample_rule`／`min_sample`／`data_status`／`unit`／`source`
- 索引顶层 1 项新增：`schema_version`
- 合计：18 ＋ 7 ＋ 1 = **26 个字段位**
- 其中**真正新增 10 个字段**：`definition`／`data_status`／`source`／`key`／`value_domain`／`superseded_by`／`schema_version`，以及 surface 的 `data_status`／`unit`／`source`
- 另有**4 处取值扩展**：`type`（＋`concept`）／`status`（＋`superseded`）／`external_only`（＋`none`）／`kind`（＋`derived`／`snapshot`／`count`）

**③ 能力分级 A／B／C**

| 口径 | A | B | C |
|---|---|---|---|
| 8 个能力主档 | **4**（CAP-02／03／07／08） | **4**（CAP-01／04／05／06） | **0** |
| 86 个能力面 | **39** | **12** | **35** |

C 类 35 条：CAP-01 1 条（官方库退役）／CAP-03 2 条／CAP-04 7 条／CAP-05 7 条／CAP-06 17 条／CAP-07 1 条；逐条见 §5.4。

**④ 收敛后待确认条数**

**23 条 → 13 条**（已解决 10；剩 9 条阻塞入库 ＋ 4 条可延后）；另有 8 条证据缺口（N-1…N-8），不计入决策条数。

### B. 引用清单（本文件用到的全部出处）

| # | 文件／命令 | 用在 |
|---|---|---|
| 1 | `daniel-bot/specs/PHASE0-ONTOLOGY-DRAFT.md` | 全文字段与出处链的上游 |
| 2 | `daniel-bot/specs/CAPABILITY-GAP-AUDIT.md` | 能力分级与 C 类 |
| 3 | `.../mcp/corpus/_ONTOLOGY.json` | 现有 4 条、`entry_count`／`corpus_version` |
| 4 | `.../mcp/corpus/_MANIFEST.json` | 0.9.206／8 束／41 文件／25 切片／7,164 行 |
| 5 | `.../mcp/corpus/kol-intelligence/references/12-ontology-registry.md` | B.1–B.5、登记纪律 |
| 6 | `.../daniel_cli/ontology.py` | `_IDREF_RX:33`、`parse_entries:145–182`、`build:187` |
| 7 | `.../daniel_cli/corpus.py` | `_attach_ontology` 注入 |
| 8 | `.../mcp/check_ontology.py` | C19-a/b/c/e/f |
| 9 | `.../mcp/check_corpus_sync.py` | `_rebuild_ontology:480–506` |
| 10 | `.../daniel_cli/schema.py` | 97 条命令；`lists:393–422`；`search:467–499`；`mentions:548/565/592/609` |
| 11 | `.../daniel_cli/commands/mod_lists.py` | `add-items` 计划／执行／回读／写注册 |
| 12 | `.../daniel_cli/commands/mod_mentions.py` | 只读 HANDLERS／`TOP_LIMIT_MIN/MAX` |
| 13 | `.../daniel_cli/commands/mod_search.py` | `enrich` 只读 |
| 14 | `.../daniel_cli/intake/processes.json` | 前置条件与工序键 |
| 15 | `.../contracts/kol-list.json` | 列 63／必填 73／排序 76 |
| 16 | `.../contracts/real-brands-inventory.json` | 品牌四列 |
| 17 | `.../contracts/high-performance-video-list.json` | 视频级列与评级 |
| 18 | `.../lib/index.js` | 20 处注册；deep/open 两段；roster 退役；写链 |
| 19 | `.../lib/worker.py` | `op_insight:234`；`op_kol_profile:252`；提交审计 `_audit_commit:532`／`_audit_open_commit:568`／`_audit_deep_commit:589` |
| 20 | `.../lib/normalize.js` | 均播／互动率／订阅数实现 |
| 21 | `.../lib/research.js` | 计划账本、TTL 300 秒、五档阶段 |
| 22 | `.../tests/golden/baseline.json` | `registeredCount: 20` |
| 23 | `docs/marketing/skills/kol-intelligence.md` | 母本附录 B、L31／674／683／724／3220–3227／4126 |
| 24 | `docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md` | 字段口径、单位陷阱、`avg_views_*` |
| 25 | `.agents/skills/kol-negotiation/SKILL.md` | CPM 公式与判据 |
| 26 | `.agents/skills/kol-execution-sov/SKILL.md` | SOV 口径 |
| 27 | `.agents/skills/nox-cli/SKILL.md` | 9 条读命令、六词口径、C1–C6 |
| 28 | `.agents/skills/nox-weekly/SKILL.md` | 回复率与数字自证 |
| 29 | `docs/marketing/skills/voc-intelligence.md` | VOC 三层与红线 |
| 30 | `.agents/skills/voc-report/SKILL.md` | G1–G9 |
| 31 | `tools/voc-crawler/STATUS.md` | 平台矩阵 |
| 32 | `.kol-tools/daniel_sov.py` | `brand_share:226–232` |
| 33 | `docs/product/daniel-copilot/02-MVP范围与模块清单.md` | 审计引用的产品承诺 |

### C. 不做的事（避免被当漏项）

| # | 不做 | 原因 |
|---|---|---|
| 1 | 不改代码／不改契约／不改母本 | 本阶段只定稿 |
| 2 | 不写第二份登记表 | Q-01 |
| 3 | 不新增工具 | 决策 4 |
| 4 | 不建 20 任务度量集 | Q-22（下一阶段） |
| 5 | 不动飞书 | 硬约束 |
| 6 | 不把 C 类写成「以后会有」 | §6.3 只给替代话术 |

### D. 变更记录

| 版本 | 日期 | 改了什么 |
|---|---|---|
| 1.0-final-candidate | 2026-11-08 | 由草案收口：3 条决策落定；5 概念＋10 指标改 `surfaces` 形态；均播拆两条；新增 `lists add-items`／open 两段式／4 条提及只读命令／`search enrich`；能力分 A/B/C（39/12/35 面）；待确认 23→13 |

---

> **到这里停下，等 Jack 审批。**
> 审批通过后才进入 §3.9 的 8 步落地（改母本 → 切分 → 重建索引 → 门禁 → 加抽取 → 更新基线 → 契约列名）。
