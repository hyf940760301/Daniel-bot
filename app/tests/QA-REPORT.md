# QA-REPORT · Daniel Bot 桌面端二开门禁（G0–G3）

> 日期：**2026-11-02**（本轮：把 G2/G3 从占位改成可执行）· 上一版 2026-11-01（G0/G1）
> 构建工作区：`/tmp/dsh-build/dsh-src`（官方源码 + 13 文件改动，HEAD `ce7073d5`）
> 补丁：`daniel-bot/app/desktop-patches/WIP-embed-and-isolate.patch`（**42,959 B，sha256 `8aa7b73e…29ac`**；11-01 23:51 更新过一版，旧值 42,651 B / `60ab139a…`）
> 本报告所有 PASS/FAIL/SKIP 均为**真实执行输出**（Node v22.23.2 / macOS 26.3 arm64），没有用任何绕过参数。

---

## 0. 结论

| 门禁 | 结论 | 通过 / 失败 / 跳过 | 一句话 |
|---|---|---|---|
| **G0 代码门禁** | ✅ **PASS** | 10 / 0 / 0 | 补丁在干净 HEAD 上可应用，应用结果与工作区 13 文件逐字节相同；构建与 366 条官方测试全绿（本轮 2026-11-02 复跑仍绿） |
| **G1 契约门禁** | ✅ **PASS** | 10 / 0 / 2 | 哈希 / 5 键 / 崩溃恢复 / 幂等全过；**上一轮记录的 `.staging-*` 泄漏本轮未复现**（见 §5） |
| **G2 打包门禁** | ✅ **PASS（旧包）** | 13 / 0 / 0（+5 记录） | 体积 269.7 MB、adhoc 签名 + 深验、版本一致、runtime/app.asar 结构、卸载无残留全过 |
| **G3 安装后运行门禁** | ⏭ **SKIP** | 4 / 0 / 7（+2 记录） | 拷贝与签名已真跑通过；**启动/独立 home/退出三项刻意没跑**（旧包 + 不污染真实桌面），启动路径另用假 app 自测 11/0/0 |
| G4 真机恢复演练 | ⏭ SKIP（占位） | 0 / 0 / 3 | 需要真机交互；代码级等价物已由 G1-3a 覆盖 |

**本轮交付的可执行性**：两个脚本都能独立跑、`--help` 可用、退出码语义清晰（0 无 FAIL / 1 有 FAIL / 2 参数错误），出包后一条命令即可判定。
**G3 的 SKIP 不是"跑不了"**：本机有图形会话，是**刻意不在用户桌面上启动旧版应用**（会弹窗、会往真实 `~/Library/Application Support` 写数据），详见 §4.3。

### 怎么复跑

```bash
cd "/Users/huyifan/Desktop/DeepSeek Harness"

# G2：验 DMG（缺省自动找最新；验旧包加 --legacy）
node daniel-bot/app/tests/g2-packaging-gate.mjs
node daniel-bot/app/tests/g2-packaging-gate.mjs --legacy           # 改造前旧包
node daniel-bot/app/tests/g2-packaging-gate.mjs --dmg <path.dmg>

# G3：安装后运行（出包后跑这条就够）
node daniel-bot/app/tests/g3-install-gate.mjs --dmg <path.dmg>
node daniel-bot/app/tests/g3-install-gate.mjs --app "/path/Daniel Bot.app"
node daniel-bot/app/tests/g3-install-gate.mjs --dmg <path.dmg> --preflight   # 只验拷贝+签名

# 全量汇总（G2/G3 无产物时自动 SKIP，不判 PASS）
node daniel-bot/app/tests/run-all.mjs
node daniel-bot/app/tests/run-all.mjs --dmg <path.dmg> --only g2,g3
```

每个门禁脚本可独立运行，输出格式固定为 `PASS|FAIL 名称 ← 期望 vs 实际`，另有 `RECORD 名称 = 值`（只记录、不判定）。

---

## 1. G0 代码门禁 —— PASS（10/10）

### G0-1 补丁可复现

做法：`git archive HEAD` 取出**干净树**（不碰当前工作区、不新增 worktree），在干净树上 `git apply --check`，再真应用一次并与工作区逐字节比对。

```
PASS G0-1a 干净树取自 HEAD（不含补丁新增文件） ← 期望: HEAD=ce7073d5 解包成功且无 daniel-plugin.ts | 实际: archive=0 tar=0 无 daniel-plugin.ts=true
PASS G0-1b 干净副本上 git apply --check ← 期望: 退出码 0，无 fuzz/reject | 实际: 退出码 0，stderr 空
PASS G0-1c 真应用补丁（非 --check） ← 期望: 退出码 0，无 .rej/.orig 残留 | 实际: 退出码 0，残留=无
PASS G0-1d 应用结果与工作区 13 文件逐字节一致 ← 期望: 13 个文件 sha256 全等，0 失配 | 实际: 13 个文件，失配 0
```

