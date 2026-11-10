/**
 * 业务视图层：把系统内部字段翻译成"业务语言"，并**丢弃**内部技术字段。
 *
 * 为什么需要它：工具直接回原始 JSON 时，模型会把这些内部键名（如 otherProductLines、
 * industryKeywords、expandedCategoryKeywords）原样讲给用户——既看不懂，也等于把系统字段
 * 暴露给外部。这里统一做两件事：
 *   ① 只保留业务需要的字段，并按中文业务词命名；
 *   ② 内部技术字段（id 之外的 userId、onboardingCompleted、createdAt 等）一律不进输出。
 */
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join, resolve as resolvePath } from 'node:path'

const COUNTRY_CN = {
  US: '美国', CA: '加拿大', GB: '英国', UK: '英国', DE: '德国', FR: '法国', JP: '日本',
  AU: '澳大利亚', KR: '韩国', IT: '意大利', ES: '西班牙', NL: '荷兰', BR: '巴西', IN: '印度',
}

function countries(list) {
  if (!Array.isArray(list) || !list.length) return null
  return list.map((c) => COUNTRY_CN[String(c).toUpperCase()] || String(c))
}

/** 竞品：只留「名称 + 该竞品覆盖的品类关键词」，其余子字段不输出 */
function competitors(list) {
  if (!Array.isArray(list) || !list.length) return null
  return list.map((c) => {
    const out = { 名称: c && c.name ? String(c.name) : '（未命名）' }
    const kw = c && (c.categoryKeywords || c.keywords)
    if (Array.isArray(kw) && kw.length) out.品类关键词 = kw.map(String)
    return out
  })
}

function keywords(list) {
  if (!Array.isArray(list) || !list.length) return null
  return list.map(String)
}

/** 品牌业务视图（对外只讲这些） */
export function brandView(raw) {
  if (!raw || typeof raw !== 'object') return null
  const v = {
    品牌名: raw.name || null,
    品牌编号: raw.id ?? null,
    简介: raw.description || null,
    品类: raw.category || null,
    目标市场: countries(raw.targetCountries),
    行业关键词: keywords(raw.industryKeywords),
    竞品: competitors(raw.competitors),
    样品价: typeof raw.sampleCost === 'number' ? raw.sampleCost : null,
    关联频道: raw.youtubeChannelTitle || raw.youtubeChannelId || null,
  }
  // 只去掉空项，不保留任何内部键
  for (const k of Object.keys(v)) if (v[k] === null || v[k] === undefined) delete v[k]
  if (v.竞品) v.竞品数 = v.竞品.length
  if (v.行业关键词) v.行业关键词数 = v.行业关键词.length
  return v
}

/** 频道业务视图（KOL 档案用） */
export function channelView(raw) {
  if (!raw || typeof raw !== 'object') return null
  const v = {
    频道名: raw.title || raw.channelTitle || null,
    频道编号: raw.channelId || null,
    订阅数: raw.subscriberCount ?? null,
    国家: COUNTRY_CN[String(raw.country || '').toUpperCase()] || raw.country || null,
    总播放: raw.viewCount ?? null,
    视频数: raw.videoCount ?? null,
    建号时间: raw.joinedDate || null,
    标签: Array.isArray(raw.tags) ? raw.tags.map(String) : null,
  }
  for (const k of Object.keys(v)) if (v[k] === null || v[k] === undefined) delete v[k]
  return v
}

/** 统一附在每次返回里的"回答纪律"，确保跨轮次也能守住 */
export const ANSWER_POLICY =
  '回答只用业务语言：说明「做到了哪一步＋涉及哪些业务信息（品牌/名额/市场/竞品/关键词等）＋下一步」；' +
  '每次交付后必须给 1–2 条具体下一步（直接说做什么，不写"还可以继续优化"这类空话），' +
  // 🔴 模块名必须与前端「下一步卡片」的解析表**逐字一致**（2026-11-03 前端改为 Daniel 原名后同步）：
  //    账号与盘点／品牌档案／红人检索／红人名单／真实性核验／合作追踪／品牌提及／内容情报／声量份额。
  //    写成旧名（账号与工作区／品牌资产／真实性与背调）会让卡片解析不到而**被前端直接丢弃**。
  '每条写明所属模块：账号与盘点／品牌档案／红人检索／红人名单／真实性核验／合作追踪／品牌提及／内容情报／声量份额，' +
  '且与本任务相关；最多 2 条，不列成长菜单；任务失败或数据不足时，下一步写「补齐什么」；' +
  '禁用「如需」「可以帮你」这类句式起头；' +
  '禁止出现接口名、路由名、字段英文名（如 otherProductLines／industryKeywords）、HTTP 动作、payload 之类的系统内部信息。' +
  // 🔴 固定格式（2026-11-03 新增，见 CHANGES-NEXT-STEPS-FIX.md）：前端「下一步卡片」只认
  //    「标题行 ＋ 每项 <模块名>：<动作>」。只写"要给 1–2 条下一步"是不够的——模型会把它
  //    写成一段正文或几行不带标记的文字，卡片就解析不到（2026-11-03 18:51 那条回答即如此）。
  '交付完成后，单独一行写「下一步：」，下面用「- 模块名：具体动作」列出 1–2 条（模块名必须是上面九个之一）。' +
  // 🔴 结果区折叠（2026-11-09 新增，见 PHASE1-INTERACTION-DESIGN §2.2／§10、CHANGES-SLICE2.md）：
  //    前端「说明与下一步」只认下面这个格式；标题必须是「业务思路：」「自我检讨：」两行之一，
  //    每条以「- 」起头。**可选**：没有内容就别写，禁止为凑格式编造。
  '任务结束时可选补充两段说明（只在确实有内容时才写，没有就不写，禁止编造）：' +
  '单独一行写「业务思路：」，下面用「- 」列 1–4 条，每条一句话，写清用了什么检索词／筛选维度／关键取舍；' +
  '再单独一行写「自我检讨：」，下面用「- 」列 1–3 条，每条一句话，写清这次哪里做得不够（如数据缺失、口径受限）；' +
  '确实没有明显问题就写一条「这次没有明显问题」；这两段同样禁止出现接口名、字段名、模块名。'



/** 品牌清单（跨工作区）→ 业务视图：只留名称、编号、所属工作区 */
export function brandList(raw) {
  const items = (raw && (raw.brands || raw.items)) || []
  return {
    数量: raw && typeof raw.count === 'number' ? raw.count : items.length,
    品牌: items.map((b) => ({
      品牌名: b.name || null,
      品牌编号: b.id ?? null,
      所属工作区: b.workspaceName || null,
    })),
    数据时点: raw && raw.indexBuiltAt ? raw.indexBuiltAt : null,
  }
}

/** 能力域清单 → 业务视图：去掉语料路径、源文件、指纹等内部信息 */
export function skillsList(raw) {
  if (!raw || typeof raw !== 'object') return null
  const domains = (raw['能力域'] || []).map((d) => {
    const item = { 名称: d['域名'] || d['名称'] || null, 主题: d['能力域'] || null }
    if (typeof d['切片数'] === 'number') item.切片数 = d['切片数']
    const summary = String(d['摘要'] || '').replace(/\*\*/g, '')
    if (summary) item.摘要 = summary.slice(0, 60) + (summary.length > 60 ? '…' : '')
    return item
  })
  const total = raw['总量'] || {}
  return {
    能力域数: raw['能力域数'] ?? domains.length,
    语料版本: raw['语料版本'] ?? null,
    完整性: raw['完整性'] ?? null,
    切片总数: total['切片数'] ?? null,
    能力域: domains,
  }
}


