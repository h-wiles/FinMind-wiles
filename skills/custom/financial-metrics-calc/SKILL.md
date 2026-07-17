---
name: financial-metrics-calc
description: >-
  财务指标计算与同业对比技能。当需要对财报数据进行深入指标计算、杜邦分析拆解、
  多公司横向对比时触发：
  - "计算ROE并做杜邦拆解"、"毛利率怎么算的"
  - "对比这几家公司的盈利能力"
  - "分析营收增长的驱动因素"
  - 任何需要确定性计算（非LLM估算）的财务指标
  此技能确保指标计算准确、公式透明、结果可复现。
allowed-tools:
  - financial_metrics
  - bash
  - read_file
  - write_file
---

# 财务指标计算与同业对比

## Overview

此技能提供财务指标的确定性计算能力。核心原则：**所有数值计算必须通过 `financial_metrics` 工具或 `calculate.py` 脚本执行，禁止 LLM 手算。** 这是因为 LLM 的数值计算不可靠，可能产生误差。

## 指标计算工作流

### Step 1: 确认数据完整性

在计算前，确认数据文件包含必要字段。不同指标依赖不同的报表科目：

| 指标 | 依赖报表 | 关键科目 |
|------|---------|---------|
| ROE | 利润表 + 资产负债表 | 净利润、股东权益 |
| 毛利率 | 利润表 | 营业收入、营业成本 |
| 净利率 | 利润表 | 净利润、营业收入 |
| 资产负债率 | 资产负债表 | 总负债、总资产 |
| 流动比率 | 资产负债表 | 流动资产、流动负债 |
| FCF Yield | 现金流量表 + 行情 | 经营现金流、资本支出、市值 |
| 同比增速 | 利润表（多期） | 营收、净利润（当前+去年同期） |

如果数据不完整，先回到 `financial-report-analysis` Skill 的 Phase 2 补取数据。

### Step 2: 执行计算

**方式一：使用 `financial_metrics` 工具（推荐，单期数据）**

```
financial_metrics(
    json_data=<financial_data 返回的 JSON>,
    metrics="roe,gross_margin,net_margin,dupont"
)
```

**方式二：使用 calculate.py 脚本（多期数据或批量计算）**

```bash
python /mnt/skills/custom/financial-report-analysis/scripts/calculate.py \
  --data-file /mnt/user-data/workspace/financials/600519_2024.json \
  --metrics "roe,gross_margin,net_margin,debt_ratio,current_ratio,dupont,yoy_growth" \
  --output /mnt/user-data/workspace/metrics_600519_2024.json
```

### Step 3: 解读结果

计算完成后，对照基准值给出解读。读取 `references/formulas.md` 获取：
- 每个指标的详细公式
- 不同行业的合理范围
- 异常的常见原因

## 同业对比工作流

### Step 1: 确定可比公司

- 同行业（GICS 行业分类一致或相近）
- 相近市值规模（不要拿千亿和十亿比）
- 同样的报告期（确保时间窗口一致）

### Step 2: 逐公司计算核心指标

对每家公司执行相同的指标集，写入统一格式的对比文件：

```bash
# 对每家公司执行
python /mnt/skills/custom/financial-report-analysis/scripts/calculate.py \
  --data-file /mnt/user-data/workspace/financials/{stock}_{period}.json \
  --metrics "roe,gross_margin,net_margin,debt_ratio,yoy_growth" \
  --output /mnt/user-data/workspace/metrics_{stock}_{period}.json
```

### Step 3: 生成对比表

将多家公司的指标汇总为对比表格：

| 指标 | 公司A | 公司B | 公司C | 行业均值 |
|------|-------|-------|-------|---------|
| ROE | | | | |
| 毛利率 | | | | |
| 净利率 | | | | |
| 营收增速 | | | | |

### Step 4: 分析与排名

- 标注每个指标的最优值和最差值
- 分析差距原因（品牌溢价？规模效应？成本结构？）
- 如果涉及跨市场对比，特别注意会计准则差异

## 杜邦分析专项

杜邦分析是理解 ROE 驱动因素的核心工具。

### 三因子模型

ROE = 净利率 × 资产周转率 × 权益乘数

- **净利率高** → 品牌/技术优势（高附加值）
- **周转率高** → 运营效率优秀（薄利多销）
- **杠杆高** → 依赖债务驱动（风险关注点）

### 解读方法

1. 逐年对比各因子的变化，锁定 ROE 变动的主导因素
2. 和同行业公司对比，看差异来自哪个因子
3. 警惕高杠杆拉动的 ROE（权益乘数 > 3 时需关注风险）

### 执行

```bash
python /mnt/skills/custom/financial-report-analysis/scripts/calculate.py \
  --data-file /mnt/user-data/workspace/financials/{stock}_{period}.json \
  --metrics "dupont" \
  --output /mnt/user-data/workspace/dupont_{stock}_{period}.json
```

## 计算结果的可靠性原则

1. **标注数据来源** — 每个指标标注出自哪张表的哪个科目
2. **标注计算假设** — 如"ROE 使用期末股东权益（未取平均）"
3. **识别异常值** — 如果某项指标远超行业正常范围，主动标注并分析可能原因（数据错误？一次性损益？会计准则差异？）
4. **不要修饰数字** — 计算结果是什么就是什么，不要为了让"故事好看"而选择性报告
