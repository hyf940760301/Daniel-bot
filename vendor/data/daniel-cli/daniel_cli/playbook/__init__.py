# -*- coding: utf-8 -*-
"""工序契约引擎（TICKET-146 · P0-3 契约化骨架）。

一条工序 = 一份**声明式契约**（JSON）；本包把契约里的**判据与门禁变成可执行断言**，
并把结果收成一份带**计数自洽**的自检报告。三件事分开：

| 文件 | 管什么 |
|---|---|
| `model.py` | 契约字段口径（输入／前置／步骤／判据／门禁／交付件schema／自检／失败模式） |
| `loader.py` | 契约目录定位与加载（`DANIEL_CONTRACTS_DIR` 可覆盖；真源随 CLI 分发） |
| `validate.py` | 校验：字段、门禁声明、**步骤只能引用 schema.py 已声明的命令与参数**（D3） |
| `assertions.py` | 断言词汇表与取值引用解析（判据的可执行化） |
| `actions.py` | 离线假动作（写类只写沙箱内文件，不碰任何 Daniel 写路由） |
| `gates.py` | 五道门禁：样本上限／写权限／只读默认／写步骤确认／回读校验 |
| `executor.py` | 执行器：跑契约、出交付件、出自检报告、定退出码 |
| `selfcheck.py` | 引擎自证：把每份契约按它声明的期望跑一遍 |

**零 DSH 依赖**：只用标准库，不 import 任何 DSH 模块；门禁挂在执行器内部，不依赖宿主 hook。
"""
from . import actions, assertions, executor, gates, loader, model, selfcheck, validate

__all__ = ["actions", "assertions", "executor", "gates", "loader", "model",
           "selfcheck", "validate", "run_contract", "engine_selfcheck", "CONTRACT_FIELDS"]

#: 契约的八项字段（票面口径，业务语言）
CONTRACT_FIELDS = model.EIGHT_FIELDS

run_contract = executor.run_contract
engine_selfcheck = selfcheck.engine_selfcheck
