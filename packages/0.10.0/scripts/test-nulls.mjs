/**
 * 无 null 自检（TICKET-220 ＋ TICKET-221）：所有可离线用例的返回体都不许出现 null／undefined。
 *
 * 为什么单列一个脚本：宿主对工具返回值做严格校验，只要出现一个 null 就报
 * `value is not lossless JSON`，**整次调用直接失败**（历史上踩过两次）。这条约束不能
 * 只靠"记得写 prune()"，得有一条能在改完代码后立刻跑的自检。
 *
 * 用法：node scripts/test-nulls.mjs
 * 覆盖：
 *   ① `tests/golden/cases.mjs` 里全部可离线用例（含 `daniel_run(['auth','status'])` 这条
 *      原始数据整段透传、`daniel_batch` 失败条目这两处前缺陷点）；
 *   ② 三档 trace 开关（off／summary／full）各跑一遍——加 trace 也不许引入空值；
 *   ③ 缺失信息必须是**文字**（「未取到」「不适用」），不是 null；
 *   ④ **构造数据**覆盖需联网的工具（TICKET-221）：`daniel_brand_view`／`daniel_brands_list`／
 *      `daniel_brand_count` 走的是业务视图（按"有则填、无则 null"组织）＋ `clean()` 直出，
 *      这里用构造的原始数据喂视图层、再走 `clean()`，离线验证「null 键消失、0 与 false 保留」。
 */
import { apply, clean, prune } from '../lib/index.js'
import { brandList, brandView } from '../lib/normalize.js'
import { buildTraceSections, finalizeOutput } from '../lib/trace.js'
import { CASES, SKIPPED } from '../tests/golden/cases.mjs'

