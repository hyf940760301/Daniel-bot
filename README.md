# Daniel Bot 项目

> 这里是 Daniel Bot 的全部本地资产：**三个版本的插件包**、**出包**、**方案文档**、**待做的 app 包**。
> 一句话：以后找 Daniel Bot 的东西，只看这个目录。

## 目录结构

```
daniel-bot/
├── packages/           插件包源码（按版本）
│   ├── 0.9.11/         线上基线（客户端曾长期使用，冻结）
│   ├── 0.10.0/         语义登记表版
│   └── 0.11.0/         业务判断下沉版（当前线上）
├── releases/           打好的 .tgz 出包（可直接装）
├── app/                daniel bot app（macOS 独立应用）——规划中
├── specs/              方案与决策（S1 需求 / S2 方案 / 下沉 / 决策记录）
├── docs/               版本说明与使用指南
├── assets/             素材
└── legacy/             历史遗留（旧副本、冷备份、codex 包）
```

## 三个版本的关系

| 版本 | 状态 | 关键差异 |
|---|---|---|
| **0.9.11** | 冻结 | 基线；澄清逻辑在插件 JS（531 行） |
| **0.10.0** | 未上线 | 加语义登记表（附录 B）＋ C19 门禁 |
| **0.11.0** | **当前线上** | 业务判断下沉到 CLI（JS 剩 53 行）＋ 91 条命令 |

## 客户端怎么指过来

客户端不直接读这个目录，而是通过两个 profile 的软链：

```
~/.dsh/profiles/{web,desktop}/node_modules/daniel-dsh-plugin → daniel-bot/packages/<版本>
```

切换版本＝改这个软链 + 重启服务：

```bash
# 切到某版本（示例：0.11.0）
ln -sfn "/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/packages/0.11.0" \
        ~/.dsh/profiles/web/node_modules/daniel-dsh-plugin

# 重启常驻服务（否则改的是文件、跑的还是旧进程）
launchctl kickstart -k gui/$(id -u)/com.deepseek.dsh.web
```

## 出包

```bash
cd packages/0.11.0 && node scripts/pack.mjs --dest ../../releases
node scripts/clean-install-check.mjs --tgz ../../releases/daniel-dsh-plugin-0.11.0.tgz
```

## 纪律

1. **一个版本一个目录**，不在别人目录里改；
2. 改了包要同步 `releases/` 里的出包，否则"源码新、包旧"；
3. `specs/` 是方案权威副本，工作区 `docs/` 为草稿；
4. `legacy/` 只读。
