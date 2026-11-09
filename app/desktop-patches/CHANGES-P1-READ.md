# CHANGES-P1-READ · 补齐 P1 的 5 条只读能力入口（审计报告点名「Bot 调不到」）

> 时间：2026-11-08 · 管线 A（只读）
> 源码：`daniel-bot/packages/0.11.0`（`vendor/data/daniel-cli` ＋ `vendor/.kol-tools`），已同步到
> `/tmp/dsh-build/dsh-src/apps/desktop/resources/vendor/daniel-dsh-plugin` 并重打 tgz。
> **按纪律未打包 DMG**（要等下一次打包才进新 `.app`）。

---

## 0. 这次补的是哪 5 条（以及为什么它们以前不通）

审计（`daniel-bot/specs/CAPABILITY-GAP-AUDIT.md` §2 第 2／3 行）的判据是四层：
① 路由 → ② CLI 命令 → ③ MCP 工具 → ④ Bot 可调用。**②→③④ 不缺**（`daniel_run` 是任意只读子命令的直通），
真正断的是 **①→②：路由在仪器里已经跑通，但 CLI 没有对应命令**。所以本次只补 CLI（`schema.py` ＋
`commands/`），**没有新增 MCP 工具**——`daniel_run` 立刻就能调到。

| # | 命令 | 数据通路 | 只读？ | 以前的状态 |
|---|---|---|---|---|
| 1 | `daniel mentions chart` | `brandMentions.getChartData` | ✅ | 仪器 `--chart` 有，CLI 无命令 |
| 2 | `daniel mentions top-channels` | `brandMentions.getTopChannels` | ✅ | 仪器 `--top-channels` 有，CLI 无命令 |
| 3 | `daniel mentions evidence` | `brandMentions.getVideoEvidence` | ✅ | 仪器 `--evidence` 有，CLI 无命令 |
| 4 | `daniel mentions export` | `brandMentions.exportMentions`（**非 batch GET**） | ✅ | 仪器 `--export` 有，CLI 无命令 |
| 5 | `daniel search enrich` | `discovery.enrichChannels` ＋`discovery.enrichEmails` | ✅（只读通道） | 只存在于 `daniel_search.py --enrich` 的批处理里，且**原地写回文件**；CLI 无命令 |

---

## 1. 命令契约（`--help` 就是契约，由 `schema.py` 派生）

### 1.1 四条 `mentions`（都要求 `--brand` ＋ `--job`）

| 命令 | 必填 / 可选 | 默认 | 输出（`data` 字段，业务语言） |
|---|---|---|---|
| `chart` | `--brand` 必填、`--job` 必填 | — | `任务编号` ＋ `表现分布`／`真实性分布`／`视频类型分布`／`推广建议分布`／`月度趋势`／`分布块数` |
| `top-channels` | `--brand`＋`--job` 必填；`--limit`（5–50）、`--relevance-filter`（all／confirmed／confirmed_likely） | `--limit 10`、口径 `all` | `频道数`／`本次口径`／`本次上限`／`可能还有更多`／`频道[]`（频道编号、频道名、订阅数、视频数、平均综合分、平均播放、总播放、平均真实性、频道得分、是否已在名单、各表现档位视频数、相关性） |
| `evidence` | `--brand`＋`--job` 必填（**不需要视频编号**） | — | `状态`／`匹配视频数`／`符合条件数`／`入选视频数`／`已分析数`／`剩余可入选数`／`剩余待分析数`／`是否已开始分批`／`批次数`／`视频[]`（视频编号、视频标题、分析进度）／`视频数` |
| `export` | `--brand`＋`--job` 必填；`--relevance-filter`、`--exclude-official`、`--language`（14 个语言码） | 口径 `confirmed_likely`；不排除官方；不限语言 | `条数`／`邮箱缺失条数`／`提及[]`（频道名、频道账号、频道链接、视频标题、视频链接、播放量、订阅数、综合分、自然表现、相关性、视频类型、是否官方、语言、邮箱） |

三条“按真实调用点定的”细节（都在下面的 §2 有出处）：

1. **`--brand` 用于本地核对任务归属**：四条都会先按品牌拉一次 `brandMentions.listJobs`（最多 10 条），
   编号不在清单里且清单没触上限 ⇒ 直接报“这个品牌下没有任务编号 …”并列出该品牌现有任务，
   **不发任何读请求**（与既有 `mentions status`／`results` 同一条预检）。
