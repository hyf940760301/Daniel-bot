# CHANGES · S6.2 左栏能力地图（只读 · 默认收起）

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开，基线 `ce7073d5`，已含品牌/登录/主题改造）
> 新增包：`packages/client/ui-capability-map`（`@deepseek-ai/dsh-client-ui-capability-map`）
> 状态：**类型检查 / 桌面构建 / 单测全绿；未打包（按纪律）**
> 一句话：左栏加一条**只读**能力地图——默认收起成 48px 竖条，点开 320px，按 9 个业务阶段列出「关键能力」，本地搜索过滤，不执行任何命令。

---

## 1. 插槽选择依据（先侦察后决策）

### 1.1 三个候选的实测事实

| 候选 | 事实（源码行号） | 结论 |
|---|---|---|
| `sidebar` | 声明为 **single**（`packages/client/ui-layout/src/client/index.ts:70`）；文档写明 **OCCUPIED by ui-sidebar's SidebarRoot**，注册到这里是"replaces the navigation column outright"（同文件 `:60-64`）；single 槽同优先级二次注册**直接抛错**，不同优先级则**阴影覆盖**（`packages/client/ui-slots/src/index.ts:1215-1223`）。渲染方是 `AppFrame.tsx:273-277`（`renderSlot('sidebar', { collapsed, width, drawer })`） | ❌ 会顶掉会话列表与其内部座位（workspaces/settings），违反"不覆盖现有 sidebar 内容" |
| `shell.leading` | 同为 **single**（`ui-layout/src/client/index.ts:121`），文档写明 **OCCUPIED by ui-sidebar's reopen/New Session controls**（`:113`）；且 **只在抽屉态或 macOS 侧栏收起时挂载**：`AppFrame.tsx:286` `const leadingMounted = drawer \|\| darwin && sidebarCollapsed`，`:331-335` 条件渲染 | ❌ 一是会覆盖侧栏的窗口控件，二是默认（侧栏展开）**根本不渲染**，能力地图会整条消失 → 不满足"默认收起仍可见" |
| `shell.overlay` | **list** 槽（`ui-layout/src/client/index.ts:107`），文档写明是"the additive seat for a frame-wide surface of your own: a fresh `id` is added beside the shipped entries instead of replacing them"（`:104-105`），整层 click-through、条目自行 opt-in 指针事件（`:98-102`）；`AppFrame.tsx:281` 每帧都 render、`:328-330` 常驻挂载；宿主层 CSS `AppFrame.module.css:381-390`（`position:absolute; inset:0; pointer-events:none`，`> *` 才收回指针） | ✅ 追加、不抢位、常驻 |

> 补充：`shell.overlay` 也是本管线既定技术依据——`daniel-bot/specs/DECISIONS-A.md` 的 D-056「技术依据」一行直接指到 `packages/client/ui-open-in-app/src/client/index.ts:60` 的 `shell.overlay` 注入。

### 1.2 结论

挂 **`shell.overlay`**，用自有 id `capability-map.rail`（`order: 40`）**追加**一条浮层。不改 AppFrame、不动 ui-sidebar、不注册 `sidebar` / `shell.leading`；`shell.overlay` 是 list 槽，新 id 与出厂条目并存。

**代价（如实记录）**：overlay 是浮层，不是网格轨道。收起态 48px 竖条贴在 frame 左边缘（`left: 8px`，顶到 `--dsh-frame-top-clearance` 之下），因此在应用侧栏展开时**视觉上压在侧栏最左侧 48px 之上**（与 `shell.leading` 这类窗口 chrome 同一层语义）；它不会卸载/替换侧栏，dock 区除竖条外全部 click-through。若后续要求"独占一条真实列、完全不吃侧栏像素"，需要改 `AppFrame` 的 grid 轨道（`AppFrame.tsx:295-297` 目前固定三列），属改壳，不在 S6.2 范围。

---

## 2. 新增/改动文件

