#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daniel Copilot 的 MCP server（stdio · TICKET-153 Part A）。

它做什么
--------
把已经剥离好的 `data/daniel-cli` 能力**原样**暴露成一个 MCP server，让别的宿主（Cursor 3.24.12
是本票的目标宿主）能像 DSH 一样调用同一条工序。本文件**不重新实现任何业务逻辑**：
每一次 `tools/call` 都落成一次真实子进程调用

    <python> data/daniel-cli/bin/daniel <模块> <子命令> --json …

然后解析 stdout 的 JSON 信封，取其中的 `data` 作为工具结果。

单一真源（不许有第二份工具清单）
--------------------------------
工具清单**不是**在这里手写的，而是从 `daniel_cli.schema`（唯一真源）经 `exports.mcp_tools()`
派生出来的 —— 与 `daniel schema --mcp --json` 输出的是同一份。清单一旦漂移，
`client_check.py` 的键比对会当场报出来。

能力面全量可见，写动作一律不由 AI 执行（TICKET-161 口径；三条口径都从真源派生，不是手写名单）
------------------------------------------------------------------------------------------------
  ① `annotations.readOnlyHint is True`
     —— 只读性固定的命令（读链）：**直接执行**；
  ② `annotations.readOnly == "contract-dependent"`
     且该命令 `writeStage == "sandbox"`
     —— 只读性取决于契约、且写动作只落在本次运行沙箱目录里的命令（目前只有 `playbook run`）：
     可执行，但**永不转发 `--confirm`**，因此契约里若真含写步骤，只会拿到退出码 3（需确认）；
  ③ 其余全部写链命令（品牌／名单的增删改、检索提交、采集触发、登录落地会话…）
     —— 注册为**确认单工具**：调用它**只返回一份确认单**（将执行的确切命令／动作类型／
     影响面／不可逆性／所需前置／替代路径），**永不执行**、**永不转发 `--confirm`**、
     **不产生任何副作用**（影响面只来自只读预查）。退出码语义与 CLI 对齐：3＝需确认。

两条模式的定位（用户 2026-10-15 裁决）：**CLI＝完整能力集成的落地形态**（写链人工确认后
真执行）；**MCP＝Daniel 数据层接入面**（能力模块调度，读链执行、写链只出确认单）。
所以两种模式在**能力面上完全一样**，差异只在「**谁执行**」这一层 —— 因此 `initialize` 的回包里
写的是「写链＝确认单通道」，而不是"写链不暴露"。

安全纪律
--------
  · **凭据值绝不进任何输出**：子进程环境只透传白名单（`DANIEL_HOME` 等落点类变量），
    `DANIEL_PASSWORD` / `DANIEL_EMAIL` / `DANIEL_KEYCHAIN_ACCOUNT` / `DANIEL_ALLOW_PLAINTEXT`
    一律不传；万一它们出现在任何要输出的文本里，还会被就地替换成 `<已隐去>`；
  · **stdout 只跑协议**：任何诊断只走 stderr，否则宿主会把日志当协议帧解析；
  · 不触发任何采集、不做任何飞书写操作。

用法
----
  python3 data/daniel-cli/mcp/server.py                 # stdio 常驻（宿主这么起它）
  python3 data/daniel-cli/mcp/server.py --list-tools    # 打印将要注册的工具清单（排障）
  python3 data/daniel-cli/mcp/server.py --describe      # 打印暴露口径与数量
  python3 data/daniel-cli/mcp/server.py --self-test     # 自检（正控＋退化输入）
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))               # 定位用：解析软链
PKG_ROOT = os.path.dirname(HERE)                                  # data/daniel-cli
REPO_ROOT = os.path.dirname(os.path.dirname(PKG_ROOT))            # 工作区根
DANIEL_BIN = os.path.join(PKG_ROOT, "bin", "daniel")

if PKG_ROOT not in sys.path:
    sys.path.insert(0, PKG_ROOT)

from daniel_cli import CLI_NAME                                # noqa: E402
from daniel_cli import __version__ as CLI_VERSION                 # noqa: E402
from daniel_cli import authgate                                   # noqa: E402
from daniel_cli.exits import (EXIT_INTERNAL, EXIT_NEEDS_CONFIRM,  # noqa: E402
                              EXIT_OK, EXIT_USAGE, name_of)
from daniel_cli import exports as _exports                        # noqa: E402（暴露档位唯一真源）
from daniel_cli.exports import arg_name, mcp_tools, tool_name     # noqa: E402
from daniel_cli.schema import SCHEMA                              # noqa: E402

SERVER_NAME = "daniel-copilot"
SERVER_TITLE = "Daniel Copilot（只读能力）"
SERVER_VERSION = "0.1.0"
SERVER_WEBSITE = "https://github.com/local/daniel-copilot"

#: 本 server 认得的协议版本（收到哪个就回哪个；不在表里的回我们最新的那个）
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
LATEST_PROTOCOL = SUPPORTED_PROTOCOLS[0]

#: 传给子进程的环境变量白名单。**只有这些**；其余（含一切凭据类变量）一律不传。
ENV_ALLOWLIST = (
    "PATH",                       # 找 python3 / 系统工具（本 server 自身用 sys.executable 起 CLI）
    "HOME",                       # 钥匙串与 ~ 展开（凭据「来源」需要，凭据「值」不需要）
    "TMPDIR",                     # 契约引擎自建临时沙箱的落点
    "LANG", "LC_ALL", "LC_CTYPE",  # 编码环境
    "PYTHONIOENCODING",
    "DANIEL_HOME",                # 数据落点（本票明确要求透传）
    "DANIEL_CLI_TOOLS",           # 能力目录（.kol-tools）显式覆盖
    "DANIEL_CONTRACTS_DIR",       # 契约目录覆盖
    "DANIEL_PLAYBOOK_SANDBOX",    # 契约运行的沙箱落点（跨宿主比对要可指定，否则落点随机）
)

#: 这些变量的**值**属于凭据（或能开启明文降级），既不透传、也不允许出现在任何输出里。
SENSITIVE_ENV = (
    "DANIEL_PASSWORD", "DANIEL_EMAIL", "DANIEL_KEYCHAIN_ACCOUNT",
    "DANIEL_ALLOW_PLAINTEXT", "DANIEL_TOKEN", "DANIEL_SESSION", "DANIEL_API_KEY",
)
REDACTED = "<已隐去>"

INSTRUCTIONS = (
    "Daniel Copilot 的能力面（读链 ＋ 写链确认单）。工具清单由 "
    "data/daniel-cli/daniel_cli/schema.py 单一真源派生，"
    "与 `daniel schema --mcp --json` 完全一致。"
    "**两种模式的定位**：CLI＝完整能力集成的落地形态（写链在人工确认 `--confirm` 后真执行）；"
    "MCP＝Daniel 数据层接入面（能力模块调度）。所以两种模式在能力面上**完全一样**，"
    "差异只在「谁执行」这一层。"
    "**写链＝确认单通道**：品牌与名单的增删改、检索提交、提及与声量的采集触发、"
    "合作活动新建、通路扫描、接管写链验收、账号登录等写命令**都已注册为工具**，"
    "但它们是**确认单工具** —— 调用后**只返回一份确认单**"
    "（将执行的确切命令／动作类型／影响面／不可逆性／所需前置／替代路径），"
    "**永不执行**、**永不转发 `--confirm`**、**不产生任何副作用**"
    "（影响面只来自只读预查）。要真执行，请把确认单里的命令拿到 CLI 由人跑。"
    "退出码语义与 CLI 对齐：3＝需确认（**不是**成功）。"
    "读链工具（只读）与沙箱工序引擎（`daniel_playbook_run`，写动作只落本次运行沙箱）会真执行，"
    "但不会触发任何真实采集，也不会对飞书做任何写操作。"
    "**业务语料随服务分发**：8 束 KOL 能力域的判据语料（版本见 `daniel_skills_list`）"
    "就打包在本服务目录内的 `mcp/corpus/`，按**服务自身位置**定位 —— 不需要宿主去读 "
    "`~/.agents/skills/`，也不依赖任何其它安装步骤。用 `daniel_skills_list` 列能力域，"
    "用 `daniel_skills_read` 按切片读判据原文（**先看切片清单再按 --section 读正文**，"
    "整束约 995 KB，不要一次全读）；支持 resources 的宿主也可以用 "
    "`daniel-copilot://skills/<域>/<切片号>` 直接读某一片。"
    "🔴 **授权是起点（TICKET-194）**：未登录时业务模块工具**一律不放行** —— 调用后返回"
    "**结构化「未登录」错误**（`isError=true`、`structuredContent.未登录=true`、"
    "`authenticated=false`、带 `fix` 一行修法），**不是空数据**；接入／自救／随包自检三类工具"
    "（`daniel_auth_status`、`daniel_account_login`、`daniel_schema_*`、`daniel_connect_*` 等）"
    "仍可用。登录请走浏览器：`daniel account login --browser` —— 账号密码**只在 Daniel 页面上**输。"
)

#: 语料 resource 的 URI 方案（宿主不支持 resources 也没关系，工具路径已全覆盖）
RESOURCE_SCHEME = "daniel-copilot"


# ═══════════════ 写链＝确认单通道：动作事实表（TICKET-161） ═══════════════
#: 确认单的「动作类型」是**闭合枚举**：需求稿的五类写动作 ＋ 一档显式的「其他（本机副作用）」。
#: 不写成随手自由文本 —— 取值只能落在这六个字面值里（`--self-test` 逐条断言）。
#:
#: **如实标注的产品事实**：当前 14 条写命令里，「同步飞书」与「对外发信」这两类
#: **还没有任何对应命令**（飞书写链整体后置，账号配额里虽有「每月邮件」一栏，但 CLI 侧
#: 没有对外发信命令）。确认单通道为这两类**留位**，但今日无命令可出它们的确认单 ——
#: 不许假装覆盖了五类。覆盖率见 `describe()["actionCoverage"]`。
ACTION_SYNC_FEISHU = "同步飞书"
ACTION_WRITE_RECORD = "写 Daniel 记录"
ACTION_SEND_OUT = "对外发信"
ACTION_DELETE = "删除类"
ACTION_TRIGGER_COLLECT = "触发采集"
ACTION_LOCAL_SIDE_EFFECT = "其他（本机副作用）"
ACTION_TYPES = (ACTION_SYNC_FEISHU, ACTION_WRITE_RECORD, ACTION_SEND_OUT,
                ACTION_DELETE, ACTION_TRIGGER_COLLECT, ACTION_LOCAL_SIDE_EFFECT)
#: 需求稿的五类（`其他（本机副作用）`不在这五类里，但同样属"AI 不得自行执行"）。
FIVE_CATEGORIES = (ACTION_SYNC_FEISHU, ACTION_WRITE_RECORD, ACTION_SEND_OUT,
                   ACTION_DELETE, ACTION_TRIGGER_COLLECT)

