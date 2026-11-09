/**
 * 红人检索的两条任务式通道 · **纯逻辑**（无 I/O、无网络、无子进程，单测直接引用）。
 *
 * 为什么要单独一个模块：
 *   · **阶段映射只能有一处**。上游 `discovery.getSearchJob` 的 `status` 是英文枚举
 *     （`queued／running／enriching／done／failed` 一类），前端左栏与工具返回必须同样五档；
 *     两处各写一份必然漂移，所以统一在这里映射成「排队中／检索中／富化中／完成／失败」。
 *   · **两段式的计划账本要能被单测直接验**（不存在的 planId／过期的 planId 必须被拒），
 *     而它只是内存里的一张表，没有理由绑在工具闭包里。
 *
 * 通道选择口径（语料与工具描述用同一句话）：**有品牌 → deep；无品牌／自由描述 → open**。
 */
import { createHash } from 'node:crypto'

/** 计划有效期：与写操作两段式保持一致（5 分钟）。过期后必须重新出计划。 */
export const PLAN_TTL_MS = 5 * 60 * 1000

/** 五档阶段（顺序固定：前端左栏按这个顺序画进度，不做第二种排序）。 */
export const RESEARCH_STAGES = Object.freeze(['排队中', '检索中', '富化中', '完成', '失败'])

/**
 * 上游 status → 五档阶段。**大小写／首尾空白不敏感**；未知状态按「检索中」显示并保留原文，
 * 不假装认识它（也不擅自判失败：判失败要有服务端的 failed/error 才算数）。
 */
const STAGE_OF_STATUS = new Map([
  ['queued', '排队中'], ['pending', '排队中'], ['created', '排队中'], ['waiting', '排队中'],
  ['scheduled', '排队中'], ['not_started', '排队中'], ['notstarted', '排队中'], ['idle', '排队中'],
  ['running', '检索中'], ['searching', '检索中'], ['processing', '检索中'], ['in_progress', '检索中'],
  ['inprogress', '检索中'], ['executing', '检索中'], ['started', '检索中'], ['started_search', '检索中'],
  ['enriching', '富化中'], ['enrich', '富化中'], ['enrichment', '富化中'],
  ['done', '完成'], ['completed', '完成'], ['completed_with_warnings', '完成'], ['success', '完成'],
  ['succeeded', '完成'], ['finished', '完成'],
  ['failed', '失败'], ['error', '失败'], ['cancelled', '失败'], ['canceled', '失败'],
  ['timeout', '失败'], ['aborted', '失败'], ['rejected', '失败'],
])

/** 终态（不再变化的阶段）：前端据此停止轮询。 */
export const TERMINAL_STAGES = Object.freeze(['完成', '失败'])

/**
 * 上游状态 → 五档阶段。
 * @param {unknown} status 服务端原始状态
 * @param {{percent?: number}} [opts] 已知进度（0–100）；完成态一律补成 100
 * @returns {{阶段: string, 阶段序号: number, 状态原文: string, 已识别: boolean, 终态: boolean, 进度百分比?: number}}
 */
export function mapResearchStage(status, opts = {}) {
  const raw = status === null || status === undefined ? '' : String(status).trim()
  const key = raw.toLowerCase()
  // 空状态＝任务刚建、还没回读到状态 → 排队中；非空但没见过的 → 检索中（并保留原文供排查）
  const stage = raw === '' ? '排队中' : (STAGE_OF_STATUS.get(key) ?? '检索中')
  const out = {
    阶段: stage,
    阶段序号: RESEARCH_STAGES.indexOf(stage) + 1,
    状态原文: raw || '（服务端尚未给出状态）',
    已识别: raw === '' ? true : STAGE_OF_STATUS.has(key),
    终态: TERMINAL_STAGES.includes(stage),
  }
  const pct = Number(opts.percent)
  if (Number.isFinite(pct)) out.进度百分比 = Math.max(0, Math.min(100, Math.round(pct)))
  else if (stage === '完成') out.进度百分比 = 100
  return out
}

/** 计划账本（planId → 计划）。工具闭包里只放一张；单测可以直接 new 一张来验拒绝路径。 */
export function newPlanStore() {
  return new Map()
}

function digestOf(kind, args) {
  return createHash('sha256')
    .update(`${kind}|${JSON.stringify(args ?? {})}`)
    .digest('hex')
    .slice(0, 20)
}

/**
 * 登记一份**待确认**的计划（deep 通道第一步）。这一步不提交任何东西。
 * @returns {{planId: string, 过期秒数: number, createdAt: number}}
 */
