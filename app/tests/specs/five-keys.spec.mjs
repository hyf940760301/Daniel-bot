/**
 * G1-2 最小单测：overlay / cordis.patch 的写入逻辑必须写全 5 个键，且两个文件不漂移。
 *
 * 为什么不用 grep 判：grep "entry:" 在一行注释里也能命中。这里直接调用产品代码写出真文件，
 * 再用 js-yaml 解析成对象，断言 config 的**键集合完全等于** {entry, python, danielHome, timeoutMs, trace}：
 *   · 少一个键 ⇒ overlay 的 config 是整对象替换，等于把那个配置删掉（S2 §2.6）；
 *   · 多一个键 ⇒ 说明有未记录的配置面，契约没跟上；
 *   · 出现两行 `- id: daniel` ⇒ 用户层插入而不是原地覆盖，插件会被加载两次。
 *
 * 运行：
 *   cd /tmp/dsh-build/dsh-src
 *   node --import tsx --test /path/to/daniel-bot/app/tests/specs/five-keys.spec.mjs
 *
 * 第 4 条是防假绿的关键：官方 daniel-plugin.spec.ts 只断言 patch **文件文本**里有 5 个键。
 * 文件里有 ≠ Host 挂载时有 —— 插件自带的 bundle patch 用 `- insert:` 写 2 个键，
 * 如果哪天层序变了（用户层先于 bundle 层），文件仍是 5 键、官方用例仍绿，
 * 但组装结果只剩插件那 2 个键（没有 entry / danielHome / trace），运行期直接找不到 CLI。
 * 所以这里用真实的 loadProfileDirectory + composeEntries 复核**组装后**的 config。
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const SRC = process.env.DSH_SRC ?? '/tmp/dsh-build/dsh-src'
const YAML_ENTRY = join(SRC, 'node_modules', 'js-yaml', 'index.js')
assert.ok(existsSync(YAML_ENTRY), `找不到 js-yaml（期望 ${YAML_ENTRY}）—— 先 pnpm install`)

const yaml = (await import(YAML_ENTRY)).default
const { DANIEL_PLUGIN_NAME, writeDanielProfilePatch, writeDanielAppOverlay } = await import(
  `${SRC}/apps/desktop/src/daniel-plugin.ts`
)
const { composeEntries, loadProfileDirectory } = await import(`${SRC}/packages/boot/app-boot/src/profile.ts`)

const KEYS = ['danielHome', 'entry', 'python', 'timeoutMs', 'trace']

function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'qa-keys-'))
  const profile = join(root, 'profiles', 'desktop')
  mkdirSync(join(profile, 'node_modules', DANIEL_PLUGIN_NAME), { recursive: true })
  return {
    profile,
    embeds: {
      pluginSource: join(profile, 'node_modules', DANIEL_PLUGIN_NAME),
      danielHome: join(root, 'daniel-home'),
    },
  }
}

/** 解析成行数组，并返回唯一的 daniel 行（多于一行直接失败）。 */
function danielRow(text, label) {
  const doc = yaml.load(text)
  assert.ok(Array.isArray(doc), `${label} 应解析为 YAML 列表`)
  const rows = doc.filter(row => row?.id === 'daniel')
  assert.equal(rows.length, 1, `${label} 里 - id: daniel 必须恰好 1 行，实际 ${String(rows.length)} 行`)
  return rows[0]
}

test('profile patch：一行 daniel，config 键集合恰好是 5 个', () => {
  const { profile, embeds } = fixture()
  writeDanielProfilePatch(embeds, profile)
  const row = danielRow(readFileSync(join(profile, 'cordis.patch.yml'), 'utf8'), 'cordis.patch.yml')

  assert.deepEqual(Object.keys(row.config).sort(), KEYS, 'config 键集合必须恰好等于 5 键')
  assert.equal(row.config.python, 'python3')
  assert.equal(typeof row.config.timeoutMs, 'number', 'timeoutMs 必须是数字，不是字符串')
  assert.equal(row.config.timeoutMs, 180000)
  assert.equal(row.config.trace, 'summary')
  assert.equal(row.config.danielHome, embeds.danielHome)
  assert.equal(
    row.config.entry,
    join(profile, 'node_modules', DANIEL_PLUGIN_NAME, 'vendor', 'data', 'daniel-cli', 'bin', 'daniel'),
    'entry 必须指向 profile 内副本的 CLI 入口',
  )
})

