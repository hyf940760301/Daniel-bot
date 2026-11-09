# CHANGES · 顶部选择进入模型上下文（PHASE1 §9.4 / §9.8 · 管线 A）

> 状态：**已实现，门禁通过，未打包 DMG**（按任务要求停在验收）。
> 设计依据：`daniel-bot/specs/PHASE1-INTERACTION-DESIGN.md` §9.4 与新增的 §9.8。
> 源树：`/private/tmp/dsh-build/dsh-src`。本文件落在 `daniel-bot/app/desktop-patches/`，
> 并同步一份到源树 `apps/desktop/desktop-patches/`。

---

## 1. 做了什么（一句话）

顶部选择器存的 `{ workspace, brand }` 现在随每次提交走一条**独立的请求元数据通道**到 Host，
再由一个 host 插件渲染成**运行时上下文**（不是用户消息正文、也不是会打断缓存前缀的 system prompt 段）；
用户不重复名字，模型也能答出当前工作区/品牌，切换后下一轮立即答新值。

---

## 2. 改动点

### 2.1 客户端：选择 → 发送

| 文件 | 改动 |
|---|---|
| `packages/client/ui-capability-map/src/client/selection.ts` | 新增 `promptSelectionOf(snapshot)`：工作区与品牌**都**有值才返回 `{ workspace:{id,name}, brand:{id,name} }`，否则 `undefined`。 |
| `.../client/index.ts` | 在既有的 `sendGuard` 注册旁边注册 `ctx.conversation.requestContext.register(...)`（同一处 `ctx.inject(['conversation'])`），用上面的投影取值。 |
| `packages/client/ui-conversation/src/client/contract/request-context.ts` | **新增**。`ComposerRequestContextSource` / `ComposerRequestContexts` / `ComposerRequestContextRegistry`：按注册顺序取第一个非空值；单个 source 抛错只跳过它，**不影响发送**。 |
| `.../client/service.ts` | `IConversation` 增加 `requestContext`；`send()` 与 `sendSession()` 在提交时读一次，作为 `session.prompt(..., selection)` 的第 5 个参数。**没有选择时不传该参数**，既有四参调用形态完全不变（测试里的 fake Session 不用改）。 |
| `.../client/apply.ts` | 构建注册表并注入 `ConversationController`。 |
| `.../client/index.ts` | 导出新契约类型。 |

### 2.2 RPC：一条与 `clientTimeZone` 同构的字段

| 文件 | 改动 |
|---|---|
| `packages/api/session-controller/src/types.ts` | 新增 `ClientSelection`；`SessionPromptRequest.clientSelection?`；`MessageSourceMap['user-rpc']` 增加 `clientSelection?`（durable source 字段）；`RemoteErrorDetailsMap` 增加 `session/invalid-selection`。 |
| `packages/api/session-controller/src/selection.ts` | **新增**。`canonicalClientSelection`：workspace id 必须是非负安全整数；brand id 接受字符串或数字并归一为字符串；名字去空白、非空、≤200 字符；brand id ≤200 字符。 |
| `.../src/index.ts` | `prompt()` 在写 source 前校验；非法值返回 `session/invalid-selection`（不会落进历史）；合法值写进这条用户消息的 `source.clientSelection`。 |
| `.../src/client/contract/session.ts`、`.../src/client/sessions/session.ts` | `prompt()` 增加可选第 5 参 `selection`；普通会话把它放进 RPC 请求体（subagent 分支不涉及）。 |
| `packages/extensions/tool-cordis/src/api-catalog.ts` | `pnpm gen-cordis-catalog` 重新生成（新增 `ClientSelection`、`SessionPromptRequest` 声明更新）。 |

### 2.3 Host：元数据 → 模型上下文（新增最小插件包）

| 文件 | 改动 |
|---|---|
| `packages/context/client-selection-context/package.json` | **新增**包 `@deepseek-ai/dsh-client-selection-context`（host 插件，peer 依赖：cordis / agent / llm / session / system-prompt / api-session-controller）。 |
| `.../src/index.ts` | ① `agent/pre-step`（prepend 之前即可）遍历本条被 claim 的提示词，把带 `clientSelection` 的那条记进 `WeakMap<Session, ClientSelection>`；② `ctx.systemPrompt.context({ name:'app:client-selection', order:130, interpolate:false })` 在每次装配/刷新时渲染最新一对；没有记录返回空串。 |
| `packages/bundle/web-app/cordis.patch.yml` | 新行 `client-selection-context`，`disabled: ctx.get('profileContext')?.name !== 'desktop'`：只在 Daniel 桌面 profile 挂载，普通 `dsh web` 行为不变。 |
| `packages/bundle/web-app/package.json` | 加依赖，桌面打包闭包会自动带上这个包。 |
| `tsconfig.host.json` | 新包加入 host 聚合。 |
| `packages/api/session-controller/tsconfig.host.json` | `src/selection.ts` 加入显式 files 列表。 |
| `packages/context/client-selection-context/README.md`、`README.zh.md`、`README.i18n.yaml` | 新增包文档（英/中对照 + 配对记录），含 Model Experience 与 Known Limitations；`packages/context/README{,.zh}.md` 分组表补一行并重记配对。 |

