# CHANGES · 能力栏与侧栏换位：`[rail][sidebar]` → `[sidebar][rail]`

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，基线 `ce7073d5` ＋ 既有 Daniel 补丁）
> 状态：**类型检查 / 桌面构建 / 客户端 bundle / `ui-layout` 140 条 / `ui-capability-map` 62 条全绿；未打包（按纪律）**
> 一句话：只把网格里两列的**位置**对调，宽度解算（`computeColumns`）一行未改，所有列宽数值前后完全一致；侧栏成为第一条轨道并承接窗口 chrome，rail 变成紧随其后的第二条轨道，收起仍是 48px。

---

## 1. 网格顺序

### 1.1 目标布局

```
换位前： [rail 48/320] [sidebar 280] [center] [rightbar]
换位后： [sidebar 280] [rail 48/320] [center] [rightbar]
```

### 1.2 `AppFrame.tsx` 模板（唯一一行几何代码）

```diff
         gridTemplateColumns:
-          `${railWidth}px ${cols.sidebar}px minmax(${cols.rightbar === 0 ? 0 : CENTER_MIN}px, 1fr) minmax(0px, ${rightbarMax}px)`,
+          `${cols.sidebar}px ${railWidth}px minmax(${cols.rightbar === 0 ? 0 : CENTER_MIN}px, 1fr) minmax(0px, ${rightbarMax}px)`,
```

（`AppFrame.tsx:346-347`。只换两个插值的先后，`computeColumns` 的返回值逐字未动。）

### 1.3 各列的 `grid-column`

`AppFrame.module.css`

| 列 | 换位前 `grid-column` | 换位后 `grid-column` |
|---|---|---|
| `.sidebarCol` | 2 | **1** |
| `.railCol` | 1 | **2** |
| `.centerCol` | 3 | 3（未动） |
| `.rightbarCol` | 4 | 4（未动） |
| `.bottomRow` | `1 / -1` | 未动 |
| `.handle` | `1 / 1 / 2 / -1` | 未动（绝对定位的横条，不占列） |

### 1.4 DOM 顺序也一起换了

网格位置由 `grid-column` 决定，但**阅读/ Tab 顺序由 DOM 决定**。所以 `AppFrame` 的子节点顺序同步改成「sidebar → rail」：

```diff
-      {!drawer && <RailColumn expanded={railExpanded}>{rail}</RailColumn>}
+      {/* DOM order matches the grid order (sidebar | rail): tab order follows the
+          visual left-to-right reading order, and the rail column keeps its
+          resolved track. */}
       <div className={css.sidebarCol} …>
         {sidebar}
       </div>
+      {!drawer && <RailColumn expanded={railExpanded}>{rail}</RailColumn>}
```

`bottomRow`、`overlayLayer`、`leadingSeat`、两个 `DragHandle` 的相对次序未变（都是绝对定位或整行元素）。

---

## 2. 侧栏拖拽手柄

手柄是 `left` 内联定位的 8px 命中条（`margin-left: -4px`，骑在列边界上）。

```diff
-      {/* … The capability rail sits before the sidebar, so the handle rides the
-          sidebar's right edge at rail + sidebar. */}
-      {!drawer && !centeredSidebar && !sidebarCollapsed && <DragHandle side="sidebar" left={railWidth + cols.sidebar} … />}
+      {/* The sidebar is the frame's first track, so its right edge is its own
+          width — the same border the capability rail starts from. The rail's
+          expansion therefore never moves this handle. */}
+      {!drawer && !centeredSidebar && !sidebarCollapsed && <DragHandle side="sidebar" left={cols.sidebar} … />}
```

（`AppFrame.tsx:392-395`。）

- 命中区仍是「侧栏右边缘 ±4px」，只是这条边缘从 `rail + sidebar` 变成了 `sidebar`；
- **rail 展开/收起时手柄不动**（rail 在侧栏右侧生长，侧栏右边缘不动）——换位前反而需要跟着 rail 宽度平移；
- 右栏手柄 `left = viewport - normal.rightbar` 与换位无关，一行未动（单测里 `1056px` / `728px` / `738px` 三条旧断言原样通过）。

---

## 3. 窗口 chrome 由 sidebar 承接

### 3.1 事实核对

