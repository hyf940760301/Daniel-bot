# 变更记录：对话区顶部「工作区 + 品牌」细条 & 模块名改回 Daniel 原名（中英双语）

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，基线 `ce7073d5`，已含品牌/登录/主题/能力全景与执行透视）
> 改动包：`packages/client/ui-capability-map`（主体）、`packages/client/ui-conversation`（新增一个只读槽位，1 行渲染）、生成物 `packages/extensions/cordis-client-runner/src/client/slot-catalog.ts`（槽位目录重新生成）
> 状态：**类型检查 / 桌面构建 / 客户端 bundle / 单测全绿；未打包（按纪律）**
> 一句话：对话区顶部多一条 **27px 的只读细条**——左边 `工作区 90002 · Workspace`，右边 `品牌 Halliday`；九个模块名全部改回 Daniel 原名并配上英文（`品牌档案 / Brand Profile`、`真实性核验 / Authenticity`、`账号与盘点 / Account`），左栏、轨迹步骤行、全景指南弹窗三处同步。
> **2026-11-03 改版**：工作区改显示**名称**（90002 → `Jack`）、整条改成**单行左对齐**、字号/字重/颜色改为 **14px / 600 / 正文黑** —— 见 §8（§1 的数据来源口径不变；§2 末尾的样式描述与 §6.2 的渲染文本已被 §8 取代）。

---

## 1. 口径：为什么品牌是「本次任务用到」的

这是本次唯一需要解释的口径，因为两半的数据性质完全不同。

| 项 | 事实 | 细条怎么显示 |
|---|---|---|
| 工作区 | **有真实状态**。`account workspaces` 的返回体里带 `activeWorkspaceId`（`daniel_cli/commands/mod_account.py` 的 `cmd_workspaces`：`data = {"count", "activeWorkspaceId", "workspaces"}`） | 取**本会话里 `account workspaces`（含别名 `workspaces list`）结果**里的 `activeWorkspaceId`；没有这个结果、或结果里没有该字段 → `工作区：未知` |
| 品牌 | **没有全局「当前品牌」**。Daniel 的每条命令用 `--brand <编号或名字>` 按需指定，CLI 不保存「上次用的品牌」 | 取**本次任务最近一次调用**里的 `--brand` 值；任务里没出现过 → `品牌：未指定` |

补充三条实现口径：

1. **编号 → 名字只认已有结果**。`--brand 4800023` 显示成 `品牌 Halliday`，前提是本会话里出现过 `brands list` 的结果、且其中 `brands[].id === 4800023`。
   映射不到就**原样显示编号**（`品牌 9999999`）——不猜、不去查、不请求。名字本身作为 `--brand` 传进来时（`--brand Halliday`）直接显示原值。
2. **任务边界**：人类消息（`user/message`，`source.kind === 'user'`）开启新任务时**清空品牌**；**工作区保留**（它是账号状态，不属于某个任务）。合成注入（`source.kind !== 'user'`）不算任务边界。
3. **只读**：细条只读会话事件窗口里**已经发生**的 `tool/call` 参数与 `tool/result` 文本，不切工作区、不发请求、不落盘、没有任何按钮或链接。

> 为什么不从会话 cwd / 工作区文件推工作区：那是 Harness 的 Workspace，不是 Daniel 账号下的工作区编号，两者不是一回事；用它会显示一个「看起来对、其实不是 Daniel 那个 90002」的数字。`未知` 是诚实的。

---

## 2. 位置：一条细条，不是卡片

DSH 的会话骨架里没有「对话区顶部的加性槽位」，`conversation.header` 是**单占位**（导航/标题/视图页签），注册进去会顶掉导航。所以本次加了一个**空的、加性的 list 槽位**，由会话骨架渲染、由能力地图包占用：