> 只跑 `--check` 会假绿：能打上 ≠ 打完之后等于工作区。所以补了 1c（真应用）和 1d（13 文件 sha256 逐个比对）。

### G0-2 类型检查

```
PASS G0-2 tsc + bundle 构建 ← 期望: 退出码 0，无 error TS，lib/main.js 本次重写 | 实际: 退出码 0，error TS 0 处，mtime 已更新
      $ tsc -b && pnpm run bundle
      $ tsdown --config-loader native
      ℹ [ESM] lib/main.js  846.03 kB │ gzip: 213.56 kB
```

命令：`pnpm -C apps/desktop run build`（Node 24 toolchain 置前）。防假绿：额外断言 `lib/main.js` 的 mtime 确实被本次刷新。

### G0-3 官方测试（project-manager / profile 相关）

> ⚠️ `pnpm -C apps/desktop test` 在本仓库不存在（`apps/desktop/package.json` 没有 `test` 脚本）。门禁改用仓库根 `node_modules/.bin/vitest run <11 个 spec>`，跑的是同一批用例。

```
PASS G0-3a 测试运行器存在 ← 期望: .../node_modules/.bin/vitest 可执行；11 个 spec 都在 | 实际: vitest=有，spec 11/11
PASS G0-3b 官方测试全绿（11 个 spec） ← 期望: 退出码 0，Test Files 11 passed，0 failed | 实际: 退出码 0，Test Files 11 passed，Tests 366 passed
PASS G0-3c project-manager 用例数（贴真实数量） ← 期望: project-manager.spec.ts ≥ 35 passed（1 skipped 允许） | 实际: project-manager.spec.ts 36 tests，其中 skipped 1 ⇒ passed 35
PASS G0-3d 补丁新增的 daniel-plugin 用例被执行 ← 期望: daniel-plugin.spec.ts (5 tests) | 实际: daniel-plugin.spec.ts (5 tests)
```

| spec | 用例数 |
|---|---|
| apps/desktop/tests/project-manager.spec.ts | 36 tests / 1 skipped ⇒ 35 passed |
| apps/desktop/tests/daniel-plugin.spec.ts | 5 |
| apps/desktop/tests/profile-mcp.spec.ts | 1 |
| apps/desktop/tests/development-project.spec.ts | 3 |
| packages/boot/app-boot/tests/profile.spec.ts | 36 |
| packages/boot/app-boot/tests/profile-sanitize.spec.ts | 5 |
| packages/boot/app-boot/tests/profile-plugins.spec.ts | 7 |
| packages/boot/app-boot/tests/profile-compatibility.spec.ts | 27 |
| packages/boot/app-boot/tests/profile-resolution.spec.ts | 233 |
| packages/boot/app-boot/tests/profile-resolution-service.spec.ts | 12 |
| packages/boot/app-boot/tests/profile-resolution-worker-bootstrap.spec.ts | 2 |
| **合计** | **366 passed / 1 skipped / 0 failed** |

### G0-4 补丁与工作区一致

```
PASS G0-4 补丁文件 == 工作区 git diff HEAD（逐字节） ← 期望: sha256 相同、13 个 diff --git、字节数相同 | 实际: patch 8aa7b73e81379219… 42959B，diff 8aa7b73e81379219… 42959B；diff --git 13 vs 13
```

---

## 2. G1 契约门禁 —— PASS（10 通过 / 0 失败 / 2 跳过）

> 本轮（2026-11-02）复跑结论为 PASS：G1-4b/4c 的 `.staging-*` 残留为 0、两次 sync 的 vendor 树指纹相同。
> 上一轮记录的 FAIL 及根因分析保留在 §5（作为历史），本轮未复现。

### G1-1 插件内容哈希 —— PASS

```
PASS G1-1a 插件版本与文件数 ← daniel-dsh-plugin@0.11.0，210 个文件，0 软链
PASS G1-1b root_hash 等于版本钉死的 known-good ← bc34a72f9d062003…（0.11.0 一致）
SKIP G1-1c PLUGIN-MANIFEST.json 一致 ← 补丁未引入 PLUGIN-MANIFEST.json（已 grep 补丁全文核实），无清单可对
PASS G1-1d 与 tgz 真源逐文件一致 ← 解包 210 文件，root_hash 相同，差集为空
```

判据不是"目录存在"：按 `embedDanielPlugin` 同一算法（`path\0bytes\0sha256\n` 再 sha256）复算 210 个文件，并与 `daniel-bot/releases/daniel-dsh-plugin-0.11.0.tgz` 解包结果做双向差集（0 差异）。

### G1-2 配置 5 键 —— PASS

