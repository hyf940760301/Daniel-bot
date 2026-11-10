<!-- 本文件是 `docs/marketing/skills/kol-intelligence.md` L6895–L7524 的**逐字切片**（语料版本 0.9.207）；请勿在此改写判据，改动须回流源文件后重跑切分器 -->
<!-- 源节：附录 B 语义登记（概念／指标／判据／表达的口径登记） -->


## 附录 B · 语义登记（Ontology Registry）

> 本附录是**机器可读的判据登记**，由切分器切为 `references/12-ontology-registry.md`，再由段三抽取为 `mcp/corpus/_ONTOLOGY.json`。
> 登记项只回答三件事：**这个概念怎么定义、这个数怎么算、这条判据该问什么**。流程本身仍在工序表（`intake/processes.json`），本附录不重复。

### B.1 登记项：指标 metric.creator.avg_views_long

```yaml
id: metric.creator.avg_views_long
type: metric
label: 长视频均播
axes:
  content_form: long
surfaces:
  reported:
    kind: mean
    window: latest_30_videos
    sample_rule: 最新 30 条里的长视频
    min_sample: 5
  median:
    kind: median
    window: last_28_days
    sample_rule: 近 28 天、时长 > 60 秒的视频
    min_sample: 5
external_only: median
owner: 总监代签（2026-11-08）
status: superseded
superseded_by: [metric.creator.avg_views.drawer_28d]
version: 1.0.0
```

### B.2 登记项：判据 criterion.creator.screen

```yaml
id: criterion.creator.screen
type: criterion
label: 找红人 · 筛选维度
stage: screening
owner: 总监代签（2026-11-08）
resolution: ask_once_per_task
groups:
  - key: content_vertical
    label: 内容与垂类
    example: 真机上手测评／资讯／对比；英文
    default: 上手测评、英文
    weight: 高
  - key: audience_geo
    label: 受众与地域
    example: 美国为主；18–44 岁
    default: 美国为主
    weight: 中
  - key: performance_scale
    label: 表现与规模
    example: 长视频均播 ≥ 50 万；互动表现达标
    default: 长视频均播 50 万、互动表现达标
    weight: 高
  - key: commercial
    label: 商业与合作
    example: 有同类产品经验；排除正在合作竞品
    default: 同类经验优先
    weight: 中
  - key: exclusions
    label: 排除项
    example: 排除已合作过、纯搬运号
    default: 都排除
    weight: 中
```

### B.3 登记项：表达 expr.kol_list

```yaml
id: expr.kol_list
type: expression
label: 红人名单交付
owner: 总监代签（2026-11-08）
sections: [概览, 名单, 每条依据, 覆盖率与缺口, 下一步]
required: [数字必须带口径与时间点, 不确定写待确认]
banned: [非常好, 绝对, 肯定没问题, 大概]
```

### B.4 登记纪律

1. **一条登记项一个 yaml 块**，块内 `id` 必填且全局唯一；
2. `owner` 必填（业务角色或授权代签），无 owner 不入索引；
3. 阈值只作为 `default` 出现，**最终取值由用户在任务开始前确认**，不由登记项决定；
4. `availability: unavailable` 的维度不得出现在提问清单里；
5. 本附录不写流程顺序，流程以 `intake/processes.json` 为准。

### B.5 登记项：判据 criterion.clarify.param_gate

