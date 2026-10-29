# Daniel CLI（`data/daniel-cli/`）

> TICKET-145（P0-2）交付物：把 Daniel 的 **17 个模块**收口成一套 **host 无关、零 DSH 依赖**的命令行，
> 并提供一份**单一真源**的命令清单，用来派生 `--help`、MCP 工具清单与 DSH `defineTool` 草稿。
> TICKET-146（P0-3）在其上加了 **`playbook`（工序契约）**模块：把一条工序写成声明式契约，
> 让判据与门禁变成**可执行断言**（见 `PLAYBOOK.md`）。

## 0. 两种承载模式的定位（用户 2026-10-15 裁决 · 一句话）

| 模式 | 形态 | 读链 | 写链 | 能力面 |
|---|---|---|---|---|
| **CLI** | **完整能力集成的落地形态** | 直接执行 | 人工确认（`--confirm`）后**真执行** | 89 条命令 |
| **MCP** | **Daniel 数据层接入面**（能力模块调度） | 直接执行 | **只出确认单、永不执行**（确认卡片通道） | 89 条工具，**完全一样** |

一句话：**CLI＝完整能力落地；MCP＝Daniel 接入面** —— 两种模式的能力面**完全相同**（同一份
`daniel_cli/schema.py` 派生，差集为 0），差别只在「**谁执行写动作**」：CLI 由人加 `--confirm` 执行，
MCP 只把一条**含 `--confirm` 的命令**交到人手里（`daniel_brands_create` 这类工具**永远不会执行**）。
写链的暴露口径逐条登记在 `mcp/exposure-register.json`，双向断言守门。

## 1. 快速上手

### 1.0 🔴 授权是起点（TICKET-194 · **装完先做这一件事**）

**未登录时业务模块一律不放行**：任何要读／写 Daniel 数据的命令都会 fail-fast ——
**退出码 2 ＋「请先登录」＋ 一行修法**，**零真实数据、不静默降级**。MCP 侧同样（结构化「未登录」，不是空数据）。

**登录的唯一正路（人用）：账号密码只在 Daniel 自己的页面上输，CLI 绝不追问**

```bash
# ① 打开 Daniel 登录页并给出回读步骤（账号密码在页面上输）
python3 data/daniel-cli/bin/daniel account login --browser --confirm
# ② 在浏览器里完成登录：https://daniel-agent.com/auth
# ③ 把浏览器里的会话粘回命令行 —— CLI **先校验、通过后才落盘**
#    DevTools → Application → Storage → Cookies → https://daniel-agent.com
#    → 双击 app_session_id 的 Value 整格 → 复制 → 粘回终端
#    （这条 cookie 带 HttpOnly：在 Console 里敲 document.cookie 取不到它）
# ④ 确认三态
python3 data/daniel-cli/bin/daniel auth status
```

**`daniel auth status` 的退出码三档**（可脚本判定，`--json` 给 `{authenticated, reason}`）：

| 退出码 | `reason` | 含义 | 下一步 |
|---|---|---|---|
| **0** | 通过 | 本地会话有效 ＋ 服务端确认了这个账号 | 正常用 |
| **1** | 去登录 | 无 token，或 token 被服务端拒 | `daniel account login --browser --confirm` |
| **2** | 稍后重试 | 服务端不可达（网络／5xx） | **过一会儿重试**（本地会话没失效，**不要**重新登录） |

**未登录时仍然可用的命令（接入／自救／随包自检三类，其余全部 fail-fast）**：

| 类别 | 命令 |
|---|---|
| 帮助与版本 | `--help`、`--version`、`<模块> <子命令> --help` |
| 自救 | `account login`、`auth status`、`account credentials`、`account credentials-set`、`account whoami`、`account paths`、`account list`、`account switch` |
| 接入 | `connect --list／--print／--apply／--uninstall／--doctor`、`pack --out／--check`、**`install`（安装向导：`run`／`--check`／`--upgrade`）** |
| 随包自检 | `schema --show／--mcp／--dsh-tools／--check`、`skills list／read`、`intake route／draft／parity／catalog`、`playbook list／show／validate／selfcheck`、`parity selfcheck`、`keywords check`、`route catalog` |

> 判据的**单一真源**是 `daniel_cli/authgate.py::WHITELIST`（每条都带"为什么它是自救命令"）；
> `daniel --help` 末尾印的就是从它派生出来的清单，`daniel schema --json` 可拿到机器可读版本。
> **两档，无第三态**：一条命令要么在白名单里（未登录可用），要么受门禁（未登录 fail-fast）。

**与"一键跳转授权"的差距（如实说）**：现在是「跳转登录页 → 在 Daniel 完成登录 →
从浏览器**把会话粘回 CLI**」，多一步人工动作。原因在平台侧：登录页 `/auth` 不接受
`redirect`／`callback`／`code`；`auth.*` 里没有 device-code／poll 端点；Google 登录的
`redirect_uri` 由服务端写死在自己域名 —— **授权码回不到命令行**。平台需求已登记在 `TICKET-194`。

**无头／CI 的备用路**（🔴 **不是给人用的主路径**）：环境变量 `DANIEL_EMAIL`／`DANIEL_PASSWORD`
＋ `account login --confirm`（见 1.1）。

### 1.1 新机器三步（**无头／CI 的备用路** —— 有浏览器请走 1.0 的浏览器授权路）

在一台**没有凭据的新机器**上：先把凭据交给本机钥匙串，再登录，再用一条只读命令确认能取到数。

