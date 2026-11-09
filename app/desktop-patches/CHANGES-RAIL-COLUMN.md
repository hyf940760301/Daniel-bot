# CHANGES · 能力地图改壳：从浮层竖条 → 真实左侧列

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，已含品牌/登录/主题与 `ui-capability-map`）
> 状态：**类型检查 / 桌面构建 / 客户端 bundle / 相关单测全绿；未打包（按纪律）**
> 一句话：把能力地图从 `shell.overlay` 浮层挪成网格里的**第一条真实轨道**（`shell.rail`），侧栏像素不再被压住；轨道宽度由 `computeColumns` 统一解算（收起 48 / 展开 320），窄屏先让 rail 收起，抽屉态整列不挂。

---

## 1. 为什么要改壳

上一版（`CHANGES-CAPABILITY-MAP.md` §1.2）把 48px 竖条注册在 `shell.overlay`：它是**浮层**，`position:absolute; left:8px`，侧栏展开时压在侧栏最左侧 48px 之上，且与 `shell.leading` 这类窗口 chrome 同层语义。当时明确记录了"要做成真正的列需要改 `AppFrame` 的轨道"。

这次就改这条轨道：网格从 3 列变 4 列

```
rail | sidebar | center | rightbar
```

能力栏在自己的轨道里绘制，**任何宽度下都不与侧栏的像素重叠**；宽度不再写死在组件 CSS 里，而由 `columns.ts` 与其它三列一起解算。

---

## 2. `columns.ts`：改前 / 改后

> 任务单里写的是 `solveColumns()`；本仓实际导出的函数名是 **`computeColumns()`**（`ui-layout/src/client/columns.ts`，唯一的几何解算入口）。名字未改，避免动无关调用面；语义按任务单执行。

### 2.1 签名

```ts
// 改前
export interface Columns { sidebar: number; center: number; rightbar: number }
export function computeColumns(
  viewport: number, sidebar: number, rightbar: number,
  collapsedWidth = SIDEBAR_COLLAPSED, centeredSidebar = false,
): Columns

// 改后
export interface Columns { rail: number; sidebar: number; center: number; rightbar: number }
export const RAIL_COLLAPSED = 48
export const RAIL_EXPANDED = 320
export function computeColumns(
  viewport: number, sidebar: number, rightbar: number,
  collapsedWidth = SIDEBAR_COLLAPSED, centeredSidebar = false,
  rail = 0,                       // 0=不挂载（抽屉态）；48=竖条；320=面板
): Columns
```

`rail` 用**宽度偏好**而不是布尔：和 `sidebar` 的 `0 = 收起` 同一套写法，调用方可以把"抽屉态整列不挂载"与"用户收起"区分开。默认 `0` 让这个纯函数对既有调用方保持零行为变化（旧测试只需补 `rail: 0`）。

### 2.2 关键分支（真实 diff 片段）

```diff
   const s = sidebar === 0 ? collapsedWidth : centeredSidebar ? viewport / 2 : clampWidth(sidebar, SIDEBAR_MIN, SIDEBAR_MAX)
-  const available = viewport - s - CENTER_MIN
+  // The rail is the first concession: an expanded rail holds its 320px only
+  // when the sidebar and an open right track still leave the center its
+  // protected minimum. Otherwise it drops to the 48px strip — it never pushes
+  // the center below CENTER_MIN and never forces an open right panel shut.
+  const railRequest = rail <= 0 ? 0 : rail >= RAIL_EXPANDED ? RAIL_EXPANDED : RAIL_COLLAPSED
+  const rightDemand = rightbar === 0 ? 0 : RIGHTBAR_MIN
+  const railWidth = railRequest === RAIL_EXPANDED && viewport - RAIL_EXPANDED - s - rightDemand >= CENTER_MIN
+    ? RAIL_EXPANDED
+    : railRequest === 0 ? 0 : RAIL_COLLAPSED
+  const available = viewport - railWidth - s - CENTER_MIN
   const r = rightbar === 0 || available < RIGHTBAR_MIN
     ? 0
     : Math.min(available, clampWidth(rightbar, RIGHTBAR_MIN, viewport * RIGHTBAR_MAX_RATIO))
-  return { sidebar: s, center: Math.max(0, viewport - s - r), rightbar: r }
+  return { rail: railWidth, sidebar: s, center: Math.max(0, viewport - railWidth - s - r), rightbar: r }
 }
```

