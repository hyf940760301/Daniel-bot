# CHANGES · S6.1 全局视觉换皮（DSH 视觉 → Daniel 视觉）

> 范围：`packages/client/ui-theme/src/styles/**`（token 层）、`packages/client/ui-layout/src/client/AppFrame.module.css`（1 处结构性蓝色 wash）、
> `packages/client/ui-settings-account/src/client/DesktopOnboarding.module.css`（前序 WIP 遗留的样式契约违规，非本次换皮引入）
> 工作树：`/tmp/dsh-build/dsh-src`　基线 commit：`master`（工作树已有前序 Daniel WIP 改动）
> 状态：**类型检查 / 桌面构建 / 指定两套单测全绿**；未打包（按纪律）。
> 交付形态：**改 token 值**，不逐个组件写覆盖样式；组件 CSS 只动 2 个文件，原因见 §4。

---

## 0. 一句话

主界面（右栏对话区 / 左侧边栏 / 设置页）的颜色全部来自 `design-platform.css` 的约 400 个 `--dsw-*` token，
所以这次**只换色板与别名**：DeepSeek 蓝系 → Daniel 蓝系（#2B7FB0 / 亮步 #67C3F0），画布浅 `#F9FAFC` / 深 `#0F1115`，
正文浅 `#191C20` / 深 `#F9FAFB`，字体换 `Inter` 优先栈，控件圆角 8→10px（其余档位本就合规），阴影换成 Daniel 的冷黑双段式。
**布局、间距、组件结构、图标、交互一行未动**（§5 有清单）。

---

## 1. 改法：为什么是 token 层

把整条链路拆开看，颜色只有三处源头：

```
--dsw-static-*（色板）  →  --dsw-alias-*（语义别名）  →  组件 CSS（只写 var()）
```

因此只要改**色板**和**少量语义别名**，右栏、侧栏、设置页、对话框、Toast、滚动条、Markdown、代码块会一起变色，
不需要在 200+ 个 `*.module.css` 里写 `!important` 覆盖。这次实际改到的组件 CSS 只有 2 个文件（§4）。

两条设计原则：

1. **同一语义在深浅两主题下都必须是 Daniel 蓝**：所以两套色板块里的 `--dsw-static-deepseek-*` / `--dsw-static-blue-*` 同步改，
   而不是只改浅色。
2. **能从色板派生的绝不写死别名**：例如 `--dsw-alias-link`（浅 deepseek-500 / 深 deepseek-400）、
   `--dsw-alias-state-business-primary`（focus ring）、`--dsw-alias-bg-document-selection`、`--dsw-specific-sidebar-nav-item-active-accent`
   **一行没改**，色板换完后它们自动变成 Daniel 蓝 —— 这是 token 层改法的收益，也是本文件里"看起来漏了"的地方。

---

## 2. 映射表（token → 旧值 → 新值 → 为什么）

### 2.1 品牌蓝：DeepSeek 蓝 → Daniel 蓝