```bash
# 第一步：把凭据写进本机系统钥匙串（写操作，必须带 --confirm；任何输出都不回显密码）
#   ① 推荐：邮箱与密码都从环境变量读，密码不进命令行历史
export DANIEL_EMAIL="你的账号邮箱"        # 只在本机终端里设，别写进任何文件
export DANIEL_PASSWORD="你的账号密码"
python3 data/daniel-cli/bin/daniel account credentials set --from-env --confirm
#   ② 也可以显式给：--email <邮箱> --password <密码>
#   两种写法完全等价：account credentials set … ／ account credentials-set …

# 第二步：登录并落地会话（写操作；登录后回读账号，拿不到真实账号即判失败）
python3 data/daniel-cli/bin/daniel account login --confirm

# 第三步：只读取数验证（能取到数，就说明这一台装好了）
python3 data/daniel-cli/bin/daniel account whoami
python3 data/daniel-cli/bin/daniel brands list --limit 5
```

> 🔴 **这条路要密码落进环境变量／钥匙串**，所以它只是**无人值守场景**的备用路。
> 人在自己电脑上，请走 1.0。

三条纪律（与 `--help` 同源）：

- **写凭据只写本机系统钥匙串**：钥匙串写失败会**非零退出并给出指引**，**不会**退而写明文凭据文件；
  确实需要明文降级时，由你**显式**设置 `DANIEL_ALLOW_PLAINTEXT=1` 并自行用凭据工具写入
  （那一步的风险由这次显式选择承担，本命令不代做）。
- **任何输出都不回显密码**：结果里只给掩码邮箱；密码参数在进"执行计划"之前就被抹掉，
  因此既不会进 `--json` 输出，也不会进审计记录。
- **没有凭据时登录按用户错误报**（退出码 2），并明确指向 `account credentials set` 或 1.0 的浏览器路。

### 1.1.1 旧位置的凭据／会话**默认不再被读取**（TICKET-194 · C）

旧版把一份明文凭据／会话／品牌缓存**写在代码目录里**，读取时"新位置没有就回退到旧位置" ——
于是 `DANIEL_HOME` 形同虚设（实测：干净临时 `DANIEL_HOME` 下 `brands list` 照样返回 200 条真实品牌）。
现在：

- 任何旧位置**只有当它落在生效的 `DANIEL_HOME` 之内**时才允许读，在之外**一律拒读**；
- **明文凭据**的旧位置再叠一道**显式开关** `DANIEL_ALLOW_LEGACY_CRED=1`（**默认关**，读到会打警告）；
- 被拒的旧位置**如实报出**（不静默）：`daniel account paths --json` 的 `legacy_gate` 里逐条给出
  「旧位置 / 是否允许读 / 为什么 / 原因码」，`account credentials` 的 `legacy_plaintext_file`
  给出 `allowed`／`reasonCode`／`declaredPath`。

```bash
# 看旧位置到底能不能读、为什么（人话版）
python3 data/daniel-cli/bin/daniel account paths
python3 data/daniel-cli/bin/daniel account paths --json   # legacy_gate 段逐条给判定
```

→ 结论：**把项目目录交出去，不再等于把管理员凭据交出去**。

### 1.2 其余常用命令

```bash
cd <仓库根>

# 总帮助（含退出码语义）
python3 data/daniel-cli/bin/daniel --help

# 一条只读命令
python3 data/daniel-cli/bin/daniel brands list --json
python3 data/daniel-cli/bin/daniel mentions jobs --brand 3690002 --limit 5
python3 data/daniel-cli/bin/daniel authenticity channel --channel @Mrwhosetheboss

# 单一真源：全部子命令与参数的机器可读清单
python3 data/daniel-cli/bin/daniel schema --json

# 工序契约：列出 / 校验 / 跑一份 / 引擎自证
python3 data/daniel-cli/bin/daniel playbook list
python3 data/daniel-cli/bin/daniel playbook validate
python3 data/daniel-cli/bin/daniel playbook run engine-smoke --json
python3 data/daniel-cli/bin/daniel playbook run engine-write-demo --confirm --keep  # 保留沙箱
python3 data/daniel-cli/bin/daniel playbook selfcheck

# 自检（12 模块只读冒烟 ＋ 退出码语义 ＋ JSON 可解析 ＋ 零 DSH 依赖 ＋ 凭据来源矩阵
#       ＋ 契约引擎 ＋ 权限与门禁 ＋ 模块自带自检）
python3 data/daniel-cli/bin/daniel --self-test

# 交付物工厂（TICKET-175）：跑一份**模板式**契约并出件；落点默认 $DANIEL_HOME/output/<契约id>/
python3 data/daniel-cli/bin/daniel playbook deliver high-performance-video-list
python3 data/daniel-cli/bin/daniel playbook deliver high-performance-video-list --out /tmp/交付物 --json
# 出件自检正控：故意注入一条缺列记录 → 必须 FAIL 并点出行号，且落点上不产出文件
python3 data/daniel-cli/bin/daniel playbook run high-performance-video-list-degraded
# 真实数据只读示例（4 次只读调用，不触发采集、不做任何写；无网时记「跳过（需要联网）」）
python3 data/daniel-cli/bin/daniel playbook run high-performance-video-list-live

# 多账号（A2）：看当前账号与本机已存账号／切到某个账号／回到原来的位置
python3 data/daniel-cli/bin/daniel account list
python3 data/daniel-cli/bin/daniel account switch <另一个账号的邮箱> --confirm
python3 data/daniel-cli/bin/daniel account switch --clear --confirm
#   切换后：会话／缓存／产出（output）／调度（sched）都落该账号的分区
#   （<数据落点根>/accounts/<账号分区>），两个账号互不可见；凭据按账号分条存在钥匙串里，
#   切回不用重输密码。分区规则只有一处实现，`daniel account paths` 会回读当前分区。

# 印刷级 PDF 出件（A4）：出件格式的一种，复用既有出件工序（.kol-tools/doc_to_pdf.py）
python3 data/daniel-cli/bin/daniel playbook deliver script-review
#   同时落 PDF（签署／归档件）与 .md（可复制版），并多跑一条「PDF 保真」自检：
#   A4 页面／叠字 0／md↔PDF 去空白字符逐类相等 ＋ 逐行点名

# 看这个账号能读什么、能写什么（能力矩阵）
python3 data/daniel-cli/bin/daniel account capabilities

# 看凭据从哪来（只读，只回掩码邮箱）／看写操作审计（每次写一条记录）
python3 data/daniel-cli/bin/daniel account credentials
python3 data/daniel-cli/bin/daniel account audit

# 仓库自检链（schema → 只读冒烟 → 分发物断言 → 契约引擎 → 汇总）
bash data/daniel-cli/selfcheck.sh
```

