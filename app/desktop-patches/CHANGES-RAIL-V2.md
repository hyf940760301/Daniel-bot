# CHANGES · 左栏重做：Daniel 能力全景 + 执行透视（S6.4 · 只读 · 按模块 · 每任务重置）

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，基线 `ce7073d5`，已含品牌/登录/主题与上一版能力地图/执行轨迹）
> 改动包：`packages/client/ui-capability-map`（既有包内重做，不新增包、不新增运行时依赖）
> 状态：**类型检查 / 桌面构建 / 客户端 bundle / 单测全绿；未打包**
> 一句话：左栏从「九阶段静态能力清单 + 阶段轨迹」改成「本次任务的步骤路径 + 九个 Daniel 模块的使用全景」，按调用 id 去重、按人类用户消息重置，只读、默认收起 48px、展开 320px。

---

## 0. 用户已裁决的四条（本版不变）

1. 全景按 **Daniel 模块**分组（不是业务意图、不是内部阶段名）。
2. **每个任务重置**（新任务开始 → 清空路径）。
3. **不提供技术视图开关**（没有任何显示原始工具名 / 模块 id 的入口）。
4. **只读**：不能点击发起任务、不能触发任何调用；只有「展开 / 收起面板」与「滚动」可用。

补充范围调整（用户中途追加）：左栏**不再渲染静态能力清单**（模块下的全部动作/命令）。左栏只保留两块：

- 本次执行的步骤列表（模块 + 业务动作 + 状态）；
- 9 个模块的状态行（未用 / 使用中 / 已用 + 次数）。

映射数据仍完整保留在生成物 `module-map.generated.ts`（模块 → 动作 → 覆盖命令），供下一步的独立「Daniel 全景地图指引」弹窗复用；左栏不读它的动作清单。

---

## 1. 模块裁剪依据（构建期，不在运行期读工作区文件）

输入：`daniel-bot/app/workflow-map.json`（`daniel.workflow-map.v1`，10 个 workflow / 91 条 command）。
输出：`src/client/module-map.generated.ts`（已入库；浏览器包不读任何工作区文件）。

```bash
node packages/client/ui-capability-map/scripts/build-module-map.mjs \
  --from "/Users/…/daniel-bot/app/workflow-map.json"
# → wrote …/module-map.generated.ts
#   modules 9 · actions 51 · commands 52/91
```

### 1.1 对外模块表

| 对外模块 | 来源 `module` | 动作数 | 覆盖命令 |
|---|---|---:|---:|
| 账号与工作区 | 账号与工作区 | 10 | 11（含 `workspaces list` 别名） |
| 品牌资产 | 品牌资产 | 7 | 7 |
| 红人检索 | 红人检索、检索词清单 | 4 | 4 |
| 红人名单 | 红人名单 | 8 | 8 |
| 真实性与背调 | 真实性核验（改名） | 2 | 2 |
| 合作追踪 | 合作追踪 | 8 | 8 |
| 品牌提及 | 品牌提及 | 4 | 4 |
| 内容情报 | 内容情报 | 4 | 4 |
| 声量份额 | 声量份额 | 4 | 4 |
| **合计** | | **51** | **52** |

### 1.2 裁剪规则

1. **只发布九个业务模块**，顺序即产品序。两个来源模块做业务归并：「检索词清单」并入红人检索（它本就是检索质量的一部分）；「真实性核验」对外改名为真实性与背调。
2. **隐藏全部运维/基建模块**：`工序契约 / 宿主接入 / 安装向导 / 出包 / 命令清单 / 数据通路 / 接管验收 / 口径一致性 / 业务语料 / 授权 / 调度 / 需求入口 / 澄清`。生成期用 `OPS_MODULES` 闭集断言：这些模块的命令一条都不许出现在对外查表里；并断言每个源 `module` 要么归入九个业务模块、要么在运维闭集里，新增一个未归类模块会直接失败。
3. **发布判据从 `internal` 标志 / `workflow.id` 改为 `module` 列**。这是本版必须改的一条：`账号与工作区` 的 10 条命令在源数据里都是 `internal: true` 且 `workflow.id: ops`，但用户要求它出现在全景里，所以不能再按 `internal` 过滤。反过来，运维模块即使某些行 `internal` 不是 true 也必须剔除——模块口径比行内标志更可靠。
4. **`澄清` 模块不发布，但追问类工具仍要可读**：`daniel_clarify` / `daniel_screen_ask` 走工具规则落到「红人检索」，而不是把 `clarify plan/ask` 两条命令放进模块表。
5. **每条对外命令恰好一个手写业务动作**；动作名是左栏唯一会显示的文案。生成期断言：
   - 对外模块 ≤ 10（实际 9）；
   - 九个模块每个至少 1 个动作、每个动作至少 1 条覆盖命令；
   - 动作文案不得含英文字母、`_`、`--`、`.ts`／`.json`、反引号；
   - 运维模块命令不得出现在对外映射里；
   - 覆盖命令总数 = 查表条目数（52），无重复、无过期动作。
