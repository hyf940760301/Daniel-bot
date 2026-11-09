/**
 * `daniel_login` 自检（不需要 DSH 宿主）：用最小 mock ctx 注册工具，逐个跑用例并打印结果。
 *
 * 用法：node scripts/test-login.mjs
 *
 * 🔴 纪律（硬约束，写进代码里）：
 *   ① **只喂伪造的会话值**（`aaa.bbb.ccc` 之类），本脚本没有任何读取真实会话的路径；
 *   ② 数据落点**强制**指到工作区临时目录（`tmp/login-test-home`），跑之前断言它确实在工作区内、
 *      且不等于用户真实落点 —— 保证 CLI 的会话文件／审计只会写进临时目录；
 *   ③ 成功路径用 `entry` 指向**假 CLI 桩**（不联网、不落真会话），只为验插件这一侧的
 *      「值走 stdin／不进 argv／不回显／不删用户文件／回读后给什么」；
 *   ④ 跑完 `rm -rf` 临时落点（异常也清）。
 */
import { apply } from '../lib/index.js'
import { existsSync, mkdirSync, rmSync, writeFileSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const WORKSPACE = resolve(join(HERE, '..', '..'))

const TMP_HOME = join(WORKSPACE, 'tmp', 'login-test-home')    // CLI 的数据落点（会话／审计都在这）
const TMP_FILES = join(WORKSPACE, 'tmp', 'login-test-files')  // 用例用的「会话值文件」与假 CLI 桩
const REAL_HOME = join(process.env.HOME || '', 'Library', 'Application Support', 'DanielCopilot')

/** 保险丝：临时落点必须在工作区内，且绝不能是用户真实落点 */
if (!TMP_HOME.startsWith(WORKSPACE + '/')) throw new Error('临时落点不在工作区内，拒绝运行：' + TMP_HOME)
if (resolve(TMP_HOME) === resolve(REAL_HOME)) throw new Error('临时落点与用户真实落点重合，拒绝运行')

// 双保险：config.danielHome 已经钉住落点，环境变量再钉一次（CLI 子进程会继承）
process.env.DANIEL_HOME = TMP_HOME
process.env.DANIEL_NO_OPEN = '1'

rmSync(TMP_HOME, { recursive: true, force: true })
rmSync(TMP_FILES, { recursive: true, force: true })
mkdirSync(TMP_HOME, { recursive: true })
mkdirSync(TMP_FILES, { recursive: true })

// ── 用例文件（内容全部是伪造的）────────────────────────────────
const MISSING_FILE = join(TMP_FILES, 'not-exist.txt')
const BAD_FILE = join(TMP_FILES, 'wrong-format.txt')
const EMPTY_FILE = join(TMP_FILES, 'empty.txt')
const GOOD_FILE = join(TMP_FILES, 'fake-session.txt')
const FAKE_ENTRY = join(TMP_FILES, 'fake-daniel.py')
const FAKE_LOG = join(TMP_FILES, 'fake-daniel-log.json')

writeFileSync(BAD_FILE, '这不是会话值 just some text\n')
writeFileSync(EMPTY_FILE, '   \n\n')

// 伪造值：① 三段点分但头段不是 JWS 头（CLI 的形态校验会挡）② 结构像真 JWS 头（会走到服务端）
const FAKE_PLAIN = 'aaa.bbb.ccc'
const FAKE_JWS = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ZmFrZS1wYXlsb2Fk.ZmFrZS1zaWc'
writeFileSync(GOOD_FILE, '  "' + FAKE_JWS + '"\n')   // 故意带引号与换行，验证清洗

// 假 CLI 桩：把收到的 stdin／argv 记下来，再按真 CLI 的 JSON 信封回话（不联网、不落任何真会话）
writeFileSync(FAKE_ENTRY, `# -*- coding: utf-8 -*-
import json, sys
log = ${JSON.stringify(FAKE_LOG)}
mode = "login" if "login" in sys.argv else "status"
stdin_data = sys.stdin.read() if mode == "login" else ""
with open(log, "a", encoding="utf-8") as f:
    f.write(json.dumps({"mode": mode, "argv": sys.argv[1:], "stdin": stdin_data.strip()}, ensure_ascii=False) + "\\n")
if mode == "status":
    print(json.dumps({"ok": True, "data": {
        "authenticated": True, "reason": "通过",
        "server": {"账号(掩码)": "f***@***.com"},
        "local": {"本机会话文件": "/tmp/fake-home/session/session.json"},
        "next": "可以正常调用业务模块。"}}, ensure_ascii=False))
else:
    print(json.dumps({"ok": True, "data": {"readback": {"detail": {
        "会话文件": {"路径": "/tmp/fake-home/session/session.json"}}}}}, ensure_ascii=False))
`)

// ── 注册（同一份 apply，两种配置）──────────────────────────────
function registerTool(config) {
  const got = []
  const ctx = {
    tools: { register: (t) => got.push(t) },
    logger: { info() {}, warn() {}, debug() {} },
    effect() {},
    inject: ['tools'],
  }
  apply(ctx, config)
  return { tools: got, login: got.find((t) => t.name === 'daniel_login') }
}

const real = registerTool({ python: 'python3', timeoutMs: 60000, danielHome: TMP_HOME })
const stub = registerTool({ python: 'python3', timeoutMs: 30000, danielHome: TMP_HOME, entry: FAKE_ENTRY })
if (!real.login || !stub.login) {
  console.error('未注册 daniel_login；已注册：' + real.tools.map((t) => t.name).join(','))
  process.exit(1)
}

// ── 用例 ──────────────────────────────────────────────────────
const CASES = [
  { id: '①无参数', tool: real.login, args: {}, expect: { exitCode: 2, kind: 'usage' } },
  {
    id: '②文件不存在', tool: real.login, args: { session_file: MISSING_FILE },
    expect: { exitCode: 2, kind: 'session_file_not_found' },
  },
  {
    id: '③文件内容格式错误', tool: real.login, args: { session_file: BAD_FILE },
    expect: { exitCode: 2, kind: 'invalid_session_format' },
  },
  {
    id: '④文件为空', tool: real.login, args: { session_file: EMPTY_FILE },
    expect: { exitCode: 2, kind: 'session_file_empty' },
  },
  {
    id: '⑤两个参数同时给', tool: real.login, args: { session_file: BAD_FILE, session_value: FAKE_PLAIN },
    expect: { exitCode: 2, kind: 'usage' },
  },
  {
    id: '⑥伪造值·三段点分但非 JWS（真实调用）', tool: real.login, args: { session_value: FAKE_PLAIN }, real: true,
    expectAny: [{ exitCode: 2, kind: 'invalid_session_format' }],
    secrets: [FAKE_PLAIN],
  },
  {
    id: '⑦伪造值·JWS 形态（真实调用，期望服务端不认）', tool: real.login, args: { session_value: FAKE_JWS }, real: true,
    expectAny: [
      { exitCode: 1, kind: 'session_rejected' },
      { exitCode: 1, kind: 'login_timeout' },
      { exitCode: 2, kind: 'server_unreachable' },
    ],
    secrets: [FAKE_JWS],
  },
  {
    id: '⑧成功路径（假 CLI 桩，不联网）：文件方式 → 值只走 stdin', tool: stub.login,
    args: { session_file: GOOD_FILE }, stub: true,
    expect: { exitCode: 0, ok: true },
    secrets: [FAKE_JWS],
  },
]

let pass = 0
let fail = 0
const lines = []

for (const c of CASES) {
  const out = await c.tool.execute(c.args, {})
  const json = JSON.stringify(out)
  const kind = (out.error && out.error.kind) || ''
  const targets = c.expectAny || [c.expect]
  const okCase = targets.some((t) => t.exitCode === out.exitCode
    && (t.kind === undefined || t.kind === kind)
    && (t.ok === undefined || t.ok === out.ok))
  const leaked = (c.secrets || []).some((s) => s && json.includes(s))
  let extraOk = true
  const extraLines = []
  if (c.stub) {
    // 假 CLI 桩的账：值必须走 stdin、绝不在 argv 里；用户文件不删；回读结果照实给
    const records = readFileSync(FAKE_LOG, 'utf8').trim().split('\n').filter(Boolean).map((l) => JSON.parse(l))
    const loginRec = records.filter((r) => r.mode === 'login').pop() || { argv: [], stdin: '' }
    const argvHasSecret = loginRec.argv.some((x) => String(x).includes(FAKE_JWS))
    const stdinOk = loginRec.stdin === FAKE_JWS
    const fileKept = existsSync(GOOD_FILE)
    const maskOk = Boolean(out.data) && out.data['账号'] === 'f***@***.com' && out.data['已登录'] === true
    extraOk = stdinOk && !argvHasSecret && fileKept && maskOk
    extraLines.push(`   假 CLI 被调用次数： ${records.length}（登录 1 次 ＋ 回读 ${records.length - 1} 次）`)
    extraLines.push(`   值走 stdin： ${stdinOk ? '是' : '否（不合格！）'}；argv 里带值： ${argvHasSecret ? '是（不合格！）' : '否'}`)
    extraLines.push(`   用户文件仍在： ${fileKept ? '是（插件不删用户文件）' : '否（不合格！）'}；回读掩码账号： ${maskOk ? 'f***@***.com' : '缺（不合格！）'}`)
    extraLines.push(`   返回 note： ${String(out.note || '').slice(0, 130)}`)
  }
  const ok = okCase && !leaked && extraOk
  if (ok) pass += 1; else fail += 1

  lines.push(`\n── ${c.id}${c.real ? '［真实调用］' : ''}${c.stub ? '［假 CLI 桩］' : ''}`)
  lines.push(`   入参： ${JSON.stringify(c.args)}`)
  lines.push(`   期望： ${targets.map((t) => `exitCode=${t.exitCode}${t.ok === true ? ' ok=true' : ''}${t.kind ? ' / ' + t.kind : ''}`).join(' 或 ')}`)
  lines.push(`   实际： exitCode=${out.exitCode} ok=${out.ok} ${kind ? '/ ' + kind : ''} → ${ok ? 'PASS' : 'FAIL'}`)
  lines.push(`   回显会话值： ${leaked ? '是（不合格！）' : '否'}`)
  if (extraLines.length) lines.push(...extraLines)
  lines.push(`   输出： ${json.length > 700 ? json.slice(0, 700) + '…' : json}`)
}

console.log(`注册工具（${real.tools.length}）: ${real.tools.map((t) => t.name).join(', ')}`)
console.log(`数据落点（临时）: ${TMP_HOME}｜临时文件: ${TMP_FILES}`)
console.log(lines.join('\n'))
console.log(`\n合计：PASS ${pass} / FAIL ${fail}`)

// ── 清理：临时落点一律删掉（里面是本轮跑出来的会话/审计）──────────
rmSync(TMP_HOME, { recursive: true, force: true })
rmSync(TMP_FILES, { recursive: true, force: true })
console.log(`已清理：${TMP_HOME} 存在=${existsSync(TMP_HOME)}；${TMP_FILES} 存在=${existsSync(TMP_FILES)}`)
process.exit(fail === 0 ? 0 : 1)
