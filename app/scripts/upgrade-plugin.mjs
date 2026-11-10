#!/usr/bin/env node
/**
 * daniel-bot/app/scripts/upgrade-plugin.mjs
 * 一条命令把桌面端内嵌的 Daniel 插件换到新版本（默认干跑；只有 --apply 才写盘）。
 *
 * 用法：
 *   node daniel-bot/app/scripts/upgrade-plugin.mjs --tgz "<新插件 tgz>" [--src /tmp/dsh-build/dsh-src] [--dry-run]
 *   node daniel-bot/app/scripts/upgrade-plugin.mjs --tgz "<新插件 tgz>" --src /tmp/dsh-build/dsh-src --apply
 *   node daniel-bot/app/scripts/upgrade-plugin.mjs --verify <目录> [--expect <root hash>]
 *
 * 退出码：0 成功 / 2 参数错 / 3 校验失败 / 4 执行失败。
 *
 * 边界（硬约束）：
 *   · 只写 /tmp/dsh-build 下（解包临时目录 + 源码树的 vendor 目录）；
 *   · 不改 /tmp/dsh-build/dsh-src 的源码（vendor/ 是 .gitignore 的生成物，由 sync 脚本重写）；
 *   · 不打包、不 commit、不改 G1 常量（常量只打印出来让人改）。
 *
 * ── root hash 口径（唯一口径；与 specs/UPGRADE-PLUGIN.md §3、G1 门禁逐字一致，不得另立一套）──
 * 1. 范围：package/ 下所有普通文件；任意层级的 specs/、node_modules/、.git/ 目录整体跳过。
 * 2. 逐文件：sha256 = 文件字节的 SHA-256（小写 hex），bytes = 文件字节数，
 *    path = 相对 package/ 的路径（/ 分隔，无前导 ./）。
 * 3. 排序：按 path 的字节序升序（Buffer.compare）。
 * 4. 拼串：每条 path\0bytes\0sha256\n（\0 = NUL，\n = 换行），按序喂给同一个 SHA-256。
 * 5. 结果：64 位小写 hex 即 root hash。不含时间戳/权限/属主；软链不计入（出现即告警）。
 *
 * 0.11.0 基线：218 个文件 / 8bf188561936b1ab9777410ecd41bb3df0974a41410058ddfa814508c84fba98
 *   （2026-11-09 改母本附录 B.4 一句措辞 → 重切语料，18 个文件内容变、文件数不变；上一基线 218 /
 *   268cec49c55d8f948cc78f5591852cf642678f8fbbd6b4649bbd8030825b056c）
 */
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, lstatSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs'
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'

const HERE = dirname(fileURLToPath(import.meta.url))
const APP_DIR = resolve(HERE, '..') // daniel-bot/app
const REPO_DIR = resolve(APP_DIR, '..') // daniel-bot
const BUILD_ROOT = '/tmp/dsh-build'
const DEFAULT_SRC = join(BUILD_ROOT, 'dsh-src')
const PLUGIN_NAME = 'daniel-dsh-plugin'
/** 与 sync-daniel-plugin.mjs / G1 门禁同一排除集：不打进包里的开发目录。 */
const EXCLUDED = new Set(['specs', 'node_modules', '.git'])
const MIN_FILES = 100
/** 壳随包的 Node 版本（build/toolchain/node24），用于 engines 兼容性告警。 */
const SHELL_NODE_MAJOR = 24
/** 已知基线，仅用于展示与提示，不参与判定。 */
const BASELINE = { version: '0.11.0', files: 218, rootHash: '8bf188561936b1ab9777410ecd41bb3df0974a41410058ddfa814508c84fba98' }

const USAGE = `插件升级工具（Daniel Bot 桌面端内嵌插件）

用法
  node daniel-bot/app/scripts/upgrade-plugin.mjs --tgz <新插件 tgz> [--src /tmp/dsh-build/dsh-src] [--dry-run] [--apply]
  node daniel-bot/app/scripts/upgrade-plugin.mjs --verify <插件目录> [--expect <root hash>]

参数
  --tgz <path>        新插件包（文件名必须是 ${PLUGIN_NAME}-<version>.tgz）
  --src <dir>         源码树根（默认 /tmp/dsh-build/dsh-src；真执行时必须在 /tmp/dsh-build 下）
  --dry-run           干跑（默认行为）：只解包到临时目录算 hash 与差异，不碰 vendor
  --apply             真执行：解包 → 调 sync-daniel-plugin.mjs → 复算并断言 hash
  --allow-republish   允许"同版本号但内容不同"的重打包（默认拒绝，见手册 §6）
  --verify <dir>      只核验一个目录的版本/文件数/root hash（vendor、.app 内副本、profile 副本都行）
  --expect <hash>     配合 --verify：断言 hash 等于该值（可带 sha256: 前缀）
  -h, --help          打印本说明

退出码
  0  成功（干跑通过 / 真执行通过 / 核验一致）
  2  参数错（缺 --tgz、未知参数、--src 不是源码树、干跑与 --apply 同时给）
  3  校验失败（tgz 不存在/不是 tgz/包名不符/版本与文件名不符/文件数 <${String(MIN_FILES)}/同版本不同内容）
  4  执行失败（sync 失败、写后 hash 或文件数不符）

示例
  node daniel-bot/app/scripts/upgrade-plugin.mjs --tgz "daniel-bot/releases/${PLUGIN_NAME}-0.12.0.tgz" --dry-run
  node daniel-bot/app/scripts/upgrade-plugin.mjs --tgz "daniel-bot/releases/${PLUGIN_NAME}-0.12.0.tgz" --apply
  node daniel-bot/app/scripts/upgrade-plugin.mjs --verify "/tmp/dsh-build/dsh-src/apps/desktop/resources/vendor/${PLUGIN_NAME}" --expect ${BASELINE.rootHash}

手册：daniel-bot/specs/UPGRADE-PLUGIN.md`

