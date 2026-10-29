/**
 * 依赖解析：插件可能被装到任意位置（profile node_modules／本地目录符号链接／全局），
 * 因此 @deepseek-ai/dsh-tools 与 schemastery 不能假设「就在我隔壁」。
 * 解析顺序：① 常规 import；② 从 DSH 安装目录向上找；③ 从 profile node_modules 找。
 */
import { createRequire } from 'node:module'
import { existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { homedir } from 'node:os'

function candidateRoots() {
  const roots = []
  const push = (p) => { if (p && !roots.includes(p)) roots.push(p) }
  // DSH 进程入口（.../dsh/lib/bin.js）→ 向上找包根
  const entry = process.argv[1] ? resolve(process.argv[1]) : ''
  let cur = entry ? dirname(entry) : ''
  for (let i = 0; i < 5 && cur && cur !== dirname(cur); i += 1) { push(cur); cur = dirname(cur) }
  if (process.env.DSH_NODE_MODULES) push(process.env.DSH_NODE_MODULES)
  const dshHome = process.env.DSH_HOME || join(homedir(), '.dsh')
  push(join(dshHome, 'profiles', 'node_modules'))
  push(join(dshHome, 'profiles', 'web', 'node_modules'))
  push(join(dshHome, 'profiles', 'desktop', 'node_modules'))
  return roots
}

export async function loadDep(specifier) {
  try {
    return await import(specifier)
  } catch (firstError) {
    const require = createRequire(join(process.cwd(), 'noop.js'))
    for (const root of candidateRoots()) {
      try {
        const resolved = require.resolve(specifier, { paths: [root] })
        if (existsSync(resolved)) return await import(new URL(`file://${resolved}`).href)
      } catch { /* 继续下一个候选 */ }
    }
    throw new Error(
      `daniel-dsh-plugin: 无法解析依赖 ${specifier}（已尝试常规 import 与 DSH 安装目录）。` +
      `请确认 DSH 安装完整，或设置 DSH_NODE_MODULES。原始错误：${firstError && firstError.message}`,
    )
  }
}
