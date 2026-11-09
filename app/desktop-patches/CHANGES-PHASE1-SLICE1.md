# 阶段 1 · 第一批（SLICE 1）交互改动

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，Daniel Bot）
> 设计依据：`daniel-bot/specs/PHASE1-INTERACTION-DESIGN.md` §1.1 / §1.3 / §3.1–§3.4 / §5.1 / §7
> 状态：**类型检查 / 构建 / 单测已跑（见 §4）；未打包 DMG（按纪律）**
> 一句话：默认姿态改成「对话是唯一主交互区」——左栏 48px 只留一个「能做什么」，空态从 3 条泛示例换成 5 句能直接开工的业务句，输入框旁和空态底部各补一个「能做什么」入口。

---

## 1. 本批做了什么（只这 4 条 + 2 处支撑）

| # | 设计稿条目 | 改前 | 改后 |
|---|---|---|---|
| 1 | §1.1 / §1.3 左栏收起态 | 48px 条上**两个**入口：竖向「执行透视」（18px 图标）+ 底部 38px「Daniel 全景地图」按钮 | **只剩一个入口**：22px 图标 + 竖排 13px「能做什么」；底部按钮删除；不露模块名、不露进度、不露第二个按钮 |
| 2 | §3.1 / §3.2 / §3.3 空态 | 主标题「开始一个新任务」+「Daniel 会调用对应能力去完成」+ 3 条泛示例（工作区 / 竞品 / 找红人）+ 通用 placeholder | 主标题「你想先做哪件事？」+「说一句就行，我直接给你能用的结果：名单、邮件、判断，马上能拿去用。」+ **5 句业务示例**（2 列网格，≥640px）+ placeholder「直接说你要做什么，比如：找 10 个做智能戒指的 TikTok 红人」 |
| 3 | §3.4 / D-078 两个入口 | 只有左栏一个入口（<768 左栏整列消失 → 无入口） | ① 输入框控制行左侧 `conversation.input.left`（list 槽位，原先无人占用）13px「能做什么」；② 空态底部（输入卡下方）「不知道从哪开始？看看能做什么 →」 |
| 4 | §5.1 差异 #5 副标题 | 「说说你想做什么，Daniel 会调用对应能力去完成。」 | 「说一句就行，我直接给你能用的结果：名单、邮件、判断，马上能拿去用。」 |

**两处支撑改动（不新增业务）：

- **左栏开合状态从「AppFrame 私有 useState」提到布局 store**（设计 §5.1 第 11 条）。不这么做，输入框旁与空态底部的入口点了没反应。新增 `ctx.layout.openRail()`（只发请求、不持久化；框架的列宽求解仍可回落 48px）。
- **空态底部新增一个 single 槽位** `conversation.hero.capability`（root 作用域，只在 hero 阶段渲染）。官方包只负责「留位置」，文案与点击行为都由 `ui-capability-map` 提供，避免把 Daniel 话术写进官方包。

### 点击行为（按 Jack 裁决，覆盖设计稿默认）

- 空态 5 句示例：**只填入输入框 + 聚焦，不发送**（沿用 `prefillExampleDraft`：`setDraft` → `focus`，签名里没有 submit/send）。
- 两个「能做什么」入口：**≥1024 打开 320 左栏；<1024（含 <768 左栏整列消失）打开 720 全景模态**；两者是同一份 `GuideMap` 内容，两种呈现（§1.2 降级规则）。

---

## 2. 改动文件

