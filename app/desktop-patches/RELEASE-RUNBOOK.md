# 发版流程（标准动作 · 不要再自由发挥）

> 2026-11-09 立。起因：上下文压缩后丢了"打包由用户跑"的约定，代理自己试打包，绕了一小时。
> **铁律：打包命令由 Jack 在真实终端执行；代理只准备环境、给命令、做打包后校验。**

## 一、代理负责（打包前）

0. **品牌图标就位**（每次重建树后必跑）：
   ```bash
   "/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/app/scripts/ensure-brand-icon.sh"
   ```
   期望输出 `0ee602f27430b98e`。漏跑会静默回落到上游鲸鱼图标（2026-11-09 已踩过）。

1. `/tmp/dsh-build/dsh-src` 树就绪（干净副本重建 + `pnpm install --store-dir /private/tmp/.pnpm-store` + 应用补丁 + 同步插件 vendor）
2. 跑门禁：`G0`（12/0）、`G1`（10/0，2 项无产物跳过）、插件单测
3. 把下面「二」的命令原样给用户

## 二、Jack 执行（打包）

```bash
cd /tmp/dsh-build/dsh-src
export PATH="/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/build/toolchain/node24/bin:$PATH"
export ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
export ELECTRON_CUSTOM_DIR="{{ version }}"
cd apps/desktop
pnpm run package:mac:arm64:unsigned
```

产物：`.desktop-build/targets/mac-arm64/unsigned-artifacts/daniel-bot-<版本>-mac-arm64-unsigned.dmg`

> 为什么必须由用户跑：打包脚本含 `runtime-payload-smoke`，需要真实 PTY（`/dev/ptmx`）。沙箱里 `posix_openpt` 返回 `Operation not permitted`，必失败。

## 三、代理归档（打包后第一件事）

```bash
cp -f "<unsigned-artifacts 里的 dmg>" \
  "/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/releases/daniel-bot-<版本>-mac-arm64-unsigned.dmg"
```

**安装一律从这个 releases 路径取**，不用 unsigned-artifacts 里的临时件。

## 四、安装（Jack 执行）

```bash
pkill -f "Daniel Bot" 2>/dev/null; sleep 1
rm -rf "/Applications/Daniel Bot.app"
open "/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/releases/daniel-bot-<版本>-mac-arm64-unsigned.dmg"
```

`open` 挂载 DMG 并弹 Finder，**把 Daniel Bot.app 拖进 Applications**。

> 首次启动会重拷插件（218 文件），多等 2–3 秒。

## 五、验证（三条，别扩展）

```bash
# 1) 版本
defaults read "/Applications/Daniel Bot.app/Contents/Info.plist" CFBundleShortVersionString

# 2) 随包插件
cat "/Applications/Daniel Bot.app/Contents/Resources/vendor/daniel-dsh-plugin/package.json" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('插件', d['version'])"

# 3) 时间（确认新包）
stat -f "App: %Sm" -t "%Y-%m-%d %H:%M:%S" "/Applications/Daniel Bot.app"
```

## 六、代理负责（安装后）

1. 包内校验：插件 root hash、**App 图标 hash（应为 `0ee602f2…`，不是 `8d84ca64…`）**、关键界面文案
2. 跑 G2
3. 给界面验收清单

## 七、版本完成后：推送 GitHub（仅新分支）

> 触发时机：**每次版本更新完成**（打包、安装、三条验证都过）之后。
> 仓库：`git@github.com:hyf940760301/Daniel-bot.git`
> **铁律：只推新分支 `pc-app-version`，不碰 `main`，不开 PR、不合并。**

### 推送内容（B：桌面应用项目）
| 目录 | 推 |
|---|---|
| `daniel-bot/app/`（补丁、脚本、测试、指南） | ✅ |
| `daniel-bot/packages/`（插件源码） | ✅ |
| `daniel-bot/docs/`、`assets/`、`specs/` | ✅ |
| `daniel-bot/build/`（5.6G 干净树） | ❌ |
| `daniel-bot/releases/`（DMG 250M+） | ❌ |

### 步骤
```bash
# 1) 在独立工作副本里建孤儿分支（不继承 main 历史）
cd /tmp/daniel-bot-push
git init
git remote add origin git@github.com:hyf940760301/Daniel-bot.git
git checkout --orphan pc-app-version

# 2) 放文件（排除 build/ releases/ node_modules .DS_Store）
rsync -a --exclude build --exclude releases --exclude node_modules --exclude .DS_Store \
  "/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/" ./

# 3) 提交并只推这个分支
git add -A
git commit -m "chore(pc-app): <版本号> 桌面应用工程快照"
git push -u origin pc-app-version
```

### 推送后校验
1. `git ls-remote origin pc-app-version` 有输出；
2. `main` 的 commit 与推送前一致（没有被动过）；
3. 仓库页面能看到新分支。

### 凭据
SSH（`~/.ssh/id_rsa`）已可用，实测 `ls-remote` 通。
