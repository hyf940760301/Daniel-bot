# `data/daniel-cli/mcp/` —— 把 Daniel CLI 的能力接到别的宿主上（TICKET-153 Part A）

这个目录只干一件事：**让已经剥离好的 `data/daniel-cli` 能力被别的宿主（第一个是 Cursor 3.24.12）用起来**，
并且把"用起来了"证明成可机械复跑的证据，而不是一句"我试过了"。

| 文件 | 是什么 | 一句话 |
|---|---|---|
| `server.py` | 自研 MCP server（stdio） | 把 CLI 的 61 条子命令全量暴露成 MCP 工具（读链执行／沙箱引擎执行／**写链只出确认单**）；工具清单由 `daniel_cli/schema.py` 派生，**没有第二份** |
| `client_check.py` | 脚本化 MCP 客户端 | 走真实 stdio 做协议级断言：`initialize` → `tools/list` → `tools/call` → `resources/*`，含 `--self-test` |
| `compare_hosts.py` | 一致性比对器 | 两份交付物做**同字段／同排序／同条数**比对，差异为 0 才算过 |
| `check_corpus_sync.py` | 语料漂移门禁 | 包内语料 vs 源束**逐文件 sha256** 比对；差异即红（TICKET-159） |
| `exposure-register.json` | 差异显式登记表 | 「CLI 有、MCP 没有」的命令**逐条登记**（含未暴露原因／替代路径／执行语义），双向断言守门 |
| `corpus/` | **随包分发的业务语料** | 8 束 KOL 能力域（`SKILL.md` ＋ `references/*.md` ＋ `_CORPUS.json` ＋ `_MANIFEST.json`），按服务自身位置定位 |
| `_fixtures/cross-host/` | 跨宿主回归对 | Cursor 3.24.12（经 MCP）× DSH（直接 CLI）的**真实产物原件**，比对器自检每次重比一遍 |

这些脚本**只用标准库**（Python 3.9+），**不 import 任何 DSH 模块**，也不需要装任何 MCP SDK。

---

## 一、怎么跑

```bash
# 1) server 自检（派生口径、写链不注册、凭据不进子进程环境、语料 resources）
python3 data/daniel-cli/mcp/server.py --self-test

# 2) 协议级验证（含正控与退化输入；会另起 server 子进程）
python3 data/daniel-cli/mcp/client_check.py --self-test

# 3) 一致性比对器自检
python3 data/daniel-cli/mcp/compare_hosts.py --self-test

# 3.5) 语料漂移门禁（包内语料 vs 源束，逐文件 sha256；0＝绿，2＝红）
python3 data/daniel-cli/mcp/check_corpus_sync.py

# 4) 经 MCP 路径跑一份契约（默认 minimal-skeleton；真实数据契约用 --contract 指定）
python3 data/daniel-cli/mcp/client_check.py --contract real-brands-inventory --playbook \
    --out-dir /tmp/xhost-real/mcp --sandbox /tmp/xhost-real/mcp/sandbox

# 5) 跨宿主比对（两条路径各跑一次同一契约，产物必须差异 0）
python3 data/daniel-cli/mcp/compare_hosts.py --a A.json --b B.json \
    --label-a "直接 CLI" --label-b "经 MCP server"
```

> 真实数据契约（要走一次网络读）比对时**必须显式**加 `--volatile 耗时毫秒` ——
> 两侧耗时必然不同（实测 862ms 对 898ms）。比对器**不做隐式忽略**：差异只落在耗时上时它会打印
> 一条提示告诉你怎么显式声明；差异不止耗时时**不打印**那条提示。

宿主侧怎么注册，见 `docs/product/daniel-copilot/_impl/TICKET-153-Cursor宿主注册片段.md`。

---

## 二、工具清单从哪来（单一真源，不许有第二份）

`server.py` 的注册表是这么来的：

```
daniel_cli/schema.py  ──exports.mcp_tools()──▶  工具定义（name / description / inputSchema / annotations）
                                              │
                                              ├─ 过滤：见下方「暴露口径」
                                              └─ 原样装进 tools/list（inputSchema 逐字不改）
```

