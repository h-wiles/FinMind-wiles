

# 二次开发思路

## DeerFlow 扩展点分析

DeerFlow 的设计哲学是 **"框架提供基础设施，Skill 承载领域知识"**。构建垂直领域 Agent 的本质，是在 DeerFlow 的 5 个核心扩展点上填入领域专属内容：

```
DeerFlow 扩展点              本项目填什么              影响范围
─────────────────────────────────────────────────────────
① community/ 工具    →   financial_data / stock_info   新增可调用工具
                         / financial_metrics

② skills/custom/     →   SKILL.md + 脚本 + 参考资料    Agent 行为模式

③ subagents.custom   →   3 个专项子代理               任务委派策略
   _agents

④ SOUL.md +          →   分析师人格 + 会计准则知识     Agent 身份
   memory.json

⑤ config.yaml        →   工具注册 + 子代理配置         全局集成
   + extensions_      →   Skill 启用/禁用
   config.json
```

### 关键设计原则（来自 DeerFlow skill-creator）

1. **Pushy Description** — Skill 的 `description` frontmatter 要主动"抢占"触发场景，防止 Agent 漏触发。宁可过度声明，不可保守。

2. **Progressive Disclosure（渐进式加载）** — SKILL.md 主体控制在 500 行以内，详细参考资料放入 `references/` 按需读取。

3. **Script as Black Box** — 计算脚本通过 CLI 调用，Agent 不读取脚本源码。保证确定性计算的同时节省 context。

4. **Phase 结构** — 用阶段化工作流（Phase 1→5）引导 Agent 的思维链，每阶段有明确的输入/输出/检查清单。

---

## 设计决策

### 决策 1：工具层 — 为什么不用 MCP Server？

DeerFlow 支持两种外部工具接入方式：

| 方式 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| **Community 工具**（本项目选择） | 与 DeerFlow 深度集成、配置简单、只需一个 Python 文件 | 依赖 DeerFlow 加载机制 | 紧密耦合的工具 |
| **MCP Server** | 独立进程、跨项目复用、标准协议 | 需管理额外进程、配置较复杂 | 通用/可复用工具 |

**选择 Community 工具的原因：** 财报数据获取与 DeerFlow 的 skill 系统和 config 热加载深度耦合。Agent 需要根据 skill 的指导调用正确的数据接口，而 Community 工具可以直接读取 `config.yaml` 中的 tool config。

### 决策 2：数据源 — 免费优先

| 库 | 覆盖市场 | 费用 | 稳定性 |
|----|---------|------|--------|
| **akshare** | A 股、港股 | 免费 | 中（依赖东方财富/新浪接口，可能变动）|
| **yfinance** | 美股、港股 | 免费 | 中（非官方接口） |
| Tushare Pro | A 股 | 需积分 | 高 |
| Wind API | 全部 | 昂贵 | 高 |

**选择 akshare + yfinance 的原因：** 零成本启动，覆盖三地市场。生产环境可替换为商业数据源。

### 决策 3：子代理拆分 — 关注点分离

将财报分析拆分为 3 个子代理，而非 1 个全能 Agent：

```
主 Agent (财务分析师)
  │
  ├─→ financial-data-fetcher   — 只取数据，不分析
  │    工具：financial_data, web_search, write_file
  │    约束：禁止 task、ask_clarification
  │
  ├─→ financial-analyst        — 只分析，不取数据
  │    工具：financial_metrics, bash, read_file
  │    约束：禁止 task、financial_data、web_search
  │
  └─→ report-generator         — 只合成报告，不分析
       工具：bash, write_file
       约束：禁止 task、ask_clarification
       技能：chart-visualization
```

**好处：**
- 每个子代理的 system prompt 更短、更聚焦
- 工具权限更精细（data-fetcher 不能分析，analyst 不能搜索）
- 出问题时容易定位是哪个环节出错
- 可以给不同子代理分配不同模型（data-fetcher 用小模型省钱，analyst 用大模型保证质量）

---

## 数据流设计

### 一次完整分析的数据流

```
用户输入
  │
  ▼
┌─ Phase 1: 需求理解 ─────────────────────────────────────┐
│  输入：用户原始消息                                        │
│  处理：识别 股票代码、市场、分析维度、时间范围              │
│  输出：结构化的分析需求                                    │
│  例如：{stocks: ["600519","000858"], period: "2024Q4",    │
│         metrics: ["ROE","毛利率","杜邦分析"]}              │
└──────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Phase 2: 数据获取（委派 financial-data-fetcher）─────────┐
│  ┌─────────────────────────────────────────────────────┐ │
│  │ financial_data("600519", "2024", "annual")          │ │
│  │   → {资产负债表, 利润表, 现金流量表}                  │ │
│  │ financial_data("000858", "2024", "annual")          │ │
│  │ web_search("茅台 2024年报 公告 营收 利润")           │ │
│  │   → [新闻、研报、公告链接]                            │ │
│  └─────────────────────────────────────────────────────┘ │
│  输出：/mnt/user-data/workspace/financials/               │
│        ├── 600519_2024_annual.json                        │
│        ├── 000858_2024_annual.json                        │
│        └── news_context.md                                │
└──────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Phase 3: 分析计算（委派 financial-analyst）──────────────┐
│  ┌─────────────────────────────────────────────────────┐ │
│  │ bash: python calculate.py --data-file ...           │ │
│  │       --metrics "roe,gross_margin,dupont,yoy_growth" │ │
│  │   → {ROE: 29.8%, 杜邦拆解: {净利率:51.5%, ...}}     │ │
│  └─────────────────────────────────────────────────────┘ │
│  输出：/mnt/user-data/workspace/metrics.json              │
│        /mnt/user-data/workspace/analysis.json             │
└──────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Phase 4: 可视化 ───────────────────────────────────────┐
│  输入：metrics.json                                      │
│  处理：读取 chart-visualization skill 的 references/      │
│        → generate_bar_chart.md                           │
│        → generate_line_chart.md                          │
│  调用：node scripts/generate.js '{"tool":"bar_chart",    │
│         "args":{...}}'                                   │
│  输出：图表 PNG URL                                       │
└──────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Phase 5: 报告合成（委派 report-generator）──────────────┐
│  ┌─────────────────────────────────────────────────────┐ │
│  │ 按 report_template.md 模板合成报告                    │ │
│  │ bash: python export_report.py                       │ │
│  │       --analysis-file analysis.json                  │ │
│  │       --metrics-file metrics.json                   │ │
│  │       --output /mnt/user-data/outputs/report.xlsx   │ │
│  └─────────────────────────────────────────────────────┘ │
│  输出：文本报告 + 图表 + Excel 文件                        │
└──────────────────────────────────────────────────────────┘
```

---

# 实施步骤

## 第一阶段：数据层 — 财务数据工具模块

> **目标：** 让 Agent 能通过工具调用获取 A 股/港股/美股的结构化财务数据。
>
> **新建文件：** 3 个 | **修改文件：** 1 个（config.yaml）

### 1.1 创建数据提供商抽象层

**文件：** `backend/packages/harness/deerflow/community/financial/provider.py`

核心思路：定义统一的 `FinancialDataProvider` 抽象类，由三个实现类分别处理不同市场，再用 `CompositeProvider` 根据股票代码自动路由。

