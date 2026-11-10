# 阶段 1 · 第二批（SLICE 2）交互改动：结果区「说明与下一步」+ 反馈行

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，Daniel Bot）
> 设计依据：`daniel-bot/specs/PHASE1-INTERACTION-DESIGN.md` §2（结果区结构）、§7 已裁决第 1 条、§10（本批实现记录）
> 状态：**类型检查 / 构建 / 单测 / G1 已跑（见 §6）；未打包 DMG（按纪律）**
> 一句话：结果末尾的「下一步卡片」并入折叠区第三段，前面补「业务思路 / 自我检讨」两段；下面加一条常驻反馈行（👍 / 👎 + 四原因 + 按原因给两个只记录不重跑的按钮），点踩记录落到本地 `feedback.jsonl`。

---

## 1. 本批做了什么（只这 3 块）

| # | 设计稿条目 | 改前 | 改后 |
|---|---|---|---|
| 1 | §2.2 折叠区 | 只有常驻的「下一步」卡组（约 100px，带模块名） | **单行 32px**「▸ 这个结果怎么来的，还能接着做什么 … 展开」；展开后三段固定顺序：**这个结果是怎么来的** / **哪里还做得不够** / **接下来可以做什么**（原下一步卡片）。段内最多 5 条，超出显示「还有 N 条」。某段无内容不渲染；三段全无 → 整块不渲染 |
| 2 | §2.3 反馈行 | 无 | **常驻 32px**：`这个结果有用吗？ 👍 👎`（16px SVG，未选 outline / 选中 fill + 主色），右端 **查看依据**（占位，不实现面板）。点 👎 就地展开 4 个原因 chips；未选原因提交 disabled；提交后「已记录」+ 主/次操作；👍 轻量「已记录」1.5s |
| 3 | §7 已裁决第 1 条 | — | **每个会话第 1 个带折叠区的结果自动展开一次**，标题右侧提示「以后默认收起」，点击或 3s 消失；会话级标记持久化，刷新后不再自动展开 |

**两个边界（明确不做）**：

- 写入确认条（§2.1 第 3 块）本批不动；写入类下一步卡片仍按原样出现在第三段。
- 点踩后的「重跑 / 改描述 / 换范围」只写一条 `action` 记录，**不触发任何任务**（第三批做）。「查看依据」面板同样留到后续批次。

---

## 2. 改动文件

### 2.1 客户端插件（`packages/client/ui-capability-map`）

| 文件 | 改了什么 |
|---|---|
| `src/client/result-notes.ts` | **新增**：解析「业务思路 / 自我检讨」两段（标题 + 前缀行两种写法、列表结构、最多 50 条、正文行结束段落、围栏代码剔除）；`foldSection` 负责「显示 5 条 + 还有 N 条」 |
| `src/client/feedback.ts` | **新增**：四个原因、原因→主/次操作表、`FeedbackRecord`、FNV-1a 64 位摘要、桌面桥探测、`submitFeedback`（桥失败静默转 localStorage 备份） |
| `src/client/explain-seen.ts` | **新增**：会话级首次展开标记（`localStorage['dsh.daniel.explain-seen.v1']`，最多 200 个；无 storage 时内存兜底） |
| `src/client/ResultNotes.tsx` | **新增**：折叠区 + 反馈行；三段渲染；自动展开判定与 3s 提示；原因行 / 已记录行 / 操作按钮 |
| `src/client/ResultNotes.module.css` | **新增**：收起行 32px、反馈行 32px、< 480px 短标题、原因 chips、主/次按钮；全部主题 token，`prefers-reduced-motion` 关动效 |
| `src/client/NextSteps.tsx` | 抽出 `NextStepCardList`（卡片本体）供第三段复用；`NextStepCards` 行为不变，导出新组件与类型 |
| `src/client/next-steps.ts` | 仅把 `withoutFences` 导出给新解析器复用；解析规则**零改动** |
| `src/client/locales.ts` | zh + en 各新增 33 个 key（explain.* / feedback.*），键集保持一致 |
| `src/client/index.ts` | `turnTail` 入口改渲染 `ResultNotes`（entry id / order 不变），`inject` 增加 `sessionId` 与 `appendFeedback`；导出新模块 |
| `tests/result-notes.client.spec.tsx` | **新增** 30 条：解析 5、折叠区 6、自动展开 5、反馈行 9（含选择带入记录）、记录 2、注册 1、样式 2 |
| `tests/evidence.client.spec.tsx` | **新增** 1 条证据用例，默认 skip；`DSH_EVIDENCE=1` 时打印折叠/展开/缺段/自动展开的真实 DOM |

