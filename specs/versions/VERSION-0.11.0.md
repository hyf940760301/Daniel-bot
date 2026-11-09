# A 管线 0.11.0 —— 业务判断下沉（clarify / screen_ask 切到 CLI）

- **发布日期**：2026-10-31
- **前序版本**：0.10.0
- **语料版本**：0.9.206（源 `docs/marketing/skills/kol-intelligence.md`；C18 三处＋版本链五处一致）
- **CLI 命令**：89 → **91**（新增 `daniel clarify plan`／`daniel clarify ask`）
- **插件工具**：仍 15 个；`daniel_clarify`／`daniel_screen_ask` 的行为与输出**逐字节不变**

## 本次改动

1. **判断下沉**：28 条参数级追问（4 场景）＋ 5 类选择面 ＋ 触发词 ＋ 轮次规则，全部落在
   语义登记表（附录 B.5／B.2 五组改写）＋ CLI ＋ 包内 `clarify_triggers.json`；
   插件 `lib/clarify.js` 从 531 行降到 **53 行**，只剩 argv 组装与结果透传（无文案、无判据）。
2. **新增两条 CLI 命令**：`clarify plan`（一次给全）／`clarify ask`（按覆盖度动态追问），
   离线、纯本地、不取数；空 need 走 usage 闸（exit 2）。
3. **门禁**：C19-f（登记表 4 场景/28 条/5 组结构）、C20（登记表 ↔ 触发词双向对账）、
   `clarify_parity_check.py`（L1 语义／L2 键序／L3 渲染哈希，60 次比对）接入 `selfcheck.sh` 第 5/6 步。
4. **插件安全**：CLI 子进程不再继承模型 Key（`SECRET_ENV` 白名单式删除），`command` 写死为
   `clarify`／`screen_ask`（不透传 CLI 的 `clarify.plan`）。
5. **金标准**：采集层做路径归一化（绝对/相对包路径 → `<PATH>`），基线机器无关；
   golden 26/26、clarify 用例 9/9 逐字节不变；`test-clarify` 36/36（A1–A6 等价断言）。

## 兼容性与回退

- 用户可见行为**不变**：同样的 need/reply/round → 同样的清单与话术（golden 逐字节比对为证）。
- 已知 bug-compatible（不在本版修）：`inferTopic` 对「品牌＋找红人」判成品牌建档（TICKET-282）、
  `screenPlan` 的 `need` 死参数（TICKET-283）、轮次字面量 3（282）、`parseScreenReply` 双调（284）。
- 回退：`tmp/rollback-S3/` 下按阶段留有快照（M1／M2／M3／M4）；插件侧回退 0.10.0 即恢复 JS 判断。

## 验收证据（本版出包时）

- `daniel schema --check` 10/10（91 命令／23 模块）
- C19 绿／C20 绿／语料同步 9/9
- `clarify_parity_check --check`：60 次比对全绿（plan 29＋ask 23＝52 个独立形态）
- `test-clarify` 36/36；golden 26/26（clarify 9/9 逐字节不变，基线机器无关）
