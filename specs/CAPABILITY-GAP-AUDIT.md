# 能力差距审计：Daniel 能力 → Bot 可达性（管线 A · 只读）

> 审计对象：`daniel-bot/packages/0.11.0`（CLI `vendor/data/daniel-cli`、脚本 `vendor/.kol-tools`、DSH 插件 `lib/index.js`）。
> 审计时点：2026-11-08。只读，未改动任何被审文件；本文件是唯一新增。
> **2026-11-08 修订**：工具数口径 19 → **20**（`daniel_open_research_commit` 早已注册，原审计漏计）；同日 deep 提交补上写审计、open 研究收成两段式，第 16／17 条与"写审计只由 CLI 落盘"的旧结论已作废，行内已改。CLI 命令实为 **97**（原写 91 是本轮之前的数）。
> 判定链按票面四层：① 路由 → ② CLI 命令 → ③ MCP 工具 → ④ Bot 可调用（读走 `daniel_run`，写走 `daniel_write_plan/commit`）。

---

## 0. 口径（先说清怎么数，否则后面的数字没法复核）

| 项 | 口径 | 复现方式 |
|---|---|---|
| 被检路由 | 以 `.kol-tools/*.py` 里字面出现的 106 条为底：−7 条前缀别名 −5 条探针候选 −1 条自检反例 −2 条内部辅助 = 91；＋ `daniel_intel.py` 注册表里靠前缀拼出、字面 grep 抓不到的 8 条（`intelligence.refresh/requestCollection`、`memos.create/update`、`actions.observationTimeline/setStatus`、`content.listVideos/getStats`）= 99；＋ 只在 CLI 侧出现的 7 条（A3 补的 `lists.savedChannelIds`／`getShareStatus`／`getAutoPriorityStatus`、`ct.campaigns.getStats`／`resolveChannel`／`deleteCampaign`／`ct.deals.listWithVideoStats`）= **106 条** | `grep -rhoE "['\"](auth\|brands\|lists\|…)(\.[a-zA-Z0-9]+)+['\"]" *.py` ＋ `daniel_intel.py:60-150` |
| CLI 命令 | `schema.py` 里 `c(...)` 的定义数（按 `_MODULES` 逐条数） | `grep -cE '^\s*c\(' schema.py` → **91** |
| MCP 工具 | `lib/index.js` 里 `ctx.tools.register` 的条数 | `grep -c "ctx.tools.register" lib/index.js` → **20**；`tests/golden/baseline.json` `registeredCount: 20` 一致 |
| 断点 | 四层中**任一层**不可达即算断；本审计按"最先缺的那一层"归层，不重复计数 | — |

**关键前提（决定怎么解读"断点"）**：层④ 有两个**通用直通**工具 —— `daniel_run`（任意只读子命令，`lib/index.js:839`）与 `daniel_write_plan/commit`（任意写命令，`lib/index.js:1340/1379`）。因此 **②→③ 不构成断点**：只要 CLI 有这条命令，Bot 就能调到。真正断的是 **①→②（有路由、无命令）**。

---

## 1. 汇总

### 1.1 四个面的事实

| 面 | 数量 | 证据 |
|---|---|---|
| 产品承诺的"已接管路由" | **92 条** | `docs/marketing/skills/_CAPABILITY-INVENTORY-kol-2026-10-15.md:149`（合计 92 条路由／38 条命令／38 个工具） |
| 被检路由（代码里真出现过的业务路由） | **106 条** | §0 口径 |
| CLI 命令 | **91 条**（业务 38 ／ 元能力与本机 53；写 23） | `schema.py`；`mcp/exposure-register.json` 23 条 entries 与"写 23"一致 |
| MCP 工具（DSH 插件，Bot 实际用这个） | **20 个**（业务专用 9、通用直通 2、写链 2、元／语料／追问 6、已退役 1） | `lib/index.js`；`tests/golden/baseline.json` |
| MCP 工具（CLI 派生面 `mcp/server.py`，Cursor/Codex 用这个） | **91 个** | 离线实跑 `daniel schema mcp` → 91 个工具名 |

