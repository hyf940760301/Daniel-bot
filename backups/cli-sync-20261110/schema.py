# -*- coding: utf-8 -*-
"""**单一真源**：Daniel CLI 的全部模块、子命令、参数、退出码与示例（TICKET-145 §2）。

为什么要有这个文件
------------------
票面要求"同一份 schema 自动派生三样东西"。这个文件就是那份 schema，派生器有三：

  - `helpgen.py` → CLI 的 `--help` 文本（**不手写第二份**）
  - `exports.py` → MCP tool list（`{"name","description","inputSchema"}`）
  - `exports.py` → DSH `defineTool` 工具定义草稿（`{"name","description","parameters"}`）

因此本文件**只描述、不执行**：任何 handler 都放在 `commands/` 下，靠 `commands/__init__.py`
里的注册表与这里的键一一对应。两份真源一旦漂移，`daniel schema --check` 会报出来。

字段口径
--------
- `type`：`str` / `int` / `float` / `flag`（布尔开关） / `path` / `choice`
- `required`：只对**取值型**参数有意义（`flag` 永远不是必填——开关的"必填"是语义问题，不是参数问题）
- `write`：`True` 表示有副作用（写操作）。写链有三道独立的闸（TICKET-152）：
  ① **权限**：账号对**该模块**有写权限才放行；没有权限 → 退出码 2 ＋ 人话理由
     （说明系统角色／账号状态／工作区权益／配额是哪一轴不满足）；
  ② **确认**：不带 `--confirm` 一律只做干跑（打印将要做什么＋影响范围），退出码 3，零写入；
  ③ **删除凭据**：删除类命令在 `--confirm` 之外还要 `--delete-token <目标名>`
     （把目标名原样再写一遍；写错即拒、退出码 2、零删除）。
- `write_stage`：写命令的开放级别。`live`＝真实执行已接通（带确认会真写，写后回读校验）；
  `gated`＝本工序只交付权限门禁、干跑与审计留痕，真实执行不在本工序范围；
  `sandbox`＝写动作只落在本次运行的沙箱目录内（工序契约引擎的离线假动作）。
- `delete_target`：删除类命令的目标名口径（例如「名单名」）。填了它，派生出的帮助里必须出现
  `--delete-token`，`daniel schema --check` 会核对它真的被注册（帮助与实际参数不许漂移）。
- `route_debug`：内部数据通路名，**只在 `--json` 的调试卷里出现**，不进 `--help`
"""
from .exits import EXIT_CODES, EXIT_INTERNAL, EXIT_OK, EXIT_USAGE, EXIT_NEEDS_CONFIRM

#: 票面要求的 12 个模块（`schema` 是元模块，不计入）
REQUIRED_MODULES = ("brands", "lists", "search", "mentions", "intel", "sov",
                    "ct", "authenticity", "route", "takeover", "parity", "account")

#: **本机副作用**类模块：写的是**本机文件**（宿主配置），不是 Daniel 数据。
#: 为什么需要这张表（且必须逐条写明理由）：`schema --check` 的 S6 有一条"非业务模块的写级别只能
#: 是 `sandbox`"的约束，它的本意是"没有权限判据的模块不许真写 Daniel 数据"。而接入类模块写的是
#: 用户本机的宿主配置文件 —— 这里根本没有"Daniel 账号权限"这一轴可判（`permissions.verdict`
#: 对无判据模块一律放行，理由就是"该模块没有模块级判据"），但它**确实**要真写、也**确实**走
#: 同一条门禁链（确认轴 ＋ 快照 ＋ 回读对账 ＋ 审计）。把这条例外写进唯一的真源、并由 S6
#: **显式打印**（不做静默分支），比让实现去迁就一个不适用于它的约束更诚实。
LOCAL_WRITE_MODULES = {
    "connect": "写的是**本机宿主配置**（~/.cursor/mcp.json ／ ~/.codex/config.toml），不是 Daniel "
               "数据：没有 Daniel 账号权限这一轴可判；真实写链已接通，且带确认轴 ＋ 写前快照 ＋ "
               "写后回读对账 ＋ 可撤销（`--uninstall`）＋ 审计留痕。",
    "pack": "写的是**本机的一个交付目录**（`<你给的目录>/daniel-bot`，逐文件从源目录复制），"
            "不是 Daniel 数据：没有 Daniel 账号权限这一轴可判；真实写链已接通，且带确认轴 ＋ "
            "**出包即自证**（回读对账五条：文件集合／逐文件 sha256／点名排除 0 命中／结构完整／"
            "引用闭合）＋ 出包清单（收据）落在包目录之外 ＋ 审计留痕；包目录非空或落在源目录之内"
            "一律拒绝。",
    "install": "写的是**本机三处安装落点**（`~/.local/bin/daniel` 一条软链 ＋ shell 配置里一行 "
               "PATH；宿主技能目录下 8 条 `kol-*` 软链；宿主配置里本产品那一条 —— 后者**只经 "
               "`connect` 写**），不是 Daniel 数据：没有 Daniel 账号权限这一轴可判；真实写链已接通，"
               "且带确认轴 ＋ **写前落快照**（`$DANIEL_HOME/install/snapshots/<时间戳>/`）＋ "
               "**写后逐项回读对账**（入口真能跑／软链指向本包／技能正文 sha256 与包内一致／"
               "宿主配置条目恰好一条且指向本次装的包）＋ 审计留痕；每一步先判「现状是否已是目标」"
               "⇒ **重复跑不改任何文件**（幂等）。**完成后仍须处于已登录态**才算成功（否则如实报"
               "「还差登录这一步」并给出下一步命令，退出码非 0）。",
}

#: `connect` 支持的宿主（选项候选值的唯一真源；实现层从 `daniel_cli/connect/hosts.py` 取同一份）
CONNECT_HOSTS = ("cursor", "codex")

OPTION_TYPES = ("str", "int", "float", "flag", "path", "choice")


def o(name, type="str", help="", required=False, metavar=None, default=None,
      choices=None, repeat=False, secret=False):
    """定义一条参数。`help` 用业务语言（不写内部通路名）。

    `secret=True`：**这条参数的取值不得出现在任何输出里**（密码类）。声明在这里是给所有派生器
    与执行层看的同一份事实：CLI 侧该参数的值在进"执行计划"之前就被抹掉；派生出来的工具定义
    里把它标成 `writeOnly`；任何"把实参拼成给人看的命令"的地方都必须用占位符而不是原值。

    名字不以 `-` 开头即**位置参数**（例如 `playbook run <契约>` 里的 `契约`）：
    它同时有一个等价的 `--name 契约` 写法（两条路都能用）。位置参数在 argparse 侧一律用
    `nargs="?"`（与同名选项共用 dest，避免互相覆盖），因此 `required=True` 的含义是
    "运行期必填、工具定义里也标必填"，缺参由运行期报用户错误（退出码 2）。
    """
    if type not in OPTION_TYPES:
        raise ValueError("未知参数类型：%s（允许：%s）" % (type, "/".join(OPTION_TYPES)))
    if required and type == "flag":
        raise ValueError("%s：布尔开关不能标必填" % name)
    if choices and type != "choice":
        raise ValueError("%s：只有 choice 能带候选取值" % name)
    positional = not str(name).startswith("-")
    if positional and type == "flag":
        raise ValueError("%s：位置参数不能是布尔开关" % name)
    return {
        "name": name,
        "type": type,
        "help": help,
        "required": bool(required),
        "positional": positional,
        "metavar": metavar,
        "default": default,
        "choices": list(choices) if choices else None,
        "repeat": bool(repeat),
        "secret": bool(secret),
    }


def c(name, summary, options=(), write=False, examples=(), returns="",
      description=None, exit_codes=None, route_debug=None, instrument=None,
      write_note=None, read_only_dynamic=False, read_only_note=None,
      write_stage=None, delete_target=None, danger=None, cli_aliases=None,
      confirm_help=None, local_write_note=None):
    """定义一条子命令（粗粒度：一个业务动作一条命令，不做 219 个脚本的镜像）。

    `write_note`：写操作默认有一段统一的提示文本（"权限 → 确认 → 删除凭据"三道闸）；
    少数命令的写语义更细（例如 `playbook run` 只有**契约里有写步骤时**才需要确认），
    可以用它换成更准确的说法 —— 帮助文本必须说真话，而门禁的机器判据（S6）不动。

    `write_stage`：写命令的开放级别（`live`／`gated`／`sandbox`，见文件头口径）。
    写命令不填就按 `live` 处理（本工序的真实写链只接通了品牌与名单两组）。

    `delete_target`：删除类命令的目标名口径（例如「名单名」）。填了它，派生器必须给这条命令
    加上 `--delete-token`，`schema --check` 会核对"声明了就必须真的注册"。

    `read_only_dynamic`：**是否只读取决于运行期输入**（例如 `playbook run` 取决于契约里有没有
    写步骤）。这类命令不写死"只读/非只读"的布尔注解（写死就是假话），改由派生器输出
    "取决于契约"＋一句说明；运行时信封的 `readOnly` 仍按实际情况如实给出。

    `confirm_help`：这条写命令 `--confirm` 的帮助文案。不填就按 `write_stage` 派生
    （`live`＝写了会真写／`gated`＝本工序不执行／`sandbox`＝只落本次运行的沙箱目录）。
    写语义更细的命令（例如"把凭据写进本机钥匙串""登录并刷新会话"）应当填它，让用户在按
    `--confirm` 之前就知道**究竟会写什么** —— 帮助必须与真实副作用一致。

    `cli_aliases`：这条命令**等价的 argv 写法**（整条命令路径，例如
    `["account credentials set"]`）。本 CLI 的子命令名是**单个 argv 词**（argparse 的
    `add_subparsers` 按词匹配），所以"两段式读法"没法直接注册成一条命令；为了一边保住
    "MCP 确认单里由 `模块 + 子命令` 拼出的命令必须真能跑"与"命令键 `.split(\".\")` 拼出的
    argv 必须对"，一边让两种写法都可用，别名在这里**声明**（唯一真源），由 `rewrite_aliases`
    在解析前按声明重写 argv，并在帮助文本里列出。

    `local_write_note`：这条命令**会往本机落点写文件，但不写 Daniel 远端**（例：`playbook
    deliver` 把交付物写进本机出件落点）。为什么必须有这个字段（`TICKET-202` 的 `Q14`，事故形态
    ＝**登记与事实不符**）：`write=False` 只表示"不是写链"，派生器据此把命令标成**纯只读**
    （`readOnlyHint=True`／`exposure=read-only`）⇒ 宿主与读者都会以为它**完全不动磁盘**，而它
    其实会在本机产出交付物。填了它，派生器改用 **`local-output`** 档（**仍可直接执行** —— 不是
    写链、不改执行语义），且**两个载荷**（协议面 `tools/list` 与自省载荷 `schema --mcp --json`）
    都带上档位与这句注记。
    """
    codes = list(exit_codes) if exit_codes else ([EXIT_OK, EXIT_USAGE, EXIT_INTERNAL] +
                                                ([EXIT_NEEDS_CONFIRM] if write else []))
    stage = write_stage
    if write and stage is None:
        stage = "live"
    if not write:
        stage = None
    if write and not returns:
        # 写操作统一口径：写链有三道闸（权限／确认／删除凭据），写后回读校验并留审计
        returns = ("写操作的结果：干跑时给出执行计划与影响范围；带 --confirm 执行时给出改动前后的"
                   "对照、回读校验结论与审计记录落点。")
        if stage == "gated":
            returns = ("写操作的结果：本工序只到干跑（给出执行计划与影响范围）；"
                       "真实执行不在本工序交付范围。")
        elif stage == "sandbox":
            returns = "写操作的结果：写动作只落在本次运行的沙箱目录内，并给出回读校验结论。"
    return {
        "name": name,
        "summary": summary,
        "description": description or summary,
        "options": list(options),
        "write": bool(write),
        "writeStage": stage,
        "deleteTarget": delete_target,
        "danger": danger,
        "cliAliases": [str(a) for a in cli_aliases] if cli_aliases else None,
        "confirmHelp": confirm_help,
        "writeNote": list(write_note) if write_note else None,
        "readOnlyDynamic": bool(read_only_dynamic),
        "readOnlyNote": read_only_note or ("是否只读取决于运行期输入（运行时信封的 readOnly 会如实给出）"
                                          if read_only_dynamic else None),
        #: **会往本机落点写文件、但不写 Daniel 远端**的命令（`TICKET-202`·`Q14`）。
        #: 与 `readOnlyNote` 分开：前者说"只读性取决于输入"，这里说的是"确实会写**本机**文件"。
        #: 派生器（`exports.exposure_of`）把它判成 `local-output` 档，两个载荷都带上。
        "localWriteNote": local_write_note,
        "examples": list(examples),
        "returns": returns,
        "exitCodes": codes,
        "routeDebug": route_debug,
        "instrument": instrument,
    }


def m(key, title, summary, commands, flag_commands=None, usage_note=None, self_test=None,
      options=()):
    """定义一个模块。`flag_commands` 支持 `daniel schema --check` 这种"不带子命令名"的写法。

    `self_test`：本模块**自带**自检的一句话说明（给了它，模块的 `--help` 里就出现 `--self-test`，
    且 `daniel <模块> --self-test` 走这个模块自己的自检，而不是 CLI 总自检）。
    只有真的实现了模块级自检的模块才填 —— 帮助必须说真话。

    `options`：**模块级**（子命令之外）的参数。为什么要它：`flag_commands` 把开关变成命令之后，
    用户很自然会写成 `daniel connect --host cursor --print`（参数在开关**前面**），而开关背后的
    参数若只声明在子命令上，这种写法就解析不了。声明在这里的参数会同时挂在模块解析器上；子命令上
    也声明同一份（两处同源，同一个 `o(...)` 定义），于是"参数在前／在后"两种写法都能用
    —— argparse 只在目标属性**不存在**时才写默认值，因此模块层先解析到的值不会被子解析器覆盖。
    """
    return {
        "key": key,
        "title": title,
        "summary": summary,
        "usageNote": usage_note,
        "flagCommands": dict(flag_commands or {}),
        "selfTest": self_test,
        "options": list(options),
        "commands": list(commands),
    }


# ─────────────────────────── 全局参数 ───────────────────────────
GLOBAL_OPTIONS = [
    o("--json", "flag", "结果以 JSON 打印（结果只走 stdout；进度与提示只走 stderr）"),
    o("--verbose", "flag", "把过程信息也打到 stderr（默认安静）"),
    o("--version", "flag", "打印版本号后退出"),
    o("--self-test", "flag", "跑本 CLI 的自检（schema 一致性、退出码语义、12 模块只读可达、零 DSH 依赖）"),
]

