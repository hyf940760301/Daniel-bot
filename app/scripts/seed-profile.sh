#!/usr/bin/env bash
#
# seed-profile.sh — M0：把 Daniel 插件种进 DSH 的 web profile，并写出启动用的 app-overlay.yml
#
# 幂等：可重复执行；已就位的步骤只做校验、不重写文件（时间戳也不变）。
#
# 用法：
#   bash scripts/seed-profile.sh --app <DanielBot.app> --home <DANIEL_HOME> --dsh-home <DSH_HOME>
#   bash scripts/seed-profile.sh --app <DanielBot.app> --write-manifest   # 构建期：生成 PLUGIN-MANIFEST.json
#
#   --app        .app 包路径（也接受已组装好的 Resources 目录，供开发期使用）
#   --home       DANIEL_HOME（Daniel CLI / 插件的数据落点）
#   --dsh-home   DSH_HOME（DSH 自己的数据落点，与上面的 home 必须是两个目录，§2.5）
#   --write-manifest  只做「复算插件哈希 → 写 <Resources>/PLUGIN-MANIFEST.json」并退出
#
# 退出码：
#   0 成功
#   2 参数 / 路径不合法（缺参数也走这里）
#   3 完整性校验失败（清单失配、插件未挂载、出现 skipping profile bundle）
#   4 环境不可用（找不到能跑 DSH 的解释器，或 dump-config 本身失败）
#
# 依据：S2-方案设计.md v8 §2.5（两个 home）、§2.6（overlay 5 键写全）、
#      §3.1（启动时序 5/6/11）、§3.5（插件校验与重植）、§5.2（插件装成真目录）、§5.4（哈希算法）
#
set -euo pipefail
export LC_ALL=C   # 字节序排序：§5.4 的 root_hash 算法依赖它

PROG="$(basename "$0")"
EXIT_USAGE=2
EXIT_INTEGRITY=3
EXIT_ENV=4

PLUGIN_NAME="daniel-dsh-plugin"
PROFILE_NAME="web"
TRACE_MODE="summary"
TIMEOUT_MS="180000"

say()  { printf '%s\n' "$*"; }
step() { printf '\n── %s\n' "$*"; }
ok()   { printf '   ✓ %s\n' "$*"; }
warn() { printf '   ! %s\n' "$*" >&2; }
die()  { local code="$1"; shift; printf '\n✗ %s\n' "$*" >&2; exit "$code"; }

usage() {
  cat <<'USAGE'
seed-profile.sh — 把 Daniel 插件种进 DSH web profile

用法：
  bash scripts/seed-profile.sh --app <DanielBot.app> --home <DANIEL_HOME> --dsh-home <DSH_HOME>
  bash scripts/seed-profile.sh --app <DanielBot.app> --write-manifest

参数：
  --app <路径>        .app 包路径；也接受已组装好的 Resources 目录（开发期）
  --home <路径>       DANIEL_HOME（Daniel CLI / 插件的数据落点）
  --dsh-home <路径>   DSH_HOME（DSH 自己的数据落点；必须与 --home 分开）
  --write-manifest    只复算插件哈希并写 <Resources>/PLUGIN-MANIFEST.json，然后退出（构建期用）
  -h, --help          显示本帮助

退出码：0 成功 / 2 参数不合法 / 3 完整性校验失败 / 4 环境不可用
USAGE
}

# ── 参数 ──────────────────────────────────────────────────────────────────────
APP_ARG=""
DANIEL_HOME_ARG=""
DSH_HOME_ARG=""
WRITE_MANIFEST=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --app)
      [ "$#" -ge 2 ] || die "$EXIT_USAGE" "--app 缺少路径"
      APP_ARG="$2"; shift 2 ;;
    --home)
      [ "$#" -ge 2 ] || die "$EXIT_USAGE" "--home 缺少路径"
      DANIEL_HOME_ARG="$2"; shift 2 ;;
    --dsh-home)
      [ "$#" -ge 2 ] || die "$EXIT_USAGE" "--dsh-home 缺少路径"
      DSH_HOME_ARG="$2"; shift 2 ;;
    --write-manifest)
      WRITE_MANIFEST=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      die "$EXIT_USAGE" "未知参数：$1（用 --help 看用法）" ;;
  esac
done

