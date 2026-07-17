---
name: financial-report-analysis
description: >-
  财报分析核心技能。当用户的问题涉及上市公司财报时触发：
  - 询问营收、利润、毛利率、净利率、ROE、负债率、现金流等财务指标
  - 对比多家公司的财务表现（如"茅台和五粮液谁更赚钱"）
  - 分析财报变化趋势（同比、环比、季度变化）
  - 杜邦分析、现金流质量分析、估值分析
  - 任何涉及"财报""年报""季报""利润表""资产负债表""现金流量表""财务数据""业绩"等词汇
  - 用户上传了 PDF/Excel 财报文件并希望分析
  宁可多用此技能，不可漏用。财务相关问题如果不使用此技能，你将没有数据来源。
allowed-tools:
  - financial_data
  - stock_info
  - financial_metrics
  - web_search
  - web_fetch
  - bash
  - read_file
  - write_file
  - task
---

# 财报分析

## Overview

此技能提供专业的三地（A股/港股/美股）上市公司财报分析能力。覆盖盈利能力、成长性、财务健康度、估值、现金流质量等分析维度。自动获取数据、计算指标、生成图表，最终输出结构化分析报告。

## 核心方法论：5 阶段分析工作流

### Phase 1: 需求理解

在拉取任何数据之前，先明确用户真正想知道什么。

**步骤：**
1. 识别涉及的上市公司及其股票代码
   - 用户只说公司名（如"茅台"）时，先用 `web_search` 确认代码
   - 代码格式：A股6位数字、港股加 `HK.` 前缀、美股用字母代码
2. 识别时间范围（最新季报？2024年报？近5年？）
3. 识别用户关心的核心指标和维度
4. 确认输出要求（纯文本？图表？Excel？）

**输出：** 在回复中简要确认分析计划，给用户一个预期。

### Phase 2: 数据获取

用工具获取所有需要的结构化数据和非结构化背景信息。

> **推荐：** 将此阶段委派给 `financial-data-fetcher` 子代理。子代理专注于数据获取，不会被分析思路干扰。

**步骤（自行执行时）：**
1. 对每家公司调用 `stock_info` 确认代码和基本信息
2. 调用 `financial_data` 获取三张表（`report_type="all"`，`period=目标期间`）
3. 如有趋势分析需求，再获取多期数据
4. 调用 `web_search` 补充搜索：最新公告、行业动态、券商观点
5. 将原始数据写入 workspace：
   ```
   /mnt/user-data/workspace/financials/{stock_code}_{period}.json
   ```

**检查清单：**
- [ ] 所有目标公司的基本信息已获取
- [ ] 所有目标期间的三张表数据已获取
- [ ] 已搜索最新公告和新闻

### Phase 3: 分析计算

用 `financial_metrics` 工具执行确定性计算，然后基于数据做定性分析。

> **推荐：** 将此阶段委派给 `financial-analyst` 子代理。
> 委托前先读取 `skills/custom/financial-metrics-calc/references/formulas.md` 了解各指标公式和解读方法。

**步骤：**
1. 调用 `financial_metrics` 计算各项指标（传入 Phase 2 获取的 JSON 数据）
2. 如果是跨市场对比，注意会计准则差异（读取 `references/accounting.md`）
3. 执行分析：
   - 盈利能力：ROE 拆解（杜邦分析）、毛利率趋势、费用率
   - 成长性：营收/利润 CAGR、同比环比
   - 财务健康度：负债结构、偿债能力、现金流质量
   - 估值：PE/PB 历史分位（如果获取了历史估值数据）
4. 对照行业基准判断公司所处水平

**分析框架速查：**

| 分析目的 | 推荐框架 | 关键指标 |
|---------|---------|---------|
| 盈利质量 | 杜邦分析 | ROE、净利率、周转率、杠杆 |
| 成长性 | 收入拆解 | 营收CAGR、量价拆解 |
| 财务风险 | 风险评估 | 流动比率、负债率、Z-score |
| 现金流 | 现金流质量 | OCF/NI比、FCF Yield |
| 同业对比 | 多维度排名 | 雷达图/矩阵 |

**委托给专项 Skills 的分析（按需加载）：**
- 需要深入指标计算和同业对比 → 读取 `skills/custom/financial-metrics-calc/SKILL.md`
- 需要风险评估 → 读取 `skills/custom/financial-risk-assessment/SKILL.md`
- 需要估值分析 → 读取 `skills/custom/financial-valuation/SKILL.md`

### Phase 4: 可视化

为关键发现生成图表。

> **委托给 `chart-visualization` skill。** 不要自己写图表代码。

**常用图表类型：**
- ROE 对比 → 柱状图（读取 `chart-visualization` 的 `references/generate_bar_chart.md`）
- 趋势变化 → 折线图（读取 `references/generate_line_chart.md`）
- 杜邦拆解 → 瀑布图/堆叠柱状图

### Phase 5: 报告合成

将分析结果组织为专业报告。

> **推荐：** 将此阶段委派给 `report-generator` 子代理。

**报告结构（参照 `templates/report_template.md`）：**
1. 执行摘要（300字以内，核心结论+3-5个关键数据）
2. 公司概览（行业、市值、营收规模）
3. 财务表现分析（按三张表展开）
4. 关键指标解读
5. 风险提示
6. 总结与展望

**如需 Excel 导出：**
```bash
python /mnt/skills/custom/financial-report-analysis/scripts/export_report.py \
  --analysis-file /mnt/user-data/workspace/analysis.json \
  --metrics-file /mnt/user-data/workspace/metrics.json \
  --output /mnt/user-data/outputs/report.xlsx
```

## 质量检查清单

在完成分析前逐项检查：
- [ ] 所有金额已标注单位（元/万元/亿元）
- [ ] 同比/环比数据已注明基期
- [ ] 对比分析时已考虑会计准则差异
- [ ] 已标注数据来源和数据截止日期
- [ ] 异常数据已识别并说明可能原因
- [ ] 不确定的结论已明确标注
- [ ] 涉及投资建议时已附加风险提示

## 完整示例

### 场景：对比茅台和五粮液的2024年报

**用户输入：** "帮我分析茅台和五粮液的2024年年报，ROE有没有下降？谁更值得投资？"

**Phase 1 →** 识别：茅台(600519)、五粮液(000858)，2024年报，关注ROE趋势和综合对比

**Phase 2 →** 数据获取：
```
financial_data("600519", "all", "2024")
financial_data("000858", "all", "2024")
stock_info("600519")
stock_info("000858")
web_search("茅台 2024年报 业绩")
web_search("五粮液 2024年报 业绩")
```

**Phase 3 →** 分析计算：调用 `financial_metrics` 对各公司数据计算 ROE、杜邦拆解、毛利率、同比增长率

**Phase 4 →** 生成 ROE 对比柱状图

**Phase 5 →** 输出报告：
```
📊 茅台 vs 五粮液 2024年报分析

一、执行摘要
2024年茅台ROE为X%，五粮液ROE为Y%...
（附ROE对比柱状图）

二、盈利能力对比
杜邦拆解显示...

三、风险提示
- 白酒行业整体增速放缓
- ...

四、结论
...
```

> ⚠️ **重要提醒：**
> - 所有分析结论必须基于实际获取的数据，绝不编造
> - 数据源限制（如 akshare 偶尔不可用）必须告知用户
> - 首次出现的专业术语提供括号中文说明
