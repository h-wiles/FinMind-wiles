"""Tests for financial data tools and calculation functions."""

import json

import pytest

from deerflow.community.financial.tools import (
    _extract,
    _safe_div,
    _calc_roe,
    _calc_gross_margin,
    _calc_net_margin,
    _calc_debt_ratio,
    _calc_current_ratio,
    _calc_quick_ratio,
    _calc_dupont,
    _calc_yoy_growth,
    _calc_ocf_ni_ratio,
    _CALC_FUNCTIONS,
    financial_data_tool,
    stock_info_tool,
    financial_metrics_tool,
)


# ═══════════════════════════════════════════════════════════════
# 模拟财报数据
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def maotai_data():
    """模拟贵州茅台 2024 年报数据（金额单位：元）"""
    return {
        "income_statement": {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "report_type": "income_statement",
            "period": "2024",
            "data": [
                {"item": "营业收入", "amount": 150_000_000_000},
                {"item": "营业成本", "amount": 12_000_000_000},
                {"item": "销售费用", "amount": 5_000_000_000},
                {"item": "管理费用", "amount": 8_000_000_000},
                {"item": "净利润", "amount": 75_000_000_000},
                {"item": "归属于母公司股东的净利润", "amount": 75_000_000_000},
            ],
        },
        "balance_sheet": {
            "data": [
                {"item": "资产总计", "amount": 300_000_000_000},
                {"item": "流动资产合计", "amount": 200_000_000_000},
                {"item": "货币资金", "amount": 80_000_000_000},
                {"item": "存货", "amount": 40_000_000_000},
                {"item": "负债合计", "amount": 60_000_000_000},
                {"item": "流动负债合计", "amount": 50_000_000_000},
                {"item": "股东权益合计", "amount": 240_000_000_000},
                {"item": "归属于母公司股东权益合计", "amount": 240_000_000_000},
            ],
        },
        "cash_flow": {
            "data": [
                {"item": "经营活动现金流量净额", "amount": 70_000_000_000},
            ],
        },
    }


@pytest.fixture
def empty_data():
    return {}


# ═══════════════════════════════════════════════════════════════
# _extract
# ═══════════════════════════════════════════════════════════════

class TestExtract:
    def test_direct_match(self, maotai_data):
        assert _extract(maotai_data, "营业收入") == 150_000_000_000

    def test_balance_sheet_item(self, maotai_data):
        assert _extract(maotai_data, "资产总计") == 300_000_000_000

    def test_cashflow_item(self, maotai_data):
        assert _extract(maotai_data, "经营活动现金流量净额") == 70_000_000_000

    def test_partial_match(self, maotai_data):
        """hint 包含在 item 名称中即可匹配"""
        assert _extract(maotai_data, "货币资金")

    def test_multiple_hints_fallback(self, maotai_data):
        """多个 hint 依次尝试，净利润没匹配到就找归母净利润"""
        assert _extract(maotai_data, "净利润", "归属于母公司股东的净利润") == 75_000_000_000

    def test_nonexistent_item(self, maotai_data):
        assert _extract(maotai_data, "不存在的科目") is None

    def test_empty_data(self, empty_data):
        assert _extract(empty_data, "营业收入") is None

    def test_none_data(self):
        assert _extract(None, "营业收入") is None

    def test_no_data_key(self):
        assert _extract({"not_data": 123}, "营业收入") is None


# ═══════════════════════════════════════════════════════════════
# _safe_div
# ═══════════════════════════════════════════════════════════════

class TestSafeDiv:
    def test_normal(self):
        assert _safe_div(10, 2) == 5.0

    def test_numerator_none(self):
        assert _safe_div(None, 100) is None

    def test_denominator_none(self):
        assert _safe_div(100, None) is None

    def test_denominator_zero(self):
        assert _safe_div(100, 0) is None

    def test_both_none(self):
        assert _safe_div(None, None) is None


# ═══════════════════════════════════════════════════════════════
# 计算函数 — 正常数据
# ═══════════════════════════════════════════════════════════════

