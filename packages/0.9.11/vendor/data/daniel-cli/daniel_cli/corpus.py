# -*- coding: utf-8 -*-
"""业务语料（技能束）的**唯一读取真源**（TICKET-159）。

它解决什么问题
--------------
用户口径（2026-10-14）：**语料必须包含在整个 MCP 里** —— 别的电脑上的 Cursor 只做一件事
（注册我们的 MCP server），之后**无需任何其它安装步骤**就能拿到营销语料并据此干活。
所以语料不能放在用户级目录（`~/.agents/skills/`）、不能放在工作区里、不能靠宿主去找：
它必须**随包分发**，服务启动时**按自身位置**定位。

定位口径（三层，全部相对本文件，与 cwd 无关）
--------------------------------------------
  ① 环境变量 `DANIEL_CORPUS_DIR`（显式覆盖，供测试与"把语料放到别处"的部署用）；
  ② `<包根>/mcp/corpus/`，即 `data/daniel-cli/mcp/corpus/`（**分发物内的默认落点**）。

**不**读 `~/.agents/skills/`：那是开发机的用户级安装目录，另一台机器上不一定有，
即便有也可能是**别的版本**。本模块一次都不碰它（也不碰 `.kol-tools/`、不碰仓库根）。

语料结构（真源 = `.agents/skills/kol-*/`，由 TICKET-148 从
`docs/marketing/skills/kol-intelligence.md` 机械切分，`--verify` 已证零丢失；**切分时的源版本
不写在这里** —— 它是第二真源、必然漂：现行版本一律取下面清单里的 `corpus_version`）
---------------------------------------------------------------------
    mcp/corpus/_MANIFEST.json          # 本清单（版本／逐束 sha256／字节数／切片数）
    mcp/corpus/<域>/SKILL.md           # 导航件：覆盖的源节表 ＋ 核心判据速查（逐字摘录）
    mcp/corpus/<域>/_CORPUS.json       # 切片台账：每个 references 文件对应的源行区间与标题
    mcp/corpus/<域>/references/*.md    # **逐字切片**（判据原文，带源行区间注记）

读法（分片是硬要求）
--------------------
整束合计约 995 KB，**一次灌给宿主会淹掉上下文**，所以：

  · 不给 `section` → 返回**导航**（元信息 ＋ 切片清单），不返回正文；
  · `section=0` → 返回 SKILL.md（导航件）正文，按 `max_bytes` 分片；
  · `section=N` → 返回第 N 个切片的**逐字正文**，按 `max_bytes` 分片；
  · `grep=词` → 只回命中行（带切片号与行号），用来"先定位再精读"。

退出码语义由上层 `mod_skills` 决定；本模块只做读取与报错（抛 `CorpusError`）。
"""
import hashlib
import io
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)                          # data/daniel-cli

#: 分发物内语料根（**相对包自身**，不看 cwd、不看用户目录）
CORPUS_REL = os.path.join("mcp", "corpus")
#: 显式覆盖用的环境变量
ENV_OVERRIDE = "DANIEL_CORPUS_DIR"
#: 根清单文件名
MANIFEST_NAME = "_MANIFEST.json"

#: 能力域顺序（＝能力地图的推进顺序；`skills_list` 与一致性键比对都按它排）
SKILL_ORDER = (
    "kol-intelligence",
    "kol-discovery",
    "kol-screening",
    "kol-outreach",
    "kol-negotiation",
    "kol-contract",
    "kol-daniel-api",
    "kol-execution-sov",
)

#: 域 → 中文能力域标签（与 SKILL.md 的 frontmatter `description` 无关，只做人看的标签）
DOMAIN_LABELS = {
    "kol-intelligence": "总纲与路由",
    "kol-discovery": "阶段 1 · 发现",
    "kol-screening": "阶段 2 · 背调",
    "kol-outreach": "阶段 3 · 外联",
    "kol-negotiation": "阶段 4 · 谈判",
    "kol-contract": "合同出具与返工",
    "kol-daniel-api": "Daniel 数据层",
    "kol-execution-sov": "阶段 5–7 · 执行／SOV／热点",
}

