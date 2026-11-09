#!/usr/bin/env node
/**
 * @deprecated 2026-11-02 起，G3 由 `g3-install-gate.mjs`（安装后运行门禁）取代。
 *
 * 本文件保留为**转发壳**，避免旧文档/脚本里的路径失效：直接以同样参数调用新门禁，退出码一致。
 *
 * 为什么换掉：原占位脚本的判据是「端内跑通（调用随包 daniel-cli / trace 生效 / Python 缺失诊断）」，
 * 需要 PTY 与已安装的产物，本组无法执行；新的 G3 把"能装、能起、独立 home、能退"做成可执行的硬检查，
 * 产线出包后立刻能跑。
 *
 * 以下三项**新 G3 没有覆盖**（原占位内容，留作后续人工/下一道门禁）：
 *   1. 端内问「列一下我的品牌」，确认走的是随包 daniel-cli（profile 内副本的
 *      vendor/data/daniel-cli/bin/daniel），不是 PATH 里的 daniel；
 *   2. 跑一次对话后 $DANIEL_HOME 下有 audit 记录（trace 生效的证据）；
 *   3. 临时 mv 掉随包 python 再启动：应见「Python 不可用」诊断页，而不是白屏。
 */
import { spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import process from 'node:process'

const HERE = dirname(fileURLToPath(import.meta.url))
console.error('[deprecated] g3-runtime-smoke-gate.mjs 已由 g3-install-gate.mjs 取代，本次转交给新门禁执行。')
const result = spawnSync(process.execPath, [join(HERE, 'g3-install-gate.mjs'), ...process.argv.slice(2)], { stdio: 'inherit' })
process.exitCode = result.status ?? 1
