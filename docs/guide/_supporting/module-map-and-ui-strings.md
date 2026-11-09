# 取证底稿：Daniel 模块映射与界面文案（2026-09-28）

> **用途**：本指南的**事实来源**。指南里每一句"界面上会看到什么"都对照这里；改版时可据此复核。
> **取证方式**：读取线上前端产物（`https://daniel-agent.com/assets/*.js`）里的 **UI 字符串** —— 只读静态资源，不涉及任何账号与数据。

## 一、模块映射（导航 label → path，取自线上 `index-*.js`）

| 界面英文标签 | 路径 | 本指南用名 | 本次试用 |
|---|---|---|---|
| Brand Deep Research | `/discovery?tab=brand` | AI 红人搜索 · **品牌深度研究** | ✅ 开放 |
| AI Open Research | `/discovery?tab=open` | AI 红人搜索 · **AI 开放研究** | ✅ 开放 |
| YouTube Official | `/discovery?tab=youtube-official` | （未开放） | ❌ |
| Brand Mentions（页内 Deep Analytics） | `/brand-mentions` | **品牌内容分析** | ✅ 开放 |
| Videos | `/content/videos` | 视频追踪（Campaign 维度，非本次三模块） | — |
| Authenticity（页内标题 Authenticity Check） | `/authenticity` | **真实性分析** | ✅ 开放 |
| Creator Search / Saved Lists / Campaigns / Inbox / SOV 等 | … | 本次未开放 | ❌ |

## 五、品牌内容分析页（2026-09-29 渲染取证 · A 级）

> **取证方式**：Playwright ＋ 账号会话 cookie 打开 `https://daniel-agent.com/brand-mentions`（Halliday · jobId `4c36f144` · 创建于 2026-09-10 · 290 个视频 · 最近 180 天 · 全球），
> **读渲染后的 DOM**（不是只读 bundle 字符串）。**教训 152**：`bundle 字符串 ≠ 页面结构` —— 字符串只能证明"有这些词"，章节层级、表头列名、分档口径只有**渲染后的页面**能定。

### 页面骨架

```
H1  Brand Mention Intelligence
    发现 Organic 增长势能，并判断哪些 Brand 讨论需要关注
按钮  开始新的 Brand Mention Research
H2  Halliday（当前报告）· 创建于 2026/9/10 · 290 个视频 · 最近 180 天 · 全球
标签  总览 ｜ Top 频道 ｜ 全部视频
H4  Organic Performance ｜ 月度趋势 ｜ 表现分布 ｜ 视频类型 ｜ 真实性 ｜ 评分方法
```

### 总览指标（KPI 名逐字）

```
视频总数 │ ≥1,000 次观看 │ 已排除不相关内容 │ 总观看量（累计）│ 平均每条观看量（均值）
独立频道数（独立 Creator）│ 平均 Rated Score（加权评分 · 满分 5.00）
Organic Performance 分档：High（优先审查）／Good（尽快审查）／Average（持续观察）／Low（Organic 触达较低）
```

### 「全部视频」表（列名逐字）

```
Organic Performance（分组列）│ 视频、Creator 与内容 │ 视频分析 │ Rated Score ↓ │ 表现 │ 观看量 │ Creator 可信度
筛选：Organic Performance ｜ 内容类型 ｜ 全部格式 ｜ Confirmed + Likely ｜ 真实性 ｜ 语言 ｜ 隐藏 Official 频道
操作：导出 CSV（导出时同时获取邮箱，界面提示可能需要 30 秒）｜ 运行 Deep Review ｜ Top 30 Long-form Deep Review
```

### 两处口径（界面自带说明）

- **表现**：`Ratio = 视频指标 ÷ Creator 频道平均值`；`覆盖规则：Views Ratio < 0.3 → 强制判定为低于基准`；等级＝显著超出基准／超出基准／平均／低于基准／显著低于基准。
- **Creator 可信度**：`基于频道最近 50 个观看量至少 100 的视频评估受众真实性。用于判断合作风险，不代表当前视频的态度或表现。`；分级 `85+ 优秀 · 70–84 良好 · 50–69 一般 · <50 较差`。

### 视频报告（Deep Analytics）章节名逐字

```
决策总览 ｜ 核心营销解读 ｜ 完整证据 ｜ Replay × 字幕洞察 ｜ 叙事结构 ｜ 下一轮内容测试
Audience 释放的信号 ｜ 商业信号构成 ｜ 异议挖掘 ｜ 行动触发点 ｜ 证据覆盖
视频主张 ｜ 购买信号 ｜ 待验证风险 ｜ 证据支持的机会 ｜ Coverage 限制
核心营销解读 = Brand 团队可以立即使用的四项答案：情绪态度 ｜ 最强正向信号 ｜ 隐性阻力 ｜ 核心关注点
叙事结构 = 首个说服断点 ｜ 缺失的承接 ｜ 转化收口
证据覆盖 = 评论样本数 ｜ 各结论引用数 ｜ 评论分类
```

