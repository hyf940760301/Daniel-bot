/**
 * 集成测试 · P1 只读能力入口（真 CLI 子进程 ＋ 假数据源，不联网、不写真实落点）
 *
 * 被测的 5 条命令（审计报告点名的"有路由、Bot 调不到"）：
 *   · `mentions chart`        → brandMentions.getChartData
 *   · `mentions top-channels` → brandMentions.getTopChannels
 *   · `mentions evidence`     → brandMentions.getVideoEvidence
 *   · `mentions export`       → brandMentions.exportMentions（非 batch GET）
 *   · `search enrich`         → discovery.enrichChannels / discovery.enrichEmails（只读通道）
 *
 * 为什么用"真 CLI ＋ 假客户端"而不是直接调 Python 函数：要证明的是**命令契约**——
 * 参数怎么给、缺参怎么报、调了哪条路由、返回是不是业务字段、以及"只读命令一次 mutate 都没发"。
 * 只测函数会把 schema／argparse／路由分发／读信封全绕过去。
 *
 * 跑法：node --test daniel-bot/packages/0.11.0/tests/p1-read-commands.test.mjs
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const HERE = dirname(fileURLToPath(import.meta.url))
const PKG = join(HERE, '..')
const CLI = join(PKG, 'vendor', 'data', 'daniel-cli', 'bin', 'daniel')
const KOL = join(PKG, 'vendor', '.kol-tools')
const PY = process.env.PYTHON || 'python3'

/** 每个用例一份独立世界：工具目录（假客户端 ＋ 真实落点/路径/仪器）、home、调用日志。 */
function makeWorld(world = {}) {
  const root = mkdtempSync(join(tmpdir(), 'daniel-p1read-'))
  const tools = join(root, 'tools')
  mkdirSync(tools, { recursive: true })
  cpSync(join(HERE, 'fixtures', 'cli-stub', 'daniel_client.py'), join(tools, 'daniel_client.py'))
  for (const name of ['daniel_paths.py', 'daniel_io.py', 'daniel_mentions.py', 'daniel_search.py']) {
    cpSync(join(KOL, name), join(tools, name))
  }
  const home = join(root, 'home')
  mkdirSync(home, { recursive: true })
  const worldPath = join(root, 'world.json')
  const callsPath = join(root, 'calls.jsonl')
  writeFileSync(worldPath, JSON.stringify(world, null, 1))
  const fixture = join(root, 'auth-fixture.json')
  writeFileSync(fixture, JSON.stringify({
    systemRole: 'admin', userStatus: 'active',
    workspace: { id: 90002, name: 'Test WS', planTier: 'pro', status: 'active',
      maxBrands: -1, maxSearchesPerMonth: -1 },
  }))
  const env = {
    ...process.env,
    DANIEL_CLI_TOOLS: tools,
    DANIEL_HOME: home,
    DANIEL_CLI_AUTH_FIXTURE: fixture,
    FAKE_WORLD: worldPath,
    FAKE_CALLS: callsPath,
    PYTHONPYCACHEPREFIX: join(root, 'pycache'),
  }
  return { root, home, worldPath, callsPath, env }
}

function runCli(env, args) {
  const r = spawnSync(PY, [CLI, ...args, '--json'], { env, encoding: 'utf8', timeout: 120000 })
  const out = String(r.stdout || '').trim()
  let doc = null
  try { doc = JSON.parse(out) } catch { /* 保留原文供断言 */ }
  return { code: r.status, stdout: out, stderr: String(r.stderr || ''), doc }
}

function runHelp(env, args) {
  const r = spawnSync(PY, [CLI, ...args, '--help'], { env, encoding: 'utf8', timeout: 60000 })
  return { code: r.status, text: `${String(r.stdout || '')}${String(r.stderr || '')}`.replace(/\s+/g, ' ') }
}

function calls(world) {
  if (!existsSync(world.callsPath)) return []
  return readFileSync(world.callsPath, 'utf8').trim().split('\n').filter(Boolean).map((l) => JSON.parse(l))
}

function routesOf(world, kind) {
  return calls(world).filter((c) => c.kind === kind).map((c) => c.route)
}

const JOB = 'job-1'

