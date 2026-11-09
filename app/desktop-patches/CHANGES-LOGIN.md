# CHANGES · 第三、四组（登录页 + 关闭更新）

> 补丁：`daniel-bot/app/desktop-patches/0003-login-and-update.patch`（62 KB，14 个文件，+1261 / −25）
> 基线：`/tmp/dsh-work-2`（已应用 0001 的那份工作树）
> 状态：**代码 + 构建 + 单测已验；GUI 未真机点击**（本机没有可交互的桌面会话）→ 见 §4「待用户真机验证」

---

## 0. 一句话

启动先登录 Daniel 账号：登录窗口是**原生 BrowserWindow（独立窗口，不是 DSH 内页面）**，登录成功前不创建主窗口、不启动 Host；成功后把 `app_session_id` 写到 `$DANIEL_HOME/session/session.json`（文件 0600 / 目录 0700），下次启动用 `auth.me` 校验通过就跳过登录。同时把更新链路（自动检查、聚焦/唤醒检查、菜单「检查更新…」、强制更新策略轮询）**默认全部关死**，只留一个环境变量开关 `DANIEL_BOT_ALLOW_UPDATE=1` 便于将来恢复。

---

## 1. 第三组：登录页

### 1.1 启动时序（改在 `apps/desktop/src/main.ts:384`）

```
app.whenReady → main()
  ├─ installDanielHomes()                      ← 0001 已有，定义 $DSH_HOME / $DANIEL_HOME
  ├─ desktopUpdatesAllowed()                   ← 第四组的开关（读一次）
  ├─ await requireDanielSession(...)           ← 【新】账号闸门，见下
  │    ├─ 无 session                → 打开登录窗口
  │    ├─ 有 session + auth.me 通过 → 直接返回（跳过登录）
  │    ├─ 有 session + 服务端拒绝   → 删掉旧 session → 打开登录窗口
  │    └─ 有 session + 网络不可达   → 打开登录窗口，并给出「网络不可达」提示 + 「重新校验」按钮
  │         （不把「连不上」误判成「密码错」，也不静默放行）
  ├─ 返回 undefined（用户关窗）    → app.quit() + return（不建窗口 / 不起 Host）
  └─ 返回 {email} → 继续原有启动流程：readDesktopSettings → … → createMainWindow() → reconcileBackend()
```

关键点：闸门位于 `main()` 的**最前面**，早于 `createMainWindow()`（main.ts 末尾）与 `reconcileBackend()`（Host 启动）。所以「登录成功才创建/显示主窗口」是结构性的，而不是靠隐藏窗口做到的。

### 1.2 新增文件

| 文件 | 作用 |
|---|---|
| `apps/desktop/src/daniel-login.ts`（新，526 行） | 主进程：session 文件读写（0600/0700、原子 rename、回读校验）、`auth.login` / `auth.me` 调用、网络错误分类、登录窗口创建与 IPC、启动闸门 `requireDanielSession()` |
| `apps/desktop/src/daniel-login-api.ts`（新） | 三处共用：IPC 通道名、失败原因枚举（`credential / network / server / mismatch / invalid`）、中英文文案、页面可调用的 API 类型 |
| `apps/desktop/src/preload-daniel-login.ts`（新） | 沙箱 preload：`contextBridge.exposeInMainWorld('danielLogin', …)`，只暴露 `submit / retryStored / cancel / onSucceeded`，密码只经 `submit` 交给主进程 |
| `apps/desktop/renderer/daniel-login.html`（新） | 登录页（本地文件，CSP 为 `default-src 'none'`，无任何远端资源） |
| `apps/desktop/renderer/daniel-login.css`（新） | 与壳一致的材质：窗口透明 + 平台毛玻璃、Montserrat 品牌字、48px 输入框 / 44px 按钮、浅深色自动跟随 |
| `apps/desktop/renderer/daniel-login.js`（新） | 纯 DOM 逻辑：填文案、提交、错误显示、成功后禁输入；**提交后立即清空密码框** |
| `apps/desktop/tests/daniel-login.spec.ts`（新） | 4 条单测：落点路径、0600/0700、原子覆盖、非 Daniel cookie 拒绝、清理 |

