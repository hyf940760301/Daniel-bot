# -*- coding: utf-8 -*-
"""account 模块：账号与盘点（登录状态、可见工作区、能力矩阵、审计、数据落点）。

本模块是"权限驱动写链"的**入口**：
  · `capabilities` 打印能力矩阵（12 个业务模块 × 读/写 × 是否允许 ＋ 理由），
    写命令能不能用就是按这张表判的（同一份实现：`daniel_cli/permissions.py`）；
  · `credentials`（只读）看凭据从哪来；`credentials-set`（写操作）把凭据写进**本机系统钥匙串**
    —— 新机器上"装好即用"的第一步（TICKET-170）；
  · `login`（写操作）真登录并把会话落进数据落点（权限 600），登录后回读账号名确认是真实账号；
  · `audit` 导出写操作审计（时间／账号／工作区／品牌／动作／影响范围／回读结果／是否回滚）。

两条写命令的凭据纪律（TICKET-170）：
  · **只包装**既有仪器 `.kol-tools/daniel_credentials.py`，不改它的存储口径与优先级；
  · **任何输出都不回显密码** —— 参数里的密码在进"执行计划"之前就从参数里抹掉，只留掩码邮箱；
  · 钥匙串写失败**不静默降级为明文**：非零退出并给出指引，且不写任何明文凭据文件。
"""
import hashlib
import json
import os
import stat as stat_mod
import sys

from .. import accounts as accounts_mod
from .. import audit as audit_mod
from .. import authgate
from .. import permissions
from ..exits import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE
from ..runtime import CliError, load_capability, load_client, new_client
from ._common import (STAGE_LIVE, credential_status, gated_write, paths_snapshot)

BOARD = "account"

#: 凭据来源 → 给人看的说法（不回显任何凭据值）
SOURCE_LABEL = {
    "keychain": "本机系统钥匙串",
    "env": "环境变量 DANIEL_EMAIL／DANIEL_PASSWORD",
    "legacy_plaintext_file": "旧的明文凭据文件（只读兼容）",
    "plaintext_fallback": "明文降级文件（需要显式开启）",
    "none": "没有找到任何来源",
}

#: 钥匙串写失败时的指引（**不提供**自动明文降级：那是本票的红线）
KEYCHAIN_FAIL_HINT = (
    "请在本机自己的终端里重跑同一条命令（无人值守或受限环境里，系统常会拒绝写钥匙串）；"
    "本命令**只写系统钥匙串，不会退而写明文文件**。若这台机器确实没有可用钥匙串"
    "（例如非 macOS 环境）而你确实需要明文降级，请显式设置 DANIEL_ALLOW_PLAINTEXT=1 后"
    "用凭据工具 `python3 .kol-tools/daniel_credentials.py store-set --from-legacy` 自行写入 —— "
    "那一步的明文风险由这次显式选择承担，本命令不代做。"
    "写完用 `daniel account credentials` 看来源是否为钥匙串。"
)

#: 没有可用凭据时，登录命令给出的下一步（人话＋明确指向写入入口）
NO_CREDENTIAL_HINT = (
    "先跑 `daniel account credentials set --email <你的邮箱> --confirm`"
    "（或 `--from-env`，从环境变量 DANIEL_EMAIL／DANIEL_PASSWORD 读）"
    "把凭据写进本机系统钥匙串；写好后跑 `daniel account login --confirm` 登录，"
    "再用 `daniel account whoami` 确认登录的是你的账号。"
)


# ─────────────────────────── 凭据：来源与掩码 ───────────────────────────
def _credentials_module():
    return load_capability("daniel_credentials")


def _mask(email):
    """掩码邮箱（沿用凭据仪器的掩码口径：只露形状，不露值）。"""
    return _credentials_module().mask_email(email)


def _scrub(text, *secrets):
    """把文本里出现过的秘密值抹掉（纵深防御：万一哪条上游消息回显了值也不许流到输出）。"""
    out = str(text or "")
    for s in secrets:
        if s:
            out = out.replace(str(s), "<已隐去>")
    return out


def _purge_args(ctx, *names):
    """把敏感参数从 `ctx.args` 里**彻底删掉**。

    为什么必须删：写链的执行计划（`_common._plan_from_args` 直接遍历 `vars(ctx.args)`）、
    审计记录与 `--json` 结果都会把参数原样打印出来。密码只要还留在参数里，就会进计划、
    进审计、进 stdout —— 这是本票最硬的一条红线。
    """
    for n in names:
        try:
            delattr(ctx.args, n)
        except AttributeError:
            pass


def _credential_input(ctx):
    """解出本次要写入的凭据 `{email, password, fromEnv}`，并把参数里的明文抹掉。

    来源二选一（写进帮助文本，口径只有这一份）：
      · `--from-env`：只认环境变量 `DANIEL_EMAIL`／`DANIEL_PASSWORD`（与 `--email/--password`
        同时给就报用法错，避免"以为写的是 A、实际写的是 B"）；
      · 不给 `--from-env`：邮箱取 `--email`（没有就退回环境变量 `DANIEL_EMAIL`），
        密码取 `--password`（没有就退回环境变量 `DANIEL_PASSWORD`）。
    """
    creds = _credentials_module()
    from_env = bool(ctx.get("from-env"))
    email, password = ctx.get("email"), ctx.get("password")
    if from_env and (email or password):
        raise CliError("--from-env 与 --email／--password 不能同时给：凭据来源二选一，"
                       "避免「以为写的是这一份、实际写的是那一份」",
                       hint="要么加 --from-env（只读环境变量），要么用 --email／--password 显式给")
    if from_env:
        email, password = os.environ.get("DANIEL_EMAIL"), os.environ.get("DANIEL_PASSWORD")
        missing = [n for n, v in (("DANIEL_EMAIL", email), ("DANIEL_PASSWORD", password)) if not v]
        if missing:
            raise CliError("环境变量里没有备齐凭据：缺 %s" % "／".join(missing),
                           hint="在环境里设好 DANIEL_EMAIL 与 DANIEL_PASSWORD 后重试；"
                                "或改用 --email／--password 显式传入")
    else:
        email = email or os.environ.get("DANIEL_EMAIL")
        password = password or os.environ.get("DANIEL_PASSWORD")
        if not email or not password:
            raise CliError("凭据没给齐（缺%s）" % ("邮箱" if not email else "密码"),
                           hint="两条路任选：① `daniel account credentials set --email <你的邮箱> "
                                "--confirm`（密码从环境变量 DANIEL_PASSWORD 读，不进命令行历史）；"
                                "② `daniel account credentials set --from-env --confirm`"
                                "（邮箱与密码都从环境变量读）")
    ctx.credential_input = {"email": email, "password": password, "fromEnv": from_env}
    _purge_args(ctx, "email", "password")             # 明文不进计划、不进审计、不进输出
    ctx.args.account_email_masked = creds.mask_email(email)
    return ctx.credential_input


# ─────────────────────────── 会话文件指纹 ───────────────────────────
def _session_path():
    dpaths = load_capability("daniel_paths")
    return dpaths.resolve("session_file")


def _session_fingerprint():
    """会话文件的**无内容**指纹（存在性／权限／内容摘要前 12 位）。

    只留摘要，不留内容：会话文件里是登录票据，本身也是凭据，不进任何输出。
    """
    path = _session_path()
    fp = {"path": path, "exists": os.path.exists(path), "sha12": None, "mode": None}
    if not fp["exists"]:
        return fp
    try:
        with open(path, "rb") as fh:
            fp["sha12"] = hashlib.sha256(fh.read()).hexdigest()[:12]
        fp["mode"] = oct(stat_mod.S_IMODE(os.stat(path).st_mode))
    except OSError:
        pass
    return fp


def _ensure_session_mode_600(path):
    """会话文件权限收到 600（本票要求"会话落 DANIEL_HOME/session/（权限 600）"）。"""
    try:
        before = oct(stat_mod.S_IMODE(os.stat(path).st_mode))
    except OSError:
        return None, False
    if before == "0o600":
        return before, False
    try:
        os.chmod(path, 0o600)
        return "0o600", True
    except OSError:
        return before, False


# ═══════════════════ 按工作区读配额／权益（TICKET-203） ═══════════════════
# 起因：写链的落点**跟随"品牌所属工作区"**（`commands/mod_takeover.py`：`ws = b.get("workspaceId")`），
# 而 `capabilities` 只看得到**当前所在工作区** ⇒ 写之前无法知道目标工作区还有没有品牌位，
# 代价已经真实发生过（`TICKET-188` 链路 6 跑到服务端才知道 `limit=2/used=2` 已满）。
#
# 本节的**唯一口径**（三条硬红线，全在这一节的纯函数里落地）：
#   ① 平台没返回上限 ⇒ 一律写「未知」，**绝不用已用数冒充上限、绝不静默填 0**；
#   ② 平台口径的 `-1` 是"不限"，如实写「不限」（既不是未知、也不是 0）；
#   ③ 上限或已用缺一个 ⇒ 余量与"是否已满"也写「未知」，**不猜**。
#
# 取数走**降级阶梯**（能力因账号角色而异，逐级如实标注用的是哪一级）：
#   ① `admin.listWorkspaces`：一次请求拿**全部工作区**，每个带 `maxBrands`（上限）
#      ＋ `brandCount`（已用）＋ `currentUsage`（检索／邮件）＋ `enabledFeatures`（权益）；
#   ② `workspaces.list`：同一批工作区，但**不返回上限** ⇒ 上限记「未知」；
#   ③ `brands.list {workspaceId}`：逐工作区**复算已用数**（`len(rows)`），上限仍记「未知」。
# ①②需要管理角色（未实测非管理角色是否可调 —— 手上只有 super_admin 账号）；③任何角色都能用。
QUOTA_UNKNOWN = "未知"
QUOTA_UNLIMITED = "不限"

#: 降级阶梯的三条通路名（写进结果，让读者知道这一级给不给上限）
QUOTA_ROUTE_ADMIN = "admin.listWorkspaces"
QUOTA_ROUTE_PUBLIC = "workspaces.list"
QUOTA_ROUTE_BRANDS = "brands.list"


def _int_or_none(v):
    """宽松取整：非数字（含 `True`／`None`／字符串垃圾）→ None。**不把取不到的算成 0**。"""
    if isinstance(v, bool) or v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def quota_cell(limit, used, limit_source="", used_source="", unit="个"):
    """一条配额读数：上限／已用／余量／是否已满（**唯一口径**，见本节开头三条红线）。

    `limit` 的原值另存在 `原始上限` 里（供下层判据用），展示值只给"数字／未知／不限"三种。
    """
    lim, usd = _int_or_none(limit), _int_or_none(used)
    cell = {"上限": QUOTA_UNKNOWN, "已用": QUOTA_UNKNOWN if usd is None else usd,
            "余量": QUOTA_UNKNOWN, "是否已满": None, "上限是否已知": False,
            "单位": unit,
            "上限来源": limit_source or "平台未返回上限",
            "已用来源": used_source or "平台未返回已用数",
            "原始上限": lim, "原始已用": usd}
    if lim is None:
        return cell
    cell["上限是否已知"] = True
    if lim < 0:                                   # 平台口径：-1 ＝ 不限
        cell["上限"] = QUOTA_UNLIMITED
        cell["余量"] = QUOTA_UNLIMITED
        cell["是否已满"] = False
        return cell
    cell["上限"] = lim
    if usd is None:
        return cell
    cell["余量"] = max(lim - usd, 0)
    cell["是否已满"] = bool(usd >= lim)
    return cell


def quota_block_from_row(row, origin, limit_key, brand_limit_source, brand_used_source):
    """把**一行工作区记录**转成配额块。**上限字段不存在时如实记「未知」**（不猜、不填 0）。

    同一个函数服务两条通路（`admin.listWorkspaces` 有 `maxBrands`；`workspaces.list` 没有），
    品牌那一格的差别只由 `limit_key` 决定 —— 于是"某条通路不给上限"这件事在结果里**结构上可见**：
    `workspaces.list` 没有 `maxBrands` 这个键 ⇒ 品牌上限必然落到「未知」。
    检索／邮件的上限取自 `currentUsage.*Limit`（缺了才退回 `max*PerMonth`），已用取自
    `currentUsage.*Used` —— 两个来源各自写进 `上限来源`／`已用来源`，不混。
    """
    row = row if isinstance(row, dict) else {}
    usage = row.get("currentUsage") if isinstance(row.get("currentUsage"), dict) else {}
    limit = row.get(limit_key)
    sl = usage.get("searchesLimit")
    if sl is None:
        sl = row.get("maxSearchesPerMonth")
    el = usage.get("emailsLimit")
    if el is None:
        el = row.get("maxEmailsPerMonth")
    named = "%s.{字段}" % origin
    return {
        "工作区编号": _int_or_none(row.get("id")),
        "工作区名称": row.get("name"),
        "计划": row.get("planTier"),
        "状态": row.get("status"),
        "品牌配额": quota_cell(limit, row.get("brandCount"), brand_limit_source,
                             brand_used_source, "个品牌"),
        "检索配额": quota_cell(sl, usage.get("searchesUsed"),
                             named.format(字段="currentUsage.searchesLimit"),
                             named.format(字段="currentUsage.searchesUsed"), "次/月"),
        "邮件配额": quota_cell(el, usage.get("emailsSent"),
                             named.format(字段="currentUsage.emailsLimit"),
                             named.format(字段="currentUsage.emailsSent"), "封/月"),
        "工作区权益": row.get("enabledFeatures"),
        "成员数": _int_or_none(row.get("memberCount")),
        "取数来源": origin,
    }


