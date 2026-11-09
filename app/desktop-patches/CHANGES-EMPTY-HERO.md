# 变更记录：新会话（空白草稿）Hero 改成 Daniel 的样子

> 工作树：`/tmp/dsh-build/dsh-src`（DSH 二开）
> 改动包：`packages/client/ui-conversation`（组件 + 文案 + 预填桥）、`packages/client/ui-primitives`（品牌位图公开导出）
> 状态：**类型检查 / bundle / 桌面构建 / 单测已跑（见 §8）；未打包（按纪律）**
> 一句话：点「创建新会话」看到的不再是 Harness 的「探索未至之境 / 预览版 + 鲸鱼」，而是 **Daniel Bot 标记 + 开始一个新任务 + 一句副标题 + 3 个可点示例**；示例只把话填进输入框，**永远不替你发送**。

---

## 1. 问题与定位

用户原话：*「点击创建新会话，新会话的对话框还是 harness 默认的探索未至之境的预览版页面内容，说明这里漏掉了没有进行改造」*。

漏改的就是这个组件——空白草稿阶段（`data-phase="hero"`）的 Hero：

| 项 | 改前 | 改后 |
|---|---|---|
| 品牌标记 | `FISH_LOGO_PATH`（Harness 鲸鱼，SVG，hover 有 SMIL 摆动） | **Daniel Bot 产品标记**（`DANIEL_BOT_MARK` 位图，静止） |
| 标题 | `探索未至之境` / `Into the Unknown` | **`开始一个新任务` / `Start a new task`** |
| 角标 | `预览版` / `Preview`（标题右上角 mono 小胶囊） | **删除**（会让人以为功能不全） |
| 副标题 | 无 | **一句**：`说说你想做什么，Daniel 会调用对应能力去完成。` |
| 示例入口 | 无 | **3 个可点业务示例**，点击只预填草稿 |
| 动效 | hover 鲸鱼摆动（SMIL + CSS） | **无动画**（同时满足 `prefers-reduced-motion`） |
| 颜色 | — | 全部 `--dsw-*` token，深浅色共用一张表 |

> 说明：鲸鱼是从「组件 fallback」来的，不是某个插件占位。`ui-brand-official` 的官方品牌插件**故意不注册** `conversation.hero.brand.mark`（它的测试也断言了这一点），所以 hero 一直落在 Harness 的鲸鱼 fallback 上——这就是「漏改」的机制原因。

---

## 2. 改动文件

| 文件 | 改了什么 |
|---|---|
| `packages/client/ui-conversation/src/client/skeleton/EmptyHero.tsx` | 重写 Hero：Daniel 标记 + 标题 + 副标题 + 3 示例；删除鲸鱼 SVG、SMIL 变形路径、hover state、`hero.preview` 角标；新增 `onExample` 属性 |
| `packages/client/ui-conversation/src/client/skeleton/HeroShell.module.css` | 新增 `.subtitle` / `.examples` / `.example` / `.exampleText` / `.mark`；删除 `.fish` / `.fishHitbox` / `@keyframes hero-fish-swim` / `.previewBadge` / `.titleGroup`；窄屏一步降级 |
| `packages/client/ui-conversation/src/client/skeleton/prefill.ts` | **新增**：`prefillExampleDraft()`，只认 `setDraft / focus / state` 三个动词（签名里就没有 submit/send） |
| `packages/client/ui-conversation/src/client/skeleton/ConversationContent.tsx` | 从注入里取 `prefillExample`，传给 `<HeroShell onExample>` |
| `packages/client/ui-conversation/src/client/apply.ts` | `conversation.content` 的 inject 新增 `prefillExample`：解析本会话 `SessionInput`（`inputHub.shell(sessionId)`）→ 非 `plain/claimed` 拒绝 → `setDraft` → `focus` |
| `packages/client/ui-conversation/src/client/contract/slots.ts` | `ConversationInjected` 新增 `prefillExample: (phrase: string) => boolean` |
| `packages/client/ui-conversation/src/client/locales.ts` | 8 语言：`hero.headline` 改写、新增 `hero.subtitle` + 3 个 `hero.example.*`、**删除 `hero.preview`** |
| `packages/client/ui-primitives/src/index.ts` | 公开导出 `DANIEL_BOT_MARK` / `DANIEL_BOT_NAME`（图形**复用** `src/daniel-brand.ts`，没有新造） |
| `packages/client/ui-conversation/tests/skeleton.client.spec.tsx` | Hero 测试重写 10 条；4 处旧断言（`探索未至之境` / `预览版`）更新 |
| `packages/client/ui-brand-official/src/client/index.ts` | 只改注释：fallback 从「animated fish」改成「Daniel Bot mark」 |
| `daniel-bot/app/desktop-patches/CHANGES-EMPTY-HERO.md` | 本文 |