| 落点 | 文件 | 说明 |
|---|---|---|
| 槽位声明 | `packages/client/ui-conversation/src/client/contract/slots.ts` → `'conversation.context.bar': { kind: 'list'; scope: 'root' }` | root 作用域：占用方自带数据源，不拿 Session 绑定 |
| 槽位声明（父） | 同文件 `ConversationSlotProps` += `'conversation.context.bar'` | 让骨架拿到 `renderSlot` 的类型 |
| 子槽位登记 | `packages/client/ui-conversation/src/client/apply.ts`（`main.conversation` 的 `children`） | 与 `conversation.header` 并列 |
| 渲染位 | `packages/client/ui-conversation/src/client/skeleton/ConversationMainPanel.tsx` | `<header>` 之后、`conversation.content` 之前；**hero / settling / active 三个阶段都在**，所以空白会话也看得到工作区 |
| 空态 | `ConversationRoot.module.css` → `.contextBar:empty { display: none }` | 没人占用时高度为 0，不占位 |
| 占用方 | `packages/client/ui-capability-map/src/client/index.ts` | `ctx.slots.inject('conversation.context.bar', …)`，`id: 'capability-map.context'` |

视觉：整条 27px 高、`--dsw-alias-bg-base` 底、`0.5px` 的 `--dsw-alias-border-l3` 下边线、左右内边距与对话区 header 对齐（`0 28px 0 20px`）；文字 10–12px（主行 11px、英文小字 10px）、弱化色 `--dsw-alias-label-caption / tertiary / secondary`；**没有任何动画/过渡**（所以 `prefers-reduced-motion` 无需特判）。

窄屏：`max-width: 720px` 时先丢掉 `· Workspace` 这个英文词、内边距收到 16px，数值本身省略号截断，两半不会互相挤掉。

---

## 3. 双语规则

### 3.1 模块名是数据，不是文案

九个模块的**中文名 + 英文名**都放进生成物 `module-map.generated.ts`（`ModuleDefinition.name` / `nameEn`），弹窗指南同理放进 `guide.generated.ts`（`GuideModule.nameEn`）。理由：左栏、轨迹步骤、指南弹窗三处要显示同一份名字，运行时不允许任何一处自己拼英文。

| id | 中文（Daniel 原名） | 英文 |
|---|---|---|
| account | 账号与盘点 | Account |
| brands | 品牌档案 | Brand Profile |
| discovery | 红人检索 | Creator Search |
| lists | 红人名单 | Saved Lists |
| screening | 真实性核验 | Authenticity |
| tracking | 合作追踪 | Campaigns |
| mentions | 品牌提及 | Brand Mentions |
| intel | 内容情报 | Intelligence |
| share | 声量份额 | Share of Voice |

> 中文名是**身份**（命令表、下一步解析、轨迹合并都按它 key），英文名只用于显示。`trace.ts` 的快照形状没动，英文在渲染层用 `module-names.ts` 按中文名/模块 id 反查——不新增状态、不改既有测试的 fold 契约。

### 3.2 三处显示规则

| 处 | 样子 | 实现 |
|---|---|---|
| 左栏模块行（320px 面板） | `账号与盘点` 正常字号 + `Account` 10px 弱化，同一行；右侧次数/状态不变 | `TraceRail.tsx` + `.moduleNameEn`（`flex: 0 1 auto`、`text-overflow: ellipsis`，永不换行） |
| 轨迹步骤行的模块标签 | 两行、右对齐：上行中文 10px，下行英文 9px | `.stepTag` 改成 `inline-flex` 纵向；`真实性核验 / Authenticity` 一行放不下，堆叠才不会把英文吃掉 |
| 全景指南弹窗 | 左栏索引 `品牌档案 Brand Profile`（英文 10px 弱化）+ 右侧详情标题 `品牌档案` 后跟 11px 的 `Brand Profile`；搜索同时匹配中英文 | `GuideMap.tsx`（`filterGuide` 也匹配 `nameEn`）+ `.moduleNameEn` / `.detailTitleEn` |

### 3.3 48px 收起态怎么处理（不挤爆）

