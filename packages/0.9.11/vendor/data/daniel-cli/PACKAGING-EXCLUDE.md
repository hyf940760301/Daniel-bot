# 分发构建排除清单（PACKAGING-EXCLUDE）

> 依据：TICKET-145 §3（并入项 B）｜上游：`04-剥离清单` C1「凭据与会话钉在代码目录」。
> 用途：把 Daniel CLI / 能力脚本打包成分发物（另一台机器、另一个模型、另一个宿主）时，
> **下面这些路径一律不得进入分发物**。

## 1. 必须排除（安全项：进了就是凭据泄漏）

| 路径 | 是什么 | 为什么必须排除 |
|---|---|---|
| `.daniel_cred.json` | Daniel 账号**邮箱＋密码明文**（仓库根） | 明文密码；分发即外泄 |
| `.kol-tools/.daniel_session.json` | 会话 JWT（`app_session_id`，**1 年有效**） | 会话等同账号，无需密码即可取数 |
| `$DANIEL_HOME/secrets/`（含 `credentials.json`） | 明文降级凭据（仅 `DANIEL_ALLOW_PLAINTEXT=1` 时生成） | 同为明文密码 |
| `$DANIEL_HOME/session/` | 会话文件（系统默认落点或工作区降级落点） | 会话 JWT |
| `.daniel-home/` | 工作区降级落点整体（session／cache／output／logs／secrets） | 上面两项都在里面 |
| `~/Library/Application Support/DanielCopilot/` | macOS 默认落点整体 | 同上 |
| `.env` / `.env.*` | 环境变量文件（可能含 `DANIEL_EMAIL`／`DANIEL_PASSWORD`） | 明文凭据 |
| `*keychain*` / `*.pem` / `*.p12` / `id_rsa*` | 密钥材料 | 通用安全项 |

## 2. 必须排除（噪声项：进了会带走上万文件或本机私有数据）

| 路径 | 是什么 |
|---|---|
| `_archive*/`（`.kol-tools/_archive/`、`_archive-oneshot/` 等） | 历史一次性脚本（388 个 `.py` 里的大头） |
| `.kol-tools/_snapshots/`、`.kol-tools/_verify_tmp/`、`.kol-tools/_recovery/` | 运行期快照与临时件 |
| `.kol-tools/_cache/` | 本机缓存（含品牌索引，属账号数据） |
| `.kol-tools/_daniel_bundle/`、`.kol-tools/_daniel_jsref/` 之外的前端还原件 | 体积大、可再生成（`_daniel_jsref/` 若被 `parity` 依赖则**保留**） |
| `data/crawl/**`、`data/review-export-*.json` | 抓取语料与导出的评审数据（几 MB～上百 MB，且含第三方内容） |
| `.tmp-doc/`、`.tmp-docs/`、`.tmp-up/`、`tmp/`、`tmp_ref/` | 临时工作目录 |
| `__pycache__/`、`*.pyc`、`.pytest_cache/`、`.mypy_cache/` | 解释器缓存 |
| `*.bak-*`、`*.tmp`、`*.orig` | 备份与中间件 |
| `node_modules/`、`.npm-cache-dsh/`、`dist/`、`build/` | 依赖与构建产物 |

## 3. 可以进分发物（这些才是产品）

| 路径 | 说明 |
|---|---|
| `data/daniel-cli/**` | CLI 本体（`bin/daniel` ＋ `daniel_cli/**`）与本文档 |
| `.kol-tools/daniel_*.py`（顶层，非归档目录） | Daniel 能力层：`daniel_client` / `daniel_paths` / `daniel_credentials` 及各模块仪器 |
| `.kol-tools/check_no_secrets_in_dist.py` | 分发前的断言器（随包提供，供打包方自证） |
| `.kol-tools/_daniel_jsref/` | 口径一致性仪器需要的算法还原件（`parity` 命令依赖） |

> 分发物**不需要**：`tickets/`、`docs/marketing/**`、`docs/roles/**`、`inf-docs/` 等团队工作区内容。

## 4. 构建后必须做的断言（不是"建议"，是"必须"）

打包完成后，对**打包目录**跑一次凭据断言：

