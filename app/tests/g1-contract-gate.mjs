#!/usr/bin/env node
/**
 * G1 · 契约门禁（插件内容哈希 / 配置 5 键 / sanitizeProfile 兼容 / seed 幂等）
 *
 * 独立运行：
 *   node daniel-bot/app/tests/g1-contract-gate.mjs
 *   node daniel-bot/app/tests/g1-contract-gate.mjs --src /tmp/dsh-build/dsh-src --tgz /path/to.tgz
 *
 * 退出码：0 = 无 FAIL（可含 SKIP）；1 = 存在 FAIL。
 *
 * 防假绿要点（每条都写明"为什么不能只看表面"）：
 *   G1-1 哈希不是"目录存在就算过"：按产品同一算法复算 218 个文件的 root_hash，
 *        并与 **tgz 真源**、以及版本钉死的 known-good 常量三方对齐。
 *        补丁没有引入 PLUGIN-MANIFEST.json（已核实），所以清单缺失不算 FAIL，改为 tgz 对齐。
 *   G1-2 不是 grep 5 个键：真调用写入函数产出文件，再用 js-yaml 解析，断言键集合**恰好**相等。
 *   G1-3 不是看注释：真调用 DesktopProjectManager.disableAllPlugins() 跑崩溃恢复，
 *        并带一条 CONTROL（裸 sanitize 会删插件且挪走 patch），证明"只看 bundles"会假绿。
 *   G1-4 跑两次比对**整个 vendor 根**的文件树：只比对 daniel-dsh-plugin 子目录会漏掉
 *        .staging-* 残留（实测每次幂等运行 +5.7MB）。
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { dirname, join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import process from 'node:process'
import { Gate, dim, parseArgs, run, sha256File } from './lib/gate.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const APP = join(HERE, '..')
const PLUGIN = 'daniel-dsh-plugin'
const DEFAULTS = {
  src: '/tmp/dsh-build/dsh-src',
  tgz: join(APP, '..', 'releases', 'daniel-dsh-plugin-0.11.0.tgz'),
  toolchain: join(APP, '..', 'build', 'toolchain', 'node24', 'bin'),
}
const args = parseArgs(process.argv.slice(2), DEFAULTS)
const SRC = String(args.src)
const TGZ = String(args.tgz)
const TOOLCHAIN = String(args.toolchain)
const WORK = join('/tmp', `qa-g1-${String(process.pid)}`)
const VENDOR_ROOT = join(SRC, 'apps', 'desktop', 'resources', 'vendor')
const PLUGIN_DIR = join(VENDOR_ROOT, PLUGIN)
/** 插件 0.11.0 的 known-good root_hash（CHECKPOINT §1 / sync 脚本输出）。升级插件必须同时改这里。 */
const KNOWN_GOOD = { version: '0.11.0', files: 218, rootHash: 'cca08a5a65578ee98d8aa2ec1944ab2c42d633a072da135d400c5ea4daaf4486' }
const gate = new Gate('G1', '契约门禁')

const env = { PATH: `${TOOLCHAIN}:${process.env.PATH ?? ''}`, DSH_SRC: SRC }

function lastLines(text, count = 10) {
  return String(text).trimEnd().split('\n').slice(-count).join('\n')
}

/** 与 embedDanielPlugin 完全相同的清单算法（路径\0字节数\0sha256\n 再 sha256），排除不打进包里的目录。 */
const EXCLUDED = new Set(['specs', 'node_modules', '.git'])
function inventory(root) {
  const files = []
  const symlinks = []
  const visit = directory => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      if (EXCLUDED.has(entry.name)) continue
      const path = join(directory, entry.name)
      const name = relative(root, path).split(sep).join('/')
      if (entry.isSymbolicLink()) { symlinks.push(name); continue }
      if (entry.isDirectory()) { visit(path); continue }
      if (!entry.isFile()) throw new Error(`不支持的目录项：${name}`)
      const body = readFileSync(path)
      files.push({ path: name, bytes: body.byteLength, sha256: createHash('sha256').update(body).digest('hex') })
    }
  }
  visit(root)
  return { files: files.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0)), symlinks }
}
function inventoryDigest(files) {
  const hash = createHash('sha256')
  for (const file of files) hash.update(`${file.path}\0${String(file.bytes)}\0${file.sha256}\n`)
  return hash.digest('hex')
}
/** 整棵树的指纹（路径 + 文件 sha256 + 目录条目），用于"跑两次是否一样"。 */
function treeFingerprint(root) {
  const rows = []
  const visit = directory => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name)
      const name = relative(root, path).split(sep).join('/')
      if (entry.isDirectory()) { rows.push(`d ${name}`); visit(path); continue }
      if (entry.isSymbolicLink()) { rows.push(`l ${name}`); continue }
      rows.push(`f ${name} ${sha256File(path)}`)
    }
  }
  if (existsSync(root)) visit(root)
  rows.sort()
  return { hash: 'tree-sha256:' + createHash('sha256').update(rows.join('\n')).digest('hex'), entries: rows.length }
}
const stagingDirs = root =>
  existsSync(root) ? readdirSync(root, { withFileTypes: true }).filter(e => e.isDirectory() && e.name.startsWith('.staging-')).map(e => e.name) : []