### 2.4 测试

| 文件 | 覆盖 |
|---|---|
| `packages/context/client-selection-context/tests/client-selection-context.spec.ts` | **新增**，6 条：渲染含 id+name、名字带换行不破行、**首轮首个请求**就带上下文、切换后新请求带新值、无选择不注入、续步不丢。用桩适配器记录 `GenerateOptions`。 |
| `packages/api/session-controller/tests/session-cold.host.spec.ts` | 新增 1 条：RPC 合法值规范化后写进 `followup` 的 source；缺省不带字段；5 种畸形值返回 `session/invalid-selection` 且不落历史。 |
| `packages/client/ui-conversation/tests/service-orchestration.client.spec.ts` | 新增 4 条：`send` 带选择、`sendSession` 带选择、无来源不传字段且抛错来源不阻塞、**带 send-guard 的 composer 提交仍带上下文**。 |
| `packages/client/ui-capability-map/tests/selection.client.spec.tsx` | 新增 3 条：投影出 id+name；缺一半不投影；切换工作区丢旧品牌后不投影、重选品牌后投影新值。 |

---

## 3. 模型实际看到的片段（原文，脱敏）

截图式抄录一次真实请求（桩适配器记录的 `GenerateOptions.messages`，值用 jack / Halliday 这种演示值）：

```
system: You are an AI agent powered by DeepSeek Harness.

user: 我现在在哪个工作区？用哪个品牌？

user: Current runtime context. This snapshot supersedes earlier runtime-context snapshots.

Current workspace and brand selected in the app's top bar (authoritative for this conversation even though the user's message does not repeat them):
- Workspace: "jack" (id 90002)
- Brand: "Halliday" (id 4800023)
When the user asks which workspace or brand is active, answer with these values. A newer snapshot supersedes these values.
```

要点：

- 第二段是 `source.kind === 'runtime-context'` 的**上下文快照**，聊天区不渲染成用户说过的话；
- 用户那句话原样保留，**没有任何拼接**；
- 名字用 JSON 引号包住，品牌名里带换行/引号也不会伪造出新的结构行。

---

## 4. 切换前后两次请求的差异

同一会话，第一次选 `jack / Halliday`，切换后第二次选 `mike / ACME`：

| | 请求 1 | 请求 2 |
|---|---|---|
| 用户消息 | `我现在在哪个工作区？用哪个品牌？` | `那现在呢？` |
| 上下文快照（新增于历史尾部） | `Workspace: "jack" (id 90002)` / `Brand: "Halliday" (id 4800023)` | `Workspace: "mike" (id 90003)` / `Brand: "ACME" (id 4800044)` |
| 旧快照 | — | 作为历史留在原处，文字自带「This snapshot supersedes earlier runtime-context snapshots」 |

原文（请求 2 的尾部）：

```
user: 那现在呢？

user: Current runtime context. This snapshot supersedes earlier runtime-context snapshots.

Current workspace and brand selected in the app's top bar (authoritative for this conversation even though the user's message does not repeat them):
- Workspace: "mike" (id 90003)
- Brand: "ACME" (id 4800044)
When the user asks which workspace or brand is active, answer with these values. A newer snapshot supersedes these values.
```

说明：**旧快照不会被删除** —— 会话历史不可变是 DSH 的既有语义（工作目录、Web 入口变化时同样如此）。
最新快照是权威值，且文字里明确写了「更新者覆盖旧值」，模型按新值回答；聊天区两条都不可见。
这也是「切换后立即生效」能成立的机制：变化只追加一次，不重复注入（值没变时不增加任何 token）。

---

## 5. 测试与构建证据（真实输出）

### 5.1 单测 / 集成

```text
$ pnpm exec vitest run packages/context/client-selection-context packages/client/ui-conversation packages/client/ui-capability-map
Test Files  64 passed (64)
     Tests  1087 passed (1087)
```

```text
$ pnpm exec vitest run packages/api/session-controller
Test Files  48 passed (48)
     Tests  1079 passed (1079)
```

```text
$ pnpm exec vitest run packages/bundle/web-app
Test Files  7 passed (7)
     Tests  57 passed (57)
```

```text
$ pnpm exec vitest run scripts/verify-no-unknown-casts.spec.ts
Test Files  1 passed (1)
     Tests  69 passed (69)
```

单条证据（新增用例本身）：

```text
$ pnpm exec vitest run packages/context/client-selection-context
 ✓ packages/context/client-selection-context/tests/client-selection-context.spec.ts (6 tests) 171ms
```

### 5.2 类型检查 / 构建

```text
$ pnpm exec tsc -b tsconfig.client.json
（无输出）
EXIT:0
```