let pass = 0
let fail = 0
const failures = []
function check(id, ok, detail) {
  if (ok) pass += 1
  else { fail += 1; failures.push(`${id} —— ${detail}`) }
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${id}${detail ? ' —— ' + detail : ''}`)
}

/** 结构层：返回第一条 null／（数组里的）undefined 路径 */
function nullPaths(v, path = '$', inArray = false, out = []) {
  if (v === null) out.push(path)
  else if (v === undefined) { if (inArray) out.push(path) }
  else if (Array.isArray(v)) v.forEach((x, i) => nullPaths(x, `${path}[${i}]`, true, out))
  else if (typeof v === 'object') for (const [k, x] of Object.entries(v)) nullPaths(x, `${path}.${k}`, false, out)
  return out
}

/** 字节层：序列化文本里不许出现 null 字面量（宿主看到的就是这串文本） */
const NULL_LITERAL = /(^|[\[{,:])\s*null\s*([,\]}:\n]|$)/

function register(traceMode) {
  const got = []
  apply({ tools: { register: (t) => got.push(t) }, logger: { info() {}, warn() {}, debug() {} }, effect() {}, inject: ['tools'] },
    { python: 'python3', timeoutMs: 30000, trace: traceMode })
  return Object.fromEntries(got.map((t) => [t.name, t]))
}

/** 定向补充：批量里的**写命令**分支（data 用「不适用」文字，过去是 null） */
const EXTRA = [
  { id: 'batch_write_needs_plan', tool: 'daniel_batch', args: { calls: [['brands', 'update', '--brand', '3690002', '--description', '插件自检试运行']] } },
]

const MODES = ['off', 'summary', 'full']
const tools = Object.fromEntries(MODES.map((m) => [m, register(m)]))

let calls = 0
let casesRun = 0
for (const mode of MODES) {
  for (const c of CASES) {
    const out = await tools[mode][c.tool].execute(c.args, {})
    calls += 1
    casesRun += 1
    const paths = nullPaths(out)
    const text = JSON.stringify(out)
    const bad = paths.length > 0 || NULL_LITERAL.test(text) || /undefined/.test(text)
    check(`①${mode} 档 ${c.id}（${c.tool}）返回体无 null/undefined`, !bad,
      bad ? `null 路径：${paths.slice(0, 4).join(' | ') || '（文本里出现 null 字面量）'}` : `${text.length} 字节`)
  }
  for (const c of EXTRA) {
    const out = await tools[mode][c.tool].execute(c.args, {})
    calls += 1
    casesRun += 1
    const paths = nullPaths(out)
    const text = JSON.stringify(out)
    const bad = paths.length > 0 || NULL_LITERAL.test(text) || /undefined/.test(text)
    check(`①${mode} 档 ${c.id}（${c.tool}）返回体无 null/undefined`, !bad,
      bad ? `null 路径：${paths.slice(0, 4).join(' | ')}` : `${text.length} 字节｜data=${JSON.stringify(out.data && out.data.results && out.data.results[0] && out.data.results[0].data).slice(0, 60)}`)
  }
}

/* ── ② 定向：两处前缺陷点（TICKET-220）───────── */
const runAuth = await tools.summary.daniel_run.execute({ argv: ['auth', 'status'] }, {})
const runAuthText = JSON.stringify(runAuth)
check('②daniel_run([\'auth\',\'status\'])：过去为 null 的两个键已不再出现',
  !/本机会话读取异常/.test(runAuthText) && !/服务端原文/.test(runAuthText) && nullPaths(runAuth).length === 0,
  `字节=${runAuthText.length}`)

const batchFail = await tools.summary.daniel_batch.execute({ calls: [['brands', 'show']] }, {})
const failEntry = ((batchFail.data || {}).results || [])[0] || {}
check('②daniel_batch 失败条目：data 是文字说明（不是 null）',
  typeof failEntry.data === 'string' && failEntry.data.includes('未取到') && nullPaths(batchFail).length === 0,
  `data=${JSON.stringify(failEntry.data)}`)

const batchWrite = await tools.summary.daniel_batch.execute({ calls: [['brands', 'update', '--brand', '3690002', '--description', '插件自检试运行']] }, {})
const writeEntry = ((batchWrite.data || {}).results || [])[0] || {}
check('②daniel_batch 写命令条目：data 是「不适用」文字（不是 null）',
  typeof writeEntry.data === 'string' && writeEntry.data.includes('不适用') && nullPaths(batchWrite).length === 0,
  `exitCode=${writeEntry.exitCode}｜data=${JSON.stringify(writeEntry.data).slice(0, 70)}`)

/* ── ③ 定向：状态与能力清单（最常调的两个）───────── */
for (const name of ['daniel_status', 'daniel_skills_list']) {
  const out = await tools.summary[name].execute({}, {})
  const text = JSON.stringify(out)
  check(`③${name}：无 null/undefined`, nullPaths(out).length === 0 && !NULL_LITERAL.test(text), `${text.length} 字节`)
}

/* ── ④ 构造数据：clean() 层统一兜底 prune（TICKET-221）─────────
 * 这三个工具的输出要联网才有，无法在断网机器上真跑；但它们的前缺陷面在**视图层 ＋ clean()**
 * 这一段（视图层按"有则填、无则 null"组织 → 过去 null 原样透出）。因此用构造数据喂视图层，
 * 再走 `clean()`，把这一段离线验掉。顺带验「0 与 false 不被误删」（prune 语义不变）。
 */
const cleanText = (o) => JSON.stringify(o)
const noNull = (o) => nullPaths(o).length === 0 && !NULL_LITERAL.test(cleanText(o)) && !/undefined/.test(cleanText(o))

// ④-1 daniel_brand_view：档案里大量可空字段（简介／品类／目标市场／关键词／样品价／关联频道）
const brandViewOut = clean({
  ok: true, command: 'brands show Lymow', exitCode: 0,
  data: {
    品牌: brandView({
      id: 4800023, name: 'Lymow',
      description: null, category: null, targetCountries: null, industryKeywords: null,
      competitors: [{ name: 'Halliday', categoryKeywords: null }, { name: null }],
      sampleCost: 0, youtubeChannelId: null, userId: 'internal-should-not-show',
    }),
    回答提示: '用业务语言复述',
  },
})
check('④daniel_brand_view（构造数据）：可空字段的 null 键全部消失、无 null/undefined',
  noNull(brandViewOut)
  && brandViewOut.data['品牌']['品牌名'] === 'Lymow'
  && !('简介' in brandViewOut.data['品牌']) && !('品类' in brandViewOut.data['品牌'])
  && !('关联频道' in brandViewOut.data['品牌']) && !('userId' in brandViewOut.data['品牌']),
  cleanText(brandViewOut.data['品牌']).slice(0, 120))
check('④daniel_brand_view（构造数据）：样品价 0 保留（不是被 prune 误删）',
  brandViewOut.data['品牌']['样品价'] === 0, `样品价=${cleanText(brandViewOut.data['品牌']['样品价'])}`)
check('④daniel_brand_view（构造数据）：竞品子字段缺失时不留 null',
  noNull(brandViewOut.data['品牌']['竞品']) && brandViewOut.data['品牌']['竞品'].length === 2,
  cleanText(brandViewOut.data['品牌']['竞品']))

// ④-2 daniel_brands_list：跨工作区清单（名称／工作区／数据时点都可能没给）
const brandsListOut = clean({
  ok: true, command: 'brands list', exitCode: 0,
  data: brandList({
    count: 2,
    brands: [{ id: 1, name: 'Lymow', workspaceName: null }, { id: 2, name: null, workspaceName: 'jack' }],
    indexBuiltAt: null,
  }),
})
check('④daniel_brands_list（构造数据）：清单项与数据时点的 null 键消失、无 null/undefined',
  noNull(brandsListOut)
  && brandsListOut.data['数量'] === 2
  && brandsListOut.data['品牌'].length === 2
  && !('所属工作区' in brandsListOut.data['品牌'][0])
  && !('品牌名' in brandsListOut.data['品牌'][1])
  && !('数据时点' in brandsListOut.data),
  cleanText(brandsListOut.data).slice(0, 140))

// ④-3 daniel_brand_count：实时口径（耗时可能缺）＋ 回落索引口径（数据时点可能缺）
const countLiveOut = clean({
  ok: true, command: '品牌计数（工作区 90002）', exitCode: 0,
  data: {
    工作区编号: 90002, 数量: 2,
    品牌: [{ 品牌名: 'Lymow', 品牌编号: 4800023 }, { 品牌名: null, 品牌编号: 4800024 }],
    口径: '实时（与网页端一致，未读本地索引）', 耗时毫秒: 0,
  },
})
check('④daniel_brand_count（构造数据·实时口径）：null 品牌名消失、耗时 0 保留',
  noNull(countLiveOut) && countLiveOut.data['数量'] === 2
  && countLiveOut.data['耗时毫秒'] === 0
  && !('品牌名' in countLiveOut.data['品牌'][1]),
  cleanText(countLiveOut.data).slice(0, 140))

const countIndexOut = clean({
  ok: false, command: 'brands list --workspace 90002（实时失败，回落索引）', exitCode: 1,
  data: {
    工作区编号: 90002, 数量: 1, 品牌: [{ 品牌名: 'Lymow', 品牌编号: 4800023, 所属工作区: null }],
    口径: '本地索引（实时接口未通）', 数据时点: null, 说明: '请把数据时点一并告知用户。',
  },
  error: { kind: 'live_query_failed', message: 'worker 不可用' },
})
check('④daniel_brand_count（构造数据·回落口径）：数据时点缺失时该键消失、ok:false 保留',
  noNull(countIndexOut) && countIndexOut.ok === false && countIndexOut.exitCode === 1
  && !('数据时点' in countIndexOut.data) && !('所属工作区' in countIndexOut.data['品牌'][0]),
  cleanText(countIndexOut.data).slice(0, 140))

// ④-4 clean()／prune() 本体：口径不变（去 null/undefined/空串，留 0 与 false）
const cleanBase = clean({
  ok: true, command: 'x', exitCode: 0,
  data: { a: null, b: '', c: 0, d: false, e: [], f: { g: null, h: 'keep' }, i: [null, 'x', undefined] },
  error: { kind: 'k', message: null, 建议: [] },
  note: null,
})
check('④clean()：内部统一过 prune()（null/undefined/空串消失，0／false／空数组保留）',
  noNull(cleanBase)
  && cleanBase.data['c'] === 0 && cleanBase.data['d'] === false
  && Array.isArray(cleanBase.data['e']) && cleanBase.data['f']['h'] === 'keep'
  && !('a' in cleanBase.data) && !('b' in cleanBase.data) && !('note' in cleanBase)
  && !('message' in cleanBase.error),
  cleanText(cleanBase).slice(0, 160))
check('④clean()：结构不变（ok／exitCode／回答纪律 三个必备键始终在）',
  typeof cleanBase.ok === 'boolean' && typeof cleanBase.exitCode === 'number'
  && typeof cleanBase['回答纪律'] === 'string')
check('④prune() 语义不变（与 0.9.2 一致）',
  JSON.stringify(prune({ a: null, b: '', c: [null, 'x', undefined], d: { e: null, f: 'y' }, g: 0, h: false }))
  === '{"c":["x"],"d":{"f":"y"},"g":0,"h":false}')
check('④遍历面：全部可离线用例（CASES）均已跑过，需联网的三个 clean() 直出工具已有构造数据用例',
  CASES.every((c) => c.offline !== false) && CASES.length > 0
  && ['daniel_brand_view', 'daniel_brands_list', 'daniel_brand_count'].every((n) => SKIPPED.some((s) => s.tool === n)))

/* ── ⑤ 闸账本（TICKET-217）：带账本的四段／装配后的返回体也不许出 null/undefined ──
 * 账本用**内联**方式给（data.闸账本），因此这条用例不读盘、不联网，也不写任何文件；
 * 顺带验「淘汰数 0 的闸不被当成空值丢掉」（0 是结论，不是缺失）。
 */
const LEDGER_INLINE = {
  版本: '1.0', 任务标识: 'roster-selftest', 参数指纹: 'selftest',
  生成时刻: Math.floor(Date.now() / 1000), 检索式: 'tech review',
  候选总数: 20, 入选数: 8, 排除合计: 12,
  闸: [
    { 闸: '国家 US', 判据: '频道登记国家须在 US 内', 通过数: 12, 淘汰数: 8, 典型例子: ['A（登记国 IN）'] },
    { 闸: '粉丝区间 1万–60万', 判据: '订阅数落在 1万–60万 之间', 通过数: 8, 淘汰数: 4, 典型例子: [] },
    { 闸: '品类 Tech', 判据: '平台登记的品类须匹配 Tech', 通过数: 8, 淘汰数: 0, 典型例子: [] },
  ],
  样本: { 取到: 20, 候选总数: 20, 覆盖: '全量' },
  排除明细: [{ 闸: '国家 US', 判据: '频道登记国家须在 US 内', 红人: 'A', 频道编号: 'UC1', 订阅数: 1234, 国家: 'IN', 品类: 'Technology', 原因: '登记国 IN' }],
  缺: [],
}
const ROSTER_CTX = {
  args: { query: 'tech review', country: 'US', min_subscribers: 10000, max_subscribers: 600000, limit: 10, page: 1 },
  data: { 命中总数: 8, 本页条数: 8, 页码: 1, 闸账本: LEDGER_INLINE },
}
for (const mode of ['summary', 'full']) {
  const sec = buildTraceSections('daniel_roster_search', { ...ROSTER_CTX, mode })
  const text = JSON.stringify(sec)
  check(`⑤${mode} 档 daniel_roster_search（内联账本）：四段无 null/undefined`,
    nullPaths(sec).length === 0 && !NULL_LITERAL.test(text) && !/undefined|NaN/.test(text),
    `${text.length} 字节`)
  check(`⑤${mode} 档 daniel_roster_search（内联账本）：淘汰 0 的闸写成「0（无）」（0 不当缺失丢掉）`,
    (sec['排除分块'] || []).some((x) => /品类 Tech：0（无）|· 品类 Tech｜0（无）/.test(x)),
    (sec['排除分块'] || []).find((x) => x.includes('品类')) || '（没找到品类闸）')
}
const assembledLedger = finalizeOutput({
  tool: 'daniel_roster_search', mode: 'summary', ...ROSTER_CTX,
  result: clean({ ok: true, command: '官方库检索 tech review', exitCode: 0, data: ROSTER_CTX.data }),
  answerPolicy: '回答纪律',
})
check('⑤装配后（clean ＋ trace）：返回体无 null/undefined，data 原样保留',
  nullPaths(assembledLedger).length === 0 && !NULL_LITERAL.test(JSON.stringify(assembledLedger))
  && assembledLedger.ok === true && assembledLedger.data['闸账本']['排除合计'] === 12,
  `${JSON.stringify(assembledLedger).length} 字节`)

console.log(`\n遍历：${casesRun} 次工具调用（${CASES.length + EXTRA.length} 个用例 × ${MODES.length} 档开关；累计 ${calls} 次）`)
console.log(`合计：PASS ${pass} / FAIL ${fail}`)
if (fail) {
  console.log('\n失败项：')
  for (const f of failures) console.log('  · ' + f)
}
process.exit(fail === 0 ? 0 : 1)
