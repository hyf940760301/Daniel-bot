# CHANGES · 轨迹降噪：只有 Daniel 能力调用成行，内部动作折叠成一行「整理结果」

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，基线 `ce7073d5`，已含品牌/登录/主题/能力全景与执行透视）
> 改动包：`packages/client/ui-capability-map`（既有包内改，不新增包、**不新增运行时依赖**、不新增请求）
> 状态：**类型检查 / 桌面构建 / 客户端 bundle / 单测全绿；未打包（按纪律）**
> 一句话：一次任务里只有 **Daniel 能力调用**（`daniel_*` 里能落到九个业务模块的那些）成为步骤；bash / 文件读写 / python / skill / web 这类**内部动作不再各占一行**，而是折叠成当前任务的**一行「整理结果」**，状态随执行在「进行中 → 已完成」之间变化，不显示次数；全程没有 Daniel 调用时，明写「本次未调用 Daniel 能力」。

---

## 0. 用户裁决的七条规则 → 实现落点

| # | 规则 | 实现落点 |
|---|---|---|
| 1 | 只有 Daniel 能力调用成为一步 | `trace.ts:483` `start()`：`isDanielTool(tool)` 为真才走 `danielRow()`；否则走 `foldedRow()` |
| 2 | 非 Daniel 工具不单独成行，折叠成当前任务的一行「整理结果」，状态随执行变化 | `trace.ts:57`（行 id）、`trace.ts:64`（行文案）、`trace.ts:529` `foldedRow()`、`trace.ts:318`（`open` 在飞计数）、`trace.ts:543`（状态派生） |
| 3 | 不显示次数（选 A）：只写「整理结果」 | 行文案是常量 `WORK_ROW_ACTION`，不含 `N`、不含「步」「次」；测试 `trace-filter.client.spec.tsx:429` 断言 |
| 4 | 连续多次内部动作合并成同一行，不追加 | `foldedRow()` 先返回 `this.work`（`trace.ts:529-536`），只有第一笔内部动作会 `push` 进 `order` |
| 5 | 全程无 Daniel 调用 → 显示「本次未调用 Daniel 能力」 | 判据 `TraceRail.tsx:77`；文案 `locales.ts:26 / 74`；渲染 `TraceRail.tsx:157-159`；样式 `CapabilityMap.module.css:248` |
| 6 | 任务重置逻辑不变（新的人类消息清空） | 规则未动：`isHumanPrompt()` + `beginTask()`（`trace.ts:415`），新消息把 `calls / order / work` 一起清掉（`trace.ts:419`） |
| 7 | 兜底：`daniel_*` 但映射不到，仍保留「正在调用 Daniel 能力…」一行（可合并连续同类） | `trace.ts:501` `danielRow()`：模块为 null 且命中兜底文案时，若紧邻上一行也是同类兜底行则复用，否则新开一行 |

---

## 1. 判据：什么算「非 Daniel 工具」（按工具名，不按参数猜）

### 1.1 只读一个字段

折叠只读持久事件 `tool/call`（类型定义 `packages/core/session/src/types.ts:369`：`{ turn, step, callId, name, arguments }`）里的 **`name`**。

`arguments` 仍然只用于**已经判定为 Daniel** 的调用去做命令解析（`daniel_run` 的 `argv`、`daniel_batch` 的 `calls`），**绝不**用来判断"这次调用是不是 Daniel"。

### 1.2 判据（`trace.ts:278-283`）

一次调用算 Daniel 能力，当且仅当**工具名**满足其一：

1. 以 `daniel_` 开头（Daniel 能力工具的命名空间，`trace.ts:54`）；
2. 或出现在随包生成的 Daniel 工具表里：
   - 命令桥 `MODULE_MAP.toolCommands`（`module-map.generated.ts:596`，当前 2 条：`daniel_brands_list` → `brands list`、`daniel_brand_view` → `brands show`）；
   - 直接规则 `MODULE_MAP.toolRules`（`module-map.generated.ts:600`，当前 9 条）。

第 2 条是给"已注册工具清单"兜的口：将来若有非 `daniel_` 前缀的 Daniel 工具，只要进了这两张生成表，仍按 Daniel 处理；反过来，名字长得像 Daniel 但没进表、也没前缀的，一律按内部动作折叠。

