# 插件包升级手册（UPGRADE-PLUGIN）

> **一句话**：换插件版本 = 跑一条命令（默认干跑）+ 改 4 处常量 + 按 6 条清单验收。
> 本文与 `daniel-bot/app/scripts/upgrade-plugin.mjs` 共用**同一套 hash 口径**，两者对不上就是 bug。
>
> 适用对象：给 Daniel Bot 桌面端换内嵌插件（`daniel-dsh-plugin`）的发布工程。
> 不适用：换 DSH 壳版本、改插件业务代码、走渠道发版（那些有各自的流程）。

---

## 0. 一页速查

```bash
# 1) 干跑（默认；只解包到临时目录，不碰 vendor）
node daniel-bot/app/scripts/upgrade-plugin.mjs --tgz "daniel-bot/releases/daniel-dsh-plugin-<新版本>.tgz"

# 2) 真执行（写 vendor）
node daniel-bot/app/scripts/upgrade-plugin.mjs --tgz "daniel-bot/releases/daniel-dsh-plugin-<新版本>.tgz" --apply

# 3) 改常量（§5，4 处）
# 4) 跑门禁
node daniel-bot/app/tests/g1-contract-gate.mjs
# 5) 打包（要有 PTY 的终端）
pnpm -C apps/desktop package:mac:arm64:unsigned
# 6) 按 §8 的 6 条清单验收
```

| 我遇到的情况 | 看哪一节 |
|---|---|
| 插件出了新版，要打进桌面端 | §1 → §4 |
| 不确定新包能不能用、壳兼不兼容 | §2 |
| 想自己复算 hash、核对某个目录 | §3 + `--verify` |
| 脚本报"同版本号但内容不同" | §6 |
| 升级后出问题要退回去 | §7 |
| 打包完了，怎么算验收通过 | §8 |
| 踩过的坑（gitignore / staging / 两套 hash） | §9 |

---

## 1. 触发场景（为什么升级）

出现以下任一情况就需要换插件版本，**不是"想到了才做"**：

1. **插件侧发了新版本**：`daniel-bot/packages/<版本>/` 出了新的 `releases/daniel-dsh-plugin-<版本>.tgz`
   （典型：修了插件 bug、加了工具、改了检索词/能力域、CLI 行为变更）。
2. **桌面端要发的 DMG 必须带最新能力**：DMG 里的插件是**打包那一刻的快照**，包内不换 = 用户装到的是旧能力。
3. **线上反馈指向插件**：用户报"某个工具不存在 / 参数不对 / 走了旧逻辑"，而源码已修 → 需要把新版打进壳再发。
4. **插件里有安全/合规修复**：必须在下一个 DMG 里带上，不能等"下次顺手"。

**不该用本手册的场景**：改插件的业务代码（走 `packages/<版本>/` 自己的出包流程）、
换 DSH 壳版本（走 `specs/` 的壳升级流程）、只改壳的 UI。

---

## 2. 前置检查

### 2.1 新 tgz 从哪来

**唯一合法来源**：`daniel-bot/packages/<版本>/` 用 `scripts/pack.mjs` 打出来的包，落到 `daniel-bot/releases/`。

```bash
cd daniel-bot/packages/<版本>
node scripts/pack.mjs --dest ../../releases
node scripts/clean-install-check.mjs --tgz ../../releases/daniel-dsh-plugin-<版本>.tgz
```

三条硬规矩：

1. **不要手工 `tar -czf` 重打包**：会带进 `._*`、`__pycache__`、`.DS_Store`，文件数与 hash 立刻对不上（实测：同一棵树手工重打，hash 会变）。
2. **不要改包里的 `package.json` 版本号**：版本号必须由源码 `packages/<版本>/package.json` 决定，改包内文件 = 造一个"假版本"。
3. **文件名必须是 `daniel-dsh-plugin-<version>.tgz`**：脚本拿文件名里的版本和包内 `package.json` 的版本做**严格相等**比对，不一致直接退出 3。

### 2.2 版本号规则

- 语义化版本 `MAJOR.MINOR.PATCH`，可带预发布后缀（`0.12.0-rc.1` 合法）。
- **版本号必须单调递增**；新版本号小于现状时脚本照跑但会打印
  `版本判定 …（⚠ 版本号变小：这是回退，走手册 §7 回滚流程）` ——回退是合法操作，只是别当成升级。
- **同一版本号不允许重打**（内容变了但版本号没变）：脚本默认**拒绝**（退出 3）。原因见 §6。

### 2.3 与当前 DSH 壳是否兼容

脚本会**自动拦**这些（不满足就退出 3，不会写盘）：

| # | 检查 | 为什么是硬的 |
|---|---|---|
| 1 | 包名 `daniel-dsh-plugin` | 壳里 `DANIEL_PLUGIN_NAME` 是常量，改名等于换了个插件 |
| 2 | 版本号 = 文件名版本 | 否则 MANIFEST/门禁/发布记录全部对不上 |
| 3 | 文件数 ≥ 100 | 防止拿到空包/半包 |
| 4 | `dsh.bundle.patch` 已声明**且指向的文件在包内** | 壳靠这个字段把插件当 bundle 加载；字段在、文件不在 = 首启挂载失败 |
| 5 | `vendor/data/daniel-cli/bin/daniel` 存在 | 壳的 `pluginRow` 把插件入口**写死**在这个路径（`apps/desktop/src/daniel-plugin.ts`），换路径必须同时改壳 |

