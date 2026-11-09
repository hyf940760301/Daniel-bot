# CHANGES · S6.5 Daniel 全景地图（说明指南 · 只读 · 可预填不执行）

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，基线 `ce7073d5`，已含品牌 / 登录 / 主题 / 执行透视 / 执行轨迹）
> 改动包：`packages/client/ui-capability-map`（既有包内加一层，不新增包、不新增运行时依赖）
> 内容源：`daniel-bot/app/guide/daniel-guide.json`（9 模块 / 31 功能 / 31 句示例话术，措辞已由用户确认）
> 状态：**类型检查 / 桌面构建 / 客户端 bundle / 单测全绿；未打包（按纪律）**
> 一句话：左栏底部多一个地图图标，点开是一本**只读**的 Daniel 说明书；每句示例话术旁边一个「填进对话」，只把话写进输入框，**永远不替你发送**。

---

## 1. 入口与形态

### 1.1 入口（rail 底部）

| 位置 | 形态 | 代码 |
|---|---|---|
| 收起态（48px 竖条） | 底部一个图标按钮，可见文字隐藏，`aria-label="Daniel 全景地图"` | `CapabilityMap.tsx:108`（按钮）、`CapabilityMap.module.css`（`.guideButton` / `.guideLabel`） |
| 展开态（320px 面板） | 面板下方、`readonly.note` 之下的一行「图标 + Daniel 全景地图」 | 同上；两种形态共用同一个按钮元素与同一个 ref |

- 图标是包内自绘的**折页地图**（`CapabilityMap.tsx:191` 的 `MapGlyph`）：`currentColor` 描边，随主题色；primitives 里没有地图/书图标，为避免为一个图标新增依赖，直接画 16×16 的 3 段折线。
- 按钮带 `aria-haspopup="dialog"` 与 `aria-expanded`，键盘可 Tab 到、Enter/Space 可开。

### 1.2 弹窗

| 项 | 实现 |
|---|---|
| 形态 | 居中模态，宽 `min(720px, 100vw - 48px)`，高 `max-height: 80vh`，内部滚动（`GuideMap.module.css` 的 `.dialog.dialog`） |
| 语义 | `role="dialog"` + `aria-modal="true"` + `aria-label="Daniel 全景地图"`（由共享 `Modal` 组件给出，`GuideMap.tsx:90`） |
| 结构 | 标题行（标题 + 副标题 + 关闭） → 搜索行 → 左「9 个模块」/ 右「该模块的功能卡片」 → 只读说明脚注 |
| 功能卡片 | 功能名 + 一句话 + 「示例话术」+ 原句 + 「填进对话」按钮 |
| 搜索 | 顶部 `type="search"`，**本地过滤**：模块名 / 功能名 / 示例话术；不打接口（测试用 `fetch` 桩断言零调用） |
| 空态 | 无命中时右侧显示「没有找到匹配的内容 / 换个词试试，或清空搜索看全部九个模块。」，`role="status"` |
| 遮罩 / Esc / 关闭按钮 | 三条都关；关闭后焦点回到触发按钮（见 §3.4） |

> 弹窗**只读**：不发请求、不改数据、不调工具；唯一的写动作是往输入框写草稿（§3）。

---

## 2. 内容与生成规则

### 2.1 生成器

```bash
# 生成（内容源在应用工程里，绝对路径由调用方给）
node packages/client/ui-capability-map/scripts/build-guide.mjs \
  --from "/Users/…/daniel-bot/app/guide/daniel-guide.json"

# 校验（CI / 提交前）：重新渲染并与已提交文件逐字节比对
node packages/client/ui-capability-map/scripts/build-guide.mjs --from <同一个文件> --check
```

- 产出：`packages/client/ui-capability-map/src/client/guide.generated.ts`（`GUIDE`，含 9/31/31 与两枚摘要）。
- 包脚本：`pnpm -C packages/client/ui-capability-map run guide:build`。
- 同样是「内容烘焙进包」而不是运行时读文件：只有装了应用、没有仓库的机器也要能打开这本说明书（与 `build-module-map.mjs` 同一条规矩）。

