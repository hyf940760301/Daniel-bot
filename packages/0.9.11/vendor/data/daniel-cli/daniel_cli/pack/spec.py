# -*- coding: utf-8 -*-
"""出包的**源清单规则**（唯一真源）：哪些文件必须包含、哪些必须排除，各带理由。

为什么是"规则"而不是"一份清单"
------------------------------
票面（TICKET-193 §A）要求排除清单**不靠猜**：每一项都要有理由，并且要落成**可复算的规则**
（路径模式 ＋ 理由）。所以本文件里只有两样东西：

  ① **档位**：每个模式必落 `必须包含` 或 `必须排除` 之一（票面「分档条件」）；
  ② **理由**：每一条都必须写明"为什么必须这样"，且理由要指向一个**代码事实**
     （谁在运行期按名字读它、谁在什么条件下才会写它），不是"我觉得应该排除"。

规则一旦声明，候选面与排除集都由 `classify()` **算出来** —— 手抄清单在这里结构上不存在。

三个面（说清"源 − 包 == 排除清单"是在哪个面上成立的）
----------------------------------------------------
  · **候选面**：`CANDIDATE_ROOTS` 声明的那几棵树里的全部文件。它们**有可能**进包，
    逐个过规则：命中包含规则 ⇒ 候选；候选再判**非兜底**的排除规则；没有任何包含规则命中
    ⇒ 判兜底排除规则（`X01` ＝"能力层里不在白名单内的文件"）；两边都没命中 ⇒ 既不在包里、
    也不进排除清单（它压根不在候选面里）。
    **差集对账**（`源 − 包 == 排除清单`）就是在这个面上逐项复算的。
  · **包含面**：候选面里没被排除的那些 —— 它们必须**一个不少**地出现在包里，且逐字节相等。
  · **点名面**：**不在候选面内**、但必须在排除清单上被**逐项点名**的路径
    （`NAMED_EXCLUSIONS`）。为什么要单独一面：这些是整个分发安全的要害
    （`<源根>/.daniel_cred.json` 就是明文邮箱＋密码），它们**不在候选面里**并不是
    "因为它们在别的目录所以自然被排掉"这种推断，而是**被点名排除并单独断言包内不存在**。
    票面（追加要求）明确禁止用"顺带被排掉"代替点名，故此处单列。

匹配语义（写在这里，避免"读起来像正则、其实不是"）
--------------------------------------------------
模式按 `fnmatch` 语义匹配**相对源根的 POSIX 路径**；`*` **可以跨**目录分隔符（本文件里的模式
都按这个语义写，例如 `.kol-tools/*` 覆盖 `.kol-tools/` 下任意深度）。大小写敏感（macOS 默认
文件系统不敏感，但包是拷到别的机器上的，这里按"逐字节"判，不做大小写折叠）。
"""
import fnmatch

#: 候选面的根（相对源根）。**只有**这几棵树里的文件会被"考虑进包"。
CANDIDATE_ROOTS = (
    "data/daniel-cli",
    ".kol-tools",
)


def _rule(rid, pattern, reason, tier, fallback=False):
    return {"id": rid, "pattern": pattern, "reason": reason, "tier": tier, "fallback": fallback}


