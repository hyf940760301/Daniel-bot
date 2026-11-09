/**
 * 输出契约层（trace）：**三档开关 ＋ 详简两层 ＋ 四段白名单 ＋ 校验器 ＋ 追加式装配**
 *
 * 一句话：谁必须带溯源、带什么、缺了怎么办，全在这一个文件里定；工具实现不各写一套。
 *
 * 三档开关（`Config.trace`）：
 *   off     → 返回体**完全不含** trace 字段（等价 0.9.1 的老行为，用于随时一键回退）
 *   summary → 白名单工具追加 trace，四段各 ≤2 条短句（结论级，默认档）
 *   full    → 白名单工具追加 trace，完整四段（骨架 ＋ 每条理由更细的表述）
 *
 * 详简两层由 `trace.层级` 写明（`summary`／`full`），并附 `trace.末尾提示` 一句固定话术
 * （设计草案 §2.5 的常驻提示；措辞逐字固定，不许改写）：
 *   summary → 「—— 目前是简略版本，想看详细报告或说明（筛选逻辑、排除明细、口径依据）可以直接告诉我。」
 *   full    → 「需要逐条明细的话告诉我。」
 *   off／非白名单 → 不出现该字段。
 *
 * 五条不改动承诺在本文件的落点：
 *   ① 工具名/参数名不动 —— 本文件不碰工具定义；
 *   ② 旧字段不改不删   —— 只在返回体**末尾追加** `trace`，其余键原样；
 *   ③ 默认行为不变     —— 非白名单工具在任何档位都不加字段；
 *   ④ 失败不升级       —— 四段生成失败降级成「本次溯源不可用」，不抛错；
 *   ⑤ 写操作零改动     —— daniel_write_plan / daniel_write_commit 不在白名单，永不加字段。
 */
import {
  EXCLUDED_CSV_COLUMNS,
  EXCLUDED_CSV_THRESHOLD,
  LEDGER_TTL_SECONDS,
  TRACE_EXCLUDED_LINE_MAX,
  TRACE_EXCLUDED_MAX_LINES,
  TRACE_LEVELS,
  TRACE_MISSING,
  TRACE_NO_GATE,
  TRACE_SECTIONS,
  TRACE_UNAVAILABLE,
  TRACE_VERSION,
  buildTraceSections,
  gateLedgerBlock,
  readRosterLedger,
  rosterArgsKey,
  rosterTaskId,
  traceBaseDir,
  traceLevelOf,
  traceMissing,
  traceSections,
  traceUnavailable,
  writeExcludedCsv,
} from './normalize.js'

export {
  EXCLUDED_CSV_COLUMNS, EXCLUDED_CSV_THRESHOLD, LEDGER_TTL_SECONDS,
  TRACE_EXCLUDED_LINE_MAX, TRACE_EXCLUDED_MAX_LINES,
  TRACE_LEVELS, TRACE_MISSING, TRACE_NO_GATE, TRACE_SECTIONS, TRACE_UNAVAILABLE, TRACE_VERSION,
  buildTraceSections, gateLedgerBlock, readRosterLedger, rosterArgsKey, rosterTaskId,
  traceBaseDir, traceLevelOf, traceMissing, traceSections, traceUnavailable, writeExcludedCsv,
}

/** 三档开关（顺序即文档顺序） */
export const TRACE_MODES = Object.freeze(['off', 'summary', 'full'])
export const TRACE_DEFAULT_MODE = 'summary'

/**
 * ★ 常驻提示（措辞逐字固定，用户会形成"看到这行就知道能展开"的条件反射）★
 * 简版每次都给；详版换成轻量尾注；off／非白名单不给。
 */
export const TRACE_HINT_SUMMARY = '—— 目前是简略版本，想看详细报告或说明（筛选逻辑、排除明细、口径依据）可以直接告诉我。'
export const TRACE_HINT_FULL = '需要逐条明细的话告诉我。'

/** 层级 → 末尾提示（唯一映射，别处不许再拼这句） */
export function traceHintOf(level) {
  return traceLevelOf(level) === 'full' ? TRACE_HINT_FULL : TRACE_HINT_SUMMARY
}

/**
 * ★ 四段强制白名单（**单一来源**，后续票直接复用，不许在别处再抄一份）★
 *
 * 进名单的判据（设计草案 §2.1）：这次输出的价值来自"我筛掉了什么、为什么筛掉"——
 * 名单类／筛选类／评估类。
 * 不带的是：单点查询（brand_view／kol_profile 之外的档案查询）、纯状态查询（status／
 * skills_list／skills_read／login）、单条读数（brand_count）、以及写链路两名（两段式零改动）。
 */
export const TRACE_TOOLS = Object.freeze([
  'daniel_brands_list',      // 名单类：品牌清单
  'daniel_roster_search',    // 名单类：官方库找红人
  'daniel_kol_profile',      // 评估类：红人档案＋受众画像
  'daniel_batch',            // 批量取数：多命令一次回，结论来自多条读数
  'daniel_run',              // 直通取数：任意只读子命令
])

