#!/usr/bin/env node
/**
 * G2 · 打包门禁（DMG 产物：体积 / 挂载 / 签名 / 版本 / 结构 / 卸载）
 *
 * 独立运行：
 *   node daniel-bot/app/tests/g2-packaging-gate.mjs
 *   node daniel-bot/app/tests/g2-packaging-gate.mjs --dmg <path.dmg>
 *   node daniel-bot/app/tests/g2-packaging-gate.mjs --legacy      # 验改造前旧包：插件项记 RECORD 不判 FAIL
 *
 * 参数：
 *   --dmg <path>    指定 DMG（文件或目录；目录取其中最新的 .dmg）。缺省自动发现：
 *                   /tmp/dsh-build/dsh-src/apps/desktop/.desktop-build/**\/*.dmg 与 daniel-bot/releases/*.dmg
 *                   里 mtime 最新的那个。
 *   --mount <dir>   挂载点（默认 /tmp/qa-g2-mnt-<pid>，用完即删）
 *   --legacy        改造前产物（无内嵌插件）模式：G2-6 记 RECORD。
 *   --keep          卸载后保留挂载点空目录（默认删除；不影响残留判定）
 *   --help          打印本说明
 *
 * 退出码：0 = 无 FAIL（可含 SKIP；全 SKIP 时结论行为 SKIP）；1 = 存在 FAIL。
 *
 * 关于体积区间 200–400 MB（bytes：200,000,000 – 400,000,000，按 10 进制 MB）：
 *   · 下界 200 MB：改造前 0.2.2-alpha.2 实测 269.7 MB / 257.2 MiB，是本次打底的基线；
 *     内嵌插件（210 文件 ≈ 6 MB）与随包 runtime 只会让它变大。掉到 200 MB 以下说明
 *     资源没打进去（runtime / app.asar 被裁），是要拦的真问题。
 *   · 上界 400 MB：给"内嵌 8 束语料 + CLI + 可能的随包 Python"留 ≥40% 余量，
 *     同时能抓住"把 node_modules / 构建缓存 / 第二份 runtime 打进包"这类事故。
 *   · 两种口径都要求落在区间内（10 进制 MB 与 MiB），避免"按 1000 算过、按 1024 算没过"的扯皮。
 */