脚本只**告警**（不拦，但你要人判）：

- `engines.node` 高于壳随包 Node（v24）→ 首启可能直接抛错；
- 包内出现软链（G1-1a 要求 0 软链）；
- `package.json` 的 `main` / `exports["."]` 指向的文件不在包内；
- `cordis.patch.yml` 不再声明 `id: daniel`（壳的恢复逻辑靠这个 row id 覆盖，不靠新增一个实例）。

**需要人判、脚本判不了的**：

- 插件的**配置键**是否还是壳写的 5 键（`entry / python / danielHome / timeoutMs / trace`）。
  壳每次写 patch 都会整段覆盖 `config`，插件若新增了配置键，壳不写就会丢 → 必须同时改壳的 `pluginRow`。
  验证：`node daniel-bot/app/tests/g1-contract-gate.mjs`（G1-2a 真跑写入 + 解析 + 断言键恰好 5 个）。
- 插件的**运行时依赖**（Python 版本、CLI 子命令）是否随包带齐 → 用新包跑一次 `node scripts/smoke.mjs --call daniel_status`。

---

## 3. root hash 口径（唯一口径）

**这套口径同时用于**：`upgrade-plugin.mjs`、G1 门禁（`app/tests/g1-contract-gate.mjs`）、本文档、`sync-daniel-plugin.mjs` 的打印。**不要另立一套**。

```
1. 范围：package/ 下所有普通文件；任意层级的 specs/、node_modules/、.git/ 目录整体跳过。
2. 逐文件：sha256 = 文件字节的 SHA-256（小写 hex），bytes = 文件字节数，
   path = 相对 package/ 的路径（/ 分隔，无前导 ./）。
3. 排序：按 path 的字节序升序（Buffer.compare）。
4. 拼串：每条 path\0bytes\0sha256\n（\0 = NUL，\n = 换行），按序喂给同一个 SHA-256。
5. 结果：64 位小写 hex 即 root hash。不含时间戳/权限/属主；软链不计入（出现即告警）。
```

三个容易记错的点：

- **是"先逐文件 hash、再拼串 hash"，不是把文件内容直接连起来 hash**；`bytes` 是十进制字符串。
- **排序按字节序**，不是本地化排序（`LC_ALL=C` 的直觉）。
- **权限、mtime、属主不进 hash**：所以"hash 对了"不等于"可执行位对了"（见 §8 第 3 条）。

基线（0.11.0，可用于自检）：

| 版本 | 文件数 | root hash |
|---|---|---|
| 0.11.0（deep 审计补齐 · **当前**） | 218 | `cca08a5a65578ee98d8aa2ec1944ab2c42d633a072da135d400c5ea4daaf4486` |
| 0.11.0（P1-READ 重打后） | 217 | `c81af4dd14bdf8ec3017b13672b41ca87a4f59ccbc25b47b573e31efd4ec4e2d` |
| 0.11.0（P1-READ 重打前） | 216 | `5b9cf918c4481edd26c36392e2e41a4ffd80bc1fa46edcbdf43edefe09b0a121` |

> 同一版本号下出现过**三个**包：P1-READ（5 条只读命令 ＋ 1 个测试文件 ＋ 假客户端增补）
> 用 `--allow-republish` 重打，216 → 217；2026-11-08 补齐 deep 提交审计（`lib/worker.py`
> ＋ `tests/test_deep_audit.py`，文件数 217 → 218）再次 `--allow-republish` 重打。
> **判定一律用上表第一行。**

复算任意目录（vendor / `.app` 内副本 / profile 副本都行）：

```bash
node daniel-bot/app/scripts/upgrade-plugin.mjs --verify "<目录>" --expect <hash>
```

---

## 4. 操作步骤（命令 + 每步预期输出）

> 全程在仓库根 `/Users/huyifan/Desktop/DeepSeek Harness` 下执行；源码树默认 `/tmp/dsh-build/dsh-src`。

### Step 0 · 记录现状 + 备份（30 秒，但回滚靠它）

```bash
node daniel-bot/app/scripts/upgrade-plugin.mjs --verify \
  /tmp/dsh-build/dsh-src/apps/desktop/resources/vendor/daniel-dsh-plugin
```

预期：`版本 0.11.0` / `文件数 218` / `root hash cca08a5a6557…`（与上表第一行一致）。
**把这三行贴到发布记录里**——回滚后要拿它比对。

```bash
mkdir -p /tmp/dsh-build/.plugin-backup
tar -czf "/tmp/dsh-build/.plugin-backup/daniel-dsh-plugin-$(date +%Y%m%d-%H%M%S)-$(node -p "require('/tmp/dsh-build/dsh-src/apps/desktop/resources/vendor/daniel-dsh-plugin/package.json').version").tgz" \
  -C /tmp/dsh-build/dsh-src/apps/desktop/resources/vendor daniel-dsh-plugin
```

预期：`ls -lh /tmp/dsh-build/.plugin-backup/` 多出一个约 6 MB 的 tgz。
**为什么必须备份**：vendor 目录被 `.gitignore` 忽略（`dsh-src/.gitignore:36`），`git checkout` 拿不回来（§9 坑 1）。

### Step 1 · 干跑

```bash
node daniel-bot/app/scripts/upgrade-plugin.mjs \
  --tgz "daniel-bot/releases/daniel-dsh-plugin-<新版本>.tgz"
```

**预期输出（真实样例，当前 0.11.0 tgz 对 0.11.0 现场）**：