# ─────────────────────── `install` 模块的参数（模块级与子命令共用同一份定义） ───────────────────────
# 为什么要提出来放这里：`flag_commands` 把 `--check` 变成命令之后，用户很自然会写成
# `daniel install --check --project ~/x`（参数在开关**后面**）；模块级与子命令级声明**同一份**
# `o(...)` 定义，两种写法才等价（见 `m()` 的 `options` 说明）。
_INSTALL_HOST = o("--host", "choice", "接入哪个宿主；不给则**自动检测本机有痕迹的宿主**"
                                     "（一个都没检测到 ⇒ 第 ③ 步按「不适用」如实登记）",
                  choices=CONNECT_HOSTS, metavar="宿主")
_INSTALL_FROM = o("--from", "path", "装哪一份包：默认＝**手上这一份包**；也可给 `daniel pack --out` "
                                    "出的产物目录或一个包目录（**分发渠道的唯一抽象点**在 "
                                    "`install/source.py`，将来换 npm 只换它）", metavar="包目录")
_INSTALL_PROJECT = o("--project", "path", "能力束装到哪个项目目录（默认＝当前目录），落点是它下面的 "
                                          "`.agents/skills/`", metavar="项目目录")
_INSTALL_SKILLS = o("--skills-dir", "path", "直接指定能力束落点（默认 `<项目目录>/.agents/skills`）",
                    metavar="目录")
_INSTALL_BIN = o("--bin-dir", "path", "命令行入口装到哪个目录（默认 `~/.local/bin`）", metavar="目录")
_INSTALL_COOKIE = o("--session-cookie-stdin", "flag",
                    "无头／CI 形态：从标准输入读**浏览器里的会话值**（等价于 `account login` 的同名"
                    "开关）；🔴 读的是会话，**不是账号密码**")
_INSTALL_NOOPEN = o("--no-open", "flag", "不调用系统浏览器，只打印 Daniel 登录页地址")
_INSTALL_CONFIRM = o("--confirm", "flag", "确认执行这次安装；不给则只做干跑（打印四步计划，零写入）")
_INSTALL_DRYRUN = o("--dry-run", "flag", "只打印将要做什么（默认行为，可省略）")

