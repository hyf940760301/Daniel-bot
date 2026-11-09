/**
 * 集成测试 · `daniel lists add-items`（真 CLI 子进程 ＋ 假数据源，不联网、不写真实落点）
 *
 * 为什么用"真 CLI ＋ 假客户端"而不是直接调 Python 函数：这条命令的价值在**门禁链**
 * （权限 → 干跑 → 确认 → 逐批写 → 回读 → 审计）。只测函数会把门禁链与审计绕过去。
 * 假客户端只替换数据源（`.kol-tools/daniel_client.py`），CLI 本体、schema、门禁、审计
 * 全部走真实实现。
 *
 * 覆盖：
 *   ① 干跑不出发包（没有 `lists.batchAddItems` 写请求）；
 *   ② 文件方式：8 个字段完整保留；
 *   ③ ID 方式：详情回查补齐，补不到的标「未取到」且不编；
 *   ④ 超过 100 人自动拆批；
 *   ⑤ 回读条数不一致 → 退出码 1 且写明差多少；
 *   ⑥ 两个来源都给／都不给 → 可操作的人话提示；
 *   ⑦ 审计：干跑一条（executed=false）＋ 真跑一条（executed=true，含回读）。
 *
 * 跑法：node --test daniel-bot/packages/0.11.0/tests/lists-add-items.test.mjs
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { cpSync, existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const HERE = dirname(fileURLToPath(import.meta.url))
const PKG = join(HERE, '..')
const CLI = join(PKG, 'vendor', 'data', 'daniel-cli', 'bin', 'daniel')
const KOL = join(PKG, 'vendor', '.kol-tools')
const PY = process.env.PYTHON || 'python3'

/** 每个用例一份独立世界：工具目录（假客户端 ＋ 真实落点/路径模块）、home、审计、调用日志。 */
function makeWorld({ lists = {}, details = {}, failDetails = [], mutateMode = 'normal' } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'daniel-additems-'))
  const tools = join(root, 'tools')
  mkdirSync(tools, { recursive: true })
  cpSync(join(HERE, 'fixtures', 'cli-stub', 'daniel_client.py'), join(tools, 'daniel_client.py'))
  for (const name of ['daniel_paths.py', 'daniel_io.py', 'daniel_search.py']) {
    cpSync(join(KOL, name), join(tools, name))
  }
  const home = join(root, 'home')
  mkdirSync(home, { recursive: true })
  const worldPath = join(root, 'world.json')
  const callsPath = join(root, 'calls.jsonl')
  writeFileSync(worldPath, JSON.stringify({ lists, details, failDetails, mutateMode }, null, 1))
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
  return { root, home, worldPath, callsPath, env, auditPath: join(home, 'logs', 'write-audit.jsonl') }
}

function runCli(env, args) {
  const r = spawnSync(PY, [CLI, ...args, '--json'], { env, encoding: 'utf8', timeout: 120000 })
  const out = String(r.stdout || '').trim()
  let doc = null
  try { doc = JSON.parse(out) } catch { /* 保留原文供断言 */ }
  return { code: r.status, signal: r.signal, stdout: out, stderr: String(r.stderr || ''), doc }
}

function calls(world) {
  if (!existsSync(world.callsPath)) return []
  return readFileSync(world.callsPath, 'utf8').trim().split('\n').filter(Boolean).map((l) => JSON.parse(l))
}

function writeItems(world, items) {
  const p = join(world.root, 'items.json')
  writeFileSync(p, JSON.stringify(items, null, 1))
  return p
}

function audit(world) {
  if (!existsSync(world.auditPath)) return []
  return readFileSync(world.auditPath, 'utf8').trim().split('\n').filter(Boolean).map((l) => JSON.parse(l))
}

const FULL = {
  channelId: 'UCfull0000000000000001', channelTitle: 'Full Channel', subscriberCount: 123456,
  country: 'us', tier: 3, cqiScore: 72.5, contactEmail: 'one@example.com', engagementRate: 3.2,
}

test('① --help：命令存在，且 --items-file／--channel-ids 的"给什么、怎么给"写在帮助里', () => {
  const w = makeWorld()
  const r = runCli(w.env, ['lists', 'add-items', '--help'])
  assert.equal(r.code, 0, r.stderr)
  // --help 不走 --json（argparse 原生帮助），所以直接断言文本
  const help = spawnSync(PY, [CLI, 'lists', 'add-items', '--help'], { env: w.env, encoding: 'utf8' })
  const text = String(help.stdout || '')
  const flat = text.replace(/\s+/g, ' ')     // argparse 会按终端宽度折行，先压成一行再断言
  assert.match(flat, /add-items/)
  assert.match(flat, /--items-file/)
  assert.match(flat, /最小可用.*channelId/)
  assert.match(flat, /常用三字段/)
  assert.match(flat, /--channel-ids 123456,234567/)
  assert.ok(flat.includes('只给编号时会逐个回查'), '缺少「只给编号时会逐个回查」的说明')
  assert.ok(flat.includes('补不到的留空并标「未取到」'), '缺少「未取到」口径的说明')
  assert.ok(flat.includes('（写操作）'), '帮助里必须写明这是写操作')
})

