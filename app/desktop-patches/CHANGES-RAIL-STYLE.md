# CHANGES · 执行透视列表升级 + 下一步卡片升级与「优先」标识

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，基线 `ce7073d5`，已含品牌 / 登录 / 主题 / 执行透视 / 全景地图 / 下一步卡片）
> 改动包：`packages/client/ui-capability-map`（既有包内改动，**不新增包、不新增依赖、无新运行时 import**）
> 状态：**类型检查 / 桌面构建 / 包 bundle / 单测（155 条）全绿；未打包（按纪律）**
> 一句话：左栏九行模块列表改成「模块名靠左、次数与状态贴行尾右对齐」的 30px 行；回答下方的下一步卡片改成 46px 圆角卡，并按一条**写在代码里的固定词表**给其中一张打「优先」，命中的那张排到第一。

---

## 0. 结论先行

| 项 | 之前 | 现在 |
|---|---|---|
| 模块行右边缘 | 次数与状态各占自身宽度，`未用/已用/使用中` 字数不同 → 右边缘随行浮动 | 行尾块 `margin-left:auto` 推到最右，内部两列固定网格，状态列固定 `3.4em` 右对齐 → **九行右边缘同一像素** |
| 模块名字号 | 12px（行）/ 10px（英文） | **13px** / **10px** |
| 次数与状态字号 | 10px | **12px** |
| 模块行 | 26px、间距 1px、无分隔 | **30px、间距 3px、0.5px 极浅分隔线**（无卡片阴影） |
| 状态点 | 已用 = 品牌色实心 + 勾；使用中 = 品牌色实心 + 光晕 | 未用 = **空心点**；已用 = **弱化实心点**；使用中 = **品牌点 + 加粗** |
| 次数 | `N 次`，>0 就显示 | **`×N`，仅 >1 显示**，等宽数字 |
| 下一步卡片 | 高度随内容（约 33px）、`--dsw-radius-md`、11px 胶囊 | **46px、12px 圆角、12px 胶囊、13px 主色动作** |
| 高优标识 | 无 | **一张卡**：左侧品牌竖条 + 「优先」胶囊（读屏「建议先做」），并排到第一 |

**没做**：没有新增依赖；没有改解析层（`parseNextSteps` 的语法与上限不变）；没有改「点击只填不发／已填入置灰／键盘可达」；没有打包。

---

## 1. 执行透视里的「Daniel 能力全景」列表

### 1.1 改动前后对比

| 维度 | 之前（`HEAD`） | 现在 |
|---|---|---|
| 行结构 | `li > [点][中文名][英文名][次数][状态]` 五个平级 flex 子元素 | `li > [点][标签(中文名+英文名)][行尾块(次数+状态)]`，行尾块是唯一的尾部元素 |
| 行尾对齐 | `moduleCount` / `moduleState` 各自 `flex:none`，状态 `3.4em` 右对齐但**仅在自身列内**，次数一出现就把状态挤窄 | `margin-left:auto` 推到行尾；`grid-template-columns: minmax(0,auto) 3.4em` 两列，状态固定第 2 列 `width:3.4em` + `text-align:right` |
| 中文名字号 | `.moduleRow` 12px | `.moduleName` **13px** |
| 英文名字号 | 10px | 10px（不变） |
| 次数 / 状态字号 | 10px / 10px | **12px / 12px** |
| 行高 / 行距 | `min-height:26px`，`gap:1px` | **`min-height:30px`，`gap:3px`** |
| 分隔感 | 无 | 每行 `border-bottom: 0.5px solid var(--dsw-alias-border-l1)`（4% 黑），最后一行去掉；**无背景块、无阴影** |
| 已用 | 品牌色实心点 + 7px 勾 | **弱化实心点**（`--dsw-alias-label-caption`）；名称用**正常主文字色**，状态标签用次级色（不与「使用中」抢） |
| 使用中 | 品牌色实心点 + 光晕 | 品牌点 + 柔光晕（`--dsw-alias-state-business-tertiary`）**+ 名称/状态加粗** |
| 未用 | 空心点（`border-l2`）+ 次要色 | **空心点**（caption 描边）**+ 次要色** |
| 次数文案 | `module.calls` → `{count} 次` / `{count} calls` | `module.times` → **`×{count}`**（两种语言同形），>1 才渲染 |

### 1.2 结构与右对齐（真实源码）