### 2.2 桌面壳（`apps/desktop`）

| 文件 | 改了什么 |
|---|---|
| `src/daniel-feedback-api.ts` | **新增**：`daniel:feedback:append` 通道、请求/结果类型、四原因与八动作白名单、**原因→主/次操作**映射（校验用） |
| `src/daniel-feedback.ts` | **新增**：逐字段校验（未知字段丢弃、非法整条拒绝）、`appVersion` 与缺省 `ts` 由主进程补、串行 append 到 `<userData>/feedback.jsonl`、失败返回值不抛错 |
| `src/daniel-feedback-ipc.ts` | **新增**：`ipcMain.handle`，先 `assertSender`，异常折成 `{ok:false,reason:{kind:'io'}}`，disposer 移除 handler |
| `src/preload-app.ts` | `window.__dshDesktop.danielFeedbackAppend`（只转发固定形状记录） |
| `src/main.ts` | 启动时装 feedback 桥：`userData = app.getPath('userData')`、`appVersion = app.getVersion()` |
| `tests/daniel-feedback.spec.ts` | **新增** 9 条：契约、整行字段顺序、并发两行、16 种非法输入、io 失败、IPC 守卫与 disposer、异常折值 |

### 2.3 插件提示词（`daniel-bot/packages/0.11.0`）

| 文件 | 改了什么 |
|---|---|
| `lib/normalize.js` | `ANSWER_POLICY` 在「下一步：」之外新增**可选**两段（业务思路 1–4 条 / 自我检讨 1–3 条，禁止编造、禁止系统内部词） |
| `daniel-bot/releases/daniel-dsh-plugin-0.11.0.tgz` | 重打（仍 0.11.0，218 文件，1,736,710 B） |
| `tests/answer-policy.test.mjs` | ④ 改为「硬要求仍在」+ **新增 ⑤**：业务思路/自我检讨标题、可选、没内容不写、禁止编造、1–4 / 1–3 条、系统词禁令 |
| `daniel-bot/app/tests/g1-contract-gate.mjs` | `KNOWN_GOOD.rootHash` → `cee1315f957f054f886ab4a07d4bf0d31694b7384187ee670807ba6de240a50f` |
| `apps/desktop/resources/vendor/daniel-dsh-plugin/` | 由新 tgz 同步（218 文件，0 软链） |

### 2.4 文档

| 文件 | 改了什么 |
|---|---|
| `daniel-bot/specs/PHASE1-INTERACTION-DESIGN.md` | 追加 §10「第二批实现记录」：结构、解析规则、自动展开、落盘格式、与旧卡片关系、提示词 |
| `daniel-bot/app/desktop-patches/CHANGES-SLICE2.md` | 本文 |

---

## 3. 解析规则（`result-notes.ts`）

- 认的标题：`##/### 业务思路`、`这个结果怎么来的`；`##/### 自我检讨`、`哪里还做得不够`、`自检`。允许加粗、emoji、冒号；也允许无标题的 `业务思路：` / `自我检讨：` 前缀行（冒号后的文字算第 1 条）。
- 段内只认列表行（`-` `*` `•` `–` `—`，或 `1.` / `1、` / `1)`）；正文行结束当前段，**不猜**。
- 先剔除围栏代码块；任一 `##` 标题结束当前段（`## 下一步` 的列表不会被读成业务思路）。
- 每段解析上限 50 条，UI 显示 5 条 + 「还有 N 条」。
- 第三段完全沿用 `next-steps.ts`（九个模块名、最多 2 张卡、fail-closed），未改一行规则。

---

## 4. 落盘格式（真实两行）

`daniel:feedback:append` → `<userData>/feedback.jsonl`，生产路径
`~/Library/Application Support/Daniel Bot/feedback.jsonl`。

```json
{"ts":"2026-11-09T06:52:18.548Z","sessionId":"session-evidence","turnId":3,"verdict":"down","reason":"wrong_data","workspaceId":90002,"brandId":"4800023","messageDigest":"9f2c7a1b4d8e3f60","appVersion":"0.1.0"}
{"ts":"2026-11-09T06:52:18.551Z","sessionId":"session-evidence","turnId":3,"verdict":"down","reason":"wrong_data","action":"refetch","workspaceId":90002,"brandId":"4800023","messageDigest":"9f2c7a1b4d8e3f60","appVersion":"0.1.0"}
```

- 第一行＝点踩并选「数据不对」后提交；第二行＝再点主操作「重新取一次数」（`action` 字段）。
- 字段与校验规则见 `specs/PHASE1-INTERACTION-DESIGN.md` §10.4。
- 只追加，不改不删、不回读；写失败静默转 `localStorage['dsh.daniel.feedback.pending.v1']`。