def quota_block_from_used_only(used, ws_id=None, name=None, plan_tier=None, status=None,
                               used_source="", origin="", features=None):
    """只拿得到「已用数」时的读数：**上限一律记「未知」**（这一路走的就是红线①）。"""
    return {
        "工作区编号": _int_or_none(ws_id),
        "工作区名称": name,
        "计划": plan_tier,
        "状态": status,
        "品牌配额": quota_cell(None, _int_or_none(used), "", used_source, "个品牌"),
        "检索配额": quota_cell(None, None, "", "", "次/月"),
        "邮件配额": quota_cell(None, None, "", "", "封/月"),
        "工作区权益": features,
        "成员数": None,
        "取数来源": origin or used_source,
    }


def _quota_query(client, route, inp):
    """发一次只读查询；失败不抛（阶梯要往下走），返回 `(结果, 失败原因)`。"""
    try:
        return client.query(route, inp), None
    except Exception as e:                                            # noqa: BLE001
        return None, "%s 取不到：%s" % (route, str(e)[:160])


def quota_rows_admin(client):
    """阶梯①：管理面工作区清单（含上限与已用）。返回 `(rows, 失败原因)`。"""
    rows, err = _quota_query(client, QUOTA_ROUTE_ADMIN, {})
    if isinstance(rows, list) and rows:
        return rows, None
    return None, err or "%s 返回空清单" % QUOTA_ROUTE_ADMIN


def quota_rows_public(client):
    """阶梯②：公开工作区清单（**只有已用数，没有上限**）。返回 `(rows, 失败原因)`。"""
    rows, err = _quota_query(client, QUOTA_ROUTE_PUBLIC, {})
    if isinstance(rows, list) and rows:
        return rows, None
    return None, err or "%s 返回空清单" % QUOTA_ROUTE_PUBLIC


def _row_for(rows, ws_id):
    want = _int_or_none(ws_id)
    for r in (rows or []):
        if isinstance(r, dict) and _int_or_none(r.get("id")) == want:
            return r
    return None


def workspace_quota(client, ws_id, visible=None):
    """**一个**工作区的配额读数 → `(块, 取数说明)`（永远不会返回 None：最差也如实说"取不到"）。

    阶梯走到哪一级、那一级给不给上限，全部写在结果里（读者不必猜）。
    """
    want = _int_or_none(ws_id)
    if want is None:
        return (quota_block_from_used_only(None, ws_id), "工作区编号不是数字：没有发起任何请求")

    rows, err1 = quota_rows_admin(client)
    if rows is not None:
        row = _row_for(rows, want)
        if row is not None:
            blk = quota_block_from_row(
                row, "%s（一次请求拿全部工作区）" % QUOTA_ROUTE_ADMIN,
                "maxBrands", "%s.maxBrands" % QUOTA_ROUTE_ADMIN,
                "%s.brandCount" % QUOTA_ROUTE_ADMIN)
            return blk, ("管理面工作区清单（%s）：上限与已用都来自平台读数" % QUOTA_ROUTE_ADMIN)
        err1 = "%s 里没有工作区 %s（该清单共 %d 条）" % (QUOTA_ROUTE_ADMIN, want, len(rows))

    rows2, err2 = quota_rows_public(client)
    if rows2 is not None:
        row = _row_for(rows2, want)
        if row is not None:
            blk = quota_block_from_row(
                row, "%s（该通路**不返回上限**）" % QUOTA_ROUTE_PUBLIC,
                "maxBrands", "%s 不返回上限 ⇒ 记「未知」" % QUOTA_ROUTE_PUBLIC,
                "%s.brandCount" % QUOTA_ROUTE_PUBLIC)
            return blk, ("工作区清单（%s）：只有已用数，上限平台未返回 ⇒ 记「未知」"
                         % QUOTA_ROUTE_PUBLIC)
        err2 = "%s 里没有工作区 %s" % (QUOTA_ROUTE_PUBLIC, want)

    bs, err3 = _quota_query(client, QUOTA_ROUTE_BRANDS, {"workspaceId": want})
    if isinstance(bs, list):
        info = None
        for r in (visible or []):
            if isinstance(r, dict) and _int_or_none(r.get("id")) == want:
                info = r
                break
        blk = quota_block_from_used_only(
            len(bs), want, (info or {}).get("name"), (info or {}).get("planTier"),
            None, "%s {workspaceId=%s} 的条数（复算）" % (QUOTA_ROUTE_BRANDS, want),
            "逐工作区复算（%s）：只有已用数，上限平台未返回 ⇒ 记「未知」" % QUOTA_ROUTE_BRANDS)
        return blk, ("降级到逐工作区复算（%s）：%s；%s" % (QUOTA_ROUTE_BRANDS, err1, err2))

    return (quota_block_from_used_only(None, want),
            "三级通路都取不到（①%s ②%s ③%s）⇒ 上限与已用都记「未知」"
            % (err1, err2, err3))


def quota_map_for(client, visible=None):
    """**全部**可见工作区的配额读数 → `({id: 块}, 取数说明, {id: 该级未覆盖的编号})`。

    用于 `account workspaces --with-quota`：与单工作区同一条阶梯，但**只走前两级**
    （第三级要按工作区逐个请求，112 个工作区会打出一百多次请求 ⇒ 本命令不做，如实标注未覆盖）。
    """
    rows, err1 = quota_rows_admin(client)
    if rows is not None:
        m = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            wid = _int_or_none(r.get("id"))
            if wid is None:
                continue
            m[wid] = quota_block_from_row(
                r, "%s（一次请求拿全部工作区）" % QUOTA_ROUTE_ADMIN,
                "maxBrands", "%s.maxBrands" % QUOTA_ROUTE_ADMIN,
                "%s.brandCount" % QUOTA_ROUTE_ADMIN)
        return m, ("管理面工作区清单（%s）：%d 个工作区的上限与已用都来自平台读数"
                   % (QUOTA_ROUTE_ADMIN, len(m))), set()

    rows2, err2 = quota_rows_public(client)
    if rows2 is not None:
        m = {}
        for r in rows2:
            if not isinstance(r, dict):
                continue
            wid = _int_or_none(r.get("id"))
            if wid is None:
                continue
            m[wid] = quota_block_from_row(
                r, "%s（该通路**不返回上限**）" % QUOTA_ROUTE_PUBLIC,
                "maxBrands", "%s 不返回上限 ⇒ 记「未知」" % QUOTA_ROUTE_PUBLIC,
                "%s.brandCount" % QUOTA_ROUTE_PUBLIC)
        return m, ("工作区清单（%s）：只有已用数，上限平台未返回 ⇒ 一律记「未知」"
                   % QUOTA_ROUTE_PUBLIC), set()

    missing = {_int_or_none((r or {}).get("id")) for r in (visible or [])
               if isinstance(r, dict)}
    return {}, ("三级通路里能一次拿全的前两级都取不到（①%s；②%s）⇒ **不逐工作区打一百多次请求**，"
                "所有工作区的上限与已用都记「未知」" % (err1, err2)), missing


def quota_summary(rows):
    """配额小结（给人看的一句话 ＋ 四个计数）——用来直接回答"还有哪个工作区能写"。"""
    full = room = unknown = unlimited = 0
    for r in (rows or []):
        cell = ((r or {}).get("配额") or {}).get("品牌配额") or {}
        if not cell.get("上限是否已知"):
            unknown += 1
        elif cell.get("上限") == QUOTA_UNLIMITED:
            unlimited += 1
        elif cell.get("是否已满"):
            full += 1
        else:
            room += 1
    return {
        "有余量": room, "已满": full, "不限": unlimited, "上限未知": unknown,
        "一句话": ("品牌位还有余量的工作区 %d 个；已满 %d 个；上限不限 %d 个；"
                   "上限未知 %d 个（未知不等于有位置，写之前请按目标工作区单独核）"
                   % (room, full, unlimited, unknown)),
    }


def quota_usage_for_verdict(quota):
    """配额读数 → `permissions.verdict` 认的 `usage` 形状（**配额轴判据仍只有那一份实现**）。

    上限未知时**留 None**（`permissions` 的口径是"未声明上限，不拦"）—— 关键是不能拿
    另一个工作区的上限顶替，那等于把 A 的数说成 B 的数。
    """
    q = quota or {}
    b = q.get("品牌配额") or {}
    s = q.get("检索配额") or {}
    wid = _int_or_none(q.get("工作区编号"))
    return {
        "brands": {"limit": b.get("原始上限"), "used": b.get("原始已用"),
                   "workspaceId": wid, "note": b.get("已用来源") or ""},
        "searches": {"limit": s.get("原始上限"), "used": s.get("原始已用"),
                     "workspaceId": wid,
                     "note": "每月检索额度用量取自 %s" % (s.get("已用来源") or "平台未返回")},
    }


def auth_scoped_to_workspace(auth, quota):
    """把账号快照复制一份，**配额轴与权益轴换成目标工作区的取值**（其余判据轴一律不动）。

    为什么必须复制：`capabilities` 的"账号"块仍要如实显示**当前所在工作区**，而矩阵要回答的是
    "若写目标工作区，判据是什么" —— 两个口径不同，必须各留一份、不能就地改。
    目标工作区上限未知时显式留 `None`：**绝不用当前工作区的上限顶替**。
    """
    if not isinstance(auth, dict) or not quota:
        return auth
    b = quota.get("品牌配额") or {}
    s = quota.get("检索配额") or {}
    e = quota.get("邮件配额") or {}
    out = dict(auth)
    out["workspace"] = {"id": _int_or_none(quota.get("工作区编号")),
                        "name": quota.get("工作区名称"),
                        "planTier": quota.get("计划"),
                        "status": quota.get("状态"),
                        "maxBrands": b.get("原始上限"),
                        "maxSearchesPerMonth": s.get("原始上限"),
                        "maxEmailsPerMonth": e.get("原始上限")}
    out["activeWorkspaceId"] = _int_or_none(quota.get("工作区编号"))
    # 权益轴：平台可能给 `null`（＝"没有单独配过"）。前端自己的读法是 `s.enabledFeatures ?? []`
    # （`WorkspaceAdministration.tsx`），这里沿用**平台自己的口径**（null ⇒ 空集），
    # 并把原始值留在说明里 —— 不把"平台没给"说成"已开启"。
    out["enabledFeatures"] = list(quota.get("工作区权益") or [])
    out["权益取值说明"] = ("目标工作区权益的原始取值是 %s；前端口径是 `?? []`（视为未开启任何可选权益）"
                          % ("null（未单独配置）" if quota.get("工作区权益") is None
                             else "／".join(out["enabledFeatures"]) or "空"))
    return out


def workspace_visibility_problem(visible, target):
    """目标工作区在不在账号**可见清单**里 → 问题说明 或 `None`（**纯函数**，离线可验）。

    口径：账号看不到的工作区**不假装能读**（平台不会返回别的工作区的配额）。但清单本身没拿到时
    （快照里没带 `workspaces`）**不拦** —— 让配额通路去如实报"取不到"，而不是在本地自造一道
    可能误伤的闸。
    """
    known = {_int_or_none(r.get("id")) for r in (visible or []) if isinstance(r, dict)}
    known.discard(None)
    if not known:
        return None
    want = _int_or_none(target)
    if want not in known:
        return ("工作区 %s 不在这个账号可见的工作区清单里（可见 %d 个）" % (want, len(known)))
    return None


def quota_write_verdict(quota):
    """**写链前置检查**的一句话结论：目标工作区的品牌位还有没有余量（不猜、不含糊）。"""
    cell = (quota or {}).get("品牌配额") or {}
    if not cell.get("上限是否已知"):
        return ("上限未知（平台没返回这个工作区的品牌上限）⇒ **不能断定还有位置**；"
                "已用 %s。要么按已用数与历史行为判断，要么先换一个有上限可读的工作区。"
                % cell.get("已用"))
    if cell.get("上限") == QUOTA_UNLIMITED:
        return "上限不限 ⇒ 有位置（当前已用 %s）" % cell.get("已用")
    if cell.get("是否已满"):
        return ("**已满**（上限 %s，已用 %s）⇒ 在这个工作区建品牌会被服务端拒；"
                "先换工作区，或在 Daniel 管理端把这个工作区的品牌上限调上去（本 CLI 不做这件事）"
                % (cell.get("上限"), cell.get("已用")))
    return "还有位置：余量 %s（上限 %s，已用 %s）" % (cell.get("余量"), cell.get("上限"),
                                                    cell.get("已用"))


# ─────────────────────────── 读命令 ───────────────────────────
def cmd_whoami(ctx):
    d = new_client(verbose=ctx.verbose)
    ctx.progress("正在读取当前登录账号")
    me = d.query("auth.me", {}) or {}
    email = me.get("email") or d.whoami()
    if not email:
        raise CliError("拿不到当前账号（会话或凭据可能已失效）", code=EXIT_USAGE,
                       hint="先跑 daniel account credentials 看凭据来源；"
                            "没有凭据时先跑 daniel account credentials set --email <你的邮箱> --confirm")
    ctx.emit(data={"email": email,
                   "systemRole": me.get("systemRole"),
                   "role": me.get("role"),
                   "userStatus": me.get("userStatus"),
                   "activeWorkspaceId": me.get("activeWorkspaceId")
                                        or d.active_workspace_id()},
             route="auth.me")
    return EXIT_OK