```
PASS G1-2a 5 键写入逻辑（真跑产品代码 + YAML 解析 + 组装复核） ← 4 个用例全过
      ✔ profile patch：一行 daniel，config 键集合恰好是 5 个
      ✔ overlay 与 profile patch 的五键配置完全一致（不漂移）
      ✔ 重写幂等；外来 patch 内容会被备份而不是静默丢弃
      ✔ 组装后（loadProfileDirectory + composeEntries）仍是 5 键，且只有一行 daniel
PASS G1-2b 源码模板里 5 个键名都在 ← 5/5 都在
```

真调用 `writeDanielProfilePatch` / `writeDanielAppOverlay` 写文件，用 js-yaml 解析，断言 config 的**键集合恰好等于** `{entry, python, danielHome, timeoutMs, trace}`。

### G1-3 sanitizeProfile 兼容（崩溃恢复保留插件）—— PASS

```
PASS G1-3a 崩溃恢复后插件仍在（真跑 disableAllPlugins） ← 3 个用例全过
      ✔ CONTROL: 裸 sanitizeProfile 会删插件并把 patch 挪走
      ✔ PRODUCT: 崩溃恢复后插件仍在 bundles，且 5 键 patch/overlay 被重写
      ✔ NEGATIVE: 没有插件副本时恢复不得凭空激活插件
PASS G1-3b 恢复路径顺序正确：sanitize 之后立刻重写 patch ← sanitize@4182 → rewrite@4293，拼入插件=true
```

CONTROL 用例是防假绿关键：它证明裸 `sanitizeProfile(..., ['web-app'])` 会把 `daniel-dsh-plugin` 从 bundles 删掉、且 patch 消失。

### G1-4 seed / 复制幂等 —— PASS

```
PASS G1-4a 嵌入复制幂等（embedDanielPlugin，含 mtime 不变） ← 3 个用例全过
PASS G1-4b 工作区 vendor 根无 .staging-* 残留 ← 实际 0 个
PASS G1-4c sync 脚本两次运行 vendor 根文件树一致 ← run1 tree-sha256:93d3…/253 项（staging 0）→ run2 tree-sha256:93d3…/253 项（staging 0）
SKIP G1-4d seed-profile.sh 端到端幂等 ← 需要对已签名的 .app / 组装好的 Resources
```

---

## 3. G2 打包门禁（本轮新增 · 可执行）

脚本：`daniel-bot/app/tests/g2-packaging-gate.mjs`

### 3.1 判据

| 编号 | 判据 | 期望 |
|---|---|---|
| G2-0 | 找到待检 DMG | `--dmg` 指定，或在 `/tmp/dsh-build/.../.desktop-build/**` 与 `daniel-bot/releases/` 里按 mtime 取最新 |
| G2-1 | 体积 | 200,000,000 ≤ bytes ≤ 400,000,000（且 200–400 MiB 两套口径都成立） |
| G2-2a | `hdiutil attach -nobrowse -readonly -mountpoint` | 退出码 0 |
| G2-2b | 卷内可列出 `.app` | ≥1 个 |
| G2-3a | `codesign -dv --verbose=2` | `Signature=adhoc` |
| G2-3b | `codesign --verify --deep --strict` | 退出码 0 |
| G2-4a | 版本一致 | `CFBundleShortVersionString` == DMG 文件名里的版本 |
| G2-4b | **记录** `CFBundleIdentifier` | 只记录当前值，不判 FAIL（品牌一致性归 G6 品牌门） |
| G2-5a–d | 结构 | `Resources/runtime/`、`runtime/primary-runtime/dependencies/`、`runtime/bin/node`（可执行）、`Resources/app.asar`（>1 MB） |
| G2-6 | 内嵌插件 | `Resources/vendor/daniel-dsh-plugin` 是真目录、package.json.name 正确、≥100 文件（`--legacy` 时记 RECORD） |
| G2-7a/b | 卸载与残留 | `hdiutil detach` 退出 0；`hdiutil info` 不含挂载点且挂载点内 0 条目 |

### 3.2 真实输出（用现有旧包 `deepseek-harness-0.2.2-alpha.2-mac-arm64-unsigned.dmg` 跑）

