# CHANGES · 执行轨迹：重复动作合并（×N）+「当前」指针 + 闪烁修复

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，基线 `ce7073d5`，已含品牌/登录/主题/能力全景/执行透视/轨迹降噪）
> 改动包：`packages/client/ui-capability-map`（既有包内改，**不新增依赖、不新增请求、不新增包**）
> 状态：**类型检查 / 桌面构建 / 客户端 bundle / 单测全绿；按纪律未打包**
> 一句话：一次任务里**同一个业务动作**（同模块 + 同动作）无论被调用多少次都只占**一行**，位置留在第一次出现处，右侧用小号弱化文字标 `×N`，状态「还有一次在跑 = 进行中，全部结束 = 已完成」；「当前」改为**最新一条发起且还没收到结果的调用**（带 300ms 稳定窗口）；行按**发起顺序**排，`turn/end` 收尾所有未回结果的调用；行的 DOM 节点在任务内保持同一引用，淡入只在任务重置时出现一次，高频事件合并成一次重排。

---

## 0. 三个现象 → 三条修复

| # | 用户看到的现象 | 根因（实测/核对代码） | 修复落点 |
|---|---|---|---|
| 1 | 问「Halliday 的竞品有哪些？」后，左栏出现 **7 行完全相同的「查看品牌档案 · 品牌资产 · 已完成」**，「读取工作区清单」也出现两次 | 折叠按 `callId` 去重：同一动作每调一次就是**新 callId**，于是每次调用都新开一行（逐个品牌查档案 = 7 行） | 合并键 = `模块 + 动作`（`trace.ts:367 mergeKey` / `trace.ts:625 danielRow`）；一行一个 `count` |
| 2 | 任务已有 5 个步骤，界面仍显示在跑「第 3 / 第 4 个」，像倒回去了 | 「当前」= **按行位置找最后一个 running 行**（旧 `publish()`），而行的 running 取决于「这一行收到过几次结果」；并行/乱序完成时，早发起、晚返回的调用所在行位置更靠前，指针就落在旧行上（复现输出见 §2.1） | 「当前」= **发起序号最大、且仍未 settle 的调用**所在行（`trace.ts:663 pickCurrent`）；300ms 稳定窗口；`turn/end` 逐调用收尾（`trace.ts:583 settle`） |
| 3 | 动态地图节点执行时「一闪一闪」（高亮/文字/条目频繁跳动） | 主因两条：①「当前」指针在并行行之间来回跳（现象 2 的同源）；②每个事件一次 publish + 一次通知，风暴时一帧内多次重排。行 key 与淡入本身是稳定的（核对结论见 §3） | 行 key = 首调 id（任务内不变，`TraceRail.tsx:156`）；淡入改成 `data-enter` 只在重置出现（`TraceRail.tsx:107`）；指针 300ms 稳定窗口；事件风暴合并（`trace.ts:751 notify`） |

---

## 1. 合并键 = 模块 + 动作（同一任务内）

### 1.1 判据

一次 `tool/call` 先按既有规则解析成 `{ module, action }`（`describeToolCall()`，口径见 `CHANGES-RAIL-V2.md` §2、`CHANGES-TRACE-FILTER.md` §1，本次未改），再用

```ts
`${module ?? '\u0000'}\u0000${action}`
```

当键（`trace.ts:367`）。同一任务里键相同的调用**共用同一个行对象**（`trace.ts:625` 的 `rows` 表），因此：

- 第 2 次及以后的调用**不新增行**，只把这一行的 `open += 1`、`count += 1`；
- 行对象只建一次，`order` 只在建行时 `push` 一次。

模块名/动作句都来自随包生成的 `module-map.generated.ts`，不含模型写的参数、命令、路径——合并键因此也不会把两次「看起来像同一个动作」的不同调用凑到一起，除非它们真的解析到同一个业务动作。

### 1.2 位置：第一次出现处

行只在**第一次**出现时插入 `order`，之后无论被调用多少次都**不再移动**。因此：

