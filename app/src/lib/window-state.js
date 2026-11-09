'use strict'
/**
 * 主窗口位置/大小记忆（S2 §3.1 步骤 3：读 app-state；缺失即默认值）。
 * 落点：$DANIEL_HOME/window.json（0600）。窗口被拔掉外接屏后不能开到屏幕外。
 */

const fs = require('node:fs')
const path = require('node:path')
const { screen } = require('electron')

const DEFAULTS = { width: 1280, height: 820 }
const MIN_VISIBLE = 120 // 至少要有这么多像素落在某块屏里，否则回默认值

function loadWindowState(file) {
  let raw
  try {
    raw = JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return { ...DEFAULTS, center: true }
  }
  const b = raw && raw.main
  if (!b || !Number.isFinite(b.width) || !Number.isFinite(b.height)) return { ...DEFAULTS, center: true }
  const bounds = {
    width: Math.max(960, Math.round(b.width)),
    height: Math.max(640, Math.round(b.height)),
    x: Number.isFinite(b.x) ? Math.round(b.x) : undefined,
    y: Number.isFinite(b.y) ? Math.round(b.y) : undefined,
  }
  if (bounds.x === undefined || bounds.y === undefined || !visibleOnAnyDisplay({ ...bounds, width: MIN_VISIBLE, height: MIN_VISIBLE })) {
    return { ...bounds, center: true }
  }
  return bounds
}

/** 窗口左上角是否落在某块屏幕的可用区域内（粗略但够用） */
function visibleOnAnyDisplay(rect) {
  for (const display of screen.getAllDisplays()) {
    const a = display.workArea
    const overlapX = Math.min(rect.x + rect.width, a.x + a.width) - Math.max(rect.x, a.x)
    const overlapY = Math.min(rect.y + rect.height, a.y + a.height) - Math.max(rect.y, a.y)
    if (overlapX > 0 && overlapY > 0) return true
  }
  return false
}

function saveWindowState(file, bounds) {
  const payload = {
    schema: 1,
    main: {
      x: Math.round(bounds.x),
      y: Math.round(bounds.y),
      width: Math.round(bounds.width),
      height: Math.round(bounds.height),
    },
    savedAt: new Date().toISOString(),
  }
  const dir = path.dirname(file)
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 })
  const tmp = `${file}.tmp-${process.pid}`
  fs.writeFileSync(tmp, JSON.stringify(payload, null, 2) + '\n', { mode: 0o600 })
  fs.renameSync(tmp, file)
}

module.exports = { loadWindowState, saveWindowState, DEFAULTS }