### 1.2 断点（按层）

| 层 | 断点数 | 清单 |
|---|---|---|
| **② 有路由、无 CLI 命令** | **56 条**（另有 3 条 CLI 缺但层③ 有） | 见 §1.3 |
| **③ 有 CLI、无 MCP 工具** | **0 条** | `daniel_run`（读）＋ `write_plan/commit`（写）覆盖全部 91 条命令；`playbook run` 是 `write_stage=sandbox`（只写本次沙箱），无 `gated` 命令 |
| **④ 有工具、但写链口径不对** | **3 处** | 见 §3 的 B4（开放研究直接执行）／B5（deep 提交不走 CLI 审计）／B6（本机副作用类写命令对 Bot 全开放） |

### 1.3 Bot 可达性（106 条路由的分布）

| 状态 | 条数 | 说明 |
|---|---|---|
| Bot 可直达（有 CLI 命令） | **44** | 由 38 条业务命令覆盖：`brands` 5／`lists` 8／`discovery` 7／`ct` 8／`brandMentions` 4／`actionCenter` 4／`exposureSov` 4／`auth` 2／`dashboard` 1／`sovCategories` 1（含仪器透传） |
| 仅 MCP 可达（无 CLI） | **3** | `discovery.expandTopic`、`discovery.search`（→ `daniel_open_research`）、`discovery.getChannelInsight`（→ `daniel_kol_profile`） |
| **无任何入口** | **59** | 读语义 **21** ／ 写·触发语义 **38** |

⇒ **Bot 实际可调 44／106 = 42%**。票面要求核实的那个实例（`lists.batchAddItems`）**不是孤例，而是 59 条中的 1 条**。

### 1.4 两个必须点破的口径错位

1. **能力清单承诺的 38 个 MCP 工具名，Bot 侧同名只有 1 个。** 清单（`_CAPABILITY-INVENTORY-kol-2026-10-15.md:141-148`）写的是 `daniel_lists_items`／`daniel_mentions_results`／`daniel_sov_overview` 这类名字，它们属于 **CLI 派生 MCP**（`mcp/server.py`，实跑 91 个）；DSH 插件 20 个工具里与清单同名的只有 `daniel_brands_list`。**清单不能用来判断"Bot 能做什么"。**
2. **两套 MCP 的写语义相反。** CLI 派生面：23 条写命令全部注册为"确认单、永不执行"（`mcp/exposure-register.json`：21 条 `确认单不执行` ＋ 2 条 `执行`＝沙箱／本机出件）。DSH 插件：`daniel_write_commit` **带 `--confirm` 真执行**（`lib/index.js:1415`）。同一条 `lists create`，在 Cursor 里跑不了、在 Bot 里能跑 —— 这是设计选择，但目前**没有任何一处文档同时写清这两个面**，`HANDOFF.md:16` 还停在"工具数 14、命令 89"（实际 **20／97**）。

---

## 2. 差距表（按影响排序）

> "断在哪层"用 ②③④ 表示缺的那一层。影响列给的是**承诺的出处**，不是我的判断。