const CHART = {
  performanceDist: [{ performance: 'Strong Outperform', count: 3 },
    { performance: 'Average', count: 9 }],
  authDist: [{ label: 'Excellent', count: 4 }, { label: null, count: 1 }],
  videoTypeDist: [{ videoType: 'review', count: 5 }],
  promotionDist: [{ recommendation: 'likely_organic', count: 6 }],
  monthlyTrend: [{ month: '2026-01', count: 7, avgViews: 12000, avgComposite: 2.5 }],
}

const TOP_CHANNELS = [{
  channelId: 'UCabc0000000000000001', channelTitle: 'Tech Reviewer',
  subscriberCount: 120000, videoCount: 6, avgComposite: 2.75,
  avgViews: '542578.0000', totalViews: '3255468.0000', avgAuthenticity: '88.0',
  channelScore: 77.5, isRostered: true, highPerformanceCount: '2', relevanceLabel: 'confirmed',
}]

const EVIDENCE = {
  status: 'in_progress', matchingCount: 12, eligibleCount: 5, selectedCount: 2,
  analyzedCount: 1, remainingEligibleCount: 3, remainingAnalysisCount: 1,
  batchStarted: true, batches: 2,
  videos: [{ resultId: 4441506, videoTitle: 'Halliday vs Even Realities',
    progress: { stages: { sources: { status: 'done' } } } }],
}

const EXPORT_ROWS = [
  { channelName: 'Tech Reviewer', channelHandle: '@techreviewer',
    channelUrl: 'https://youtube.com/@techreviewer', videoTitle: 'Best AI glasses 2026',
    videoUrl: 'https://youtu.be/aaa', views: '120000', subscribers: '120000',
    compositeScore: '3.85', organicPerformance: 'Strong Outperform', relevance: 'confirmed',
    type: 'review', isOfficial: 'No', language: 'en', email: '' },
  { channelName: 'Gadget Lab', channelHandle: '@gadgetlab',
    channelUrl: 'https://youtube.com/@gadgetlab', videoTitle: 'AI glasses everyday carry',
    videoUrl: 'https://youtu.be/bbb', views: '80000', subscribers: '90000',
    compositeScore: '2.10', organicPerformance: 'Average', relevance: 'confirmed',
    type: 'unboxing', isOfficial: 'No', language: 'en', email: 'hi@example.com' },
]

const ENRICH = {
  UCaaa: { publicData: { title: 'Tech Reviewer', subscriberCount: 120000, country: 'US',
    topicCategories: ['Technology'], businessEmail: 'hi@example.com' } },
  UCbbb: { publicData: { title: 'Quiet Channel' } },
}

// ── ① 帮助文案：给什么、怎么给 ──────────────────────────────────────────────
test('① 五条命令的 --help：写清「给什么、怎么给」，并带可照抄的示例', () => {
  const w = makeWorld()

  const chart = runHelp(w.env, ['mentions', 'chart'])
  assert.equal(chart.code, 0, chart.text)
  for (const needle of ['--brand', '--job', 'daniel mentions jobs --brand', '任务编号',
    'daniel mentions chart --brand 3690002 --job']) {
    assert.ok(chart.text.includes(needle), `chart 帮助缺：${needle}`)
  }

  const top = runHelp(w.env, ['mentions', 'top-channels'])
  assert.equal(top.code, 0, top.text)
  for (const needle of ['--limit', '5–50', '--relevance-filter', '--job',
    'daniel mentions top-channels --brand 3690002 --job']) {
    assert.ok(top.text.includes(needle), `top-channels 帮助缺：${needle}`)
  }

  const evidence = runHelp(w.env, ['mentions', 'evidence'])
  assert.equal(evidence.code, 0, evidence.text)
  for (const needle of ['--job', '不需要视频编号', 'daniel mentions evidence --brand 3690002 --job']) {
    assert.ok(evidence.text.includes(needle), `evidence 帮助缺：${needle}`)
  }

  const exp = runHelp(w.env, ['mentions', 'export'])
  assert.equal(exp.code, 0, exp.text)
  for (const needle of ['--exclude-official', '--language', '--relevance-filter',
    'daniel mentions export --brand 3690002 --job']) {
    assert.ok(exp.text.includes(needle), `export 帮助缺：${needle}`)
  }

  const enrich = runHelp(w.env, ['search', 'enrich'])
  assert.equal(enrich.code, 0, enrich.text)
  for (const needle of ['--channel-ids', '--items-file', '--emails', '只读',
    '每批 ≤100', '每批 ≤50', 'daniel search enrich --channel-ids']) {
    assert.ok(enrich.text.includes(needle), `enrich 帮助缺：${needle}`)
  }
})