/** 数字格式：大数用"万/亿"，率用百分比（业务看得懂） */
function num(n) {
  if (typeof n !== 'number' || !isFinite(n)) return null
  if (n >= 1e8) return (n / 1e8).toFixed(2) + ' 亿'
  if (n >= 1e4) return (n / 1e4).toFixed(1) + ' 万'
  return String(Math.round(n * 100) / 100)
}
function pct(x) {
  if (typeof x !== 'number' || !isFinite(x)) return null
  return (x * 100).toFixed(1) + '%'
}
/** 比率：2 位小数（页面口径，TICKET-234） */
function pct2(x) {
  if (typeof x !== 'number' || !isFinite(x)) return null
  return (x * 100).toFixed(2) + '%'
}
/** 整数：原始值不压缩（TICKET-234：要能与页面的 523,922 逐格对上） */
function int(n) {
  if (typeof n !== 'number' || !isFinite(n)) return null
  return Math.round(n)
}

const AGE_CN = { age18To24: '18-24', age25To34: '25-34', age35To44: '35-44', age45To54: '45-54', age55To64: '55-64', age65Plus: '65+' }

/* ── 表现块：与 Daniel 详情抽屉**同口径**（TICKET-230／231）─────────────
 *
 * 为什么不能只读 insight：抽屉的 Performance 不是读 insight，而是拿
 * `getChannelVideos` 的**视频列表现算**（`CreatorSlideOver` 的 memo）。
 * 只读 insight 会得到两种坏结果：① insight 为 null 时整块消失（用户看到"没有查到
 * 官方数据"，页面却明明有数）；② insight 有值时给的是**均值**，与页面的**中位数**
 * 相差可达一个数量级（实测 7,820 vs 665）。
 *
 * 逐字复现（与 `.kol-tools/daniel_ui_parity.py::video_list_stats` 对齐）：
 *   · 长视频样本 = contentType==="VIDEO_ON_DEMAND" **且** views>=100
 *   · 短视频样本 = contentType==="SHORTS"（**无**播放阈值）
 *   · 窗口：28 天内且条数>=3 → 用这批；否则退回"最新 30 条"
 *   · 平均播放／平均点赞 = **中位数** sorted[floor(n/2)]（偶数取上中位），不是均值
 *   · 互动率 = (Σlikes+Σcomments)/Σviews（分母用同一批样本）
 *
 * 样本量：页面拉 50 条，平台实测只给 20 条（`limit` 无效，TICKET-232），
 * 因此块里显式标注「样本 N 条」，不假装和页面同源同量。
 */
const WINDOW_28D_MS = 672 * 60 * 60 * 1000

const _n = (v) => {
  const x = Number(v)
  return isFinite(x) ? x : 0
}
const _ms = (t) => {
  if (t === null || t === undefined || t === '') return null
  if (typeof t === 'number') return t > 1e12 ? t : t * 1000
  const s = String(t).trim()
  if (/^\d+$/.test(s)) { const n = Number(s); return n > 1e12 ? n : n * 1000 }
  const x = Date.parse(s)
  return isFinite(x) ? x : null
}
/** 中位数：只统计 >0 的值，偶数长度取上中位（对齐 JS `d[Math.floor(n/2)]`） */
function median(list) {
  const d = list.filter((x) => x > 0).sort((a, b) => a - b)
  return d.length ? d[Math.floor(d.length / 2)] : 0
}
function windowOf(sample, nowMs) {
  const recent = sample.filter((v) => {
    const p = _ms(v && v.publishTime)
    return p !== null && nowMs - p <= WINDOW_28D_MS
  })
  return recent.length >= 3 ? { use: recent, source: '近28天' } : { use: sample.slice(0, 30), source: '最新30条' }
}
function scopeOf(label, sample, nowMs) {
  const { use, source } = windowOf(sample, nowMs)
  if (!use.length) return null
  // 互动率按页面公式：(Σlikes+Σcomments)/Σviews，分母用**该范围全量**视频（页面不对它开窗）
  const views = sample.reduce((s, v) => s + _n(v.views), 0)
  const likes = sample.reduce((s, v) => s + _n(v.likes), 0)
  const comments = sample.reduce((s, v) => s + _n(v.comments), 0)
  return {
    范围: label,
    视频数: use.length,
    平均播放: int(median(use.map((v) => _n(v.views)))),
    平均点赞: int(median(use.map((v) => _n(v.likes)))),
    互动率: views > 0 ? pct2((likes + comments) / views) : null,
    样本: `${source} · 样本 ${use.length} 条`,
  }
}

/** 用视频列表按页面口径算表现块（页面唯一数据源） */
function performanceFromVideos(videos, nowMs = Date.now()) {
  if (!Array.isArray(videos) || !videos.length) return null
  const vod = videos.filter((v) => v && v.contentType === 'VIDEO_ON_DEMAND' && _n(v.views) >= 100)
  const shorts = videos.filter((v) => v && v.contentType === 'SHORTS')
  // 「整体」= 长视频样本 + 短视频样本（与页面 `u(vod.concat(shorts))` 一致，
  // 不是"全部视频"——播放 <100 的长视频页面本来就不计）
  const blocks = [
    scopeOf('整体', vod.concat(shorts), nowMs),
    scopeOf('长视频', vod, nowMs),
    scopeOf('短视频', shorts, nowMs),
  ].filter(Boolean)
  return blocks.length ? blocks : null
}

/** 兜底：视频列表拿不到时，才退回 insight 的均值口径（并标明口径不同） */
function performanceBlock(stats) {
  if (!stats || typeof stats !== 'object') return null
  const one = (label, o) => {
    if (!o || typeof o !== 'object') return null
    return {
      范围: label,
      视频数: o.videoCount ?? null,
      总播放: int(o.views),
      平均播放: int(o.averageViewsPerVideo),
      平均点赞: int(o.averageLikesPerVideo),
      互动率: pct2(o.engagementRate),
      独立观众: int(o.uniqueViewers),
      样本: '平台汇总（均值口径，非页面口径）',
    }
  }
  const blocks = [one('整体', stats.overall), one('长视频', stats.vod), one('短视频', stats.shorts)].filter(Boolean)
  return blocks.length ? blocks : null
}

function topInterests(map, n = 5) {
  if (!map || typeof map !== 'object') return null
  const rows = Object.values(map)
    .filter((v) => v && typeof v === 'object')
    .sort((a, b) => (b.relativeRelevance || 0) - (a.relativeRelevance || 0))
    .slice(0, n)
    .map((v) => ({ 兴趣: v.label || null, 受众占比: pct(v.audienceSharePercentage), 相关度: v.relativeRelevance ? Number(v.relativeRelevance.toFixed(1)) : null }))
  return rows.length ? rows : null
}

function audienceBlock(a) {
  if (!a || typeof a !== 'object') return null
  const out = {}
  const g = a.genderDistribution || {}
  if (Object.keys(g).length) out.性别 = { 男性: pct(g.male), 女性: pct(g.female), 未标注: pct(g.userSpecified) }
  const age = a.ageDistribution || {}
  if (Object.keys(age).length) {
    out.年龄 = Object.entries(age).map(([k, v]) => ({ 区间: AGE_CN[k] || k, 占比: pct(v) })).filter((x) => x.区间)
  }
  const loc = a.locationDistribution || {}
  if (Object.keys(loc).length) {
    out.地区Top = Object.entries(loc).sort((x, y) => y[1] - x[1]).slice(0, 5)
      .map(([k, v]) => ({ 地区: COUNTRY_CN[String(k).toUpperCase()] || k, 占比: pct(v) }))
  }
  const aff = topInterests(a.affinityInterests)
  if (aff) out.兴趣人群 = aff
  const mkt = topInterests(a.inMarketInterests)
  if (mkt) out.购买意向 = mkt
  return Object.keys(out).length ? out : null
}