| # | 能力名 | 路由 | CLI 命令 | MCP 工具 | 断在哪层 | 影响（哪个产品承诺依赖它） | 修复成本 |
|---|---|---|---|---|---|---|---|
| 1 | **名单导入（往名单加人）** | `lists.batchAddItems`（`daniel_search.py:1183`） | **无** | **无** | ②③ | `02-MVP:38` M-LS 把 `batchAddItems` 列为"已接管"；`PHASE0-ONTOLOGY-DRAFT.md:322` 记"产品文档 §3.2 承诺的『把清单导入到某个 Brand 的 list 里』当前无命令可执行"（Q-06 仍未关） | 小 |
| 2 | 提及分析四视图（图表／头部频道／视频证据／导出） | `brandMentions.getChartData`／`getTopChannels`／`getVideoEvidence`／`exportMentions`（脚本 `daniel_mentions.py:656/670/686/703` 四条已实现） | **无** | **无** | ② | `02-MVP:40` M-BM 列 15 条"已接管"、能力清单 `:144` 标"已工具化"；VOC／声量报告直接依赖这四张表 | 小 |
| 3 | **富化（补订阅／国家／标签／商务邮箱）** | `discovery.enrichChannels`／`enrichEmails`（`daniel_search.py:939/958`） | **无** | **无** | ②③ | `02-MVP:39` M-DS 7 条"已接管"；名单产线的"邮箱列"、pitch 前置全靠它 | 小 |
| 4 | **品类档案配置写（SOV 的地基）** | `sovCategories.aiSetup`／`confirmAISetup`／`runDiagnosis`／`applyDiagnosis`／`updateBrandConfig`／`updateFilterKeywords`／`addCompetitorWithValidation`／`unlinkBrand`／`generateFilterKeywords`（9 条，`daniel_sov.py:73-82` 已列出入参） | **无** | **无** | ②④ | `02-MVP:42` M-SOV 25 条；没有品类档案就没有 SOV 报告 —— 这是 SOV 全链的前置 | 大 |
| 5 | **SEO SOV 全套** | `seoSov.listWeeks`／`getHeatmap`／`getKeywordDetail`／`getTaskStatus`／`runCollection`（`daniel_sov.py:410-449` 已实现） | **无** | **无** | ② | `02-MVP:42` 明确写"SOV（**SEO** ＋ Exposure ＋ 品类档案）"，CLI 只做了 Exposure 四条 | 中 |
| 6 | 内容情报写族 | `keywords.addCustomKeyword`／`setKeywordStatus`／`reviewKeywordOnce`；`reviews.addTextVersion`／`addDocumentVersion`／`runTextReview`／`runDocumentReview`／`reviews.run`；`topics.startVideoEvidence`；`memos.create`／`update`；`intelligence.refresh`／`requestCollection`；`actions.setStatus`（14 条，`daniel_intel.py:151-167` `WRITE_SUBCMDS` 13 条 ＋ `reviews.run`） | **无** | **无** | ②④ | `02-MVP:45` M-IC 25 条、能力清单 `:145` 标"已工具化"；当前 Bot 只能看不能动 | 中 |
| 7 | 提及触发／守卫族 | `brandMentions.collectVideoSources`／`runVideoDeepReview`／`analyzeHighAttention`／`retryJob`／`cancelJob`／`deleteJob`／`retryVideoReplay`（7 条） | **无** | **无** | ②④ | `02-MVP:57` 验收定义第 4 条"可恢复：长任务可中断续跑，失败可重试"；现在任务失败只能人工上网页 | 中 |
| 8 | 品牌渠道核验／竞品建议 | `brands.verifyChannel`／`brands.suggestCompetitors`（`daniel_brands.py:241/256`） | **无** | **无** | ② | `02-MVP:37` M-BR 7 条（含这 2 条）；能力清单 `:141` 已自认"渠道核验未提供命令" | 小 |
| 9 | 名单写扩展（删人／合并／去重／分享／自动优先级） | `lists.batchRemoveItems`／`getOverlap`／`removeOverlaps`／`mergeLists`／`updateItemTags`／`generateShareLink`／`autoPriority` | **无** | **无** | ② | `02-MVP:38` M-LS 列的 9 条里，CLI 只做了 8 条读＋create/rename/delete；"批量写做查重＋回读断言"这条产品化要求无处落地 | 中 |
| 10 | 情报看板／内容明细 | `dashboard.getTopContent`／`getTopCreators`／`getAvailableBrands`；`content.listVideos`／`getStats`；`actionCenter.memos.list`／`intelligence.status` | **无** | **无** | ② | `02-MVP:41` M-IC "25 条…dashboard.getTopContent／getTopCreators"；`daniel intel` 只有 4 个子命令（`mod_intel.py:63`） | 小 |
| 11 | 提及／审核详情读 | `reviews.getById`；`topics.getSharedCore`；`topics.getVideoEvidence`；`actions.observationTimeline` | **无** | **无** | ② | 同上（`02-MVP:41` "读全通"）—— 实际"列表通、详情不通" | 小 |
| 12 | AI 开放研究 | `discovery.expandTopic`／`discovery.search` | **无** | `daniel_open_research`（`lib/index.js:1112`，经 worker 直连脚本） | ②（③有） | 能力清单 `:143` 只承诺 `search history/job-status/submit` 三条 → 开放研究是"有工具但不在承诺里" | 中 |
| 13 | 频道表现与受众 | `discovery.getChannelInsight` | **无** | `daniel_kol_profile`（`worker.py:234`） | ② | KOL 背调（`kol-screening`）；MCP 有、CLI 无，两条路径各写一遍 | 小 |
| 14 | CT 视频洞察 | `ct.videos.getInsight` | **无** | **无** | ② | `02-MVP:43` M-CT 自认"不承诺"；A3 登记为"路由存在、成功态未实测" | 小 |
| 15 | 任意只读路由直通 | worker `op_query`（`lib/worker.py:201`，已注册进 dispatch `:655`） | — | **无工具暴露**（20 个工具里没有一条 `callWorker(cfg,'query',…)`） | ③ | 排障与"未登记路由"探索；能力在 worker 里、Bot 摸不到 | 小 |
| 16 | 开放研究提交（写） | `discovery.search`＋`discovery.expandTopic` | — | `daniel_open_research`（plan，零发包）→ `daniel_open_research_commit`（提交） | ④ | **2026-11-08 已收成两段式**：与 deep 共用计划账本（5 分钟过期、一次计划只能提交一次），提交后落 `open-research-commit` 审计；原"绕过确认"的结论作废 | — |
| 17 | deep 提交的审计 | `discovery.startSearchJob` | `search submit`（`mod_search.py:432`，有审计） | `daniel_deep_research_commit`（`lib/index.js:1065`，自己一套 plan 账本） | ④ | **2026-11-08 已补**：worker 侧提交后写 `deep-research-commit` 审计（复用 CLI 的 `daniel_cli.audit.record`，落点同一份 `write-audit.jsonl`），字段与 open 逐项一致；回归 `tests/test_deep_audit.py` | — |
| 18 | 发信／邮件（Nox 侧） | **无路由** | 无 | 无 | **C** | `mcp/exposure-register.json` 五类动作自认"对外发信…还没有任何对应命令"；Nox 在 `.agents/skills/nox-cli`（noxinfluencer 独立 CLI），**不在本包** | 大 |
| 19 | 同步飞书 | **无路由** | 无 | 无 | **C** | 同上（"同步飞书"同类）；包内 `feishu/lark` 唯一命中是 `install/wizard.py:6` 的一句源需求引用，**零飞书路由** | 大 |