| 文件 | 改了什么 |
|---|---|
| `packages/client/ui-layout/src/client/stores.ts` | `layoutInfo.railOpen`（内存态、不持久化）+ `setRailOpen` / `toggleRail` 两个 action |
| `packages/client/ui-layout/src/client/service.ts` | `ILayout.openRail()` + `LayoutController.openRail()` |
| `packages/client/ui-layout/src/client/AppFrame.tsx` | 左栏展开请求从 `useState` 改读 store（外部入口可驱动），`onToggle` 走 `actions.toggleRail()` |
| `packages/client/ui-capability-map/src/client/CapabilityMap.tsx` | 收起态删掉第二个按钮、去掉 chevron；图标 18→22px；加 `title` 浮层提示 |
| `packages/client/ui-capability-map/src/client/CapabilityMap.module.css` | 删 `.railChevron` 与「收起态 guideButton」两段死样式；补注释 |
| `packages/client/ui-capability-map/src/client/CapabilityEntry.tsx` | **新增**：两个入口共用组件 + `capabilityRoute()` 宽度路由（1024 分界）+ 模态聚焦归还 |
| `packages/client/ui-capability-map/src/client/CapabilityEntry.module.css` | **新增**：13px 文字按钮（输入行浅色、空态底行更弱），只用主题 token |
| `packages/client/ui-capability-map/src/client/locales.ts` | `rail.title`/`map.open`→「能做什么」；新增 `rail.entryHint` / `entry.open` / `hero.more`（zh + en） |
| `packages/client/ui-capability-map/src/client/index.ts` | `inject` 增加 `layout`；注册 `conversation.input.left` 与 `conversation.hero.capability` 两个入口；导出新符号 |
| `packages/client/ui-capability-map/package.json` | `dsh.client.inject` 增加 `@deepseek-ai/dsh-client-ui-layout`（加载顺序） |
| `packages/client/ui-conversation/src/client/skeleton/EmptyHero.tsx` | 示例 key 改为 `hero.example.1`–`.5`；注释同步（点击=填入不发送） |
| `packages/client/ui-conversation/src/client/skeleton/HeroShell.module.css` | 示例区 `flex 单列` → `grid`：<640 单列、≥640 两列；卡片 `min-height:44px`、不截断 |
| `packages/client/ui-conversation/src/client/skeleton/ConversationContent.tsx` | hero 阶段在输入卡下方渲染 `conversation.hero.capability` |
| `packages/client/ui-conversation/src/client/skeleton/ConversationRoot.module.css` | 新增 `.heroCapability`（左对齐、20px 左缩进、空则不占位） |
| `packages/client/ui-conversation/src/client/contract/slots.ts` | `SlotMap` + `SlotFactoryMap` 声明 `conversation.hero.capability`（single / root） |
| `packages/client/ui-conversation/src/client/apply.ts` | factory children 增加该槽位 |
| `packages/client/ui-conversation/src/client/locales.ts` | 8 语言：标题 / 副标题 / 5 示例 / hero placeholder 全量替换（旧 3 示例 key 删除） |
| `packages/client/ui-layout/tests/*` | 初始快照补 `railOpen`；新增 store 开关测试、`openRail` 服务测试、AppFrame「外部请求也能展开」测试 |
| `packages/client/ui-capability-map/tests/capability-map.client.spec.tsx` | 收起态改为「断言只有一个入口 + 22px 图标 + 文案」；新增 5 条入口/路由/不发送测试；注册测试补两个入口 |
| `packages/client/ui-capability-map/tests/guide.client.spec.tsx` | 模态改为从空态入口打开（窄窗），焦点归还断言改到该入口 |
| `packages/client/ui-capability-map/tests/context-bar.client.spec.tsx` / `next-steps.client.spec.tsx` | 注册测试补 `layout` 服务（插件新依赖） |
| `packages/client/ui-conversation/tests/skeleton.client.spec.tsx` | 标题/副标题/5 示例/点击断言更新；新增「底部入口在输入卡之后且只在空态」「2 列网格且不截断」「业务 placeholder」3 条 |
| `packages/client/ui-sidebar/tests/panel-list.client.spec.tsx` / `packages/client/ui-workspace/tests/workspaces-service.client.spec.ts` | 两个测试的 `ILayout` / action 假实现补 `openRail` / `setRailOpen` / `toggleRail`（接口扩张的机械连带） |
| `daniel-bot/specs/PHASE1-INTERACTION-DESIGN.md` | §7 增加「已裁决」列（1/2 条按 Jack 裁决）；§3.1「点击示例」改「只填入 + 聚焦」并回指 §7 |
| `daniel-bot/app/desktop-patches/CHANGES-PHASE1-SLICE1.md` | 本文 |

没有新增依赖、没有新增包、没有动 `trace.ts`（D-077 的修复保持原样）。