```tsx
<li className={css.moduleRow} data-state={module.state} data-module={module.id}>
  <span className={css.moduleDot} data-state={module.state} data-pulse={…} aria-hidden="true" />
  <span className={css.moduleLabel}>
    <span className={css.moduleName}>{module.name}</span>
    <span className={css.moduleNameEn} data-module-en="">{moduleNameEnById(module.id)}</span>
  </span>
  <span className={css.moduleEnd} data-module-end="">
    {times !== undefined && <span className={css.moduleCount} data-count={String(module.calls)}>{times}</span>}
    <span className={css.moduleState}>{t(stateKey)}</span>
  </span>
</li>
```

```css
.moduleRow { display: flex; align-items: center; gap: 8px; min-height: 30px;
             padding: 0 6px; border-bottom: 0.5px solid var(--dsw-alias-border-l1); font-size: 13px; }
.modules   { gap: 3px; }
.moduleEnd { display: grid; flex: none; margin-left: auto;
             grid-template-columns: minmax(0, auto) 3.4em; column-gap: 6px;
             align-items: center; justify-items: end; }
.moduleCount { grid-column: 1; font-size: 12px; font-variant-numeric: tabular-nums; }
.moduleState { grid-column: 2; width: 3.4em; font-size: 12px; text-align: right; }
```

右边缘为什么一定齐：

1. `.moduleEnd` 是行的**最后一个**子元素，`margin-left:auto` 把它顶到最右；
2. 它内部是**两列固定网格**：次数在 `grid-column:1`（宽度随内容），状态在 `grid-column:2`（固定 `3.4em`）；
3. 状态单元格 `text-align:right`，所以「未用 / 已用 / 使用中」无论两个还是三个字，**右边界都落在同一列边线**；
4. 次数缺失时**不渲染元素**，但 `grid-column:2` 是显式的，状态不会滑到第 1 列、右边界不会因此左移；
5. 中文名长短只影响 `.moduleLabel` 的可伸缩宽度（`flex:0 1 auto; min-width:0` + `text-overflow:ellipsis`），**碰不到行尾块**。

### 1.3 三种状态（语义与样式一一对应）

| 状态 | 点 | 文字 | CSS |
|---|---|---|---|
| 未用 | 空心环，`--dsw-alias-label-caption` 描边、透明填充 | 名称/状态用次要色 | `.moduleDot`（基础规则）+ `.moduleName{color:--dsw-alias-label-secondary}` |
| 已用 | 弱化实心点（caption 填充） | 名称**正常主文字色**、不加粗；状态标签次级色 | `.moduleDot[data-state='used']` + `.moduleRow[data-state='used'] .moduleName{color:--dsw-alias-label-primary}` + `.moduleRow[data-state='used'] .moduleState{color:--dsw-alias-label-secondary}` |
| 使用中 | 品牌实心点 + 3px 柔光晕 | 名称与状态**加粗**（600） | `.moduleDot[data-state='active']` + `.moduleRow[data-state='active'] .moduleName{font-weight:600}` |

另外：`.moduleRow[data-state='active'] .moduleNameEn` 降到 tertiary，避免英文名和加粗中文名抢同一档视觉权重。

### 1.4 Token / 深浅色 / 动效

- 颜色全部来自 `--dsw-*`：`--dsw-alias-label-secondary / -tertiary / -caption / -primary`、`--dsw-alias-border-l1`、`--dsw-alias-state-business-primary / -tertiary`、`--dsw-alias-label-primary-foreground`。没有任何硬编码色值（单测逐行扫描 `.module.css` 的颜色声明）。
- 深浅色：分隔线用 `border-l1`（深色主题下是 6% 白），状态点用 caption/品牌 token，两套主题都有定义。
- 动效：本列表唯一的动画是「使用中」点的 `railPulse`，本来就只在 `data-pulse="on"` 时挂；`@media (prefers-reduced-motion: reduce)` 里 `.moduleDot[data-pulse='on'] { animation: none }` 是兜底，且 JS 侧在减少动效时直接给 `data-pulse="off"`。新增样式**没有引入任何动画/过渡**。

---

## 2. 「下一步卡片」升级 + 高优标识

### 2.1 样式前后对比