`client_check.py` 不 import 服务端代码，而是**另起一个进程**跑 `daniel schema --mcp --json`
拿同一份清单，两边做**名字集合与条数的键比对**。所以「CLI 加了子命令、但 server 忘了跟」这种漂移会被当场抓到。

### 暴露口径（三条，都从真源派生）

| 口径 | 判据（取自 schema 派生结果） | 执行行为 | 本期条数 |
|---|---|---|---|
| 只读 | `annotations.readOnlyHint is True` | **直接执行** | 63 |
| 沙箱只读 | `annotations.readOnly == "contract-dependent"` 且该命令 `writeStage == "sandbox"` | **执行**（写动作只落本次运行沙箱；永不转发 `--confirm`） | 1（`daniel_playbook_run`） |
| **确认单** | 其余全部写链命令（`annotations.readOnlyHint is False`） | **永不执行**：只返回一份确认单 | 18 |
| ~~不注册~~ | —— | —— | **0** |

> 🔴 **批注（TICKET-197 实测 · 不改上表历史正文）**：上表与下面两段的条数是**当时（82 条命令）**的实测值，
> 已过时 —— 现盘面实测（`daniel schema --check` ＋ 真实 `tools/list` 键比对）为：
> **固定只读 65 ／ 沙箱只读 1（`daniel_playbook_run`）／ 确认单 21 ／ 注册 88**，
> CLI 声明 **88** 条、注册 **88** 条、**差集 0**（`client_check.py --self-test` **108/108** 通过）。
> 口径本身**一个字没变**（除下条新增档位），只是命令数随能力增长（`connect`／`pack`／`sched`／`install`／`playbook deliver` 等）。

> 🔴 **批注（TICKET-202 · `Q14` · 新增第**四**档「本机出件」）**：上表的"三条"现在**是四条** ——
> `playbook deliver` **会往本机出件落点写文件**（`$DANIEL_HOME/output/<契约id>/`），但它
> **不是写链**（改成确认单形态 ⇒ MCP 侧永远出不了件）。故新增档位
> **`local-output`**：`annotations.readOnlyHint is False` ＋ `_meta.daniel.exposure == "local-output"`
> ＋ `localOutput: true` ＋ `readOnlyNote`（写明"会写本机出件落点、不写 Daniel 远端"）
> —— **可直接执行**。现盘面：**本机出件 1（`daniel_playbook_deliver`）**，因此
> **固定只读 66 → 65**、**`readOnlyHint=false` 22 → 23**；88 条总数与差集 0 不变。
> 两个载荷（协议面 `tools/list` 与自省载荷 `schema --mcp --json`）口径由
> `client_check.py` 的 `exposure_mismatches()` **逐工具比对**（不一致即红，正控＝人为把 `run`
> 的协议面改成 `confirm-ticket` ⇒ 必须报红）。
> **真源永远是 `daniel schema --check`**，任何条数都以现读为准。

CLI 自己声明 **82** 条子命令，注册 **82** 条，**差集为 0**。
（最近一次增长是 TICKET-189 的 `connect` 五条：`list`／`print`／`doctor` 三条只读按口径**自动**进来，
`apply`／`uninstall` 两条写链按同一口径**自动**成为确认单工具 —— 没有一处手写第二份名单。）
**没有第二份名单要维护**，`client_check.py` 的三方键比对会当场核对
「声明 82 ／ 派生期望 82 ／ 目录实收 82」（本期实测值；**真源永远是 `daniel schema --check`**）。）

### 写链＝确认单通道（TICKET-161）

用户 2026-10-15 裁决：**CLI＝完整能力集成的落地形态；MCP＝Daniel 数据层接入面**。
于是写链在 MCP 侧**注册但永不执行** —— 它是"确认卡片通道"：

