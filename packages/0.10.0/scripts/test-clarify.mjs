/**
 * `daniel_clarify`（追问闸）自检 —— 不需要 DSH 宿主。
 *
 * 覆盖 TICKET-218 的六条硬要求：
 *   ① 一次给全：清单结构完整（缺项／优先补／口径类／下一步），且**项数 ≤ 8**；
 *   ② **优先补 Top3 必须存在**，且顺序与「缺项」的影响排序一致；
 *   ③ **口径类只列名字与影响、不给判据**（数字/比较符/阈值/算法式一律不许出现，正则反证）；
 *   ④ **明确需求不触发**：原话里已说明的参数不再问；全说清时零缺项；
 *   ⑤ **不执行任何取数**：源码层不起子进程/不读盘/不联网 ＋ 返回体层无任何业务数据；
 *   ⑥ 纯函数：同入参两次调用逐字节一致（不含时钟/随机，可进 golden 基线比对）。
 *
 * 用法：node scripts/test-clarify.mjs
 * 退出码：0 = FAIL 0；1 = 有 FAIL
 */
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { apply } from '../lib/index.js'
import {
  CLARIFY_MAX_ITEMS, CLARIFY_TOP_N, CLARIFY_TOPICS, CLARIFY_NEXT_STEP,
  clarifyPlan, clarifyTopicOf, inferTopic,
} from '../lib/clarify.js'

const HERE = dirname(fileURLToPath(import.meta.url))

