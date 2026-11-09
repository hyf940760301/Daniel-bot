# CHANGES · 应用内登录接入 Daniel 账号（2026-11-02）

> 工作目录：`/tmp/dsh-build/dsh-src`
> 工具链：`export PATH="/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/build/toolchain/node24/bin:$PATH"`
> 状态：**代码 + 类型 + 构建 + 单测已验；GUI 未真机点击**（本会话没有可交互的桌面会话）→ 见 §7
> 范围：只改「账号身份」这一条链（主进程 IPC / preload / 账号 UI），**不打包**。

---

## 0. 一句话

应用内账号状态从「DeepSeek 平台账号」切换为「**Daniel 会话**」：左下角账号菜单与设置页账号卡都显示 Daniel 邮箱，菜单/卡片里的「登录」按钮**只**调用桌面主进程打开 Daniel 原生登录窗（复用启动闸门那套 `requireDanielSession`），不再有任何入口把用户送到 `platform.deepseek.com`；「退出登录」删掉 `$DANIEL_HOME/session/session.json`。没有 `window.danielAuth` 的纯 web 预览保持原 DeepSeek 逻辑不变。

---

## 1. 实现路径

### 1.1 主进程（`apps/desktop/src/`）

| 新文件 | 作用 |
|---|---|
| `daniel-auth-api.ts`（新，36 行） | 三端共用：通道名 `dsh-daniel-auth:status / sign-in / sign-out`、`DanielAccount`、`DanielAuthApi` 类型。**不含任何 URL**，renderer 拿不到可跳转地址。 |
| `daniel-auth.ts`（新，114 行） | 主进程实现：`readDanielAccountStatus()` / `signInDanielAccount()` / `signOutDanielAccount()` / `installDanielAuthIpc()`。 |

关键决定（与需求原文的偏差，先说明）：

- **`signIn()` 复用 `requireDanielSession()`**（需求指定）。因此它继承闸门的全部语义：无 session → 开原生窗；已有有效 session → 直接返回、不开窗；已有 session 但服务端拒绝 → 清 session 后开窗；网络不可达 → 开窗并给「网络不可达」提示。同一时刻只允许一个登录尝试（`pendingSignIn` 合并并发调用），关窗返回 `null`（账号状态不变）。
- **`status()` 的 email 从哪来**：`session.json` 与 Daniel CLI 共享，里面**只有** `{cookie, ts}`，没有 email。为满足「status 读文件即返回 `{email}`」且不依赖网络，在 session 文件同目录新增身份缓存 `$DANIEL_HOME/session/account.json`（0600，只存 `{email}`）：
  - 登录成功（原生窗 `submit` 成功）→ `writeDanielAccountEmail(account.email)`；
  - 启动闸门校验通过（`requireDanielSession`）→ 缓存；
  - 「重新校验已保存的登录」成功 → 缓存；
  - 缓存缺失（例如 session 是 CLI 自己写的）→ `status()` 用现有 `auth.me` 读取一次并缓存；**服务端不可达时不删 session**，返回 `{ email: '' }`（仍算已登录，UI 用「已登录 Daniel」兜底）。
  - `clearDanielSession()` 同时删缓存，保证「session 没了 = 身份没了」。
- **不重写协议**：`auth.login` / `auth.me`、错误分类（credential/network/server/mismatch）、8s/30s 超时、tRPC 信封解析全部沿用 `daniel-login.ts`；只把 `auth.me` 的读取抽成 `readDanielAccount()` 供两处复用，并把 `verifyDanielSession()` 的返回值从枚举扩成 `{ state, email? }`（原枚举语义不变）。
- **`assertProductSender` 兜底**：三个 handler 都先过主窗口 + 主 frame 校验，与其它 `dsh-desktop:*` IPC 一致。

### 1.2 preload（`apps/desktop/src/preload-app.ts`）

在 `dsh-app://app` 主 frame 内 `contextBridge.exposeInMainWorld('danielAuth', { status, signIn, signOut })`。嵌套 frame（侧栏预览等）不暴露，也就不会拿到账号身份。

### 1.3 客户端（`packages/client/ui-settings-account/src/client/`）

