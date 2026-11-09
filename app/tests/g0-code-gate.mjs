#!/usr/bin/env node
/**
 * G0 · 代码门禁（补丁可复现 / 类型检查 / 官方测试 / 补丁与工作区一致）
 *
 * 独立运行：
 *   node daniel-bot/app/tests/g0-code-gate.mjs
 *   node daniel-bot/app/tests/g0-code-gate.mjs --src /tmp/dsh-build/dsh-src --patch /path/to.patch
 *
 * 退出码：0 = 全部 PASS（可含 SKIP）；1 = 存在 FAIL。
 *
 * 四条判据（每条都要求真实输出，不接受"通过"两字）：
 *   G0-1 补丁可复现：HEAD 干净树上 `git apply --check` 通过，且真应用后 13 个文件与工作区逐字节相同。
 *        —— 只跑 --check 会假绿：patch 能应用不等于能把工作区还原成同一棵树。
 *   G0-2 类型检查：`pnpm -C apps/desktop run build`（tsc -b + tsdown）退出 0，且产物真的被重写。
 *   G0-3 官方测试：project-manager / profile 相关 11 个 spec 全绿，打印真实通过数。
 *        —— 注意：`pnpm -C apps/desktop test` 在该仓库**不存在**（apps/desktop 无 test 脚本），
 *           本门禁改用仓库根 node_modules/.bin/vitest 直接跑同一批 spec。
 *   G0-4 补丁与工作区一致：`git diff HEAD` 与补丁文件 sha256 相同、13 个 diff 头。
 */
import { existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import process from 'node:process'
import { Gate, dim, parseArgs, run, sha256File } from './lib/gate.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const APP = join(HERE, '..')
const DEFAULTS = {
  src: '/tmp/dsh-build/dsh-src',
  patch: join(APP, 'desktop-patches', 'WIP-embed-and-isolate.patch'),
  toolchain: join(APP, '..', 'build', 'toolchain', 'node24', 'bin'),
}
const args = parseArgs(process.argv.slice(2), DEFAULTS)
const SRC = String(args.src)
const PATCH = resolve(String(args.patch))
const TOOLCHAIN = String(args.toolchain)
const WORK = join('/tmp', `qa-g0-${String(process.pid)}`)
const gate = new Gate('G0', '代码门禁')

/** Run a command with the pinned Node 24 toolchain ahead of PATH. */
function withToolchain(command, argv, options = {}) {
  const path = `${TOOLCHAIN}:${process.env.PATH ?? ''}`
  return run(command, argv, { ...options, env: { PATH: path } })
}

function lastLines(text, count = 8) {
  const lines = String(text).trimEnd().split('\n')
  return lines.slice(-count).join('\n')
}

if (!existsSync(join(SRC, '.git'))) {
  gate.check('前置：构建工作区是 git 仓库', { expected: `${SRC}/.git 存在`, actual: '不存在', ok: false, detail: '用 --src 指定源码树' })
  gate.finish()
}

rmSync(WORK, { recursive: true, force: true })
mkdirSync(WORK, { recursive: true })
gate.info(`源码树：${SRC}`)
gate.info(`补丁：${PATCH}`)
gate.info(`临时目录：${WORK}`)

// ── G0-1 补丁可复现 ────────────────────────────────────────────────────────────
{
  const head = run('git', ['-C', SRC, 'rev-parse', '--short=8', 'HEAD'])
  const tarPath = join(WORK, 'head.tar')
  const tree = join(WORK, 'tree')
  mkdirSync(tree, { recursive: true })

  const archive = run('git', ['-C', SRC, 'archive', '--format=tar', `-o${tarPath}`, 'HEAD'])
  const unpack = archive.ok ? run('tar', ['-xf', tarPath, '-C', tree]) : { ok: false, stderr: '' }
  const cleanOfPlugin = !existsSync(join(tree, 'apps', 'desktop', 'src', 'daniel-plugin.ts'))
  gate.check('G0-1a 干净树取自 HEAD（不含补丁新增文件）', {
    expected: `HEAD=${head.stdout.trim()} 解包成功且无 daniel-plugin.ts`,
    actual: `archive=${String(archive.code)} tar=${String(unpack.code)} 无 daniel-plugin.ts=${String(cleanOfPlugin)}`,
    ok: archive.ok && unpack.ok && cleanOfPlugin,
    detail: archive.stderr || unpack.stderr,
  })

  const check = run('git', ['apply', '--check', PATCH], { cwd: tree })
  gate.check('G0-1b 干净副本上 git apply --check', {
    expected: '退出码 0，无 fuzz/reject',
    actual: `退出码 ${String(check.code)}${check.stderr.trim() === '' ? '，stderr 空' : `，stderr: ${check.stderr.trim()}`}`,
    ok: check.ok,
    detail: check.stderr,
  })

  const apply = run('git', ['apply', PATCH], { cwd: tree })
  const rejectFiles = run('find', [tree, '-name', '*.rej', '-o', '-name', '*.orig']).stdout.trim()
  gate.check('G0-1c 真应用补丁（非 --check）', {
    expected: '退出码 0，无 .rej/.orig 残留',
    actual: `退出码 ${String(apply.code)}，残留=${rejectFiles === '' ? '无' : rejectFiles}`,
    ok: apply.ok && rejectFiles === '',
    detail: apply.stderr,
  })

  // 与工作区逐字节比对：证明补丁 = 工作区的全部改动，而不是"能打上"。
  const changed = run('git', ['-C', SRC, 'diff', 'HEAD', '--name-only']).stdout.trim().split('\n').filter(Boolean)
  const mismatches = []
  for (const file of changed) {
    const applied = join(tree, file)
    const live = join(SRC, file)
    // 补丁里的删除项：工作区没有该文件时，应用后也必须没有。
    if (!existsSync(live)) {
      if (existsSync(applied)) mismatches.push(`${file}（应删除但仍存在）`)
      continue
    }
    if (!existsSync(applied)) { mismatches.push(`${file}（应用后缺失）`); continue }
    const left = sha256File(applied)
    const right = sha256File(live)
    if (left !== right) mismatches.push(`${file}（${left.slice(0, 12)} ≠ ${right.slice(0, 12)}）`)
  }
  const patchFiles = (readFileSync(PATCH, 'utf8').match(/^diff --git /gm) ?? []).length
  gate.check('G0-1d 应用结果与工作区文件逐字节一致', {
    expected: `${String(patchFiles)} 个文件 sha256 全等，0 失配`,
    actual: `${String(changed.length)} 个文件，失配 ${String(mismatches.length)}${mismatches.length === 0 ? '' : `：${mismatches.slice(0, 3).join('；')}`}`,
    ok: changed.length === patchFiles && mismatches.length === 0,
    detail: mismatches.join('\n'),
  })
}

// ── G0-2 类型检查 ──────────────────────────────────────────────────────────────
{
  const mainPath = join(SRC, 'apps', 'desktop', 'lib', 'main.js')
  const before = existsSync(mainPath) ? statSync(mainPath).mtimeMs : 0
  const startedAt = Date.now()
  const build = withToolchain('pnpm', ['-C', 'apps/desktop', 'run', 'build'], { cwd: SRC, timeout: 900_000 })
  const after = existsSync(mainPath) ? statSync(mainPath).mtimeMs : 0
  const tsErrors = (build.stdout + build.stderr).match(/error TS\d+/g) ?? []
  const fresh = after > before || after >= startedAt - 2_000
  gate.check('G0-2 tsc + bundle 构建', {
    expected: '退出码 0，无 error TS，lib/main.js 本次重写',
    actual: `退出码 ${String(build.code)}，error TS ${String(tsErrors.length)} 处，mtime ${before === after ? '未变' : '已更新'}`,
    ok: build.ok && tsErrors.length === 0 && after > 0 && fresh,
    detail: lastLines(build.stdout + build.stderr, 10),
  })
}

// ── G0-2b host 聚合检查（打包时才会跑，tsc -b 覆盖不到）─────────────────────────
{
  // 清掉增量信息，避免缓存掩盖「未使用变量」这类错误（打包前就是这样漏掉的）。
  for (const info of ['tsconfig.host.tsbuildinfo', join('apps', 'desktop', 'tsconfig.host.tsbuildinfo')]) {
    rmSync(join(SRC, info), { force: true })
  }
  const host = run(join(SRC, 'node_modules', '.bin', 'tsc'), ['-p', 'tsconfig.host.json'], {
    cwd: join(SRC, 'apps', 'desktop'),
    timeout: 600_000,
    env: {
      ...process.env,
      PATH: `${TOOLCHAIN}:${process.env.PATH ?? ''}`,
      NODE_OPTIONS: '--max-old-space-size=8192',
    },
  })
  const errs = (host.stdout + host.stderr).match(/error TS\d+/g) ?? []
  gate.check('G0-2b host 聚合类型检查（tsc -p tsconfig.host.json）', {
    expected: '退出码 0，无 error TS（打包 run-gates 会用同一命令）',
    actual: `退出码 ${String(host.code)}，error TS ${String(errs.length)} 处`,
    ok: host.code === 0 && errs.length === 0,
    detail: lastLines(host.stdout + host.stderr, 12),
  })
}

// ── G0-2c client 工程编译（dev/打包会跑，desktop bundle 覆盖不到）───────────────
{
  const client = run(join(SRC, 'node_modules', '.bin', 'tsc'), ['-b', '--force', 'tsconfig.client.json'], {
    cwd: SRC,
    timeout: 900_000,
    env: { ...process.env, PATH: `${TOOLCHAIN}:${process.env.PATH ?? ''}` },
  })
  const errs = (client.stdout + client.stderr).match(/error TS\d+/g) ?? []
  gate.check('G0-2c client 工程编译（tsc -b --force，避免增量缓存掩盖未使用变量）', {
    expected: '退出码 0，无 error TS（dev 与打包 run-gates 会用同一命令）',
    actual: `退出码 ${String(client.code)}，error TS ${String(errs.length)} 处`,
    ok: client.code === 0 && errs.length === 0,
    detail: lastLines(client.stdout + client.stderr, 12),
  })
}

// ── G0-3 官方测试（project-manager / profile）──────────────────────────────────
{
  const specs = [
    'apps/desktop/tests/project-manager.spec.ts',
    'apps/desktop/tests/profile-mcp.spec.ts',
    'apps/desktop/tests/development-project.spec.ts',
    'apps/desktop/tests/daniel-plugin.spec.ts',
    'packages/boot/app-boot/tests/profile.spec.ts',
    'packages/boot/app-boot/tests/profile-sanitize.spec.ts',
    'packages/boot/app-boot/tests/profile-plugins.spec.ts',
    'packages/boot/app-boot/tests/profile-compatibility.spec.ts',
    'packages/boot/app-boot/tests/profile-resolution.spec.ts',
    'packages/boot/app-boot/tests/profile-resolution-service.spec.ts',
    'packages/boot/app-boot/tests/profile-resolution-worker-bootstrap.spec.ts',
  ].filter(file => existsSync(join(SRC, file)))

  const vitest = join(SRC, 'node_modules', '.bin', 'vitest')
  gate.check('G0-3a 测试运行器存在', {
    expected: `${vitest} 可执行；11 个 spec 都在`,
    actual: `vitest=${existsSync(vitest) ? '有' : '无'}，spec ${String(specs.length)}/11`,
    ok: existsSync(vitest) && specs.length === 11,
  })

  const result = withToolchain(vitest, ['run', ...specs], { cwd: SRC, timeout: 900_000 })
  const output = result.stdout + result.stderr
  const filesPassed = Number(/Test Files\s+(\d+) passed/.exec(output)?.[1] ?? 0)
  const testsPassed = Number(/Tests\s+(\d+) passed/.exec(output)?.[1] ?? 0)
  const testsFailed = Number(/Tests[^\n]*?(\d+) failed/.exec(output)?.[1] ?? 0)
  const totalFailedMatch = /Test Files\s+(\d+) failed/.exec(output)
  const projectManager = /project-manager\.spec\.ts \((\d+) tests?(?: \| (\d+) skipped)?\)/.exec(output)
  const danielSpec = /daniel-plugin\.spec\.ts \((\d+) tests?\)/.exec(output)
  const pmTests = Number(projectManager?.[1] ?? 0)
  const pmSkipped = Number(projectManager?.[2] ?? 0)
  const pmPassed = pmTests - pmSkipped

  gate.check('G0-3b 官方测试全绿（11 个 spec）', {
    expected: '退出码 0，Test Files 11 passed，0 failed',
    actual: `退出码 ${String(result.code)}，Test Files ${String(filesPassed)} passed${totalFailedMatch ? ` / ${String(totalFailedMatch[1])} failed` : ''}，Tests ${String(testsPassed)} passed${testsFailed > 0 ? ` / ${String(testsFailed)} failed` : ''}`,
    ok: result.ok && filesPassed === 11 && !totalFailedMatch && testsPassed >= 300,
    detail: lastLines(output, 12),
  })

  gate.check('G0-3c project-manager 用例数（贴真实数量）', {
    expected: 'project-manager.spec.ts ≥ 35 passed（1 skipped 允许）',
    actual: `project-manager.spec.ts ${String(pmTests)} tests，其中 skipped ${String(pmSkipped)} ⇒ passed ${String(pmPassed)}`,
    ok: pmTests > 0 && pmPassed >= 35 && pmSkipped <= 1,
  })

  gate.check('G0-3d 补丁新增的 daniel-plugin 用例被执行', {
    expected: 'daniel-plugin.spec.ts (5 tests)',
    actual: danielSpec === null ? '输出里没有该文件（未被 vitest 收集）' : `${danielSpec[0]}`,
    ok: Number(danielSpec?.[1] ?? 0) === 5,
  })
}

// ── G0-4 补丁与工作区一致 ──────────────────────────────────────────────────────
{
  const diffPath = join(WORK, 'worktree.diff')
  const diff = run('git', ['-C', SRC, 'diff', 'HEAD', '--binary'])
  writeFileSync(diffPath, diff.stdout)
  const patchSha = sha256File(PATCH)
  const diffSha = sha256File(diffPath)
  const patchBytes = statSync(PATCH).size
  const diffBytes = statSync(diffPath).size
  const patchHeads = (readFileSync(PATCH, 'utf8').match(/^diff --git /gm) ?? []).length
  const diffHeads = (diff.stdout.match(/^diff --git /gm) ?? []).length

  gate.check('G0-4 补丁文件 == 工作区 git diff HEAD（逐字节）', {
    expected: `sha256 相同、patch 与 diff 的 diff --git 数量相同、字节数相同`,
    actual: `patch ${patchSha.slice(0, 16)}… ${String(patchBytes)}B，diff ${diffSha.slice(0, 16)}… ${String(diffBytes)}B；diff --git ${String(patchHeads)} vs ${String(diffHeads)}`,
    ok: diff.ok && patchSha === diffSha && diffHeads === patchHeads,
    detail: diff.stderr,
  })
}

// 保留现场（便于 FAIL 复现）；打印路径但不阻塞。
gate.info(`临时树保留在 ${dim(WORK)}（可删除）`)
const code = gate.finish()
if (code === 0) rmSync(WORK, { recursive: true, force: true })
process.exitCode = code