```
读取工作区清单 → 查看品牌档案 ×7 → 读取工作区清单
```

渲染结果是两行，第一行是「读取工作区清单」（位置 1），第二行是「查看品牌档案」（位置 2）——第二行的 7 次调用不会把它推到末尾，最后那次「读取工作区清单」也不会把自己变成第三行。

### 1.3 次数 `×N`

- 计数：`FoldedCall.count`（`trace.ts:385`），每次 `start()` 命中该行就 +1；
- 发布：`publish()`（`trace.ts:694`）**只在 `count > 1` 时**把 `count` 写进 `TraceStep`（`trace.ts:131` 可选字段）；只出现 1 次时**根本没有这个字段**（不是 0、不是 1），旧快照的精确断言因此不受影响；
- 折叠行「整理结果」**永不显示次数**（`call.id === WORK_ROW_ID` 时跳过），与 `CHANGES-TRACE-FILTER.md` §2.3 的「不显示次数」一致；
- 渲染：行右侧 `<span className={css.stepCount} data-count="7">×7</span>`（`TraceRail.tsx:176-178`）；
- 文案本地化：`locales.ts:29`（zh）/ `locales.ts:82`（en）都是 `'task.step.times': '×{count}'` —— 两种语言都用 `×`，不翻译成英文单词；
- 样式（`CapabilityMap.module.css:413`）：`font-size: 10px`、`color: var(--dsw-alias-label-caption)`（弱化）、`font-variant-numeric: tabular-nums`、无背景、无边框、无圆角 —— **纯文字，不是彩色徽章**；
- 无障碍：次数进 `aria-label` 尾部（`查看品牌档案，品牌资产，已完成，×7`），读屏能听到；视觉上仍是行尾的一小段弱化文字。

### 1.4 状态聚合

行的状态不再取决于「最后一次结果」，而是**这一行还有几个调用在飞**：

```ts
private settle(call: StartedCall | undefined): void {
  if (call === undefined || call.settled) return
  call.settled = true
  call.row.open = Math.max(0, call.row.open - 1)
}
```

- `tool/call` → `open += 1`；
- `tool/result` → 只给**这条 callId** 记一次 settle，`open -= 1`；重复结果、已 settle 的调用再收到事件都不会二次扣减，所以**已完成是终态，不会回退成进行中**；
- `turn/end` → 遍历所有未 settle 的调用逐个 settle（不再整表 `open = 0`），中断/取消的调用也被收尾；
- 发布时派生：`open > 0 ? 'running' : 'done'`（`trace.ts:704`）。

因此「还有一次在跑 → 进行中；全部结束 → 已完成」是逐调用的，而不是按「最后一行」猜的。

### 1.5 不合并的情况

- **模块不同**（如「品牌资产 / 查看品牌档案」与「声量份额 / 查看声量总览」）：两行，顺序与现在一致；
- **动作不同**（如「品牌资产 / 读取品牌列表」与「品牌资产 / 查看品牌档案」）：两行；
- **内部动作**（bash / read / write / python / skill / web 等）：仍全部折叠进任务里唯一的「整理结果」行，**不进 Daniel 步骤**，也不参与 `×N`（`foldedRow()` 未改）；
- 单次出现：不显示次数。

### 1.6 边界（写清楚取舍）