export function addPlan(store, { kind, brand, query, limit, now = Date.now(), ttlMs = PLAN_TTL_MS, ...extra }) {
  const planId = digestOf(kind, { brand, query, limit, now, salt: Math.random() })
  // `...extra` 只用来让两条通道各自多带自己的字段（open 的 topic／filters），
  // **不参与 planId 摘要**：摘要口径保持不变，deep 的计划账本形状不变。
  store.set(planId, { kind, brand, query, limit, createdAt: now, ttlMs, used: false, ...extra })
  return { planId, 过期秒数: Math.round(ttlMs / 1000), createdAt: now }
}

/**
 * 取用一份计划（两段式第二步）。四条拒绝路径都必须给出**可执行**的错误语义：
 *   usage（没给编号）／unknown_plan（编号不存在）／wrong_channel（拿错通道的计划）／
 *   plan_used（已执行过一次）／plan_expired（超过有效期）。
 * 校验通过即标记 used（一次确认只对一次执行有效），并返回计划本身。
 *
 * `toolName` 与 `expectKind` 都是可选参数：不传时行为与改造前逐字一致（deep 通道不受影响）。
 */
export function claimPlan(store, planId, { now = Date.now(), expectKind = null, toolName = 'daniel_deep_research' } = {}) {
  const id = String(planId ?? '').trim()
  if (!id) {
    return { ok: false, error: { kind: 'usage', message: `planId 必填：先用 ${toolName} 出计划。` } }
  }
  const rec = store.get(id)
  if (!rec) {
    return { ok: false, error: { kind: 'unknown_plan', message: `planId 不存在（可能写错了，或计划从未生成）。请重新 ${toolName}。` } }
  }
  if (expectKind && rec.kind !== expectKind) {
    return {
      ok: false,
      error: {
        kind: 'wrong_channel',
        message: `这份计划属于「${rec.kind === 'deep' ? '品牌深度研究' : 'AI 开放研究'}」，不能在当前通道执行。请重新 ${toolName} 出计划。`,
      },
    }
  }
  if (rec.used) {
    return { ok: false, error: { kind: 'plan_used', message: `这份计划已经提交过一次（一次确认只对一次执行有效）。请重新 ${toolName}。` } }
  }
  if (now - rec.createdAt > (rec.ttlMs ?? PLAN_TTL_MS)) {
    store.delete(id)
    return { ok: false, error: { kind: 'plan_expired', message: `这份计划已过期（有效期 5 分钟）。请重新 ${toolName} 出计划并请用户确认。` } }
  }
  rec.used = true
  return { ok: true, plan: rec }
}

/** 「自动选了哪些默认项」的业务视图：每项都必须是「项／取值／依据」三件套，缺一不编。 */
export function openDefaultsView(defaults) {
  const items = Array.isArray(defaults) ? defaults : []
  return items.map((d) => ({
    项: String((d && d['项']) || '未命名项'),
    取值: String((d && d['取值'] !== undefined && d['取值'] !== null && d['取值'] !== '') ? d['取值'] : '（未取到）'),
    依据: String((d && d['依据']) || '（未说明）'),
  }))
}

/**
 * open 通道计划里的**参数分栏**：已明确的 vs 缺失／推断的。
 *
 * 为什么要分栏（2026-11-08 用户要求）：把"用户明确给了"和"系统准备推断"混在一张表里，
 * 用户就无法判断"我到底确认了什么"。这里只做分栏与文案，**不做任何取数**：
 *   · 已明确：用户原话里给了的（主题／品牌／国家／订阅数下限）；
 *   · 缺失：没给、提交时会采用默认值的（每项都写"怎么补"）；
 *   · 推断：提交时才由服务端扩写决定的（场景／内容风格／受众），**绝不写进已明确**。
 */
