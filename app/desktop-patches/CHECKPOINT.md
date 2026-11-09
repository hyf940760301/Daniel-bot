# CHECKPOINT · 第一组改造（独立 home / 内嵌插件 / 隐藏插件 UI）

> 时间：2026-11-01 18:27（Asia/Shanghai）· 状态：**代码已改完并已跑通类型与单测；未打包**
> 2026-11-08 插件内容更新：`lib/worker.py` 补 deep 提交审计（`_audit_deep_commit`，与 open 同一份 `daniel account audit`）、`lib/index.js` deep commit 回传「审计」块、新增 `tests/test_deep_audit.py`；tgz 重打为 **218 文件 / `cca08a5a65578ee98d8aa2ec1944ab2c42d633a072da135d400c5ea4daaf4486`**，G1 KNOWN_GOOD 与 `upgrade-plugin.mjs` BASELINE 已同步。
> 源码位置：`/tmp/dsh-build/dsh-src`（**会被关机清空**，本文件＋补丁已落工作区）
> 基线 commit：`ce7073d5`

---

## 1. 已完成（按文件）

| 文件 | 改动 |
|---|---|
| `apps/desktop/src/daniel-home.ts`（新） | 定义两个独立 home：默认 `~/Library/Application Support/Daniel Bot/dsh-home`（`$DSH_HOME` 可覆盖）与 `.../daniel-home`（`$DANIEL_HOME` 可覆盖）；`installDanielHomes()` 建目录并 chmod 0700，同时把两个变量写回 `process.env`（Host 子进程继承）；**不迁移/不读取旧 `~/.dsh`**（D-019）。 |
| `apps/desktop/src/main.ts` | ① `main()` 第一行调用 `installDanielHomes()`（早于 `resolveDesktopPaths()` 与 login-shell 读环境）；② 新增 `danielPluginSource()`：打包态 `Resources/vendor/daniel-dsh-plugin`，开发态 `resources/vendor/...`；③ 两处构造 `DesktopProjectManager` 时传入 `{pluginSource, danielHome}`（含崩溃恢复那处）。 |
| `apps/desktop/src/daniel-plugin.ts`（新） | 插件落地核心：`embedDanielPlugin()` 把插件复制成真目录 `$DSH_HOME/profiles/desktop/node_modules/daniel-dsh-plugin`（**按 218 文件 sha256 清单幂等**，一致则不重写、保留可执行位、staging+rename 原子替换）；`activateDanielPlugin()` 追加 `dsh.profile.bundles`；`writeDanielProfilePatch()` 写 profile 的 `cordis.patch.yml`（**5 键 entry/python/danielHome/timeoutMs/trace**，行 id=`daniel`，与插件自带 bundle patch 同 id ⇒ 原地覆盖、不产生第二条行）；`writeDanielAppOverlay()` 写 `<DANIEL_HOME>/app-overlay.yml`（同 5 键）。 |
| `apps/desktop/src/project-manager.ts` | 构造函数加可选第三参 `daniel`（不传＝旧行为，官方测试不受影响）；`applyRelease()` 在写锁内调用 `installDanielPlugin()`（复制→激活→写 patch/overlay）；`disableAllPlugins()` 改为 **sanitize 时保留 `daniel-dsh-plugin` 在 bundles 里**，并在 sanitize 后立即重写 patch/overlay（关键：否则崩溃恢复后插件消失）。 |
| `packages/bundle/web-app/cordis.patch.yml` | 删 `ui-plugin-manager`（插件页）、`ui-settings-plugin-inventory`（设置页插件清单）、`tool-plugin-manager`（agent 工具）三条行，留说明注释防 rebase 回填。 |
| `packages/bundle/web-app/presets/cordis.patch.yml`、`standard.patch.yml`、`ptc.patch.yml` | 删三份 preset 里的 `tool-plugin-manager` 插入行（**必须删**：仅删 web-app 那条 disable 无效，preset 会在会话里重新启用该工具）。 |
| `apps/desktop/scripts/sync-daniel-plugin.mjs`（新） | 把 `daniel-dsh-plugin-0.11.0.tgz` 解到 `apps/desktop/resources/vendor/daniel-dsh-plugin`（幂等、校验包名与 `dsh.bundle.patch`、保留可执行位、打印文件数与 digest）。 |
| `apps/desktop/package.json` | 新增脚本 `sync:daniel-plugin`。 |
| `apps/desktop/scripts/electron-builder-config.mjs` | `extraResources` 增加 `resources/vendor/daniel-dsh-plugin → Resources/vendor/daniel-dsh-plugin`（asar 外真目录）。 |
| `.gitignore` | 忽略 `apps/desktop/resources/vendor/`（生成物，tgz 才是真源）。 |
| `apps/desktop/tests/daniel-plugin.spec.ts`（新） | 5 条单测：复制幂等、损坏副本重植、bundles 只追加一次、5 键齐全、**崩溃恢复后插件仍在**、插件源缺失时壳仍可用。 |

