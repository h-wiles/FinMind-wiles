"""
DeerFlow 财务数据工具。

提供 3 个 LangChain tool：
- financial_data：获取上市公司财报数据
- stock_info：获取股票基本信息和实时估值指标
- financial_metrics：计算财务指标（确定性计算，不依赖 LLM）
"""

import json
import logging

from langchain.tools import tool

from deerflow.community.financial.provider import CompositeProvider

logger = logging.getLogger(__name__)

# 全局单例 provider（lazy init）
_provider: CompositeProvider | None = None


def _get_provider() -> CompositeProvider:
    global _provider
    if _provider is None:
        _provider = CompositeProvider()
    return _provider


# ═══════════════════════════════════════════════════════════════
# Tool 1: financial_data
# ═══════════════════════════════════════════════════════════════

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
            results: dict = {}
            for rt in ["income_statement", "balance_sheet", "cash_flow"]:
                results[rt] = provider.get_financial_report(stock_code, rt, period)
            return json.dumps(results, indent=2, ensure_ascii=False, default=str)
        return json.dumps(
            provider.get_financial_report(stock_code, report_type, period),
            indent=2, ensure_ascii=False, default=str,
        )
    except ValueError as e:
        return json.dumps({"error": str(e), "stock_code": stock_code}, ensure_ascii=False)
    except ImportError as e:
        return json.dumps({
            "error": f"依赖缺失: {e}。请安装: pip install akshare yfinance",
            "stock_code": stock_code,
        }, ensure_ascii=False)
    except Exception as e:
        logger.exception("financial_data_tool 异常")
        return json.dumps({
            "error": str(e),
            "stock_code": stock_code,
            "report_type": report_type,
            "period": period,
        }, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# Tool 2: stock_info
# ═══════════════════════════════════════════════════════════════

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
    except ValueError as e:
        return json.dumps({"error": str(e), "stock_code": stock_code}, ensure_ascii=False)
    except ImportError as e:
        return json.dumps({
            "error": f"依赖缺失: {e}",
            "stock_code": stock_code,
        }, ensure_ascii=False)
    except Exception as e:
        logger.exception("stock_info_tool 异常")
        return json.dumps({"error": str(e), "stock_code": stock_code}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# Tool 3: financial_metrics
# ═══════════════════════════════════════════════════════════════

_METRIC_REGISTRY = {
    "roe": "roe",
    "gross_margin": "gross_margin",
    "net_margin": "net_margin",
    "debt_ratio": "debt_ratio",
    "current_ratio": "current_ratio",
    "quick_ratio": "quick_ratio",
    "dupont": "dupont",
    "yoy_growth": "yoy_growth",
    "ocf_ni_ratio": "ocf_ni_ratio",
}

_ALL_METRICS = list(_METRIC_REGISTRY)


@tool("financial_metrics", parse_docstring=True)
def financial_metrics_tool(
    json_data: str,
    metrics: str = "all",
) -> str:
    """基于原始财报数据计算财务指标。不依赖 LLM 计算，保证准确性。

    支持的指标：
    - roe：净资产收益率 = 净利润 / 股东权益 × 100%
    - gross_margin：毛利率 = (营收 - 营业成本) / 营收 × 100%
    - net_margin：净利率 = 净利润 / 营收 × 100%
    - debt_ratio：资产负债率 = 总负债 / 总资产 × 100%
    - current_ratio：流动比率 = 流动资产 / 流动负债
    - quick_ratio：速动比率 = (流动资产 - 存货) / 流动负债
    - dupont：杜邦分析（ROE = 净利率 × 资产周转率 × 权益乘数）
    - yoy_growth：同比增长率（营收、净利润）
    - ocf_ni_ratio：经营现金流/净利润比
    - all：以上全部

    使用逗号分隔多个指标，如: "roe,gross_margin,dupont"

    Args:
        json_data: financial_data 工具返回的 JSON 数据字符串
        metrics: 要计算的指标，逗号分隔。默认 "all"

    Returns:
        JSON 字符串，包含各项指标的计算结果、公式和解读
    """
    try:
        data = json.loads(json_data)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"JSON 解析失败: {e}"}, ensure_ascii=False)

    # 确定指标列表
    if metrics == "all":
        metric_list = _ALL_METRICS
    else:
        metric_list = [m.strip() for m in metrics.split(",") if m.strip()]

    # 验证
    invalid = [m for m in metric_list if m not in _METRIC_REGISTRY]
    if invalid:
        return json.dumps({
            "error": f"不支持的指标: {invalid}",
            "available": _ALL_METRICS,
        }, ensure_ascii=False)

    # 计算
    results: dict = {}
    for metric in metric_list:
        try:
            fn = _CALC_FUNCTIONS[metric]
            results[metric] = fn(data)
        except Exception as e:
            logger.exception("计算指标 %s 失败", metric)
            results[metric] = {"error": str(e), "metric": metric}

    return json.dumps(results, indent=2, ensure_ascii=False, default=str)


