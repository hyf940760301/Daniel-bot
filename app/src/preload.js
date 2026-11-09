'use strict'
/**
 * 渲染进程唯一入口（S2 §4.1：preload 只暴露登录一个方法，且不缓存密码）。
 * 只暴露这里列出的方法；主进程每个 handler 还会校验来源是 file:// 的本地页面。
 */

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('daniel', {
  /** 启动信息：有没有会话、路径、版本（登录页/诊断用） */
  bootInfo: () => ipcRenderer.invoke('shell:boot-info'),
  /** 登录：email/password 只走这一条 invoke，主进程不保存、不记录 */
  login: (email, password) => ipcRenderer.invoke('shell:login', { email, password }),
  /** 错误页：重试 / 日志 / 诊断 */
  retry: () => ipcRenderer.invoke('shell:retry'),
  openLogs: () => ipcRenderer.invoke('shell:open-logs'),
  copyDiagnostics: () => ipcRenderer.invoke('shell:copy-diagnostics'),
  errorInfo: () => ipcRenderer.invoke('shell:error-info'),
  quit: () => ipcRenderer.invoke('shell:quit'),
  /** 闪屏状态订阅；返回取消函数 */
  onStatus: (cb) => {
    const handler = (_event, message) => cb(message)
    ipcRenderer.on('shell:status', handler)
    return () => ipcRenderer.removeListener('shell:status', handler)
  },
})