窗口左缘的 chrome（macOS 红绿灯、窗口拖拽带）此前实际压在 rail 列上，但**拖拽带与顶部条本来就属于侧栏**：`ui-sidebar` 的 `.topStrip`（52px，`data-window-drag`）和 `.logoRow` 都在侧栏列内，`ui-theme` 的 chrome 行清单也把这两行记为侧栏的行（`packages/client/ui-theme/tests/app-region-styles.client.spec.ts` 的 `CHROME_ROWS`）。所以**换位后侧栏只是回到了它本来就按窗口左缘写的那套几何**：

- 侧栏在 x=0 起，`.topStrip` 覆盖 y 0–52，红绿灯（x 16–68、y 18–32）落在条内空白段，不影响右侧的收起/展开按钮（右对齐）；
- `.topStrip` 向右的 4px 微调、`.logoRow` 的 −12px 上提等规则全部沿用，一行未改；
- 因此 `ui-sidebar`、`ui-theme` 的 chrome 规则**零改动**，`app-region-styles` 门禁 5 条照旧全绿。

### 3.2 rail 的内容上边距（本次唯一需要跟着调的地方）

rail 的占用方（`ui-capability-map`，不许改）自己按继承来的变量留白：

```css
/* ui-capability-map/src/client/CapabilityMap.module.css:22 */
.dock { padding: calc(var(--dsh-frame-top-clearance, 0px) + 6px) 0 8px; }
```

`--dsh-frame-top-clearance` 在 `html[data-platform='darwin']` 上是 48px。换位后 rail 不再被红绿灯压住，所以**在 rail 列内部把这个变量归零**（不改占用方一行代码）：

```css
/* AppFrame.module.css:75-95 */
.railCol {
  grid-column: 2;
  …
  /* The window chrome band belongs to the sidebar now, so the rail's own
     content needs no top clearance: the dock that reads this variable pads
     just 6px. The one exception is below. */
  --dsh-frame-top-clearance: 0px;
}

/* macOS collapse leaves the sidebar column at zero width, so the rail becomes
   the frame's leftmost column and the traffic lights hang over x 0–48 again.
   It re-inherits the platform clearance there, exactly as it did when it was
   the first track, so no rail control lands under the lights. (The Windows
   caption row needs no such rule: it lives outside the frame's content box,
   above every column.) */
:global([data-platform='darwin']) .frame[data-sidebar-collapsed] .railCol {
  --dsh-frame-top-clearance: 48px;
}
```

效果：侧栏展开时，rail 内容从 6px 起（与侧栏顶部条并排），不再白留 54px；macOS 侧栏整列隐藏时回到 48+6px（见第 4 节）。

**Windows 副作用（有意）**：`html[data-windows-titlebar]` 上该变量等于标题行高，而 `.frame` 已经用 `padding-top` 让出标题行。换位后 rail 归零，等于**去掉了原先的双重留白**（rail 内容此前被标题行高垫了两次）。这不是新增的视觉缺陷，而是顺手修掉的一处重复留白；如需保留原样，把第 3.2 节第一条规则的 `--dsh-frame-top-clearance` 改成 `var(--dsh-frame-top-clearance)` 的旧行为即可回退。

---

## 4. macOS 侧栏收起态：rail 在哪、和红绿灯什么关系

先看解算：`AppFrame` 里

```ts
const collapsedWidth = drawer || darwin || windowsTitlebar ? 0 : SIDEBAR_COLLAPSED
```

即 **macOS 上侧栏收起 = 整列宽 0**（不是 56px 控制栏）。于是：

| 状态 | 侧栏轨道 | rail 轨道 | rail 的位置 | 红绿灯和 rail 的关系 |
|---|---|---|---|---|
| 侧栏展开 | 280 | 48/320 | x=280 起 | 红绿灯全在侧栏列上方，**不压 rail** |
| 侧栏收起（macOS） | **0** | 48/320 | **x=0 起（整列最左）** | 与换位前**完全一样**：列背景在灯下方，但 rail 内容按 48+6px 起算，控件不会被灯压住 |

也就是说：换位**不会**让 rail 多出一次"跑到窗口左缘"的机会——它原本就一直在窗口左缘（换位前 rail 是第一条轨道，侧栏收起时侧栏宽 0 也在右侧）。唯一变化是「侧栏展开」这一种状态，rail 右移到侧栏右侧、彻底脱离红绿灯区域。

对应的保底样式就是 3.2 节的 `[data-sidebar-collapsed]` 覆盖：它保证 **rail 一旦成为最左列，就重新拿到 48px 顶部安全区**；侧栏在时该安全区归侧栏所有。