1. **`A → B → A` 仍合并为一行，位置取第一次，次数 = 2。** 这是「合并键」的直接后果：轨迹是「本次任务在哪些动作上花了多少」，不是逐条流水账。取舍是——两次 A 中间夹了 B 时，界面无法从行上看出「A 停顿后再做」，只能看到「A 做了 2 次、B 做了 1 次」；逐条的先后仍在右侧对话记录里。若将来需要「中断后再续」这种时间线语义，应新增一种「分段」行，而不是偷偷放弃合并键。
2. **无法命名的 Daniel 调用（兜底行）保持旧的「紧邻才合并」。** 这类调用没有业务身份（`module = null`、动作是兜底句），两个不相干的未命名调用不该被卖成「同一个动作」；因此只有紧挨着的兜底调用才共用一行，中间夹了任何别的行就另起一行。这也是既有 `trace-filter.client.spec.tsx`「keeps a row for a Daniel call the map cannot place instead of folding it」保持通过的原因。
3. **同一任务内计数，新任务从 1 重新开始**：`beginTask()`（`trace.ts:515`）清空 `calls / rows / order / work / 当前指针`；会话切换/收起面板走 `forget()`（`trace.ts:495`），连 `task` 序号一起归零。
4. **24 行窗口不变**：`TRACE_STEP_LIMIT = 24` 仍只截「可见步骤」，模块全景与 `count` 统计的是全部调用（合并后的行也照常滚出窗口）。
5. **模块全景数的是调用次数，不是行数**：7 次品牌档案合并成 1 行后，「品牌资产」仍记 **7 次**（`publish()` 用 `call.count` 累加，`trace.ts:712-715`）。这保证「合并」只影响行数，不影响「用了多少」。
6. **合并不改「哪些调用能成行」**：`isDanielTool()` 的判据、`整理结果` 折叠行、`本次未调用 Daniel 能力` 提示全部沿用旧口径。

---

## 2. 「当前」的判定口径与乱序完成的处理

### 2.1 旧口径与实测复现（修复前）

旧 `publish()`：

```ts
const current = running
  ? [...visible].reverse().find(step => step.status === 'running') ?? null
  : null
```

即「**按行位置，找最后一个还在 running 的行**」。用 5 步的真实形态跑一遍（1 次工作区 + 3 次品牌档案 + 1 次品牌档案，其中第 5 步先返回、第 3/4 步还没返回）：

```
rows: 5
  1. 读取工作区清单 (done)
  2. 查看品牌档案 (done)
  3. 查看品牌档案 (running)
  4. 查看品牌档案 (running)
  5. 查看品牌档案 (done)
current: 第 4 行 · 查看品牌档案
running rows: 2
```

第 5 行已经完成、界面却把「当前」放在第 4 行——正是用户说的「像倒回去了」。根因有两条，都已核对：

1. **指针按行位置取**，不按调用本身；并行调用里「较早发起、较晚返回」的那条永远占着更靠前的位置；
2. **行的 running 只由结果事件驱动**：某个调用拿不到 `tool/result`（中断、取消、事件缺失）时，那一行会一直 running，直到 `turn/end` 才被收尾——整个回合里界面就卡在旧行。

### 2.2 新口径

「当前」= **发起序号（`tool/call` 的 `event.seq`）最大、且仍未 settle 的调用**所在的行（`trace.ts:663 pickCurrent`）：

- 每条 `tool/call` 记一条 `StartedCall { row, seq, settled }`（`trace.ts:602 start`）；
- `pickCurrent()` 遍历未 settle 的调用取最大 `seq`；
- 多条并行时，**最新发起的那条占「当前」位**，其余仍是「进行中」但 `data-current` 不是 `true`（`TraceRail.tsx:137` 按行 id 比较）。

**稳定窗口**：指针已经落在某行、该行仍在跑时，**300ms 内不换行**（`CURRENT_HOLD_MS = 300`，`trace.ts:80`）；只有「它坐的行已经结束」或「窗口已过」才允许移动到新的候选。这样两条相邻事件（A 起、B 起，B 又回）不会让高亮来回跳。取舍：正常节奏下指针最多滞后 300ms；窗口结束后候选是谁就落到谁（不会自己“跳回”旧行）。

**顺序**：`order` 只在建行时追加，`steps` 永远按**发起顺序**发布；完成先后只改 `status`，不改位置。乱序完成（先发 A、后发 B，B 先回）的发布结果就是 `[A(running), B(done)]`，指针回到 A —— 行的顺序没有变。

**`turn/end` 收尾**：逐调用 settle（§1.4），所以「缺 result 的调用」不会永久卡在进行中；`turn/end` 之后迟到的 `tool/result` 是 no-op（`settle()` 幂等），不会把已完成改回进行中。