```python
"""
财务数据提供商抽象层。

支持的提供商：
- AkshareProvider：A股 + 港股主力（免费，无需 API Key）
- YfinanceProvider：美股主力 + 港股补充
- CompositeProvider：自动路由（根据股票代码前缀选择提供商）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StockIdentifier:
    """统一股票标识"""
    raw_code: str           # 用户输入的原始代码
    market: str             # "a_share" | "hk_share" | "us_share"
    normalized_code: str    # 各 provider 内部使用的标准化代码


class FinancialDataProvider(ABC):
    """财务数据提供商抽象基类"""

    @abstractmethod
    def get_financial_report(
        self, stock_code: str, report_type: str, period: str
    ) -> dict:
        """
        获取财报数据。

        Args:
            stock_code: 股票代码（标准化后的格式）
            report_type: "balance_sheet" | "income_statement" | "cash_flow"
            period: "2024" | "2024Q3" | "2024-12-31"

        Returns:
            {
                "stock_code": str,
                "stock_name": str,
                "report_type": str,
                "period": str,
                "data": [{"item": "营业收入", "amount": 150000000000, "unit": "元"}, ...]
            }
        """
        ...

    @abstractmethod
    def get_stock_info(self, stock_code: str) -> dict:
        """
        获取股票基本信息和实时估值指标。

        Returns:
            {
                "stock_code": str,
                "stock_name": str,
                "market": str,
                "industry": str,
                "market_cap": float,
                "pe_ratio": float,
                "pb_ratio": float,
                "ps_ratio": float | None,
                "dividend_yield": float | None,
                "52w_high": float | None,
                "52w_low": float | None,
            }
        """
        ...

    @abstractmethod
    def get_historical_financials(self, stock_code: str, years: int = 5) -> list[dict]:
        """
        获取历年财务数据（用于趋势分析）。

        Returns:
            [{"period": "2024", "revenue": ..., "net_profit": ..., ...}, ...]
        """
        ...


class AkshareProvider(FinancialDataProvider):
    """A股 + 港股数据提供商（基于 akshare）"""

    def get_financial_report(self, stock_code, report_type, period):
        import akshare as ak
        # A股示例：stock_financial_abstract_ths(symbol="600519", indicator="按报告期")
        # 港股示例：stock_hk_financial_indicator_em(symbol="00700")
        ...

    def get_stock_info(self, stock_code):
        import akshare as ak
        # stock_individual_info_em(symbol="600519") → PE/PB/市值
        # stock_hk_spot_em() → 港股实时行情
        ...

    def get_historical_financials(self, stock_code, years=5):
        ...


class YfinanceProvider(FinancialDataProvider):
    """美股 + 港股补充数据提供商（基于 yfinance）"""

    def get_financial_report(self, stock_code, report_type, period):
        import yfinance as yf
        # ticker = yf.Ticker("AAPL")
        # ticker.balance_sheet / ticker.financials / ticker.cashflow
        ...

    def get_stock_info(self, stock_code):
        import yfinance as yf
        # ticker.info → market_cap, pe_ratio, etc.
        ...

    def get_historical_financials(self, stock_code, years=5):
        ...


class CompositeProvider(FinancialDataProvider):
    """组合提供商 — 根据股票代码前缀自动路由"""

    def __init__(self):
        self._a_share = AkshareProvider()
        self._us_hk = YfinanceProvider()

    def _classify(self, raw_code: str) -> StockIdentifier:
        """根据代码格式识别市场。

        规则：
        - 6xxxxx → A股（上交所）
        - 0xxxxx / 3xxxxx → A股（深交所）
        - HK.xxxxx → 港股
        - 纯字母（1-5 个字符）→ 美股
        """
        code = raw_code.strip().upper()
        if code.startswith("HK."):
            return StockIdentifier(raw_code, "hk_share", code[3:])
        if code.isdigit() and len(code) == 6:
            return StockIdentifier(raw_code, "a_share", code)
        if code.isalpha() and 1 <= len(code) <= 5:
            return StockIdentifier(raw_code, "us_share", code)
        raise ValueError(f"无法识别股票代码 {raw_code} 的市场。"
                         f"支持格式：600519（A股）、HK.00700（港股）、AAPL（美股）")

    def _route(self, sid: StockIdentifier) -> FinancialDataProvider:
        if sid.market == "a_share":
            return self._a_share
        return self._us_hk  # 港股和美股都用 yfinance（港股 akshare 备用）

    def get_financial_report(self, stock_code, report_type, period):
        sid = self._classify(stock_code)
        return self._route(sid).get_financial_report(
            sid.normalized_code, report_type, period
        )

    def get_stock_info(self, stock_code):
        sid = self._classify(stock_code)
        result = self._route(sid).get_stock_info(sid.normalized_code)
        result["market"] = sid.market
        return result

    def get_historical_financials(self, stock_code, years=5):
        sid = self._classify(stock_code)
        return self._route(sid).get_historical_financials(
            sid.normalized_code, years
        )
```

### 1.2 创建 LangChain 工具

**文件：** `backend/packages/harness/deerflow/community/financial/tools.py`

仿照 `community/tavily/tools.py` 的模式，创建 3 个工具。关键约定：

- 所有工具返回 **JSON 字符串**（不是 dict），保证 Agent 能正确解析
- 错误时返回 `{"error": str, "query": str}` 而不是抛出异常
- 使用 `@tool(name, parse_docstring=True)` 注册
- 通过 `get_app_config().get_tool_config(name)` 读取配置

```python
"""
DeerFlow 财务数据工具。

提供 3 个 LangChain tool：
- financial_data：获取上市公司财报数据
- stock_info：获取股票基本信息和实时估值指标
- financial_metrics：计算财务指标
"""

import json

from langchain.tools import tool

from deerflow.config import get_app_config
from deerflow.community.financial.provider import CompositeProvider


# 全局单例 provider（lazy init）
_provider: CompositeProvider | None = None


def _get_provider() -> CompositeProvider:
    global _provider
    if _provider is None:
        _provider = CompositeProvider()
    return _provider


@tool("financial_data", parse_docstring=True)
def financial_data_tool(
    stock_code: str,
    report_type: str = "all",
    period: str = "latest",
) -> str:
    """获取上市公司财报数据。支持 A股（6位代码）、港股（HK.前缀）、美股（字母代码）。

    当需要获取某公司的资产负债表、利润表、现金流量表时使用此工具。
    返回结构化 JSON 数据，包含报表科目名称和金额。

    Args:
        stock_code: 股票代码。A股用6位数字如 600519（茅台），港股加 HK. 前缀如 HK.00700（腾讯），美股用字母代码如 AAPL
        report_type: 报表类型。"balance_sheet"（资产负债表）、"income_statement"（利润表）、
                     "cash_flow"（现金流量表）、"all"（全部三张表）
        period: 报告期。"latest"（最新）、"2024"（2024年报）、"2024Q3"（2024年三季报）
    """
    try:
        provider = _get_provider()
        if report_type == "all":
            results = {}
            for rt in ["income_statement", "balance_sheet", "cash_flow"]:
                results[rt] = provider.get_financial_report(
                    stock_code, rt, period
                )
            return json.dumps(results, indent=2, ensure_ascii=False, default=str)
        return json.dumps(
            provider.get_financial_report(stock_code, report_type, period),
            indent=2, ensure_ascii=False, default=str,
        )
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "stock_code": stock_code,
            "report_type": report_type,
            "period": period,
        }, ensure_ascii=False)


@tool("stock_info", parse_docstring=True)
def stock_info_tool(stock_code: str) -> str:
    """获取股票基本信息和实时估值指标。包含市值、PE、PB、行业分类、股息率等。

    当需要了解某公司的基本信息（市值大小、估值水平、所属行业）时使用此工具。
    也可用于在获取财报前先确认股票代码是否正确。

    Args:
        stock_code: 股票代码。格式同 financial_data 工具。
    """
    try:
        provider = _get_provider()
        return json.dumps(
            provider.get_stock_info(stock_code),
            indent=2, ensure_ascii=False, default=str,
        )
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "stock_code": stock_code,
        }, ensure_ascii=False)


@tool("financial_metrics", parse_docstring=True)
def financial_metrics_tool(
    json_data: str,
    metrics: str = "all",
) -> str:
    """基于原始财报数据计算财务指标。不依赖 LLM 计算，保证准确性。

    支持的指标（逗号分隔）：
    - roe：净资产收益率 = 净利润 / 股东权益
    - gross_margin：毛利率 = (营收 - 营业成本) / 营收
    - net_margin：净利率 = 净利润 / 营收
    - debt_ratio：资产负债率 = 总负债 / 总资产
    - current_ratio：流动比率 = 流动资产 / 流动负债
    - dupont：杜邦分析（ROE = 净利率 × 资产周转率 × 权益乘数）
    - fcf_yield：自由现金流收益率
    - yoy_growth：同比增长率（营收、净利润）
    - all：以上全部

    Args:
        json_data: financial_data 工具返回的 JSON 数据字符串
        metrics: 要计算的指标，逗号分隔

    Returns:
        JSON 字符串，包含各项指标的计算结果、公式和简要解读
    """
    try:
        data = json.loads(json_data)
        metric_list = (
            ["roe", "gross_margin", "net_margin", "debt_ratio",
             "current_ratio", "dupont", "yoy_growth"]
            if metrics == "all"
            else [m.strip() for m in metrics.split(",")]
        )

        results = {}
        for metric in metric_list:
            if metric == "roe":
                results["roe"] = _calc_roe(data)
            elif metric == "gross_margin":
                results["gross_margin"] = _calc_gross_margin(data)
            elif metric == "net_margin":
                results["net_margin"] = _calc_net_margin(data)
            elif metric == "debt_ratio":
                results["debt_ratio"] = _calc_debt_ratio(data)
            elif metric == "current_ratio":
                results["current_ratio"] = _calc_current_ratio(data)
            elif metric == "dupont":
                results["dupont"] = _calc_dupont(data)
            elif metric == "yoy_growth":
                results["yoy_growth"] = _calc_yoy_growth(data)

        return json.dumps(results, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e), "metrics": metrics}, ensure_ascii=False)


# ─── 计算函数（纯函数，便于测试）──────────────────────────

def _calc_roe(data: dict) -> dict:
    """ROE = 净利润 / 平均股东权益 × 100%"""
    # 从 data 中提取 net_profit 和 shareholders_equity
    ...
    return {"value": ..., "formula": "净利润 / 股东权益", "unit": "%"}


def _calc_gross_margin(data: dict) -> dict:
    """毛利率 = (营业收入 - 营业成本) / 营业收入 × 100%"""
    ...


def _calc_net_margin(data: dict) -> dict:
    """净利率 = 净利润 / 营业收入 × 100%"""
    ...


def _calc_debt_ratio(data: dict) -> dict:
    """资产负债率 = 总负债 / 总资产 × 100%"""
    ...


def _calc_current_ratio(data: dict) -> dict:
    """流动比率 = 流动资产 / 流动负债"""
    ...


def _calc_dupont(data: dict) -> dict:
    """杜邦分析：ROE = 净利率 × 资产周转率 × 权益乘数"""
    ...


def _calc_yoy_growth(data: dict) -> dict:
    """同比增长率"""
    ...
```

