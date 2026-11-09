# CHANGES · S6.3 执行轨迹（阶段 + 业务动作 · 实时只读）

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，基线 `ce7073d5`，已含品牌/登录/主题/S6.2 能力地图）
> 改动包：`packages/client/ui-capability-map`（既有包内加一节，不新增包）
> 状态：**类型检查 / 桌面构建 / 客户端 bundle / 单测全绿；未打包（按纪律）**
> 一句话：展开能力面板时，顶部多一行**助手正在做什么**——`当前：背调 · 核对粉丝真实性`，下面最多 6 条最近动作与状态；收起时这一节**不渲染也不订阅**。

---

## 1. 数据来源与依据（先侦察，后决策）

### 1.1 三条候选，逐一实测

| 候选 | 源码事实 | 结论 |
|---|---|---|
| 会话作用域的 `useChat`（Chat 快照） | 它挂在 **`SessionStandardProps`** 上：`packages/client/ui-chat/src/client/contract/slots.ts:402`（`useChat: UseChat`），而 `PropsRuntime` 只把 `ScopeStandardProps<ScopeOf<K>>` 拼进 props（`packages/client/ui-slots/src/index.ts:255-262`）。`shell.rail` 的 scope 是 **`root`**（`packages/client/ui-layout/src/client/index.ts:83`），拿不到会话作用域成员。全仓也没有任何插件在 `ui-chat` 之外用过 `useChat` | ❌ 槽位作用域不匹配 |
| 把轨迹做成会话作用域条目再读 store | 会话作用域的座位（`conversation.view` / `conversation.chat.*`）只在会话视图里挂载；面板在 `shell.rail`，两者不在同一棵作用域树里，要跨过去只能自建全局总线或轮询 DOM | ❌ 私接全局／轮询 DOM，任务明令禁止 |
| **Client Session 服务（`ctx.sessions`）的事件窗口** | `ctx.sessions` 是公开服务：`packages/api/session-controller/src/client/index.ts:93`；`list` 给出会话目录与本地引用计数；`binding(id)` 明确写着"借用一个已保留的绑定、不延长其生命周期"（`packages/api/session-controller/src/client/contract/sessions.ts:167`）；绑定上的 `eventSource` 是**与会话视图同源的持久事件窗口**（`contract/events.ts`，`SessionEventWindow`） | ✅ **采用**：服务是公开的、只读的，事件是宿主真正落盘的那份 |

### 1.2 拿"当前会话"的判据

不是猜，也不是取第一个：沿用 Session Controller 自己的规则——**被主视图保留（`retainedBy.mainView > 0`）的那条会话**：

- `packages/client/ui-session/src/client/index.ts:465,468`（`publishMain`：当前绑定若仍是 mainView 保留则用它，否则取第一条 mainView 保留的）
- 本实现：`trace.ts` 的 `currentSessionId()`，同样的口径，只读 `list` 快照，不 retain、不创建 scope、不触发任何 RPC。

### 1.3 拿"正在做什么"的判据

只读三种持久事件，其余一概不看：

| 事件 | 定义 | 用途 |
|---|---|---|
| `tool/call` | `packages/core/session/src/types.ts:369`（`callId` / `name` / `arguments`） | 动作**开始**就出现（这是"实时"的来源，而不是等结果） |
| `tool/result` | `packages/core/session/src/types.ts:383`（`message.source.callId`） | 动作**完成** |
| `turn/end` | 同文件（回合结束） | 回合结束时仍未回结果的调用按"已结束"收尾（中断/取消），不会永远显示"进行中" |
| `assistant/live-chunk`（transient） | 客户端临时帧 | **丢弃**（逐 token 的流式帧不进轨迹） |

### 1.4 注入方式（受支持的跨插件读取）

rail 的注册多给一个业务面（`inject`），渲染器把它绑成组件 props 上的 `useTrace` 选择器 hook：

