# -*- coding: utf-8 -*-
"""契约加载器（TICKET-146 · P0-3 §2 任务内容）。

真源落点（D1 裁决）：`data/daniel-cli/contracts/`（随 CLI 分发、剥离后仍可用、可被 CLI 自校验）；
环境变量 `DANIEL_CONTRACTS_DIR` 可整体覆盖（换宿主／换项目时不用改代码）。
示例契约放 `contracts/_examples/`。

本模块只负责"找到文件并读成字典"，格式校验在 `validate.py`、执行在 `executor.py`。
"""
import json
import os

from ..exits import EXIT_INTERNAL, EXIT_USAGE
from ..runtime import CliError
from . import model

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(os.path.dirname(_HERE))          # data/daniel-cli
DEFAULT_DIR = os.path.join(_PKG_ROOT, "contracts")
EXAMPLES_DIRNAME = "_examples"


def contracts_dir():
    """契约目录：`DANIEL_CONTRACTS_DIR` → 否则本包自带的 `contracts/`。"""
    env = os.environ.get("DANIEL_CONTRACTS_DIR")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return DEFAULT_DIR


def examples_dir(root=None):
    return os.path.join(root or contracts_dir(), EXAMPLES_DIRNAME)


def contract_files(root=None):
    """契约目录下的全部 `.json`（含 `_examples/`，示例会被标注出来）。"""
    root = root or contracts_dir()
    if not os.path.isdir(root):
        raise CliError("契约目录不存在：%s" % root, code=EXIT_INTERNAL,
                       hint="设置环境变量 DANIEL_CONTRACTS_DIR 指向契约目录（默认落点是 "
                            "data/daniel-cli/contracts/）")
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for fn in sorted(files):
            if fn.endswith(".json"):
                out.append(os.path.join(base, fn))
    return sorted(out)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except ValueError as e:
        raise CliError("契约不是合法 JSON：%s（%s）" % (path, e), code=EXIT_USAGE,
                       hint="契约用 JSON 写（零第三方依赖，不引入 YAML）；"
                            "格式见 data/daniel-cli/PLAYBOOK.md")
    except OSError as e:
        raise CliError("契约读不出来：%s（%s）" % (path, e), code=EXIT_INTERNAL)
    if not isinstance(raw, dict):
        raise CliError("契约的顶层必须是对象（JSON object）：%s" % path, code=EXIT_USAGE)
    return raw


def is_example(path, root=None):
    rel = os.path.relpath(path, root or contracts_dir())
    return rel.split(os.sep)[0] == EXAMPLES_DIRNAME


def summarize(path, root=None):
    """给 `playbook list` 用的一行摘要：id／名称／是否示例／是否含写步骤／期望结果。"""
    root = root or contracts_dir()
    row = {"路径": os.path.abspath(path), "相对路径": os.path.relpath(path, root),
           "示例": is_example(path, root), "id": None, "名称": None,
           "含写步骤": False, "期望结果": None, "错误": None}
    try:
        contract, _aliases = model.normalize(read_json(path))
    except CliError as e:
        row["错误"] = e.message
        return row
    row["id"] = contract.get(model.F_ID)
    row["名称"] = contract.get(model.F_NAME)
    row["含写步骤"] = bool(model.write_steps(contract))
    expect = (contract.get(model.F_EXPECT) or {}).get(model.E_DEFAULT) or {}
    row["期望结果"] = expect.get(model.E_RESULT)
    return row


def list_contracts(root=None):
    root = root or contracts_dir()
    return [summarize(p, root) for p in contract_files(root)]


def _matches(path, ref, root):
    rel = os.path.relpath(path, root)
    stem = os.path.splitext(os.path.basename(path))[0]
    return ref in (rel, os.path.basename(path), stem, os.path.abspath(path))


def resolve(ref, root=None):
    """按"相对路径／文件名／文件名去扩展名／契约 id"定位一份契约。"""
    root = root or contracts_dir()
    if not ref:
        raise CliError("缺少契约名（用 `daniel playbook list` 看有哪些）", code=EXIT_USAGE)
    files = contract_files(root)
    for path in files:
        if _matches(path, ref, root):
            return path
    for path in files:
        try:
            contract, _ = model.normalize(read_json(path))
        except CliError:
            continue
        if contract.get(model.F_ID) == ref:
            return path
    raise CliError("找不到契约：%s" % ref, code=EXIT_USAGE,
                   hint="用 `daniel playbook list` 看契约目录里有什么；"
                        "目录当前为 %s（可用 DANIEL_CONTRACTS_DIR 覆盖）" % root)


def load(ref, root=None):
    """读出一份契约：返回 `(规范化契约, 路径, 用到的别名)`。"""
    path = resolve(ref, root)
    raw = read_json(path)
    contract, aliases = model.normalize(raw)
    return contract, path, aliases