### 1.3 注册工具到 config.yaml

在 `config.yaml` 的 `tools` 段添加：

```yaml
tools:
  # ... 已有工具 ...

  - name: financial_data
    group: financial
    use: deerflow.community.financial.tools:financial_data_tool
    max_results: 20

  - name: stock_info
    group: financial
    use: deerflow.community.financial.tools:stock_info_tool

  - name: financial_metrics
    group: financial
    use: deerflow.community.financial.tools:financial_metrics_tool
```

同时在 `tool_groups` 中添加 `financial` 组，确保 Agent 能加载这些工具：

```yaml
tool_groups:
  - name: sandbox
  - name: web
  - name: financial   # ← 新增
```

### 1.4 Phase 1 验证清单

- [ ] `from deerflow.community.financial.provider import CompositeProvider` 无报错
- [ ] `CompositeProvider()._classify("600519")` → `market="a_share"`
- [ ] `CompositeProvider()._classify("HK.00700")` → `market="hk_share"`
- [ ] `CompositeProvider()._classify("AAPL")` → `market="us_share"`
- [ ] `CompositeProvider().get_stock_info("600519")` 返回有效的 JSON
- [ ] 启动 Gateway 后，`GET /api/models` 可以看到 financial 组的 3 个工具

---

## 第二阶段：Skill 层 — 财报分析 Skill

> **目标：** 编写 `SKILL.md` 教会 Agent 如何一步步完成财报分析。
>
> **新建文件：** 7 个

### 2.1 核心 SKILL.md

**文件：** `skills/custom/financial-report-analysis/SKILL.md`

这是整个二次开发最核心的文件，约 300 行。下面展示完整结构和关键段落：

```markdown
---
name: financial-report-analysis
description: >-
  财报分析技能。当用户的问题涉及上市公司财报时触发此技能：
  - 询问某公司的营收、利润、毛利率、净利率、ROE、负债率等财务指标
  - 对比多家公司的财务表现（如"茅台和五粮液谁更赚钱"）
  - 分析财报变化趋势（同比、环比、季度变化）
  - 杜邦分析、现金流质量分析、估值分析
  - 任何涉及"财报""年报""季报""利润表""资产负债表""现金流量表"
    "财务数据""业绩"等词汇的问题
  - 用户上传了 PDF/Excel 财报文件并希望分析
---

# 财报分析

## Overview

此技能提供专业的三地（A股/港股/美股）上市公司财报分析能力。
覆盖盈利能力、成长性、财务健康度、估值、现金流质量等分析维度。
自动获取数据、计算指标、生成图表，最终输出结构化分析报告。

## When to Use

**必须使用此技能的触发条件（覆盖所有可能场景）：**

### 财务数据/指标类
- 用户询问任何财务指标的具体数值或变化
- "XX公司赚钱能力怎么样"、"毛利率如何"、"ROE下降了吗"
- "营收"、"净利润"、"净利率"、"负债率"、"现金流"

### 财报本体类
- 用户提到"财报"、"年报"、"季报"、"中报"、"业绩"
- 用户询问"利润表"、"资产负债表"、"现金流量表"
- "分析一下XX的财务情况"

### 对比类
- 多家公司财务对比：谁更好/更差、差距在哪
- 同行对比排名

### 趋势类
- 财务指标的时间序列变化
- "最近几年"、"一直以来"、"逐年"的趋势分析

> **重要：如果你不确定是否应该使用此技能，就使用它。**
> 宁可多用，不可漏用。财报相关问题如果不使用此技能，
> 你将没有数据来源，只能给出空洞的泛泛之谈。

## 核心方法论：5 阶段分析工作流

### Phase 1: 需求理解

**目标：** 在拉取任何数据之前，先明确用户真正想知道什么。

**步骤：**
1. 识别涉及的上市公司及其股票代码
   - 如果用户只说了公司名（如"茅台"），先用 `web_search` 确认代码
   - 代码格式：A股6位数字、港股加 HK. 前缀、美股用字母代码
2. 识别时间范围（最新季报？2024年报？近5年？）
3. 识别用户关心的核心指标和维度
4. 确认输出要求（纯文本？图表？Excel？）

**输出：** 在回复中简要确认分析计划，给用户一个预期。

### Phase 2: 数据获取

**目标：** 用工具获取所有需要的结构化数据和非结构化背景信息。

> **推荐：** 将此阶段委派给 `financial-data-fetcher` 子代理（如果可用）。
> 子代理会专注于数据获取，不会被分析思路干扰。

**步骤（自行执行时）：**
1. 对每家公司调用 `stock_info` 确认代码和基本信息
2. 调用 `financial_data` 获取三张表（report_type="all", period=目标期间）
3. 如果有趋势分析需求，再获取历史数据
4. 调用 `web_search` 补充搜索：
   - 公司最新公告（可能有重大事项影响财报）
   - 行业动态（行业整体景气度）
   - 券商研报观点（作为参考，不是分析依据）
5. 将获取的原始数据写入 workspace：
   ```
   /mnt/user-data/workspace/financials/{stock_code}_{period}.json
   ```

**检查清单：**
- [ ] 所有目标公司的基本信息已获取
- [ ] 所有目标期间的三张表数据已获取
- [ ] 已搜索最新公告和新闻

### Phase 3: 分析计算

**目标：** 用 `financial_metrics` 工具执行确定性计算，然后基于数据做定性分析。

> **推荐：** 将此阶段委派给 `financial-analyst` 子代理（如果可用）。

**步骤：**
1. 调用 `financial_metrics` 计算各项指标（传入 Phase 2 获取的 JSON 数据）
2. 读取 `references/metrics.md` 了解各指标的合理范围和解读方法
3. 如果是跨市场对比，读取 `references/accounting.md` 注意准则差异
4. 执行分析：
   - 盈利能力：ROE 拆解（杜邦分析）、毛利率趋势、费用率
   - 成长性：营收/利润 CAGR、同比环比
   - 财务健康度：负债结构、偿债能力、现金流质量
   - 估值：PE/PB 历史分位（如果获取了历史估值数据）
5. 对照行业基准判断公司所处水平

**分析框架速查：**

| 分析目的 | 推荐框架 | 关键指标 |
|---------|---------|---------|
| 盈利质量 | 杜邦分析 | ROE、净利率、周转率、杠杆 |
| 成长性 | 收入拆解 | 营收CAGR、量价拆解 |
| 财务风险 | Altman Z-score | 流动比率、负债率、利息覆盖 |
| 现金流 | 现金流质量 | OCF/NI比、FCF Yield |
| 同业对比 | 雷达图/矩阵 | 多维度指标排名 |

### Phase 4: 可视化

**目标：** 为关键发现生成图表。

> **委托给 `chart-visualization` skill。** 不要自己写图表代码。

**常用图表类型：**
- ROE 对比 → 柱状图（读取 `references/generate_bar_chart.md`）
- 趋势变化 → 折线图（读取 `references/generate_line_chart.md`）
- 杜邦拆解 → 瀑布图/堆叠柱状图

### Phase 5: 报告合成

**目标：** 将分析结果组织为专业报告。

> **推荐：** 将此阶段委派给 `report-generator` 子代理（如果可用）。

**报告结构（参照 `templates/report_template.md`）：**
1. 执行摘要（300字以内）
2. 公司概览
3. 财务表现分析（按三张表展开）
4. 关键指标解读
5. 风险提示
6. 总结

**如需 Excel 导出：**
```bash
python /mnt/skills/custom/financial-report-analysis/scripts/export_report.py \
  --analysis-file /mnt/user-data/workspace/analysis.json \
  --metrics-file /mnt/user-data/workspace/metrics.json \
  --output /mnt/user-data/outputs/report.xlsx
