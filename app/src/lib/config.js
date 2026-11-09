'use strict'
/**
 * 路径与环境解析。
 *
 * 依据 S2 §2.5（两个 home）与 D-041（运行时裁决：DSH 用 Node，不用 Electron）：
 *   DANIEL_HOME  Daniel CLI / 插件的数据落点（会话、overlay、日志、窗口状态）
 *   DSH_HOME     DSH 自己的数据落点（profiles/…）
 *   Resources    随包资源（dsh/、vendor/daniel-dsh-plugin、runtime/…、PLUGIN-MANIFEST.json）
 *
 * 开发期用环境变量覆盖（本机沙箱不让写 ~/Library，验收时把两个 home 指到可写目录）：
 *   DANIEL_RESOURCES  Resources 目录
 *   DANIEL_HOME / DSH_HOME
 *   DSH_NODE_BIN      指定跑 DSH 的 Node（D-041：缺省 Resources/runtime/node → 系统 node）
 */

const path = require('node:path')
const fs = require('node:fs')
const { app } = require('electron')

/** 外壳自己的错误：kind 决定错误页文案与「重试」行为 */
class ShellError extends Error {
  constructor(kind, title, message, detail = '') {
    super(message)
    this.name = 'ShellError'
    this.kind = kind
    this.title = title
    this.detail = detail
  }
}

function isDir(p) {
  try { return fs.statSync(p).isDirectory() } catch { return false }
}
function isFile(p) {
  try { return fs.statSync(p).isFile() } catch { return false }
}

/** Resources 目录：env > 打包时的 resourcesPath > 开发期 <appDir>/Resources */
function resolveResources(appDir) {
  if (process.env.DANIEL_RESOURCES) return path.resolve(process.env.DANIEL_RESOURCES)
  if (app.isPackaged) return process.resourcesPath
  const local = path.join(appDir, 'Resources')
  return isDir(path.join(local, 'vendor', 'daniel-dsh-plugin')) ? local : ''
}

function getPaths() {
  const appDir = app.getAppPath()
  const resources = resolveResources(appDir)
  const userData = app.getPath('userData')

  const danielHome = process.env.DANIEL_HOME
    ? path.resolve(process.env.DANIEL_HOME)
    : path.join(userData, 'daniel-home')
  const dshHome = process.env.DSH_HOME
    ? path.resolve(process.env.DSH_HOME)
    : path.join(userData, 'dsh-home')

  const logsDir = path.join(danielHome, 'logs')
  // 打包后 seed 脚本要拿 .app 路径（它自己会找 Contents/Resources 与应用自带 Electron）
  const appBundle = app.isPackaged ? path.resolve(process.execPath, '../../..') : ''

  return {
    appDir,
    appBundle: appBundle && isDir(path.join(appBundle, 'Contents', 'Resources')) ? appBundle : '',
    resources,
    danielHome,
    dshHome,
    logsDir,
    overlay: path.join(danielHome, 'app-overlay.yml'),
    sessionFile: path.join(danielHome, 'session', 'session.json'),
    windowFile: path.join(danielHome, 'window.json'),
    logFile: path.join(logsDir, 'app.log'),
    dshLogFile: path.join(logsDir, 'dsh.log'),
    seedLogFile: path.join(logsDir, 'seed.log'),
    profileDir: path.join(dshHome, 'profiles', 'web'),
    dshBin: resources ? path.join(resources, 'dsh', 'lib', 'bin.js') : '',
    pluginSrc: resources ? path.join(resources, 'vendor', 'daniel-dsh-plugin') : '',
    pluginManifest: resources ? path.join(resources, 'PLUGIN-MANIFEST.json') : '',
    pythonBin: resources ? path.join(resources, 'runtime', 'python', 'bin', 'python3') : '',
    bundledNode: resources ? path.join(resources, 'runtime', 'node', 'bin', 'node') : '',
    cliTools: resources ? path.join(resources, 'bundle', '.kol-tools') : '',
  }
}

/** 建目录（0700）—— 只在需要时调，别在启动路径上乱写 */
function ensureDir(dir, mode = 0o700) {
  fs.mkdirSync(dir, { recursive: true, mode })
  try { fs.chmodSync(dir, mode) } catch { /* 目录可能已在别处收紧，忽略 */ }
}

/**
 * 校验 Resources 是否齐全（缺什么就报什么，别让 DSH 报一句看不懂的 ENOENT）。
 */
function assertResources(paths) {
  if (!paths.resources) {
    throw new ShellError(
      'env',
      '找不到应用资源',
      '没有定位到随包资源目录（dsh / 插件 / 运行时）。',
      '开发期请设置 DANIEL_RESOURCES；打包后它应位于 <App>.app/Contents/Resources。'
    )
  }
  const missing = [
    ['dsh 入口', paths.dshBin],
    ['插件包', path.join(paths.pluginSrc, 'package.json')],
  ].filter(([, p]) => !isFile(p))
  if (missing.length > 0) {
    throw new ShellError(
      'env',
      '安装不完整',
      `缺少随包资源：${missing.map(([n]) => n).join('、')}。`,
      missing.map(([n, p]) => `${n}：${p}`).join('\n')
    )
  }
}

module.exports = { getPaths, ensureDir, assertResources, ShellError, isDir, isFile }