class TestCalcROE:
    def test_maotai(self, maotai_data):
        result = _calc_roe(maotai_data)
        assert result["value"] == 31.25  # 750亿 / 2400亿
        assert result["unit"] == "%"

    def test_empty(self, empty_data):
        result = _calc_roe(empty_data)
        assert result["value"] is None


class TestCalcGrossMargin:
    def test_maotai(self, maotai_data):
        result = _calc_gross_margin(maotai_data)
        assert result["value"] == 92.0  # (1500-120)/1500

    def test_empty(self, empty_data):
        result = _calc_gross_margin(empty_data)
        assert result["value"] is None


class TestCalcNetMargin:
    def test_maotai(self, maotai_data):
        result = _calc_net_margin(maotai_data)
        assert result["value"] == 50.0  # 750/1500

    def test_empty(self, empty_data):
        result = _calc_net_margin(empty_data)
        assert result["value"] is None


class TestCalcDebtRatio:
    def test_maotai(self, maotai_data):
        result = _calc_debt_ratio(maotai_data)
        assert result["value"] == 20.0  # 600/3000

    def test_empty(self, empty_data):
        result = _calc_debt_ratio(empty_data)
        assert result["value"] is None


class TestCalcCurrentRatio:
    def test_maotai(self, maotai_data):
        result = _calc_current_ratio(maotai_data)
        assert result["value"] == 4.0  # 2000/500

    def test_empty(self, empty_data):
        result = _calc_current_ratio(empty_data)
        assert result["value"] is None


class TestCalcQuickRatio:
    def test_maotai(self, maotai_data):
        result = _calc_quick_ratio(maotai_data)
        assert result["value"] == 3.2  # (2000-400)/500

    def test_empty(self, empty_data):
        result = _calc_quick_ratio(empty_data)
        assert result["value"] is None


class TestCalcDupont:
    def test_maotai(self, maotai_data):
        result = _calc_dupont(maotai_data)
        assert result["value"] == 31.25
        assert result["breakdown"]["net_margin"] == 50.0
        assert result["breakdown"]["asset_turnover"] == 0.5    # 1500/3000
        assert result["breakdown"]["equity_multiplier"] == 1.25  # 3000/2400
        assert "interpretation" in result

    def test_empty(self, empty_data):
        result = _calc_dupont(empty_data)
        assert result["value"] is None


class TestCalcYoYGrowth:
    def test_shows_current_values(self, maotai_data):
        result = _calc_yoy_growth(maotai_data)
        assert result["current_period"]["revenue"] == 150_000_000_000
        assert result["current_period"]["net_profit"] == 75_000_000_000
        assert "去年同期" in result["note"]


class TestCalcOCFNIRatio:
    def test_maotai(self, maotai_data):
        result = _calc_ocf_ni_ratio(maotai_data)
        assert result["value"] == pytest.approx(0.93, abs=0.01)  # 700/750

    def test_empty(self, empty_data):
        result = _calc_ocf_ni_ratio(empty_data)
        assert result["value"] is None


# ═══════════════════════════════════════════════════════════════
# 计算函数 — 边界情况
# ═══════════════════════════════════════════════════════════════

class TestCalcEdgeCases:
    def test_zero_revenue(self):
        """营收为 0 时毛利率应优雅处理"""
        data = {
            "income_statement": {"data": [
                {"item": "营业收入", "amount": 0},
                {"item": "营业成本", "amount": 100},
            ]}
        }
        result = _calc_gross_margin(data)
        assert result["value"] is None

    def test_zero_equity(self):
        """股东权益为 0 时 ROE 应返回 None"""
        data = {
            "income_statement": {"data": [{"item": "净利润", "amount": 100}]},
            "balance_sheet": {"data": [{"item": "股东权益合计", "amount": 0}]},
        }
        result = _calc_roe(data)
        assert result["value"] is None

    def test_negative_net_profit(self):
        """净利润为负时 ROE 应为负数"""
        data = {
            "income_statement": {"data": [{"item": "净利润", "amount": -50_000_000}]},
            "balance_sheet": {"data": [{"item": "股东权益合计", "amount": 200_000_000}]},
        }
        result = _calc_roe(data)
        assert result["value"] == -25.0  # -5000万 / 2亿

    def test_missing_balance_sheet(self):
        """缺少资产负债表时相关指标返回 None"""
        data = {
            "income_statement": {"data": [
                {"item": "营业收入", "amount": 100},
                {"item": "净利润", "amount": 10},
            ]}
        }
        assert _calc_debt_ratio(data)["value"] is None
        assert _calc_current_ratio(data)["value"] is None
        # 净利率只需要利润表，应该能算
        assert _calc_net_margin(data)["value"] == 10.0