#: 每条确认单工具的**动作事实**。本表**不含任何执行逻辑** —— 它只描述"确认单上要写什么"：
#:   · `动作类型`／`属于五类`：闭合枚举（见上），机器可判；
#:   · `不可逆性`：一句话，写明为什么；
#:   · `消耗配额`：`True`／`False`／`"未知（无只读判据）"`（没有判据就不下结论，不编）；
#:   · `影响面对象`／`影响面条数`：模板，`{参数名}` 由**本次调用的实参**填，
#:      缺参原样显示 `<未给出>`（不编造、不留空）；
#:   · `只读替代`：不改任何东西的等价做法；
#:   · `预查`：只读预查清单 —— **影响面只能来自只读预查**，
#:      绝不为了拿影响面去跑那条写命令（`_ticket_probes()` 会逐条断言预查命令是只读的）。
#: 公共预查（`account whoami` 取工作区、`account capabilities` 取写权限与配额）由代码统一追加。
CONFIRM_TICKET = {
    "brands.create": {
        "动作类型": ACTION_WRITE_RECORD, "属于五类": True,
        "不可逆性": "低 —— 新建对象；建错了可以再删（删除另需一次确认），"
                    "但这次调用会留在本机写审计里",
        "消耗配额": False,
        "影响面对象": "在目标工作区新建品牌「{name}」",
        "影响面条数": "1 个品牌（新建）；该账号当前可见品牌数见只读预查",
        "只读替代": "daniel brands list（看已有哪些品牌，确认不是重名）",
        "预查": [{"模块": "brands", "子命令": "list", "参数": [],
                  "用途": "看现有品牌（判断是否重名，并给出现有品牌数）"}],
    },
    "brands.update": {
        "动作类型": ACTION_WRITE_RECORD, "属于五类": True,
        "不可逆性": "中 —— 被改字段的**原值不会被本 CLI 留底**，改完不能自动还原",
        "消耗配额": False,
        "影响面对象": "改品牌「{brand}」的资料",
        "影响面条数": "1 个品牌（改字段；具体改了哪些字段见「将执行的确切命令」）",
        "只读替代": "daniel brands show --brand {brand}（先看清改前是什么）",
        "预查": [{"模块": "brands", "子命令": "show", "参数": [("--brand", "{brand}")],
                  "用途": "确认品牌存在，并留下改前事实"}],
    },
    "brands.delete": {
        "动作类型": ACTION_DELETE, "属于五类": True,
        "不可逆性": "**高（不可逆）** —— 品牌删除后本 CLI 没有任何撤回手段；"
                    "命令还额外要求 `--delete-token`（把品牌名原样再写一遍）",
        "消耗配额": False,
        "影响面对象": "删除品牌「{brand}」",
        "影响面条数": "1 个品牌（删除）；该品牌下的名单条数见只读预查",
        "只读替代": "daniel brands show --brand {brand}（看清要删的是什么）、"
                    "daniel lists by-brand --brand {brand}（看会牵连多少名单）",
        "预查": [{"模块": "brands", "子命令": "show", "参数": [("--brand", "{brand}")],
                  "用途": "确认品牌存在并取品牌名（删除时要把这个名字原样再写一遍）"},
                 {"模块": "lists", "子命令": "by-brand", "参数": [("--brand", "{brand}")],
                  "用途": "看该品牌下现有名单数（删除会牵连到的对象规模）"}],
    },
    "lists.create": {
        "动作类型": ACTION_WRITE_RECORD, "属于五类": True,
        "不可逆性": "低 —— 新建对象；建错了可以再删（删除另需一次确认）",
        "消耗配额": False,
        "影响面对象": "在品牌「{brand}」下新建名单「{name}」",
        "影响面条数": "1 个名单（新建，初始 0 条红人）；"
                      "该品牌现有名单数见只读预查（建后 +1）",
        "只读替代": "daniel lists by-brand --brand {brand}（看该品牌现有名单，作为建前基线）",
        "预查": [{"模块": "brands", "子命令": "show", "参数": [("--brand", "{brand}")],
                  "用途": "确认品牌存在并取品牌名"},
                 {"模块": "lists", "子命令": "by-brand", "参数": [("--brand", "{brand}")],
                  "用途": "看该品牌现有名单数（建后应为 +1）"}],
    },
    "lists.rename": {
        "动作类型": ACTION_WRITE_RECORD, "属于五类": True,
        "不可逆性": "低 —— 名字可以再改回去，但旧名不会自动留底",
        "消耗配额": False,
        "影响面对象": "把名单 {list_id}（品牌「{brand}」）改名为「{name}」",
        "影响面条数": "1 个名单（改名）；该名单现有条目数见只读预查",
        "只读替代": "daniel lists by-brand --brand {brand}（确认目标名单编号与当前名字）",
        "预查": [{"模块": "lists", "子命令": "by-brand", "参数": [("--brand", "{brand}")],
                  "用途": "确认目标名单存在并取当前名字"}],
    },
    "lists.delete": {
        "动作类型": ACTION_DELETE, "属于五类": True,
        "不可逆性": "**高（不可逆）** —— 名单删除后本 CLI 没有任何撤回手段；"
                    "命令还额外要求 `--delete-token`（把名单名原样再写一遍）",
        "消耗配额": False,
        "影响面对象": "删除名单 {list_id}（品牌「{brand}」）",
        "影响面条数": "1 个名单（删除）；该名单当前条目数见只读预查",
        "只读替代": "daniel lists by-brand --brand {brand}（看清要删的是哪个名单、里面有多少人）",
        "预查": [{"模块": "lists", "子命令": "by-brand", "参数": [("--brand", "{brand}")],
                  "用途": "确认目标名单存在，并取名单名（删除时要把这个名字原样再写一遍）"
                          "与条目数"}],
    },
    "search.submit": {
        "动作类型": ACTION_TRIGGER_COLLECT, "属于五类": True,
        "不可逆性": "**高** —— 检索任务一经提交即消耗当月检索额度，且没有撤回命令",
        "消耗配额": True,
        "影响面对象": "为品牌「{brand}」提交一条红人检索：「{query}」",
        "影响面条数": "1 次检索任务（会真的发起）；检索额度用量见只读预查",
        "只读替代": "daniel search history（看最近的检索记录，确认这条检索还没有提过）",
        "预查": [{"模块": "search", "子命令": "history", "参数": [("--limit", 5)],
                  "用途": "看最近的检索记录（确认没有重复提交，并给出现有记录数）"}],
    },
    "mentions.run": {
        "动作类型": ACTION_TRIGGER_COLLECT, "属于五类": True,
        "不可逆性": "**高** —— 会真的抓取并入库，采集用量随之产生，没有撤回命令",
        "消耗配额": True,
        "影响面对象": "为品牌「{brand}」发起一次品牌提及分析（回溯 {days} 天）",
        "影响面条数": "1 次提及分析任务（会真的采集并入库）；该品牌已有任务数见只读预查",
        "只读替代": "daniel mentions jobs --brand {brand}（看已有任务与状态）、"
                    "daniel mentions results --brand {brand}（看已入库的结果）",
        "预查": [{"模块": "mentions", "子命令": "jobs", "参数": [("--brand", "{brand}")],
                  "用途": "看该品牌已有提及分析任务（避免重复采集）"}],
    },
    "sov.run-exposure": {
        "动作类型": ACTION_TRIGGER_COLLECT, "属于五类": True,
        "不可逆性": "**高** —— 会真的触发曝光采集并入库，没有撤回命令",
        "消耗配额": True,
        "影响面对象": "为品牌「{brand}」发起一次曝光采集（市场 {country}）",
        "影响面条数": "1 次曝光采集任务（会真的采集并入库）；当前声量基线见只读预查",
        "只读替代": "daniel sov overview --brand {brand}（看当前声量总览，作为采集前基线）",
        "预查": [{"模块": "sov", "子命令": "overview",
                  "参数": [("--brand", "{brand}"), ("--country", "{country}")],
                  "用途": "取采集前的声量基线（只读）"}],
    },
    "ct.create-campaign": {
        "动作类型": ACTION_WRITE_RECORD, "属于五类": True,
        "不可逆性": "中 —— 活动**名称建后不可改**（只能再建一个），删除也没有对应命令",
        "消耗配额": False,
        "影响面对象": "在品牌「{brand}」下新建合作活动「{title}」（{start} 起）",
        "影响面条数": "1 个合作活动（新建）；该品牌现有活动数见只读预查",
        "只读替代": "daniel ct campaigns --brand {brand}（看已有活动，确认不是重复建）",
        "预查": [{"模块": "ct", "子命令": "campaigns", "参数": [("--brand", "{brand}")],
                  "用途": "看该品牌已有活动数（判断是否重复）"}],
    },
    "route.sweep": {
        "动作类型": ACTION_TRIGGER_COLLECT, "属于五类": True,
        "不可逆性": "低 —— 不改任何业务数据；但含**一次非只读探测**，会留下调用痕迹",
        "消耗配额": "未知（探测是否计入配额没有只读判据，不下结论）",
        "影响面对象": "全量扫描通路可用性（含一次非只读探测）",
        "影响面条数": "通路条数见只读预查（route catalog 是离线命令，不联网）",
        "只读替代": "daniel route catalog（列出可探测的通路清单，离线）、"
                    "daniel route probe（只读探测单条通路）",
        "预查": [{"模块": "route", "子命令": "catalog", "参数": [],
                  "用途": "列出可探测通路清单（离线，不联网，零副作用）"}],
    },
    "takeover.check-writes": {
        "动作类型": ACTION_WRITE_RECORD, "属于五类": True,
        "不可逆性": "中 —— 这是**含写链**的接管验收：它会真的执行写链检查"
                    "（否则验不出写能力），因此会留下写痕迹",
        "消耗配额": False,
        "影响面对象": "对品牌「{brand}」跑一次含写链的接管验收",
        "影响面条数": "本次扫描区块的写链检查项；区块与只读检查项见只读预查",
        "只读替代": "daniel takeover check --brand {brand}（只读接管验收，"
                    "覆盖品牌／提及／情报／声量／真实性五块）",
        "预查": [{"模块": "takeover", "子命令": "check", "参数": [("--brand", "{brand}")],
                  "用途": "先跑只读接管验收当基线，看这次会扫哪些区块"}],
    },
    "account.login": {
        "动作类型": ACTION_LOCAL_SIDE_EFFECT, "属于五类": False,
        "不可逆性": "低 —— 只写**本机会话文件**（刷新凭据落地），重新登录即可；"
                    "不写任何 Daniel 数据、不对外发信",
        "消耗配额": False,
        "影响面对象": "刷新本机会话文件（重新登录）",
        "影响面条数": "1 次登录（会话落地）；当前会话是否还有效见只读预查",
        "只读替代": "daniel account whoami（先看当前会话是否还有效 —— 有效就不必登录）",
        "预查": [{"模块": "account", "子命令": "whoami", "参数": [],
                  "用途": "确认当前会话状态（登录会刷新它）"}],
    },
    # TICKET-170 新增的写命令（`account credentials-set`，writeStage=live）。
    # 动作事实由 TICKET-161 补齐（总监 2026-10-15 裁决：mcp/** 归 161）——
    # 只写**该命令自己能自证的事实**（取自它 schema 声明里的 writeNote／returns），
    # 不替它写"影响面该长什么样"。
    "account.credentials-set": {
        "动作类型": ACTION_LOCAL_SIDE_EFFECT, "属于五类": False,
        "不可逆性": "低 —— 只写**本机系统钥匙串**（同一账号可再次写入覆盖），"
                    "不写任何 Daniel 数据、不对外发信",
        "消耗配额": False,
        "影响面对象": "把 Daniel 登录凭据写进本机系统钥匙串",
        "影响面条数": "1 次写入（覆盖本机钥匙串里同一账号的凭据）；"
                      "当前凭据来源与钥匙串可用性见只读预查",
        "只读替代": "daniel account credentials（看凭据从哪来：钥匙串／环境变量／明文文件，"
                    "只回掩码邮箱）",
        "预查": [{"模块": "account", "子命令": "credentials", "参数": [],
                  "用途": "看当前凭据来源与钥匙串可用性（写入前基线；只读，不回显任何凭据值）"}],
    },
    # ── TICKET-194 补齐的 5 行（总监 2026-10-16 裁决 · CLS-85 的同期欠账）──
    # 这 5 条写命令是在 TICKET-186／189／193 期间**新增**的，当时漏登记这张事实表
    # （`mcp/server.py --self-test` 的正控（161）因此一直是 45/46，且**没有任何门禁消费它**）。
    # 本段**只补这 5 行**：既有 14 行一字不动、那条断言一个字不改；
    # 每行的动作事实都**对着该命令自己的实现**写（实现里写了什么，这里就写什么），不照抄命令名凑数。
    # 命令来源：`account.switch`＝TICKET-186 A2；`connect.apply／uninstall`＝TICKET-189；
    #          `ct.delete-campaign`＝TICKET-188；`pack.out`＝TICKET-193。
    "account.switch": {
        # 事实来源：`commands/mod_account.py::_switch_plan／_switch_run` —— 它自己写着
        # "只写本机的一个账号指针文件并建目录（可逆）；**不写任何凭据、不删改任何既有数据**、
        #  不联网、不动 Daniel 侧任何数据"。
        "动作类型": ACTION_LOCAL_SIDE_EFFECT, "属于五类": False,
        "不可逆性": "低 —— 只写**本机的账号指针文件**（`<数据落点根>/accounts/_state.json`，"
                    "权限 600）并建该账号的分区目录；再切回去即恢复，"
                    "**不删任何文件、不搬任何文件、不写不改任何凭据**",
        "消耗配额": False,
        "影响面对象": "把本机当前账号切到「{账号}」（或 `--clear` 取消当前账号、回到根落点）",
        "影响面条数": "1 个指针文件 ＋ 该账号的分区目录（幂等）；"
                      "切换前后的落点与既有数据是否被动见只读预查",
        "只读替代": "daniel account list（看当前账号与已存账号、各自分区）／"
                    "daniel account paths（看当前生效落点与分区规则）",
        "预查": [{"模块": "account", "子命令": "paths", "参数": [],
                  "用途": "切换前记下落点事实（根在哪、当前分区在哪），切换后可逐条对账"},
                 {"模块": "account", "子命令": "list", "参数": [],
                  "用途": "看本机已存账号与钥匙串条目（判断目标账号有没有可复用凭据）"}],
    },
    "connect.apply": {
        # 事实来源：`commands/mod_connect.py::_plan_common／_run_common` ＋ `connect/hosts.py` ——
        # 它改的是**宿主配置文件**（Cursor 的 mcp.json／Codex 的 config.toml），幂等合并、
        # 只动本产品那一条，写前落快照、写后回读对账；不碰 Daniel 侧任何数据。
        "动作类型": ACTION_LOCAL_SIDE_EFFECT, "属于五类": False,
        "不可逆性": "低 —— 只改**本机宿主配置文件里本产品那一条**（其它 server／其它表与注释"
                    "逐字节不动）；写前把原文（含 sha256）落快照到数据落点的 `connect/snapshots/`，"
                    "要还原就 `--uninstall` 或把快照复制回去",
        "消耗配额": False,
        "影响面对象": "把 Daniel CLI 接进宿主「{host}」的配置文件",
        "影响面条数": "1 个配置文件的 1 个条目（幂等：内容已一致时只回读、不改文件）；"
                      "该宿主的当前接入状态与逐行 diff 见只读预查",
        "只读替代": "daniel connect --list（各宿主接没接上）／"
                    "daniel connect --host {host} --print（只打印将要写入的那一段，不改任何文件）",
        "预查": [{"模块": "connect", "子命令": "list", "参数": [],
                  "用途": "看本机各宿主的接入状态（写前基线）"},
                 {"模块": "connect", "子命令": "print", "参数": [("--host", "{host}")],
                  "用途": "打印将写入的那一段片段（与 apply 同源，用于逐字比对）"}],
    },
    "connect.uninstall": {
        # 事实来源：`connect/hosts.py::uninstall` —— 只删本产品那一条，别的内容原样保留。
        "动作类型": ACTION_DELETE, "属于五类": True,
        "不可逆性": "中 —— 从**本机宿主配置文件**里删掉本产品那一条目；"
                    "别的内容原样保留，写前落快照可回插，但被删掉的那一段要重新 `--apply` 才回来",
        "消耗配额": False,
        "影响面对象": "从宿主「{host}」的配置里删掉 Daniel 那一条",
        "影响面条数": "1 个配置文件的 1 个条目（其它 server／表与注释不动）；"
                      "该宿主的当前接入状态见只读预查",
        "只读替代": "daniel connect --list（先看该宿主当前接的是不是本产品这一条）",
        "预查": [{"模块": "connect", "子命令": "list", "参数": [],
                  "用途": "确认该宿主当前确实接了本产品（避免误删别人的条目）"}],
    },
    "ct.delete-campaign": {
        # 事实来源：`commands/mod_ct.py::_plan_delete_campaign／_run_delete_campaign` ——
        # 它自己写着"**不可逆**，活动与其关联数据一并消失"，且是删除类（需 `--delete-token`）。
        "动作类型": ACTION_DELETE, "属于五类": True,
        "不可逆性": "**高（不可逆）** —— 删除的是 Daniel 里的合作活动，"
                    "活动与其关联数据一并消失，本 CLI 没有任何撤回手段；"
                    "命令还额外要求 `--delete-token`（把活动标题原样再写一遍）",
        "消耗配额": False,
        "影响面对象": "删除品牌「{brand}」下的合作活动「{campaign}」",
        "影响面条数": "1 个合作活动（删除）；该活动当前的状态／活动码／关联条数见只读预查",
        "只读替代": "daniel ct campaigns --brand {brand}（先看清这个品牌下有哪些活动、编号是多少）",
        "预查": [{"模块": "ct", "子命令": "campaigns", "参数": [("--brand", "{brand}")],
                  "用途": "列出该品牌下的活动，确认要删的那一条存在且编号无误"}],
    },
    "install.run": {
        # 事实来源：`commands/mod_install.py::_plan_run／_run_run` ＋ `install/wizard.py` ——
        # 它做四件事：① 入口软链进 PATH ② 8 束 `kol-*` 软链进宿主技能目录
        # ③ **调 `daniel connect --host <宿主> --apply --confirm`**（不重造接入）④ 起登录
        # （浏览器授权路，绝不索要账号密码）。写的是**本机安装落点**，不碰 Daniel 任何数据。
        "动作类型": ACTION_LOCAL_SIDE_EFFECT, "属于五类": False,
        "不可逆性": "低 —— 只动**本机**三处：`~/.local/bin/daniel` 一条软链 ＋ shell 配置里一行 PATH、"
                    "宿主技能目录下 8 条 `kol-*` 软链、宿主配置里本产品那一条（**只经 connect 写**）。"
                    "写前把原文落进 `<数据落点>/install/snapshots/<时间戳>/`，四步都是**幂等**的"
                    "（已是目标状态就不改文件），输出里带逐条回滚命令；不改任何 Daniel 数据",
        "消耗配额": False,
        "影响面对象": "在本机装好 Daniel CLI（入口 ＋ 8 束能力束 ＋ 宿主接入 ＋ 登录态）",
        "影响面条数": "3 处落点（入口软链 1 条／技能软链 8 条／宿主配置 1 个条目）；"
                      "本次会不会真改、改哪几处见只读预查（`install` 的干跑计划）",
        "只读替代": "daniel install（不带 `--confirm` 即干跑：只打印四步计划，零写入，退出码 3）／"
                    "daniel install --check（只读自检：入口／能力束／接入 doctor／登录态）",
        "预查": [{"模块": "install", "子命令": "check", "参数": [],
                  "用途": "看本机当前装成什么样、还差哪一步（写前基线，只读）"}],
    },
    "install.upgrade": {
        # 事实来源：同上 ＋ `install/wizard.py::upgrade_plan／upgrade_run` ——
        # 把入口与 8 束软链**改指**到 `--from` 那一份包，并经 `connect` 刷新宿主接入；
        # 随后**自动重跑 `install --check`**，自检不过即非零退出。
        "动作类型": ACTION_LOCAL_SIDE_EFFECT, "属于五类": False,
        "不可逆性": "低 —— 只把本机那几处**改指**到另一份包（写前同样落快照）；升回原来的包即还原；"
                    "不改任何 Daniel 数据",
        "消耗配额": False,
        "影响面对象": "把本机安装就地改指到 `--from` 指定的那一份包，并重跑自检",
        "影响面条数": "入口软链 1 条 ＋ 技能软链 8 条 ＋ 宿主配置 1 个条目；升级后自检的逐项结论"
                      "会一并返回",
        "只读替代": "daniel install --check（升级前后都用它复核）／"
                    "daniel install --upgrade --from <包目录>（不带 `--confirm` 即干跑）",
        "预查": [{"模块": "install", "子命令": "check", "参数": [],
                  "用途": "看升级前的装态（写前基线，只读）"}],
    },
    "pack.out": {
        # 事实来源：`commands/mod_pack.py::_plan_out／_run_out` ＋ `pack/builder.py` ——
        # 只在指定输出目录里做一份**完整拷贝**（按规则排除凭据与用户数据），
        # 包目录必须为空且在工作区之外；不碰 Daniel 任何数据。
        "动作类型": ACTION_LOCAL_SIDE_EFFECT, "属于五类": False,
        "不可逆性": "低 —— 只在**你指定的输出目录**里写出一份拷贝（包目录必须为空且在工作区之外）；"
                    "删掉那个目录即完全撤销，**不动源目录、不动 Daniel 任何数据**",
        "消耗配额": False,
        "影响面对象": "在「{out}」下写出一份可交付的能力包（目录形态）",
        "影响面条数": "按规则复算的包含文件数（出包清单逐项可对账，清单落在包目录**之外**）；"
                      "本次包含多少／排除多少见只读预查",
        "只读替代": "daniel pack --out {out}（不带 `--confirm` 即干跑：只打印将包含／排除什么）／"
                    "daniel pack --check <已有包目录>（对一份包跑五条只读自检）",
        "预查": [],
    },
}