**其余全部算非 Daniel 工具**：`bash`、`read`、`write`、`edit`、`glob`、`grep`、`python`、`skill`、`web_search`、`web_fetch`、`todo_write` 等宿主工具箱里的任何名字。

### 1.3 为什么不用「参数像不像」猜

- `arguments` 是模型写的自由文本（`command`、`path`、`argv`），拿它反推会把"参数里带品牌名"的 bash 误判成 Daniel 调用，也会把"参数写坏了"的 `daniel_run` 误判成内部动作。
- 工具名是宿主登记过的稳定标识，可测试、可审计、不会随模型措辞漂移。
- 单元测试把这一点钉死：`trace-filter.client.spec.tsx:247` 直接断言 `bash / read / write / python / skill / web_search / toString` 为 false，并断言两张生成表里的名字全为 true。

### 1.4 一次调用只有两个出口（旧的第三个出口已关闭）

`start()`（`trace.ts:483-490`）只有两条路径：Daniel → `danielRow()`，其它 → `foldedRow()`。原来 "非 Daniel 工具走 `fallback.generic`（正在处理…）" 的那条出口在 fold 里**不再可达**；`describeToolCall()` 的 `generic` 分支仅对直接调用者保留（既有单测仍覆盖它），折叠链不会走到。

---

## 2. 折叠规则

| 场景 | 行数 | 显示文案 | 状态 |
|---|---|---|---|
| 1 次 Daniel 能力调用 | 1 行 | 模块 + 业务动作（如「读取品牌列表」/「品牌资产」） | 进行中 → 已完成 |
| 1 次内部动作 | 1 行 | 整理结果 | 进行中 → 已完成 |
| 连续 N 次内部动作 | **始终 1 行** | 整理结果（**不写次数**） | 最后一笔在飞时「进行中」，全部结束「已完成」；中间再来一笔会回到「进行中」 |
| 内部动作 → Daniel → 内部动作 | 2 行 | 整理结果 / Daniel 步骤（折叠行只 1 条，不再新增） | 见 §3 |
| `daniel_*` 但映射不到 | 1 行/段 | 正在调用 Daniel 能力… | 同 Daniel 步骤 |
| 连续多个「映射不到」的 Daniel 调用 | 合并 1 行（紧邻才合并） | 正在调用 Daniel 能力… | 最后一条结束才算完成 |
| 全程无 Daniel 调用 | 1 行 + 提示 | 整理结果 + 本次未调用 Daniel 能力 | 已完成 |

### 2.1 一行怎么来的

- 常量：`WORK_ROW_ID = 'work'`（`trace.ts:57`，只作 list key，不渲染）、`WORK_ROW_ACTION = '整理结果'`（`trace.ts:64`）。
- 第一笔内部动作调用 `foldedRow()`（`trace.ts:529`）建行并登记 `this.work`；之后每一笔都返回同一个对象，只把该行从「已完成」重新标记为「进行中」。

### 2.2 状态怎么算（不再按"最后一次结果"猜）

行内用 `open` 记录**这一行还有几笔调用在飞**（`trace.ts:318`）：

- `tool/call`：`open += 1`；
- `tool/result`：`open = max(0, open - 1)`（`trace.ts:457`，重复结果不会把正在飞的另一笔误标完成）；
- `turn/end`：整任务 `open = 0` 收尾（`trace.ts:466`，被中断的调用不会永远「进行中」）；
- 发布时派生：`open > 0 ? 'running' : 'done'`（`trace.ts:543`）。

同一机制也让「连续多个映射不到的 Daniel 调用」能正确停在「进行中」，直到最后一笔结束。

### 2.3 不显示次数、不显示工具名

行的文案是生成侧常量，不含 `N`、不含「步 / 次」、不含任何工具名、命令名、路径或参数。测试 `trace-filter.client.spec.tsx:429-445` 对本节渲染文本做禁用词扫描（`bash / read / write / edit / python / skill / web_search / web_fetch / xlsx / tmp / -- / _ / argv / 含 / 步`，以及 `\d+ 次`）。

### 2.4 模块全景不受污染

折叠行的 `module` 为 `null`，`publish()` 统计模块次数时直接跳过（`trace.ts:548`），所以内部动作**不会点亮任何一个 Daniel 模块，也不会给任何模块加次数**。

---