### 已跑通的验证（原始输出摘要）
- `tsc -b`（`cd apps/desktop && ../../node_modules/.bin/tsc -b`）→ **EXIT 0**。
- `pnpm -C apps/desktop run build` 等价（`node apps/desktop/node_modules/pnpm/bin/pnpm.cjs -C apps/desktop run build`）→ **EXIT 0**，产出 `lib/main.js 846.03 kB`、welcome 资源正常。
- `vitest run apps/desktop/tests/project-manager.spec.ts` → **35 passed / 1 skipped**（证明未传 daniel 配置时官方行为零变化）。
- `vitest run apps/desktop/tests/daniel-plugin.spec.ts` → **5 passed**。
- 组装验证（真实 `loadProfileDirectory` + `composeEntries`，profile=临时目录）：`skippedBundles: []`，layers = base/web-app/**daniel-dsh-plugin**，**`- id: daniel` 只有 1 行**，config 含 5 键。
- YAML 校验（`loadOverlayPatches` 解析 4 个改动过的 yml）：全部可解析，`ui-plugin-manager` / `ui-settings-plugin-inventory` / `tool-plugin-manager` 均已不存在。

---

## 2. 未完成 / 卡点

1. **未打包**（按纪律不跑）：DMG 需用户在有 PTY 的终端跑。
2. **`apps/desktop/resources/vendor/daniel-dsh-plugin` 未进补丁**（`.gitignore` 忽略，218 文件/约 5.3 MB）：源码树被 `/tmp` 清空后必须重新生成一次，否则 `extraResources` 会在打包时报源目录不存在。
3. `daniel-bot/app/desktop-patches/CHANGES.md` 未写（本文件已覆盖同等信息；正式 CHANGES.md 待补）。
4. 未跑官方 e2e：`apps/cli/tests/web-agent-presets.e2e.ts`、`apps/cli/tests/profiles/web/tests/*plugin-manager*.expected.e2e.ts` 仍按上游把 `plugin_manager` 工具/插件页列为预期，**改完后这些 e2e 预期会失败**（预期内，属二开分叉）。
5. `python` 仍为 `python3`（系统解释器）：本机有，干净机可能没有 → 第二组「Python 接线」改为随包 `Resources/runtime/python/bin/python3`。

---

## 3. 下一步（可执行）

```bash
# 0) 重新拿到源码树（/tmp 已清空后）
#    按原方式复制/稀疏检出官方仓库到 /tmp/dsh-build/dsh-src，并 pnpm install，checkout 到 ce7073d5
cd /tmp/dsh-build/dsh-src

# 1) 应用补丁
git apply "/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/app/desktop-patches/WIP-embed-and-isolate.patch"

# 2) 生成随包插件目录（可重复执行；tgz 是唯一真源）
node apps/desktop/scripts/sync-daniel-plugin.mjs \
  --from "/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/releases/daniel-dsh-plugin-0.11.0.tgz"
# 期望输出：daniel-dsh-plugin@0.11.0 · 218 个文件 · cca08a5a6557
#   （2026-11-08「deep 提交补审计」重打后的基线；P1-READ 重打后是 217 · c81af4dd14bd，
#     更早是 216 · 5b9cf918c4481edd）

# 3) 类型 + 单测（打包前自检）
cd apps/desktop && ../../node_modules/.bin/tsc -b && cd ../..
node_modules/.bin/vitest run apps/desktop/tests/daniel-plugin.spec.ts apps/desktop/tests/project-manager.spec.ts

# 4) 打包（用户在有 PTY 的终端跑，本组未执行）
pnpm -C apps/desktop package:mac:arm64:unsigned

# 5) 打包后必须核对的 5 条
#    a. App 内 Resources/vendor/daniel-dsh-plugin/package.json 存在
#    b. 首次启动后 ~/Library/Application Support/Daniel Bot/dsh-home 与 daniel-home 存在且 0700
#       （~/Library/Application Support/DeepSeek Harness 不应新增 dsh 数据）
#    c. $DSH_HOME/profiles/desktop/node_modules/daniel-dsh-plugin/package.json 存在
#    d. $DSH_HOME/profiles/desktop/package.json 的 dsh.profile.bundles 含 daniel-dsh-plugin
#    e. profile 的 cordis.patch.yml 含 5 键；重启一次后仍存在
# 6) 崩溃恢复演练：删坏 profile/cordis.patch.yml 触发恢复 → 重启后 c/d/e 仍成立
```

---

## 4. `git status --short`（导出补丁时）

```
 M .gitignore
 M apps/desktop/package.json
 M apps/desktop/scripts/electron-builder-config.mjs
 A apps/desktop/scripts/sync-daniel-plugin.mjs
 A apps/desktop/src/daniel-home.ts
 A apps/desktop/src/daniel-plugin.ts
 M apps/desktop/src/main.ts
 M apps/desktop/src/project-manager.ts
 A apps/desktop/tests/daniel-plugin.spec.ts
 M packages/bundle/web-app/cordis.patch.yml
 M packages/bundle/web-app/presets/cordis.patch.yml
 M packages/bundle/web-app/presets/ptc.patch.yml
 M packages/bundle/web-app/presets/standard.patch.yml
```

`git diff --stat`：13 个文件，+731 / −24。补丁：`daniel-bot/app/desktop-patches/WIP-embed-and-isolate.patch`（942 行，新文件以 `new file` 形式包含，可直接 `git apply`）。

---

## 5. 最可能出问题的两处 + 验证方式

1. **崩溃恢复把 bundles 重置回官方模板**（`project-manager.ts` 的 `disableAllPlugins` → `sanitizeProfile(profile-sanitize.ts:32)`）。
   已处理：恢复时 bundles 传入 `[...WEB_PROFILE.bundles, daniel-dsh-plugin]`，且 sanitize 后立刻重写 patch/overlay。
   验证：`daniel-plugin.spec.ts` 的「keeps the plugin activated and configured across crash recovery」；真机再按上面第 6 步演练。
2. **`resolveBundleDir` 优先 installAnchor、后 profileDir**（`packages/boot/app-boot/src/profile.ts:651-662`）。
   风险：若哪天 runtime 树里也出现同名包，会优先用 runtime 里那份（可能版本不同）。当前 runtime 不含 `daniel-dsh-plugin`，实测层解析落到 profile 副本（见 §1 组装验证 layers 第 3 项）。
   验证：`loadProfileDirectory` + `composeEntries` 断言 `skippedBundles: []` 且 `daniel` 行 config 指向 profile 内的 `entry`；打包后可用 `--dump-config` 复核（Host 无 `--patch`，改用 profile 用户层读取）。

> 另两个次要风险：① 删 preset 里的 `tool-plugin-manager` 会让上游 `apps/cli` 的 web preset e2e 期望失配（分叉预期内）；② `python3` 依赖系统解释器（第二组解决）。