### 2.2 生成期断言（`scripts/build-guide.mjs:129` 起）

1. `schema` 必须是 `daniel.guide.v1`；模块**恰好 9 个**，id/名称唯一；
2. 每个模块 **≥ 2 个功能**（保证左栏每一行点开都不是空页），模块内功能名唯一；
3. 示例话术**非空、单行、≤ 40 字**（按码点计数，`[...text].length`，emoji 不重复计）；
4. 文案**不含**内部标记：反引号、`_`、`--`、`.ts`、`.json`；
5. 文案**不含命令拼写**（小写多词 ASCII，如 `brands list`）与工具名（`daniel_…`）、内部词（`argv` / `mcpTool` / `sha256` / `workflow-map`）；`YouTube`、`Halliday`、`90002` 这类业务词照常允许；
6. 话术**逐字发布**：生成器不 trim、不改写，首尾有空白直接判失败（弹窗要原样预填，任何"顺手整理"都是 bug）。

### 2.3 防手改漂移（两道闸）

| 闸 | 机制 | 拦什么 |
|---|---|---|
| 内容摘要 `source.digest` | 生成时对「模块 → 功能 → 话术」规范化 JSON 取 sha256，写进生成文件；单测用同一函数重算并比对（`tests/guide.client.spec.tsx` 的 `matches the authored guide and its content digest`） | 有人手改 `guide.generated.ts` 里的某句话术却没重新生成 |
| `--check` 逐字节比对 | 用源 JSON 重新渲染，与已提交文件比字节；不一致即退出码 1（`build-guide.mjs:278` 起） | 源 JSON 改了、生成文件没跟着改 |

另外 `source.sha256` 记录源文件摘要，一眼能看出这份生成物对应哪一版内容源。

---

## 3. 预填「填进对话」：先侦察，再选路

### 3.1 三条候选，逐一实测

| 候选 | 源码事实 | 结论 |
|---|---|---|
| **① chat / composer 的公开 action** | Conversation 插件把「每个会话的输入机」发布在会话作用域上：`ctx.conversation.input`（`packages/client/ui-conversation/src/client/service.ts:42`），`input.for(scope)` 取到该会话的 `SessionInput`（`packages/client/ui-conversation/src/client/input/hub.ts:75`）；`SessionInput` 上明确有 `setDraft(text)`（`.../client/contract/input.ts:189`），实现处注释写着「Replace the whole draft (**persisted-draft seed and programmatic writes**)」（`.../client/input/facade.ts:223`）。仓库里已有跨插件这么用的先例：`packages/experimental/client-ui-forge/src/client/mount.ts:121`（`conversation.input.for(scope)` + `insertQuote` + `focus`） | ✅ **采用** |
| ② 复制到剪贴板 + 轻提示 | 任何环境都能跑，但把「填进对话」降级成「你自己粘贴」，用户体验差一档 | ⏸ 未采用（保留为将来 shell 无 composer 时的备选，见 §3.4） |
| ③ 直接拒绝该能力 | 最保守，但用户要的就是"能预填" | ⏸ 未采用 |
| ❌ 查 DOM / 派发键盘事件塞 contenteditable | 输入框是 Lexical 托管的 contenteditable，DOM 直写会与编辑器状态脱节；且本任务明令禁止 | ❌ 禁止 |

### 3.2 采用的路径（一句话）

`rail 注入的 prefill(phrase)` → `prefillDraft(ctx.sessions, phrase)` → 取 `mainView` 保留的当前会话（复用 `trace.ts` 的 `currentSessionId`，与 Session Controller 同口径）→ `sessions.scope(id)` → `scope.get('conversation')` → `conversation.input.for(scope)` → **`setDraft(...)`** → `focus()`。

关键实现位置：

