#!/usr/bin/env node
/**
 * G3 · 安装后运行门禁（拷贝 → 启动 → 独立 home → 退出）
 *
 * 独立运行：
 *   node daniel-bot/app/tests/g3-install-gate.mjs --app "<path>/Daniel Bot.app"
 *   node daniel-bot/app/tests/g3-install-gate.mjs --dmg /tmp/dsh-build/.../unsigned-artifacts/xxx.dmg
 *   node daniel-bot/app/tests/g3-install-gate.mjs --dmg <dmg> --preflight   # 只做拷贝+签名预检，不启动
 *
 * 参数：
 *   --app <path>    .app 路径（可直接指向挂载卷里的 .app；脚本会先 ditto 到临时目录再跑）
 *   --dmg <path>    直接给 DMG：脚本自己挂载、取卷内 .app、拷走、卸载
 *   --dest <dir>    拷贝目标目录，默认 /tmp/qa-app（每次运行先清空）
 *   --home <dir>    独立 home 断言目标，默认 "$HOME/Library/Application Support/Daniel Bot"
 *   --preflight     只做「拷贝 + 签名验证 + 静态预检」，不启动 app（启动类检查记 SKIP，结论降为 SKIP）
 *   --quit <mode>   group（默认，向 app 自己的进程组发 SIGTERM，最安全，不会误伤同名应用）
 *                   | osascript（走 AppleEvent 正常退出流程，可能被退出确认框拦住）
 *   --keep          保留 /tmp/qa-app 下的副本（默认跑完删除；启动日志始终保留）
 *   --help          本说明
 *
 * 退出码：0 = 无 FAIL（含"未启动 ⇒ SKIP"）；1 = 存在 FAIL；2 = 参数/环境错误（没给产物等）。
 *
 * 判定纪律：
 *   · 没有图形会话、或本次不启动（--preflight）⇒ 启动类检查 **SKIP，不判 PASS**，结论行也是 SKIP；
 *   · 有图形会话但进程 10 秒内不出现 ⇒ FAIL（并贴启动日志尾部）；
 *   · 进程起来后 1.5 秒复查（抓"起来就崩"的假绿）；
 *   · 独立 home 不存在 ⇒ FAIL（D-044 核心：能力与数据都落在 Daniel Bot 自己的 home）；
 *   · 退出以「5 秒内进程组消失（ESRCH）」为准，靠 SIGKILL 才退出的也判 FAIL。
 */
