# CHANGES-NEXT-STEPS-FIX — 任务结束后的「下一步卡片」不见了：定位与修复

> 时间：2026-11-03 · 源码树 `/tmp/dsh-build/dsh-src`（基线 `ce7073d5`，工作区改动未提交）
> 范围：前端解析 `packages/client/ui-capability-map`＋插件提示词 `daniel-bot/packages/0.11.0`（含 vendor 同步与重打 tgz）
> **按纪律未打包 DMG**（卡片与提示词的改动要等下一次打包才进新 `.app`）。

---

## 1. 定位结论（先证据，后结论）

### 1.1 槽位 `conversation.chat.turnTail` 确实被渲染 —— 是"每轮结束后渲染"，不是只对特定节点

证据链（三处代码，缺一不可）：

1. `packages/client/ui-chat/src/client/conversation-nodes/turn-tail.ts`
   - `match`：`turn/start` / `turn/end` / `tool/call` / `tool/result` / `assistant/*` / `step/*` / `llm/retry` 都挂到同一个 `turn-tail` 节点；
   - `publication: match => match.event.type === 'turn/end' ? 'immediate' : 'none'`
     → **每个回合只要走到 `turn/end`，就发布一个 `turn-tail` 节点**（成功、失败、中断都一样），不是"只有某种特殊回合才有"。
2. `packages/client/ui-chat/src/client/chat/TurnTailNodeView.tsx:49`
   ```ts
   const tail = renderSlot('conversation.chat.turnTail', owner)
   if (closing === null) return tail === null ? null : <div className={css.root} data-turn-tail={data.turn}>{tail}</div>
   ```
   正常回合（`closing !== null`）里，`{tail}` 与操作行（复制/分支/用量）同排渲染；`closing === null` 时也仍渲染 tail（只有当 tail 也为 null 才整体不渲染）。
3. 槽位声明侧：`packages/client/ui-chat/src/client/chat/register-node-renderers.ts:90` 给 `turn-tail` 节点声明了 children
   `'conversation.chat.turnTail': { kind: 'list', scope: 'session' }`，`contract/slots.ts:487` 的 owner 是 `TurnTailOwnerProps`。

卡片组件自己在槽位之上再加了两个前提（`NextSteps.tsx`）：
`turn.end !== undefined`（回合已结束）且 `turn.data.get('turn-tail')?.closing` 是一段**带文本的收尾回答**；
任一不满足即 `return null`（fail-closed，占 0 像素）。因此"看不到卡片"有三种可能：槽位没渲染、组件提前返回、解析出 0 条。
1.1＋1.2 排除了前两种，问题落在解析。

### 1.2 `index.ts` 的注入仍生效（name / id / order 都对）

`packages/client/ui-capability-map/src/client/index.ts`：

```ts
ctx.slots.inject('conversation.chat.turnTail', () => ctx.slots.register({
  name: 'conversation.chat.turnTail',
  id: 'capability-map.next-steps',
  order: 30,
  locale: NS,
  inject: (): NextStepsInjected => ({ prefill: phrase => prefillDraft(ctx.sessions, phrase) }),
}, NextStepCards))
```

复验（真实跑）：`next-steps.client.spec.tsx › next-step registration › adds exactly one turnTail entry whose prefill writes the composer`
→ `entries('conversation.chat.turnTail')` 长度 **1**、`options.id = capability-map.next-steps`、`options.order = 30`，
`prefill()` 只调用 `setDraft`（`submit` / `send` 调用次数 0）。**PASS**。

### 1.3 样例文本在哪一步被丢：两处 exit，都是"格式太严"

取**真实回答**（Daniel Bot 本机 profile，session `152d1c06`，2026-11-03 18:51，user 问"账号下有几个 workspace"）的收尾：

```
你现在处于工作区 **90002（jack）**。

- 登录账号：jack（超级管理员）
- 该工作区有 3 个品牌：Halliday、iPhone、Lymow

账号与盘点：查看 jack 下 iPhone、Lymow 两个品牌的名单数量
红人名单：从 Halliday 现有 17 个名单中挑一个，拉出红人做背调筛选
```

修复前跑 `parseNextSteps`：**`[]`**（0 条 → 卡片整块消失）。丢弃点是两处，先后命中：

| # | 丢弃点（代码位置） | 为什么这条回答会命中 |
|---|---|---|
| ① | `parseNextSteps`：`if (heading === -1) return []` | 回答里**没有标题行**（既没写"下一步"，也没写"接下来"），从最后一行往前扫全部不匹配 ⇒ 直接返回空，后面的条目根本没被看 |
| ② | 标题后的条目循环：`const item = listItemOf(line)` → `item === undefined` ⇒ `break` | 即使模型写了标题，这里也只认 `-`/`*`/`•`/数字标记；**裸行 `账号与盘点：…` 不算条目**，第一条就被当成"正文结束" |
| ③ | `stepOf()`：模块名不在九个之内 ⇒ `undefined`（该条被丢，不报错） | 另一类实测形态：本机历史回答里有 **7 条**把模块写成旧名 `品牌资产`（10:33–14:32，含 13:44 之后的两条），前端解析表只认新名 ⇒ **该条被丢，卡片少一半**（这 7 条都是"第一项是旧名"，实际只出 1 张卡，本可出 2 张） |