| 维度 | 之前 | 现在 |
|---|---|---|
| 卡片高度 | 内容撑开（约 32px） | **`min-height:46px`**（44–48 区间中值） |
| 圆角 | `var(--dsw-radius-md)`（12px） | **`12px`**（写死以对齐验收口径） |
| 排布 | 内容宽度、`align-items:baseline` | 卡片满宽 `width:100%`、`align-items:center`，右侧提示贴右 |
| 模块标签 | 11px、`radius-sm`、`bg-layer-2`（浅色下与卡片同色，几乎看不见） | **胶囊：`border-radius:999px`、12px、`--dsw-alias-markdown-tag` 浅底**（深浅主题都有色差） |
| 动作文字 | 13px（继承卡片） | **13px 主色**（`.action{color:--dsw-alias-label-primary}`） |
| hover | 底色变化 + 边框加深（已有） | 保留：`--dsw-alias-interactive-bg-hover` + `--dsw-alias-border-l3` |
| 右侧提示 | 「填入输入框」11px | **「填入」12px**（文案同步改短） |
| 高优标识 | 无 | 左侧 2.5px 品牌竖条 + 「优先」胶囊（`state-business-tertiary` 底、`state-business-primary` 字） |

### 2.2 高优判定规则（确定性、可单测）

规则写在 `src/client/next-steps.ts`，是**纯函数 + 固定词表**，不读模型输出、不读顺序之外的任何信号：

```ts
export const PRIORITY_PREFIXES = ['补齐', '先确认', '先建档', '先补齐', '需要先']
export const PRIORITY_MARKERS  = ['缺少', '未建档']

isPriorityAction(action) =
     action 以 任一 PRIORITY_PREFIXES 开头
  或 action 包含 任一 PRIORITY_MARKERS
```

`prioritizeNextSteps(steps)` 的判定顺序（**先命中先赢，只标一张**）：

| 顺序 | 条件 | 结果 |
|---|---|---|
| 1 | 存在句子命中上方词表 | **第一条命中**的卡是「优先」，其余不动 |
| 2 | 没有命中，且只有 1 张卡 | 这张就是「优先」（没有可比较的对象） |
| 3 | 其余（2 张都不命中） | **不标**，保持回答里的原顺序 |
| 4 | 0 张卡 | 返回空，组件本来就不渲染 |

要点：

- 「只标第一条」：两条都命中时，第二条**不会**抢徽标（有单测 `marks only the first match…`）。
- 「命中」是**逐字**判断：`给 Halliday 建档并补齐竞品基线。` 以「给」开头、不含「缺少/未建档」→ **普通**（`补齐` 出现在句中不算命中，避免把「顺便补齐」误判成前置动作）。

### 2.3 重排：只搬一次，且稳定

```ts
const marked = match !== -1 ? match : steps.length === 1 ? 0 : -1
const ordered = []
if (marked !== -1) ordered.push({ ...steps[marked], priority: true })
steps.forEach((step, index) => { if (index !== marked) ordered.push({ ...step, priority: false }) })
```

- 只做**一次**「把标记项移到下标 0」的稳定移动：其余卡片保持原有相对顺序（`A → B` 不会变成 `B → A`）。
- 同输入同输出：纯函数、无随机、无时间、无外部状态；单测对同一入参跑两次断言 `toEqual`。
- 不改入参：返回的是新对象（单测断言 `once[1] !== steps[0]`、原数组顺序不变）。
- 已经排在第一的命中卡不会被再动（`leaves an already-first marked card in place`）。

### 2.4 交互不变（硬约束逐条核对）

| 约束 | 现状 |
|---|---|
| 点击只填不发 | 仍是 `onClick → prefill(step.action)`，`prefill` 只调 `setDraft`；没有 submit/send 路径（单测断言 `submit`/`send` 零调用，且对**重排后的第一张卡**再验一次） |
| 已填入置灰 | `data-filled` / `aria-disabled` / 文案「已填入」逻辑未改；徽标与竖条在置灰态一并降为 tertiary/边框色 |
| 键盘可达 | 仍是原生 `<button type="button">`，`tabIndex=0`、不用 `disabled`，焦点不会被输入框抢走后丢失 |
| 最多 2 张、失败即空 | 解析层未改（`NEXT_STEP_LIMIT=2`，无合规段渲染 `null`） |
| 读屏 | 徽标内有一个视觉隐藏的「建议先做」；可见文字是「优先」，所以不是纯颜色信号 |

---

## 3. 改动落点

