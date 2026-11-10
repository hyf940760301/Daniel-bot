/**
 * 单元测试 · ANSWER_POLICY 的「下一步」固定格式与模块名清单（node:test，不联网、不写盘）
 *
 * 为什么单独测这段文本（CHANGES-NEXT-STEPS-FIX.md §1／§2）：
 *   前端「下一步卡片」只认两件事——一个标题行 ＋ 每项 `<模块名>：<动作>`，
 *   模块名必须是九个业务模块之一。提示词原先只写"要给 1–2 条下一步、写明所属模块"，
 *   既没要求标题独占一行，也没要求写成列表，模型于是写成一段正文或几行裸文字，
 *   卡片整块解析不到（2026-11-03 18:51 的真实回答即如此）。
 *
 * 这份测试把"提示词侧必须始终满足的格式契约"钉住，改文案时不会静默丢掉格式：
 *   ① 必须要求「下一步：」单独一行 ＋「- 模块名：具体动作」；
 *   ② 模块名清单必须与前端解析表逐字一致，且不得残留旧名。
 *
 * 跑法：node --test daniel-bot/packages/0.11.0/tests/answer-policy.test.mjs
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { ANSWER_POLICY } from '../lib/normalize.js'

/**
 * 九个业务模块名，与前端
 * `packages/client/ui-capability-map/src/client/module-map.generated.ts` 的 `modules[].name`
 * **逐字一致**（前端测试 `next-steps.client.spec.tsx` 断言同一份清单）。
 */
const MODULES = [
  '账号与盘点', '品牌档案', '红人检索', '红人名单', '真实性核验',
  '合作追踪', '品牌提及', '内容情报', '声量份额',
]

/** 2026-11-03 之前的旧名：前端解析表已不再认，提示词里也不该出现。 */
const LEGACY = ['账号与工作区', '品牌资产', '真实性与背调']

test('① 固定格式：要求「下一步：」单独一行，下面用「- 模块名：具体动作」列 1–2 条', () => {
  assert.ok(ANSWER_POLICY.includes('下一步：'), '缺少「下一步：」标题行要求')
  assert.ok(ANSWER_POLICY.includes('单独一行'), '没有要求标题独占一行')
  assert.ok(ANSWER_POLICY.includes('- 模块名：具体动作'), '缺少「- 模块名：具体动作」列表写法要求')
  assert.ok(ANSWER_POLICY.includes('1–2 条'), '缺少条数上限（1–2 条）')
  assert.ok(ANSWER_POLICY.includes('模块名必须是上面九个之一'), '没有把模块名的取值范围钉死')
})

test('② 模块名清单：九个新名逐字都在，一次连续列出，顺序与前端一致', () => {
  for (const name of MODULES) {
    assert.ok(ANSWER_POLICY.includes(name), `缺少模块名：${name}`)
  }
  assert.ok(
    ANSWER_POLICY.includes(MODULES.join('／')),
    '九个模块名没有按前端顺序用「／」连续列出',
  )
})

test('③ 不残留任何旧模块名', () => {
  for (const legacy of LEGACY) {
    assert.ok(!ANSWER_POLICY.includes(legacy), `提示词里残留旧名：${legacy}`)
  }
})

test('④ 格式要求是"交付完成后"执行，不是可选建议', () => {
  assert.match(ANSWER_POLICY, /交付完成后，单独一行写/u)
  // 这句仍是硬要求；2026-11-09 起策略末尾追加的是**可选**说明段，不影响它的强制性。
  assert.ok(ANSWER_POLICY.includes('（模块名必须是上面九个之一）。'))
})

test('⑤ 可选说明段：业务思路 1–4 条、自我检讨 1–3 条，没内容不写、不得编造', () => {
  assert.ok(ANSWER_POLICY.includes('业务思路：'), '缺少「业务思路：」标题行')
  assert.ok(ANSWER_POLICY.includes('自我检讨：'), '缺少「自我检讨：」标题行')
  assert.ok(ANSWER_POLICY.includes('可选'), '没有说明这两段是可选输出')
  assert.ok(ANSWER_POLICY.includes('只在确实有内容时才写'), '没有要求没有内容就不写')
  assert.ok(ANSWER_POLICY.includes('禁止编造'), '没有禁止编造说明段')
  assert.ok(ANSWER_POLICY.includes('1–4 条'), '业务思路缺少条数上限')
  assert.ok(ANSWER_POLICY.includes('1–3 条'), '自我检讨缺少条数上限')
  assert.ok(ANSWER_POLICY.includes('这次没有明显问题'), '缺少"没有明显问题"的写法')
  // 两段同样禁止系统内部词（与主体同一约束）。
  assert.ok(ANSWER_POLICY.includes('这两段同样禁止出现接口名、字段名、模块名'))
})