| # | token | 旧值 | 新值 | 为什么 |
|---|---|---|---|---|
| 1 | `--dsw-static-deepseek-500` | `rgb(65, 118, 230)` #4176E6 | `rgb(43, 127, 176)` **#2B7FB0** | Daniel 主色。链接 / 品牌 / 按钮 / 选中态 / focus ring 全部从这一级派生，改这里等于一次换掉整条品牌链路 |
| 2 | `--dsw-static-deepseek-400` | `rgb(122, 170, 255)` #7AAAFF | `rgb(103, 195, 240)` **#67C3F0** | Daniel 亮色 / 悬停步；也是深色主题的链接色与 focus ring |
| 3 | `--dsw-static-deepseek-450` | `rgb(86, 134, 254)` #5686FE | `rgb(74, 159, 204)` #4A9FCC | 深色主题的品牌填充档（比 500 亮一档，深色底上才够分离） |
| 4 | `--dsw-static-deepseek-600` | `rgb(72, 104, 178)` #4868B2 | `rgb(34, 102, 143)` #22668F | 按下 / 悬停加深步；浅底白字需要这一档才够对比度 |
| 5 | `--dsw-static-deepseek-300` | `rgb(183, 200, 254)` #B7C8FE | `rgb(168, 219, 244)` #A8DBF4 | 浅蓝描边 / 微光 / 深色 shimmer 混色 |
| 6 | `--dsw-static-deepseek-200` | `rgb(211, 226, 255)` #D3E2FF | `rgb(214, 237, 250)` #D6EDFA | 气泡高亮、选中底 |
| 7 | `--dsw-static-deepseek-100` | `rgb(228, 237, 253)` #E4EDFD | `rgb(231, 244, 252)` #E7F4FC | 侧栏选中 accent、business tertiary、气泡底 |
| 8 | `--dsw-static-deepseek-50` | `rgb(237, 243, 254)` #EDF3FE | `rgb(242, 249, 253)` #F2F9FD | 最浅蓝底（侧栏选中行、引用底） |
| 9 | `--dsw-static-deepseek-800` | `rgb(52, 65, 91)` #34415B | `rgb(27, 79, 110)` #1B4F6E | 深色主题 business tertiary / 侧栏选中 accent |
| 10 | `--dsw-static-deepseek-900` | `rgb(40, 49, 66)` #283142 | `rgb(18, 58, 82)` #123A52 | 深色主题侧栏选中行底色 |
| 11 | `--dsw-static-deepseek-700-delete` | `rgb(47, 76, 143)` #2F4C8F | `rgb(29, 88, 118)` #1D5876 | 同一族里的旧深蓝，改掉避免残留 DSH 蓝 |
| 12 | `--dsw-static-blue-500` | `rgb(59, 130, 246)` #3B82F6 | `rgb(43, 127, 176)` #2B7FB0 | 文档选区、轨迹表高亮直接吃这一级；不跟随会让"选中一段文字"还是 Tailwind 蓝 |
| 13 | `--dsw-static-blue-300` | `rgb(147, 197, 253)` #93C5FD | `rgb(168, 219, 244)` #A8DBF4 | 深色 `label-deep-diving-shimmer` 的混色基准 |
| 14 | `--dsw-static-blue-450` | `rgb(77, 147, 248)` #4D93F8 | `rgb(74, 159, 204)` #4A9FCC | 上下文用量环（ContextMeter）tint |
| 15 | `--dsw-static-blue-400` | `rgb(96, 165, 250)` #60A5FA | `rgb(103, 195, 240)` #67C3F0 | 终端 ANSI 亮蓝（`ui-primitives/src/ansi.ts` 的色号映射直接引用该 token） |
| 16 | `--dsw-static-blue-600` | `rgb(37, 99, 235)` #2563EB | `rgb(34, 102, 143)` #22668F | 终端 ANSI 青 |
| 17 | `--dsw-static-blue-900` | `rgb(14, 48, 116)` #0E3074 | `rgb(18, 58, 82)` #123A52 | `--dsw-alias-label-primary-bluish` 的蓝墨色 |
| 18 | `--dsw-static-blue-950` | `rgb(23, 37, 84)` #172554 | `rgb(12, 44, 63)` #0C2C3F | `label-deep-diving` 系列的文字混色基准 |

> 注意：以上 18 条在**浅色块和深色块各写了一遍**（`body{…}` 与 `body[data-ds-dark-theme]{…}`），
> 脚本按"出现 2 次"校验后同步替换，保证两主题同一语义。

### 2.2 画布 / 正文

