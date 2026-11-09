# 管线 A · 归档索引（2026-11-02）

## 一、交付物

| 类型 | 路径 | 说明 |
|---|---|---|
| 安装包 | `daniel-bot/releases/daniel-bot-0.2.2-alpha.2-mac-arm64-unsigned.dmg` | 258 MB，包内 app 时间 17:29 |
| 二开源码补丁 | `daniel-bot/app/desktop-patches/0001-daniel-bot.patch` | 211 文件 / 10063 行，G0 12 项通过 |
| 分发说明 | `daniel-bot/分发说明.md` | 给内测同事看 |
| 插件包 | `daniel-bot-插件包/0.11.0/` + `releases/*.tgz` | 210 文件，hash `bc34a72f…` |
| 升级工序 | `daniel-bot/app/scripts/upgrade-plugin.mjs` + `specs/UPGRADE-PLUGIN.md` | 换版本一条命令 + 6 条验收 |
| 恢复点 | `daniel-bot/specs/RESUME-A.md` | /tmp 丢失后的重建方式 |

## 二、变更说明（按主题）

| 文件 | 覆盖 |
|---|---|
| `CHANGES-BRAND.md` | 品牌名/图标/Bundle ID/关于页/8 语言 |
| `CHANGES-LOGIN.md` | 桌面登录闸门、session 0600 |
| `CHANGES-ONBOARDING.md` | 引导页 Daniel 化（删"办公/创作"） |
| `CHANGES-DANIEL-AUTH.md` | 应用内账号接 Daniel（不跳 DP） |
| `CHANGES-THEME.md` | 45 个 token 换肤 + 对比度 |
| `CHANGES-CAPABILITY-MAP.md` | 左栏能力栏（v1，后被 v2 取代） |
| `CHANGES-RAIL-COLUMN.md` | 改壳：能力栏成真实列 |
| `CHANGES-TRACE.md` | 执行轨迹（v1） |
| `CHANGES-RAIL-V2.md` | 左栏 v2：9 模块 + 进度线 + `daniel_run` 映射 + 去重 |
| `CHANGES-GUIDE.md` | 全景地图弹窗（只填不发） |

## 三、决策索引（D-055 → D-074）

| 编号 | 内容 |
|---|---|
| D-055 | 二开范围与边界 |
| D-056/D-057 | 左栏设计（能力地图 + 字段级轨迹，默认收起） |
| D-058 | 一期只读 |
| D-059 | 两条管线独立 |
| D-060 | 助手自写阶段的"为什么这么写" |
| D-064 | 登录后进程退出 → 早期 `window-all-closed` 守卫 |
| D-065 | 删官方欢迎/DP 授权窗 |
| D-066 | 应用内登录接 Daniel + DP Key 保留 |
| D-067 | S6 范围补全（视觉为新增子项） |
| D-068 | 两道能力门 + S7.1 升级工序 |
| D-069 | 对比度：文字/按钮 `#22668F` |
| D-070 | 改壳真列 + 轨迹粒度 B |
| D-071 | 左栏只做执行透视，说明书另做弹窗 |
| D-072 | 弹窗：入口/深度/预填三定 |
| D-073 | S6 收口（真机 5 项过） |
| D-074 | 布局维持原样；路由抽检延后 |

## 四、门禁状态（如实）

| 门 | 结果 |
|---|---|
| G0 代码（12 项） | PASS |
| G1 契约 | PASS 10 / SKIP 2 |
| G2 打包（14 项） | PASS |
| G3 安装/运行 | SKIP（代理沙箱无法启动 GUI；真机由用户完成） |
| G4 崩溃恢复 | SKIP（同上） |
| 隔离检查（6 项） | PASS |
| 单测 | client 51 + theme/account 546 等全绿 |
| 真机验收 | 外壳/登录/引导/左栏/弹窗共 13 项，全过 |
| **路由抽检（10 条）** | **DEFERRED（未做）** |
| 映射对账（11 条） | PASS 11/0 |

## 五、已知限制

1. **未签名未公证**：用户首次打开需「仍要打开」；
2. **无自动更新**：换版本重装；
3. **路由抽检未做**：不声称已通过；
4. **布局未定稿**：能力栏位置等 UI 意见；
5. 深色模式下左侧栏与对话区对比度依赖系统主题；
6. 只读对账覆盖 11 条，其余按抽样推定。