- **能力面全量可见**：19 条写命令都在 `tools/list` 里，模型知道有这条能力、能把它排进计划；
- **调用只出确认单**：返回 `将执行的确切命令`／`动作类型`／`影响面`／`不可逆性`／`所需前置`／`替代路径`；
- **永不转发 `--confirm`**（本票唯一不能碰的底线）：传了 `confirm=true`／`delete_token` 直接
  `isError=true` 拒收，拒因写死「本模式不执行写动作…请拿确认单里的命令到 CLI…」；
- **不产生任何副作用**：影响面**只来自只读预查**（`account whoami`／`account capabilities`／
  `brands show`／`lists by-brand` …），server 为了拿影响面**也不会**去跑那条写命令；
  实现级保证：确认单分支**根本不调** `build_argv()`，且每条预查在拼 argv 前都对
  `schema` 的只读集合**断言它是只读命令**；
- **退出码语义与 CLI 对齐**：`3`＝需确认。MCP 没有退出码字段，所以它同时出现在正文第一句、
  `structuredContent.确认单.退出码语义`、`_meta.daniel.exitCode` 三处，并配
  `是否执行=false`／`executed=false`／`requiresConfirmation=true` —— **绝不被包装成成功**
  （`isError` 保持 `false`：这一票的预期产出就是确认单，标成 error 会被宿主当异常吞掉，
  确认单就到不了用户眼前；机器可读的反证在上面那四个字段里）。

**动作类型是闭合枚举**（机检，不许写成随手自由文本）：
需求稿五类（同步飞书／写 Daniel 记录／对外发信／删除类／触发采集）＋ 显式一档
`其他（本机副作用）`。**如实标注的覆盖率**：今日 19 条写命令只覆盖三类
（写 Daniel 记录／删除类／触发采集）＋ 一档其他；**「同步飞书」与「对外发信」还没有任何对应命令**
（飞书写链整体后置）—— 通道为这两类**留位**，但不假装覆盖了五类。
`account login`／`account credentials-set`／`account switch` 与 `connect apply`／`connect uninstall`
的副作用只落**本机**（会话文件／系统钥匙串／宿主配置），归入 `其他（本机副作用）`，**不属于五类**。
（`connect` 那两个直接改写宿主配置，属于同一档"本机副作用"：不碰 Daniel 数据，因此登记进
`schema.LOCAL_WRITE_MODULES` 并在 `schema --check` 的 S6 里**显式打印豁免**。）

**「印出来的命令必须真能跑」是一条判据**（不是文案要求）：印一条不存在的命令比不印更糟 ——
三级子命令最容易出事（把 `account credentials set` 拼成 `daniel account set --confirm`）。
两层断言：① server 侧断言印出的前三个 token **≡ 真源注解里的 `cli` 前缀**；
② `client_check.py` 第 2.5 组**真去问 CLI 解析器**（`daniel <模块> <子命令> --help` 必须退 0），
并配负控 `daniel account set --help` **必须退 2**（否则断言没有分辨力）。

`exposure-register.json` 逐条登记每条写命令的**执行语义**
（`命令` / `工具名` / `执行语义` / `暴露形态` / `动作类型` / `不可逆性` / `替代路径` / `说明`），
`client_check.py` 第 3 组做**双向断言 ＋ 三条新牙齿**：

| 断言 | 判什么 | 红的样子 |
|---|---|---|
| A2 **漏登记** | 差集 ⊆ 「执行语义=未注册」条目 | 差集里出现了登记表之外的条目 = 有人把能力藏了或漏注册 |
| A3 **陈旧／不实** | 「执行语义=未注册」条目 ⊆ 差集 | 登记为未注册却真的注册了（或已不存在的命令留在表里） |
| A4 **陈旧** | 登记的命令必须仍在 CLI 声明里，且「命令」↔「工具名」自洽 | 登记表成了手抄的第二份名字 |
| A5 **不实（161 新增）** | 登记为「确认单不执行」的每条必须**真注册**、`_meta.exposure == confirm-ticket`、description 写明「不会执行」 | 声称"能力面可见"其实没注册，或悄悄会执行 |
| A6 **登记不全（161 新增）** | CLI 声明的每条写命令都有登记条目 | 加了写命令却没人登记它的执行语义 |

