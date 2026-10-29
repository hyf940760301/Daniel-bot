/**
 * daniel-dsh-plugin —— Daniel Bot 的**第三种分发形态：DSH 插件**（自包含）。
 *
 * 三种形态共用同一份能力，互不影响：
 *   · CLI 形态：本机 `daniel` 命令（入口进 PATH）
 *   · MCP 形态：MCP 服务器（宿主按 MCP 配置拉起）
 *   · 插件形态（本包）：在 DSH 进程内注册 `daniel_*` 工具；
 *     **能力随包内嵌**（vendor/ 下就是 Daniel 交付包本体：程序 ＋ 8 束语料 ＋ 工序契约 ＋ 运行期能力模块），
 *     因此「只装这个插件包」= 装到了完整能力（读 ＋ 写 ＋ 出件），不需要本机另外装 CLI。
 *
 * 写操作采用**两段式**（与 CLI 的四道闸同源，闸门不在插件里重写）：
 *   daniel_write_plan   → 干跑（等价 CLI 不带 --confirm）：返回执行计划／影响范围／将被改动的对象 ＋ planId
 *   daniel_write_commit → 凭 planId 执行（等价 CLI 带 --confirm）：三条硬约束见 commit 实现
 *
 * @module daniel-dsh-plugin
 */