```

## 质量检查清单

在完成分析之前，逐项检查：
- [ ] 所有金额已标注单位（元/万元/亿元）
- [ ] 同比/环比数据已注明基期
- [ ] 对比分析时已考虑会计准则差异
- [ ] 已标注数据来源和数据截止日期
- [ ] 异常数据已识别并说明可能原因
- [ ] 不确定的结论已明确标注

## 完整示例

### 场景：对比茅台和五粮液的2024年报

**用户输入：** "帮我分析茅台和五粮液的2024年年报，ROE有没有下降？谁更值得投资？"

**Phase 1 →** 识别：茅台(600519)、五粮液(000858)，2024年报，关注ROE趋势和综合对比

**Phase 2 →** 数据获取：
```bash
# Agent 内部调用，用户不可见
financial_data("600519", "all", "2024")
financial_data("000858", "all", "2024")
stock_info("600519")
stock_info("000858")
web_search("茅台 2024年报")
web_search("五粮液 2024年报")
```

**Phase 3 →** 分析计算：
```bash
python calculate.py --data-file financials/600519_2024.json \
  --metrics "roe,dupont,gross_margin,yoy_growth"
python calculate.py --data-file financials/000858_2024.json \
  --metrics "roe,dupont,gross_margin,yoy_growth"
```

**Phase 4 →** 生成 ROE 对比柱状图

**Phase 5 →** 输出报告：
```
📊 茅台 vs 五粮液 2024年报分析

一、执行摘要
2024年茅台ROE为29.8%（↓3.2ppt），五粮液ROE为22.5%（↓2.1ppt）。
两家ROE均有所下滑，主为净利率收窄，但茅台仍显著领先。
...

二、盈利能力对比
（附ROE对比柱状图）
茅台 ROE：29.8%  五粮液 ROE：22.5%
杜邦拆解显示茅台的高ROE主要来自更高的净利率（51.5% vs 38.2%）...

三、风险提示
- 白酒行业整体增速放缓
- 茅台批发价下行压力
...

四、结论
从ROE和增长质量角度，茅台仍优于五粮液，但二者差距在收窄。
```

---

> ⚠️ **重要提醒：**
> - 所有分析结论必须基于实际获取的数据，绝不编造数据
> - 涉及投资建议时，必须附加风险提示
> - 数据源限制（如 akshare 偶尔不可用）必须告知用户
```

### 2.2 计算脚本

**文件：** `skills/custom/financial-report-analysis/scripts/calculate.py`

仿照 `data-analysis/scripts/analyze.py` 模式，提供 CLI 接口：

```python
#!/usr/bin/env python3
"""
财务指标计算脚本。

用法:
    python calculate.py --data-file /path/to/financials.json \
        --metrics "roe,gross_margin,dupont" \
        --output /path/to/metrics.json

支持指标: roe, gross_margin, net_margin, debt_ratio, current_ratio,
          dupont, fcf_yield, yoy_growth, cagr, all
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="财务指标计算工具")
    parser.add_argument("--data-file", required=True, help="financial_data 工具输出的 JSON 文件")
    parser.add_argument("--metrics", default="all", help="要计算的指标，逗号分隔")
    parser.add_argument("--output", default=None, help="输出 JSON 文件路径（默认输出到 stdout）")
    args = parser.parse_args()

    # 读取输入数据
    data = json.loads(Path(args.data_file).read_text())

    # 计算指标（复用 tools.py 中的纯函数）
    metric_list = args.metrics.split(",") if args.metrics != "all" else [
        "roe", "gross_margin", "net_margin", "debt_ratio",
        "current_ratio", "dupont", "yoy_growth"
    ]

    results = {"_meta": {"source_file": args.data_file, "metrics": metric_list}}
    for metric in metric_list:
        # 此处直接内联或 import 计算逻辑
        # results[metric] = calc_function(data)
        ...

    output_json = json.dumps(results, indent=2, ensure_ascii=False, default=str)
    if args.output:
        Path(args.output).write_text(output_json)
        print(f"结果已写入 {args.output}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
```

### 2.3 Excel 报告导出脚本

**文件：** `skills/custom/financial-report-analysis/scripts/export_report.py`

```python
#!/usr/bin/env python3
"""
财报分析 Excel 报告生成脚本。

用法:
    python export_report.py --analysis-file analysis.json \
        --metrics-file metrics.json \
        --output report.xlsx

生成 3 个 sheet:
  1. 分析摘要 — 文本结论
  2. 财务指标 — 结构化指标数据
  3. 原始数据 — 财务数据明细
"""

import argparse
import json
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side


def create_report(analysis_file: str, metrics_file: str, output: str):
    wb = openpyxl.Workbook()

    # ─── Sheet 1: 分析摘要 ───
    ws1 = wb.active
    ws1.title = "分析摘要"
    analysis = json.loads(Path(analysis_file).read_text())
    _write_summary_sheet(ws1, analysis)

    # ─── Sheet 2: 财务指标 ───
    ws2 = wb.create_sheet("财务指标")
    metrics = json.loads(Path(metrics_file).read_text())
    _write_metrics_sheet(ws2, metrics)

    # ─── Sheet 3: 原始数据 ───
    ws3 = wb.create_sheet("原始数据")
    _write_raw_data_sheet(ws3, analysis, metrics)

    wb.save(output)
    print(f"报告已生成：{output}")


def _write_summary_sheet(ws, analysis):
    """写入分析摘要 sheet"""
    # 设置表头样式
    header_font = Font(bold=True, size=14)
    ws["A1"] = "财报分析报告"
    ws["A1"].font = header_font
    # ... 更多格式化逻辑


def _write_metrics_sheet(ws, metrics):
    """写入财务指标 sheet"""
    headers = ["指标名称", "当前值", "公式", "参考范围", "解读"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
    # ... 填入数据


def _write_raw_data_sheet(ws, analysis, metrics):
    """写入原始数据 sheet"""
    ...


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="财报分析 Excel 报告生成工具")
    parser.add_argument("--analysis-file", required=True)
    parser.add_argument("--metrics-file", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    create_report(args.analysis_file, args.metrics_file, args.output)
```