```bash
# ① 断言器自检（正控必报 + 真阴性 0 命中）
python3 .kol-tools/check_no_secrets_in_dist.py --self-test

# ② 对打包目录严格扫描：命中任一凭据痕迹 → 退出码 1 → 不得发布
python3 .kol-tools/check_no_secrets_in_dist.py <打包目录>
```

退出码口径：`0`＝干净（可分发）｜`1`＝命中凭据痕迹（**不得分发**）｜`2`＝用法错误｜`3`＝自检不通过。
`--allow-repo-root` **只**用于扫描本工作区根这种"用户明确要求保留现有明文文件"的场景，
**不得**用于打包目录。

### 4.1 断言器的扫描边界（TICKET-151 C2 起生效；`--help` 里有同一份）

跑断言前先知道它**不扫什么**，否则"0 命中"会被误读成"绝对安全"：

| 边界 | 具体口径 | 为什么 |
|---|---|---|
| ① **二进制不扫内容** | 只有**文本扩展名**的文件跑内容判据：数据类 `.json .jsonl .yaml .yml .env .txt .csv .tsv .ini .conf .cfg .toml .xml .properties .sql .md5`、源码类 `.py .md .sh .bash .zsh .js .ts .jsx .tsx .html .css .rb .go`，**另加无扩展名文件**；其余扩展名（图片、`.zip/.gz/.whl`、`.so/.node/.exe`、字库、`.xlsx/.pdf`、`.log/.out/.err` 等）**只做文件名判据**。 | 二进制里"抽出可读串"的误报率远高于收益；把假凭据嵌进 `.png` 本工具**不会**报出——这一条必须写在这里，不能算"已覆盖"。 |
| ② **>4 MiB 只扫头尾** | 单文件 >4 MiB（`FULL_SCAN_MAX`）时只读**头 1 MiB（`HEAD_WINDOW`）＋ 尾 256 KiB（`TAIL_WINDOW`）**，中段不扫；命中条目标 `truncated: true`，报告里逐条打印「已按上限扫描：<路径>（x MB）」。≤4 MiB 全量读（与旧版 `MAX_BYTES` 同值，灵敏度零变化）。`--full-scan` 可对全部文件强制全量。 | 旧版对 >4 MiB 的文件**完全不扫**（本工作区有 60 个这样的文件、合计 1.55 GB）；改成扫头尾是**净增覆盖**。 |
| ③ **目录剪枝** | `.git`、`node_modules`、`__pycache__`、`.venv`、`venv`、`.mypy_cache`、`.pytest_cache`，以及 `_archive*` 前缀目录。`--scan-archives` 可放开后者。 | 归档与缓存目录不属于分发物；剪掉哪些会逐条打印，便于复核没剪过头。 |
| ④ **形态边界（既有口径）** | `password: hunter2`（值**未加引号**）不判 ERROR；把变量名本身拆行写（`DANIEL_PASS` ＋ 换行 ＋ `WORD=x`）不命中。 | 规则要求引号包裹／整词匹配；属既有口径，不是本次提速引入。 |

每次扫描的报告尾部都会打印**扫描面自报**（文件总数 ＝ 全量扫 ＋ 按上限扫 ＋ 只看文件名 ＋ 不可读；
剪枝目录数与清单；截断文件数与清单；实际读取字节数），`--surface` 可只看这一份，`--json` 里有
`scanSurface` 结构化字段。**不存在静默跳过**：剪了什么、截了什么都能被复核。

性能（TICKET-151 C2）：在"逐个文件、全量读、单线程"之外加了两条——**字节级 needle 预筛**
（只有命中 `eyj/email/password/app_session_id/daniel_cred/daniel_session` 之一的文件才解码跑正则，
每条正则的必要字面量都在 needle 表里，故不漏报）＋**线程池按文件切分**（`--jobs`，默认 8，
环境变量 `KOL_DIST_SCAN_JOBS` 可覆盖）。命中集合最后按「路径/行号/规则」排序，**结果与并发数无关**。

## 5. 与 `.gitignore` 的关系

两层防护各管一段，不能互相替代：

- `.gitignore`（仓库根）挡的是"**误提交**"——把凭据写进版本历史后再删除也没用，历史里还在；
- 本清单挡的是"**误打包**"——`.gitignore` 不参与 `tar`/`zip`/`docker build` 的选择过程。

本工作区当前**不是 git 仓库**，所以第二层（本清单 ＋ 构建后断言）是当下唯一的实际防线。
