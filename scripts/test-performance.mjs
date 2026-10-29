#!/usr/bin/env node
/**
 * 表现块口径回归（TICKET-230／231 的正控）
 *
 * 验的是「插件给用户的数 = Daniel 详情抽屉里的数」，用三个真实样本的**原始视频列表**
 * 当夹具（`tests/fixtures/performance/*.json`，取自 TICKET-229 的直连返回，未加工）。
 *
 * 判据（逐条可复算，来源 `.kol-tools/daniel_ui_parity.py::video_list_stats`）：
 *   P1 长视频样本 = VIDEO_ON_DEMAND 且 views>=100
 *   P2 短视频样本 = SHORTS，无播放阈值
 *   P3 窗口：28 天内 >=3 条用这批，否则退回最新 30 条
 *   P4 平均播放/点赞取**中位数**，偶数取上中位
 *   P5 视频列表拿不到时才退回 insight（均值口径），并标明口径不同
 *
 * 用法：node scripts/test-performance.mjs
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { kolFullView } from '../lib/normalize.js'

const HERE = dirname(fileURLToPath(import.meta.url))
const FIX = join(HERE, '..', 'tests', 'fixtures', 'performance')
const load = (n) => JSON.parse(readFileSync(join(FIX, n + '.json'), 'utf8'))

let pass = 0
const fails = []
const ok = (cond, label, detail = '') => {
  if (cond) { pass++; console.log(`[PASS] ${label}${detail ? ' —— ' + detail : ''}`) }
  else { fails.push(label); console.log(`[FAIL] ${label}${detail ? ' —— ' + detail : ''}`) }
}
const block = (view, label) => (view.表现_近28天 || []).find((b) => b.范围 === label) || null

/** 独立复算：同一批视频按页面规则（VOD>=100 / 28 天 / 中位数） */
function expect(fx) {
  const now = Date.now()
  const W = 672 * 60 * 60 * 1000
  const vod = fx.filter((v) => v.contentType === 'VIDEO_ON_DEMAND' && Number(v.views || 0) >= 100)
  const shorts = fx.filter((v) => v.contentType === 'SHORTS')
  const pick = (s) => {
    const r = s.filter((v) => v.publishTime && now - Date.parse(v.publishTime) <= W)
    return r.length >= 3 ? r : s.slice(0, 30)
  }
  const med = (arr) => {
    const d = arr.filter((x) => x > 0).sort((a, b) => a - b)
    return d.length ? d[Math.floor(d.length / 2)] : 0
  }
  return {
    vodMedian: med(pick(vod).map((v) => Number(v.views || 0))),
    vodCount: pick(vod).length,
    shortsMedian: med(pick(shorts).map((v) => Number(v.views || 0))),
    shortsCount: pick(shorts).length,
  }
}

const fmt = (n) => (n >= 1e8 ? (n / 1e8).toFixed(2) + ' 亿' : n >= 1e4 ? (n / 1e4).toFixed(1) + ' 万' : String(Math.round(n * 100) / 100))

// ── 三个真实样本：插件输出 vs 页面口径独立复算 ─────────────────
for (const name of ['watsons', 'able', 'lymow']) {
  const fx = load(name)
  const view = kolFullView({ raw: { detail: { title: name }, insight: null, videos: fx.slice(0, 5), videosAll: fx } })
  const e = expect(fx)
  const vod = block(view, '长视频')
  const shorts = block(view, '短视频')
  ok(!!(view.表现_近28天 || []).length, `P0 ${name}：表现块存在（不再整块缺失）`)
  ok(vod && vod.平均播放 === e.vodMedian, `P1/P4 ${name}：长视频平均播放=${e.vodMedian}（精确值）`, vod ? `实际 ${vod.平均播放}` : '无长视频块')
  ok(shorts && shorts.平均播放 === e.shortsMedian, `P2/P4 ${name}：短视频平均播放=${e.shortsMedian}（精确值）`, shorts ? `实际 ${shorts.平均播放}` : '无短视频块')
  ok(!!(vod && vod.视频数 === e.vodCount), `P1 ${name}：长视频样本数=${e.vodCount}`, vod ? `实际 ${vod.视频数}` : '—')
  ok(!view.未取到 || !view.未取到.includes('表现数据'), `P0 ${name}：未取到里不再出现「表现数据」`)
  ok(!!(vod && /样本 \d+ 条/.test(vod.样本 || '')), `样本量写明 ${name}`, vod ? vod.样本 : '—')
}

// ── P3：28 天内不足 3 条 → 退回最新 30 条 ───────────────────
{
  const old = Date.now() - 90 * 24 * 3600 * 1000
  const fx = Array.from({ length: 6 }, (_, i) => ({
    contentType: 'VIDEO_ON_DEMAND', views: 1000 + i * 1000, likes: 10, comments: 1,
    publishTime: new Date(old - i * 86400000).toISOString(),
  }))
  const v = kolFullView({ raw: { detail: {}, insight: null, videos: fx, videosAll: fx } })
  const vod = block(v, '长视频')
  ok(!!(vod && vod.样本.startsWith('最新30条')), 'P3：28 天内 <3 条时退回最新 30 条', vod ? vod.样本 : '—')
  ok(!!(vod && vod.平均播放 === 4000), 'P3：回退后取上中位（6 条 1000…6000 → 第 4 小 = 4000）', vod ? vod.平均播放 : '—')
}

// ── P5：视频列表为空 → insight 兜底，且标明口径不同 ────────────
{
  const insight = { stats: { overall: { videoCount: 10, views: 50000, averageViewsPerVideo: 5000, averageLikesPerVideo: 200, engagementRate: 0.04, uniqueViewers: 40000 } } }
  const v = kolFullView({ raw: { detail: {}, insight, videos: null, videosAll: null } })
  const b = block(v, '整体')
  ok(!!b, 'P5：无视频列表时仍有表现块（走 insight 兜底）')
  ok(!!(b && b.平均播放 === 5000), 'P5：兜底用的是 insight 均值', b ? b.平均播放 : '—')
  ok(!!(b && /均值口径/.test(b.样本 || '')), 'P5：兜底块标明「均值口径，非页面口径」', b ? b.样本 : '—')
}

// ── 互动率：页面公式 (Σlikes+Σcomments)/Σviews ───────────────
{
  const fx = load('watsons')
  const vod = fx.filter((x) => x.contentType === 'VIDEO_ON_DEMAND' && Number(x.views || 0) >= 100)
  const views = vod.reduce((s, x) => s + Number(x.views || 0), 0)
  const likes = vod.reduce((s, x) => s + Number(x.likes || 0), 0)
  const comments = vod.reduce((s, x) => s + Number(x.comments || 0), 0)
  const want = ((likes + comments) / views * 100).toFixed(2) + '%'
  const v = kolFullView({ raw: { detail: {}, insight: null, videos: fx, videosAll: fx } })
  const b = block(v, '长视频')
  ok(!!(b && b.互动率 === want), `互动率按页面公式（长视频=${want}）`, b ? `实际 ${b.互动率}` : '—')
}

console.log('')
console.log(`合计：PASS ${pass} / FAIL ${fails.length}`)
if (fails.length) { console.log('未通过：\n  - ' + fails.join('\n  - ')); process.exit(1) }
