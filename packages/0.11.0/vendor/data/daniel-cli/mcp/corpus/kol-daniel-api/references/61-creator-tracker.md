<!-- 本文件是 `docs/marketing/skills/kol-intelligence.md` L5722–L5900 的**逐字切片**（语料版本 0.9.207）；请勿在此改写判据，改动须回流源文件后重跑切分器 -->
<!-- 源节：§16 Creator Tracker（红人追踪）建链 -->

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

| 路由 | 方法 | 入参 | 返回要点 | 状态 |
|---|---|---|---|---|
| `ct.campaigns.list` | GET | `{"brandId": <int>}` | campaign 数组；元素含 `id`／`title`／`startDate`／`endDate`／`isEvergreen`／`campaignCode`／`status` | ✅ 实测 |
| `ct.campaigns.create` | POST | **8 键**，见 §16.2 | 新建 campaign 对象（含 `id`／`campaignCode`），成功时 **`syncError` 空**、`ycpResourceName` 有值 | ✅ 实测 |
| `ct.campaigns.update` | — | **只收 `startDate`／`endDate`／`brief`** —— 🔴 **`title` 建后不可改** | ⟦重建：弱证据 · 待补⟧ | ⚠️ 仅定位（TICKET-100 L47） |
| `ct.campaigns.resolveChannel` | — | ⟦重建：弱证据 · 待补⟧ | 对 `@handle`／URL **实测返回 `success:false`**（界面仍会原样提交，由服务端创建时再解析，**可能带回 `syncError`**） | ⚠️ 实测（失败侧） |
| `ct.deals.create` | POST | `{"campaignId", "creatorChannelId", "expectedVideoCount", "creatorCost", "currency"}` | ⟦重建：弱证据 · 待补⟧ | ⚠️ **已定位、未实测** |

**Deals／Videos 路由**（逐字 · `daniel_ct.py` L5）：**本轮范围只有 Campaign**（列／建／改），**Deals、Videos 留待下一步**（路由已定位见本章）。

### 16.4 归一化与回显（本章的核心纪律）

> 🔴 **判据一句话（CLS-47 · `_DEFECT-CLASSES.md` L60）**：**用户说的是人的话、接口要的是机器的话 —— 我负责翻译，但必须回显"我替你补了什么"，让人当场能纠正；宁可拒绝，不可悄悄猜。**

**日期归一（逐字 · `daniel_ct.py` L71–132 `norm_date`）** —— 支持：

| 形态 | 例 | 结果／说明 |
|---|---|---|
| 全数字分隔 | `2026-8-1`／`2026/8/1`／`2026.8.1` | → `2026-08-01` |
| 中文 | `2026年8月1日`／`2026年8月1号`／`26年8月1号` | → `2026-08-01`（**两位年 ⇒ 20xx**，并给说明） |
| 只有月-日 | `8月1日`／`8/1` | → **今年**，并给说明「未给年份 ⇒ 按今年 YYYY」 |
| 英文月名 | `Aug 1, 2026`／`August 1 2026`／`1 Aug 2026` | → `2026-08-01` |
| 已是 ISO | `2026-08-01` | 原样 |

🔴 **一律做真实性校验**：`2026年2月30日` → `None`（**不得悄悄顺延成 3/2**）。
🔴 **全角折半**（逐字 · L82–83）：中文输入法会打出全角分隔符（`／` `．` `－` `　`）—— **解析前先折半**（2026-09-29 **自检抓出**，是真 bug）。
**退化面**：空／`None`／非字符串／脏尾缀（`2026-08-01x`／`2026年8月`）→ 均不识别（返回 `(None, None)`）。

**结束形态归一（逐字 · `daniel_ct.py` L135–148 `norm_end`）**
- 口语形态 `evergreen`／`长期`／`永久`／`无期限`／`no end date`／`不设结束日期`／`一直` ⇒ **`'evergreen'`**；
- 🔴 **否定守卫**：**否定形态（`不是长期`／`并非…`／`not evergreen`／`no longer`）→ `None`**（**不得被当成 Evergreen**）。