改动的既有文件：`main.ts`（闸门 + 更新开关）、`tsdown.config.ts`（新增 preload 打包入口）、`scripts/electron-builder-config.mjs`（把 `lib/preload-daniel-login.cjs` 打进安装包）。

### 1.3 需求 → 实现对照

| 需求 | 实现 | 位置 |
|---|---|---|
| ① 独立原生窗口、风格与壳一致 | `new BrowserWindow({ width:440, height:560, resizable:false, show:false, titleBarStyle:'hidden', vibrancy:'menu'(mac)/acrylic(win), sandbox:true })`，页面 `renderer/daniel-login.html` 用 `loadFile` 加载；配色/字重/圆角与 welcome 面同源 | `daniel-login.ts:362`（`danielLoginWindowOptions`）、`:408`（`new BrowserWindow`）、`:490`（`window.show()`） |
| ② 账号密码 → `POST /api/trpc/auth.login`，body `{"json":{"email","password"}}`；失败显示服务端 message（**密码错是 HTTP 500**） | `loginDanielAccount()` 走 `net.request`（Electron 自带，走系统代理/TLS）；**不看状态码定性质**：非 2xx 一律先解析 tRPC 错误信封里的 `error.json.message`，再用正则判「凭据类」→ `credential`，否则 `server`；页面直接显示该原文 | `daniel-login.ts:275`（login）、`:200` 附近 `trpcMessage()`/`isCredentialMessage()` |
| ③ 成功后 cookie 写入 `$DANIEL_HOME/session/session.json`，0600，目录 0700 | `writeDanielSession()`：`mkdirSync(…,0o700)` + `chmod 0700`；写 `file.tmp-<pid>`（mode 0600）→ `rename` → 再 `chmod 0600` → 回读比对 cookie → 断言 `mode & 0o777 === 0o600`（Windows 无 POSIX 位，跳过断言） | `daniel-login.ts:94`（路径）、`:122-144`（写入） |
| ④ 下次启动 session 有效则跳过，失效则回登录页 | `requireDanielSession()` 先读盘 → `GET /api/trpc/auth.me`（8s 超时）；2xx 且有 email → `valid`；401/403 或 `code=UNAUTHORIZED` → `invalid`（**删文件**后回登录页）；连不上 → `unreachable`（不算失效，回登录页并给网络提示 + 「重新校验」） | `daniel-login.ts:335`（`verifyDanielSession`）、`:506`（`requireDanielSession`） |
| ⑤ 登录成功才创建/显示主窗口，失败不进主界面 | 闸门在 `main()` 最前面；返回 undefined 时 `app.quit(); return`，此时 `mainWindow` 尚未创建、Host 未启动 | `main.ts:386-398` |
| ⑥ 网络不可达要给明确提示（不能说成密码错） | 传输层异常 → `DanielAuthError(..., 'network')`；页面遇到 `failure==='network'` **只显示网络文案**（覆盖主进程内部细节）；超时与不可达同一分支 | `daniel-login.ts:286-292`；`renderer/daniel-login.js:84` |
| ⑦ 不把密码/会话值写进日志 | 密码只存在于 `submit` 的实参 → `JSON.stringify` → 请求体，函数返回即丢弃；会话 cookie 只在 `writeDanielSession` 的参数与请求头里出现；日志只有三类**无值**事实：`stored session was rejected`、`could not be verified (network unreachable)`、`skipped by DANIEL_BOT_SKIP_LOGIN=1` | `daniel-login.ts:519-524`、`:452`（失败日志只打 `error.message`，不含凭据） |