### 新建报告与状态（界面逐字 · 用于说明书的「」引用）

```
开始新的 Brand Mention Research
下方所有指标和建议都属于当前报告；只有需要新的目标、日期范围或市场时，才创建另一份 Research。
这会创建一份独立报告，不会改变当前正在查看的报告。
运行分析 ｜ 运行中… ｜ 正在启动…
恢复已保存的任务 ｜ 重试缺失的 AI 批次 ｜ 重试分析
分析已暂停；已完成的工作已保存，重试会从上一个完成步骤继续。
分析已完成，但仍有可恢复的 AI 缺口
当前方案最多支持12个月；更长时间范围需要升级到 Pro。
自定义范围不能超过365天；更长时间范围需要升级到 Pro。
正在导出并获取邮箱（可能需要 30 秒）
```

### 新建报告的参数（界面逐字）

```
分析目标 ｜ 时间范围（最近30天／最近90天／最近6个月／最近12个月／自定义范围（最长1年））
最大视频数 ｜ 区域 ｜ 搜索模式（完整 Brand 搜索 ／ 指定 SKU / 产品 ／（可选）第二个 SKU）
状态：排队中 ｜ 运行中 ｜ 已完成 ｜ 已完成（有限）｜ 失败 ｜ 分析已暂停；已完成的工作已保存
```

## 六、全站中文名与真实性分析结果（2026-09-29 渲染取证 · A 级）

> **取证方式**：Playwright ＋ 会话 cookie，`localStorage['daniel-locale'] = "zh"` 后渲染。**注意**：不设该键或设为英文时，页内 tab 条会渲染出**未翻译的残留文案**（见下），导航仍是中文 —— 这就是"看起来不一致"的来源。

### 侧栏（中文 · 逐字）

```
仪表盘 ｜ AI 红人搜索 ｜ 红人触达 ｜ 已保存名单 ｜ 内容 ｜ 社媒洞察 ｜ 真实性分析 ｜ 品牌内容分析
品类设置 ｜ 红人追踪 ｜ 品牌 ｜ 设置
```
「AI 红人搜索」展开后：**品牌深度研究 ｜ AI 开放研究 ｜ YouTube 官方数据 ｜ 品类拓展**（本指南覆盖前两项）

### 页内标签条（实测残留 · 内部留痕，**指南不得引用**）

```
Brand Deep研究 ｜ AI Open研究 ｜ YouTube官方数据        ← Discovery 页的 tab 条（未翻译残留）
```
i18n 词典里的正确中文：`shell.brandDeepResearch = 品牌深度研究`／`shell.aiOpenResearch = AI 开放研究`／`shell.youtubeOfficial = YouTube 官方数据`（app bundle 逐字）。

### 页面标题（逐字）

```
品牌内容分析 → h1 = Brand Mention Intelligence
真实性分析   → h1 = 真实度检查
AI 红人搜索   → 无 h1（页面主体：需求输入 ＋ 开始寻找 Creator）
```

### 真实性分析结果结构（实测：对一个 93 订阅、42 视频的频道跑一次「检查」）

```
频道行：频道名 ｜ @handle ｜ N 订阅者 ｜ N 视频 ｜ 国家 ｜「快速查看」
总分与标签：95   Authenticity   Authentic
结论说明：Organic growth signals detected.
五个维度（英文名，各给分）：
  Engagement Match      100
  Interaction Rate       82
  Fluctuation            86
  Subscriber Engagement 100
  Like/Comment Ratio    100
```

> **要点**：结果区是**总分 ＋ 5 个维度**（此前指南误写成"四个维度"，且维度名是凭印象编的 —— 见教训 152/153）。维度名在界面上是**英文**，中文模式下同样渲染英文。

## 一之二、证据等级标注（2026-09-28 补 · 教训 150 后新增）

> **为什么要有这一节**：说明书里每一句"界面上会看到什么"都必须有出处。此前我把**接口参数名**与**记忆中的界面文案**当成界面标签写进指南，被用户当场指出。
> 本节把证据按**等级**标清；**未取证的内容一律不得写进交付件**。

| 等级 | 含义 | 本指南可用范围 |
|---|---|---|
| **A · bundle 直取** | 逐字取自线上前端产物（`assets/*.js` 的界面字符串） | 可直接以「」引用 |
| **B · 抽屉取证** | 逐字核验前端源码 `CreatorSlideOver.tsx` 与抽屉界面（见 `.kol-tools/harvest_drawer_basket.py` 头部 · 2026-09-13） | 可直接以「」引用 |
| **C · 接口参数** | 只证明系统**存在**该能力，**界面标签未取证** | 只能写行为，**不得以「」引用界面文案** |
| **D · 未取证** | 无出处 | **禁止写进交付件** |