---

## 3. 结构示意

### 3.1 48px 收起态（真实渲染，已删除临时 dump 用例）

```html
<div class="_dock" data-capability-map="collapsed" data-rail-width="48">
  <button type="button" class="_rail" data-rail-entry=""
          aria-expanded="false" aria-label="能做什么" title="能做什么 · 9 类营销任务">
    <span class="_railIcon" aria-hidden="true">
      <svg width="22" height="22" data-icon="dsw-icon-checklist-outline-regular"><use href="#…"/></svg>
    </span>
    <span class="_railTitle">能做什么</span>
  </button>
</div>
```

`div` 下**只有 1 个 button**（测试断言 `querySelectorAll('button').length === 1`）；原先底部的「Daniel 全景地图」按钮不再挂载。

### 3.2 入口路由

```
点击「能做什么」
  ├─ window.innerWidth >= 1024 → ctx.layout.openRail() → 左栏 320（框架列宽求解仍可回落 48）
  └─ window.innerWidth <  1024 → 同一份 GuideMap 以 720 模态打开（min(720px, 100vw−48px)）
```

### 3.3 空态

```
你想先做哪件事？
说一句就行，我直接给你能用的结果：名单、邮件、判断，马上能拿去用。
┌──────────────────────────────┐ ┌──────────────────────────────┐
│ 找 20 个做智能眼镜测评的…      │ │ 给 @CasandChary 写一封…        │   ≥640px 两列
└──────────────────────────────┘ └──────────────────────────────┘
┌──────────────────────────────┐ ┌──────────────────────────────┐
│ 看看 @TechRax 有没有刷量…      │ │ Halliday 在 Reddit 上被怎么…   │
└──────────────────────────────┘ └──────────────────────────────┘
┌──────────────────────────────┐
│ 他一条视频报 3000 美元…        │
└──────────────────────────────┘
                    [ 直接说你要做什么，比如：找 10 个做智能戒指的 TikTok 红人 ]
不知道从哪开始？看看能做什么 →                      （13px 次要色，左对齐）
```

---

## 4. 测试与构建证据（真实输出）

### 4.1 类型检查

```console
$ pnpm exec tsc -b tsconfig.client.json
exit=0        # 0 条 error TS
```

### 4.2 桌面构建

```console
$ pnpm -C apps/desktop run build
exit=0        # tsc -b 通过 + tsdown bundle 完成
```

两个改动的客户端包单独过一遍产物构建（桌面壳直接用这些 lib 产物）：

```console
$ pnpm -C packages/client/ui-capability-map run bundle   → exit=0（lib/client.js 146.84 kB）
$ pnpm -C packages/client/ui-conversation   run bundle   → exit=0（lib/client.js 943.96 kB）
# 产物回读：ui-conversation/lib/client.js 含「你想先做哪件事」1 处；
#           ui-capability-map/lib/client.js 含「能做什么 · 9 类营销任务」1 处、「不知道从哪开始？看看能做什么」2 处
```

### 4.3 单测（本批涉及的包全绿）

```console
$ pnpm exec vitest run packages/client/ui-capability-map packages/client/ui-conversation
 Test Files  61 passed (61)
      Tests  1053 passed (1053)
      exit=0

$ pnpm exec vitest run packages/client/ui-layout
 Test Files  7 passed (7)
      Tests  143 passed (143)
```

基线对照：改动前同一命令为 `61 files / 1045 tests`，本批净增 **8 条**：

| 包 | 新增测试 |
|---|---|
| ui-capability-map | ① 1024 分界路由（1440/1024 → 抽屉，1023/768/390 → 模态）② 宽窗点击只发 `openRail`、不弹模态 ③ 窄窗点击弹同一份 720 指南、关闭后焦点回到入口 ④ 空态底行用 hero 变体与文案 ⑤ 指南「填进对话」只预填不发送 |
| ui-conversation | ⑥ 底部入口在输入卡**之后**渲染、且只在空态 ⑦ 示例区 ≥640 两列、卡片不截断 ⑧ 空态输入框 placeholder 为业务句（`aria-label` 断言） |
| ui-layout | ⑨ 外部 `setRailOpen` 请求也能把 48 展开到 320（并附 store 开关、`openRail` 服务测试） |

