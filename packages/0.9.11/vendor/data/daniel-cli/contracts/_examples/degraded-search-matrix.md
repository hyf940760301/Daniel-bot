# _tmp-退化样本 ｜ 检索词矩阵（**故意不合规 · 自建夹具** · TICKET-158）

> 本文件是 TICKET-158 的**退化样本**：故意把词表写坏，用来证明 `daniel keywords check`
> 真的会拦下它、并把违规项逐条指出来（不是笼统报一句"不合规"）。
> **它不是任何品牌的交付物、不得引用、不得对外发出。**
> 故意埋进去的缺陷（按语料判据应当逐条被报出）：
> 1) 类别缺失（十类里只写了 3 类）；
> 2) 词量越界（每类 Tag／短尾词／长句都不够，全表合计远低于 300 条）；
> 3) 类内重复（同一类别里 Tag 行与短尾词行出现完全重复的词面）；
> 4) 条件词被当成短尾词单搜；
> 5) 命中负向词（giveaway／deals-only／meme）；
> 6) 词面带装饰符号（井号、引号）；
> 7) 长句没有句号收尾；
> 8) 地域锚点没放在词首；
> 9) 命中品牌方"禁用词"（未核验的表述）；
> 10) 导语表声明的词量与实际明细对不上（计数不自洽）。
>
> 期望结果：合规＝否；违规项 ≥ 3 条且逐条给出类别／类型／词面／违规说明／来源。

## 2. 十个类别 · 检索词矩阵（导语表 · 声明数与实际明细故意对不上）

| 类别 | 用途 | Tag | 短尾词 | 其中：仅作"且"的条件词 | 长句 |
|---|---|---|---|---|---|
| 1. 品类与形态 | 主赛道召回 | 6 | 4 | 0 | 2 |
| 2. 竞品与替代品 | 迁移召回 | 4 | 2 | 1 | 1 |

### 类别 1 ｜ 品类与形态 —— 顾客会怎么称呼这台设备

| 类型 | 搜索词 | 用途 / 怎么用 | 实测命中 |
|---|---|---|---|
| **Tag**（标签框用词） | smart glasses, #smartglasses, AI glasses, smart glasses, AR glasses | 标签框/话题入口用词 | — |
| **长句**（AI 语义搜索） | Find creators who review AI glasses on camera, show real wear time and daily use<br>Find creators who cover camera-free smart glasses. | AI 语义搜索 | — |
| **短尾词**（关键词框直搜） | smart glasses, AI glasses review, "living with AI glasses", smart glasses uk | 关键词框直搜 | — |
| **条件词**（仅作"且"，不得单搜） | meeting notes, live translation, giveaway | 只能与类别 1 / 2 的锚点 AND 组合 | — |

### 类别 2 ｜ 竞品与替代品 —— 谁已经测过同类对手

| 类型 | 搜索词 | 用途 / 怎么用 | 实测命中 |
|---|---|---|---|
| **Tag**（标签框用词） | ray ban meta, xreal, rokid | 标签框/话题入口用词 | — |
| **短尾词**（关键词框直搜） | Ray-Ban Meta, deals-only smart glasses | 关键词框直搜 | — |
| **条件词**（仅作"且"，不得单搜） | ray ban meta | 只能与锚点 AND 组合 | — |

### 类别 10 ｜ 扩圈相邻垂类 —— 观众匹配但没做过本品类

| 类型 | 搜索词 | 用途 / 怎么用 | 实测命中 |
|---|---|---|---|
| **Tag**（标签框用词） | productivity tools, future of work, meme | 标签框/话题入口用词 | — |
| **短尾词**（关键词框直搜） | AI glasses for productivity, high-brightness dual-eye AI glasses | 关键词框直搜 | — |
| **条件词**（仅作"且"，不得单搜） | productivity tools, AI glasses for productivity | 只能与锚点 AND 组合 | — |

## 3. 排除清单与禁用词

**禁用词（品牌书未覆盖或未核验，检索式、邮件、表格一律不得出现）**：high-brightness dual-eye、45+ languages。

## 5. 交付前自检

- [ ] 十类别齐全，每类都有 Tag、长句、短尾词三种词（本夹具故意不齐）