| # | token | 旧值 | 新值 | 为什么 |
|---|---|---|---|---|
| 19 | `--dsw-alias-bg-base`（浅） | `var(--dsw-static-neutral-bluish-00)` = #FFFFFF | `rgb(249, 250, 252)` **#F9FAFC** | Daniel 浅色画布。**不能**改 `neutral-bluish-00`（它同时是按钮白字、开关滑块的白），所以直接给画布别名赋值 |
| 20 | `--dsw-alias-bg-base`（深） | `var(--dsw-static-neutral-bluish-950)` = #151517 | `rgb(15, 17, 21)` **#0F1115** | Daniel 深色画布（`body{background-color:var(--dsw-alias-bg-base)}` 让整窗生效） |
| 21 | `--dsw-alias-label-primary`（浅） | `var(--dsw-static-neutral-bluish-1000)` = #0F1115 | `rgb(25, 28, 32)` **#191C20** | Daniel 浅色正文 |
| 22 | `--dsw-alias-label-secondary`（浅） | `var(--dsw-static-neutral-bluish-700)` = #61666B | `rgb(91, 100, 112)` #5B6470 | 次级文字换到 Daniel 的蓝灰墨色族，与正文同一色相 |
| 23 | `--dsw-alias-label-tertiary`（浅） | `var(--dsw-static-neutral-bluish-600)` = #81858C | `rgb(133, 143, 155)` #858F9B | 同上，三级灰阶保持一致色相 |
| 24 | `--dsw-alias-label-caption`（浅） | `var(--dsw-static-neutral-bluish-400)` = #ADB2B8 | `rgb(152, 161, 173)` #98A1AD | 同上（占位符、时间戳、辅助说明） |
| 25 | `--dsw-alias-label-primary-dimmed`（浅） | `var(--dsw-static-neutral-bluish-950)` = #151517 | `rgb(44, 50, 58)` #2C323A | "压暗主文字"档，保持在正文墨色族里 |
| 26 | `--dsw-alias-label-primary`（深） | `var(--dsw-static-neutral-bluish-50)` = **#F9FAFB** | 未改 | **已经是 Daniel 深色正文值**，改了只会偏离 |
| 27 | `--dsw-linear-gradient-think`（浅 / 深） | `#fff` / `#151517` | `#F9FAFC` / `#0F1115` | 这两条是**画布字面值**（不在 token 链上）。深色下不改会在新画布上留一条比画布亮的"渐变带" |
| 28 | `--dsw-linear-think-select`（浅 / 深） | `#F5F6F7` / `#232325` | `#F2F4F8` / `#1C2026` | 同上（思考块的选中态底色） |

### 2.3 品牌色 / 链接 / 选中态 / focus ring