### 2.4 参考资料文件

#### `references/metrics.md` — 财务指标参考手册

```markdown
# 财务指标参考手册

## 盈利能力指标

### ROE（净资产收益率）
- **公式：** 净利润 / 平均股东权益 × 100%
- **含义：** 衡量股东投入资本的回报效率
- **合理范围：**
  - 一般制造业：8%–15%
  - 消费品牌：15%–30%
  - 金融行业：10%–18%
  - 优秀公司通常连续 5 年以上 ROE > 15%
- **杜邦拆解：** ROE = 净利率 × 资产周转率 × 权益乘数
  - 净利率高 → 品牌/技术优势
  - 周转率高 → 运营效率
  - 杠杆高 → 财务风险（需重点关注）

### 毛利率（Gross Margin）
- **公式：** (营业收入 - 营业成本) / 营业收入 × 100%
- **合理范围：**
  - 制造业：15%–35%
  - 消费品品牌：40%–70%
  - 白酒行业：60%–90%
  - SaaS/软件：70%–90%
- **解读要点：**
  - 毛利率持续下降 → 竞争加剧或成本上升
  - 毛利率显著高于同行 → 品牌溢价或技术壁垒

...（其余指标省略，实际应覆盖全部常用指标）
```

#### `references/accounting.md` — 三地会计准则差异

```markdown
# 中港美三地会计准则差异要点

## 收入确认

| 准则 | 核心原则 | 关键差异 |
|------|---------|---------|
| CAS（中国企业会计准则） | 五步法（与 IFRS 15 趋同） | 部分行业有特殊指引 |
| IFRS（香港财务报告准则） | IFRS 15 五步法 | 控制权转移为核心 |
| US GAAP（美国公认会计准则） | ASC 606 五步法 | 部分细节判断标准不同 |

## 资产计量

| 科目 | CAS | IFRS | US GAAP |
|------|-----|------|---------|
| 固定资产 | 历史成本为主 | 允许重估价模式 | 历史成本 |
| 投资性房地产 | 成本模式为主 | 公允价值可选 | 历史成本 |
| 存货 | 成本与可变现净值孰低 | 同 CAS | 成本与市价孰低（更严格） |

## 对分析的影响

- **跨市场对比 ROE 时**：需关注资产计量基础差异
- **港股房地产公司**：若采用公允价值模式，净资产可能被高估
- **美股科技公司**：研发费用全部费用化（CAS 允许有条件资本化）
```

#### `references/frameworks.md` — 分析框架详解

```markdown
# 财报分析框架

## 1. 杜邦分析体系

### 三因子模型
ROE = 净利率 × 资产周转率 × 权益乘数

### 五因子模型（进阶）
ROE = 税负因子 × 利息负担因子 × 经营利润率 × 资产周转率 × 权益乘数

### 解读方法
- 逐年对比各因子的变化，锁定 ROE 变动的主导因素
- 和同行业公司对比，看差异来自哪个因子
- 警惕高杠杆拉动的 ROE（权益乘数 > 3 时需关注风险）

## 2. 现金流分析框架

### 核心指标
- **经营现金流/净利润比（OCF/NI）**
  - > 1：利润质量高，现金回收好
  - < 0.5：利润可能"虚"，需关注应收账款和存货
  - 长期 < 0：经营不可持续

### 自由现金流（FCF）
- FCF = 经营现金流 - 资本支出
- FCF Yield = FCF / 市值
- 持续正 FCF 是"现金牛"的核心特征

## 3. 成长性分析框架

### CAGR（复合年增长率）
CAGR = (终值/初值)^(1/n) - 1

### 增长质量判断
- 营收增长 > 行业平均 → 抢占份额
- 利润增长 > 营收增长 → 规模效应/成本优化
- 经营现金流增长 > 利润增长 → 真正的现金增长

## 4. 同业对比框架

### 步骤
1. 选择 3-5 家可比公司（同行业、相近市值）
2. 取同样的时间窗口
3. 比较核心指标：ROE、毛利率、净利率、负债率、营收增速
4. 标注异常值和需要解释的部分
```

#### `templates/report_template.md`

```markdown
# 财报分析报告

## {{公司名称}} — {{报告期}} 财报分析

---

### 一、执行摘要

（300 字以内，核心结论 + 3-5 个关键数据）

### 二、公司概览

- **所属行业：** {{行业}}
- **市值：** {{市值}}
- **报告期营收：** {{营收}}
- **报告期净利润：** {{净利润}}
- **当前估值：** PE {{pe}} / PB {{pb}}

### 三、财务表现分析

#### 3.1 利润表分析

| 项目 | 本期 | 上期 | 同比变化 |
|------|------|------|---------|
| 营业收入 | | | |
| 营业成本 | | | |
| 毛利率 | | | |
| 净利润 | | | |
| 净利率 | | | |

**关键发现：**
- {{发现1}}
- {{发现2}}

#### 3.2 资产负债表分析

...

#### 3.3 现金流量表分析

...

### 四、关键指标解读

- **ROE：** {{ROE}} — {{解读}}
- **杜邦拆解：**
  - 净利率：{{}}
  - 资产周转率：{{}}
  - 权益乘数：{{}}

### 五、风险提示

1. {{风险1}}
2. {{风险2}}

### 六、总结与展望

{{总结}} — {{展望}}
```

---

## 第三阶段：子代理 — 专项任务委派

> **目标：** 配置 3 个自定义子代理，实现关注点分离，让复杂分析可以委派执行。

### 3.1 配置子代理

在 `config.yaml` 中添加：

