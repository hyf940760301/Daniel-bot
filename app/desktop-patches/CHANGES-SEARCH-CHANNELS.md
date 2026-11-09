# CHANGES · 红人检索改走两条任务式通道（官方库通道退役）

> 时间：2026-11-03（Asia/Shanghai）· 插件版本：`daniel-dsh-plugin@0.11.0`（**内容变、版本号不变**）
> 结论：**官方库通道（`discovery.searchRoster`）退役**；红人检索只留两条任务式通道（deep／open），并补上 4 个缺失工具。
> 纪律：本文件只讲"改成了什么、怎么验的、hash 怎么变"，不重述论证过程。

---

## 1. 通道对照（一句话：有品牌 → deep；无品牌／自由描述 → open）

| 通道 | 上游路由 | 何时用 | 工具（DSH 插件口径） | 状态 |
|---|---|---|---|---|
| ~~YouTube 官方库~~ | `discovery.searchRoster` | — | `daniel_roster_search`（**保留名字**） | 🔴 **已退役**：2026-09-14 起 503、09-16 起读超时，已裁决不再使用。调用**零发包**，只回「该走哪条通道」，`error.kind='channel_retired'` |
| **Brand Deep Research** | `startSearchJob` → `executeSearchJob` → 轮询 `getSearchJob` | **有品牌上下文**（品牌名／编号） | `daniel_deep_research`（第一段）→ `daniel_deep_research_commit(planId)`（第二段） | 可用 |
| **AI Open Research** | `expandTopic` → `search` → `executeSearchJob` | **无品牌／自由描述／跨品牌探路** | `daniel_open_research(topic, …)` | 可用 |
| 进度回读 | `getSearchJob` | 两条通道通用 | `daniel_research_status(jobId)` | 可用 |

**检索逻辑一行没重写**：两条通道的入参口径与提交序列全部复用已验证的仪器
`vendor/.kol-tools/daniel_search.py`。本次只在仪器里做了**抽取**（`deep_payload`／`open_payload`／
`start_job`／`expand_topic`），让 CLI（`cmd_deep`／`cmd_open`）与插件 worker 用**同一份**入参构造与提交序列；
`cmd_deep`／`cmd_open` 的行为与打印保持不变（`--self-test` 的失败是环境缺夹具导致的老问题，见 §7 边界）。

---

## 2. 工具契约（注册清单 · 共 19 个工具，其中检索类 5 个）

> **2026-11-08 追记**：当前注册数是 **20**（新增 `daniel_open_research_commit`，`baseline.json` 已同步为 20）；本节表格里的 19 是 2026-11-03 当时的数量，保留不改写历史。

| # | 工具 | 一句话 | 参数 | 写？ |
|---|---|---|---|---|
| 1 | `daniel_deep_research` | 品牌深度研究**第一段：只出计划、不提交** | `brand`(必填)、`query`(必填)、`limit`、`country`、`min_subscribers`、`max_subscribers` | 不写 |
| 2 | `daniel_deep_research_commit` | 品牌深度研究**第二段：凭 planId 提交** | `planId`(必填) | 真写（建检索任务） |
| 3 | `daniel_open_research` | AI 开放研究：**自动选默认项并直接执行** | `topic`(必填)、`brand`、`country`、`minSubscribers` | 真写（建检索任务） |
| 4 | `daniel_research_status` | 两条通道通用查进度（五档阶段） | `jobId`(必填) | 只读 |
| 5 | `daniel_roster_search` | **已停用，请勿调用**：只回指引、零发包 | （旧参数保留，均无作用；`query` 仍必填以保持签名不变） | 不写 |

**返回体纪律**：五个工具的成功/失败返回一律过 `clean()`——带 `回答纪律`（`ANSWER_POLICY`）、
无 `null`／`undefined`、缺数据写文字（`未取到`／`不适用`）。`daniel_deep_research` 的第一段
**不返回 `jobId`**（无任务可返回），这是"有没有提交"的显式判据。

**参数命名**：按契约用 `planId`／`jobId`／`minSubscribers`（deep 的订阅数沿用既有 snake_case
`min_subscribers`／`max_subscribers`，与 `daniel_roster_search` 历史参数一致）；实现里同时接受
`plan_id`／`job_id`／`min_subscribers` 作为别名，方便旧调用方迁移。

---

## 3. 两段式流程（deep）

```
daniel_deep_research(brand, query, …)         ← 只读：解析品牌 + 检索式归一（本地长度校验）
   → { planId, 品牌, 将提交的检索式, 筛选条件, 候选上限, 影响, 过期秒数(300), 过期时刻 }
        │  用户看计划、说「可以」
        ▼
daniel_deep_research_commit(planId)           ← 真写：建任务 + 开跑 + **一次只读回读**
   → { jobId, 阶段, 已完成条数, … }            （立刻返回，不轮询）
        │
        ▼
daniel_research_status(jobId) … 反复读        ← 只读：阶段/进度/结果摘要
```