rmSync(WORK, { recursive: true, force: true })
mkdirSync(WORK, { recursive: true })
gate.info(`源码树：${SRC}`)
gate.info(`插件 tgz：${TGZ}`)
gate.info(`临时目录：${WORK}`)

// ── G1-1 插件内容哈希 ─────────────────────────────────────────────────────────
{
  if (!existsSync(PLUGIN_DIR)) {
    gate.check('G1-1 插件内容哈希', {
      expected: `${PLUGIN_DIR} 存在且哈希可复算`,
      actual: '目录不存在 —— 先跑 sync 脚本',
      ok: false,
      detail: `复现：node ${SRC}/apps/desktop/scripts/sync-daniel-plugin.mjs --from ${TGZ}`,
    })
  } else {
    const pkg = JSON.parse(readFileSync(join(PLUGIN_DIR, 'package.json'), 'utf8'))
    const { files, symlinks } = inventory(PLUGIN_DIR)
    const digest = inventoryDigest(files)

    gate.check('G1-1a 插件版本与文件数', {
      expected: `${PLUGIN}@${KNOWN_GOOD.version}，${String(KNOWN_GOOD.files)} 个文件，0 软链`,
      actual: `${String(pkg.name)}@${String(pkg.version)}，${String(files.length)} 个文件，${String(symlinks.length)} 软链`,
      ok: pkg.name === PLUGIN && pkg.version === KNOWN_GOOD.version && files.length === KNOWN_GOOD.files && symlinks.length === 0,
    })

    gate.check('G1-1b root_hash 等于版本钉死的 known-good', {
      expected: `${KNOWN_GOOD.rootHash.slice(0, 16)}…（${KNOWN_GOOD.version}）`,
      actual: `${digest.slice(0, 16)}…（${digest === KNOWN_GOOD.rootHash ? '一致' : '不一致'}）`,
      ok: digest === KNOWN_GOOD.rootHash,
      detail: digest,
    })

    const manifestPath = join(VENDOR_ROOT, '..', 'PLUGIN-MANIFEST.json')
    if (existsSync(manifestPath)) {
      const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
      gate.check('G1-1c PLUGIN-MANIFEST.json 一致', {
        expected: manifest.root_hash,
        actual: digest,
        ok: manifest.root_hash === digest && (manifest.files ?? []).length === files.length,
      })
    } else {
      gate.skip(
        'G1-1c PLUGIN-MANIFEST.json 一致',
        '补丁未引入 PLUGIN-MANIFEST.json（已 grep 补丁全文核实），无清单可对',
        `打包后跑 bash daniel-bot/app/scripts/seed-profile.sh --app <Resources> --write-manifest 生成清单，再复跑本门禁`,
      )
    }

    // 与 tgz 真源对齐：目录可能是旧版本、被手工改过、或解包不完整。
    if (existsSync(TGZ)) {
      const extract = join(WORK, 'tgz')
      mkdirSync(extract, { recursive: true })
      const untar = run('tar', ['-xzf', TGZ, '-C', extract])
      const fromTgz = untar.ok ? inventory(join(extract, 'package')) : { files: [], symlinks: [] }
      const tgzDigest = inventoryDigest(fromTgz.files)
      const onlyVendor = files.filter(f => !fromTgz.files.some(g => g.path === f.path))
      const onlyTgz = fromTgz.files.filter(g => !files.some(f => f.path === g.path))
      gate.check('G1-1d 与 tgz 真源逐文件一致', {
        expected: `解包 ${String(KNOWN_GOOD.files)} 文件，root_hash 相同，差集为空`,
        actual: `解包 ${String(fromTgz.files.length)} 文件，hash ${tgzDigest === digest ? '相同' : '不同'}，仅目录有 ${String(onlyVendor.length)} / 仅 tgz 有 ${String(onlyTgz.length)}`,
        ok: untar.ok && fromTgz.files.length === files.length && tgzDigest === digest && onlyVendor.length === 0 && onlyTgz.length === 0,
        detail: untar.stderr || [...onlyVendor, ...onlyTgz].slice(0, 5).map(f => f.path).join('\n'),
      })
    } else {
      gate.skip('G1-1d 与 tgz 真源逐文件一致', `找不到 tgz：${TGZ}`, '用 --tgz 指向插件发布包后复跑')
    }
  }
}

