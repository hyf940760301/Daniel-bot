/**
 * 单元测试 · 红人检索两条任务式通道（node:test，无需 DSH、不联网、不写盘）
 *
 * 覆盖 5 条硬要求：
 *   ① deep 第一步**不产生提交**（无 jobId、无写调用）—— 用 worker mock 记录"实际发生了什么"；
 *   ② commit 用**错／过期** planId 被拒（且被拒时一次发包都没有）；
 *   ③ status 阶段映射**五档**（排队中／检索中／富化中／完成／失败，含大小写与未知状态）；
 *   ④ open **自动选默认项**且结果里**逐项列出所选**；
 *   ⑤ roster_search 返回 `channel_retired` 且**一次网络/worker 请求都不发**。
 *
 * 跑法：node --test daniel-bot/packages/0.11.0/tests/research-channels.test.mjs
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { apply, __setWorkerForTests, __expireResearchPlanForTests } from '../lib/index.js'
import {
  RESEARCH_STAGES, mapResearchStage, newPlanStore, addPlan, claimPlan,
  openDefaultsView, researchStatusView, PLAN_TTL_MS,
} from '../lib/research.js'

/** 用假 ctx 注册全部工具（与宿主注册路径一致），返回 name → tool */
function registerTools() {
  const got = []
  apply({ tools: { register: (t) => got.push(t) } }, { python: 'python3', timeoutMs: 5000, trace: 'off' })
  return Object.fromEntries(got.map((t) => [t.name, t]))
}

const PLAN_REPLY = {
  channel: 'deep',
  brand: { id: 3690002, name: 'Halliday', category: 'AI Glasses', workspaceId: 90002, competitors: ['Even Realities', 'Ray-Ban Meta'] },
  query: 'AI glasses review and hands-on test',
  queryChars: 34,
  maxQueryChars: 501,
  normalizedNote: null,
  limit: 10,
  payloadKeys: ['brandCategory', 'brandCompetitors', 'brandId', 'brandName', 'query'],
  submitted: false,
}

/** 安装一个记录型 worker mock：把每次 (op,args) 都记下来 */
function recorder(impl) {
  const calls = []
  __setWorkerForTests(async (op, args) => {
    calls.push({ op, args })
    return impl(op, args)
  })
  return calls
}

test('① deep 第一步只出计划：有 planId、无 jobId、只调了一次"出计划"、没有任何提交/写调用', async () => {
  const calls = recorder((op) => {
    if (op === 'research_plan') return PLAN_REPLY
    if (op === 'research_submit') throw new Error('第一步不许提交！')
    throw new Error(`意外的 op: ${op}`)
  })
  const tools = registerTools()
  assert.ok(tools.daniel_deep_research, '工具已注册')

  const out = await tools.daniel_deep_research.execute(
    { brand: 'Halliday', query: 'AI glasses review and hands-on test' }, {},
  )

  assert.equal(out.ok, true)
  assert.ok(out.data.planId, '返回 planId')
  assert.equal(out.data.jobId, undefined, '第一步不得返回 jobId')
  assert.equal(out.data['通道'], '品牌深度研究')
  assert.equal(out.data['将提交的检索式'], PLAN_REPLY.query)
  assert.equal(out.data['品牌']['名称'], 'Halliday')
  assert.equal(out.data['影响']['本次是否发包'], '没有（这一步只出计划；提交是第二步）')
  assert.equal(out.data['过期秒数'], PLAN_TTL_MS / 1000)
  assert.deepEqual(calls.map((c) => c.op), ['research_plan'], '只允许一次"出计划"，不许有 submit')
  assert.equal(out['回答纪律'] !== undefined, true, '返回体必须带回答纪律')
})