**前 10 行就是 §2 的"重点"部分**；11–19 是完整登记，避免下次又被当成新发现。

---

## 3. 三类结论

### A 类：能力在、缺入口（可包装，成本小-中）—— **10 组／41 条路由**

| id | 能力 | 路由数 | CLI 缺什么 | 成本 |
|---|---|---|---|---|
| A1 | 名单加人／导入 | 1 | `lists add-items`（写，live） | 小 |
| A2 | 提及四视图 | 4 | `mentions chart/top-channels/evidence/export`（读） | 小 |
| A3 | 富化 | 2 | `search enrich [--emails]`（写／触发） | 小 |
| A4 | SEO SOV 读 | 4 | `sov seo-weeks/heatmap/keyword/seo-task` | 中 |
| A5 | 声量杂项 | 2 | `sov categories --all`（`sovCategories.list`／`getFilterStats`） | 小 |
| A6 | 品牌核验／竞品建议 | 2 | `brands verify-channel/suggest-competitors` | 小 |
| A7 | 情报详情读 | 4 | `intel review-get/topic-core/topic-evidence/action-timeline` | 小 |
| A8 | 看板／内容明细／备忘 | 7 | `intel dashboard-*/content-*`、`intel memos`、`intel status` | 小 |
| A9 | 情报写族 | 14 | `intel keyword-add/keyword-status/review-add/review-run/…`（`WRITE_SUBCMDS` 13 条 ＋ `reviews.run`） | 中 |
| A10 | CT 视频洞察 | 1 | `ct video-insight` | 小 |

