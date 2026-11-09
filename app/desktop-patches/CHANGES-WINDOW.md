# 变更记录：主窗口默认尺寸 + 记忆上次窗口大小

范围：`apps/desktop`（Daniel Bot 桌面端 Electron 壳）。只影响**主工作区窗口**；登录窗、欢迎窗、更新窗、强制更新窗的尺寸与位置不变。

## 1. 默认尺寸

| 项 | 旧值 | 新值 |
|---|---|---|
| `width` | 1280 | **1360** |
| `height` | 820 | **780** |
| `minWidth` | 520 | 520（不变） |
| `minHeight` | 600 | 600（不变） |

首次启动（`settings.json` 里没有 `window` 记录，或记录不可用）时使用 1360×780，且不传 `x`/`y`，由平台居中。

常量集中在 `apps/desktop/src/window-state.ts`：

```ts
export const DEFAULT_MAIN_WINDOW_SIZE = { width: 1360, height: 780 } as const
export const MIN_MAIN_WINDOW_SIZE = { width: 520, height: 600 } as const
```

`createWindow()` 的 `minWidth`/`minHeight` 直接引用 `MIN_MAIN_WINDOW_SIZE`，夹紧规则和窗口本身不会各写一套数字。

## 2. 持久化结构

`userData/desktop/settings.json` 顶层新增可选字段（与已有的 `updates` 并列）：

```json
{
  "updates": { "allowTestAuthPopupWindow": false },
  "window": { "width": 1360, "height": 780, "x": 120, "y": 80, "maximized": false }
}
```

- `width`/`height`：正整数（CSS px）。
- `x`/`y`：整屏坐标，可正可负（副屏在主屏左侧时为负）；**必须成对出现**，缺一个就整条丢弃。
- `maximized`：布尔，必填。
- 首次启动的默认文档仍是 `{"updates":{...}}`，不会因为新增字段就提前写 `window`。

## 3. 恢复与夹紧规则

启动时读取一次设置，按下列顺序解析（`resolveWindowGeometry`，纯函数）：

1. **无记录** → 1360×780，无位置，`maximized: false`。
2. **尺寸夹紧**：`width ∈ [520, 目标工作区宽]`、`height ∈ [600, 目标工作区高]`。
   - 「目标工作区」= 保存位置所属的那块显示器（矩形相交面积最大者）；位置不可用时 = 主显示器 `screen.getPrimaryDisplay().workArea`。
   - 下限优先：即使某块工作区比 520×600 还小，也不会把窗口压到最小尺寸以下。
3. **位置保留条件**：位置仍在某块显示器可见范围内（判定见 §4），否则**丢弃 `x`/`y`**，交给平台在主显示器居中。
4. **`maximized`**：原样保留，由 `restoreMaximizedState()` 在窗口构造后立即应用（见 §6）。
5. **记录损坏/类型不对**（字符串数字、小数、缺 `maximized`、只有 `x` 没有 `y` 等）→ `parseWindowPlacement()` 返回 `undefined`，整条 `window` 被忽略，回落到默认尺寸；**不影响文件里的其它字段**，也不重写文件。

关键代码（`apps/desktop/src/window-state.ts`）：

```ts
function clampDimension(value: number, min: number, max: number): number {
  // `Math.max(min, max)` keeps the floor even when a display is smaller than the minimum.
  return Math.min(Math.max(value, min), Math.max(min, max))
}

const target = positionVisible && savedRect !== undefined
  ? workAreaOwning(savedRect, primary, areas)   // 保存位置所在的显示器
  : primary                                     // 位置不可用 → 主显示器
const width = clampDimension(savedWidth, MIN_MAIN_WINDOW_SIZE.width, target.width)
const height = clampDimension(savedHeight, MIN_MAIN_WINDOW_SIZE.height, target.height)
const positioned = savedRect !== undefined && isWindowPositionVisible({ ...savedRect, width, height }, areas)
return { width, height, ...(positioned ? { x: position.x, y: position.y } : {}), maximized }
```

## 4. 「屏幕外位置」的判定

用 `screen.getAllDisplays()` 取每一块屏幕的 **`workArea`**（已扣掉菜单栏/Dock/任务栏），把保存的窗口矩形与它们逐一做**矩形相交**，并要求相交区域的宽高都达到阈值：