---

## 5. 自动展开的判定（会话级）

- 标记：`localStorage['dsh.daniel.explain-seen.v1']` = `["session-evidence"]`。
- 第 1 个结果：`aria-expanded="true"` + 提示「以后默认收起」+ 写标记；
- 同会话第 2 个结果：`aria-expanded="false"`、无提示；
- 刷新（重新挂载）：仍收起；
- 第一个结果没有折叠区（三段全空）→ 不写标记，例外留给下一个有内容的结果。

---

## 6. 测试、构建与 G1（真实输出）

| 门禁 | 命令 | 结果 |
|---|---|---|
| 相关单测 | `vitest run packages/client/ui-capability-map/tests apps/desktop/tests/daniel-feedback.spec.ts` | **10 passed / 1 skipped（11 文件），227 passed / 1 skipped（228 用例）**；其中 next-steps 回归 **51/51**、result-notes **30/30**、desktop feedback **9/9** |
| 客户端类型检查 | `tsc -b tsconfig.client.json` | 退出码 **0** |
| 桌面构建 | `pnpm -C apps/desktop run build` | 退出码 **0**（tsc -b + tsdown，main/preload 均产出） |
| 提示词单测 | `node --test daniel-bot/packages/0.11.0/tests/answer-policy.test.mjs` | **5 passed / 0 failed**（④ 硬要求 + ⑤ 可选说明段） |
| G1 契约门禁 | `node daniel-bot/app/tests/g1-contract-gate.mjs --src /tmp/dsh-build/dsh-src` | **PASS 10 / FAIL 0 / SKIP 2**，退出码 0；插件 hash `cee1315f957f054f…`，218 文件 |

> 证据用例：`DSH_EVIDENCE=1 vitest run packages/client/ui-capability-map/tests/evidence.client.spec.tsx`（默认 skip，不影响「全绿」）。

### 风险 / 需要注意

| 风险 | 影响 | 处置 |
|---|---|---|
| 提示词让模型写「自我检讨：这次没有明显问题」 | 该段几乎总会出现一行占位结论 | 这是任务给定的模板；若后续嫌啰嗦，改成「没有明显问题就不输出自我检讨」即可（解析器无需改） |
| 解析器把 `## 业务思路` 之后、`##` 之前的列表当作条目 | 若模型在同一段里混入非业务列表，会被展示 | 已用「正文行结束段落」兜底；列表本身来源单一（提示词固定格式） |
| 反馈 JSONL 无轮转/上限 | 长期使用文件会变大 | 每行 < 1KB，正常使用可忽略；后续批次可加按大小轮转（本批遵守「只追加」） |
| 主进程强制「原因↔操作」配对 | 未来 UI 新增操作需同步改 `daniel-feedback-api.ts` | 映射表在客户端与主进程各一份，注释互指；新增动作时两处同改 |
| 自动展开标记按会话 id 存 localStorage | 清除站点数据后，每个会话会再自动展开一次 | 可接受降级（等价于首次使用）；不会重复打扰同会话 |
| 槽位 entry id 仍叫 `capability-map.next-steps` | 名字与内容不完全对应 | 故意保留：改 id 会在升级进程里留下两个块；注释已写明 |
| 渲染层拿不到打包版本 | `appVersion` 只能主进程写 | 已由主进程 `app.getVersion()` 注入，JSONL 每行都有 |

---

## 7. 复验（照抄）

```bash
cd /tmp/dsh-build/dsh-src
node_modules/.bin/vitest run packages/client/ui-capability-map/tests apps/desktop/tests/daniel-feedback.spec.ts
node_modules/.bin/tsc -b tsconfig.client.json
pnpm -C apps/desktop run build
DSH_EVIDENCE=1 node_modules/.bin/vitest run packages/client/ui-capability-map/tests/evidence.client.spec.tsx

cd "/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot"
node app/tests/g1-contract-gate.mjs --src /tmp/dsh-build/dsh-src
```

---

## 8. 补丁（2026-11-09）：正文不再重复「业务思路 / 自我检讨」

**问题**：这两段既在消息正文里原样显示，又被折叠区解析展示，同一段话看两遍。

**做法**：只在**渲染时**从正文摘掉这两段，折叠区照旧解析原文。消息数据不动 —— 复制、导出、反馈摘要拿到的仍是完整原文。

### 8.1 渲染前后对照（真实输出）

渲染前（存进 Session 的原文，一字未改）：