```ts
// packages/client/ui-capability-map/src/client/index.ts:56-64
const trace = new CapabilityTrace(ctx.sessions)
ctx.slots.inject('shell.rail', () => ctx.slots.register({
  name: 'shell.rail',
  locale: NS,
  inject: (): CapabilityMapInjected => ({ hooks: { trace } }),
}, CapabilityMap))
```

绑定实现：`packages/client/ui-renderer/src/client/scoped-slots.tsx:184`（`bindInjectSources`：`hooks` 里的每个源变成 `use<Name>` 选择器 hook）。**没有 window 全局、没有 DOM 轮询、没有第二份会话状态**。

---

## 2. 映射规则（43 条业务命令 → 阶段 + 业务动作）

**生成器**：`packages/client/ui-capability-map/scripts/build-trace-map.mjs`（风格照 `build-capability-map.mjs`，共用同一张九阶段表 `scripts/stages.mjs`，两个生成器不会各说各话）。

```bash
node packages/client/ui-capability-map/scripts/build-trace-map.mjs \
  --from "/Users/…/daniel-bot/app/workflow-map.json"
# → wrote …/src/client/trace-map.generated.ts
#   commands 43/43 · tool aliases 4 · tool rules 3
#   stages ["数据","发现","SOV","背调"]
```

### 2.1 命令怎么被识别

运行时只做**去参数化匹配**，不执行、不回显：

1. **专用工具 → 命令桥**（4 条）：`daniel_brands_list → brands list`、`daniel_brand_view → brands show`、`daniel_clarify → clarify plan`、`daniel_screen_ask → clarify ask`（后两条取自插件自己的 `TOOL_COMMAND` 表）。
2. **argv 型工具**：`daniel_run` / `daniel_write_plan` 取 `argv`，`daniel_batch` 取 `calls[0]`（一批最多 6 条只读命令，用第一条代表这一批）；跳过以 `-` 开头的参数，取前两个词组成匹配键（`brands list`）。
3. **无命令的专用工具**（3 条）：`daniel_roster_search → 发现 · 在平台库里检索红人`、`daniel_kol_profile → 背调 · 查看红人频道档案`、`daniel_brand_count → 数据 · 统计品牌数量`。
4. 命中后按 `阶段 · 业务动作` 渲染，例如 `data` 段的 `brands list` → **数据 · 查看品牌清单**；`screening` 段的 `authenticity channel` → **背调 · 核对粉丝真实性**。

### 2.2 覆盖与兜底比例（实测）

| 口径 | 数值 |
|---|---|
| 业务命令总数（能力地图同一口径） | **43** |
| 已映射业务命令 | **43 / 43 = 100%** |
| 未命中（落到兜底）的业务命令 | **0（0%）** |
| 全部 91 条命令里未发布的 48 条（`ops` 运维 + `internal`） | 落到 `正在调用能力…`（占全部命令的 52.7%） |
| 非 Daniel 工具（文件/终端等） | 落到 `正在处理…` |

### 2.3 生成期断言（不满足就构建失败，不会静默出一半）

1. 业务命令必须正好 43 条，且每条都有手写业务动作；手写表里多出的（过期）条目同样报错。
2. 每条目标文案**不得含**：反引号、`_`、`--`、`.ts`、`.json`，且**不得含任何英文字母**（一次性排除命令名、大写常量、路径）。
3. 阶段名必须来自九阶段共享表；工具规则指向的命令必须已映射。
4. 命令键（如 `brands list`）只作为**匹配令牌**存在于 bundle 里，**永不进入渲染路径**（下方 §5 有渲染树扫描测试）。

---

## 3. 兜底策略（未命中不显示原文）

