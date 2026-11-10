# 阶段 1 · 第三批（SLICE 3）：结果级「查看依据」+ trace 的 turn 归属

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，Daniel Bot）
> 设计依据：`daniel-bot/specs/PHASE1-INTERACTION-DESIGN.md` §2.5、§3.7、§3.11、§4.1、§5.1 第 10 条；实现记录见 §11
> 状态：**类型检查 / 桌面构建 / 客户端 bundle / 单测全绿（见 §7）；未打包 DMG（按纪律）**
> 一句话：结果底部多一个独立的「查看依据」入口；点开后一级只说「用了哪些数据、成没成、什么范围」，二级「技术明细」才给工具名/命令/参数/耗时/错误码；失败自动展开、数据缺失给顶部提示并能跳转高亮；写入只做只读预览。trace 同时补上每个调用属于哪个 turn，task 级视图一字未动。

---

## 1. 本批做了什么（4 块）

| # | 设计稿条目 | 改前 | 改后 |
|---|---|---|---|
| 1 | §2.5 依据面板 | 反馈行右端只有一个 `aria-disabled` 的占位「查看依据」 | 真入口：默认收起；展开为独立面板，正文 `max-height: 320px` 内部滚动；**一级业务 / 二级技术**严格分层 |
| 2 | §5.1-10 turn 归属 | `trace.ts` 只有 task 级（按第 N 个任务聚合） | 每个调用记 turn；新增 `TraceSnapshot.turns` 投影（同 turn 内按 `module + action` 归并）；无 turn 的老日志整条不出现，task 视图不变 |
| 3 | §3.7 规则 1/3/4 | 无 | 点击展开；失败自动展开并标失败来源与影响；数据缺失顶部一行提示，点「看依据」跳转并高亮对应项 |
| 4 | §3.7 规则 2（只读部分） | 无 | 有 `daniel_write_plan` 时在成品下展示「接下来会写进 Daniel：…」，**没有确认/执行按钮**；真确认留给第四批 |

**明确不做**：写入确认条的「确认执行 / 先不做」与真执行；点踩后的重跑；左栏按 turn 切换；结果正文的命中数解析（宁缺不猜）。

---

## 2. 改动文件

### 2.1 客户端插件（`packages/client/ui-capability-map`）

| 文件 | 改了什么 |
|---|---|
| `src/client/trace.ts` | 新增 `eventTurn()`；`StartedCall.turn`（`tool/call.data.turn`，缺字段回落最近 `turn/start`）；`turn/end` 只关指针；`turnProjection()` 生成 `TraceSnapshot.turns?`；`steps/current/modules` 字段与聚合**未改** |
| `src/client/evidence.ts` | **新增**：按 turn 折叠调用（`EvidenceTrace`）、一级来源分组、成功/部分/未取到、数据范围、耗时、错误码、写入意图、参数脱敏、报告按 turn 记忆化；记录上限 2,000 |
| `src/client/EvidencePanel.tsx` | **新增**：`EvidencePanel`（两级、技术明细折叠、× 关闭）、`DataMissingNotice`（规则 4）、`WritePreview`（规则 2 只读） |
| `src/client/EvidencePanel.module.css` | **新增**：面板/提示/写入卡；正文 320px 内部滚动；全部主题 token |
| `src/client/ResultNotes.tsx` | 反馈行占位改真入口；结果块新增缺失提示、写入预览、依据面板；失败自动展开（用户关过则不再弹）；跳转高亮状态 |
| `src/client/ResultNotes.module.css` | 「查看依据」改为可点按钮（hover / `aria-expanded` / focus ring） |
| `src/client/index.ts` | 构造并注入 `EvidenceTrace`；导出 evidence / panel 的公开 API |
| `src/client/locales.ts` | zh / en 各新增 24 个 `evidence.*` / `write.preview.*` key（键集一致） |
| `tests/trace-baseline.client.spec.tsx` | **新增 13 条**：改 trace 前先钉住既有行为（下面是 §7.1 的真实经过） |
| `tests/trace-turn.client.spec.tsx` | **新增 7 条**：turn 归属、同 turn 归并、跨 turn task 视图不变、老日志兼容 |
| `tests/evidence-panel.client.spec.tsx` | **新增 33 条**：两级、禁词、失败自动展开、缺失跳转高亮、纯生成、写入预览、200 条、脱敏、与 rail 同 turn 规则 |
| `tests/evidence-slice3.client.spec.tsx` | **新增 5 条**（默认 skip，`DSH_EVIDENCE=1` 打印真实结构/DOM/耗时） |
| `tests/trace.client.spec.tsx` | 1 处精确快照断言补上 `turns`（step 形状未动） |
| `tests/result-notes.client.spec.tsx` | 1 处占位断言改为真入口（`aria-expanded="false"`） |
| `lib/client.js` | 重新 bundle（`pnpm --filter @deepseek-ai/dsh-client-ui-capability-map run bundle`，285,795 B），否则运行时仍读旧包 |