| # | token | 旧值 | 新值 | 为什么 |
|---|---|---|---|---|
| 29 | `--dsw-alias-brand-primary`（浅） | `var(--dsw-static-neutral-bluish-1000)` = **#0F1115**（近黑主按钮） | `var(--dsw-static-deepseek-500)` **#2B7FB0** | 这是整次换皮视觉上最明显的一条：DSH 的主按钮是黑的，Daniel 的主按钮是品牌蓝 |
| 30 | `--dsw-alias-brand-primary`（深） | `var(--dsw-static-neutral-bluish-50)` = #F9FAFB（白按钮） | `var(--dsw-static-deepseek-450)` **#4A9FCC** | 深色下用提亮一档的品牌色；配深色墨字 6.41:1（白字只有 2.95:1，所以不改 `label-primary-foreground`） |
| 31 | `--dsw-alias-brand-text`（浅） | `var(--dsw-static-neutral-bluish-1000)` = #0F1115 | `rgb(25, 28, 32)` #191C20 | 字标与正文统一墨色，避免页面里出现两种"近黑" |
| 32 | `--dsw-alias-brand-primary-new-colorprimary-new-color`（浅） | `rgb(65, 118, 230)`（**硬编码字面值**） | `var(--dsw-static-deepseek-500)` | 去掉了色板里最后一处硬编码的 DSH 蓝；现在它跟着色板走 |
| 33 | `--dsw-alias-button-primary-fill` | `var(--dsw-alias-brand-primary)` | 未改 | 派生自 29/30，自动变蓝 |
| 34 | `--dsw-alias-button-primary-hover`（浅） | `var(--dsw-static-neutral-bluish-750)` = #43454A（灰） | `var(--dsw-static-deepseek-600)` #22668F | 蓝按钮悬停应加深蓝而不是跳灰 |
| 35 | `--dsw-alias-button-primary-hover`（深） | `var(--dsw-static-neutral-bluish-100)` = #EBEEF2 | `var(--dsw-static-deepseek-400)` #67C3F0 | 深色下悬停提亮（配深色墨字 10.6:1） |
| 36 | `--dsw-alias-button-info-hover`（浅） | `var(--dsw-static-deepseek-400)` #67C3F0 | `var(--dsw-static-deepseek-600)` #22668F | 发送键是白图标：亮蓝 #67C3F0 上白字只有 1.97:1，悬停改成加深 |
| 37 | `--dsw-alias-button-info-fill`（深） | `var(--dsw-static-deepseek-400)` #67C3F0 | `var(--dsw-static-deepseek-450)` #4A9FCC | 深色发送键白图标对比从 1.97:1 提到 2.95:1（比换皮前 DSH 的 2.48 还高） |
| 38 | `--dsw-alias-link` | 浅 `deepseek-500` / 深 `deepseek-400` | 未改 | 派生，自动变 #2B7FB0 / #67C3F0 |
| 39 | `--dsw-alias-state-business-primary`（= focus ring 默认色） | 浅 `deepseek-500` / 深 `deepseek-400` | 未改 | 派生。`focus.css` 的 `outline-color: var(--dsw-focus-ring-color, var(--dsw-alias-state-business-primary))` 因此自动变 Daniel 蓝 |
| 40 | `--dsw-specific-sidebar-nav-item-active`（浅） | `var(--dsw-static-neutral-bluish-100)` = #EBEEF2 | `var(--dsw-static-deepseek-50)` #F2F9FD | 选中态改用 Daniel 蓝（不是灰） |
| 41 | `--dsw-specific-sidebar-nav-item-active`（深） | `var(--dsw-static-neutral-bluish-750)` = #43454A | `var(--dsw-static-deepseek-900)` #123A52 | 同上，深色下用深蓝底 |
| 42 | `--dsw-specific-sidebar-nav-item-active-accent`（深） | `var(--dsw-static-neutral-bluish-800)` = #353638 | `var(--dsw-static-deepseek-800)` #1B4F6E | 选中行左侧 accent 用品牌深蓝 |
| 43 | `--dsw-specific-bubble`（浅） | `var(--dsw-static-deepseek-50)` → #F2F9FD | `var(--dsw-static-deepseek-100)` #E7F4FC | 新画布本身很白，用户气泡降到下一档才看得出边界 |

### 2.4 侧栏底色（token 覆盖得到，所以仍走 token）

| # | token | 旧值 | 新值 | 为什么 |
|---|---|---|---|---|
| 44 | `--dsw-specific-sidebar-fill`（浅） | `var(--dsw-static-neutral-bluish-50)` = #F9FAFB | `rgb(243, 246, 250)` #F3F6FA | 旧值几乎等于新画布（差 1 个色阶），侧栏会和对话区糊成一片；降一档拉开层次 |
| 45 | `--dsw-specific-sidebar-fill`（深） | `var(--dsw-static-neutral-bluish-900)` = #1B1B1C | `rgb(18, 21, 26)` #12151A | 贴住新深色画布、只比画布亮一档 |

### 2.5 字体

| # | token | 旧值 | 新值 | 为什么 |
|---|---|---|---|---|
| 46 | `--dsh-font-family-text-default` | `-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif` | `Inter, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif` | Daniel 字体栈。`--dsw-font-family` / 所有 `--dsw-font-*` 复合字体 token 都从它派生，改一处全站生效 |
| 47 | `--dsh-font-family-code-default` | 未改 | — | 等宽栈是代码块专用，不属于"基础正文栈"；换掉会让代码/终端排版变形 |
| 48 | `--dsw-font-family-brand` | `'Montserrat', …` 未改 | — | Montserrat 是离线打包的品牌字（`brand-font.css` + 3 个 woff2 + OFL 许可，有单测锁定），只用于品牌字标；换字体会引入新字体资源（违反"不新增依赖"） |

