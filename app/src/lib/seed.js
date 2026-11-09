'use strict'
/**
 * 首次启动 / 每次启动的资源准备（S2 §3.1 步骤 4-5、§3.5）。
 *
 * 这里不重复实现一遍「复制插件 + 写 overlay + 校验哈希」——那是 M0 的 seed-profile.sh
 * （幂等、可单独跑、有退出码）。壳只负责在起 DSH 之前调它，并把失败翻译成错误页。
 */

const { spawn } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')
const { ShellError } = require('./config')

function findSeedScript(paths) {
  const candidates = [
    path.join(paths.appDir, 'scripts', 'seed-profile.sh'),
    paths.resources ? path.join(paths.resources, 'scripts', 'seed-profile.sh') : '',
    paths.resources ? path.join(paths.resources, 'seed-profile.sh') : '',
  ].filter(Boolean)
  for (const candidate of candidates) {
    try {
      if (fs.statSync(candidate).isFile()) return candidate
    } catch { /* 下一个 */ }
  }
  return ''
}

function exec(cmd, args, { timeoutMs = 180000 } = {}) {
  return new Promise((resolve) => {
    let child
    try {
      child = spawn(cmd, args, { stdio: ['ignore', 'pipe', 'pipe'] })
    } catch (e) {
      resolve({ code: -1, stdout: '', stderr: String(e) })
      return
    }
    const out = []
    const err = []
    let done = false
    const finish = (code) => {
      if (done) return
      done = true
      clearTimeout(timer)
      resolve({ code, stdout: Buffer.concat(out).toString('utf8'), stderr: Buffer.concat(err).toString('utf8') })
    }
    const timer = setTimeout(() => {
      try { child.kill('SIGKILL') } catch { /* ignore */ }
      finish(-2)
    }, timeoutMs)
    child.stdout.on('data', (c) => out.push(Buffer.from(c)))
    child.stderr.on('data', (c) => err.push(Buffer.from(c)))
    child.on('error', (e) => { err.push(Buffer.from(String(e))); finish(-1) })
    child.on('close', (code) => finish(code))
  })
}

/**
 * 跑 seed：--app 用 .app（打包后）或 Resources（开发期），两个 home 原样传。
 * 失败时把脚本的 stderr 直接端到错误页 —— 它本来就写得很具体（哪个文件哪个哈希）。
 */
async function runSeed(paths, logger, onStatus) {
  const script = findSeedScript(paths)
  if (!script) {
    throw new ShellError(
      'seed',
      '缺少初始化脚本',
      '找不到 scripts/seed-profile.sh，无法准备运行环境。',
      '期望位置：<app>/scripts/seed-profile.sh 或 <Resources>/scripts/seed-profile.sh'
    )
  }
  const appArg = paths.appBundle || paths.resources
  onStatus('正在准备运行环境…')
  const started = Date.now()
  const res = await exec('/bin/bash', [
    script, '--app', appArg, '--home', paths.danielHome, '--dsh-home', paths.dshHome,
  ])
  logger.raw(paths.seedLogFile, `$ /bin/bash ${script} --app ${appArg} --home ${paths.danielHome} --dsh-home ${paths.dshHome}`)
  if (res.stdout) logger.raw(paths.seedLogFile, res.stdout.trimEnd())
  if (res.stderr) logger.raw(paths.seedLogFile, res.stderr.trimEnd())
  logger.info(`seed 结束：退出码 ${res.code}，用时 ${Date.now() - started} ms`)

  if (res.code !== 0) {
    const detail = (res.stderr.trim() || res.stdout.trim() || `退出码 ${res.code}`).slice(-4000)
    const title = res.code === -2
      ? '初始化超时'
      : res.code === 3
        ? '安装校验没通过'
        : '初始化失败'
    throw new ShellError('seed', title, '准备运行环境时出错，Daniel 没有启动。', detail)
  }
  return { script, stdout: res.stdout }
}

module.exports = { runSeed, findSeedScript }
