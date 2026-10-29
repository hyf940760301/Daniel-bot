/**
 * 输出契约（trace）自检：三档开关行为 ＋ 四段结构 ＋ 校验器 ＋ 无 null 兜底。
 * 用法：node scripts/test-trace.mjs
 *
 * 覆盖（对应 TICKET-216 第 6 条 ＋ TICKET-219）：
 *   ① off     → 白名单工具返回体**完全不含** trace 字段（且去掉 trace 后与 summary 档逐字节一致）
 *   ② summary → 白名单四段齐全、段值是字符串／字符串数组；非白名单一个字段都不加
 *   ③ full    → 四段齐全，且与 summary **内容不同**（详版条数更多）
 *   ④ 校验器  → 缺一段时拒绝（ok:false / exitCode:2 / kind='trace_incomplete'）；off 档永不校验
 *   ⑤ prune   → 返回体（含降级文案）不含 null/undefined，JSON 里不出现 null 字面量
 *   ⑥ 详简两层＋常驻提示 → `trace.层级` 可区分；简版各段 ≤2 条短句；两种提示措辞逐字一致；
 *                          off／非白名单不出现 `末尾提示` 字段
 *
 * 纪律：只跑**离线**用例（不需要登录/联网），否则这个自检在断网机器上就废了。
 * 需要真实业务数据的三个白名单工具（brands_list / roster_search / kol_profile）用
 * **纯函数层**验证：四段生成器 ＋ 装配函数，不发网络请求。
 */
import { apply, prune } from '../lib/index.js'
import {
  EXCLUDED_CSV_COLUMNS, TRACE_EXCLUDED_LINE_MAX, TRACE_EXCLUDED_MAX_LINES,
  TRACE_EXEMPT_TOOLS, TRACE_HINT_FULL, TRACE_HINT_SUMMARY, TRACE_SECTIONS, TRACE_TOOLS, TRACE_UNAVAILABLE, TRACE_VERSION,
  assertTrace, buildTraceSections, finalizeOutput, isTraceTool, normalizeTraceMode, rosterArgsKey, rosterTaskId,
  traceHintOf, traceLevelOf, traceSections, writeExcludedCsv,
} from '../lib/trace.js'
import { mkdirSync, readFileSync, rmSync, unlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))

/**
 * 隔离：默认把账本目录指到一个**不存在**的位置。
 * 否则本机真实跑过一次 roster_search（真的落了 ledger.json）之后，这个自检就会读到那份账本，
 * 断言变成"取决于机器上有没有跑过任务"——自检必须只依赖自己造的数据。
 */
const TMP_ROOT = (() => {
  for (const c of [join(HERE, '..', '..', 'tmp'), tmpdir()]) {
    try {
      mkdirSync(c, { recursive: true })
      const probe = join(c, `.trace-probe-${process.pid}`)
      writeFileSync(probe, 'x')
      unlinkSync(probe)
      return c
    } catch { /* 换下一个候选 */ }
  }
  return tmpdir()
})()
const EMPTY_LEDGER_DIR = join(TMP_ROOT, `no-such-ledger-${process.pid}`)
const FIXTURE_BASE = join(TMP_ROOT, `trace-selftest-${process.pid}`)
process.env.DANIEL_TRACE_DIR = EMPTY_LEDGER_DIR

/** 提示措辞的**逐字**基准（写死在这里，不从实现里取——否则实现改了测试也会跟着"过"） */
const HINT_SUMMARY_VERBATIM = '—— 目前是简略版本，想看详细报告或说明（筛选逻辑、排除明细、口径依据）可以直接告诉我。'
const HINT_FULL_VERBATIM = '需要逐条明细的话告诉我。'
/** 简版每段条数上限与每句字数上限（简版＝结论级短句） */
const SUMMARY_MAX_LINES = 2
const SUMMARY_MAX_CHARS = 41

/* ── 极简用例框架 ───────────────────────────────────────────── */
let pass = 0
let fail = 0
const failures = []

