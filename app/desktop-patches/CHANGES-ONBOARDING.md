# CHANGES · 第五组（首启引导页按 Daniel 重做）

> 范围：`packages/client/ui-settings-account`（只动首启引导，未动登录页、更新开关、打包配置）
> 工作树：`/tmp/dsh-build/dsh-src`
> 状态：**类型检查 / 桌面构建 / 单测已验**；**GUI 未真机点击**（本机无可交互桌面会话）→ 见 §7

---

## 0. 一句话

把首启引导页从「Harness 的样子」改成「Daniel 的样子」：**删掉「写代码还是办公」这一步**（welcome → process → done），**整页视觉按 daniel-agent.com 的 token 重做**（#F9FAFC 画布、#191C20 正文、#2B7FB0 / #67C3F0 品牌蓝、16–20px 圆角、克制的卡片阴影），**欢迎页换成 Daniel 品牌标记**（产品图标 + "Daniel Bot"，不再用 Harness 鲸鱼插画与字标），8 种语言的文案改成 Daniel 口径。

---

## 1. 流程：三页，删掉 purpose

```
改前：welcome → purpose（写代码 / 办公 单选）→ process（展示偏好）→ done
改后：welcome → process（希望我怎么汇报进展？）→ done
```

- `DesktopOnboarding.tsx:39`：历史进度落在 `credit` / `purpose` 时**统一落到 `process`**，用户不会看到空页，也不会被要求补选已删除的问题。
- `purpose` 字段仍保留在 `onboarding-settings.ts` 的 schema 里（旧安装的存档能正常读），但**新流程不再写它**，`onboarding-state.ts` 的完成逻辑也不再根据它分支。
- 删除 `OnboardingPurposeStep.tsx` 及其 8 语言文案、图标、CSS（`.purpose*`、`.officeCard`）。`progress.purpose` 只剩「读得懂旧存档」的作用。

---

## 2. 视觉：换的是设计，不是字

| 维度 | 落地值 | 位置 |
|---|---|---|
| 画布 / 正文 | 浅色 `#F9FAFC` / `#191C20`；深色 `#0F1115` / `#F9FAFB` | `DesktopOnboarding.module.css:11-30`（浅色）/ `:32-50`（深色），变量 `--ob-canvas` / `--ob-ink` |
| 品牌色 | 主 `#2B7FB0`，亮 `#67C3F0`（取自产品图标） | `--ob-accent` / `--ob-accent-bright` |
| 字体栈 | `Inter, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif` | `--ob-font`，整页继承 |
| 圆角 | 卡片 20px，按钮/图标块 16px | `--ob-radius-card` / `--ob-radius-control` |
| 卡片阴影 | `0 1px 2px rgba(16,24,40,.06), 0 8px 24px rgba(16,24,40,.06)` | `--ob-shadow-card`（hover 时抬到 `--ob-shadow-raised`） |
| 品牌标记 | 产品图标（44px）+ "Daniel Bot"（34px/600），**就是欢迎页 h1** | `OnboardingWelcomeStep.tsx:17-21` |
| 背景层次 | 右上 / 左下两团极淡品牌蓝径向渐变（深色下透明度 0.55），不再是纯灰底 | `.page::before` |
| 过程卡 | 三张等宽卡，图标改为「条数表示细度」的线性 glyph（1 / 2 / 4 条），右侧单选圆环；选中=品牌蓝描边 + 3px 光晕 | `OnboardingProcessStep.tsx`、`.card*` |

欢迎页不再有插画：Harness 的 4 张欢迎 webp 已从组件中移除（文件留在磁盘上不引用，不进包）。按钮也不再是壳里的中性黑/白填充，改成品牌蓝实心（深色下用亮蓝 + 深色字）。

---

## 3. 文案：8 语言全部改成 Daniel 口径

