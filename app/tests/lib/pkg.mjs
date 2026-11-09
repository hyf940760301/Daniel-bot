// DMG / .app 探测工具（G2 打包门禁与 G3 安装后运行门禁共用）
//
// 只读优先：所有函数都不修改被检产物；唯一写操作是创建/删除自己指定的临时挂载点。
// 不抛异常：失败一律以 { ok:false, ... } 返回，由门禁决定判 PASS/FAIL/SKIP。
import { existsSync, mkdirSync, readdirSync, rmSync, statSync } from 'node:fs'
import { basename, join } from 'node:path'
import process from 'node:process'
import { run } from './gate.mjs'

export const MB = 1_000_000
export const MIB = 1_048_576

/** 同步 sleep（门禁是线性流程，不需要事件循环）。 */
export function sleepSync(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms)
}

/** 字节数同时给人看的两套单位：10 进制 MB（与 Finder 一致）与 MiB（与 du -m 一致）。 */
export function humanSize(bytes) {
  const mb = bytes / MB
  const mib = bytes / MIB
  const gb = bytes / (MB * 1000)
  return gb >= 1
    ? `${mb.toFixed(1)} MB (${mib.toFixed(1)} MiB / ${gb.toFixed(2)} GB)`
    : `${mb.toFixed(1)} MB (${mib.toFixed(1)} MiB)`
}

function walk(root, depth, maxDepth, want, out) {
  let entries
  try {
    entries = readdirSync(root, { withFileTypes: true })
  } catch {
    return
  }
  for (const entry of entries) {
    if (entry.name === 'node_modules' || entry.name === '.git') continue
    const abs = join(root, entry.name)
    if (entry.isDirectory()) {
      if (depth < maxDepth) walk(abs, depth + 1, maxDepth, want, out)
      continue
    }
    if (entry.isFile() && want(entry.name)) out.push(abs)
  }
}

/** 在若干目录里找 .dmg（有界递归，跳过 node_modules/.git）。 */
export function collectDmgs(roots, maxDepth = 4) {
  const found = []
  for (const root of roots) {
    if (!existsSync(root)) continue
    walk(root, 0, maxDepth, (name) => name.toLowerCase().endsWith('.dmg'), found)
  }
  return found
}

/**
 * 解析 --dmg：文件直接用；目录取其中最新；不传则在候选目录里找最新。
 * @returns {{ path: string|null, candidates: Array<{path:string,size:number,mtime:Date}>, searched: string[] }}
 */
export function resolveDmg(explicit, roots) {
  const searched = [...roots]
  if (typeof explicit === 'string' && explicit !== '') {
    if (!existsSync(explicit)) return { path: null, candidates: [], searched: [explicit] }
    if (statSync(explicit).isDirectory()) {
      searched.unshift(explicit)
      const list = collectDmgs([explicit], 6)
      const candidates = list.map(toCandidate).sort((a, b) => b.mtime - a.mtime)
      return { path: candidates[0]?.path ?? null, candidates, searched }
    }
    return { path: explicit, candidates: [toCandidate(explicit)], searched }
  }
  const candidates = collectDmgs(roots).map(toCandidate).sort((a, b) => b.mtime - a.mtime)
  return { path: candidates[0]?.path ?? null, candidates, searched }
}

function toCandidate(path) {
  const st = statSync(path)
  return { path, size: st.size, mtime: st.mtime }
}

/**
 * 从 DMG 文件名里抽版本号。允许：
 *   deepseek-harness-0.2.2-alpha.2-mac-arm64-unsigned.dmg
 *   Daniel Bot-0.2.3-arm64.dmg
 * 预发布段遇到 -mac / -arm64 / -x64 / -universal / -unsigned 等构建后缀即停。
 */
