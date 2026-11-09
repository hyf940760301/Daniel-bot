#!/usr/bin/env bash
# Daniel CLI 仓库自检链（TICKET-145 §3；TICKET-146 增补第 4 步）
#
# 依次跑五步（任一步失败也继续跑完，最后统一汇总；退出码 0＝全绿）：
#   1/5 schema 一致性      —— 单一真源自证（CLI 注册集合 ≡ 清单声明集合 ≡ 实现注册表）
#   2/5 12 模块只读冒烟    —— `daniel --self-test`（含退出码语义、--json 可解析、零 DSH 依赖、
#                            凭据来源矩阵断言、P 组「契约引擎自证（引擎级最小）」、W 组
#                            「权限与门禁（能力矩阵／无权路径／删除凭据／审计／干跑零写）」；
#                            **不写钥匙串、不做任何真实写**）
#                            注：P 组**不重复跑逐契约期望核对**，那是第 4 步的事（P1-6 去重）
#   3/5 分发物凭据断言     —— `.kol-tools/check_no_secrets_in_dist.py`：先自检，再干净扫描 data/ 与 docs/
#   4/5 契约引擎自证       —— `daniel playbook selfcheck`：**逐契约期望核对的唯一入口**，把契约目录里
#                            每份契约按它声明的三条路径（默认／干跑／带确认）各跑一遍并核对期望
#                            （含退化样本：样本超限、写步骤未确认、对例判据失败）
#   5/5 汇总
#
# 用法：
#   bash data/daniel-cli/selfcheck.sh
#
# 注：沙箱内把数据落点钉在工作区（`DANIEL_HOME=<仓库根>/.daniel-home`），这是临时口径；
#     想用系统默认落点就自己 `export DANIEL_HOME=...` 后再跑。

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
DANIEL="$HERE/bin/daniel"
PY="${PYTHON:-python3}"
export DANIEL_HOME="${DANIEL_HOME:-$ROOT/.daniel-home}"

declare -a NAMES=() CODES=() SECS=()
T0=$(date +%s)
# step <名称> <退出码>；耗时由上一次 step 到现在自动记账
step() { NAMES+=("$1"); CODES+=("$2"); SECS+=("$(( $(date +%s) - T0 ))"); T0=$(date +%s); }

echo "Daniel CLI 自检链"
echo "仓库根：$ROOT"
echo "数据落点：DANIEL_HOME=$DANIEL_HOME"
echo "能力目录：$ROOT/.kol-tools"
echo

echo "── 1/5 schema 一致性 ──────────────────────────────────────────"
"$PY" "$DANIEL" schema --check
schemas_rc=$?
step "1/5 schema 一致性" "$schemas_rc"
echo

echo "── 2/5 12 模块只读冒烟（含退出码／JSON／零 DSH 依赖／凭据矩阵／契约引擎／权限与门禁）──"
"$PY" "$DANIEL" --self-test
selftest_rc=$?
step "2/5 12 模块只读冒烟" "$selftest_rc"
echo

echo "── 3/5 分发物凭据断言 ────────────────────────────────────────"
"$PY" "$ROOT/.kol-tools/check_no_secrets_in_dist.py" --self-test
dist_selftest_rc=$?
"$PY" "$ROOT/.kol-tools/check_no_secrets_in_dist.py" "$ROOT/data" "$ROOT/docs"
dist_scan_rc=$?
if [ "$dist_selftest_rc" -eq 0 ] && [ "$dist_scan_rc" -eq 0 ]; then dist_rc=0; else dist_rc=1; fi
step "3/5 分发物凭据断言" "$dist_rc"
echo

echo "── 4/5 契约引擎自证（逐契约期望核对：唯一入口）──────────────"
"$PY" "$DANIEL" playbook selfcheck
contracts_rc=$?
step "4/5 契约引擎自证" "$contracts_rc"
echo

echo "── 5/5 汇总 ──────────────────────────────────────────────────"
fail=0
TOTAL=0
for i in "${!NAMES[@]}"; do
  TOTAL=$(( TOTAL + SECS[i] ))
  if [ "${CODES[$i]}" -eq 0 ]; then
    printf '  %-34s 通过（退出码 %s，耗时 %ss）\n' "${NAMES[$i]}" "${CODES[$i]}" "${SECS[$i]}"
  else
    printf '  %-34s 不通过（退出码 %s，耗时 %ss）\n' "${NAMES[$i]}" "${CODES[$i]}" "${SECS[$i]}"
    fail=1
  fi
done
echo "  合计耗时：${TOTAL}s"
echo
if [ "$fail" -eq 0 ]; then
  echo "结论：全绿 —— schema 与实现一致、12 模块只读链路可达、分发物 0 条凭据痕迹、契约引擎期望全中。"
else
  echo "结论：有未通过项，见上方明细。"
fi
exit "$fail"