# ═══════════════════════════════════════════════════════════════
# 指标注册表
# ═══════════════════════════════════════════════════════════════

class TestMetricRegistry:
    def test_all_metrics_registered(self):
        expected = {"roe", "gross_margin", "net_margin", "debt_ratio",
                    "current_ratio", "quick_ratio", "dupont",
                    "yoy_growth", "ocf_ni_ratio"}
        assert set(_CALC_FUNCTIONS.keys()) == expected

    def test_all_callable(self):
        for name, fn in _CALC_FUNCTIONS.items():
            assert callable(fn), f"{name} is not callable"


# ═══════════════════════════════════════════════════════════════
# financial_metrics_tool
# ═══════════════════════════════════════════════════════════════

class TestFinancialMetricsTool:
    def test_all_metrics(self, maotai_data):
        json_str = json.dumps(maotai_data)
        result_str = financial_metrics_tool.invoke({"json_data": json_str, "metrics": "all"})
        result = json.loads(result_str)
        assert "roe" in result
        assert "gross_margin" in result
        assert "dupont" in result
        assert result["roe"]["value"] == 31.25

    def test_single_metric(self, maotai_data):
        json_str = json.dumps(maotai_data)
        result_str = financial_metrics_tool.invoke({"json_data": json_str, "metrics": "roe"})
        result = json.loads(result_str)
        assert list(result.keys()) == ["roe"]

    def test_multiple_metrics(self, maotai_data):
        json_str = json.dumps(maotai_data)
        result_str = financial_metrics_tool.invoke({"json_data": json_str, "metrics": "roe,gross_margin"})
        result = json.loads(result_str)
        assert "roe" in result
        assert "gross_margin" in result
        assert "dupont" not in result

    def test_invalid_metric(self, maotai_data):
        json_str = json.dumps(maotai_data)
        result_str = financial_metrics_tool.invoke({"json_data": json_str, "metrics": "invalid_metric"})
        result = json.loads(result_str)
        assert "error" in result
        assert "invalid_metric" in str(result["error"])

    def test_invalid_json(self):
        result_str = financial_metrics_tool.invoke({"json_data": "not valid json", "metrics": "roe"})
        result = json.loads(result_str)
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# financial_data_tool — 错误路径
# ═══════════════════════════════════════════════════════════════

class TestFinancialDataTool:
    def test_invalid_code_returns_error(self):
        """无效代码应返回 error JSON 而不是抛异常"""
        result_str = financial_data_tool.invoke(
            {"stock_code": "!!!", "report_type": "all", "period": "latest"}
        )
        result = json.loads(result_str)
        assert "error" in result

    def test_valid_code_does_not_crash(self):
        """有效代码不应抛异常（可能因网络不可用返回空数据，但不崩溃）"""
        result_str = financial_data_tool.invoke(
            {"stock_code": "600519", "report_type": "all", "period": "latest"}
        )
        result = json.loads(result_str)
        # 有网络时返回数据，无网络时返回 error，任何情况都不应崩溃
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════
# stock_info_tool — 错误路径
# ═══════════════════════════════════════════════════════════════

class TestStockInfoTool:
    def test_invalid_code_returns_error(self):
        result_str = stock_info_tool.invoke({"stock_code": "!!!"})
        result = json.loads(result_str)
        assert "error" in result

    def test_valid_code_does_not_crash(self):
        result_str = stock_info_tool.invoke({"stock_code": "600519"})
        result = json.loads(result_str)
        assert isinstance(result, dict)