test('② commit 用错／过期的 planId 被拒，且被拒时一次提交都不发', async () => {
  const calls = recorder((op) => {
    if (op === 'research_submit') return { channel: 'deep', jobId: 'job-ok', status: 'queued', results: [] }
    if (op === 'research_plan') return PLAN_REPLY
    throw new Error(`意外的 op: ${op}`)
  })
  const tools = registerTools()

  // (a) 不存在的 planId
  const wrong = await tools.daniel_deep_research_commit.execute({ planId: 'deadbeefdeadbeef0000' }, {})
  assert.equal(wrong.ok, false)
  assert.equal(wrong.error.kind, 'unknown_plan')
  assert.equal(calls.filter((c) => c.op === 'research_submit').length, 0, '错 planId 不得提交')

  // (b) 空 planId（宿主先做必填校验；即使绕过校验，工具自己也把它当 usage 拒掉）
  const empty = await tools.daniel_deep_research_commit.execute({ planId: '' }, {})
  assert.equal(empty.error.kind, 'usage')
  await assert.rejects(() => tools.daniel_deep_research_commit.execute({}, {}), /missing required property "planId"/)

  // (c) 过期：先真出一份计划，再把它的时间往前拨过 TTL
  const plan = await tools.daniel_deep_research.execute({ brand: 'Halliday', query: 'AI glasses review' }, {})
  assert.ok(plan.data.planId)
  assert.equal(__expireResearchPlanForTests(plan.data.planId), true)
  const expired = await tools.daniel_deep_research_commit.execute({ planId: plan.data.planId }, {})
  assert.equal(expired.ok, false)
  assert.equal(expired.error.kind, 'plan_expired')
  assert.equal(calls.filter((c) => c.op === 'research_submit').length, 0, '过期 planId 不得提交')

  // (d) 同一份计划只能提交一次（一次确认只对一次执行有效）
  const fresh = await tools.daniel_deep_research.execute({ brand: 'Halliday', query: 'AI glasses review' }, {})
  const first = await tools.daniel_deep_research_commit.execute({ planId: fresh.data.planId }, {})
  assert.equal(first.ok, true)
  assert.equal(first.data.jobId, 'job-ok')
  const second = await tools.daniel_deep_research_commit.execute({ planId: fresh.data.planId }, {})
  assert.equal(second.ok, false)
  assert.equal(second.error.kind, 'plan_used')
  assert.equal(calls.filter((c) => c.op === 'research_submit').length, 1, '只提交了一次')
})

test('②b 计划账本纯逻辑：TTL 边界与非法 planId（不依赖工具闭包）', () => {
  const store = newPlanStore()
  const now = Date.now()
  const { planId, 过期秒数 } = addPlan(store, { kind: 'deep', brand: { id: 1 }, query: 'q', limit: 5, now, ttlMs: 60_000 })
  assert.equal(过期秒数, 60)
  assert.equal(claimPlan(store, planId, { now: now + 59_000 }).ok, true)
  const reused = claimPlan(store, planId, { now: now + 59_500 })
  assert.equal(reused.error.kind, 'plan_used')

  const stale = addPlan(store, { kind: 'deep', brand: {}, query: 'q', limit: 5, now, ttlMs: 60_000 })
  const expired = claimPlan(store, stale.planId, { now: now + 61_000 })
  assert.equal(expired.ok, false)
  assert.equal(expired.error.kind, 'plan_expired')
  assert.equal(store.has(stale.planId), false, '过期计划会被移除')

  assert.equal(claimPlan(store, '', {}).error.kind, 'usage')
  assert.equal(claimPlan(store, 'nope', {}).error.kind, 'unknown_plan')
})

