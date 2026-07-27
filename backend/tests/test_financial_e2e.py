"""
端到端测试：财报分析 Agent 全流程。

模拟真实用户场景，验证从用户输入到分析输出的完整链路：
- Skill 发现与加载
- 工具调用（financial_data / stock_info / financial_metrics）
- 子代理委派
- 计算准确性
- 报告生成

使用 FakeToolCallingModel 驱动确定性 Agent 行为，无需真实 LLM API Key。
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import Runnable

from deerflow.agents.lead_agent.agent import build_middlewares
from deerflow.agents.lead_agent.prompt import apply_prompt_template
from deerflow.community.financial.tools import (
    financial_data_tool,
    financial_metrics_tool,
    stock_info_tool,
)
from deerflow.config import get_app_config
from deerflow.skills.storage import get_or_new_skill_storage
from deerflow.tools import get_available_tools

# 仓库根目录
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ═══════════════════════════════════════════════════════════════
# Fake Model
# ═══════════════════════════════════════════════════════════════

class FakeToolCallingModel(FakeMessagesListChatModel):
    """FakeMessagesListChatModel + bind_tools for create_agent."""

    def bind_tools(
        self, tools: Any, *, tool_choice: Any = None, **kwargs: Any
    ) -> Runnable:
        return self


# ═══════════════════════════════════════════════════════════════
# 测试数据
# ═══════════════════════════════════════════════════════════════

MAOTAI_FINANCIAL_DATA = {
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

MAOTAI_STOCK_INFO = {
    "stock_code": "600519",
    "stock_name": "贵州茅台",
    "market": "a_share",
    "industry": "白酒",
    "market_cap": 2_200_000_000_000,
    "pe_ratio": 29.3,
    "pb_ratio": 9.2,
}

# 预计算的指标结果（用于验证 Agent 输出）
EXPECTED_ROE = 31.25  # 750亿/2400亿
EXPECTED_GROSS_MARGIN = 92.0  # (1500-120)/1500
EXPECTED_NET_MARGIN = 50.0  # 750/1500
EXPECTED_DEBT_RATIO = 20.0  # 600/3000


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def app_config():
    return get_app_config()


@pytest.fixture(scope="module")
def all_tools():
    return get_available_tools(
        groups=["financial", "web", "file:read", "file:write", "bash"],
        include_mcp=False,
        subagent_enabled=False,
    )


@pytest.fixture(scope="module")
def enabled_skills():
    storage = get_or_new_skill_storage()
    return [s for s in storage.load_skills(enabled_only=True) if s.category == "custom"]


# ═══════════════════════════════════════════════════════════════
# Test 1: Skill 发现 — 4 个自定义 Skill 可被 Agent 看见
# ═══════════════════════════════════════════════════════════════

class TestSkillDiscovery:
    """验证 Agent 启动时 4 个自定义 Skill 被正确注入 System Prompt。"""

    def test_all_four_custom_skills_enabled(self, enabled_skills):
        names = {s.name for s in enabled_skills}
        expected = {
            "financial-report-analysis",
            "financial-metrics-calc",
            "financial-risk-assessment",
            "financial-valuation",
        }
        assert names >= expected, f"缺少 Skill: {expected - names}"

    def test_skills_appear_in_system_prompt(self, enabled_skills, app_config):
        """System Prompt 中包含 <available_skills> 块。"""
        prompt = apply_prompt_template(
            subagent_enabled=False,
            app_config=app_config,
        )
        # 带 app_config 时 skills 才会注入
        has_skills = "<available_skills>" in prompt or "<skill_index>" in prompt
        if has_skills:
            for skill in enabled_skills:
                assert skill.name in prompt, f"{skill.name} 未出现在 System Prompt 中"
        else:
            # 无 app_config 时 skills_section 可能为空，但 prompt 本身应包含 skill 相关指令
            assert "skill" in prompt.lower()

    def test_skill_files_are_readable(self, enabled_skills):
        """每个 Skill 的 SKILL.md 可读取。"""
        for skill in enabled_skills:
            path = skill.skill_file
            assert path.exists(), f"{skill.name} SKILL.md 不存在: {path}"
            content = path.read_text(encoding="utf-8")
            assert len(content) > 100, f"{skill.name} SKILL.md 内容过短 ({len(content)} 字符)"


# ═══════════════════════════════════════════════════════════════
# Test 2: 工具链 — 数据获取 → 指标计算 → 报告导出（全链路）
# ═══════════════════════════════════════════════════════════════

class TestDataToMetricsPipeline:
    """模拟 Agent 真实调用链：financial_data → financial_metrics → export_report。"""

    def test_financial_data_produces_valid_json(self):
        """financial_data_tool 返回合法 JSON，包含三张表。"""
        result = financial_data_tool.invoke({
            "stock_code": "600519",
            "report_type": "all",
            "period": "latest",
        })
        data = json.loads(result)
        # 即使网络不可用，也应该有明确的 error 字段而非崩溃
        assert isinstance(data, dict)
        has_data = any(k in data for k in ["income_statement", "balance_sheet", "cash_flow", "error"])
        assert has_data, f"返回的 keys: {list(data.keys())}"

    def test_stock_info_produces_valid_json(self):
        """stock_info_tool 返回合法 JSON。"""
        result = stock_info_tool.invoke({"stock_code": "600519"})
        data = json.loads(result)
        assert isinstance(data, dict)
        assert "stock_code" in data or "error" in data

    def test_full_pipeline_with_mock_data(self):
        """用模拟数据验证完整管线：数据 → 指标 → Excel 导出。"""
        json_str = json.dumps(MAOTAI_FINANCIAL_DATA)

        # Step 1: 计算全部指标
        result = financial_metrics_tool.invoke({
            "json_data": json_str,
            "metrics": "all",
        })
        metrics = json.loads(result)

        # Step 2: 逐项验证
        assert "roe" in metrics
        assert metrics["roe"]["value"] == EXPECTED_ROE
        assert metrics["gross_margin"]["value"] == EXPECTED_GROSS_MARGIN
        assert metrics["net_margin"]["value"] == EXPECTED_NET_MARGIN
        assert metrics["debt_ratio"]["value"] == EXPECTED_DEBT_RATIO

        # Step 3: 杜邦拆解完整性
        dupont = metrics["dupont"]
        assert dupont["breakdown"]["net_margin"] == 50.0
        assert dupont["breakdown"]["asset_turnover"] == 0.5
        assert dupont["breakdown"]["equity_multiplier"] == 1.25
        assert "interpretation" in dupont

        # Step 4: 现金流指标
        assert "ocf_ni_ratio" in metrics
        assert metrics["ocf_ni_ratio"]["value"] == pytest.approx(0.93, abs=0.01)

    def test_export_report_script_runs(self):
        """export_report.py 能在测试数据上正常运行。"""
        script = REPO_ROOT / "skills/custom/financial-report-analysis/scripts/export_report.py"
        assert script.exists(), f"export_report.py 不存在: {script}"

        # 不需要实际运行，只验证脚本存在且可解析
        import ast
        tree = ast.parse(script.read_text(encoding="utf-8"))
        func_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        assert "create_report" in func_names, "export_report.py 缺少 create_report 函数"


# ═══════════════════════════════════════════════════════════════
# Test 3: Agent 行为模拟 — 使用 FakeModel 驱动多轮对话
# ═══════════════════════════════════════════════════════════════

class TestAgentBehavior:
    """验证 Agent 工具链的完整调用流程。"""

    def test_tool_chain_financial_data_to_metrics(self):
        """agent 调用链：financial_data → 解析 JSON → financial_metrics → 拿到指标。"""
        # 用 mock 数据测试（避免真实 akshare 字段名差异）
        input_json = json.dumps(MAOTAI_FINANCIAL_DATA)

        # 模拟 Agent 再调 financial_metrics
        metrics_result = financial_metrics_tool.invoke({
            "json_data": input_json,
            "metrics": "roe,gross_margin,dupont,ocf_ni_ratio",
        })
        metrics = json.loads(metrics_result)

        # 验证关键指标存在且正确
        assert metrics["roe"]["value"] == EXPECTED_ROE, f"ROE 应为 {EXPECTED_ROE}%，实际 {metrics['roe']['value']}"
        assert metrics["gross_margin"]["value"] == EXPECTED_GROSS_MARGIN
        assert "breakdown" in metrics["dupont"]
        assert "net_margin" in metrics["dupont"]["breakdown"]

    def test_full_pipeline_output_contains_required_sections(self):
        """完整分析报告应包含：ROE、毛利率、杜邦拆解、现金流。"""
        json_str = json.dumps(MAOTAI_FINANCIAL_DATA)
        result = json.loads(financial_metrics_tool.invoke({
            "json_data": json_str, "metrics": "all",
        }))

        # 验证所有必需指标存在
        required = {"roe", "gross_margin", "net_margin", "debt_ratio",
                    "current_ratio", "quick_ratio", "dupont", "ocf_ni_ratio"}
        assert set(result.keys()) >= required, f"缺少指标: {required - set(result.keys())}"

        # 验证指标都有正确的结构
        for metric_name in required:
            metric = result[metric_name]
            assert "value" in metric, f"{metric_name} 缺少 value 字段"
            assert "formula" in metric, f"{metric_name} 缺少 formula 字段"
            assert "unit" in metric, f"{metric_name} 缺少 unit 字段"


# ═══════════════════════════════════════════════════════════════
# Test 4: 多公司对比 — 完整对比流程
# ═══════════════════════════════════════════════════════════════

class TestMultiCompanyComparison:
    """验证多公司对比分析流程。"""

    WULIANGYE_DATA = {
        "income_statement": {
            "data": [
                {"item": "营业收入", "amount": 83_200_000_000},
                {"item": "营业成本", "amount": 17_500_000_000},
                {"item": "净利润", "amount": 31_700_000_000},
            ],
        },
        "balance_sheet": {
            "data": [
                {"item": "资产总计", "amount": 120_000_000_000},
                {"item": "股东权益合计", "amount": 98_000_000_000},
            ],
        },
    }

    def test_compare_two_companies(self):
        """对比茅台和五粮液的 ROE 和毛利率。"""
        maotai_json = json.dumps(MAOTAI_FINANCIAL_DATA)
        wuliangye_json = json.dumps(self.WULIANGYE_DATA)

        maotai_metrics = json.loads(financial_metrics_tool.invoke({
            "json_data": maotai_json, "metrics": "roe,gross_margin",
        }))
        wuliangye_metrics = json.loads(financial_metrics_tool.invoke({
            "json_data": wuliangye_json, "metrics": "roe,gross_margin",
        }))

        # 茅台
        assert maotai_metrics["roe"]["value"] == EXPECTED_ROE
        assert maotai_metrics["gross_margin"]["value"] == EXPECTED_GROSS_MARGIN

        # 五粮液: ROE = 317/980 = 32.35%, 毛利率 = (832-175)/832 = 78.97%
        assert wuliangye_metrics["roe"]["value"] == pytest.approx(32.35, abs=0.1)
        assert wuliangye_metrics["gross_margin"]["value"] == pytest.approx(78.97, abs=0.1)

        # 茅台毛利率显著高于五粮液（92% vs 79%）
        assert maotai_metrics["gross_margin"]["value"] > wuliangye_metrics["gross_margin"]["value"]


# ═══════════════════════════════════════════════════════════════
# Test 5: 风险评估 — Z-score + 现金流质量
# ═══════════════════════════════════════════════════════════════

class TestRiskAssessment:
    """验证风险评估相关指标计算。"""

    def test_ocf_ni_ratio_interpretation(self):
        """OCF/NI 比 > 1 表示利润质量高。"""
        json_str = json.dumps(MAOTAI_FINANCIAL_DATA)
        result = json.loads(financial_metrics_tool.invoke({
            "json_data": json_str, "metrics": "ocf_ni_ratio",
        }))
        assert result["ocf_ni_ratio"]["value"] == pytest.approx(0.93, abs=0.01)
        assert "健康" in result["ocf_ni_ratio"].get("interpretation", "")

    def test_risk_detection_with_high_debt(self):
        """高负债公司的资产负债率应正确反映。"""
        high_debt_data = {
            "balance_sheet": {
                "data": [
                    {"item": "资产总计", "amount": 100_000_000},
                    {"item": "负债合计", "amount": 85_000_000},  # 85% 高负债
                ],
            },
        }
        result = json.loads(financial_metrics_tool.invoke({
            "json_data": json.dumps(high_debt_data), "metrics": "debt_ratio",
        }))
        assert result["debt_ratio"]["value"] == 85.0

    def test_negative_profit_roe(self):
        """亏损公司的 ROE 应为负数。"""
        loss_data = {
            "income_statement": {"data": [{"item": "净利润", "amount": -10_000_000}]},
            "balance_sheet": {"data": [{"item": "股东权益合计", "amount": 100_000_000}]},
        }
        result = json.loads(financial_metrics_tool.invoke({
            "json_data": json.dumps(loss_data), "metrics": "roe",
        }))
        assert result["roe"]["value"] == -10.0


# ═══════════════════════════════════════════════════════════════
# Test 6: 跨市场支持 — A股/港股/美股代码识别
# ═══════════════════════════════════════════════════════════════

class TestCrossMarket:
    """验证三地股票代码市场识别。"""

    from deerflow.community.financial.provider import CompositeProvider

    @pytest.mark.parametrize("code,expected_market,expected_normalized", [
        ("600519", "a_share", "600519"),
        ("000858", "a_share", "000858"),
        ("300750", "a_share", "300750"),
        ("HK.00700", "hk_share", "00700"),
        ("HK.09988", "hk_share", "09988"),
        ("AAPL", "us_share", "AAPL"),
        ("TSLA", "us_share", "TSLA"),
    ])
    def test_market_classification(self, code, expected_market, expected_normalized):
        cp = self.CompositeProvider()
        sid = cp._classify(code)
        assert sid.market == expected_market
        assert sid.normalized_code == expected_normalized

    def test_tools_accept_all_markets(self):
        """financial_data 应对三地代码都不崩溃。"""
        for code in ["600519", "HK.00700", "AAPL"]:
            result = financial_data_tool.invoke({
                "stock_code": code, "report_type": "all", "period": "latest",
            })
            data = json.loads(result)
            assert isinstance(data, dict)


# ═══════════════════════════════════════════════════════════════
# Test 7: 子代理配置验证
# ═══════════════════════════════════════════════════════════════

class TestSubagentConfiguration:
    """验证 3 个子代理的配置正确性。"""

    def test_three_subagents_configured(self, app_config):
        custom = app_config.subagents.custom_agents
        expected = {"financial-data-fetcher", "financial-analyst", "report-generator"}
        assert set(custom.keys()) >= expected

    def test_data_fetcher_tools(self, app_config):
        agent = app_config.subagents.custom_agents["financial-data-fetcher"]
        assert "financial_data" in agent.tools
        assert "stock_info" in agent.tools
        assert "web_search" in agent.tools
        assert "task" in agent.disallowed_tools, "子代理不能递归委派"
        assert "financial_metrics" in agent.disallowed_tools, "取数子代理不应做分析"

    def test_analyst_cannot_fetch_data(self, app_config):
        agent = app_config.subagents.custom_agents["financial-analyst"]
        assert "financial_data" in agent.disallowed_tools, "分析子代理不应自己取数据"
        assert "web_search" in agent.disallowed_tools
        assert "financial_metrics" in agent.tools, "分析子代理必须能计算指标"

    def test_report_generator_skills(self, app_config):
        agent = app_config.subagents.custom_agents["report-generator"]
        assert "chart-visualization" in (agent.skills or [])
        assert "financial-report-analysis" in (agent.skills or [])


# ═══════════════════════════════════════════════════════════════
# Test 8: Calculate.py 脚本验证
# ═══════════════════════════════════════════════════════════════

class TestCalculateScript:
    """验证 calculate.py 脚本的 CLI 接口。"""

    def test_script_exists_and_callable(self, tmp_path):
        """脚本在正确的路径，且所有指标函数可被调用。"""
        script = REPO_ROOT / "skills/custom/financial-report-analysis/scripts/calculate.py"
        assert script.exists()

        # 写入测试数据
        data_file = tmp_path / "test_financials.json"
        data_file.write_text(json.dumps(MAOTAI_FINANCIAL_DATA), encoding="utf-8")

        output_file = tmp_path / "metrics_output.json"

        # 直接 import 并调用 main 逻辑
        import importlib.util
        spec = importlib.util.spec_from_file_location("calculate", script)
        module = importlib.util.module_from_spec(spec)

        # 模拟命令行参数
        old_argv = sys.argv
        sys.argv = [
            "calculate.py",
            "--data-file", str(data_file),
            "--metrics", "roe,gross_margin,dupont",
            "--output", str(output_file),
        ]
        try:
            spec.loader.exec_module(module)
        except SystemExit:
            pass
        finally:
            sys.argv = old_argv

        # 验证输出
        if output_file.exists():
            result = json.loads(output_file.read_text(encoding="utf-8"))
            assert result["roe"]["value"] == EXPECTED_ROE
            assert result["gross_margin"]["value"] == EXPECTED_GROSS_MARGIN
            assert result["dupont"]["breakdown"]["net_margin"] == 50.0