```yaml
id: criterion.clarify.param_gate
type: criterion
label: 澄清闸 · 参数级追问（4 场景 / 28 项）
owner: 总监代签（2026-11-08）
version: 1.0.0
resolution: ask_once_per_task
scenarios:
  - key: kol_search
    label: 找红人／建名单
    dims:
      - key: market
        ask: 目标市场
        why: 决定从哪个国家／地区找人，也决定受众核验按哪一国看；不说就有可能整份名单地域不对
        default: 按 US 执行
        impact: 影响全部候选的地域与受众核验口径，不补最容易整份名单跑偏
      - key: fans
        ask: 粉丝量级区间
        why: 决定要头部还是中腰部；不同量级的报价、内容质量、可谈性差很多，混着找没法比较
        default: 按 1 万到 60 万订阅执行（以中腰部为主）
        impact: 直接决定名单的量级结构，越晚改返工越大
      - key: audience
        ask: 是否必须有官方受众数据
        why: 有的红人平台没有受众数据；不说明只能「有则用、无则标注缺失」，受众这项核验会打折
        default: 有则用、无则标注缺失，不因缺受众数据直接淘汰
        impact: 影响受众核验的严格程度，进而影响最终入选人数
      - key: format
        ask: 内容形式（长视频／短视频）
        why: 长视频和短视频的均播、报价、受众都不同；混着给会出一份没法横向比的名单
        default: 长短都看，名单里标出每位的主形式
        impact: 影响候选池，也决定均播要按哪种形式对比
      - key: qty
        ask: 数量上限（本次要几位）
        why: 决定给你多少候选、要不要继续翻页取；不说明我按一页给
        default: 默认给 10 位候选
        impact: 影响取数轮次与名单长度，也决定要不要分页
      - key: dedupe
        ask: 是否排重（合作过的人要不要剔除）
        why: 重复或已合作的人会占掉名额，也决定要不要额外比一份既有名单
        default: 名单内按唯一标识排重；已合作过的人默认保留，只在备注里标出合作过
        impact: 影响最终可用名额，也决定要不要多跑一次名单比对
      - key: deliver
        ask: 交付形态（表格／文档）
        why: 表格和文档的字段组织完全不同；你要能直接拿去用，不说我按表格给
        default: 按表格交付（红人、频道链接、量级、国家、均播、联系方式）
        impact: 影响出件格式，早定能省一次返工
      - key: deadline
        ask: 交付时点（什么时候要）
        why: 决定我先给一版能用的粗名单，还是一次做到位；也决定要不要加班跑
        default: 按今天内先给一版可用名单执行
        impact: 影响交付节奏，以及在「快」和「全」之间怎么取舍
      - key: window
        ask: 数据时间窗
        why: 看近一个月和近三个月可能选出完全不同的人，尤其刚出过爆款的
        default: 按近 28 天表现判断
        impact: 影响均播与互动的读数，从而影响谁算「表现好」
    calibers:
      - ask: 什么算「高自然表现」
        impact: 决定最终谁能进名单
      - ask: 什么算「内容相关」到可以算同类红人
        impact: 决定排除边界往外放多宽
      - ask: 什么算「互动好」
        impact: 决定要不要因为互动低而淘汰人
  - key: list_ops
    label: 名单处理（合并／去重／比对）
    dims:
      - key: qty
        ask: 数量上限（这份名单最后要留多少人）
        why: 决定是「全留」还是「按条件砍到多少位」，也决定要不要排序取前 N
        default: 默认全留（不砍名额），只做合并与去重
        impact: 决定最终名单规模，是最容易返工的一项
      - key: dedupe
        ask: 是否排重
        why: 名单合并的核心就是去重；不说清就只能按既有名单里一模一样的写法判重
        default: 按频道链接与账号名排重，写法不同的同名项保留两条并标注疑似重复
        impact: 直接决定名单条数，也决定「重复」的判定松紧
      - key: columns
        ask: 输出要哪些列
        why: 这份名单要交给谁、用来干什么，决定留哪些列；列定不下来容易白跑一遍
        default: 按「红人、频道链接、量级、国家、联系方式」这几列交付
        impact: 决定最终表格字段，返工成本最高的一环
      - key: baseline
        ask: 以哪份名单为准
        why: 合并比对必须先有基准，否则谁算新的、谁算重复的说不清
        default: 以你给的既有名单为基准，平台数据只做补充
        impact: 决定谁算「新增」谁算「重复」，直接影响结果口径
      - key: deliver
        ask: 交付形态（表格／文档）
        why: 同一份名单做成在线表还是文档，字段组织完全不同
        default: 按表格交付（可直接双击打开的表格文件）
        impact: 影响出件格式，早定能省一次返工
      - key: deadline
        ask: 交付时点（什么时候要）
        why: 决定我先给一版粗合并，还是一次做到位
        default: 按今天内先给一版可用名单执行
        impact: 影响交付节奏与深度取舍
      - key: window
        ask: 数据时间窗（名单取哪个时点的数据）
        why: 两份名单取数时点不同，量级和均播会对不上
        default: 按最近一次取到的平台数据为准，并标出取数时点
        impact: 影响两份名单能不能直接对比
    calibers:
      - ask: 什么算「同一个人」（不同频道、不同语言号要不要合并）
        impact: 决定名单条数，也决定谁算重复
      - ask: 什么算「值得保留」
        impact: 决定全留还是只留信息完整的那批
  - key: brand_setup
    label: 品牌建档／品牌清单
    dims:
      - key: market
        ask: 目标市场
        why: 品牌在哪些国家卖，决定要建哪些站点、关注哪些市场的声量
        default: 按 US 执行
        impact: 影响所有后续声量与竞品数据的取数范围
      - key: scope
        ask: 品牌主体范围（子品牌／产品线要不要单列）
        why: 同一集团常有多个子品牌，不说明就会把它们的声量混在一起算
        default: 只建主体品牌，子品牌不单列，声量归到主体名下
        impact: 影响品牌归属判断，串了就得整份重算
      - key: competitors
        ask: 竞品范围（要不要一起建档）
        why: 竞品要不要一起建、建几个，决定清单规模，也决定后面能不能直接做对比
        default: 不单独建竞品，只在主体品牌下挂竞品名做关联
        impact: 影响清单规模，以及后续对比分析能不能直接跑
      - key: category
        ask: 品类与关键词范围
        why: 品类关键词决定哪些内容算「提到这个品牌」，范围宽窄直接影响声量大小
        default: 按品牌主营品类自动归集，只收与主营品类相关的内容
        impact: 影响声量口径的高低，也影响竞品对比的公平性
      - key: deliver
        ask: 交付形态（表格／文档）
        why: 品牌档案与品牌清单的字段组织不同；不说我按表格给
        default: 按表格交付（品牌、站点、主营品类、竞品关联、数据时点）
        impact: 影响出件格式，早定能省一次返工
      - key: deadline
        ask: 交付时点（什么时候要）
        why: 决定我先给一版粗档案还是一次做到位
        default: 按今天内先给一版可用清单执行
        impact: 影响交付节奏与深度取舍
    calibers:
      - ask: 什么算「竞品」
        impact: 决定对比对象是谁，也决定对比结论可不可信
      - ask: 什么算「主线产品」
        impact: 决定哪些内容算品牌相关
  - key: generic
    label: 通用（未指定场景）
    dims:
      - key: market
        ask: 目标市场
        why: 决定按哪个国家／地区取数与核验；不说可能整体偏地域
        default: 按 US 执行
        impact: 影响全部取数的地域与核验口径
      - key: qty
        ask: 数量上限（本次要几条）
        why: 决定给你多少条、要不要继续翻页取
        default: 默认给 10 条
        impact: 影响取数轮次与结果规模
      - key: deliver
        ask: 交付形态（表格／文档）
        why: 表格和文档的字段组织完全不同，不说我按表格给
        default: 按表格交付
        impact: 影响出件格式，早定能省一次返工
      - key: deadline
        ask: 交付时点（什么时候要）
        why: 决定先给一版能用的，还是一次做到位
        default: 按今天内先给一版可用结果执行
        impact: 影响交付节奏与深度取舍
      - key: dedupe
        ask: 是否排重
        why: 同名同人的重复项会占名额，也影响结果条数
        default: 按唯一标识排重
        impact: 影响结果条数与名单口径
      - key: window
        ask: 数据时间窗
        why: 看近一个月和近三个月可能选出完全不同的结果
        default: 按近 28 天数据判断
        impact: 影响读数的可比性，从而影响结论
    calibers:
      - ask: 什么算「结果合格」
        impact: 决定这批结果算不算交付完成
```