// ── ② 缺参：报错文案要含「该怎么给」 ─────────────────────────────────────────
test('② 缺参报错带可照抄示例（mentions 四条）', () => {
  const w = makeWorld()
  for (const cmd of ['chart', 'top-channels', 'evidence', 'export']) {
    const r = runCli(w.env, ['mentions', cmd])
    assert.equal(r.code, 2, `${cmd} 缺参应退出 2，实际 ${r.code}：${r.stderr}`)
    assert.equal(r.doc.ok, false)
    assert.equal(r.doc.error.kind, 'usage')
    assert.match(r.doc.error.hint, new RegExp(`daniel mentions ${cmd} --brand 3690002`),
      `${cmd} 的 hint 必须给出可照抄的写法：${r.doc.error.hint}`)
    assert.match(r.stderr, /--brand/, 'argparse 的用法行仍要列出缺哪个参数')
  }
})

test('②b search enrich：缺输入／两个都给／文件不存在，三种都报「怎么给」', () => {
  const w = makeWorld()

  const none = runCli(w.env, ['search', 'enrich'])
  assert.equal(none.code, 2, none.stderr)
  assert.match(none.doc.error.message, /缺少输入/)
  assert.match(none.doc.error.hint, /--channel-ids UC/)
  assert.match(none.doc.error.hint, /--items-file/)
  assert.match(none.doc.error.hint, /--emails/)

  const both = runCli(w.env, ['search', 'enrich', '--channel-ids', 'UCaaa', '--items-file', './x.json'])
  assert.equal(both.code, 2)
  assert.match(both.doc.error.message, /只能给一个/)
  assert.match(both.doc.error.hint, /--items-file/)

  const missing = runCli(w.env, ['search', 'enrich', '--items-file', join(w.root, 'nope.json')])
  assert.equal(missing.code, 2)
  assert.match(missing.doc.error.message, /文件不存在/)
  assert.match(missing.doc.error.hint, /--channel-ids/)

  // 三种拒绝都不许发请求
  assert.equal(calls(w).length, 0, '被拒的调用不得发出任何请求')
})

// ── ③ mentions 四视图：路由正确、返回是业务字段 ───────────────────────────
test('③ mentions chart：走 getChartData，返回五块分布（业务字段）', () => {
  const w = makeWorld({ jobs: [{ jobId: JOB, status: 'done' }], chart: CHART })
  const r = runCli(w.env, ['mentions', 'chart', '--brand', '3690002', '--job', JOB])
  assert.equal(r.code, 0, r.stderr)
  assert.equal(r.doc.readOnly, true)
  const data = r.doc.data
  assert.equal(data['任务编号'], JOB)
  assert.deepEqual(data['表现分布'], [{ 表现档位: 'Strong Outperform', 条数: 3 },
    { 表现档位: 'Average', 条数: 9 }])
  assert.equal(data['真实性分布'].length, 2, 'label 为 null 的行也要保留')
  assert.equal(data['视频类型分布'][0]['视频类型'], 'review')
  assert.equal(data['推广建议分布'][0]['推广建议'], 'likely_organic')
  assert.equal(data['月度趋势'][0]['平均播放'], 12000)
  assert.equal(data['分布块数'], 5)
  // 内部字段名不得直接出现在 data 顶层
  assert.equal(data.performanceDist, undefined)

  const sent = calls(w).filter((c) => c.route === 'brandMentions.getChartData')
  assert.equal(sent.length, 1, '必须真的调到 getChartData')
  assert.deepEqual(sent[0].payload, { jobId: JOB })
  assert.equal(calls(w).filter((c) => c.kind === 'mutate').length, 0)
})

