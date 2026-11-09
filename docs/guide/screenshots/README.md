# 截图存放目录（screenshots/）

把截图按下面的文件名放在本目录，v2 会自动匹配插入指南。

| 文件名 | 对应指南位置 |
|---|---|
| `S1-nav.png` | 引导章 · 图 1 |
| `S2-brand-deep-input.png` | 1.2 · 图 2 |
| `S3-brand-deep-filled.png` | 1.2（选截） |
| `S4-result-list.png` | 1.3 · 图 3 |
| `S5-open-research.png` | 1.4 · 图 4 |
| `S6-content-expansion.png` | 1.5 · 图 5 |
| `S7-creator-drawer-top.png` | 1.6 · 图 6 |
| `S8-creator-drawer-bottom.png` | 1.6 · 图 7 |
| `S9-brand-analysis-setup.png` | 2.3 · 图 8 |
| `S10-marketing-read.png` | 2.4 · 图 9 |
| `S11-evidence.png` | 2.5 · 图 11 |
| `S12-authenticity.png` | 3.3 · 图 12 |
| `S13-authenticity-warning.png` | 3.4（选截，对照） |
| `S14-analytics-unavailable.png` | 1.6（选截，反例） |
| `S15-objections.png` | 2.4 · 图 10（选截） |
| `S16-analysis-running.png` | 2.3（选截） |

**要求**：PNG · 中文界面 · 窗口宽度一致（建议 ≥1440px，缩放 100%）· 敏感信息整块遮盖 · 文件名严格一致（区分大小写）。

详细取景与标注要求见同级目录的 `截图清单.md`。放入图片后跑一次一致性检查：

```bash
python3 .kol-tools/check_guide_figures.py --html docs/marketing/daniel-guide/Daniel-系统功能指南.html \
    --checklist docs/marketing/daniel-guide/截图清单.md \
    --shots docs/marketing/daniel-guide/screenshots
```
