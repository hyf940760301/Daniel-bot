# 读结果信封（`daniel.read.v1`）—— 读链结构化输出契约

> 来源：TICKET-150「P1 读链结构化补全」。适用：`daniel mentions …`／`daniel intel …` 等**读**子命令，
> 以及它们消费的既有仪器 `.kol-tools/daniel_mentions.py`／`daniel_intel.py`。
> 本文件只写**读链的搬运口径**（条数、游标、截断标注）；业务字段的含义仍以能力层语料为准
> （`kol-daniel-api`／`kol-intelligence` 束），本层不新增任何业务判据。

## 1. 两条路，同一份结果

```
仪器路径：python3 .kol-tools/daniel_intel.py --brand <品牌> actions --json        → 读结果信封
CLI 路径：python3 data/daniel-cli/bin/daniel intel actions --brand <品牌> --json  → 外层信封.data ＝ 信封.result
```

两条路的**条目集合必须逐字一致**（同名同序同条数）。这条回归由
`data/daniel-cli/read_parity_check.py` 守着（在线只读；`--self-test` 离线）。

## 2. 仪器侧的读结果信封（`--json` 时 stdout 有且只有一个 JSON 文档）

| 字段 | 含义 |
|---|---|
| `schema` | 固定 `daniel.read.v1` |
| `route` | 真实路由名（只读 GET） |
| `method` | `GET` |
| `input` | 本次真实入参（脱敏后；供复核"这份结果是对谁查的"） |
| `total` | 服务端给的总数；服务端没给则为本次取到的全量条数；单对象为 `null` |
| `returned` | 本次真正放进 `result` 的条数 |
| `result` | 服务端原样返回（仅做凭据类脱敏，字段不增删不改名） |
| `filter` | 口径回显：`echo`（本次实际发出的过滤条件，逐字来自入参）＋ `taskLevelExcluded`（服务端自报的**任务级**排除条数） |
| `paging` | 分页导航：`kind／limit／offset／page／pageSize／totalPages／hasMore／nextCursor／nextPage／singlePageMax／rowsUnique／dedupOk／stabilityNote／howToContinue` |
| `truncated` | 本次结果是否**被收窄过**（用户给了上限／服务端截取／字符预算触发） |
| `truncatedReason` | 收窄的原因、上限值、被收窄了多少条（`truncated=true` 时必有） |

`paging.kind` 是**数据的形状**（不是业务判据）：

| kind | 什么时候 | 游标怎么用 |
|---|---|---|
| `offset` | 入参没有分页键（如 `actions.list` 一次返回全部） | `nextCursor` ＝下一条的偏移，用 `--offset <N>` 续取；或去掉 `--limit` 一次取全 |
| `server-page` | 入参带 `page/pageSize`（如 `mentions results`） | `nextPage` ＝下一页页码，用 `--page <N>` 续取；`totalPages` 由服务端给 |
| `server-limit` | 入参带 `limit` 且**服务端不返回总数**（如 `mentions jobs`／`top-channels`） | 返回条数＝上限时 `truncated=true`；加大 `--limit` 再取（接口无游标，能否再取到由服务端决定） |
| `server-window` | 入参带 `limit/offset`，服务端已切好窗口（如内容视频列表） | 加大 `--limit`／改 `--offset` |
| `none` | 单对象或一次返回即全量 | 无分页 |

### 2.1 `paging` 里的三条"翻页安全"事实（TICKET-150 · 总监裁决）

按页翻看这类列表**会重复或漏条**（排序键大量并列 ⇒ 偏移分页的边界不稳定；实测同一份
114 条的列表按页取只会得到 110 个不同编号，同时漏掉 4 条）。所以信封里带三条事实：

| 字段 | 含义 |
|---|---|
| `singlePageMax` | 单页上限（实测 200）：**总数不超过它时不该翻页**，一页取完最稳 |
| `rowsUnique` ／ `dedupOk` | 本批条数与**不同编号数**；`dedupOk=false` ⇒ 本批有重复行，信封的 `notes` 会写明"这批数据不可信，请按编号去重或一次取全" |
| `stabilityNote` | 需要翻页时（`totalPages>1`）给出的提示：「排序键并列 ⇒ 按页翻取可能重复或遗漏；总数不超过单页上限时请一页取完，翻页结果要按编号去重后再用」 |