| 环节 | 位置 |
|---|---|
| 服务入口（公开服务，不是全局） | `packages/client/ui-conversation/src/client/service.ts:42`（`readonly input: SessionInputResolver`） |
| 按会话取输入机 | `packages/client/ui-conversation/src/client/input/hub.ts:75`（`for(actx)`，未保留的会话会抛错） |
| 写草稿的公开动词 | `packages/client/ui-conversation/src/client/contract/input.ts:189`；实现 `.../input/facade.ts:223` |
| 先把焦点交还输入框 | `.../input/facade.ts` 的 `focus()`（Lexical 自己的 `editor.focus()`，不是 `document.querySelector(...).focus()`） |
| 本包桥接 | `packages/client/ui-capability-map/src/client/prefill.ts:77`（`prefillDraft`）、`:104`（`focusComposer`） |
| 注入给 rail | `packages/client/ui-capability-map/src/client/index.ts:75-76`（`prefill` / `focusChat` 走 slot 的 `inject` 面，渲染器把它绑成组件 props） |

> 结构上本包**不依赖** `ui-conversation`：`scope.get('conversation')` 以结构类型惰性解析（`prefill.ts` 顶部注释），`package.json` 的 `dsh.client.inject` 未新增任何一项，`dependencies` 未新增任何一条。

### 3.3 语义与降级

| 情形 | 行为 |
|---|---|
| 输入框是空的 | 草稿 = 该句示例话术（逐字） |
| 用户已经打了字 | **保留**已打的字，另起一行追加该句（覆盖用户输入比多一行更糟）；`setDraft` 会清掉行内引用 chip，这是该 API 的既有语义 |
| 没有当前会话 / 没有 composer / 插件未加载 | 返回 `unavailable`：弹窗**不关**，脚注上方出现 `role="status"` 提示「当前没有可用的对话输入框，先打开一个对话再试。」 |
| 预填成功 | 关弹窗，并把焦点交还输入框（见 §3.4） |
| 任何情况 | **不调 `submit()`、不调 `send()`、不发请求、不调工具**——草稿在浏览器里，只有人按回车才会发出去 |

### 3.4 焦点为什么需要两段

共享 `Modal` 的 `useModalLayer` 在卸载时会把焦点还给打开它的元素（`packages/client/ui-primitives/src/useModalLayer.ts`，`pendingRestore` 分支）。所以：

- 普通关闭（Esc / 遮罩 / 关闭按钮）→ 弹窗卸载后，rail 自己的 effect（`CapabilityMap.tsx:93`）把焦点交回**地图按钮**；
- 预填成功关闭 → `closeGuide('composer')` 记下目标，卸载后调 `focusChat()` 把焦点**重新交给输入框**（否则会被 modal 层的"还给 opener"覆盖）。

测试里两条都断言了（`returns focus to the trigger` / `writes the exact phrase…` 后的 `focusChat` 调用）。

---

## 4. 可访问性

| 项 | 做法 | 证据 |
|---|---|---|
| 对话框语义 | `role="dialog"` + `aria-modal="true"` + `aria-label`（标题） | `GuideMap.tsx:90`，测试断言两者 |
| 初始焦点 | 搜索框带 `data-modal-autofocus`，Modal 打开即聚焦 | `GuideMap.tsx:105`；测试 `lands focus in the search box` |
| Esc | 由 modal 层统一接管（顶层才响应），关闭后焦点回归 | 测试 `closes on Escape and returns focus to the trigger` |
| 遮罩点击 | 同一条 `onClose` 路径 | 测试 `closes on the mask and on the close control` |
| 焦点陷阱 | modal 层把 Tab 收回卡内 | 测试 `keeps Tab inside the dialog` |
| 模块列表 | `<nav aria-label="模块">` + 每项 `aria-pressed` 表示当前选中 | `GuideMap.tsx:121` |
| 空态 / 失败提示 | `role="status"`，读屏可播报 | `GuideMap.tsx:136`、`:167` |
| 触发按钮 | `aria-label`、`aria-haspopup="dialog"`、`aria-expanded` | `CapabilityMap.tsx:111-113` |
| 键盘 | 全部控件是原生 `button` / `input`，Tab 序即视觉序 | — |
| 焦点可见 | `:focus-visible` 用主题 focus-ring token（不被裁切） | `GuideMap.module.css` 末尾 |