| 文件 | 作用 |
|---|---|
| `packages/client/ui-capability-map/package.json` | 新包清单；`dsh.client.inject` = renderer + locale；`exports["./client"]` |
| `.../tsconfig.json`、`tsdown.config.ts` | 与 `ui-brand-official` 同构（`clientBundle`，client 面 `src/client/index.ts`） |
| `.../src/index.ts` | 空 apply，给 Loader 一个宿主行 |
| `.../src/client/index.ts` | 注册字典 + **唯一**一条 `shell.overlay` 条目（`id: capability-map.rail`, `order: 40`, `locale: capability-map`） |
| `.../src/client/CapabilityMap.tsx` | 竖条 / 面板 / 搜索 / 阶段展开 / Esc 收起（组件内状态） |
| `.../src/client/CapabilityMap.module.css` | 全部用 `--dsw-*` token；卡片 16px、控件 10px |
| `.../src/client/capability-map.generated.ts` | **生成物**：精简后的能力地图数据 |
| `.../src/client/types.ts` | 数据契约（`CapabilityMapData` / `CapabilityStage` / `CapabilityItem`） |
| `.../src/client/locales.ts` | `zh` + `en`（键集以 zh 为准，en 用 `satisfies` 锁全） |
| `.../scripts/build-capability-map.mjs` | 裁剪脚本（见 §3）；`pnpm -C … run map:build` |
| `.../tests/capability-map.client.spec.tsx` | 8 条单测 |
| `.../README.md`、`README.zh.md`、`README.i18n.yaml` | 包文档（`package-reference` 模板；中英成对，哈希记录由 `verify-translation-pairing --write` 生成） |
| `.../locale/{de,en,es,fr,ja,pt,ru,zh}.json` | 包元数据（`meta.title` / `meta.description`），满足 `verify-locale-metadata` |
| `scripts/verify-package-readme-model-experience.ts`（+1 行） | 把本包登记进 `SENTENCE_MODEL_EXPERIENCE`（`kind: 'none'`）＋ README 的 "None, as …" 一句式 Model Experience |
| `tsconfig.client.json`（+1 行） | 项目引用 `./packages/client/ui-capability-map` |
| `tsconfig.base.json`（+1 行） | `@deepseek-ai/dsh-client-ui-capability-map` → `.../src` |
| `packages/bundle/web-app/package.json`（+1 行） | `workspace:*` 依赖 |
| `packages/bundle/web-app/cordis.patch.yml`（+5 行） | 客户端 roster 插入 `ui-capability-map` 行 |
| `pnpm-lock.yaml` | 新增 importer（`pnpm install --lockfile-only` 生成） |

---

## 3. 数据裁剪规则（构建期，不在运行期读工作区文件）

**输入**：`daniel-bot/app/workflow-map.json`（`daniel.workflow-map.v1`，10 个 workflow / 91 条 command，含 `fieldEvidence`）
**输出**：`src/client/capability-map.generated.ts`（已入库；浏览器包不读任何工作区文件）

```bash
node packages/client/ui-capability-map/scripts/build-capability-map.mjs \
  --from "/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/app/workflow-map.json"
# → wrote …/capability-map.generated.ts
#   stages 9 · capabilities 30 · commands 43/91
#   产品说明=0 发现=6 背调=2 外联=0 谈判=0 合同=0 执行=0 SOV=4 数据=31
```

规则（脚本注释里逐条写明，改规则要同步本文件）：

1. **只发布 9 个业务阶段**，顺序＝业务流：产品说明 → 发现 → 背调 → 外联 → 谈判 → 合同 → 执行 → SOV → 数据。第 10 个 workflow `ops`（平台运维）是内部阶段，**整段剔除**，其 48 条命令不进左栏。
2. 每阶段保留：`id`、业务名（`name`）、一句话（`summary`，脚本内人工撰写、非抓取）、`commands`（该阶段映射到的命令数）、`assisted`、`capabilities`（3–5 条）。
3. **关键能力来源**：按命令的 `module` 分组（按命令数降序、同数按首次出现），`detail` 取该组最多 3 个 `page` 名；分组 ≥3 时取前 5 组。分组 <3 的阶段改用 workflow 的 `steps`（业务子阶段）当能力名，再补该阶段的 module 组；**同名不重复**（`背调` 的 `真实性核验` 既是步骤又是模块，合并成一条并带上该模块的 2 条命令）。
4. **无命令阶段**（产品说明/外联/谈判/合同/执行）标 `assisted: true`，能力＝该阶段 3 个 steps；UI 显示「助手完成」而不是「0 条命令」（对应 D-060：本阶段由助手按判据完成）。
5. **只留业务字段**：命令原文、`match`、`mcpTool`、`fieldEvidence`、`workflowReason`、`internal`、源码路径**全部丢弃**；只保留源文件 sha256 作可追溯指纹。生成脚本对「每阶段 3–5 条」做断言，不满足直接失败，不会静默出半张图。

**精简 JSON 的字段与条数**（`schema: daniel.capability-map.v1`）：

| 字段 | 内容 |
|---|---|
| `schema` | `daniel.capability-map.v1` |
| `source` | `{ workflowMap: "daniel-bot/app/workflow-map.json", sha256: "ce185a093d8b…", workflows: 10, commands: 91 }` |
| `stages` | **9 条**（顺序见上）；每条 `{ id, name, summary, commands, assisted, capabilities }` |
| `stages[].capabilities` | 每条 `{ name, detail, commands }`；**合计 30 条**，每阶段 3–5 条（3,3,3,3,3,3,3,4,5） |
| 命令覆盖 | 业务命令 **43/91**（其余 48 条属 `ops`，按规则 1 不进左栏） |

