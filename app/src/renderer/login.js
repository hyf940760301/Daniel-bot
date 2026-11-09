'use strict'

const form = document.getElementById('login-form')
const emailEl = document.getElementById('email')
const passwordEl = document.getElementById('password')
const submitEl = document.getElementById('submit')
const errorBox = document.getElementById('login-error')
const errorText = document.getElementById('login-error-text')
const errorHint = document.getElementById('login-error-hint')
const statusEl = document.getElementById('form-status')

let busy = false

function showError(message, hint) {
  errorText.textContent = message || '登录失败'
  if (hint) {
    errorHint.textContent = hint
    errorHint.hidden = false
  } else {
    errorHint.hidden = true
  }
  errorBox.classList.add('show')
}

function clearError() {
  errorBox.classList.remove('show')
  errorText.textContent = ''
  errorHint.hidden = true
}

function setBusy(next) {
  busy = next
  submitEl.disabled = next
  submitEl.textContent = next ? '正在登录…' : '登录'
  statusEl.textContent = next ? '正在验证账号…' : ''
}

form.addEventListener('submit', async (event) => {
  event.preventDefault()
  if (busy) return
  clearError()

  const email = emailEl.value.trim()
  const password = passwordEl.value
  if (!email || !password) {
    showError('请输入邮箱和密码。')
    return
  }
  if (!window.daniel) {
    showError('页面没有连上应用主进程，请重启 Daniel Bot。')
    return
  }

  setBusy(true)
  try {
    const result = await window.daniel.login(email, password)
    // 密码用完即弃：即使失败也不再留在输入框里
    passwordEl.value = ''
    if (!result || result.ok !== true) {
      if (result && result.fatal) {
        // 已经切到错误页（网络不可达等），这里不再抢镜
        return
      }
      showError(result && result.message ? result.message : '登录失败，请重试。', result && result.hint)
      setBusy(false)
      return
    }
    statusEl.textContent = '登录成功，正在启动服务…'
  } catch (err) {
    passwordEl.value = ''
    showError('登录失败：' + (err && err.message ? err.message : String(err)))
    setBusy(false)
  }
})

emailEl.addEventListener('input', clearError)
passwordEl.addEventListener('input', clearError)