### B · 抽屉取证（2026-09-13 · `CreatorSlideOver.tsx` 逐字核验）

```
YT Data Insight
Public Data
Avg Views
```

> 依据：`.kol-tools/harvest_drawer_basket.py` 头部注释（"抽屉弹窗 → YT Data Insight →「Avg Views」磁贴"；"无 Analytics 授权的频道抽屉会切到「Public Data」变体"）。

### C · 接口参数（界面标签未取证 · 只能写行为）

- **品牌深度研究**：`discovery.startSearchJob` 入参 `query, brandId, brandName, brandCompetitors, brandCategory, country, minSubscribers`（**无 keywords、无 selected\***）。
- **AI 开放研究**：`discovery.search` 入参 `topic, selectedScenarios[], selectedContentStyles[], selectedAudiences[], brandId…, country, minSubscribers`；出参 `keywords[50], dimensions`。
- **写法约束**：可以说"选择使用场景、内容风格与人群三类条件"，**不得写成「使用场景（Scenarios）」这类界面引用**。

### D · 未取证清单（等截图核对，禁止先写）

| 内容 | 状态 |
|---|---|
| 真实性分析页的**维度名称** | ✅ **已取证（2026-09-29 渲染）**：Engagement Match／Interaction Rate／Fluctuation／Subscriber Engagement／Like/Comment Ratio（见第六节）；**诊断语分档仍未取证**（只见到 Authentic 与 Organic growth signals detected. 一例） |
| 品牌深度研究输入区是否存在**结构化选择控件** | 未取证（接口入参里**没有** selected\*，故指南按"无三类选择"写）—— 等 S2 截图核对 |
| AI 开放研究输入区三类选择的**界面标签** | 未取证（接口入参有 `selectedScenarios/ContentStyles/Audiences`，故指南只写"三类条件"，不写界面标签）—— 等 S4 截图核对 |
| **新建 Brand 向导第 2 步（添加竞品）的字段** | 未取证 —— 只取证到按钮文案「下一步：添加竞品」与品类设置页的竞品区块（「添加竞品 Brand 名称…」＋「添加」）。指南只写动作、不写第 2 步字段标签；等 S14 截图核对 |
| 创作者详情（抽屉）除 `Avg Views`／`Brand 匹配`／`互动`／`发布节奏`／`商业合作`／`成本与价值`／`Audience 质量` 之外的**字段行界面写法** | 部分未取证 —— 等 S6 截图核对 |

**说明**：线上已切中文默认，但**模块映射未变**（部分 chunk 仍保留英文标签，如 `Brand Deep Research`；同一页面亦出现中文写法「品牌深度研究」）。指南两处并列，便于对照。

## 二、关键界面文案（逐条取自 bundle，作为"怎么写"的依据）

### 1) Discovery（AI 红人搜索）

### Discovery

```
AI 会将搜索需求扩展为多组关键词，并通过 YouTube Official 数据寻找最相关的 Creator。
AI 将从 5 个维度生成 50 个搜索关键词，并行搜索 YouTube。
Brand 信息
Content Expansion 暂时不可用，当前搜索结果未发生改变。
Creator 的其他 Brand
Creator 的其他内容
上一页
下一页
为什么能破圈
代表标题
全选
全部
关键词
内容扩展地图
刚刚
刷新
取消
受众相邻方向
命中缓存 Creator
品牌深度研究
已分析 Creator
已分析标题
已恢复搜索
开始寻找 Creator
当前Brand与Category圈层之外的高频内容
排序：
探索内容扩展
描述理想的 Creator 或搜索主题…
揭示Creator另一面商业组合的非竞品Brand
搜索
搜索市场
搜索记录已删除
新发现
暂无搜索记录
最近搜索
未配置
根据每位 Creator 最多 50 个公开视频标题，发现相关行业、Brand 和主题。
正在分析结果…
正在寻找受众相邻方向、其他 Brand 与非核心内容；当前结果不会改变。
正在读取 Creator 视频标题模式
每位 Creator
每页：
没有找到 Creator，请尝试更换关键词或放宽搜索条件。
竞品
订阅数
请先配置 Brand Operating Markets
通过受众、场景或问题连接的不同内容生态
（仍在加载…）
```

### CreatorSlideOver（创作者抽屉）