/** 不在白名单的工具（登记在此只为"名单可见"，代码按 TRACE_TOOLS 判断） */
export const TRACE_EXEMPT_TOOLS = Object.freeze([
  'daniel_status', 'daniel_skills_list', 'daniel_skills_read', 'daniel_login',
  'daniel_brand_view', 'daniel_brand_count',
  'daniel_write_plan', 'daniel_write_commit',
  // TICKET-218：追问清单只产出「缺哪几项参数」，不是筛选/评估结论，按判据不必带溯源
  'daniel_clarify', 'daniel_screen_ask',
  // 检索通道（2026-11-03 改为两条任务式通道）：出计划／提交／查状态都不产出"我筛掉了什么"，
  // 结果还是候选清单、筛选在后续环节，所以不套四段；退役的官方库工具已不产出名单（ok=false，
  // finish 不会追加），但名字仍留在上面白名单里，避免历史返回体的字段口径发生变化。
  'daniel_deep_research', 'daniel_deep_research_commit',
  'daniel_open_research', 'daniel_open_research_commit', 'daniel_research_status',
])

/** 开关归一：空值/未知值一律按默认档处理（配置写错不至于让输出掉字段） */
export function normalizeTraceMode(v) {
  const m = String(v === undefined || v === null ? '' : v).trim().toLowerCase()
  return TRACE_MODES.includes(m) ? m : TRACE_DEFAULT_MODE
}

export function isTraceTool(name) {
  return TRACE_TOOLS.includes(String(name === undefined || name === null ? '' : name))
}

/** 段值合格判据：非空字符串，或"全部非空字符串"的非空数组 */
export function sectionOk(v) {
  if (typeof v === 'string') return v.trim().length > 0
  if (Array.isArray(v)) return v.length > 0 && v.every((x) => typeof x === 'string' && x.trim().length > 0)
  return false
}

/**
 * 校验器：白名单工具在 summary/full 档必须四段齐全。
 * **off 档永不校验**（这是"一键回退"能生效的前提）。
 * @returns {{ok: boolean, missing: string[], checked: boolean}}
 */
export function assertTrace(toolName, trace, traceMode) {
  const mode = normalizeTraceMode(traceMode)
  if (mode === 'off') return { ok: true, missing: [], checked: false }
  if (!isTraceTool(toolName)) return { ok: true, missing: [], checked: false }
  const sections = (trace && trace['四段']) || {}
  const missing = TRACE_SECTIONS.filter((n) => !sectionOk(sections[n]))
  return { ok: missing.length === 0, missing, checked: true }
}

/**
 * 追加式装配（工具出口统一走这里）：**off / 非白名单 → 原对象原样返回**（一个字段都不动）。
 *
 * 校验不通过时（说明生成器有 bug，不是用户的问题）返回 ok:false / exitCode:2 /
 * error.kind='trace_incomplete' —— 按契约"缺段不许算成功"，同时不把未校验的业务数据
 * 当成成功结果抛出去。
 *
 * @param {object} o
 * @param {string} o.tool    工具名
 * @param {string} o.mode    开关档位
 * @param {object} o.args    本次入参（生成四段要用）
 * @param {object} o.data    本次业务数据（生成四段要用）
 * @param {object} o.result  已清洗好的老返回体（clean() 的输出）
 * @param {string} o.answerPolicy 回答纪律文本（拒绝时也要带，保持返回体形状一致）
 * @param {Function} [o.build] 四段生成器（默认 buildTraceSections；参数化是为了让测试能注入"缺段"场景）
 */
export function finalizeOutput(o) {
  const { tool, mode, result } = o || {}
  const args = (o && o.args) || {}
  const data = o && o.data
  const answerPolicy = (o && o.answerPolicy) || ''
  const build = (o && o.build) || buildTraceSections
  const m = normalizeTraceMode(mode)
  const level = traceLevelOf(m)

  // ① 关闭档：老行为，连 trace 字段都不出现
  // ② 非白名单：老行为，一个字段都不加
  if (m === 'off' || !isTraceTool(tool)) return result

  const trace = {
    版本: TRACE_VERSION,
    层级: level,                                       // summary｜full（详简两层在返回体里可见）
    开关: m,
    四段: build(tool, { args, data, mode: m }),        // 简版各段 ≤2 条短句；详版完整四段
    末尾提示: traceHintOf(level),                      // 常驻提示：措辞逐字固定，跟着结论走
  }
  const verdict = assertTrace(tool, trace, m)
  if (!verdict.ok) {
    const rejected = { ok: false, exitCode: 2 }
    if (answerPolicy) rejected['回答纪律'] = String(answerPolicy)
    if (result && typeof result.command === 'string' && result.command) rejected.command = result.command
    rejected.error = {
      kind: 'trace_incomplete',
      message: `输出契约校验未通过：缺「${verdict.missing.join('、')}」四段之一，按规则不许返回成功（trace=${m}）。`,
    }
    return rejected
  }
  // 只追加：老字段原样，trace 放最后
  return { ...result, trace }
}
