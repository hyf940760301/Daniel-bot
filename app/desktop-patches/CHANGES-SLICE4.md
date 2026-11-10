# 阶段 1 · 第四批（SLICE 4）：写入确认条 + 点踩后的真重做

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，Daniel Bot）
> 设计依据：`daniel-bot/specs/PHASE1-INTERACTION-DESIGN.md` §2.1 第 3 块、§9.4、§7.2；实现记录见该文件 §12
> 状态：**类型检查 / 桌面构建 / 客户端 bundle / 单测全绿（见 §6）；未打包 DMG（按纪律）**
> 一句话：写入类下一步不再只是一张「点一下填进输入框」的卡 —— 多了一条 56–72px 的确认条，把「写到哪个工作区 › 哪个品牌 › 哪个名单（多少人）」说清楚；点「确认执行」只发一条用户消息，模型仍要先出写入计划、用户再确认才 commit。点踩后的四个原因各长出一个真「重做」按钮，点一次发一条固定指令、记一条 `action=retry`，同一结果 30 秒只做一次；旧结果一个字都不删。

---

## 1. 本批做了什么（3 块）

| # | 设计稿条目 | 改前 | 改后 |
|---|---|---|---|
| 1 | §2.1 第 3 块 · 写入确认条 | 写入类下一步只有一张建议卡；落点仅卡上一行小字，点了只填输入框 | 结果区多一条**常驻确认条**（56–72px）：`将写入 jack › Halliday › 第十一批（12 人）`＋「确认执行」「先不做」；缺落点 → 确认禁用＋「先补全落点」 |
| 2 | 写链纪律 · 写入是选择题 | 无确认条，也无第二条消息通路 | 「确认执行」**只发一条用户消息**：`执行这个写入：…`。客户端没有工具句柄，模型照旧先 plan、用户再确认、才 commit |
| 3 | §7.2 · 点踩即时重做 | 四个原因各有两个「动作」按钮，点了只记日志，不重跑 | 每个原因**一个「重做」**：发一条固定指令（4 条文案见 §4），记 `action=retry`；同一结果 30 秒一次，重复点提示「刚重做过，稍等」；旧结果保留，新结果作为新 Turn |

**明确不做**：点「确认执行」后直接执行写入（永远不做，写链必须两段式）；真打包 DMG；重做时自动重放旧工具调用。

---

## 2. 改动文件

### 2.1 客户端插件（`packages/client/ui-capability-map`）

| 文件 | 改了什么 |
|---|---|
| `src/client/write-confirm.ts` | **新增**：把写入类下一步解析成 `WriteDraft`（工作区 › 品牌 › 名单 ＋ 人数）；`writeDraftOf` / `missingTargetOf` / `isWriteComplete` / `writeMessageOf`；动词尾巴不当名单名（「加入名单」→ 名单缺失，不猜） |
| `src/client/WriteConfirm.tsx` | **新增**：确认条组件。三态：可确认 / 缺落点（禁用＋提示）/ 已发出；「先不做」折叠成 32px 一行；确认与折叠都不碰工具，只发消息 / 只记反馈 |
| `src/client/retry.ts` | **新增**：4 条固定重做指令、`retryMessageOf`、30 秒窗口（`claimRetry` / `releaseRetry` / `resetRetryThrottle`） |
| `src/client/send-message.ts` | **新增**：本包唯一的发送路径。只从会话 scope 取 `conversation` 并 `send(text)`；无 scope / 无会话 / 被拒都落成值，不抛 |
| `src/client/ResultNotes.tsx` | 结果区接入确认条（在缺失提示之后、折叠区之前）；有确认条时不再叠只读写入预览；反馈行的「已记录」行改为一个「重做」按钮（带原因说明与节流提示） |
| `src/client/ResultNotes.module.css` | 确认条 56–72px（折叠态 32px）、两个按钮、状态行、重做说明/提示；全部主题 token |
| `src/client/feedback.ts` | `FeedbackAction` 追加 `retry` / `decline`；旧 8 个 id 保留（历史记录可读） |
| `src/client/locales.ts` | zh / en 各新增 13 个 `write.confirm.*` / `retry.*` key；`write.preview.body` 改为「确认之后才会写入」 |
| `src/client/index.ts` | 注入 `sendMessage`（`sendUserMessage(ctx.sessions, sessionId, …)`）；导出新的公开 API |
| `tests/slice4.client.spec.tsx` | **新增 23 条**：纯解析 6、DOM 9、重做 5、发送路径 3 |
| `tests/slice4-evidence.client.spec.tsx` | **新增 3 条**（默认 skip，`DSH_SLICE4=1` 打印真实 DOM/消息/节流） |
| `tests/result-notes.client.spec.tsx` | 2 处**计划内**断言更新（两按钮占位 → 一个「重做」；新用例断言消息与节流）；`props` 补 `sendMessage` |
| `lib/client.js` | 重新 bundle（307,451 B），否则运行时仍读旧包 |