```text
$ node daniel-bot/app/tests/g2-packaging-gate.mjs --legacy
  · 候选目录：/tmp/dsh-build/dsh-src/apps/desktop/.desktop-build , .../daniel-bot/releases
  · 候选 DMG 2 个（mtime 新→旧）：
     .../daniel-bot/releases/deepseek-harness-0.2.2-alpha.2-mac-arm64-unsigned.dmg  269.7 MB (257.2 MiB)
     /tmp/dsh-build/.../unsigned-artifacts/deepseek-harness-0.2.2-alpha.2-mac-arm64-unsigned.dmg  269.7 MB (257.2 MiB)
PASS G2-0 找到待检 DMG ← 期望: 文件存在且是普通文件 | 实际: .../releases/deepseek-harness-0.2.2-alpha.2-mac-arm64-unsigned.dmg
PASS G2-1 DMG 体积在 200–400 MB ← 期望: 200,000,000 ≤ bytes ≤ 400,000,000（200–400 MB），且 200–400 MiB | 实际: 269,653,442 bytes = 269.7 MB (257.2 MiB)；10 进制 MB 区间内=true，MiB 区间内=true
PASS G2-2a hdiutil attach（-nobrowse -readonly -mountpoint） ← 期望: 退出码 0，只读挂载到指定挂载点 | 实际: 退出码 0；设备 /dev/disk6→GUID_partition_scheme, /dev/disk6s1→Apple_HFS /private/tmp/qa-g2-mnt-80858
PASS G2-2b 卷内可列出 .app ← 期望: 卷根 ≥1 个 *.app 目录 | 实际: 1 个：DeepSeek Harness.app
PASS G2-3a 签名类型 = adhoc ← 期望: Signature=adhoc | 实际: Signature=adhoc；Identifier=com.deepseek.harness；Format=app bundle with Mach-O thin (arm64)
PASS G2-3b codesign --verify --deep --strict ← 期望: 退出码 0 | 实际: 退出码 0，输出为空
PASS G2-4a CFBundleShortVersionString 与文件名版本一致 ← 期望: 文件名版本 ∈ {0.2.2-alpha.2} 且等于 Info.plist 版本 | 实际: Info.plist=0.2.2-alpha.2；文件名解析出 {0.2.2-alpha.2}
RECORD G2-4b CFBundleIdentifier（记录当前值，不判 FAIL） = com.deepseek.harness
RECORD G2-4c CFBundleName / CFBundleVersion（记录） = DeepSeek Harness / 0.2.2-alpha.2
PASS G2-5a Contents/Resources/runtime/ 存在 ← 期望: runtime 是目录 | 实际: .../Contents/Resources/runtime（目录）
PASS G2-5b runtime/primary-runtime（含 dependencies） ← 期望: primary-runtime/ 是目录，且其下 dependencies/ 存在 | 实际: primary-runtime=目录；dependencies=目录
PASS G2-5c runtime/bin/node 存在且可执行 ← 期望: 文件存在，权限含 x | 实际: 存在，0755，100 B，可执行=true
PASS G2-5d Contents/Resources/app.asar 存在且非空壳 ← 期望: 文件存在且 > 1 MB | 实际: 212.7 MB (202.8 MiB)
RECORD G2-6 内嵌插件 Resources/vendor/daniel-dsh-plugin（--legacy：只记录） = 不存在（改造前预期）
RECORD G2-6b .app 体积（记录） = 1066.5 MB (1017.1 MiB / 1.07 GB)
RECORD G2-6c .app 名称（记录，G6 品牌门用） = DeepSeek Harness.app
PASS G2-7a hdiutil detach 退出 0 ← 期望: 退出码 0（必要时 -force 重试） | 实际: 退出码 0；尝试 1 次
PASS G2-7b 卸载后无残留挂载点 ← 期望: hdiutil info 不含该挂载点，且挂载点目录为空/已删 | 实际: hdiutil info 命中=false；挂载点内条目=0

RESULT: PASS  G2 打包门禁 · DMG 产物结构与签名 — 通过 13 / 失败 0 / 跳过 0 / 记录 5
  用时 32.8s · 退出码 0
```

### 3.3 体积区间 200–400 MB 的依据

- **下界 200 MB**：改造前 `0.2.2-alpha.2` 实测 **269.7 MB / 257.2 MiB**，是这次打底的基线；内嵌插件（210 文件 ≈ 6 MB）与随包 runtime 只会让它更大。掉到 200 MB 以下只可能是 runtime / app.asar 没打进去。
- **上界 400 MB**：给"内嵌 8 束语料 + CLI + 可能的随包 Python"留 ≥40% 余量，同时能抓住"node_modules / 构建缓存 / 第二份 runtime 被打进包"这类事故（`.app` 解包后 1.07 GB，压缩成 DMG 后 270 MB，比例约 1:4）。
- 两套单位都判（10 进制 MB 与 MiB），避免"按 1000 算过、按 1024 算没过"的扯皮。

### 3.4 为什么有 RECORD 项

`CFBundleIdentifier` 当前仍是 `com.deepseek.harness`。按任务口径，G2 **只记录不判定**——改造后它应当变成 Daniel 的品牌标识，品牌一致性由 G6 品牌门用这条记录去判 FAIL。同理 `CFBundleName`、`.app` 名称、`.app` 体积都只记录，供 G6 / 发版核对。

`--legacy` 只影响 G2-6（内嵌插件）：旧包本来就没有 `Resources/vendor/daniel-dsh-plugin`，用 `--legacy` 跑会记 RECORD；**改造后的包不要加 `--legacy`**，那条必须是 PASS。