**Evergreen → 入参（逐字 · L165–167）**：`end=evergreen` ⇒ 入参自动转 `isEvergreen=true` **且不传 `endDate`**。

**回显（逐字 · `daniel_ct.py` L193–205 `normalization_echo`）**
- 输出「开始日期 「原串」 ⇒ ISO（我补了什么）」／「结束日期 「原串」 ⇒ evergreen／ISO（…）」；
- 🔴 **只在真的做了推定（补年份／两年前缀／Evergreen 口语）时才输出，原样 ISO 不刷屏**。

### 16.5 软提醒与坑（写前必看）

**软提醒（不拦 · 逐字 · `daniel_ct.py` L208–223 `warnings_for`）**

| 触发 | 文案要点 |
|---|---|
| 已有同名 campaign | `已有同名 campaign N 条（界面允许重名，故只提醒不拦）：<ids>` |
| 开始日期早于今天 | `开始日期 YYYY-MM-DD 早于今天 YYYY-MM-DD（如需修正可走 ct.campaigns.update 的 startDate）` |
| 频道不是 `UC…` 形态 | `频道不是 UC… ID 形态，创建时可能解析失败并带回 syncError` |

**十条坑（逐字 · `tickets/TICKET-100-creator-tracker-campaign-create.md` L37–48）**

| # | 坑 | 判据／处置 |
|---|---|---|
| 1 | **命名空间认错**：`campaigns.*`（内容模块）vs **`ct.*`**（Creator Tracker） | 名称像 ≠ 同一条链路；**路由先落 chunk 再写** |
| 2 | **旧客户端快照静默失效**（CLS-46）：`brands.list` 传 `null` 报 400；`lists.delete` 的键是 `id` | 入参以 bundle 调用点为准 ＋ **写后回读** |
| 3 | **口语日期原样传入**（CLS-47）：`26年8月1号` | 归一化 ＋ **回显我替你补了什么**；不存在日期**拒绝不顺延** |
| 4 | **否定守卫**：`不是长期` 不该被当成 Evergreen | 归一化函数内做否定前缀判定，配 `[degenerate:negation]` 控制 |
| 5 | **全角字符**（中文输入法的 `／ ． － 　`） | 解析前统一折半（**本轮由自检抓出，是真 bug**） |
| 6 | **Evergreen 的接口语义**：`isEvergreen:true` 时**不得传 endDate**（落库为哨兵 `2035-12-31`） | 互斥校验 ＋ **实测确证** |
| 7 | **频道输入**：`@handle`／URL 实测 `resolveChannel` 返回 `success:false` | **给 `UC…` 最稳** |
| 8 | **把推断当事实**（CLS-46 家族）：曾按配色推测 `status` 初值 `draft` | 实测是 **`active`**；凡推断标证据级别，**第一次真跑就回代** |
| 9 | **`title` 建后不可改** | 建前确认名称；要改只能**删了重建**（`update` 只收 `startDate`／`endDate`／`brief`） |
| 10 | **参数错抛 Python 栈** | 一律**人话报错 ＋ exit 1**（逐字 · `daniel_ct.py` L311–316） |

### 16.6 工序与纪律

| 步 | 动作 | 命令／要点 |
|---|---|---|
| 1 | 解析品牌 | `brands.list`（**入参必须是 `{}`**）→ 按 id 或名字解析（**歧义即抛错，不猜**） |
| 2 | 读既有 campaign（软提醒用） | `ct.campaigns.list({brandId})` |
| 3 | **组装入参 ＋ 校验 ＋ 试算**（`--dry-run`） | 打印「归一化回显」「软提醒」「待创建：<json>」 |
| 4 | 写 | `ct.campaigns.create(payload)`（POST） |
| 5 | 🔴 **写后回读**（CLS-46 纪律） | `ct.campaigns.list({brandId})` → **按返回 id 找**；**找不到 ⇒ 视为失败**；打印「campaign 数 N → M」＋「完整对象」；有 `syncError` 打印告警 |

**工具用法（逐字 · `daniel_ct.py` docstring L19–24）**