/* ── 极简用例框架 ───────────────────────────────────────────── */
let pass = 0
let fail = 0
const failures = []
function check(id, ok, detail) {
  if (ok) pass += 1
  else { fail += 1; failures.push(`${id} —— ${detail}`) }
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${id}${detail ? ' —— ' + detail : ''}`)
}
const sha = (o) => createHash('sha256').update(JSON.stringify(o)).digest('hex')
const J = (o) => JSON.stringify(o)

/* ── 注册（真跑 apply，用假 ctx）──────────────────────────────── */
const reg = []
apply({ tools: { register: (t) => reg.push(t) }, logger: { info() {}, warn() {}, debug() {} }, effect() {}, inject: ['tools'] },
  { python: 'python3', timeoutMs: 30000, trace: 'summary' })
const byName = Object.fromEntries(reg.map((t) => [t.name, t]))
const screenAsk = reg.find((t) => t.name === 'daniel_screen_ask')
const clarify = byName.daniel_clarify

/* ── 固定入参（静态，不含业务数据）──────────────────────────── */
const AMBIGUOUS = '帮我找一批测评红人'
const EXPLICIT =
  '帮我找 US 市场 1 万到 10 万粉的 YouTube 长视频测评红人，要 20 位，交付 Excel 表格，本周五前给我，按近 30 天表现看，名单内排重'
const BY_TOPIC = {
  kol_search: '找一批测评红人',
  list_ops: '把两份名单合并一下',
  brand_setup: '帮我建一个品牌',
  generic: '帮我做一份资料',
}

const call = (args) => clarify.execute(args, {})
const out = await call({ need: AMBIGUOUS })
const d = (out && out.data) || {}
const outExplicit = await call({ need: EXPLICIT })
const dExplicit = (outExplicit && outExplicit.data) || {}

/* ═══════════════ ① 注册与参数契约 ═══════════════ */
check('①注册：工具总数 15（含 daniel_screen_ask），daniel_clarify 在列', reg.length === 15 && Boolean(clarify) && Boolean(screenAsk), `注册=${reg.length}`)
const params = clarify.parameters || {}
const props = params.properties || {}
const required = Array.isArray(params.required) ? params.required : []
check('①参数：need 必填、topic 可选',
  required.includes('need') && !required.includes('topic')
  && String(props.need && props.need.type) === 'string'
  && String(props.topic && props.topic.type) === 'string',
  `required=${J(required)}｜properties=${Object.keys(props).join(',')}`)
check('①参数：topic 只允许三个场景（枚举，不许自由填写）',
  Array.isArray(props.topic && props.topic.enum)
  && J([...(props.topic.enum || [])].sort()) === J([...CLARIFY_TOPICS].sort()),
  `enum=${J(props.topic && props.topic.enum)}`)
check('①参数：not required 的 topic 缺省也不报错（不传就按原话自动判断）',
  d['场景依据'] === '按需求原话自动判断（要指定场景就传 topic）', `场景依据=${d['场景依据']}`)

/* ═══════════════ ② 一次给全：清单结构与上限 ═══════════════ */
const BLOCKS = ['场景', '已识别项', '缺项', '优先补', '口径类', '下一步']
check('②返回体：四块清单齐全（缺项／优先补／口径类／下一步）＋场景头',
  out.ok === true && out.exitCode === 0 && BLOCKS.every((k) => k in d),
  `ok=${out.ok}｜keys=${Object.keys(d).join(',')}`)
check(`②缺项：项数 ≤ 上限 ${CLARIFY_MAX_ITEMS}（模糊需求下正好顶到上限）`,
  Array.isArray(d['缺项']) && d['缺项'].length > 0 && d['缺项'].length <= CLARIFY_MAX_ITEMS,
  `项数=${(d['缺项'] || []).length}`)
check('②缺项：每项都有「项名＋为什么问＋不答的默认值」且都非空',
  (d['缺项'] || []).every((it) => ['项名', '为什么问', '不答的默认值'].every(
    (k) => typeof it[k] === 'string' && it[k].trim().length > 0)),
  J((d['缺项'] || [])[0]))
check('②缺项：项名互不重复（同一件事不重复问）',
  new Set((d['缺项'] || []).map((it) => it['项名'])).size === (d['缺项'] || []).length,
  `去重后=${new Set((d['缺项'] || []).map((it) => it['项名'])).size}`)
check('②上限溢出：超出 8 项的部分不列，但写明「其余按默认口径执行」',
  typeof d['其余按默认口径执行'] === 'string' && /其余按默认口径执行/.test(d['其余按默认口径执行']),
  String(d['其余按默认口径执行'] || '（缺该说明）').slice(0, 90))

/* ═══════════════ ③ 优先补 Top3 ═══════════════ */
const top = d['优先补'] || []
check('③优先补：正好 3 项（Top3 存在）', top.length === CLARIFY_TOP_N, `项数=${top.length}`)
check('③优先补：每项都有「项名＋为什么先补」，且项名都在缺项里',
  top.every((t) => typeof t['项名'] === 'string' && typeof t['为什么先补'] === 'string'
    && t['为什么先补'].trim() && (d['缺项'] || []).some((it) => it['项名'] === t['项名'])),
  J(top.map((t) => t['项名'])))
check('③优先补：顺序＝缺项的影响排序（Top3 就是缺项前 3 项）',
  J(top.map((t) => t['项名'])) === J((d['缺项'] || []).slice(0, CLARIFY_TOP_N).map((it) => it['项名'])),
  `${J(top.map((t) => t['项名']))} vs ${J((d['缺项'] || []).slice(0, CLARIFY_TOP_N).map((it) => it['项名']))}`)

/* ═══════════════ ④ 口径类：只列名字与影响，不给判据 ═══════════════ */
const cal = d['口径类'] || []
check('④口径类：非空且只含「项名＋影响」两个字段（没有「默认值」这类可执行判据）',
  cal.length > 0 && cal.every((c) => J(Object.keys(c).sort()) === J(['影响', '项名'])),
  `项数=${cal.length}｜字段=${J(cal[0] && Object.keys(cal[0]))}`)
check('④口径类：项名都是「什么算…」这类口径问题，不是参数',
  cal.every((c) => /什么算/.test(c['项名'])),
  J(cal.map((c) => c['项名'])))
check('④口径类：每项都写明「插件不代拟」（不替用户做重大口径决定）',
  cal.every((c) => /插件不代拟/.test(c['影响'])),
  String(cal[0] && cal[0]['影响']))

/** 判据反证：口径类里**不许**出现任何可执行判据（阈值／比较符／算式／评分线） */
const VERDICT_PATTERNS = [
  { re: /[≥≤><]|>=|<=/, why: '比较符' },
  { re: /\d/, why: '任何数字（阈值/评分线/样本量都是判据）' },
  { re: /阈值|门槛|合格线|评分|打分|权重|判据[:：]|公式|折算/, why: '判据类词' },
  { re: /(按|以).{0,10}(计算|算出|折算|判定)/, why: '算式表述' },
  { re: /例如|比如|一般来说|超过|低于|高于/, why: '隐含判据的举例/区间表述' },
]
const calText = cal.map((c) => `${c['项名']}｜${c['影响']}`)
const hits = []
for (const t of calText) {
  for (const p of VERDICT_PATTERNS) if (p.re.test(t)) hits.push(`${p.why}: ${t.slice(0, 60)}`)
}
check('④口径类（正则反证）：不含任何判据 —— 无比较符／无数字／无阈值门槛／无算式',
  hits.length === 0, hits.length ? hits.slice(0, 3).join(' ｜ ') : `扫描 ${calText.length} 条，0 命中`)
check('④口径类与缺项不重叠：口径问题不会被混进「可答的参数项」里',
  cal.every((c) => !(d['缺项'] || []).some((it) => it['项名'] === c['项名'])),
  `${cal.length} 条口径类对 ${(d['缺项'] || []).length} 条参数项`)

/* ═══════════════ ⑤ 明确需求不触发 ═══════════════ */
const known = dExplicit['已识别项'] || []
check('⑤明确需求：原话里已说明的参数被认出来（至少 5 项）', known.length >= 5, `已识别=${known.length}｜${J(known)}`)
check('⑤明确需求：已识别的参数不再问（缺项与已识别项零重叠）',
  (dExplicit['缺项'] || []).every((it) => !known.includes(it['项名'])),
  `缺项=${J((dExplicit['缺项'] || []).map((it) => it['项名']))}`)
check('⑤明确需求：缺项明显少于模糊需求（不会把已经说过的再问一遍）',
  (dExplicit['缺项'] || []).length < (d['缺项'] || []).length,
  `${(dExplicit['缺项'] || []).length} 项 vs 模糊需求 ${(d['缺项'] || []).length} 项`)

const FULL = '帮我找 US 市场 1 万到 10 万粉的 YouTube 长视频测评红人，要 20 位，交付 Excel 表格，'
  + '本周五前给我，按近 30 天表现看，名单内排重，受众数据有则用无则标注缺失'
const outFull = await call({ need: FULL })
const dFull = (outFull && outFull.data) || {}
check('⑤全部说清：缺项为空（零触发，不硬凑问题）',
  Array.isArray(dFull['缺项']) && dFull['缺项'].length === 0 && (dFull['优先补'] || []).length === 0,
  `缺项=${(dFull['缺项'] || []).length}｜优先补=${(dFull['优先补'] || []).length}`)
check('⑤全部说清：明确给出「不需要追问」的结论与话术',
  outFull.ok === true && typeof dFull['结论'] === 'string' && /不需要追问/.test(dFull['结论'])
  && dFull['下一步'] !== CLARIFY_NEXT_STEP,
  `${dFull['结论']}｜下一步=${String(dFull['下一步']).slice(0, 30)}`)
check('⑤全部说清：仍然给出口径类（参数齐了也不等于口径齐了）',
  (dFull['口径类'] || []).length > 0, `${(dFull['口径类'] || []).length} 条`)

/* ═══════════════ ⑥ 不取数：源码层 ＋ 返回体层 ═══════════════ */
const src = readFileSync(join(HERE, '..', 'lib', 'clarify.js'), 'utf8')
const FORBIDDEN_SRC = [
  ['child_process', /child_process/],
  ['spawn/exec', /\bspawn\b|\bexecFile\b|\bexecSync\b/],
  ['起 worker', /worker\.py/],
  ['调 CLI', /daniel-cli|\bvendor\b/],
  ['读盘', /readFileSync|writeFileSync|createWriteStream/],
  ['网络', /\bfetch\(|https?:\/\//],
  ['时钟', /Date\.now|new Date\(/],
  ['随机', /Math\.random/],
]
const srcHits = FORBIDDEN_SRC.filter(([, re]) => re.test(src)).map(([n]) => n)
check('⑥不取数（源码层）：clarify.js 不起子进程／不读盘／不联网／不看时钟／不用随机',
  srcHits.length === 0, srcHits.length ? `命中：${srcHits.join('、')}` : '8 类禁项 0 命中')

/** 判据：不出现**一次取数的结果**（品牌名/红人数/金额/播放量）。
 *  注意口径：清单里的默认口径允许写量级（如「1 万到 60 万订阅」「默认给 10 位候选」），
 *  那是我方默认值、不是平台数据；所以这里查的是「取数结果的字段与数值」，
 *  不是「返回体里不许有数字」。 */
const BIZ_KEYS = ['候选红人', '命中总数', '频道编号', '订阅数', '中位播放', '播放量', '互动率',
  '品牌名', '品牌清单', '达人列表', '闸账本']
const BIZ_TEXT = /[$¥€]|USD|RMB|人民币|(订阅数|粉丝数|播放量|互动率|中位播放|命中总数|报价|预算|金额)\s*[:：]\s*[$¥€]?\d/
const allText = [out, outExplicit, outFull].map(J).join('\n')
const badKeys = BIZ_KEYS.filter((k) => allText.includes(k))
check('⑥不取数（返回体层）：不含任何一次取数的结果字段（品牌名／红人数／金额／播放量…）',
  badKeys.length === 0 && !BIZ_TEXT.test(allText),
  badKeys.length ? `命中键：${badKeys.join('、')}`
    : (BIZ_TEXT.test(allText) ? `命中数值：${String(allText.match(BIZ_TEXT)).slice(0, 40)}` : `业务数据键 0 命中、金额类数值 0 命中｜${allText.length} 字节`))
check('⑥返回体层：只有清单，没有「候选／候选人 / 结果列表」这类取数产物',
  (out.data && !('候选红人' in out.data) && !('结果' in out.data) && !('data' in out.data)) === true,
  `data.keys=${J(Object.keys(d))}`)
check('⑥不取数：命令标识写明是 clarify（不是任何取数子命令）',
  out.command === 'clarify' && !/roster|brands|search/i.test(String(out.command)),
  `command=${out.command}`)

/* ═══════════════ ⑦ 纯函数：幂等、无时钟 ═══════════════ */
const out2 = await call({ need: AMBIGUOUS })
check('⑦纯函数：同入参两次调用逐字节一致（不看时钟、不用随机）', sha(out) === sha(out2),
  `${sha(out).slice(0, 12)} vs ${sha(out2).slice(0, 12)}`)
const planA = clarifyPlan(AMBIGUOUS)
const planB = clarifyPlan(AMBIGUOUS, 'kol_search')
const blocks = (p) => J({ 缺项: p['缺项'], 优先补: p['优先补'], 口径类: p['口径类'] })
check('⑦纯函数（直接调 clarifyPlan）：自动判出的场景与显式传 topic 得到同一份清单',
  blocks(planA) === blocks(planB) && planA['场景'] === planB['场景'],
  `${sha(blocks(planA)).slice(0, 12)} vs ${sha(blocks(planB)).slice(0, 12)}｜场景=${planA['场景']}`)

/* ═══════════════ ⑧ 三个场景都能出清单 ═══════════════ */
for (const topic of CLARIFY_TOPICS) {
  const o = await call({ need: BY_TOPIC[topic], topic })
  const dd = (o && o.data) || {}
  check(`⑧场景 ${topic}：清单有效（缺项 1–${CLARIFY_MAX_ITEMS} 项／优先补 3 项／口径类非空）`,
    o.ok === true
    && (dd['缺项'] || []).length > 0 && (dd['缺项'] || []).length <= CLARIFY_MAX_ITEMS
    && (dd['优先补'] || []).length === CLARIFY_TOP_N
    && (dd['口径类'] || []).length > 0
    && typeof dd['下一步'] === 'string' && dd['下一步'].includes('默认口径'),
    `${topic}: 缺项=${(dd['缺项'] || []).length}｜优先补=${(dd['优先补'] || []).length}｜口径类=${(dd['口径类'] || []).length}`)
}
check('⑧场景归一：未知 topic 不报错，按通用清单走',
  clarifyTopicOf('no_such_topic') === 'generic' && clarifyTopicOf(undefined) === 'generic'
  && clarifyTopicOf('KOL_SEARCH') === 'kol_search',
  `${clarifyTopicOf('no_such_topic')}／${clarifyTopicOf(undefined)}／${clarifyTopicOf('KOL_SEARCH')}`)
check('⑧场景自动判断：红人 → 找红人；名单合并去重 → 名单处理；品牌建档 → 品牌建档',
  inferTopic('帮我找一批测评红人') === 'kol_search'
  && inferTopic('把这两份红人名单合并去重') === 'list_ops'
  && inferTopic('帮我建一个品牌库') === 'brand_setup'
  && inferTopic('看看今天的数据') === 'generic',
  `${inferTopic('帮我找一批测评红人')}／${inferTopic('把这两份红人名单合并去重')}／${inferTopic('帮我建一个品牌库')}／${inferTopic('看看今天的数据')}`)

/* ═══════════════ ⑨ need 必填与用法闸 ═══════════════ */
const empty = await call({ need: '   ' })
check('⑨空 need：ok:false / exitCode 2 / kind=usage（不硬编一份空洞清单）',
  empty.ok === false && empty.exitCode === 2 && empty.error && empty.error.kind === 'usage'
  && !('data' in empty),
  `ok=${empty.ok}｜kind=${empty.error && empty.error.kind}`)
let thrown = null
try { await call({}) } catch (e) { thrown = String(e && e.message) }
check('⑨缺 need：被参数契约直接挡住（宿主侧就报错，进不到业务逻辑）',
  thrown !== null && /need/.test(thrown), thrown ? thrown.slice(0, 90) : '（未抛错）')

/* ── 合计 ─────────────────────────────────────────────────── */
console.log('')
console.log(`合计：PASS ${pass} / FAIL ${fail}`)
if (fail) {
  console.log('失败项：')
  for (const f of failures) console.log('  · ' + f)
  process.exit(1)
}
process.exit(0)