补充：`session.json` 的格式与 Daniel CLI 完全一致（`{"cookie":"app_session_id=<JWT>","ts":<epoch>}`），因为 `$DANIEL_HOME` 是 CLI / 插件 / 壳共用的落点——**登录一次，DSH 里的 daniel 插件直接复用同一份会话**，不需要额外桥接。

### 1.4 复用而非重写

`daniel-bot/app/src/lib/auth.js`（`net.request` 封装、set-cookie 解析、tRPC 信封解析、`auth.me` 回读邮箱防串号、HTTP 500=密码错的处理）与 `app/src/lib/session.js`（原子写、0600、回读校验）是按原逻辑移植的，只做了三件事：TS 类型化、把「网络/超时」拆成独立失败原因给 UI 用、把结果改成页面可读的 `{ok, failure, message}`。

---

## 2. 第四组：关闭更新

### 2.1 开关

新增 `apps/desktop/src/update-gate.ts`：

```ts
export const DANIEL_ALLOW_UPDATE_ENV = 'DANIEL_BOT_ALLOW_UPDATE'
export function desktopUpdatesAllowed(env = process.env): boolean {
  return env[DANIEL_ALLOW_UPDATE_ENV]?.trim() === '1'     // 只有显式 1 才开
}
```

默认（不设变量）= 关。设 `DANIEL_BOT_ALLOW_UPDATE=1` = 恢复官方那套行为（含强制更新策略）。

### 2.2 被门控的入口（5 处 + 1 处纵深）

| 入口 | 处理 | 位置 |
|---|---|---|
| 菜单「检查更新…」 | 连分隔符一起从菜单模板里条件展开；关闭时菜单里根本没有这一项 | `main.ts:1106-1110` |
| 手动检查（菜单 / Web 状态按钮 `DESKTOP_IPC.updatesOpen`） | `openUpdatePrompt()` 首行 `if (!updatesAllowed) return Promise.resolve()` —— 下载/安装确认流程一并不可达 | `main.ts:937` |
| 定时检查 + 聚焦检查 + 唤醒检查 | 三者都走 `automaticCheck()`，首行 `if (!updatesAllowed) return`；`updateSchedule` 从不被唤醒，因此不会装定时器 | `main.ts:1058` |
| 强制更新策略（轮询远端 + 阻塞界面 + 测试登录弹窗） | `if (policyConfig !== undefined && updatesAllowed)` —— 关闭时 `mandatoryPolicy`/`mandatoryUI` 根本不构造，`isMandatory()` 恒 false | `main.ts:1456` |
| `electron-updater` 本体 | 不再在模块顶层取 `autoUpdater`；改为 `releaseFeedUpdater()` 里 `desktopUpdatesAllowed() ? electronUpdater.autoUpdater : undefined`。关闭时 updater 为 undefined：不挂监听、不设 channel、`check/download/install` 直接返回，`doCheck()` 里还有一道 `updater === undefined → throw` 的兜底 | `update-coordinator.ts:13-16`、`:64`、`:78`、`:108`、`:212-216` |

### 2.3 grep 验证（真实输出）

```
$ grep -rn "autoUpdater\|checkForUpdates" apps/desktop/src
apps/desktop/src/update-coordinator.ts:15:  return desktopUpdatesAllowed() ? electronUpdater.autoUpdater : undefined
apps/desktop/src/update-coordinator.ts:78:    if (updater === electronUpdater.autoUpdater) {
apps/desktop/src/update-coordinator.ts:215:      const result = await updater.checkForUpdates()
```

三处逐条说明：

1. `:15` —— **就是开关本身**（三元表达式的 true 分支；关闭时不求值）。
2. `:78` —— 身份比较（判断要不要替换内置 httpExecutor），只有 `updater !== undefined`（即开关打开）时才可能走到；`autoUpdater` 已经由 `:15` 求值过。
3. `:215` —— 唯一的真实网络调用，位于 `doCheck()` 内；`doCheck()` 只被 `check()` 调用，而 `check()` 首行是 `if (this.updater === undefined) return this.current`（`:108`），`doCheck()` 自己还有 `if (updater === undefined) throw`（`:213`）。

