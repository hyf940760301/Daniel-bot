/**
 * golden 基线用例表（capture.mjs 与 diff.mjs **共用同一份**，否则两边不可比）。
 *
 * 选例原则：
 *   ① **只选不依赖网络／登录的路径**——本机断网、未登录时也必须能复跑；
 *   ② 覆盖每个工具「至少一条能跑通的分支」：真实读（skills / auth status）或
 *      纯本地前置校验（用法错误、权限闸、过期 plan 等），这些分支的输出是确定性的；
 *   ③ 需要真实业务数据才能跑的工具（品牌清单、红人档案、官方库检索等）在 SKIPPED 里
 *      写明「需网络/需登录」，基线不收录它们的输出（收录了也会因账号数据变化而抖动）。
 *
 * 稳定性：CASE 里的 args 是**静态输入**，属于基线的一部分（改了等于改了用例本身）。
 */

/** 需要真实业务数据／联网才能跑的工具：不进基线，但必须仍被注册（工具数见基线 registeredCount） */
export const SKIPPED = [
  { tool: 'daniel_brands_list', reason: '需网络/需登录', detail: '实测 25s 超时（依赖账号品牌索引与平台接口）' },
  { tool: 'daniel_brand_view', reason: '需网络/需登录', detail: '实测可用但依赖在线业务数据，值会随账号变化，不入基线' },
  { tool: 'daniel_brand_count', reason: '需网络/需登录', detail: '实时口径需常驻 worker 直连平台接口' },
  { tool: 'daniel_kol_profile', reason: '需网络/需登录', detail: '频道档案／受众／近 28 天表现均为在线数据' },
  { tool: 'daniel_roster_search', reason: '需网络/需登录', detail: 'YouTube 官方库检索，需登录且属长任务接口' },
]

/**
 * 可离线复跑的用例。id 一经写入基线即**不可改名**（改名会被 diff 判成用例丢失）。
 * offline: true 表示该用例完全在本地确定（无时钟、无随机、无网络），要求字节层一致。
 */
export const CASES = [
  // ── 状态查询（本地 auth status，约 1 秒）──
  { id: 'status_default', tool: 'daniel_status', args: {}, offline: true },

  // ── 登录：只跑前置校验分支（不写任何凭据、不联网）──
  { id: 'login_no_args', tool: 'daniel_login', args: {}, offline: true },
  { id: 'login_file_not_found', tool: 'daniel_login', args: { session_file: '__golden__/no-such-session.txt' }, offline: true },

  // ── 能力清单（随包语料，离线）──
  { id: 'skills_list', tool: 'daniel_skills_list', args: {}, offline: true },
  { id: 'skills_read_index', tool: 'daniel_skills_read', args: { skill: 'kol-screening' }, offline: true },
  { id: 'skills_read_section', tool: 'daniel_skills_read', args: { skill: 'kol-screening', section: 1 }, offline: true },

  // ── 只读直通：用法闸 / 索引重建同意闸 / 真实本地读 ──
  { id: 'run_empty', tool: 'daniel_run', args: { argv: [] }, offline: true },
  { id: 'run_refresh_needs_consent', tool: 'daniel_run', args: { argv: ['brands', 'list', '--refresh'] }, offline: true },
  { id: 'run_skills_list', tool: 'daniel_run', args: { argv: ['skills', 'list'] }, offline: true },
  // TICKET-220 回归：auth status 是**原始数据整段透传**里最容易带 null 的那条
  // （local.本机会话读取异常 / server.服务端原文 曾经都是 null）。修复后这些键直接不出现。
  { id: 'run_auth_status', tool: 'daniel_run', args: { argv: ['auth', 'status'] }, offline: true },

  // ── 批量只读：用法闸 ＋ 真实本地读 ＋ 失败条目不吐 null ──
  { id: 'batch_empty', tool: 'daniel_batch', args: { calls: [] }, offline: true },
  { id: 'batch_too_many', tool: 'daniel_batch', args: { calls: [['skills', 'list'], ['skills', 'list'], ['skills', 'list'], ['skills', 'list'], ['skills', 'list'], ['skills', 'list'], ['skills', 'list']] }, offline: true },
  { id: 'batch_skills_list', tool: 'daniel_batch', args: { calls: [['skills', 'list']] }, offline: true },
  // TICKET-220 回归：失败条目过去 data 是 null；现在用文字说明（未取到／不适用）
  { id: 'batch_auth_status', tool: 'daniel_batch', args: { calls: [['auth', 'status']] }, offline: true },
  { id: 'batch_local_fail', tool: 'daniel_batch', args: { calls: [['brands', 'show']] }, offline: true },

  // ── 追问闸（TICKET-218）：纯函数、离线、同入参必同输出，所以能进基线做逐字节比对 ──
  // 模糊需求：清单顶到上限 8 项 ＋ 溢出项写明「其余按默认口径执行」
  { id: 'clarify_ambiguous', tool: 'daniel_clarify', args: { need: '帮我找一批测评红人' }, offline: true },
  // 明确需求：已说的参数不再问（这份入参把 9 项参数全说到，缺项应为空）
  {
    id: 'clarify_explicit',
    tool: 'daniel_clarify',
    args: { need: '帮我找 US 市场 1 万到 10 万粉的 YouTube 长视频测评红人，要 20 位，交付 Excel 表格，本周五前给我，按近 30 天表现看，名单内排重，受众数据有则用无则标注缺失' },
    offline: true,
  },
  // 场景由调用方指定（名单处理）：口径类与缺项都换成另一套
  { id: 'clarify_list_ops', tool: 'daniel_clarify', args: { need: '把两份名单合并一下', topic: 'list_ops' }, offline: true },
  // 用法闸：need 是空白 → ok:false / kind=usage（不硬编一份空洞清单）
  { id: 'clarify_empty_need', tool: 'daniel_clarify', args: { need: '   ' }, offline: true },

  // ── 写链路：只跑「不会写入」的前置分支（干跑用法闸、假 planId）──
  { id: 'write_plan_empty', tool: 'daniel_write_plan', args: { argv: [] }, offline: true },
  { id: 'write_commit_unknown_plan', tool: 'daniel_write_commit', args: { plan_id: '__golden__-no-such-plan' }, offline: true },
]
