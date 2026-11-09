/**
 * G1-4 最小单测：插件复制成真目录的幂等性（产品代码 embedDanielPlugin）。
 *
 * 判据不是"第二次没报错"，而是：
 *   · 第二次返回 copied=false；
 *   · 目标树的「内容 + 大小 + mtime」指纹完全不变（真幂等 = 不重写，时间戳不动）；
 *   · 损坏副本会被替换（否则幂等检查会掩盖损坏）；
 *   · 插件源缺失时壳仍可用（installed=false，不抛异常）。
 *
 * 运行：
 *   cd /tmp/dsh-build/dsh-src
 *   node --import tsx --test /path/to/daniel-bot/app/tests/specs/embed-idempotent.spec.mjs
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const SRC = process.env.DSH_SRC ?? '/tmp/dsh-build/dsh-src'
const { embedDanielPlugin } = await import(`${SRC}/apps/desktop/src/daniel-plugin.ts`)
const SOURCE = process.env.DANIEL_PLUGIN_SOURCE ?? join(SRC, 'apps/desktop/resources/vendor/daniel-dsh-plugin')

/** 记录树里每个文件的 路径+大小+mtime，用来证明"没重写"（只比内容会漏掉重写）。 */
function fingerprint(root) {
  const files = []
  const visit = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name)
      if (entry.isDirectory()) { visit(path); continue }
      const stat = statSync(path)
      files.push(`${path.slice(root.length)}|${String(stat.size)}|${String(stat.mtimeMs)}`)
    }
  }
  visit(root)
  return files.sort().join('\n')
}

test('embedDanielPlugin: 第二次启动不重写副本（内容与 mtime 都不变）', () => {
  const profile = mkdtempSync(join(tmpdir(), 'qa-embed-'))
  const first = embedDanielPlugin(SOURCE, profile)
  assert.deepEqual({ ...first }, { installed: true, copied: true }, '首次必须复制')

  const target = join(profile, 'node_modules/daniel-dsh-plugin')
  const before = fingerprint(target)
  const second = embedDanielPlugin(SOURCE, profile)
  assert.deepEqual({ ...second }, { installed: true, copied: false }, '第二次不得复制')
  assert.equal(fingerprint(target), before, '树指纹（内容+大小+mtime）必须不变')
})

test('embedDanielPlugin: 损坏副本会被替换', () => {
  const profile = mkdtempSync(join(tmpdir(), 'qa-embed-'))
  embedDanielPlugin(SOURCE, profile)
  writeFileSync(join(profile, 'node_modules/daniel-dsh-plugin', 'package.json'), '{"name":"broken"}')
  const third = embedDanielPlugin(SOURCE, profile)
  assert.equal(third.copied, true, '损坏副本必须重植')
})

test('embedDanielPlugin: 插件源缺失时壳仍可用', () => {
  const profile = mkdtempSync(join(tmpdir(), 'qa-embed-'))
  const missing = join(profile, 'absent-source')
  try {
    const result = embedDanielPlugin(missing, profile)
    assert.deepEqual({ ...result }, { installed: false, copied: false })
  } finally {
    rmSync(missing, { recursive: true, force: true })
  }
})