```ts
const TITLE_BAR_STRIP_HEIGHT = 48   // 窗口顶部可拖动条的高度
const MIN_VISIBLE_WIDTH = 120       // 至少露出 120px 宽
const MIN_VISIBLE_HEIGHT = 24       // 至少露出 24px 高

export function isWindowPositionVisible(rect, workAreas): boolean {
  const strip = { x: rect.x, y: rect.y, width: rect.width, height: TITLE_BAR_STRIP_HEIGHT }
  return workAreas.some((area) => {
    const visible = overlap(strip, area)   // width/height 为相交尺寸，负值表示不相交
    return visible.width >= MIN_VISIBLE_WIDTH && visible.height >= MIN_VISIBLE_HEIGHT
  })
}
```

判定的是**标题栏条带**而不是整个窗口：

- 只测整个窗口会漏掉「窗口主体还压在某块屏幕上、标题栏却在屏幕上方」的情况 —— 这种窗口能看见但拖不回来；
- 条带 48px 高、要求至少露出 120×24px，既能接住「外接屏拔掉后坐标落在 5000,4000」这种彻底离屏，也不会误杀「窗口压在屏幕边缘/跨越两块屏」的正常摆放；
- 用 `workArea` 而不是 `bounds`，避免把窗口恢复到菜单栏或 Dock 底下；
- 允许负坐标（副屏在主屏左侧），因此不能用「x≥0 且 y≥0」这种近似判断。

## 5. 写入时机

| 事件 | 行为 |
|---|---|
| `resize` / `move` | 去抖 **500ms**（`WINDOW_PLACEMENT_DELAY_MS`）后写一次；连续拖动只写最后一次 |
| `maximize` / `unmaximize` | **立即**写 |
| `close` | 立即写（macOS/Windows 上关窗只是隐藏，窗口对象还在，几何仍有效） |
| `app will-quit` | 再写一次（兜住仍在去抖中的最后一次 resize/move） |

写入值：

- 尺寸/位置取 `window.getNormalBounds()` —— 最大化时的「还原尺寸」，而不是当前铺满屏幕的尺寸；
- `maximized` 取 `window.isMaximized()`；
- 窗口已销毁 / 最小化 / 全屏时**跳过本次写入**，避免用图标尺寸或屏幕尺寸覆盖掉用户真正选择过的几何。

去抖器是纯逻辑（`createPlacementWriter`），`read`/`write` 通过参数注入，单测用假定时器验证「连续 5 次 resize 只写 1 次」。

## 6. `maximized` 与 restore 的顺序

恢复顺序固定为：**先用保存的普通尺寸构造窗口 → 再 `window.maximize()`**。

```ts
const geometry = resolveWindowGeometry(desktopSettings.window, primaryWorkArea, workAreas)
const window = createWindow(appPreload, false, true, geometry) // width/height = 普通尺寸
restoreMaximizedState(window, geometry)                        // maximized 时调用 maximize()
```

原因：

1. **不能让最大化尺寸成为「还原尺寸」**。如果先把窗口按最大化后的屏幕尺寸建出来再 `maximize()`，用户点「还原」时窗口会退回一个接近全屏的大小，而不是他上次退出时的窗口大小。用普通尺寸建窗，Electron 会把这份 bounds 记成 unmaximize 目标。
2. **不用 `restore()`**。`restore()` 是 `minimize()` 的反操作（把最小化窗口还原），对新建且未最小化的窗口没有意义；用它替代 `maximize()` 会得到一个普通窗口。
3. **在 `show()` 之前最大化**。窗口创建时 `show: false`，`maximize()` 发生在首次显示之前，因此第一帧就是最大化状态，不会出现「先弹小窗、再跳到最大化」的闪动。

## 7. 兼容策略

- **旧文件**：没有 `window` 字段 → 按默认尺寸，不报错、不警告、不重写文件（读路径只读不写）。
- **坏字段**：`window` 存在但类型/取值不对 → 只丢弃该字段并 `console.warn` 一条，`updates` 等其它字段照常生效。
- **坏 JSON**：整份文档解析失败 → 回落默认值（与既有 `updates` 的处理一致），不崩、不重写。
- **写文件**：先重新读盘上文档（保留未知字段与 `updates`），再写临时文件 `settings.json.<pid>.tmp`，最后 `rename` 覆盖；中途失败只 `console.warn`，并清理临时文件，绝不影响启动。写失败时旧文件保持原样（单测用 `renameSync` 抛 `EACCES` 验证）。
- 磁盘上的文档若损坏到一个对象都解析不出来，保存时会以「默认文档 + 本次几何」重建，并记一条警告（否则几何永远存不下来）。
- 只对主窗口生效：`createWindow()` 的 `geometry` 参数只有 `createMainWindow()` 传入；登录窗（`daniel-login.ts`）、欢迎窗（`welcome-window.ts`）、强制更新窗（`mandatory-update-window.ts`）、测试授权窗（`policy-test-auth.ts`）各自 `new BrowserWindow({...})`，不读这份记录。

