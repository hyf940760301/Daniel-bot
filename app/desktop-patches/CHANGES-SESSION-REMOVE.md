# CHANGES · 会话列表「移除会话」：一次确认的归档式移除

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，基线 `ce7073d5`，已含品牌/登录/主题/能力全景/执行透视/轨栏）
> 改动包：`packages/client/ui-workspace`（既有包内改，**不新增包、不新增依赖、不新增 CSS、不新增请求**）
> 状态：**类型检查 / 客户端 bundle / 桌面构建 / 单测全绿；未打包（按纪律）**
> 一句话：悬停会话行出现的「…」菜单新增最后一项「移除会话」（危险色）。点它先弹**一次**确认（标题「移除这个会话？」／正文「移除后会从列表消失，可在归档中找回。」／按钮「取消」「移除」，默认焦点在「取消」，Esc＝取消）；确认后走**既有归档入口**，会话从列表消失、进归档可找回；**正在运行的会话该项置灰**并在菜单里写明原因。

---

## 0. 用户裁决 → 落点

| # | 裁决 | 实现落点 |
|---|---|---|
| 1 | 移除＝归档（可从归档找回），不是物理删除 | 只调既有 `UiWorkspaceService.archiveSession`（`navigation.ts:382`）→ `workspaces.archiveSession`；不碰会话日志、不碰磁盘。会话 id 进注册表的 `archivedSessionIds` |
| 2 | 入口＝悬停会话行的「…」按钮 | 复用既有的行内触发按钮（`rows/Rows.tsx:753-761`）与其菜单；本次只往共享菜单加一行（`session-actions/context-menus.tsx:85`），**没有新造触发器** |
| 3 | 必须二次确认，文案要让用户知道「能找回」 | 确认框复用既有 `shell.overlay` 的 `workspace.session-archive` 条目与 `archiveRequest` 快照，请求带 `mode:'remove'`（`contract/slots.ts:400-414`）；正文即「移除后会从列表消失，可在归档中找回。」 |
| 4 | 成功后从列表移除并选中相邻会话（或新建会话） | 移除后 archived 集合更新、默认过滤器不再列出该行；被移除的若是**当前会话**，走既有 `clearMain()`（`navigation.ts:384`、`515`）落到**新建会话**视图——即裁决里「或新建会话」那一支（取舍见 §4.2） |
| 5 | 失败给 toast，不静默 | `index.ts:245-253`：`archiveSession` 失败 → `notify({ kind: 'removeFailed' })` + `console.warn`；toast 文案「移除会话失败，该会话仍在列表中，请重试」（`toast/register.ts:74-79`） |
| 6 | 运行中的会话：禁用该项并给出原因，不能点了没反应 | `tree.ts:398` `runningSessionIds()` 判定「自己的回合在跑，或直接子智能体在跑」；菜单项 `disabled`，标签改为「移除会话（会话运行中，需先停止）」（`context-menus.tsx:89`）。原生 disabled 按钮不可能被点中，原因直接写在菜单项里 |

---

## 1. 入口：沿用既有「…」按钮（零新增 DOM）

| 事实 | 位置 |
|---|---|
| 「…」按钮已存在，点击即开该会话的菜单（`openSessionMenu(..., 'toggle')`） | `rows/Rows.tsx:753-761` |
| 可访问名沿用既有 `actions.session.aria`：zh＝`会话“{name}”的操作`（含「会话操作」语义，并带行名以便同名行区分） | `locales.ts:107` |
| 按钮静止隐藏、悬停／菜单打开／键盘模态下 focus-within 才显示 | `rows/Rows.module.css:273-278`（`.rowActions{display:none}`）、`317-332`（`:hover` / `.menuOpen` / `:focus-within` → `inline-flex`） |
| 行可 Tab 聚焦（`tabIndex={0}`），标题有自己的省略号车道，动作条是 flex 兄弟节点，不遮挡标题 | `rows/Rows.tsx:667`、`716-733`；`Rows.module.css:181-188`（`.title` 的 `min-width:0 / text-overflow:ellipsis`） |
| 菜单上下键/Home/End/Enter/Esc 与关闭回焦由共享菜单原语负责 | `packages/client/ui-primitives/src/Menu.tsx:409-500` |

