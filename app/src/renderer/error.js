'use strict'

const badge = document.getElementById('badge')
const titleEl = document.getElementById('err-title')
const messageEl = document.getElementById('err-message')
const detailEl = document.getElementById('err-detail')
const logEl = document.getElementById('err-log')
const retryEl = document.getElementById('retry')
const logsEl = document.getElementById('logs')
const diagEl = document.getElementById('diag')
const copyHint = document.getElementById('copy-hint')

const BADGE = {
  dsh: '!',
  plugin: '⊘',
  auth: '⋯',
  seed: '!',
  env: '!',
  unknown: '!',
}

function render(info) {
  if (!info) return
  const kind = info.kind || 'unknown'
  badge.className = 'badge ' + kind
  badge.textContent = BADGE[kind] || '!'
  titleEl.textContent = info.title || '出错了'
  messageEl.textContent = info.message || ''
  if (info.detail && String(info.detail).trim()) {
    detailEl.textContent = String(info.detail).trim()
    detailEl.hidden = false
  } else {
    detailEl.hidden = true
  }
  logEl.textContent = info.logPath || '—'
  if (kind === 'auth') retryEl.textContent = '回到登录页'
}

async function load() {
  if (!window.daniel) {
    messageEl.textContent = '页面没有连上应用主进程。'
    return
  }
  try {
    render(await window.daniel.errorInfo())
  } catch (err) {
    messageEl.textContent = '读取错误详情失败：' + (err && err.message ? err.message : String(err))
  }
}

retryEl.addEventListener('click', async () => {
  retryEl.disabled = true
  retryEl.textContent = '正在重试…'
  try {
    await window.daniel.retry()
  } finally {
    setTimeout(() => {
      retryEl.disabled = false
      retryEl.textContent = badge.className.includes('auth') ? '回到登录页' : '重试'
    }, 1500)
  }
})

logsEl.addEventListener('click', () => { window.daniel.openLogs() })

diagEl.addEventListener('click', async () => {
  try {
    await window.daniel.copyDiagnostics()
    copyHint.textContent = '诊断信息已复制到剪贴板'
    setTimeout(() => { copyHint.textContent = '' }, 2400)
  } catch {
    copyHint.textContent = '复制失败'
  }
})

load()
