# -*- coding: utf-8 -*-
"""「取包」——**分发渠道的唯一抽象点**（TICKET-195 · 用户 2026-10-16 裁定）。

用户逐字要求
------------
> 「不过目前整个包还没有放到 npm 上，所以理论上 npm 的安装逻辑**不适用**（可以按照你的流程：
> 一条命令做完 装 CLI ＋ 装能力束 ＋ 写宿主接入（复用 connect）＋ 起登录，**后续只需要替换为
> npm 包安装即可**）」

所以本文件只回答一个问题：**这次要装的"包"从哪来、它在盘上的哪里**。
四步（装 CLI／装能力束／写宿主接入／起登录）**一律不碰"包从哪来"** —— 它们只消费本文件
返回的那一份 `包根`／`仓库根`／`入口`／`语料根`。将来包上了 npm，**只有这里换实现**：

| 阶段 | 渠道（`--from` 形态） | 四步 | 用户命令 |
|---|---|---|---|
| 现在（本票） | `self`（默认）／`<包目录>` | 完全相同 | `daniel install …` |
| 将来（上 npm 后） | `npm:<包名>@<版本>`（**本票只登记形态，不实现**） | 完全相同 | **逐字相同** |

🔴 **不引入 Node／npm 依赖**：本文件的 `npm` 渠道**只做形态登记与明确拒绝**（写明"这条缝已留，
但本票不执行它，也不因此要求 Node"）。任何 Python 侧都不调用 npm。

三种「本地产物」都认（都指向同一个包本身，只是摆放位置不同）
-----------------------------------------------------------
  · **出包产物目录**：`daniel pack --out /tmp/交付包` 出的那份 —— 给 `/tmp/交付包`
    （里面有 `daniel-bot/`）或直接给 `/tmp/交付包/daniel-bot`；
  · **包目录**：`…/data/daniel-cli`（含 `bin/daniel` 与 `daniel_cli/`）；
  · **仓库根／工作区根**：含 `data/daniel-cli/` 与 `.kol-tools/` 的那一级。

完整性判据（**不完整就当场拒绝**，并说清缺什么）
----------------------------------------------
包要能真的跑起来，缺一样都不行：
  ① `<包根>/bin/daniel`（入口，按 realpath 定位包自身）；
  ② `<包根>/daniel_cli/schema.py`（程序主体）；
  ③ `<包根>/mcp/server.py`（宿主接入要指向它）；
  ④ `<包根>/mcp/corpus/kol-*/SKILL.md`（能力束的**唯一真源**；软链装的就是它）；
  ⑤ `<仓库根>/.kol-tools/daniel_client.py`（取数能力；入口从包根向上找它）。
"""
import os

from ..exits import EXIT_USAGE
from ..runtime import CliError

#: 渠道形态（`--from` 的三种写法；`npm` 只登记、不实现）
CHANNEL_SELF = "self"
CHANNEL_DIR = "dir"
CHANNEL_NPM = "npm"

#: npm 渠道的**形态登记**（将来包上 npm 后，只换这一处的实现；四步与用户命令逐字不变）
NPM_CHANNEL_NOTE = (
    "`npm:<包名>@<版本>` 是**将来**的取包渠道（包上 npm 之后）——本票**不执行它**，"
    "也**不因此引入 Node／npm 依赖**：这条缝已经在 `daniel_cli/install/source.py` 里留好，"
    "届时只换「包从哪来」这一个函数，**四步与用户敲的命令逐字不变**。"
)


def _abspath(p):
    return os.path.abspath(os.path.expanduser(str(p)))


def self_package_root():
    """当前这份 CLI 自己的包根（`<…>/data/daniel-cli`）——从**本文件位置**推，不写死。"""
    here = os.path.dirname(os.path.realpath(__file__))          # …/daniel_cli/install
    return os.path.dirname(os.path.dirname(here))               # …/data/daniel-cli


def repo_root_of(pkg_root):
    """包根对应的仓库根（含 `.kol-tools`）——入口运行期就是靠它向上找能力目录的。

    先在包根的上两级里找 `.kol-tools`（出包产物／工作区都是这个形状），
    再退一步用"包根的上一级"（并把"没找到"如实带在返回值里，不假装）。
    """
    cand = []
    up = pkg_root
    for _ in range(4):
        up = os.path.dirname(up)
        if not up or up == os.path.dirname(up):
            break
        cand.append(up)
    for c in cand:
        if os.path.isfile(os.path.join(c, ".kol-tools", "daniel_client.py")):
            return c, True
    base = os.path.dirname(pkg_root)
    return base, False


def _pkg_candidates(p):
    """一个目录可能是哪些形态 → 候选包根（按"最像包"排序，先给结论再给理由）。"""
    return [
        os.path.join(p, "daniel-bot", "data", "daniel-cli"),      # 出包产物目录（现名）
        os.path.join(p, "daniel-copilot", "data", "daniel-cli"),  # 出包产物目录（TICKET-207 之前的旧名，兼容）
        os.path.join(p, "data", "daniel-cli"),                    # 仓库根／工作区根
        p,                                                        # 包目录本身
    ]