test('③b mentions top-channels：limit 校验、走 getTopChannels、数字字符串还原成数字', () => {
  const w = makeWorld({ jobs: [{ jobId: JOB, status: 'done' }], topChannels: TOP_CHANNELS })
  const r = runCli(w.env, ['mentions', 'top-channels', '--brand', '3690002', '--job', JOB,
    '--limit', '25'])
  assert.equal(r.code, 0, r.stderr)
  const data = r.doc.data
  assert.equal(data['频道数'], 1)
  assert.equal(data['本次上限'], 25)
  assert.deepEqual(data['可能还有更多'], '否（返回条数没到上限）')
  const row = data['频道'][0]
  assert.equal(row['频道编号'], 'UCabc0000000000000001')
  assert.equal(row['订阅数'], 120000)
  assert.equal(row['平均播放'], 542578, '服务端给的字符串数字要还原成数字')
  assert.equal(row['强表现视频数'], 2)
  assert.equal(row['相关性'], 'confirmed')

  const sent = calls(w).filter((c) => c.route === 'brandMentions.getTopChannels')
  assert.equal(sent.length, 1)
  assert.deepEqual(sent[0].payload, { jobId: JOB, limit: 25, relevanceFilter: 'all' })

  // 越界：本地拦、不发包（实测 1／3／100 都被服务端 400 拒）
  const w2 = makeWorld({ jobs: [{ jobId: JOB, status: 'done' }], topChannels: TOP_CHANNELS })
  for (const bad of ['3', '100']) {
    const r2 = runCli(w2.env, ['mentions', 'top-channels', '--brand', '3690002', '--job', JOB,
      '--limit', bad])
    assert.equal(r2.code, 2, `--limit ${bad} 应本地拦下`)
    assert.match(r2.doc.error.message, /最少 5、最多 50/)
    assert.match(r2.doc.error.hint, /本次没有发出任何请求/)
  }
  assert.equal(calls(w2).filter((c) => c.route === 'brandMentions.getTopChannels').length, 0)
})

test('③c mentions evidence：走 getVideoEvidence（jobId＋brandId），视频清单业务化', () => {
  const w = makeWorld({ jobs: [{ jobId: JOB, status: 'done' }], evidence: EVIDENCE })
  const r = runCli(w.env, ['mentions', 'evidence', '--brand', '3690002', '--job', JOB])
  assert.equal(r.code, 0, r.stderr)
  const data = r.doc.data
  assert.equal(data['状态'], 'in_progress')
  assert.equal(data['匹配视频数'], 12)
  assert.equal(data['入选视频数'], 2)
  assert.equal(data['批次数'], 2)
  assert.equal(data['视频数'], 1)
  assert.equal(data['视频'][0]['视频编号'], 4441506)
  assert.equal(data['视频'][0]['视频标题'], 'Halliday vs Even Realities')

  const sent = calls(w).filter((c) => c.route === 'brandMentions.getVideoEvidence')
  assert.equal(sent.length, 1)
  assert.deepEqual(sent[0].payload, { jobId: JOB, brandId: 3690002 })
})

test('③d mentions export：走非 batch 的 exportMentions，14 列翻成业务字段', () => {
  const w = makeWorld({ jobs: [{ jobId: JOB, status: 'done' }], export: EXPORT_ROWS })
  const r = runCli(w.env, ['mentions', 'export', '--brand', '3690002', '--job', JOB,
    '--relevance-filter', 'all', '--exclude-official', '--language', 'en'])
  assert.equal(r.code, 0, r.stderr)
  const data = r.doc.data
  assert.equal(data['条数'], 2)
  assert.equal(data['邮箱缺失条数'], 1)
  assert.equal(data['提及'][0]['频道账号'], '@techreviewer')
  assert.equal(data['提及'][0]['综合分'], 3.85)
  assert.equal(data['提及'][1]['邮箱'], 'hi@example.com')

  const sent = calls(w).filter((c) => c.route === 'brandMentions.exportMentions')
  assert.equal(sent.length, 1, '必须真的调到 exportMentions')
  assert.equal(sent[0].kind, 'query_plain', '导出走非 batch GET 通路')
  assert.deepEqual(sent[0].payload,
    { jobId: JOB, relevanceFilter: 'all', excludeOfficial: true, languageFilter: 'en' })
  assert.equal(calls(w).filter((c) => c.kind === 'mutate').length, 0)
})

