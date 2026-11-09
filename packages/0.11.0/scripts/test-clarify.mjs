/**
 * `daniel_clarify`（追问闸）自检 —— 不需要 DSH 宿主。
 *
 * 2026-10-31 起（业务判断下沉 · M3）：判断逻辑已搬到 CLI（`daniel clarify plan|ask`），
 * 插件 `lib/clarify.js` 只剩「参数搬运 + 结果透传」。因此本自检分两层：
 *   · ①–⑤、⑦–⑨：**行为层**——调工具，看清单结构/文案/上限/场景/用法闸（判据不变）；
 *   · ⑥：**等价断言 A1–A6**——旧版查"JS 源码里有没有 spawn/读盘/联网"，现在改成
 *     "CLI 命令是不是真的不取数、不联网、不读账号、只读两个本地文件、幂等、不起子进程"。
 *     （旧断言在下沉后必然误报：插件就是要起子进程调 CLI。）
 *
 * 用法：node scripts/test-clarify.mjs
 *   · 默认用包内 vendor 的 CLI；切插件/未 vendor 时用 `DANIEL_BIN=<canonical>/bin/daniel` 覆盖。
 * 退出码：0 = FAIL 0；1 = 有 FAIL。
 */
import { readFileSync, mkdtempSync, rmSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { dirname, join } from 'node:path'
import { tmpdir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import { apply } from '../lib/index.js'
import { CLARIFY_MAX_ITEMS, CLARIFY_TOP_N, CLARIFY_TOPICS } from '../lib/clarify.js'

const HERE = dirname(fileURLToPath(import.meta.url))
const CLI_BIN = process.env.DANIEL_BIN
  || join(HERE, '..', 'vendor', 'data', 'daniel-cli', 'bin', 'daniel')
const CLI_PKG = dirname(dirname(CLI_BIN))

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
}

const call = (args) => clarify.execute(args, {})
const out = await call({ need: AMBIGUOUS })
const d = (out && out.data) || {}
const outExplicit = await call({ need: EXPLICIT })
const dExplicit = (outExplicit && outExplicit.data) || {}

/* ═══════════════ ① 注册与参数契约 ═══════════════ */
check('①注册：工具总数 19（含 daniel_screen_ask 与 4 个检索通道工具），daniel_clarify 在列', reg.length === 19 && Boolean(clarify) && Boolean(screenAsk), `注册=${reg.length}`)
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
check('②缺项：每项都有「项名＋为什么问＋不答的默认值」且都非空、项名不重复',
  (d['缺项'] || []).every((it) => ['项名', '为什么问', '不答的默认值'].every(
    (k) => typeof it[k] === 'string' && it[k].trim().length > 0))
  && new Set((d['缺项'] || []).map((it) => it['项名'])).size === (d['缺项'] || []).length,
  J((d['缺项'] || [])[0]))
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
check('④口径类：只含「项名＋影响」两字段，且与缺项零重叠（口径问题不混进可答参数）',
  cal.length > 0 && cal.every((c) => J(Object.keys(c).sort()) === J(['影响', '项名']))
  && cal.every((c) => !(d['缺项'] || []).some((it) => it['项名'] === c['项名'])),
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
  && /不需要再问你/.test(String(dFull['下一步'])),
  `${dFull['结论']}｜下一步=${String(dFull['下一步']).slice(0, 24)}`)
check('⑤全部说清：仍然给出口径类（参数齐了也不等于口径齐了）',
  (dFull['口径类'] || []).length > 0, `${(dFull['口径类'] || []).length} 条`)

/* ═══════════════ ⑥ 等价断言 A1–A6（替代旧的 8 类 JS 源码禁项）═══════════════ */
const pyOf = (rel) => readFileSync(join(CLI_PKG, rel), 'utf8')
const CLARIFY_PY_TEXT = [pyOf('daniel_cli/clarify.py'), pyOf('daniel_cli/commands/mod_clarify.py')].join('\n')

/** A1 不取数：返回体里没有任何一次取数的结果字段（沿用旧判据，不重写） */
const BIZ_KEYS = ['候选红人', '命中总数', '频道编号', '订阅数', '中位播放', '播放量', '互动率',
  '品牌名', '品牌清单', '达人列表', '闸账本']
const BIZ_TEXT = /[$¥€]|USD|RMB|人民币|(订阅数|粉丝数|播放量|互动率|中位播放|命中总数|报价|预算|金额)\s*[:：]\s*[$¥€]?\d/
const allText = [out, outExplicit, outFull].map(J).join('\n')
const badKeys = BIZ_KEYS.filter((k) => allText.includes(k))
check('⑥A1 不取数（返回体）：不含品牌名／红人数／金额／播放量这类取数结果',
  badKeys.length === 0 && !BIZ_TEXT.test(allText),
  badKeys.length ? `命中键：${badKeys.join('、')}` : `业务数据键 0 命中、金额类数值 0 命中｜${allText.length} 字节`)

/** A2 离线：CLI 的 clarify 两个模块不出现网络调用 */
const NET = /urllib|requests|socket|http\.client|aiohttp|httpx/
check('⑥A2 离线（源码）：CLI clarify 模块无网络调用（urllib/requests/socket/http.client）',
  !NET.test(CLARIFY_PY_TEXT), NET.test(CLARIFY_PY_TEXT) ? '命中网络库' : '两个模块 0 命中')

/** A3 纯本地：不给可用 DANIEL_HOME（指向空目录）也能跑通 */
const emptyHome = mkdtempSync(join(tmpdir(), 'clarify-home-'))
let cliRun = { status: null, json: null }
try {
  const p = spawnSync(process.env.PYTHON || 'python3',
    [CLI_BIN, 'clarify', 'plan', '--need', AMBIGUOUS, '--json'],
    { env: { ...process.env, DANIEL_HOME: emptyHome, DANIEL_NO_OPEN: '1' }, encoding: 'utf8', timeout: 60000 })
  cliRun.status = p.status
  try { cliRun.json = JSON.parse(p.stdout) } catch { cliRun.json = null }
} finally {
  rmSync(emptyHome, { recursive: true, force: true })
}
check('⑥A3 纯本地：无可用 DANIEL_HOME（空目录）时 CLI 仍能跑出完整清单',
  cliRun.status === 0 && cliRun.json && cliRun.json.ok === true && cliRun.json.data
  && Array.isArray(cliRun.json.data['缺项']),
  `exit=${cliRun.status}｜ok=${Boolean(cliRun.json && cliRun.json.ok)}`)

/** A4 只读两个本地文件：不写盘、不读账号 */
const WRITE_API = /json\.dump\(|os\.remove|os\.unlink|shutil\.|open\([^)]*['"][wa]b?['"]/
const ACCOUNT_MOD = /(^|\n)\s*(from|import)\s+.*\b(accounts|authgate|permissions|connect)\b/
check('⑥A4 只读本地：CLI clarify 模块不写盘、不读账号（只碰随包登记表与触发词）',
  !WRITE_API.test(CLARIFY_PY_TEXT) && !ACCOUNT_MOD.test(CLARIFY_PY_TEXT)
  && /clarify_triggers\.json/.test(CLARIFY_PY_TEXT),
  WRITE_API.test(CLARIFY_PY_TEXT) ? '命中写盘 API'
    : (ACCOUNT_MOD.test(CLARIFY_PY_TEXT) ? '命中账号模块' : '无写盘、无账号依赖，引用 clarify_triggers.json'))

/** A5 幂等：同入参两次调用逐字节一致 */
const out2 = await call({ need: AMBIGUOUS })
check('⑥A5 幂等：同入参两次调用逐字节一致（不看时钟、不用随机）', sha(out) === sha(out2),
  `${sha(out).slice(0, 12)} vs ${sha(out2).slice(0, 12)}`)

/** A6 不起子进程：CLI clarify 模块内部不得再 spawn（避免"命令套命令"） */
const SUBPROC = /\bsubprocess\b|\bos\.system\b|\bos\.popen\b|\bpty\.spawn\b/
check('⑥A6 不起子进程（源码）：CLI clarify 模块无 subprocess/os.system/os.popen',
  !SUBPROC.test(CLARIFY_PY_TEXT), SUBPROC.test(CLARIFY_PY_TEXT) ? '命中子进程 API' : '0 命中')

/* ═══════════════ ⑦ 场景显式指定与自动判断一致 ═══════════════ */
const autoOut = await call({ need: AMBIGUOUS })
const explicitK = await call({ need: AMBIGUOUS, topic: 'kol_search' })
const blocks = (o) => J({ 缺项: o.data['缺项'], 优先补: o.data['优先补'], 口径类: o.data['口径类'] })
check('⑦场景：显式传 topic 与按原话自动判断得到同一份清单（只差「场景依据」一句）',
  blocks(autoOut) === blocks(explicitK) && autoOut.data['场景'] === explicitK.data['场景'],
  `${sha(blocks(autoOut)).slice(0, 12)} vs ${sha(blocks(explicitK)).slice(0, 12)}｜场景=${autoOut.data['场景']}`)

/* ═══════════════ ⑧ 三个场景＋自动判断 ═══════════════ */
const sceneRows = []
for (const topic of CLARIFY_TOPICS) {
  const o = await call({ need: BY_TOPIC[topic], topic })
  const dd = (o && o.data) || {}
  sceneRows.push([topic, o.ok === true
    && (dd['缺项'] || []).length > 0 && (dd['缺项'] || []).length <= CLARIFY_MAX_ITEMS
    && (dd['优先补'] || []).length === CLARIFY_TOP_N
    && (dd['口径类'] || []).length > 0
    && typeof dd['下一步'] === 'string' && dd['下一步'].includes('默认口径'),
  `缺项=${(dd['缺项'] || []).length}｜优先补=${(dd['优先补'] || []).length}`])
}
check('⑧场景：三个场景都能出有效清单（缺项 1–8／优先补 3／口径类非空）',
  sceneRows.every(([, ok]) => ok), sceneRows.map(([t, ok, s]) => `${t}:${ok ? 'ok' : 'FAIL'}(${s})`).join(' ｜ '))

const autoJudge = [
  ['帮我找一批测评红人', '找红人／建名单'],
  ['把这两份红人名单合并去重', '名单处理（合并／去重／比对）'],
  ['帮我建一个品牌库', '品牌建档／品牌清单'],
  ['看看今天的数据', '通用（未指定场景）'],
]
const judgeGot = []
for (const [need, want] of autoJudge) judgeGot.push((await call({ need })).data['场景'] === want)
check('⑧场景自动判断：红人／合并去重／品牌建档／无关需求各自落到正确场景',
  judgeGot.every(Boolean), `四例：${judgeGot.filter(Boolean).length}/4`)

const brandFirst = await call({ need: '帮我为 Halliday 品牌找一批测评红人' })
check('⑧已知偏差（bug-compatible）：提到「品牌」的找红人需求仍判成品牌建档（TICKET-282 另案）',
  brandFirst.data['场景'] === '品牌建档／品牌清单', `场景=${brandFirst.data['场景']}`)

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

/* ═══════════════ ⑩ 选择面与命令标识 ═══════════════ */
const guide = await screenAsk.execute({ need: '帮我找 20 个做智能眼镜测评的红人' }, {})
const dg = (guide && guide.data) || {}
check('⑩选择面：首次调用出五类方向（组名/举例/默认），且不追问',
  guide.ok === true && dg['模式'] === '选择面'
  && Array.isArray(dg['选择面']) && dg['选择面'].length === 5
  && dg['选择面'].every((g) => g['方向'] && g['举例'] && g['不给就按']),
  `模式=${dg['模式']}｜组数=${(dg['选择面'] || []).length}`)
const follow = await screenAsk.execute({ need: '帮我找 20 个做智能眼镜测评的红人', reply: '找点做测评的', round: 1 }, {})
check('⑩追问：回答后按覆盖度追问（轮次 1，追问 3 项）',
  follow.ok === true && follow.data['模式'] === '动态追问' && follow.data['轮次'] === 1
  && (follow.data['追问'] || []).length === 3,
  `模式=${follow.data['模式']}｜追问=${(follow.data['追问'] || []).length}`)
check('⑩命令标识：两个工具各自写死 command（不透传 CLI 的 clarify.plan）',
  out.command === 'clarify' && guide.command === 'screen_ask',
  `clarify=${out.command}｜screen_ask=${guide.command}`)

/* ── 合计 ─────────────────────────────────────────────────── */
console.log('')
console.log(`合计：PASS ${pass} / FAIL ${fail}`)
if (fail) {
  console.log('失败项：')
  for (const f of failures) console.log('  · ' + f)
  process.exit(1)
}
process.exit(0)