# ─────────────────────────── 模块定义 ───────────────────────────
_MODULES = [

    m("auth", "授权", "**授权是起点**：未登录时业务模块一律不放行（退出码 2 ＋「请先登录」"
                      "＋ 一行修法，零真实数据、不静默降级）。本模块把「登录了没有」做成"
                      "**一条可脚本判定**的命令。",
      commands=[
          c("status", "看登录状态：本地会话 ＋ 一次服务端校验（退出码三档，可脚本判定）",
            options=[o("--timeout", "int", "服务端校验的超时秒数（默认 25 秒，"
                                             "真源见 daniel_cli/authgate.py::VERIFY_TIMEOUT）",
                       metavar="秒")],
            examples=["daniel auth status", "daniel auth status --json",
                      "daniel auth status --json | python3 -c \"import json,sys;"
                      "print(json.load(sys.stdin)['data']['authenticated'])\""],
            returns="`authenticated`（真／假）与 `reason`（通过／去登录／稍后重试），"
                    "外加本机会话文件落点、会话是否落在数据落点之内、服务端校验的最小事实"
                    "（掩码邮箱／HTTP 码／服务端原文分类）。**不回显任何会话值**。",
            exit_codes=[EXIT_OK, 1, EXIT_USAGE],
            route_debug="auth.me"),
      ],
      usage_note="未登录时**只有接入／自救／随包自检三类命令可用**（完整清单见 `daniel --help`）；"
                 "其余命令一律 fail-fast。\n\n"
                 "**登录的唯一正路**（账号密码只在 Daniel 自己的页面上输入，CLI 绝不追问）：\n"
                 "  ① `daniel account login --browser --confirm` —— 打开 Daniel 登录页并给出**回读步骤**；\n"
                 "  ② 在浏览器里完成登录；\n"
                 "  ③ 把浏览器里的会话粘回 CLI —— CLI **先校验后落盘**\n"
                 "     （`$DANIEL_HOME/session/session.json`，权限 600）；\n"
                 "  ④ `daniel auth status` —— 0＝通过／1＝去登录／2＝服务端不可达。\n"
                 "无头／CI 可用环境变量 `DANIEL_EMAIL`／`DANIEL_PASSWORD` ＋ "
                 "`daniel account login --confirm` —— **那是 CI 用的备用路，不是给人用的主路径**。\n\n"
                 "为什么不是「一键跳转授权」：平台的登录页（`/auth`）不接受 `redirect`／`callback`／"
                 "`code` 参数，`auth.*` 里也没有 device-code／poll 这类端点，Google 登录的 "
                 "`redirect_uri` 由服务端写死在自己域名 —— 授权码回不到命令行。"
                 "所以当前形态是「跳转登录页 → 在 Daniel 完成登录 → 从浏览器回读会话粘回 CLI」。"),

    m("brands", "品牌档案", "看品牌本身：有哪些品牌、某个品牌长什么样、竞品是谁。",
      [
          c("list", "列出账号可见的全部品牌（跨工作区，不受当前所在工作区影响）",
            options=[o("--workspace", "int", "只看某个工作区下的品牌", metavar="编号"),
                     o("--limit", "int", "最多返回几条", default=200, metavar="条数"),
                     o("--refresh", "flag", "强制重建品牌索引（较慢，约 1 分钟起）")],
            examples=["daniel brands list", "daniel brands list --json --limit 20",
                      "daniel brands list --workspace 90002"],
            returns="品牌编号、品牌名、所属工作区编号与名称。",
            route_debug="auth.listMyWorkspaces + brands.list(workspaceId)"),
          c("show", "看单个品牌的完整档案（简介、频道、竞品、目标市场）",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌")],
            examples=["daniel brands show --brand 3690002", "daniel brands show --brand Halliday --json"],
            returns="品牌档案对象。",
            route_debug="brands.getById"),
          c("competitors", "看某个品牌登记在案的竞品与品类关键词",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌")],
            examples=["daniel brands competitors --brand 3690002"],
            returns="竞品名与每个竞品对应的品类关键词。"),
          c("create", "新建品牌（写操作）", write=True, write_stage="live",
            danger="新建会占用工作区品牌配额（非管理角色用满即拒）",
            options=[o("--name", "str", "品牌名", required=True, metavar="名称"),
                     o("--description", "str", "品牌简介"),
                     o("--category", "str", "品类"),
                     o("--industry-keywords", "str", "行业关键词，英文逗号分隔（如 \"lawn mower,robotic mower\"）",
                       metavar="kw1,kw2"),
                     o("--target-countries", "str", "目标市场国家代码，英文逗号分隔（如 US,CA,GB）",
                       metavar="US,CA,GB"),
                     o("--sample-cost", "int", "样品价（整数）", metavar="金额"),
                     o("--competitors", "str", "竞品：\"名称:关键词1|关键词2;名称2:关键词\"，或 JSON 数组",
                       metavar="竞品串"),
                     o("--workspace", "int", "建到哪个工作区（不给就用当前工作区）",
                       metavar="编号")],
            examples=["daniel brands create --name \"示例品牌\" --confirm",
                      "daniel brands create --name \"_tmp-验收\" --workspace 90002 --confirm"]),
          c("update", "修改品牌资料（写操作）", write=True, write_stage="live",
            danger="按字段局部合并：只改你给的字段，其余字段保持原样（可回写原值还原）",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--name", "str", "新的品牌名"),
                     o("--description", "str", "新的品牌简介"),
                     o("--category", "str", "新的品类"),
                     o("--industry-keywords", "str", "新的行业关键词（英文逗号分隔；传空串表示清空）",
                       metavar="kw1,kw2"),
                     o("--target-countries", "str", "新的目标市场（英文逗号分隔；传空串表示清空）",
                       metavar="US,CA,GB"),
                     o("--sample-cost", "int", "新的样品价（整数）", metavar="金额"),
                     o("--competitors", "str", "新的竞品：\"名称:kw1|kw2;名称2:kw\"，或 JSON 数组（传 [] 清空）",
                       metavar="竞品串")],
            examples=["daniel brands update --brand 3690002 --description \"新简介\" --confirm",
                      "daniel brands update --brand 3690002 --description \"临时改动\" --confirm"]),
          c("clone", "参考某个品牌克隆一个新品牌：复制其简介／品类／行业关键词／目标市场／样品价／竞品"
                     "（写操作；干跑先给计划）",
            write=True, write_stage="live",
            danger="会在目标工作区新增 1 个品牌，并把参考品牌的业务字段整份复制过去；"
                   "受目标工作区品牌配额约束",
            confirm_help="确认在指定工作区新建这个品牌并复制参考品牌的业务字段",
            options=[o("--from", "str", "参考品牌（品牌名或编号）", required=True, metavar="品牌"),
                     o("--name", "str", "新品牌名", required=True, metavar="名称"),
                     o("--workspace", "int", "建到哪个工作区（不给就用当前工作区）", metavar="编号")],
            examples=["daniel brands clone --from Halliday --name Lymow --workspace 90002",
                      "daniel brands clone --from 3690002 --name \"_tmp-克隆验收\" --confirm"],
            returns="干跑：执行计划（新品牌名、目标工作区、将复制的字段清单、影响范围与配额）；"
                    "带 --confirm：新品牌编号、逐字段回读核对结论、审计落点。"),
          c("delete", "删除品牌（写操作，不可逆）", write=True, write_stage="live",
            delete_target="品牌名",
            danger="不可逆：品牌档案与登记竞品一并删除；默认只允许删除 _tmp- 前缀的测试品牌",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--allow-non-tmp", "flag", "允许删除非 _tmp- 前缀的真实品牌（默认拒绝）")],
            examples=["daniel brands delete --brand 4800002 --confirm "
                      "--delete-token \"_tmp-验收\""]),
      ]),

    m("lists", "红人名单", "看品牌下已经攒下来的红人名单，以及名单里都有谁。",
      [
          c("by-brand", "列出某个品牌下的全部名单",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌")],
            examples=["daniel lists by-brand --brand 3690002",
                      "daniel lists by-brand --brand Halliday --json"],
            returns="名单编号、名单名、条目数。",
            route_debug="lists.listByBrand"),
          c("items", "看某个名单里的红人条目（含频道、订阅数、评分）",
            description="看某个名单里的红人条目。默认输出与改造前一致（条目里**没有** @handle："
                        "列表接口本身不返回它）；要给每条补上 @handle，显式加 `--with-handle` —— "
                        "它会逐条查频道详情（同一频道走 15 分钟进程内缓存，不重复发请求）。",
            options=[o("--list-id", "int", "名单编号", required=True, metavar="编号"),
                     o("--limit", "int", "最多返回几条", default=50, metavar="条数"),
                     o("--offset", "int", "从第几条开始", default=0, metavar="偏移"),
                     o("--with-handle", "flag", "逐条补上频道账号 @handle（走频道详情，带进程内缓存）。"
                                                "不加时输出与原来完全一致")],
            examples=["daniel lists items --list-id 8310034 --limit 20",
                      "daniel lists items --list-id 8310034 --limit 3 --with-handle",
                      "daniel lists items --list-id 8310034 --limit 3 --with-handle --json"],
            returns="红人条目列表。带 --with-handle 时每条多一个 handle（补不到会写明原因，"
                    "不留空值），并附一段补齐统计（发了几次请求、几次走缓存）。",
            route_debug="lists.getItems"),
          c("saved-channel-ids", "看某个品牌下所有名单里已保存过的频道编号（批量加人／去重前先看）",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌")],
            examples=["daniel lists saved-channel-ids --brand 3690002",
                      "daniel lists saved-channel-ids --brand Halliday --json"],
            returns="频道编号条数与编号清单 —— 用来避免把同一批人重复写进名单。",
            route_debug="lists.savedChannelIds"),
          c("share-status", "看某个名单的分享状态（是否开启分享、分享码、分享时间）",
            options=[o("--list-id", "int", "名单编号", required=True, metavar="编号")],
            examples=["daniel lists share-status --list-id 6150007",
                      "daniel lists share-status --list-id 6150007 --json"],
            returns="是否开启分享、分享令牌与分享码、分享时间。",
            route_debug="lists.getShareStatus"),
          c("auto-priority-status", "看某个名单的自动优先级状态（跑没跑、进度、完成时间）",
            options=[o("--list-id", "int", "名单编号", required=True, metavar="编号")],
            examples=["daniel lists auto-priority-status --list-id 6150007"],
            returns="自动优先级状态（如 idle／running）、进度百分比、完成时间与最近更新时间。",
            route_debug="lists.getAutoPriorityStatus"),
          c("create", "新建名单（写操作）", write=True, write_stage="live",
            danger="会自动拦同品牌下的重名名单（服务端不拦，由本命令在客户端拦）",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--name", "str", "名单名", required=True, metavar="名称")],
            examples=["daniel lists create --brand 3690002 --name \"第十一批\" --confirm",
                      "daniel lists create --brand 3690002 --name \"临时名单-验收\" --confirm"]),
          c("rename", "给名单改名（写操作）", write=True, write_stage="live",
            danger="只改名单名，名单里的条目不动",
            options=[o("--list-id", "int", "名单编号", required=True, metavar="编号"),
                     o("--brand", "str", "名单所属品牌（服务端接口需要品牌编号）",
                       required=True, metavar="品牌"),
                     o("--name", "str", "新的名单名", required=True, metavar="名称")],
            examples=["daniel lists rename --list-id 8310034 --brand 3690002 "
                      "--name \"第十批（终版）\" --confirm"]),
          c("delete", "删除名单（写操作，不可逆）", write=True, write_stage="live",
            delete_target="名单名",
            danger="不可逆：名单与其条目一并删除；默认拒绝删除非空名单",
            options=[o("--list-id", "int", "名单编号", required=True, metavar="编号"),
                     o("--brand", "str", "名单所属品牌（服务端接口需要品牌编号）",
                       required=True, metavar="品牌"),
                     o("--allow-non-empty", "flag", "允许删除仍有 creator 的名单（默认拒绝）")],
            examples=["daniel lists delete --list-id 8310034 --brand 3690002 --confirm "
                      "--delete-token \"第十批（终版）\""]),
      ]),

    m("search", "红人检索", "发起或回看红人检索：检索记录、检索任务状态。",
      [
          c("history", "看最近的检索记录（关键词、检索方式、发起时间）",
            options=[o("--limit", "int", "最多返回几条", default=10, metavar="条数")],
            examples=["daniel search history", "daniel search history --limit 30 --json"],
            returns="检索记录列表。",
            route_debug="discovery.getSearchHistory"),
          c("job-status", "看某个检索任务跑到哪一步了",
            options=[o("--job", "str", "检索任务编号", required=True, metavar="任务编号")],
            examples=["daniel search job-status --job 3f2a1b0c-0000-0000-0000-000000000000"],
            returns="任务状态与进度。",
            instrument="daniel_search.py --job-status"),
          c("submit", "提交一条新的红人检索（写操作／会触发检索）", write=True,
            write_stage="live",
            danger="会真的发起检索任务并消耗每月检索额度（建任务 ＋ 开跑共 2 次发包，"
                   "随后 1 次只读回读）",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--query", "str", "检索式（描述想找什么样的红人；上限 501 字符）",
                       required=True, metavar="检索式"),
                     o("--limit", "int", "希望返回多少个候选（记录在计划与审计里）", metavar="条数")],
            examples=["daniel search submit --brand 3690002 --query \"AI glasses reviewer\" --confirm"]),
      ]),

    m("mentions", "品牌提及", "看品牌的提及分析任务：跑过哪些、结果如何、单条视频表现。",
      [
          c("jobs", "列出某个品牌的提及分析任务",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--limit", "int", "最多返回几条", default=10, metavar="条数")],
            examples=["daniel mentions jobs --brand 3690002 --limit 5"],
            returns="任务编号、状态、分析时间范围、视频/频道/播放量汇总。",
            instrument="daniel_mentions.py --jobs"),
          c("status", "看某个提及任务的进度与汇总",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--job", "str", "任务编号", required=True, metavar="任务编号")],
            examples=["daniel mentions status --brand 3690002 --job <任务编号>"],
            returns="进度百分比、完成说明、结果汇总、异常信息。",
            instrument="daniel_mentions.py --status"),
          c("results", "看某个提及任务的结果分页（视频级评分）",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--job", "str", "任务编号", required=True, metavar="任务编号"),
                     o("--page", "int", "第几页", default=1, metavar="页码"),
                     o("--page-size", "int", "每页条数（最少 10、最多 200；总数不超过 200 时"
                                             "建议一次取完，避免翻页重复或漏条）",
                       default=50, metavar="条数"),
                     o("--relevance-filter", "choice",
                       "相关度口径：默认只给与本品相关的提及；要看全部（含与本品不相关的）"
                       "请显式指定 all",
                       default="confirmed_likely", metavar="口径",
                       choices=["all", "confirmed", "confirmed_likely"])],
            examples=["daniel mentions results --brand 3690002 --job <任务编号> --page-size 20",
                      "daniel mentions results --brand 3690002 --job <任务编号> "
                      "--relevance-filter all"],
            returns="视频标题、频道、播放量、表现档位。默认口径**只包含与本品相关的提及**"
                    "（confirmed_likely）：与本品不相关的条目会被挡在结果外；要看全部请显式"
                    "`--relevance-filter all`。本次实际用的口径见 JSON 的 `read.filter.echo`；"
                    "服务端另给一个**任务级**统计 `read.filter.taskLevelExcluded`"
                    "（本次分析共多少条被判为不相关，与本次筛选项无关，不是「本次被过滤了多少」）。",
            instrument="daniel_mentions.py --results"),
          c("run", "发起一次品牌提及分析（写操作／会触发采集）", write=True,
            write_stage="live",
            danger="会真的触发采集并入库（1 次发包 ＋ 1 次只读回读；回溯天数最少 7、"
                   "最多分析视频最少 100 条）",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--days", "int", "回溯天数（最少 7、最多 1095）", default=7, metavar="天数"),
                     o("--max-videos", "int", "最多分析多少条视频（最少 100、最多 5000）",
                       default=100, metavar="条数")],
            examples=["daniel mentions run --brand 3690002 --days 7 --confirm"]),
      ]),

    m("intel", "内容情报", "看系统给出的待办动作、关键词、选题与内容审核单。",
      [
          c("actions", "列出待办动作（系统建议做什么，含依据与建议做法）",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--status", "str", "只看某个状态的动作", repeat=True, metavar="状态"),
                     o("--limit", "int", "最多返回几条", metavar="条数")],
            examples=["daniel intel actions --brand 3690002",
                      "daniel intel actions --brand 3690002 --status suggested --json"],
            returns="动作编号、类型、标题、依据、建议做法、证据。",
            instrument="daniel_intel.py actions"),
          c("keywords", "列出品牌正在追踪的关键词",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌")],
            examples=["daniel intel keywords --brand 3690002"],
            returns="关键词、来源、启用状态、上限与余量。",
            instrument="daniel_intel.py keywords"),
          c("topics", "列出品牌的选题（含主要关键词与支撑词）",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌")],
            examples=["daniel intel topics --brand 3690002"],
            returns="选题编号、标题、主要关键词、支撑词。",
            instrument="daniel_intel.py topics"),
          c("reviews", "列出内容审核单",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌")],
            examples=["daniel intel reviews --brand 3690002"],
            returns="审核单列表（无单时为空列表）。",
            instrument="daniel_intel.py reviews"),
      ]),

    m("sov", "声量份额", "看品牌在某市场里跟竞品比声量：份额、品类档案、竞品视频明细。",
      [
          c("overview", "看品牌与竞品的声量份额总览",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--country", "str", "市场（默认取品牌档案里的第一个）", metavar="市场"),
                     o("--days", "int", "统计窗口天数", default=30, metavar="天数")],
            examples=["daniel sov overview --brand 3690002 --country US --days 30",
                      "daniel sov overview --brand Halliday --json"],
            returns="各品牌的播放量、视频数与份额占比。",
            instrument="daniel_sov.py --sov-overview"),
          c("categories", "看品牌所属的品类档案（含竞品清单与品类词）",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--country", "str", "市场（默认取品牌档案里的第一个）", metavar="市场")],
            examples=["daniel sov categories --brand 3690002"],
            returns="品类档案与登记竞品。",
            instrument="daniel_sov.py --categories"),
          c("brand-videos", "看品牌（或竞品）被收录的视频明细",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--video-brand", "str", "要看哪个品牌的视频（默认同 --brand）", metavar="品牌名"),
                     o("--limit", "int", "最多返回几条", default=30, metavar="条数")],
            examples=["daniel sov brand-videos --brand 3690002 --video-brand Halliday --limit 10"],
            returns="视频标题、频道、播放量、发布时间。",
            instrument="daniel_sov.py --brand-videos"),
          c("run-exposure", "发起一次曝光采集（写操作／会触发采集）", write=True,
            write_stage="live",
            danger="会真的触发采集并入库（1 次发包 ＋ 1 次档案解析 ＋ 1 次只读回读）",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--country", "str", "市场", required=True, metavar="市场"),
                     o("--days", "int", "统计窗口天数（用于计划说明；触发入参只有四个键）",
                       default=30, metavar="天数")],
            examples=["daniel sov run-exposure --brand 3690002 --country US --confirm"]),
      ]),

    m("ct", "合作追踪", "Creator Tracker：看品牌登记的合作活动与其档期。",
      [
          c("campaigns", "列出某个品牌登记的合作活动",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌")],
            examples=["daniel ct campaigns --brand 3690002"],
            returns="活动编号、标题、起止日期、活动码。",
            route_debug="ct.campaigns.list"),
          c("campaign-stats", "看某个合作活动的统计（订单数／达人数／应有与已关联视频数）",
            options=[o("--campaign", "int", "活动编号（`daniel ct campaigns --brand <品牌>` 可取）",
                       required=True, metavar="编号")],
            examples=["daniel ct campaign-stats --campaign 660001",
                      "daniel ct campaign-stats --campaign 660001 --json"],
            returns="活动对象本身（编号／标题／起止／活动码）＋统计项：订单数、达人数、"
                    "应有视频数、已关联视频数（长／短视频分列）。",
            route_debug="ct.campaigns.getStats"),
          c("deals", "看某个合作活动的订单明细（达人合作单 ＋ 视频表现）",
            options=[o("--campaign", "int", "活动编号", required=True, metavar="编号")],
            examples=["daniel ct deals --campaign 660001",
                      "daniel ct deals --campaign 660001 --json"],
            returns="订单条数与逐条明细（合作单 ＋ 关联视频的统计）。该活动还没有订单时返回 0 条"
                    "（**不是失败**）。",
            route_debug="ct.deals.listWithVideoStats"),
          c("videos", "看某个合作活动下已关联的共创视频明细",
            options=[o("--campaign", "int", "活动编号", required=True, metavar="编号")],
            examples=["daniel ct videos --campaign 660001",
                      "daniel ct videos --campaign 660001 --json"],
            returns="视频条数与逐条明细。活动还没有关联视频时返回 0 条（**不是失败**）。",
            route_debug="ct.videos.list"),
          c("resolve-channel", "把频道输入（@handle／链接／UC 编号）解析成频道编号",
            options=[o("频道", "str", "频道输入：@handle、频道链接或 UC 开头的频道编号",
                       required=True, metavar="频道")],
            examples=["daniel ct resolve-channel @Mrwhosetheboss",
                      "daniel ct resolve-channel @Mrwhosetheboss --json"],
            returns="解析出的频道编号与是否成功。建活动要填的品牌频道建议用这里取到的编号。",
            route_debug="ct.campaigns.resolveChannel"),
          c("interests", "看某个频道的内容兴趣画像",
            options=[o("--channel", "str", "频道编号（UC 开头）", required=True, metavar="频道")],
            examples=["daniel ct interests --channel UC66W1l41kXuASV-UYvC9xzA"],
            returns="兴趣来源与兴趣列表（这个频道的内容兴趣画像）。",
            route_debug="ct.videos.getChannelInterests"),
          c("create-campaign", "新建合作活动（写操作）", write=True, write_stage="live",
            danger="会真的在品牌下建出活动（1 次发包 ＋ 1 次回读；建完可删）",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--title", "str", "活动标题（验收用请带 `-验收-` 前缀；以 `-` 开头时"
                                         "写成 --title=\"-验收-…\"，否则会被当成选项）",
                       required=True, metavar="标题"),
                     o("--start", "str", "开始日期 YYYY-MM-DD", required=True, metavar="日期"),
                     o("--end", "str", "结束日期 YYYY-MM-DD（不给就得显式加 --evergreen）",
                       metavar="日期"),
                     o("--brief", "str", "活动简介（可选）", metavar="简介"),
                     o("--evergreen", "flag", "长期有效（不设结束日期）")],
            examples=["daniel ct create-campaign --brand 3690002 --title \"夏季合作\" "
                      "--start 2026-08-01 --evergreen --confirm",
                      "daniel ct create-campaign --brand 3690002 --title=\"-验收-临时活动\" "
                      "--start 2026-10-15 --end 2026-10-16 --confirm"]),
          c("delete-campaign", "删除合作活动（写操作／**不可逆**）", write=True, write_stage="live",
            delete_target="活动标题",
            danger="不可逆：删完活动与其关联数据一并消失（删除类：除 --confirm 外还要 --delete-token）。"
                   "服务端前置：活动处于 active 时不能直接删（HTTP 412 实测），会先自动归档再删",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--campaign", "int", "活动编号（`daniel ct campaigns --brand <品牌>` 可取）",
                       required=True, metavar="编号")],
            examples=["daniel ct delete-campaign --brand 3690002 --campaign 660001 --confirm "
                      "--delete-token \"halliday summer test\""]),
      ]),

    m("authenticity", "真实性核验", "看单个频道的数据是否可信（播放、互动、波动三项信号）。",
      [
          c("channel", "按频道看真实性评分（支持频道链接、@handle 或频道编号）",
            options=[o("--channel", "str", "频道链接、@handle 或频道编号", required=True, metavar="频道"),
                     o("--videos-json", "path", "离线复核：改用本地视频数据文件，不联网", metavar="文件")],
            examples=["daniel authenticity channel --channel @Mrwhosetheboss",
                      "daniel authenticity channel --channel UCxxxx --json"],
            returns="频道名、订阅数、样本视频数、总分与三项信号的判定。",
            instrument="daniel_authenticity.py --channel"),
          c("weights", "看真实性评分各信号的权重口径（离线，不联网）", options=[],
            examples=["daniel authenticity weights"],
            returns="各信号名称与权重。",
            instrument="daniel_authenticity.py --explain-weights"),
      ]),

    m("route", "数据通路体检", "检查底层数据通路是否还通（只读探测，不触发任何采集）。",
      [
          c("probe", "探测一条只读通路是否可用，返回拿到的字段形状"
                     "（判断字段是否存在只能看 fields 列表；sample 只用于看数据形态、默认截断）",
            description="探测一条只读通路是否可用，返回拿到的字段名与一段数据样本。"
                        "**判断某个字段是否存在，只能看 `fields` 列表**（它来自整包返回的全部字段名）；"
                        "`sample` 只用于看数据形态，默认截断到前 400 字符，被截断时样本末尾带显式标记，"
                        "并同时给出 `sample_chars`（原始长度）与 `sample_truncated`（是否被截断）——"
                        "**样本里没看到某个字段，不等于平台没有这个字段**"
                        "（历史事故：频道详情共 11 个字段、handle 排在最后被切掉，于是被误判为没有 handle）。"
                        "要看完整样例加 `--full-sample`。",
            options=[o("--route", "str", "通路名（用 `daniel route catalog` 查）", required=True, metavar="通路"),
                     o("--input", "str", "入参 JSON（默认空参）", metavar="JSON"),
                     o("--full-sample", "flag", "返回完整样本（默认截断到 400 字符）。"
                                                "判断字段是否存在只看 fields 列表，sample 只用于看数据形态")],
            examples=["daniel route probe --route discovery.resolveChannelInput "
                      "--input '{\"input\":\"@Harveyinchina\"}'",
                      "daniel route probe --route discovery.getChannelDetail "
                      "--input '{\"channelId\":\"UCrfKs1Lm9hV_YBo0SHf2IBA\"}' --full-sample",
                      "daniel route catalog"],
            returns="是否可用、耗时、返回的**完整**字段名清单（fields —— 判断字段存不存在的唯一依据）、"
                    "字段数（field_count）、数据样本（sample）及其原始长度（sample_chars）"
                    "与是否被截断（sample_truncated）。"),
          c("catalog", "列出可探测的通路清单（离线，不联网）", options=[],
            examples=["daniel route catalog", "daniel route catalog --json"],
            returns="通路名、请求动词、说明、是否已知可用。"),
          c("sweep", "全量扫描通路可用性（写操作／逐条发包探测）",
            write=True, write_stage="live",
            danger="逐条发包（**只读 GET**）：写语义通路以 405 判定存在性，**不执行任何写动作**；"
                   "一条通路一次请求，不并发、不重试",
            options=[o("--limit", "int", "本次最多探测几条候选通路（默认全部）", metavar="条数"),
                     o("--out", "path", "把完整探测结果写到这个文件", metavar="文件")],
            examples=["daniel route sweep --confirm",
                      "daniel route sweep --limit 3 --confirm --json"]),
      ]),

    m("takeover", "接管验收", "核对「我们读到的」与「页面上看到的」是否一致：跑一遍只读验收。",
      [
          c("check", "跑一遍只读接管验收（品牌/提及/情报/声量/真实性）",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--only", "str", "只跑某个区块（可多次）", repeat=True, metavar="区块"),
                     o("--out", "path", "把验收证据写到这个文件", metavar="文件")],
            examples=["daniel takeover check --brand 3690002",
                      "daniel takeover check --brand 3690002 --only brands --json"],
            returns="每个区块每项检查的结论与证据。",
            instrument="daniel_takeover_check.py"),
          c("check-writes", "含写链的接管验收（写操作）", write=True, write_stage="live",
            danger="含真实写：建一个临时品牌、改一个字段、然后删掉并双回读（用后即删）；"
                   "sov 区块是零净变化写回（默认只跑 brands）",
            options=[o("--brand", "str", "品牌名或品牌编号", required=True, metavar="品牌"),
                     o("--only", "str", "只跑某个区块的写链（可多次；默认 brands）",
                       repeat=True, metavar="区块"),
                     o("--out", "path", "把验收证据写到这个文件", metavar="文件")],
            examples=["daniel takeover check-writes --brand 3690002 --confirm",
                      "daniel takeover check-writes --brand 3690002 --only brands --confirm --json"]),
      ]),

    m("parity", "口径一致性", "核对我们的判定口径与前端页面的算法是否逐字一致。",
      [
          c("selfcheck", "核对判定口径与页面实现是否一致（离线，不联网）", options=[],
            examples=["daniel parity selfcheck", "daniel parity selfcheck --json"],
            returns="逐项检查的通过情况与差异。",
            instrument="daniel_ui_parity.py --selfcheck"),
          c("compare", "用本地抓取的页面数据做一次逐字比对（离线）",
            options=[o("--probe", "path", "页面抓取数据文件", required=True, metavar="文件"),
                     o("--report", "path", "把比对报告写到这个文件", metavar="文件")],
            examples=["daniel parity compare --probe ./probe.json --report ./parity.json"],
            returns="逐字段比对结果。",
            instrument="daniel_ui_parity.py --probe"),
      ]),

    m("account", "账号与盘点", "登录状态、可见工作区、凭据来源与数据落点。",
      [
          c("whoami", "看当前登录的是哪个账号", options=[],
            examples=["daniel account whoami", "daniel account whoami --json"],
            returns="账号邮箱、系统角色、账号状态与当前工作区编号。", route_debug="auth.me"),
          c("workspaces", "列出账号可见的工作区",
            options=[o("--with-quota", "flag",
                       "每个工作区再带上**配额读数**（品牌／检索／邮件：上限、已用、余量，"
                       "以及计划与工作区权益）；上限平台没返回时如实写「未知」，不猜、不填 0")],
            examples=["daniel account workspaces --json",
                      "daniel account workspaces --with-quota --json"],
            returns="工作区编号与名称；当前所在工作区单独标注。加了 `--with-quota` 时每个工作区"
                    "另带 `配额`（品牌／检索／邮件的上限／已用／余量／是否已满 ＋ 各项取数来源），"
                    "并给出小结「还有余量／已满／不限／上限未知」各几个。"
                    "**上限未知 ≠ 有位置**，如实登记而不是猜。",
            route_debug="auth.listMyWorkspaces + admin.listWorkspaces（配额）"),
          c("capabilities", "看这个账号的能力矩阵：每个模块能不能读、能不能写，以及为什么",
            options=[o("--refresh", "flag", "重新探测账号事实（默认优先用本地快照，10 分钟内有效）"),
                     o("--module", "str", "只看某个模块（可多次；名字见 daniel account capabilities）",
                       repeat=True, metavar="模块"),
                     o("--workspace", "int",
                       "**按这个工作区**看配额（写链的落点跟随「品牌所属工作区」，所以写之前要按"
                       "目标工作区看）；给了它就多出一段「目标工作区配额」与写链前置检查结论，"
                       "并把能力矩阵的配额轴／权益轴换成该工作区的取值。**不会切换当前工作区**",
                       metavar="工作区编号")],
            examples=["daniel account capabilities", "daniel account capabilities --json",
                      "daniel account capabilities --module lists --json",
                      "daniel account capabilities --workspace 60003 --json"],
            returns="账号事实（系统角色／账号状态／工作区计划与配额／工作区权益）＋ 12 个业务模块的"
                    "读／写结论与理由 ＋ 每一条判据轴的当前取值；结论与写命令实际执行的判据同源。"
                    "给了 `--workspace` 时另给：目标工作区的**品牌配额（上限／已用／余量）**、"
                    "计划、工作区权益、**写链前置检查结论**，以及「这一份读数是从哪条通路取的」；"
                    "上限平台没返回时**如实写「未知」**（绝不用已用数冒充上限、绝不填 0）。",
            route_debug="auth.me + auth.listMyWorkspaces + workspaces.activeFeatures"
                        "（--workspace 时配额取自 admin.listWorkspaces，逐级降级）"),
          c("audit", "导出写操作审计：每次写的时间／账号／工作区／品牌／动作／影响范围／回读结果／是否回滚",
            options=[o("--limit", "int", "只导出最近的几条", metavar="条数"),
                     o("--out", "path", "把审计导出写到这个文件", metavar="文件")],
            examples=["daniel account audit", "daniel account audit --json --limit 20",
                      "daniel account audit --out /tmp/daniel-write-audit.json"],
            returns="审计记录列表与小结（记录条数／真执行／未执行／执行失败／已回滚／最近一条）。"),
          c("credentials", "看凭据从哪来（钥匙串/环境变量/明文文件），不回显任何密码", options=[],
            examples=["daniel account credentials"],
            returns="凭据来源、掩码邮箱、钥匙串与各项降级通道的可用性。"),
          c("credentials-set", "把 Daniel 登录凭据写进本机系统钥匙串（写操作）",
            write=True, write_stage="live",
            cli_aliases=["account credentials set"],
            confirm_help="确认执行：会把凭据**真写进本机系统钥匙串**（不是干跑）；"
                         "不给 --confirm 则只做干跑，什么都不写", 
            danger="会更新本机系统钥匙串里的凭据条目（再写一次即覆盖，可逆）；"
                   "不改 Daniel 侧任何数据，**不写任何明文凭据文件**",
            write_note=[
                "本命令会**真的把凭据写进本机系统钥匙串**。不加 `--confirm` 只打印将要做什么"
                "（退出码 3），**什么都不写**；加了 `--confirm` 才写入，写完**回读确认来源是"
                "钥匙串**，并留一条可在 `daniel account audit` 里导出的记录。",
                "**凭据来源二选一**：① `--from-env` 只读环境变量 `DANIEL_EMAIL`／"
                "`DANIEL_PASSWORD`；② `--email`／`--password` 显式传入（邮箱也可退回环境变量 "
                "`DANIEL_EMAIL`，密码也可退回 `DANIEL_PASSWORD`）。两者同时给会被拒绝。",
                "**任何输出都不回显密码**：结果里只给掩码邮箱。",
                "**钥匙串写失败会非零退出并给出指引**，也不会退而写明文凭据文件；确实需要明文"
                "降级时，由你显式设置 `DANIEL_ALLOW_PLAINTEXT=1` 并自行用凭据工具写入。",
                "两种写法完全等价：`daniel account credentials set …` 与 "
                "`daniel account credentials-set …`。",
            ],
            options=[o("--email", "str", "账号邮箱（不给就退回环境变量 DANIEL_EMAIL）",
                       metavar="邮箱"),
                     o("--password", "str", "账号密码（不给就退回环境变量 DANIEL_PASSWORD）",
                       metavar="密码", secret=True),
                     o("--from-env", "flag", "只从环境变量 DANIEL_EMAIL／DANIEL_PASSWORD 读凭据"
                                             "（与 --email／--password 同时给会被拒绝）")],
            examples=["daniel account credentials set --from-env --confirm",
                      "daniel account credentials-set --email you@example.com --confirm"],
            returns="写入结果：凭据来源（应为钥匙串）、掩码邮箱、明文文件有没有被写、"
                    "以及下一步（`daniel account login --confirm`）。"),
          c("paths", "看数据落点（会话、缓存、产出、日志各在哪），以及当前账号的数据分区", options=[],
            examples=["daniel account paths", "daniel account paths --json"],
            returns="各落点绝对路径与选择理由；另给当前账号的分区（账号 → 分区目录的规则、"
                    "落点根与根的选择理由、当前生效落点、凭据钉在哪个账号）。"),
          c("list", "看当前账号 ＋ 列出本机已存账号（含各自的数据分区与钥匙串条目有无）",
            options=[],
            examples=["daniel account list", "daniel account list --json"],
            returns="当前账号（掩码）与它的分区落点、本机已存账号清单（每个账号的分区、"
                    "是否当前、钥匙串里有没有条目、最近使用时间）、以及分区规则。"
                    "**不回显任何凭据值**。"),
          c("switch", "切换当前账号：之后每条命令的会话／缓存／产出／调度改落该账号的数据分区",
            write=True, write_stage="live",
            cli_aliases=["account use"],
            confirm_help="确认执行：会**真的把当前账号指针写成本次指定的账号**（不是干跑）；"
                         "不给 --confirm 则只做干跑，什么都不写",
            danger="只写本机的一个账号指针文件并建目录（可逆：再切回去即恢复）；"
                   "**不写任何凭据、不删改任何既有数据**、不联网、不动 Daniel 侧任何数据",
            write_note=[
                "本命令把**当前账号**切到指定账号，并写在本机的账号指针文件里"
                "（`<数据落点根>/accounts/_state.json`，权限 600）。不给 `--confirm` 只打印将要"
                "做什么（退出码 3），**什么都不写**。",
                "切换之后，**会话／缓存／产出（含 `output/`）／调度（`sched/`）都落在该账号的"
                "分区目录里**（`<数据落点根>/accounts/<账号分区>/…`），两个账号的数据互不可见；"
                "分区规则只有一处实现，`daniel account paths` 会回读当前分区。",
                "**凭据按账号分条存在系统钥匙串里，切换只改「读哪一条」** —— 切回老账号"
                "**不需要重新输入密码**；本命令**不写、不改、不删任何凭据**。",
                "**不迁移、不删除任何既有数据**：切换只新增「本账号的那一行」＋建目录；"
                "既有安装（没有切过账号时）落点仍是原来的根目录，一个字都不变。",
                "目标账号在本机没有可复用凭据（钥匙串里没有条目、环境变量也不是它）时，"
                "**按用户错误报（退出码 2）**并指向 `daniel account credentials set`。",
            ],
            options=[o("账号", "str", "要切换到的账号邮箱；也支持 `--to <邮箱>` 写法",
                       metavar="邮箱"),
                     o("--to", "str", "与位置参数 `<账号>` 等价的写法", metavar="邮箱"),
                     o("--clear", "flag", "取消当前账号：回到根落点（切账号之前那个区域，"
                                          "既有数据一直在那里，本命令不搬家、不删除）")],
            examples=["daniel account switch you@example.com --confirm",
                      "daniel account list --json",
                      "daniel account switch you@example.com --confirm --json",
                      "daniel account switch --clear --confirm"],
            returns="切换结果：切换前后的当前账号（掩码）与生效落点、新建的分区目录、"
                    "以及回读对账四条（指针、分区就绪、上一个账号数据未被动、凭据条目仍在）。"),
          c("login", "登录并刷新会话（写操作／落地会话文件）", write=True,
            write_stage="live",
            confirm_help="确认执行：会**真的登录并刷新本机会话文件**（不是干跑）；"
                         "不给 --confirm 则只做干跑，什么都不写",
            danger="会重写数据落点里的会话文件（权限 600；重新登录即可刷新，可逆）",
            write_note=[
                "🔴 **给人用的主路径是「浏览器授权登录」**：`daniel account login --browser --confirm` ——"
                "打开 Daniel 登录页（`https://daniel-agent.com/auth`），你在**页面上**完成登录，"
                "再把浏览器里的会话粘回 CLI，CLI **先校验、通过后才落盘**。"
                "这条路上**CLI 绝不向你要账号密码**，命令里也不该出现密码。",
                "**无头／CI 的备用路**（**不是给人用的主路径**）：环境变量 "
                "`DANIEL_EMAIL`／`DANIEL_PASSWORD` ＋ `--confirm`（不带 `--browser`），"
                "用凭据直接换会话。",
                "本命令会**真的写本机会话文件**（`DANIEL_HOME/session/session.json`，权限 600）。"
                "不加 `--confirm` 只打印将要做什么（退出码 3），**什么都不写**。",
                "不改任何 Daniel 业务数据、不触发任何采集。",
                "密码路（不带 `--browser`）：已有有效会话时默认**复用**（不重复登录）；"
                "要强制重新登录加 `--force`。",
                "**回读失败的三种情况给三种不同的人话**（可区分）：格式不对／服务端不认／"
                "服务端不可达；退出码沿用同一张三档表：0＝通过，1＝无 token 或 token 被拒（去登录），"
                "2＝服务端不可达（稍后重试）。会话值**绝不回显**。",
            ],
            options=[o("--browser", "flag", "**主路径**：打开 Daniel 登录页，在页面上登录后"
                                           "把会话粘回来（不向你要账号密码）"),
                     o("--no-open", "flag", "与 --browser 同用：只打印登录页地址，"
                                            "不调用系统浏览器（无图形界面／远程环境）"),
                     o("--session-cookie-stdin", "flag",
                       "与 --browser 同用：从标准输入读会话值（管道用；"
                       "非交互式终端必须用它，否则无法等待粘贴）"),
                     o("--force", "flag", "强制重新登录，不复用已有会话（仅密码路有效）")],
            examples=["daniel account login --browser",
                      "daniel account login --browser --confirm",
                      "daniel account login --browser --confirm --session-cookie-stdin < 会话值文件",
                      "daniel account login --confirm        # 无头／CI 备用路（不是主路径）",
                      "daniel account login --confirm --force --json"],
            returns="登录结果：回读到的账号（掩码）、系统角色与账号状态、会话文件落点与权限、"
                    "凭据来源（浏览器路为「浏览器授权」），以及回读校验是否通过"
                    "（拿不到真实账号即判失败）。**不回显任何会话值或密码**。"),
      ],
      self_test="跑本模块自带的自检（多账号分区的机器可验判据：纯函数组验分区规则的确定性／"
                "不撞车／可逆／不越界；端到端组在临时根 ＋ 假钥匙串上让两个账号来回切 2 次，"
                "验①分区不串（A 的产出在 B 的分区里看不见）②切回免重输（凭据按账号分条且被钉到"
                "当前账号，两条密码串都不出现在输出里）③paths／list 如实回读当前分区"
                "④切换不删改上一个账号的数据）；反例：目标账号没有可复用凭据必须被拒（退出码 2）、"
                "不带 --confirm 必须退出码 3 且不动指针。全程离线、只写临时目录）。"),

    m("keywords", "检索词清单", "把「检索词清单」这条业务工序做成可调用、可回归的只读检查："
                              "读入一份词表文件，按语料里的判据逐条校验，给出「判据 → 来源」、"
                              "逐条违规项，以及**本命令判不了、必须人工过**的判据清单。",
      usage_note="本模块**只读本地文件**：不联网、不查任何账号与品牌档案、不写任何文件、"
                 "不触发任何采集任务。它是「检索词清单」这条工序的可调用入口，"
                 "判据来源是随包分发的业务语料（发现阶段 §2.1 检索词矩阵方法论与词量标准／"
                 "§2.2 排除规则／§2.3 呈现标准）与模板 `_TEMPLATE-kol-search-matrix.md`。"
                 "\n\n词表格式（`--file` 支持的范围，三种任选）：\n"
                 "  · md：产出标准 v2 的类别表结构 —— `### 类别 N ｜ 名称` 一行一个类别，"
                 "每类一张表，表内 **Tag／长句／短尾词／条件词** 四行（无条件的类别省略条件词行）；"
                 "搜索词格内用逗号或换行分隔（长句用 <br> 或换行分隔，一条一行）；"
                 "\n  · csv：表头 `类别,类型,检索词`，一行一个词面；"
                 "\n  · json：`{\"检索词\": [{\"类别\": …, \"类型\": …, \"检索词\": …}, …]}`"
                 "（顶层直接给这个数组也可以），或 "
                 "`{\"类别\": [{\"类别\": …, \"Tag\": [...], \"短尾词\": [...], "
                 "\"长句\": [...], \"条件词\": [...]}]}`。"
                 "\n  类型取值固定四种：`Tag`／`长句`／`短尾词`／`条件词`。",
      commands=[
          c("check", "校验一份检索词清单：格式、十类别齐备、词量、重复、负向词、装饰符号、"
                     "地域锚点位置、计数自洽（只读）",
            options=[o("--file", "path", "词表文件。支持三种格式：md（类别表结构）／csv（表头 "
                                         "类别,类型,检索词）／json（检索词数组）；支持范围与逐格写法见 "
                                         "`daniel keywords --help` 的「词表格式」。相对路径会从当前目录"
                                         "逐级向上找，也可以直接给绝对路径",
                       required=True, metavar="文件"),
                     o("--brand", "str", "词表归属品牌（如 3690002）：**只作归属标注**，"
                                         "本命令不联网、不查品牌档案",
                       metavar="品牌"),
                     o("--only", "str", "只跑指定的判据（可多次；编号见结果的「判据」清单，"
                                        "例如 FMT／CAT／CATQ／TOTAL／DUP／COND／DECO／NEG／BAN／"
                                        "SENT／REGION／COUNT）",
                       repeat=True, metavar="判据编号"),
                     o("--rows", "int", "交付件清单最多展示多少条（0＝全量，默认 0）；"
                                        "被截断时逐行标注「样本模式：仅展示前 N 条，全量 X 条」",
                       default=0, metavar="条数"),
                     o("--strict-exit", "flag", "有违规时按「当场拦下」处理：退出码 2"
                                                "（默认档有违规仍退出码 0，结论看结果里的「合规」字段）")],
            examples=["daniel keywords check --file docs/marketing/kol/"
                      "2026-09-halliday-g2-kol-search-matrix-v4.md --brand 3690002",
                      "daniel keywords check --file 我的词表.md --json",
                      "daniel keywords check --file 我的词表.md --only DUP --json",
                      "daniel keywords check --file 词表.csv --strict-exit"],
            returns="词表规模（类别数、各类型条数、合计）、逐条判据的结论与**来源**、"
                    "逐条违规项（类别／类型／词面／违规说明／来源）、提示（不计违规）、"
                    "**需人工判断**的判据清单、以及交付件「检索词清单」（一条词一行，"
                    "带「是否合规」与「命中判据」）。计数口径：结果里的 `count` ＝ 违规项数"
                    "（0 表示全合规），全量词量见「规模」。退出码与结论是两件事："
                    "**默认档**即便查出违规也退出码 0（结果里 `ok=false`、`合规=false`、"
                    "「违规」逐条列出），适合「跑一遍看结论＋用判据断言违规数 0」的场合；"
                    "**加 --strict-exit** 则有违规即退出码 2（适合「必须当场拦下」的场合）。",
            description="校验一份检索词清单（只读）。判据全部标注来源；不可机械化的判据"
                        "（每个词可溯来源、锚点法则、扩圈迁移可达性、反向抽检、扩圈双闸门、"
                        "词量回测、锚点负向语境、改版只增不减）显式单列「需人工判断」，"
                        "不会假装能判。词表格式：md＝产出标准 v2 的类别表结构"
                        "（`### 类别 N ｜ 名称` + 每类一张表，表内 Tag／长句／短尾词／条件词 四行，"
                        "词面用逗号或换行分隔，长句用 <br> 或换行分隔）；"
                        "csv＝表头 `类别,类型,检索词`，一行一个词面；"
                        "json＝`{\"检索词\": [{\"类别\": …, \"类型\": …, \"检索词\": …}, …]}`"
                        "（顶层直接给这个数组也可以），或 `{\"类别\": [{\"类别\": …, "
                        "\"Tag\": [...], \"短尾词\": [...], \"长句\": [...], \"条件词\": [...]}]}`。"
                        "类型取值：Tag／长句／短尾词／条件词。",
            exit_codes=[EXIT_OK, EXIT_USAGE, EXIT_INTERNAL]),
      ],
      self_test="跑本模块自带的自检（正控：合规样本必须通过；退化正控：故意不合规的样本必须被拦下"
                "且逐条报出；另含格式等价性与反例；只读、不联网）"),

    m("skills", "业务语料", "看**随包分发**的业务语料（KOL 能力域）：有哪些能力域、"
                          "每束覆盖哪些源节、判据原文在哪一段。",
      usage_note="语料**随本 CLI／MCP 服务一起分发**（`data/daniel-cli/mcp/corpus/`），"
                 "按**包自身位置**定位 —— 不读 `~/.agents/skills/`、不看当前工作目录、"
                 "不依赖 `.kol-tools/`。因此把 `data/daniel-cli/` 单独拷到一台新机器上，"
                 "这两条命令照样能跑（这正是「另一台机器只注册 MCP 就自动获得语料」的判据）。"
                 "\n\n**分片读法（必须遵守）**：整束合计约 995 KB，一次灌进上下文会把宿主的"
                 "上下文淹掉。所以：不给 `--section` 只回**导航**（元信息＋切片清单），"
                 "不回正文；`--section 0` 回导航件 SKILL.md；`--section N` 回第 N 个切片的"
                 "**逐字正文**；正文超过 `--max-bytes` 时自动分片，用 `--offset` 续读。"
                 "拿不准该读哪一片时，先用 `--grep` 只回命中行定位。",
      self_test="跑本模块自带的自检（正控：8 个能力域齐、版本各束一致、逐束重算 sha256 与清单比对必须全等；真阴性：把语料根指到临时副本并篡改一处，必须被报为「不一致」；漂移门禁：源束 ↔ 包内语料逐文件比对，**分发环境无源束时显式记为「跳过」而不是通过**；只读：不联网、不写任何文件）。",
      commands=[
          c("list", "列出随包分发的全部能力域（摘要、语料版本、前置条件、整束 sha256）",
            options=[],
            examples=["daniel skills list", "daniel skills list --json"],
            returns="语料版本、落点与定位方式、总量（字节数／文件数／切片数）、完整性结论，"
                    "以及每个能力域的域键、中文标签、摘要、前置条件（何时加载）、"
                    "切片数、字节数、整束 sha256 与**逐文件 sha256 清单**。"),
          c("read", "读一束语料：先看切片清单，再按切片号读判据原文（自动分片，可续读）",
            options=[o("--name", "str", "能力域（域键，见 `daniel skills list`）",
                       required=True, metavar="域"),
                     o("--section", "int", "切片号：0 ＝ 导航件 SKILL.md，1…N ＝ 第 N 个切片；"
                                           "不给则只回导航与切片清单", metavar="切片号"),
                     o("--grep", "str", "在选定范围里搜词，只回命中行（带切片号与行号）——"
                                        "用来先定位再精读，避免整段灌入", metavar="关键词"),
                     o("--max-bytes", "int", "本次正文最多回多少字节（0 ＝ 不限）",
                       default=48000, metavar="字节数"),
                     o("--offset", "int", "从正文的第几个字节开始（配合 --max-bytes 续读）",
                       default=0, metavar="偏移"),
                     o("--max-hits", "int", "`--grep` 最多回多少行命中（0 ＝ 不限）",
                       default=60, metavar="行数")],
            examples=["daniel skills read --name kol-discovery --json",
                      "daniel skills read --name kol-discovery --section 1 --max-bytes 20000",
                      "daniel skills read --name kol-screening --section 0",
                      "daniel skills read --name kol-intelligence --grep 数据红线"],
            returns="模式（导航／正文／检索）＋ 语料版本与完整性 ＋ "
                    "导航模式给切片清单、正文模式给分片信息（本次字节／总字节／下一次偏移）与正文、"
                    "检索模式给命中行清单。**切片正文是逐字切片，不改写任何判据。**"),
      ]),

    m("playbook", "工序契约", "把一条工序写成声明式契约：列出、看、校验、跑一份、引擎自证。"
                             "契约里的判据与门禁都是可执行断言，不是文档。",
      [
          c("list", "列出契约目录里的全部契约（含示例与退化样本）", options=[],
            examples=["daniel playbook list", "daniel playbook list --json"],
            returns="每份契约的编号、名称、相对路径、是否示例、是否含写步骤、期望结果。"),
          c("show", "看一份契约的完整内容与校验结论（字段同 03 号草案口径）",
            options=[o("name", "str", "契约编号或文件名（位置写法，也可写 `--name 契约`）",
                       required=True, metavar="契约"),
                     o("--name", "str", "与位置写法等价（`daniel playbook show <契约>`）",
                       metavar="契约")],
            examples=["daniel playbook show --name engine-smoke",
                      "daniel playbook show engine-smoke"],
            returns="规范化后的契约全文（输入／前置／步骤／判据／门禁／交付件schema／自检／失败模式）、"
                    "落点路径与校验结论。"),
          c("validate", "校验契约：字段齐备、步骤只引用已声明的命令与参数、门禁五道齐备",
            options=[o("name", "str", "只校验某一份（位置写法，不给则校验目录里全部）",
                       metavar="契约"),
                     o("--name", "str", "与位置写法等价（`daniel playbook validate <契约>`）",
                       metavar="契约")],
            examples=["daniel playbook validate", "daniel playbook validate engine-smoke --json"],
            returns="每份契约的逐项检查结论与问题明细（引用幻觉命令、门禁缺项、装饰性声明都会报出来）。"),
          c("run", "跑一份契约：判据与门禁变成可执行断言，跑完出自检报告（含计数自洽）",
            write=True,
            write_stage="sandbox",
            read_only_dynamic=True,
            read_only_note="是否只读取决于契约是否含写步骤：纯读链契约只读；含写步骤的契约只写"
                           "本次运行的沙箱文件（不碰任何 Daniel 写路由）。运行时信封的 readOnly "
                           "会如实给出。",
            write_note=[
                "本命令按**写操作**登记：契约里**可能含写步骤**（写步骤走"
                " dry-run → --confirm → 执行 → 回读校验 三段门禁）。",
                "只有**契约里真的声明了写步骤**时才需要 --confirm；纯读链契约直接跑即为退出码 0。",
                "本工序的写类动作只有「离线假动作」（只写本地沙箱内的文件），"
                "**不碰任何 Daniel 写路由**；",
                "不带 --confirm 时写步骤只打印计划、不执行任何写（退出码 3）。",
                "沙箱处置：默认自建的临时沙箱**跑完即清理**；加 --keep（或设 "
                "DANIEL_PLAYBOOK_SANDBOX）则保留，报告里的「运行.沙箱保留」会写明是哪一种。",
            ],
            options=[o("name", "str", "契约编号或文件名（位置写法，也可写 `--name 契约`）",
                       required=True, metavar="契约"),
                     o("--name", "str", "与位置写法等价（`daniel playbook run <契约>`）",
                       metavar="契约"),
                     o("--sample", "flag", "样本模式（v0.1 的默认模式；本开关只为显式表达，可省略）"),
                     o("--full", "flag", "全量口径（v0.1 不实现：给了就直接报错退出）"),
                     o("--keep", "flag", "保留本次自建的临时沙箱（默认为跑完即清理；"
                                         "用户指定的落点本来就不清理）"),
                     o("--limit", "str", "覆盖契约声明的样本上限，写成「上限名=整数」；可多次",
                       repeat=True, metavar="上限=值"),
                     o("--input", "str", "覆盖契约声明的输入，写成「输入名=值」；可多次",
                       repeat=True, metavar="输入=值"),
                     o("--out", "path", "把完整运行报告另外写到这个文件", metavar="文件")],
            examples=["daniel playbook run engine-smoke --json",
                      "daniel playbook run --name engine-smoke --limit 行数上限=8",
                      "daniel playbook run engine-write-demo --confirm --json",
                      "daniel playbook run engine-write-demo --keep --json"],
            returns="运行报告：契约与模式、输入与上限、沙箱处置（保留／已清理）、"
                    "前置／步骤／判据／门禁／自检五组明细、交付件落点与行数、写动作台账、"
                    "计数自洽与结论。"),
          c("deliver", "出件：按契约里声明的出件模板产出交付物并落到本地目录（出件前自动跑五条自检）",
            options=[o("name", "str", "契约编号或文件名（位置写法，也可写 `--name 契约`）",
                       required=True, metavar="契约"),
                     o("--name", "str", "与位置写法等价（`daniel playbook deliver <契约>`）",
                       metavar="契约"),
                     o("--out", "path", "交付物落点目录；不给则落 `$DANIEL_HOME/output/<契约id>/`"
                                        "（落点统一由 daniel_paths 解析，不写代码目录）",
                       metavar="目录"),
                     o("--limit", "str", "覆盖契约声明的样本上限，写成「上限名=整数」；可多次",
                       repeat=True, metavar="上限=值"),
                     o("--input", "str", "覆盖契约声明的输入，写成「输入名=值」；可多次",
                       repeat=True, metavar="输入=值")],
            examples=["daniel playbook deliver high-performance-video-list",
                      "daniel playbook deliver high-performance-video-list --json",
                      "daniel playbook deliver high-performance-video-list --out /tmp/交付物"],
            returns="出件报告：交付物落点与文件名、格式、行数与列数、**sha256**、"
                    "五条出件自检的逐条结论、关键桶计数、计数对账（主表行数 == 文件行数、"
                    "入池 ≥ 出件及差额解释）、多口径阶梯、说明与口径附表的落点与 sha256。"
                    "**出件自检不过 → 非零退出且落点上不产出任何文件**（逐条点出违规行）。",
            local_write_note="**会往本机出件落点写文件、不写 Daniel 远端**：交付物落在本机"
                             "`$DANIEL_HOME/output/<契约id>/`（`--out` 可覆盖该落点），"
                             "**不改任何 Daniel 数据、不触发采集、不对外发信**；出件自检不过时"
                             "非零退出且**落点上不产出任何文件**。宿主侧**可直接执行**"
                             "（不是确认单工具）：这就是「CLI ＋ MCP 接入即交付物」里 MCP 侧的"
                             "出件通道 —— 调用一次会真在本机产出交付物。"),
          c("selfcheck", "契约引擎自证：把目录里每份契约按它声明的期望各跑一遍（含退化样本）",
            options=[o("--require-network", "flag",
                       "把「需要联网」契约在联网探测失败时改判为失败（不给则记「跳过（需要联网）」、"
                       "不计入未通过项；等价环境变量 DANIEL_PLAYBOOK_REQUIRE_NETWORK=1）")],
            examples=["daniel playbook selfcheck", "daniel playbook selfcheck --json",
                      "daniel playbook selfcheck --require-network --json"],
            returns="逐契约逐路径的「期望 vs 实际」对照、计数自洽／读链零写／明细齐备三条不变量，"
                    "外加「跳过（需联网）」一栏（跳过 ≠ 通过）。"),
      ]),

    m("sched", "调度层", "长任务的**断点续跑**与**采集排队 ＋ 限流退避**：任务能中断、能续跑、"
                        "不重跑已完成的取数；取数经统一队列（并发上限可配）并带 429／5xx 指数退避；"
                        "终态四态分明（成功／失败／超时／配额耗尽）。",
      usage_note="**这一层解决的是长任务的三件事**（用户最初的痛点就在这：429／终态误判／半途失败）："
                 "\n\n① **断点续跑** —— 任务状态与每一步的结果（含结果指纹）落 `$DANIEL_HOME/sched/`，"
                 "**每步立刻落盘**；中断或失败后再跑，已完成的步骤按结果指纹校验后**跳过**，"
                 "不重复取数。"
                 "\n\n② **排队与退避** —— 步骤执行前先经**统一队列**准入（并发上限默认 1，保守；"
                 "用 `--concurrency` 或环境变量 `DANIEL_SCHED_CONCURRENCY` 可配），429／5xx 按"
                 "**指数退避 ＋ 上限 ＋ 抖动**重试，**每次重试都往 stderr 打一行**（不许静默重试到超时）。"
                 "\n\n③ **终态分明** —— `成功`／`失败`／`超时`／`配额耗尽` 四个词就是四个终态；"
                 "只有全部步骤成功才记「已完成」，被中断是「进行中」——**都不当成成功**，且非成功终态"
                 "一律非零退出。"
                 "\n\n**只读与红线**：本模块不做任何 Daniel 写、不触发任何采集 —— 步骤里能引用的命令"
                 "一律限定为 `schema.py` 声明的**只读**命令（`search submit`／`mentions run`／"
                 "`sov run-exposure`／`route sweep` 这类写命令在校验期即被拒绝），取数地址默认"
                 "**只允许回环地址**（假端点／夹具；要指向远端须显式设 `DANIEL_SCHED_ALLOW_REMOTE=1`）。"
                 "这四个触发类命令的**准入点就是这条队列**（`sched queue` 可查）；它们的真实执行"
                 "在本工序仍是 `gated`（只到干跑）。"
                 "\n\n**落点与状态**：全部落 `$DANIEL_HOME/sched/`（走 `daniel_paths`，惰性解析，"
                 "**不写代码目录**）：`tasks/<任务>.json`（检查点）、`tasks/<任务>.result.json`"
                 "（到达终态时的结果，可逐字比对）、`queue.json`（队列）。本模块的命令**只写这些本地"
                 "状态文件**，对 Daniel 是只读的。",
      commands=[
          c("run", "跑一个任务：有检查点就从检查点**续跑**（已完成的步骤不重复取数），"
                   "没有就按全新任务跑（不报错）",
            options=[o("任务", "str", "任务编号（位置写法，也可写 `--task <编号>`；"
                                    "不给就用规格里的 `id`）", metavar="任务编号"),
                     o("--task", "str", "与位置写法等价（`daniel sched run <任务编号>`）",
                       metavar="任务编号"),
                     o("--spec", "path", "任务规格 JSON（新建任务必填；续跑时可省略 —— "
                                         "默认用任务目录里存的规格副本）", metavar="文件"),
                     o("--concurrency", "int", "本次的并发上限（默认取环境变量 "
                                               "DANIEL_SCHED_CONCURRENCY，再退到 1＝保守）",
                       metavar="条数"),
                     o("--retry", "int", "覆盖「重试次数」上限（默认 4）", metavar="次数"),
                     o("--deadline", "float", "覆盖单步时限（秒，含退避等待；默认 120）",
                       metavar="秒")],
            examples=["daniel sched run --spec /tmp/任务.json --json",
                      "daniel sched resume 我的长任务 --json",
                      "daniel sched run 我的长任务 --concurrency 2 --retry 3 --json"],
            cli_aliases=["sched resume"],
            returns="任务状态（成功／失败／超时／配额耗尽／进行中）、进度（总步骤／已完成／未完成／"
                    "失败）、逐步明细（状态／尝试次数／耗时／终态原因／结果指纹／是否续跑跳过）、"
                    "结果指纹与落点（状态文件／规格文件／结果文件）、本次跳过（已完成）的步骤。"),
          c("retry", "重试未成功的步骤：已成功且结果指纹一致的步骤一律不动（**幂等** —— "
                     "重试不会产生重复记录、也不会改变结果指纹）",
            options=[o("任务", "str", "任务编号（位置写法，也可写 `--task <编号>`）", metavar="任务编号"),
                     o("--task", "str", "与位置写法等价", metavar="任务编号"),
                     o("--spec", "path", "任务规格 JSON（默认用任务目录里存的规格副本）",
                       metavar="文件"),
                     o("--concurrency", "int", "本次的并发上限", metavar="条数"),
                     o("--retry", "int", "覆盖「重试次数」上限", metavar="次数"),
                     o("--deadline", "float", "覆盖单步时限（秒）", metavar="秒")],
            examples=["daniel sched retry 我的长任务 --json",
                      "daniel sched retry --task 我的长任务 --retry 5 --json"],
            returns="与 `run` 同一份报告；`续跑.本次跳过（已完成）` 列出被跳过的步骤。"
                    "**重复重试同一份规格，结果指纹与步骤条数逐字不变。**"),
          c("status", "看任务与进度：进行中／已完成／失败／超时／配额耗尽（给任务编号则看逐步明细）",
            options=[o("任务", "str", "任务编号（位置写法，也可写 `--task <编号>`；"
                                    "不给则列出全部任务）", metavar="任务编号"),
                     o("--task", "str", "与位置写法等价", metavar="任务编号")],
            examples=["daniel sched status", "daniel sched status --json",
                      "daniel sched status 我的长任务 --json"],
            returns="任务列表（状态／进度／更新时间／结果指纹／状态文件）与各状态计数；"
                    "给编号时返回该任务的逐步明细与落点。**「进行中」不等于「已完成」。**"),
          c("queue", "看统一队列：并发上限（含来源）、受管触发类命令、逐条入队记录、受管清单自证",
            options=[],
            examples=["daniel sched queue", "daniel sched queue --json"],
            returns="并发上限与来源、队列文件落点、队列条目（排队中／运行中／终态）、"
                    "受管触发类命令清单（与 `schema.py` 的对账结论）、远端取数开关状态。"),
      ]),

    m("connect", "接入", "把 Daniel 接进宿主（Cursor／Codex）：**一条命令**自己算路径、幂等合并写入、"
                         "端到端自检、可卸载 —— 换机器、换宿主都是同一条命令。",
      options=[o("--host", "choice", "要接入／检查哪个宿主", choices=CONNECT_HOSTS, metavar="宿主"),
               o("--confirm", "flag", "确认执行这次写；不给则只做干跑（先给逐行 diff，不写任何文件）"),
               o("--dry-run", "flag", "只打印将要做什么（默认行为，可省略）")],
      usage_note="**为什么要有这个模块**：在这之前，「接入」是**用户手工往宿主配置里抄一段带本机"
                 "绝对路径的片段**（Cursor 与 Codex 两套格式，还要自己「合并不要覆盖」）—— 换一台"
                 "电脑、换一个宿主就得重来一遍，而且没有任何命令能回答「这套接入到底通不通」。"
                 "\n\n**接入步骤只有一条命令**（换机器、换宿主，接入都是它）：\n\n"
                 "    daniel connect --host <宿主> --apply --confirm\n\n"
                 "三条纪律：① **路径一律运行时现算**（解释器／服务入口／工作目录／数据落点），"
                 "配置里不出现任何写死的路径，所以换机器不用改任何东西；② **只动本产品那一条** ——"
                 "Cursor 保留 `mcpServers` 里其它 server 与无关字段，Codex 保留 `config.toml` 里"
                 "其它表与注释，重复执行结果不变，`--uninstall` 只删自己那一条；"
                 "③ **写前落快照、写后回读对账**（sha256 ＋ 逐项核对 ＋ 审计留痕），"
                 "因此每一步都可复算、可回滚。"
                 "\n\n**判断「通不通」不用打开宿主**：`daniel connect --doctor` 端到端断言"
                 "（包完整性 → server 起得来 → 工具数 == 声明数 → 只读命令取到真实数据 → "
                 "每个宿主的配置与路径），任一项不过即退出码非 0 并给一行可执行修法。"
                 "\n\n支持的宿主：`cursor`（`~/.cursor/mcp.json`）与 `codex`（`~/.codex/config.toml`）。"
                 "**其它宿主本票未做** —— `--list` 会如实说「未支持」，不给没实测过的片段。",
      commands=[
          c("list", "看本机支持哪些宿主、各自接没接上（配置文件、本产品条目数、路径是否指向当前包）"
                    "（只读）",
            options=[o("--host", "choice", "只看某个宿主", choices=CONNECT_HOSTS, metavar="宿主")],
            examples=["daniel connect --list", "daniel connect list --json",
                      "daniel connect --list --host codex --json"],
            returns="本次**现算**出来的路径（解释器／服务入口／工作目录／数据落点，各带来源）、"
                    "每个宿主一行（配置文件路径、本机是否有该宿主的痕迹、本产品条目数、"
                    "配置文件里其它 server、结论「已接入（指向当前包）／未接入（附原因）」）、"
                    "尚未适配的宿主与原因（缺该宿主的配置片段生成器；**CLI 与能力层 skill 与宿主无关，不受此影响**）。**检测不到宿主就写「未检测到」，不留空壳。**"),
          c("print", "只打印该宿主应写入的完整片段（不改任何文件），供审阅或手工粘贴；"
                     "与你手工抄不同，这一份的路径是本机现算的",
            options=[o("--host", "choice", "要打印哪个宿主的片段", choices=CONNECT_HOSTS,
                       required=True, metavar="宿主")],
            examples=["daniel connect --host cursor --print",
                      "daniel connect --host codex --print",
                      "daniel connect --host cursor --print --json"],
            returns="该宿主配置里本产品那一段的**逐字原文**与它的 sha256。非 `--json` 时 stdout "
                    "**只有这一段**（可以直接重定向成文件，或交给 "
                    "`mcp/client_check.py --snippet <文件>` 验证）；说明性文字走 stderr。"),
          c("apply", "把本产品接入该宿主：自己算路径并**幂等合并**进宿主配置（保留其它 server、"
                     "其它表与注释），写前落快照、写后回读对账（写操作）",
            write=True, write_stage="live",
            danger="会改写你本机的宿主配置文件（只在本产品那一条上动；写前落快照，"
                   "可用 --uninstall 还原）",
            confirm_help="确认把本产品那一条合并进宿主配置（只动这一条；写前落快照、写后回读对账）",
            options=[o("--host", "choice", "要接入哪个宿主", choices=CONNECT_HOSTS,
                       required=True, metavar="宿主")],
            examples=["daniel connect --host cursor --apply",
                      "daniel connect --host cursor --apply --confirm",
                      "daniel connect apply --host codex --confirm --json"],
            returns="干跑（不带 --confirm）：将写入的片段、**逐行 diff**（`-` 删哪行／`+` 增哪行）、"
                    "改动前后 sha256、影响范围、对账结论（其它 server／其它表是否逐字节未动），"
                    "退出码 3；带 --confirm：上述内容 ＋ 快照落点 ＋ 回读对账逐项结论 ＋ "
                    "审计记录落点。**内容已一致时不改动文件**（幂等，sha256 不变）。"),
          c("uninstall", "把本产品那一条从该宿主配置里删掉（其它 server、其它表与注释逐字节不动；"
                         "可逆 —— 写前同样落快照）（写操作）",
            write=True, write_stage="live",
            danger="会改写你本机的宿主配置文件（只删本产品那一条；写前落快照）",
            confirm_help="确认从宿主配置里删掉本产品那一条（其它内容不动；写前落快照）",
            options=[o("--host", "choice", "要从哪个宿主卸载", choices=CONNECT_HOSTS,
                       required=True, metavar="宿主")],
            examples=["daniel connect --host cursor --uninstall",
                      "daniel connect --host cursor --uninstall --confirm",
                      "daniel connect uninstall --host codex --confirm --json"],
            returns="干跑：将删掉的那一段与**逐行 diff**、改动前后 sha256、退出码 3；"
                    "带 --confirm：快照落点、回读对账（本产品条目已为 0、其它 server／其它表仍在）、"
                    "审计记录落点。**这个文件里没有本产品条目时不做任何改动。**"),
          c("doctor", "端到端断言「这套接入通不通」：包完整性 → MCP server 起得来（复用既有仪器）→ "
                      "工具数 == schema 声明数 → 真跑一条只读命令取到真实数据 → 每个宿主：配置存在、"
                      "本产品条目恰好一条、路径指向当前包（只读）",
            options=[o("--host", "choice", "只检查某个宿主", choices=CONNECT_HOSTS, metavar="宿主")],
            examples=["daniel connect --doctor", "daniel connect --doctor --json",
                      "daniel connect --doctor --host codex --json"],
            returns="逐项结论（每项带**证据**；未过的项带**一行可执行修法**）、本次现算的全部路径、"
                    "总结论与退出码（**任一项不过即退出码非 0**）。它**不需要打开宿主**也能回答"
                    "「接入对不对」——宿主里「会话真的跑通」仍由你自己做，但那一步只是"
                    "「宿主认不认这份配置」，不是判据的唯一来源。"),
      ],
      flag_commands={"--list": "list", "--print": "print", "--apply": "apply",
                     "--uninstall": "uninstall", "--doctor": "doctor"}),

    m("pack", "出包", "把 CLI 打成一个**可交付的能力包**：一条命令出包、一条命令自检"
                      "（包内可跑／包内接入可用／干净／无写死路径／差集对账）。",
      options=[],
      usage_note="**为什么要有这个模块**：交付形态是「CLI ＋ MCP 接入即交付物」，但在这之前，"
                 "「把 CLI 装到另一台机器」只能**手工拷贝** `data/daniel-cli/**`（拷多拷少全凭经验），"
                 "而且没有任何东西能回答「**这一份拷贝是不是完整、干不干净**」"
                 "（有没有夹带凭据、你的数据、本机绝对路径、内部台账）。"
                 "\n\n**两条命令**（出包是写操作，默认干跑）：\n\n"
                 "    daniel pack --out <目录> --confirm        # 出一份包（包根是 <目录>/daniel-bot）\n"
                 "    daniel pack --check <包目录>              # 只读自检：五条断言逐条给结论\n\n"
                 "自检的五条断言：**① 包内可跑**（临时 HOME ＋ 哨兵钥匙串服务下跑 `--version` 与 "
                 "`schema --check` 10/10）｜**② 包内接入可用**（同环境跑 `connect --apply` 与 "
                 "`connect --doctor`，doctor 的第 ① 项就是「包完整性」）｜**③ 干净**（凭据与令牌复用"
                 "既有断言器扫描 ＋ 本机绝对路径 0 命中 ＋ legacy 凭据／会话文件按名字点名）｜"
                 "**④ 无写死绝对路径**（包内 `.py` 不出现本机路径）｜**⑤ 差集对账**"
                 "（包内文件 ⊆ 源目录，且 `源 − 包 == 排除清单` 逐项可复算，同时报文件数与总字节）。"
                 "\n\n**排除清单不靠猜**：每条都是「路径模式 ＋ 理由」，真源在 "
                 "`daniel_cli/pack/spec.py`（必须包含 5 条／必须排除 26 条／点名排除 22 条），"
                 "候选面与排除集都由规则**算出来**，逐项清单落在包目录**之外**的 "
                 "`<目录>/_PACK_MANIFEST.json`（包内必须严格满足「包内文件 ⊆ 源目录」）。"
                 "\n\n**诚实边界**：① 包内不含任何凭据与你的数据（这是本模块的首要用途），"
                 "但也**不含** `.kol-tools/` 里那 141 个一票一用的业务仪器与检查器；"
                 "② `compare_hosts.py` 的正控回归对（`mcp/_fixtures/cross-host/*.json`）**含本机绝对路径**，"
                 "按「干净优先」被排除 ⇒ 包内那一条 `--self-test` 跑不了（已知边界，见 README）；"
                 "③ 「包内可跑」这一条必须在**源目录之外**的临时目录里跑，否则可能读到源目录的明文凭据"
                 "而变成假绿 —— 本命令自己会拷一份到临时目录再跑。",
      commands=[
          c("out", "出一条可交付的能力包：按声明式源清单规则逐文件复制源目录里的"
                   "「必须包含」集，并对结果做回读对账（写操作）",
            write=True, write_stage="live",
            danger="会在 `<你给的目录>/daniel-bot` 写入一份完整拷贝（实测 163 个文件／约 4.1 MB）；"
                   "**包目录必须为空**，且**不得位于工作区之内**（本命令会拒绝在工作区里出包 —— "
                   "往仓库里出包会污染门禁扫描面与仪器台账）",
            confirm_help="确认把这份包写到 `<目录>/daniel-bot`（逐文件复制；包内不含任何凭据与"
                         "你的数据；出包清单落在包目录之外）",
            options=[o("out_dir", "path", "包写到哪个目录（位置写法，也可写 `--out <目录>`）；"
                                         "包根是它下面的 `daniel-bot/`",
                       required=True, metavar="目录"),
                     o("--out", "path", "与位置写法等价（`daniel pack --out <目录>`）", metavar="目录"),
                     o("--source", "path", "源目录（默认＝本 CLI 所在的工作区根）", metavar="目录")],
            examples=["daniel pack --out /tmp/交付包",
                      "daniel pack --out /tmp/交付包 --confirm",
                      "daniel pack out --out /tmp/交付包 --confirm --json"],
            cli_aliases=["pack --out"],
            returns="干跑（不带 --confirm）：这次的**计数**（包含 N 个文件／M 字节、排除 K 项）、"
                    "规则表（必须包含／必须排除／点名排除，逐条带理由）、排除样例、包根与出包清单路径、"
                    "退出码 3；带 --confirm：上述内容 ＋ 逐条回读对账结论（包内文件集合、逐文件 sha256、"
                    "点名排除 0 命中、结构完整、引用闭合）＋ 回滚说明。"),
          c("check", "只读自检一份包：五条断言（① 包内可跑 ② 包内接入可用 ③ 干净 ④ 无写死绝对路径 "
                     "⑤ 差集对账）逐条给结论与证据（只读，不产出任何东西）",
            options=[o("pack_dir", "path", "包目录（位置写法，也可写 `--pack-dir <目录>`）",
                       required=True, metavar="包目录"),
                     o("--pack-dir", "path", "与位置写法等价（`daniel pack --check <包目录>`）",
                       metavar="目录"),
                     o("--source", "path", "源目录（不给则从本 CLI 位置推；推不出就只用出包清单复算"
                                           "差集，并如实标注「与源的差集未取得」）", metavar="目录"),
                     o("--host", "choice", "只对某个宿主做隔离复现（默认＝**两个宿主都做**："
                                           "Cursor 与 Codex 各接入一次，再跑不带 --host 的 "
                                           "`connect --doctor`，连跨宿主一致性一起验）",
                       choices=CONNECT_HOSTS, metavar="宿主"),
                     o("--keep", "flag", "保留隔离复现的临时目录（排查用；默认用完即删）"),
                     o("--fast", "flag", "只跑 A1–A4（跳过 A5 隔离复现，约 1 秒）：排查与快速回归用；"
                                         "**验收不要用这个开关**（跳过≠通过，结论里会点出未取得项）")],
            examples=["daniel pack --check /tmp/交付包/daniel-bot",
                      "daniel pack check /tmp/交付包/daniel-bot --json",
                      "daniel pack --check /tmp/交付包/daniel-bot --host codex --json"],
            cli_aliases=["pack --check"],
            returns="五条断言逐条：**判据／通过与否／证据**（未过的给**明细**：命中清单、差集、缺失项、"
                    "doctor 逐项结论）＋ 结论 ＋ 包内文件数与总字节。**任一条不过即退出码非 0**；"
                    "「未取得」的项（例如环境里没有凭据时「包内接入可用」需要真取一次数）"
                    "如实登记，既不按通过也不按失败处理。"),
      ]),

    m("install", "安装向导", "**一条命令装好**：装 CLI ＋ 装能力束 ＋ 写宿主接入（复用 `connect`）"
                            "＋ 起登录（浏览器授权路）—— 对齐飞书项目 CLI 的安装与接入形态。",
      options=[_INSTALL_HOST, _INSTALL_FROM, _INSTALL_PROJECT, _INSTALL_SKILLS, _INSTALL_BIN,
               _INSTALL_COOKIE, _INSTALL_NOOPEN, _INSTALL_CONFIRM, _INSTALL_DRYRUN],
      usage_note="**为什么要有这个模块**：在这之前，「装好」要手工做四件事 —— 拷包、`ln -s` 入口、"
                 "逐束软链技能、抄宿主配置，最后才想起来登录。现在**一条命令做完四步**：\n\n"
                 "    daniel install --confirm\n\n"
                 "四步各自对应一条既有能力，**不重造**：\n"
                 "  ① **装 CLI**：把入口软链到用户 PATH（`~/.local/bin/daniel` ＋ shell 配置里一行 PATH）"
                 "—— 沿用 `06` 步骤 2 的既有做法；\n"
                 "  ② **装能力束**：8 束 `kol-*` 按**软链**装到宿主技能目录（默认 `<项目目录>/.agents/skills`）"
                 "—— **唯一真源留在能力包里**，升级自动跟随、不复制、不占额外空间；\n"
                 "  ③ **写宿主接入**：直接调 `daniel connect --host <宿主> --apply --confirm`"
                 "（自己算路径、幂等合并、写前落快照、写后回读对账）；\n"
                 "  ④ **起登录**：打开／打印 Daniel 登录页（`https://daniel-agent.com/auth`），"
                 "你在**页面上**完成登录后把会话粘回来 —— **CLI 绝不向你要账号密码**。\n\n"
                 "**幂等与可回滚**：每一步先判「现状是否已经是目标」⇒ 重复跑**不改任何文件**；"
                 "写前把原文落进 `<数据落点>/install/snapshots/<时间戳>/`，写后逐项回读对账。\n\n"
                 "**装完会自动复核**：四步跑完，**同一条命令里**立刻再跑一次只读复核"
                 "（与 `daniel install --check` **同源**，直接复用同一套函数 —— 入口能跑／8 束完整且"
                 "与包内逐字一致／复用 `connect --doctor` 判接入／`daniel auth status` 判登录态），"
                 "把**四步结论 ＋ 复核四项结论**打在输出末尾，**用户不需要再输入任何命令**；"
                 "四项全绿才算装好，任一不过即给**一行修法**且退出码非 0。"
                 "`daniel install --check` 这条命令**保留**，供随时重跑。\n\n"
                 "🔴 **现在是本地安装；包上 npm 之后还是同一条命令、同一套步骤** —— 换的只有"
                 "「包从哪来」这一处（`--from`），四步逻辑与用户命令逐字不变，也**不引入 Node／npm 依赖**。",
      commands=[
          c("run", "一条命令做完四步：装 CLI（入口进 PATH）＋ 装能力束（8 束软链）＋ 写宿主接入"
                   "（复用 connect）＋ 起登录（浏览器授权路）（写操作）",
            write=True, write_stage="live",
            danger="会写三处本机内容：① `~/.local/bin/daniel` 一条软链 ＋ shell 配置里一行 PATH；"
                   "② 宿主技能目录下 8 条 `kol-*` 软链；③ 宿主配置里本产品那一条（后者**只经 "
                   "`connect` 写**，幂等、写前落快照、可 `--uninstall` 撤）。**不改任何 Daniel 数据、"
                   "不触发任何采集、不向你要账号密码**",
            confirm_help="确认安装：装 CLI ＋ 8 束能力束 ＋ 宿主接入 ＋ 起登录（四步都只动本机；"
                         "写前落快照、写后回读对账；重复跑不改文件）",
            options=[_INSTALL_HOST, _INSTALL_FROM, _INSTALL_PROJECT, _INSTALL_SKILLS, _INSTALL_BIN,
                     _INSTALL_COOKIE, _INSTALL_NOOPEN],
            examples=["daniel install",
                      "daniel install --confirm",
                      "daniel install --confirm --host cursor",
                      "daniel install --confirm --from /tmp/交付包",
                      "daniel install run --confirm --project ~/我的项目 --json"],
            returns="干跑（不带 --confirm）：四步逐条的**将要做什么**（入口与 PATH 行、8 束的落点与"
                    "现状、要接入的宿主与理由、登录页与回读形态）＋ 会改哪些文件 ＋ 复核命令，退出码 3；"
                    "带 --confirm：四步的**改动清单 ＋ 逐项回读对账结论 ＋ 快照落点 ＋ 安装台账落点**，"
                    "随后**同一进程内自动跑一次只读复核**（与 `install --check` 同源，不重写），"
                    "结果在 `readback.detail.装完复核`（含 `回读.逐项` 四项）＋ 人读输出**末尾**的"
                    "「四步结论 ＋ 复核四项结论」块 —— **用户不需要再输入任何命令**。"
                    "**完成后仍须处于已登录态、且复核四项全绿**才算成功；任一条不过就如实报出来"
                    "并给**一行修法**，退出码非 0（不静默 exit 0）。"),
          c("check", "装完自检（只读）：① 入口能跑 ② 8 束软链完整且与包内逐字一致 ③ 接入（复用 "
                     "`connect --doctor`）④ 登录态（`auth status` 三档）⇒ 全绿退出码 0，任一不过给一行修法",
            options=[_INSTALL_HOST, _INSTALL_FROM, _INSTALL_PROJECT, _INSTALL_SKILLS, _INSTALL_BIN],
            examples=["daniel install --check",
                      "daniel install --check --json",
                      "daniel install check --project ~/我的项目 --json"],
            returns="四项逐条：**判据／通过与否／证据**（入口路径与 `--version` 实跑结果、8 束的软链"
                    "指向与 `SKILL.md` 指纹、doctor 的逐项结论、`auth status` 的三档结论）＋ 总结论 ＋ "
                    "**一行修法**。本机没有宿主时，第 ③ 项按**不适用**处理（不是通过也不是失败）。"
                    "**任一项不过即退出码非 0**（登录态那一项沿用 `auth status` 的三档退出码语义）。"),
          c("upgrade", "就地升级：把本机安装改指到另一份包（入口与 8 束软链改指、宿主配置经 "
                       "`connect` 刷新），随后**自动重跑 `install --check`** 并把它的结论作为本次结果"
                       "（写操作）",
            write=True, write_stage="live",
            danger="会改指入口软链与 8 束技能软链，并经 `connect` 刷新宿主配置里本产品那一条"
                   "（写前落快照）；升级后自动跑一遍 `daniel install --check`",
            confirm_help="确认升级：把本机安装改指到 `--from` 那一份包，并经 connect 刷新宿主接入；"
                         "随后自动重跑自检",
            options=[_INSTALL_HOST, _INSTALL_FROM, _INSTALL_PROJECT, _INSTALL_SKILLS, _INSTALL_BIN],
            examples=["daniel install --upgrade --from /tmp/交付包2",
                      "daniel install --upgrade --from /tmp/交付包2 --confirm",
                      "daniel install upgrade --from /tmp/交付包2 --confirm --json"],
            returns="升级干了什么（改指了哪些条目）＋ **升级后自检的完整结论**（四项逐条）＋ 快照落点。"
                    "**自检不过即退出码非 0**（并给一行修法）—— 升级的判据是「自检全绿」，"
                    "不是「命令跑完了」。"),
      ],
      flag_commands={"--check": "check", "--upgrade": "upgrade"}),

    m("intake", "需求入口", "把「需求识别 → 能力匹配 → 前置条件告知 → 工序契约草稿」做成能力包"
                           "核心：一句话需求就能看清**这是哪道工序、还缺什么、缺了怎么补**。",
      usage_note="本模块是**能力包核心**（真源在 `daniel_cli/intake/`）：CLI 与 MCP 是两种"
                 "承载模式，**每一种都内置这条完整链路**（不存在「某能力只在一种模式里」）。"
                 "\n\n三条纪律：① **能查的必须去查** —— 凡 Daniel 侧能查到的前置条件"
                 "（品牌名单、名单条目、品牌档案、提及与声量、合作活动、真实性评分…）"
                 "由本命令**真调一次只读命令**并把退出码／条数／耗时当证据；查不到的才写"
                 "「需你提供」。② **缺件不硬跑** —— 前置不齐时只给「缺什么＋怎么补」，"
                 "报告里 `可执行=false`（退出码仍是 0，参数错误才是 2）。③ **写动作要人点头** —— "
                 "写动作在两种模式下都**可见**：CLI 模式走 `--confirm` 人工确认后执行，"
                 "MCP 模式只出**确认单**（附可直接执行的命令），由人拿到 CLI／桌面壳执行；"
                 "报告里对应的状态是「需人工确认后执行」，**不是**「不支持／能力缺失」。"
                 "\n\n全程只读：不写任何 Daniel 数据、不触发任何采集；`draft` 只在 `--out` "
                 "指定的落点写一份草稿文件（默认落在引擎契约目录之外，见 `draft` 的返回说明）。"
                 "\n\n前置条件的来源类型四种：`人提供`／`系统内已有`／`可推导`／`模式能力`"
                 "（第四种由当前模式**真实可用**的能力集合在运行期派生，不写死在表里）。"
                 "前置条件**细到工序**（例：审核表-出件／砍价-还价／首封-起草 各自列）。",
      commands=[
          c("route", "一句话需求 → 候选工序（排序＋理由＋置信度）＋ 前置条件清单（逐项带状态）"
                     "＋ 缺件清单（只读）",
            options=[o("--need", "str", "一句话需求（业务原话即可）", required=True,
                       metavar="一句话需求"),
                     o("--brand", "str", "本次针对哪个品牌（品牌名或编号）；不给就从需求里认，"
                                         "认不出来会如实说「还没确定」", metavar="品牌"),
                     o("--top", "int", "候选工序最多给几条", default=3, metavar="条数"),
                     o("--check-all", "flag", "对前几条候选都做实查（默认真查 Top1，"
                                             "其余只给声明清单）"),
                     o("--mode", "choice", "按哪种承载模式判能力可用性（默认按当前进程判定）",
                       choices=["cli", "mcp"]),
                     o("--no-probe", "flag", "不联网实查：只按声明给状态（会明确标「未实查」，"
                                            "不谎称已满足）"),
                     o("--timeout", "int", "单条取数的超时（秒）", default=30, metavar="秒")],
            examples=["daniel intake route --need \"帮我审一下这批红人的报价\"",
                      "daniel intake route --need \"出一份声量份额报告\" --brand 3690002 --json",
                      "daniel intake route --need \"帮我审一下这批红人的报价\" --no-probe",
                      "daniel intake route --need \"触发一次品牌提及采集\" --mode mcp --json"],
            returns="候选工序（工序／能力域／置信度／档位／理由／产出交付件／对应契约）、"
                    "Top1 的**前置条件清单**（每项带来源类型、当前状态、取数方式、实查证据、怎么补）、"
                    "缺件清单与待确认清单、`可执行`（缺件时为 false）、模式事实"
                    "（当前模式可用能力数与真源）、实查记录、结论与下一步。"),
          c("draft", "一句话需求 → 生成本次任务的**工序契约草稿**（输入／步骤／判据／门禁／"
                     "交付件／自检），并就地用引擎校验器校验（只读；只写这一份草稿）",
            options=[o("--need", "str", "一句话需求（业务原话即可）", required=True,
                       metavar="一句话需求"),
                     o("--out", "path", "草稿落到哪个文件（默认落在引擎契约目录之外的 "
                                        "`data/daniel-cli/drafts/`，避免每任务一份的数据依赖草稿"
                                        "混进引擎自证）", metavar="文件"),
                     o("--brand", "str", "本次针对哪个品牌（品牌名或编号）", metavar="品牌"),
                     o("--input", "str", "你手上已经有的输入，写成「名字=值」；可多次",
                       repeat=True, metavar="名字=值"),
                     o("--mode", "choice", "按哪种承载模式判能力可用性", choices=["cli", "mcp"]),
                     o("--no-probe", "flag", "不联网实查（交付件形状会因此无法确证，"
                                            "草稿会如实把期望写成「失败／1」）"),
                     o("--timeout", "int", "单条取数的超时（秒）", default=30, metavar="秒")],
            examples=["daniel intake draft --need \"帮我审一下这批红人的报价\" --brand 3690002",
                      "daniel intake draft --need \"帮我审一下这批红人的报价\" "
                      "--brand 3690002 --out /tmp/本次任务.json --json",
                      "daniel intake draft --need \"出一份声量份额报告\" --brand 3690002 "
                      "--input 竞争集=Anker,RayNeo"],
            returns="草稿落点与契约编号、引擎校验结论（**能过 `playbook validate` 才算成**）、"
                    "取数步骤数与交付件形状（来源步骤／列／必填列）、`待你确认或补充` 清单"
                    "（「人提供」类输入留的**显式空占位**，不编造输入值）、"
                    "待补充后才能加入的取数步骤、写动作确认单、期望结果与说明、复核命令。"),
          c("parity", "模式对等断言：CLI 模式与 MCP 模式暴露的**能力集合／技能集合／语料版本**"
                     "键比对（只读）",
            options=[],
            examples=["daniel intake parity", "daniel intake parity --json"],
            returns="四组断言（能力／链路／技能／可达）逐组结论与**键比对字符串**："
                    "能力集合差集是否只允许写链、intake 链路在两种模式下是否都可达、"
                    "技能集合与语料版本三源是否逐字一致、同一份技能清单在两种模式下是否都取得到"
                    "（未落地项显式登记，不当通过）。"),
          c("catalog", "看工序与前置条件表本身：8 个能力域各有哪些工序、每个工序要哪些前置条件"
                       "（只读）",
            options=[o("--domain", "str", "只看某个能力域（域键，如 kol-negotiation）",
                       metavar="能力域")],
            examples=["daniel intake catalog", "daniel intake catalog --domain kol-negotiation",
                      "daniel intake catalog --json"],
            returns="语料版本与工序总量、来源类型统计、工序表自证结论，以及每个能力域下"
                    "每道工序的触发语义、前置条件（名称／来源类型／取数方式／说明）、"
                    "产出交付件、对应契约、需要能力与依据出处。"),
      ],
      self_test="跑本模块自带的自检（正控：真实历史需求必须落到正确能力域；真阴性：完全无关的"
                "需求不得硬匹配；缺件场景必须给缺件清单与补法；写动作三态与措辞；草稿必须过"
                "`playbook validate` 并能被 `playbook run` 真跑；模式对等断言；只读自证）"),

    m("schema", "命令清单", "本 CLI 自描述：全部子命令与参数、以及派生出来的工具定义。",
      [
          c("show", "打印全部子命令与参数的机器可读清单（单一真源）", options=[],
            examples=["daniel schema", "daniel schema --json"],
            returns="模块、命令、参数、类型、是否必填、是否写操作、退出码语义、示例。"),
          c("mcp", "打印 MCP tool list（{name, description, inputSchema}）", options=[],
            examples=["daniel schema mcp --json"],
            returns="每个子命令一个 MCP 工具定义。"),
          c("dsh-tools", "打印 DSH defineTool 工具定义草稿（{name, description, parameters}）", options=[],
            examples=["daniel schema dsh-tools --json"],
            returns="每个子命令一个 DSH 工具定义草稿。"),
          c("check", "自证：CLI 实际注册的子命令集合 ≡ 本清单声明的集合（并核对实现是否齐备）",
            options=[],
            examples=["daniel schema --check"],
            returns="差异清单与结论。",
            exit_codes=[EXIT_OK, EXIT_INTERNAL]),
      ],
      flag_commands={"--mcp": "mcp", "--dsh-tools": "dsh-tools", "--check": "check"},
      usage_note="不带子命令名时默认执行 `show`，所以 `daniel schema --json` 直接打印清单。"),

    m("clarify", "澄清",
      "**参数级追问**：把一份模糊需求里**可枚举**的参数缺口一次列全（缺市场／粉丝区间／内容形式／"
      "交付形态／时间窗／排重／数量／交付时点），每项都带「不答按什么默认走」；口径级判断只列名字"
      "与影响，不给判据。**离线、不取数**：只读随包登记表与触发词，返回体里没有任何品牌名／红人数／金额。",
      [
          c("plan", "列参数缺口清单，并给出找红人的五类方向（选择面）",
            options=[o("--need", "str", "用户原话或需求摘要（必填）", required=True),
                     o("--topic", "choice", "场景；不给则按原话判断（kol_search 找红人／list_ops 名单处理／"
                                            "brand_setup 品牌建档）",
                       choices=["kol_search", "list_ops", "brand_setup"])],
            examples=['daniel clarify plan --need "帮我找一批测评红人"',
                      'daniel clarify plan --need "把两份名单合并一下" --topic list_ops --json'],
            returns="`场景`／`场景依据`／`已识别项`／`缺项`（每项带「为什么问」与「不答的默认值」）／"
                    "`优先补`／`口径类`／`下一步`／`选择面`；有溢出时多一个 `其余按默认口径执行`，"
                    "参数全齐时多一个 `结论`。**不含任何取数结果**。",
            exit_codes=[EXIT_OK, EXIT_USAGE, EXIT_INTERNAL]),
          c("ask", "找红人专用：先出五类选择面，再按回答动态追问（最多 2 轮）",
            options=[o("--need", "str", "用户原话（必填）", required=True),
                     o("--reply", "str", "用户对「选择面」的回答；不给＝首次调用（只出选择面）"),
                     o("--round", "int", "第几轮问答（从 1 起）；到 2 轮不再追问，按默认跑并标「未确认」")],
            examples=['daniel clarify ask --need "帮我找 20 个做智能眼镜测评的红人"',
                      'daniel clarify ask --need "…" --reply "美国、长视频均播 30 万、排除已合作" --round 1 --json'],
            returns="四模式之一：`选择面`／`确认`／`动态追问`／`到上限按默认`；字段含 `选择面`／`模式`／"
                    "`已识别项`／`缺口`／`追问`／`未确认项`／`下一步` 等。**不取数**。",
            exit_codes=[EXIT_OK, EXIT_USAGE, EXIT_INTERNAL]),
      ],
      usage_note="本模块**不取数**、不联网、不读账号：只读随包登记表（28 条参数文案）与触发词文件。"
                 "需求已经说得够清楚时不必调用；调用也会回「参数已齐」。"),

]