取值越界（`执行语义` 只能是 `执行` / `确认单不执行` / `未注册`）同样＝红。
这张表**必须随产品一起更新**（它是随包分发的产品件，不是内部笔记）。

**差集归零改写了 TICKET-159 的不变量**：新的模式对等不变量＝「能力面：两模式集合完全相等（差集 0）；
差异只体现在 `执行语义`（`执行`／`确认单不执行`），且该字段双向断言」。

---

## 二之二、语料随包分发（TICKET-159）

> 🔵 **脱敏状态如实标注**：`_MANIFEST.json` 里写着 `"已脱敏": false`
> **（当前口径：内部推广阶段默认全部语料通过、不做脱敏；范围清单见 **飞书《测试与结论》第四节 TC-09 模块**）**。
> 用户 2026-10-15 裁决：产品级 CLI 目前仅内部推广，语料库不存在敏感内容、默认全部通过
> ⇒ 不做脱敏、不建零命中门禁（TICKET-164 已降级为"只出清单"）。
> 本票只证"语料能随包分发且不漂移"，与"内容是否可外发"是两件事 —— 把状态写清楚，不做静默假设；
> 门禁的**段二**按"将来对外分发时启用脱敏"预留（结构已就位，届时不用改门禁）。

用户口径：**语料必须包含在整个 MCP 里** —— 别的电脑上的 Cursor **只做一件事**（注册本 MCP server），
之后**无需任何其它安装步骤**就能拿到营销语料并据此干活。所以：

- 8 束语料（`kol-intelligence` / `kol-discovery` / `kol-screening` / `kol-outreach` /
  `kol-negotiation` / `kol-contract` / `kol-daniel-api` / `kol-execution-sov`）连同
  `SKILL.md`、`references/*.md`（逐字切片）、`_CORPUS.json` **就放在本目录的 `corpus/` 里**；
- 服务与 CLI 都按**自身位置**定位语料（`daniel_cli/corpus.py`：`<包根>/mcp/corpus`），
  **不读 `~/.agents/skills/`**、不看 cwd、不依赖 `.kol-tools/`；
- 宿主侧两条路都能拿到：**工具**（最通用，Cursor 一定能用）
  `daniel_skills_list` / `daniel_skills_read`；**resources**（宿主支持时更好用）
  `daniel-copilot://skills`、`daniel-copilot://skills/<域>`、`daniel-copilot://skills/<域>/<切片号>`。
  宿主不支持 resources 也没关系 —— 工具路径已全覆盖（两条路走的是**同一个** CLI 实现，不可能是两份数据）。

**分片是硬要求**：整束合计约 1.15 MB（单文件最大 469 KB）。所以不给 `--section` 只回**导航**（切片清单），
`--section 0` 回导航件 `SKILL.md`，`--section N` 回第 N 个切片的逐字正文，正文超 `--max-bytes`（默认 48000）
自动分片，用 `--offset` 续读；拿不准读哪一片先用 `--grep` 只回命中行。

### 语料更新四步（**改语料必须走完四步**）

```bash
# ① 改语料源（只读文件，由营销角色维护）
#    docs/marketing/skills/kol-intelligence.md

# ② 重切源束（TICKET-148 的切分器）＋ 零丢失校验
python3 docs/product/daniel-copilot/_impl/TICKET-148-语料束切分器.py
python3 docs/product/daniel-copilot/_impl/TICKET-148-语料束切分器.py --verify

# ③ **一条命令**把源束重新导出进包内并重写清单（复用同一个切分器，不另写导出器）
#    链内顺序已经是「导出 → 脱敏步骤位 → 算分发版哈希」
python3 data/daniel-cli/mcp/check_corpus_sync.py --sync

# ④ 漂移门禁（必须绿；红则不得提交）
python3 data/daniel-cli/mcp/check_corpus_sync.py
```

**为什么顺序不能颠倒**：清单里记的哈希要么是"源束原文的指纹"（段一），要么是"脱敏后分发版的指纹"（段二）。
先算哈希后脱敏，就会**记着前者却宣称后者** —— 清单与门禁同时失真，而且没人看得出来。