### 2.3 已验证的边界

- 新任务（人类 `user/message`）→ 指针清空、行清空、`task + 1`；
- 会话切换 / 收起面板 → `forget()` 全清，指针不残留；
- `turn/end` 后行仍留在屏幕上（可读「上次做了什么」），但 `current = null`、`running = false`；
- 面板收起时不订阅、不折叠（沿用旧口径）。

---

## 3. 闪烁的三个来源与处理

先把怀疑逐条对着代码核对，再说改了什么（不照猜）：

| 怀疑 | 核对结论 | 处理 |
|---|---|---|
| ① 行 key 不稳定 → React 重排/重挂载 | 旧代码 key 用 `step.id`（首个 callId），**本身是稳定的**；但本次要引入「合并」，如果按 `module+action` 现场生成 key 或新 id，就会变成不稳定 | 明确规定 **行 id = 首调 id**（`trace.ts:625` 建行时传入），任务内不变；`TraceRail.tsx:156` 用它做 key；单测断言 20 次更新后 `li` 仍是同一个 DOM 节点 |
| ② 淡入动画被每次更新重放 | 旧代码 `animation` 挂在 `.task` 上、靠 `key={trace.task}` 重挂载才重放，**更新时不会重放**；但它依赖「整块重挂载」才不重放，一旦有人去掉 key 就会每次都淡入 | 改成显式标记：`data-enter="on"` 只在 `task` 序号变化后的 200ms 内出现（`TraceRail.tsx:80-86,107`），CSS 只在 `[data-enter='on']` 上播动画（`CapabilityMap.module.css:157`）；单测断言「更新后不出现、重置后出现一次、200ms 后消失」 |
| ③「当前」指针在两条相近事件间来回切 | **是主因之一**：旧口径是「最后一个 running 行」，并行调用乱序完成时会在行之间跳（§2.1 复现） | 「当前」改为按调用取最新未完成 + 300ms 稳定窗口；单测用假定时器断言窗口内不抖、窗口后才移动 |
| ④ 高频事件逐条重排（一帧多次） | **是主因之二**：每个窗口通知都会 `publish()` 并同步通知一次，40 个事件就是 40 次重排 | `notify()`（`trace.ts:751`）合并风暴：一个窗口（80ms）内前 6 次照常即时发布，之后**整窗最多一次**，带最新快照；快照本身永远是最新的，只是通知被合并 |

另外两条既有约束仍在：

- `prefers-reduced-motion` 下**没有动画**：`useReducedMotion()` 决定不写 `data-enter`、`data-pulse="off"`，CSS 媒体查询再兜一层（`CapabilityMap.module.css:588`）；
- 状态单调：`tool/result` 只 settle 一次、重复 `tool/call` 直接忽略（`start()` 里 `calls.has(id)` 早退），所以**同一个调用/同一行**的「已完成」不会再回到「进行中」。注意：同动作的**新调用**（新 callId）当然会把该行重新标成进行中——那是新的一次执行，不是状态回退。

---

## 4. 测试证据

### 4.1 新增 18 条（`tests/trace-dedupe.client.spec.tsx`，全部通过）