| 文案 | 改前 | 改后 |
|---|---|---|
| 欢迎标题 | `欢迎使用 DeepSeek Harness` | `Daniel Bot` |
| 简介（zh） | 「…Bot 在本地文件夹里工作，读写文件、调用工具，完成从发现到 SOV 的全流程。」 | 「Daniel 帮助 Brand 发现、验证并与真正契合受众的 YouTube Creator 建立联系。」 |
| 简介（en） | 「DeepSeek Harness works in a local folder and uses tools…」 | 「Daniel helps brands discover, verify, and connect with YouTube creators who genuinely fit their audience.」 |
| process 标题 | 「你希望看到多少工作过程？」 | 「希望我怎么汇报进展？」 |
| 三个选项 | 聚焦结果 / 关键细节 / 完整过程 | **精简 / 标准 / 详细**（内部代号 compact / standard / detailed 不再出现在界面文案里） |
| 选项说明 | 「只看结果，保持界面简洁明了」 | 「只给结论和结果，过程收起」 |
| 跳过说明 | 提到「开启代码工作工具」 | 只说「调整进展的展示方式」 |

日 / 西 / 法 / 德 / 俄 / 葡 六种语言按同一口径重写（介绍句 = Daniel 为品牌做发现、验证、撮合；process = 怎么汇报进展 + 精简/标准/详细）。**全部 8 语言都不再出现 Harness / DeepSeek / 代码 / 办公。**

另外把文案 key `backToHarness` 改名为 `backToApp`（值本来就是「返回 Daniel Bot」），这样 `src/client` 里连 key 名都不再出现 Harness；同时改写了两处注释里的 Harness 字眼（`contact-url.ts`、`AccountSection.tsx`）。

---

## 4. 文件 → 改了什么 → 为什么

| 文件 | 改了什么 | 为什么 |
|---|---|---|
| `src/client/OnboardingPurposeStep.tsx` | **删除**（65 行） | 「写代码还是办公」是 Harness 的功能，Daniel 不做这个分流 |
| `src/client/DesktopOnboarding.tsx` | 页面表去掉 credit/purpose；`targetStep` 把旧步骤落到 `process`；`go()` 只接受 `welcome｜process`；删掉 purpose 分支与 `purposeNext()`；分析事件里只保留 process 的 `selected_content` | 流程收成三页，旧存档不落到空页 |
| `src/client/OnboardingWelcomeStep.tsx` | h1 改为「图标 + Daniel Bot」品牌标记；删除插画、`locale` 入参、Harness 字标样式 | 欢迎页必须是 Daniel 的品牌标记，不是换字 |
| `src/client/OnboardingProcessStep.tsx` | 三个选项改成 1/2/4 条 glyph + 单选圆环；卡片改为按钮内 `role="radio"`（键盘方向键逻辑不变） | 去掉 Harness 紫/蓝/青三色图标，视觉统一到品牌蓝 |
| `src/client/DesktopOnboarding.module.css` | 整页重写：token、径向渐变背景、品牌锁排、卡片、单选圆环、导航、对话框、响应式、reduced-motion | 这是「换皮」的主体；之前是壳的 token + 32px 药丸卡 + 动画描边 |
| `src/client/OnboardingSurface.module.css` | 外壳背景/文字/字体改用 `--ob-*`；去掉 macOS 透明覆盖（改为不透明画布） | 引导页背景必须是 #F9FAFC，而不是透出窗口材质 |
| `src/client/assets/onboarding-daniel-mark.svg` | **新增**：从登录窗 `welcome-brand.svg` 抽出的产品图标（96×96 PNG 包在 SVG 里） | 复用官方品牌资产，不新画、不引依赖 |
| `src/client/assets/onboarding-{office,code,compact,standard,detailed}.svg` | **删除**（5 个） | 前两个只服务已删除的 purpose 页；后三个是 Harness 紫/蓝/青配色的选项图标，已由内联单色 glyph 取代 |
| `src/client/locales/onboarding.ts` | 8 语言重写：删 7 个 purpose key + `onboardingWelcome`，新增/改写 process 三项与介绍句 | 文案与流程同时收敛 |
| `src/client/locales.ts` | `backToHarness` → `backToApp`（8 语言） | 文案 key 不再出现 Harness |
| `src/client/onboarding-state.ts` | `finish()` 不再按 purpose 分支：完成态只带用户选的汇报级别，`usage=compact`、`developerTools=false`；跳过态固定 `standard` | 没有「办公/开发」分流后，不应该再偷偷把开发工具打开 |
| `src/client/onboarding-contract.ts`、`src/onboarding-settings.ts`、`src/index.ts` | 只改注释：标明 purpose 是历史字段、`credit`/`purpose` 是已下线页面 | 让后来人知道为什么字段还在 |
| `src/client/contact-url.ts`、`AccountSection.tsx` | 注释里的 Harness → Daniel Bot / the app | 注释也不该留旧品牌 |
| `tests/*` | 见 §6 | 断言旧步骤的测试同步改成新流程 |