**取数收口**（对"要拿全量"的调用方）：先用 `--page-size 200` 取一页 —— 服务端说 `totalPages=1`
就是全量，**不翻页**；确实超过 200 才逐页取，并在取完后断言「累计条数 == 不同编号数」；
断言不过就**不许**把这份数据当结果交出去（重取或明确标注不可信）。
`data/daniel-cli/read_parity_check.py` 里的 `fetch_all_rows()` 就是这条规则的落地实现。

### 2.2 `filter`：口径必须回显，且不许把"任务级统计"说成"本次被过滤"

- `echo`：本次**真正发出**的过滤条件（如 `relevanceFilter=confirmed_likely`）。
  `mentions results` 的默认口径**只给与本品相关的提及** —— 与本品不相关的条目会被挡在结果外；
  要看全部必须显式 `--relevance-filter all`（取值域与仪器 `RELEVANCE_FILTER` 同源，并有一条断言锁死两者一致）。
- `taskLevelExcluded`：服务端字段 `excludedIrrelevant` 的**原样搬运**。它是**任务级统计**
  ——「本次分析共有 N 条被判为不相关、不计入推广建议」，**与本次请求的筛选项无关**
  （实测：`--relevance-filter all` 时服务端**照样**返回同一个数）。因此字段名带 `taskLevel`，
  不暗示"本次被过滤了多少"。
- 要表达"**本次请求**隐藏了多少" ⇒ 只能用**两个口径的服务端 `total` 相减**
  （例如全量 114 − 本次 96 ＝ 18），而且**必须标明这是算术推导、不是服务端字段**。
  回归工具把这行单列出来标注为"算术推导（不作通过条件）"。

## 3. CLI 侧的外层信封

CLI 的 `--json` 仍是一个信封（`ok／cli／version／module／command／readOnly／exitCode／elapsedMs`），
其中：

- `data` ＝ 读结果信封的 **`result`**（业务载荷，键与仪器口径逐字一致）；
- `read` ＝ 读链元信息（`schema／route／method／filter／total／returned／paging／truncated／truncatedReason`）；
- `notes` ＝ 被收窄时的**人话说明**（同一条也会打到 stderr，机器与人都看得到）。

宿主（如 MCP）不读 `read` 也不影响取数；读了就能知道"这是不是全量、下一页怎么取"。

## 4. 上限与截断：一律显式，绝不静默（TICKET-150 验收第 3 条）

| 上限 | 上限值 | 触发条件 | 取全办法 |
|---|---|---|---|
| 条数上限（本机分页） | 用户给的 `--limit N` | 全量条数 > N | `--offset <nextCursor>` 续取，或去掉 `--limit` |
| 服务端每页条数 | `--page-size`（实测取值域 **10–200**） | 请求即分页 | `--page <nextPage>` 逐页取（`total`／`totalPages` 由服务端给） |
| 服务端条数上限 | `--limit`（`listJobs`／`topChannels`） | 返回条数 ＝ 上限（即可能还有更多） | 加大 `--limit` 再取；接口不返回总数，所以**只有触顶才敢说"可能还有更多"**（`hasMore=null`） |
| 字符预算 | `--max-chars N`（**默认 0 ＝ 不限**） | 序列化结果超过 N 个字符 | 去掉 `--max-chars`，或用 `--offset <nextCursor>` 分批取 |

- **旧行为已废止**：仪器 `--json` 曾把结果截到 12000 字符（intel）／200000 字符（mentions results／evidence／export），
  截断处不是合法 JSON，调用方只能"抢救前几条"。现在**不再按字符截断**；
  唯一会按字符收窄的是显式 `--max-chars`，而且**只丢整条、绝不切字符**（输出永远是合法 JSON），
  并同时给出 `truncated=true`、`truncatedReason`（含上限值与已保留条数）与续取游标。
- 人读模式（不带 `--json`）显示的是**摘要**，行内会写明"全量请用 `--json`"，不会被误当成全量。

## 5. 失败与退出码

| 情形 | 退出码 | stdout（`--json`） | stderr |
|---|---|---|---|
| 成功 | 0 | 一个 JSON 文档（含 `data`／`read`） | 进度行 |
| 入参不合法（越界／错枚举／缺键／对象找不到） | **2**（用户错误） | 一个 JSON 文档：`ok=false` ＋ `error{kind:"usage",message,hint}` | 一句人话（**无 traceback**） |
| 本地能断定的"编号不存在"（`mentions results/status --job`） | **2**（用户错误） | 同上，`message` 里列出该品牌现有任务编号 | 一句人话 |
| 本地**不能**断定（该品牌任务清单已触上限） | 1（内部错误，服务端 500） | 同上但 `kind:"internal"`，`message` 追加"任务较多，请先核对编号" | 仪器原始尾行 |
| 真故障（网络、500、解析失败） | 1（内部错误） | 同上但 `kind:"internal"` | 仪器原始尾行／traceback（要看得见） |

