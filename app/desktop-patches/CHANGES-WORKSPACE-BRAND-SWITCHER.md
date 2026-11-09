# CHANGES · 顶部工作区 / 品牌选择器（PHASE1 §9 · 管线 A）

> 状态：**已实现，门禁通过，未打包 DMG**（按任务要求停在验收）。
> 设计依据：`daniel-bot/specs/PHASE1-INTERACTION-DESIGN.md` §9（§9.7 已回填本文的尺寸/颜色表）。
> 源树：`/private/tmp/dsh-build/dsh-src`（Daniel 补丁栈所在的 DSH 检出）；本文件落在
> `daniel-bot/app/desktop-patches/`，并同步一份到源树 `apps/desktop/desktop-patches/`。

---

## 1. 做了什么（一句话）

把顶部 `ContextBar` 从「被动解析展示」改成**两个显式选择器**（工作区、品牌，两者必选）：
发送前缺值**不发请求**并给内联一键选择；工具结果与自己选的不一致时**只问不切**；
选择存本机、下次启动继承；下拉数据优先走桌面只读 IPC，web 构建退回「本次会话见过的」。
写入类下一步卡片补上「工作区 › 品牌 › 名单」落点。

---

## 2. 改动点

### 2.1 桌面壳层（只读 IPC，方案 A）

| 文件 | 改动 |
|---|---|
| `apps/desktop/src/daniel-context-api.ts` | **新增**。通道常量 `DANIEL_CONTEXT_IPC`、返回类型 `DanielContextResult`、`window.__dshDesktop` 契约。 |
| `apps/desktop/src/daniel-context.ts` | **新增**。CLI 入口解析（复用插件同一套：`$DANIEL_BIN` → `<profile>/node_modules/daniel-dsh-plugin/vendor/data/daniel-cli/bin/daniel`）、8s 硬超时（超时 `SIGKILL` 并返回 `timeout`）、stdout 信封解析、60s 内存缓存 + 并发合流、进程环境剥掉模型 Key 并置 `DANIEL_NO_OPEN=1`。 |
| `apps/desktop/src/daniel-context-ipc.ts` | **新增**。两个 `ipcMain.handle`，`assertSender` 校验调用方窗口；唯一接受的参数是 `refresh: boolean`（只清缓存，改不了跑哪条命令）；主进程退出前 `removeHandler`。 |
| `apps/desktop/src/preload-app.ts` | 仅在主 frame 暴露 `contextBridge.exposeInMainWorld('__dshDesktop', { danielWorkspaces, danielBrands })`，与既有 `danielAuth` 同一模式。 |
| `apps/desktop/src/main.ts` | 启动时建一个 catalog 并 `installDanielContextIpc({ assertSender: assertProductSender, catalog })`，`will-quit` 时注销。 |

**只读是结构性的**：渲染进程只能发通道名，不能传 argv / 工区 id / flag；两个命令常量本身不含 `--confirm` 或写动词（有测试钉住）。

### 2.2 客户端

| 文件 | 改动 |
|---|---|
| `packages/client/ui-capability-map/src/client/selection.ts` | **新增**。选择状态存储：持久化（`localStorage` key `dsh.daniel.workspace-brand.v1`）、桌面桥读取与失败分类、web 兜底选项、发送门 `attemptSend()`、不一致检测（同一会话同一对象只问一次）、`switchToDetected` / `keepDetected`。 |
| `.../Selector.tsx` + `Selector.module.css` | **新增**。32px 触发条、240×320 下拉、32px 搜索行、36px 选项、↑↓/Enter/Esc/输入过滤、空态「还没有工作区，去 Daniel 建一个」+「刷新」、<480px 只显示当前值并 8 字截断。 |
| `.../ContextBar.tsx` + `ContextBar.module.css` | **重写**（保留文件名与导出名 `ContextBar` / `ContextBarInjected`）。内部渲染两个选择器 + 一行不一致提示/「数据来自 X」标注。 |
| `.../SelectionNotice.tsx` + `SelectionNotice.module.css` | **新增**。发送被拒后的内联提示（`conversation.input.dock`，order −10），一个按钮「选工作区 ▾ / 选品牌 ▾」，只开下拉、不代选、不发送。 |
| `.../context.ts` | `ContextSnapshot` 增加 `workspaces[]` / `brands[]`（本次会话见过的），供 web 兜底；快照签名带上两张表的规模，新行也能触发重绘。 |
| `.../next-steps.ts` + `NextSteps.tsx` + `NextSteps.module.css` | 新增 `isWriteStep` / `listNameOf` / `writeTargetOf`；写入类卡片第二行显示「将写入 工作区 › 品牌 › 名单」。 |
| `.../locales.ts` | 新增 24 个 zh/en 文案键（选择器、空态、超时、不一致、发送门、写入落点）。 |
| `.../index.ts` | 组装：建 `ContextSelection`、注入两个选择器与动作、注册内联提示、把发送门注册进会话服务。 |