| 文件 | 改动 |
|---|---|
| `packages/client/ui-capability-map/src/client/TraceRail.tsx` | 模块行结构：新增 `.moduleLabel` / `.moduleEnd`；次数改 `×N` 且 `calls > 1` 才渲染；去掉已用行的小勾（改为弱化实心点） |
| `packages/client/ui-capability-map/src/client/CapabilityMap.module.css` | 模块行布局、字号、行高/间距、分隔线、三档状态点与文字权重、行尾两列网格、`max-width` 兜底同步 |
| `packages/client/ui-capability-map/src/client/next-steps.ts` | 新增 `PRIORITY_PREFIXES` / `PRIORITY_MARKERS` / `isPriorityAction` / `PrioritizedNextStep` / `prioritizeNextSteps`（纯函数，无副作用） |
| `packages/client/ui-capability-map/src/client/NextSteps.tsx` | 解析后接 `prioritizeNextSteps`；卡片加 `data-priority`；插入徽标（含读屏文案） |
| `packages/client/ui-capability-map/src/client/NextSteps.module.css` | 46px / 12px 圆角 / 12px 胶囊 / 13px 动作 / 右侧「填入」/ 优先竖条与徽标 / 置灰态全套 |
| `packages/client/ui-capability-map/src/client/locales.ts` | `module.calls` → `module.times`（`×{count}`，中英同形）；`nextSteps.fill` 文案改「填入」；新增 `nextSteps.priority` / `nextSteps.priorityHint` |
| `packages/client/ui-capability-map/tests/capability-map.client.spec.tsx` | 新增 5 条（右对齐结构与顺序、字号、次数阈值、三档状态、行距/分隔），并更新 1 条旧断言（见 §4.3） |
| `packages/client/ui-capability-map/tests/next-steps.client.spec.tsx` | 新增 21 条（规则正/负例、首条命中、单卡、不命中、重排稳定、徽标唯一、点击只写 draft、卡片度量） |

---

## 4. 测试证据

### 4.1 退出码

```text
$ npx tsc -b tsconfig.client.json
tsc exit=0

$ pnpm -C packages/client/ui-capability-map bundle
✔ [@deepseek-ai/dsh-client-ui-capability-map/client] Build complete in 105ms
bundle exit=0

$ pnpm -C apps/desktop run build
✓ built in 369ms
desktop build exit=0

$ pnpm vitest run packages/client/ui-capability-map
 Test Files  7 passed (7)
      Tests  155 passed (155)
tests exit=0
```

### 4.2 测试数账

| 文件 | 之前 | 现在 | 新增 |
|---|---|---|---|
| `capability-map.client.spec.tsx` | 16 | 21 | +5 |
| `next-steps.client.spec.tsx` | 17 | 38 | +21 |
| 其余 5 个文件 | 96 | 96 | 0 |
| **合计** | **129** | **155** | **+26** |

新增用例覆盖验收清单的每一项：

| 验收点 | 用例 |
|---|---|
| 右对齐：行尾元素为次数/状态且顺序固定 | `pins the count and the state to the row end, count first and state last`（逐行断言 `lastElementChild === .moduleEnd`、块内末位是 `.moduleState`、次数只在有值时位于其前；并断言九行中文名长度确实不同、`.moduleEnd` 有 `margin-left:auto`、`.moduleState` 有 `text-align:right` + `width:3.4em`） |
| 字号取值 | `uses 13px module names, 10px English names, and 12px counts and states` |
| 次数 >1 才显示 | `prints a count only above one, as ×N with tabular digits`（7 次→`×7`、1 次→无 `[data-count]` 且无 `×`） |
| 三种状态样式 | `marks 未用 hollow, 已用 solid and muted, 使用中 brand and bold` |
| 行高/间距/分隔 | `separates the rows with a 3px rhythm and a hairline, not stacked cards` |
| 卡片高度/圆角 | `gives a card a 44–48px height, a 12px radius, and a 12px module capsule`（数值解析后断言 44 ≤ h ≤ 48，并断言 `border-radius:12px`、胶囊 12px、动作 13px、hover 底色与边框） |
| 优先徽标只出现一次 | `renders one 优先 badge, on the first card, after the rule moved it up`（`[data-priority="true"]` 与 `[data-priority-badge]` 各 1 个，且都在第一张） |
| 规则命中/不命中 | 7 条正例 `it.each`（5 个前缀 + 2 个包含词）+ 4 条负例 `it.each` |
| 重排稳定 | `moves the marked card to the front exactly once, stably, without mutating the input` |
| 点击仍只 `setDraft` | `still only writes the composer draft when the priority card is clicked` |

### 4.3 既有断言的更新（仅 1 处，说明原因）

`capability-map.client.spec.tsx` 里旧的「工作示例」用例原本断言模块行文本包含 `1 次`。新规则是**次数仅 >1 显示**，一次调用不再打印次数，因此该断言改为：

```ts
// 之前
expect(moduleRows.find(row => row.getAttribute('data-module') === 'account')?.textContent).toContain('1 次')
// 现在
expect(moduleRows.find(row => row.getAttribute('data-module') === 'account')?.querySelector('[data-count]')).toBeNull()
```

其余 128 条断言**未改动**，全部通过。