import { spawn } from 'node:child_process'
import { closeSync, existsSync, mkdirSync, openSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs'
import { homedir } from 'node:os'
import { basename, dirname, join, resolve as resolvePath } from 'node:path'
import { fileURLToPath } from 'node:url'
import process from 'node:process'
import { Gate, dim, parseArgs, run } from './lib/gate.mjs'
import {
  attachDmg, codesignVerify, detachDmg, escapeRegex, graphicalSession, humanSize,
  listApps, pidAlive, probeGroup, readPlist, resolveDmg, treeStats,
} from './lib/pkg.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const BUILD_ROOT = '/tmp/dsh-build/dsh-src/apps/desktop/.desktop-build'
const RELEASES = join(HERE, '..', '..', 'releases')

const args = parseArgs(process.argv.slice(2), {
  app: '',
  dmg: '',
  dest: '/tmp/qa-app',
  home: join(homedir(), 'Library', 'Application Support', 'Daniel Bot'),
  preflight: false,
  quit: 'group',
  keep: false,
})

if (args.help) {
  console.log(`G3 安装后运行门禁 · 用法

  node daniel-bot/app/tests/g3-install-gate.mjs --app "<path>/Daniel Bot.app"
  node daniel-bot/app/tests/g3-install-gate.mjs --dmg <path.dmg>

  --app <path>    .app 路径（脚本先 ditto 到 --dest，避免在只读卷上跑）
  --dmg <path>    DMG 路径（脚本自己挂载 / 取 .app / 卸载）
  --dest <dir>    拷贝目标，默认 /tmp/qa-app（每次先清空）
  --home <dir>    独立 home 断言目标，默认 "$HOME/Library/Application Support/Daniel Bot"
  --preflight     只做拷贝+签名+静态预检，不启动 app（沙箱/无人值守时用；结论降为 SKIP）
  --quit <mode>   group（默认，给 app 自己的进程组 SIGTERM）| osascript（正常退出流程）
  --keep          保留 /tmp/qa-app 下的副本
  --help          本说明

检查项：ditto 拷贝 + 副本签名 / 10 秒内进程出现 / 日志无 "skipping profile bundle" /
        ~/Library/Application Support/Daniel Bot 生成且 0700 / 5 秒内退出（ESRCH）/ Gatekeeper 评估（记录）。
退出码：0 无 FAIL（可含 SKIP）；1 有 FAIL；2 参数或环境错误。`)
  process.exit(0)
}

const DEST = String(args.dest)
const HOME_TARGET = String(args.home)
const PREFLIGHT = Boolean(args.preflight) || Boolean(args['no-launch'])
const GUI = graphicalSession()

if (DEST === '/' || DEST === homedir() || DEST === resolvePath(homedir())) {
  console.error(`[G3] --dest 不能是 ${DEST}（脚本会先清空该目录）`)
  process.exit(2)
}
if (process.platform !== 'darwin') {
  console.error(`[G3] 本门禁只支持 macOS（当前 ${process.platform}）`)
  process.exit(2)
}
const NO_INPUT = String(args.app) === '' && String(args.dmg) === ''

const gate = new Gate('G3', '安装后运行门禁 · 启动 / 独立 home / 退出')
const state = {
  mountPoint: null,
  detached: false,
  sourceApp: null,
  copiedApp: null,
  appName: basename(String(args.app).replace(/\/$/, ''), '.app'),
}

gate.info(`图形会话：${GUI.ok ? '可用' : '不可用'}（${GUI.detail}）`)
gate.info(`拷贝目标：${DEST}`)
gate.info(`独立 home 断言：${HOME_TARGET}`)

let continued = false
try {
  if (NO_INPUT) {
    skipNoArtifact()
  } else {
    continued = prepare()
    if (continued) await launchPhase()
    else gate.info('前置检查未通过，跳过启动类检查')
  }
} catch (error) {
  gate.check('G3-99 门禁自身未抛异常', {
    expected: '门禁应把失败转成 FAIL 而不是崩溃',
    actual: `${error?.stack ?? String(error)}`.split('\n').slice(0, 6).join('\n'),
    ok: false,
  })
} finally {
  ensureDetach()
  if (state.copiedApp !== null && !Boolean(args.keep)) {
    rmSync(DEST, { recursive: true, force: true })
    gate.info(dim(`副本 ${DEST} 已删除（--keep 可保留）`))
  } else if (state.copiedApp !== null) {
    gate.info(dim(`副本保留在 ${DEST}`))
  }
}

process.exitCode = gate.finish({
  skipReason: NO_INPUT
    ? '没有给 --app/--dmg（还没出包，或这次只想跑其它门禁）'
    : PREFLIGHT
      ? '以 --preflight 运行：只验产物与签名，启动 / 独立 home / 退出三项没有执行'
      : !GUI.ok
        ? `没有可用的图形会话（${GUI.detail}）：启动类检查没有执行`
        : undefined,
})

// ── 前置：解析产物 → 拷贝 → 副本签名 ────────────────────────────────────────
function prepare() {
  if (!resolveSource()) return false

  const copyTarget = join(DEST, basename(state.sourceApp))
  state.appName = basename(state.sourceApp, '.app')

  rmSync(DEST, { recursive: true, force: true })
  mkdirSync(DEST, { recursive: true })
  const ditto = run('ditto', [state.sourceApp, copyTarget], { timeout: 900_000 })
  const src = ditto.ok ? treeStats(state.sourceApp) : null
  const dst = ditto.ok ? treeStats(copyTarget) : null
  // 用「文件数 + 逻辑字节」而不是 du：DMG 是压缩只读卷，块占用与 APFS 不同（实测差 3%）。
  const same = src !== null && dst !== null && src.files === dst.files && src.bytes === dst.bytes && src.links === dst.links
  gate.check('G3-1a ditto 拷贝到可写目录', {
    expected: 'ditto 退出码 0，副本与源文件数/逻辑字节/软链数完全一致',
    actual: ditto.ok && src && dst
      ? `退出码 0；源 ${src.files} 文件 / ${humanSize(src.bytes)} / ${src.links} 软链 → 副本 ${dst.files} 文件 / ${humanSize(dst.bytes)} / ${dst.links} 软链`
      : `退出码 ${String(ditto.code)}（未统计）`,
    ok: ditto.ok && same,
    detail: ditto.ok ? '' : `${ditto.stderr}`.trim().slice(-800),
  })
  if (!ditto.ok) return false
  state.copiedApp = copyTarget

  const verify = codesignVerify(copyTarget)
  gate.check('G3-1b 副本 codesign --verify --deep --strict', {
    expected: '退出码 0（拷贝不能破坏 adhoc 签名）',
    actual: `退出码 ${String(verify.code)}${verify.out === '' ? '，输出为空' : ''}`,
    ok: verify.ok,
    detail: verify.ok ? '' : verify.out,
  })

  const plist = readPlist(copyTarget)
  state.plist = plist
  state.bundleExec = String(plist?.CFBundleExecutable ?? state.appName)
  state.displayName = String(plist?.CFBundleName ?? state.appName)
  state.bundleId = String(plist?.CFBundleIdentifier ?? '')
  state.exePath = join(copyTarget, 'Contents', 'MacOS', state.bundleExec)
  gate.record(
    'G3-1c 产物身份（记录）',
    `${state.displayName} / ${state.bundleId || '(无 bundle id)'} / v${String(plist?.CFBundleShortVersionString ?? '?')}`,
  )

  const exeStat = existsSync(state.exePath) ? statSync(state.exePath) : null
  gate.check('G3-1d Contents/MacOS 可执行文件', {
    expected: 'Contents/MacOS/<CFBundleExecutable> 存在且可执行',
    actual: exeStat === null ? `缺失：${state.exePath}` : `${state.bundleExec}（${(exeStat.mode & 0o777).toString(8).padStart(4, '0')}）`,
    ok: exeStat !== null && (exeStat.mode & 0o111) !== 0,
  })
  return exeStat !== null && (exeStat.mode & 0o111) !== 0
}

function resolveSource() {
  if (String(args.app) !== '') {
    const app = resolvePath(String(args.app))
    const ok = existsSync(join(app, 'Contents', 'Info.plist'))
    gate.check('G3-0 解析待测 .app', {
      expected: '--app 指向含 Contents/Info.plist 的 .app',
      actual: ok ? app : `${app} 不存在或不是 .app`,
      ok,
    })
    if (!ok) return false
    state.sourceApp = app
    return true
  }

  const found = resolveDmg(String(args.dmg), [BUILD_ROOT, RELEASES])
  const dmgPath = found.path ?? String(args.dmg)
  state.mountPoint = join('/tmp', `qa-g3-mnt-${process.pid}`)
  rmSync(state.mountPoint, { recursive: true, force: true })
  const attach = attachDmg(dmgPath, state.mountPoint)
  if (!attach.ok) {
    gate.check('G3-0 从 DMG 取 .app', {
      expected: `hdiutil attach 成功并列出 .app（${dmgPath}）`,
      actual: `attach 退出码 ${String(attach.code)}`,
      ok: false,
      detail: `${attach.stdout}${attach.stderr}`.trim().slice(-800),
    })
    return false
  }
  const apps = listApps(state.mountPoint)
  if (apps.length === 0) {
    gate.check('G3-0 从 DMG 取 .app', { expected: '卷根至少 1 个 .app', actual: '0 个', ok: false })
    return false
  }
  state.sourceApp = apps[0].path
  gate.check('G3-0 从 DMG 取 .app', {
    expected: '挂载成功且卷内有 .app',
    actual: `${basename(dmgPath)} → ${apps.map((a) => a.name).join(', ')}`,
    ok: true,
  })
  return true
}

function ensureDetach() {
  if (state.mountPoint === null || state.detached) return
  state.detached = true
  const detach = detachDmg(state.mountPoint)
  if (detach.ok) gate.info(`卸载临时 DMG：成功（${state.mountPoint}）`)
  else gate.check('G3-0b 卸载临时 DMG', { expected: 'hdiutil detach 退出 0', actual: String(detach.attempts.at(-1)?.code), ok: false, detail: detach.out })
  rmSync(state.mountPoint, { recursive: true, force: true })
}

// ── 启动 / 日志 / home / 退出 ───────────────────────────────────────────────
async function launchPhase() {
  if (PREFLIGHT) {
    skipLaunchChecks('以 --preflight 运行：只验产物与签名，不启动 app')
    return
  }
  if (!GUI.ok) {
    skipLaunchChecks(`没有可用的图形会话（${GUI.detail}）`)
    return
  }
  await runLaunchPhase()
}

function skipNoArtifact() {
  const how = '出包后：node daniel-bot/app/tests/g3-install-gate.mjs --dmg /tmp/dsh-build/dsh-src/apps/desktop/.desktop-build/targets/mac-arm64/unsigned-artifacts/*.dmg'
  for (const name of [
    'G3-0 解析待测 .app',
    'G3-1a ditto 拷贝到可写目录',
    'G3-1b 副本 codesign --verify --deep --strict',
    'G3-2a 10 秒内进程出现',
    'G3-2c 日志无 "skipping profile bundle"',
    'G3-3a ~/Library/Application Support/Daniel Bot/ 生成',
    'G3-3b 独立 home 权限 0700',
    'G3-4 5 秒内退出（进程组 ESRCH）',
  ]) {
    gate.skip(name, '没有给 --app/--dmg（尚未出包）', how)
  }
}

function skipLaunchChecks(reason) {
  gate.skip('G3-2a 10 秒内进程出现', reason, `手工跑：open -n "${join(DEST, basename(state.sourceApp))}"`)
  gate.skip('G3-2b 启动后 1.5 秒仍存活', reason, '同上')
  gate.skip('G3-2c 日志无 "skipping profile bundle"', reason, '手工跑后读 app 的 stdout/stderr 或 ~/Library/Logs/<AppName>')
  gate.skip('G3-3a ~/Library/Application Support/Daniel Bot/ 生成', reason, `手工跑后：ls -ld "${HOME_TARGET}"`)
  gate.skip('G3-3b 独立 home 权限 0700', reason, `手工跑后：stat -f '%Sp %N' "${HOME_TARGET}"`)
  gate.skip('G3-3c dsh-home / daniel-home 子目录', reason, `手工跑后：ls -la "${HOME_TARGET}"`)
  gate.skip('G3-4 5 秒内退出（进程组 ESRCH）', reason, `手工跑：osascript -e 'quit app "${state.displayName ?? state.appName}"'`)
  reportGatekeeper(state.copiedApp)
  const app = join(DEST, basename(state.sourceApp))
  console.log(dim('\n  用户手工执行的两条命令（普通终端里跑，输出贴回来即可判定）：'))
  console.log(`    open -n "${app}"`)
  console.log(`    sleep 10; ls -ld "${HOME_TARGET}" "${HOME_TARGET}/dsh-home"; osascript -e 'quit app "${state.displayName ?? state.appName}"'`)
}

async function runLaunchPhase() {
  const app = state.copiedApp
  const exePath = state.exePath
  const appName = state.displayName
  const logPath = join('/tmp', `qa-g3-launch-${process.pid}.log`)
  const startedAt = Date.now()
  let launchPid = null
  let childExited = false
  let method = 'exec'

  console.log(dim(`  · 启动：${exePath}`))
  const fd = openSync(logPath, 'w')
  try {
    const child = spawn(exePath, [], { detached: true, stdio: ['ignore', fd, fd], cwd: '/' })
    child.on('error', () => {})
    // 必须挂 exit 监听：否则子进程退出后变僵尸，pidAlive 一直为真（同步轮询还会堵住 SIGCHLD 回收）。
    child.once('exit', () => { childExited = true })
    child.unref()
    launchPid = child.pid ?? null
  } catch (error) {
    console.log(dim(`  · 直接执行失败：${error.message}；改用 open -n`))
  } finally {
    closeSync(fd)
  }

  // 10 秒窗口：前 4 秒等直接执行；仍无进程则退回 LaunchServices（open -n），继续等到 10 秒。
  let pids = []
  let firstSeenAt = null
  while (Date.now() - startedAt < 10_000) {
    pids = findPids(exePath)
    // 直接 spawn 的子进程若已通过 exit 事件确认退出（僵尸可能仍被 pgrep 列出），不算"出现"。
    if (childExited) pids = pids.filter((pid) => pid !== launchPid)
    if (pids.length > 0) {
      firstSeenAt = Date.now()
      break
    }
    if (method === 'exec' && Date.now() - startedAt > 4_000) {
      method = 'open'
      console.log(dim('  · 直接执行 4 秒未见进程，改用 open -n'))
      run('open', ['-n', '--stdout', logPath, '--stderr', logPath, app], { timeout: 30_000 })
    }
    await sleep(200)
  }

  const elapsed = firstSeenAt === null ? null : ((firstSeenAt - startedAt) / 1000).toFixed(2)
  const logTail = readTail(logPath, 12)
  gate.check('G3-2a 10 秒内进程出现', {
    expected: '启动后 10 秒内 pgrep -f "<app>/Contents/MacOS/<exe>" ≥1 个进程',
    actual: firstSeenAt === null
      ? `10 秒内未出现（方式 ${method}）`
      : `${elapsed}s 出现，pid=${pids.join(',')}（方式 ${method}${launchPid === null ? '' : `，直接执行 pid=${launchPid}`}）`,
    ok: firstSeenAt !== null,
    detail: firstSeenAt === null ? `启动日志尾部：\n${logTail || '(空)'}` : '',
  })

  if (firstSeenAt === null) {
    skipRestOfLaunch('进程没起来，后续检查无对象', logPath)
    reportGatekeeper(app)
    return
  }

  // 起来后 1.5 秒复查：抓"起来了但立刻崩"的假绿。
  await sleep(1500)
  pids = findPids(exePath)
  const alive = pids.length > 0
  gate.check('G3-2b 启动后 1.5 秒仍存活', {
    expected: '进程未在启动阶段崩溃退出',
    actual: alive ? `存活，pid=${pids.join(',')}` : '已退出（启动即崩）',
    ok: alive,
    detail: alive ? '' : `启动日志尾部：\n${logTail || '(空)'}`,
  })
  if (!alive) {
    skipRestOfLaunch('进程启动即崩，后续检查无对象', logPath)
    reportGatekeeper(app)
    return
  }

  const pgid = method === 'exec' && launchPid !== null ? launchPid : psPgid(pids[0])
  gate.record('G3-2d 进程与进程组（记录）', `pid=${pids.join(',')} pgid=${String(pgid ?? '?')}`)

  checkLogs({ logPath, appName, since: startedAt - 2000 })
  await checkHome()
  await checkQuit({ pgid, pids, exePath, appName, launchPid, childExited: () => childExited })
  reportGatekeeper(app)
  console.log(dim(`  · 启动日志：${logPath}（保留，供排查）`))
}

function checkLogs({ logPath, appName, since }) {
  const sources = collectLogs({ logPath, appName, since })
  const text = sources.map((s) => s.text).join('\n')
  const hit = /skipping profile bundle/i.test(text)
  if (sources.length === 0 || text.trim() === '') {
    gate.skip(
      'G3-2c 日志无 "skipping profile bundle"',
      '本次运行没有产生可读日志（app 正常启动不落盘，只在崩溃时写 ~/Library/Logs）',
      '若出现"插件装了但用不了"，用 --dump-config 或崩溃报告里的 hostDiagnostic 复核 skippedBundles',
    )
    return
  }
  gate.check('G3-2c 日志无 "skipping profile bundle"', {
    expected: '日志（app 输出 + ~/Library/Logs/<AppName>）不含该行',
    actual: hit ? '命中 skipping profile bundle（插件层被跳过）' : `未命中（扫描 ${sources.length} 个来源 / ${text.length} 字符）`,
    ok: !hit,
    detail: hit ? text.split('\n').filter((l) => /skipping profile bundle/i.test(l)).slice(0, 5).join('\n') : '',
  })
}

async function checkHome() {
  const target = HOME_TARGET
  let appeared = existsSync(target)
  const waitStart = Date.now()
  while (!appeared && Date.now() - waitStart < 5_000) {
    await sleep(200)
    appeared = existsSync(target)
  }
  gate.check('G3-3a ~/Library/Application Support/Daniel Bot/ 生成', {
    expected: `${target} 存在（app 自己建，不读旧 ~/.dsh）`,
    actual: appeared ? '已生成' : `不存在（等待 5s）`,
    ok: appeared,
    detail: appeared ? '' : 'D-044 核心：能力与数据必须落在 Daniel Bot 自己的 home；不存在说明 installDanielHomes() 没跑或路径变了。',
  })
  if (!appeared) {
    gate.skip('G3-3b 独立 home 权限 0700', 'home 目录不存在，无权限可判', `手工跑后：stat -f '%Sp %N' "${target}"`)
    gate.skip('G3-3c dsh-home / daniel-home 子目录', 'home 目录不存在', `手工跑后：ls -la "${target}"`)
    return
  }
  const mode = statSync(target).mode & 0o777
  gate.check('G3-3b 独立 home 权限 0700', {
    expected: '权限 0700',
    actual: mode.toString(8).padStart(4, '0'),
    ok: mode === 0o700,
    detail: mode === 0o700 ? '' : '其他人可读 ⇒ 数据隔离失效；installDanielHomes() 里应 chmod 0700。',
  })
  const subs = ['dsh-home', 'daniel-home'].map((name) => {
    const path = join(target, name)
    const exists = existsSync(path) && statSync(path).isDirectory()
    return { name, ok: exists, mode: exists ? (statSync(path).mode & 0o777).toString(8).padStart(4, '0') : '-' }
  })
  gate.check('G3-3c dsh-home / daniel-home 子目录存在且 0700', {
    expected: '两个子目录都存在且权限 0700',
    actual: subs.map((s) => `${s.name}=${s.ok ? `存在/${s.mode}` : '缺失'}`).join('；'),
    ok: subs.every((s) => s.ok && s.mode === '0700'),
  })
  const legacy = join(homedir(), 'Library', 'Application Support', 'DeepSeek Harness')
  gate.record('G3-3d 旧 home 状态（记录）', existsSync(legacy) ? '存在（不迁移属预期，D-019）' : '不存在')
}

async function checkQuit({ pgid, pids, exePath, appName, launchPid, childExited }) {
  const quitStart = Date.now()
  let quitMode = String(args.quit)
  if (quitMode === 'osascript') {
    const osa = run('osascript', ['-e', `quit app ${JSON.stringify(appName)}`], { timeout: 20_000 })
    if (!osa.ok) {
      console.log(dim(`  · osascript 退出失败（${`${osa.stderr}`.trim().slice(0, 200)}），回落进程组信号`))
      quitMode = 'group'
    }
  }
  if (quitMode !== 'osascript') killGroup(pgid, pids, 'SIGTERM')

  let result = await waitGone(pgid, pids, exePath, 5_000, launchPid, childExited)
  let escalated = false
  if (!result.gone) {
    escalated = true
    killGroup(pgid, pids, 'SIGKILL')
    result = await waitGone(pgid, pids, exePath, 2_000, launchPid, childExited)
  }
  const seconds = ((Date.now() - quitStart) / 1000).toFixed(2)
  const groupNote = result.group === 'denied'
    ? '（进程组探针回报 EPERM：组内已无成员，按退出处理）'
    : result.group === 'gone' ? '（进程组探针 ESRCH）' : ''
  gate.check('G3-4 5 秒内退出（进程组 ESRCH）', {
    expected: '发退出请求后 ≤5 秒进程组消失（process.kill(-pgid,0) → ESRCH）',
    actual: result.gone
      ? `${seconds}s 内退出（方式 ${quitMode}${escalated ? '，需 SIGKILL 升级' : ''}）${groupNote}`
      : `${seconds}s 后仍存活（pgid=${String(pgid ?? '?')}，pid=${pids.join(',')}，组探针=${result.group}，路径匹配=${result.found}）`,
    ok: result.gone && !escalated,
    detail: result.gone && escalated ? '超过 5 秒才退出：退出流程可能被确认框/后台任务卡住，需人工确认' : '',
  })
}

function skipRestOfLaunch(reason, logFile) {
  gate.skip('G3-2c 日志无 "skipping profile bundle"', reason, `日志：${logFile}`)
  gate.skip('G3-3a ~/Library/Application Support/Daniel Bot/ 生成', reason, `手工跑后：ls -ld "${HOME_TARGET}"`)
  gate.skip('G3-3b 独立 home 权限 0700', reason, `手工跑后：stat -f '%Sp %N' "${HOME_TARGET}"`)
  gate.skip('G3-3c dsh-home / daniel-home 子目录', reason, `手工跑后：ls -la "${HOME_TARGET}"`)
  gate.skip('G3-4 5 秒内退出（进程组 ESRCH）', reason, `手工跑：osascript -e 'quit app "${state.displayName ?? state.appName}"'`)
}

function reportGatekeeper(appPath) {
  if (!existsSync('/usr/sbin/spctl')) {
    gate.skip('G3-5 Gatekeeper 评估（spctl）', '本机没有 /usr/sbin/spctl，无法评估', '在装有 spctl 的 macOS 上重跑；或首次双击观察是否有"无法验证开发者"提示')
    return
  }
  const r = run('/usr/sbin/spctl', ['--assess', '--type', 'execute', '-vv', appPath], { timeout: 120_000 })
  const text = `${r.stdout}${r.stderr}`.trim().split('\n').filter(Boolean)
  gate.record(
    'G3-5 Gatekeeper 评估（记录，不判 FAIL）',
    `spctl 退出码 ${String(r.code)}：${text.at(-1) ?? '(无输出)'}`.slice(0, 300),
    'adhoc 未公证的包被 rejected 属预期（本阶段就是 unsigned 包）；这里只记录首次启动会不会被拦。',
  )
}

// ── 进程工具 ────────────────────────────────────────────────────────────────
function findPids(exePath) {
  const r = run('pgrep', ['-f', escapeRegex(exePath)], { timeout: 15_000 })
  if (!r.ok) return []
  return r.stdout.trim().split('\n').filter(Boolean).map((x) => Number.parseInt(x, 10)).filter(Number.isFinite)
}

function psPgid(pid) {
  const r = run('ps', ['-o', 'pgid=', '-p', String(pid)], { timeout: 15_000 })
  const value = Number.parseInt(r.stdout.trim(), 10)
  return Number.isFinite(value) ? value : null
}

function killGroup(pgid, pids, signal) {
  if (process.env.QA_G3_DEBUG === '1') {
    try { process.kill(-pgid, 0); console.log(`dbg: probe -${pgid} alive`) } catch (e) { console.log(`dbg: probe -${pgid} ${e.code}`) }
    console.log(`dbg pgrep: ${JSON.stringify(findPids(state.exePath))}`)
    console.log(`dbg ps: ${run('ps', ['-o', 'pid,ppid,pgid,sess,stat,command', '-p', String(pids[0])]).stdout.trim()}`)
  }
  const mine = typeof process.getpgrp === 'function' ? process.getpgrp() : null
  if (pgid !== null && pgid > 1 && pgid !== mine) {
    try {
      process.kill(-pgid, signal)
      return
    } catch (error) {
      if (error.code === 'ESRCH') return
      console.log(dim(`  · kill(-${pgid}) 失败：${error.code}；改为逐个杀`))
    }
  }
  for (const pid of pids) {
    try {
      process.kill(pid, signal)
    } catch {
      // 已退出
    }
  }
}

async function waitGone(pgid, pids, exePath, timeoutMs, launchPid = null, childExited = () => false) {
  const deadline = Date.now() + timeoutMs
  let last = { group: 'unknown', pids: pids.length, found: 0 }
  while (Date.now() < deadline) {
    const group = pgid !== null && pgid > 1 ? probeGroup(pgid) : 'gone'
    // 直接 spawn 的那个 pid 以 exit 事件为准：僵尸进程 process.kill(pid,0) 仍返回成功。
    const anyPid = pids.some((pid) => (pid === launchPid ? !childExited() && pidAlive(pid) : pidAlive(pid)))
    const found = findPids(exePath).length
    last = { group, pids: anyPid ? 1 : 0, found }
    // 判"已退出"的三条件：① 原 pid 都不在了；② 路径匹配不到进程；③ 进程组不是明确 alive。
    // ③ 允许 EPERM：macOS 对"已无成员"的组可能返回 EPERM（见 lib/pkg.mjs probeGroup 注释）。
    if (!anyPid && found === 0 && group !== 'alive') return { gone: true, ...last }
    await sleep(200)
  }
  return { gone: false, ...last }
}

function sleep(ms) {
  return new Promise((resolve) => { setTimeout(resolve, ms) })
}

function readTail(path, lines) {
  try {
    return readFileSync(path, 'utf8').trimEnd().split('\n').slice(-lines).join('\n')
  } catch {
    return ''
  }
}

/** 日志来源：本次启动的 stdout/stderr + ~/Library/Logs/<AppName> 下本次运行后写过的文件。 */
function collectLogs({ logPath, appName, since }) {
  const sources = []
  try {
    sources.push({ path: logPath, text: readFileSync(logPath, 'utf8') })
  } catch {
    // 没有该文件就当没有来源
  }
  const dirs = [join(homedir(), 'Library', 'Logs', appName)]
  const execName = state.bundleExec
  if (execName !== undefined && execName !== appName) dirs.push(join(homedir(), 'Library', 'Logs', execName))
  for (const dir of dirs) {
    if (!existsSync(dir)) continue
    let entries = []
    try {
      entries = readdirSync(dir, { withFileTypes: true })
    } catch {
      continue
    }
    for (const entry of entries) {
      if (!entry.isFile()) continue
      const path = join(dir, entry.name)
      try {
        if (statSync(path).mtimeMs < since) continue
        sources.push({ path, text: readFileSync(path, 'utf8') })
      } catch {
        // 读不到的跳过
      }
    }
  }
  return sources
}