### 2.3 会话发送路径（唯一的架构性改动）

顶部选择器属于能力地图包，而发送由 `ui-conversation` 的 composer 负责，依赖方向不能反过来。
因此加了一条**通用**缝隙（不含任何 Daniel 字样）：

| 文件 | 改动 |
|---|---|
| `packages/client/ui-conversation/src/client/contract/send-guard.ts` | **新增**。`ComposerSendBlock` / `ComposerSendGuard` / `ComposerSendGuards`。 |
| `.../input/send-guard.ts` | **新增**。按注册顺序求值的注册表，第一个 block 胜出。 |
| `.../service.ts`、`apply.ts` | `ctx.conversation.sendGuard` 暴露给业务插件。 |
| `.../input/facade.ts` | `SessionInputShell.submit()` 在派发前询问门；有 block 就 `return`：**不派发、不发请求、草稿原样保留**。空草稿的 Enter（队列/停止手势）不询问。 |
| `.../input/hub.ts` | 把门惰性解析成 shell 依赖（服务未装配时为 undefined，不影响独立使用）。 |
| `.../index.ts` | 导出以上类型。 |

### 2.4 文档

| 文件 | 改动 |
|---|---|
| `daniel-bot/specs/PHASE1-INTERACTION-DESIGN.md` | §9 末尾追加 **§9.7「样式规格（已实现）」**：选择器、下拉、窄屏、提示四张表 + 实现文件。 |
| 本文件 | 改动点、IPC 契约、测试证据、风险。 |

---

## 3. IPC 契约

```
通道：daniel:workspaces        参数：refresh?: boolean
通道：daniel:brands            参数：refresh?: boolean
```

返回（成功）：

```ts
{ ok: true, items: [{ id: 90002, name: 'jack' }] }                     // workspaces
{ ok: true, items: [{ id: '4800023', name: 'Halliday', workspaceId: 90002 }] }  // brands
```

返回（失败，永不抛异常；`refresh` 只是绕过 60s 内存缓存，不能改命令）：

```ts
{ ok: false, reason: { kind: 'timeout' } }
{ ok: false, reason: { kind: 'cli',       message: '登录已过期' } }
{ ok: false, reason: { kind: 'malformed', message: 'unparseable CLI output' } }
```

执行的命令（固定，不接受渲染进程输入）：

```
python3 <entry> account workspaces --json
python3 <entry> brands list --json --limit 200
```

`<entry>` 解析顺序（与内置插件完全一致，文件里没有本机绝对路径）：
`$DANIEL_BIN` → `<profile>/node_modules/daniel-dsh-plugin/vendor/data/daniel-cli/bin/daniel`。

**真实返回样例**（直接跑 catalog 读本机 Daniel，非构造数据）：

```json
{ "ok": true, "count": 122, "sample": [
  { "id": 60003,   "name": "Admin Workspace" },
  { "id": 90001,   "name": "Alia" },
  { "id": 1170002, "name": "Anta Sports" } ] }
{ "ok": true, "count": 200, "sample": [
  { "id": "4200006", "name": "Manspot", "workspaceId": 1200001 },
  { "id": "3480001", "name": "aeke",    "workspaceId": 90001 },
  { "id": "180001",  "name": "Anker",   "workspaceId": 60001 } ] }
```

