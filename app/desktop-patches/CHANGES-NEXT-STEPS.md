# CHANGES · S6.6 下一步引导卡片（只预填 · 不发送）

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，基线 `ce7073d5`，已含品牌 / 登录 / 主题 / 执行透视 / 全景地图）
> 改动包：`packages/client/ui-capability-map`（**既有包内加一层**，不新增包、不新增 npm 依赖、无新运行时 import）
> 状态：**客户端类型检查 / 桌面构建 / 包 bundle / 单测（17 条）全绿；未打包（按纪律）**
> 一句话：助手回答末尾如果有「下一步」段，消息下方就出现 1–2 张可点的卡片；点一下只把动作那句话写进输入框并交回焦点，**永远不替你发送**；没有合规的「下一步」段就**什么都不显示**。

---

## 1. 插槽选择依据（先侦察后决策）

### 1.1 三个候选的实测事实

| 候选 | 事实（源码行号） | 结论 |
|---|---|---|
| `conversation.chat.turnTail` | **list** 槽，声明为「a completed Turn's action row 之前的按序功能条目」（`packages/client/ui-chat/src/client/contract/slots.ts:487`）；owner 就是 `TurnTailOwnerProps`（`turn: TurnLocation` + `seq` + `openFile`），由 `TurnTailNodeView.tsx:49` 在**本轮答案与操作行之间**渲染；同槽已有 `ui-plan`、`ui-deliverables`、`client-ui-action-cards` 三个正式占用者 | ✅ 天然「助手消息下方」、天然一轮一份、卡片随消息滚动 |
| `conversation.chat.assistant-actions` | **list** 槽，但语义是「图标动作条」（`slots.ts:493`，owner 只有 `messageId`），渲染进 `MessageIconActions` 的 `extraActions`（`TurnTailNodeView.tsx:56`）——一排小图标，塞不下「模块 + 一句话」卡片 | ❌ 形态不匹配，且拿不到 Turn 的收尾数据 |
| `conversation.input.overlay` | **list** 槽，挂载点是 composer 的 `overlayAnchor`（`packages/client/ui-conversation/src/client/skeleton/InputBar.tsx:448`），实际用途是**弹层/菜单**（`ui-commands`、`ui-input-trigger`、反馈弹窗都注册在这里） | ❌ 是浮层锚点，不是「输入框上方的一行内容」，会把卡片压到输入区上 |

### 1.2 结论

挂 **`conversation.chat.turnTail`**，自有 `id: 'capability-map.next-steps'`、`order: 30`，与既有条目并列追加，不改 ui-chat、不改 TurnTail 视图、不占用 `assistant-actions`。

**数据来源（关键）**：同槽的 `ActionCardTail` 已用 `turn.data.get('turn-tail')?.closing` 读取「本轮最后一条有正文的助手消息」（`packages/experimental/client-ui-action-cards/src/client/Card.tsx:104`）。本改动复用同一条路径：`TurnTailChatData.closing` 就是 `FinalAssistantChatData`（`chat-nodes.ts:94-99`），其中 `blocks` 是最终定稿的助手块。因此：

- 不需要 `useChat` 全量快照、不需要扫 DOM、不需要另存一份会话状态；
- 只取 `block.kind === 'text'` 的块拼成正文（reasoning / tool-call 不参与解析）；
- `turn.end === undefined`（本轮未结束）直接不渲染，避免把流式中的半句话当结论。

**依赖方向**：`ui-capability-map` 只加了 **一个 tsconfig 项目引用** `../ui-chat/tsconfig.client.json`（编译顺序，不是 npm 依赖），源码侧只有 `import type {} from '@deepseek-ai/dsh-client-ui-chat/client'`——`tsc` 拿类型、**运行时零 import**。bundle 产物实测只有三个外部 `require`：`react`、`react/jsx-runtime`、`@deepseek-ai/dsh-client-ui-primitives`，`dsh-client-ui-chat` 出现次数 **0**。

---

## 2. 解析规则（纯函数 `src/client/next-steps.ts`）

### 2.1 语法

```
[任意回答正文]
下一步            ← 或「下一步建议」「Next steps」；可带冒号、可加粗、可写成 ## 标题
1. <模块>：<动作>  ← 编号（1. / 1、/ 1)）或短横线（- / * / •）
2. <模块>：<动作>
```