import { loadDep } from './deps.js'
import { brandView, brandList, skillsList, channelView, kolFullView, planView, renameAndScrub, ANSWER_POLICY } from './normalize.js'
import { finalizeOutput, TRACE_MODES, TRACE_DEFAULT_MODE, TRACE_TOOLS, assertTrace, buildTraceSections } from './trace.js'
import { clarifyPlan, screenPlan, CLARIFY_MAX_ITEMS, CLARIFY_TOPICS } from './clarify.js'
import { execFile, spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const dshTools = await loadDep('@deepseek-ai/dsh-tools')
const schemastery = await loadDep('@deepseek-ai/schemastery')
const defineTool = dshTools.defineTool
const z = schemastery.default ?? schemastery

export const name = 'daniel'
export const inject = ['tools']

const HERE = dirname(fileURLToPath(import.meta.url))
/** 包内自带的 Daniel 能力（vendor/ 下是交付包本体：data/ ＋ .kol-tools/） */
const VENDOR_ENTRY = join(HERE, '..', 'vendor', 'data', 'daniel-cli', 'bin', 'daniel')

/** 插件配置（全部可选） */
export const Config = z.object({
  /** 覆盖入口：默认用包内 vendor 副本；给出则优先用它（如指向服务端代理脚本） */
  entry: z.string(),
  /** 解释器（默认 python3；Daniel 只用标准库） */
  python: z.string().default('python3'),
  /** 数据落点（DANIEL_HOME）；留空交给 Daniel 自解析（会话、缓存、审计都在这里） */
  danielHome: z.string(),
  /** 单次调用超时（毫秒） */
  timeoutMs: z.natural().default(180000),
  /**
   * 输出溯源档位（名单/筛选/评估类结果是否附带四段：筛选逻辑链／入选理由／排除分块／口径假设）
   *   off     → 不追加任何新字段（= 0.9.1 老行为，出问题一个配置改回去）
   *   summary → 白名单工具追加四段，**每段 ≤2 条短句**的结论级信息（默认）
   *   full    → 白名单工具追加**完整四段**（骨架内容 ＋ 每条理由更细的表述）
   * 两档都会在 trace 里带上 `层级`（summary｜full）与 `末尾提示`（常驻提示一句，措辞固定）。
   */
  trace: z.union([z.const('off'), z.const('summary'), z.const('full')]).default(TRACE_DEFAULT_MODE),
})

function resolveEntry(config) {
  if (config.entry) return config.entry
  if (process.env.DANIEL_BIN) return process.env.DANIEL_BIN
  if (existsSync(VENDOR_ENTRY)) return VENDOR_ENTRY
  // 🔴 这里**不许出现任何本机绝对路径**（2026-10-22 用户裁决：整包要能复制到别人机器上跑）。
  //    入口只认三处，全部相对"包自身"或由使用者在安装/运行时给出：
  //      ① config.entry（宿主配置显式给）② 环境变量 DANIEL_BIN
  //      ③ 包内 vendor（相对本文件：<包根>/vendor/data/daniel-cli/bin/daniel）
  throw new Error('daniel-dsh-plugin: 找不到 Daniel 入口（包内 vendor 缺失，且未配置 config.entry／DANIEL_BIN）')
}

/** 数据落点：显式配置 > 环境变量 > 本机已有落点（这样"装完即用本机现有登录"） */
function resolveHome(config) {
  if (config.danielHome) return config.danielHome
  if (process.env.DANIEL_HOME) return process.env.DANIEL_HOME
  const mac = join(homedir(), 'Library', 'Application Support', 'DanielCopilot')
  if (existsSync(mac)) return mac
  return null   // 交给 Daniel 自己降级（包内 .daniel-home）
}

function runDaniel(config, args) {
  const env = { ...process.env }
  const home = resolveHome(config)
  if (home) env.DANIEL_HOME = home
  env.DANIEL_NO_OPEN = '1'          // 插件形态绝不弹浏览器
  return new Promise((resolve) => {
    execFile(
      config.python || 'python3',
      [resolveEntry(config), ...args, '--json'],
      { env, timeout: config.timeoutMs, maxBuffer: 64 * 1024 * 1024 },
      (err, stdout, stderr) => {
        let parsed = null
        try { parsed = JSON.parse(stdout) } catch { /* 非 JSON 输出 */ }
        const exitCode = err && typeof err.code === 'number' ? err.code : err ? 1 : 0
        resolve({
          exitCode,
          ok: Boolean(parsed && parsed.ok),
          data: parsed ? parsed.data : null,
          error: parsed ? parsed.error : null,
          stderrTail: (stderr || '').slice(-1500),
        })
      },
    )
  })
}

/**
 * 输出清洗：宿主对返回值做严格校验，null／undefined 会被判 "not lossless JSON"。
 *
 * **统一兜底（TICKET-221）**：所有工具出口都走这一个函数，因此这里就地过一遍 `prune()`——
 * 视图层/透传层若带出 null／undefined／空串，到这一层直接消失，不会原样透给宿主。
 * 一处改、全工具受益：`daniel_brand_view`／`daniel_brands_list`／`daniel_brand_count`
 * 这些 `clean(data)` 直出的工具从此也不再有 null 风险（不必每个出口各写一遍 prune）。
 * 导出只为自检脚本能直接验证这条口径（`scripts/test-nulls.mjs`）。
 */
export function clean(o) {
  const r = { ok: Boolean(o.ok), exitCode: Number(o.exitCode ?? 0), 回答纪律: ANSWER_POLICY }
  if (o.command) r.command = String(o.command)
  if (o.data !== null && o.data !== undefined) r.data = o.data
  if (o.error !== null && o.error !== undefined) r.error = o.error
  if (o.note) r.note = String(o.note)
  return prune(r)
}

/* ───────────────── 登录（把会话值经标准输入交给 CLI；绝不进 argv、绝不进输出） ─────────────────
 *
 * 为什么登录要单列一条链而不是 `runDaniel(['account','login',...])`：
 *   会话值是**能做事的凭据**（约一年有效）。走 argv 会出现在进程列表里（`ps` 就能捞），
 *   因此值只能走 **stdin**（CLI 的 `--session-cookie-stdin` 就是为此存在的）；
 *   同理它也不许进工具的返回值／错误文案／日志 —— 输出里只留掩码账号。
 * 不承诺"一键授权"：平台登录页不接受第三方跳转回调，人取一次会话值这一步省不掉。
 */

/** 会话值形态：三段点分（`xxx.yyy.zzz`）。这里只做轻校验，深校验（JWS 头）由 CLI 自己做。 */
function sessionShapeOk(v) {
  const parts = String(v).split('.')
  return parts.length === 3 && parts.every((p) => p.length > 0)
}

/** 去掉首尾空白／换行／包裹的一对引号；顺便容忍整串 cookie（`app_session_id=…;`） */
function tidySessionValue(raw) {
  let s = String(raw === null || raw === undefined ? '' : raw).replace(/^\uFEFF/, '').trim()
  s = s.replace(/^app_session_id\s*=\s*/i, '')
  s = s.replace(/;\s*$/, '').trim()
  s = s.replace(/^["'`]+/, '').replace(/["'`]+$/, '').trim()
  return s
}

/** 从任意文本里抹掉会话值（纵深防御：万一上游文案回显了它，也不许流出插件） */
function scrubSecret(text, secret) {
  let out = String(text === null || text === undefined ? '' : text)
  if (secret) out = out.split(String(secret)).join('<已隐去>')
  return out
}

/**
 * 去掉 null／undefined／空串（宿主对返回值做严格校验，空值一律不出现）。
 * 导出只为自检脚本能直接验这条口径（`scripts/test-trace.mjs`／`scripts/test-nulls.mjs`）。
 */
export function prune(v) {
  if (Array.isArray(v)) return v.map(prune).filter((x) => x !== null && x !== undefined)
  if (v && typeof v === 'object') {
    const out = {}
    for (const [k, val] of Object.entries(v)) {
      const pv = prune(val)
      if (pv !== null && pv !== undefined && pv !== '') out[k] = pv
    }
    return out
  }
  return v
}

/** 真跑登录：`spawn` ＋ 把会话值写进 stdin 后关闭（值不进 argv） */
function runDanielLogin(config, value) {
  const env = { ...process.env }
  const home = resolveHome(config)
  if (home) env.DANIEL_HOME = home
  env.DANIEL_NO_OPEN = '1'          // 插件形态绝不弹浏览器
  const argv = [
    resolveEntry(config),
    'account', 'login', '--browser', '--no-open', '--confirm', '--session-cookie-stdin', '--json',
  ]
  const timeoutMs = Number(config.timeoutMs) || 180000
  return new Promise((resolve) => {
    let child
    try {
      child = spawn(config.python || 'python3', argv, { env, stdio: ['pipe', 'pipe', 'pipe'] })
    } catch (e) {
      resolve({ exitCode: 1, ok: false, data: null, error: null, stderrTail: String(e && e.message || e), timedOut: false })
      return
    }
    let out = ''
    let errOut = ''
    let timedOut = false
    const timer = setTimeout(() => { timedOut = true; try { child.kill('SIGKILL') } catch { /* 已退出 */ } }, timeoutMs)
    child.on('error', (e) => { errOut += '\n' + String(e && e.message || e) })
    child.stdin.on('error', () => { /* 子进程提前退出导致的 EPIPE：不影响结论 */ })
    child.stdout.on('data', (c) => { out += String(c) })
    child.stderr.on('data', (c) => { errOut += String(c) })
    child.on('close', (code) => {
      clearTimeout(timer)
      let parsed = null
      try { parsed = JSON.parse(out) } catch { /* 非 JSON 输出 */ }
      resolve({
        exitCode: timedOut ? 1 : (typeof code === 'number' ? code : 1),
        ok: Boolean(parsed && parsed.ok),
        data: parsed ? parsed.data : null,
        error: parsed ? parsed.error : null,
        stderrTail: errOut.slice(-1500),
        timedOut,
      })
    })
    child.stdin.end(String(value) + '\n')
  })
}

/** 登录失败的分类：四种情况给各自不同的人话（过期／不可达／格式／其它） */
function classifyLoginFailure(r) {
  const text = [
    (r.error && r.error.message) || '',
    (r.error && r.error.hint) || '',
    r.stderrTail || '',
  ].join('\n')
  if (r.timedOut) {
    return {
      kind: 'login_timeout',
      message: '这次登录请求超时了（服务端没在校验时限内回应）。会话值本身可能没问题：过一会儿再试一次即可，不要反复重登。',
    }
  }
  if (/服务端不认|已过期|登出过/.test(text)) {
    return {
      kind: 'session_rejected',
      message: '会话值可能已过期（服务端不认这个值），重新登录一次：在浏览器里重新登录 Daniel，再复制 app_session_id 那一行的整格 Value。',
    }
  }
  if (/服务端不可达|不可达|URI?Error|Connection|timed? ?out|getaddrinfo|SSL/i.test(text)) {
    return {
      kind: 'server_unreachable',
      message: '会话格式没问题，但这会儿连不上 Daniel 的服务端，没能完成校验 —— 过一会儿重试就好，不要反复重新登录（本地会话没失效）。',
    }
  }
  if (/不是一条会话 cookie|格式不对|shape/.test(text)) {
    return {
      kind: 'invalid_session_format',
      message: '这个值不是一条会话值（格式不对）：应复制浏览器里 app_session_id 那一行的整格 Value（形如 xxx.yyy.zzz）。',
    }
  }
  if (/没有读到会话值|空/.test(text)) {
    return {
      kind: 'empty_session',
      message: '没有读到会话值（内容是空的）：请把浏览器里 app_session_id 那一行的整格 Value 存进文件后再试。',
    }
  }
  return {
    kind: 'login_failed',
    message: '登录没有完成：' + String((r.error && r.error.message) || '（CLI 没给可用的错误说明）').slice(0, 200),
  }
}

/** 登录后回读：只留「登录了吗／账号（掩码）／状态说明／会话文件落点／下一步」 */
async function readbackLogin(config) {
  const r = await runDaniel(config, ['auth', 'status'])
  const d = r.data || {}
  return {
    已登录: Boolean(d.authenticated),
    账号: (d.server && d.server['账号(掩码)']) || '',
    状态说明: d.reason || '',
    会话文件落点: (d.local && d.local['本机会话文件']) || '',
    下一步: d.next || '',
  }
}

/** 实时口径：直接打 brands.list（按工作区），不读索引、不重建索引 —— 与 Daniel web 端一致 */
/* ───────────────── 常驻 worker（消除每次调用的进程启动开销，并复用已登录会话） ───────────────── */
let WORKER = null
let WORKER_SEQ = 0
const WORKER_PENDING = new Map()

function startWorker(cfg) {
  const env = { ...process.env }
  const home = resolveHome(cfg)
  if (home) env.DANIEL_HOME = home
  env.DANIEL_NO_OPEN = '1'
  const child = spawn(cfg.python || 'python3', [join(HERE, 'worker.py')], { env, stdio: ['pipe', 'pipe', 'pipe'] })
  let buf = ''
  child.stdout.on('data', (chunk) => {
    buf += String(chunk)
    let idx
    while ((idx = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, idx); buf = buf.slice(idx + 1)
      if (!line.trim()) continue
      let msg
      try { msg = JSON.parse(line) } catch { continue }
      const p = WORKER_PENDING.get(msg.id)
      if (!p) continue
      WORKER_PENDING.delete(msg.id)
      if (msg.ok) p.resolve(msg.data)
      else p.reject(new Error((msg.error && msg.error.message) || 'worker error'))
    }
  })
  child.on('exit', () => {
    WORKER = null
    for (const [, p] of WORKER_PENDING) p.reject(new Error('daniel worker 退出'))
    WORKER_PENDING.clear()
  })
  child.stderr.on('data', () => { /* 保持安静：不让 python 警告污染工具输出 */ })
  return child
}

/** 调常驻 worker（首次自动拉起；进程死了下次重建） */
function callWorker(cfg, op, args, timeoutMs = 30000) {
  if (!WORKER) WORKER = startWorker(cfg)
  const id = ++WORKER_SEQ
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { WORKER_PENDING.delete(id); reject(new Error(`worker ${op} 超时`)) }, timeoutMs)
    WORKER_PENDING.set(id, {
      resolve: (v) => { clearTimeout(timer); resolve(v) },
      reject: (e) => { clearTimeout(timer); reject(e) },
    })
    WORKER.stdin.write(JSON.stringify({ id, op, args }) + '\n')
  })
}