### B.6 语义层补登：5 个概念 ＋ 10 个指标（P0 · 2026-11-08 定稿）

> 出处：`daniel-bot/specs/PHASE0-ONTOLOGY-FINAL.md` §2（业务字典）、§3（登记表扩展方案）、§7.7（9 条阻塞项的默认方案）。
> 本节**追加在附录 B 末尾**（不就地插入），因此其余切片的源行区间不变，只有 `12-ontology-registry.md` 的终点后移。
> `owner` 按 §7.7 Q-15 统一为 `总监代签（2026-11-08）`；新条目 `version: 2.0.0`。
> 概念只给 `key`／`value_domain`（概念不是计算，不给 `surfaces`）；指标的面一律写进 `surfaces.<面键>`，**不设 `取值面` 字段**。

#### B.6.1 登记项：概念 concept.brand（品牌）

```yaml
id: concept.brand
type: concept
label: 品牌
owner: 总监代签（2026-11-08）
status: active
stage: ""
key: brandId
definition: Daniel 里的品牌实体：品牌编号＋名称＋工作区＋品类＋目标市场＋行业关键词＋样品价＋竞品；是检索口径、背调、提及任务、声量统计的共同事实源。
value_domain: brandId 为整数；name 允许为空、允许同名（服务端不拦空名／重名，不可用名字当唯一键）；必须归属一个 workspaceId；targetCountries 为 ISO 国家码数组；sampleCost 为样品计价（不是零售价）；competitors 以品牌自己配置的为准。
data_status: reliable
source: "contracts/real-brands-inventory.json#交付件schema.列; references/60-data-layer.md:239,369"
version: 2.0.0
```