test('③ status 阶段映射固定五档（大小写不敏感；未知状态按检索中，不擅自判失败）', () => {
  assert.deepEqual([...RESEARCH_STAGES], ['排队中', '检索中', '富化中', '完成', '失败'])

  const table = [
    ['queued', '排队中'], ['pending', '排队中'], ['NOT_STARTED', '排队中'], ['', '排队中'],
    ['running', '检索中'], ['Running', '检索中'], ['in_progress', '检索中'],
    ['enriching', '富化中'], ['ENRICH', '富化中'],
    ['done', '完成'], ['completed', '完成'], ['completed_with_warnings', '完成'],
    ['failed', '失败'], ['error', '失败'], ['cancelled', '失败'],
  ]
  for (const [status, stage] of table) {
    const m = mapResearchStage(status)
    assert.equal(m.阶段, stage, `status=${status} 应映射为 ${stage}`)
    assert.equal(m.阶段序号, RESEARCH_STAGES.indexOf(stage) + 1)
    assert.equal(m.终态, stage === '完成' || stage === '失败')
  }
  const weird = mapResearchStage('some_new_state')
  assert.equal(weird.阶段, '检索中')
  assert.equal(weird.已识别, false)
  assert.equal(weird.状态原文, 'some_new_state')
  assert.equal(mapResearchStage('done').进度百分比, 100)
  assert.equal(mapResearchStage('running', { percent: 42.6 }).进度百分比, 43)
})

test('③b researchStatusView：五档出现在工具返回里，进度与结果摘要不空口编', async () => {
  const payload = {
    jobId: 'job-1', status: 'enriching', progressCompleted: 12, progressTotal: 30,
    progressPercent: undefined, foundCount: 88, resultCount: 2,
    results: [
      { 红人: 'Channel A', 订阅数: 120000, 国家: 'US', 均播: 9000, 品类: 'Tech' },
      { 红人: 'Channel B', 订阅数: undefined, 国家: undefined, 均播: undefined, 品类: undefined },
    ],
  }
  const view = researchStatusView(payload)
  assert.equal(view.阶段, '富化中')
  assert.equal(view.进度百分比, 40) // 12/30 推算，服务端没给百分比才推算
  assert.equal(view.已完成条数, 12)
  assert.equal(view.命中总数, 88)
  assert.equal(view.结果摘要.length, 2)
  assert.equal(view.结果摘要[1].订阅数, '未取到', '缺数据必须写"未取到"，不是 null')

  __setWorkerForTests(async (op) => {
    assert.equal(op, 'research_status')
    return payload
  })
  const tools = registerTools()
  const out = await tools.daniel_research_status.execute({ jobId: 'job-1' }, {})
  assert.equal(out.ok, true)
  assert.equal(out.data.阶段, '富化中')
  assert.equal(out.data.终态, false)
  assert.match(out.data['下一步'], /还没跑完/)

  const missing = await tools.daniel_research_status.execute({ jobId: '  ' }, {})
  assert.equal(missing.error.kind, 'usage')
  await assert.rejects(() => tools.daniel_research_status.execute({}, {}), /missing required property "jobId"/)
})