| # | 用例 | 断言要点 | 行号 |
|---|---|---|---|
| 1 | 连续 7 次同动作合并 | 1 行，`id` = 首调 `p0`，`count: 7`，位置在首调；全部返回后 `done` 且仍 `count: 7` | 260 |
| 2 | 非连续重复（A→B→A）合并 | 行 id 序列 `['a1','b1']`，A 行 `count: 2`，B 行无 `count` | 280 |
| 3 | 模块/动作不同不合并 | 三行 `账号与工作区:读取工作区清单`、`品牌资产:读取品牌列表`、`声量份额:查看声量总览`，顺序不变，均无 `count` | 296 |
| 4 | 整理结果折叠行不参与 Daniel 行、不计数 | `['p1', WORK_ROW_ID]`，品牌行 `count: 2`，工作行 `count` 为 `undefined` | 312 |
| 5 | 模块全景按调用计数 | 7 次合并后「品牌资产」仍 `calls: 7` | 326 |
| 6 | 跨任务重置计数 | 任务 1 里 `count: 3` → 新人类消息后 `steps: []` → 新任务第一次调用 `count` 为 `undefined` | 335 |
| 7 | 次数显示（渲染） | 合并行 `[data-count="7"]` 文本 `×7`；单次行无 `[data-count]`、文本无 `×`；`aria-label` 末尾为 `，×7` | 358 |
| 8 | 用户真实形态 = 2 行 | 1 次工作区 + 7 次品牌档案 + 1 次工作区 → 2 行；`aria-label` 分别为 `…已完成，×2` / `…已完成，×7`；全景 2 / 7 | 380 |
| 9 | 状态聚合 | 两次同名调用：未返回时 `{count:2,status:'running'}`；返回一次仍 `running` 且 `running: true`；两次都返回 `{status:'done',count:2}`、`{running:false,current:null}` | 406 |
| 10 | 状态不回退 | 已完成后重复 `tool/result`、重复 `tool/call` → 仍 `done`、`count` 不变、`running: false` | 422 |
| 11 | 「当前」= 最新发起的未完成调用 | 后发起的行占 `current`；另一行 `status: 'running'`；两行时 `current.id` 为后发起那行 | 441 |
| 12 | 乱序完成不改顺序 | 先发 A 后发 B、B 先回 → 行序仍 `['a1','b1']`，状态 `['running','done']`，`current` 回到 A | 466 |
| 13 | `turn/end` 收尾缺结果的调用 | 两条在飞、只回一条，`turn/end` 后两行都 `done`、`running:false`、`current:null`；迟到结果不改 | 484 |
| 14 | 跨任务清空指针 | 新任务后 `{task:1,running:false,current:null,steps:[]}`；新调用成为 `current` | 501 |
| 15 | 300ms 稳定窗口（假定时器） | 窗口内新调用不抢指针（50ms、299ms 两次断言）；301ms 后新行接管，且不再回跳 | 514 |
| 16 | 20 次快速事件后行节点不变 | `stepRows(panel)[0]` 与更新前**同一 DOM 节点**（`===`）；仍 1 行；`data-count="20"`；通知次数 ≤ 第 6 次 + 合并后 1 次 | 541 |
| 17 | 淡入只在重置出现一次 | 打开 `data-enter="on"` → 200ms 后消失；任务内更新不出现；重置后出现一次、再消失 | 575 |
| 18 | `prefers-reduced-motion` 无动画 | `data-enter` 不出现；运行节点的 `data-pulse="off"` | 599 |

新增条数 18 ≥ 要求的 6；其中 1–8 覆盖合并/位置/次数/跨任务，9–10 覆盖状态聚合，11–15 覆盖「当前」与乱序，16–18 覆盖闪烁。

### 4.2 既有 79 条

```
 ✓ packages/client/ui-capability-map/tests/trace.client.spec.tsx        (17 tests)
 ✓ packages/client/ui-capability-map/tests/trace-filter.client.spec.tsx (11 tests)
 ✓ packages/client/ui-capability-map/tests/capability-map.client.spec.tsx (16 tests)
 ✓ packages/client/ui-capability-map/tests/guide.client.spec.tsx        (18 tests)
 ✓ packages/client/ui-capability-map/tests/next-steps.client.spec.tsx   (17 tests)
```

**一处既有用例的 fixture 必须改（已改，透明说明）**：`trace.client.spec.tsx` 的「renders at most the newest 24 steps but keeps counting every module call」原来用 **30 次完全相同的 `brands list`** 来造 30 行；按新的合并键这 30 次就是 **1 行**，与「24 行窗口」的前提冲突。改法**不是放宽断言**，而是把 fixture 换成 **30 个不同的业务动作**（从 `MODULE_MAP.commands` 取不同的 `module + action`，各调一次），继续断言：可见步骤 24 行、首行 `c6`、末行 `c29`、各模块调用数与总和 30。原意（窗口截断 + 按调用计数）完全保留；「合并后的行仍按调用数计入模块全景」由新增第 5 条覆盖。其余 78 条**未改一字**，全绿。