2. **`top-channels` 的相关性默认 `all`**：实测这条路由用 `confirmed`／`confirmed_likely` 会在同一数据集回
   0 条（服务端过滤字段与展示字段不一致），所以默认取全量、相关性看返回里的「相关性」列。
3. **`evidence` 不需要视频 id**：路由入参就是 `{jobId, brandId}`；视频编号在返回的 `视频[]` 里
   （拿它去触发深析是另一条**写**链，不在只读范围）。

### 1.2 `search enrich`（只读富化）

| 项 | 契约 |
|---|---|
| 输入 | `--channel-ids "UC…,UC…"`（英文逗号分隔）**或** `--items-file <json>`（三形状都认：`["UC…"]`／`[{"channelId":"UC…"}]`／`{"results":[…]}`、`{"channels":[…]}`）；两者**只能给一个** |
| 邮箱 | 不加 `--emails` **只走 `discovery.enrichChannels`**；加了才再走 `discovery.enrichEmails` |
| 拆批 | 频道链路每批 **≤100**、邮箱链路每批 **≤50**（两条常量来自仪器实测，**不互相类推**） |
| 输出 | `频道数`／`来源`／`去重条数`／`批次{频道批量,邮箱批量,频道请求次数,邮箱请求次数,失败批次}`／`补齐情况{订阅数,国家,标签,商务邮箱}.{补到,未补到}`／`频道[]`（频道编号、频道名、订阅数、国家、标签、商务邮箱、补齐字段）／`没补到的{条数,明细,是否截断}`／`频道链路没返回的编号`／`说明` |
| 只读 | **不发 `mutate`、不写任何文件、不改任何 Daniel 数据**；不走确认轴、不落写审计 |

三种输入错误都有“怎么给”的提示（缺输入／两个都给／文件不存在），且**一次请求都不发**。

---

## 2. 参数来源（路由 → 真实调用点 → 入参键 → 返回形状）

> 原则：**抄调用点，不猜**。下表“调用点”列都是本包/本仓库里能点开的文件行。

| 路由 | 调用点（文件:行） | 入参键（照抄） | 返回形状（照抄） |
|---|---|---|---|
| `brandMentions.getChartData` | `vendor/.kol-tools/daniel_mentions.py:671`（`cmd_chart`）；`vendor/.kol-tools/daniel_takeover_check.py:279`；前端 bundle `docs/marketing/kol/_daniel-integration/02-brand-mentions.md:62`（`@288428`） | `{jobId}` | `02-brand-mentions.md:31/162`：5 块 `performanceDist[{performance,count}]`／`authDist[{label,count}]`（`label` 可为 null）／`videoTypeDist[{videoType,count}]`／`promotionDist[{recommendation,count}]`／`monthlyTrend[{month,count,avgViews,avgComposite}]` |
| `brandMentions.getTopChannels` | `vendor/.kol-tools/daniel_mentions.py:685`（`cmd_top_channels`）；`daniel_takeover_check.py:283/285`；bundle `02-brand-mentions.md:63`（`@288564`，界面传 `limit:25`） | `{jobId, limit, relevanceFilter}` | `02-brand-mentions.md:32/163`：数组，16 键（`channelId/channelTitle/subscriberCount/videoCount/avgComposite/avgViews/totalViews/avgAuthenticity/channelScore/isRostered/{high,good,average,low,unrated}PerformanceCount/relevanceLabel`）；`limit` 合法 **5–50**（1／3／100 → 400） |
| `brandMentions.getVideoEvidence` | `vendor/.kol-tools/daniel_mentions.py:701`（`cmd_evidence`）；`daniel_takeover_check.py:297`；bundle `02-brand-mentions.md:64`（`@288729`） | `{jobId, brandId}` | `02-brand-mentions.md:33/164`：对象 10 键（`status/matchingCount/eligibleCount/selectedCount/analyzedCount/remainingEligibleCount/remainingAnalysisCount/batchStarted/batches(数字)/videos[]`） |
| `brandMentions.exportMentions` | `vendor/.kol-tools/daniel_mentions.py:722`（`cmd_export`，`method="GET_PLAIN"`）；`daniel_takeover_check.py:316`；bundle `02-brand-mentions.md:84-87`（`@330578`，**原始 fetch、非 batch**） | `{jobId, relevanceFilter, excludeOfficial, languageFilter?}` | `02-brand-mentions.md:34/165`：数组，行 14 键（`channelName/channelHandle/channelUrl/videoTitle/videoUrl/views/subscribers/compositeScore/organicPerformance/relevance/type/isOfficial/language/email`） |
| `discovery.enrichChannels` | `vendor/.kol-tools/daniel_search.py:939`（既有 `cmd_enrich` 的写回批处理）；本包新增只读入口 `daniel_search.py:1065` | `{channelIds}`，单批 **≤100**（`daniel_search.py:81`） | `{channels:[{channelId, publicData:{subscriberCount, country, topicCategories, businessEmail, title}, …}]}`（嵌套形状见**仓库根** `.kol-tools/seed_probe_mcgeee.py:94`；本命令两种形状都认） |
| `discovery.enrichEmails` | `vendor/.kol-tools/daniel_search.py:958`；新增只读入口 `daniel_search.py:1091` | `{channelIds}`，单批 **≤50**（`daniel_search.py:82`：50→200／51→400） | `{results:[{channelId, email}]}` |

