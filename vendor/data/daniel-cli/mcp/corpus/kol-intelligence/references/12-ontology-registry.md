<!-- 本文件是 `docs/marketing/skills/kol-intelligence.md` L6895–L6973 的**逐字切片**（语料版本 0.9.204）；请勿在此改写判据，改动须回流源文件后重跑切分器 -->
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
  - key: performance
    label: 表现与规模
    dims:
      - key: avg_views_long
        ask: 长视频均播下限？
        default: 500000
        availability: auto
      - key: engagement_rate
        ask: 互动率下限？
        default: 0.05
        availability: auto
  - key: audience
    label: 受众与地域
    dims:
      - key: market_country
        ask: 主要市场国家或地区？
        availability: auto
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