- **收起态根本不渲染模块行**：48px 竖条只有清单图标 + 竖排标题（既有行为），`data-capability-map="collapsed"`、`data-rail-width="48"`，面板 body 不挂载 ⇒ 模块名没有可被挤爆的容器。
- **样式层再兜一道**：`.dock[data-rail-width='48'] .moduleNameEn` / `.stepTagEn { display: none }`，中文名 `.moduleName` / `.stepTagZh` 设 `max-width: 100%`、`overflow: hidden`、`text-overflow: ellipsis`、`white-space: nowrap`。即便以后有人在 48px 里渲染模块行，也只会剩中文（必要时省略号），不会把轨道撑宽。
- 单测 `mounts no module row at all in the collapsed 48px strip` 直接断言收起态 DOM 里既没有中文模块名也没有英文模块名。

---

## 4. 改动文件

| 文件 | 改了什么 |
|---|---|
| `packages/client/ui-capability-map/scripts/build-module-map.mjs` | `MODULES` 增加 `en`；新增 `assertEnglishName()`（非空、首尾无空白、首字母大写、只允许字母和空格、不重复）；生成物写出 `nameEn`；`ALIASES` / `TOOL_RULES` 里的模块名改成新名 |
| `packages/client/ui-capability-map/src/client/module-map.generated.ts` | **重新生成**（9 模块 / 51 动作 / 52 命令不变，新增 9 个 `nameEn`） |
| `packages/client/ui-capability-map/src/client/types.ts` | `ModuleDefinition.nameEn`、`GuideModule.nameEn` |
| `packages/client/ui-capability-map/src/client/module-names.ts` | **新增**：按中文名 / 模块 id 反查英文名（`moduleNameEn` / `moduleNameEnById`） |
| `packages/client/ui-capability-map/src/client/TraceRail.tsx` | 模块行与步骤标签双语；aria-label 同步带上英文 |
| `packages/client/ui-capability-map/src/client/CapabilityMap.module.css` | `.moduleNameEn`、`.stepTagZh/.stepTagEn`、48px 收起态兜底规则 |
| `packages/client/ui-capability-map/scripts/build-guide.mjs` | 指南也要求中英两个名字（同样的生成期断言）；`nameEn` 进生成物与内容摘要（digest） |
| `packages/client/ui-capability-map/src/client/guide.generated.ts` | **重新生成**（模块改名 + `nameEn`） |
| `packages/client/ui-capability-map/src/client/GuideMap.tsx` | 索引行、详情标题双语；`filterGuide` 同时匹配英文名 |
| `packages/client/ui-capability-map/src/client/GuideMap.module.css` | `.moduleNameEn`、`.detailTitleEn` |
| `packages/client/ui-capability-map/src/client/context.ts` | **新增**：`ContextTrace` 折叠（`--brand` 解析、`activeWorkspaceId` 解析、`brands list` 名字映射、任务边界重置、会话切换清空） |
| `packages/client/ui-capability-map/src/client/ContextBar.tsx` | **新增**：细条组件（左工作区、右品牌、只读、无控件） |
| `packages/client/ui-capability-map/src/client/ContextBar.module.css` | **新增**：27px 细条样式（全部 `--dsw-*` token） |
| `packages/client/ui-capability-map/src/client/locales.ts` | 6 个新 key（`context.region / workspace / workspaceEn / brand / unknownWorkspace / noBrand`），中英各一份 |
| `packages/client/ui-capability-map/src/client/index.ts` | 注册 `conversation.context.bar` 占用方；导出新 API |
| `packages/client/ui-capability-map/src/client/next-steps.ts` | 只改注释（模块名不再是 workflow map 的拼写） |
| `packages/client/ui-capability-map/tests/context-bar.client.spec.tsx` | **新增 24 条**测试 |
| 既有 6 个测试文件 | 旧的模块名断言 / 构造数据改成新名（共 29 处），行为断言不变 |
| `packages/client/ui-capability-map/tests/fixtures/daniel-guide.json` | 与作者源同步（逐字节一致，sha256 对得上） |
| `packages/client/ui-conversation/src/client/contract/slots.ts` | 新增 `conversation.context.bar` 槽位声明 |
| `packages/client/ui-conversation/src/client/apply.ts` | `main.conversation` 声明该子槽位 |
| `packages/client/ui-conversation/src/client/skeleton/ConversationMainPanel.tsx` | header 之后渲染该槽位 |
| `packages/client/ui-conversation/src/client/skeleton/ConversationRoot.module.css` | `.contextBar`（空态零高） |
| `packages/extensions/cordis-client-runner/src/client/slot-catalog.ts` | 槽位目录重新生成（`pnpm run gen-client-catalog`） |
| `daniel-bot/app/guide/daniel-guide.json` | 九个模块改名 + `nameEn`（指南作者源） |
| `packages/client/ui-capability-map/README.md` / `.zh.md` / `README.i18n.yaml` | 说明与双语记录同步 |