例（`发现`，截断）：`{ id: "discovery", name: "发现", commands: 6, assisted: false, capabilities: [ { name: "红人检索", detail: "检索历史 · 检索任务进度 · 发起检索", commands: 3 }, … ] }`

---

## 4. 交互

| 行为 | 实现 |
|---|---|
| **默认收起** | 组件首帧 `useState(false)`，收起分支**只渲染** 48px 竖条（竖排标题 ＋ 清单图标 ＋ 右向箭头，整条是一个 `<button>`） |
| 展开 | 点竖条 → 320px 面板：标题、搜索框、9 个阶段行；每条右侧标「N 条命令」或「助手完成」 |
| 单阶段展开 | 阶段行是 `<button aria-expanded>`，点开显示该阶段一句话 ＋ 3–5 条关键能力（名称 ＋ 页面名 ＋ 命令数） |
| 收起 | ① 面板右上关闭按钮；② 面板内按 `Esc`（`onKeyDown` 在面板内拦截 `Escape`，`preventDefault` + `stopPropagation`，不吞全局 Esc） |
| 搜索 | `type="search"` 输入框，**本地 substring 过滤**业务名/一句话/能力名/页面名；命中时自动展开该阶段；无命中显示 `role="status"` 空态。不发请求、不做排序 |
| 键盘可达 | 竖条、关闭钮、阶段行都是原生 `<button>`（Tab 可达、Enter/Space 触发）；展开时焦点自动落到搜索框，收起时焦点回到竖条；`focus-visible` 用主题 focus ring |
| **只读** | 组件无 RPC、无命令、无网络；能力行是纯文本（无 `<a>`、无按钮、无 `data-command`）；面板底部常驻「只读地图：只说明能做什么，不执行任何命令」 |

**状态存哪**：全部是**组件内存态**（`useState`）——`open`（是否展开）、`query`（搜索词）、`openStage`（展开的阶段 id）。**没有 store、没有持久化**：所以每次挂载必然收起，重启/重挂也不会记住上次展开，硬要求"默认收起"由实现方式保证，而不是靠初始化兜底。

---

## 5. 视觉

- 只用 token：`--dsw-alias-bg-layer-1/2`、`--dsw-alias-label-primary/secondary/tertiary/caption`、`--dsw-alias-border-l1/l2`、`--dsw-alias-interactive-bg-hover`、`--dsw-alias-link`、`--dsw-alias-state-business-primary`、`--dsw-elevation-prominent` + `--dsw-elevation-stroke-color`、`--dsw-radius-xs/sm/lg`、`--dsw-focus-ring-width/color`；顶距用 `--dsh-frame-top-clearance`（macOS 48px）。
- 面＝`bg-layer-1` ＋ `elevation-prominent`（和 shell 菜单同一套 elevation 三件套）；卡片圆角 16px（`radius-lg`）、控件 10px（`radius-sm`）。
- 深浅色都成立：所有颜色来自 token，没有写死色值、没有新增字体/图标库；图标全部来自 `@deepseek-ai/dsh-client-ui-primitives`（`IconChecklistOutlineRegular`、`IconChevronRightOutlineRegular`、`IconCloseOutlineRegular`、`IconSearchOutlineRegular`）。
- 字体沿用继承（14/13/12/11px 阶梯与侧栏一致），不引入字体。

---

## 6. 门禁与测试（真实输出）

```text
$ node_modules/.bin/tsc -b tsconfig.client.json
TSC_EXIT=0

$ pnpm -C apps/desktop run build
✓ built in 430ms            # …welcome.js 229.22 kB
BUILD_EXIT=0

$ node_modules/.bin/vitest run packages/client/ui-capability-map/tests/capability-map.client.spec.tsx
 ✓ |thread-safe| packages/client/ui-capability-map/tests/capability-map.client.spec.tsx (8 tests) 153ms
 Test Files  1 passed (1)
      Tests  8 passed (8)
TEST_EXIT=0

$ ../../../node_modules/.bin/tsdown        # 包自身 client 产物
ℹ [client] [CJS] lib/client.js  26.09 kB │ gzip: 7.08 kB
✔ Build complete in 69ms

$ node_modules/.bin/vitest run scripts/check-workspace-constraints.spec.ts \
    scripts/client-bundle-css.spec.ts scripts/client-bundle-purity.spec.ts scripts/client-tsconfig.spec.ts
 Test Files  4 passed (4)
      Tests  244 passed (244)
```