### 2.2 桌面主进程（`apps/desktop`）

| 文件 | 改了什么 |
|---|---|
| `src/daniel-feedback-api.ts` | 动作词表追加 `retry` / `decline`；新增 `DANIEL_FEEDBACK_RETRY_REASONS`（四个原因都可重做） |
| `src/daniel-feedback.ts` | 校验规则：`retry` 必须带四选一 reason；`decline` 不带 reason 且允许 `down` 无 reason；单条仍逐字段校验、未知字段丢弃 |
| `tests/daniel-feedback.spec.ts` | 词表断言更新；新增「四原因 retry 均接受」「decline 无 reason 落盘」与 4 条非法组合 |

### 2.3 文档

| 文件 | 改了什么 |
|---|---|
| `daniel-bot/specs/PHASE1-INTERACTION-DESIGN.md` | 追加 §12「第四批实现记录」：结构、落点、写链、重做、词表、边界 |
| `daniel-bot/app/desktop-patches/CHANGES-SLICE4.md` | 本文（含两张质检表） |

---

## 3. 数据结构（真样例）

`WriteDraft`（纯函数输出，渲染层不再自己拼字符串）：

```json
{
  "step": { "module": "红人名单", "action": "把 12 个人加入名单「第十一批」" },
  "kind": "list",
  "action": "把 12 个人加入名单「第十一批」",
  "workspace": "jack",
  "brand": "Halliday",
  "list": "第十一批",
  "count": 12
}
```

| 字段 | 规则 |
|---|---|
| `kind` | `list`（要名单）／`profile`（建档、品牌档案，只要工作区＋品牌） |
| `list` | 优先引号里的名字；动词尾巴（`人加入`、`加入`）一律丢弃；解析不到 = 缺失，不猜 |
| `count` | 只认「N 个人 / N 人 / N 位」；「20 个红人」不算人数，宁缺不猜 |
| `workspace` / `brand` | 只来自顶部显式选择，不从动作句里猜 |
| `missingTargetOf` | 固定顺序：workspace → brand → list（`profile` 不要求 list） |

一条真实的 `feedback.jsonl` 重做记录（渲染层组出这一行，主进程落盘时再补 `appVersion`）：

```json
{"ts":"2026-11-09T09:43:25.021Z","sessionId":"evidence","turnId":3,"verdict":"down","reason":"wrong_data","action":"retry","workspaceId":90002,"brandId":"4800023","messageDigest":"10c84851de8c22d7"}
```

一条真实的「先不做」记录：

```json
{"ts":"2026-11-09T09:48:09.868Z","sessionId":"evidence","turnId":3,"verdict":"down","action":"decline","workspaceId":90002,"brandId":"4800023","messageDigest":"10c84851de8c22d7"}
```

---

## 4. 真实文案与 DOM（`DSH_SLICE4=1` 的输出）

### 4.1 确认条（落点完整）

```html
<section class="_writeBar_fe1acc" data-write-confirm="true" data-write-complete="true"
         aria-label="将写入 jack › Halliday › 第十一批（12 人）">
  <div class="_writeText_fe1acc">
    <span data-write-confirm-target>将写入 jack › Halliday › 第十一批（12 人）</span>
    <span data-write-confirm-action>把 12 个人加入名单「第十一批」</span>
  </div>
  <div class="_writeButtons_fe1acc">
    <button data-write-confirm-execute>确认执行</button>
    <button data-write-confirm-decline>先不做</button>
  </div>
</section>
bar height band:   min-height: 56px;   max-height: 72px;
```