function videosBlock(list) {
  if (!Array.isArray(list) || !list.length) return null
  return list.map((v) => ({
    标题: v.title || null,
    播放: num(v.views),
    点赞: num(v.likes),
    时长秒: v.durationSecs ?? null,
    发布时间: v.publishTime || null,
    链接: v.videoUrl || null,
  }))
}

/** KOL 完整业务视图：档案 ＋ 表现（页面同口径）＋ 受众 ＋ 近期视频 */
export function kolFullView(payload) {
  const raw = (payload && payload.raw) || {}
  const view = { 频道: channelView(raw.detail || payload.channel || {}) }
  // 表现块优先级（TICKET-230）：视频列表复算（页面口径）→ insight 兜底（均值口径）
  const perf = performanceFromVideos(raw.videosAll || raw.videos) || performanceBlock((raw.insight || {}).stats)
  if (perf) view.表现_近28天 = perf
  const aud = audienceBlock((raw.insight || {}).audience)
  if (aud) view.受众 = aud
  const vids = videosBlock(raw.videos)
  if (vids) view.近期视频 = vids
  /* 缺块语义（TICKET-233）：必须分清两件事，否则用户会把"平台没有"当成"我们坏了"。
     · 平台未收录 = 接口正常返回、但该字段就是空（再查也一样）
     · 本次未取到 = 取数失败／根本没走到（重试或补采有意义） */
  const missing = []             // 本次未取到
  const notCovered = []          // 平台未收录
  if (!raw.detail) missing.push('频道档案')
  if (!perf) missing.push('表现数据')
  if (!raw.videos) missing.push('近期视频')
  const insightData = raw.insight || null
  const insightStatus = raw.insightStatus || (insightData ? 'ok' : 'empty')
  if (!aud) {
    if (insightStatus === 'error') missing.push('受众数据')
    else notCovered.push('受众与兴趣画像')
  }
  if (missing.length) view.未取到 = missing
  if (notCovered.length) view.平台未收录 = notCovered
  const hints = []
  if (!perf) hints.push('表现数据拿不到时，按视频列表复算（与详情抽屉同口径）')
  if (notCovered.length) hints.push('受众画像平台未收录时，改用平均播放、互动率、内容分类判断人群；需要平台补采可单独发起（需你确认）')
  if (missing.length) hints.push('取数失败的项可稍后重试，重试仍失败再考虑补采')
  if (hints.length) view.替代信号 = hints
  return view
}


/* ───────── 通用：内部键清洗 + 业务化改名 + 写计划业务化 ───────── */

/** 内部键：一律不输出（接口名、路由、调试信息、本机路径等） */
const INTERNAL_KEY = /^(route|method|procedure|payload|request|response|http|httpStatus|rawBody|trpc|_meta|_debug|shape|seconds|elapsedMs|nextPageToken|auditPath|indexBuiltAt|源文件|源文件sha256|源文件行数|语料根|定位方式|读法|写入字段|品牌编号?\b)$/i

/** 内部键 → 业务词（键名本身也要中文化，否则等于暴露字段名） */
const KEY_CN = {
  id: '编号', name: '名称', title: '标题', description: '简介', category: '品类',
  workspaceId: '工作区编号', workspaceName: '工作区', brandId: '品牌编号',
  channelId: '频道编号', competitorId: '竞品编号', brand: '品牌',
  industryKeywords: '行业关键词', targetCountries: '目标市场', sampleCost: '样品价',
  competitors: '竞品', categoryKeywords: '品类关键词', youtubeChannelId: '频道编号',
  youtubeChannelTitle: '关联频道', videoCount: '视频数', subscriberCount: '订阅数',
  viewCount: '总播放', country: '国家', createdAt: '创建时间', updatedAt: '更新时间',
  videos: '视频', count: '数量', items: '条目', brands: '品牌', data: '数据',
  audience: '受众', stats: '数据', averageStats: '平均数据', timeRange: '统计窗口',
  startTime: '开始时间', endTime: '结束时间', overall: '整体', vod: '长视频', shorts: '短视频',
}

export function renameAndScrub(value, depth = 0) {
  if (depth > 6 || value === null || typeof value !== 'object') return value
  if (Array.isArray(value)) return value.slice(0, 30).map((x) => renameAndScrub(x, depth + 1))
  const out = {}
  for (const [k, v] of Object.entries(value)) {
    if (INTERNAL_KEY.test(k)) continue
    out[KEY_CN[k] || k] = renameAndScrub(v, depth + 1)
  }
  return out
}

/** 写计划 → 业务语言：把「要做什么、影响谁、改哪几项（现值和目标值）」讲清楚，不出现字段名 */
const FIELD_CN = {
  name: '品牌名', description: '简介', category: '品类', industryKeywords: '行业关键词',
  targetCountries: '目标市场', sampleCost: '样品价', competitors: '竞品',
  youtubeChannelId: '关联频道编号', youtubeChannelTitle: '关联频道名称',
}

/** 影响范围里的人话化：只替换已知字段名，不碰英文正文（TICKET-235） */
function impactText(text) {
  if (!text) return null
  let out = String(text)
  for (const [k, cn] of Object.entries(FIELD_CN)) {
    out = out.replace(new RegExp(`\\b${k}\\b`, 'g'), cn)
  }
  return out
}

export function planView(plan, op) {
  if (!plan || typeof plan !== 'object') return null
  const changes = (plan.changes && Object.values(plan.changes)[0]) || {}
  const items = []
  for (const [k, v] of Object.entries(changes)) {
    if (k === 'id' || k === 'workspaceId') continue
    items.push({ 项目: FIELD_CN[k] || k, 目标值: Array.isArray(v) ? v.length + ' 项' : String(v) })
  }
  const before = plan.before || {}
  const withBefore = items.map((it) => {
    const old = Object.entries(before).find(([k]) => (FIELD_CN[k] || k) === it.项目)
    return old ? { ...it, 现有值: Array.isArray(old[1]) ? old[1].length + ' 项' : String(old[1]) } : it
  })
  return {
    动作: op || plan.action || null,
    影响对象: plan.targetName || plan.brand || null,
    所属工作区编号: plan.workspaceId ?? null,
    影响范围: impactText(plan.impact),
    将要改动: withBefore.length ? withBefore : null,
    配额: plan.quota ? { 上限: plan.quota.limit ?? null, 当前占用: plan.existingBrandCount ?? null } : null,
  }
}


/* ───────── 输出契约：四段溯源（筛选逻辑链／入选理由／排除分块／口径假设）─────────
 *
 * 为什么放在视图层：四段讲的仍然是**业务语言**（为什么筛掉、口径是什么），和 brandView／
 * skillsList 一样属于"把系统内部动作翻译成人话"，不该散落在工具实现里。
 *
 * 纪律（对应 09-工程方案 §4.1「失败不升级」）：
 *   · 每段的值只能是**字符串**或**字符串数组**，绝不能是 null／空数组；
 *   · 本层能确定产出的给真实内容；产不出的统一给「本次溯源不可用（原因：…）」；
 *   · 任何异常都就地降级成上面那句话，**绝不上抛**（不许因为溯源把工具搞挂）。
 */