> 字体落地说明：桌面端不随包分发 Inter，`Inter` 在已装该字体的机器上生效，否则按栈落到 PingFang SC（macOS）/ 雅黑（Windows），
> 效果与 Daniel 官网的中文正文一致。**没有**新增字体文件。

### 2.6 圆角

| # | token | 旧值 | 新值 | 为什么 |
|---|---|---|---|---|
| 49 | `--dsw-radius-sm` | `8px` | `10px` | Daniel 控件档 10–12px；`sm` 是按钮/输入/标签的主控件档 |
| 50 | `--dsw-radius-md` | `12px` → 未改 | — | 已在 Daniel 控件档上界，无需改 |
| 51 | `--dsw-radius-lg` / `--dsw-radius-xl` | `16px` / `20px` → 未改 | — | 已在 Daniel 卡片档 16–20px 内，无需改 |
| 52 | `--dsw-radius-xs` | `4px` → 未改 | — | 绘制细节档（行号、勾选框内框），故意保留小几何 |
| 53 | `--dsw-radius-panel` | `28px` → 未改 | — | 大面板档（composer 卡片、浮层窗口），不属于"控件/卡片"两档；改动会连带改变多个浮层几何，超出换皮范围 |

### 2.7 阴影（Daniel 的冷黑 + 双段式）

| # | token | 旧值 | 新值 | 为什么 |
|---|---|---|---|---|
| 54 | `--dsw-shadow-lv1` | `0 2px 4px 0 rgba(0,0,0,.05)` | `0 1px 2px 0 rgba(16,24,40,.06)` | Daniel 阴影色是冷黑 `#101828` 系，不是纯黑；近贴层用 1px/2px |
| 55 | `--dsw-shadow-lv2` | `0 4px 12px rgba(0,0,0,.02), 0 2px 8px rgba(0,0,0,.04)` | `0 1px 2px rgba(16,24,40,.06), 0 8px 24px rgba(16,24,40,.06)` | Daniel 卡片阴影基线（与引导页 `--ob-shadow-card` 完全同值，全站一致） |
| 56 | `--dsw-shadow-lv3` | `0 0 1px rgba(0,0,0,.2), 0 0 4px .02, 0 12px 32px .08` | `0 0 0 .5px rgba(16,24,40,.08), 0 1px 2px .06, 0 8px 24px .06` | 浮层/Toast；把 1px 环换成 0.5px 发丝，与全站 hairline 体系一致 |
| 57 | `--dsw-shadow-lv1-blur` | `0 4px 12px rgba(0,0,0,.02)` | `0 4px 12px rgba(16,24,40,.04)` | 同上，只换冷黑与透明度 |
| 58 | `--dsw-elevation-panel` / `-prominent` / `-soft` | 三件套里的柔光层 `rgba(0,0,0,.02–.05)` | `rgba(16,24,40,.04–.08)` 双段式 | 保持 `var(--dsw-elevation-stroke), 0 …` 的契约形状（elevation 测试逐字断言这个前缀），只换柔光色与档位 |

### 2.8 计数

- 脚本化替换 **56 个编辑点 / 75 处字面值**（每处都断言了出现次数，多一处少一处都会中断），共 **45 个 token 名**取值发生变化。
- 其中 19 个色板 token 在浅色块与深色块里**各改一次**（38 处），其余是语义别名（浅 13 处 / 深 10 处）与字体、圆角、阴影、渐变。
- 上表 58 行里 **10 行是"明确不改 + 原因"**（26/33/38/39/47/48/50/51–53），其余 48 行为实际改动（部分行合并了深浅两主题或整族 token）。

---

## 3. 深色模式是怎么保证的

1. **两套主题块各自赋值**：`body{…}`（浅）与 `body[data-ds-dark-theme]{…}`（深）是两份独立声明，
   所有画布 / 正文 / 侧栏 / 按钮色都分别写在各自块里，没有"一套值两主题共用"的字面色。
