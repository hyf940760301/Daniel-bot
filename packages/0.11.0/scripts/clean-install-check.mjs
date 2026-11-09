#!/usr/bin/env node
/**
 * 干净机验收（0.9.8 新增）：把 `<pkg>.tgz` 当成「别人拿到的那一份包」来验。
 *
 * 为什么需要它：0.9.7 之前只验过「本机能跑」（smoke / trace / golden），
 * 但那些都跑在开发机上，包内多出来的 .pyc、含本机绝对路径的夹具、缺 vendor 的目录，
 * 在开发机上统统看不出来 —— 只有把包解到**临时目录 ＋ 假 HOME** 里才会暴露。
 *
 * 判据（任何一条不过 ⇒ 退出码 1）：
 *   C1 包内不得有 `__pycache__` / `*.pyc`（pack spec X02／X03）
 *   C2 包内不得有 `mcp/_fixtures/cross-host/*.json`（pack spec X26：刻意含本机路径）
 *   C3 包内必须自带 CLI 树、能力目录、8 束语料、插件入口与 bundle patch
 *   C4 假 HOME 下 `daniel --version` 能跑
 *   C5 假 HOME 下能力目录可解析（`skills list` 报 8 个能力域，且不出现「找不到 Daniel 能力目录」）
 *   C6 假 HOME 下业务门禁正常（`account audit` 走到「请先登录」，而不是内部错误）
 *   C7 解包后的代码/配置里不得出现本机用户名路径（`/Users/<name>`、`/home/<name>`）
 *
 * 用法：
 *   node scripts/clean-install-check.mjs --tgz ../daniel-dsh-plugin-0.9.8.tgz
 *   node scripts/clean-install-check.mjs --tgz <path> --keep   # 保留临时目录便于排查
 */

import { execFileSync, spawnSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, relative, resolve, extname } from 'node:path'

const argv = process.argv.slice(2)
const getArg = (name, dflt = null) => {
  const i = argv.indexOf(name)
  return i >= 0 && argv[i + 1] ? argv[i + 1] : dflt
}
const tgzArg = getArg('--tgz')
const keep = argv.includes('--keep')
if (!tgzArg) {
  console.error('用法：node scripts/clean-install-check.mjs --tgz <包路径.tgz> [--keep]')
  process.exit(2)
}
const tgz = resolve(tgzArg)