```
插件升级 · 干跑（只解包到临时目录，不碰 vendor，退出前删除）
────────────────────────────────────────────────────────────────────────
  新包 tgz      /Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/releases/daniel-dsh-plugin-0.11.0.tgz
  tgz 体积      1,682,277 字节 / 1.6 MB
  解包位置      /tmp/dsh-build/.plugin-upgrade/36496（跑完即删）
  目标目录      /tmp/dsh-build/dsh-src/apps/desktop/resources/vendor/daniel-dsh-plugin

  ✓ package/package.json 存在
  ✓ 包名 daniel-dsh-plugin
  ✓ 版本 0.11.0 与文件名一致
  ✓ 文件数 210（阈值 ≥100）
  ✓ dsh.bundle.patch = ./cordis.patch.yml（文件在包内）
  ✓ 壳写死的入口 vendor/data/daniel-cli/bin/daniel

现状 → 新包
  版本        0.11.0                → 0.11.0
  文件数      210                   → 210
  总字节      5,518,706             → 5,518,706 字节（5.3 MB）
  目录类型    真目录                → 真目录（sync 用 rename 落地）
  版本判定    0.11.0（版本号没变）

影响范围（会变的文件）
  0 个文件会变：新包与现状逐文件相同（新增 0 / 修改 0 / 删除 0）

影响链（本脚本只改第 1 处）
  1. 源码树 vendor 目录（本脚本写入，被 .gitignore 忽略：/tmp/dsh-build/dsh-src/.gitignore:36）
  2. 打包产物 <App>.app/Contents/Resources/vendor/daniel-dsh-plugin（下次打包才生效）
  3. 首启 profile 副本 $DSH_HOME/profiles/desktop/node_modules/daniel-dsh-plugin（用户机器首启时由壳复制）

结论
  与现状一致，无需升级（版本 0.11.0、218 个文件、hash 完全相同）
  root hash（现状）：cca08a5a65578ee98d8aa2ec1944ab2c42d633a072da135d400c5ea4daaf4486
  root hash（新包）：cca08a5a65578ee98d8aa2ec1944ab2c42d633a072da135d400c5ea4daaf4486
  退出码 0；未写盘。
```

**怎么读这份输出**：

- `版本判定` 一行是结论：`升级` / `版本号没变` / `⚠ 版本号变小（回退）`。
- `影响范围` 是**逐文件**的差集（新增/修改/删除），不是"目录变了"这种模糊话；升级时至少核对条数与目录形态是否符合预期。
- `影响链` 告诉你**这次只改第 1 处**：第 2 处要重新打包，第 3 处是用户机器首启时由壳自己复制。
- 干跑**不写 vendor**；解包目录在退出时删除（`/tmp/dsh-build/.plugin-upgrade/<pid>`）。

**退出码 0 = 可以往下走**；3 = 包有问题（看 stderr 的 `upgrade-plugin: …`），先修包，不要绕过。

### Step 2 · 真执行

```bash
node daniel-bot/app/scripts/upgrade-plugin.mjs \
  --tgz "daniel-bot/releases/daniel-dsh-plugin-<新版本>.tgz" --apply
```

**预期输出（真实样例，0.11.0 → 0.12.0，测试镜像）**：

```
插件升级 · 真执行（会写 vendor）
…
影响范围（会变的文件）
  会变 3 个文件（新增 1 / 修改 2 / 删除 0），其余 208 个不变
  新增：lib/new-tool.js
  修改：lib/index.js、package.json
…
[1/3] 解包完成（见上）
[2/3] 调 sync 脚本：/tmp/dsh-build/dsh-src/apps/desktop/scripts/sync-daniel-plugin.mjs
      （下面是 sync 自己的输出；期望最后出现「✓ 已写入 …」）
✓ 已写入 /private/tmp/dsh-build/dsh-src/apps/desktop/resources/vendor/daniel-dsh-plugin
  daniel-dsh-plugin@0.12.0 · 211 个文件 · bfc5814560c3
[3/3] 复算 vendor

✓ 升级完成：daniel-dsh-plugin@0.12.0
  vendor 目录  ：/tmp/dsh-build/dsh-src/apps/desktop/resources/vendor/daniel-dsh-plugin
  目录类型     ：真目录（非软链）
  文件数       ：211
  root hash    ：bfc5814560c33a52a8b8ed9a9c4024c5976113d7b2341535556eee66eb180ffc
  与 tgz 一致  ：是（版本 / 文件数 / hash 三项都断言过）
```

判定通过的标准：**`[3/3]` 之后必须出现"与 tgz 一致：是"**。脚本自己会复算一遍，不靠 sync 的打印。

> `--apply` 只做三件事：解包 → 调 `sync-daniel-plugin.mjs --from <解包目录>` → 复算断言。
> **不打包、不 commit、不改 G1 常量**（常量在 Step 3 由人改）。

### Step 3 · 改常量

见 §5。改完为止，**别在没改常量时去跑 G1**（会红，且红得没有信息量）。

### Step 4 · 跑门禁

```bash
node daniel-bot/app/tests/g1-contract-gate.mjs
```

预期（关键三行）：

```
PASS G1-1a 插件版本与文件数 ← 期望: daniel-dsh-plugin@0.12.0，211 个文件，0 软链 | 实际: daniel-dsh-plugin@0.12.0，211 个文件，0 软链
PASS G1-1b root_hash 等于版本钉死的 known-good ← 期望: bfc5814560c3…（0.12.0） | 实际: bfc5814560c3…（一致）
PASS G1-1d 与 tgz 真源逐文件一致 ← 期望: 解包 211 文件，root_hash 相同，差集为空 | …
RESULT: PASS  G1 契约门禁 — 通过 …
```