```yaml
subagents:
  # 全局默认（可选）
  timeout_seconds: 1800
  max_turns: null

  # 自定义子代理
  custom_agents:

    # ─── 子代理 1: 数据获取 ───
    financial-data-fetcher:
      description: "专门获取财务数据的子代理。调用 financial_data 和 web_search 获取财报、公告和新闻。只做数据获取，不进行分析。"
      system_prompt: |
        你是财务数据获取专家。你的唯一任务是获取指定的财务数据。

        工作流程：
        1. 识别输入的股票代码和市场
        2. 调用 financial_data 获取结构化财报数据（资产负债表、利润表、现金流量表）
        3. 调用 stock_info 获取股票基本信息
        4. 调用 web_search 搜索相关公告、新闻和行业动态
        5. 将所有获取的数据整理到 /mnt/user-data/workspace/financials/ 目录
        6. 返回数据文件路径列表和内容摘要

        输出格式：
        ```
        数据获取完成：
        - 600519_2024_annual.json（2024年报三张表）
        - 000858_2024_annual.json（2024年报三张表）
        - news_context.md（相关新闻和公告摘要）
        ```

        **禁止进行分析或给出投资建议。** 只做数据获取和整理。
        如果某个数据源暂时不可用，在返回值中注明，不要尝试从其他渠道推测数据。
      tools:
        - financial_data
        - stock_info
        - web_search
        - web_fetch
        - bash
        - read_file
        - write_file
      disallowed_tools:
        - task
        - ask_clarification
      max_turns: 60
      timeout_seconds: 600

    # ─── 子代理 2: 深度分析 ───
    financial-analyst:
      description: "深度财务分析子代理，基于已获取的财报数据执行杜邦分析、现金流分析、估值计算和趋势分析。"
      system_prompt: |
        你是专业的财务分析师。基于已获取的财报数据，执行深度分析。

        分析能力：
        1. 杜邦分析：将 ROE 拆解为净利率 × 资产周转率 × 权益乘数
        2. 现金流质量：经营现金流/净利润比、自由现金流分析
        3. 成长性：营收/利润的同比/环比增长、CAGR
        4. 估值分析：PE/PB/PS/FCF Yield 历史对比
        5. 风险识别：异常科目变动、应收账款质量、存货周转、商誉减值风险

        分析工作流：
        1. 读取 workspace 中的原始财报数据 JSON 文件
        2. 调用 financial_metrics 工具计算所有相关指标
           ```bash
           python /mnt/skills/custom/financial-report-analysis/scripts/calculate.py \
             --data-file /mnt/user-data/workspace/financials/{stock}_{period}.json \
             --metrics all \
             --output /mnt/user-data/workspace/metrics_{stock}_{period}.json
           ```
        3. 对照行业基准值判断公司所处水平
        4. 识别异常和风险信号
        5. 输出结构化的分析结果

        输出格式：JSON + 文本摘要
        ```json
        {
          "company": "公司名",
          "period": "报告期",
          "metrics": {...},
          "highlights": ["发现1", "发现2"],
          "risks": ["风险1"],
          "raw_data_source": "数据文件路径"
        }
        ```

        **始终标注数据来源。不确定的地方明确说明。不要编造数据。**
      tools:
        - financial_metrics
        - bash
        - read_file
        - write_file
      disallowed_tools:
        - task
        - ask_clarification
        - financial_data
        - web_search
        - web_fetch
      max_turns: 100
      timeout_seconds: 900

    # ─── 子代理 3: 报告生成 ───
    report-generator:
      description: "报告生成子代理，将分析结果合成为结构化的财报分析报告，支持生成图表和 Excel 导出。"
      system_prompt: |
        你是财务报告撰写专家。基于分析数据生成专业的财报分析报告。

        报告输出能力：
        1. 结构化文本报告（Markdown 格式）
        2. 图表可视化（委托 chart-visualization skill）
        3. Excel 数据报告（调用 export_report.py 脚本）

        报告结构（参照 SKILL.md 中的模板）：
        1. 执行摘要（300字以内，核心结论+关键数据）
        2. 公司概览（商业模式、行业地位、市值规模）
        3. 财务表现分析（按利润表、资产负债表、现金流量表展开）
        4. 关键指标解读（ROE、毛利率趋势、现金流质量、杜邦拆解等）
        5. 风险提示
        6. 总结与展望

        可视化流程：
        1. 确定需要可视化的指标（如 ROE 对比、趋势变化）
        2. 读取 chart-visualization skill 的对应 reference 文件
        3. 调用 chart-visualization 的 generate.js 脚本生成图表
        4. 将图表 URL 嵌入报告

        Excel 导出：
        ```bash
        python /mnt/skills/custom/financial-report-analysis/scripts/export_report.py \
          --analysis-file /mnt/user-data/workspace/analysis.json \
          --metrics-file /mnt/user-data/workspace/metrics.json \
          --output /mnt/user-data/outputs/report.xlsx
        ```
        生成的 Excel 包含 3 个 sheet：分析摘要、财务指标、原始数据。

        风格要求：
        - 专业但不卖弄术语
        - 重要数据用粗体
        - 用 🟢🟡🔴 标注风险等级
        - 所有金额标注单位
      tools:
        - bash
        - read_file
        - write_file
      disallowed_tools:
        - task
        - ask_clarification
      skills:
        - chart-visualization
        - financial-report-analysis
      max_turns: 80
      timeout_seconds: 600
```

### 3.2 子代理之间的协作关系

```
主 Agent（财务分析师 SOUL）
  │
  │  "帮我分析茅台的2024年报"
  │
  ├─→ task(subagent_type="financial-data-fetcher", prompt="获取600519 2024年报三张表数据")
  │      │
  │      └─→ 返回: {数据文件路径列表}
  │
  ├─→ task(subagent_type="financial-analyst", prompt="分析600519的2024年财报，关注ROE趋势")
  │      │
  │      └─→ 返回: {指标计算结果 + 分析发现}
  │
  └─→ task(subagent_type="report-generator", prompt="基于以上分析生成报告+图表+Excel")
         │
         └─→ 返回: 文本报告 + 图表 URL + Excel 下载链接
```

---

## 第四阶段：Agent 身份 — SOUL.md + 记忆播种

> **目标：** 定义 Agent 的人设、行为准则和初始领域知识。

### 4.1 创建 Agent 配置文件

**文件：** `backend/.deer-flow/users/{user_id}/agents/financial-analyst/config.yaml`

```yaml
name: financial-analyst
description: 专业财报分析助手，覆盖A股/港股/美股上市公司财报
model: inherit
skills:
  - financial-report-analysis
  - chart-visualization
  - deep-research
tool_groups:
  - sandbox
  - web
  - financial
```

也可以通过 DeerFlow 的 `/bootstrap` 命令交互式创建：
```
/bootstrap → "我是财务分析师" → 按引导回答 → 自动生成 SOUL.md 和 config.yaml
```

### 4.2 编写 SOUL.md

**文件：** `backend/.deer-flow/users/{user_id}/agents/financial-analyst/SOUL.md`

```markdown
# Identity

你是专业的财务分析师，专注于中国A股、港股和美股的上市公司财报分析。
你服务投资研究团队和独立投资者，他们需要清晰、准确、基于数据的财务分析。
你的价值在于快速从财报数据中提取洞察，识别异常和风险，而不是简单复述数据。

# Core Traits

1. **数据驱动** — 所有结论基于实际财报数据，而非主观判断或市场情绪
2. **主动标注局限性** — 明确指出数据来源、会计准则差异、数据时效性等限制
3. **定量先于定性** — 先给出数据，再做解读。不先入为主
4. **异常敏感** — 主动识别和提示异常数据、科目变动和潜在风险信号
5. **诚实透明** — 数据不足或不确定时明确告知，绝不编造数据
6. **对比思维** — 分析一家公司时，主动考虑和同行/历史对比

# Communication

- 专业但不卖弄术语。首次出现的财务术语提供简洁注释（括号中文说明）
- 默认使用中文沟通，但保留关键财务术语的英文（如 ROE、EBITDA、FCF、CAGR）
- 重要结论和数据用**粗体**强调
- 金额使用易读单位（万元、亿元），并标注原始单位
- 风险等级用视觉化标记：🟢 低风险 🟡 关注 🔴 高风险

# Domain Expertise

你熟练掌握以下领域的专业知识：

**会计准则：**
- 中国会计准则（CAS）与 IFRS 趋同的要点
- 香港财务报告准则（HKFRS / IFRS）
- 美国公认会计准则（US GAAP）与 IFRS 的核心差异
- 三地准则差异对 ROE、资产计量、收入确认的影响

**分析框架：**
- 杜邦分析（三因子 + 五因子拆解）
- 自由现金流折现估值逻辑
- Altman Z-score 财务风险预警
- Porter 五力行业分析

**核心关注指标：**
- 盈利能力：ROE、毛利率、净利率、EBITDA 率
- 成长性：营收/利润 CAGR、YoY/QoQ 增长
- 现金流质量：OCF/NI 比、FCF Yield
- 资产效率：资产周转率、存货周转天数、应收周转天数
- 财务健康度：资产负债率、流动比率、利息覆盖倍数

# Growth

你通过每次对话了解用户的偏好：
- 更关注盈利能力还是成长性？
- 偏好深度分析还是快速摘要？
- 关注哪些特定行业或公司？

将这些偏好记录到记忆中，逐步成为一个更懂用户的专属分析师。

# Lessons Learned

- （此区域由 Agent 自动更新，记录纠正过的错误）
```