### 4.3 验收 ①：用户这次的形态（1 次工作区 + 7 次品牌档案 + 1 次工作区）

用真实事件序列喂折叠并**真渲染** `TraceRail` 后读 DOM（修复前是 1 + 7 + 1 = 9 行）：

```
步骤行数：2
  1. 读取工作区清单，账号与工作区，已完成，×2
  2. 查看品牌档案，品牌资产，已完成，×7
本节可见文本：本次任务已完成上次查看品牌档案已完成读取工作区清单账号与工作区×2已完成查看品牌档案品牌资产×7已完成
任务状态：done（current=null）
账号与工作区调用数：2
品牌资产调用数：7
```

按可见结构写出来：

```
本次任务                                        已完成
● 上次  查看品牌档案  已完成
   1. ✓  读取工作区清单        账号与工作区  ×2  已完成
   2. ✓  查看品牌档案          品牌资产      ×7  已完成
```

（末行原始文本是 `textContent` 去空白，内联元素之间没有空格；`×2 / ×7` 就是 `×N` 那一段弱化文字。）

### 4.4 验收 ②：状态聚合的断言原文

```ts
it('stays 进行中 while one call of the row is in flight and settles when all are done', () => {
  const { trace, session, stop } = liveTrace()
  session.push(toolCall('p1', PROFILE.tool, PROFILE.args))
  session.push(toolCall('p2', PROFILE.tool, PROFILE.args))
  expect(trace.getSnapshot().steps[0]).toMatchObject({ id: 'p1', count: 2, status: 'running' })

  session.push(toolResult('p1'))
  expect(trace.getSnapshot().steps[0]).toMatchObject({ status: 'running' })
  expect(trace.getSnapshot().running).toBe(true)

  session.push(toolResult('p2'))
  expect(trace.getSnapshot().steps[0]).toMatchObject({ status: 'done', count: 2 })
  expect(trace.getSnapshot()).toMatchObject({ running: false, current: null })
  stop()
})
```

同一序列在验收脚本里的运行输出（三条状态被逐个打印）：

```
两次同名调用尚未返回：count=2 status=running running=true
只返回一次：count=2 status=running running=true
两次都返回：count=2 status=done running=false current=null
```

### 4.5 门禁真实输出

```bash
$ export PATH="/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/build/toolchain/node24/bin:$PATH"
$ cd /tmp/dsh-build/dsh-src

$ pnpm exec tsc -b tsconfig.client.json
TSC_EXIT=0

$ pnpm -C apps/desktop run build
$ tsc -b && pnpm run bundle
…
✔ Build complete in 78ms
✔ Build complete in 122ms
✓ built in 416ms
DESKTOP_BUILD_EXIT=0

$ pnpm -C packages/client/ui-capability-map run bundle
ℹ [@deepseek-ai/dsh-client-ui-capability-map/client] [CJS] lib/client.js      106.13 kB │ gzip: 27.36 kB
ℹ [@deepseek-ai/dsh-client-ui-capability-map/client] [CJS] lib/client.js.map  146.64 kB │ gzip: 39.14 kB
ℹ [@deepseek-ai/dsh-client-ui-capability-map/client] [CJS] 2 files, total: 252.77 kB
✔ [@deepseek-ai/dsh-client-ui-capability-map/client] Build complete in 42ms
BUNDLE_EXIT=0

$ pnpm exec vitest run packages/client/ui-capability-map
 ✓ |thread-safe| packages/client/ui-capability-map/tests/trace.client.spec.tsx (17 tests)
 ✓ |thread-safe| packages/client/ui-capability-map/tests/next-steps.client.spec.tsx (17 tests)
 ✓ |thread-safe| packages/client/ui-capability-map/tests/trace-filter.client.spec.tsx (11 tests)
 ✓ |thread-safe| packages/client/ui-capability-map/tests/trace-dedupe.client.spec.tsx (18 tests)
 ✓ |thread-safe| packages/client/ui-capability-map/tests/capability-map.client.spec.tsx (16 tests)
 ✓ |thread-safe| packages/client/ui-capability-map/tests/guide.client.spec.tsx (18 tests)

 Test Files  6 passed (6)
      Tests  97 passed (97)
VITEST_EXIT=0
```

