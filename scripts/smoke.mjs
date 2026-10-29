/**
 * 自包含自检（不需要 DSH）：用假 ctx 注册工具，并真调到插件包内 vendor 的 Daniel。
 * 用法：node scripts/smoke.mjs [--call daniel_status|daniel_write_plan ...]
 */
import { apply } from '../lib/index.js'

const reg = []
apply({ tools: { register: (t) => reg.push(t) } }, { python: 'python3', timeoutMs: 180000 })
console.log('注册工具（%d）:', reg.length)
for (const t of reg) console.log('  -', t.name, '｜params:', Object.keys(t.parameters?.properties || {}).join(',') || '(无)')

const which = process.argv[3] || 'daniel_status'
const t = reg.find((x) => x.name === which)
if (!t) { console.error('未找到工具', which); process.exit(1) }

let args = {}
if (which === 'daniel_skills_read') args = { skill: 'kol-screening', section: 1 }
if (which === 'daniel_brands_list') args = { limit: 3 }
if (which === 'daniel_run') args = { argv: ['brands', 'show', '--brand', '3690002'] }
// 追问闸（TICKET-218）：纯函数、不取数，可以直接这样真调一次
if (which === 'daniel_clarify') args = { need: process.argv[4] || '帮我找一批测评红人' }
if (which === 'daniel_write_plan') args = { argv: (process.argv[4] || 'brands,update,--brand,3690002,--description,插件自检试运行').split(',') }

const out = await t.execute(args, {})
console.log('\n调用', which, '→ exitCode=', out.exitCode, 'ok=', out.ok)
console.log(JSON.stringify(out).slice(0, 900))
process.exit(0)