既有断言改写（不是新增）：左栏收起态「只有一个入口 + 22px 图标」、中英标题/副标题、5 条示例、点击示例写入草稿不发送、模态焦点归还。

### 4.4 空态渲染文本（真实 DOM 文本）

```
你想先做哪件事？
说一句就行，我直接给你能用的结果：名单、邮件、判断，马上能拿去用。
找 20 个做智能眼镜测评的美国 YouTube 红人，10 万粉以上
给 @CasandChary 写一封首封 pitch，推 Halliday 的智能眼镜
看看 @TechRax 这个号有没有刷量，粉丝是不是真的
Halliday 在 Reddit 上被怎么评价，负面集中在哪
他一条视频报 3000 美元，这个价格贵不贵，该还到多少
```

placeholder：`直接说你要做什么，比如：找 10 个做智能戒指的 TikTok 红人`（测试断言文本输入框的 `aria-label` 等于该句）。

---

## 5. 风险与已知落差

| # | 风险 / 落差 | 影响 | 处置 |
|---|---|---|---|
| 1 | **1024–1439 且右侧栏占满**时，320 展开会被框架回落 48px，此时点击「能做什么」不会自动改开模态（§1.2「降级不静默」未实现） | 窄窗 + 右栏同开是少数路径，点击表现为「没反应」 | 本批不做；需给 `ILayout` 增加「已解析的 rail 是否真的展开」可观测值，属设计 §5.1 第 11 条的后续；已在 §6 待办登记 |
| 2 | 展开面板标题仍是「执行透视」，与入口文案「能做什么」不同名 | 点开后标题语义不一致 | 展开面板要换成「5 组任务 + 搜索」的任务地图（§5.1 第 2 条，本批范围外），届时一并改名；本批只动 48px 条 |
| 3 | 空态示例的 5 句 + 新副标题在 8 个语言字典里都换了（ja/es/fr/de/ru/pt 为意译，非官方译审） | 非中文界面文案质量取决于意译 | 先保证 key 完整、语义与中文一致；上线前建议母语审校一遍 |
| 4 | 改的是官方包 `ui-conversation`（EmptyHero / locales / 槽位） | DSH 升级会覆盖（§8.4 零侵入的长期债，设计 §5.1 第 4/5 条已认定） | 新逻辑尽量薄：文案在官方 locales、入口实现全在 `ui-capability-map`；升级时只需重放这两处 |
| 5 | `ctx.layout` 接口扩张（+`openRail`） | 其它包若自造 `ILayout` 假实现会类型报错 | 本批已修 ui-sidebar / ui-workspace 两个测试假实现；运行时无破坏（新方法只增不改） |
| 6 | 环境前提：`packages/client/ui-capability-map/node_modules` 在本机缺失（6 个测试文件报 `Failed to resolve import "react"`） | 本批开工前该包测试本身就是红的 | 已按 pnpm 目录布局补齐链接（react / react-dom / @testing-library / workspace 包），未改任何源码；换机或重装依赖后此修复自动消失 |
| 7 | `ui-sidebar` 的 `sidebar-root` / `sidebar-snapshot` 用例仍红（期望文案 `DSH Local Build`） | 与本批无关（品牌改名遗留），但会让全量测试看起来不干净 | 未在本批处理；本批只保证「我改过的 sidebar 用例（panel-list）+ ui-workspace 全绿」（17 files / 549 tests） |

---

## 6. 本批未做（明确划界）

- 左栏展开面板的内容重构（5 组业务任务 + 搜索 + 切 tab2）→ §5.1 第 2/3 条。
- 结果区：「说明与下一步」折叠区、反馈行、结果级依据面板 → §5.1 第 9/10 条。
- 业务思路折叠区「只第 1 个结果默认展开」的运行时逻辑（裁决 #1）→ 依赖折叠区存在，属下一批。
- 未登录提示、首次使用小字提示 → §3.5 / §3.6，本批不含。
- 打包 DMG → 按纪律不做。