| 文件 | 改动 |
|---|---|
| `daniel-auth.ts`（新，45 行） | `window.danielAuth` 的**结构类型 + `declare global`**（不用 any）；`readDanielAuthBridge()` 只接受三个方法齐全的对象，半截 stub 视为不存在。 |
| `AccountSection.tsx` | `AccountSnapshot` 新增 `daniel?: { bridge, email? }`；`AccountSectionInjected` 新增可选 `danielSignIn` / `danielSignOut`。渲染优先级：bridge 存在 → Daniel 卡片（未登录＝原 signed-out 卡，按钮调 `danielSignIn`；已登录＝邮箱 +「退出登录」）；bridge 不存在 → 原 DeepSeek 逻辑（signed-out 卡与 `start` 完整恢复）。 |
| `AccountMenu.tsx` | 恢复「登录」菜单项（`IconUserOutlineMedium`）；`onSelect`：`signin` → 有 bridge 走 `danielSignIn`，否则走原 `start`（`SignInDialog` 仅在无 bridge 时渲染）；`signout` → 有 bridge 直接 `danielSignOut`（不查平台任务、不弹平台确认框），否则原 `SignOutDialog`。显示名：bridge 存在时用 Daniel 邮箱（空则「已登录 Daniel」），否则原 profile 名。 |
| `index.ts` | apply 时读一次 `readDanielAuthBridge()`；有 bridge 则以 `daniel.status()` 为首个账号状态，并把它并入 operations（`danielSignIn` / `danielSignOut` 成功后立即 publish）。`settings.section` 的注册条件从「仅 `credential-stored`」改为「Daniel bridge 存在，或平台账号已登录」——否则未登录时设置页根本不会出现账号卡。 |
| `locales.ts` | 新增 `danielSignedIn`（8 语言）。其余文案复用既有 `settingsSignedOutTitle/Description`（上一轮已改为 Daniel Bot 措辞）。 |

### 1.4 类型

`window.danielAuth` 用 `declare global` 声明在客户端包内；主进程侧另有同名结构的 `DanielAuthApi`（`daniel-auth-api.ts`），两边不改同一份代码，也不互相 import。

---

## 2. 改动文件清单

新增（3）：

- `apps/desktop/src/daniel-auth-api.ts`
- `apps/desktop/src/daniel-auth.ts`
- `packages/client/ui-settings-account/src/client/daniel-auth.ts`

修改（7）：

- `apps/desktop/src/main.ts`（+9）
- `apps/desktop/src/preload-app.ts`（+12）
- `apps/desktop/src/daniel-login.ts`（身份缓存 + `auth.me` 复用，+153/−? 含注释）
- `packages/client/ui-settings-account/src/client/AccountSection.tsx`（+82）
- `packages/client/ui-settings-account/src/client/AccountMenu.tsx`（+39/−?）
- `packages/client/ui-settings-account/src/client/index.ts`（+32）
- `packages/client/ui-settings-account/src/client/locales.ts`（+8 行，每语言 1 键）

测试：

- `packages/client/ui-settings-account/tests/account.client.spec.tsx`（+86：4 条 Daniel UI 用例；原 signed-out 菜单用例改为「设置/反馈/登录」）
- `packages/client/ui-settings-account/tests/apply.client.spec.ts`（+25：1 条插件级用例，验证 `status()` 首次读、`signIn` 后 publish、`signOut` 后 publish）
- `packages/client/ui-settings-account/tests/expected/menu-signed-out-{en,zh}.txt`（恢复 `Sign in` / `登录`）

**没有**新增依赖、没有改打包配置（新文件由 `main.ts` / `preload-app.ts` import，现有 tsdown 入口自动打进 `lib/main.js`、`lib/preload-app.cjs`）、没有动更新开关。

---

## 3. 需求 → 实现对照