test('② 干跑：只出计划、不出发包；计划含 list-id／将加 N／跳过 M／预计批数／影响范围', () => {
  const w = makeWorld({
    lists: { 8310034: [{ channelId: 'UCexisting000000000001', channelTitle: 'Existing' }] },
  })
  const p = writeItems(w, [
    { channelId: 'UCnew1', channelTitle: 'New 1', subscriberCount: 10000 },
    { channelId: 'UCnew2', channelTitle: 'New 2', subscriberCount: 20000 },
    { channelId: 'UCexisting000000000001', channelTitle: 'Existing' },
    { channelId: 'UCnew1', channelTitle: 'Dup' },
  ])
  const r = runCli(w.env, ['lists', 'add-items', '--list-id', '8310034', '--items-file', p])
  assert.equal(r.code, 3, `干跑应退出 3，实际 ${r.code}：${r.stderr}`)
  assert.equal(r.doc.ok, false)
  assert.equal(r.doc.exitCode, 3)
  const plan = r.doc.data.plan
  assert.equal(plan.listId, 8310034)
  assert.equal(plan['将加人数'], 2)
  assert.equal(plan['跳过人数'], 2)
  assert.deepEqual(plan['跳过明细'], { 条目内重复: 1, 已在名单: 1, '超出 --limit': 0 })
  assert.equal(plan['预计批数'], 1)
  assert.match(plan.impact, /名单 8310034 现有 1 人/)
  assert.equal(r.doc.data.executed, false)
  assert.equal(r.doc.data.dryRun, true)
  // 关键：干跑没有写请求
  assert.equal(calls(w).filter((c) => c.kind === 'mutate').length, 0, '干跑不得发写请求')
})

test('③ 文件方式：8 个字段完整保留；写入后回读一致；干跑＋真跑各一条审计', () => {
  const w = makeWorld({ lists: { 8310034: [] } })
  const p = writeItems(w, [FULL])
  const dry = runCli(w.env, ['lists', 'add-items', '--list-id', '8310034', '--items-file', p])
  assert.equal(dry.code, 3)
  assert.deepEqual(dry.doc.data.plan['字段补齐情况'], {
    channelId: '1/1', channelTitle: '1/1', subscriberCount: '1/1', country: '1/1',
    tier: '1/1', cqiScore: '1/1', contactEmail: '1/1', engagementRate: '1/1',
  })
  const real = runCli(w.env, ['lists', 'add-items', '--list-id', '8310034', '--items-file', p, '--confirm'])
  assert.equal(real.code, 0, real.stderr)
  assert.equal(real.doc.data.readback.verified, true)
  assert.equal(real.doc.data.readback.detail.delta, 1)
  assert.equal(real.doc.data.detail['计划新增'], 1)
  assert.equal(real.doc.data.detail['实际新增'], 1)

  const sent = calls(w).filter((c) => c.kind === 'mutate' && c.route === 'lists.batchAddItems')
  assert.equal(sent.length, 1)
  const item = sent[0].payload.items[0]
  for (const key of ['channelId', 'channelTitle', 'subscriberCount', 'country', 'tier',
    'cqiScore', 'contactEmail', 'engagementRate']) {
    assert.ok(key in item, `写入条目缺字段：${key}`)
  }
  assert.equal(item.country, 'US', '国家代码统一大写')
  assert.equal(typeof item.tier, 'number', 'tier 必须是数字（不是档名）')

  // 审计：写入前（干跑）一条 + 写入后（真跑）一条
  const rows = audit(w)
  assert.equal(rows.length, 2, JSON.stringify(rows))
  assert.equal(rows[0].executed, false)
  assert.equal(rows[0].dryRun, true)
  assert.equal(rows[0].exitCode, 3)
  assert.equal(rows[1].executed, true)
  assert.equal(rows[1].ok, true)
  assert.equal(rows[1].readbackOk, true)
  assert.equal(rows[1].command, 'add-items')
})

test('④ ID 方式：详情回查补齐；补不到的留空并标「未取到」，不编', () => {
  const w = makeWorld({
    lists: { 8310034: [] },
    details: {
      UCdetail1: { title: 'Detail One', subscriberCount: 120000, country: 'US', engagementRate: 3.2 },
      UCdetail2: { title: 'Detail Two', subscriberCount: 5000 },
    },
    failDetails: ['UCdetailfail'],
  })
  const r = runCli(w.env, ['lists', 'add-items', '--list-id', '8310034',
    '--channel-ids', 'UCdetail1,UCdetail2,UCdetailfail'])
  assert.equal(r.code, 3, r.stderr)
  const plan = r.doc.data.plan
  assert.equal(plan['将加人数'], 3)
  assert.equal(plan['补齐统计'].requested, 3)
  assert.equal(plan['补齐统计'].detailFailed, 1)
  assert.equal(plan['字段补齐情况'].contactEmail, '0/3', '详情里没有邮箱 → 标未取到，不编')
  assert.equal(plan['字段补齐情况'].channelTitle, '2/3')
  const failed = plan['未取到'].明细.find((x) => x.channelId === 'UCdetailfail')
  assert.ok(failed, '失败的那条必须出现在「未取到」明细里')
  assert.ok(failed.缺字段.includes('channelTitle'))
  assert.match(failed.原因, /500/)
  assert.equal(calls(w).filter((c) => c.kind === 'mutate').length, 0, '干跑不得发写请求')
  assert.equal(calls(w).filter((c) => c.kind === 'detail').length, 3, '只对要加的人回查详情')
})