**为什么没改 aria-label**：这段可访问名已被装配测试与 `packages/experimental/liveshare` 的只读回归用 `/^会话“/` 锁定；改字符串会外溢到别的包。按钮语义（会话操作）与行名区分度都在，故保留，并在此明写。

---

## 2. 菜单项

- 位置与顺序：`order 700`、`afterContent`（与「归档会话」同在弹层尾部）、`separatorBefore`、`danger:true`、图标 `workspace.remove`（垃圾桶，`index.ts:306`）。
  实测菜单顺序（`rename-assembly` 与 `session-remove-assembly` 双重锁定）：
  `置顶会话 → 重命名 → 分叉会话 → 复制 Session ID →（外部插件插入项）→ 归档会话 → 移除会话`。
- 显隐条件：`workspace/archiveSession` 权限允许 **且** 该会话未在归档集合中 → 才出现；归档行不出现（`context-menus.tsx:86`）。
- 运行中：`disabled:true`，标签含原因；`observe` 里挂了 `actions.running`，会话开始/停止运行会**就地**把该项置灰或恢复，无需重开菜单（`context-menus.tsx:94`）。

---

## 3. 二次确认

复用既有确认面：请求仍写进 `archiveRequest` 快照，仍由 `shell.overlay` 的 `workspace.session-archive` 条目渲染；只有 `mode:'remove'` 时换成移除文案与「不停止任何工作」的路径（`session-actions/ArchiveSession.tsx:79-140`）。

**渲染文本（zh，真实输出，来自 jsdom 渲染结果）**

```
TITLE:   移除这个会话？
TEXT:    移除这个会话？移除后会从列表消失，可在归档中找回。取消移除
BUTTONS: 关闭(X) | 取消(autofocus) | 移除
ACTIVE:  取消
```

- 标题：`remove.confirm.title` =「移除这个会话？」（`locales.ts:91`）
- 正文：`remove.confirm.desc` =「移除后会从列表消失，可在归档中找回。」（`locales.ts:92`）
- 按钮：`取消` / `移除`；`移除` 复用了既有的危险按钮类 `deleteAction`（`WorkspaceBrowser.module.css:614` → `var(--dsw-alias-state-error-primary)`）。
- 默认焦点在「取消」：按钮带 `data-modal-autofocus`（`ArchiveSession.tsx:111`），模态层据此先记录触发控件再移焦（`useModalLayer.ts:67-69`）。
- Esc＝取消：模态层的 Escape 走 `onClose` → `settleSessionArchive()`，只清请求、不归档（`ArchiveSession.tsx:80-84`）。
- 移除请求**不列**「将被停止的工作」清单（那是 `stop-and-archive` 模式的 UI）；`activity` 为空数组。
- 八国语言齐全（zh/en/ja/es/fr/de/ru/pt，`locales.ts` 各字典同步）。

---

## 4. 执行：复用既有归档入口（不新造第二套）

### 4.1 调用链（文件:行）

| 步骤 | 位置 |
|---|---|
| 菜单项 → 只是「请求确认」，不归档 | `context-menus.tsx:92` → `requestSessionRemoval` |
| 请求写入既有快照（带 `mode:'remove'`，并**重查** `workspace/archiveSession` 权限，避免菜单打开后权限被收回仍能移除） | `index.ts:179-183` |
| 确认 → `removeSession` | `index.ts:245-253` |
| **既有归档入口**（本次没有新增归档实现） | `navigation.ts:382` `UiWorkspaceService.archiveSession(sessionId)` |
| 落到 Host 的注册表写入 | `workspaces.archiveSession`（api-workspace-controller 客户端） |
| 行消失的机制 | `archivedSessionIds` 更新 → 默认过滤器 `sessionVisible()` 不再列出；归档行可在「全部对话（显示已归档）」里找回（既有筛选） |
| 当前会话被移除 | `navigation.ts:384`：`if (this.mainReference?.sessionId === sessionId) this.clearMain()` → 落到新建会话视图 |
| 失败 | 捕获 → `notify({ kind:'removeFailed' })` + `console.warn('session removal rejected:', reason)`；**不 resolve 成成功**（toast 明说「仍在列表中」） |