# ── 工具 ──────────────────────────────────────────────────────────────────────
abs_dir() { ( cd "$1" && pwd -P ); }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/seed-profile.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT INT TERM

# 内嵌工具脚本：JSON 结构改动 + 插件哈希清单（§5.4 算法），避免依赖任何 npm 包
cat > "$WORK/patch-pkg.mjs" <<'JS'
// 幂等地把 daniel-dsh-plugin 声明进 profile 的 package.json：
//   dsh.profile.bundles 追加（保持顺序）＋ dependencies 用 file: 指向已复制的目录。
// 只在内容真的变化时才写盘（tmp+rename），第二次运行保持文件不动。
import { readFileSync, writeFileSync, renameSync } from 'node:fs'

const [pkgPath, depSpec, pluginName] = process.argv.slice(2)
const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'))
pkg.dsh ??= {}
pkg.dsh.profile ??= {}
const bundles = (pkg.dsh.profile.bundles ??= [])
const deps = (pkg.dependencies ??= {})

let changed = false
if (!bundles.includes(pluginName)) {
  bundles.push(pluginName)
  changed = true
}
if (deps[pluginName] !== depSpec) {
  deps[pluginName] = depSpec
  changed = true
}

if (changed) {
  const tmp = `${pkgPath}.tmp-seed-${process.pid}`
  writeFileSync(tmp, JSON.stringify(pkg, null, 2) + '\n', { mode: 0o644 })
  renameSync(tmp, pkgPath)
  console.log('patched')
} else {
  console.log('unchanged')
}
JS

cat > "$WORK/plugin-manifest.mjs" <<'JS'
// 插件文件哈希清单（S2 §5.4 的固定算法）：
//   · 路径用 /、相对清单根、按 UTF-8 字节序排序；
//   · 每行 "sha256  size  path\n"，对整段再 sha256 → root_hash；
//   · 不含时间戳，mode 只作记录不参与 root_hash；软链必须 0。
// 用法：plugin-manifest.mjs <compute|verify|write> <pluginDir> [manifestPath]
import { createHash } from 'node:crypto'
import { readFileSync, readdirSync, statSync, writeFileSync, existsSync } from 'node:fs'
import { join, relative, sep, basename } from 'node:path'

const [mode, rootDir, manifestPath] = process.argv.slice(2)
if (!mode || !rootDir) {
  console.error('用法：plugin-manifest.mjs <compute|verify|write> <pluginDir> [manifestPath]')
  process.exit(2)
}

const symlinks = []
const files = []

function walk(dir) {
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    const abs = join(dir, ent.name)
    const rel = relative(rootDir, abs).split(sep).join('/')
    if (ent.isSymbolicLink()) {
      symlinks.push(rel)
      continue
    }
    if (ent.isDirectory()) {
      walk(abs)
      continue
    }
    if (!ent.isFile()) continue
    const st = statSync(abs)
    files.push({
      abs,
      path: rel,
      size: st.size,
      mode: (st.mode & 0o777).toString(8).padStart(4, '0'),
    })
  }
}

walk(rootDir)
files.sort((a, b) => Buffer.compare(Buffer.from(a.path, 'utf8'), Buffer.from(b.path, 'utf8')))

const algo = 'sha256'
for (const f of files) f.sha256 = createHash(algo).update(readFileSync(f.abs)).digest('hex')

const rootHash =
  algo + ':' + createHash(algo).update(
    files.map((f) => `${f.sha256}  ${f.size}  ${f.path}\n`).join('')
  ).digest('hex')

if (symlinks.length > 0) {
  console.error(`清单不允许软链（实测 ${symlinks.length} 条）：${symlinks.slice(0, 3).join(', ')}`)
  process.exit(1)
}

const summary = `files=${files.length}\nroot_hash=${rootHash}\nsize=${files.reduce((n, f) => n + f.size, 0)}`

if (mode === 'write') {
  if (!manifestPath) {
    console.error('write 模式需要 manifestPath')
    process.exit(2)
  }
  const manifest = {
    schema: 1,
    root: basename(rootDir),
    root_hash: rootHash,
    symlinks: 0,
    files: files.map((f) => ({ path: f.path, size: f.size, sha256: f.sha256, mode: f.mode })),
  }
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n', { mode: 0o644 })
  console.log(summary)
  process.exit(0)
}