让步顺序（从左到右，越靠前越先让步）：

1. **rail**：320 会挤破中栏 400 最小宽、或会把已打开的右栏挤到 300 以下 → 降级 48；
2. **rightbar**：缩到 300，再不行整条轨道撤掉（原规则，未改）；
3. **center**：只有在右栏轨道不存在时才允许低于 400，最低 0（原规则，未改）。

`sidebar` 的取值规则（264–420 夹取、`0` 用 `collapsedWidth`、折叠横屏取 `viewport / 2`）**一行未动**；rail 不参与 sidebar 的宽窄，也不改变中点对齐语义（中点仍按整帧算）。

---

## 3. 三个视口的解算结果（脚本真实输出）

脚本 `/tmp/rail-columns.ts` 直接 import `computeColumns` 打印（`node_modules/.bin/tsx` 跑）：

```text
1280px desktop rail request=strip(48 request)   -> rail= 48  sidebar=  280  center= 952  rightbar=0  Σ=1280
1280px desktop rail request=panel(320 request)  -> rail=320  sidebar=  280  center= 680  rightbar=0  Σ=1280
 900px narrow  rail request=strip(48 request)   -> rail= 48  sidebar=   56  center= 796  rightbar=0  Σ=900
 900px narrow  rail request=panel(320 request)  -> rail=320  sidebar=   56  center= 524  rightbar=0  Σ=900
 700px drawer  rail request=hidden              -> rail=  0  sidebar=    0  center= 700  rightbar=0  Σ=700
1280px + right panel(864)            -> rail= 48  sidebar=  280  center= 400  rightbar=552
 900px + right panel(864)            -> rail= 48  sidebar=   56  center= 400  rightbar=396
 700px + right panel(864)            -> rail=  0  sidebar=    0  center= 400  rightbar=300
```

读法（与 AppFrame 的入参一致）：

| 视口 | 模式 | sidebar 入参 | rail 结果 | sidebar 结果 | center | 说明 |
|---|---|---|---|---|---|---|
| 1280 | 桌面 | 280（≥1024 展开） | 48 / 320 | 280 | 952 / 680 | 两种 rail 状态都放得下 |
| 900 | 窄屏（<1024 自动收起） | 0 → 56 | 48 / 320 | 56 | 796 / 524 | 320 面板仍不挤破 400 |
| 700 | 抽屉（<768） | 0 | **0（不挂载）** | 0 | 700 | 抽屉覆盖中栏，rail 让位 |

最后三行是"rail 先让步"的证据：1280 打开 864 右栏时，若 rail 硬撑 320，右栏只剩 (1280−320−280−400)=280 < 300 会被**整条关掉**；rail 降到 48 后中栏正好 400、右栏保住 552。

---

## 4. `AppFrame.tsx`：四轨网格 + `shell.rail`

### 4.1 网格

```diff
- `${cols.sidebar}px minmax(${cols.rightbar === 0 ? 0 : CENTER_MIN}px, 1fr) minmax(0px, ${rightbarMax}px)`
+ `${railWidth}px ${cols.sidebar}px minmax(${cols.rightbar === 0 ? 0 : CENTER_MIN}px, 1fr) minmax(0px, ${rightbarMax}px)`
```

列位随之外移：`.railCol` = grid-column 1、`.sidebarCol` = 2、`.centerCol` = 3、`.rightbarCol` = 4；`.bottomRow` 仍是 `1 / -1`，`.handle` 仍是 `1 / 1 / 2 / -1`（不受影响）。
侧栏拖拽手柄的 `left` 从 `cols.sidebar` 改为 `railWidth + cols.sidebar`（它现在骑在侧栏**右**边缘，即 rail + sidebar 处）。

### 4.2 新槽 `shell.rail`