test('⑤ 超过 100 人自动拆批：计划写明批数，真跑逐批写入', () => {
  const w = makeWorld({ lists: { 8310034: [] } })
  const items = Array.from({ length: 205 }, (_, i) => ({
    channelId: `UCbatch${String(i).padStart(4, '0')}`,
    channelTitle: `Channel ${i}`, subscriberCount: 10000 + i,
  }))
  const p = writeItems(w, items)
  const dry = runCli(w.env, ['lists', 'add-items', '--list-id', '8310034', '--items-file', p])
  assert.equal(dry.code, 3)
  assert.equal(dry.doc.data.plan['预计批数'], 3)
  assert.deepEqual(dry.doc.data.plan['批次'].每批人数, [100, 100, 5])

  const real = runCli(w.env, ['lists', 'add-items', '--list-id', '8310034', '--items-file', p, '--confirm'])
  assert.equal(real.code, 0, real.stderr)
  const writes = calls(w).filter((c) => c.kind === 'mutate' && c.route === 'lists.batchAddItems')
  assert.deepEqual(writes.map((c) => c.payload.items.length), [100, 100, 5])
  assert.equal(real.doc.data.readback.detail.delta, 205)
})

test('⑥ 回读不一致 → 退出码 1，并写明差多少；审计记 readback 失败', () => {
  const w = makeWorld({ lists: { 8310034: [] }, mutateMode: 'drop_one' })
  const p = writeItems(w, [
    { channelId: 'UCa', channelTitle: 'A', subscriberCount: 1 },
    { channelId: 'UCb', channelTitle: 'B', subscriberCount: 2 },
  ])
  const r = runCli(w.env, ['lists', 'add-items', '--list-id', '8310034', '--items-file', p, '--confirm'])
  assert.equal(r.code, 1, `回读不一致必须退出 1，实际 ${r.code}：${r.stderr}`)
  assert.equal(r.doc.data.readback.verified, false)
  assert.match(r.doc.data.readback.reason, /回读条数增加 1，与计划新增 2 不一致（差 -1）/)
  const rows = audit(w)
  assert.equal(rows.length, 1)
  assert.equal(rows[0].executed, true)
  assert.equal(rows[0].ok, false)
  assert.equal(rows[0].readbackOk, false)
  assert.equal(rows[0].failureKind, 'readback')
})

test('⑦ 来源二选一：两个都给／都不给，都报"两条路径 + 各自怎么给"', () => {
  const w = makeWorld({ lists: { 8310034: [] } })
  const p = writeItems(w, [{ channelId: 'UCx' }])

  const none = runCli(w.env, ['lists', 'add-items', '--list-id', '8310034'])
  assert.equal(none.code, 2)
  assert.match(none.doc.error.message, /条目来源二选一/)
  assert.match(none.doc.error.hint, /--items-file/)
  assert.match(none.doc.error.hint, /--channel-ids 123456,234567/)
  assert.match(none.doc.error.hint, /最小写法/)

  const both = runCli(w.env, ['lists', 'add-items', '--list-id', '8310034', '--items-file', p,
    '--channel-ids', '123,456'])
  assert.equal(both.code, 2)
  assert.match(both.doc.error.message, /两个都给了/)
  assert.match(both.doc.error.hint, /--items-file/)
  assert.match(both.doc.error.hint, /--channel-ids/)
  // 两条拒绝路径都不得执行写
  assert.equal(calls(w).filter((c) => c.kind === 'mutate').length, 0)
})

test('⑧ --limit：只加前 N 人，超出的记入「超出 --limit」', () => {
  const w = makeWorld({ lists: { 8310034: [] } })
  const p = writeItems(w, [
    { channelId: 'UC1', channelTitle: '1' }, { channelId: 'UC2', channelTitle: '2' },
    { channelId: 'UC3', channelTitle: '3' },
  ])
  const r = runCli(w.env, ['lists', 'add-items', '--list-id', '8310034', '--items-file', p, '--limit', '2'])
  assert.equal(r.code, 3)
  assert.equal(r.doc.data.plan['将加人数'], 2)
  assert.equal(r.doc.data.plan['跳过明细']['超出 --limit'], 1)
})