硬约束（与 `daniel_write_plan/commit` 同源，单测逐条验过）：

1. **第一段绝不提交**：只调 worker 的 `research_plan`（只读解析品牌 ＋ 本地校验），
   **不调** `startSearchJob`／`executeSearchJob` ⇒ 不建任务、不写检索记录、不消耗额度；
2. **一次 planId 只对一次提交有效**（`plan_used`）；**5 分钟过期**（`plan_expired`）；
3. **不存在的 planId 被拒**（`unknown_plan`），空值走 `usage`；
4. 提交失败不会把 planId 洗成可用状态之外的假象（提交前即标记 used，与写链路一致）。

`planId` 的登记逻辑单独放在 `lib/research.js`（纯函数、无 I/O），所以"错／过期／重复"三条拒绝路径
可以在单测里直接构造，不需要碰网络。

---

## 4. 阶段映射（固定五档 · 单一实现）

`lib/research.js::mapResearchStage()` 是唯一实现，工具返回与前端左栏共用：

| 上游 `status`（大小写不敏感） | 阶段 |
|---|---|
| `queued`／`pending`／`created`／`waiting`／`scheduled`／`not_started`／`idle` | **排队中** |
| `running`／`searching`／`processing`／`in_progress`／`executing`／`started` | **检索中** |
| `enriching`／`enrich`／`enrichment` | **富化中** |
| `done`／`completed`／`completed_with_warnings`／`success`／`succeeded`／`finished` | **完成** |
| `failed`／`error`／`cancelled`／`canceled`／`timeout`／`aborted`／`rejected` | **失败** |
| 空值（刚建任务、还没回读到） | **排队中** |
| 其它未知值 | **检索中**（保留 `状态原文`，`已识别=false`；**不擅自判失败**） |

```js
// lib/research.js
export const RESEARCH_STAGES = Object.freeze(['排队中', '检索中', '富化中', '完成', '失败'])
const STAGE_OF_STATUS = new Map([
  ['queued', '排队中'], ['pending', '排队中'], ['created', '排队中'], ['waiting', '排队中'],
  ['scheduled', '排队中'], ['not_started', '排队中'], ['idle', '排队中'],
  ['running', '检索中'], ['searching', '检索中'], ['processing', '检索中'],
  ['in_progress', '检索中'], ['executing', '检索中'], ['started', '检索中'],
  ['enriching', '富化中'], ['enrich', '富化中'],
  ['done', '完成'], ['completed', '完成'], ['completed_with_warnings', '完成'], ['finished', '完成'],
  ['failed', '失败'], ['error', '失败'], ['cancelled', '失败'], ['canceled', '失败'], ['timeout', '失败'],
])

export function mapResearchStage(status, opts = {}) {
  const raw = status === null || status === undefined ? '' : String(status).trim()
  const key = raw.toLowerCase()
  // 空状态＝任务刚建、还没回读到 → 排队中；非空但没见过的 → 检索中（并保留原文供排查）
  const stage = raw === '' ? '排队中' : (STAGE_OF_STATUS.get(key) ?? '检索中')
  const out = {
    阶段: stage,
    阶段序号: RESEARCH_STAGES.indexOf(stage) + 1,
    状态原文: raw || '（服务端尚未给出状态）',
    已识别: raw === '' ? true : STAGE_OF_STATUS.has(key),
    终态: ['完成', '失败'].includes(stage),
  }
  const pct = Number(opts.percent)
  if (Number.isFinite(pct)) out.进度百分比 = Math.max(0, Math.min(100, Math.round(pct)))
  else if (stage === '完成') out.进度百分比 = 100
  return out
}
```

**进度百分比**：服务端给了 `progressPercent` 就用它；没给但有 `progressCompleted/progressTotal`
就按两者推算（向下取整到 0–100）；完成态补 100；其余情况**不给这个键**（不编数字）。

---

## 5. open 通道的"自动默认项"

用户已授权：open **自动选默认场景／内容风格／受众并继续执行，不逐项追问**。代价是必须如实回显：

- 默认项来源＝`expandTopic(topic)` 返回的三组标签，**自动全选**，每组最多 5 个；
- 扩写失败／没返回标签 → 三组为空，`自动选择说明` 写「本次没有可用的自动选项（按主题自由检索）」，
  **不编标签**；
- 返回体的 `自动默认项` 是**逐项三件套**：`项 / 取值 / 依据`（品牌上下文、场景、内容风格、受众、国家、订阅数下限），
  未指定的写 `不限` 并注明「未指定 → 不限」；
- 未给品牌时沿用仪器默认品牌（`Halliday`，可用 `DANIEL_OPEN_DEFAULT_BRAND` 覆盖），并在默认项里
  写清「未指定品牌 → 沿用默认品牌」。

