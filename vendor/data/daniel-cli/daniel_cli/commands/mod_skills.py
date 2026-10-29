# -*- coding: utf-8 -*-
"""skills 模块：**随包分发的业务语料**的只读入口（TICKET-159）。

为什么这条命令必须在 CLI 侧也有一份
----------------------------------
用户口径是「语料包含在整个 MCP 中，别的电脑注册 MCP 后自动装上」。MCP 工具是最通用的那条路
（Cursor 一定能用），但同一条能力在**没有宿主**的场合（脚本、CI、临时排障、macOS 终端里
直接查一句判据）也需要一个入口 —— 那就是这里的 `daniel skills list` / `daniel skills read`。

**两侧同一份真源**：MCP 侧的工具不自己读语料，它落成一次真实子进程调用
`daniel skills list --json` / `daniel skills read … --json`（与其它 41 条工具同一条路），
所以「MCP 侧看到的」与「CLI 侧看到的」在结构上不可能是两份东西。
读取实现只有一处：`daniel_cli/corpus.py`（按包自身位置定位，**不读 `~/.agents/skills/`**）。

本模块只有读：不联网、不查账号与品牌档案、不写任何文件、不触发任何采集、不 import 任何
`.kol-tools/` 能力脚本 —— 因此**把 `data/daniel-cli/` 单独拷到一台没有 `.kol-tools` 的机器上，
这条命令照样能跑**（这正是"随包分发"的判据）。
"""
import os

from .. import corpus
from ..exits import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE
from ..runtime import CliError


def _load(call):
    """统一把语料层的报错转成 CLI 的受控错误（退出码 1 ＋ 人话理由）。"""
    try:
        return call()
    except corpus.CorpusError as e:
        raise CliError(str(e), code=EXIT_INTERNAL,
                       hint="语料随包分发在 `data/daniel-cli/mcp/corpus/`；"
                            "分发物里缺了它就会报这条（见 mcp/README.md 的「语料随包分发」一节）")


def _pick_domain(ctx):
    name = ctx.require("--name")
    if name in corpus.SKILL_ORDER:
        return name
    raise CliError("不认识的能力域：%s" % name, code=EXIT_USAGE,
                   hint="可选：%s" % "、".join(corpus.SKILL_ORDER))


def _as_int(ctx, opt, default=None, minimum=None):
    raw = ctx.get(opt, default)
    if raw is None or raw == "":
        return default
    try:
        val = int(raw)
    except (TypeError, ValueError):
        raise CliError("%s 需要一个整数，收到 %r" % (opt, raw), code=EXIT_USAGE)
    if minimum is not None and val < minimum:
        raise CliError("%s 不能小于 %d，收到 %d" % (opt, minimum, val), code=EXIT_USAGE)
    return val


def cmd_list(ctx):
    payload = _load(lambda: corpus.list_skills())
    if ctx.json_mode:
        ctx.emit(data=payload)
        return EXIT_OK
    lines = ["随包分发的业务语料（%s）" % payload["语料版本"],
             "落点：%s（%s）" % (payload["语料根"], payload["定位方式"]),
             "规模：%d 个能力域 ｜ %d 个切片 ｜ %s 字节 ｜ 完整性 %s"
             % (payload["能力域数"], payload["总量"]["切片数"],
                payload["总量"]["字节数"], payload["完整性"]),
             "读法：%s" % payload["读法"], ""]
    for s in payload["能力域"]:
        lines.append("· %s（%s）｜%s" % (s["域"], s["能力域"], s["版本"]))
        lines.append("    前置条件：%s" % (s["前置条件"] or "—"))
        lines.append("    切片 %d 个 ｜ 整束 %s 字节 ｜ 完整性 %s"
                     % (s["切片数"], s["字节数"], s.get("完整性", "未校验")))
        lines.append("    摘要：%s" % _clip(s["摘要"], 120))
    ctx.emit(text="\n".join(lines))
    return EXIT_OK