#### B.6.2 登记项：概念 concept.product（型号／产品）

```yaml
id: concept.product
type: concept
label: 型号／产品（SKU）
owner: 总监代签（2026-11-08）
status: active
stage: ""
key: skuTerms（无实体 id）
definition: 品牌下的具体产品型号；在本仓不是实体，而是三样东西的合称：品牌提及的检索单元、报价分母的形式依据、产品说明块的事实来源。
value_domain: 品牌方型号名（自由文本，来自任务配置的 skuTerms）；任务模式为 brand（品牌名）或 sku（型号词）；品牌池 = 品牌名任务 ∪ 其 SKU 词任务，按 videoId 去重；型号名未知时写 unknown，不造名。
data_status: unknown
source: "references/60-data-layer.md:383-390,456"
version: 2.0.0
```

#### B.6.3 登记项：概念 concept.channel（取数渠道）

```yaml
id: concept.channel
type: concept
label: 取数渠道（平台）
owner: 总监代签（2026-11-08）
status: active
stage: ""
key: 平台枚举
definition: 渠道＝取数渠道，指平台（YouTube 等），不是某个品牌频道。本条不指销售渠道、也不指品牌自己的 YouTube 频道。
value_domain: "youtube／reddit／kickstarter／avsforum／rv_forum／nox_email（6 值）"
data_status: reliable
source: "tools/voc-crawler/STATUS.md; docs/marketing/skills/voc-intelligence.md:33-47"
version: 2.0.0
```

#### B.6.4 登记项：概念 concept.creator（红人／频道）

```yaml
id: concept.creator
type: concept
label: 红人／频道
owner: 总监代签（2026-11-08）
status: active
stage: ""
key: channelId
definition: 一个 YouTube 频道；「红人」是业务称呼，「频道」是数据单位。合作主体以频道计，不以人计。
value_domain: channelId 为 UC 开头的字符串（唯一键）；handle 形如 @xxx 且可为 null；title 为官方全文；country 是频道所在地，不是受众国家；subscribers 为整数快照。
data_status: reliable
source: "_DANIEL-FIELD-DICTIONARY.md:134,200-204（dev-side）; lib/index.js:886"
version: 2.0.0
```

#### B.6.5 登记项：概念 concept.list（名单）

