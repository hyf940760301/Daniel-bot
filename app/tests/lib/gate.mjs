// 门禁框架（纯 Node，无第三方依赖）
//
// 约定（D-052 / D-053）：
//   · PASS 必须打印「期望 vs 实际」，不允许只写“通过”；
//   · FAIL 必须可由本脚本的原命令复现；
//   · 无法验证一律 SKIP + 理由 + 复验方法，不许写成 PASS；
//   · 退出码：0 = 无 FAIL（可含 SKIP）；1 = 存在 FAIL。
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, lstatSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import process from 'node:process'

const TTY = Boolean(process.stdout.isTTY)
const paint = (code, text) => (TTY ? `\x1b[${code}m${text}\x1b[0m` : text)
export const green = (t) => paint(32, t)
export const red = (t) => paint(31, t)
export const yellow = (t) => paint(33, t)
export const dim = (t) => paint(2, t)

export class Gate {
  constructor(id, title) {
    this.id = id
    this.title = title
    this.results = []
    this.startedAt = new Date()
    console.log(`\n${'═'.repeat(72)}\n${id} · ${title}\n${'═'.repeat(72)}`)
    console.log(dim(`node ${process.version} · ${new Date().toISOString()}`))
  }

  info(message) {
    console.log(dim(`  · ${message}`))
  }

  check(name, { expected, actual, ok, detail }) {
    const status = ok ? green('PASS') : red('FAIL')
    console.log(`${status} ${name} ← 期望: ${expected} | 实际: ${actual}`)
    if (detail) for (const line of String(detail).split('\n').slice(0, 12)) console.log(dim(`      ${line}`))
    this.results.push({ name, status: ok ? 'PASS' : 'FAIL', expected, actual, detail })
    return Boolean(ok)
  }

  skip(name, reason, how) {
    console.log(`${yellow('SKIP')} ${name} ← ${reason}`)
    if (how) console.log(dim(`      复验方法: ${how}`))
    this.results.push({ name, status: 'SKIP', expected: reason, actual: '-', detail: how })
  }

  /**
   * 只记录不判定（例如 CFBundleIdentifier 当前值、Gatekeeper 评估结果）。
   * 这类事实要留给下游门禁（G6 品牌门）判，本门禁若判 FAIL 会掩盖真正的结构问题。
   */
  record(name, value, note) {
    const text = String(value === undefined || value === null || value === '' ? '(空)' : value)
    console.log(`RECORD ${name} = ${text}`)
    if (note) console.log(dim(`      ${note}`))
    this.results.push({ name, status: 'RECORD', expected: '-', actual: text, detail: note })
    return text
  }

  /**
   * @param {{skipReason?: string}} [options] skipReason：本次运行有检查项未执行，
   *   即使有 PASS 也把结论降为 SKIP（例：G3 只跑了预检没真启动，不能算通过）。
   */
  finish(options = {}) {
    const pass = this.results.filter((r) => r.status === 'PASS').length
    const fail = this.results.filter((r) => r.status === 'FAIL').length
    const skip = this.results.filter((r) => r.status === 'SKIP').length
    const recorded = this.results.filter((r) => r.status === 'RECORD').length
    const code = fail > 0 ? 1 : 0
    // 全 SKIP 的环境依赖门禁不能显示 PASS（防假绿）：一条真判据都没通过时，结论是 SKIP。
    // 同理，有检查项明确没跑（skipReason）时，PASS 也只能降为 SKIP。
    const verdict = fail > 0
      ? red('FAIL')
      : options.skipReason !== undefined || (pass === 0 && skip > 0)
        ? yellow('SKIP')
        : green('PASS')
    if (fail === 0 && options.skipReason !== undefined) {
      console.log(yellow(`\n本次未跑完整判据：${options.skipReason}`))
    }
    console.log(`\nRESULT: ${verdict}  ${this.id} ${this.title} — 通过 ${pass} / 失败 ${fail} / 跳过 ${skip}${recorded > 0 ? ` / 记录 ${recorded}` : ''}`)
    if (fail > 0) {
      console.log(red('  失败项：'))
      for (const r of this.results.filter((x) => x.status === 'FAIL')) console.log(red(`   · ${r.name}`))
    }
    console.log(dim(`  用时 ${((Date.now() - this.startedAt.getTime()) / 1000).toFixed(1)}s · 退出码 ${code}`))
    process.exitCode = code
    return code
  }
}