任何一条 FAIL：先看它打印的"期望 vs 实际"，回 §3 查 hash 口径，或回 §5 查常量。

### Step 5 · 打包（有 PTY 的终端）

```bash
pnpm -C apps/desktop package:mac:arm64:unsigned
```

预期：`apps/desktop/.desktop-build/targets/mac-arm64/unsigned-artifacts/` 下出现新的 `.dmg`。
打包后**必须**做 §8 的第 4 条（`.app` 内副本 + hash），G2 的 G2-6 只判"存在 + 名字 + ≥100 文件"，不判版本与 hash。

### Step 6 · 首启 + 恢复演练

见 §8 第 5、6 条。首启验证要在**测试 HOME**上做，不要污染日常 profile。

---

## 5. 要改的常量（文件 + 行号）

行号以 2026-11-02 的工作区为准；脚本每次运行会打印**实时**行号与建议值，以脚本输出为准。

| # | 文件:行 | 内容 | 不改的后果 |
|---|---|---|---|
| 1 | `app/tests/g1-contract-gate.mjs:44` | `const KNOWN_GOOD = { version, files, rootHash }` | G1-1a / G1-1b 直接 FAIL（门禁永久红） |
| 2 | `app/tests/g1-contract-gate.mjs:33` | `tgz: join(APP, '..', 'releases', 'daniel-dsh-plugin-0.11.0.tgz')` | G1-1d 拿旧包比对，报"与 tgz 真源不一致"；旧包被删后变成 SKIP（假绿风险） |
| 3 | `app/desktop-patches/CHECKPOINT.md:59` | `# 期望输出：daniel-dsh-plugin@0.11.0 · 218 个文件 · cca08a5a6557` | 下一个人照文档跑，看到数字不同会以为升级失败 |
| 4 | `README.md:53` | `node scripts/clean-install-check.mjs --tgz ../../releases/daniel-dsh-plugin-0.11.0.tgz` | 源码包自检命令指向旧包 |

脚本打印的样子（真实输出）：

```
要改的常量（脚本不会替你改：旧版本号/哈希写死在源码与文档里）
  app/tests/g1-contract-gate.mjs
    :33  现：tgz: join(APP, '..', 'releases', 'daniel-dsh-plugin-0.11.0.tgz'),
           改：tgz: join(APP, '..', 'releases', 'daniel-dsh-plugin-0.12.0.tgz'),
    :44  现：const KNOWN_GOOD = { version: '0.11.0', files: 218, rootHash: 'cca08a5a…' }
           改：const KNOWN_GOOD = { version: '0.12.0', files: 211, rootHash: 'bfc581…' }
  app/desktop-patches/CHECKPOINT.md
    :59  现：# 期望输出：daniel-dsh-plugin@0.11.0 · 218 个文件 · cca08a5a6557
           改：# 期望输出：daniel-dsh-plugin@0.12.0 · 211 个文件 · bfc5814560c3
  README.md
    :53  现：node scripts/clean-install-check.mjs --tgz ../../releases/daniel-dsh-plugin-0.11.0.tgz
           改：node scripts/clean-install-check.mjs --tgz ../../releases/daniel-dsh-plugin-0.12.0.tgz
```

**不要改的"旧版本号"**（改了是造假/制造混乱）：

- `app/tests/QA-REPORT.md`、`specs/DECISIONS-A.md`、`specs/S2-方案设计.md`、`specs/RESUME-A.md`、`docs/versions/06-工程推进管线.md`
  —— 这些是**历史快照/当时的真实验收记录/当期的计划文档**，不是当前配置。QA-REPORT 改了就失去"当时跑过什么"的证据价值。

改完自检：

```bash
grep -rn "daniel-dsh-plugin-0\.1[0-9]" daniel-bot/app daniel-bot/README.md | grep -v QA-REPORT
```

预期：只剩新版本号（以及 CHECKPOINT 里可能的历史上下文说明，如果有就一起改）。

---

## 6. 新版本 hash 与旧版本不同时，脚本怎么提示

先给结论表（脚本对四种组合的处理）：

| 现状版本 | 新包版本 | hash | 脚本判定 | 退出码 |
|---|---|---|---|---|
| 0.11.0 | 0.12.0 | 不同 | **正常升级**：打印 旧→新、差异文件清单、要改的常量 | 0（干跑） |
| 0.11.0 | 0.11.0 | **相同** | **与现状一致，无需升级**，不写盘 | 0 |
| 0.11.0 | 0.11.0 | **不同** | **拒绝**：同版本号重打 | 3 |
| 0.12.0 | 0.11.0 | 不同 | 允许，但标 **⚠ 版本号变小：这是回退**，指向 §7 | 0（干跑） |

### 6.1 版本变了、hash 也不同（正常升级）

脚本不会只说"hash 不一样"，而是**摊开差异**（以下为真实输出）：

