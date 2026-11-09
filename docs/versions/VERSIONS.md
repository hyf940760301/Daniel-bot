# 插件版本索引（本地管理）

> 三个版本互不影响：客户端只加载其中一个；改造在各自的目录里做。
> 回退＝改一条软链 + 重启客户端。

| 版本 / 代号 | 状态 | 落地位置 | 分支 | 版本说明 |
|---|---|---|---|---|
| **0.9.11** | **线上（客户端在跑）** | `daniel-plugins/0.9.11/` | `main` + tag `v0.9.11` | `versions/VERSION-0.9.11.md` |
| 0.9.11 冷备份 | 只读归档 | `daniel-plugins/_archive-0.9.11/` | — | 同上 |
| **0.10.0** | 语义登记表版（已过出厂检查，未上线） | `daniel-plugins/next/` | `feat/ontology-registry` | `versions/VERSION-0.10.0.md` |
| **a-v2** | **A 管线改造专用**（产品迭代 v2） | `daniel-plugins/a-v2/` | `feat/product-v2` | 待写 |
| 母本快照 | 只读 | `daniel-plugins/_backup/` | — | — |

## 三条互不影响

| 关系 | 说明 |
|---|---|
| 0.9.11 ↔ 0.10.0 | 不同目录、不同分支；客户端只加载 0.9.11 |
| 0.10.0 ↔ a-v2 | a-v2 从 0.10.0 **克隆**（含语义登记表），此后各自演进，互不覆盖 |
| 任意两者 | 都读同一份母本 `docs/marketing/skills/kol-intelligence.md`；母本改动只影响"重新切语料"，不影响已打好的包 |

## 切版与回退（改软链 + 重启）

```bash
# 切到 0.10.0
ln -sfn "/Users/huyifan/Desktop/DeepSeek Harness/daniel-plugins/next" \
        ~/.dsh/profiles/web/node_modules/daniel-dsh-plugin

# 切回 0.9.11
ln -sfn "/Users/huyifan/Desktop/DeepSeek Harness/daniel-plugins/0.9.11" \
        ~/.dsh/profiles/web/node_modules/daniel-dsh-plugin
```

之后**完全退出客户端再打开**，跑三条验收（登录状态 / 能力清单 / 列 3 个品牌）。

## 打包与出厂检查

```bash
cd daniel-plugins/<版本目录> && node scripts/pack.mjs --dest ../
node scripts/clean-install-check.mjs --tgz ../daniel-dsh-plugin-<版本>.tgz
```

## 纪律

1. **一个目录一个版本**，不许在别人的目录里改；
2. 每次发版四件齐：`package.json` 版本号 + 版本说明 + 出包 + 出厂检查；
3. 回退必须验收，只换软链不验收等于没回退；
4. 冷备份目录只读。