### 1.3 怎么调用（先看清这一点）

`daniel` **默认不在 PATH 上**（本机实测：直接敲 `daniel` 会报 command not found）。两种调用方式
完全等价，任选一种：

```bash
# ① 从仓库根用相对路径调（最稳，本文档里所有示例都用这种写法）
python3 data/daniel-cli/bin/daniel <模块> <子命令> [参数]

# ② 已设可执行位，直接跑这个文件也可以（shebang 是 #!/usr/bin/env python3）
./data/daniel-cli/bin/daniel <模块> <子命令> [参数]

# ③ 想直接用 `daniel` 这个名字：自己做一条软链（装到 PATH 上通常是软链，bin/daniel 用
#    realpath 定位包根，软链下照常可用）
ln -s "$PWD/data/daniel-cli/bin/daniel" /usr/local/bin/daniel   # 或 ~/bin/daniel
daniel <模块> <子命令> [参数]
```

## 2. 输出与退出码契约

| 项 | 约定 |
|---|---|
| 结果 | 只走 **stdout**；`--json` 时 stdout 有且只有**一个** JSON 文档 |
| 进度/提示/警告 | 只走 **stderr**（`--json` 时也如此，方便管道消费） |
| 交互 | 默认**非交互**：不读 TTY、不弹提问；缺参直接报错退出 |
| 退出码 | `0` 成功｜`1` 内部错误｜`2` 用户错误｜`3` 需要确认（写操作未加 `--confirm`） |
| 退出码的两个**局部口径**（不是第二套，但含义要说清） | ① **未登录门禁（TICKET-194）**：业务模块命令未登录时退 **2**（＝"这是你要先解决的用户侧问题"），`--json` 里 `error.kind = "unauthenticated"`；② **`auth status` 三档**：`0` 通过／`1` 去登录（无 token 或 token 被拒）／**`2` 服务端不可达 ⇒ 稍后重试**（这里的 2 不是"你参数写错了"）。两者都写进了各自命令的 `--help`。 |
| 写操作 | 写链由**账号的使用权限**决定（不是审批）：账号对那个模块有写权限才放行，没有权限 → 退出码 2 ＋ 一行理由（说明是系统角色／账号状态／工作区权益／配额哪一轴不满足，用 `daniel account capabilities` 看完整矩阵） |
| 写操作的确认 | 默认**干跑**：未加 `--confirm` → 退出码 3 且**不执行任何写**（只打印将要做什么＋影响范围）；加 `--confirm` 才真的执行，执行后**回读校验**并留一条**审计记录**（`daniel account audit`） |
| 写操作的留痕（TICKET-196 · 收口） | **每一次尝试都留恰一条**审计，不只是成功那一次：成功／回读不过／被拒（权限轴不满足／缺 `--delete-token`／删除凭据写错／计划轴拒绝）／干跑**各一条**；执行函数**抛异常也留一条**（`executed=true` 的语义逐字是「**尝试执行但抛异常**」，异常只记**类型 ＋ 脱敏后的消息**，凭据／会话值不落盘）。失败记录都带可判定的 `failureKind`（`permission`／`delete-token-missing`／`delete-token-mismatch`／`stage-not-live`／`plan-rejected`／`readback`／`exception`／`unsettled`），对账式恒成立：**总条数 == 成功 ＋ 失败 ＋ 拒绝／干跑**。只读命令**不留**审计（正确）。 |
| 删除类写操作 | 在 `--confirm` 之外**必须再确认一次**：`--delete-token <目标名>`（把目标名原样再写一遍；写错即拒、退出码 2、**零删除**） |
| 写命令的开放级别 | `live`（**真实执行已接通**：品牌／名单两组 ＋ 凭据写入与登录 ＋ 多账号切换 ＋ **触发类四条**——检索 `search submit`／提及 `mentions run`／曝光 `sov run-exposure`／通路体检 `route sweep`（TICKET-188 · A1 接通）＋ 合作活动 `ct create-campaign`／`ct delete-campaign` ＋ 接管验收 `takeover check-writes`）｜`sandbox`（写动作只落沙箱：`playbook run` 的离线假动作）。**当前没有 `gated` 写命令** |
| 例外 | `playbook run` 按"写操作"登记（**契约可能含写步骤**），但它不执行任何 Daniel 写：纯读链契约直接跑即退出码 0；只有契约里声明了写步骤时才需要 `--confirm`，且写类动作只写本地沙箱文件；写步骤的判据是**账号对该模块有没有写权限** |