**脱敏步骤位**：`check_corpus_sync.py` 的 `redact_step()` 就是那个位置（在 `run_splitter()` 之后、
`write_manifest()` 之前），本期 `REDACTION_STEP = None`，即**不接线**，并在输出里明说"本期未接线"。
将来对外分发、段二启用时，把 `REDACTION_STEP` 指向脱敏工具，或直接把实现写进函数体；接线约定：
`python3 <脱敏工具> --in <源束根> --out <输出根>`，退出码 0 ＝ 输出根下产出与源束同布局的分发版语料。

### 漂移门禁是**两段式**的（脱敏落地后不用改门禁）

| 段 | 判据条件 | 比什么 | 用途 |
|---|---|---|---|
| **段一**（当前） | 清单 `"已脱敏": false` | **包内 == 源束**（逐文件 sha256，逐字） | 证明**复制无损** |
| **段二**（将来对外分发、启用脱敏之后） | 清单 `"已脱敏": true` 且 `"脱敏工具"` 已填 | **包内 == 源束经同一份脱敏工具处理后的结果**（现场重算，**不比原文**） | 证明**分发版与脱敏口径一致** |

**为什么必须两段**：脱敏之后源束与分发版**必然不相等**。门禁若写成只有"必须相等"一种形态，
164 一落地就会**假红**（而且会诱导人把门禁删掉）。切换条件严格是"两个字段同时具备"：
只写 `已脱敏: true` 却没接线 ⇒ **红**（"宣称脱敏了却没有可复核的脱敏工具"本身就是不实登记）。
`--self-test` 里为此配了正控（造一个恒等脱敏器把清单切到段二 ⇒ 绿）与退化输入（段二下包内漂移 ⇒ 红）。

**为什么必须有第 ④ 步**：语料在仓库里有**两份物理副本**（源束 `.agents/skills/kol-*/` 与包内
`mcp/corpus/kol-*/`），天然是"第二真源"的形状。如果包内副本会静默漂移，
"新机器装完就有完整语料"就会在某次语料更新后**悄悄退化成旧版**且没人发现 —— 比功能没做更糟。
门禁把漂移变成**会红的断言**：重算包内逐文件 sha256，与 `_MANIFEST.json` 记录的
「源束路径 ＋ 源束整束 sha256 ＋ 逐文件 sha256」比对，再按上表的段一口径与源束逐文件比对；
差异会打印**哪个文件、期望哪个哈希、实际哪个哈希**。源束不在本机时（分发物上的正常情形）
该项记「跳过」而不是失败 —— 否则门禁在分发物上永远红、等于没有。

`check_corpus_sync.py --self-test` 共 13 项：2 条正控（段一全绿；源束不在本机记跳过仍绿）
＋ 1 条段二接线演练正控 ＋ 9 条退化输入（包内被改一字节必须红且点名文件、源束改了包内没同步必须红、
清单逐文件哈希被篡改必须红、清单缺 `source_bundle` 必须红、清单缺 `已脱敏` 必须红、
宣称已脱敏却没接线必须红、段二下包内漂移必须红、整束目录缺失必须红、清单文件缺失必须红且不崩）
＋ `--write-manifest` 在两侧不一致时必须拒绝（不洗白漂移）。

**真跑过的输出（重生成后门禁为绿）**：

