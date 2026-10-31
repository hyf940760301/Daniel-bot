/**
 * 追问闸（**薄适配**）—— 只做「参数搬运 ＋ 结果透传」，不含任何业务判断。
 *
 * 2026-10-31 起（业务判断下沉 · M3）：28 条字段定义、5 类选择面、触发词、轮次规则
 * 全部下沉到 CLI（`daniel clarify plan|ask`）＋ 语义登记表（附录 B.5）＋ 包内触发词文件。
 * 本文件只剩：对外常量、argv 组装、调 runner、原样交回。
 *
 * 三条硬约束（改这里之前先读）：
 *   ① `command` 由**调用方**写死（`'clarify'` / `'screen_ask'`），**不许透传 CLI 的 `command`**
 *      —— CLI 会回 `clarify.plan`，透传会让 golden 的 command 字段变化 ⇒ 基线红；
 *   ② 本文件不写文案、不写判据（自查：grep 查「key 冒号 单引号」应为 0）；
 *   ③ 同入参必同输出（CLI 侧是纯本地计算），交给 golden 做逐字节比对。
 */

/** 追问清单上限（对外文档/断言用；真正的截断在 CLI 侧） */
export const CLARIFY_MAX_ITEMS = 8
/** 「优先补」条数（同上，仅作对外契约常量） */
export const CLARIFY_TOP_N = 3
/** 允许的场景（工具参数的 enum 真源） */
export const CLARIFY_TOPICS = Object.freeze(['kol_search', 'list_ops', 'brand_setup'])

/** 两个工具各自的**固定** command 值（不许改成 CLI 的 `<模块>.<子命令>`） */
export const TOOL_COMMAND = Object.freeze({ plan: 'clarify', ask: 'screen_ask' })

/** `daniel clarify plan` 的 argv（不含 --json：runner 统一追加） */
export function planArgv(need, topic) {
  const argv = ['clarify', 'plan', '--need', String(need)]
  if (topic !== undefined && topic !== null && String(topic) !== '') argv.push('--topic', String(topic))
  return argv
}

/** `daniel clarify ask` 的 argv（reply/round 不传就不追加，保持"未给"与"空串"的区分） */
export function askArgv(need, reply, round) {
  const argv = ['clarify', 'ask', '--need', String(need)]
  if (reply !== undefined && reply !== null) argv.push('--reply', String(reply))
  if (round !== undefined && round !== null) argv.push('--round', String(round))
  return argv
}

/**
 * 调 CLI 并原样交回结果。
 * @param {(cfg:object, argv:string[]) => Promise<object>} run 注入的 runner（index.js 的 runDaniel）
 * @param {object} config 插件配置
 * @param {'plan'|'ask'} mode
 * @param {{need:string, topic?:string, reply?:string, round?:number}} params
 */
export async function runClarify(run, config, mode, params) {
  const argv = mode === 'plan'
    ? planArgv(params.need, params.topic)
    : askArgv(params.need, params.reply, params.round)
  const r = await run(config, argv)
  return { ok: r.ok, exitCode: r.exitCode, data: r.data, error: r.error }
}