```ts
'shell.rail': { kind: 'single'; scope: 'root'; owner: RailOwnerProps }
```

```ts
export interface RailOwnerProps {
  /** 只有解算真的给出 320 轨道时才为 true；请求被窄窗否决时报告 false。 */
  open: boolean
  /** 翻转 AppFrame 里的展开请求（竖条、收起按钮、Esc 共用）。 */
  onToggle: () => void
}
```

渲染方式与既有 `renderSlot` 一致：

```ts
const rail = useMemo(() => renderSlot('shell.rail', {
  open: railExpanded,
  onToggle: toggleRail,
}), [renderSlot, railExpanded, toggleRail])
...
{!drawer && <RailColumn expanded={railExpanded}>{rail}</RailColumn>}
```

- **状态归属**：`AppFrame` 持 `useState(false)` + `useCallback` 翻转（只存内存，不落 store、不持久化）。新挂载必然是竖条。
- **`open` 是解算后的状态**，不是原始请求：`railExpanded = cols.rail === RAIL_EXPANDED`。这样 320 面板绝不会被塞进 48px 轨道（否则组件会渲染一个被裁掉的面板）。
- **点击 / 键盘**：竖条、收起按钮都是原生 `<button>`（Tab 可达、Enter/Space 触发）；面板内 `Esc` 走组件 `onKeyDown`，同样调用 `onToggle`。
- **动画**：`trackToggle` 末尾追加 `:${railExpanded}`，rail 的 48↔320 与侧栏/右栏一样走 `data-animating` 的 `grid-template-columns` 过渡；窗口缩放引发的自动降级不缓动（既有规则）。

### 4.3 视觉

`.railCol` 与 `.sidebarCol` 同底色（`--dsw-specific-sidebar-fill`）+ 同一条 `border-l3` 分隔线；macOS 上把侧栏那条"蓝色氛围 + 半透明 tint"的规则同时挂到 `.railCol`（含深色与 Reduce Transparency 两个变体），让 rail 与侧栏在 vibrancy 上连成一片而不是出现色缝。抽屉态下 rail 不渲染，因此没有任何抽屉样式需要改。

---

## 5. 窄屏降级规则（明确写死）

1. **320 只在"sidebar + 已请求的右栏最小宽 + 中栏 400"都还放得下时成立**：

   ```text
   viewport - 320 - sidebar - (rightbar === 0 ? 0 : 300) >= 400
   ```

   不成立就降到 48。判定用的是**右栏是否被请求**（`rightbar !== 0`），所以：
   - 右栏关着时，1280/900 都能展开 320（中栏 680 / 524，均 ≥ 400）；
   - 右栏开着时，1280 自动降到 48，把空间让给右栏（右栏保 552、中栏保 400）。
2. **rail 的降级不影响 sidebar**：不会为了保住 rail 而去压缩侧栏，也不会改 sidebar 的 264–420 夹取与中点对齐。
3. **用户请求是"粘性"的**：在 770px 点展开 → 轨道仍是 48、`open` 报告 false；窗口拉宽到 1280 时该请求自动生效（与"侧栏保留宽屏偏好"同一套直觉）。单测 `keeps the 48px strip when the expanded rail would take the center floor` 覆盖。
4. 48 是**下限**：即使视口小到 20px，rail 仍是 48（与 sidebar 的 56 一样按"轨道已声明"处理，中栏按 0 夹底），不会出现负宽。

---

## 6. drawer 态：为什么整列不挂载

规则：**`drawer === true` 时 rail 轨道宽度 0、`<aside>` 不渲染、`slotCalls` 仍可读但组件不挂载。**

依据：

1. 抽屉态下侧栏本身是 `position:absolute` 的覆盖层（`grid-area:auto`、`z-index:71`），中栏已经让到整幅宽度；再给 rail 一条 48px 轨道，只会把**抽屉要盖住的那块中栏**缩小，没有任何可见收益。
2. 抽屉带遮罩（`z-index:70`）并会让中栏 `inert`；rail 若挂在遮罩下就是被盖住的死像素，若抬到遮罩上就会和模态语义打架（用户在抽屉里操作时还能点开能力面板）。
3. 抽屉断点是"窄到放不下并排列"的兜底；此时 rail 的展开面板本来也会被 §5 降级成 48，等于只剩一条无用的竖条。