（97 = 既有 79 + 新增 18。改动的 `TraceStep` 只新增**可选** `count?`，单次调用的快照形状与旧精确断言逐字节一致；`trace.client` 里 `toEqual` 的整快照断言未改仍通过。）

---

## 5. 改动文件

| 文件 | 改动 |
|---|---|
| `packages/client/ui-capability-map/src/client/trace.ts` | 新增 `mergeKey()` / `rows` 表 / `count`；`TraceStep.count?`；`StartedCall`（seq + settled）与逐调用 `settle()`；`pickCurrent()`（最新发起未完成 + `CURRENT_HOLD_MS`）；`publish()` 按调用计模块次数并带 `count`/`current` 进签名；`notify()` 风暴合并（`BURST_PUBLISH_LIMIT` / `PUBLISH_COALESCE_MS`）；`beginTask()` / `forget()` 清 `rows`、指针与合并定时器；文件头注释更新 |
| `packages/client/ui-capability-map/src/client/TraceRail.tsx` | 任务块 `data-enter` 标记（只在重置后 200ms 出现，`reduced` 时不出现）；行右侧 `×N`（`data-count`、`aria-label` 带次数）；行 key 注释明确「首调 id」 |
| `packages/client/ui-capability-map/src/client/CapabilityMap.module.css` | `.task[data-enter='on']` 才播 `taskFade`；新增 `.stepCount`（10px、弱化色、tabular-nums、无徽章）；reduced-motion 选择器同步 |
| `packages/client/ui-capability-map/src/client/locales.ts` | 新增 `task.step.times`（zh / en 均为 `×{count}`） |
| `packages/client/ui-capability-map/tests/trace-dedupe.client.spec.tsx` | **新增 18 条**（合并 / 次数 / 状态 / 跨任务 / 当前指针 / 乱序 / 收尾 / 稳定窗口 / DOM 节点 / 淡入 / reduced-motion） |
| `packages/client/ui-capability-map/tests/trace.client.spec.tsx` | 只改「24 行窗口」那条的 fixture（30 次同名 → 30 个不同业务动作），断言强度不变 |
| `packages/client/ui-capability-map/lib/*` | `tsc -b` 与 `bundle` 产物（构建生成，非手改） |

未新增依赖、未新增网络请求、未改模块映射数据。

---

## 6. 已知边界（汇总）

1. **`A → B → A` 合并**：位置取第一次、次数 2；两次 A 之间的停顿在行上看不见（§1.6.1）。要看逐条时间线，右侧对话记录仍在。
2. **兜底行只按紧邻合并**：无法命名的 Daniel 调用没有业务身份，不相邻就不并（§1.6.2）。
3. **24 行窗口**：合并减少行数，但窗口上限仍是 24；当前行若滚出窗口，顶部「进行中 + 动作」仍显示它，列表里没有对应行（避免把旧行硬钉在窗口里）。
4. **指针最多滞后 300ms**：稳定窗口的代价；只在「它坐的行已经结束」时才立即移动。
5. **风暴合并的代价**：一窗内第 7 次起的发布最多延迟 80ms 到达界面；快照与 `getSnapshot()` 始终最新。
6. **只按任务/会话**：跨任务重新计数，不落盘、不跨会话。
7. **oxlint**：对本次改动的 `trace.ts` / `locales.ts` 无告警；`TraceRail.tsx` 的 `arrow-parens` 落在未改动的模块全景行上（既有问题，不在本次三条硬门禁内）。