DEFAULT_MAX_BYTES = 48000
DEFAULT_MAX_HITS = 60


class CorpusError(Exception):
    """语料不可用或读取失败（上层转成退出码 1／2 与人话理由）。"""


# ─────────────────────────── 定位 ───────────────────────────
def corpus_dir():
    """语料根的绝对路径（优先显式覆盖，否则包内相对路径）。"""
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(_PKG_ROOT, CORPUS_REL)


def locate():
    """返回 `(语料根, 定位方式说明)` —— 说明会原样进结果，便于另一台机器上排障。"""
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return corpus_dir(), "环境变量 %s 显式指定" % ENV_OVERRIDE
    return corpus_dir(), "随包分发（相对包自身：%s）" % os.path.join(
        os.path.basename(_PKG_ROOT), CORPUS_REL)


def available():
    return os.path.isfile(os.path.join(corpus_dir(), MANIFEST_NAME))


def _need_manifest():
    root = corpus_dir()
    path = os.path.join(root, MANIFEST_NAME)
    if not os.path.isfile(path):
        raise CorpusError(
            "随包语料不可用：找不到 %s。语料本应随 MCP 服务一起分发（`mcp/corpus/`），"
            "出现这条说明分发物被裁过或复制不全；可用环境变量 %s 指向语料目录"
            % (path, ENV_OVERRIDE))
    return root, path


# ─────────────────────────── 摘要与哈希 ───────────────────────────
def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    with io.open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def bundle_digest(skill_dir):
    """整束摘要：对「相对路径 ＋ 该文件 sha256」按路径排序后求 sha256。

    口径固定，因此**换机器／换文件系统顺序都不会变**，可以直接拿来比对"两台机器上是不是同一版"。
    """
    items = []
    for dirpath, dirnames, filenames in os.walk(skill_dir):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, skill_dir).replace(os.sep, "/")
            items.append((rel, sha256_file(full)))
    h = hashlib.sha256()
    for rel, dig in items:
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(dig.encode("ascii"))
        h.update(b"\n")
    return h.hexdigest(), len(items)


def _read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def _read_json(path):
    try:
        return json.loads(_read_text(path))
    except ValueError as e:
        raise CorpusError("语料文件不是合法 JSON：%s（%s）" % (path, e))


_MANIFEST_CACHE = {}


def manifest(refresh=False):
    """根清单（带进程内缓存；`refresh=True` 重新读盘）。"""
    root, path = _need_manifest()
    if not refresh and path in _MANIFEST_CACHE:
        return _MANIFEST_CACHE[path]
    doc = _read_json(path)
    if not isinstance(doc, dict) or not isinstance(doc.get("bundles"), dict):
        raise CorpusError("语料清单结构不对（缺 bundles）：%s" % path)
    _MANIFEST_CACHE[path] = doc
    return doc