# ═══════════════════════════════════════════════════════════════
# 数据提取工具
# ═══════════════════════════════════════════════════════════════

def _extract(data: dict, *item_hints: str) -> float | None:
    """从财报 dict 中递归查找科目金额。

    遍历路径：
    1. 直接在 data["data"] 列表中按 item 名称匹配
    2. 递归进入 income_statement / balance_sheet / cash_flow 子 dict
    3. 模糊匹配：item 名称中包含任意 hint 就算匹配
    """
    if not isinstance(data, dict):
        return None

    # 检查 data 列表
    items = data.get("data")
    if isinstance(items, list):
        for entry in items:
            if isinstance(entry, dict):
                item_name = entry.get("item", "")
                for hint in item_hints:
                    if hint in item_name:
                        try:
                            return float(entry.get("amount", 0))
                        except (ValueError, TypeError):
                            return None

    # 递归子 dict
    for key in ("income_statement", "balance_sheet", "cash_flow"):
        section = data.get(key)
        if isinstance(section, dict):
            result = _extract(section, *item_hints)
            if result is not None:
                return result

    return None


def _safe_div(a: float | None, b: float | None) -> float | None:
    """安全除法，分子或分母为 None/0 时返回 None。"""
    if a is None or b is None or b == 0:
        return None
    return a / b


# ═══════════════════════════════════════════════════════════════
#  7 个计算函数（纯函数，可在 calculate.py 中复用）
# ═══════════════════════════════════════════════════════════════

def _calc_roe(data: dict) -> dict:
    """ROE = 净利润 / 股东权益 × 100%"""
    net_profit = _extract(data, "净利润", "归属于母公司股东的净利润")
    equity = _extract(data, "股东权益合计", "归属于母公司股东权益合计", "所有者权益合计")
    val = _safe_div(net_profit, equity)
    return {
        "value": round(val * 100, 2) if val is not None else None,
        "formula": "净利润 / 股东权益 × 100%",
        "unit": "%",
    }


def _calc_gross_margin(data: dict) -> dict:
    """毛利率 = (营业收入 - 营业成本) / 营业收入 × 100%"""
    revenue = _extract(data, "营业收入", "营业总收入", "总收入")
    cost = _extract(data, "营业成本", "营业总成本")
    if revenue is None or revenue == 0 or cost is None:
        return {"value": None, "formula": "(营收 - 营业成本) / 营收 × 100%", "unit": "%"}
    return {
        "value": round((revenue - cost) / revenue * 100, 2),
        "formula": "(营收 - 营业成本) / 营收 × 100%",
        "unit": "%",
    }


def _calc_net_margin(data: dict) -> dict:
    """净利率 = 净利润 / 营业收入 × 100%"""
    net_profit = _extract(data, "净利润", "归属于母公司股东的净利润")
    revenue = _extract(data, "营业收入", "营业总收入", "总收入")
    val = _safe_div(net_profit, revenue)
    return {
        "value": round(val * 100, 2) if val is not None else None,
        "formula": "净利润 / 营收 × 100%",
        "unit": "%",
    }


def _calc_debt_ratio(data: dict) -> dict:
    """资产负债率 = 总负债 / 总资产 × 100%"""
    total_liability = _extract(data, "负债合计", "负债总计", "总负债")
    total_asset = _extract(data, "资产总计", "总资产", "资产合计")
    val = _safe_div(total_liability, total_asset)
    return {
        "value": round(val * 100, 2) if val is not None else None,
        "formula": "总负债 / 总资产 × 100%",
        "unit": "%",
    }