> 另有 **3 条"CLI 缺、MCP 有"**（`discovery.expandTopic`／`discovery.search`／`discovery.getChannelInsight`），不计入上面 41 条：Bot 能调，但 CLI 面缺，三面（CLI／MCP／能力清单）不一致。

### B 类：能力在、但 Bot 不该直接调（应走确认卡片／人工）—— **3 组／18 条路由**

| id | 内容 | 路由数 | 为什么不该直调 |
|---|---|---|---|
| B1 | `brandMentions` 触发与守卫（`collectVideoSources`／`runVideoDeepReview`／`analyzeHighAttention`／`cancelJob`／`deleteJob`／`retryJob`／`retryVideoReplay`） | 7 | 触发采集不可撤（`mod_mentions.py:168` 自述"接口虽有 `brandMentions.deleteJob`，但那是**对生产品牌**的删除类写…只登记任务编号"） |
| B2 | `sovCategories` 9 条写（AI 建品类／诊断／改关键词／解绑品牌） | 9 | 一次 `aiSetup`／`confirmAISetup` 会重建整个品类口径，影响该品牌历史 SOV 可比性 |
| B3 | `exposureSov.forceRefresh`、`seoSov.runCollection` | 2 | 强制刷新绕缓存、消耗配额（`daniel_sov.py:166` 要 `confirmation:"FORCE_REFRESH"` 字面量，平台自己都当危险操作） |

### B 类的另外 3 项（不是路由缺口，是写链口径问题）

| id | 问题 | 证据 |
|---|---|---|
| B4 | `daniel_open_research` 直接执行写：无干跑、无用户确认、无 CLI 审计 | `lib/index.js:1112-1145`；与 AGENTS.md §3.7 冲突 |
| B5 | `daniel_deep_research_commit` 用独立 plan 账本，与 `daniel_write_plan/commit` 平行（两套 TTL／摘要校验），写不进 `account audit` | `lib/index.js:1061`；审计只由 `commands/_common.py:134-164` 落盘 |
| B6 | 本机副作用类写命令对 Bot 全开放（`connect apply/uninstall`、`install run/upgrade`、`account login/switch/credentials-set`、`pack out`） | `write_plan` 不设命令白名单，全靠 CLI 退出码 3 判定（`lib/index.js:1352`） |

### C 类：能力本身没有（需后端新增或跨系统）—— 5 条

| id | 内容 | 依据 |
|---|---|---|
| C1 | 邮件发送／回复 | 本包 0 路由、0 工具（grep `smtp/sendmail/outreach/nox` 仅命中语料文本）；Nox 在 `.agents/skills/nox-cli` 的独立 CLI |
| C2 | 同步飞书 | `exposure-register.json` 自认"五类里同步飞书无命令"；包内 `feishu/lark` 唯一命中是 `install/wizard.py:6` 的源需求引用，零路由 |
| C3 | 内容情报删除类写 | `02-MVP:45`＋`A3-未实测路由补齐登记.md:60-64`：系统侧无删除路由 |
| C4 | 真实性分数写入 | `02-MVP:44`：前端自算，`authenticityScore` 不可写 |
| C5 | 官方库检索（`discovery.searchRoster`） | 已退役：`lib/index.js:922` 的 `daniel_roster_search` 零发包、只回"该走哪条通道" |

**计数自洽**：41（A：读 21 ＋ 写 20）＋ 18（B）＝ 59 ＝ §1.3 的"无任何入口 59 条"（读 21／写·触发 38，A／B 互不重叠）。另有 3 条"CLI 缺、MCP 有"单列，不计入 59。

---

## 4. 建议优先级（前 5）

排法：先修"产品已经明写承诺、且 Bot 一调就穿帮"的，再修"能力在但没人调得到"的，最后动写链口径。