// ── ④ search enrich：只走读路由、绝不发 mutate ────────────────────────────
test('④ search enrich：按编号补齐，只发 read_post，一次 mutate 都没有', () => {
  const w = makeWorld({ enrich: ENRICH })
  const r = runCli(w.env, ['search', 'enrich', '--channel-ids', 'UCaaa,UCbbb,UCccc'])
  assert.equal(r.code, 0, r.stderr)
  assert.equal(r.doc.readOnly, true)
  const data = r.doc.data
  assert.equal(data['频道数'], 3)
  assert.equal(data['补齐情况']['订阅数']['补到'], 1)
  assert.equal(data['补齐情况']['订阅数']['未补到'], 2)
  assert.equal(data['补齐情况']['国家']['补到'], 1)
  assert.equal(data['补齐情况']['标签']['补到'], 1)
  assert.deepEqual(data['频道'][0]['标签'], ['Technology'])
  // 没给 --emails 就不走邮箱链路：逐条与统计里都不出现「商务邮箱」（服务端顺手带回的也不展示，
  // 免得读者以为这次补过邮箱）
  assert.equal(data['频道'][0]['商务邮箱'], undefined)
  assert.equal(data['补齐情况']['商务邮箱'], undefined, '没给 --emails 就不该声称补过邮箱')
  assert.ok(data['说明'].some((x) => x.includes('加 --emails')), '要写明怎么补邮箱')
  const missing = data['没补到的']['明细'].find((x) => x['频道编号'] === 'UCccc')
  assert.ok(missing, '服务端没返回的编号必须出现在「没补到的」里')
  assert.ok(missing['缺什么'].includes('订阅数'))
  assert.ok(data['频道链路没返回的编号'].includes('UCccc'))

  // 铁律：只读命令不许发 mutate
  assert.equal(calls(w).filter((c) => c.kind === 'mutate').length, 0, '只读命令不得发写请求')
  assert.deepEqual(routesOf(w, 'read_post'), ['discovery.enrichChannels'])
  assert.deepEqual(routesOf(w, 'query'), [], '不经过任何 query 路由')
})

test('④b search enrich --emails：加走 enrichEmails，邮箱字段才出现在补齐情况里', () => {
  const w = makeWorld({ enrich: ENRICH })
  const r = runCli(w.env, ['search', 'enrich', '--channel-ids', 'UCaaa,UCbbb', '--emails'])
  assert.equal(r.code, 0, r.stderr)
  const data = r.doc.data
  assert.equal(data['补齐情况']['商务邮箱']['补到'], 1)
  assert.equal(data['补齐情况']['商务邮箱']['未补到'], 1)
  assert.deepEqual(routesOf(w, 'read_post'),
    ['discovery.enrichChannels', 'discovery.enrichEmails'])
  assert.equal(calls(w).filter((c) => c.kind === 'mutate').length, 0)
})

test('④c search enrich：批量上限分开拆（频道 100 / 邮箱 50），不得互相类推', () => {
  const w = makeWorld({ enrich: {} })
  const ids = Array.from({ length: 101 }, (_, i) => `UC${String(i).padStart(4, '0')}`)
  const r = runCli(w.env, ['search', 'enrich', '--channel-ids', ids.join(',')])
  assert.equal(r.code, 0, r.stderr)
  const chBatches = calls(w).filter((c) => c.kind === 'read_post'
    && c.route === 'discovery.enrichChannels').map((c) => c.payload.channelIds.length)
  assert.deepEqual(chBatches, [100, 1])
  assert.equal(r.doc.data['批次']['频道请求次数'], 2)

  const w2 = makeWorld({ enrich: ENRICH })
  const ids2 = Array.from({ length: 51 }, (_, i) => `UC${String(i).padStart(4, '0')}`)
  const r2 = runCli(w2.env, ['search', 'enrich', '--channel-ids', ids2.join(','), '--emails'])
  assert.equal(r2.code, 0, r2.stderr)
  const mailBatches = calls(w2).filter((c) => c.kind === 'read_post'
    && c.route === 'discovery.enrichEmails').map((c) => c.payload.channelIds.length)
  assert.deepEqual(mailBatches, [50, 1], '邮箱链路每批 ≤50（51 会被服务端 400）')
  assert.equal(calls(w2).filter((c) => c.kind === 'mutate').length, 0)
})

test('④d search enrich --items-file：认任务返回体形状，且只读不改文件', () => {
  const w = makeWorld({ enrich: ENRICH })
  const file = join(w.root, 'kol-items.json')
  const body = JSON.stringify({ results: [{ channelId: 'UCaaa' }, { channelId: 'UCbbb' }, { channelId: 'UCaaa' }] })
  writeFileSync(file, body)
  const r = runCli(w.env, ['search', 'enrich', '--items-file', file])
  assert.equal(r.code, 0, r.stderr)
  assert.equal(r.doc.data['频道数'], 2, '同一编号只富化一次')
  assert.equal(r.doc.data['去重条数'], 1)
  assert.equal(readFileSync(file, 'utf8'), body, '只读命令不得回写输入文件')
  assert.equal(calls(w).filter((c) => c.kind === 'mutate').length, 0)
})