另外两处「会不会偷偷发请求」的排查：

- `mandatory-update-policy` 的远端轮询：关闭时不构造（`main.ts:1456`），`policyAuth` 也不构造。
- 打包侧 `publish` / `app-update.yml`：**没有动**（那是第二组的发布脚本，动它会牵连上传流程）。当前 `apps/desktop/package.json` 没有 `publish` 字段，`electron-builder-config.mjs:301` 因此写 `publish: null`；即便将来某次打包写入了 `app-update.yml`，运行期也不会读它——因为 `releaseFeedUpdater()` 返回 undefined，`check()` 从不执行。

---

## 3. 验收（真实输出）

### 3.1 构建

```
$ export PATH="…/daniel-bot/build/toolchain/node24/bin:$PATH"
$ pnpm -C apps/desktop run build
$ tsc -b && pnpm run bundle
$ tsdown --config-loader native
…
ℹ [CJS] lib/preload-daniel-login.cjs  4.37 kB │ gzip: 2.05 kB
ℹ [ESM] lib/main.js  867.11 kB │ gzip: 219.91 kB
EXIT_CODE=0
```

（`lib/main.js` 867.11 kB；新增 `lib/preload-daniel-login.cjs` 4.37 kB。）

### 3.2 单测

```
$ node_modules/.bin/vitest run apps/desktop/tests/daniel-login.spec.ts
✓ |thread-safe| apps/desktop/tests/daniel-login.spec.ts (4 tests) 6ms
Test Files  1 passed (1)   Tests  4 passed (4)
```

覆盖：`$DANIEL_HOME/session/session.json` 落点、文件 `0600`、目录 `0700`、覆盖写仍 0600、非 `app_session_id` 内容被拒、`clearDanielSession()` 幂等。

回归（原有两套启动用例 + 更新用例，均通过）：

```
$ DSH_HOME=/tmp/vt-dsh DANIEL_HOME=/tmp/vt-daniel vitest run apps/desktop/tests/main-startup.spec.ts
✓ apps/desktop/tests/main-startup.spec.ts (151 tests) 3034ms   → 151 passed
$ … welcome-startup.spec.ts   → 2 passed
$ … update-coordinator.spec.ts → 20 passed
$ … update-schedule.spec.ts   → 20 passed
```

> 说明：这两套用例原本会 `chmod ~/.dsh`，本机沙箱不允许，故用 `DSH_HOME/DANIEL_HOME` 指到临时目录跑。

### 3.3 补丁

```
$ git -C /tmp/dsh-work-2 diff > daniel-bot/app/desktop-patches/0003-login-and-update.patch
62,264 bytes · 14 files changed, 1261 insertions(+), 25 deletions(-)

$ cd /tmp/patchgen && git apply --check 0003-login-and-update.patch
APPLY-CHECK OK        # 在一份「0001 已应用、0003 未应用」的干净树上校验通过
```

---

## 4. 待用户真机验证（本机无 GUI，**未判 PASS**）

```bash
# ① 首次登录：应出现 440×560 的独立登录窗口（标题 Daniel Bot），密码错显示服务端原文，正确则自动关窗进工作区
DANIEL_HOME=/tmp/daniel-login-verify pnpm -C apps/desktop dev

# ② 会话落点与权限 + 二次启动跳过登录
stat -f '%Sp %N' /tmp/daniel-login-verify/session /tmp/daniel-login-verify/session/session.json
#   期望：drwx------ …/session    -rw------- …/session.json
DANIEL_HOME=/tmp/daniel-login-verify pnpm -C apps/desktop dev
#   期望：不再出现登录窗口，直接进工作区；把 session.json 的 cookie 改坏再启动 → 回到登录页
```