def cmd_workspaces(ctx):
    """列出账号可见的工作区；`--with-quota` 时**每个工作区带上配额读数**（TICKET-203）。

    配额的取数走 `quota_map_for()` 的同一条降级阶梯：管理面清单（上限＋已用）→ 工作区清单
    （只有已用，上限记「未知」）→ 取不到就一律记「未知」（**不逐工作区打一百多次请求**）。
    全程**只读**：不切工作区、不改任何数据。
    """
    d = new_client(verbose=ctx.verbose)
    ctx.progress("正在读取可见工作区")
    rows = d.query("auth.listMyWorkspaces", {}) or []
    rows = [r for r in rows if isinstance(r, dict)]
    active = d.active_workspace_id()
    for r in rows:
        r["isActive"] = (r.get("id") == active)
    data = {"count": len(rows), "activeWorkspaceId": active, "workspaces": rows}
    if ctx.get("with-quota"):
        ctx.progress("正在按工作区读配额（只读；一次请求拿全部工作区）")
        qmap, how, missing = quota_map_for(client=d, visible=rows)
        for r in rows:
            wid = _int_or_none(r.get("id"))
            blk = qmap.get(wid)
            if blk is None:
                blk = quota_block_from_used_only(
                    None, wid, r.get("name"), r.get("planTier"), None, "",
                    "本命令未取到（该工作区不在本次配额通路的返回里）")
            r["配额"] = blk
        data["配额取数说明"] = how
        data["配额小结"] = quota_summary(rows)
        if missing:
            data["配额小结"]["未覆盖的工作区数"] = len(missing)
    ctx.emit(data=data, route="auth.listMyWorkspaces")
    return EXIT_OK


def cmd_credentials(ctx):
    """只回来源与掩码，**不回显任何密码**。"""
    ctx.progress("正在盘点凭据来源（不会回显密码）")
    ctx.emit(data=credential_status())
    return EXIT_OK


def _partition_plain_words(facts):
    """把"数据落在哪、为什么"写成一句**非工程读者也能懂**的人话。

    为什么必须有这一句：只给路径与来源码（`partition:xxx`）等于没解释 —— 用户要的是
    "我现在的文件在哪、会不会丢、怎么回到原来的样子"。
    """
    if facts["是否已分区"]:
        return ("你现在用的是账号 %s，数据（会话、缓存、产出的文件、任务队列）都放在 "
                "%s 这个专属目录里，与别的账号互不可见；这是切账号时自动分开的，"
                "切换前那些文件一直在 %s、**一个都没有被搬动或删除**。"
                "换账号：`daniel account switch <邮箱> --confirm`；"
                "回到切换前的位置：`daniel account switch --clear --confirm`。"
                % (facts["当前账号(掩码)"] or "（未知）", facts["生效落点"],
                   facts["数据落点根"]))
    return ("你还没有切换过账号，数据就落在原来的位置 %s —— 与升级前**完全一样**（没有搬家、"
            "没有删除）。要用多个账号时，先 `daniel account switch <邮箱> --confirm` 切到某个"
            "账号，那个账号的数据会分到它自己的目录里，与其它账号互不可见；"
            "根目录里既有的文件会一直留在原地。" % facts["数据落点根"])


def cmd_paths(ctx):
    """数据落点 ＋ **当前账号的分区**（TICKET-186 · A2 的"回读当前分区"入口）。

    两条口径写死在这里：
      · 落点**一律**由 `daniel_paths` 解析（本命令只是把它的结果读出来，不自造第二份）；
      · 分区**一律**由 `accounts.partition_home()` 算（单一真源），本命令不含任何拼接逻辑。
    """
    ctx.progress("正在解析数据落点")
    snap = paths_snapshot()
    facts = accounts_mod.partition_facts()
    snap["账号分区"] = {
        "一句话说明": _partition_plain_words(facts),
        "当前账号(掩码)": facts["当前账号(掩码)"],
        "是否已分区": facts["是否已分区"],
        "数据落点根": facts["数据落点根"],
        "根的选择理由": facts["根的选择理由"],
        "根的选择理由(人话)": facts["根的选择理由(人话)"],
        "当前账号分区": facts["当前账号分区"],
        "生效落点": facts["生效落点"],
        "落点来源": facts["落点来源"],
        "分区规则": facts["分区规则"],
        "凭据账号钉在哪": _mask(facts["凭据账号钉在哪"]) if facts["凭据账号钉在哪"] else None,
        "账号状态文件": facts["账号状态文件"],
    }
    ctx.emit(data=snap)
    return EXIT_OK


def cmd_list(ctx):
    """看当前账号 ＋ 列已存账号（**一条只读命令**把"我在哪个账号、还有哪些账号"讲清楚）。

    不做任何写：只读账号状态文件与**钥匙串里条目在不在**（`security` 不带 `-w`，绝不读值）。
    """
    ctx.progress("正在盘点账号与数据分区（不回显任何凭据值）")
    data = accounts_mod.list_accounts()
    data["说明"] = ("「是否当前」＝本机当前选中的账号；「分区落点」＝该账号的数据目录"
                    "（会话／缓存／产出／调度都在这下面）。切账号用 "
                    "`daniel account switch <邮箱> --confirm`。")
    data["钥匙串条目怎么核的"] = ("只问系统「这个账号有没有条目」（不带 -w），"
                                  "**不读、不打印任何凭据值**")
    ctx.emit(data=data)
    return EXIT_OK


def cmd_capabilities(ctx):
    """能力矩阵：本账号对每个模块能读什么、能写什么、为什么。

    判据与写命令用的是**同一份实现**（`permissions.verdict`），因此这里的结论就是
    写命令实际会执行的结论 —— 不存在"报告说能写、命令却拒绝"这种两套口径。

    `--workspace <编号>`（TICKET-203）：把**配额轴与权益轴**换成**目标工作区**的取值，并单独给出
    "这个工作区还剩多少品牌位"的一段读数 —— 写链的落点跟随"品牌所属工作区"，所以写之前必须按
    **目标工作区**看配额，而不是只看当前所在的那个。**本命令不会切换工作区**（不调
    `auth.switchWorkspace`、不改任何数据）。
    """
    force = bool(ctx.get("refresh"))
    ctx.progress("正在读取账号事实（角色／状态／工作区权益与配额）")
    auth, why = permissions.current_auth(force=force)
    target = _int_or_none(ctx.get("workspace"))
    quota = None
    quota_how = ""
    visible = (auth or {}).get("workspaces") or []
    if target is not None:
        problem = workspace_visibility_problem(visible, target)
        if problem:
            raise CliError(
                problem,
                code=EXIT_USAGE,
                hint="用 `daniel account workspaces` 看可见清单；"
                     "配额只能对**账号能看到的工作区**读（平台不返回别的工作区的配额）")
    usage = None
    if auth is None:
        ctx.warn("账号事实取不到：%s（写操作会按「确认不了权限就不动手」处理）" % why)
    elif auth.get("source") != "fixture":
        if target is None:
            ctx.progress("正在读取配额用量（只读）")
            usage = permissions.probe_usage(auth)
        else:
            ctx.progress("正在读取工作区 %s 的配额与权益（只读；不会切换当前工作区）" % target)
            quota, quota_how = workspace_quota(new_client(verbose=ctx.verbose), target,
                                               visible=visible)
            usage = quota_usage_for_verdict(quota)
    elif target is not None:
        ctx.note("本次用的是注入快照（%s）：配额读数不联网，不下发任何请求" % why)

    matrix_auth = auth
    if quota:
        matrix_auth = auth_scoped_to_workspace(auth, quota)
    rows = permissions.capability_matrix(matrix_auth, usage)
    only = ctx.get("module") or []
    if only:
        wanted = {str(m) for m in only}
        rows = [r for r in rows if r["模块"] in wanted]
        if not rows:
            raise CliError("--module 里的模块名都不认识：%s" % "／".join(sorted(wanted)),
                           hint="可用模块：%s" % "／".join(permissions.rule_keys()))
    summary = permissions.summarize(rows)
    data = {
        "账号": ({"邮箱": (auth or {}).get("emailMasked"),
                  "系统角色": (auth or {}).get("systemRole"),
                  "账号角色": (auth or {}).get("role"),
                  "账号状态": (auth or {}).get("userStatus"),
                  "当前工作区": (auth or {}).get("activeWorkspaceId"),
                  "工作区计划": ((auth or {}).get("workspace") or {}).get("planTier"),
                  "配额上限": {"品牌数": ((auth or {}).get("workspace") or {}).get("maxBrands"),
                               "每月检索": ((auth or {}).get("workspace") or {}).get("maxSearchesPerMonth"),
                               "每月邮件": ((auth or {}).get("workspace") or {}).get("maxEmailsPerMonth")},
                  "工作区权益": (auth or {}).get("enabledFeatures")} if auth else None),
        "判据说明": "读写是否开放由账号的使用权限决定（系统角色／账号状态／工作区权益／配额四轴）；"
                    "本工程不引入审批流。",
        "取数说明": why,
        "配额用量": usage,
        "小结": summary,
        "能力矩阵": rows,
    }
    if quota:
        data["配额口径适用于工作区"] = target
        data["目标工作区配额"] = quota
        data["目标工作区配额取数说明"] = quota_how
        data["写链前置检查（目标工作区）"] = quota_write_verdict(quota)
        data["说明"] = ("本命令**没有切换当前工作区**（当前仍是 %s）；"
                        "能力矩阵的配额轴与权益轴已换成目标工作区 %s 的取值，"
                        "其余判据轴（系统角色／账号状态）取本账号。"
                        % ((auth or {}).get("activeWorkspaceId"), target))
    ctx.emit(data=data)
    return EXIT_OK


def cmd_audit(ctx):
    """导出写操作审计（写链的第三道纪律：每次写都要留一条可导出记录）。"""
    ctx.progress("正在读取写操作审计记录")
    payload = audit_mod.export(out_path=ctx.get("out"), limit=ctx.get("limit"))
    ctx.emit(data=payload)
    return EXIT_OK


HANDLERS = {
    "whoami": cmd_whoami,
    "workspaces": cmd_workspaces,
    "credentials": cmd_credentials,
    "paths": cmd_paths,
    "list": cmd_list,
    "capabilities": cmd_capabilities,
    "audit": cmd_audit,
}


# ─────────────────────────── 写命令①：把凭据写进本机钥匙串 ───────────────────────────
CREDENTIALS_SET_ACTION = "把 Daniel 登录凭据写进本机系统钥匙串"


def _credentials_set_plan(ctx, client):
    """只读地算清"将要写什么"：解出来源与掩码邮箱、看现有钥匙串状态。

    **不联网、不登录、不写任何东西**（干跑与真执行共用这一份计划）。密码在这一步就被
    从参数里抹掉，因此计划里只有掩码邮箱。
    """
    _credential_input(ctx)
    st = credential_status()
    kc = st.get("keychain") or {}
    email_masked = ctx.args.account_email_masked
    return {
        "targetName": "本机系统钥匙串（service=%s，账号=%s）" % (kc.get("service"), email_masked),
        "impact": "把凭据写进**本机系统钥匙串**（service=%s，账号=%s）："
                  "同 service 下的同名条目会被更新，其余条目不动；"
                  "不改 Daniel 侧任何数据、不发任何网络请求、**不写任何明文凭据文件**。"
                  % (kc.get("service"), email_masked),
        "changes": {"keychain.set": {"service": kc.get("service"),
                                     "account": email_masked,
                                     "plaintextWrite": False}},
        "account_email_masked": email_masked,
        "credential_from_env": bool(ctx.get("from-env")),
        "keychain_available": bool(kc.get("available")),
        "before_source": st.get("source"),
    }