没有新增依赖、没有新增包；品牌图形直接用 `packages/client/ui-primitives/src/daniel-brand.ts` 里既有的 `DANIEL_BOT_MARK`（data URI 位图，128×128）。

---

## 3. 组件结构

```tsx
export function HeroShell({ t, renderSlot, onExample, children }: HeroShellProps) {
  return (
    <div className={css.root}>
      <div className={css.stack}>
        <div className={css.headline}>
          <span className={css.markHitbox}>
            {renderSlot('conversation.hero.brand.mark', { size: 34, className: css.mark }, {
              fallback: <HeroMark />,        // <img src={DANIEL_BOT_MARK} width={34} height={34}>
            })}
          </span>
          <span className={css.title}>{t('hero.headline')}</span>
        </div>
        <p className={css.subtitle}>{t('hero.subtitle')}</p>
        <div className={css.examples}>
          {HERO_EXAMPLE_KEYS.map(key => (
            <button key={key} type="button" className={css.example} onClick={() => { onExample(t(key)) }}>
              <span className={css.exampleText}>{t(key)}</span>
            </button>
          ))}
        </div>
        <div className={css.body}>{/* composer 仍挂在本组件外面 */}</div>
      </div>
      {children}
    </div>
  )
}
```

- 品牌槽位 `conversation.hero.brand.mark` **保留**：第三方仍可占位；不占位时 fallback 是 Daniel 标记（不再是鲸鱼）。
- 标记仍是 34px（与槽位 owner 的 `size: 34` 约定一致），圆角 8px，和桌面图标同一视觉语言。
- 示例是真正的 `<button>`：Tab 可达、Enter/Space 可触发、`:focus-visible` 有 token 描边焦点环。

---

## 4. 三个示例 + 预填链路（不发送）

### 4.1 示例话术（zh 逐字）

1. `我这个账号下有几个工作区？`
2. `Halliday 的竞品有哪些？`
3. `找 20 个做智能眼镜测评的 YouTube 红人`

顺序即产品顺序：账号 → 竞品 → 找红人。

### 4.2 预填走公开接口

`apply.ts` 的注入（等价于 `ctx.conversation.input.for(scope)` 拿到的 `SessionInput`）：

```ts
prefillExample: (phrase: string): boolean => {
  if (sessionId === undefined) return false
  const shell = inputHub.shell(sessionId)                 // 本会话的 SessionInput
  if (shell.snapshot.phase !== 'plain' && shell.snapshot.phase !== 'claimed') return false
  return prefillExampleDraft(shell, phrase)               // setDraft → focus
}
```

`prefill.ts` 只借三个动词（**签名里就没有** `submit` / `send`）：

```ts
export interface ExampleDraftTarget {
  setDraft(text: string): void
  focus(): void
  readonly state: { getSnapshot(): { readonly draft: string } }
}

export function prefillExampleDraft(input: ExampleDraftTarget, phrase: string): boolean {
  const text = phrase.trim()
  if (text === '') return false
  let existing = ''
  try { existing = input.state.getSnapshot().draft } catch { existing = '' }
  try {
    input.setDraft(existing.trim() === '' ? text : `${existing}\n${text}`)
  } catch { return false }
  try { input.focus() } catch { /* 未挂载的 composer 拿不到焦点，草稿照样落地 */ }
  return true
}
```

- **没有 DOM 操作**：不 `querySelector`、不模拟键盘、不点发送按钮。
- **不丢用户已输入的内容**：已有草稿时换行追加（与全景地图弹窗的「填进对话」同一口径）；空草稿时直接填入。
- 写完 `focus()`，把光标交回输入框，用户按 Enter 自己决定发不发。
- 提交中（`submitting/sending/adjudicating`）直接拒绝写入，避免和在手提交打架。