### ① `lists.batchAddItems` → 加 `lists add-items` 写命令（成本：小）
- 动作：在 `commands/mod_lists.py` 增 `cmd_add_items`，`write_stage="live"`，入参复用 `daniel_search.py:1183` 已实测的 items 形状（`channelId/channelTitle/subscriberCount/country/tier/cqiScore/contactEmail/engagementRate`）；写后回读 `lists.getItems` 断言条数增加；`schema.py` 注册 `c("add-items", …, write=True, write_stage="live")`。
- 为什么排第一：`02-MVP:38` 已经把它写进"已接管 9 条"，客户按文档点单会直接失败。
- 同一票顺手把 `PHASE0 Q-06` 结掉（否则文档两处自相矛盾）。

### ② 提及四视图 → 加 4 条只读命令（成本：小）
- 动作：`mod_mentions.py` 增 `chart`／`top-channels`／`evidence`／`export`，一律 `read_instrument(ctx, SCRIPT, ["--chart", job, "--json"])` 走既有信封，零新逻辑。
- 收益：能力清单 `:144` 的"15 条已工具化"从口号变成可核对。

### ③ 富化 → 加 `search enrich`（成本：小-中）
- 动作：`--emails` 开关切换 `discovery.enrichChannels`／`enrichEmails`；两者是 mutation（补数据）但语义近只读，建议 `write_stage="live"` ＋ 干跑列出将补的 channelId 数与配额影响。
- 收益：名单产线的"邮箱列"从人工变成可跑；`kol-outreach` 的首封信缺邮箱就发不出去。

### ④ 写链收口：开放研究改两段式 ＋ 两条 research 写落审计（成本：中）
- 动作：`daniel_open_research` 拆成 `daniel_open_research`（出计划）＋ `daniel_open_research_commit(planId)`，复用 `lib/research.js` 现成的 `claimPlan`；worker 的 `research_submit`／`open_submit` 在提交前调用 CLI 记一条审计（或在 `worker.py` 侧写同一份 `audit.record` 结构），让 `daniel account audit` 能看到。
- 理由：唯一**真写却没有确认、也没有审计**的通道，且是"找红人"主入口 —— 风险与使用频率不匹配。

### ⑤ SEO SOV → 要么补 4 条命令，要么改文案（成本：中）
- 若补：`sov seo-weeks/heatmap/keyword` ＋ `seo-run`（`daniel_sov.py:410-449` 已完成取数与分页，只需命令壳）。
- 若不补：把 `02-MVP:42` 与能力清单 `:146` 的"SOV（SEO＋Exposure＋品类档案）"改成"Exposure＋品类档案（SEO 未接线）"，别让"SoV 报告"这个交付件建在拿不到的数上。

> 明确"暂不接"的三项：发信（C1，跨系统）、飞书同步（C2，后置）、CT 视频洞察（A10，无成功态样本，接了也只能报错）。

---

## 5. 待确认（不写进结论的部分）

| 项 | 为什么待确认 | 怎么确认 |
|---|---|---|
| `lists.batchRemoveItems`／`getOverlap`／`removeOverlaps`／`mergeLists`／`updateItemTags`／`generateShareLink`／`autoPriority` 的入参 | 只在 A3 登记"405＝路由存在"，**入参键与返回形状一概未实测**（`A3-未实测路由补齐登记.md:88-96` 自述"没对任何写路由发起写请求"） | 只读 GET 探测只能判"是 mutation"，须逐条读前端 bundle 调用点或找人确认 |
| `ct.deals.create/update`、`ct.videos.create/unlink/refreshAsync` | 同上，且当前系统无视频对象，成功态无法验 | 造一条测试活动后复验 |
| `inbox.getCreatorContactHistory` | 只在 `daniel_route_probe.py:60` 当探针候选（GET 报 405），**是否属产品能力未知** | 未列入被检集（§0 探针），若确认属产品能力则升为 A 类 |
| `discovery.searchRoster` 退役后是否有替代 | 已裁决退役（`lib/index.js:915-921`），但 `04-剥离清单` 未同步 | 文档对齐，不涉代码 |
| `HANDOFF.md` 的"14 工具／89 命令／语料 0.9.204" | 与实测 19／91／0.9.206 不符 | 改文档，不需要发明新事实 |