### 4.2 为什么是「新建会话」而不是「相邻会话」

裁决允许「相邻会话（或新建会话）」。相邻选中需要在移除瞬间复制一份**可见顺序**（分组/置顶/归档过滤/手动排序四层派生都在 `tree.ts` + 视图 store 里，且属于浏览器组件的渲染态），在归档服务层再算一遍会变成第二套顺序，容易与列表显示不一致。
因此这里遵守既有归档语义：**被移除的是当前会话 → 新建会话视图；不是当前会话 → 只从列表消失**。若后续确需「选中相邻」，单点改法是在 `navigation.archiveSession` 收尾处从同一份派生顺序取邻居再 `openSession`（需要把可见顺序下沉到服务层），不影响本次的菜单/确认/归档链路。

### 4.3 成功后的提示

确认本身就是撤销点（取消＝不删）。确认成功后不再弹「已归档」snackbar：行已消失、归档筛选里可找回；失败才弹 toast。这样避免与既有「归档会话」成功后的 undo 提示重复（那条仍保留在原「归档会话」入口上）。

---

## 5. 例外：正在运行的会话

- 判据：`runningSessionIds(list)`（`tree.ts:398-411`）——**会话自己的回合在跑**，或**任一直接子智能体在跑**（读 `projectionsBySession[sessionId].values.subagentCatalog`，且子会话 summary 仍标 `running`）。规则与行上状态点同源。
- 派生：`index.ts:166` `const runningSet = derive(sessions.list, runningSessionIds)`，只随会话列表快照重建。
- 消费：菜单 `observe` 里包含该集合（`context-menus.tsx:94`），会话运行状态变化会重解析菜单项。
- 呈现：`disabled:true` + 标签「移除会话（会话运行中，需先停止）」（`locales.ts:65`）。原生 `<button disabled>`，点击不会触发任何回调——**不存在「点了没反应」**；原因就在同一行文字里（共享菜单的数据行不支持 tooltip 字段，故用菜单内说明，符合裁决「tooltip 或菜单内说明」）。
- 为什么不顺手改成「停止并归档」：那是既有「归档会话」入口在 Host 拒绝后弹的 `stop-and-archive` 二次确认；移除是「不打断工作」的轻轻一按，运行中直接不给按，避免两条危险路径互相顶替。

---

## 6. 视觉

- **零新增 CSS**：动作条、图标按钮、危险按钮全部复用既有类与 token。
  - hover 按钮：`Rows.module.css:453-478`（`.iconButton`，含 `:focus-visible` 环）
  - 危险色：`WorkspaceBrowser.module.css:614-616` `.deleteAction:not(:disabled){color:var(--dsw-alias-state-error-primary)}`
  - 菜单行危险态：共享菜单 `Menu.module.css` 的 `.danger`（由 `danger:true` 驱动）
- 只用 `--dsw-*` token（error / label / interactive-bg 等既有别名），深浅色由既有 token 定义承担，没有新增颜色常量。
- 长标题：`.title` 的 `min-width:0 / overflow:hidden / text-overflow:ellipsis` 未动；动作条是 flex 兄弟不覆盖标题（`Rows.module.css:181-188`、`207-209`）。

---

## 7. 测试证据

### 7.1 命令与结果

```
$ pnpm exec vitest run packages/client/ui-workspace/tests
 Test Files  16 passed (16)
      Tests  529 passed (529)
   EXIT=0
```

基线同套件为 **512 passed**，本次净增 **17 条**（其中 8 条落在新的整链装配文件 `session-remove-assembly.client.spec.tsx`）。另跑依赖本行菜单/可访问名的跨包回归：

```
$ pnpm exec vitest run packages/experimental/liveshare/tests/viewer-write-artifact.client.spec.tsx
 Test Files  1 passed (1)
      Tests  1 passed (1)
```

### 7.2 裁决要求的 8 项 → 对应测试

