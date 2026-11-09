#!/usr/bin/env node
/**
 * 跑全部门禁并汇总。任何门禁退出 1 则整体退出 1；纯 SKIP 的门禁不拉低结论，但会单独标出。
 *
 * 用法：
 *   node daniel-bot/app/tests/run-all.mjs
 *   node daniel-bot/app/tests/run-all.mjs --only g0,g1
 *   node daniel-bot/app/tests/run-all.mjs --src /tmp/dsh-build/dsh-src
 *   node daniel-bot/app/tests/run-all.mjs --dmg <path.dmg>   # 额外参数原样透传给每个门禁（G2/G3 认 --dmg）
 *
 * 说明：G2/G3 在没有产物时给出 SKIP（不判 PASS），汇总里单独标出；指定了 --dmg 却找不到文件时是 FAIL。
 */
import { spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import process from 'node:process'
import { dim, green, red, yellow } from './lib/gate.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const ALL = [
  ['g0', 'g0-code-gate.mjs', 'G0 代码门禁'],
  ['g1', 'g1-contract-gate.mjs', 'G1 契约门禁'],
  ['g2', 'g2-packaging-gate.mjs', 'G2 打包门禁'],
  ['g3', 'g3-install-gate.mjs', 'G3 安装后运行门禁'],
  ['g4', 'g4-crash-recovery-gate.mjs', 'G4 真机恢复演练（占位）'],
]

const argv = process.argv.slice(2)
const onlyArg = argv.find(arg => arg.startsWith('--only=')) ?? (argv.includes('--only') ? `--only=${String(argv[argv.indexOf('--only') + 1])}` : undefined)
const only = onlyArg === undefined ? null : onlyArg.slice('--only='.length).split(',').map(s => s.trim())
const extra = argv.filter((arg, index) => !arg.startsWith('--only') && !(index > 0 && argv[index - 1] === '--only'))

const rows = []
for (const [id, file, title] of ALL) {
  if (only !== null && !only.includes(id)) continue
  console.log(`\n▶ ${title}`)
  // 不能只看退出码：全 SKIP 的门禁退出码也是 0，会把"没验"显示成"OK"。
  const result = spawnSync(process.execPath, [join(HERE, file), ...extra], { encoding: 'utf8' })
  const output = `${result.stdout ?? ''}${result.stderr ?? ''}`
  process.stdout.write(output)
  const code = result.status ?? 1
  const verdict = /RESULT: (PASS|FAIL|SKIP)/.exec(output)?.[1] ?? (code === 0 ? 'UNKNOWN' : 'FAIL')
  rows.push({ id, title, code, verdict })
}

console.log('\n' + '─'.repeat(72))
console.log('门禁汇总')
let failed = 0
let skipped = 0
for (const row of rows) {
  if (row.verdict === 'PASS') console.log(`  ${green('PASS')} ${row.id}  ${row.title}`)
  else if (row.verdict === 'FAIL') { failed += 1; console.log(`  ${red('FAIL')} ${row.id}  ${row.title}`) }
  else { skipped += 1; console.log(`  ${yellow('SKIP')} ${row.id}  ${row.title}`) }
}
console.log(dim(`  共 ${String(rows.length)} 个门禁：PASS ${String(rows.length - failed - skipped)} / FAIL ${String(failed)} / SKIP ${String(skipped)}`))
if (skipped > 0) console.log(yellow('  注意：SKIP 不等于通过（G2/G3 需要产物、G4 仍为占位；门禁自行判定是否具备条件）。'))
process.exitCode = failed > 0 ? 1 : 0