export const TRACE_VERSION = '1.1'
/** 四段固定顺序（顺序即呈现顺序，改顺序等于改契约） */
export const TRACE_SECTIONS = Object.freeze(['筛选逻辑链', '入选理由', '排除分块', '口径假设'])
/** 产不出溯源时的固定措辞（前端/文档/测试都按这句话判定"降级"） */
export const TRACE_UNAVAILABLE = '本次溯源不可用'

/**
 * 详简两层（设计草案 §2.4）：同一份四段，两种密度。
 *   summary → 每段 **≤2 条短句** 的结论级信息（够判断）
 *   full    → 完整四段（骨架内容 ＋ 每条理由更细的表述，够复盘）
 */
export const TRACE_LEVELS = Object.freeze(['summary', 'full'])
export const TRACE_SUMMARY_MAX_LINES = 2
export const TRACE_SUMMARY_LINE_MAX = 40
/**
 * 「排除分块」的简版例外（TICKET-217）：闸账本要**一闸一行**把淘汰数写出来，
 * 否则简版就说不清"是哪道闸淘汰了多少"（设计草案 §2.4 简版也要带排除分块数量）。
 * 上限：1 行合计 ＋ 至多 3 道闸 ＋ 1 行明细落点 ＋ 1 行缺项 ＝ 6 行；每行 60 字。
 */
export const TRACE_EXCLUDED_MAX_LINES = 6
export const TRACE_EXCLUDED_LINE_MAX = 60
/** 超过这么多位排除，明细落 CSV 文件而不是铺在会话里（用户 2026-10-19 定：30） */
export const EXCLUDED_CSV_THRESHOLD = 30
/** 排除明细 CSV 的列（顺序即表头顺序） */
export const EXCLUDED_CSV_COLUMNS = Object.freeze(['任务标识', '闸', '红人', '频道编号', '订阅数', '国家', '品类', '判据'])
/** 账本保鲜期（秒）：超过这个时长的 ledger.json 视为过期，按「缺」处理（不让旧账本冒充本次） */
export const LEDGER_TTL_SECONDS = 900

/** 档位 → 层级：只有 full 是详版，其余（含 off，虽然 off 不会走到这里）按简版 */
export function traceLevelOf(mode) {
  return String(mode === undefined || mode === null ? '' : mode).trim().toLowerCase() === 'full' ? 'full' : 'summary'
}

/** 降级文案：固定措辞 ＋ 原因（原因必带，否则读的人不知道是"没筛"还是"没做"） */
export function traceUnavailable(reason) {
  return `${TRACE_UNAVAILABLE}（原因：${String(reason || '本次无可确定的口径信息').slice(0, 120)}）`
}

/** 「本次没做成筛选记录」的固定措辞（方案 C：缺什么就点名，不许编数字） */
export const TRACE_MISSING = '本次溯源不可用（缺：'
/** 显式声明「这次根本没有筛选环节」（非名单类）的固定措辞 */
export const TRACE_NO_GATE = '本次无筛选环节（非名单类）'
/** 执行侧筛选、宿主侧看不见闸记录的固定措辞（batch／run） */
export const TRACE_EXECUTOR_SIDE = '筛选闸记录；筛选发生在执行侧，需由执行侧记账'

/**
 * 「本次溯源不可用（缺：<具体缺哪一闸>）」—— 方案 C 的第三种合法形态。
 * 与 `traceUnavailable()`（原因式降级）不同：这里点明**缺的是哪一闸**，读的人能据此补数据。
 */
export function traceMissing(what) {
  return `${TRACE_MISSING}${String(what || '筛选闸记录').slice(0, 120)}）`
}

/** 段值归一：只留非空字符串；字符串包成单元素数组（对外统一"字符串数组"形态） */
function traceLines(v) {
  if (typeof v === 'string') return v.trim() ? [v.trim()] : []
  if (Array.isArray(v)) {
    return v.filter((x) => typeof x === 'string' && x.trim()).map((x) => x.trim())
  }
  return []
}

/** 简版收缩：最多 N 条、每句不超过 M 字（超了截断加省略号，不硬凑长句） */
function condenseLines(v, maxLines = TRACE_SUMMARY_MAX_LINES, lineMax = TRACE_SUMMARY_LINE_MAX) {
  return traceLines(v).slice(0, maxLines)
    .map((s) => (s.length > lineMax ? s.slice(0, lineMax) + '…' : s))
}

/**
 * 四段结构的**骨架生成器**：把「部分四段」补成完整四段。
 * 缺的段写成「本次溯源不可用（原因：…）」，不留空、不留 null。
 *
 * @param {object} partial 允许只给若干段（也可给 `${段名}原因` 指定该段的降级原因）；
 *                         另可给 `简版: { 段名: [...] }` 指定该段的结论级短句
 * @param {string} reason  兜底原因
 * @param {string} level   'summary'（默认，每段 ≤2 条短句）｜'full'（完整四段）
 */
export function traceSections(partial, reason, level = 'summary') {
  const out = {}
  const p = partial || {}
  const brief = p['简版'] && typeof p['简版'] === 'object' ? p['简版'] : null
  const isSummary = level !== 'full'
  for (const name of TRACE_SECTIONS) {
    let got
    // 「排除分块」放宽到 4 行 × 60 字：闸账本一闸一行，简版也要能看清每道闸淘汰了多少
    const cap = name === '排除分块'
      ? [TRACE_EXCLUDED_MAX_LINES, TRACE_EXCLUDED_LINE_MAX]
      : [TRACE_SUMMARY_MAX_LINES, TRACE_SUMMARY_LINE_MAX]
    if (isSummary) {
      // 简版：优先用生成器给的结论级短句；没给就从详版里收缩前几条
      got = condenseLines(brief && brief[name], cap[0], cap[1])
      if (!got.length) got = condenseLines(p[name], cap[0], cap[1])
    } else {
      got = traceLines(p[name])
    }
    out[name] = got.length ? got : [traceUnavailable(p[`${name}原因`] || reason)]
  }
  return out
}


/* ───────── 闸账本（TICKET-217 · 方案 C）：读 worker 的实测账本 ＋ 生成排除分块 ＋ 明细落文件 ─────────
 *
 * 为什么要跨进程传一个文件：
 *   淘汰数只有 worker（python 侧，真机调官方库）算得出来 —— 它按闸逐次实测命中总数；
 *   而四段是在视图层（本文件）拼的。两边靠一份**入参指纹命名**的 ledger.json 对接：
 *   同一套入参 → 同一个任务标识 → 同一个目录，并发两个任务的账本不会串号。
 * 纪律：
 *   · 读不到／读坏了／过期了，一律返回 null，由调用方写「本次溯源不可用（缺：…）」；
 *   · **绝不**在这里补任何通过／淘汰数（无账本 = 没有数，不是 0）。
 */

/** 数量写法（业务看得懂）：10000 → 1万；600000 → 60万；8 → 8 */
function fmtCount(n) {
  const v = typeof n === 'number' ? n : Number(n)
  if (!isFinite(v)) return String(n)
  if (v >= 1e8) return String(Number((v / 1e8).toFixed(2))) + '亿'
  if (v >= 1e4) return String(Number((v / 1e4).toFixed(2))) + '万'
  return String(Math.round(v))
}