#: 每条确认单工具都会跑的**公共只读预查**（工作区 ＋ 写权限 ＋ 配额）。
COMMON_PROBES = (
    {"模块": "account", "子命令": "whoami", "参数": [],
     "用途": "取本次调用的账号与当前工作区"},
    {"模块": "account", "子命令": "capabilities", "参数": [],
     "用途": "取写权限判据与配额（结论与实际写门禁同源）"},
)

#: 确认单**必须**有的字段（缺一个即红；`--self-test` 与 `client_check.py` 两侧都断言）。
TICKET_FIELDS = ("将执行的确切命令", "动作类型", "影响面", "不可逆性", "所需前置", "替代路径")


# ─────────────────────────── 工具注册表（从单一真源派生） ───────────────────────────
def _command_index():
    """`<工具名>` → `(模块定义, 命令定义)`。名字由 `exports.tool_name` 算，不手写。"""
    idx = {}
    for mod in SCHEMA["modules"]:
        for cmd in mod["commands"]:
            idx[tool_name(mod["key"], cmd["name"])] = (mod, cmd)
    return idx


def _option_map(cmd):
    """MCP 属性名 → CLI 选项名（含位置参数的 `--同名` 等价写法）。

    位置参数（如 `playbook run <契约>`）在 schema 里声明了等价的 `--name 契约`，
    两者 `arg_name()` 相同，这里按 CLI 选项优先，避免把同一个 dest 传两遍。
    """
    m = {}
    for opt in cmd["options"]:
        key = arg_name(opt["name"])
        if key not in m or not opt.get("positional"):
            m.setdefault(key, opt["name"])
            if not opt.get("positional"):
                m[key] = opt["name"]
    return m


def _exposure(cmd):
    """暴露口径判定 —— **委托给唯一真源**（`TICKET-202`·`Q14`）。

    为什么不再在 server 里各判一次：先前协议面与自省载荷各写一套规则，结果"同一件事两种说法"
    （`run` 缺标准键、`deliver` 被当成纯只读）。现在两边都调 `exports.exposure_of(cmd)`，
    由 `client_check.py` 的 `exposure_mismatches()` 逐工具比对两个载荷，不一致即红。
    返回 `None` 表示**不注册**（四档之外没有第五种情形；保留这个分支只为让"不注册"这条路显式存在）。
    """
    exp = _exports.exposure_of(cmd)
    return exp if exp else None


#: 敏感参数的**显示占位符**：确认单里绝不打印原值（连掩码都不给，因为值本身没用）。
SECRET_PLACEHOLDER = "<在终端里自行输入>"


def _secret_arg_names(cmd, schema):
    """声明为**敏感**的参数名（MCP 侧 `arg_name` 形式）。

    两个来源都认，取并集（纵深防御，任一层标记都能生效）：
      · schema 里的 `o(..., secret=True)`（CLI 侧的声明）；
      · 派生出的 JSON Schema 属性上的 `"writeOnly": true`（`exports.py` 的派生形式）。
    """
    from_flag = {arg_name(o["name"]) for o in cmd["options"] if o.get("secret")}
    from_schema = {k for k, v in ((schema or {}).get("properties") or {}).items()
                   if isinstance(v, dict) and v.get("writeOnly")}
    return from_flag | from_schema


def _drop_secret_props(schema, secret):
    """确认单工具的 `inputSchema`：**剔除敏感参数**。

    为什么可以剔（这是本票最硬的一条）：确认单工具**永不执行** ⇒ 传进来的密码**没有任何用途**。
    接受一个"永不使用、却会被拼进提示串"的敏感参数，纯粹是**泄漏面**。
    剔除之后，确认单自然变成「把下面这条命令拿到终端里跑，密码你自己输」——
    与本项目「写动作由人拿到 CLI 执行」的立场完全一致。
    这是**按真源标记做的投影**（不是第二份参数定义）：投影规则只有一条，且由 `secret`／`writeOnly` 驱动。
    """
    if not secret:
        return schema, []
    props = {k: v for k, v in (schema.get("properties") or {}).items() if k not in secret}
    required = [k for k in (schema.get("required") or []) if k not in secret]
    return {"type": schema.get("type", "object"), "properties": props, "required": required,
            "additionalProperties": schema.get("additionalProperties", False)}, sorted(secret)


def _ticket_description(tool, cmd):
    """确认单工具的 description：真源描述 **＋** 一句暴露语义（不是另写一份描述）。

    为什么加这句：真源描述里写着「开放级别：真实执行已接通」（那是 **CLI 形态**的事实），
    宿主若只看这一句就会以为 MCP 侧也会执行 —— 加的这一句把两种形态的边界说清楚。
    """
    return ("%s ｜ **【MCP 确认单工具：本工具不会执行这个写动作】**"
            "调用后只返回一份确认单（将执行的确切命令／动作类型／影响面／不可逆性／"
            "所需前置／替代路径），不产生任何副作用、也不转发 `--confirm`；"
            "上面那句「真实执行已接通」说的是 **CLI 形态**（完整能力集成）—— "
            "要真执行请把确认单里的命令拿到终端加 `--confirm` 由人跑。"
            "退出码语义 3＝需确认（不是成功）。" % tool["description"])


def build_registry():
    """从单一真源派生要注册的工具清单（含排障元数据与参数映射）。"""
    index = _command_index()
    registry = {}
    for tool in mcp_tools():
        name = tool["name"]
        mod, cmd = index[name]
        ann = tool.get("annotations") or {}
        exposure = _exposure(cmd)
        if exposure is None:
            continue
        title = "%s · %s" % (mod["title"], cmd["summary"].split("（")[0].strip() or name)
        schema = tool["inputSchema"]                  # 原样派生，不二次编辑
        secret = _secret_arg_names(cmd, schema)
        dropped = []
        if exposure == "confirm-ticket":
            title = "【确认单】%s" % title
            description = _ticket_description(tool, cmd)
            # 敏感参数**不进 MCP 的 inputSchema**（详见 `_drop_secret_props` 的理由）
            schema, dropped = _drop_secret_props(schema, secret)
        else:
            description = tool["description"]
        registry[name] = {
            "tool": {
                "name": name,
                "title": title,
                "description": description,
                "inputSchema": schema,
                "annotations": {
                    "title": title,
                    # 读链（含"本机出件"档）：只有**纯只读**才是 readOnlyHint=True。
                    # `playbook deliver` 会往本机出件落点写文件 ⇒ 它**不是**纯只读（False），
                    # 但仍**可直接执行**（不是确认单工具）—— `TICKET-202`·`Q14`。
                    # 确认单工具**永不执行** ⇒ destructiveHint 必须给 False（不可能造成破坏），
                    # 且 idempotentHint=True（重复调用不改变任何东西）。
                    "readOnlyHint": exposure == "read-only",
                    "destructiveHint": False,
                    "idempotentHint": True,
                    "openWorldHint": True,
                },
                "_meta": {"daniel": {
                    "module": mod["key"],
                    "command": cmd["name"],
                    "exposure": exposure,
                    "writeStage": cmd.get("writeStage"),
                    # 本机写档／补充说明（`TICKET-202`·`Q14`）：让**只看工具定义**的人也能读出
                    # "会写本机出件落点、不写 Daniel 远端"；键名与自省载荷同一把（`readOnlyNote`）。
                    "localOutput": exposure == "local-output",
                    "readOnlyNote": ann.get("readOnlyNote") or cmd.get("localWriteNote"),
                    "executes": exposure != "confirm-ticket",
                    "actionType": (CONFIRM_TICKET.get("%s.%s" % (mod["key"], cmd["name"]))
                                   or {}).get("动作类型"),
                    # 透明登记：剔了哪些敏感参数、为什么（不静默改 schema）
                    "droppedSecretParams": dropped,
                    "droppedReason": ("确认单工具永不执行 ⇒ 敏感参数无用途，剔除以消除回显泄漏面"
                                      if dropped else None),
                    "cli": ann.get("cli"),
                    "generatedBy": SCHEMA["generatedBy"],
                }},
            },
            "module": mod["key"],
            "command": cmd["name"],
            "exposure": exposure,
            "writeStage": cmd.get("writeStage"),
            "cli": ann.get("cli"),
            "write": bool(cmd["write"]),
            "deleteTarget": cmd.get("deleteTarget"),
            "secret": sorted(secret),
            "options": _option_map(cmd),
            "required": sorted(arg_name(o["name"]) for o in cmd["options"]
                               if o.get("required") and not o.get("positional")),
            "repeat": sorted(arg_name(o["name"]) for o in cmd["options"] if o.get("repeat")),
            "flags": sorted(arg_name(o["name"]) for o in cmd["options"] if o["type"] == "flag"),
        }
    return registry


def action_coverage(registry):
    """动作类型覆盖率 ＋ **缺动作事实的命令**（如实标注，缺就是红，不许崩）。

    两条产品事实都在这里变成可机检的东西：
      · 「同步飞书」「对外发信」**没有对应命令** —— 通道为它们留位，但不假装覆盖五类；
      · 任何一条确认单工具如果**没有** `CONFIRM_TICKET` 行（例如新增了写命令却忘了登记动作事实），
        必须**被点名列出来**，而不是让取值变成 None 把报告带崩 ——
        `--self-test` 会对这个清单断言（非空＝红）。
    """
    used, unfactored, out_of_enum = {}, [], []
    for name, e in registry.items():
        if e["exposure"] != "confirm-ticket":
            continue
        act = (CONFIRM_TICKET.get("%s.%s" % (e["module"], e["command"])) or {}).get("动作类型")
        if not act:
            unfactored.append(name)
            continue
        if act not in ACTION_TYPES:
            out_of_enum.append("%s=%r" % (name, act))
            continue
        used.setdefault(act, []).append(name)
    return {
        "闭合枚举": list(ACTION_TYPES),
        "需求稿五类": list(FIVE_CATEGORIES),
        "今日有命令的类别": {k: sorted(v) for k, v in used.items()},
        "五类里今日无命令的类别": [a for a in FIVE_CATEGORIES if a not in used],
        "不属于五类的命令": {k: sorted(v) for k, v in used.items() if k not in FIVE_CATEGORIES},
        "缺动作事实的命令（非空＝红：写了新写命令但没登记它的动作事实）": sorted(unfactored),
        "动作类型越界的命令（非空＝红）": sorted(out_of_enum),
        "说明": "「同步飞书」「对外发信」今日无对应命令（飞书写链整体后置）——"
                "确认单通道为这两类留位，但不假装已覆盖。",
    }