```
Audience 质量存疑，互动模式异常，可能存在作弊风险
Audience 质量高，互动自然，未发现作弊信号
Brand 匹配
Brand 匹配度较低，视频主题偏离目标品类
Brand 合作经验丰富，内容交付质量较可靠
CQI 评分
不活跃
与 Brand 有一定相关性，部分视频涉及相关主题
专属视频
互动
付费合作
以获得更精确判断
估算结果 —
借测合作
具备一定商业经验，可按 Brand Brief 协作
内容与 Brand 高度匹配，多个视频命中品类关键词
加载中…
发布节奏适中（每月 2–4 个视频），活跃度正常
发布频率低或已不活跃
发布频繁（每周至少 1 个视频），Creator 非常活跃
合作价值
合作历史有限，可能需要更明确的执行指导
合作成本与预算高度匹配，性价比突出
合作成本相对预算偏高，可能占用过多份额
合作成本适中，处于可接受预算范围
合作记录
商业合作
成本与价值
收起基准
查看基准
沉寂
活跃
活跃度
活跃度较低
真实性
行动
质量可接受，虽有波动但整体正常
赠品合作
配置样品成本
风险
```

### authenticityScore（真实度得分组件）

```
```

### Authenticity（真实性分析页）

```
youtube.com/@handle，频道 URL，或 UC... 频道 ID
在上方粘贴 YouTube 频道 URL、@handle 或频道 ID
快速查看
无法解析此输入为 YouTube 频道。请尝试直接输入频道 URL 或 @handle。
检查
真实度检查
至少需要 3 个有观看量的视频。
视频
视频数据不足，无法计算真实度得分。
解析频道失败
订阅者
输入 Creator 的 YouTube 频道 URL、@handle 或频道 ID，以验证其受众真实度。
输入要检查的 Creator
```

### BrandMentions（品牌内容分析）

```
Audience 释放的信号
Brand 声量占比
Coverage 限制
Creator 可信度
Deep Analytics V4 已进入队列，正在开始采集来源。
Organic Performance 证据
Organic 表现优秀
Organic 表现良好
Organic 触达与 Creator 可信度独立于营销解读。
Short-form · 无需 Replay
YouTube 评论
一般
上一页
上方营销解读已将问题与异议和一般性热情分开。
下一版 Brief 硬性规则
下一页
不相关
互动率
优秀
低于基准
停止分析
分析
分析历史
分析已启动！
删除
删除该分析及其全部结果？
即使情绪为正向，Creator/闲聊仍按曝光噪音处理。
历史分析
历史分析 · 只读
叙事结构
可用
各结论引用数
商业信号
商业信号构成
商业相关性与情绪是两条独立轴线。Creator 赞美与剧情闲聊会展示，但不会计入产品需求。
回应覆盖
导出 CSV
已打开现有的 Deep Analytics V4 任务。
已筛选
已筛除/不相关
已选视频
平均
平均 Rated Score
建议行动及其证据已显示在上方营销解读中。
异议挖掘
当前方案最多支持12个月；更长时间范围需要升级到 Pro。
待验证风险
提及
搜索视频标题或频道…
教程
整体反应依据
新闻
是否 Official
显著低于基准
显著超出基准
暂无
暂无分析
暂无风险假设获得足够引用支持。
月度趋势
有限分析
未出现明确的转化 CTA。
未知
未知频道
未评估
查看 Transcript 引文
横向滚动视频结果
正在使用同一 Source Set 重试失败的分析阶段。
正在启动 V4 任务…
正在重试分析…
没有可导出的数据
点赞
相关性
真实性
类型
缺失回答：
自定义范围不能超过365天；更长时间范围需要升级到 Pro。
良好
表现
表现分布
观看量
视频 URL
视频、Creator 与内容
视频主张
视频分析
视频数量
视频标题
视频类型
订阅数
证据不可用：未保存已引用的 Transcript 原文。
证据支持的机会
证据覆盖
评论
评论分类
评论样本数
该分类暂无可用证据。
语言
请先选择 Brand
请至少输入一个 SKU 关键词
购买信号
购买阻力
赞助内容
超出基准
较差
邮箱
频道 URL
频道名称
```

### ContentVideos（视频追踪）

```
交易金额
审核中
已发布
已完成
操作
暂无跟踪的视频
更新时间
状态
视频
视频总数
跟踪与您的Campaign相关联的所有Creator视频
通过VideoCollaboration关联到交易的视频及其表现数据将显示在这里。
```

## 七、品牌（Brand 管理）与新建 Brand 向导（2026-09-29 渲染取证 · A 级）

> **取证方式**：Playwright ＋ 账号会话 cookie，中文模式（`daniel-locale=zh`）打开 `https://daniel-agent.com/brands`，读渲染后 DOM；
> 向导只读不写（**除表单交互外不点任何创建/保存按钮**，取证后关闭弹窗，工作区未留任何新建对象）。

```
侧栏（逐字）：仪表盘 ｜ AI 红人搜索 ｜ 红人触达 ｜ 已保存名单 ｜ 内容 ｜ 社媒洞察 ｜ 真实性分析 ｜ 品牌内容分析 ｜ 品类设置 ｜ 红人追踪 ｜ 品牌 ｜ 设置
路由：/brands（取自线上 index-CgQTUrYk.js 的 path 列表；/category-settings 见第八节）
H1  Brand 管理
副标题  管理 Brand 档案、市场范围与竞品监测
按钮  新建 Brand
品牌卡（逐字）  OCJOY ｜ Electric Toothbrush ｜ 需要完成设置 ｜ 6 个竞品 ｜ 1 个市场
```