const strOrNull = (v) => {
  if (v === undefined || v === null || v === '') return null
  const s = String(v).trim()
  return s || null
}
const numOrNull = (v) => {
  if (v === undefined || v === null || v === '') return null
  const n = Number(v)
  return isFinite(n) ? (Number.isInteger(n) ? n : n) : null
}

/**
 * 入参指纹（前 16 位）——**必须**与 `lib/worker.py::roster_args_key()` 逐字符一致：
 * 同 7 个键、字典序、无空格 JSON、缺值写 null。
 */
export function rosterArgsKey(args) {
  const a = args || {}
  const canon = {
    category: strOrNull(a.category),
    country: strOrNull(a.country),
    limit: numOrNull(a.limit) === null ? 10 : numOrNull(a.limit),
    maxSubscribers: numOrNull(a.max_subscribers),
    minSubscribers: numOrNull(a.min_subscribers),
    page: numOrNull(a.page) === null ? 1 : numOrNull(a.page),
    query: String(a.query === undefined || a.query === null ? '' : a.query).trim(),
  }
  return createHash('sha256').update(JSON.stringify(canon), 'utf8').digest('hex').slice(0, 16)
}

/** 任务标识：一个任务一个账本目录 */
export function rosterTaskId(args) {
  return 'roster-' + rosterArgsKey(args)
}

/** 账本根目录：DANIEL_TRACE_DIR 显式覆盖 > <DANIEL_HOME>/out/trace（与 worker.py 同规则） */
export function traceBaseDir() {
  const explicit = strOrNull(process.env.DANIEL_TRACE_DIR)
  if (explicit) return explicit
  const home = strOrNull(process.env.DANIEL_HOME)
  if (home) return join(home, 'out', 'trace')
  const mac = join(homedir(), 'Library', 'Application Support', 'DanielCopilot')
  return existsSync(mac) ? join(mac, 'out', 'trace') : null
}

/**
 * 读本次任务的闸账本：优先用返回体里直接带的（未来 index.js 把字段透传过来时走这条），
 * 否则读 worker 落的 ledger.json。读不到 → null（调用方必须写「缺」，不许编数）。
 */
export function readRosterLedger(args, data) {
  const inline = data && typeof data === 'object' ? data['闸账本'] : null
  if (inline && typeof inline === 'object') return inline
  try {
    const base = traceBaseDir()
    if (!base) return null
    const path = join(base, rosterTaskId(args), 'ledger.json')
    if (!existsSync(path)) return null
    const led = JSON.parse(readFileSync(path, 'utf8'))
    if (!led || typeof led !== 'object') return null
    // 指纹／保鲜期双重校验：防"上一轮同名参数"的旧账本冒充本次
    if (String(led['参数指纹'] || '') !== rosterArgsKey(args)) return null
    const at = Number(led['生成时刻'] || 0)
    if (!at || Date.now() / 1000 - at > LEDGER_TTL_SECONDS) return null
    return led
  } catch {
    return null
  }
}

/** CSV 单元：含逗号／引号／换行就加引号（不改变值的字面） */
function csvCell(v) {
  const s = v === undefined || v === null ? '' : String(v)
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
}

/**
 * 排除明细落文件（>30 位时才铺文件，会话里只给路径）。
 * 落点：`<base>/<任务标识>/excluded.csv`；**绝不**写进插件包目录（命中 vendor/ 直接拒绝）。
 * @returns {{path: string|null, written: boolean, reason: string}}
 */
export function writeExcludedCsv(o) {
  const rows = (o && o.rows) || []
  const taskId = (o && o.taskId) || 'roster-unknown'
  const base = (o && o.base) || traceBaseDir()
  if (!base) return { path: null, written: false, reason: '没有可写的数据目录（DANIEL_HOME 未定位）' }
  const path = join(base, taskId, 'excluded.csv')
  const abs = resolvePath(path)
  if (/[\\/]vendor[\\/]/.test(abs) || /[\\/]daniel-dsh-plugin[\\/](lib|scripts|tests)[\\/]/.test(abs)) {
    return { path: null, written: false, reason: '落点落在插件包目录内，按纪律拒绝写入' }
  }
  try {
    mkdirSync(dirname(abs), { recursive: true })
    const head = EXCLUDED_CSV_COLUMNS.map(csvCell).join(',')
    const body = rows.map((r) => EXCLUDED_CSV_COLUMNS.map((c) => csvCell(
      c === '任务标识' ? (r['任务标识'] || taskId) : r[c],
    )).join(','))
    // BOM：Excel 直接双击打开不乱码（内容本身仍是标准 CSV）
    writeFileSync(abs, '\uFEFF' + [head, ...body].join('\n') + '\n', 'utf8')
    return { path: abs, written: true, reason: '' }
  } catch (e) {
    return { path: null, written: false, reason: String((e && e.message) || e).slice(0, 120) }
  }
}

/**
 * 把闸账本翻成「排除分块」的一段话（详简两层）。
 * 返回 `{ 简版: [...], 全: [...], 有数: boolean }`：
 *   · 有数 = true  → 用的是 worker 的**实测**通过／淘汰数；
 *   · 有数 = false → 只给「缺什么」，一个数字都不给（方案 C 禁止编造）。
 */