没有新增依赖、没有新增包、没有改 Host/MCP、没有新增任何网络请求。

---

## 5. 生成期断言（实测）

**模块表**（`build-module-map.mjs`）：

```
$ node scripts/build-module-map.mjs --from …/workflow-map.json
wrote …/src/client/module-map.generated.ts
modules 9 · actions 51 · commands 52/91
账号与盘点=10动作/11命令 品牌档案=7动作/7命令 红人检索=4动作/4命令 红人名单=8动作/8命令
真实性核验=2动作/2命令 合作追踪=8动作/8命令 品牌提及=4动作/4命令 内容情报=4动作/4命令 声量份额=4动作/4命令
```

故意弄坏英文名后（临时副本，验证断言真的会拦住）：

```
build-module-map: 模块 lists 的英文模块名必须首字母大写：saved lists
build-module-map: 模块 intel 缺少英文模块名
```

**指南表**（`build-guide.mjs`，同样的两条断言）：

```
empty -> build-guide: 模块 1（账号与盘点）的英文名 缺少英文模块名
lower -> build-guide: 模块 2（品牌档案）的英文名 的英文模块名必须首字母大写：brand profile
valid -> 9 modules
```

---

## 6. 验收

### 6.1 构建 / 类型 / 测试退出码

| 命令 | 结果 |
|---|---|
| `npx tsc -b tsconfig.client.json` | **exit 0** |
| `pnpm -C apps/desktop run build` | **exit 0**（`lib/main.js` 887.16 kB、welcome 页 built） |
| `pnpm -C packages/client/ui-capability-map run bundle` | **exit 0**（`lib/client.js` 130.77 kB） |
| `npx vitest run … packages/client/ui-capability-map/tests` | **7 files / 121 tests passed**（既有 97 + 新增 24） |
| `npx vitest run … packages/client/ui-conversation/tests` | **54 files / 881 tests passed**（骨架被改，回归一遍） |
| `npx tsx scripts/gen-client-catalog.ts --check` + `scripts/gen-client-catalog.spec.ts` | up to date；22 tests passed |

新增 24 条覆盖：工作区显示 / 品牌解析（三种工具形态、两种 `--brand` 写法、后写覆盖前写）/ 编号→名字映射 / 映射不到显示原值 / 未指定品牌 / 未知工作区 / 跨任务清空品牌且保留工作区 / 会话切换全部清空 / 非来源命令的结果不采信 / 只读（无 fetch、无 WebSocket、零控件）/ 颜色只用 token 且字号 10–12px、无动画 / 九模块中英名齐全且英文首字母大写 / 指南弹窗中英名与英文搜索 / 步骤标签与模块行双语 / 48px 收起态无模块名 / 槽位注册恰好一条。

### 6.2 顶部条渲染文本（真实 DOM 输出）

> 上一轮（编号 + 左右分列）的口径，**已被 §8.3 取代**，留作历史对照。

