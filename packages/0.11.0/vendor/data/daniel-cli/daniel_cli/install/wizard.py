# -*- coding: utf-8 -*-
"""安装向导（TICKET-195）—— **一条命令做完四件事** 的判据层。

用户 2026-10-16 逐字要求
------------------------
> 「我想要的整个 cli 的逻辑：`https://project.feishu.cn/b/helpcenter/1ykiuvvj/sypelipg` 就是飞书项目，
> 产品手册中关于 cli 和 mcp server 的部分，**这种安装和接入形式**」

> 「可以按照你的流程：一条命令做完 **装 CLI ＋ 装能力束 ＋ 写宿主接入（复用 connect）＋ 起登录**，
> 后续只需要**替换为 npm 包安装**即可」

四步（本文件就是它们唯一的实现处）
----------------------------------
| 步 | 做什么 | 复用谁 |
|---|---|---|
| ① | **装 CLI**：把入口装进用户 PATH（软链 ＋ 一行 PATH 配置，**幂等**、写前落快照） | 沿用 `06` 步骤 2／`TICKET-189` 的既有做法 |
| ② | **装能力束**：8 束 `kol-*` 按**软链**装到宿主技能目录（唯一真源留在包里，升级自动跟随） | 沿用 `06` 步骤 3 的口径（**不复制**） |
| ③ | **写宿主接入**：**调 `daniel connect --host <宿主> --apply --confirm`**（不重造） | `daniel_cli/connect/**` |
| ④ | **起登录**：打开／打印 Daniel 登录页，让用户在**页面上**登录后回读会话 | `account login --browser`（`TICKET-194`） |

🔴 **不在向导里向用户索要账号密码**：第 ④ 步只走浏览器授权路（`--session-cookie-stdin` 是
把**浏览器里的会话**用管道喂进来的无头形态，与 `account login` 的同名开关等价）。

🔴 **自动化路径不得产生"真人可见的副作用"**（2026-10-16 事故后固化）
------------------------------------------------------------------------
`install` 是**给人用的**：人在真终端里跑，第 ④ 步可以打开 Daniel 登录页。但**一切自动化**
（自检／验收／CI／Agent 调用／管道喂值）**绝不许调起系统浏览器** —— 事故就是"验收驱动反复跑
`install --confirm` ⇒ 用户桌面上被反复弹出登录页"。因此判据落成**代码里的默认行为**（不是纪律）：

  ① 环境变量 `DANIEL_NO_OPEN` 为真 ⇒ 任何路径都不开；
  ② 显式 `--no-open` ⇒ 不开；
  ③ **stdin 不是交互终端**（脚本／管道／子进程）⇒ **默认就不开**。

判据只有一处实现（`commands/mod_account.no_open_decision`），并在 `_open_browser()` **函数自身**
里先过一道 —— 任何调用方漏传开关也开不了。非交互时改为**打印登录页地址**＋下一步命令。

⑤ **装完自动复核（TICKET-206 · 只读，不是第五步写入）**
--------------------------------------------------
用户 2026-10-17 逐字要求
> 「**整个 cli 的逻辑在于，一条指令，按照工作流完成全量和完整的安装** …… 而**不是**需要用户去输入
> 对应的指令后才能完整安装 …… 很多人是没有程序基础的，他们需要的是**傻瓜式安装**。」

所以四步跑完之后，**同一进程内自动再跑一次只读复核**（直接调 `check_all()` —— 与
`daniel install --check` **同一套判据函数**，不重写、不重跑登录、不新增联网断言），并把
**四步逐条结论 ＋ 复核四项结论**打在输出**末尾**：用户不需要再敲任何命令就知道"装没装好"。
`daniel install --check` 这条命令**保留**（随时可重跑）。它只读本机 ⇒ 不改变四步的任何写行为。

四条纪律
--------
① **"包从哪来"只有一处**（`source.py::resolve`）：本文件只消费它给出的 `包根`／`入口`／`语料根`，
   将来换 npm 渠道时本文件**一行不改**；
② **幂等**：每一步都先判"现状是否已经就是目标"，是则**不改任何文件**（不重写软链、不重复追加
   PATH 行、不重复建已存在的软链）—— 重复跑结果不变；
③ **可回滚**：写前把**原文**落进 `$DANIEL_HOME/install/snapshots/<时间戳>/`，写后逐项回读对账；
   宿主配置只经 `connect` 动本产品那一条；
④ **不撒谎**：每一步只给「已完成／不适用（附理由）」两种结论；第 ④ 步没登录就**明说没完成**
   并给出下一步命令，绝不假称装好了。
"""
import argparse
import atexit
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

from ..connect import hosts
from ..exits import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE
from ..runtime import CliError, Context, Emitter, load_capability
from . import source as source_mod

#: 随包的 8 束能力束（**从包里算出来**，这里只是 06 与验收对照用的名字表；
#: 真源是 `source.skill_names()` —— 包里少一束就少装一束，不假装）
SKILL_NAMES = ("kol-intelligence", "kol-discovery", "kol-screening", "kol-outreach",
               "kol-negotiation", "kol-contract", "kol-daniel-api", "kol-execution-sov")

#: 登录页路径（与 `authgate.LOGIN_PAGE_PATH` 同源，这里只做文档级引用）
LOGIN_HINT = "daniel account login --browser --confirm"

#: 第 ④ 步"未完成"时的**一行下一步**（无 TTY 时打印它，不阻塞）
NEXT_STEP_TEXT = ("下一步：%s（打开 Daniel 登录页，在页面上完成登录后把会话粘回来）；"
                  "登录完成后想再确认，可重跑 `daniel install --check`（装完已自动复核，可选）"
                  % LOGIN_HINT)


# ═══════════════════════ 落点（一律走既有解析层） ═══════════════════════
def data_home():
    return load_capability("daniel_paths").resolve("home")


def install_root():
    return os.path.join(data_home(), "install")


def state_path():
    return os.path.join(install_root(), "state.json")