def describe(registry):
    ro = sorted(k for k, v in registry.items() if v["exposure"] == "read-only")
    sb = sorted(k for k, v in registry.items() if v["exposure"] == "sandbox-only")
    ct = sorted(k for k, v in registry.items() if v["exposure"] == "confirm-ticket")
    lo = sorted(k for k, v in registry.items() if v["exposure"] == "local-output")
    corpus = _corpus_summary()
    return {
        "server": SERVER_NAME,
        "version": SERVER_VERSION,
        "cliVersion": CLI_VERSION,
        "generatedBy": SCHEMA["generatedBy"],
        "protocols": list(SUPPORTED_PROTOCOLS),
        "modePositioning": {
            "cli": "完整能力集成的落地形态：读链直接执行；写链在人工确认（--confirm）后**真执行**。",
            "mcp": "Daniel 数据层接入面（能力模块调度）：读链直接执行；写链**只出确认单、永不执行**。",
            "能力面": "两种模式的能力面**完全一样**（同一份单一真源派生）；"
                      "差异只在「谁执行」这一层。",
        },
        "exposureRule": {
            "read-only": "annotations.readOnlyHint is True（只读性固定）：直接执行",
            "sandbox-only": "annotations.readOnly == contract-dependent 且 writeStage == sandbox"
                            "（只读性取决于契约；写步骤只落本次运行沙箱，永不转发 --confirm）",
            "local-output": "annotations.readOnlyHint is False 且 _meta.daniel.exposure == local-output"
                            "（**会往本机出件落点写文件、不写 Daniel 远端**：可直接执行，"
                            "调用一次真在本机产出交付物；它不是写链，因此**不用**确认单形态 —— "
                            "TICKET-202·Q14 新增档，现存 `playbook deliver` 一条）",
            "confirm-ticket": "其余全部写链命令：注册为**确认单工具** —— 调用只返回确认单，"
                              "永不执行、永不转发 --confirm、不产生任何副作用"
                              "（影响面只来自只读预查）；退出码语义 3＝需确认",
        },
        "counts": {"readOnly": len(ro), "sandboxOnly": len(sb), "localOutput": len(lo),
                   "confirmTicket": len(ct),
                   "registered": len(registry), "cliDeclared": len(mcp_tools())},
        "actionCoverage": action_coverage(registry),
        "readOnlyTools": ro,
        "sandboxOnlyTools": sb,
        "localOutputTools": lo,
        "confirmTicketTools": ct,
        "resources": {"supported": True, "scheme": RESOURCE_SCHEME,
                      "count": corpus.get("resourceCount"),
                      "corpusVersion": corpus.get("corpusVersion"),
                      "corpusRoot": corpus.get("corpusRoot"),
                      "note": "语料随本服务分发（按服务自身位置定位）；宿主不支持 resources 时"
                              "用 daniel_skills_list / daniel_skills_read 两条工具即可。"},
        "envPassthrough": list(ENV_ALLOWLIST),
        "envNeverPassed": list(SENSITIVE_ENV),
    }


# ─────────────────────────── 子进程调用 ───────────────────────────
def child_env():
    """构造子进程环境：**只**透传白名单，其余一律丢弃（凭据类变量永不进入子进程）。"""
    env = {}
    for key in ENV_ALLOWLIST:
        val = os.environ.get(key)
        if val is not None and val != "":
            env[key] = val
    env.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    env["PYTHONIOENCODING"] = "utf-8"
    # TICKET-160：告诉子进程"这一次是经 MCP 模式进来的"。intake 链路据此判「模式能力」三态：
    # MCP 模式下写动作只出确认单（措辞是「需要你确认」，不是"不支持"）；缺省（不设）即 CLI 模式。
    env["DANIEL_CLI_MODE"] = "mcp"
    for bad in SENSITIVE_ENV:                      # 防御性断言：白名单里不可能混进凭据
        env.pop(bad, None)
    return env


def redact(text):
    """把环境里出现过的凭据值（以及它们的掩码前后的形态）从任何输出里抹掉。"""
    if not text:
        return text
    out = str(text)
    for key in SENSITIVE_ENV:
        val = os.environ.get(key)
        if val and len(val) >= 4:
            out = out.replace(val, REDACTED)
    return out


def refuse_execution_flags(arguments):
    """`--confirm` / `--delete-token` 的拒绝（**本票唯一不能碰的底线**，代码与行为两侧都断言）。

    拒绝而不是"忽略"：传了 `confirm=true` 的调用者显然是想**执行**，因此回一条
    `isError=true` 的明确拒因，比静默降级成"又给一份确认单"更不容易被误读成已执行。
    拒因写死了一句可机检的话（`client_check.py` 与 `--self-test` 都断言它）。
    """
    args = arguments if isinstance(arguments, dict) else {}
    for banned, why in (("confirm", "`--confirm`"), ("delete_token", "`--delete-token`")):
        if banned in args and args[banned] not in (None, False, "", [], {}):
            return ("%s 永不转发：本模式不执行写动作（退出码语义 3＝需确认）；"
                    "请拿确认单里的命令到 CLI（完整能力集成形态）由人执行，"
                    "本工具只返回确认单、不做任何写。" % why)
    return None


def build_argv(entry, arguments):
    """`tools/call` 的 arguments → `daniel <模块> <子命令> --json …`（返回 argv 与拒绝理由）。

    **只有读链与沙箱工序引擎走这里**。确认单工具**从不**经过本函数 ——
    它走 `build_confirm_ticket()`，那条路只拼只读预查的 argv（见 `_ticket_probes()`）。
    因此 `--confirm` 在结构上就进不了任何子进程 argv：本函数显式拒收它，
    而它的调用方只有 `call_tool()` 的读链分支。
    """
    args = arguments if isinstance(arguments, dict) else {}
    refuse = refuse_execution_flags(args)
    if refuse:
        return None, refuse
    argv = [sys.executable or "python3", DANIEL_BIN, entry["module"], entry["command"]]
    unknown = []
    for key, val in args.items():
        if key in ("confirm", "dry_run", "delete_token"):
            continue                              # dry_run 是默认行为，不转发
        opt = entry["options"].get(key)
        if opt is None:
            unknown.append(key)
            continue
        if key in entry["flags"]:
            if val is True:
                argv.append(opt)
            continue
        if val is None or val == "":
            continue
        if key in entry["repeat"] or isinstance(val, list):
            for one in (val if isinstance(val, list) else [val]):
                argv += [opt, _stringify(one)]
        else:
            argv += [opt, _stringify(val)]
    if unknown:
        return None, ("参数名不认识：%s（本工具允许的参数见 tools/list 的 inputSchema：%s）"
                      % ("、".join(sorted(unknown)), "、".join(sorted(entry["options"]))))
    argv.append("--json")
    return argv, None


def _stringify(val):
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def run_daniel(argv, timeout=1800):
    """跑一次 CLI，返回 `(exit_code, envelope_or_None, stdout, stderr)`。"""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=child_env(), cwd=REPO_ROOT, timeout=timeout)
    except subprocess.TimeoutExpired:
        return EXIT_INTERNAL, None, "", "CLI 执行超时（%s 秒）" % timeout
    except OSError as e:
        return EXIT_INTERNAL, None, "", "无法启动 CLI：%s" % e
    env_doc = None
    text = (p.stdout or "").strip()
    if text:
        try:
            env_doc = json.loads(text)
        except ValueError:
            env_doc = None
    return p.returncode, env_doc, p.stdout or "", p.stderr or ""


# ═══════════════ 确认单：只读预查 ＋ 组装（TICKET-161） ═══════════════
def _read_only_keys():
    """`schema` 里声明为**只读**的命令键集合（`模块.子命令`）。

    只读预查的白名单就来自这里 —— **不手写名单**：预查命令是不是只读，由单一真源说了算。
    """
    return {"%s.%s" % (m["key"], c["name"])
            for m in SCHEMA["modules"] for c in m["commands"] if not c["write"]}


def _shellish(value):
    """给人照着复制的命令里，带空白的取值加引号（只影响显示，不影响任何 argv）。"""
    text = _stringify(value)
    return '"%s"' % text if re.search(r"\s", text) else text


def _fills(template, args, secret=()):
    """模板里的 `{参数名}` → 本次实参；缺参显示 `<未给出>`（不编造、不留空）。

    **敏感参数一律显示占位符**（`secret` 里的名字），绝不打印原值 ——
    纵深防御：即便宿主绕过 inputSchema 硬塞了一个密码，提示串里也永远是占位符。
    """
    if not isinstance(template, str):
        return template
    secret = set(secret or ())

    def sub(m):
        name = m.group(1)
        if name in secret:
            return SECRET_PLACEHOLDER
        val = (args or {}).get(name)
        return "<未给出>" if val in (None, "", [], {}) else _shellish(val)

    return re.sub(r"\{([a-z_]+)\}", sub, template)


def human_command(entry, arguments, with_confirm=True):
    """确认单里那条**给人照着跑**的命令。

    含 `--confirm`（否则到 CLI 跑只会拿到退出码 3，不执行）；删除类再补一个
    `--delete-token "<目标名>"` 占位（这个名字要人自己再写一遍，本函数不代填）。

    **敏感参数打成 `<在终端里自行输入>`**：确认单会进会话记录与日志，
    把密码原样拼进去等于把凭据写进交付物（本票红线）。

    **注意**：这条字符串只出现在**给人看的文本**里。本 server 自己**永不**把它拼进
    子进程 argv —— 见 `_ticket_probes()`（预查命令逐条断言是只读的）与 `call_tool()`
    （确认单分支根本不调 `build_argv`）。
    """
    args = arguments if isinstance(arguments, dict) else {}
    secret = set(entry.get("secret") or ())
    parts = [CLI_NAME, entry["module"], entry["command"]]
    for key, val in args.items():
        if key in ("confirm", "dry_run", "delete_token"):
            continue
        opt = entry["options"].get(key)
        if opt is None or val in (None, "", [], {}):
            continue
        if key in entry["flags"] and key not in secret:
            if val is True:
                parts.append(opt)
            continue
        if key in secret:
            parts.append("%s %s" % (opt, SECRET_PLACEHOLDER))
            continue
        if key in entry["repeat"] or isinstance(val, list):
            for one in (val if isinstance(val, list) else [val]):
                parts.append("%s %s" % (opt, _shellish(one)))
        else:
            parts.append("%s %s" % (opt, _shellish(val)))
    if with_confirm:
        parts.append("--confirm")
        if entry.get("deleteTarget"):
            parts.append('--delete-token "<%s>"' % entry["deleteTarget"])
    return " ".join(parts)


def _mask_email(value):
    """邮箱只留首字母与域名：确认单要能被人认出"是哪个账号"，但不必留完整地址。"""
    if not isinstance(value, str) or "@" not in value:
        return value
    head, _, domain = value.partition("@")
    return "%s***@%s" % (head[:1] or "", domain)


def _probe_digest(key, data):
    """把只读预查的返回**收敛成几个事实字段**（不原样透传）。

    为什么必须收敛：`lists by-brand` 的原始行里带着 `shareToken`／`shareAccessCode`
    这类**分享令牌** —— 原样贴进确认单就等于把凭据写进交付物（本票红线）。
    这里只取影响面需要的那几个数，凭据类字段一个都不进。
    """
    if not isinstance(data, dict):
        return "（载荷不是对象，已省略）"
    if key == "account.whoami":
        return {"工作区编号": data.get("activeWorkspaceId"),
                "账号": _mask_email(data.get("email")),
                "系统角色": data.get("systemRole"), "账号状态": data.get("userStatus")}
    if key == "account.capabilities":
        acct = data.get("账号") or {}
        return {"当前工作区": acct.get("当前工作区"), "工作区计划": acct.get("工作区计划"),
                "配额上限": acct.get("配额上限"), "配额用量": data.get("配额用量"),
                "能力小结": data.get("小结")}
    if key == "account.audit":
        return data.get("小结")
    if key == "account.credentials":
        # **只取"来源与可用性"这几个判定用事实**：不回显任何凭据值，也不带本机明文文件路径
        # （邮箱只留命令自己给的掩码形态）。
        return {"凭据来源": data.get("source"), "凭据是否存在": data.get("exists"),
                "掩码邮箱": data.get("email_masked"),
                "钥匙串是否可用": (data.get("keychain") or {}).get("available"),
                "钥匙串里是否已有": (data.get("keychain") or {}).get("found"),
                "明文降级是否启用": (data.get("plaintext_fallback") or {}).get("enabled")}
    if key == "brands.show":
        return {"品牌名": data.get("name"), "品牌编号": data.get("id"),
                "工作区编号": data.get("workspaceId"), "类目": data.get("category")}
    if key == "brands.list":
        return {"品牌数": data.get("count")}
    if key == "lists.by-brand":
        rows = data.get("lists") or []
        return {"品牌": data.get("brand"), "名单数": data.get("count"),
                "名单（编号／名称／条目数）": [{"编号": r.get("id"), "名称": r.get("name"),
                                              "条目数": r.get("influencerCount")}
                                             for r in rows if isinstance(r, dict)][:20]}
    if key == "search.history":
        rows = data.get("records") or data.get("history") or data.get("列表") or []
        return {"记录数": len(rows) if isinstance(rows, list) else data.get("count")}
    if key == "mentions.jobs":
        rows = data.get("jobs") or data.get("任务") or []
        return {"任务数": len(rows) if isinstance(rows, list) else data.get("count")}
    if key == "sov.overview":
        return {"品牌数": len(data.get("brands") or data.get("竞品") or []) or data.get("count"),
                "窗口天数": data.get("days")}
    if key == "ct.campaigns":
        rows = data.get("campaigns") or data.get("活动") or []
        return {"活动数": len(rows) if isinstance(rows, list) else data.get("count")}
    if key == "route.catalog":
        rows = data.get("routes") or data.get("通路") or []
        return {"通路数": len(rows) if isinstance(rows, list) else data.get("count")}
    if key == "takeover.check":
        return {"区块数": len(data.get("blocks") or data.get("区块") or []),
                "结论": (data.get("结论") or data.get("summary"))}
    # 兜底：只回字段名，不回取值（宁可少给事实，也不把未知形状里的凭据漏出去）
    return {"字段": sorted(data.keys())}


def _write_permission(caps_digest, module):
    """从写权限小结里取这个模块的写结论（与写命令实际执行时的判据同源）。

    `caps_digest` 是 `account capabilities` 只读预查的**收敛结果**（见 `_probe_digest`）。
    拿不到就返回 None —— 不猜"应该能写"。
    """
    if not isinstance(caps_digest, dict):
        return None
    summary = caps_digest.get("能力小结") or {}
    writable = summary.get("可写模块")
    if not isinstance(writable, list):
        return None
    return {"模块": module, "可写": module in writable,
            "可写模块": writable, "不可写模块": summary.get("不可写模块")}