### 4.2 落点不全（未选工作区 / 品牌）

```html
<section data-write-confirm data-write-complete="false"
         aria-label="将写入 未选择工作区 › 未选择品牌 › 第十一批（12 人）">
  …
  <span data-write-confirm-missing>先补全落点</span>
  <button data-write-confirm-execute disabled>确认执行</button>
  <button data-write-confirm-decline>先不做</button>
</section>
execute disabled: true
hint: 先补全落点
```

> 「先不做」保持可点：它不写任何东西，而且是这条卡唯一的退出方式；禁用它等于把用户困在一条无法完成的写入上。

### 4.3 点「确认执行」后发送的消息（原文）

```text
执行这个写入：把 12 个人加入名单「第十一批」（品牌 Halliday）
```

发送后确认条原地变为（按钮收起）：

```html
<span data-write-confirm-state="sent" role="status">已发给 Daniel，等写入计划</span>
```

### 4.4 「先不做」折叠态

```html
<section class="_writeBar_fe1acc" data-write-confirm="true" data-write-complete="true" data-write-collapsed="true">
  <span data-write-confirm-state="declined">已记下，这次先不写</span>
  <span class="_writeTargetFold_fe1acc">将写入 jack › Halliday › 第十一批（12 人）</span>
</section>
```

### 4.5 四个原因的「重做」

```text
- wrong_data:   重做上一步：重新取一次数，刚才那次数据不可靠
- off_topic:    重做上一步：重新理解我的问题，上次没答到点上
- too_verbose:  重做上一步：给短版，只保留结论和必要依据
- useless:      重做上一步：换个做法重做，上次结果没用
```

「已记录」行（真实 DOM）：

```html
<div data-feedback-done>
  <span role="status">已记录</span>
  <button data-feedback-retry="wrong_data">重做</button>
  <span>重新取一次数</span>
</div>
```

### 4.6 节流证据

```text
sent: 重做上一步：重新取一次数，刚才那次数据不可靠
retry record: {"reason":"wrong_data","action":"retry","workspaceId":90002,"brandId":"4800023",…}
message count after 29,999 ms: 1
hint: 刚重做过，稍等
message count after 30,000 ms: 2
old result still mounted: true
```

### 4.7 「不直接调工具」的探针输出

```text
services requested from the session scope: [ 'conversation' ]
send result: sent
sent: 执行这个写入：把 12 个人加入名单「第十一批」（品牌 Halliday）
decline/fold + retry copy contains tool words: false
conversation.send attaches the top-bar selection: true
message text itself repeats the workspace: false
```

后两行是「带顶部已选上下文」的证据：消息走的是 `conversation.send`，它在每次提交时读顶部选择器注册的 request-context（§9.8），因此工作区/品牌随请求一起到模型，而**不**被拼进用户可见的正文（正文里只有品牌，因为那句「（品牌 Halliday）」本身是给模型看的目标限定）。

---

## 5. 写链（为什么按钮不会自己写）

```text
确认条 / 重做按钮
  └─ sendUserMessage(sessionId, text)             ← 唯一发送路径
       └─ sessions.scope(id).get('conversation').send(text)
            └─ 一条普通用户消息（工作区/品牌随请求上下文注入，§9.8）
                 └─ 模型：daniel_write_plan（执行计划，原样给用户）
                      └─ 用户在对话里第二次确认
                           └─ 模型：daniel_write_commit
```

- 客户端**没有** tool / MCP / 写入命令句柄：新增两个模块里不存在 `daniel_*`、`.tool`、`callTool`（静态断言），运行时也只向会话要了 `conversation` 一个服务（动态断言）。
- 一次确认只对一次执行有效（AGENTS.md §3 第 7 条）；确认条只负责把「写什么」发出去，第二道确认在模型/工具链，本批不越过。
- 发送失败（无会话、被拒）都是值：UI 留在原地显示「没能发出去，再试一次」，不会静默当作已执行。

---

## 6. 测试、构建与真实输出

### 6.1 全量（客户端）

```
npx vitest run packages/client/ui-capability-map/tests
Test Files  14 passed | 3 skipped (17)
     Tests  309 passed | 9 skipped (318)
```