/** 运行子进程；永不抛异常，返回 { ok, code, stdout, stderr }。 */
export function run(command, args = [], { cwd, env, timeout = 600_000, input } = {}) {
  const result = spawnSync(command, args, {
    cwd,
    env: env ? { ...process.env, ...env } : process.env,
    encoding: 'utf8',
    timeout,
    input,
    maxBuffer: 256 * 1024 * 1024,
  })
  return {
    ok: result.status === 0 && !result.error,
    code: result.status,
    signal: result.signal,
    stdout: result.stdout ?? '',
    stderr: result.stderr ?? '',
    error: result.error,
  }
}

export function which(command) {
  const r = run('bash', ['-c', `command -v ${JSON.stringify(command)}`])
  return r.ok ? r.stdout.trim() : null
}

export function sha256File(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

export function sha256Text(text) {
  return createHash('sha256').update(text).digest('hex')
}

function walk(root) {
  const files = []
  const walkDir = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const abs = join(dir, entry.name)
      const rel = relative(root, abs).split(sep).join('/')
      let st
      try {
        st = lstatSync(abs)
      } catch {
        continue
      }
      if (st.isSymbolicLink()) {
        files.push({ path: rel, type: 'link', size: 0, mode: 'link', sha: '-' })
        continue
      }
      if (st.isDirectory()) {
        walkDir(abs)
        continue
      }
      if (!st.isFile()) continue
      files.push({
        path: rel,
        type: 'file',
        size: st.size,
        mode: (st.mode & 0o777).toString(8).padStart(4, '0'),
        sha: sha256File(abs),
      })
    }
  }
  if (existsSync(root)) walkDir(root)
  return files
}

/**
 * 文件树指纹：按路径字节序排序后对「sha256 size mode path」整段再 hash。
 * 用于 seed 幂等（同一目录跑两次指纹必须相同）。
 */
export function treeFingerprint(root) {
  const files = walk(root)
  files.sort((a, b) => Buffer.compare(Buffer.from(a.path), Buffer.from(b.path)))
  const text = files.map((f) => `${f.sha}  ${f.size}  ${f.mode}  ${f.path}\n`).join('')
  return {
    root,
    hash: 'tree-sha256:' + sha256Text(text),
    files: files.length,
    links: files.filter((f) => f.type === 'link').length,
    bytes: files.reduce((n, f) => n + f.size, 0),
  }
}

/** 与 seed-profile.sh --write-manifest 相同的清单算法（S2 §5.4）。 */
export function pluginManifest(root) {
  const files = walk(root).filter((f) => f.type === 'file')
  files.sort((a, b) => Buffer.compare(Buffer.from(a.path), Buffer.from(b.path)))
  const text = files.map((f) => `${f.sha}  ${f.size}  ${f.path}\n`).join('')
  return {
    files,
    symlinks: walk(root).filter((f) => f.type === 'link').length,
    rootHash: 'sha256:' + sha256Text(text),
    totalBytes: files.reduce((n, f) => n + f.size, 0),
  }
}

/** 读取 app-overlay.yml 的 5 键（最小 YAML 解析，不引依赖）。 */
export function parseOverlay(text) {
  const lines = text.split('\n')
  const start = lines.findIndex((l) => l.trim() === '- id: daniel')
  if (start < 0) return { found: false, config: {} }
  const config = {}
  let inConfig = false
  for (let i = start + 1; i < lines.length; i++) {
    const line = lines[i]
    if (/^- id:/.test(line)) break
    if (line.trim() === 'config:') { inConfig = true; continue }
    if (!inConfig) continue
    const m = /^    ([A-Za-z][A-Za-z0-9]*):\s?(.*)$/.exec(line)
    if (m) config[m[1]] = m[2].replace(/^"|"$/g, '')
  }
  return { found: true, config }
}

/** 解析 dump-config 里 `- id: daniel` 段的 config（结构同上）。 */
export function parseDumpConfig(text) {
  return parseOverlay(text)
}

export function readJsonSafe(path) {
  try {
    return JSON.parse(readFileSync(path, 'utf8'))
  } catch {
    return null
  }
}

export function ensureDir(path, mkdir) {
  return mkdir(path, { recursive: true })
}

export function rel(root, path) {
  return relative(root, path).split(sep).join('/')
}

export function exists(path) {
  return existsSync(path)
}

export function statSafe(path) {
  try {
    return statSync(path)
  } catch {
    return null
  }
}

/** 简单参数解析：--key value / --key=value / --flag */
export function parseArgs(argv, defaults = {}) {
  const out = { ...defaults }
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]
    if (!arg.startsWith('--')) continue
    const eq = arg.indexOf('=')
    if (eq > 2) {
      out[arg.slice(2, eq)] = arg.slice(eq + 1)
      continue
    }
    const key = arg.slice(2)
    const next = argv[i + 1]
    if (next === undefined || next.startsWith('--')) out[key] = true
    else { out[key] = next; i += 1 }
  }
  return out
}