---

## 5. 视觉

- **只用 `--dsw-*` token**：颜色全部走 `var(--dsw-alias-…)`，圆角走 `var(--dsw-radius-…)`，焦点环走 `--dsw-focus-ring-*`；`GuideMap.module.css` 里没有任何 `#hex` / `rgb()` / `hsl()`，单测逐行扫描颜色声明（`uses only theme tokens for colour in light and dark`）。
- **深浅色都成立**：没有一处按 `prefers-color-scheme` 写分支，全部由主题变量决定；迁移到 Daniel 配色同样不需要改这份 CSS。
- **`prefers-reduced-motion` 下无动画**：本组件 CSS **零** `animation` / `transition`（单测直接断言不存在）；共享 `Modal` 自带的一次淡入由它自己的 `@media (prefers-reduced-motion: reduce) { … animation: none }` 关掉（单测断言那段规则存在）。
- 弹窗尺寸：720px 宽、80vh 高、内部两栏各自滚动；标题/搜索/脚注不滚。

---

## 6. 测试与证据

### 6.1 命令与退出码

```text
$ tsc -b tsconfig.client.json
（无输出）
tsc-exit=0

$ pnpm -C apps/desktop run build
…
✓ built in 333ms
desktop-build-exit=0

$ pnpm -C packages/client/ui-capability-map run bundle
✔ [@deepseek-ai/dsh-client-ui-capability-map/client] Build complete in 55ms
bundle-exit=0

$ npx vitest run packages/client/ui-capability-map/tests/
 ✓ trace.client.spec.tsx (17 tests)
 ✓ capability-map.client.spec.tsx (16 tests)
 ✓ guide.client.spec.tsx (18 tests)
 Test Files  3 passed (3)
      Tests  51 passed (51)
```

`guide.client.spec.tsx` 18 条覆盖：打开 + 初始焦点、Esc 关闭 + 焦点回归、遮罩/关闭按钮、Tab 陷阱、9 模块与功能卡片、切换模块、搜索过滤（模块名/功能名/话术 + 零 fetch）、空态、31 条内容断言、预填并关闭、无 composer 的提示、桥接（setDraft/focus/不 submit 不 send）、已有草稿追加、无会话降级、内容与摘要一致、生成器三种非法输入、无动画、token 颜色。

### 6.2 「不会自动发送」的断言原文

```ts
// 组件层：点了「填进对话」之后，只有 prefill 被调用；没有任何发送面
expect(prefill).toHaveBeenCalledTimes(1)
expect(prefill).toHaveBeenCalledWith('把我的品牌都列出来')
expect(focusChat).toHaveBeenCalledTimes(1)
expect(fetchMock).not.toHaveBeenCalled()
expect(socketMock).not.toHaveBeenCalled()
expect(document.querySelector('[data-command]')).toBeNull()
expect(screen.queryByRole('dialog')).toBeNull()

// 桥接层：录音 composer 上 submit/send 计数器必须保持 0
expect(calls.setDraft).toEqual(['我现在登录的是哪个账号？'])
expect(calls.focus).toBe(1)
expect(calls.submit).toBe(0)
expect(calls.send).toBe(0)
```

### 6.3 生成器失败示例（故意把一句示例话术改到 45 字）

```text
$ node packages/client/ui-capability-map/scripts/build-guide.mjs --from /tmp/guide-broken.json
exit=1
[stderr]
build-guide: 品牌资产 的功能 1（看品牌清单）的示例话术 45 字，超过 40 字上限：把我的品牌都列出来，顺便把每个品牌的竞品、名单、声量份额和最近的视频数据也一起整理好发给我
```

改内容源、不重新生成时（`--check`）：

```text
$ node …/build-guide.mjs --from /tmp/guide-drift.json --check
exit=1
[stderr]
build-guide: 生成结果与指南不一致（内容漂移），请重新生成并一起提交
```

同一份源正常时：