- 新增：`slice4.client.spec.tsx` 23 条；evidence 打印 3 条（默认 skip）。
- 回归：`result-notes` 30 条全绿（含 2 处计划内断言更新）、`evidence-panel` 33 条、`next-steps` 51 条、D-077 三条 trace 套件全部原样通过；`evidence.client` / `evidence-slice3` 的 skip 用例保持 skip。
- 桌面主进程：`npx vitest run apps/desktop/tests/daniel-feedback.spec.ts` → `11 passed (11)`。

### 6.2 门禁

| 门禁 | 命令 | 结果 |
|---|---|---|
| 客户端类型检查 | `npx tsc -b tsconfig.client.json` | 退出码 **0** |
| 桌面构建 | `pnpm -C apps/desktop run build` | 退出码 **0**（tsc -b ＋ tsdown ＋ vite welcome） |
| 客户端 bundle | `pnpm --filter @deepseek-ai/dsh-client-ui-capability-map run bundle` | 退出码 **0**，`lib/client.js` 307,451 B |

### 6.3 验收打印

```
DSH_SLICE4=1 npx vitest run packages/client/ui-capability-map/tests/slice4-evidence.client.spec.tsx
✓ slice 4 evidence (3 tests)
```

输出即 §4 的 4.1–4.7。

---

## 7. 方案质检表

| 条款（§） | 要求 | 实现位置 | 是否满足 | 偏离说明 |
|---|---|---|---|---|
| §2.1 第 3 块 | 写入确认条在结果区、折叠区**之前**，出现即展开、常驻 | `ResultNotes.tsx`（缺失提示之后、`data-result-notes` 之前）；`WriteConfirm.tsx` | 满足 | 无 |
| §2.1 第 3 块 | 一行卡 **56–72px** ＋ 2 个按钮 | `ResultNotes.module.css` `.writeBar { min-height:56px; max-height:72px }`；`data-write-confirm-execute/-decline` | 满足 | 高 56 是由两行文字（落点＋动作句）撑出来的；更长的名字单行省略，不撑破 72 |
| §2.1 第 3 块 | 「先不做」→ **折叠**该条（不是消失） | `WriteConfirm.tsx` `phase='declined'`；`.writeBar[data-write-collapsed]` 32px | 满足 | 折叠后仍保留一行落点（比纯隐藏多给一句「本来会写什么」） |
| §2.1 / §9.4 | 文案必须含落点：工作区 › 品牌 › 名单（N 人） | `write-confirm.ts` `missingTargetOf`；`WriteConfirm.tsx` `targetLineOf` | 满足 | `kind='profile'`（建档类）没有名单概念，落点为工作区 › 品牌 |
| §9.4 | 缺落点 → 按钮禁用 ＋「先补全落点」 | `isWriteComplete` / `data-write-confirm-missing` | 满足 | **确认执行**禁用；「先不做」保留可点（不写任何东西，且是唯一退出）。这是对「按钮禁用」的收窄解释，已在此写明 |
| §3.5 / 写链纪律 | 写入是选择题：确认后**不执行**，必须 plan → 用户再确认 → commit | `send-message.ts` 只发用户消息；`index.ts` 注入 `sendMessage`；无工具句柄 | 满足 | 第二道确认在模型/工具链，本批不越过、也不伪造 |
| §3.5 | 卡片 / 按钮**不直接调用** daniel 工具 | `send-message.ts` 只取 `conversation`；测试断言 `requested === ['conversation']`；源码断言无 `daniel_*` / `.tool` / `callTool` | 满足 | 无 |
| §3.5 | 确认消息带顶部已选上下文 | `conversation.send` 读 `requestContext`（§9.8 既有注入） | 满足 | 工作区/品牌走请求元数据，不写进用户可见正文 |
| §7.2 | 4 个原因各给**一个**「重做」按钮 | `retry.ts` `RETRY_INSTRUCTIONS`；`ResultNotes.tsx` `data-feedback-retry` | 满足 | 第三批的「主/次两个动作按钮」收敛为一个「重做」＋一行说明；旧 8 个 action id 仍在日志白名单里（历史兼容） |
| §7.2 | 点击发固定指令：`重做上一步：<原因对应指令>` | `retryMessageOf`；消息原文见 §4.5 | 满足 | 无 |
| §7.2 | 记录 `feedback(action=retry, reason=...)` | `FeedbackRow.onRetry` → `appendFeedback`；桌面校验接受 4 个 reason | 满足 | 发送失败也记录（点击发生的事实），与「已记录」语义一致 |
| §7.2 | 同一 turn **30 秒**内只重做一次；重复点提示「刚重做过，稍等」 | `retry.ts` `claimRetry` / `releaseRetry`；key=`sessionId:turnId` | 满足 | 30 秒窗口在发送**前**占用（防双击）；发送失败会释放，可立即重试（不是放宽节流） |
| §7.2 | 重做后原结果保留，新结果作为新 turn | 只发消息、不删任何记录/DOM；测试断言结果块仍是同一节点 | 满足 | 无 |
| 业务语言 | 确认条 / 重做按钮不出现工具名、接口、模块名 | `locales.ts` 文案；`slice4.client.spec.tsx` 禁用词断言 | 满足 | 允许出现产品名「Daniel」（既有文案同款） |