| 情况 | 显示 | 为什么 |
|---|---|---|
| Daniel 命令不在发布的 43 条里（如 `auth status`、`skills read`） | `正在调用能力…`（无阶段前缀） | 它在 Daniel 能力范围内，但不在业务阶段表里；给一句人话，不给命令名 |
| `daniel_write_commit`（只带 `plan_id`，参数里没有命令） | `正在调用能力…` | 真不知道它执行的是哪条命令，不猜 |
| 非 Daniel 工具（读文件、跑脚本、转换文档……） | `正在处理…` | 助手确实在干活，但不能说成 Daniel 能力，也不能暴露工具名 |
| 参数不是 JSON / 过大（>64KB）/ 不是对象 / argv 全是开关 | `正在调用能力…` | 解析失败一律降级，不抛错、不显示原文 |
| 命令名撞上对象原型键（如 `constructor`） | `正在调用能力…` | 规则表按自有键查（`Object.hasOwn`），不继承原型 |

---

## 4. 渲染结构（展开态）

```
┌ 能力地图 ────────────────────────┐
│ 执行轨迹                          │
│ ● 当前：背调 · 核对粉丝真实性      │   ← 有调用在跑
│   ── 或 ──                        │
│ ● 最近：数据 · 查看名单成员        │   ← 空闲但有历史
│   ── 或 ──                        │
│ ● 空闲中                          │   ← 什么都没有
│   背调 · 核对粉丝真实性   进行中   │   ← 最多 6 条，时间倒序
│   数据 · 查看名单成员     完成     │
└──────────────────────────────────┘
```

- 收起态：整节不渲染（组件树里根本没有它，见 §5 的订阅计数测试）。
- 状态只有两档：`进行中` / `完成`；回合一结束仍未回结果的调用按 `完成` 收尾。
- 不出现：命令原文、工具名、参数、返回值、`callId`、字段名、接口名。

真实渲染文本（zh 字典，jsdom 里渲染真实组件取 `textContent`）：

```
当前：背调 · 核对粉丝真实性
背调 · 核对粉丝真实性  进行中
数据 · 查看名单成员    完成
正在调用能力…          完成
正在处理…              完成
```

---

## 5. 性能（多久更新一次 · 收起时是否有开销）

**没有轮询、没有定时器。** 事件驱动，且只在面板展开时存在：

| 维度 | 事实 |
|---|---|
| 订阅数量 | 展开时 2 条：`sessions.list` + 当前会话绑定的 `eventSource`；收起时 0 条（`CapabilityTrace.detach()` 解绑并清空） |
| 更新频率 | 跟着会话日志走：**每次工具调用开始／结束各一次重算**；逐 token 的流式帧被丢弃 |
| 重算成本 | 只处理 `change.entries` 里的**增量**（`seq` 单调去重），不重扫整段历史；重算后与上次的"可见快照签名"比对，**没变就不通知 React**（所以纯文本流一个像素都不会重绘） |
| 展开的一次性成本 | 首次订阅要对已加载窗口做一遍扫描（只为取最近的动作）。实测 5,000 条事件 **1.67 ms** |
| 增量成本 | 实测 1,000 条 `tool/call`/`tool/result` 追加 = **1.83 ms**（≈1.8 µs/条，含 JSON 解析与匹配） |
| 内存上限 | 折叠表最多 24 条调用，渲染最多 6 条；不写 localStorage／indexedDB，不落任何本地存储 |
| 切会话 | `list` 一变即重解析；**绑定变了就清空**（不跨会话串味） |

> 一句话：不展开 = 零开销；展开 = 每次工具调用两次毫秒级重算，逐 token 的流不触发重绘。

---

## 6. 已知边界（如实记录）

1. **只有展开才订阅**：收起时不监听、不折叠、不保留任何轨迹；再次展开会从当前会话已加载的窗口重扫一次（1.67 ms 量级）。
2. **只覆盖"已加载"的那段窗口**：`eventSource` 是连续窗口，`hasMore` 为真时更早的历史不在内存里——轨迹只保证"最近的动作"准确。
3. **paging 不回溯**：向上翻页（prepend）拿到的都是更早的事件，`seq` 比已折叠的小，直接被忽略；轨迹不会因为翻历史而回退。
4. **`daniel_batch` 只按第一条命令命名**（一批最多 6 条），一条面板行无法表示六个动作。
5. **非 Daniel 工具不细分**：统一 `正在处理…`，不做工具名映射（映射了就必然要显示工具名）。
6. **写操作不特殊标注**：写命令（`daniel_write_plan` 的 argv 能被识别，`daniel_write_commit` 不能）在轨迹里只是普通动作，不显示"写"字样——轨迹读的是事件，不做权限判断。
7. **不落存储**：轨迹完全由会话数据派生，刷新/换会话即重建。