```
有品牌       : 工作区 90002 · Workspace 品牌 Halliday
无品牌       : 工作区 90002 · Workspace 品牌：未指定
工作区未知   : 工作区：未知 品牌：未指定
品牌编号未映射: 工作区 90002 · Workspace 品牌 9999999
```

### 6.3 九个模块中英对照（来自生成物 `module-map.generated.ts`）

```
账号与盘点 / Account            品牌档案 / Brand Profile      红人检索 / Creator Search
红人名单 / Saved Lists          真实性核验 / Authenticity     合作追踪 / Campaigns
品牌提及 / Brand Mentions       内容情报 / Intelligence       声量份额 / Share of Voice
```

指南弹窗生成物 `guide.generated.ts` 的九个模块名与上表逐一相同（单测断言两者相等）。

### 6.4 窄宽度（48px 收起）

- 收起态 DOM 只有图标 + 竖排标题；**模块行不渲染**，所以既没有中文名也没有英文名可被挤爆（单测断言）。
- 样式层兜底：48px 时英文名 `display: none`，中文名省略号截断（`text-overflow: ellipsis`），轨道不会被撑宽。
- 展开态固定 320px：模块行英文名 `max-width: 46%` + 省略号，步骤标签英文名换到第二行，两者都不会把右侧的次数/状态挤掉。

---

## 7. 未做 / 需要下游跟一处

- **未打包**（按纪律）。
- `apps/desktop/resources/vendor/daniel-dsh-plugin/lib/normalize.js` 里的 `ANSWER_POLICY`（“回答纪律”提示词）仍然写着旧模块名（`账号与工作区／品牌资产／真实性与背调…`）。它属于 Host/MCP 侧的供应商文件，本次硬约束要求不改，所以没动。影响：模型可能继续在「下一步」里写旧名，`parseNextSteps` 只认新名 ⇒ 那几张下一步卡片会解析不出来。建议在 Daniel 项目里同步改这段提示词后再同步 vendor（不属于本次改动范围）。
- `docs/i18n` 的配对校验里 `apps/desktop/docs/diagnostics/README.i18n.yaml` 有一条**改动前就存在**的未同步（与本次无关，未处理）。

---

## 8. 2026-11-03 改版：工作区显示名称 · 单行左对齐 · 正文黑

> 本次只动「显示什么 + 长什么样」，**数据来源口径与只读纪律一条不改**：仍然只读本会话里已发生的 `account workspaces` / `brands list` 结果与 `--brand` 参数，不发请求、不查索引、不落盘、没有任何控件；新任务仍然清品牌、留工作区（现在名字也一并留着）。

### 8.1 显示规则：名称优先，编号兜底

| 字段 | 取值顺序 | 兜底 |
|---|---|---|
| 工作区 | 同一次 `account workspaces`（含别名 `workspaces list`）结果里 `workspaces[]` 的 `id → name`，取 `activeWorkspaceId` 对应的 `name`（例：90002 → `Jack`） | ① 该 id 在 `workspaces[]` 里没有可用名字 → 显示**编号**：`工作区：90002`；② 结果里连 `activeWorkspaceId` 都没有 → `工作区：未知` |
| 品牌 | 本次任务最近一次 `--brand` 的值；数字编号经本会话 `brands list` 结果的 `id → name` 翻译成名字 | ① 任务里没出现过 `--brand` → `品牌：未指定`；② 编号映射不到 → 原样显示编号 |

名称和编号**来自同一次结果**，不是第二次请求：CLI 的 `cmd_workspaces` 返回 `data = {count, activeWorkspaceId, workspaces[]}`，每行是 `{id, name, planTier, memberRole, …}` 再补一个 `isActive`（`daniel_cli/commands/mod_account.py`）。`activeWorkspaceId` 给出「哪个」，`workspaces[]` 给出「叫什么」。

取不到的三种情形都写死成可读文案，**不猜**：

