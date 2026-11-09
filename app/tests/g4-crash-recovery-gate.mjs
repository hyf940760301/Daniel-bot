#!/usr/bin/env node
/**
 * G4 · 真机崩溃恢复演练（占位 · 需要打包后的 .app + 交互式终端）
 *
 * 代码层面的恢复路径已由 G1-3（真跑 DesktopProjectManager.disableAllPlugins）覆盖；
 * 这里补的是"真机触发一次崩溃恢复"的整链路验证。只声明判据，不产出 PASS。
 *
 * 独立运行：node daniel-bot/app/tests/g4-crash-recovery-gate.mjs
 *
 * 复验方法（用户执行）：
 *   1. 正常运行一次 Daniel Bot，确认 $DSH_HOME/profiles/desktop/cordis.patch.yml 含 5 键；
 *   2. 删坏该文件（或写入非法 YAML），再启动应用触发恢复（应用内崩溃恢复入口）；
 *   3. 断言：出现 cordis.patch.yml.bak-<时间戳>；新的 cordis.patch.yml 仍在且含 5 键；
 *      profile/package.json 的 bundles 仍含 daniel-dsh-plugin；再重启一次仍成立。
 *
 * 升级插件后的验收清单（6 条，含本条）见 daniel-bot/specs/UPGRADE-PLUGIN.md §8；本条对应第 ⑥ 条。
 * 换版本用 daniel-bot/app/scripts/upgrade-plugin.mjs（默认干跑），不要手工 cp 覆盖 vendor。
 */
import process from 'node:process'
import { Gate } from './lib/gate.mjs'

const gate = new Gate('G4', '真机崩溃恢复演练（占位）')
gate.info('本门禁为占位：实现前不得据此判 PASS')
gate.skip(
  'G4-a 恢复后 5 键 patch 自动重建',
  '需要已打包 .app 与真机交互触发恢复',
  '见文件头 1→3 步；断言的代码级等价物是 G1-3a 的 PRODUCT 用例',
)
gate.skip(
  'G4-b 恢复后 bundles 仍含 daniel-dsh-plugin',
  '同上（真机才能验证既有 profile 的迁移）',
  '见文件头第 3 步',
)
gate.skip(
  'G4-c 二次重启不回退',
  '同上',
  '恢复后再重启一次，重复断言 a/b',
)
const code = gate.finish()
process.exitCode = code