test('④ open 自动选默认项：无需逐项确认，且结果里逐项列出"选了什么＋依据"', async () => {
  const seen = recorder((op) => {
    assert.equal(op, 'open_submit')
    return {
      channel: 'open', jobId: 'job-open-1', topic: 'AI glasses for business travel',
      brand: { id: 3690002, name: 'Halliday' },
      autoSelections: { scenarios: ['国际商务会议'], contentStyles: ['智能眼镜评测'], audiences: ['国际商务旅客'] },
      autoSource: '主题扩写返回的三组标签，自动全选（无需逐项确认；要改直接改结果复核）',
      expandError: null,
      defaults: [
        { 项: '品牌上下文', 取值: 'Halliday', 依据: '按入参' },
        { 项: '场景', 取值: '国际商务会议', 依据: '主题扩写返回的三组标签，自动全选' },
        { 项: '内容风格', 取值: '智能眼镜评测', 依据: '主题扩写返回的三组标签，自动全选' },
        { 项: '受众', 取值: '国际商务旅客', 依据: '主题扩写返回的三组标签，自动全选' },
        { 项: '国家', 取值: '不限', 依据: '未指定 → 不限' },
        { 项: '订阅数下限', 取值: '不限', 依据: '未指定 → 不限' },
      ],
      status: 'queued', progressCompleted: 0, progressTotal: 0,
      results: [], readback: true,
    }
  })
  const tools = registerTools()
  // 两段式：plan 只出计划（不提交），commit 才执行。
  const plan = await tools.daniel_open_research.execute({ topic: 'AI glasses for business travel' }, {})
  assert.equal(plan.ok, true)
  assert.ok(plan.data.planId, 'plan 必须返回 planId')
  assert.equal(seen.length, 0, 'plan 阶段一次提交都不发')
  // plan 必须把「已明确」与「缺失/推断」分开，且缺失项要写怎么补
  const known = plan.data['已明确的参数'] || []
  assert.ok(known.some((x) => String(x.项 || '').includes('主题')), '已明确参数里要有主题')
  const missing = plan.data['缺失或推断的参数'] || []
  for (const item of missing) {
    assert.ok(item.怎么补, `缺失项 ${item.项} 必须写"怎么补"`)
  }

  const out = await tools.daniel_open_research_commit.execute({ planId: plan.data.planId }, {})
  assert.equal(out.ok, true)
  assert.equal(out.data.jobId, 'job-open-1')
  assert.equal(out.data.阶段, '排队中')
  assert.equal(seen.length, 1, '一次 commit 就提交，不需要逐项确认的第二次往返')

  // 扩写失败时也必须如实说"没有可用的自动选项"，不许编标签
  assert.deepEqual(
    openDefaultsView([{ 项: '场景', 取值: null, 依据: '' }]),
    [{ 项: '场景', 取值: '（未取到）', 依据: '（未说明）' }],
  )

  const emptyTopic = await tools.daniel_open_research.execute({ topic: '   ' }, {})
  assert.equal(emptyTopic.error.kind, 'usage')
  await assert.rejects(() => tools.daniel_open_research.execute({}, {}), /missing required property "topic"/)
})

test('⑤ roster_search 已退役：返回 channel_retired 且一次 worker／网络请求都不发', async () => {
  const calls = recorder(() => {
    throw new Error('退役工具不许调用 worker')
  })
  // 连 fetch 也装上探针：退役路径必须"零发包"
  const realFetch = globalThis.fetch
  let fetches = 0
  globalThis.fetch = async () => { fetches += 1; throw new Error('退役工具不许发网络请求') }
  try {
    const tools = registerTools()
    const out = await tools.daniel_roster_search.execute({ query: 'AI glasses review', country: 'US' }, {})

    assert.equal(out.ok, false)
    assert.equal(out.error.kind, 'channel_retired')
    assert.match(out.error.message, /已停用/)
    assert.equal(out.error['本次是否发包'], '没有')
    assert.ok(Array.isArray(out.error['改走']) && out.error['改走'].length >= 2)
    assert.match(out.error['改走'].join(' '), /daniel_deep_research/)
    assert.match(out.error['改走'].join(' '), /daniel_open_research/)
    assert.equal(out['回答纪律'] !== undefined, true)
    assert.equal(calls.length, 0, '退役工具不得调用 worker')
    assert.equal(fetches, 0, '退役工具不得发网络请求')
    // 工具描述明确写了"已停用，请勿调用"
    assert.match(tools.daniel_roster_search.description, /已停用，请勿调用/)
  } finally {
    globalThis.fetch = realFetch
  }
})

test('工具注册清单：两条新通道 ＋ 状态 ＋ 退役的官方库＝5 个检索类工具', async () => {
  const tools = registerTools()
  const names = Object.keys(tools).filter((n) => /research|roster/.test(n)).sort()
  assert.deepEqual(names, [
    'daniel_deep_research',
    'daniel_deep_research_commit',
    'daniel_open_research',
    'daniel_open_research_commit',
    'daniel_research_status',
    'daniel_roster_search',
  ])
  for (const n of names) {
    assert.ok(String(tools[n].description || '').startsWith('[Daniel]'), `${n} 描述保留 [Daniel] 前缀`)
  }
  assert.match(tools.daniel_deep_research.description, /只出计划，不提交/)
  assert.match(tools.daniel_research_status.description, /排队中／检索中／富化中／完成／失败/)
})