---

## 5. 视觉口径

| 项 | 取值 |
|---|---|
| 标记 | 34×34，`border-radius: 8px`，`DANIEL_BOT_MARK` |
| 标题 | 26/32、wt500、`--dsw-alias-label-primary`；窄屏（≤480px）22/28 |
| 副标题 | 14/22、`--dsw-alias-label-tertiary`、居中 |
| 示例卡片 | `1px solid var(--dsw-alias-border-l2)`、`var(--dsw-radius-md)`、`var(--dsw-alias-bg-layer-1)`、`padding: 12px 14px`、文字 13/20 `--dsw-alias-label-secondary` —— 与全景地图弹窗 `.card` 同一套卡片语言 |
| hover | `--dsw-alias-border-l3` + `--dsw-alias-interactive-bg-hover` + `--dsw-alias-label-primary` |
| 焦点 | `1px solid var(--dsw-focus-ring-color, var(--dsw-alias-state-business-primary))`，offset 2 |
| 动效 | **无**：没有 `@keyframes`、没有 `transition`、没有 `animation`；`prefers-reduced-motion` 无需额外分支 |
| 深浅色 | 全表只用 `--dsw-*` token；单测扫描 CSS 源，禁止 `#hex` 与 `rgb()/hsl()` 字面量 |

示例区在 `.stack` 内、输入卡片之上（结构顺序：标题 → 副标题 → 示例 → 的工作区 chip 行 → 输入卡片）；宽屏单列 3 行，长话术 `overflow-wrap: anywhere` 自动换行，不裁切。

---

## 6. 8 语言文案

`hero.preview` 从 8 个字典里全部删除（`satisfies Record<keyof typeof en, string>` 会强制 8 份键集一致，所以少写一份会直接类型报错）。

### 6.1 标题 + 副标题（全文）

| 语言 | `hero.headline` | `hero.subtitle` |
|---|---|---|
| zh | 开始一个新任务 | 说说你想做什么，Daniel 会调用对应能力去完成。 |
| en | Start a new task | Tell Daniel what you want to do, and it will call the right capability to get it done. |
| ja | 新しいタスクを始める | やりたいことを伝えてください。Daniel が適切な機能を呼び出して実行します。 |
| es | Empezar una tarea nueva | Cuéntale a Daniel qué quieres hacer y usará la capacidad adecuada para conseguirlo. |
| fr | Démarrer une nouvelle tâche | Dites à Daniel ce que vous voulez faire : il mobilisera la capacité adaptée pour le réaliser. |
| de | Eine neue Aufgabe starten | Sagen Sie Daniel, was Sie tun möchten – er nutzt die passende Fähigkeit, um es zu erledigen. |
| ru | Начать новую задачу | Расскажите Daniel, что нужно сделать, — он задействует нужную функцию и выполнит задачу. |
| pt | Começar uma nova tarefa | Diga ao Daniel o que você quer fazer — ele aciona a capacidade certa para concluir. |

### 6.2 三个示例（8 语言同口径）

| 语言 | 工作区 | 竞品 | 找红人 |
|---|---|---|---|
| zh | 我这个账号下有几个工作区？ | Halliday 的竞品有哪些？ | 找 20 个做智能眼镜测评的 YouTube 红人 |
| en | How many workspaces do I have on this account? | Who competes with Halliday? | Find 20 YouTube creators who review smart glasses |
| ja | このアカウントにはワークスペースがいくつありますか？ | Halliday の競合はどこですか？ | スマートグラスをレビューする YouTube クリエイターを 20 人探してください |
| es | ¿Cuántos espacios de trabajo hay en esta cuenta? | ¿Quiénes son los competidores de Halliday? | Busca 20 creadores de YouTube que analicen gafas inteligentes |
| fr | Combien d'espaces de travail ai-je sur ce compte ? | Qui sont les concurrents de Halliday ? | Trouve 20 créateurs YouTube qui testent des lunettes connectées |
| de | Wie viele Arbeitsbereiche habe ich in diesem Konto? | Wer sind die Wettbewerber von Halliday? | Finde 20 YouTube-Creator, die Smart Glasses testen |
| ru | Сколько рабочих пространств в этом аккаунте? | Кто конкуренты Halliday? | Найди 20 YouTube-авторов, которые обозревают умные очки |
| pt | Quantos espaços de trabalho há nesta conta? | Quem são os concorrentes da Halliday? | Encontre 20 criadores do YouTube que avaliam óculos inteligentes |