仪器侧同口径（TICKET-168 已把这条落到仪器自己身上）：本地入参校验抛 `ParamError`
（`daniel_mentions.py`）或用 `SystemExit("人话")`（`daniel_intel.py`），服务端 **400／422**
（本次请求本身不合法，如 `pageSize` 超服务端上限）也算用户错误；入口包装统一归一成退出码 2；
真故障（5xx／不可达／解析失败／**404 等本地断不了的情形**）→ 1，traceback 保留在 stderr。

### 5.0 仪器侧的失败信封（`daniel.error.v1`）与退出码判据

仪器**直跑**（不经 `daniel` CLI）时，`--json` 的失败出口与成功出口一样受单文档契约约束：

```json
{
 "ok": false,
 "schema": "daniel.error.v1",
 "route": "<出问题的只读路由，拿不到就不给>",
 "exitCode": 2,
 "error": {"kind": "usage", "message": "<一句人话>", "hint": "<怎么办 ＋ 服务端原话>"}
}
```

| 情形 | 退出码 | `error.kind` | stderr |
|---|---|---|---|
| 本地入参校验不过（`ParamError`／`SystemExit("人话")`／argparse 参数错） | **2** | `usage` | **一句人话**（`--json` 时；无 traceback） |
| 服务端 **400／422**（本次请求被服务端判为不合法，如 `pageSize` 越界） | **2** | `usage` | 一句人话 |
| 服务端 5xx／网络不可达／响应解析失败 | **1** | `internal` | traceback ＋ 末行一句人话 |
| 服务端 404／401／403（对象不存在或不可见、身份与权限问题） | **1** | `internal` | 同上；**本地断不了"是编号错还是权限错"，不冒充用户错误** |
| 写链需确认（干跑） | **3** | `confirm` | 一句人话 |

三条判据（**只做错误归类，不含业务判据**）：

1. **"入参类 4xx"只认 400／422**。`400 BAD_REQUEST`／`422` 按定义就是"我们发出去的请求本身不合法"；
   401／403 是身份与权限、404 是对象存在性 —— 都不是"用户填错了参数"，报 1 更诚实。
2. **拿不到原始状态码时不猜**：`daniel_client.query()` 会把异常压成一行
   `… 失败: HTTP Error 400: …`，出口层从这行文字里认状态码（只认这个固定形状），
   认不到就按 1 报。
3. **服务端原话进 `error.hint`，不进 stderr**：`--json` 时 stdout 只有一个文档、stderr 只留一句
   人话，排障信息（zod 的 `too_big: maximum 100`、5xx 的原始报文摘要）因此放在 JSON 的 `hint` 里
   —— 机器与人都能读到，两边都不被淹。

实现位置（**收口只有一个地方**）：`.kol-tools/daniel_io.py` 的 `cli(main, argv, …)`。
各仪器只在自己的入口写 `return daniel_io.cli(main, argv, usage_errors=(ParamError,))`，
**逐命令重复 catch 不算完成**。`daniel_io` 把 stdout 包一层 `raw_decode` 计数器：
已经出过文档就**绝不补第二份**（补第二份正是"上层把错误当成成功数据"的病根）。

### 5.1 stdout 恒定一个 JSON 文档（**机器可读契约**）

`--json` 时 stdout **有且只有一个 JSON 文档**（吃掉这一个之后剩余全是空白）。这条由
`data/daniel-cli/stdout_contract_check.py` 守着：它用 `json.JSONDecoder().raw_decode` **数**文档个数
（`json.loads` 分不清"一个文档 + 尾随日志行"与"两个文档"），并覆盖成功（0）／用户错误（2）／
需确认（3）／内部错误（1）四条路径，外加静态审计（扫"出结果之后又调 error/raise"的位置）。

仪器侧的同一条判据由 `python3 .kol-tools/daniel_intel.py --self-test` 的
`errcontract_*` 五项正控守着（四条失败路径 ＋ 一条真阴性，跑真进程、用 `raw_decode` 数文档）。