```
现状 → 新包
  版本        0.11.0                → 0.12.0
  文件数      210                   → 211
  总字节      5,518,706             → 5,518,735 字节（5.3 MB）
  目录类型    真目录                → 真目录（sync 用 rename 落地）
  版本判定    0.11.0 → 0.12.0（升级）

影响范围（会变的文件）
  会变 3 个文件（新增 1 / 修改 2 / 删除 0），其余 208 个不变
  新增：lib/new-tool.js
  修改：lib/index.js、package.json

结论
  干跑通过：0.11.0 → 0.12.0，3 个文件会变
  旧 hash   5b9cf918c4481edd26c36392e2e41a4ffd80bc1fa46edcbdf43edefe09b0a121
  新 hash   bfc5814560c33a52a8b8ed9a9c4024c5976113d7b2341535556eee66eb180ffc
  新文件数  211
  下一步：确认无误后把 --dry-run 换成 --apply 真执行
```

要看的三个数字：**旧 hash、新 hash、会变的文件数**。三者与发布说明对得上，才允许 `--apply`。

### 6.2 版本没变、hash 变了（同版本重打，拒绝）

```
  ⚠ 同版本号但内容不同（同名重打）
     0.11.0 现状 hash：5b9cf918c4481edd26c36392e2e41a4ffd80bc1fa46edcbdf43edefe09b0a121
     0.11.0 新包 hash：a17ced1fad7b945a496f45ef4e0addbe1a169f1e111bc207451cb6c189e7dfda

结论
  ✗ 拒绝执行：0.11.0 是同版本重打（内容变了但版本号没变）
  已发布过的版本号不允许静默替换（G1 的 KNOWN_GOOD 与已发 DMG 会对不上）。
  若确认要重打：加 --allow-republish，并在 specs/DECISIONS-A.md 记一条。
```

stderr 同时给出（退出码 3）：

```
upgrade-plugin: 同版本号不同内容：0.11.0 的 hash 1ce31013… → a17ced1f…，拒绝静默替换（确需重打请加 --allow-republish）
```

**为什么默认拒绝**：同名不同内容意味着"同一个版本号能对应两个包"。已经装出去的 DMG、G1 的 KNOWN_GOOD、发布记录会互相矛盾，事后无法判断用户装的是哪一份。
真需要重打（例如包被污染必须原地替换）：**先升版本号**（推荐）；确实不能升版本，才用 `--allow-republish`，并在 `specs/DECISIONS-A.md` 留一条记录说明原因。

### 6.3 版本、hash 都一样（无需升级）

```
结论
  与现状一致，无需升级（版本 0.11.0、218 个文件、hash 完全相同）
  root hash（现状）：cca08a5a65578ee98d8aa2ec1944ab2c42d633a072da135d400c5ea4daaf4486
  root hash（新包）：cca08a5a65578ee98d8aa2ec1944ab2c42d633a072da135d400c5ea4daaf4486
  退出码 0；未写盘。
```

这是**最常见的一次运行**（确认现场与发布包一致）。此时不用 `--apply`，也不用改常量。

---

## 7. 回滚

### 7.1 回滚到哪里

| 层 | 回滚方式 | 说明 |
|---|---|---|
| 源码树 vendor 目录 | 用旧 tgz 再跑一次本脚本（`--apply`） | 唯一可靠方式；目录被 gitignore，git 救不了 |
| G1 常量（4 处） | 手工改回旧版本号/文件数/hash | 脚本不替你改，也不替你改回 |
| 已打包的 DMG | 用旧 tgz 重新打包 | 产物不可"降级"，只能重打 |
| 已发布的自更新渠道 | `apps/desktop/scripts/rollback-desktop-channel.ts`（需发布记录 + 凭据） | **不走本手册**，此处只提一句 |

### 7.2 标准回滚（源码树 + 常量）

```bash
# 1) 用上一个版本的 tgz 再跑一次（脚本会提示"版本号变小：这是回退"，属预期）
node daniel-bot/app/scripts/upgrade-plugin.mjs \
  --tgz "daniel-bot/releases/daniel-dsh-plugin-<上一版本>.tgz" --apply

# 2) 核对：版本/文件数/hash 是否等于 Step 0 记录的那三行
node daniel-bot/app/scripts/upgrade-plugin.mjs --verify \
  /tmp/dsh-build/dsh-src/apps/desktop/resources/vendor/daniel-dsh-plugin --expect <上一版本 hash>

# 3) 常量改回（§5 的 4 处）
# 4) 复跑门禁
node daniel-bot/app/tests/g1-contract-gate.mjs
```

### 7.3 没有旧 tgz / vendor 已损坏

用 Step 0 的备份恢复（这就是为什么升级前必须备份）：

```bash
rm -rf /tmp/dsh-build/dsh-src/apps/desktop/resources/vendor/daniel-dsh-plugin
tar -xzf /tmp/dsh-build/.plugin-backup/<备份文件>.tgz \
  -C /tmp/dsh-build/dsh-src/apps/desktop/resources/vendor
# 备份的是"已解包目录"，解出来就是 vendor/daniel-dsh-plugin，不需要再跑 sync
node daniel-bot/app/scripts/upgrade-plugin.mjs --verify \
  /tmp/dsh-build/dsh-src/apps/desktop/resources/vendor/daniel-dsh-plugin --expect <备份时记录的 hash>
```

> 备份是"目录快照"，里面可能带 `.staging-*` 残留吗？不会——sync 成功时会把 staging 挪走。
> 但如果备份时目录里已有残留，恢复后先删 `vendor/.staging-*` 再继续（§9 坑 2）。

### 7.4 git 能帮上什么（和帮不上什么）

