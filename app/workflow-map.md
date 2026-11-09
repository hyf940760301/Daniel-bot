# Daniel Bot 执行轨迹 · 字段级映射表（workflow-map）

> 本文件由 `daniel-bot/app/scripts/gen-workflow-map.py` 生成，**勿手改**。
> 机器可消费版本：`daniel-bot/app/workflow-map.json`（schema `daniel.workflow-map.v1`）。
> 重跑：`python3 daniel-bot/app/scripts/gen-workflow-map.py`；核对：`… --check`。
> 工作流口径的**唯一来源**：A 包内 `mcp/corpus/kol-intelligence/SKILL.md` §1（7 阶段总览，源 L68–L82）＋ 8 束 `kol-*` 语料；不使用另一条管线的模块名（D-058/D-059，见 §九 9.3）。

## 一、它解决什么

左栏要在用户发一句话后实时显示：Bot 调了哪条命令 → 对应 Daniel 的哪个**模块/页面** → 正在读或写**哪些字段** → 处在**哪一阶段第几步**。本表就是这三层的对照：

- `match`：命令面（CLI 写法；同时给 `mcpTool`，MCP 工具调用可落到同一条）；
- `module` / `page`：业务模块与页面（人读，不暴露内部模块键）；
- `fields`：左栏要显示的字段清单，逐条带 `fieldEvidence`（证据出处）；
- `workflow` / `step`：能力阶段与 0 起的步骤号；`workflowReason` 是逐条的归类依据。

## 二、工作流定义（10 条）

| id | 名称 | 步骤（`step` 为 0 起下标） | 命令数 |
|---|---|---|---|
| `stage0-product` | 产品说明与 Key Feature | 0. 产品事实 → 1. Key Feature 提炼 → 2. 官方说明块 | 0 |
| `discovery` | 发现 | 0. 检索词矩阵（含参数澄清） → 1. 跑检索 → 2. 名单产线 | 6 |
| `screening` | 背调 | 0. 评分卡 → 1. 真实性核验 → 2. shortlist | 2 |
| `outreach` | 外联（KOL Pitch） | 0. 首封 Pitch → 1. 跟进 → 2. 回复处置 | 0 |
| `negotiation` | 谈判 | 0. 问价 → 1. 砍价 → 2. 审核表 | 0 |
| `contract` | 合同 | 0. 条款适配 → 1. 出具合同 → 2. 签署归档 | 0 |
| `execution` | 执行 | 0. 审稿 → 1. 发布 → 2. 数据回收 | 0 |
| `sov` | SOV 与热点 | 0. 固定竞争集 → 1. 份额与情感 → 2. 热点追踪 | 4 |
| `data` | 数据层 | 0. 读取 → 1. 写入（含回读） | 31 |
| `ops` | 平台运维 | 0. 需求路由 → 1. 环境与账号 → 2. 安装与接入 → 3. 自检与出包 | 48 |

**这 10 条怎么来的**：

- 业务阶段链按 D-058：`stage0-product`（阶段 0）→ `discovery`（1）→ `screening`（2）→ `outreach`（3）→ `negotiation`（4）→ `contract`（合同束）→ `execution`（5）→ `sov`（6 与 7 合并：SOV 追踪 ＋ 热点/趋势）。
- `contract` **不在 7 阶段表的 8 行里**：8 束语料中 `kol-contract` 是独立能力束，D-058 把它列为 A 阶段链的一环（谈判之后、执行之前），故单列一条。
- `data` 与 `ops` 是 D-058 指定的两个横向层：`data` ＝ 跨阶段的平台数据能力（品牌／名单／提及／CT 等，同一份数据同时服务多个阶段）；`ops` ＝ 平台运维，全部 `internal: true`（48 条）。

## 三、能力地图 7 阶段 → 本表工作流

| 阶段 | 名称（`SKILL.md` §1 逐字） | 工作流 | 该阶段命令数 |
|---|---|---|---|
| 0 | 产品说明与 Key Feature 提炼（跨阶段基础能力） | `stage0-product` | 0 |
| 1 | 发现 Discovery | `discovery` | 6 |
| 2 | 深度背调 Due Diligence | `screening` | 2 |
| 3 | Pitch 外联 Outreach | `outreach` | 0 |
| 4 | 报价谈判 Negotiation | `negotiation` | 0 |
| 5 | 执行至成功 Execution | `execution` | 0 |
| 6 | SOV 追踪 | `sov` | 4 |
| 7 | 热点/趋势追踪 | `sov`（与 6 合并；热点复用 data 层的提及证据） | 0 |

### 3.1 为什么有 5 条工作流是 0 条命令

**CLI 是数据层，不是作业层**：阶段 0（产品说明）、3（外联）、4（谈判）、5（执行）与 `contract` 的作业载体是 `.kol-tools/` 的仪器与 Skill 章节，不在 91 条命令里。这不是漏映射，是边界——左栏若要把这些阶段也点亮，需要把下列仪器接成第二条轨迹源。

| 工作流 | 0 条的原因 | 现有载体（能力条目 → 仪器） |
|---|---|---|
| `stage0-product` | CLI 没有「产品事实 → 说明块」的命令；产出是文档 | 方法在 `SKILL.md` §2.3；45 条能力条目里没有对应仪器 |
| `outreach` | CLI 不发邮件；首封/跟进/回复是邮件作业 | `edm-reply`（check_email_tone.py）；`edm-correction`（check_email_tone.py）；`edm-shipping-info`（check_email_tone.py）；`edm-first-pitch`；`edm-followup`（check_email_tone.py）；`edm-confirm-ack`（check_email_tone.py、email_quality_metrics.py）；`edm-pitch`（check_email_tone.py） |
| `negotiation` | CLI 不做问价/砍价/审核表；这些是判据与四表作业 | `edm-quote-request`（check_email_tone.py）；`edm-bargain`（check_email_tone.py、check_batch_diversity.py、check_reply_intent.py）；`terms-response`；`four-tables`（review_tables_verify.py、preflight_check.py）；`edm-terms-contract`（check_email_tone.py）；`edm-rate-im`（check_email_tone.py）；`review-table-fill`（check_review_row.py、review-row-spec.json） |
| `contract` | CLI 不出合同；合同是文档作业 | `contract-kol-adapt`（contract_kol.py、build_mrp_base.py、check_contract_form_consistency.py）；`contract-feishu-sync`（contract_kol.py、build_mrp_base.py、check_destructive_calls.py）；`contract-issue`（check_contract_fidelity.py、doc_to_pdf.py、contract_kol.py、check_contract_form_consistency.py） |
| `execution` | CLI 不做审稿/回收；执行期数据由 data 层的 CT 与提及提供 | `review-recovery`；`edm-progress-brief`（check_email_tone.py、email_quality_metrics.py）；`script-review`（check_external_review_form.py） |

### 3.2 两个横向层为什么吸收这些命令

