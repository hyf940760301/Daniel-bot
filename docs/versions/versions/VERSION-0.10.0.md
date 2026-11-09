# 版本 0.10.0 · 语义登记表版

## 基本信息
- 日期：2026-10-30
- 上一版：0.9.11（冻结基线，未改动）
- 插件版本：**0.10.0**
- 语料版本：**0.9.205**（上一版 0.9.204，新增附录 B）
- 工具数：**15**（新增 `daniel_screen_ask`）
- 能力束：8（不变，kol-intelligence 由 12 片增至 13 片）
- 契约：**14**（新增 `kol-list`）

## 这一版改了什么

| 类型 | 内容 | 影响 |
|---|---|---|
| 新增 | 母本 `## 附录 B · 语义登记`（指标／判据／表达三类登记项） | 语料多一片 |
| 新增 | `daniel_cli/ontology.py` ＋ `mcp/corpus/_ONTOLOGY.json` | 登记项可被机器查询 |
| 新增 | `skills read` 返回时展开正文引用的登记项 | 读技能即拿到口径 |
| 新增 | 工具 `daniel_screen_ask`（一次给全 ＋ 按回答动态追问） | 找红人不再固定三轮 |
| 新增 | 契约 `kol-list` ＋ 四类自检 `deliverable_checks.py` | 名单交付可自证 |
| 新增 | `mcp/check_ontology.py`（C19-a/b/c/e） | 登记表可门禁 |
| 修改 | `check_corpus_sync.py` 增加段三（重建索引） | `--sync` 后索引自动更新 |
| 修改 | 工序表加 `判据引用`（screening 5 条） | 工序可引用登记项 |
| 不变 | CLI 89 命令、其余 13 份契约、能力束数量 | — |

## 怎么验证这一版是好的

1. `node tests/golden/diff.mjs` → 26/26 逐字节一致；
2. `node scripts/test-clarify.mjs` → 36/36；
3. `daniel schema --check` → 10/10；
4. `daniel playbook validate` → 14/14；
5. `python3 mcp/check_ontology.py` → C19 四项绿；
6. `check_corpus_sync.py --sync` → 9/9 绿；
7. `clean-install-check.mjs --tgz` → C1–C7 全过。

## 怎么回退

方式一（git）：
```bash
cd daniel-plugins/next && git checkout 58ab1a2   # 升版前的最后一次提交
```
方式二（整包）：客户端软链指回 `daniel-plugins/0.9.11`，重启客户端。

回退后跑三条验收：登录状态／能力清单（8 域）／列 3 个品牌。

## 已知问题

- 工序表真源（`intake-parts`）与产物已漂移：重跑合并器会丢 `execution-sov-14` 并把版本降回 0.9.196 ⇒ **不要重跑合并器**，改产物时同步改真源（D-1）。
- 母本为多包共享：旧包 0.9.11 不能用当前母本重切（D-2）。
- C18 依赖 `.agents/skills` 软链，现已收编到 `daniel-plugins/next/_skills-src`（D-3 已解决）。