**找不到的部分**：本次没有“猜”任何参数。`getVideoEvidence` 一度被怀疑还需要视频 id —— 调用点与
400 报文都只有 `{jobId, brandId}`（`02-brand-mentions.md:33`、`:145` 的必填键复核），所以**不加**视频 id 参数。

---

## 3. 只读是怎么保证的（不是靠“我们觉得它只读”）

| 机制 | 说明 | 可核对的地方 |
|---|---|---|
| CLI 层声明 `write=False` | 不进写链：没有 `--confirm`／`--dry-run`／`--delete-token`，`schema --check` 的 S6 会拦“读命令带确认开关” | `schema.py` 四条 `c(...)` 无 `write=True`；`daniel schema --check` S6 通过 |
| `mentions` 四条走 `d.query` / `d.query_plain` | 都是 GET；`export` 的非 batch 形态由 `query_plain` 发出（前端调用点就是这一形态） | `daniel_client.py::query_plain`；`daniel_mentions.py::call(method="GET_PLAIN")` |
| `search enrich` **不发 `mutate`** | 富化两条路由在 tRPC 里登记为 mutation（POST），但只取数据、不写库。CLI 用**显式的只读通道** `read_post()` 发送：不参与写链的确认轴与写审计 | `daniel_client.py::read_post`（新）＋ `daniel_search.py::cmd_enrich_read` |
| `search enrich` 不写文件 | 旧的 `daniel_search.py --enrich` 会**原地覆盖写回**输入文件 ＋ 写 CSV；新入口**只读输入、只出 stdout** | `cmd_enrich_read` 全程无 `io.open(...,'w')`；测试 ④d 断言输入文件逐字节不变 |
| 测试用桩断言 | 假客户端的 `mutate` 与 `read_post` 是两个方法、分别记账：5 条命令跑完 `mutate` 计数必须为 **0** | `tests/p1-read-commands.test.mjs` ③③d④④b④c④d |

---

## 4. 改动文件

| 文件 | 改动 |
|---|---|
| `vendor/data/daniel-cli/daniel_cli/schema.py` | 注册 5 条命令（`mentions chart/top-channels/evidence/export`、`search enrich`）：参数、帮助、示例、返回说明、`instrument`／`route_debug` |
| `vendor/data/daniel-cli/daniel_cli/commands/mod_mentions.py` | 4 个 handler ＋ 业务字段整形（`shape_chart`／`shape_top_channels`／`shape_evidence`／`shape_export`）＋ `--limit` 本地边界（5–50） |
| `vendor/data/daniel-cli/daniel_cli/commands/mod_search.py` | `cmd_enrich`（输入二选一校验、文件存在性校验、调仪器只读入口） |
| `vendor/data/daniel-cli/daniel_cli/runtime.py` | `read_instrument(..., shape=)`：取数留在仪器、**取名**在 CLI（`data` 换业务字段名，`read` 元信息仍按原始载荷算） |
| `vendor/data/daniel-cli/daniel_cli/cli.py` | 缺参／参数不合法时，JSON 与 stderr 都补一条**可照抄的示例**（从 schema 取，不手写第二份）——“该怎么给”不再只是一句“去看帮助” |
| `vendor/.kol-tools/daniel_client.py` | 新增 `read_post()`（只读语义的 POST 查询，独立于写链的 `mutate`）与 `query_plain()`（非 batch GET） |
| `vendor/.kol-tools/daniel_mentions.py` | `export` 改走客户端的 `GET_PLAIN` 通路（不再自己发 urllib，可离线测试；报错面不变） |
| `vendor/.kol-tools/daniel_search.py` | 新增只读富化入口 `--enrich-ids`／`--enrich-file`／`--json`（`cmd_enrich_read`）：合并嵌套 `publicData`、两条链路分别拆批、只出结果不写文件 |
| `tests/p1-read-commands.test.mjs`（新） | 11 条用例：帮助文案／缺参提示／四条路由／只读断言／拆批上限／文件不回写 |
| `tests/fixtures/cli-stub/daniel_client.py` | 假客户端补 `BASE`／`query_plain`／`read_post`／四条 mentions 读路由（**向后兼容**：`lists add-items` 的用例不受影响） |