缓存实测：首读 4.0s（两条命令），二次读 0ms 且结果逐字节相同（60s TTL 内）。

---

## 4. 行为对照（§9.6 验收）

| 场景 | 行为 |
|---|---|
| 未选工作区点发送 | composer 不派发，输入框上方出现「先选一个工作区，我才能查你的数据 [选工作区 ▾]」；点按钮只开下拉。 |
| 已选工作区、未选品牌 | 同样拦截，提示改为品牌；选完不自动发送。 |
| 两者都选 | 正常发送，顶部显示两个名字。 |
| 工具结果来自别的工作区 | 顶部选择器**下一行**（即会话结果区顶部）出现「这次查到的是 mike 的数据，当前选的是 jack [切到 mike] [保持]」；不自动切、不遮挡结果。 |
| 点「切到 mike」 | 选择更新，提示消失。 |
| 点「保持」 | 选择不变，出现「数据来自 mike」标注（新任务开始时清掉）。 |
| 同一会话同一对象 | 只提示一次（`asked` 集合），同一结果重复到达不再打扰。 |
| 重启应用 | 从 `localStorage` 继承上次的工作区/品牌。 |
| web 构建（无 `window.__dshDesktop`） | 下拉只列本次会话工具结果里见过的，并在底部标注「仅显示本次会话见过的」。 |
| 写入类下一步卡片 | 卡片第二行「将写入 jack › Halliday › 第十一批」（缺哪半显示「未选择工作区/品牌」）。 |

---

## 5. 测试证据

### 5.1 选择器 DOM（未选虚线 / 已选实线）

```
UNSELECTED>>> <button type="button" class="_trigger_6d60a9 _empty_6d60a9" data-selector="workspace"
  data-selected="false" aria-haspopup="listbox" aria-expanded="false" aria-label="工作区：未选择">
  <span class="_label_6d60a9">工作区</span>
  <span class="_value_6d60a9" data-selector-value="workspace">未选择</span>
  <span class="_caret_6d60a9" aria-hidden="true">▾</span></button>

SELECTED>>> <button type="button" class="_trigger_6d60a9 _selected_6d60a9" data-selector="workspace"
  data-selected="true" aria-haspopup="listbox" aria-expanded="false" aria-label="工作区：jack">
  <span class="_label_6d60a9">工作区</span>
  <span class="_value_6d60a9" data-selector-value="workspace">jack</span>
  <span class="_caret_6d60a9" aria-hidden="true">▾</span></button>
```

样式由 `Selector.module.css` 钉死（测试直接读 CSS 源断言）：
`.trigger { height: 32px; padding: 0 10px; border: 1px solid #E5E6EB; border-radius: 8px; font-size: 13px; font-weight: 500 }`、
`.trigger:hover { background: #F5F6F7 }`、`.empty { border-style: dashed; border-color: #C9CDD4 }`、
`.menu { min-width: 240px; max-height: 320px }`、`.search { height: 32px }`、`.option { height: 36px }`、
`@media (max-width: 480px) { .label { display: none } .value { max-width: 8em } }`、`ContextBar.module.css .row { gap: 8px }`。

空数据下拉实拍：

```
<div data-selector-menu="workspace">
  <input aria-label="搜索工作区" placeholder="搜索工作区" value="">
  <div data-selector-empty="workspace"><span>还没有工作区，去 Daniel 建一个</span><button>刷新</button></div>
  <div data-selector-footer="workspace">仅显示本次会话见过的</div>
</div>
```

### 5.2 缺值发送被拦（不发请求的断言）

`packages/client/ui-conversation/tests/send-guard.client.spec.ts`：
注册一个 block 后 `shell.submit()`，断言 **sink（通往 Host 的唯一出口）一次都没被调用**、草稿原样保留；清掉 block 后同一草稿才发送。