- **`data` 吸收品牌/名单/提及/CT/情报**：这五组是「同一份数据被多个阶段读」的平台能力（例如同一份名单同时服务发现落库、背调取人、外联取联系方式），按 D-058 归数据层，不按「谁先用它」归阶段。
- **`ops` 吸收账号/安装/接入/出包/自检/工序引擎**：它们不产出 KOL 业务数据，只维护运行环境；若塞进业务阶段，左栏会把运维动作显示成业务动作。

### 3.3 45 条能力条目里的「Daniel 直连」条目 → CLI 模块

| 能力条目 | 覆盖的 CLI 模块 | 该模块命令数 |
|---|---|---|
| `daniel-lists` | lists | 8 |
| `daniel-campaign` | ct | 8 |
| `kol-fullchain-search` | search | 3 |
| `screening-caliber` | search | 3 |
| `gate-sweep` | search | 3 |
| `cqi-cutoff` | search | 3 |
| `daniel-brands` | brands | 7 |
| `daniel-brand-mentions` | mentions | 4 |
| `daniel-intel-core` | intel／authenticity | 6 |
| `daniel-sov` | sov | 4 |
| `daniel-takeover-check` | takeover | 2 |

其余 34 条能力条目（邮件、合同、交付物预检、维护卫生…）不对应 CLI 命令；本表不把它们硬塞进 entries——左栏只在 Bot 真的调 Daniel 命令时才有字段可显示。

## 四、覆盖统计

| 项 | 数 | 说明 |
|---|---|---|
| CLI 命令总数 | 91 | `daniel schema --check` 声明的集合（脚本断言） |
| 已映射 | 91 | 每条都有 module/page/action/workflow/fields/workflowReason |
| 其中 `internal` | 48 | 平台/工具链，不面向业务用户 |
| 业务命令 | 43 | 会出现在业务左栏 |
| 未映射 | 0 | 无（两种漂移都会让脚本失败） |
| 带 MCP 工具名 | 91 | `daniel_<模块>_<命令>`，与 `schema.mcp` 同源 |

**动作分布**：compute 19／read 49／write 23。

**未映射命令清单**：无（0 条）。脚本对「schema 有、CLASSIFY 没有」与「CLASSIFY 有、schema 没有」两种漂移都会直接失败，不会静默输出半张表。

### 按模块（命令数）

| 模块 | 命令数 | 其中 internal |
|---|---|---|
| 授权 | 1 | 1 |
| 品牌资产 | 7 | 0 |
| 红人名单 | 8 | 0 |
| 红人检索 | 3 | 0 |
| 品牌提及 | 4 | 0 |
| 内容情报 | 4 | 0 |
| 声量份额 | 4 | 0 |
| 合作追踪 | 8 | 0 |
| 真实性核验 | 2 | 0 |
| 数据通路 | 3 | 3 |
| 接管验收 | 2 | 2 |
| 口径一致性 | 2 | 2 |
| 账号与工作区 | 10 | 10 |
| 检索词清单 | 1 | 0 |
| 业务语料 | 2 | 2 |
| 工序契约 | 6 | 6 |
| 调度 | 4 | 4 |
| 宿主接入 | 5 | 5 |
| 出包 | 2 | 2 |
| 安装向导 | 3 | 3 |
| 需求入口 | 4 | 4 |
| 命令清单 | 4 | 4 |
| 澄清 | 2 | 0 |

## 五、字段证据覆盖