```
$ python3 data/daniel-cli/mcp/check_corpus_sync.py --sync
=== 重导出：源文件 → 包内语料（顺序：导出 → 脱敏 → 算哈希）===
· 重导出：…/TICKET-148-语料束切分器.py --out …/data/daniel-cli/mcp/corpus
  语料版本 0.9.196 ｜ 源 docs/marketing/skills/kol-intelligence.md（sha256 c5db0d0a1b25…）
· 脱敏步骤位：**本期未接线**（清单 `已脱敏=false`）——当前口径（用户 2026-10-15 裁决）：内部推广阶段默认全部语料通过、不做脱敏；范围清单见 **飞书《测试与结论》第四节 TC-09 模块**
· 已重写清单：…/mcp/corpus/_MANIFEST.json（语料版本 0.9.196 ｜ 8 束 ｜ 40 文件 ｜ 24 切片 ｜ 已脱敏=false）
=== 重导出后立刻跑一遍门禁（④ 漂移校验）===
 [通过] 包内语料逐文件 sha256 ≡ 清单记录（差一即红）  ｜ 比对 40 个文件 ｜ 不一致 0 个
 [通过] 脱敏状态已如实标注：已脱敏=false ｜ 当前口径（用户 2026-10-15 裁决）：内部推广阶段默认全部语料通过、不做脱敏；范围清单见 …**飞书《测试与结论》TC-09**
 [通过] 「期望的分发版」逐文件 sha256 ≡ 包内（段一：包内 == 源束（逐字））  ｜ 比对 40 个文件 ｜ 不一致 0 个
检查项：9 条，通过 9 条，未过 0 条，跳过 0 条
结论：绿 —— 包内语料与清单／源束一致
```

> **待挂接**：这道门禁尚未挂进 `selfcheck.sh` 汇总链（该文件本票不动，已回报总监由其排期）。
> 在那之前，改语料的人**必须手工跑第 ④ 步**。

---

## 二之三、从宿主调出件：最小示例（照抄即可产出一条真实交付物 · TICKET-197）

> 这一段是**给人照抄用的**：工具名、参数、预期产物路径三样都在这里，不用先读源码。
> 「宿主按协议调一次 ⇒ 交付物真的落在磁盘上」这件事已在协议层实测钉死
> （验收件：`docs/product/daniel-copilot/_impl/TICKET-197-MCP出件协议层-验收.md`）。

**① 工具名（以派生为准，不要猜）**：`daniel_playbook_deliver`
（来源 `daniel schema --mcp --json`；等价 CLI 命令写在该工具的 `_meta.daniel.cli` 里：
`daniel playbook deliver <契约> --json`）

**② 参数**（`inputSchema` 逐字来自单一真源，只有 4 个）：

| 参数 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `name` | **是** | string | 契约编号（如 `high-performance-video-list`）；`daniel playbook list` 看有哪些 |
| `out` | 否 | string | 交付物落点目录；**不给就落 `$DANIEL_HOME/output/<契约id>/`** |
| `limit` | 否 | string[] | 覆盖契约声明的样本上限，写「上限名=整数」 |
| `input` | 否 | string[] | 覆盖契约声明的输入，写「输入名=值」 |

