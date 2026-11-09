/**
 * P0 基线固化 · 输出结构快照采集器
 *
 * 做什么：用**假 ctx** 注册插件全部工具（注册数见基线 registeredCount），按 `cases.mjs` 的用例逐个真调，
 * 把每次返回体的**结构**（字段树 ＋ 类型 ＋ 数组长度 ＋ 契约键取值）存成快照。
 * 不存业务值——快照要能进仓库、能长期 diff，不能带账号、品牌名、正文这类数据。
 *
 * 用法：
 *   node tests/golden/capture.mjs                     # 打印快照到标准输出
 *   node tests/golden/capture.mjs --out tests/golden/baseline.json
 *   node tests/golden/capture.mjs --trace off|summary|full   # 指定 trace 档位（默认 off）
 *
 * 基线更新（**唯一**允许改基线的入口，机械执行「只重采指定工具的用例」这条纪律）：
 *   node tests/golden/capture.mjs --update tests/golden/baseline.json \
 *        --only daniel_run,daniel_batch --reason "TICKET-220 缺陷修复：出口过 prune()"
 *   · 未列进 --only 的用例**原样保留**，并打印逐条 sha256 审计；
 *   · 工具签名（工具数/参数表）有任何变化 → 拒绝写入（那不是"用例更新"，得走契约评审）；
 *   唯一例外（TICKET-218 起）：本票**新增工具**时，用 `--accept-new-tool <新工具名>`
 *     显式声明「这次签名变化是加了一个已过契约评审的新工具」。该开关只放行**纯追加**：
 *     既有工具的参数表必须逐字节不变、注册数只能多加 --accept-new-tool 列的个数，
 *     且新工具必须同时在 --only 里；任何一条不满足仍拒绝写入。
 *   · 每次更新都追加进 baselineUpdates 审计账（时间／工具／原因／动了哪几条／签名变化）。
 *
 * 注意：
 *   · 快照里唯一带值的是契约键 `ok / exitCode / kind`（这三者是行为约定，必须可比）；
 *   · 每个用例另存 `sha256`——用于 diff 的「字节层」比对（`trace=off` 时须与基线一致）；
 *   · 采集时就地校验「返回体不含 null/undefined」（宿主会报 not lossless JSON）。
 */
import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { apply } from '../../lib/index.js'
import { CASES, SKIPPED } from './cases.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))

/** 契约键：这三者的**值**属于行为约定，必须进快照 */
const VALUE_KEYS = new Set(['ok', 'exitCode', 'kind'])

/**
 * 结构快照：递归成「类型树」。
 *   object → { t:'object', props: {键: 子结构} }（键按字典序，与插入顺序无关）
 *   array  → { t:'array', len: 长度, item: 合并后的元素结构 }
 *   string → { t:'string' }（契约键记值：{ t:'string', v:'usage' }）
 */
export function shapeOf(v, key) {
  if (v === null) return { t: 'null' }
  if (v === undefined) return { t: 'undefined' }
  if (Array.isArray(v)) {
    const items = v.map((x) => shapeOf(x, key))
    const item = items.length ? items.reduce(mergeShape) : { t: 'none' }
    return { t: 'array', len: v.length, item }
  }
  const ty = typeof v
  if (ty === 'object') {
    const props = {}
    for (const k of Object.keys(v).sort()) {
      // undefined 属性会被 JSON.stringify 丢掉 —— 模型/宿主看不到它，不算契约的一部分
      if (v[k] === undefined) continue
      props[k] = shapeOf(v[k], k)
    }
    return { t: 'object', props }
  }
  if (VALUE_KEYS.has(key) && (ty === 'string' || ty === 'number' || ty === 'boolean')) return { t: ty, v }
  return { t: ty }
}

/** 数组合并：元素结构不同（混合类型/不同键）时合成为一个结构，顺带把差异摊平 */
function mergeShape(a, b) {
  if (JSON.stringify(a) === JSON.stringify(b)) return a
  if (a.t === 'object' && b.t === 'object') {
    const props = {}
    for (const k of Array.from(new Set([...Object.keys(a.props), ...Object.keys(b.props)])).sort()) {
      if (a.props[k] && b.props[k]) props[k] = mergeShape(a.props[k], b.props[k])
      else props[k] = a.props[k] || b.props[k]
    }
    return { t: 'object', props }
  }
  if (a.t === 'array' && b.t === 'array') {
    return { t: 'array', len: Math.max(a.len, b.len), item: (a.len && b.len) ? mergeShape(a.item, b.item) : a.item }
  }
  if (a.t === b.t) return { t: a.t }
  return { t: 'union', of: Array.from(new Set([a.t, b.t])).sort() }
}