def _ticket_probes(entry, arguments, timeout=300):
    """只读预查：**只跑只读命令**，拿影响面要用的真实事实。

    这是「不产生副作用」的**实现级保证**：每条预查在拼 argv 之前都对着
    `_read_only_keys()`（来自 `schema.py` 单一真源）**断言它是只读命令**；
    拼出来的 argv 里既没有 `--confirm` 也没有 `--delete-token`，
    且**从不包含本次那条写命令**（写命令的模块/子命令只出现在给人看的字符串里）。
    """
    key = "%s.%s" % (entry["module"], entry["command"])
    plan = CONFIRM_TICKET.get(key) or {}
    allowed = _read_only_keys()
    args = arguments if isinstance(arguments, dict) else {}
    out = []
    seen = set()
    for spec in list(COMMON_PROBES) + list(plan.get("预查") or []):
        probe_key = "%s.%s" % (spec["模块"], spec["子命令"])
        if probe_key in seen:
            continue          # 公共预查与命令自己的预查可能撞车（如 account.login）：只跑一次
        seen.add(probe_key)
        if probe_key not in allowed:
            out.append({"能力键": probe_key,
                        "命令": "%s %s %s" % (CLI_NAME, spec["模块"], spec["子命令"]),
                        "用途": spec.get("用途"),
                        "结果": "已跳过：该命令不在只读白名单里（拒绝为了拿影响面去跑非只读命令）"})
            continue
        argv = [sys.executable or "python3", DANIEL_BIN, spec["模块"], spec["子命令"]]
        for opt, tmpl in spec.get("参数") or []:
            if isinstance(tmpl, str) and tmpl.startswith("{"):
                val = args.get(tmpl[1:-1])
                if val in (None, "", [], {}):
                    continue                       # 实参没给就不查，不猜
            else:
                val = tmpl
            argv += [opt, _stringify(val)]
        argv.append("--json")
        code, envelope, _out, err = run_daniel(argv, timeout=timeout)
        shown = " ".join(argv[2:])
        # `命令` 是给人看的展示串（补上 `daniel ` 前缀，否则读起来像半句）；
        # 结构化的匹配一律走 `能力键`，**不许拿这个展示串做判断**。
        row = {"能力键": probe_key, "命令": "%s %s" % (CLI_NAME, shown),
               "用途": spec.get("用途")}
        if code == EXIT_OK and envelope and envelope.get("ok") is True:
            row["退出码"] = code
            row["结果"] = _probe_digest(probe_key, envelope.get("data"))
        else:
            row["退出码"] = code
            row["结果"] = "（只读预查没成功，影响面这一项如实留空）%s" % _reason(code, envelope, err)
        out.append(row)
    return out


def build_confirm_ticket(entry, arguments):
    """组装一份**结构化确认单**。本函数**不执行任何写命令**（只跑只读预查）。"""
    key = "%s.%s" % (entry["module"], entry["command"])
    plan = CONFIRM_TICKET.get(key) or {}
    args = arguments if isinstance(arguments, dict) else {}
    probes = _ticket_probes(entry, args)
    # 按**显式能力键**取预查结果，不按命令字符串前缀猜 —— 前缀猜法错过一次：
    # 预查行的 `命令` 少了 `daniel ` 前缀（那是给人看的展示串），于是 startswith 恒假，
    # 「目标工作区」与写权限判据双双静默为空。取值必须靠结构化字段，不靠人看的字符串。
    by_key = {row.get("能力键"): row.get("结果") for row in probes
              if isinstance(row.get("结果"), dict)}
    caps = by_key.get("account.capabilities")
    acct_ws = (by_key.get("account.whoami") or {}).get("工作区编号")
    obj_ws = (by_key.get("brands.show") or {}).get("工作区编号")

    # 目标工作区：优先"对象所属工作区"（品牌档案里的 workspaceId，那才是这次写真正落的地方），
    # 没有对象工作区时退回"账号当前工作区"；本机副作用类的命令**不落任何工作区**，如实写"不适用"。
    if plan.get("动作类型") == ACTION_LOCAL_SIDE_EFFECT:
        target_ws, ws_src = "不适用（本机副作用：不落任何 Daniel 工作区）", "—"
    elif obj_ws is not None:
        target_ws, ws_src = obj_ws, "对象所属工作区（只读预查 brands show）"
    elif acct_ws is not None:
        target_ws, ws_src = acct_ws, "账号当前工作区（只读预查 account whoami）"
    else:
        target_ws, ws_src = None, "只读预查没给出来源"

    # 所需前置：能查的都真查了；查不到的如实说"查不到"，不写"应该没问题"
    prereq = []
    perm = _write_permission(caps, entry["module"])
    if perm is None:
        prereq.append("写权限：只读预查没拿到结论 —— 请在 CLI 用 `daniel account capabilities` 自查，"
                      "不要按「应该能写」开工")
    elif perm["可写"]:
        prereq.append("写权限：允许（该账号对 `%s` 模块可写；判据见「影响面.只读预查」的 "
                      "account capabilities）" % entry["module"])
    else:
        prereq.append("写权限：**不允许** —— `%s` 不在可写模块里（%s）；"
                      "即便加上 --confirm 也会以退出码 2 被拒，不会执行"
                      % (entry["module"], "、".join(perm["可写模块"]) or "（空）"))
    missing = [k for k in entry["required"] if args.get(k) in (None, "", [], {})]
    if missing:
        prereq.append("必填参数：缺 %s（缺了 CLI 会以退出码 2 拒绝，不会执行）"
                      % "、".join(missing))
    elif entry["required"]:
        prereq.append("必填参数：已给齐（%s）" % "、".join(entry["required"]))
    else:
        prereq.append("必填参数：本命令没有必填参数")
    if entry.get("deleteTarget"):
        prereq.append("删除类的二次确认：`--delete-token` 要把「%s」**原样再写一遍**"
                      "（写错即拒绝、退出码 2，且不做任何删除）" % entry["deleteTarget"])
    if key == "account.credentials-set":
        # 该命令自己的 writeNote 里写着"凭据来源二选一，两者同时给会被拒绝" —— 照抄它的口径，
        # 不替它推断别的。
        prereq.append("凭据来源二选一：`--from-env`（只读环境变量）或 `--email`／`--password`；"
                      "**两者同时给会被拒绝**（退出码 2）")
        prereq.append("钥匙串写失败**不会静默降级为明文**：会非零退出并给指引；"
                      "确实要明文降级须显式设 `DANIEL_ALLOW_PLAINTEXT=1` 并自行用凭据工具写入")
    prereq.append("Daniel 会话有效（本次只读预查的退出码见「影响面.只读预查」，全 0 即有效）")

    ticket = {
        "工具": entry["tool"]["name"],
        "能力键": key,
        "动作类型": plan.get("动作类型"),
        "是否属于需求稿五类": plan.get("属于五类"),
        "是否执行": False,
        "退出码语义": {"退出码": EXIT_NEEDS_CONFIRM, "含义": name_of(EXIT_NEEDS_CONFIRM),
                       "说明": "与 CLI 对齐：CLI 侧不带 --confirm 也是这个退出码，"
                               "且同样不执行。**这不是成功**。"},
        "将执行的确切命令": human_command(entry, args, with_confirm=True),
        "影响面": {
            "目标工作区": target_ws,
            "目标工作区来源": ws_src,
            "目标对象": _fills(plan.get("影响面对象"), args, entry.get("secret")),
            "条数": _fills(plan.get("影响面条数"), args, entry.get("secret")),
            "是否消耗配额": plan.get("消耗配额"),
            "只读预查": probes,
            "影响面来源": "**只来自只读预查**：本 server 为了拿影响面也不会去跑那条写命令。",
        },
        "不可逆性": plan.get("不可逆性"),
        "所需前置": prereq,
        "替代路径": [
            "只读替代：%s" % _fills(plan.get("只读替代"), args, entry.get("secret")),
            "先干跑（不写任何东西）：%s" % human_command(entry, args, with_confirm=False),
            "真执行（CLI 形态，人工确认）：把「将执行的确切命令」原样复制到终端跑",
        ],
        "为什么不在这里执行": "MCP 是 Daniel 数据层接入面（用户 2026-10-15 裁决）："
                              "能力面全量可见，但写动作一律不由 AI 执行。"
                              "本 server 永不转发 `--confirm`，调用此工具**不产生任何副作用**。",
    }
    return ticket


def _ticket_text(ticket):
    """确认单的**人话文本**（宿主把它当普通工具结果展示）。"""
    lines = ["Daniel 确认单工具：%s" % ticket["工具"],
             "结果：**未执行** —— 退出码语义 %d＝%s；本工具只出确认单，"
             "永不执行写动作、永不转发 --confirm、不产生任何副作用。"
             % (ticket["退出码语义"]["退出码"], ticket["退出码语义"]["含义"]),
             "动作类型：%s（属于需求稿五类：%s）"
             % (ticket["动作类型"], "是" if ticket["是否属于需求稿五类"] else "否 —— 见下方说明"),
             "",
             "将执行的确切命令（复制到终端跑，由人确认）：",
             "  %s" % ticket["将执行的确切命令"],
             "",
             "影响面：",
             "  目标工作区：%s" % ticket["影响面"]["目标工作区"],
             "  目标对象：%s" % ticket["影响面"]["目标对象"],
             "  条数：%s" % ticket["影响面"]["条数"],
             "  是否消耗配额：%s" % ticket["影响面"]["是否消耗配额"],
             "  只读预查（影响面只来自这里）："]
    for row in ticket["影响面"]["只读预查"]:
        lines.append("    · %s ｜ %s ｜ 退出码 %s" % (row["命令"], row["用途"], row.get("退出码")))
        lines.append("      → %s" % json.dumps(row["结果"], ensure_ascii=False)[:600])
    lines += ["", "不可逆性：%s" % ticket["不可逆性"], "", "所需前置："]
    lines += ["  · %s" % one for one in ticket["所需前置"]]
    lines += ["", "替代路径："]
    lines += ["  · %s" % one for one in ticket["替代路径"]]
    lines += ["", ticket["为什么不在这里执行"]]
    return "\n".join(lines)


# ─────────────────────────── 语料（随服务分发） ───────────────────────────
def cli_json(module, command, extra=(), timeout=120):
    """跑一次 CLI 并取 `data`（拿不到就返回 `(None, 人话理由)`）。

    语料的工具路径与 resource 路径**都走这一个口**：不在这里重读语料文件，
    因此"宿主从 MCP 看到的"与"人在终端里 `daniel skills …` 看到的"不可能是两份东西。
    """
    argv = [sys.executable or "python3", DANIEL_BIN, module, command] + list(extra) + ["--json"]
    code, envelope, _out, err = run_daniel(argv, timeout=timeout)
    if code != EXIT_OK or not envelope or envelope.get("ok") is not True:
        return None, _reason(code, envelope, err)
    return envelope.get("data"), None


class ResourceError(Exception):
    """resource 读不到（上层转成 JSON-RPC 错误，不假装成功）。"""


class CorpusResources:
    """把随包语料暴露成 MCP resources（`resources/list` ＋ `resources/read`）。

    一次 `daniel skills list --json` 拿到全部元信息后缓存；`resources/read` 才真读正文。
    URI 三型（都指向**真实存在**的内容，不做"读了 URI 却返回索引"这种事）：
      `daniel-copilot://skills`                → 语料索引（JSON）
      `daniel-copilot://skills/<域>`           → 该束导航件 SKILL.md 逐字正文（markdown）
      `daniel-copilot://skills/<域>/<切片号>`  → 该切片的逐字正文（markdown）
    """

    def __init__(self):
        self._index = None

    def index(self, refresh=False):
        if self._index is None or refresh:
            data, why = cli_json("skills", "list")
            if data is None:
                raise ResourceError("读不到随包语料：%s" % why)
            self._index = data
        return self._index

    def domains(self):
        return self.index().get("能力域") or []

    def _domain(self, name):
        for s in self.domains():
            if s.get("域") == name:
                return s
        raise ResourceError("不认识的能力域：%s（可选：%s）"
                            % (name, "、".join(s.get("域", "") for s in self.domains())))

    def list_resources(self):
        idx = self.index()
        out = [{
            "uri": "%s://skills" % RESOURCE_SCHEME,
            "name": "skills-index",
            "title": "业务语料索引（%s）" % idx.get("语料版本"),
            "description": "随服务分发的全部能力域：域键、中文标签、语料版本、前置条件、切片清单。"
                           "共 %s 个能力域。" % idx.get("能力域数"),
            "mimeType": "application/json",
        }]
        for s in self.domains():
            out.append({
                "uri": "%s://skills/%s" % (RESOURCE_SCHEME, s["域"]),
                "name": s["域"],
                "title": "%s（%s）" % (s["域"], s.get("能力域") or ""),
                "description": "导航件 SKILL.md：本束覆盖的源节表 ＋ 核心判据速查。"
                               "语料版本 %s ｜ 整束 %s 字节。" % (s.get("版本"), s.get("字节数")),
                "mimeType": "text/markdown",
            })
            for sec in s.get("切片") or []:
                out.append({
                    "uri": "%s://skills/%s/%s" % (RESOURCE_SCHEME, s["域"], sec["切片号"]),
                    "name": "%s-%s" % (s["域"], sec["切片号"]),
                    "title": "%s ｜ %s" % (s["域"], sec.get("源节标题") or sec.get("文件")),
                    "description": "逐字切片 %s（源行区间 %s，%s 字节）。"
                                   % (sec.get("文件"), sec.get("源行区间"), sec.get("字节数")),
                    "mimeType": "text/markdown",
                })
        return out

    def read(self, uri):
        """URI → `resources/read` 的 contents 条目。"""
        if not isinstance(uri, str) or not uri.startswith(RESOURCE_SCHEME + "://"):
            raise ResourceError("不认得的 resource URI：%s（本 server 只提供 %s://skills…）"
                                % (uri, RESOURCE_SCHEME))
        rest = uri[len(RESOURCE_SCHEME) + 3:]
        if rest in ("skills", "skills/"):
            idx = self.index()
            return {"uri": uri, "mimeType": "application/json",
                    "text": json.dumps(idx, ensure_ascii=False, indent=1)}
        parts = [p for p in rest.split("/") if p != ""]
        if not parts or parts[0] != "skills":
            raise ResourceError("不认得的 resource URI：%s" % uri)
        if len(parts) == 2:
            name, section = parts[1], 0
        elif len(parts) == 3:
            name = parts[1]
            if not parts[2].isdigit():
                raise ResourceError("切片号必须是整数：%s" % parts[2])
            section = int(parts[2])
        else:
            raise ResourceError("不认得的 resource URI：%s" % uri)
        self._domain(name)
        extra = ["--name", name, "--section", str(section), "--max-bytes", "0"]
        data, why = cli_json("skills", "read", extra)
        if data is None:
            raise ResourceError("读语料失败：%s" % why)
        if data.get("模式") != "正文":
            raise ResourceError("读到的是「%s」模式，不是正文（%s）" % (data.get("模式"), uri))
        return {"uri": uri, "mimeType": "text/markdown", "text": data.get("正文") or ""}