- `dsh-src` 是 git 仓库，但 **`apps/desktop/resources/vendor/` 在 `.gitignore:36` 被忽略** → `git checkout` / `git clean` 都不会恢复它。
- 本工作区（`daniel-bot/`）**不是 git 仓库**（`git rev-parse` 报 not a git repository）→ 常量改动没有版本历史可回退，只能手工改回。
- 结论：**回滚靠"旧 tgz + 备份"，不靠 git**。

---

## 8. 6 条升级验收清单

判定顺序就是 1→6：**前一条不通过，后面不用做**。每条都给"命令 / 期望 / 失败怎么办"。

> 这份清单是**唯一版本**：G2 的 G2-6、G4 的文件头都只做静态引用（指到本节），不复制判据——复制一份就等于养两套，早晚对不上。

### ① `tar -tzf` 解出的 `package/package.json` 版本 = 期望版本

```bash
tar -tzf "daniel-bot/releases/daniel-dsh-plugin-<版本>.tgz" | grep -c '^package/'        # 条目数
tar -xzf "daniel-bot/releases/daniel-dsh-plugin-<版本>.tgz" -O package/package.json | grep -E '"(name|version)"'
```

期望：

```
"name": "daniel-dsh-plugin",
"version": "<版本>",
```

且 `"version"` 与文件名里的 `<版本>` **逐字符相同**（脚本会在干跑里再判一次并打印 `✓ 版本 <版本> 与文件名一致`）。

失败 → 包打错了：回 `packages/<版本>/` 重新 `pack.mjs`，不要手改包内 JSON。

### ② 插件 root hash 与脚本输出一致

```bash
node daniel-bot/app/scripts/upgrade-plugin.mjs --verify \
  /tmp/dsh-build/dsh-src/apps/desktop/resources/vendor/daniel-dsh-plugin --expect <干跑打印的新 hash>
```

期望：

```
  ✓ 与期望一致：包名、文件数、root hash 全部对上
```

失败 → 三种可能：vendor 没换成功（重跑 `--apply`）、`--src` 指错树、口径用错（§3）。

### ③ vendor 目录是**真目录**（非软链）、文件数一致

```bash
V=/tmp/dsh-build/dsh-src/apps/desktop/resources/vendor/daniel-dsh-plugin
stat -f "%HT" "$V"                                   # 期望：Directory（软链会显示 Symbolic Link）
find "$V" -type f | wc -l                            # 期望：与清单文件数一致（0.11.0 = 213）
find "$V" -type l | wc -l                            # 期望：0
ls -a "$V/.." | grep -c '^\.staging-'                # 期望：0
ls -l "$V/vendor/data/daniel-cli/bin/daniel" | cut -c1-10   # 期望：-rwxr-xr-x（可执行位，hash 查不出来）
```

期望四连：`Directory` / `213` / `0` / `0` / `-rwxr-xr-x`。

**为什么单独查真目录**：electron-builder 的 `extraResources` 复制软链会得到软链；asar 包里则是读不到的。壳的 `embedDanielPlugin` 也按普通目录用 `rename` 落地，软链会在某些路径上直接失败。

### ④ 打包后包内 `Contents/Resources/vendor/daniel-dsh-plugin` 存在且 hash 一致

```bash
hdiutil attach -nobrowse -readonly "daniel-bot/releases/<新>.dmg"
# 卷名取自 `ls /Volumes`，一般是 "Daniel Bot"
node daniel-bot/app/scripts/upgrade-plugin.mjs --verify \
  "/Volumes/Daniel Bot/Daniel Bot.app/Contents/Resources/vendor/daniel-dsh-plugin" --expect <hash>
hdiutil detach "/Volumes/Daniel Bot"
```

期望：`类型 真目录` + `文件数 218` + `root hash` 与 ② 完全相同。

自动门禁：`node daniel-bot/app/tests/g2-packaging-gate.mjs --dmg <dmg>` → `PASS G2-6 内嵌插件 …`。
注意 **G2-6 只判"存在 + name + 文件数 ≥100"，不判版本、不判 hash**——所以 ④ 的 `--verify` 不能省。

失败 → 打包时 vendor 目录不存在或被裁：检查打包前是否跑过 Step 2、`electron-builder-config.mjs` 的 `extraResources` 是否还指向 `resources/vendor/daniel-dsh-plugin`。

### ⑤ 首启后 profile 里存在，且 bundles 含它

```bash
DSH_HOME="${DSH_HOME:-$HOME/Library/Application Support/Daniel Bot/dsh-home}"
P="$DSH_HOME/profiles/desktop"

test -f "$P/node_modules/daniel-dsh-plugin/package.json" && echo "plugin present"
node -p "JSON.parse(require('fs').readFileSync(process.argv[1],'utf8')).dsh.profile.bundles.includes('daniel-dsh-plugin')" "$P/package.json"
node daniel-bot/app/scripts/upgrade-plugin.mjs --verify "$P/node_modules/daniel-dsh-plugin" --expect <hash>
```

期望：`plugin present` / `true` / `文件数 218` + hash 一致。

**为什么还要单独查**：`.app` 里有副本 ≠ 用户 profile 里有副本。首启复制是 `embedDanielPlugin` 做的，它只在"目录不存在或 hash 不同"时才重写。
**验证时机**：装新 DMG → 启动到登录页 → 关掉 → 再查。旧 `.app` 不会更新这份副本（所以"用户升级"= 换新 `.app`）。

### ⑥ 崩溃恢复后插件仍在

代码级等价验证（**必须做，能自动化**）：