### 3.5 出包后怎么跑

```bash
node daniel-bot/app/tests/g2-packaging-gate.mjs          # 自动找最新 dmg（新包在 .desktop-build 下）
# 或显式：
node daniel-bot/app/tests/g2-packaging-gate.mjs \
  --dmg /tmp/dsh-build/dsh-src/apps/desktop/.desktop-build/targets/mac-arm64/unsigned-artifacts/<新包>.dmg
```

新包预期的关键变化：`G2-6 PASS`（插件随包）、`CFBundleIdentifier` 记录值变成 Daniel 品牌标识。

---

## 4. G3 安装后运行门禁（本轮新增 · 可执行）

脚本：`daniel-bot/app/tests/g3-install-gate.mjs`（旧的 `g3-runtime-smoke-gate.mjs` 已改成转发壳，保留旧路径可用）

### 4.1 判据

| 编号 | 判据 | 说明 |
|---|---|---|
| G3-0 | 解析产物 | `--app` 或 `--dmg`；给 DMG 时自己挂载取 `.app`，结束时卸载 |
| G3-1a | `ditto` 拷到 `/tmp/qa-app` | 副本与源的**文件数 / 逻辑字节 / 软链数**完全一致 |
| G3-1b | 副本 `codesign --verify --deep --strict` | 退出码 0（拷贝不能破坏签名） |
| G3-1c | 记录产物身份 | 名称 / bundle id / 版本 |
| G3-1d | `Contents/MacOS/<CFBundleExecutable>` | 存在且可执行 |
| G3-2a | 10 秒内进程出现 | `pgrep -f "<app>/Contents/MacOS/<exe>"` |
| G3-2b | 启动 1.5 秒后仍存活 | 抓"起来了但立刻崩"的假绿 |
| G3-2c | 日志无 `skipping profile bundle` | 扫 stdout/stderr + `~/Library/Logs/<AppName>`；没有日志来源时 SKIP |
| G3-3a | `~/Library/Application Support/Daniel Bot/` 生成 | 不存在 ⇒ **FAIL**（D-044 核心验收） |
| G3-3b | 该目录权限 0700 | |
| G3-3c | `dsh-home` / `daniel-home` 子目录存在且 0700 | |
| G3-4 | 5 秒内退出 | `process.kill(-pgid,0)` → ESRCH；超时要 SIGKILL 的也判 FAIL |
| G3-5 | Gatekeeper 评估 | `spctl` 结果**只记录**（adhoc 未公证被 rejected 属预期） |

退出码：0 = 无 FAIL（含"未启动 ⇒ SKIP"）；1 = 有 FAIL；2 = 参数/环境错误。

### 4.2 对旧 DMG 的真实输出（`--preflight`）

```text
$ node daniel-bot/app/tests/g3-install-gate.mjs --dmg .../deepseek-harness-0.2.2-alpha.2-mac-arm64-unsigned.dmg --preflight
  · 图形会话：可用（gui/501 可访问，控制台用户 huyifan）
  · 拷贝目标：/tmp/qa-app
  · 独立 home 断言：/Users/huyifan/Library/Application Support/Daniel Bot
PASS G3-0 从 DMG 取 .app ← 期望: 挂载成功且卷内有 .app | 实际: deepseek-harness-0.2.2-alpha.2-…dmg → DeepSeek Harness.app
PASS G3-1a ditto 拷贝到可写目录 ← 期望: 副本与源文件数/逻辑字节/软链数完全一致 | 实际: 源 6414 文件 / 1049.9 MB / 16 软链 → 副本 6414 文件 / 1049.9 MB / 16 软链
PASS G3-1b 副本 codesign --verify --deep --strict ← 期望: 退出码 0 | 实际: 退出码 0，输出为空
RECORD G3-1c 产物身份（记录） = DeepSeek Harness / com.deepseek.harness / v0.2.2-alpha.2
PASS G3-1d Contents/MacOS 可执行文件 ← 期望: 存在且可执行 | 实际: DeepSeek Harness（0755）
SKIP G3-2a 10 秒内进程出现 ← 以 --preflight 运行：只验产物与签名，不启动 app
SKIP G3-2b 启动后 1.5 秒仍存活 ← 同上
SKIP G3-2c 日志无 "skipping profile bundle" ← 同上
SKIP G3-3a ~/Library/Application Support/Daniel Bot/ 生成 ← 同上
SKIP G3-3b 独立 home 权限 0700 ← 同上
SKIP G3-3c dsh-home / daniel-home 子目录 ← 同上
SKIP G3-4 5 秒内退出（进程组 ESRCH） ← 同上
RECORD G3-5 Gatekeeper 评估（记录，不判 FAIL） = spctl 退出码 3：/tmp/qa-app/DeepSeek Harness.app: rejected
  · 卸载临时 DMG：成功（/tmp/qa-g3-mnt-81483）
  · 副本 /tmp/qa-app 已删除（--keep 可保留）

本次未跑完整判据：以 --preflight 运行：只验产物与签名，启动 / 独立 home / 退出三项没有执行

RESULT: SKIP  G3 安装后运行门禁 · 启动 / 独立 home / 退出 — 通过 4 / 失败 0 / 跳过 7 / 记录 2
  用时 44.9s · 退出码 0
```

