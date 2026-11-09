#!/bin/bash
# 把品牌图标复制进构建树（打包前必跑）。
# 起因：2026-11-09 /tmp 树被清空后 apps/desktop/build/icon.icns 丢失，
# 打包静默回落到上游鲸鱼图标。品牌图标的 durable 副本在工作区 assets/。
set -euo pipefail
WS="/Users/huyifan/Desktop/DeepSeek Harness"
SRC="$WS/daniel-bot/assets/daniel-bot.icns"
DST="/tmp/dsh-build/dsh-src/apps/desktop/build/icon.icns"
[ -f "$SRC" ] || { echo "缺少品牌图标: $SRC" >&2; exit 2; }
mkdir -p "$(dirname "$DST")"
cp -f "$SRC" "$DST"
echo "品牌图标已就位: $(shasum -a 256 "$DST" | cut -c1-16)"