`--json` 的外层信封（所有命令一致）：

```json
{
  "ok": true, "cli": "daniel", "version": "0.1.0",
  "module": "mentions", "command": "jobs", "readOnly": true,
  "exitCode": 0, "elapsedMs": 2410,
  "data": { "...结构化结果..." },
  "notes": ["可选：截断/告警说明"],
  "route": "可选：内部通路名（**只在 JSON 里**，不进 --help）"
}
```

取不到结构化结果时用 `text` 字段承载仪器原文（此时 `data` 不出现）。

## 3. 模块与命令（粗粒度收口，不做 219 个脚本的镜像）

| 模块 | 业务标题 | 子命令 |
|---|---|---|
| `brands` | 品牌档案 | `list` `show` `competitors` ＋ `create` `update` `delete`（写） |
| `lists` | 红人名单 | `by-brand` `items` `saved-channel-ids` `share-status` `auto-priority-status` ＋ `create` `rename` `delete`（写） |
| `search` | 红人检索 | `history` `job-status` ＋ `submit`（写） |
| `mentions` | 品牌提及 | `jobs` `status` `results` ＋ `run`（写） |
| `intel` | 内容情报 | `actions` `keywords` `topics` `reviews` |
| `sov` | 声量份额 | `overview` `categories` `brand-videos` ＋ `run-exposure`（写） |
| `ct` | 合作追踪 | `campaigns` `campaign-stats` `deals` `videos` `resolve-channel` `interests` ＋ `create-campaign` `delete-campaign`（写；后者是前者的逆操作，删除类需 `--delete-token`） |
| `authenticity` | 真实性核验 | `channel` `weights` |
| `route` | 数据通路体检 | `probe` `catalog` ＋ `sweep`（写） |
| `takeover` | 接管验收 | `check` ＋ `check-writes`（写） |
| `parity` | 口径一致性 | `selfcheck` `compare` |
| `account` | 账号与盘点 | `whoami` `workspaces` `capabilities`（能力矩阵）`audit`（写审计）`credentials`（看来源）`paths`（含当前账号的数据分区）`list`（看当前账号＋列已存账号） ＋ **`credentials-set`（写：把凭据写进本机钥匙串，等价写法 `account credentials set`）** `login`（写：**浏览器授权登录**（主路径）或凭据登录（无头／CI 备用路）；登录后落地会话） `switch`（写：切换当前账号，数据按账号分区；`--clear` 回到根落点） |
| `auth` | 授权（TICKET-194） | `status`（只读：登录状态三态 —— 本地会话 ＋ 一次服务端校验；退出码 **0** 通过／**1** 去登录／**2** 服务端不可达；`--json` 给 `{authenticated, reason}`） |
| `playbook` | 工序契约 | `list` `show` `validate` `deliver`（出件，格式含 CSV／XLSX／MD／JSON／**PDF**）`selfcheck` ＋ `run`（契约含写步骤时才需 `--confirm`） |
| `keywords` | 检索词清单 | `check` |
| `skills` | 业务语料 | `list` `read` |
| `intake` | 需求入口 | `route` `draft` `parity` `catalog` |
| `sched` | 调度层 | `run` `retry` `status` `queue` |
| `connect` | 接入（TICKET-189） | `list` `print` `doctor`（只读） ＋ **`apply` `uninstall`（写：把本产品接入宿主／从宿主卸载；自己算路径 ＋ 幂等合并 ＋ 写前快照 ＋ 写后回读对账；不支持 `--host` 之外第二份逻辑**） |
| `pack` | 出包（TICKET-193） | `check`（只读：对一份包跑五条断言自检） ＋ **`out`（写：出一条可交付的能力包；干跑默认、包目录必须为空且在工作区之外）** |
| `install` | **安装向导（TICKET-195）** | `check`（只读装完自检：入口／能力束／接入 doctor／登录态） ＋ **`run`（写：一条命令做完四步 —— 装 CLI ＋ 装能力束 ＋ 写宿主接入（复用 `connect`）＋ 起登录）** **`upgrade`（写：就地改指另一份包 ＋ 自动重跑 `--check`）**；`--check`／`--upgrade` 两个快捷开关与子命令等价 |
| `schema` | 命令清单（元模块） | `show` `mcp` `dsh-tools` `check` |

共 **89 条子命令**：读 66 条、写 22 条、沙箱写 1 条（P0-2 交付时为 12 个模块／54 条；后续 `skills`／`intake`／新机器凭据／出件命令／多账号切换／A3 未实测路由补齐／A1 触发链路接通／**`connect` 接入**／**`pack` 出包**／**`install` 安装向导**等票增至 **22／88**，真源见 `daniel schema --check`）（其中 `live`＝真实执行已接通 **21 条**：品牌与名单两组、凭据写入与登录、多账号切换、**触发类四条**（检索／提及／曝光／通路体检）、合作活动建与删、含写链的接管验收、**`connect apply`／`connect uninstall`（写本机宿主配置）**、**`pack out`（写本机交付目录）**、**`install run`／`install upgrade`（写本机安装落点）**、**`brands clone`（参考品牌克隆）**；`gated`＝**0 条**（TICKET-188 · A1 之后已无「只到干跑」的写命令）；`sandbox`＝只写沙箱 1 条：`playbook run`）。每条命令的 `--help` 都带返回内容与示例。