```yaml
id: concept.list
type: concept
label: 名单（Saved List）
owner: 总监代签（2026-11-08）
status: active
stage: ""
key: listId
definition: 挂在某品牌下的红人集合，有 listId、名称、条目数；一条条目＝一个 channelId。名单属于品牌，不属于账号；同一频道可出现在多份名单里。
value_domain: listId 为整数；必须归属一个 brandId；条目数 ≥0，与页面人数不一致时以读到的条目为准并标注；名单名非空、允许同名。
data_status: reliable
source: "schema.py#lists.*; processes.json#daniel-api-01"
version: 2.0.0
```

#### B.6.6 登记项：指标 metric.creator.avg_views.reported（M1）

```yaml
id: metric.creator.avg_views.reported
type: metric
label: 均播（接口均值 · 近 28 天）
owner: 总监代签（2026-11-08）
status: active
stage: ""
surfaces:
  api_field:
    kind: mean
    window: last_28_days
    sample_rule: 该范围 videoCount>0；vod／shorts 的 videoCount=0 时该字段缺失（正常，不是错误）
    min_sample: 1
    data_status: unreliable
    unit: 次播放
    source: "lib/worker.py:234; lib/normalize.js:232"
external_only: none
data_status: unreliable
definition: 窗口内总播放 ÷ 窗口内新视频数（均值）；字段为 discovery.getChannelInsight 的 stats.overall／vod／shorts.averageViewsPerVideo，三个范围各自独立、不可互算。
source: "lib/worker.py:234; lib/normalize.js:155-161,232-249; docs/marketing/skills/kol-intelligence.md:674"
version: 2.0.0
```

#### B.6.7 登记项：指标 metric.creator.avg_views.drawer_28d（M2）

```yaml
id: metric.creator.avg_views.drawer_28d
type: metric
label: 均播（详情抽屉 · 近 28 天 · 中位数）
owner: 总监代签（2026-11-08）
status: active
stage: screening
surfaces:
  detail_drawer:
    kind: median
    window: last_28_days
    sample_rule: 长视频=contentType VIDEO_ON_DEMAND 且 views>=100；短视频=SHORTS（无播放阈值）；28 天内且条数>=3 用该批，否则退回最新 30 条
    min_sample: 5
    data_status: reliable
    unit: 次播放
    source: "lib/normalize.js:173,188,192,199,217"
external_only: detail_drawer
data_status: reliable
definition: 长视频与短视频各自播放量的中位数；「整体」=长视频样本∪短视频样本（不是全部视频：播放<100 的长视频页面本来就不计）；窗口近 28 天，不足 3 条退回最新 30 条。历史口径「时长>60 秒」已按代码更正。
source: "lib/normalize.js:155-229; docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md:144-171（dev-side）"
version: 2.0.0
```

#### B.6.8 登记项：指标 metric.creator.avg_views.pool_12m100（M3）

```yaml
id: metric.creator.avg_views.pool_12m100
type: metric
label: 均播（名单产线 · 最近 12 个月 ∩ 最新 100 条 · 中位数）
owner: 总监代签（2026-11-08）
status: active
stage: screening
surfaces:
  pipeline_v2:
    kind: median
    window: last_12_months ∩ latest_100_videos
    sample_rule: 有界全量池（最近 12 个月 ∩ 最新 100 条 → 去重 → 剔 views<100）内 VOD 播放量中位数
    min_sample: 50
    data_status: reliable
    unit: 次播放
    source: "docs/marketing/skills/kol-intelligence.md:724"
external_only: pipeline_v2
data_status: reliable
definition: 有界全量池（最近 12 个月 ∩ 最新 100 条 → 去重 → 剔 views<100）内 VOD 播放量的中位数；池内样本低于 50 条时须标「池量不足」，并同时报页数／池量／池内 VOD 数／Shorts 占比。
source: "docs/marketing/skills/kol-intelligence.md:724; contracts/kol-list.json:63,73,76"
version: 2.0.0
```

#### B.6.9 登记项：指标 metric.creator.avg_views.package（M4）