macOS 侧栏收起态（`darwin && sidebarCollapsed`）：**保留 rail 为 48px 真实列**。依据：

1. 既有规则里收回的是 **sidebar 列**（`collapsedWidth = 0`，因为窗口 chrome 座位 `shell.leading` 已承接"重新打开/新建会话"两个控件，中栏要能贴到窗口左缘）；rail 不是那组 chrome 控件，它是产品自己的导航面，侧栏收起时把能力地图也一起藏掉，等于"越收起越找不到能力"。
2. 保留后 `shell.leading` 的挂载条件、`left: 88px` 与 `--dsh-frame-leading-clearance: 160px` **一行未改**；rail 只占 0–48px，红绿灯（x≈12–68）压在它上方，所以 rail 的内容从 `--dsh-frame-top-clearance`（macOS 48px）之下开始，控件不会落到红绿灯底下。
3. 代价如实记录：darwin 收起态下窗口最左缘现在是 rail（48px），会话区从 x=48 起；`shell.leading` 的两个控件仍在 88px，落在中栏内——与改动前相比只是中栏整体右移 48px。

---

## 7. `ui-capability-map`：改成受控组件

| 项 | 改前 | 改后 |
|---|---|---|
| 注册 | `shell.overlay`（list，id `capability-map.rail`） | **`shell.rail`**（single，`locale: capability-map`；single 槽不带 id/order） |
| 展开状态 | 组件 `useState(false)` | **框架传入 `open` / `onToggle`**，组件不自持 |
| 默认态 | 组件每次挂载收起 | 框架首帧 `false` → 仍是 48px 竖条 |
| `Esc` | `setOpen(false)` | `onToggle()`（框架收轨道） |
| 收起按钮 | `setOpen(false)` | `onToggle()` |
| 焦点 | 开→搜索框，关→竖条 | 不变（`wasOpen` 判据保留，`open` 由 props 驱动） |
| 搜索 / 阶段展开 | 组件内存态 | 不变 |
| 样式 | `position:absolute; left:8px` 浮层卡片、`bg-layer-1` + `prominent` 阴影、16px 圆角 | 填满轨道：`width/height:100%`，无定位、无阴影、无圆角，轨道底色由 `.railCol` 提供；顶部依旧让出 `--dsh-frame-top-clearance` |

只读约束原样保留：无 RPC、无命令、无 `<a>`/`data-command`，能力行仍是纯文本。

---

## 8. 门禁与测试（真实输出）

```text
$ node_modules/.bin/tsc -b tsconfig.client.json
TSC_EXIT=0

$ pnpm -C apps/desktop run build
✓ built in 602ms            # …welcome.js 229.22 kB
BUILD_EXIT=0

$ cd packages/client/ui-layout && ../../../node_modules/.bin/tsdown
ℹ [client] [CJS] lib/client.js      41.80 kB │ gzip: 11.21 kB
✔ Build complete in 73ms
TSDOWN_LAYOUT_EXIT=0

$ cd packages/client/ui-capability-map && ../../../node_modules/.bin/tsdown
ℹ [client] [CJS] lib/client.js      26.05 kB │ gzip: 7.07 kB
✔ Build complete in 22ms
TSDOWN_MAP_EXIT=0

$ node_modules/.bin/vitest run packages/client/ui-layout/tests packages/client/ui-capability-map/tests
 ✓ packages/client/ui-layout/tests/columns.client.spec.ts (23 tests)
 ✓ packages/client/ui-layout/tests/app-frame.client.spec.tsx (54 tests)
 ✓ packages/client/ui-layout/tests/apply.client.spec.ts (9 tests)
 ✓ packages/client/ui-layout/tests/service.client.spec.ts (6 tests)
 ✓ packages/client/ui-layout/tests/layout-store.client.spec.ts (36 tests)
 ✓ packages/client/ui-layout/tests/theme-presenter.client.spec.ts (7 tests)
 ✓ packages/client/ui-layout/tests/document-title.client.spec.tsx (4 tests)
 ✓ packages/client/ui-capability-map/tests/capability-map.client.spec.tsx (9 tests)
 Test Files  8 passed (8)
      Tests  148 passed (148)
TEST_EXIT=0
```