### 2.2 文档

| 文件 | 改了什么 |
|---|---|
| `daniel-bot/specs/PHASE1-INTERACTION-DESIGN.md` | 追加 §11「第三批实现记录」：结构、turn 数据模型、两级口径、四条规则、性能、已知边界 |
| `daniel-bot/app/desktop-patches/CHANGES-SLICE3.md` | 本文 |

---

## 3. 数据结构（真样例）

### 3.1 一条带 turn 的事件（session log 原文）

```json
{"type":"event","event":{"type":"tool/call","seq":1,"time":1000,
 "data":{"turn":7,"step":1,"callId":"c1","name":"daniel_run",
 "arguments":"{\"argv\":[\"brands\",\"show\",\"--brand\",\"4800023\"]}"}}}
```

### 3.2 `TraceSnapshot.turns`（同 turn 内归并，task 级不变）

```json
"turns": [
  { "turn": 7, "steps": [
      { "id": "c1", "module": "品牌档案", "action": "查看品牌档案", "status": "done", "count": 2 },
      { "id": "c3", "module": "品牌提及", "action": "查看提及任务", "status": "done" }
  ]},
  { "turn": 9, "steps": [
      { "id": "c4", "module": "声量份额", "action": "查看声量总览", "status": "done" }
  ]}
]
```

同一批调用的 task 级视图（`steps`）仍是 `c1 ×2 → c3 → c4`，且每个 step 上**没有** `turn` 字段 —— 左栏渲染不需要改一行。

### 3.3 `EvidenceReport`（一个 turn 一份）

```json
{
  "turn": 7,
  "sources": [
    { "id": "brands",  "label": "品牌档案", "outcome": "ok",      "calls": 2, "range": "近 28 天" },
    { "id": "mentions","label": "社区提及", "outcome": "missing", "calls": 1, "range": "近 28 天" }
  ],
  "failed": true,
  "missing": [{ "id": "mentions", "label": "社区提及", "outcome": "missing", "calls": 1 }],
  "fetchedAt": "2026-11-09 17:42",
  "hasCalls": true
}
```

（`calls` / `writes` 省略；技术层只在点「技术明细」时渲染。）

---

## 4. 两级真实文案（`DSH_EVIDENCE=1` 的 DOM 输出）

### 4.1 一级（默认可见）

```
这次用到的数据
- 品牌档案 / 成功 / 数据范围 近 28 天
- 红人库 / 成功 / 数据范围 近 28 天
- 社区提及 / 未取到 / 数据范围 近 28 天
  社区提及没取到，这部分结论只能按已有信息给
取的时间 2026-11-09 17:42
没取到的：社区提及（未取到）
技术明细
```

### 4.2 二级（点「技术明细」后）

```
daniel_brand_view / brands show --brand 4800023 / 参数 {"brand":"4800023"} / 180 ms
daniel_roster_search / search submit --query AI glasses / 参数 {"query":"AI glasses","country":"US"} / 180 ms
daniel_run / mentions jobs / 参数 {"argv":["mentions","jobs"]} / 400 ms / 错误码 UPSTREAM_TIMEOUT
```

### 4.3 无取数

```
这次没有取数，直接用已有信息生成
```

### 4.4 写入只读预览

```
接下来会写进 Daniel
把 2 个人加入 US-Glasses-Q4 名单（品牌 Halliday · 名单 US-Glasses-Q4）
这一批只把要写的内容列出来，不会执行；确认与执行在下一步开放。
查看依据
```

（按钮只有一个「查看依据」；`button[data-write-confirm]` 数量 = 0。）

---

## 5. 四条主动露出 → 落点