2. **色板双写**：18 条 `--dsw-static-*` 在两个块里同步改过（脚本按"出现 2 次"断言），
   所以同一语义（brand / link / focus / selection）在深浅下都是 Daniel 蓝，只是明度档不同（#2B7FB0 ↔ #67C3F0 / #4A9FCC）。
3. **深色正文本来就是对的值**：`--dsw-alias-label-primary`（深）原值 `neutral-bluish-50` = **#F9FAFB**，正好等于 Daniel 深色正文，
   所以这一条**故意不改**；深色画布由 `--dsw-alias-bg-base` 换成 #0F1115。
4. **主题切换靠属性重算**：`data-ds-dark-theme` 一变，CSS 变量层即时重算，无需重载、无需 JS 参与。
5. **顺手修掉两处"画布残影"**：`--dsw-linear-gradient-think` / `--dsw-linear-think-select` 是旧画布的字面值
   （深色 `#151517`/`#232325`），不在 token 链上；不改的话深色下会在新画布 #0F1115 上出现一条偏亮的渐变带。已同步到 `#0F1115`/`#1C2026`。

**实测解析值**（用脚本从改后的 CSS 里按 `var()` 链解出来，不是人肉推测）：

```text
== LIGHT
--dsw-alias-bg-base                  #f9fafc   --dsw-alias-label-primary        #191c20
--dsw-alias-label-secondary          #5b6470   --dsw-alias-label-tertiary       #858f9b
--dsw-alias-link                     #2b7fb0   --dsw-alias-brand-primary        #2b7fb0
--dsw-alias-state-business-primary   #2b7fb0   --dsw-specific-sidebar-fill      #f3f6fa
--dsw-specific-sidebar-nav-item-active #f2f9fd --dsw-specific-bubble            #e7f4fc
--dsw-alias-label-primary-foreground  #ffffff  --dsw-alias-button-info-fill     #2b7fb0
contrast text/canvas 16.37 · link/canvas 4.22 · btn fg/brand 4.41

== DARK
--dsw-alias-bg-base                  #0f1115   --dsw-alias-label-primary        #f9fafb
--dsw-alias-label-secondary          #cfd3d6   --dsw-alias-label-tertiary       #adb2b8
--dsw-alias-link                     #67c3f0   --dsw-alias-brand-primary        #4a9fcc
--dsw-alias-state-business-primary   #67c3f0   --dsw-specific-sidebar-fill      #12151a
--dsw-specific-sidebar-nav-item-active #123a52 --dsw-specific-bubble            #2c2c2e
--dsw-alias-label-primary-foreground  #0f1115  --dsw-alias-button-info-fill     #4a9fcc
contrast text/canvas 18.08 · link/canvas 9.58 · btn fg/brand 6.41
```

> 对比度说明：浅色链接 #2B7FB0 / 画布 4.22:1、主按钮白字 4.41:1 —— 都略低于 AA 正文 4.5:1。
> 这是 Daniel 品牌色本身的边界（官网同值），要提上去就得把品牌色压到 #22668F，本轮按"品牌色以基线为准"保留，记录在此备查。

---

## 4. 动了哪两个组件 CSS，为什么（token 覆盖不到的）