if (mode === 'verify') {
  if (!manifestPath || !existsSync(manifestPath)) {
    console.error(`清单不存在：${manifestPath ?? '(未给出)'}`)
    process.exit(2)
  }
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  const declared = new Map((manifest.files ?? []).map((f) => [f.path, f]))
  const actual = new Map(files.map((f) => [f.path, f]))
  const problems = []

  for (const [path, want] of declared) {
    const got = actual.get(path)
    if (!got) { problems.push(`缺少文件：${path}`); continue }
    if (got.size !== want.size) { problems.push(`大小不符：${path}（清单 ${want.size} / 实际 ${got.size}）`); continue }
    if (got.sha256 !== want.sha256) { problems.push(`哈希不符：${path}\n      清单 ${want.sha256}\n      实际 ${got.sha256}`) }
  }
  for (const path of actual.keys()) if (!declared.has(path)) problems.push(`多出文件：${path}`)

  if (manifest.root_hash !== rootHash) {
    problems.unshift(`root_hash 不符：清单 ${manifest.root_hash} / 实际 ${rootHash}`)
  }
  if (manifest.symlinks !== 0) problems.unshift(`清单声明了软链：${manifest.symlinks}`)

  if (problems.length > 0) {
    console.error(`✗ ${problems.length} 项失配（清单 ${manifestPath}）`)
    for (const p of problems.slice(0, 8)) console.error(`  · ${p}`)
    if (problems.length > 8) console.error(`  · …另有 ${problems.length - 8} 项`)
    process.exit(1)
  }
  console.log(summary)
  process.exit(0)
}

// compute
console.log(summary)
JS

# ── 定位 Resources ───────────────────────────────────────────────────────────
[ -n "$APP_ARG" ] || die "$EXIT_USAGE" "缺少 --app <app 路径>"
step "定位应用资源"

[ -d "$APP_ARG" ] || die "$EXIT_USAGE" "--app 不是目录：$APP_ARG"
APP_ABS="$(abs_dir "$APP_ARG")"

if [ -f "$APP_ABS/Contents/Resources/vendor/$PLUGIN_NAME/package.json" ]; then
  R="$(abs_dir "$APP_ABS/Contents/Resources")"
  LAYOUT=".app 包"
elif [ -f "$APP_ABS/vendor/$PLUGIN_NAME/package.json" ]; then
  R="$APP_ABS"
  LAYOUT="Resources 目录（开发期）"
else
  die "$EXIT_USAGE" "--app 下找不到 vendor/$PLUGIN_NAME/package.json（既不是 .app，也不是组装好的 Resources 目录）：$APP_ABS"
fi

SRC="$R/vendor/$PLUGIN_NAME"
PLUGIN_ENTRY="$SRC/vendor/data/daniel-cli/bin/daniel"
MANIFEST="$R/PLUGIN-MANIFEST.json"

ok "应用：$APP_ABS"
ok "资源：$R（$LAYOUT）"
[ -f "$PLUGIN_ENTRY" ] || die "$EXIT_INTEGRITY" "插件里缺 CLI 入口：$PLUGIN_ENTRY"
[ -f "$SRC/cordis.patch.yml" ] || die "$EXIT_INTEGRITY" "插件里缺 cordis.patch.yml：$SRC/cordis.patch.yml"