| 需求 | 实现 | 位置 |
|---|---|---|
| 应用内账号 = Daniel 会话；已登录显示邮箱 + 头像占位 | `AccountMenu` 用 `daniel.email` 作 label、`AccountAvatar` 无图时用内置 User 图标；`AccountSection` 显示邮箱 +「已登录 Daniel」 | `AccountMenu.tsx:38-49`、`AccountSection.tsx:186-200` |
| 菜单有「退出登录」 | 已登录时 `signout` 项 → `danielSignOut()`（删 session 与身份缓存） | `AccountMenu.tsx:88-97` |
| 未登录时菜单有「登录」，点击弹桌面 Daniel 登录窗 | `signin` 项 → `danielSignIn()` → IPC `dsh-daniel-auth:sign-in` → `requireDanielSession()` 开原生窗 | `AccountMenu.tsx:90,96`；`daniel-auth.ts:60-87` |
| 登录成功后 UI 立即变已登录 | `openDanielLoginWindow` 关窗（成功后 ~400ms）→ promise resolve → `publishDaniel(email)` → React 重渲染 | `index.ts:293-298` |
| 点击登录入口绝不跳 `platform.deepseek.com` | Daniel 分支只走 IPC；`SignInDialog`（唯一渲染平台授权链接的组件）在 bridge 存在时不渲染 | `AccountMenu.tsx:100` |
| 设置页恢复卡片 | Daniel 未登录：原 signed-out 卡（标题/描述/按钮）回归；已登录：邮箱 +「退出登录」 | `AccountSection.tsx:171-201` |
| 纯 web 回退原逻辑 | `readDanielAuthBridge()` 返回 undefined 时，`signedIn`、菜单项、`SignInDialog`、`start()` 全部走原路径 | `index.ts:56-75`；`AccountMenu.tsx:41,96-98,100`；`AccountSection.tsx:205-220` |
| 不删「模型 Key」设置 | `settings.models.*`、`AccountOnboarding`、onboarding 配置未改 | — |

---

## 4. 验收（真实输出）

### 4.1 三条命令

```bash
$ node_modules/.bin/tsc -b tsconfig.client.json
TSC_EXIT=0                      # 无任何诊断输出

$ pnpm -C apps/desktop run build
BUILD_EXIT=0                    # 关键尾部见下

$ pnpm --dir . exec vitest run packages/client/ui-settings-account/tests
VITEST_EXIT=0
 Test Files  27 passed (27)
      Tests  372 passed (372)
   Duration  21.72s
```

`apps/desktop` 构建尾部（`/tmp/dsh-build/desktop-build-final.log`）：

```
✔ Build complete in 110ms
[ESM] lib/main.js  874.71 kB │ gzip: 221.18 kB
[CJS] lib/preload-app.cjs  130.31 kB │ gzip: 34.56 kB
✓ 34 modules transformed.
lib/welcome/welcome.js  229.22 kB │ gzip: 70.07 kB
✓ built in 377ms
```

顺带回归（不在三条硬约束内）：

```bash
$ pnpm --dir . exec vitest run apps/desktop/tests/daniel-login.spec.ts
 ✓ 4 tests passed
```

### 4.2 平台 URL 扫描

```bash
$ grep -rn "platform.deepseek.com\|authorize" packages/client/ui-settings-account/src/client | grep -v "\.d\.ts"
```

结果：**17 行命中，全部是标识符 `authorizeUrl`**（`browser-login.ts` / `SignInDialog.tsx` / `authorize-url.ts` / `AccountSection.tsx` / `index.ts`），**字面量 `platform.deepseek.com` 命中数 = 0**。

为什么还剩这些：

- `authorizeUrl` 是 **Host 返回给纯 web 的 DeepSeek OAuth 地址**，属于「无 `window.danielAuth` 时回退原逻辑」的保留路径；桌面端（bridge 存在）不渲染 `SignInDialog`，`start()` 也不会被账号入口触发，所以桌面点击任何登录入口都到不了它。
- `AccountSection.tsx:237` 的 `attempt.authorizeUrl` 只在「平台账号登录尝试进行中」时出现，桌面 Daniel 模式不会产生 attempt。

### 4.3 测试覆盖（新增 5 条）

