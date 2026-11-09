# 管线 A · 恢复点（2026-11-02 17:45）

## 一句话状态

桌面端外壳 + 登录 + 引导 + 主界面左栏（执行透视）+ 全景地图弹窗**全部交付并真机验收通过**；剩 S6.3 两道能力门、S7 分发、S8 归档。

## 当前可用产物

| 项 | 路径 |
|---|---|
| 安装包 | `daniel-bot/releases/daniel-bot-0.2.2-alpha.2-mac-arm64-unsigned.dmg`（17:31，包内 app 17:29） |
| 二开补丁 | `daniel-bot/app/desktop-patches/0001-daniel-bot.patch`（211 文件 / 10063 行） |
| 构建工作树 | `/tmp/dsh-build/dsh-src`（**注意：/tmp 关机清空**，重建方式见下） |
| 插件包 | `daniel-bot-插件包/0.11.0/` + `releases/*.tgz` |

## 重建工作树（若 /tmp 丢失）

```bash
# 1. 取官方源码到 /tmp（不要在 iCloud 目录构建）
git clone <官方 DSH 仓库> /tmp/dsh-build/dsh-src && cd /tmp/dsh-build/dsh-src
git checkout ce7073d5
# 2. 应用补丁
git apply "/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/app/desktop-patches/0001-daniel-bot.patch"
# 3. 装依赖（Electron 走镜像）
export ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
export ELECTRON_CUSTOM_DIR="{{ version }}"
export PATH="/Users/huyifan/Desktop/DeepSeek Harness/daniel-bot/build/toolchain/node24/bin:$PATH"
pnpm install
# 4. 打包
cd apps/desktop && pnpm run package:mac:arm64:unsigned
```

## 已完成（按层）

| 层 | 内容 | 门禁 |
|---|---|---|
| 品牌 | 名称/图标/Bundle ID/关于页/8 语言标题 | G0/G2 |
| 登录 | 桌面闸门 + 应用内 Daniel 账号（不跳 DP） | 真机 4 项 |
| 引导 | Daniel 视觉、无"办公/创作"、无额度页 | 真机 |
| 视觉 | token 层换肤（45 token）+ 对比度调整 | 546 测试 |
| 左栏 | 真实列 48/320；执行透视（9 模块、进度线、去重、每任务重置） | 33 测试 + 真机 5 项 |
| 全景地图 | 弹窗、9 模块/31 功能/31 话术、只填不发 | 51 测试 + 真机 |
| 更新 | 全链路关闭 | 代码审查 |
| 插件 | 0.11.0 内嵌、入口隐藏、崩溃不丢 | G1/G4 |

## 欠项

1. **S6.3 两道能力门**
   - 映射对账：已抽验 `brands list` / `account workspaces` 两条，与左栏动作一致；其余 49 条建议抽 10 条批量跑（只读）。
   - 路由抽检：10 条话术见 `daniel-bot/app/tests/routing-cases.json`，**需在运行中的应用里逐条问**（模型 + 工具都在应用内），代理环境无法代替。
2. **S7 分发**：安装说明/更新策略/给谁。
3. **S8 归档**：决策、变更、产物清单收口。

## 关键决策索引

D-056 左栏设计 → D-064 登录后退出 bug → D-065 关欢迎页 → D-066 应用内 Daniel 账号
D-067 S6 范围补全 → D-068 两道能力门 + 升级工序 → D-069 对比度
D-070 改壳真列 + 轨迹粒度 B → D-071 左栏只做透视、说明书另做 → D-072 弹窗三项 → D-073 S6 收口

## 环境事实（会咬人的）

- **不能在 `~/Desktop` 构建**：iCloud 会加 `com.apple.FinderInfo`，导致 `codesign ... detritus not allowed`；必须在 `/tmp`。
- **打包需真终端**（PTY）：`runtime:smoke` 用 pty，代理沙箱不放行 `/dev/ptmx`。
- **Electron 下载需镜像**：`ELECTRON_MIRROR` + `ELECTRON_CUSTOM_DIR="{{ version }}"`。
- **打包会重建 client bundle**（`run-gates` 的 Client bundle 步骤），只跑 `apps/desktop build` 不会更新 `lib/client.js`。
- **归档前必须校验包内 app 时间**：曾把旧包覆盖进 releases，导致用户装成旧版。