// ── G1-2 配置 5 键 ────────────────────────────────────────────────────────────
{
  const spec = join(HERE, 'specs', 'five-keys.spec.mjs')
  const result = run('node', ['--import', 'tsx', '--test', spec], { cwd: SRC, env, timeout: 300_000 })
  const output = result.stdout + result.stderr
  const pass = Number(/^ℹ pass (\d+)$/m.exec(output)?.[1] ?? 0)
  const fail = Number(/^ℹ fail (\d+)$/m.exec(output)?.[1] ?? 0)
  gate.check('G1-2a 5 键写入逻辑（真跑产品代码 + YAML 解析 + 组装复核）', {
    expected: '4 个用例全过（文件恰好 5 键 / overlay 与 patch 一致 / 幂等且备份 / 组装后仍 5 键）',
    actual: `pass ${String(pass)} / fail ${String(fail)}，退出码 ${String(result.code)}`,
    ok: result.ok && pass === 4 && fail === 0,
    detail: lastLines(output, 12),
  })

  // 静态兜底：有人删掉模板里的键，动态用例能抓到；这里再防"键名被改名换义"。
  const source = readFileSync(join(SRC, 'apps', 'desktop', 'src', 'daniel-plugin.ts'), 'utf8')
  const missing = ['entry', 'python', 'danielHome', 'timeoutMs', 'trace'].filter(
    key => !source.includes(`\`    ${key}: `),
  )
  gate.check('G1-2b 源码模板里 5 个键名都在', {
    expected: 'entry / python / danielHome / timeoutMs / trace 均出现在 pluginRow 模板',
    actual: missing.length === 0 ? '5/5 都在' : `缺 ${missing.join(', ')}`,
    ok: missing.length === 0,
  })
}

// ── G1-3 sanitizeProfile 兼容 ────────────────────────────────────────────────
{
  const spec = join(HERE, 'specs', 'sanitize-profile.spec.mjs')
  const result = run('node', ['--import', 'tsx', '--test', spec], { cwd: SRC, env, timeout: 300_000 })
  const output = result.stdout + result.stderr
  const pass = Number(/^ℹ pass (\d+)$/m.exec(output)?.[1] ?? 0)
  const fail = Number(/^ℹ fail (\d+)$/m.exec(output)?.[1] ?? 0)
  gate.check('G1-3a 崩溃恢复后插件仍在（真跑 disableAllPlugins）', {
    expected: '3 个用例全过（CONTROL 删插件 / PRODUCT 恢复后插件+5键 patch / NEGATIVE 不凭空激活）',
    actual: `pass ${String(pass)} / fail ${String(fail)}，退出码 ${String(result.code)}`,
    ok: result.ok && pass === 3 && fail === 0,
    detail: lastLines(output, 14),
  })

  const source = readFileSync(join(SRC, 'apps', 'desktop', 'src', 'project-manager.ts'), 'utf8')
  const sanitizeAt = source.indexOf('sanitizeProfile(')
  const rewriteAt = source.indexOf('writeDanielProfilePatch(', sanitizeAt + 1)
  const passesDaniel = /bundles\s*=\s*embedded\s*\?[^\n]*DANIEL_PLUGIN_NAME/.test(source) || /\[\s*\.\.\.WEB_PROFILE\.bundles\s*,\s*DANIEL_PLUGIN_NAME\s*\]/.test(source)
  gate.check('G1-3b 恢复路径顺序正确：sanitize 之后立刻重写 patch', {
    expected: 'sanitizeProfile(...) 之后调用 writeDanielProfilePatch(...)；bundles 里显式拼入 DANIEL_PLUGIN_NAME',
    actual: `sanitize@${String(sanitizeAt)} → rewrite@${String(rewriteAt)}（${rewriteAt > sanitizeAt ? '顺序正确' : '顺序错误/缺失'}），拼入插件=${String(passesDaniel)}`,
    ok: sanitizeAt > 0 && rewriteAt > sanitizeAt && passesDaniel,
  })
}