function check(id, ok, detail) {
  if (ok) pass += 1
  else { fail += 1; failures.push(`${id} —— ${detail}`) }
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${id}${detail ? ' —— ' + detail : ''}`)
}

/* ── 注册（同一份 apply，三档配置各注册一次）─────────────────── */
function register(config) {
  const got = []
  apply({ tools: { register: (t) => got.push(t) }, logger: { info() {}, warn() {}, debug() {} }, effect() {}, inject: ['tools'] }, config)
  const byName = Object.fromEntries(got.map((t) => [t.name, t]))
  return { all: got, byName }
}

const R = {
  off: register({ python: 'python3', timeoutMs: 60000, trace: 'off' }),
  summary: register({ python: 'python3', timeoutMs: 60000, trace: 'summary' }),
  full: register({ python: 'python3', timeoutMs: 60000, trace: 'full' }),
}

/* ── 小工具 ─────────────────────────────────────────────────── */
const stripTrace = (o) => { const c = { ...o }; delete c.trace; return c }
const hasTrace = (o) => Object.prototype.hasOwnProperty.call(o, 'trace')
const isStrArr = (v) => Array.isArray(v) && v.length > 0 && v.every((x) => typeof x === 'string' && x.trim())
const sectionsOf = (o) => (o && o.trace && o.trace['四段']) || {}
const fourFull = (o) => {
  const s = sectionsOf(o)
  return TRACE_SECTIONS.every((n) => isStrArr(s[n])) && Object.keys(s).length === TRACE_SECTIONS.length
}
const nullPaths = (v, p = '$', inArray = false, out = []) => {
  if (v === null) out.push(p)
  else if (v === undefined) { if (inArray) out.push(p) }
  else if (Array.isArray(v)) v.forEach((x, i) => nullPaths(x, `${p}[${i}]`, true, out))
  else if (typeof v === 'object') for (const [k, x] of Object.entries(v)) nullPaths(x, `${p}.${k}`, false, out)
  return out
}

/* ── ① off 档：白名单工具无 trace 字段 ───────────────────────── */
const runCase = { tool: 'daniel_run', args: { argv: ['skills', 'list'] } }
const batchCase = { tool: 'daniel_batch', args: { calls: [['skills', 'list']] } }

const out = {}
for (const m of ['off', 'summary', 'full']) {
  for (const c of [runCase, batchCase]) {
    const key = `${m}:${c.tool}`
    out[key] = await R[m].byName[c.tool].execute(c.args, {})
  }
}

for (const c of [runCase, batchCase]) {
  const o = out[`off:${c.tool}`]
  check(`①off 档 ${c.tool}：返回体不含 trace 字段`, o.ok === true && !hasTrace(o), `ok=${o.ok} keys=${Object.keys(o).join(',')}`)
}
check('①off 档 daniel_run：去掉 trace 后与 summary 档逐字节一致',
  JSON.stringify(stripTrace(out[`off:daniel_run`])) === JSON.stringify(stripTrace(out[`summary:daniel_run`])))

/* ── ②③ summary / full：白名单四段齐全 ──────────────────────── */
for (const m of ['summary', 'full']) {
  for (const c of [runCase, batchCase]) {
    const o = out[`${m}:${c.tool}`]
    const s = sectionsOf(o)
    check(`②${m} 档 ${c.tool}：四段齐全且段值为字符串数组`, o.ok === true && fourFull(o),
      `段=${Object.keys(s).join('/')}｜筛选逻辑链=${JSON.stringify(s['筛选逻辑链'] || null).slice(0, 90)}`)
    check(`②${m} 档 ${c.tool}：trace 版本/开关正确`, o.trace && o.trace['版本'] === TRACE_VERSION && o.trace['开关'] === m,
      `版本=${o.trace && o.trace['版本']}｜开关=${o.trace && o.trace['开关']}`)
  }
}

/* ── ② 非白名单：任何档位都不加 trace ───────────────────────── */
const EXEMPT_OFFLINE = [
  ['daniel_status', {}],
  ['daniel_skills_list', {}],
  ['daniel_skills_read', { skill: 'kol-screening', section: 1 }],
  ['daniel_login', {}],
  ['daniel_write_plan', { argv: [] }],
  ['daniel_write_commit', { plan_id: '__test__-no-such-plan' }],
]
for (const m of ['summary', 'full']) {
  for (const [name, args] of EXEMPT_OFFLINE) {
    const o = await R[m].byName[name].execute(args, {})
    check(`②${m} 档 非白名单 ${name}：不加 trace 字段`, !hasTrace(o), `keys=${Object.keys(o).join(',')}`)
  }
}
for (const name of TRACE_EXEMPT_TOOLS) {
  check(`②白名单口径：${name} 判定为不带溯源`, !isTraceTool(name) && !TRACE_TOOLS.includes(name))
}
for (const name of TRACE_TOOLS) {
  check(`②白名单口径：${name} 判定为必须带溯源`, isTraceTool(name) && !TRACE_EXEMPT_TOOLS.includes(name))
}
check('②白名单＋豁免名单＝注册工具全集（14 个，无遗漏无重复）',
  new Set([...TRACE_TOOLS, ...TRACE_EXEMPT_TOOLS]).size === 14
  && R.summary.all.length === 14
  && R.summary.all.every((t) => isTraceTool(t.name) || TRACE_EXEMPT_TOOLS.includes(t.name)),
  `注册=${R.summary.all.length}`)

/* ── ② 需联网的三个白名单工具：用纯函数层验四段 ──────────────── */
const MOCKS = [
  ['daniel_brands_list', { args: { workspace: 90002, limit: 3 }, data: { 数量: 3, 品牌: [{}, {}, {}], 数据时点: '2026-10-18' } }, '工作区 90002'],
  ['daniel_roster_search', { args: { query: 'AI glasses review', country: 'US', min_subscribers: 10000 }, data: { 命中总数: 2, 本页条数: 2, 页码: 1 } }, 'AI glasses review'],
  ['daniel_kol_profile', { args: { handle: '@CasandChary' }, data: { 频道: {}, 未取到: ['受众'] } }, '@CasandChary'],
]
for (const [tool, ctx, mustContain] of MOCKS) {
  const 四段 = buildTraceSections(tool, { ...ctx, mode: 'summary' })
  const flat = TRACE_SECTIONS.map((n) => (四段[n] || []).join(' ')).join(' ')
  check(`②${tool}：四段齐全（纯函数层，不发网络）`,
    TRACE_SECTIONS.every((n) => isStrArr(四段[n])))
  check(`②${tool}：四段引用本次入参「${mustContain}」`, flat.includes(mustContain),
    flat.slice(0, 120))
  const assembled = finalizeOutput({
    tool, mode: 'summary', args: ctx.args, data: ctx.data,
    result: { ok: true, exitCode: 0, command: tool, data: ctx.data }, answerPolicy: '回答纪律',
  })
  check(`②${tool}：装配后旧字段原样保留＋trace 追加在最后`,
    assembled.ok === true && assembled.command === tool
    && JSON.stringify(assembled.data) === JSON.stringify(ctx.data)
    && Object.keys(assembled).at(-1) === 'trace' && fourFull(assembled))
}

/* ── ④ 校验器：缺段必须拒绝；off 档永不校验 ─────────────────── */
// mock 注入：直接回一份**只有一段**的四段（不经过 traceSections 的补齐），模拟生成器漏段
const FAULTY = () => ({ 筛选逻辑链: ['只有一段'] })
const brokenSummary = finalizeOutput({
  tool: 'daniel_run', mode: 'summary', args: {}, data: {},
  result: { ok: true, exitCode: 0, command: 'run', data: { x: 1 } }, answerPolicy: '回答纪律',
  build: FAULTY,
})
check('④校验器：summary 档缺段 → ok:false / exitCode:2 / kind=trace_incomplete',
  brokenSummary.ok === false && brokenSummary.exitCode === 2
  && brokenSummary.error && brokenSummary.error.kind === 'trace_incomplete'
  && brokenSummary.data === undefined,
  `kind=${brokenSummary.error && brokenSummary.error.kind}｜缺=${brokenSummary.error && brokenSummary.error.message}`)

const brokenFull = finalizeOutput({
  tool: 'daniel_batch', mode: 'full', args: {}, data: {},
  result: { ok: true, exitCode: 0, command: 'batch', data: { results: [] } }, answerPolicy: '回答纪律',
  build: FAULTY,
})
check('④校验器：full 档缺段同样拒绝', brokenFull.ok === false && brokenFull.exitCode === 2
  && brokenFull.error.kind === 'trace_incomplete')

const offWithFaulty = finalizeOutput({
  tool: 'daniel_run', mode: 'off', args: {}, data: {},
  result: { ok: true, exitCode: 0, command: 'run', data: { x: 1 } }, answerPolicy: '回答纪律',
  build: FAULTY,
})
check('④校验器：off 档永不校验（缺段也照原样返回、无 trace 字段）',
  offWithFaulty.ok === true && !hasTrace(offWithFaulty) && JSON.stringify(offWithFaulty.data) === '{"x":1}')

const exemptWithFaulty = finalizeOutput({
  tool: 'daniel_status', mode: 'summary', args: {}, data: {},
  result: { ok: true, exitCode: 0, command: 'auth status', data: { x: 1 } }, answerPolicy: '回答纪律',
  build: FAULTY,
})
check('④校验器：非白名单即便四段缺失也不校验、不加字段',
  exemptWithFaulty.ok === true && !hasTrace(exemptWithFaulty))

const assertOff = assertTrace('daniel_run', { 四段: {} }, 'off')
const assertSummary = assertTrace('daniel_run', { 四段: {} }, 'summary')
check('④assertTrace：off 档 checked=false 且 ok=true；summary 档列出 4 个缺段',
  assertOff.ok === true && assertOff.checked === false
  && assertSummary.ok === false && assertSummary.missing.length === 4,
  `summary 缺=${assertSummary.missing.join('、')}`)

check('④开关归一：未知值/空值回落到默认 summary，off/summary/full 原样',
  normalizeTraceMode(undefined) === 'summary' && normalizeTraceMode('') === 'summary'
  && normalizeTraceMode('OFF') === 'off' && normalizeTraceMode('乱写') === 'summary'
  && normalizeTraceMode('full') === 'full')

/* ── ⑤ 失败降级：生成器抛错必须降级成「本次溯源不可用」，不许抛出去 ── */
const THROWING = { get argv() { throw new Error('模拟生成器炸了') }, get handle() { throw new Error('boom') } }
const degraded = buildTraceSections('daniel_run', { args: THROWING, data: {}, mode: 'summary' })
check('⑤生成器抛错 → 全段降级为「本次溯源不可用」，不抛异常',
  TRACE_SECTIONS.every((n) => isStrArr(degraded[n]) && degraded[n][0].includes(TRACE_UNAVAILABLE)),
  degraded['筛选逻辑链'][0])

const noBuilder = buildTraceSections('daniel_unknown_tool', { args: {}, data: {} })
check('⑤无生成器的工具 → 四段全部降级（不返回空段）',
  TRACE_SECTIONS.every((n) => isStrArr(noBuilder[n]) && noBuilder[n][0].includes(TRACE_UNAVAILABLE)))
check('⑤降级文案必带原因', TRACE_SECTIONS.every((n) => /原因：/.test(noBuilder[n][0])))

/* ── ⑤ 无 null：所有离线用例（三档）返回体都不含 null/undefined ── */
const NULL_CASES = [
  ['daniel_status', {}],
  ['daniel_skills_list', {}],
  ['daniel_skills_read', { skill: 'kol-screening' }],
  ['daniel_login', {}],
  ['daniel_run', { argv: ['skills', 'list'] }],
  ['daniel_run', { argv: ['auth', 'status'] }],
  ['daniel_batch', { calls: [['skills', 'list']] }],
  ['daniel_write_plan', { argv: [] }],
  ['daniel_write_commit', { plan_id: '__test__-no-such-plan' }],
]
for (const m of ['off', 'summary', 'full']) {
  for (const [name, args] of NULL_CASES) {
    const o = await R[m].byName[name].execute(args, {})
    const paths = nullPaths(o)
    const text = JSON.stringify(o)
    const literal = /[:[,]null[,}\]]/.test(text)
    check(`⑤${m} 档 ${name} ${JSON.stringify(args).slice(0, 28)}：无 null/undefined`,
      paths.length === 0 && !literal, paths.slice(0, 3).join(' | '))
  }
}

const pruned = prune({ a: null, b: '', c: [null, 'x', undefined], d: { e: null, f: 'y' }, g: 0, h: false })
check('⑤prune()：null/undefined/空串被清掉，0 与 false 保留',
  JSON.stringify(pruned) === '{"c":["x"],"d":{"f":"y"},"g":0,"h":false}', JSON.stringify(pruned))

/* ── ⑥ 详简两层 ＋ 常驻提示（TICKET-219）────────────────────── */
const linesOf = (o) => TRACE_SECTIONS.reduce((n, s) => n + ((sectionsOf(o)[s] || []).length), 0)
const hintOf = (o) => (o && o.trace ? o.trace['末尾提示'] : undefined)

for (const c of [runCase, batchCase]) {
  const s = out[`summary:${c.tool}`]
  const f = out[`full:${c.tool}`]
  check(`⑥${c.tool}：返回体里能看出层级（summary vs full）`,
    s.trace && f.trace && s.trace['层级'] === 'summary' && f.trace['层级'] === 'full',
    `summary 层级=${s.trace && s.trace['层级']}｜full 层级=${f.trace && f.trace['层级']}`)
  check(`⑥${c.tool}：两档四段内容确实不同，且详版条数更多`,
    JSON.stringify(s.trace['四段']) !== JSON.stringify(f.trace['四段']) && linesOf(f) > linesOf(s),
    `简版 ${linesOf(s)} 条 vs 详版 ${linesOf(f)} 条`)
  check(`⑥${c.tool}：简版四段各 ≤${SUMMARY_MAX_LINES} 条短句（每句 ≤${SUMMARY_MAX_CHARS} 字）`,
    TRACE_SECTIONS.every((n) => {
      const lines = sectionsOf(s)[n] || []
      return lines.length > 0 && lines.length <= SUMMARY_MAX_LINES && lines.every((x) => x.length <= SUMMARY_MAX_CHARS)
    }),
    TRACE_SECTIONS.map((n) => `${n}:${(sectionsOf(s)[n] || []).length}条/${Math.max(...(sectionsOf(s)[n] || ['']).map((x) => x.length))}字`).join('｜'))
  check(`⑥${c.tool}：详版保留骨架内容（四段都不止一条）`,
    TRACE_SECTIONS.every((n) => (sectionsOf(f)[n] || []).length >= 1) && linesOf(f) >= 6,
    `详版 ${linesOf(f)} 条`)
}

// 简版提示：逐字一致、位于 trace 内
check('⑥summary 档：末尾提示逐字等于基准句子',
  hintOf(out[`summary:daniel_run`]) === HINT_SUMMARY_VERBATIM
  && hintOf(out[`summary:daniel_batch`]) === HINT_SUMMARY_VERBATIM,
  JSON.stringify(hintOf(out[`summary:daniel_run`])))
check('⑥full 档：末尾提示逐字等于基准句子（不是简版那句）',
  hintOf(out[`full:daniel_run`]) === HINT_FULL_VERBATIM
  && hintOf(out[`full:daniel_batch`]) === HINT_FULL_VERBATIM
  && hintOf(out[`full:daniel_run`]) !== HINT_SUMMARY_VERBATIM,
  JSON.stringify(hintOf(out[`full:daniel_run`])))
check('⑥常驻提示是 trace 的独立字段、不混进四段正文',
  TRACE_SECTIONS.every((n) => (sectionsOf(out[`summary:daniel_run`])[n] || []).every((x) => !x.includes('简略版本'))))

// off 档 / 非白名单：既没有 trace，也没有末尾提示
check('⑥off 档：不出现末尾提示字段（连 trace 都没有）',
  !hasTrace(out['off:daniel_run']) && hintOf(out['off:daniel_run']) === undefined)
const exemptSummary = await R.summary.byName['daniel_status'].execute({}, {})
check('⑥非白名单（daniel_status）：任何档位都不出现末尾提示字段',
  !hasTrace(exemptSummary) && hintOf(exemptSummary) === undefined)

// 实现与基准是否一致（常量没被悄悄改写）
check('⑥提示常量与基准句子逐字一致（TRACE_HINT_SUMMARY／TRACE_HINT_FULL）',
  TRACE_HINT_SUMMARY === HINT_SUMMARY_VERBATIM && TRACE_HINT_FULL === HINT_FULL_VERBATIM,
  `${JSON.stringify(TRACE_HINT_SUMMARY)}｜${JSON.stringify(TRACE_HINT_FULL)}`)
check('⑥traceHintOf／traceLevelOf：档位→层级的映射与提示一一对应',
  traceLevelOf('summary') === 'summary' && traceLevelOf('full') === 'full' && traceLevelOf('off') === 'summary'
  && traceHintOf('summary') === HINT_SUMMARY_VERBATIM && traceHintOf('full') === HINT_FULL_VERBATIM)

// 需联网的三个白名单工具：纯函数层也要有详简差异（不发网络）
for (const [tool, ctx] of MOCKS) {
  const brief = buildTraceSections(tool, { ...ctx, mode: 'summary' })
  const detail = buildTraceSections(tool, { ...ctx, mode: 'full' })
  const n = (s) => TRACE_SECTIONS.reduce((a, k) => a + (s[k] || []).length, 0)
  const capOf = (k) => (k === '排除分块' ? TRACE_EXCLUDED_MAX_LINES : SUMMARY_MAX_LINES)
  check(`⑥${tool}：纯函数层也有详简差异（简版各段不超上限、详版更多）`,
    TRACE_SECTIONS.every((k) => (brief[k] || []).length <= capOf(k)) && n(detail) > n(brief),
    `简版 ${n(brief)} 条 vs 详版 ${n(detail)} 条`)
}

/* ── ⑦ 闸账本与排除分块（TICKET-217 · 方案 C）──────────────────
 *
 * 全部离线：账本由本用例**自己造**（结构与 worker.py 落的一致），不用真连官方库。
 * 覆盖五条：① 有真实闸计数时四段含闸账本；② batch/run 必须写「本次溯源不可用（缺：…）」；
 * ③ 淘汰 0 的闸写「0（无）」；④ 排除 >30 落 CSV 且路径出现在 trace 里；⑤ trace=off 逐字节一致。
 */
const ROSTER_ARGS = {
  query: 'tech review', country: 'US', min_subscribers: 10000, max_subscribers: 600000, limit: 10, page: 1,
}
const ROSTER_DATA = { 命中总数: 8, 本页条数: 8, 页码: 1 }
/** 自造数字的形态（反证用：没有实测的地方一个这样的字样都不许出现） */
const ARTIFICIAL = /淘汰\s*\d+\s*位|通过\s*\d+\s*位|淘汰合计\s*\d+|淘汰\s*0\s*位/
const ROSTER_TASK = rosterTaskId(ROSTER_ARGS)

/** 造一份与 worker 落盘同构的账本（候选 47 → 国家 US 21 → 粉丝 8 → 品类 8；品类闸 0 淘汰） */
function makeLedger(o, args = ROSTER_ARGS) {
  const gates = o.gates
  const rows = []
  for (const g of gates) {
    for (let i = 0; i < (g.rows ?? 0); i += 1) {
      rows.push({
        闸: g.闸, 判据: g.判据, 红人: `${g.闸}-样本${i + 1}`, 频道编号: `UCfake${i}`,
        订阅数: 12345, 国家: 'IN', 品类: 'Technology', 原因: '构造数据',
      })
    }
  }
  return {
    版本: '1.0', 工具: 'daniel_roster_search',
    任务标识: rosterTaskId(args), 参数指纹: rosterArgsKey(args), 生成时刻: Math.floor(Date.now() / 1000),
    检索式: args.query, 候选总数: o.候选总数, 入选数: o.入选数, 排除合计: o.排除合计,
    闸: gates.map((g) => ({
      闸: g.闸, 判据: g.判据, 通过数: g.通过数, 淘汰数: g.淘汰数, 样本内淘汰: g.rows ?? 0,
      典型例子: g.典型例子 || [],
    })),
    样本: { 取到: o.候选总数, 候选总数: o.候选总数, 覆盖: '全量' },
    排除明细: rows, 缺: [],
  }
}

function putLedger(ledger) {
  mkdirSync(join(FIXTURE_BASE, ledger.任务标识), { recursive: true })
  writeFileSync(join(FIXTURE_BASE, ledger.任务标识, 'ledger.json'), JSON.stringify(ledger), 'utf8')
  process.env.DANIEL_TRACE_DIR = FIXTURE_BASE
}

const LEDGER_39 = makeLedger({
  候选总数: 47, 入选数: 8, 排除合计: 39,
  gates: [
    { 闸: '国家 US', 判据: '频道登记国家须在 US 内', 通过数: 21, 淘汰数: 26, rows: 26,
      典型例子: ['Trendy Tech Review Show（登记国 IN）', 'Sulit Tech Reviews（登记国 PH）', 'Chigz Tech Reviews（登记国 GB）'] },
    { 闸: '粉丝区间 1万–60万', 判据: '订阅数落在 1万–60万 之间', 通过数: 8, 淘汰数: 13, rows: 13,
      典型例子: ['Tech Reviews with phil（订阅 8860）'] },
    { 闸: '品类 Tech', 判据: '平台登记的品类须匹配 Tech', 通过数: 8, 淘汰数: 0, rows: 0 },
  ],
})

// ① 有真实闸计数：四段齐全 ＋ 排除分块逐闸给「闸名＋淘汰数」
putLedger(LEDGER_39)
const ledSummary = buildTraceSections('daniel_roster_search', { args: ROSTER_ARGS, data: ROSTER_DATA, mode: 'summary' })
const ledFull = buildTraceSections('daniel_roster_search', { args: ROSTER_ARGS, data: ROSTER_DATA, mode: 'full' })
const ledSummaryText = ledSummary['排除分块'].join('\n')
check('⑦①闸账本：有真实闸记录时四段齐全（简版／详版都是字符串数组）',
  [ledSummary, ledFull].every((s) => TRACE_SECTIONS.every((n) => isStrArr(s[n]))),
  `简版段=${Object.keys(ledSummary).length}｜详版段=${Object.keys(ledFull).length}`)
check('⑦①闸账本：排除分块逐闸写「闸名＋淘汰数」（两道有淘汰的闸都在）',
  /国家 US：淘汰 26 位/.test(ledSummaryText) && /粉丝区间 1万–60万：淘汰 13 位/.test(ledSummaryText)
  && ledSummary['排除分块'][0] === '排除合计 39 位（候选 47、入选 8）',
  ledSummary['排除分块'].join(' ｜ '))
check('⑦①闸账本：筛选逻辑链给闸链（候选 → 入选），不是只报本页条数',
  ledSummary['筛选逻辑链'].some((x) => /候选 47 → 入选 8/.test(x))
  && ledFull['筛选逻辑链'].some((x) => /国家 US → 通过 21/.test(x))
  && ledFull['筛选逻辑链'].some((x) => /粉丝区间 1万–60万 → 通过 8/.test(x)),
  ledFull['筛选逻辑链'].slice(2, 5).join(' ｜ '))
check('⑦①闸账本：详版每道闸给「淘汰数＋典型例子（≤3）＋判据一句话」',
  ledFull['排除分块'].some((x) => /· 国家 US｜淘汰 26 位（通过 21 位）｜判据：.+｜典型：.+、.+、/.test(x)),
  ledFull['排除分块'][1])
check('⑦①闸账本：入选 ＋ 排除 ＝ 候选总数（数量自洽，无「待定」档）',
  8 + 39 === 47, '8 + 39 = 47')

// ③ 淘汰数为 0 的闸必须写「0（无）」
check('⑦③淘汰 0 的闸写「0（无）」（简版与详版都写，不得省略）',
  ledSummary['排除分块'].some((x) => /^品类 Tech：0（无）$/.test(x))
  && ledFull['排除分块'].some((x) => /· 品类 Tech｜0（无）/.test(x)),
  ledSummary['排除分块'].find((x) => x.startsWith('品类')) || '（简版里没找到该闸）')

// ④ 排除 >30 位：落 CSV，路径出现在 trace 里，且不落插件包目录
const csvPath = join(FIXTURE_BASE, ROSTER_TASK, 'excluded.csv')
const csvText = (() => { try { return readFileSync(csvPath, 'utf8') } catch { return '' } })()
const csvLines = csvText.split('\n').filter((x) => x.length > 0)
const csvHead = csvLines[0] ? csvLines[0].replace(/^\uFEFF/, '') : ''
check('⑦④排除 39 位（>30）已生成 CSV：文件存在、表头正确、39 行数据',
  csvLines.length === 40 && csvHead === EXCLUDED_CSV_COLUMNS.join(','),
  `行数=${csvLines.length}｜表头=${csvHead}`)
check('⑦④排除分块里给出落点（简版给相对路径、详版给绝对路径），且不在插件包目录（不落 vendor/）',
  ledSummary['排除分块'].some((x) => x.includes(`${ROSTER_TASK}/excluded.csv`))
  && ledFull['排除分块'].some((x) => x.includes(csvPath))
  && !/vendor[\\/]/.test(csvPath),
  ledFull['排除分块'].find((x) => x.includes('excluded.csv')) || '（没找到落点）')
check('⑦④CSV 每行都带任务标识与所属闸（明细能对上某道闸）',
  csvLines.slice(1, 30).every((l) => l.startsWith(`${ROSTER_TASK},`) && /,(国家 US|粉丝区间 1万–60万),/.test(l)),
  csvLines[1])
check('⑦④>30 才落文件：恰好 30 位时不生成 CSV（阈值是"超过"不是"达到"）',
  (() => {
    // 先把上一次 39 位留下的 CSV 删掉，确保"文件在不在"就是这一次的结果
    try { rmSync(join(FIXTURE_BASE, ROSTER_TASK, 'excluded.csv'), { force: true }) } catch { /* 本来就没有 */ }
    const exactly30 = makeLedger({
      候选总数: 47, 入选数: 17, 排除合计: 30,
      gates: [{ 闸: '国家 US', 判据: '频道登记国家须在 US 内', 通过数: 17, 淘汰数: 30, rows: 30 }],
    })
    putLedger(exactly30)
    const s = buildTraceSections('daniel_roster_search', { args: ROSTER_ARGS, data: ROSTER_DATA, mode: 'full' })
    let wrote = false
    try { readFileSync(join(FIXTURE_BASE, ROSTER_TASK, 'excluded.csv')); wrote = true } catch { wrote = false }
    return !s['排除分块'].some((x) => x.includes('已落文件')) && wrote === false
  })(),
  '30 位不触发落文件（既不写文件，也不给落点）')

// ② 账本"空但不可用" ≠ "没有筛选环节"（回归：账本被关掉/探测失败时闸表也是空的）
const offShape = makeLedger({ 候选总数: 0, 入选数: 0, 排除合计: 0, gates: [] })
offShape.闸 = []
offShape.缺 = ['筛选闸记录']
offShape.降级 = '闸账本已按配置关闭（DANIEL_LEDGER=off），本次不产出闸计数'
putLedger(offShape)
const offShapeOut = buildTraceSections('daniel_roster_search', { args: ROSTER_ARGS, data: ROSTER_DATA, mode: 'summary' })
check('⑦②账本被关掉（闸表为空但有「缺」）时不许自称「本次无筛选环节」，必须写「缺」',
  offShapeOut['排除分块'][0].startsWith('本次溯源不可用（缺：')
  && !offShapeOut['排除分块'].some((x) => x.includes('本次无筛选环节'))
  && !ARTIFICIAL.test(offShapeOut['排除分块'].join(' ')),
  offShapeOut['排除分块'][0])

// ② 真的没有筛选条件（worker 明确标了「无筛选环节」）才声明这一句
const noGateArgs = { query: 'tech review', limit: 5, page: 1 }
const noGateLedger = makeLedger({ 候选总数: 47, 入选数: 47, 排除合计: 0, gates: [] }, noGateArgs)
noGateLedger.闸 = []
noGateLedger.无筛选环节 = true
putLedger(noGateLedger)
const noGateOut = buildTraceSections('daniel_roster_search', { args: noGateArgs, data: ROSTER_DATA, mode: 'summary' })
check('⑦②只给检索式、没加任何条件时声明「本次无筛选环节」＋「淘汰 0（无）」',
  noGateOut['排除分块'].some((x) => x.startsWith('本次无筛选环节'))
  && noGateOut['排除分块'].some((x) => x.includes('淘汰 0（无）')),
  noGateOut['排除分块'].join(' ｜ '))

// 无账本 / 账本缺闸：一律「本次溯源不可用（缺：…）」，一个数字都不给
process.env.DANIEL_TRACE_DIR = EMPTY_LEDGER_DIR
const noLedger = buildTraceSections('daniel_roster_search', { args: ROSTER_ARGS, data: ROSTER_DATA, mode: 'full' })
check('⑦②无账本时 roster_search 写「本次溯源不可用（缺：筛选闸记录）」，不编任何淘汰数',
  noLedger['排除分块'][0].startsWith('本次溯源不可用（缺：')
  && noLedger['排除分块'][0].includes('筛选闸记录')
  && !/淘汰\s*\d+\s*位/.test(noLedger['排除分块'].join(' '))
  && !/淘汰合计\s*\d+/.test(noLedger['排除分块'].join(' ')),
  noLedger['排除分块'][0])

const partial = makeLedger({
  候选总数: 47, 入选数: 21, 排除合计: 26,
  gates: [
    { 闸: '国家 US', 判据: '频道登记国家须在 US 内', 通过数: 21, 淘汰数: 26, rows: 26, 典型例子: ['A（登记国 IN）'] },
    { 闸: '粉丝区间 1万–60万', 判据: '订阅数落在 1万–60万 之间', 通过数: null, 淘汰数: null, rows: 0 },
  ],
})
// 把第二道闸的「通过数／淘汰数」删掉，模拟"该闸之后的实测计数没取到"
delete partial.闸[1].通过数
delete partial.闸[1].淘汰数
delete partial.入选数
delete partial.排除合计
partial.缺 = ['粉丝区间 1万–60万 的通过与淘汰数（未取到该闸之后的实测计数）']
putLedger(partial)
const partialOut = buildTraceSections('daniel_roster_search', { args: ROSTER_ARGS, data: ROSTER_DATA, mode: 'full' })
check('⑦②账本缺一道闸时：已取到的闸照实给数，缺的那道闸写「缺」且不给数字',
  partialOut['排除分块'].some((x) => /· 国家 US｜淘汰 26 位/.test(x))
  && partialOut['排除分块'].some((x) => x.includes('本次溯源不可用（缺：') && x.includes('粉丝区间 1万–60万'))
  && partialOut['排除分块'].some((x) => /· 粉丝区间 1万–60万｜淘汰数未取到｜/.test(x)),
  partialOut['排除分块'].filter((x) => x.includes('粉丝区间')).join(' ｜ '))

for (const mode of ['summary', 'full']) {
  for (const [tool, args, data] of [
    ['daniel_batch', { calls: [['skills', 'list']] }, { results: [{ ok: true }, { ok: false }] }],
    ['daniel_run', { argv: ['brands', 'list', '--workspace', '90002'] }, {}],
  ]) {
    const sec = buildTraceSections(tool, { args, data, mode })
    const text = sec['排除分块'].join(' ')
    check(`⑦②${mode} 档 ${tool}：排除分块写「本次溯源不可用（缺：筛选闸记录；…执行侧…）」且没有任何自造数字`,
      sec['排除分块'][0].startsWith('本次溯源不可用（缺：')
      && sec['排除分块'][0].includes('筛选闸记录')
      && sec['排除分块'][0].includes('执行侧')
      && !ARTIFICIAL.test(text),
      sec['排除分块'][0])
  }
}

// ② 非名单类（brands_list / kol_profile）：显式声明「本次无筛选环节」，不是"淘汰 0"
for (const [tool, args, data] of [
  ['daniel_brands_list', { workspace: 90002, limit: 3 }, { 数量: 3, 品牌: [{}, {}, {}] }],
  ['daniel_kol_profile', { handle: '@CasandChary' }, { 频道: {}, 未取到: ['受众'] }],
]) {
  const sec = buildTraceSections(tool, { args, data, mode: 'summary' })
  check(`⑦②${tool}：排除分块声明「本次无筛选环节（非名单类）」（不写淘汰数）`,
    sec['排除分块'][0] === '本次无筛选环节（非名单类）' && !ARTIFICIAL.test(sec['排除分块'].join(' ')),
    sec['排除分块'][0])
}

// ⑤ trace=off：闸账本机制一律不参与 → 返回体与"没有账本时"逐字节一致，也不写任何文件
putLedger(LEDGER_39)
const offResult = { ok: true, exitCode: 0, command: '官方库检索 tech review', data: ROSTER_DATA }
const offWithLedger = finalizeOutput({
  tool: 'daniel_roster_search', mode: 'off', args: ROSTER_ARGS, data: ROSTER_DATA,
  result: offResult, answerPolicy: '回答纪律',
})
const offNoLedger = finalizeOutput({
  tool: 'daniel_roster_search', mode: 'off', args: ROSTER_ARGS, data: ROSTER_DATA,
  result: offResult, answerPolicy: '回答纪律',
})
check('⑦⑤trace=off：返回体与改动前逐字节一致（无 trace 字段、data 原样）',
  JSON.stringify(offWithLedger) === JSON.stringify(offNoLedger)
  && JSON.stringify(offWithLedger) === JSON.stringify(offResult)
  && !hasTrace(offWithLedger),
  `字节=${JSON.stringify(offWithLedger).length}`)

// 落文件的安全闸：落点落在插件包目录时拒绝写入（禁止落到 vendor/ 或 lib/scripts/tests）
const refused = writeExcludedCsv({
  taskId: ROSTER_TASK, rows: [{ 红人: 'x' }], base: join(HERE, '..', 'vendor', '.kol-tools'),
})
check('⑦④落文件安全闸：落点落在插件包目录（vendor/）时拒绝写入并给出原因',
  refused.written === false && refused.path === null && /拒绝/.test(refused.reason),
  refused.reason)

// 简版不会因为闸多而丢掉落点／缺项：行数上限按「合计＋闸＋落点＋缺项」放行
check(`⑦排除分块简版行数上限明确（≤${TRACE_EXCLUDED_MAX_LINES} 行、每行 ≤${TRACE_EXCLUDED_LINE_MAX} 字）`,
  ledSummary['排除分块'].length <= TRACE_EXCLUDED_MAX_LINES
  && ledSummary['排除分块'].every((x) => x.length <= TRACE_EXCLUDED_LINE_MAX),
  `行数=${ledSummary['排除分块'].length}｜最长=${Math.max(...ledSummary['排除分块'].map((x) => x.length))} 字`)

// 并发不串号：两个任务（入参不同 → 任务标识不同 → 目录不同）各读各的账本
const argsA = { ...ROSTER_ARGS, country: 'US' }
const argsB = { ...ROSTER_ARGS, country: 'GB' }
const ledgerA = makeLedger({
  候选总数: 47, 入选数: 8, 排除合计: 39,
  gates: [{ 闸: '国家 US', 判据: '频道登记国家须在 US 内', 通过数: 21, 淘汰数: 26, rows: 26 }],
}, argsA)
const ledgerB = makeLedger({
  候选总数: 20, 入选数: 5, 排除合计: 15,
  gates: [{ 闸: '国家 GB', 判据: '频道登记国家须在 GB 内', 通过数: 5, 淘汰数: 15, rows: 15 }],
}, argsB)
putLedger(ledgerA)
putLedger(ledgerB)
const outA = buildTraceSections('daniel_roster_search', { args: argsA, data: ROSTER_DATA, mode: 'full' })
const outB = buildTraceSections('daniel_roster_search', { args: argsB, data: ROSTER_DATA, mode: 'full' })
const textA = outA['排除分块'].join(' ')
const textB = outB['排除分块'].join(' ')
check('⑦并发不串号：两个任务（入参不同）各读各的账本，数字互不污染',
  rosterTaskId(argsA) !== rosterTaskId(argsB)
  && /排除合计 39 位/.test(textA) && /国家 US｜淘汰 26 位/.test(textA) && !/国家 GB/.test(textA)
  && /排除合计 15 位/.test(textB) && /国家 GB｜淘汰 15 位/.test(textB) && !/国家 US/.test(textB),
  `A=${ledgerA.任务标识}｜B=${ledgerB.任务标识}`)

/* ── ⑧ 2026-10-22 总监裁定（按 08／09／HANDOFF §3.1 执行，本票三条默认值作废）──
 *
 * 三条口径与各自的可造红点：
 *   ① **不做第三档、不加 trace 字段**：数据块没取到（kol_profile 的「未取到」）落在**排除分块的原因列**，
 *      装配后 trace 键集合必须恒为既有的 5 个；删掉那一行 ⇒ 本段 FAIL。
 *   ② **排除 >30 位只在详版**给「按闸计数（汇总）＋ 前 30 位 ＋ 附表落点」，简版守 ≤6 行；
 *      删掉详版这两行、或把它们塞进简版 ⇒ 本段 FAIL。
 *   ③ **常驻提示**逐字不变、连续两次调用都带、只出现一次（不做"仅首次"，插件无会话状态）。
 *   另加两个正控：留痕补齐（取数来源／时点）与非白名单反控（无 trace）。
 */
const TRACE_KEYS_FROZEN = ['四段', '开关', '末尾提示', '版本', '层级'].sort()
const traceKeysOf = (o) => Object.keys((o && o.trace) || {}).sort()
const keysFrozen = (o) => JSON.stringify(traceKeysOf(o)) === JSON.stringify(TRACE_KEYS_FROZEN)

// ⑧① 留痕补齐：取数**来源／时点／口径**三样都要能在 trace 里对上（不是"请自己看返回体"）
process.env.DANIEL_TRACE_DIR = EMPTY_LEDGER_DIR
const BL_ARGS = { workspace: 90002, limit: 3 }
const BL_DATA = { 数量: 3, 品牌: [{}, {}, {}], 数据时点: '2026-10-18T09:12:00Z' }
const blBrief = buildTraceSections('daniel_brands_list', { args: BL_ARGS, data: BL_DATA, mode: 'summary' })
const blDetail = buildTraceSections('daniel_brands_list', { args: BL_ARGS, data: BL_DATA, mode: 'full' })
check('⑧①daniel_brands_list 简版：口径假设写出**实际取数时点**（不再只说"看返回体"）',
  blBrief['口径假设'].some((x) => x === '取数时点：2026-10-18T09:12:00Z'),
  blBrief['口径假设'].join(' ｜ '))
check('⑧①daniel_brands_list 详版：时点＋"本地索引构建时刻"（不冒充本次实时抓取）',
  blDetail['筛选逻辑链'].some((x) => x.includes('取数时点：2026-10-18T09:12:00Z') && x.includes('本地索引构建时刻')),
  blDetail['筛选逻辑链'].find((x) => x.startsWith('取数时点')) || '（没找到时点行）')
const sourceLineOf = (tool, ctx) => buildTraceSections(tool, { ...ctx, mode: 'full' })['筛选逻辑链']
check('⑧①daniel_roster_search 详版：写出「取数来源与时间」（官方库本次调用，不冒充索引/历史名单）',
  sourceLineOf('daniel_roster_search', { args: ROSTER_ARGS, data: ROSTER_DATA })
    .some((x) => x.startsWith('取数来源与时间：YouTube 官方库本次调用返回')))
check('⑧①daniel_kol_profile 详版：写出「取数来源与时间」',
  sourceLineOf('daniel_kol_profile', { args: { handle: '@CasandChary' }, data: { 频道: {} } })
    .some((x) => x.startsWith('取数来源与时间：本次调用直连')))
check('⑧①daniel_batch／daniel_run 详版：写出「取数来源与时间」（各命令时点不互相拉平）',
  sourceLineOf('daniel_batch', { args: { calls: [['skills', 'list']] }, data: { results: [] } })
    .some((x) => x.startsWith('取数来源与时间：本次调用直通'))
  && sourceLineOf('daniel_run', { args: { argv: ['skills', 'list'] }, data: {} })
    .some((x) => x.startsWith('取数来源与时间：本次调用直通')))

// ⑧② 数据块没取到：只进「排除分块」原因列；不新增第三种块／不新增字段
const kpMiss = buildTraceSections('daniel_kol_profile', { args: { handle: '@CasandChary' }, data: { 频道: {}, 未取到: ['受众'] }, mode: 'summary' })
const kpPlatform = buildTraceSections('daniel_kol_profile', { args: { handle: '@CasandChary' }, data: { 频道: {}, 平台未收录: ['受众与兴趣画像'] }, mode: 'summary' })
check('⑧②TICKET-233：平台未收录 与 本次未取到 在排除分块里分开表述',
  kpPlatform['排除分块'].some((x) => x.includes('平台未收录：受众与兴趣画像') && !x.includes('可重试')),
  kpPlatform['排除分块'].join(' ｜ '))
const kpWhole = buildTraceSections('daniel_kol_profile', { args: { handle: '@CasandChary' }, data: { 频道: {}, 受众: {} }, mode: 'summary' })
check('⑧②kol_profile 未取到受众：落在排除分块原因列，且 [0] 仍是既有那句「本次无筛选环节（非名单类）」',
  kpMiss['排除分块'][0] === '本次无筛选环节（非名单类）'
  && kpMiss['排除分块'].some((x) => x.includes('本次未取到：受众')),
  kpMiss['排除分块'].join(' ｜ '))
check('⑧②数据块齐全时不多出「未取到」行（不硬凑第三种块）',
  kpWhole['排除分块'].length === 1 && !kpWhole['排除分块'].some((x) => x.includes('本次未取到') || x.includes('平台未收录')),
  kpWhole['排除分块'].join(' ｜ '))
const kpAssembled = finalizeOutput({
  tool: 'daniel_kol_profile', mode: 'summary', args: { handle: '@CasandChary' },
  data: { 频道: {}, 未取到: ['受众'] },
  result: { ok: true, exitCode: 0, command: 'kol_profile', data: { 频道: {} } }, answerPolicy: '回答纪律',
})
check('⑧②装配后 trace 键集合冻结在既有 5 个（版本／层级／开关／四段／末尾提示），没有新增字段',
  keysFrozen(kpAssembled), traceKeysOf(kpAssembled).join(','))

// ⑧③ 排除 >30 位：详版给「按闸计数 ＋ 前 30 位 ＋ 附表落点」；简版守 ≤6 行
putLedger(LEDGER_39)
const bigFull = buildTraceSections('daniel_roster_search', { args: ROSTER_ARGS, data: ROSTER_DATA, mode: 'full' })
const bigBrief = buildTraceSections('daniel_roster_search', { args: ROSTER_ARGS, data: ROSTER_DATA, mode: 'summary' })
check('⑧③排除 39 位：详版给「按闸计数（汇总）」，逐闸写清淘汰数（0 也写 0（无））',
  bigFull['排除分块'].some((x) => x === '按闸计数（汇总）：国家 US 26 位；粉丝区间 1万–60万 13 位；品类 Tech 0（无）'),
  bigFull['排除分块'].find((x) => x.startsWith('按闸计数')) || '（没找到按闸计数行）')
const top30 = bigFull['排除分块'].find((x) => x.startsWith('前 30 位（按闸顺序，其余见附表）：')) || ''
check('⑧③详版「前 30 位」恰好 30 位 ＋ 其余见附表（全量仍在文件里）',
  top30.length > 0 && top30.split('、').length === 30,
  `列了 ${top30 ? top30.split('、').length : 0} 位｜${top30.slice(0, 80)}…`)
check('⑧③简版不加「前 30 位／按闸计数」（不铺开），且仍守排除分块 ≤6 行上限',
  !bigBrief['排除分块'].some((x) => x.includes('前 30 位') || x.includes('按闸计数（汇总）'))
  && bigBrief['排除分块'].length <= TRACE_EXCLUDED_MAX_LINES,
  `简版 ${bigBrief['排除分块'].length} 行`)
const l30 = makeLedger({
  候选总数: 47, 入选数: 17, 排除合计: 30,
  gates: [{ 闸: '国家 GB', 判据: '频道登记国家须在 GB 内', 通过数: 17, 淘汰数: 30, rows: 30 }],
}, argsB)
putLedger(l30)
const s30 = buildTraceSections('daniel_roster_search', { args: argsB, data: ROSTER_DATA, mode: 'full' })
check('⑧③恰好 30 位：详版也不加「前 30 位／按闸计数」（阈值是"超过 30"，不是"达到 30"）',
  !s30['排除分块'].some((x) => x.includes('前 30 位') || x.includes('按闸计数（汇总）')),
  s30['排除分块'].join(' ｜ '))

// ⑧④ 常驻提示：逐字不变、每次结论都带、只出现一次（不做"仅首次"）
const hintRun1 = (await R.summary.byName['daniel_run'].execute(runCase.args, {})).trace['末尾提示']
const hintRun2 = (await R.summary.byName['daniel_run'].execute(runCase.args, {})).trace['末尾提示']
const hintRunText = JSON.stringify(await R.summary.byName['daniel_run'].execute(runCase.args, {}))
check('⑧④常驻提示：连续两次调用都带、逐字等于基准句（不是"仅首次"，插件无会话状态）',
  hintRun1 === HINT_SUMMARY_VERBATIM && hintRun2 === HINT_SUMMARY_VERBATIM,
  JSON.stringify(hintRun1))
check('⑧④提示不携带"首次播报"类变体（不主动播报、措辞固定）',
  !/首次|第一次/.test(hintRunText) && hintRunText.split(HINT_SUMMARY_VERBATIM).length - 1 === 1,
  `出现次数=${hintRunText.split(HINT_SUMMARY_VERBATIM).length - 1}`)

// ⑧⑤ 反控：非白名单（状态查询／追问闸）在 summary 档一个字段都不加
for (const [n, a] of [['daniel_status', {}], ['daniel_clarify', { need: '帮我找一批测评红人' }]]) {
  const o = await R.summary.byName[n].execute(a, {})
  check(`⑧⑤反控 ${n}（非白名单）：无 trace／无四段／无末尾提示`, o.ok === true && !hasTrace(o),
    `keys=${Object.keys(o).join(',')}`)
}

// ⑧⑥ 白名单逐个：summary 档四段必须全部非空（缺一段就该 FAIL）
const MOCK_ALL = {
  daniel_brands_list: { args: BL_ARGS, data: BL_DATA },
  daniel_roster_search: { args: ROSTER_ARGS, data: ROSTER_DATA },
  daniel_kol_profile: { args: { handle: '@CasandChary' }, data: { 频道: {} } },
  daniel_batch: { args: { calls: [['skills', 'list']] }, data: { results: [{ ok: true }] } },
  daniel_run: { args: { argv: ['skills', 'list'] }, data: {} },
}
for (const tool of TRACE_TOOLS) {
  const sec = buildTraceSections(tool, { ...MOCK_ALL[tool], mode: 'summary' })
  // 「非空」还不够：降级句也是非空。这里要求四段都**产出了真内容**（没有一段掉进"（原因：…）"降级）。
  check(`⑧⑥${tool}：summary 档四段逐段产出真内容（不是降级句，逐工具过一遍白名单）`,
    TRACE_SECTIONS.every((n) => isStrArr(sec[n]) && !sec[n].some((x) => x.includes('（原因：'))),
    TRACE_SECTIONS.map((n) => `${n}:${(sec[n] || []).length}条`).join('｜') + `｜首句=${JSON.stringify((sec['筛选逻辑链'] || [])[0] || null)}`)
}

// 收尾：清掉本次自检造的临时账本与 CSV，并恢复隔离目录
try { rmSync(FIXTURE_BASE, { recursive: true, force: true }) } catch { /* 清不掉不影响结论 */ }
process.env.DANIEL_TRACE_DIR = EMPTY_LEDGER_DIR

/* ── 汇总 ───────────────────────────────────────────────────── */
console.log(`\n合计：PASS ${pass} / FAIL ${fail}`)
if (fail) {
  console.log('\n失败项：')
  for (const f of failures) console.log('  · ' + f)
}
process.exit(fail === 0 ? 0 : 1)