def read_state():
    try:
        with io.open(state_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (IOError, OSError, ValueError):
        return {}


def now_stamp():
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _sha256_file(path):
    h = hashlib.sha256()
    with io.open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm(path):
    """归一化用于**比较**的路径（两侧都要过；只归一化一侧 = 没修 · CLS-84）。"""
    return os.path.realpath(os.path.abspath(str(path or "")))


def _snap_path(stamp):
    return os.path.join(install_root(), "snapshots", stamp)


def _ensure_snap(snapbox):
    """**懒建**快照目录：只有真的要落快照时才建。

    为什么懒建：票面要求"重复跑结果不变" —— 要是每次跑都先建一个空快照目录，那"结果不变"
    就成了一句空话（磁盘上确实多了东西）。没有改动 ⇒ 连目录都不建。
    """
    if snapbox.get("dir"):
        return snapbox["dir"]
    d = _snap_path(snapbox["stamp"])
    try:
        if not os.path.isdir(d):
            os.makedirs(d)
    except OSError as e:
        raise CliError("快照目录建不出来（%s）：%s" % (d, e), code=EXIT_INTERNAL,
                       hint="先确认数据落点可写：`daniel account paths`")
    snapbox["dir"] = d
    return d


def _snapshot_file(src, snapbox, name):
    """把一份原文复制进快照目录（**写前落快照**）；返回落点或 None。"""
    if not os.path.isfile(src):
        return None
    dest = os.path.join(_ensure_snap(snapbox), name)
    shutil.copy2(src, dest)
    return dest


def _run(argv, timeout=900, stdin_text=None, cwd=None):
    """跑一个子进程并拿回 `(退出码, stdout, stderr)`（超时如实记，不静默）。"""
    try:
        p = subprocess.run([str(a) for a in argv], capture_output=True, text=True,
                           timeout=timeout, input=stdin_text, cwd=cwd)
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return None, "", "超时（%s 秒）" % timeout
    except OSError as e:
        return None, "", "%s: %s" % (type(e).__name__, e)


def _install_prefix(ctx):
    """跑**已装那份包**的命令前缀。

    为什么必须跑"已装的入口"而不是当前进程：`connect --doctor`／`auth status` 的判据是
    「与本 CLI 当前所在的包比」—— 从包里装的时候，当前进程是**源**那份，判据必须作用在
    **装出来的那一份**上，否则"接入指向当前包"就答错了对象。
    """
    entry = os.path.join(_bin_dir(ctx), "daniel")
    if os.path.isfile(entry):
        return [hosts.interpreter(), entry]
    src = source_mod.resolve(ctx.get("from"))
    return [hosts.interpreter(), src["入口"]]


def _installed_json(ctx, argv, timeout=600):
    """跑已装入口的一条只读命令并取回 `--json` 信封（取不到如实返回 None）。"""
    code, out, err = _run(_install_prefix(ctx) + list(argv) + ["--json"], timeout=timeout)
    try:
        return code, json.loads(out or "")
    except ValueError:
        return code, None


# ═══════════════════════ ① 装 CLI（入口进 PATH） ═══════════════════════
def _bin_dir(ctx):
    explicit = ctx.get("bin_dir")
    if explicit:
        return os.path.abspath(os.path.expanduser(str(explicit)))
    return os.path.join(os.path.expanduser("~"), ".local", "bin")


def _entry_link_state(entry, want):
    """入口现状：不存在／已是本条软链／指向别处／是个普通文件（都要分档说清）。"""
    st = {"入口": entry, "指向": want, "存在": os.path.exists(entry) or os.path.islink(entry),
          "是软链": os.path.islink(entry), "当前指向": None, "一致": False, "形态": None}
    if not st["存在"]:
        st["形态"] = "不存在（本次将新建这条软链）"
        return st
    if st["是软链"]:
        st["当前指向"] = os.readlink(entry)
        st["一致"] = _norm(entry) == _norm(want)
        st["形态"] = ("已是本条软链（一致）" if st["一致"]
                      else "软链指向别处：%s ⇒ 本次改指" % st["当前指向"])
        return st
    st["形态"] = "是一个**普通文件**（不是本产品建的软链）⇒ 本次会把它改名留底后建软链"
    return st


def _rc_file():
    """PATH 配置写哪个文件：zsh 用 `~/.zshrc`（macOS 默认），否则退回 bash/profile 的常见落点。"""
    home = os.path.expanduser("~")
    zshrc = os.path.join(home, ".zshrc")
    shell = os.environ.get("SHELL", "")
    if os.path.isfile(zshrc) or shell.endswith("zsh"):
        return zshrc
    for name in (".bash_profile", ".profile"):
        p = os.path.join(home, name)
        if os.path.isfile(p):
            return p
    return os.path.join(home, ".profile")


def _path_line(bin_dir):
    """PATH 那一行：落点是"用户主目录下的标准位置"时写 `$HOME/...`（换机器／换用户名也能用）。"""
    home = os.path.expanduser("~")
    if _norm(bin_dir) == _norm(os.path.join(home, ".local", "bin")):
        return 'export PATH="$HOME/.local/bin:$PATH"'
    return 'export PATH="%s:$PATH"' % bin_dir


def _rc_lines(path):
    try:
        with io.open(path, encoding="utf-8") as fh:
            return fh.read().splitlines()
    except (IOError, OSError):
        return []


def _rc_has(path, bin_dir):
    """PATH 行是否已在（**幂等的判据**：按"落点"判，不按整行逐字判）。

    两种写法都认：**展开后的绝对路径**与 `$HOME/.local/bin`（标准落点本命令写后者）。
    只认一种的后果是**重复跑会重复追加** —— 那正是幂等要防的事。
    """
    home = os.path.expanduser("~")
    marks = [bin_dir]
    if bin_dir.startswith(home + os.sep):
        marks.append("$HOME/" + os.path.relpath(bin_dir, home))
    for ln in _rc_lines(path):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if any(m in s for m in marks):
            return True
    return False


def step_cli_plan(ctx, src):
    bin_dir = _bin_dir(ctx)
    entry = os.path.join(bin_dir, "daniel")
    rc = _rc_file()
    line = _path_line(bin_dir)
    st = _entry_link_state(entry, src["入口"])
    has = _rc_has(rc, bin_dir)
    done = bool(st["一致"] and has)
    return {
        "步": "① 装 CLI（入口进 PATH）",
        "结论": "已完成（入口已指向这份包，且 PATH 行已在）" if done else "待执行",
        "bin 目录": bin_dir,
        "入口": entry,
        "将指向": src["入口"],
        "入口现状": st,
        "PATH 行": line,
        "PATH 配置文件": rc,
        "PATH 行已存在": has,
        "会改哪些文件": ([entry] if not st["一致"] else []) + ([rc] if not has else []),
        "幂等": "入口已是这条软链 ⇒ 不重写；PATH 行已存在 ⇒ 不重复追加（重复跑结果不变）",
        "不装什么": "不装 pip 包、不建虚拟环境、不碰系统目录、不改解释器",
    }


def step_cli_apply(ctx, src, snapbox):
    bin_dir = _bin_dir(ctx)
    entry = os.path.join(bin_dir, "daniel")
    rc = _rc_file()
    line = _path_line(bin_dir)
    before = _entry_link_state(entry, src["入口"])
    changes, snaps = [], []

    if not before["一致"]:
        try:
            if not os.path.isdir(bin_dir):
                os.makedirs(bin_dir)
        except OSError as e:
            raise CliError("bin 目录建不出来（%s）：%s" % (bin_dir, e), code=EXIT_INTERNAL,
                           hint="换一个可写目录：`daniel install --bin-dir <目录> --confirm`")
        if before["存在"] and not before["是软链"]:
            keep = "%s.bak-%s" % (entry, time.strftime("%Y%m%d-%H%M%S"))
            shutil.move(entry, keep)
            changes.append("原有同名普通文件已改名留底：%s" % keep)
            snaps.append({"项": "原有入口文件", "留底": keep})
        tmp = entry + ".daniel-install-tmp"
        if os.path.islink(tmp) or os.path.exists(tmp):
            os.remove(tmp)
        os.symlink(src["入口"], tmp)
        os.replace(tmp, entry)                      # 原子替换：不会留下半截入口
        changes.append("入口软链已建/改指：%s ⇒ %s" % (entry, src["入口"]))

    has = _rc_has(rc, bin_dir)
    if not has:
        snap = _snapshot_file(rc, snapbox, os.path.basename(rc) + ".orig")
        if snap:
            snaps.append({"项": "PATH 配置文件原文", "快照": snap})
        try:
            with io.open(rc, "a", encoding="utf-8") as fh:
                if os.path.isfile(rc) and os.path.getsize(rc) > 0:
                    fh.write("\n")
                fh.write(line + "\n")
        except OSError as e:
            raise CliError("PATH 配置写不进去（%s）：%s" % (rc, e), code=EXIT_INTERNAL,
                           hint="手工把这一行加进你的 shell 配置：%s" % line)
        changes.append("PATH 行已追加到 %s：%s" % (rc, line))

    # 回读对账：① 软链指向对不对 ② PATH 行在不在 ③ **入口真的跑得起来**（直接执行，用它的 shebang）
    after = _entry_link_state(entry, src["入口"])
    rc_ok = _rc_has(rc, bin_dir)
    code_direct, out_direct, err_direct = _run([entry, "--version"], timeout=120)
    how = "直接执行入口（用它的 shebang）"
    if code_direct != 0:
        code_direct, out_direct, err_direct = _run([hosts.interpreter(), entry, "--version"],
                                                   timeout=120)
        how = "用 %s 执行入口" % hosts.interpreter()
    checks = [
        {"项": "入口软链指向这份包", "通过": bool(after["一致"]), "实际": after["当前指向"]},
        {"项": "PATH 行已在配置文件里", "通过": rc_ok, "实际": rc},
        {"项": "入口真能跑（%s）" % how, "通过": code_direct == 0,
         "实际": (out_direct or err_direct or "").strip().splitlines()[-1:] or
                 ["退出码 %s" % code_direct]},
    ]
    bad = [c["项"] for c in checks if not c["通过"]]
    done = not bad
    return {
        "步": "① 装 CLI（入口进 PATH）",
        "结论": "已完成" if done else "未完成",
        "改动": changes or ["无（已是目标状态，未改动任何文件）"],
        "快照": snaps,
        "回读": {"verified": done, "逐项": checks,
                 "reason": None if done else "回读对账未通过：" + "；".join(bad)},
        "入口": entry, "将指向": src["入口"], "PATH 配置文件": rc, "PATH 行": line,
        "下一步": "新开一个终端后 `daniel --help` 应当可用（PATH 是登录时读的）",
    }


# ═══════════════════════ ② 装能力束（软链） ═══════════════════════
def _project_dir(ctx):
    explicit = ctx.get("project")
    if explicit:
        return os.path.abspath(os.path.expanduser(str(explicit)))
    return os.path.abspath(os.getcwd())


def _skills_dir(ctx):
    explicit = ctx.get("skills_dir")
    if explicit:
        return os.path.abspath(os.path.expanduser(str(explicit)))
    return os.path.join(_project_dir(ctx), ".agents", "skills")


def _skill_state(dst, want):
    st = {"落点": dst, "指向": want, "存在": os.path.exists(dst) or os.path.islink(dst),
          "是软链": os.path.islink(dst), "当前指向": None, "一致": False, "形态": None}
    if not st["存在"]:
        st["形态"] = "不存在（本次将新建软链）"
        return st
    if st["是软链"]:
        st["当前指向"] = os.readlink(dst)
        st["一致"] = _norm(dst) == _norm(want)
        st["形态"] = "已是本条软链（一致）" if st["一致"] else "软链指向别处 ⇒ 本次改指"
        return st
    st["形态"] = "真实目录/文件（**不覆盖**：先改名留底，再建软链）"
    return st


def step_skills_plan(ctx, src):
    skills_dir = _skills_dir(ctx)
    rows = []
    for name in source_mod.skill_names(src):
        rows.append(_skill_state(os.path.join(skills_dir, name),
                                 source_mod.skill_source(src, name)))
    missing_src = [n for n in SKILL_NAMES if n not in source_mod.skill_names(src)]
    done = bool(rows) and all(r["一致"] for r in rows) and not missing_src
    return {
        "步": "② 装能力束（8 束 kol-*，软链）",
        "结论": "已完成（8 束软链都已指向这份包）" if done else "待执行",
        "技能目录": skills_dir,
        "能力束数": len(rows),
        "逐束现状": rows,
        "唯一真源留在包里": src["语料根"],
        "不复制": "软链方式：升级能力包时技能自动跟着新，且不占额外空间（复制式实测占 1.2 MB）",
        "包里缺的束": missing_src or "无",
        "会改哪些条目": [r["落点"] for r in rows if not r["一致"]],
        "幂等": "已是本条软链的条目一个都不动（重复跑结果不变）",
        "不碰什么": "**不修改、不删除**任何已存在的技能目录；同名真实目录先改名留底",
    }


def step_skills_apply(ctx, src, snapbox):
    """（`snapbox` 本步用不到：同名真实条目的留底是**原地改名**，不搬进快照目录 ——
    用户一眼能看到、一步能撤回；见下面 `keep` 那一段。）"""
    skills_dir = _skills_dir(ctx)
    try:
        if not os.path.isdir(skills_dir):
            os.makedirs(skills_dir)
    except OSError as e:
        raise CliError("技能目录建不出来（%s）：%s" % (skills_dir, e), code=EXIT_INTERNAL,
                       hint="换一个可写落点：`daniel install --skills-dir <目录> --confirm`")
    changes, snaps, checks = [], [], []
    for name in source_mod.skill_names(src):
        want = source_mod.skill_source(src, name)
        dst = os.path.join(skills_dir, name)
        st = _skill_state(dst, want)
        if not st["一致"]:
            if st["存在"] and not st["是软链"]:
                # 口径跟 `06` 步骤 3 一致：**同名先改名留底，再放新的**（**原地**改名 —— 就在
                # 同一个技能目录里，用户一眼能看到、一步能撤回；不悄悄搬到别处）。
                keep = "%s.bak-%s" % (dst, time.strftime("%Y%m%d-%H%M%S"))
                shutil.move(dst, keep)
                ctx.warn("同名技能条目**不是本产品建的软链**（可能是复制式安装的旧副本）："
                         "已**原地改名留底** %s ⇒ %s（本命令不覆盖、不删除你原有的技能）"
                         % (dst, os.path.basename(keep)))
                changes.append("现有同名条目已改名留底：%s ⇒ %s" % (dst, keep))
                snaps.append({"项": "既有 %s" % name, "留底": keep})
            if os.path.islink(dst):
                os.remove(dst)
            os.symlink(want, dst)
            changes.append("软链已建/改指：%s ⇒ %s" % (dst, want))
        ok_link = os.path.islink(dst) and _norm(dst) == _norm(want)
        src_skill = os.path.join(want, "SKILL.md")
        dst_skill = os.path.join(dst, "SKILL.md")
        digest = None
        if ok_link and os.path.isfile(src_skill) and os.path.isfile(dst_skill):
            digest = (_sha256_file(src_skill) == _sha256_file(dst_skill))
        checks.append({"项": "%s：软链指向 + 正文可读且与包内一致" % name,
                       "通过": bool(ok_link and digest is not False),
                       "实际": ("%s ｜ SKILL.md sha256 前12位 %s"
                                % (os.readlink(dst) if os.path.islink(dst) else "(非软链)",
                                   (_sha256_file(dst_skill)[:12]
                                    if os.path.isfile(dst_skill) else "读不到")))})
    bad = [c["项"] for c in checks if not c["通过"]]
    done = bool(checks) and not bad
    return {
        "步": "② 装能力束（8 束 kol-*，软链）",
        "结论": "已完成" if done else "未完成",
        "改动": changes or ["无（已是目标状态，未改动任何文件）"],
        "快照": snaps,
        "回读": {"verified": done, "逐项": checks,
                 "reason": None if done else "回读对账未通过：" + "；".join(bad)},
        "技能目录": skills_dir,
        "能力束数": len(checks),
        "唯一真源": src["语料根"],
        "下一步": "宿主里新开一个会话，用 `/` 或 `$` 应能看到这 8 个 kol- 开头的技能（技能列表是宿主启动时扫描的）",
    }


# ═══════════════════════ ③ 写宿主接入（复用 connect） ═══════════════════════
def hosts_to_apply(ctx):
    """这次要接进哪些宿主：显式 `--host` 优先；否则**自动检测本机有痕迹的宿主**（都没有 ⇒ 不适用）。"""
    explicit = ctx.get("host")
    if explicit:
        return [hosts.host_meta(explicit)["key"]], "命令行显式指定（--host %s）" % explicit
    det = [k for k in hosts.host_keys() if hosts.host_detected(k)]
    if det:
        return det, "自动检测：本机存在这些宿主的痕迹（%s）" % "、".join(
            os.path.dirname(hosts.config_path(k)) for k in det)
    return [], "本机未检测到任何宿主（%s 与 %s 都不存在）" % (
        os.path.dirname(hosts.config_path(hosts.host_keys()[0])),
        os.path.dirname(hosts.config_path(hosts.host_keys()[-1])))


def step_connect_plan(ctx, src):
    keys, why = hosts_to_apply(ctx)
    rows = []
    for k in keys:
        st = hosts.read_state(k)
        rows.append({"宿主": k, "配置文件": st.get("配置文件"),
                     "宿主检测到": bool(st.get("宿主是否检测到")),
                     "本产品条目数": st.get("条目数"),
                     "其它 server": "、".join(st.get("其它成员") or []) or "无"})
    if not keys:
        return {"步": "③ 写宿主接入（复用 connect）", "结论": "不适用（%s）" % why,
                "原因": why, "复用命令": [], "逐宿主现状": [],
                "什么时候需要它": "装上 Cursor／Codex 之后重跑 "
                                  "`daniel install --host cursor --confirm` 即可接上"}
    return {
        "步": "③ 写宿主接入（复用 connect）",
        "结论": "待执行",
        "要接入的宿主": keys,
        "宿主选择理由": why,
        "复用命令": ["daniel connect --host %s --apply --confirm" % k for k in keys],
        "逐宿主现状": rows,
        "只动本产品那一条": "Cursor 保留 `mcpServers` 里其它 server；Codex 保留 `config.toml` 里其它表与注释",
        "幂等": "connect 自己就是幂等的：内容已一致时不改动文件（sha256 不变）",
    }


def step_connect_apply(ctx, src, keys):
    prefix = _install_prefix(ctx)
    rows = []
    for k in keys:
        argv = ["connect", "--host", k, "--apply", "--confirm"]
        code, out, err = _run(prefix + argv, timeout=600)
        st = hosts.read_state(k)
        entry = st.get("取值") or {}
        args = entry.get("args") or [None]
        want_server = os.path.join(src["包根"], "mcp", "server.py")
        checks = [
            {"项": "%s：配置文件能读回" % k, "通过": bool(st.get("存在")),
             "实际": st.get("配置文件")},
            {"项": "%s：本产品条目恰好一条" % k, "通过": st.get("条目数") == 1,
             "实际": st.get("条目数")},
            {"项": "%s：服务入口指向本次装的包" % k,
             "通过": _norm(args[0]) == _norm(want_server), "实际": args[0]},
        ]
        bad = [c["项"] for c in checks if not c["通过"]]
        rows.append({
            "宿主": k,
            "connect 退出码": code,
            "connect 输出末行": (out or err or "").strip().splitlines()[-1:] or [""],
            "回读": {"verified": not bad, "逐项": checks,
                     "reason": None if not bad else "回读对账未通过：" + "；".join(bad)},
        })
    bad_rows = [r for r in rows if not r["回读"]["verified"] or r["connect 退出码"] != 0]
    done = bool(rows) and not bad_rows
    return {
        "步": "③ 写宿主接入（复用 connect）",
        "结论": "已完成" if done else "未完成",
        "逐宿主": rows,
        "复用命令": ["daniel connect --host %s --apply --confirm" % k for k in keys],
        "回读": {"verified": done,
                 "reason": None if done else "有宿主没接上：" + "、".join(
                     r["宿主"] for r in bad_rows)},
        "下一步": "判断接入「通不通」不用打开宿主：`daniel connect --doctor`",
    }


# ═══════════════════════ ④ 起登录（浏览器授权路） ═══════════════════════
def _login_page_url():
    from ..runtime import load_client
    from .. import authgate
    return load_client().base_url().rstrip("/") + authgate.LOGIN_PAGE_PATH


def _no_open_decision(explicit=False):
    """要不要禁止调起系统浏览器 —— **判据只有一处**（`commands/mod_account.no_open_decision`）。

    为什么向导这边不自己判一遍：开浏览器是**真人可见的副作用**（用户桌面上会弹窗口）。判据
    写两份就一定会漂移，而漂移的代价是"自动化又偷偷弹了一次窗口"。所以这里只**转发**：
    环境变量 `DANIEL_NO_OPEN`／显式 `--no-open`／**非交互终端**，三条任一命中即禁止开。
    """
    from ..commands.mod_account import no_open_decision
    return no_open_decision(explicit)


def _open_browser(url):
    """尽力用系统默认浏览器打开登录页（**只给"人在真终端里"那条路**）。

    🔴 先过 `_no_open_decision()`：自动化（自检／验收／CI／无 TTY）走到这里一律**不开**，只打印
    地址。这条闸放在**函数自身**里 ⇒ 任何调用方漏传 `--no-open` 也开不了。
    """
    if _no_open_decision()[0]:
        return False, None
    for cmd in (["open", url], ["xdg-open", url]):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if p.returncode == 0:
                return True, cmd[0]
        except (OSError, subprocess.SubprocessError):
            continue
    return False, None


def step_login_plan(ctx, src=None):
    """只读的计划：本机有没有会话（**不联网**；真校验留到执行/自检那一步）。"""
    from .. import authgate
    sess = authgate.local_session()
    has = bool(sess.get("hasToken"))
    blocked, why = _no_open_decision(bool(ctx.get("no-open")))
    return {
        "步": "④ 起登录（浏览器授权登录）",
        "结论": "待执行（本机已有会话文件，将先做一次只读校验）" if has else "待执行（本机没有会话）",
        "本机有没有会话": has,
        "会话文件": sess.get("sessionFile"),
        "登录页": _login_page_url(),
        "打开方式": ("**不打开浏览器**（%s）—— 只打印登录页地址" % why if blocked
                     else "将调用系统默认浏览器打开登录页（只有**人在真终端里、且没关掉它**才会开）"),
        "回读形态": ("交互式粘贴会话值（当前终端是 TTY）"
                     if sys.stdin.isatty() or ctx.get("session-cookie-stdin")
                     else "非交互式终端 ⇒ **不阻塞**：打印登录页与下一步命令"),
        "会给出一条现成命令": LOGIN_HINT,
        "🔴 不向用户索要账号密码": "账号密码**只在 Daniel 页面上输入**；CLI 只接收浏览器里的会话值",
        "🔴 自动化不许弹窗": "环境变量 `DANIEL_NO_OPEN`／`--no-open`／非交互终端，三条任一命中即"
                            "**不调起系统浏览器**（判据只有一处：`commands/mod_account.no_open_decision`）",
        "无头／CI 形态": "把浏览器里的会话用管道喂进来：`daniel install --confirm "
                         "--session-cookie-stdin < 值文件`（等价于 account login 的同名开关）",
    }


def _inner_browser_login(ctx, src, use_stdin, no_open=True):
    """**复用 `account login --browser`**（不重造登录链）：在进程内调它，输出收进内存。

    为什么在进程内调而不是开子进程：它要**读这个终端的 stdin**（粘贴会话值），开子进程会把
    交互两截化；这里给它一个写到内存的 Emitter，于是向导的 stdout 仍然只有**一份** JSON。

    `no_open` **默认 True**（🔴 自动化不许弹窗）：内层登录路只有在调用方**明确**说"人在真终端里、
    可以开"时才会去调系统浏览器。默认值的取向就是"宁可不开"。
    """
    from ..commands.mod_account import WRITE_HANDLERS
    handler = WRITE_HANDLERS["login"]
    args = argparse.Namespace(confirm=True, dry_run=False, browser=True,
                              session_cookie_stdin=bool(use_stdin),
                              no_open=bool(no_open), verbose=ctx.verbose, json=True)
    buf = io.StringIO()
    em = Emitter(json_mode=True, quiet=False, out=buf, err=ctx.emitter.err)
    ictx = Context(args, em, module="account", command="login", read_only=False)
    code = handler(ictx)
    doc = None
    try:
        doc = json.loads(buf.getvalue() or "")
    except ValueError:
        doc = None
    return code, doc


def step_login_apply(ctx, src):
    """**向导的最后一步**：起登录 → 回读 → 再跑一次 `auth status` 确认（不假称完成）。"""
    from .. import authgate
    code0, doc0 = _installed_json(ctx, ["auth", "status"], timeout=120)
    if code0 == EXIT_OK:
        srv = ((doc0 or {}).get("data") or {}).get("server") or {}
        return {"步": "④ 起登录（浏览器授权登录）", "结论": "已完成",
                "方式": "本机已有有效会话：一次只读校验通过（没有重新登录，也没有写任何文件）",
                "账号(掩码)": srv.get("账号(掩码)"), "auth status 退出码": code0,
                "登录页": _login_page_url(),
                "下一步": "已经可以用了：`daniel brands list --json` 是真取数的那一条"}
    if code0 == 2:
        return {"步": "④ 起登录（浏览器授权登录）", "结论": "不适用（服务端不可达）",
                "方式": "本机会话没有被判失效 —— 这是网络／服务端问题，**不要重新登录**",
                "auth status 退出码": code0,
                "下一步": "过一会儿重试：`daniel auth status`（退出码 2 ⇒ 稍后重试）",
                "一行修法": "daniel auth status"}

    url = _login_page_url()
    interactive = sys.stdin.isatty()                       # 🔴 只有**真人交互终端**才可能开浏览器
    tty = interactive or bool(ctx.get("session-cookie-stdin"))
    # 🔴 2026-10-16 事故修复（总监直修 · 见 TICKET-195）：**自动化路径绝不许弹真窗口**。
    #    上一版只要没给 `--no-open` 就调系统浏览器 ⇒ 验收驱动反复跑 `install --confirm`
    #    时，用户桌面上被反复弹出 Daniel 登录页。现在判据**只有一处** `_no_open_decision()`：
    #      ① 显式 `--no-open`；② 环境变量 `DANIEL_NO_OPEN`；③ **stdin 不是交互终端**
    #    （脚本／Agent／CI／管道喂会话值都属于这一类，它们本来也无法交互）。
    blocked, why = _no_open_decision(bool(ctx.get("no-open")))
    opened = None
    if not blocked:
        opened, how = _open_browser(url)
        if opened:
            ctx.emitter.note("已用 `%s` 打开 Daniel 登录页。" % how)
    else:
        ctx.emitter.note("**不打开浏览器**：%s。登录页地址：%s" % (why, url))
    if not tty:
        return {
            "步": "④ 起登录（浏览器授权登录）", "结论": "未完成（当前不是交互式终端，按约定不阻塞）",
            "登录页": url, "浏览器已打开": bool(opened), "没有打开浏览器的原因": why,
            "方式": "打印登录页 URL ＋ 下一步命令（无 TTY 时不等待粘贴、也不弹窗）",
            "下一步命令": LOGIN_HINT,
            "一行修法": LOGIN_HINT,
            "无头／CI 形态": "把浏览器里的会话用管道喂进来：`daniel account login --browser "
                             "--confirm --session-cookie-stdin < 值文件`（或在向导里加同名开关）",
        }
    inner_code, inner_doc = _inner_browser_login(ctx, src, bool(ctx.get("session-cookie-stdin")),
                                                 no_open=blocked)
    data = (inner_doc or {}).get("data") or {}
    rb = data.get("readback") or {}
    detail = data.get("detail") or {}
    if inner_code == EXIT_OK and rb.get("verified"):
        code1, doc1 = _installed_json(ctx, ["auth", "status"], timeout=120)
        srv = ((doc1 or {}).get("data") or {}).get("server") or {}
        return {"步": "④ 起登录（浏览器授权登录）", "结论": "已完成" if code1 == 0 else "未完成",
                "方式": "浏览器授权登录：登录页 → 你在页面上登录 → 会话回读 → **先校验后落盘**",
                "登录页": url, "浏览器已打开": bool(opened),
                "账号(掩码)": detail.get("账号(掩码)") or srv.get("账号(掩码)"),
                "会话文件": ((rb.get("detail") or {}).get("会话文件")),
                "auth status 退出码": code1,
                "一行修法": None if code1 == 0 else "daniel auth status",
                "下一步": "已经可以用了：`daniel brands list --json` 是真取数的那一条"}
    reason = (rb.get("reason") or ((inner_doc or {}).get("error") or {}).get("message")
              or "登录没有完成")
    return {"步": "④ 起登录（浏览器授权登录）", "结论": "未完成",
            "方式": "浏览器授权登录没有走完（会话没读到／没通过校验）",
            "登录页": url, "浏览器已打开": bool(opened),
            "原因": reason, "login 退出码": inner_code,
            "下一步命令": LOGIN_HINT, "一行修法": LOGIN_HINT}


# ═══════════════════════ 编排：四步 ═══════════════════════
def wizard_plan(ctx):
    """干跑（默认）：把四步**将要做什么**逐条算出来，**不写任何文件**。"""
    src = source_mod.resolve(ctx.get("from"))
    steps = [step_cli_plan(ctx, src), step_skills_plan(ctx, src),
             step_connect_plan(ctx, src), step_login_plan(ctx, src)]
    keys, why = hosts_to_apply(ctx)
    return {
        "targetName": "本机安装落点（入口 ＋ 能力束 ＋ 宿主配置 ＋ 登录）",
        "impact": "四步都只动**本机**：① 一个入口软链 ＋ 一行 PATH 配置；② 8 条技能软链；"
                  "③ 宿主配置里本产品那一条（经 `connect`，幂等、写前落快照）；"
                  "④ 打开 Daniel 登录页并在页面上登录后落地会话文件（权限 600）。"
                  "**不改任何宿主配置的其它内容、不改 Daniel 侧任何数据、不触发任何采集、"
                  "不向你要账号密码。**",
        "包从哪来": {k: src[k] for k in ("渠道", "包根", "仓库根", "入口", "语料根",
                                         "能力域数", "来源说明")},
        "分发渠道的缝": src["将来换渠道只换哪里"],
        "四步": {s["步"]: s for s in steps},
        "要接入的宿主": keys,
        "宿主选择理由": why,
        "幂等": "四步都可重复跑：已经是目标状态的一律不改文件",
        "回滚": "写前把原文落进 %s；宿主那一条用 `daniel connect --host <宿主> --uninstall --confirm` 撤"
                % os.path.join(install_root(), "snapshots"),
        "复核命令": ["daniel install --check", "daniel auth status", "daniel connect --doctor"],
        "装完会自动复核": "四步跑完**同一条命令里**自动跑一次只读复核（与 `daniel install --check` "
                          "同源：入口能跑／8 束完整且与包内逐字一致／接入通不通／登录态），"
                          "四步结论与复核四项结论打在输出末尾 —— **不需要再输入任何命令**；"
                          "`daniel install --check` 仍保留，供随时重跑",
        "包内不含任何凭据": "入口与能力束都是软链，不复制任何东西；凭据只会落在系统钥匙串或数据落点的会话文件里",
    }


def wizard_run(ctx, plan):
    """真执行：四步逐个落地 ＋ 逐个回读对账 ＋ **装完自动复核**，并落一份安装台账。"""
    stamp = now_stamp()
    snapbox = {"stamp": stamp, "dir": None}
    src = source_mod.resolve(ctx.get("from"))
    s1 = step_cli_apply(ctx, src, snapbox)
    ctx.progress(s1["步"] + "：" + s1["结论"])
    s2 = step_skills_apply(ctx, src, snapbox)
    ctx.progress(s2["步"] + "：" + s2["结论"])
    keys, why = hosts_to_apply(ctx)
    if keys:
        s3 = step_connect_apply(ctx, src, keys)
    else:
        p3 = step_connect_plan(ctx, src)
        s3 = {"步": p3["步"], "结论": p3["结论"], "原因": p3["原因"], "逐宿主": [],
              "回读": {"verified": True, "reason": None, "不适用": p3["原因"]},
              "下一步": p3["什么时候需要它"]}
    ctx.progress(s3["步"] + "：" + s3["结论"])
    s4 = step_login_apply(ctx, src)
    ctx.progress(s4["步"] + "：" + s4["结论"])
    steps = [s1, s2, s3, s4]

    # ⑤ **装完自动复核**（TICKET-206）：四步之后同一进程内跑一次只读复核（与 `install --check`
    #    同源）。它只读、不写，因此四步的写行为与三重闸语义**一律不动**；用户不必再敲任何命令。
    review = auto_review(ctx, steps)

    writes_ok = all(s.get("回读", {}).get("verified", True) for s in steps[:3])
    logged_in = s4["结论"] in ("已完成",)
    login_na = s4["结论"].startswith("不适用")
    if not logged_in and not login_na:
        ctx.note("装好了（① ② ③ 已完成），但**还差登录这一步**：%s" % NEXT_STEP_TEXT)

    reasons = []
    if not writes_ok:
        reasons.append("有步骤的回读对账未通过：" + "；".join(
            s["回读"].get("reason") or s["步"] for s in steps[:3]
            if not s.get("回读", {}).get("verified", True)))
    if not logged_in and not login_na:
        reasons.append("向导要求**完成后处于已登录状态**，但现在还不是：" + NEXT_STEP_TEXT)
    if not review["通过"] and not reasons:
        # 🔴 "装完了但复核有项没过"**不许静默 exit 0**（与四步回读不过同一个口径）。
        reasons.append("装完自动复核有项没过：" + (review["一行修法"] or review["结论"]))

    verified = not reasons
    state = {
        "时间": stamp, "包根": src["包根"], "仓库根": src["仓库根"], "入口": s1["入口"],
        "技能目录": s2["技能目录"], "宿主": keys, "快照目录": snapbox["dir"],
        "四步": [{"步": s["步"], "结论": s["结论"]} for s in steps],
        "登录": {"已登录": logged_in, "auth status 退出码": s4.get("auth status 退出码")},
        "装完复核": {"通过": review["通过"], "结论": review["结论"]},
        "从哪份包装": src["来源说明"],
    }
    try:
        if not os.path.isdir(install_root()):
            os.makedirs(install_root())
        with io.open(state_path(), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(state, ensure_ascii=False, indent=1) + "\n")
    except (IOError, OSError) as e:
        ctx.warn("安装台账没写进去（不影响已落地的安装）：%s" % e)

    _print_tail_later(ctx, review_lines(review))
    return {
        "mutation": {"包根": src["包根"], "入口": s1["入口"], "技能目录": s2["技能目录"],
                     "宿主": keys, "快照目录": snapbox["dir"], "安装台账": state_path(),
                     "四步结论": {s["步"]: s["结论"] for s in steps},
                     "复核四项": {i.get("项"): ("通过" if i.get("通过") else "未通过")
                                  for i in (review["回读"] or {}).get("逐项") or []}},
        "readback": {"verified": verified,
                     "reason": "；".join(reasons) or None,
                     "detail": {"四步逐条": steps, "未完成项": reasons or "无",
                                "装完复核": review}},
        "rolledBack": None,
        "rollbackNote": _rollback_note(s1, s2, keys, snapbox["dir"]),
    }


def _rollback_note(s1, s2, keys, snap_dir):
    """逐条回滚说明（**必须与"这次到底改了什么"一致**，不许给一句含糊的话）。

    `snap_dir` 为空有两种可能，说法完全不同：① 这次**没改**这个文件 ⇒「没有改动，也没有快照」；
    ② 这个文件**这次是新建的**（此前不存在，没有原文可留）⇒「删掉它即还原」。混为一谈就是假话。
    """
    changed_rc = any(str(s1.get("PATH 配置文件")) in str(c) for c in (s1.get("改动") or []))
    if snap_dir:
        rc_tail = "，或从快照还原 %s" % os.path.join(
            snap_dir, os.path.basename(s1["PATH 配置文件"]) + ".orig")
    elif changed_rc:
        rc_tail = "（这个文件本次是**新建**的：此前不存在，所以没有原文快照；删掉那一行即还原）"
    else:
        rc_tail = "（本次没有改动它 ⇒ 也没有快照）"
    lines = ["要撤掉这次安装（三步各一条，互不影响）：",
             "  · 卸命令行：rm -f %s（并删掉 %s 里那一行 %s%s）"
             % (s1["入口"], s1["PATH 配置文件"], s1["PATH 行"], rc_tail),
             "  · 卸能力束：rm -f %s/kol-*（只删这 8 个）" % s2["技能目录"]]
    for k in keys:
        lines.append("  · 卸 %s 接入：daniel connect --host %s --uninstall --confirm" % (k, k))
    lines.append("  · 本次写前的原文快照：%s"
                 % (snap_dir or "（本次没有改动任何文件，因此没有落快照）"))
    return "\n".join(lines)


# ═══════════════════════ `install --check`：装完自检（只读） ═══════════════════════
def _check_cli(ctx, src):
    bin_dir = _bin_dir(ctx)
    entry = os.path.join(bin_dir, "daniel")
    st = _entry_link_state(entry, src["入口"])
    code, out, err = _run([entry, "--version"], timeout=120)
    how = "直接执行入口"
    if code != 0:
        code, out, err = _run([hosts.interpreter(), entry, "--version"], timeout=120)
        how = "用 %s 执行入口" % hosts.interpreter()
    ok = bool(st["一致"]) and code == 0
    return {"项": "① 装 CLI（入口进 PATH）", "通过": ok,
            "证据": "入口 %s ⇒ %s ｜ 跑 `--version`（%s）→ %s"
                    % (entry, st["当前指向"] or "（入口不存在）", how,
                       (out or err or "").strip().splitlines()[-1:] or ["退出码 %s" % code]),
            "修法": None if ok else "daniel install --confirm（幂等，会补齐入口与 PATH 行）"}


def _check_skills(ctx, src):
    """② 8 束能力束：按**随包的固定 8 个名字**（`SKILL_NAMES`）逐束判，缺一束即不通过。

    为什么按固定的 8 个名字判、而不是"包里现在有几个就判几个"：复核要回答的是
    「**8 束**是否完整」——按包里现有的清单判，包里少一束就会变成"7/7 全对"，那正是
    "看着全绿、实际少一束"的假绿（TICKET-206 的反控就是打这一条）。
    同时区分两种红，因为**修法不一样**：包内缺这一束（重装补不回来，要从包里补回）
    ／软链或正文本符（`install --confirm` 幂等重跑就能改指回来）。
    """
    skills_dir = _skills_dir(ctx)
    rows, bad, pkg_missing, fixable = [], [], [], []
    for name in SKILL_NAMES:
        want = source_mod.skill_source(src, name)
        dst = os.path.join(skills_dir, name)
        in_pkg = os.path.isfile(os.path.join(want, "SKILL.md"))
        ok_link = os.path.islink(dst) and _norm(dst) == _norm(want)
        same = None
        if in_pkg and os.path.isfile(os.path.join(dst, "SKILL.md")):
            same = (_sha256_file(os.path.join(dst, "SKILL.md")) ==
                    _sha256_file(os.path.join(want, "SKILL.md")))
        good = bool(ok_link and same)
        if not good:
            bad.append(name)
            (fixable if in_pkg else pkg_missing).append(name)
        rows.append("%s%s" % (name, ("（包内缺这一束）" if not in_pkg
                                     else ("" if good else "（不符）"))))
    # ── 云同步冲突副本检测（TICKET-211）─────────────────────────────
    # 触发场景：技能目录位于 **iCloud／云盘同步目录**（如 `~/Desktop` 被 iCloud 接管）时，
    # 同步服务会给"同目录同名"的新建条目追加 ` 2`／` 3` 后缀，于是 agent 眼里这 8 束**不存在**。
    # 判据：技能目录里出现 `<某个需求束名> <数字>` 形态的条目 ⇒ 报红并给出两条修法。
    strays = []
    try:
        for entry in sorted(os.listdir(skills_dir)):
            m = re.match(r"^(%s) \d+$" % "|".join(re.escape(n) for n in SKILL_NAMES), entry)
            if m:
                strays.append(entry)
    except OSError:
        strays = []
    ok_all = not bad and not strays
    if strays:
        fix = ("检测到 %d 个疑似**云同步冲突副本**条目（%s）：① 先删掉这些副本；"
               "② 把技能目录移出云同步目录（iCloud／OneDrive 等）后重跑 `daniel install --confirm`；"
               "原因：同步服务会给同名新条目追加 ` 2` 后缀，导致 agent 读不到该束"
               % (len(strays), "、".join(strays)))
    elif ok_all:
        fix = None
    elif pkg_missing:
        fix = ("包内少了这几束：%s ⇒ 这不是安装的问题：从完整的包里把这几束补回"
               "（或重新取一份完整的包）后再跑 `daniel install --confirm`" % "、".join(pkg_missing))
    else:
        fix = "daniel install --confirm（幂等，会把不符的软链改指回来）"
    return {"项": "② 装能力束（8 束 kol-* 软链完整且指向这份包）", "通过": ok_all,
            "证据": "落点 %s ｜ %d/%d 束一致（%s）｜ 8 束里包内有 %d 束%s"
                    % (skills_dir, len(SKILL_NAMES) - len(bad), len(SKILL_NAMES),
                       "、".join(rows), len(SKILL_NAMES) - len(pkg_missing),
                       ("｜**疑似云同步冲突副本 %d 个：%s**" % (len(strays), "、".join(strays))
                        if strays else "")),
            "缺束": pkg_missing or None,
            "修法": fix}


def _check_connect(ctx, src, keys):
    """③ 接入：复用 `connect --doctor`。

    **一次跑完全部宿主**（`--doctor` 不带 `--host`）：doctor 的 ①②③④（包完整性／server 起得来／
    工具数／只读命令取到真实数据）是**所有宿主共享**的断言，按宿主各跑一遍等于把同一组断言
    （含一次联网只读）重复 N 遍 —— 实测两个宿主 2×10s。这里跑一遍、按 `⑤ 宿主 <名字>` 那一项
    逐宿主取证，判据与结论**都不变**，只是不再重复劳动（TICKET-206：自动复核不许让 install 变慢）。
    """
    if not keys:
        return {"项": "③ 写宿主接入（复用 connect --doctor）",
                "通过": True, "不适用": "本机未检测到任何宿主（Cursor／Codex 都没装）",
                "证据": "没有可检查的宿主 ⇒ 本项按**不适用**处理（不是通过，也不是失败）",
                "修法": "装上宿主后：daniel install --host cursor --confirm"}
    prefix = _install_prefix(ctx)
    code, doc = _check_doctor(prefix)
    data = (doc or {}).get("data") or {}
    items = data.get("检查项") or []
    shared_bad = [i for i in items
                  if not i.get("通过") and not str(i.get("项") or "").startswith("⑤")]
    rows, bad, fixes = [], [], {}
    for k in keys:
        mine = [i for i in items if str(i.get("项") or "").startswith("⑤ 宿主 %s" % k)]
        fails = [i for i in (mine + shared_bad) if not i.get("通过")]
        ok = bool(mine) and not fails
        detail = "；".join(str(i.get("证据", "")) for i in fails) or (
            (mine[0].get("证据") if mine else "") or data.get("结论") or "取不到 doctor 输出")
        rows.append("%s → 退出码 %s ｜ %s" % (k, code, str(detail)[:200]))
        if not ok:
            bad.append(k)
            fixes[k] = (fails[0].get("修法") if fails else None)
    ok_all = not bad
    return {"项": "③ 写宿主接入（复用 connect --doctor）", "通过": ok_all,
            "证据": "；".join(rows),
            "修法": None if ok_all else (
                fixes.get(bad[0]) or "daniel connect --host %s --apply --confirm" % bad[0])}


def _check_doctor(prefix, key=None):
    argv = ["connect", "--doctor", "--json"] + (["--host", key] if key else [])
    code, out, err = _run(prefix + argv, timeout=900)
    try:
        return code, json.loads(out or "")
    except ValueError:
        return code, None


def _check_login(ctx):
    from .. import authgate
    st = authgate.status()
    code = st.get("exitCode")
    ok = code == EXIT_OK
    fix = {"去登录": LOGIN_HINT, "稍后重试": "daniel auth status（服务端不可达 ⇒ 过一会儿重试）"}.get(
        st.get("reason"), "daniel auth status")
    return {"项": "④ 登录态（auth status 三档：0 通过／1 去登录／2 服务端不可达）", "通过": ok,
            "证据": "登录状态：%s ｜ 退出码 %s ｜ 账号(掩码) %s ｜ %s"
                    % (st.get("reason"), code,
                       ((st.get("server") or {}).get("账号(掩码)") or "（未登录）"),
                       (st.get("next") or "").strip()),
            "修法": None if ok else fix,
            "exitCode": code}


def check_all(ctx):
    """`install --check` 的四项（① 装 CLI ② 能力束 ③ 接入 ④ 登录态）→ 全绿 exit 0。"""
    src = source_mod.resolve(ctx.get("from"))
    state = read_state()
    keys, why = hosts_to_apply(ctx)
    if not keys and state.get("宿主"):
        keys, why = [k for k in state["宿主"] if k in hosts.host_keys()], "安装台账里记的宿主"
    items = [_check_cli(ctx, src), _check_skills(ctx, src), _check_connect(ctx, src, keys),
             _check_login(ctx)]
    failed = [i for i in items if not i["通过"]]
    code = EXIT_OK if not failed else (failed[0].get("exitCode") or EXIT_INTERNAL)
    return {
        "通过": not failed,
        "检查项": items,
        "结论": ("全部通过：装好了，可以正常用（%d 项）" % len(items)) if not failed else
                "未通过：%d 项 —— 一行修法：%s" % (len(failed), failed[0]["修法"]),
        "一行修法": None if not failed else failed[0]["修法"],
        "包从哪来": {k: src[k] for k in ("渠道", "包根", "来源说明")},
        "宿主": keys, "宿主选择理由": why,
    }, code


# ═════════════════ 四步之后：**装完自动复核**（TICKET-206 · 只读，一条指令闭环） ═════════════════
#: 复核块的标题（人读输出与 `--json` 里同一个说法）
REVIEW_TITLE = "装完自动复核（与 `daniel install --check` 同源）"

#: 末尾结论块只在**人读模式**挂（`--json` 时 stdout 必须只有一个 JSON 文档）
_TAIL_BLOCKS = []


def _step_fix(step):
    """四步里某一步"没完成"时的**一行修法**（已完成 ⇒ None，不硬凑一句废话）。"""
    if not step:
        return None
    if str(step.get("结论") or "").startswith("已完成"):
        return None
    for key in ("一行修法", "下一步命令", "下一步"):
        if step.get(key):
            return step[key]
    return None


def auto_review(ctx, steps):
    """四步跑完之后**同一进程内**跑一次只读复核 —— 与 `daniel install --check` **完全同源**。

    为什么直接调 `check_all()` 而不是"另写一套复核"：`install --check` 那四项就是本产品的
    判据真源（入口能跑／8 束完整且与包内逐字一致／接入通不通／登录态）。抄一份出来 = 两处判据，
    迟早漂移 —— 漂移的代价是"用户看到的绿"和"真实状态"不一致。所以这里**只调用、不重写**：
    `check_all` 跑的也都是只读命令（`--version`／读软链与指纹／`connect --doctor`／`auth status`），
    **不重跑登录、不向 Daniel 写任何东西**。

    返回的这块同时喂三个出口：① 人读输出的末尾结论块；② `readback.detail["装完复核"]`（`--json`
    的结构化复核段）；③ 安装台账里的一行结论。
    """
    ctx.progress("装完自动复核（与 `daniel install --check` 同源：只读本机，不重跑登录）")
    report, code = check_all(ctx)
    items = report.get("检查项") or []
    four = [{"步": s.get("步"), "结论": s.get("结论"), "一行修法": _step_fix(s)} for s in steps]
    failed = [i for i in items if not i.get("通过")]
    ok = bool(report.get("通过")) and not failed
    fix = None
    if failed:
        fix = failed[0].get("修法")
    return {
        "项": REVIEW_TITLE,
        "只读": True,
        "同源": ("直接调用 `install --check` 的同一套判据函数（`install/wizard.py::check_all`）："
                 "不另写一套复核，也不重跑登录／不新增联网断言"),
        "四步": four,
        "回读": {"verified": ok,
                 "reason": None if ok else "复核 %d 项没过：%s" % (
                     len(failed), "；".join(str(i.get("项")) for i in failed)),
                 "逐项": items},
        "通过": ok,
        "结论": ("装好了，可以正常用：四步 ＋ 复核四项全绿（不需要再输入任何命令）" if ok else
                 "装完了，但复核有 %d 项没过 —— 一行修法：%s" % (len(failed), fix)),
        "一行修法": None if ok else fix,
        "复核自身退出码": code,
        "复核命令": ["daniel install --check", "daniel connect --doctor", "daniel auth status"],
        "下一步": ("已经可以用了：`daniel brands list --json` 是真取数的那一条" if ok else
                   "按上面那一行修法处理后，随时可重跑 `daniel install --check` 复核"),
    }


def review_lines(review):
    """复核块 → 给人看的**末尾结论块**（用户不需要再敲任何命令就知道装没装好）。"""
    mark = "通过" if review.get("通过") else "未通过"
    lines = ["", "════════ %s ════════" % REVIEW_TITLE, "四步结论："]
    for r in review.get("四步") or []:
        lines.append("  %s → %s" % (r.get("步"), r.get("结论")))
        if r.get("一行修法"):
            lines.append("      一行修法：%s" % r["一行修法"])
    lines.append("复核四项：")
    for i in (review.get("回读") or {}).get("逐项") or []:
        lines.append("  %s → %s" % (i.get("项"), "通过" if i.get("通过") else "未通过"))
        ev = " ".join(str(i.get("证据") or "").split())
        if len(ev) > 240:
            ev = ev[:240] + "…（全量见 --json 的 readback.detail.装完复核）"
        if ev:
            lines.append("      证据：%s" % ev)
        if i.get("不适用"):
            lines.append("      注：%s" % i["不适用"])
        if not i.get("通过") and i.get("修法"):
            lines.append("      一行修法：%s" % i["修法"])
    lines.append("结论：%s" % review.get("结论"))
    if review.get("通过"):
        lines.append("（一条指令闭环：不需要再输入任何命令；想随时复核仍可跑 "
                     "`daniel install --check`）")
    return lines


def _print_tail_later(ctx, lines):
    """把末尾结论块挂到**进程退出**时打印。

    为什么必须挂退出钩子：`install` 的 stdout 分两段 —— 本函数执行时写不了"最后一行"，真正的
    数据转储由写链（`commands/_common.gated_write` → `emit_raw`）在 `wizard_run` **返回之后**
    才打印。要让"四步结论 ＋ 复核四项结论"成为用户看到的**最后一块**，只能在数据转储之后打印。
    只在人读模式挂：`--json` 时 stdout 必须只有一个 JSON 文档（机器读的那份里，复核段在
    `readback.detail["装完复核"]`）。
    """
    if getattr(ctx, "json_mode", False):
        return
    text = "\n".join(lines) + "\n"

    def _flush():
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except (IOError, OSError, ValueError):          # 输出口已关闭：不因"打不出来"改变退出码
            pass

    _TAIL_BLOCKS.append(text)
    atexit.register(_flush)


# ═══════════════════════ `install --upgrade`：就地升级 ＋ 重跑自检 ═══════════════════════
def upgrade_plan(ctx):
    src = source_mod.resolve(ctx.get("from"))
    state = read_state()
    old = state.get("包根")
    same = bool(old) and _norm(old) == _norm(src["包根"])
    return {
        "targetName": "把本机安装就地指向另一份包，并**重跑自检**",
        "impact": ("入口软链与 8 束技能软链改指到 %s，宿主配置经 `connect --apply --confirm` 刷新"
                   "（只动本产品那一条）；随后**自动跑一遍 `install --check`** 并把它的结论作为"
                   "本次升级的结果（不过就非零退出）。" % src["包根"]),
        "从哪升到哪": {"升级前（台账）": old, "升级到": src["包根"],
                       "结论": "两份是同一个包 ⇒ 本次是幂等复核（不改任何文件）" if same
                               else "会改指到新的包"},
        "复用 connect": "宿主那一份仍由 `connect` 写（快照 ＋ 回读对账 ＋ 审计）",
        "npm 形态下这条命令是什么": "`npm i -g <包>@latest` ＋ 同一条自检 —— 四步与用户命令逐字不变",
        "复核命令": ["daniel install --check"],
    }


def upgrade_run(ctx, plan):
    """升级 ＝ 四步（改指到新包）＋ **装完自动复核**。

    复核只跑一次：`wizard_run` 里已经跑过一遍（TICKET-206），这里**直接复用**那一份结果，
    不再调一次 `check_all` —— 升级后的自检与 `install --check` 是同一套判据，跑两遍只是把同一组
    断言（含一次联网只读）重复一遍（TICKET-206：不许让命令变慢）。
    """
    out = wizard_run(ctx, plan)
    detail = out["readback"]["detail"]
    review = detail.get("装完复核") or {}
    report = {"通过": bool(review.get("通过")),
              "结论": review.get("结论"),
              "检查项": (review.get("回读") or {}).get("逐项") or [],
              "一行修法": review.get("一行修法")}
    code = EXIT_OK if report["通过"] else EXIT_INTERNAL
    out["mutation"]["升级后自检"] = {"通过": report["通过"], "结论": report["结论"]}
    out["readback"] = {"verified": bool(out["readback"]["verified"]) and report["通过"],
                       "reason": out["readback"]["reason"] or (
                           None if report["通过"] else (report["一行修法"] or report["结论"])),
                       "detail": {"安装四步": detail, "升级后自检": report}}
    out["exitCodeHint"] = code
    return out


__all__ = ["SKILL_NAMES", "LOGIN_HINT", "NEXT_STEP_TEXT", "data_home", "install_root",
           "state_path", "read_state", "wizard_plan", "wizard_run", "check_all",
           "upgrade_plan", "upgrade_run", "hosts_to_apply", "step_login_plan"]