def _corpus_summary():
    """`--describe` 用的一句话语料概览（拿不到就如实说拿不到，不编数字）。"""
    try:
        idx = CorpusResources().index()
    except ResourceError as e:
        return {"corpusVersion": None, "corpusRoot": None, "resourceCount": None,
                "error": str(e)}
    n = 1 + len(idx.get("能力域") or []) + sum(len(s.get("切片") or [])
                                              for s in (idx.get("能力域") or []))
    return {"corpusVersion": idx.get("语料版本"), "corpusRoot": idx.get("语料根"),
            "resourceCount": n}


# ─────────────────────────── 结果装配 ───────────────────────────
def summarize(data, limit=1600):
    """给人看的摘要（复用 CLI 自己的中文渲染口径，截断时说明）。"""
    if data is None:
        return "（无结构化结果）"
    if isinstance(data, dict):
        head = "共 %d 个字段：%s" % (len(data), "、".join(list(data.keys())[:12]))
    elif isinstance(data, list):
        head = "共 %d 条记录" % len(data)
    else:
        return str(data)
    try:
        from daniel_cli.runtime import render_human
        body = render_human(data, max_items=5)
    except Exception:                                               # noqa: BLE001
        body = json.dumps(data, ensure_ascii=False, indent=1)
    if len(body) > limit:
        body = body[:limit] + "\n…（摘要截断，完整内容见下方结构化 JSON）"
    return head + "\n" + body


def _reason(exit_code, envelope, stderr):
    """退出码 → 人话理由。"""
    known = name_of(exit_code)
    if envelope and isinstance(envelope.get("error"), dict):
        err = envelope["error"]
        msg = err.get("message") or ""
        hint = err.get("hint") or ""
        return redact("%s（退出码 %d＝%s）%s" % (msg, exit_code, known,
                                              ("；建议：" + hint) if hint else ""))
    tail = [l for l in (stderr or "").strip().splitlines() if l.strip()]
    if tail:
        return redact("%s（退出码 %d＝%s）" % (tail[-1], exit_code, known))
    return "退出码 %d＝%s" % (exit_code, known)


def _unauthenticated_result(name, entry, verdict):
    """MCP 侧的**结构化「未登录」**结果（TICKET-194 · A 的 MCP 面）。

    为什么要有这一条（而不是让 CLI 子进程去报）：票面要求"未登录时工具调用必须返回
    **结构化「未登录」错误 ＋ 修法**（**不许静默返回空数据**）"。最稳的做法是在**本进程**
    先过同一道门禁（判据真源同样是 `daniel_cli.authgate`），于是：
      · 业务模块工具**根本不会起子进程**（零真实数据、零副作用）；
      · 返回体里 `isError=true` ＋ `structuredContent.未登录=true` ＋ `authenticated=false`
        ＋ `fix`（一行修法）＋ `reason`，机器与人都能判；
      · 🔴 **模式对等不变量不变**：这条路上没有 `--confirm`、没有 `--delete-token`，
        `executed=false`／`confirmForwarded=false` 明确写进 `_meta`。
    """
    text = "\n".join([
        "Daniel 工具未执行：**未登录**",
        "工具：%s（等价命令：%s）" % (name, entry["cli"]),
        "理由：%s" % verdict["reason"],
        "修法（一行）：%s" % verdict["fix"],
        "说明：未登录时业务模块一律不放行 —— 这里返回的是**结构化的未登录错误**，"
        "**不是空数据**；没有任何 Daniel 取数发生。",
        "登录走浏览器：`daniel account login --browser`（账号密码**只在 Daniel 页面上**输入）。",
        "看登录状态：`daniel auth status`（0＝通过／1＝去登录／2＝服务端不可达）。",
    ])
    return {
        "content": [{"type": "text", "text": redact(text)}],
        "isError": True,
        "structuredContent": {
            "未登录": True,
            "authenticated": False,
            "reason": verdict["reason"],
            "module": entry["module"],
            "command": entry["command"],
            "fix": verdict["fix"],
            "next": "在同一条 Daniel 安装上完成浏览器登录后重试本工具。",
        },
        "_meta": {"daniel": {
            "tool": name, "module": entry["module"], "command": entry["command"],
            "unauthenticated": True, "authenticated": False,
            "exitCode": EXIT_USAGE, "executed": False, "confirmForwarded": False,
            "gate": "daniel_cli/authgate.py（与 CLI 同一份判据）",
        }},
    }


def call_tool(registry, name, arguments, timeout=1800):
    """执行一次 `tools/call`，返回 MCP 的 `ToolResult`（或 `(None, 错误说明)`）。

    三条路**在结构上分开**：
      · **未登录**（TICKET-194 门禁）→ `_unauthenticated_result()`：**不起子进程**、
        不含任何数据，只给结构化「未登录」＋ 修法。判据与 CLI 同源（`authgate`）；
      · `exposure == "confirm-ticket"` → `_confirm_ticket_result()`：**只跑只读预查**，
        绝不调 `build_argv()`，因此那条写命令在结构上就没有任何执行路径；
      · 其余（读链／沙箱工序引擎） → 老路：拼 argv 起子进程。
    """
    entry = registry.get(name)
    if entry is None:
        return None, "未知工具：%s" % name
    # ① **结构性不变量先行**：`--confirm`／`--delete-token` 的拒绝**与登录态无关** ——
    #    本模式永不转发这两个开关这件事，不该因为"没登录"就换一套说辞（模式对等不变量）。
    refused = refuse_execution_flags(arguments if isinstance(arguments, dict) else {})
    if refused:
        return {"content": [{"type": "text", "text": redact(refused)}],
                "isError": True,
                "structuredContent": {"refused": True, "confirmForwarded": False,
                                      "executed": False, "reason": redact(refused)},
                "_meta": {"daniel": {"tool": name, "cli": entry["cli"], "refused": True,
                                     # 拒绝路径同样要留证据：没执行、没转发 --confirm
                                     "executed": False, "confirmForwarded": False}}}, None
    # ② **授权门禁**（TICKET-194）：判据与 CLI 同源（`daniel_cli.authgate`）—— 未登录时
    #    业务模块工具一律返回结构化「未登录」，**不起子进程、不含任何数据**。
    gate_verdict = authgate.gate(entry["module"], entry["command"])
    if gate_verdict is not None:
        return _unauthenticated_result(name, entry, gate_verdict), None
    if entry["exposure"] == "confirm-ticket":
        return _confirm_ticket_result(entry, arguments), None
    argv, refuse = build_argv(entry, arguments)
    if refuse:
        return {"content": [{"type": "text", "text": redact(refuse)}],
                "isError": True,
                "_meta": {"daniel": {"tool": name, "cli": entry["cli"], "refused": True,
                                     # 拒绝路径同样要留证据：没执行、没转发 --confirm
                                     "executed": False, "confirmForwarded": False}}}, None
    code, envelope, out, err = run_daniel(argv, timeout=timeout)
    ok = (code == EXIT_OK) and bool(envelope) and envelope.get("ok") is True
    data = (envelope or {}).get("data")
    shown = " ".join(argv[2:])
    lines = ["Daniel 只读工具：%s" % name,
             "等价命令：%s" % shown,
             "退出码：%d（%s）" % (code, name_of(code)),
             "是否成功：%s" % ("是" if ok else "否")]
    if ok:
        lines.append("结果摘要：%s" % summarize(data))
    else:
        lines.append("失败理由：%s" % _reason(code, envelope, err))
        if code == EXIT_NEEDS_CONFIRM:
            lines.append("说明：本 server 永不转发 --confirm —— 写动作请由人拿确认单里的命令到 "
                         "CLI（完整能力集成形态）执行。")
    if data is not None:
        lines.append("--- 结构化结果（JSON）---")
        lines.append(json.dumps(data, ensure_ascii=False, indent=1))
    elif envelope is not None:
        lines.append("--- 结构化结果（JSON）---")
        lines.append(json.dumps({k: v for k, v in envelope.items() if k != "data"},
                                ensure_ascii=False, indent=1))
    result = {"content": [{"type": "text", "text": redact("\n".join(lines))}],
              "isError": not ok}
    structured = {"data": data} if data is not None else {}
    structured["envelope"] = {k: v for k, v in (envelope or {}).items() if k != "data"}
    structured["cli"] = shown
    result["structuredContent"] = structured
    result["_meta"] = {"daniel": {
        "tool": name, "module": entry["module"], "command": entry["command"],
        "exitCode": code, "readOnly": bool((envelope or {}).get("readOnly")),
        "exposure": entry["exposure"],
    }}
    return result, None


def _confirm_ticket_result(entry, arguments):
    """确认单工具的结果：**只出确认单，永不执行**。

    退出码语义与 CLI 对齐：`3`＝需确认。MCP 没有退出码这个字段，所以它同时出现在
    三处（正文第一句／`structuredContent.确认单.退出码语义`／`_meta.daniel.exitCode`），
    并且**没有任何"成功"的味道**：`是否执行=false`、`executed=false`、
    `requiresConfirmation=true`、正文第一句就是"未执行"。

    `isError` 为什么是 false：这一票的**预期产出**就是一份确认单 —— 它是工具干对了活，
    不是工具失败（CLI 侧退出码 3 也不是"错误"，它是"等你点头"）。把它标成 isError
    反而会让宿主把它当异常吞掉，确认单就到不了用户眼前。**但它绝不被包装成成功**：
    上面那四个字段 + 退出码 3 是机器可读的反证。
    """
    refuse = refuse_execution_flags(arguments)
    if refuse:
        return {"content": [{"type": "text", "text": redact(refuse)}],
                "isError": True,
                "_meta": {"daniel": {"tool": entry["tool"]["name"], "exposure": "confirm-ticket",
                                     "refused": True, "executed": False,
                                     "exitCode": EXIT_NEEDS_CONFIRM,
                                     "confirmForwarded": False}}}
    ticket = build_confirm_ticket(entry, arguments)
    text = _ticket_text(ticket)
    return {
        "content": [{"type": "text", "text": redact(text)}],
        "isError": False,
        "structuredContent": {"确认单": ticket, "cli": entry["cli"]},
        "_meta": {"daniel": {
            "tool": entry["tool"]["name"],
            "module": entry["module"], "command": entry["command"],
            "exposure": "confirm-ticket",
            "exitCode": EXIT_NEEDS_CONFIRM, "exitCodeName": name_of(EXIT_NEEDS_CONFIRM),
            "executed": False, "requiresConfirmation": True,
            "confirmForwarded": False,
            "actionType": ticket["动作类型"],
            "属于需求稿五类": ticket["是否属于需求稿五类"],
        }},
    }


# ─────────────────────────── JSON-RPC / MCP 协议 ───────────────────────────
ERR_PARSE, ERR_REQUEST, ERR_METHOD, ERR_PARAMS, ERR_INTERNAL = -32700, -32600, -32601, -32602, -32603