**定位结论一句话**：槽位与注入都是好的；**提示词没规定格式、解析器却要求固定格式**（标题行 ＋ 每项列表标记 ＋ 九个新名之一），模型只要换了说法，解析就返回 0 条，卡片不报错地消失。

顺带用真实语料量化"时有时无"：本机 6 个会话、24 条 assistant 回答里，
旧解析能出卡片 **11 条**、一条都出不了 **13 条**（这 13 条**全部**是"没有标题行"——其中一条就是 18:51 那段裸模块行）；
能出的 11 条里又有 **7 条**因为第一项写成旧名 `品牌资产`，只剩 1 张卡而不是 2 张。
修复后同语料：能出卡片 **12 条**（多出的正是 18:51 那条，现在出 2 张），旧名那 7 条仍按设计丢弃该条。

---

## 2. 两侧改动

### 2.1 前端解析放宽（`packages/client/ui-capability-map/src/client/next-steps.ts`）

| 规则 | 修复前 | 修复后 |
|---|---|---|
| 标题 | `下一步`／`下一步建议`／`Next steps`，允许 `#`、加粗、尾冒号 | 追加 `建议下一步`、`接下来`；**允许 emoji 前缀**（`🎯 下一步`、`👉 **下一步建议**`）；`#`/加粗/尾冒号照旧 |
| 条目 | 只认 `-`／`*`／`•`／`1.` 等列表标记 | 列表标记**可选**：裸行 `<模块名>：<动作>` 也算条目 |
| 无标题 | 直接返回 `[]` | **回退**：扫最后 `NEXT_STEP_TAIL_LINES = 8` 个非空行，收集以九个模块名开头且带冒号的行，最多 2 条 |
| 模块名 | 仅九个业务模块 | **不变**（旧名仍丢弃，`stepOf` 不改） |
| 条数 | 最多 2 条 | **不变** |
| 点击行为 | 只 prefill、不发送 | **不变**（`NextSteps.tsx` 未改） |
| 优先徽标 | 固定短语表 + 只标一张 + 移到首位 | **不变**（`prioritizeNextSteps` 未改） |

保留的防误判：代码围栏先剔除；有标题时**不**走尾部回退；标题后遇到既不是条目也不是 `<模块>：` 的行仍然"到此为止"（正文不会被读成下一步）。

### 2.2 插件提示词加固定格式（`daniel-bot/packages/0.11.0/lib/normalize.js` 的 `ANSWER_POLICY`）

在结尾追加一句硬要求（并在上方加注释说明为什么必须有格式）：

```
交付完成后，单独一行写「下一步：」，下面用「- 模块名：具体动作」列出 1–2 条（模块名必须是上面九个之一）。
```

同步产物：
- `apps/desktop/resources/vendor/daniel-dsh-plugin`（由 `apps/desktop/scripts/sync-daniel-plugin.mjs` 从新 tgz 解出，幂等）
- `daniel-bot/releases/daniel-dsh-plugin-0.11.0.tgz`（`packages/0.11.0/scripts/pack.mjs` 重打，213 文件）

新增插件单测 `daniel-bot/packages/0.11.0/tests/answer-policy.test.mjs`：断言策略里含「下一步：」+「- 模块名：具体动作」+「模块名必须是上面九个之一」，九个模块名按前端顺序连续列出，且**不残留**旧名（`账号与工作区／品牌资产／真实性与背调`）。

---

## 3. 测试证据

### 3.1 同一样例文本，修复前 vs 修复后

```
旧解析： []
新解析： ["账号与盘点｜查看 jack 下 iPhone、Lymow 两个品牌的名单数量",
         "红人名单｜从 Halliday 现有 17 个名单中挑一个，拉出红人做背调筛选"]
```

即：**同一条真实回答现在解析出 2 条卡片**，分别是「账号与盘点」「红人名单」，动作句子与回答原文逐字一致。

### 3.2 前端（`pnpm exec vitest run packages/client/ui-capability-map`）

```
 ✓ |thread-safe| packages/client/ui-capability-map/tests/next-steps.client.spec.tsx (46 tests) 78ms
 ✓ … trace.client.spec.tsx (17) / trace-filter (11) / trace-dedupe (18) / context-bar (33) /
     capability-map (21) / guide (18)

 Test Files  7 passed (7)
      Tests  164 passed (164)
```

`next-steps.client.spec.tsx` 由 38 → **46**（新增 8 条，全部在 `describe('next-step acceptance set')`）：

