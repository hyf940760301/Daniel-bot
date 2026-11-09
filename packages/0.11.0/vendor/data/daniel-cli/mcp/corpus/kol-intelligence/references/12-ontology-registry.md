<!-- 本文件是 `docs/marketing/skills/kol-intelligence.md` L6895–L7164 的**逐字切片**（语料版本 0.9.206）；请勿在此改写判据，改动须回流源文件后重跑切分器 -->
<!-- 源节：附录 B 语义登记（指标／判据／表达的口径登记） -->


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
owner: 业务-红人组
version: 1.0.0
```

### B.2 登记项：判据 criterion.creator.screen

```yaml
id: criterion.creator.screen
type: criterion
label: 找红人 · 筛选维度
stage: screening
owner: 业务-红人组
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
owner: 业务-红人组
sections: [概览, 名单, 每条依据, 覆盖率与缺口, 下一步]
required: [数字必须带口径与时间点, 不确定写待确认]
banned: [非常好, 绝对, 肯定没问题, 大概]
```

### B.4 登记纪律

1. **一条登记项一个 yaml 块**，块内 `id` 必填且全局唯一；
2. `owner` 必填（业务角色），无 owner 不入索引；
3. 阈值只作为 `default` 出现，**最终取值由用户在任务开始前确认**，不由登记项决定；
4. `availability: unavailable` 的维度不得出现在提问清单里；
5. 本附录不写流程顺序，流程以 `intake/processes.json` 为准。

### B.5 登记项：判据 criterion.clarify.param_gate

```yaml
id: criterion.clarify.param_gate
type: criterion
label: 澄清闸 · 参数级追问（4 场景 / 28 项）
owner: 业务-红人组
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