## 8. 代码落点

| 文件 | 改动 |
|---|---|
| `apps/desktop/src/window-state.ts` | **新增**：默认/最小尺寸常量、`parseWindowPlacement`、`isWindowPositionVisible`、`resolveWindowGeometry`、`restoreMaximizedState`、`readWindowPlacement`、`createPlacementWriter` |
| `apps/desktop/src/settings.ts` | `DesktopSettings.window?`；读取时校验并容忍坏值；新增 `saveDesktopWindowPlacement()`（原子写、失败仅告警） |
| `apps/desktop/src/main.ts` | `createWindow()` 接收 `geometry`；`createMainWindow()` 读设置→算几何→建窗→`maximize()`→挂 `resize/move/maximize/unmaximize/close/closed`；`will-quit` 兜底写 |
| `apps/desktop/tests/window-state.spec.ts` | **新增** 32 条用例（含参数化） |
| `apps/desktop/tests/settings.spec.ts` | 未改动，既有 18 条继续通过 |
| `apps/desktop/tests/main-startup.spec.ts` | 测试替身补齐 Electron 真实 API：`screen`、`getNormalBounds()`、`isMaximized()`、`maximize()` |

## 9. 测试与构建证据

```console
$ export PATH="<node24>:$PATH"
$ pnpm -C apps/desktop run build
$ echo $?
0

$ ./node_modules/.bin/vitest run apps/desktop/tests/window-state.spec.ts apps/desktop/tests/settings.spec.ts
 ✓ |thread-safe| apps/desktop/tests/window-state.spec.ts (32 tests) 14ms
 ✓ |thread-safe| apps/desktop/tests/settings.spec.ts (18 tests) 19ms
 Test Files  2 passed (2)
      Tests  50 passed (50)

$ ./node_modules/.bin/tsc -b tsconfig.client.json
$ echo $?
0
```

`tsc -b`（宿主工程，随 `build` 一起执行）与 `tsc -b tsconfig.client.json` 均为 0；本次未触及 client 代码，client 工程仅作回归确认。

新增用例覆盖（对应需求 8 条）：

1. 无记录 → 1360×780、无位置、未最大化
2. 有合法记录 → 尺寸/位置/最大化原样使用
3. 宽高超工作区 → 夹到工作区；过小 → 抬到 520×600
4. 位置在屏幕外 → 丢弃位置（且副屏负坐标位置不被误杀）
5. `maximized: true` → 调用 `maximize()`；false → 不调用
6. 旧设置文件（无 `window`）→ 不报错、其它字段保留、文件不被重写
7. 损坏 JSON → 回落默认且不抛；`window` 字段坏 → 只丢该字段
8. 去抖：连续 5 次 resize 只写 1 次；`writeNow()` 立即写并取消挂起的去抖；`dispose()` 后不再写

另：`apps/desktop/tests/main-startup.spec.ts` 共 151 条，本次 **147 通过 / 4 失败**；这 4 条（`raises the first workspace only for a Windows installer restart`）在**本次改动前的同一份代码**上失败结果完全一致，属既有问题（该分支在 Daniel 定制里已固定 `raiseAfterUpdate = false`），与窗口尺寸无关。`welcome-startup.spec.ts` 同样在改动前后一致失败（该定制已停用欢迎流程）。

## 10. 已知限制

- `getNormalBounds()` 在部分 Linux 桌面环境下与 `getBounds()` 等价，最大化状态下的「还原尺寸」可能不准；macOS/Windows 正常。
- 全屏（`isFullScreen()`）期间不写盘，退出全屏并触发 resize 后会补写。
- 显示器热插拔只在启动时判定；运行中拔屏仍可能导致窗口离屏，下次重启会按 §4 重置到主屏居中。
- 去抖固定 500ms，没有做成可配置项（用户未要求）。