另外两处与左缘相关的既有机制未受影响：

- `shell.leading`（macOS 收起时的重开控件）仍挂在 `left: 88px`，落在中栏左侧而非 rail 上；`--dsh-frame-leading-clearance: 160px` 也未改；
- 换位后侧栏宽 0，中栏左边界到 x=48（rail 右缘），`.centerCol` 的 darwin 左边框仍由 `[data-sidebar-collapsed] .centerCol { border-left: none }` 关掉，不会凭空多一条缝。

---

## 5. drawer 态（<768）

`railPreference = drawer ? 0 : …`，`drawer` 时 **rail 列根本不渲染**（`{!drawer && <RailColumn …/>}`）。换位后：

- 抽屉里的侧栏仍是 `position: absolute; inset: 0 auto 0 0`（从窗口左缘滑入），**从侧栏列自身的 CSS 出发**，与它在网格里排第几无关；
- `drawerMask` 仍是帧内绝对定位的遮罩（z 70），`inert` 仍加在 `CenterColumn` / `RightbarColumn` / `bottomRow` / `leadingSeat` 上，打开抽屉时这些区域照旧不可聚焦；
- 换位只改了「同层两个列的绘制顺序」，遮罩（z 70）与抽屉（z 71）的层级都在列之上，未动。

单测覆盖：`sidebar drawer` 三条（遮罩点击、`inert`、768 边界）原样通过；新增的 `railTrack = 0` 断言见 §8。

---

## 6. 动画 / 过渡

### 6.1 没有「逐列过渡」这回事

`data-animating` 期间只挂了一条 CSS：

```css
.frame[data-animating] { transition: grid-template-columns var(--ds-transition-duration-slow) var(--ds-ease-in-out); }
```

四个轨道是**同一个属性**，同一时长同一条曲线一起走——不存在"先动 rail 再动 sidebar"的排序，因此换位不会产生"展开时跳一下"。真正会跳的两个点已经由既有机制挡住：

1. `data-animating` 在子节点布局副作用测量新宽度**之前**就置位（`animateTracks` 用 `useLayoutEffect` 之前的渲染值算）；
2. 手柄的 `left` 与轨道同曲线（`.frame[data-animating] .handle { transition: left … }`），且**换位后 rail 展开不会改动手柄的 `left`**（它锚在侧栏右缘），从根上消除了"手柄先跳、轨道后到"的可能。

### 6.2 `trackToggle` 的字段顺序

`trackToggle` 只是「离散状态指纹」，字符串内容不参与布局；为了让读代码的人和列顺序一致，字段按**新列序**重排（sidebar → rail → rightbar）：

```diff
-  const trackToggle = `${sidebarCollapsed}:${layoutInfo.rightbarTrack}:${centeredSidebar}:${railExpanded}`
+  // Fingerprint of the discrete track states, read left to right in the frame's
+  // own column order (sidebar | rail | rightbar). All four tracks ride one
+  // `grid-template-columns` transition, so this only has to detect *that* a
+  // discrete state flipped — not sequence per-column easing.
+  const trackToggle = `${sidebarCollapsed}:${railExpanded}:${layoutInfo.rightbarTrack}:${centeredSidebar}`
```

（`AppFrame.tsx:259-263`。语义无变化：首值仍是挂载时的值，挂载不会误触发动画；视口变化仍走"瞬时落位"分支。）

---

## 7. `computeColumns` 未改（要求 7）

`columns.ts` **只改了一条注释**（"48px strip left of the sidebar" → "between the sidebar and the centre"），函数签名、夹取、让步顺序（rail → rightbar → center）一行未动。原因是宽度解算与列的位置无关：它只回答"每条轨道多宽"，不回答"谁在左"。

换位前后同一入参的返回值逐字相同，这也正是下一节"三视口列宽数值一致"的根据。

---

## 8. 单测：改了哪几条、为什么

`packages/client/ui-layout/tests/app-frame.client.spec.tsx`：**139 → 140 条**（新增 1 条），全部通过。改动分三类：

### 8.1 读模板的 helper（顺序语义）——3 处