def _credentials_set_run(ctx, client, plan):
    """真写：只调既有仪器 `store-set` 的等价入口（`DanielCredentialStore.set`），再回读确认。"""
    inp = getattr(ctx, "credential_input", None) or {}
    email, password = inp.get("email"), inp.get("password")
    creds = _credentials_module()
    store = creds.DanielCredentialStore()

    before_status = store.status()
    before_plain = bool((before_status.get("plaintext_fallback") or {}).get("exists"))
    before_legacy = bool((before_status.get("legacy_plaintext_file") or {}).get("exists"))

    ctx.progress("正在把凭据写进本机系统钥匙串（不会回显密码）")
    # allow_plaintext_fallback=False：本命令**不提供**明文降级（红线）。钥匙串写失败就非零退出。
    ok, source, msg = store.set(email, password, allow_plaintext_fallback=False)
    # 纵深防御：上游消息里万一带上了凭据值（例如底层命令超时后把整条 argv 回显出来），
    # 密码一律抹掉、邮箱一律换成掩码再往外传 —— 结果只给形状，不给值。
    msg = _scrub(msg, password)
    if email:
        msg = msg.replace(str(email), _mask(email))

    if not ok or source != "keychain":
        raise CliError("凭据没有写进系统钥匙串：%s" % (msg or "钥匙串写入被拒绝"),
                       code=EXIT_INTERNAL, hint=KEYCHAIN_FAIL_HINT)

    after_status = store.status()
    kc = after_status.get("keychain") or {}
    after_plain = bool((after_status.get("plaintext_fallback") or {}).get("exists"))
    after_legacy = bool((after_status.get("legacy_plaintext_file") or {}).get("exists"))

    readback_ok = (after_status.get("source") == "keychain" and bool(kc.get("found"))
                   and kc.get("account_masked") == _mask(email))
    plaintext_untouched = (before_plain == after_plain and before_legacy == after_legacy)
    verified = bool(readback_ok and plaintext_untouched)
    reason = ""
    if not readback_ok:
        reason = ("回读到的凭据来源不是钥匙串（来源=%s，条目存在=%s，账号=%s），"
                  "请用 daniel account credentials 复核"
                  % (after_status.get("source"), kc.get("found"), kc.get("account_masked")))
    elif not plaintext_untouched:
        reason = "回读发现明文凭据文件的存在性发生了变化（本命令不应写任何明文文件），请人工核对"

    return {
        "mutation": {"route": "keychain.set", "service": kc.get("service"),
                     "account": _mask(email), "source": source,
                     "plaintextWrite": False, "note": "只写了系统钥匙串，没有写任何明文文件"},
        "readback": {
            "verified": verified,
            "reason": reason,
            "detail": {
                "说明": "写入后回读：凭据来源＝**钥匙串**（不是环境变量、不是明文文件）",
                "来源": after_status.get("source"),
                "钥匙串": {"service": kc.get("service"), "条目存在": bool(kc.get("found")),
                          "账号(掩码)": kc.get("account_masked"),
                          "钥匙串可用": bool(kc.get("available"))},
                "明文文件有没有被写": ("没有（写入前后一致）" if plaintext_untouched
                                      else "**有变化，请人工核对**"),
                "明文文件": {"降级文件": {"路径": (after_status.get("plaintext_fallback") or {}).get("path"),
                                        "写入前存在": before_plain, "写入后存在": after_plain},
                            "旧明文文件": {"路径": (after_status.get("legacy_plaintext_file") or {}).get("path"),
                                          "写入前存在": before_legacy,
                                          "写入后存在": after_legacy}},
                "下一步": "跑 `daniel account login --confirm` 登录并落地会话",
            },
            "before": {"source": before_status.get("source"),
                       "email_masked": before_status.get("email_masked")},
            "after": {"source": after_status.get("source"),
                      "email_masked": after_status.get("email_masked")},
        },
        "detail": {
            "说明": "凭据已写进本机系统钥匙串；密码没有出现在任何输出里，也没有写任何明文文件。",
            "下一步": "① `daniel account login --confirm` 登录；② 只读命令验证取数"
                      "（例如 `daniel account whoami`）",
        },
    }


# ─────────────────────────── 写命令②：登录并刷新会话 ───────────────────────────
LOGIN_ACTION = "登录并刷新本机会话（会写会话文件）"


def _login_plan(ctx, client):
    """只读地算清"将发生什么"：看凭据来源、看会话文件现状。**不登录、不写文件。**"""
    if ctx.get("browser"):
        return _browser_login_plan(ctx)          # 主路径：浏览器授权登录（TICKET-194）
    st = credential_status()
    if not st.get("exists"):
        raise CliError("本机还没有可用的 Daniel 凭据：登录无从谈起（本次没有动任何东西）",
                       code=EXIT_USAGE, hint=NO_CREDENTIAL_HINT)
    path = _session_path()
    exists = os.path.exists(path)
    force = bool(ctx.get("force"))
    return {
        "targetName": "本机会话文件（%s）" % path,
        "impact": "用%s登录 Daniel（账号 %s），并把新的会话写进 %s（目录 session，文件权限 600）；"
                  "不触发任何采集、不改任何业务数据；登录后回读账号名确认是真实账号。"
                  % (SOURCE_LABEL.get(st.get("source"), st.get("source") or "本机凭据"),
                     st.get("email_masked") or "（掩码未知）", path),
        "changes": {"auth.login": {"force": force}},
        "sessionFile": path,
        "sessionFileExists": exists,
        "credential_source": st.get("source"),
        "email_masked": st.get("email_masked"),
        "reusesExistingSession": (not force) and exists,
    }


def _credential_hint(trpc=None):
    """凭据类失败的"处理建议"：**可执行下一步** ＋（可回查的）服务端原文。

    为什么原文只出现在建议里、不进人话正文：用户先要看到"该做什么"（TICKET-179 的业务可用性
    抽检就是问"下一步该做什么"）；服务端原文是给排障回查用的，`--json` 的错误细节里也能取到。
    """
    dc = load_client()
    kind = getattr(trpc, "kind", None) or "credential"
    hint = dc.FAILURE_NEXT.get(kind) or dc.FAILURE_NEXT["credential"]
    if getattr(trpc, "server_message", None):
        hint += "（服务端原文：%s；通路 %s；HTTP %s）" % (
            trpc.server_message, getattr(trpc, "path", None) or "auth.login",
            getattr(trpc, "http_status", None))
    return hint


def _login_run(ctx, client, plan):
    """真登录 → 回读账号 → 校正会话文件权限 → 刷新账号盘点所需的最小上下文。

    `--browser`（主路径）：走**浏览器授权登录**那条 —— 打开登录页、回读会话、先校验后落盘；
    这条路上**不向用户索要账号密码**（TICKET-194 用户逐字要求）。
    """
    if ctx.get("browser"):
        return _browser_login_run(ctx, client, plan)
    force = bool(ctx.get("force"))
    before = _session_fingerprint()
    st = credential_status()
    ctx.progress("正在登录 Daniel（凭据取自%s；不回显任何凭据值）"
                 % SOURCE_LABEL.get(st.get("source"), st.get("source") or "本机凭据"))

    d = client                      # 触发懒客户端：没有有效会话时它自己会真登录一次
    dc = load_client()
    try:
        d.login(force=force)
    except dc.CredentialError as e:
        # 服务端明说"邮箱或密码不正确"（Daniel 用 HTTP 500 返回它）⇒ **用户错误**，退出码 2。
        # 不许把它报成"内部错误 1"，也不许把用户引向 --verbose（TICKET-179）。
        raise CliError(e.human, code=EXIT_USAGE, hint=_credential_hint(e.trpc)) from None
    except CliError as e:
        # `new_client()` 会把既有能力的 SystemExit 包装成 CliError（读命令那条路）：
        # 这里剥出原始异常，好把"处理建议"换成凭据类的可执行下一步。
        inner = getattr(e, "__context__", None)
        if isinstance(inner, dc.CredentialError):
            raise CliError(inner.human, code=EXIT_USAGE, hint=_credential_hint(inner.trpc)) from None
        raise
    except SystemExit as e:
        # 其它"用户可见的错误"（例如服务端 200 但**没给 app_session_id**）⇒ 仍是用户错误，
        # 但要把处理建议换成凭据类的那一条（CLI 兜底的 SystemExit 建议是给"对象不存在／多义"写的）。
        msg = e.code if isinstance(e.code, str) else "登录失败（原因未说明）"
        raise CliError(str(msg), code=EXIT_USAGE, hint=_credential_hint()) from None
    after = _session_fingerprint()
    mode, fixed = (None, False)
    if after.get("exists"):
        mode, fixed = _ensure_session_mode_600(after["path"])

    me = {}
    err = ""
    try:
        me = d.query("auth.me", {}) or {}
    except Exception as e:                                              # noqa: BLE001
        err = "%s: %s" % (type(e).__name__, str(e)[:160])
    email = me.get("email") or d.whoami()
    email = _scrub(email)

    # 凭据里的账号（掩码口径与凭据仪器一致）——写成邮箱形状时才用来对账
    cred_email = None
    if st.get("source") == "keychain":
        cred_email = (_credentials_module().keychain_find() or (None, None))[0]
    else:
        cred_email = os.environ.get("DANIEL_EMAIL")
    cred_match = None
    if email and cred_email and "@" in str(cred_email):
        cred_match = (_mask(cred_email) == _mask(email))

    reasons = []
    if not email:
        reasons.append("登录后读不到账号（whoami 没返回账号名）%s" % ("；原始错误：%s" % err if err else ""))
    if not after.get("exists"):
        reasons.append("会话文件没有落地：%s" % after.get("path"))
    if mode not in ("0o600",):
        reasons.append("会话文件权限不是 600（当前 %s）" % mode)
    if cred_match is False:
        reasons.append("回读到的账号（%s）与本机凭据里的账号（%s）不是同一个"
                       % (_mask(email), _mask(cred_email)))
    verified = not reasons

    if cred_match is False and email and after.get("exists"):
        # 回读到的账号与本机凭据不是同一个 ⇒ **凭据没有真正生效**（典型成因：本机已有一份
        # 属于另一个账号的会话，登录命令复用了它、根本没去用你写入的凭据）。
        # 这是**用户侧**的问题（凭据不对／不对号），不是产品坏了：报退出码 2 并给出下一步，
        # 而不是走进"写已提交但回读没通过 → 内部错误 1"（TICKET-179 要修的就是这条误导面）。
        # 该分支只在**复用既有会话**（未加 --force）时可能命中：真登录用的是凭据，不会对不上。
        raise CliError(
            "凭据没有生效：本机已有的会话属于另一个账号（%s），本次登录没有用你写入的凭据。"
            "若你的邮箱或密码不正确、或与这个账号不是同一个，请重写凭据后再试。" % _mask(email),
            code=EXIT_USAGE,
            hint="加 --force 用凭据重新登录：`daniel account login --confirm --force`；"
                 "若仍失败，用 `daniel account credentials set --email <你的邮箱> --confirm` "
                 "重写凭据，并用 `daniel account credentials` 核对邮箱拼写。")

    context = {"refreshed": False, "note": ""}
    if verified:
        try:
            permissions.write_cache(permissions.probe_live(client=d))
            context = {"refreshed": True,
                       "note": "已刷新账号盘点（能力矩阵）所需的账号快照缓存"}
        except Exception as e:                                          # noqa: BLE001
            context = {"refreshed": False, "note": "账号快照没刷新成功（不影响本次登录）：%s"
                                                   % str(e)[:120]}

    return {
        "mutation": {"route": "auth.login", "force": force,
                     "sessionFile": after.get("path"),
                     "sessionWritten": bool(after.get("exists")) and (
                         not before.get("exists") or before.get("sha12") != after.get("sha12")),
                     "sessionReused": (not force) and before.get("exists")
                                      and before.get("sha12") == after.get("sha12")},
        "readback": {
            "verified": verified,
            "reason": "；".join(reasons),
            "detail": {
                "说明": "登录后回读账号：拿到的是**真实账号**才算成功",
                "账号(掩码)": _mask(email),
                "系统角色": me.get("systemRole"),
                "账号状态": me.get("userStatus"),
                "当前工作区编号": me.get("activeWorkspaceId"),
                "凭据来源": st.get("source"),
                "凭据账号与回读账号一致": cred_match,
                "会话文件": {"路径": after.get("path"), "是否存在": bool(after.get("exists")),
                            "权限": mode, "权限已由本命令校正": fixed,
                            "写入前摘要(前12位)": before.get("sha12"),
                            "写入后摘要(前12位)": after.get("sha12")},
                "账号快照": context,
                "下一步": "跑一条只读取数确认链路可用，例如 `daniel account whoami` 或 "
                          "`daniel brands list --limit 5`",
            },
            "before": before,
            "after": after,
        },
        "detail": {
            "说明": "已登录并把会话落在数据落点的 session 目录；回读确认拿到的是真实账号。",
            "账号(掩码)": _mask(email),
        },
    }


# ────────────────── 写命令④：浏览器授权登录（**主路径** · TICKET-194） ──────────────────
# 用户 2026-10-16 逐字定的唯一正路：
#   「逻辑**并不是直接在 codex 里面直接输入账号密码**，而是需要**支持跳转到 Daniel 的登陆页面**，
#     在 Daniel 完成登陆后，**对应的用户信息被读取和完成授权**」
# 落地三条：① 不在宿主里索要账号密码；② 打开 Daniel 登录页（账号密码只在页面上输）；
#          ③ 回读会话 → **先校验后落盘** → 落在**既有**那条会话链上（$DANIEL_HOME/session/）。
BROWSER_LOGIN_ACTION = "浏览器授权登录：打开 Daniel 登录页 → 回读会话 → 校验后落地会话文件"

#: `/auth` 页面上要用户照做的**精确到点哪里**的步骤（该 cookie 带 HttpOnly ⇒ `document.cookie` 拿不到）
READBACK_STEPS = (
    "回读步骤（这一步不能省：平台没有把会话送回命令行的通道）：",
    "  ① 在打开的 Daniel 登录页上完成登录（账号密码**只在 Daniel 页面上输入**，"
    "不要给这里的任何命令）；",
    "  ② 登录成功后，在**同一个浏览器**里打开开发者工具：菜单「更多工具 → 开发者工具」"
    "（macOS ⌥⌘I，Windows/Linux Ctrl+Shift+I）；",
    "  ③ 切到 **Application（应用）** 面板 → 左栏 **Storage → Cookies → https://daniel-agent.com**；",
    "  ④ 在 Cookie 列表里找到行名为 **app_session_id** 的那一条，双击它的 **Value** 单元格"
    "全选 → 复制；",
    "     （⚠️ 这条 cookie 带 HttpOnly：在 Console 里敲 `document.cookie` **取不到**它，"
    "必须按上面一步步点；）",
    "  ⑤ 回到这里粘贴（粘完按回车）——CLI **先校验、通过后才落盘**。",
    "只有会话值会被读进这一次请求；**任何输出里都不会回显这个值**。",
)

#: 没粘东西 / 格式不对 / 被服务端拒 / 服务端不可达 —— 四种情况给**各自不同的人话**（可区分）
READBACK_EMPTY = ("没有读到会话值（粘进来的内容是空的）。请回到浏览器的 Application → Cookies，"
                  "复制 app_session_id 的 Value 再试；也可以把值用管道喂进来："
                  "`daniel account login --browser --confirm --session-cookie-stdin < 值文件`")