6. **兜底句例外**：`fallback.action = "正在调用 Daniel 能力…"` 允许出现产品名 `Daniel`（它不是命令/工具/路径），生成器对兜底句只禁止内部标记；其余业务文案一律禁字母。
7. **被裁掉 40 条源命令**（91 − 51）：全部是运维/基建行（含 2 条 `clarify`）。另有 1 条 `workspaces list` 别名，使对外查表条目为 **52**。

### 1.3 动作名单（供下一步指引弹窗复用）

- **账号与工作区**（10）：查看当前账号、查看账号清单、读取工作区清单、查看账号能力、切换当前账号、重新登录账号、查看操作记录、查看凭据来源、更新本机凭据、查看数据落点
- **品牌资产**（7）：读取品牌列表、查看品牌档案、查看竞品清单、新建品牌、更新品牌资料、复制品牌档案、删除品牌
- **红人检索**（4）：查看检索历史、查看检索进度、发起红人检索、校验检索词
- **红人名单**（8）：查看品牌下的名单、查看名单成员、查看已存频道、查看名单分享状态、查看自动优先级、新建名单、名单改名、删除名单
- **真实性与背调**（2）：核对粉丝真实性、查看评分权重
- **合作追踪**（8）：查看合作活动、查看活动统计、查看订单明细、查看共创视频、解析频道、查看频道兴趣画像、新建合作活动、删除合作活动
- **品牌提及**（4）：查看提及任务、查看提及进度、查看视频评分、发起提及分析
- **内容情报**（4）：查看待办动作、查看追踪关键词、查看选题、查看内容审核单
- **声量份额**（4）：查看声量总览、查看品类竞争、查看品牌视频、发起曝光采集


---

## 2. `daniel_run` 解析规则

真实工具不是 `brands_list` 这样的一个命令一个工具，而是：

- `daniel_run`：通用只读直通，参数 `argv: string[]`（如 `["workspaces","list"]`）；
- `daniel_batch`：一次多条只读命令，参数 `calls: string[][]`；
- `daniel_write_plan` / `daniel_write_commit`：两段式写链；
- 以及 `daniel_brands_list` / `daniel_brand_view` / `daniel_brand_count` / `daniel_kol_profile` / `daniel_roster_search` / `daniel_screen_ask` / `daniel_clarify` / `daniel_status` / `daniel_login` 等专用工具。

### 2.1 解析顺序（`src/client/trace.ts: describeToolCall`）

1. `daniel_batch` → 逐条解析 `calls`：
   - 只有一条 → 用该条动作；
   - 多条且所有可解析调用落在**同一模块** → 该模块 + 「批量读取多项数据」；
   - 多条但模块不一致 → 模块为 `null` + 「批量读取多项数据」；
   - 一条都解析不出 → 兜底。
2. `daniel_run` / `daniel_write_plan` 且参数里有 `argv` → `commandToken(argv)`：
   - **跳过所有以 `-` 开头的片段**（`--json`、`--workspace`、`--refresh` 等）；
   - 取**前两个非开关片段**、转小写、空格连接，得到 `<group> <subcommand>`；
   - 例：`["workspaces","list"] → "workspaces list"`；`["account","workspaces","--with-quota"] → "account workspaces"`；`["--json","brands","list","--workspace","90002"] → "brands list"`。
3. 专用工具 → 命令桥 `toolCommands`（`daniel_brands_list → brands list`、`daniel_brand_view → brands show`）→ 再查命令表。
4. 专用工具 → 工具规则 `toolRules`（`daniel_roster_search`、`daniel_kol_profile`、`daniel_screen_ask`、`daniel_clarify`、`daniel_brand_count`、`daniel_status`、`daniel_login`、`daniel_write_plan`、`daniel_write_commit`）。
5. 仍未命中 → 兜底：
   - `daniel_*` → 模块 `null`（UI 标「其他能力」）+ 「正在调用 Daniel 能力…」；
   - 其它工具（如 `bash`）→ 模块 `null` + 「正在处理…」。
   - **任何路径都不返回模型写的命令、参数或结果。**

### 2.2 别名