字段**不是手写的**：每条字段都在生成时到四个事实源里查一遍，按 `code`（commands/*.py 的键/参数）→ `route`（60-data-layer.md 返回字段）→ `schema`（schema.py 该命令的返回说明）→ `dict`（字段字典）取第一个命中；四级都没有才标 `inferred`。

> 行号是该键在文件里**首次出现**的位置（证明确实有这个字段名），不保证就是本命令的读写行；要看读写点，按同一个键在该文件里再搜。

| 证据档位 | 字段数 | 占比 |
|---|---|---|
| `code`（commands/*.py 字段名/参数） | 173 | 51.0% |
| `route`（60-data-layer 返回字段） | 11 | 3.2% |
| `schema`（schema.py 返回说明） | 155 | 45.7% |
| `dict`（字段字典源字段） | 0 | 0.0% |
| `inferred`（推断·无直接证据） | 0 | 0.0% |
| **合计** | **339** | 100% |

> `dict` 档 0 命中是**预期**：字段字典集中在频道画像（均播/受众/兴趣），对应到本表就是 `lists.items` 的几项，而它们已被 `route` 档先命中（同一批字段在 60-data-layer 里也有）。字典在本表的实际用途是**核对展示名与源字段**（§11 规范字段表）＋ §6.7 的`brands.list` 实测返回（`targetCountries`／`sampleCost`）；它仍列在 `generated_from` 里。

**口径**：`code`＋`route` 是「接口/命令里真实存在的字段名」，合计 **184/339（54.3%）**；`schema` 与 `dict` 是文件里逐字存在的业务字段描述（仍可追溯，只是不是接口键本身）；`inferred` 为 **0/339（0.0%）**。

### 标 `inferred: true` 的清单

无。全部字段都能在四个事实源里逐字查到。

> **证据边界**：`daniel_cli/commands/*.py` 对 intel／sov／ct 是**薄壳**——真正的字段读写在 `.kol-tools/daniel_*.py` 仪器里，而它不在任务给定的四个事实源内，本表**不把它算作证据**（否则等于偷偷换真源）。下面这 16 条要升到 `code` 档，得先决定是否把仪器源码纳入证据源。

**只看业务命令（43 条，160 个字段）**：`code`＋`route` 强证据 **90/160（56.2%）**，其余 70 个字段来自这些命令自己的返回说明。也就是说：榜单/统计/画像类命令（intel／sov／ct／authenticity）的接口字段名不在 CLI 源码里（它们复用 `.kol-tools/` 仪器），只能以命令返回说明为据——这类条目**建议用真实返回再核一遍**，见下面的弱证据清单。

**证据最弱的一档（全部字段只有 `schema`/`dict` 档，建议人工复核）**：共 28 条（业务 16 条、平台 12 条）。业务那 16 条是要优先复核的：它们的接口键在 `commands/*.py` 与 60-data-layer 里都没有，只有命令返回说明（例外：`clarify` 两条的键其实在 `daniel_cli/clarify.py`，但按本表 code 档口径只认 `commands/*.py`，故仍列在这里）。

| 命令 | 页面 | 范围 | 字段数 |
|---|---|---|---|
| `lists share-status` | 名单分享 | **业务** | 3 |
| `lists auto-priority-status` | 自动优先级 | **业务** | 4 |
| `intel actions` | 待办动作 | **业务** | 5 |
| `intel keywords` | 追踪关键词 | **业务** | 4 |
| `intel topics` | 选题 | **业务** | 4 |
| `sov overview` | 声量总览 | **业务** | 3 |
| `sov brand-videos` | 品牌视频明细 | **业务** | 4 |
| `ct campaign-stats` | 活动统计 | **业务** | 4 |
| `ct deals` | 订单明细 | **业务** | 3 |
| `ct videos` | 共创视频 | **业务** | 2 |
| `ct resolve-channel` | 频道解析 | **业务** | 2 |
| `ct interests` | 频道兴趣画像 | **业务** | 2 |
| `authenticity channel` | 频道真实性评分 | **业务** | 5 |
| `authenticity weights` | 评分权重 | **业务** | 2 |
| `parity selfcheck` | 口径自检 | 平台 | 3 |
| `account audit` | 写操作审计 | 平台 | 5 |
| `playbook selfcheck` | 契约引擎自证 | 平台 | 3 |
| `sched retry` | 失败重试 | 平台 | 3 |
| `sched status` | 任务状态 | 平台 | 3 |
| `connect doctor` | 接入自检 | 平台 | 4 |
| `install run` | 安装 | 平台 | 5 |
| `install upgrade` | 升级 | 平台 | 3 |
| `schema show` | 命令清单 | 平台 | 5 |
| `schema mcp` | MCP 工具清单 | 平台 | 3 |
| `schema dsh-tools` | DSH 工具定义 | 平台 | 3 |
| `schema check` | 清单自证 | 平台 | 2 |
| `clarify plan` | 参数缺口清单 | **业务** | 5 |
| `clarify ask` | 五类选择面追问 | **业务** | 5 |

## 六、映射表（按模块分组）

证据列写作 `code/route/schema/dict` 的字段数；`⚠️N` 表示该条有 N 个推断字段。归类依据逐条见 §七。

### 授权（1 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `auth status` | 登录状态 | read | 平台运维 · 1 环境与账号 | 登录状态、判定理由、会话落点、退出码 | code 4 |

### 品牌资产（7 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `brands list` | 品牌列表 | read | 数据层 · 0 读取 | 品牌名、品类、目标市场、竞品 | code 4 |
| `brands show` | 品牌详情 | read | 数据层 · 0 读取 | 品牌编号、简介、频道、竞品、目标市场 | code 5 |
| `brands competitors` | 竞品清单 | read | 数据层 · 0 读取 | 竞品名、品类关键词 | code 2 |
| `brands create` | 新建品牌 | write | 数据层 · 1 写入（含回读） | 品牌名、简介、品类、行业关键词、目标市场、样品价、竞品 | code 7 |
| `brands update` | 品牌编辑 | write | 数据层 · 1 写入（含回读） | 品牌名、简介、品类、行业关键词、目标市场、样品价、竞品 | code 7 |
| `brands clone` | 品牌克隆 | write | 数据层 · 1 写入（含回读） | 新品牌名、目标工作区、简介、品类、目标市场、样品价、竞品 | code 7 |
| `brands delete` | 品牌删除 | write | 数据层 · 1 写入（含回读） | 品牌名、工作区、删除凭据 | code 3 |

### 红人名单（8 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `lists by-brand` | 名单列表 | read | 数据层 · 0 读取 | 名单编号、名单名、红人数 | code 3 |
| `lists items` | 名单成员 | read | 数据层 · 0 读取 | 频道编号、频道名、订阅数、质量分、互动率、标签 | code 1 / route 5 |
| `lists saved-channel-ids` | 已存频道 | read | 数据层 · 0 读取 | 频道编号、编号条数 | code 2 |
| `lists share-status` | 名单分享 | read | 数据层 · 0 读取 | 是否开启分享、分享码、分享时间 | schema 3 |
| `lists auto-priority-status` | 自动优先级 | read | 数据层 · 0 读取 | 自动优先级状态、进度百分比、完成时间、最近更新时间 | schema 4 |
| `lists create` | 新建名单 | write | 数据层 · 1 写入（含回读） | 名单名、品牌 | code 2 |
| `lists rename` | 名单改名 | write | 数据层 · 1 写入（含回读） | 名单编号、名单名、品牌 | code 3 |
| `lists delete` | 删除名单 | write | 数据层 · 1 写入（含回读） | 名单编号、名单名、红人数、删除凭据 | code 4 |

### 红人检索（3 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `search history` | 检索历史 | read | 发现 · 1 跑检索 | 检索式、检索方式、发起时间 | code 1 / schema 2 |
| `search job-status` | 检索任务进度（五档阶段） | read | 发现 · 1 跑检索 | 任务状态、进度 | code 1 / schema 1 |
| `search submit` | 发起检索（deep／open） | write | 发现 · 1 跑检索 | 检索式、品牌、候选上限 | code 3 |

### 品牌提及（4 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `mentions jobs` | 提及任务列表 | read | 数据层 · 0 读取 | 任务编号、状态、分析时间范围、视频数 | code 2 / schema 2 |
| `mentions status` | 任务进度与汇总 | read | 数据层 · 0 读取 | 进度百分比、当前阶段、已分析数、完成说明、结果汇总 | code 2 / route 2 / schema 1 |
| `mentions results` | 视频级评分结果 | read | 数据层 · 0 读取 | 视频标题、频道、播放量、表现评级、相关性 | route 2 / schema 3 |
| `mentions run` | 发起提及分析 | write | 数据层 · 1 写入（含回读） | 品牌、检索方式、回溯天数、最多视频数 | code 4 |

### 内容情报（4 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `intel actions` | 待办动作 | read | 数据层 · 0 读取 | 动作编号、类型、标题、依据、建议做法 | schema 5 |
| `intel keywords` | 追踪关键词 | read | 数据层 · 0 读取 | 关键词、来源、启用状态、上限与余量 | schema 4 |
| `intel topics` | 选题 | read | 数据层 · 0 读取 | 选题编号、标题、主要关键词、支撑词 | schema 4 |
| `intel reviews` | 内容审核单 | read | 数据层 · 0 读取 | 审核单、阶段、选题标签 | code 1 / route 1 / schema 1 |

### 声量份额（4 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `sov overview` | 声量总览 | read | SOV 与热点 · 1 份额与情感 | 播放量、视频数、份额占比 | schema 3 |
| `sov categories` | 品类档案与竞品 | read | SOV 与热点 · 0 固定竞争集 | 品类档案、登记竞品 | code 1 / route 1 |
| `sov brand-videos` | 品牌视频明细 | read | SOV 与热点 · 1 份额与情感 | 视频标题、频道、播放量、发布时间 | schema 4 |
| `sov run-exposure` | 发起曝光采集 | write | SOV 与热点 · 1 份额与情感 | 品类档案、市场、统计窗口 | code 3 |

### 合作追踪（8 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `ct campaigns` | 合作活动列表 | read | 数据层 · 0 读取 | 活动编号、标题、起止日期、活动码 | code 3 / schema 1 |
| `ct campaign-stats` | 活动统计 | read | 数据层 · 0 读取 | 订单数、达人数、应有视频数、已关联视频数 | schema 4 |
| `ct deals` | 订单明细 | read | 数据层 · 0 读取 | 订单条数、合作单、视频统计 | schema 3 |
| `ct videos` | 共创视频 | read | 数据层 · 0 读取 | 视频条数、逐条明细 | schema 2 |
| `ct resolve-channel` | 频道解析 | read | 数据层 · 0 读取 | 频道编号、是否成功 | schema 2 |
| `ct interests` | 频道兴趣画像 | read | 数据层 · 0 读取 | 兴趣来源、兴趣列表 | schema 2 |
| `ct create-campaign` | 新建活动 | write | 数据层 · 1 写入（含回读） | 活动名、开始日期、结束日期、是否常青 | code 4 |
| `ct delete-campaign` | 删除活动 | write | 数据层 · 1 写入（含回读） | 活动编号、活动名 | code 2 |

### 真实性核验（2 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `authenticity channel` | 频道真实性评分 | compute | 背调 · 1 真实性核验 | 频道名、订阅数、样本视频数、总分、信号判定 | schema 5 |
| `authenticity weights` | 评分权重 | compute | 背调 · 0 评分卡 | 信号名称、权重 | schema 2 |

### 数据通路（3 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `route probe` | 通路探测 | read | 平台运维 · 3 自检与出包 | 是否可用、字段清单、字段数、数据样本 | code 4 |
| `route catalog` | 通路清单 | read | 平台运维 · 3 自检与出包 | 通路名、请求动词、说明、默认入参 | code 4 |
| `route sweep` | 全量通路扫描 | write | 平台运维 · 3 自检与出包 | 可用性、出口文件 | code 1 / schema 1 |

### 接管验收（2 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `takeover check` | 只读验收 | compute | 平台运维 · 3 自检与出包 | 区块、检查项、结论、证据 | code 1 / schema 3 |
| `takeover check-writes` | 含写链验收 | write | 平台运维 · 3 自检与出包 | 检查项、状态、临时对象残留、回读结论 | code 4 |

### 口径一致性（2 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `parity selfcheck` | 口径自检 | compute | 平台运维 · 3 自检与出包 | 检查项、通过情况、差异 | schema 3 |
| `parity compare` | 页面逐字比对 | compute | 平台运维 · 3 自检与出包 | 逐字段比对、页面抓取数据 | code 1 / schema 1 |

### 账号与工作区（10 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `account whoami` | 当前账号 | read | 平台运维 · 1 环境与账号 | 账号邮箱、系统角色、账号状态、当前工作区 | code 4 |
| `account workspaces` | 工作区列表 | read | 平台运维 · 1 环境与账号 | 工作区编号、工作区名称、是否当前、配额 | code 4 |
| `account capabilities` | 能力矩阵 | compute | 平台运维 · 1 环境与账号 | 系统角色、账号状态、模块、读写结论、配额 | code 4 / schema 1 |
| `account audit` | 写操作审计 | read | 平台运维 · 1 环境与账号 | 记录条数、真执行、未执行、已回滚、最近一条 | schema 5 |
| `account credentials` | 凭据来源 | read | 平台运维 · 1 环境与账号 | 凭据来源、掩码邮箱、钥匙串可用性 | code 3 |
| `account credentials-set` | 写入凭据 | write | 平台运维 · 1 环境与账号 | 凭据来源、掩码邮箱、明文文件是否写入、服务名 | code 4 |
| `account paths` | 数据落点 | read | 平台运维 · 1 环境与账号 | 会话、缓存、产出、日志、账号分区 | code 1 / schema 4 |
| `account list` | 本机账号 | read | 平台运维 · 1 环境与账号 | 当前账号、分区落点、已存账号、钥匙串 | code 3 / schema 1 |
| `account switch` | 切换账号 | write | 平台运维 · 1 环境与账号 | 切换前后账号、生效落点、回读对账 | code 1 / schema 2 |
| `account login` | 登录 | write | 平台运维 · 1 环境与账号 | 回读到的账号、系统角色、会话落点、回读校验 | code 2 / schema 2 |

### 检索词清单（1 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `keywords check` | 检索词清单校验 | compute | 发现 · 0 检索词矩阵（含参数澄清） | 词表规模、违规项、判据结论、检索词清单 | code 2 / schema 2 |

### 业务语料（2 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `skills list` | 能力域清单 | read | 平台运维 · 1 环境与账号 | 语料版本、能力域、前置条件、整束sha256、切片数 | code 4 / schema 1 |
| `skills read` | 语料正文 | read | 平台运维 · 1 环境与账号 | 模式、切片清单、正文、检索命中 | code 4 |

### 工序契约（6 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `playbook list` | 契约清单 | read | 平台运维 · 3 自检与出包 | 契约编号、名称、是否示例、是否含写步骤 | code 1 / schema 3 |
| `playbook show` | 契约详情 | read | 平台运维 · 3 自检与出包 | 契约全文、落点路径、校验结论 | code 3 |
| `playbook validate` | 契约校验 | compute | 平台运维 · 3 自检与出包 | 检查结论、问题明细 | code 1 / schema 1 |
| `playbook run` | 契约执行 | write | 平台运维 · 3 自检与出包 | 模式、步骤明细、门禁、自检、交付件落点 | code 2 / schema 3 |
| `playbook deliver` | 出件 | compute | 平台运维 · 3 自检与出包 | 交付物落点、行数、sha256、出件自检 | code 3 / schema 1 |
| `playbook selfcheck` | 契约引擎自证 | compute | 平台运维 · 3 自检与出包 | 期望结果、实际结果、不变量 | schema 3 |

### 调度（4 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `sched run` | 任务续跑 | compute | 平台运维 · 3 自检与出包 | 任务状态、进度、逐步明细、结果指纹 | code 1 / schema 3 |
| `sched retry` | 失败重试 | compute | 平台运维 · 3 自检与出包 | 本次跳过、结果指纹、步骤条数 | schema 3 |
| `sched status` | 任务状态 | read | 平台运维 · 3 自检与出包 | 任务列表、状态计数、逐步明细 | schema 3 |
| `sched queue` | 统一队列 | read | 平台运维 · 3 自检与出包 | 并发上限、上限来源、队列条目、受管清单 | code 3 / schema 1 |

### 宿主接入（5 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `connect list` | 宿主状态 | read | 平台运维 · 2 安装与接入 | 现算路径、宿主、配置文件、本产品条目数 | code 4 |
| `connect print` | 配置片段 | read | 平台运维 · 2 安装与接入 | 宿主、配置片段、片段sha256 | code 3 |
| `connect apply` | 接入宿主 | write | 平台运维 · 2 安装与接入 | diff 明细、快照落点、回读对账 | code 1 / schema 2 |
| `connect uninstall` | 移除接入 | write | 平台运维 · 2 安装与接入 | 将删片段、diff 明细、快照落点 | code 2 / schema 1 |
| `connect doctor` | 接入自检 | read | 平台运维 · 2 安装与接入 | 逐项结论、证据、修法、总结论 | schema 4 |

### 出包（2 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `pack out` | 出包 | write | 平台运维 · 3 自检与出包 | 计数、规则表、包根、出包清单、回读对账 | code 3 / schema 2 |
| `pack check` | 包自检 | read | 平台运维 · 3 自检与出包 | 五条断言、判据、通过与否、证据 | code 1 / schema 3 |

### 安装向导（3 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `install run` | 安装 | write | 平台运维 · 2 安装与接入 | 入口与 PATH、能力束、宿主接入、登录、回读对账 | schema 5 |
| `install check` | 安装自检 | read | 平台运维 · 2 安装与接入 | 四项判据、证据、总结论、修法 | code 1 / schema 3 |
| `install upgrade` | 升级 | write | 平台运维 · 2 安装与接入 | 改指条目、自检结论、快照落点 | schema 3 |

### 需求入口（4 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `intake route` | 需求路由 | compute | 平台运维 · 0 需求路由 | 候选工序、前置条件、缺件清单、可执行、置信度 | code 4 / schema 1 |
| `intake draft` | 契约草稿 | compute | 平台运维 · 0 需求路由 | 草稿落点、校验结论、取数步骤数、待确认清单 | code 3 / schema 1 |
| `intake parity` | 模式对等 | compute | 平台运维 · 0 需求路由 | 四组断言、键比对、未落地项 | code 1 / schema 2 |
| `intake catalog` | 工序目录 | compute | 平台运维 · 0 需求路由 | 能力域、工序、前置条件、依据 | code 4 |

### 命令清单（4 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `schema show` | 命令清单 | read | 平台运维 · 1 环境与账号 | 模块、命令、参数、是否写操作、退出码 | schema 5 |
| `schema mcp` | MCP 工具清单 | read | 平台运维 · 1 环境与账号 | 工具名、描述、入参结构 | schema 3 |
| `schema dsh-tools` | DSH 工具定义 | read | 平台运维 · 1 环境与账号 | 工具名、描述、参数 | schema 3 |
| `schema check` | 清单自证 | compute | 平台运维 · 1 环境与账号 | 差异清单、结论 | schema 2 |

### 澄清（2 条）

| 命令 | 页面 | 动作 | 阶段 · 步 | 字段 | 证据 |
|---|---|---|---|---|---|
| `clarify plan` | 参数缺口清单 | compute | 发现 · 0 检索词矩阵（含参数澄清） | 缺项、为什么问、默认值、优先补、下一步 | schema 5 |
| `clarify ask` | 五类选择面追问 | compute | 发现 · 0 检索词矩阵（含参数澄清） | 选择面、模式、缺口、追问、未确认项 | schema 5 |

## 七、归类依据（91 条逐条）

按工作流分组；每条给「命令 → 阶段 · 步 → 为什么」。

### 发现（`discovery`，6 条）

| 命令 | 阶段 · 步 | 归类依据 |
|---|---|---|
| `search history` | 发现 · 1 跑检索 | 检索历史用于复用词表与复盘，属阶段 1 的检索记录 |
| `search job-status` | 发现 · 1 跑检索 | 发现阶段的检索执行与记录；检索产出候选长名单 longlist，是阶段 1 的产线 |
| `search submit` | 发现 · 1 跑检索 | 发现阶段的检索执行与记录；检索产出候选长名单 longlist，是阶段 1 的产线 |
| `keywords check` | 发现 · 0 检索词矩阵（含参数澄清） | 检索词清单的格式/词量/重复/计数校验，是阶段 1 的词表门禁 |
| `clarify plan` | 发现 · 0 检索词矩阵（含参数澄清） | 找红人的参数缺口清单（不取数），属阶段 1 的入口澄清 |
| `clarify ask` | 发现 · 0 检索词矩阵（含参数澄清） | 找红人的五类选择面与动态追问（不取数），属阶段 1 的入口澄清 |

### 背调（`screening`，2 条）

| 命令 | 阶段 · 步 | 归类依据 |
|---|---|---|
| `authenticity channel` | 背调 · 1 真实性核验 | 按前端口径当场复算真实性评分（该页不落库） |
| `authenticity weights` | 背调 · 0 评分卡 | 背调评分口径；真实性与造假检测是阶段 2 的判据 |

### SOV 与热点（`sov`，4 条）

| 命令 | 阶段 · 步 | 归类依据 |
|---|---|---|
| `sov overview` | SOV 与热点 · 1 份额与情感 | SOV 份额/热点的取数与明细；SOV 是阶段 6（份额+情感）与阶段 7（热点）的载体 |
| `sov categories` | SOV 与热点 · 0 固定竞争集 | SOV 的固定竞争集：品类档案里的登记竞品以品牌自配置为准 |
| `sov brand-videos` | SOV 与热点 · 1 份额与情感 | SOV 份额/热点的取数与明细；SOV 是阶段 6（份额+情感）与阶段 7（热点）的载体 |
| `sov run-exposure` | SOV 与热点 · 1 份额与情感 | 发起曝光采集（SOV 的取数触发；写链带确认与回读） |

### 数据层（`data`，31 条）

| 命令 | 阶段 · 步 | 归类依据 |
|---|---|---|
| `brands list` | 数据层 · 0 读取 | 跨阶段平台数据的读取；品牌档案是检索口径、背调、产品说明共用的事实源（D-058：平台能力归 data） |
| `brands show` | 数据层 · 0 读取 | 品牌档案详情：产品说明与各阶段共用的事实源（品类/竞品/目标市场/简介） |
| `brands competitors` | 数据层 · 0 读取 | 跨阶段平台数据的读取；品牌档案是检索口径、背调、产品说明共用的事实源（D-058：平台能力归 data） |
| `brands create` | 数据层 · 1 写入（含回读） | 跨阶段平台数据的写入（确认＋回读）；品牌档案是检索口径、背调、产品说明共用的事实源（D-058：平台能力归 data） |
| `brands update` | 数据层 · 1 写入（含回读） | 跨阶段平台数据的写入（确认＋回读）；品牌档案是检索口径、背调、产品说明共用的事实源（D-058：平台能力归 data） |
| `brands clone` | 数据层 · 1 写入（含回读） | 跨阶段平台数据的写入（确认＋回读）；品牌档案是检索口径、背调、产品说明共用的事实源（D-058：平台能力归 data） |
| `brands delete` | 数据层 · 1 写入（含回读） | 跨阶段平台数据的写入（确认＋回读）；品牌档案是检索口径、背调、产品说明共用的事实源（D-058：平台能力归 data） |
| `lists by-brand` | 数据层 · 0 读取 | 跨阶段平台数据的读取；名单是跨阶段载体：发现落库、背调取人、外联取联系方式（D-058：平台能力归 data） |
| `lists items` | 数据层 · 0 读取 | 名单成员读取（含频道、订阅数、质量分、互动率、标签），背调与外联取人都用它 |
| `lists saved-channel-ids` | 数据层 · 0 读取 | 跨阶段平台数据的读取；名单是跨阶段载体：发现落库、背调取人、外联取联系方式（D-058：平台能力归 data） |
| `lists share-status` | 数据层 · 0 读取 | 跨阶段平台数据的读取；名单是跨阶段载体：发现落库、背调取人、外联取联系方式（D-058：平台能力归 data） |
| `lists auto-priority-status` | 数据层 · 0 读取 | 跨阶段平台数据的读取；名单是跨阶段载体：发现落库、背调取人、外联取联系方式（D-058：平台能力归 data） |
| `lists create` | 数据层 · 1 写入（含回读） | 跨阶段平台数据的写入（确认＋回读）；名单是跨阶段载体：发现落库、背调取人、外联取联系方式（D-058：平台能力归 data） |
| `lists rename` | 数据层 · 1 写入（含回读） | 跨阶段平台数据的写入（确认＋回读）；名单是跨阶段载体：发现落库、背调取人、外联取联系方式（D-058：平台能力归 data） |
| `lists delete` | 数据层 · 1 写入（含回读） | 跨阶段平台数据的写入（确认＋回读）；名单是跨阶段载体：发现落库、背调取人、外联取联系方式（D-058：平台能力归 data） |
| `mentions jobs` | 数据层 · 0 读取 | 跨阶段平台数据的读取；品牌提及是平台级证据能力，供 SOV/热点与背调复用（D-058：平台能力归 data） |
| `mentions status` | 数据层 · 0 读取 | 跨阶段平台数据的读取；品牌提及是平台级证据能力，供 SOV/热点与背调复用（D-058：平台能力归 data） |
| `mentions results` | 数据层 · 0 读取 | 跨阶段平台数据的读取；品牌提及是平台级证据能力，供 SOV/热点与背调复用（D-058：平台能力归 data） |
| `mentions run` | 数据层 · 1 写入（含回读） | 发起品牌提及分析（触发采集；写链带确认与回读），产出归数据层 |
| `intel actions` | 数据层 · 0 读取 | 跨阶段平台数据的读取；Action Center 是平台内容情报（动作/选题/审核单），跨阶段复用（D-058：平台能力归 data） |
| `intel keywords` | 数据层 · 0 读取 | 跨阶段平台数据的读取；Action Center 是平台内容情报（动作/选题/审核单），跨阶段复用（D-058：平台能力归 data） |
| `intel topics` | 数据层 · 0 读取 | 跨阶段平台数据的读取；Action Center 是平台内容情报（动作/选题/审核单），跨阶段复用（D-058：平台能力归 data） |
| `intel reviews` | 数据层 · 0 读取 | 跨阶段平台数据的读取；Action Center 是平台内容情报（动作/选题/审核单），跨阶段复用（D-058：平台能力归 data） |
| `ct campaigns` | 数据层 · 0 读取 | 跨阶段平台数据的读取；Creator Tracker 是平台级合作追踪（订单/视频/统计），跨阶段复用（D-058：平台能力归 data） |
| `ct campaign-stats` | 数据层 · 0 读取 | 跨阶段平台数据的读取；Creator Tracker 是平台级合作追踪（订单/视频/统计），跨阶段复用（D-058：平台能力归 data） |
| `ct deals` | 数据层 · 0 读取 | 跨阶段平台数据的读取；Creator Tracker 是平台级合作追踪（订单/视频/统计），跨阶段复用（D-058：平台能力归 data） |
| `ct videos` | 数据层 · 0 读取 | 跨阶段平台数据的读取；Creator Tracker 是平台级合作追踪（订单/视频/统计），跨阶段复用（D-058：平台能力归 data） |
| `ct resolve-channel` | 数据层 · 0 读取 | 频道实体解析：把 @handle／链接／UC 编号解析成频道编号 |
| `ct interests` | 数据层 · 0 读取 | 跨阶段平台数据的读取；Creator Tracker 是平台级合作追踪（订单/视频/统计），跨阶段复用（D-058：平台能力归 data） |
| `ct create-campaign` | 数据层 · 1 写入（含回读） | 跨阶段平台数据的写入（确认＋回读）；Creator Tracker 是平台级合作追踪（订单/视频/统计），跨阶段复用（D-058：平台能力归 data） |
| `ct delete-campaign` | 数据层 · 1 写入（含回读） | 跨阶段平台数据的写入（确认＋回读）；Creator Tracker 是平台级合作追踪（订单/视频/统计），跨阶段复用（D-058：平台能力归 data） |

### 平台运维（`ops`，48 条）

| 命令 | 阶段 · 步 | 归类依据 |
|---|---|---|
| `auth status` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；登录态是全部业务命令的前置 |
| `route probe` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；通路体检是平台自检，不面向业务阶段 |
| `route catalog` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；通路体检是平台自检，不面向业务阶段 |
| `route sweep` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；通路体检是平台自检，不面向业务阶段 |
| `takeover check` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；接管验收是平台验收，不面向业务阶段 |
| `takeover check-writes` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；接管验收是平台验收，不面向业务阶段 |
| `parity selfcheck` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；口径一致性自检是平台验收 |
| `parity compare` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；口径一致性自检是平台验收 |
| `account whoami` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；账号/工作区/凭据/审计是平台环境 |
| `account workspaces` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；账号/工作区/凭据/审计是平台环境 |
| `account capabilities` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；账号/工作区/凭据/审计是平台环境 |
| `account audit` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；账号/工作区/凭据/审计是平台环境 |
| `account credentials` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；账号/工作区/凭据/审计是平台环境 |
| `account credentials-set` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；账号/工作区/凭据/审计是平台环境 |
| `account paths` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；账号/工作区/凭据/审计是平台环境 |
| `account list` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；账号/工作区/凭据/审计是平台环境 |
| `account switch` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；账号/工作区/凭据/审计是平台环境 |
| `account login` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；账号/工作区/凭据/审计是平台环境 |
| `skills list` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；随包语料是各阶段判据的来源，本身是平台资产 |
| `skills read` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；随包语料是各阶段判据的来源，本身是平台资产 |
| `playbook list` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；工序契约引擎是平台执行器 |
| `playbook show` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；工序契约引擎是平台执行器 |
| `playbook validate` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；工序契约引擎是平台执行器 |
| `playbook run` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；工序契约引擎是平台执行器 |
| `playbook deliver` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；工序契约引擎是平台执行器 |
| `playbook selfcheck` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；工序契约引擎是平台执行器 |
| `sched run` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；调度是平台执行器 |
| `sched retry` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；调度是平台执行器 |
| `sched status` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；调度是平台执行器 |
| `sched queue` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；调度是平台执行器 |
| `connect list` | 平台运维 · 2 安装与接入 | 平台运维 · 安装与接入；宿主接入属于安装动作 |
| `connect print` | 平台运维 · 2 安装与接入 | 平台运维 · 安装与接入；宿主接入属于安装动作 |
| `connect apply` | 平台运维 · 2 安装与接入 | 平台运维 · 安装与接入；宿主接入属于安装动作 |
| `connect uninstall` | 平台运维 · 2 安装与接入 | 平台运维 · 安装与接入；宿主接入属于安装动作 |
| `connect doctor` | 平台运维 · 2 安装与接入 | 平台运维 · 安装与接入；宿主接入属于安装动作 |
| `pack out` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；出包属于分发动作 |
| `pack check` | 平台运维 · 3 自检与出包 | 平台运维 · 自检与出包；出包属于分发动作 |
| `install run` | 平台运维 · 2 安装与接入 | 平台运维 · 安装与接入；安装向导属于安装动作 |
| `install check` | 平台运维 · 2 安装与接入 | 平台运维 · 安装与接入；安装向导属于安装动作 |
| `install upgrade` | 平台运维 · 2 安装与接入 | 平台运维 · 安装与接入；安装向导属于安装动作 |
| `intake route` | 平台运维 · 0 需求路由 | 平台运维 · 需求路由；需求路由是平台入口 |
| `intake draft` | 平台运维 · 0 需求路由 | 平台运维 · 需求路由；需求路由是平台入口 |
| `intake parity` | 平台运维 · 0 需求路由 | 平台运维 · 需求路由；需求路由是平台入口 |
| `intake catalog` | 平台运维 · 0 需求路由 | 平台运维 · 需求路由；需求路由是平台入口 |
| `schema show` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；命令清单是平台元数据 |
| `schema mcp` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；命令清单是平台元数据 |
| `schema dsh-tools` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；命令清单是平台元数据 |
| `schema check` | 平台运维 · 1 环境与账号 | 平台运维 · 环境与账号；命令清单是平台元数据 |

## 八、助手自写阶段的依据

这 5 个阶段**没有随包仪器**，作业由助手按能力语料自己完成（§3.1 的「0 条命令」）。左栏对它们不显示工具调用，只显示一句「本阶段由助手完成」，再加下面这张表——让用户看到**助手是怎么判断的**，而不是依据出自哪份文件。

| 阶段 | 这一条讲什么 | 我为什么这么写 | 产出物 |
|---|---|---|---|
| 产品说明与 Key Feature | 产品说明只写有出处的参数 | 我写的每个参数和功能名，都能在品牌书或官网里翻到原话，翻不到的就留白标待确认。因为这个说明会被对方拿去比对官网——编一个数字，整封邮件立刻被判定成群发模板，后面再解释也拉不回来。宁可少写一句，也不写一句没人背书的话。 | 产品说明块（英文） |
| 产品说明与 Key Feature | 卖点为什么按七个维度核 | 品类定位、差异化、主要功能、日常功能、硬件、生态、背书，我逐项打勾，缺哪项就明说缺哪项。因为漏掉的卖点不会自己长回来：KOL 照着这份说明写脚本，没写进去的就不会出现在视频里，等上线再补只能重拍。多核一遍的成本，远低于补拍一次。 | 完整性核对表 ＋ 缺口清单 |
| 外联（KOL Pitch） | 产品段怎么写 | 我把产品参数和使用场景放在最前面，因为对方判断要不要继续聊，看的是「你到底用没用过这东西」。形容词堆得再多，也不如一句具体参数；写得太像模板，对方连回都不会回。所以这一段每句话，我都要能在品牌物料里找到出处。 | 首封邮件正文（英文） |
| 外联（KOL Pitch） | 首封要不要带条款 | 首封我只讲产品、请他报价，交付、授权、付款这些条款留到第二封。因为第一次接触就甩一整套条款，对方会当成群发的合同模板直接不回；先把产品聊明白，条款反而更好谈。 | 首封邮件（英文）＋ 条款邮件（英文） |
| 谈判 | 报价贵不贵怎么判 | 我不看粉丝量，先把这个号的报价按它最近的实际平均播放折成千次播放成本，再判合理、偏高还是过高。因为粉丝可以买、播放买不了：二十万粉但条均五千播放的号，报出来的单价会高得离谱，只看总价根本比不出问题。 | 对内审核表（价格判断三选一） |
| 谈判 | 目标价为什么不一刀切 | 数据扎实又明显报高价的号，我把目标价往上放；常规号就按参考区间往下谈。因为同一套折扣砍所有号，遇到真强的号会直接谈崩；对方一旦觉得你不识货，后面再想拉回来就很难。 | 砍价邮件（英文）＋ 目标价 |
| 合同 | 合同为什么只换字不动版 | 我在原母版上换掉条款文字，页边距、字号、行距、签署区一个都不动。因为这份文件的版式就是客户和法务认它的方式：我试过把条款一字不差地重排一遍，还是被退回——对方看到的已经不是同一份文件了。 | 合同签署版（PDF）＋ 可复制版 |
| 合同 | 条款改动为什么压到最少 | 我先列出必须替换的段落，只改这几处，其余照抄母版。因为改动越多，对方越会怀疑「这合同是不是有问题」，然后重新拉一轮谈判，签署周期会拖长一倍。 | 条款替换清单 |
| 执行 | 审稿到底卡多严 | 我只卡三件事：方向讲得对不对、事实有没有错、卖点有没有讲到位，不要求他逐字照品牌方的说明念。因为真人拍视频不可能一字不差，卡太严只会拖到错过发布窗口；但价格、规格这类事实错误必须当场改，那是品牌方要背书的部分。 | 逐句审稿意见 |
| 执行 | 回收为什么用同一套字段 | 发布时间、链接、播放点赞评论、转化信号、授权和付款状态，我按同一套字段记。因为字段各记各的，后面复盘和声量就对不上账，既回答不了这波投放值不值，也没法跟下一批比。 | 回收清单 |

**口径**：写成第一人称的判断过程——我怎么看这件事、为什么这样更好、不这样会怎样。**文件名、章节号、内部代号一概不出现**：用户不需要知道依据出自哪份文件，只需要知道这个人为什么这么写。

如果左栏要实现「本阶段由助手完成」这一态，消费 `workflows[].agentRationale` 即可：`title` 是这条的小标题，`thinking` 是展示正文，`output` 是产出物。`trace`（文件:行号）只给 QA 回溯，**不进左栏**。

> 生成器断言：5 个阶段每个至少 1 条依据（或显式标 `missing`）、最多 3 条；`title`／`thinking`／`output` 命中内部标识正则（`SKILL`、`§`、`CLS-`、`TICKET-`、`*.md` 等）或空话词表（「按照标准」「依据规范」「确保质量」等）即失败；`thinking` 少于 40 字即失败；`trace` 必须落在随包语料里、行号存在且该行非空，否则失败。

## 九、不确定项（需要知道的判断）

### 9.1 字段级

- 无字段级推断：全部字段都能在四个事实源里逐字查到。
- 但「能查到」不等于「是接口键」：有 28 条命令的字段只有 `schema` 档证据（见 §五的弱证据清单），其中 16 条是业务命令。这批字段在接入真实返回时要再核一遍键名，尤其是 intel／sov／ct／authenticity 四组。

### 9.2 映射级（不是字段问题，而是编辑判断）

- **`lists.*` 归 `data` 而不归 `discovery`**：能力地图阶段 1 的产出含「名单产线」，但同一份名单同时服务发现落库、背调取人、外联取联系方式；按 D-058 的「跨阶段平台能力」口径归 `data`，不按「谁先用」归阶段。
- **`ct.*` 归 `data` 而不归 `execution`**：CT 的订单/视频/统计确实是执行期回收的数据，但它同时被 SOV 与复盘复用；D-058 明确把 CT 列入数据层。
- **`intel.*` 归 `data`**：Action Center（动作/关键词/选题/审核单）跨阶段复用，无法唯一归到某一阶段。
- **`sov.categories` 放 0「固定竞争集」**（品类档案与登记竞品是 SOV 的口径起点），其余 `sov.*` 放 1「份额与情感」。
- **`authenticity.weights` 放 0「评分卡」**（权重口径），`authenticity.channel` 放 1「真实性核验」。
- **`discovery` 的「名单产线」与 `screening` 的「shortlist」两步 0 条**：名单读写统一归`data`；shortlist 的落盘是文档产出，不是命令。
- **`authenticity.channel` 的动作标 `compute`**：它读频道数据后用前端口径**当场复算**（60-data-layer §15.5 实测：该页不落库、分数前端自算），所以不是纯 read。
- **`playbook.run` 是 `write` 但只写沙箱**：schema 的 `writeStage=sandbox`（写动作只落在本次运行的沙箱目录），条目里带 `writeStage` 就是给左栏区分「真写」与「沙箱演练」用的；其余 22 条写命令都是 `live`。

### 9.3 禁用词说明（D-058/D-059）

本表**禁用**另一条管线（B 管线）的模块名：建联 / 舆情 / VOC。A 的能力只按包内能力地图命名；这些词出现在本表即视为污染（隔离契约 D-058/D-059）。生成器里已加断言：`workflow-map.json` 出现任一禁用词即拒绝写盘。

## 十、最容易错的两处（写映射时踩过的坑）

### 坑 1：`returns` 文本 ≠ 实际返回字段（少写字段）

`daniel brands list` 的 `schema.py` 返回说明只写「品牌编号、品牌名、所属工作区编号与名称」，但 60-data-layer §15.3.2 的 `brands.list` 实际返回含 `category`／`competitors[]`，`_DANIEL-FIELD-DICTIONARY.md` §6.7 的实测返回还含 `sampleCost`／`targetCountries`。**只按 `returns` 建表，左栏会漏掉「品类/目标市场/竞品/样品价」四项**——这正是本表把 `route` 与 `code` 排在 `schema` 之前的原因。

反向的坑同样致命：`tier` 在写库（`lists.batchAddItems.tier`）里是**数字 1–4**，在界面上是**档名**（Mega/Macro/Mid/Micro，且展示分档的分界与写库分界不是同一套，见 60-data-layer §15.3.4）。同名字段两套取值域，左栏若直接显示数字会与用户看到的档名对不上。

### 坑 2：同一个「名单编号」在不同命令里键名不同

`lists.rename` 用 `listId`，而 `lists.delete` **必须用 `id`**（60-data-layer §15.5 硬限 #2：传 `listId` → 400）；`lists.create` 的入参是 `brandId`＋`name`。同一个业务概念「名单编号」，三条命令对应两个键名——若按「字段名统一」去渲染或回填，删除会静默 400。同类还有 `ct.resolve-channel` 的入参键是 `channelInput`（不是 `input`，语料里写错过，见 `mod_ct.py` 的 docstring）。

### 附带一条口径提醒

`mentions.results` 的默认口径是 `confirmed_likely`（只回与本品相关的提及），`all` 才是全量；两者字段一样但**条数不同**（实测 96 vs 114，60-data-layer §15.5.8 第 4 条）。左栏若要显示「读取 N 条」，必须带上口径，否则用户会以为数据丢了。

## 十一、生成方法（哪一步从哪个文件取）

| 步骤 | 取什么 | 从哪取 |
|---|---|---|
| 1 | 91 条命令、模块、摘要、是否写操作、参数、返回说明 | `daniel_cli/schema.py`（`SCHEMA.modules[].commands[]`；脚本 import 后遍历，不手抄） |
| 2 | MCP 工具名 | `daniel_cli/exports.py::mcp_payload()` 的 `annotations.cli` （与 `schema.py` 同一真源，逐条核对） |
| 3 | 模块/页面的业务命名 | 票面示例（`品牌资产 · 品牌列表`）＋ `schema.py` 的模块 `title` ＋ Daniel 页面语义 |
| 4 | 7 阶段名称与顺序 | A 包内 `mcp/corpus/kol-intelligence/SKILL.md` §1（源 L68–L82）＋ 其逐字切片 `references/02-capability-map.md`（两处必须一致，脚本断言） |
| 5 | 工作流归类（91 条） | `CLASSIFY` 表（生成器内唯一真源）；逐条依据写在 `workflowReason`，按 `MODULE_REASON` ＋ `REASON_OVERRIDE` 生成 |
| 6 | 能力层覆盖核对 | `_CAPABILITY-MAP.json`（断言 45 条）里以 Daniel 仪器为载体的条目 → CLI 模块（§3.3）；指到的模块若一条命令都没有即失败 |
| 7 | 字段候选键 | `daniel_cli/commands/*.py`（payload/emit 键）＋ `60-data-layer.md`（路由返回字段）＋ `_DANIEL-FIELD-DICTIONARY.md`（规范字段名的源字段列） |
| 8 | 字段取证（逐字段） | 生成时按 `code → route → schema → dict` 查索引，命中即写 `fieldEvidence`（文件:行号）；四级不中才 `inferred` |
| 9 | 覆盖与隔离自证 | 断言「schema 命令集 ≡ CLASSIFY 命令集」且条数＝91；断言 JSON 无禁用词；跑 `node scripts/check-isolation.mjs` 须 6/6 |

**没有修改 `daniel-bot/packages/0.11.0/` 下的任何文件**：脚本只读该目录，产出全部落在 `daniel-bot/app/`。