---

## 6. 语料 / 映射 / 回答纪律同步

| 对象 | 改动 |
|---|---|
| `vendor/data/daniel-cli/mcp/corpus/kol-discovery/references/10-discovery-steps.md` | §2.2.12 的入口裁决改为「已退役」；新增两条通道的选择规则与工具口径；表格三行（官方库/ deep / open）按现状重写；`subscriberCount`／`rosterInsight` 两处 roster 口径同步 |
| 同目录其余 `kol-*` 束 | 由语料切分器从真源 `docs/marketing/skills/kol-intelligence.md` **重新切分**（真源同改，净行数不变 ⇒ 切片区间不漂移），逐束重新同步进包；`_MANIFEST.json` 的逐文件 hash、整束 hash、`source_doc_sha256`、`source_lines` 一并重算 |
| `app/workflow-map.json` / `.md`（＋生成器 `app/scripts/gen-workflow-map.py`） | 3 条 search 命令说明与工具对齐：`search.submit` → `mcpTool=daniel_deep_research`（`mcpTools` 另列 commit／open）、`search.job-status` → `daniel_research_status` 且页名标「五档阶段」、`search.history` 不变；`--check` 重算一致 |
| `vendor/data/daniel-cli/daniel_cli/schema.py` | `search` 模块与 `job-status`／`submit` 三条帮助文案改为两通道口径（workflow-map 的 summary 即取自此真源） |
| `lib/normalize.js` 的 `ANSWER_POLICY` | 模块名同步前端「下一步卡片」的新名：**账号与盘点／品牌档案／红人检索／红人名单／真实性核验／合作追踪／品牌提及／内容情报／声量份额**（旧名「账号与工作区／品牌资产／真实性与背调」会让卡片解析不到而被丢弃）；语料里同句的模块清单同步改 |
| `lib/trace.js` | 4 个新检索工具 + `daniel_screen_ask` 登记进豁免名单（不套四段溯源），工具全集＝白名单 5 ＋ 豁免 14 ＝ 19 |
| `tests/golden/baseline.json` | 走 `--update … --accept-new-tool` 正规入口重采（原因是 `ANSWER_POLICY` 文本变化 ⇒ 所有返回体字节必然变化）；既有工具参数表逐字节未变 |

---

## 7. 测试证据（真实输出）

### 7.1 新增单测（`tests/research-channels.test.mjs`，node:test，离线）

```
$ node --test tests/research-channels.test.mjs
# tests 8
# pass 8
# fail 0
```

覆盖：① deep 第一步不产生提交（无 jobId、worker 只被调了一次 `research_plan`）
② commit 错／过期／重复 planId 被拒且被拒时零提交 ③ 五档映射（含大小写、空值、未知状态）
④ open 自动选默认项且逐项列出 ⑤ roster 返回 `channel_retired` 且 worker 调用次数＝0、`fetch` 调用次数＝0。

### 7.2 插件既有自检（回归）

```
$ node scripts/test-trace.mjs      → 合计：PASS 153 / FAIL 0
$ node scripts/test-nulls.mjs      → 合计：PASS 101 / FAIL 0   （81 次工具调用 × 三档）
$ node scripts/test-clarify.mjs    → 合计：PASS  36 / FAIL 0
$ node tests/golden/diff.mjs       → 字节层 26/26 一致；FAIL 0
```

> 顺带修掉一条**既有**红：`test-trace` 的"白名单＋豁免＝注册全集"原本是 14 vs 15（`daniel_screen_ask`
> 未登记），现在补齐并改为 19。

### 7.3 语料漂移门禁

```
$ python3 mcp/check_corpus_sync.py --source-root <工作区>/.agents/skills
检查项：9 条，通过 9 条，未过 0 条，跳过 0 条
结论：绿 —— 包内语料与清单／源束一致
（打包态无源束时：通过 9 / 跳过 1，同样绿）
```

### 7.4 G1 契约门禁

```
PASS G1-1a 插件版本与文件数 ← daniel-dsh-plugin@0.11.0，212 个文件，0 软链
PASS G1-1b root_hash 等于版本钉死的 known-good ← 7165f0215b44c509…（一致）
PASS G1-1d 与 tgz 真源逐文件一致 ← 解包 212 文件，hash 相同，差集为空
RESULT: PASS  G1 契约门禁 — 通过 10 / 失败 0 / 跳过 2
```

### 7.5 免费演示（deep 第一步，真实返回）