### 4.3 播种领域记忆

**文件：** `backend/.deer-flow/users/{user_id}/memory.json`

在 memory.json 的 `facts` 数组中添加以下领域知识。系统会自动将这些知识注入到 Agent 的上下文窗口中。

```json
{
  "facts": [
    {
      "id": "fa-domain-001",
      "content": "用户偏好先看盈利能力指标（ROE、毛利率），再叠加成长性和风险指标",
      "category": "preference",
      "confidence": 0.85,
      "createdAt": "2026-01-01T00:00:00Z"
    },
    {
      "id": "fa-domain-002",
      "content": "一般制造业毛利率15%-35%为正常区间，消费品牌30%-60%为优秀，白酒行业60%-90%",
      "category": "knowledge",
      "confidence": 0.85,
      "createdAt": "2026-01-01T00:00:00Z"
    },
    {
      "id": "fa-domain-003",
      "content": "A股财报会计期间与自然年一致，年报截止日为12月31日，季报分为一季报（3月31日）、半年报（6月30日）、三季报（9月30日）",
      "category": "knowledge",
      "confidence": 0.95,
      "createdAt": "2026-01-01T00:00:00Z"
    },
    {
      "id": "fa-domain-004",
      "content": "港股财年截止日由公司自定，常见的有3月31日（如腾讯、友邦）和12月31日（如中移动），分析时需先确认公司具体财年",
      "category": "knowledge",
      "confidence": 0.95,
      "createdAt": "2026-01-01T00:00:00Z"
    },
    {
      "id": "fa-domain-005",
      "content": "美股财年(Fiscal Year)不等于自然年，如Apple的FY2024截止于2024年9月28日，需查10-K确认",
      "category": "knowledge",
      "confidence": 0.95,
      "createdAt": "2026-01-01T00:00:00Z"
    },
    {
      "id": "fa-domain-006",
      "content": "ROE连续5年以上>15%是高质量公司的基本特征，但需拆分是高净利率、高周转还是高杠杆驱动",
      "category": "knowledge",
      "confidence": 0.90,
      "createdAt": "2026-01-01T00:00:00Z"
    },
    {
      "id": "fa-domain-007",
      "content": "经营活动现金流/净利润比长期<0.5是利润质量差的危险信号，需重点关注应收账款和存货周转",
      "category": "knowledge",
      "confidence": 0.90,
      "createdAt": "2026-01-01T00:00:00Z"
    },
    {
      "id": "fa-domain-008",
      "content": "用户每次分析结束后希望得到3-5条核心结论的要点摘要（TL;DR格式）",
      "category": "preference",
      "confidence": 0.80,
      "createdAt": "2026-01-01T00:00:00Z"
    }
  ]
}
```

也可以通过 Agent 对话自然积累：
```
用户："记住，我喜欢先看ROE，然后看现金流质量"
Agent：→ 自动提取为 memory fact
```

---

## 第五阶段：配置汇总 & 集成联调

> **目标：** 整合所有组件，确保端到端可运行。

### 5.1 完整配置清单

#### `config.yaml` — 应包含的全部新增内容

```yaml
# ===== 工具注册 =====
tools:
  - name: financial_data
    group: financial
    use: deerflow.community.financial.tools:financial_data_tool
    max_results: 20

  - name: stock_info
    group: financial
    use: deerflow.community.financial.tools:stock_info_tool

  - name: financial_metrics
    group: financial
    use: deerflow.community.financial.tools:financial_metrics_tool

# ===== 工具组 =====
tool_groups:
  - name: sandbox
  - name: web
  - name: financial

# ===== 子代理配置 =====
subagents:
  custom_agents:
    financial-data-fetcher:
      # ...（见第三阶段完整配置）
    financial-analyst:
      # ...（见第三阶段完整配置）
    report-generator:
      # ...（见第三阶段完整配置）

# ===== 记忆配置 =====
memory:
  enabled: true
  injection_enabled: true
  max_injection_tokens: 3000
  guaranteed_categories:
    - correction
    - knowledge
  max_facts: 150
  fact_confidence_threshold: 0.7

# ===== Skill 路径（已有，无需修改） =====
skills:
  container_path: /mnt/skills
```

#### `extensions_config.json` — Skill 启用

```json
{
  "skills": {
    "financial-report-analysis": {"enabled": true},
    "chart-visualization": {"enabled": true},
    "deep-research": {"enabled": true}
  }
}
```

### 5.2 依赖安装

在 `backend/pyproject.toml` 的 `[project.optional-dependencies]` 中添加：

```toml
[project.optional-dependencies]
financial = [
    "akshare>=1.14.0",
    "yfinance>=0.2.0",
    "openpyxl>=3.1.0",
]
```

安装命令：

```bash
cd backend

# 方式 1: 使用 optional extra
uv sync --extra financial

# 方式 2: 直接 pip install
uv pip install akshare yfinance openpyxl
```

### 5.3 开发顺序建议

```
Week 1 ─ 第一阶段
  ├── Day 1-2: 实现 provider.py（CompositeProvider + 三个子类）
  ├── Day 3-4: 实现 tools.py（3 个 LangChain tool）
  └── Day 5:   注册到 config.yaml，验证工具可用性

Week 2 ─ 第二阶段
  ├── Day 1-2: 编写 SKILL.md 核心文档
  ├── Day 3:   编写 calculate.py 计算脚本
  ├── Day 4:   编写 references/ 参考文档
  └── Day 5:   编写 export_report.py + templates/

Week 3 ─ 第二+三阶段
  ├── Day 1-2: 在实际对话中测试 Skill
  ├── Day 3:   迭代优化 SKILL.md（根据测试反馈）
  ├── Day 4:   配置 3 个子代理到 config.yaml
  └── Day 5:   测试子代理委派流程

Week 4 ─ 第四+五阶段
  ├── Day 1-2: 编写 SOUL.md + 播种 memory.json
  ├── Day 3:   端到端集成测试
  ├── Day 4:   修复问题 + 文档完善
  └── Day 5:   性能优化 + 写测试
```

### 5.4 启动验证

```bash
# 1. 确保所有文件在正确位置
ls skills/custom/financial-report-analysis/SKILL.md
ls backend/packages/harness/deerflow/community/financial/tools.py

# 2. 启动 Gateway
cd backend && make dev

# 3. 验证工具注册
curl http://localhost:8001/api/models | jq '.models[] | select(.name | startswith("financial"))'

# 4. 在 Chat UI 中测试（打开 http://localhost:2026）
# 输入："茅台2024年报的营收是多少？ROE是多少？"
```

---

# 验证方案

## 单元测试

### 1. Provider 层测试

```python
# tests/test_financial_provider.py

class TestCompositeProvider:
    def test_classify_a_share(self):
        sid = CompositeProvider()._classify("600519")
        assert sid.market == "a_share"
        assert sid.normalized_code == "600519"

    def test_classify_hk_share(self):
        sid = CompositeProvider()._classify("HK.00700")
        assert sid.market == "hk_share"
        assert sid.normalized_code == "00700"

    def test_classify_us_share(self):
        sid = CompositeProvider()._classify("AAPL")
        assert sid.market == "us_share"

    def test_classify_invalid(self):
        with pytest.raises(ValueError):
            CompositeProvider()._classify("invalid_code!")

    @pytest.mark.integration
    def test_get_stock_info_a_share(self):
        """需要网络连接"""
        result = CompositeProvider().get_stock_info("600519")
        assert "stock_name" in result
        assert "market_cap" in result
```

### 2. Tools 层测试

