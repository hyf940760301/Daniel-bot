# 版本 0.9.11 · 现状基线（冻结）

## 基本信息
- 归档日期：2026-10-29
- 语料版本：0.9.204（8 束 / 40 文件 / 24 切片 / 1,279,955 B）
- 母本：`docs/marketing/skills/kol-intelligence.md`（6,894 行）
- 能力面：插件 14 个内置工具；CLI 89 条命令 / 22 个模块
- 契约：13 份（5 工程 + 8 示例）；读链信封 `daniel.read.v1`

## 安装形态（重要）
- 客户端通过**软链**加载源码目录：
  `~/.dsh/profiles/{web,desktop}/node_modules/daniel-dsh-plugin → Desktop/DeepSeek Harness/daniel-dsh-plugin`（该路径现为兼容软链，指向 `daniel-plugins/0.9.11`）
- **不是安装 tgz**，因此"替换 tgz"不会生效；回退必须改软链或换目录

## 版本管理状态
- 无 git 仓库 → 改动不可追溯
- 已有打包产物 `daniel-dsh-plugin-0.9.11.tgz`（可用于重建目录）

## 用途
1. 语义登记表改造的**对照基线**
2. 改造失败时的**回退目标**

## 回退到本版
```bash
ln -sfn "/Users/huyifan/Desktop/DeepSeek Harness/daniel-plugins/0.9.11" \
        ~/.dsh/profiles/web/node_modules/daniel-dsh-plugin
ln -sfn "/Users/huyifan/Desktop/DeepSeek Harness/daniel-plugins/0.9.11" \
        ~/.dsh/profiles/desktop/node_modules/daniel-dsh-plugin
```
然后完全重启客户端 + 新开会话，跑三条验收（登录状态 / 能力清单 / 列 3 个品牌）。

## 已知问题
- 无 git 历史，本版之后不得在原地改动（否则基线消失）
- C1/C18 版本链要求六处相等，本版五处一致、六处含 `_MANIFEST.json` 0.9.204