```json
{
 "ok": true, "exitCode": 0,
 "command": "品牌深度研究·计划 Halliday",
 "data": {
  "planId": "815edf66061cfa6719d6",
  "通道": "品牌深度研究",
  "品牌": { "名称": "Halliday", "编号": "3690002", "品类": "AI Glasses", "竞品数": 11 },
  "将提交的检索式": "hands-on reviews and comparisons of AI smart glasses for everyday use",
  "检索式字数": 69, "检索式上限": 501, "候选上限": 10,
  "影响": {
   "会建任务": "会在品牌名下建一条检索任务并立刻开跑",
   "写检索记录": "检索记录里会多一条（可回看、可复用词表）",
   "额度": "本工作区检索额度不限，不消耗配额",
   "本次是否发包": "没有（这一步只出计划；提交是第二步）"
  },
  "过期秒数": 300,
  "过期时刻": "2026-11-03T05:15:56.645Z",
  "下一步": "把「品牌／将提交的检索式／筛选条件／影响」原样讲给用户；用户说「可以」后再调用 daniel_deep_research_commit(planId)。"
 }
}
```

返回体里**没有 `jobId`**，且"本次是否发包＝没有"——这就是"第一步不提交"的可核对证据。全程只花一次只读的品牌解析。

---

## 8. hash 变更

| 项 | 旧 | 新 |
|---|---|---|
| 插件版本 | `0.11.0` | `0.11.0`（内容变、版本不变） |
| 文件数 | 210 | **212**（新增 `lib/research.js`、`tests/research-channels.test.mjs`） |
| root hash | `587647fecb25b9e3e0fb5adf3eb39caa7562c0e36b49e31ae86ce4f179f2f0f0` | **`7165f0215b44c509b0a42d0237296691d88e91d2e71f9e3c05e1b5050cf8fd56`** |
| tgz | `releases/daniel-dsh-plugin-0.11.0.tgz`（旧内容） | 同路径**重打**（`node scripts/pack.mjs --dest ../../releases`，1,696,744 B） |

同步改了这四处常量（与 G1／手册口径一致）：

- `daniel-bot/app/tests/g1-contract-gate.mjs` → `KNOWN_GOOD = { version:'0.11.0', files:212, rootHash:'7165f021…' }`
- `daniel-bot/app/scripts/upgrade-plugin.mjs` → `BASELINE` 同上（含头部注释）
- `daniel-bot/app/desktop-patches/CHECKPOINT.md` → 「212 个文件 · 7165f0215b44」
- `daniel-bot/specs/UPGRADE-PLUGIN.md` → 基线表 ＋ 复算示例 ＋ 校验清单引用

**根 hash 口径未变**：`package/` 下普通文件（跳过 `specs`／`node_modules`／`.git`），
每条 `path\0bytes\0sha256\n` 按路径字节序串联再 SHA-256。

---

## 9. 复现命令

```bash
# 0) 单测 + 自检
cd daniel-bot/packages/0.11.0
node --test tests/research-channels.test.mjs
node scripts/test-trace.mjs && node scripts/test-nulls.mjs && node scripts/test-clarify.mjs
node tests/golden/diff.mjs

# 1) 语料（真源 → 切片 → 包内）
python3 "docs/product/daniel-copilot/_impl/TICKET-148-语料束切分器.py" --verify
python3 daniel-bot/packages/0.11.0/vendor/data/daniel-cli/mcp/check_corpus_sync.py

# 2) 重打插件包并同步到桌面端源码树
node scripts/pack.mjs --dest ../../releases
node /tmp/dsh-build/dsh-src/apps/desktop/scripts/sync-daniel-plugin.mjs \
  --from "daniel-bot/releases/daniel-dsh-plugin-0.11.0.tgz"

# 3) 复算 hash + 跑门禁
node daniel-bot/app/scripts/upgrade-plugin.mjs --verify <vendor 目录>
node daniel-bot/app/tests/g1-contract-gate.mjs
```

---

## 10. 边界与未做（如实说明）

1. **真提交未跑**：`daniel_deep_research_commit` 与 `daniel_open_research` 都会**真建检索任务**（消耗额度），
   本次验收只做了「deep 第一步」这一条不花钱的真实调用；两条提交路径的正确性由单测（mock worker）
   ＋ worker 侧结构化错误实测覆盖。要跑真提交，需用户明确点头。
2. **`research_status` 未跑真实 jobId**：检索历史接口不返回 jobId，造一个真 jobId 必须先提交任务，
   因此五档映射用单测（表驱动：15 个上游状态 ＋ 空值 ＋ 未知值）与 `researchStatusView` 的构造数据覆盖；
   真实服务端的错误路径（不存在的 jobId → `job_not_found`）已真跑。
3. **`daniel_search.py --self-test` 在本机本来就红**（缺 permanent-exclusion 夹具，未改动的原件同样红），
   与本次改动无关；本次只保证 `cmd_deep`／`cmd_open` 的行为与打印不变（入参与提交序列是同一条代码路径）。
4. **未打包 DMG**：按纪律停在"插件 tgz ＋ vendor 同步"，桌面端安装包由用户在可交互终端自行触发。