def _calc_current_ratio(data: dict) -> dict:
    """流动比率 = 流动资产 / 流动负债"""
    current_assets = _extract(data, "流动资产合计")
    current_liability = _extract(data, "流动负债合计")
    val = _safe_div(current_assets, current_liability)
    return {
        "value": round(val, 2) if val is not None else None,
        "formula": "流动资产 / 流动负债",
        "unit": "",
    }


def _calc_quick_ratio(data: dict) -> dict:
    """速动比率 = (流动资产 - 存货) / 流动负债"""
    current_assets = _extract(data, "流动资产合计")
    inventory = _extract(data, "存货", "存货净额")
    current_liability = _extract(data, "流动负债合计")
    if current_assets is None or inventory is None or current_liability is None or current_liability == 0:
        return {"value": None, "formula": "(流动资产 - 存货) / 流动负债", "unit": ""}
    return {
        "value": round((current_assets - inventory) / current_liability, 2),
        "formula": "(流动资产 - 存货) / 流动负债",
        "unit": "",
    }


def _calc_dupont(data: dict) -> dict:
    """杜邦三因子分析：ROE = 净利率 × 资产周转率 × 权益乘数"""
    net_profit = _extract(data, "净利润", "归属于母公司股东的净利润")
    revenue = _extract(data, "营业收入", "营业总收入", "总收入")
    total_asset = _extract(data, "资产总计", "总资产", "资产合计")
    equity = _extract(data, "股东权益合计", "归属于母公司股东权益合计", "所有者权益合计")

    if any(v is None or v == 0 for v in [revenue, total_asset, equity]):
        return {"value": None, "formula": "净利率 × 资产周转率 × 权益乘数", "unit": "%",
                "error": "数据不完整（营收/总资产/股东权益缺失或为零）"}

    net_margin_val = net_profit / revenue if net_profit else 0
    asset_turnover = revenue / total_asset
    equity_multiplier = total_asset / equity
    roe = net_margin_val * asset_turnover * equity_multiplier * 100

    return {
        "value": round(roe, 2),
        "formula": "净利率 × 资产周转率 × 权益乘数",
        "unit": "%",
        "breakdown": {
            "net_margin": round(net_margin_val * 100, 2),
            "asset_turnover": round(asset_turnover, 2),
            "equity_multiplier": round(equity_multiplier, 2),
        },
        "interpretation": {
            "high_net_margin": "品牌/技术壁垒 → 高附加值型",
            "high_asset_turnover": "运营效率 → 薄利多销型",
            "high_equity_multiplier": "高杠杆 → 需关注偿债风险",
        },
    }


def _calc_yoy_growth(data: dict) -> dict:
    """同比增长率。注意：需要至少两期数据，如果只提供了单期数据则仅回显当期值。"""
    revenue = _extract(data, "营业收入", "营业总收入")
    net_profit = _extract(data, "净利润", "归属于母公司股东的净利润")
    return {
        "current_period": {
            "revenue": revenue,
            "net_profit": net_profit,
        },
        "note": "同比计算需要去年同期数据。如果 data 中包含 multiple periods 数据可自动计算，否则仅回显当期绝对值。",
        "formula": "(当期 - 去年同期) / |去年同期| × 100%",
        "unit": "%",
    }


def _calc_ocf_ni_ratio(data: dict) -> dict:
    """经营现金流/净利润比 = 经营活动现金流量净额 / 净利润"""
    ocf = _extract(data, "经营活动产生的现金流量净额", "经营活动现金流量净额")
    net_profit = _extract(data, "净利润", "归属于母公司股东的净利润")
    val = _safe_div(ocf, net_profit)
    return {
        "value": round(val, 2) if val is not None else None,
        "formula": "经营现金流 / 净利润",
        "unit": "",
        "interpretation": "> 1.0 健康，< 0.5 利润质量存疑",
    }


# ─── 计算函数注册表 ──────────────────────────────────────

_CALC_FUNCTIONS = {
    "roe": _calc_roe,
    "gross_margin": _calc_gross_margin,
    "net_margin": _calc_net_margin,
    "debt_ratio": _calc_debt_ratio,
    "current_ratio": _calc_current_ratio,
    "quick_ratio": _calc_quick_ratio,
    "dupont": _calc_dupont,
    "yoy_growth": _calc_yoy_growth,
    "ocf_ni_ratio": _calc_ocf_ni_ratio,
}
