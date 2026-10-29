#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ontology.py —— 语义登记表的索引与注入（零第三方依赖）。

职责边界
--------
* 本模块**不定义**任何业务口径，只做三件事：
  ① 从语料切片（`references/12-ontology-registry.md`）抽取登记项，产出只读索引 `_ONTOLOGY.json`；
  ② 在 `skills read` 返回正文时，把正文引用到的登记项**展开**附在末尾；
  ③ 供校验器查询某条登记项是否存在、是否可用（`status`）。

设计取舍
--------
* **不引入 YAML 解析库**：登记项块结构固定（id/type/label/owner/version/…），
  用正则抽顶层键即可；原文整块保留在 `raw` 里，避免"解析一半丢信息"。
* **索引是生成物**：不手改；`check_corpus_sync.py` 负责重建（段三）。
"""

import json
import os
import re

INDEX_NAME = "_ONTOLOGY.json"
REGISTRY_SLICE_PREFIX = "12-ontology-registry"

_ID_RX = re.compile(r"^id:\s*([A-Za-z0-9_.\-]+)\s*$", re.M)
_TYPE_RX = re.compile(r"^type:\s*([A-Za-z0-9_\-]+)\s*$", re.M)
_LABEL_RX = re.compile(r"^label:\s*(.+?)\s*$", re.M)
_OWNER_RX = re.compile(r"^owner:\s*(.+?)\s*$", re.M)
_STATUS_RX = re.compile(r"^status:\s*(.+?)\s*$", re.M)
_STAGE_RX = re.compile(r"^stage:\s*(.+?)\s*$", re.M)
_AVAIL_RX = re.compile(r"availability:\s*([A-Za-z_]+)")
_IDREF_RX = re.compile(r"\b((?:metric|criterion|expr|concept|constraint)\.[A-Za-z0-9_.\-]+)")


def corpus_dir():
    here = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(os.path.dirname(here), "mcp", "corpus")


def index_path(cdir=None):
    return os.path.join(cdir or corpus_dir(), INDEX_NAME)


def load(cdir=None):
    """读索引；不存在返回 None（未启用语义登记表的老包照常工作）。"""
    p = index_path(cdir)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _yaml_blocks(md):
    """抽 ```yaml ... ``` 块（保留原文）。"""
    out = []
    for m in re.finditer(r"```ya?ml\s*\n(.*?)```", md, re.S):
        out.append(m.group(1).rstrip())
    return out


def parse_entries(md):
    """从登记切片正文解析登记项（只抽可索引字段，原文整块保留）。"""
    entries = []
    for block in _yaml_blocks(md):
        mid = _ID_RX.search(block)
        if not mid:
            continue
        label = _LABEL_RX.search(block)
        owner = _OWNER_RX.search(block)
        status = _STATUS_RX.search(block)
        stage = _STAGE_RX.search(block)
        typ = _TYPE_RX.search(block)
        avail = sorted(set(_AVAIL_RX.findall(block)))
        entries.append({
            "id": mid.group(1),
            "type": typ.group(1) if typ else "",
            "label": label.group(1).strip() if label else "",
            "owner": owner.group(1).strip() if owner else "",
            "status": status.group(1).strip() if status else "active",
            "stage": stage.group(1).strip() if stage else "",
            "availability": avail,
            "raw": block,
        })
    return entries


def build(slices, corpus_version=""):
    """生成索引数据结构。`slices` = [(文件名, 正文)]。"""
    entries, seen = [], set()
    for fname, text in slices:
        if not fname.startswith(REGISTRY_SLICE_PREFIX):
            continue
        for e in parse_entries(text):
            if e["id"] in seen:
                continue
            seen.add(e["id"])
            entries.append(e)
    return {
        "kind": "daniel.ontology.v1",
        "corpus_version": corpus_version,
        "entry_count": len(entries),
        "entries": entries,
    }


def write(doc, cdir=None):
    p = index_path(cdir)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write("\n")
    return p


def refs_in(text):
    """正文里被引用的登记项 id（去重、保序）。"""
    seen, out = set(), []
    for m in _IDREF_RX.finditer(text or ""):
        i = m.group(1)
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def render(entries, limit=12):
    """把登记项渲染成给模型看的紧凑块（业务语言，不暴露内部字段名）。"""
    lines = []
    for e in entries[:limit]:
        bits = [e.get("label") or e["id"]]
        if e.get("owner"):
            bits.append("责任人：" + e["owner"])
        if e.get("status") and e["status"] != "active":
            bits.append("状态：" + e["status"])
        lines.append("- [%s] %s" % (e["id"], "｜".join(bits)))
    return "\n".join(lines)


def resolve(ids, cdir=None):
    doc = load(cdir)
    if not doc:
        return []
    by_id = {e["id"]: e for e in doc.get("entries", [])}
    return [by_id[i] for i in ids if i in by_id]