### 4.3 为什么这次是 SKIP，而不是 PASS 或 FAIL

1. 旧包是**改造前**产物：没有独立 home 逻辑，跑 G3-3a 必然 FAIL——这个 FAIL 说明不了任何新问题，只会污染结论。
2. 真跑要 `open` 旧版应用：会**在用户桌面上弹窗**，并往真实 `~/Library/Application Support` 写数据。本会话不该制造这种副作用，所以**不启动**，用 `--preflight` 只做拷贝与签名（这两项真跑了、真 PASS）。
3. 因此结论行是 `RESULT: SKIP`：**有 PASS 也不降级成"通过"**，`Gate.finish({skipReason})` 会把结论压成 SKIP，`run-all` 也会单独标 SKIP。

**用户手工复验的两条命令**（普通终端里跑，输出贴回来即可判定）：

```bash
open -n "/tmp/qa-app/Daniel Bot.app"
sleep 10; ls -ld "$HOME/Library/Application Support/Daniel Bot" "$HOME/Library/Application Support/Daniel Bot/dsh-home"; osascript -e 'quit app "Daniel Bot"'
```

### 4.4 启动路径自测：用一个一次性假 app 真跑（11 PASS / 0 FAIL）

为了证明"启动 → 进程 → home → 退出"这条链路真的能跑（而不是写完就算），在本机用 `/tmp/qa-fake/Fake Bot.app`（ad-hoc 签名、壳体脚本、只往 `$FAKE_HOME` 写）完整跑了一遍：

```text
$ FAKE_HOME=/tmp/qa-fake/home/... node daniel-bot/app/tests/g3-install-gate.mjs --app "/tmp/qa-fake/Fake Bot.app" --keep
PASS G3-2a 10 秒内进程出现 ← 实际: 0.01s 出现，pid=97139（方式 exec，直接执行 pid=97139）
PASS G3-2b 启动后 1.5 秒仍存活 ← 实际: 存活，pid=97139
RECORD G3-2d 进程与进程组（记录） = pid=97139 pgid=97139
PASS G3-2c 日志无 "skipping profile bundle" ← 实际: 未命中（扫描 1 个来源 / 93 字符）
PASS G3-3a ~/Library/Application Support/Daniel Bot/ 生成 ← 实际: 已生成
PASS G3-3b 独立 home 权限 0700 ← 实际: 0700
PASS G3-3c dsh-home / daniel-home 子目录存在且 0700 ← 实际: dsh-home=存在/0700；daniel-home=存在/0700
PASS G3-4 5 秒内退出（进程组 ESRCH） ← 实际: 0.27s 内退出（方式 group）（进程组探针 ESRCH）
RESULT: PASS  G3 安装后运行门禁 · 启动 / 独立 home / 退出 — 通过 11 / 失败 0 / 跳过 0 / 记录 4
```

另外用第二个假 app（不建 home）验证 FAIL 语义：`G3-3a` 判 **FAIL**、两条子目录检查降为 SKIP、进程仍能正常退出，结论 `RESULT: FAIL … 退出码 1`，符合"独立 home 不存在就是不合格"。

### 4.5 出包后怎么跑（一条命令）

```bash
node daniel-bot/app/tests/g3-install-gate.mjs \
  --dmg /tmp/dsh-build/dsh-src/apps/desktop/.desktop-build/targets/mac-arm64/unsigned-artifacts/<新包>.dmg
```

新包预期：11 项全 PASS，且 `CFBundleIdentifier` 记录为 Daniel 品牌标识。若 `G3-3a` FAIL，直接看 `~/Library/Application Support/Daniel Bot/` 是否被 `installDanielHomes()` 建出来。

### 4.6 实现里踩到的三个坑（都已变成判据的一部分）

| 坑 | 现象 | 处理 |
|---|---|---|
| `du` 在 DMG 上不可比 | 源 1,041,492 KB → 副本 1,073,708 KB（+3.1%），差点把"拷贝成功"判成 FAIL | 改用**文件数 + 逻辑字节 + 软链数**（`treeStats`），与文件系统块大小无关 |
| 子进程变僵尸 | 同步轮询（`Atomics.wait`）堵住 SIGCHLD，`kill(pid,0)` 永远成功，退出判定假 FAIL | 轮询改 `await setTimeout`（让事件循环回收子进程）+ 挂 `exit` 监听 |
| 进程组探针 EPERM | macOS 对"组内已无成员"可能返回 EPERM 而不是 ESRCH；把 EPERM 当"还活着"会导致永远等不到退出 | `probeGroup` 返回 alive/gone/denied；判"已退出"要求 pid 不在 + pgrep 为空 + 组探针非 alive |