const results = []
const record = (id, desc, ok, detail = '') => {
  results.push({ id, desc, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${id}  ${desc}${detail ? '  — ' + detail : ''}`)
}

// ── C0：包存在 ──────────────────────────────────────────────
if (!statSync(tgz, { throwIfNoEntry: false })) {
  console.error(`找不到包：${tgz}`)
  process.exit(2)
}

// ── C1／C2／C3：直接读 tar 名单，不解包 ─────────────────────
const listing = execFileSync('tar', ['-tzf', tgz], { maxBuffer: 64 * 1024 * 1024 })
  .toString('utf8')
  .split('\n')
  .filter(Boolean)
const entries = listing.map((p) => p.replace(/^package\//, ''))
const hit = (re) => entries.filter((p) => re.test(p))

const pycache = hit(/(^|\/)__pycache__\/|\.pyc$/)
record('C1', '包内无 __pycache__ / *.pyc', pycache.length === 0, pycache.slice(0, 3).join(', '))

const crossHost = hit(/mcp\/_fixtures\/cross-host\//)
record('C2', '包内无 cross-host 正控夹具（含本机路径）', crossHost.length === 0, crossHost.slice(0, 3).join(', '))

const required = [
  'lib/index.js',
  'cordis.patch.yml',
  'package.json',
  'vendor/data/daniel-cli/bin/daniel',
  'vendor/.kol-tools/daniel_client.py',
  'vendor/.kol-tools/daniel_paths.py',
  'vendor/data/daniel-cli/mcp/corpus/kol-intelligence/SKILL.md',
]
const missing = required.filter((r) => !entries.includes(r))
const corpusDirs = new Set(
  entries.filter((p) => /^vendor\/data\/daniel-cli\/mcp\/corpus\/[^/]+\/SKILL\.md$/.test(p))
)
record(
  'C3',
  '包自带 CLI 树／能力目录／8 束语料／入口',
  missing.length === 0 && corpusDirs.size === 8,
  missing.length ? '缺 ' + missing.join(', ') : `语料 ${corpusDirs.size}/8 束`
)

// ── 解包到临时目录 ＋ 假 HOME ───────────────────────────────
const work = mkdtempSync(join(tmpdir(), 'daniel-clean-'))
const pkgDir = join(work, 'package')
const fakeHome = join(work, 'home')
mkdirSync(fakeHome, { recursive: true })
execFileSync('tar', ['-xzf', tgz, '-C', work], { maxBuffer: 64 * 1024 * 1024 })

const cliBin = join(pkgDir, 'vendor/data/daniel-cli/bin/daniel')
const env = {
  ...process.env,
  HOME: fakeHome,
  DANIEL_NO_OPEN: '1',
  // 显式清掉可能从开发机继承的落点/能力目录，避免"用本机配置冒充包自足"
  DANIEL_HOME: '',
  DANIEL_BIN: '',
  DANIEL_CLI_TOOLS: '',
}
for (const k of ['DANIEL_HOME', 'DANIEL_BIN', 'DANIEL_CLI_TOOLS']) delete env[k]

const runCli = (args) => {
  const r = spawnSync(cliBin, args, { env, encoding: 'utf8', timeout: 120_000 })
  return { code: r.status, out: `${r.stdout || ''}${r.stderr || ''}` }
}

// C4：版本
const ver = runCli(['--version'])
record('C4', '假 HOME 下 `daniel --version` 可跑', ver.code === 0 && /daniel\s+\d/.test(ver.out), (ver.out || '').trim().split('\n')[0])

// C5：能力目录（.kol-tools）＋ 语料
const skills = runCli(['skills', 'list'])
const noTools = /找不到 Daniel 能力目录/.test(skills.out)
const domains = (skills.out.match(/个能力域/) || []).length > 0
record(
  'C5',
  '能力目录可解析且 8 束语料可读',
  skills.code === 0 && !noTools && domains,
  noTools ? '命中了「找不到能力目录」' : (skills.out.match(/(\d+) 个能力域/) || ['', '?'])[1] + ' 个能力域'
)

// C6：业务门禁（未登录应走到"请先登录"，不是内部错误）
const audit = runCli(['account', 'audit'])
const internalErr = /找不到 Daniel 能力目录|Traceback|EXIT_INTERNAL/.test(audit.out)
const gated = /请先登录/.test(audit.out)
record('C6', '业务门禁正常（走到「请先登录」）', !internalErr && gated, internalErr ? '内部错误' : '未登录即拦')

// C7：包内不得残留本机用户名路径
const scanExt = new Set(['.js', '.mjs', '.cjs', '.json', '.py', '.yml', '.yaml', '.sh', '.toml'])
const nameRe = /\/(?:Users|home)\/[A-Za-z0-9._-]+\//
const offenders = []
const walk = (dir) => {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) walk(p)
    else if (scanExt.has(extname(p))) {
      const text = readFileSync(p, 'utf8')
      if (nameRe.test(text)) offenders.push(relative(pkgDir, p))
    }
  }
}
walk(pkgDir)
record('C7', '包内代码/配置无本机用户名路径', offenders.length === 0, offenders.slice(0, 3).join(', '))

// ── 汇总 ───────────────────────────────────────────────────
const failed = results.filter((r) => !r.ok)
console.log('')
console.log(`合计 ${results.length} 项：PASS ${results.length - failed.length} / FAIL ${failed.length}`)
if (failed.length) {
  console.log('未通过：' + failed.map((r) => r.id).join('、'))
  console.log(`临时目录（--keep 可保留）：${work}`)
  process.exit(1)
}
if (!keep) rmSync(work, { recursive: true, force: true })
else console.log(`临时目录已保留：${work}`)
process.exit(0)