| 位置 | 改动 | 为什么 |
|---|---|---|
| `trackList()` | 注释由 `[rail, sidebar, rightbar]` 改为 `[sidebar, rail, rightbar]`（返回值顺序同步） | 模板第一个 px 现在是侧栏宽 |
| `tracks()` | 解构 `const [rail, sidebar, rightbar]` → `const [sidebar, rail, rightbar]`；rail 取值仍校验 0/48/320 | 保持 `tracks()` 对外仍是 `[sidebar, rightbar]`，**所以下面所有数值断言一条都不用改** |
| `railTrack()` | `trackList(frame)[0]` → `[1]` | rail 现在是第二条轨道 |

> 关键点：**旧断言里的数字一个都没动**（280/56/420/400/864/365/306/1056/728…），因为宽度本来就没变。改的只是"从模板的第几个 px 读"。

### 8.2 既有用例（补断言，不改原断言）——3 条

| 用例 | 补充 | 为什么 |
|---|---|---|
| `keeps the closed sidebar mounted at its 56px rail without a handle` | 加 `expect(trackList(frame)).toEqual([56, 48, 0])` | 固定"非 macOS 收起态 = 侧栏 56px 在最左，rail 48px 紧随其后" |
| `mounts the shell.leading seat only while the darwin collapse hides the column` | 收起后加 `expect(railTrack(frame)).toBe(48)` | 固定 macOS 收起态 rail 仍在（且成为最左列），对应 §4 的样式前提 |
| `renders the rail as a real first track …` | 只改标题为 `… real second track …`，断言未动 | 标题里的 "first" 已经不成立 |

### 8.3 新增用例——1 条

`keeps the sidebar as the first track and the rail as the second, wherever the solve lands`

断言三件事：

1. `trackList(frame) === [280, 48, 0]`，且模板整串等于 `280px 48px minmax(0px, 1fr) minmax(0px, 0px)`（列顺序）；
2. `sidebar-content` 在 DOM 里先于 `shell.rail-content`（Tab/阅读顺序）；
3. 侧栏手柄 `left === '280px'`；rail 展开到 320 后仍 `280px`（不被 rail 推走）；把侧栏拖到 360 后 `trackList === [360, 320, 0]` 且 `left === '360px'`。

`ui-capability-map`：**62 条一条未改、全绿**（该包源码零改动，见 §10 第 3 条）。

---

## 9. 验证证据（真实输出）

### 9.1 三道构建门禁

```text
$ node_modules/.bin/tsc -b tsconfig.client.json
TSC_EXIT=0                                    # 无输出即无错误

$ pnpm -C packages/client/ui-layout run bundle
✔ [@deepseek-ai/dsh-client-ui-layout/client] [CJS] lib/client.js  42.14 kB │ gzip: 11.31 kB
✔ [@deepseek-ai/dsh-client-ui-layout/client] Build complete in 61ms
BUNDLE_EXIT=0

$ pnpm -C apps/desktop run build
ℹ [ESM] lib/main.js  874.71 kB │ gzip: 221.18 kB
✓ built in 502ms                              # welcome 资源
DESKTOP_EXIT=0
```

### 9.2 单测

```text
$ vitest run packages/client/ui-layout/tests
 ✓ columns.client.spec.ts (23)  ✓ service.client.spec.ts (6)  ✓ layout-store.client.spec.ts (36)
 ✓ theme-presenter.client.spec.ts (7)  ✓ document-title.client.spec.tsx (4)
 ✓ app-frame.client.spec.tsx (55)  ✓ apply.client.spec.ts (9)
 Test Files  7 passed (7)
      Tests  140 passed (140)

$ vitest run packages/client/ui-capability-map/tests
 ✓ trace (17)  ✓ trace-filter (11)  ✓ capability-map (16)  ✓ guide (18)
 Test Files  4 passed (4)
      Tests  62 passed (62)
```

（换位前基线同样是 `ui-layout 139 passed` / `ui-capability-map 62 passed`，可对比。）

### 9.3 三视口列宽：数值一致，只是顺序变了

测法：临时用例渲染真实 `AppFrame` 并打印 `frame.style.gridTemplateColumns`（jsdom 不做布局，读的就是浏览器会拿到的那串模板），三视口 × rail 两态；先在**换位后**跑一遍，再把模板那一行临时改回 rail 在前跑一遍，然后恢复。测完临时用例已删除。