1. 标题六种写法＋Markdown 标题＋加粗都能读；
2. emoji 前缀标题（`🎯`／`👉`／`📌`／`✅`）；
3. 编号/符号标记全覆盖（`1.` `1、` `1)` `1）` `1．` `-` `*` `•` `–`）；
4. 标题下**无列表标记**的裸行；
5. **无标题回退**（用上面那条真实回答的形态，逐字断言两条卡片）；
6. 回退的两个上限：最多 2 条、只看最后 8 个非空行（第 9 行的模块行不算）；
7. 模块名不匹配丢弃（`品牌资产`／`账号与工作区`／`真实性`／`财务`）；
8. 正文里的"提到模块名"不算下一步（含标题下先出现正文行的情况）。

另把注册用例加强为同时断言 `id` 与 `order = 30`（name 即查询用的槽位键）。

类型检查：`tsc -b packages/client/ui-capability-map` → **EXIT 0**。

### 3.3 插件（`node --test daniel-bot/packages/0.11.0/tests/*.mjs`）

```
tests/answer-policy.test.mjs      tests 4  pass 4  fail 0
tests/research-channels.test.mjs  tests 8  pass 8  fail 0
```

（`research-channels` 为既有用例，未改动、无回归；golden 基线只记响应**形状**与 shape 哈希，提示词文本变化不影响它，故未改。）

---

## 4. root hash 变更与门禁

| 项 | 修复前 | 修复后 |
|---|---|---|
| 插件文件数 | 212 | **213**（+`tests/answer-policy.test.mjs`） |
| root hash | `7165f0215b44c509b0a42d0237296691d88e91d2e71f9e3c05e1b5050cf8fd56` | **`bed0612538e71658a68a5d268b99754910526cc660afe7cf442360355831f70a`** |
| tgz 体积 | 1,696,744 B | 1,722,437 B |

同步更新（口径 A：`path\0bytes\0sha256\n` 再 sha256，范围跳过 `specs/`、`node_modules/`、`.git/`）：

- `daniel-bot/app/tests/g1-contract-gate.mjs` → `KNOWN_GOOD = { version: '0.11.0', files: 213, rootHash: 'bed061…' }`（含头部注释的 213）
- `daniel-bot/app/scripts/upgrade-plugin.mjs` → `BASELINE = { version: '0.11.0', files: 213, rootHash: 'bed061…' }`（含头部注释）
- `daniel-bot/app/desktop-patches/CHECKPOINT.md` → 「213 文件」×2、「213 个文件 · bed0612538e7」
- `daniel-bot/specs/UPGRADE-PLUGIN.md` → §3 基线表、Step 0 预期、§5 引用的 CHECKPOINT 行、§6 示例、§9 口径表、§8 ③④⑤ 的文件数期望

> **刻意未改**：`CHANGES-SEARCH-CHANNELS.md`、`QA-REPORT.md`、`specs/DECISIONS-A.md`、`S2-方案设计.md` —— 它们是当时的真实验收记录（历史证据），改了就失去"当时跑过什么"的价值。

### 门禁真实输出（`node daniel-bot/app/tests/g1-contract-gate.mjs`）

```
PASS G1-1a 插件版本与文件数 ← 期望: daniel-dsh-plugin@0.11.0，213 个文件，0 软链 | 实际: 同
PASS G1-1b root_hash 等于版本钉死的 known-good ← 期望: bed0612538e71658…（0.11.0） | 实际: 一致
PASS G1-1d 与 tgz 真源逐文件一致 ← 解包 213 文件，hash 相同，仅目录有 0 / 仅 tgz 有 0
PASS G1-2a / G1-2b / G1-3a / G1-3b / G1-4a / G1-4b / G1-4c
SKIP G1-1c（补丁未引入 PLUGIN-MANIFEST.json）· SKIP G1-4d（本会话无打包产物）

RESULT: PASS  G1 契约门禁 — 通过 10 / 失败 0 / 跳过 2（退出码 0）
```

---

## 5. 影响链与没做的事

1. **要重打 DMG 才在用户机器上生效**：`.app` 里的插件是打包那一刻的快照；本机 `profile` 副本
   （`~/Library/Application Support/Daniel Bot/dsh-home/profiles/desktop/node_modules/daniel-dsh-plugin`，
   现为 212 文件 / `7165f021…`）要等新 `.app` 首启后由 `embedDanielPlugin` 按 hash 比对重写。
   本轮按纪律**未打包**。
2. **旧模块名（`品牌资产` 等）仍会被前端丢弃**（设计如此：宁可少一张卡，也不猜一张错卡）。
   本轮靠提示词的"模块名必须是上面九个之一"＋已有新旧名清单收敛；语料侧抽查未发现旧名残留
   （`vendor/data/daniel-cli/mcp/corpus` 里 0 处 `品牌资产`、7 个文件用新名），历史回答里的旧名来自模型自身的用词习惯。
3. **未改其它包、未新增依赖**；`NextSteps.tsx`、CSS、`prefill.ts`、`prioritizeNextSteps` 一行未动，
   卡片行为（点击只 prefill、优先徽标规则）与修复前完全一致。
4. `lib/` 为构建产物：类型检查已跑（`tsc -b`），`pnpm -C apps/desktop run build` 未运行（打包动作，按纪律停在打包前）。