class Server:
    def __init__(self, registry, out=None, err=None, resources=None):
        self.registry = registry
        self.out = out or sys.stdout
        self.err = err or sys.stderr
        self.initialized = False
        self.protocol = LATEST_PROTOCOL
        self.client_info = None
        self.resources = resources if resources is not None else CorpusResources()

    # ── 输出 ──
    def send(self, obj):
        self.out.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.out.flush()

    def reply(self, rid, result):
        self.send({"jsonrpc": "2.0", "id": rid, "result": result})

    def fail(self, rid, code, message, data=None):
        err = {"code": code, "message": message}
        if data is not None:
            err["data"] = redact(data)
        self.send({"jsonrpc": "2.0", "id": rid, "error": err})

    def log(self, msg):
        print(redact(msg), file=self.err, flush=True)

    # ── 方法 ──
    def on_initialize(self, params):
        params = params if isinstance(params, dict) else {}
        want = params.get("protocolVersion")
        self.protocol = want if want in SUPPORTED_PROTOCOLS else LATEST_PROTOCOL
        self.client_info = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else None
        return {
            "protocolVersion": self.protocol,
            "capabilities": {"tools": {"listChanged": False},
                             "resources": {"listChanged": False, "subscribe": False}},
            "serverInfo": {"name": SERVER_NAME, "title": SERVER_TITLE,
                           "version": SERVER_VERSION, "websiteUrl": SERVER_WEBSITE},
            "instructions": INSTRUCTIONS,
        }

    def on_tools_list(self, params):
        return {"tools": [self.registry[k]["tool"] for k in sorted(self.registry)]}

    def on_resources_list(self, params):
        """`resources/list`：随包语料的索引 ＋ 每束导航件 ＋ 每个切片（都指向真实内容）。"""
        try:
            return {"resources": self.resources.list_resources()}, None
        except ResourceError as e:
            return None, (ERR_INTERNAL, str(e))

    def on_resources_read(self, params):
        params = params if isinstance(params, dict) else {}
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            return None, (ERR_PARAMS, "resources/read 缺少 uri（字符串）")
        try:
            return {"contents": [self.resources.read(uri)]}, None
        except ResourceError as e:
            return None, (ERR_PARAMS, str(e))

    def on_tools_call(self, params):
        params = params if isinstance(params, dict) else {}
        name = params.get("name")
        if not isinstance(name, str) or not name:
            return None, (ERR_PARAMS, "tools/call 缺少 name（字符串）")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return None, (ERR_PARAMS, "tools/call 的 arguments 必须是对象，收到 %s"
                          % type(arguments).__name__)
        if name not in self.registry:
            return None, (ERR_PARAMS, "未知工具：%s（可用工具见 tools/list，共 %d 条）"
                          % (name, len(self.registry)))
        result, refuse = call_tool(self.registry, name, arguments)
        if refuse:
            return None, (ERR_PARAMS, refuse)
        return result, None

    def dispatch(self, msg):
        """处理一条消息。返回 True 表示继续，False 表示退出。"""
        if not isinstance(msg, dict):
            self.fail(None, ERR_REQUEST, "JSON-RPC 消息必须是对象，收到 %s" % type(msg).__name__)
            return True
        rid = msg.get("id")
        has_id = "id" in msg
        method = msg.get("method")
        params = msg.get("params")
        if msg.get("jsonrpc") != "2.0":
            if has_id:
                self.fail(rid, ERR_REQUEST, "jsonrpc 字段必须是 \"2.0\"")
            return True
        if not isinstance(method, str) or not method:
            if has_id:
                self.fail(rid, ERR_REQUEST, "缺少 method（字符串）")
            return True

        if method.startswith("notifications/"):
            if method == "notifications/initialized":
                self.initialized = True
            return True                                    # 通知不回包
        try:
            return self._dispatch_call(rid, has_id, method, params)
        except Exception as e:                             # noqa: BLE001
            # 兜底：任何未预期的内部异常都变成 -32603，**不让进程死** ——
            # 宿主那边看到的是一条错误响应，而不是"连接断了、不知道为什么"。
            if has_id:
                self.fail(rid, ERR_INTERNAL, "服务端内部错误：%s: %s"
                          % (type(e).__name__, e))
            else:
                self.log("内部错误（无 id 的消息）：%s: %s" % (type(e).__name__, e))
            return True

    def _dispatch_call(self, rid, has_id, method, params):
        if method == "ping":
            if has_id:
                self.reply(rid, {})
            return True
        if method == "initialize":
            if has_id:
                self.reply(rid, self.on_initialize(params))
            return True
        if method == "tools/list":
            if has_id:
                self.reply(rid, self.on_tools_list(params))
            return True
        if method == "tools/call":
            result, err = self.on_tools_call(params)
            if err:
                if has_id:
                    self.fail(rid, err[0], err[1])
            elif has_id:
                self.reply(rid, result)
            return True
        if method == "resources/list":
            result, err = self.on_resources_list(params)
            if err:
                if has_id:
                    self.fail(rid, err[0], err[1])
            elif has_id:
                self.reply(rid, result)
            return True
        if method == "resources/read":
            result, err = self.on_resources_read(params)
            if err:
                if has_id:
                    self.fail(rid, err[0], err[1])
            elif has_id:
                self.reply(rid, result)
            return True
        if method == "shutdown":
            if has_id:
                self.reply(rid, {})
            return False
        if has_id:
            self.fail(rid, ERR_METHOD, "方法未实现：%s" % method,
                      {"supported": ["initialize", "notifications/initialized", "ping",
                                     "tools/list", "tools/call", "resources/list",
                                     "resources/read", "shutdown"]})
        return True

    def handle_line(self, line):
        text = line.strip()
        if not text:
            return True
        try:
            msg = json.loads(text)
        except ValueError as e:
            self.fail(None, ERR_PARSE, "JSON 解析失败：%s" % e)
            return True
        if isinstance(msg, list):                          # 批量请求：MCP 的 stdio 不用，仍按 JSON-RPC 兜住
            if not msg or not all(isinstance(one, dict) for one in msg):
                self.fail(None, ERR_REQUEST,
                          "批量消息非法（空数组或含非对象元素）；"
                          "MCP 的 stdio 传输不使用批量请求")
                return True
            for one in msg:
                if not self.dispatch(one):
                    return False
            return True
        return self.dispatch(msg)

    def serve(self, stream=None):
        stream = stream or sys.stdin
        for line in stream:
            if not self.handle_line(line):
                break
        return 0