class CliError extends Error {
  constructor(code, message) {
    super(message)
    this.name = 'CliError'
    this.code = code
  }
}

let stagingToClean = null

function log(message = '') {
  process.stdout.write(`${message}\n`)
}
function fail(message) {
  process.stderr.write(`upgrade-plugin: ${message}\n`)
}

/** 终端显示宽度（CJK 记 2 列），只影响排版，不影响任何判定。 */
const CJK = /[\u1100-\u115f\u2e80-\u303e\u3041-\u33ff\u3400-\u4dbf\u4e00-\u9fff\ua000-\ua4cf\uac00-\ud7a3\uf900-\ufaff\ufe30-\ufe4f\uff00-\uff60\uffe0-\uffe6]/
function displayWidth(text) {
  let width = 0
  for (const char of text) width += CJK.test(char) ? 2 : 1
  return width
}
function pad(text, size) {
  return text + ' '.repeat(Math.max(0, size - displayWidth(text)))
}
function rule() {
  log('─'.repeat(72))
}
function bytesText(bytes) {
  return `${bytes.toLocaleString('en-US')} 字节 / ${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/* ─────────────────────────── 清单与 hash（唯一实现） ─────────────────────────── */

function inventory(root) {
  const files = []
  const symlinks = []
  const visit = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      if (EXCLUDED.has(entry.name)) continue
      const absolute = join(directory, entry.name)
      const path = relative(root, absolute).split(sep).join('/')
      if (entry.isSymbolicLink()) {
        symlinks.push(path)
        continue
      }
      if (entry.isDirectory()) {
        visit(absolute)
        continue
      }
      if (!entry.isFile()) throw new CliError(3, `不支持的目录项（既不是文件也不是目录）：${path}`)
      const body = readFileSync(absolute)
      files.push({ path, bytes: body.byteLength, sha256: createHash('sha256').update(body).digest('hex') })
    }
  }
  visit(root)
  files.sort((left, right) => Buffer.compare(Buffer.from(left.path), Buffer.from(right.path)))
  return { files, symlinks }
}

function digest(files) {
  const hash = createHash('sha256')
  for (const file of files) hash.update(`${file.path}\0${String(file.bytes)}\0${file.sha256}\n`)
  return hash.digest('hex')
}

function totalBytes(files) {
  return files.reduce((sum, file) => sum + file.bytes, 0)
}

/** 读一个目录的现场：是不是真目录、版本、文件数、hash。 */
function inspectDir(directory) {
  if (!existsSync(directory)) return null
  const stat = lstatSync(directory)
  const symlink = stat.isSymbolicLink()
  const isDirectory = symlink ? statSync(directory).isDirectory() : stat.isDirectory()
  if (!isDirectory) return { broken: true, symlink }
  const { files, symlinks } = inventory(directory)
  let manifest = null
  try {
    manifest = JSON.parse(readFileSync(join(directory, 'package.json'), 'utf8'))
  } catch {
    manifest = null
  }
  return {
    broken: false,
    symlink,
    manifest,
    files,
    symlinks,
    bytes: totalBytes(files),
    hash: digest(files),
  }
}

function diffInventories(currentFiles, nextFiles) {
  const current = new Map(currentFiles.map((file) => [file.path, file]))
  const next = new Map(nextFiles.map((file) => [file.path, file]))
  const added = []
  const changed = []
  const removed = []
  for (const [path, file] of next) {
    const before = current.get(path)
    if (before === undefined) added.push(file)
    else if (before.sha256 !== file.sha256 || before.bytes !== file.bytes) changed.push(file)
  }
  for (const [path, file] of current) if (!next.has(path)) removed.push(file)
  const sortByPath = (list) => list.sort((a, b) => Buffer.compare(Buffer.from(a.path), Buffer.from(b.path)))
  return { added: sortByPath(added), changed: sortByPath(changed), removed: sortByPath(removed) }
}

/* ───────────────────────────────── 参数解析 ───────────────────────────────── */

function parseCli(argv) {
  let values
  try {
    const parsed = parseArgs({
      args: argv,
      options: {
        tgz: { type: 'string' },
        src: { type: 'string' },
        verify: { type: 'string' },
        expect: { type: 'string' },
        apply: { type: 'boolean', default: false },
        'dry-run': { type: 'boolean', default: false },
        'allow-republish': { type: 'boolean', default: false },
        help: { type: 'boolean', short: 'h', default: false },
      },
      strict: true,
      allowPositionals: false,
    })
    values = parsed.values
  } catch (error) {
    throw new CliError(2, `参数无法解析：${error.message}\n\n${USAGE}`)
  }

  if (values.help === true) return { help: true }
  if (values.verify !== undefined && values.tgz !== undefined) throw new CliError(2, '--verify 与 --tgz 不能同时使用（核验请单独跑）')
  if (values.apply === true && values['dry-run'] === true) throw new CliError(2, '--apply 与 --dry-run 互斥：默认就是干跑，真执行只给 --apply')
  if (values.expect !== undefined && values.verify === undefined) throw new CliError(2, '--expect 只能配合 --verify 使用')
  if (values.verify === undefined && values.tgz === undefined) throw new CliError(2, `缺少 --tgz <新插件 tgz>（或用 --verify 核验已有目录）\n\n${USAGE}`)

  return {
    help: false,
    tgz: values.tgz,
    src: values.src ?? DEFAULT_SRC,
    verify: values.verify,
    expect: values.expect,
    apply: values.apply === true,
    dryRun: values['dry-run'] === true,
    allowRepublish: values['allow-republish'] === true,
  }
}

function normalizeHash(value) {
  if (value === undefined) return null
  const trimmed = value.trim().toLowerCase().replace(/^sha256:/, '')
  if (!/^[0-9a-f]{64}$/.test(trimmed)) {
    throw new CliError(2, `--expect 不是 64 位十六进制 sha256：${value}`)
  }
  return trimmed
}

function insideBuildRoot(target) {
  const rel = relative(BUILD_ROOT, resolve(target))
  return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel))
}

function resolveSrc(value) {
  const src = resolve(process.cwd(), value)
  if (!existsSync(src) || !statSync(src).isDirectory()) {
    throw new CliError(2, `--src 不是目录：${src}`)
  }
  const syncScript = join(src, 'apps', 'desktop', 'scripts', 'sync-daniel-plugin.mjs')
  if (!existsSync(syncScript)) {
    throw new CliError(2, `--src 下没有 apps/desktop/scripts/sync-daniel-plugin.mjs：${src}（给错源码树了？）`)
  }
  return { src, syncScript }
}

/* ───────────────────────────────── 版本比较 ──────────────────────────────── */

/** 只用于"这是升级还是回退"的提示，不参与任何校验。返回 -1/0/1，无法解析时返回 null。 */
function compareVersions(left, right) {
  const parse = (value) => {
    const match = /^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$/.exec(value ?? '')
    return match === null ? null : { core: [Number(match[1]), Number(match[2]), Number(match[3])], pre: match[4] ?? null }
  }
  const a = parse(left)
  const b = parse(right)
  if (a === null || b === null) return null
  for (let index = 0; index < 3; index += 1) {
    if (a.core[index] !== b.core[index]) return a.core[index] < b.core[index] ? -1 : 1
  }
  if (a.pre === b.pre) return 0
  if (a.pre === null) return 1
  if (b.pre === null) return -1
  const leftParts = a.pre.split('.')
  const rightParts = b.pre.split('.')
  for (let index = 0; index < Math.max(leftParts.length, rightParts.length); index += 1) {
    const x = leftParts[index]
    const y = rightParts[index]
    if (x === undefined) return -1
    if (y === undefined) return 1
    const xn = /^\d+$/.test(x)
    const yn = /^\d+$/.test(y)
    if (xn && yn && Number(x) !== Number(y)) return Number(x) < Number(y) ? -1 : 1
    if (xn !== yn) return xn ? -1 : 1
    if (x !== y) return x < y ? -1 : 1
  }
  return 0
}

/* ─────────────────────────────────── 核验模式 ─────────────────────────────── */

function verifyMode(options) {
  const directory = resolve(process.cwd(), options.verify)
  if (!existsSync(directory)) throw new CliError(3, `目录不存在：${directory}`)
  const stat = lstatSync(directory)
  const symlink = stat.isSymbolicLink()
  const isDirectory = symlink ? statSync(directory).isDirectory() : stat.isDirectory()
  if (!isDirectory) throw new CliError(3, `不是目录：${directory}`)

  const { files, symlinks } = inventory(directory)
  const hash = digest(files)
  let manifest = null
  try {
    manifest = JSON.parse(readFileSync(join(directory, 'package.json'), 'utf8'))
  } catch {
    manifest = null
  }
  const expect = normalizeHash(options.expect)

  log('')
  log('插件目录核验')
  rule()
  log(`  ${pad('目录', 12)}${directory}`)
  log(`  ${pad('类型', 12)}${symlink ? '⚠ 软链（验收要求真目录）' : '真目录'}`)
  log(`  ${pad('包名', 12)}${String(manifest?.name ?? '(package.json 解析失败)')}`)
  log(`  ${pad('版本', 12)}${String(manifest?.version ?? '(未知)')}`)
  log(`  ${pad('文件数', 12)}${String(files.length)}${symlinks.length > 0 ? `（另有 ${String(symlinks.length)} 个软链）` : ''}`)
  log(`  ${pad('总字节', 12)}${bytesText(totalBytes(files))}`)
  log(`  ${pad('root hash', 12)}${hash}`)
  if (expect !== null) log(`  ${pad('期望 hash', 12)}${expect}`)

  const problems = []
  if (symlink) problems.push('目录是软链，不是真目录（验收清单第 3 条）')
  if (manifest?.name !== PLUGIN_NAME) problems.push(`包名不是 ${PLUGIN_NAME}`)
  if (files.length < MIN_FILES) problems.push(`文件数 ${String(files.length)} < ${String(MIN_FILES)}`)
  if (expect !== null && expect !== hash) problems.push('root hash 与 --expect 不一致')

  if (problems.length === 0) {
    log('')
    log(expect === null ? '  ✓ 目录结构正常（未给 --expect，未比对 hash）' : '  ✓ 与期望一致：包名、文件数、root hash 全部对上')
    return 0
  }
  log('')
  for (const problem of problems) log(`  ✗ ${problem}`)
  throw new CliError(3, `核验不通过：${problems.join('；')}`)
}

/* ─────────────────────────────────── 升级模式 ─────────────────────────────── */

function listTarEntries(tgz) {
  const result = spawnSync('tar', ['-tzf', tgz], { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 })
  if (result.error !== undefined) throw new CliError(3, `无法运行 tar：${result.error.message}`)
  if (result.status !== 0) {
    throw new CliError(3, `tgz 解不开（tar 退出码 ${String(result.status)}）：${(result.stderr ?? '').trim() || tgz}`)
  }
  return (result.stdout ?? '').split('\n').filter((line) => line !== '')
}

function upgradeMode(options) {
  const tgz = resolve(process.cwd(), options.tgz)
  const { src, syncScript } = resolveSrc(options.src)
  const wantApply = options.apply === true

  if (wantApply && !insideBuildRoot(src)) {
    throw new CliError(2, `只允许写 ${BUILD_ROOT} 下的源码树；--src 在边界外：${src}\n（干跑可以读任意源码树，真执行请指向 ${DEFAULT_SRC}）`)
  }

  // ── 输入存在性（先校验再打印，报错时不留半截标题）─────────────────────────
  if (!existsSync(tgz)) throw new CliError(3, `tgz 不存在：${tgz}`)
  if (!statSync(tgz).isFile()) throw new CliError(3, `不是文件：${tgz}`)
  const fileName = basename(tgz)
  const nameWithoutSuffix = fileName.replace(/\.(tgz|tar\.gz)$/, '')
  if (nameWithoutSuffix === fileName) throw new CliError(3, `不是 .tgz / .tar.gz：${fileName}`)
  const expectedPrefix = `${PLUGIN_NAME}-`
  if (!nameWithoutSuffix.startsWith(expectedPrefix)) {
    throw new CliError(3, `文件名不符合 ${PLUGIN_NAME}-<version>.tgz：${fileName}`)
  }
  const fileVersion = nameWithoutSuffix.slice(expectedPrefix.length)
  const tgzBytes = statSync(tgz).size

  log('')
  log(wantApply ? '插件升级 · 真执行（会写 vendor）' : '插件升级 · 干跑（只解包到临时目录，不碰 vendor，退出前删除）')
  rule()

  log(`  ${pad('新包 tgz', 14)}${tgz}`)
  log(`  ${pad('tgz 体积', 14)}${bytesText(tgzBytes)}`)

  // ── 解包到临时目录（只写 /tmp/dsh-build）────────────────────────────────
  const stagingRoot = join(BUILD_ROOT, '.plugin-upgrade')
  const staging = join(stagingRoot, String(process.pid))
  mkdirSync(stagingRoot, { recursive: true })
  rmSync(staging, { recursive: true, force: true })
  mkdirSync(staging, { recursive: true })
  stagingToClean = staging
  log(`  ${pad('解包位置', 14)}${staging}（跑完即删）`)

  const entries = listTarEntries(tgz)
  for (const entry of entries) {
    const normalized = entry.replace(/^\.\//, '')
    if (isAbsolute(normalized) || normalized.split('/').includes('..')) {
      throw new CliError(3, `压缩包含不安全路径（绝对路径或 ..）：${entry}`)
    }
  }
  if (!entries.some((entry) => entry.replace(/^\.\//, '') === 'package/package.json')) {
    throw new CliError(3, `压缩包里没有 package/package.json：${fileName}（不是 npm pack 的标准结构）`)
  }

  const untar = spawnSync('tar', ['-xzf', tgz, '-C', staging], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
  if (untar.error !== undefined) throw new CliError(3, `无法运行 tar：${untar.error.message}`)
  if (untar.status !== 0) {
    throw new CliError(3, `解包失败（tar 退出码 ${String(untar.status)}）：${(untar.stderr ?? '').trim()}`)
  }

  const extracted = join(staging, 'package')
  if (!existsSync(join(extracted, 'package.json'))) throw new CliError(3, `解包后没有 package/package.json：${fileName}`)

  // ── tgz 内容校验 ────────────────────────────────────────────────────────
  let manifest
  try {
    manifest = JSON.parse(readFileSync(join(extracted, 'package.json'), 'utf8'))
  } catch (error) {
    throw new CliError(3, `package/package.json 不是合法 JSON：${error.message}`)
  }

  const checks = []
  checks.push({ ok: true, text: 'package/package.json 存在' })
  const nameOk = manifest.name === PLUGIN_NAME
  checks.push({ ok: nameOk, text: `包名 ${String(manifest.name)}${nameOk ? '' : ` ≠ ${PLUGIN_NAME}`}` })
  if (!nameOk) {
    printChecks(checks)
    throw new CliError(3, `包名不符：期望 ${PLUGIN_NAME}，实际 ${String(manifest.name)}`)
  }

  const versionOk = manifest.version === fileVersion
  checks.push({
    ok: versionOk,
    text: `版本 ${String(manifest.version)}${versionOk ? ' 与文件名一致' : ` ≠ 文件名里的 ${fileVersion}`}`,
  })
  if (!versionOk) {
    printChecks(checks)
    throw new CliError(3, `版本号与文件名不一致：package.json=${String(manifest.version)}，文件名=${fileVersion}（发布前必须重打，不能手改）`)
  }

  let listed
  try {
    listed = inventory(extracted)
  } catch (error) {
    if (error instanceof CliError) throw error
    throw new CliError(3, `读解包目录失败：${error.message}`)
  }
  const fileCount = listed.files.length
  checks.push({ ok: fileCount >= MIN_FILES, text: `文件数 ${String(fileCount)}（阈值 ≥${String(MIN_FILES)}）` })
  if (fileCount < MIN_FILES) {
    printChecks(checks)
    throw new CliError(3, `文件数不足：${String(fileCount)} < ${String(MIN_FILES)}，明显不是完整插件包`)
  }

  const patchField = manifest.dsh?.bundle?.patch
  if (typeof patchField !== 'string' || patchField === '') {
    printChecks(checks)
    throw new CliError(3, '插件包没有声明 dsh.bundle.patch —— 壳不会把它当作 bundle 加载')
  }
  const patchPath = resolve(join(extracted, patchField))
  const patchInside = !relative(extracted, patchPath).startsWith('..')
  const patchExists = patchInside && existsSync(patchPath)
  checks.push({ ok: patchExists, text: `dsh.bundle.patch = ${patchField}${patchExists ? '（文件在包内）' : '（文件不在包内）'}` })
  if (!patchExists) {
    printChecks(checks)
    throw new CliError(3, `dsh.bundle.patch 指向的文件不在包内：${patchField}`)
  }

  // 壳把入口写死在 pluginRow 里：node_modules/daniel-dsh-plugin/vendor/data/daniel-cli/bin/daniel
  const cliEntry = join(extracted, 'vendor', 'data', 'daniel-cli', 'bin', 'daniel')
  const entryExists = existsSync(cliEntry)
  checks.push({
    ok: entryExists,
    text: `壳写死的入口 vendor/data/daniel-cli/bin/daniel${entryExists ? '' : ' 不存在'}`,
  })
  if (!entryExists) {
    printChecks(checks)
    throw new CliError(
      3,
      '缺少 vendor/data/daniel-cli/bin/daniel —— 壳的 pluginRow 把插件入口写死在这个路径（apps/desktop/src/daniel-plugin.ts），' +
        '换路径必须同时改壳并重打包，不属"换插件版本"的范围',
    )
  }

  const hash = digest(listed.files)
  const newBytes = totalBytes(listed.files)

  // ── 现场与差异 ──────────────────────────────────────────────────────────
  const vendorRoot = join(src, 'apps', 'desktop', 'resources', 'vendor')
  const targetDir = join(vendorRoot, PLUGIN_NAME)
  const current = inspectDir(targetDir)

  log(`  ${pad('目标目录', 14)}${targetDir}`)
  log('')
  printChecks(checks)
  for (const warning of collectWarnings(manifest, listed, extracted)) log(`  ⚠ ${warning}`)

  if (current === null) log(`  ⚠ 现状：${targetDir} 不存在 —— 这是首次落地，脚本会新建目录`)
  else if (current.broken) log(`  ⚠ 现状：${targetDir} 存在但不是目录（文件？）—— 会被替换`)

  log('')
  log('现状 → 新包')
  log(`  ${pad('版本', 12)}${pad(String(current?.manifest?.version ?? '(无)'), 22)}→ ${String(manifest.version)}`)
  log(`  ${pad('文件数', 12)}${pad(current === null ? '(无)' : String(current.files.length), 22)}→ ${String(fileCount)}`)
  log(
    `  ${pad('总字节', 12)}${pad(current === null ? '(无)' : totalBytes(current.files).toLocaleString('en-US'), 22)}→ ${newBytes.toLocaleString('en-US')} 字节（${(newBytes / 1024 / 1024).toFixed(1)} MB）`,
  )
  log(`  ${pad('目录类型', 12)}${pad(current === null ? '(无)' : current.symlink ? '软链' : '真目录', 22)}→ 真目录（sync 用 rename 落地）`)
  log(`  ${pad('版本判定', 12)}${describeVersionChange(current?.manifest?.version, manifest.version)}`)

  const diff = current === null || current.broken
    ? { added: listed.files, changed: [], removed: [] }
    : diffInventories(current.files, listed.files)
  const changedCount = diff.added.length + diff.changed.length + diff.removed.length

  log('')
  log('影响范围（会变的文件）')
  if (changedCount === 0) {
    log('  0 个文件会变：新包与现状逐文件相同（新增 0 / 修改 0 / 删除 0）')
  } else {
    log(
      `  会变 ${String(changedCount)} 个文件（新增 ${String(diff.added.length)} / 修改 ${String(diff.changed.length)} / 删除 ${String(diff.removed.length)}），` +
        `其余 ${String(fileCount - diff.added.length - diff.changed.length)} 个不变`,
    )
    printFileList('新增', diff.added)
    printFileList('修改', diff.changed)
    printFileList('删除', diff.removed)
  }
  log('')
  log('影响链（本脚本只改第 1 处）')
  log(`  1. 源码树 vendor 目录（本脚本写入，被 .gitignore 忽略：${src}/.gitignore:36）`)
  log('  2. 打包产物 <App>.app/Contents/Resources/vendor/daniel-dsh-plugin（下次打包才生效）')
  log('  3. 首启 profile 副本 $DSH_HOME/profiles/desktop/node_modules/daniel-dsh-plugin（用户机器首启时由壳复制）')

  if (current !== null && !current.broken && current.manifest?.version === manifest.version && current.hash !== hash) {
    log('')
    log('  ⚠ 同版本号但内容不同（同名重打）')
    log(`     ${manifest.version} 现状 hash：${current.hash}`)
    log(`     ${manifest.version} 新包 hash：${hash}`)
  }

  const sameHash = current !== null && !current.broken && current.hash === hash
  const republish = current !== null && !current.broken && current.hash !== hash && current.manifest?.version === manifest.version

  if (sameHash && !current.symlink && current.symlinks.length === 0 && listed.symlinks.length === 0) {
    log('')
    log('结论')
    log(`  与现状一致，无需升级（版本 ${String(manifest.version)}、${String(fileCount)} 个文件、hash 完全相同）`)
    log(`  root hash（现状）：${current.hash}`)
    log(`  root hash（新包）：${hash}`)
    log(`  退出码 0；未写盘。${wantApply ? '（--apply 也没动任何文件）' : ''}`)
    return 0
  }

  log('')
  log('写入链（--apply 时执行）')
  log(`  1. 解包 ${fileName} → ${staging}/package`)
  log(`  2. node ${syncScript} --from ${staging}/package`)
  log(`  3. 复算 ${targetDir} 的版本/文件数/root hash，断言 = ${hash}（不一致退出 4）`)
  log('  4. 只动 vendor；不打包、不 commit、不改 G1 常量')

  if (republish && !options.allowRepublish) {
    log('')
    log('结论')
    log(`  ✗ 拒绝执行：${String(manifest.version)} 是同版本重打（内容变了但版本号没变）`)
    log('  已发布过的版本号不允许静默替换（G1 的 KNOWN_GOOD 与已发 DMG 会对不上）。')
    log('  若确认要重打：加 --allow-republish，并在 specs/DECISIONS-A.md 记一条。')
    throw new CliError(3, `同版本号不同内容：${String(manifest.version)} 的 hash ${current.hash} → ${hash}，拒绝静默替换（确需重打请加 --allow-republish）`)
  }

  log('')
  log('结论')
  if (current === null || current.broken) {
    log(`  首次落地：${String(manifest.version)}，将写入 ${String(changedCount)} 个文件`)
  } else {
    log(
      `  ${wantApply ? '真执行' : '干跑通过'}：${String(current.manifest?.version ?? '?')} → ${String(manifest.version)}，` +
        `${String(changedCount)} 个文件会变`,
    )
  }
  if (current !== null && current.symlink === true) log('  唯一要修的：现状是软链，--apply 会删链接、落成真目录（内容不变）')
  log(`  ${pad('旧 hash', 10)}${current?.hash ?? '(无)'}`)
  log(`  ${pad('新 hash', 10)}${hash}`)
  log(`  ${pad('新文件数', 10)}${String(fileCount)}`)
  if (!wantApply) {
    printConstants(current?.manifest?.version ?? null, manifest.version, fileCount, hash)
    log('')
    log('下一步：确认上面的数字与文件清单无误后，把 --dry-run 换成 --apply 真执行')
    return 0
  }

  // ── 真执行 ──────────────────────────────────────────────────────────────
  if (current !== null && current.symlink === true) {
    log('')
    log('  ⚠ 现状是软链：先删链接本身（不删它指向的目录），让 sync 落成真目录（验收清单第 3 条）')
    rmSync(targetDir, { recursive: true, force: true })
  }
  log('')
  log('[1/3] 解包完成（见上）')
  log(`[2/3] 调 sync 脚本：${syncScript}`)
  log('      （下面是 sync 自己的输出；期望最后出现「✓ 已写入 …」）')
  const sync = spawnSync(process.execPath, [syncScript, '--from', extracted], { stdio: 'inherit' })
  if (sync.error !== undefined) throw new CliError(4, `无法运行 sync 脚本：${sync.error.message}`)
  if (sync.status !== 0) {
    throw new CliError(4, `sync 脚本失败（退出码 ${String(sync.status)}）：vendor 可能停在中间态，按 specs/UPGRADE-PLUGIN.md §7 回滚`)
  }

  log('[3/3] 复算 vendor')
  const after = inspectDir(targetDir)
  if (after === null) throw new CliError(4, `sync 之后目标目录仍不存在：${targetDir}`)
  if (after.broken) throw new CliError(4, `sync 之后目标不是目录：${targetDir}`)
  if (after.symlink) throw new CliError(4, `目标目录是软链，不是真目录（验收清单第 3 条）：${targetDir}`)
  if (after.files.length !== fileCount) {
    throw new CliError(4, `文件数不符：期望 ${String(fileCount)}，实际 ${String(after.files.length)}`)
  }
  if (after.hash !== hash) {
    const afterDiff = diffInventories(listed.files, after.files)
    throw new CliError(
      4,
      `root hash 不符：期望 ${hash}，实际 ${after.hash}（新增 ${String(afterDiff.added.length)} / 修改 ${String(afterDiff.changed.length)} / 删除 ${String(afterDiff.removed.length)}）`,
    )
  }

  const residues = existsSync(vendorRoot)
    ? readdirSync(vendorRoot, { withFileTypes: true }).filter((entry) => entry.name.startsWith('.staging-')).map((entry) => entry.name)
    : []
  log('')
  log(`✓ 升级完成：${PLUGIN_NAME}@${String(manifest.version)}`)
  log(`  vendor 目录  ：${targetDir}`)
  log(`  目录类型     ：真目录（非软链）`)
  log(`  文件数       ：${String(after.files.length)}`)
  log(`  root hash    ：${after.hash}`)
  log(`  与 tgz 一致  ：是（版本 / 文件数 / hash 三项都断言过）`)
  if (residues.length > 0) {
    log(`  ⚠ staging 残留：${residues.join(', ')}（G1-4b 会判 FAIL，手工删掉）`)
  }

  printConstants(current?.manifest?.version ?? null, manifest.version, fileCount, hash)
  printNextSteps()
  return 0
}

function describeVersionChange(previous, next) {
  if (previous === undefined || previous === null) return `${String(next)}（无旧版本可比）`
  if (previous === next) return `${String(next)}（版本号没变）`
  const order = compareVersions(next, previous)
  if (order === null) return `${String(previous)} → ${String(next)}（无法比较，按升级处理）`
  if (order > 0) return `${String(previous)} → ${String(next)}（升级）`
  return `${String(previous)} → ${String(next)}（⚠ 版本号变小：这是回退，走手册 §7 回滚流程）`
}

function printChecks(checks) {
  for (const check of checks) log(`  ${check.ok ? '✓' : '✗'} ${check.text}`)
}

function printFileList(label, files) {
  if (files.length === 0) return
  const shown = files.slice(0, 8).map((file) => file.path)
  const rest = files.length - shown.length
  log(`  ${label}：${shown.join('、')}${rest > 0 ? ` …另 ${String(rest)} 个` : ''}`)
}

/** 只告警不拦截：打包能过但运行会出问题的点。 */
function collectWarnings(manifest, listed, root) {
  const warnings = []
  if (listed.symlinks.length > 0) {
    warnings.push(`包内有 ${String(listed.symlinks.length)} 个软链（${listed.symlinks.slice(0, 3).join('、')}）：G1-1a 要求 0 软链`)
  }
  const entries = [manifest.main, typeof manifest.exports === 'string' ? manifest.exports : manifest.exports?.['.']]
  for (const entry of entries) {
    if (typeof entry !== 'string' || entry === '') continue
    if (!existsSync(resolve(join(root, entry)))) warnings.push(`package.json 指向的入口不存在：${entry}（插件会加载失败）`)
  }
  const engines = manifest.engines?.node
  if (typeof engines === 'string') {
    const major = /(\d+)/.exec(engines)
    if (major !== null && Number(major[1]) > SHELL_NODE_MAJOR) {
      warnings.push(`engines.node=${engines} 高于壳随包 Node（v${String(SHELL_NODE_MAJOR)}），首启可能直接抛错`)
    }
  }
  return warnings
}

/* ────────────────────────────── 常量扫描与收尾提示 ─────────────────────────── */

function scanConstants(oldVersion) {
  const rows = []
  const wantsOldTgz = (text) => oldVersion !== null && text.includes(`${PLUGIN_NAME}-${oldVersion}.tgz`)
  const targets = [
    {
      file: join(REPO_DIR, 'app', 'tests', 'g1-contract-gate.mjs'),
      match: (text) => /KNOWN_GOOD\s*=/.test(text) || wantsOldTgz(text),
    },
    {
      file: join(REPO_DIR, 'app', 'desktop-patches', 'CHECKPOINT.md'),
      match: (text) => /期望输出：daniel-dsh-plugin@/.test(text),
    },
    { file: join(REPO_DIR, 'README.md'), match: wantsOldTgz },
  ]
  for (const target of targets) {
    if (!existsSync(target.file)) continue
    const lines = readFileSync(target.file, 'utf8').split('\n')
    lines.forEach((text, index) => {
      if (!target.match(text)) return
      rows.push({ file: relative(REPO_DIR, target.file).split(sep).join('/'), line: index + 1, text: text.trim() })
    })
  }
  return rows
}

function suggestionFor(row, oldVersion, newVersion, files, hash) {
  if (/KNOWN_GOOD\s*=/.test(row.text)) {
    return `const KNOWN_GOOD = { version: '${newVersion}', files: ${String(files)}, rootHash: '${hash}' }`
  }
  if (oldVersion === null) return null
  if (!row.text.includes(oldVersion)) return null
  if (/期望输出：daniel-dsh-plugin@/.test(row.text) && row.text.includes('个文件')) {
    return row.text.replace(`${PLUGIN_NAME}@${oldVersion}`, `${PLUGIN_NAME}@${newVersion}`).replace(/· \d+ 个文件 · [0-9a-f]{12}/, `· ${String(files)} 个文件 · ${hash.slice(0, 12)}`)
  }
  return row.text.replaceAll(oldVersion, newVersion)
}

function printConstants(oldVersion, newVersion, files, hash) {
  const rows = scanConstants(oldVersion)
  log('')
  log('要改的常量（脚本不会替你改：旧版本号/哈希写死在源码与文档里）')
  if (rows.length === 0) {
    log(`  没扫到写死的旧版本号（${String(oldVersion ?? '未知')}）；发布前仍请 grep 一遍：`)
    log(`  grep -rn "${PLUGIN_NAME}-" daniel-bot/app daniel-bot/README.md`)
  } else {
    let lastFile = null
    let pending = 0
    for (const row of rows) {
      if (row.file !== lastFile) log(`  ${row.file}`)
      lastFile = row.file
      log(`    :${String(row.line)}  现：${row.text}`)
      const suggestion = suggestionFor(row, oldVersion, newVersion, files, hash)
      if (suggestion !== null && suggestion !== row.text) {
        pending += 1
        log(`           改：${suggestion}`)
      }
    }
    if (pending === 0) log('  （扫到的常量已经是目标版本/哈希，无需改动）')
    log('  说明：g1-contract-gate.mjs 的两处是功能判据（不改 → G1-1a/1b/1d FAIL）；CHECKPOINT/README 是操作文档，也要跟着改。')
  }
}

function printNextSteps() {
  log('')
  log('下一步')
  log('  1. 改上面的常量（G1 的 KNOWN_GOOD 含 version / files / rootHash 三个值）')
  log('  2. 跑门禁：node daniel-bot/app/tests/g1-contract-gate.mjs')
  log('  3. 打包（要有 PTY 的终端）：pnpm -C apps/desktop package:mac:arm64:unsigned')
  log('  4. 按 specs/UPGRADE-PLUGIN.md §8 的 6 条清单验收（含 .app 内副本、首启 profile、崩溃恢复）')
}

/* ──────────────────────────────────── 入口 ─────────────────────────────────── */

function run(argv) {
  const options = parseCli(argv)
  if (options.help) {
    log(USAGE)
    return 0
  }
  if (options.verify !== undefined) return verifyMode(options)
  return upgradeMode(options)
}

let exitCode = 0
try {
  exitCode = run(process.argv.slice(2))
} catch (error) {
  if (error instanceof CliError) {
    fail(error.message)
    exitCode = error.code
  } else {
    fail(`未预料的错误（按执行失败处理）：${error?.stack ?? String(error)}`)
    exitCode = 4
  }
} finally {
  if (stagingToClean !== null) {
    rmSync(stagingToClean, { recursive: true, force: true })
    try {
      const parent = dirname(stagingToClean)
      if (existsSync(parent) && readdirSync(parent).length === 0) rmSync(parent, { recursive: true, force: true })
    } catch {
      // 临时目录清理失败不影响结论。
    }
  }
}
process.exitCode = exitCode