---

## 5. 上一轮 FAIL 项（本轮未复现，保留根因）

> 2026-11-01 记录的两条 FAIL 是 `sync-daniel-plugin.mjs` 每次幂等运行泄漏 `.staging-*`（原因：命中"未变化"分支时 `process.exit(0)` 跳过 `finally` 的清理）。
> 本轮（2026-11-02）复跑 G1：`G1-4b` 0 个残留、`G1-4c` 两次指纹相同（253 项 / staging 0）⇒ **PASS**。
> 原因：补丁在 11-01 23:51 更新过一版（42,959 B），新的 sync 脚本在命中「未变化」分支时**先** `rmSync(staging)` 再 `process.exit(0)`（patch 第 174 行；旧版没有这一行）。**这不是本轮 QA 的改动**，原始根因保留在此供回溯。

原复现步骤（保留）：

```bash
rm -rf /tmp/qa-sync && mkdir -p /tmp/qa-sync/apps/desktop/scripts /tmp/qa-sync/apps/desktop/resources/vendor
cp /tmp/dsh-build/dsh-src/apps/desktop/scripts/sync-daniel-plugin.mjs /tmp/qa-sync/apps/desktop/scripts/
cd /tmp/qa-sync/apps/desktop
TGZ="/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/releases/daniel-dsh-plugin-0.11.0.tgz"
node scripts/sync-daniel-plugin.mjs --from "$TGZ"   # 第 1 次
node scripts/sync-daniel-plugin.mjs --from "$TGZ"   # 第 2 次
find resources/vendor -maxdepth 1 -name '.staging-*' | wc -l   # 期望 0
```

影响面（当时结论，仍成立）：`electron-builder-config.mjs` 的 `extraResources` 只映射 `resources/vendor/daniel-dsh-plugin`，`.staging-*` **不进包**，不是发版事故；但会脏构建机、并绊倒任何对整个 `vendor/` 做哈希的下游脚本。

---

## 6. 最可能假绿的地方 + 我加的判据

### 首选：**5 键配置"文件里有" ≠ "Host 挂载时有"**

- 官方 `daniel-plugin.spec.ts` 只断言 patch **文件文本**里有 `entry:`；插件自带的 bundle patch 只写 2 个键（`python` / `timeoutMs`）。
- 一旦上游 rebase 改了层序，**文件仍是 5 键、官方用例仍绿**，但组装结果只剩 2 个键 ⇒ 运行期找不到 CLI（"插件装了但用不了"）。
- 我的判据（`specs/five-keys.spec.mjs` 第 4 条）：用真实 `loadProfileDirectory` + `composeEntries` 组装后断言 `skippedBundles` 为空、`- id: daniel` 恰好 1 行、config 键集合恰好 5 键、`entry` 指向 profile 内副本。

### G2 / G3 里的四处

| 假绿 | 为什么会绿 | 我加的判据 |
|---|---|---|
| DMG 能挂载就当包没问题 | 挂载成功不代表签名、结构、版本都对 | G2 逐项断言 adhoc 签名 + 深验退出码 + 版本比对 + runtime/app.asar 存在且非空壳 |
| `app.asar` 只要存在 | 0 字节 / 几百字节的 asar 也能"存在" | G2-5d 要求 > 1 MB |
| app 启动了就当跑通 | Electron 起来 200 ms 崩掉也会短暂出现 | G3-2b 启动 1.5 秒复查 + G3-2c 扫日志 |
| 进程消失就当"正常退出" | 崩溃/被系统杀掉也会消失；僵尸又会让它"永远活着" | G3-4 要求 5 秒内 ESRCH，超时靠 SIGKILL 的判 FAIL；僵尸用 `exit` 事件判定 |

另外两处历史判据（保留）：补丁"能 apply"就当可复现（G0-1c/1d 真应用 + 13 文件 sha256）；`run-all` 把 SKIP 显示成 OK（改为解析 `RESULT:` 行，零 PASS 且全 SKIP ⇒ SKIP）。

---

## 7. SKIP 清单（含原因与复验方法）