```bash
node daniel-bot/app/tests/g1-contract-gate.mjs
```

期望三行：

```
PASS G1-3a 崩溃恢复后插件仍在（真跑 disableAllPlugins） ← 期望: 3 个用例全过（CONTROL 删插件 / PRODUCT 恢复后插件+5键 patch / NEGATIVE 不凭空激活） | 实际: pass 3 / fail 0
PASS G1-3b 恢复路径顺序正确：sanitize 之后立刻重写 patch ← …
```

真机演练（**在测试 HOME 上做，别动日常 profile**）：

```bash
P="$DSH_HOME/profiles/desktop/cordis.patch.yml"
cp "$P" /tmp/cordis.patch.yml.before
printf 'this: [is: broken\n' > "$P"          # 写坏，触发恢复
open -a "Daniel Bot"                          # 启动，等 15s
ls "$DSH_HOME/profiles/desktop/" | grep 'cordis.patch.yml.bak-'   # 期望：有 .bak-<时间戳>
grep -c '^    \(entry\|python\|danielHome\|timeoutMs\|trace\):' "$P"  # 期望：5
node -p "JSON.parse(require('fs').readFileSync(process.argv[1],'utf8')).dsh.profile.bundles.includes('daniel-dsh-plugin')" \
  "$DSH_HOME/profiles/desktop/package.json"   # 期望：true
```

再重启一次，上面三条仍然成立 → ⑥ 通过。

**已知局限**：G4 门禁目前是占位（只 SKIP + 给复验步骤），真机这一步没有自动化；`G1-3a` 是它的代码级等价物，不能互相替代。

### 清单与门禁的对应关系

| 清单项 | 自动门禁 | 备注 |
|---|---|---|
| ① 版本 = 期望 | 干跑输出；G1-1a | 门禁只在 vendor 上判，tgz 侧靠脚本 |
| ② hash 一致 | G1-1b / G1-1d；`--verify` | G1-1d 还会与 tgz 做双向差集 |
| ③ 真目录 + 文件数 | G1-1a（软链必须 0）；`--verify` | 可执行位只能人查 |
| ④ `.app` 内副本 | G2-6（只判存在/名字/≥100） | 版本/hash 用 `--verify` |
| ⑤ 首启 profile | 无（G3 不查插件） | 手工三条命令 |
| ⑥ 崩溃恢复 | G1-3a / G1-3b；G4 占位 | 真机演练手工 |

---

## 9. 已知坑

### 坑 1 · vendor 目录被 .gitignore，git 救不回来

`dsh-src/.gitignore:36` 是 `apps/desktop/resources/vendor/`。所以：

- `git status` **看不到** vendor 的变化 → 别以为"没改"；
- `git checkout -- .` / `git clean -fd` **不会**恢复它 → 回滚只能靠旧 tgz 或备份（§7）；
- 代码评审时你以为在评审"插件内容"，其实评审不到（内容在 tgz 里）→ 要审就审 tgz 的 hash + 差异清单。

### 坑 2 · staging 残留（`.staging-<pid>`）

`sync-daniel-plugin.mjs` 在 `vendor/` 根下建 `.staging-<pid>` 再 `rename` 落地；进程被 `kill -9`、磁盘满、或两次并发运行时会留下它：

- 症状：`vendor/` 里多出 `.staging-12345/`，**每次幂等运行多出约 5.7 MB**；G1-4b 会判 FAIL。
- 处置：`rm -rf /tmp/dsh-build/dsh-src/apps/desktop/resources/vendor/.staging-*`。
- 预防：**不要并发跑** sync / 本脚本；失败后重跑一次（脚本会先 `rm -rf` 自己的 staging）。

### 坑 3 · 两套 hash 口径，千万别互比

| 来源 | 拼串 | 0.11.0 的结果 |
|---|---|---|
| **本手册 / `upgrade-plugin.mjs` / G1 门禁** | `path\0bytes\0sha256\n` | `cca08a5a65578ee98d8aa2ec1944ab2c42d633a072da135d400c5ea4daaf4486` |
| `seed-profile.sh --write-manifest` 生成的 `PLUGIN-MANIFEST.json` | `sha256  size  path\n`（两个空格分隔） | `sha256:6395329196c4bacd0ae63dc9e28f654e60ae0c5f7dec9737c4b5b4139ca56309`（P1-READ 重打前的水印；本包未生成清单） |

两者**都叫 root hash**，但结果不同。拿 seed 的 `root_hash` 去对 G1 / 本脚本，会得到"永远不一致"的假故障。
**判定一律以口径 A（本手册 §3）为准**；seed 的清单是打包时给运行期自检用的，两者不要交叉比对。

### 坑 4 · "文件数"不等于 `tar -tzf` 的条目数

清单口径会跳过 `specs/`、`node_modules/`、`.git/`。0.11.0 恰好 `tar` 条目 = 210 = 清单文件数（包里本来就没有这些目录）。
将来包里若混进 `specs/`，`tar` 条目会**大于**清单文件数——这时不要以为升级失败，按 `--verify` 打印的"文件数"为准。

### 坑 5 · hash 不含权限，可执行位要单独查

`vendor/data/daniel-cli/bin/daniel` 必须是 `-rwxr-xr-x`。用 `cp` 手工覆盖可能丢可执行位，而 hash 完全正常。
`sync-daniel-plugin.mjs` 用 `rename` 搬目录、`cpSync` 保留 mode，所以**用它**，别手工 `cp -R`。