```yaml
id: metric.creator.avg_views.package
type: metric
label: 均播（按成交形式取值 · CPM 分母 N）
owner: 总监代签（2026-11-08）
status: active
stage: negotiation
surfaces:
  manual_formula:
    kind: derived
    window: 随所选面
    sample_rule: 1 长→长视频均播；1 短→短视频均播；1 长+1 短→两者相加；必须写明用的是哪个面
    min_sample: 5
    data_status: unknown
    unit: 次播放
    source: "docs/marketing/skills/kol-intelligence.md:683"
external_only: none
data_status: unknown
definition: 按本行成交形式取值：1 长→长视频均播；1 短→短视频均播；1 长+1 短→两者相加；N 的取值面必须与本行 CPM 同面同窗。
source: "docs/marketing/skills/kol-intelligence.md:683; .agents/skills/kol-negotiation/SKILL.md:60"
version: 2.0.0
```

#### B.6.10 登记项：指标 metric.creator.subscribers（M5）

```yaml
id: metric.creator.subscribers
type: metric
label: 订阅数（快照）
owner: 总监代签（2026-11-08）
status: active
stage: screening
surfaces:
  api_field:
    kind: snapshot
    window: 取数时点
    sample_rule: 单频道单次；来源覆盖 getChannelDetail 6/6、parallelSearch 约 40–70%、Job 路线 100%
    min_sample: 1
    data_status: reliable
    unit: 人
    source: "lib/worker.py:209; lib/normalize.js:342"
external_only: api_field
data_status: reliable
definition: 频道订阅数快照，整数、不压缩（要能与页面的 523,922 逐格对上）。
source: "lib/worker.py:209; lib/normalize.js:147,342; docs/marketing/kol/_DANIEL-FIELD-DICTIONARY.md:294（dev-side）"
version: 2.0.0
```

#### B.6.11 登记项：指标 metric.creator.engagement_rate（M6）

```yaml
id: metric.creator.engagement_rate
type: metric
label: 互动率
owner: 总监代签（2026-11-08）
status: active
stage: screening
surfaces:
  api_field:
    kind: ratio
    window: insight 近 28 天；表现块分母用该范围全量视频，不开窗
    sample_rule: (Σlikes+Σcomments)/Σviews，分母用同一批样本；views=0 返回 null
    min_sample: 5
    data_status: unreliable
    unit: 小数 0–1（insight）
    source: "lib/normalize.js:202,211,242"
  list_item:
    kind: ratio
    window: 名单条目快照
    sample_rule: lists.getItems.engagementRate 原值
    min_sample: 5
    data_status: unreliable
    unit: 百分数（1.6 = 1.6%）
    source: "lib/normalize.js:143; _DANIEL-FIELD-DICTIONARY.md:439-442（dev-side）"
external_only: list_item
data_status: unreliable
definition: (Σlikes+Σcomments)/Σviews，分母用同一批样本；同一业务名有两个面、两种单位，交付前统一成百分数 2 位并标来源分支。
source: "lib/normalize.js:143,202-211,242; _DANIEL-FIELD-DICTIONARY.md:439-442,481（dev-side）"
version: 2.0.0
```

#### B.6.12 登记项：指标 metric.quote.cpm（M7）

```yaml
id: metric.quote.cpm
type: metric
label: CPM（报价评估）
owner: 总监代签（2026-11-08）
status: active
stage: negotiation
surfaces:
  manual_formula:
    kind: ratio
    window: 报价时点
    sample_rule: 一行一个报价；报价与 N 同面同窗；同一行只允许一个 CPM
    min_sample: 1
    data_status: unreliable
    unit: 美元／千次播放
    source: "docs/marketing/skills/kol-intelligence.md:683,3220-3227"
external_only: none
data_status: unreliable
definition: CPM = 报价 ÷ N × 1000，N = M4（按成交形式取的均播）；套餐按相加值取分母；基准区间：内部参考（不随包）。
source: "docs/marketing/skills/kol-intelligence.md:31,683,3220-3227; .agents/skills/kol-negotiation/SKILL.md:41-48,60"
version: 2.0.0
```