| 文件 | 改动 | 为什么 token 覆盖不到 |
|---|---|---|
| `packages/client/ui-layout/src/client/AppFrame.module.css` | macOS 侧栏的蓝色 wash 里 5 处 `rgb(122 155 240)` → `rgb(43 127 176)`、4 处紫 `rgb(143 137 184)` → 亮蓝 `rgb(103 195 240)`；注释同步改写 | token 只提供侧栏**底色**（`--dsw-specific-sidebar-fill`）。这段是"底色 + 顶部蓝 wash + 底部紫 wash + 混入色相"四层叠加，需要**固定色相 + 指定 alpha**，token 层没有对应变量（现成的 token 都是不透明色，套进 `color-mix(… 40%, transparent)` 会丢掉设计意图）。只换色相与注释，alpha/层数/结构一字未动 |
| `packages/client/ui-settings-account/src/client/DesktopOnboarding.module.css` | ① 3 处 `outline: 2px solid var(--ob-focus)` → `var(--dsw-focus-ring-width) solid var(--dsw-focus-ring-color, var(--dsw-alias-state-business-primary))`；② `.indicator` 补 `corner-shape: round`；③ `.brandMark` 13px/11px、`.navigation button` 8px 等局部圆角 → `--dsw-radius-md` / `--dsw-radius-sm`；④ `--ob-radius-card/control`、`.confirmationClose`、`.dialogButton` 也 token 化；⑤ 删掉随之失效的 `--ob-focus` 定义 | **不是本次换皮引入的**：这三类问题是前序 WIP 留下的样式契约违规（基线跑这套测试就已经 3 红，见 §6）。仓库用单测强制"focus ring 必须走共享 ring 色""组件圆角必须走 `--dsw-radius-*`""full-round 必须配对 corner-shape"。修法是把 onboarding 拉回 token 体系，不改结构/间距；`.confirmationClose`/`.dialogButton`/`--ob-radius-card` 的值与改前等价（28px/12px/20px），`--ob-radius-control` 顺带从 16px 落到 Daniel 控件档 12px |

`packages/client/ui-theme/tests/expected/radius-exceptions.expected.json` 同步删掉 `DesktopOnboarding.module.css` 那段**过期例外**
（里面列的 `.card: 32px`、`.page .action: 12px`、`.indicator: 6px` 在现文件里已不存在，属于陈旧期望）。

---

## 5. 没有改的（结构 / 功能 / 其他视觉面）

- **布局 / 间距 / 网格 / 断点**：0 处改动。`padding`、`gap`、`width`、`grid-template-*` 全部未动。
- **组件结构 / JSX / 属性**：0 处 `.tsx` 改动（本轮只改 CSS 与一个测试期望 JSON）。
- **图标 / 插画 / 组件逻辑 / 交互**：未动。插画色板（`--dsw-alias-illustration-*` → `neutral-bluish-55/90/310`）**故意不改**，
  因为有单测把这三个中性步进锁成浅色插画的契约值（`[245,247,250]` / `[237,240,244]` / `[202,210,219]`）。
- **深色卡片层级 `--dsw-alias-bg-layer-1/2/3`**：保留原 `neutral-bluish-875/850/800`。原因：`scrollbar-styles` 契约用
  "深色层级解析值 == palette rung"来表达 elevation 关系，`--dsw-specific-input-major` / `--dsw-specific-tip` 正是靠"与 layer-2/3 同 rung"
  才被纳入受检面；把 layer 改成字面色会让 rung 匹配失效、把这两个面从受检集合里掉出去（范围收缩）。
  深色卡片因此仍是中性灰 #2C2C2E —— 与 Daniel 深色中性面同族，且不引入 DSH 蓝。
- **菜单玻璃底 `--dsw-menu-surface-fill`**（浅 `rgba(252,253,254,.7)` / 深 `rgba(48,49,54,.64)`，含 darwin 两个变体）：
  `elevation-styles` 测试逐字锁定这四个值；它们本身是近白/近黑的中性玻璃，与 Daniel 画布不冲突，改了要动契约测试而收益为 0。
- **`--dsw-static-blue-50/50p/75/100/800`**：全仓 grep 无任何别名或组件引用（死 token），改了没有可见效果。
- **滚动条 / 状态色（success/warn/error/violet）/ diff 色**：不属于品牌蓝链路，保持原值。
- **`--dsw-alias-label-primary-foreground`（深）**：保持深墨 `#0F1115`。深色主按钮填的是亮蓝 #4A9FCC，深墨字 6.41:1；
  若改成白字只剩 2.95:1，且会让完成态圆点（绿底）的白字对比更差。

---

## 6. 验收（真实输出）

### 6.1 构建命令

```text
$ node_modules/.bin/tsc -b tsconfig.client.json
TSC EXIT=0            ← 无输出即通过
```