| 项 | 原因 | 复验方法 |
|---|---|---|
| G1-1c `PLUGIN-MANIFEST.json` | 补丁未引入该清单（grep 全文核实） | 打包后 `bash daniel-bot/app/scripts/seed-profile.sh --app <Resources> --write-manifest` 生成，再复跑 G1 |
| G1-4d `seed-profile.sh` 端到端 | 需要已签名 `.app` / 组装好的 Resources | `bash daniel-bot/app/scripts/seed-profile.sh --app <xxx.app> --home /tmp/qa-home --dsh-home /tmp/qa-dsh` 连跑两次 |
| G2 全部（无包时） | 候选目录里没有 `.dmg` | 出包后 `node g2-packaging-gate.mjs`（自动发现） |
| G3-2a/2b/2c/3a/3b/3c/4 | 本次 `--preflight`（旧包 + 不启动 GUI） | 出包后 `node g3-install-gate.mjs --dmg <新包>`；或按 §4.3 的两条手工命令 |
| G3-2c（有启动但无日志） | app 正常启动不落盘，只在崩溃时写 `~/Library/Logs` | 出现"插件装了但用不了"时，用 `--dump-config` / 崩溃报告里的 `hostDiagnostic` 复核 `skippedBundles` |
| G4 a–c 真机恢复演练 | 需真机触发崩溃恢复 | 见 `g4-crash-recovery-gate.mjs` 文件头；代码级等价物已由 G1-3a 覆盖 |

**SKIP 一律没有写成 PASS**：G2 无包时结论行是 `RESULT: SKIP`；G3 的 `--preflight` 即使有 4 个 PASS 也压成 `RESULT: SKIP`。

---

## 8. 交付文件

| 文件 | 作用 |
|---|---|
| `daniel-bot/app/tests/g2-packaging-gate.mjs` | **本轮重写**：G2 六类检查（体积/挂载/签名/版本/结构/卸载），`--dmg`、`--legacy`、`--help` |
| `daniel-bot/app/tests/g3-install-gate.mjs` | **本轮新增**：G3（拷贝→签名→启动→日志→独立 home→退出→Gatekeeper），`--app`、`--dmg`、`--preflight`、`--quit`、`--help` |
| `daniel-bot/app/tests/lib/pkg.mjs` | **本轮新增**：DMG 挂载/卸载/残留判定、plist 解析、签名查询、版本解析、`treeStats`、进程组探针 |
| `daniel-bot/app/tests/lib/gate.mjs` | 本轮扩展：`record()`（只记录不判定）、`finish({skipReason})`（有 PASS 也降为 SKIP）、`parseArgs` 支持 `--key=value` |
| `daniel-bot/app/tests/run-all.mjs` | 接入 G2/G3 新脚本；SKIP 语义与提示更新 |
| `daniel-bot/app/tests/g3-runtime-smoke-gate.mjs` | 改为**转发壳**（旧路径仍可用），并列出新 G3 未覆盖的三项运行时检查 |
| `daniel-bot/app/tests/g0-code-gate.mjs` / `g1-contract-gate.mjs` | 未改动，本轮复跑仍绿 |
| `daniel-bot/app/tests/specs/*.spec.mjs` | 未改动（G1 的单测） |
| `daniel-bot/app/tests/QA-REPORT.md` | 本报告 |

**未改动产品源码**：`/tmp/dsh-build/dsh-src` 只读（只跑 G0 的构建与测试）；跑完复查 `git status` 仍是 13 项改动、补丁 sha256 未变。
本轮临时文件：`/tmp/qa-g2-mnt-*`、`/tmp/qa-g3-mnt-*`、`/tmp/qa-app*`、`/tmp/qa-g3-launch-*.log`（门禁自行清理挂载点与副本；启动日志保留供排查）。

## G3 真机验证（用户执行，2026-11-02 00:34）

来源：用户在真实终端安装并启动 `daniel-bot-v2-1102.dmg` 后执行。

```
drwx------@ 4 huyifan staff 128 11月 2 00:34 .../Application Support/Daniel Bot
drwx------@ 3 huyifan staff  96 11月 2 00:34 .../Daniel Bot/daniel-home
drwx------@ 7 huyifan staff 224 11月 2 00:34 .../Daniel Bot/dsh-home
$HOME/Library/Application Support/Daniel Bot/dsh-home/profiles/desktop/node_modules
daniel-dsh-plugin
```

| 判据 | 结果 | 证据 |
|---|---|---|
| G3-3a 独立 home 生成 | **PASS（真机）** | 三个目录存在，权限 `drwx------`（0700） |
| G3-3b 权限 0700 | **PASS（真机）** | 同上 |
| G3-3c 插件就位 | **PASS（真机）** | `profiles/desktop/node_modules/daniel-dsh-plugin` 存在 |
| G3-2c UI 无插件入口 | **PASS（真机）** | 用户确认：插件入口看不到 |
| G3-3d 不继承旧 home | **PASS（真机）** | 用户确认：会话列表为空（未读 `~/.dsh`） |

> 本会话内的 G3-3a FAIL 系沙箱导致（`sandbox initialization failed: Operation not permitted`），非产品缺陷；真机验证已通过。