- 结果还没来 / 结果里没有 `activeWorkspaceId` → `工作区：未知`（不从会话 cwd、不从工作区文件名反推，那是 Harness 的工作区，不是 Daniel 账号下的工作区）；
- `activeWorkspaceId` 有、但 `workspaces[]` 里没有这一行（或名字是空串） → 显示编号 `工作区：90002`，因为「编号至少是真的」比「编一个名字」诚实；
- `--brand 4800023` 但本会话没有能映射它的 `brands list` 结果 → 显示 `4800023` 原值。

解析容错（`workspaceNames()`）：先按 JSON 取 `workspaces[]`，只认「数字 `id` + 非空字符串 `name`」，其余行跳过——**绝不拿邻行的名字顶替**（行里没有名字就让它未知）；只有整段文本 `JSON.parse` 失败（被说明文字包住 / 被截断）时，才在 `"workspaces"` 之后的那一段做宽松扫描，避免把 `brands[]` 的名字误当工作区名。

### 8.2 样式取值

| 项 | 取值 | 落在 |
|---|---|---|
| 布局 | `display: flex; flex-wrap: nowrap; justify-content: flex-start`（**去掉** `space-between`） | `.bar` |
| 字段间距 | `gap: 20px`（16–24px 区间内；只有这一处间距，没有第二个分隔符） | `.bar` |
| 字号 | `font-size: 14px` | `.bar`（`.label` / `.value` 继承） |
| 字重 | `font-weight: 600` | `.bar` |
| 颜色 | `color: var(--dsw-alias-label-primary)`（正文黑；浅色 `rgb(25,28,32)` = #191C20，深色取同一 token 的 `--dsw-static-neutral-bluish-50` = `rgb(249,250,251)` = #F9FAFB） | `.bar` / `.label` / `.value` |
| 单行 | `white-space: nowrap`；值超长时省略号 | `.bar` / `.item` |
| 高度 / 底色 / 下边线 | 27px / `var(--dsw-alias-bg-base)` / `0.5px var(--dsw-alias-border-l3)`（未变） | `.bar` |

实际 CSS 片段（`ContextBar.module.css`）：

```css
.bar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: flex-start;   /* 单行从左边开始连续排，不再两端对齐 */
  gap: 20px;                     /* 两个字段之间唯一且固定的间距 */
  height: 27px;
  padding: 0 28px 0 20px;
  border-bottom: 0.5px solid var(--dsw-alias-border-l3);
  background: var(--dsw-alias-bg-base);
  color: var(--dsw-alias-label-primary);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
  white-space: nowrap;
}

.label { flex: none; color: var(--dsw-alias-label-primary); }
.value { color: var(--dsw-alias-label-primary); font-variant-numeric: tabular-nums; }
```

配套的文案/类变化：删掉 `.lang`（`· Workspace` 英文尾缀）与 `.muted`（弱化色）；locale 去掉 `context.workspace / context.workspaceEn / context.brand`，换成 `context.workspaceLabel`（`工作区：`）与 `context.brandLabel`（`品牌：`），中英各一份（英文为 `Workspace: ` / `Brand: `）。`context.unknownWorkspace` / `context.noBrand` 原样沿用——未知态也是同一档正文黑，不再弱化。

深浅色：颜色全部走 `--dsw-*` token，CSS 里**没有一个硬编码色值**（单测禁 `#hex` / `rgb()` / `hsl()`），所以深色下自动取深色主题的正文色，不会写死黑。

### 8.3 新的渲染文本（真实 DOM 输出）

用真实组件 + 固定 snapshot 渲染、`textContent` 归一化空白后的输出：

```
有品牌        : 工作区：Jack 品牌：Halliday
无品牌        : 工作区：Jack 品牌：未指定
工作区未知    : 工作区：未知 品牌：未指定
名称映射不到  : 工作区：90002 品牌：Halliday
```

真实 DOM（有品牌那条，哈希类名来自 CSS Modules）：