## 4. 单一真源与三样派生物

`daniel_cli/schema.py` 是**唯一**的命令清单来源，它派生三样东西：

```bash
daniel schema --json          # ① 机器可读清单（模块/命令/参数/类型/必填/是否写/退出码/示例）
                              #    ② CLI 的 --help 文本（由 argparse 从同一份 schema 构建，不手写第二份）
daniel schema --mcp --json    # ③ MCP tool list：{"name","description","inputSchema"}
daniel schema dsh-tools --json# ④ DSH defineTool 草稿：{"name","description","parameters"}
daniel schema --check         # 自证：CLI 实际注册集合 ≡ 清单声明集合 ≡ 实现注册表（10 项）
```

TICKET-146 新增的 `playbook` 模块也登记在这份真源里，所以 `--help`／MCP 工具清单／DSH `defineTool`
草稿三份派生**自动**包含它 —— 没有任何手写的第二份清单。

`--check` 的 10 项判据（`daniel_cli/checks.py`）：

| 编号 | 判据 |
|---|---|
| S1 | CLI（argparse）实际注册的子命令集合 ≡ schema 声明的集合 |
| S2 | 每条声明的子命令都有实现（命令注册表齐备，防"声明了没实现"） |
| S3 | 12 个业务模块齐备（外加元模块 `schema`） |
| S4 | 每条命令的参数集合与清单一致（派生出的工具定义才可信） |
| S5 | 每条命令都有摘要、返回说明与示例 |
| S6 | 写命令三道闸齐备（权限判据＋确认开关＋删除类 token 开关），读操作不带这些开关；非业务模块的写级别只能是 `sandbox`（**唯一例外**＝`schema.LOCAL_WRITE_MODULES`，显式打印） |
| S7 | 每条写命令的**实现**真的装了写门禁（读注册表里那个函数对象的门禁标记，防「声明了没装」） |
| S8 | 派生出的 MCP／DSH 工具定义自洽（名字唯一、必填项都在属性里、条数与声明一致） |
| S9 | 清单里的示例命令都能被本 CLI 解析（示例不骗人） |
| S10 | 权限矩阵覆盖 12 个业务模块，且管理角色全开、降级角色被拒并给出理由 |

## 5. 目录结构

```
data/daniel-cli/
├── bin/daniel                     # 入口（可执行；只用标准库）
├── daniel_cli/
│   ├── schema.py                  # ★ 单一真源（模块/命令/参数/退出码/示例）
│   ├── exits.py                   # 退出码常量（唯一定义处）
│   ├── helpgen.py                 # 派生器①：schema → argparse → --help
│   ├── exports.py                 # 派生器②③：schema → MCP / DSH 工具定义
│   ├── checks.py                  # 一致性自证（schema --check 用它）
│   ├── runtime.py                 # 能力目录定位、输出通道、子进程复用、JSON 提取
│   ├── cli.py                     # 入口与分发（退出码收口 ＋ **授权硬门禁的唯一前置检查**）
│   ├── authgate.py                # ★ 授权门禁与自救白名单（TICKET-194）：WHITELIST 单一真源、
│   │                              #   `auth status` 的三态判定、未登录的错误结构与修法
│   ├── selftest.py                # daniel --self-test（A/E/R/J/Z/C ＋ P 六组）
│   ├── playbook/                  # ★ 工序契约引擎（TICKET-146；零 DSH 依赖）
│   │   ├── model.py               #   契约字段口径（八项字段＋限额＋期望）
│   │   ├── loader.py              #   契约目录定位与加载（DANIEL_CONTRACTS_DIR 可覆盖）
│   │   ├── validate.py            #   校验：D3「只能引用 schema 已声明的命令与参数」
│   │   ├── assertions.py          #   断言词汇表与取值引用解析
│   │   ├── actions.py             #   离线假动作（只写本地沙箱，不碰 Daniel 写路由）
│   │   ├── gates.py               #   五道门禁：样本上限/写权限/只读默认/写步骤确认/回读校验
│   │   ├── executor.py            #   执行器：跑契约、出交付件、出报告、定退出码
│   │   └── selfcheck.py           #   引擎自证：逐契约核对「期望 vs 实际」
│   ├── pack/                      # ★ 出包与包自检（TICKET-193）
│   │   ├── spec.py                #   源清单规则真源（必须包含 5 条／必须排除 26 条／点名排除 22 条，各带理由）
│   │   ├── builder.py             #   出包：按 spec 复算候选面 → 复制 → 落出包清单（在包目录**之外**）
│   │   ├── scanner.py             #   干净度：凭据（复用既有断言器）／本机绝对路径／legacy 点名／.py 写死路径
│   │   ├── isolation.py           #   隔离复现：临时 HOME ＋ 哨兵钥匙串服务 ＋ 包副本在源目录之外
│   │   └── verify.py              #   `--check` 的五条断言编排（A1 结构／A2 引用闭合／A3 干净／A4 差集／A5 隔离）
│   ├── install/                   # ★ **安装向导**（TICKET-195）
│   │   ├── source.py              #   「**包从哪来**」的单一抽象点（现在本地／将来 npm 只换这里）
│   │   └── wizard.py              #   四步判据与执行：① 装 CLI ② 装能力束 ③ 写接入（复用 connect）④ 起登录
│   │                              #   ＋ `--check` 自检 ＋ `--upgrade` 就地升级；写前落快照、写后回读对账
│   └── commands/                  # 22 个模块的实现（12 个业务模块 ＋ auth／account／keywords／skills／intake／playbook／sched／connect／pack／**install**／schema）
│       ├── _common.py             # 品牌解析复用、写骨架、凭据/落点盘点
│       ├── mod_<模块>.py          # 每个模块一份，显式 HANDLERS / WRITE_HANDLERS
├── contracts/                     # ★ 契约真源（随 CLI 分发；DANIEL_CONTRACTS_DIR 可覆盖）
│   └── _examples/                 #   示例契约 ＋ 退化样本（证明门禁真会拦）
├── PLAYBOOK.md                    # 契约格式与写法（面向人：怎么写一份契约）
├── selfcheck.sh                   # 仓库自检链（5 步）
├── PACKAGING-EXCLUDE.md           # 分发构建必须排除的路径 ＋ 构建后断言
└── README.md                      # 本文件
```