**`--json` 下不能同用的开关**（用了就报入参错／退出码 2，而不是悄悄多吐一份文档）：
一次调用只允许**一个**数据出口。例如 `daniel_intel.py` 的 `--json` 与
`--raw`／`--shape`／`--routes`／`--self-test` 互斥，`--json` 与"多个子命令"互斥
（多子命令会出多份信封）。`daniel_authenticity.py` 的 `--json` 与 `--explain-weights` 同理。

## 6. 复跑命令（只读）

```bash
# 仪器路径 vs CLI 路径键比对（三案例）
python3 data/daniel-cli/read_parity_check.py --brand 3690002
python3 data/daniel-cli/read_parity_check.py --self-test        # 离线自检（含反例）

# stdout 契约（`--json` 恰好一个 JSON 文档）：在线四类路径 ＋ 离线静态审计 ＋ 判据自检
python3 data/daniel-cli/stdout_contract_check.py
python3 data/daniel-cli/stdout_contract_check.py --audit-source
python3 data/daniel-cli/stdout_contract_check.py --self-test

# 读链自检（离线，不联网）
python3 .kol-tools/daniel_intel.py --self-test
python3 .kol-tools/daniel_mentions.py --self-test

# 分页与截断标注的现场抽查
python3 data/daniel-cli/bin/daniel intel actions --brand 3690002 --json | head -40
python3 data/daniel-cli/bin/daniel intel actions --brand 3690002 --limit 5 --json
python3 data/daniel-cli/bin/daniel mentions results --brand 3690002 --job <任务编号> --page-size 20 --json

# 失败出口（TICKET-168）：两条复现命令 —— 入参类 400 → 2；品牌不存在 404 → 1；都只出一个文档
python3 .kol-tools/daniel_intel.py --brand 3690002 dashboard-creators --json --page 1 --page-size 200
python3 .kol-tools/daniel_intel.py --brand 99999999 actions --json
# 数文档个数（`json.loads` 分不出"一个文档 ＋ 尾随文本"与"两个文档"）：
python3 - <<'PY'
import json, subprocess, sys
p = subprocess.run([sys.executable, ".kol-tools/daniel_intel.py", "--brand", "99999999",
                    "actions", "--json"], capture_output=True, text=True)
dec, i, n, t = json.JSONDecoder(), 0, 0, p.stdout
while i < len(t):
    while i < len(t) and t[i] in " \t\r\n": i += 1
    if i >= len(t): break
    _o, i = dec.raw_decode(t, i); n += 1
print("exit=%s docs=%d" % (p.returncode, n))
PY
```

## 7. 适用边界：**哪些命令有 `read`**（`TICKET-168` 验收第 6 条）

**结论：读结果信封（`read`）只适用于走"读链仪器 ＋ `read_instrument()`"的那批命令，不是所有
`--json` 命令。没有 `read` **不是**缺陷。**

判据（可以机械核对，不靠记忆）：

| 判据 | `read` | 覆盖面 |
|---|---|---|
| 该子命令的实现调的是 `read_instrument(...)`（即：仪器 `--json` 出 `daniel.read.v1` 信封，由 CLI 拆成 `data` ＋ `read`） | **有** | `daniel intel actions／keywords／topics／reviews`、`daniel mentions jobs／status／results` |
| 该子命令的实现调的是 `use_instrument(...)`（仪器只打自己的 JSON 或人读文本，CLI 原样搬进 `data`／`text`） | **没有** | `brands *`、`sov *`、`authenticity *`、`takeover *`、`parity *`、`search *`、`lists *`、`ct *`、`route *` |

实测（只读，顶层键逐字）：

```bash
python3 data/daniel-cli/bin/daniel brands list --limit 2 --json            # 顶层无 read
python3 data/daniel-cli/bin/daniel sov brand-videos --brand 3690002 --json # 顶层无 read
python3 data/daniel-cli/bin/daniel intel actions --brand 3690002 --limit 2 --json   # 顶层有 read
python3 data/daniel-cli/bin/daniel mentions jobs --brand 3690002 --limit 2 --json   # 顶层有 read
```

为什么没有 `read` 不是缺陷：`read` 装的是**读链搬运口径**（条数、游标、是否被收窄），它的前提是
仪器把结果装进了 `daniel.read.v1` 信封。上面那批命令的仪器只返回业务载荷本身（或人读文本），
**没有分页搬运口径可搬**，硬塞一个空 `read` 只会让"有 `read`"这个信号失去意义。