export function openPlanParams({ topic, brand, country, minSubscribers }) {
  const known = [{
    项: '主题／检索式',
    取值: String(topic ?? ''),
    依据: '用户原话（本次计划绑定这个值，提交时不可改）',
  }]
  if (brand) known.push({ 项: '品牌上下文', 取值: String(brand), 依据: '按入参' })
  if (country) known.push({ 项: '国家', 取值: String(country), 依据: '按入参' })
  if (minSubscribers !== undefined && minSubscribers !== null && minSubscribers !== '') {
    known.push({ 项: '订阅数下限', 取值: String(minSubscribers), 依据: '按入参' })
  }

  const missing = []
  if (!brand) {
    missing.push({
      项: '品牌上下文', 状态: '缺失', 取值: '未指定（提交时沿用默认品牌 Halliday）',
      怎么补: '要用别的品牌，在 brand 参数里给品牌名或品牌编号（它只影响竞品/品类上下文，不改主题）。',
    })
  }
  if (!country) {
    missing.push({
      项: '国家', 状态: '缺失', 取值: '不限',
      怎么补: '只想看某个市场，在 country 里给国家代码（如 US；多个用英文逗号分开）。',
    })
  }
  if (minSubscribers === undefined || minSubscribers === null || minSubscribers === '') {
    missing.push({
      项: '订阅数下限', 状态: '缺失', 取值: '不限',
      怎么补: '想排除小号，在 minSubscribers 里给数字（如 10000）；不给则不设下限。',
    })
  }

  // 三项都是**提交时才确定**的推断值：计划阶段不预取（避免"计划里写了一套、提交时又变一套"）
  const inferred = [
    { 项: '场景', 状态: '推断', 取值: '提交时按主题自动扩写（本计划不预取）',
      怎么补: '想固定场景，请直接在 topic 里写清（例如"商务会议场景"）。' },
    { 项: '内容风格', 状态: '推断', 取值: '提交时按主题自动扩写（本计划不预取）',
      怎么补: '想固定风格，请在 topic 里写清（例如"上手评测风格"）。' },
    { 项: '受众', 状态: '推断', 取值: '提交时按主题自动扩写（本计划不预取）',
      怎么补: '想固定受众，请在 topic 里写清（例如"面向商务旅客"）。' },
  ]
  return { 已明确的参数: known, 缺失或推断的参数: [...missing, ...inferred] }
}

/**
 * open 通道的预估三件套。**只给口径与依据，不编数字**：
 * 条数在提交前无法确定（服务端按检索式实算），时长由服务端排队决定，消耗是确定的
 * （建 1 条任务 ＋ 执行 1 次 ＋ 写 1 条检索记录）。三块都带「依据」，方便用户复核。
 */
export function openPlanEstimate() {
  return {
    条数: {
      预估值: '提交前无法确定（不承诺条数）',
      依据: '服务端按检索式实算；提交后可在任务状态里看到命中总数',
    },
    时长: {
      预估值: '分钟级（排队＋检索＋富化，具体由服务端定）',
      依据: '本通道提交后立即返回任务编号、不阻塞等待；进度用 daniel_research_status 查',
    },
    消耗: {
      预估值: '创建 1 条检索任务 ＋ 执行 1 次；写 1 条检索记录；占用每月检索额度 1 次（账号无上限时不消耗）',
      依据: '与本通道的实际提交序列一致（建任务 → 执行）',
    },
  }
}

/** 一条任务状态的业务视图（工具返回与前端左栏共用同一份字段名）。 */
export function researchStatusView(data) {
  const d = data && typeof data === 'object' ? data : {}
  const total = Number.isFinite(Number(d.progressTotal)) ? Number(d.progressTotal) : undefined
  const done = Number.isFinite(Number(d.progressCompleted)) ? Number(d.progressCompleted) : undefined
  const pct = Number.isFinite(Number(d.progressPercent))
    ? Number(d.progressPercent)
    : (total && total > 0 && done !== undefined ? Math.round((done * 100) / total) : undefined)
  const stage = mapResearchStage(d.status, { percent: pct })
  const rows = Array.isArray(d.results) ? d.results : []
  const out = {
    任务编号: d.jobId ? String(d.jobId) : '（未取到）',
    ...stage,
    已完成条数: done ?? rows.length,
    候选条数: rows.length,
    结果摘要: rows.map((r) => ({
      红人: String((r && r['红人']) || '（未命名频道）'),
      订阅数: r && r['订阅数'] !== undefined && r['订阅数'] !== null ? r['订阅数'] : '未取到',
      国家: r && r['国家'] ? String(r['国家']) : '未取到',
      均播: r && r['均播'] !== undefined && r['均播'] !== null ? r['均播'] : '未取到',
      品类: r && r['品类'] ? String(r['品类']) : '未取到',
    })),
  }
  if (total !== undefined) out.总数 = total
  if (Number.isFinite(Number(d.foundCount))) out.命中总数 = Number(d.foundCount)
  if (d.resultsTruncated) out.结果已截断 = true
  if (d.errorMessage) out.失败原因 = String(d.errorMessage).slice(0, 300)
  if (Array.isArray(d.keywords) && d.keywords.length) out.检索关键词 = d.keywords.slice(0, 40).map(String)
  return out
}