```bash
python3 .kol-tools/daniel_ct.py --campaigns --brand Halliday
python3 .kol-tools/daniel_ct.py --create-campaign --brand Halliday --title "halliday summer test" \
    --start 2026-08-01 --evergreen --channel UC66W1l41kXuASV-UYvC9xzA
python3 .kol-tools/daniel_ct.py --create-campaign ... --dry-run
python3 .kol-tools/daniel_ct.py --self-test
```

**纪律三条（章程 L647）**：写前 `--dry-run` 看入参 → 写后**回读** → 参数错**人话报错**不抛栈。

### 16.7 实测确证值（**第一次真跑就回代**）

| 项 | 实测值 | 证据 |
|---|---|---|
| 身份／品牌 | brand Halliday **`3690002`**；档案 `youtubeChannelId` ＝ **`UC66W1l41kXuASV-UYvC9xzA`** | TICKET-100 L13；`daniel_ct.py` L329（自检夹具） |
| 建出对象 | `id=660001` · `campaignCode=7EQS4G` · `title=halliday summer test` · `startDate=2026-08-01` · **`endDate=2035-12-31` ＋ `isEvergreen=true`**（**Evergreen 哨兵**）· `status=active` · `source=ct` · **`syncError` 空**（`ycpResourceName` 有值） | TICKET-100 L28 |
| 回读 | `ct.campaigns.list({brandId:3690002})` campaign 数 **0 → 1** | TICKET-100 L29 |
| 归一化端到端 | `--start "26年8月1号" --end "evergreen"` → dry-run 回显**两条**归一化 ＋ 入参 `{startDate:"2026-08-01", isEvergreen:true}`（**无 `endDate`**） | TICKET-100 L30 |
| 脏输入拒绝 | `--start "2026年2月30日"` → 人话报错「无法识别为日期」＋ 支持格式提示，**exit 1**（**不顺延成 3/2**） | TICKET-100 L31 |
| `status` 初值 | **`active`**（推翻此前 `draft` 的推测） | TICKET-100 L46（坑 #8） |

### 16.8 仪器与验收判据

| 仪器 | 自检 | 覆盖 |
|---|---|---|
| `.kol-tools/daniel_ct.py --self-test` | **34/34**（本轮实测） | 正控 22 项（正常 Evergreen／有结束日期／标题归一／brief 空不传／频道回落与优先／二选一必填／互斥／结束早于开始／标题空／品牌缺 id／档案无频道／日期真实性／回显条件）＋ 口语归一 11 项（中文口语／多分隔符／无年份推定／英文月名／Evergreen 口语／`end=evergreen` 自动转／不存在日期／空／非字符串／脏尾缀／**否定守卫**／全大写／全角分隔）＋ 六类退化输入标记 |

**验收判据（可执行，逐条对应能力地图 acceptance）**
1. **口语输入自动归一 ＋ 回显** —— `normalization_echo` 在真的做了推定时**必须输出**，原样 ISO 不输出；
2. **结束日期与 Evergreen 互斥** —— 同给即报错；`end=evergreen` ⇒ `isEvergreen=true` 且**不传 `endDate`**；
3. **频道给 `UC…` ID** —— 非 `UC` 形态产生软提醒（不拦）；
4. **写后回读** —— 按返回 `id` 回读，**找不到即视为失败（exit 1）**。

### 16.9 范例路径

| 类型 | 路径 |
|---|---|
| 主仪器 | `.kol-tools/daniel_ct.py` |
| 传输层 | `.kol-tools/daniel_client.py` |
| 取证底稿（入参逐键来源） | `docs/marketing/kol/_build/creator-tracker-campaign-create-schema.md` |
| 任务单 | `tickets/TICKET-100-creator-tracker-campaign-create.md` |
| 上游（名单级读写） | `tickets/TICKET-099-daniel-lists-write-path.md` · 本章 §15 |
| 章程同源条款 | `docs/roles/kol-expert.md` §7.71（L640–647） |
| 缺陷类 | `docs/marketing/skills/_DEFECT-CLASSES.md` CLS-47（L60） |

---