test('overlay 与 profile patch 的五键配置完全一致（不漂移）', () => {
  const { profile, embeds } = fixture()
  writeDanielProfilePatch(embeds, profile)
  writeDanielAppOverlay(embeds, profile)
  const overlay = yaml.load(readFileSync(join(embeds.danielHome, 'app-overlay.yml'), 'utf8'))
  const patch = yaml.load(readFileSync(join(profile, 'cordis.patch.yml'), 'utf8'))
  assert.deepEqual(overlay, patch, 'overlay 与 patch 必须逐字段相同')
  assert.deepEqual(Object.keys(overlay[0].config).sort(), KEYS)
})

test('重写幂等；外来 patch 内容会被备份而不是静默丢弃', () => {
  const { profile, embeds } = fixture()
  assert.equal(writeDanielProfilePatch(embeds, profile), true, '首次写入应发生变化')
  assert.equal(writeDanielProfilePatch(embeds, profile), false, '第二次写入必须是无操作')

  writeFileSync(join(profile, 'cordis.patch.yml'), '- id: someone-else\n  config:\n    keep: true\n')
  writeDanielProfilePatch(embeds, profile)
  const backup = join(profile, 'cordis.patch.yml.bak-daniel')
  assert.ok(existsSync(backup), '外来内容必须备份到 .bak-daniel')
  assert.match(readFileSync(backup, 'utf8'), /someone-else/, '备份里应有原内容')
})

test('组装后（loadProfileDirectory + composeEntries）仍是 5 键，且只有一行 daniel', () => {
  const root = mkdtempSync(join(tmpdir(), 'qa-compose-'))
  const profile = join(root, 'profiles', 'desktop')
  const plugin = join(profile, 'node_modules', DANIEL_PLUGIN_NAME)
  mkdirSync(join(plugin, 'vendor', 'data', 'daniel-cli', 'bin'), { recursive: true })
  mkdirSync(join(plugin, 'lib'), { recursive: true })
  writeFileSync(join(plugin, 'lib', 'index.js'), 'export {}\n')

  // 真实插件包的清单与它自带的 patch（`- insert:` 只给 2 个键）——
  // 这正是"文件 5 键 ≠ 组装 5 键"的风险来源，不能用手写的简化 fixture 替代。
  const packaged = join(SRC, 'apps', 'desktop', 'resources', 'vendor', DANIEL_PLUGIN_NAME)
  cpSync(join(packaged, 'package.json'), join(plugin, 'package.json'))
  cpSync(join(packaged, 'cordis.patch.yml'), join(plugin, 'cordis.patch.yml'))

  writeFileSync(join(profile, 'package.json'), JSON.stringify({
    name: 'desktop-profile',
    private: true,
    dsh: { profile: { bundles: [DANIEL_PLUGIN_NAME] } },
    dependencies: {},
  }, null, 2))

  const embeds = { pluginSource: plugin, danielHome: join(root, 'daniel-home') }
  writeDanielProfilePatch(embeds, profile)

  const loaded = loadProfileDirectory('dsh', profile, join(root, 'absent-anchor', 'package.json'))
  assert.deepEqual(loaded.skippedBundles, [], '插件 bundle 不得被跳过（跳过＝静默降级成没有 Daniel 的 DSH）')
  assert.equal(loaded.patches.length, 1, '用户层 patch 必须被读到')

  const entries = composeEntries([...loaded.layers.map(layer => layer.patches), loaded.patches])
  const rows = entries.filter(entry => entry.id === 'daniel')
  assert.equal(rows.length, 1, '组装后 - id: daniel 必须恰好 1 行')
  assert.deepEqual(Object.keys(rows[0].config).sort(), KEYS, '组装后的 config 也必须恰好 5 键')
  assert.equal(rows[0].config.entry, join(plugin, 'vendor', 'data', 'daniel-cli', 'bin', 'daniel'))
  assert.equal(rows[0].config.danielHome, embeds.danielHome)
  assert.equal(rows[0].config.timeoutMs, 180000)
})