补充核对（第四组）：启动后打开应用菜单，**不应**有「检查更新…」；`DANIEL_BOT_ALLOW_UPDATE=1` 时该项恢复。若要看有没有 feed 请求，可在路由器/代理侧过滤 `daniel-agent.com` 之外的主机，或直接 `tcpdump -i en0 -n port 443` 观察。

---

## 5. 没做什么 / 已知限制

1. **没有跑打包与真机 GUI**：DMG 需要在有 PTY 的终端跑（`pnpm -C apps/desktop package:mac:arm64:unsigned`），本组按纪律未执行。因此 §4 两条命令是**唯一**的最终判据。
2. **没有做运行期会话失效处理**：`auth.me` 校验只发生在启动时。若使用过程中 Daniel 会话过期，DSH 里的插件会报未登录，需要重启应用回到登录页；没做「插件报未登录 → 自动弹登录窗口」的桥。
3. **网络不可达时不放行**：有 session 但校验时网络不通，选择「回登录页并解释」而不是「静默进入工作区」。若将来要求离线可用，需要改成可配置策略（当前取舍写在 `requireDanielSession()` 的注释里）。
4. **`DANIEL_BOT_SKIP_LOGIN=1` 逃生开关**：给自动化/CI 和「服务端全挂时救急」用，默认关闭；打开时只打一行 `skipped by DANIEL_BOT_SKIP_LOGIN=1` 并直接进入。**不建议**发给最终用户。
5. **未改 `@deepseek-ai/*` 包名 / LICENSE / 依赖**；没有新增依赖（HTTP 用 Electron `net`，文件用 `node:fs`）。
6. **两处测试文件被改**（`main-startup.spec.ts`、`welcome-startup.spec.ts`）：各加 1 行 `vi.mock('../src/daniel-login.ts')`（该套用例是「闸门之后」的壳行为，登录有独立用例）+ 1 行 `process.env.DANIEL_BOT_ALLOW_UPDATE='1'`（这两套断言的就是被保留的官方更新路径，须显式打开开关才测得到）。
7. **补丁之外的一处基线修复**（需你知晓）：`apps/desktop/scripts/desktop-release-environment.d.mts` 在 0001 快照里缺 `DANIEL_BOT_PRODUCT_NAME` / `DANIEL_BOT_APP_ID` 两条声明，而 `.mjs` 已经导出、多个脚本已引用 → 干净树 `tsc -b` 会报 4 条 TS2305。我在本工作树补了这 6 行（与 `dsh-build` 现行内容一致，属第二组范围），**没有**放进 0003。若你的树已含 0002 的修复，则无需处理。

---

## 6. 关于 `/tmp/dsh-work-2` 的 git（重要，必须知会）

- 我接手时 `git status` 正常；工作过程中该工作树的 `.git` 被清空成只剩空目录（10:07 左右，无任何文件残留、对象不可恢复），`git rev-parse HEAD` 随之失败，构建的 `bundle` 步骤（`repositoryClientBuildEnvironment` 要 `git rev-parse HEAD`）也因此先失败。
- 为恢复可验证状态，我重建了一个**只含一个提交的本地仓库**：该提交的树 = 「0001 已应用（+ 上述 `.d.mts` 6 行）」的状态。随后我的改动是**未提交的工作区改动 + intent-to-add 的新文件**，因此 `git -C /tmp/dsh-work-2 diff` 能直接导出完整 0003。
- 代价：**该工作树里不再有上游历史 `ce7073d5`**（原始 `.git` 已被毁，不可恢复）。上游历史仍在 `/tmp/dsh-build/dsh-src/.git`，我没有改动它。若你要在 `/tmp/dsh-work-2` 里做基于上游 commit 的操作，需要重新 `git fetch`/重建工作树；仅要 0003 的话，现有状态足够。