export function versionCandidates(fileName) {
  const stem = basename(fileName).replace(/\.dmg$/i, '')
  const re = /(\d+\.\d+\.\d+(?:-(?!mac\b|arm64\b|x64\b|universal\b|unsigned\b|win\b|linux\b|intel\b)[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?)(?=-|$)/g
  return [...stem.matchAll(re)].map((m) => m[1])
}

/** 读 Info.plist（plutil 转 JSON，二进制 plist 也能读）。 */
export function readPlist(appPath) {
  const plist = join(appPath, 'Contents', 'Info.plist')
  if (!existsSync(plist)) return null
  const r = run('plutil', ['-convert', 'json', '-o', '-', plist], { timeout: 60_000 })
  if (!r.ok) return null
  try {
    return JSON.parse(r.stdout)
  } catch {
    return null
  }
}

/** 卷根下的 *.app（只列一层，DMG 常规布局）。 */
export function listApps(mountpoint) {
  let entries
  try {
    entries = readdirSync(mountpoint, { withFileTypes: true })
  } catch {
    return []
  }
  return entries
    .filter((e) => e.isDirectory() && e.name.endsWith('.app'))
    .map((e) => ({ name: e.name, path: join(mountpoint, e.name) }))
}

/** 挂载 DMG 到指定目录（只读、不弹 Finder、指定挂载点便于卸载校验）。 */
export function attachDmg(dmgPath, mountpoint) {
  mkdirSync(mountpoint, { recursive: true })
  const r = run('hdiutil', ['attach', '-nobrowse', '-readonly', '-mountpoint', mountpoint, dmgPath], { timeout: 300_000 })
  const devices = [...r.stdout.matchAll(/^(\/dev\/disk\d+(?:s\d+)?)\s+(\S.*)$/gm)].map((m) => ({ device: m[1], name: m[2].trim() }))
  return { ok: r.ok, code: r.code, stdout: r.stdout, stderr: r.stderr, devices }
}

/** 卸载；失败时 -force 重试两次（Spotlight/杀毒偶发占用）。 */
export function detachDmg(mountpoint) {
  const attempts = []
  let r = run('hdiutil', ['detach', mountpoint], { timeout: 120_000 })
  attempts.push({ args: ['detach', mountpoint], code: r.code, out: `${r.stdout}${r.stderr}`.trim() })
  for (let i = 0; i < 2 && !r.ok; i++) {
    sleepSync(1000)
    r = run('hdiutil', ['detach', '-force', mountpoint], { timeout: 120_000 })
    attempts.push({ args: ['detach', '-force', mountpoint], code: r.code, out: `${r.stdout}${r.stderr}`.trim() })
  }
  return { ok: r.ok, attempts, out: attempts.at(-1)?.out ?? '' }
}

/**
 * 卸载后的残留判定：三条独立证据，任一成立即判残留。
 *   ① hdiutil info 里还有这个挂载点（内核视角没卸）；
 *   ② 挂载点目录还能列出内容（说明还挂着，或卸载未清空）；
 *   ③ 挂载点目录消失/为空（正常）。
 */
export function mountResidual(mountpoint) {
  const info = run('hdiutil', ['info'], { timeout: 60_000 })
  const inInfo = info.stdout.includes(mountpoint)
  let entries = []
  try {
    entries = readdirSync(mountpoint)
  } catch {
    entries = []
  }
  return { residual: inInfo || entries.length > 0, inInfo, visibleEntries: entries, entries }
}

/** `codesign -dv --verbose=2`：输出在 stderr，按行取字段。 */
export function codesignDv(appPath) {
  const r = run('codesign', ['-dv', '--verbose=2', appPath], { timeout: 180_000 })
  const text = `${r.stderr}${r.stdout}`
  const field = (key) => new RegExp(`^${key}=(.*)$`, 'm').exec(text)?.[1]?.trim() ?? null
  return {
    ok: r.ok,
    text,
    signature: field('Signature'),
    identifier: field('Identifier'),
    team: field('TeamIdentifier'),
    format: field('Format'),
    sealedResources: field('Sealed Resources'),
    runtime: field('Runtime Version'),
  }
}

/** `codesign --verify --deep --strict`。 */
export function codesignVerify(appPath, { deep = true, strict = true, timeout = 600_000 } = {}) {
  const argv = ['--verify']
  if (deep) argv.push('--deep')
  if (strict) argv.push('--strict')
  argv.push(appPath)
  const r = run('codesign', argv, { timeout })
  return { ok: r.ok, code: r.code, out: `${r.stderr}${r.stdout}`.trim(), argv: `codesign ${argv.join(' ')}` }
}

/** 递归数文件（用于断言插件目录不是空壳）。 */
export function countFiles(root) {
  let count = 0
  const stack = [root]
  while (stack.length > 0) {
    const dir = stack.pop()
    let entries
    try {
      entries = readdirSync(dir, { withFileTypes: true })
    } catch {
      continue
    }
    for (const entry of entries) {
      const abs = join(dir, entry.name)
      if (entry.isDirectory()) stack.push(abs)
      else if (entry.isFile()) count += 1
    }
  }
  return count
}

/**
 * 逻辑体积统计（文件数 / 逻辑字节 / 软链数）。
 * 为什么不用 du：DMG 是压缩只读卷，du 报的是块占用；拷到 APFS 后同一份内容块占用会变大
 * （实测 1,041,492 KB → 1,073,708 KB，差 3%），拿 du 比较会把"拷贝成功"误判成 FAIL。
 */
export function treeStats(root) {
  let files = 0
  let bytes = 0
  let links = 0
  let dirs = 0
  const stack = [root]
  while (stack.length > 0) {
    const dir = stack.pop()
    let entries
    try {
      entries = readdirSync(dir, { withFileTypes: true })
    } catch {
      continue
    }
    for (const entry of entries) {
      const abs = join(dir, entry.name)
      if (entry.isSymbolicLink()) { links += 1; continue }
      if (entry.isDirectory()) { dirs += 1; stack.push(abs); continue }
      if (!entry.isFile()) continue
      files += 1
      try {
        bytes += statSync(abs).size
      } catch {
        // 读不到的按 0 计
      }
    }
  }
  return { files, dirs, links, bytes }
}

/** 目录占用（KB），用系统 du，比逐文件 stat 快得多。 */

export function dirSizeKb(path) {
  const r = run('/usr/bin/du', ['-sk', path], { timeout: 300_000 })
  const kb = Number.parseInt(r.stdout.trim().split(/\s+/)[0] ?? '', 10)
  return Number.isFinite(kb) ? kb : null
}

/** 当前是否有可用的图形登录会话（没有就绝不能判"启动失败=PASS"）。 */
export function graphicalSession() {
  const uid = typeof process.getuid === 'function' ? process.getuid() : null
  const gui = uid === null ? { ok: false, out: 'no uid' } : run('launchctl', ['print', `gui/${uid}`], { timeout: 15_000 })
  const consoleUser = run('stat', ['-f%Su', '/dev/console'], { timeout: 15_000 })
  const user = consoleUser.ok ? consoleUser.stdout.trim() : ''
  return {
    ok: gui.ok && user !== '' && user !== 'root' && user !== 'loginwindow',
    uid,
    guiOk: gui.ok,
    consoleUser: user,
    detail: gui.ok ? `gui/${uid} 可访问，控制台用户 ${user}` : `launchctl print gui/${uid} 失败：${`${gui.stderr}`.trim().slice(0, 200)}`,
  }
}

/**
 * 探测进程组状态：'alive' | 'gone' | 'denied'。
 * · ESRCH ⇒ 组里没有进程了（正常"已退出"）；
 * · EPERM ⇒ 组还在、但内核不允许我们给它发信号。注意 macOS 上**组里只剩僵尸/已无成员**时
 *   也可能返回 EPERM（实测：进程已被 SIGTERM 干掉后 `kill(-pgid,0)` 回报 EPERM 而不是 ESRCH），
 *   所以 EPERM 只能当"无法判定"，不能当"还活着"——否则永远等不到退出（G3 自测踩过这个坑）。
 */
export function probeGroup(pgid) {
  try {
    process.kill(-pgid, 0)
    return 'alive'
  } catch (error) {
    if (error.code === 'ESRCH') return 'gone'
    if (error.code === 'EPERM') return 'denied'
    return 'denied'
  }
}

/** 兼容旧调用：只有明确 alive 才算活着（EPERM 视为未判定，不再返回 true）。 */
export function processGroupAlive(pgid) {
  return probeGroup(pgid) === 'alive'
}

export function pidAlive(pid) {
  try {
    process.kill(pid, 0)
    return true
  } catch (error) {
    return error.code === 'EPERM'
  }
}

/** pgrep 用：把路径里的正则元字符转义。 */
export function escapeRegex(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** 清掉自己建的挂载点目录（已卸载后才调用）。 */
export function removeMountpoint(dir) {
  try {
    rmSync(dir, { recursive: true, force: true })
  } catch {
    // 挂载点删不掉不影响结论，残留检查已经单独判过。
  }
}
