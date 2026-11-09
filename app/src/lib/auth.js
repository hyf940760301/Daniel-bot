'use strict'
/**
 * 登录：壳主进程直连 Daniel 的 tRPC（S2 §4.1 / D-033）。
 *
 *   POST /api/trpc/auth.login   body {"json":{"email","password"}}
 *   GET  /api/trpc/auth.me      {"json":null}，回读邮箱
 *
 * 🔴 服务端在**密码错时返回 HTTP 500**（不是 401），错误原因在响应体
 *    `{"error":{"json":{"message":"Invalid email or password",…}}}` —— 必须解析 body，
 *    只看状态码会把「密码错」报成「服务端故障」。
 *
 * 密码只在本模块的调用栈里存活到请求结束；不写日志、不写文件、不进子进程。
 */

const { net } = require('electron')

const BASE = (process.env.DANIEL_BASE_URL || 'https://daniel-agent.com').replace(/\/+$/, '')

class AuthError extends Error {
  constructor(message, { kind = 'credential', status = 0, serverMessage = '' } = {}) {
    super(message)
    this.name = 'AuthError'
    this.kind = kind            // credential | account | network | server | mismatch
    this.status = status
    this.serverMessage = serverMessage
  }
}

function request({ method = 'GET', url, headers = {}, body = '', timeoutMs = 30000 }) {
  return new Promise((resolve, reject) => {
    let settled = false
    const finish = (fn, value) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      fn(value)
    }
    const timer = setTimeout(() => {
      try { req.abort() } catch { /* ignore */ }
      const err = new Error('请求超时')
      err.code = 'ETIMEDOUT'
      finish(reject, err)
    }, timeoutMs)

    let req
    try {
      req = net.request({ method, url, redirect: 'manual' })
    } catch (e) {
      finish(reject, e)
      return
    }
    for (const [k, v] of Object.entries(headers)) {
      try { req.setHeader(k, v) } catch { /* 个别头 Electron 不允许改，忽略 */ }
    }
    req.on('response', (res) => {
      const chunks = []
      res.on('data', (c) => chunks.push(Buffer.from(c)))
      res.on('error', (e) => finish(reject, e))
      res.on('end', () => finish(resolve, {
        status: res.statusCode,
        headers: res.headers || {},
        body: Buffer.concat(chunks).toString('utf8'),
      }))
    })
    req.on('error', (e) => finish(reject, e))
    if (body) req.write(body)
    req.end()
  })
}

/** set-cookie 可能是数组，也可能是被折成一条的字符串 */
function setCookies(headers) {
  const raw = headers['set-cookie']
  if (!raw) return []
  return Array.isArray(raw) ? raw : [String(raw)]
}

function pickSessionCookie(headers) {
  for (const line of setCookies(headers)) {
    for (const part of String(line).split(';')) {
      const token = part.trim()
      if (token.startsWith('app_session_id=') && token.length > 'app_session_id='.length) return token
    }
  }
  return ''
}

/** tRPC 错误信封 → 服务端原文（batch 形态是数组，单发是对象） */
function trpcMessage(bodyText) {
  try {
    let data = JSON.parse(bodyText)
    if (Array.isArray(data)) data = data[0]
    const json = data && data.error && (data.error.json || data.error)
    if (json && typeof json.message === 'string' && json.message.trim()) return json.message.trim()
  } catch { /* 非 JSON：没有原文可用 */ }
  return ''
}

function jsonBody(res) {
  try {
    let data = JSON.parse(res.body)
    if (Array.isArray(data)) data = data[0]
    return data || {}
  } catch {
    return {}
  }
}

function normalizeEmail(value) {
  return String(value || '').trim().toLowerCase()
}

/**
 * 登录并回读账号。
 * @returns {Promise<{cookie: string, email: string}>} cookie 形如 `app_session_id=<JWT>`
 */
async function login({ email, password }) {
  const payload = JSON.stringify({ json: { email, password } })
  let res
  try {
    res = await request({
      method: 'POST',
      url: `${BASE}/api/trpc/auth.login`,
      headers: {
        'Content-Type': 'application/json',
        Origin: BASE,
        Referer: `${BASE}/auth`,
      },
      body: payload,
      timeoutMs: 30000,
    })
  } catch (e) {
    throw new AuthError(
      e.code === 'ETIMEDOUT' ? '连接 Daniel 超时，请检查网络后重试。' : '连不上 Daniel（网络不可达），请稍后重试。',
      { kind: 'network' }
    )
  }

  const ok = res.status >= 200 && res.status < 300
  const cookie = ok ? pickSessionCookie(res.headers) : ''

  if (!ok || !cookie) {
    const serverMessage = trpcMessage(res.body)
    if (serverMessage) {
      const kind = /invalid email or password|incorrect password|invalid credentials|wrong password|邮箱或密码|密码不正确/i.test(serverMessage)
        ? 'credential'
        : 'server'
      throw new AuthError(serverMessage, { kind, status: res.status, serverMessage })
    }
    if (ok) {
      throw new AuthError('登录失败：服务端没有返回会话（app_session_id）。', { kind: 'server', status: res.status })
    }
    throw new AuthError(`登录失败：服务端返回 HTTP ${res.status}。`, { kind: 'server', status: res.status })
  }

  // 回读邮箱：确认拿到的不是别人的会话（§3.2）
  let me
  try {
    const url = `${BASE}/api/trpc/auth.me?batch=1&input=${encodeURIComponent(JSON.stringify({ 0: { json: null } }))}`
    const res2 = await request({
      method: 'GET',
      url,
      headers: { Cookie: cookie, Origin: BASE, Referer: `${BASE}/` },
      timeoutMs: 20000,
    })
    if (res2.status < 200 || res2.status >= 300) {
      throw new AuthError(
        `登录已通过，但回读账号失败（HTTP ${res2.status}），请重试。`,
        { kind: 'server', status: res2.status, serverMessage: trpcMessage(res2.body) }
      )
    }
    const data = jsonBody(res2)
    me = data?.result?.data?.json ?? data?.result?.data ?? null
  } catch (e) {
    if (e instanceof AuthError) throw e
    throw new AuthError('登录已通过，但回读账号时网络中断，请重试。', { kind: 'network' })
  }

  const meEmail = normalizeEmail(me && me.email)
  if (!meEmail) {
    throw new AuthError('登录已通过，但服务端没有返回账号信息，请重试。', { kind: 'mismatch' })
  }
  if (meEmail !== normalizeEmail(email)) {
    throw new AuthError('登录得到的会话与输入的邮箱不一致，已拒绝保存。', { kind: 'mismatch' })
  }

  return { cookie, email: meEmail }
}

module.exports = { login, AuthError, BASE }