export function gateLedgerBlock(o) {
  const ledger = o && o.ledger
  const args = (o && o.args) || {}
  // ① 没账本：明确「缺」，不编数字（简版只说缺什么，解释放详版）
  if (!ledger || typeof ledger !== 'object') {
    const why = '筛选闸记录 —— 官方库只回「这套条件命中多少」，逐闸淘汰数须由执行侧逐闸实测；本次账本未落盘／未启用'
    return {
      有数: false,
      简版: [traceMissing('筛选闸记录')],
      全: [
        traceMissing(why),
        '为什么不给数字：淘汰数只能由「该闸前后的两次实测命中总数」相减得到；拿不到这两个数就写 0 或估算，等于编造',
        '补数据的办法：确认本机数据目录可写（账本落在 <数据目录>/out/trace/<任务标识>/ledger.json）后重跑同一次检索',
      ],
    }
  }

  // ② 账本在，但本次根本没有筛选条件：显式声明「本次无筛选环节」
  const gates = Array.isArray(ledger['闸']) ? ledger['闸'] : []
  const missing = Array.isArray(ledger['缺']) ? ledger['缺'].filter((x) => typeof x === 'string' && x.trim()) : []
  const cand = typeof ledger['候选总数'] === 'number' ? ledger['候选总数'] : null

  /** 账本「空但不可用」的写法：只缺什么写什么，绝不说成"没有筛选环节" */
  const unavailable = (what) => ({
    有数: false,
    简版: [traceMissing(what)],
    全: [
      traceMissing(what),
      ledger['降级'] ? `账本说明：${String(ledger['降级'])}` : '账本说明：本次闸链没能算出可核对的通过／淘汰数',
      '为什么不给数字：淘汰数只能由「该闸前后的两次实测命中总数」相减得到；拿不到这两个数就写 0 或估算，等于编造',
      '补数据的办法：确认本机数据目录可写（账本落在 <数据目录>/out/trace/<任务标识>/ledger.json）后重跑同一次检索',
    ],
  })

  if (!gates.length) {
    // 只有 worker **明确**说"本次闸链为空"（用户没给国家／粉丝区间／品类）才敢这么写；
    // 账本被关掉、探测失败、基线取不到（闸表同样为空）都不算 —— 那属于「不可用」，不是「没有筛选」。
    if (ledger['无筛选环节'] !== true) {
      return unavailable(missing.length ? missing.join('；') : '筛选闸记录')
    }
    return {
      有数: false,
      简版: ['本次无筛选环节：未给国家／粉丝区间／品类，候选全部通过', '淘汰 0（无）'],
      全: [
        `本次无筛选环节：只按检索式取数，未加国家／粉丝区间／品类${cand !== null ? `，候选 ${cand} 位全部通过` : ''}`,
        '淘汰 0（无）：没有执行筛选闸，所以既没有淘汰，也没有"因为某道闸被剔除"的人',
        ledger['降级'] ? `账本说明：${ledger['降级']}` : '账本说明：本次闸链为空（无筛选条件）',
      ],
    }
  }

  const taskId = String(ledger['任务标识'] || rosterTaskId(args))
  const rows = Array.isArray(ledger['排除明细']) ? ledger['排除明细'] : []
  const picked = typeof ledger['入选数'] === 'number' ? ledger['入选数'] : null
  const dropped = typeof ledger['排除合计'] === 'number' ? ledger['排除合计'] : null

  // ③ 逐闸：数量 ＋ 典型例子（≤3）＋ 判据一句话；0 淘汰写「0（无）」
  const brief = []
  const detail = []
  if (dropped !== null && picked !== null && cand !== null) {
    brief.push(`排除合计 ${dropped} 位（候选 ${cand}、入选 ${picked}）`)
    detail.push(`排除合计 ${dropped} 位：候选总数 ${cand} 位（官方库按检索式命中的全部候选）－ 入选 ${picked} 位，逐闸均为实测计数`)
  }
  for (const g of gates) {
    const name = String(g['闸'] || '未命名闸')
    const cut = typeof g['淘汰数'] === 'number' ? g['淘汰数'] : null
    const pass = typeof g['通过数'] === 'number' ? g['通过数'] : null
    const rule = String(g['判据'] || '该闸的业务判据')
    const examples = Array.isArray(g['典型例子']) ? g['典型例子'].filter((x) => typeof x === 'string' && x.trim()).slice(0, 3) : []
    if (cut === null) {
      brief.push(`${name}：淘汰数未取到（不估算）`)
      detail.push(`· ${name}｜淘汰数未取到｜判据：${rule}｜不估算：该闸前后的实测计数没拿到，写任何数字都是编的`)
      continue
    }
    if (cut === 0) {
      brief.push(`${name}：0（无）`)
      detail.push(`· ${name}｜0（无）${pass !== null ? `（通过 ${pass} 位）` : ''}｜判据：${rule}｜本次无一例因该闸淘汰`)
      continue
    }
    brief.push(`${name}：淘汰 ${cut} 位`)
    detail.push(`· ${name}｜淘汰 ${cut} 位${pass !== null ? `（通过 ${pass} 位）` : ''}｜判据：${rule}`
      + (examples.length ? `｜典型：${examples.join('、')}` : '｜典型：本次样本里没有可举例的人'))
  }

  // ④ 明细：>30 位落 CSV，段里给路径（简版给可定位的相对路径，详版给绝对路径）
  const cover = ledger['样本'] && typeof ledger['样本'] === 'object' ? ledger['样本'] : null
  let csv = null
  if (dropped !== null && dropped > EXCLUDED_CSV_THRESHOLD) {
    csv = writeExcludedCsv({ taskId, rows, base: o && o.base })
    if (csv.written) {
      brief.push(`明细 ${rows.length} 位已落文件：${join(taskId, 'excluded.csv')}`)
      detail.push(`排除明细 ${rows.length} 位已落文件（超过 ${EXCLUDED_CSV_THRESHOLD} 位不逐条铺在会话里）：${csv.path}`)
      detail.push(`文件位置：数据目录下的 out/trace/${taskId}/excluded.csv（CSV 带表头，Excel 直接双击可开）`)
      if (cover && typeof cover['取到'] === 'number' && typeof cover['候选总数'] === 'number' && cover['取到'] < cover['候选总数']) {
        detail.push(`明细覆盖：样本 ${cover['取到']} 位／候选 ${cover['候选总数']} 位（其余位只进了闸计数，未逐条列出）`)
      }
    } else {
      brief.push(`明细 ${rows.length} 位未落文件（${csv.reason}）`)
      detail.push(`排除明细 ${rows.length} 位想落文件但没写成：${csv.reason}；闸计数不受影响，明细可重跑一次再取`)
    }
  } else if (rows.length) {
    detail.push(`排除明细 ${rows.length} 位（未超 ${EXCLUDED_CSV_THRESHOLD} 位，不落文件）：`
      + rows.slice(0, 3).map((r) => `${r['红人']}（${r['闸']}）`).join('、')
      + (rows.length > 3 ? ` 等 ${rows.length} 位` : ''))
  }

  // ④-b 详版专属（2026-10-22 总监裁定，按 08 §2.3.3 的既有口径）：排除 >30 位时，
  //    消息里只放「按闸计数（汇总）＋ 前 30 位 ＋ 附表落点」，全量仍在 CSV，不新增导出开关。
  //    简版**不加**：简版「排除分块」有 ≤6 行上限，逐条铺开会把"哪道闸淘汰多少"挤掉。
  if (dropped !== null && dropped > EXCLUDED_CSV_THRESHOLD) {
    const dims = gates.map((g) => {
      const cut = typeof g['淘汰数'] === 'number' ? g['淘汰数'] : null
      return `${g['闸']} ${cut === null ? '未取到' : (cut === 0 ? '0（无）' : `${cut} 位`)}`
    })
    if (dims.length) detail.push(`按闸计数（汇总）：${dims.join('；')}`)
    const top = rows.slice(0, 30)
    const where = csv && csv.written ? '其余见附表' : '其余未落文件，只进了闸计数'
    if (top.length) {
      detail.push(`前 ${top.length} 位（按闸顺序，${where}）：`
        + top.map((r) => `${r['红人'] || '（未命名）'}（${r['闸'] || '未归闸'}）`).join('、')
        + (rows.length < dropped ? `；本次样本共 ${rows.length} 位，另有 ${dropped - rows.length} 位只进了闸计数` : ''))
    } else {
      detail.push('前 30 位：本次没有逐条明细可列（明细未落盘），只给上面的按闸计数')
    }
  }

  // ⑤ 缺项：把没取到的那一道闸点名（方案 C 第三种形态）
  if (missing.length) {
    brief.push(traceMissing(missing.join('；')))
    detail.push(traceMissing(missing.join('；')))
    detail.push('已给出的闸都是实测数；缺的那几道闸一律不给数字（0 也不给，因为"没取到"不等于"没淘汰"）')
  }
  return { 有数: true, 简版: brief, 全: detail }
}

const j = (v, d) => (v === undefined || v === null || v === '' ? d : String(v))

/**
 * 逐工具的四段生成器（本票是**骨架**：只给"从入参和返回体就能确定"的内容）。
 * 真正的闸账本／逐条入选理由／排除分块计数在下一票（TICKET-217）接入，此处不臆造数字。
 *
 * 每个生成器给两份内容：
 *   · 四段本体（详版 full 用）—— 骨架内容 ＋ 更细的表述；
 *   · `简版` 四个键（简版 summary 用）—— 每段 ≤2 条短句，只说结论级信息。
 */