/**
 * 返回体里不许有 null（宿主会报 not lossless JSON）：返回第一条违规路径，没有则 null。
 * 口径：
 *   · 对象里的 `undefined` 属性 → **不算违规**（JSON.stringify 会直接丢掉它，宿主看不到）；
 *   · 数组里的 `undefined` 元素 → **算违规**（序列化成 null 后同样会炸）；
 *   · `null` 一律算违规。
 */
export function firstNullPath(v, path = '$', inArray = false) {
  if (v === null) return path
  if (v === undefined) return inArray ? path : null
  if (Array.isArray(v)) {
    for (let i = 0; i < v.length; i += 1) {
      const p = firstNullPath(v[i], `${path}[${i}]`, true)
      if (p) return p
    }
    return null
  }
  if (typeof v === 'object') {
    for (const [k, val] of Object.entries(v)) {
      const p = firstNullPath(val, `${path}.${k}`, false)
      if (p) return p
    }
  }
  return null
}

/**
 * 工具参数元信息：工具名／参数名／参数类型一个都不许改，这里固化下来。
 * 注意 `defineTool` 会把 `parameters` 规范化成 JSON-Schema 形状
 * （`{ type:'object', properties:{…}, required:[…] }`），因此要下钻到 properties。
 */
export function toolMeta(reg) {
  const out = {}
  for (const t of reg) {
    const p = t.parameters || {}
    const props = (p && p.properties) || {}
    const req = Array.isArray(p && p.required) ? p.required : []
    out[t.name] = {
      params: Object.keys(props).sort().map((n) => ({
        n,
        t: String(props[n].type || ''),
        req: req.includes(n),
        items: props[n].items ? String(props[n].items.type || '') : '',
      })),
    }
  }
  return out
}

/**
 * 路径归一化：把**绝对路径**替换成 `<PATH>`，让基线**机器无关**。
 *
 * 为什么放在采集层而不是产品输出：
 *   · 产品该给用户看的绝对路径（如语料根）不该为了测试被抹掉；
 *   · 但基线一旦写进某台机器的 `/Users/...`，换机器/换目录/换分支就必红（M3 实测：
 *     `run_skills_list` 在 M3 之前就是红的，`batch_skills_list` 因 DANIEL_BIN 换目录而红）。
 * 归一化只作用于**快照**（shape 与 sha），不改任何工具返回值。
 */