| # | 触发 | 代码 | 测试 |
|---|---|---|---|
| 1 | 点「查看依据」 | `ResultNotes.tsx` `toggleEvidence` → `EvidencePanel open` | `is collapsed by default and opens on the feedback row entry` |
| 2 | 写入确认前 | `WritePreview`（`EvidencePanel.tsx`） | `shows what would be called and written, with no execute button` |
| 3 | 执行失败 | `ResultNotes.tsx` 初始/`useEffect` 依 `report.failed` 自动 open；失败来源 `data-evidence-status="missing"` + 影响句 | `opens itself on a failed fetch and marks the failed source and its impact`；`treats a call the Turn left in flight as failed` |
| 4 | 数据缺失 | `DataMissingNotice` → `jumpToEvidence()` 设 open + highlight | `shows the top notice, opens the panel and highlights the source that fell short` |

**不主动露出**：`shows no notice, no write card and no panel for a clean read`（成功路径 0 系统层）。

---

## 6. 词表纪律（一级禁词）

自动化断言（`evidence-panel`「keeps every technical word out of the business level」）：

```ts
const business = businessText(view)          // [data-evidence-level="business"]
expect(business).not.toMatch(/daniel_|route|MCP/u)
expect(business).not.toMatch(/模块|接口|工具/u)
```

一级实际文案只含：数据标签、成功/部分/未取到、数据范围、取的时间、缺失影响句、无取数句、写入预览句。
技术词 100% 落在 `[data-evidence-tech]` 内。

> 一处刻意保留：一级的「品牌档案」与模块同名。依据是 §2.5 的文案样例本身写的就是「品牌档案」，而 §4.3 禁的是「品牌档案**模块**」这种系统说法。其余模块名（红人检索 / 真实性核验 / 品牌提及 / 红人名单 / 账号与盘点 / 声量份额 / 合作追踪 / 内容情报）全部换成业务数据说法。

---

## 7. 测试、构建与真实输出

### 7.1 改 trace 之前先补回归（D-077 覆盖缺口）

先新建 `trace-baseline.client.spec.tsx`，只测**现有**行为，不动 trace.ts：

```
npx vitest run packages/client/ui-capability-map/tests/trace-baseline.client.spec.tsx
✓ ... (8 tests)
Tests  8 passed (8)
```

覆盖的正是 D-077 三个修复没管到的路径：`commandToken` 的非字符串/空 token、`describeBatch` 的空 calls 与跨模块、`prepend` 窗口、非 event 条目、重复序号、重复 callId、无关事件类型。改完 trace 后同一文件扩到 13 条（多补 5 条边界），仍全绿。

### 7.2 全量

```
npx vitest run packages/client/ui-capability-map/tests
Test Files  13 passed | 2 skipped (15)
     Tests  286 passed | 6 skipped (292)
```

- 新增：baseline 13 + turn 7 + panel 33 = 53 条；另有 5 条 `DSH_EVIDENCE` 打印用例默认 skip。
- 既有 233 条基线：除 2 处**计划内**断言更新（占位 → 真入口、精确快照补 `turns`）外全部原样通过；`next-steps` 51、`result-notes` 30、D-077 三条 trace 套件 46 全绿。
- 覆盖：trace.ts 行 100% / 分支 97.7%；evidence.ts 行 96.5% / 分支 82.9%；EvidencePanel.tsx 行 100%。未覆盖的是防御分支与 2,000 条裁剪路径。

### 7.3 门禁

| 门禁 | 命令 | 结果 |
|---|---|---|
| 客户端类型检查 | `npx tsc -b tsconfig.client.json` | 退出码 **0** |
| 桌面构建 | `pnpm -C apps/desktop run build` | 退出码 **0**（tsc -b + tsdown + vite welcome） |
| 客户端 bundle | `pnpm --filter @deepseek-ai/dsh-client-ui-capability-map run bundle` | 退出码 **0**，`lib/client.js` 285,795 B |

### 7.4 验收打印（`DSH_EVIDENCE=1`）