### 新建 Brand 向导（点「新建 Brand」后的弹窗）

```
标题  创建新 Brand
字段（label 逐字，* ＝ 必填）：
  Brand 名称 *           输入框 placeholder：e.g., Anker
  品类                   输入框 placeholder：例如：消费电子
  Brand 描述             textarea placeholder：简要说明 Brand、产品与目标受众…
  产品样品成本（USD） *   数字输入，placeholder：e.g., 150
                         字段说明：用于计算产品置换合作所需的最低 KOL 规模
  Operating Markets      区块说明：Countries where this Brand operates or plans to operate. Category monitoring is configured separately.
                         计数：0 / 3 ｜ Workspace limit
                         空态：No operating markets selected yet.
                         选择器：Search by country name or code ｜ 3 remaining
                         校验：Select at least one Operating Market to continue.
按钮  下一步：添加竞品 ｜ Close
```

**要点**：第 1 步是档案 ＋ Operating Markets；按钮文案表明**第 2 步是添加竞品**（第 2 步字段级仍未取证 —— 见 D 级清单；品类设置页的「竞品」区块是同一份名单的日常维护入口）。

## 八、品类设置（Category Settings）（2026-09-29 渲染取证 · A 级）

> **取证方式**：同第七节，打开 `/category-settings`（路由取自线上 bundle `path:"/category-settings"`）。

```
H1  Category Settings
副标题  管理 OCJOY 的 Category Profile 与细分方向

区块 Category
  按钮 Reset
  内容  Electric Toothbrush & Water Flosser
  描述  This category covers electric toothbrushes and water flossers, focusing on their features, performance, and user experiences.
        It includes reviews, comparisons, and maintenance guides for oral hygiene devices.

区块 竞品
  说明  当前 Category 中正在追踪的 Brand
  列表  Philips Sonicare ｜ Oral-B ｜ Waterpik ｜ Quip ｜ Burst ｜ Suri ｜ Foreo
  输入框 placeholder  添加竞品 Brand 名称…      按钮 添加

区块 Monitoring Markets
  说明  从此 Brand 的 Operating Market 中选择；SEO 与 Exposure SOV 只采集这些市场。
  计数  已监控 1 / 1 个 Operating Market ｜ 无单独监控上限
  选项  US

区块 Admin 控制 → Filter Rules
  说明  Keywords used to filter relevant/irrelevant videos      按钮 Regenerate
  列表  Positive Keywords (20) ／ Negative Keywords (14)
        （示例逐字：electric toothbrush review／sonic toothbrush／best electric toothbrush／oral irrigator／water flosser review …；
          manual toothbrush／toothpaste／mouthwash／dental floss／teeth whitening strips …）

区块 Monitoring
  说明  Filter effectiveness and audit history

区块 AI Diagnosis
  说明  Input client feedback to get keyword suggestions
  输入  textarea placeholder：Describe the data quality issue (e.g., 'too many chainsaw videos appearing for Husqvarna')
  按钮  Run Diagnosis
```

## 九、读取方向取证（2026-09-29 渲染取证 · A 级）

> **用途**：用户 2026-09-29 要求「结果怎么看」的**读取方式列**写成方向判断（哪个好、哪个差、越高越好还是越低越好）。以下是界面自带的方向依据。

### 品牌内容分析 · 总览指标与副标签（逐字）

```
视频总数 25 ｜ ≥1,000 次观看 ｜ 已排除不相关内容 22（与 Brand 匹配度较低）｜ 总观看量 99.1K（累计）
平均每条观看量 4.0K（均值）｜ 独立频道数 8（独立 Creator）｜ 平均 Rated Score 1.05（加权评分 · 满分 5.00）
显著超出基准 3（相对 Creator 基准）
```

### 品牌内容分析 · 评分方法（界面自带 · 逐字）

```
Rated Score (0–5)：将每条视频与 Creator 的 Organic 基准进行比较的加权评分；所有比率最高按 10x 计算。
表现等级：显著超出基准 ≥ 1.5x ｜ 超出基准 1.2x – 1.5x ｜ 平均 0.8x – 1.2x ｜ 低于基准 0.5x – 0.8x ｜ 显著低于基准 < 0.5x
Ratio = 视频指标 ÷ Creator 频道平均值
Authenticity Score (0–100)：基于互动模式分析评估频道可信度。
  85+ 优秀 · 70–84 良好 · 50–69 一般 · <50 较差
如何根据触达采取行动
  High Organic Performance   优先审查；放大正向内容，或回应负面内容
  Good Organic Performance   尽快审查，并决定放大、互动或回应
  Average Organic Performance 持续观察讨论与受众反馈
  Low Organic Performance    触达较低不代表情绪判断；请单独审查 Brand 风险
Organic Performance 衡量相对 Creator 基准的触达，不用于判断情绪。
（视频维度「真实性」条形分档：优秀 ／ 良好 ／ 一般 ／ 较差）
```