SCHEMA = {
    "schemaVersion": "1.0",
    "cli": "daniel",
    "generatedBy": "data/daniel-cli/daniel_cli/schema.py（唯一真源）",
    "conventions": {
        "stdout": "只放结果（--json 时是且仅是一个 JSON 文档）",
        "stderr": "只放进度、提示与警告",
        "interactive": "默认非交互，不依赖 TTY，不弹任何提问",
        "writeGating": "写操作默认干跑；未加 --confirm 一律退出码 3 且不执行任何写",
        "writePermission": "写链由账号的使用权限决定：账号对该模块没有写权限时退出码 2，"
                           "并用一行理由说明是系统角色／账号状态／工作区权益／配额哪一轴不满足"
                           "（用 daniel account capabilities 看完整能力矩阵）；本 CLI 不含审批流",
        "writeDeleteToken": "删除类操作在 --confirm 之外必须再给 --delete-token <目标名>"
                            "（把目标名原样再写一遍；写错即拒、退出码 2、零删除）",
        "writeAudit": "每次写留一条可导出记录（时间／账号／工作区／品牌／动作／影响范围／回读结果／"
                      "是否回滚），落在数据落点的 logs 目录，用 daniel account audit 导出",
    },
    "exitCodes": EXIT_CODES,
    "globalOptions": GLOBAL_OPTIONS,
    "modules": _MODULES,
}


