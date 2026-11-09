'use strict'
/**
 * DSH 子进程（S2 §3.1 / §3.4 / §3.5 / D-041）。
 *
 *   argv：<dsh>/lib/bin.js --profile web --patch <overlay> --no-open --port 0
 *   （🔴 --patch 必须排在 --no-open/--port 之前：解析器在第一个未知参数之后进入
 *     pass-through，写在后面会被当成 web app 的参数，报 `unknown option '--patch'`）
 *
 *   env ：PATH 前置随包 python/node、两个 home、遥测双关、ELECTRON_RUN_AS_NODE
 *   扫描：stdout ＋ stderr 逐行，就绪行 /^dsh web: http:\/\/127\.0\.0\.1:(\d+)\/\?token=(\S+)$/
 *   退出：detached=true 自成一个进程组，杀 -pid（不杀只留 DSH 会剩 python 孙进程）
 */

const { spawn, execFileSync } = require('node:child_process')
const readline = require('node:readline')
const fs = require('node:fs')
const path = require('node:path')
const { isDir } = require('./config')

const READY_RE = /^dsh web: http:\/\/127\.0\.0\.1:(\d+)\/\?token=(\S+)$/
const SKIP_RE = /skipping profile bundle\s+"daniel-dsh-plugin"/
const MIN_NODE = { major: 22, minor: 18 } // import.meta.main 要求 ≥22.18（R-01）