```
=== 1) 事件带 turn → 每 Turn 归并 ===
snapshot.turns: [ { "turn": 7, "steps": [ … count: 2 … ] }, { "turn": 9, "steps": [ … ] } ]
task-level steps: [ c1 ×2, c3, c4 ]（每步无 turn 字段）

=== 2) 依据面板 ===
auto-open on failure (panel present at mount): true
top notice: !这次有 1 项数据没取全，结论可能不完整看依据
LEVEL 1 rows: ["品牌档案 / 成功 / 数据范围 近 28 天", "红人库 / 成功 / 数据范围 近 28 天",
               "社区提及 / 未取到 / 数据范围 近 28 天 / 社区提及没取到，这部分结论只能按已有信息给"]
LEVEL 2 rows: ["daniel_brand_view / brands show --brand 4800023 / 参数 {…} / 180 ms", …]

=== 3) 默认收起（成功路径不露出）===
panel present: false    notice present: false    write card present: false

=== 4) 纯生成（无取数）===
empty copy: 这次没有取数，直接用已有信息生成

=== 5) 写入前只读预览 ===
write card: 接下来会写进 Daniel把 2 个人加入 US-Glasses-Q4 名单（…）…查看依据
execute buttons: 0

=== 6) 业务层禁词检查 ===
contains daniel_ / route / MCP: false
```

---

## 8. 风险与边界

| # | 风险 | 影响 | 处置 |
|---|---|---|---|
| 1 | `TraceSnapshot` 新增可选 `turns` | 任何对快照做**精确相等**断言的消费方会失败（本仓仅我们自己的 1 条测试） | 字段可选、无 turn 时不存在；渲染路径零改动；已在测试里固定 step 形状 |
| 2 | 依据折叠常驻订阅 | 长会话首次挂载要回放整个事件窗口 | 2,000 条上限、按 turn 签名记忆化、报告对象稳定；200 条展开实测 21 ms（§9 工程表） |
| 3 | 数据标签是手写表 | 新增模块会落到「其他数据」 | 模块表是构建期固定的 9 个；新增时需同步 `DATA_LABELS`（测试会显示标签） |
| 4 | 写入预览依赖 argv 形状 | 只认 `lists add-items` 等少数命令，其余退回业务动作句 | 宁少不编；`daniel_write_commit` 明确不算「即将写入」 |
| 5 | `turn/end` 把在飞调用记失败 | 网络抖动/取消会让面板自动展开（可能比过去吵） | 这正是 §3.7-3 要的「异常必须被看见」；用户关掉后本 turn 不再弹 |
| 6 | 脱敏是正则不是解析器 | 能盖住键名含 token/secret/session 等与 Bearer，但盖不住「位置参数里的一串随机密钥」 | 只展示 Daniel 调用参数、截断 240 字符；不落盘、不进日志 |
| 7 | 一级保留「品牌档案」 | 与模块名同字 | §2.5 样例即此词；已在本文件与 spec §11.5 显式记录 |

---

## 9. 方案质检表（逐条对照）

| 方案条款 | 要求 | 实现位置 | 是否满足 | 偏离说明 |
|---|---|---|---|---|
| §2.5 两级、严禁混层 | 一级说数据/结果/范围；二级才给模块/工具/命令/参数/耗时/错误码 | `EvidencePanel.tsx` `SourceRow`（一级）/ `CallRow`（二级）；`evidence.ts` `DATA_LABELS` / `EvidenceCall` | **满足** | 一级用「数据标签」而非模块名；「品牌档案」为 §2.5 样例原词 |
| §2.5 默认收起、展开 max-height 320、内部滚动 | 收起 0 高；展开正文 320 内滚 | `EvidencePanel.module.css` `.scroll`：`max-height: 320px; overflow-y: auto; overscroll-behavior: contain` | **满足** | 无 |
| §3.7-1 点「查看依据」→ 展开（任何时候） | 结果底部入口，独立于折叠区 | 反馈行右端 `[data-evidence-toggle]` → `EvidencePanel` | **满足** | 入口位置按 §2.3 与反馈同行；面板在反馈行**下方**独立块 |
| §3.7-2 写入/执行确认前展示「调用什么、写入什么」 | 第四批联动，本批只读 | `WritePreview`：标题 + 业务动作句 + 目标（品牌/名单/工作区）+ 「不会执行」+ 查看依据 | **满足（只读版）** | 本批**没有**确认/执行按钮（第四批），刻意避免误认 |
| §3.7-3 执行失败自动展开、标失败节点与影响 | 不点也展开；失败项可见 | `ResultNotes.tsx` `useState(report?.failed)` + `useEffect`；`data-evidence-status="missing"` + 影响句；二级错误码 | **满足** | 用户手动关闭后本 turn 不再自动弹（避免打扰），失败仍留在结果里 |
| §3.7-4 数据缺失顶部提示、点击跳转并高亮 | 不是错误横幅；可跳到依据 | `DataMissingNotice` + `jumpToEvidence()` 设 `highlight=missing[0].id` | **满足** | 文案用「没取全」覆盖 partial + missing 两种 |
| §3.11 结果区层级：依据独立入口，不并入折叠区 | 两个解释入口（折叠行 + 查看依据），依据单独块 | 结果块顺序：提示 → 写入卡 → 折叠区 → 反馈行 → 依据面板 | **满足** | 收起态元信息仍为 64px（入口在反馈行内） |
| 业务语言不出现模块名/接口名/MCP | 一级禁词 | 断言 `not.toMatch(/daniel_\|route\|MCP/)`、`not.toMatch(/模块\|接口\|工具/)` | **满足** | 「品牌档案」例外见上；技术词只在 `[data-evidence-tech]` |
| §4.1 除四条外不主动露出 | 成功路径 0 系统层 | 成功路径断言：无提示、无写入卡、面板不存在 | **满足** | 「查看依据」入口常驻是 §2.3 要求，不算主动露出 |
| §2.6 高度预算 | 收起态元信息 ≤ 72px | 折叠 32 + 反馈 32 = 64；面板收起 0；提示/写入卡仅条件出现 | **满足** | 条件块会让该轮临时更高，属于设计内的异常/写入态 |