| 用例 | 断言 |
|---|---|
| `shows the Daniel email and signs out from the Settings card`（en/zh） | 卡片出现 `ada@example.com`；状态文案 = `danielSignedIn`；无「用量」链接；点「退出登录」→ `danielSignOut` 调用 1 次 |
| `opens the native Daniel sign-in from the signed-out Settings card`（en/zh） | 未登录卡可见；点「登录」→ `danielSignIn` 调用 1 次；页面无 `platform.deepseek.com` 链接 |
| `signs in to Daniel from the sidebar menu without a Platform dialog`（en/zh） | 菜单项 = [设置, 反馈, 登录]；点登录 → `danielSignIn` 1 次；不出现 `SignInDialog`（`role=dialog` 为 null） |
| `labels the launcher with the Daniel email and signs out from its menu`（en/zh） | 触发器文本含邮箱；菜单项 = [设置, 反馈, 退出登录]；点退出 → `danielSignOut` 1 次且不弹平台确认框 |
| `takes the account identity from the Desktop Daniel bridge`（插件级，`apply.client.spec.ts`） | 装 `globalThis.danielAuth` → apply 后 `status()` 被读 1 次且快照为 `{bridge:true,email:null}`；`danielSignIn()` 后邮件发布；`danielSignOut()` 后回到 null；未登录时设置页 section 仍注册（能给出登录卡） |

---

## 5. 三处关键改动（文件:行 → 改前 → 改后）

### 5.1 `apps/desktop/src/main.ts:826-832`（新增账号 IPC 安装）

```ts
// 改前：应用内没有任何账号 IPC，主窗口只能读 Host 的 DeepSeek 账号流。

// 改后
  // The in-app account surfaces read, sign in, and sign out through the same
  // session the startup gate owns; every call must come from the product window.
  const disposeDanielAuth = installDanielAuthIpc({
    assertSender: assertProductSender,
    localeId: () => currentDesktopLocale().id,
  })
  app.on('will-quit', () => { disposeDanielAuth() })
```

### 5.2 `apps/desktop/src/preload-app.ts:17-23, 118`（暴露 `window.danielAuth`）

```ts
// 改前：只有 dshDesktop / dshPlatform / dshOnboarding / __DSH_* 这几组桥，没有账号桥。

// 改后
function createDanielAuthApi(): DanielAuthApi {
  return {
    status: () => ipcRenderer.invoke(DANIEL_AUTH_IPC.status) as Promise<DanielAuthAccount>,
    signIn: () => ipcRenderer.invoke(DANIEL_AUTH_IPC.signIn) as Promise<DanielAuthAccount>,
    signOut: () => ipcRenderer.invoke(DANIEL_AUTH_IPC.signOut) as Promise<void>,
  }
}

// 仅在 dsh-app://app 的主 frame 内：
  if (process.isMainFrame) contextBridge.exposeInMainWorld('danielAuth', createDanielAuthApi())
```

### 5.3 `packages/client/ui-settings-account/src/client/AccountMenu.tsx:88-101`（恢复登录入口，改接 Daniel）

```tsx
// 改前（上一轮删掉了入口）
        // Daniel Bot 的身份由桌面登录闸门承担，应用内不再提供平台登录入口。
        ...(signedIn ? [{ id: 'signout', ... }] : []),
      ]}
      onSelect={(id) => {
        ...
        else void requestSignOut()
      }} />

// 改后
        // Desktop offers the native Daniel window here; a plain browser offers its Platform dialog.
        ...(signedIn ? [{ id: 'signout', label: t('signOut'), icon: <LogoutIcon />, disabled: busy }]
          : [{ id: 'signin', label: t('signIn'), icon: <IconUserOutlineMedium size={16} /> }]),
      ]}
      onSelect={(id) => {
        ...
        else if (id === 'signin') { if (danielBridge) beginDanielSignIn(); else beginSignIn() }
        else if (danielBridge) endDanielSession()
        else void requestSignOut()
      }} />
    {!danielBridge && account.loginVisible && !account.onboarding && <SignInDialog ... />}
```

### 5.4（补充）`AccountSection.tsx:171-201`（设置页卡片）