# ─────────────────────────── 自检 ───────────────────────────
def self_test():
    checks = []

    def ok(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    registry = build_registry()
    info = describe(registry)
    declared = mcp_tools()
    index = _command_index()

    # 正控：清单来自真源、数量自洽
    ok("正控：工具清单来自单一真源（每条都能在 schema 里找到对应命令）",
       all(name in index for name in registry) and len(registry) > 0,
       "注册 %d 条 / 声明 %d 条" % (len(registry), len(declared)))
    ok("正控：只读性固定的读链命令全部在内（readOnlyHint is True）",
       all(t["name"] in registry for t in declared
           if (t.get("annotations") or {}).get("readOnlyHint") is True))
    # inputSchema 与真源的关系：**逐字一致**，唯一例外是确认单工具按 `secret`／`writeOnly`
    # **投影掉敏感参数**（投影规则只有一条、由真源标记驱动，且剔除项登记在 _meta 里，
    # 不是"第二份参数定义"）。这条断言把两者都管住。
    drift, bad_drop = [], []
    for t in declared:
        if t["name"] not in registry:
            continue
        got = registry[t["name"]]["tool"]["inputSchema"]
        dropped = set(registry[t["name"]]["tool"]["_meta"]["daniel"].get("droppedSecretParams") or [])
        src_props = dict((t["inputSchema"].get("properties") or {}))
        expect_secret = {k for k, v in src_props.items()
                         if isinstance(v, dict) and v.get("writeOnly")}
        if registry[t["name"]]["exposure"] == "confirm-ticket":
            stripped = {k: v for k, v in src_props.items() if k not in expect_secret}
            want = dict(t["inputSchema"])
            want["properties"] = stripped
            want["required"] = [k for k in (t["inputSchema"].get("required") or [])
                                if k not in expect_secret]
            if got != want:
                drift.append(t["name"])
            if dropped != expect_secret:
                bad_drop.append("%s：剔除 %s ≠ 真源敏感标记 %s"
                                % (t["name"], sorted(dropped), sorted(expect_secret)))
        elif got != t["inputSchema"]:
            drift.append(t["name"])
    ok("正控：inputSchema ≡ 真源（确认单工具只按真源的 secret 标记投影掉敏感参数，剔除项已登记）",
       not drift and not bad_drop,
       "漂移：%s%s" % ("、".join(drift) if drift else "无",
                     ("；剔除不符：" + "；".join(bad_drop)) if bad_drop else
                     "（确认单侧剔除 = 真源 writeOnly 标记，逐条对上）"))
    # ── 能力面全量可见（TICKET-161）：CLI 声明的每条命令都必须注册 ──
    missing = sorted(set(index) - set(registry))
    ok("正控（161）：CLI 声明的每一条命令都注册了（能力面全量可见，差集为 0）",
       not missing, "注册 %d / 声明 %d%s" % (len(registry), len(declared),
                                          ("；缺失：" + "、".join(missing)) if missing else ""))
    ct_names = sorted(k for k, v in registry.items() if v["exposure"] == "confirm-ticket")
    local_names = sorted(k for k, v in registry.items() if v["exposure"] == "local-output")
    declared_writes = sorted(t["name"] for t in declared
                             if (t.get("annotations") or {}).get("readOnlyHint") is False)
    all_write_tools = sorted(tool_name(m["key"], c["name"])
                             for m in SCHEMA["modules"] for c in m["commands"] if c["write"])
    # TICKET-202·Q14：`readOnlyHint=False` 现在**不等于**写链 —— `playbook deliver`（本机出件）
    # 也是 False（它会真写本机文件），但它**不是写链、不用确认单形态**。故断言拆成两半：
    #   ① 写链全部以宿主内可见形态注册（确认单 ∪ 沙箱执行 ≡ 声明的写命令）；
    #   ② 「非纯只读」清单 ≡ 写链 ∪ 本机出件（**不多不少** —— 少一条＝有人偷偷把能力标成只读，
    #      多一条＝有人把新档位漏登记）。
    ok("正控（161＋202）：写链全部以「宿主内可见」的形态注册（确认单 ＋ 沙箱执行），一条不漏；"
       "且「非纯只读」清单 ≡ 写链 ∪ 本机出件（不多不少）",
       set(ct_names) | set(info["sandboxOnlyTools"]) == set(all_write_tools)
       and set(declared_writes) == set(all_write_tools) | set(local_names),
       "确认单 %d ＋ 沙箱执行 %d ＝ 写链 %d 条（CLI 声明的写命令 %d 条）｜ 本机出件 %d 条 ｜ "
       "非纯只读 %d 条"
       % (len(ct_names), len(info["sandboxOnlyTools"]),
          len(set(ct_names) | set(info["sandboxOnlyTools"])), len(all_write_tools),
          len(local_names), len(declared_writes)))
    bad_desc = [n for n in ct_names if "不会执行" not in registry[n]["tool"]["description"]]
    ok("正控（161）：每条确认单工具的 description 都写明「不会执行」", not bad_desc,
       "未写明：%s" % ("、".join(bad_desc) if bad_desc else "无（%d 条全部写明）" % len(ct_names)))
    bad_ann = [n for n in ct_names
               if registry[n]["tool"]["annotations"]["destructiveHint"] is not False
               or registry[n]["tool"]["annotations"]["readOnlyHint"] is not False
               or registry[n]["tool"]["_meta"]["daniel"].get("executes") is not False]
    ok("正控（161）：确认单工具的注解不说谎（readOnlyHint=false／destructiveHint=false／executes=false）",
       not bad_ann, "异常：%s" % ("、".join(bad_ann) if bad_ann else "无"))
    # 拆成两条：**缺行**与**取值越界**是两件事，红的时候要能一眼看出该补哪一样。
    missing_action = info["actionCoverage"]["缺动作事实的命令（非空＝红：写了新写命令但没登记它的动作事实）"]
    ok("正控（161）：每条确认单工具都登记了动作事实（CONFIRM_TICKET 一行不缺）",
       not missing_action,
       "缺动作事实：%s" % ("、".join(missing_action) if missing_action
                        else "无（%d 条全部有登记）" % len(ct_names)))
    bad_action = info["actionCoverage"]["动作类型越界的命令（非空＝红）"]
    ok("正控（161）：每条确认单工具的动作类型都落在闭合枚举里（五类 ＋ 其他（本机副作用））",
       not bad_action, "越界：%s" % ("；".join(bad_action) if bad_action else
                                   "无（枚举 %s）" % "／".join(ACTION_TYPES)))

    # ── 零副作用：结构级断言（离线可跑，不依赖网络） ──
    # 做法：把 run_daniel 换成一个"记账器"，然后真调一条确认单工具 —— 记下它到底起了哪些子进程。
    # 这是本票第一验收项（CLS-78 意外真写）在**代码路径**上的守门：
    #   ① 记到的每条子进程命令都必须是**只读命令**；
    #   ② 任何一条 argv 里都不许出现 --confirm / --delete-token；
    #   ③ 那条写命令本身（lists create）一次都不许被起。
    seen_argv = []
    real_run = globals()["run_daniel"]

    def _spy(argv, timeout=1800):
        seen_argv.append(list(argv))
        return EXIT_INTERNAL, None, "", "自检拦截：本次不真跑子进程（只记 argv）"

    try:
        globals()["run_daniel"] = _spy
        probe_entry = registry["daniel_lists_create"]
        ticket = build_confirm_ticket(probe_entry, {"brand": "3690002", "name": "自检用名单"})
    finally:
        globals()["run_daniel"] = real_run
    readonly = _read_only_keys()
    spawned_keys = {"%s.%s" % (a[2], a[3]) for a in seen_argv if len(a) > 3}
    ok("正控（161）：确认单工具起过的子进程**全部是只读命令**（没有一条是写命令）",
       seen_argv and spawned_keys <= readonly,
       "起过 %d 条：%s" % (len(spawned_keys), "、".join(sorted(spawned_keys))))
    ok("正控（161）：任何子进程 argv 里都没有 --confirm／--delete-token（结构上转发不了）",
       not any("--confirm" in a or "--delete-token" in a for a in seen_argv),
       "argv %d 条全部干净" % len(seen_argv))
    ok("正控（161）：那条写命令本身一次都没被起（lists.create ∉ 起过的子进程）",
       "lists.create" not in spawned_keys, "起过的：%s" % "、".join(sorted(spawned_keys)))
    ok("正控（161）：确认单里给出的是**含 --confirm** 的可执行命令（给人到 CLI 跑），"
       "而 server 自己从不执行它",
       "--confirm" in ticket["将执行的确切命令"]
       and "--delete-token" not in ticket["将执行的确切命令"]
       and ticket["是否执行"] is False
       and ticket["退出码语义"]["退出码"] == EXIT_NEEDS_CONFIRM,
       "命令：%s ｜ 退出码 %d" % (ticket["将执行的确切命令"], ticket["退出码语义"]["退出码"]))
    ok("正控（161）：确认单六个必备字段齐备且影响面声明来自只读预查",
       all(f in ticket for f in TICKET_FIELDS)
       and all(k in ticket["影响面"] for k in ("目标工作区", "目标对象", "条数",
                                              "是否消耗配额", "只读预查"))
       and "只来自只读预查" in ticket["影响面"]["影响面来源"],
       "字段：%s" % "、".join(TICKET_FIELDS))
    # **静默为空**是本票踩过的真坑：预查结果曾经因为"按命令字符串前缀猜"而恒取不到，
    # 于是「目标工作区」恒为 None、写权限判据恒走"没拿到结论"分支 —— 表面上字段都在、
    # 断言全绿，实际影响面是空的。这里把它钉成会红的断言：
    # **要么填上真值，要么显式写明"没拿到"**，不许两者都不是。
    live = build_confirm_ticket(registry["daniel_lists_create"],
                                {"brand": "3690002", "name": "自检观看用（不执行）"})
    lws = live["影响面"]["目标工作区"]
    lsrc = live["影响面"]["目标工作区来源"]
    lprobes = live["影响面"]["只读预查"]
    l_ok = [p for p in lprobes if p.get("退出码") == EXIT_OK]
    ok("正控（161）：影响面不是静默为空（真值或显式「没拿到」，两者必居其一）",
       lws is not None or "没给出来源" in (lsrc or ""),
       "目标工作区=%r ｜ 来源=%s ｜ 只读预查成功 %d/%d 条"
       % (lws, lsrc, len(l_ok), len(lprobes)))
    ok("正控（161）：只读预查成功时写权限判据真的取到了结论（不走「没拿到结论」兜底）",
       (not l_ok) or not str(live["所需前置"][0]).startswith("写权限：只读预查没拿到结论"),
       live["所需前置"][0][:120])
    bad_probe = [r["命令"] for r in ticket["影响面"]["只读预查"]
                 if str(r.get("结果", "")).startswith("已跳过")]
    ok("[degenerate] 非只读命令进不了预查白名单（预查拒绝为了拿影响面去跑写命令）",
       not bad_probe, "被拒的：%s" % ("、".join(bad_probe) if bad_probe else "无（全部在只读白名单内）"))
    # ── 敏感参数绝不回显：**行为断言**（哨兵串在整个回包里出现 0 次） ──
    # 这是红线「任何输出都不得回显密码」的机检版。为什么用哨兵串对**整个回包**做子串计数：
    # 单点 grep 人话那一处不够 —— 实测过"人话 2 次、整个回包 4 次"，说明不止一处会漏。
    sentinel = "T161-SENTINEL-SECRET-4a1f-NEVER-ECHO"
    probe_tool = "daniel_account_credentials_set"
    stored = globals()["run_daniel"]
    try:
        globals()["run_daniel"] = _spy                 # 记账器：这一条只证"回显"，不联网
        cred_res = _confirm_ticket_result(
            registry[probe_tool], {"email": "probe@example.com", "password": sentinel})
    finally:
        globals()["run_daniel"] = stored
    whole = json.dumps(cred_res, ensure_ascii=False)
    n_hits = whole.count(sentinel)
    ok("安全（161）：确认单工具收到 password → 哨兵串在**整个回包**里出现 0 次",
       n_hits == 0, "命中 %d 次（扫过 %d 字：content ＋ structuredContent ＋ _meta 全都在内）"
       % (n_hits, len(whole)))
    ok("安全（161）：敏感参数在确认单里打成占位符（口令你自己在终端输）",
       SECRET_PLACEHOLDER in whole and "--password" in whole,
       "占位符：%s" % SECRET_PLACEHOLDER)
    ok("安全（161）：敏感参数不进 MCP 的 inputSchema（确认单永不执行 ⇒ 传了也没用，只留泄漏面）",
       "password" not in (registry[probe_tool]["tool"]["inputSchema"].get("properties") or {}),
       "被剔除的敏感参数：%s（并登记在 _meta.daniel.droppedSecretParams）"
       % (registry[probe_tool]["tool"]["_meta"]["daniel"].get("droppedSecretParams")))
    leaky = []
    for n in ct_names:
        e = registry[n]
        props = e["tool"]["inputSchema"].get("properties") or {}
        if e["secret"] and set(e["secret"]) & set(props):
            leaky.append("%s：%s" % (n, "、".join(e["secret"])))
    ok("安全（161）：其余确认单工具逐条扫过 —— 没有一条把敏感参数留在 inputSchema 里",
       not leaky, "；".join(leaky) if leaky
       else "14 条逐条扫过，只有 %s 声明了敏感参数且已剔除" % probe_tool)
    # 判据（总监 2026-10-15 追加）：**确认单里印出的命令必须真的能在 CLI 上跑通** ——
    # 印出来一条不存在的命令，比不印更糟。三级子命令最危险（把 `account credentials set`
    # 拼成 `daniel account set --confirm` 就是一条不存在的命令）。
    # 这里从 server 侧闭环：每条确认单工具印出来的前三个 token 必须 **≡ 单一真源注解里的 `cli`
    # 前三个 token**（`daniel <模块> <子命令>`），且该 `模块.子命令` 必须真在 schema 里。
    bad_cmd = []
    declared_keys = {"%s.%s" % (m["key"], c["name"])
                     for m in SCHEMA["modules"] for c in m["commands"]}
    for name in ct_names:
        e = registry[name]
        printed = human_command(e, {}).split()
        declared_cli = (e["cli"] or "").split()
        if len(printed) < 3 or len(declared_cli) < 3 or printed[:3] != declared_cli[:3]:
            bad_cmd.append("%s：印出 %r ≠ 真源 %r" % (name, " ".join(printed[:3]),
                                                   " ".join(declared_cli[:3])))
        elif "%s.%s" % (printed[1], printed[2]) not in declared_keys:
            bad_cmd.append("%s：%s.%s 不在 schema 里" % (name, printed[1], printed[2]))
    ok("正控（161）：确认单里印出的命令 ≡ 单一真源的 `模块 子命令`（不印不存在的命令）",
       not bad_cmd, "；".join(bad_cmd[:3]) if bad_cmd
       else "%d 条逐条等于真源注解的 `cli` 前缀" % len(ct_names))
    # 拒收 --confirm / --delete-token：拒因必须写死那两句可机检的话
    r1 = _confirm_ticket_result(registry["daniel_lists_create"],
                                {"brand": "x", "name": "y", "confirm": True})
    t1 = "".join(b["text"] for b in r1["content"])
    ok("[degenerate] 确认单工具收到 confirm=true → 拒绝，且拒因写明「本模式不执行写动作」"
       "＋「请拿确认单…到 CLI」",
       r1["isError"] is True and "本模式不执行写动作" in t1 and "请拿确认单" in t1
       and "CLI" in t1 and r1["_meta"]["daniel"]["executed"] is False,
       t1[:110])
    r2 = _confirm_ticket_result(registry["daniel_brands_delete"],
                                {"brand": "x", "delete_token": "x"})
    t2 = "".join(b["text"] for b in r2["content"])
    ok("[degenerate] 确认单工具收到 delete_token → 拒绝（删除类的二次确认也不代填）",
       r2["isError"] is True and "本模式不执行写动作" in t2, t2[:110])
    ok("安全：describe() 里给出的动作类型枚举与事实表一致（覆盖率如实标注）",
       info["actionCoverage"]["五类里今日无命令的类别"] == [ACTION_SYNC_FEISHU, ACTION_SEND_OUT],
       "五类里今日无命令：%s ｜ 今日有：%s"
       % ("、".join(info["actionCoverage"]["五类里今日无命令的类别"]),
          "、".join(info["actionCoverage"]["今日有命令的类别"])))
    # 安全：环境白名单里不含凭据
    ok("安全：子进程环境不含任何凭据类变量",
       not set(child_env()) & set(SENSITIVE_ENV), "白名单 %d 项" % len(ENV_ALLOWLIST))
    ok("安全：redact() 会把凭据值替换掉",
       _redact_probe() == "口令=" + REDACTED, _redact_probe())

    # 语料：随服务分发（TICKET-159）
    ok("正控：语料两条工具已注册（skills_list／skills_read）",
       "daniel_skills_list" in registry and "daniel_skills_read" in registry,
       "注册 %d 条（含 %s）" % (len(registry), "、".join(
           n for n in sorted(registry) if n.startswith("daniel_skills_"))))
    res = CorpusResources()
    try:
        items = res.list_resources()
        domains = [s.get("域") for s in res.domains()]
        ok("正控：resources 覆盖 8 个能力域 ＋ 索引 ＋ 每个切片",
           len(domains) == 8 and len(items) == 1 + 8 + sum(len(s.get("切片") or [])
                                                          for s in res.domains()),
           "resource %d 条 ｜ 能力域 %s" % (len(items), "、".join(domains)))
        idx = res.index()
        ok("正控：语料索引带版本与完整性（一眼看出本机装的是哪一版）",
           bool(idx.get("语料版本")) and idx.get("完整性") == "一致",
           "语料版本 %s ｜ 完整性 %s ｜ 落点 %s"
           % (idx.get("语料版本"), idx.get("完整性"), idx.get("语料根")))
        first = items[2]["uri"] if len(items) > 2 else None
        body = res.read(first) if first else {}
        ok("正控：resources/read 真读到切片正文（不是伪造的空串）",
           bool(body.get("text")) and body.get("mimeType") == "text/markdown",
           "%s → %d 字" % (first, len(body.get("text") or "")))
    except ResourceError as e:
        ok("正控：语料 resources 可枚举", False, "ResourceError：%s" % e)
    try:
        res.read("daniel-copilot://skills/kol-不存在的域")
        ok("[degenerate] 不认识的域 → 报错（不假装成功）", False, "竟然读到了正文")
    except ResourceError as e:
        ok("[degenerate] 不认识的域 → 报错（不假装成功）", True, str(e)[:90])
    try:
        res.read("http://example.com/x")
        ok("[degenerate] 非本 server 的 URI 方案 → 报错", False, "竟然读到了内容")
    except ResourceError as e:
        ok("[degenerate] 非本 server 的 URI 方案 → 报错", True, str(e)[:90])

    # 退化输入：参数构造
    entry = registry.get("daniel_playbook_run")
    if entry:
        argv, why = build_argv(entry, {"confirm": True})
        ok("[degenerate] 传 confirm=true 必须被拒（拒因＝本模式不执行写动作，不是「暂不暴露」）",
           argv is None and "本模式不执行写动作" in (why or "")
           and "请拿确认单" in (why or ""), why or "")
        argv, why = build_argv(entry, {"name": "minimal-skeleton", "out": "/tmp/x.json"})
        ok("正控：正常参数能拼出 `--name … --out … --json`",
           argv is not None and argv[-1] == "--json" and "--name" in argv and "--out" in argv,
           " ".join(argv[2:]) if argv else (why or ""))
    argv, why = build_argv(registry["daniel_playbook_run"], {})
    ok("[degenerate] 缺必填（不给 name）不在这里拦，交给 CLI 报退出码 2",
       argv is not None, " ".join(argv[2:]) if argv else (why or ""))

    # 退化输入：协议层
    srv = Server(registry, out=io.StringIO(), err=io.StringIO())
    srv.handle_line("这不是 JSON")
    out = srv.out.getvalue()
    ok("[degenerate] 非法 JSON → -32700 且进程不死",
       '"code": -32700' in out or '"code":-32700' in out, out.strip().replace("\n", " ")[:120])
    srv = Server(registry, out=io.StringIO(), err=io.StringIO())
    srv.handle_line(json.dumps([1, 2, 3]))
    ok("[degenerate] 顶层不是对象 → -32600",
       "-32600" in srv.out.getvalue(), srv.out.getvalue().strip()[:120])
    srv = Server(registry, out=io.StringIO(), err=io.StringIO())
    srv.handle_line(json.dumps({"jsonrpc": "2.0", "id": 7, "method": "no/such"}))
    ok("[degenerate] 未知方法 → -32601 且 id 原样回",
       "-32601" in srv.out.getvalue() and '"id": 7' in srv.out.getvalue())
    srv = Server(registry, out=io.StringIO(), err=io.StringIO())
    srv.handle_line(json.dumps({"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                                "params": {"name": "no_such_tool"}}))
    ok("[degenerate] 未知工具名 → -32602",
       "-32602" in srv.out.getvalue() and "未知工具" in srv.out.getvalue())
    srv = Server(registry, out=io.StringIO(), err=io.StringIO())
    srv.handle_line(json.dumps({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                                "params": {"name": "daniel_playbook_run",
                                           "arguments": ["x"]}}))
    ok("[degenerate] arguments 不是对象 → -32602", "-32602" in srv.out.getvalue())
    srv = Server(registry, out=io.StringIO(), err=io.StringIO())
    srv.handle_line(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))
    ok("[degenerate] 通知不回包（stdout 保持空）", srv.out.getvalue() == "",
       repr(srv.out.getvalue()[:60]))
    srv = Server(registry, out=io.StringIO(), err=io.StringIO())
    srv.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                "params": {"protocolVersion": "1900-01-01"}}))
    body = json.loads(srv.out.getvalue().strip())
    ok("[degenerate] 不认得的 protocolVersion → 回我们最新的那个",
       body["result"]["protocolVersion"] == LATEST_PROTOCOL, body["result"]["protocolVersion"])
    srv = Server(registry, out=io.StringIO(), err=io.StringIO())
    srv.handle_line(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "initialize",
                                "params": {"protocolVersion": "2025-03-26"}}))
    body = json.loads(srv.out.getvalue().strip())
    ok("正控：认得的 protocolVersion 原样回声",
       body["result"]["protocolVersion"] == "2025-03-26")
    ok("[degenerate] 白名单外的 DANIEL_* 变量不进子进程",
       "DANIEL_PASSWORD" not in child_env() and "DANIEL_EMAIL" not in child_env())
    ok("安全：describe() 里不含任何凭据值",
       not any(v and len(v) >= 4 and v in json.dumps(info, ensure_ascii=False)
               for k, v in os.environ.items() if k in SENSITIVE_ENV))

    passed = sum(1 for _, v, _ in checks if v)
    print("=== daniel-copilot MCP server 自检 ===")
    for name, good, detail in checks:
        print(" %s %s%s" % ("[通过]" if good else "[未过]", name,
                            ("  ｜ " + detail) if detail else ""))
    print("自检 %d/%d" % (passed, len(checks)))
    print("暴露口径：只读 %d 条（执行）＋ 沙箱只读 %d 条（执行）＋ **本机出件 %d 条**（执行；"
          "会写本机出件落点、不写 Daniel 远端）＋ 确认单 %d 条（**永不执行**）"
          "＝ 注册 %d 条（CLI 声明 %d 条）"
          % (info["counts"]["readOnly"], info["counts"]["sandboxOnly"],
             info["counts"]["localOutput"], info["counts"]["confirmTicket"],
             info["counts"]["registered"], info["counts"]["cliDeclared"]))
    return 0 if passed == len(checks) else 1


def _redact_probe():
    old = os.environ.get("DANIEL_PASSWORD")
    os.environ["DANIEL_PASSWORD"] = "probe-secret-153"
    try:
        return redact("口令=probe-secret-153")
    finally:
        if old is None:
            os.environ.pop("DANIEL_PASSWORD", None)
        else:
            os.environ["DANIEL_PASSWORD"] = old


# ─────────────────────────── 入口 ───────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="Daniel Copilot MCP server（stdio · TICKET-153）")
    ap.add_argument("--list-tools", action="store_true", help="打印将要注册的工具清单")
    ap.add_argument("--describe", action="store_true", help="打印暴露口径与数量统计")
    ap.add_argument("--self-test", action="store_true", help="自检（正控＋退化输入）")
    a = ap.parse_args(argv)

    if a.self_test:
        return self_test()
    registry = build_registry()
    if a.describe:
        print(json.dumps(describe(registry), ensure_ascii=False, indent=1))
        return 0
    if a.list_tools:
        print(json.dumps({"tools": [registry[k]["tool"] for k in sorted(registry)]},
                         ensure_ascii=False, indent=1))
        return 0
    # ⚠️ 措辞不许省成"只读工具"：**88 条里只有 65 条是纯只读** —— 还有 1 条本机出件（会写本机落点）、
    # 1 条沙箱执行（写只落本次运行沙箱）、21 条确认单（永不执行）。TICKET-202·Q14。
    _ro = sum(1 for v in registry.values() if v["exposure"] == "read-only")
    print("· daniel-copilot MCP server（stdio）已就绪：注册 %d 条工具（只读 %d ／ 本机出件 %d ／ "
          "沙箱执行 %d ／ 确认单 %d）"
          % (len(registry), _ro,
             sum(1 for v in registry.values() if v["exposure"] == "local-output"),
             sum(1 for v in registry.values() if v["exposure"] == "sandbox-only"),
             sum(1 for v in registry.values() if v["exposure"] == "confirm-ticket")),
          file=sys.stderr, flush=True)
    return Server(registry).serve()


if __name__ == "__main__":
    sys.exit(main())