# 选一个能跑 DSH 的解释器。优先系统 node（Electron 38 的内置 Node 在真正 boot 时
# 会被 DSH 的原生加载器拒绝，见 README「已知边界」）；退而用 Electron 的 RUN_AS_NODE
# ——dump-config 不触达 boot 路径，可以跑。
#
# 注意：PATH 里的 `electron` 只是 `#!/usr/bin/env node` 的壳，没 node 时起不来，
# 所以要找真正的 Electron 二进制（应用自带的，或 npm 包里的 path.txt 指向的那个）。
find_electron_binary() {
  local f base p
  if [ -d "$APP_ABS/Contents/MacOS" ]; then
    for f in "$APP_ABS"/Contents/MacOS/*; do
      [ -f "$f" ] && [ -x "$f" ] || continue
      printf '%s\n' "$f"; return 0
    done
  fi
  for base in "$HOME/.npm-global/lib/node_modules/electron" \
              "/usr/local/lib/node_modules/electron" \
              "/opt/homebrew/lib/node_modules/electron"; do
    [ -f "$base/path.txt" ] || continue
    # path.txt 里的路径相对 electron 包的 dist/（例：Electron.app/Contents/MacOS/Electron）
    p="$(cat "$base/path.txt")"
    case "$p" in /*) ;; *) p="$base/dist/$p" ;; esac
    [ -x "$p" ] && { printf '%s\n' "$p"; return 0; }
  done
  return 1
}

NODE_KIND=""
NODE_BIN=""
ELECTRON_BIN=""
if command -v node >/dev/null 2>&1; then
  NODE_KIND="node"; NODE_BIN="$(command -v node)"
elif ELECTRON_BIN="$(find_electron_binary)"; then
  NODE_KIND="electron"
fi

run_node() {
  if [ "$NODE_KIND" = "node" ]; then
    "$NODE_BIN" "$@"
  else
    ELECTRON_RUN_AS_NODE=1 "$ELECTRON_BIN" "$@"
  fi
}

# ── 构建期：只写清单 ─────────────────────────────────────────────────────────
if [ "$WRITE_MANIFEST" -eq 1 ]; then
  step "复算插件哈希并写 PLUGIN-MANIFEST.json"
  [ -n "$NODE_KIND" ] || die "$EXIT_ENV" "找不到 node / electron，无法计算哈希"
  run_node "$WORK/plugin-manifest.mjs" write "$SRC" "$MANIFEST" >/dev/null \
    || die "$EXIT_INTEGRITY" "写清单失败：$MANIFEST"
  chmod 0644 "$MANIFEST"
  ok "已写：$MANIFEST"
  # 回读一遍，确认写进去的能验过
  run_node "$WORK/plugin-manifest.mjs" verify "$SRC" "$MANIFEST" >/dev/null \
    || die "$EXIT_INTEGRITY" "清单写完后回读校验失败：$MANIFEST"
  ok "回读校验通过"
  exit 0
fi

# ── 两个 home ────────────────────────────────────────────────────────────────
step "检查两个 home（DSH_HOME 与 DANIEL_HOME 必须分开）"

[ -n "$DANIEL_HOME_ARG" ] || die "$EXIT_USAGE" "缺少 --home <DANIEL_HOME>"
[ -n "$DSH_HOME_ARG" ] || die "$EXIT_USAGE" "缺少 --dsh-home <DSH_HOME>"

# 先按字面路径挡一次：避免「参数指错 → 先在仓库里建出目录 → 再报错」这种副作用。
precheck_path() {
  local p="$1" label="$2"
  case "$p" in "~/"*) p="$HOME/${p#\~/}" ;; esac
  case "$p" in /*) ;; *) p="$PWD/$p" ;; esac
  case "/$p/" in
    */daniel-bot/*) die "$EXIT_USAGE" "$label 落在交付副本根（daniel-bot/）里：$p —— 换到 ~/Library/Application Support/Daniel Bot/ 下" ;;
    */vendor/*)     die "$EXIT_USAGE" "$label 落在 vendor/ 里：$p —— 换到 ~/Library/Application Support/Daniel Bot/ 下" ;;
  esac
  case "$p/" in
    "${APP_ABS}/"*) die "$EXIT_USAGE" "$label 落在 .app 包内（签名后只读）：$p" ;;
  esac
}
precheck_path "$DANIEL_HOME_ARG" "DANIEL_HOME"
precheck_path "$DSH_HOME_ARG" "DSH_HOME"

mkdir -p "$DANIEL_HOME_ARG" || die "$EXIT_USAGE" "无法创建 --home：$DANIEL_HOME_ARG"
mkdir -p "$DSH_HOME_ARG" || die "$EXIT_USAGE" "无法创建 --dsh-home：$DSH_HOME_ARG"
DANIEL_HOME="$(abs_dir "$DANIEL_HOME_ARG")"
DSH_HOME="$(abs_dir "$DSH_HOME_ARG")"
chmod 700 "$DANIEL_HOME" 2>/dev/null || true

# §2.5 细节 1：DANIEL_HOME 绝不能落在交付副本根 / vendor / .app 里
# （CLI 的 refuse_reason 会拒写；.app 签名后只读）。
for p in "$DANIEL_HOME" "$DSH_HOME"; do
  case "/$p/" in
    */daniel-bot/*) die "$EXIT_USAGE" "路径落在交付副本根（daniel-bot/）里：$p —— 换到 ~/Library/Application Support/Daniel Bot/ 下" ;;
    */vendor/*)     die "$EXIT_USAGE" "路径落在 vendor/ 里：$p —— 换到 ~/Library/Application Support/Daniel Bot/ 下" ;;
  esac
  case "$p/" in
    "${APP_ABS}/"*) die "$EXIT_USAGE" "路径落在 .app 包内（签名后只读）：$p" ;;
  esac
done

[ "$DANIEL_HOME" != "$DSH_HOME" ] || die "$EXIT_USAGE" "DANIEL_HOME 与 DSH_HOME 不能是同一个目录：$DANIEL_HOME"
case "$DANIEL_HOME/" in
  "$DSH_HOME/"*) die "$EXIT_USAGE" "DANIEL_HOME 不能是 DSH_HOME 的子目录：$DANIEL_HOME ⊂ $DSH_HOME" ;;
esac
case "$DSH_HOME/" in
  "$DANIEL_HOME/"*) die "$EXIT_USAGE" "DSH_HOME 不能是 DANIEL_HOME 的子目录：$DSH_HOME ⊂ $DANIEL_HOME" ;;
esac

PROFILE="$DSH_HOME/profiles/$PROFILE_NAME"
OVERLAY="$DANIEL_HOME/app-overlay.yml"
PYTHON="$R/runtime/python/bin/python3"

ok "DANIEL_HOME：$DANIEL_HOME"
ok "DSH_HOME   ：$DSH_HOME"
[ -x "$PYTHON" ] || warn "随包 Python 还不存在：$PYTHON（overlay 照写；启动时会由端内诊断页报出来）"

# ── DSH 调用器 ───────────────────────────────────────────────────────────────
if [ -f "$R/dsh/lib/bin.js" ]; then
  DSH_JS="$R/dsh/lib/bin.js"
elif command -v dsh >/dev/null 2>&1; then
  DSH_JS=""
else
  die "$EXIT_ENV" "既没有 $R/dsh/lib/bin.js，也没有 PATH 里的 dsh"
fi

[ -n "$NODE_KIND" ] || die "$EXIT_ENV" "找不到 node / electron，无法启动 DSH"

run_dsh() {
  if [ -n "$DSH_JS" ]; then
    if [ "$NODE_KIND" = "node" ]; then
      DSH_HOME="$DSH_HOME" DANIEL_HOME="$DANIEL_HOME" "$NODE_BIN" "$DSH_JS" "$@"
    else
      DSH_HOME="$DSH_HOME" DANIEL_HOME="$DANIEL_HOME" ELECTRON_RUN_AS_NODE=1 "$ELECTRON_BIN" "$DSH_JS" "$@"
    fi
  else
    DSH_HOME="$DSH_HOME" DANIEL_HOME="$DANIEL_HOME" dsh "$@"
  fi
}

# ── 1. 让 DSH 自己建 profile ─────────────────────────────────────────────────
step "1/5 让 DSH 自建 profile：$PROFILE"

if [ -f "$PROFILE/package.json" ]; then
  ok "profile 已存在（DSH 每次启动都会重写 cordis.yml，这里不碰它）"
else
  run_dsh --profile "$PROFILE_NAME" --dump-config >"$WORK/dump-init.yml" 2>"$WORK/dump-init.err" \
    || { cat "$WORK/dump-init.err" >&2; die "$EXIT_ENV" "DSH 初始化 profile 失败（--dump-config 退出码非 0）"; }
  if grep -q 'skipping profile bundle' "$WORK/dump-init.err"; then
    cat "$WORK/dump-init.err" >&2
    die "$EXIT_INTEGRITY" "DSH 初始化 profile 时已有 bundle 被跳过（见上）"
  fi
  [ -f "$PROFILE/package.json" ] || die "$EXIT_ENV" "DSH 说成功，但 $PROFILE/package.json 不存在"
  ok "已创建：$PROFILE"
fi

# ── 2. 插件复制成真目录 ──────────────────────────────────────────────────────
step "2/5 插件复制成真目录：<profile>/node_modules/$PLUGIN_NAME"

[ -n "$NODE_KIND" ] || die "$EXIT_ENV" "找不到 node / electron，无法计算插件哈希"

if [ -f "$MANIFEST" ]; then
  if ! verify_out="$(run_node "$WORK/plugin-manifest.mjs" verify "$SRC" "$MANIFEST")"; then
    die "$EXIT_INTEGRITY" "Resources 里的插件与 $MANIFEST 不符 —— 安装已损坏，请重新下载安装包（细节见上）"
  fi
  SRC_HASH="$(printf '%s\n' "$verify_out" | sed -n 's/^root_hash=//p')"
  SRC_FILES="$(printf '%s\n' "$verify_out" | sed -n 's/^files=//p')"
  ok "Resources 插件与清单一致（$SRC_FILES 个文件，$SRC_HASH）"
else
  warn "没有 PLUGIN-MANIFEST.json —— 跳过清单校验，只算实际哈希（构建期请先跑 --write-manifest）"
  SRC_HASH="$(run_node "$WORK/plugin-manifest.mjs" compute "$SRC" | sed -n 's/^root_hash=//p')"
  SRC_FILES="$(run_node "$WORK/plugin-manifest.mjs" compute "$SRC" | sed -n 's/^files=//p')"
  ok "Resources 插件实际哈希（$SRC_FILES 个文件，$SRC_HASH）"
fi

NM="$PROFILE/node_modules"
DST="$NM/$PLUGIN_NAME"
mkdir -p "$NM"

copy_plugin() {
  local stage="$NM/.$PLUGIN_NAME.staging.$$"
  rm -rf "$stage"
  cp -R "$SRC" "$stage" || die "$EXIT_INTEGRITY" "复制插件失败：$SRC → $stage"
  rm -rf "$DST"
  mv "$stage" "$DST" || die "$EXIT_INTEGRITY" "落位插件失败：$stage → $DST"
  ok "已复制：$DST"
}

if [ -L "$DST" ]; then
  rm -f "$DST"
  warn "原来是指向别处的软链，已删掉（要求是真目录）"
fi

if [ -d "$DST" ]; then
  DST_HASH="$(run_node "$WORK/plugin-manifest.mjs" compute "$DST" | sed -n 's/^root_hash=//p')"
  if [ "$DST_HASH" = "$SRC_HASH" ]; then
    ok "profile 内插件已是真目录且与 Resources 一致（不重写）"
  else
    copy_plugin
  fi
else
  copy_plugin
fi

DST_HASH="$(run_node "$WORK/plugin-manifest.mjs" compute "$DST" | sed -n 's/^root_hash=//p')"
[ "$DST_HASH" = "$SRC_HASH" ] || die "$EXIT_INTEGRITY" "复制后哈希不一致：Resources $SRC_HASH / profile $DST_HASH"
ok "profile 内插件哈希与 Resources 一致（$SRC_HASH）"

# ── 3. package.json 声明 ─────────────────────────────────────────────────────
step "3/5 在 profile 的 package.json 里声明插件（bundles + file: 依赖）"

[ -f "$PROFILE/package.json" ] || die "$EXIT_ENV" "profile 缺 package.json：$PROFILE/package.json"
pkg_state="$(run_node "$WORK/patch-pkg.mjs" "$PROFILE/package.json" "file:./node_modules/$PLUGIN_NAME" "$PLUGIN_NAME")" \
  || die "$EXIT_ENV" "改写 $PROFILE/package.json 失败"
if [ "$pkg_state" = "patched" ]; then
  ok "已声明：dsh.profile.bundles += $PLUGIN_NAME，dependencies[\"$PLUGIN_NAME\"] = file:./node_modules/$PLUGIN_NAME"
else
  ok "声明已就位（不重写）"
fi

# ── 4. 写 app-overlay.yml（5 键写全） ────────────────────────────────────────
step "4/5 写 app-overlay.yml（overlay 的 config 是整对象替换，5 键必须写全）"

overlay_body() {
  cat <<EOF
# 由 $PROG 生成 / 每次启动重写；请勿手工编辑（改这里会被下一次启动覆盖）。
# 依据 S2 §2.6：config 是整对象替换，少写一个键就等于把那个配置删掉。
- id: daniel
  config:
    entry: "$PLUGIN_ENTRY"
    python: "$PYTHON"
    danielHome: "$DANIEL_HOME"
    timeoutMs: $TIMEOUT_MS
    trace: $TRACE_MODE
EOF
}

if [ -f "$OVERLAY" ] && overlay_body | cmp -s - "$OVERLAY"; then
  ok "内容未变（不重写）：$OVERLAY"
else
  overlay_body > "$WORK/app-overlay.yml"
  chmod 0600 "$WORK/app-overlay.yml"
  mv "$WORK/app-overlay.yml" "$OVERLAY"
  chmod 0600 "$OVERLAY"
  ok "已写：$OVERLAY（0600）"
fi

# ── 5. 回读断言：插件真的挂上了、5 键真的生效 ────────────────────────────────
step "5/5 回读断言：--dump-config 里 daniel 条目成立且 5 键生效"

if ! run_dsh --profile "$PROFILE_NAME" --patch "$OVERLAY" --dump-config >"$WORK/dump.yml" 2>"$WORK/dump.err"; then
  cat "$WORK/dump.err" >&2
  die "$EXIT_ENV" "DSH --dump-config 失败（退出码非 0）"
fi

if grep -q 'skipping profile bundle' "$WORK/dump.err"; then
  grep 'skipping profile bundle' "$WORK/dump.err" >&2
  die "$EXIT_INTEGRITY" "插件被跳过（skipping profile bundle）—— 不允许静默降级成「没有 Daniel 的 DSH」"
fi

if ! grep -q "^- id: daniel$" "$WORK/dump.yml"; then
  die "$EXIT_INTEGRITY" "dump-config 里没有 '- id: daniel' —— 挂载链断裂（插件没进 bundles，或 package.json 被改回去了）"
fi

# 把 daniel 的 config 段拉平（YAML 会把长值折行，这里合并续行），输出 key=value
extract_config() {
  awk '
    $0 == "- id: daniel" { found = 1; next }
    found && /^- id:/ { exit }
    !found { next }
    $0 == "  config:" { inconfig = 1; next }
    !inconfig { next }
    /^    [A-Za-z][A-Za-z0-9]*: / {
      if (pending != "") { print pending "=" value; pending = "" }
      line = substr($0, 5)
      key = line; sub(/:.*$/, "", key)
      value = line; sub(/^[^:]*:[ ]?/, "", value)
      if (value == ">-" || value == ">" || value == "|" || value == "|-") { pending = key; value = ""; next }
      print key "=" value
      next
    }
    pending != "" && /^      / {
      part = substr($0, 7)
      value = (value == "" ? part : value " " part)
      next
    }
    END { if (pending != "") print pending "=" value }
  ' "$WORK/dump.yml"
}

CFG="$(extract_config)"
get_cfg() { printf '%s\n' "$CFG" | sed -n "s/^$1=//p" | head -1; }

[ -n "$CFG" ] || die "$EXIT_INTEGRITY" "dump-config 里 daniel 条目没有 config 段"

expect_cfg() { # key expected
  local got
  got="$(get_cfg "$1")"
  [ "$got" = "$2" ] || die "$EXIT_INTEGRITY" "overlay 的 $1 没生效：期望 '$2'，实际 '$got'"
  ok "$1 = $2"
}

expect_cfg entry "$PLUGIN_ENTRY"
expect_cfg python "$PYTHON"
expect_cfg danielHome "$DANIEL_HOME"
expect_cfg timeoutMs "$TIMEOUT_MS"
expect_cfg trace "$TRACE_MODE"

key_count="$(printf '%s\n' "$CFG" | grep -c '^[A-Za-z]' || true)"
[ "$key_count" = "5" ] || die "$EXIT_INTEGRITY" "config 应有 5 个键，dump 里是 $key_count 个（overlay 少写＝删键）"
ok "5 个键齐全（entry / python / danielHome / timeoutMs / trace）"

# ── 结果 ─────────────────────────────────────────────────────────────────────
# 这一段只写「结果状态」，不写「本次做了什么」——所以两次运行的这一段逐字相同，
# 幂等可以直接用 diff 证明（动作差异在上面的步骤行里）。
step "结果（幂等：这一段两次运行逐字相同）"
cat <<EOF
   app resources : $R
   dsh home      : $DSH_HOME
   daniel home   : $DANIEL_HOME
   profile       : $PROFILE
   plugin        : $SRC_FILES 个文件 / root_hash $SRC_HASH
   overlay       : $OVERLAY
   mounted       : $PLUGIN_NAME（dump-config 已确认 5 键生效）
EOF

say ""
say "完成。"