# ═══════════════════════ 一、必须包含（附理由） ═══════════════════════
INCLUDE_RULES = (
    _rule("I1", "data/daniel-cli/*",
          "CLI 本体：`bin/daniel`（入口，按 realpath 定位包根）＋ `daniel_cli/**`（19 个模块的实现、"
          "单一真源 `schema.py`、契约引擎、账号分区、调度层、`connect` 接入层）＋ `mcp/server.py`"
          "（MCP 服务）＋ `mcp/corpus/**`（**随包语料**：`corpus.py` 按包自身位置定位它）＋ "
          "`contracts/**`（契约真源与夹具）＋ 随包文档与自检链。"
          "判据来源：`daniel_cli/runtime.py` 只从本包内定位代码与语料，包外只依赖能力目录。",
          "必须包含"),
    _rule("I2", ".kol-tools/daniel_*.py",
          "Daniel 能力层里**被 CLI 运行期按名字加载**的模块（15 个）：`daniel_client`（共享客户端，"
          "含鉴权与跨工作区品牌解析）、`daniel_paths`（落点唯一真源）、`daniel_credentials`（凭据存储）、"
          "`daniel_io`（JSON 出口收口层）＋ 11 个模块仪器（brands／lists／search／mentions／intel／sov／"
          "ct／authenticity／route_probe／takeover_check／ui_parity），以及它们互相之间的按名加载"
          "（`_load_sibling`／`_sibling`／`spec_from_file_location`／`_load`）。"
          "判据来源：引用闭合断言（`verify.static_reference_closure()`）—— 这条不是靠背下来的名单，"
          "而是靠「凡包内代码按名字引用的能力模块，包里必须有」守住的。",
          "必须包含"),
    _rule("I3", ".kol-tools/doc_to_pdf.py",
          "出件工序的 PDF 渲染器：`daniel playbook deliver <契约>` 在契约声明 `格式=PDF` 时按路径加载它"
          "（`daniel_cli/playbook/pdfout.py`）。少了它，出件能力在包里就断了，而连接入自检都发现不了。",
          "必须包含"),
    _rule("I4", ".kol-tools/check_no_secrets_in_dist.py",
          "分发物凭据断言器（TICKET-144）：本包的干净度断言**复用它**（不另造扫描口径，票面要求），"
          "同时把它随包带过去，使拿到包的人**自己**也能对这份拷贝复跑一次凭据断言。",
          "必须包含"),
    _rule("I5", ".kol-tools/_daniel_jsref/*",
          "`parity`（口径一致性）仪器要用的前端算法还原件（36 KiB）：`commands/_common.oracle_path()` 与"
          "`daniel_ui_parity.py --oracle` 都指向它，缺了它 `parity compare` 就跑不了。",
          "必须包含"),
)