## 3. 行序：折叠行留在时间顺序里，不堆到末尾

- 折叠行在**第一笔内部动作发生的那一刻**插入 `order`，此后**不再移动**。
- 因此「读品牌清单 → 整理结果 → 输出」就是这三行的时间顺序；后面的 Daniel 步骤一律追加在它之后，**不会**出现"把所有整理结果攒到任务末尾"。
- 混合场景 `Daniel → 内部动作 → Daniel → 内部动作` 的发布结果是 `[读取品牌列表, 整理结果, 第二个 Daniel 步骤]`：后一笔内部动作**更新同一行**（不新增行、也不把行搬到末尾）。测试 `trace-filter.client.spec.tsx:313-332` 断言了这个 id 序列与 `steps.filter(isWorkRow).length === 1`。
- 「不动位置」是有意的：行在用户阅读时来回跳，比位置略早更干扰；而这一行本来就是"本任务的内部工作"的聚合，不是逐次事件。
- 任务重置时折叠行随任务一起消失（`beginTask()` 里 `this.work = undefined`，`trace.ts:419`）；`turn/end` 不清空，只把行收尾为「已完成」。

---

## 4. 「本次未调用 Daniel 能力」：诚实，不编

- 判据（`TraceRail.tsx:77`）：本节已有步骤行，但**没有任何一行**是 Daniel 步骤（即所有行都是折叠行）。
- 渲染（`TraceRail.tsx:157-159`）：步骤列表下方一行弱化提示，文案 `locales.ts:26`（中文）/ `locales.ts:74`（英文），样式 `CapabilityMap.module.css:248`。
- 时机：任务已有内容、且**当下没有在飞的动作**（`state === 'done'`）时才出现——任务刚开头在读文件、跑脚本时不会先闪一句"本次未调用 Daniel 能力"；**随后真的调用了 Daniel 能力，提示立即消失**（测试 `trace-filter.client.spec.tsx:411-427` 用 act 包裹验证运行中不显示、结算后显示、Daniel 结算后消失）。
- 同时九个模块全部保持「未用」——不编造模块归属。
- 空任务（还没有任何调用）不显示该提示，仍显示「等待任务开始」，与旧行为一致。

---

## 5. 测试证据

### 5.1 新增 11 条（`tests/trace-filter.client.spec.tsx`，全部通过）

| # | 用例 | 断言要点 | 行号 |
|---|---|---|---|
| 1 | 判据只看工具名 | `isDanielTool`：`bash/read/write/python/skill/web_search/toString` 为 false；两张生成表里的名字全为 true | 247 |
| 2 | 非 Daniel 工具不产生独立行 | `bash` + `read` 两笔 → 只有 1 行，id=`work`，action=`整理结果`，`module=null`，且行内不含 `ls/tmp/brands.json/bash/read` | 270 |
| 3 | 连续 10 次内部动作只生成 1 条「整理结果」 | 10 笔在飞 → 1 行「进行中」；逐笔结算后仍 1 行「已完成」；文案不含数字/「步」/「次」 | 289 |
| 4 | 混合场景行序正确 | `Daniel → 内部 → Daniel → 内部` → id 序列 `['c1','work','c2']`，action `['读取品牌列表','整理结果','查看声量总览']`，折叠行只有 1 条 | 313 |
| 5 | 折叠行随 turn/end 收尾、随新人类消息清空 | `turn/end` 后 done；`user/message` 后 `task=1, steps=[]`；再来内部动作重新出现 1 行 | 334 |
| 6 | 连续多个「映射不到」的 Daniel 调用合并 1 行 | 3 笔 → 1 行；中途结算不提前变 done，最后一笔结束才 done | 351 |
| 7 | 兜底行不被折叠 | `daniel_skills_read` / 内部动作 / `daniel_skills_list` → id 序列 `['d1','work','d2']`，兜底行文案 `正在调用 Daniel 能力…` | 371 |
| 8 | 真实形态：1 次品牌清单 + 12 次内部动作 = 2 行 | 渲染出 2 个 `listitem`；第 1 行含「读取品牌列表 / 品牌资产」，第 2 行 `data-row="work"`、文本 `整理结果已完成`；全文不含「正在处理…」/「其他能力」 | 391 |
| 9 | 全程无 Daniel 调用 | 内部动作还在跑时不显示；结算后渲染文本含「本次未调用 Daniel 能力」；模块区 0 个 used/active；Daniel 步骤结算后提示消失 | 411 |
| 10 | 文案不含次数、不含工具名/命令名 | 真实形态下扫描 13 个禁用词 + `\d+ 次` + 「整理结果（N…」 | 429 |
| 11 | 折叠行作为已完成的一步保留到任务结束 | `data-state=done`、`上次`、行 `data-status=done`、`data-row=work`、aria-label=`整理结果，已完成` | 447 |