### 真实度检查（/authenticity）结果与方向（逐字）

```
空态：输入要检查的 Creator ｜ 在上方粘贴 YouTube 频道 URL、@handle 或频道 ID
页内标题  真实度检查 ｜ 说明：输入 Creator 的 YouTube 频道 URL、@handle 或频道 ID，以验证其受众真实度。
2026-09-29 实测一例（@mkbhd）：87 ｜ Authenticity ｜ Authentic ｜ Organic growth signals detected.
  五维：Engagement Match 84 ｜ Interaction Rate 90 ｜ Fluctuation 75 ｜ Subscriber Engagement 100 ｜ Like/Comment Ratio 83
2026-09-29 实测另一例（小频道）：95 ｜ Authentic ｜ Organic growth signals detected.
  五维：Engagement Match 100 ｜ Interaction Rate 82 ｜ Fluctuation 86 ｜ Subscriber Engagement 100 ｜ Like/Comment Ratio 100
方向：分数为 0–100，**越高越可信**；两例高分样本的结论标签均为 Authentic。
界面上有「快速查看」入口。
```

### 界面文案引用池（本节所有字符串已逐字取证，指南可引用）

品牌 ｜ Brand 管理 ｜ 管理 Brand 档案、市场范围与竞品监测 ｜ 新建 Brand ｜ 创建新 Brand ｜ Brand 名称 ｜ 品类 ｜ Brand 描述 ｜ 产品样品成本（USD）
｜ 用于计算产品置换合作所需的最低 KOL 规模 ｜ Operating Markets ｜ Search by country name or code ｜ Select at least one Operating Market to continue.
｜ 下一步：添加竞品 ｜ 需要完成设置 ｜ 个竞品 ｜ 个市场 ｜ 品类设置 ｜ Category Settings ｜ Category ｜ Reset ｜ 竞品
｜ 当前 Category 中正在追踪的 Brand ｜ 添加 ｜ Monitoring Markets ｜ 从此 Brand 的 Operating Market 中选择；SEO 与 Exposure SOV 只采集这些市场。
｜ 已监控 1 / 1 个 Operating Market ｜ 无单独监控上限 ｜ Admin 控制 ｜ Filter Rules ｜ Regenerate ｜ Positive Keywords ｜ Negative Keywords
｜ Monitoring ｜ AI Diagnosis ｜ Run Diagnosis ｜ 真实度检查 ｜ 输入 Creator 的 YouTube 频道 URL、@handle 或频道 ID，以验证其受众真实度。
｜ 检查 ｜ 输入要检查的 Creator ｜ 快速查看 ｜ 表现等级 ｜ 显著超出基准 ｜ 超出基准 ｜ 平均 ｜ 低于基准 ｜ 显著低于基准
｜ Authenticity Score (0–100) ｜ 优秀 ｜ 良好 ｜ 一般 ｜ 较差 ｜ 如何根据触达采取行动 ｜ 优先审查 ｜ 尽快审查 ｜ 持续观察
｜ Organic Performance 衡量相对 Creator 基准的触达，不用于判断情绪。 ｜ 与 Brand 匹配度较低 ｜ 加权评分 · 满分 5.00

### 仅 Admin 可见的界面串（打标 · 供判据 ⑮ 使用）

> 这些串在页面上位于「Admin 控制」标题之下；**普通账号的日常配置用不到**，因此不得写进「操作步骤」与「输入示例」。
> 打标格式：`【仅 Admin】<串>`（每行一个）。

【仅 Admin】Filter Rules
【仅 Admin】Regenerate
【仅 Admin】Positive Keywords
【仅 Admin】Negative Keywords
【仅 Admin】AI Diagnosis
【仅 Admin】Run Diagnosis
【仅 Admin】Keywords used to filter relevant/irrelevant videos
【仅 Admin】Input client feedback to get keyword suggestions

### 品牌创建第 2 步：竞品与关键词（**用户口述口径** · 2026-09-29）

> **来源**：产品方（用户）口述确认，**非渲染取证** —— 界面字段级文案仍待 S14 截图核对（见 D 级清单）。
> 用户原话：「竞品（第 2 步）**界面未标注这个有点问题，未标注就写必填**」「其次是竞品示例，**给一个竞品+对应的 keywords 即可**」。