## 6. 能力层定位（不重写业务逻辑）

CLI 本身**不含**任何业务判据，取数一律复用既有能力：

- **共享客户端**：`.kol-tools/daniel_client.py`（41 个脚本都在用；含鉴权、跨工作区品牌解析）；
- **落点与凭据**：`.kol-tools/daniel_paths.py`、`.kol-tools/daniel_credentials.py`；
- **模块仪器**：`.kol-tools/daniel_<模块>.py`（通过 `subprocess` 调它们的**只读**开关）。

能力目录按"从本包位置逐级向上找 `.kol-tools`"定位，也可用 `DANIEL_CLI_TOOLS` 显式指定
（剥离到别的宿主后不用改代码）。端点用 `DANIEL_BASE_URL` 覆盖，落点用 `DANIEL_HOME` 覆盖。

## 6.1 出包（`daniel pack`，TICKET-193）

`daniel pack --out <目录> --confirm` 出一条**可交付的能力包**（包根 `<目录>/daniel-bot`：
`data/daniel-cli/**` ＋ `.kol-tools/` 里那 16 个运行时依赖 ＋ `_daniel_jsref/`），
`daniel pack --check <包目录>` 对一份包跑五条断言（结构／引用闭合／干净／差集对账／隔离复现）。

**源清单规则的真源是 `daniel_cli/pack/spec.py`**（必须包含 5 条／必须排除 26 条／
点名排除 22 条，每条都是「路径模式 ＋ 理由」）；候选面、包含集与排除集全部由规则**算出来**，
每一份包的逐项排除清单落在**包目录之外**的 `<目录>/_PACK_MANIFEST.json`（收据）。

与 TICKET-147 时代那份 `PACKAGING-EXCLUDE.md` 的关系（**复用与替换，逐条说清**）：

| 维度 | 旧口径（`PACKAGING-EXCLUDE.md`，TICKET-145/147） | 本票（`daniel pack`） |
|---|---|---|
| 形态 | 一份**给人看的清单**（3 张表：必须排除／噪声项／可以进） | **可执行的规则表**（`spec.py`）＋ **逐项可复算的排除账**（收据） |
| 凭据扫描 | `check_no_secrets_in_dist.py <打包目录>` **要人记得手工跑** | **复用同一个断言器**（`scanner.credentials()` 直接调它），并把"退出码必须为 0"写成断言 |
| 覆盖范围 | 凭据、噪声目录、体积 | 凭据 ＋ **本机绝对路径**（旧口径不含）＋ **legacy 凭据／会话／索引三类点名** ＋ legacy 点名的"不许偷偷回退"反控 |
| 差集 | 无（靠人比对） | `包内 ⊆ 源` 且 `源 − 包 == 排除清单`，**逐项**相等才算过 |
| 复现 | 无 | `daniel pack --check`（默认就是隔离跑一遍：临时 HOME ＋ 哨兵钥匙串服务 ＋ 包副本在源目录之外） |

`PACKAGING-EXCLUDE.md` **保留**（它记录了"为什么这些路径不能进分发物"的推导与那份断言器的
使用说明），但**出包这件事不再依赖人去读它**：规则搬进了 `spec.py`，账目由 `pack` 自己算。

**两条已知边界**（如实登记，不假装覆盖）：① 包内**不含** `.kol-tools/` 里其余 141 个一票一用的
业务仪器与检查器（CLI 运行期只按名字加载白名单里那几个模块）；② `compare_hosts.py` 的正控回归对
（`mcp/_fixtures/cross-host/*.json`）**含本机绝对路径**，按"干净优先"被排除 ⇒ 包内那条
`--self-test` 缺少正控夹具。两条都写在 `pack/spec.py` 的规则理由里。

## 6.2 安装向导（`daniel install`，TICKET-195）

**一条命令做完四件事**（对齐飞书项目 CLI 的安装与接入形态）：

```bash
daniel install --confirm        # ① 装 CLI ② 装能力束 ③ 写宿主接入（复用 connect）④ 起登录
daniel install                  # 不带 --confirm ＝ 干跑：只打印四步计划（退出码 3，零写入）
daniel install --check          # 装完自检：入口／能力束／接入 doctor／登录态 ⇒ 全绿退 0，否则一行修法
daniel install --upgrade --from <包目录> --confirm   # 就地改指另一份包 ＋ 自动重跑 --check
```

四步各自对应一条既有能力，**不重造**：① 入口软链进 PATH（沿用 `06` 步骤 2）；② 8 束 `kol-*`
按**软链**装到宿主技能目录（唯一真源留在包里）；③ **直接调 `daniel connect --host <宿主> --apply --confirm`**；
④ 打开／打印 Daniel 登录页（浏览器授权路，**绝不索要账号密码**）。