| 视口 | rail 状态 | 换位前模板（rail 在前） | 换位后模板（sidebar 在前） | rail | sidebar | center | rightbar |
|---|---|---|---|---|---|---|---|
| 1280 | 收起 | `48px 280px minmax(0px, 1fr) minmax(0px, 0px)` | `280px 48px …` | 48 | 280 | 952 | 0 |
| 1280 | 展开 | `320px 280px …` | `280px 320px …` | 320 | 280 | 680 | 0 |
| 900 | 收起 | `48px 56px …` | `56px 48px …` | 48 | 56 | 796 | 0 |
| 900 | 展开 | `320px 56px …` | `56px 320px …` | 320 | 56 | 524 | 0 |
| 700 | 收起 | `0px 0px minmax(0px, 1fr) minmax(0px, 0px)` | `0px 0px …` | 0 | 0 | 700 | 0 |
| 700 | 展开 | `0px 0px …`（抽屉态无 rail 列） | `0px 0px …` | 0 | 0 | 700 | 0 |

`center = viewport − rail − sidebar − rightbar`，逐行相加都等于视口宽。**每个数字前后完全相同，只有两个 px 的先后对调。**

### 9.4 侧栏手柄的新 left 计算（代码）

```tsx
// AppFrame.tsx:392-395
{!drawer && !centeredSidebar && !sidebarCollapsed && (
  <DragHandle side="sidebar" left={cols.sidebar} onStart={onSidebarStart} onDrag={onSidebarDrag} onEnd={onDragEnd} />
)}
```

`cols.sidebar` 是解算后的侧栏宽（264–420 夹取 / 折叠横屏取帧中点）。1280 视口默认态：`left = 280`（rail 展开后仍是 280，因为 rail 在它右边生长）；拖到 360 后 `left = 360`。

### 9.5 其它门禁（顺带核过）

```text
$ tsx scripts/gen-client-catalog.ts --check
gen-client-catalog: …/slot-catalog.ts is up to date.        # 改了 shell.rail 的槽位说明，已重新生成
$ tsx scripts/verify-translation-pairing.ts packages/client/ui-layout/README.md
verify-translation-pairing: 1 named pair(s) consistent.
$ vitest run packages/client/ui-theme/tests/app-region-styles.client.spec.ts
 Tests  5 passed (5)                                        # chrome 行归属未变
```

---

## 10. 未做 / 明确说明

1. **未打包**（按纪律）。`apps/desktop` 的 web 资源与 DMG 均未重建。
2. **`ui-capability-map` 源码零改动**（要求：只拿 `open`/`onToggle`）。代价是它自己的注释/README 里仍写着 "left of the sidebar"——与新版面不符但**不影响行为**；该包 62 条单测未动、全绿。若允许动文档，建议后续把 `src/client/index.ts:6` 与 `README(.zh).md` 的这句改成"between the sidebar and the centre"。
3. **`ui-layout` 自己的文档/槽位说明已同步**：`slot` 契约（`src/client/index.ts`）、`README.md` / `README.zh.md`（并重录了 `README.i18n.yaml` 的分节哈希）、生成的 `slot-catalog.ts`。
4. **未跑官方 e2e / 截图基线**：视觉验收需要在真实窗口里看（三视口 + macOS 展开/收起 + 抽屉），本次只到"构建 + 单测 + 模板串"这一层。
5. **补丁已落工作区**：同目录 `RAIL-SWAP.patch`（9 个文件：`ui-layout` 8 个 + 生成的 `slot-catalog.ts`），`git apply --check --reverse` 通过，可在 `/tmp` 被清空后用它在同一基线上重放。

---

## 11. 改动文件清单

| 文件 | 改动 |
|---|---|
| `packages/client/ui-layout/src/client/AppFrame.tsx` | 模板顺序、DOM 顺序、侧栏手柄 `left`、`trackToggle` 字段顺序、注释 |
| `packages/client/ui-layout/src/client/AppFrame.module.css` | `.sidebarCol`=1 / `.railCol`=2、rail 顶部安全区归零 + macOS 收起态恢复 48px |
| `packages/client/ui-layout/src/client/columns.ts` | 仅注释（"48px strip left of the sidebar"） |
| `packages/client/ui-layout/src/client/index.ts` | `shell.rail` 槽位说明（"left of the sidebar" → "between the sidebar and the centre"） |
| `packages/client/ui-layout/tests/app-frame.client.spec.tsx` | 3 个 helper 顺序、3 条既有用例补断言、1 条新用例 |
| `packages/client/ui-layout/README.md` / `README.zh.md` / `README.i18n.yaml` | 段落顺序描述 + 配对哈希 |
| `packages/extensions/cordis-client-runner/src/client/slot-catalog.ts` | 生成物随槽位说明刷新 |