`workspaces list` 是任务里的验收例子，而当前 CLI 同一读取写作 `account workspaces`。生成器用 `ALIASES` 把 `workspaces list` 指到既有的「账号与工作区 · 读取工作区清单」，并断言别名只能指向已存在的动作，不能凭空造模块。查表结果两者完全一致。

`--flag` 的取值不单独识别：真实调用都把命令放在开关之前，因此取前两个非 `-` 片段足够；如果未来出现 `["brands","--workspace","90002","list"]` 这种把开关插进子命令中间的写法，会解析成 `brands 90002` 并落兜底，不会误报成别的动作。

---

## 3. 去重：一个 tool call id 只产生一行

实现位置：`src/client/trace.ts`

- `private readonly calls = new Map<string, FoldedCall>()`（按调用 id 建 Map）；
- `start(id, tool, raw)` 第一行 `if (this.calls.has(id)) return`（`trace.ts:412`）：`tool/call` 插入「进行中」；
- `case 'tool/result'`（`trace.ts:387`）：用 `event.data.message.source.callId` 找到同一条记录，**就地**把 `status` 改成 `done`；找不到（窗口里只有结果、没有开始）就忽略，不补行；
- `order` 只保存首次插入的那条记录；`publish()` 投影时一条记录只产出一个 `TraceStep`。

因此同一次调用无论轨迹里出现几次 `tool/call`（重放、窗口替换、渲染抖动），都只有一行。单测 `deduplicates one call id into exactly one row, updated in place` 覆盖：开始 → 再开始（snapshot 引用不变）→ 结果 → `steps.length === 1`。

---

## 4. 每任务重置：事件依据与口径

### 4.1 采用的事件

只从会话持久事件窗口读四种事件（都在 `packages/core/session/src/types.ts`）：

| 事件 | 定义位置 | 本版用法 |
|---|---|---|
| `tool/call` | `packages/core/session/src/types.ts:369` | 起一步（进行中） |
| `tool/result` | `packages/core/session/src/types.ts:383` | 按 `callId` 就地收尾 |
| `user/message` | `packages/core/session/src/types.ts:315` | **任务边界**：人类用户消息 → 清空路径 |
| `turn/end` | `packages/core/session/src/types.ts:303` | 只把仍在跑的调用收尾，**不清空** |

「人类用户消息」的判据来自消息源类型：`packages/llm/llm/src/message.ts:111` 定义 `user: { kind: 'user' }`。`user/message` 这个事件同时承载 `agent.inject()` 的合成内容（文件变更通知、AGENTS.md、cron 提醒等），所以不能见到 `user/message` 就重置；只有 `source.kind === 'user'` 才算新任务。

折叠代码：

- `trace.ts:392` `case 'user/message': if (isHumanPrompt(event.data)) this.beginTask()`
- `trace.ts:350` `beginTask()`：`task += 1`，清空 `calls` 与 `order`；
- `trace.ts:395` `case 'turn/end'`：把所有调用置 `done`，保留路径；
- 会话切换 / 收起面板：`forget()` 清空并回到 `EMPTY_TRACE`。

### 4.2 为什么不用 `turn/end` 当重置点

`turn/end` 只说明「这一轮结束」，不代表用户开始了新任务；如果在这里清空，用户刚看完执行结果、面板就变空，看不到「上次做了什么」。所以本版：

- **新任务**：人类 `user/message`；
- **任务结束**：`turn/end` 只收尾，路径保留，标题改为「上次 … 已完成」；
- **新任务的第一条工具调用**：在已经清空的路径上重新起一行；
- **会话切换/收起**：整块忘记。

### 4.3 重放口径

面板收起时不订阅；再次展开时事件窗口可能是 `replace`，折叠会从头重放。由于人类用户消息会重置，重放结束时只留下**最新任务**的步骤；分页 `prepend` 进来的更老历史（`seq` 小于已读游标）不会把面板拉回旧任务。单测 `replays only the newest task when the window is replaced` 覆盖。

### 4.4 任务切换的视觉重置

`TraceRail` 的 `<section key={trace.task}>` 在 `task` 递增时重新挂载，CSS `taskFade 180ms ease-out` 让整块淡入；`data-task` 同时暴露给测试。`prefers-reduced-motion` 下 `animation: none`。

---

## 5. UI：只剩两块，且只读

### 5.1 结构

展开后的 320px 面板：

1. 标题「执行透视」+ 副标题「Daniel 能力全景 · 跟随当前任务」；
2. **本次任务**：`上次 / 进行中` 一行 + 步骤路径（每条 = 业务动作 + 右侧模块标签 + 状态）；
3. **Daniel 能力全景**：固定 9 行，圆点 + 模块名 + 次数 + 状态；
4. 底部只读说明。