仓库文档/元数据门禁（新包会触发的那几条，逐条真跑）：

```text
$ tsx scripts/verify-locale-metadata.ts
verify-locale-metadata: all package and template metadata has complete shipped-language translations.   # EXIT 0

$ tsx scripts/verify-package-readme-summaries.ts
verify-package-readme-summaries: 426 English package README Summaries are within 100 words.            # EXIT 0

$ tsx scripts/verify-package-readme-model-experience.ts
… 373 README(s) checked (… 138 explained none …), all conform.                                         # EXIT 0

$ tsx scripts/verify-package-readme-limitations.ts
verify-package-readme-limitations: 373 package READMEs checked (1 whitelisted), all conform.           # EXIT 0

$ node_modules/.bin/vitest run scripts/doc-standard.spec.ts
 ✓ |thread-safe| scripts/doc-standard.spec.ts (22 tests) 389ms   Tests 22 passed (22)                 # EXIT 0
```

> 例外（与本次改动无关）：`tsx scripts/verify-translation-pairing.ts` 报 `apps/desktop/docs/diagnostics/README.i18n.yaml: out of sync` —— 那是前序桌面补丁（`apps/desktop/docs/diagnostics/README.md` 已被改）留下的记录，本次未触碰；本包自己的 `README.i18n.yaml` 已用 `--write` 生成并与正文一致。

8 条单测（覆盖硬要求）：

1. **默认收起**：挂载后只有竖条，`aria-expanded=false`，无面板/无搜索框/无阶段列表，竖条文本不含任何阶段简介。
2. **展开**：点竖条出现面板与 9 个阶段行；点「发现」出该阶段 3–5 条能力（含 `红人检索`）；再点收起。
3. **Esc**：焦点在搜索框时按 `Escape` → 面板卸载、焦点回到竖条。
4. **搜索过滤**：输入「真实性」只剩「背调」且自动展开；输入不存在词显示空态；清空恢复 9 行；`fetch` **0 次调用**。
5. **只读不可执行**：面板内无 `<a>` / `role=link` / `data-command`；按钮总数＝9 阶段＋1 关闭；点能力名无副作用；`fetch` 与 `WebSocket` **均未调用**。
6. **不泄内部字段**：面板文本不含 `daniel_`、`fieldEvidence`、`mcpTool`、`.py`、`--confirm`、`workflow-map.json`、`internal`。
7. **数据契约**：9 阶段顺序固定、每阶段 3–5 条、能力行仅 `{name, detail, commands}`、业务命令 43、源总数 91/10；序列化后不含任何内部键。
8. **插槽注册**：`apply` 后 `shell.overlay` 恰 1 条（id `capability-map.rail`），`sidebar` 与 `shell.leading` **各 0 条**。

---

## 7. 未做 / 需要注意

1. **未打包**（按纪律）。桌面包要在真机看到这条竖条，打包前必须重跑客户端 bundle（本包 `lib/client.js` 已本地构建验证，26.09 kB），即 `pnpm run build:lib:client`（或 `pnpm -C packages/client/ui-capability-map run bundle`）；只跑 `pnpm -C apps/desktop run build` 不会产出客户端产物。
2. **本机 `pnpm install` 被 store 策略挡住**：`pnpm install` 判定现有 `node_modules` 与 `/private/tmp/.pnpm-store/v11` 不匹配，要求整目录重装（`ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`），故**没有整装**；改为 `pnpm install --lockfile-only` 更新锁文件，并按 pnpm 同构手工补了 3 处 `node_modules` 软链（新包自身的 9 条、`packages/bundle/web-app/node_modules/@deepseek-ai/dsh-client-ui-capability-map`）。干净环境直接 `pnpm install` 即可，锁文件已包含新 importer。
3. **未做真机视觉验收**（未打包、未起应用）：冷暖两套主题的观感只做了 token 层核对；浮层与侧栏的重叠关系见 §1.2，需要真机确认接受度。
4. 源 `workflow-map.json` 更新后必须重跑裁剪脚本，否则地图与能力清单会过期（生成文件头部有源 sha256 前 12 位可对账）。
5. **改了一条门禁脚本**：`scripts/verify-package-readme-model-experience.ts` 的 `SENTENCE_MODEL_EXPERIENCE` 增加了本包一行（`kind: 'none'`）。这是该门禁的既定做法——浏览器侧、不触模型的包必须在审计清单里留理由；不登记该门禁会以"missing package README / missing Model Experience"报错。
6. 视觉重叠（§1.2）与真机观感都**未做验收**（未打包）。若要求"左栏完全不吃侧栏像素"，需要改 `AppFrame` 的列轨道或把浮层改成按侧栏宽度偏移，二者都超出 S6.2 范围，留待裁决。