改动前同一命令是 **141 passed**；本次 +7（columns +6、capability-map +1，app-frame 条数不变但新增/替换了 rail 相关用例）。

仓库侧受影响门禁（逐条真跑）：

```text
$ node_modules/.bin/tsx scripts/gen-client-catalog.ts --check
gen-client-catalog: stale — …/slot-catalog.ts
$ node_modules/.bin/tsx scripts/gen-client-catalog.ts     # 重新生成（新增 shell.rail 条目、行号更新）
gen-client-catalog: wrote packages/extensions/cordis-client-runner/src/client/slot-catalog.ts.

$ node_modules/.bin/vitest run scripts/gen-client-catalog.spec.ts scripts/client-bundle-css.spec.ts \
    scripts/client-bundle-purity.spec.ts scripts/client-tsconfig.spec.ts scripts/check-workspace-constraints.spec.ts
 Test Files  5 passed (5)
      Tests  266 passed (266)                       # EXIT 0

$ tsx scripts/verify-translation-pairing.ts --write packages/client/ui-layout/README.md packages/client/ui-capability-map/README.md
$ tsx scripts/verify-translation-pairing.ts <同两个 pair>
verify-translation-pairing: 2 named pair(s) consistent; the corpus-wide check still runs in doc-sync.

$ tsx scripts/verify-package-readme-summaries.ts   → 426 English Summaries within 100 words   # EXIT 0
$ tsx scripts/verify-package-readme-model-experience.ts → 373 README(s) checked, all conform   # EXIT 0
$ tsx scripts/verify-package-readme-limitations.ts → 373 READMEs checked, all conform          # EXIT 0
$ vitest run scripts/doc-standard.spec.ts → 22 passed                                            # EXIT 0
```

### 覆盖到的行为（新增/调整的用例）

- **columns**：rail 作为第一轨道从 center 扣除；`rail=0` 与 `rail=48` 不同义；320 在 1000px 恰好成立、999px 降 48；1280 开右栏时 rail 让位（中栏 400、右栏 552）；折叠横屏中点不变（1920→960/640，951→475.5/427.5）；20px 视口 rail 仍 48。
- **app-frame**：默认 rail 轨道 48、owner props `{ open:false, onToggle }`；`onToggle` → 320 且 `data-animating=true`；770px 展开请求被否（轨道 48、`open=false`），拉宽到 1280 自动生效；抽屉态无 `[data-shell-rail]`、轨道 0、占用方不挂载；rail 不在 `[data-shell-overlay]` 里（证明不再是浮层）。
- **capability-map**：默认竖条；**受控**（点竖条只调 `onToggle`，父级不改 `open` 就不出面板）；展开 9 阶段与单阶段开合；`Esc` → `onToggle` 且焦点回竖条；搜索过滤 / 空态 / 清空；只读（无 link / `data-command` / 按钮数 = 9+1）；不泄内部字段；数据契约 43/91；注册落在 `shell.rail` 且 `shell.overlay`/`sidebar`/`shell.leading` 各 0 条。

---

## 9. 影响面（如实记录的行为变化）

1. **右栏打开阈值整体右移 48px**（rail 常驻的代价）：
   - 侧栏 420 时，右栏从"1119px 起关轨道"变为"1167px 起关"（1168 → 300，1167 → 0）；
   - 侧栏 420 时 1200px 下右栏宽从 380 变 332；1100px 下从 420 变 372。