---

## 5. 测试证据（真实输出）

### 5.1 全量测试（现有 20 条 ＋ 新增 11 条）

```
$ cd daniel-bot/packages/0.11.0 && node --test tests/*.mjs
1..31
# tests 31
# suites 0
# pass 31
# fail 0
# cancelled 0
# skipped 0
# todo 0
```

（改动前同一命令：`# tests 20 / # pass 20 / # fail 0`。）

### 5.2 新增用例覆盖了什么

| 用例 | 断言要点 |
|---|---|
| ① 帮助 | 5 条命令都含“给什么、怎么给”＋可照抄示例（`--channel-ids` 示例、`每批 ≤100`／`每批 ≤50`、`不需要视频编号`） |
| ② / ②b 缺参 | `mentions *` 缺参 → 退出 2，`error.hint` 直接给出 `daniel mentions <cmd> --brand 3690002 --job …`；`search enrich` 三种错误各给“两种给法”，且**零请求** |
| ③ | `chart`：payload 恰好 `{jobId}`，`data` 无内部字段名（`performanceDist` 为 undefined），null 标签行保留 |
| ③b | `top-channels`：payload `{jobId, limit:25, relevanceFilter:'all'}`；字符串数字 `"542578.0000"` → `542578`；`--limit 3/100` 本地拦下且**零请求** |
| ③c | `evidence`：payload `{jobId, brandId:3690002}`；视频清单业务化 |
| ③d | `export`：走 `query_plain`；payload 带 `excludeOfficial:true`／`languageFilter:'en'`；`邮箱缺失条数` 正确 |
| ④ / ④b | `search enrich`：`read_post` 路由序列正确、**`mutate` 计数 0**；没给 `--emails` 时**不声称补过邮箱** |
| ④c | 101 个频道 → `[100, 1]` 两批；51 个邮箱 → `[50, 1]` 两批（**不互相类推**） |
| ④d | `{"results":[…]}` 形状可读、重复编号去重、**输入文件逐字节不变** |

### 5.3 CLI 一致性自证

```
$ python3 vendor/data/daniel-cli/bin/daniel schema --check --json
"data": { "ok": true, "summary": "全部通过（10/10）", "commandCount": 97, ... }
```

（`mention` 四条与 `search enrich` 都已进 CLI；CLI 派生 MCP 工具数 97，其中含
`daniel_mentions_chart/top_channels/evidence/export` 与 `daniel_search_enrich`。）

---

## 6. hash 变更（插件重打）

> 本次重打过程中出过几个**中间包**（`f8bf1b51…`／`11d38bee…`，都只为核对注释与常量，未出 DMG）；
> **终版**是 `c81af4dd…`（`1,733,442 B`）。下表与所有常量一律以终版为准，下面贴的 `--apply`
> 输出就是终版那次（所以“旧 hash”是上一个中间包 `11d38bee…`）。

| 项 | 改前（P1-READ 之前） | 改后（终版） |
|---|---|---|
| tgz | `releases/daniel-dsh-plugin-0.11.0.tgz`（216 文件） | 同路径重打（**217 文件**，1,733,442 B，解包 5.7 MB） |
| root hash | `5b9cf918c4481edd26c36392e2e41a4ffd80bc1fa46edcbdf43edefe09b0a121` | **`c81af4dd14bdf8ec3017b13672b41ca87a4f59ccbc25b47b573e31efd4ec4e2d`** |
| 文件数 | 216 | 217（＋`tests/p1-read-commands.test.mjs`） |

重打与同步（终版那次，真实输出）：