### 5.2 原有 51 条：**0 改动、全绿**

`trace.client.spec.tsx` 17 + `capability-map.client.spec.tsx` 16 + `guide.client.spec.tsx` 18。未改任何既有断言、未放宽任何既有用例（`TraceStep` / `TraceSnapshot` 的形状没变，旧快照 `toEqual` 不受影响）。

---

## 6. 门禁真实输出

```bash
$ export PATH="/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/build/toolchain/node24/bin:$PATH"
$ cd /tmp/dsh-build/dsh-src

$ pnpm exec tsc -b tsconfig.client.json
TSC_EXIT=0

$ pnpm -C apps/desktop run build
$ tsc -b && pnpm run bundle
…
✓ built in 347ms
DESKTOP_BUILD_EXIT=0        # 脚本自身先跑 tsc -b，再 bundle

$ pnpm -C packages/client/ui-capability-map run bundle
ℹ [@deepseek-ai/dsh-client-ui-capability-map/client] [CJS] lib/client.js       88.36 kB │ gzip: 22.28 kB
ℹ [@deepseek-ai/dsh-client-ui-capability-map/client] [CJS] lib/client.js.map  118.96 kB │ gzip: 30.84 kB
✔ [@deepseek-ai/dsh-client-ui-capability-map/client] Build complete in 43ms
BUNDLE_EXIT=0

$ npx vitest run packages/client/ui-capability-map
 ✓ |thread-safe| packages/client/ui-capability-map/tests/trace.client.spec.tsx (17 tests)
 ✓ |thread-safe| packages/client/ui-capability-map/tests/trace-filter.client.spec.tsx (11 tests)
 ✓ |thread-safe| packages/client/ui-capability-map/tests/capability-map.client.spec.tsx (16 tests)
 ✓ |thread-safe| packages/client/ui-capability-map/tests/guide.client.spec.tsx (18 tests)

 Test Files  4 passed (4)
      Tests  62 passed (62)
VITEST_EXIT=0
```

---

## 7. 验收：用户这次的真实形态（1 次品牌清单 + 12 次内部动作）

用真实事件序列喂折叠：`daniel_brands_list`（结算）→ 12 笔内部动作（`bash / read / write / edit / bash / python / skill / web_search / web_fetch / bash / read / write`，参数里带 `/tmp/brands-N.xlsx`）→ `turn/end`，再把 `TraceRail` 真渲染出来读 DOM：

```
   步骤行数：2
   1. 读取品牌列表，品牌资产，已完成   [Daniel 步骤]
   2. 整理结果，已完成   [折叠行]
   本节可见文本：本次任务已完成上次整理结果已完成读取品牌列表品牌资产已完成整理结果已完成
```

（上面末行是 DOM `textContent` 去空白后的原始串，内联元素之间没有空格；按 UI 结构读是：标题「本次任务 / 已完成」→ 实时行「上次 整理结果 已完成」→ 两行步骤。）

按可见结构写出来就是用户会看到的两行：

```
本次任务                                        已完成
● 上次  整理结果  已完成
   1. ✓  读取品牌列表                          品牌资产   已完成
   2. ✓  整理结果                                         已完成
```

**12 次内部动作 = 1 行，整任务 = 2 行**（修复前是 1 + 12 = 13 行「正在处理… / 其他能力」）。

### 7.1 「无 Daniel 调用」场景

同一折叠，3 笔 `bash`（参数带 `node build.js`）后 `turn/end`：

```
   步骤行数：1
   1. 整理结果，已完成
   本节可见文本：本次任务已完成上次整理结果已完成整理结果已完成本次未调用 Daniel 能力
   模块行：账号与工作区未用 | 品牌资产未用 | 红人检索未用 | 红人名单未用 | 真实性与背调未用 | 合作追踪未用 | 品牌提及未用 | 内容情报未用 | 声量份额未用
```