READBACK_SHAPE = ("粘贴的内容**不是一条会话 cookie**（格式不对）：它应当是一段三段点分的票据"
                  "（形如 `xxx.yyy.zzz`），或 `app_session_id=xxx.yyy.zzz` 这样的整串。"
                  "最可能的原因：复制到了别的 cookie，或只复制了一部分。"
                  "请重新执行上面第 ④ 步，确认复制的是 **app_session_id 的 Value** 整格内容。")
READBACK_REJECTED = ("这个会话**服务端不认**（很可能已经过期，或你已在那台浏览器上登出过）。"
                     "请重新走一遍：打开登录页 → 登录 → 重新复制 app_session_id → 再粘一次。")
READBACK_UNREACHABLE = ("会话格式没问题，但**服务端不可达**，没能完成校验 —— 过一会儿重试这条命令"
                        "即可（**不要**反复重新登录）。")


def _login_page_url():
    return load_client().base_url().rstrip("/") + authgate.LOGIN_PAGE_PATH


#: 🔴 **环境级硬开关**：设了它，**任何路径都不得调起系统浏览器**（只打印地址）。
#: 为什么必须是环境级而不是只靠 `--no-open`：开浏览器是**真人可见的副作用**（用户桌面上会弹窗口）。
#: 凡自动化（自检／验收／CI／Agent 调用／管道）都不该产生这种副作用 —— 纪律靠不住，所以做成
#: "环境说不行就是不行"，并且**非交互终端（无 TTY）本身就是默认不开**（见 `no_open_decision`）。
NO_OPEN_ENV = "DANIEL_NO_OPEN"