> 6 个非中英语言是**人工按同口径写**（不是机翻直出），业务词 `Halliday` / `YouTube` / `20` 在各语言里保持原样，便于用户直接拿去问。

---

## 7. 测试：改了什么、为什么

### 7.1 Hero 测试整体重写（10 条）

旧测试 `renders the English preview badge through the hero locale seat` 断言的是**被删掉的东西**（`Into the Unknown` / `Preview`），所以整条替换。新 10 条：

1. 渲染 Daniel Bot 产品标记（`img[src^="data:image/png;base64,"]`），且**没有 svg**（鲸鱼不再出现）；品牌槽位 owner 仍拿到 `size: 34` 与 `className`；
2. zh 标题 `开始一个新任务` + 副标题；`探索未至之境`、`预览版` 都查不到；
3. en 标题 `Start a new task` + 副标题；`Into the Unknown`、`Preview` 都查不到；
4. 恰好 3 个示例按钮，话术逐字匹配；
5. 点示例 → `onExample` 收到该句话术（只调一次）；
6. `prefillExampleDraft` 只走 `setDraft` + `focus`，**不调 submit / send**（见 §7.3 原文）；
7. 已有草稿时**换行追加**，不覆盖用户已输入内容；
8. 挂真实组件树点示例：草稿进机器、`phase` 仍是 `plain`、`submit` 与 `sink` 均未被调用；
9. CSS 源里没有 `#hex` / `rgb()` / `hsl()` 字面量（深浅色只靠 token）；
10. CSS 源里没有 `animation:` / `transition:` / `@keyframes`（无动画，天然满足 reduced-motion）。

### 7.2 旧断言更新（4 处，其他测试文件里）

| 位置 | 改前 | 改后 |
|---|---|---|
| `skeleton.client.spec.tsx`「hero phase」 | `getByText('探索未至之境')` + `getByText('预览版')` | `getByText('开始一个新任务')` + `queryByText('预览版')` **为 null** |
| 「keeps a rejected first prompt engaging…」 | `queryByText('探索未至之境')` 为 null | `queryByText('开始一个新任务')` 为 null |
| 「startup auto-selection…」 | `getByText('探索未至之境')` | `getByText('开始一个新任务')` |
| 测试夹具 `mount()` | 草稿固定 `'ordinary draft'` | 新增 `draft` 选项（默认不变），hero 用例传 `''` |

### 7.3 「点了不发送」的断言原文

```ts
it('prefills the draft through setDraft + focus, never submit or send', () => {
  const input = {
    setDraft: vi.fn<(text: string) => void>(),
    focus: vi.fn(),
    submit: vi.fn(),
    send: vi.fn(),
    state: { getSnapshot: () => ({ draft: '' }) },
  }
  expect(prefillExampleDraft(input, '  Halliday 的竞品有哪些？  ')).toBe(true)
  expect(input.setDraft).toHaveBeenCalledExactlyOnceWith('Halliday 的竞品有哪些？')
  expect(input.focus).toHaveBeenCalledOnce()
  expect(input.submit).not.toHaveBeenCalled()
  expect(input.send).not.toHaveBeenCalled()
})

it('clicking a hero example writes the session draft and sends nothing', () => {
  const b = mount(sessionSnapshotOf({ blank: true }), undefined, undefined, { draft: '' })
  const submit = vi.spyOn(b.wiring, 'submit')
  fireEvent.click(b.view.getByRole('button', { name: zh['hero.example.competitors'] }))
  expect(b.wiring.state.getSnapshot().draft).toBe('Halliday 的竞品有哪些？')
  expect(b.wiring.state.getSnapshot().phase).toBe('plain')
  expect(submit).not.toHaveBeenCalled()
  expect(b.sink).not.toHaveBeenCalled()
})
```