**要判断"有没有拿到数据"，不要看 `read` 在不在**：看 `ok`、`exitCode` 与 `data`；
要判断"拿没拿全"，才看 `read.truncated`／`read.paging`，而这两条只在确实有 `read` 的命令上有意义。

## 8. 全仪器 `--json` 收口情况（`TICKET-168` 验收第 5 条）

`.kol-tools/daniel_*.py` 共 14 个文件逐个过了一遍（`--json` 指"有机器可读格式开关的仪器"）：

| 文件 | 机器可读开关 | 入口包装 | 本次 | 说明 |
|---|---|---|---|---|
| `daniel_intel.py` | `--json` | `cli()` → `daniel_io.cli` | **改** | 修掉"读失败把中文打 stdout ＋ exit 0 ＋ 0 个文档"；失败也出一个信封；`--json` 与多子命令／`--raw` 等互斥；自检加 5 项 `raw_decode` 正控 |
| `daniel_mentions.py` | `--json` | `cli()` → `daniel_io.cli` | **改** | 读链失败补 `ok=false` 信封；`call()`／`cmd_export` 不再"任何非 200 都报 2"（5xx 现在报 1）；原始报文改走 `error.hint` |
| `daniel_sov.py` | `--json` | `cli()` → `daniel_io.cli` | **改** | 去掉污染 `--json` stdout 的中文行（改 stderr）；失败补信封；无子命令 1→2 |
| `daniel_takeover_check.py` | `--json` | `cli()` → `daniel_io.cli` | **改** | 验收进度行在 `--json` 时改走 stderr（原先排在 JSON 前面）；失败补信封 |
| `daniel_authenticity.py` | `--json` | `cli()` → `daniel_io.cli` | **改** | 新增入口包装（原先用户错误带 traceback 报 1）；无子命令 0→2；`--json` 与 `--explain-weights` 互斥 |
| `daniel_ui_parity.py` | `--json`（原只在 `--selfcheck` 分支生效） | `cli()` → `daniel_io.cli` | **改** | `--probe` 分支不再无视 `--json`；"落盘：…"改走 stderr；失败补信封 |
| `daniel_paths.py` | `--json` | `cli()` → `daniel_io.cli` | **改** | 退出码分级本来就是对的，只补"失败时 stdout 一个信封" |
| `daniel_search.py` | **无任何格式开关** | 无（`main()`，被 CLI 以 `use_instrument` 拉起） | **不改** | 它根本没有 `--json`：单文档契约对它就**不适用**。失败时 stdout 为空 ＋ 退出 1（人读模式，错误在 stderr 的 traceback），符合"非 `--json` 模式 stdout 不含 JSON 信封"的判据。**遗留（不在本票范围）**：`--job-status` 拿到 `status='failed'` 的任务也算成功（`daniel_search.py:887`），且它没有机器可读出口 —— 要另开票加 `--json` |
| `daniel_brands.py` | 无（`--get` 使 stdout 变裸 JSON） | 无 | **不改** | 无 `--json`、CLI 不消费它（`brands` 模块自己实现读链）；失败一律 `print('❌…')` 到 stdout ＋ `return 1` —— 属"没有机器可读出口"的同类问题，但改它＝给它新增契约，超出本票范围（另开票） |
| `daniel_ct.py` | 无 | 无 | **不改** | 同上（`mod_ct.py` 明说无 JSON 出口） |
| `daniel_lists.py` | 无 | 无 | **不改** | 同上 |
| `daniel_credentials.py` | 无（输出恒 JSON） | 无 | **不改** | 凭据写链，不是读命令；`return 3` 与 CLI 的"需确认 3"撞语义，属另一类问题（另开票） |
| `daniel_route_probe.py` | 无 | 无 | **不改** | CLI 只 `load_capability` 取它的常量，从不以脚本调；`main()` 无 return 恒 0 —— 已知问题，另开票 |
| `daniel_client.py` | 无（纯库） | 无 | **不改** | 库模块，无 argparse、无 `--json`；失败靠 `raise` 交调用方 |

小结：**7 个"带机器可读开关的读命令"本次全部收口**（intel／mentions／sov／takeover_check／
authenticity／ui_parity／paths）；**7 个不适用不改**，理由已逐条写明（无 `--json` 开关、或非读命令、
或纯库）。上表里标"另开票"的四条是**同类但不同口径**的问题（无机器可读出口/退出码语义撞车），
本票未越界修改。