def no_open_decision(explicit=False):
    """要不要**禁止**调起系统浏览器？→ `(禁止?, 理由)`（**唯一判据**，两条路共用）。

    优先级（**从严到宽**，任何一条命中即禁止）：
      ① 环境变量 `DANIEL_NO_OPEN` 为真（1／true／yes／on）—— **自动化路径的保险丝**；
      ② 命令行显式 `--no-open`；
      ③ **当前不是交互式终端**（管道／重定向／子进程／CI）—— 没人能看见那个窗口，开了只会
         在用户桌面上乱弹 ⇒ 默认不开，只打印登录页地址。
    只有"人在真终端里、且没关掉它"才允许调起浏览器。
    """
    v = str(os.environ.get(NO_OPEN_ENV) or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True, ("环境变量 %s 已设 ⇒ **任何路径都不调起系统浏览器**（只打印登录页地址）"
                      % NO_OPEN_ENV)
    if explicit:
        return True, "命令行给了 `--no-open`：只打印登录页地址，不调起系统浏览器"
    if not sys.stdin.isatty():
        return True, ("当前不是交互式终端（自动化／CI／管道）⇒ **默认不调起系统浏览器**，"
                      "只打印登录页地址；人在真终端里跑时不带 --no-open 才会自动打开")
    return False, None


def _open_browser(url):
    """尽力用系统默认浏览器打开登录页；打不开不算失败（URL 已经打印出来了）。

    🔴 **先过 `no_open_decision()`**：这一步不是"礼貌检查"，而是"自动化不许产生真人可见副作用"
    的落地点 —— 所以判据放在**函数自身**里，任何一个调用方漏传 `--no-open` 也开不了。
    """
    import subprocess
    if no_open_decision()[0]:
        return False, None
    for cmd in (["open", url], ["xdg-open", url]):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if p.returncode == 0:
                return True, cmd[0]
        except (OSError, subprocess.SubprocessError):
            continue
    return False, None


def _parse_session_value(raw):
    """把用户粘回来的东西解析成 cookie 串。返回 `(cookie 或 None, 形态码)`。

    **绝不回显输入值**：只回形态码（`empty`／`shape`／`ok`），异常文本里也只有长度。
    """
    import base64
    s = str(raw or "").strip().strip('"').strip("'").strip()
    if not s:
        return None, "empty"
    for part in s.split(";"):                    # 允许整串 cookie（`a=b; app_session_id=…`）
        p = part.strip()
        if p.startswith("app_session_id="):
            s = p[len("app_session_id="):].strip()
            break
    s = s.strip().strip('"').strip("'")
    if not s:
        return None, "empty"
    parts = s.split(".")
    if len(parts) != 3 or not all(parts):
        return None, "shape"
    try:                                          # 头段必须是能解出 `alg` 的 JSON（JWS 形态）
        pad = "=" * (-len(parts[0]) % 4)
        head = json.loads(base64.urlsafe_b64decode(parts[0] + pad).decode("utf-8", "replace"))
    except Exception:                                                 # noqa: BLE001
        return None, "shape"
    if not isinstance(head, dict) or not head.get("alg"):
        return None, "shape"
    return "app_session_id=" + s, "ok"


def _read_session_value(ctx):
    """取回读值：优先 `--session-cookie-stdin`；否则交互式粘贴（**非 TTY 不阻塞等待**）。"""
    import sys as _sys
    if ctx.get("session-cookie-stdin"):
        return _sys.stdin.read()
    if not _sys.stdin.isatty():
        raise CliError(
            "当前不是交互式终端，没法等你粘贴会话值 —— 请改用管道把值喂进来："
            "`daniel account login --browser --confirm --session-cookie-stdin < 值文件`"
            "（或 `… | daniel account login --browser --confirm --session-cookie-stdin`）",
            code=EXIT_USAGE,
            hint="只想先看步骤与登录页地址：`daniel account login --browser`"
                 "（不带 --confirm：只打印计划，不写任何文件）")
    print("请粘贴 app_session_id 的 Value（粘完按回车；这个值不会出现在结果里）：",
          file=_sys.stderr)
    return input()


def _browser_login_plan(ctx):
    """浏览器授权路的**只读**计划（不联网、不登录、不写任何东西）。"""
    path = _session_path()
    return {
        "targetName": "本机会话文件（%s）" % path,
        "impact": "打开 Daniel 登录页（%s）→ 你在**页面上**完成登录 → 你把会话粘回来 → "
                  "CLI **先校验（一次只读校验）后落盘**，会话写进 %s（权限 600）。"
                  "全程**不向你要账号密码**、不触发任何采集、不改任何业务数据。"
                  % (_login_page_url(), path),
        "changes": {"session.write": {"path": path, "mode": "0o600",
                                      "verifyBeforeWrite": True}},
        "authorizationPath": "browser",
        "loginPage": _login_page_url(),
        "sessionFile": path,
        "sessionFileExists": os.path.exists(path),
        "steps": list(READBACK_STEPS),
        "note": "主路径：账号密码**只在 Daniel 页面上**输入。无头／CI 才用环境变量那一套"
                "（`daniel account login --confirm`）—— 那不是给人用的主路径。",
    }


def _browser_login_run(ctx, client, plan):
    """真跑：打开登录页 → 回读 → **先校验后落盘**（落盘走既有那条会话链，不另造第二套）。

    `client` 是写链的懒客户端代理，**本路径刻意不碰它** —— 浏览器授权路不该因为
    "顺手解析一下"就触发一次密码登录。
    """
    import sys as _sys
    path, url = plan["sessionFile"], plan["loginPage"]
    before = _session_fingerprint()

    ctx.progress("请在浏览器里完成登录：%s" % url)
    for line in READBACK_STEPS:
        ctx.emitter.note(line)
    blocked, why = no_open_decision(bool(ctx.get("no-open")))
    if blocked:
        ctx.note("没有自动打开浏览器：%s。请手动访问上面的地址。" % why)
    else:
        opened, how = _open_browser(url)
        if opened:
            print("已用 `%s` 打开登录页。" % how, file=_sys.stderr)
        else:
            ctx.note("没能自动打开浏览器，请手动访问上面的地址。")

    raw = _read_session_value(ctx)
    cookie, shape = _parse_session_value(raw)
    if shape == "empty":
        raise CliError(READBACK_EMPTY, code=1, hint="重新执行上面第 ④ 步后重跑本命令")
    if shape == "shape":
        raise CliError(READBACK_SHAPE, code=1, hint="重新执行上面第 ④ 步后重跑本命令")

    ctx.progress("正在校验这个会话（一次只读校验，不改任何数据）")
    state, detail = authgate.verify_session(cookie)
    if state == authgate.VERIFY_REJECTED:
        raise CliError(READBACK_REJECTED, code=1,
                       hint="服务端原文：%s" % (detail.get("服务端原文") or "（未给原文）"))
    if state == authgate.VERIFY_UNREACHABLE:
        raise CliError(READBACK_UNREACHABLE, code=EXIT_USAGE,
                       hint="端点：%s（可先跑 `daniel auth status` 看三态）" % detail.get("endpoint"))

    # 落盘：**既有那条链**（`Daniel._save_cookie`），不另造第二套会话文件
    d = load_client().Daniel(verbose=ctx.verbose)
    d._save_cookie(cookie)                                            # noqa: SLF001
    mode, fixed = _ensure_session_mode_600(path) if os.path.exists(path) else (None, False)
    after = _session_fingerprint()
    email = detail.get("账号(掩码)")

    reasons = []
    if not after.get("exists"):
        reasons.append("会话文件没有落地：%s" % path)
    if mode != "0o600":
        reasons.append("会话文件权限不是 600（当前 %s）" % mode)
    if _session_inside_home(path) is False:
        reasons.append("会话文件不在当前数据落点之内：%s" % path)
    verified = not reasons
    return {
        "mutation": {"route": "browser.readback", "authorizationPath": "browser",
                     "sessionFile": path,
                     "sessionWritten": bool(after.get("exists")) and (
                         not before.get("exists") or before.get("sha12") != after.get("sha12")),
                     "sessionValueEchoed": False,
                     "note": "会话经一次只读校验通过后才落盘；**全程没有向用户索要账号密码**"},
        "readback": {
            "verified": verified,
            "reason": "；".join(reasons),
            "detail": {
                "说明": "回读到的会话**先经服务端校验通过**才落盘（拿不到真实账号即判失败）",
                "账号(掩码)": email,
                "系统角色": detail.get("系统角色"),
                "账号状态": detail.get("账号状态"),
                "校验": {"结论": state, "HTTP": detail.get("http")},
                "会话文件": {"路径": path, "是否存在": bool(after.get("exists")),
                            "权限": mode, "权限已由本命令校正": fixed,
                            "写入前摘要(前12位)": before.get("sha12"),
                            "写入后摘要(前12位)": after.get("sha12")},
                "下一步": "跑 `daniel auth status` 确认是「通过」，然后照常用业务命令",
            },
            "before": before,
            "after": after,
        },
        "detail": {
            "说明": "浏览器授权登录完成：会话已校验并落在数据落点的 session 目录（权限 600）。",
            "账号(掩码)": email,
            "与「一键跳转授权」的差距": "平台登录页不接受 redirect／callback／code，也没有 "
                                       "device-code／poll 端点 ⇒ 目前必须由人把会话从浏览器粘回来一步。",
        },
    }


def _session_inside_home(path):
    """会话文件是否落在生效的 `DANIEL_HOME` 之内（自检用；判据真源是 `daniel_paths`）。"""
    try:
        dpaths = load_capability("daniel_paths")
        home = os.path.abspath(dpaths.home())
        p = os.path.abspath(path)
        return p == home or p.startswith(home + os.sep)
    except Exception:                                                 # noqa: BLE001
        return None


# ─────────────────────────── 写命令③：切换当前账号（数据按账号分区） ───────────────────────────
SWITCH_ACTION = "切换当前账号（后续命令的会话／缓存／产出／调度改落该账号的分区）"

#: 目标账号在本机**没有**任何可复用凭据时的下一步（"切回免重输"是本功能的硬要求）
SWITCH_NO_CRED_HINT = (
    "先把这个账号的凭据存进本机系统钥匙串："
    "`daniel account credentials set --email <这个账号的邮箱> --confirm`"
    "（或 `--from-env`）；存完再跑 `daniel account switch <邮箱> --confirm`。"
    "也可以把 DANIEL_EMAIL／DANIEL_PASSWORD 设成这个账号后再切。"
)


def _switch_target(ctx):
    """本次要切到哪个账号（位置参数 `<账号>`；也支持 `--to <账号>`）。

    `--clear` 是"取消当前账号"（回到未指定账号的**根落点**，也就是切账号之前那个区域）——
    有了它，切账号这件事**完全可逆**：既有数据一直在根落点，不会被搬走。
    """
    if ctx.get("clear"):
        return None
    target = ctx.get("账号") or ctx.get("to")
    if not target:
        raise CliError("没有指定要切到哪个账号",
                       hint="用法：`daniel account switch <邮箱> --confirm`；"
                            "取消当前账号（回到根落点）用 `daniel account switch --clear --confirm`；"
                            "看当前账号与已存账号用 `daniel account list`")
    return str(target).strip()


def _switch_has_credentials(target):
    """目标账号在本机有没有**可复用**的凭据：钥匙串条目（只判存在）或同名环境变量。"""
    if accounts_mod.keychain_has(target):
        return "keychain"
    env_email = (os.environ.get("DANIEL_EMAIL") or "").strip()
    if env_email and env_email.lower() == target.lower() and os.environ.get("DANIEL_PASSWORD"):
        return "env"
    return None


def _switch_plan(ctx, client):
    """**只读**算清"将发生什么"：目标账号、它的分区、切前切后的落点、以及不做哪些事。

    不联网、不登录、不写任何东西（干跑与真执行共用这一份计划）。
    """
    target = _switch_target(ctx)
    before = accounts_mod.partition_facts()
    prev = before["当前账号(掩码)"]
    if target is None:                                  # --clear：取消当前账号
        return {
            "targetName": "（取消当前账号）",
            "impact": ("取消当前账号：之后每条命令的会话／缓存／产出／调度回到**根落点 %s**"
                       "（也就是切账号之前那个区域）。不删任何目录、不删任何文件、不碰凭据。"
                       % before["数据落点根"]),
            "changes": {"account.switch": {"账号(掩码)": None,
                                           "切换前落点": before["生效落点"],
                                           "切换后落点": before["数据落点根"],
                                           "只写指针文件": True,
                                           "删除数据": False,
                                           "迁移既有数据": False}},
            "account_email_masked": None,
            "credential_source": None,
            "partition": before["数据落点根"],
            "previous_partition": before["生效落点"],
            "clear": True,
        }
    src = _switch_has_credentials(target)
    if not src:
        raise CliError("目标账号「%s」在本机没有可复用的凭据：切过去之后每条命令都要重输密码，"
                       "这不是本功能要的结果" % _mask(target),
                       code=EXIT_USAGE, hint=SWITCH_NO_CRED_HINT)
    after = accounts_mod.partition_facts(target)
    return {
        "targetName": _mask(target),
        "impact": ("把本机当前账号从 %s 切到 %s：之后每条命令的会话／缓存／产出（含 output／"
                   "sched）都落在 %s；凭据读取改钉到该账号在钥匙串里的那条（**切回不用重输密码**）。"
                   "不改任何既有账号的数据、不写任何凭据、不联网、不动 Daniel 侧任何数据。"
                   % (prev or "（未指定）", _mask(target), after["生效落点"])),
        "changes": {"account.switch": {"账号(掩码)": _mask(target),
                                       "数据落点根": after["数据落点根"],
                                       "切换后落点": after["生效落点"],
                                       "切换前落点": before["生效落点"],
                                       "凭据来源": src,
                                       "只写指针文件": True,
                                       "迁移既有数据": False}},
        "account_email_masked": _mask(target),
        "credential_source": src,
        "partition": after["生效落点"],
        "previous_partition": before["生效落点"],
    }


def _switch_run(ctx, client, plan):
    """真切换：登记（只加自己那一行）→ 建分区目录 → 写指针 → **回读对账**。

    回读对账（CLS-87）四件事，逐件印实际值：
      ① 当前账号指针 == 目标账号；
      ② 目标分区目录存在且五个子目录就绪（会话／缓存／产出／日志／调度）；
      ③ **上一个账号的分区文件数没变**（证明切换不删改别人的数据）；
      ④ 目标账号的钥匙串条目**仍在**（证明切换没碰凭据）。
    """
    target = _switch_target(ctx)
    src = _switch_has_credentials(target) if target else None
    prev = accounts_mod.active_account()
    before_prev = accounts_mod.partition_summary(prev) if prev else None
    before_kc = accounts_mod.keychain_has(target) if target else False
    before_audit_files = _switch_partition_file_count()

    ctx.progress("正在切换当前账号（只写本机指针文件；不写凭据、不动既有数据）"
                 if target else "正在取消当前账号（只写本机指针文件；不删任何数据）")
    result = accounts_mod.switch(target) if target else accounts_mod.clear_active()

    after_active = accounts_mod.active_account()
    after_part = accounts_mod.partition_summary(after_active)
    after_prev = accounts_mod.partition_summary(prev) if prev else None
    after_kc = accounts_mod.keychain_has(target) if target else False

    reasons = []
    ok_active = (after_active is None) if not target else (
        bool(after_active) and after_active.lower() == target.lower())
    if not ok_active:
        reasons.append("回读到的当前账号是 %s，不是目标 %s"
                       % (_mask(after_active), _mask(target) if target else "（未指定）"))
    ok_dirs = all(os.path.isdir(os.path.join(after_part["落点"], s))
                  for s in ("session", "cache", "output", "logs", "sched"))
    if target and not ok_dirs:
        reasons.append("目标分区缺少子目录（会话／缓存／产出／日志／调度）：%s" % after_part["落点"])
    untouched = (before_prev is None) or (after_prev["文件数"] == before_prev["文件数"])
    if not untouched:
        reasons.append("上一个账号的分区文件数变了（%s → %s）：切换不应删改任何既有数据"
                       % (before_prev["文件数"], after_prev["文件数"]))
    kc_kept = (not before_kc) or after_kc
    if not kc_kept:
        reasons.append("目标账号的钥匙串条目在切换后找不到了：切换不应碰凭据")
    verified = not reasons

    return {
        "mutation": {"route": "account.switch",
                     "账号(掩码)": _mask(target) if target else None,
                     "取消当前账号": bool(not target),
                     "凭据来源": src,
                     "写入内容": {"指针文件": accounts_mod.state_path(),
                                  "只新增本账号一行": bool(target),
                                  "写凭据": False, "删改既有数据": False, "联网": False},
                     "新建目录": result.get("created") or [],
                     "审计目录文件数（切换前）": before_audit_files},
        "readback": {
            "verified": verified,
            "reason": "；".join(reasons),
            "detail": {
                "说明": "切换后回读四件事：当前账号指针、目标分区就绪、上一个账号的数据没被动、"
                        "凭据条目仍在",
                "①当前账号指针": {"回读值(掩码)": _mask(after_active),
                                  "期望(掩码)": _mask(target) if target else None,
                                  "成立": ok_active},
                "②目标分区就绪": {"分区落点": after_part["落点"], "存在": after_part["存在"],
                                  "子目录文件数": after_part["子目录"],
                                  "五个子目录齐备": ok_dirs},
                "③上一个账号的数据没被动": {
                    "上一个账号(掩码)": _mask(prev) if prev else None,
                    "分区": (before_prev or {}).get("落点"),
                    "文件数（切换前）": (before_prev or {}).get("文件数"),
                    "文件数（切换后）": (after_prev or {}).get("文件数"),
                    "成立": untouched},
                "④凭据没被碰": {"目标账号钥匙串条目（切换前）": before_kc,
                                "目标账号钥匙串条目（切换后）": after_kc,
                                "核法": "只要 `security find-generic-password` 的退出码（不带 -w）",
                                "成立": kc_kept},
                "下一步": ("直接跑 `daniel account whoami` 确认取到的是这个账号；"
                          "用 `daniel account paths` 看当前分区" if target else
                          "跑 `daniel account paths` 确认已回到根落点；"
                          "根的既有数据一直在那里（本次没有搬家、没有删除）"),
            },
            "before": {"当前账号(掩码)": _mask(prev) if prev else None,
                       "生效落点": (result.get("before") or {}).get("生效落点")},
            "after": {"当前账号(掩码)": _mask(after_active),
                      "生效落点": (result.get("after") or {}).get("生效落点")},
        },
        "detail": {
            "说明": ("已切换当前账号；会话／缓存／产出／调度从下一条命令起落该账号的分区。"
                     if target else
                     "已取消当前账号；会话／缓存／产出／调度回到根落点（既有数据一直在那里）。"),
            "账号(掩码)": _mask(target) if target else None,
            "切换后落点": after_part["落点"],
            "下一步": ("① `daniel account whoami` 确认账号；② `daniel account paths` 看分区；"
                      "③ 切回别的账号：`daniel account switch <那个邮箱> --confirm`；"
                      "回到根落点：`daniel account switch --clear --confirm`" if target else
                      "① `daniel account paths` 看落点；② 再切账号："
                      "`daniel account switch <邮箱> --confirm`"),
        },
    }


def _switch_partition_file_count():
    """当前账号分区里 `logs/` 的文件数（切换前后对账用；没账号时看根）。"""
    try:
        return accounts_mod.partition_summary(accounts_mod.active_account())["文件数"]
    except OSError:
        return None


# ─────────────────────────── 模块自带自检（A2 的可回归验收） ───────────────────────────
#: 假钥匙串（自检用）：只实现 `find-generic-password`（带／不带 `-a`、带／不带 `-w`）
#: 与 `-h`。**它只活在临时目录里**，不进仓库、不碰真钥匙串 —— 目的是让"凭据按账号分条"
#: 与"切回免重输"这两条**不依赖真机钥匙串**也能被机器验证。
_FAKE_SECURITY = '''#!/usr/bin/env python3
import json, os, sys
STORE = os.environ["FAKE_KEYCHAIN_STORE"]
a = sys.argv[1:]
if not a or a[0] == "-h":
    print("fake security"); sys.exit(0)
def load():
    try:
        with open(STORE) as f:
            return json.load(f)
    except Exception:
        return []
cmd = a[0]
if cmd == "find-generic-password":
    svc = acct = None; want = False; i = 1
    while i < len(a):
        if a[i] == "-s": svc = a[i + 1]; i += 2
        elif a[i] == "-a": acct = a[i + 1]; i += 2
        elif a[i] == "-w": want = True; i += 1
        else: i += 1
    hits = [r for r in load() if r.get("service") == svc
            and (acct is None or r.get("account") == acct)]
    if not hits:
        sys.exit(44)
    if want and acct is not None:
        print(hits[0]["password"]); sys.exit(0)
    print('    "acct"<blob>="%s"' % hits[0]["account"]); sys.exit(0)
sys.exit(1)
'''


class _FakeQuotaClient:
    """离线假客户端：只实现 `query(route, inp)`，**不发任何请求**。

    用途：把"按工作区读配额"的**降级阶梯**验到位（哪一级给不给上限、下一级是什么、
    三级全挂时怎么如实记「未知」）—— 这些判据不能靠"线上正好命中哪一级"来碰运气，
    必须能在**离线、无网络**的情况下被机器反复验证。
    """

    def __init__(self, responses):
        self.responses = dict(responses or {})
        self.calls = []

    def query(self, route, inp=None, retries=3):
        self.calls.append(route)
        val = self.responses.get(route)
        if isinstance(val, BaseException):
            raise val
        if val is None:
            raise RuntimeError("%s 在假客户端里没有配置（模拟「该通路不可用」）" % route)
        return val


def _quota_selftest_items(add, run, root):
    """TICKET-203 的离线判据：**正控 ＋ 反控**，全部离线、不发任何请求、不写任何远端数据。

    覆盖三件事：
      ① 读数口径（`quota_cell`）：上限／已用／余量／已满，含"未知"与"不限"两种非数字情形；
      ② 降级阶梯（`workspace_quota`／`quota_map_for`）：三级通路各自给出什么、全挂时写什么；
      ③ `--workspace` 的重定向（`auth_scoped_to_workspace`）：配额轴跟着目标工作区走，
         **且不得就地改账号快照、不得拿当前工作区的上限顶替目标工作区**。
    """
    # ── ① 读数口径：正控 ──
    c1 = quota_cell(4, 2, "src.limit", "src.used")
    add("配额正控：上限 4／已用 2 ⇒ 余量 2、未满（上限与已用各记来源）",
        c1["上限"] == 4 and c1["已用"] == 2 and c1["余量"] == 2 and c1["是否已满"] is False
        and c1["上限是否已知"] is True and c1["上限来源"] == "src.limit"
        and c1["已用来源"] == "src.used",
        "上限=%s 已用=%s 余量=%s 已满=%s" % (c1["上限"], c1["已用"], c1["余量"], c1["是否已满"]))
    c2 = quota_cell(2, 2)
    add("配额正控：上限 2／已用 2 ⇒ 判「已满」、余量 0（写前检查必须能拦下这一档）",
        c2["是否已满"] is True and c2["余量"] == 0,
        "已满=%s 余量=%s" % (c2["是否已满"], c2["余量"]))
    c3 = quota_cell(1, 5)
    add("配额正控：已用超过上限（1／5）⇒ 仍判「已满」、余量不为负（不出现 -4）",
        c3["是否已满"] is True and c3["余量"] == 0, "余量=%s" % c3["余量"])
    c4 = quota_cell(-1, 14)
    add("配额正控：上限 -1（平台口径的不限）⇒ 写「不限」（既不是未知、也不是 0）",
        c4["上限"] == QUOTA_UNLIMITED and c4["余量"] == QUOTA_UNLIMITED
        and c4["是否已满"] is False,
        "上限=%s 余量=%s" % (c4["上限"], c4["余量"]))

    # ── ① 读数口径：反控（本票最硬的两条红线）──
    c5 = quota_cell(None, 7)
    add("配额反控：平台没给上限 ⇒ 上限必须写「未知」，**不得用已用数冒充、不得填 0**",
        c5["上限"] == QUOTA_UNKNOWN and c5["上限"] != 7 and c5["上限"] != 0
        and c5["上限是否已知"] is False and c5["已用"] == 7 and c5["余量"] == QUOTA_UNKNOWN
        and c5["是否已满"] is None,
        "上限=%r 已用=%r 余量=%r" % (c5["上限"], c5["已用"], c5["余量"]))
    c6 = quota_cell(4, None)
    add("配额反控：已用数取不到 ⇒ 已用与余量都写「未知」，**不得当成 0 也不得当成未满**",
        c6["已用"] == QUOTA_UNKNOWN and c6["余量"] == QUOTA_UNKNOWN
        and c6["是否已满"] is None and c6["上限"] == 4,
        "已用=%r 余量=%r 已满=%r" % (c6["已用"], c6["余量"], c6["是否已满"]))
    c7 = quota_cell("不是数字", "也不是")
    add("配额反控：上限／已用是垃圾值 ⇒ 一律「未知」（不抛异常、不猜成 0）",
        c7["上限"] == QUOTA_UNKNOWN and c7["已用"] == QUOTA_UNKNOWN
        and c7["原始上限"] is None and c7["原始已用"] is None,
        "上限=%r 已用=%r" % (c7["上限"], c7["已用"]))

    # ── ② 降级阶梯：第①级（管理面清单，上限＋已用都有）──
    admin_row = {"id": 90002, "name": "jack", "planTier": "starter", "status": "active",
                 "maxBrands": 4, "maxSearchesPerMonth": -1, "maxEmailsPerMonth": -1,
                 "memberCount": 1, "brandCount": 2, "enabledFeatures": [],
                 "currentUsage": {"searchesUsed": 66, "searchesLimit": -1,
                                  "emailsSent": 0, "emailsLimit": -1}}
    fake_a = _FakeQuotaClient({QUOTA_ROUTE_ADMIN: [admin_row, {"id": 60003, "name": "AW",
                                                              "planTier": "enterprise",
                                                              "maxBrands": -1,
                                                              "brandCount": 14}]})
    blk, how = workspace_quota(fake_a, 90002)
    add("阶梯①正控：管理面清单命中 ⇒ 上限 4／已用 2，且**只用了一次请求**（不逐工作区打）",
        blk["品牌配额"]["上限"] == 4 and blk["品牌配额"]["已用"] == 2
        and fake_a.calls == [QUOTA_ROUTE_ADMIN],
        "上限=%s 已用=%s ｜ 实际请求通路=%s" % (blk["品牌配额"]["上限"],
                                              blk["品牌配额"]["已用"], fake_a.calls))
    add("阶梯①正控：计划与工作区名如实带出，检索／邮件配额也各自记了来源",
        blk["计划"] == "starter" and blk["工作区名称"] == "jack"
        and blk["检索配额"]["上限"] == QUOTA_UNLIMITED and blk["检索配额"]["已用"] == 66
        and "currentUsage.searchesUsed" in blk["检索配额"]["已用来源"],
        "%s ｜ 检索上限=%s 已用=%s" % (how, blk["检索配额"]["上限"], blk["检索配额"]["已用"]))
    blk2, _how2 = workspace_quota(fake_a, 60003)
    add("阶梯①正控：另一个不同计划的工作区（enterprise／上限 -1）读到「不限」＋已用 14",
        blk2["品牌配额"]["上限"] == QUOTA_UNLIMITED and blk2["品牌配额"]["已用"] == 14
        and blk2["计划"] == "enterprise",
        "计划=%s 上限=%s 已用=%s" % (blk2["计划"], blk2["品牌配额"]["上限"],
                                    blk2["品牌配额"]["已用"]))

    # ── ② 降级阶梯：第②级（工作区清单只有已用，**没有上限**）──
    fake_b = _FakeQuotaClient({
        QUOTA_ROUTE_ADMIN: RuntimeError("HTTP 403：管理面清单不可用（模拟非管理角色）"),
        QUOTA_ROUTE_PUBLIC: [{"id": 90002, "name": "jack", "planTier": "starter",
                              "status": "active", "memberCount": 1, "brandCount": 2,
                              "enabledFeatures": []}]})
    blk3, how3 = workspace_quota(fake_b, 90002)
    add("阶梯②正控：管理面不可用 ⇒ 退到工作区清单，**上限如实写「未知」、已用取 brandCount**",
        blk3["品牌配额"]["上限"] == QUOTA_UNKNOWN and blk3["品牌配额"]["已用"] == 2
        and blk3["品牌配额"]["上限是否已知"] is False,
        "上限=%r 已用=%s ｜ %s" % (blk3["品牌配额"]["上限"], blk3["品牌配额"]["已用"], how3))
    add("阶梯②反控：这一级的**上限没有被已用数或 0 顶替**（两者都不等于 2／0）",
        blk3["品牌配额"]["上限"] != blk3["品牌配额"]["已用"] and blk3["品牌配额"]["上限"] != 0,
        "上限=%r（已用=%s，上限原始值=%r）" % (blk3["品牌配额"]["上限"],
                                            blk3["品牌配额"]["已用"],
                                            blk3["品牌配额"]["原始上限"]))

    # ── ② 降级阶梯：第③级（逐工作区用 brands.list 复算已用）──
    fake_c = _FakeQuotaClient({
        QUOTA_ROUTE_ADMIN: RuntimeError("HTTP 500"),
        QUOTA_ROUTE_PUBLIC: RuntimeError("HTTP 500"),
        QUOTA_ROUTE_BRANDS: [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}]})
    blk4, how4 = workspace_quota(fake_c, 90002, visible=[{"id": 90002, "name": "jack",
                                                          "planTier": "starter"}])
    add("阶梯③正控：前两级都不可用 ⇒ 用 `brands.list {workspaceId}` **复算已用=条数(5)**，"
        "上限仍写「未知」",
        blk4["品牌配额"]["已用"] == 5 and blk4["品牌配额"]["上限"] == QUOTA_UNKNOWN
        and blk4["工作区名称"] == "jack",
        "已用=%s（5 条品牌 ⇒ 复算算式 len(rows)）｜上限=%r" % (blk4["品牌配额"]["已用"],
                                                             blk4["品牌配额"]["上限"]))
    add("阶梯③正控：复算那一级确实问的是**目标工作区**（入参带上了 workspaceId，不是当前工作区）",
        fake_c.calls[-1] == QUOTA_ROUTE_BRANDS, "实际请求通路顺序=%s" % fake_c.calls)

    # ── ② 降级阶梯：三级全挂（最差也要如实说"未知"，不许崩、不许填数）──
    fake_d = _FakeQuotaClient({QUOTA_ROUTE_ADMIN: RuntimeError("HTTP 403"),
                               QUOTA_ROUTE_PUBLIC: RuntimeError("HTTP 404"),
                               QUOTA_ROUTE_BRANDS: RuntimeError("HTTP 404")})
    blk5, how5 = workspace_quota(fake_d, 90002)
    add("阶梯反控：三级通路全挂 ⇒ 上限与已用都写「未知」，且取数说明里列出三级各为什么失败",
        blk5["品牌配额"]["上限"] == QUOTA_UNKNOWN and blk5["品牌配额"]["已用"] == QUOTA_UNKNOWN
        and all(r in how5 for r in (QUOTA_ROUTE_ADMIN, QUOTA_ROUTE_PUBLIC, QUOTA_ROUTE_BRANDS)),
        how5)

    # ── ② `--with-quota` 的批量通路：失败时**不逐工作区打一百多次请求** ──
    fake_e = _FakeQuotaClient({QUOTA_ROUTE_ADMIN: RuntimeError("HTTP 403"),
                               QUOTA_ROUTE_PUBLIC: RuntimeError("HTTP 403")})
    qmap, how_e, missing = quota_map_for(fake_e, visible=[{"id": 1}, {"id": 2}, {"id": 3}])
    add("批量反控：前两级都不可用 ⇒ 只试 2 次就收手、所有工作区记「未知」"
        "（**不逐工作区打 112 次请求**）",
        qmap == {} and len(fake_e.calls) == 2 and len(missing) == 3,
        "实际请求次数=%d ｜ %s" % (len(fake_e.calls), how_e))
    fake_f = _FakeQuotaClient({QUOTA_ROUTE_ADMIN: [admin_row]})
    rows_for_summary = [{"id": 90002, "配额": quota_map_for(fake_f, visible=[])[0][90002]},
                        {"id": 1, "配额": quota_block_from_used_only(3, 1)}]
    summ = quota_summary(rows_for_summary)
    add("批量正控：小结把「有余量／已满／不限／上限未知」分开数（未知与 '有位置' 不混）",
        summ["有余量"] == 1 and summ["上限未知"] == 1 and summ["已满"] == 0
        and "未知不等于有位置" in summ["一句话"],
        summ["一句话"])

    # ── ③ `--workspace` 的重定向：不得就地改账号快照、不得拿当前工作区上限顶替 ──
    auth_now = {"systemRole": "super_admin", "userStatus": "active", "activeWorkspaceId": 90002,
                "enabledFeatures": [], "emailMasked": "ja***@example.com",
                "workspace": {"id": 90002, "name": "jack", "planTier": "starter",
                              "status": "active", "maxBrands": 4, "maxSearchesPerMonth": -1,
                              "maxEmailsPerMonth": -1}}
    scoped = auth_scoped_to_workspace(auth_now, blk2)          # blk2 = 60003／上限 -1／已用 14
    add("重定向正控：矩阵用的快照里配额轴换成目标工作区（60003 ⇒ 上限 -1、计划 enterprise）",
        scoped["workspace"]["id"] == 60003 and scoped["workspace"]["maxBrands"] == -1
        and scoped["workspace"]["planTier"] == "enterprise"
        and scoped["activeWorkspaceId"] == 60003,
        "切后＝id %s／上限 %s／计划 %s" % (scoped["workspace"]["id"],
                                        scoped["workspace"]["maxBrands"],
                                        scoped["workspace"]["planTier"]))
    add("重定向反控：**不得就地改**账号快照（当前工作区仍是 90002、上限仍是 4）",
        auth_now["workspace"]["id"] == 90002 and auth_now["workspace"]["maxBrands"] == 4
        and auth_now["activeWorkspaceId"] == 90002,
        "原快照＝id %s／上限 %s" % (auth_now["workspace"]["id"],
                                  auth_now["workspace"]["maxBrands"]))
    scoped_unknown = auth_scoped_to_workspace(auth_now, blk3)   # blk3 = 上限未知／已用 2
    add("重定向反控：目标工作区上限未知时**留空**，绝不拿当前工作区的上限（4）顶替",
        scoped_unknown["workspace"]["maxBrands"] is None
        and scoped_unknown["workspace"]["maxBrands"] != 4,
        "目标上限=%r（当前工作区上限=4）" % scoped_unknown["workspace"]["maxBrands"])
    u = quota_usage_for_verdict(blk3)
    add("重定向正控：喂给判据的 usage 里上限仍是 None（口径与读一致，不新造一个数）",
        u["brands"]["limit"] is None and u["brands"]["used"] == 2
        and u["brands"]["workspaceId"] == 90002,
        "limit=%r used=%r ws=%s" % (u["brands"]["limit"], u["brands"]["used"],
                                   u["brands"]["workspaceId"]))
    v_unknown = quota_write_verdict(blk3)
    add("写链前置检查反控：上限未知时**不下「有位置」的结论**（明说不能断定，也不给余量）",
        "不能断定" in v_unknown and "余量" not in v_unknown and not v_unknown.startswith("还有位置"),
        v_unknown)
    v_full = quota_write_verdict(quota_block_from_row(
        {"id": 1, "maxBrands": 2, "brandCount": 2}, "假通路", "maxBrands", "假通路.maxBrands",
        "假通路.brandCount"))
    add("写链前置检查正控：已满时给「已满」并指向换工作区／管理端调上限（本 CLI 不做那件事）",
        "已满" in v_full and "管理端" in v_full, v_full)

    # ── ③ 参数解析：**离线**验（argparse 层在授权门禁之前，不发任何请求）──
    # 为什么这一段不做"跑真命令"：`capabilities` 在授权门禁之后才能进业务逻辑，
    # 离线环境没有会话 ⇒ 子进程一律停在"请先登录"。参数本身与可见性判据都提成了纯函数，
    # 于是这两条判据**离线就能验到底**（真命令的联调另外由本票的在线实测覆盖）。
    from ..helpgen import build_parser
    ns = build_parser().parse_args(["account", "capabilities", "--workspace", "60003"])
    add("参数正控：`capabilities --workspace 60003` 解析成 workspace=60003（int，不是字符串）",
        getattr(ns, "workspace", None) == 60003 and isinstance(getattr(ns, "workspace", None), int),
        "workspace=%r（%s）" % (getattr(ns, "workspace", None),
                              type(getattr(ns, "workspace", None)).__name__))
    ns2 = build_parser().parse_args(["account", "capabilities"])
    add("参数正控：**不给** --workspace 时该值为 None（老行为一字不变：不加配额块）",
        getattr(ns2, "workspace", None) is None, "workspace=%r" % getattr(ns2, "workspace", None))
    ns3 = build_parser().parse_args(["account", "workspaces", "--with-quota"])
    ns4 = build_parser().parse_args(["account", "workspaces"])
    add("参数正控：`workspaces --with-quota` 解析成 with_quota=True；不给时为 False（默认不额外取数）",
        getattr(ns3, "with_quota", None) is True and getattr(ns4, "with_quota", None) is not True,
        "给了=%r 没给=%r" % (getattr(ns3, "with_quota", None), getattr(ns4, "with_quota", None)))
    p, _doc = run("account", "capabilities", "--workspace", "abc", "--json")
    add("参数反控：--workspace 给非数字 ⇒ 退出码 2（argparse 拦下，不到授权门禁、不发任何请求）",
        p.returncode == 2, "退出码=%s" % p.returncode)
    p, _doc = run("account", "capabilities", "--workspace", "--json")
    add("参数反控：--workspace 给了但没给值 ⇒ 退出码 2（不许静默当成「不指定」）",
        p.returncode == 2, "退出码=%s" % p.returncode)

    # ── ③ 可见性判据：正控＋反控（纯函数，离线）──
    visible_two = [{"id": 90002, "name": "jack", "planTier": "starter"},
                   {"id": 60003, "name": "Admin Workspace", "planTier": "enterprise"}]
    add("可见性正控：目标在可见清单里 ⇒ 判「没问题」（放行）",
        workspace_visibility_problem(visible_two, 60003) is None
        and workspace_visibility_problem(visible_two, "60003") is None,
        "int 与字符串两种写法都放行")
    prob = workspace_visibility_problem(visible_two, 123456)
    add("可见性反控：目标**不在**可见清单里 ⇒ 明确报错（不假装能读别的工作区的配额）",
        isinstance(prob, str) and "123456" in prob and "可见 2 个" in prob, str(prob))
    add("可见性反控：清单没拿到时**不误伤**（返回 None，交给配额通路如实报「取不到」）",
        workspace_visibility_problem([], 123456) is None
        and workspace_visibility_problem(None, 123456) is None,
        "空清单/None 清单都放行")


