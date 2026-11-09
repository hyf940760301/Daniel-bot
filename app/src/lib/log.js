'use strict'
/**
 * 日志与脱敏。
 *
 * 纪律（S2 §4.1）：密码只在内存活到请求结束，永不落盘、永不进日志；
 * 就绪 URL 里的 token、会话 cookie 一律打码。日志只写本机 DANIEL_HOME/logs。
 */

const fs = require('node:fs')
const path = require('node:path')

const SCRUB = [
  // 就绪行里的 token（`?token=...`）
  [/([?&]token=)[A-Za-z0-9_\-]+/g, '$1***'],
  // 会话 cookie
  [/(app_session_id=)[^;\s"'\\]+/g, '$1***'],
  [/(["']?password["']?\s*[:=]\s*["']?)[^"',\s}]+/gi, '$1***'],
  [/(["']?email["']?\s*[:=]\s*["']?)[^"',\s}]+@[^"',\s}]+/gi, '$1***'],
]

/** 把敏感串打码；日志、错误页、诊断信息都先过这一层 */
function scrub(text) {
  if (typeof text !== 'string') return ''
  let out = text
  for (const [re, rep] of SCRUB) out = out.replace(re, rep)
  return out
}

class Logger {
  constructor(paths, { ringSize = 200 } = {}) {
    this.paths = paths
    this.ringSize = ringSize
    this.ring = []
    this.ready = false
  }

  init() {
    try {
      fs.mkdirSync(this.paths.logsDir, { recursive: true, mode: 0o700 })
      try { fs.chmodSync(this.paths.logsDir, 0o700) } catch { /* ignore */ }
      this.ready = true
    } catch {
      this.ready = false
    }
  }

  /** 外壳自己的事件（带时间戳） */
  app(level, message) {
    const line = `${new Date().toISOString()} ${level} ${scrub(String(message))}`
    this._append(this.paths.logFile, line + '\n')
  }

  info(message) { this.app('INFO', message) }
  warn(message) { this.app('WARN', message) }
  error(message) { this.app('ERROR', message) }

  /** 子进程原始输出（已脱敏，保留行序，便于排障） */
  raw(file, line) {
    this._append(file, scrub(line) + '\n')
    this.ring.push(scrub(line))
    if (this.ring.length > this.ringSize) this.ring.shift()
  }

  /** 最近 n 行（给错误页 / 诊断信息） */
  tail(n = 20) {
    return this.ring.slice(-n).join('\n')
  }

  _append(file, text) {
    if (!this.ready) this.init()
    if (!this.ready) return
    try { fs.appendFileSync(file, text, { mode: 0o600 }) } catch { /* 日志失败不该拖垮应用 */ }
  }

  /** 诊断信息（复制到剪贴板用） */
  diagnostics() {
    const p = this.paths
    return [
      `Daniel Bot ${require('../../package.json').version}`,
      `Electron ${process.versions.electron} / Node ${process.versions.node} / Chromium ${process.versions.chrome}`,
      `platform ${process.platform} ${process.arch} ${require('node:os').release()}`,
      `resources ${p.resources || '(未找到)'}`,
      `DANIEL_HOME ${p.danielHome}`,
      `DSH_HOME ${p.dshHome}`,
      `log ${p.logFile}`,
      `dshLog ${p.dshLogFile}`,
      '',
      '--- 最近输出 ---',
      this.tail(60),
    ].join('\n')
  }
}

module.exports = { Logger, scrub, ensureLogDir: (dir) => fs.mkdirSync(dir, { recursive: true, mode: 0o700 }) }
