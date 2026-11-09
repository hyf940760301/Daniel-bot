#!/usr/bin/env bash
# Daniel Bot · DSH 插件安装器（自包含：插件包内已带完整能力，不需要本机另装 CLI）
# 用法：
#   bash scripts/install.sh                 # 自动选择 profile（PC 客户端=desktop，dsh web=web）
#   bash scripts/install.sh --profile web   # 指定 profile
#   bash scripts/install.sh --no-patch      # 只放插件，不改 patch 层
set -euo pipefail

PROFILE=""
WRITE_PATCH=1
while [ $# -gt 0 ]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --no-patch) WRITE_PATCH=0; shift ;;
    *) echo "未知参数: $1"; exit 2 ;;
  esac
done

DSH_HOME="${DSH_HOME:-$HOME/.dsh}"
PKG_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ -z "$PROFILE" ]; then
  if [ -d "$DSH_HOME/profiles/desktop" ]; then PROFILE="desktop"
  elif [ -d "$DSH_HOME/profiles/web" ]; then PROFILE="web"
  else echo "✗ 找不到 DSH profile（$DSH_HOME/profiles 下既没有 desktop 也没有 web）" >&2; exit 3; fi
fi
NM="$DSH_HOME/profiles/node_modules"
PATCH="$DSH_HOME/profiles/$PROFILE/cordis.patch.yml"
echo "① 目标 profile: $PROFILE"

test -f "$PKG_DIR/vendor/data/daniel-cli/bin/daniel" || { echo "✗ 插件包内缺 vendor 能力，包不完整" >&2; exit 4; }
echo "② 包内能力自检: vendor 在位（$(find "$PKG_DIR/vendor" -type f | wc -l | tr -d ' ') 个文件）"

mkdir -p "$NM"
rm -rf "$NM/daniel-dsh-plugin"
cp -R "$PKG_DIR" "$NM/daniel-dsh-plugin"
echo "③ 插件已装入: $NM/daniel-dsh-plugin"

if [ "$WRITE_PATCH" = "1" ]; then
  mkdir -p "$(dirname "$PATCH")"
  [ -f "$PATCH" ] && cp "$PATCH" "$PATCH.bak-$(date +%Y%m%d-%H%M%S)"
  python3 - "$PATCH" <<'PY'
import io, os, sys
patch_path = sys.argv[1]
entry = """# dsh profile patch layer（由 daniel-dsh-plugin 安装器写入；insert 语法插入一个插件条目）
- insert:
    - id: daniel
      name: daniel-dsh-plugin
      config:
        # 入口与能力都在包内 vendor，无需指定 entry；如需覆盖可加 entry: "/abs/path/bin/daniel"
        python: "python3"
        danielHome: "%s/Library/Application Support/DanielCopilot"
        timeoutMs: 180000
""" % os.environ.get('HOME', '')
old = ""
try:
    old = io.open(patch_path, encoding="utf-8").read()
except OSError:
    pass
if "daniel-dsh-plugin" in old:
    print("④ patch 层已存在 daniel 条目，未改动（改配置请手动编辑 %s）" % patch_path)
else:
    io.open(patch_path, "w", encoding="utf-8").write(entry)
    print("④ patch 层已写入:", patch_path)
PY
fi

echo "⑤ 完成。接下来：重启一次 DSH（退出后重新打开 PC 客户端 / 重新 dsh web），"
echo "   然后在会话里让 agent 调 daniel_status 确认能干活。"