def _selftest_items():
    """A2 的机器可验判据（正控 ＋ 反例），全部离线、全部落在临时目录。

    两组：
      · **纯函数组**：分区规则的确定性／不撞车／可逆／不越界（`accounts.self_check()`）；
      · **端到端组**：两个账号（A／B）在**临时根 ＋ 假钥匙串**上来回切 2 次 —— 验
        ① 分区不串（A 的产出在 B 的分区里看不见）② 切回免重输（凭据按账号分条、被钉到当前
        账号）③ `paths`／`list` 如实回读当前分区 ④ 切换不删改上一个账号的数据。
    """
    import json
    import shutil
    import subprocess
    import sys
    import tempfile

    items = []

    def add(desc, ok, detail=""):
        items.append((desc, bool(ok), detail))

    ok_pure, pure_items = accounts_mod.self_check()
    for desc, ok, detail in pure_items:
        add("纯函数：" + desc, ok, detail)

    #: 两个账号的**掩码必须能分辨**（否则"当前是哪个账号"在结果里看不出区别，
    #: 这条自检就验不动）—— 故意让本地部分首字母与域名都不同。
    ACCT_A, ACCT_B = "acct.a@example.com", "beta.b@example.org"
    root = tempfile.mkdtemp(prefix="daniel-accounts-e2e-")
    bin_daniel = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "bin", "daniel")
    store = os.path.join(root, "fake-keychain.json")
    fake = os.path.join(root, "security")
    fixture = os.path.join(root, "auth-fixture.json")

    def run(*argv, env_extra=None):
        env = dict(os.environ)
        env.pop("DANIEL_HOME", None)
        env.pop("DANIEL_BASE_HOME", None)
        env.pop("DANIEL_EMAIL", None)
        env.pop("DANIEL_PASSWORD", None)
        env.pop("DANIEL_KEYCHAIN_ACCOUNT", None)
        env.update({"DANIEL_HOME": root, "DANIEL_SECURITY_BIN": fake,
                    "FAKE_KEYCHAIN_STORE": store,
                    "DANIEL_CLI_AUTH_FIXTURE": fixture})
        env.update(env_extra or {})
        p = subprocess.run([sys.executable, bin_daniel] + list(argv),
                           capture_output=True, text=True, env=env, timeout=300)
        try:
            doc = json.loads(p.stdout)
        except ValueError:
            doc = None
        return p, doc

    try:
        with open(store, "w", encoding="utf-8") as fh:
            json.dump([{"service": "daniel-copilot", "account": ACCT_A, "password": "pw-A-secret"},
                       {"service": "daniel-copilot", "account": ACCT_B, "password": "pw-B-secret"}],
                      fh)
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write(_FAKE_SECURITY)
        os.chmod(fake, 0o755)
        with open(fixture, "w", encoding="utf-8") as fh:
            json.dump({"systemRole": "super_admin", "userStatus": "active",
                       "activeWorkspaceId": 90002}, fh)

        # 未切换时：落点＝根目录（既有安装一个字不变）
        p, doc = run("account", "paths", "--json")
        base_home = ((doc or {}).get("data") or {}).get("home")
        add("未指定账号时落点＝根目录（既有安装原地不动）",
            p.returncode == 0 and base_home == root, "home=%s" % base_home)

        # 两账号来回切 2 次（每次带 --confirm）
        seq, failures = [], []
        for n, acct in enumerate([ACCT_A, ACCT_B, ACCT_A, ACCT_B], 1):
            p, doc = run("account", "switch", acct, "--confirm", "--json")
            data = (doc or {}).get("data") or {}
            part = ((data.get("readback") or {}).get("detail") or {}).get("②目标分区就绪", {}).get("分区落点")
            seq.append({"n": n, "acct": acct, "rc": p.returncode, "partition": part})
            if p.returncode != 0:
                failures.append("第 %d 次切换（%s）退出码 %s：%s"
                                % (n, acct, p.returncode, (p.stderr or "").strip()[-160:]))
        add("两个账号来回切 2 次都成功（带 --confirm 真执行）",
            not failures and len(seq) == 4, "；".join(failures) or "4 次切换全部退出码 0")
        add("每次切换后落点都跟着账号走，且从未落到代码目录",
            all(s["partition"] and s["partition"].startswith(root + os.sep) for s in seq),
            " ｜ ".join("%s→%s" % (s["acct"].split("@")[0], os.path.basename(s["partition"] or ""))
                        for s in seq))
        part_a = [s["partition"] for s in seq if s["acct"] == ACCT_A][-1]
        part_b = [s["partition"] for s in seq if s["acct"] == ACCT_B][-1]
        add("两个账号的分区是两个不同目录（不串的物理前提）",
            bool(part_a) and bool(part_b) and part_a != part_b, "%s ≠ %s" % (part_a, part_b))

        # 不串：在 A 的分区产出目录放一个可辨识对象，切到 B 之后它不在 B 的分区下
        marker = os.path.join(part_a, "output", "可辨识对象-A.txt")
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write("A 的产出\n")
        p, doc = run("account", "switch", ACCT_B, "--confirm", "--json")
        out_b = os.path.join(part_b, "output", "可辨识对象-A.txt")
        add("A 的产出在 B 的分区里看不见（切到 B 后不串）",
            not os.path.exists(out_b), "A 的产出：%s；B 侧同名文件存在=%s"
                                       % (marker, os.path.exists(out_b)))
        p, doc = run("account", "switch", ACCT_A, "--confirm", "--json")
        add("切回 A 后 A 的产出还在（切换不丢件、可逆）",
            os.path.exists(marker), marker)

        # paths／list 如实回读当前分区
        p, doc = run("account", "paths", "--json")
        data = (doc or {}).get("data") or {}
        back = (data.get("账号分区") or {})
        add("account paths 回读当前分区（含根、分区、来源说明）",
            back.get("当前账号分区") == part_a and back.get("当前账号(掩码)", "").startswith("a***")
            and bool(back.get("落点来源")) and bool(back.get("根的选择理由")),
            "分区=%s ｜ 来源=%s ｜ 根理由=%s" % (back.get("当前账号分区"), back.get("落点来源"),
                                                back.get("根的选择理由")))
        add("account paths 的分区一律在 DANIEL_HOME 之下、且不是代码目录",
            str(back.get("生效落点") or "").startswith(root + os.sep),
            str(back.get("生效落点")))
        p, doc = run("account", "list", "--json")
        data = (doc or {}).get("data") or {}
        rows = data.get("已存账号") or []
        add("account list 列出两个已存账号，都标了钥匙串条目存在（凭据按账号分条）",
            p.returncode == 0 and len(rows) == 2
            and all(r.get("钥匙串条目") == "有" for r in rows)
            and len({r.get("邮箱(掩码)") for r in rows}) == 2,
            " ｜ ".join("%s 条目=%s 分区=%s" % (r.get("邮箱(掩码)"), r.get("钥匙串条目"),
                                              os.path.basename(r.get("分区落点") or ""))
                        for r in rows))
        add("account list 标出的「当前」就是刚切到的账号",
            sum(1 for r in rows if r.get("是否当前")) == 1
            and [r for r in rows if r.get("是否当前")][0].get("分区落点") == part_a,
            "当前=%s" % [(r.get("邮箱(掩码)")) for r in rows if r.get("是否当前")])

        # 切回免重输：凭据被钉到当前账号（取到的是 A 那条，不是 B 那条），且不回显值
        p, doc = run("account", "credentials", "--json")
        data = (doc or {}).get("data") or {}
        kc = data.get("keychain") or {}
        add("切回免重输：凭据读取被钉到当前账号（取到 A 那条钥匙串条目，无需重输）",
            data.get("source") == "keychain" and kc.get("account_masked", "").startswith("a***"),
            "source=%s 条目账号=%s" % (data.get("source"), kc.get("account_masked")))
        raw = p.stdout
        add("任何输出都不回显凭据值（两条密码串都不出现）",
            "pw-A-secret" not in raw and "pw-B-secret" not in raw, "已扫 stdout")

        # 反例：目标账号在本机没有凭据时必须拒绝（否则"切过去要重输密码"＝假功能）
        p, doc = run("account", "switch", "nobody@example.com", "--confirm", "--json")
        add("反例：目标账号没有可复用凭据时按用户错误拒绝（退出码 2，零写入）",
            p.returncode == 2, "退出码=%s" % p.returncode)

        # 干跑：不带 --confirm 必须退出码 3 且不写指针
        before_state = open(accounts_mod.state_path(), encoding="utf-8").read() \
            if os.path.exists(accounts_mod.state_path()) else ""
        p, doc = run("account", "switch", ACCT_A, "--json")
        add("干跑：不带 --confirm 退出码 3，且不动当前账号指针",
            p.returncode == 3 and ((doc or {}).get("data") or {}).get("executed") is False,
            "退出码=%s executed=%s" % (p.returncode,
                                       ((doc or {}).get("data") or {}).get("executed")))

        # 可逆：--clear 回到根落点，之后还能再切回来
        p, doc = run("account", "switch", "--clear", "--confirm", "--json")
        p2, doc2 = run("account", "paths", "--json")
        back2 = ((doc2 or {}).get("data") or {}).get("账号分区") or {}
        add("可逆：--clear 取消当前账号后落点回到根目录（既有数据一直在那里）",
            p.returncode == 0 and back2.get("生效落点") == root
            and back2.get("是否已分区") is False,
            "退出码=%s 生效落点=%s 已分区=%s" % (p.returncode, back2.get("生效落点"),
                                                back2.get("是否已分区")))
        p, doc = run("account", "switch", ACCT_A, "--confirm", "--json")
        p2, doc2 = run("account", "paths", "--json")
        back3 = ((doc2 or {}).get("data") or {}).get("账号分区") or {}
        add("可逆：--clear 之后还能切回 A（分区与 A 的产出都还在）",
            p.returncode == 0 and back3.get("当前账号分区") == part_a and os.path.exists(marker),
            "分区=%s ｜ A 的产出还在=%s" % (back3.get("当前账号分区"), os.path.exists(marker)))

        # TICKET-203：按工作区读配额的离线判据（正控 ＋ 反控，零请求）
        _quota_selftest_items(add, run, root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return items, ok_pure


def selftest(emitter):
    """模块自带自检入口（`daniel account --self-test`；也由 `daniel --self-test` 的 R2 组自动纳入）。"""
    items, _ok_pure = _selftest_items()
    ok_all = all(ok for _d, ok, _x in items)
    if getattr(emitter, "json_mode", False):
        emitter.result(data={"summary": "%d 项：通过 %d／未过 %d"
                                        % (len(items), sum(1 for _d, ok, _x in items if ok),
                                           sum(1 for _d, ok, _x in items if not ok)),
                             "明细": [{"项": d, "通过": ok, "说明": x} for d, ok, x in items]},
                       ok=ok_all, exit_code=0 if ok_all else 1)
    else:
        for d, ok, x in items:
            print("  %s %s%s" % ("通过" if ok else "失败", d, ("  —— " + x) if x else ""),
                  file=emitter.out)
        print("结论：%s（%d 项：通过 %d／未过 %d）"
              % ("✅ 全绿" if ok_all else "❌ 有未过项", len(items),
                 sum(1 for _d, ok, _x in items if ok),
                 sum(1 for _d, ok, _x in items if not ok)), file=emitter.out)
    return 0 if ok_all else 1


SELFTEST = selftest          # 模块自带自检入口（schema 声明 selfTest ⇒ 实现必须给这个名字）


WRITE_HANDLERS = {
    "credentials-set": gated_write(
        BOARD, "credentials-set", CREDENTIALS_SET_ACTION, stage=STAGE_LIVE,
        plan_fn=_credentials_set_plan, run_fn=_credentials_set_run,
        danger="会更新本机系统钥匙串里的凭据条目（可逆：再写一次即覆盖）；"
               "不改 Daniel 侧任何数据，也不写任何明文凭据文件"),
    "login": gated_write(
        BOARD, "login", LOGIN_ACTION, stage=STAGE_LIVE,
        plan_fn=_login_plan, run_fn=_login_run,
        danger="会重写数据落点里的会话文件（权限 600，重新登录即可刷新）；"
               "不触发采集、不改业务数据"),
    "switch": gated_write(
        BOARD, "switch", SWITCH_ACTION, stage=STAGE_LIVE,
        plan_fn=_switch_plan, run_fn=_switch_run,
        danger="只写本机的一个账号指针文件并建目录（可逆：再切回去即恢复）；"
               "**不写任何凭据、不删改任何既有数据**、不联网、不动 Daniel 侧任何数据"),
}