// ── G1-4 seed 幂等 ───────────────────────────────────────────────────────────
{
  const spec = join(HERE, 'specs', 'embed-idempotent.spec.mjs')
  const result = run('node', ['--import', 'tsx', '--test', spec], { cwd: SRC, env, timeout: 300_000 })
  const output = result.stdout + result.stderr
  const pass = Number(/^ℹ pass (\d+)$/m.exec(output)?.[1] ?? 0)
  const fail = Number(/^ℹ fail (\d+)$/m.exec(output)?.[1] ?? 0)
  gate.check('G1-4a 嵌入复制幂等（embedDanielPlugin，含 mtime 不变）', {
    expected: '3 个用例全过（二次不重写 / 损坏重植 / 源缺失不崩）',
    actual: `pass ${String(pass)} / fail ${String(fail)}，退出码 ${String(result.code)}`,
    ok: result.ok && pass === 3 && fail === 0,
    detail: lastLines(output, 12),
  })

  // 工作区现场：残留 staging 说明 sync 脚本的运行路径会漏清理。
  const liveStaging = stagingDirs(VENDOR_ROOT)
  gate.check('G1-4b 工作区 vendor 根无 .staging-* 残留', {
    expected: '0 个残留（sync 脚本每次运行都应清干净）',
    actual: liveStaging.length === 0 ? '0 个' : `${String(liveStaging.length)} 个：${liveStaging.join(', ')}`,
    ok: liveStaging.length === 0,
    detail: liveStaging.length === 0 ? '' : liveStaging.map(name => `${name}（${String(readdirSync(join(VENDOR_ROOT, name)).length)} 项）`).join('\n'),
  })

  // 真跑两次 sync 脚本（在镜像目录里，不动构建工作区），比对整个 vendor 根的文件树。
  const script = join(SRC, 'apps', 'desktop', 'scripts', 'sync-daniel-plugin.mjs')
  if (!existsSync(script)) {
    gate.check('G1-4c sync 脚本两次运行文件树一致', {
      expected: `${script} 存在`,
      actual: '不存在（补丁未应用？）',
      ok: false,
    })
  } else {
    const mirror = join(WORK, 'mirror', 'apps', 'desktop')
    mkdirSync(join(mirror, 'scripts'), { recursive: true })
    mkdirSync(join(mirror, 'resources', 'vendor'), { recursive: true })
    writeFileSync(join(mirror, 'scripts', 'sync-daniel-plugin.mjs'), readFileSync(script))
    const root = join(mirror, 'resources', 'vendor')
    const first = run('node', [join(mirror, 'scripts', 'sync-daniel-plugin.mjs'), '--from', TGZ], { cwd: mirror, env, timeout: 300_000 })
    const tree1 = treeFingerprint(root)
    const staging1 = stagingDirs(root)
    const second = run('node', [join(mirror, 'scripts', 'sync-daniel-plugin.mjs'), '--from', TGZ], { cwd: mirror, env, timeout: 300_000 })
    const tree2 = treeFingerprint(root)
    const staging2 = stagingDirs(root)
    const targetDigest = existsSync(join(root, PLUGIN)) ? inventoryDigest(inventory(join(root, PLUGIN)).files) : 'absent'

    gate.check('G1-4c sync 脚本两次运行 vendor 根文件树一致（无新增条目）', {
      expected: '两次 tree 指纹相同，entries 相同，.staging-* 为 0',
      actual: `run1 ${tree1.hash.slice(0, 16)}…/${String(tree1.entries)} 项（staging ${String(staging1.length)}）→ run2 ${tree2.hash.slice(0, 16)}…/${String(tree2.entries)} 项（staging ${String(staging2.length)}）`,
      ok: first.ok && second.ok && tree1.hash === tree2.hash && tree1.entries === tree2.entries && staging2.length === 0,
      detail: `runner 退出码 ${String(first.code)}/${String(second.code)}；插件目录自身 hash ${targetDigest.slice(0, 16)}…（说明副本本身是对的，脏的是根目录）`,
    })
  }

  gate.skip(
    'G1-4d seed-profile.sh 端到端幂等',
    '需要对已签名的 .app / 组装好的 Resources（含 runtime/python、dsh/lib/bin.js）；本会话无打包产物，跑了会误判',
    '打包后：bash daniel-bot/app/scripts/seed-profile.sh --app <xxx.app> --home /tmp/qa-home --dsh-home /tmp/qa-dsh 连跑两次，diff 两次 stdout 的「结果」段，并用 --write-manifest 复算 root_hash',
  )
}

gate.info(`临时目录保留在 ${dim(WORK)}（可删除）`)
const code = gate.finish()
if (code === 0) rmSync(WORK, { recursive: true, force: true })
process.exitCode = code
