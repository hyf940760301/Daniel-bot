/**
 * P0 基线固化 · 基线 diff（**只允许新增**）
 *
 * 判据（对应 09-工程方案 §5 验收第 1、8 条）：
 *   · 字段删除 / 改名 / 类型变化 / 契约键（ok・exitCode・kind）取值变化 → **FAIL**
 *   · 新增字段 → **ADD**（允许，这正是「追加式改造」的形态）
 *   · 数组长度变化 → **WARN**（属数据层：语料/账号数据变了，不是契约变化）
 *   · 工具名 / 参数名 / 参数类型变化 → **FAIL**
 *   · 用例标了 offline 的，字节层（sha256）必须一致；`trace=off` 时这就等价于
 *     「与 P0 基线逐字节一致」的证明。字节不一致默认 FAIL，可用 --allow-byte-drift 降级为 WARN。
 *
 * 用法：
 *   node tests/golden/diff.mjs                      # 用 baseline.json 比当前输出（trace=off）
 *   node tests/golden/diff.mjs --trace off|summary|full
 *   node tests/golden/diff.mjs --baseline <path> [--allow-byte-drift]
 * 退出码：0 = PASS（无 FAIL）；1 = FAIL
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { capture } from './capture.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = resolve(HERE, 'baseline.json')

function argOf(name, fallback) {
  const i = process.argv.indexOf(name)
  return i >= 0 ? process.argv[i + 1] : fallback
}

const findings = []
const push = (level, path, msg) => findings.push({ level, path, msg })

function walkDiff(base, cur, path) {
  if (!cur) { push('FAIL', path, '字段被删除或改名（基线有、现在没有）'); return }
  if (base.t !== cur.t) {
    if (base.t === 'union' || cur.t === 'union') {
      push('FAIL', path, `类型变化 ${base.t} → ${cur.t}`)
      return
    }
    push('FAIL', path, `类型变化 ${base.t} → ${cur.t}`)
    return
  }
  if (base.t === 'object') {
    for (const k of Object.keys(base.props)) walkDiff(base.props[k], cur.props[k], `${path}.${k}`)
    for (const k of Object.keys(cur.props)) if (!base.props[k]) push('ADD', `${path}.${k}`, '新增字段（允许）')
    return
  }
  if (base.t === 'array') {
    if (base.len !== cur.len) push('WARN', `${path}[]`, `数组长度 ${base.len} → ${cur.len}（数据层，非契约变化）`)
    if (base.len && cur.len) walkDiff(base.item, cur.item, `${path}[]`)
    return
  }
  if (base.t === 'union') {
    const a = (base.of || []).join('|'); const b = (cur.of || []).join('|')
    if (a !== b) push('FAIL', path, `联合类型变化 ${a} → ${b}`)
    return
  }
  if ('v' in base || 'v' in cur) {
    if (JSON.stringify(base.v) !== JSON.stringify(cur.v)) {
      push('FAIL', path, `契约键取值变化 ${JSON.stringify(base.v)} → ${JSON.stringify(cur.v)}`)
    }
  }
}

/* ── 跑 ─────────────────────────────────────────────────── */
const basePath = resolve(process.cwd(), argOf('--baseline', BASE))
const traceMode = String(argOf('--trace', 'off'))
const allowByteDrift = process.argv.includes('--allow-byte-drift')
const baseline = JSON.parse(readFileSync(basePath, 'utf8'))
const current = await capture(traceMode)

console.log(`基线：${basePath}`)
console.log(`当前：trace=${traceMode}（实时采集）\n`)

// ① 工具数
if (baseline.registeredCount !== current.registeredCount) {
  push('FAIL', '$registeredCount', `注册工具数变化 ${baseline.registeredCount} → ${current.registeredCount}`)
}

// ② 工具名 / 参数名 / 参数类型
const bTools = Object.keys(baseline.toolMeta || {})
const cTools = Object.keys(current.toolMeta || {})
for (const name of bTools) {
  if (!cTools.includes(name)) { push('FAIL', `$toolMeta.${name}`, '工具被删除或改名'); continue }
  const bp = JSON.stringify(baseline.toolMeta[name].params)
  const cp = JSON.stringify(current.toolMeta[name].params)
  if (bp !== cp) push('FAIL', `$toolMeta.${name}.params`, `参数名/参数类型变化：${bp} → ${cp}`)
}
for (const name of cTools) if (!bTools.includes(name)) push('FAIL', `$toolMeta.${name}`, '新增工具（本票不允许新增工具）')

// ③ 跳过清单（哪些工具因需网络/需登录而未覆盖）
const bSkip = Object.keys(baseline.skipped || {}).sort()
const cSkip = Object.keys(current.skipped || {}).sort()
if (bSkip.join(',') !== cSkip.join(',')) {
  push('FAIL', '$skipped', `跳过清单变化：${bSkip.join(',')} → ${cSkip.join(',')}`)
}

// ④ 用例结构树（只允许新增字段）
for (const id of Object.keys(baseline.cases)) {
  const b = baseline.cases[id]
  const c = current.cases[id]
  if (!c) { push('FAIL', `$cases.${id}`, '用例丢失（用例被删除或改名）'); continue }
  walkDiff(b.shape, c.shape, `$cases.${id}.shape`)
}
for (const id of Object.keys(current.cases)) {
  if (!baseline.cases[id]) push('FAIL', `$cases.${id}`, '新增用例（基线未覆盖，请先更新基线）')
}

// ⑤ 字节层：offline 用例的整段输出 sha256 必须一致
let byteTotal = 0
let byteSame = 0
for (const id of Object.keys(baseline.cases)) {
  const b = baseline.cases[id]
  const c = current.cases[id]
  if (!b.offline || !c) continue
  byteTotal += 1
  if (b.sha256 === c.sha256) byteSame += 1
  else {
    push(allowByteDrift ? 'WARN' : 'FAIL', `$cases.${id}.sha256`,
      `输出字节与基线不一致（基线 ${String(b.sha256).slice(0, 12)}… → 现在 ${String(c.sha256).slice(0, 12)}…）`)
  }
}

/* ── 报告 ───────────────────────────────────────────────── */
const by = (lv) => findings.filter((f) => f.level === lv)
const fail = by('FAIL')
const add = by('ADD')
const warn = by('WARN')

for (const f of findings) console.log(`  [${f.level}] ${f.path}  —— ${f.msg}`)
if (!findings.length) console.log('  （无差异）')

console.log('')
console.log(`用例数：${Object.keys(baseline.cases).length} 个（覆盖工具 ${new Set(Object.values(baseline.cases).map((c) => c.tool)).size} 个）`)
console.log(`跳过：${Object.keys(baseline.skipped).length} 个工具（需网络/需登录）`)
console.log(`字段层：新增 ${add.length} ｜ 警告 ${warn.length} ｜ 失败 ${fail.length}`)
console.log(`字节层：${byteSame}/${byteTotal} 个用例输出与基线逐字节一致（trace=${traceMode}）`)
console.log('')
if (fail.length) {
  console.log(`FAIL：${fail.length} 处不允许的改动（字段删除/改名/类型变化/契约键变化/工具签名变化/字节层不一致）`)
  process.exit(1)
}
console.log(`PASS：仅允许新增（新增字段 ${add.length} 个，警告 ${warn.length} 个，无破坏性改动）`)
process.exit(0)