按结构读：

```
本次任务                                        已完成
● 上次  整理结果  已完成
   1. ✓  整理结果                                         已完成
   本次未调用 Daniel 能力
```

九个模块全「未用」——没有任何一行把内部动作包装成 Daniel 能力。

---

## 8. 改动文件

| 文件 | 改动 |
|---|---|
| `packages/client/ui-capability-map/src/client/trace.ts` | 新增 `DANIEL_TOOL_PREFIX` / `WORK_ROW_ID` / `WORK_ROW_ACTION` / `isDanielTool()` / `isWorkRow()`；`FoldedCall.status` 改为在飞计数 `open`；`start()` 分两路（`danielRow()` / `foldedRow()`）；`tool/result`、`turn/end` 按计数收尾；`beginTask()` / `forget()` 清折叠行；`publish()` 派生状态；文件头与 `describeToolCall()` 注释更新 |
| `packages/client/ui-capability-map/src/client/TraceRail.tsx` | 折叠行不加模块标签（`data-row="work"`）；aria-label 不带模块；无 Daniel 步骤时渲染「本次未调用 Daniel 能力」注释 |
| `packages/client/ui-capability-map/src/client/CapabilityMap.module.css` | 新增 `.taskNote`（只用主题 token） |
| `packages/client/ui-capability-map/src/client/locales.ts` | 新增 `task.noDaniel`（zh / en） |
| `packages/client/ui-capability-map/tests/trace-filter.client.spec.tsx` | 新增 11 条用例（折叠 / 行序 / 渲染文本 / 诚实提示） |
| `packages/client/ui-capability-map/lib/*` | `tsc -b` 与 `bundle` 的产物（随构建生成，不是手改） |

未新增依赖，未新增网络请求，未改模块映射数据（`module-map.generated.ts` 未动）。

---

## 9. 已知边界

1. **24 行窗口**：折叠行与 Daniel 步骤共用 `TRACE_STEP_LIMIT = 24`（`trace.ts:45`）。如果它很早就出现、之后又有 24+ 个 Daniel 步骤，它会滚出可见窗口（`publish()` 只保留最新 24 行）。没有把它"钉"在窗口里，是因为那会破坏时间顺序；需要"常驻折叠行"时应单独做粘性行，而不是偷偷改顺序。「上次」行与模块全景始终正确。
2. **按任务聚合，不按批次**：一个任务里所有内部动作只有一行，读文件、写 xlsx、跑脚本在视觉上无法区分——这是用户选 A（不显示次数）的直接后果，也是本次降噪的代价。
3. **紧邻才合并（兜底行）**：连续多个映射不到的 `daniel_*` 合并成一行；中间夹了任何别的行（Daniel 步骤或折叠行）就会另起一行。
4. **前缀是约定**：`daniel_` 前缀来自当前工具命名空间；若将来 Daniel 能力换了命名空间，必须同时进入 `MODULE_MAP.toolCommands` / `toolRules` 才会被认成 Daniel（判据是"前缀 **或** 随包工具表"）。
5. **不跨任务、不跨会话**：折叠行随任务重置清空，不落盘、不持久化（与既有轨迹口径一致）。
6. **提示只在结算后出现**：任务里第一笔是内部动作、随后才调 Daniel 时，Rail 不会先闪一句「本次未调用 Daniel 能力」；只有该任务当下没有在飞动作时才判定并显示。
7. **`describeToolCall()` 的 `generic` 分支**仍在（对导出 API 保留、既有单测覆盖），但折叠链已不会走到它；若有人直接调用该函数，仍可能拿到"正在处理…"——界面不再消费这个结果。

---

## 10. 与既有文档的关系

- 本文只改**"哪些调用成为一行、怎么折叠"**；模块映射（命令 → 业务动作）与九模块裁剪仍按 `CHANGES-RAIL-V2.md` §1–§2 与 `CHANGES-CAPABILITY-MAP.md`，未改动。
- 轨迹的事件来源（`tool/call` / `tool/result` / `user/message` / `turn/end`）、按 `retainedBy.mainView` 取会话、收起不订阅、只读不请求等口径，均沿用 `CHANGES-RAIL-V2.md` §4–§6。
