"""
财务数据提供商抽象层。

支持的提供商：
- AkshareProvider：A股主力（免费，无需 API Key）
- YfinanceProvider：美股主力 + 港股（免费）
- CompositeProvider：自动路由（根据股票代码前缀选择提供商）

所有 Provider 返回统一的 dict 格式，调用方不需要关心底层数据源。
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ─── 常量 ──────────────────────────────────────────────────

_A_SHARE_BALANCE_KEYS = [
    "资产总计", "流动资产合计", "货币资金", "应收账款", "存货",
    "非流动资产合计", "固定资产", "无形资产", "商誉",
    "负债合计", "流动负债合计", "短期借款", "应付账款",
    "非流动负债合计", "长期借款", "应付债券",
    "股东权益合计", "实收资本（或股本）", "资本公积", "盈余公积", "未分配利润",
    "归属于母公司股东权益合计",
]

_A_SHARE_INCOME_KEYS = [
    "营业总收入", "营业收入", "营业成本", "销售费用", "管理费用",
    "研发费用", "财务费用", "投资收益", "营业利润", "利润总额",
    "所得税费用", "净利润", "归属于母公司股东的净利润",
    "扣除非经常性损益的净利润", "基本每股收益",
]

_A_SHARE_CASHFLOW_KEYS = [
    "经营活动现金流量净额", "销售商品提供劳务收到的现金",
    "投资活动现金流量净额", "购建固定资产无形资产和其他长期资产支付的现金",
    "筹资活动现金流量净额", "分配股利利润或偿付利息支付的现金",
]


@dataclass
class StockIdentifier:
    """统一股票标识"""
    raw_code: str
    market: str          # "a_share" | "hk_share" | "us_share"
    normalized_code: str


class FinancialDataProvider(ABC):
    """财务数据提供商抽象基类"""

    @abstractmethod
    def get_financial_report(self, stock_code: str, report_type: str, period: str) -> dict:
        """获取财报数据。返回 {"stock_code", "stock_name", "report_type", "period", "data": [...]}"""
        ...

    @abstractmethod
    def get_stock_info(self, stock_code: str) -> dict:
        """获取股票基本信息。返回 {"stock_code", "stock_name", "market", "industry", ...}"""
        ...

    @abstractmethod
    def get_historical_financials(self, stock_code: str, years: int = 5) -> list[dict]:
        """获取历年财务数据。返回 [{"period": "2024", "revenue": ..., "net_profit": ..., ...}, ...]"""
        ...


# ═══════════════════════════════════════════════════════════════
# AkshareProvider — A 股
# ═══════════════════════════════════════════════════════════════

class AkshareProvider(FinancialDataProvider):
    """A股数据提供商（基于 akshare）。

    akshare 是免费库，数据来自东方财富、新浪财经等公开接口。
    注意：这些接口可能因上游变动而暂时不可用，但通常会自动恢复。
    """

    def _ensure_ak(self):
        try:
            import akshare as ak
            return ak
        except ImportError:
            raise ImportError(
                "akshare 未安装。请运行: pip install akshare"
            )

    # ── 财报 ──────────────────────────────────────────────

    def get_financial_report(self, stock_code: str, report_type: str, period: str) -> dict:
        ak = self._ensure_ak()
        stock_name = self._resolve_stock_name(ak, stock_code)

        try:
            raw = ak.stock_financial_abstract_ths(symbol=stock_code, indicator="按报告期")
        except Exception as e:
            logger.warning("akshare stock_financial_abstract_ths 失败: %s，尝试备用接口", e)
            try:
                raw = ak.stock_financial_abstract_ths(symbol=stock_code, indicator="按年度")
            except Exception:
                return {
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "report_type": report_type,
                    "period": period,
                    "data": [],
                    "error": f"akshare 财报接口不可用: {e}",
                }

        if raw is None or raw.empty:
            return {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "report_type": report_type,
                "period": period,
                "data": [],
                "error": "akshare 返回空数据，可能股票代码无效或接口变动",
            }

        # 找到目标报告期
        if period != "latest":
            # period 可能是 "2024" / "2024Q3" / "2024-12-31"
            target_rows = raw[raw["报告期"].str.contains(str(period), na=False)]
            if target_rows.empty:
                return {
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "report_type": report_type,
                    "period": period,
                    "data": [],
                    "error": f"未找到报告期 {period} 的数据",
                }
            row = target_rows.iloc[0]
        else:
            row = raw.iloc[0]

        period_str = str(row.get("报告期", period))

        # 按 report_type 筛选科目
        if report_type == "balance_sheet":
            keys = _A_SHARE_BALANCE_KEYS
        elif report_type == "income_statement":
            keys = _A_SHARE_INCOME_KEYS
        elif report_type == "cash_flow":
            keys = _A_SHARE_CASHFLOW_KEYS
        else:
            keys = _A_SHARE_BALANCE_KEYS + _A_SHARE_INCOME_KEYS + _A_SHARE_CASHFLOW_KEYS

        data = []
        for key in keys:
            if key in row.index:
                val = row[key]
                if val is not None and str(val) != "nan":
                    try:
                        data.append({"item": key, "amount": float(val), "unit": "元"})
                    except (ValueError, TypeError):
                        pass

        return {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "report_type": report_type,
            "period": period_str,
            "data": data,
        }

    # ── 股票信息 ──────────────────────────────────────────

    def get_stock_info(self, stock_code: str) -> dict:
        ak = self._ensure_ak()
        stock_name = self._resolve_stock_name(ak, stock_code)

        result = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "market": "a_share",
            "industry": "",
            "market_cap": 0.0,
            "pe_ratio": None,
            "pb_ratio": None,
            "ps_ratio": None,
            "dividend_yield": None,
            "52w_high": None,
            "52w_low": None,
        }

        try:
            info = ak.stock_individual_info_em(symbol=stock_code)
            if info is not None and not info.empty:
                info_dict = dict(zip(info["item"], info["value"]))

                def _get_float(key: str) -> float | None:
                    v = info_dict.get(key)
                    if v is None or v == "" or str(v) == "nan":
                        return None
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        return None

                result["industry"] = str(info_dict.get("行业", info_dict.get("industry", "")))
                result["market_cap"] = _get_float("总市值") or _get_float("totalMarketCap") or 0.0
                result["pe_ratio"] = _get_float("市盈率-动态") or _get_float("PE")
                result["pb_ratio"] = _get_float("市净率") or _get_float("PB")
        except Exception as e:
            logger.warning("akshare stock_individual_info_em 失败: %s", e)

        return result

    # ── 历史 ──────────────────────────────────────────────

    def get_historical_financials(self, stock_code: str, years: int = 5) -> list[dict]:
        ak = self._ensure_ak()
        try:
            raw = ak.stock_financial_abstract_ths(symbol=stock_code, indicator="按报告期")
        except Exception as e:
            logger.warning("akshare 历史财报失败: %s", e)
            return []

        if raw is None or raw.empty:
            return []

        results = []
        for _, row in raw.head(years * 4).iterrows():  # 每年最多 4 季
            period = str(row.get("报告期", ""))
            try:
                revenue = float(row.get("营业总收入", row.get("营业收入", 0)))
                net_profit = float(row.get("净利润", row.get("归属于母公司股东的净利润", 0)))
            except (ValueError, TypeError):
                continue

            results.append({
                "period": period,
                "revenue": revenue,
                "net_profit": net_profit,
            })

        return results

    # ── 辅助 ──────────────────────────────────────────────

    def _resolve_stock_name(self, ak, stock_code: str) -> str:
        try:
            info = ak.stock_individual_info_em(symbol=stock_code)
            if info is not None and not info.empty:
                info_dict = dict(zip(info["item"], info["value"]))
                return str(info_dict.get("股票简称", stock_code))
        except Exception:
            pass
        return stock_code


# ═══════════════════════════════════════════════════════════════
# YfinanceProvider — 美股 + 港股
# ═══════════════════════════════════════════════════════════════

class YfinanceProvider(FinancialDataProvider):
    """美股 + 港股数据提供商（基于 yfinance）。

    yfinance 是免费库，数据来自 Yahoo Finance。
    港股代码需要加后缀（如 0700.HK），本 Provider 自动处理。
    """

    def _ensure_yf(self):
        try:
            import yfinance as yf
            return yf
        except ImportError:
            raise ImportError(
                "yfinance 未安装。请运行: pip install yfinance"
            )

    def _to_yf_symbol(self, stock_code: str) -> str:
        """将内部标准化代码转为 yfinance 代码。
        - A股: 600519 → 600519.SS (上交所) / 000858.SZ (深交所)
        - 港股: 00700 → 0700.HK
        - 美股: AAPL → AAPL
        """
        code = stock_code.strip().upper()
        if code.isdigit() and len(code) == 6:
            if code.startswith("6"):
                return f"{code}.SS"
            return f"{code}.SZ"
        if code.isdigit():
            return f"{code.lstrip('0')}.HK"
        return code

    # ── 财报 ──────────────────────────────────────────────

    def get_financial_report(self, stock_code: str, report_type: str, period: str) -> dict:
        yf = self._ensure_yf()
        symbol = self._to_yf_symbol(stock_code)

        try:
            ticker = yf.Ticker(symbol)
            stock_name = ticker.info.get("longName", ticker.info.get("shortName", stock_code))
        except Exception:
            stock_name = stock_code
            ticker = yf.Ticker(symbol)

        report_key = {
            "balance_sheet": "balance_sheet",
            "income_statement": "financials",
            "cash_flow": "cashflow",
        }.get(report_type, None)

        data = []
        error_msg = ""

        if report_key:
            try:
                df = getattr(ticker, report_key)
                if df is None or df.empty:
                    error_msg = f"{report_type} 数据为空"
                else:
                    date_col = df.columns[0] if period == "latest" else next(
                        (c for c in df.columns if str(period) in str(c)), None
                    )
                    if date_col is not None:
                        series = df[date_col].dropna()
                        period_str = str(date_col.date() if hasattr(date_col, "date") else date_col)
                        for item_name, amount in series.items():
                            try:
                                data.append({
                                    "item": str(item_name),
                                    "amount": float(amount),
                                    "unit": "USD" if not stock_code.isdigit() else "HKD",
                                })
                            except (ValueError, TypeError):
                                pass
                    else:
                        error_msg = f"未找到 {period} 期间数据"
            except Exception as e:
                error_msg = str(e)

        return {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "report_type": report_type,
            "period": period,
            "data": data,
            "error": error_msg or None,
        }

    # ── 股票信息 ──────────────────────────────────────────

    def get_stock_info(self, stock_code: str) -> dict:
        yf = self._ensure_yf()
        symbol = self._to_yf_symbol(stock_code)

        result = {
            "stock_code": stock_code,
            "stock_name": stock_code,
            "market": "",
            "industry": "",
            "market_cap": 0.0,
            "pe_ratio": None,
            "pb_ratio": None,
            "ps_ratio": None,
            "dividend_yield": None,
            "52w_high": None,
            "52w_low": None,
        }

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            if info:
                result.update({
                    "stock_name": str(info.get("longName", info.get("shortName", stock_code))),
                    "market": str(info.get("market", info.get("exchange", ""))),
                    "industry": str(info.get("industry", info.get("sector", ""))),
                    "market_cap": float(info.get("marketCap", 0) or 0),
                    "pe_ratio": _safe_float(info.get("trailingPE") or info.get("forwardPE")),
                    "pb_ratio": _safe_float(info.get("priceToBook")),
                    "ps_ratio": _safe_float(info.get("priceToSalesTrailing12Months")),
                    "dividend_yield": _safe_float(info.get("dividendYield")),
                    "52w_high": _safe_float(info.get("fiftyTwoWeekHigh")),
                    "52w_low": _safe_float(info.get("fiftyTwoWeekLow")),
                })
        except Exception as e:
            logger.warning("yfinance get_stock_info 失败: %s", e)

        return result

    # ── 历史 ──────────────────────────────────────────────

    def get_historical_financials(self, stock_code: str, years: int = 5) -> list[dict]:
        yf = self._ensure_yf()
        symbol = self._to_yf_symbol(stock_code)

        try:
            ticker = yf.Ticker(symbol)
            financials = ticker.financials
            if financials is None or financials.empty:
                return []

            results = []
            for col in financials.columns[:years]:
                date_str = str(col.date() if hasattr(col, "date") else col)[:4]
                series = financials[col]
                try:
                    revenue = float(series.get("Total Revenue", 0))
                    net_profit = float(series.get("Net Income", series.get("Net Income Common Stockholders", 0)))
                except (ValueError, TypeError):
                    continue
                results.append({"period": date_str, "revenue": revenue, "net_profit": net_profit})
            return results
        except Exception as e:
            logger.warning("yfinance 历史财报失败: %s", e)
            return []


# ═══════════════════════════════════════════════════════════════
# CompositeProvider — 自动路由
# ═══════════════════════════════════════════════════════════════

class CompositeProvider(FinancialDataProvider):
    """组合提供商 — 根据股票代码前缀自动选择底层 Provider。"""

    def __init__(self):
        self._a_share = AkshareProvider()
        self._us_hk = YfinanceProvider()

    def _classify(self, raw_code: str) -> StockIdentifier:
        code = raw_code.strip().upper()
        if code.startswith("HK."):
            return StockIdentifier(raw_code, "hk_share", code[3:])
        if code.isdigit() and len(code) == 6:
            return StockIdentifier(raw_code, "a_share", code)
        if code.isalpha() and 1 <= len(code) <= 5:
            return StockIdentifier(raw_code, "us_share", code)
        raise ValueError(
            f"无法识别股票代码 '{raw_code}' 的市场。"
            f"支持格式: 600519（A股）、HK.00700（港股）、AAPL（美股）"
        )

    def _route(self, sid: StockIdentifier) -> FinancialDataProvider:
        if sid.market == "a_share":
            return self._a_share
        return self._us_hk

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


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _safe_float(val: Any) -> float | None:
    """安全转 float，失败返回 None"""
    if val is None:
        return None
    try:
        v = float(val)
        return v if v == v else None  # NaN → None
    except (ValueError, TypeError):
        return None