def frontmatter(text):
    """解析 SKILL.md 的 frontmatter（只认本语料用到的两层：顶层键 ＋ `metadata:` 一层）。

    够用即可 —— 这里不是通用 YAML 解析器，是一份**已知结构**的读取器；
    解析不出就返回空表，由调用方按缺项降级（不假装读到）。
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    body = text[3:end]
    out, nested_key = {}, None
    for raw in body.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith((" ", "\t")):                     # 缩进行 → 归到上一个顶层键
            if nested_key:
                k, _, v = raw.strip().partition(":")
                out[nested_key][k.strip()] = _unquote(v.strip())
            continue
        key, sep, val = raw.partition(":")
        if not sep:
            continue
        key, val = key.strip(), val.strip()
        if val == "":
            out[key] = {}
            nested_key = key
        else:
            out[key] = _unquote(val)
            nested_key = None
    return out


def _unquote(v):
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1].replace('\\"', '"')
    return v


# ─────────────────────────── 单束元信息 ───────────────────────────
def _skill_dir(name):
    root, _ = _need_manifest()
    if name not in SKILL_ORDER:
        raise CorpusError("不认识的能力域：%s（可选：%s）" % (name, "、".join(SKILL_ORDER)))
    return os.path.join(root, name)


def file_hashes(skill_dir):
    """束内**逐文件** sha256（相对路径 → 摘要），按路径排序返回。

    这一份是「CLI 侧与 MCP 侧语料完全一致」这条硬断言的比对对象：
    两侧都吐出这一张表，**逐文件名＋逐 sha256 相等**才算一致（差一即缺陷）。
    只比条数或只比整束摘要都会漏掉"换了一个文件但整束摘要碰巧没变"之外的更多情形，
    因此这里给到最细的一层。
    """
    rows = []
    for dirpath, dirnames, filenames in os.walk(skill_dir):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, skill_dir).replace(os.sep, "/")
            rows.append({"文件": rel, "sha256": sha256_file(full),
                         "字节数": os.path.getsize(full)})
    rows.sort(key=lambda r: r["文件"])
    return rows


def skill_meta(name, verify=True, files=True):
    """一束语料的元信息（版本／摘要／前置条件／切片清单／逐文件摘要／完整性）。

    `verify=True` 时重算整束 sha256 与清单比对（约 1 MB 读取，毫秒级），
    并把结论写进 `完整性`：`一致`／`不一致（语料被改过或复制不全）`。
    `files=True` 时附**束内文件清单**（相对路径＋sha256＋字节数）。
    """
    doc = manifest()
    entry = doc["bundles"].get(name)
    if not entry:
        raise CorpusError("清单里没有这一束：%s" % name)
    sdir = _skill_dir(name)
    if not os.path.isdir(sdir):
        raise CorpusError("清单里有 %s，但目录不存在：%s" % (name, sdir))
    skill_md = os.path.join(sdir, "SKILL.md")
    corpus_json = os.path.join(sdir, "_CORPUS.json")
    if not os.path.isfile(skill_md) or not os.path.isfile(corpus_json):
        raise CorpusError("%s 的 SKILL.md 或 _CORPUS.json 缺失（随包复制不全）" % name)
    fm = frontmatter(_read_text(skill_md))
    meta = fm.get("metadata") or {}
    cj = _read_json(corpus_json)
    slices = cj.get("slices") or []
    sections = []
    for i, sl in enumerate(slices, start=1):
        fpath = os.path.join(sdir, sl["file"])
        size = os.path.getsize(fpath) if os.path.isfile(fpath) else None
        sections.append({
            "切片号": i,
            "文件": sl["file"],
            "源节标题": sl.get("title", ""),
            "源行区间": "L%s–L%s" % (sl.get("start"), sl.get("end")),
            "字节数": size,
            "存在": size is not None,
        })
    sm_meta = meta.get("corpus_sha256") or cj.get("source_sha256")
    out = {
        "域": name,
        "能力域": DOMAIN_LABELS.get(name, ""),
        "名称": fm.get("name", name),
        "版本": fm.get("version") or meta.get("corpus_version") or cj.get("corpus_version"),
        "摘要": fm.get("description", ""),
        "前置条件": fm.get("whenToUse", ""),
        "读法": "本束只做导航：不给 section 先看切片清单，再按切片号读正文（逐字切片，不改写判据）。",
        "源文件": cj.get("source") or meta.get("corpus_source"),
        "源文件sha256": sm_meta,
        "源文件行数": cj.get("source_lines"),
        "切片数": len(sections),
        "SKILL.md字节数": os.path.getsize(skill_md),
        "字节数": entry.get("bytes"),
        "文件数": entry.get("files"),
        "整束sha256": entry.get("bundle_sha256"),
        "切片": sections,
    }
    if files:
        # 束内**逐文件** sha256：这是「CLI 侧与 MCP 侧语料完全一致」的比对对象（差一即红）
        out["文件清单"] = file_hashes(sdir)
    if verify:
        got, n = bundle_digest(sdir)
        same = (got == entry.get("bundle_sha256")) and (n == entry.get("files"))
        out["完整性"] = "一致" if same else "不一致（语料被改过或复制不全）"
        out["实测整束sha256"] = got
        out["实测文件数"] = n
    return out


def list_skills(verify=True):
    """`skills_list` 的完整载荷：8 个能力域 ＋ 摘要 ＋ 版本 ＋ 前置条件。"""
    root, how = locate()
    doc = manifest()
    items = []
    for name in SKILL_ORDER:
        if name not in doc["bundles"]:
            raise CorpusError("清单缺少能力域：%s" % name)
        items.append(skill_meta(name, verify=verify))
    versions = sorted({s["版本"] for s in items if s["版本"]})
    integrity = sorted({s.get("完整性", "未校验") for s in items})
    return {
        "语料版本": doc.get("corpus_version"),
        "语料根": root,
        "定位方式": how,
        "能力域数": len(items),
        "版本集合": versions,
        "完整性": integrity[0] if len(integrity) == 1 else "／".join(integrity),
        "源文件": doc.get("source"),
        "源文件sha256": doc.get("source_sha256"),
        "源文件行数": doc.get("source_lines"),
        "总量": {"字节数": doc.get("total_bytes"), "文件数": doc.get("total_files"),
                 "切片数": doc.get("total_slices")},
        "读法": "先本清单选域 → `skills read --name <域>` 取切片清单 → `--section N` 读正文"
                "（大切片按 --max-bytes 分片，用 --offset 续读）。",
        "能力域": items,
    }


# ─────────────────────────── 分片读取 ───────────────────────────
def _section_source(name, section):
    """`section` → `(标签, 文件绝对路径, 源行区间, 标题)`。`section=0` ＝ SKILL.md。"""
    sdir = _skill_dir(name)
    meta = skill_meta(name, verify=False)
    if section is None:
        return None
    if section == 0:
        return {"切片号": 0, "文件": "SKILL.md", "源节标题": "导航件（本束总览）",
                "源行区间": "—", "路径": os.path.join(sdir, "SKILL.md")}
    if section < 0 or section > len(meta["切片"]):
        raise CorpusError("切片号超出范围：%s（本束共 %d 个切片，另有 0 ＝ 导航件 SKILL.md）"
                          % (section, len(meta["切片"])))
    one = meta["切片"][section - 1]
    one = dict(one)
    one["路径"] = os.path.join(sdir, one["文件"])
    return one


def _chunk(text, max_bytes, offset):
    """按**字节**分片（不按字符，保证宿主侧按字节续读不会串位）。"""
    raw = text.encode("utf-8")
    total = len(raw)
    offset = max(0, int(offset or 0))
    if offset >= total:
        return "", {"偏移": offset, "本次字节": 0, "总字节": total,
                    "还有更多": False, "下一次偏移": None,
                    "说明": "偏移已到末尾（总字节 %d）" % total}
    if not max_bytes or max_bytes <= 0:
        piece = raw[offset:]
        nxt = None
    else:
        end = min(total, offset + int(max_bytes))
        while end < total:                      # 不切断 UTF-8 多字节字符
            try:
                raw[offset:end].decode("utf-8")
                break
            except UnicodeDecodeError:
                end -= 1
        piece = raw[offset:end]
        nxt = end if end < total else None
    info = {"偏移": offset, "本次字节": len(piece), "总字节": total,
            "还有更多": nxt is not None, "下一次偏移": nxt}
    if nxt is not None:
        info["续读"] = "还有更多：再用 --offset %d 取下一片" % nxt
    return piece.decode("utf-8"), info


def read_skill(name, section=None, grep=None, max_bytes=DEFAULT_MAX_BYTES,
               offset=0, max_hits=DEFAULT_MAX_HITS):
    """`skills_read` 的载荷。

    三种模式（互斥优先级：`grep` > `section` > 导航）：
      · `grep` 给了 → 在选定范围内只回命中行（带切片号与行号），不整段灌正文；
      · `section` 给了 → 回该切片正文（按 `max_bytes` 分片）；
      · 都不给 → 回导航（元信息 ＋ 切片清单），**不返回正文**。
    """
    meta = skill_meta(name, verify=True)
    head = {
        "域": name,
        "能力域": meta["能力域"],
        "版本": meta["版本"],
        "源文件": meta["源文件"],
        "源文件sha256": meta["源文件sha256"],
        "整束sha256": meta["整束sha256"],
        "完整性": meta.get("完整性"),
    }
    if grep:
        hits, scanned, total = _grep(name, grep, section, max_hits)
        return dict(head, 模式="检索",
                    关键词=grep,
                    检索范围=("切片 %s" % section) if section is not None else "整束（导航件 ＋ 全部切片）",
                    目标文件数=scanned,
                    命中总数=total,
                    命中数=len(hits),
                    命中截断=(total > len(hits)),
                    命中=hits,
                    提示="命中行只给上下文线索；判据原文请用 --section <切片号> 精读。")

    src = _section_source(name, section)
    if src is None:
        return dict(head, 模式="导航",
                    读法=meta["读法"],
                    切片清单=meta["切片"],
                    下一步="用 --section <切片号> 读正文；0 ＝ 导航件 SKILL.md；"
                           "拿不准切到哪一片就先用 --grep <关键词> 定位。",
                    提示="本模式**不返回正文**（整束约 %s 字节）；避免一次灌满宿主上下文。"
                         % meta["字节数"])

    if not os.path.isfile(src["路径"]):
        raise CorpusError("切片文件缺失：%s" % src["路径"])
    text = _read_text(src["路径"])
    piece, info = _chunk(text, max_bytes, offset)
    return dict(head, 模式="正文",
                切片号=src["切片号"],
                切片文件=src["文件"],
                源节标题=src["源节标题"],
                源行区间=src["源行区间"],
                分片=info,
                正文=piece)


def _grep(name, pattern, section, max_hits):
    """在选定范围内找命中行。返回 `(命中行, 目标文件数, 命中总数)`。

    `max_hits` **只截断返回的清单，不影响扫描面**：先把全部目标文件扫完，
    这样"扫描了几个文件、一共命中几行"是真的（早退会让计数骗人）。
    """
    import re
    try:
        rx = re.compile(pattern)
    except re.error:
        rx = re.compile(re.escape(pattern))
    sdir = _skill_dir(name)
    meta = skill_meta(name, verify=False)
    targets = []
    if section is None:
        targets.append({"切片号": 0, "文件": "SKILL.md", "源节标题": "导航件（本束总览）",
                        "路径": os.path.join(sdir, "SKILL.md")})
        for one in meta["切片"]:
            targets.append(dict(one, 路径=os.path.join(sdir, one["文件"])))
    else:
        targets.append(_section_source(name, section))
    hits, scanned, total = [], 0, 0
    limit = int(max_hits or 0)
    for t in targets:
        if not os.path.isfile(t["路径"]):
            continue
        scanned += 1
        for no, line in enumerate(_read_text(t["路径"]).splitlines(), start=1):
            if rx.search(line):
                total += 1
                if not limit or len(hits) < limit:
                    hits.append({"切片号": t["切片号"], "切片文件": t["文件"],
                                 "源节标题": t["源节标题"], "行号": no,
                                 "行": line.strip()[:300]})
    return hits, scanned, total


def consistency_key(payload):
    """把 `skills_list` 载荷压成**可键比对**的一行键：`域=版本` 排序串 ＋ 语料版本。

    MCP 侧与 CLI 侧的载荷都过这一函数，两边字符串**逐字相等**才算一致
    （比"都返回了 8 条"更强的断言：域集合、每域版本、总版本三项都在键里）。
    """
    items = payload.get("能力域") or []
    pairs = sorted("%s=%s" % (s.get("域"), s.get("版本")) for s in items)
    return {
        "语料版本": payload.get("语料版本"),
        "能力域数": len(items),
        "键": "；".join(pairs),
        "整束sha256": "；".join(sorted("%s=%s" % (s.get("域"), s.get("整束sha256"))
                                     for s in items)),
    }