class DshError extends Error {
  constructor(kind, title, detail = '') {
    super(title)
    this.name = 'DshError'
    this.kind = kind // node | dsh | plugin
    this.detail = detail
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/** 解释器优先级（D-041）：DSH_NODE_BIN → Resources/runtime/node → 系统 node */
function findNode(paths) {
  const candidates = []
  if (process.env.DSH_NODE_BIN) candidates.push({ bin: process.env.DSH_NODE_BIN, source: 'DSH_NODE_BIN' })
  if (paths.bundledNode) candidates.push({ bin: paths.bundledNode, source: 'Resources/runtime/node' })
  for (const dir of (process.env.PATH || '').split(':').filter(Boolean)) {
    candidates.push({ bin: path.join(dir, 'node'), source: `PATH (${dir})` })
  }
  for (const c of candidates) {
    try {
      if (!fs.statSync(c.bin).isFile()) continue
      fs.accessSync(c.bin, fs.constants.X_OK)
      return c
    } catch { /* 下一个 */ }
  }
  return null
}

/** 版本探针：低版本 Node 会让 DSH 入口静默不执行（零输出、exit 0），必须在起服务前拦住 */
function probeNodeVersion(bin) {
  let out
  try {
    out = execFileSync(bin, ['-v'], {
      encoding: 'utf8',
      timeout: 8000,
      env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' },
    }).trim()
  } catch (e) {
    throw new DshError('node', '无法运行 Node', `执行 ${bin} -v 失败：${e.message}`)
  }
  const m = out.match(/^v(\d+)\.(\d+)\.(\d+)/)
  if (!m) throw new DshError('node', '无法识别 Node 版本', `输出：${out}`)
  const version = { major: Number(m[1]), minor: Number(m[2]), patch: Number(m[3]) }
  if (version.major < MIN_NODE.major || (version.major === MIN_NODE.major && version.minor < MIN_NODE.minor)) {
    throw new DshError(
      'node',
      'Node 版本过低',
      `当前 ${out}，需要 ≥22.18（否则 DSH 入口静默不执行）。\n请用 DSH_NODE_BIN 指定，或把 Node 放进 Resources/runtime/node。`
    )
  }
  return { version: out, ...version }
}

class DshService {
  constructor({ paths, logger, onStatus, onExit }) {
    this.paths = paths
    this.logger = logger
    this.onStatus = onStatus || (() => {})
    this.onExit = onExit || null
    this.child = null
    this.ready = null
    this.stopping = false
    this.node = null
  }

  buildEnv() {
    const env = { ...process.env }
    const parts = [
      this.paths.pythonBin ? path.dirname(this.paths.pythonBin) : '',
      this.paths.bundledNode ? path.dirname(this.paths.bundledNode) : '',
      env.PATH || '',
    ].filter(Boolean)
    env.PATH = parts.join(':')
    env.DSH_HOME = this.paths.dshHome
    env.DANIEL_HOME = this.paths.danielHome
    env.DANIEL_NO_OPEN = '1'
    if (this.paths.cliTools && isDir(this.paths.cliTools)) env.DANIEL_CLI_TOOLS = this.paths.cliTools
    env.DSH_TELEMETRY_MODE = 'DISABLED'
    env.DSH_TELEMETRY_DISABLED = '1'
    // D-041 下解释器是 Node；这项只在有人把 DSH_NODE_BIN 指到 Electron 二进制时才起作用
    env.ELECTRON_RUN_AS_NODE = '1'
    delete env.DANIEL_PASSWORD
    return env
  }

  /** 启动（失败按 1s/3s/9s 退避重拉；插件被跳过不重试——重试不会让 bundle 长出 dsh.bundle） */
  async start() {
    const node = findNode(this.paths)
    if (!node) {
      throw new DshError(
        'node',
        '找不到 Node 运行时',
        '按 D-041 的顺序找过：DSH_NODE_BIN → Resources/runtime/node/bin/node → PATH 里的 node，都没有可执行的。'
      )
    }
    const probed = probeNodeVersion(node.bin)
    this.node = node
    this.logger.info(`DSH 解释器：${node.bin}（来源 ${node.source}，${probed.version}）`)

    const delays = [1000, 3000, 9000]
    let last = null
    for (let attempt = 0; attempt <= delays.length; attempt++) {
      if (attempt > 0) {
        this.onStatus(`正在重启服务（第 ${attempt} 次）…`)
        await sleep(delays[attempt - 1])
      }
      try {
        return await this.spawnOnce()
      } catch (e) {
        last = e
        this.logger.error(`DSH 启动失败（第 ${attempt + 1} 次）：${e.message}`)
        if (e.kind === 'plugin') throw e
      }
    }
    throw last || new DshError('dsh', '服务启动失败')
  }

  spawnOnce() {
    const argv = [
      this.paths.dshBin,
      '--profile', 'web',
      '--patch', this.paths.overlay,
      '--no-open', '--port', '0',
    ]
    return new Promise((resolve, reject) => {
      let child
      try {
        child = spawn(this.node.bin, argv, {
          detached: true,             // 自成进程组：退出时才能 kill(-pid) 连孙进程一起收
          stdio: ['ignore', 'pipe', 'pipe'],
          env: this.buildEnv(),
        })
      } catch (e) {
        reject(new DshError('dsh', '无法启动服务进程', String(e)))
        return
      }
      this.child = child
      this.stopping = false
      this.onStatus('正在启动服务…')
      this.logger.info(`启动 DSH：${this.node.bin} ${argv.join(' ')}`)

      let settled = false
      let timer = null
      const done = (fn, value) => {
        if (settled) return
        settled = true
        if (timer) clearTimeout(timer)
        fn(value)
      }

      timer = setTimeout(() => {
        done(reject, new DshError('dsh', '服务启动超时（60 秒）', this.logger.tail(40)))
        this.killChild('SIGTERM')
      }, 60000)

      const handleLine = (line) => {
        const text = String(line)
        this.logger.raw(this.paths.dshLogFile, text)

        if (SKIP_RE.test(text)) {
          // §3.5：宁可报错，也不静默降级成「没有 Daniel 的 DSH」
          done(reject, new DshError('plugin', '能力包没有挂上', text))
          this.killChild('SIGTERM')
          return
        }
        const m = text.match(READY_RE)
        if (m && m[2].length > 0) {
          this.ready = {
            url: `http://127.0.0.1:${m[1]}/?token=${m[2]}`,
            port: Number(m[1]),
            token: m[2],
            pid: child.pid,
          }
          this.logger.info(`服务就绪：127.0.0.1:${m[1]}（token 已打码）`)
          done(resolve, this.ready)
        }
      }

      const rlOut = readline.createInterface({ input: child.stdout })
      const rlErr = readline.createInterface({ input: child.stderr })
      rlOut.on('line', handleLine)
      rlErr.on('line', handleLine)

      child.once('error', (e) => {
        done(reject, new DshError('dsh', '无法启动服务进程', String(e)))
      })

      child.once('exit', (code, signal) => {
        const wasReady = Boolean(this.ready) && !this.stopping
        this.logger.warn(`DSH 退出：code=${code} signal=${signal}`)
        this.child = null
        this.ready = null
        if (wasReady && this.onExit) this.onExit({ code, signal })
        done(reject, new DshError('dsh', '服务进程意外退出', `退出码 ${code} / 信号 ${signal}\n\n${this.logger.tail(30)}`))
      })
    })
  }

  killChild(signal) {
    const child = this.child
    if (!child || !child.pid) return
    try {
      process.kill(-child.pid, signal)
    } catch (e) {
      if (e.code !== 'ESRCH') {
        try { child.kill(signal) } catch { /* 已经没了 */ }
      }
    }
  }

  /** 收尾：SIGTERM 进程组 → 8 秒 → SIGKILL → 用 kill(-pgid, 0) 证明整组不存在 */
  async stop() {
    const child = this.child
    const ready = this.ready
    this.stopping = true
    this.ready = null
    if (!child || !child.pid) {
      this.child = null
      this.stopping = false
      return { wasRunning: false, pid: 0, groupAlive: false, hadReady: Boolean(ready) }
    }

    const pid = child.pid
    let exited = child.exitCode !== null || child.signalCode !== null
    const onExit = () => { exited = true }
    child.once('exit', onExit)

    try {
      process.kill(-pid, 'SIGTERM')
      this.logger.info(`已向进程组 -${pid} 发 SIGTERM`)
    } catch (e) {
      if (e.code !== 'ESRCH') {
        try { child.kill('SIGTERM') } catch { /* ignore */ }
      }
    }

    const deadline = Date.now() + 8000
    while (!exited && Date.now() < deadline) await sleep(100)

    if (!exited) {
      try {
        process.kill(-pid, 'SIGKILL')
        this.logger.warn(`进程组 -${pid} 未在 8 秒内退出，已发 SIGKILL`)
      } catch { /* 已退出 */ }
      const hardDeadline = Date.now() + 2000
      while (!exited && Date.now() < hardDeadline) await sleep(50)
    }

    try { child.removeListener('exit', onExit) } catch { /* ignore */ }
    await sleep(150)

    let groupAlive = true
    try {
      process.kill(-pid, 0) // 探活：整组还有没有进程
    } catch (e) {
      groupAlive = e.code !== 'ESRCH'
    }
    this.logger.info(`进程组 -${pid} 探活：${groupAlive ? '仍在' : '已清空'}`)
    this.child = null
    this.stopping = false
    return { wasRunning: true, pid, groupAlive, hadReady: Boolean(ready) }
  }
}

module.exports = { DshService, DshError, findNode, probeNodeVersion, READY_RE, SKIP_RE }