```text
$ node …/build-guide.mjs --from "<…>/daniel-guide.json" --check
build-guide: 生成结果与指南一致
check-exit=0
```

### 6.4 弹窗渲染文本示例（切到「品牌资产」，前两张卡）

```text
Daniel 全景地图 | 品牌资产
看品牌清单   列出账号可见的全部品牌   示例话术 把我的品牌都列出来   填进对话
看品牌档案   简介、目标市场、频道、售价区间   示例话术 Halliday 这个品牌是做什么的？   填进对话
```

左栏九行（含每行功能数）：

```text
账号与工作区 3 项 / 品牌资产 4 项 / 红人检索 3 项 / 红人名单 4 项 / 真实性与背调 2 项
合作追踪 4 项 / 品牌提及 3 项 / 内容情报 4 项 / 声量份额 4 项
```

---

## 7. 文件清单

新增：

| 文件 | 作用 |
|---|---|
| `packages/client/ui-capability-map/scripts/build-guide.mjs` | 内容生成器 + 断言 + 摘要 + `--check` |
| `packages/client/ui-capability-map/scripts/build-guide.d.mts` | 生成器的类型声明（测试直接 import `.mjs`，无需 `allowJs`） |
| `packages/client/ui-capability-map/src/client/guide.generated.ts` | 生成物（9 / 31 / 31） |
| `packages/client/ui-capability-map/src/client/GuideMap.tsx` | 弹窗组件 + 本地过滤 |
| `packages/client/ui-capability-map/src/client/GuideMap.module.css` | 弹窗样式（纯 token、零动画） |
| `packages/client/ui-capability-map/src/client/prefill.ts` | 预填桥接（`setDraft` + `focus`）与降级 |
| `packages/client/ui-capability-map/tests/guide.client.spec.tsx` | 18 条单测 |
| `packages/client/ui-capability-map/tests/fixtures/daniel-guide.json` | 内容源快照（与 `daniel-bot/app/guide/daniel-guide.json` 同 sha256，供测试在仓库内复算） |

修改：

| 文件 | 改动 |
|---|---|
| `packages/client/ui-capability-map/src/client/CapabilityMap.tsx` | 底部地图按钮、弹窗挂载、关闭后的焦点去向、`MapGlyph` |
| `packages/client/ui-capability-map/src/client/CapabilityMap.module.css` | `.guideButton` / `.guideIcon` / `.guideLabel` 与 focus-ring |
| `packages/client/ui-capability-map/src/client/index.ts` | 导出新面；`inject` 面加 `prefill` / `focusChat` |
| `packages/client/ui-capability-map/src/client/locales.ts` | 新增 `guide.*` 文案（zh + en） |
| `packages/client/ui-capability-map/src/client/types.ts` | `GuideFunction` / `GuideModule` / `GuideData` / `GUIDE_SCHEMA` |
| `packages/client/ui-capability-map/package.json` | 加 `guide:build` 脚本（无新依赖） |
| `packages/client/ui-capability-map/tests/capability-map.client.spec.tsx` | 两处"面板内按钮数"注释更新（面板内仍只有折叠按钮；地图按钮在面板下方） |

---

## 8. 已知限制 / 明确不做

1. **不打包**（按纪律），只交工作树与构建证据。
2. 文案目前是**中文原文**（内容源即中文）；`locales.ts` 只补了界面壳文案的 zh/en，模块与话术不做机翻——它们是要被原样填进对话的句子，翻译会改变语义。
3. 没有"技术视图"：不展示命令名、字段名、参数；生成期断言挡住这些字符串。
4. 输入框里已有**行内引用 chip** 时，`setDraft` 会按该 API 的既有语义清掉 chip（草稿文字保留）。若将来需要"保留 chip 追加"，应改用 `inputActions.insertText` + `captureInsertion`（同一服务，会话作用域组件的公开面），本层不私接。
5. 预填只在有**当前会话**（`mainView` 保留）时可用；新建空会话尚未进入主视图时按 `unavailable` 处理，并提示先打开一个对话。