# ═══════════════════════ 二、必须排除（附理由） ═══════════════════════
EXCLUDE_RULES = (
    _rule("X01", ".kol-tools/*",
          "能力层里**不在 I2／I3／I4 白名单内**的文件（其余 141 个顶层脚本，以及台账、备份、"
          "渲染中间件、一次性 shell、归档子目录）。理由：CLI 运行期只**按名字**加载白名单里那几个模块，"
          "从不执行别的脚本；其余文件是一票一用的业务仪器与检查器，进包只会放大体积"
          "（`.kol-tools` 全量 130 MB）并扩大泄漏面。**本规则命中的每个文件都在出包清单的「排除」段里逐项列出。**",
          "必须排除", fallback=True),
    _rule("X02", "*__pycache__*",
          "解释器字节码缓存目录：内容由本机解释器生成，含**本机绝对路径**（源文件名写进 .pyc 头），"
          "且随时可再生成 —— 换机器没有任何价值，只有风险。",
          "必须排除"),
    _rule("X03", "*.pyc", "散落的字节码文件（未落在 `__pycache__` 目录里的情形）：同上。", "必须排除"),
    _rule("X04", "*.pyo", "优化字节码：同上。", "必须排除"),
    _rule("X05", "*.bak-*",
          "改造前的备份件（例如 `.kol-tools/daniel_client.py.bak-20261014`）：是**历史版本**，"
          "与现行实现并存会让人（和仪器）不知道该执行哪一份。",
          "必须排除"),
    _rule("X06", "*.orig", "补丁工具留下的原件（`.orig`）：同上，历史版本。", "必须排除"),
    _rule("X07", "*.tmp", "中间件：一次执行留下的半成品，没有分发价值。", "必须排除"),
    _rule("X08", "*.log", "运行日志：含本机路径与运行期事实（账号掩码、品牌名、落点）。", "必须排除"),
    _rule("X09", "*.out", "既有仪器重定向出来的运行输出：同上。", "必须排除"),
    _rule("X10", "*.err", "同上（错误输出落盘件）。", "必须排除"),
    _rule("X11", "*.zip", "归档件：包必须给**目录形态**（可逐项复算），夹杂归档会让差集对账失去意义。",
          "必须排除"),
    _rule("X12", "*.tar.gz", "同上（压缩归档）。", "必须排除"),
    _rule("X13", "*.tgz", "同上（压缩归档）。", "必须排除"),
    _rule("X14", ".env",
          "环境变量文件：按 README 的凭据纪律，`DANIEL_EMAIL`／`DANIEL_PASSWORD` 可能就在里面（明文凭据）。",
          "必须排除"),
    _rule("X15", "*.env", "同上（`.env.local` 这类形态）。", "必须排除"),
    _rule("X16", "*keychain*", "钥匙串材料（导出件／夹具）：通用密钥材料，一律不进分发物。", "必须排除"),
    _rule("X17", "*.pem", "私钥／证书材料。", "必须排除"),
    _rule("X18", "*.p12", "证书／私钥容器。", "必须排除"),
    _rule("X19", "id_rsa*", "SSH 私钥。", "必须排除"),
    _rule("X20", "*.daniel_cred.json",
          "**明文凭据文件**（邮箱＋密码）：`daniel_paths` 的 `legacy_credentials_fallback`，"
          "是这个产品里唯一会把密码落成明文的路径。**名字级**命中即排除，不看它在哪一层。",
          "必须排除"),
    _rule("X21", "*.daniel_session.json",
          "**会话 JWT 文件**（`app_session_id`，1 年有效）：等同账号，无需密码即可取数。名字级命中即排除。",
          "必须排除"),
    _rule("X22", "*/secrets/*",
          "`$DANIEL_HOME/secrets/`（仅在显式 `DANIEL_ALLOW_PLAINTEXT=1` 时生成）里的明文降级凭据："
          "同为明文密码。",
          "必须排除"),
    _rule("X23", "*/.daniel-home/*",
          "工作区降级落点整体（session／cache／output／logs／secrets 全在里面）：包含会话与账号数据。",
          "必须排除"),
    _rule("X24", "*/_cache/*",
          "本机缓存（`brand-index.json` 是**账号数据**：账号可见的品牌与工作区清单）。",
          "必须排除"),
    _rule("X25", "*_INVENTORY*",
          "仪器／文件台账（`_INVENTORY.md`／`_INVENTORY.json`）：**内部治理件**，属团队工作区内容，"
          "不是产品的一部分（票面红线点名）。",
          "必须排除"),
    _rule("X26", "data/daniel-cli/mcp/_fixtures/cross-host/*.json",
          "`compare_hosts.py` 的**正控回归对**（两份真件产物）。它们**含本机绝对路径**"
          "（`/Users/<用户名>/…` 共 12 处）—— 那是真件的一部分（该目录 README 写明"
          "「只有本机路径与工序结论」），但正因如此它们过不了本包的机器特征断言（票面 ③）。"
          "**取舍**：干净优先 ⇒ 排除这两个文件；代价是包内 `compare_hosts.py --self-test` 缺正控夹具"
          "（已登记为已知边界）。",
          "必须排除"),
)

#: 兜底规则（只在没有任何包含规则命中时生效）：`X01`。
FALLBACK_RULES = tuple(r["id"] for r in EXCLUDE_RULES if r["fallback"])