- **竞品＝必填**（界面未标星号，但按必填处理；**交付件不得写"界面未标注"**）；
- **每个竞品配一组对应关键词**（示例：`Philips Sonicare` ＋ `sonic toothbrush`／`brush head replacement`）。

> **补充口径（2026-09-29 用户第二条指令）**：示例**定版** —— 竞品示例用 `XREAL`，其对应关键词写作
> `Keywords: AR glasses, XR glasses, smart glasses`（英文关键词，按该竞品内容里的实际写法给）。与「以智能眼镜品牌为例」的示例语境一致。
> **补充口径（2026-09-29 用户第三条指令）**：**品类设置示例与品牌创建示例同语境（智能眼镜）** ——
> Category 名称 `Smart Glasses & AR Eyewear`、竞品 `XREAL`、Monitoring Markets `US`；两章示例不再各用一套品类。

## 十、CQI 评分区（创作者详情抽屉）· 2026-09-29 组件文案取证（B 级）

> **取证方式**：读取线上前端产物 —— `assets/CreatorSlideOver-DCxe8lsV.js`（抽屉组件）＋ `assets/cqiEvidence-CRiebIoE.js`（CQI 证据与 benchmark 模板）＋ `assets/authenticityScore-a-IZvxEl.js`（体量档与互动率基准）。
> **等级说明**：属 **B 级（界面组件文案取证）** —— 文案与数据结构（`conclusion`／`evidence`／`benchmark` 三段）逐字来自组件；**面板的视觉层级未做渲染复核**。

### 面板结构（逐字）

```
抽屉里两块评分区：
  ① 匹配评分（Match Score）  —— 徽标形如「P{优先级} · {分数}」，下列字段：
       匹配评分 ｜ VPR ｜ Brand 匹配（Brand Fit）｜ 互动（Engagement）｜ Audience ｜ 合作价值 ｜ 商业合作 ｜ 真实性
  ② CQI 评分（CQI Score）    —— 徽标形如「CQI {等级} · {总分}」，下列五个维度
       每个维度都渲染三段：结论（conclusion）／依据（evidence）／benchmark
```

### CQI 五个维度与各自的 benchmark、程度说明（逐字）

```
Brand Fit｜结论：Brand 匹配：{x}/{y} — 品类匹配强 ／ 品类匹配良好 ／ 通过搜索命中品类
         依据：{N} 个视频命中 {品类} 关键词。竞品提及：{品牌}({次数})、…
   benchmark：当前位置：{档位}。判断区间：命中 6 个以上视频 = 品类专家；4–5 个 = 强匹配；2–3 个 = 可用匹配；
              1 个 = 探索性匹配；0 个 = 仅搜索发现。品类导向 Brief 优先使用品类专家或强匹配 Creator；
              少于 2 个命中时，触达前需要人工复核内容。命中关键词：{词}({次数})、…
Engage  ｜结论：互动：{x}/{y} — 互动高 ／ 互动一般 ／ 互动低
         依据：互动率：{x}%（点赞 + 评论 ÷ 观看量，基于近期视频）
   benchmark：当前位置：在 {体量档} 频道中属于{档位}。判断区间：优秀 ≥{excellent}%；强 {strong}–{excellent−0.1}%；
              典型 {typical}–{strong−0.1}%；需要复核 {watch}–{typical−0.1}%；较弱 <{watch}%。
              同类平均为 {x}%，样本 {N} 个频道。
Audience｜结论：观看渗透率：{x}%（平均观看量 ÷ 订阅数）。每个视频平均 {N}K 次观看。
   benchmark：当前位置：在 {体量档} 频道中属于{档位}。同类分位点：P25 {x}%，中位数 {x}%，P75 {x}%，P90 {x}%。
              当前同类平均为 {x}%，样本 {N} 个频道。
Activity｜结论：最近发布：{日期}（{N} 天前）
   benchmark：当前位置：{档位}。判断区间：7 天内发布 = 适合立即启动；8–28 天 = 活跃；
              29–60 天 = 活跃度下降；超过 60 天 = 沉寂。时效性 Campaign 应优先选择适合立即启动或活跃的 Creator；
              否则请在触达前确认下一次发布时间。
Commercial｜结论：付费内容比例：{x}%（{N}/{M} 个视频）
   benchmark：当前位置：{档位}。判断区间：付费内容 ≥30% = 经验非常丰富；10–29.9% = 经验丰富；
              5–9.9% = 有一定经验；<5% = 合作历史有限。同类平均为 {x}%。
              该指标衡量商业执行熟悉度，而非 Audience 质量。
```

**程度说明的档位名（逐字）**