```tsx
// 改前
  // Daniel Bot authenticates at the desktop gate; ...
  if (!signedIn && !active) return null

// 改后：bridge 存在 → 未登录给「登录」卡（调 danielSignIn）、已登录给「邮箱 + 退出登录」卡（调 danielSignOut）；
// bridge 不存在 → 原 signed-out 卡（调 start）+ 原平台卡片。
  if (danielBridge) {
    if (!danielSignedIn) return (/* 原 signed-out 版式，按钮 → danielSignIn */)
    return (/* 身份卡：email + 「已登录 Daniel」 + 退出登录 → danielSignOut */)
  }
  if (!signedIn && !active) return (/* 原平台 signed-out 卡，按钮 → start */)
```

---

## 6. 没有 Daniel 会话时，用户会看到什么

1. **应用内（运行中，例如 session 被手动删掉）**：
   - 左下角账号按钮回到「更多（⋯）」形态；菜单 = 设置 / 意见反馈 / **登录**。
   - 设置 → 账号，显示「当前未登录 Daniel Bot 账号 / 登录 Daniel Bot 账号获取专属 API Key」+ 主按钮「登录」。
   - 点「登录」→ 弹出**桌面原生 Daniel 登录窗**（440×560，独立窗口，密码只用于本次换取会话）；登录成功后窗自动关闭，左下角与设置页立即变成「邮箱 + 退出登录」。关闭登录窗则什么都不变。
2. **下次启动**：启动闸门照旧先跑（无 session → 登录窗；不登录就不建主窗口、不起 Host）。也就是「应用内可以登出，但下次进来仍要先登录」。
3. **纯 web 预览**（无桌面壳）：完全看不到 Daniel 入口，仍是原「登录 DeepSeek 账号 / 添加 API Key」流程。
4. **已登录时**：左下角显示 Daniel 邮箱 + 用户图标头像；设置页显示同一邮箱、状态「已登录 Daniel」、按钮「退出登录」。

---

## 7. 边界、已知取舍、待真机验证

**取舍 1：桌面账号页不再显示 DeepSeek 钱包（充值余额 / 赠送余额 / 用量 / 充值链接）。**
理由：这些数据属于另一个账号（平台账号），在 Daniel 身份下会显示成「未登录 / 余额不可用」，与「账号 = Daniel」冲突；Daniel 卡片按需求只放邮箱 + 退出登录。纯 web 构建完整保留。若需要把「用量 / 充值」作为纯链接放回 Daniel 卡片，加一行即可（不影响登录语义）。

**取舍 2：设置页导航标题仍是「账号与余额」。**
桌面下已无余额行，文案略超前。改 `nav` 会牵动 8 语言与 web 侧文案，本轮未动，建议后续统一为「账号」。

**取舍 3：模型凭据 onboarding（`settings.models.*` / `AccountOnboarding`）保留原平台流程。**
它属于「模型 Key」配置，不在账号身份这条链上；需求也明确要求不动。因此严格意义上应用内**仍有**一条平台授权入口（设置 → 模型），但账号菜单 / 账号卡 / 模型报错 toast 均不会把用户送过去。

**未做**：打包（按要求停在验证后）；GUI 真机点击（本会话无桌面会话）。

**待真机验证清单**（请在有图形会话的机器上跑一次）：

1. 启动 → 用 Daniel 账号登录 → 左下角是否显示邮箱、设置页是否显示邮箱 + 退出登录。
2. 删掉 `$DANIEL_HOME/session/session.json`（应用运行中）→ 重启 UI/切换设置页 → 是否出现「登录」入口（注：`status()` 只在 apply 时读一次，运行中删文件后 UI 不会自己变；这是预期，见下条）。
3. 在未登录态点「登录」→ 是否弹原生窗；登录成功 → UI 是否自动变已登录（无需刷新）。
4. 点「退出登录」→ `$DANIEL_HOME/session/session.json` 是否消失；UI 是否变未登录；再点「登录」是否能重新登录。
5. 全程观察是否出现任何 `platform.deepseek.com` 页面。

> 备注（实现事实）：账号状态是**每次客户端 apply 读一次 + 每次登录/登出后刷新**，没有做跨窗口实时推送。运行中由外部删除 session 文件时，UI 不会自动翻转，重开窗口或再次登录/登出后才会同步。若需要「外部删文件也实时反映」，可再加一条 `fs.watch` → `webContents.send` 的推送通道。