# ═══════════════ 三、点名排除：不在候选面内、但必须逐项点名 ═══════════════
#: 每一项都是 `(模式, 理由)`；模式按 fnmatch 语义对**包内相对路径**匹配。
#: 断言方式：**包内不得出现**任何命中这些模式的文件（`scanner.named_exclusions()`）；命中即 FAIL。
NAMED_EXCLUSIONS = (
    (".daniel_cred.json",
     "**明文凭据**（`<源根>/.daniel_cred.json`，63 字节＝邮箱＋密码）。它是 "
     "`daniel_paths.LEGACY['credentials_fallback']` 的回退点 —— 只要它跟包一起走，"
     "拿到包的人在**未登录**状态下也能取到真实数据（TICKET-193 追加要求实测确认过这个坑）。"),
    (".kol-tools/.daniel_session.json",
     "**legacy 会话 JWT**（`<能力目录>/.daniel_session.json`）：`daniel_paths.LEGACY['session_file']`，"
     "1 年有效、无需密码即可取数。"),
    (".kol-tools/_cache/*",
     "**legacy 品牌索引**（`<能力目录>/_cache/brand-index.json`）："
     "`daniel_paths.LEGACY['brand_index']`，内容是账号可见的品牌与工作区清单（账号数据）。"),
    (".daniel-home/*",
     "**工作区降级落点**（`<源根>/.daniel-home/`）：`daniel_paths.FALLBACK_HOME`，"
     "session／cache／output／logs／secrets 都在里面。它在目标机器上是**运行期生成目录**，"
     "绝不该是分发内容。"),
    (".env", "环境变量文件（可能含 `DANIEL_EMAIL`／`DANIEL_PASSWORD`）：不管出现在包内哪一层都不允许。"),
    ("*.env", "同上（`.env.local` 这类形态）。"),
    (".kol-tools/_INVENTORY.md", "仪器台账（内部治理件）：票面点名不得随包。"),
    (".kol-tools/_INVENTORY.json", "仪器台账（内部治理件）：票面点名不得随包。"),
    (".kol-tools/_archive*/*",
     "历史一次性脚本归档（`.kol-tools/_archive/`、`_archive-oneshot/`）：体积大、可再生成、"
     "含早期凭据形态的代码。"),
    (".kol-tools/_snapshots/*", "运行期快照（写前原文副本）：含被改写文件的内容。"),
    (".kol-tools/_verify_tmp/*", "验证用临时目录。"),
    (".kol-tools/_recovery/*", "恢复件。"),
    (".kol-tools/_backup-t147/*", "TICKET-147 改造前的备份树。"),
    (".kol-tools/_fixtures/*", "业务夹具（对外邮件定版语料等）：属能力语料面，不进 CLI 分发物。"),
    (".kol-tools/_daniel_bundle/*", "前端构建产物还原件（体积大、可再生成）。"),
    (".kol-tools/_libs/*", "第三方 vendored 依赖目录。"),
    (".kol-tools/ytdlp/*", "第三方 vendored 代码（含公开测试 token）：TICKET-144 的排除清单已点名。"),
    (".kol-tools/*.out", "运行输出落盘件。"),
    (".kol-tools/*.sh", "一次性 shell（`watch_*.sh`／`finalize_when_done.sh` 之类）：与 CLI 运行无关。"),
    (".kol-tools/*.json", "能力层台账（矩阵／词表／覆盖记录等）：属团队工作区内容。"),
    (".kol-tools/*.bak*", "改造前备份件。"),
    ("Library/Application Support/DanielCopilot/*",
     "**macOS 首选落点**（`daniel_paths.CANDIDATES[0]`）：会话、缓存、出件、日志、以及（显式降级时的）"
     "明文凭据都在里面。它按定义在用户主目录下、不在包里，但同样**点名**排掉，"
     "以防有人把整个落点拷进包目录。"),
)

#: 出包时**不复制**的空目录（源里有、包里不留）：没有文件可复算，留着只会让人以为"包里该有东西"。
SKIP_EMPTY_DIRS = ("data/daniel-cli/drafts",)


def match(rel, pattern):
    """按 `fnmatch` 语义匹配相对路径（`*` 可跨目录分隔符；大小写敏感）。"""
    return fnmatch.fnmatchcase(rel, pattern)


def _first(rules, rel):
    for r in rules:
        if match(rel, r["pattern"]):
            return r
    return None


def classify(rel):
    """一个相对路径的判定 → `(包含规则 or None, 排除规则 or None)`。

    口径（顺序即语义）：
      ① 先找**包含规则**；命中 ⇒ 它是候选，接着只再判**非兜底**的排除规则
         （兜底规则 X01 是"白名单之外"，不能吃掉白名单里的文件）；
      ② 没有任何包含规则命中 ⇒ 判兜底排除规则（X01，即"`.kol-tools/` 里不在白名单内的文件"）；
      ③ 两边都没命中 ⇒ 该文件不在候选面（既不在包里，也不进排除清单）。
    """
    inc = _first(INCLUDE_RULES, rel)
    if inc is not None:
        exc = _first([r for r in EXCLUDE_RULES if r["id"] not in FALLBACK_RULES], rel)
        return inc, exc
    return None, _first([r for r in EXCLUDE_RULES if r["id"] in FALLBACK_RULES], rel)


def rule_by_id(rid):
    for r in INCLUDE_RULES + EXCLUDE_RULES:
        if r["id"] == rid:
            return r
    return None