第二条是**真机器**（`SessionInputShell`）上的断言：草稿进了 input 机器、提交栅栏 `phase === 'plain'`、`submit` 方法没被调用、默认 sink（真正发送的出口）也没被调用。

---

## 8. 验证输出（真实终端）

### 8.1 本包类型检查

```
$ pnpm exec tsc -b packages/client/ui-conversation/tsconfig.client.json
EXIT:0
```

### 8.2 客户端 bundle

```
$ pnpm -C packages/client/ui-conversation run bundle
✔ [@deepseek-ai/dsh-client-ui-conversation/client] Build complete in 187ms
EXIT:0
```

### 8.3 桌面构建

```
$ pnpm -C apps/desktop run build
✓ built in 429ms
DESKTOP BUILD EXIT:0
```

### 8.4 单测（本包全量）

```
$ pnpm exec vitest run packages/client/ui-conversation
 Test Files  54 passed (54)
      Tests  881 passed (881)
```

Hero 专项：

```
$ pnpm exec vitest run packages/client/ui-conversation/tests/skeleton.client.spec.tsx -t "Hero chrome" --reporter=verbose
 Tests  10 passed | 37 skipped (47)
```

### 8.5 渲染文本（zh，真实渲染结果）

用临时探针（已删除）渲染 `<HeroShell>` 的可见文本：

```
--- zh ---
开始一个新任务
说说你想做什么，Daniel 会调用对应能力去完成。
我这个账号下有几个工作区？
Halliday 的竞品有哪些？
找 20 个做智能眼镜测评的 YouTube 红人
--- en ---
Start a new task
Tell Daniel what you want to do, and it will call the right capability to get it done.
How many workspaces do I have on this account?
Who competes with Halliday?
Find 20 YouTube creators who review smart glasses
```

### 8.6 聚合 `tsc -b tsconfig.client.json`：**非 0，但错误不在本 ticket**

```
$ pnpm exec tsc -b tsconfig.client.json
packages/client/ui-workspace/tests/session-actions.client.spec.tsx(148,28): error TS2741:
  Property 'requestSessionRemoval' is missing … required in type 'Omit<ArchiveSessionInjected, "hooks">'
（同文件 151 / 158 / 161 行同样错误，共 4 条）
TSC EXIT:1
```

- 4 条全部来自 `packages/client/ui-workspace/tests/session-actions.client.spec.tsx`，是**同一工作区里另一个并行改动**（会话移除功能）留下的半成品：`ui-workspace/src` 已加 `requestSessionRemoval` / `removeSession`，它的测试还没跟上。
- 证据：该测试文件 mtime `Nov 3 00:26:42`、`ui-workspace/src/client/contract/slots.ts` mtime `00:23:51`；我 00:24 第一次跑聚合时，`ui-workspace/src/client/index.ts` 还报过 `Cannot find name 'runningSessionIds'`（现在是干净的），说明对方正在同一棵工作树上改。
- 本 ticket **未改** `packages/client/ui-workspace` 任何文件；本包与 `ui-primitives` 的单包类型检查均为 0。
- 聚合 tsc 需要在对方补完 `ui-workspace` 测试后重跑一次才能全绿。

---

## 9. 未做 / 边界

1. **没有改 `apps/web` 的上游 e2e**：`apps/web/tests/{startup-auto-selection,session-replay-reload,lifecycle-chrome,connection-recovery,hmr-live}.e2e.ts` 里仍写着 `Into the Unknown`，其中 `startup-auto-selection` 还断言 hover 时鲸鱼 SVG 的 `animationName !== 'none'`——这两处在新 Hero 下必然失效（标记变位图、动效删除）。这些是 Harness Web 前端的 e2e（需要 Playwright + 构建后的 web 产物，不在本 ticket 的四道门禁内），且本仓库对 `apps/web` 的历史改动为 **0 个文件**，所以按既有边界**不纳入本次改动**；如果要跑那套 e2e，需要单独开票把定位器改成 `Start a new task` 并把「鲸鱼摆动」断言换成「标记是位图、无动画」。
2. **没有打包**（按纪律）：只跑类型检查 / bundle / 桌面构建 / 单测。
3. 桌面端要在真实窗口里看到效果，需要重启开发态应用（`ui-conversation` 的 `lib/client.js` 已重新 bundle）。