- **幂等**：每一步先判"现状是否已是目标" ⇒ 重复跑**不改任何文件**；**可回滚**：写前把原文落进
  `<数据落点>/install/snapshots/<时间戳>/`，输出里带逐条回滚命令；
- **分发渠道的缝**：`--from` 是唯一的"取包"参数，实现只有一处（`install/source.py::resolve`）——
  **现在是本地安装；包上 npm 之后还是同一条命令、同一套步骤**（且**不引入 Node／npm 依赖**）；
- 🔴 **自动化不许弹窗**：`install` 是给人用的（人在真终端里可打开登录页），但**自检／验收／CI／Agent
  一律不得调起系统浏览器** —— 判据是**代码默认行为**（`DANIEL_NO_OPEN=1`／显式 `--no-open`／
  **非交互终端**，三条任一命中即不开），单一实现在 `commands/mod_account.no_open_decision`；
- 🔴 **登录只在会话失效时发生**：`auth status` 退 0（有效）⇒ 第 ④ 步直接判「已完成」，**不重新登录、
  不弹页**；退 2（服务端不可达）⇒ 明确"不要重新登录"；**只有退 1 才走登录页**，且一次运行最多开一次。

## 7. 自检覆盖（`daniel --self-test`）

| 组 | 覆盖 |
|---|---|
| A | 单一真源一致（同 `schema --check` 的 10 项） |
| E | 退出码语义：缺参 → 2；类型非法 → 2；写操作无 `--confirm` → 3（且说明未执行写）；写操作带 `--confirm` → 1；只读 → 0 |
| R | 12 模块各一条只读命令真实返回数据（退出码 0 且结果是 JSON）。**受控并发**跑（TICKET-151 C1）：线程池默认 6 路（`DANIEL_SELFTEST_SMOKE_WORKERS` 可覆盖，`1`＝串行对照），汇总仍按固定模块顺序输出；任一条失败会指名道姓地打印**是哪一条**与**原始错误**（stderr 原文，凭据值已脱敏） |
| J | `--json` 输出可被 `json.loads` 整体解析；外层信封字段齐备 |
| Z | 零 DSH 依赖：把 `PATH` 收成只含 `python3` 再跑一条只读命令；另做源码级 import 扫描 |
| C | 凭据来源矩阵：有钥匙串 → `keychain`；无钥匙串且有环境变量 → `env`（**全程不写钥匙串**） |
| R2 | **模块自带自检**（2026-10-15 通用化）：凡 `schema` 里声明了 `selfTest` 的模块**自动**纳入本组（当前 `account` ＋ `keywords` ＋ `skills` ＋ `intake`），**不重写任何模块的判据**，只逐个子进程外调；另加一条**覆盖断言**「声明了几个就必须覆盖几个」——目的是防"声明了却没接线"（`intake` 的 19 项自检曾一度没进总自检，于是"总自检全过"≠"所有模块自检都过"）。新增模块只需在 schema 声明 `selfTest`，**不必再手工接线** |
| P | 契约引擎自证（TICKET-146 · **引擎级最小**）：契约能加载／校验、最小契约跑通且计数自洽、门禁五道齐备、沙箱处置写明、D3 拒幻觉命令、引擎零 DSH 依赖（**逐契约期望核对**交给 `playbook selfcheck` 单一入口，见 §7.1） |

## 7.1 工序契约（`playbook`，TICKET-146）

一条工序 ＝ 一份 JSON 契约（八项字段：输入／前置／步骤／判据／门禁／交付件schema／自检／失败模式）。
`contracts/` 是契约真源（`DANIEL_CONTRACTS_DIR` 可覆盖），格式与写法见 `PLAYBOOK.md`。

| 命令 | 做什么 |
|---|---|
| `playbook list` | 列出契约目录里的全部契约（含示例与退化样本） |
| `playbook show <契约>` | 看一份契约全文与校验结论（也可写 `--name <契约>`） |
| `playbook validate [<契约>]` | 校验字段齐备、**步骤只引用 `schema.py` 已声明的命令与参数**（D3）、门禁五道齐备（不给契约名则校验全部） |
| `playbook run <契约>` | 跑契约：判据变断言、门禁真拦人、出交付件与自检报告（含计数自洽）；`--keep` 保留沙箱 |
| `playbook deliver <契约>` | **出件**（TICKET-175）：跑一份**模板式**契约，把交付物按声明的格式落到本地目录；落点默认 `$DANIEL_HOME/output/<契约id>/`，`--out DIR` 可覆盖（落点统一由 `daniel_paths` 解析，**不写代码目录**） |
| `playbook selfcheck` | 引擎自证：把每份契约按它声明的 `期望` 各跑一遍（含退化样本） |

三条要点：

- **门禁挂在执行器内部**（不依赖任何宿主 hook）：样本上限／写权限／只读默认／写步骤确认／回读校验；
- **写类动作只有离线假动作**（只写本地沙箱文件），契约引用任何 Daniel 写路由都会被硬拒绝（退出码 2）；
- **沙箱默认跑完即清理**（`finally` 里清，正常／报错／被拦下都清）；`--keep` 或设
  `DANIEL_PLAYBOOK_SANDBOX` 则保留，报告里的 `运行.沙箱保留` 写明是哪一种；
- **超限报错、不静默截断**；`--full` 在 v0.1 直接报错退出；
- **三条运行路径都要自证**：`期望` 支持 `默认`／`干跑`（`--dry-run`）／`带确认`（`--confirm`），
  含写步骤的契约三条必须齐（`playbook selfcheck` 逐条跑、逐条核对期望与实际）。

