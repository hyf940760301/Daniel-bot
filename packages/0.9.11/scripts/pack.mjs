#!/usr/bin/env node
/**
 * 出包（0.9.8 新增）：先拷一份**暂存副本**，按 pack spec X02／X03／X26 剪掉不该外发的文件，
 * 再对副本跑 `npm pack`。源目录一个字节都不动。
 *
 * 为什么不用 .npmignore：实测 npm 10.9.8 下，只要 package.json 里有 `files` 字段，
 * `.npmignore` 就**完全不生效**（0.9.8 出包时验证过：把 __pycache__ 写进 .npmignore，
 * dry-run 仍然是 197 个文件、.pyc 照旧在包里）。所以排除只能在打包前做。
 *
 * 判据出处：`vendor/data/daniel-cli/daniel_cli/pack/spec.py`
 *   X02 `*__pycache__*` / X03 `*.pyc`   字节码含本机绝对路径
 *   X26 `data/daniel-cli/mcp/_fixtures/cross-host/*.json`  刻意含本机路径的正控夹具
 *
 * 用法：
 *   node scripts/pack.mjs                # 出到仓库根目录，名字按 package.json 版本
 *   node scripts/pack.mjs --dest ../     # 指定落点
 *   node scripts/pack.mjs --keep         # 保留暂存副本便于排查
 */

import { cpSync, mkdtempSync, rmSync, readdirSync, statSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'

const HERE = dirname(fileURLToPath(import.meta.url))
const PKG = resolve(HERE, '..')
const argv = process.argv.slice(2)
const getArg = (n, d = null) => {
  const i = argv.indexOf(n)
  return i >= 0 && argv[i + 1] ? argv[i + 1] : d
}
const dest = resolve(getArg('--dest', resolve(PKG, '..')))
const keep = argv.includes('--keep')

// ── 排除规则（与 pack spec 一一对应）────────────────────────
const RULES = [
  { id: 'X02/X03', desc: '__pycache__ 与 *.pyc', test: (p) => /(^|\/)__pycache__(\/|$)/.test(p) || p.endsWith('.pyc') },
  { id: 'X26', desc: 'cross-host 正控夹具（含本机路径）', test: (p) => p.includes('/mcp/_fixtures/cross-host/') },
  { id: '—', desc: '.DS_Store', test: (p) => p.endsWith('.DS_Store') },
]
const excluded = (relPath) => RULES.some((r) => r.test(relPath))

const pkgJson = JSON.parse(execFileSync('cat', [join(PKG, 'package.json')]).toString('utf8'))
const filesField = pkgJson.files || []

const stage = mkdtempSync(join(tmpdir(), 'daniel-pack-'))
const pruned = []

// 只拷 `files` 白名单里声明的内容 ＋ package.json（npm 自己也要它）
const toCopy = [...filesField, 'package.json']
for (const entry of toCopy) {
  const src = join(PKG, entry)
  if (!existsSync(src)) throw new Error('files 字段里的路径不存在：' + entry)
  cpSync(src, join(stage, entry), {
    recursive: true,
    filter: (from) => {
      const rel = from.slice(PKG.length + 1)
      if (!rel) return true
      if (excluded(rel)) {
        pruned.push(rel)
        return false
      }
      return true
    },
  })
}

const out = execFileSync(
  'npm',
  ['pack', stage, '--pack-destination', dest, '--cache', join(stage, '.npm-cache'), '--logs-dir', join(stage, '.npm-logs')],
  { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 }
)
const name = (out.trim().split('\n').pop() || '').trim()
const tgzPath = join(dest, name)

console.log(`暂存：${stage}`)
console.log(`剪掉 ${pruned.length} 条：`)
for (const r of RULES) {
  const n = pruned.filter((p) => r.test(p)).length
  if (n) console.log(`  ${r.id}  ${r.desc}  ×${n}`)
}
console.log(`出包：${tgzPath}`)
const st = statSync(tgzPath)
console.log(`大小：${st.size.toLocaleString()} B`)
if (!keep) rmSync(stage, { recursive: true, force: true })
else console.log(`暂存已保留：${stage}`)
