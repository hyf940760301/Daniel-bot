# -*- coding: utf-8 -*-
"""命令注册表：`<模块>.<子命令>` → 处理函数。

这是一份**显式**的注册表（不按 schema 自动生成），因为 `daniel schema --check` 要拿它跟
`schema.py` 逐条比对：两边一旦漂移（声明了没实现 / 实现了没声明）必须被报出来。
如果按 schema 自动生成，这个检查就永远为真、失去意义。
"""
from . import (mod_account, mod_authenticity, mod_auth, mod_brands, mod_connect, mod_ct,
               mod_install, mod_intake, mod_intel, mod_keywords, mod_lists, mod_mentions,
               mod_pack, mod_parity, mod_playbook, mod_route, mod_sched, mod_schema,
               mod_search, mod_skills, mod_sov, mod_takeover)

#: 模块键 → 模块实现文件
MODULE_IMPLS = {
    "brands": mod_brands,
    "lists": mod_lists,
    "search": mod_search,
    "mentions": mod_mentions,
    "intel": mod_intel,
    "sov": mod_sov,
    "ct": mod_ct,
    "authenticity": mod_authenticity,
    "route": mod_route,
    "takeover": mod_takeover,
    "parity": mod_parity,
    "account": mod_account,
    "auth": mod_auth,
    "keywords": mod_keywords,
    "skills": mod_skills,
    "intake": mod_intake,
    "playbook": mod_playbook,
    "sched": mod_sched,
    "connect": mod_connect,
    "pack": mod_pack,
    "install": mod_install,
    "schema": mod_schema,
}


def build_registry():
    reg = {}
    for mod_key, impl in MODULE_IMPLS.items():
        for name, fn in getattr(impl, "HANDLERS", {}).items():
            reg["%s.%s" % (mod_key, name)] = fn
        for name, fn in getattr(impl, "WRITE_HANDLERS", {}).items():
            reg["%s.%s" % (mod_key, name)] = fn
    return reg


REGISTRY = build_registry()


def registered_keys():
    return set(REGISTRY)


def handler_for(module_key, command_name):
    return REGISTRY.get("%s.%s" % (module_key, command_name))


def selftest_for(module_key):
    """模块**自带**自检的入口（`daniel <模块> --self-test` 走它）。

    只有真的实现了模块级自检的模块才在实现文件里给 `SELFTEST`；
    没给的模块不给这个入口（上层收到 None 就退回 CLI 总自检），
    因此"schema 里声明了自带自检、实现却没有"会立刻表现为总自检兜底，而不是静默假通过。
    """
    impl = MODULE_IMPLS.get(module_key)
    return getattr(impl, "SELFTEST", None) if impl is not None else None