def _inspect(pkg_root):
    """完整性逐项结论：`(ok, 缺什么[list], 细节[dict])`。"""
    entry = os.path.join(pkg_root, "bin", "daniel")
    schema = os.path.join(pkg_root, "daniel_cli", "schema.py")
    server = os.path.join(pkg_root, "mcp", "server.py")
    corpus = os.path.join(pkg_root, "mcp", "corpus")
    repo, repo_ok = repo_root_of(pkg_root)
    domains = []
    if os.path.isdir(corpus):
        domains = sorted(d for d in os.listdir(corpus)
                         if d.startswith("kol-") and os.path.isfile(
                             os.path.join(corpus, d, "SKILL.md")))
    missing = []
    if not os.path.isfile(entry):
        missing.append("入口 <包根>/bin/daniel")
    if not os.path.isfile(schema):
        missing.append("程序主体 <包根>/daniel_cli/schema.py")
    if not os.path.isfile(server):
        missing.append("MCP 服务入口 <包根>/mcp/server.py")
    if not domains:
        missing.append("能力束真源 <包根>/mcp/corpus/kol-*/SKILL.md")
    if not repo_ok:
        missing.append("取数能力 <.kol-tools/daniel_client.py>（入口从包根向上找它）")
    detail = {"包根": pkg_root, "仓库根": repo, "入口": entry, "语料根": corpus,
              "能力域数": len(domains), "能力域": domains,
              "仓库根含 .kol-tools": bool(repo_ok)}
    return (not missing), missing, detail


def resolve(spec=None):
    """`--from <包目录|…>` → 这次要装的包（**单一抽象点**）。

    返回 `{渠道, 包根, 仓库根, 入口, 语料根, 能力域, 来源说明, 用户给的参数, 被检查过的候选}`；
    判不出来或包不完整 ⇒ `CliError`（退出码 2）＋ 一行修法，**绝不猜一个包出来**。
    """
    raw = str(spec or "").strip()
    if not raw or raw == CHANNEL_SELF:
        pkg = self_package_root()
        ok, missing, detail = _inspect(pkg)
        if not ok:
            raise CliError("当前这份 CLI 自身不完整，缺：%s" % "；".join(missing),
                           code=EXIT_USAGE,
                           hint="用 `daniel pack --check <包目录>` 核对这份包，或换一份完整的包")
        return _result(CHANNEL_SELF, detail, "当前这份 CLI 自己（`--from` 未给：装的就是手上这一份包）",
                       raw, [])

    if raw.lower().startswith("npm:") or raw.lower().startswith("npm/"):
        raise CliError("本票不支持 npm 渠道的取包：%s" % raw, code=EXIT_USAGE,
                       hint=NPM_CHANNEL_NOTE)

    p = _abspath(raw)
    if not os.path.isdir(p):
        raise CliError("`--from` 指的目录不存在：%s" % p, code=EXIT_USAGE,
                       hint="给一个**包目录**（含 `data/daniel-cli/` 或 `bin/daniel`）或"
                            "`daniel pack --out` 出的产物目录；不给则用当前这一份包")
    tried = _pkg_candidates(p)
    for cand in tried:
        if os.path.isfile(os.path.join(cand, "bin", "daniel")):
            ok, missing, detail = _inspect(cand)
            if not ok:
                raise CliError("这份包不完整（%s），缺：%s" % (cand, "；".join(missing)),
                               code=EXIT_USAGE,
                               hint="重新出一份（`daniel pack --out <目录> --confirm`）后重试；"
                                    "缺 `.kol-tools/daniel_client.py` 时说明拿到的只是"
                                    "命令行那一半，不是完整能力包")
            return _result(CHANNEL_DIR, detail,
                           "本地产物目录：%s（认出包根 %s）" % (p, cand), raw, tried)
    raise CliError("这个目录里没有找到一个完整的 CLI 包：%s" % p, code=EXIT_USAGE,
                   hint="检查过的候选：%s；应当有 `bin/daniel` ＋ `daniel_cli/schema.py` ＋ "
                        "`mcp/server.py` ＋ `mcp/corpus/kol-*/SKILL.md`，且仓库根含 `.kol-tools/`"
                        % "、".join(tried))


def _result(channel, detail, note, raw, tried):
    return {
        "渠道": channel,
        "包根": detail["包根"],
        "仓库根": detail["仓库根"],
        "入口": detail["入口"],
        "语料根": detail["语料根"],
        "能力域": detail["能力域"],
        "能力域数": detail["能力域数"],
        "仓库根含 .kol-tools": detail["仓库根含 .kol-tools"],
        "来源说明": note,
        "用户给的参数": raw or None,
        "被检查过的候选": tried,
        "将来换渠道只换哪里": "daniel_cli/install/source.py::resolve()（四步与用户命令逐字不变）",
    }


def skill_names(src):
    """该包随包的 8 束能力束**从盘上算出来**（不手抄清单；缺了就少一条，如实体现）。"""
    corpus = src["语料根"]
    if not os.path.isdir(corpus):
        return []
    return sorted(d for d in os.listdir(corpus)
                  if d.startswith("kol-") and os.path.isfile(os.path.join(corpus, d, "SKILL.md")))


def skill_source(src, name):
    return os.path.join(src["语料根"], name)


__all__ = ["CHANNEL_SELF", "CHANNEL_DIR", "CHANNEL_NPM", "NPM_CHANNEL_NOTE",
           "self_package_root", "repo_root_of", "resolve", "skill_names", "skill_source"]