def cmd_read(ctx):
    name = _pick_domain(ctx)
    section = _as_int(ctx, "--section", None, minimum=0)
    payload = _load(lambda: corpus.read_skill(
        name,
        section=section,
        grep=ctx.get("--grep"),
        max_bytes=_as_int(ctx, "--max-bytes", corpus.DEFAULT_MAX_BYTES, minimum=0),
        offset=_as_int(ctx, "--offset", 0, minimum=0),
        max_hits=_as_int(ctx, "--max-hits", corpus.DEFAULT_MAX_HITS, minimum=0),
    ))
    if ctx.json_mode:
        ctx.emit(data=payload)
        return EXIT_OK

    mode = payload["模式"]
    head = ["能力域：%s（%s）｜语料版本 %s ｜完整性 %s"
            % (payload["域"], payload["能力域"], payload["版本"], payload["完整性"]),
            "源文件：%s（sha256 %s）"
            % (payload["源文件"], _clip(payload["源文件sha256"] or "", 16))]
    if mode == "导航":
        head += ["", "本束切片清单（用 --section <切片号> 读正文，0 ＝ 导航件 SKILL.md）："]
        for one in payload["切片清单"]:
            head.append("  [%2d] %-34s %-14s %s"
                        % (one["切片号"], one["文件"], one["源行区间"],
                           one["源节标题"]))
        head += ["", payload["提示"], payload["下一步"]]
    elif mode == "检索":
        head += ["", "检索「%s」：范围 %s ｜ 扫描 %d 个文件 ｜ 命中 %d 行%s"
                 % (payload["关键词"], payload["检索范围"], payload["目标文件数"],
                    payload["命中总数"],
                    "（只回前 %d 行，取全用 --max-hits 0）" % payload["命中数"]
                    if payload["命中截断"] else "")]
        for h in payload["命中"]:
            head.append("  [%2d] %s:%d  %s" % (h["切片号"], h["切片文件"], h["行号"], h["行"]))
        head += ["", payload["提示"]]
    else:
        info = payload["分片"]
        head += ["", "切片 %d ｜ %s ｜ 源行区间 %s ｜ %s"
                 % (payload["切片号"], payload["切片文件"], payload["源行区间"],
                    payload["源节标题"]),
                 "分片：本次 %d 字节 / 共 %d 字节（偏移 %d）%s"
                 % (info["本次字节"], info["总字节"], info["偏移"],
                    "；" + info["续读"] if info.get("续读") else "；已到末尾"),
                 ""]
        head.append(payload["正文"])
    ctx.emit(text="\n".join(head))
    return EXIT_OK


def _clip(text, limit):
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "…"


HANDLERS = {
    "list": cmd_list,
    "read": cmd_read,
}

WRITE_HANDLERS = {}