没有搜索框、没有阶段折叠、没有静态能力清单、没有技术视图开关。面板内唯一的 `<button>` 是收起按钮；控件之外没有任何 `onClick` 业务路径。

### 5.2 视觉要点

- **当前步骤最突出**：`14px / 600`，左侧实心品牌色圆点 + 呼吸脉冲；已完成步骤 `12px`、`label-tertiary` 降饱和、节点内对勾；未开始的步骤不渲染。
- **竖向进度线**：每行 `::before` 连接下一节点；已完成段 `--dsw-alias-state-business-primary`，进入当前节点的一段是品牌色→描边色的 `linear-gradient`，仍在等待的尾段是 `--dsw-alias-border-l2`。
- **模块标签**：每条步骤右侧 `10px`、`label-caption`，最大宽度 42%，不与动作文字抢戏。
- **模块状态行**：未用 = 空心描边圆点；使用中 = 实心品牌色 + 脉冲；已用 = 实心品牌色 + 对勾；右侧次数 `10px` 等宽数字，状态文字 `10px`，没有彩色徽章墙。
- **任务切换**：180ms 淡入（位移 2px），不是闪。
- **颜色**：全部 `--dsw-*` token（另有框架的 `--dsh-frame-top-clearance` 只用于顶部避让，不是颜色）；单测扫 CSS，断言没有 hex / `rgb()` / `hsl()`，颜色声明必须带 `var(--dsw-` 或 `transparent`。
- **动效**：纯 CSS，没有动画库；`prefers-reduced-motion: reduce` 下淡入与脉冲都为 `none`，同时 JS 侧的 `data-pulse` 直接输出 `off`（双层保证）。
- **只读**：面板无 `<a>`、无 `[role="link"]`、无 `[data-command]`；`fetch` / `WebSocket` 在渲染与点击文本时都不会被调用（单测 stub 断言）。

### 5.3 收起 / 展开

宽度仍由框架的 `computeColumns` 统一解算：收起 48px、展开 320px，窄屏先让 rail 降级。组件在 `data-rail-width` 上暴露 `48` / `320` 作为测试与验收锚点，但真正占宽的是轨道。

---

## 6. 测试证据

```text
$ node_modules/.bin/vitest run packages/client/ui-capability-map

 ✓ |thread-safe| packages/client/ui-capability-map/tests/trace.client.spec.tsx (17 tests) 22ms
 ✓ |thread-safe| packages/client/ui-capability-map/tests/capability-map.client.spec.tsx (16 tests) 323ms

 Test Files  2 passed (2)
      Tests  33 passed (33)
```

覆盖与任务要求逐条对应：

| 要求 | 测试 |
|---|---|
| `daniel_run` 映射 | `resolves daniel_run argv, ignoring flags and keeping the first two tokens`、`carries the worked example command as an alias of the account read` |
| 去重 | `deduplicates one call id into exactly one row, updated in place` |
| 任务重置 | `clears the path on a new human message but keeps the finished path on turn/end`、`replays only the newest task when the window is replaced` |
| 模块状态 | `counts calls per module and derives 未用 / 使用中 / 已用`、`marks the running step as current and its module as 使用中` |
| 兜底文案 | `falls back to business copy and never to the model's arguments`、`labels an unplaceable Daniel call as 其他能力 without lighting a module` |
| 只读 | `issues no request and exposes no action affordance`、`is controlled and expands into the 320px read-only panel` |
| 收起零订阅 | `renders only the collapsed 48px strip on mount and holds no subscription`、`subscribes only while the panel is open` |
| 深浅色不写死颜色 | `uses only theme tokens for colour and keeps the reduced-motion rule` |
| reduced motion | `turns the pulse off under prefers-reduced-motion` |
| 不渲染静态清单 | `does not render a static capability catalogue` |
| 任务切换淡入 | `fades in a fresh task block when the task ordinal changes` |

> 33 条是重写后的全量（旧 29 条里按阶段/搜索的用例已随静态清单删除），其中上表 13 条直接对应本次要求，超过「新增 ≥ 8 条」。

---

## 7. 门禁真实输出

```text
$ node_modules/.bin/tsc -b tsconfig.client.json
TSC_EXIT=0

$ pnpm -C packages/client/ui-capability-map run bundle
BUNDLE_EXIT=0
lib/client.js      53.44 kB │ gzip: 13.56 kB

$ pnpm -C apps/desktop run build
DESKTOP_BUILD_EXIT=0
✓ built in 406ms
```