```text
$ pnpm -C apps/desktop run build
ℹ [ESM] lib/main.js  874.71 kB │ gzip: 221.18 kB
✔ Build complete in 180ms
vite v6.4.3 building for production...
✓ 34 modules transformed.
lib/welcome/design-platform.css        24.94 kB │ gzip:  3.67 kB
lib/welcome/welcome.css                38.60 kB │ gzip:  5.36 kB
lib/welcome/welcome.js                229.22 kB │ gzip: 70.07 kB
✓ built in 394ms
DESKTOP BUILD EXIT=0
```

构建产物已吃到新色板（抽查 `lib/welcome/design-platform.css`）：

```text
--dsw-alias-bg-base: rgb(249, 250, 252)      ← 浅色画布
--dsw-alias-bg-base: rgb(15, 17, 21)         ← 深色画布
--dsw-static-deepseek-500: rgb(43, 127, 176) ← Daniel 蓝
--dsw-alias-brand-primary: var(--dsw-static-deepseek-500)
--dsw-alias-brand-primary: var(--dsw-static-deepseek-450)  ← 深色
--dsw-shadow-lv2: 0 1px 2px 0 rgba(16, 24, 40, .06), 0 8px 24px 0 rgba(16, 24, 40, .06)
```

### 6.2 单测（任务指定的两套）

```text
$ pnpm --dir . exec vitest run packages/client/ui-theme/tests packages/client/ui-settings-account/tests
 Test Files  49 passed (49)
      Tests  546 passed (546)
   Duration  41.27s
VITEST EXIT=0
```

单独跑 ui-theme（更严的契约面：色板/圆角/focus/elevation/滚动条/插画/字体）：

```text
 Test Files  22 passed (22)
      Tests  174 passed (174)
```

**关于基线**：改之前这套测试**本来就有 3 条红**（不是本次引入）——`corner-shape`、`focus-ring`、`radius`
全部指向 `ui-settings-account/src/client/DesktopOnboarding.module.css` 的前序 WIP 违规。本次按 §4 修掉后，
三个文件从 3 failed / 171 passed 变成 **0 failed / 174 passed**。
（验证方式：把 4 个改过的 CSS 文件临时还原到 index 版本再跑，确认这 3 条红在改前就存在。）

### 6.3 映射表覆盖

- 表内 58 行，**实际改动 45 个 token 名**（远超"至少 10 条"要求），另有 10 行明确说明为何不改。
- 其中最容易漏、也最容易被误判为"没改"的几条：`--dsw-alias-link`、`--dsw-alias-state-business-primary`（focus ring）、
  `--dsw-alias-button-primary-fill`、`--dsw-alias-bg-document-selection`、`--dsw-specific-sidebar-nav-item-active-accent`（浅）
  —— 它们**一行没改**，但值已经变成 Daniel 蓝，因为改的是它们指向的色板。

### 6.4 没做的事

- **未打包**（DMG/exe 按纪律不跑）。
- **未真机点 GUI**：本机无交互桌面会话；深色/浅色、侧栏、对话区、设置页的观感以"token 解析值 + 构建产物 + 契约测试"验证，
  真机确认留给下一轮。

## 7. 追加调整（对比度，D-069）

按用户裁决选 B：浅色文字/按钮加深一档，装饰色保持品牌蓝。

| token（仅浅色块） | 旧 | 新 | 对比度 |
|---|---|---|---|
| `--dsw-alias-link` | `var(--dsw-static-deepseek-500)` = `#2B7FB0` | `#22668F` | 4.22 → **5.98** |
| `--dsw-alias-brand-primary` | 同上 | `#22668F` | 白字 4.41 → **6.24** |
| `--dsw-alias-button-primary-hover` | `var(--dsw-static-deepseek-600)` | `#1B5272` | 8.05 |

保持不变的装饰性用法：`--dsw-alias-brand-primary-new-color…`、`--dsw-alias-state-business-primary`（focus ring）、选中态背景，仍用 `#2B7FB0` / `#67C3F0`。