const WORKSPACE = resolve(HERE, '..', '..', '..', '..')
const ABS_PATH = /\/(?:Users|home|opt|private|var|tmp|Volumes)\/[^\s"'`，。；、)\]}]+/g

export function normalizePaths(v) {
  if (typeof v === 'string') {
    // ① 语料根（绝对或相对、任何包名）整体归一：`…/mcp/corpus` → `<PATH>`
    let out = v.replace(/[^\s"'`：]*\/mcp\/corpus/g, '<PATH>')
    // ② 其余绝对路径（含工作区根）→ `<PATH>`
    out = out.split(WORKSPACE).join('<PATH>').replace(ABS_PATH, '<PATH>')
    return out
  }
  if (Array.isArray(v)) return v.map(normalizePaths)
  if (v && typeof v === 'object') {
    const out = {}
    for (const [k, x] of Object.entries(v)) out[k] = normalizePaths(x)
    return out
  }
  return v
}

function argOf(name, fallback) {
  const i = process.argv.indexOf(name)
  return i >= 0 ? process.argv[i + 1] : fallback
}

/** 采集快照（纯函数式：返回快照对象，不落盘） */
export async function capture(traceMode = 'off') {
  const reg = []
  apply({ tools: { register: (t) => reg.push(t) } }, { python: 'python3', timeoutMs: 20000, trace: traceMode })

  const snapshot = {
    schemaVersion: 1,
    registeredCount: reg.length,
    toolMeta: toolMeta(reg),
    cases: {},
    skipped: {},
  }

  for (const c of CASES) {
    const t = reg.find((x) => x.name === c.tool)
    if (!t) throw new Error(`用例 ${c.id}: 工具 ${c.tool} 没有注册`)
    const out = await t.execute(c.args, {})
    const nullPath = firstNullPath(out)
    if (nullPath) throw new Error(`用例 ${c.id}: 返回体含 null/undefined（${nullPath}），宿主会报 not lossless JSON`)
    // 快照层做路径归一化：绝对路径 → `<PATH>`（产品返回值不变，基线机器无关）
    const normalized = normalizePaths(out)
    snapshot.cases[c.id] = {
      tool: c.tool,
      args: c.args,
      offline: Boolean(c.offline),
      shape: shapeOf(normalized, '$'),
      sha256: createHash('sha256').update(JSON.stringify(normalized)).digest('hex'),
    }
  }

  for (const s of SKIPPED) {
    if (!reg.find((x) => x.name === s.tool)) throw new Error(`跳过的工具 ${s.tool} 竟然没有注册（工具名被改过？）`)
    snapshot.skipped[s.tool] = { reason: s.reason, detail: s.detail }
  }
  snapshot.coverage = { called: Object.keys(snapshot.cases).length, skipped: Object.keys(snapshot.skipped).length, tools: reg.length }
  return snapshot
}

/* ── CLI ─────────────────────────────────────────────────── */
if (process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  const traceMode = String(argOf('--trace', 'off'))
  const out = argOf('--out', '')
  const update = argOf('--update', '')          // 就地更新基线（**必须**配 --only，见下）
  const only = String(argOf('--only', '')).split(',').map((s) => s.trim()).filter(Boolean)
  const reason = String(argOf('--reason', '未注明原因（基线只允许因缺陷修复而局部更新）'))
  /* 新增工具的签名变化许可口（见文件头）：只放行「纯追加」，不放行任何改签名 */
  const acceptNew = String(argOf('--accept-new-tool', '')).split(',').map((s) => s.trim()).filter(Boolean)

  if (update) {
    /* 基线更新纪律的机械保障：**只**重采 --only 列出的工具的用例，其余用例原样保留，
     * 并把这次更新记进 baselineUpdates 审计账（谁、什么时候、因为什么、动了几条）。 */
    if (!only.length) {
      console.error('拒绝执行：--update 必须同时给 --only <工具名,工具名>（防止顺手全量重采把基线洗白）')
      process.exit(2)
    }
    const path = resolve(process.cwd(), update)
    const old = JSON.parse(readFileSync(path, 'utf8'))
    const fresh = await capture(traceMode)
    const sha = (c) => (c && c.sha256 ? String(c.sha256).slice(0, 12) : '—')
    const mergedCases = {}
    const audit = []
    const order = [...Object.keys(old.cases), ...Object.keys(fresh.cases).filter((id) => !old.cases[id])]
    for (const id of order) {
      const before = old.cases[id]
      const after = fresh.cases[id]
      const tool = (after && after.tool) || (before && before.tool) || ''
      if (after && only.includes(tool)) {
        mergedCases[id] = after
        audit.push({ 用例: id, 工具: tool, 更新前: sha(before), 更新后: sha(after), 结论: before ? (before.sha256 === after.sha256 ? '重采后一致' : '已更新（有意）') : '新增用例' })
      } else if (before) {
        mergedCases[id] = before
        if (only.includes(tool)) audit.push({ 用例: id, 工具: tool, 更新前: sha(before), 更新后: '（保留）', 结论: '该工具用例已不在用例表，保留旧基线待人工裁决' })
      }
    }
    /* 工具签名（登记数/参数表）不许在"用例更新"里被悄悄改掉。
     * 例外：`--accept-new-tool` 显式声明的**纯追加**（本票新增工具）。判据四条全都要满足：
     *   ① 既有工具一个都没少，且每个参数表逐字节不变；
     *   ② 多出来的工具名恰好等于 --accept-new-tool 列的名字（不多不少）；
     *   ③ 注册数的增量恰好等于新增工具个数；
     *   ④ 这些新工具同时出现在 --only 里（否则它们的用例根本没被重采）。 */
    const signatureChanged =
      JSON.stringify(old.toolMeta) !== JSON.stringify(fresh.toolMeta)
      || old.registeredCount !== fresh.registeredCount
    const oldNames = Object.keys(old.toolMeta || {})
    const freshNames = Object.keys(fresh.toolMeta || {})
    const added = freshNames.filter((n) => !oldNames.includes(n))
    const removed = oldNames.filter((n) => !freshNames.includes(n))
    const sameParams = oldNames.every((n) => fresh.toolMeta[n]
      && JSON.stringify(fresh.toolMeta[n].params) === JSON.stringify(old.toolMeta[n].params))
    const additiveOk = acceptNew.length > 0
      && removed.length === 0
      && sameParams
      && JSON.stringify(added.slice().sort()) === JSON.stringify(acceptNew.slice().sort())
      && fresh.registeredCount === old.registeredCount + added.length
      && added.every((n) => only.includes(n))
    if (signatureChanged && !additiveOk) {
      console.error('拒绝写入：本次采集到的工具签名（工具数/参数表）与基线不一致 —— 这不是"用例更新"，请单独走一次契约评审。')
      if (acceptNew.length) {
        console.error('  --accept-new-tool 只放行「纯追加」：既有参数表须逐字节不变、注册数只加新增个数、新工具须同时在 --only。')
        console.error(`  新增=${JSON.stringify(added)}｜删除=${JSON.stringify(removed)}｜既有参数表不变=${sameParams}｜注册数 ${old.registeredCount} → ${fresh.registeredCount}`)
      }
      process.exit(2)
    }
    // 放行了纯追加，就必须真的把新签名写进去（否则 diff 仍按老注册数判 FAIL）
    const signature = signatureChanged
      ? { registeredCount: fresh.registeredCount, toolMeta: fresh.toolMeta }
      : { registeredCount: old.registeredCount, toolMeta: old.toolMeta }
    const snapshot = {
      schemaVersion: old.schemaVersion,
      registeredCount: signature.registeredCount,
      toolMeta: signature.toolMeta,
      cases: mergedCases,
      skipped: old.skipped,
      coverage: { called: Object.keys(mergedCases).length, skipped: Object.keys(old.skipped).length, tools: signature.registeredCount },
      baselineUpdates: [...(old.baselineUpdates || []), {
        at: new Date().toISOString(),
        tools: only,
        reason,
        changedCases: audit.filter((a) => a.结论 !== '重采后一致').map((a) => a.用例),
        ...(signatureChanged
          ? { signature: { registeredCount: [old.registeredCount, fresh.registeredCount], acceptedNewTools: acceptNew } }
          : {}),
      }],
    }
    writeFileSync(path, JSON.stringify(snapshot, null, 2) + '\n')
    console.log(`基线已就地更新：${update}`)
    console.log(`  只重采工具：${only.join(', ')}｜原因：${reason}`)
    console.log('  用例逐条审计（sha256 前 12 位）：')
    for (const a of audit) console.log(`   · ${a.用例.padEnd(24)} ${a.工具.padEnd(24)} ${a.更新前} → ${a.更新后}  ${a.结论}`)
    const untouched = Object.keys(mergedCases).filter((id) => !only.includes(mergedCases[id].tool))
    if (signatureChanged) {
      console.log(`  工具签名：注册数 ${old.registeredCount} → ${fresh.registeredCount}｜新增工具 ${acceptNew.join(', ')}（既有工具参数表逐字节未变）`)
    }
    console.log(`  未受影响用例：${untouched.length} 个（原样保留，可再用 diff.mjs 复核）`)
    process.exit(0)
  }

  const snap = await capture(traceMode)
  const text = JSON.stringify(snap, null, 2) + '\n'
  if (out) {
    writeFileSync(resolve(process.cwd(), out), text)
    console.log(`已写入 ${out}`)
  } else {
    process.stdout.write(text)
  }
  console.log(`采集完成：注册工具 ${snap.registeredCount} 个；调用 ${snap.coverage.called} 个用例；跳过 ${snap.coverage.skipped} 个工具（需网络/需登录）；trace=${traceMode}`)
}