#### B.6.13 登记项：指标 metric.sov.platform_share（M8）

```yaml
id: metric.sov.platform_share
type: metric
label: 声量份额（平台返回 share）
owner: 总监代签（2026-11-08）
status: active
stage: sov
surfaces:
  api_field:
    kind: share
    window: --days（默认 30）
    sample_rule: 同一品类大盘内被收录视频；--country 不传时取品牌档案第一个市场
    min_sample: 1
    data_status: unknown
    unit: 百分数 1 位小数
    source: ".kol-tools/daniel_sov.py:226-232"
external_only: api_field
data_status: unknown
definition: daniel sov overview 返回的各品牌 share，百分比 1 位小数，由服务端计算，我方只读不重算；品牌不在结果里返回 None，不臆造 0。
source: ".kol-tools/daniel_sov.py:226-246; mcp/corpus/kol-daniel-api/references/60-data-layer.md:242,249"
version: 2.0.0
```

#### B.6.14 登记项：指标 metric.sov.mention_share（M9）

```yaml
id: metric.sov.mention_share
type: metric
label: 声量份额（提及份额 · 固定竞争集）
owner: 总监代签（2026-11-08）
status: active
stage: sov
surfaces:
  manual_formula:
    kind: share
    window: 由口径声明定，≥1 个月
    sample_rule: 品牌提及 ÷（自身+竞争集品牌）提及 ×100%；提及逐条回源核验；情感三档抽样判定并记录抽样规则与样本量
    min_sample: 1
    data_status: reliable
    unit: 百分数
    source: ".agents/skills/kol-execution-sov/SKILL.md:87-104,97"
external_only: manual_formula
data_status: reliable
definition: SOV = 品牌提及 ÷（自身+竞争集品牌）提及 ×100（%）；固定竞争集、同一市场、同一渠道、同一时间窗；必须与情感同读（负向高声量是警告不是胜利）。
source: ".agents/skills/kol-execution-sov/SKILL.md:87-104; processes.json#execution-sov-07"
version: 2.0.0
```

#### B.6.15 登记项：指标 metric.outreach.reply_rate（M10）

```yaml
id: metric.outreach.reply_rate
type: metric
label: 回复率（建联）
owner: 总监代签（2026-11-08）
status: active
stage: outreach
surfaces:
  outreach_system:
    kind: ratio
    window: --window A..B
    sample_rule: 回复 ÷ 发送；回复人数=有红人来信的会话数；已送达=发送−退订；已读=收件人中 opened 人数；口径按收件人逐人状态
    min_sample: 1
    data_status: unreliable
    unit: 百分数
    source: ".agents/skills/nox-weekly/SKILL.md:73,191"
external_only: outreach_system
data_status: unreliable
definition: 回复 ÷ 发送；按收件人逐人状态算，不用接口 arrive 字段单算一套；跨批次合并须带合计行且不与单批口径混。VOC 复核走 voc-report。
source: ".agents/skills/nox-weekly/SKILL.md:69-74,191; .agents/skills/nox-cli/SKILL.md:130-140"
version: 2.0.0
```

#### B.6.16 登记纪律补充（语义层 P0）

1. **面键只认六值**：`api_field`／`detail_drawer`／`pipeline_v2`／`list_item`／`manual_formula`／`outreach_system`；不设 `取值面` 字段、不写 `face:` 子键。
2. **`external_only` 必须是本条 `surfaces` 的键之一或 `none`**（`none` ＝ 该条不进对外交付件）。
3. **顶层 `data_status` ＝ `external_only` 面的状态**；面级可覆盖（M6 两面同状态、单位不同）。
4. **均播不合并**：M2（近 28 天）与 M3（最近 12 个月 ∩ 最新 100 条）平级登记，窗口写进 `id`／`label`／`definition`；契约列名只映射 M2，M3 另起列名。
5. **阈值不进随包语料**：M7 的基准区间只写「内部参考（不随包）」，具体数值只留母本 L3225。