| 要求 | 测试（文件:行 / 名称） |
|---|---|
| 悬停出现 | `session-remove-assembly.client.spec.tsx:248`「keeps the hover trigger hidden until the row is hovered, focused, or its menu is open」（断言 `.rowActions{display:none}` 与 `:hover/.menuOpen/:focus-within → inline-flex`） |
| 点击开菜单 | `session-remove-assembly.client.spec.tsx:128`「offers 移除会话 as the last row action…」（点行内「…」→ 菜单出现，含全部 6 行） |
| 菜单有「移除会话」 | 同上（顺序断言到 `归档会话 → 移除会话`）；数据层：`session-menu-actions.client.spec.ts`「offers removal as the last destructive row…」 |
| 点它弹确认框 | `session-remove-assembly.client.spec.tsx:128`（标题/正文/按钮/默认焦点/未归档）；单测：`session-actions.client.spec.tsx`「asks the removal question with the archival copy and starts on Cancel」 |
| 确认后调归档且行消失 | `session-remove-assembly.client.spec.tsx:166`「confirming archives the session and the row leaves the list」 |
| 取消不调归档 | `session-remove-assembly.client.spec.tsx:151`「cancelling archives nothing and keeps the row」＋`session-actions.client.spec.tsx`「cancelling never archives」 |
| 运行中会话禁用 | `session-remove-assembly.client.spec.tsx:216`「disables removal while the session runs and says why」＋`session-menu-actions.client.spec.ts`「disables removal while the session works…」＋`tree.client.spec.ts`「reports a running turn and a running direct child as live work…」 |
| Esc 关闭且焦点回到「…」按钮 | `session-remove-assembly.client.spec.tsx:185`「Escape closes the menu and returns focus to the row actions trigger」＋`session-actions.client.spec.tsx`「Escape cancels and returns focus to the row action trigger that raised it」 |

补充：键盘可达（Down/End 走到「移除会话」，该行是原生 button，Enter 即原生激活并打开确认）——`session-remove-assembly.client.spec.tsx:199`；失败非静默——`apply.client.spec.ts`「reports a refused removal through the notice instead of failing silently」。

### 7.3 两条断言原文（验收点名）

**「取消不删」**（装配层，`session-remove-assembly.client.spec.tsx:158-162`）：

```ts
    await waitFor(() => { expect(view.queryByRole('dialog')).toBeNull() })
    // 取消不删：the Host was never asked, the archive set is unchanged, the row stays.
    expect(archiveCalls(runtime)).toHaveLength(0)
    expect(runtime.workspaces.list.getSnapshot().archivedSessionIds).not.toContain(SID)
    expect(view.getByText(TITLE)).toBeTruthy()
```

单测层同一命题（`session-actions.client.spec.tsx:455-457`）：

```ts
      fireEvent.click(screen.getByRole('button', { name: '取消' }))
      expect(removeSession).not.toHaveBeenCalled()
```

**「确认才删」**（装配层，`session-remove-assembly.client.spec.tsx:175-180`）：

```ts
    // 确认才删：the row disappears through the existing archive hop.
    await waitFor(() => { expect(view.queryByText(TITLE)).toBeNull() })
    await waitFor(() => { expect(view.queryByRole('dialog')).toBeNull() })
    expect(archiveCalls(runtime)).toEqual([{ method: 'archiveSession', args: [SID] }])
    // Removal is archival: the id sits in the archived set, not a deleted log.
    expect(runtime.workspaces.list.getSnapshot().archivedSessionIds).toContain(SID)
```

单测层（`session-actions.client.spec.tsx:446-448`）：

```ts
      fireEvent.click(screen.getByRole('button', { name: '移除' }))
      expect(removeSession).toHaveBeenCalledExactlyOnceWith(sid('one'))
      expect(stopAndArchiveSession).not.toHaveBeenCalled()
```

### 7.4 运行中会话的实测