const TRACE_BUILDERS = {
  /** 品牌清单：取数口＋取数条件是可确定的；没做二次筛选就明说没做 */
  daniel_brands_list(ctx) {
    const args = ctx.args || {}
    const data = ctx.data && typeof ctx.data === 'object' ? ctx.data : {}
    const n = typeof data['数量'] === 'number' ? data['数量'] : (Array.isArray(data['品牌']) ? data['品牌'].length : 0)
    const ws = args.workspace ? `工作区 ${args.workspace}` : '未限工作区'
    const limit = args.limit ? `、最多 ${args.limit} 条` : ''
    // 取数时点（关键节点留痕：来源／时点／口径三样都要能在 trace 里对上）：
    // 过去只写「时点看返回体的「数据时点」」，等于把时点推给读者自己找；这里把值本身写进溯源。
    const at = typeof data['数据时点'] === 'string' && data['数据时点'].trim() ? data['数据时点'].trim() : ''
    return {
      简版: {
        筛选逻辑链: [`取数条件：${ws}${limit}`, `取数结果：${n} 个品牌`],
        入选理由: ['清单类只做取数，不逐条判定入选'],
        排除分块: [TRACE_NO_GATE],
        口径假设: ['本清单是取数结果，不构成筛选结论', at ? `取数时点：${at}` : '取数时点：本地索引（返回体未给构建时刻）'],
      },
      筛选逻辑链: [
        '取数口：品牌清单（跨工作区，读本地索引，秒级）',
        `取数条件：${ws}${limit}`,
        `取数结果：返回 ${n} 个品牌`,
        at ? `取数时点：${at}（本地索引构建时刻，不是本次重新抓取）` : '取数时点：本地索引（返回体未给构建时刻，不按「本次实时」讲）',
        '本次未执行二次筛选 —— 清单类只做取数，不做淘汰',
        '取数只读本地索引，不重建索引（重建约 1 分钟起，须你明确同意后才做）',
      ],
      入选理由: [
        `清单内 ${n} 个品牌均按取数口原样返回，未逐条判定入选理由`,
        '要按品类／市场等条件筛，说明条件即可另跑一次筛选类任务（那次会带闸账本）',
        '你没给筛选条件时，"都在清单里"就是唯一判据，这里不替你补造理由',
      ],
      排除分块: [
        `${TRACE_NO_GATE}：品牌清单只做取数，没有任何筛选闸，因此没有"被剔除的人"可列`,
        '也不写"淘汰 0"以外的任何数字 —— 没执行闸就不存在淘汰数，编一个 0 会让人误以为查过了',
      ],
      口径假设: [
        '数据来自本地索引，时点看返回体的「数据时点」',
        '未按品类／市场等条件过滤，因此这份清单不构成筛选结论',
        '条数受入参 limit 约束（未给则按默认条数），不是全量：要全量请调大 limit',
      ],
    }
  },

  /** 官方库检索：检索式与条件原样回引 ＋ **真实闸账本**（逐闸实测，能算的必须算） */
  daniel_roster_search(ctx) {
    const args = ctx.args || {}
    const data = ctx.data && typeof ctx.data === 'object' ? ctx.data : {}
    const n = typeof data['本页条数'] === 'number' ? data['本页条数'] : 0
    const total = typeof data['命中总数'] === 'number' ? data['命中总数'] : '未返回'
    const page = data['页码'] ? String(data['页码']) : '1'
    const ledger = readRosterLedger(args, data)
    const block = gateLedgerBlock({ args, data, ledger })
    const gates = ledger && Array.isArray(ledger['闸']) ? ledger['闸'] : []
    const cand = ledger && typeof ledger['候选总数'] === 'number' ? ledger['候选总数'] : null
    const picked = ledger && typeof ledger['入选数'] === 'number' ? ledger['入选数'] : null

    /* ── 筛选逻辑链：闸链能算就逐闸写出来（每步都是官方库实测计数） ── */
    const chain = []
    if (block.有数 && gates.length) {
      chain.push(`闸链（每步都是官方库实测计数）：候选 ${cand !== null ? cand : '未取到'}`)
      for (const g of gates) {
        const pass = typeof g['通过数'] === 'number' ? g['通过数'] : '未取到'
        chain.push(`${g['闸']} → 通过 ${pass}`)
      }
      if (picked !== null) chain.push(`入选 ${picked} 位（通过全部 ${gates.length} 道闸）`)
    }
    const briefChain = block.有数 && gates.length
      ? [`检索式：${j(args.query, '（未给检索式）')}`, `候选 ${cand !== null ? cand : '未取到'} → 入选 ${picked !== null ? picked : '未取到'}（${gates.length} 道闸）`]
      : [`检索式：${j(args.query, '（未给检索式）')}`, `命中 ${total} 位，本页 ${n} 条`]

    return {
      简版: {
        筛选逻辑链: briefChain,
        入选理由: block.有数 && picked !== null
          ? [`${picked} 位＝通过全部 ${gates.length} 道闸的候选`, '命中不等于入选：入库后仍需按匹配／数据／风险逐人核']
          : [`本页 ${n} 位是官方库按检索式命中的结果`],
        排除分块: block.简版,
        口径假设: ['订阅数／均播取官方库返回值，未外部核验', '状态只有入选／排除两档；报价不参与名单类判断'],
      },
      筛选逻辑链: [
        `检索式：${j(args.query, '（未给检索式）')}`,
        `条件：国家 ${j(args.country, '不限')}；订阅数 ${j(args.min_subscribers, '不限')}–${j(args.max_subscribers, '不限')}；品类 ${j(args.category, '不限')}`,
        '取数来源与时间：YouTube 官方库本次调用返回（不是本地索引或历史名单；重跑同一条件可能得到不同候选）',
        ...(chain.length ? chain : ['闸链：本次没有可用的闸计数（见「排除分块」里缺的是哪一闸）']),
        `分页：第 ${page} 页、本页 ${n} 条；命中总数 ${total}`,
        `换条件会改变候选集：本次共 ${n} 条是"这套检索式＋这组条件"下的结果，不是全部合适的人`,
      ],
      入选理由: [
        block.有数 && picked !== null
          ? `${picked} 位＝官方库按检索式命中、且通过全部 ${gates.length} 道闸的那批，原样呈现`
          : `本页 ${n} 位候选是官方库按检索式与条件命中的结果，原样呈现`,
        '逐人入选理由（匹配／数据／风险）由 Agent 按返回体逐条写；本层只给能对上的闸与数',
        '命中不等于入选：官方库按相关度排序，不代表已按你的业务判据筛过',
      ],
      排除分块: block.全,
      口径假设: [
        '闸顺序固定为国家 → 粉丝区间 → 品类；每闸淘汰数＝该闸前后两次**实测**命中总数之差（不是比例推算）',
        '状态只有入选／排除两档；受众数据缺失只标注、不判状态；报价不参与名单类判断',
        '订阅数／中位播放取官方库返回值，未做外部交叉核验',
        '检索式措辞会改变命中范围：换说法可能得到不同候选集',
        '分页取数只覆盖当前页；要全量结论需翻完再判',
      ],
    }
  },

  /** 单点查询：明确写"不是名单、不涉及入选判定"，避免被误读成筛选结论 */
  daniel_kol_profile(ctx) {
    const args = ctx.args || {}
    const data = ctx.data && typeof ctx.data === 'object' ? ctx.data : {}
    const known = ['频道', '表现_近28天', '受众', '近期视频'].filter((k) => data[k] !== undefined)
    const miss = Array.isArray(data['未取到']) ? data['未取到'] : []
    // 两类缺失分开报（TICKET-233）：平台未收录 ≠ 本次未取到，处理动作完全不同
    const notCovered = Array.isArray(data['平台未收录']) ? data['平台未收录'] : []
    return {
      简版: {
        筛选逻辑链: [`单点查询：按 handle 取「${j(args.handle, '（未给 handle）')}」的完整档案`, '不做候选筛选'],
        入选理由: ['单点查询，不涉及入选判定'],
        排除分块: (miss.length || notCovered.length)
          ? [TRACE_NO_GATE,
             ...(miss.length ? [`本次未取到：${miss.join('、')}（可重试/补采，只标注不判状态）`] : []),
             ...(notCovered.length ? [`平台未收录：${notCovered.join('、')}（平台本来就没有，重试无意义）`] : [])]
          : [TRACE_NO_GATE],
        口径假设: ['表现与受众为近 28 天窗口'],
      },
      筛选逻辑链: [
        `单点查询：按 handle「${j(args.handle, '（未给 handle）')}」直接取该频道完整档案，不做候选筛选`,
        known.length ? `本次取到的块：${known.join('／')}` : '本次没有取到任何数据块',
        '取数来源与时间：本次调用直连（频道档案／近 28 天表现／受众／近期视频），不落数据快照',
        '一块一块取全（频道／表现／受众／近期视频），缺块在下一条里点名，不静默省略',
      ],
      入选理由: ['本次是单点查询，不是名单，不涉及入选判定'],
      排除分块: [
        `${TRACE_NO_GATE}：单点查询没有候选池，也就没有"被剔除的人"可列`,
        '单个红人档案不判入选／排除：状态两档只用在名单类结果上',
        // 数据块没取到：按既有口径落在**排除块的原因列**里写清楚（不新增第三种块、不新增字段）。
        ...(miss.length
          ? [`本次未取到：${miss.join('、')} —— 已在返回体「未取到」标注；可重试/补采，按口径只标注、不判状态`]
          : []),
        ...(notCovered.length
          ? [`平台未收录：${notCovered.join('、')} —— 平台侧本来就没有这份数据，重试无意义；改用替代信号（均播／互动率／内容分类）判断`]
          : []),
      ],
      口径假设: [
        '表现与受众为近 28 天窗口的口径',
        miss.length ? `未取到的项：${miss.join('、')}（已在返回体「未取到」标注，不因此判定为不可用）` : '本次各项数据均已取到',
        '数据缺失不改变结论性质：缺哪块说哪块，不用推算值顶替',
        '受众数据缺失只标注、不判状态；报价不参与名单类判断',
      ],
    }
  },

  /** 批量只读：执行的命令清单原样列出；闸记录在执行侧，本层不编任何淘汰数 */
  daniel_batch(ctx) {
    const args = ctx.args || {}
    const data = ctx.data && typeof ctx.data === 'object' ? ctx.data : {}
    const calls = Array.isArray(args.calls) ? args.calls : []
    const results = Array.isArray(data.results) ? data.results : []
    const okN = results.filter((r) => r && r.ok).length
    const failN = results.length - okN
    return {
      简版: {
        筛选逻辑链: [`本次执行 ${calls.length} 条只读命令`, `成功 ${okN} 条、失败 ${failN} 条`],
        入选理由: ['批量直通，不涉及入选判定'],
        排除分块: [traceMissing(TRACE_EXECUTOR_SIDE)],
        口径假设: ['各条命令沿用自身取数口径'],
      },
      筛选逻辑链: [
        `本次执行 ${calls.length} 条只读命令：${calls.map((c) => (Array.isArray(c) ? c.join(' ') : String(c))).join('；')}`,
        `逐条结果：成功 ${okN} 条、失败 ${failN} 条`,
        '取数来源与时间：本次调用直通（每条命令的时点以它自己的返回体为准，本层不统一改写）',
        '批量直通：每条命令的结果原样返回，未叠加筛选',
        '不做顺序依赖：每条命令独立跑，一条失败不影响其它条',
      ],
      入选理由: [
        '批量只读直通，结果按命令原样给出，不涉及入选判定',
        '哪条没取到，就在那条里写明「未取到」，不用其它条的数据代替',
      ],
      排除分块: [
        traceMissing(TRACE_EXECUTOR_SIDE),
        '为什么不给数字：这里跑的是「别人已经做完的取数命令」，筛选发生在执行侧，宿主侧看不到闸前后的命中数',
        failN
          ? `另外：本次有 ${failN} 条命令没成功（见返回体 results 里 ok 为 false 的条目）—— 这是取数失败，不是名单淘汰，两件事不要混`
          : '另外：本次没有失败命令；但"没有失败"不等于"没有淘汰"，淘汰数仍以执行侧记账为准',
      ],
      口径假设: [
        '各条命令沿用其自身的取数口径（如索引时点／实时接口），本层不二次改写',
        '条目里带的时点／窗口都以那条命令自己的为准，不互相拉平',
      ],
    }
  },

  /** 只读直通：单条命令，可确定的只有"跑了什么"；闸记录同样在执行侧 */
  daniel_run(ctx) {
    const args = ctx.args || {}
    const argv = Array.isArray(args.argv) ? args.argv.map(String) : []
    const cmd = argv.join(' ') || '（空）'
    return {
      简版: {
        筛选逻辑链: [`只读命令：${cmd.length > 24 ? cmd.slice(0, 24) + '…' : cmd}`, '结果原样返回，未叠加筛选'],
        入选理由: ['单条命令直通，不涉及入选判定'],
        排除分块: [traceMissing(TRACE_EXECUTOR_SIDE)],
        口径假设: ['口径沿用该命令自身'],
      },
      筛选逻辑链: [
        `本次执行只读命令：${cmd}`,
        '取数来源与时间：本次调用直通（以该命令返回体里的时点为准，本层不改写）',
        '只读直通：命令结果原样返回，未叠加筛选',
        '写命令一律不走这条链（要写请走 daniel_write_plan → daniel_write_commit）',
      ],
      入选理由: [
        '单条命令直通，不涉及入选判定',
        '结果里有什么就给什么，缺失项用文字说明「未取到」，不补 null、不补推测值',
      ],
      排除分块: [
        traceMissing(TRACE_EXECUTOR_SIDE),
        '为什么不给数字：直通命令的筛选是执行侧做的，宿主侧拿不到闸前后的命中数；写 0 会被读成"确认没淘汰"，所以只写缺什么',
      ],
      口径假设: [
        '数据口径沿用该命令自身（如索引时点／实时接口、统计窗口）',
        '命令参数决定取数范围：换参数就是换范围，本层不改写命令语义',
      ],
    }
  },
}

/**
 * 取某工具的四段（对外唯一入口）：**永不抛错**。
 * 无生成器／生成器抛错／某段产不出 → 该段降级成「本次溯源不可用（原因：…）」。
 * @param {string} tool 工具名
 * @param {{args?: object, data?: object, mode?: string}} ctx mode 决定详简两层
 */
export function buildTraceSections(tool, ctx) {
  const level = traceLevelOf((ctx || {}).mode)
  const builder = TRACE_BUILDERS[tool]
  if (!builder) return traceSections({}, '该工具不在四段强制名单内，暂不产出溯源', level)
  let partial = {}
  try {
    partial = builder(ctx || {}) || {}
  } catch (e) {
    return traceSections({}, `四段生成过程出错（${String((e && e.message) || e).slice(0, 60)}），已降级`, level)
  }
  return traceSections(partial, '本次无可确定的口径信息', level)
}