- 未新增依赖（`package.json` 的 `dependencies` 未动，`scripts` 仅把 `map:build` 指向新生成器）。
- 未打包（按纪律）。

---

## 8. 验收：一条真实渲染文本

模拟 `daniel_run ["workspaces","list"]`，用一个临时 demo spec 经真实 `CapabilityTrace` 折叠、真实 `CapabilityMap` 渲染后，从 DOM 逐行读出的文本（demo 已删除，不留在仓库）：

**调用进行中：**

```text
执行透视 — Daniel 能力全景 · 跟随当前任务
本次任务
  进行中 读取工作区清单
  ● 读取工作区清单，账号与工作区，进行中
Daniel 能力全景
  ● 账号与工作区   1 次   使用中
  ○ 品牌资产   未用
  ○ 红人检索   未用
  ○ 红人名单   未用
  ○ 真实性与背调   未用
  ○ 合作追踪   未用
  ○ 品牌提及   未用
  ○ 内容情报   未用
  ○ 声量份额   未用
  只读：只反映执行进度，不发起任何调用。
```

**同一调用回结果后：**

```text
执行透视 — Daniel 能力全景 · 跟随当前任务
本次任务    已完成
  上次 读取工作区清单 已完成
  ✓ 读取工作区清单，账号与工作区，已完成
Daniel 能力全景
  ● 账号与工作区   1 次   已用
  ○ 品牌资产   未用
  ○ 红人检索   未用
  ○ 红人名单   未用
  ○ 真实性与背调   未用
  ○ 合作追踪   未用
  ○ 品牌提及   未用
  ○ 内容情报   未用
  ○ 声量份额   未用
  只读：只反映执行进度，不发起任何调用。
```

去重证据（同一 demo 内，同一 id 再发一次 `tool/call`）：

```text
=== DEDUPE (start twice + result once) ===
steps=1 rows=1 step={"id":"call-1","module":"账号与工作区","action":"读取工作区清单","status":"done"}
```

---

## 9. 改动文件

| 文件 | 作用 |
|---|---|
| `packages/client/ui-capability-map/scripts/build-module-map.mjs` | 新生成器：九模块裁剪、动作闭集、别名、运维模块断言 |
| `.../src/client/module-map.generated.ts` | 生成物：9 模块 / 51 动作 / 52 命令（含别名） |
| `.../src/client/types.ts` | 模块表契约（`ModuleAction` / `ModuleDefinition` / `ModuleRule` / `ModuleMapData`） |
| `.../src/client/trace.ts` | 折叠：argv 解析、工具桥/规则、去重、每任务重置、模块计数 |
| `.../src/client/TraceRail.tsx` | 本次任务路径 + 九模块全景 + 只读 + reduced-motion 钩子 |
| `.../src/client/CapabilityMap.tsx` | 48px 竖条 / 320px 面板、焦点、Esc、只读说明 |
| `.../src/client/CapabilityMap.module.css` | 全部 `--dsw-*` token、进度线、脉冲、淡入、reduced-motion |
| `.../src/client/locales.ts` | 新词典（任务/全景/模块状态），删除搜索/阶段键 |
| `.../src/client/index.ts` | 导出新契约；注册不变 |
| `.../tests/trace.client.spec.tsx` | 17 条：模块表、解析、兜底、去重、重置、计数、会话切换 |
| `.../tests/capability-map.client.spec.tsx` | 16 条：收起零订阅、只读、两块结构、视觉锚点、reduced-motion、token |
| `.../README.md` / `README.zh.md` / `README.i18n.yaml` / `locale/{zh,en}.json` | 包文档与元数据同步 |
| `.../package.json` | `map:build` 指向新生成器；描述更新 |

**删除**（静态清单退场，避免死代码）：

- `scripts/build-capability-map.mjs`
- `scripts/build-trace-map.mjs`
- `scripts/stages.mjs`
- `src/client/capability-map.generated.ts`
- `src/client/trace-map.generated.ts`

---

## 10. 已知限制

- 左栏跟主视图会话；后台会话/子代理不显示。
- 多命令 `daniel_batch` 只占一行，只给共享模块记一次；分属不同模块时不点亮任何模块（避免把一次批量调用算成多次）。
- 若事件窗口只加载了某任务的后半段（人类消息不在窗内），重放无法知道任务边界，会把窗内调用当成当前任务；这是「只读已加载窗口」的边界，不做额外推测。
- 模块表是构建期快照；工作流地图变更后必须重新生成，否则左栏还是上一版动作。