`packages/client/ui-capability-map/tests/selection.client.spec.tsx`：
用**与 `index.ts` 相同的 guard 组装方式**把门交给真实 `SessionInputShell`，断言 `sink` 未被调用、`missing === 'workspace'`；
选完工作区再提交 → `missing === 'brand'`，仍然 `sink` 未调用；选完品牌后仍不自动发送。

### 5.3 不一致提示只出现一次

`selection.client.spec.tsx › mismatch prompting › asks once per object and never switches on its own`：
同一 `90003` 结果第二次到达时 `mismatch` 为 `undefined`（`asked` 集合）；并且选择始终停在 `90002`（未自动切）。

### 5.4 测试与构建退出码

```
$ pnpm exec tsc -b tsconfig.client.json
TSC_EXIT=0

$ pnpm -C apps/desktop run build
✔ built in 387ms
BUILD_EXIT=0

$ pnpm exec vitest run packages/client/ui-capability-map/tests
Test Files  8 passed (8)
     Tests  185 passed (185)

$ pnpm exec vitest run packages/client/ui-conversation/tests      # 全量回归
Test Files  55 passed (55)
     Tests  889 passed (889)

$ pnpm exec vitest run apps/desktop/tests/daniel-context.spec.ts apps/desktop/tests/daniel-plugin.spec.ts
Test Files  2 passed (2)
     Tests  18 passed (18)

$ pnpm run build:lib:client        # 客户端产物（含新 CSS/组件）
CLIENT_BUNDLE_EXIT=0
```

新增/改写测试清单：

- `apps/desktop/tests/daniel-context.spec.ts`（13）：只读 argv / 无 `--confirm`、通道名、entry 解析、环境剥离、两段 payload 解析、60s TTL、超时 `SIGKILL`、并发合流、失败不缓存。
- `packages/client/ui-capability-map/tests/selection.client.spec.tsx`（14）：选择器渲染/键盘/空数据/超时、发送门（含跨包真实 shell）、不一致只问一次、持久化读。
- `packages/client/ui-capability-map/tests/context-bar.client.spec.tsx`（30，改写 strip 段）：两个选择器、未选/已选、不一致提问、无请求、尺寸断言。
- `packages/client/ui-capability-map/tests/next-steps.client.spec.tsx`（+5）：写入卡片落点。
- `packages/client/ui-conversation/tests/send-guard.client.spec.ts`（5）：门语义。

---

## 6. 风险与未做

1. **选择尚未注入模型请求上下文（§9.4 前半句未做）**：当前选择只用于「发送前校验 + 顶部展示 + 卡片落点」，没有作为请求上下文带给模型。本轮验收清单不含该项；若要做，应在会话请求组装处注入（`ui-conversation` 的 send 路径或 Host 侧），需单独立项。
2. **`brands list` 会读本地品牌索引**：索引已存在时纯读（本机实测 `indexBuiltAt 2026-11-02`，无写盘）；索引缺失时 CLI 会自建缓存。IPC 层本身不写任何文件，但这条命令的既有行为不受本改动控制。
3. **首次读 4.0s**：两条命令串行上限 8s，本机实测约 2.8s + 0.9s；冷启动时下拉会先显示「正在读取…」。超时按 8s 报 `timeout`，不重试。
4. **不一致检测依赖会话事件里的结构化字段**：沿用 `context.ts` 现有解析（`activeWorkspaceId` / `workspaces[]` / `--brand`），结果里没有这些字段就不会提示（宁可不问，不猜）。
5. **「保持」的标注是顶部一条标注，不是逐条结果贴标**：同一任务的标注在下一个用户任务开始时清掉；若要逐条消息级打标，需要在消息节点上存状态，属后续增强。
6. **未打包 DMG**：按任务要求停在验收；`build:lib:client` 已产出新客户端 bundle，桌面壳层 bundle 也已重建。
7. **两棵源树**：实现提交在 `/private/tmp/dsh-build/dsh-src`（Daniel 补丁栈所在检出）；工作区内的 `daniel-bot/build/dsh-src` 是打包用的干净树、不含 `ui-capability-map`，故未在那里实现。