const LIVE_PY = (ws) => `
import json, sys, time
sys.path.insert(0, ${JSON.stringify("__KOL__")})
import daniel_client as dc
d = dc.Daniel(verbose=False)
t0 = time.time()
route, brands = d.brands(${ws})
el = int((time.time() - t0) * 1000)
print(json.dumps({"route": route, "count": len(brands), "elapsedMs": el,
                  "brands": [{"id": b.get("id"), "name": b.get("name"), "workspaceId": b.get("workspaceId")} for b in brands]}, ensure_ascii=False))
`;

function runLive(config, workspace) {
  const kolDir = join(HERE, '..', 'vendor', '.kol-tools')
  const env = { ...process.env }
  const home = resolveHome(config)
  if (home) env.DANIEL_HOME = home
  env.DANIEL_NO_OPEN = '1'
  const code = LIVE_PY(workspace).replace('__KOL__', kolDir)
  return new Promise((resolve) => {
    execFile(config.python || 'python3', ['-c', code], { env, timeout: config.timeoutMs, maxBuffer: 32 * 1024 * 1024 }, (err, stdout, stderr) => {
      let parsed = null
      try { parsed = JSON.parse(stdout.trim().split('\n').pop()) } catch { /* 非 JSON */ }
      resolve({
        ok: Boolean(parsed) && !err,
        exitCode: err ? 1 : 0,
        data: parsed,
        error: err ? { kind: 'live_query_failed', message: (stderr || err.message || '').slice(-600) } : null,
      })
    })
  })
}


/**
 * 闸账本出栈前的裁剪（TICKET-218 · B）：worker 的账本原样带出，只去掉 `账本落点`
 * （那是本机文件路径，属内部落点，不该出现在给模型的返回体里，免得被复述给用户）。
 * 账本是**实测**计数，不是业务数据，因此可以随结果一起带出；没账本就返回 null（出口 prune 会抹掉）。
 */
function ledgerForOutput(led) {
  if (!led || typeof led !== 'object') return null
  const { 账本落点, ...rest } = led
  return rest
}

/** 清洗只读直通结果：去掉内部键，避免模型把接口名/字段名讲给用户 */
const INTERNAL_KEY = /^(route|method|procedure|payload|request|http|httpStatus|rawBody|trpc|_meta|_debug|shape|seconds|elapsedMs|nextPageToken)$/i
function scrub(v, depth = 0) {
  if (depth > 6 || v === null || typeof v !== 'object') return v
  if (Array.isArray(v)) return v.slice(0, 30).map((x) => scrub(x, depth + 1))
  const out = {}
  for (const [k, val] of Object.entries(v)) {
    if (INTERNAL_KEY.test(k)) continue
    out[k] = scrub(val, depth + 1)
  }
  return out
}


/** 读能力正文：只留「哪一束·哪一段·正文」，去掉文件路径、行区间、指纹这类内部信息 */
function trimSkillsRead(data) {
  if (!data || typeof data !== 'object') return data
  const out = {}
  if (data['能力域']) out['能力域'] = data['能力域']
  if (data['域']) out['能力'] = data['域']
  if (typeof data['切片号'] === 'number') out['切片号'] = data['切片号']
  if (data['源节标题']) out['章节'] = data['源节标题']
  if (data['完整性']) out['完整性'] = data['完整性']
  if (data['分片'] && typeof data['分片'] === 'object') {
    out['本次字节'] = data['分片']['本次字节']
    out['是否还有更多'] = data['分片']['还有更多']
  }
  if (Array.isArray(data['切片清单'])) out['切片清单'] = data['切片清单']
  let body = data['正文'] || data['text'] || data['content']
  if (body) {
    // 切掉正文顶部的生成说明（含源文件路径与行区间），只留判据本身
    body = String(body).replace(/^<!--[\s\S]*?-->\s*/,'')
    out['正文'] = body.slice(0, 12000)
  }
  return Object.keys(out).length ? out : renameAndScrub(data)
}

const OUT = {
  schema: {
    type: 'object',
    additionalProperties: true,
    properties: {
      ok: { type: 'boolean', required: true },
      exitCode: { type: 'number', required: true },
      command: { type: 'string' },
      data: { type: 'object', additionalProperties: true },
      error: { type: 'object', additionalProperties: true },
      note: { type: 'string' },
    },
  },
}

function tool(meta) {
  return defineTool({
    name: meta.name,
    description: meta.description,
    parameters: meta.parameters,
    output: {
      schema: OUT.schema,
      render: (_a, value) => [{ type: 'text', text: JSON.stringify(value, null, 1) }],
    },
    execute: meta.execute,
  })
}

/* ───────────────── 写操作：两段式（plan → 人确认 → commit） ───────────────── */

const PLANS = new Map()          // planId -> { argv, objectsDigest, createdAt, used }
const PLAN_TTL_MS = 5 * 60 * 1000

/** 把「将被改动的具体对象」从干跑结果里抽出来并做摘要（用于绑定确认） */
function digestOf(argv, data) {
  const plan = (data && data.plan) || {}
  const payload = JSON.stringify({
    argv,
    targetName: plan.targetName ?? null,
    brand: plan.brand ?? null,
    workspaceId: plan.workspaceId ?? null,
    impact: plan.impact ?? null,
  })
  return createHash('sha256').update(payload).digest('hex').slice(0, 16)
}