### 坑 6 · 同版本重打（脚本会拒绝，别绕过）

见 §6.2。绕过（`--allow-republish`）的代价是：G1 的 KNOWN_GOOD 与已发 DMG 指向两份不同的字节，事后无法解释。
**默认做法：升版本号。**

### 坑 7 · `.app` 内副本是打包时快照，不会跟着 vendor 变

改完 vendor 后不重新打包，DMG 里还是旧插件。判据：`.app` 内 `package.json` 的版本 = 你刚升的版本（§8 ④）。
反过来，旧 `.app` 的用户首启也只会复制旧副本——"升级"对用户意味着**换新 DMG**。

### 坑 8 · 首启复制是"按 hash 决定要不要重写"

`embedDanielPlugin` 只在目标不存在或 hash 不同时重写。所以：

- 想看首启是否真的换了插件：先确认 `$DSH_HOME/profiles/desktop/node_modules/daniel-dsh-plugin` 的 hash 是旧版，再装新 DMG 首启，再查变成新版。
- 如果 profile 副本 hash 已经等于新包（比如上次首启已经复制过），首启不会重写（正常，不是 bug）。

### 坑 9 · macOS 的 `._*` / `.DS_Store` / `__pycache__`

手工重打包最常见的污染源。它们会让文件数与 hash 一起变，且 `tar -tzf` 里看起来"只是多了几个小文件"。
`pack.mjs` 已经有排除规则（X02/X03/X26 + `.DS_Store`），**所以只用 `pack.mjs` 出包**。

### 坑 10 · 别把 `--src` 指到工作区里的 `daniel-bot/`

`--src` 要的是 **DSH 源码树**（必须有 `apps/desktop/scripts/sync-daniel-plugin.mjs`）。指错会退出 2：
`--src 下没有 apps/desktop/scripts/sync-daniel-plugin.mjs：…（给错源码树了？）`。
另外真执行时 `--src` 必须在 `/tmp/dsh-build` 下（脚本边界），干跑可以读任意树。

### 坑 11 · 别手工改 `vendor` 里的文件"先对付一下"

vendor 是生成物。手改之后：hash 与 tgz 对不上、G1-1d 报差集、下次 sync 直接覆盖你的改动。要改就改 `packages/<版本>/` 再出包。

### 坑 12 · 发布记录里要留 hash，不要只留版本号

同一个版本号理论上只能对应一份字节（本手册的规矩），但历史包/重打包确实发生过。发布记录里写清
**版本 + 文件数 + root hash（64 位全量）**，三个月后才查得清"用户装的是哪一份"。

---

## 10. 附录：退出码、参数、边界

### 退出码

| 码 | 含义 | 典型触发 |
|---|---|---|
| 0 | 成功 | 干跑通过 / `--apply` 通过 / `--verify` 一致 / 无需升级 |
| 2 | 参数错 | 缺 `--tgz`、未知参数、`--apply` 与 `--dry-run` 同给、`--src` 不是源码树、`--apply` 时 `--src` 在 `/tmp/dsh-build` 外 |
| 3 | 校验失败 | tgz 不存在 / 不是 tgz / 包名不符 / 版本与文件名不符 / 文件数 <100 / 缺 `dsh.bundle.patch` / 入口路径不存在 / 同版本不同内容 / `--verify` 不一致 |
| 4 | 执行失败 | sync 脚本失败、写后文件数或 hash 不符、未预期异常 |

### 参数

```
--tgz <path>        新插件包（文件名 daniel-dsh-plugin-<version>.tgz）
--src <dir>         源码树根，默认 /tmp/dsh-build/dsh-src
--dry-run           干跑（默认；与 --apply 互斥）
--apply             真执行（唯一会写盘的开关）
--allow-republish   允许同版本号重打（默认拒绝，§6.2）
--verify <dir>      只核验目录（vendor / .app 内副本 / profile 副本）
--expect <hash>     配合 --verify 断言 hash（可带 sha256: 前缀）
-h, --help          帮助
```

### 写盘边界（脚本自己守的）

- 只写 `/tmp/dsh-build/` 下：解包临时目录 `/tmp/dsh-build/.plugin-upgrade/<pid>` + 源码树 vendor 目录；
- 不改 `dsh-src` 的**源码**（vendor 是 gitignore 的生成物，由 sync 重写）；
- 不打包、不 commit、不改 G1 常量、不碰 `daniel-bot/` 下任何文件（只读扫描常量）。

### 相关文件

| 文件 | 作用 |
|---|---|
| `daniel-bot/app/scripts/upgrade-plugin.mjs` | 本手册对应的脚本（唯一实现） |
| `daniel-bot/app/tests/g1-contract-gate.mjs` | G1 契约门禁（hash/5 键/恢复/幂等） |
| `daniel-bot/app/tests/g2-packaging-gate.mjs` | G2 打包门禁（`.app` 内副本存在性） |
| `daniel-bot/app/tests/g4-crash-recovery-gate.mjs` | G4 真机恢复（占位） |
| `apps/desktop/scripts/sync-daniel-plugin.mjs` | 真正搬目录的脚本（幂等） |
| `apps/desktop/src/daniel-plugin.ts` | 壳侧：`DANIEL_PLUGIN_NAME`、`embedDanielPlugin`、5 键 `pluginRow` |
| `apps/desktop/scripts/electron-builder-config.mjs` | `extraResources` 把 vendor 打进 `.app` |