---

## 10. 工程质检表

| 检查项 | 结果 | 证据 |
|---|---|---|
| 回归：改 trace 前补既有行为测试 | **先补 8 条并全绿，再改 trace；改完扩到 13 条仍全绿** | `trace-baseline.client.spec.tsx`：`Tests 8 passed (8)` → `13 passed (13)`；覆盖 `commandToken` 非字符串/空 token、batch 空 calls/跨模块、`prepend`、非 event、重复 seq、重复 callId、无关事件 |
| 回归：现有套件不回归 | **286 passed / 6 skipped（292）**；对比改前 233 passed / 1 skipped | `npx vitest run packages/client/ui-capability-map/tests`；既有 `next-steps` 51、`result-notes` 30、D-077 三套 46 全绿；仅 2 处计划内断言更新 |
| 边界：老会话无 turn 字段 | **不白屏，task 视图照旧，`turns` 整条不出现** | `trace-turn`「still renders the task view and simply omits the Turn projection」；`turns` 断言 `toBeUndefined()`，`steps` 精确相等 |
| 边界：老日志缺 turn 但有 `turn/start` | **能归属** | `trace-turn`「derives the Turn from turn/start when the call itself carries none」；`evidence`「falls back to turn/start…」 |
| 边界：纯生成无工具调用 | **显示「这次没有取数，直接用已有信息生成」** | `evidence-panel`「says so when the Turn fetched nothing」；打印输出 `=== 4)` |
| 边界：工具失败 | **标 failed、给错误码、自动展开、来源=未取到** | `evidence-panel`「opens itself on a failed fetch…」；`marks a failed result and keeps the error code」 |
| 边界：工具超时/中断 | **`turn/end` 时仍在飞的调用记 `INTERRUPTED`，触发自动展开** | `evidence-panel`「treats a call the Turn left in flight as failed」：status=failed、errorCode=INTERRUPTED、durationMs=29000 |
| 边界：部分成功 | **来源=部分** | `evidence-panel`「calls a mixed source partial…」 |
| 兼容：task 级视图未被破坏 | **跨 turn 同动作在 task 级仍 `×2`；`steps` 无 turn 字段** | `trace-turn`「keeps the task view merged across Turns while the Turn view stays split」；D-077 46 条全过 |
| 性能：面板展开不阻塞长会话 | **200 条调用：挂载+展开+技术明细 21.0 ms（jsdom，无布局）；正文 320px 内滚** | 打印 `=== 7) 200 条调用展开耗时 ===`；`panel: 320px scroll box` 断言 `max-height/overflow`；记录上限 2,000、报告按 turn 记忆化 |
| 安全：技术明细不泄露密钥/令牌 | **参数进快照前脱敏；DOM 断言无明文** | `evidence-panel`「scrubs credentials…」+「never leaks a credential even when the technical list is open」：`app_session_id` / `token` / `Bearer` 值均不出现 |
| 构建：类型检查 | **退出码 0** | `npx tsc -b tsconfig.client.json` |
| 构建：桌面 | **退出码 0** | `pnpm -C apps/desktop run build` |
| 构建：客户端 bundle | **退出码 0** | `pnpm --filter @deepseek-ai/dsh-client-ui-capability-map run bundle`；`lib/client.js` 285,795 B |