export function apply(ctx, config) {
  const cfg = { ...config }
  const wrap = (command, args) => async () => {
    const r = await runDaniel(cfg, args)
    return clean({ ok: r.ok, command, exitCode: r.exitCode, data: r.data, error: r.error })
  }

  /* ── 输出契约（trace）：只在**成功**返回上追加四段，位置在返回体最后 ──
   * · trace=off 或工具不在白名单 → 原对象原样返回（一个字段都不动，可与基线逐字节比对）；
   * · ok=false 的返回不追加：错误语义优先，对失败结果讲"筛选逻辑"没有意义。
   */
  const finish = (toolName, args, result) => {
    if (!result || result.ok !== true) return result
    return finalizeOutput({
      tool: toolName,
      mode: cfg.trace,
      args: args || {},
      data: result.data,
      result,
      answerPolicy: ANSWER_POLICY,
    })
  }

  /* ── 只读工具 ───────────────────────────────────────────── */
  ctx.tools.register(tool({
    name: 'daniel_status',
    description: '[Daniel] 登录状态与账号（掩码）＋ 数据落点。装完插件先调这个确认能干活。',
    parameters: {},
    execute: async () => {
      const r = await runDaniel(cfg, ['auth', 'status'])
      const d = r.data || {}
      return clean({
        ok: r.ok, command: 'auth status', exitCode: r.exitCode,
        data: {
          已登录: Boolean(d.authenticated),
          状态说明: d.reason || null,
          账号: (d.server && d.server['账号(掩码)']) || null,
          角色: (d.server && d.server['系统角色']) || null,
          // 未登录时的下一步必须是**插件里真能执行**的动作：CLI 命令对插件用户不存在
          下一步: d.authenticated
            ? (d.next || null)
            : '在浏览器登录 Daniel（https://daniel-agent.com/auth），把 app_session_id 存成文本文件后把路径给我，我用 daniel_login 完成登录；登录一次约一年有效。',
        },
        error: r.error,
      })
    },
  }))

  ctx.tools.register(tool({
    name: 'daniel_login',
    description:
      '[Daniel] **登录 Daniel（首次使用／换机器时先做这一步，登录一次约一年有效）**。' +
      '什么时候用：用户说「登录 Daniel」「登录一下」「授权 Daniel」，或其它 daniel_* 工具返回未登录／去登录时。' +
      '两个参数**二选一**，优先前者：' +
      '① `session_file`（**推荐**）：让用户把会话值存成一个本地纯文本文件，把文件绝对路径给你 —— ' +
      '这样值不进对话记录；② `session_value`：用户直接在对话里贴值（兜底；值会留在对话记录里，用了要提醒）。' +
      '会话值怎么取（要原样告诉用户）：在浏览器里登录 Daniel（https://daniel-agent.com/auth）→ ' +
      '开发者工具（macOS ⌥⌘I）→ Application → 左侧 Storage → Cookies → https://daniel-agent.com → ' +
      '找到行名为 `app_session_id` 的那一条，双击 Value 整格全选复制（这条 cookie 带 HttpOnly，Console 里敲 document.cookie 取不到）。' +
      '本工具只做「值 → 校验 → 落盘 → 回读确认」，**不会**、也**不承诺**一键跳转授权（平台登录页不支持第三方回调，人取一次值这一步省不掉）；' +
      '本工具也不弹浏览器、不要账号密码。' +
      '返回只有：已登录（真／假）、账号（掩码）、状态说明、会话文件落点、失败时的下一步；' +
      '**任何情况下都不回显会话值**。用文件方式时，返回里会提示用户自己删掉那个文件。' +
      '错误是按类型可区分的：文件不存在／文件为空／格式不对／服务端不认（过期，需重新登一次）／服务端不可达（稍后重试，别反复重登）。',
    parameters: {
      session_file: {
        type: 'string',
        description: '本地文件绝对路径（推荐）：文件内容就是会话值。值不进对话记录。',
      },
      session_value: {
        type: 'string',
        description: '直接传会话值本身（兜底；会留在对话记录里，尽量改用 session_file）。',
      },
    },
    execute: async (args) => {
      const a = args || {}
      const fileIn = typeof a.session_file === 'string' ? a.session_file.trim() : ''
      const valueIn = typeof a.session_value === 'string' ? a.session_value.trim() : ''
      const CMD = 'account login（浏览器授权路）'

      if (fileIn && valueIn) {
        return clean({
          ok: false, command: CMD, exitCode: 2,
          error: {
            kind: 'usage',
            message: 'session_file 与 session_value 只能给一个：优先用 session_file（值不进对话记录），另一个留空。',
          },
        })
      }
      if (!fileIn && !valueIn) {
        return clean({
          ok: false, command: CMD, exitCode: 2,
          error: {
            kind: 'usage',
            message: '需要 session_file 或 session_value 之一：推荐让用户把会话值存成一个本地文件、把文件路径给你（session_file，值不进对话记录）；兜底才让用户直接贴值（session_value）。',
          },
        })
      }

      // 文件名容错：允许 `~/` 写法
      let filePath = fileIn
      if (filePath.startsWith('~/')) filePath = join(homedir(), filePath.slice(2))

      let value = ''
      let source = ''
      if (filePath) {
        let raw = ''
        try {
          raw = readFileSync(filePath, 'utf8')
        } catch (e) {
          const code = String((e && e.code) || 'READ_FAILED')
          if (code === 'ENOENT') {
            return clean({
              ok: false, command: CMD, exitCode: 2,
              error: {
                kind: 'session_file_not_found',
                message: `找不到这个文件：${filePath}。请让用户确认路径（要绝对路径、别带多余引号），或重新把会话值存一次。`,
              },
            })
          }
          return clean({
            ok: false, command: CMD, exitCode: 2,
            error: {
              kind: 'session_file_unreadable',
              message: `这个文件读不了：${filePath}（${code}）。请让用户把会话值另存成一个纯文本文件（例如 ~/Desktop/daniel-session.txt）再把路径给你。`,
            },
          })
        }
        value = tidySessionValue(raw)
        if (!value) {
          return clean({
            ok: false, command: CMD, exitCode: 2,
            error: {
              kind: 'session_file_empty',
              message: `这个文件是空的（或只有空白）：${filePath}。请让用户把浏览器里 app_session_id 那一行的整格 Value 存进这个文件，再给一次路径。`,
            },
          })
        }
        source = 'file'
      } else {
        value = tidySessionValue(valueIn)
        if (!value) {
          return clean({
            ok: false, command: CMD, exitCode: 2,
            error: { kind: 'empty_session', message: 'session_value 是空的：请让用户重新复制 app_session_id 那一行的整格 Value。' },
          })
        }
        source = 'inline'
      }

      if (!sessionShapeOk(value)) {
        return clean({
          ok: false, command: CMD, exitCode: 2,
          error: {
            kind: 'invalid_session_format',
            message: '这个值不是一条会话值（格式不对）：应复制浏览器里 app_session_id 那一行的整格 Value（形如 xxx.yyy.zzz）。' +
              '位置：开发者工具 → Application → Storage → Cookies → https://daniel-agent.com → 行 app_session_id 的 Value 整格。',
          },
          note: source === 'file' ? `会话值没有写进任何地方；那个文件还在原处：${filePath}，改好内容后可以直接再调一次。` : undefined,
        })
      }

      // 真跑：值只走 stdin
      const r = await runDanielLogin(cfg, value)
      const fileNote = source === 'file'
        ? `会话值是从文件读的。那个文件仍留在原处：${filePath}（里面是凭据）——建议你用完自己删掉它，本工具不替你删任何文件。`
        : '这次是把会话值直接贴进来的：它已经进入对话记录，建议删掉那条消息、以后改用「存成本地文件再给路径」的方式。'

      if (!r.ok) {
        const f = classifyLoginFailure(r)
        const msg = scrubSecret(f.message, value)
        // 口径统一：用法／格式类错误一律退出码 2（不论是在插件预检挡下的，还是 CLI 形态校验挡下的）
        const code = (f.kind === 'invalid_session_format' || f.kind === 'empty_session') ? 2 : (r.exitCode || 1)
        return clean({
          ok: false, command: CMD, exitCode: code,
          data: prune({ 已登录: false, 下一步: msg }),
          error: { kind: f.kind, message: msg },
          note: source === 'file' ? fileNote : undefined,
        })
      }

      // 回读：登录完立刻确认"到底登上了没有"（不信命令自己的话说成功）
      const back = await readbackLogin(cfg)
      const loggedPath = (r.data && r.data.readback && r.data.readback.detail && r.data.readback.detail['会话文件']
        && r.data.readback.detail['会话文件']['路径']) || back.会话文件落点

      if (!back.已登录) {
        return clean({
          ok: false, command: CMD, exitCode: 1,
          data: prune({
            已登录: false,
            账号: back.账号,
            状态说明: back.状态说明 || '会话已写入，但回读没有确认登录通过',
            会话文件落点: loggedPath,
            下一步: scrubSecret(back.下一步 || '再试一次：让用户在浏览器里重新登录后重新复制会话值；若连续不成，先确认这台机器能打开 daniel-agent.com。', value),
          }),
          error: {
            kind: 'readback_not_authenticated',
            message: '会话写进去了，但回读登录状态没有通过 —— 先不要急着反复重登，过一会儿用 daniel_status 再看一次。',
          },
          note: source === 'file' ? fileNote : undefined,
        })
      }

      return clean({
        ok: true, command: CMD, exitCode: 0,
        data: prune({
          已登录: true,
          账号: back.账号,
          状态说明: '登录成功：会话已校验并落盘，回读确认是这个账号',
          会话文件落点: loggedPath,
        }),
        note: fileNote,
      })
    },
  }))

  ctx.tools.register(tool({
    name: 'daniel_brands_list',
    description:
      '[Daniel] 列出账号可见的品牌，**秒级（约 1 秒，读本地索引）**。可按工作区过滤：问「某工作区有哪些品牌」时传 workspace。' +
      '返回里带 indexBuiltAt（索引构建时间）——请把该时间一并告诉用户，**不要**为了让数据"更新"而触发刷新（刷新约 1 分钟起，必须由用户明确同意）。',
    parameters: {
      workspace: { type: 'number', description: '只看某个工作区（如 90002）' },
      limit: { type: 'number', description: '最多返回多少个品牌（默认 20）' },
    },
    execute: async (args) => {
      const a = ['brands', 'list']
      if (args && args.workspace) a.push('--workspace', String(args.workspace))
      if (args && args.limit) a.push('--limit', String(args.limit))
      const r = await runDaniel(cfg, a)
      return finish('daniel_brands_list', args, clean({ ok: r.ok, command: 'brands list', exitCode: r.exitCode, data: r.ok && r.data ? brandList(r.data) : null, error: r.error }))
    },
  }))

  ctx.tools.register(tool({
    name: 'daniel_brand_view',
    description:
      '[Daniel] 看**某个品牌的业务档案**（品类、目标市场、行业关键词、竞品、样品价、简介），**已翻译成业务语言**：' +
      '竞品只给「名称＋该竞品覆盖的品类关键词」，不暴露系统内部字段。' +
      '需要核对"落库的到底是什么"时用这个工具，然后把业务字段讲给用户即可。',
    parameters: {
      brand: { type: 'string', required: true, description: '品牌名或品牌编号（如 4800023）' },
    },
    execute: async (args) => {
      const r = await runDaniel(cfg, ['brands', 'show', '--brand', String(args.brand)])
      const raw = (r.data && (r.data.brand || r.data)) || null
      const view = brandView(raw)
      return clean({
        ok: Boolean(r.ok && view),
        command: `brands show ${args.brand}`,
        exitCode: r.exitCode,
        data: view ? { 品牌: view, 回答提示: '用业务语言复述：品类、目标市场、行业关键词数量与示例、竞品名单与各自关键词；不要说字段名或接口。' } : null,
        error: r.error,
      })
    },
  }))

  ctx.tools.register(tool({
    name: 'daniel_brand_count',
    description:
      '[Daniel] **回答「某个工作区有多少个品牌」就调这个：默认走实时口径（直连接口，约 1 秒，与 Daniel 网页端一致，不读索引、不重建索引）**。' +
      '返回 count、品牌清单、source（live＝实时／index＝回落的索引）、以及耗时。' +
      '仅当 source=index 时，才需要把 indexBuiltAt 一并告诉用户。' +
      '**不要**为"要更新"而重建索引：`--refresh` 要 1 分钟起，必须用户明确同意。',
    parameters: {
      workspace: { type: 'number', required: true, description: '工作区编号（如 jack=90002）' },
    },
    execute: async (args) => {
      const ws = Number(args.workspace)
      // ① 实时优先：直连 brands.list（与 web 端一致，约 1 秒，不读索引、不重建索引）
      let live = { ok: false, error: { message: 'worker 不可用' } }
      try {
        const d = await callWorker(cfg, 'brands', { workspace: ws })
        live = { ok: true, data: { count: d.count, brands: d.brands, route: d.route, elapsedMs: Math.round((d.seconds || 0) * 1000) } }
      } catch (e) {
        live = await runLive(cfg, ws)   // 兜底：一次性进程
      }
      if (live.ok && live.data) {
        return clean({
          ok: true,
          command: `品牌计数（工作区 ${ws}）`,
          exitCode: 0,
          data: {
            工作区编号: ws,
            数量: live.data.count,
            品牌: (live.data.brands || []).map((b) => ({ 品牌名: b.name, 品牌编号: b.id })),
            口径: '实时（与网页端一致，未读本地索引）',
            耗时毫秒: live.data.elapsedMs ?? null,
          },
        })
      }
      // ② 回落：本地索引（离线／接口不可达时），并明确标注数据时点
      const r = await runDaniel(cfg, ['brands', 'list', '--workspace', String(ws)])
      const d = r.data || {}
      const brands = d.brands || []
      return clean({
        ok: r.ok,
        command: `brands list --workspace ${ws}（实时失败，回落索引）`,
        exitCode: r.exitCode,
        data: {
          工作区编号: ws,
          数量: d.count ?? brands.length,
          品牌: brands.map((b) => ({ 品牌名: b.name, 品牌编号: b.id, 所属工作区: b.workspaceName })),
          口径: '本地索引（实时接口未通）',
          数据时点: d.indexBuiltAt ?? null,
          说明: '请把数据时点一并告知用户。',
        },
        error: r.error,
      })
    },
  }))

  ctx.tools.register(tool({
    name: 'daniel_skills_list',
    description: '[Daniel] 列出随包分发的营销能力域（8 束）与工序统计。不需要登录。',
    parameters: {},
    execute: async () => {
      const r = await runDaniel(cfg, ['skills', 'list'])
      return clean({ ok: r.ok, command: 'skills list', exitCode: r.exitCode, data: r.data ? skillsList(r.data) : null, error: r.error })
    },
  }))

  ctx.tools.register(tool({
    name: 'daniel_skills_read',
    description: '[Daniel] 读某一束能力的切片清单或正文（判断标准原文）。不需要登录。',
    parameters: {
      skill: { type: 'string', required: true, description: '能力域名，如 kol-screening' },
      section: { type: 'number', description: '切片号（不给则返回切片清单）' },
    },
    execute: async (args) => {
      const a = ['skills', 'read', '--name', String(args.skill)]
      if (args && args.section) a.push('--section', String(args.section))
      const r = await runDaniel(cfg, a)
      return clean({ ok: r.ok, command: 'skills read', exitCode: r.exitCode, data: r.data ? trimSkillsRead(r.data) : null, error: r.error })
    },
  }))

  ctx.tools.register(tool({
    name: 'daniel_run',
    description:
      '[Daniel] 任意**只读**子命令直通（如 ["brands","show","--brand","3690002"]）。写命令请改用 daniel_write_plan → daniel_write_commit 两段式。',
    parameters: {
      argv: { type: 'array', required: true, items: { type: 'string' }, description: '子命令与参数' },
      user_approved_refresh: {
        type: 'boolean',
        description: '仅当命令带 --refresh（重建索引，约 1 分钟起）时使用：必须先向用户说明代价并取得明确同意，才可置 true。',
      },
    },
    execute: async (args) => {
      const argv = (args && args.argv) || []
      if (!argv.length) return clean({ ok: false, command: 'run', exitCode: 2, error: { kind: 'usage', message: 'argv 不能为空' } })
      // 防护：索引重建（--refresh）是 1 分钟起的重活，必须由用户明确同意，插件不代劳
      const wantsRefresh = argv.map(String).includes('--refresh')
      if (wantsRefresh && !(args && args.user_approved_refresh === true)) {
        return clean({
          ok: false, command: argv.join(' '), exitCode: 2,
          error: {
            kind: 'refresh_needs_user_consent',
            message: '重建索引（--refresh）约需 1 分钟起，属重量级操作：请先向用户说明代价并取得明确同意后再执行；日常查询请直接用缓存结果（秒级）并注明索引时间。',
          },
        })
      }
      const r = await runDaniel(cfg, argv.map(String))
      if (r.exitCode === 3) {
        return clean({
          ok: false, command: argv.join(' '), exitCode: 3,
          error: {
            kind: 'write_needs_plan',
            message: '这是写操作：请先用 daniel_write_plan 生成计划交用户确认，再用 daniel_write_commit 执行。',
          },
        })
      }
      // 出口统一过 prune()：直通会把 CLI 原始数据整段透传，其中可能含 null —— 宿主对返回值做
      // 严格校验，含 null 会报 value is not lossless JSON，整次调用直接失败。缺失项一律不出现。
      return finish('daniel_run', args, clean({ ok: r.ok, command: argv.join(' '), exitCode: r.exitCode, data: r.data ? prune(scrub(r.data)) : null, error: r.error }))
    },
  }))

  /* ── KOL 档案：一次调用拿全（常驻 worker，内部并行）─────────── */
  ctx.tools.register(tool({
    name: 'daniel_kol_profile',
    description:
      '[Daniel] **看一个红人的完整档案就用这一个工具，一次调用拿全（约 2–3 秒）**：' +
      '输入 handle（@xxx 或频道地址），返回四块业务信息：① 频道档案（名称／订阅数／国家／总播放／视频数）' +
      '② 近 28 天表现（视频数、总播放、平均播放、互动率，分整体／长视频／短视频）' +
      '③ 受众（性别、年龄分布、地区 Top5、兴趣人群与购买意向 Top5）④ 近期视频（标题／播放／点赞／时长／发布时间）。' +
      '**这就是系统里红人详情抽屉里那些数据，一次给全，不用再逐项追问**。' +
      '回答时只讲业务信息（分块列要点即可），**不要**复述内部步骤、接口名或字段名。',
    parameters: {
      handle: { type: 'string', required: true, description: '红人 handle（如 @CasandChary）或频道地址' },
      videos: { type: 'number', description: '近期视频条数（默认 5，最多 10）' },
    },
    execute: async (args) => {
      try {
        const n = Math.min(Number(args.videos || 5) || 5, 10)
        const d = await callWorker(cfg, 'kol_profile', { handle: String(args.handle), videos: n }, 60000)
        const view = kolFullView(d)
        // 出口过 prune()：kolFullView 内部按「有则填、无则 null」组织分块，null 不许出插件
        // （缺哪块由视图里的「未取到」文字说明，不是留 null）。
        return finish('daniel_kol_profile', args, clean({
          ok: true, command: `kol_profile ${args.handle}`, exitCode: 0,
          data: prune({
            ...view,
            耗时秒: d.seconds ?? null,
            回答提示: '按四块给业务结论（频道／表现／受众／近期视频）；缺哪块就照实说，并分清两种：「平台未收录」（平台没这个数据，再说一遍也没有）与「本次未取到」（取数失败，可重试/补采）——不要编，也不要出现接口名或字段名。',
          }),
        }))
      } catch (e) {
        return clean({ ok: false, command: `kol_profile ${args.handle}`, exitCode: 1, error: { kind: 'kol_profile_failed', message: String(e.message || e) } })
      }
    },
  }))

  /* ── YouTube 官方库检索（带受众数据的那一份）─────────────── */
  ctx.tools.register(tool({
    name: 'daniel_roster_search',
    description:
      '[Daniel] **在 YouTube 官方库里找红人（带受众数据的那一份）就用这个工具**，而不是逐个频道去查。' +
      '输入检索式（描述想找什么样的红人）＋ 可选条件（国家、订阅数上下限、品类、分页）。' +
      '返回候选频道清单（名称／编号／订阅数／国家／品类／中位播放）与命中总数。' +
      '⚠️ 官方库是长任务型接口：正常情况下 2–5 秒；平台过载时会返回「官方库暂不可用/超时」，' +
      '此时**如实告诉用户并建议稍后重试或缩小条件**；**不要**改用其它来源（历史名单/其它模块）替代官方库结果，' +
      '除非用户明确同意换源。回答时只讲业务信息（红人、订阅数、国家、均播），不要提接口名或字段名。',
    parameters: {
      query: { type: 'string', required: true, description: '检索式：描述想找什么样的红人（如 "AI glasses review"）' },
      limit: { type: 'number', description: '本次返回多少条（默认 10，建议 10–20）' },
      page: { type: 'number', description: '第几页（默认 1）' },
      country: { type: 'string', description: '国家代码，多个用英文逗号（如 US,CA,GB）' },
      min_subscribers: { type: 'number', description: '订阅数下限' },
      max_subscribers: { type: 'number', description: '订阅数上限' },
      category: { type: 'string', description: '品类（如 Tech）' },
    },
    execute: async (args) => {
      try {
        const d = await callWorker(cfg, 'roster_search', {
          query: String(args.query),
          limit: args.limit ?? 10,
          page: args.page ?? 1,
          country: args.country,
          category: args.category,
          minSubscribers: args.min_subscribers,
          maxSubscribers: args.max_subscribers,
        }, 90000)
        // 出口过 prune()：「平台没给」的字段直接从结果里消失（模型按"未取到"表述），不留 null
        return finish('daniel_roster_search', args, clean({
          ok: true, command: `官方库检索 ${args.query}`, exitCode: 0,
          data: prune({
            命中总数: d.total ?? null,
            本页条数: (d.channels || []).length,
            页码: d.page ?? null,
            候选红人: (d.channels || []).map((c) => ({
              红人: c.title || null,
              频道编号: c.channelId || null,
              订阅数: c.subscriberCount ?? null,
              国家: c.country || null,
              品类: c.category || null,
              中位播放: c.medianViews ?? null,
            })),
            耗时秒: d.seconds ?? null,
            // 闸账本透传（TICKET-218 · B）：worker 已逐闸实测通过／淘汰数，过去被这张
            // 白名单映射丢掉，normalize 只能退回读 ledger.json 文件桥接。追加这一个字段后，
            // normalize 的 readRosterLedger() 优先走**字段通道**，文件桥接退居备用。
            // 只追加、不动既有字段；无账本时该键不出现（clean/prune 抹掉 null）。
            闸账本: ledgerForOutput(d['闸账本']),
            回答提示: '列出候选红人＋订阅数＋国家＋均播，并说明命中总数；缺数据就说缺，不要编。',
          }),
        }))
      } catch (e) {
        let detail = String(e.message || e)
        let kind = 'roster_failed', 建议 = null
        try { const j = JSON.parse(detail); kind = j.kind || kind; 建议 = j['建议']; detail = j.detail || '' } catch { /* 非结构化 */ }
        return clean({
          ok: false, command: `官方库检索 ${args.query}`, exitCode: 1,
          error: {
            kind,
            message: detail.slice(0, 300),
            建议: 建议 || ['稍后重试', '缩小条件后重试', '不要用其它来源替代，除非用户同意'],
          },
        })
      }
    },
  }))

  /* ── 批量只读：一次工具调用跑多条只读命令（省掉多轮往返）──── */
  ctx.tools.register(tool({
    name: 'daniel_batch',
    description:
      '[Daniel] 一次调用执行**多条只读命令**（最多 6 条），省掉多轮工具往返。' +
      '需要同时看几个东西时用它，例如 ["brands list --workspace 90002","skills read --name kol-screening"]。' +
      '写命令会被拒绝；写请走 daniel_write_plan → daniel_write_commit。',
    parameters: {
      calls: {
        type: 'array', required: true,
        items: { type: 'array', items: { type: 'string' } },
        description: '每条命令是一个 argv 数组，如 [["brands","list","--workspace","90002"]]',
      },
    },
    execute: async (args) => {
      const calls = (args && args.calls) || []
      if (!calls.length) return clean({ ok: false, command: 'batch', exitCode: 2, error: { kind: 'usage', message: 'calls 不能为空' } })
      if (calls.length > 6) return clean({ ok: false, command: 'batch', exitCode: 2, error: { kind: 'usage', message: '一次最多 6 条' } })
      const results = []
      for (const argv of calls) {
        const a = (argv || []).map(String)
        const r = await runDaniel(cfg, a)
        const entry = { command: a.join(' '), ok: r.ok, exitCode: r.exitCode }
        // 缺失数据用**文字**表达，绝不留 null（宿主校验会因 null 判 not lossless JSON）：
        //   写命令被挡下 → 明确说该走两段式；命令没返回数据 → 明确说未取到；
        //   有数据 → 清洗后过 prune()，把 CLI 原始数据里的 null 一并清掉。
        if (r.exitCode === 3) entry.data = '（不适用：这条是写操作，请走 daniel_write_plan → daniel_write_commit）'
        else if (r.data) entry.data = prune(renameAndScrub(r.data))
        else entry.data = '（未取到：这条命令没有返回数据）'
        if (r.error) entry.error = { kind: r.error.kind || 'error', message: String(r.error.message || '').slice(0, 200) }
        results.push(entry)
      }
      return finish('daniel_batch', args, clean({ ok: results.every((x) => x.ok), command: `batch(${results.length})`, exitCode: 0, data: { results } }))
    },
  }))

  /* ── 追问闸：模糊需求一次对齐（TICKET-218 · A）───────────────────
   *
   * 只做**参数级**追问（缺市场／缺粉丝区间／缺内容形式／缺交付形态／缺时间窗／
   * 缺是否排重／缺数量上限／缺交付时点）；口径级模糊（"什么算高自然表现"）不在这里，
   * `口径类[]` 只列名字与影响，明写「属口径判断，插件不代拟」。
   *
   * **不执行任何取数**：本工具是纯函数（lib/clarify.js），不起子进程、不读盘、不联网，
   * 返回体里不可能出现品牌名／红人数／金额这类业务数据，只有清单。
   * 也不进 trace 白名单：追问清单不是筛选/评估结论，没有「我筛掉了什么」可讲。
   */
  ctx.tools.register(tool({
    name: 'daniel_clarify',
    description:
      '[Daniel] **需求还模糊时，先调这一个工具把要问的一次问全**（不要自己一轮轮追问用户）。' +
      '输入用户原话或需求摘要（need）＋可选场景（topic：kol_search 找红人／list_ops 名单处理／brand_setup 品牌建档），' +
      '返回四块：① 缺项（每项都带「为什么问」和不答时的默认值）② 优先补（Top3，按对结果的影响排序）' +
      '③ 口径类（只列需要业务口径判断的名字与影响，**插件不给判据**）④ 下一步（答多少都行，未答按默认口径跑并在结论里标注）。' +
      '清单最多 8 项，超出的会写明「其余按默认口径执行」。' +
      '⚠️ 用户需求已经说得够清楚时**不要调**这个工具（调了会返回「参数已齐」），直接干活。' +
      '**找红人（kol_search）走动态追问**：第一次调用只出「选择面」（五类方向＋举例＋默认）；' +
      '把用户回答原样传进 reply 再调一次，它会算覆盖度——说清三门以上直接回「确认」，否则只追问最关键的 2–3 项；' +
      '最多追问 2 轮（传 round 递增），到上限按默认跑并标「未确认」。' +
      '本工具**不取数**：返回里只有清单，没有任何品牌名、红人数或金额。',
    parameters: {
      need: {
        type: 'string',
        required: true,
        description: '用户原话或需求摘要（如"帮我找一批测评红人"）。只用于判断哪些参数已经说了，不会回显给用户。',
      },
      topic: {
        type: 'string',
        enum: [...CLARIFY_TOPICS],
        description: '场景（可选）：kol_search＝找红人／建名单；list_ops＝名单合并去重比对；brand_setup＝品牌建档。不填按通用清单。',
      },
    },
    execute: async (args) => {
      const need = String((args && args.need) || '').trim()
      if (!need) {
        return clean({
          ok: false, command: 'clarify', exitCode: 2,
          error: {
            kind: 'usage',
            message: 'need 不能为空：把用户原话或需求摘要传进来，才判断得出哪些参数已经说了。',
          },
        })
      }
      // 找红人：走「一次给全 ＋ 按覆盖度动态追问」；其余场景沿用参数清单
      const topic = args && args.topic
      // 首次调用：沿用参数清单，并额外给出「选择面」供用户一次说全。
      // 用户回答后的动态追问走 screenPlan（待参数契约评审通过后再接线）。
      const data = Object.assign({}, clarifyPlan(need, topic), { 选择面: screenPlan(need).选择面 })
      // 纯函数出清单：不取数、不读盘、不看时钟，同入参必同输出（可进 golden 基线比对）
      return clean({ ok: true, command: 'clarify', exitCode: 0, data })
    },
  }))

  /* ── 写操作第一段：干跑出计划 ───────────────────────────── */
  ctx.tools.register(tool({
    name: 'daniel_write_plan',
    description:
      '[Daniel] 写操作第一步（**不写入任何东西**）：对一条写命令做干跑，返回执行计划、影响范围、将被改动的具体对象，以及 planId。把这份计划原样呈现给用户，等用户明确说「可以／继续」后，再用 daniel_write_commit 执行。**不要**改用仪器、也不要用底层接口绕开这条链。一次 plan 只能 commit 一次，5 分钟过期。',
    parameters: {
      argv: {
        type: 'array', required: true, items: { type: 'string' },
        description: '完整写命令与参数（不要再加 --confirm），如 ["brands","update","--brand","3690002","--description","新简介"]',
      },
    },
    execute: async (args) => {
      const argv = ((args && args.argv) || []).map(String).filter((s) => s !== '--confirm')
      if (!argv.length) return clean({ ok: false, command: 'write_plan', exitCode: 2, error: { kind: 'usage', message: 'argv 不能为空' } })
      const r = await runDaniel(cfg, argv)
      if (r.exitCode !== 3) {
        return clean({
          ok: false, command: argv.join(' '), exitCode: r.exitCode, data: r.data,
          error: {
            kind: 'not_a_write_or_rejected', message: '干跑没有返回「待确认」：这可能是只读命令，或权限／参数校验已拒绝。',
          },
        })
      }
      const planId = createHash('sha256')
        .update(argv.join(' ') + '|' + Date.now() + '|' + Math.random())
        .digest('hex').slice(0, 20)
      PLANS.set(planId, { argv, objectsDigest: digestOf(argv, r.data), createdAt: Date.now(), used: false })
      return clean({
        ok: true, command: argv.join(' '), exitCode: 3,
        data: {
          planId,
          过期秒数: PLAN_TTL_MS / 1000,
          计划: planView((r.data && r.data.plan) || null, (r.data && r.data.action) || null),
          危险提示: (r.data && r.data.danger) || null,
          下一步: '把「动作／影响对象／将要改动／影响范围」讲给用户确认；用户说「可以」后再调用 daniel_write_commit(planId)。不要提到接口或字段名。',
        },
      })
    },
  }))

  /* ── 写操作第二段：凭确认执行 ───────────────────────────── */
  ctx.tools.register(tool({
    name: 'daniel_write_commit',
    description:
      '[Daniel] 写操作第二步：凭 planId 真正执行（等于 CLI 的 --confirm）。只在用户明确确认过**同一份计划**后调用。三条硬约束：① 计划内容必须与干跑时一致（对象或参数变了会被拒）；② 一次 plan 只能执行一次，5 分钟过期；③ 删除类必须回填目标名（delete_token）。',
    parameters: {
      plan_id: { type: 'string', required: true, description: 'daniel_write_plan 返回的 planId' },
      delete_token: { type: 'string', description: '删除类操作必填：把目标名原样再写一遍（如名单名、品牌名）' },
    },
    execute: async (args) => {
      const planId = String((args && args.plan_id) || '')
      const rec = PLANS.get(planId)
      if (!rec) return clean({ ok: false, command: 'write_commit', exitCode: 2, error: { kind: 'unknown_plan', message: 'planId 不存在或已过期。请重新 daniel_write_plan。' } })
      if (rec.used) return clean({ ok: false, command: 'write_commit', exitCode: 2, error: { kind: 'plan_used', message: '该 plan 已执行过一次（一次确认只对一次执行有效）。请重新 plan。' } })
      if (Date.now() - rec.createdAt > PLAN_TTL_MS) {
        PLANS.delete(planId)
        return clean({ ok: false, command: 'write_commit', exitCode: 2, error: { kind: 'plan_expired', message: 'plan 已超过 5 分钟有效期。请重新 daniel_write_plan。' } })
      }
      // 硬约束 ①：执行前重跑一次干跑，比对「将被改动的对象／参数」是否与确认时一致
      const dry = await runDaniel(cfg, rec.argv)
      if (dry.exitCode !== 3) {
        PLANS.delete(planId)
        return clean({ ok: false, command: rec.argv.join(' '), exitCode: dry.exitCode, data: dry.data, error: { kind: 'plan_stale', message: '执行前复核未通过（目标或权限已变化）。请重新 plan。' } })
      }
      if (digestOf(rec.argv, dry.data) !== rec.objectsDigest) {
        PLANS.delete(planId)
        return clean({ ok: false, command: rec.argv.join(' '), exitCode: 2, error: { kind: 'plan_changed', message: '计划内容与用户确认时不一致（对象／影响范围发生变化），已拒绝执行。请重新 plan 并请用户重新确认。' } })
      }
      // 硬约束 ③：删除类必须回填目标名
      const isDelete = rec.argv.includes('delete') || rec.argv.includes('delete-campaign') || rec.argv.some((a) => a.endsWith('-delete'))
      const dt = (args && args.delete_token) ? String(args.delete_token) : ''
      if (isDelete && !dt) {
        return clean({ ok: false, command: rec.argv.join(' '), exitCode: 2, error: { kind: 'delete_token_required', message: '删除类操作必须回填目标名（delete_token），形同 CLI 的 --delete-token。' } })
      }
      const execArgs = [...rec.argv, '--confirm']
      if (isDelete && dt) execArgs.push('--delete-token', dt)
      rec.used = true                                   // 硬约束 ②：一次一用
      const r = await runDaniel(cfg, execArgs)
      PLANS.delete(planId)
      return clean({ ok: r.ok, command: rec.argv.join(' '), exitCode: r.exitCode, data: r.data, error: r.error })
    },
  }))
}
