"""Tests for financial data providers."""

import pytest

from deerflow.community.financial.provider import (
    CompositeProvider,
    StockIdentifier,
    _safe_float,
)


# ═══════════════════════════════════════════════════════════════
# _safe_float
# ═══════════════════════════════════════════════════════════════

class TestSafeFloat:
    def test_normal_float(self):
        assert _safe_float(3.14) == 3.14

    def test_int(self):
        assert _safe_float(42) == 42.0

    def test_string_number(self):
        assert _safe_float("123.45") == 123.45

    def test_none(self):
        assert _safe_float(None) is None

    def test_nan_string(self):
        assert _safe_float("nan") is None

    def test_invalid_string(self):
        assert _safe_float("not_a_number") is None

    def test_empty_string(self):
        assert _safe_float("") is None


# ═══════════════════════════════════════════════════════════════
# StockIdentifier
# ═══════════════════════════════════════════════════════════════

class TestStockIdentifier:
    def test_create(self):
        sid = StockIdentifier("600519", "a_share", "600519")
        assert sid.raw_code == "600519"
        assert sid.market == "a_share"
        assert sid.normalized_code == "600519"


# ═══════════════════════════════════════════════════════════════
# CompositeProvider._classify
# ═══════════════════════════════════════════════════════════════

class TestClassify:
    def setup_method(self):
        self.cp = CompositeProvider()

    # ── A股 ──

    def test_a_share_shanghai(self):
        """上交所 6xxxxx"""
        sid = self.cp._classify("600519")
        assert sid.market == "a_share"
        assert sid.normalized_code == "600519"

    def test_a_share_shenzhen_main(self):
        """深交所主板 0xxxxx"""
        sid = self.cp._classify("000858")
        assert sid.market == "a_share"
        assert sid.normalized_code == "000858"

    def test_a_share_shenzhen_gem(self):
        """深交所创业板 3xxxxx"""
        sid = self.cp._classify("300750")
        assert sid.market == "a_share"
        assert sid.normalized_code == "300750"

    # ── 港股 ──

    def test_hk_share_with_prefix(self):
        sid = self.cp._classify("HK.00700")
        assert sid.market == "hk_share"
        assert sid.normalized_code == "00700"

    def test_hk_share_lowercase_prefix(self):
        """HK. 前缀大小写不敏感（会被 upper）"""
        sid = self.cp._classify("hk.09988")
        assert sid.market == "hk_share"
        assert sid.normalized_code == "09988"

    def test_hk_share_with_spaces(self):
        """前后空格被 strip"""
        sid = self.cp._classify("  HK.00700  ")
        assert sid.market == "hk_share"
        assert sid.normalized_code == "00700"

    # ── 美股 ──

    def test_us_share_aapl(self):
        sid = self.cp._classify("AAPL")
        assert sid.market == "us_share"
        assert sid.normalized_code == "AAPL"

    def test_us_share_tsla(self):
        sid = self.cp._classify("TSLA")
        assert sid.market == "us_share"

    def test_us_share_nvda(self):
        sid = self.cp._classify("NVDA")
        assert sid.market == "us_share"

    def test_us_share_single_char(self):
        """美股代码最少 1 个字母"""
        sid = self.cp._classify("F")  # Ford
        assert sid.market == "us_share"

    def test_us_share_five_char(self):
        """美股代码最多 5 个字母"""
        sid = self.cp._classify("BRKB")  # 5 字母纯字母
        assert sid.market == "us_share"
        assert sid.normalized_code == "BRKB"

    # ── 无效代码 ──

    def test_invalid_mixed(self):
        """混合字符应抛异常"""
        with pytest.raises(ValueError, match="无法识别"):
            self.cp._classify("invalid!")

    def test_invalid_empty(self):
        with pytest.raises(ValueError, match="无法识别"):
            self.cp._classify("")

    def test_invalid_too_many_digits(self):
        """超过 6 位的纯数字"""
        with pytest.raises(ValueError, match="无法识别"):
            self.cp._classify("12345678")

    def test_invalid_short_digits(self):
        """不是 6 位的数字"""
        with pytest.raises(ValueError, match="无法识别"):
            self.cp._classify("123")

    def test_invalid_too_long_alpha(self):
        """超过 5 个字母"""
        with pytest.raises(ValueError, match="无法识别"):
            self.cp._classify("TOOLONG")


# ═══════════════════════════════════════════════════════════════
# CompositeProvider._route
# ═══════════════════════════════════════════════════════════════

class TestRoute:
    def setup_method(self):
        self.cp = CompositeProvider()

    def test_routes_a_share_to_akshare(self):
        from deerflow.community.financial.provider import AkshareProvider

        sid = StockIdentifier("600519", "a_share", "600519")
        provider = self.cp._route(sid)
        assert isinstance(provider, AkshareProvider)

    def test_routes_hk_share_to_yfinance(self):
        from deerflow.community.financial.provider import YfinanceProvider

        sid = StockIdentifier("HK.00700", "hk_share", "00700")
        provider = self.cp._route(sid)
        assert isinstance(provider, YfinanceProvider)

    def test_routes_us_share_to_yfinance(self):
        from deerflow.community.financial.provider import YfinanceProvider

        sid = StockIdentifier("AAPL", "us_share", "AAPL")
        provider = self.cp._route(sid)
        assert isinstance(provider, YfinanceProvider)