```html
<div class="_bar_235f94" data-context-bar="" data-task="0" role="group" aria-label="当前工作区与品牌">
  <span class="_item_235f94" data-context="workspace">
    <span class="_label_235f94">工作区：</span><span class="_value_235f94" data-context-value="workspace">Jack</span>
  </span>
  <span class="_item_235f94" data-context="brand">
    <span class="_label_235f94">品牌：</span><span class="_value_235f94" data-context-value="brand">Halliday</span>
  </span>
</div>
```

两个字段在同一个 flex 行内、顺序固定 `workspace → brand`（单测断言 `data-context` 顺序），字段之间只有 `gap: 20px`；源码里两个 `<span>` 之间保留了一个真实空格文本节点（`{' '}`），视觉上被 flex 丢弃、只服务读屏与文本断言，所以视觉间距就是 20px，不会被多算。

### 8.4 测试证据

`npx vitest run packages/client/ui-capability-map/tests`：

```
 ✓ |thread-safe| packages/client/ui-capability-map/tests/trace.client.spec.tsx (17 tests)
 ✓ |thread-safe| packages/client/ui-capability-map/tests/next-steps.client.spec.tsx (17 tests)
 ✓ |thread-safe| packages/client/ui-capability-map/tests/trace-filter.client.spec.tsx (11 tests)
 ✓ |thread-safe| packages/client/ui-capability-map/tests/trace-dedupe.client.spec.tsx (18 tests)
 ✓ |thread-safe| packages/client/ui-capability-map/tests/context-bar.client.spec.tsx (31 tests)
 ✓ |thread-safe| packages/client/ui-capability-map/tests/capability-map.client.spec.tsx (16 tests)
 ✓ |thread-safe| packages/client/ui-capability-map/tests/guide.client.spec.tsx (18 tests)

 Test Files  7 passed (7)
      Tests  128 passed (128)
```

121 → 128：**新增 7 条，改写 2 条**（既有的 121 条全部保留通过）。

新增：

| # | 断言 |
|---|---|
| 1 | `workspaceNames()` 从同一份结果解析 `90002 → Jack`（含杂行跳过、prose 文本兜底、无 `workspaces` 返回空） |
| 2 | 折叠层：`account workspaces` 结果同时给出 `workspace: 90002` 与 `workspaceName: 'Jack'` |
| 3 | 折叠层：结果里只有 id、没有对应名字行 → `workspaceName: undefined`（不猜） |
| 4 | 折叠层：新任务清品牌，工作区**和名字**都保留 |
| 5 | 渲染：`工作区：Jack 品牌：Halliday`，且不含 `90002` / `Workspace` |
| 6 | 渲染：名字缺失时回退 `工作区：90002` |
| 7 | 样式：`.bar` 是 `flex` + `justify-content: flex-start` + `gap: 20px`（且落在 16–24px）、没有 `space-between`；字号 13–14px、`font-weight: 600`、三处颜色都是 `var(--dsw-alias-label-primary)`、CSS 里没有 `label-caption / label-tertiary` 弱化色 |

改写 2 条：原来的「左右分列 + 编号」渲染断言，改成「单行 + 名称」；原「10–12px 弱化色」的字号检查改成 13–14px 正文黑（硬编码色 / 动画 / 过渡的禁令保留）。

### 8.5 构建 / 类型 / bundle

| 命令 | 结果 |
|---|---|
| `npx tsc -b tsconfig.client.json` | **exit 0** |
| `pnpm -C apps/desktop run build` | **exit 0**（`lib/main.js` 887.16 kB、welcome 页 built） |
| `pnpm -C packages/client/ui-capability-map run bundle` | **exit 0**（`lib/client.js` 132.22 kB，上一轮 130.77 kB） |

改动文件：`packages/client/ui-capability-map/src/client/{context.ts,ContextBar.tsx,ContextBar.module.css,locales.ts,index.ts}`（`index.ts` 只多导出一个 `workspaceNames`）、`packages/client/ui-capability-map/tests/context-bar.client.spec.tsx`。没有新增依赖、没有新增包、没有改 Host/MCP、没有新增任何网络请求、**未打包**（按纪律）。