---

## 8. 工程质检表

| 检查项 | 结果 | 证据 |
|---|---|---|
| 回归：第三批 evidence / result-notes | **绿** | `evidence-panel` 33、`evidence` 相关 46、`result-notes` 30；全量 309 passed / 9 skipped |
| 回归：next-steps / trace（D-077） | **绿** | `next-steps` 51、trace 三条套件原样通过，未改解析器 |
| 新增覆盖 | **23 条** | 纯解析 6、DOM 9（含两种落点与 CSS）、重做 5、发送路径 3 |
| 边界：缺工作区 / 缺品牌 / 缺名单 | **通过** | 三态都渲染确认条、确认禁用、「先补全落点」；名单缺失显示「未写名单」不猜 |
| 边界：动词冒充名单名 | **通过** | `writeListOf('把 12 个人加入名单')` → `undefined`（「人加入」被丢弃） |
| 边界：建档类无名单 | **通过** | `kind='profile'`：落点 `jack › Halliday`，确认可用 |
| 节流 | **通过** | 29,999ms 只发 1 条；30,000ms 发第 2 条；另一个 Turn 不受影响；重复点显示「刚重做过，稍等」 |
| 安全：不直接调工具 | **通过** | 运行时只请求 `conversation`；源码无 `daniel_*` / `.tool` / `callTool`；确认条文本无技术词 |
| 安全：反馈词表扩展 | **通过** | `retry` 必须带 reason；`decline` 必须不带 reason；非法组合 4 条全部拒绝且不落盘 |
| 安全：写链不可绕过 | **通过** | 确认只产生一条用户消息；没有 commit 入口；第二道确认在模型侧 |
| 构建：客户端类型 | **0** | `npx tsc -b tsconfig.client.json` |
| 构建：桌面 | **0** | `pnpm -C apps/desktop run build` |
| 构建：客户端 bundle | **0** | 307,451 B，重打后运行时才读得到新逻辑 |
| 打包 DMG | **未做** | 按任务纪律，交付停在「构建通过」 |

---

## 9. 风险与边界

| # | 风险 | 影响 | 处置 |
|---|---|---|---|
| 1 | 名单名是文本启发式 | 少数自然说法解析不到名单 | 解析不到就禁用确认、显示「未写名单」；不猜、不写错名单 |
| 2 | 建档类落点用当前品牌 | 动作句里的另一个品牌名不会替换落点 | 条上只用当前选择；模型能从动作句本身读到目标；已在 §12.7 写明 |
| 3 | 一结果只一条确认条 | 两张写入卡时第二条没有确认条 | 第二条仍是建议卡（填输入框）；避免同时问两个「要不要写」 |
| 4 | 「先不做」在缺落点时仍可点 | 与「按钮禁用」字面不完全一致 | 它不写任何东西且是唯一退出；确认按钮已按要求禁用，已在质检表标注 |
| 5 | 重做不留旧反馈行状态 | 重做后原行仍显示「已记录 / 重做」 | 这是「原结果保留」的一部分；新 Turn 在主对话区出现，旧块不删 |
| 6 | 程序发送绕过发送前选择门禁 | 无选择时手输被拦，程序发送不拦 | 确认条本身要求工作区＋品牌齐全；重做与选择无关，不需要门禁 |
