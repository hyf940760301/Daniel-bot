'use strict'
/**
 * 会话文件（S2 §4.2）。
 *
 * 落点：$DANIEL_HOME/session/session.json，内容 {"cookie": "app_session_id=<JWT>", "ts": <epoch>}
 * 权限：文件 0600、目录 0700（CLI 自己也要求 600）。
 * 原子写：tmp + rename，绝不先截断。
 */

const fs = require('node:fs')
const path = require('node:path')

function readSession(file) {
  try {
    const raw = fs.readFileSync(file, 'utf8')
    const data = JSON.parse(raw)
    const cookie = typeof data?.cookie === 'string' ? data.cookie : ''
    if (!cookie.startsWith('app_session_id=')) return null
    const ts = Number(data?.ts) || 0
    return { cookie, ts }
  } catch {
    return null
  }
}

function writeSession(file, { cookie, ts = Date.now() / 1000 }) {
  const dir = path.dirname(file)
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 })
  try { fs.chmodSync(dir, 0o700) } catch { /* ignore */ }

  const tmp = `${file}.tmp-${process.pid}`
  fs.writeFileSync(tmp, JSON.stringify({ cookie, ts }, null, 1) + '\n', { mode: 0o600 })
  try { fs.chmodSync(tmp, 0o600) } catch { /* ignore */ }
  fs.renameSync(tmp, file)
  try { fs.chmodSync(file, 0o600) } catch { /* ignore */ }

  // 回读校验：权限与内容都当面确认，别「以为写成功了」
  const mode = fs.statSync(file).mode & 0o777
  if (mode !== 0o600) throw new Error(`会话文件权限异常：${mode.toString(8)}（期望 600）`)
  const got = readSession(file)
  if (!got || got.cookie !== cookie) throw new Error('会话文件回读不一致')
  return got
}

function deleteSession(file) {
  try { fs.unlinkSync(file) } catch (e) { if (e.code !== 'ENOENT') throw e }
}

module.exports = { readSession, writeSession, deleteSession }
