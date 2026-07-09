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