| 规则 | 实现 | 为什么 |
|---|---|---|
| 认三种标题 | 正则 `^(?:下一步建议\|下一步\|next\s+steps?)$`（`i` 忽略大小写） | 覆盖纪律层要求的写法 |
| 标题装饰 | 先去掉 `#{1,6}`、`**`/`__`/`*`/`_`/反引号，再反复剥掉尾部 `:`/`：` | `**下一步**：` 这种「加粗 + 冒号」要能认（首版曾漏，已修并有单测） |
| 只认**最后**一处标题 | 从尾部向前找第一个标题行 | 回答里若先给旧建议、后给新建议，取新的 |
| 只看标题下 **最多 3 条**列表项 | 逐行读，遇到非列表行立即停（空行允许） | 「下面紧跟 1–3 条」；标题后如果先来一段散文，说明不是列表，宁可不出 |
| 一条必须是 `<模块>：<动作>` | 行体先去掉列表标记与包裹强调，再要求**整条以九个模块名之一开头**，紧跟 `:` 或 `：` | 不做模糊匹配、不做别名 |
| 模块校验 | 模块名来自 `module-map.generated.ts` 的九个名字，**严格相等** | 九个模块是产品词汇表，错一个就是错卡片 |
| 动作清洗 | 去掉首尾包裹的 `**`/`__`/反引号，保留句内文字与标点 | 填进输入框的应该是干净的一句话 |
| 最多 **2** 条 | `NEXT_STEP_LIMIT = 2`，超过截断 | 产品上限 |
| 代码块不算 | 先删掉 ``` / ~~~ 围栏块 | 回答里「引用」一段示例时不能长出假卡片 |
| 失败即空 | 任何一步不满足就返回 `[]`，**不猜、不补、不降级** | 宁可少，不要错 |

### 2.2 真实文本输出（`node` 直接跑 `parseNextSteps`，逐字复制）

**A. 中文「下一步」+ 编号（正常）**

输入：

```
三家竞品的建档已经补齐，摘要如下。

下一步
1. 品牌资产：把 Even Realities、Ray-Ban Meta 也建档，补齐同品类竞品基线。
2. 声量份额：以这 3 个竞品为固定竞争集，出近 30 天提及份额。
```

输出：

```json
[
  { "module": "品牌资产", "action": "把 Even Realities、Ray-Ban Meta 也建档，补齐同品类竞品基线。" },
  { "module": "声量份额", "action": "以这 3 个竞品为固定竞争集，出近 30 天提及份额。" }
]
```

**B. 英文标题 + 冒号 + 编号（正常）**

输入：

```
Done — the three profiles are updated.