---

## 5. 验收输出（真实 DOM，逐字复制）

### 5.1 模块行（账号与盘点 7 次·使用中；品牌档案 1 次·已用；其余未用）

列表整体可见文本：

```text
账号与盘点Account×7使用中品牌档案Brand Profile已用红人检索Creator Search未用红人名单Saved Lists未用真实性核验Authenticity未用合作追踪Campaigns未用品牌提及Brand Mentions未用内容情报Intelligence未用声量份额Share of Voice未用
```

逐行结构（`点 | 标签[中文名 / 英文名] | 行尾块[次数 状态]`）：

```text
active  点(active) | 标签[账号与盘点 / Account] | 行尾块[次数=×7 状态=使用中]
used    点(used)   | 标签[品牌档案 / Brand Profile] | 行尾块[状态=已用]
unused  点(unused) | 标签[红人检索 / Creator Search] | 行尾块[状态=未用]
unused  点(unused) | 标签[红人名单 / Saved Lists] | 行尾块[状态=未用]
unused  点(unused) | 标签[真实性核验 / Authenticity] | 行尾块[状态=未用]
unused  点(unused) | 标签[合作追踪 / Campaigns] | 行尾块[状态=未用]
unused  点(unused) | 标签[品牌提及 / Brand Mentions] | 行尾块[状态=未用]
unused  点(unused) | 标签[内容情报 / Intelligence] | 行尾块[状态=未用]
unused  点(unused) | 标签[声量份额 / Share of Voice] | 行尾块[状态=未用]
```

注意第 1 行：次数 `×7` 在状态「使用中」**之前**，状态永远是行尾块的第 2 列；第 2 行没有次数，状态仍然落在同一列——这就是「右边界齐」的来源。

### 5.2 卡片两种形态

带优先（原回答里「先补齐…」排在第二条，被规则搬到第一）：

```text
[优先卡] 模块胶囊[品牌档案] | 动作[先补齐三个竞品的档案，再出基线。] | 徽标[优先(读屏：建议先做)] | 提示[填入]
[普通卡] 模块胶囊[品牌提及] | 动作[看近 7 天负面提及的主要渠道。] | 提示[填入]
```

不带优先（两张都是普通动作 → 不标、不重排）：

```text
[普通卡] 模块胶囊[品牌档案] | 动作[给 Halliday 建档并补齐竞品基线。] | 提示[填入]
[普通卡] 模块胶囊[声量份额] | 动作[出近 30 天的提及份额。] | 提示[填入]
```

### 5.3 优先规则：三组输入 → 输出

| 输入 | 解析顺序 | 输出 |
|---|---|---|
| 规则命中（第二条「先补齐…」，被搬到第一） | 品牌提及：看近 7 天负面提及的主要渠道。 → 品牌档案：先补齐三个竞品的档案，再出基线。 | **[优先] 品牌档案：先补齐三个竞品的档案，再出基线。 → 品牌提及：看近 7 天负面提及的主要渠道。** |
| 规则不命中（两张都是普通动作） | 品牌档案：给 Halliday 建档并补齐竞品基线。 → 声量份额：出近 30 天的提及份额。 | 品牌档案：给 Halliday 建档并补齐竞品基线。 → 声量份额：出近 30 天的提及份额。（**不标、不重排**） |
| 只有一张卡（句子本身不命中） | 品牌提及：看近 7 天负面提及。 | **[优先] 品牌提及：看近 7 天负面提及。** |

规则表与逐句判定（同一函数的输出）：

```text
前缀：补齐 / 先确认 / 先建档 / 先补齐 / 需要先；包含：缺少 / 未建档
高优  先补齐三个竞品的档案。
高优  把缺少品牌档案的竞品补进基线。
普通  给 Halliday 建档并补齐竞品基线。
```

---

## 6. 边界与未做

- **未打包**：按要求停在构建与单测，没有生成 dmg/zip。
- **未改解析语法**：`下一步` 段落识别、模块白名单、最多 2 张、代码围栏剔除全部沿用 `CHANGES-NEXT-STEPS.md` 的实现，本次只在解析结果上加一层纯函数排序。
- **未改插槽**：卡片仍在 `conversation.chat.turnTail`，不抢 `assistant-actions`。
- **未新增依赖**：`PRIORITY_*` 是常量数组，`prioritizeNextSteps` 无 import。
- **次级项的取舍**：模块行不使用整行底色（避免九行像九张卡），只用 0.5px 极浅分隔线；卡片优先态只用 2.5px 品牌竖条 + 小胶囊，不加阴影、不加动画。