---

## 5. 深色模式怎么保证的

只有**一组** CSS 变量、两处取值，没有第二套硬编码颜色：

```css
:global(:root) {
  --ob-canvas: #f9fafc;      /* 画布 */
  --ob-ink: #191c20;         /* 正文 */
  …
}
@media (prefers-color-scheme: dark) {
  :global(:root) {
    --ob-canvas: #0f1115;    /* 深色画布 */
    --ob-ink: #f9fafb;       /* 深色正文 */
    …
  }
}
```

- 组件里所有颜色（背景、正文、次要文字、描边、品牌蓝、阴影、光晕）都只引用 `--ob-*`，因此深色下**只需要重定义变量**，组件与布局零改动。
- 桌面壳会把 UI 的主题源镜像进 Electron 的 `nativeTheme`（`apps/desktop/src/preload-theme.ts`），所以 `prefers-color-scheme` 跟随的是**应用内主题**（含用户手动切的浅/深），不只是系统设置。
- 深色下品牌色改为亮蓝 `#67C3F0`（主色 `#2B7FB0` 在深底上对比不足），按钮文字随之变深色 `#0F1115`，卡片阴影改黑底浓度。

---

## 6. 验收（真实输出）

### 6.1 `tsc -b tsconfig.client.json`

```
$ export PATH="/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/build/toolchain/node24/bin:$PATH"
$ node_modules/.bin/tsc -b tsconfig.client.json; echo "TSC_EXIT:$?"
TSC_EXIT:0
```

### 6.2 `pnpm -C apps/desktop run build`

```
$ pnpm -C apps/desktop run build
✔ Build complete in 62ms
…
✓ built in 363ms
BUILD_EXIT:0
```

（第二次复跑同样 `BUILD_EXIT:0`，日志在 `/tmp/desktop-build.log`。）

### 6.3 旧品牌词扫描

```
$ grep -rn "Harness\|写代码\|办公" packages/client/ui-settings-account/src/client | grep -v "\.d\.ts"
$ echo $?
1        # 无匹配 = 0 行
```

### 6.4 三处改动（改前 → 改后）

**① `src/client/DesktopOnboarding.tsx:39,98`（流程）**

```diff
- const targetStep = progress.step === 'credit' ? 'purpose' : progress.step
+ const targetStep: OnboardingPage = progress.step === 'welcome' || progress.step === 'done' ? progress.step : 'process'

- {step === 'welcome' && <OnboardingWelcomeStep … onStart={() => { click('next'); go('purpose') }} />}
- {step === 'purpose' && <OnboardingPurposeStep t={t} heading={heading} busy={busy} purpose={progress.purpose}
-   onSelect={(purpose) => { void update({ purpose }) }} onContinue={() => { click('next'); purposeNext() }} />}
+ {step === 'welcome' && <OnboardingWelcomeStep t={t} heading={heading} busy={busy} onStart={() => { click('next'); go('process') }} />}
```

**② `src/client/OnboardingWelcomeStep.tsx:17-21`（欢迎页标题 → 品牌标记）**

```diff
- <h1 id="desktop-onboarding-title" ref={heading} tabIndex={-1}>{t('onboardingWelcome')} <em className={css.brand}>{t('onboardingBrand')}</em></h1>
- <p className={css.heroDescription}>{t('onboardingIntroduction')}</p>
- …
- <div className={css.welcomeIllustration} aria-hidden="true">
-   <OnboardingIllustration className={css.welcomeArtwork} src={…} darkSrc={…} />
- </div>
+ <h1 id="desktop-onboarding-title" ref={heading} tabIndex={-1} className={css.brandLockup}>
+   <img className={css.brandMark} src={brandMark} width={44} height={44} alt="" aria-hidden="true" />
+   <span className={css.brandName}>{t('onboardingBrand')}</span>
+ </h1>
+ <p className={css.heroDescription}>{t('onboardingIntroduction')}</p>
```