```text
$ NODE_OPTIONS=--max-old-space-size=8192 pnpm exec tsc -b tsconfig.host.json
EXIT:0
```
（默认堆 4GB 会在整仓聚合检查时 OOM，仓库自带的 `build:lib:host` 也用 8192；这是既有工程事实，不是本次改动引入的。）

```text
$ NODE_OPTIONS=--max-old-space-size=8192 pnpm -C apps/desktop run build
...
✓ built in 429ms
EXIT:0
```

```text
$ pnpm verify-cordis-catalog
gen-cordis-catalog: 129 generated file(s)/region(s) are up to date.
EXIT:0
```

### 5.3 文档门禁

```text
$ pnpm test:docs
run-gates: 19 passed, 2 failed, 0 skipped in 56.19s.
FAILED translation pairing — apps/desktop/docs/diagnostics/README.i18n.yaml（本次改动未触碰）
FAILED concrete terms — packages/client/ui-capability-map/{scripts/build-guide.mjs,src/client/types.ts}（上一次任务留下的命中，本次改动未触碰）
```

新增的两个 README 单独跑都过：

```text
$ pnpm verify-package-readme-limitations
verify-package-readme-limitations: 374 package READMEs checked (1 whitelisted), all conform.

$ pnpm verify-package-readme-model-experience
verify-package-readme-model-experience: 374 README(s) checked (...), all conform.

$ pnpm verify-package-readme-summaries
verify-package-readme-summaries: 427 English package README Summaries are within 100 words.

$ pnpm verify-md-links
verify-md-links: 2316 file(s) checked, all relative cross-links and fragments resolve.

$ pnpm verify-translation-pairing packages/context/client-selection-context/README.md
verify-translation-pairing: 1 named pair(s) consistent; the corpus-wide check still runs in doc-sync.
```

上文两条 FAILED 是**改动前就存在**的：诊断文档的配对记录与能力地图脚本/类型的 provenance 用词，都不在本次改动文件清单里；本次新增/修改的文档与 README 全部通过各自门禁。

---

## 6. 风险与回滚

| 风险 | 判断 | 处置 |
|---|---|---|
| 新字段让旧客户端/旧 Host 不兼容 | **低**：字段可选，缺省不出现；Host 端 `undefined` 直接跳过 | 无需迁移；旧请求行为完全不变 |
| 恶意/畸形 `clientSelection` 注入提示词 | **中**：值会进模型上下文 | Host 侧强校验（id/长度/非空），渲染时名字 `JSON.stringify`，换行无法伪造结构行；插件只渲染两个受控字段，不落其它内容 |
| 隐私：品牌/工作区名进会话历史 | **可接受**：这本就是用户在顶部显式选择、并要求模型使用的地址；与工具结果里的名字同源 | source 字段随会话持久化，和 `clientTimeZone` 同级；不额外写日志 |
| 每轮上下文增长 | **低**：值不变时不追加；只有切换才多一段固定 4 行文本 | 快照机制自带去重 |
| 旧快照残留导致模型答旧值 | **低**：新快照在历史尾部且明写 supersede；旧快照聊天区不可见 | 若未来要求物理替换，需给 runtime-context 增加「替换上一快照」语义，属独立改动，不在本次范围 |
| 桌面之外误挂载 | **低**：bundle 行带 `profileContext !== 'desktop'` 禁用 | 普通 `dsh web` 的 composition 不变（web-app 的 7 个测试文件全绿） |
| 打包闭包漏包 | **低**：`apps/cli` → `dsh-web-app` → 新包，闭包自动带上 | 真打包时用 `prepare:packages` 的闭包校验；本次按任务要求**未打 DMG** |

**回滚**：撤销 2.1–2.3 的文件即可；RPC 字段可选，单独回滚 host 插件只会让选择「不再进上下文」，不会破坏发送。

---

## 7. 为什么是这个 seam（而不是别的）

- **没有复用 `agent-instructions`/静态 system prompt**：`agent-instructions` 读工作区文件、面向「持久指令」；
  选择是**每轮可能变**的事实，塞进 system prompt 会每轮改写缓存前缀。
  `ctx.systemPrompt.context` 正是 DSH 给「每轮变化的事实」（cwd、Web URL）留的通道，语义、去重、UI 隐藏都已具备。
- **没有把值拼进用户消息**：任务明确禁止；而且用户可见正文会污染回放、引用、导出。
- **RPC 字段沿用 `clientTimeZone` 的既有模式**：可选、Host 校验、写进 durable source；
  这是仓库里唯一「客户端每轮带一点元数据给 Host」的成熟先例，改动面最小。
- **客户端注册表沿用 `sendGuard` 的既有模式**：依赖方向仍是「业务插件 → conversation 服务」，
  composer 不 import 能力地图包；`ui-conversation` 里没有出现任何 Daniel 字样。
- **Host 插件单独成包**：不污染 `ui-capability-map`（浏览器包）也不碰通用 `harness-dev-context`；
  只在桌面 profile 挂载，web 组合零变化。