import { existsSync, rmSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import process from 'node:process'
import { Gate, dim, parseArgs, readJsonSafe } from './lib/gate.mjs'
import {
  attachDmg, codesignDv, codesignVerify, countFiles, detachDmg, dirSizeKb, humanSize,
  listApps, MB, MIB, mountResidual, readPlist, resolveDmg, sleepSync, versionCandidates,
} from './lib/pkg.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const BUILD_ROOT = '/tmp/dsh-build/dsh-src/apps/desktop/.desktop-build'
const RELEASES = join(HERE, '..', '..', 'releases')

const SIZE_MIN = 200 * MB
const SIZE_MAX = 400 * MB
const SIZE_MIN_MIB = 200 * MIB
const SIZE_MAX_MIB = 400 * MIB

const args = parseArgs(process.argv.slice(2), {
  dmg: '',
  mount: join('/tmp', `qa-g2-mnt-${process.pid}`),
  legacy: false,
  keep: false,
})

if (args.help) {
  console.log(`G2 打包门禁 · 用法

  node daniel-bot/app/tests/g2-packaging-gate.mjs [--dmg <path.dmg>] [--legacy] [--mount <dir>] [--keep]

  --dmg <path>   DMG 文件或目录（目录取其中最新 .dmg）。缺省在下面两处按 mtime 自动发现：
                 ${BUILD_ROOT}
                 ${RELEASES}
  --legacy       改造前产物模式：内嵌插件项（G2-6）只记录不判 FAIL
  --mount <dir>  挂载点，默认 /tmp/qa-g2-mnt-<pid>
  --keep         卸载后保留挂载点空目录
  --help         本说明

检查项：体积 200–400 MB / attach 成功且能列出 .app / adhoc 签名 + 深验退出 0 /
        版本号与文件名一致 / runtime+app.asar 结构 / detach 且无残留挂载。
退出码：0 无 FAIL；1 有 FAIL。`)
  process.exit(0)
}

const gate = new Gate('G2', '打包门禁 · DMG 产物结构与签名')
const MOUNT = String(args.mount)
const LEGACY = Boolean(args.legacy)

const resolved = resolveDmg(args.dmg, [BUILD_ROOT, RELEASES])
const DMG = resolved.path

gate.info(`候选目录：${resolved.searched.join(' , ')}`)
if (resolved.candidates.length > 1) {
  gate.info(`候选 DMG ${resolved.candidates.length} 个（mtime 新→旧）：`)
  for (const c of resolved.candidates.slice(0, 5)) gate.info(`  ${c.path}  ${humanSize(c.size)}  ${c.mtime.toISOString()}`)
}

if (DMG === null) {
  if (args.dmg) {
    // 明确指定了却没找到 ⇒ 是 FAIL（用户以为有包，实际没有）
    gate.check('G2-0 找到待检 DMG', {
      expected: `--dmg 指向的 DMG 存在（当前：${String(args.dmg)}）`,
      actual: '未找到',
      ok: false,
      detail: `候选目录：${resolved.searched.join(' | ')}`,
    })
  } else {
    // 自动发现模式下没包 ⇒ 只是"还没出包"，不能算通过，也不该拉红整个汇总
    gate.skip('G2-0 找到待检 DMG', '候选目录里没有 .dmg（还没出包）', '出包后直接重跑；产物在 /tmp/dsh-build/.../unsigned-artifacts 或 daniel-bot/releases')
    for (const name of [
      'G2-1 DMG 体积在 200–400 MB',
      'G2-2a hdiutil attach（-nobrowse -readonly -mountpoint）',
      'G2-2b 卷内可列出 .app',
      'G2-3a 签名类型 = adhoc',
      'G2-3b codesign --verify --deep --strict',
      'G2-4a CFBundleShortVersionString 与文件名版本一致',
      'G2-5a Contents/Resources/runtime/ 存在',
      'G2-5b runtime/primary-runtime（含 dependencies）',
      'G2-5c runtime/bin/node 存在且可执行',
      'G2-5d Contents/Resources/app.asar 存在且非空壳',
      'G2-6 内嵌插件 Resources/vendor/daniel-dsh-plugin',
      'G2-7a hdiutil detach 退出 0',
      'G2-7b 卸载后无残留挂载点',
    ]) gate.skip(name, '没有可检的 DMG', '出包后重跑：node daniel-bot/app/tests/g2-packaging-gate.mjs --dmg <path>')
  }
  process.exitCode = gate.finish()
  process.exit(process.exitCode)
}

gate.check('G2-0 找到待检 DMG', {
  expected: '文件存在且是普通文件',
  actual: DMG,
  ok: existsSync(DMG) && statSync(DMG).isFile(),
  detail: `mtime ${statSync(DMG).mtime.toISOString()}`,
})
gate.info(`待检 DMG：${DMG}`)

// ── G2-1 体积 ────────────────────────────────────────────────────────────────
{
  const size = statSync(DMG).size
  const inMb = size >= SIZE_MIN && size <= SIZE_MAX
  const inMib = size >= SIZE_MIN_MIB && size <= SIZE_MAX_MIB
  gate.check('G2-1 DMG 体积在 200–400 MB', {
    expected: '200,000,000 ≤ bytes ≤ 400,000,000（200–400 MB），且 200–400 MiB',
    actual: `${size.toLocaleString('en-US')} bytes = ${humanSize(size)}；10 进制 MB 区间内=${inMb}，MiB 区间内=${inMib}`,
    ok: inMb && inMib,
    detail: [
      '区间依据：改造前 0.2.2-alpha.2 实测 269.7 MB / 257.2 MiB 为基线；',
      '下界拦“runtime/app.asar 没打进去”，上界拦“node_modules/构建缓存/重复 runtime 被打进包”。',
    ].join('\n'),
  })
}

// ── G2-2 挂载 + 列出 .app ────────────────────────────────────────────────────
rmSync(MOUNT, { recursive: true, force: true })
const attach = attachDmg(DMG, MOUNT)
let mounted = attach.ok

gate.check('G2-2a hdiutil attach（-nobrowse -readonly -mountpoint）', {
  expected: '退出码 0，只读挂载到指定挂载点',
  actual: `退出码 ${String(attach.code)}；设备 ${attach.devices.map((d) => `${d.device}→${d.name.replace(/\s+/g, ' ')}`).join(', ') || '(无)'}`,
  ok: attach.ok,
  detail: attach.ok ? '' : `${attach.stdout}${attach.stderr}`.trim().slice(-1200),
})

if (!attach.ok) {
  mounted = false
  gate.check('G2-2b 卷内可列出 .app', {
    expected: '挂载成功且卷根有 ≥1 个 .app',
    actual: '未挂载，无法检查',
    ok: false,
    detail: '先修 attach 失败（常见原因：DMG 损坏、同名卷已挂载、磁盘空间不足）。',
  })
} else {
  const apps = listApps(MOUNT)
  gate.check('G2-2b 卷内可列出 .app', {
    expected: '卷根 ≥1 个 *.app 目录',
    actual: `${apps.length} 个：${apps.map((a) => a.name).join(', ') || '(无)'}`,
    ok: apps.length >= 1,
    detail: apps.length > 1 ? '多个 .app：后续检查取第一个；发版包应只有一个' : '',
  })

  const APP = apps[0]?.path ?? null
  if (APP !== null) {
    const plist = readPlist(APP)

    // ── G2-3 签名 ──────────────────────────────────────────────────────────
    const dv = codesignDv(APP)
    gate.check('G2-3a 签名类型 = adhoc', {
      expected: 'codesign -dv --verbose=2 输出 Signature=adhoc',
      actual: `Signature=${String(dv.signature)}；Identifier=${String(dv.identifier)}；Format=${String(dv.format)}`,
      ok: dv.signature === 'adhoc',
      detail: dv.signature === 'adhoc' ? '' : dv.text.split('\n').slice(0, 8).join('\n'),
    })

    const verify = codesignVerify(APP)
    gate.check('G2-3b codesign --verify --deep --strict', {
      expected: '退出码 0（无 resource fork / 未封装资源 / 签名失效）',
      actual: `退出码 ${String(verify.code)}${verify.out === '' ? '，输出为空' : ''}`,
      ok: verify.ok,
      detail: verify.ok ? '' : `${verify.out}\n若报 resource fork / detritus：xattr -cr "<app>" 后重跑（D-042 已知坑）。`,
    })

    // ── G2-4 版本 + bundle id ─────────────────────────────────────────────
    if (plist === null) {
      gate.check('G2-4a CFBundleShortVersionString 与文件名版本一致', {
        expected: 'Contents/Info.plist 可读且版本号与 DMG 文件名一致',
        actual: 'Info.plist 缺失或 plutil 解析失败',
        ok: false,
      })
    } else {
      const plistVersion = String(plist.CFBundleShortVersionString ?? '')
      const nameVersions = versionCandidates(DMG)
      if (nameVersions.length === 0) {
        gate.skip(
          'G2-4a CFBundleShortVersionString 与文件名版本一致',
          `DMG 文件名里找不到版本号（${DMG.split('/').pop()}），无从比对`,
          '打包按 <name>-<version>-<arch>.dmg 命名后可自动比对；当前人工确认 Info.plist 版本',
        )
      } else {
        gate.check('G2-4a CFBundleShortVersionString 与文件名版本一致', {
          expected: `文件名版本 ∈ {${nameVersions.join(', ')}} 且等于 Info.plist 版本`,
          actual: `Info.plist=${plistVersion}；文件名解析出 {${nameVersions.join(', ')}}`,
          ok: nameVersions.includes(plistVersion),
        })
      }
      gate.record(
        'G2-4b CFBundleIdentifier（记录当前值，不判 FAIL）',
        String(plist.CFBundleIdentifier ?? '(空)'),
        '改造后应变为 Daniel 品牌标识；此处只记录，品牌一致性由 G6 品牌门判。改造前基线 = com.deepseek.harness',
      )
      gate.record(
        'G2-4c CFBundleName / CFBundleVersion（记录）',
        `${String(plist.CFBundleName ?? '(空)')} / ${String(plist.CFBundleVersion ?? '(空)')}`,
      )
    }

    // ── G2-5 结构 ──────────────────────────────────────────────────────────
    const RES = join(APP, 'Contents', 'Resources')
    const runtimeDir = join(RES, 'runtime')
    const primaryRuntime = join(runtimeDir, 'primary-runtime')
    const nodeBin = join(runtimeDir, 'bin', 'node')
    const asar = join(RES, 'app.asar')

    gate.check('G2-5a Contents/Resources/runtime/ 存在', {
      expected: 'runtime 是目录',
      actual: existsSync(runtimeDir) ? `${runtimeDir}（${statSync(runtimeDir).isDirectory() ? '目录' : '非目录'}）` : '不存在',
      ok: existsSync(runtimeDir) && statSync(runtimeDir).isDirectory(),
    })

    const deps = join(primaryRuntime, 'dependencies')
    gate.check('G2-5b runtime/primary-runtime（含 dependencies）', {
      expected: 'primary-runtime/ 是目录，且其下 dependencies/ 存在',
      actual: existsSync(primaryRuntime)
        ? `primary-runtime=${statSync(primaryRuntime).isDirectory() ? '目录' : '非目录'}；dependencies=${existsSync(deps) ? (statSync(deps).isDirectory() ? '目录' : '非目录') : '缺失'}`
        : '不存在',
      ok: existsSync(primaryRuntime) && statSync(primaryRuntime).isDirectory()
        && existsSync(deps) && statSync(deps).isDirectory(),
    })

    const nodeStat = existsSync(nodeBin) ? statSync(nodeBin) : null
    const nodeExecutable = nodeStat !== null && (nodeStat.mode & 0o111) !== 0
    gate.check('G2-5c runtime/bin/node 存在且可执行', {
      expected: '文件存在，权限含 x（启动 Host 依赖它）',
      actual: nodeStat === null
        ? '不存在'
        : `存在，${(nodeStat.mode & 0o777).toString(8).padStart(4, '0')}，${nodeStat.size} B，可执行=${nodeExecutable}`,
      ok: nodeStat !== null && nodeStat.isFile() && nodeExecutable,
    })

    const asarStat = existsSync(asar) ? statSync(asar) : null
    gate.check('G2-5d Contents/Resources/app.asar 存在且非空壳', {
      expected: '文件存在且 > 1 MB（空 asar 说明应用代码没打进去）',
      actual: asarStat === null ? '不存在' : humanSize(asarStat.size),
      ok: asarStat !== null && asarStat.isFile() && asarStat.size > MB,
    })

    // ── G2-6 内嵌插件（改造后判据；旧包用 --legacy 记 RECORD）──────────────
    // 这里只判"存在 + 名字 + 文件数"；版本与 root hash 由 upgrade-plugin.mjs --verify 补齐
    // （specs/UPGRADE-PLUGIN.md §8 ④：只判存在性会放过"旧版本没换"这类事故）。
    const vendorPlugin = join(RES, 'vendor', 'daniel-dsh-plugin')
    const pluginPkg = readJsonSafe(join(vendorPlugin, 'package.json'))
    const pluginFiles = existsSync(vendorPlugin) ? countFiles(vendorPlugin) : 0
    const pluginOk = pluginPkg !== null && pluginPkg.name === 'daniel-dsh-plugin' && pluginFiles >= 100
    if (LEGACY) {
      gate.record(
        'G2-6 内嵌插件 Resources/vendor/daniel-dsh-plugin（--legacy：只记录）',
        existsSync(vendorPlugin) ? `${String(pluginPkg?.version ?? '?')} / ${pluginFiles} 文件` : '不存在（改造前预期）',
        '旧包没有内嵌插件属预期；改造后这条必须 PASS（D-044：能力随包，不让用户装插件）。',
      )
    } else {
      gate.check('G2-6 内嵌插件 Resources/vendor/daniel-dsh-plugin', {
        expected: 'asar 外真目录，package.json.name=daniel-dsh-plugin，文件数 ≥100',
        actual: existsSync(vendorPlugin)
          ? `name=${String(pluginPkg?.name ?? '(解析失败)')}，version=${String(pluginPkg?.version ?? '?')}，${pluginFiles} 文件`
          : '目录不存在',
        ok: pluginOk,
        detail: pluginOk ? '' : '改造后缺这个目录 ⇒ Daniel 能力没随包（用户会看到“没有 Daniel 的 DSH”）。',
      })
    }

    const appKb = dirSizeKb(APP)
    gate.record('G2-6b .app 体积（记录）', appKb === null ? '(du 失败)' : humanSize(appKb * 1024))
    gate.record('G2-6c .app 名称（记录，G6 品牌门用）', APP.split('/').pop())
  }
}

// ── G2-7 卸载 + 残留 ────────────────────────────────────────────────────────
if (!mounted) {
  gate.skip('G2-7a hdiutil detach 退出 0', 'attach 未成功，没有可卸载的卷', '修好 attach 后重跑，本项自动执行')
  gate.skip('G2-7b 卸载后无残留挂载点', 'attach 未成功，没有可卸载的卷', '同上')
} else {
  const detach = detachDmg(MOUNT)
  gate.check('G2-7a hdiutil detach 退出 0', {
    expected: '退出码 0（必要时 -force 重试）',
    actual: `退出码 ${String(detach.attempts.at(-1)?.code)}；尝试 ${detach.attempts.length} 次`,
    ok: detach.ok,
    detail: detach.ok ? '' : detach.attempts.map((a) => `${a.args.join(' ')} → ${a.code} ${a.out}`.trim()).join('\n'),
  })
  sleepSync(500)
  const residual = mountResidual(MOUNT)
  gate.check('G2-7b 卸载后无残留挂载点', {
    expected: 'hdiutil info 不含该挂载点，且挂载点目录为空/已删',
    actual: `hdiutil info 命中=${residual.inInfo}；挂载点内条目=${residual.entries.length}`,
    ok: !residual.residual,
    detail: residual.residual ? `残留条目：${residual.entries.slice(0, 8).join(', ')}` : '',
  })
  if (detach.ok && !Boolean(args.keep)) rmSync(MOUNT, { recursive: true, force: true })
}

gate.info(dim(`临时挂载点：${MOUNT}（${Boolean(args.keep) ? '已保留' : '已清理'}）`))
process.exitCode = gate.finish()