```python
# tests/test_financial_tools.py

class TestFinancialTools:
    def test_financial_data_tool_invalid_code(self):
        result = financial_data_tool("INVALID", "all", "latest")
        data = json.loads(result)
        assert "error" in data

    def test_financial_metrics_tool_roe(self):
        """用已知数据验证 ROE 计算"""
        test_data = json.dumps({
            "income_statement": {
                "data": [
                    {"item": "净利润", "amount": 100000000},
                ]
            },
            "balance_sheet": {
                "data": [
                    {"item": "股东权益合计", "amount": 500000000},
                ]
            }
        })
        result = financial_metrics_tool(test_data, "roe")
        data = json.loads(result)
        # ROE = 1亿 / 5亿 = 20%
        assert "roe" in data
        # 验证结果接近 20%
```

### 3. Skill 加载测试

```bash
# 验证 SKILL.md 格式正确，能被 DeerFlow 解析
cd backend
PYTHONPATH=. uv run python -c "
from deerflow.skills.parser import parse_skill_file
from pathlib import Path
skill = parse_skill_file(
    Path('../skills/custom/financial-report-analysis/SKILL.md'),
    'custom',
    Path('financial-report-analysis')
)
print(f'Skill: {skill.name}')
print(f'Description: {skill.description}')
"
```

## 集成测试

### 1. 端到端场景测试

```bash
# 场景 1: 单一公司财报查询
curl -X POST http://localhost:8001/api/runs/wait \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "financial-analyst",
    "input": "茅台2024年报的ROE和毛利率是多少？",
    "config": {"recursion_limit": 50}
  }'

# 场景 2: 多公司对比
# input: "对比茅台和五粮液2024年的毛利率和净利率，谁更优秀？"

# 场景 3: 跨市场分析
# input: "对比茅台(A股)、腾讯(港股)、Apple(美股)的现金流情况"

# 场景 4: 趋势分析
# input: "茅台过去5年的ROE变化趋势如何？分析原因"

# 场景 5: Excel 导出
# input: "分析完毕，请导出Excel报告"
```

### 2. Skill 触发测试

用以下关键词测试 skill 是否正确激活（在运行日志中能看到 skill 加载记录）：

| 关键词 | 期望行为 |
|--------|---------|
| "财报" | ✅ 触发 financial-report-analysis |
| "ROE" | ✅ 触发 |
| "毛利率" | ✅ 触发 |
| "年报" | ✅ 触发 |
| "利润表" | ✅ 触发 |
| "今天天气" | ❌ 不触发 |
| "写代码" | ❌ 不触发 |

### 3. 子代理委派测试

在对话中要求一个需要多步骤的任务（如"分析茅台2024年报并生成图表"），观察：

- [ ] `task_started` 事件已正确触发
- [ ] `financial-data-fetcher` 被调用（子代理 run log 确认）
- [ ] `financial-analyst` 接收到 data-fetcher 的输出
- [ ] `report-generator` 生成最终报告
- [ ] 图表 URL 可访问
- [ ] Excel 文件生成且 3 个 sheet 内容正确

## 性能基准

| 场景 | 预期时间 | 主要耗时环节 |
|------|---------|-------------|
| 单公司单期报 | 15-40s | akshare API 调用（~10s/次） |
| 双公司对比 | 30-60s | 两次数据获取 + 两次分析 |
| 趋势分析（5年） | 40-80s | 多次历史数据获取 |
| 含图表+Excel | 60-120s | 图表生成 + Excel 导出 |

> 💡 **优化建议：** 如果数据源响应慢，考虑在 `provider.py` 中增加本地缓存层（如 `diskcache`），同一财报周期内缓存 akshare 的返回结果。

---

# 常见问题 FAQ

### Q1: akshare 接口不稳定怎么办？

1. akshare 依赖东方财富/新浪等公开接口，可能因反爬或接口变更不可用
2. 短期：增加重试逻辑（3次，指数退避）
3. 长期：对接商业数据源（Tushare Pro、Wind 等），通过切换 `provider.py` 中的实现类即可
4. Provider 抽象层已设计为可替换的（见第一阶段 1.1），更换数据源只需新写一个 Provider 子类

### Q2: 如何添加新的分析维度？

例如要添加 ESG 评分分析：
1. 在 `references/frameworks.md` 中添加 ESG 分析框架
2. 在 `SKILL.md` 的 Phase 3 中添加 ESG 分析步骤
3. 如果涉及新指标，在 `scripts/calculate.py` 中添加计算逻辑
4. 如果涉及新数据源，在 `provider.py` 中添加对应的 `get_esg_score()` 方法

### Q3: 分析结果不准确怎么办？

1. 检查 LLM 模型配置 — 建议使用 `claude-sonnet-5` 或 `deepseek-v4-pro` 级别的模型
2. 开启 `thinking_enabled: true` 增强推理能力
3. 在 `SKILL.md` 中添加更严格的检查清单
4. 让 `financial-analyst` 子代理输出中间推理步骤供人工审核

### Q4: 如何限制 Agent 的工具权限？

通过 Skill 的 `allowed-tools` frontmatter 字段：
```yaml
---
name: financial-report-analysis
allowed-tools: [financial_data, stock_info, financial_metrics, web_search, web_fetch, bash, read_file, write_file]
---
```
声明后，Agent 在此 Skill 激活时只能使用列出的工具。

### Q5: 生产环境需要注意什么？

1. **沙箱隔离** — 将 `sandbox.use` 从 `LocalSandboxProvider` 切换到 `AioSandboxProvider`（Docker 隔离）
2. **API 限流** — akshare 调用频率过高可能被封，增加调用间隔（2s+）
3. **数据缓存** — 财报数据不需要实时更新，增加本地缓存（如 SQLite/Redis）
4. **成本控制** — 给子代理设置严格的 `max_turns` 和 `timeout_seconds`
5. **监控** — 添加 `financial_data` 工具的调用成功率、响应时间监控

---

# 后续扩展方向

## 短期（1-2 个月）

- [ ] **接入更多数据源** — Tushare Pro（A股）、Alpha Vantage（美股）、Wind
- [ ] **PDF 财报解析** — 结合 DeerFlow 的文件上传功能，支持用户上传 PDF 财报自动解析
- [ ] **数据缓存层** — 用 akshare 作为数据源，但加本地 SQLite 缓存避免重复请求
- [ ] **增加行业基准数据** — 在 `references/industry-benchmarks.md` 中预置各行业基准值

## 中期（3-6 个月）

- [ ] **实时行情集成** — 在分析报告中加入实时股价和估值数据
- [ ] **定时巡检** — 利用 DeerFlow 的 scheduler 功能，定时检查关注列表的财报更新
- [ ] **知识图谱** — 构建产业链/供应链关系图谱，支持上下游联动分析
  - 例如：茅台毛利率下降 → 可能是高粱涨价 → 关联上游种植企业
- [ ] **多语言报告** — 中/英文报告自动切换

## 长期

- [ ] **预测模型** — 基于历史财报数据训练营收/利润预测模型
- [ ] **智能预警** — 自动识别财务异常信号（如营收增长但现金流恶化），主动提醒用户
- [ ] **竞品分析** — 自动识别同行业可比公司，生成竞争格局分析
- [ ] **事件驱动分析** — 重大事件（如证监会问询、业绩预告修正）自动触发深度分析

---

> 📚 **参考文档：**
> - [DeerFlow AGENTS.md](../AGENTS.md) — 框架总览
> - [backend/AGENTS.md](../backend/AGENTS.md) — 后端架构详解
> - [frontend/AGENTS.md](../frontend/AGENTS.md) — 前端架构详解
> - DeerFlow Skills 设计模式 — 参考 `skills/public/deep-research/SKILL.md` 和 `skills/public/data-analysis/SKILL.md`
> - DeerFlow 社区工具模式 — 参考 `backend/packages/harness/deerflow/community/tavily/tools.py`
