# -*- coding: utf-8 -*-
"""退出码语义（TICKET-145 §1；TICKET-152 校正）——**唯一的常量定义处**。

四个码是 CLI 与调用方（人／其它模型／MCP 壳）之间的契约，任何子命令都不许自造第五个。
`--help` 里的说明文本由 `schema.exit_code_lines()` 从这张表生成，不手写第二份。

写链的三种"没写成"分得很清楚（TICKET-152）：
  · **退出码 2**：账号对那个模块**没有写权限**（或删除类没给／给错删除凭据）—— 用户侧的东西不对；
  · **退出码 3**：权限没问题，但**没给 --confirm**（只做了干跑）—— 需要确认；
  · **退出码 1**：链路/环境异常。
"""

EXIT_OK = 0            # 成功
EXIT_INTERNAL = 1      # 内部错误（链路异常／环境缺件／按工作令红线不允许执行的动作）
EXIT_USAGE = 2         # 用户错误（缺参、取值非法、引用的对象不存在、账号没有该模块权限）
EXIT_NEEDS_CONFIRM = 3  # 需要确认（写操作未加 --confirm）

#: 机器可读的退出码表（进 `daniel schema --json`）
EXIT_CODES = [
    {
        "code": EXIT_OK,
        "name": "成功",
        "meaning": "命令执行完成，结果已写入 stdout。",
        "when": "读操作正常返回；写操作执行成功且回读校验通过；`--help`／`--version`／`schema` 类查询。",
    },
    {
        "code": EXIT_INTERNAL,
        "name": "内部错误",
        "meaning": "链路或环境异常：取数失败、依赖缺件、文件不可写、审计写不下去，"
                   "以及按本次工作令红线**不允许执行**的动作（例如触发采集）。",
        "when": "网络/接口异常、依赖脚本缺失、文件不可写、写已提交但回读校验不通过、"
                "被工作令红线拦下的动作。",
    },
    {
        "code": EXIT_USAGE,
        "name": "用户错误",
        "meaning": "调用方给的东西不对：缺必填参数、参数类型/取值非法、引用的品牌或名单不存在，"
                   "**以及账号对目标模块没有权限**（含删除类没给或给错删除凭据）。",
        "when": "缺参、给错类型、品牌名多义或查不到、账号没有该模块的读/写权限、"
                "--delete-token 与目标名不一致。",
    },
    {
        "code": EXIT_NEEDS_CONFIRM,
        "name": "需要确认",
        "meaning": "这是写操作，未加 --confirm：只做了干跑（打印将要做什么＋影响范围），"
                   "**没有执行任何写**。",
        "when": "任何标了“写操作”的子命令，未显式传 --confirm。",
    },
]

_BY_CODE = {e["code"]: e for e in EXIT_CODES}


def name_of(code):
    e = _BY_CODE.get(code)
    return e["name"] if e else "未知"


def exit_code_lines():
    """给 `--help` 用的退出码说明（从 EXIT_CODES 生成）。"""
    return ["%d = %s：%s" % (e["code"], e["name"], e["meaning"]) for e in EXIT_CODES]
