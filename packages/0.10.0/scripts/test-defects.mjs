#!/usr/bin/env node
/**
 * 缺陷回归（TICKET-233／234／235／236）—— 每条对应一个真实用户可见问题
 *
 *   D233 缺块语义：平台未收录 ≠ 本次未取到（且要给替代信号）
 *   D234 精度：表现块给精确整数、互动率 2 位小数（能跟页面逐格对）
 *   D235 写链干跑：影响范围里不得出现英文字段名
 *   D236 落点不可写：<2 秒失败并给修法，不许先建 74 秒索引
 *
 * 用法：node scripts/test-defects.mjs
 */
import { readFileSync, mkdtempSync, mkdirSync, chmodSync, rmSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { tmpdir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { kolFullView, planView } from '../lib/normalize.js'

const HERE = dirname(fileURLToPath(import.meta.url))
const PKG = join(HERE, '..')
const fx = JSON.parse(readFileSync(join(PKG, 'tests/fixtures/performance/watsons.json'), 'utf8'))

let pass = 0
const fails = []
const ok = (cond, label, detail = '') => {
  if (cond) { pass++; console.log(`[PASS] ${label}${detail ? ' —— ' + detail : ''}`) }
  else { fails.push(label); console.log(`[FAIL] ${label}${detail ? ' —— ' + detail : ''}`) }
}

// ── D233：两类缺失分开 ─────────────────────────────────────
{
  const v1 = kolFullView({ raw: { detail: { title: 'x' }, insight: null, insightStatus: 'empty', videos: fx.slice(0, 5), videosAll: fx } })
  ok(Array.isArray(v1.平台未收录) && v1.平台未收录.some((s) => s.includes('受众')), 'D233a：接口返回空 → 记「平台未收录」', JSON.stringify(v1.平台未收录))
  ok(!v1.未取到 || !v1.未取到.some((s) => s.includes('受众')), 'D233a：「平台未收录」不再混进「未取到」')
  ok(Array.isArray(v1.替代信号) && v1.替代信号.length > 0, 'D233b：给了替代信号', v1.替代信号 ? v1.替代信号[0].slice(0, 40) + '…' : '无')

  const v2 = kolFullView({ raw: { detail: { title: 'x' }, insight: null, insightStatus: 'error', videos: fx.slice(0, 5), videosAll: fx } })
  ok(Array.isArray(v2.未取到) && v2.未取到.includes('受众数据'), 'D233c：取数失败 → 记「本次未取到」', JSON.stringify(v2.未取到))
  ok(!v2.平台未收录 || !v2.平台未收录.some((s) => s.includes('受众')), 'D233c：失败不再被写成「平台没有」')
}

// ── D234：精确数值 + 2 位小数 ───────────────────────────────
{
  const v = kolFullView({ raw: { detail: { title: 'x' }, insight: null, videos: fx.slice(0, 5), videosAll: fx } })
  const vod = (v.表现_近28天 || []).find((b) => b.范围 === '长视频')
  ok(!!(vod && Number.isInteger(vod.平均播放)), 'D234a：平均播放是整数（不再压成「万」）', vod ? String(vod.平均播放) : '—')
  ok(!!(vod && /^\d+\.\d{2}%$/.test(vod.互动率 || '')), 'D234b：互动率 2 位小数', vod ? vod.互动率 : '—')
  const raw = fx.filter((x) => x.contentType === 'VIDEO_ON_DEMAND' && Number(x.views || 0) >= 100)
  ok(!!(vod && raw.some((x) => Number(x.views) === vod.平均播放)), 'D234c：该数值能在原始返回里精确找到（就等于某条视频的 views 中位）')
}

// ── D235：影响范围里不出现英文字段名 ────────────────────────
{
  const view = planView({ impact: '修改品牌「Lymow」的 1 个字段：description：「旧简介」→「新简介」；其余字段不动', targetName: 'Lymow' }, 'brands.update')
  ok(!!(view && /简介/.test(view.影响范围)), 'D235a：影响范围用业务词「简介」', view ? view.影响范围.slice(0, 50) : '—')
  ok(!!(view && !/description|industryKeywords|sampleCost/.test(view.影响范围)), 'D235b：影响范围 0 处英文字段名')
}

// ── D236：落点不可写 → 快速失败（<2s），不先建索引 ──────────
{
  const base = mkdtempSync(join(tmpdir(), 'd236-'))
  const ro = join(base, 'ro-home')
  mkdirSync(ro, { recursive: true })
  chmodSync(ro, 0o555)                     // 只读：能进、不能建
  const t0 = Date.now()
  const r = spawnSync('python3', [join(PKG, 'lib', 'worker.py')], {
    input: JSON.stringify({ id: 1, op: 'brands', args: { limit: 3 } }) + '\n',
    encoding: 'utf8',
    timeout: 60_000,
    env: { ...process.env, DANIEL_HOME: ro },
  })
  const ms = Date.now() - t0
  let resp = null
  try { resp = JSON.parse((r.stdout || '').trim().split('\n')[0]) } catch { /* 保持 null */ }
  ok(ms < 2000, 'D236a：落点不可写时 <2 秒失败', `${ms} ms`)
  ok(!!(resp && resp.ok === false && /数据落点不可写/.test(resp.error?.message || '')), 'D236b：明确说「数据落点不可写」并给修法', resp?.error?.message?.slice(0, 60) || '无响应')
  chmodSync(ro, 0o755)
  rmSync(base, { recursive: true, force: true })
}

console.log('')
console.log(`合计：PASS ${pass} / FAIL ${fails.length}`)
if (fails.length) { console.log('未通过：\n  - ' + fails.join('\n  - ')); process.exit(1) }