```text
三家竞品的建档已经补齐，摘要如下。

## 业务思路
- 用「智能眼镜测评」「智能眼镜 review」两组词检索，再按美国、10 万粉以上筛。
- 按最近 28 天的更新频率排优先级。

## 自我检讨
- 这次 Reddit 评论没取到，所以只有 YouTube 的声量。

下一步
- 品牌档案：把 Even Realities 也建档，补齐同品类竞品基线。
```

渲染后（正文可见文本；两段只在折叠区里出现）：

```text
三家竞品的建档已经补齐，摘要如下。

下一步
- 品牌档案：把 Even Realities 也建档，补齐同品类竞品基线。
```

### 8.2 改动文件

| 文件 | 改了什么 |
|---|---|
| `packages/client/ui-chat/src/client/chat/message-text.ts` | **新增**：`ctx.chatMessageText` 注册表（`order` 排序、同 `id` 覆盖、disposer 只删自己那条、无注册时恒等）。这是「消息正文文本变换」的最小 seam |
| `packages/client/ui-chat/src/client/chat/AssistantMarkdown.tsx` | `text` block 在 Markdown 解析前应用变换；被清空的 block 跳过；无变换时行为与改动前逐字一致 |
| `packages/client/ui-chat/src/client/chat/AssistantNodeView.tsx` | 注入可选 `textTransform` 并下传（不传即恒等） |
| `packages/client/ui-chat/src/client/chat/register-node-renderers.ts` | assistant-step 的 inject 接上 `messageText.apply`（一个稳定函数，避免每次渲染换 identity） |
| `packages/client/ui-chat/src/client/apply.ts` | 创建并 `provide('chatMessageText')`，随插件卸载销毁 |
| `packages/client/ui-chat/src/client/index.ts` | 导出注册表类型与工厂 |
| `packages/client/ui-capability-map/src/client/result-notes.ts` | **新增** `classifyLines` 行分类器（解析器与摘除器共用）＋ `stripResultNotes`；`parseResultNotes` 改为消费同一分类器，规则零变化 |
| `packages/client/ui-capability-map/src/client/index.ts` | 通过 `ctx.inject(['chatMessageText'])` 注册 `capability-map.result-notes.body`（渲染期摘除）；导出 `stripResultNotes` |
| `packages/client/ui-capability-map/tests/strip-result-notes.client.spec.tsx` | **新增** 15 条：规则 9、渲染 3、流式 3 |
| `packages/client/ui-capability-map/tests/result-notes.client.spec.tsx` | registration 用例新增断言：注册 id 与 `stripResultNotes` 同函数 |
| `packages/client/ui-chat/tests/message-text.client.spec.tsx` | **新增** 9 条：注册表 4、渲染 seam 5（含流式/完成一致、空 block 跳过） |
| `packages/client/ui-chat/tests/reasoning-render-fixture.tsx` | 测试夹具补传注册表参数（生产签名变更） |

### 8.3 规则与流式

完整规则见 `specs/PHASE1-INTERACTION-DESIGN.md` §10.7。要点：

- 与折叠区**同一个行分类器**：标题识别、列表项、正文行结束、其它 `##` 标题结束、围栏代码块整体剔除；
- 保守：不明确匹配就原样返回（逐字节相同），`## 业务思路与取舍` 这类更长的标题不算；代码块里的同名标题不摘；
- 摘除区间两侧都是正文时补一个空行，防止两段文字被粘成一段；
- 流式与完成走同一函数、没有 `streaming` 分支；已摘内容不会回闪（唯一的过渡是标题行写全前短暂可见，方向是可见 → 隐藏）；
- 不摘「下一步」标题与列表，不改折叠区结构；
- 已知边界：按 `text` block 逐个应用；若标题与列表被工具调用切成两个 block，后一个 block 不含标题，列表会保守保留（多看一次重复，不误删正文）。

### 8.4 测试与构建（真实输出）

| 门禁 | 命令 | 结果 |
|---|---|---|
| 相关包单测 | `vitest run packages/client/ui-capability-map/tests packages/client/ui-chat/tests` | **68 passed / 1 skipped（69 文件），1185 passed / 1 skipped（1186 用例）**；其中 result-notes **30/30**、strip-result-notes **15/15**、next-steps 回归 **51/51**、message-text **9/9** |
| 客户端类型检查 | `tsc -b tsconfig.client.json` | 退出码 **0** |
| 桌面构建 | `pnpm -C apps/desktop run build` | 退出码 **0** |
| 客户端插件 bundle | `pnpm --filter @deepseek-ai/dsh-client-ui-chat bundle`、`pnpm --filter @deepseek-ai/dsh-client-ui-capability-map bundle` | 均退出码 **0**（`lib/` 为忽略产物，已含新 seam 与注册） |

> 按纪律**未打包 DMG**。