| 维度 | 档位名（从好到差） |
|---|---|
| Brand Fit | 品类专家 ／ 强匹配 ／ 可用匹配 ／ 探索性匹配 ／ 仅搜索发现 |
| Engage | 优秀 ／ 强 ／ 典型 ／ 需要复核 ／ 较弱 |
| Audience | 前 10% ／ 前 25% ／ 高于中位数 ／ 低于中位数 ／ 后 25% |
| Activity | 适合立即启动 ／ 活跃 ／ 活跃度下降 ／ 沉寂 |
| Commercial | 经验非常丰富 ／ 经验丰富 ／ 有一定经验 ／ 合作历史有限 |

### 体量档与互动率基准（逐字）

```
体量档（按订阅数）：Nano (<10K) ｜ Micro (10K–100K) ｜ Mid-size (100K–1M) ｜ Macro (1M–10M) ｜ Mega (10M+)
互动率五档阈值（按体量档给出，单位 %）：
  Mega 3／2／1.2／0.5 ｜ Macro 4／3／2／1 ｜ Mid-size 5／3.5／2.5／1.5 ｜ Micro 7／5／3／2 ｜ Nano 10／7／4／2
观看渗透率分位点（P90／P75／P50／P25，单位 %）：
  Mega 27／18／5／1 ｜ Macro 32／10／1.3／0.5 ｜ Mid-size 28／11／3.6／1.2 ｜ Micro 40／20／8／3 ｜ Nano 60／30／15／5
匹配评分区的「该体量基准」：VPR = 5%（≥1M）／8%（≥100K）／12%（其余）；ER = 1–2%／2–4%／4–8%（同档）
```

### 匹配评分区字段的解释句（逐字，抽屉里直接显示）

```
VPR {x}%（该体量基准为 {基准}）。高分代表粉丝活跃，未发现明显僵尸粉问题 ／ VPR 数据待计算，请打开详情卡完成计算
ER {x}%（该体量基准为 {基准}），反映真实粉丝参与度
Brand 匹配：内容与 Brand 高度匹配，多个视频命中品类关键词 ／ 与 Brand 有一定相关性，部分视频涉及相关主题 ／ Brand 匹配度较低，视频主题偏离目标品类
互动：发布频繁（每周至少 1 个视频），Creator 非常活跃 ／ 发布节奏适中（每月 2–4 个视频），活跃度正常 ／ 发布频率低或已不活跃
合作价值：合作成本与预算高度匹配，性价比突出 ／ 合作成本适中，处于可接受预算范围 ／ 合作成本相对预算偏高，可能占用过多份额
商业合作：Brand 合作经验丰富，内容交付质量较可靠 ／ 具备一定商业经验，可按 Brand Brief 协作 ／ 合作历史有限，可能需要更明确的执行指导
真实性：Audience 质量高，互动自然，未发现作弊信号 ／ 质量可接受，虽有波动但整体正常 ／ Audience 质量存疑，互动模式异常，可能存在作弊风险
VPR 高，粉丝活跃，未发现明显僵尸粉问题 ／ VPR 适中，粉丝活跃度一般 ／ VPR 低
```

### 引用池（本节字符串已逐字取证，指南可引用）

CQI 评分 ｜ CQI ｜ 匹配评分 ｜ Nano (<10K) ｜ Micro (10K–100K) ｜ Mid-size (100K–1M) ｜ Macro (1M–10M) ｜ Mega (10M+)
｜ 品类专家 ｜ 强匹配 ｜ 可用匹配 ｜ 探索性匹配 ｜ 仅搜索发现 ｜ 优秀 ｜ 强 ｜ 典型 ｜ 需要复核 ｜ 较弱
｜ 前 10% ｜ 前 25% ｜ 高于中位数 ｜ 低于中位数 ｜ 后 25% ｜ 适合立即启动 ｜ 活跃 ｜ 活跃度下降 ｜ 沉寂
｜ 经验非常丰富 ｜ 经验丰富 ｜ 有一定经验 ｜ 合作历史有限 ｜ 该体量基准为 ｜ VPR ｜ 观看渗透率 ｜ 互动率
｜ 命中 6 个以上视频 = 品类专家；4–5 个 = 强匹配；2–3 个 = 可用匹配；1 个 = 探索性匹配；0 个 = 仅搜索发现
｜ 7 天内发布 = 适合立即启动；8–28 天 = 活跃；29–60 天 = 活跃度下降；超过 60 天 = 沉寂
｜ 付费内容 ≥30% = 经验非常丰富；10–29.9% = 经验丰富；5–9.9% = 有一定经验；<5% = 合作历史有限
｜ 优秀 ／ 强 ／ 典型 ／ 需要复核 ／ 较弱 ｜ 1–2% ｜ 2–4% ｜ 4–8% ｜ 5% ｜ 8% ｜ 12%
> **补充口径（2026-09-29 用户第四条指令）**：**竞品的 Keywords 写品类，不写型号** ——
> 示例：竞品 `Samsung Galaxy S25 Ultra` 对应 `Keywords: smartphone, Android phone, flagship phone`（不要写成该竞品自己的型号串）。