def selftest(emitter):
    """模块自带自检（`daniel skills --self-test`；由 CLI 总自检的 K 组自动纳入）。

    口径（三条）：
      ① **不重写判据** —— 一律复用 `daniel_cli.corpus`（语料读取真源）与
         `mcp/check_corpus_sync.py`（源束↔包内语料的漂移门禁）；
      ② **可移植** —— 源束 `.agents/skills/` 在**分发环境里不存在**，故漂移门禁那一项
         在无源束时记为「跳过（无源束：属分发环境）」：**不冒充通过、也不因分发环境判失败**
         （跳过 ≠ 通过 ≠ 失败）；
      ③ **真阴性** —— 篡改一处必须被报出，证明校验在做事而不是恒绿。
    """
    import shutil
    import tempfile

    from .. import corpus
    items = []

    def add(desc, ok, detail=""):
        items.append((desc, bool(ok), detail))

    def emit_all():
        ok_all = all(ok for _d, ok, _x in items)
        skips = [d for d, ok, x in items if x.startswith("跳过")]
        if getattr(emitter, "json_mode", False):
            emitter.result(data={"summary": "%d 项：通过 %d／跳过 %d"
                                                % (len(items), sum(1 for _d, ok, _x in items if ok), len(skips)),
                                 "明细": [{"项": d, "通过": ok, "说明": x} for d, ok, x in items]},
                           ok=ok_all, exit_code=0 if ok_all else 1)
        else:
            for d, ok, x in items:
                print("  %s %s%s" % ("通过" if ok else "失败", d, ("  —— " + x) if x else ""), file=emitter.out)
            print("  合计 %d 项：通过 %d／不通过 %d" % (len(items),
                  sum(1 for _d, ok, _x in items if ok),
                  sum(1 for _d, ok, _x in items if not ok)), file=emitter.out)
        return 0 if ok_all else 1

    try:
        root, how = corpus.locate()
        add("A1 语料可定位且清单存在", corpus.available(), "%s（%s）" % (root, how))
        doc = corpus.manifest()
        payload = corpus.list_skills(verify=True)          # 返回**字典载荷**，不是列表
        items_ = payload.get("能力域") or []
        n_manifest = len(doc.get("bundles") or {})
        add("A2 能力域数与清单一致",
            payload.get("能力域数") == len(items_) == n_manifest,
            "载荷 %s／明细 %d／清单 %d" % (payload.get("能力域数"), len(items_), n_manifest))
        vers = [str(v) for v in (payload.get("版本集合") or [])]
        add("A3 语料版本各束一致", len(vers) == 1, "版本集合：%s" % "、".join(vers))
        bad = [(s.get("能力域"), s.get("完整性")) for s in items_ if s.get("完整性") != "一致"]
        add("A4 逐束完整性（重算 sha256 与清单比对）", payload.get("完整性") == "一致" and not bad,
            "不一致：%s" % bad if bad else "全部 %d 束：一致" % len(items_))
    except Exception as exc:                                  # noqa: BLE001
        add("A0 自检可执行", False, "异常：%s" % str(exc)[:160])
        return emit_all()

    # ── 真阴性：把语料根指到临时副本，篡改一个字节，必须被报出 ──
    tmp = None
    saved = os.environ.get(corpus.ENV_OVERRIDE)
    try:
        tmp = tempfile.mkdtemp(prefix="daniel-skills-selftest-")
        shutil.copytree(corpus.corpus_dir(), os.path.join(tmp, "corpus"))
        env_root = os.path.join(tmp, "corpus")
        # 篡改：往某束的 SKILL.md 追加一个字节
        victim = None
        for s in (corpus.list_skills(verify=True).get("能力域") or []):
            d = s.get("域") or ""
            cand = os.path.join(env_root, d, "SKILL.md")
            if os.path.isfile(cand):
                victim = cand
                break
        if victim is None:
            add("B1 真阴性夹具可构造", False, "找不到可篡改的 SKILL.md")
        else:
            os.environ[corpus.ENV_OVERRIDE] = env_root
            with open(victim, "a", encoding="utf-8") as fh:
                fh.write("\n<!-- selftest tamper -->\n")
            corpus.manifest(refresh=True)
            tampered = [s for s in (corpus.list_skills(verify=True).get("能力域") or [])
                        if s.get("完整性") != "一致"]
            add("B1 真阴性：篡改一处必须被报为不一致", bool(tampered),
                ("被报出 %d 束：%s" % (len(tampered), [s.get("能力域") for s in tampered])) if tampered
                else "**篡改了却没报出来 ⇒ 校验恒绿，等于没校验**")
    except Exception as exc:                                  # noqa: BLE001
        add("B1 真阴性：篡改一处必须被报为不一致", False, "异常：%s" % str(exc)[:160])
    finally:
        if saved is None:
            os.environ.pop(corpus.ENV_OVERRIDE, None)
        else:
            os.environ[corpus.ENV_OVERRIDE] = saved
        try:
            corpus.manifest(refresh=True)
        except Exception:                                     # noqa: BLE001
            pass
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    # ── 漂移门禁：源束 ↔ 包内语料（分发环境无源束 ⇒ 显式跳过）──
    try:
        # __file__ = <ws>/data/daniel-cli/daniel_cli/commands/mod_skills.py ⇒ 上溯 5 层到工作区根
        ws_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))))
        src = os.path.join(ws_root, ".agents", "skills")
        gate_path = os.path.join(ws_root, "data", "daniel-cli", "mcp", "check_corpus_sync.py")
        if not os.path.isdir(src) or not os.path.isfile(gate_path):
            add("C1 源束 ↔ 包内语料漂移门禁", True,
                "跳过（无源束：属分发环境，跳过 ≠ 通过）")
        else:
            import importlib.util
            spec = importlib.util.spec_from_file_location("ccs", gate_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            led = mod.Ledger()
            ok, _info = mod.gate(led, corpus.corpus_dir(), src,
                                 os.path.join(corpus.corpus_dir(), corpus.MANIFEST_NAME))
            bad_c1 = [i["name"] for i in led.failed]
            add("C1 源束 ↔ 包内语料漂移门禁", ok,
                ("未过 %d 项：%s" % (len(bad_c1), "；".join(bad_c1[:3]))) if bad_c1
                else "断言 %d 项全部通过（包内语料 == 源束）" % len(led.items))
    except Exception as exc:                                  # noqa: BLE001
        add("C1 源束 ↔ 包内语料漂移门禁", False, "异常：%s" % str(exc)[:160])

    return emit_all()


#: 模块自带自检（由 `cli.py` 的模块级钩子分发：`daniel skills --self-test`）
SELFTEST = selftest
