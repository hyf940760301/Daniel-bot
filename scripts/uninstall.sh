#!/usr/bin/env bash
# 卸载 Daniel Bot 的 DSH 插件（不动 Daniel 的数据与会话）
set -euo pipefail
PROFILE="${1:-}"
DSH_HOME="${DSH_HOME:-$HOME/.dsh}"
[ -z "$PROFILE" ] && { [ -d "$DSH_HOME/profiles/desktop" ] && PROFILE=desktop || PROFILE=web; }
NM="$DSH_HOME/profiles/node_modules"
PATCH="$DSH_HOME/profiles/$PROFILE/cordis.patch.yml"

rm -rf "$NM/daniel-dsh-plugin" && echo "① 已移除插件: $NM/daniel-dsh-plugin"
if [ -f "$PATCH" ] && grep -q "daniel-dsh-plugin" "$PATCH"; then
  cp "$PATCH" "$PATCH.bak-uninstall-$(date +%Y%m%d-%H%M%S)"
  python3 - "$PATCH" <<'PY'
import io, sys
p = sys.argv[1]
txt = io.open(p, encoding="utf-8").read()
# 只删本产品的 insert 块（到下一个顶层 "- " 或文件尾为止）
lines = txt.split("\n"); out=[]; skip=False
for ln in lines:
    if ln.strip().startswith("- insert:"):
        skip = True
    elif skip and ln.startswith("- ") and not ln.strip().startswith("- insert:"):
        skip = False
    if not skip:
        out.append(ln)
new = "\n".join(out)
if "daniel-dsh-plugin" in new:   # 兜底：整体重置为空数组（仅当文件里只剩本产品）
    new = "# dsh profile patch layer\n[]\n"
io.open(p, "w", encoding="utf-8").write(new)
print("② 已从 patch 层移除 daniel 条目:", p)
PY
else
  echo "② patch 层没有 daniel 条目，跳过"
fi
echo "③ 完成。重启 DSH 后该插件工具即消失（Daniel 的数据／登录态不受影响）。"