**③ 宿主侧怎么调**（真实 stdio JSON-RPC，逐字可复现）：

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"我的宿主","version":"0.1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"daniel_playbook_deliver","arguments":{"name":"high-performance-video-list"}}}
```

**④ 预期产物**（默认落点，调用成功即出现在磁盘上）：

```
$DANIEL_HOME/output/high-performance-video-list/高表现视频清单.csv              ← 主表（29 列，3 行）
$DANIEL_HOME/output/high-performance-video-list/高表现视频清单-说明与口径.csv   ← 说明与口径附表
```

回包里能直接拿到指纹，**不用自己去数**：`result.structuredContent.data.出件` =
`{落点, 产物[], sha256, 行数, 格式, 自检[五条], 违规[]}`；`result.isError` 为 `false`，
`result._meta.daniel` = `{tool, module, command, exitCode, readOnly, exposure}`。
实测（本机 `high-performance-video-list`）主表 `sha256=dfa2d733bf00c938…`、`2101` 字节、`3` 行。

**⑤ 出件自检不过就不出件**：五条自检（全表闭合／计数对账／排序键单调／无空值／关键桶非0）
是出件的组成部分；任一条不过 ⇒ 非零退出、**落点上一个文件都不产出**（逐条点出违规行）。

**⑥ 没登录时**：本工具**fail-fast**，返回**结构化「未登录」错误**
（`isError=true` ＋ `structuredContent.未登录=true` ＋ `fix` 一行修法 ＋ `_meta.daniel.executed=false`），
**不静默返回空数据、也不落任何文件**。修法就是它给的那一行：`daniel account login --browser --confirm`。

> 口径边界（**TICKET-202·`Q14` 已改**：本工具现在按 **`local-output`** 派生 ——
> `annotations.readOnlyHint=false`（它**会写本机文件**，所以**不是**纯只读）＋
> `_meta.daniel.exposure="local-output"`／`localOutput=true`／`readOnlyNote` 写明事实；
> 但它**仍可直接执行**（不是确认单工具）—— 宿主照旧一次调用就出件）。
> 它**不碰任何 Daniel 数据、不触发采集、不写飞书**；唯一的副作用是把交付物写进
> **本产品自己的出件落点** `$DANIEL_HOME/output/<契约id>/`（不会写到别处）。

---

## 三、安全纪律（本目录的硬约束）

1. **凭据值绝不进任何输出**。子进程环境只透传白名单：
   `PATH` `HOME` `TMPDIR` `LANG` `LC_ALL` `LC_CTYPE` `PYTHONIOENCODING`
   `DANIEL_HOME` `DANIEL_CLI_TOOLS` `DANIEL_CONTRACTS_DIR` `DANIEL_PLAYBOOK_SANDBOX`。
   `DANIEL_PASSWORD` / `DANIEL_EMAIL` / `DANIEL_KEYCHAIN_ACCOUNT` / `DANIEL_ALLOW_PLAINTEXT`
   既不透传，还会被 `redact()` 从任何要输出的文本里替换成 `<已隐去>`。
2. **stdout 只跑协议**。日志、进度、警告一律走 stderr —— 否则宿主会把日志行当协议帧解析。
3. **不触发采集、不做飞书写**。本目录注册的工具分三类：只读（执行）、沙箱内自洽（执行）、
   **确认单（永不执行）** —— 任何一类都**不调用任何写路由**、不发起任何抓取任务、不写飞书。
   19 条写链只把「将执行的确切命令」交到人手里，由人拿到 CLI 执行。
4. **注册片段里不含任何凭据**（见 `_impl/TICKET-153-Cursor宿主注册片段.md`）。

---

## 四、比对器在比什么（三条机械判据）

1. **同字段**：同一层级对象的字段**名字集合**相同（A 独有／B 独有分别列出）；
2. **同排序**：共同字段的**键序列**相同（JSON 对象的插入顺序就是排序，键序不同即报）；
3. **同条数**：每个数组**长度**相同，逐下标递归比对元素。

在此之上再比**取值**，并且**不比字符串格式差异**。归一化只有两条规则，都**只作用在字符串取值上**
（字段名与结构一概不动），命中处数会在输出里逐条打印：

| 规则 | 把什么归一成什么 | 为什么要这条 |
|---|---|---|
| ① 运行根目录 | `<运行根>` → `<RUN_ROOT>` | 两个宿主选的落点根不同（`/tmp/x/a` 对 `/tmp/x/b`，或各自的 `$TMPDIR`）。不给 `--norm-a/--norm-b` 时从产物 `运行.沙箱目录` 自动推 |
| ② 临时沙箱名 | `daniel-playbook-<随机>` → `daniel-playbook-<SANDBOX>` | 没指定 `DANIEL_PLAYBOOK_SANDBOX` 时，两侧沙箱目录名各带一段随机后缀；只做规则①的话这段后缀会留在字符串里，**"差异 0" 永远达不成**（总监 2026-10-14 在 Cursor×DSH 真实产物上实测到的缺口） |

另外：

- 只差首尾空白的字符串算相等（计入"仅格式差异"）；
- 时间戳这类天生逐次不同的字段，必须用 `--volatile <字段名>` **显式声明**才跳过取值比对，
  跳过处数会打印 —— **不做隐式忽略**；
- `--no-sandbox-normalize` 只关规则②，`--strict` 两条都关：后者用来做负控，
  证明"差异 0"不是被归一化掩盖出来的（在同一对真实产物上会如实报出 3 条沙箱落点差异）。

差异为 0 时显式打印 `差异 0`；有差异时逐条列出**字段名／位置与行号／两侧取值**。

**可信度证据（负控，必须一起看）**：2026-10-14 在真实两宿主（Cursor 3.24.12 经 MCP × DSH 直接 CLI）
各跑一次 `minimal-skeleton`，默认口径结论是 **差异 0**；**同一对产物加 `--strict`（关掉全部归一化）
会如实报出 3 处差异**，全部是契约引擎自建临时沙箱的随机目录名：

```
[01] 取值不同 ｜ 字段：运行.沙箱目录      ｜ 行号：A=15  B=15
[02] 取值不同 ｜ 字段：前置.明细[0].明细  ｜ 行号：A=43  B=43
[03] 取值不同 ｜ 字段：交付件.路径        ｜ 行号：A=164 B=164
总差异：差异 3 条（结构层 0 条 ＋ 取值层 3 条）        # 退出码 2
```

即：**"差异 0"不是靠忽略字段掩盖出来的** —— 结构层在任何口径下都是 0，取值层那 3 处是运行落点，
由规则②归一化。这条负控（以及"改字段值／删字段／调换字段顺序必须报出"）已写进 `--self-test`，
每次改动后自动重验；演示时**不要只看默认口径**，一定要把 `--strict` 的对照一起贴出来。

**回归对**：`_fixtures/cross-host/` 存着 2026-10-14 在 **Cursor 3.24.12（经 MCP）** 与 **DSH（直接 CLI）**
各跑一次 `minimal-skeleton` 的原件（含 sha256 与来源说明）。`compare_hosts.py --self-test` 每次都会把
这一对重新比一遍（正控：差异 0），并配多条真阴性（改字段值／删字段／调换字段顺序必须报出；
关掉规则② 必须报出那 3 处）—— 见 `_fixtures/cross-host/README.md`。

---

## 五、这层不做什么

- 不重新实现任何业务逻辑：每次 `tools/call` 就是一次真实子进程调用
  `<python> data/daniel-cli/bin/daniel <模块> <子命令> --json …`；
  **语料也一样** —— `daniel_skills_list` / `daniel_skills_read` 与 resources 都落成同一句
  `daniel skills …`，服务端不自己读语料文件，因此 MCP 侧与 CLI 侧不可能是两份数据；
- 不改 `daniel_cli/` 里的任何既有语义（schema／exports 只新增 `skills` 模块，既有命令一个字没动）；
- **server 自己**不写任何宿主配置（`~/.cursor/mcp.json`／`~/.codex/config.toml` 都在工作区外）；
  把它们写对这件事由 **CLI 侧**的 `daniel connect` 负责（TICKET-189：自己算路径 ＋ 幂等合并 ＋
  写前快照 ＋ 写后回读对账），而且它的写链在 MCP 侧同样只出确认单、永不执行；
- **不做 DSH 侧工具注册**（`schema dsh-tools` 只打印草稿）；
- **写链不在宿主里执行**：19 条写命令里有 18 条以确认单形态注册（`playbook run` 是沙箱自洽形态），调用只返回确认单（TICKET-161）。

---

## 六、模式对比：MCP vs CLI（TICKET-159 §需对比）

用户裁决（2026-10-15）：**能力集成走 CLI，MCP 只做 Daniel 能力模块的调度入口，不作为产品级**。
两形态**不是二选一，也不必各做一份实现** —— 它们共用同一份单一真源（`daniel_cli/schema.py` ＋
`daniel_cli/corpus.py`），差异只在**投递面**。完整对比（适用场景／能力边界／是否必须双份 ＋ 实测证据）
见 `docs/product/daniel-copilot/_impl/TICKET-159-MCP与CLI模式对比.md`。

一句话结论：**MCP 是"宿主里的调度口"（零安装、只读、无 TTY、能力偏窄），CLI 是"真正的产品形态"
（可管道、可脚本、可写链、可离线排障）；语料与技能两侧必须完全相等，而命令侧差异必须显式登记。**