---

## 7. 改动文件

| 文件 | 作用 |
|---|---|
| `packages/client/ui-capability-map/scripts/stages.mjs` | **新**：九阶段共享表（能力地图与轨迹共用的唯一真源） |
| `.../scripts/build-capability-map.mjs` | 改：改为 `import { STAGES }`（产物逐字节不变，已重跑核对） |
| `.../scripts/build-trace-map.mjs` | **新**：轨迹映射生成器（43 条手写业务动作 + 4 条工具桥 + 3 条工具规则 + 兜底） |
| `.../src/client/trace-map.generated.ts` | **新**（生成物）：`TRACE_MAP` |
| `.../src/client/trace.ts` | **新**：事件折叠（`CapabilityTrace`）+ 命令→业务动作解析（`describeToolCall`） |
| `.../src/client/TraceRail.tsx` | **新**：轨迹区（当前一行 + 最多 6 条历史） |
| `.../src/client/CapabilityMap.tsx` | 改：接 `InjectFace<CapabilityMapInjected>`，展开时挂 `<TraceRail/>` |
| `.../src/client/CapabilityMap.module.css` | 改：`.trace*` 样式（全部 `--dsw-*` token，含 `prefers-reduced-motion` 兜底） |
| `.../src/client/index.ts` | 改：`inject` 加 `sessions`；注册时注入 `trace` 业务面；导出轨迹类型 |
| `.../src/client/locales.ts` | 改：zh/en 各 7 个 `trace.*` 键 |
| `.../src/client/types.ts` | 改：`TraceRule` / `TraceMapData` / `TRACE_MAP_SCHEMA` |
| `.../tsconfig.json` | 改：引用 `../../api/session-controller/tsconfig.client.json` |
| `.../package.json`、`pnpm-lock.yaml` | 改：`@deepseek-ai/dsh-api-session-controller`（workspace，类型依赖；`dsh.client.inject` 同步登记） |
| `.../tests/trace.client.spec.tsx` | **新**：19 条（映射表 3 + 事件折叠 10 + 面板 5 + 会话解析 1） |
| `.../tests/capability-map.client.spec.tsx` | 改：props 补 `useTrace`、注册用例补 `sessions` 服务与 inject 断言、加"非 Escape 键不收起"（共 10 条） |

> 说明：`ctx.sessions` 只用于**读**，没有新增写操作、没有改 Host/MCP 协议、没有新增运行时依赖（session-controller 是既有 workspace 包，且只引类型）。

---

## 8. 验收命令与结果

```bash
# 1) 客户端聚合类型检查
npx tsc -b tsconfig.client.json          # exit 0

# 2) 桌面构建
pnpm -C apps/desktop run build            # exit 0

# 3) 客户端插件 bundle
pnpm -C packages/client/ui-capability-map run bundle
#   lib/client.js  46.05 kB (gzip 12.45 kB)  exit 0

# 4) 相关单测（本包 + 受影响 ui-chat / ui-layout）
npx vitest run packages/client/ui-chat/tests packages/client/ui-layout/tests packages/client/ui-capability-map/tests
#   Test Files 66 passed (66) · Tests 1111 passed (1111)

# 5) 本包覆盖率（改动/新增的客户端文件全部 100%）
npx vitest run packages/client/ui-capability-map/tests --coverage \
  --coverage.include='packages/client/ui-capability-map/src/**'
#   src/client 全体 100/100/100/100（CapabilityMap.tsx · TraceRail.tsx · trace.ts ·
#   client/index.ts · locales.ts · 两个 generated.ts · types.ts）
#   唯一未覆盖：src/index.ts（宿主侧空 apply，S6.2 起即如此，本次未动）
```
