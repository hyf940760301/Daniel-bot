# -*- coding: utf-8 -*-
"""`connect` —— 把「接入」做成 CLI 自带能力（TICKET-189）。

一句话：**换机器、换宿主，接入都只有同一条命令。**

    daniel connect --list                         # 本机支持哪些宿主、各自接没接上
    daniel connect --host cursor --print          # 只打印该宿主该写的那一段（不改任何文件）
    daniel connect --host cursor --apply --confirm    # 自己算路径 ＋ 幂等合并写进去
    daniel connect --host cursor --uninstall --confirm # 只删自己那一条
    daniel connect --doctor                       # 端到端断言：这套接入到底通不通

两层：`hosts`（算路径／生成片段／合并／快照／回读）与 `doctor`（端到端断言）。
`commands/mod_connect.py` 只做 CLI 接线，不重复这里的任何判据。
"""
from . import doctor, hosts

__all__ = ["hosts", "doctor"]
