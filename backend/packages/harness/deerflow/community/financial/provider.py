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

    raw_code: str  # 用户输入的原始代码
    market: str  # "a_share" | "hk_share" | "us_share"
    normalized_code: str  # 各 provider 内部使用的标准化代码


class FinancialDataProvider(ABC):
    """财务数据提供商抽象基类"""

    @abstractmethod
    def get_financial_report(self, stock_code: str, report_type: str, period: str) -> dict:
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
        # A股示例：stock_financial_abstract_ths(symbol="600519", indicator="按报告期")
        # 港股示例：stock_hk_financial_indicator_em(symbol="00700")
        ...

    def get_stock_info(self, stock_code):
        # stock_individual_info_em(symbol="600519") → PE/PB/市值
        # stock_hk_spot_em() → 港股实时行情
        ...

    def get_historical_financials(self, stock_code, years=5): ...


class YfinanceProvider(FinancialDataProvider):
    """美股 + 港股补充数据提供商（基于 yfinance）"""

    def get_financial_report(self, stock_code, report_type, period):
        # ticker = yf.Ticker("AAPL")
        # ticker.balance_sheet / ticker.financials / ticker.cashflow
        ...

    def get_stock_info(self, stock_code):
        # ticker.info → market_cap, pe_ratio, etc.
        ...

    def get_historical_financials(self, stock_code, years=5): ...


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
        raise ValueError(f"无法识别股票代码 {raw_code} 的市场。支持格式：600519（A股）、HK.00700（港股）、AAPL（美股）")

    def _route(self, sid: StockIdentifier) -> FinancialDataProvider:
        if sid.market == "a_share":
            return self._a_share
        return self._us_hk  # 港股和美股都用 yfinance（港股 akshare 备用）

    def get_financial_report(self, stock_code, report_type, period):
        sid = self._classify(stock_code)
        return self._route(sid).get_financial_report(sid.normalized_code, report_type, period)

    def get_stock_info(self, stock_code):
        sid = self._classify(stock_code)
        result = self._route(sid).get_stock_info(sid.normalized_code)
        result["market"] = sid.market
        return result

    def get_historical_financials(self, stock_code, years=5):
        sid = self._classify(stock_code)
        return self._route(sid).get_historical_financials(sid.normalized_code, years)