---

## 6. 证据索引（逐条可核对）

| 结论 | 证据 |
|---|---|
| 91 条命令 | `vendor/data/daniel-cli/daniel_cli/schema.py`（AST 数 `c()` = 91；`REQUIRED_MODULES` 12 ＋ 11 个扩展模块） |
| 20 个工具、20 基线 | `lib/index.js`（20 处 `ctx.tools.register`）；`tests/golden/baseline.json` `registeredCount: 20` |
| 通用直通 | `lib/index.js:839`（`daniel_run`，写命令返回 exitCode 3 引导两段式）、`:1219`（`daniel_batch`，最多 6 条只读）、`:1340`／`:1379`（写链两段） |
| 写链真执行 | `lib/index.js:1415` `runDaniel(cfg, [...rec.argv, '--confirm'])` |
| 写审计只落一份 | CLI 侧 `commands/_common.py:134-164` `_audit()`；worker 侧提交审计 `lib/worker.py::_audit_commit`（同样调 `daniel_cli.audit.record`，落点同一份 `write-audit.jsonl`） |
| `lists` 只有 8 读 3 写、无加人 | `commands/mod_lists.py:348` `HANDLERS`（by-brand/items/saved-channel-ids/share-status/auto-priority-status）、`:356` `WRITE_HANDLERS`（create/rename/delete） |
| 加人只存在于脚本 | `vendor/.kol-tools/daniel_search.py:1175`（`lists.create`）、`:1183`（`lists.batchAddItems`） |
| `search submit` 只覆盖 deep | `commands/mod_search.py:432`（写命令）＋ `_run_submit` 只打 `startSearchJob/executeSearchJob/getSearchJob`；`expandTopic/search` 无任何 CLI 引用 |
| 开放研究走 worker 直连脚本 | `lib/index.js:1112`（工具）→ `callWorker(cfg,'open_submit')` → `lib/worker.py:514`（`op_open_submit`）→ `daniel_search.py:783`（`expandTopic`）／`:835`（`start_job`） |
| intel 13 条写子命令（＋`reviews.run`）无 CLI | `daniel_intel.py:151-167` `WRITE_SUBCMDS`；CLI `mod_intel.py:63` 只有 4 条读 |
| SOV 只做 Exposure 四件 | `commands/mod_sov.py:46` `HANDLERS`（overview/categories/brand-videos）＋ `WRITE_HANDLERS`（run-exposure） |
| 承诺 92 路由／38 命令／38 工具 | `docs/marketing/skills/_CAPABILITY-INVENTORY-kol-2026-10-15.md:141-149` |
| 92 条路由的模块分布 | `docs/product/daniel-copilot/02-MVP范围与模块清单.md:37-46` |
| 两套 MCP 并存 | `connect/hosts.py:64-65`（写入 `mcp/server.py`）、`:184`（"dsh 尚未适配"）；DSH 侧是独立插件包 |
| 写命令在 CLI-MCP 侧永不执行 | `mcp/exposure-register.json`（23 entries：21 确认单 ＋ 2 可执行＝`playbook run` 沙箱／`playbook deliver` 本机出件） |
| 能力清单的 MCP 工具名 ≠ 插件工具名 | 清单 `:141-148` 的 38 个名字 vs `lib/index.js` 的 20 个；同名只有 `daniel_brands_list` |
| `_CAPABILITY-MAP.json` 不是能力清单 | 真源在 `docs/marketing/skills/_CAPABILITY-MAP.json`（能力→章节路由地图，v2.8）；`mcp/corpus/` 下**没有** `_CAPABILITY-MAP.json`；`_ONTOLOGY.json` 只有 4 条登记项（指标／判据／表达），不是能力清单 |