2. **768px 处右栏不再可开**：`56 + 48 + 400 + 300 = 804`，所以 `canShow` 在 768 为 false、在 767（抽屉态，rail 不挂）为 true。这是"真实列 vs 浮层"的直接成本，已写进 app-frame 用例。
3. **窗口级**：`layout-before` 的三轨模板变成四轨，任何按 `gridTemplateColumns` 文本断言的测试都要跟着改（本仓只有 `app-frame.client.spec.tsx` 的 `tracks()` helper，已改为解析四轨并单独暴露 `railTrack()`）。
4. **`shell.overlay` 少了一个条目**：能力栏不再出现在浮层里；`shell.overlay` 的其它条目与 click-through 语义未动。

---

## 10. 改了哪些文件

| 文件 | 改动 |
|---|---|
| `packages/client/ui-layout/src/client/columns.ts` | `Columns.rail`、`RAIL_COLLAPSED/RAIL_EXPANDED`、`computeColumns` 增 `rail` 参数与先让步分支 |
| `packages/client/ui-layout/src/client/AppFrame.tsx` | 四轨模板、`RailColumn`、`shell.rail` 渲染与 `{open,onToggle}`、rail 状态、动画 key、侧栏手柄位置 |
| `packages/client/ui-layout/src/client/AppFrame.module.css` | `.railCol`；四列列位后移；darwin tint 规则扩到 rail |
| `packages/client/ui-layout/src/client/index.ts` | SlotMap `shell.rail` 文档、`RailOwnerProps` 导出、children 声明 |
| `packages/client/ui-capability-map/src/client/CapabilityMap.tsx` | 受控化（去掉 open 状态）、`Esc`/收起走 `onToggle`、文档 |
| `packages/client/ui-capability-map/src/client/CapabilityMap.module.css` | 去掉浮层定位/阴影/固定宽高，改为填满轨道 |
| `packages/client/ui-capability-map/src/client/index.ts` | 注册从 `shell.overlay` 改到 `shell.rail` |
| `packages/client/ui-layout/tests/columns.client.spec.ts` | `rail: 0` 基线 + 新增 6 条 rail 用例 |
| `packages/client/ui-layout/tests/app-frame.client.spec.tsx` | 四轨 helper、rail owner/track 用例、右栏门槛数值、抽屉态断言 |
| `packages/client/ui-capability-map/tests/capability-map.client.spec.tsx` | 受控 harness、受控用例、注册座位断言 |
| `packages/client/ui-layout/README.md` / `.zh.md` / `README.i18n.yaml` | 三栏→四栏、`shell.rail` 座位与让步顺序；重录配对哈希 |
| `packages/client/ui-capability-map/README.md` / `.zh.md` / `README.i18n.yaml` | 座位从 overlay 改为 rail、受控约定、限制项改写；重录配对哈希 |
| `packages/extensions/cordis-client-runner/src/client/slot-catalog.ts` | 生成物：新增 `shell.rail` 条目与新行号（`gen-client-catalog` 重跑） |

---

## 11. 未做 / 需要注意

1. **未打包**（按纪律）。真机要看这条列，打包前必须重建两个客户端产物：`pnpm -C packages/client/ui-layout run bundle`、`pnpm -C packages/client/ui-capability-map run bundle`（本次已本地跑通并更新 `lib/client.js`）。
2. **未做真机视觉验收**：rail/侧栏的分隔线、macOS 上 rail 与侧栏的 tint 连续性、320px 面板在 1280 下的观感，都只做了 token 与几何层核对；需要起应用看一眼（尤其 macOS 收起态最左缘现在多 48px）。
3. **rail 顶部 48px 带不是窗口拖动行**：macOS 上红绿灯压在该区域上方，列内容从 `--dsh-frame-top-clearance` 之下开始；没有把 rail 加进 `data-window-drag` 的拖动行清单（那是 ui-web/ui-theme 门禁的受管清单，本次不动）。
4. **窄窗"点了没反应"的窗口**：仅当 48 + sidebar + 400 > viewport（例如 770px）时，展开请求会被解算否决，竖条保持 48；请求留存，窗口变宽即生效。若产品希望此时给出提示，需要再加一个 owner 字段（本单只给 `{ open, onToggle }`）。
5. `pnpm install` 的 store 策略问题仍与上一单相同（未整装，未新增依赖）；本单**没有新增任何运行时依赖**（只用了既有的 React / cordis / slots）。