Next steps:
1. 红人名单：把这次筛出的 12 位红人存成名单。
2. 合作追踪：给已回复的 3 位红人建跟进记录。
```

输出：

```json
[
  { "module": "红人名单", "action": "把这次筛出的 12 位红人存成名单。" },
  { "module": "合作追踪", "action": "给已回复的 3 位红人建跟进记录。" }
]
```

**C. 故意不合规（模块不在九个之内）**

输入：

```
下一步
1. 财务：把这批报价汇总成表。
2. 竞品分析：对比三家竞品的声量。
```

输出：

```json
[]
```

→ 两条都被丢弃，界面**什么都不渲染**。

**D. 部分不合规（丢第 1 条、留第 2 条）**

输入：

```
下一步
1. 财务：把这批报价汇总成表。
2. 品牌资产：给 Halliday 建档，补齐竞品基线。
```

输出：

```json
[
  { "module": "品牌资产", "action": "给 Halliday 建档，补齐竞品基线。" }
]
```

---

## 3. 渲染位置与形态

```
┌ 助手回答正文（最后一条）──────────────────────────┐
│ …摘要…                                          │
└─────────────────────────────────────────────────┘
下一步                                ← 弱化小标题（11px，tertiary）
┌───────────────────────────────────────────────┐
│ 品牌资产 │ 把 Even Realities、Ray-Ban Meta…   填入输入框 │  ← 原生 <button>
├───────────────────────────────────────────────┤
│ 声量份额 │ 以这 3 个竞品为固定竞争集…          填入输入框 │
└───────────────────────────────────────────────┘
[复制] [赞/踩] …                                  ← 本轮操作行（原有）
```

| 元素 | 实现 | 说明 |
|---|---|---|
| 容器 | `<section aria-label="下一步建议" data-next-steps>` | 测试钩子 `[data-next-steps]` |
| 卡片 | **原生 `<button type="button">`**（`data-next-step="0/1"`） | Tab 可达、Enter/Space 原生激活，不自己模拟键盘 |
| 模块名 | `<span>` 小标签（11px / `--dsw-alias-bg-layer-2` 底 / secondary 字色） | 弱化，不抢动作 |
| 动作 | 一句话，允许换行（`overflow-wrap: anywhere`） | 不截断成省略号，避免点错 |
| 提示 | 卡片右侧 11px「填入输入框」/「已填入」 | 让「点一下会发生什么」在点之前就可见 |
| 无结果 | 组件 `return null` | 不占位、不留空行 |

---

## 4. 点击行为（只预填，不发送）

1. 点击 → `prefill(step.action)`；
2. `prefill` 就是包内既有的 `prefillDraft(ctx.sessions, phrase)`（`prefill.ts:77`）——它走 `ctx.conversation.input.for(scope)` → `SessionInput.setDraft` → `focus()`，**不是 DOM 注入、不是合成键盘事件**；
3. `setDraft` 把整句写进草稿（已有草稿则换行追加，不吞用户已输入的文字），`focus()` 把光标交回输入框；
4. 返回 `'filled'` → 该卡片置为「已填入」；返回 `'unavailable'`（当前会话没有 composer）→ 卡片**保持可点**，不做任何假成功；
5. 代码里**不存在** `submit()` / `send()` 的调用路径。

「点击不发送」的断言原文（`tests/next-steps.client.spec.tsx`，假 composer 上挂了 `submit` / `send` 两个间谍）：

```ts
fireEvent.click(cardsOf(view)[1]!)
expect(composer.setDraft).toHaveBeenCalledTimes(1)
expect(composer.setDraft).toHaveBeenCalledWith('以这 3 个竞品为固定竞争集，出近 30 天提及份额。')
expect(composer.focus).toHaveBeenCalledTimes(1)
expect(composer.submit).not.toHaveBeenCalled()
expect(composer.send).not.toHaveBeenCalled()
```

注册层的同一条证明（真实 `SlotRegistry` + 真实 `apply`）：

```ts
const injected = (entries[0]?.inject as (() => { prefill: (phrase: string) => string }) | undefined)?.()
expect(injected?.prefill('给 Halliday 建档。')).toBe('filled')
expect(composer.setDraft).toHaveBeenCalledTimes(1)
expect(composer.submit).not.toHaveBeenCalled()
expect(composer.send).not.toHaveBeenCalled()
```

---

## 5. 状态

| 状态 | 规则 |
|---|---|
| 出现时机 | 本轮 `turn/end` 之后、且最后一条助手消息有合规「下一步」段 |
| 出现次数 | **同一轮只出现一次**（一个 turn-tail 条目 = 一组卡片） |
| 存活 | 组件内 `useState`，**不持久化**；随消息所在轮次存在，重载后重新解析 |
| 已填入 | 点成功后该卡片 `data-filled="true"` + `aria-disabled="true"` + 文案「已填入」，样式转灰、hover 不再变色；**保留 tab 焦点**（不用 `disabled`，避免焦点被浏览器丢掉） |
| 重复点击 | 已填入后 handler 直接 return，不会重复写草稿 |
| 未填入 | 没有 composer（`unavailable`）时不置灰，用户可再试 |

---

## 6. 边界（解析失败 / 异常输入怎么办）

| 情况 | 行为 | 用户看到什么 |
|---|---|---|
| 回答里没有「下一步」段 | `parseNextSteps` → `[]` → 组件 `null` | **什么都没有**（不占位、不留空行） |
| 标题对、但模块名不在九个之内 | 该条丢弃；全丢则 `[]` | 卡片不出现（或只出现合规的那一条） |
| 标题后先是一段散文 | 遇到非列表行即停 → `[]` | 不出现 |
| 标题下写了 4 条以上 | 只读前 3 条，最多留 2 条 | 最多 2 张卡 |
| 条目没有冒号（`品牌资产 给 X 建档`） | 该条丢弃 | 不出现 / 少一张 |
| 「下一步」只出现在代码块里 | 围栏块先被删 → `[]` | 不出现 |
| 回答里出现两次「下一步」 | 只取**最后**一处 | 只出现最后一组 |
| 本轮还在流式输出（`turn.end` 缺失） | 不渲染 | 结束后才出现 |
| 当前会话没有 composer | `prefill` 返回 `unavailable`，卡片保持可点 | 点了没反应、不置灰（不假装成功） |

> 设计取向：这一层的失败模式统一是「少显示」，不是「显示错的」。因为没有卡片时用户仍然可以直接打字，而一张错模块的卡片会把用户引到错的模块上。

---

## 7. 视觉

- **只用 `--dsw-*` token**：`--dsw-alias-bg-layer-1/2`、`--dsw-alias-interactive-bg-hover/active`、`--dsw-alias-border-l2/l3`、`--dsw-alias-label-primary/secondary/tertiary`、`--dsw-radius-md/sm`、`--dsw-focus-ring-width/color`、`--dsw-font-family`；
- 深浅色成立：不写任何 `#hex` / `rgb()` / `hsl()`（单测扫描 CSS 逐行断言，`transparent` 是唯一例外）；
- hover：底色 + 边框同时变；`focus-visible`：`outline` 用焦点环 token；
- `prefers-reduced-motion: reduce` 下 `transition: none`（唯一动效是 hover/active 的 120ms 底色过渡）。

---

## 8. 改动文件