```
$ node scripts/pack.mjs --dest ".../daniel-bot/releases"
npm notice total files: 217
出包：.../releases/daniel-dsh-plugin-0.11.0.tgz

$ node app/scripts/upgrade-plugin.mjs --tgz releases/daniel-dsh-plugin-0.11.0.tgz \
      --src /tmp/dsh-build/dsh-src --allow-republish --apply
  旧 hash   11d38beeac504295a80c038ca7f4b1bb2dc02ff21ef5471c433fab1f51c5a8d8
  新 hash   c81af4dd14bdf8ec3017b13672b41ca87a4f59ccbc25b47b573e31efd4ec4e2d
  新文件数  217
✓ 已写入 /private/tmp/dsh-build/dsh-src/apps/desktop/resources/vendor/daniel-dsh-plugin
  daniel-dsh-plugin@0.11.0 · 217 个文件 · c81af4dd14bd
  与 tgz 一致：是（版本 / 文件数 / hash 三项都断言过）

$ node app/scripts/upgrade-plugin.mjs --verify /tmp/.../resources/vendor/daniel-dsh-plugin
  版本        0.11.0
  文件数      217
  root hash   c81af4dd14bdf8ec3017b13672b41ca87a4f59ccbc25b47b573e31efd4ec4e2d
```

> 同版本号重打用了 `--allow-republish`（版本语义：内容修 bug、不升版本；已按手册 §6.2 记录）。

### 6.1 跟着改的常量／文档（漏一个 G1 就红）

| 文件 | 改了什么 |
|---|---|
| `daniel-bot/app/tests/g1-contract-gate.mjs:44` | `KNOWN_GOOD` → `{ files: 217, rootHash: 'c81af4dd…' }` |
| `daniel-bot/app/scripts/upgrade-plugin.mjs:26/47` | 文件头基线注释 ＋ `BASELINE` 同步 |
| `daniel-bot/specs/UPGRADE-PLUGIN.md` | §3 基线表（217／新 hash，并保留旧行说明“同版本两个包”）／§4 Step 0 预期／§5 常量示例／§6.3 无需升级样例／§9 坑 3 的两套 hash 口径表 |
| `daniel-bot/app/desktop-patches/CHECKPOINT.md:58` | sync 脚本“期望输出”改成 `217 个文件 · c81af4dd14bd` |
| 本文件 | 契约、来源、测试、hash |

### 6.2 G1 结果

```
$ node daniel-bot/app/tests/g1-contract-gate.mjs
PASS G1-1a 插件版本与文件数 ← 期望: daniel-dsh-plugin@0.11.0，217 个文件，0 软链 | 实际: 同
PASS G1-1b root_hash 等于版本钉死的 known-good ← 期望: c81af4dd14bd6eda…（0.11.0） | 实际: 一致
SKIP G1-1c PLUGIN-MANIFEST.json 一致 ← 补丁未引入清单文件（G1 自己说明这是 skip，不是 FAIL）
PASS G1-1d 与 tgz 真源逐文件一致 ← 解包 217 文件，hash 相同，差集为空
PASS G1-2a / G1-2b / G1-3a / G1-3b / G1-4a / G1-4b / G1-4c
SKIP G1-4d seed-profile 端到端幂等（需要已签名 .app，本会话无打包产物）
RESULT: PASS  G1 契约门禁 — 通过 10 / 失败 0 / 跳过 2
```

---

## 7. 偏差、待确认与已知问题（不藏的几件事）

1. **`search enrich` 没有把 `--brand` 设成必填**（与任务书第 3 条“`--brand` 必填”的一处偏差）。
   理由：这两条路由的入参只有 `channelIds`（见 §2），没有 brandId；强行要求用户填一个**不参与取数**的
   品牌只会让人以为它影响结果。四条 `mentions` 命令按任务书要求 **`--brand` 必填**，且它真的有用
   （本地核对任务归属）。如果要求统一，改成必填只需加一行（`required=True`）＋在仪器里忽略它。
2. **富化路由是 POST 动词**：平台把它们登记在 mutation 下（`daniel_search.py:939/958` 的既有实现也用
   `mutate`）。本命令用 `read_post()` 只读通道发送 —— 不写库、不写文件、不落写审计，但它**不是 GET**。
   测试的判据是“**不发 mutate**”（桩里两个方法分开记账），这一点在 §3 已写明。
3. **`daniel_search.py --self-test` 失败（预先存在，与本次无关）**：`self_test()` 在
   `IndexError: list index out of range`（`daniel_search.py:1588`），`packages/0.10.0` 的同名自检
   同样失败（`:1343`）。本次没有改它（不在票面范围），已在此登记。
4. **没有新增 MCP 工具**：`daniel_run` 是任意只读子命令直通，5 条命令立刻可调；新增专用工具是
   另一件事（会改插件工具清单与 golden baseline）。
5. **未打包 DMG**（按纪律）；`/tmp` 被清后需要按 CHECKPOINT §3 的步骤重新 sync ＋ 打包。