**③ `src/client/locales/onboarding.ts:10,18-26`（文案）**

```diff
- onboardingIntroduction: 'Daniel 帮助 Brand 发现、验证并与真正契合受众的 YouTube Creator 建立联系。Bot 在本地文件夹里工作，读写文件、调用工具，完成从发现到 SOV 的全流程。'
+ onboardingIntroduction: 'Daniel 帮助 Brand 发现、验证并与真正契合受众的 YouTube Creator 建立联系。'
- onboardingProcess: '你希望看到多少工作过程？'
- onboardingCompact: '聚焦结果'
- onboardingCompactDescription: '只看结果，保持界面简洁明了'
+ onboardingProcess: '希望我怎么汇报进展？'
+ onboardingCompact: '精简'
+ onboardingCompactDescription: '只给结论和结果，过程收起'
+ onboardingStandard: '标准'        /* 原「关键细节」 */
+ onboardingDetailed: '详细'        /* 原「完整过程」 */
```

### 6.5 单测

```
$ vitest run packages/client/ui-settings-account/tests/desktop-onboarding.client.spec.tsx
✓ 24 tests passed
$ vitest run packages/client/ui-settings-account/tests/onboarding-state.client.spec.ts
✓ 59 tests passed
```

改动过的测试：

| 文件 | 改动 |
|---|---|
| `tests/desktop-onboarding.client.spec.tsx` | 按新流程重写：删掉 purpose/credit 页面的用例，新增「旧 purpose 存档落到 process」；快照只保留 welcome/process |
| `tests/onboarding-state.client.spec.ts` | 完成态用例由「purpose × process」九宫格改为三个汇报级别；新增「旧 purpose 不影响结果」；跳过默认仍为 standard |
| `tests/expected/onboarding-{welcome,process}[-en].txt` | 重新生成（新文案） |
| `tests/expected/onboarding-{purpose,credit}*.txt` | 删除（页面已不存在） |
| `tests/expected/onboarding-preferences.json` | 重新生成（3 条，全部 `usage: compact` / `developer: false`） |
| `tests/desktop-onboarding-entry.client.spec.tsx` | 标题断言从「欢迎使用 + Daniel Bot」改为 `Daniel Bot` |
| `tests/account.client.spec.tsx`、`tests/quota-notice-hold.client.spec.tsx` | 仅跟随 key 改名 `backToHarness` → `backToApp` |

---

## 7. 没做 / 已知

- **GUI 未真机点击**：本机没有可交互桌面会话，视觉是按 token 与结构实现、并用 lightningcss 校验两个 CSS Module 可编译；最终观感需要你在终端里起应用看一眼。
- **欢迎插画只下线、没删文件**：`assets/onboarding-welcome*.webp`（4 张 Harness 插画）已无任何 import，仍留在磁盘上，不进包、不上屏；要彻底清掉可以直接删。
- **客户端 bundle 未重建**：`packages/client/ui-settings-account/lib/client.js` 还是旧的（连之前的品牌改造也没进 lib）。要看到效果，需要按你既有流程重建 client 产物（本次按要求没跑打包）。
- **包内 README 未改**：`packages/client/ui-settings-account/README.md` / `README.zh.md` 第 64 段仍在描述额度页与「办公/开发」分流（属于上一轮就过时的文档）。要一起收口的话，我可以下一轮只改这两段。
- **两处与本次无关的既有失败**（改动前就红，未擅自修改）：
  1. `tests/account.client.spec.tsx` 6 个快照仍是「DeepSeek Harness」文字（上一轮品牌改造没重生成快照）；
  2. `tests/quota-notice-hold.client.spec.tsx` 的「onboarding recharge page」用例仍在断言已删除的 credit 页。