| 文件 | 作用 |
|---|---|
| `packages/client/ui-capability-map/src/client/next-steps.ts` | **新增** 纯解析函数，`parseNextSteps()` / `NEXT_STEP_MODULES` / `NEXT_STEP_LIMIT` |
| `packages/client/ui-capability-map/src/client/NextSteps.tsx` | **新增** `NextStepCards` 组件 + `NextStepsInjected`（只有 `prefill` 一个写入口） |
| `packages/client/ui-capability-map/src/client/NextSteps.module.css` | **新增** 卡片样式（全 token） |
| `packages/client/ui-capability-map/src/client/index.ts` | 注册 `conversation.chat.turnTail` 条目；导出解析函数与组件 |
| `packages/client/ui-capability-map/src/client/locales.ts` | +4 组 key（`nextSteps.region/caption/fill/filled`，中英） |
| `packages/client/ui-capability-map/tsconfig.json` | +1 条项目引用 `../ui-chat/tsconfig.client.json`（仅类型/编译顺序） |
| `packages/client/ui-capability-map/tests/next-steps.client.spec.tsx` | **新增** 17 条单测 |

未改 ui-chat / ui-conversation / 任何上游包；未改 `package.json`（没有新增 npm 依赖）。

---

## 9. 测试证据

命令（工作目录 `/tmp/dsh-build/dsh-src`，`PATH` 指向 build toolchain 的 node24）：

```bash
tsc -b tsconfig.client.json                              # EXIT 0（21.9s）
pnpm -C packages/client/ui-capability-map run bundle     # EXIT 0，client: lib/client.js 100.16 kB
pnpm -C apps/desktop run build                           # EXIT 0
vitest run packages/client/ui-capability-map/tests       # 79 passed / 5 files
npm exec oxlint -- <4 个改动文件>                         # 0 warnings, 0 errors
vitest run scripts/client-bundle-purity.spec.ts scripts/client-tsconfig.spec.ts  # 50 passed
vitest run scripts/check-workspace-constraints.spec.ts   # 165 passed
```

单文件（本次新增的 17 条）：

```
 ✓ parseNextSteps > keeps the nine-module vocabulary and the two-card limit
 ✓ parseNextSteps > reads 中文「下一步」+ 编号
 ✓ parseNextSteps > reads 加粗标题 + 冒号 + 短横线
 ✓ parseNextSteps > reads 英文标题 Next steps
 ✓ parseNextSteps > reads the heading with a colon, without one, bolded, and as a Markdown heading
 ✓ parseNextSteps > drops items whose module is not one of the nine
 ✓ parseNextSteps > truncates a three-item list to two cards
 ✓ parseNextSteps > returns nothing without a heading, without items, or across prose
 ✓ parseNextSteps > ignores a quoted block inside a fenced code block and prefers the last heading
 ✓ NextStepCards > renders one card per step with a muted module label and the action sentence
 ✓ NextStepCards > renders nothing at all when the answer has no conforming section, and nothing while the Turn is open
 ✓ NextStepCards > clicking only writes the draft and focuses it — no submit, no send
 ✓ NextStepCards > greys a card after it filled and keeps later clicks from writing again
 ✓ NextStepCards > keeps a card actionable when no composer was available
 ✓ NextStepCards > is reachable and activatable from the keyboard
 ✓ NextStepCards > styles every colour with a theme token and drops motion under reduced motion
 ✓ next-step registration > adds exactly one turnTail entry whose prefill writes the composer

 Test Files  1 passed (1)
      Tests  17 passed (17)
```

覆盖点对照（要求的 11 类）：中文/英文标题 ✅、带冒号/不带 ✅、编号与短横线 ✅、超过 2 条截断 ✅、模块不匹配丢弃 ✅、无「下一步」不渲染 ✅、点击只调 setDraft 不调 submit/send ✅、点击后置灰 ✅、键盘可达 ✅、深浅色不写死颜色 ✅、无结果不占位（`childElementCount === 0`）✅。

> 键盘说明：卡片是原生 `<button>`，所以 Tab 停在它上面、Enter/Space 由浏览器触发 click；jsdom 不实现「keydown → 激活」这一步，因此单测断言的是「原生 button + `tabIndex === 0` + 未 disabled + `.focus()` 生效 + 同一个 click handler 生效」，而不是伪造一次 Enter。

---

## 10. 已知取舍 / 未做

- **每个已完成轮次都会显示自己的卡片**（不是只显示最新一轮）：卡片属于那条消息，滚动回看时仍在；只在最新轮显示的方案会在下一轮开始后把上一条的引导抹掉。
- **模块名严格匹配九个名字**，不做「品牌资产模块」「资产」这类近似匹配——误配的代价高于少一张卡。
- **`prefill` 用的是「当前主视图会话」的 composer**（`prefill.ts` 既有语义）；卡片本来就渲染在当前会话里，所以两者一致。
- 本轮**没有**改包 README / 未重新打包（按纪律停在源码与构建产物）。