def module_map():
    return {mod["key"]: mod for mod in SCHEMA["modules"]}


def declared_command_keys():
    """schema 里声明的全部命令键（`<模块>.<子命令>`）。"""
    return {"%s.%s" % (mod["key"], cmd["name"])
            for mod in SCHEMA["modules"] for cmd in mod["commands"]}


def find_command(module_key, command_name):
    mod = module_map().get(module_key)
    if not mod:
        return None
    for cmd in mod["commands"]:
        if cmd["name"] == command_name:
            return cmd
    return None


# ─────────────────────── argv 别名（唯一真源在这里） ───────────────────────
def cmd_aliases():
    """`{(别名分词…): (模块, 子命令)}` —— 只认 `cli_aliases` 里**声明过**的写法。

    这是别名的**唯一真源**：派生器与解析器都从这里取，任何地方都不许再写一张别名表。
    """
    out = {}
    for mod in SCHEMA["modules"]:
        for cmd in mod["commands"]:
            for alias in (cmd.get("cliAliases") or []):
                tokens = tuple(str(alias).split())
                if len(tokens) < 2:
                    raise ValueError("%s 的别名 %r 至少要写成「模块 子命令」两段" % (cmd["name"], alias))
                out[tokens] = (tokens[0], cmd["name"])
    return out


def rewrite_aliases(argv):
    """把 argv 里声明过的别名写法重写成真源里的命令名（没命中就原样返回）。

    `["account", "credentials", "set", "--confirm"]` → `["account", "credentials-set", "--confirm"]`。
    先替换最长命中的别名，替换到不再命中为止（别名不会互相嵌套，这里只是保证幂等）。
    """
    args = [str(a) for a in argv]
    aliases = cmd_aliases()
    for _ in range(4):
        hit = None
        for tokens in sorted(aliases, key=len, reverse=True):
            n = len(tokens)
            for i in range(0, len(args) - n + 1):
                if tuple(args[i:i + n]) == tokens:
                    hit = (tokens, aliases[tokens], i)
                    break
            if hit:
                break
        if not hit:
            break
        tokens, target, i = hit
        args = args[:i] + [target[0], target[1]] + args[i + len(tokens):]
    return args
    return None


def module_keys():
    return tuple(mod["key"] for mod in SCHEMA["modules"])


def cli_modules():
    """票面要求的 12 个业务模块（不含元模块 schema）。"""
    return tuple(k for k in module_keys() if k in REQUIRED_MODULES)