### 7.2 交付物工厂（出件模板 ＋ 出件自检 ＋ 本地落盘，TICKET-175）

`交付件schema` 有两代写法，**同一份字段**，不另造机制：

| 写法 | 触发条件 | 行为 |
|---|---|---|
| **遗留式** | 只声明 `名称／文件名／来源步骤／列／必填列` | 出 JSON 到**本次运行的沙箱**（跑完随沙箱清理）。老契约一个字不用改 |
| **模板式** | 多声明一个 `格式`（`CSV`／`XLSX`／`MD`／`JSON`／**`PDF`**＝印刷级出件） | 按模板渲染、**出件前自动跑五条自检**（PDF 另加一条「PDF 保真」）、落 `$DANIEL_HOME/output/<契约id>/`；`--out` 可覆盖 |

模板式要声明：`列`（列名／来源／必填或可空／无数据写法／出处）、`排序`（键＋方向）、
`无数据写法`、`不得占位列`、`行判据`（逐字取自 Skill，每条带 `出处`）、`关键桶`、
`计数对账`、`判据出处`，可选 `附表`（说明与口径）。`playbook validate` 会把
**缺字段／排序键不存在／必填列与无数据写法缺失／引用不可解析**逐条报出来。

**五条出件自检（出件的组成部分，自动跑；不过不得出件）**：

| # | 断言 | 不过的后果 |
|---|---|---|
| ① | 全表闭合：候选池与出件表两侧，每条记录都带齐必填列 | 逐条点出**第几行缺哪一列** |
| ② | 计数对账：主表行数 == **回读出来的**文件行数；入池 ≥ 出件且差额可解释 | 两侧实际值都印出来 |
| ③ | 排序键单调（按模板声明的键与方向） | 点出**第一处逆序的行号** |
| ④ | 无「无数据写法」以外的空值，且不许自造 `N/A`／`-` 之类占位 | 点出行号＋列名 |
| ⑤ | 关键桶非 0（如出件行数、来源任务去重数） | 点出哪个桶是 0、下限是多少 |

**「不过不得出件」怎么做到**：渲染 → 写进**系统临时文件** → 回读做计数对账 → 五条全过才
`os.replace` 到落点。任一条不过：临时文件删除、**落点上不存在任何文件**、非零退出。

三个现成的契约（`daniel playbook list` 可见）：

| 契约 | 作用 |
|---|---|
| `high-performance-video-list` | 第一个模板（高表现视频清单，29 列）：判据逐字取自 KOL 能力语料 §15.5.3／§15.5.4／§15.5.5／§15.5.6，用离线夹具跑通全链 |
| `high-performance-video-list-degraded` | **出件自检正控**：夹具里故意埋一条缺列记录 → 必须 FAIL、点出行号、不产出文件 |
| `high-performance-video-list-live` | **真实只读数据示例**：4 次只读调用取回品牌名任务＋SKU 词任务的完整品牌池（524 条），不触发采集、不做任何写 |

## 8. 本工序不做的事（边界）

> ⚠️ 本节原先写着「不做写链／不实现 MCP server」—— 那两条在后续票里已经**不再成立**
> （写链已装好三道闸并接通真实执行；`mcp/server.py` 就是本包自带的服务）。下面是**当前事实**。

- **写链：命令都实现了，但默认不执行**。**22 条**写命令全部装好闸门（**权限判据**＋**`--confirm`**
  ＋**删除类 `--delete-token`**＋**执行后回读校验**）：不带 `--confirm` 一律**干跑**（退出码 3，只打印将要做什么与影响范围）。
  开放级别：`live`（**21 条真实执行已接通**，含触发类四条与 `ct` 建／删活动；执行后回读校验并留审计记录）｜
  `sandbox`（`playbook run` 的写动作只落本地沙箱）。**每一次尝试都留恰一条审计**（成功／失败／被拒／干跑／
  **执行函数抛异常**各一条，失败带可判定的 `failureKind`，对账式见 §2 的「写操作的留痕」行）。
  **触发类四条**（`search submit`／`mentions run`／
  `sov run-exposure`／`route sweep`）真跑时**一律经统一队列**先拿并发位（`DANIEL_SCHED_CONCURRENCY`，默认 1），
  命中 429／5xx 按指数退避重试，结束时把终态（成功／失败／超时／配额耗尽）写进队列记录（`daniel sched queue` 可见）；
- **MCP 形态：本包自带 server（`mcp/server.py`）**，把 89 条命令全部暴露成工具；
  写链以「**确认单**」形态注册 —— **调用只返回确认单，永不执行、永不转发 `--confirm`**
  （影响面只来自只读预查）。所以"写动作不由 AI 执行"这条纪律的**执行面在 CLI**，
  MCP 只是把它交到人手里。口径逐条登记在 `mcp/exposure-register.json`；
- **不在 DSH 内注册工具**：`schema dsh-tools` 只打印 `defineTool` 草稿；
- **不做飞书写操作**：本交付物与飞书无关（确认单的五类动作里，「同步飞书」与「对外发信」
  今日**还没有对应命令**，通道为它们留位但不假装覆盖）；
- **不写具体业务工序**：`contracts/` 里的业务契约只到"出件模板的第一个模板"（高表现视频清单，
  TICKET-175）；竞品视频子表、跨快照取点名证据并集、其余业务工序是后续票的事（**不假装覆盖**）。