- 菜单里那一行的可访问名为「移除会话（会话运行中，需先停止）」，`disabled` 属性为真；点它既不弹框也不归档（`archiveCalls(runtime)` 长度 0）——`session-remove-assembly.client.spec.tsx:216-226`。
- 运行判定覆盖「子智能体在跑但父会话自己没在跑」：`tree.client.spec.ts` 用 `projectionsBySession[parent] = subagentCatalog([child])` + `child.running = true` 断言父会话被算作 live work。

---

## 8. 门禁（真实退出码）

| 门禁 | 命令 | 结果 |
|---|---|---|
| 客户端类型检查 | `pnpm exec tsc -b tsconfig.client.json` | **exit 0**，无输出 |
| ui-workspace bundle | `pnpm -C packages/client/ui-workspace run bundle` | **exit 0**（`lib/client.js` 295.16 kB / gzip 68.39 kB；Build complete） |
| 桌面构建 | `pnpm -C apps/desktop run build` | **exit 0**（`✓ built in 416ms`，welcome 资产正常） |
| 单测 | `pnpm exec vitest run packages/client/ui-workspace/tests` | **exit 0**，16 files / 529 tests passed |

未执行打包（`package:desktop`），按任务纪律。

---

## 9. 变更文件

**源码（7）**

| 文件 | 作用 |
|---|---|
| `packages/client/ui-workspace/src/client/contract/slots.ts` | `SessionArchiveConfirmRequest.mode?: 'remove'`；`ArchiveSessionInjected.requestSessionRemoval`；`SessionArchiveConfirmInjected.removeSession`；Toast 增 `removeFailed` |
| `packages/client/ui-workspace/src/client/tree.ts` | 新增 `runningSessionIds(list)`（自身回合 / 直接子智能体） |
| `packages/client/ui-workspace/src/client/index.ts` | `runningSet` 派生；`requestSessionRemoval`；`removeSession`（失败 toast）；`workspace.remove` 图标；把 `running` 交给菜单注册 |
| `packages/client/ui-workspace/src/client/session-actions/context-menus.tsx` | 新增 `session.remove/remove`（order 700、danger、afterContent、运行中 disabled+原因、observe running） |
| `packages/client/ui-workspace/src/client/session-actions/ArchiveSession.tsx` | 确认对话框按 `mode` 分支：移除文案/不列工作/焦点在取消/走 `removeSession` |
| `packages/client/ui-workspace/src/client/toast/register.ts` | 注册 `removeFailed` 通知（warning，6s） |
| `packages/client/ui-workspace/src/client/locales.ts` | 8 语言 × 7 键（menu.removeSession / menu.removeSessionRunning / remove.confirm.title/desc/action/pending / toast.removeFailed） |

**测试（6）**

| 文件 | 改动 |
|---|---|
| `tests/session-remove-assembly.client.spec.tsx` | **新增**：整链装配 7 条 + hover 样式 1 条 |
| `tests/session-actions.client.spec.tsx` | 确认框夹具加 `removeSession`/`mode`；新增移除模式 4 条 |
| `tests/session-menu-actions.client.spec.ts` | 菜单数据层：删除项顺序/危险态、运行中禁用、归档/无权限撤回（+3 条） |
| `tests/apply.client.spec.ts` | 移除失败 toast（+1 条）；toast 键清单补 `removeFailed` |
| `tests/tree.client.spec.ts` | `runningSessionIds` 判定（+1 条） |
| `tests/rename-assembly.client.spec.tsx` | 既有菜单顺序/分隔线/End 焦点断言随新行更新（行为未变，只是多了一行） |

**文档（1）**：本文件。

---

## 10. 边界与明确未做

1. **相邻会话选中**：未做，走裁决允许的另一支（新建会话，见 §4.2）；原因是不在服务层复制列表顺序。
2. **性能**：唯一的全局派生是一个 Set，随 `sessions.list` 快照重建（与既有 `pinnedSet`/`archivedSet` 同款），每行一次 `has()`。
3. **权限**：移除项与「归档会话」同权限（`workspace/archiveSession`），没有引入新端点；请求时二次校验。
4. **文案**：「移除」不写「删除」——避免用户以为日志被物理删除；正文明确「可在归档中找回」。
5. **不新增依赖、不新增请求、不新增包。**
