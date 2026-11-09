/**
 * G1-3 最小单测：崩溃恢复（sanitizeProfile）之后插件必须仍然活着，且 5 键配置被重写。
 *
 * 运行（必须用构建树自己的 tsx，因为要 import 产品源码的 TS）：
 *   cd /tmp/dsh-build/dsh-src
 *   node --import tsx --test /path/to/daniel-bot/app/tests/specs/sanitize-profile.spec.mjs
 *
 * 三条用例，缺一不可：
 *   1. CONTROL —— 裸 sanitizeProfile 会把插件从 bundles 里删掉、并把 cordis.patch.yml 挪走。
 *      这条是防假绿的关键：只断言 "bundles 里有插件" 而不看 patch 是否被重写，会漏掉
 *      "插件在、5 键配置没了" 的真实故障（Host 起来后插件读不到 entry/danielHome）。
 *   2. PRODUCT —— 产品代码 DesktopProjectManager.disableAllPlugins() 恢复后：
 *      bundles 保留插件、旧 patch 有备份、新 patch 含且仅含一行 daniel、5 键齐、overlay 同步。
 *   3. NEGATIVE —— profile 里没有插件副本时，恢复不得凭空把插件塞回 bundles。
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const SRC = process.env.DSH_SRC ?? '/tmp/dsh-build/dsh-src'
const { DesktopProjectManager } = await import(`${SRC}/apps/desktop/src/project-manager.ts`)
const { sanitizeProfile } = await import(`${SRC}/packages/boot/app-boot/src/profile-sanitize.ts`)
const { DANIEL_PLUGIN_NAME } = await import(`${SRC}/apps/desktop/src/daniel-plugin.ts`)

const KEYS = ['danielHome', 'entry', 'python', 'timeoutMs', 'trace']
const PATCH = `# daniel
- id: daniel
  config:
    entry: "/x/daniel"
    python: "python3"
    danielHome: "/x/home"
    timeoutMs: 180000
    trace: summary
`

function makeProfile(bundles, { withPlugin = true } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'qa-recovery-'))
  const profile = join(root, 'profiles', 'desktop')
  mkdirSync(profile, { recursive: true })
  if (withPlugin) {
    mkdirSync(join(profile, 'node_modules', DANIEL_PLUGIN_NAME), { recursive: true })
    writeFileSync(
      join(profile, 'node_modules', DANIEL_PLUGIN_NAME, 'package.json'),
      JSON.stringify({ name: DANIEL_PLUGIN_NAME, version: '0.0.0' }),
    )
  }
  writeFileSync(
    join(profile, 'package.json'),
    JSON.stringify({ name: 'desktop-profile', private: true, dsh: { profile: { bundles } }, dependencies: {} }, null, 2),
  )
  writeFileSync(join(profile, 'cordis.patch.yml'), PATCH)
  return { root, profile, danielHome: join(root, 'daniel-home') }
}

const managerFor = (profile, danielHome) =>
  new DesktopProjectManager(
    { profile, lock: join(profile, 'lock') },
    { dsh: '/nonexistent-runtime' },
    { pluginSource: join(profile, 'node_modules', DANIEL_PLUGIN_NAME), danielHome },
  )

test('CONTROL: 裸 sanitizeProfile 会删插件并把 patch 挪走', () => {
  const { profile } = makeProfile(['web-app', DANIEL_PLUGIN_NAME])
  const backup = sanitizeProfile('dsh', profile, ['web-app'])
  const bundles = JSON.parse(readFileSync(join(profile, 'package.json'), 'utf8')).dsh.profile.bundles
  assert.deepEqual(bundles, ['web-app'], '对照：插件已被删出 bundles')
  assert.equal(existsSync(join(profile, 'cordis.patch.yml')), false, '对照：patch 被挪走（所以必须重写）')
  assert.ok(backup !== undefined && existsSync(backup), '对照：旧 patch 有备份')
})

test('PRODUCT: 崩溃恢复后插件仍在 bundles，且 5 键 patch/overlay 被重写', async () => {
  const { profile, danielHome } = makeProfile(['web-app', DANIEL_PLUGIN_NAME])
  const backup = await managerFor(profile, danielHome).disableAllPlugins()

  const pkg = JSON.parse(readFileSync(join(profile, 'package.json'), 'utf8'))
  assert.ok(pkg.dsh.profile.bundles.includes(DANIEL_PLUGIN_NAME), '恢复后插件仍被激活')

  assert.ok(backup !== undefined && existsSync(backup), '恢复前把旧 patch 备份了')
  const patch = readFileSync(join(profile, 'cordis.patch.yml'), 'utf8')
  assert.match(patch, /^- id: daniel$/m, '写回了 daniel 行')
  assert.equal((patch.match(/^- id: daniel$/gm) ?? []).length, 1, '只有一行 daniel（不重复插入）')
  for (const key of KEYS) assert.match(patch, new RegExp(`^    ${key}: `, 'm'), `patch 缺键 ${key}`)

  const overlay = readFileSync(join(danielHome, 'app-overlay.yml'), 'utf8')
  for (const key of KEYS) assert.match(overlay, new RegExp(`^    ${key}: `, 'm'), `overlay 缺键 ${key}`)
})

test('NEGATIVE: 没有插件副本时恢复不得凭空激活插件', async () => {
  const { profile, danielHome } = makeProfile(['web-app'], { withPlugin: false })
  await managerFor(profile, danielHome).disableAllPlugins()
  const pkg = JSON.parse(readFileSync(join(profile, 'package.json'), 'utf8'))
  assert.ok(!pkg.dsh.profile.bundles.includes(DANIEL_PLUGIN_NAME), '不得凭空激活')
})
